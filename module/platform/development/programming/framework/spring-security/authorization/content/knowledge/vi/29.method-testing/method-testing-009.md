# Kiểm thử meta-annotation, role hierarchy và PermissionEvaluator trong Spring Security

## 1. Mục tiêu và bối cảnh

Ở tầng service, việc kiểm tra quyền không chỉ là xác nhận người dùng đã đăng nhập. Một phương thức có thể được bảo vệ bằng **meta-annotation** chứa quy tắc @PreAuthorize, chấp nhận một vai trò nhờ **role hierarchy**, hoặc quyết định quyền trên từng đối tượng nhờ **PermissionEvaluator**. Bài này tập trung vào cách viết kiểm thử để chứng minh cả trường hợp **được phép** và **bị từ chối**, đồng thời phát hiện khi cấu hình bảo mật chưa thực sự được áp dụng.

Sau bài học, bạn có thể:

1. Viết kiểm thử JUnit 5 cho Spring-managed service dùng @EnableMethodSecurity và @PreAuthorize.
2. Kiểm tra meta-annotation bảo mật của **mã ứng dụng**; đồng thời tái sử dụng meta-annotation @WithMockUser cho **dữ liệu kiểm thử**.
3. Chứng minh các quyền kế thừa từ ROLE_ADMIN xuống ROLE_MANAGER rồi ROLE_VIEWER trong một role hierarchy, và chứng minh chiều ngược lại không được cấp.
4. Kiểm tra PermissionEvaluator theo tài nguyên, định danh và hành động; phân biệt hai overload của hasPermission.
5. Nhận biết kiểm thử “xanh giả” vì gọi trực tiếp một đối tượng không đi qua proxy hoặc chỉ viết tình huống được phép.

**Phạm vi:** method security cho Spring MVC/Servlet hoặc service đồng bộ, Java 17+, Spring Security 6.x/7.x. Bài không hướng dẫn thay thế kiểm thử endpoint HTTP và không áp dụng nguyên xi cho reactive method security.

## 2. Mô hình quyết định quyền

Spring Security áp dụng @PreAuthorize khi gọi phương thức qua **Spring AOP proxy** của một bean được quản lý. Nó lấy Authentication từ SecurityContext, đánh giá biểu thức SpEL và chỉ gọi thân phương thức nếu điều kiện đạt. Nếu bị từ chối, trong kiểm thử gọi service trực tiếp qua proxy thường nhận được AccessDeniedException (hoặc lớp con); không nên đồng nhất ngoại lệ Java này với mã HTTP 403, vì 403 là kết quả của lớp xử lý yêu cầu web.

~~~text
JUnit 5 + Spring Test
       │
       ├── @WithMockUser / @WithMockAdmin
       │        └── điền Authentication vào SecurityContext
       │
       └── gọi bean service qua Spring AOP proxy
                     │
                     └── @PreAuthorize / meta-annotation
                               │
                               ├── hasAuthority(...) → authority phù hợp
                               ├── hasRole(...)      → vai trò + role hierarchy
                               └── hasPermission(...) → PermissionEvaluator
                                         │
                                    cho phép / từ chối
~~~

Ba khái niệm phục vụ những bài toán khác nhau:

| Cơ chế | Điều cần kiểm thử | Câu hỏi nghiệp vụ |
| --- | --- | --- |
| Meta-annotation bảo mật | Annotation tùy biến có được nhận diện và thực thi? | Chỉ người có quyền phê duyệt mới duyệt hóa đơn? |
| Role hierarchy | Vai trò cao có thừa hưởng quyền vai trò thấp và không thừa hưởng ngược? | ADMIN có được xem tính năng dành cho VIEWER? |
| PermissionEvaluator | Quyết định có phụ thuộc đúng người, tài nguyên và hành động? | Alice có được đọc tài liệu số 42, nhưng không được đọc số 43? |

**Phân biệt hai loại meta-annotation:** Một annotation có @PreAuthorize (ví dụ @CanApprove) bảo vệ **mã production**. Một annotation có @WithMockUser (ví dụ @WithMockAdmin) chỉ thiết lập **Authentication trong test**. Việc test được chạy với người dùng có quyền không tự chứng minh service đã bật bảo vệ; phải có ít nhất một test yêu cầu bị từ chối.

## 3. Dựng môi trường kiểm thử phương thức

Trong dự án Spring Boot 3.x / Java 17+ sử dụng Gradle, cần các dependency sau (Spring Boot quản lý phiên bản tương thích):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Nếu dự án đã có các dependency này, không thêm lại. Spring Security Test tích hợp với Spring TestContext thông qua WithSecurityContextTestExecutionListener. @SpringJUnitConfig tạo ApplicationContext cho JUnit Jupiter, tự tham gia các TestExecutionListener mặc định, rồi chuẩn bị và dọn SecurityContext cho từng test. **@WithMockUser không cần tài khoản có thật**; nếu mã cần principal là kiểu UserDetails riêng của ứng dụng, hãy dùng @WithUserDetails cùng UserDetailsService thực, hoặc tự tạo @WithSecurityContext.

Đặt một tệp **src/test/java/demo/authorization/MethodSecurityLessonTest.java** với nội dung đầy đủ dưới đây. Cấu hình Spring cho bài test được khai báo ngay trong lớp, nên không cần ứng dụng web đang chạy. Ví dụ dùng vai trò ADMIN > MANAGER > VIEWER và một quy tắc đọc tài liệu có chủ đích đơn giản, phục vụ minh họa; trong ứng dụng thật cần thay bằng nguồn quyền đáng tin cậy.

~~~java
package demo.authorization;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.Serializable;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MethodSecurityLessonTest.SecurityConfig.class)
class MethodSecurityLessonTest {

    // Meta-annotation của ứng dụng: quy tắc thật trên phương thức.
    @Target({ElementType.METHOD, ElementType.TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @PreAuthorize("hasAuthority('invoice:approve')")
    public @interface CanApprove {}

    // Meta-annotation của test: một danh tính giả tái sử dụng được.
    @Target({ElementType.METHOD, ElementType.TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @WithMockUser(username = "chief", roles = "ADMIN")
    public @interface WithMockAdmin {}

    public static class LessonService {

        @CanApprove
        public String approveInvoice() {
            return "approved";
        }

        @PreAuthorize("hasRole('VIEWER')")
        public String viewReport() {
            return "report";
        }

        // #p0 là tham số thứ nhất, không phụ thuộc cờ biên dịch -parameters.
        @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
        public String readDocument(Long id) {
            return "document:" + id;
        }
    }

    // Chỉ Alice được đọc Document 42. Đây là chính sách giả lập cho test.
    static class DemoDocumentPermissionEvaluator implements PermissionEvaluator {

        @Override
        public boolean hasPermission(
                Authentication auth, Object domainObject, Object permission) {
            // Bài này kiểm thử biến thể có id + type; từ chối an toàn
            // cho biến thể nhận trực tiếp domain object.
            return false;
        }

        @Override
        public boolean hasPermission(
                Authentication auth, Serializable id, String type, Object permission) {
            return auth != null
                    && auth.isAuthenticated()
                    && "alice".equals(auth.getName())
                    && Long.valueOf(42L).equals(id)
                    && "Document".equals(type)
                    && "read".equals(permission);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class SecurityConfig {

        @Bean
        LessonService lessonService() {
            return new LessonService();
        }

        // static để bean expression handler được công bố sớm
        // trước khi các cấu hình method security được khởi tạo.
        @Bean
        static MethodSecurityExpressionHandler methodSecurityExpressionHandler() {
            var handler = new DefaultMethodSecurityExpressionHandler();
            handler.setRoleHierarchy(RoleHierarchyImpl.fromHierarchy(
                    "ROLE_ADMIN > ROLE_MANAGER\nROLE_MANAGER > ROLE_VIEWER"));
            handler.setPermissionEvaluator(
                    new DemoDocumentPermissionEvaluator());
            return handler;
        }
    }

    @Autowired
    LessonService service; // Bean đã được Spring bọc bằng proxy bảo mật.

    @Test
    @WithMockUser(authorities = "invoice:approve")
    void metaAnnotationAllowsExpectedAuthority() {
        assertEquals("approved", service.approveInvoice());
    }

    @Test
    @WithMockAdmin
    void metaAnnotationStillDeniesAdminWithoutApproveAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> service.approveInvoice());
    }

    @Test
    @WithMockAdmin
    void adminInheritsViewerRole() {
        assertEquals("report", service.viewReport());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCanViewReportDirectly() {
        assertEquals("report", service.viewReport());
    }

    @Test
    @WithMockUser(roles = "GUEST")
    void guestDoesNotInheritViewerRole() {
        assertThrows(AccessDeniedException.class,
                () -> service.viewReport());
    }

    @Test
    @WithMockUser(username = "alice")
    void permissionEvaluatorAllowsMatchingUserAndDocument() {
        assertEquals("document:42", service.readDocument(42L));
    }

    @Test
    @WithMockUser(username = "bob")
    void permissionEvaluatorDeniesOtherUser() {
        assertThrows(AccessDeniedException.class,
                () -> service.readDocument(42L));
    }

    @Test
    @WithMockUser(username = "alice")
    void permissionEvaluatorDeniesOtherDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.readDocument(43L));
    }
}
~~~

**Chạy:** Tại gốc dự án Gradle có wrapper, chạy:

~~~bash
./gradlew test --tests "demo.authorization.MethodSecurityLessonTest"
~~~

Trên Windows/PowerShell dùng lệnh tương đương **.\gradlew.bat test --tests "demo.authorization.MethodSecurityLessonTest"**. Kỳ vọng: **8 test thành công**, không có đầu ra chuẩn (stdout) nào được mã kiểm thử tự in. Số lượng và trạng thái do JUnit/Gradle báo; không nên chép nguyên một mẫu log vì log phụ thuộc phiên bản và cấu hình runner.

Nếu dùng dự án Spring Boot 4 / Spring Security 7, áp dụng dependency test phù hợp với dự án đang dùng; ví dụ ở đây chỉ giả định một dự án Boot 3.x đã cấu hình test JUnit Jupiter. Cơ chế kiểm thử method security là cùng ý tưởng, nhưng nên đối chiếu phiên bản framework và starter khi chuyển dự án.

## 4. Đọc và chứng minh kết quả theo từng cơ chế

### 4.1. Meta-annotation bảo mật

@CanApprove kết hợp @PreAuthorize với chính sách hasAuthority('invoice:approve'). Spring Security quét meta-annotation nên một lời gọi **service.approveInvoice()** qua proxy phải bị kiểm soát như khi gắn @PreAuthorize trực tiếp.

- **Đường cho phép:** @WithMockUser(authorities = "invoice:approve") cấp đúng GrantedAuthority nên approveInvoice trả về chuỗi **approved**.
- **Đường từ chối:** @WithMockAdmin tạo người dùng chief có ROLE_ADMIN, nhưng cấu hình hierarchy hiện tại không cho ROLE_ADMIN suy ra invoice:approve; vì vậy cuộc gọi phải ném AccessDeniedException.
- **Ý nghĩa:** Nếu test từ chối bất ngờ thành công, hãy nghi ngờ @EnableMethodSecurity chưa có hiệu lực, method không được proxy, annotation sai phạm vi hoặc test gọi đối tượng tự new.

@WithMockAdmin là **meta-annotation dành cho test**: nó gói @WithMockUser(username = "chief", roles = "ADMIN") để không lặp dữ liệu. Có thể thêm @WithUserDetails hoặc @WithSecurityContext bên trong annotation tùy nhu cầu. Tránh nhầm annotation test với chính sách production; chúng tác động ở hai thời điểm khác nhau.

**Đối chiếu annotation:** Cần @Retention(RUNTIME) để framework nhìn thấy metadata ở runtime. @Target phải có METHOD/TYPE đúng nơi sẽ gắn. Nếu meta-annotation tùy biến nhận tham số để chèn vào SpEL, kiểm tra dấu nháy và biểu thức sau khi nội suy; không suy luận rằng mọi annotation tùy biến đều tự động được hiểu.

### 4.2. Role hierarchy

Vai trò ở đây tạo thành chuỗi:

~~~text
ROLE_ADMIN ⇒ ROLE_MANAGER ⇒ ROLE_VIEWER
~~~

Ký hiệu ⇒ nghĩa là vai trò bên trái **bao hàm** vai trò bên phải khi bộ đánh giá quyền tính các authority có thể đạt tới; nó không buộc Authentication ban đầu lưu thêm các authority thấp hơn.

- chief với roles="ADMIN" chỉ được @WithMockUser cấp ROLE_ADMIN, nhưng vẫn qua hasRole('VIEWER') nhờ handler đã kết nối RoleHierarchyImpl.
- VIEWER trực tiếp qua điều kiện và không cần thừa hưởng.
- GUEST bị từ chối vì không nằm trong chuỗi thừa hưởng. Tương tự, VIEWER không thể suy ra MANAGER hay ADMIN.

Với cấu hình mặc định, **hasRole('VIEWER')** tương ứng kiểm tra **ROLE_VIEWER**. Trong @WithMockUser, **roles = "ADMIN"** tự thêm ROLE_, còn **authorities = "invoice:approve"** là chuỗi nguyên vẹn; không viết roles="ROLE_ADMIN" và không mặc định coi mọi authority là role.

**Tại sao không chỉ khai báo một RoleHierarchy bean?** Các biểu thức @PreAuthorize được đánh giá bởi MethodSecurityExpressionHandler; ví dụ gắn role hierarchy tường minh lên DefaultMethodSecurityExpressionHandler để kết quả có thể kiểm chứng. Những đường cấp quyền khác, như @Secured và JSR-250, có cơ chế tích hợp riêng; phải kiểm thử đúng annotation đang dùng. Đừng suy từ việc hasRole trong HTTP filter hoạt động sang việc cấu hình ở method layer đã đúng.

**Khi tăng độ khó:** thêm các test MANAGER→VIEWER cho phép, VIEWER→MANAGER từ chối và một hierarchy nhiều nhánh. Nếu sửa chuỗi vai trò, cập nhật cả test cho phép và từ chối để tránh vô ý mở rộng quyền.

### 4.3. PermissionEvaluator

Biểu thức **hasPermission(#p0, 'Document', 'read')** truyền cho PermissionEvaluator: Authentication của người gọi, id ở tham số thứ nhất, tên loại tài nguyên **Document** và hành động **read**.

Interface có hai biến thể, phục vụ hai hình thức biểu thức:

| SpEL | Overload thực thi | Dữ liệu cần kiểm tra |
| --- | --- | --- |
| hasPermission(#document, 'read') | hasPermission(Authentication, Object, Object) | Đối tượng domain và quyền |
| hasPermission(#p0, 'Document', 'read') | hasPermission(Authentication, Serializable, String, Object) | Id, loại đối tượng và quyền |

Trong mã minh họa, overload dạng đối tượng trả **false** có chủ đích. Không nên trả **true** mặc định hoặc bỏ quên overload này khi ứng dụng có sử dụng nó. Trong ứng dụng thật, cả hai overload cần thống nhất cùng chính sách quyền sở hữu/ACL, kể cả khi tài nguyên null, id không tồn tại, permission không hợp lệ hoặc người dùng không có quyền.

**Ba kiểm thử tài nguyên** trong ví dụ bảo vệ ba trục riêng:

1. Alice + Document#42 + read ⇒ cho phép.
2. Bob + Document#42 + read ⇒ từ chối, dù id và hành động giống nhau.
3. Alice + Document#43 + read ⇒ từ chối, dù người dùng và hành động giống nhau.

Để đầy đủ hơn trong hệ thống thật, thêm kiểm thử đổi **read→write**, đổi loại **Document→Report**, id không tồn tại, null, quyền sau khi bị thu hồi và quyền của người dùng được ủy quyền. Cần giữ chính sách **mặc định từ chối** cho trường hợp không xác định.

**Tại sao chỉ mock Authentication chưa đủ?** PermissionEvaluator quyết định quyền theo dữ liệu miền nghiệp vụ. @WithMockUser chỉ tạo danh tính/authorities giả, không tạo dữ liệu quyền trong cơ sở dữ liệu. Với unit test của evaluator, dùng dữ liệu giả điều khiển được và assert các tổ hợp đúng/sai; với integration test, dùng repository/fixture kiểm chứng các quan hệ owner/tenant/ACL thật. Không nên làm mẫu test có điều kiện phụ thuộc vào thời gian, tài khoản hoặc dữ liệu môi trường thực.

## 5. Ma trận kiểm thử và tiêu chuẩn chấp nhận

| Mã | Điều kiện đầu vào | Lời gọi | Kết quả |
| --- | --- | --- | --- |
| M1 | authority invoice:approve | approveInvoice() | Được phép |
| M2 | ROLE_ADMIN, không có invoice:approve | approveInvoice() | Bị từ chối |
| H1 | ROLE_ADMIN | viewReport() | Được phép qua hierarchy |
| H2 | ROLE_VIEWER | viewReport() | Được phép trực tiếp |
| H3 | ROLE_GUEST | viewReport() | Bị từ chối |
| P1 | alice, id=42 | readDocument(42) | Được phép |
| P2 | bob, id=42 | readDocument(42) | Bị từ chối |
| P3 | alice, id=43 | readDocument(43) | Bị từ chối |

Với mỗi quy tắc bảo mật, tối thiểu có một phép thử **allow** và một phép thử **deny**. Test chỉ kiểm tra chuỗi trả về khi được phép không thể phát hiện việc interceptor đã tắt. Một cách xác nhận độc lập trong lúc chẩn đoán là kiểm tra **AopUtils.isAopProxy(service)**; trong bài này, các test từ chối là bằng chứng quan trọng hơn vì chúng phải thất bại nếu gọi trực tiếp LessonService không qua cơ chế bảo vệ.

Có thể thêm unit test riêng cho DemoDocumentPermissionEvaluator để khẳng định chính sách không phụ thuộc Spring context, rồi dùng các test service ở trên để chứng minh cấu hình handler thật sự gọi evaluator. Hai loại kiểm thử bổ sung cho nhau: đúng thuật toán quyền chưa đủ nếu wiring thiếu, còn wiring đúng chưa đủ nếu thuật toán quyền sai.

## 6. Các lỗi thường gặp và cách khắc phục

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Người không đủ quyền vẫn gọi được service | Thiếu @EnableMethodSecurity; gọi bằng new; self-invocation qua this; proxy không áp dụng | Lấy bean từ ApplicationContext, thêm test deny, kiểm tra AOP proxy |
| ADMIN không qua điều kiện VIEWER | Chưa gắn RoleHierarchy vào đúng expression handler, sai ROLE_ prefix, cấu hình khác môi trường test | Kiểm tra ROLE_ADMIN > ROLE_VIEWER và bean MethodSecurityExpressionHandler |
| hasPermission luôn từ chối | Chưa setPermissionEvaluator; mặc định không có evaluator phù hợp; gọi nhầm overload | Đặt breakpoint trong cả hai overload; kiểm tra id/type/permission |
| Test @WithMockUser xanh nhưng production lỗi principal | Principal giả là User chuẩn, không phải kiểu custom | Dùng @WithUserDetails hoặc @WithSecurityContext theo principal thật |
| Test deny báo sai loại exception | Lẫn ngữ cảnh HTTP với lời gọi service; hoặc không có Authentication | Xác định lời gọi đang đi qua proxy hay MockMvc; test đúng cấp độ |
| Kết quả khác nhau theo thứ tự chạy | Test tự sửa SecurityContext hoặc dữ liệu quyền chung mà không dọn | Dùng listener Spring Test, fixture độc lập, reset mock/DB |
| Hiểu sai roles và authorities | roles tự có ROLE_, authorities giữ nguyên chuỗi | Assert trực tiếp authority tạo bởi annotation test |
| Test service chạy nhưng không chạm controller | Chỉ kiểm tra tầng phương thức, chưa đi qua HTTP chain | Thêm MockMvc integration test riêng nếu cần xác nhận mapping và HTTP status |

**Cảnh báo về self-invocation:** Nếu một phương thức bên trong cùng bean gọi **this.securedMethod()**, cuộc gọi có thể không đi qua AOP proxy nên annotation bị bỏ qua. Kiểm thử gọi qua bean được inject mới phản ánh cơ chế method security; thiết kế service cần tránh đường gọi nội bộ vượt proxy hoặc dùng kiến trúc phù hợp.

**Cảnh báo về test HTTP:** @WithMockUser trên Spring Test gắn SecurityContext vào luồng chạy test. Nó phù hợp với lời gọi bean và nhiều kiểm thử MockMvc có cấu hình Spring Security; nó không tự chuyển danh tính sang một HTTP server thật chạy trên luồng khác. Với kiểm thử end-to-end, phải xác thực chính yêu cầu HTTP.

**Cảnh báo về phiên bản và API:** @EnableMethodSecurity là cấu hình hiện đại thay cho @EnableGlobalMethodSecurity. Nếu đang dùng @Secured/JSR-250, cần bật các chế độ tương ứng; không áp dụng mặc định cách đánh giá của @PreAuthorize cho mọi annotation. Khi dùng phiên bản Spring Security khác, kiểm tra tài liệu phiên bản đó về RoleHierarchy và handler.

## 7. Bài thực hành mở rộng

Hãy sửa bộ test theo thứ tự sau; mỗi bước cần thêm ít nhất một test từ chối trước khi coi tính năng đã xong:

1. Thêm phương thức **exportReport()** yêu cầu MANAGER; xác nhận ADMIN và MANAGER được phép, VIEWER bị từ chối.
2. Tạo meta-annotation **@CanReadDocument** bao bọc hasPermission với tham số id; xác nhận quy tắc được gọi như khi đặt @PreAuthorize trực tiếp.
3. Mở rộng evaluator để tài liệu có **owner**, **tenantId** và tập **allowedActions**; kiểm thử người cùng tenant, khác tenant, chủ sở hữu, người không phải chủ và quyền write không được cấp. Ưu tiên fixture xác định thay cho kết nối dữ liệu thật.
4. Viết một test cố tình gọi **new LessonService().viewReport()** và quan sát vì sao nó không được bảo vệ; sau đó giữ các test chính dùng bean proxy.
5. Thêm kiểm thử endpoint riêng bằng MockMvc nếu service được gọi qua controller, đối chiếu trường hợp bị chặn ở tầng HTTP và bị chặn ở tầng method.

**Tự đánh giá:** Bạn đã chứng minh được quy tắc có chạy qua proxy? Có cả allow và deny cho meta-annotation, hierarchy và PermissionEvaluator? Dữ liệu test có tách biệt? Nếu đổi một quyền/role/id, test thất bại đúng như dự đoán? Chỉ khi trả lời được các câu đó thì bộ kiểm thử mới bảo vệ thay đổi phân quyền thực sự.

## 8. Tài liệu tham khảo

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Authorization Architecture / Hierarchical Roles: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — PermissionEvaluator API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html
