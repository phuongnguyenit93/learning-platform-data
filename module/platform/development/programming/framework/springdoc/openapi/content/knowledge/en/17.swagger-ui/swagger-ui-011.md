# Persisting UI Authentication State and Risks on Shared Machines

Swagger UI has an Authorize button allowing developers to enter an API key, Basic credentials, Bearer token, or run an OAuth flow before calling APIs with Try it out. By default, authentication state only persists for the current Swagger UI session. When the persistAuthorization option is enabled, Swagger UI preserves authorization data across page refreshes and even across closing and reopening the browser.

This feature is convenient on a personal development machine, yet it carries clear risks on shared machines. The next person opening Swagger UI in the same browser profile may see the active Authorize state and send requests using the previous person's permissions. Therefore, it is important to understand where data is stored, how it differs from server cookies/sessions, and how to disable or clear state properly.

## 1. What does Authorize in Swagger UI store?

The OpenAPI document describes the security schemes supported by the API. Swagger UI uses that metadata to render the Authorize dialog. Users can enter:

- An API key sent via header or query parameter.
- HTTP Basic username/password.
- A Bearer token, typically an access token such as a JWT or opaque token.
- An OAuth 2.0 authorization result.
- An OpenID Connect authorization result.

After the user authorizes, Swagger UI holds the authorization state to attach matching credentials to Try it out requests. This is browser-side state. It is not a login session managed by Spring Security and does not replace server-side authorization.

~~~mermaid
flowchart TD
    A["User opens Swagger UI"] --> B["Authorize"]
    B --> C["Enter API key / Basic / Bearer / OAuth"]
    C --> D["Swagger UI holds authorization state"]
    D --> E{"persistAuthorization"}
    E -->|false| F["Held in UI runtime only"]
    E -->|true| G["State saved to browser storage"]
    F --> H["Try it out sends request"]
    G --> H
    H --> I["Spring Security / API validates credential"]
    I --> J["Allow or deny request"]
~~~

Credentials attached by Swagger UI are not automatically trusted by the server. Every request must still pass authentication, authorization, scope/role checks, and API security policies.

## 2. How does persistAuthorization work?

Swagger UI provides the configuration option:

~~~javascript
SwaggerUIBundle({
    url: "/v3/api-docs",
    dom_id: "#swagger-ui",
    persistAuthorization: false
});
~~~

Meaning:

| Value | Behavior |
|---|---|
| false | Does not persist authorization data across UI reloads; this is the default |
| true | Persists authorization data so it is not lost after refreshing or closing/reopening the browser |

springdoc maps this Swagger UI option to a Spring Boot property:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

Or in application.properties:

~~~properties
springdoc.swagger-ui.persistAuthorization=false
~~~

When enabled:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: true
~~~

Swagger UI documentation explicitly states the default is false. springdoc also documents the same default and notes that authorization data will not be lost on browser close or refresh when true is enabled. Check the property reference for your exact springdoc branch if the project uses an older version.

## 3. Data is stored in browser storage

In Swagger UI, persistAuthorization uses browser-side storage to restore authorization state. In current Swagger UI implementations, this state is persisted across browser sessions using localStorage.

localStorage has the following characteristics:

- Data is scoped to the origin, meaning scheme, host, and port.
- Pages sharing the same origin can access the same localStorage area.
- Data survives page refreshes, closing tabs, and closing/reopening the browser.
- Data does not expire automatically over time like an access token.
- JavaScript running in the same origin can read the data.

For example, these two URLs are different origins because their schemes differ:

~~~text
http://docs.example.com
https://docs.example.com
~~~

These two applications share the same origin if scheme, host, and port match:

~~~text
https://tools.example.com/swagger-ui/
https://tools.example.com/admin/
~~~

Different paths do not create separate localStorage areas. Under the same origin, JavaScript from one application can access the shared storage per same-origin rules.

localStorage is not an encrypted secret vault. Never assume tokens are hashed, encrypted, or protected by the machine's OS password. Any script executing in that origin can read data accessible to that origin.

## 4. Comparing memory, localStorage, sessionStorage, and cookies

| Mechanism | Lifetime | Scope | Readable by JavaScript? |
|---|---|---|---|
| UI memory | Lifetime of current page | Swagger UI instance | Yes, via running app code |
| localStorage | Across refreshes and browser restarts until cleared | Same origin | Yes |
| sessionStorage | Within the page session; typically cleared when tab closes | Same origin and tab | Yes |
| HttpOnly cookie | According to expiry/session cookie | Domain/path and cookie policy | Not directly readable by JavaScript |
| Server-side session | According to timeout and server policy | By session identifier | Server manages state |

Do not confuse persistAuthorization with sessionStorage. Swagger UI documentation describes persistAuthorization as persisting authorization data across browser closes/refreshes; the standard configuration for this feature is not a switch to sessionStorage.

springdoc has use-local-storage and use-session-storage properties for CSRF tokens. Those control where Swagger UI retrieves CSRF tokens; they do not replace or change the persistAuthorization mechanism for credentials.

## 5. Risks on shared machines

Suppose an engineer authorizes with an admin-privileged access token on a lab machine. After they close the tab, someone else logs into the same browser profile and reopens Swagger UI on the same origin. If persistAuthorization remains enabled and data was not cleared, Swagger UI can restore the old credentials.

Key risks:

### Next user inherits the previous user's permissions

The next user can invoke endpoints with a still-valid token. They do not need to know the original password or token if Swagger UI has automatically restored authorization state.

### Tokens remain longer than users expect

Closing a tab or closing the browser does not clear localStorage. Tokens can remain until cleared, overwritten, or evicted by browser/storage policies.

### XSS or same-origin scripts read credentials

If a Cross-Site Scripting vulnerability allows JavaScript execution in Swagger UI's origin, malicious scripts can read authorization data from localStorage and exfiltrate it. CSP and dependency management reduce XSS risk but do not turn localStorage into a secret vault.

### Anyone with browser profile access can read the data

Shared machines may allow multiple people to access the same browser profile or OS account. Anyone able to access the profile can read browser data stored on the machine.

### Other applications on the same origin share storage

If Swagger UI and another application share scheme, host, and port, a script in that origin can access the same localStorage. Separating paths is not storage isolation.

### Credentials retain permissions even after the UI closes

Swagger UI does not control the lifetime of tokens issued by the authorization server. A token remains usable by any client until it expires or is rejected by the server/authorization server.

## 6. Do not confuse Swagger UI state with cookies/sessions

persistAuthorization manages authorization data used by Swagger UI for UI requests. It does not automatically govern every type of browser login.

For example, if the API uses session cookies:

- The browser may send session cookies automatically according to domain, path, SameSite, Secure, and credential mode.
- HttpOnly cookies cannot be read directly by JavaScript.
- Session cookies may still exist even when Swagger UI does not hold a Bearer token.
- Disabling persistAuthorization does not mean the server has logged out or the browser has deleted cookies.

If the system uses Spring Security session login, provide a logout endpoint and server-side timeout/invalidation. If using bearer tokens, apply appropriate expiry/revocation/introspection policies.

Similarly, the Logout button in Swagger UI's Authorize dialog removes authorization state from the UI and Swagger UI's corresponding storage. That action does not automatically call an OAuth revocation endpoint, invalidate issued JWTs, or terminate sessions in other systems.

## 7. Recommended policy for shared machines

For public machines, lab machines, demo machines, kiosks, or shared workstations:

1. Keep persistAuthorization set to false.
2. Never pre-authorize with admin tokens or production credentials.
3. Use test accounts with least privilege.
4. Issue short-lived access tokens with narrow scopes.
5. Never store client secrets in Swagger UI configuration.
6. When finished, click Logout inside the Authorize dialog.
7. Sign out of the application and identity provider if logged in via SSO.
8. Clear site data for that exact origin if handing the machine over to someone else.
9. Close the browser profile or sign out of the OS account per organizational procedure.

Do not treat closing a tab as clearing credentials. With localStorage, data can persist after tabs and browsers close.

### Decision table

| Environment | persistAuthorization | Policy |
|---|---|---|
| Public/lab machines | false | Must be disabled |
| Shared demo machines | false | Disable and use test tokens |
| Engineer's personal machine | false by default | Consider enabling only if needed and profile is controlled |
| Multi-user staging | false | Do not share authorization state |
| Production | false | Typically disable Swagger UI or protect strictly |
| CI/OpenAPI export | Not needed | Disable Swagger UI if pipeline only needs documents |

## 8. Secure configuration in Spring Boot

### Default configuration

Set false explicitly in shared configuration so readers see the intent:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    persist-authorization: false
~~~

Explicit declaration helps prevent another profile from accidentally enabling persistence without review.

### Production profile

If production does not need Swagger UI or OpenAPI endpoints, disable both separately:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
    persist-authorization: false
~~~

Disabling Swagger UI does not automatically disable OpenAPI JSON/YAML endpoints. Disabling API docs also does not replace security policies for business REST endpoints. Verify both paths after deployment.

If production needs internal documentation, keep the UI and API docs behind Spring Security or a gateway, restrict users by role, and never enable persistence on shared workstations.

### Separate personal machine profile

If an engineering team genuinely needs state preserved across refreshes on individually managed personal machines, enable it in a dedicated profile:

~~~yaml
# application-personal-dev.yml
springdoc:
  swagger-ui:
    persist-authorization: true
~~~

Use this configuration only when the browser profile is not shared, the machine is locked when unattended, tokens have least privilege and short lifetimes, and users know how to logout/clear site data. Never place this profile into default or shared profiles.

Do not enable persistence merely to avoid pasting tokens occasionally. Weigh token lifetime, token privileges, and API sensitivity first.

## 9. OAuth 2.0, OpenID Connect, and client secrets

Swagger UI runs in the browser, making it a public client. Any configuration sent to the browser can be inspected by users.

### Do not embed production client secrets

springdoc has a property for configuring an OAuth client secret, yet documentation warns against using it in production because it exposes sensitive security credentials.

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: swagger-ui-public-client
      # Do not configure a production client-secret in the browser
      use-pkce-with-authorization-code-grant: true
~~~

With OAuth authorization code flow for a public client, use Proof Key for Code Exchange (PKCE) when supported by the authorization server. PKCE protects the authorization code exchange; it does not encrypt tokens saved by persistAuthorization and does not stop same-origin JavaScript from reading tokens.

### Restricting tokens

- Request only scopes required for testing actions.
- Use short-lived access tokens.
- Do not store refresh tokens in Swagger UI without a clear protective design.
- Do not use broad-privileged production tokens for API testing.
- Do not put tokens into URLs, query strings, logs, screenshots, or tickets.
- Configure the authorization server to revoke tokens/sessions when needed.

Short-lived tokens limit the exposure window if leaked, but do not replace clearing storage and revoking credentials.

## 10. Logout and token revocation are two different actions

When a user selects Logout in the Authorize dialog:

- Swagger UI clears authorization state for the corresponding security scheme.
- If persistence is enabled, Swagger UI updates stored state so login does not auto-restore on the next load.
- Subsequent Try it out requests no longer use the credential logged out in the UI.

However:

- Already issued access tokens may still be valid.
- Refresh tokens may still be valid if the authorization server has not revoked them.
- SSO sessions may still be active.
- Application session cookies may still remain in the browser.

Full session termination depends on authentication type:

| Authentication type | Required action |
|---|---|
| API key | Logout from UI and revoke/rotate the key in the issuing system if exposed |
| Bearer access token | Logout from UI; wait for expiry or revoke via server mechanism |
| OAuth 2.0 | Logout from UI; call revocation endpoint if token revocation is needed; logout authorization server per policy |
| OIDC SSO | End application session and perform provider logout if needed |
| Cookie session | Call application's logout endpoint to invalidate session; clear cookies per policy |

For stateless JWTs, deleting the token from the browser does not invalidate the JWT on the server. If early revocation is required, the system must implement mechanisms such as a denylist, token introspection, or an appropriate key/session strategy.

## 11. Clearing authorization data on shared machines

Follow these steps in order:

1. In Swagger UI, open Authorize and choose Logout for every authorized security scheme.
2. Log out of the application and identity provider if signed in with SSO.
3. Open browser site data settings or Developer Tools.
4. Select Swagger UI's exact origin.
5. Clear site data/local storage according to your organization's browser management procedures.
6. Reload Swagger UI and verify the Authorize button no longer shows an authenticated state.
7. Test a request requiring authentication; it must be rejected until fresh credentials are entered.

In Chrome/Edge DevTools, open Application, inspect Storage and Local Storage for the exact origin. Never copy token values into the clipboard, tickets, or logs to prove deletion. Only verify the presence/absence of the authorization record or UI state.

Clearing all site data for an origin may simultaneously clear cookies, local storage, IndexedDB, and other data for apps on that origin. If multiple apps share the origin, coordinate with administrators before wiping all data.

Do not rely on deleting a hardcoded localStorage key name without checking your exact Swagger UI version. Key details and serialized state structure are implementation details subject to change. Prefer the Logout button and Clear site data scoped to the exact origin.

### Incognito/Private browsing

Private browsing uses isolated storage for a private session. Under common browser behavior, private localStorage data is cleared when the last private tab closes. However, that is not a reason to enable persistAuthorization on public machines:

- Credentials can still be read while the private window remains open.
- Another user could use the open private session if the machine is unattended.
- Browser extensions or malicious scripts in the session can still read same-origin data.
- Private mode does not replace logout and token revocation.

## 12. Do not confuse CSRF storage with authorization persistence

springdoc has separate CSRF settings:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
      use-local-storage: false
      use-session-storage: false
      cookie-name: XSRF-TOKEN
      header-name: X-XSRF-TOKEN
~~~

The use-local-storage and use-session-storage properties specify where to read the CSRF token to attach to requests. They do not govern where Swagger UI stores Bearer tokens, API keys, or OAuth authorization state.

For example:

- persist-authorization: controls retaining authorization data across reloads.
- csrf.use-session-storage: reads the CSRF token from sessionStorage.
- csrf.use-local-storage: reads the CSRF token from localStorage.

Do not enable CSRF local storage thinking it will move Bearer tokens to sessionStorage.

## 13. Restricting Try it out does not clear credentials

Try it out methods can be disabled:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

This prevents Swagger UI from sending Try it out requests for all HTTP methods. Operations can still be viewed in the document. This option is useful for read-only docs, yet it does not delete saved authorization data and does not replace disabling persistAuthorization.

Likewise, disabling Swagger UI does not disable API docs endpoints. If docs are unwanted in production, configure both springdoc.swagger-ui.enabled and springdoc.api-docs.enabled separately.

## 14. Avoid overriding configuration via URL

Swagger UI supports receiving configuration from multiple sources. Do not enable queryConfigEnabled to allow URL query strings to override security configurations such as persistAuthorization.

queryConfigEnabled defaults to false. springdoc marks URL query-string config overrides as legacy and includes related security warnings. Keep this option false; do not let users alter security-sensitive settings via query strings.

Never place tokens in URL query parameters. URLs can appear in browser history, proxy logs, analytics, referrers, or screenshots.

## 15. Verifying configuration and actual behavior

Do not just read application.yml. Verify the effective configuration after Spring Boot loads profiles, environment variables, and config servers.

### Checking configuration

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

If multiple profiles exist, search for overrides of:

- springdoc.swagger-ui.persistAuthorization
- springdoc.swagger-ui.enabled
- springdoc.api-docs.enabled
- springdoc.swagger-ui.oauth.clientSecret
- springdoc.swagger-ui.queryConfigEnabled

Ensure production and shared-workstation profiles do not enable persistence.

### Browser testing

In a test environment with dummy credentials:

1. Open Swagger UI and authorize.
2. Refresh the page.
3. With persistAuthorization=false, Authorize state must not restore from local storage.
4. When testing true on a dedicated test machine, state can be restored after refresh and browser restart.
5. Click Logout then refresh; authorization state must no longer restore.
6. Confirm tokens do not appear in URLs, console logs, or application logs.

Never test with real production tokens. Never screenshot or save token values from DevTools.

## 16. Inspecting with DevTools without exposing tokens

Developer Tools can verify storage behavior:

- Select Swagger UI's exact origin.
- Open Application or Storage.
- Inspect Local Storage and Session Storage.
- Verify only the presence/absence of authorization state or changes after Logout.
- Do not expand or copy sensitive values.
- After verification, clear site data for the test environment.

If automated testing is needed, use dummy tokens and disposable browser profiles. Tests can assert that after reloading with persistAuthorization=false, the Authorize button returns to an unauthenticated state without reading or asserting real token values in storage.

## 17. Policy for CI and deployment environments

CI pipelines needing OpenAPI JSON/YAML only to validate or publish artifacts typically do not need Swagger UI:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
    persist-authorization: false
~~~

Production environments not serving docs:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
    persist-authorization: false
~~~

Internal environments with Swagger UI:

- Protect UI and API docs using Spring Security or a gateway.
- Restrict users by role.
- Keep persistence off on shared machines.
- Never configure production client secrets in JavaScript/browsers.
- Use short-lived access tokens with narrow scopes.
- Enable server-side auditing for impactful test actions.

Swagger UI is only a client. It grants no permissions on its own and does not replace securing API endpoints.

## 18. Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Reopening Swagger UI still shows Authorized | persistAuthorization is enabled and storage still holds data | Disable property, Logout, and clear site data for that origin |
| Browser closed yet token remains | localStorage persists across browser restarts | Do not rely on closing the browser as cleanup |
| Another user can call APIs on a lab machine | Shared browser profile/origin with saved auth state | Disable persistence, logout, clear site data, and use separate profiles |
| persistAuthorization disabled yet requests carry cookies | Cookies/sessions are managed independently by the browser | Logout server session and clear cookies per policy |
| Clicked Logout yet token still works via curl | UI logout does not revoke access tokens | Revoke token or wait for expiry; verify server policy |
| Enabled CSRF use-session-storage yet Bearer token persists | The two properties govern different types of data | Disable persistAuthorization separately |
| Swagger UI auto-authorizes after reload | Pre-authorization config or custom plugin outside persistAuthorization | Check configUrl, init scripts, and custom JavaScript |
| Token leaked in console/logs | Custom interceptor or logging prints request headers | Redact Authorization; never log tokens |
| Client secret appears in page source | OAuth clientSecret config sent to browser | Remove client secret; use public client and PKCE |
| Clearing site data logs out another app | Multiple apps share origin storage/cookies | Separate origins or coordinate cleanup scope |

## 19. Checklist before using persistAuthorization

- [ ] Understood that persistAuthorization defaults to false.
- [ ] Identified which credentials Swagger UI retains.
- [ ] Identified browser storage and origin scope.
- [ ] Persistence is disabled on public, lab, or shared profiles.
- [ ] No production tokens or overly broad credentials are saved.
- [ ] Access tokens have short lifetimes and minimal scopes.
- [ ] No client secret is embedded in browser configuration.
- [ ] PKCE is enabled for public OAuth clients when appropriate.
- [ ] Server cookies/sessions are managed separately from Swagger UI authorization state.
- [ ] UI Logout is not confused with token revocation/server logout.
- [ ] Clear site data procedure exists when handing over machines.
- [ ] CSRF storage is not confused with authorization persistence.
- [ ] queryConfigEnabled is not enabled to override security settings.
- [ ] CI enables API docs only when UI is unnecessary.
- [ ] Production disables or protects both Swagger UI and API docs per policy.
- [ ] Tested reload/logout with dummy tokens on a dedicated browser profile.

## 20. Official references

- [Swagger UI Configuration – Authorization](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): persistAuthorization, default false, and behavior retaining authorization across browser closes/refreshes.
- [Swagger UI issue 8711](https://github.com/swagger-api/swagger-ui/issues/8711): upstream discussion on persistAuthorization storing authorization state in localStorage.
- [springdoc Swagger UI Properties](https://springdoc.org/ui-properties.html): springdoc.swagger-ui.persistAuthorization property and CSRF storage options.
- [springdoc Configuration Properties](https://springdoc.org/properties.html): Swagger UI properties, queryConfigEnabled, and OAuth client secret warning.
- [Swagger UI OAuth 2.0](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/): configuring OAuth flows and PKCE.
- [MDN Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API): differences between localStorage and sessionStorage.
- [MDN Window.localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage): origin scope and persistence across browser sessions.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): risks of storing sensitive info in Web Storage and XSS.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): recommendation against storing tokens/session IDs/JWTs/refresh tokens in localStorage or sessionStorage.
- [Spring Security Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout and server-side session invalidation.

## Conclusion

persistAuthorization lets Swagger UI keep Authorize state across refreshes and browser restarts, while causing credentials to linger longer in browser profiles. On shared machines, keep this option set to false, use narrowly scoped short-lived test tokens, Logout from both the UI and login systems, and clear site data for the exact origin when handing off the machine. Always distinguish Swagger UI's authorization state from server-issued cookies/sessions and tokens: clearing UI state does not automatically revoke tokens or end server sessions. localStorage can be read by same-origin JavaScript, so never treat it as a secure vault for credentials.
