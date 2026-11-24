# Mapping Business Permissions to GrantedAuthority in Spring Security Servlet

**Scope:** Java 17+, Spring Security 6.x, and a Spring Boot application running on Jakarta Servlet. This lesson belongs to the **Accounts** section. The focus is on translating user, role, and permission data from a business system into <code>GrantedAuthority</code> values that Spring Security understands, then testing real authentication and authorization. The complete example uses Spring Boot 3.3.5, Spring JDBC, H2, HTTP Basic, and MockMvc.

In a real product, a database may store users belonging to groups such as "Accounting", "Administration", "Report Viewer", or fine-grained permissions like "Allowed to export reports". Spring Security does not automatically infer the meaning of these codes. The application must build a **trusted, consistent, and tested mapping step** before Spring Security uses the data to decide whether a request may proceed.

## 1. Three Concepts to Distinguish

| Concept | Example | Responsibility |
| --- | --- | --- |
| **Business account** | Account record ID 42, username <code>analyst</code>, status ACTIVE | Identity and account state; may relate to department, organization, tenant |
| **Role (business role)** | <code>ANALYST</code>, <code>ADMIN</code> | Responsibility grouping typically assigned to users in the business model |
| **Operation permission (permission)** | <code>report:read</code>, <code>report:export</code> | Specific capability the application wants to permit or deny |
| **GrantedAuthority** | <code>ROLE_ANALYST</code> or <code>report:read</code> | Verified permission representation in Spring Security that rules match against |

<code>GrantedAuthority</code> is an interface in <code>org.springframework.security.core</code>; its key method is <code>String getAuthority()</code>. <code>SimpleGrantedAuthority</code> is a common implementation holding an authority string. When authentication succeeds, <code>Authentication.getAuthorities()</code> contains the list of authorities attached to the authenticated identity.

**A business role is not automatically an authority.** The system must define rules converting role codes, business permissions, and scope of application. Never take a self-declared field from a request JSON, such as <code>{"role":"ADMIN"}</code>, to construct <code>SimpleGrantedAuthority("ROLE_ADMIN")</code>. Granted authority values must come from a verified source or trusted authentication mechanism.

### How Do Roles and Permissions Relate?

Suppose the business defines two roles:

| Role in database | Permissions in database | Generated GrantedAuthority |
| --- | --- | --- |
| <code>ANALYST</code> | <code>report:read</code> | <code>ROLE_ANALYST</code>, <code>report:read</code> |
| <code>ADMIN</code> | <code>report:read</code>, <code>report:export</code> | <code>ROLE_ADMIN</code>, <code>report:read</code>, <code>report:export</code> |

The example above has **no default "ADMIN automatically implies all permissions"**. ADMIN's permissions are granted explicitly via role–permission relations. If you want role hierarchies or permission inheritance, you must configure and test them separately, rather than inferring them from the name ADMIN.

## 2. Distinguishing hasRole and hasAuthority

In Spring Security, two common expressions are:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/reports").hasAuthority("report:read")
~~~

Under the default configuration, <code>hasRole("ADMIN")</code> looks for authority <code>ROLE_ADMIN</code>. Conversely, <code>hasAuthority("report:read")</code> matches the exact string <code>report:read</code>; it **does not automatically add a prefix**.

| Held authority | Check | Result |
| --- | --- | --- |
| <code>ROLE_ADMIN</code> | <code>hasRole("ADMIN")</code> | Passes |
| <code>ADMIN</code> | <code>hasRole("ADMIN")</code> | Fails under default prefix |
| <code>ROLE_ADMIN</code> | <code>hasAuthority("ROLE_ADMIN")</code> | Passes |
| <code>report:export</code> | <code>hasAuthority("report:export")</code> | Passes |
| <code>ROLE_ANALYST</code> | <code>hasAuthority("report:read")</code> | Does not pass automatically; requires permission mapping or separate role rule |

**Recommended convention:** store business role codes in the database as <code>ADMIN</code>, <code>ANALYST</code>; add <code>ROLE_</code> when mapping to Spring Security. Use stable permission codes, such as <code>report:read</code>, and keep them unchanged when wrapping in <code>SimpleGrantedAuthority</code>. Do not mix these two namespaces.

Direct creation example:

~~~java
GrantedAuthority role =
    new SimpleGrantedAuthority("ROLE_ADMIN");
GrantedAuthority permission =
    new SimpleGrantedAuthority("report:export");
~~~

The snippet above illustrates syntax inside a class importing <code>GrantedAuthority</code> and <code>SimpleGrantedAuthority</code>; it does not prove a real user holds those permissions. That proof comes from trusted business data, account status, and resource-ownership constraints.

## 3. Data-to-Authority Conversion Flow in a Servlet Application

With HTTP Basic or form login backed by username/password and <code>DaoAuthenticationProvider</code>, the typical flow is:

~~~text
HTTP request + username/password
    |
    v
Spring Security authentication filters
    |
    v
AuthenticationManager / DaoAuthenticationProvider
    |
    v
UserDetailsService.loadUserByUsername(username)
    |
    +-- Read account: password hash + status
    +-- Read granted roles
    +-- Read permissions for those roles
    +-- Validate permission codes
    '-- Map -> Collection<GrantedAuthority>
    |
    v
Verify password / account status
    |
    v
Authenticated Authentication + GrantedAuthority
    |
    v
SecurityContext -> AuthorizationFilter / method security
    |
    v
hasRole / hasAuthority / resource policies
~~~

<code>UserDetailsService</code> is only responsible for loading <code>UserDetails</code> from a username; **it does not compare passwords itself**. The appropriate authentication component verifies the password hash via <code>PasswordEncoder</code> and checks account status. <code>UserDetails.getAuthorities()</code> supplies authorities for Spring Security to use at the authorization step.

In applications that store authentication in a session, authority data is normally loaded at login and may remain in <code>SecurityContext</code> across requests. If roles in the database just changed, the held authentication **does not automatically update immediately**. With HTTP Basic, credentials are normally re-authenticated per request, though caching and authentication configuration can affect when data is re-read. Permission revocation policies must be designed explicitly.

For OAuth2/OIDC or JWT resource servers, Spring Security has a different path: converters map claims/scopes to authorities; <code>UserDetailsService</code> is not always called. You must identify **which authority source is actually in use** before modifying mapping code.

## 4. Database Model: account, role, permission

Example business data normalized into five tables:

~~~text
app_account
  id, login_name, password_hash, status
       |
       | 1 - n
       v
app_account_role ------------> app_role
  account_id, role_code         role_code
                                       |
                                       | 1 - n
                                       v
                              app_role_permission
                              role_code, permission_code
                                       |
                                       v
                                 app_permission
                                 permission_code
~~~

Rules:
- <code>app_account.status</code> can be ACTIVE or DISABLED. A DISABLED account cannot log in even if it still has roles in the table.
- One account can have multiple roles, one role can have multiple permissions, and a permission can belong to multiple roles.
- Primary keys/foreign keys prevent duplicate-data bugs and references to nonexistent roles.
- The source granting roles/permissions must be protected by an administrative workflow with authorization, auditing, and only allow approved codes.
- In a multi-tenant model, associations must be tied to a tenant and checked on every resource; **never automatically elevate one tenant's permissions into system-wide permissions**.

For example, role ANALYST carries <code>report:read</code>. Role ADMIN carries both <code>report:read</code> and <code>report:export</code>. An account holding both roles receives the deduplicated union of authorities without producing duplicate <code>report:read</code> entries.

## 5. Runnable Spring Boot Project

Structure:

~~~text
business-authorities/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/businessauth/
    │   │   ├── BusinessAuthApplication.java
    │   │   ├── BusinessSecurityConfiguration.java
    │   │   ├── BusinessUserDetailsService.java
    │   │   └── ReportController.java
    │   └── resources/
    │       └── schema.sql
    └── test/
        └── java/com/example/businessauth/
            └── BusinessAuthorityTest.java
~~~

The demo uses in-memory H2 to run standalone; H2 and test accounts **do not represent production password storage and management**. In real projects, replace H2 with a managed data source, use migrations like Flyway/Liquibase, and integrate with your organization's identity system.

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>business-authorities</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 5.2. schema.sql

Create <code>src/main/resources/schema.sql</code>:

~~~sql
CREATE TABLE app_account (
    id BIGINT PRIMARY KEY,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE app_role (
    role_code VARCHAR(40) PRIMARY KEY
);

CREATE TABLE app_permission (
    permission_code VARCHAR(80) PRIMARY KEY
);

CREATE TABLE app_account_role (
    account_id BIGINT NOT NULL,
    role_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (account_id, role_code),
    FOREIGN KEY (account_id) REFERENCES app_account(id),
    FOREIGN KEY (role_code) REFERENCES app_role(role_code)
);

CREATE TABLE app_role_permission (
    role_code VARCHAR(40) NOT NULL,
    permission_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (role_code, permission_code),
    FOREIGN KEY (role_code) REFERENCES app_role(role_code),
    FOREIGN KEY (permission_code) REFERENCES app_permission(permission_code)
);
~~~

Spring Boot with embedded H2 and default SQL initialization executes <code>schema.sql</code> when initializing the DataSource. The demo seeds data via <code>ApplicationRunner</code> once the schema is ready. If switching to PostgreSQL/MySQL in a real project, configure migrations and initialization ordering for that database rather than relying on the H2 demo.

### 5.3. Main Class and Seed Data

Create <code>src/main/java/com/example/businessauth/BusinessAuthApplication.java</code>:

~~~java
package com.example.businessauth;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class BusinessAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(BusinessAuthApplication.class, args);
    }

    @Bean
    ApplicationRunner seedData(JdbcTemplate db, PasswordEncoder encoder) {
        return args -> {
            db.update("INSERT INTO app_role(role_code) VALUES (?)", "ANALYST");
            db.update("INSERT INTO app_role(role_code) VALUES (?)", "ADMIN");

            db.update("INSERT INTO app_permission(permission_code) VALUES (?)",
                    "report:read");
            db.update("INSERT INTO app_permission(permission_code) VALUES (?)",
                    "report:export");

            db.update("INSERT INTO app_role_permission(role_code, permission_code) "
                    + "VALUES (?, ?)", "ANALYST", "report:read");
            db.update("INSERT INTO app_role_permission(role_code, permission_code) "
                    + "VALUES (?, ?)", "ADMIN", "report:read");
            db.update("INSERT INTO app_role_permission(role_code, permission_code) "
                    + "VALUES (?, ?)", "ADMIN", "report:export");

            db.update("INSERT INTO app_account(id, login_name, password_hash, status) "
                    + "VALUES (?, ?, ?, ?)", 1L, "analyst",
                    encoder.encode("analyst-pass"), "ACTIVE");
            db.update("INSERT INTO app_account(id, login_name, password_hash, status) "
                    + "VALUES (?, ?, ?, ?)", 2L, "admin",
                    encoder.encode("admin-pass"), "ACTIVE");
            db.update("INSERT INTO app_account(id, login_name, password_hash, status) "
                    + "VALUES (?, ?, ?, ?)", 3L, "suspended",
                    encoder.encode("suspended-pass"), "DISABLED");

            db.update("INSERT INTO app_account_role(account_id, role_code) "
                    + "VALUES (?, ?)", 1L, "ANALYST");
            db.update("INSERT INTO app_account_role(account_id, role_code) "
                    + "VALUES (?, ?)", 2L, "ADMIN");
            db.update("INSERT INTO app_account_role(account_id, role_code) "
                    + "VALUES (?, ?)", 3L, "ANALYST");
        };
    }
}
~~~

The demo creates three accounts: analyst, admin, and suspended. The suspended account still has the ANALYST role to highlight that **having a role does not mean being permitted to authenticate**. Passwords are encoded via <code>PasswordEncoder</code> before saving, never stored in plaintext in the database. The hardcoded passwords in the example are strictly localhost fixtures.

### 5.4. Main Mapping Step: UserDetailsService

Create <code>src/main/java/com/example/businessauth/BusinessUserDetailsService.java</code>:

~~~java
package com.example.businessauth;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class BusinessUserDetailsService implements UserDetailsService {

    private static final Set<String> KNOWN_ROLES =
            Set.of("ANALYST", "ADMIN");
    private static final Set<String> KNOWN_PERMISSIONS =
            Set.of("report:read", "report:export");

    private final JdbcTemplate db;

    public BusinessUserDetailsService(JdbcTemplate db) {
        this.db = db;
    }

    private record Account(
            long id, String login, String passwordHash, String status) { }

    @Override
    public UserDetails loadUserByUsername(String username) {
        List<Account> matches = db.query(
            "SELECT id, login_name, password_hash, status "
                    + "FROM app_account WHERE login_name = ?",
            (rs, index) -> new Account(
                rs.getLong("id"),
                rs.getString("login_name"),
                rs.getString("password_hash"),
                rs.getString("status")),
            username
        );

        if (matches.isEmpty()) {
            throw new UsernameNotFoundException("Account not found");
        }
        Account account = matches.get(0);

        List<String> roles = db.queryForList(
            "SELECT role_code FROM app_account_role "
                    + "WHERE account_id = ? ORDER BY role_code",
            String.class, account.id()
        );

        List<String> permissions = db.queryForList(
            "SELECT DISTINCT rp.permission_code "
                    + "FROM app_account_role ar "
                    + "JOIN app_role_permission rp "
                    + "ON rp.role_code = ar.role_code "
                    + "WHERE ar.account_id = ? "
                    + "ORDER BY rp.permission_code",
            String.class, account.id()
        );

        Set<GrantedAuthority> unique = new LinkedHashSet<>();

        for (String roleCode : roles) {
            if (!KNOWN_ROLES.contains(roleCode)) {
                throw new IllegalStateException("Unknown business role");
            }
            unique.add(new SimpleGrantedAuthority("ROLE_" + roleCode));
        }

        for (String permissionCode : permissions) {
            if (!KNOWN_PERMISSIONS.contains(permissionCode)) {
                throw new IllegalStateException("Unknown business permission");
            }
            unique.add(new SimpleGrantedAuthority(permissionCode));
        }

        if (!Set.of("ACTIVE", "DISABLED").contains(account.status())) {
            throw new IllegalStateException("Unknown account status");
        }

        return User.withUsername(account.login())
            .password(account.passwordHash())
            .authorities(new ArrayList<>(unique))
            .disabled(!"ACTIVE".equals(account.status()))
            .build();
    }
}
~~~

**Why is the mapping written this way?**

1. Reads the account using a parameterized SQL query with <code>?</code>; never concatenates <code>username</code> directly into SQL.
2. Reads the roles granted to the account via a foreign-keyed junction table, then retrieves all permissions associated with those roles.
3. Validates role/permission codes against the set recognized by the application; new codes cannot implicitly grant privileges merely by appearing in data.
4. Roles get the <code>ROLE_</code> prefix; permissions keep <code>report:read</code>/<code>report:export</code> intact.
5. <code>LinkedHashSet</code> removes duplicate authorities if multiple roles share the same permission.
6. A DISABLED account returns a <code>UserDetails</code> with <code>isEnabled() == false</code>; the authentication provider will reject login even if the password is right.
7. <code>User.withUsername(...)</code> is the standard way to build <code>UserDetails</code>. For systems needing an account ID or tenant context on the principal, you can create a custom <code>UserDetails</code> and check those attributes in application policies.

The <code>KNOWN_ROLES</code> and <code>KNOWN_PERMISSIONS</code> sets are intentionally fixed in the demo to demonstrate **fail closed**: adding a new permission code requires updating the contract and corresponding tests. Larger systems maintain a governed role/permission registry and controlled migrations. When data contains an unknown code, throwing an error rather than silently granting permissions is shown here. Operational alerts and synchronized migrations are needed to prevent unintended login failures; never turn an "unknown role" into "ADMIN".

**Do not simply turn department names or display job titles into authorities** by prepending a prefix. "Accounting" or "Sales Department" can be mutable display labels; authorities need stable codes, clear namespaces, and a governed grant workflow.

### 5.5. SecurityFilterChain and PasswordEncoder

Create <code>src/main/java/com/example/businessauth/BusinessSecurityConfiguration.java</code>:

~~~java
package com.example.businessauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BusinessSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/info")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/admin/panel")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/reports/export")
                    .hasAuthority("report:export")
                .requestMatchers(HttpMethod.GET, "/reports")
                    .hasAuthority("report:read")
                .anyRequest()
                    .denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

The configuration above uses a default chain covering all requests, ending with <code>denyAll()</code>. Unlisted endpoints are not left open by default. HTTP Basic makes experimenting with mapping easy; real applications can use form login, OIDC, tokens, or another authentication mechanism.

<code>PasswordEncoderFactories.createDelegatingPasswordEncoder()</code> by default creates hashes prefixed with the algorithm identifier such as <code>{bcrypt}</code> in stored strings. At login, Spring Security picks the matching encoder to verify the password. Never compare raw password strings directly with database hashes, and never write a custom plaintext password encoder to "fix" login errors.

**Default CSRF remains enabled.** The example only uses state-safe GETs, so disabling CSRF is unnecessary. When adding POST/PUT/DELETE with cookie/session mechanisms, design proper CSRF tokens; never confuse CSRF issues with <code>GrantedAuthority</code> permissions.

### 5.6. Controller to Observe Permissions

Create <code>src/main/java/com/example/businessauth/ReportController.java</code>:

~~~java
package com.example.businessauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/public/info")
    public String info() {
        return "public";
    }

    @GetMapping("/reports")
    public String reports() {
        return "report-list";
    }

    @GetMapping("/reports/export")
    public String exportReports() {
        return "report-export";
    }

    @GetMapping("/admin/panel")
    public String adminPanel() {
        return "admin-panel";
    }
}
~~~

The controller does not need to query user_roles every time to grant access; Spring Security rules inspect the authentication's authorities. However, if an endpoint accesses specific resources by <code>reportId</code> or <code>tenantId</code>, permission to call the route is a **necessary but insufficient** condition: you must also verify which specific resources the account is allowed to view/edit, as analyzed in Section 9.

## 6. Running the Application and Predicting Results

In the directory containing <code>pom.xml</code>:

~~~bash
mvn test
mvn spring-boot:run
~~~

In-memory H2 is created when the application starts. <code>schema.sql</code> creates the tables, and <code>ApplicationRunner</code> inserts sample data. On restart, the in-memory H2 database is re-initialized.

Using curl:

~~~bash
# Public, no login required.
curl -i http://localhost:8080/public/info

# No credentials -> HTTP 401.
curl -i http://localhost:8080/reports

# Analyst has report:read -> HTTP 200.
curl -i -u analyst:analyst-pass http://localhost:8080/reports

# Analyst lacks report:export -> HTTP 403.
curl -i -u analyst:analyst-pass http://localhost:8080/reports/export

# Admin has report:export -> HTTP 200.
curl -i -u admin:admin-pass http://localhost:8080/reports/export

# Admin has ROLE_ADMIN -> HTTP 200.
curl -i -u admin:admin-pass http://localhost:8080/admin/panel

# Analyst lacks ROLE_ADMIN -> HTTP 403.
curl -i -u analyst:analyst-pass http://localhost:8080/admin/panel

# DISABLED account despite right password -> HTTP 401.
curl -i -u suspended:suspended-pass http://localhost:8080/reports
~~~

Expected table:

| Caller | GET /reports | GET /reports/export | GET /admin/panel |
| --- | --- | --- | --- |
| Anonymous | 401 | 401 | 401 |
| analyst / analyst-pass | 200 | 403 | 403 |
| admin / admin-pass | 200 | 200 | 200 |
| suspended / suspended-pass | 401 | 401 | 401 |

Results depend strictly on the demo code just created, without accounting for custom exception handlers, gateways, sessions, or other filters. The status sequence is the **expected result when running**, not logs from an executed run.

If you test only an ADMIN account, you might miss bugs granting excessive permissions to ANALYST. You must test both present and absent permissions, disabled accounts, and newly undeclared URLs.

## 7. Testing Mapping and Behavior with MockMvc

Create <code>src/test/java/com/example/businessauth/BusinessAuthorityTest.java</code>:

~~~java
package com.example.businessauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BusinessAuthorityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    UserDetailsService users;

    @Test
    void businessRolesAndPermissionsBecomeAuthorities() {
        UserDetails analyst = users.loadUserByUsername("analyst");
        UserDetails admin = users.loadUserByUsername("admin");

        assertThat(analyst.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder("ROLE_ANALYST", "report:read");

        assertThat(admin.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder(
                "ROLE_ADMIN", "report:read", "report:export");
    }

    @Test
    void analystCanReadButCannotExport() throws Exception {
        mvc.perform(get("/reports")
                .with(httpBasic("analyst", "analyst-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-list"));

        mvc.perform(get("/reports/export")
                .with(httpBasic("analyst", "analyst-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminHasBothPermissionAndRole() throws Exception {
        mvc.perform(get("/reports/export")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-export"));

        mvc.perform(get("/admin/panel")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-panel"));
    }

    @Test
    void missingCredentialsAndDisabledAccountAreRejected() throws Exception {
        mvc.perform(get("/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/reports")
                .with(httpBasic("suspended", "suspended-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unlistedRouteIsDeniedForAuthenticatedUser() throws Exception {
        mvc.perform(get("/new-admin-feature")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

The test suite verifies two **separate** aspects:
- **Mapping:** real account/role/permission data produces the right set of authorities in <code>UserDetails</code>.
- **Behavior:** when requests traverse the security filter chain, only accounts with matching authorities can access endpoints.

Do not just assert that the service returns <code>ROLE_ADMIN</code> and treat all of authorization as tested: URL matchers, HTTP methods, SecurityFilterChain, and resource data can all cause other failures. Also test real endpoints via MockMvc or HTTP integration.

Testing nonexistent accounts is also useful: <code>loadUserByUsername</code> must reject instead of returning a default account with granted roles. When introducing a new permission, update both mapping tests and HTTP tests in the same PR.

## 8. When to Grant a Role vs. When to Grant a Permission?

Granting a role like <code>ROLE_ADMIN</code> is useful for high-level policies, such as access to an admin section. Granting a permission like <code>report:export</code> is useful to express a business action independent of role names.

Suppose tomorrow a <code>SUPERVISOR</code> role is allowed to view and export reports without administering users. If the controller checked only <code>hasRole("ADMIN")</code> for report export, you would have to modify authorization code every time a new role appeared. If the controller uses <code>hasAuthority("report:export")</code>, the system only needs to grant that permission to the SUPERVISOR role through a controlled admin workflow, along with adding tests.

On the other hand, avoid creating hundreds of arbitrary permission strings named after UI screens. Design permission codes around stable actions and clear business objects, for example:

| Code | Meaning |
| --- | --- |
| <code>report:read</code> | Permitted to view reports within allowed scope |
| <code>report:export</code> | Permitted to export reports within allowed scope |
| <code>invoice:approve</code> | Permitted to approve invoices after passing business checks |
| <code>user:manage</code> | Permitted to perform user management actions within granted scope |

Authorities in <code>Authentication</code> express **action-type permissions**, not automatic permission over every record. For instance, <code>report:read</code> is only the prerequisite to invoke the report-viewing feature; the application must still check whether the user is allowed to view a specific report.

### Rules at the HTTP and Method Levels

With a mapped permission, you can check it at the web layer:

~~~java
.requestMatchers(HttpMethod.GET, "/reports")
.hasAuthority("report:read")
~~~

Or at the service layer via method security:

~~~java
@PreAuthorize("hasAuthority('report:export')")
public byte[] exportReport(long reportId) {
    return reportService.export(reportId);
}
~~~

The method security snippet above is **illustrative**, not a standalone Java class: it requires enabling <code>@EnableMethodSecurity</code>, a proper service bean, and per-record authorization checks inside the business logic. Method security is especially useful when a service is invoked across multiple endpoints/mechanisms, though do not assume a proxy method covers all internal calls (e.g., self-invocation bypasses the proxy under normal behavior).

## 9. Multi-Tenant Case: Never Elevate Scoped Permissions to Global Permissions

Suppose account <code>mai</code> has role <code>ADMIN</code> **only in tenant A**. If you naively map:

~~~java
new SimpleGrantedAuthority("ROLE_ADMIN");
~~~

and then apply <code>hasRole("ADMIN")</code> to all tenant URLs, you might accidentally allow Mai to exercise admin privileges on tenant B. Real business data typically has a scope dimension:

~~~text
account_id | tenant_id | role_code
-----------+-----------+----------
42         | A         | ADMIN
42         | B         | VIEWER
~~~

One clear design approach separates:

1. **General authority:** which functional capability groups the account has in the application, implying no access across all tenants.
2. **Per-object authorization:** for each <code>tenantId</code>/<code>reportId</code>, check membership, role within the tenant, ownership, and record status against an authoritative data source at the time needed.

Example business check to perform:

~~~text
User 42 calls GET /tenants/B/reports/900
    -> request authenticated?
    -> report 900 actually belongs to tenant B?
    -> user 42 has active membership in tenant B?
    -> role in tenant B has report:read?
    -> resource 900 has additional owner/status constraints?
    -> only allow when every condition passes
~~~

Never directly trust a tenant ID in a URL, header, or self-declared user claim to grant permissions. In particular, do not rely solely on <code>hasAuthority("TENANT_A_ADMIN")</code> while forgetting to verify the tenant on the resource fetched from the database. A system can use tenant-namespaced authorities or a dedicated authorization service; the core point is that **permissions and scope must be explicitly bound and checked on the actual target object**.

### A General Rule

**RBAC** (role-based access control) fits defining action groups; **ABAC** or object/caller attribute checks fit conditions like tenant, owner, document status, approval limits, and department relations. Both can be combined; <code>GrantedAuthority</code> does not replace all business checks.

## 10. Controlling Authority Lifecycles and Runtime Updates

Role/permission data changes over time: staff transfer departments, permissions are revoked, accounts are locked, or organizational policies shift. Answer three questions accurately:

**When are authorities loaded?** In the HTTP Basic pattern, account/authorities are loaded when authentication runs per request (subject to cache/configuration). With form login, <code>SecurityContext</code> may be kept in HttpSession; with JWT, authorities may originate from previously issued claims.

**When do authority changes take effect?** Not automatically on the next request across all models. A live session may keep an old snapshot; a JWT may remain valid until expiration; caches have their own TTLs. Sensitive permissions need revocation mechanisms or current-state server checks.

**Who may modify permissions?** Only authenticated, authorized administration workflows with audit trails and change controls. Writing to <code>app_account_role</code> and <code>app_role_permission</code> is a high-privilege operation; never let a self-service endpoint update roles from user payloads.

| Authentication mechanism | Common authority source | Considerations on permission revocation |
| --- | --- | --- |
| HTTP Basic + UserDetailsService | Account/role/permission loaded at authentication | User cache, DB cost, and reload timing |
| Form login + HttpSession | Authorities stored in authentication/session | Active sessions, re-authentication, invalidate/refresh |
| JWT resource server | Verified claims converted to authorities | Token lifetime, refresh, revoke/introspection if applicable |
| Opaque token introspection | Information provided by introspection server | Cache/introspection freshness and revocation |
| Custom authentication | Project-designed converter/provider | Must explicitly test source, freshness, and tenant context |

Never update a session's authorities by editing the database directly and assuming Spring Security will auto-sync. You need a tested freshness, revocation, and caching strategy.

## 11. Mapping in OAuth2/JWT Differs from UserDetailsService

When a Spring Security application acts as an OAuth2 resource server, tokens may carry scopes such as <code>reports.read</code>. Spring Security normally converts scopes into authority strings prefixed with <code>SCOPE_</code>, e.g. <code>SCOPE_reports.read</code> via the default converter. This **differs** from the lesson's database creating <code>report:read</code> and <code>ROLE_ANALYST</code>.

If the authorization policy uses:

~~~java
.hasAuthority("report:read")
~~~

then authority <code>SCOPE_reports.read</code> will not automatically match. Choose a matching convention for both the authority source and rule configuration, or write a trusted converter to normalize them. With JWTs, never trust a claim just because the JSON is readable; first verify issuer, audience, signature, expiration, and token conditions per the system's authentication configuration.

Likewise, never pull an arbitrary <code>roles</code> field from a request body or header and pass it straight into <code>Authentication</code>. Clearly distinguish client-asserted data from verified claims and authorities from server-managed business stores.

## 12. Consistency, Performance, and Safety of the Mapper

A well-operated mapper should satisfy:

- **Stable codes:** roles/permissions use enums or a governed registry, with documented meanings and migrations on renames.
- **Fail closed:** nonexistent accounts, disabled accounts, and invalid roles/permissions must never default to granting access. Distinguish data errors (needing alerts) from insufficient permissions (business rules).
- **Deduplication:** a permission granted by multiple roles should not appear repeatedly; use a <code>Set</code> when building authorities.
- **Trusted source:** authorities are derived from data verified by the server/identity provider, not client-filled fields.
- **Transaction boundaries:** if role and permission edits must remain consistent, wrap data updates in transactions; consider snapshots or appropriate transactions when reading multiple tables under high load.
- **Performance:** avoid N+1 queries per role; fetch permissions via joins in one pass as shown, add indexes on account/role keys, and cache with revocation policies if needed.
- **No data leaks:** never log password hashes, session IDs, access tokens, or sensitive permission lists to public outputs.
- **Least privilege:** never grant all permissions on missing codes or DB connection failures; never use <code>permitAll</code> to "fix" mapper bugs.
- **Boundary testing:** unknown roles, disabled accounts, zero roles, multiple roles sharing a permission, wrong tenant, revoked permissions, and undeclared paths.

Illustration of handling an account with multiple roles:

~~~text
account roles = [ANALYST, ADMIN]
role permissions:
    ANALYST -> report:read
    ADMIN   -> report:read, report:export

Unique GrantedAuthority:
    ROLE_ANALYST
    ROLE_ADMIN
    report:read
    report:export
~~~

There is no inherent "ROLE_ADMIN is stronger than ROLE_ANALYST" inside <code>SimpleGrantedAuthority</code> merely from the name. They are just strings; role inheritance or "allowed if holding any of these authorities" logic is defined intentionally by policies or a role hierarchy.

## 13. Common Errors and How to Diagnose Them

| Symptom / Error | Possible Cause | How to Check |
| --- | --- | --- |
| User has ADMIN code yet <code>hasRole("ADMIN")</code> returns 403 | Mapper produced <code>ADMIN</code> instead of <code>ROLE_ADMIN</code> | Inspect exact <code>Authentication.getAuthorities()</code> and prefix |
| Account has report permission yet <code>hasAuthority("report:read")</code> denies | Permission code mismatch or missing join | Check role–permission table and UserDetails data |
| Newly locked user can still use an old session | Session/token/cache still holds old authentication | Check revoke/invalidate strategy and TTL |
| Tenant A admin can view tenant B | Flattened tenant role into global authority | Enforce membership and ownership per resource |
| Multiple roles produce duplicate permissions | Join query returns duplicate rows | Use SELECT DISTINCT or a Set |
| New role does not work | Registry/mapper does not yet recognize new code | Migrations, code rollout, and new permission tests |
| DB data error ends up granting default access | Mapper fallback too permissive | Fail closed and alert on data errors |
| Every route becomes 200 after debugging | Accidentally switched to permitAll | Review SecurityFilterChain and integration tests |
| HTTP 401 instead of 403 | Credentials failed authentication or account disabled | Distinguish failed authentication from missing authority |
| Admin sees 403 despite having authority | URL/method rule or another filter chain matched | Test real requests and check which chain is selected |
| Mapper test passes yet API still leaks | Only tested UserDetails, not HTTP behavior | Add MockMvc tests with anonymous/wrong role/other paths |

**Distinguishing 401 and 403:** HTTP Basic usually returns 401 when unauthenticated or with invalid credentials; an authenticated user lacking an authority usually gets 403. However, security entry points, exception handlers, and CSRF mechanisms can alter the outcome; test the actual app rather than making absolute inferences from status codes alone.

## 14. Checklist Before Bringing Authority Mapping to a Real App

1. Define business roles, permissions, and how scopes (tenant, unit, resource) are represented in the schema.
2. Constrain data with foreign keys/unique constraints; govern accepted permission codes and audit grant operations.
3. Load user/account status/password hashes from a proper authoritative source; verify status and credentials via the authentication provider.
4. Map roles to <code>ROLE_...</code> if using <code>hasRole</code>, and map permissions to exact codes for <code>hasAuthority</code>. Never take authorities from untrusted client input.
5. Deduplicate and reject unknown codes; never infer global access from scoped permissions.
6. Define freshness and revocation for sessions, caches, and tokens, especially when critical permissions change.
7. Place authorization rules at URL or service layers as needed; additionally check ownership/tenant inside business logic.
8. Test mapping directly, test requests with/without authorities, disabled accounts, multiple roles, different tenants, revoked permissions, and new routes.
9. Observe logs safely when debugging: logging authority names in controlled dev environments is fine, never log passwords, tokens, or sensitive account details.
10. Verify policies and endpoint surfaces in the real deployment environment; a mapper unit test cannot replace an integration test of Spring's SecurityFilterChain.

## 15. Self-Check Questions

**Question 1:** Database stores role <code>ADMIN</code>, code creates <code>SimpleGrantedAuthority("ADMIN")</code>, yet the URL uses <code>hasRole("ADMIN")</code>. Why does it return 403?  
**Answer:** Under the default prefix, <code>hasRole("ADMIN")</code> searches for <code>ROLE_ADMIN</code>. Map the role to the proper authority or redesign the rule consistently.

**Question 2:** A user has two roles that both grant <code>report:read</code>. Are two <code>report:read</code> GrantedAuthority entries needed?  
**Answer:** No. One unique authority is enough; use a Set to deduplicate and avoid redundant data.

**Question 3:** A DISABLED account still has the ADMIN role in the database. Should Spring Security allow login?  
**Answer:** No. UserDetails must reflect the disabled state and the authentication provider must reject login.

**Question 4:** A user has <code>report:read</code>; are they allowed to view all reports of all tenants?  
**Answer:** Not by default. The authority is only one condition; tenant membership and per-report permissions must still be checked.

**Question 5:** After deleting the ADMIN role in the database, do all existing sessions/JWTs immediately lose the old authority?  
**Answer:** There is no such guarantee. You need update, invalidation, or live-authority check mechanisms depending on the system and session/token/cache lifetimes.

**Key takeaway:** <code>GrantedAuthority</code> is the **permission format consumed by Spring Security**, not the original business decision source. Design mappings with trusted sources, stable code conventions, account status checks, and tenant scoping; then verify with both UserDetails tests and HTTP/method authorization tests.
