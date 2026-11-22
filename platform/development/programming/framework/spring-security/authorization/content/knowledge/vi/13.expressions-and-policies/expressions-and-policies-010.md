# Ranh giới giữa kiểm tra quyền, kiểm tra tính hợp lệ và điều kiện nghiệp vụ

> **Phạm vi:** Spring Security – authorization, nhóm **Biểu thức và chính sách**. Bài học phân định ba câu hỏi thường bị trộn lẫn trong ứng dụng Java/Spring: **ai có quyền làm?**, **dữ liệu có hợp lệ không?**, và **trạng thái nghiệp vụ có cho phép hành động không?** Nội dung dùng Spring Boot Servlet, Spring Security method security, Jakarta Bean Validation và ví dụ Java 17+. Các quyết định cụ thể cần được điều chỉnh theo hợp đồng API và mô hình miền của từng ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân loại một quy tắc thành **authorization**, **input validation**, **business invariant** hoặc quy tắc giao thoa.
2. Đặt mỗi loại kiểm tra ở lớp thích hợp: security filter/method, DTO/controller, service/domain và database.
3. Dự đoán sự khác nhau giữa yêu cầu bị từ chối do thiếu quyền, dữ liệu sai và xung đột trạng thái; giải thích khi nào HTTP 400, 401, 403, 404, 409 có thể xuất hiện.
4. Thiết kế thứ tự kiểm tra để tránh tiết lộ dữ liệu, tránh cập nhật dở và giữ tính nguyên tử khi có truy cập đồng thời.
5. Kiểm thử cả đường gọi HTTP và service, kể cả trường hợp cùng một yêu cầu mắc nhiều lỗi.

## 2. Ba câu hỏi, ba ý nghĩa

Giả sử ứng dụng quản lý hóa đơn cho phép người dùng duyệt hóa đơn.

**Kiểm tra quyền (authorization)** trả lời: *chủ thể hiện tại có được thực hiện hành động này trên tài nguyên này không?* Ví dụ: nhân viên có authority `invoice:approve` và chỉ được duyệt hóa đơn thuộc phạm vi được giao. Đầu vào là danh tính/quyền đáng tin và ngữ cảnh tài nguyên; thất bại thường là quyết định **deny**.

**Kiểm tra tính hợp lệ (validation)** trả lời: *dữ liệu được gửi có đúng kiểu, định dạng, cấu trúc và các ràng buộc đầu vào không?* Ví dụ: lý do phê duyệt không được trắng, dài tối đa 120 ký tự; ID phải là số dương. Dữ liệu có thể sai ngay cả khi người gửi là quản trị viên.

**Điều kiện nghiệp vụ (business rule/invariant)** trả lời: *hành động có hợp lệ trong trạng thái và quy trình hiện tại của miền không?* Ví dụ: chỉ hóa đơn `DRAFT` mới được phê duyệt; hóa đơn đã `APPROVED` không được phê duyệt lần nữa; tổng tiền sau điều chỉnh không được vượt hạn mức nghiệp vụ. Đây là quy tắc đúng/sai của nghiệp vụ, không đơn giản là quyền được cấp.

Ví dụ một yêu cầu `POST /api/invoices/42/approve`:

| Tình huống | Câu hỏi được kiểm tra | Phân loại |
| --- | --- | --- |
| Người gửi không có `invoice:approve` | Có được phép sử dụng chức năng duyệt không? | Quyền cấp chức năng |
| Người gửi có quyền duyệt nhưng hóa đơn thuộc người/tenant khác | Có được thao tác trên tài nguyên **này** không? | Quyền cấp tài nguyên |
| `reason = "   "` hoặc dài 200 ký tự | Payload có đáp ứng ràng buộc nhập liệu không? | Validation |
| Hóa đơn đã `APPROVED` | Có thể chuyển trạng thái thêm lần nữa không? | Business invariant |
| Hóa đơn không tồn tại | Có tìm thấy tài nguyên được yêu cầu không? | Resource lookup; cách phản hồi còn phụ thuộc chính sách bảo mật |
| Chủ thể có quyền duyệt, payload đúng, hóa đơn ở `DRAFT` | Cả ba lớp đều đạt | Có thể thực thi, nhưng còn phải bảo đảm giao dịch/đồng thời |

**Một kết quả 403 không chứng minh payload hợp lệ; một kết quả 400 không chứng minh người gọi có quyền.** Mỗi lớp giải quyết một câu hỏi khác.

### 2.1. Không phân loại theo tên annotation

- `@PreAuthorize`, `AuthorizationManager` và `hasAuthority(...)` điển hình là **authorization**.
- `@Valid`, `@NotBlank`, `@Size`, `@Positive` điển hình là **validation**.
- `if (invoice.status() != DRAFT)` hoặc phương thức `invoice.approve()` điển hình là **business rule**.
- `@Transactional`, optimistic locking và constraint ở DB giúp giữ tính nhất quán, nhưng **không thay thế** ba loại kiểm tra trên.

Đặt một điều kiện sai lớp có thể làm API trông vẫn hoạt động nhưng trả mã lỗi sai, lộ dữ liệu hoặc khó dùng lại từ job/message listener.

## 3. Ranh giới trách nhiệm theo lớp

~~~text
HTTP client
   |
   v
SecurityFilterChain
   |  authentication, CSRF (khi áp dụng), quyền URL/chức năng
   v
Controller + binding + Bean Validation
   |  parse JSON, @Valid, kích thước/định dạng
   v
Spring proxy của Service
   |  @PreAuthorize / AuthorizationManager: quyền lời gọi
   v
Service + Domain
   |  load tài nguyên trong phạm vi tin cậy
   |  quyền đối tượng/tenant/ownership, trạng thái DRAFT, invariant
   v
Repository / DB
   |  WHERE tenant_id, điều kiện cập nhật, version/lock, transaction
   v
Kết quả hoặc lỗi có phân loại
~~~

Sơ đồ mô tả **ranh giới chức năng**, không cam kết mọi advisor Spring chạy theo một thứ tự cố định. Chẳng hạn MVC có thể bind và validate tham số controller trước khi lời gọi vào service gặp `@PreAuthorize`; `@Transactional` và method-security advisors có thứ tự cấu hình riêng. Không dựa vào thứ tự ngầm định để bảo đảm an toàn.

Ở HTTP, filter chain thường là nơi hợp lý để loại sớm request không được xác thực/không có quyền tổng quát; controller đảm trách payload validation; service kiểm tra quyền theo tài nguyên và invariant; DB bảo đảm tính đúng đắn khi nhiều request cùng tranh chấp.

### 3.1. Khi nào là quy tắc bảo mật, khi nào là nghiệp vụ?

Có vùng giao thoa thật sự. Ví dụ “chỉ trưởng nhóm được duyệt khi số tiền vượt ngưỡng” vừa nói đến **vai trò của người duyệt** vừa phụ thuộc **giá trị của hóa đơn**. Hãy tách thành các vế có ý nghĩa:

~~~text
canApprove(actor, invoice):
  actor có authority duyệt?
  actor cùng tenant và được phân công?
  nếu invoice.amount > threshold: actor có quyền duyệt vượt ngưỡng?

businessPrecondition(invoice):
  invoice vẫn ở DRAFT?
  invoice không bị khóa trong kỳ kế toán?
  dữ liệu liên quan còn nhất quán?
~~~

Các điều kiện dựa vào **actor/authority và đối tượng** thường thuộc authorization policy; điều kiện mô tả **trạng thái hợp lệ của miền dù ai gọi** thuộc domain invariant. Có thể triển khai cả hai trong domain service, nhưng đặt tên, loại exception và test tách bạch.

Lưu ý: business policy cũng có thể giới hạn “ai được thao tác”. Vì vậy ranh giới là **ý nghĩa của quy tắc và hành vi khi thất bại**, không phải phân chia cứng bằng một từ khóa hay class.

## 4. Authorization: quyền cấp chức năng và quyền cấp tài nguyên

### 4.1. Quyền cấp chức năng

Một endpoint duyệt hóa đơn có thể yêu cầu authority `invoice:approve`:

~~~java
// Trích đoạn trong cấu hình SecurityFilterChain của Spring Boot Servlet.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
        .hasAuthority("invoice:approve")
    .anyRequest().authenticated()
);
~~~

Đây là quyết định theo **request**. URL permission có thể chặn phần lớn người không có quyền, nhưng không chứng minh hóa đơn cụ thể thuộc phạm vi của họ.

### 4.2. Quyền cấp phương thức

Kích hoạt method security qua `@EnableMethodSecurity`. Spring Security Starter **không tự bật** method-level authorization.

~~~java
// Trích đoạn thuộc Spring-managed service.
@PreAuthorize("hasAuthority('invoice:approve')")
public InvoiceView approve(long id, String reason) {
    // Các điều kiện trên tài nguyên vẫn cần được kiểm tra.
}
~~~

Nếu kiểm tra `@PreAuthorize` không đạt, method không được gọi. Annotation chỉ hoạt động nếu lời gọi thực tế đi qua cơ chế interception của Spring, thường là proxy; `this.approve(...)` gọi nội bộ trong cùng bean có thể bỏ qua proxy.

### 4.3. Quyền trên đối tượng và tenant

Ví dụ “Alice được duyệt hóa đơn của Alice” là quyền trên một tài nguyên. Không lấy `ownerId` hay `tenantId` do client tự khai rồi coi là bằng chứng quyền. Service phải lấy chủ thể từ `SecurityContext` đáng tin, tra tài nguyên từ repository trong đúng phạm vi tenant, và kiểm tra ACL/assignment trên dữ liệu thực.

~~~java
// Sơ đồ code bên trong service, giả sử đã load invoice.
Authentication actor = SecurityContextHolder.getContext().getAuthentication();
if (actor == null || !invoice.owner().equals(actor.getName())) {
    throw new AccessDeniedException("Access denied");
}
~~~

Với nhiều tenant, dùng **định danh ổn định** từ token/identity provider, tránh chỉ dựa vào tên hiển thị; đưa tenant constraint vào truy vấn và kiểm tra ở service/data layer. Nếu không muốn tiết lộ tài nguyên của tenant khác có tồn tại, API có thể cố ý trả 404 thống nhất cho tài nguyên vắng mặt hoặc không nhìn thấy. **HTTP 404 trong trường hợp này vẫn có thể đại diện cho quyết định bảo mật theo hợp đồng API**, không có nghĩa đây là lỗi validation.

### 4.4. Cần kiểm tra ở mấy nơi?

Các tầng có vai trò bổ sung:

- **Web:** đóng tuyến nhạy cảm, bắt buộc xác thực và quyền chung, xử lý session/CSRF.
- **Service:** bảo vệ hành động nghiệp vụ bất kể được gọi qua HTTP, job, message consumer hay test.
- **Repository/DB:** giới hạn data scope, atomic update và tránh race.

Không coi việc UI ẩn nút “Approve” là enforcement. Người dùng vẫn có thể gọi API trực tiếp. Không coi việc SQL chỉ trả các dòng thuộc owner là đủ để cho phép mọi chức năng thao tác trên các dòng đó.

## 5. Validation: dữ liệu phải đúng, dù người dùng là ai

Ví dụ đầu vào:

~~~java
public record ApproveRequest(
        @NotBlank(message = "reason is required")
        @Size(max = 120, message = "reason is too long")
        String reason) {
}
~~~

Với `jakarta.validation.constraints.NotBlank` và `Size`, lý do `null`/trắng hoặc dài quá 120 ký tự bị coi là không hợp lệ. Đặt ở điểm nhận request:

~~~java
@PostMapping("/{id}/approve")
public InvoiceView approve(@PathVariable long id,
                           @Valid @RequestBody ApproveRequest request) {
    return service.approve(id, request.reason());
}
~~~

Trong Spring MVC, `@Valid @RequestBody` kích hoạt Bean Validation khi có provider phù hợp; mặc định lỗi constraint dạng này thường gây `MethodArgumentNotValidException` và HTTP 400. JSON sai cấu trúc có thể thất bại từ bước deserialize trước cả Bean Validation. Nếu service được gọi từ CLI/job, annotation `@Valid` trên tham số controller **không tự chạy lại**; service/domain vẫn phải bảo vệ các tiền điều kiện thiết yếu.

Một số nhóm validation:

| Nhóm | Ví dụ | Nơi đặt gần nhất |
| --- | --- | --- |
| Kiểu/cấu trúc | JSON hợp lệ, trường bắt buộc, ID parse được | HTTP binding/DTO |
| Kích thước/định dạng | `@NotBlank`, `@Size(max=120)`, `@Email` | DTO + Bean Validation |
| Quan hệ giữa trường đầu vào | `start <= end`, có một trong hai lựa chọn | Custom validator hoặc value object |
| Dữ liệu hợp lệ khi không qua HTTP | Amount dương, money currency hợp lệ | Constructor/value object/service |
| Ràng buộc DB | NOT NULL, UNIQUE, CHECK | Database như hàng rào cuối |

**Validation không quyết định quyền truy cập.** Một request với `reason = "Đã kiểm tra"` hoàn toàn hợp lệ vẫn phải bị từ chối nếu user không có `invoice:approve` hoặc không có quyền trên hóa đơn.

Ngược lại, `@PreAuthorize("hasAuthority('invoice:approve')")` không làm cho chuỗi `reason` hợp lệ, không thay thế `@Size` và không sửa dữ liệu sai.

### 5.1. Tránh dùng validator để dò tài nguyên nhạy cảm

Một custom validator gọi repository để kiểm tra “invoice ID có tồn tại không” có thể dẫn đến query nhạy cảm trước authorization. Nếu ràng buộc cần quyền và trạng thái hiện tại của tài nguyên, nên kiểm tra tại ranh giới service với ngữ cảnh bảo mật và transaction phù hợp. Tách validation cấu trúc (an toàn, độc lập với quyền) khỏi dữ liệu động (có thể rò rỉ thông tin nếu kiểm tra quá sớm).

## 6. Business invariant: điều kiện của thao tác và trạng thái

Giả sử workflow:

~~~text
DRAFT -> APPROVED
DRAFT -> CANCELLED
APPROVED -> (không được APPROVE lần nữa)
CANCELLED -> (không được APPROVE)
~~~

Ngay cả người có quyền `invoice:approve` cũng không thể hợp lệ hóa thao tác “duyệt một hóa đơn đã duyệt” chỉ nhờ authority. Domain có thể trả lỗi **xung đột trạng thái** (chẳng hạn 409 theo hợp đồng REST), vì điều kiện phụ thuộc vào trạng thái hiện tại và có thể thay đổi.

~~~java
// Sơ đồ logic domain, không phải chương trình Java độc lập.
if (invoice.status() != InvoiceStatus.DRAFT) {
    throw new InvoiceStateConflictException();
}
invoice.approve();
~~~

Phân biệt:

- **Không được duyệt vì không có quyền**: thay actor/authority có thể làm quyết định khác.
- **Không được duyệt vì hóa đơn đã APPROVED**: đổi actor sang admin cũng không làm thao tác lặp trở nên hợp lệ, trừ khi nghiệp vụ định nghĩa một quyền override và workflow riêng.
- **Không được duyệt vì reason trống**: sửa payload là đủ nếu quyền và trạng thái đã hợp lệ.

Với thanh toán, tồn kho, quota và phê duyệt đồng thời, invariant phải được bảo vệ ở **thời điểm ghi có tính nguyên tử**, không chỉ bằng một `if` đọc trước rồi cập nhật sau. Dùng transaction cùng pessimistic/optimistic locking, version column hoặc conditional update (ví dụ `UPDATE ... WHERE status='DRAFT' AND version=?`); kiểm tra số dòng được cập nhật. `@Transactional` tự nó **không ngăn mọi race condition** và không phải authorization mechanism.

## 7. Thứ tự kiểm tra: bảo mật, thông điệp lỗi và side effect

Một cách suy nghĩ an toàn là **kiểm tra quyền trên dữ liệu cần truy cập trước khi tiết lộ thuộc tính nhạy cảm của dữ liệu đó**, đồng thời bảo đảm mọi invariant còn đúng ngay lúc cập nhật.

Ví dụ hợp lý cho API duyệt:

1. Request đi qua authentication/CSRF/authorization cấp URL.
2. MVC parse và kiểm tra shape của payload (các bước này có thể nằm trước kiểm tra quyền ở service).
3. Method security chặn actor thiếu authority chức năng.
4. Service tra tài nguyên trong phạm vi cho phép; xác định actor có quyền với đối tượng hay không; không cung cấp thông tin tài nguyên ẩn.
5. Kiểm tra invariant nghiệp vụ trên trạng thái hiện tại, sau đó thực hiện cập nhật nguyên tử.
6. Trả kết quả hoặc lỗi thích hợp; log/audit theo chính sách không lộ bí mật.

**Không có một “thứ tự duy nhất” áp dụng cho mọi ứng dụng Spring.** Thứ tự cụ thể chịu ảnh hưởng của filter chain, argument resolution, AOP advisors, transaction boundaries và exception handlers. Nếu có yêu cầu ưu tiên 403 trước 400, cần đặt guard ở lớp thực sự chạy đủ sớm (thường là web/request level hoặc policy trước logic đọc nhạy cảm), không chỉ gắn thêm annotation và giả định thứ tự.

### 7.1. Khi một request sai ở nhiều chỗ

Alice gửi lý do trống cho một hóa đơn của Bob và không có authority `invoice:approve`. Tùy nơi enforce, hệ thống có thể từ chối ở web filter trước khi xem body; nếu chỉ có method security tại service, MVC có thể báo input 400 trước khi gọi service. Điều đó không tự động chứng minh bảo mật bị lỗi, nhưng có thể vi phạm yêu cầu “không xác nhận gì về dữ liệu bị bảo vệ”. Hãy viết test cố định contract: người không có quyền không được suy luận sự tồn tại/thuộc tính dữ liệu nhạy cảm từ thay đổi thông điệp lỗi.

### 7.2. Tại sao không dùng `@PostAuthorize` để bảo vệ ghi?

`@PostAuthorize` xét quyền **sau khi** thân method đã chạy; nếu thao tác đã commit DB, gửi email hay gọi dịch vụ ngoài, từ chối sau đó không bảo đảm hoàn tác. Với mutate operation, ưu tiên `@PreAuthorize` cộng kiểm tra quyền đối tượng trong service trước khi ghi và kiểm tra nguyên tử tại DB.

### 7.3. Lưu ý về mã HTTP

| Lỗi và ngữ cảnh | Mã HTTP thường chọn | Cần hiểu đúng |
| --- | --- | --- |
| Chưa xác thực vào tài nguyên bảo vệ | 401 | Phụ thuộc authentication entry point; không tự suy ra trong mọi request |
| Đã xác thực nhưng thiếu quyền | 403 | Không đồng nghĩa payload sai |
| Tài nguyên không tồn tại hoặc bị cố ý ẩn | 404 | Có thể dùng để không tiết lộ sự tồn tại |
| Body/field không hợp lệ | 400 | Mặc định phổ biến của MVC với `@Valid @RequestBody` |
| Ràng buộc miền phụ thuộc trạng thái hiện tại | 409 | Thích hợp cho state conflict; không phải mọi business error đều là 409 |
| Một dạng input đúng cú pháp nhưng vi phạm semantic contract | 422 hoặc 400 tùy API | Không có ánh xạ tự động áp dụng cho mọi business rule |

Một số request POST thiếu **CSRF token** có thể bị trả 403 ngay cả khi người dùng có authority và dữ liệu đúng. Bảo vệ CSRF là vấn đề an toàn request, không phải lỗi business state. Với API dùng HTTP session/cookie, giữ CSRF protection và truyền token đúng cách; test MockMvc cho phương thức không an toàn cần `with(csrf())`.

## 8. Ví dụ Spring Boot: phân tách ba nhóm kiểm tra

Ví dụ sau chứa một ứng dụng nhỏ với in-memory storage để tập trung vào ranh giới quyết định:

- `SecurityFilterChain` + `@PreAuthorize` kiểm tra authority `invoice:approve`.
- `@Valid ApproveRequest` kiểm tra dữ liệu nhận ở controller, service kiểm tra lại invariant đầu vào cho caller khác HTTP.
- Service kiểm tra owner theo principal hiện tại, cố ý trả 404 cho invoice không nhìn thấy và invoice không tồn tại.
- Trạng thái chỉ có `DRAFT` mới chuyển sang `APPROVED`; nếu trạng thái khác thì trả 409.
- `ConcurrentHashMap.compute` cập nhật một key nguyên tử trong ví dụ in-memory. Với DB thật cần transaction, concurrency control, tenant scoping và constraints riêng.

**`src/main/java/example/boundaries/BoundaryApplication.java`** — một file Java cho một dự án Spring Boot Servlet đã có các dependency cần thiết:

~~~java
package example.boundaries;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.servlet.DispatcherType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                            .hasAuthority("invoice:approve")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // CSRF vẫn bật mặc định; POST cần CSRF token hợp lệ.
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo")
                        .authorities("invoice:approve").build(),
                User.withUsername("bob")
                        .password("{noop}demo")
                        .authorities("invoice:approve").build(),
                User.withUsername("viewer")
                        .password("{noop}demo")
                        .authorities("invoice:view").build());
        // {noop} chỉ để học; ứng dụng thật phải dùng password encoder an toàn.
    }
}

record ApproveRequest(
        @NotBlank @Size(max = 120) String reason) {
}

enum InvoiceStatus {
    DRAFT, APPROVED
}

record Invoice(long id, String owner, InvoiceStatus status, String reason) {
}

record InvoiceView(long id, InvoiceStatus status) {
}

@RestController
@RequestMapping("/api/invoices")
class InvoiceController {
    private final InvoiceService service;

    InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @PostMapping("/{id}/approve")
    InvoiceView approve(@PathVariable long id,
                        @Valid @RequestBody ApproveRequest request) {
        return service.approve(id, request.reason());
    }
}

@Service
class InvoiceService {
    private final Map<Long, Invoice> invoices = new ConcurrentHashMap<>(
            Map.of(
                    1L, new Invoice(1L, "alice", InvoiceStatus.DRAFT, ""),
                    2L, new Invoice(2L, "bob", InvoiceStatus.DRAFT, ""),
                    3L, new Invoice(3L, "alice", InvoiceStatus.APPROVED,
                                   "Already approved")));

    @PreAuthorize("hasAuthority('invoice:approve')")
    public InvoiceView approve(long id, String reason) {
        // Bảo vệ tiền điều kiện kể cả khi service được gọi ngoài MVC.
        if (reason == null || reason.isBlank() || reason.length() > 120) {
            throw new InvalidReasonException();
        }

        Authentication actor =
                SecurityContextHolder.getContext().getAuthentication();

        Invoice updated = invoices.compute(id, (key, current) -> {
            // Cố ý không tiết lộ tài nguyên không thuộc phạm vi actor.
            if (actor == null || current == null
                    || !current.owner().equals(actor.getName())) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Invoice not found");
            }

            // Invariant không phụ thuộc vào quyền của Alice hay Bob.
            if (current.status() != InvoiceStatus.DRAFT) {
                throw new InvoiceStateConflictException();
            }

            return new Invoice(current.id(), current.owner(),
                    InvoiceStatus.APPROVED, reason);
        });

        return new InvoiceView(updated.id(), updated.status());
    }
}

@ResponseStatus(HttpStatus.BAD_REQUEST)
class InvalidReasonException extends RuntimeException {
    InvalidReasonException() {
        super("Invalid approval reason");
    }
}

@ResponseStatus(HttpStatus.CONFLICT)
class InvoiceStateConflictException extends RuntimeException {
    InvoiceStateConflictException() {
        super("Invoice must be DRAFT");
    }
}
~~~

**Gradle dependencies** cho một dự án đã bật Spring Boot plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Không coi khối trên là file `build.gradle` độc lập. Đặt ứng dụng trong một dự án Spring Boot đã cấu hình plugin/Gradle wrapper; có thể chạy `./gradlew bootRun` (hoặc `gradlew.bat bootRun` trên Windows). Khi gọi POST qua browser/client có CSRF protection, phải lấy và gửi CSRF token đúng theo cơ chế ứng dụng; không chỉ gửi HTTP Basic rồi mong POST thành công. Ví dụ testing bên dưới dùng `with(csrf())` để kiểm chứng.

### 8.1. Vì sao không gộp ba quyết định vào một biểu thức SpEL?

Một biểu thức như sau là ví dụ *không nên mặc định dùng*:

~~~java
// Phản ví dụ khái niệm, không phải API production:
@PreAuthorize("hasAuthority('invoice:approve') "
        + "and @store.isDraft(#p0) "
        + "and #p1.length() <= 120")
~~~

Nó trộn authority, trạng thái DB và độ dài input vào một nhãn “access denied”; có thể làm sai mã HTTP, khiến input lỗi bị diễn đạt là thiếu quyền, và làm trạng thái bị kiểm tra **trước khi** transaction thực sự ghi. Giữ validation ở DTO/value object và business state trong service/domain sẽ dễ giải thích, test và xử lý lỗi hơn. Có thể dùng bean policy trong `@PreAuthorize` để kiểm tra quyền theo đối tượng, nhưng phải xác định rõ điều kiện nào thật sự thuộc authorization.

### 8.2. Vì sao dùng `ConcurrentHashMap.compute`?

Nếu hai request cùng approve invoice 1, phép cập nhật theo key được thực thi nguyên tử trong ví dụ, nên chỉ một request thấy trạng thái `DRAFT` và chuyển thành `APPROVED`; request còn lại gặp `InvoiceStateConflictException`. **Đây là thuộc tính của map trong demo**, không phải hành vi mặc định của một entity JPA được load rồi save. Khi chuyển sang cơ sở dữ liệu, cần transaction và cách phối hợp version/lock/conditional update thực sự; không chuyển nguyên xi giả định in-memory.

### 8.3. Vì sao owner sai trả 404?

Trong ví dụ này, ứng dụng cố ý không tiết lộ một invoice không thuộc owner. Cả “không tồn tại” và “không nhìn thấy” đều trả 404, sau khi authority cấp tính năng đã đạt. Một ứng dụng khác có thể chọn 403 nếu người gọi đã được phép biết đối tượng tồn tại. Chọn chính sách một lần rồi áp dụng nhất quán cho endpoint chi tiết, tìm kiếm, xuất, cập nhật và tải tệp.

## 9. Kiểm thử cả ba ranh giới

Kiểm thử request qua `MockMvc` để xác nhận tương tác giữa filter chain, validation và service AOP. File dưới đây là **integration test** cho ứng dụng ở trên. `@DirtiesContext` tạo trạng thái in-memory mới cho mỗi test để các ca độc lập; cách này đơn giản cho tài liệu, nhưng tốn thời gian hơn thiết lập fixture riêng.

**`src/test/java/example/boundaries/BoundaryApplicationTest.java`**:

~~~java
package example.boundaries;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class BoundaryApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void validInputWithPermissionAndDraftSucceeds() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));
    }

    @Test
    @WithMockUser(username = "viewer", authorities = "invoice:view")
    void featurePermissionIsRequired() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void blankReasonIsValidationError() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"   \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void otherOwnersInvoiceIsHidden() throws Exception {
        mvc.perform(post("/api/invoices/2/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void alreadyApprovedInvoiceIsBusinessConflict() throws Exception {
        mvc.perform(post("/api/invoices/3/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isConflict());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void postWithoutCsrfFailsBeforeBusiness() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Ý nghĩa của bộ test:**

| Test | Điểm kiểm tra | Kết quả |
| --- | --- | --- |
| Alice duyệt ID 1, lý do đúng | Quyền + validation + invariant đều đạt | 200 |
| Viewer thiếu authority | Filter chain chặn trước business | 403 |
| Alice gửi reason trắng | DTO Bean Validation | 400 |
| Alice gửi ID 2 của Bob | Quyền tài nguyên theo chính sách ẩn | 404 |
| Alice duyệt ID 3 đã APPROVED | Invariant trạng thái | 409 |
| Alice gửi POST thiếu CSRF | Bảo vệ request độc lập với business | 403 |

Cần bổ sung trong dự án thực: test request đồng thời, service gọi qua proxy, security context ở background job, tenant isolation, cập nhật DB có version, transaction rollback, và policy 404/403 chống enumeration. Với thử nghiệm validation service ngoài HTTP, gọi service qua bean Spring có mock authentication; đừng test annotation bằng `new InvoiceService()` rồi kết luận method security đã được chạy.

## 10. Java 17 độc lập: so sánh kết quả của ba loại lỗi

Đoạn này chỉ minh họa **cách phân loại quyết định**, không giả lập các filter/proxy của Spring. Lưu thành `BoundaryDemo.java`:

~~~java
import java.util.Set;

public class BoundaryDemo {
    static String approve(String user, Set<String> authorities,
                          String owner, String reason, boolean draft) {
        if (!authorities.contains("invoice:approve")
                || !user.equals(owner)) {
            return "DENIED";
        }
        if (reason == null || reason.isBlank() || reason.length() > 120) {
            return "INVALID";
        }
        if (!draft) {
            return "CONFLICT";
        }
        return "APPROVED";
    }

    public static void main(String[] args) {
        Set<String> permissions = Set.of("invoice:approve");
        System.out.println(approve("alice", permissions,
                "alice", "Reviewed", true));
        System.out.println(approve("bob", permissions,
                "alice", "Reviewed", true));
        System.out.println(approve("alice", permissions,
                "alice", " ", true));
        System.out.println(approve("alice", permissions,
                "alice", "Reviewed", false));
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac --release 17 BoundaryDemo.java
java BoundaryDemo
~~~

stdout **chính xác**:

~~~text
APPROVED
DENIED
INVALID
CONFLICT
~~~

Đổi `user`, `reason` và `draft` cho thấy một thao tác có thể thất bại bởi ba nguyên nhân độc lập. Việc kiểm tra `DENIED` trước trong ví dụ là một **chính sách lựa chọn thứ tự**, không phải bằng chứng mọi web framework luôn kiểm tra như vậy.

## 11. Các lỗi thiết kế thường gặp

### 11.1. Nhầm “không hợp lệ” thành “không có quyền”

Nếu `reason` trống mà ném `AccessDeniedException`, client nhận lỗi quyền dù sửa payload mới là cách giải quyết. Dẫn đến UX khó hiểu và audit an ninh nhiễu. Hãy dùng validation exception, và chỉ phát sinh access denied khi điều kiện về actor/permission thực sự không đạt.

### 11.2. Nhét business state vào role

Quy tắc “hóa đơn chỉ được duyệt khi DRAFT” không phải authority `ROLE_DRAFT`; trạng thái của hóa đơn thay đổi độc lập với danh tính người gọi. Thể hiện bằng domain transition hoặc policy có tên rõ; nếu chỉ đặc biệt admin được override, mô hình hóa như một **hành động khác có quyền khác** và invariant khác.

### 11.3. Chỉ kiểm tra `@Valid` ở controller

Job, message listener hoặc một service khác có thể gọi thẳng business service. Vì vậy domain invariant và validation của value object vẫn phải được bảo vệ ở nơi tái sử dụng; không phụ thuộc việc luôn có HTTP controller.

### 11.4. Chỉ kiểm tra ownership ở controller/UI

Một service được gọi qua endpoint khác có thể vô tình bỏ qua check. Bảo vệ bằng method/security policy ở lớp service hoặc domain authorization đủ gần tài nguyên; truy vấn theo tenant, kiểm thử cả đường gọi khác HTTP.

### 11.5. Đọc trạng thái rồi ghi mà không kiểm soát đồng thời

Hai request đều thấy `DRAFT`, cùng chuyển thành `APPROVED` và phát sự kiện hai lần. Dùng transaction kết hợp lock/version/conditional update, và quản lý idempotency cho API. Một lệnh `if` trong Java không tạo tính nguyên tử của DB.

### 11.6. Dùng `@PostAuthorize` cho cập nhật

Quyền được đánh giá sau thân method nên có thể đã tạo side effect. Ưu tiên chặn trước và kiểm tra lại điều kiện gắn với dữ liệu tại điểm ghi. Không mong chờ exception tự động hoàn tác email, API bên ngoài hoặc event đã phát.

### 11.7. Trả toàn bộ thông tin lỗi cho user chưa có quyền

Ví dụ “Invoice 42 của Bob đã APPROVED” lộ owner và trạng thái cho user không được thấy. Quyết định có trả 403 hay 404, log nội bộ khác client response; đặt chi tiết nhạy cảm chỉ trong kênh audit phù hợp. Không nên lộ stack trace, principal token hoặc SQL qua exception handler.

### 11.8. Biến mọi business conflict thành 403

Nếu người dùng có quyền và payload đúng nhưng hóa đơn đã khóa, trả 403 khiến client tưởng cần xin thêm quyền. Mã lỗi 409 hoặc mã domain nhất quán sẽ phản ánh hành động cần thiết của client rõ hơn. Với công việc async/batch, định nghĩa status cho từng item hay all-or-nothing theo hợp đồng chứ không tự đồng nhất với HTTP.

### 11.9. Coi kiểm thử một lớp là đủ

Bài test `@WithMockUser` cho service không chứng minh filter chain, CSRF và DTO validation; bài test controller không chạy qua Spring security proxy nếu mock service. Dùng test có mục đích riêng cho mỗi lớp và một số integration test xuyên suốt để phát hiện lỗi thứ tự hoặc thiếu interceptor.

## 12. Cách chọn ranh giới cho quy tắc mới

Khi thêm một yêu cầu, tự hỏi theo thứ tự:

1. **Có phụ thuộc danh tính, nhóm quyền, tenant hoặc quyền của chủ thể trên đối tượng không?** Nếu có, viết policy authorization có tên rõ; quyết định không đạt phải mang ngữ nghĩa deny.
2. **Có thể xác định sai/đúng chỉ từ dữ liệu đầu vào và contract của trường không?** Nếu có, dùng validation, ưu tiên kiểu bất biến/value object cho constraint cốt lõi.
3. **Có phụ thuộc trạng thái của hệ thống, giao dịch, tồn kho, hạn mức hay chuyển trạng thái không?** Nếu có, đưa vào domain/service invariant; bảo vệ khi cập nhật thật.
4. **Quy tắc ở nhiều nhóm?** Tách thành các predicate có tên, giữ nghĩa lỗi riêng, chỉ kết hợp tại điểm thực thi.
5. **Dữ liệu nào có thể bị lộ trước khi check quyền?** Chỉ hiển thị/validate những gì người dùng được biết; dùng response code và thông điệp lỗi nhất quán cho tài nguyên ẩn.
6. **Có đồng thời hoặc retry?** Dùng giao dịch, version/lock/unique constraint/idempotency key; kiểm thử race và rollback.

### Bài tập tình huống

Người dùng `alice` có authority `invoice:approve`, gửi lý do “OK” cho invoice 5. Invoice 5 thuộc tenant khác và trạng thái `APPROVED`. Điều kiện nào cần chặn trước khi nói “đã APPROVED”?

**Đáp án:** kiểm tra quyền trên invoice/tenant trước khi tiết lộ trạng thái. Có thể trả 404 thống nhất cho tài nguyên không được thấy. Dù lý do đúng và Alice có authority cấp chức năng, Alice vẫn không có quyền trên invoice 5; không nên báo chi tiết trạng thái APPROVED.

Nếu invoice 5 thuộc đúng tenant/cấp quyền của Alice, thì invariant `APPROVED` chặn phê duyệt lại; API có thể trả 409. Nếu reason trống, Bean Validation có thể trả 400 trước khi service đọc trạng thái, tùy đường đi đã cấu hình. Khi cả ba đạt, cập nhật mới được phép, với tính nguyên tử được DB bảo đảm.

## Tài liệu tham khảo chính thức

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request-level authorization và `AuthorizationManager`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interception, exception khi từ chối.
- [Spring Framework – `@RequestBody` + Bean Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): `@Valid`, `MethodArgumentNotValidException` và response 400 mặc định.
- [Spring Security – CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` trên MockMvc với unsafe HTTP methods.
- [Spring Framework – Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): ranh giới proxy, rollback và transaction semantics.
