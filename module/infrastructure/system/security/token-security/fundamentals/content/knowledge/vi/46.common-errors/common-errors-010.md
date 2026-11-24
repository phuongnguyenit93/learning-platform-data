# Scope quá rộng: Nhận diện và khắc phục cấp quyền vượt nhu cầu

## 1. Mục tiêu và phạm vi

Một access token có thể hợp lệ về chữ ký, issuer, audience và thời hạn nhưng vẫn mang nhiều quyền hơn mức ứng dụng cần. Ví dụ, một dịch vụ chỉ cần đọc tồn kho lại được cấp cả quyền điều chỉnh và xóa tồn kho. Khi token bị đánh cắp, lộ trong log hoặc bị sử dụng sai mục đích, kẻ tấn công có thể khai thác toàn bộ scope được cấp trong thời gian token còn hiệu lực. Đây là lỗi **scope quá rộng (over-scoped token)**.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học liên hệ scope với mô hình tin cậy và vòng đời token: authorization server cấp quyền, client yêu cầu quyền, resource server kiểm tra quyền và policy quyết định thao tác. Người thiết kế cần bảo đảm quyền được cấp phù hợp với use case, client, audience/resource và thời hạn; đồng thời kiểm tra scope thực tế trên token sau các bước refresh hoặc token exchange.

Sau bài học, người học có thể:

- Nhận biết scope quá rộng và phân biệt nó với role hoặc quyền truy cập dữ liệu.
- Xác định nguyên nhân từ client registration, consent, default scope, policy hoặc ánh xạ claim.
- Đánh giá tác động của over-scoping đối với access token, refresh token và token exchange.
- Thu hẹp scope theo least privilege, audience/resource và thời hạn.
- Kiểm thử cả requested scope, granted scope và quyền thực tế tại resource server.
- Phát hiện, xử lý và ngăn tái diễn việc cấp quyền vượt nhu cầu.

## 2. Scope quá rộng là gì?

Scope mô tả phạm vi quyền mà client yêu cầu hoặc authorization server cấp cho access token. Resource server dùng scope đã xác minh cùng các chính sách khác để quyết định thao tác có được phép hay không. Scope quá rộng xảy ra khi tập quyền được cấp vượt quá nhu cầu đã được phê duyệt của client hoặc use case.

Ví dụ:

| Client/use case | Nhu cầu thực tế | Scope bị cấp quá rộng |
| --- | --- | --- |
| orders-dashboard chỉ xem đơn hàng | orders.read | orders.read orders.write orders.cancel |
| inventory-reporter chỉ đọc tồn kho | inventory.read | inventory.read inventory.adjust inventory.delete |
| billing-export chỉ xuất hóa đơn | billing.invoice.read | billing.admin payments.refund customer.delete |
| service gửi thông báo trạng thái | notifications.send | notifications.* hoặc admin |

Một scope quá rộng có thể do tên scope quá tổng quát, ví dụ **admin**, **full_access**, **api.all**; do một client nhận nhiều scope không cần thiết; hoặc do scope có ý nghĩa quá lớn so với thao tác thực tế. Wildcard scope như **resource.*** cần được xem xét đặc biệt vì có thể tự động bao gồm quyền mới được thêm trong tương lai.

Không phải cứ token có nhiều scope là sai. Một ứng dụng có nhiều use case thực sự có thể cần nhiều quyền. Câu hỏi là: **mỗi scope có cần thiết cho client, audience, hành động và thời hạn đang xét hay không?** Quyết định cần dựa trên bằng chứng sử dụng và yêu cầu nghiệp vụ, không chỉ dựa vào số lượng scope.

## 3. Vì sao scope quá rộng nguy hiểm?

### 3.1 Tăng phạm vi thiệt hại khi token bị lộ

Bearer access token thường có thể được sử dụng bởi bất kỳ bên nào sở hữu token nếu không có sender constraint. Nếu token chứa quyền đọc, ghi, xóa và quản trị, kẻ tấn công có thể thực hiện nhiều thao tác trong cùng thời hạn token. Scope tối thiểu làm giảm số hành động có thể thực hiện khi credential bị lộ.

Ví dụ một worker chỉ cần đọc trạng thái thanh toán nhưng nhận scope **payments.read payments.refund payments.admin**. Nếu access token bị lộ trong log, hậu quả có thể vượt xa việc đọc dữ liệu: người khác có thể hoàn tiền hoặc gọi API quản trị, tùy policy của resource server.

### 3.2 Tăng nguy cơ leo thang quyền và truy cập chéo dịch vụ

Nếu authorization server cấp scope rộng cho nhiều audience, một token có thể bị sử dụng ở nhiều API. Audience và scope giải quyết hai câu hỏi khác nhau:

- **Audience/resource:** token được phát hành để resource server nào chấp nhận?
- **Scope:** token được phép yêu cầu những nhóm hành động nào trong phạm vi resource đó?

Audience rộng không thay thế scope hẹp; scope rộng cũng không hợp thức hóa audience sai. Resource server cần xác minh cả hai. Không cấp một access token cho nhiều API không liên quan chỉ vì chúng cùng một hệ thống.

### 3.3 Tạo đặc quyền tồn tại lâu hơn nhu cầu

Scope quá rộng thường đi cùng access token lifetime dài, refresh token có thể dùng lâu hoặc policy không thu hồi kịp. Khi quyền của client đã thay đổi nhưng refresh token vẫn có thể xin access token với scope cũ, quyền vượt nhu cầu tiếp tục tồn tại.

Việc giảm scope ở cấu hình client không nhất thiết làm các access token đã phát hành mất hiệu lực ngay. Cần xác định cách xử lý token hiện có: chờ hết hạn, revoke token/refresh token, introspection hoặc denylist theo khả năng của hệ thống.

### 3.4 Làm suy yếu kiểm soát và khó kiểm toán

Khi client nào cũng được cấp **full_access**, resource owner khó biết ứng dụng thực sự cần gì. Consent trở nên thiếu ý nghĩa, audit không phản ánh ranh giới quyền nhỏ nhất và việc điều tra khó xác định quyền nào là cần thiết cho từng nghiệp vụ.

## 4. Phân biệt scope, role và quyền trên tài nguyên

Scope không phải là toàn bộ hệ thống phân quyền. Một request có thể cần đồng thời nhiều lớp kiểm soát:

| Lớp | Ví dụ | Câu hỏi |
| --- | --- | --- |
| Token scope | orders.cancel | Client/token có được phép yêu cầu hành động hủy đơn không? |
| Audience | orders-api | Token có dành cho API đang nhận request không? |
| Role/authority | ORDER_MANAGER | Chủ thể có vai trò phù hợp không? |
| Resource ownership | order.tenant_id = caller.tenant_id | Chủ thể có được thao tác trên bản ghi cụ thể không? |
| Business policy | Đơn hàng chưa giao | Trạng thái hiện tại có cho phép hủy không? |

Scope quá rộng vẫn là lỗi ngay cả khi API có thêm role check, vì token đã được cấp quyền vượt nhu cầu và có thể được sử dụng ở endpoint khác hoặc sau khi cấu hình thay đổi. Ngược lại, scope hẹp không thay thế kiểm tra ownership, tenant và business rule.

Ví dụ, token có **orders.read** không đồng nghĩa người dùng được đọc mọi đơn hàng. Resource server vẫn cần giới hạn bản ghi theo tenant hoặc quyền sở hữu. Token có **orders.cancel** cũng không có nghĩa được hủy đơn đã giao nếu business policy cấm hành động đó.

## 5. Các nguyên nhân thường gặp

| Nguyên nhân | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Dùng scope tổng quát | Client nhận **admin**, **full_access** | Tách scope theo hành động và resource |
| Cấp tất cả scope khi đăng ký client | Client nhỏ nhận toàn bộ API permissions | Áp dụng allowlist theo client và use case |
| Default scope quá rộng | Request không chỉ định scope vẫn nhận quyền lớn | Rà soát default/implicit scope; mặc định cấp tối thiểu |
| Consent không được giới hạn | User/admin chấp thuận quyền không liên quan | Hiển thị rõ quyền, yêu cầu phê duyệt theo rủi ro |
| Scope mapping sai | Claim **scp** hoặc **scope** được ánh xạ thành authority rộng | Kiểm thử converter và schema của issuer |
| Wildcard/prefix matching | Scope **orders.*** hoặc so khớp chuỗi con | Dùng danh sách quyền chính xác, policy có kiểm soát |
| Client dùng chung | Nhiều workload chia sẻ một OAuth client | Tách client identity theo workload và môi trường |
| Refresh flow giữ quyền cũ | Refresh token tiếp tục xin scope đã không còn cần | Rà soát refresh policy, rotation và revoke |
| Token exchange không downscope | Token mới giữ toàn bộ scope của token nguồn | Áp dụng policy requested/granted scope và audience |
| Không review quyền định kỳ | Scope tích lũy qua thời gian | Access review và loại bỏ quyền không sử dụng |
| API không kiểm tra scope | Token được cấp rộng và endpoint không giới hạn | Áp dụng authorization tại resource server |

Một lỗi thiết kế quan trọng là cấp scope theo quyền của người dùng mà không xét quyền của client. Trong OAuth, token có thể đại diện cho user, client hoặc cả hai tùy grant/extension. Authorization server phải áp dụng policy phù hợp với loại client, subject, actor, audience và grant; không sao chép toàn bộ quyền của user sang mọi ứng dụng.

## 6. Xác định scope tối thiểu cần cấp

### 6.1 Lập ma trận client – resource – hành động

Trước khi sửa cấu hình, lập bảng nhu cầu:

| Client | Resource/Audience | Hành động | Scope cần thiết | Lý do |
| --- | --- | --- | --- | --- |
| orders-dashboard | orders-api | Xem đơn hàng | orders.read | Hiển thị danh sách và chi tiết |
| orders-worker | inventory-api | Đọc tồn kho | inventory.read | Kiểm tra số lượng trước khi đặt |
| billing-export | billing-api | Đọc hóa đơn | billing.invoice.read | Xuất dữ liệu hóa đơn đã được phép |
| refund-service | billing-api | Hoàn tiền | payments.refund | Xử lý refund theo workflow riêng |

Không gom scope của các ứng dụng thành một role dùng chung nếu chúng có nhu cầu khác nhau. Tách client identity theo workload giúp cấp quyền và thu hồi độc lập. Client ID không phải secret, nhưng credential xác thực client phải được bảo vệ.

### 6.2 Chọn độ hạt của scope

Scope nên đủ cụ thể để diễn đạt quyền mà resource server có thể kiểm tra, nhưng không nên tạo hàng trăm scope trùng lặp khó quản lý. Có thể thiết kế theo:

- Resource: orders, inventory, billing, profile.
- Action: read, create, update, cancel, refund, administer.
- Ranh giới nhạy cảm: dữ liệu cá nhân, export, thanh toán, quản trị.

Ví dụ **orders.read** và **orders.cancel** dễ đánh giá hơn một scope chung **orders.manage** nếu hai hành động có rủi ro khác nhau. Với hệ thống đơn giản, scope **orders.write** có thể bao gồm nhiều thao tác ghi; khi đó cần kiểm tra xem các thao tác có cùng mức rủi ro và cùng chủ thể được phép hay không.

Không dùng scope để mã hóa từng record ID hoặc dữ liệu động. Quyền truy cập từng tài nguyên nên được kiểm tra bằng policy dữ liệu/ABAC hoặc authorization logic ở resource server.

### 6.3 Xem xét quyền theo thời gian

Scope chỉ nên được cấp trong thời hạn phù hợp. Với quyền nhạy cảm:

- Access token lifetime ngắn hơn quyền thông thường nếu rủi ro yêu cầu.
- Refresh token có rotation, reuse detection và giới hạn theo client.
- Scope đặc quyền có thể yêu cầu consent hoặc step-up authorization.
- Client có thể cần reauthorization khi scope hoặc audience thay đổi.
- Khi client không còn dùng quyền, loại scope khỏi policy và revoke credential/token theo quy trình.

TTL ngắn giảm cửa sổ sử dụng token bị lộ nhưng không thay thế việc cấp scope tối thiểu.

## 7. Requested scope và granted scope

Một client có thể yêu cầu một tập scope nhưng authorization server chỉ cấp tập con được phép. Phải phân biệt:

- **Requested scope:** quyền client yêu cầu trong authorization/token request.
- **Granted scope:** quyền authorization server thực sự cấp.
- **Effective permission:** quyền resource server thực tế cho phép sau khi kiểm tra scope, audience, subject/actor, ownership và business policy.

Ví dụ request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_AUTHENTICATION>

grant_type=client_credentials&scope=inventory.read%20inventory.adjust
~~~

Giả sử policy chỉ cho client **inventory-reporter** đọc tồn kho. Authorization server có thể từ chối toàn bộ yêu cầu nếu không chấp nhận scope requested, hoặc cấp tập scope hẹp hơn nếu grant/server contract hỗ trợ và response thể hiện rõ quyền thực tế. Không giả định mọi authorization server đều tự động downscope khi request scope quá rộng.

Ví dụ metadata minh họa khi chỉ cấp quyền đọc:

~~~json
{
  "access_token": "<REDACTED>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

Client phải sử dụng scope được trả về và không được suy ra quyền từ scope đã yêu cầu. Resource server vẫn phải kiểm tra scope thực tế trên token đã xác minh. Không ghi raw access token vào log hoặc tài liệu.

## 8. Scope quá rộng trong token exchange

RFC 8693 cho phép client gửi subject token và tùy chọn actor token đến STS để yêu cầu token mới. Token exchange không có nghĩa token mới mặc nhiên giữ nguyên mọi quyền của token nguồn. STS cần đánh giá:

- Client nào đang yêu cầu exchange?
- Subject và actor đã được xác minh chưa?
- Token nguồn được phát hành bởi issuer nào và dành cho audience nào?
- Audience/resource mới có nằm trong allowlist không?
- Requested scope có nằm trong quyền client được phép exchange không?
- Scope nào được cấp sau khi áp dụng policy?

Ví dụ: token nguồn có **orders.read orders.write inventory.read inventory.adjust**. Orders API chỉ cần gọi Inventory API để đọc tồn kho. STS nên cấp token mới có audience **inventory-api** và scope **inventory.read**. Không chuyển **inventory.adjust** hoặc scope của Orders API sang token mới nếu không có nhu cầu và policy cho phép.

| Thuộc tính | Token nguồn | Token sau exchange |
| --- | --- | --- |
| Audience | orders-api | inventory-api |
| Scope | orders.read orders.write inventory.read inventory.adjust | inventory.read |
| Mục đích | Thao tác đơn hàng | Đọc tồn kho để kiểm tra |
| Thời hạn | Theo token nguồn | Theo policy token mới, thường ngắn và phù hợp use case |

Downscoping phải được thực thi ở STS và được phản ánh trên token mới/introspection response. Chỉ thay đổi log hoặc response metadata mà không giới hạn quyền thật trong token/resource server là không đủ.

## 9. Cách phát hiện scope quá rộng

### 9.1 Đối chiếu quyền được cấp với quyền sử dụng

Thu thập metadata an toàn về scope được cấp và endpoint/hành động được gọi. So sánh trong một khoảng thời gian đại diện cho chu kỳ nghiệp vụ:

- Scope được cấp nhưng không được sử dụng.
- Client có scope quản trị nhưng chỉ gọi API đọc.
- Một client có audience không liên quan tới chức năng của nó.
- Scope đặc quyền xuất hiện trên nhiều client không cần quyền đó.
- Requested scope liên tục vượt granted scope hoặc policy.

Không tự động xóa scope chỉ vì không thấy sử dụng trong một ngày. Có thể có tác vụ hàng tháng/quý, quy trình khẩn cấp hoặc traffic theo mùa. Review cần owner xác nhận và xét đủ chu kỳ nghiệp vụ.

### 9.2 Tín hiệu cảnh báo

- Token của client thông thường chứa **admin**, **delete**, **refund** hoặc **impersonate**.
- Client yêu cầu nhiều audience hoặc scope mới bất thường.
- Requested scope tăng đột ngột sau một lần thay đổi cấu hình.
- Một workload dùng chung client ID với nhiều dịch vụ không liên quan.
- Resource server nhận token có scope vượt danh mục được phép.
- Token exchange cấp scope không nằm trong allowlist.
- Refresh token tiếp tục duy trì quyền đã bị gỡ khỏi cấu hình client.

Audit event nên ghi requested/granted scope, audience, client, subject/actor đã xác minh, policy version và outcome. Tránh ghi raw token hoặc toàn bộ claim nhạy cảm. Nếu cần fingerprint để tương quan token, dùng keyed HMAC và hạn chế truy cập.

## 10. Khắc phục một client đã được cấp scope quá rộng

Quy trình xử lý có kiểm soát:

1. Xác định client, môi trường, audience, scope và thời điểm quyền được cấp.
2. Tìm owner và business purpose của từng scope.
3. Đối chiếu với API usage, job schedule và tài liệu nghiệp vụ.
4. Xác định scope tối thiểu cần giữ; tách client nếu nhiều workload có nhu cầu khác nhau.
5. Cập nhật client registration, consent hoặc authorization policy theo quy trình phê duyệt.
6. Kiểm thử token mới: requested/granted scope, audience và endpoint authorization.
7. Xử lý access token và refresh token đã phát hành theo mức độ rủi ro: chờ hết hạn, revoke hoặc yêu cầu reauthorization.
8. Theo dõi lỗi 403, token refresh failure và workflow nghiệp vụ sau thay đổi.
9. Ghi audit change, người yêu cầu/phê duyệt, policy version và kết quả readback.

Không thu hẹp scope trực tiếp trong production mà không đánh giá tác động. Thay đổi quá nhanh có thể làm hỏng job hợp lệ; giữ scope rộng quá lâu lại duy trì rủi ro. Dùng staging/canary, thông báo owner và rollback có kiểm soát.

### 10.1 Khi phát hiện token bị lộ cùng scope quá rộng

Nếu có bằng chứng token bị lộ:

- Xác định token type, issuer, client, audience, scope và thời hạn còn lại bằng nguồn tin cậy.
- Revoke token/refresh token hoặc vô hiệu hóa client theo incident policy.
- Kiểm tra token reuse, request bất thường và các hành động đã thực hiện tại resource server.
- Thu hẹp scope/client policy trước khi cấp credential mới.
- Xoay client credential nếu credential client cũng bị lộ.
- Đánh giá refresh-token family và revoke liên quan nếu có reuse detection.
- Lưu audit evidence, correlation ID và timeline; không sao chép token thật vào ticket.

Chỉ thay đổi scope cấu hình không làm access token cũ mất quyền ngay trong mọi kiến trúc. Cần biết resource server xác minh token bằng JWT local validation, introspection hay cache; mỗi cách có độ trễ thu hồi khác nhau.

## 11. Kiểm thử scope quá rộng

Test cần chứng minh rằng client chỉ nhận đúng quyền được phê duyệt và resource server từ chối hành động vượt quyền. Có cả test cấp token và test sử dụng token.

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| SCOPE-01 | Client chỉ được phép inventory.read yêu cầu inventory.read | Cấp quyền đọc theo policy |
| SCOPE-02 | Client inventory-reporter yêu cầu inventory.adjust | Từ chối hoặc downscope theo contract đã xác định |
| SCOPE-03 | Token có inventory.read gọi API đọc | Cho qua scope check |
| SCOPE-04 | Token chỉ có inventory.read gọi API điều chỉnh | 403/insufficient_scope theo hợp đồng |
| SCOPE-05 | Client yêu cầu scope admin không nằm allowlist | Không cấp scope admin |
| SCOPE-06 | Token có audience billing-api gọi orders-api | Bị từ chối do audience |
| SCOPE-07 | Token exchange yêu cầu inventory.read và inventory.adjust | Token mới chỉ có scope được policy cho phép |
| SCOPE-08 | Refresh token sau khi policy scope đã thu hẹp | Không tái cấp quyền cũ trái policy |
| SCOPE-09 | Claim scope sai kiểu hoặc chứa scope không được định nghĩa | Không tự tạo authority ngoài allowlist |
| SCOPE-10 | Wildcard scope khớp quyền mới được thêm | Không tự mở rộng quyền ngoài change được duyệt |
| SCOPE-11 | Client dùng chung được tách thành hai workload | Mỗi client nhận đúng tập scope riêng |
| SCOPE-12 | Scope bị gỡ nhưng access token cũ còn hiệu lực | Hành vi revoke/cache/expiry đúng với policy đã công bố |

Ngoài status code, kiểm tra:

- Token response hoặc introspection cho biết granted scope thực tế.
- Resource server chỉ ánh xạ scope đã xác minh và được hỗ trợ.
- Request bị từ chối không tạo side effect, không phát event nghiệp vụ và không gọi downstream đặc quyền.
- Audit event ghi decision, client, audience, scope và policy version an toàn.
- Không xuất hiện access token, refresh token hoặc client secret trong log/test report.

### 11.1 Kiểm tra quyền bằng Spring Security

Ví dụ cấu hình endpoint chỉ cho phép authority **SCOPE_inventory.read**:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/inventory/**")
        .hasAuthority("SCOPE_inventory.read")
    .requestMatchers(HttpMethod.POST, "/inventory/adjust")
        .hasAuthority("SCOPE_inventory.adjust")
    .anyRequest().authenticated()
);
~~~

Test authorization layer bằng MockMvc và JWT test principal:

~~~java
mockMvc.perform(post("/inventory/adjust")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_inventory.read"))))
    .andExpect(status().isForbidden());
~~~

Đây là test lớp authorization với authority giả lập; nó không chứng minh JWT signature, issuer, audience, claim mapping hoặc token issuance thực tế. Cần test converter/decoder và luồng lấy token từ authorization server ở tầng tích hợp phù hợp. Với opaque token, dùng opaqueToken() cho authorization test và introspection stub cho HTTP integration.

## 12. Các lỗi khắc phục thường gặp

| Cách xử lý sai | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Xóa scope khỏi giao diện client nhưng không đổi policy issuer | Token vẫn được cấp scope cũ | Cập nhật nguồn cấp quyền và xác minh token mới |
| Chỉ kiểm tra requested scope | Nhầm quyền yêu cầu với quyền được cấp | Kiểm tra granted scope trong response/token đã xác minh |
| Thu hẹp scope nhưng không xử lý token cũ | Access token/refresh token cũ vẫn có thể dùng quyền rộng | Revoke hoặc chờ expiry theo risk và contract |
| Dùng một OAuth client cho nhiều workload | Không thể giới hạn/thu hồi độc lập | Tách client identity và credential |
| Chỉ kiểm tra scope, bỏ qua audience | Token có thể dùng sai resource | Xác minh cả aud/resource |
| Chuyển mọi scope của token nguồn khi exchange | Token mới có quyền không cần thiết | STS áp dụng allowlist và downscope |
| Dùng wildcard để tiện vận hành | Quyền mới có thể tự được bao gồm | Scope cụ thể và review khi mở rộng |
| Xóa quyền dựa trên usage ngắn hạn | Làm hỏng tác vụ ít chạy | Xem đủ chu kỳ và xác nhận với owner |
| Chỉ dựa vào 403 sau deploy | Không biết token response có bị cấp rộng hay không | Kiểm thử cả issuance và resource server |

## 13. Checklist phòng ngừa

- [ ] Mỗi client có owner, business purpose và audience/resource rõ ràng.
- [ ] Scope được cấp theo ma trận client – resource – action.
- [ ] Tránh scope tổng quát và wildcard nếu không có lý do/kiểm soát rõ.
- [ ] Tách client identity giữa workload và môi trường có ranh giới tin cậy khác nhau.
- [ ] Authorization server kiểm tra allowlist requested scope và trả granted scope rõ ràng.
- [ ] Resource server xác minh issuer, audience, expiry và scope theo hợp đồng.
- [ ] Kiểm tra ownership, tenant và business rule ngoài scope.
- [ ] Token exchange chỉ cấp scope/audience được policy cho phép.
- [ ] Refresh flow không tái cấp quyền đã bị thu hẹp hoặc thu hồi.
- [ ] Access review định kỳ tìm scope không cần thiết và scope không sử dụng đủ chu kỳ.
- [ ] Thay đổi scope có phê duyệt, audit và readback.
- [ ] Có quy trình revoke/reauthorize khi scope quá rộng hoặc token bị lộ.
- [ ] Test token response, JWT/opaque mapping, resource authorization và side effect.
- [ ] Log/audit không chứa raw token hoặc client secret.

## Tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** scope trong authorization request và token response.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** sử dụng access token và xử lý insufficient_scope.
- **RFC 8693 — OAuth 2.0 Token Exchange:** subject/actor token, audience/resource và scope của token được cấp.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ OAuth flow, token và client.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile claim của JWT access token.
- **NIST SP 800-53 Rev. 5 — AC-6 Least Privilege:** cấp quyền tối thiểu theo nhiệm vụ.

Scope quá rộng là lỗi thiết kế quyền có thể làm tăng đáng kể hậu quả khi token bị lộ hoặc bị sử dụng sai mục đích. Khắc phục bền vững cần xác định nhu cầu theo từng client/resource/action, giới hạn quyền tại authorization server, kiểm tra lại tại resource server và quản lý các token đã phát hành theo vòng đời. Least privilege chỉ được bảo đảm khi requested scope, granted scope và quyền thực tế đều được kiểm chứng.
