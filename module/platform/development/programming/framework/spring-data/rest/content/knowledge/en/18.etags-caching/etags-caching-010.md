# Distinguishing Header-Based Freshness Validation from Application Data Caching

## Objectives

After this lesson, you will be able to:

- Distinguish HTTP caching at the client/proxy from application caching on the server.
- Explain the roles of **ETag**, **Last-Modified**, **If-None-Match**, and **If-Modified-Since**.
- Understand the **304 Not Modified** response and how clients reuse stored representations.
- Configure appropriate **Cache-Control** and **Vary** headers for HTTP representations.
- Recognize optimistic locking with **@Version** and **If-Match**.
- Use Spring Cache with **@Cacheable**, **@CachePut**, and **@CacheEvict**.
- Design cache invalidation when data changes via services or Spring Data REST.
- Avoid confusing freshness validation with storing data in the application cache.

## 1. Two Cache Layers Solving Two Different Problems

When a client calls Spring Data REST, data can be cached in multiple places. Two common layers are:

**HTTP cache** stores response representations in the browser, reverse proxy, or CDN. The server controls this caching via HTTP response headers such as Cache-Control, ETag, Last-Modified, and Vary. The client can ask the server whether the stored copy is still fresh.

**Application cache** stores processing results or data on the server side, usually in application memory or a shared cache such as Redis. Spring Cache provides an abstraction to cache method results and evict or update entries when data changes.

| Criterion | HTTP cache / freshness | Application cache |
|---|---|---|
| Where is it stored? | Browser, proxy, CDN, or HTTP client | Server memory, Caffeine, Redis, or another cache provider |
| What is stored? | HTTP representation and metadata | Method results, DTOs, data, or objects |
| Primary mechanism | Cache-Control, ETag, Last-Modified, conditional requests | @Cacheable, @CachePut, @CacheEvict |
| How is freshness checked? | Client sends validator; server returns 304 or new representation | Application uses TTL, keys, eviction, or refresh |
| Who controls it? | HTTP server and caches obeying HTTP semantics | Application code and configuration |
| Example | Browser holds HAL JSON and sends If-None-Match | Service keeps PersonDto by ID in Redis |

Both layers can operate at the same time. The browser can hold an HTTP response while the server uses Redis to quickly retrieve data when building a new response. Deleting a Redis entry does not automatically clear the response copy in the browser; HTTP headers do not automatically clear server caches either.

## 2. Freshness and Validation in HTTP Caching

An HTTP cache can use two approaches to decide whether a stored response can be reused or needs to check back with the server:

1. **Freshness lifetime**: the response is still fresh according to the declared duration, for example Cache-Control: max-age=60.
2. **Validation**: the response has exceeded its freshness time or requires rechecking; the client sends a validator such as ETag or Last-Modified.

If the response is still fresh, the cache can return it immediately without calling the origin server. If revalidation is needed, the cache sends a conditional request with the validator. The server determines whether the representation has changed.

Example response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, max-age=60
ETag: "person-42-v7"

{ "name": "Lan" }
~~~

The browser can store the body along with the ETag. When the response exceeds its freshness lifetime, the browser sends:

~~~http
GET /api/people/42 HTTP/1.1
If-None-Match: "person-42-v7"
Accept: application/hal+json
~~~

If the representation still corresponds to that ETag, the server returns:

~~~http
HTTP/1.1 304 Not Modified
ETag: "person-42-v7"
Cache-Control: private, max-age=60
~~~

The **304 Not Modified** response does not resend the body. The client uses the previously stored body and updates cache metadata per the new response. 304 is a normal result of a conditional GET, not an error.

If the representation has changed, the server returns a new response, typically **200 OK**, accompanied by the new body and new validator.

## 3. ETag Is a Representation Validator

An **ETag** (Entity Tag) is a string validator issued by the server for a representation. The client stores this value and sends it back in the next request for the server to compare.

Example:

~~~http
ETag: "person-42-v7"
~~~

An ETag is an opaque identifier: the client should not parse its internal contents to infer versions or business data. The server decides how to generate it, such as from an entity version, a representation checksum, or a version code.

There are two forms:

- **Strong ETag**: has no W/ prefix; used when representations are considered byte-for-byte equivalent under strong validator rules.
- **Weak ETag**: has the **W/** prefix, for example **W/"person-42-v7"**; indicates representations are semantically equivalent though they may differ byte-for-byte.

Example:

~~~http
ETag: W/"person-42-v7"
~~~

For conditional GET using If-None-Match, HTTP permits weak validator comparison. For operations requiring exact version checks such as If-Match, strong comparison is required; a weak ETag is unsuitable for ensuring optimistic concurrency.

The ETag must change when the relevant representation changes in a way the validator needs to detect. If a response depends on projection, Accept, language, user permissions, or related data, ETag generation must account for factors that can make representations differ. Do not use the same ETag for two different representations merely because they come from the same entity ID.

## 4. If-None-Match and Conditional GET

**If-None-Match** lets the client send back one or more ETags it holds:

~~~http
If-None-Match: "person-42-v7"
~~~

For GET or HEAD:

- If the current representation matches the validator under weak comparison rules, the server can return **304 Not Modified**.
- If it does not match, the server returns the new representation, typically **200 OK**.

Example verification with curl:

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  -H 'If-None-Match: "person-42-v7"' \
  http://localhost:8080/api/people/42
~~~

If multiple ETags need to be checked, the header can contain a tag list or **\*** per HTTP syntax. Let the HTTP client construct valid header syntax; do not compare ETag strings on the client and skip the server.

**If-None-Match** is also used in certain write requests with a non-existence/mismatch condition; when the condition fails, the server can return **412 Precondition Failed**. For this lesson, the most important case is conditional GET to reuse cached responses.

If a request carries both If-None-Match and If-Modified-Since, If-None-Match takes higher precedence under HTTP semantics. The server must not ignore the ETag to rely solely on modification time.

## 5. Last-Modified and If-Modified-Since

**Last-Modified** indicates when the representation was last modified:

~~~http
Last-Modified: Tue, 10 Nov 2026 09:30:00 GMT
~~~

The client stores this value and sends it on a subsequent request:

~~~http
If-Modified-Since: Tue, 10 Nov 2026 09:30:00 GMT
~~~

If the representation has not changed since that timestamp, the server can return 304. If it has changed, the server returns the new body along with the new Last-Modified.

Example:

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  -H 'If-Modified-Since: Tue, 10 Nov 2026 09:30:00 GMT' \
  http://localhost:8080/api/people/42
~~~

Last-Modified is straightforward to implement when data has a reliable update timestamp. However, HTTP dates have one-second resolution; multiple updates within the same second can be hard to distinguish by time alone. Inaccurate server clocks or improperly updated timestamps also make the validator wrong.

ETag is usually more accurate and flexible because it can be based on a version or checksum. An application can emit both ETag and Last-Modified; when a client sends both validators, the server must follow HTTP precedence rules.

## 6. Cache-Control Determines How Responses Are Stored and Reused

**Cache-Control** governs the cache policy for a response. Some common directives:

| Directive | Meaning |
|---|---|
| **max-age=60** | The response is considered fresh for 60 seconds from the appropriate point under HTTP caching rules |
| **private** | Only private caches such as browsers may store it; shared caches must not use that response |
| **public** | Allows shared caches to store the response if other HTTP conditions permit |
| **no-cache** | The response can be stored, but must be revalidated before reuse |
| **no-store** | Do not store the response in any HTTP cache |
| **must-revalidate** | Once stale, caches must revalidate before reusing |
| **s-maxage=120** | Freshness lifetime for shared caches; overrides max-age in shared caches |

In particular, distinguish:

- **no-cache** does not mean do not store. It requires rechecking before reuse.
- **no-store** instructs caches not to store the response.
- **private** restricts storage to private caches; it does not encrypt data and does not replace authorization.

Example personal response that may use:

~~~http
Cache-Control: private, max-age=60
~~~

A response containing sensitive data that policy forbids storing can use:

~~~http
Cache-Control: no-store
~~~

A response that can be stored but must check freshness before use:

~~~http
Cache-Control: private, no-cache
ETag: "person-42-v7"
~~~

Choose directives based on actual data and risk. Do not set public on a response that depends on the logged-in user if a shared cache could accidentally serve one person's representation to another.

## 7. Vary: Distinguishing Response Variants

A URL can return different representations depending on request headers. For example, a client requests HAL or another JSON format, or the server alters content by language.

The **Vary** header tells caches which request headers alter the representation:

~~~http
Vary: Accept, Accept-Language
~~~

Caches must treat different Accept and Accept-Language values as distinct response variants for the same URL.

If the server emits HAL based on Accept, verify the response includes Vary: Accept when needed. If a response is personalized by cookie or authorization, choose an appropriate cache policy and do not rely solely on Vary to protect data.

Vary is not a list of fields in the body. It describes request headers that affect how the server produces the representation.

## 8. Freshness Headers in Spring MVC

For custom controllers, Spring MVC provides **WebRequest.checkNotModified(...)** to evaluate conditional requests. The controller can compute ETag or Last-Modified, then let Spring set status 304 when the validator is still valid.

Example:

~~~java
import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

@RestController
public class PersonController {

    private final PersonService personService;

    public PersonController(PersonService personService) {
        this.personService = personService;
    }

    @GetMapping("/api/people/{id}")
    public ResponseEntity<PersonDto> getPerson(
            @PathVariable Long id,
            WebRequest request) {

        PersonDto person = personService.findById(id);

        String etag = "\"" + person.version() + "\"";
        long lastModified = person.updatedAt().toEpochMilli();

        if (request.checkNotModified(etag, lastModified)) {
            return null;
        }

        return ResponseEntity.ok()
            .eTag(etag)
            .lastModified(lastModified)
            .cacheControl(
                CacheControl.maxAge(Duration.ofSeconds(60)).cachePrivate()
            )
            .body(person);
    }
}
~~~

This is an illustrative example for a custom MVC endpoint. **version()** and **updatedAt()** are assumed DTO accessors. In a real application, ETag must represent the exact representation and lastModified must come from a reliable timestamp.

**checkNotModified** should be called before building or serializing an expensive body. If the request already carries a matching validator, Spring can terminate the response with 304 without sending a body. Verify behavior on the Spring MVC version and servlet container in use.

Simply adding an ETag header to ResponseEntity does not mean every request is automatically compared. In custom controllers, conditional requests must be handled explicitly or via supported framework mechanisms.

## 9. Spring Data REST and Optimistic Locking with @Version

ETag can also serve another purpose: preventing clients from overwriting newer changes made by others. This is **optimistic locking**.

With JPA, declare a version field:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Version
    private Long version;
}
~~~

The version is incremented by the persistence provider when the entity is updated. Spring Data REST can use the version property to support optimistic locking and ETags for item resources depending on configuration/version. Inspect actual responses to confirm what ETag the API emits.

Illustrative flow:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

Response includes ETag:

~~~http
ETag: "7"
~~~

The client edits the resource and sends the read validator:

~~~http
PUT /api/people/42
If-Match: "7"
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan Nguyen"
}
~~~

If another client has updated the entity and the current version no longer matches, the server rejects the conditional operation, typically with **412 Precondition Failed** or an optimistic locking error according to how the framework maps it.

Distinguish the two directions of ETag usage:

- **If-None-Match** in GET: "Is the copy I am holding still fresh?" If it matches, the server returns 304.
- **If-Match** in PUT/PATCH/DELETE: "Execute only if the resource is still at the version I read." If it does not match, the server rejects to prevent lost updates.

ETag can be used for both cache validation and optimistic concurrency, yet the meaning depends on the request header. Do not pull an ETag from another response or alter the tag string on the client.

## 10. Application Cache in Spring

Application caching stores processing results on the server side. Spring Cache provides annotations to mark methods that can be cached, update the cache, or evict entries.

Enable caching:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Example caching the result of reading a Person:

~~~java
@Service
public class PersonQueryService {

    private final PersonRepository personRepository;

    public PersonQueryService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Cacheable(cacheNames = "peopleById", key = "#id")
    public PersonDto findById(Long id) {
        Person person = personRepository.findById(id)
            .orElseThrow();

        return PersonDto.from(person);
    }
}
~~~

When **findById(42)** is called the first time, the method runs and the result is stored under key 42. Subsequent calls can retrieve the result from cache without re-executing the query inside the method.

**@Cacheable** does not generate HTTP ETags, does not add Cache-Control, and does not make browsers return 304. It affects only server-side method execution.

Spring Boot can auto-configure an appropriate cache provider based on dependencies present in the application. Caffeine is typically suited for local in-process caching; Redis is suited when multiple instances need to share a cache. Configure TTL, capacity, serialization, and eviction policies according to the provider in use.

## 11. @CacheEvict and @CachePut When Data Changes

A cache is useful only when the application has a strategy to update or evict stale entries.

### Evicting an entry after an update

~~~java
@Service
public class PersonCommandService {

    private final PersonRepository personRepository;

    public PersonCommandService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @CacheEvict(cacheNames = "peopleById", key = "#id")
    @Transactional
    public Person update(Long id, PersonUpdateRequest request) {
        Person person = personRepository.findById(id)
            .orElseThrow();

        person.setName(request.name());
        return personRepository.save(person);
    }
}
~~~

After the update method succeeds, the entry with the matching key is evicted. The next read loads fresh data and repopulates the cache.

### Evicting list and query caches

If search or collection results are also cached, updating a Person can affect multiple results. You can use:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "peopleById", key = "#id"),
    @CacheEvict(cacheNames = "peopleSearch", allEntries = true)
})
@Transactional
public Person update(Long id, PersonUpdateRequest request) {
    // Load, modify, and save Person.
}
~~~

**@CachePut** can update an entry with the method's return value instead of evicting it:

~~~java
@CachePut(cacheNames = "peopleById", key = "#result.id")
public PersonDto updateAndReturn(PersonUpdateRequest request) {
    // Update data and return the full DTO.
}
~~~

Use **@CachePut** only when you are sure the method result is the complete representation matching the key. For caches depending on queries, filters, sorting, or user permissions, evicting related entries is usually safer than manually updating individual variants.

## 12. Transaction Boundaries and Cache Invalidation

Cache invalidation must be synchronized with when data is committed.

If the cache is evicted too early, another request may read old data from the database and reload it into the cache before the update transaction commits. If a transaction rolls back after the cache was already evicted, the system may have to reload data even though the data did not actually change; this is usually safe but causes unnecessary cache misses.

For use cases requiring strict control, you can publish a domain event inside the transaction and evict the cache only after commit:

~~~java
public record PersonChanged(Long personId) {
}
~~~

~~~java
@Service
public class PersonCommandService {

    private final PersonRepository repository;
    private final ApplicationEventPublisher events;

    public PersonCommandService(
            PersonRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public Person update(Long id, PersonUpdateRequest request) {
        Person person = repository.findById(id).orElseThrow();
        person.setName(request.name());

        Person saved = repository.save(person);
        events.publishEvent(new PersonChanged(saved.getId()));
        return saved;
    }
}
~~~

~~~java
@Component
public class PersonCacheInvalidator {

    private final CacheManager cacheManager;

    public PersonCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterPersonChanged(PersonChanged event) {
        Cache byId = cacheManager.getCache("peopleById");
        if (byId != null) {
            byId.evict(event.personId());
        }

        Cache searches = cacheManager.getCache("peopleSearch");
        if (searches != null) {
            searches.clear();
        }
    }
}
~~~

The listener runs only after the transaction containing the event commits successfully. If the transaction rolls back, the cache is not evicted by this listener. The example requires importing the corresponding Spring Cache, transaction event, and event publisher types.

Spring Data REST by default calls the repository directly for repository resources. If caching is placed in a service that the REST exporter does not call, `@CacheEvict` annotations on that service will not run when clients write through the default repository endpoint.

If the application permits writes via both services and Spring Data REST endpoints, you must have an invalidation strategy covering every write path. You can use custom endpoints calling command services, place cache policies at the appropriate repository/event integration point, or handle repository events with post-commit synchronization suitable for your version. Do not assume an AfterSave event always means the transaction has committed; verify the actual lifecycle and transactions.

## 13. Which Data Should Be Cached?

Cache repeated reads that are relatively stable and have clear keys. Examples:

- Detail DTOs by ID.
- Infrequently changing catalogs.
- Public configuration or metadata.
- Popular search results with a short TTL and a clear invalidation policy.

Be cautious with:

- JPA entities with lazy associations or persistence context state.
- Collections with many filter, sort, page, and projection variants.
- Data depending on tenant, user, role, or access permissions.
- Balances, inventory, or statuses requiring high freshness.
- Results containing personal or confidential data.

It is usually better to cache immutable DTOs or data detached from the persistence context rather than keeping long-lived JPA entities in cache. The key must include every factor that changes the result, such as tenant ID, locale, or projection type. Do not share a key solely by ID if the same ID can be viewed differently by different users.

## 14. How Do HTTP Caching and Application Caching Cooperate?

A request can pass through both layers:

1. The browser checks its stored HTTP response.
2. If the copy is still fresh, the browser returns data from cache without calling the server.
3. If revalidation is needed, the browser sends If-None-Match or If-Modified-Since.
4. The server determines the current ETag/Last-Modified.
5. To build a new representation or compute the validator, the server can read data from the application cache.
6. If the validator matches, the server returns 304; otherwise, it returns 200 with the new body.
7. The browser updates the HTTP cache per Cache-Control and the new validator.

For example, Redis can cache PersonDto for 5 minutes while the browser caches the response for 30 seconds. The two TTLs do not need to match because they manage two different layers. However, when Person changes, the application needs to invalidate Redis and the next HTTP response must emit a validator/freshness policy reflecting the new data.

Do not assume that clearing Redis automatically notifies the browser. The browser only learns a response changed when freshness expires, upon revalidation, when purged by an external mechanism, or upon receiving a new request per HTTP rules.

Conversely, setting **Cache-Control: no-store** does not prevent the server from using Caffeine or Redis. It controls only HTTP caching, not application caching.

## 15. Testing Freshness and Application Caching

When debugging, test the two layers separately.

### Testing HTTP caching

1. Call GET and save ETag, Last-Modified, Cache-Control, and Vary.
2. Call again with If-None-Match.
3. Verify 304 has no response body when the representation has not changed.
4. Modify the data and call again with the old ETag.
5. Verify the server returns the new representation and new validator.
6. Verify the response distinguishes representations by Accept or user.

Example:

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  -H 'If-None-Match: "person-42-v7"' \
  http://localhost:8080/api/people/42
~~~

### Testing application caching

1. Call the service method the first time and verify repository queries execute.
2. Call again with the same cache key and verify the result comes from cache.
3. Update data through each write path supported by the application.
4. Verify item keys and related query caches are evicted or refreshed.
5. Test local and distributed caches when running multiple instances.
6. Verify rollbacks do not leave uncommitted data in the cache.

Do not rely solely on response times to conclude caching is working. Observe cache metrics, hit/miss ratios, query logs, and actual data.

## 16. Common Errors

### Confusing ETag with a data storage location

ETag is only a validator. It holds no body and is not a cache store. Clients or proxies store representations; ETag helps validate the stored copy.

### Thinking 304 is an error

304 indicates the client can reuse the stored representation. The response does not need to resend the body.

### Using no-cache with the meaning of no-store

no-cache requires revalidation before reuse; no-store instructs not to store the response in HTTP caches.

### ETag does not change even though data changed

The validator does not fully reflect the version or fields affecting the representation. Use an appropriate version/checksum and account for projection, media type, locale, or permissions.

### Cache-Control inappropriate for personal data

User-dependent responses cached in shared caches can leak data. Choose private/no-store and enforce authorization according to actual requirements.

### Clearing application cache yet the browser still displays stale data

The two cache layers are independent. Check max-age, validators, and revalidation behavior in the HTTP cache.

### Service cache is not evicted when writing via Spring Data REST

The default REST exporter calls repository resources, which can bypass services carrying `@CacheEvict`. All write paths must be covered by an appropriate invalidation strategy.

### Cache is repopulated with stale data while a transaction is uncommitted

Invalidation occurred before commit or a reader loaded data while the update transaction had not completed. For strict consistency requirements, handle invalidation after commit and test concurrency.

### Using a cache key missing tenant or projection

Two requests with the same ID but different tenants, locales, projections, or permissions can receive the wrong result. Include factors affecting the result in the key or do not cache that data.

### Thinking @Version automatically replaces all HTTP cache policies

`@Version` helps detect update conflicts and can be used as an ETag in Spring Data REST. It does not automatically decide max-age, private/public, no-store, or Vary.

## 17. Key Takeaways

- HTTP caching stores representations at clients/proxies; application caching stores data or method results on the server.
- **ETag** and **Last-Modified** are validators; **If-None-Match** and **If-Modified-Since** request freshness checks.
- When a representation has not changed, conditional GET can receive **304 Not Modified** and the client reuses the stored body.
- **Cache-Control** governs freshness and cacheability; **Vary** distinguishes variants by request headers.
- **If-Match** can protect updates from lost updates; JPA **@Version** supports optimistic locking.
- Spring Cache uses **@Cacheable**, **@CachePut**, and **@CacheEvict** for server-side caching.
- Invalidation must cover every write path, including repository endpoints exposed by Spring Data REST.
- When strict consistency is required, tie invalidation to transaction commit time.
- HTTP caching and application caching are independent; configuring or clearing one layer does not automatically affect the other.
- Separately test HTTP statuses/headers, cache hits/misses, repository queries, and post-update behavior.

## References

- [RFC 9110 — HTTP Semantics: Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-conditional-requests)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)