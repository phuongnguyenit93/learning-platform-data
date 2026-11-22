# Broken Function Level Authorization

## 1. BFLA là gì?

**Broken Function Level Authorization (BFLA)** xảy ra khi API không kiểm tra đầy đủ quyền gọi một chức năng. Người dùng đã đăng nhập có thể gọi chức năng dành cho vai trò hoặc nhóm quyền khác, chẳng hạn user thường gọi endpoint quản trị, nhân viên hỗ trợ tự hoàn tiền, hoặc một service account gọi thao tác chỉ dành cho hệ thống thanh toán.

Ví dụ, giao diện chỉ hiển thị nút “Khóa tài khoản” cho quản trị viên. Một user thường có thể mở Developer Tools, gửi request trực tiếp đến `POST /api/admin/users/42/disable` và thử xem server có thực hiện hay không. Nếu backend chỉ kiểm tra người gọi đã đăng nhập, chức năng vẫn có thể bị gọi dù giao diện đã ẩn nút.

BFLA là lỗi phân quyền ở **mức chức năng**. Nó khác với BOLA/IDOR, vốn xảy ra khi caller được phép gọi một loại chức năng nhưng có thể thao tác lên đối tượng không thuộc phạm vi của mình. Một endpoint có thể mắc cả hai lỗi: user thường gọi được chức năng quản trị (BFLA), rồi thay ID để tác động tài khoản của tenant khác (BOLA).

| Câu hỏi | Kiểu kiểm soát | Ví dụ lỗi |
|---|---|---|
| Ai được gọi chức năng này? | Function-level authorization | User thường gọi `POST /admin/users`. |
| Caller được thao tác trên đối tượng nào? | Object-level authorization | User A đọc đơn hàng của user B. |
| Caller được đọc hoặc sửa trường nào? | Property-level authorization | User tự gửi `role: ADMIN` trong JSON. |

Xác thực (authentication) chỉ xác định danh tính hoặc credential của caller. Nó không tự cấp quyền cho mọi chức năng. Mỗi request cần được kiểm tra quyền phù hợp với hành động mà endpoint thực hiện.

## 2. Vì sao BFLA thường xuất hiện?

Các nguyên nhân phổ biến gồm:

- **Chỉ kiểm tra đăng nhập:** mọi principal đã xác thực đều được phép vào `/api/**`, dù có endpoint quản trị hoặc thao tác nhạy cảm.
- **Dựa vào giao diện:** ẩn nút, route hoặc menu theo role nhưng backend không có kiểm tra tương ứng.
- **Phân quyền theo URL không đầy đủ:** chỉ bảo vệ `/admin/**`, trong khi cùng chức năng có alias, route phiên bản cũ, endpoint mobile hoặc RPC khác.
- **Bỏ sót HTTP method:** `GET` được bảo vệ nhưng `POST`, `PATCH`, `DELETE`, endpoint bulk hoặc endpoint export không được áp dụng cùng chính sách.
- **Vai trò quá rộng:** một role như `USER` hoặc `STAFF` được cấp nhiều quyền hơn nhu cầu thực tế; mọi nhân viên nội bộ đều có quyền quản trị.
- **Tin dữ liệu do client gửi:** server nhận `role`, `isAdmin`, `permissions` hoặc header tự khai báo làm căn cứ cấp quyền.
- **Quên kiểm tra ở luồng phụ:** GraphQL resolver, WebSocket, batch job, file upload/download, webhook hoặc endpoint nội bộ không đi qua bộ lọc phân quyền chính.
- **Chính sách không đồng nhất:** controller kiểm tra quyền nhưng service khác được gọi trực tiếp từ một endpoint khác mà không có kiểm soát tương đương.
- **Thay đổi hệ thống nhưng quên cập nhật quyền:** chức năng mới, route mới hoặc vai trò mới được triển khai mà không có policy và test tương ứng.

Attacker thường không cần đoán mật khẩu hoặc vượt qua đăng nhập. Họ sử dụng một tài khoản hợp lệ, khám phá endpoint và thử gọi chức năng vượt quyền bằng cách sửa URL, method, body hoặc gọi API trực tiếp.

## 3. Lập danh mục chức năng và quyền cần có

Trước khi viết rule, cần biết API cung cấp những hành động nào và ai có trách nhiệm thực hiện chúng. Đừng chỉ phân loại theo nhóm URL hoặc tên role.

Với từng endpoint, ghi nhận:

1. Hành động nghiệp vụ thực tế mà endpoint kích hoạt.
2. Các nhóm principal có thể gọi hành động đó: người dùng, nhân viên, quản trị viên, service account hoặc hệ thống tích hợp.
3. Quyền tối thiểu cần có và các điều kiện bổ sung như tenant, trạng thái nghiệp vụ, thời gian hoặc bước phê duyệt.
4. Tác dụng phụ và mức độ ảnh hưởng nếu chức năng bị gọi trái phép.
5. Tất cả đường vào chức năng: REST route, GraphQL mutation, RPC, job, webhook hoặc giao diện quản trị.

Ví dụ danh mục permission cho hệ thống quản lý đơn hàng:

| Permission | Ý nghĩa | Principal có thể được cấp |
|---|---|---|
| `order:read` | Tra cứu đơn hàng theo phạm vi được phép. | Customer, support, order-service. |
| `order:create` | Tạo đơn hàng. | Customer, checkout-service. |
| `order:cancel` | Yêu cầu hủy đơn. | Customer, support theo chính sách. |
| `order:refund` | Khởi tạo hoàn tiền. | Finance, payment-service. |
| `order:approve` | Phê duyệt đơn hoặc ngoại lệ. | Supervisor. |
| `user:role:assign` | Gán hoặc thu hồi role của user. | Identity administrator. |
| `audit:read` | Tra cứu audit event. | Security auditor. |

Permission nên biểu diễn một hành động cụ thể, có tên nhất quán và dễ kiểm kê. Tránh một quyền tổng quát như `admin` nếu nó gom cả đọc dữ liệu, hoàn tiền, cấp quyền và xóa tài khoản. Chia quyền theo chức năng giúp giảm tác động khi một tài khoản bị chiếm.

### Ma trận quyền mẫu

| Chức năng | Customer | Support | Supervisor | Finance | Security admin |
|---|---:|---:|---:|---:|---:|
| Đọc đơn của chính mình | Có | Có theo nhiệm vụ | Có theo nhiệm vụ | Có theo nhiệm vụ | Theo policy kiểm toán |
| Tạo đơn | Có | Không mặc định | Không mặc định | Không mặc định | Không mặc định |
| Hủy đơn | Có trong điều kiện | Có trong phạm vi hỗ trợ | Có | Không mặc định | Không mặc định |
| Hoàn tiền | Không | Không mặc định | Theo hạn mức | Có | Không mặc định |
| Phê duyệt ngoại lệ | Không | Không | Có | Theo quy trình | Không mặc định |
| Gán role | Không | Không | Không | Không | Có |

Ma trận chỉ là ví dụ. Quyền thật phải xuất phát từ quy trình nghiệp vụ, phân tách nhiệm vụ (separation of duties), hạn mức và trách nhiệm của từng nhóm. Có thể yêu cầu hai người khác nhau tạo và phê duyệt một giao dịch giá trị cao.

## 4. Chọn mô hình phân quyền phù hợp

### RBAC: phân quyền theo vai trò

Role-Based Access Control (RBAC) gán permission cho role, sau đó gán role cho principal. Ví dụ role `FINANCE_OPERATOR` có `payment:read` và `payment:refund`; role `SUPPORT_AGENT` có `order:read` và `order:cancel` trong phạm vi công việc.

RBAC dễ quản lý khi tổ chức có nhóm công việc ổn định. Tuy nhiên, role có thể phình to nếu mọi ngoại lệ đều tạo role mới. Hãy đặt tên role theo trách nhiệm, giữ permission nhỏ và rà soát việc gán role định kỳ.

### ABAC: phân quyền theo thuộc tính

Attribute-Based Access Control (ABAC) xét thuộc tính của principal, request, resource và môi trường. Ví dụ, nhân viên chỉ được hoàn tiền khi:

- Có permission `payment:refund`.
- Đơn thuộc khu vực/đơn vị mà nhân viên phụ trách.
- Số tiền không vượt hạn mức được giao.
- Đơn đang ở trạng thái cho phép hoàn tiền.
- Request đến từ phiên hoặc thiết bị đáp ứng mức bảo đảm theo policy.

ABAC phù hợp với quy tắc có điều kiện, nhưng policy cần được quản lý tập trung, kiểm thử và giải thích được lý do cho phép/từ chối.

### ReBAC: phân quyền theo quan hệ

Relationship-Based Access Control (ReBAC) dựa vào quan hệ giữa principal và tài nguyên hoặc nhóm tài nguyên. Ví dụ, một user là thành viên của project, chủ sở hữu workspace hoặc người được ủy quyền quản lý một tài khoản. ReBAC thường phối hợp với RBAC/ABAC thay vì thay thế tất cả.

### Kết hợp các mô hình

Một quyết định có thể gồm nhiều điều kiện: principal có permission chức năng, quan hệ với tenant hợp lệ, resource đang ở trạng thái phù hợp và giao dịch nằm trong hạn mức. Mặc định từ chối nếu thiếu thông tin, không tìm thấy policy hoặc policy engine gặp lỗi. Không biến lỗi kiểm tra quyền thành trạng thái “cho phép tạm thời”.

## 5. Thiết kế kiểm tra quyền ở backend

### Bảo vệ theo chức năng, không theo giao diện

Mọi endpoint nhạy cảm phải có kiểm tra ở server. Giao diện có thể ẩn chức năng để cải thiện trải nghiệm, nhưng backend vẫn phải từ chối caller không có quyền. Không tin role, permission hoặc cờ `isAdmin` trong query, body, cookie không được bảo vệ hay header do client tự đặt.

Nếu quyền được đưa vào JWT, chỉ sử dụng claim sau khi xác minh chữ ký, issuer, audience, thời hạn và các thuộc tính cần thiết. Cần cân nhắc độ trễ thu hồi quyền: token sống lâu có thể giữ permission cũ sau khi người dùng bị hạ quyền. Với hành động nhạy cảm, có thể tra policy hiện tại hoặc dùng token ngắn hạn và cơ chế thu hồi phù hợp.

### Kiểm tra quyền theo hành động cụ thể

Ví dụ với Spring Security:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
```

Rule ở filter chain yêu cầu danh tính cho API và từ chối route chưa được khai báo. Kiểm tra quyền chức năng chi tiết được đặt tại method/service tương ứng:

```java
@RestController
@RequestMapping("/api/users")
public class UserAdminController {
    private final UserAdminService userAdminService;

    public UserAdminController(UserAdminService userAdminService) {
        this.userAdminService = userAdminService;
    }

    @PostMapping("/{userId}/disable")
    @PreAuthorize("hasAuthority('user:account:disable')")
    public void disableUser(@PathVariable UUID userId) {
        userAdminService.disable(userId);
    }
}
```

`hasAuthority` so khớp permission cụ thể. `hasRole("ADMIN")` trong Spring thường áp dụng tiền tố `ROLE_`; cần thống nhất cách biểu diễn role và authority để tránh nhầm lẫn. Trong hệ thống lớn, có thể gọi policy service thay vì viết nhiều biểu thức role trực tiếp.

Đừng chỉ bảo vệ controller nếu cùng service có thể được gọi từ nhiều entry point. Có thể đặt kiểm tra method-level ở application service để bảo vệ các đường gọi nội bộ, nhưng phải hiểu cơ chế proxy của Spring: self-invocation (một method trong cùng bean gọi trực tiếp method được bảo vệ) có thể không đi qua proxy và không kích hoạt method security như mong đợi. Thiết kế service boundary rõ ràng và kiểm thử đường gọi thật.

### Kiểm tra ở nhiều lớp

- **Gateway/filter chain:** chặn request chưa xác thực, giới hạn route và áp dụng policy tổng quát.
- **Controller/application service:** kiểm tra permission cho hành động cụ thể.
- **Domain service:** bảo đảm quy tắc nghiệp vụ, trạng thái và phân tách nhiệm vụ.
- **Data access:** kiểm tra phạm vi tenant/object khi thao tác dữ liệu; không dựa vào kiểm tra ở một nhánh controller duy nhất.

Không cần nhân bản mọi rule ở mọi lớp. Mỗi lớp phải có trách nhiệm rõ và không có đường vào thay thế bỏ qua kiểm tra cốt lõi.

## 6. Bảo vệ endpoint quản trị và chức năng nhạy cảm

Endpoint quản trị thường có tác động lớn: tạo/xóa user, gán role, thay đổi cấu hình, xem audit log, export dữ liệu, hoàn tiền, điều chỉnh số dư hoặc mở khóa tài khoản. Hãy:

- Tách permission theo từng hành động như `user:read`, `user:disable`, `user:role:assign`, `config:update` thay vì cấp một quyền quản trị tổng quát.
- Dùng xác thực mạnh và xác thực tăng cường cho hành động có hậu quả cao; cân nhắc step-up authentication hoặc phê duyệt độc lập.
- Áp dụng hạn mức, dual control và separation of duties cho giao dịch lớn hoặc thay đổi quyền nhạy cảm.
- Giới hạn tài khoản service theo đúng chức năng và audience; không cấp quyền tương tác người dùng nếu workload không cần.
- Có thể tách admin API về network/hostname riêng để giảm bề mặt tấn công, nhưng vẫn phải xác thực và phân quyền tại server.
- Ghi audit event cho hành động quản trị, người thực hiện, đối tượng, kết quả và lý do; không ghi token hoặc secret.

Không dùng việc đổi URL sang `/internal`, IP allowlist hoặc VPN làm cơ chế phân quyền duy nhất. Các lớp mạng có thể bổ sung kiểm soát, nhưng endpoint vẫn cần kiểm tra principal và permission.

## 7. Kiểm tra mọi đường vào cùng một chức năng

BFLA thường tồn tại vì cùng một hành động được cung cấp qua nhiều giao thức hoặc route. Lập danh sách và áp dụng cùng policy cho:

- REST endpoint với từng HTTP method và API version.
- GraphQL query/mutation và từng resolver; không chỉ bảo vệ endpoint `/graphql` ở mức đăng nhập.
- gRPC/RPC method và message handler.
- WebSocket message/action sau khi kết nối đã được thiết lập; xác thực handshake không thay thế phân quyền từng action.
- Bulk endpoint, import/export, file upload/download và thao tác bất đồng bộ.
- Webhook, callback, scheduled job và consumer nhận message.
- Endpoint mobile/legacy hoặc route tương thích ngược còn được duy trì.

Ví dụ, nếu `POST /api/users/{id}/disable` được bảo vệ nhưng GraphQL mutation `disableUser(id)` không kiểm tra permission tương đương, attacker vẫn có thể gọi chức năng qua GraphQL. Tốt nhất các entry point gọi cùng application service có guard thống nhất.

Với background job, principal có thể là service identity hoặc workload identity thay vì user. Vẫn cần quyền riêng cho job, giới hạn tenant và hành động, xác minh nguồn message và tránh sử dụng một tài khoản hệ thống có quyền toàn cục cho mọi tác vụ.

## 8. Các lỗi triển khai cần tránh

| Anti-pattern | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chỉ kiểm tra `authenticated()` | Mọi user đã đăng nhập có thể gọi chức năng nhạy cảm. | Kiểm tra permission theo hành động. |
| Ẩn nút admin ở frontend | Request trực tiếp vẫn đến backend. | Bảo vệ endpoint tại server. |
| Dùng một role `ADMIN` cho mọi quyền | Quyền quá rộng, tăng tác động khi tài khoản bị chiếm. | Tách permission và giới hạn role theo trách nhiệm. |
| Đọc role từ request body/header | Caller tự nâng quyền. | Lấy principal từ security context hoặc identity provider đã xác minh. |
| Chỉ bảo vệ một route | Alias, version cũ hoặc giao thức khác có thể bỏ qua. | Kiểm kê mọi entry point và dùng policy chung. |
| Chỉ kiểm tra ở gateway | Service có thể bị gọi trực tiếp hoặc từ job nội bộ. | Kiểm tra ở application/service boundary và hạn chế network path. |
| Policy engine lỗi thì cho phép | Lỗi hạ tầng trở thành bypass quyền. | Fail closed và theo dõi lỗi policy. |
| Không test quyền bị từ chối | Regression có thể mở lại chức năng cho user thường. | Viết test âm cho từng permission/endpoint. |
| Cấp role lâu dài không rà soát | Quyền tích tụ theo thời gian và sau chuyển vị trí. | Có thời hạn, recertification và quy trình thu hồi role. |

## 9. Kiểm thử BFLA

Kiểm thử phải gọi API trực tiếp bằng các principal có quyền khác nhau. Không chỉ xác minh giao diện ẩn/hiện nút. Với mỗi endpoint, tạo ma trận gồm anonymous, user thường, role liên quan, supervisor, admin và service account.

Ví dụ test âm với Spring Security MockMvc:

```java
@WebMvcTest(UserAdminController.class)
@Import(SecurityConfig.class)
class UserAdminAuthorizationTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    UserAdminService userAdminService;

    @Test
    @WithMockUser(authorities = "user:read")
    void regularUserCannotDisableAccount() throws Exception {
        mockMvc.perform(post("/api/users/{id}/disable",
                "7a9d9bb0-b7c0-4c90-a51c-89c5e8c0b3c1"))
            .andExpect(status().isForbidden());

        verifyNoInteractions(userAdminService);
    }
}
```

Đây là ví dụ minh họa; cần cấu hình test slice, bean và security filter phù hợp phiên bản Spring Security của dự án. Kiểm tra `verifyNoInteractions` giúp xác nhận request bị từ chối trước khi service tạo tác dụng phụ.

Ma trận kiểm thử gợi ý:

| Principal | `GET /api/admin/audit` | `POST /api/users/{id}/disable` | `POST /api/payments/{id}/refund` |
|---|---:|---:|---:|
| Anonymous | 401 | 401 | 401 |
| Customer | 403 | 403 | 403 |
| Support | Theo policy | 403 | 403 |
| Security auditor | Có | 403 | 403 |
| Identity administrator | Theo policy | Có | 403 |
| Finance operator | Theo policy | 403 | Có trong hạn mức |

Các status code trong bảng là ví dụ cho API phân biệt chưa xác thực (`401`) với đã xác thực nhưng không có quyền (`403`). Một số hệ thống trả `404` cho tài nguyên/chức năng cần che giấu sự tồn tại; cần nhất quán và không để response vô tình tiết lộ dữ liệu.

Ngoài ma trận role, hãy thử:

- Gọi cùng chức năng qua route alias, API version cũ, HTTP method khác và endpoint bulk.
- Sửa body, query, header, `X-HTTP-Method-Override` nếu hệ thống hỗ trợ và các trường role/permission.
- Gọi GraphQL mutation, RPC method, WebSocket action hoặc job tương đương.
- Dùng token thiếu scope, token hết hạn, token có permission cũ sau khi role bị thu hồi.
- Gọi trực tiếp service bỏ qua gateway trong môi trường kiểm thử được phép.
- Kiểm tra request bị từ chối không tạo audit side effect sai, không gửi email, không hoàn tiền và không thay đổi trạng thái.
- Kiểm tra policy engine hoặc identity provider không sẵn sàng thì hệ thống từ chối an toàn.

## 10. Giám sát và quản trị quyền

Audit log nên ghi nhận principal, loại principal, permission được yêu cầu, endpoint/action, resource identifier ở mức phù hợp, tenant, quyết định allow/deny, policy version, request ID, thời điểm và lý do từ chối có kiểm soát. Không ghi access token, API key, password hoặc dữ liệu nhạy cảm không cần thiết.

Các tín hiệu cần theo dõi:

- Một user thường xuyên gọi endpoint quản trị hoặc nhận nhiều `403` liên tiếp.
- Principal gọi chức năng hiếm khi dùng, ngoài giờ hoặc từ nguồn bất thường.
- Service account gọi endpoint ngoài danh sách chức năng đã khai báo.
- Tăng đột biến thao tác hoàn tiền, export, gán role, khóa user hoặc thay đổi cấu hình.
- Permission/role được cấp mới, nâng quyền, không sử dụng lâu ngày hoặc không được thu hồi khi nhân sự chuyển nhiệm vụ.
- Một route mới được triển khai nhưng chưa có policy hoặc test quyền tương ứng.

Quản trị quyền cần có quy trình cấp, phê duyệt, rà soát và thu hồi. Áp dụng least privilege, thời hạn cho quyền đặc biệt (just-in-time access) và recertification định kỳ. Khi người dùng đổi vai trò hoặc rời tổ chức, thu hồi role, session/token và các credential liên quan theo SLA đã xác định.

## 11. Checklist cho mỗi chức năng API

- [ ] Đã mô tả rõ hành động nghiệp vụ và mức độ nhạy cảm của chức năng?
- [ ] Đã xác định principal nào được phép gọi và permission cụ thể cần có?
- [ ] Server kiểm tra quyền trên mọi request, không phụ thuộc frontend hoặc network location?
- [ ] Quyền được lấy từ identity đã xác minh, không lấy từ body/header do client tự khai báo?
- [ ] Đã kiểm kê REST, HTTP method, API version, GraphQL/RPC, WebSocket, job và route thay thế?
- [ ] Các entry point dùng policy thống nhất và không có đường gọi service bỏ qua guard?
- [ ] Có kiểm tra object/tenant/property riêng khi chức năng tác động dữ liệu cụ thể?
- [ ] Chính sách mặc định từ chối và xử lý lỗi policy theo fail-closed?
- [ ] Chức năng nhạy cảm có hạn mức, step-up authentication hoặc dual control khi cần?
- [ ] Có test cho anonymous, user thường, role đúng, role sai, service account và quyền đã thu hồi?
- [ ] Request bị từ chối không tạo tác dụng phụ?
- [ ] Có audit log, cảnh báo và quy trình rà soát/thu hồi quyền?

BFLA được ngăn chặn khi mỗi chức năng có permission rõ ràng và backend thực thi policy trên mọi đường vào. Role chỉ là cách nhóm quyền; quyết định cuối cùng cần xét hành động, danh tính đã xác minh và điều kiện nghiệp vụ. Khi kết hợp function-level authorization với kiểm tra object/property, least privilege, test âm và audit, API giảm được nguy cơ một tài khoản hợp lệ sử dụng chức năng vượt quá trách nhiệm được giao.
