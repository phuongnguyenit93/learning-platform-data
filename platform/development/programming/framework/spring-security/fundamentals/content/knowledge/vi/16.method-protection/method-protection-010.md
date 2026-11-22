# Không dùng kiểm tra sau thực thi để thay thế quyền cho thao tác đã ghi dữ liệu

> **Module:** Spring Security - fundamentals  
> **Chủ đề cha:** Bảo vệ phương thức  
> **Thông điệp chính:** Một phản hồi `403 Forbidden` sau `@PostAuthorize` không chứng minh rằng method chưa ghi dữ liệu. Đối với hành động có side effect, kiểm tra quyền phải diễn ra **trước** thao tác; transaction và các cơ chế khắc phục sự cố không được dùng để thay thế authorization.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa `@PreAuthorize` và `@PostAuthorize` theo **thời điểm** Spring Security đánh giá quyết định.
- Phát hiện bug khi gắn `@PostAuthorize` cho lệnh UPDATE, DELETE, phê duyệt, gửi message hoặc thanh toán.
- Đọc mã Java 17/Spring Boot chạy được, trong đó method đã bị deny nhưng bộ đếm trạng thái vẫn thay đổi.
- Hiểu giới hạn của `@Transactional`, rollback, AOP advisor order và side effect bên ngoài database.
- Thiết kế phân quyền trước hành động, kiểm tra owner/tenant/resource và bảo toàn invariant khi có concurrency.
- Viết kiểm thử chứng minh cả **caller bị từ chối** và **dữ liệu không bị thay đổi trái quyền**.

## 2. Spring Security kiểm tra trước hay sau method?

Khi method security được bật bằng `@EnableMethodSecurity`, Spring Security tạo các interceptors áp dụng cho Spring-managed beans. Hai annotation quan trọng có semantics khác nhau:

| Annotation | Khi đánh giá? | Truy cập được return value? | Nên dùng |
| --- | --- | --- | --- |
| `@PreAuthorize` | Trước khi thân method chạy | Không | Ngăn thao tác ghi/xóa/duyệt trước khi phát sinh side effect |
| `@PostAuthorize` | Sau khi thân method đã trả về | Có, qua `returnObject` | Quyết định có được **nhận kết quả đã đọc** hay không |
| `@PreFilter` | Trước khi method xử lý, lọc tham số tập hợp thích hợp | Không | Giới hạn tập phần tử xử lý, không thay thế policy |
| `@PostFilter` | Sau khi method trả tập kết quả | Có | Giới hạn danh sách trả về, không undo thao tác ghi |

Ví dụ cấu hình tối thiểu:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Spring Boot Starter Security **không tự bật** method security chỉ vì dependency tồn tại; cần cấu hình này hoặc cách bật tương đương được nạp vào Spring ApplicationContext. Trong proxy mode thông thường, lời gọi phải đi qua Spring bean proxy để interceptors có thể hoạt động.

### Sơ đồ thời điểm kiểm tra

~~~text
@PreAuthorize

Caller -> Spring proxy -> kiểm tra quyền
                              | DENY -> exception, method chưa chạy
                              | GRANT -> method chạy -> ghi dữ liệu -> trả về


@PostAuthorize

Caller -> Spring proxy -> method chạy -> ghi dữ liệu -> trả về
                                                       |
                                                       v
                                                 kiểm tra quyền
                                                 | DENY -> exception
                                                 | GRANT -> trả kết quả

Ở nhánh DENY, ghi dữ liệu CÓ THỂ đã xảy ra.
~~~

`@PreAuthorize` không tự bảo đảm một thao tác sẽ hợp lệ trong mọi hoàn cảnh: cần chính sách đúng, lời gọi qua proxy và các kiểm tra owner/tenant/invariant thích hợp. Nhưng nó đặt bước chặn **trước** side effect, đúng nơi cần cho write operation.

## 3. Vì sao `@PostAuthorize` nguy hiểm cho method ghi dữ liệu?

Giả sử method duyệt hóa đơn:

~~~java
// VÍ DỤ SAI: đoạn mã minh họa tích hợp vào service.
@PostAuthorize("hasAuthority('invoice:approve')")
public String approveInvoice(long id) {
    invoiceRepository.updateStatus(id, "APPROVED");
    return "approved";
}
~~~

Nếu caller là Alice, đã xác thực nhưng thiếu `invoice:approve`:

1. Proxy có thể chuyển lời gọi tới thân method.
2. Repository thực hiện UPDATE hóa đơn.
3. Method trả chuỗi `approved`.
4. After-method interceptor đánh giá `hasAuthority('invoice:approve')` và từ chối.
5. Caller nhận `AccessDeniedException`; HTTP integration phù hợp có thể biến nó thành `403 Forbidden`.
6. **Dữ liệu có thể đã đổi** hoặc đã commit trước khi exception được phát hiện.

Điểm cần ghi nhớ: `@PostAuthorize` không phải lệnh undo. Nó được thiết kế để quyết định việc **trả kết quả sau invocation**, không phải để ngăn execution đã diễn ra.

~~~text
Quan sát từ phía client: HTTP 403
Quan sát thực tế có thể có: invoice #42 = APPROVED
Lỗ hổng: kiểm tra quyền sau thời điểm thay đổi trạng thái
~~~

Điều tương tự xảy ra khi method gửi Kafka event, email, gọi payment gateway, cập nhật cache ngoài transaction hoặc khởi chạy tác vụ bất đồng bộ.

### Tác dụng phụ không phải lúc nào cũng đảo ngược được

~~~java
// VÍ DỤ SAI: payment gateway đã nhận yêu cầu trước after-check.
@PostAuthorize("hasAuthority('payment:transfer')")
public String transfer(String recipient, long amount) {
    paymentGateway.transfer(recipient, amount);
    return "sent";
}
~~~

Dù sau đó có `AccessDeniedException`, Spring Security không tự thu hồi lệnh mà gateway đã nhận. Một database rollback cũng không mặc nhiên hoàn tác email đã gửi hay message đã xuất bản.

**Quy tắc:** Trước khi side effect phát sinh, hệ thống phải hoàn tất authorization phù hợp; đừng đặt niềm tin vào phản hồi lỗi sau hành động.

## 4. Mẫu đúng cho operation ghi

Thay after-check bằng before-check:

~~~java
// Mã minh họa nằm trong một Spring-managed service.
@PreAuthorize("hasAuthority('invoice:approve')")
public String approveInvoice(long id) {
    invoiceRepository.updateStatus(id, "APPROVED");
    return "approved";
}
~~~

Khi user thiếu authority, lời gọi được intercept sẽ bị chặn **trước khi** repository chạy.

Nhưng quyền thao tác chung có thể chưa đủ. Ví dụ người dùng chỉ được duyệt hóa đơn cùng tenant; cần chính sách theo resource:

~~~java
// Cần bean invoicePolicy và repository thật của ứng dụng.
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.mayApprove(authentication, #invoiceId)"
)
public void approveInvoice(long invoiceId) {
    invoiceRepository.approve(invoiceId);
}
~~~

`invoicePolicy` phải sử dụng dữ liệu đáng tin cậy để kiểm tra owner, tenant, trạng thái, hạn mức và quy định nghiệp vụ. Không tin `tenantId` do client tự khai báo. Biểu thức trên là **đoạn minh họa tích hợp**, không phải ví dụ Java độc lập.

Ngay cả sau `@PreAuthorize`, một trạng thái có thể thay đổi đồng thời; vì vậy cần kiểm tra/khóa/UPDATE điều kiện tại transaction boundary khi thích hợp (phần 8).

## 5. Ví dụ chạy được: sau khi bị DENY, bộ đếm vẫn tăng

Demo này dùng **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.x**. Để thấy rõ thứ tự authorization mà không phụ thuộc database rollback, ta dùng `AtomicInteger` trong một Spring bean. Nếu method gọi `incrementAndGet()`, exception xuất hiện sau đó không tự giảm giá trị.

### 5.1. Cấu trúc

~~~text
after-authorize-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/afterauth/
    │   ├── Application.java
    │   ├── StateStore.java
    │   └── MutationService.java
    └── test/java/demo/afterauth/
        └── MutationServiceTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'after-authorize-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Demo kiểm tra service trực tiếp, không cần web server. `spring-security-test` cung cấp `@WithMockUser` và `@WithAnonymousUser` để tạo security context trong test; chúng không thực hiện đăng nhập thật.

### 5.2. Application bật method security

File `src/main/java/demo/afterauth/Application.java`:

~~~java
package demo.afterauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

`@EnableMethodSecurity` nằm trên class cấu hình Spring Boot được nạp. Nếu bỏ annotation này, `@PreAuthorize`/`@PostAuthorize` trên service không được thực thi bởi method security infrastructure mặc định.

### 5.3. Trạng thái ghi có thể quan sát

File `src/main/java/demo/afterauth/StateStore.java`:

~~~java
package demo.afterauth;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class StateStore {

    private final AtomicInteger writes = new AtomicInteger();

    public int writeOnce() {
        return writes.incrementAndGet();
    }

    public int current() {
        return writes.get();
    }

    public void reset() {
        writes.set(0);
    }
}
~~~

### 5.4. Hai method có cùng authority nhưng khác thời điểm

File `src/main/java/demo/afterauth/MutationService.java`:

~~~java
package demo.afterauth;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class MutationService {

    private final StateStore store;

    public MutationService(StateStore store) {
        this.store = store;
    }

    // SAI đối với write: thực thi side effect rồi mới kiểm tra.
    @PostAuthorize("hasAuthority('record:write')")
    public int writeThenCheck() {
        return store.writeOnce();
    }

    // ĐÚNG hơn: người thiếu quyền không vào được thân method.
    @PreAuthorize("hasAuthority('record:write')")
    public int checkThenWrite() {
        return store.writeOnce();
    }
}
~~~

Cả hai method cần authority `record:write`. Với Alice chỉ có `record:read`:

- `writeThenCheck()` chạy `store.writeOnce()`, rồi mới bị từ chối.
- `checkThenWrite()` bị từ chối trước lời gọi `store.writeOnce()`.

### 5.5. Kiểm thử bằng JUnit 5

File `src/test/java/demo/afterauth/MutationServiceTest.java`:

~~~java
package demo.afterauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MutationServiceTest {

    @Autowired
    MutationService service;

    @Autowired
    StateStore store;

    @BeforeEach
    void resetStore() {
        store.reset();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "record:read")
    void postAuthorizeDeniesAfterTheMutation() {
        assertThrows(AccessDeniedException.class,
            () -> service.writeThenCheck());

        // DENY không có nghĩa chưa có side effect.
        assertEquals(1, store.current());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "record:read")
    void preAuthorizeDeniesBeforeTheMutation() {
        assertThrows(AccessDeniedException.class,
            () -> service.checkThenWrite());

        assertEquals(0, store.current());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "record:write")
    void authorizedUserCanWrite() {
        assertEquals(1, service.checkThenWrite());
        assertEquals(1, store.current());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "record:write")
    void authorizedUserAlsoPassesPostCheck() {
        assertEquals(1, service.writeThenCheck());
        assertEquals(1, store.current());
    }

    @Test
    @WithAnonymousUser
    void anonymousCallerCannotWriteWithPreCheck() {
        assertThrows(AccessDeniedException.class,
            () -> service.checkThenWrite());

        assertEquals(0, store.current());
    }
}
~~~

Chạy trong root project với JDK 17+ và Gradle 8.x:

~~~bash
gradle test
~~~

Hoặc chỉ chạy class test:

~~~bash
gradle test --tests demo.afterauth.MutationServiceTest
~~~

**Kết quả kỳ vọng:** cả 5 test thành công. Bảng sau mô tả dữ liệu sau mỗi test khi `@BeforeEach` đã reset bộ đếm; đây là **kết quả suy ra từ chương trình**, không phải log test đã chạy trong bài viết.

| Trường hợp | Quyền của caller | Kết quả phương thức | `store.current()` |
| --- | --- | --- | --- |
| Alice gọi `writeThenCheck()` | `record:read` | `AccessDeniedException` | **1** |
| Alice gọi `checkThenWrite()` | `record:read` | `AccessDeniedException` | **0** |
| Bob gọi `checkThenWrite()` | `record:write` | Trả `1` | **1** |
| Bob gọi `writeThenCheck()` | `record:write` | Trả `1` | **1** |
| Anonymous gọi `checkThenWrite()` | Không có quyền ghi | `AccessDeniedException` | **0** |

**Hãy chú ý test đầu.** Nếu chỉ assert `AccessDeniedException`, người đọc rất dễ tưởng hệ thống đã được bảo vệ. Nhưng assertion về trạng thái cho thấy mutation thực sự đã xảy ra.

### Tại sao ví dụ này đáng tin để giải thích thời điểm?

`AtomicInteger` không có transaction database nên không có cơ chế rollback nào che lấp hiệu ứng. Các test gọi service được Spring inject qua AOP proxy (không tạo bằng `new`). Khi after-interceptor từ chối sau khi target trả kết quả, bộ đếm vẫn bằng `1`. Demo này chứng minh vấn đề thứ tự, **không khẳng định mọi JDBC transaction sẽ commit trong mọi cấu hình**.

## 6. Transaction rollback không phải phép thay thế authorization

Một phản biện thường gặp: “Method có `@Transactional`, nếu `@PostAuthorize` deny thì transaction rollback, vậy đã an toàn”. Kết luận này **không đúng trong mọi trường hợp**.

### 6.1. Rollback có phạm vi giới hạn

Với transaction khai báo của Spring Framework, một `RuntimeException` hoặc `Error` truyền qua transaction interceptor thường có thể kích hoạt rollback theo cấu hình mặc định. Checked exceptions cần rollback rules tương ứng nếu muốn rollback. Nhưng transaction chỉ điều phối **những resource tham gia** trong phạm vi thực tế.

Ví dụ database rollback không mặc nhiên hoàn tác:

- Email/SMS đã gửi.
- Request chuyển tiền đã nhận bởi gateway.
- Event đã publish lên broker ngoài transaction.
- File đã ghi ở filesystem.
- Cache bên ngoài transaction và `AtomicInteger` trong demo.
- Ghi nhận đã commit ở một transaction độc lập khác.

Vì vậy **rollback database thành công vẫn không chứng minh “chưa có tác dụng phụ trái quyền”**.

### 6.2. Advisor ordering và transaction boundary

`@PostAuthorize` lẫn `@Transactional` đều được Spring áp dụng qua advice. Thứ tự lồng nhau có thể ảnh hưởng chuyện exception đến trước hay sau thời điểm commit.

~~~text
Ví dụ A: transaction advice bao ngoài after-authorize advice

BEGIN
  target method UPDATE
  @PostAuthorize: DENY
  exception đi qua transaction interceptor
ROLLBACK có thể xảy ra theo rollback rule


Ví dụ B: after-authorize advice bao ngoài transaction advice

BEGIN
  target method UPDATE
COMMIT
@PostAuthorize: DENY
exception xuất hiện sau COMMIT
~~~

Đây là **hai khả năng khái niệm**, không phải tuyên bố một cấu hình Spring cụ thể chắc chắn rơi vào A hoặc B. Cần biết advisor order, transaction manager, propagation, exception handling và proxy topology thực tế.

Tài liệu Spring Security chính thức cũng cảnh báo `@PostAuthorize` **không được khuyến nghị** cho class thực hiện database writes vì thay đổi thường có thể diễn ra trước khi các security invariants được đánh giá.

Cách thiết kế ổn định hơn: **kiểm tra quyền ở trước write operation**, không phụ thuộc một tổ hợp advisor/rollback ngẫu nhiên để sửa một quyết định phân quyền quá muộn.

### 6.3. HTTP 403 không chứng nhận rollback

Một request trả `403 Forbidden` có thể đã bị chặn ở HTTP authorization, CSRF, `@PreAuthorize` hoặc `@PostAuthorize`. Không thể suy ra điểm bị chặn hoặc trạng thái database chỉ từ HTTP status. Nếu một transaction đã commit trước khi after-check DENY, response 403 **không đảo ngược commit đó**.

Đối với các operation rủi ro cao, test phải quan sát dữ liệu sau khi transaction hoàn tất và xác minh không có external call nào được phát ra khi thiếu quyền.

## 7. `@PostAuthorize` phù hợp với trường hợp nào?

`@PostAuthorize` vẫn hữu ích cho **method đọc** khi quyền phụ thuộc giá trị thực được trả về.

~~~java
// Ví dụ tích hợp, cần Document và documentRepository trong ứng dụng.
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject != null and returnObject.ownerUsername == authentication.name"
)
public Document getDocument(long documentId) {
    return documentRepository.findById(documentId).orElse(null);
}
~~~

Method đọc trả `Document` với property `ownerUsername` (ví dụ getter `getOwnerUsername()`). Before-check yêu cầu quyền đọc; after-check chỉ cho trả object nếu chủ sở hữu khớp principal. Không có yêu cầu cập nhật dữ liệu trong thân method.

Tuy nhiên, method đọc **vẫn đã chạy** trước after-check; hãy tránh những side effect nhạy cảm bên trong. Với dữ liệu nhạy cảm hoặc tập tài liệu lớn, lọc theo owner/tenant ở repository/query trước khi tải dữ liệu thường tốt hơn. `@PostFilter` tương tự: nó lọc collection **trả về**, không xóa các thao tác ghi trong thân method.

## 8. Kiểm tra trước ghi vẫn cần bảo toàn invariant khi có concurrent requests

Quyền `invoice:approve` chỉ xác nhận principal có capability chung. Điều đó chưa chứng minh người ấy được duyệt **invoice #42** của tenant khác, hoặc hóa đơn vẫn còn ở trạng thái PENDING lúc ghi.

Một chuỗi bảo vệ thường là:

1. **Authentication:** có principal đã được hệ thống xác minh.
2. **Authority check:** `@PreAuthorize("hasAuthority('invoice:approve')")`.
3. **Object policy:** kiểm tra owner/tenant/trạng thái từ dữ liệu server, không chỉ dựa input client.
4. **Write-boundary invariant:** kiểm tra điều kiện trong transaction hoặc bằng UPDATE có điều kiện / optimistic versioning / lock để chống race (*TOCTOU — time of check to time of use*).
5. **External side effects:** chỉ tiến hành sau authorization và theo thiết kế nhất quán đã xác định.

Ví dụ SQL chỉ để minh họa atomic check-and-write:

~~~sql
UPDATE invoices
SET status = 'APPROVED'
WHERE id = :invoice_id
  AND tenant_id = :verified_tenant_id
  AND status = 'PENDING';
~~~

`:verified_tenant_id` lấy từ nguồn danh tính/tenant đã tin cậy; các tham số phải bind an toàn. Kiểm tra số dòng bị ảnh hưởng: bằng 0 có thể nghĩa là sai tenant, trạng thái không hợp lệ hoặc record không còn phù hợp. Không trả “đã duyệt” khi không update thành công.

Một UPDATE có điều kiện **không thay thế** authentication hay authority check. Nó là lớp phòng vệ dữ liệu để bảo toàn quy tắc tại thời điểm ghi.

### Gửi event, outbox và idempotency

Nếu cần publish sự kiện “invoice approved” sau commit database, có thể dùng transactional outbox. Ghi event outbox trong cùng transaction và gửi khi transaction đã commit giúp tăng tính nhất quán. Nhưng **không được tạo event trái quyền trước khi kiểm tra authorization**. Với payment gateway, cần idempotency key và chính sách retry/compensation; các cơ chế ấy xử lý tính an toàn nghiệp vụ, không phải cấp quyền.

## 9. Phải bảo vệ đúng entry point qua Spring AOP proxy

Trong proxy mode, `@PreAuthorize` trên một method không luôn chặn lời gọi `this.method()` từ bên trong cùng object:

~~~java
// Ví dụ rủi ro: self-invocation đi thẳng vào target method.
@Service
public class InvoiceWorkflow {

    public void run(long id) {
        approve(id); // self-invocation, không đi qua proxy thông thường
    }

    @PreAuthorize("hasAuthority('invoice:approve')")
    public void approve(long id) {
        // ghi dữ liệu
    }
}
~~~

Nếu `run()` là entry point được gọi bên ngoài và không có policy, interceptor trên `approve()` có thể bị bypass bởi self-invocation. Sửa bằng cách bảo vệ `run()` hoặc tách `approve()` sang Spring-managed service khác được inject và gọi qua bean proxy.

Tương tự, tạo đối tượng bằng `new` sẽ không tự hưởng method-security advice của Spring. Một method private hoặc final cũng có những giới hạn proxy/override tùy kiểu proxy. Việc đặt `@PreAuthorize` là cần nhưng chưa đủ: **phải kiểm chứng đường gọi thực tế**.

## 10. Test quyền và dữ liệu: cần hai kiểu assertion

| Thứ phải kiểm tra | Mục đích | Assertion |
| --- | --- | --- |
| Authorization | Caller thiếu quyền bị từ chối | Exception `AccessDeniedException` hoặc HTTP 403 |
| State invariant | Không có mutation trái quyền | Database row/status trước và sau bằng nhau |
| External side effect | Không có lệnh trái quyền ra ngoài | Payment/event/email fake hoặc sandbox ghi nhận 0 lần |
| Concurrent safety | Không phá invariant khi trạng thái đổi đồng thời | Atomic update, version check, test đồng thời |
| Proxy boundary | Annotation có hiệu lực trên entry point thực | Gọi qua Spring bean và test nhánh thiếu quyền |

Các kịch bản test tối thiểu:

- Chưa đăng nhập: không ghi.
- Đã đăng nhập nhưng thiếu authority: không ghi.
- Có authority nhưng sai owner/tenant: không ghi.
- Đúng authority và owner/tenant: ghi đúng tài nguyên và đúng một lần.
- Dữ liệu đổi đồng thời: không vượt qua business invariant.
- Exception, retry, lỗi gateway: không nhân đôi side effect trái phép.
- Method được gọi từ một service khác hoặc nội bộ: không bypass policy.

**Đừng chỉ viết** `assertThrows(AccessDeniedException.class, ...)` rồi kết luận an toàn: demo ở phần 5 cho thấy nó có thể đạt ngay cả khi state đã tăng.

Lưu ý thêm: Integration test chạy trong transaction test do framework rollback ở cuối có thể che giấu trạng thái commit thật. Khi cần chứng minh tính an toàn trước/sau transaction, hãy kiểm tra bằng test thực sự quan sát dữ liệu ngoài transaction test hoặc sau commit đúng cách.

`@WithMockUser` trong method tests mô phỏng security context, không chứng minh cơ chế đăng nhập, xác minh JWT và mapping claims sang `GrantedAuthority` ngoài production đã đúng. Hãy test các tầng này riêng khi cần.

## 11. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gắn `@PostAuthorize` lên method DELETE/UPDATE | DENY nhưng target có thể đã ghi | `@PreAuthorize` và domain authorization trước mutation |
| Thấy HTTP 403, kết luận dữ liệu không đổi | Bỏ sót bug đã commit hoặc external call | Assert state và side effect thực tế |
| Tin rằng `@Transactional` luôn rollback mọi thứ | Không phải mọi thứ nằm trong transaction; order advisor khác nhau | Đừng dựa vào rollback để thay thế authorization |
| Chỉ dùng `hasRole('ADMIN')` rồi bỏ owner/tenant check | Mở quyền quá rộng ở cấp đối tượng | Object-level policy và write-boundary invariant |
| Có before-check nhưng không xử lý TOCTOU | Dữ liệu đổi giữa check và write | Conditional UPDATE, lock hoặc versioning |
| `@PostFilter` sau khi đã gửi message | Lọc response không xóa message đã gửi | Kiểm tra quyền trước việc gửi |
| `this.approve()` trong cùng bean | Method security có thể bị bypass | Policy ở entry point hoặc bean riêng |
| Chỉ test response, không test database | Không phát hiện unauthorized mutation | Test quyền + trạng thái trước/sau |
| Tin quyền/tenant client gửi lên | Có thể tự nâng quyền hoặc vượt tenant | Dùng nguồn xác thực/tài nguyên đáng tin cậy |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `@PostAuthorize` từ chối sau khi method đã UPDATE invoice, client nhận 403. Invoice chắc chắn chưa đổi chứ?

**Đáp án:** Không. Method đã chạy trước after-check; UPDATE có thể đã commit. Cần xác minh database và transaction boundary.

**Câu 2.** `@Transactional` có biến after-check thành before-check không?

**Đáp án:** Không. Nó điều phối commit/rollback của các resource tham gia; quyết định quyền vẫn đến sau nếu dùng `@PostAuthorize`. Advisor order và side effects bên ngoài càng làm việc suy đoán rollback không an toàn.

**Câu 3.** Nếu dùng `@PreAuthorize("hasAuthority('invoice:approve')")`, còn phải kiểm tra điều gì?

**Đáp án:** Tenant/owner/state của hóa đơn thật, business invariants và khả năng concurrent update nếu chúng thuộc chính sách hệ thống.

**Câu 4.** Vì sao `@PostAuthorize("returnObject.ownerUsername == authentication.name")` có thể thích hợp với read service?

**Đáp án:** Quyền nhận đối tượng phụ thuộc vào chính đối tượng đã đọc, miễn là method không gây side effect nhạy cảm.

**Câu 5.** Test trả 403 cần thêm assertion gì để chứng minh lệnh ghi trái phép không xảy ra?

**Đáp án:** Kiểm tra database/state không đổi và không có external action trái phép được gửi.

**Câu 6.** Vì sao `@PreAuthorize` có thể bị bỏ qua khi gọi `this.approve()`?

**Đáp án:** Trong Spring AOP proxy mode, self-invocation không đi qua proxy để chạy advice trên method được gọi.

## 13. Kết luận và tài liệu chính thức

**Không dùng kiểm tra sau thực thi để thay thế quyền cho thao tác đã ghi dữ liệu.** Với action có side effect, phân quyền phải là điều kiện **để bắt đầu thực thi**, không phải một xét duyệt sau khi hệ thống đã làm. `@PostAuthorize` có ích cho các quyết định dựa trên dữ liệu trả về của method đọc; transaction, compensation và idempotency phục vụ tính nhất quán nhưng không thay quyền trước action. Test bảo mật tốt luôn kiểm tra cả DENY và **không có mutation trái phép**.

Tài liệu tham khảo:

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
