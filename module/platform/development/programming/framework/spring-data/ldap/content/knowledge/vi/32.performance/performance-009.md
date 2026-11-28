# Cache tra cứu với đánh đổi về độ mới và phân quyền

Tra cứu LDAP lặp lại cùng một thông tin có thể tạo nhiều round trip, tăng tải directory server và làm ứng dụng phụ thuộc mạnh vào latency của mạng. Cache giúp giảm số lần search, nhưng dữ liệu directory thay đổi theo vòng đời tài khoản, group membership, quyền đọc và replication giữa các máy chủ. Một kết quả cache nhanh có thể đã cũ; nghiêm trọng hơn, cache key thiếu tenant hoặc authorization scope có thể trả dữ liệu của người này cho người khác.

Trong module **SPRING_DATA_LDAP**, cache cần được thiết kế cùng với DN, base DN, search scope, filter, schema, ACL và luồng CRUD. Bài thuộc chương **Hiệu năng**, tập trung vào chủ đề **“Cache tra cứu với đánh đổi về độ mới và phân quyền”**. Nội dung hướng dẫn chọn dữ liệu phù hợp để cache, xây cache key theo phạm vi tin cậy, cấu hình TTL, xử lý invalidation sau write, phối hợp nhiều instance và kiểm thử freshness/security.

> **Nguyên tắc:** cache là bản sao tạm thời của dữ liệu directory. Nó không thay thế LDAP ACL, xác thực, authorization hoặc kiểm tra trạng thái tài khoản tại thời điểm cần thiết. Trước khi trả dữ liệu từ cache, ứng dụng vẫn phải xác định caller có quyền đọc dữ liệu đó theo policy hiện hành.

## 1. Vì sao cache tra cứu LDAP?

Một ứng dụng có thể tra cứu cùng một người dùng nhiều lần trong một phiên làm việc:

- Lấy tên hiển thị sau khi người dùng đăng nhập.
- Hiển thị thông tin nhân viên trong nhiều màn hình.
- Đọc group membership để dựng menu.
- Resolve DN từ UID hoặc email.
- Đọc thông tin phòng ban để xử lý nghiệp vụ.
- Tải danh sách thuộc tính phục vụ một API tổng hợp.

Nếu mỗi lần đều gọi LDAP, ứng dụng tạo nhiều search request giống nhau. Cache-aside có thể giảm số request và latency khi dữ liệu được đọc thường xuyên, ít thay đổi.

Ví dụ:

```text
Request A ── search uid=u1001 ──► LDAP
             nhận PersonSummary
                    │
                    ▼
                 Cache
                    ▲
                    │ hit
Request B ──────────┘
                    │
                    ▼
             trả PersonSummary
             không search LDAP
```

Lợi ích thường thấy:

- Giảm số lần search lặp lại.
- Giảm tải trên LDAP server và connection pool.
- Giảm latency của các request đọc phổ biến.
- Giúp ứng dụng chịu được biến động latency ngắn của directory.
- Có thể giảm chi phí lookup group hoặc metadata được đọc thường xuyên.

Nhưng cache chỉ hữu ích khi có thể xác định rõ **dữ liệu nào được cache, ai được đọc, chấp nhận dữ liệu cũ trong bao lâu và cách xóa cache khi dữ liệu thay đổi**.

## 2. Phân biệt connection pool và result cache

Hai cơ chế này giải quyết hai vấn đề khác nhau:

| Cơ chế | Tái sử dụng gì? | Có bỏ qua LDAP search không? |
|---|---|---|
| LDAP connection pool | Kết nối/context đã mở để giảm chi phí tạo kết nối | Không |
| Result cache | Kết quả search/lookup đã nhận trước đó | Có, khi cache hit |
| HTTP response cache | Response API đã tạo | Có thể, ở tầng HTTP |
| ORM/entity cache | Entity hoặc state do persistence framework quản lý | Phụ thuộc ORM/store |

Connection pool không phải cache dữ liệu. Dùng lại một LDAP connection vẫn phải gửi search operation để lấy entry mới. Ngược lại, result cache có thể trả dữ liệu mà không mở LDAP operation trong request đó.

Không nên tuyên bố tăng connection pool size là đã cache lookup. Cũng không nên dùng result cache để che một vấn đề connection leak hoặc pool exhaustion.

## 3. Những loại dữ liệu nào phù hợp để cache?

Không phải mọi kết quả LDAP đều nên cache như nhau:

| Dữ liệu | Khả năng cache | Lưu ý |
|---|---|---|
| Tên hiển thị, mã nhân viên | Thường phù hợp | Chọn TTL theo yêu cầu freshness |
| Thông tin phòng ban ít thay đổi | Có thể phù hợp | Evict sau provisioning/update |
| Resolve UID sang DN | Có thể phù hợp | Xóa khi rename/move/delete |
| Metadata schema ít thay đổi | Có thể phù hợp | Version theo schema/deployment |
| Group membership | Cần thận trọng | Có thể cache cho hiển thị UI; không dùng bản cache làm nguồn quyết định authorization |
| Account enabled/locked/expired | Không nên dùng cache làm quyết định đăng nhập | Bind/server policy phải được kiểm tra hiện thời |
| Authorization decision | Chỉ khi có policy version/revocation strategy rõ | Nếu không, quyền vừa bị thu hồi vẫn có thể được dùng |
| Password, bind credential | Không cache | Không lưu secret trong result cache |
| Raw LDAP context/connection | Không cache như dữ liệu ứng dụng | Quản lý qua connection pool/lifecycle |

Cache thông tin profile có thể là lựa chọn hợp lý. Cache kết quả xác thực hoặc trạng thái bảo mật thường tạo rủi ro lớn hơn lợi ích.

## 4. Chọn cache theo yêu cầu freshness

Trước khi đặt TTL, hãy trả lời:

1. Dữ liệu thay đổi thường xuyên đến mức nào?
2. Sau khi admin cập nhật, người dùng phải thấy thay đổi trong bao lâu?
3. Có thao tác nào cần đọc dữ liệu mới ngay sau khi write không?
4. Dữ liệu có ảnh hưởng đến đăng nhập, quyền hoặc quyết định bảo mật không?
5. Nếu directory replica trễ, cache có thể kéo dài trạng thái cũ thêm bao lâu?
6. Cache có nhiều instance hay chỉ một process?

Ví dụ policy:

| Loại dữ liệu | TTL minh họa | Cách làm mới |
|---|---:|---|
| Tên hiển thị | 1–5 phút | TTL + evict sau update |
| Resolve UID → DN | 15–60 giây | Evict sau rename/move |
| Group membership dùng cho UI | 10–30 giây | Evict khi membership thay đổi |
| Account status cho login | Không dùng result cache để quyết định bind | Xác minh với directory |
| Dữ liệu cần read-after-write | Bypass cache hoặc evict rồi đọc nguồn | Sau mutation thành công |

Các con số chỉ là điểm khởi đầu để benchmark. TTL thực tế phải dựa trên yêu cầu nghiệp vụ, khả năng invalidation, tải server và mức độ nhạy cảm của dữ liệu.

**TTL dài giảm số lần đọc LDAP nhưng kéo dài cửa sổ dữ liệu cũ. TTL ngắn giảm cửa sổ stale nhưng tăng tải và cache miss.**

## 5. Kiến trúc cache-aside cho Spring Data LDAP

Cache-aside là cách triển khai phổ biến:

1. Ứng dụng nhận yêu cầu tra cứu.
2. Xác định caller và directory scope được phép.
3. Tạo cache key từ scope và tiêu chí đã chuẩn hóa.
4. Đọc cache.
5. Nếu hit, kiểm tra authorization hiện hành rồi trả dữ liệu.
6. Nếu miss, thực hiện LDAP search trong base/scope được phép.
7. Map kết quả thành DTO phù hợp và cache nếu đủ điều kiện.
8. Sau write, evict các key bị ảnh hưởng hoặc phát sự kiện invalidation.

```text
HTTP request
    │
    ▼
Resolve authenticated principal
    │
    ▼
Resolve trusted directory scope
    │
    ▼
Authorize lookup
    │
    ▼
Build complete cache key
    │
    ▼
Cache lookup
    ├── HIT ──► Re-check resource authorization ──► Return
    │
    └── MISS
          │
          ▼
      LDAP search
          │
          ▼
      Map DTO
          │
          ▼
      Cache eligible result
          │
          ▼
        Return

LDAP write ──► successful mutation ──► evict/update cache
```

Không để cache lookup diễn ra trước khi ứng dụng xác định tenant/scope và quyền đọc. Nếu cache được truy vấn bằng key chỉ gồm UID, hai tenant có thể dùng chung entry cache khi cùng UID.

## 6. Cache key phải đại diện cho toàn bộ phạm vi truy vấn

Một cache key thiếu thành phần có thể trả sai dữ liệu. Với lookup theo UID, key thường cần thể hiện:

- Logical directory/partition đang truy vấn.
- Tenant hoặc scope ID đã được xác thực.
- Phiên bản scope/policy hoặc authorization version.
- UID đã normalize theo quy tắc của ứng dụng.
- Projection/schema version nếu các màn hình cache tập attribute khác nhau.
- Caller/role fingerprint nếu quyền đọc thực sự khác nhau theo caller.

Ví dụ key:

```java
public record PersonLookupKey(
        String directoryAlias,
        String scopeId,
        long authorizationVersion,
        String normalizedUid,
        String projectionVersion
) {}
```

Record có equality/hashCode theo các field nên có thể làm cache key trong Spring Cache. Các giá trị directoryAlias, scopeId và authorizationVersion phải được lấy từ security context hoặc scope resolver tin cậy, không nhận nguyên văn từ HTTP request.

Không nhất thiết phải đưa username vào key nếu mọi caller trong một scope có cùng quyền đọc dữ liệu profile và authorization được kiểm tra lại ở mỗi request. Nếu quyền khác nhau theo user/role, phải đưa security dimension tương ứng vào key hoặc tránh dùng chung cache cho kết quả đã lọc theo quyền.

### Tránh ghép key bằng chuỗi tùy tiện

Không nên làm:

```java
String key = tenantId + ":" + uid;
```

Nếu field chứa dấu phân cách, có thể tạo collision logic; đồng thời khó mở rộng version/scope. Dùng record key hoặc key generator có cấu trúc.

## 7. Authorization phải chạy ở mỗi request cache hit

Cache không tự chạy lại LDAP ACL. Điều này đặc biệt quan trọng khi ứng dụng bind bằng **một service account dùng chung**:

- LDAP server đánh giá ACL theo service account.
- Service account có thể đọc nhiều entry hơn một người dùng cuối.
- Cache giữ kết quả đã đọc bằng quyền rộng của service account.
- Nếu API trả cache trực tiếp, người dùng cuối có thể nhận dữ liệu mà họ không được phép xem.

Do đó, cần authorization ở tầng ứng dụng trước và sau cache lookup:

1. Xác định principal đã xác thực.
2. Resolve tenant/base DN từ principal.
3. Kiểm tra caller có quyền thực hiện loại lookup.
4. Đọc cache hoặc LDAP.
5. Kiểm tra caller có quyền đọc entry/field cụ thể.
6. Chỉ trả projection được phép.

Nếu LDAP ACL được đánh giá khác nhau theo từng user bind, cache dùng chung càng nguy hiểm. Không được dùng cache hit để thay thế một operation vốn cần thực hiện dưới identity của user. Trong trường hợp này, hoặc cache key phải phân biệt đầy đủ authorization identity và vẫn kiểm tra quyền hiện tại, hoặc không cache kết quả đó.

**Không cache authorization decision lâu hơn thời hạn thu hồi quyền mà hệ thống cam kết.** Nếu cần cache quyền, dùng policy version/epoch được tăng khi role, group hoặc ACL thay đổi và có invalidation đáng tin cậy.

## 8. Cấu hình Spring Cache với Caffeine

Spring Cache cung cấp abstraction như `@Cacheable`, `@CacheEvict` và `CacheManager`. TTL và eviction policy phụ thuộc cache provider. Với Caffeine, có thể đặt maximum size và expire-after-write:

```java
import java.time.Duration;
import java.util.List;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.annotation.EnableCaching;

@Configuration
@EnableCaching
public class DirectoryCacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        CaffeineCache peopleByUid = new CaffeineCache(
                "ldapPersonByUid",
                Caffeine.newBuilder()
                        .maximumSize(20_000)
                        .expireAfterWrite(Duration.ofSeconds(30))
                        .recordStats()
                        .build());

        CaffeineCache groupMembership = new CaffeineCache(
                "ldapGroupMembership",
                Caffeine.newBuilder()
                        .maximumSize(5_000)
                        .expireAfterWrite(Duration.ofSeconds(15))
                        .recordStats()
                        .build());

        SimpleCacheManager manager = new SimpleCacheManager();
        manager.setCaches(List.of(peopleByUid, groupMembership));
        return manager;
    }
}
```

Cần dependency Caffeine và Spring Cache trong ứng dụng. Với Spring Boot, có thể dùng cache starter phù hợp và cấu hình provider theo phiên bản dự án.

Trong ví dụ:

- maximumSize giới hạn số cache entry.
- expireAfterWrite đặt tuổi tối đa tính từ lần ghi cache.
- recordStats bật thống kê hit/miss/eviction của Caffeine.
- Hai cache có TTL khác nhau vì profile và group membership có mức độ nhạy freshness khác nhau.

Đây là cache cục bộ trong một JVM. Nếu chạy nhiều instance, mỗi instance có cache riêng; cấu hình Caffeine không tự đồng bộ invalidation giữa các node.

## 9. Cache lookup bằng @Cacheable

Ví dụ service đọc một profile theo UID trong scope đã được xác định:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Component;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public record PersonSummary(
        String uid,
        String commonName,
        String email) {}

@Component
public class CachedDirectoryPersonReader {

    private final LdapTemplate ldapTemplate;
    private final DirectoryScopeResolver scopeResolver;

    public CachedDirectoryPersonReader(
            LdapTemplate ldapTemplate,
            DirectoryScopeResolver scopeResolver) {
        this.ldapTemplate = ldapTemplate;
        this.scopeResolver = scopeResolver;
    }

    @Cacheable(
            cacheNames = "ldapPersonByUid",
            key = "#p0",
            unless = "#result == null")
    public PersonSummary find(PersonLookupKey key) {
        DirectoryScope scope =
                scopeResolver.resolve(key.scopeId());

        if (!scope.directoryAlias().equals(key.directoryAlias())
                || scope.authorizationVersion()
                        != key.authorizationVersion()) {
            throw new IllegalStateException(
                    "Directory scope version changed");
        }

        LdapQuery request = query()
                .base(scope.baseDn())
                .searchScope(scope.searchScope())
                .countLimit(2)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(key.normalizedUid());

        List<PersonSummary> matches =
                ldapTemplate.search(request, attrs ->
                        new PersonSummary(
                                read(attrs, "uid"),
                                read(attrs, "cn"),
                                read(attrs, "mail")));

        if (matches.size() > 1) {
            throw new IllegalStateException(
                    "UID is not unique in the selected scope");
        }

        return matches.isEmpty() ? null : matches.get(0);
    }

    private static String read(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null || attribute.size() == 0
                ? null
                : String.valueOf(attribute.get());
    }
}
```

`unless = "#result == null"` tránh lưu kết quả null trong cache này. Điều đó có nghĩa lookup không tìm thấy sẽ tiếp tục gọi LDAP ở lần sau. Nếu muốn negative caching, hãy thiết kế riêng với TTL ngắn và cân nhắc enumeration/race khi user vừa được tạo.

Một lưu ý về Spring proxy: method được cache phải được gọi qua Spring bean proxy. Gọi method find() từ một method khác trong cùng instance (self-invocation) có thể bỏ qua interceptor cache theo cấu hình proxy mặc định.

## 10. Xác định scope và quyền trước khi gọi cached reader

Cached reader ở phần trước chỉ nhận key. Một facade/service nên tạo key từ principal đã xác thực và kiểm tra quyền trên mỗi request:

```java
import java.security.Principal;
import org.springframework.stereotype.Service;

@Service
public class DirectoryPeopleLookup {

    private final DirectoryScopeResolver scopeResolver;
    private final DirectoryAuthorization authorization;
    private final CachedDirectoryPersonReader cachedReader;

    public DirectoryPeopleLookup(
            DirectoryScopeResolver scopeResolver,
            DirectoryAuthorization authorization,
            CachedDirectoryPersonReader cachedReader) {
        this.scopeResolver = scopeResolver;
        this.authorization = authorization;
        this.cachedReader = cachedReader;
    }

    public PersonSummary findByUid(
            Principal principal,
            String rawUid) {

        DirectoryScope scope =
                scopeResolver.requireReadScope(principal);

        authorization.requireCanSearchPeople(principal, scope);

        String uid = normalizeUid(rawUid);
        PersonLookupKey key = new PersonLookupKey(
                scope.directoryAlias(),
                scope.id(),
                scope.authorizationVersion(),
                uid,
                "person-summary-v1");

        PersonSummary person = cachedReader.find(key);

        if (person != null) {
            authorization.requireCanReadPerson(
                    principal, scope, person);
        }

        return person;
    }

    private static String normalizeUid(String rawUid) {
        if (rawUid == null || rawUid.isBlank()) {
            throw new IllegalArgumentException("UID is required");
        }
        String uid = rawUid.strip();
        if (uid.length() > 64) {
            throw new IllegalArgumentException("UID is too long");
        }
        return uid;
    }
}
```

DirectoryScopeResolver và DirectoryAuthorization là thành phần của ứng dụng, cần được triển khai theo security model thực tế. Điểm quan trọng là:

- scope được resolve từ principal, không từ tenantId tùy ý của request.
- Authorization chạy trước cache hit.
- Authorization resource-level chạy sau khi có entry.
- authorizationVersion thay đổi khi policy/scope liên quan thay đổi.
- Cached reader chỉ đọc đúng base DN mà scope resolver tin cậy cấp.

Spring Cache có thể bỏ qua toàn bộ method body khi cache hit. Vì vậy, việc resolve scope hiện tại và kiểm tra quyền không được chỉ đặt bên trong method có `@Cacheable`; facade phải thực hiện chúng ở mỗi request trước khi gọi cached reader. Việc kiểm tra resource-level sau khi nhận kết quả cũng phải chạy cho cả cache hit lẫn cache miss.

Nếu quyền đọc field khác nhau, DTO projection và cache key cũng phải phản ánh quyền đó; tốt hơn là chỉ cache một projection tối thiểu, rồi lọc field theo authorization hiện tại.

## 11. Cache kết quả search phức tạp khó hơn cache lookup theo ID

Một search động có thể phụ thuộc vào:

- Base DN.
- Search scope.
- LDAP filter.
- Sort keys.
- Page size và cookie.
- Attribute projection.
- Tenant và principal.
- Schema/version của directory.

Nếu cache key bỏ sót một thành phần, cache có thể trả kết quả của một query khác. Nếu đưa toàn bộ filter raw vào key, cache cardinality có thể tăng rất nhanh và chứa PII.

Khuyến nghị:

- Ưu tiên cache lookup theo identifier ổn định như UID hoặc DN.
- Chỉ cache search list nếu query shape có giới hạn và lặp lại đủ nhiều.
- Chuẩn hóa filter theo AST/criteria đã validate, không lấy raw filter từ client.
- Bao gồm base/scope, tenant, sort, projection và query version trong key.
- Không cache page có cookie như thể cookie là một query độc lập.
- Đặt maximum size và TTL ngắn cho cache search.
- Không cache browse toàn directory theo một key chung.

Với search có cardinality cao, cache hit rate có thể thấp hơn chi phí lưu key/result và invalidation.

## 12. Negative caching: cache kết quả không tìm thấy

Negative caching lưu trạng thái “không tìm thấy entry” trong một khoảng ngắn. Nó có thể giảm search lặp lại cho UID không tồn tại, nhưng cần cẩn trọng:

- Một user vừa được provision có thể vẫn bị coi là không tồn tại đến hết TTL.
- Kẻ tấn công có thể gửi nhiều UID ngẫu nhiên làm cache phình to.
- Cache negative result có thể trở thành một nguồn side-channel nếu public response khác nhau.
- Invalidation khi tạo entry phải xóa negative cache tương ứng.

Nếu dùng negative cache:

1. Dùng TTL ngắn hơn positive cache.
2. Giới hạn maximum size.
3. Rate limit lookup miss.
4. Trả public response trung tính.
5. Evict negative key ngay sau khi tạo entry thành công.
6. Không cache lỗi timeout, TLS hoặc directory unavailable như “user không tồn tại”.

Phân biệt **not found** với **directory unavailable**. Không biến lỗi hạ tầng thành negative cache.

## 13. Invalidation sau create, update, rename và delete

Cache-aside không tự biết directory đã thay đổi. Sau một write thành công, ứng dụng phải invalidation các key liên quan.

| LDAP mutation | Cache cần xem xét |
|---|---|
| Create person | Positive/negative lookup theo UID và DN mới |
| Update profile | UID, DN, profile projection và search list liên quan |
| Rename UID | Key UID cũ và UID mới |
| Move entry sang OU khác | Key theo scope cũ/mới, DN và các search cache |
| Delete person | UID, DN, group membership và negative cache |
| Add/remove group membership | Cache membership, group summary và authorization version |
| Thay đổi ACL/policy | Cache key/policy version và authorization cache |

Không chỉ evict key theo UID nếu cache còn lookup theo DN, email hoặc group membership. Cần có một registry các cache/key bị ảnh hưởng hoặc một chiến lược invalidation theo scope/version.

### Evict sau write thành công

Ví dụ:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Service;

@Service
public class DirectoryPersonWriter {

    private final PersonRepository repository;
    private final CacheManager cacheManager;

    public DirectoryPersonWriter(
            PersonRepository repository,
            CacheManager cacheManager) {
        this.repository = repository;
        this.cacheManager = cacheManager;
    }

    public void update(
            DirectoryPerson updated,
            PersonLookupKey oldKey,
            PersonLookupKey newKey) {

        repository.save(updated);

        Cache cache = cacheManager.getCache("ldapPersonByUid");
        if (cache != null) {
            cache.evict(oldKey);
            cache.evict(newKey);
        }
    }
}
```

Ví dụ giả định oldKey và newKey được tạo từ scope/version tin cậy và đại diện đúng cache projection. Trong code thật, nếu rename/move ảnh hưởng nhiều cache khác, hãy evict các key đó hoặc tăng scope generation để vô hiệu hóa cả nhóm.

LDAP write không tự trở thành transaction ACID nhiều entry. Với workflow nhiều bước, invalidation cần gắn với từng mutation đã thành công hoặc với trạng thái workflow cuối cùng được xác định rõ. Nếu một phần workflow đã thay đổi directory rồi bước sau thất bại, không được giữ cache cũ cho entry đã thay đổi.

## 14. TTL là backstop, không thay thế invalidation

TTL đảm bảo cache entry không tồn tại mãi, nhưng không thay thế invalidation sau write:

- Nếu TTL là 5 phút, người dùng có thể thấy dữ liệu cũ gần 5 phút.
- Nếu update thành công nhưng cache không evict, TTL chỉ giới hạn thời gian stale.
- Nếu cache key thiếu tenant hoặc scope, TTL không sửa được lỗi phân quyền.
- Nếu cache invalidation event bị mất, TTL là lớp phục hồi cuối cùng.

Chọn expireAfterWrite khi muốn giới hạn tuổi dữ liệu kể từ lần ghi cache. expireAfterAccess có thể giữ một entry nóng lâu hơn vì mỗi lần đọc lại làm mới thời điểm hết hạn; điều đó có thể kéo dài dữ liệu cũ ngoài dự kiến.

Có thể thêm jitter vào TTL hoặc refresh schedule để tránh hàng nghìn key hết hạn cùng lúc. Không dùng stale-while-revalidate cho account status, membership hoặc dữ liệu mà policy yêu cầu thu hồi tức thời.

## 15. Nhiều application instance cần invalidation phân tán

Với Caffeine local cache:

```text
Instance A ── Cache A
     │
     └────── LDAP directory

Instance B ── Cache B
     │
     └────── LDAP directory
```

Khi instance A cập nhật entry và chỉ evict Cache A, Cache B vẫn giữ dữ liệu cũ cho đến khi TTL hết hạn.

Các lựa chọn:

| Chiến lược | Ưu điểm | Giới hạn |
|---|---|---|
| Local cache + TTL ngắn | Đơn giản, latency thấp | Các instance có thể lệch nhau trong TTL |
| Publish invalidation event | Các instance xóa key gần đồng thời | Cần bảo đảm event delivery và xử lý duplicate |
| Distributed cache | Dữ liệu cache dùng chung | Thêm network dependency, security và vận hành |
| Version/generation key | Thay version làm key cũ không còn được dùng | Cần nguồn version nhất quán |
| Không cache dữ liệu nhạy freshness | Consistency đơn giản hơn | Tăng LDAP traffic |

Một event invalidation nên chứa logical directory alias, scope/entity identifier và version cần thay đổi; tránh phát raw password, full LDAP entry hoặc toàn bộ attribute nhạy cảm.

Nếu write thành công nhưng publish event thất bại, instance khác có thể giữ stale data. Có thể dùng retry/outbox ở tầng ứng dụng nếu có durable store phù hợp; TTL ngắn là backstop. Vì LDAP và database outbox thường không nằm trong cùng transaction, cần thiết kế reconciliation thay vì giả định atomic commit.

## 16. Race condition: cache fill cũ đến sau invalidation

Một tình huống khó:

1. Request A cache miss và bắt đầu LDAP search.
2. Request B update entry trên LDAP rồi evict cache.
3. Request A nhận response cũ từ replica hoặc search bắt đầu trước update.
4. Request A ghi kết quả cũ vào cache sau khi B đã evict.

Kết quả cũ sống lại sau invalidation.

Các cách giảm rủi ro:

- Dùng generation/version token trong cache key.
- Tăng generation sau write; response từ generation cũ không được ghi vào key hiện tại.
- Với dữ liệu cần read-after-write, bypass cache và đọc nguồn có thẩm quyền.
- Dùng write-through có kiểm soát nếu phù hợp.
- Giữ TTL ngắn làm giới hạn stale cuối cùng.
- Nếu cần consistency mạnh, không cache loại dữ liệu đó.

Một cache version có thể nằm trong key:

```java
public record ScopedCacheKey(
        String scopeId,
        long generation,
        String uid
) {}
```

Sau invalidation, tăng generation của scope. Các request mới dùng key generation mới; response cũ ghi vào generation cũ và không được request mới đọc. Cách này cần generation store có consistency phù hợp và cơ chế dọn key cũ.

## 17. Cache và LDAP replication

Ngay cả khi ứng dụng không dùng cache, directory có thể có nhiều replica/DC. Một write trên server A chưa chắc xuất hiện ngay trên server B.

Vì vậy, cần tách hai nguồn dữ liệu cũ:

- **Cache staleness:** ứng dụng trả kết quả đã lưu trước đó.
- **Replication lag:** LDAP replica trả dữ liệu chưa nhận thay đổi.

Evict cache rồi đọc replica chưa đồng bộ vẫn có thể nhận dữ liệu cũ. Nếu use case yêu cầu read-after-write:

- Đọc từ endpoint/server có thẩm quyền vừa ghi, nếu topology hỗ trợ.
- Bypass application cache.
- Có thể xác minh bằng version/modify timestamp phù hợp schema.
- Retry có giới hạn và có backoff khi replication delay là điều được chấp nhận.
- Không khẳng định một cache miss đồng nghĩa dữ liệu đã mới nhất.

Không dùng cache để che replication lag cho login, lockout hoặc quyền vừa bị thu hồi.

## 18. Cache stampede và tải tăng đột biến

Khi một key phổ biến hết TTL, nhiều request có thể cùng cache miss và cùng search LDAP. Đây là cache stampede.

Các biện pháp:

- Dùng cơ chế single-flight/synchronized loading phù hợp provider.
- Làm mới trước khi hết hạn cho dữ liệu profile không nhạy freshness.
- Thêm TTL jitter để tránh nhiều key hết hạn đồng thời.
- Giới hạn concurrency của refresh/search.
- Dùng backoff khi LDAP server đang quá tải.
- Có circuit breaker/timeout phù hợp cho dependency.
- Không retry vô hạn khi cache miss.

Một số provider hỗ trợ đồng bộ load theo key. `@Cacheable(sync = true)` có thể giảm duplicate load trong phạm vi cache manager/provider hỗ trợ, nhưng cần kiểm tra semantics và giới hạn của provider. Nó không đồng bộ load giữa các JVM nếu cache là local.

Không dùng stale data để vượt qua policy bảo mật chỉ nhằm giảm stampede.

## 19. Cache lỗi và dữ liệu nhạy cảm

Chỉ cache kết quả nghiệp vụ đã được xác định rõ. Tránh cache:

- Password hoặc bind credential.
- Raw Authentication object.
- DirContext hoặc LDAP connection.
- Exception, timeout và TLS failure như thể là kết quả rỗng.
- Account locked/disabled/expired làm căn cứ duy nhất cho quyết định login.
- Authorization decision mà không có policy version và revocation model.
- Entry đầy đủ nếu API chỉ cần một projection nhỏ.

DTO cache nên bất biến, chỉ chứa các field cần dùng và có retention phù hợp. Với dữ liệu nhạy cảm, đánh giá memory dump, heap dump, backup, distributed cache encryption, access control và log key. Cache in-memory vẫn có thể xuất hiện trong heap dump.

Nếu cache chứa PII, hãy giảm field, TTL và quyền truy cập; không log cache key hoặc giá trị nguyên vẹn nếu chúng chứa UID/email.

## 20. Đo hiệu quả cache thay vì chỉ bật cache

Theo dõi:

- Hit rate và miss rate theo cache name.
- Eviction/expiration count.
- Load duration và LDAP search latency.
- Số LDAP search được giảm.
- Cache size/estimated weight.
- Số lỗi load và timeout.
- Số invalidation event được phát/nhận.
- Độ trễ từ LDAP write đến cache invalidation trên các instance.
- Tỷ lệ request phải bypass cache vì freshness/authorization.

Không dùng username, DN, email, tenant ID hoặc raw filter làm metric label có cardinality cao. Chỉ dùng label có tập giá trị hữu hạn như `cache=person|group`, `outcome=hit|miss|load_error` và `directory=primary|secondary`.

Cần so sánh latency p50/p95/p99 trước và sau khi cache, cùng với LDAP server load. Hit rate cao chưa chắc tốt nếu dữ liệu stale hoặc cache invalidation lỗi.

## 21. Kiểm thử freshness, invalidation và phân quyền

### Unit test

- Cùng scope, UID và projection tạo cùng key.
- Hai tenant có cùng UID nhưng tạo key khác nhau.
- Hai authorization version khác nhau không dùng chung entry.
- Cache hit vẫn chạy authorization facade.
- UID rỗng/quá dài bị từ chối trước lookup.
- Lookup không tìm thấy không bị negative-cache ngoài ý muốn.
- Update evict key cũ và key mới khi rename.
- Delete evict profile, DN và các cache liên quan.
- Không cache timeout/TLS/directory unavailable.
- Bypass path không đọc cache cho use case read-after-write.

### Integration test với LDAP test server

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Lần đọc đầu tiên | Cache miss và LDAP search được gọi |
| Đọc lần thứ hai cùng key | Cache hit, không có search lặp |
| Hết TTL | Cache miss và dữ liệu được nạp lại |
| Update qua service | Key bị evict sau write thành công |
| Rename UID | Cả UID cũ và mới được xử lý đúng |
| Delete entry | Cache không tiếp tục trả profile đã xóa |
| Hai tenant cùng UID | Không rò dữ liệu chéo |
| Caller mất quyền | Cache hit không vượt authorization |
| Authorization version đổi | Key cũ không được dùng cho policy mới |
| Replica lag | Bypass cache vẫn có thể thấy replica cũ; test ghi rõ behavior |
| Nhiều instance | Invalidation event làm cache node khác evict |
| Event bị mất | TTL/reconciliation giới hạn thời gian stale |
| Concurrent miss | Không tạo load amplification vượt policy |
| Directory timeout | Không cache lỗi như not found |
| Heap/log inspection | Không thấy password hoặc raw credential |

### Kiểm thử thời gian stale

Định nghĩa một yêu cầu cụ thể, ví dụ “profile thông thường có thể stale tối đa 30 giây trong điều kiện event invalidation hoạt động”. Sau đó test:

1. Đọc profile và tạo cache entry.
2. Cập nhật entry qua write service.
3. Kiểm tra instance hiện tại evict ngay sau write thành công.
4. Kiểm tra instance khác nhận invalidation event.
5. Tắt event consumer để xác minh TTL là backstop.
6. Đo thời gian đến khi dữ liệu mới xuất hiện.
7. Ghi rõ giới hạn nếu replica lag dài hơn cache TTL.

Không tuyên bố consistency mạnh hơn những gì test và topology chứng minh.

## 22. Bài tập thực hành

Một ứng dụng nhân sự dùng Spring Data LDAP. Trang hồ sơ hiển thị `uid`, `cn`, `mail` và `departmentNumber`. Cùng một profile được đọc nhiều lần; admin có thể cập nhật phòng ban, đổi UID hoặc xóa tài khoản. Ứng dụng chạy ba instance và dùng một service account để đọc LDAP.

Hãy thiết kế:

1. DTO bất biến chỉ chứa các field cần cho trang hồ sơ.
2. Cache key gồm directory alias, scope/tenant ID, authorization version, UID và projection version.
3. Scope resolver lấy base DN từ principal đã xác thực.
4. Authorization trước cache lookup và kiểm tra resource-level sau cache hit.
5. Caffeine cache có maximum size và TTL phù hợp.
6. `@Cacheable` chỉ cache kết quả profile hợp lệ.
7. Write service evict UID/DN cũ và mới sau mutation thành công.
8. Invalidation event để hai instance còn lại evict cache.
9. TTL làm backstop nếu event delivery thất bại.
10. Read-after-write path bypass cache hoặc đọc từ server có thẩm quyền.
11. Không cache password, bind result, account lockout hoặc authorization decision lâu dài.
12. Unit/integration test cho cross-tenant, revoke permission, rename, delete, replica lag và concurrent miss.

**Câu hỏi tự đánh giá:**

- Connection pool khác result cache ở đâu?
- Vì sao cache key chỉ gồm UID không an toàn trong ứng dụng đa tenant?
- Vì sao authorization phải được kiểm tra lại khi cache hit?
- `expireAfterWrite` khác `expireAfterAccess` như thế nào?
- Vì sao negative cache cần TTL ngắn và invalidation khi create?
- Vì sao evict local cache trên instance A chưa đủ cho ba instance?
- Cache invalidation race có thể làm dữ liệu cũ sống lại như thế nào?
- Vì sao cache miss không bảo đảm đọc được dữ liệu mới nhất từ replica?

## 23. Checklist trước khi phát hành

- [ ] Đã xác định dữ liệu nào được cache và dữ liệu nào không được cache.
- [ ] Đã phân biệt connection pool với result cache.
- [ ] Cache key bao gồm directory, tenant/scope, authorization version và query/projection dimensions cần thiết.
- [ ] Scope/base DN đến từ principal hoặc resolver tin cậy, không từ request tùy ý.
- [ ] Authorization chạy ở mỗi request, kể cả cache hit.
- [ ] Không dùng cache để thay thế LDAP ACL hoặc user bind.
- [ ] Không cache password, credential hoặc bind result.
- [ ] Không dùng cache account status/authorization để quyết định bảo mật nếu freshness không được bảo đảm.
- [ ] TTL được chọn từ yêu cầu stale tolerance và có maximum size.
- [ ] Có invalidation sau create/update/rename/move/delete/group membership change.
- [ ] Xử lý cả key cũ và key mới khi rename/move.
- [ ] Nhiều instance có distributed invalidation hoặc chấp nhận stale window được ghi rõ.
- [ ] Có TTL/reconciliation làm backstop khi event invalidation thất bại.
- [ ] Có phương án giảm cache stampede.
- [ ] Negative cache có TTL ngắn và không cache lỗi hạ tầng.
- [ ] Read-after-write có bypass/cache eviction và nguồn đọc phù hợp replication topology.
- [ ] Không cache raw LDAP context, connection hoặc exception.
- [ ] Cache DTO chỉ chứa field cần thiết và bảo vệ PII.
- [ ] Metrics không dùng UID/DN/email làm label.
- [ ] Có test cross-tenant, permission revoke, invalidation, TTL, replica lag và multi-instance.
- [ ] Đã đo hit rate, LDAP latency, p95/p99 và thời gian stale thực tế.

### Tài liệu tham khảo

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html) — `@Cacheable`, `@CacheEvict`, cache key và `CacheManager`.
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html) — cấu hình cache provider trong ứng dụng Spring Boot.
- [Caffeine — User Guide](https://github.com/ben-manes/caffeine/wiki) — size-based eviction, expiration và statistics.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — `LdapTemplate`, context source và repository abstractions.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — search, update và LDAP operation semantics.
- [OWASP Cheat Sheet Series — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — kiểm tra quyền ở mọi request và nguyên tắc least privilege.

**Kết luận:** cache LDAP có thể giảm search lặp và latency, nhưng chỉ an toàn khi cache key đại diện đầy đủ cho directory scope và query, authorization được kiểm tra ở mỗi request, TTL phản ánh mức stale được chấp nhận và write path invalidation đúng các key liên quan. Với nhiều instance, cần cơ chế invalidation phân tán hoặc chấp nhận stale window có giới hạn. Không cache credential, bind result hay quyết định bảo mật như dữ liệu profile; khi cần read-after-write hoặc trạng thái tài khoản hiện thời, hãy bypass cache và xác minh với directory phù hợp.
