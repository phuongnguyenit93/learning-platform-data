# So sánh kiểm tra trước, kiểm tra sau và lọc danh sách

> **Phạm vi:** Spring Security Method Security ở tầng service (Servlet hoặc các lời gọi bean đồng bộ), Java 17+, Spring Boot 3.x/Spring Security 6.x. Bài thực hành so sánh **kiểm tra quyền trước khi thực thi** (`@PreAuthorize`), **kiểm tra quyền sau khi có kết quả** (`@PostAuthorize`) và **lọc từng phần tử** trước/sau lời gọi (`@PreFilter`, `@PostFilter`). Mục tiêu là chọn đúng công cụ theo nghiệp vụ, không nhầm “từ chối cả lời gọi” với “loại một số phần tử”.

## 1. Bốn cách bảo vệ khác nhau ở điểm nào?

Khi bật `@EnableMethodSecurity`, Spring Security tạo các interceptor trên **bean được Spring quản lý**. Các annotation kiểm soát lời gọi phương thức hoặc dữ liệu đi qua nó:

| Cơ chế | Thời điểm | Đối tượng kiểm tra | Khi không đạt điều kiện | Mục đích điển hình |
| --- | --- | --- | --- | --- |
| `@PreAuthorize` | **Trước** thân phương thức | Principal, authorities và tham số đầu vào | Từ chối **cả lời gọi**, thân phương thức không chạy | Chặn thao tác ghi, archive, delete, approve ngay từ đầu |
| `@PostAuthorize` | **Sau** khi thân phương thức trả kết quả | Principal và `returnObject` | Từ chối **cả kết quả**; thân phương thức **đã chạy** | Kiểm tra quyền sở hữu khi phải đọc object để biết owner |
| `@PreFilter` | **Trước** khi thân phương thức xử lý tham số | Từng `filterObject` của tập đầu vào | Loại các phần tử không đạt; phương thức thường vẫn chạy với tập còn lại, có thể rỗng | Xử lý batch theo từng tài nguyên được phép |
| `@PostFilter` | **Sau** khi thân phương thức tạo tập kết quả | Từng `filterObject` của tập trả về | Chỉ trả cho caller phần tử đạt điều kiện; có thể trả tập rỗng | Lọc danh sách kết quả cho đúng principal |

**Hai trục độc lập** quyết định cách dùng:

1. **Khi nào đánh giá?** `Pre` trước thân method; `Post` sau thân method.
2. **Đánh giá gì?** `Authorize` quyết định **cả lời gọi/cả kết quả**, còn `Filter` quyết định **từng phần tử**.

`@PreAuthorize` và `@PreFilter` không tương đương: một thao tác ghi theo lô có thể phải *từ chối toàn bộ* nếu chứa tài liệu không thuộc quyền, trong khi một thao tác nhập hàng loạt được thiết kế cho phép bỏ qua các tài liệu không đủ quyền có thể dùng lọc. Việc *âm thầm* loại phần tử trong nghiệp vụ cần xử lý all-or-nothing có thể gây mất dữ liệu hoặc kết quả thành công sai kỳ vọng.

`@PostAuthorize` và `@PostFilter` cũng khác: với dữ liệu `A1, B1, A2`, `@PostAuthorize` kiểm tra một `returnObject` như `B1` có thể ném ngoại lệ và **không trả object nào**; `@PostFilter` trên cả list sẽ trả `A1, A2` cho Alice. Không coi `@PostFilter` là cách tự động tạo HTTP 403.

### Luồng thực thi

```text
Caller (SecurityContext của alice)
   |
   v
Spring AOP / method-security proxy
   |
   +--> @PreFilter: bỏ phần tử không đạt ở input
   +--> @PreAuthorize: quyết định có được chạy method?
   |      Không -> AccessDeniedException (method không chạy)
   v
Service method body: đọc DB / xử lý batch / tạo kết quả
   |
   +--> @PostAuthorize: quyết định có cho trả cả kết quả?
   |      Không -> AccessDeniedException (method đã chạy)
   +--> @PostFilter: loại từng phần tử không đạt ở output
   v
Caller nhận kết quả đã được bảo vệ
```

Sơ đồ là cách **phân loại giai đoạn**, không phải bảo đảm thứ tự tuyệt đối khi phối hợp nhiều annotation tùy phiên bản/configuration. Trong Spring Security có các advisor với thứ tự riêng; khi kết hợp annotation trên cùng method, cần xác nhận thứ tự thực tế và viết test theo contract cuối cùng. Tránh đặt side effect vào biểu thức kiểm tra.

## 2. Ngữ cảnh thực hành: một bộ tài liệu, nhiều quyết định

Giả sử service có ba tài liệu, được lấy từ dữ liệu **do server quản lý**:

| ID | Owner | Alice được xem/lọc? | Bob được xem/lọc? |
| --- | --- | --- | --- |
| `A1` | `alice` | Có | Không |
| `B1` | `bob` | Không | Có |
| `A2` | `alice` | Có | Không |

Bốn nghiệp vụ trong bài:

- `archive(id)` yêu cầu authority `document:archive` **và** ID thuộc principal hiện tại. Cần chặn trước thao tác thay đổi trạng thái → `@PreAuthorize`.
- `findOne(id)` phải đọc document để biết owner. Có thể dùng `@PostAuthorize` kiểm tra `returnObject.owner`, miễn thân method chỉ là **đọc không gây side effect**.
- `acceptedIds(documents)` nhận một batch *đã được phía server xác minh*, chủ động bỏ phần tử không thuộc người gọi trước khi thân method nhận → `@PreFilter`.
- `listAll()` trả về dữ liệu hỗn hợp và chỉ muốn caller thấy phần tử của mình → `@PostFilter`.

Kết quả dự kiến:

| User và lời gọi | Kết quả quan sát | Thân phương thức có chạy? |
| --- | --- | --- |
| Alice có authority, `archive("A1")` | `"archived:A1"` | Có |
| Alice có authority, `archive("B1")` | `AccessDeniedException` | Không |
| Alice thiếu authority, `archive("A1")` | `AccessDeniedException` | Không |
| Alice, `findOne("A1")` | Document `A1` | Có |
| Alice, `findOne("B1")` | `AccessDeniedException` | **Có**: đọc rồi mới chặn trả về |
| Alice, `acceptedIds([A1,B1,A2])` | `[A1,A2]` | Có, chỉ thấy A1/A2 |
| Alice, `listAll()` | `[A1,A2]` | Có, đã tạo list gốc gồm cả B1 |
| Bob, `listAll()` | `[B1]` | Có |
| Charlie, `listAll()` | `[]` | Có, trả list rỗng |

**An toàn ownership:** `@PreAuthorize` nên kiểm tra owner theo **dữ liệu đáng tin từ repository/ACL/PDP**, dựa trên ID tài nguyên; không tin vào trường `owner` do client gửi khi cập nhật/xóa. Với `@PreFilter`, nếu tập input chứa object do client tự tạo, `filterObject.owner` cũng không đủ chống giả mạo; cần resolve/verify đối tượng từ nguồn server trước khi xử lý.

## 3. Ví dụ Spring Test chạy được với Java 17

Ví dụ dùng Spring ApplicationContext test tối thiểu: không phải khởi động web server. Trong dự án Spring Boot 3.x có Gradle Wrapper và BOM/version từ plugin, cần những dependency sau (nếu chưa có):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Toàn bộ ví dụ test nằm trong một file** `src/test/java/com/example/security/AuthorizationComparisonTest.java`. `@SpringJUnitConfig` khởi tạo context, `@EnableMethodSecurity` bật interceptor; `@Autowired` lấy service qua proxy thật; `@WithMockUser` cung cấp SecurityContext cho từng case.

```java
package com.example.security;

import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(AuthorizationComparisonTest.Config.class)
class AuthorizationComparisonTest {

    @Autowired DocumentService service;

    @BeforeEach
    void resetCounters() {
        service.reset();
    }

    private static List<Document> mixedInput() {
        // ArrayList sửa được: @PreFilter có thể loại phần tử.
        return new ArrayList<>(List.of(
            new Document("A1", "alice"),
            new Document("B1", "bob"),
            new Document("A2", "alice")
        ));
    }

    private static List<String> ids(List<Document> documents) {
        return documents.stream().map(Document::getId).toList();
    }

    // Nhóm A: @PreAuthorize bảo vệ toàn bộ thao tác ghi.
    @Test
    @WithMockUser(username = "alice", authorities = "document:archive")
    void preAuthorizeAllowsValidAuthorityAndServerOwnership() {
        assertEquals("archived:A1", service.archive("A1"));
        assertEquals(1, service.archiveRuns.get());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:archive")
    void preAuthorizeDeniesForeignOwnershipBeforeMethodBody() {
        assertThrows(AccessDeniedException.class,
            () -> service.archive("B1"));
        assertEquals(0, service.archiveRuns.get());
    }

    @Test
    @WithMockUser(username = "alice")
    void preAuthorizeDeniesMissingAuthorityEvenForOwnDocument() {
        assertThrows(AccessDeniedException.class,
            () -> service.archive("A1"));
        assertEquals(0, service.archiveRuns.get());
    }

    // Nhóm B: @PostAuthorize xét returnObject sau khi đã đọc.
    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeReturnsOwnedDocument() {
        assertEquals("A1", service.findOne("A1").getId());
        assertEquals(1, service.findRuns.get());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeRejectsForeignResultButBodyAlreadyRan() {
        assertThrows(AccessDeniedException.class,
            () -> service.findOne("B1"));
        assertEquals(1, service.findRuns.get());
    }

    // Nhóm C: @PreFilter thay đổi tập đầu vào mà method nhìn thấy.
    @Test
    @WithMockUser(username = "alice")
    void preFilterRemovesForeignElementBeforeBody() {
        assertEquals(List.of("A1", "A2"),
            service.acceptedIds(mixedInput()));
        assertEquals(1, service.acceptRuns.get());
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilterCanPassAnEmptyBatchWithoutDenyingCall() {
        List<Document> onlyBob = new ArrayList<>(List.of(
            new Document("B1", "bob")));
        assertEquals(List.of(), service.acceptedIds(onlyBob));
        assertEquals(1, service.acceptRuns.get());
    }

    @Test
    @WithMockUser(username = "bob")
    void preFilterDependsOnAuthenticatedPrincipal() {
        assertEquals(List.of("B1"),
            service.acceptedIds(mixedInput()));
    }

    // Nhóm D: @PostFilter trả đúng subset cho caller.
    @Test
    @WithMockUser(username = "alice")
    void postFilterKeepsOnlyAliceDocuments() {
        assertEquals(List.of("A1", "A2"),
            ids(service.listAll()));
        assertEquals(1, service.listRuns.get());
    }

    @Test
    @WithMockUser(username = "bob")
    void postFilterKeepsOnlyBobDocuments() {
        assertEquals(List.of("B1"), ids(service.listAll()));
    }

    @Test
    @WithMockUser(username = "charlie")
    void postFilterReturnsEmptyListWhenNoElementMatches() {
        assertEquals(List.of(), ids(service.listAll()));
        assertEquals(1, service.listRuns.get());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class Config {
        @Bean
        OwnershipPolicy ownership() {
            return new OwnershipPolicy();
        }

        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    public static final class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }

    // Giả lập lookup server-side, KHÔNG lấy owner do request khai báo.
    public static class OwnershipPolicy {
        public boolean ownedBy(String id, String username) {
            return DocumentService.STORED.stream().anyMatch(
                d -> d.getId().equals(id)
                  && d.getOwner().equals(username));
        }
    }

    public static class DocumentService {
        static final List<Document> STORED = List.of(
            new Document("A1", "alice"),
            new Document("B1", "bob"),
            new Document("A2", "alice")
        );

        final AtomicInteger archiveRuns = new AtomicInteger();
        final AtomicInteger findRuns = new AtomicInteger();
        final AtomicInteger acceptRuns = new AtomicInteger();
        final AtomicInteger listRuns = new AtomicInteger();

        public void reset() {
            archiveRuns.set(0);
            findRuns.set(0);
            acceptRuns.set(0);
            listRuns.set(0);
        }

        @PreAuthorize(
            "hasAuthority('document:archive') " +
            "and @ownership.ownedBy(#p0, authentication.name)")
        public String archive(String id) {
            archiveRuns.incrementAndGet();
            // Mô phỏng side effect; ví dụ không ghi database.
            return "archived:" + id;
        }

        @PostAuthorize("returnObject.owner == authentication.name")
        public Document findOne(String id) {
            findRuns.incrementAndGet();
            return STORED.stream()
                .filter(d -> d.getId().equals(id))
                .findFirst()
                .orElseThrow(() -> new NoSuchElementException(id));
        }

        @PreFilter("filterObject.owner == authentication.name")
        public List<String> acceptedIds(List<Document> documents) {
            acceptRuns.incrementAndGet();
            // Method chỉ thấy tài liệu còn lại sau @PreFilter.
            return documents.stream().map(Document::getId).toList();
        }

        @PostFilter("filterObject.owner == authentication.name")
        public List<Document> listAll() {
            listRuns.incrementAndGet();
            // Cố ý có tài liệu của cả alice và bob để kiểm tra lọc.
            return new ArrayList<>(STORED);
        }
    }
}
```

Dùng Gradle Wrapper tại root dự án đã cấu hình Spring Boot:

```bash
./gradlew test --tests "com.example.security.AuthorizationComparisonTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.security.AuthorizationComparisonTest"
```

**Kỳ vọng từ mã nguồn:** **11 JUnit 5 tests PASS**, theo các assertion và fixture đã nêu. Test không in stdout cố định; output thực tế của Gradle phụ thuộc cấu hình báo cáo. Đây là **kết quả mong đợi**, không phải khẳng định đã chạy test ở môi trường bên ngoài.

### Vì sao các kiểm thử này có ý nghĩa?

- `archiveRuns == 0` khi `@PreAuthorize` từ chối chứng minh **thân phương thức không thực thi**. Đồng thời test kiểm tra cả authority và ownership từ dữ liệu server.
- `findRuns == 1` khi `@PostAuthorize` từ chối chứng minh **thân phương thức đã truy xuất object** trước khi caller nhận `AccessDeniedException`. Vì vậy tránh dùng `@PostAuthorize` một mình cho thao tác có side effect.
- `acceptedIds(mixedInput())` trả ID **ngay trong method body**, chứng minh input đã bị lọc trước; nếu annotation không hoạt động, `B1` xuất hiện và test đỏ.
- `listAll()` luôn tạo đủ ba tài liệu, nhưng caller Alice chỉ nhận `A1,A2`, Bob chỉ nhận `B1`, Charlie nhận `[]`: đây là kiểm tra **nội dung đầu ra**, không chỉ `size()`.
- Các lời gọi đều dùng bean `@Autowired`, với `@EnableMethodSecurity`; dùng `new DocumentService()` riêng hoặc `this.someSecuredMethod()` trong cùng bean có thể bỏ qua Spring AOP proxy và làm sai kết luận.

**Giới hạn có chủ ý:** `STORED`, `archiveRuns`, `findRuns` là fixture nội bộ; bộ test minh họa semantics và interception. Khi đưa vào production, thay in-memory lookup bằng repository có ownership/tenant guard và test cả database, events, HTTP status, transactional behavior.

## 4. Chọn cách nào theo nghiệp vụ?

### 4.1. Ghi dữ liệu: kiểm tra quyền trước

Nếu hành động thay đổi trạng thái, gửi event hoặc gọi API khác, ưu tiên kiểm tra quyền **trước** khi gây hiệu ứng. Với `archive(id)`, annotation `@PreAuthorize` chặn ngay nếu caller thiếu authority hay không sở hữu ID.

Nếu sử dụng một `@PostAuthorize` trên method đã thực hiện `repository.save(...)`, lỗi quyền **sau khi save** không tự bảo đảm rollback, đặc biệt nếu đã gọi hệ thống ngoài transaction hoặc phát sự kiện. Một số transaction có thể rollback khi ngoại lệ truyền qua đúng ranh giới, nhưng không dùng điều đó thay cho guard trước khi ghi.

Trong ví dụ, policy đọc owner từ `DocumentService.STORED`; ở hệ thống thật, phép kiểm tra quyền phải dựa vào ID, owner/tenant đã xác minh tại repository hoặc PDP, không phải thuộc tính client có thể sửa. Đồng thời cần chống **TOCTOU** (kiểm tra xong rồi owner/status bị thay đổi bởi giao dịch khác): transaction, row lock hoặc update có điều kiện tùy nghiệp vụ.

### 4.2. Trả về một object: kiểm tra quyền sau nếu cần thuộc tính kết quả

Một lời gọi `findOne(id)` có thể phải tải object để biết owner. `@PostAuthorize("returnObject.owner == authentication.name")` bảo vệ object **trước khi caller nhận nó**, nên đặc biệt phù hợp với service đọc. Với object null, expression `returnObject.owner` có thể lỗi; cần quy ước null-safety/`Optional` hoặc cho service ném not-found có chủ đích. Trong ví dụ, ID thiếu ném `NoSuchElementException`; ví dụ **không ánh xạ** ngoại lệ đó thành HTTP 404.

`@PostAuthorize` giúp chặn việc trả object không thuộc quyền nhưng **không che việc method đã chạy** và không phải phương án tốt nhất cho truy vấn lớn. Nếu có thể đưa điều kiện `WHERE owner_id = :principal` vào repository và bảo đảm tenant isolation sớm, nên làm ngay từ data layer; annotation giữ vai trò bổ sung/defense-in-depth.

### 4.3. Batch input: dùng `@PreFilter` khi việc bỏ phần tử là đúng contract

`@PreFilter` kiểm tra từng `filterObject` trước khi method nhận dữ liệu. Với danh sách `[A1, B1, A2]` cho Alice, method chỉ xử lý `[A1, A2]`. Nếu tất cả bị lọc, method vẫn có thể nhận danh sách rỗng: **đây không phải AccessDeniedException mặc định**.

Khi nhiều tham số có thể được lọc, chỉ định rõ `filterTarget`:

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents")
public void submitBatch(String batchId, List<Document> documents) {
    // Snippet minh họa trong một service, không phải class độc lập.
}
```

Để xác định tham số qua tên `documents`, biên dịch Java với `-parameters` (hoặc cơ chế đặt tên tương ứng được phiên bản framework hỗ trợ). Kiểm tra đúng loại collection; với list trong bài, dùng `new ArrayList<>(...)` vì việc lọc có thể cần xóa phần tử. Dùng trực tiếp `List.of(...)` làm input bất biến có thể gây lỗi tùy cách Spring thực thi filter. `Map` sử dụng `filterObject.value.owner` vì phần tử là entry. Spring Security cũng hỗ trợ array và stream; stream phải còn mở và chỉ tiêu thụ một lần.

Đừng dùng `@PreFilter` để sửa sai thao tác ghi batch all-or-nothing: nếu policy yêu cầu từ chối cả lô khi có một ID không hợp lệ, kiểm tra toàn bộ lô trước khi bắt đầu transaction, hoặc trả lỗi yêu cầu. Nếu nghiệp vụ cho phép xử lý phần hợp lệ, response nên công khai rõ phần nào được xử lý, phần nào bị bỏ và vì sao, với thông tin trả về phù hợp chính sách.

### 4.4. Trả danh sách: dùng `@PostFilter` khi phải lọc từng phần tử

`@PostFilter("filterObject.owner == authentication.name")` hoạt động trên tập kết quả trước khi caller nhận. Thử principal khác nhau trên cùng fixture để chắc chắn list không rò tài liệu. Với `Map<String, Document>`, truy cập `filterObject.value.owner`; cần assert cả key và ID/owner chứ không chỉ `size()`.

Lọc **sau truy vấn** có chi phí và rủi ro: service có thể đã tải hàng nghìn record rồi mới loại phần lớn; nếu đã phân trang ở DB, một page 20 bản ghi có thể chỉ còn 2 bản ghi được phép, trong khi `totalElements`/`hasNext` tính trên tập chưa lọc. Với dữ liệu lớn, lọc theo ACL/owner/tenant **ngay trong query**, bảo đảm count/pagination đồng nhất; dùng method security như guard bổ sung khi cần.

`@PostFilter` không thay thế quyết định “người gọi có được mở API list hay không”: có thể kết hợp `@PreAuthorize("hasAuthority('document:list')")` để cấm toàn bộ lời gọi trước, rồi `@PostFilter` để giới hạn từng phần tử trả về. Cần test cả mức quyền gọi và nội dung từng phần tử.

## 5. So sánh cách kiểm thử và cách xử lý lỗi

| Tình huống | Nên assert | Assertion dễ gây kết luận sai |
| --- | --- | --- |
| `@PreAuthorize` bị deny | `AccessDeniedException`; counter side effect/thân method bằng 0 | Chỉ kiểm tra exception mà không chứng minh method chưa chạy |
| `@PostAuthorize` bị deny | `AccessDeniedException`; method đã đọc đúng một lần | Tưởng method chưa chạy vì caller không thấy object |
| `@PreFilter` với input hỗn hợp | ID xuất hiện **trong thân method** chính xác | Chỉ xem input sau lời gọi (phụ thuộc mutation collection) |
| `@PostFilter` với output hỗn hợp | Caller chỉ có ID được phép, đúng owner và thứ tự nếu cần | Chỉ assert số lượng |
| Không có phần tử đạt quyền | Empty collection phù hợp contract, không tự phát sinh 403 | Coi empty list tương đương access denied |
| Thiếu đăng nhập | Test đúng cơ chế authentication/context | Tự giả định HTTP 401 trong unit method test |
| Không có tài nguyên | Xác nhận not-found theo contract | Dùng expression null không kiểm soát rồi coi SpEL exception là 404 |

Ở **test method security** ngoài HTTP, từ chối thường thể hiện qua `AccessDeniedException`; mã 401/403 là việc của web filter/entry point/exception translation và cần **MockMvc/integration test HTTP riêng** để xác minh. `@WithMockUser` tạo Authentication giả lập theo tên và authority, nhưng không kiểm chứng password/JWT signature/claim converter. Nếu app dùng OAuth2, tenant claims hoặc principal tùy biến, bổ sung test converter và test với đúng `Authentication` thực tế.

Các trường hợp regression thiết yếu: người dùng đúng quyền, thiếu authority, foreign ownership, ID không tồn tại, batch toàn hợp lệ, batch hỗn hợp, batch toàn bị lọc, kết quả list của Alice/Bob/Charlie, và gọi qua các entry point thật (controller, async/message consumer) có thể đi qua các proxy khác nhau.

## 6. Những sai lầm thường gặp

1. **Thiếu `@EnableMethodSecurity`:** thêm annotation nhưng chưa kích hoạt method security. Spring Boot Security starter không tự bảo đảm bật pre/post annotations.
2. **Dùng `new Service()` trong test:** bỏ qua Spring proxy. `self-invocation` (`this.securedMethod()`) cũng thường vượt qua interception dạng proxy.
3. **Tin vào `owner` trong JSON đầu vào:** người gọi có thể giả owner; lấy quyền theo server-side ID/tenant.
4. **Dùng `@PostAuthorize` cho thao tác có side effect:** kiểm tra sau thân method có thể quá muộn.
5. **Dùng `@PreFilter` thay cho chặn cả lô:** âm thầm bỏ object có thể vi phạm atomicity/business semantics.
6. **Chỉ test happy path và số lượng list:** không phát hiện rò ID của người khác.
7. **Chuyển `@PostFilter` thành chiến lược query mặc định:** tải dữ liệu thừa, sai phân trang, count và cache.
8. **Dùng immutable input** cho filter yêu cầu mutation hoặc map expression sai (`filterObject.owner` thay vì `filterObject.value.owner`).
9. **Nhầm `roles` với `authorities`:** `@WithMockUser(roles="ADMIN")` tạo `ROLE_ADMIN`; `authorities="document:archive"` là tên authority chính xác.
10. **Giả định mỗi annotation sinh HTTP 403:** method test và HTTP test có boundary khác nhau; `@PreFilter/@PostFilter` thường chỉ trả collection đã lọc.

## 7. Checklist áp dụng

- [ ] Xác định rõ policy cần **từ chối cả thao tác** hay **lọc từng phần tử**.
- [ ] Nếu ghi dữ liệu, chặn trái quyền **trước** khi có side effect, kiểm tra owner/tenant từ server.
- [ ] Nếu kiểm tra kết quả sau, bảo đảm method không thực hiện side effect nguy hiểm trước authorization.
- [ ] Kích hoạt `@EnableMethodSecurity`, gọi qua Spring-managed bean/proxy.
- [ ] Test với ít nhất hai principal và tập dữ liệu chứa own/foreign.
- [ ] Dùng danh sách phù hợp cho filter; kiểm tra chính xác ID/owner trong input service và output caller.
- [ ] Với dữ liệu lớn/pagination, lọc chính xác ngay trong query/data layer; kiểm tra count và giới hạn truy vấn.
- [ ] Khi áp dụng vào API, bổ sung test HTTP 401/403/404 và business side effect theo security chain thật.

## Tài liệu tham khảo

- [Spring Security — Method Security, Pre/Post Authorize và Pre/Post Filter](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — `@WithMockUser` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
