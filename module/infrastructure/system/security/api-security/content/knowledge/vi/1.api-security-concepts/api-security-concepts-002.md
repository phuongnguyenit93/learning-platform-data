# Bảo mật API bao gồm identity, authorization, input và output

Bảo mật API là tập hợp các kiểm soát bảo vệ từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. Một API chỉ dùng HTTPS hoặc yêu cầu người dùng đăng nhập vẫn có thể bị khai thác nếu người gọi được phép đọc dữ liệu của người khác, gửi đầu vào nguy hiểm, tiêu tốn tài nguyên quá mức hoặc nhận về những trường dữ liệu nội bộ.

Khi thiết kế một endpoint, cần trả lời bốn câu hỏi liên tiếp:

1. **Identity:** Ai đang gọi API?
2. **Authorization:** Danh tính đó được phép thực hiện hành động nào trên đối tượng dữ liệu nào?
3. **Input:** Dữ liệu gửi vào có đúng cấu trúc, hợp lệ về nghiệp vụ và an toàn để xử lý không?
4. **Output:** Phản hồi chỉ tiết lộ dữ liệu mà người gọi được phép biết hay không?

Bốn phần này bổ sung cho nhau. Identity tạo ra căn cứ để quyết định quyền; authorization giới hạn hành động và phạm vi dữ liệu; kiểm soát input bảo vệ hệ thống trong lúc tiếp nhận và xử lý yêu cầu; kiểm soát output ngăn dữ liệu nhạy cảm thoát ra ngoài.

## 1. Identity: xác định chính xác bên gọi API

Identity là thông tin đại diện cho chủ thể đang gửi yêu cầu. Chủ thể có thể là người dùng, ứng dụng bên thứ ba, một service nội bộ, thiết bị hoặc một tác vụ chạy nền. Mỗi loại chủ thể có cách xác thực phù hợp, nhưng hệ thống đều phải xác định được credential thuộc về ai hoặc workload nào.

**Authentication (xác thực)** là quá trình kiểm tra credential để xác nhận identity. Một số cơ chế thường gặp:

- **Session cookie:** phù hợp với ứng dụng web có phiên đăng nhập; cookie cần được bảo vệ bằng các thuộc tính như `HttpOnly`, `Secure` và `SameSite` phù hợp. Vì trình duyệt tự gửi cookie, các request làm thay đổi dữ liệu cũng cần biện pháp chống CSRF phù hợp.
- **OAuth 2.0 access token:** thường được dùng để cấp quyền truy cập API cho ứng dụng hoặc người dùng. Với JWT, resource server phải kiểm tra chữ ký, issuer, audience, thời hạn và các điều kiện liên quan trước khi tin vào claims.
- **API key:** thường nhận diện một ứng dụng hoặc khách hàng tích hợp. API key không tự chứng minh người dùng cuối là ai và không nên được xem như một cơ chế phân quyền chi tiết.
- **Mutual TLS (mTLS):** dùng chứng thư số để xác thực workload hoặc máy khách trong các kết nối service-to-service.

Không được xem dữ liệu do client tự khai báo là bằng chứng identity. Ví dụ, `userId`, `tenantId`, `role` hoặc `isAdmin` nằm trong JSON request không chứng minh người gửi sở hữu danh tính hay quyền tương ứng. Server phải lấy identity từ credential đã xác thực và đã kiểm tra.

Với JWT, việc giải mã token thành công chưa đủ. Server cần xác minh chữ ký bằng khóa tin cậy, kiểm tra `iss` (issuer), `aud` (audience), `exp` (thời điểm hết hạn), và các claim bắt buộc theo hợp đồng bảo mật. Token dành cho một API không nên được chấp nhận tùy tiện ở API khác. Credential cũng cần có thời hạn, quy trình thu hồi hoặc luân chuyển phù hợp và không được ghi nguyên văn vào log.

Identity trả lời câu hỏi **ai đang gọi**, chứ chưa trả lời người đó được phép làm gì. Một token hợp lệ chỉ cho biết danh tính đã được xác thực; nó không đồng nghĩa với quyền truy cập mọi tài nguyên.

## 2. Authorization: kiểm tra quyền ở đúng phạm vi

Authorization (phân quyền) quyết định một identity có thể thực hiện hành động cụ thể trên tài nguyên cụ thể trong ngữ cảnh hiện tại hay không. Kiểm tra này phải được thực hiện ở phía server cho từng yêu cầu cần bảo vệ.

Một endpoint thường cần ít nhất ba góc nhìn phân quyền:

| Phạm vi | Câu hỏi cần kiểm tra | Ví dụ |
| --- | --- | --- |
| Chức năng (function-level) | Người gọi có được phép dùng chức năng này không? | Nhân viên hỗ trợ được xem đơn hàng nhưng không được hoàn tiền. |
| Đối tượng (object-level) | Người gọi có được phép thao tác trên bản ghi cụ thể này không? | Người dùng chỉ được xem đơn hàng thuộc tài khoản hoặc tenant của mình. |
| Thuộc tính (property-level) | Người gọi có được phép đọc hoặc thay đổi trường dữ liệu này không? | Người dùng được đổi địa chỉ giao hàng nhưng không được tự đặt `totalPrice`, `ownerId` hoặc `status`. |

Chỉ kiểm tra quyền ở cấp endpoint là chưa đủ. Ví dụ, endpoint `GET /api/orders/{orderId}` có thể yêu cầu người dùng đăng nhập, nhưng nếu server chỉ truy vấn theo `orderId` thì người dùng có thể thay ID để đọc đơn hàng của người khác. Đây là lỗi phân quyền mức đối tượng, thường được gọi là IDOR hoặc BOLA.

Có hai cách tiếp cận phổ biến để biểu diễn quyền:

- **RBAC (Role-Based Access Control):** cấp quyền thông qua vai trò như `ADMIN`, `SUPPORT` hoặc `CUSTOMER`. Cách này dễ quản lý khi quyền gắn tương đối ổn định với vai trò.
- **ABAC (Attribute-Based Access Control):** quyết định dựa trên thuộc tính của chủ thể, tài nguyên và ngữ cảnh, chẳng hạn tenant, người sở hữu, trạng thái đơn hàng, thời gian hoặc mức độ nhạy cảm.

Một hệ thống có thể kết hợp cả hai: role hoặc scope quyết định người dùng có thể gọi chức năng; quan hệ sở hữu, tenant và trạng thái nghiệp vụ quyết định họ có thể thao tác trên bản ghi cụ thể hay không.

Các nguyên tắc quan trọng:

- Mặc định từ chối nếu chưa có quy tắc cấp quyền rõ ràng (deny by default).
- Kiểm tra quyền ở server trong mỗi request; ẩn nút trên giao diện không phải là kiểm soát bảo mật.
- Không tin `tenantId`, `ownerId`, role hay trạng thái do client gửi lên. Lấy dữ liệu nhận diện từ identity đã xác thực và dữ liệu quyền từ nguồn tin cậy phía server.
- Kiểm tra cả trạng thái nghiệp vụ. Người có quyền sửa đơn hàng vẫn có thể không được sửa sau khi đơn đã giao hoặc đã khóa.
- Dùng phản hồi `403 Forbidden` khi muốn thể hiện tài nguyên tồn tại nhưng người gọi không có quyền; có thể dùng `404 Not Found` để che giấu sự tồn tại của tài nguyên nếu đó là chính sách nhất quán của hệ thống.

## 3. Input: kiểm soát dữ liệu đi vào

Mọi dữ liệu bên ngoài gửi đến API đều phải được xem là không đáng tin cậy, kể cả dữ liệu đến từ ứng dụng nội bộ. Input có thể nằm trong path, query string, header, cookie, JSON body, multipart file hoặc URL mà server được yêu cầu truy cập.

Kiểm soát input nên có nhiều lớp:

### 3.1. Kiểm tra cấu trúc và kiểu dữ liệu

Kiểm tra request có đúng schema hay không: trường bắt buộc, kiểu dữ liệu, độ dài, định dạng, miền giá trị, số lượng phần tử và kích thước tổng thể. Chỉ nhận các trường endpoint thực sự hỗ trợ. Với dữ liệu dạng enum, dùng danh sách giá trị cho phép thay vì chấp nhận chuỗi tùy ý.

Ví dụ, endpoint đổi địa chỉ giao hàng chỉ cần nhận trường `address`. Không nên bind trực tiếp JSON vào entity `Order` có cả `tenantId`, `ownerId`, `totalPrice` và `status`, vì client có thể gửi thêm trường mà endpoint không có ý định cho phép thay đổi. Hãy dùng request DTO riêng cho từng thao tác.

### 3.2. Kiểm tra ý nghĩa nghiệp vụ

Một giá trị đúng kiểu vẫn có thể sai về nghiệp vụ. Số lượng hàng có thể là số nguyên nhưng phải lớn hơn 0 và không vượt giới hạn cho phép; ngày kết thúc không được trước ngày bắt đầu; một đơn hàng đã hủy không được chuyển thẳng sang trạng thái đã giao.

Validation nên được thực hiện ở ranh giới API và tiếp tục được bảo đảm trong lớp nghiệp vụ hoặc cơ sở dữ liệu khi cần. Không dựa vào validation ở giao diện người dùng, vì client có thể bị thay thế hoặc bỏ qua.

### 3.3. Ngăn injection và xử lý dữ liệu đúng ngữ cảnh

Không ghép chuỗi input trực tiếp vào câu SQL, lệnh hệ điều hành, biểu thức hoặc truy vấn. Dùng prepared statement/parameterized query và API an toàn của framework. Khi đưa dữ liệu vào HTML, JavaScript, URL hoặc một ngữ cảnh khác, phải mã hóa đầu ra đúng ngữ cảnh đó. Validation giúp từ chối dữ liệu không hợp lệ nhưng không thay thế parameterization hay output encoding.

### 3.4. Chống SSRF khi API gọi địa chỉ do người dùng cung cấp

SSRF (Server-Side Request Forgery) xảy ra khi kẻ tấn công khiến server gửi request đến địa chỉ mà họ chọn, chẳng hạn dịch vụ nội bộ, địa chỉ loopback hoặc endpoint metadata của hạ tầng. Rủi ro xuất hiện ở tính năng nhập URL, tải ảnh từ URL, webhook, proxy hoặc kiểm tra trạng thái website.

Nếu nghiệp vụ bắt buộc phải truy cập URL do người dùng cung cấp, cần giới hạn scheme, hostname và port bằng allowlist phù hợp; chặn địa chỉ loopback, private, link-local và các dải địa chỉ dành riêng; kiểm tra địa chỉ IP thực tế sau phân giải DNS và bảo đảm kết nối dùng đúng địa chỉ đã kiểm tra; kiểm tra lại đích sau redirect; đồng thời áp dụng timeout, giới hạn kích thước phản hồi và kiểm soát egress ở tầng mạng. Không chỉ kiểm tra chuỗi URL ban đầu vì DNS hoặc redirect có thể khiến kết nối cuối cùng đi đến một địa chỉ khác.

### 3.5. Giới hạn việc tiêu tốn tài nguyên

Một request hợp lệ về cú pháp vẫn có thể làm hệ thống quá tải. Cần đặt giới hạn cho kích thước body và file tải lên, số phần tử trong batch, page size, độ sâu truy vấn, thời gian xử lý, số lần thử và tần suất gọi API. Với thao tác tốn kém, có thể áp dụng quota theo identity, tenant hoặc client, kết hợp rate limiting và giới hạn đồng thời. Khi vượt giới hạn, trả lỗi phù hợp như `413 Payload Too Large` hoặc `429 Too Many Requests`.

## 4. Output: chỉ trả dữ liệu được phép tiết lộ

Output gồm response body, HTTP headers, mã trạng thái, thông báo lỗi, file tải xuống và cả dữ liệu được ghi vào log. Mỗi dạng đầu ra đều có thể làm lộ thông tin nếu không được kiểm soát.

Các nguyên tắc chính:

- **Tối thiểu hóa dữ liệu:** chỉ trả những trường client cần cho chức năng hiện tại. Dùng response DTO hoặc projection riêng; tránh serialize trực tiếp entity hoặc đối tượng nội bộ.
- **Phân quyền theo trường:** một người có thể xem hồ sơ nhưng không được xem số giấy tờ, thông tin thanh toán hoặc dữ liệu riêng tư. Cùng một bản ghi có thể cần response khác nhau tùy identity và mục đích truy cập.
- **Không tiết lộ bí mật nội bộ:** không trả access token, mật khẩu, API key, secret, dữ liệu cấu hình, câu SQL, stack trace hoặc đường dẫn nội bộ.
- **Lỗi an toàn:** thông báo lỗi nên đủ hữu ích cho client nhưng không tiết lộ chi tiết triển khai. Ghi chi tiết kỹ thuật vào log được bảo vệ, kèm correlation ID để tra cứu.
- **Bảo vệ cache và truyền tải:** với response chứa dữ liệu nhạy cảm, cân nhắc chính sách cache như `Cache-Control: no-store`; dùng HTTPS để bảo vệ dữ liệu trên đường truyền.
- **Bảo vệ log:** không ghi credential hoặc toàn bộ payload nhạy cảm. Che hoặc loại bỏ dữ liệu cá nhân và bí mật; giới hạn quyền đọc log và thời gian lưu theo chính sách.

Không nên giả định rằng dữ liệu đã được phân quyền khi đọc thì mọi trường trong response đều được phép trả về. Quyền đọc một đối tượng không nhất thiết đồng nghĩa với quyền đọc tất cả thuộc tính của nó.

## 5. Ví dụ: bảo vệ endpoint đổi địa chỉ giao hàng

Giả sử API cung cấp endpoint:

```http
PATCH /api/orders/{orderId}/shipping-address
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "address": "12 Nguyen Hue, District 1"
}
```

Một cách triển khai bằng Spring Boot có thể thể hiện rõ các lớp kiểm soát:

```java
public record ChangeShippingAddressRequest(
    @NotBlank
    @Size(max = 200)
    String address
) {}

public record OrderResponse(
    UUID id,
    String status,
    String shippingAddress
) {}

@PatchMapping("/orders/{orderId}/shipping-address")
@PreAuthorize("hasAuthority('SCOPE_orders:write')")
public OrderResponse changeShippingAddress(
        @AuthenticationPrincipal Jwt jwt,
        @PathVariable UUID orderId,
        @Valid @RequestBody ChangeShippingAddressRequest request) {

    UUID tenantId = UUID.fromString(jwt.getClaimAsString("tenant_id"));

    Order order = orderRepository.findByIdAndTenantId(orderId, tenantId)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

    authorizationService.requireCanChangeShippingAddress(jwt, order);
    order.changeShippingAddress(request.address());

    return orderMapper.toResponse(order);
}
```

Ví dụ trên giả định resource server đã xác minh token và cấu hình Spring Security đã bật method security. Các kiểm soát được phân chia như sau:

| Thành phần | Kiểm soát |
| --- | --- |
| Identity | `@AuthenticationPrincipal Jwt` nhận principal đã được xác thực; `tenant_id` được lấy từ claim đáng tin cậy của token. |
| Authorization chức năng | `@PreAuthorize` yêu cầu scope `orders:write`. |
| Authorization đối tượng | Truy vấn theo cả `orderId` và `tenantId` giới hạn bản ghi trong tenant của người gọi; service kiểm tra thêm quyền và trạng thái nghiệp vụ. |
| Input | Request DTO chỉ nhận `address`; `@Valid`, `@NotBlank` và `@Size` kiểm tra dữ liệu đầu vào. |
| Output | `OrderResponse` chỉ công bố các trường được chọn, thay vì trả trực tiếp toàn bộ entity `Order`. |

Client không thể dùng request này để tự đổi `tenantId`, `ownerId`, `totalPrice` hoặc `status`, vì các trường đó không nằm trong DTO. Trong hệ thống thực tế, cần bổ sung kiểm tra định dạng địa chỉ, quy tắc nghiệp vụ, xử lý lỗi và kiểm thử phù hợp với yêu cầu của sản phẩm.

## 6. Kiểm thử bảo mật theo từng lớp

Kiểm thử nên tập trung vào các trường hợp vượt qua ranh giới quyền và dữ liệu, không chỉ kiểm tra request thành công.

| Lớp | Trường hợp cần thử | Kết quả mong đợi |
| --- | --- | --- |
| Identity | Thiếu token, token hết hạn, sai issuer hoặc audience, chữ ký không hợp lệ | Từ chối xác thực; không xử lý nghiệp vụ như một identity hợp lệ. |
| Authorization chức năng | Người dùng có token hợp lệ nhưng thiếu scope/role cần thiết | Từ chối hành động. |
| Authorization đối tượng | Người dùng A thay ID để đọc hoặc sửa tài nguyên của người dùng B; tenant A truy cập dữ liệu tenant B | Không truy cập được tài nguyên ngoài phạm vi được cấp. |
| Authorization thuộc tính | Gửi thêm `role`, `ownerId`, `tenantId`, `price` hoặc `status` vào request | Các trường không được phép không thể thay đổi dữ liệu. |
| Input | Thiếu trường, sai kiểu, chuỗi quá dài, số ngoài miền, payload quá lớn, ký tự gây injection | Từ chối hoặc xử lý an toàn theo hợp đồng API; không làm hỏng truy vấn hay hệ thống. |
| SSRF | URL trỏ đến loopback, private IP, link-local, địa chỉ sau redirect hoặc đích thay đổi qua DNS | Request bị chặn theo chính sách đích đến. |
| Resource abuse | Page size rất lớn, batch quá nhiều phần tử, gọi dồn dập hoặc thao tác tốn kém lặp lại | Áp dụng giới hạn và trả phản hồi phù hợp. |
| Output | Đọc response và log bằng tài khoản có quyền khác nhau; kiểm tra lỗi và header | Không lộ trường nhạy cảm, credential, stack trace hoặc dữ liệu ngoài phạm vi. |

Với trường hợp tài nguyên không thuộc quyền của người gọi, hệ thống có thể trả `403` hoặc `404` tùy chính sách che giấu sự tồn tại. Điều quan trọng là hành vi nhất quán và không làm lộ dữ liệu.

## 7. Giám sát và vận hành

Kiểm soát bảo mật cần được quan sát sau khi API đi vào hoạt động. Log và metric có thể ghi nhận identity hoặc client ID, route template, hành động, quyết định cho phép/từ chối, tenant, mã tài nguyên phù hợp, thời điểm, địa chỉ nguồn theo chính sách và correlation ID. Không ghi token, mật khẩu hay payload nhạy cảm nguyên vẹn.

Các tín hiệu nên theo dõi gồm tỷ lệ `401` và `403` tăng bất thường, nhiều lần thử truy cập các ID liên tiếp, lỗi validation tăng đột biến, lưu lượng `429`, request có thời gian xử lý dài và hoạt động gọi ra ngoài đến đích không mong đợi. Cần kết hợp cảnh báo với quy trình điều tra, giới hạn quyền truy cập log và chính sách lưu trữ dữ liệu.

## 8. Checklist khi thiết kế một endpoint

Trước khi đưa endpoint vào sử dụng, hãy xác định:

- [ ] Những loại identity nào được phép gọi endpoint và credential được xác minh ra sao?
- [ ] Quyền chức năng nào là bắt buộc? Quyền trên từng đối tượng và từng trường được kiểm tra ở đâu?
- [ ] Dữ liệu nào được phép nhận? Schema, miền giá trị và quy tắc nghiệp vụ đã được kiểm tra chưa?
- [ ] Endpoint có truy cập URL, file, truy vấn hoặc tài nguyên bên ngoài theo dữ liệu người dùng cung cấp không? SSRF và giới hạn tài nguyên đã được xử lý chưa?
- [ ] Response chỉ chứa trường cần thiết cho đúng identity và mục đích sử dụng chưa?
- [ ] Các trường hợp thiếu quyền, truy cập chéo người dùng/tenant, input sai, lạm dụng tài nguyên và rò rỉ output đã được kiểm thử chưa?
- [ ] Log, metric và cảnh báo có đủ thông tin điều tra mà không làm lộ bí mật không?

HTTPS bảo vệ dữ liệu trên đường truyền, còn identity, authorization, input và output bảo vệ cách API xác định người gọi, quyết định quyền, xử lý yêu cầu và tiết lộ dữ liệu. Một API an toàn cần kết hợp các lớp này theo đúng endpoint, đối tượng dữ liệu và luồng nghiệp vụ mà nó cung cấp.
