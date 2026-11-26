# Hợp đồng cho phép, từ chối và tác dụng phụ cần quan sát

## Mục tiêu học tập

Một bài kiểm thử phân quyền không hoàn chỉnh nếu chỉ khẳng định request nhận `200 OK` hoặc `403 Forbidden`. Với thao tác nhạy cảm như duyệt đơn hàng, ta còn phải chứng minh người có quyền thực hiện đúng hành động, người thiếu quyền bị từ chối, dữ liệu không bị thay đổi ngoài ý muốn và hệ thống bên ngoài không nhận lệnh trái phép.

Sau bài học này, bạn có thể:

- Mô tả chính sách dưới dạng hợp đồng **ai – hành động – tài nguyên – điều kiện – kết quả**.
- Thiết kế cặp kiểm thử cho phép và từ chối theo role, authority, scope, trạng thái tài nguyên và quyền sở hữu.
- Kiểm tra HTTP status, response body, headers và dữ liệu không được tiết lộ.
- Quan sát tác dụng phụ ở database, event/outbox, message broker và dịch vụ bên ngoài.
- Phân biệt tác dụng phụ nghiệp vụ cần bị ngăn với security audit event có thể được phép ghi lại.
- Dùng `MockMvc`, `WebTestClient`, `@WithMockUser` và JWT/OAuth2/OIDC mock để kiểm chứng hợp đồng trên Servlet và Reactive.

Bài này thuộc module **SPRING_SECURITY_TESTING**, nơi người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Hợp đồng bảo mật phải mô tả cả kết quả lẫn tác động

Giả sử ứng dụng quản lý đơn hàng có endpoint `POST /api/orders/{id}/approve`. Chỉ nhân viên có authority `orders:approve` mới được duyệt đơn đang ở trạng thái `PENDING_REVIEW`.

Nếu chỉ viết test rằng quản trị viên nhận `200`, ta chưa biết người dùng thường có thể gọi endpoint hay không. Nếu test người dùng thường nhận `403` nhưng đơn hàng vẫn chuyển trạng thái hoặc email xác nhận đã được gửi, hệ thống vẫn có lỗi nghiêm trọng.

Một hợp đồng bảo mật đầy đủ cần trả lời:

1. **Ai?** Người chưa xác thực, người dùng thường, người duyệt, quản trị viên hay service account?
2. **Làm gì?** Đọc, tạo, sửa, duyệt, hủy hay xuất dữ liệu?
3. **Trên tài nguyên nào?** Đơn hàng của mình, đơn của người khác, báo cáo quản trị hay tài nguyên đã bị khóa?
4. **Trong điều kiện nào?** Role/scope, trạng thái tài nguyên, tenant, chủ sở hữu, CSRF token hoặc trạng thái tài khoản?
5. **Kết quả quan sát được là gì?** HTTP status, response body, headers, thay đổi dữ liệu và các lời gọi ra ngoài?

| Thành phần | Ví dụ |
| --- | --- |
| Chủ thể (subject) | `linh` với `ROLE_USER` hoặc `mai` với `orders:approve`. |
| Hành động (action) | `approve`. |
| Tài nguyên (resource) | Đơn hàng `ORD-42` thuộc tenant `store-a`. |
| Điều kiện (condition) | Đơn đang `PENDING_REVIEW` và người duyệt thuộc đúng tenant. |
| Quyết định (decision) | Cho phép hoặc từ chối. |
| Kết quả HTTP | `200`, `401`, `403` hoặc mã được quy định trong API. |
| Tác động nghiệp vụ | Trạng thái đơn, bản ghi lịch sử, outbox event, lời gọi thanh toán/email. |

### 1.1. Ba lớp kết quả cần quan sát

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Quyết định bảo mật | Request được phép đi tiếp không? | User thiếu authority bị chặn. |
| Phản hồi giao thức | Client quan sát được điều gì? | Status, JSON error, WWW-Authenticate, correlation ID. |
| Tác động hệ thống | Điều gì đã thay đổi hoặc được kích hoạt? | Database update, message, email, payment request. |

Một request bị từ chối có thể có phản hồi đúng nhưng tác động hệ thống sai. Vì vậy, test phải quan sát đủ các lớp phù hợp với rủi ro.

### 1.2. Luồng xử lý và các điểm cần quan sát

~~~mermaid
flowchart TD
    R["HTTP request"] --> A["Authentication"]
    A -->|Không hợp lệ| X["401 / entry point"]
    A -->|Hợp lệ| Z["Authorization"]
    Z -->|Thiếu quyền| Y["403 / access denied"]
    Z -->|Được phép| V["Validate nghiệp vụ"]
    V -->|Không hợp lệ| B["4xx theo hợp đồng"]
    V -->|Hợp lệ| T["Transaction / service"]
    T --> D["Database state"]
    T --> O["Outbox / domain event"]
    O --> E["Consumer / email / downstream"]
    X --> OBS["Assert response + side effects"]
    Y --> OBS
    B --> OBS
    D --> OBS
    E --> OBS
~~~

Sơ đồ là mô hình khái niệm. Trong ứng dụng thực, filter, method interceptor, transaction boundary và event publisher có thể nằm ở các thành phần khác nhau. Test cần xác định tác dụng nào có thể xảy ra trước hoặc sau điểm từ chối.

## 2. Ma trận cho phép và từ chối

Với thao tác duyệt đơn hàng, hãy chuyển chính sách thành các trường hợp có thể kiểm tra:

| Chủ thể và điều kiện | Kỳ vọng | Vì sao |
| --- | --- | --- |
| Chưa đăng nhập | `401` hoặc redirect theo entry point | Chưa có danh tính được xác thực. |
| User đã đăng nhập, chỉ có `orders:read` | `403` | Có danh tính nhưng thiếu quyền duyệt. |
| Có `orders:approve`, đúng tenant, đơn đang chờ duyệt | Thành công | Đủ quyền và điều kiện tài nguyên. |
| Có quyền nhưng đơn thuộc tenant khác | `403` hoặc `404` theo chính sách | Không được thao tác ngoài phạm vi tenant. |
| Có quyền nhưng đơn đã được duyệt | `409 Conflict` hoặc lỗi nghiệp vụ quy định | Quyền không làm mất hiệu lực của quy tắc trạng thái. |
| Request POST thiếu CSRF token khi CSRF bật | `403` | Bị chặn ở lớp bảo vệ HTTP. |
| JWT không hợp lệ hoặc hết hạn | Thường `401` | Token không tạo được authentication hợp lệ. |

Không mặc định mọi ứng dụng phải dùng đúng các mã trên. Ví dụ, API có thể cố ý trả `404` để không tiết lộ tài nguyên có tồn tại hay không; form login có thể redirect; exception handler có thể chuẩn hóa lỗi theo hợp đồng riêng. Test phải khớp chính sách đã chọn.

### 2.1. Test từ chối phải chứng minh bị từ chối vì đúng lý do

Một test POST không có CSRF token có thể nhận `403` trước khi kiểm tra authority. Nếu mục tiêu là chứng minh user thiếu `orders:approve`, phải cung cấp CSRF token hợp lệ trong test đó.

Tương tự, nếu endpoint yêu cầu JWT scope, test dùng `jwt().authorities(...)` có thể bỏ qua converter. Muốn kiểm tra converter, cần test riêng mapping claim và thêm test tích hợp khi cần.

Quy tắc thực hành:

- Test xác thực: thay credential/token, giữ chính sách quyền ổn định.
- Test phân quyền: giữ authentication hợp lệ và các điều kiện khác hợp lệ, chỉ thay authority/role.
- Test CSRF: giữ danh tính và quyền, chỉ thay token CSRF.
- Test tenant/ownership: giữ danh tính và authority, thay tài nguyên hoặc chủ sở hữu.
- Test trạng thái nghiệp vụ: giữ quyền, thay trạng thái tài nguyên.

Khi mỗi test chỉ thay đổi một điều kiện trọng yếu, kết quả có nguyên nhân rõ ràng.

## 3. Hợp đồng thành công: không chỉ kiểm tra status 200

Khi request được phép, nên kiểm tra các đầu ra liên quan đến hành động:

- HTTP status và kiểu nội dung đúng, ví dụ `200 OK` hoặc `204 No Content` theo hợp đồng.
- Response chỉ trả các trường mà caller được phép xem.
- Trạng thái tài nguyên thay đổi chính xác một lần.
- Lịch sử/audit nghiệp vụ có actor và thời điểm đúng.
- Event hoặc outbox record được tạo theo thiết kế.
- Downstream call chỉ diễn ra khi hành động được commit hoặc đạt điều kiện đã định.
- Không phát sinh tác động trùng lặp ngoài dự kiến.

Ví dụ, API duyệt đơn trả JSON:

~~~json
{
  "orderId": "ORD-42",
  "status": "APPROVED",
  "approvedBy": "mai"
}
~~~

Test thành công không nên dừng ở `status().isOk()`. Cần kiểm tra body, database state và các sự kiện quan trọng.

### 3.1. Ví dụ kiểm tra response và trạng thái lưu

Giả sử có controller và service đã cấu hình security phù hợp, repository có thể đọc lại đơn hàng sau request. Ví dụ dưới đây tập trung vào assertion của hợp đồng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureMockMvc
class ApproveOrderContractTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderRepository orders;

    @Test
    @WithMockUser(username = "mai", authorities = "orders:approve")
    void approverChangesPendingOrderToApproved() throws Exception {
        orders.save(Order.pending("ORD-42", "store-a"));

        mvc.perform(post("/api/orders/ORD-42/approve")
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.orderId").value("ORD-42"))
            .andExpect(jsonPath("$.status").value("APPROVED"))
            .andExpect(jsonPath("$.approvedBy").value("mai"));

        assertThat(orders.findById("ORD-42").orElseThrow().getStatus())
            .isEqualTo(OrderStatus.APPROVED);
    }
}
~~~

Ví dụ giả định có các kiểu `Order`, `OrderRepository`, `OrderStatus`, factory `Order.pending(...)` và endpoint trả response như trên. Dự án thực tế cần thay bằng fixture, transaction và repository tương ứng.

Nếu test chạy trong transaction được rollback sau mỗi test, việc đọc repository trong cùng transaction vẫn có thể quan sát thay đổi chưa commit. Nếu hệ thống phát event sau commit, cần kiểm tra ở đúng ranh giới transaction hoặc dùng test phù hợp với cơ chế outbox.

## 4. Hợp đồng từ chối: kiểm tra không có tác dụng phụ nghiệp vụ

Khi user thiếu quyền, điều quan trọng không chỉ là trả `403` mà còn là:

- Trạng thái đơn hàng không đổi.
- Không tạo bản ghi duyệt hoặc lịch sử nghiệp vụ giả.
- Không phát domain event `OrderApproved`.
- Không gọi dịch vụ thanh toán, email hoặc downstream API.
- Không tăng số lần xử lý hoặc tiêu thụ quota theo logic chỉ dành cho thao tác thành công.
- Không trả dữ liệu nhạy cảm trong response.

Ví dụ test từ chối với user chỉ có quyền đọc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureMockMvc
class DeniedApprovalContractTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderRepository orders;

    @Test
    @WithMockUser(username = "linh", authorities = "orders:read")
    void readerCannotApproveAndOrderRemainsPending() throws Exception {
        orders.save(Order.pending("ORD-42", "store-a"));

        mvc.perform(post("/api/orders/ORD-42/approve")
                .with(csrf()))
            .andExpect(status().isForbidden());

        assertThat(orders.findById("ORD-42").orElseThrow().getStatus())
            .isEqualTo(OrderStatus.PENDING_REVIEW);
    }
}
~~~

CSRF token được cung cấp để test thực sự đi tới quy tắc phân quyền. Nếu bỏ `.with(csrf())`, test có thể vẫn nhận `403` nhưng chưa chứng minh authority đã được kiểm tra.

### 4.1. Không có side effect cũng phải được đo bằng bằng chứng

Để kiểm tra không có event hoặc lời gọi bên ngoài, có thể thay collaborator bằng mock/spy trong test context rồi xác minh không được gọi:

~~~java
verify(orderEventPublisher, never())
    .publish(any(OrderApproved.class));

verify(notificationClient, never())
    .sendApproval(any());
~~~

Các lời gọi trên là ví dụ Mockito. Trong Spring Boot phiên bản hỗ trợ, có thể dùng `@MockitoBean` để thay bean trong context; dự án cũ hơn có thể đang dùng `@MockBean`. Chọn API phù hợp với phiên bản dự án.

Với database, đọc lại trạng thái và số lượng bản ghi liên quan. Với message broker hoặc outbox, kiểm tra không có event nghiệp vụ được tạo. Không chỉ verify mock nếu ứng dụng có thể ghi side effect qua một đường khác.

### 4.2. Phân biệt business side effect và security audit

Một request bị từ chối có thể được ghi vào security audit log hoặc phát một sự kiện bảo mật như `AccessDeniedRecorded`. Đây có thể là hành vi mong muốn.

| Tác động khi bị từ chối | Kỳ vọng thường gặp |
| --- | --- |
| Cập nhật trạng thái đơn hàng | Không xảy ra. |
| Tạo lịch sử duyệt nghiệp vụ | Không xảy ra. |
| Gửi email xác nhận đơn được duyệt | Không xảy ra. |
| Gọi cổng thanh toán | Không xảy ra. |
| Ghi security audit về lần truy cập bị từ chối | Có thể xảy ra theo chính sách. |
| Tăng metric/đếm request bị từ chối | Có thể xảy ra. |
| Ghi log chẩn đoán không chứa secret | Có thể xảy ra. |

Không nên assert “không có bất kỳ event nào” nếu hệ thống được thiết kế để phát security audit event. Hãy phân biệt loại event và mục đích của nó.

## 5. Xác minh response error không làm lộ dữ liệu

Response từ chối cũng là một phần của hợp đồng bảo mật. Một lỗi `403` có thể vô tình trả về tên chủ tài nguyên, địa chỉ, thông tin thanh toán hoặc nội dung exception nội bộ.

Ví dụ response lỗi đã chuẩn hóa:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền thực hiện thao tác này",
  "traceId": "req-7f21"
}
~~~

Các assertion phù hợp:

- Status đúng theo hợp đồng.
- Content type là JSON nếu API chuẩn hóa lỗi JSON.
- Mã lỗi ổn định để client xử lý.
- Message không chứa stack trace, SQL, secret, token hoặc dữ liệu riêng của tài nguyên.
- Response không chứa những trường chỉ caller được phép xem.
- Có trace/correlation ID nếu hệ thống quy định.

Ví dụ:

~~~java
mvc.perform(post("/api/orders/ORD-42/approve")
        .with(csrf())
        .with(user("linh").authorities("orders:read")))
    .andExpect(status().isForbidden())
    .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
    .andExpect(jsonPath("$.debug").doesNotExist())
    .andExpect(jsonPath("$.paymentDetails").doesNotExist());
~~~

Nếu API chủ ý trả `404` để che sự tồn tại của tài nguyên ngoài tenant, hãy assert đúng mã đó và bảo đảm body không phân biệt được tài nguyên có tồn tại hay không theo mức thông tin mà chính sách cho phép.

## 6. Phân biệt lỗi bảo mật và lỗi nghiệp vụ

Một user có quyền vẫn có thể không thực hiện được hành động vì trạng thái tài nguyên không phù hợp. Đây không nhất thiết là lỗi phân quyền.

| Tình huống | Phân loại | Kết quả gợi ý |
| --- | --- | --- |
| Không có authentication | Lỗi xác thực | `401` hoặc redirect. |
| Đã xác thực nhưng thiếu `orders:approve` | Lỗi phân quyền | `403`. |
| Đúng quyền nhưng đơn đã bị hủy | Xung đột trạng thái nghiệp vụ | `409`. |
| Đúng quyền nhưng payload sai định dạng | Lỗi validation | `400` hoặc `422` theo hợp đồng. |
| Đơn không tồn tại | Không tìm thấy tài nguyên | `404`. |
| Đơn ở tenant khác | Chính sách cô lập dữ liệu | `403` hoặc `404` tùy thiết kế. |

Test nên tách riêng các điều kiện. Nếu một user thiếu quyền gửi payload sai định dạng, framework có thể trả lỗi validation trước hoặc sau bước authorization tùy kiến trúc. Muốn kiểm tra quyền, dùng payload hợp lệ và dữ liệu tài nguyên hợp lệ; muốn kiểm tra validation, dùng user đủ quyền để tránh quyền truy cập che mất lỗi cần quan sát.

## 7. Test theo tầng HTTP với MockMvc và WebTestClient

### 7.1. Servlet: kiểm tra allow/deny và response

Với Servlet, `MockMvc` gửi request qua Spring MVC và filter chain được tích hợp trong test context. Cặp test cho phép/từ chối nên dùng cùng endpoint, payload và fixture, chỉ thay danh tính hoặc quyền.

~~~java
@Test
@WithMockUser(username = "mai", authorities = "orders:approve")
void approverIsAllowed() throws Exception {
    mvc.perform(post("/api/orders/ORD-42/approve")
            .with(csrf()))
        .andExpect(status().isOk());
}

@Test
@WithMockUser(username = "linh", authorities = "orders:read")
void readerIsDenied() throws Exception {
    mvc.perform(post("/api/orders/ORD-42/approve")
            .with(csrf()))
        .andExpect(status().isForbidden());
}
~~~

Hai test này giả định order ở trạng thái có thể duyệt và endpoint có cấu hình CSRF mặc định. Nếu không có CSRF trong test từ chối, kết quả có thể không đến từ authority.

Có thể dùng `.with(jwt())` để thử scope giả lập hoặc `.with(opaqueToken())` cho principal opaque giả lập. Các helper này thiết lập authentication để kiểm tra downstream authorization; muốn kiểm tra chữ ký JWT hay introspection thực, hãy gửi bearer token qua header và để decoder/introspector thực thi.

### 7.2. Reactive: kiểm tra response và dữ liệu sau request

Với ứng dụng WebFlux, dùng `WebTestClient` gắn application context và áp dụng Spring Security configurer. Ví dụ:

~~~java
client.mutateWith(mockUser("mai").authorities(
        new SimpleGrantedAuthority("orders:approve")))
    .mutateWith(csrf())
    .post().uri("/api/orders/ORD-42/approve")
    .exchange()
    .expectStatus().isOk();

client.mutateWith(mockUser("linh").authorities(
        new SimpleGrantedAuthority("orders:read")))
    .mutateWith(csrf())
    .post().uri("/api/orders/ORD-42/approve")
    .exchange()
    .expectStatus().isForbidden();
~~~

Đây là ví dụ cho client mock server của WebFlux. Để xác minh tác dụng phụ, cần đọc lại repository/reactive store sau khi request hoàn tất hoặc kiểm tra publisher/event sink tương ứng.

### 7.3. Test trực tiếp service không thay thế test HTTP

Nếu gọi service trực tiếp với `@WithMockUser`, bạn có thể xác minh method security. Nhưng test đó không chứng minh:

- URL matcher bảo vệ đúng đường dẫn.
- CSRF được áp dụng đúng.
- Exception handler tạo response đúng.
- Controller không vô tình trả thêm trường nhạy cảm.
- Filter chain đã được gắn vào MockMvc/WebTestClient.

Do đó, service test và HTTP test bổ sung cho nhau. Dùng test service để cô lập quy tắc phương thức; dùng test HTTP để xác minh hợp đồng mà client bên ngoài quan sát được.

## 8. Tác dụng phụ trong transaction, event và hệ thống phân tán

Kiểm tra side effect cần tính đến transaction boundary và cách ứng dụng phát sự kiện.

### 8.1. Database transaction

Nếu kiểm tra quyền xảy ra trước khi service cập nhật dữ liệu, request bị từ chối phải giữ nguyên trạng thái. Nhưng nếu ứng dụng ghi dữ liệu trước rồi mới phát hiện lỗi, test chỉ kiểm tra status có thể bỏ sót lỗi.

Với thao tác nhạy cảm, hãy kiểm tra:

- Bản ghi chính có thay đổi không.
- Bảng lịch sử có thêm dòng không.
- Outbox có thêm event nghiệp vụ không.
- Số dư, quota hoặc bộ đếm có thay đổi không.
- Transaction rollback có thực sự hoàn tác mọi ghi nhận trong cùng transaction không.

Nếu test được chạy trong transaction riêng của framework test và rollback sau mỗi test, cần phân biệt rollback của **test transaction** với transaction của request. Với async processing hoặc request chạy ở thread/transaction khác, assertion phải quan sát đúng transaction boundary.

### 8.2. Domain event và outbox

Nhiều ứng dụng dùng event để thông báo đơn đã được duyệt. Một hợp đồng thành công có thể yêu cầu:

- Trạng thái đơn thành `APPROVED`.
- Một event `OrderApproved` được ghi vào outbox.
- Event chỉ được publish sau khi transaction commit hoặc được relay từ outbox.
- Event chứa actor và ID đơn hàng, không chứa secret hoặc dữ liệu không cần thiết.

Hợp đồng từ chối có thể yêu cầu không có `OrderApproved`. Nếu hệ thống phát security audit event, đó là loại event khác và có thể được phép.

### 8.3. Downstream call

Ví dụ duyệt đơn kích hoạt dịch vụ email hoặc thanh toán. Trong test, thay client bên ngoài bằng mock để kiểm tra lời gọi:

~~~java
verify(notificationClient, times(1))
    .sendApproval(eq("ORD-42"), eq("mai"));

verify(notificationClient, never())
    .sendApproval(eq("ORD-42"), eq("linh"));
~~~

Đây là assertion minh họa. Nếu hệ thống dùng message broker/outbox thay vì gọi trực tiếp, hãy kiểm tra event/outbox tương ứng; verify một mock client không thể chứng minh broker thật đã nhận hoặc xử lý message.

### 8.4. Retry và idempotency

Một request được phép có thể bị gửi lại do client retry hoặc mạng không ổn định. Hợp đồng cần nêu rõ việc lặp lại có tạo hai lần duyệt, hai email hay hai payment request không.

Test nên bao gồm:

- Hai request liên tiếp cùng idempotency key.
- Hai request đồng thời nếu thao tác có nguy cơ race condition.
- Trạng thái đơn đã được cập nhật sau lần đầu.
- Chỉ một event nghiệp vụ hoặc downstream action được tạo theo thiết kế.

Đối với request bị từ chối, retry không được tạo tác động nghiệp vụ về sau nếu quyền vẫn chưa được cấp.

## 9. Quyền theo tenant và chủ sở hữu: kiểm tra dữ liệu bị cô lập

Role giống nhau không có nghĩa người dùng nhìn thấy cùng dữ liệu. Ví dụ hai user đều có `ROLE_USER`, nhưng chỉ được truy cập đơn thuộc tenant hoặc sở hữu của mình.

| Caller | Tài nguyên | Kết quả |
| --- | --- | --- |
| `linh`, tenant A | Đơn tenant A do linh sở hữu | Cho phép nếu policy cho phép. |
| `linh`, tenant A | Đơn tenant A của mai | Từ chối nếu cần kiểm tra owner. |
| `linh`, tenant A | Đơn tenant B | Từ chối hoặc ẩn bằng 404 theo policy. |
| `mai`, tenant B | Đơn tenant B | Cho phép nếu đủ điều kiện. |

Khi test từ chối, kiểm tra cả:

- Response không trả dữ liệu đơn hàng ngoài phạm vi.
- Không thay đổi trạng thái hoặc tạo lịch sử.
- Không gọi downstream service cho đơn hàng đó.
- Không làm lộ sự tồn tại của tài nguyên nếu chính sách yêu cầu ẩn.

Một lỗi phổ biến là kiểm tra role ở URL nhưng truy vấn repository không ràng buộc tenant. Cặp test với hai tenant khác nhau có thể phát hiện lỗi mà test role đơn giản không tìm ra.

## 10. Bộ dữ liệu kiểm thử phải cô lập và có ý nghĩa

Một test contract dễ tin cậy khi fixture xác định rõ:

- User, authority, tenant và trạng thái tài khoản.
- Tài nguyên và chủ sở hữu.
- Trạng thái trước request.
- Payload hợp lệ.
- Event/outbox hoặc mock collaborator quan sát được.
- Kết quả kỳ vọng sau request.

Không dùng dữ liệu ngẫu nhiên khó tái hiện nếu không cần thiết. Nếu ID được sinh động, lưu lại giá trị trong test và dùng nhất quán ở request lẫn assertion.

Dùng dữ liệu riêng cho mỗi test hoặc dọn sạch giữa các test để test chạy độc lập. Với database dùng chung hoặc test song song, tránh giả định một bảng luôn rỗng; assert theo ID fixture cụ thể hoặc tạo namespace riêng.

## 11. Những lỗi khiến test bảo mật xanh giả

### 11.1. Chỉ assert 403

403 có thể đến từ CSRF, method security, URL matcher hoặc exception handler. Xác định điểm từ chối bằng cách giữ các điều kiện khác hợp lệ và kiểm tra side effect.

### 11.2. Không kiểm tra dữ liệu sau request bị từ chối

Status có thể đúng nhưng database đã thay đổi trước khi exception xảy ra. Đọc lại trạng thái, audit nghiệp vụ, outbox và các mock collaborator.

### 11.3. Chỉ verify mock downstream

Ứng dụng có thể có đường gọi khác không đi qua mock đó. Kết hợp verify collaborator với kiểm tra database/event/outbox nếu đó là các kênh tác động thực tế.

### 11.4. Nhầm security audit với event nghiệp vụ

Request bị từ chối có thể được ghi vào security log. Không assert rằng hệ thống tuyệt đối không ghi gì; hãy assert rằng không có tác động nghiệp vụ trái phép và audit event đúng chính sách.

### 11.5. Dùng user mock để kết luận token thật hợp lệ

`@WithMockUser`, `jwt()` và `mockJwt()` thiết lập danh tính giả lập. Chúng không xác minh password, chữ ký JWT, introspection hay OAuth2/OIDC protocol.

### 11.6. Không kiểm tra response body

Một lỗi `403` có thể trả dữ liệu nhạy cảm. Assert các trường được phép tồn tại và trường nhạy cảm không xuất hiện; kiểm tra không có stack trace hoặc secret.

### 11.7. Test dữ liệu sai trong khi muốn test quyền

Validation có thể làm request dừng trước hoặc sau bước authorization tùy thiết kế. Dùng payload hợp lệ khi kiểm tra quyền; dùng user đủ quyền khi kiểm tra validation.

## 12. Checklist thiết kế một security contract test

Trước khi viết test cho một endpoint nhạy cảm, trả lời các câu hỏi sau:

- Chủ thể là ai, đã xác thực chưa, có role/authority/scope nào?
- Hành động và tài nguyên cụ thể là gì?
- Điều kiện tenant, owner và trạng thái tài nguyên là gì?
- Điều kiện HTTP như CSRF hoặc content type có hợp lệ không?
- Ca cho phép phải trả status/body/header nào?
- Ca từ chối phải trả status/body/header nào?
- Khi thành công, database/event/downstream nào phải thay đổi?
- Khi bị từ chối, những tác động nghiệp vụ nào tuyệt đối không được xảy ra?
- Security audit/metric nào vẫn được phép ghi?
- Test đang dùng principal mock hay credential/token thật?
- Có cần test thêm ở tầng method hoặc component để xác định nguyên nhân không?

## 13. Bài thực hành tổng hợp

Xây dựng endpoint `POST /api/orders/{id}/approve` và hoàn thành các yêu cầu:

1. Tạo ma trận cho `anonymous`, `ROLE_USER`, authority `orders:approve` và người dùng thuộc tenant khác.
2. Viết test cho phép: approver duyệt đơn `PENDING_REVIEW`, nhận response thành công, trạng thái thành `APPROVED` và có đúng một event nghiệp vụ.
3. Viết test từ chối: user chỉ có `orders:read` nhận lỗi đúng hợp đồng; trạng thái đơn, lịch sử duyệt, outbox và downstream call không thay đổi.
4. Thêm test thiếu CSRF token và token hợp lệ để phân biệt lỗi CSRF với lỗi phân quyền.
5. Thêm test tài nguyên thuộc tenant khác; xác minh response không làm lộ dữ liệu và không tạo side effect.
6. Thử đơn đã bị hủy nhưng caller vẫn có quyền duyệt; phân biệt lỗi trạng thái nghiệp vụ với lỗi phân quyền.
7. Nếu dùng event hoặc email, mock/spy collaborator hoặc đọc outbox để kiểm tra số lần phát hành.
8. Viết một nhóm test tương đương bằng `WebTestClient` cho ứng dụng Reactive.
9. Ghi lại test nào dùng `@WithMockUser`/JWT mock và test nào gửi credential/token qua xác thực thật.

**Tiêu chí hoàn thành:** có ít nhất một ca được phép và một ca bị từ chối; cả hai kiểm tra response và trạng thái hệ thống; ca từ chối chứng minh không có tác động nghiệp vụ trái phép.

## 14. Ghi nhớ

Một security contract test tốt mô tả đầy đủ chủ thể, hành động, tài nguyên và điều kiện. Khi được phép, hệ thống phải trả phản hồi đúng và tạo đúng tác động nghiệp vụ. Khi bị từ chối, hệ thống phải trả lỗi theo hợp đồng, không tiết lộ dữ liệu và không thực hiện tác động nghiệp vụ trái phép.

Dùng `MockMvc` hoặc `WebTestClient` để quan sát hành vi HTTP; dùng `@WithMockUser`, JWT/OAuth2/OIDC mock để thiết lập danh tính khi kiểm tra phân quyền; kết hợp kiểm tra database, outbox, event và downstream calls để chứng minh tác động thực tế. Hãy phân biệt security audit event được phép ghi với event nghiệp vụ không được phát khi request bị từ chối.

Kết quả cần trả lời được hai điều: **request có được phép không, và hệ thống đã hoặc chưa làm gì vì request đó?**
