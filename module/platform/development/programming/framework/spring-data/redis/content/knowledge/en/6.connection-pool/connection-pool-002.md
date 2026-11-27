# Password or ACL Username/Password Authentication in Spring Data Redis

## 1. What Problem Does Redis Authentication Solve?

A Spring Boot application often connects to Redis over the network to read caches, update counters, store short-lived data, or work with Redis data structures. If Redis requires authentication, the client must prove it is permitted to use the connection **before executing business commands**. When Redis uses ACL (Access Control List), the client also needs permissions for individual commands, keys, and sometimes Pub/Sub channels.

In Spring Data Redis, this responsibility belongs to **connection configuration**: the application passes credentials to the Redis client library, such as Lettuce, through Spring Boot or a developer-configured **RedisConnectionFactory**. Operations such as **StringRedisTemplate.opsForValue().get(...)** then use those established connections.

Two types of authentication must be distinguished:

- **Application end-user authentication**: for example, a customer logging into a website with an email and password.
- **Service-to-Redis authentication**: the Spring Boot application itself logging into Redis using a provisioned Redis account.

Redis does not automatically know which HTTP user is calling an API. A Spring Boot service typically uses one Redis identity for its connections, unless the architecture intentionally implements a different model.

Symptoms indicating authentication or authorization issues include **NOAUTH**, **WRONGPASS**, **NOPERM**, or Redis connection exceptions when the application starts up or executes commands.

## 2. Two Common Models: Default Password and ACL Username/Password

### 2.1. Single-Password Authentication: The Default User

In simple Redis tutorials, the server is configured with a single shared password. The client only sends the password without specifying a separate username:

~~~text
AUTH <password>
~~~

From Redis 6 onward, the **ACL** mechanism introduced the concept of users; password-only login is treated for compatibility as authenticating as the **default** user. Depending on server configuration, the default user's password can be set via the traditional **requirepass** directive or via ACLs.

Example server configuration for a test environment:

~~~conf
# A snippet of redis.conf configuration, not application.yml
requirepass REPLACE_WITH_A_STRONG_SECRET
~~~

This configures the **Redis Server** side. It differs from setting a password on the Spring Boot side. Setting **spring.data.redis.password** in the application does not automatically enable authentication on the Redis Server.

With the default-password model:

- Clients can send a password without specifying a username.
- Redis 6+ can also authenticate under the username **default** if that user is configured accordingly.
- Applications using the same password share the same Redis identity; it is difficult to restrict permissions per application by simply sharing one password.
- Having a password **does not mean** data transmitted over the network is encrypted.

### 2.2. Authentication with an ACL User

Redis 6 and later support creating **named users**, each with their own credentials and permissions. The username/password authentication syntax is:

~~~text
AUTH <username> <password>
~~~

Example separation of responsibilities:

| Redis User | Purpose | Desired Scope |
| --- | --- | --- |
| **spring_cache** | Application reading/writing cache | Commands and keys belonging to the cache namespace |
| **event_consumer** | Service reading Redis Streams | Permitted Stream commands and keys |
| **redis_admin** | Operator or operations system | Necessary ACL management, configuration, and diagnostics |

ACLs help organize access according to the **principle of least privilege**. You can restrict:

1. **Commands**: a user can run GET/SET but has no permission for CONFIG or FLUSHALL.
2. **Key patterns**: only allowed to access keys matching a pattern, such as **spring:cache:***.
3. **Pub/Sub channels**: when an application uses Pub/Sub, channel permissions are managed separately from keys.

Not every Redis deployment allows applications to create ACL users themselves. With a managed Redis service, operators may have to create users via the provider's admin console or API.

### 2.3. Comparison Table

| Characteristic | Default User Password | ACL Username/Password |
| --- | --- | --- |
| What does the client send? | Password; username usually omitted | Username and password |
| AUTH syntax | AUTH password | AUTH username password |
| Redis identity | Usually **default** | Named user, e.g. **spring_cache** |
| Access permissions | Permissions tied to the default user | Can be granted individually per user |
| Common use cases | Simple environments, legacy setups | Multiple services or clear permission separation |
| Changing permissions | Changing default permissions affects all clients using it | Can adjust an individual user |

Key point: Redis does not have two completely separate authentication systems in modern versions; **the simple password approach is typically a compatibility path for the ACL default user**.

## 3. Authentication Flow in a Spring Boot Application

~~~mermaid
sequenceDiagram
    participant App as Spring Boot service
    participant Client as Lettuce / RedisConnectionFactory
    participant Redis as Redis Server
    App->>Client: Requests StringRedisTemplate operation
    Client->>Redis: Opens TCP or TLS connection
    Client->>Redis: AUTH or authenticated handshake step
    Redis-->>Client: Authentication succeeds or fails
    Client->>Redis: GET / SET per user permissions
    Redis-->>Client: Value or NOPERM
    Client-->>App: Returns result / exception
~~~

In practice, clients may use combined handshake or authentication commands depending on protocol and library versions; the diagram depicts the **meaning** of the process rather than requiring the library to always send a separate standalone AUTH command.

A **RedisConnectionFactory** knows how to create or provide connections. **RedisTemplate**, **StringRedisTemplate**, and other Redis access components use that factory. If connections are reused or borrowed from a pool, the application does not need to call AUTH manually in every business method.

**Important processing order:** the connection is authenticated first; only afterward does Redis check the user's permissions on each command and key. Therefore, **a successful login can still receive NOPERM**.

## 4. Configuring Spring Boot When Redis Only Requires a Password

With Spring Boot 3.x and the Spring Data Redis starter, add the Gradle dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Suppose the Redis Server has a password for the **default user**. Configuration in **application.yml**:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
~~~

The **REDIS_PASSWORD** environment variable must be supplied when the application starts. Do not write real passwords into configuration files committed to Git.

In this case, **no username is needed**. If you actively configure the **default** user on Redis and want to specify the username explicitly, Redis 6+ can accept the corresponding default/password pair as well. However, for legacy password-only configurations, omitting the username field is usually clearest.

Distinguish the fields:

- **host** and **port**: where Redis is listening.
- **password**: the secret for Redis to authenticate the client identity.
- **connect-timeout**: time limit for establishing the connection.
- **timeout**: time limit for executing commands according to client configuration.

Setting timeouts does not fix password errors. When Redis returns WRONGPASS, increasing timeouts or pool size does not make invalid credentials valid.

**Version note:** examples using the **spring.data.redis** configuration namespace are common in Spring Boot 3.x. Some older Spring Boot projects use **spring.redis**. When maintaining legacy projects, verify against the exact Spring Boot version in use.

## 5. Configuring Spring Boot with ACL Username/Password

Suppose Redis already has a user named **spring_cache** and a corresponding password. Application configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
~~~

At runtime, both variables need valid values:

~~~text
REDIS_USERNAME=spring_cache
REDIS_PASSWORD=<secret-of-user-spring_cache>
~~~

These are **examples of variable names**, not a recommendation to print passwords to a terminal or commit a file containing secrets. Provide variables through a secret management mechanism appropriate for your operating environment.

Once Spring Boot has auto-created the connection factory from the starter, code using Redis does not need to pass user and password manually:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CacheProbeService {

    private final StringRedisTemplate redis;

    public CacheProbeService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String roundTrip() {
        String key = "spring:cache:demo";
        redis.opsForValue().set(key, "connected", Duration.ofMinutes(1));
        return redis.opsForValue().get(key);
    }
}
~~~

With valid connection configuration and Redis permissions, **roundTrip()** returns **connected**. The data is stored with a 1-minute TTL. The method contains no AUTH command because the client already handled authentication at the connection layer.

If the user only has **GET** permission and lacks **SET** permission, the write step in roundTrip will fail with an authorization error. If the user is allowed to SET but is not allowed to touch keys with the **spring:cache:** prefix, Redis can also reject the command.

### When the Application Configures ConnectionFactory Manually

If a project does not rely on default auto-configuration or needs deep connection customization, you can create a **RedisStandaloneConfiguration**, set username/password, and pass it into **LettuceConnectionFactory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class CustomRedisConnectionConfiguration {

    @Bean
    RedisConnectionFactory redisConnectionFactory(
            @Value("${app.redis.host}") String host,
            @Value("${app.redis.port}") int port,
            @Value("${app.redis.username:}") String username,
            @Value("${app.redis.password}") String password) {

        RedisStandaloneConfiguration config =
                new RedisStandaloneConfiguration(host, port);

        if (username != null && !username.isBlank()) {
            config.setUsername(username);
        }
        config.setPassword(RedisPassword.of(password));

        return new LettuceConnectionFactory(config);
    }
}
~~~

The **app.redis.*** properties in the example belong to a custom namespace, for instance:

~~~yaml
app:
  redis:
    host: localhost
    port: 6379
    username: ${REDIS_USERNAME:}
    password: ${REDIS_PASSWORD}
~~~

Only create a custom factory when there is a clear reason. If an application defines its own factory while still expecting Spring Boot auto-configuration to manage every connection aspect as before, discrepancies can arise in timeouts, TLS, pooling, and other settings. This snippet illustrates **how to attach credentials to a connection factory**; if the system uses TLS or Redis Cluster/Sentinel, configure the client to match the actual topology.

## 6. Creating and Restricting an ACL User on Redis

To explain the server side, assume an administrator has logged into Redis with an identity that has ACL management permissions. In **redis-cli interactive mode** in a test environment, an example command is:

~~~text
ACL SETUSER spring_cache reset on >REPLACE_WITH_A_STRONG_SECRET ~spring:cache:* +get +set +del +exists +ttl +pttl +type +ping
~~~

Meaning of each part:

| Component | Explanation |
| --- | --- |
| **ACL SETUSER spring_cache** | Creates or updates the ACL user named spring_cache. |
| **reset** | Resets key permissions/rules to a restricted default state, avoiding accidentally retaining old privileges. |
| **on** | Enables the user so it can authenticate. |
| **>REPLACE_WITH_A_STRONG_SECRET** | Adds a password for the user. The **>** prefix is ACL syntax. |
| **~spring:cache:\*** | Allows accessing only keys matching this pattern. |
| **+get +set +del ...** | Grants each permitted Redis command individually. |

**Important note:** the **>** character in ACL syntax can be interpreted by a shell as output redirection if typed directly in an unescaped shell command. The example above is for the **interactive redis-cli** prompt, not a command to paste verbatim after **redis-cli** in an OS terminal. The ACL configuration command also contains a plaintext password in terminal input; for real environments, use your organization's or Redis service's secure secret/ACL provisioning mechanism.

This is an illustrative user for **GET, SET, DEL, EXISTS, TTL, PTTL, TYPE, PING** operations on keys prefixed with spring:cache:. That user is not automatically permitted to run HGETALL, CONFIG, FLUSHALL, or admin commands. If the application uses additional data structures, a pool needs extra initialization commands, or a cache manager needs to clear an entire cache region, grant the corresponding permissions according to actual needs.

For example, **RedisCacheManager** may use key prefixes like **cacheName::key** and **KEYS/SCAN** commands when performing certain bulk cache evictions. If the ACL only allows **spring:cache:*** and a few basic commands from the example, those flows can be denied. Determine the application's **actual key prefixes**, the commands it issues, and the appropriate permission level before granting access.

Redis ACLs manage permissions for **Redis commands/keys/channels**; they do not replace business-level authorization checks for individual HTTP users in the application.

### 6.1. Viewing ACL Configuration and Error Logs

With a privileged admin account, several useful commands include:

~~~text
ACL GETUSER spring_cache
ACL LIST
ACL LOG 10
~~~

- **ACL GETUSER** inspects a user's status and permissions.
- **ACL LIST** lists user definitions; output may contain sensitive configuration details, so restrict sharing.
- **ACL LOG 10** displays recent ACL-related denial events, useful for distinguishing missing command permissions from key permissions.

Redis also provides **ACL WHOAMI** to query the currently authenticated identity; whether it can be called depends on the user's permissions. Do not assume a restricted application account can read or modify the full ACL configuration.

### 6.2. Do Created Users Persist Across Restarts?

**ACL SETUSER** modifies the ACL state on the running Redis Server. Persistence depends on configuration:

- If Redis uses a properly configured **ACL file**, administrators can save changes to it via the corresponding ACL management mechanism, such as **ACL SAVE** when available.
- If users/ACLs are provisioned via **redis.conf**, configuration pipelines, or a managed service, update that configuration source in the supported way.
- Do not assume a one-off CLI user creation always persists across every restart or environment change.

In production, users and permissions should be managed through controlled operational workflows; application accounts normally **do not need ACL SETUSER permission**.

## 7. Testing Connections with redis-cli

Testing login via the CLI helps separate Redis Server issues from Spring Boot configuration issues.

### 7.1. Default User Password

From the OS terminal:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 --askpass
~~~

redis-cli will prompt interactively for the password. Once authenticated:

~~~text
PING
SET spring:cache:probe ok EX 60
GET spring:cache:probe
TTL spring:cache:probe
~~~

If the connection requires authentication and none is provided, Redis may return **NOAUTH Authentication required**. Do not use the **-a** command-line flag with real passwords in shared examples or scripts that can leak in history; **--askpass** avoids placing secrets on the command line.

### 7.2. ACL Username/Password

From the OS terminal:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 --user spring_cache --askpass
~~~

Enter the password of the **spring_cache** user when prompted by the CLI. Then test:

~~~text
PING
SET spring:cache:probe "hello" EX 60
GET spring:cache:probe
TYPE spring:cache:probe
TTL spring:cache:probe
~~~

With the example ACL in section 6, these commands fall within the granted scope. If you try accessing a key outside the namespace:

~~~text
GET another-service:private
~~~

Redis may return **NOPERM** because the user is not allowed to access that key. NOPERM does not mean the username/password is wrong; authentication may have succeeded while the ACL denied the operation.

In the interactive CLI, two forms also exist:

~~~text
AUTH <password>
AUTH <username> <password>
~~~

This is **illustrative syntax**; do not enter both lines or copy the **< >** brackets as literal values. Because typing a password in the interactive CLI can leave traces in history or logs, prefer **--askpass** when testing logins.

## 8. Securing Connections with TLS: Authentication Is Not Encryption

Passwords and ACLs decide **who is allowed access**. TLS protects **the transport** between Spring Boot and Redis when both ends support and properly configure it.

Not using TLS on an untrusted network leaves data and authentication credentials exposed on the wire. For a Redis Server offering a TLS endpoint, an example in Spring Boot 3.x is:

~~~yaml
spring:
  data:
    redis:
      host: redis.example.internal
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
~~~

The port above is illustrative only: a provider's TLS endpoint may use a different port. Enabling **ssl.enabled** in Spring does not automatically turn on TLS on the Redis Server. You need a TLS-capable server and proper trust/certificate configuration for the system.

Beyond TLS, apply network restrictions, least-privilege Redis ACLs, periodic secret rotation, and avoid exposing credentials via URLs, logs, or build files.

## 9. How Does Authentication Relate to Connection Pools?

In the **Lettuce** model commonly used with Spring Data Redis, many ordinary operations can share a single thread-safe native connection when configuration permits. Pooled connections are usually considered for operations or architectures that need dedicated connections, such as blocking operations, transactions, or specific optimization requirements.

Whether using a shared connection or multiple connections in a pool, **every new TCP/TLS connection to Redis must complete valid authentication** before executing commands. Permissions remain bound to the Redis identity authenticated on that connection.

Example Lettuce pool configuration when an application has a need and has added the appropriate pooling library:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.apache.commons:commons-pool2'
}
~~~

~~~yaml
spring:
  data:
    redis:
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      host: localhost
      port: 6379
      lettuce:
        pool:
          max-active: 8
          max-idle: 8
          min-idle: 0
          max-wait: 2s
~~~

These pool values are illustrative only, not default optimal parameters for every system. Enabling a pool is not strictly required to use Spring Data Redis; evaluate operation types, concurrency, and client behavior.

Some important consequences:

- Increasing **max-active** does not fix WRONGPASS or NOPERM errors.
- Revoking a user's permissions can cause operations on existing connections to fail, even though the application previously logged in successfully.
- When changing passwords, new connections must use the new secret; for pools or reused connections, you need a plan to reload configuration and reinitialize old connections as needed.
- If username/password are misconfigured across profiles, adding a pool only creates more connection failures using the same wrong credentials.

### 9.1. Zero-Downtime Password Rotation: Points to Plan Ahead

Depending on the ACL management mechanism, you can arrange a transition window accepting multiple valid secrets, update all services, and then revoke the old secret. Keep in mind:

1. Ensure the Redis Server accepts the new secret.
2. Update the secret for the application and running deployments.
3. Recreate or verify connections/pools to ensure new connections use the new secret.
4. Revoke the old secret after confirming applications and background tasks have switched to the new secret.

Do not change passwords abruptly in a multi-instance environment without knowing how each instance reloads configuration or credentials.

## 10. Distinguishing Authentication, Authorization, and Connectivity Errors

| Error / Symptom | Common Meaning | Next Check |
| --- | --- | --- |
| **NOAUTH Authentication required** | Client has not authenticated, but Redis requires it | Check whether username/password are passed; inspect connection factory and active profile. |
| **WRONGPASS invalid username-password pair or user is disabled** | Credentials mismatch or ACL user is disabled | Verify exact username, secret, ACL status, and Redis endpoint. |
| **NOPERM this user has no permissions...** | Authenticated, but lacks permission for the command, key, or channel | Inspect exact command, key prefix, ACL rules; use ACL LOG with admin rights. |
| **Connection refused** | Cannot establish socket to host/port | Check whether Redis is running, DNS, port, firewall, container network. |
| **Timeout** | Connection setup or command did not finish in time | Check network, Redis load, pool, TLS, timeout configuration. |
| **TLS/SSL handshake failure** | Protocol mismatch or untrusted certificate | Check TLS endpoint, port, truststore, and SSL configuration on both sides. |
| **AUTH failed when Redis does not require a password** | Client sent AUTH, but server has no matching credentials configured | Check server configuration and remove unnecessary credentials in that environment. |

There is no single error message across all Redis client versions. In Spring Boot, Redis errors are usually wrapped in Spring Data Redis or Lettuce exceptions; read the **root cause** to locate the true issue.

### Ordered Diagnostic Process

**Step 1 — Check the endpoint.** Verify host, port, standalone/Sentinel/Cluster topology, and TLS usage. An app connecting to the wrong Redis instance can receive WRONGPASS even when the secret is right for the intended environment.

**Step 2 — Check the credential type.** Does the environment use a default password or a named ACL user? If using ACL, both username and password must match. Some managed Redis services require configuring users in a specific way.

**Step 3 — Test with redis-cli.** Use **--askpass** and **--user** as needed. If the CLI cannot log in to the same endpoint, resolve the Redis/credential side first.

**Step 4 — Check permissions on the exact key and command.** If the CLI logs in successfully but GET/SET gets NOPERM, use admin privileges to inspect the ACL user and denied events. Do not grant **+@all** just to make the error disappear.

**Step 5 — Check Spring configuration.** Review active profiles, environment variables, secret injection, application.yml files, custom factories, and Redis URLs in use. Do not log password values for debugging.

**Step 6 — Check existing connections and pools.** If secrets were recently rotated, verify whether the application reloaded configuration, reconnected, or rebuilt the pool.

## 11. Common Misconceptions

**“Just adding a password in Spring Boot makes Redis secure?”** No. The server also needs authentication configured, network restrictions, appropriate TLS, and proper access rules. Client-side credential configuration only tells the client which secret to use.

**“If using ACLs, should every service still use the default user?”** Not necessarily. ACLs are valuable when each service has a user with a clear permission scope. Sharing the default user across all services makes revoking or restricting individual permissions difficult.

**“If connecting succeeds, can GET/SET always run?”** No. An ACL can allow a user to log in while prohibiting specific commands or keys.

**“Is a Redis username like a website login account?”** No. An ACL username represents the client/service connecting to Redis, not an end user's identity in the system.

**“Will configuring a large pool prevent Redis errors?”** No. Pooling relates to connection management and reuse; authentication, ACLs, TLS, performance, and reliability are separate concerns that must be addressed by root cause.

**“Is enabling TLS enough for authorization?”** No. TLS protects the connection; ACLs control what a Redis user can do. Use both together according to infrastructure requirements.

**“Is an ACL user with +get +set enough for all of Spring Cache?”** Not necessarily. Account for delete commands, TTLs, prefixes, serialization, cache management operations, and initialization commands issued by the Redis client.

## 12. End-to-End Walkthrough Example

Suppose a Spring Boot service needs to cache product names in Redis, and Redis already has an ACL user:

~~~text
Username: spring_cache
Allowed keys: spring:cache:*
Allowed commands: GET, SET, DEL, EXISTS, TTL, PTTL, TYPE, PING
~~~

The application has the configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
~~~

The service writes to the cache:

~~~java
redis.opsForValue().set(
    "spring:cache:product:42",
    "Spring Data Redis",
    Duration.ofSeconds(90));
~~~

You can log in to Redis as that user and verify:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 --user spring_cache --askpass
~~~

Once inside redis-cli:

~~~text
PING
TYPE spring:cache:product:42
GET spring:cache:product:42
TTL spring:cache:product:42
~~~

You should observe that the key is of type **string**, its value is **Spring Data Redis**, and the TTL counts down from roughly 90 seconds. If the service deletes the key (such as when updating a product), **EXISTS spring:cache:product:42** returns 0. If you enter a key outside the granted namespace, Redis may return NOPERM.

The same model applies to other Spring Data Redis examples: **the connection factory handles credentials**, the Redis Server handles **authentication and ACL checks**, and the service layer performs only permitted data operations.

## 13. Principles to Keep in Mind During Deployment

1. **Know which authentication type Redis requires**: default user password or ACL username/password.
2. **Use Spring Boot's standard connection configuration** when sufficient; create a custom ConnectionFactory only when there is a specific requirement.
3. **Never place secrets in source code, Git examples, logs, or shared URLs.** Use the environment's secret management mechanism.
4. **Grant permissions according to the actual commands and keys the application uses**; include Spring Cache, key prefixes, cache-clear commands, and Pub/Sub/Streams if applicable.
5. **Protect the network channel**, using TLS when needed together with network policies and ACLs.
6. **Separate authentication issues from pooling and connectivity**: WRONGPASS, NOPERM, timeouts, and Connection refused do not share the same fix.
7. **Have a secret rotation process** that accounts for running instances and existing connections/pools.

**Key takeaway:** Spring Data Redis supports both common authentication methods: **a password for the default user** and **ACL username/password**. Spring Boot passes credentials through configuration to the Redis client; the Redis Server decides whether the client may log in and execute commands on keys. Understanding this boundary helps configure accurately, diagnose errors effectively, and grant least-privilege permissions to each service.
