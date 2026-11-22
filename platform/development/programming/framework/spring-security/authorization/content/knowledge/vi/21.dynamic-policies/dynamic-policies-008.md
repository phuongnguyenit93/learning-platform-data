# Cache quyết định có thời hạn và vô hiệu hóa khi quyền thay đổi

## 1. Mục tiêu và bối cảnh

Trong Spring Security Authorization, một quyết định như **“Alice có được đọc Document #42 không?”** có thể cần tra database ACL, nhóm quyền, chính sách động hoặc một Policy Decision Point (PDP) bên ngoài. Nếu lặp lại cùng một phép kiểm tra ở mọi request, hệ thống tốn nhiều truy vấn và tăng độ trễ. **Cache quyết định phân quyền** lưu tạm kết quả `ALLOW` hoặc `DENY` để dùng lại khi tất cả điều kiện liên quan vẫn còn hiệu lực.

Nhưng một câu trả lời `ALLOW` đúng lúc 10:00 không nhất thiết còn đúng lúc 10:01: quản trị viên có thể **thu hồi quyền**, người dùng bị xóa khỏi nhóm, tài liệu đổi owner, tenant membership bị hủy hoặc policy mới được triển khai. Cache giúp tăng hiệu năng, đồng thời có thể biến quyết định cũ thành **lỗ hổng truy cập** nếu không có thời hạn và cơ chế vô hiệu hóa.

Bài thuộc nhóm **Chính sách động** của module Spring Security Authorization. Sau bài này, bạn có thể:

1. Phân biệt cache **quyết định authorization** với cache dữ liệu, session/JWT, quyền role và Spring Security ACL cache.
2. Thiết kế cache key theo **tenant + subject ổn định + action + resource type/ID + policy version** thay vì chỉ username hoặc resource ID.
3. Dùng TTL cho cả `ALLOW` và `DENY`, và hiểu **TTL là giới hạn độ cũ, không bảo đảm thu hồi ngay**.
4. Invalidate khi quyền được grant/revoke, resource/owner/ACL cha thay đổi, role/membership thay đổi hoặc policy được triển khai.
5. Giải thích cách phối hợp **transaction commit → event → invalidation**, xử lý trễ/mất event, nhiều instance và các race condition.
6. Đo hit/miss, số lần tính quyết định, độ trễ, stale-decision window và phát hiện failure mode.
7. Chạy project Java 17+ với Spring Method Security thật, cache TTL có đồng hồ giả và JUnit 5 kiểm thử grant/revoke/expiry/tenant isolation/fail closed.
8. Xác định khi nào **không được dùng cache lâu**, hoặc phải kiểm tra trực tiếp authoritative store tại thời điểm thao tác nhạy cảm.

**Phạm vi:** Java 17+, Spring Boot BOM 3.5.x, Spring Security 6.5.x, Spring Test/JUnit 5. Ví dụ cache trong RAM dùng `ConcurrentHashMap` để làm rõ cơ chế; production nên dùng một thư viện cache có `maximumSize`, TTL, metrics và invalidation phù hợp như Caffeine hoặc một kiến trúc phân tán có kiểm soát.

## 2. Cache điều gì, và quyết định phụ thuộc dữ liệu nào?

Ví dụ: `Document#42` của `TENANT_A`; Alice có quyền `READ`, nhưng không có quyền `WRITE`. Một quyết định có thể phụ thuộc vào:

- **Subject:** danh tính ổn định `issuer + subject` đã xác thực; không chỉ `username` vì hai tenant có thể cùng username.
- **Tenant:** tenant đã được server xác nhận; không lấy giá trị tùy ý từ request header.
- **Action:** `READ`, `WRITE`, `DELETE`, `APPROVE`, `EXPORT` là các hành động có policy độc lập.
- **Resource:** loại `Document`, ID, tenant của tài nguyên, owner, trạng thái, độ nhạy, quan hệ ACL cha.
- **Policy:** version/epoch của ACL, phiên bản quy tắc tổ chức, role hierarchy, nhóm quyền, tenant membership.
- **Context:** thời gian, IP/device assurance, mức xác thực, số tiền giao dịch, legal hold, workflow hoặc những thuộc tính thay đổi từng request.

Không phải mọi yếu tố nên được cache. Với policy có điều kiện thay đổi liên tục, tốt hơn là **chỉ cache phần bất biến/ít thay đổi** rồi kiểm tra lại điều kiện động ở mỗi lời gọi. Nếu policy dùng thời gian hiện tại, IP, trạng thái account hoặc dữ liệu vừa thay đổi, phải đưa chúng vào khóa hoặc loại khỏi phần quyết định được cache.

### 2.1. Sơ đồ đường đi

```text
Caller -> Spring-managed service proxy
                 |
                 v
   @PreAuthorize("hasAuthority('DOC_READ') and
                  @decisionPolicy.can(authentication, #id, 'READ')")
                 |
                 v
           Trusted principal?
            /           \
        invalid          valid
          |                |
        DENY               v
                Cache key = tenant + issuer/sub +
                            action + resource type/id +
                            policy revision
                             |
                     +-------+-------+
                     |               |
                 HIT & fresh     MISS/expired
                     |               |
                     v               v
               ALLOW / DENY      Authoritative policy
                                     |
                                ALLOW / DENY
                                     |
                             cache with TTL
                                     |
                                     v
                              decision returned
```

Khi có thay đổi quyền:

```text
Admin đổi ACL/role/owner  --transaction--> COMMIT
                                           |
                                           v
                                  policy version tăng
                                           |
                                           v
                              gửi invalidation event
                                           |
                         +-----------------+-----------------+
                         |                 |                 |
                      node A            node B            node C
                      evict             evict             evict
                         |                 |                 |
                         +------------ next request ----------+
                                           |
                                           v
                                 tính lại quyết định
```

**Lưu ý:** các event và cache tại nhiều node có thể bị trễ hoặc mất. Thêm TTL chỉ bảo đảm quyết định hết hạn sau một khoảng thời gian **theo đồng hồ của node**; nó không tự bảo đảm toàn hệ thống thấy revoke tức thì.

## 3. Thiết kế cache key: không được chia sẻ nhầm kết quả

### 3.1. Khóa tối thiểu cho policy minh họa

```java
record ResourceKey(
    String tenant, String resourceType, long resourceId
) {}

record SubjectKey(
    String tenant, String issuer, String subject
) {}

record DecisionKey(
    ResourceKey resource,
    SubjectKey actor,
    String action,
    long policyRevision
) {}
```

Đây là các Java `record` có thể biên dịch trong project Java 17+, dùng ở ví dụ test hoàn chỉnh phía dưới.

| Thành phần key | Vì sao bắt buộc trong tình huống này? |
| --- | --- |
| `tenant` của resource | `Document#42` ở A khác `Document#42` ở B |
| `resourceType` | `Document#42` khác `Invoice#42` |
| `resourceId` | Phân biệt các đối tượng cùng type |
| `tenant` của actor | Người thuộc A không nhận cache của B |
| `issuer + subject` | Tên `alex` có thể trùng giữa nhiều identity provider/tenant |
| `action` | `READ` không được dùng lại cho `WRITE` hay `EXPORT` |
| `policyRevision` | Quyền đã thay đổi phải dùng thế hệ cache khác |

Nếu policy còn phụ thuộc `roleSet`, mức MFA, owner, trạng thái workflow, thời gian hoặc request context, **key trên chưa đủ**. Có thể đưa `authorizationEpoch`/session/role version vào key hoặc kiểm tra các điều kiện đó bên ngoài cache. Đừng biến mọi claim/request thành một key phức tạp không kiểm soát: hãy xác định **đúng phạm vi cacheable** bằng threat model.

### 3.2. Những khóa sai thường gặp

```java
// SAI: hai tenant cùng resource ID có thể dùng chung quyết định.
String key1 = "document:42";

// SAI: username không nhất thiết là user identity toàn cục.
String key2 = "alex:document:42";

// SAI: READ và WRITE có chính sách khác nhau.
String key3 = "TENANT_A:alice:document:42";

// SAI nếu role/policy mới thay đổi mà revision không đổi:
String key4 = "A:alice:document:42:READ";
```

Cũng không được để client gửi sẵn `cacheKey` hoặc `tenantId` để server dùng trực tiếp. Key phải được dựng từ **Authentication đã được xác thực** và resource đã được xác định từ nguồn tin cậy.

### 3.3. Không cache bản ghi dữ liệu như quyết định

Một cache `ALLOW`/`DENY` **khác** cache response body hoặc entity. Sau khi authorization cho phép, việc trả tài liệu vẫn phải lấy theo đúng tenant/resource, áp dụng field redaction và kiểm tra policy bổ sung nếu cần. Nếu cache dữ liệu chỉ theo `id=42`, dù decision cache đúng, endpoint vẫn có thể trả nhầm body của tenant khác.

`AclCache` của Spring Security ACL có nhiệm vụ cache ACL object, **không tự đồng nghĩa** với một cache Boolean `hasPermission`. Hai lớp có TTL/invalidation khác nhau; revoke phải làm cả dữ liệu ACL và quyết định đã tính bị làm mới đúng thời điểm.

## 4. TTL: giới hạn độ cũ, không thay thế revoke event

### 4.1. Cơ chế và lựa chọn TTL

Một entry thông thường:

```text
key       = (TENANT_A, issuer-a/user-123, READ, Document#42, rev=7)
decision  = ALLOW
createdAt = 10:00:00
expiresAt = 10:00:05
```

Nếu hiện tại **trước** `expiresAt`, entry có thể được dùng lại; đến đúng thời điểm expiry hoặc sau đó phải tính lại. Ví dụ test dùng đồng hồ `Clock` giả nên kiểm tra được biên thời gian mà không phải `Thread.sleep`.

Một lựa chọn minh họa:

- **ALLOW TTL = 5 giây**.
- **DENY TTL = 2 giây**: quyền mới được cấp có thể sớm được thấy hơn khi event grant bị chậm.
- Với quyết định tài chính/nhạy cảm, TTL còn ngắn hơn hoặc **bỏ cache và recheck authoritative source** trước commit.
- TTL phải có giới hạn trên và chính sách quan trắc; không mặc định `ALLOW` có thể sống đến hết JWT/session.
- Kích thước cache phải được giới hạn để tránh key cardinality quá lớn và memory exhaustion.

Các số 5s/2s ở đây là **cấu hình học tập**, không phải giá trị chuẩn cho mọi sản phẩm. Nếu yêu cầu “thu hồi quyền có hiệu lực tối đa sau 1 giây”, TTL 5 giây **không đủ** khi không có cơ chế invalidation đáng tin cậy.

### 4.2. Những điều TTL không bảo đảm

- Không thu hồi tức thì khi admin vừa revoke.
- Không hủy một request đã qua authorization và đang thực thi.
- Không đồng bộ cache giữa nhiều instance.
- Không phát hiện token/JWT đã bị thu hồi nếu ứng dụng chỉ dựa vào authority nằm trong token cũ.
- Không thay đổi kết quả của một quyết định đã được cache dựa trên dữ liệu sai.
- Không tự bảo đảm **wall-clock** chính xác; production nên dùng clock/ticker monotonic của thư viện cache cho thời gian hết hạn và test clock phù hợp.

**Khi expiry quá dài:** stale `ALLOW` cho phép truy cập trái phép sau revoke. **Khi expiry quá ngắn:** tăng hit rate của database/PDP, giảm lợi ích hiệu năng và có thể gây “cache stampede”.

## 5. Invalidation: khi nào phải xóa hoặc đổi version?

Các sự kiện nên xem xét:

| Sự kiện | Phạm vi invalidation cần đánh giá |
| --- | --- |
| Grant/revoke ACE cho tài liệu | Mọi decision trên resource đó, các action/SID liên quan |
| Đổi owner hoặc trạng thái DRAFT→APPROVED | Resource và các quyền phụ thuộc owner/state |
| Thay parent ACL hoặc `entriesInheriting` | Child và các descendant phụ thuộc kế thừa |
| Role/group membership của Alice thay đổi | Các quyết định dựa trên authority/nhóm của Alice; token cũ cần xử lý riêng |
| Tenant membership bị thu hồi | Mọi quyết định actor–tenant liên quan, cả session/token/DB scope |
| Policy code/config đổi phiên bản | Invalidate theo policy version/epoch hoặc clear có kiểm soát |
| Resource bị xóa/chuyển tenant | Quyết định cho resource cũ, key mới và dữ liệu cached |
| Mức độ nhạy cảm, export approval thay đổi | Quyết định READ/EXPORT và field-level projection liên quan |
| Emergency user suspension | Không chờ TTL bình thường; chặn qua authoritative gate/denylist |

### 5.1. Hai kỹ thuật thường kết hợp

**Chủ động evict:** sau cập nhật thành công, xóa cache theo resource/subject/policy. Có thể dùng `cache.invalidate(resource)`, topic Pub/Sub, message bus hoặc framework cache eviction.

**Version/epoch:** key chứa phiên bản chính sách. Khi quyền thay đổi, version của resource/policy/subject tăng. Request sau dùng key mới nên không thể khớp `ALLOW` ở version cũ.

```text
Trước revoke: key = (... Document#42, revision=7) -> ALLOW
Sau revoke:   key = (... Document#42, revision=8) -> MISS -> DENY
```

Điều kiện **rất quan trọng**: mọi node phải biết **revision mới** một cách đáng tin và đủ nhanh. Nếu revision chỉ lưu trong RAM node A, node B không biết nó đổi và vẫn có thể dùng cached `ALLOW`. Versioning **không tự giải quyết distributed consistency**; trong nhiều hệ thống cần revision lấy từ authoritative store hoặc event/stream có version, cùng cơ chế xử lý event bị bỏ lỡ.

### 5.2. Tại sao nên evict sau commit?

Nếu một transaction thay ACL rồi publish invalidation **trước commit**, node khác có thể cache-miss và đọc lại **quyền cũ**, sau đó cache kết quả cũ ngay khi transaction cuối cùng commit. Nếu transaction rollback, invalidation trước commit cũng tạo churn vô ích.

Mô hình nên cân nhắc:

```text
BEGIN
  UPDATE acl_entries ...
  UPDATE permission_revision ...
  INSERT INTO outbox(permission-changed, revision=8)
COMMIT
  -> outbox publisher / after-commit callback
  -> subscribers evict hoặc tăng revision
  -> monitoring/ack/retry
```

Outbox giúp giảm nguy cơ DB commit thành công nhưng process chết trước khi phát event. Tuy nhiên, subscriber vẫn có thể trễ; TTL và version/strong reads là lớp dự phòng. Với quyền cực nhạy cảm, có thể cần đọc trực tiếp authoritative revision trên mỗi request hoặc xử lý đồng bộ và chấp nhận chi phí.

### 5.3. Event trễ, mất, trùng hoặc đảo thứ tự

- **Mất event:** TTL chặn việc cache sống mãi; nếu yêu cầu revoke tức thì thì TTL không đủ.
- **Trùng event:** invalidation phải idempotent.
- **Đảo thứ tự:** gắn revision tăng đơn điệu; không áp dụng một snapshot quyền cũ lên snapshot mới.
- **Node vừa khởi động:** không nhận các event quá khứ thì cache lúc đầu nên rỗng; nếu tải snapshot, phải có revision gắn kèm.
- **Concurrent miss:** nhiều request cùng miss có thể cùng đánh PDP; dùng `cache.get(key, loader)` đồng bộ/coalescing để giảm stampede.
- **Race invalidate-vs-load:** một loader cũ có thể trả về sau khi revoke. Version token từ nguồn đáng tin hoặc invalidation sequencing mới giải quyết triệt để; không tự khẳng định `cache.evict()` đơn lẻ là tuyến tính hóa mọi request.

## 6. Quy tắc cache quyết định an toàn

1. **Deny by default:** principal không hợp lệ, tenant sai, resource không tồn tại, thiếu permission hay nguồn policy lỗi => không cấp quyền.
2. **Check authority mỗi request:** trong Spring dùng `hasAuthority` bên ngoài phần cache; không dùng cached `ALLOW` để bỏ qua toàn bộ authentication hoặc status account.
3. **Chỉ cache kết quả thành công:** lỗi network/PDP không phải `ALLOW`. Nếu cache `DENY` do lỗi, cần ghi rõ semantics/TTL riêng, tránh làm outage bị che giấu.
4. **Key đầy đủ:** resource, tenant, actor issuer/sub, action, policy version; thêm role/membership/assurance version nếu policy phụ thuộc.
5. **Bounded cache:** giới hạn size, TTL, metric, không lưu raw JWT/PII vào key dễ bị log; có thể dùng opaque stable IDs.
6. **Không cho user tự invalidate hoặc tự chọn policy revision**: management event chỉ từ nguồn đã xác thực.
7. **Thay đổi quyền phải có audit:** người sửa, target, old/new permissions, revision, commit time, node nhận invalidation.
8. **Một lời gọi WRITE/APPROVE nhạy cảm cần kiểm tra ở thời điểm ghi:** `@PreAuthorize` dùng cache chỉ là một lớp, phải có conditional update/version/transaction phù hợp.
9. **Giải thích stale window bằng SLO:** ví dụ maximum stale grant, propagation P99, detection alert; không dùng khái niệm “cache mới” mơ hồ.
10. **Tách cache policy khỏi cache dữ liệu** và bảo vệ cả hai đường. Invalidate decision không tự xóa document payload cached.

## 7. Tích hợp với Spring Security Method Security

Với Spring Security 6.5, `@EnableMethodSecurity` kích hoạt interceptor cho `@PreAuthorize` trên Spring-managed bean. SpEL có thể gọi một bean Java:

```java
@PreAuthorize(
    "hasAuthority('DOC_READ') and " +
    "@decisionPolicy.can(authentication, #id, 'READ')"
)
public String read(@P("id") long id) {
    return repository.findAllowedDocument(id);
}
```

Đây là **fragment**, chưa phải chương trình độc lập. `decisionPolicy` cần bean được đăng ký với tên đó; `@P("id")` xác định parameter name cho SpEL. `authentication` là đối tượng do Spring Security cung cấp cho expression.

Đừng dùng chỉ:

```java
@Cacheable(cacheNames = "decisions", key = "#id")
public boolean canRead(long id) { ... }
```

Đó là **anti-pattern**: key thiếu actor, tenant, action, version; chưa kể `@Cacheable` và method security đều dùng AOP nên thứ tự advice, self-invocation và điều kiện cache phải được kiểm thử.

Nếu dùng Spring Cache/Caffeine, có thể dùng key builder thống nhất và `@CacheEvict` hoặc API invalidate được gọi sau commit. **Spring Security không tự cache mọi kết quả `@PreAuthorize`** chỉ vì bạn bật Method Security. Cache decision là logic ứng dụng/PDP, khác với SecurityContext/session cache.

## 8. Project Java 17+ chạy được, TTL kiểm thử bằng đồng hồ giả

Project test dùng **Spring Method Security thật**, không mock interceptor, nhưng policy store và document repository **in-memory** để tập trung vào cache. Nó minh họa:

- Hai resource cùng ID 42 ở hai tenant; hai người cùng tên `alex` có subject khác nhau.
- Key chứa tenant + issuer/sub + action + type/ID + revision.
- TTL ALLOW 5s, DENY 2s; test đồng hồ giả `Clock`, không cần `Thread.sleep`.
- Admin grant/revoke tạo revision mới và invalidate decision theo resource.
- Test giả lập **mất invalidation** trong cùng JVM; revision mới vẫn buộc cache miss.
- Test authority gate, no-rule, lỗi policy source, cache hit/miss, isolation và không có side effect khi deny.

**Giới hạn thiết kế:** version map/decision cache nằm trong **một JVM**; production nhiều node phải phân phối invalidation/revision. `ConcurrentHashMap` trong ví dụ có giới hạn đơn giản bằng clear toàn bộ khi đầy; nó **không phải** eviction algorithm production, cũng không chống mọi race như một distributed transaction.

### 8.1. Cấu trúc dự án

```text
decision-cache-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/DecisionCacheSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'decision-cache-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Đây là project chỉ dùng `src/test/java`: `testImplementation` là đủ. Nếu chuyển thành ứng dụng thật, dependencies Spring Security/Context ở `implementation` và cache ở runtime phù hợp. Java 17 là tối thiểu cho `record`; không dùng API preview.

### 8.2. Tệp Java integration test hoàn chỉnh

Tạo `src/test/java/demo/DecisionCacheSecurityTest.java`:

```java
package demo;

import java.security.Principal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(DecisionCacheSecurityTest.Config.class)
public class DecisionCacheSecurityTest {

    private static final String ISSUER = "https://idp.example.test";

    public record Actor(
        String tenant, String issuer, String subject, String username
    ) implements Principal {
        @Override
        public String getName() {
            return username;
        }
    }

    public record ResourceKey(
        String tenant, String type, long id
    ) {}

    public record SubjectKey(
        String tenant, String issuer, String subject
    ) {}

    public record GrantKey(
        ResourceKey resource, SubjectKey actor, String action
    ) {}

    public record DecisionKey(
        ResourceKey resource, SubjectKey actor,
        String action, long revision
    ) {}

    public record Entry(boolean allowed, Instant expiresAt) {}

    private static final Actor ALICE = new Actor(
        "TENANT_A", ISSUER, "subject-a", "alex");

    private static final Actor BOB = new Actor(
        "TENANT_B", ISSUER, "subject-b", "alex");

    private static final Actor IMPOSTOR = new Actor(
        "TENANT_A", ISSUER, "other-subject", "alex");

    private static final Actor ADMIN = new Actor(
        "TENANT_A", ISSUER, "policy-admin", "admin");

    private static ResourceKey doc(String tenant, long id) {
        return new ResourceKey(tenant, "Document", id);
    }

    private static SubjectKey subject(Actor actor) {
        return new SubjectKey(
            actor.tenant(), actor.issuer(), actor.subject());
    }

    public static class TestClock extends Clock {
        private final AtomicReference<Instant> current =
            new AtomicReference<>(Instant.parse(
                "2030-01-01T00:00:00Z"));

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            if (!ZoneOffset.UTC.equals(zone)) {
                throw new IllegalArgumentException(
                    "Demo supports only UTC");
            }
            return this;
        }

        @Override
        public Instant instant() {
            return current.get();
        }

        void reset() {
            current.set(Instant.parse(
                "2030-01-01T00:00:00Z"));
        }

        void advance(Duration duration) {
            current.updateAndGet(t -> t.plus(duration));
        }
    }

    public static class Documents {
        private final Map<ResourceKey, String> bodies =
            new ConcurrentHashMap<>();

        void reset() {
            bodies.clear();
            bodies.put(doc("TENANT_A", 42), "A private 42");
            bodies.put(doc("TENANT_B", 42), "B private 42");
            bodies.put(doc("TENANT_A", 43), "A document 43");
        }

        Optional<String> read(ResourceKey resource) {
            return Optional.ofNullable(bodies.get(resource));
        }

        void write(ResourceKey resource, String newBody) {
            if (!bodies.containsKey(resource)) {
                throw new AccessDeniedException("Not visible");
            }
            bodies.put(resource, newBody);
        }
    }

    public static class RuleStore {
        private final Documents documents;
        private final Map<GrantKey, Boolean> grants =
            new ConcurrentHashMap<>();
        private final Map<ResourceKey, AtomicLong> revisions =
            new ConcurrentHashMap<>();
        private final AtomicInteger evaluations =
            new AtomicInteger();
        private final AtomicBoolean available =
            new AtomicBoolean(true);

        RuleStore(Documents documents) {
            this.documents = documents;
        }

        void reset() {
            grants.clear();
            revisions.clear();
            evaluations.set(0);
            available.set(true);
            grant(doc("TENANT_A", 42), subject(ALICE), "READ");
            grant(doc("TENANT_B", 42), subject(BOB), "READ");
            grant(doc("TENANT_A", 43), subject(ALICE), "READ");
        }

        long revision(ResourceKey key) {
            AtomicLong current = revisions.get(key);
            return current == null ? 0L : current.get();
        }

        private void bump(ResourceKey resource) {
            revisions.computeIfAbsent(
                resource, ignored -> new AtomicLong()
            ).incrementAndGet();
        }

        void grant(
                ResourceKey resource, SubjectKey actor,
                String action) {
            grants.put(
                new GrantKey(resource, actor, action),
                Boolean.TRUE);
            bump(resource);
        }

        void revoke(
                ResourceKey resource, SubjectKey actor,
                String action) {
            grants.remove(new GrantKey(resource, actor, action));
            bump(resource);
        }

        boolean evaluate(
                ResourceKey resource, SubjectKey actor,
                String action) {
            evaluations.incrementAndGet();
            if (!available.get()) {
                throw new IllegalStateException(
                    "Policy source unavailable");
            }
            return documents.read(resource).isPresent()
                && Boolean.TRUE.equals(grants.get(
                    new GrantKey(resource, actor, action)));
        }

        int evaluations() {
            return evaluations.get();
        }

        boolean isAvailable() {
            return available.get();
        }

        void setAvailable(boolean state) {
            available.set(state);
        }
    }

    public static class DecisionCache {
        private static final Duration ALLOW_TTL =
            Duration.ofSeconds(5);
        private static final Duration DENY_TTL =
            Duration.ofSeconds(2);
        private static final int MAX_ENTRIES = 1000;

        private final TestClock clock;
        private final Map<DecisionKey, Entry> entries =
            new ConcurrentHashMap<>();
        private final AtomicInteger hits = new AtomicInteger();
        private final AtomicInteger misses = new AtomicInteger();

        DecisionCache(TestClock clock) {
            this.clock = clock;
        }

        boolean decide(
                DecisionKey key, Supplier<Boolean> loader) {
            Instant now = clock.instant();
            Entry entry = entries.get(key);

            if (entry != null && now.isBefore(entry.expiresAt())) {
                hits.incrementAndGet();
                return entry.allowed();
            }

            misses.incrementAndGet();
            // Nếu loader ném lỗi, tuyệt đối không cache ALLOW.
            boolean allowed = loader.get();
            Duration ttl = allowed ? ALLOW_TTL : DENY_TTL;

            // Giới hạn thô cho demo; production dùng cache LRU/size
            // như Caffeine, tránh clear toàn bộ dưới tải cao.
            if (entries.size() >= MAX_ENTRIES) {
                entries.clear();
            }

            entries.put(
                key, new Entry(allowed, clock.instant().plus(ttl)));
            return allowed;
        }

        void invalidateResource(ResourceKey resource) {
            entries.keySet().removeIf(
                k -> k.resource().equals(resource));
        }

        void invalidateSubject(SubjectKey actor) {
            entries.keySet().removeIf(
                k -> k.actor().equals(actor));
        }

        void reset() {
            entries.clear();
            hits.set(0);
            misses.set(0);
        }

        int hits() { return hits.get(); }
        int misses() { return misses.get(); }
        int size() { return entries.size(); }
    }

    public static class DecisionPolicy {
        private final RuleStore rules;
        private final DecisionCache cache;

        DecisionPolicy(RuleStore rules, DecisionCache cache) {
            this.rules = rules;
            this.cache = cache;
        }

        private Actor trusted(Authentication authentication) {
            if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof Actor a)
                || a.tenant() == null || a.tenant().isBlank()
                || a.issuer() == null || a.issuer().isBlank()
                || a.subject() == null || a.subject().isBlank()) {
                return null;
            }
            // Test chỉ mô phỏng một authentication boundary đã
            // xác thực; production phải verify JWT/issuer/membership.
            return a;
        }

        public boolean can(
                Authentication authentication, long id,
                String action) {
            Actor actor = trusted(authentication);

            if (actor == null || !rules.isAvailable()) {
                // Fail closed kể cả khi đã có entry cache:
                // demo dùng một availability flag tức thời trong JVM.
                return false;
            }

            ResourceKey resource = doc(actor.tenant(), id);
            SubjectKey who = subject(actor);
            DecisionKey key = new DecisionKey(
                resource, who, action, rules.revision(resource));

            try {
                return cache.decide(key,
                    () -> rules.evaluate(resource, who, action));
            } catch (IllegalStateException policyUnavailable) {
                return false;
            }
        }
    }

    public static class Probe {
        private final Map<String, AtomicInteger> calls =
            new ConcurrentHashMap<>();

        void mark(String action) {
            calls.computeIfAbsent(
                action, ignored -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String action) {
            AtomicInteger value = calls.get(action);
            return value == null ? 0 : value.get();
        }

        void reset() {
            calls.clear();
        }
    }

    public static class ProtectedDocuments {
        private final Documents documents;
        private final Probe probe;

        ProtectedDocuments(Documents documents, Probe probe) {
            this.documents = documents;
            this.probe = probe;
        }

        private Actor actor() {
            Authentication authentication =
                SecurityContextHolder.getContext()
                    .getAuthentication();
            if (authentication == null
                || !(authentication.getPrincipal() instanceof Actor a)) {
                throw new AccessDeniedException(
                    "Trusted principal required");
            }
            return a;
        }

        @PreAuthorize(
            "hasAuthority('DOC_READ') and " +
            "@decisionPolicy.can(authentication, #id, 'READ')"
        )
        public String read(@P("id") long id) {
            probe.mark("READ");
            Actor a = actor();
            return documents.read(doc(a.tenant(), id))
                .orElseThrow(() ->
                    new AccessDeniedException("Not visible"));
        }

        @PreAuthorize(
            "hasAuthority('DOC_WRITE') and " +
            "@decisionPolicy.can(authentication, #id, 'WRITE')"
        )
        public void write(
                @P("id") long id, String newBody) {
            probe.mark("WRITE");
            Actor a = actor();
            documents.write(
                doc(a.tenant(), id), newBody);
        }
    }

    public static class PermissionAdmin {
        private final RuleStore rules;
        private final DecisionCache cache;

        PermissionAdmin(
                RuleStore rules, DecisionCache cache) {
            this.rules = rules;
            this.cache = cache;
        }

        @PreAuthorize("hasAuthority('POLICY_ADMIN')")
        public void revoke(
                String tenant, long id, Actor target,
                String action) {
            requireSameTenant(tenant, target);
            ResourceKey key = doc(tenant, id);
            rules.revoke(key, subject(target), action);
            cache.invalidateResource(key);
        }

        @PreAuthorize("hasAuthority('POLICY_ADMIN')")
        public void grant(
                String tenant, long id, Actor target,
                String action) {
            requireSameTenant(tenant, target);
            ResourceKey key = doc(tenant, id);
            rules.grant(key, subject(target), action);
            cache.invalidateResource(key);
        }

        @PreAuthorize("hasAuthority('POLICY_ADMIN')")
        public void invalidateActor(Actor target) {
            cache.invalidateSubject(subject(target));
        }

        private void requireSameTenant(
                String tenant, Actor target) {
            if (target == null
                || !tenant.equals(target.tenant())) {
                throw new IllegalArgumentException(
                    "Cross-tenant policy mutation");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {

        @Bean TestClock clock() {
            return new TestClock();
        }

        @Bean Documents documents() {
            return new Documents();
        }

        @Bean RuleStore ruleStore(Documents documents) {
            return new RuleStore(documents);
        }

        @Bean DecisionCache decisionCache(TestClock clock) {
            return new DecisionCache(clock);
        }

        @Bean("decisionPolicy")
        DecisionPolicy decisionPolicy(
                RuleStore rules, DecisionCache cache) {
            return new DecisionPolicy(rules, cache);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean ProtectedDocuments protectedDocuments(
                Documents documents, Probe probe) {
            return new ProtectedDocuments(documents, probe);
        }

        @Bean PermissionAdmin permissionAdmin(
                RuleStore rules, DecisionCache cache) {
            return new PermissionAdmin(rules, cache);
        }
    }

    @Autowired TestClock clock;
    @Autowired Documents documentsData;
    @Autowired RuleStore rules;
    @Autowired DecisionCache cache;
    @Autowired ProtectedDocuments protectedDocs;
    @Autowired PermissionAdmin admin;
    @Autowired Probe probe;

    private void as(Actor actor, String... authorities) {
        SecurityContext ctx =
            SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                actor, "test-only",
                AuthorityUtils.createAuthorityList(authorities)));
        SecurityContextHolder.setContext(ctx);
    }

    private void asAlice() {
        as(ALICE, "DOC_READ", "DOC_WRITE");
    }

    private void asBob() {
        as(BOB, "DOC_READ", "DOC_WRITE");
    }

    private void asAdmin() {
        as(ADMIN, "POLICY_ADMIN");
    }

    @BeforeEach
    void prepare() {
        clock.reset();
        documentsData.reset();
        rules.reset();
        cache.reset();
        probe.reset();
        asAlice();
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void springSecurityActuallyProxiesProtectedMethods() {
        assertThat(AopUtils.isAopProxy(protectedDocs)).isTrue();
        assertThat(AopUtils.isAopProxy(admin)).isTrue();
    }

    @Test
    void firstAllowMissThenSecondAllowHitsCache() {
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(rules.evaluations()).isEqualTo(1);
        assertThat(cache.misses()).isEqualTo(1);
        assertThat(cache.hits()).isEqualTo(1);
    }

    @Test
    void allowCacheExpiresAfterFiveSeconds() {
        protectedDocs.read(42L);
        clock.advance(Duration.ofSeconds(4));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(1);

        clock.advance(Duration.ofSeconds(1));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void denyDecisionCanBeCachedWithoutRunningMethodBody() {
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(1);
        assertThat(cache.hits()).isEqualTo(1);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void denyEntryExpiresAtTwoSeconds() {
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);

        clock.advance(Duration.ofSeconds(2));
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void revokeInvalidatesPreviouslyCachedAllow() {
        protectedDocs.read(42L);

        asAdmin();
        admin.revoke("TENANT_A", 42L, ALICE, "READ");
        asAlice();

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
        assertThat(probe.count("READ")).isEqualTo(1);
    }

    @Test
    void grantInvalidatesPreviouslyCachedDeny() {
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);

        asAdmin();
        admin.grant("TENANT_A", 42L, IMPOSTOR, "READ");
        as(IMPOSTOR, "DOC_READ");

        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void resourceRevisionProtectsAgainstMissedLocalEviction() {
        protectedDocs.read(42L);
        assertThat(cache.size()).isEqualTo(1);

        // Test giả lập event eviction bị mất trong CÙNG JVM.
        // Không phải đường mutation production được phép.
        rules.revoke(
            doc("TENANT_A", 42L), subject(ALICE), "READ");

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void sameResourceIdAndUsernameInOtherTenantHasOwnEntry() {
        assertThat(ALICE.getName()).isEqualTo("alex");
        assertThat(BOB.getName()).isEqualTo("alex");

        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        asBob();
        assertThat(protectedDocs.read(42L))
            .isEqualTo("B private 42");
        assertThat(rules.evaluations()).isEqualTo(2);

        asAlice();
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(cache.hits()).isEqualTo(1);
    }

    @Test
    void sameUsernameDifferentSubjectDoesNotReuseAllow() {
        protectedDocs.read(42L);
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void readGrantDoesNotBecomeWriteGrant() {
        protectedDocs.read(42L);
        assertThatThrownBy(() ->
            protectedDocs.write(42L, "Tampered"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(documentsData.read(
            doc("TENANT_A", 42L))).contains("A private 42");
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void newlyGrantedWriteWorksOnlyForItsTenant() {
        asAdmin();
        admin.grant("TENANT_A", 42L, ALICE, "WRITE");
        asAlice();

        protectedDocs.write(42L, "A edited");
        assertThat(documentsData.read(
            doc("TENANT_A", 42L))).contains("A edited");
        assertThat(documentsData.read(
            doc("TENANT_B", 42L))).contains("B private 42");
        assertThat(probe.count("WRITE")).isEqualTo(1);
    }

    @Test
    void resourceEvictionDoesNotClearUnrelatedResource() {
        protectedDocs.read(42L);
        protectedDocs.read(43L);
        assertThat(rules.evaluations()).isEqualTo(2);

        asAdmin();
        admin.revoke("TENANT_A", 42L, ALICE, "READ");
        asAlice();
        assertThat(protectedDocs.read(43L))
            .isEqualTo("A document 43");
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void invalidatingSubjectForcesItsEntriesToReevaluate() {
        protectedDocs.read(42L);
        protectedDocs.read(43L);
        assertThat(rules.evaluations()).isEqualTo(2);

        asAdmin();
        admin.invalidateActor(ALICE);
        asAlice();

        protectedDocs.read(42L);
        protectedDocs.read(43L);
        assertThat(rules.evaluations()).isEqualTo(4);
    }

    @Test
    void ordinaryUserCannotRevokeSomebodyElse() {
        long before = rules.revision(doc("TENANT_A", 42L));
        assertThatThrownBy(() ->
            admin.revoke("TENANT_A", 42L, ALICE, "READ"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.revision(
            doc("TENANT_A", 42L))).isEqualTo(before);
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
    }

    @Test
    void policyAdminCannotMutateAnotherTenantTargetByMistake() {
        asAdmin();
        assertThatThrownBy(() ->
            admin.grant("TENANT_A", 42L, BOB, "READ"))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(rules.revision(
            doc("TENANT_A", 42L))).isEqualTo(1L);
    }

    @Test
    void missingFunctionAuthorityStopsBeforeCacheLookup() {
        as(ALICE, "DOC_WRITE");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isZero();
        assertThat(cache.misses()).isZero();
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void untrustedStringPrincipalCannotUseOtherUsersCache() {
        protectedDocs.read(42L);
        SecurityContext ctx =
            SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "alex", "test-only",
                AuthorityUtils.createAuthorityList("DOC_READ")));
        SecurityContextHolder.setContext(ctx);

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(1);
    }

    @Test
    void unknownResourceIsDeniedAndMayBeCachedBriefly() {
        assertThatThrownBy(() -> protectedDocs.read(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThatThrownBy(() -> protectedDocs.read(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(1);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void policySourceOutageBlocksEvenCachedAllowInDemo() {
        protectedDocs.read(42L);
        rules.setAvailable(false);

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isEqualTo(1);
        rules.setAvailable(true);
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
    }

    @Test
    void revokingBDoesNotChangeACachedDecision() {
        protectedDocs.read(42L);
        asBob();
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(2);

        asAdmin();
        admin.revoke("TENANT_B", 42L, BOB, "READ");
        asAlice();
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(rules.evaluations()).isEqualTo(2);

        asBob();
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void cacheDoesNotKeepAnAllowBeyondExactTtlBoundary() {
        protectedDocs.read(42L);
        clock.advance(Duration.ofMillis(4999));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(1);

        clock.advance(Duration.ofMillis(1));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(2);
    }
}
```

### 8.3. Các lớp trong project có vai trò gì?

| Lớp / record | Vai trò |
| --- | --- |
| `Actor` / `SubjectKey` | Tách username hiển thị khỏi tenant+issuer+subject |
| `ResourceKey` | Phân biệt Document#42 của tenant A và B |
| `DecisionKey` | Chứa resource, actor, action và revision |
| `RuleStore` | Nguồn chính sách giả lập, đếm số lần evaluate và tăng revision khi grant/revoke |
| `DecisionCache` | Cache Boolean theo TTL; evict theo resource hoặc actor; đếm hit/miss |
| `DecisionPolicy` | Bridge từ `Authentication` tới policy+cache; fail closed với principal/source bất hợp lệ |
| `ProtectedDocuments` | Hai method READ/WRITE được `@PreAuthorize` bảo vệ qua Spring proxy |
| `PermissionAdmin` | Đường grant/revoke được bảo vệ bằng `POLICY_ADMIN`, tăng revision và evict |
| `TestClock` | Đồng hồ UTC điều khiển được, kiểm tra TTL không chờ thời gian thực |
| `Probe` | Chứng minh method body không chạy khi bị deny |

### 8.4. Chạy và kết quả kỳ vọng

Trong thư mục `decision-cache-demo`:

```bash
gradle test --tests demo.DecisionCacheSecurityTest
```

Nếu có Gradle Wrapper: dùng `./gradlew test --tests demo.DecisionCacheSecurityTest` trên Linux/macOS hoặc `gradlew.bat test --tests demo.DecisionCacheSecurityTest` trên Windows.

**Kỳ vọng:** **22 JUnit tests** đạt và Gradle báo `BUILD SUCCESSFUL`. Đây là **kết quả được dự đoán từ mã ví dụ**, không phải log thực thi đã được thu thập. Báo cáo HTML: `build/reports/tests/test/index.html`.

| Cụm test | Kết quả cần chứng minh |
| --- | --- |
| Spring proxy | Method Security thực sự hoạt động |
| Cache hit / TTL ALLOW | Lượt thứ hai không gọi lại RuleStore; hết 5s sẽ tính lại |
| Cache hit / TTL DENY | DENY có thể cache 2s nhưng body không được chạy |
| Revoke | ALLOW đã cache bị vô hiệu hóa sau thay quyền |
| Grant | DENY đã cache không cản quyền mới sau invalidation |
| Missed eviction cùng JVM | Revision tăng làm key mới; không dùng lại ALLOW cũ |
| Tenant và subject | Cùng ID/username không dùng chung quyết định giữa actors |
| Action READ vs WRITE | Grant READ không mặc định cấp WRITE |
| Eviction resource/subject | Chỉ phạm vi phù hợp bị tính lại |
| Admin policy | Actor không có POLICY_ADMIN không sửa được quyền |
| Không có authority/principal | Không thể mượn cached ALLOW |
| Unknown resource | Fail closed và DENY ngắn hạn |
| Source unavailable | Flag outage trong JVM làm policy deny trước cache |
| Exact TTL boundary | Đến đúng `expiresAt` phải miss |

**Cần hiểu giới hạn của test:** đồng hồ và policy revision đều nằm trong một process. Test missed eviction chỉ có ý nghĩa khi **revision tại cùng node đã thay đổi**. Nó **không** chứng minh node khác có revision mới; cũng không chứng minh tính nhất quán tuyến tính giữa một request đang chạy và một revoke vừa commit.

## 9. Triển khai production với Spring Cache, Caffeine hoặc Redis

### 9.1. Caffeine cho cache trong một JVM

Nếu dùng Caffeine, một cấu hình điển hình có giới hạn size và TTL:

```java
// Fragment minh họa; thêm dependency com.github.ben-manes.caffeine:caffeine.
com.github.benmanes.caffeine.cache.Cache<DecisionKey, Boolean> cache =
    com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
        .maximumSize(50_000)
        .expireAfterWrite(java.time.Duration.ofSeconds(5))
        .recordStats()
        .build();

// Lấy từ nguồn chính sách khi miss:
Boolean allowed = cache.get(key, k -> policyStore.evaluate(k));
```

`DecisionKey`/`policyStore` phải do ứng dụng định nghĩa như phần trước; snippet **không phải chương trình độc lập**. Đây là TTL chung cho mọi entry, trong khi demo dùng TTL khác nhau cho ALLOW/DENY. Nếu cần TTL theo kết quả, dùng `Expiry` tùy biến và test chính xác; đừng khẳng định `expireAfterWrite` tự hỗ trợ hai TTL theo Boolean.

Với Spring Cache, `@Cacheable` và `@CacheEvict` có ích nhưng cần kiểm soát **key, thứ tự method-security advisor, transaction boundary, proxy self-invocation và permission version**. Không thay thẳng `@PreAuthorize` bằng `@Cacheable`.

### 9.2. Redis/distributed cache

Một Redis cache dùng chung có thể giảm khác biệt giữa các node, nhưng **không tự đảm bảo revoke tức thì**:

- Pub/Sub message có thể bị mất khi subscriber offline; stream/outbox có replay và version giúp mạnh hơn.
- Cache write, DB commit và event publish không tự atomic.
- Nhiều region có replication lag; TTL và propagation SLO phải được định nghĩa.
- Redis eviction policy/memory pressure có thể làm hit rate dao động.
- Cần key namespace rõ tenant/resource/action/policy; khi chính sách đổi thì version và invalidation nhất quán.
- Chú ý dữ liệu nhạy cảm trong cache keys/logs: dùng hashed/opaque IDs khi phù hợp; TLS và auth cho Redis.

Một kiến trúc cho **thu hồi mạnh** có thể đặt `revocationEpoch` ở authoritative store và kiểm tra epoch hiện hành trước khi dùng cached ALLOW. Nếu epoch lookup cũng được cache ở node với TTL dài, bài toán stale quyền vẫn chưa được giải quyết. Những hành động có hậu quả lớn có thể cần **bỏ cache ALLOW**, hoặc re-evaluate trong transaction ở thời điểm thực thi.

### 9.3. Không đồng nhất invalidation của ACL và decision cache

Nếu quyền đến từ Spring Security ACL, thay ACE bằng `MutableAclService.updateAcl` có thể invalidate `AclCache` của implementation phù hợp. Nhưng một Boolean decision cache bên ngoài **không tự biết** lần cập nhật đó. Phải nối sự kiện ACL change đến cả hai tầng cache, xét cả **parent ACL, descendants, group membership** và effective permissions.

## 10. Các tình huống nhạy cảm và race condition

### 10.1. TOCTOU: kiểm tra quyền khác thời điểm thực thi

```text
t0  Request A: cached ALLOW for Document#42
t1  Admin: revoke READ
t2  Request A: enters method body and returns data
t3  Other nodes receive invalidation event
```

Ngay cả khi evict ở t1, request đã qua gate trước đó vẫn có thể hoàn thành. Với read đơn giản, xác định mức stale chấp nhận được. Với xóa dữ liệu, approve hoặc giao dịch tài chính, thực thi **condition check trong transaction/conditional SQL** hoặc chiến lược concurrency kiểm soát, không chỉ cache gate.

### 10.2. Cache stampede và concurrent loader

Khi 10.000 request cùng hết TTL, tất cả có thể gọi PDP đồng thời. Trong demo, `ConcurrentHashMap` + `get`/`put` đơn giản có thể làm nhiều loader chạy cùng lúc; production dùng loader coalescing/atomic cache load phù hợp, giới hạn tải và không vô tình biến cache stampede thành outage.

### 10.3. Policy store outage

Nếu PDP/database không sẵn sàng, một cached ALLOW **vẫn có thể tiếp tục được dùng** cho đến TTL nếu ứng dụng không có health/revocation gate được cập nhật. Demo cố ý đặt `RuleStore.isAvailable()` trước cache để mô phỏng fail closed trong cùng JVM, nhưng **health flag cục bộ không chứng minh fail closed toàn mạng**. Với dữ liệu rủi ro cao, không dùng “stale-while-revalidate” cho authorization nếu chưa được threat model chấp thuận.

### 10.4. Revocation của JWT và thay đổi role

Nếu `hasAuthority('DOC_READ')` đọc authority từ JWT ký hợp lệ nhưng token có hạn sử dụng dài, thu hồi role trong DB không tự làm authority trong token mất đi. Evict decision cache không sửa được JWT đã cấp. Có thể cần token lifetime ngắn, introspection, authz/version check, session revocation hoặc policy epoch; kiểm thử toàn bộ đường, không chỉ `DecisionCache`.

### 10.5. Batch/list/export

Cache một quyết định READ cho `Document#42` không có nghĩa user được export mọi Document của tenant. Mỗi tài nguyên và hành động cần policy riêng; `READ` không suy ra `EXPORT`. Với danh sách lớn, chỉ cache những phần hợp lý và thực hiện tenant/row filtering trong repository/SQL; tránh N+1 PDP queries và `@PostFilter` gây sai pagination.

## 11. Quan trắc và SLO cho cache authorization

| Metric / signal | Ý nghĩa |
| --- | --- |
| `authz_decision_cache_hit_total` / miss | Tỉ lệ tái sử dụng / chi phí đánh PDP |
| `authz_decision_cache_entries` | Size và key cardinality |
| `authz_decision_cache_evictions_total` | Invalidation và capacity evictions |
| `authz_policy_evaluation_seconds` | Độ trễ PDP/DB khi miss |
| `authz_policy_revision` | Version nào đang được dùng tại node |
| `authz_invalidation_delivery_lag_seconds` | Trễ từ commit đến khi node nhận event |
| `authz_invalidation_errors_total` | Event bị lỗi, stale nguy cơ cao |
| `authz_revocation_stale_allow_total` | Test/canary phát hiện ALLOW sau revoke |
| `authz_policy_source_unavailable_total` | Đo lỗi nguồn quyền và hành vi fail closed |

Tránh đưa **raw token, username/email, nội dung tài liệu** vào label metrics vì cardinality và rò dữ liệu. Khi debug, ghi correlation ID, hashed/opaque principal IDs, resource type/tenant đã được phép log, policy revision, cache hit/miss và quyết định (theo chính sách audit).

**SLO minh họa cần thỏa thuận:** “99,9% revoke events đến mọi node trong 1 giây; stale ALLOW tối đa 5 giây khi event mất.” Đây chỉ là mục tiêu ví dụ; nếu SLA sản phẩm là **thu hồi tuyệt đối ngay**, cần kiến trúc mạnh hơn TTL/invalidation eventual consistency.

## 12. Những lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| User đã bị revoke vẫn đọc được | Entry ALLOW còn TTL, event chậm/mất, node chưa nhận revision | Audit commit→event→evict; test sau revoke ở nhiều node |
| Có READ nhưng WRITE cũng được | Key thiếu action | Dùng READ/WRITE/EXPORT tách biệt |
| Tenant B nhận cached ALLOW của A | Key thiếu tenant hoặc resource type | Test cùng ID 42 ở A/B |
| Hai người cùng username dùng chung cache | Key chỉ dùng `authentication.getName()` | Test issuer/sub khác nhau |
| Grant mới vẫn bị DENY lâu | Cache DENY có TTL dài hoặc không invalidate | TTL DENY ngắn + grant invalidation |
| Revoke không ảnh hưởng Spring ACL cache | Chỉ evict Boolean decision cache | Invalidate ACL object/parent dependencies đúng cách |
| Node A đúng nhưng B sai | Invalidation event/revision không được phát tán | Multi-instance tests, outbox/stream, health/version |
| Memory tăng liên tục | Không maximum size, key quá phân mảnh | Bounded cache, size metrics, policy key audit |
| PDP bị đột biến tải sau TTL | Cache stampede | Single-flight/coalescing, jitter, rate limit |
| Không thấy method-security deny | Thiếu `@EnableMethodSecurity`, self-invocation, gọi `new` | Test Spring proxy, `Probe` |
| Policy source lỗi nhưng vẫn ALLOW | Dùng cached ALLOW trong outage | Fail-closed gate theo rủi ro, authoritative check |
| Data trả sai dù cache decision đúng | Cache payload/repository thiếu tenant scope | Tách cache quyết định và cache dữ liệu |
| Revoke role nhưng token vẫn có authority | JWT/session cache chưa được làm mới | Token/version/introspection/revocation tests |
| Cache chậm/không hiệu quả | TTL quá ngắn, invalidation quá rộng, key high-cardinality | Hit/miss P95, group by policy, tune trong giới hạn rủi ro |

### Quy trình chẩn đoán tối thiểu

1. Kiểm tra **principal đã xác thực**, tenant, issuer/sub, authority và resource đang xét.
2. In/quan sát **cache key cấu trúc** (không log token), action và revision.
3. Test phép tính khi **bỏ qua cache** trên cùng dữ liệu authoritative.
4. So entry cache với thời điểm `expiresAt`; test đúng biên TTL.
5. Xem transaction cập nhật quyền đã **COMMIT** chưa.
6. Kiểm tra event invalidation có phát, có được xử lý đúng revision trên từng node hay không.
7. Kiểm tra role/session/JWT/ACL cache khác còn giữ quyền cũ không.
8. Kiểm tra request bị deny **trước body**, không có side effects.
9. Kiểm thử SQL/repository và cache dữ liệu không lộ resource tenant khác.

## 13. Checklist trước production

- [ ] Cache key gồm actor tenant + stable identity, resource type/tenant/ID, action và revision/những attributes ảnh hưởng.
- [ ] Không sử dụng username hiển thị, local ID hoặc `hasAuthority` cache thô như identity toàn cục.
- [ ] Có TTL cho ALLOW/DENY phù hợp rủi ro; deny TTL không giữ user bị chặn quá lâu sau grant.
- [ ] Có maximum size, metric, single-flight/rate limiting cho loader dưới tải cao.
- [ ] Có invalidation sau commit cho grant/revoke/owner/parent/role/membership/policy changes.
- [ ] Distributed event có retry/replay/version và theo dõi lag; test mất/trùng/đảo thứ tự event.
- [ ] Có xử lý nguồn policy lỗi theo fail-closed policy; không tự dùng stale ALLOW cho thao tác rủi ro cao.
- [ ] Kiểm tra `@PreAuthorize` trên Spring proxy, không bỏ qua bằng self-invocation.
- [ ] READ/WRITE/EXPORT tách action; tenant/resource checks được thực hiện cả khi cache hit.
- [ ] Có test revoke sau ALLOW đã cache, grant sau DENY đã cache, TTL exact boundary, 2 tenant cùng ID và 2 subject cùng username.
- [ ] Có kiểm thử multi-node, JWT/session revocation, cache khác (ACL/document) và TOCTOU.
- [ ] Với side effect nhạy cảm, xác thực lại điều kiện tại thời điểm ghi dưới transaction/conditional SQL.
- [ ] Có audit actor/resource/revision và mục tiêu rõ về maximum stale authorization.

## 14. Bài tập

1. **TTL sai:** đổi ALLOW TTL thành 15 phút, bỏ invalidation. Xác định khoảng tối đa stale ALLOW và lý do thiết kế không an toàn nếu revoke SLA là 1 giây.
2. **Cache key sai:** bỏ tenant khỏi `ResourceKey` hoặc dùng username `alex` thay issuer/sub. Viết test hai tenant cùng ID 42, xác minh cache collision.
3. **Action:** thêm `APPROVE` hoặc `EXPORT`, bảo đảm grant READ không tạo entry ALLOW cho action mới.
4. **Group membership:** thêm nhóm REVIEWER và `roleRevision`. Khi Alice rời nhóm, invalidation theo subject phải xóa mọi quyết định dùng group đó; token cũ cũng phải được xử lý.
5. **Caffeine:** thay map bằng cache `maximumSize`, `expireAfterWrite`, `recordStats`; test TTL bằng ticker giả thay vì ngủ thật.
6. **Transaction:** thêm H2/PostgreSQL database và một outbox row khi revoke; chỉ phát event sau commit. Thử rollback và kiểm tra cache vẫn nhất quán với dữ liệu thật.
7. **Nhiều node:** chạy hai instance có cache riêng. Revoke ở A, giả lập node B mất event; kiểm tra TTL và revision refresh behavior.
8. **TOCTOU:** thêm `write` sửa DB dưới optimistic version. Cho revoke giữa precheck và commit; đề xuất cách chặn side effect dựa vào authoritative policy.
9. **Outage:** mô phỏng PDP không trả lời, kiểm tra không có ALLOW mới; phân tích cached ALLOW đã có và quyết định fail-closed cho từng action.
10. **ACL cha:** thay ACE parent và test invalidation toàn bộ descendants kế thừa, không chỉ ACL cha.

## 15. Tổng kết

Cache quyết định phân quyền có hai mục tiêu **đồng thời**: giảm chi phí đánh policy và **không dùng lại quyền đã lỗi thời quá giới hạn rủi ro**. TTL chỉ là thời hạn tồn tại; khi ACL/role/policy thay đổi cần invalidate và/hoặc chuyển sang **policy revision** mới. Trong hệ thống phân tán, phải phát tán thay đổi hoặc kiểm tra revision từ nguồn đáng tin, nếu không node khác vẫn có thể trả cached `ALLOW`.

Bản chất của cache key là **“ai + trong tenant nào + muốn làm gì + với resource nào + dưới phiên bản quyền nào”**. Spring Security `@PreAuthorize` vẫn kiểm tra authority theo từng lần gọi; cache chỉ tối ưu phần đánh giá policy đã xác định là có thể lưu tạm. Hành động có hậu quả lớn cần cơ chế transaction/recheck mạnh hơn cache TTL.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, custom bean trong `@PreAuthorize`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework — Cache Abstraction và cache annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Caffeine Wiki — Eviction, size & expiration: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine Wiki — Population, `Cache.get(key, loader)`: https://github.com/ben-manes/caffeine/wiki/Population
- Spring Security — Domain Object Security ACLs và ACL cache: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- OWASP API1:2023 — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
