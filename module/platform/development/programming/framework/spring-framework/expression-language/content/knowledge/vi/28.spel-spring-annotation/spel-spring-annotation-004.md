# SpEL trong @PreAuthorize và các annotation bảo mật

Spring Security dùng Spring Expression Language (SpEL) để viết điều kiện phân quyền ngay trên method thông qua các annotation như `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`. Biểu thức có thể kiểm tra authority của người dùng hiện tại, đọc tham số method, gọi một bean chuyên trách kiểm tra quyền hoặc lọc dữ liệu theo chủ sở hữu.

Các annotation này thuộc **method security**. Chúng bảo vệ lời gọi method đi qua proxy Spring, bổ sung cho cấu hình bảo mật ở tầng HTTP. Muốn dùng SpEL trong method security, ứng dụng phải bật hỗ trợ tương ứng và gọi method qua Spring-managed bean.

## 1. Bật method security

Với Spring Security hiện đại, bật method security bằng `@EnableMethodSecurity` trên một class cấu hình:

    @Configuration
    @EnableMethodSecurity
    public class SecurityConfiguration {
    }

`prePostEnabled` mặc định là true, nên các annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` được bật.

Nếu ứng dụng cần các annotation role-based cũ hơn, có thể bật thêm:

    @Configuration
    @EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
    )
    public class SecurityConfiguration {
    }

Trong các ứng dụng Spring Security phiên bản cũ, cấu hình thường dùng `@EnableGlobalMethodSecurity(prePostEnabled = true)`. Khi nâng cấp, nên dùng annotation tương ứng với phiên bản Spring Security của dự án.

Method security hoạt động thông qua cơ chế AOP/proxy của Spring. Chỉ đặt annotation lên method không đủ nếu object được gọi không do Spring quản lý hoặc lời gọi không đi qua proxy.

## 2. Dùng @PreAuthorize để kiểm tra trước khi gọi method

`@PreAuthorize` đánh giá biểu thức trước khi method body được thực thi. Nếu biểu thức trả về false, Spring Security từ chối lời gọi và method không được chạy.

Ví dụ chỉ cho quản trị viên:

    @PreAuthorize("hasRole('ADMIN')")
    public void deleteUser(Long userId) {
        userService.deleteById(userId);
    }

Hoặc cho phép người có authority cụ thể:

    @PreAuthorize("hasAuthority('invoice:read')")
    public Invoice getInvoice(Long invoiceId) {
        return invoiceRepository.findById(invoiceId)
                .orElseThrow();
    }

Có thể kết hợp nhiều điều kiện:

    @PreAuthorize(
        "hasAuthority('invoice:read') and " +
        "@invoiceAuthorization.canRead(authentication, #invoiceId)"
    )
    public Invoice getInvoice(@P("invoiceId") Long invoiceId) {
        return invoiceRepository.findById(invoiceId)
                .orElseThrow();
    }

Trong ví dụ này, người gọi phải có authority `invoice:read` và bean `invoiceAuthorization` phải xác nhận họ được đọc invoice cụ thể. Đây là cách kết hợp quyền tổng quát với kiểm tra quyền trên tài nguyên.

## 3. Các đối tượng và hàm bảo mật có sẵn trong expression

Expression root của method security cung cấp các thông tin và hàm bảo mật thường dùng:

| Thành phần | Ý nghĩa |
|---|---|
| `authentication` | Authentication hiện tại |
| `principal` | Principal của người dùng hiện tại |
| `hasRole('ADMIN')` | Kiểm tra role, mặc định có tiền tố `ROLE_` |
| `hasAnyRole('ADMIN', 'SUPPORT')` | Kiểm tra có ít nhất một role |
| `hasAuthority('invoice:read')` | Kiểm tra authority chính xác |
| `hasAnyAuthority(...)` | Kiểm tra có ít nhất một authority |
| `isAuthenticated()` | Kiểm tra trạng thái đã xác thực |
| `permitAll()` / `denyAll()` | Cho phép hoặc từ chối vô điều kiện |
| `hasPermission(...)` | Kiểm tra quyền qua PermissionEvaluator |

Có thể truy cập thông tin người dùng qua property:

    authentication.name
    principal.username

Ví dụ:

    @PreAuthorize("#username == authentication.name")
    public Profile getMyProfile(String username) {
        return profileRepository.findByUsername(username);
    }

Biểu thức này chỉ cho phép người gọi truy cập profile có username trùng với tên trong Authentication hiện tại. Với ứng dụng nhiều tenant hoặc có quy tắc ownership phức tạp, nên kiểm tra thêm tenant và trạng thái tài nguyên qua một authorization service.

## 4. Phân biệt role và authority

`hasRole` và `hasAuthority` có cách so khớp khác nhau:

- `hasRole('ADMIN')` thường kiểm tra authority `ROLE_ADMIN`, do role prefix mặc định là `ROLE_`.
- `hasAuthority('invoice:read')` so khớp chính xác authority `invoice:read`.

Ví dụ:

    @PreAuthorize("hasRole('ADMIN') or hasAuthority('invoice:approve')")
    public void approveInvoice(Long invoiceId) {
        ...
    }

Không nên truyền sẵn tiền tố `ROLE_` vào `hasRole` nếu cấu hình đang dùng prefix mặc định; hãy dùng `hasRole('ADMIN')`. Nếu ứng dụng tùy chỉnh role prefix, kết quả kiểm tra role sẽ tuân theo cấu hình đó.

Role thường biểu diễn nhóm quyền rộng như ADMIN hoặc SUPPORT. Authority thường biểu diễn hành động cụ thể như `invoice:read`, `invoice:approve` hoặc `customer:export`. Chọn quy ước nhất quán để tránh annotation kiểm tra sai chuỗi quyền.

## 5. Truy cập tham số method

SpEL có thể tham chiếu tham số method bằng tên:

    @PreAuthorize("#ownerId == authentication.name")
    public Document findDocument(String ownerId) {
        ...
    }

Để tên tham số có thể được phát hiện ổn định, nên biên dịch Java với tùy chọn `-parameters` hoặc khai báo tên bằng annotation `@P` của Spring Security:

    public Document findDocument(
            @P("ownerId") String ownerId) {
        ...
    }

Nếu không có tên tham số, có thể dùng chỉ số:

    @PreAuthorize("#p0 == authentication.name")
    public Document findDocument(String ownerId) {
        ...
    }

Các alias `#p0` và `#a0` tham chiếu tham số đầu tiên; `#p1` và `#a1` tham chiếu tham số thứ hai. Cách dùng chỉ số ít phụ thuộc metadata tên tham số nhưng kém dễ đọc khi method có nhiều đối số.

Với method có nhiều tham số, hãy dùng tên rõ ràng và kiểm thử expression trên cấu hình build thực tế. Không giả định tên biến trong source luôn có sẵn ở runtime nếu compiler không giữ metadata.

## 6. Gọi bean kiểm tra quyền bằng @beanName

Method-security expression có thể gọi bean do Spring quản lý bằng cú pháp `@beanName`. Đây là cách phù hợp để đặt quy tắc domain phức tạp trong Java thay vì nhồi nhiều logic vào chuỗi SpEL.

Ví dụ:

    @Component("documentAuthorization")
    public class DocumentAuthorization {

        public boolean canEdit(
                Authentication authentication,
                Long documentId) {
            // Kiểm tra owner, tenant và trạng thái tài liệu.
            return ...;
        }
    }

    @PreAuthorize(
        "hasAuthority('document:write') and " +
        "@documentAuthorization.canEdit(authentication, #documentId)"
    )
    public void updateDocument(
            @P("documentId") Long documentId,
            UpdateDocumentRequest request) {
        ...
    }

Bean được Spring Security resolve trong method-security expression context. Nếu ứng dụng thay thế expression handler mặc định, cần bảo đảm cấu hình mới vẫn hỗ trợ bean resolution theo cách dự án yêu cầu.

Authorization bean nên có method nhỏ, tên rõ ràng và chủ yếu đọc trạng thái để quyết định quyền. Không nên dùng method kiểm tra quyền để ghi dữ liệu, gửi thông báo hoặc thực hiện một side effect khác.

## 7. Dùng hasPermission cho quyền trên tài nguyên

Khi ứng dụng có mô hình quyền theo object, có thể dùng `hasPermission`:

    @PreAuthorize(
        "hasPermission(#documentId, 'Document', 'READ')"
    )
    public Document getDocument(
            @P("documentId") Long documentId) {
        ...
    }

Hoặc truyền trực tiếp object:

    @PreAuthorize("hasPermission(#document, 'WRITE')")
    public void updateDocument(Document document) {
        ...
    }

`hasPermission` ủy quyền quyết định cho PermissionEvaluator được cấu hình trong Spring Security. Nếu ứng dụng dùng ACL hoặc một permission model riêng, cần cung cấp PermissionEvaluator tương ứng. Không có evaluator phù hợp thì không nên giả định expression sẽ tự hiểu các quyền domain.

Với kiểm tra ownership đơn giản, một authorization bean chuyên biệt có thể dễ đọc hơn. Với hệ thống permission tổng quát, `hasPermission` giúp thống nhất cách kiểm tra quyền trên nhiều loại tài nguyên.

## 8. Dùng @PostAuthorize để kiểm tra kết quả trả về

`@PostAuthorize` đánh giá biểu thức sau khi method đã thực thi. Biến `returnObject` tham chiếu kết quả method:

    @PostAuthorize(
        "returnObject.owner.username == authentication.name"
    )
    public Document findDocument(Long documentId) {
        return documentRepository.findById(documentId)
                .orElseThrow();
    }

Ví dụ này kiểm tra người dùng hiện tại có phải chủ sở hữu document được trả về hay không. Nếu biểu thức false, Spring Security từ chối kết quả trả về cho caller.

Vì method body đã chạy trước khi kiểm tra hậu điều kiện, không nên dùng `@PostAuthorize` làm lớp bảo vệ duy nhất cho thao tác có side effect như chuyển tiền, xóa dữ liệu hoặc gửi thông báo. Với thao tác cần ngăn việc thực thi trái phép ngay từ đầu, dùng `@PreAuthorize`.

`@PostAuthorize` hữu ích khi quyết định quyền phụ thuộc vào object chỉ xác định được sau khi truy vấn. Dù vậy, hãy cân nhắc truy vấn có điều kiện theo user hoặc tenant để không tải dữ liệu ngoài phạm vi rồi mới từ chối ở cuối.

## 9. Dùng @PreFilter và @PostFilter

Hai annotation filter dùng biến `filterObject` để biểu diễn phần tử đang được kiểm tra.

**@PreFilter** lọc collection được truyền vào method trước khi method chạy:

    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "documents"
    )
    public void updateDocuments(List<Document> documents) {
        documentService.updateAll(documents);
    }

Nếu method có nhiều tham số dạng collection, `filterTarget` chỉ rõ tham số nào cần lọc. Nếu chỉ có một tham số phù hợp, có thể bỏ thuộc tính này.

**@PostFilter** lọc collection mà method trả về:

    @PostFilter(
        "filterObject.owner == authentication.name"
    )
    public List<Document> findDocuments() {
        return documentRepository.findAll();
    }

Trong mỗi lần đánh giá predicate, `filterObject` là phần tử hiện tại. Kết quả chỉ giữ lại phần tử thỏa điều kiện.

Filtering ở tầng method không thay thế truy vấn dữ liệu có phân quyền. Với collection lớn, nên lọc ngay ở repository hoặc database theo user/tenant để giảm dữ liệu được tải và xử lý. `@PostFilter` chỉ lọc kết quả sau khi method đã chạy; nó không đảo ngược side effect đã xảy ra trong method.

## 10. Phân biệt các annotation bảo mật

| Annotation | Thời điểm | Mục đích |
|---|---|---|
| `@PreAuthorize` | Trước method | Kiểm tra điều kiện truy cập |
| `@PostAuthorize` | Sau method | Kiểm tra kết quả trả về |
| `@PreFilter` | Trước method | Lọc collection đầu vào |
| `@PostFilter` | Sau method | Lọc collection kết quả |
| `@Secured` | Trước method | Kiểm tra danh sách authority/role tĩnh |
| `@RolesAllowed` | Trước method | Kiểm tra role theo JSR-250 |

`@Secured` và `@RolesAllowed` không phải annotation chứa SpEL expression. Chúng dùng danh sách role/authority tĩnh. Muốn biểu đạt điều kiện động dựa trên tham số, principal hoặc dữ liệu domain, dùng nhóm annotation pre/post.

Ví dụ:

    @Secured("ROLE_ADMIN")
    public void rebuildIndex() {
        ...
    }

    @RolesAllowed({"ADMIN", "SUPPORT"})
    public void viewSupportDashboard() {
        ...
    }

Muốn bật hai nhóm annotation này, cấu hình `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)`.

## 11. Method security và Spring proxy

Method security thường được thực thi qua Spring AOP proxy. Vì vậy, lời gọi phải đi qua proxy của bean được Spring quản lý.

Một trường hợp dễ bỏ sót là self-invocation:

    @Service
    public class InvoiceService {

        public void process(Long id) {
            approve(id); // Gọi nội bộ trên this
        }

        @PreAuthorize("hasAuthority('invoice:approve')")
        public void approve(Long id) {
            ...
        }
    }

Lời gọi `approve(id)` từ method `process` đi trực tiếp trên cùng instance, không đi qua proxy bên ngoài. Do đó, interceptor method security có thể không được kích hoạt cho lời gọi nội bộ này.

Hãy đặt ranh giới bảo mật ở method được gọi qua bean proxy từ bên ngoài, hoặc tách thao tác được bảo vệ sang một Spring bean riêng. Tránh dựa vào annotation trên method nội bộ mà không kiểm thử đường gọi thực tế.

Cũng cần kiểm tra method visibility và kiểu proxy mà ứng dụng sử dụng. Cách an toàn là đặt annotation trên service method được gọi qua Spring bean và kiểm thử bằng cách lấy bean từ ApplicationContext thay vì tự khởi tạo object bằng `new`.

## 12. Kiểm thử method-security expression

Nên kiểm thử cả trường hợp được phép và bị từ chối. Spring Security Test cung cấp các annotation như `@WithMockUser` để thiết lập Authentication cho test:

    @Test
    @WithMockUser(authorities = "invoice:read")
    void userCanReadInvoice() {
        Invoice invoice = invoiceService.getInvoice(10L);
        assertNotNull(invoice);
    }

Và trường hợp thiếu authority:

    @Test
    @WithMockUser(authorities = "invoice:write")
    void userCannotReadInvoiceWithoutReadAuthority() {
        assertThrows(
                AccessDeniedException.class,
                () -> invoiceService.getInvoice(10L)
        );
    }

Các test nên gọi method qua bean Spring được inject để proxy và method-security interceptor thực sự hoạt động. Với expression dùng tham số, hãy kiểm tra cách bind tên tham số trên build thực tế. Với authorization bean hoặc PermissionEvaluator, test cả trường hợp owner, non-owner, sai tenant và tài nguyên không tồn tại theo chính sách của ứng dụng.

## 13. Nguyên tắc thiết kế expression an toàn

- Dùng `@PreAuthorize` cho quyết định cần thực hiện trước method body.
- Dùng `hasAuthority` cho quyền hành động cụ thể; dùng `hasRole` cho role theo quy ước prefix.
- Dùng `#parameter` hoặc `#p0` để tham chiếu đối số; cấu hình metadata hoặc `@P` để tên tham số ổn định.
- Chuyển logic domain phức tạp vào authorization bean hoặc PermissionEvaluator.
- Không đặt side effect trong method chỉ có nhiệm vụ kiểm tra quyền.
- Không dùng `@PostAuthorize` thay cho kiểm tra trước đối với hành động có side effect.
- Hạn chế `@PostFilter` trên collection lớn; ưu tiên truy vấn có phân quyền tại repository.
- Đảm bảo lời gọi đi qua Spring proxy và test bằng Spring-managed bean.
- Không ghép dữ liệu người dùng trực tiếp vào chuỗi SpEL động; giữ expression trong code đáng tin cậy và truyền dữ liệu qua tham số.

## 14. Ghi nhớ

Spring Security dùng SpEL trong `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` để kiểm tra quyền hoặc lọc dữ liệu ở ranh giới method. Expression có thể dùng Authentication, principal, role/authority, tham số method, `returnObject`, `filterObject`, bean reference và `hasPermission`. Bật method security bằng `@EnableMethodSecurity`, đặt annotation trên Spring-managed bean và bảo đảm lời gọi đi qua proxy. Dùng pre-authorization để ngăn method chạy khi không có quyền; post-authorization chỉ kiểm tra sau khi method đã thực thi. Giữ authorization logic rõ ràng, giới hạn side effect và kiểm thử cả đường gọi được phép lẫn bị từ chối.
