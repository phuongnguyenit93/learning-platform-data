# Test missing scope: Kiểm thử access token thiếu quyền

## 1. Mục tiêu của bài kiểm thử

Một access token có thể hợp lệ về chữ ký, issuer và thời hạn nhưng vẫn không đủ quyền để thực hiện một thao tác. Ví dụ, token cho phép đọc đơn hàng không mặc nhiên cho phép hủy đơn hàng. **Test missing scope** kiểm tra resource server có từ chối đúng yêu cầu khi token không chứa scope cần thiết, đồng thời vẫn cho phép các yêu cầu có đủ quyền.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài kiểm thử này nối các bước xác thực token với phân quyền ở API. Người học cần hiểu token được phát hành cho ai, bởi issuer nào, dùng ở audience nào, còn hiệu lực hay không, chứa scope gì và dịch vụ đích ánh xạ scope đó thành quyền thực thi ra sao. Phạm vi bài gồm JWT và opaque token, access token, OAuth 2.0/OIDC, API resource server và các tình huống token exchange có scope bị giới hạn.

Sau bài học, người học có thể:

- Phân biệt token không hợp lệ với token hợp lệ nhưng thiếu quyền.
- Xác định scope bắt buộc cho từng endpoint và HTTP method.
- Viết kiểm thử cho token thiếu scope, sai scope, đủ scope và scope bị giảm khi exchange.
- Kiểm tra cả HTTP status, response header theo hợp đồng API và việc không thực thi nghiệp vụ khi bị từ chối.
- Chọn đúng lớp kiểm thử để kiểm tra ánh xạ claim, xác minh token và quyết định phân quyền.

## 2. Scope nằm ở đâu trong quyết định bảo mật?

Scope mô tả phạm vi quyền mà authorization server cấp cho client/token trong một ngữ cảnh. Resource server sử dụng chính sách của mình để quyết định một scope có cho phép thao tác cụ thể hay không. Ví dụ:

| API | Scope yêu cầu | Hành động được phép |
| --- | --- | --- |
| **GET /orders/{id}** | **orders.read** | Đọc đơn hàng |
| **GET /orders** | **orders.read** | Liệt kê đơn hàng trong phạm vi dữ liệu được phép |
| **POST /orders** | **orders.write** | Tạo đơn hàng |
| **POST /orders/{id}/cancel** | **orders.cancel** | Hủy đơn hàng |
| **GET /admin/audit** | **audit.read** | Đọc dữ liệu audit dành cho vai trò được cấp quyền |

Tên scope chỉ là một phần của chính sách. Có **orders.read** không có nghĩa người dùng được đọc mọi đơn hàng: API còn có thể kiểm tra tenant, chủ sở hữu bản ghi, trạng thái nghiệp vụ hoặc thuộc tính khác. Scope cũng không tự động đồng nghĩa với role của người dùng. Role thường mô tả tư cách trong hệ thống; scope thường giới hạn quyền mà một client/token được cấp cho resource hoặc use case.

Một token có thể mang các claim khác nhau tùy issuer và loại token:

- JWT access token thường mang thông tin scope trong claim **scope** (chuỗi các giá trị phân tách bằng dấu cách) hoặc một claim như **scp** theo quy ước của nhà cung cấp.
- Opaque access token không cho resource server tự đọc claim từ token; server thường kiểm tra qua introspection hoặc cơ chế tra cứu đáng tin cậy khác. Phản hồi introspection có thể cung cấp **active**, **scope**, **client_id**, **sub**, **aud**, **exp** và các metadata tùy hỗ trợ.
- ID token phục vụ thông tin xác thực người dùng cho client OIDC; không dùng ID token thay access token để gọi resource API.

Không giả định mọi JWT đều dùng cùng tên claim hoặc mọi authorization server đều biểu diễn scope giống nhau. Resource server phải cấu hình rõ cách chuyển dữ liệu đã xác minh thành authority/permission nội bộ.

### 2.1 Phân biệt xác thực và phân quyền

| Tình huống | Câu hỏi | Kết quả HTTP thường dùng |
| --- | --- | --- |
| Không gửi access token | Request đã được xác thực chưa? | **401 Unauthorized** |
| Token sai chữ ký, hết hạn, sai issuer hoặc không dùng được | Token có hợp lệ cho resource server không? | **401 Unauthorized** |
| Token hợp lệ nhưng thiếu scope cần thiết | Chủ thể đã xác thực có quyền làm việc này không? | **403 Forbidden** |
| Token đủ scope nhưng không sở hữu tài nguyên | Chính sách truy cập dữ liệu có cho phép không? | **403 Forbidden** hoặc **404 Not Found** theo chính sách che giấu tài nguyên |
| Token hợp lệ và đủ scope, các điều kiện khác đều đạt | Có được thực hiện thao tác không? | Status thành công theo hợp đồng endpoint |

Với Bearer token, RFC 6750 mô tả lỗi **invalid_token** và **insufficient_scope**. Khi token hợp lệ nhưng không đủ quyền, resource server thường trả **403** và có thể cung cấp header:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.cancel"
Content-Type: application/json

{"error":"insufficient_scope"}
~~~

Header và body thực tế phụ thuộc giao thức, framework và hợp đồng API. Không nên trả thông tin policy nội bộ, danh sách quyền quản trị hoặc dữ liệu nhạy cảm chỉ để giải thích vì sao request bị từ chối. Nếu API cố ý che giấu sự tồn tại của tài nguyên bằng **404**, kiểm thử phải xác nhận đúng chính sách đã công bố.

Điểm cần nhớ: **401 thường nói rằng request chưa có thông tin xác thực hợp lệ; 403 thường nói rằng danh tính đã được xác thực nhưng không đủ quyền.** Đừng dùng một token hết hạn để kiểm tra missing scope vì khi đó request có thể bị dừng ở bước xác thực trước khi policy scope được đánh giá.

## 3. Xác định hợp đồng scope trước khi viết test

Trước tiên, lập bảng quyền cho từng endpoint. Ghi rõ scope nào là bắt buộc, scope có kết hợp theo AND hay OR, có scope thay thế hay không và các điều kiện dữ liệu nào được áp dụng thêm.

Ví dụ, API có chính sách:

- **GET /reports**: yêu cầu **reports.read**.
- **POST /reports**: yêu cầu **reports.write**.
- **POST /reports/{id}/publish**: yêu cầu đồng thời **reports.write** và **reports.publish**.
- **GET /profile**: chấp nhận một trong hai scope **profile.read** hoặc **profile.admin**.

Với hai scope cần đồng thời, token chỉ có một trong hai phải bị từ chối. Với hai scope thay thế, chỉ cần một scope được chấp nhận theo đúng policy. Đây là điểm dễ bị kiểm thử sai nếu người viết test chỉ nhìn tên scope mà không đọc hợp đồng phân quyền.

| Quy tắc | Token | Kết quả mong đợi |
| --- | --- | --- |
| Bắt buộc một scope | Có **reports.read** | Cho qua bước kiểm tra scope |
| Bắt buộc một scope | Chỉ có **reports.write** | Từ chối |
| Bắt buộc cả hai scope | Có **reports.write** và **reports.publish** | Cho qua bước kiểm tra scope |
| Bắt buộc cả hai scope | Chỉ có **reports.write** | Từ chối |
| Chấp nhận một trong hai | Có **profile.read** | Cho qua bước kiểm tra scope |
| Chấp nhận một trong hai | Có **profile.admin** | Cho qua bước kiểm tra scope |
| Chấp nhận một trong hai | Chỉ có **reports.read** | Từ chối |

"Cho qua bước kiểm tra scope" chưa đồng nghĩa request chắc chắn thành công. Các kiểm tra tenant, ownership, trạng thái tài nguyên, rate limit và quy tắc nghiệp vụ vẫn phải chạy.

## 4. Ma trận kiểm thử missing scope

Một bộ test cân bằng phải có trường hợp âm và trường hợp dương. Test âm chứng minh quyền thiếu bị từ chối; test dương chứng minh endpoint không bị khóa nhầm và mapping scope hoạt động đúng.

| ID | Token/request | Kết quả mong đợi | Điều cần xác minh |
| --- | --- | --- | --- |
| MS-01 | Không có token | **401** | Authentication bắt buộc |
| MS-02 | Token hết hạn hoặc chữ ký sai | **401** | Lỗi xác thực được phân loại đúng, không nhầm missing scope |
| MS-03 | Token hợp lệ, không có scope | **403** | Thiếu quyền bắt buộc |
| MS-04 | Token hợp lệ, chỉ có scope khác | **403** | Không cấp quyền theo scope gần giống |
| MS-05 | Token có đúng scope cần thiết | Cho qua authorization | Kiểm thử dương, nghiệp vụ trả kết quả theo fixture |
| MS-06 | Token có scope cần thiết và scope thừa | Cho qua nếu policy cho phép | Scope thừa không làm mất quyền hợp lệ |
| MS-07 | Policy yêu cầu A và B, token chỉ có A | **403** | Quy tắc AND được áp dụng |
| MS-08 | Policy chấp nhận A hoặc B, token có B | Cho qua authorization | Quy tắc OR được áp dụng |
| MS-09 | Token đúng scope nhưng sai audience | **401** hoặc lỗi xác thực theo hợp đồng | Scope không bù được audience sai |
| MS-10 | Token đúng scope nhưng subject không sở hữu tài nguyên | **403/404** theo policy | Scope không bỏ qua kiểm tra ownership |
| MS-11 | Token exchange chỉ được cấp scope hẹp hơn yêu cầu | API đích từ chối thao tác cần scope đã bị loại | **requested_scopes** và **granted_scopes** được phân biệt |
| MS-12 | Scope claim có định dạng không hợp lệ | Từ chối theo policy | Không tự suy diễn quyền từ dữ liệu lỗi |

Với mỗi trường hợp bị từ chối, xác minh thêm:

1. Controller/service nghiệp vụ không thực hiện thay đổi dữ liệu.
2. Không trả dữ liệu nhạy cảm trong response.
3. Audit/security event có thể ghi nhận decision và reason code an toàn theo thiết kế hệ thống.
4. Response không tiết lộ token, chữ ký, secret hoặc toàn bộ claim riêng tư.
5. Nếu API cam kết **WWW-Authenticate**, header có error phù hợp; nếu không cam kết thì không tạo assertion không có trong hợp đồng.

## 5. Ví dụ request để kiểm thử API

Giả sử endpoint **POST /orders/ORD-100/cancel** yêu cầu **orders.cancel**. Các giá trị token dưới đây chỉ là placeholder; không dùng token production trong test hoặc tài liệu.

**Case A — Token không có scope bắt buộc**

~~~http
POST /orders/ORD-100/cancel HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_WITHOUT_ORDERS_CANCEL>
Content-Type: application/json

{"reason":"duplicate"}
~~~

Kỳ vọng: request bị từ chối theo hợp đồng (**403** với Bearer **insufficient_scope** khi áp dụng RFC 6750); đơn hàng vẫn giữ nguyên trạng thái.

**Case B — Token chỉ có scope đọc**

~~~http
POST /orders/ORD-100/cancel HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_WITH_ORDERS_READ>
Content-Type: application/json

{"reason":"duplicate"}
~~~

Kỳ vọng: bị từ chối. **orders.read** không được tự động nâng thành **orders.cancel**.

**Case C — Token có đúng scope**

~~~http
POST /orders/ORD-100/cancel HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_WITH_ORDERS_CANCEL>
Content-Type: application/json

{"reason":"duplicate"}
~~~

Kỳ vọng: qua kiểm tra scope; kết quả cuối phụ thuộc token còn hiệu lực, audience đúng, subject có quyền với đơn hàng và quy tắc trạng thái đơn hàng.

Khi dùng **curl**, không bật chế độ verbose hoặc lưu header chứa token vào log dùng chung. Lấy token từ fixture test hoặc môi trường thử nghiệm có kiểm soát; không dán bearer token thật vào issue, chat, CI output hay ảnh chụp màn hình.

## 6. Kiểm thử theo từng lớp

### 6.1 Unit test cho policy

Unit test cô lập hàm quyết định quyền để xác minh logic AND/OR, ánh xạ scope và các trường hợp biên. Đầu vào nên là tập authority đã chuẩn hóa từ thành phần xác thực, không phải chuỗi JWT chưa kiểm tra.

Ví dụ logic minh họa:

~~~java
import java.util.Set;

final class OrderPolicy {
    boolean canCancel(Set<String> authorities) {
        return authorities.contains("SCOPE_orders.cancel");
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import org.junit.jupiter.api.Test;

class OrderPolicyTest {
    private final OrderPolicy policy = new OrderPolicy();

    @Test
    void deniesWhenCancelScopeIsMissing() {
        assertFalse(policy.canCancel(Set.of("SCOPE_orders.read")));
    }

    @Test
    void allowsWhenCancelScopeIsPresent() {
        assertTrue(policy.canCancel(Set.of("SCOPE_orders.cancel")));
    }

    @Test
    void doesNotInferCancelFromSimilarScopeName() {
        assertFalse(policy.canCancel(Set.of("SCOPE_orders.cancel.read")));
    }
}
~~~

Unit test này chỉ xác minh policy thuần. Nó không kiểm tra HTTP status, JWT signature, issuer, audience, expiry hoặc introspection.

### 6.2 HTTP integration test với Spring Security

Với Spring Security Resource Server, một endpoint có thể yêu cầu authority **SCOPE_orders.cancel**. Đoạn cấu hình minh họa:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/orders/*/cancel")
            .hasAuthority("SCOPE_orders.cancel")
        .requestMatchers(HttpMethod.GET, "/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2.jwt());
~~~

Ví dụ MockMvc kiểm tra authorization layer:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderAuthorizationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsAuthenticatedTokenWithoutCancelScope() throws Exception {
        mockMvc.perform(post("/orders/ORD-100/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowsTokenWithCancelScopePastAuthorizationFilter() throws Exception {
        mockMvc.perform(post("/orders/ORD-100/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isOk());
    }
}
~~~

Đây là ví dụ cần điều chỉnh theo controller, security configuration và status thực tế của ứng dụng. **jwt()** trong Spring Security Test tạo authentication giả cho request; nó **không kiểm tra chữ ký JWT, issuer, audience hay expiry như decoder production**. Test này phù hợp để xác minh quyền ở HTTP layer. Cần có test riêng cho JWT decoder và claim-to-authority converter.

Nếu endpoint trả **202**, **204** hoặc status nghiệp vụ khác, thay assertion cho đúng hợp đồng. Test cho phép cũng cần fixture và mock service phù hợp để chứng minh request đã đi qua policy, không phải do test vô tình bỏ qua security filter chain.

### 6.3 Kiểm thử ánh xạ claim JWT

Với JWT access token, kiểm tra ít nhất:

- Chữ ký được xác minh bằng key tin cậy và thuật toán được cho phép.
- **iss** khớp issuer tin cậy.
- **aud** chứa resource server đang nhận token.
- **exp** còn hiệu lực; kiểm tra **nbf** nếu có.
- Claim scope được đọc theo đúng định dạng mà issuer cam kết.
- Converter chỉ tạo authority từ token đã xác minh; không dùng dữ liệu từ JWT tự chế chưa qua decoder.

Một lỗi thường gặp là authorization policy đòi **SCOPE_orders.cancel** nhưng converter lại đọc **scp** trong khi issuer phát claim **scope**, hoặc ngược lại. Khi đó token có quyền nhưng API vẫn từ chối. Hãy kiểm thử converter bằng các JWT fixture có chữ ký test hợp lệ và claim đúng schema, đồng thời có fixture claim thiếu, sai kiểu hoặc sai issuer/audience. Không vô hiệu hóa kiểm tra chữ ký trong integration test chỉ để test chạy nhanh.

### 6.4 Kiểm thử opaque token và introspection

Với opaque token, resource server không tự parse JWT claims. Kiểm thử cần xác minh tương tác introspection và quyết định cuối:

| Phản hồi introspection giả lập | Kỳ vọng |
| --- | --- |
| **active: true**, scope có **orders.cancel**, audience hợp lệ | Qua bước scope |
| **active: true**, chỉ có **orders.read** | Bị từ chối thiếu scope |
| **active: false** | Không xác thực được token, thường là **401** |
| Introspection timeout/5xx | Xử lý theo fail-closed/fail-open policy đã phê duyệt; mặc định an toàn cho API nhạy cảm là không cấp quyền khi không xác minh được |
| **active: true**, thiếu hoặc sai audience | Từ chối theo validation policy |

Nếu resource server cache introspection response, cần test cả TTL và invalidation. Token bị thu hồi có thể vẫn được chấp nhận trong thời gian cache nếu hệ thống không có cơ chế cập nhật; đây là một rủi ro vòng đời token, không phải lỗi riêng của phép so sánh scope.

### 6.5 Kiểm thử end-to-end qua Authorization Server

Kiểm thử end-to-end dùng client/test user có quyền khác nhau để lấy token thật từ authorization server thử nghiệm. Xác nhận:

1. Client chỉ yêu cầu những scope được phép.
2. Authorization server trả đúng scope đã cấp; không mặc định **granted = requested**.
3. Resource server xác minh token và ánh xạ scope theo hợp đồng.
4. API từ chối thao tác vượt scope và cho phép thao tác nằm trong scope.
5. Token hết hạn/thu hồi được xử lý đúng theo thiết kế cache/introspection.

Đây là lớp kiểm thử giúp bắt lỗi cấu hình giữa issuer và resource server. Nó chậm hơn unit/integration test, nên nên chạy có chọn lọc trong pipeline hoặc bộ kiểm thử bảo mật chuyên biệt.

## 7. Kiểm thử scope khi dùng token exchange

Trong OAuth 2.0 Token Exchange, token mới có thể được cấp với phạm vi quyền hẹp hơn token nguồn hoặc scope client yêu cầu. Test phải phân biệt:

- **requested_scopes**: scope client yêu cầu.
- **granted_scopes**: scope authorization server thực sự cấp.
- Scope resource server kiểm tra trên token mới.

Ví dụ: **orders-api** yêu cầu đổi token để gọi **inventory-api**, với **inventory.read inventory.adjust**. Policy chỉ cho phép **inventory.read**. Nếu authorization server cấp token chỉ có **inventory.read**, API điều chỉnh tồn kho phải từ chối.

| Bước | Dữ liệu kiểm thử | Kết quả |
| --- | --- | --- |
| Token exchange request | **inventory.read inventory.adjust** | Ghi nhận scope yêu cầu |
| Policy STS | Chỉ cho phép **inventory.read** | Không cấp quyền điều chỉnh |
| Exchange response/token | **inventory.read** | Token mới có scope đã cấp |
| **GET /inventory** | Dùng token mới | Cho qua scope check |
| **POST /inventory/adjust** | Dùng cùng token mới | Từ chối thiếu **inventory.adjust** |

Không dùng token nguồn để suy ra token mới có cùng scope. Kiểm tra claims/metadata của token mới hoặc introspection tương ứng, đúng issuer và audience đích. Nếu authorization server từ chối exchange, kiểm tra response OAuth error và audit decision; không tiếp tục gọi resource API bằng token cũ như một fallback ngoài policy.

## 8. Kiểm tra side effect và dữ liệu trả về

Chỉ kiểm tra **403** là chưa đủ đối với endpoint thay đổi dữ liệu. Một lỗi có thể xảy ra khi controller thực hiện side effect trước khi kiểm tra quyền hoặc exception handler biến lỗi thành response khác. Với mỗi case thiếu scope, nên xác minh:

- Database record không đổi trạng thái.
- Không phát message/event nghiệp vụ.
- Không gọi dịch vụ downstream có đặc quyền.
- Không tạo file, thanh toán, tác vụ nền hoặc notification.
- Response không chứa dữ liệu của tài nguyên bị cấm truy cập.

Ví dụ test hủy đơn hàng cần kiểm tra trạng thái vẫn là **PENDING**, service **cancelOrder** không được gọi và không có event **OrderCancelled** được publish khi token thiếu scope. Dùng spy/mock ở test phù hợp hoặc đọc lại trạng thái trong integration test với database test.

Không nên chỉ kiểm tra số lần gọi controller: controller có thể được gọi trước khi security filter từ chối hoặc policy được đánh giá ở method security. Chọn điểm quan sát đúng với kiến trúc thực tế.

## 9. Các lỗi kiểm thử thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Dùng token hết hạn để test missing scope | Test dừng ở authentication, không đi tới authorization | Dùng token hợp lệ nhưng thiếu scope |
| Chỉ test **403**, không test token đủ scope | API có thể từ chối tất cả request | Bổ sung positive control |
| Mock trực tiếp authority và kết luận JWT mapping đúng | Bỏ qua claim converter/decoder | Test converter và JWT validation riêng |
| Giả định mọi issuer đều dùng claim **scope** | Token hợp lệ có thể bị ánh xạ sai | Khóa hợp đồng issuer/claim mapping |
| Chỉ test scope, bỏ qua audience | Token dành cho API khác có thể bị chấp nhận | Thêm case audience sai |
| Dùng chuỗi gần giống như **orders.cancelled** | Có thể phát hiện lỗi so khớp prefix/substring | Test exact authority, không dùng contains trên chuỗi chưa tokenize |
| Không test AND/OR | Chính sách nhiều scope dễ bị triển khai sai | Viết case thiếu từng scope và case đủ tập quyền |
| Không kiểm tra side effect | Dữ liệu có thể bị thay đổi dù response là lỗi | Kiểm tra database, event và downstream call |
| Dùng token production trong CI | Có nguy cơ lộ credential và khó tái lập | Dùng issuer/test key và fixture riêng |
| Bỏ qua cache introspection | Token thu hồi vẫn có thể được chấp nhận | Test TTL, cache miss, timeout và invalidation |
| Cho phép request khi introspection lỗi mà không có policy | Có thể biến lỗi hạ tầng thành cấp quyền | Quy định rõ fail behavior; không cấp quyền khi chưa xác minh trong luồng nhạy cảm |

## 10. Ví dụ kế hoạch kiểm thử cho một endpoint

Giả sử **POST /payments/{id}/refund** yêu cầu **payments.refund**. Kế hoạch tối thiểu:

| Test | Authentication | Scope | Audience | Ownership | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| Refund success | Hợp lệ | Có **payments.refund** | **payments-api** | Chủ sở hữu hợp lệ | Cho phép theo business rule |
| Missing scope | Hợp lệ | Chỉ **payments.read** | **payments-api** | Hợp lệ | **403**, không refund |
| No scope | Hợp lệ | Không có | **payments-api** | Hợp lệ | **403**, không refund |
| Expired token | Không hợp lệ | Có **payments.refund** | **payments-api** | Hợp lệ | **401**, không refund |
| Wrong audience | Chữ ký hợp lệ | Có **payments.refund** | **orders-api** | Hợp lệ | Từ chối xác thực/audience |
| Wrong owner | Hợp lệ | Có **payments.refund** | **payments-api** | Không hợp lệ | **403** hoặc **404**, không refund |
| Introspection unavailable | Không thể xác minh | Không kết luận | Chưa xác minh | Hợp lệ | Theo policy; không cấp quyền khi chưa xác minh |

Khi test fail, báo cáo nên nêu endpoint/method, loại token fixture, scope expected/actual, issuer/audience fixture, status/header thực tế, side effect đã quan sát và correlation ID. Không đính kèm raw token hoặc secret.

## 11. Checklist hoàn tất

- [ ] Đã xác định scope bắt buộc cho từng endpoint và HTTP method.
- [ ] Đã mô tả rõ scope kết hợp AND/OR và scope thay thế.
- [ ] Có test token hợp lệ nhưng không có scope.
- [ ] Có test token chỉ mang scope khác hoặc gần giống.
- [ ] Có positive control với scope chính xác.
- [ ] Phân biệt **401 invalid_token** với **403 insufficient_scope** theo hợp đồng API.
- [ ] Kiểm tra audience, issuer, expiry và chữ ký ở lớp phù hợp.
- [ ] Kiểm tra mapping claim JWT hoặc introspection của opaque token.
- [ ] Kiểm tra scope được cấp sau token exchange, không suy ra từ token nguồn.
- [ ] Xác minh request bị từ chối không tạo side effect hoặc gọi downstream đặc quyền.
- [ ] Không dùng token/secret production trong test, log hoặc CI artifact.
- [ ] Đã kiểm thử cache, timeout và lỗi introspection nếu hệ thống dùng opaque token.

## Tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** định nghĩa scope trong request/response OAuth.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** cách sử dụng Bearer token và lỗi **invalid_token**, **insufficient_scope**.
- **RFC 7662 — OAuth 2.0 Token Introspection:** endpoint introspection và metadata như **active**/**scope**.
- **RFC 8693 — OAuth 2.0 Token Exchange:** trao đổi token và phạm vi quyền của token được cấp.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** profile JWT access token và các claim liên quan.
- **Spring Security Reference — OAuth 2.0 Resource Server / Testing:** cấu hình resource server và hỗ trợ test JWT authentication trong MockMvc.

Một bài kiểm thử missing scope đáng tin cậy chứng minh được cả hai phía: token thiếu quyền bị từ chối trước khi nghiệp vụ tạo side effect, còn token có đúng quyền vẫn đi qua authorization khi các điều kiện khác hợp lệ. Điều đó giúp phát hiện lỗi cấu hình scope, sai ánh xạ claim và nguy cơ cấp quyền vượt quá phạm vi dự định.
