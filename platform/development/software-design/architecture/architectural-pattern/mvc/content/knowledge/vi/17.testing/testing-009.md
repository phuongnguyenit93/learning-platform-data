# Kiểm thử quyền truy cập, session và cách ly người dùng

## Mục tiêu

Ứng dụng MVC phải bảo đảm mỗi người dùng chỉ thực hiện được những thao tác họ được phép và chỉ nhìn thấy dữ liệu thuộc phạm vi của mình. Một endpoint có thể hoạt động đúng về mặt kỹ thuật nhưng vẫn gây lộ dữ liệu nếu Controller chỉ kiểm tra người dùng đã đăng nhập mà quên kiểm tra quyền trên tài nguyên cụ thể. Tương tự, một session được quản lý sai có thể khiến trạng thái đăng nhập hoặc dữ liệu của người này bị dùng nhầm cho người khác.

Kiểm thử bảo mật cần xác nhận cả đường đi được phép và đường đi bị từ chối. Người dùng có quyền phải truy cập được tài nguyên hợp lệ; người dùng khác, người chưa đăng nhập hoặc người có vai trò thấp hơn phải bị từ chối theo đúng chính sách. Các kiểm thử cũng cần xác nhận session được tạo, thay đổi, hết hạn và hủy đúng cách, đồng thời dữ liệu không bị rò rỉ giữa người dùng hoặc tenant.

Bài học này giải thích cách kiểm thử authentication, authorization, quyền trên từng tài nguyên, session lifecycle và user isolation trong ứng dụng MVC. Các ví dụ sử dụng Java, Spring Security, MockMvc và các tầng persistence.

Sau khi học, người học có thể:

- Phân biệt authentication và authorization khi thiết kế test.
- Kiểm thử quyền ở route, method, tài nguyên và từng trường dữ liệu.
- Phát hiện lỗi truy cập ngang, truy cập vượt quyền và IDOR/BOLA.
- Thiết kế test chứng minh người dùng và tenant không truy cập dữ liệu của nhau.
- Kiểm thử session, login, logout, timeout và session fixation.
- Sử dụng Spring Security Test và MockMvc để tạo ngữ cảnh người dùng.
- Kết hợp unit test, MVC test và integration test với database.
- Kiểm tra cả status response lẫn việc dữ liệu và tác dụng phụ không bị thay đổi trái phép.

## 1. Vì sao cần kiểm thử quyền truy cập và cách ly người dùng?

Giả sử một ứng dụng quản lý hồ sơ cho phép người dùng xem và cập nhật thông tin cá nhân. Endpoint có thể nhận một ID:

    GET /profiles/42
    PATCH /profiles/42

Nếu server chỉ xác nhận request đã đăng nhập, Alice có thể đổi ID thành hồ sơ của Bob và đọc hoặc sửa dữ liệu của Bob. Đây là lỗi phân quyền ở cấp đối tượng. Việc endpoint yêu cầu đăng nhập không có nghĩa là mọi người dùng đã đăng nhập đều được truy cập mọi tài nguyên.

Một lỗi khác có thể xuất hiện khi ứng dụng lưu currentUser trong biến static hoặc tái sử dụng một đối tượng chứa dữ liệu theo request. Request của Alice có thể vô tình nhận dữ liệu của Bob khi nhiều request chạy song song hoặc khi trạng thái không được dọn đúng cách.

Các kiểm thử cần trả lời:

- Người chưa đăng nhập có thể gọi endpoint cần xác thực không?
- Người đã đăng nhập nhưng thiếu quyền có thể gọi endpoint quản trị không?
- Người dùng A có đọc hoặc sửa tài nguyên của người dùng B không?
- Tenant A có truy cập dữ liệu của tenant B không?
- Người dùng có thể gửi thêm trường như ownerId hoặc role để tự nâng quyền không?
- Session cũ có còn hợp lệ sau logout hoặc khi đăng nhập không?
- Một request mới có thể thừa hưởng danh tính hoặc dữ liệu từ request trước không?

Các câu hỏi này phải được kiểm tra ở nhiều tầng. Chỉ kiểm thử status HTTP có thể bỏ sót lỗi khi server trả 403 nhưng vẫn thực hiện một tác dụng phụ trước đó.

## 2. Phân biệt authentication và authorization

Authentication (xác thực) xác định người gọi là ai. Authorization (phân quyền) quyết định người đó được làm gì trên tài nguyên nào.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Người gọi đã đăng nhập bằng danh tính nào? | Alice có phiên đăng nhập hợp lệ |
| Authorization | Alice có quyền xem báo cáo quản trị không? | Chỉ ADMIN được xem báo cáo |
| Object-level authorization | Alice có quyền trên hồ sơ cụ thể này không? | Alice chỉ sửa hồ sơ do Alice sở hữu |
| Tenant isolation | Dữ liệu có thuộc tenant hiện tại không? | Tenant A không đọc đơn hàng của tenant B |
| Field-level authorization | Người dùng có được sửa trường này không? | Người dùng không tự đổi role hoặc ownerId |

Một test authentication có thể chứng minh người chưa đăng nhập bị chuyển đến trang login hoặc nhận 401. Nó chưa chứng minh người đã đăng nhập chỉ truy cập được tài nguyên thuộc quyền của mình.

### Hai chiều kiểm thử bắt buộc

Với mỗi chính sách quan trọng, nên có ít nhất:

1. Test dương: người có quyền thực hiện được thao tác.
2. Test âm: người không có quyền bị từ chối và không gây thay đổi dữ liệu.

Nếu chỉ viết test âm, cấu hình có thể vô tình chặn tất cả mọi người. Nếu chỉ viết test dương, lỗ hổng phân quyền có thể vẫn tồn tại.

## 3. Xác định chính sách quyền trước khi viết test

Test cần dựa trên chính sách rõ ràng. Đừng suy ra quyền từ tên endpoint hoặc vai trò mặc định.

Ví dụ một hệ thống quản lý khóa học có chính sách:

| Actor | Xem khóa học công khai | Xem đăng ký của mình | Xem mọi đăng ký | Duyệt đăng ký |
|---|---:|---:|---:|---:|
| Anonymous | Có | Không | Không | Không |
| Student | Có | Có | Không | Không |
| Instructor | Có | Theo khóa học được phân công | Không | Có trong khóa học được phân công |
| Admin | Có | Có | Có | Có |

Bảng này mô tả quyền ở mức chức năng. Khi truy cập một đăng ký cụ thể, ứng dụng còn phải kiểm tra quan hệ giữa actor và tài nguyên. Ví dụ, một Instructor chỉ được duyệt đăng ký của khóa học mình phụ trách.

### RBAC, permission và policy

- RBAC (Role-Based Access Control) gán quyền theo vai trò như STUDENT, INSTRUCTOR hoặc ADMIN.
- Permission-based access dùng quyền cụ thể như registration:read hoặc course:approve.
- Attribute-based access control (ABAC) xét thuộc tính của actor, tài nguyên và ngữ cảnh, ví dụ chủ sở hữu, tenant, trạng thái hoặc thời gian.

Một ứng dụng có thể kết hợp các cách này. Test nên phản ánh chính sách thực tế, ví dụ một user có role INSTRUCTOR nhưng chỉ được duyệt tài nguyên thuộc course được phân công.

### Deny by default

Khi chưa có quy tắc cho phép rõ ràng, hệ thống nên từ chối. Trong test, cần kiểm tra endpoint mới hoặc route chưa khai báo quyền không vô tình trở thành public. Cũng cần xác nhận các đường dẫn tĩnh, login và tài nguyên công khai được cho phép đúng phạm vi.

## 4. Các lớp phân quyền cần kiểm thử trong MVC

Một request có thể đi qua nhiều lớp kiểm soát:

    Browser / API Client
             |
             v
       Security Filter
       Authentication
             |
             v
       URL Authorization
             |
             v
         Controller
             |
             v
       Application Service
             |
             v
       Object / Domain Policy
             |
             v
       Repository / Database

Mỗi lớp có mục đích khác nhau:

- Security filter xác thực request và áp dụng quy tắc chung.
- URL authorization bảo vệ nhóm endpoint theo path và method.
- Method security có thể bảo vệ phương thức service hoặc controller.
- Object-level policy quyết định actor có quyền trên tài nguyên cụ thể không.
- Repository có thể giới hạn truy vấn theo owner hoặc tenant để tránh tải nhầm dữ liệu.
- Database constraint và row-level security có thể tạo thêm lớp bảo vệ nếu hệ thống dùng chúng.

Không cần lặp mọi quy tắc ở tất cả các tầng. Tuy nhiên, test phải chứng minh ranh giới quan trọng được bảo vệ. Nếu application service được gọi từ nhiều adapter, quyền trên tài nguyên không nên chỉ tồn tại trong một Controller.

### Không coi việc ẩn nút là phân quyền

Ẩn nút Edit trong View chỉ cải thiện giao diện. Người dùng vẫn có thể gửi request thủ công. Test phải gọi trực tiếp endpoint hoặc use case với actor không có quyền để chứng minh server từ chối.

## 5. Truy cập ngang, truy cập dọc và IDOR/BOLA

Hai nhóm lỗi phân quyền thường gặp:

**Horizontal privilege escalation** (truy cập ngang) xảy ra khi một người dùng truy cập dữ liệu hoặc hành động thuộc về người dùng khác có cùng mức quyền. Ví dụ, Alice xem hóa đơn của Bob bằng cách thay ID trong URL.

**Vertical privilege escalation** (truy cập dọc) xảy ra khi người dùng có quyền thấp thực hiện thao tác dành cho vai trò cao hơn. Ví dụ, Student gọi endpoint duyệt đăng ký vốn chỉ dành cho Instructor.

IDOR (Insecure Direct Object Reference) và BOLA (Broken Object Level Authorization) mô tả các tình huống server không kiểm tra quyền đúng cách khi client tham chiếu đến một đối tượng bằng ID hoặc khóa khác.

### Test truy cập ngang

Chuẩn bị hai người dùng và hai tài nguyên:

- Alice sở hữu profile A.
- Bob sở hữu profile B.

Kiểm tra:

- Alice đọc profile A thành công.
- Alice đọc profile B bị từ chối theo chính sách.
- Alice cập nhật profile B bị từ chối.
- Dữ liệu profile B không thay đổi sau request bị từ chối.
- Bob vẫn đọc được profile B sau đó.

Test cuối cùng rất quan trọng: nó chứng minh request của Alice không gây ra thay đổi âm thầm dù response có thể đã trả lỗi.

### Test truy cập dọc

Chuẩn bị một Student và một Admin:

- Student gọi endpoint xem chức năng dành cho Student thành công.
- Student gọi endpoint quản trị bị từ chối.
- Student không thể thay role của mình bằng request body.
- Admin gọi endpoint quản trị thành công.
- Các quyền khác không bị mở rộng chỉ vì user có một role hợp lệ.

### Chọn 403 hay 404

Khi actor không có quyền truy cập một tài nguyên, ứng dụng có thể trả 403 Forbidden hoặc 404 Not Found theo chính sách. Trả 404 có thể tránh tiết lộ tài nguyên có tồn tại hay không. Test nên kiểm tra đúng chính sách đã chọn, không giả định mọi ứng dụng phải dùng cùng status.

Điều quan trọng hơn status là dữ liệu không bị trả về, thao tác không được thực hiện và không có tác dụng phụ.

## 6. Thiết kế ma trận test actor – resource – action

Một ma trận giúp tìm các tổ hợp chưa được kiểm thử.

| Actor | Tài nguyên thuộc actor | Tài nguyên của user khác | Tài nguyên tenant khác | Hành động quản trị |
|---|---|---|---|---|
| Anonymous | Không truy cập dữ liệu riêng | Không truy cập | Không truy cập | Không truy cập |
| Student A | Được phép theo chính sách | Bị từ chối | Bị từ chối | Bị từ chối |
| Student B | Được phép theo chính sách | Bị từ chối | Bị từ chối | Bị từ chối |
| Instructor A | Theo khóa học được giao | Theo phân công | Bị từ chối | Chỉ quyền được giao |
| Admin | Theo phạm vi quản trị | Theo phạm vi quản trị | Theo phạm vi quản trị | Được phép |

Không nhất thiết phải viết một test cho mọi ô trong ma trận. Hãy chọn các trường hợp bao phủ từng quy tắc và từng ranh giới có rủi ro cao. Với hệ thống nhiều vai trò, có thể dùng parameterized test để chạy cùng một kịch bản cho nhiều actor.

### Bao phủ cả action và resource

Một người dùng có thể được phép đọc nhưng không được phép cập nhật. Một Instructor có thể xem danh sách đăng ký của khóa học mình phụ trách nhưng không được xem khóa học của Instructor khác. Vì vậy, test cần kết hợp:

- Actor.
- Action: read, create, update, delete, approve, export.
- Resource: owner, tenant, trạng thái và quan hệ.
- Context: session, thời gian hoặc trạng thái quy trình nếu có.

## 7. Kiểm thử quyền route và method với Spring Security

Spring Security Test cung cấp các cách tạo SecurityContext cho MockMvc mà không cần thực hiện đăng nhập thật ở mọi test.

Ví dụ với annotation:

    @WebMvcTest(AdminController.class)
    @Import(SecurityConfig.class)
    class AdminControllerTest {

        @Autowired
        MockMvc mockMvc;

        @Test
        @WithMockUser(username = "student", roles = "STUDENT")
        void studentCannotOpenAdminPage() throws Exception {
            mockMvc.perform(get("/admin/reports"))
                    .andExpect(status().isForbidden());
        }

        @Test
        @WithMockUser(username = "admin", roles = "ADMIN")
        void adminCanOpenAdminPage() throws Exception {
            mockMvc.perform(get("/admin/reports"))
                    .andExpect(status().isOk());
        }
    }

Ví dụ giả định cấu hình ứng dụng trả 403 cho user đã xác thực nhưng thiếu quyền. Với form login, request chưa xác thực có thể được chuyển hướng đến trang đăng nhập; với REST API, có thể trả 401. Hãy kiểm tra đúng AuthenticationEntryPoint của ứng dụng.

@WithMockUser tạo một người dùng giả trong SecurityContext để kiểm thử authorization. Nó không thực hiện quy trình đăng nhập, không kiểm tra mật khẩu và không chứng minh session fixation hoặc cookie được cấu hình đúng.

### Roles và authorities

Trong Spring Security:

- Roles thường được ánh xạ thành authority có tiền tố ROLE_.
- Authorities là các quyền cụ thể được khai báo trực tiếp.

Ví dụ:

    @Test
    @WithMockUser(authorities = "course:approve")
    void userWithApprovalPermissionCanApprove() throws Exception {
        mockMvc.perform(post("/courses/42/approve")
                        .with(csrf()))
                .andExpect(status().isOk());
    }

Khi dùng thuộc tính roles, Spring Security tự thêm tiền tố ROLE_. Không truyền giá trị ROLE_ADMIN vào thuộc tính roles vì có thể tạo tiền tố kép. Nếu ứng dụng dùng permission cụ thể, hãy dùng authorities và test đúng tên quyền mà policy kiểm tra.

### Dùng request post processor

Có thể đặt user cho từng request:

    mockMvc.perform(get("/admin/reports")
            .with(user("student").roles("STUDENT")))
        .andExpect(status().isForbidden());

Hoặc:

    mockMvc.perform(get("/courses/42")
            .with(user("reviewer")
                    .authorities(
                            new SimpleGrantedAuthority("course:read"))))
        .andExpect(status().isOk());

Cách này hữu ích khi một test cần chạy nhiều request với actor khác nhau hoặc khi muốn tạo danh tính có authority cụ thể.

## 8. Kiểm thử method security

Một số ứng dụng dùng annotation như @PreAuthorize để bảo vệ phương thức:

    @Service
    public class ReportService {

        @PreAuthorize("hasRole('ADMIN')")
        public Report generateMonthlyReport() {
            return reportRepository.generateMonthlyReport();
        }
    }

Cần bật method security trong cấu hình ứng dụng, ví dụ bằng @EnableMethodSecurity. Test phải chạy qua Spring proxy để annotation được áp dụng. Gọi trực tiếp một object được tạo bằng new trong unit test không kiểm tra được interceptor của Spring.

Có thể kiểm thử:

- User có role ADMIN gọi thành công.
- User có role STUDENT bị từ chối.
- User chưa xác thực bị từ chối nếu phương thức yêu cầu authentication.
- Repository hoặc dependency tạo báo cáo không được gọi khi access bị từ chối.

Nếu test trực tiếp method security, dùng Spring integration test hoặc cấu hình test context có proxy. Unit test cho policy logic vẫn có thể gọi policy object trực tiếp.

### Không chỉ test annotation

Annotation có thể đúng nhưng method được gọi từ một đường khác không qua proxy hoặc policy chỉ kiểm tra role mà quên quyền trên tài nguyên. Hãy kết hợp test method security với test use case và endpoint thật.

## 9. Kiểm thử quyền trên từng tài nguyên

Quyền truy cập đối tượng (object-level authorization) là trọng tâm của các lỗi IDOR/BOLA. Test cần tạo dữ liệu thuộc nhiều owner và xác nhận truy vấn cũng như thao tác được giới hạn theo actor.

Một query service có thể nhận actor ID và resource ID:

    public record GetProfileQuery(
            UUID actorId,
            UUID profileId) {
    }

    @Service
    public class GetProfile {
        private final ProfileRepository profiles;
        private final ProfileAccessPolicy accessPolicy;

        public GetProfile(
                ProfileRepository profiles,
                ProfileAccessPolicy accessPolicy) {
            this.profiles = profiles;
            this.accessPolicy = accessPolicy;
        }

        public ProfileDetails execute(GetProfileQuery query) {
            Profile profile = profiles.findById(query.profileId())
                    .orElseThrow(ProfileNotFoundException::new);

            accessPolicy.checkCanView(query.actorId(), profile);

            return ProfileDetails.from(profile);
        }
    }

Trong một ứng dụng, có thể dùng truy vấn giới hạn ngay từ repository, chẳng hạn tìm theo cả profile ID và owner ID. Cách đó giảm khả năng vô tình tải dữ liệu không thuộc actor và có thể tránh một số đường truy cập sai.

    Optional<Profile> findByIdAndOwnerId(
            UUID profileId,
            UUID ownerId);

Dù dùng cách nào, quyền vẫn cần được xác định theo policy của ứng dụng. Không dùng ID do client gửi làm bằng chứng sở hữu.

### Test không chỉ kiểm tra response

Một test cho request cập nhật hồ sơ của người khác nên xác nhận:

1. Response bị từ chối theo chính sách.
2. Use case hoặc repository update không được gọi, nếu từ chối xảy ra ở lớp web.
3. Nếu policy nằm trong Application Service, không có thay đổi được lưu.
4. Nội dung hồ sơ gốc vẫn giữ nguyên.
5. Owner hợp lệ vẫn có thể đọc và cập nhật tài nguyên của mình.

Nếu test chỉ xác nhận status 403, nó có thể bỏ sót lỗi code đã cập nhật dữ liệu trước khi phát hiện quyền không hợp lệ.

## 10. Kiểm thử cách ly tenant

Trong hệ thống multi-tenant, một người dùng thường thuộc về một tenant hoặc tổ chức. Mỗi query và command phải giới hạn dữ liệu theo tenant hiện tại.

Ví dụ, Tenant A và Tenant B cùng có một đơn hàng với ID riêng. User của Tenant A không được đọc, sửa hoặc xóa đơn hàng của Tenant B.

### Xác định tenant từ nguồn đáng tin cậy

Tenant ID nên được lấy từ principal hoặc security context đã được xác thực, hoặc từ một cơ chế tenant resolution đã được kiểm tra. Không tin tenantId gửi trong request body hoặc query parameter nếu người dùng có thể tự thay đổi giá trị đó.

Ví dụ command nội bộ:

    public record GetInvoiceQuery(
            UUID actorId,
            UUID tenantId,
            UUID invoiceId) {
    }

Controller lấy actor và tenant từ principal:

    @GetMapping("/invoices/{invoiceId}")
    public InvoiceResponse detail(
            @PathVariable UUID invoiceId,
            @AuthenticationPrincipal AppPrincipal principal) {

        InvoiceDetails details = getInvoice.execute(
                new GetInvoiceQuery(
                        principal.userId(),
                        principal.tenantId(),
                        invoiceId));

        return InvoiceResponse.from(details);
    }

Query repository có thể giới hạn theo tenant:

    Optional<Invoice> findByIdAndTenantId(
            UUID invoiceId,
            UUID tenantId);

### Test cách ly tenant

Tạo tối thiểu:

- User A thuộc Tenant A.
- User B thuộc Tenant B.
- Invoice A thuộc Tenant A.
- Invoice B thuộc Tenant B.

Kiểm tra:

- User A đọc Invoice A thành công.
- User A không đọc Invoice B.
- User A không cập nhật hoặc xóa Invoice B.
- User A gửi tenantId của Tenant B trong request cũng không đổi được tenant context.
- User B vẫn đọc và sửa Invoice B theo quyền.
- Danh sách, tìm kiếm, export, count và autocomplete đều giới hạn theo tenant.

Đừng chỉ test endpoint chi tiết theo ID. Lỗi tenant leak thường xuất hiện trong endpoint tìm kiếm, báo cáo, thống kê, export hoặc truy vấn phụ.

### Kiểm tra khóa và ràng buộc dữ liệu

Với dữ liệu tenant, cần xem xét unique constraint có bao gồm tenant ID hay không. Ví dụ, mã hóa đơn có thể duy nhất trong từng tenant chứ không nhất thiết duy nhất toàn hệ thống. Test integration nên xác nhận truy vấn, index và constraint phản ánh đúng mô hình tenant.

Nếu database dùng row-level security, cần test cả cấu hình session/database role và cách transaction đặt tenant context. Không chỉ dựa vào test repository giả lập.

## 11. Kiểm thử field-level authorization và mass assignment

Một user có thể được phép cập nhật tên hiển thị nhưng không được đổi role, owner ID hoặc trạng thái duyệt. Nếu request bind trực tiếp vào entity, client có thể gửi thêm trường nhạy cảm.

Ví dụ request hợp lệ:

    public record UpdateProfileRequest(
            String displayName,
            String phoneNumber) {
    }

Không đưa các trường role, tenantId, ownerId hoặc accountStatus vào DTO cập nhật công khai nếu người dùng không được thay đổi chúng.

### Test trường bị cấm

Gửi request có thêm trường role:

    mockMvc.perform(patch("/profiles/me")
            .with(user("alice").roles("USER"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "Alice",
                  "role": "ADMIN"
                }
                """))
        .andExpect(status().is2xxSuccessful());

Ví dụ trên chỉ kiểm tra việc cập nhật trường được phép nếu serializer bỏ qua trường lạ. Nếu API chọn chính sách từ chối trường không khai báo, test cần kỳ vọng 400. Dù chính sách nào, sau request phải xác nhận role của Alice vẫn không đổi.

Không coi việc serializer bỏ qua trường lạ là đủ. Test phải đọc lại dữ liệu để xác nhận trường nhạy cảm không bị thay đổi. Nếu request DTO vô tình chứa role, test này sẽ phát hiện lỗi.

### Kiểm tra quyền theo trường

Một số vai trò có thể được phép sửa trường khác nhau. Ví dụ Instructor được sửa mô tả khóa học nhưng chỉ Admin được thay trạng thái xuất bản. Có thể tách command hoặc dùng policy rõ ràng cho từng hành động. Test cần chứng minh user thường không thay được trường đặc quyền qua API, form hoặc endpoint khác.

## 12. Kiểm thử session lifecycle

Session là trạng thái duy trì giữa nhiều HTTP request. Với ứng dụng MVC dùng session cookie, test cần xác nhận vòng đời session phù hợp với chính sách bảo mật.

Các mốc chính:

1. Trước đăng nhập: người dùng chưa có SecurityContext đã xác thực.
2. Sau đăng nhập: request tiếp theo nhận diện đúng user.
3. Khi xác thực thành công: session fixation protection được áp dụng.
4. Khi logout: SecurityContext và session được xử lý theo cấu hình.
5. Khi session hết hạn: request tiếp theo không còn được xem là đã đăng nhập.
6. Khi đăng nhập bằng tài khoản khác: dữ liệu và quyền của user cũ không được giữ lại.

### Kiểm thử đăng nhập

@WithMockUser hữu ích để kiểm tra authorization, nhưng nó không kiểm tra form login, password encoder, authentication provider hoặc session được tạo ra như thế nào.

Để kiểm tra quy trình đăng nhập, hãy gửi request qua endpoint login thật trong test context, dùng tài khoản test và password encoder được cấu hình:

    mockMvc.perform(post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "test-password"))
        .andExpect(status().is3xxRedirection());

Sau khi login thành công, dùng session từ response/request test để gửi request tiếp theo và xác nhận danh tính đã được lưu đúng. Chi tiết lấy session phụ thuộc cách MockMvc test được thiết lập; có thể dùng MockHttpSession và MvcResult để giữ trạng thái giữa các request.

### Kiểm thử session fixation

Session fixation xảy ra khi ứng dụng tiếp tục sử dụng một session ID do client đã biết trước cả sau khi người dùng đăng nhập. Kẻ tấn công có thể cố gắng khiến nạn nhân dùng một session ID mà kẻ tấn công biết.

Spring Security có session fixation protection trong cấu hình servlet thông thường. Sau khi authentication thành công, session ID nên được thay đổi hoặc session mới được tạo theo chiến lược cấu hình.

Một test nên:

- Tạo session trước đăng nhập.
- Gửi login request qua filter chain.
- Xác nhận authentication thành công.
- Xác nhận session ID được thay đổi hoặc session cũ không còn là session xác thực theo chiến lược.
- Xác nhận request sau login có danh tính đúng.

MockMvc hữu ích để kiểm tra hành vi filter, nhưng việc xác nhận cookie/session ID ở cấp container nên có integration test chạy với servlet container thật nếu đó là yêu cầu quan trọng của hệ thống.

### Kiểm thử logout

Logout cần xóa hoặc vô hiệu hóa trạng thái xác thực theo cấu hình. Với Spring Security, endpoint logout mặc định thường dùng POST khi CSRF protection bật.

Test cần:

- Đăng nhập thành công.
- Gửi POST logout với CSRF token.
- Gửi request tiếp theo bằng session cũ.
- Xác nhận request được xem là anonymous hoặc bị chuyển đến login/401.
- Xác nhận dữ liệu riêng tư không còn truy cập được qua session cũ.

Không chỉ kiểm tra redirect sau logout. Phải kiểm tra request kế tiếp.

### Kiểm thử timeout

Session hết hạn sau khoảng thời gian không hoạt động theo cấu hình. Test với MockMvc có thể mô phỏng trạng thái session, nhưng thời điểm hết hạn thực tế phụ thuộc container và session store.

Integration test nên xác nhận:

- Session hết hạn bị từ chối.
- Người dùng được yêu cầu đăng nhập lại.
- Session mới không thừa hưởng dữ liệu riêng tư của session cũ.
- Request đang mở nhưng gửi sau timeout nhận phản hồi phù hợp.

Không cần chờ timeout thật trong mọi test. Có thể cấu hình khoảng thời gian ngắn trong test profile hoặc mô phỏng session invalidation, đồng thời giữ ít nhất một test tích hợp cho hành vi container khi cần.

## 13. Kiểm thử cách ly session giữa người dùng

Mỗi request phải được xử lý với SecurityContext và session phù hợp. Không lưu danh tính hiện tại trong biến static hoặc singleton có thể bị ghi đè bởi request khác.

Một test cách ly session nên tạo hai session độc lập:

    MockHttpSession aliceSession = new MockHttpSession();
    MockHttpSession bobSession = new MockHttpSession();

Sau khi đăng nhập Alice và Bob theo hai luồng riêng, gửi request dùng từng session và xác nhận:

- Session Alice luôn đại diện Alice.
- Session Bob luôn đại diện Bob.
- Request của Alice không trả dữ liệu riêng tư của Bob.
- Logout Alice không làm logout Bob.
- Thay đổi dữ liệu của Alice không thay đổi dữ liệu hiển thị của Bob.
- Request tiếp theo không thừa hưởng principal từ session trước.

Đây là mô tả cấu trúc test. Khi viết test thật, hãy dùng luồng login và session repository của ứng dụng thay vì chỉ gắn một session rỗng rồi giả định nó đã được xác thực.

### Kiểm thử song song

Một số lỗi chỉ xuất hiện khi request chạy đồng thời. Có thể chạy hai request song song với hai principal khác nhau và dữ liệu riêng biệt để tìm:

- ThreadLocal không được dọn.
- MDC hoặc SecurityContext bị rò giữa thread.
- Biến mutable dùng chung chứa actor hiện tại.
- Cache không phân vùng theo user hoặc tenant.
- Repository query thiếu điều kiện owner/tenant.
- Session store ghi đè dữ liệu giữa hai người dùng.

Spring Security lưu SecurityContext theo cơ chế gắn với request/thread và cung cấp tích hợp cho tác vụ bất đồng bộ. Code tự tạo thread hoặc executor cần truyền context có chủ đích và dọn context sau khi xử lý.

Không dùng một test song song thiếu kiểm soát rồi kết luận hệ thống an toàn. Hãy tạo dữ liệu riêng, đồng bộ điểm bắt đầu và xác nhận kết quả của từng actor.

## 14. Kiểm thử CSRF cùng session và quyền truy cập

CSRF và authorization giải quyết các vấn đề khác nhau nhưng cùng ảnh hưởng đến request thay đổi trạng thái.

- CSRF kiểm tra request có token hợp lệ trong ngữ cảnh session hay không.
- Authorization kiểm tra actor có quyền thực hiện hành động trên tài nguyên hay không.

Một request cần cả hai điều kiện. Token hợp lệ không cấp thêm quyền. User có quyền cũng không được bỏ qua CSRF token khi ứng dụng dùng cookie session và cấu hình yêu cầu token.

Với MockMvc, có thể dùng Spring Security Test:

    mockMvc.perform(post("/profiles/42")
            .with(user("alice").roles("USER"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "Alice"
                }
                """))
        .andExpect(status().isOk());

Các test bổ sung:

- Thiếu CSRF token: bị từ chối trước Controller.
- Token hợp lệ nhưng actor không sở hữu tài nguyên: bị từ chối bởi authorization.
- Actor có quyền nhưng payload vi phạm validation: nhận lỗi validation.
- Actor có quyền và token hợp lệ: thao tác thành công.
- Không có session: nhận phản hồi authentication phù hợp.

Tách các điều kiện này giúp xác định test thất bại ở lớp nào và tránh nhầm lỗi 403 do CSRF với lỗi 403 do phân quyền.

## 15. Kiểm thử với MockMvc và Spring Security Test

Để dùng các helper như @WithMockUser, user(), csrf() hoặc jwt(), dự án thường cần dependency Spring Security Test cùng phiên bản với Spring Security đang sử dụng.

Một cấu hình MVC test có thể như sau:

    @WebMvcTest(ProfileController.class)
    @Import(SecurityConfig.class)
    class ProfileControllerSecurityTest {

        @Autowired
        MockMvc mockMvc;

        @MockBean
        ProfileService profileService;

        @Test
        void anonymousUserCannotOpenPrivateProfile() throws Exception {
            mockMvc.perform(get("/profiles/me"))
                    .andExpect(status().is3xxRedirection());
        }

        @Test
        @WithMockUser(username = "alice", roles = "USER")
        void authenticatedUserCanOpenOwnProfile() throws Exception {
            when(profileService.getOwnProfile("alice"))
                    .thenReturn(new ProfileResponse("Alice"));

            mockMvc.perform(get("/profiles/me"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.displayName").value("Alice"));
        }
    }

Đây là ví dụ minh họa. Tên endpoint, response và AuthenticationEntryPoint cần khớp với cấu hình ứng dụng. Trong các phiên bản Spring Boot mới, @MockBean có thể được thay bằng cơ chế bean override tương ứng của phiên bản; dùng annotation phù hợp với stack của dự án.

### @WithMockUser và @WithUserDetails

- @WithMockUser tạo một user giả với username, roles hoặc authorities được khai báo.
- @WithUserDetails tải user qua UserDetailsService của test context, hữu ích khi cần kiểm tra mapping user thực tế.
- user() tạo Authentication cho một request cụ thể.
- jwt() tạo JWT Authentication giả cho endpoint dùng OAuth2 Resource Server.

Các helper này không thay thế test đăng nhập thật. Hãy dùng chúng để tập trung vào authorization; dùng integration test cho authentication provider, session và cookie.

### Kiểm thử JWT Resource Server

Nếu API dùng bearer JWT thay vì session, có thể dùng request post processor jwt():

    mockMvc.perform(get("/api/reports")
            .with(jwt().authorities(
                    new SimpleGrantedAuthority("report:read"))))
        .andExpect(status().isOk());

Test này xác nhận quyền sau khi JWT Authentication đã được tạo trong test. Nó không xác nhận chữ ký token, issuer, audience hoặc cấu hình decoder thực tế. Những phần đó cần integration test riêng với decoder và cấu hình bảo mật.

## 16. Kiểm thử ở các tầng khác nhau

Không một loại test nào đủ cho mọi yêu cầu. Hãy phân chia trách nhiệm:

| Loại test | Phạm vi | Điều chứng minh |
|---|---|---|
| Unit test policy | Access policy, ownership rule | Quy tắc cho phép/từ chối theo actor và resource |
| Application service test | Use case và repository port giả lập | Không thực hiện hành động khi actor thiếu quyền |
| MVC slice test | Filter, route, controller và response | Authentication/authorization ở ranh giới HTTP |
| Persistence integration test | Repository, ORM, database | Query giới hạn owner/tenant và constraint hoạt động |
| Full integration test | Login, session, cookie, container | Session lifecycle, fixation, logout và timeout |
| Concurrency test | Nhiều request đồng thời | Không rò session hoặc dữ liệu giữa actor |

### Unit test policy

Kiểm tra các trường hợp như owner, non-owner, admin, tenant khác và tài nguyên ở trạng thái không cho phép. Test nên nhanh và không cần web server.

### Application service test

Dùng fake repository hoặc mock để xác nhận use case kiểm tra quyền trước khi ghi dữ liệu. Nếu access policy từ chối, verify rằng phương thức save không được gọi.

### MVC slice test

Kiểm tra SecurityFilterChain, URL authorization, method security được tích hợp và response status. Dùng user/authorities giả lập.

### Persistence integration test

Dùng database test phù hợp để xác nhận truy vấn theo owner và tenant thực sự giới hạn dữ liệu. H2 có thể không mô phỏng đầy đủ hành vi của database sản xuất, đặc biệt với row-level security, collation, constraint hoặc SQL đặc thù. Với tính năng phụ thuộc database cụ thể, dùng Testcontainers hoặc môi trường tích hợp tương ứng.

### Full integration test

Kiểm tra login/logout, session fixation, cookie flags và timeout qua servlet container. Đây là nơi xác minh hành vi không được mô phỏng đầy đủ trong MockMvc.

## 17. Kiểm thử truy vấn, cache và tác vụ bất đồng bộ

Cách ly người dùng có thể bị phá vỡ ở những nơi không trực tiếp nhìn thấy trong Controller.

### Repository query

Kiểm tra mọi truy vấn đọc và ghi có áp dụng owner/tenant filter theo đúng policy. Các endpoint export, search, count, autocomplete và report cần được đưa vào phạm vi test.

### Cache

Nếu cache kết quả theo resource ID nhưng dữ liệu phụ thuộc người dùng hoặc tenant, key có thể thiếu user/tenant context. Test nên gọi cùng endpoint với hai actor và xác nhận response không bị lấy từ cache của actor trước.

Ví dụ, cache key của dashboard có thể cần chứa tenant ID và phạm vi quyền. Không nên dùng một key toàn cục cho dữ liệu riêng tư.

### Tác vụ nền và message consumer

Một tác vụ bất đồng bộ có thể chạy sau khi request kết thúc. Nếu nó cần actor hoặc tenant context, phải truyền dữ liệu cần thiết rõ ràng vào message/job và kiểm tra lại quyền hoặc tính hợp lệ theo chính sách. Không phụ thuộc vào ThreadLocal hoặc SecurityContext của request ban đầu sau khi request đã kết thúc.

Test nên xác nhận message của tenant A không làm worker truy cập dữ liệu tenant B và context được dọn sau khi xử lý.

## 18. Dữ liệu test an toàn và có khả năng lặp lại

Test bảo mật cần dữ liệu được kiểm soát:

- Tạo user và resource bằng factory hoặc fixture có tên rõ ràng.
- Dùng ID khác nhau cho từng user và tenant.
- Không dùng tài khoản thật hoặc dữ liệu production.
- Không dùng password thật hoặc token thật.
- Xác định rõ role, authority, owner và tenant của từng fixture.
- Dọn dữ liệu hoặc rollback transaction theo chiến lược test.
- Không dựa vào thứ tự test chạy.
- Không chia sẻ mutable fixture giữa các test song song.

Một fixture tốt giúp người đọc hiểu ngay quan hệ:

    alice = user("alice", tenantA)
    bob = user("bob", tenantA)
    carol = user("carol", tenantB)

    aliceProfile = profile(owner=alice, tenant=tenantA)
    bobProfile = profile(owner=bob, tenant=tenantA)
    carolProfile = profile(owner=carol, tenant=tenantB)

Từ đó test có thể mô tả chính xác Alice được xem hồ sơ nào, không được xem hồ sơ nào và dữ liệu tenant nào cần được cách ly.

## 19. Các lỗi thường gặp khi kiểm thử bảo mật

### Chỉ kiểm tra route cần đăng nhập

Một route yêu cầu authenticated user vẫn có thể lộ tài nguyên của người dùng khác. Cần test object-level authorization.

### Chỉ kiểm tra status 403

Status đúng chưa chứng minh không có tác dụng phụ. Hãy đọc lại database hoặc xác nhận repository không được gọi.

### Dùng cùng một user cho mọi test

Test không thể phát hiện lỗi truy cập ngang nếu không có ít nhất hai actor và tài nguyên thuộc các actor khác nhau.

### Dùng @WithMockUser để kết luận session an toàn

Annotation này tạo SecurityContext giả. Nó không kiểm tra login, session fixation, cookie, logout hoặc timeout.

### Bỏ qua tenant trong test

Hệ thống multi-tenant cần fixture thuộc nhiều tenant và kiểm tra cả read, write, search, export và report.

### Test chỉ theo role

Role có thể chưa đủ để quyết định quyền trên resource. Cần kiểm tra ownership, assignment, trạng thái và tenant.

### Tin ID do client gửi

ID hợp lệ không chứng minh quyền truy cập. Test phải thay ID sang tài nguyên của actor khác.

### Không test field nhạy cảm

Request có thể thêm role, ownerId hoặc tenantId. Test phải xác nhận server bỏ qua hoặc từ chối trường ngoài hợp đồng và dữ liệu đặc quyền không đổi.

### Dùng H2 cho mọi kiểm thử database

Database in-memory có thể không mô phỏng row-level security hoặc constraint đặc thù. Dùng integration test với database tương thích khi chính sách bảo mật phụ thuộc tính năng của database sản xuất.

### Để trạng thái test rò sang test khác

SecurityContext, session hoặc fixture dùng chung có thể khiến kết quả phụ thuộc thứ tự chạy. Dọn context, session và dữ liệu sau mỗi test; kiểm tra riêng các kịch bản song song.

## 20. Quy trình xây dựng bộ test quyền truy cập và session

Khi thêm một chức năng MVC, có thể thực hiện theo trình tự:

1. Viết ma trận actor, action, resource và tenant.
2. Xác định endpoint public, authenticated và restricted.
3. Xác định policy ở cấp object, field và tenant.
4. Tạo fixture có ít nhất hai user và hai phạm vi dữ liệu khi cần.
5. Viết test dương cho actor có quyền.
6. Viết test âm cho anonymous, non-owner, role thấp và tenant khác.
7. Xác nhận request bị từ chối không đọc hoặc ghi dữ liệu ngoài phạm vi.
8. Kiểm thử CSRF cùng authorization cho request thay đổi trạng thái dùng cookie session.
9. Kiểm thử login, session rotation, logout và timeout bằng test phù hợp.
10. Bổ sung persistence integration test cho query filter và constraint.
11. Kiểm tra cache, export, search và tác vụ nền có giữ đúng context.
12. Chạy test song song có kiểm soát để tìm lỗi rò context.

## 21. Checklist trước khi phát hành

- Anonymous user không truy cập được endpoint riêng tư.
- User đã đăng nhập nhưng thiếu role/authority bị từ chối.
- User không đọc, sửa hoặc xóa tài nguyên của user khác.
- Quyền trên từng object được kiểm tra ở use case hoặc policy phù hợp.
- Tenant context lấy từ nguồn đã xác thực, không tin tenant ID tùy ý từ client.
- Danh sách, search, count, export và report đều được giới hạn theo owner/tenant.
- Trường role, ownerId và tenantId không thể bị sửa qua mass assignment.
- Request bị từ chối không tạo side effect.
- Session của user này không được dùng cho user khác.
- Session ID được bảo vệ khi đăng nhập theo chính sách session fixation.
- Logout làm mất quyền sử dụng session cũ.
- Session timeout được xử lý đúng.
- CSRF và authorization được test độc lập và kết hợp.
- Cache và tác vụ bất đồng bộ không làm rò dữ liệu giữa actor.
- Test dùng dữ liệu giả lập, không phụ thuộc thứ tự và có thể chạy lặp lại.

## Kết luận

Kiểm thử quyền truy cập và cách ly người dùng phải chứng minh server chỉ cho phép actor thực hiện hành động trên đúng tài nguyên và trong đúng phạm vi dữ liệu. Authentication xác định danh tính; authorization kiểm tra quyền theo route, method, object, field và tenant. Session lifecycle bảo đảm danh tính không bị giữ lại hoặc dùng nhầm giữa các request và người dùng.

Trong MVC, Spring Security Test và MockMvc giúp kiểm tra filter, route và method security; unit test xác nhận policy; integration test xác nhận truy vấn, transaction và session thực tế. Kết hợp các tầng test, dùng nhiều actor và dữ liệu thuộc nhiều phạm vi, đồng thời xác nhận request bị từ chối không tạo tác dụng phụ sẽ giúp phát hiện IDOR/BOLA, privilege escalation và rò rỉ dữ liệu trước khi phát hành.
