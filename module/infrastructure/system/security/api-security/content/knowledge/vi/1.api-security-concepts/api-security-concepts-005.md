# Mọi endpoint, method và object đều là bề mặt tấn công

Một API có thể dùng HTTPS, xác thực người dùng bằng token và vẫn để lộ dữ liệu hoặc cho phép thực hiện hành động trái phép. Nguyên nhân thường nằm ở chỗ hệ thống chỉ kiểm tra người gọi đã đăng nhập hay chưa, nhưng chưa kiểm tra đầy đủ người đó được phép gọi **endpoint nào**, dùng **HTTP method nào** và thao tác trên **object cùng thuộc tính nào**.

Trong API Security, cần xem mỗi request là một tổ hợp gồm đường dẫn, phương thức, danh tính, dữ liệu đầu vào, object được tham chiếu và trạng thái nghiệp vụ. Mỗi thành phần đều có thể trở thành điểm mà kẻ tấn công khai thác. Vì vậy, thiết kế bảo mật phải đi theo từng endpoint, từng thao tác và từng object; HTTPS và đăng nhập chỉ là những lớp bảo vệ ban đầu.

## 1. Nhìn bề mặt tấn công qua ba lớp

### Endpoint: API đang cung cấp khả năng nào?

Endpoint là điểm truy cập một chức năng của hệ thống, thường được nhận diện bằng đường dẫn và phiên bản API, chẳng hạn:

```http
GET /api/v1/orders
GET /api/v1/orders/{orderId}
POST /api/v1/orders
GET /api/v1/admin/users
POST /api/v1/files/import
```

Mỗi endpoint có thể để lộ một khả năng khác nhau: đọc danh sách, xem chi tiết, tạo đơn hàng, tra cứu người dùng hoặc nhập tệp. Endpoint công khai, endpoint nội bộ, endpoint quản trị, webhook, callback, endpoint kiểm tra sức khỏe và endpoint phục vụ tài liệu đều cần được đưa vào danh mục kiểm kê. Một endpoint ít được giao diện chính sử dụng vẫn có thể bị gọi trực tiếp nếu nó còn được triển khai và có thể truy cập.

Không nên chỉ kiểm kê các đường dẫn mà frontend đang gọi. Hãy rà soát cả phiên bản cũ, route dành cho ứng dụng di động, API đối tác, endpoint thử nghiệm, chức năng quản trị và các route được bật theo cấu hình môi trường. Một endpoint bị quên vẫn là bề mặt tấn công nếu máy chủ còn phục vụ nó.

### HTTP method: người gọi được làm hành động gì?

Cùng một đường dẫn có thể cung cấp nhiều hành động. Ví dụ:

| Request | Ý nghĩa | Rủi ro cần kiểm soát |
|---|---|---|
| `GET /orders/{id}` | Đọc đơn hàng | Lộ đơn hàng của người khác hoặc tenant khác |
| `PATCH /orders/{id}` | Cập nhật một phần | Sửa thuộc tính không được phép như `ownerId`, `status`, `total` |
| `DELETE /orders/{id}` | Xóa đơn hàng | Người dùng thường xóa dữ liệu hoặc xóa nhầm object ngoài phạm vi |
| `POST /orders` | Tạo đơn hàng | Giả mạo giá, chủ sở hữu, trạng thái hoặc tạo hàng loạt |

Kiểm soát quyền ở cấp đường dẫn là chưa đủ. Việc được phép đọc một đơn hàng không đồng nghĩa được phép sửa hoặc xóa đơn hàng đó. Tương tự, quyền cập nhật hồ sơ cá nhân không tự động cấp quyền thay đổi vai trò, trạng thái tài khoản hay thông tin thanh toán.

Các method phổ biến có ý nghĩa bảo mật khác nhau:

- `GET` và `HEAD` thường dùng để đọc. Chúng vẫn có thể làm lộ dữ liệu nhạy cảm, kích hoạt truy vấn tốn kém hoặc gây tác dụng phụ nếu ứng dụng thiết kế sai.
- `POST` thường tạo tài nguyên hoặc thực hiện một hành động. Cần kiểm tra quyền tạo, dữ liệu được phép gửi, giới hạn số lượng và khả năng gửi lặp.
- `PUT` thường thay thế biểu diễn của tài nguyên; `PATCH` thường cập nhật một phần. Cả hai cần quy định rõ thuộc tính nào người gọi được sửa.
- `DELETE` cần kiểm tra quyền xóa trên đúng object, điều kiện trạng thái và tác động dây chuyền đến dữ liệu liên quan.
- `OPTIONS` và `HEAD` cũng phải được cấu hình có chủ đích. CORS preflight hoặc việc ẩn một method khỏi tài liệu API không thay thế kiểm tra quyền trên request thực tế.

Không dựa vào việc giao diện không hiển thị nút thao tác hoặc tài liệu API không liệt kê method để coi hành động đó đã được bảo vệ. Máy chủ phải từ chối method không được hỗ trợ và kiểm tra quyền ở phía máy chủ cho mọi method được hỗ trợ. Nếu hệ thống có method override qua header hoặc tham số, cần tính cả cơ chế đó khi đánh giá bề mặt tấn công.

### Object: dữ liệu nào đang được truy cập hoặc thay đổi?

Object là tài nguyên cụ thể mà request nhắm tới, ví dụ đơn hàng `orderId=8f...`, hồ sơ người dùng, hóa đơn, tệp, tài khoản hoặc bản ghi thuộc một tổ chức. Object còn có các thuộc tính và quan hệ: chủ sở hữu, tenant, trạng thái, giá trị thanh toán, danh sách mặt hàng, vai trò và các object lồng bên trong.

Một người dùng có thể được phép gọi `GET /orders/{orderId}` nhưng chỉ được xem đơn hàng của mình. Người đó cũng có thể được phép cập nhật địa chỉ giao hàng nhưng không được thay `customerId`, `paymentStatus` hoặc `totalAmount`. Vì thế, kiểm tra quyền phải xét cả object cụ thể và từng thuộc tính có thể đọc hoặc ghi.

Object không chỉ được truyền qua path parameter. Nó có thể xuất hiện trong query string, JSON body, header, cookie, tên tệp, trường lồng nhau hoặc danh sách ID trong một request hàng loạt. Mọi tham chiếu object do client cung cấp đều cần được xem là dữ liệu không đáng tin cậy.

## 2. Xác thực không đồng nghĩa với phân quyền

Xác thực (authentication) trả lời câu hỏi: **Ai đang gửi request?** Ví dụ, token hợp lệ cho biết request thuộc về một tài khoản đã đăng nhập.

Phân quyền (authorization) trả lời câu hỏi: **Danh tính đó được phép thực hiện hành động nào trên tài nguyên nào?** Một quyết định phân quyền tốt thường cần kết hợp ít nhất ba yếu tố:

1. **Danh tính và phạm vi:** người dùng, service account, tenant hoặc tổ chức nào đang gọi?
2. **Chức năng:** danh tính đó có quyền thực hiện hành động như `orders:read`, `orders:update` hay `users:delete` không?
3. **Object và ngữ cảnh:** object có thuộc phạm vi quản lý của danh tính không, trạng thái hiện tại có cho phép hành động không, và có điều kiện nghiệp vụ nào phải thỏa mãn không?

Vai trò như `USER`, `MANAGER`, `ADMIN` có thể hữu ích, nhưng một vai trò chung thường không diễn tả đủ quyền trên từng object. Trong hệ thống nhiều tenant, phải xác định tenant từ danh tính đã được xác thực và áp dụng nó vào truy vấn dữ liệu. Không tin `tenantId`, `ownerId` hoặc `userId` do client tự gửi để quyết định phạm vi truy cập.

Một request chỉ được xử lý khi tất cả điều kiện cần thiết đều đạt. Có token hợp lệ không có nghĩa là được truy cập mọi endpoint; có quyền gọi chức năng không có nghĩa là được thao tác trên mọi object; có quyền sửa object cũng không có nghĩa là được sửa mọi thuộc tính của nó.

## 3. Kiểm soát quyền ở cấp object: ngăn BOLA và IDOR

BOLA (Broken Object Level Authorization), thường được gọi cùng nhóm vấn đề IDOR (Insecure Direct Object Reference), xảy ra khi ứng dụng nhận diện được người gọi nhưng không xác minh người đó có quyền trên object được yêu cầu.

Giả sử người dùng A có thể xem đơn hàng của mình:

```http
GET /api/v1/orders/1001
Authorization: Bearer <token-cua-A>
```

Nếu người dùng A thay `1001` thành `1002` và máy chủ trả về đơn hàng của người dùng B, endpoint đang thiếu kiểm soát quyền ở cấp object. ID khó đoán, UUID hoặc ID được mã hóa không giải quyết được lỗi này. Kẻ tấn công có thể lấy ID từ lịch sử, log phía client, liên kết chia sẻ hoặc một endpoint khác.

Một cách triển khai dễ mắc lỗi là tìm object trước rồi chỉ kiểm tra token:

```java
// Không đủ an toàn nếu chỉ kiểm tra người gọi đã đăng nhập.
Order order = orderRepository.findById(orderId)
    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
return orderMapper.toResponse(order);
```

Hãy ràng buộc truy vấn với phạm vi mà người gọi được phép truy cập. Ví dụ Spring Boot dưới đây lấy chủ thể từ JWT đã xác thực và tìm đơn hàng theo cả ID lẫn chủ sở hữu:

```java
@GetMapping("/api/v1/orders/{orderId}")
public OrderResponse getOrder(
        @PathVariable UUID orderId,
        @AuthenticationPrincipal Jwt jwt) {

    UUID customerId = UUID.fromString(jwt.getSubject());

    Order order = orderRepository
        .findByIdAndCustomerId(orderId, customerId)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

    return orderMapper.toResponse(order);
}
```

`findByIdAndCustomerId` biểu diễn truy vấn đã giới hạn theo chủ sở hữu. Với hệ thống nhiều tenant, truy vấn thường cần thêm điều kiện tenant; với quản trị viên hoặc nhân viên hỗ trợ, cần một chính sách riêng có kiểm tra vai trò, phạm vi và mục đích truy cập. Không nên thêm một nhánh `ADMIN` rộng đến mức bỏ qua mọi ràng buộc mà không có quy tắc rõ ràng.

Áp dụng cùng nguyên tắc cho thao tác cập nhật và xóa. Kiểm tra quyền trước khi thay đổi trạng thái, và thực hiện việc kiểm tra cùng cập nhật trong một giao dịch phù hợp để tránh tình trạng quyền hoặc trạng thái object thay đổi giữa hai bước. Với thao tác hàng loạt, phải kiểm tra từng object trong tập ID; không giả định rằng quyền trên một phần tử đại diện cho quyền trên cả danh sách.

## 4. Kiểm soát quyền ở cấp chức năng: ngăn BFLA

BFLA (Broken Function Level Authorization) xảy ra khi người dùng có thể gọi một chức năng vượt quá quyền được cấp. Ví dụ, một tài khoản thông thường gọi được `DELETE /api/v1/users/{id}` hoặc truy cập `GET /api/v1/admin/reports` dù giao diện không cung cấp các thao tác này.

Mỗi endpoint và method cần gắn với quyền chức năng cụ thể. Trong Spring Security, có thể dùng quy tắc ở tầng HTTP hoặc annotation tại service/controller, tùy kiến trúc:

```java
@PreAuthorize("hasAuthority('users:delete')")
@DeleteMapping("/api/v1/users/{userId}")
public void deleteUser(@PathVariable UUID userId) {
    userService.deleteUser(userId);
}
```

Đoạn mã trên minh họa kiểm tra quyền chức năng. Service vẫn cần kiểm tra người gọi có được xóa **userId cụ thể** hay không, cũng như các điều kiện nghiệp vụ như không cho phép xóa tài khoản quản trị cuối cùng. Quyền chức năng và quyền object giải quyết hai câu hỏi khác nhau nên thường phải cùng tồn tại.

Hãy rà soát mọi method của một endpoint. Ví dụ, quyền `orders:read` không nên vô tình cho phép `PATCH` hoặc `DELETE`; quyền `users:read` không nên được dùng thay cho `users:export`. Nếu có quyền theo phạm vi, hãy phân biệt rõ quyền xem một bản ghi, xem danh sách trong tổ chức, xuất dữ liệu và quản trị toàn hệ thống.

## 5. Bảo vệ thuộc tính: ngăn BOPLA và mass assignment

BOPLA (Broken Object Property Level Authorization) xảy ra khi ứng dụng không kiểm soát đúng thuộc tính mà người gọi được đọc hoặc ghi. Một dạng phổ biến là mass assignment: ứng dụng ánh xạ trực tiếp JSON từ client vào entity hoặc object miền nghiệp vụ, khiến client có thể gửi thêm các trường ngoài dự kiến.

Ví dụ request cập nhật hồ sơ bình thường chỉ nên cho phép đổi tên hiển thị:

```http
PATCH /api/v1/profile
Content-Type: application/json

{
  "displayName": "An Nguyen",
  "role": "ADMIN",
  "enabled": true
}
```

Nếu controller bind JSON trực tiếp vào entity `User`, các trường `role` hoặc `enabled` có thể bị cập nhật ngoài ý muốn. Cách an toàn hơn là dùng DTO chỉ chứa các trường được phép nhận:

```java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName
) {}
```

```java
@PatchMapping("/api/v1/profile")
public ProfileResponse updateProfile(
        @Valid @RequestBody UpdateProfileRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    UUID userId = UUID.fromString(jwt.getSubject());
    User user = userService.updateDisplayName(userId, request.displayName());
    return profileMapper.toResponse(user);
}
```

Service chỉ cập nhật thuộc tính được cho phép sau khi xác định người dùng từ danh tính đã xác thực. Các thuộc tính nhạy cảm như `role`, `ownerId`, `tenantId`, `balance`, `price`, `status` và `isVerified` cần luồng nghiệp vụ riêng, kiểm tra quyền riêng hoặc chỉ được hệ thống tự thiết lập.

Kiểm soát thuộc tính khi **đọc** cũng quan trọng như khi ghi. Không trả về toàn bộ entity chỉ vì người gọi được xem object. Dùng response DTO hoặc projection để chỉ xuất các trường cần thiết. Ví dụ, người mua có thể xem trạng thái đơn hàng nhưng không cần thấy ghi chú nội bộ, dữ liệu thanh toán đầy đủ hoặc thông tin cá nhân của nhân viên xử lý.

Với object lồng nhau, hãy kiểm tra từng tham chiếu và từng thuộc tính. Một request cập nhật đơn hàng có thể chứa `shippingAddress`, `items`, `discountCode` và `paymentMethod`; quyền cập nhật địa chỉ không tự động cấp quyền thay đổi giá sản phẩm hoặc người sở hữu đơn hàng.

## 6. Xác thực dữ liệu đầu vào và kiểm soát SSRF

Path, query, header, cookie, JSON body, multipart form và nội dung tệp đều có thể do bên ngoài kiểm soát. Validation cần kiểm tra cả định dạng lẫn ý nghĩa:

- Kiểu dữ liệu, độ dài, miền giá trị, định dạng và giới hạn số phần tử.
- ID có tồn tại và object có nằm trong phạm vi được phép truy cập hay không.
- Trạng thái hiện tại có cho phép chuyển sang trạng thái mới hay không.
- Giá, số lượng, loại tiền, thời gian và các giá trị tính toán có hợp lệ theo quy tắc nghiệp vụ không.
- Content-Type, kích thước tệp, định dạng thực tế và nội dung tải lên có phù hợp không.

Validation không thay thế phân quyền. Một `orderId` đúng định dạng vẫn có thể thuộc người khác; một `role` hợp lệ vẫn có thể là giá trị người dùng không được phép đặt.

Đặc biệt chú ý endpoint nhận URL để tải ảnh, nhập dữ liệu, kiểm tra webhook hoặc tạo bản xem trước. Nếu máy chủ tự truy cập URL do client cung cấp, chức năng đó có thể trở thành SSRF (Server-Side Request Forgery). Kẻ tấn công có thể tìm cách khiến máy chủ gọi địa chỉ nội bộ, dịch vụ quản trị hoặc metadata endpoint trong hạ tầng.

Để giảm rủi ro SSRF:

1. Ưu tiên danh sách host hoặc dịch vụ đích được phép thay vì chấp nhận mọi URL.
2. Chỉ cho phép scheme cần thiết, thường là `https`; từ chối scheme không phục vụ nghiệp vụ.
3. Phân giải DNS và kiểm tra địa chỉ IP đích, chặn loopback, private, link-local và các dải địa chỉ hạ tầng nhạy cảm theo chính sách triển khai.
4. Kiểm tra lại đích sau redirect và xử lý cẩn thận thay đổi DNS để tránh kiểm tra một địa chỉ nhưng kết nối tới địa chỉ khác.
5. Đặt timeout, giới hạn kích thước phản hồi và số lần redirect; giới hạn quyền mạng outbound của dịch vụ.

Không chỉ dựa vào kiểm tra chuỗi URL. Việc xác thực phải áp dụng cho địa chỉ mạng thực sự mà máy chủ sẽ kết nối.

## 7. Ngăn lạm dụng tài nguyên và request hàng loạt

Một endpoint được phân quyền đúng vẫn có thể bị lạm dụng để tiêu tốn CPU, bộ nhớ, kết nối cơ sở dữ liệu, băng thông hoặc chi phí dịch vụ bên ngoài. Các điểm thường bị bỏ sót gồm:

- API danh sách cho phép `limit` quá lớn hoặc không giới hạn phân trang.
- Bộ lọc, tìm kiếm, sắp xếp hoặc truy vấn lồng nhau tạo câu truy vấn rất tốn kém.
- Endpoint xử lý tệp cho phép upload quá lớn hoặc giải nén dữ liệu vượt giới hạn.
- API batch nhận hàng nghìn ID và thực hiện nhiều thao tác trong một request.
- Chức năng gửi OTP, email, SMS, tạo báo cáo hoặc gọi dịch vụ bên thứ ba có thể bị gọi liên tục.
- Request có thể giữ kết nối lâu, tạo nhiều tác vụ đồng thời hoặc kích hoạt biểu thức chính quy tốn thời gian.

Áp dụng giới hạn theo từng loại tài nguyên: kích thước request, số phần tử, kích thước trang tối đa, timeout, độ sâu truy vấn, số tác vụ đồng thời, quota và rate limit. Rate limit nên cân nhắc danh tính, tenant, endpoint và địa chỉ nguồn; chỉ giới hạn theo IP có thể gây ảnh hưởng người dùng hợp lệ dùng chung mạng, trong khi chỉ giới hạn theo tài khoản có thể bỏ sót request chưa xác thực.

Với thao tác tạo thanh toán, đặt hàng hoặc gửi yêu cầu có thể được retry, hãy thiết kế idempotency key và quy tắc chống xử lý trùng. Idempotency giúp retry an toàn nhưng không thay thế rate limit hay kiểm tra quyền. Cần xác định thời gian lưu khóa, phạm vi khóa và cách xử lý khi cùng khóa được gửi với nội dung khác nhau.

## 8. Bảo vệ luồng nghiệp vụ, không chỉ từng request riêng lẻ

Kẻ tấn công có thể sử dụng các request hợp lệ theo thứ tự bất thường để phá vỡ quy trình. Ví dụ:

1. Tạo đơn hàng với số lượng lớn.
2. Gửi request thay đổi giá hoặc mã giảm giá sau khi hệ thống đã tính tổng tiền.
3. Gọi endpoint xác nhận thanh toán mà không có bằng chứng thanh toán hợp lệ.
4. Gửi lại request hoàn tiền nhiều lần hoặc đồng thời từ nhiều phiên.

Mỗi request riêng lẻ có thể vượt qua validation cơ bản, nhưng chuỗi thao tác vẫn tạo ra kết quả sai. Hãy mô hình hóa trạng thái và chuyển trạng thái hợp lệ ở phía máy chủ. Ví dụ, đơn hàng chỉ được chuyển từ `PENDING_PAYMENT` sang `PAID` sau khi xác minh kết quả từ cổng thanh toán; không nhận `status: "PAID"` từ request cập nhật chung của client.

Các quy tắc quan trọng nên được thực thi trong service/domain layer và giao dịch cơ sở dữ liệu phù hợp. Với tồn kho, số dư, phiếu giảm giá và hoàn tiền, cần xử lý cạnh tranh đồng thời để tránh hai request cùng tiêu thụ một tài nguyên hoặc thực hiện một hành động nhiều lần. Với webhook, xác minh chữ ký, nguồn gửi, timestamp và cơ chế chống phát lại theo giao thức của nhà cung cấp.

## 9. Bảo vệ dữ liệu trên request, response và log

HTTPS bảo vệ dữ liệu khi truyền trên đường mạng, nhưng không ngăn API trả nhầm dữ liệu cho người đã đăng nhập. Mỗi response cần tuân theo nguyên tắc chỉ trả dữ liệu cần thiết cho chức năng và người nhận. Hãy chú ý thông tin cá nhân, token, khóa bí mật, thông tin thanh toán, dữ liệu nội bộ và trường kỹ thuật không nên công khai.

Không ghi access token, mật khẩu, khóa API hoặc toàn bộ payload nhạy cảm vào log. Log phục vụ điều tra nên ghi nhận các dữ kiện cần thiết như request ID, route template, danh tính/tenant ở dạng phù hợp, hành động, kết quả phân quyền và mã lỗi. Nếu cần ghi object ID hoặc dữ liệu đầu vào, hãy áp dụng chính sách che, rút gọn và thời hạn lưu giữ.

Thông báo lỗi cũng cần được kiểm soát. Không trả stack trace, câu SQL, đường dẫn nội bộ hoặc cấu hình hệ thống cho client. Có thể dùng phản hồi `403 Forbidden` khi người gọi đã được xác thực nhưng không có quyền, hoặc `404 Not Found` khi chính sách cần tránh tiết lộ sự tồn tại của object; điều quan trọng là áp dụng nhất quán và không để nội dung phản hồi vô tình xác nhận dữ liệu nhạy cảm.

## 10. Lập ma trận endpoint–method–object

Một cách thực tế để biến nguyên tắc trên thành công việc là lập ma trận bảo mật cho API. Ví dụ:

| Endpoint | Method | Object/thuộc tính | Ai được phép? | Kiểm tra bắt buộc |
|---|---|---|---|---|
| `/orders/{id}` | `GET` | Đơn hàng, địa chỉ, trạng thái | Chủ đơn; nhân viên có phạm vi hỗ trợ | Quyền đọc chức năng, owner/tenant, trường được phép trả |
| `/orders/{id}` | `PATCH` | Địa chỉ giao hàng | Chủ đơn khi đơn còn cho phép sửa | Quyền cập nhật, owner/tenant, trạng thái, DTO allowlist |
| `/orders/{id}` | `DELETE` | Đơn hàng | Vai trò được cấp quyền theo chính sách | Quyền xóa, owner/tenant, điều kiện nghiệp vụ, tác động liên quan |
| `/admin/users/{id}` | `DELETE` | Tài khoản người dùng | Quản trị viên phù hợp | Quyền chức năng, phạm vi quản trị, quy tắc bảo vệ tài khoản đặc biệt |
| `/files/import` | `POST` | Tệp và dữ liệu nhập | Người dùng có quyền nhập trong tenant | Quyền chức năng, loại/kích thước tệp, kiểm tra nội dung và giới hạn tài nguyên |
| `/previews` | `POST` | URL máy chủ sẽ truy cập | Vai trò được dùng chức năng xem trước | Quyền chức năng, allowlist đích, kiểm tra DNS/IP, timeout và giới hạn phản hồi |

Với mỗi dòng, cần ghi rõ nguồn danh tính, phạm vi tenant, thuộc tính đọc/ghi, điều kiện trạng thái, giới hạn tài nguyên và dữ liệu có thể xuất hiện trong response. Ma trận nên được cập nhật khi thêm endpoint, method, trường dữ liệu hoặc luồng nghiệp vụ mới.

## 11. Kiểm thử bảo mật theo từng lớp

Kiểm thử không nên chỉ xác nhận request hợp lệ trả `200 OK`. Hãy kiểm tra các trường hợp bị từ chối và các tổ hợp danh tính–method–object–thuộc tính.

| Lớp | Ca kiểm thử nên có |
|---|---|
| Endpoint | Người chưa xác thực gọi endpoint cần đăng nhập; người dùng thường gọi endpoint quản trị; route cũ hoặc route nội bộ còn truy cập được |
| Method | Cùng một endpoint với `GET`, `POST`, `PATCH`, `DELETE`; method không hỗ trợ; method override nếu hệ thống bật |
| Object | Người dùng A đọc, sửa và xóa object của B; truy cập object ở tenant khác; gửi danh sách ID trộn object được phép và không được phép |
| Property | Gửi thêm `role`, `ownerId`, `tenantId`, `status`, `balance`; thử đọc trường nội bộ trong response; thử cập nhật object lồng nhau |
| Validation/SSRF | ID sai định dạng, dữ liệu vượt giới hạn, URL tới địa chỉ nội bộ, redirect tới đích bị chặn, phản hồi quá lớn hoặc quá chậm |
| Tài nguyên | Trang cực lớn, batch lớn, upload lớn, gọi lặp endpoint tốn kém, request đồng thời và retry |
| Luồng nghiệp vụ | Bỏ qua bước, đổi thứ tự trạng thái, gửi lại thanh toán/hoàn tiền, sử dụng mã giảm giá nhiều lần, cập nhật đồng thời |

Nên có test tự động cho các quy tắc phân quyền quan trọng, đặc biệt là quyền object và property. Có thể tạo dữ liệu kiểm thử với hai người dùng thuộc hai tenant, nhiều vai trò và object ở các trạng thái khác nhau. Kiểm thử cả response body, số bản ghi bị thay đổi và side effect; một request trả `403` nhưng vẫn ghi dữ liệu là lỗi bảo mật nghiêm trọng.

Khi thêm endpoint hoặc method mới, yêu cầu review ma trận quyền và bổ sung test tương ứng trong quy trình pull request. Kiểm thử động, fuzzing và rà soát cấu hình có thể bổ sung cho test ứng dụng, nhưng không thay thế việc xác định chính sách nghiệp vụ chính xác.

## 12. Giám sát và phản ứng khi API bị lạm dụng

Giám sát nên phát hiện được các dấu hiệu như một tài khoản thử nhiều object ID, nhiều request bị từ chối trên endpoint quản trị, lượng request tăng bất thường, batch lớn, nhiều lần retry thanh toán, hoặc dịch vụ liên tục truy cập đích mạng không nằm trong chính sách. Tùy mức độ nhạy cảm, có thể cảnh báo theo người dùng, tenant, route template và loại hành động.

Kết hợp log có cấu trúc, metric, trace và audit event cho hành động quan trọng. Đảm bảo có request/correlation ID để nối các bước của một luồng; bảo vệ log khỏi truy cập trái phép và tránh đưa bí mật vào dữ liệu quan sát. Khi phát hiện bất thường, hệ thống cần có cách giới hạn lưu lượng, thu hồi thông tin xác thực, khóa chức năng hoặc cô lập dịch vụ theo quy trình vận hành.

## 13. Checklist khi thiết kế hoặc review một API

- [ ] Endpoint đã được kiểm kê, có mục đích rõ ràng và không còn route thử nghiệm hoặc phiên bản cũ không cần thiết.
- [ ] Mỗi HTTP method được hỗ trợ có quyền chức năng riêng và hành vi được định nghĩa rõ.
- [ ] Danh tính và tenant được lấy từ ngữ cảnh xác thực đáng tin cậy, không lấy quyền từ ID client tự khai báo.
- [ ] Mọi object được kiểm tra quyền truy cập theo chủ sở hữu, tenant, quan hệ và ngữ cảnh nghiệp vụ.
- [ ] DTO đầu vào chỉ cho phép các thuộc tính được sửa; response chỉ trả các thuộc tính được phép đọc.
- [ ] Path, query, header, body, tệp và URL ngoài đều được validation theo kiểu, miền giá trị và ngữ nghĩa.
- [ ] Endpoint có khả năng truy cập URL từ máy chủ đã có biện pháp chống SSRF và giới hạn kết nối outbound.
- [ ] Có giới hạn request, trang, batch, upload, thời gian xử lý, đồng thời và tần suất phù hợp.
- [ ] Luồng nghiệp vụ kiểm soát chuyển trạng thái, retry, phát lại và cạnh tranh đồng thời.
- [ ] Test bao gồm cả truy cập hợp lệ lẫn truy cập chéo người dùng/tenant, sai method, sai thuộc tính và lạm dụng tài nguyên.
- [ ] Log, metric và audit event đủ hỗ trợ phát hiện sự cố mà không làm lộ bí mật hoặc dữ liệu nhạy cảm.

## Kết luận

Mỗi endpoint phơi bày một khả năng, mỗi HTTP method xác định một hành động, và mỗi object cùng thuộc tính xác định dữ liệu mà hành động đó tác động tới. API Security chỉ đầy đủ khi máy chủ xác minh cả ba lớp trong ngữ cảnh của từng request, đồng thời kiểm soát validation, luồng nghiệp vụ, tài nguyên và dữ liệu được trả về. HTTPS bảo vệ đường truyền và authentication xác định người gọi; chính sách authorization chi tiết mới quyết định người đó được làm gì trên tài nguyên nào.
