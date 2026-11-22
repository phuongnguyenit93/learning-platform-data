# Nguyên tắc quyền tối thiểu, mặc định từ chối và kiểm tra mọi lần truy cập

## 1. Bức tranh tổng thể: vì sao cần ba nguyên tắc?

**Xác thực (authentication)** trả lời “Bạn là ai?”. **Phân quyền (authorization)** trả lời “Với danh tính và ngữ cảnh hiện tại, bạn được phép làm hành động nào trên tài nguyên nào?”. Một người dùng đã đăng nhập vẫn có thể không được xem tài liệu của đồng nghiệp, sửa hóa đơn đã khóa hoặc đọc dữ liệu của doanh nghiệp khác.

Một quyết định phân quyền thường phải xét đủ năm thành phần:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Chủ thể (principal) | Ai thực hiện? | Người dùng 42, dịch vụ nội bộ A |
| Hành động (action) | Muốn làm gì? | Đọc, tạo, sửa, phê duyệt, xóa |
| Tài nguyên (resource) | Thao tác trên đối tượng nào? | Tài liệu 123, đơn hàng 99 |
| Ngữ cảnh (context) | Điều kiện hiện tại là gì? | Tenant, chủ sở hữu, trạng thái hồ sơ |
| Chính sách (policy) | Điều kiện nào cho phép? | Có quyền đọc **và** thuộc cùng tenant **và** có quyền với tài liệu |

Có thể hình dung quyết định là `allow = policy(principal, action, resource, context)`. Không đủ thông tin để chứng minh được phép thì từ chối. Đừng đồng nhất “đã đăng nhập”, “có vai trò quản trị ở một phần hệ thống” hay “biết ID của đối tượng” với “có quyền truy cập”.

Ba nguyên tắc phối hợp nhau:

1. **Quyền tối thiểu (least privilege):** mỗi chủ thể chỉ được cấp những quyền thực sự cần cho nhiệm vụ của mình, trong phạm vi cần thiết và thời gian cần thiết.
2. **Mặc định từ chối (deny by default):** mọi hành động chưa được chính sách cho phép rõ ràng đều bị từ chối.
3. **Kiểm tra mọi lần truy cập (complete mediation):** mọi đường đi có thể dẫn tới thao tác được bảo vệ đều phải qua kiểm tra quyền phù hợp tại thời điểm thao tác.

Nguyên tắc thứ nhất thu hẹp quyền đã cấp; nguyên tắc thứ hai ngăn quyền phát sinh do cấu hình thiếu; nguyên tắc thứ ba ngăn kẻ tấn công đi vòng qua chỗ kiểm tra. Cả ba cần được thực hiện ở phía máy chủ.

## 2. Quyền tối thiểu: cấp đúng việc, đúng đối tượng, đúng phạm vi

### 2.1. Từ nhu cầu nghiệp vụ đến quyền thực thi

Giả sử ứng dụng có tài liệu với ba nhóm nhiệm vụ:

| Vai trò nghiệp vụ | Xem tài liệu thuộc phạm vi được giao | Tạo/chỉnh sửa trong phạm vi được giao | Phê duyệt | Quản trị người dùng |
| --- | :---: | :---: | :---: | :---: |
| Người xem | Có | Không | Không | Không |
| Biên tập viên | Có | Có | Không | Không |
| Người phê duyệt | Có | Theo nhiệm vụ riêng | Có | Không |
| Quản trị danh tính | Chỉ nếu được giao thêm | Không mặc nhiên | Không mặc nhiên | Có |

Đây là **ma trận minh họa**, chưa đủ để cấp quyền thực tế. “Có quyền xem” vẫn phải gắn với một tập tài liệu cụ thể: của chính mình, cùng tổ chức, được chia sẻ hoặc thuộc một dự án được giao. Quyền chức năng như `document:read` chỉ là điều kiện cần; phạm vi dữ liệu là điều kiện khác.

Một thiết kế dễ kiểm soát:

- Tách quyền theo hành động, chẳng hạn `document:read`, `document:create`, `document:update`, `document:approve`, `user:manage`. Không dùng một quyền “toàn năng” cho mọi tác vụ.
- Gắn phạm vi: tenant, dự án, chủ sở hữu, nhóm được chia sẻ và trạng thái đối tượng.
- Cấp quyền qua vai trò hoặc chính sách có quản trị; có quy trình thu hồi khi người dùng chuyển vị trí, rời tổ chức hoặc hết thời hạn được ủy quyền.
- Với tài khoản dịch vụ, chỉ cấp phạm vi API, tài nguyên và thời hạn cần thiết; không dùng khóa quản trị chung cho tác vụ chỉ cần quyền đọc.
- Tách nhiệm vụ nhạy cảm khi cần: người lập yêu cầu không tự động là người phê duyệt; hành động đặc quyền cần dấu vết kiểm toán.

**Ví dụ sai:** tài khoản hỗ trợ khách hàng có `ROLE_ADMIN` chỉ để tra cứu tình trạng một yêu cầu. Khi tài khoản bị lộ, kẻ tấn công có thể tận dụng nhiều chức năng hoàn toàn không liên quan.

**Ví dụ tốt hơn:** tài khoản có `ticket:read` và chỉ được xem những yêu cầu đã phân công cho nhóm hỗ trợ; quyền xuất toàn bộ dữ liệu hoặc thay đổi người dùng được quản lý riêng.

### 2.2. Vai trò, authority và quyền trên đối tượng không giống nhau

Trong Spring Security, một đối tượng `Authentication` có thể chứa các `GrantedAuthority`. Bộ kiểm tra `hasAuthority("document:read")` so khớp chính xác authority đó. Bộ kiểm tra `hasRole("ADMIN")` theo cấu hình thông thường kiểm tra authority có tiền tố `ROLE_`, tức `ROLE_ADMIN`; không nên nhầm hai cách viết.

Vai trò (role) giúp nhóm quyền theo công việc; authority/permission biểu diễn khả năng cụ thể; chính sách theo thuộc tính/đối tượng (ví dụ owner/tenant) quyết định liệu quyền đó áp dụng được vào tài nguyên đang yêu cầu hay không. Tên vai trò không tự kiểm tra quyền sở hữu tài liệu.

Quyền ở **cấp chức năng** và quyền ở **cấp dữ liệu** phải cùng được đáp ứng:

```text
Cho phép đọc tài liệu 123
    = có authority document:read
      VÀ tài liệu 123 thuộc tenant được phép
      VÀ người dùng có quyền trên tài liệu 123
      VÀ trạng thái tài liệu cho phép đọc
```

Nếu ứng dụng cho phép quyền chia sẻ hay ngoại lệ, diễn đạt chúng thành nhánh chính sách có thể kiểm thử. Đừng tự thêm điều kiện “là admin thì bỏ qua mọi kiểm tra” ở nhiều nơi.

## 3. Mặc định từ chối: chỉ mở những gì đã được quyết định

### 3.1. Chính sách danh sách cho phép

Ở một API, cấu hình an toàn khởi đầu bằng việc nêu rõ các đường dẫn/cách gọi công khai, các thao tác có quyền tương ứng, sau đó từ chối phần còn lại. Ví dụ:

- `GET /health/public`: công khai vì chỉ trả trạng thái vô hại đã được duyệt.
- `GET /api/documents/{id}`: cần quyền `document:read` và kiểm tra quyền với tài liệu `id`.
- `POST /api/documents`: cần quyền `document:create` và kiểm tra tenant, thuộc tính đầu vào.
- Endpoint mới, phương thức HTTP chưa xét hoặc đường dẫn quản trị chưa khai báo: từ chối cho đến khi có quy tắc cụ thể.

Từ chối mặc định làm giảm khả năng một endpoint mới “vô tình công khai” khi lập trình viên quên thêm luật. **Một thao tác đăng nhập bắt buộc (`authenticated()`) chưa phải là quyền nghiệp vụ:** nó cho phép mọi người đã đăng nhập, trong khi tác vụ có thể chỉ dành cho một nhóm nhỏ.

Cần phân biệt:

| Tình huống | Kết quả chính sách |
| --- | --- |
| Có quy tắc cho phép và đủ mọi điều kiện | Cho phép |
| Không khớp bất kỳ quy tắc cho phép nào | Từ chối |
| Có quyền chức năng nhưng sai tenant/chủ sở hữu | Từ chối |
| Thiếu dữ liệu cần thiết để xác định quyền | Từ chối an toàn |
| Hệ thống kiểm tra quyền phụ thuộc không sẵn sàng | Không suy đoán thành cho phép; xử lý lỗi thích hợp |

“Thất bại an toàn” (fail closed) không có nghĩa lỗi kỹ thuật nào cũng phải trả HTTP 403. Một lỗi hạ tầng có thể cần mã 5xx, nhưng **không được cho thực hiện hành động nhạy cảm** khi chưa xác minh quyền.

### 3.2. Điều gì không nên bị hiểu sai?

- `permitAll()` không phải lỗi nếu dùng cho tài nguyên **được xác nhận** là công khai; vấn đề là mở rộng nó quá mức, chẳng hạn `/api/**`.
- `anyRequest().authenticated()` có thể thích hợp với một ứng dụng mà mọi người đăng nhập đều có quyền truy cập mọi endpoint còn lại; nó không thay được kiểm tra quyền chi tiết cho nghiệp vụ có phân vai.
- Một số hệ thống có ngoại lệ từ chối/cho phép chồng lấn. Phải định nghĩa rõ thứ tự ưu tiên, không giả định ngẫu nhiên rằng “rule cuối thắng”.
- Tài nguyên không tồn tại và tài nguyên không được phép xem đôi khi đều được trả 404 để tránh làm lộ sự tồn tại. Việc dùng 403 hay 404 là quyết định thiết kế; **quyết định cho phép/từ chối phải đúng trước khi chọn mã trả về**.

## 4. Kiểm tra mọi lần truy cập: chặn đường vòng

### 4.1. “Mọi lần” nghĩa là mọi điểm vào và mọi đối tượng

Kiểm tra quyền một lần lúc đăng nhập chỉ chứng minh danh tính tại thời điểm đó. Trong suốt phiên làm việc, người dùng có thể đổi nhóm quyền, tài liệu đổi chủ sở hữu, yêu cầu chuyển sang tenant khác hoặc đối tượng đã bị khóa. Vì thế, ở mỗi thao tác cần tái đánh giá các điều kiện còn liên quan.

Các đường đi thường bị bỏ sót:

| Đường đi | Kiểm tra cần thiết |
| --- | --- |
| HTTP GET/POST/PATCH/DELETE | Quyền theo hành động và tài nguyên |
| Đọc `/api/documents/123` rồi đổi ID thành 124 | Quyền với chính đối tượng 124 (chống IDOR/BOLA) |
| Xuất CSV, tải file, trả ảnh/đính kèm, tải hàng loạt | Quyền trên từng phần dữ liệu được xuất |
| GraphQL resolver hoặc WebSocket message | Chính sách tại điểm truy cập thực tế |
| Tác vụ nền, consumer sự kiện, hàng đợi, lệnh nội bộ | Danh tính thực thi và quyền tương ứng; không mặc nhiên “nội bộ là tin cậy” |
| Hàm dịch vụ được gọi từ controller khác | Kiểm tra ở ranh giới dịch vụ hoặc truy vấn dữ liệu, tránh phụ thuộc duy nhất vào URL |

**Ví dụ:** giao diện ẩn nút “Xóa” đối với người dùng thường, nhưng họ vẫn gọi trực tiếp `DELETE /api/documents/123` bằng HTTP. Ẩn nút là cải thiện trải nghiệm, không phải cơ chế phân quyền.

**Ví dụ:** endpoint danh sách chỉ hiển thị tài liệu của tenant A, nhưng endpoint đọc chi tiết dùng `findById(id)`. Một tài khoản tenant A có thể đoán ID của tenant B; chính endpoint chi tiết phải giới hạn tenant và quyền đối tượng.

### 4.2. Kiểm tra gần dữ liệu được sử dụng

Một cách giảm lỗi là đưa điều kiện bảo vệ vào truy vấn:

```text
Không đủ:
  SELECT ... FROM documents WHERE id = :id

Cần (khi mô hình quyền là chủ sở hữu trong tenant):
  SELECT ... FROM documents
  WHERE id = :id AND tenant_id = :tenantId AND owner_id = :userId
```

Mô hình thực tế có thể cho phép người được chia sẻ hoặc vai trò khác. Khi đó truy vấn/chính sách phải diễn đạt đúng tất cả nhánh cho phép và phủ nhận truy cập vượt phạm vi. Lấy một tài nguyên rồi “lọc ở giao diện” là quá muộn.

Với thao tác **ghi**, phải bảo đảm quyền và điều kiện trạng thái vẫn đúng khi ghi diễn ra, nhất là khi có cập nhật đồng thời. Tùy dữ liệu, có thể dùng giao dịch, khóa, kiểm soát phiên bản hoặc câu lệnh UPDATE có điều kiện; chỉ kiểm tra trước rồi ghi vô điều kiện dễ tạo khoảng hở kiểm tra–sử dụng (TOCTOU). Một giao dịch tự nó không bảo đảm loại bỏ mọi race condition nếu không chọn cơ chế cô lập/khóa phù hợp.

### 4.3. Nên đặt kiểm tra ở những lớp nào?

1. **Lớp HTTP:** lọc các truy cập không xác thực, endpoint công khai và quyền tổng quát theo phương thức/đường dẫn.
2. **Lớp phương thức dịch vụ:** chặn hành động nghiệp vụ nhạy cảm, kể cả khi được gọi từ nhiều controller.
3. **Lớp truy cập dữ liệu/chính sách đối tượng:** giới hạn tenant, chủ sở hữu, chia sẻ, trạng thái và quyền của bản ghi cụ thể.

Các lớp này bổ sung nhau. Không nhất thiết lặp lại nguyên xi một điều kiện ở mọi lớp, nhưng mọi đường đến thao tác phải đi qua ít nhất một kiểm tra đầy đủ, đáng tin cậy cho thao tác đó. Không dựa vào frontend, dữ liệu do client tự khai về vai trò/tenant hay một hàm tiện ích có thể bị bỏ qua.

## 5. Áp dụng trong Spring Security (Servlet, Spring Security 6)

### 5.1. Bảo vệ tuyến HTTP với `SecurityFilterChain`

Đây là **mã minh họa tích hợp vào ứng dụng Spring Boot Servlet**, không phải chương trình Java chạy độc lập. Giả sử đã cấu hình cơ chế xác thực và chuyển quyền nghiệp vụ thành `GrantedAuthority` trong `Authentication`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/health/public").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.POST, "/api/documents/**")
                .hasAuthority("document:create")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("document:update")
            .requestMatchers(HttpMethod.DELETE, "/api/documents/**")
                .hasAuthority("document:delete")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Ý nghĩa:

- Danh sách `requestMatchers(...)` nêu những tuyến/phương thức đã được xem xét; `anyRequest().denyAll()` đóng các tuyến còn lại.
- Quyền `document:read` chỉ là **cửa đầu tiên**. Đọc `/api/documents/123` vẫn phải kiểm tra tài liệu 123 thuộc phạm vi được phép.
- Thứ tự các matcher có thể ảnh hưởng quy tắc được chọn: khai báo quy tắc cụ thể trước quy tắc bao quát. Nếu có nhiều `SecurityFilterChain`, kiểm tra toàn bộ phạm vi các chain để không bỏ sót endpoint.
- Ví dụ không cấu hình đăng nhập, token JWT, CORS hoặc CSRF. Những cơ chế đó phải được cấu hình đúng theo loại client; không tùy tiện tắt CSRF cho ứng dụng dùng phiên/cookie. Spring Security Reactive/WebFlux dùng `SecurityWebFilterChain` và `authorizeExchange`, không dùng nguyên xi cấu hình Servlet trên.

Nếu dùng JWT/OAuth2 resource server, chú ý bước ánh xạ claim/scope thành authority. Ví dụ cấu hình mặc định thường ánh xạ scope thành `SCOPE_<scope>`; `hasAuthority("document:read")` chỉ thành công khi hệ thống **thực sự** cấp authority đúng chuỗi này. Không giả định tên trong token tự biến thành quyền Java mong muốn.

### 5.2. Kiểm tra quyền ở tầng nghiệp vụ và dữ liệu

Giả sử tài liệu phải thuộc cùng tenant và thuộc sở hữu người dùng. Lớp dịch vụ có thể giữ điều kiện phân quyền tại điểm đọc; đoạn sau là **mã minh họa**, cần các kiểu `Document`, `DocumentRepository`, `CurrentUser` và `DocumentView` của ứng dụng.

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;
    private final CurrentUser currentUser;

    public DocumentService(DocumentRepository documents,
                           CurrentUser currentUser) {
        this.documents = documents;
        this.currentUser = currentUser;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(Long id) {
        Long tenantId = currentUser.tenantId();
        Long userId = currentUser.userId();

        Document document = documents
            .findByIdAndTenantIdAndOwnerId(id, tenantId, userId)
            .orElseThrow(() -> new DocumentNotFoundException(id));

        return DocumentView.from(document);
    }
}
```

Ở đây `@PreAuthorize` chặn người không có quyền chức năng, còn truy vấn có điều kiện loại bỏ tài liệu ngoài tenant hoặc không thuộc chủ sở hữu. Một implementation của repository có thể khai báo:

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    Optional<Document> findByIdAndTenantIdAndOwnerId(
        Long id, Long tenantId, Long ownerId);
}
```

Nếu tài liệu được chia sẻ với nhiều người, thay điều kiện `ownerId` bằng chính sách phân quyền đối tượng đúng của nghiệp vụ; không áp dụng ví dụ hẹp như một quy tắc tuyệt đối. `CurrentUser` phải lấy danh tính/tenant đã được máy chủ xác thực và kiểm chứng, không lấy `tenantId` do client gửi rồi tin ngay.

**Điểm cần nhớ khi dùng `@PreAuthorize`:** cần bật method security (ví dụ `@EnableMethodSecurity`); cơ chế thông dụng dựa trên Spring AOP proxy. Một lời gọi từ một phương thức sang phương thức khác trên **chính cùng instance** (self-invocation) có thể không đi qua proxy, nên không được lấy annotation đó làm bảo vệ duy nhất nếu còn đường gọi bỏ qua nó. Quy tắc đối tượng phải giữ ở một ranh giới thực sự được thực thi, chẳng hạn service public được gọi qua proxy và/hoặc truy vấn giới hạn dữ liệu.

### 5.3. Bài thực hành Java 17 chạy độc lập

Chương trình nhỏ sau không phụ thuộc Spring. Nó mô phỏng một chính sách “có permission, cùng tenant và đúng chủ sở hữu” để thấy rằng **một điều kiện đúng riêng lẻ không đủ cấp quyền**.

Lưu thành file `AuthorizationPrinciplesDemo.java`:

```java
import java.util.Set;

public class AuthorizationPrinciplesDemo {
    record User(long id, long tenantId, Set<String> permissions) {}
    record Document(long id, long tenantId, long ownerId) {}

    static boolean canRead(User user, Document document) {
        return user != null
            && document != null
            && user.permissions().contains("document:read")
            && user.tenantId() == document.tenantId()
            && user.id() == document.ownerId();
    }

    public static void main(String[] args) {
        User alice = new User(10, 7, Set.of("document:read"));
        User bob = new User(20, 7, Set.of("document:read"));
        User noPermission = new User(10, 7, Set.of());

        Document aliceDoc = new Document(1, 7, 10);
        Document otherTenantDoc = new Document(2, 8, 10);

        System.out.println(canRead(alice, aliceDoc));
        System.out.println(canRead(bob, aliceDoc));
        System.out.println(canRead(alice, otherTenantDoc));
        System.out.println(canRead(noPermission, aliceDoc));
    }
}
```

Biên dịch và chạy:

```bash
javac AuthorizationPrinciplesDemo.java
java AuthorizationPrinciplesDemo
```

Kết quả chuẩn (stdout):

```text
true
false
false
false
```

Giải thích từng dòng: Alice đủ quyền với tài liệu của mình; Bob có cùng permission nhưng không sở hữu tài liệu; Alice không thuộc tenant của tài liệu thứ hai; người dùng cuối là Alice về mặt định danh nhưng đã bị thu hồi permission. Hàm trả `false` với giá trị null, thể hiện quyết định mặc định từ chối khi thiếu chủ thể hoặc tài nguyên. Trong hệ thống thật, chính sách cũng phải xử lý chia sẻ, trạng thái tài liệu, ủy quyền và tính toàn vẹn danh tính.

## 6. Kiểm thử phân quyền bằng trường hợp được phép và bị từ chối

Chỉ kiểm tra “admin gọi API thành công” là chưa đủ. Mỗi hành động nhạy cảm cần tối thiểu các ca đại diện sau:

| Kiểm thử | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Truy cập hợp lệ | Đúng authority, tenant, quyền đối tượng | Cho phép |
| Chưa xác thực | Không có danh tính hợp lệ | Không được xử lý hành động; thường 401 hoặc chuyển sang đăng nhập theo cơ chế ứng dụng |
| Thiếu quyền chức năng | Đã đăng nhập nhưng thiếu `document:read` | Từ chối, thường 403 |
| Sai chủ sở hữu | Có `document:read` nhưng tài liệu thuộc người khác | Từ chối; có thể 403 hoặc 404 theo chính sách tiết lộ |
| Sai tenant | Có authority và biết ID nhưng khác tenant | Từ chối |
| Endpoint/phương thức mới | Không khai báo rule cho đường dẫn hoặc HTTP verb | Từ chối theo mặc định |
| Quyền bị thu hồi | Sau khi thu hồi, thực hiện thao tác tiếp theo | Không tiếp tục được phép theo mô hình cập nhật quyền của hệ thống |
| Điểm vào thay thế | Xuất dữ liệu, xử lý hàng loạt, consumer, lời gọi dịch vụ khác | Không thể đi vòng kiểm tra |

Với Spring MVC, có thể viết kiểm thử tích hợp bằng `MockMvc` và `spring-security-test`; ví dụ ý tưởng sau giả định đang dùng cấu hình ở mục 5 và đã nạp đúng cấu hình bảo mật vào bài test:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Bên trong một test có MockMvc tên mockMvc:
mockMvc.perform(get("/api/documents/123")
        .with(user("reader").authorities(
            new org.springframework.security.core.authority.SimpleGrantedAuthority(
                "document:read"))))
    .andExpect(status().isNotFound()); // Ví dụ: tài liệu 123 ngoài phạm vi reader

mockMvc.perform(get("/api/documents/123")
        .with(user("viewer").authorities(
            new org.springframework.security.core.authority.SimpleGrantedAuthority(
                "another:permission"))))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/admin/unknown")
        .with(user("reader")))
    .andExpect(status().isForbidden());
```

Đây là **các câu lệnh minh họa đặt trong một test**, không phải lớp Java độc lập. Kết quả 404 của trường hợp đầu chỉ đúng nếu dữ liệu thử nghiệm và handler được thiết lập để che việc tồn tại tài liệu; tùy chính sách ứng dụng, mã từ chối khác có thể hợp lệ. Đừng viết test chỉ dựa vào mã HTTP mà quên khẳng định rằng dữ liệu không bị trả về và hành động ghi không xảy ra.

Nên kết hợp kiểm thử đơn vị cho hàm chính sách, kiểm thử tích hợp cho SecurityFilterChain và lớp dịch vụ, và các ca đổi ID/chuyển tenant/đổi HTTP method. Đặc biệt kiểm tra sự khác nhau giữa người dùng cùng vai trò nhưng khác phạm vi dữ liệu.

## 7. Lỗi phổ biến và cách khắc phục

| Lỗi | Vì sao nguy hiểm | Hướng khắc phục |
| --- | --- | --- |
| Chỉ ẩn nút trên giao diện | Có thể gọi API trực tiếp | Thực thi quyền ở server |
| Chỉ dùng `authenticated()` cho mọi API | Ai đăng nhập cũng có thể gọi chức năng nhạy cảm | Tách authority theo hành động |
| Kiểm tra role nhưng không kiểm tra ID/tenant | Lộ hoặc sửa dữ liệu đối tượng khác (IDOR/BOLA) | Chính sách đối tượng và truy vấn giới hạn dữ liệu |
| Quy tắc cuối là `permitAll()` hoặc quá rộng | Endpoint mới vô tình mở | Rule công khai cụ thể, mặc định `denyAll()` |
| Tin `userId`/`tenantId` từ request | Client có thể tự nhận danh tính/phạm vi | Dùng danh tính đã xác thực và dữ liệu máy chủ kiểm chứng |
| Chỉ kiểm tra khi login hoặc khi hiển thị trang | Quyền và tài nguyên có thể đổi, tồn tại đường gọi khác | Kiểm tra ở từng lần thao tác nhạy cảm |
| Chỉ dựa vào annotation khi có self-invocation | Có đường gọi không qua proxy | Bảo vệ tại ranh giới dịch vụ thực sự và lớp dữ liệu |
| Quên xuất file, tác vụ nền, batch | Có đường truy cập ngoài controller thông thường | Kiểm kê toàn bộ điểm vào và kiểm thử đường thay thế |
| Giữ quyền sau khi chuyển vị trí hoặc hết hạn | Quyền ngày càng tích lũy | Có thời hạn, rà soát và thu hồi |
| Giả định claim JWT = authority | Quy tắc kiểm tra có thể sai hoặc thiếu | Kiểm tra ánh xạ claim/scope → GrantedAuthority thực tế |

Việc ghi log hữu ích cho phát hiện hành vi bất thường, nhưng không thay thế quyết định cho phép/từ chối. Log nên chứa chủ thể, hành động, đối tượng đã chuẩn hóa, kết quả và mã tương quan; tránh ghi token hay dữ liệu nhạy cảm không cần thiết.

## 8. Quy trình áp dụng vào một chức năng mới

1. **Xác định đối tượng và hành động:** ai muốn thực hiện thao tác gì trên tài nguyên nào, trong tenant/ngữ cảnh nào?
2. **Viết chính sách cho phép nhỏ nhất:** quyền chức năng, phạm vi đối tượng, trạng thái và ngoại lệ nghiệp vụ được phê duyệt. Nêu rõ trường hợp bị từ chối.
3. **Đặt chốt kiểm tra ở mọi đường truy cập:** HTTP, phương thức dịch vụ, truy vấn dữ liệu, job, xuất file. Không dựa vào giao diện hoặc token/claim chưa được chuyển thành quyền đáng tin.
4. **Đóng các trường hợp chưa định nghĩa:** matcher mặc định từ chối, tài khoản thiếu quyền không được tự nâng quyền, thiếu dữ liệu chính sách không được cho qua.
5. **Kiểm thử theo ma trận:** đúng người, sai người, khác tenant, thiếu permission, chưa đăng nhập, đổi ID, đổi HTTP verb, quyền bị thu hồi; bảo đảm không có dữ liệu hoặc tác động phụ trái phép.
6. **Theo dõi vòng đời quyền:** ai cấp, ai duyệt, khi nào hết hiệu lực, cách thu hồi và cách điều tra truy cập bị từ chối.

### Tự kiểm tra kiến thức

- Một nhân viên có `document:read` nhưng đọc tài liệu ở tenant khác. Nguyên tắc nào buộc phải chặn? **Quyền tối thiểu theo phạm vi đối tượng** và **kiểm tra mỗi lần truy cập**.
- Một endpoint `PATCH /api/documents/{id}` mới chưa có rule. Cách xử lý an toàn? **Từ chối mặc định**, cho đến khi phân quyền rõ.
- Giao diện đã ẩn nút “Xóa”. API xóa có cần kiểm tra lại? **Có**; frontend không là ranh giới bảo mật.
- Truy vấn chỉ có `WHERE id = :id` dù API đã kiểm tra permission chung. Còn thiếu gì? **Giới hạn tenant/chủ sở hữu hoặc chính sách chia sẻ của đối tượng**.
- Khi hệ thống không xác định được quyền do dữ liệu chính sách bị lỗi, có cho thao tác nhạy cảm chạy tiếp? **Không**; từ chối an toàn và xử lý lỗi phù hợp.

**Ghi nhớ:** “Có thể làm gì” phải được cấp tối thiểu; “không được cấp rõ ràng” phải bị từ chối; và “được phép với đối tượng này ngay lúc này hay không” phải được xác minh trên mọi đường dẫn thực sự có thể thực hiện thao tác.