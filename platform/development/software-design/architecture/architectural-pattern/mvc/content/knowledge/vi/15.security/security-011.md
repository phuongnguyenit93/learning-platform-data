# Kiểm thử truy cập trái phép và rò rỉ dữ liệu

Một ứng dụng MVC có thể xác thực người dùng thành công nhưng vẫn để lộ dữ liệu nếu kiểm tra quyền không đầy đủ. Ví dụ, người dùng đã đăng nhập thay mã đơn hàng trên URL để xem đơn của người khác; nhân viên thường gọi được endpoint quản trị; hoặc API trả toàn bộ entity khiến response chứa email nội bộ, địa chỉ riêng hay trường trạng thái không dành cho client.

**Kiểm thử truy cập trái phép và rò rỉ dữ liệu** xác minh rằng mỗi request chỉ được thực hiện khi danh tính và quyền phù hợp, đồng thời phản hồi chỉ chứa dữ liệu mà người gọi được phép xem. Trong mô hình **Model–View–Controller (MVC)**, việc này liên quan đến filter bảo mật, Controller, dịch vụ nghiệp vụ, truy vấn dữ liệu và hợp đồng của View/API. Kiểm tra ở một lớp duy nhất thường không đủ.

Bài học này tập trung vào cách xây dựng ma trận quyền, kiểm tra truy cập ngang và dọc, phát hiện IDOR/BOLA, kiểm tra dữ liệu trả về và viết test âm/dương cho ứng dụng web. Mục tiêu là biến chính sách bảo mật thành các tình huống kiểm thử có thể lặp lại.

## 1. Phân biệt xác thực và phân quyền

Hai câu hỏi cần được trả lời cho mỗi request:

- **Xác thực (authentication):** Ai đang gửi request? Ứng dụng có xác minh được danh tính đó không?
- **Phân quyền (authorization):** Danh tính này có được phép thực hiện hành động trên tài nguyên cụ thể không?

Người dùng đăng nhập thành công chỉ chứng minh ứng dụng đã nhận diện họ. Điều đó không có nghĩa họ được xem mọi đơn hàng, sửa mọi hồ sơ hoặc gọi mọi chức năng.

Ví dụ:

| Tình huống | Kết quả mong đợi |
|---|---|
| Request không có thông tin xác thực đến endpoint riêng tư | Bị từ chối hoặc chuyển đến đăng nhập theo loại ứng dụng |
| Người dùng thường truy cập chức năng chỉ dành cho quản trị viên | Bị từ chối |
| Người dùng A xem tài nguyên thuộc người dùng B | Bị từ chối theo chính sách truy cập đối tượng |
| Người dùng A xem tài nguyên của chính mình | Được phép nếu vai trò và trạng thái đáp ứng chính sách |
| Quản trị viên truy cập chức năng quản trị | Được phép nếu tài khoản có quyền tương ứng |

Với API, request chưa xác thực thường nhận 401; người dùng đã xác thực nhưng thiếu quyền thường nhận 403. Ứng dụng có thể dùng 404 để che giấu sự tồn tại của tài nguyên theo một chính sách nhất quán. Với ứng dụng HTML, request chưa đăng nhập có thể được redirect đến trang đăng nhập.

## 2. Những lớp bảo vệ trong ứng dụng MVC

Không nên đặt toàn bộ bảo mật vào một câu lệnh kiểm tra trong Controller. Một request có thể đi qua nhiều lớp:

1. Filter hoặc security middleware xác thực request và tạo security context.
2. Quy tắc URL kiểm tra quyền truy cập ở mức endpoint.
3. Controller nhận request và gọi use case.
4. Application service kiểm tra quyền trên hành động hoặc tài nguyên.
5. Repository truy vấn dữ liệu trong phạm vi người dùng hoặc tenant được phép.
6. DTO/View Model giới hạn các trường được trả về.

~~~mermaid
flowchart TD
    R[HTTP request] --> F[Security Filter]
    F -->|Chưa xác thực| U[401 hoặc redirect đăng nhập]
    F -->|Đã xác thực| P[URL / Method Authorization]
    P -->|Không đủ quyền| D[403 hoặc 404 theo chính sách]
    P -->|Được phép vào endpoint| C[Controller]
    C --> A[Application Service]
    A --> O[Kiểm tra quyền trên đối tượng]
    O -->|Không có quyền| X[Từ chối]
    O -->|Có quyền| Q[Repository với phạm vi truy cập]
    Q --> M[DTO / View Model]
    M --> V[HTML hoặc JSON an toàn]
~~~

Mỗi lớp giải quyết một loại rủi ro:

- Filter và URL authorization bảo vệ cổng vào.
- Method/service authorization bảo vệ thao tác nghiệp vụ.
- Kiểm tra quyền đối tượng bảo vệ từng bản ghi.
- Truy vấn có điều kiện người dùng/tenant giảm nguy cơ đọc nhầm dữ liệu.
- DTO và View Model hạn chế rò rỉ trường.

Các lớp này bổ sung cho nhau. Một endpoint có role ADMIN vẫn có thể có lỗi truy cập ngang nếu người dùng có role đó chỉ được quản lý một tập tài nguyên nhất định.

## 3. Lập ma trận quyền trước khi viết test

Ma trận quyền (authorization matrix) liệt kê actor, tài nguyên, hành động và kết quả mong đợi. Nó giúp phát hiện các trường hợp bị bỏ quên như người dùng đã đăng nhập nhưng không phải chủ sở hữu.

Ví dụ với chức năng đơn hàng:

| Actor | Xem đơn của mình | Xem đơn người khác | Hủy đơn của mình | Quản lý mọi đơn |
|---|---:|---:|---:|---:|
| Anonymous | Từ chối | Từ chối | Từ chối | Từ chối |
| Customer A | Cho phép | Từ chối | Theo trạng thái đơn | Từ chối |
| Customer B | Cho phép | Từ chối | Theo trạng thái đơn | Từ chối |
| Support agent | Theo phạm vi hỗ trợ | Theo phạm vi hỗ trợ | Theo chính sách | Không mặc định |
| Administrator | Cho phép | Cho phép | Theo chính sách | Cho phép |

Ma trận cần phản ánh chính sách thực tế của sản phẩm. Ví dụ, nhân viên hỗ trợ có thể xem đơn thuộc khu vực được phân công, nhưng không có quyền xem tất cả đơn hàng. Hãy mô tả phạm vi đó rõ ràng thay vì dùng một role chung rồi giả định mọi thao tác đều được phép.

Với mỗi dòng trong ma trận, nên có:

- Một test chứng minh hành động được phép hoạt động.
- Một hoặc nhiều test chứng minh hành động bị cấm.
- Kiểm tra response không tiết lộ dữ liệu ngoài phạm vi.
- Kiểm tra trạng thái dữ liệu không bị thay đổi khi request bị từ chối.

## 4. Truy cập trái phép theo chiều dọc và chiều ngang

### 4.1. Vertical privilege escalation

Truy cập trái phép theo chiều dọc xảy ra khi người dùng có quyền thấp thực hiện chức năng dành cho vai trò cao hơn.

Ví dụ:

- Customer gọi endpoint khóa tài khoản.
- Nhân viên thường truy cập trang quản trị.
- Người dùng không có quyền thay đổi giá sản phẩm.
- Request tự thêm trường role=ADMIN vào payload cập nhật hồ sơ.

Test cần xác minh cả endpoint HTML và API, cũng như những thao tác có thể được gọi trực tiếp mà không đi qua giao diện.

### 4.2. Horizontal privilege escalation

Truy cập trái phép theo chiều ngang xảy ra khi người dùng có cùng vai trò nhưng truy cập dữ liệu của nhau.

Ví dụ:

- Customer A thay orderId trong URL để xem đơn của Customer B.
- Người dùng thay userId trong request body để cập nhật hồ sơ người khác.
- Một tenant đọc báo cáo thuộc tenant khác.

Kiểm tra role đơn thuần không ngăn được loại lỗi này. Hệ thống phải xác minh quyền trên đối tượng cụ thể, thường dựa trên danh tính đã xác thực, quyền sở hữu, quan hệ được chia sẻ hoặc tenant context.

## 5. IDOR và BOLA là gì?

**IDOR (Insecure Direct Object Reference)** là lỗi xảy ra khi ứng dụng dùng một định danh do client cung cấp để truy cập đối tượng nhưng không kiểm tra quyền của người gọi trên đối tượng đó.

**BOLA (Broken Object Level Authorization)** là cách gọi phổ biến trong bảo mật API cho lỗi thiếu phân quyền ở cấp đối tượng. Cả hai khái niệm nhấn mạnh cùng một vấn đề: biết ID không đồng nghĩa có quyền truy cập tài nguyên.

Ví dụ endpoint:

~~~http
GET /api/orders/10042
~~~

Nếu ứng dụng chỉ tải đơn hàng theo ID:

~~~java
Order order = orderRepository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);
return mapper.toResponse(order);
~~~

thì người dùng có thể thử thay 10042 bằng ID khác. UUID khó đoán hơn số tăng tuần tự, nhưng không phải cơ chế phân quyền. Một định danh không thể thay thế kiểm tra quyền.

### 5.1. Kiểm tra quyền sở hữu ở tầng truy vấn

Một cách rõ ràng là giới hạn truy vấn theo cả ID tài nguyên và danh tính chủ sở hữu:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {
    Optional<Order> findByIdAndOwnerId(Long id, Long ownerId);
}
~~~

Dịch vụ truy vấn nhận user ID từ security context đã xác thực:

~~~java
@Transactional(readOnly = true)
public OrderDetailView getVisibleOrder(Long orderId, Long currentUserId) {
    Order order = orderRepository
            .findByIdAndOwnerId(orderId, currentUserId)
            .orElseThrow(OrderNotFoundException::new);

    return mapper.toDetailView(order);
}
~~~

Không lấy currentUserId từ tham số query hoặc body do client tự gửi. Danh tính phải đến từ principal/security context đã được xác minh. Nếu sản phẩm cần hỗ trợ nhân viên hoặc người được ủy quyền, hãy mở rộng chính sách bằng một authorization service có quy tắc rõ.

### 5.2. Kiểm tra quyền sau khi tải đối tượng

Một cách khác là tải đối tượng rồi gọi policy kiểm tra quyền:

~~~java
Order order = orderRepository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

authorizationService.checkCanRead(currentUser, order);
return mapper.toDetailView(order);
~~~

Cách này phù hợp khi chính sách phức tạp hơn một điều kiện owner ID. Cần bảo đảm mọi đường truy cập đến đối tượng đều đi qua kiểm tra, kể cả các use case khác như export, download file hoặc thao tác nền.

## 6. Phân quyền ở URL và method trong Spring Security

Spring Security có thể bảo vệ endpoint theo vai trò hoặc authority. Ví dụ:

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/assets/**").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .requestMatchers("/account/**").authenticated()
                        .anyRequest().denyAll()
                )
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

Trong ví dụ, chỉ trang chủ, trang đăng nhập và tài nguyên tĩnh được công khai; đường dẫn admin yêu cầu role ADMIN, account yêu cầu người dùng đã đăng nhập, còn route chưa được khai báo bị từ chối theo mặc định. Cấu hình thực tế cần bổ sung CSRF, session policy, API authentication và các cơ chế khác theo loại ứng dụng. Không dùng permitAll cho endpoint chỉ vì Controller dự định tự kiểm tra sau đó.

Method security có thể bảo vệ use case:

~~~java
@PreAuthorize("hasAuthority('ORDER_CANCEL')")
public void cancelOrder(Long orderId, Long currentUserId) {
    // Kiểm tra quyền trên chính đơn hàng vẫn cần được thực hiện.
}
~~~

Authority ORDER_CANCEL cho biết actor được phép thực hiện loại hành động nào. Dịch vụ vẫn phải kiểm tra trạng thái đơn và quyền trên orderId cụ thể. Role/authority cấp chức năng và quyền đối tượng là hai lớp kiểm tra khác nhau.

## 7. Không tin userId, role hoặc tenantId do client gửi

Một lỗi thường gặp là dùng dữ liệu trong request để xác định người thực hiện thao tác:

~~~java
@PostMapping("/api/profile")
public void update(@RequestBody ProfileUpdateRequest request) {
    profileService.update(request.userId(), request.displayName());
}
~~~

Nếu client được tự chọn userId, họ có thể thử cập nhật hồ sơ của người khác. Tương tự, không tin các trường role, isAdmin, ownerId, accountBalance hoặc tenantId do client gửi.

Hãy lấy actor từ security context:

~~~java
@PostMapping("/api/profile")
public void update(
        @AuthenticationPrincipal AppPrincipal principal,
        @Valid @RequestBody ProfileUpdateRequest request
) {
    profileService.updateOwnProfile(
            principal.userId(),
            request.displayName()
    );
}
~~~

Request DTO chỉ chứa các trường được phép sửa:

~~~java
public record ProfileUpdateRequest(
        @NotBlank @Size(max = 100) String displayName
) {}
~~~

Nếu cần thay đổi email hoặc số điện thoại, hãy định nghĩa use case riêng có xác minh bổ sung. Không nhận role, owner ID hoặc trạng thái nội bộ trong DTO cập nhật hồ sơ thông thường.

## 8. Kiểm tra cách ly tenant

Với ứng dụng đa tenant, quyền truy cập thường phải giới hạn theo tenant của người dùng. Việc người dùng có role hợp lệ trong tenant A không đồng nghĩa được đọc dữ liệu tenant B.

Ví dụ:

- Tenant A có customer, order và invoice riêng.
- Người dùng của tenant A gửi request đến ID invoice thuộc tenant B.
- Ứng dụng phải từ chối và không tiết lộ thông tin invoice.

Tenant ID cần được xác định từ security context hoặc cơ chế định tuyến tenant đáng tin cậy. Không nên lấy tenant ID trong query parameter làm căn cứ duy nhất để giới hạn truy vấn.

Một truy vấn có phạm vi tenant:

~~~java
Optional<Invoice> findByIdAndTenantId(
        UUID invoiceId,
        UUID trustedTenantId
);
~~~

Test nên tạo ít nhất hai tenant, mỗi tenant có người dùng và dữ liệu riêng. Sau đó xác minh người dùng tenant A không thể đọc, cập nhật, xóa hoặc export dữ liệu tenant B. Cần kiểm tra cả truy vấn danh sách và endpoint chi tiết; đôi khi endpoint detail đã được bảo vệ nhưng báo cáo tổng hợp vẫn lọc thiếu tenant.

## 9. Rò rỉ dữ liệu qua response

Một request có thể được phân quyền đúng nhưng response vẫn trả quá nhiều dữ liệu. Ví dụ, Controller trả trực tiếp entity:

~~~java
@GetMapping("/api/profile")
public UserEntity profile(@AuthenticationPrincipal AppPrincipal principal) {
    return userRepository.findById(principal.userId()).orElseThrow();
}
~~~

Entity có thể chứa password hash, email xác minh, trạng thái nội bộ, ghi chú hỗ trợ hoặc quan hệ không dành cho client. Serializer có thể đưa những trường này vào JSON nếu không có giới hạn rõ.

Hãy tạo response DTO chỉ chứa dữ liệu được phép:

~~~java
public record ProfileResponse(
        String displayName,
        String publicEmail,
        String avatarUrl
) {}
~~~

Mapper chuyển entity thành DTO theo hợp đồng công khai:

~~~java
public ProfileResponse toResponse(UserEntity user) {
    return new ProfileResponse(
            user.getDisplayName(),
            user.getPublicEmail(),
            user.getAvatarUrl()
    );
}
~~~

Không dựa vào việc ẩn một trường trong giao diện. Nếu trường đã có trong JSON/HTML, người dùng có thể xem bằng DevTools hoặc công cụ HTTP. Dữ liệu phải được giới hạn ngay tại response được tạo ở máy chủ.

## 10. Kiểm tra rò rỉ trong HTML, JSON và file

Các kênh phản hồi có thể để lộ dữ liệu theo những cách khác nhau:

| Kênh | Rủi ro cần kiểm tra |
|---|---|
| JSON API | Entity serialization, trường nội bộ, quan hệ lồng nhau, dữ liệu của người khác |
| HTML View | Dữ liệu nhạy cảm trong DOM, hidden input, comment, script hoặc thuộc tính data-* |
| File download | Tải hóa đơn, báo cáo hoặc ảnh thuộc người dùng khác |
| Error response | Stack trace, SQL, tên lớp, dữ liệu request |
| Export/report | Truy vấn thiếu điều kiện owner hoặc tenant |
| Cache | Response riêng tư được lưu và phục vụ cho người dùng khác |
| Log/trace | Token, cookie, dữ liệu cá nhân hoặc request body |

Kiểm tra HTML bằng cách xem response source/DOM, không chỉ nhìn giao diện. Kiểm tra JSON bằng cách xác minh các trường được phép có mặt và các trường nhạy cảm không tồn tại. Với file, kiểm tra cả metadata, tên file, nội dung và quyền truy cập.

## 11. Kiểm thử truy cập trái phép bằng MockMvc

Spring Security Test cung cấp các annotation như @WithMockUser để chạy request với một danh tính giả lập. Test cần kiểm tra cả người dùng hợp lệ và không hợp lệ.

Ví dụ endpoint chỉ dành cho quản trị viên:

~~~java
@WebMvcTest(AdminReportController.class)
@Import(SecurityConfiguration.class)
class AdminReportAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "customer-a", roles = "CUSTOMER")
    void customerCannotOpenAdminReport() throws Exception {
        mockMvc.perform(get("/admin/reports"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin-a", roles = "ADMIN")
    void administratorCanOpenAdminReport() throws Exception {
        mockMvc.perform(get("/admin/reports"))
                .andExpect(status().isOk());
    }
}
~~~

Ví dụ minh họa kiểm tra role ở URL. Cấu hình thực tế có thể redirect người dùng chưa đăng nhập đến trang login thay vì trả 401/403; hãy viết assertion theo hợp đồng HTML hoặc API đã chọn. Test dương cho admin rất quan trọng: nó chứng minh endpoint vẫn hoạt động với actor được phép, tránh việc test chỉ xác nhận mọi request đều bị chặn.

## 12. Kiểm thử IDOR/BOLA bằng hai người dùng

Để kiểm tra quyền sở hữu, hãy chuẩn bị ít nhất hai người dùng và hai tài nguyên:

- Customer A sở hữu Order A.
- Customer B sở hữu Order B.
- Customer A được phép xem Order A.
- Customer A không được phép xem Order B.

Ví dụ test cho query service:

~~~java
@DataJpaTest
class OrderOwnershipQueryTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void userCannotLoadAnotherUsersOrder() {
        Long ownerA = 10L;
        Long ownerB = 20L;
        Order orderB = persistOrder(ownerB);

        Optional<Order> result = orderRepository
                .findByIdAndOwnerId(orderB.getId(), ownerA);

        assertThat(result).isEmpty();
    }
}
~~~

Test tích hợp ở lớp MVC nên xác minh hành vi HTTP và dữ liệu phản hồi:

~~~java
@Test
@WithMockUser(username = "customer-a", roles = "CUSTOMER")
void customerCannotReadAnotherUsersOrder() throws Exception {
    mockMvc.perform(get("/api/orders/{id}", orderOwnedByB))
            .andExpect(status().isNotFound())
            .andExpect(content().string(
                    not(containsString("customer-b@example.test"))
            ));
}
~~~

Ví dụ dùng 404 để che giấu sự tồn tại tài nguyên. Nếu chính sách ứng dụng chọn 403, hãy kiểm tra 403 một cách nhất quán. Quan trọng là response không chứa dữ liệu đơn hàng của người khác.

## 13. Kiểm thử rò rỉ trường nhạy cảm

Test response nên xác minh các trường được phép có mặt và các trường cấm không xuất hiện.

Ví dụ với JSON:

~~~java
@Test
@WithMockUser(username = "customer-a", roles = "CUSTOMER")
void profileResponseContainsOnlyPublicFields() throws Exception {
    mockMvc.perform(get("/api/profile"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").exists())
            .andExpect(jsonPath("$.publicEmail").exists())
            .andExpect(jsonPath("$.passwordHash").doesNotExist())
            .andExpect(jsonPath("$.role").doesNotExist())
            .andExpect(jsonPath("$.internalNotes").doesNotExist());
}
~~~

Nếu một trường không được phép xuất hiện, hãy kiểm tra cả các đường dẫn lồng nhau. Ví dụ account.owner.email có thể làm lộ email dù trường ownerEmail ở cấp gốc không tồn tại.

Với HTML, có thể kiểm tra response string:

~~~java
mockMvc.perform(get("/account"))
        .andExpect(status().isOk())
        .andExpect(content().string(
                not(containsString("passwordHash"))
        ))
        .andExpect(content().string(
                not(containsString("internalNotes"))
        ));
~~~

Test này không thay thế kiểm tra bảo mật XSS hoặc escape. Nó chỉ xác minh các dữ liệu nhạy cảm cụ thể không bị render vào response.

## 14. Kiểm thử request bị từ chối không làm thay đổi dữ liệu

Một request bị từ chối cần không tạo tác dụng phụ. Chẳng hạn, Customer A cố hủy đơn của Customer B. Test không chỉ kiểm tra status mà còn xác minh trạng thái đơn vẫn giữ nguyên.

~~~java
@Test
@WithMockUser(username = "customer-a", roles = "CUSTOMER")
void forbiddenCancelDoesNotChangeOrderState() throws Exception {
    mockMvc.perform(post("/api/orders/{id}/cancel", orderOwnedByB)
                    .with(csrf()))
            .andExpect(status().isNotFound());

    Order reloaded = orderRepository.findById(orderOwnedByB).orElseThrow();
    assertThat(reloaded.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
}
~~~

Với Spring Security bật CSRF, POST test cần gửi token CSRF hợp lệ để kiểm tra authorization của endpoint. Nếu không có token, request có thể bị chặn ở CSRF filter trước khi đi đến logic quyền; test khi đó chưa chứng minh được kiểm tra quyền đối tượng.

## 15. Kiểm thử CSRF và CORS đúng mục đích

CSRF và CORS giải quyết các vấn đề khác nhau:

- **CSRF:** ngăn website khác lợi dụng trình duyệt đã xác thực để gửi thao tác ngoài ý muốn bằng cookie/session của người dùng.
- **CORS:** quy định trình duyệt có cho JavaScript từ origin khác đọc response hay không.

CORS không phải cơ chế phân quyền và không ngăn mọi request trái phép. Một client không chạy trong trình duyệt vẫn có thể gọi API trực tiếp. CSRF test nên xác minh request thay đổi trạng thái thiếu token bị từ chối khi ứng dụng dùng cookie/session authentication.

Ví dụ:

~~~java
@Test
@WithMockUser
void postWithoutCsrfTokenIsRejected() throws Exception {
    mockMvc.perform(post("/account/email")
                    .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser
void postWithCsrfTokenReachesApplication() throws Exception {
    mockMvc.perform(post("/account/email")
                    .with(csrf())
                    .param("email", "new@example.test"))
            .andExpect(status().is3xxRedirection());
}
~~~

Kết quả cụ thể tùy controller và cấu hình. Test có token chứng minh request vượt qua CSRF filter; vẫn cần các test riêng cho quyền người dùng và validation.

## 16. Kiểm tra quyền với file download và export

Endpoint tải file thường bị bỏ sót vì URL có thể chứa tên file hoặc mã tài liệu:

~~~http
GET /documents/invoice-1001.pdf
~~~

Không nên chỉ kiểm tra người dùng đã đăng nhập. Trước khi trả file, ứng dụng phải xác minh quyền truy cập tài liệu, quyền trên hóa đơn liên quan và phạm vi tenant.

Test cần bao gồm:

- Chủ sở hữu tải được file của mình.
- Người dùng khác không tải được file đó.
- Người dùng không có quyền không thể đoán URL rồi tải file.
- File tạm hoặc URL ký có thời hạn và phạm vi phù hợp.
- Response không tiết lộ đường dẫn lưu trữ nội bộ.
- Tên file và Content-Disposition không chứa dữ liệu tùy ý có thể gây injection.

Với export CSV/XLSX, kiểm tra truy vấn nguồn có giới hạn owner/tenant và chỉ xuất các cột được phép. Không dùng một endpoint export toàn hệ thống rồi chỉ ẩn dữ liệu bằng JavaScript ở trình duyệt.

## 17. Cache có thể làm rò dữ liệu giữa người dùng

Một response riêng tư được cache sai cách có thể được phục vụ cho người dùng khác. Rủi ro này xuất hiện ở browser cache, reverse proxy, CDN hoặc cache ứng dụng.

Với dữ liệu cá nhân hoặc response phụ thuộc vào session, cần xác định chính sách cache. Ví dụ:

~~~http
Cache-Control: private, no-store
~~~

Không phải mọi response riêng tư đều cần no-store; chính sách phụ thuộc loại dữ liệu và yêu cầu hiệu năng. Tuy nhiên, không được để shared cache lưu response cá nhân mà không có khóa cache và cơ chế kiểm soát phù hợp. Không dùng cookie hoặc Authorization header làm khóa cache một cách ngầm định nếu hệ thống cache không hỗ trợ chính sách đó.

Test có thể gửi cùng URL lần lượt với hai người dùng khác nhau và xác minh response thứ hai không chứa dữ liệu của người thứ nhất. Cần kiểm tra cả header cache và cấu hình CDN/reverse proxy trong môi trường tích hợp.

## 18. Kiểm tra log và error response để tránh rò rỉ

Ngay cả khi HTML/JSON chính an toàn, dữ liệu có thể xuất hiện trong:

- Stack trace hoặc exception message trả cho client.
- Log request/response.
- Trace span và baggage.
- Header debug hoặc correlation metadata.
- Redirect URL và query string.
- Thông báo validation phản chiếu rejected value.

Tạo dữ liệu đánh dấu trong test, chẳng hạn chuỗi giả lập PRIVATE_MARKER_42, rồi xác minh nó không xuất hiện trong response không được phép. Với log, dùng appender test hoặc cơ chế kiểm tra log có kiểm soát để bảo đảm token, mật khẩu và session ID đã được loại bỏ.

Trace ID có thể được trả cho người dùng để hỗ trợ tra cứu, nhưng trace ID không phải credential. Không dùng nó làm quyền truy cập log hoặc tài nguyên.

## 19. Thiết kế bộ test theo ma trận quyền

Một bộ test có thể được tổ chức theo actor, hành động và quan hệ với tài nguyên:

| Nhóm test | Danh tính | Tài nguyên | Hành động | Kết quả cần xác minh |
|---|---|---|---|---|
| Anonymous | Chưa đăng nhập | Tài nguyên riêng tư | Đọc | 401 hoặc redirect login |
| Role thấp | Customer | Chức năng admin | Đọc/thay đổi | 403 |
| Owner | Customer A | Đơn của A | Đọc | Thành công, chỉ dữ liệu được phép |
| Non-owner | Customer A | Đơn của B | Đọc | 403/404, không rò dữ liệu |
| Non-owner | Customer A | Đơn của B | Cập nhật/xóa | Bị từ chối, dữ liệu không đổi |
| Tenant khác | User tenant A | Tài nguyên tenant B | Mọi thao tác | Bị từ chối, không rò dữ liệu |
| Authorized admin | Admin | Tài nguyên trong phạm vi | Quản lý | Thành công theo chính sách |

Với mỗi endpoint, hãy kiểm tra:

1. Không có credential.
2. Credential hợp lệ nhưng role không đủ.
3. Role đủ nhưng không có quyền trên đối tượng.
4. Có quyền trên đối tượng.
5. Payload chứa trường ngoài allowlist.
6. Response không chứa trường nhạy cảm.
7. Request bị từ chối không làm thay đổi trạng thái.

Không nhất thiết mọi endpoint đều cần mọi tổ hợp. Hãy ưu tiên các endpoint chứa dữ liệu cá nhân, tài chính, quản trị, thao tác thay đổi trạng thái và tài nguyên có thể truy cập bằng ID.

## 20. Những lỗi kiểm thử thường gặp

### Chỉ test người dùng chưa đăng nhập

Điều này không phát hiện lỗi ngang giữa hai người dùng đã xác thực. Luôn có test owner và non-owner.

### Chỉ test role, không test quyền đối tượng

Hai người cùng role CUSTOMER vẫn có dữ liệu riêng. Cần kiểm tra ownership hoặc quan hệ chia sẻ.

### Dùng ID khó đoán thay cho authorization

UUID hoặc mã ngẫu nhiên chỉ làm việc đoán ID khó hơn; nó không chứng minh người gọi có quyền.

### Chỉ kiểm tra status code

Response 404 có thể vẫn chứa một phần dữ liệu trong body. Test cần kiểm tra nội dung, header và trạng thái dữ liệu sau request.

### Bỏ qua test dương

Nếu mọi request đều bị chặn, test âm vẫn có thể xanh. Cần chứng minh người dùng đúng quyền vẫn sử dụng được chức năng.

### Mock bỏ qua lớp kiểm tra quyền

Nếu mock service luôn trả dữ liệu, test Controller có thể bỏ qua policy thật. Nên có test ở service/repository và test tích hợp dùng cấu hình bảo mật thực tế.

### Không gửi CSRF token trong test POST

Request có thể bị CSRF filter chặn trước khi kiểm tra authorization. Hãy thêm token khi mục tiêu test là quyền trên đối tượng; giữ test riêng cho CSRF.

### Kiểm tra giao diện thay vì response thực

Ẩn nút trên giao diện không bảo vệ endpoint. Người dùng có thể gọi URL hoặc API trực tiếp. Kiểm tra request/response ở phía máy chủ.

## 21. Checklist review và kiểm thử bảo mật MVC

- [ ] Đã phân biệt authentication với authorization.
- [ ] Có ma trận quyền cho actor, tài nguyên và hành động.
- [ ] Endpoint riêng tư được bảo vệ ở security filter hoặc lớp tương đương.
- [ ] Quyền trên từng đối tượng được kiểm tra, không chỉ dựa vào role.
- [ ] User ID và tenant ID lấy từ ngữ cảnh đáng tin cậy.
- [ ] Không tin role, ownerId, giá hoặc trạng thái do client gửi.
- [ ] DTO đầu vào chỉ nhận các trường được phép thay đổi.
- [ ] Response dùng DTO/View Model và không lộ entity nội bộ.
- [ ] Có test anonymous, role thấp, owner, non-owner và actor được phép.
- [ ] Có test IDOR/BOLA cho đọc, cập nhật, xóa và export.
- [ ] Request bị từ chối không tạo tác dụng phụ.
- [ ] Có test cách ly tenant nếu ứng dụng đa tenant.
- [ ] Có test HTML, JSON, file download, error response và log phù hợp.
- [ ] CSRF được kiểm tra riêng khi dùng cookie/session authentication.
- [ ] Cache không làm response riêng tư bị chia sẻ sai người dùng.
- [ ] Test kiểm tra cả dữ liệu được phép xuất hiện và dữ liệu phải vắng mặt.

## Kết luận

Kiểm thử bảo mật MVC cần xác minh cả quyền gọi endpoint và quyền truy cập tài nguyên cụ thể. Hãy dùng ma trận quyền để kiểm tra người chưa đăng nhập, vai trò không đủ, chủ sở hữu, người không phải chủ sở hữu và các tenant khác nhau. ID khó đoán, nút bị ẩn hoặc role hợp lệ không thay thế kiểm tra quyền đối tượng. Bên cạnh status code, test phải kiểm tra response HTML/JSON/file, dữ liệu lưu sau request bị từ chối, cache và log. Khi Controller, dịch vụ nghiệp vụ, repository và DTO cùng thực thi ranh giới rõ ràng, ứng dụng giảm nguy cơ truy cập trái phép và rò rỉ dữ liệu.
