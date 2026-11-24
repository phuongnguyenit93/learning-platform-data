# Preventing LDAP Injection When Building Filters from Input

## 1. The Problem: An Input Field Can Alter the LDAP Filter Structure

In a **Spring Boot Integration** system, an application may query LDAP/Active Directory to find accounts, groups, departments, or verify user info before calling an HTTP client, writing to a database, updating a cache, or emitting events via Kafka/RabbitMQ. LDAP is often viewed as a background data service, yet its **search filter** is also a query language with syntax and operators. Concatenating input data directly into a filter string lets users alter the meaning of the query.

Suppose the application supports looking up users by `uid`:

```java
// UNSAFE: input flows directly into LDAP filter syntax
String filter = "(&(objectClass=inetOrgPerson)(uid="
        + username + "))";
```

When `username = "alice"`, the filter becomes:

```text
(&(objectClass=inetOrgPerson)(uid=alice))
```

When a sender supplies `username = "*"`, the result is:

```text
(&(objectClass=inetOrgPerson)(uid=*))
```

In LDAP search filters, `(uid=*)` is a **presence filter** (requiring only that the `uid` attribute exist), no longer an exact match for one account. The query can return many more people than intended. If the application picks the first result to decide permissions, or returns the full unverified result set, the risk becomes **broadened access scope, directory leakage, or broken authentication logic**.

More sophisticated inputs can include parentheses, `&`, `|`, `!`, and other expressions attempting to reshape the filter tree. Not every payload yields a valid filter, and exploitability depends on how the app handles results and on LDAP server ACLs; nevertheless, **the vulnerability lies in allowing data to control query syntax**.

**Learning objectives:**

- Distinguish an LDAP search filter from a Distinguished Name (DN) and an LDAP URL.
- Understand filter syntax, special characters, and escaping rules per RFC 4515.
- Build safe filters using Spring LDAP APIs instead of string concatenation.
- Restrict attributes, operators, base DN, search scope, and result volume.
- Test injection with malicious data, Unicode, duplicate accounts, and LDAP errors.
- Protect access control and observability when integrating LDAP into Spring Boot.

## 2. LDAP Search Filters Are a Structured Language

Common search filters:

| Form | Meaning | Example |
| --- | --- | --- |
| Equality | Attribute matches value | `(uid=alice)` |
| Presence | Attribute exists | `(mail=*)` |
| Substring | Value matches pattern with wildcard | `(cn=Anh*)` |
| AND | All sub-conditions hold | `(&(objectClass=person)(uid=alice))` |
| OR | At least one sub-condition holds | `(|(uid=alice)(mail=alice@example.org))` |
| NOT | Negates a condition | `(!(accountStatus=disabled))` |
| Comparison | Greater-or-equal / less-or-equal per matching rule | `(employeeNumber>=1000)` |
| Extensible match | Custom matching rule or special match semantics | Depends on directory and schema |

LDAP filters use **prefix** notation: operators precede sub-expressions, such as `(&(a=x)(b=y))`. Data used inside a search value must never be able to introduce new parentheses, wildcards, or OR/NOT branches.

### 2.1. Two Separate Layers: Syntax and Value

The application owns the filter structure:

```text
(&(objectClass=inetOrgPerson)(uid=<VALUE>))
```

Input may act only as the **value of a single comparison**, never changing operators, attribute names, or condition grouping. This parallels parameterized queries in SQL, except **LDAP APIs and escaping rules differ from SQL**. Never use SQL escaping, HTML encoding, or JSON escaping to fix LDAP injection.

### 2.2. Why Input Validation Alone Is Not Enough

Length bounds, type checks, and character allowlists are good defenses, yet validation does not replace building filters properly. Valid usernames/emails in real systems can contain more characters than a simple regex allows; policies change across identity sources.

Apply all of these together:

1. **Input validation** per business contract (length, requiredness, format, canonicalization).
2. **Safe filter construction** via library builders/filter objects to escape values.
3. **Allowlists** for non-parameterizable parts such as attributes or search modes.
4. **LDAP ACLs and search limits** to limit blast radius if queries are abused.
5. **Application authorization** governing which accounts/groups and fields may be exposed.

## 3. RFC 4515: Escaping LDAP Search Filter Values

RFC 4515 defines the string representation of LDAP search filters. When placing a value into a filter **assertion value**, certain special bytes must be written as a backslash followed by two hexadecimal digits.

| Character in Input | Byte / Syntactic Role | How Escaped in Filter |
| --- | --- | --- |
| `*` | Wildcard / presence / substring | `\2a` |
| `(` | Open expression | `\28` |
| `)` | Close expression | `\29` |
| `\` | Escape character | `\5c` |
| NUL | Byte 0x00 | `\00` |

Example when **literally searching for an asterisk**:

```text
Literal input:       *
Wrong (presence):    (uid=*)
Right (literal '*'): (uid=\2a)
```

For username `a(b)c*`:

```text
Literal input:      a(b)c*
Escaped value:      a\28b\29c\2a
Search filter:      (uid=a\28b\29c\2a)
```

Here `\28` and `\29` **are no longer structural parentheses**, and `\2a` **is not a wildcard**. The directory matches against a value containing those literal characters according to the attribute's matching rule.

Never write a custom `replace()` chain in business code: it is easy to get replacement order wrong, miss NUL, mishandle Unicode/bytes, or double-escape. Use framework-implemented and tested components. For UTF-8 strings, RFC 4515 also governs octets and invalid UTF-8 sequences; validate/decode input properly at ingress boundaries.

**Note:** `&`, `|`, and `!` act as operators in specific syntactic positions. Their presence inside a value does not call for an "SQL-like escaping list." Let the library construct the **entire filter** and escape assertion values per LDAP rules.

## 4. The Safest Approach: Spring LDAP LdapQueryBuilder

For Spring Boot 3.x apps using compatible Spring LDAP 3.x, Spring LDAP offers the `LdapQueryBuilder` DSL to declare filter structure and supply inputs strictly as **values**.

### 4.1. Dependencies and Connection Configuration

```kotlin
// build.gradle.kts — Spring Boot manages compatible versions
implementation("org.springframework.boot:spring-boot-starter-data-ldap")
```

```yaml
# application.yml — illustrative; secrets supplied by runtime/secret manager
spring:
  ldap:
    urls: "${LDAP_URLS:ldaps://ldap.example.org:636}"
    base: "dc=example,dc=org"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
```

`spring.ldap.base` is the base DN for the configured LDAP context; search bases below it are typically DNs **relative** to this base. Never put user-supplied usernames, OUs, or DNs directly into configuration. Production requires proper TLS (LDAPS or StartTLS per directory capability), certificate and hostname verification, a secret manager, least-privileged bind permissions, and bounded timeouts/connection pools.

### 4.2. Using User Input in an Equality Filter

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Repository;

record DirectoryPerson(String uid, String commonName, String mail) {}

@Repository
public class DirectoryPersonRepository {
    private final LdapTemplate ldap;

    public DirectoryPersonRepository(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<DirectoryPerson> findByUsername(String username) {
        if (username == null || username.isBlank()
                || username.length() > 64) {
            throw new IllegalArgumentException("Invalid username length");
        }

        LdapQuery safeQuery = query()
                .base("ou=people")
                .countLimit(2)
                .timeLimit(1500)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        return ldap.search(safeQuery,
                (AttributesMapper<DirectoryPerson>) attrs -> {
                    String uid = (String) attrs.get("uid").get();
                    String name = (String) attrs.get("cn").get();
                    Attribute mail = attrs.get("mail");
                    String email = mail == null
                            ? null : (String) mail.get();
                    return new DirectoryPerson(uid, name, email);
                });
    }
}
```

The protection lies in `.and("uid").is(username)`: the framework builds an equality filter and **escapes the username value** rather than concatenating it into syntax. Both `objectClass=inetOrgPerson` and attribute `uid` are application-controlled constants.

`countLimit(2)` detects non-unique results without dumping the whole directory; `timeLimit(1500)` sets a client/query search time limit via Spring LDAP's API, though effective limits also depend on the server, connection timeouts, network, and LDAP configuration. They **do not replace** server-side size/time limits, rate limits, and overall application timeouts.

The mapper assumes entries have `uid` and `cn`. For other schemas (like Active Directory using `sAMAccountName`, `userPrincipalName`), define schema-specific mappings and handle null/multi-valued attributes. Never push directory data into responses before enforcing authorization and allowlisting exposed fields.

### 4.3. Verifying Uniqueness Instead of Picking the First Match

```java
List<DirectoryPerson> found = directoryPersonRepository
        .findByUsername(username);

if (found.isEmpty()) {
    // Account not found under lookup criteria.
    throw new UserNotFoundException();
}
if (found.size() != 1) {
    // Data/contract violation: uid is not unique within search scope.
    throw new AmbiguousDirectoryIdentityException();
}
DirectoryPerson person = found.get(0);
```

`UserNotFoundException` and `AmbiguousDirectoryIdentityException` are **illustrative application-defined exceptions**. In authentication flows, never "take the first user" and treat a search hit as proof of authentication. Finding a directory entry only identifies an **entry matching the query**; it does not prove the caller knows the password, holds a valid session, or has access permission.

## 5. Building Filters with Filter Objects, Avoiding String Concatenation

Spring LDAP also provides `EqualsFilter`, `AndFilter`, and `OrFilter` in `org.springframework.ldap.filter`. When building dynamic filters with multiple **application-controlled** branches, construct a filter tree from objects.

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

String encodeSafeUserFilter(String username, String departmentCode) {
    AndFilter filter = new AndFilter();
    filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    filter.and(new EqualsFilter("uid", username));
    filter.and(new EqualsFilter("departmentNumber", departmentCode));
    return filter.encode();
}
```

Here, attribute names and operators are chosen by the application; `username` and `departmentCode` are **assertion values** escaped by the filter objects. Never write:

```java
// UNSAFE: two request values concatenated directly into the filter
String unsafeFilter = "(&(uid=" + username
        + ")(departmentNumber=" + departmentCode + "))";
```

**Never pass a raw filter string from an HTTP request into APIs** like `query().filter(rawUserFilter)`, even with the intent to "support advanced search." Methods taking raw filters assume the filter source is **already trusted**; they cannot tell syntax apart from untrusted input that needs escaping.

If the application needs optional AND/OR combinations, let clients select from predefined operations (e.g., "lookup by uid", "by email", "by group") and let the backend assemble the filter branches. Never allow clients to send arbitrary parentheses, raw filter fragments, matching rule identifiers, or arbitrary schema attributes.

## 6. Attribute Names, Operators, and Base DNs Are Also Attack Surfaces

Escaping **values** is insufficient if users still control other parts of the query structure. For example:

```java
// WRONG: attributeName comes from an uncontrolled query parameter
String filter = "(" + attributeName + "="
        + userValue + ")";
```

Even when `userValue` is escaped, an invalid attribute or operator can break the query, broaden searches, or exploit attributes readable by the service account that the API must not expose.

### 6.1. Allowlisting Search Fields

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import org.springframework.ldap.query.LdapQuery;

enum AccountSearchField {
    USERNAME, EMAIL
}

LdapQuery safeSearch(AccountSearchField field, String value) {
    String ldapAttribute = switch (field) {
        case USERNAME -> "uid";
        case EMAIL -> "mail";
    };

    return query()
            .base("ou=people")
            .countLimit(20)
            .timeLimit(1500)
            .where("objectClass").is("inetOrgPerson")
            .and(ldapAttribute).is(value);
}
```

HTTP APIs should accept only enum values or mapped names validated strictly; reject anything outside the allowed list. `value` must also enforce length bounds and data contracts. Never expose the entire LDAP schema as public search fields.

### 6.2. Never Let Callers Choose Arbitrary Base DNs or Search Scopes

An API taking arbitrary `baseDn`, `searchScope`, or `filter` inadvertently becomes a general-purpose directory query console. Users could search prohibited OUs or run `SUBTREE` at the directory root instead of `ONELEVEL` at `ou=people`.

Enforce this policy:

- Map tenants/organizations to OUs via **trusted backend configuration**; never use unverified raw tenant headers as DNs.
- Fix Base DN and search scope per endpoint or allowed endpoint group.
- Return only needed attributes; never return full entries by default.
- Enforce result limits, execution timeouts, pagination, and rate limits.
- When restricting by org/tenant, check permissions server-side rather than merely hiding results in the UI.
- Prevent callers from requesting sensitive attributes like password hashes, tokens, or admin metadata.

A service account with directory-wide read rights increases the blast radius of any flaw. Prefer a bind account restricted to needed OUs/attributes, backed by application-level authorization.

## 7. Distinguishing LDAP Filter Escaping from DN Escaping

LDAP has at least **two distinct contexts often confused**:

1. **Search filters** per RFC 4515, e.g., `(uid=alice)`.
2. **Distinguished Names** per RFC 4514, e.g., `uid=alice,ou=people,dc=example,dc=org`.

The special characters and escaping rules for these two contexts **differ**. For instance, commas `,` and plus signs `+` have structural roles in DNs, yet are not all special characters in filter assertion values. Conversely, `*` is a wildcard in filters, not a DN operator.

Never apply filter escaping to build a DN, and never take an already DN-escaped string and drop it into a filter without filter escaping. Use the right structured API for each context.

### 7.1. Building DNs with LdapNameBuilder

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDnForUser(String userId) {
    // RDN values are encoded per DN rules, not filter rules.
    return LdapNameBuilder.newInstance("ou=people")
            .add("uid", userId)
            .build();
}
```

If `userId` contains commas, plus signs, or DN special characters, the builder encodes the RDN value in the DN context. The base DN here is a trusted constant; never let input choose the organization, OU, or root directory.

In plain JNDI, `javax.naming.ldap.Rdn` and `LdapName` also build structured DNs. Never concatenate:

```java
// UNSAFE: userId can break out of the DN structure.
String unsafeDn = "uid=" + userId + ",ou=people,dc=example,dc=org";
```

**Note on authentication:** Spring Security LDAP provides authentication via bind or password comparison as configured. When implementing LDAP login, use proper authentication components and brute-force protections rather than concatenating DNs/filters and merely checking "search found an account." Safe queries are only one piece of authentication.

## 8. Prefix/Wildcard Search: Keep Decision Control on the Backend

In autocomplete or prefix name lookup, wildcards can be a **valid product requirement**. Yet there is a huge difference between:

- Client sends `prefix = "an"`, and the backend offers a "starts with" feature with backend-controlled wildcards.
- Client sends a raw filter string `(cn=an*)` or injects `*`, parentheses, and ORs freely.

For fuzzy/prefix searches, design as follows:

1. User input remains strictly a **literal search term**, never a filter fragment.
2. The backend picks a fixed operator (`starts_with`, `contains`, or `exact`) from an allowed enum.
3. Use a builder/API dedicated to **substring matching** so the literal portion is escaped and only backend-controlled wildcards are added. Never concatenate raw input into `(cn=...*)`.
4. Enforce minimum prefix length, result caps, timeouts, and rate limits to prevent enumerating the whole directory.
5. Never use substring/contains searches for authentication or account authorization requiring an exact unique match.

Some Spring LDAP DSL methods support substring/like searches depending on the version. Verify via **tests** how those methods handle wildcards and escaping; never assume `like`-style methods enforce the exact same behavior as `is()`. When constructing advanced filters, compose them strictly from trusted primitives and context-escaped values.

## 9. Integrating with HTTP APIs: Preventing Input from Controlling LDAP

In a REST API, an account lookup endpoint might accept:

```http
GET /api/directory/users?username=alice HTTP/1.1
Accept: application/json
```

Never let the frontend send arbitrary `ldapFilter`, `baseDn`, or `attribute` values and forward them. HTTP should accept only **business parameters** like `username`, `email`, or `departmentCode`.

### 9.1. Sample Controller Separating Input from Filter

```java
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/directory/users")
class DirectoryController {
    private final DirectoryPersonRepository directory;

    DirectoryController(DirectoryPersonRepository directory) {
        this.directory = directory;
    }

    @GetMapping
    ResponseEntity<List<DirectoryPerson>> searchByUsername(
            @RequestParam String username) {
        // Demo: production must verify caller permissions,
        // restrict returned fields, and apply appropriate rate limits.
        List<DirectoryPerson> users = directory.findByUsername(username);
        return ResponseEntity.ok(users);
    }
}
```

This example focuses on data crossing the HTTP → LDAP boundary. **Do not treat it as a complete secure public API**: add authentication, authorization, an allowlist of response fields, user-enumeration mitigations, and PII protection. Filter builders do not replace access control.

To limit information leakage during login flows, never distinguish "username does not exist" from "wrong password" if security policy requires preventing account enumeration. Public messages should be uniform, while internal logs retain only necessary details under access control.

### 9.2. Handling LDAP Failures and Fallbacks

LDAP is a network dependency and can hit connection timeouts, referrals, busy servers, size/time limits exceeded, or TLS errors. An application may apply bounded retries with backoff for transient errors, yet must not retry infinitely or widen search scopes upon failure.

For **authorization**, never auto-allow access when LDAP is unreachable unless security policy defines a verified fallback mechanism. Cached directory results need TTLs, invalidation, and stale-permission risk analysis. If using a Redis cache or Kafka events to propagate group status, define the source of truth and acceptable sync lag.

## 10. Testing LDAP Injection Prevention

### 10.1. Unit Tests for Filter Objects

The smallest property to prove is that **input remains a literal** without changing filter structure. JUnit example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class LdapFilterEscapingTest {

    @Test
    void starMustBeLiteralInsteadOfPresenceFilter() {
        String encoded = new EqualsFilter("uid", "*").encode();
        assertEquals("(uid=\\2a)", encoded);
    }

    @Test
    void parenthesesMustNotChangeFilterStructure() {
        String encoded = new EqualsFilter("uid", "a(b)c").encode();
        assertEquals("(uid=a\\28b\\29c)", encoded);
    }

    @Test
    void backslashMustBeEscaped() {
        String encoded = new EqualsFilter("uid", "a\\b").encode();
        assertEquals("(uid=a\\5cb)", encoded);
    }

    @Test
    void nulMustBeEscaped() {
        String encoded = new EqualsFilter(
                "uid", "a" + String.valueOf((char) 0) + "b").encode();
        assertEquals("(uid=a\\00b)", encoded);
    }
}
```

These tests illustrate RFC 4515 semantics; when running them, verify the output of your exact Spring LDAP version. Do not write a custom encoder just to test that encoder; test the library's API and **actual query execution paths**. Passing helper unit tests does not guarantee no other place in the app still uses string concatenation.

### 10.2. Integration Tests Against a Real Directory

Using an embedded LDAP server/test container or an authorized test directory, seed fixed entries such as:

```text
ou=people,dc=example,dc=org
  uid=alice  -> inetOrgPerson
  uid=bob    -> inetOrgPerson
  uid=admin  -> inetOrgPerson
```

| Input Data | Expectation |
| --- | --- |
| `alice` | Returns only Alice's entry when caller is authorized |
| `*` | Does not become a presence filter, does not return all users |
| `a(b)c` | Matched as literal value if allowed by policy |
| `\` or `a\b` | Does not break filter parser or alter query structure |
| NUL, overly long string, blank | Rejected by validation or safely encoded per contract |
| Strings with multiple parens and `\|`/`&` | Does not alter backend's fixed condition set |
| Valid Unicode | No encoding errors or semantic drift if schema permits |
| Two entries sharing username in scope | Throws ambiguous error, never picks first entry |
| Attribute name outside allowlist | Rejected, never becomes a raw LDAP attribute |
| Out-of-bounds search scope/base | Cannot be executed via HTTP input |
| LDAP timeout/referral/unavailable | Does not fail-open permissions; bounded error/timeout |
| Narrowly privileged bind account | Cannot read entries/attributes beyond granted permissions |

Tests should assert both **which entity is returned** and **that out-of-scope data is not leaked**, not merely compare filter strings. For Active Directory, test against the real schema (case folding, multi-valued attributes, nested groups, referrals) because behavior can differ from simple test directories.

### 10.3. Escaping Tests Do Not Replace Authorization Tests

Even with properly escaped filters, an API can still return users the caller is not permitted to see if authentication/authorization is missing. Test account, OU, tenant, group, and sensitive-field permissions; verify there is no way to supply another user's ID/DN to read unauthorized records. Security tests must cover the **authorization boundary**, not just filter syntax.

## 11. Logging, Tracing, and Metrics for LDAP Errors

Operations typically need to know how long queries take, whether they timed out, returned not-found, or hit schema errors. You do not need to log raw filters containing user values.

**Low-cardinality metrics** can include:

```text
ldap_lookup_duration_seconds{
    operation="find_by_username",
    directory="corporate",
    outcome="success"
}

ldap_lookup_total{
    operation="find_by_username",
    outcome="timeout"
}
```

Avoid labels like `username`, `email`, `uid`, `dn`, `raw_filter`, or `correlationId` due to high cardinality and personal identifier exposure. Use access-controlled structured logs/traces for individual investigations when genuinely needed, with retention, masking, and restricted access. If inputs contain newlines/control characters, sanitize logs to prevent log injection.

For tracing, propagate correlation IDs across HTTP → LDAP operation → DB/cache/broker per your observability architecture, but **never** attach raw LDAP filters as default attributes on every span. When logging exceptions, avoid combining username, bind credentials, full DN, and full server errors if doing so leaks sensitive data.

Useful alerts:

- Unusual spikes in query failure/timeout/busy-server rates.
- Search p95/p99 latency, query volume, or result counts exceeding operation thresholds.
- Validation rejection counts (without using raw input as a label).
- Locked bind accounts, TLS/certificate errors, and referral loops.
- Sudden surge in wildcard/broad searches, indicating enumeration or client misconfiguration.

## 12. Misguided Injection "Fixes"

| Wrong Approach | Why It Fails | Use Instead |
| --- | --- | --- |
| `filter = "(uid=" + input + ")"` | Input controls syntax | `where("uid").is(input)` or `EqualsFilter` |
| Stripping only `*` | Leaves `(`, `)`, `\`, NUL; corrupts legitimate data | Library RFC 4515 escaping |
| HTML/URL/SQL escaping | Wrong syntax for LDAP filters | LDAP-specific filter builders |
| Using filter escaping to build a DN | RFC 4515 differs from RFC 4514 | `LdapNameBuilder`/`Rdn` for DNs |
| Letting clients send raw LDAP filters for "flexibility" | Grants control over operators/attributes/scope | Enum/field allowlist API |
| Letting any authenticated user query arbitrarily | Authentication is not authorization | Narrow ACLs, endpoint-level authorization |
| Catching exceptions and widening the search | Can expose directory on malformed queries | Fail cleanly and investigate errors |
| Taking the first LDAP match as identity | Broad filters/duplicate entries cause identity confusion | Enforce uniqueness and true authentication |
| Logging full filters for debugging | Leaks usernames, DNs, PII; adds log injection surface | Log normalized operation, outcome, latency |
| Relying solely on input length limits | Short inputs like `*` still carry special syntax | Escaping + schema/policy validation |
| Sharing an all-powerful service account across APIs | One flaw expands lookup blast radius | Least-privilege binds and narrow search scopes |
| Trusting user/group caches indefinitely | Misses revocations and directory updates | TTL/invalidation, explicit consistency policy |

## 13. Implementation Checklist in Spring Boot Integration

- [ ] All LDAP search filters accepting input from HTTP, files, Kafka/RabbitMQ, Redis, or partners use builders/filter objects; never concatenate input into raw filters.
- [ ] Clearly separate **filter assertion values** (RFC 4515) from **DN/RDN values** (RFC 4514); use context-appropriate escaping APIs.
- [ ] Attribute names, operators, base DNs, search scopes, and matching rules come from backend allowlists/config.
- [ ] Input validation aligns with business rules, yet escaping still runs even on valid inputs.
- [ ] Searches enforce narrow bases/scopes, size/time limits, pagination/rate limits, and minimal attribute projections.
- [ ] Every identity lookup enforces uniqueness; never treat "first result" as proof of authentication.
- [ ] LDAP bind accounts have least privilege, connections use TLS with certificate validation, and credentials stay out of source/logs.
- [ ] APIs authenticate/authorize via proper mechanisms; directory lookups never replace password/token verification.
- [ ] Timeouts, referrals, and server-unavailable errors never fail-open authorization.
- [ ] Tested `*`, parentheses, backslashes, NUL, Unicode, overly broad queries, non-allowlisted attributes, and schema errors.
- [ ] Integration tests against a real or compatible LDAP server confirm malicious inputs never broaden results.
- [ ] Logs/traces and metrics omit raw filters, bind credentials, usernames/emails/DNs, and personal IDs in metric labels.
- [ ] When LDAP data flows to DB/cache/broker, target schemas, retention, access controls, idempotency, and data contracts still apply.

**Desired outcome:** When a Spring Boot application queries LDAP, external inputs can affect only the **value to match**, never turning into operators, arbitrary attributes, or expanded search scopes. Using Spring LDAP query/filter builders, context-appropriate DN builders, permission bounds, and integration testing prevents LDAP injection while keeping search, authentication, and observability intact.
