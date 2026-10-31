import { useEffect, useState } from "react";
import { LoaderCircle, RefreshCw, ShieldCheck, Users } from "lucide-react";

type UserProfile = {
  username: string;
  role: "user" | "admin";
  learning_level: string;
  goal: string;
  time_horizon: string;
  risk_comfort: string;
};

export default function AdminProfiles() {
  const [profiles, setProfiles] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadProfiles() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/admin/profiles", {
        credentials: "same-origin",
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(body?.detail || "Could not load user profiles.");
      }
      const result = (await response.json()) as { profiles: UserProfile[] };
      setProfiles(result.profiles);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Could not load user profiles.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProfiles();
  }, []);

  return (
    <section className="admin-profiles">
      <div className="admin-heading">
        <div>
          <div className="conversation-kicker">
            <ShieldCheck size={14} /> ADMINISTRATION
          </div>
          <h2>User learning profiles</h2>
          <p>View the learning profiles associated with registered accounts.</p>
        </div>
        <button
          className="admin-refresh"
          type="button"
          onClick={() => void loadProfiles()}
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          Refresh
        </button>
      </div>

      {error && <p className="admin-message error" role="alert">{error}</p>}

      {loading ? (
        <div className="admin-loading">
          <LoaderCircle size={17} className="spin" /> Loading user profiles…
        </div>
      ) : !error && profiles.length === 0 ? (
        <div className="admin-empty"><Users size={20} /> No profiles found.</div>
      ) : !error ? (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col">Username</th>
                <th scope="col">Role</th>
                <th scope="col">Experience</th>
                <th scope="col">Learning goal</th>
                <th scope="col">Time horizon</th>
                <th scope="col">Risk comfort</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((profile) => (
                <tr key={profile.username}>
                  <th scope="row">{profile.username}</th>
                  <td><span className={`admin-role ${profile.role}`}>{profile.role}</span></td>
                  <td>{profile.learning_level}</td>
                  <td>{profile.goal || "—"}</td>
                  <td>{profile.time_horizon || "—"}</td>
                  <td>{profile.risk_comfort || "Not specified"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className="admin-privacy-note">
        This view contains personal learning-profile information. Access is
        limited to administrator accounts.
      </p>
    </section>
  );
}
