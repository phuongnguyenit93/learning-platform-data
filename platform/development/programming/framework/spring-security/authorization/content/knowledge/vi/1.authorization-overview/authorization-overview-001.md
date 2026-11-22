# Phân quyền: Ai được làm gì trên tài nguyên nào?

Trong ứng dụng, **phân quyền (authorization)** trả lời một câu hỏi nghiệp vụ: **chủ thể nào được thực hiện hành động nào trên tài nguyên cụ thể nào, trong điều kiện nào?** Đây là điểm xuất phát để thiết kế chính sách bảo mật của Spring Security, trước khi chọn annotation hay viết cấu hình HTTP.

Sau bài này, bạn có thể tách bạch xác thực và phân quyền, diễn đạt một quy tắc truy cập bằng dữ liệu nghiệp vụ, phân biệt kiểm tra ở URL với kiểm tra trên từng tài nguyên, và xây dựng các tình huống kiểm thử cho quyết định cho phép/từ chối.

## 1. Bốn thành phần của một quyết định phân quyền

Có thể hình dung một quyết định là:

~~~text
canAccess(subject, action, resource, context) -> ALLOW hoặc DENY
~~~

| Thành phần | Câu hỏi | Ví dụ trong hệ thống đơn hàng |
| --- | --- | --- |
| **Subject (chủ thể)** | Ai đang yêu cầu? | Người dùng `alice`, đã đăng nhập, thuộc cửa hàng `shop-a`, có quyền `ORDER_READ_OWN`. |
| **Action (hành động)** | Người đó muốn làm gì? | Xem đơn, hủy đơn, hoàn tiền, xuất báo cáo; không nhất thiết chỉ là GET/POST/PUT/DELETE. |
| **Resource (tài nguyên)** | Hành động nhắm vào đối tượng nào? | Đơn hàng số 42, chủ sở hữu `alice`, thuộc `shop-a`. |
| **Context (bối cảnh)** | Những điều kiện nào phải đúng? | Cùng cửa hàng/tenant, trạng thái đơn còn cho phép hủy, chính sách đang có hiệu lực. |

Ví dụ, câu “người dùng đã đăng nhập được vào `/api/orders/42`” mới trả lời một phần. Để **xem đơn 42**, hệ thống vẫn cần biết người gọi có quyền đọc đơn, đơn có thuộc cửa hàng họ được phép truy cập hay không, và quan hệ của họ với đơn đó. Với **hủy đơn 42**, còn phải kiểm tra trạng thái cho phép hủy.

Một nguyên tắc hữu ích: **đăng nhập thành công không suy ra được quyền trên mọi dữ liệu**; mã định danh tài nguyên trong URL cũng không chứng minh quyền sở hữu.

## 2. Xác thực khác phân quyền như thế nào?

- **Authentication (xác thực):** kiểm tra danh tính và thiết lập thông tin người gọi. Ví dụ: token hợp lệ cho biết yêu cầu đến từ tài khoản `alice`.
- **Authorization (phân quyền):** dựa vào danh tính đã biết cùng với chính sách để quyết định một hành động cụ thể có được phép hay không. Ví dụ: `alice` chỉ được xem đơn của mình trong đúng cửa hàng.
- **Hiển thị trên giao diện:** ẩn nút “Hủy” cho người không có quyền giúp trải nghiệm rõ ràng, nhưng **không thể thay thế kiểm tra ở máy chủ**. API có thể được gọi trực tiếp mà không qua giao diện.

Kết quả truy cập thường có hai nhánh. Nếu không xác thực mà endpoint yêu cầu đăng nhập, REST API thường trả **401 Unauthorized**; nếu đã xác thực nhưng không đủ quyền, thường trả **403 Forbidden**. Cơ chế đăng nhập bằng biểu mẫu, entry point và handler tùy chỉnh có thể chuyển hướng hoặc trả phản hồi khác. Vì vậy đừng coi mã HTTP là chính sách; mã HTTP chỉ thể hiện kết quả xử lý từ chối.

## 3. Từ câu nghiệp vụ thành chính sách kiểm tra được

Giả sử hệ thống quản lý đơn hàng đa cửa hàng (**multi-tenant**). Ta chọn chính sách ví dụ:

1. Mọi thao tác trên đơn đều đòi hỏi **đã xác thực** và **cùng tenant** với đơn.
2. Quyền `ORDER_READ_OWN` cho phép đọc **đơn do chính người gọi sở hữu**. Quyền `ORDER_READ_ALL` cho phép đọc các đơn trong tenant của người gọi.
3. Quyền `ORDER_CANCEL_OWN` cho phép hủy đơn của mình; `ORDER_CANCEL_ALL` cho phép hủy đơn trong tenant. **Cả hai vẫn đòi hỏi trạng thái đơn cho phép hủy**.
4. Nếu bất kỳ điều kiện bắt buộc nào không đạt, **từ chối**. Không có quy tắc khớp cũng phải từ chối theo nguyên tắc *deny by default*.

Bảng quyết định minh họa:

| Người gọi / thao tác | Đơn được yêu cầu | Quyết định | Lý do |
| --- | --- | --- | --- |
| Alice có `ORDER_READ_OWN` muốn đọc | Đơn của Alice trong `shop-a` | ALLOW | Đúng quyền, đúng chủ sở hữu và tenant. |
| Alice có `ORDER_READ_OWN` muốn đọc | Đơn của Bob trong `shop-a` | DENY | Không phải chủ sở hữu, không có quyền đọc mọi đơn. |
| Nhân viên hỗ trợ có `ORDER_READ_ALL` muốn đọc | Đơn của Alice trong `shop-a` | ALLOW | Có quyền đọc trong tenant. |
| Nhân viên hỗ trợ chỉ có `ORDER_READ_ALL` muốn hủy | Đơn của Alice trong `shop-a` | DENY | Quyền đọc không đồng nghĩa quyền hủy. |
| Nhân viên hỗ trợ có `ORDER_READ_ALL` muốn đọc | Đơn trong `shop-b` | DENY | Khác tenant, dù có quyền đọc tất cả trong tenant của mình. |
| Alice có `ORDER_CANCEL_OWN` muốn hủy | Đơn của Alice đã xử lý | DENY | Đúng chủ sở hữu nhưng trạng thái không cho phép. |

Chú ý sự khác nhau giữa **quyền chung** và **điều kiện trên đối tượng**. `ORDER_READ_ALL` không có nghĩa “mọi đơn ở mọi tenant”. Một quyền rộng vẫn có thể bị giới hạn bởi tổ chức, phạm vi dữ liệu, trạng thái hoặc ràng buộc pháp lý. Tenant và danh tính cần lấy từ ngữ cảnh xác thực đáng tin cậy hoặc dữ liệu máy chủ đã kiểm chứng, không chấp nhận một ID tùy ý do client gửi rồi xem đó là bằng chứng có quyền.

## 4. Role, authority, ownership và các mô hình chính sách

**RBAC (Role-Based Access Control)** gán quyền qua vai trò, như `CUSTOMER`, `SUPPORT`, `ADMIN`. Phù hợp để trả lời “nhóm người dùng nào được vào chức năng nào?”, nhưng một mình vai trò không biết đơn hàng thuộc ai.

**ABAC (Attribute-Based Access Control)** quyết định theo thuộc tính của chủ thể, tài nguyên và ngữ cảnh, như `actor.tenantId == order.tenantId` hoặc `order.cancellable == true`. Phù hợp cho quy tắc động theo trạng thái, tổ chức và thời điểm.

**ReBAC (Relationship-Based Access Control)** dựa vào quan hệ giữa chủ thể và tài nguyên, chẳng hạn “người tạo”, “người được chia sẻ”, “thành viên dự án”. Kiểm tra `actor.id == order.ownerId` là một quan hệ sở hữu đơn giản.

Các mô hình này **có thể phối hợp**. Ví dụ: người dùng cần quyền `ORDER_CANCEL_OWN` (**permission**), đúng chủ sở hữu (**relationship**), cùng tenant và đơn chưa xử lý (**attributes**). Một quy tắc tốt thường là phép **AND** của các điều kiện bắt buộc, kết hợp **OR** giữa các con đường được phép rõ ràng, tránh vô tình cho phép vì thiếu một kiểm tra.

Trong Spring Security, thông tin `Authentication` chứa `GrantedAuthority`. Một authority thường là chuỗi chỉ quyền hoặc vai trò mà hệ thống đã gán. Với cấu hình mặc định, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`; còn `hasAuthority("ORDER_READ_ALL")` so khớp chính xác chuỗi đó. Đừng nhầm tên role trong mã với giá trị authority thực tế trong `Authentication`.

**Authority không tự động thay thế việc truy vấn đối tượng.** Chẳng hạn, lưu hàng chục nghìn ID đơn hàng thành authority riêng trên mỗi người dùng thường không phải cách thích hợp để bảo vệ từng đơn. Kiểm tra tenant, ownership và trạng thái ở lớp nghiệp vụ bằng dữ liệu hiện hành thường rõ ràng hơn.

## 5. Kiểm tra ở đâu trong một ứng dụng Spring Security?

Có ba lớp trách nhiệm bổ sung cho nhau:

| Lớp kiểm tra | Biết được gì? | Chịu trách nhiệm chính |
| --- | --- | --- |
| **HTTP/request** | Đường dẫn, HTTP method và thông tin xác thực | Chặn endpoint công khai/nội bộ, yêu cầu đăng nhập hoặc quyền tổng quát. |
| **Method/service** | Thao tác nghiệp vụ, tham số gọi hàm, người dùng hiện tại | Chặn lời gọi nghiệp vụ không được phép, kể cả khi dịch vụ có nhiều đường đi vào. |
| **Domain/resource** | Đối tượng thực tế trong cơ sở dữ liệu: owner, tenant, trạng thái | Quyết định trên **từng bản ghi hoặc nhóm bản ghi**; bảo vệ khỏi truy cập nhầm đối tượng. |

Ví dụ cấu hình **Spring Boot 3 / Spring Security 6 với Java 17+** cho tầng HTTP:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Đây là **đoạn cấu hình để đặt trong dự án Spring Boot có dependency Spring Security**, không phải file biên dịch độc lập bằng `javac`. Quy tắc cụ thể đứng trước, `anyRequest().denyAll()` làm chốt chặn cuối. Với `authorizeHttpRequests`, Spring Security xét các request matcher theo thứ tự và dùng **quy tắc khớp đầu tiên**. `permitAll` chỉ nên áp dụng cho endpoint thực sự công khai.

Điểm then chốt: `.requestMatchers("/api/orders/**").authenticated()` **chỉ đảm bảo có đăng nhập**, chưa đảm bảo người đó sở hữu đơn hoặc thuộc đúng tenant. Sau khi tải đơn từ cơ sở dữ liệu, service vẫn phải dùng chính sách nghiệp vụ để quyết định `READ` hay `CANCEL`. Tránh suy ra quyền từ ID trên URL hay từ việc người dùng truy cập được controller.

Annotation `@EnableMethodSecurity` bật các cơ chế như `@PreAuthorize` cho phương thức trong bean do Spring quản lý. Ví dụ `@PreAuthorize("hasAuthority('ORDER_READ_ALL')")` chỉ kiểm tra authority; nếu phương thức trả danh sách đơn, bản thân nó vẫn cần giới hạn truy vấn theo tenant. Với đối tượng cụ thể, có thể ủy quyền cho một policy bean kiểm tra ID tài nguyên và `Authentication`, hoặc kiểm tra tường minh trong service sau khi tải đối tượng. Lưu ý method security dựa trên Spring AOP proxy: lời gọi nội bộ từ một phương thức sang phương thức khác trên chính cùng instance có thể không đi qua interceptor.

Trên servlet stack, `AuthorizationFilter` và `AuthorizationManager` giúp kiểm tra quyền ở mức HTTP; `ExceptionTranslationFilter` tham gia chuyển ngoại lệ bảo mật thành phản hồi thích hợp. Trong thiết kế nghiệp vụ, ta quan tâm trước hết tới **điều kiện cho phép hay từ chối**, rồi mới lựa chọn vị trí/hook Spring Security để thực thi.

## 6. Ví dụ Java 17 chạy độc lập: quyết định trên một đơn hàng

Chương trình sau cố ý **không dùng Spring** để làm rõ chính sách cốt lõi. `Principal` đại diện thông tin người gọi đã được xác minh; `Order` là dữ liệu tài nguyên. Khi tích hợp thật, những giá trị này phải đến từ hệ thống xác thực và dữ liệu máy chủ, không tự gán từ request của client.

Lưu chương trình thành **AuthorizationDecisionDemo.java**:

~~~java
import java.util.Set;

public class AuthorizationDecisionDemo {
    enum Action { READ, CANCEL }

    record Principal(String userId, String tenantId,
                     Set<String> authorities, boolean authenticated) {}

    record Order(String ownerId, String tenantId, boolean cancellable) {}

    static boolean allowed(Principal actor, Action action, Order order) {
        if (actor == null || !actor.authenticated()
                || !actor.tenantId().equals(order.tenantId())) {
            return false;
        }
        return switch (action) {
            case READ -> actor.authorities().contains("ORDER_READ_ALL")
                    || (actor.authorities().contains("ORDER_READ_OWN")
                        && actor.userId().equals(order.ownerId()));
            case CANCEL -> order.cancellable()
                    && (actor.authorities().contains("ORDER_CANCEL_ALL")
                        || (actor.authorities().contains("ORDER_CANCEL_OWN")
                            && actor.userId().equals(order.ownerId())));
        };
    }

    public static void main(String[] args) {
        Principal alice = new Principal("alice", "shop-a",
                Set.of("ORDER_READ_OWN", "ORDER_CANCEL_OWN"), true);
        Principal support = new Principal("sue", "shop-a",
                Set.of("ORDER_READ_ALL"), true);
        Principal anonymous = new Principal("guest", "shop-a",
                Set.of("ORDER_READ_ALL"), false);
        Order ownNew = new Order("alice", "shop-a", true);
        Order ownProcessed = new Order("alice", "shop-a", false);
        Order otherTenant = new Order("bob", "shop-b", true);

        System.out.println("Alice reads own order: "
                + allowed(alice, Action.READ, ownNew));
        System.out.println("Alice cancels processed order: "
                + allowed(alice, Action.CANCEL, ownProcessed));
        System.out.println("Support reads same-tenant order: "
                + allowed(support, Action.READ, ownNew));
        System.out.println("Support cancels without permission: "
                + allowed(support, Action.CANCEL, ownNew));
        System.out.println("Cross-tenant read: "
                + allowed(support, Action.READ, otherTenant));
        System.out.println("Unauthenticated read: "
                + allowed(anonymous, Action.READ, ownNew));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
~~~

Kết quả chuẩn:

~~~text
Alice reads own order: true
Alice cancels processed order: false
Support reads same-tenant order: true
Support cancels without permission: false
Cross-tenant read: false
Unauthenticated read: false
~~~

Đọc kỹ hai điều kiện đầu của `allowed`: chưa xác thực hoặc khác tenant thì **DENY trước khi xét từng hành động**. Nhánh `READ` cho phép hai con đường cụ thể: có quyền đọc tất cả trong tenant, hoặc có quyền đọc của mình *và* thật sự là chủ đơn. Nhánh `CANCEL` bổ sung điều kiện trạng thái. Quy tắc này mô phỏng chính sách mẫu; hệ thống thực tế còn có thể cần trạng thái khóa tài khoản, phân quyền chi nhánh, giới hạn thời gian, quy định về hoàn tiền, v.v.

## 7. Thiết kế kiểm thử theo quyết định, không chỉ theo endpoint

Khi viết yêu cầu bảo mật, hãy lập bảng gồm **chủ thể + quyền + hành động + tài nguyên + bối cảnh + kết quả mong đợi**. Ít nhất cần thử:

| Tình huống | Kỳ vọng |
| --- | --- |
| Chưa xác thực gọi API bảo vệ | Bị từ chối; REST API thông thường trả 401. |
| Đã xác thực nhưng thiếu authority | DENY; REST API thông thường trả 403. |
| Có `READ_OWN`, xem đúng đơn của mình | ALLOW nếu các điều kiện khác hợp lệ. |
| Có `READ_OWN`, đổi ID sang đơn của người khác | DENY, kể cả khi endpoint giống hệt. |
| Có `READ_ALL`, truy cập đơn tenant khác | DENY. |
| Có quyền hủy nhưng đơn không còn được hủy | DENY. |
| Có quyền đúng, cùng tenant, trạng thái phù hợp | ALLOW. |
| Gọi cùng service từ controller khác hoặc luồng nội bộ | Chính sách nghiệp vụ vẫn được áp dụng. |

Trong Spring Boot, có thể kết hợp test HTTP bằng MockMvc và test policy/service với dữ liệu đơn thật hoặc fixture. Đừng chỉ kiểm tra mã 200 của người có quyền; **các ca âm** (đặc biệt đổi ID, đổi tenant, đổi trạng thái) mới phát hiện được nhiều lỗi truy cập đối tượng.

Lỗi nghiêm trọng thường gặp là **IDOR/BOLA**: API cho phép người dùng thay một ID trong đường dẫn để đọc hoặc sửa tài nguyên của người khác. Ví dụ `GET /api/orders/42` và `GET /api/orders/43` đều vượt qua `authenticated()`, nhưng chỉ một đơn thuộc người gọi. Cần kiểm tra quyền trên **đúng đối tượng được tải lên**; với API liệt kê, cần giới hạn truy vấn ngay từ đầu để không trả dữ liệu ngoài phạm vi.

## 8. Các lỗi tư duy phổ biến và cách phòng tránh

1. **“Đã đăng nhập là được.”** Xác thực chỉ xác định người gọi; luôn gắn hành động với đối tượng và điều kiện tương ứng.
2. **“Có role ADMIN là bỏ qua mọi giới hạn.”** Chỉ tạo ngoại lệ khi yêu cầu nghiệp vụ cho phép rõ ràng; các giới hạn tenant, trạng thái và quy định khác có thể vẫn bắt buộc.
3. **“Ẩn nút trên UI là đủ.”** Luôn kiểm tra ở máy chủ, bất kể request đến từ trình duyệt, mobile, script hay một entry point khác.
4. **“Kiểm tra URL là đủ.”** Quy tắc HTTP không nắm hết owner, tenant, trạng thái bản ghi; phối hợp service/domain policy.
5. **“Client gửi tenantId/ownerId nên tin được.”** Dùng danh tính/tenant đã xác minh và kiểm tra quan hệ với dữ liệu server. Không đồng nhất dữ liệu đầu vào với quyền được cấp.
6. **“Không tìm thấy quy tắc cấm thì cho phép.”** Ưu tiên **deny by default** và quyền tối thiểu (*least privilege*); đặt quy tắc rộng thật cẩn thận.
7. **“Một kiểm tra trong controller sẽ bảo vệ mọi nơi.”** Tái sử dụng chính sách ở tầng nghiệp vụ khi cùng thao tác có nhiều entry point. Chú ý giới hạn proxy nếu dựa vào method security.
8. **“Test happy path là xong.”** Kiểm thử thiếu quyền, khác chủ, khác tenant, trạng thái biên và thay đổi quyền trong thời gian chạy. Cân nhắc audit quyết định từ chối mà không ghi token hay dữ liệu nhạy cảm vào log.

## 9. Cách chuyển một yêu cầu mới thành chính sách

Khi nhận câu “nhân viên được sửa đơn”, hãy làm rõ lần lượt:

1. **Ai:** mọi nhân viên, chỉ nhân viên thuộc cửa hàng hay chỉ người được giao đơn?
2. **Làm gì:** sửa địa chỉ giao hàng, thay giá, hủy, hoàn tiền có phải các quyền khác nhau?
3. **Tài nguyên nào:** mọi đơn trong tenant, đơn của nhóm, hay chỉ đơn được giao?
4. **Khi nào:** chỉ trước khi giao, giới hạn giá trị, cần phê duyệt thêm?
5. **Quyết định và kiểm chứng:** viết rõ điều kiện ALLOW, các trường hợp DENY, áp dụng trong service và tạo test cho mỗi nhánh.

Ví dụ, thay câu mơ hồ bằng: “Nhân viên có `ORDER_EDIT_ADDRESS` được đổi địa chỉ của đơn trong tenant mình, chỉ khi đơn chưa bàn giao vận chuyển”. Quy tắc có thể kiểm thử là:

~~~text
ALLOW khi:
  authenticated
  AND hasAuthority(ORDER_EDIT_ADDRESS)
  AND actor.tenantId == order.tenantId
  AND order.shippingStatus == NOT_HANDED_OVER
DENY trong mọi trường hợp còn lại
~~~

**Điểm cần nhớ:** Phân quyền không chỉ là “user có role gì”. Câu trả lời đầy đủ là **ai + hành động + tài nguyên cụ thể + bối cảnh + quy tắc được thực thi nhất quán ở máy chủ**. Spring Security cung cấp cơ chế để thực thi; chính sách ALLOW/DENY trước hết phải được xác định rõ từ nghiệp vụ.

### Tài liệu đối chiếu

- [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
