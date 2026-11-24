# Looking Up or Deleting Sessions via the `sessions` Endpoint with Suitable Spring Session

## 1. Understanding Sessions and the Endpoint's Management Scope

An HTTP session stores server-side state across multiple requests from a browser or device. For example, a session can hold login context, UI preferences, or temporary user data. A session ID helps the server find the right session; one username can be associated with multiple distinct sessions.

Spring Session routes session storage and lookup through a managed repository (session repository), such as JDBC or Redis. Spring Boot Actuator's built-in `sessions` endpoint uses this repository to inspect information and delete a session by ID.

~~~text
Alice on browser A → session A
Alice on browser B → session B
                                  ↓
                   Spring Session session repository
                                  ↑
             Actuator: look up or delete within supported scope
~~~

Three concepts to distinguish:

| Concept | Meaning |
| --- | --- |
| Username/principal name | Identity used to look up indexed sessions |
| Session ID | Identifier of one specific session |
| Session cookie | Information sent by the browser so the server identifies the session per app config |

**Deleting session A does not automatically delete session B**, even though both belong to Alice. Similarly, a cookie still sitting in the browser does not mean the corresponding session record still exists in the store.

The management endpoint is not a login API, does not create a session for the passed username, and has no built-in "delete all sessions of all users" operation.

This article focuses on **Spring Boot 3.3.x, Servlet, and Spring Session JDBC**. The runnable example uses Boot **3.3.0**, Spring Session **3.3.0**, H2 **2.2.224**, and Java **17 or higher**.

## 2. What Does "Using Suitable Spring Session" Require?

### 2.1. Plain HttpSession Is Not Enough

A Servlet application can use an `HttpSession` managed by Tomcat without using a Spring Session repository. Simply adding `spring-boot-starter-actuator` and exposing `sessions` does not turn all container sessions into data managed by the endpoint.

In Boot 3.3's Servlet configuration, the endpoint requires a Spring Session `SessionRepository`. Sessions to be observed must actually be stored through a repository compatible with the application. Spring Session provides an integration filter/layer so `HttpSession` usage goes through that storage mechanism.

Boot auto-configures supported Spring Session repositories; you do not need to add `@Enable*HttpSession` annotations just to repeat configuration already managed by Boot. Source: [Spring Session in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html).

### 2.2. Reading by ID and Searching by Username Have Different Requirements

In Boot 3.3, `SessionsEndpoint` accepts two capabilities:

| Repository Capability | Operations Using That Capability |
| --- | --- |
| `SessionRepository` | `findById`, `deleteById` |
| `FindByIndexNameSessionRepository` | Finding sessions by principal name index |

A repository that supports reading/deleting by ID does not necessarily support searching by username. Do not conclude "the endpoint works" means all of its operations have corresponding data and capabilities.

For example:

- `JdbcIndexedSessionRepository` supports both capabilities.
- `RedisSessionRepository` and `RedisIndexedSessionRepository` do not share the same indexing capability.
- `MapSessionRepository` used in experiments only supports basic operations and does not automatically provide principal queries.

The two-parameter constructor exists since Boot 3.3.0; the indexed repository parameter may be omitted (`null`). The example below directly verifies this difference. Source: [Boot 3.3 SessionsEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/session/SessionsEndpoint.html).

### 2.3. Username Must Be Written to the Right Index

Searching by username uses `findByPrincipalName(username)`, not scanning every attribute to guess an identity.

A custom attribute named `"username"` does not automatically become the principal index. With compatible repositories, Spring Session has principal resolution mechanisms; Spring Security integration or an attribute keyed by `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME` can supply the value to index.

Verify the system's resolution mechanism and when sessions are persisted. Do not accept a username from a browser and treat it as an authenticated identity.

### 2.4. Servlet vs. Reactive Boundaries in the Exact Version

The examples in this article use Servlet's `SessionsEndpoint` and JDBC. Boot **3.3.0** auto-configuration code also includes a `ReactiveSessionsEndpoint` branch for `ReactiveSessionRepository`, with reactive indexed lookup supplied separately when available.

The endpoint overview table in Boot 3.3 docs describes Servlet requirements, yet 3.3.0 code already has the reactive branch too. Therefore, when evaluating a WebFlux application, check the exact code and repository type of the version in use instead of copying the article's JDBC/Servlet config verbatim. You can inspect [SessionsEndpointAutoConfiguration at tag v3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/session/SessionsEndpointAutoConfiguration.java) directly.

## 3. Configuring a Servlet Web Application Using JDBC

The following Gradle snippet fits into an existing Spring Boot 3.3 project with version management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.session:spring-session-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

This is a lab configuration for an existing Spring Boot application, not a standalone Gradle project.

Example `application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  datasource:
    url: jdbc:h2:mem:session_web_lab;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  session:
    timeout: 30m
    jdbc:
      initialize-schema: always

management:
  endpoint:
    sessions:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,sessions
~~~

`initialize-schema: always` here is for a fresh in-memory H2 lab. For long-lived managed databases, preparing Spring Session tables must follow that environment's schema management process.

The condition layers remain independent:

1. The application has the right Spring Session repository and needed tables/connections.
2. The endpoint is enabled.
3. The endpoint is exposed over HTTP.
4. The request is permitted through the security layer.

In Boot 3.3, only `health` is exposed over HTTP by default; `exclude` takes precedence over `include`. Source: [Enabling, exposing, and securing Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

If using Redis and username lookup is needed, choose the matching indexing capability; Boot configuration can use `spring.session.redis.repository-type=indexed`. Specifying Redis as storage does not automatically prove the active repository supports principal queries. See [selecting Spring Session's indexed Redis repository](https://docs.spring.io/spring-session/reference/3.0/configuration/redis.html).

## 4. HTTP Operations to Use

The paths below assume port `8080`, base path `/actuator`, no additional context path, and authorized requests.

| Request | Result/Scope |
| --- | --- |
| `GET /actuator/sessions?username=alice` | List of sessions indexed for Alice |
| `GET /actuator/sessions/{sessionId}` | Metadata for one session |
| `DELETE /actuator/sessions/{sessionId}` | Deletes that specific session ID from the repository |

### 4.1. Finding Sessions for a Username

Use URL encoding for the search value:

~~~shell
curl -i -G --data-urlencode "username=alice" "http://localhost:8080/actuator/sessions"
~~~

On Windows PowerShell where `curl` is an alias, use `curl.exe` to invoke the real curl tool.

Example response shape, with illustrative ID and timestamps:

~~~json
{
  "sessions": [
    {
      "id": "60000000-0000-4000-8000-000000000001",
      "attributeNames": ["theme"],
      "creationTime": "2026-11-06T02:00:00Z",
      "lastAccessedTime": "2026-11-06T02:10:00Z",
      "maxInactiveInterval": 1800,
      "expired": false
    }
  ]
}
~~~

Omitting `username` does not mean "list all sessions." It is a required parameter of the lookup-by-username operation.

A username with no matches in an indexed repository normally returns an empty list `{"sessions":[]}`. That differs from the endpoint lacking an indexed lookup capability.

### 4.2. Looking Up a Specific ID

Example using the illustrative ID above:

~~~shell
curl -i "http://localhost:8080/actuator/sessions/60000000-0000-4000-8000-000000000001"
~~~

A successful result is a single session object without an outer `sessions` wrapper.

| Field | How to Read |
| --- | --- |
| `id` | Session ID |
| `attributeNames` | Attribute names, not their values |
| `creationTime` | Creation timestamp |
| `lastAccessedTime` | Most recent access timestamp recorded by the session |
| `maxInactiveInterval` | Maximum inactive interval, in seconds |
| `expired` | Result of expiration check on the returned session |

Do not read `maxInactiveInterval=1800` as "only 1800 seconds remaining." It is the allowed inactivity timeout; remaining time depends on last access time and observation time.

`attributeNames` can indicate the presence of security context or UI preferences, but the API does not return the full values of those attributes. The HTTP contract is documented in [Actuator Sessions API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sessions.html).

### 4.3. Deleting the Selected Session

~~~shell
curl -i -X DELETE "http://localhost:8080/actuator/sessions/60000000-0000-4000-8000-000000000001"
~~~

The endpoint calls the repository's `deleteById(sessionId)`, without turning it into "delete all sessions of the username associated with that ID."

In Boot 3.3, the delete operation returns `void`; on normal completion without error, the HTTP response is **204 No Content**. There is no JSON body reporting the count of deleted sessions.

## 5. Distinguishing Empty, Unsupported, and Nonexistent Cases

| Scenario in Boot 3.3 | Typical Result After Security/Routing |
| --- | --- |
| Indexed repository, sessions found for username | `200`, non-empty array |
| Indexed repository, username has no matching sessions | `200`, empty array |
| Required `username` parameter missing | `400` |
| No indexed repository for username lookup | Read operation returns `null`, mapped to `404` |
| GET for an ID no longer returned by the repository | `404` |
| Normal DELETE handling | `204`, even when repository does not find the ID and performs a no-op |

Crucial last point: the `SessionRepository.deleteById` contract allows doing nothing if the session is not found. **204 does not prove the ID existed before the request.** To verify after deletion, look up the ID again and check the result at that moment.

HTTP status codes can also be produced by security layers, reverse proxies, or wrong paths. A single `404` alone is not enough to conclude the cause was session deletion.

In Boot 3.3's implementation, GET by ID calls `findById` and builds the descriptor; the operation does not update `lastAccessedTime` or re-save the target session. Nor should you expect the endpoint to list all expired sessions: repositories may exclude expired sessions from search results.

## 6. Java Experiment with a Real JDBC Repository on In-Memory H2

The experiment uses `SessionsEndpoint` itself and `JdbcIndexedSessionRepository`. It does not start an HTTP server, does not log in real users, and does not affect any external session store.

Goals:

1. Save two sessions with the same principal `alice`.
2. Search by username to see both.
3. Delete one ID and confirm the remaining ID still exists.
4. Delete repeatedly to see why delete success does not prove the session existed.
5. Compare against a non-indexed repository.

### 6.1. Dependencies

Create `pom.xml` in a separate lab directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>sessions-endpoint-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Maven is used to build the classpath; the next step compiles directly with `javac`. The Spring Session JDBC dependency brings in the required Spring libraries.

### 6.2. Complete Program

Place `SessionsEndpointDemo.java` alongside `pom.xml`:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.boot.actuate.session.SessionsEndpoint;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.MapSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;
import org.springframework.transaction.support.TransactionTemplate;

public class SessionsEndpointDemo {
    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:sessions_endpoint_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");
        new ResourceDatabasePopulator(new ClassPathResource(
                "org/springframework/session/jdbc/schema-h2.sql"))
                .execute(dataSource);

        var transactions = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));
        var repository = new JdbcIndexedSessionRepository(
                new JdbcTemplate(dataSource), transactions);
        var endpoint = new SessionsEndpoint(repository, repository);

        String firstId = saveSession(repository, "alice");
        String secondId = saveSession(repository, "alice");
        System.out.println("alice before="
                + endpoint.sessionsForUsername("alice").getSessions().size());
        System.out.println("attribute name visible="
                + endpoint.getSession(firstId).getAttributeNames().contains("theme"));

        endpoint.deleteSession(firstId);
        System.out.println("deleted session absent="
                + (endpoint.getSession(firstId) == null));
        System.out.println("alice after="
                + endpoint.sessionsForUsername("alice").getSessions().size());
        System.out.println("other session remains="
                + (endpoint.getSession(secondId) != null));
        endpoint.deleteSession(firstId);
        System.out.println("repeat delete completed=true");
        System.out.println("unknown user sessions="
                + endpoint.sessionsForUsername("nobody").getSessions().size());

        var plainRepository = new MapSessionRepository(new ConcurrentHashMap<>());
        String plainId = saveSession(plainRepository, "alice");
        var plainEndpoint = new SessionsEndpoint(plainRepository, null);
        System.out.println("id lookup without index="
                + (plainEndpoint.getSession(plainId) != null));
        System.out.println("username lookup without index available="
                + (plainEndpoint.sessionsForUsername("alice") != null));
    }

    private static <S extends Session> String saveSession(
            SessionRepository<S> repository, String username) {
        S session = repository.createSession();
        session.setAttribute(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                username);
        session.setAttribute("theme", "dark");
        repository.save(session);
        return session.getId();
    }
}
~~~

The `schema-h2.sql` script is inside the Spring Session JDBC library and creates the tables needed for the lab. There is no need to copy table definitions into another data model. The JDBC repository provides both ID-based storage and principal-based lookup. Source: [JdbcIndexedSessionRepository 3.3.0 API](https://docs.spring.io/spring-session/docs/3.3.0/api/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html).

`saveSession` uses type parameter `S extends Session` to save the exact session type each repository creates. Setting principal `alice` here generates server-side experimental data, **not an authentication mechanism**.

### 6.3. Compiling and Running

Requires JDK 17+ and Maven; downloading dependencies the first time requires Maven repository connectivity.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$sessionsClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$sessionsClasspath" SessionsEndpointDemo.java
java -cp ".;$sessionsClasspath" SessionsEndpointDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
sessions_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$sessions_classpath" SessionsEndpointDemo.java
java -cp ".:$sessions_classpath" SessionsEndpointDemo
~~~

Stdout:

~~~text
alice before=2
attribute name visible=true
deleted session absent=true
alice after=1
other session remains=true
repeat delete completed=true
unknown user sessions=0
id lookup without index=true
username lookup without index available=false
~~~

Conclusions proven by the run:

- Two sessions sharing a username are not a single session.
- Deleting `firstId` makes that session no longer found, while `secondId` remains readable.
- Deleting the same ID again completes normally.
- A username with no matches yields an empty list in an indexed JDBC repository.
- `MapSessionRepository` still supports reading by ID; passing `null` for the indexed repository makes username lookup return no result descriptor.

The program avoids printing random IDs or specific timestamps so stdout stays deterministic. The lab's H2 lives in memory and ends its lifecycle when the process exits.

## 7. Practicing Session Lifecycle over HTTP

To generate test data on the **lab web application** configured in section 3, you can add the following illustrative controller:

~~~java
import java.util.Map;
import jakarta.servlet.http.HttpSession;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionLabController {
    @GetMapping("/lab/touch")
    public Map<String, String> touch(HttpSession session) {
        session.setAttribute(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                "alice");
        session.setAttribute("theme", "dark");
        return Map.of("sessionId", session.getId());
    }
}
~~~

This is a lab data-seeding controller with a fixed principal, not for authentication or production app APIs. Place the class in a package scanned by Spring Boot.

PowerShell example, assuming the local lab requires no authentication:

~~~powershell
$lab = Invoke-RestMethod -Uri "http://localhost:8080/lab/touch" -SessionVariable labCookies
$sessionId = $lab.sessionId
$sessionUrl = "http://localhost:8080/actuator/sessions/" + [uri]::EscapeDataString($sessionId)

Invoke-RestMethod -Uri "http://localhost:8080/actuator/sessions?username=alice"
Invoke-RestMethod -Uri $sessionUrl
Invoke-WebRequest -Method Delete -Uri $sessionUrl
~~~

After DELETE, calling GET on `$sessionUrl` normally returns `404`. In PowerShell, HTTP error responses may be thrown as exceptions; inspect the status code rather than treating every exception as a connection failure.

You can resend an application request using the old cookie:

~~~powershell
$next = Invoke-RestMethod -Uri "http://localhost:8080/lab/touch" -WebSession $labCookies
$next.sessionId -ne $sessionId
~~~

In this lab, the controller always requests an `HttpSession`, so when the old session is no longer valid, a new session is created and a new ID is returned. This is not the old session "coming back to life"; nor did DELETE prevent the browser from creating any new sessions in the future.

In an application with Spring Security, a request after losing its login session may require re-authentication, redirect, or return an error per security config. Do not extrapolate the behavior of an unauthenticated lab controller to claim all applications respond the same way.

## 8. Deletion Scope and Limitations to Understand

### 8.1. One ID Differs from All of a User's Sessions

If Alice is logged in on three devices, deleting one session ID does not log out the other two devices. To handle multiple sessions, the management workflow must search and select the matching IDs and process each ID individually.

Even if all of Alice's sessions are found initially, a new session may be created right after lookup. The "find then delete each ID" sequence does not automatically become an atomic operation blocking all new sessions for the account.

### 8.2. Repository and Deployment Topology Determine What Is Affected

If application instances share the same JDBC or Redis store and the same session scope configuration, deletion affects the record in the shared store. If each process uses an independent store, a request to one process does not control another process's store.

Check the datasource, table names, namespaces, and actual configuration. Looking only at the `/actuator/sessions` URL does not tell you which system or which instances the operation affects.

### 8.3. Deleting a Session Does Not Revoke Every Credential Type

A session is server-side state. Deleting it does not implicitly revoke JWTs, refresh tokens, remember-me cookies, or sessions at an external identity provider.

A completely stateless JWT system may not create login sessions for this endpoint to find. An empty list in that case does not prove the user is unauthenticated.

### 8.4. Deletion Does Not Roll Back In-Flight Requests

A request that already read the session or security context before the record was deleted may already be proceeding through the processing pipeline. The endpoint does not promise to cancel in-flight requests or roll back business transactions.

When emergency access revocation is needed, also check the application's authorization checks and credential lifecycle.

### 8.5. Session ID in Responses and Cookie Values Must Be Distinguished

Use the ID returned by the endpoint or application for ID-based paths. Do not assume the entire raw cookie value always equals that exact ID string, as cookie representation depends on serializers/configuration.

Also do not record real session IDs in public guides or use them as proof of identity. In operations, treat IDs as access-controlled data.

## 9. Securing Management Operations and Diagnosing Errors

The `username=alice` parameter is a search condition, not a check on whether the caller is authorized to view Alice. Lookup and deletion permissions must be enforced by the management security layer.

If building an API for users to manage their own sessions, that API must resolve the authenticated principal and verify session ownership server-side. Do not expose the management endpoint directly to end-user UIs allowing arbitrary username/ID substitution.

With Spring Security, GET being allowed does not guarantee DELETE is allowed. Beyond authorization, default CSRF protection can block DELETE and return `403`; having valid credentials alone is not enough to assume all write requests will be accepted. Do not disable CSRF application-wide just to make lab commands run. Source: [Actuator security and CSRF](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

| Symptom | What to Check |
| --- | --- |
| Endpoint does not appear | Actuator, Spring Session store, auto-configuration conditions, endpoint enabled/exposed, port/base path |
| GET username returns `400` | Did you pass the required parameter and URL-encode its value |
| ID lookup works, username search does not | Does the repository provide principal indexing capability |
| Returns empty array despite knowing someone is logged in | Right principal name, right store, right index, persistence timing, and authentication type |
| GET by ID returns `404` | Wrong ID, expired, already deleted, different store, or wrong path |
| DELETE returns `403` | Authorization and CSRF; do not blame the session store yet |
| DELETE `204`, user still has access | Another session, new session created, remember-me/JWT, or already-authenticated in-flight request |
| Old cookie still present in browser | Deleting server-side record does not remotely edit cookies on devices |

## 10. Choosing the Right Evidence When Handling an Anomalous Session

Suppose Alice reports an unfamiliar device holds an active login session.

1. Identify the exact environment, session store, and principal name the system uses.
2. With appropriate management permissions, look up Alice's sessions.
3. Cross-check available info to pick the right ID; basic metadata does not implicitly contain IP, device type, or full activity history.
4. Delete the selected ID and re-check lookup for that ID.
5. Verify subsequent access behavior according to the application's authentication mechanism; do not treat `204` as proof that all of Alice's session/token types were invalidated.

**Self-check exercises:**

- In the experiment, why did deleting one ID drop Alice's session count from 2 to 1?
- Why does a username with no matches in an indexed repository differ from querying a username on a non-indexed repository?
- If deleting the same ID twice both complete, what does `204` tell you and what does it not tell you?
- Why can a browser obtain a new ID after its old session was deleted?
- A stateless JWT application returns an empty session list: what evidence is still missing before concluding the user is logged out?

When reporting results, specify the **selected session ID, managing repository, indexing capability, and observation timestamp** so others can verify the operation's scope.
