# Bảo vệ API xuyên suốt thiết kế, triển khai và vận hành

API là ranh giới mà qua đó ứng dụng nhận yêu cầu, đọc hoặc thay đổi dữ liệu và kích hoạt nghiệp vụ. Vì vậy, bảo mật API phải bảo vệ được từng thao tác, từng đối tượng dữ liệu và từng bước trong luồng nghiệp vụ. Việc người dùng đã đăng nhập, request đi qua HTTPS hay API Gateway đã xác thực token chỉ giải quyết một phần vấn đề. Một API vẫn có thể để lộ dữ liệu của khách hàng khác, cho phép gọi chức năng quản trị, nhận dữ liệu đầu vào nguy hiểm hoặc tiêu tốn tài nguyên ngoài dự kiến.

Trong bài này, **API Security** được xem là tập hợp các quyết định và biện pháp bảo vệ xuyên suốt vòng đời API: từ thiết kế hợp đồng, xác thực, phân quyền, kiểm tra dữ liệu, xử lý kết nối ra ngoài, bảo vệ tài nguyên đến kiểm thử và giám sát khi chạy thật. Trọng tâm là thiết kế quyền theo endpoint, đối tượng dữ liệu và luồng nghiệp vụ, thay vì chỉ dựa vào đăng nhập hoặc HTTPS.

Sau bài học, người đọc có thể:

- Phân tích bề mặt tấn công của một API theo endpoint, chức năng, đối tượng và thuộc tính dữ liệu.
- Phân biệt xác thực với phân quyền, đồng thời nhận diện lỗi phân quyền mức chức năng, đối tượng và thuộc tính.
- Xây dựng quy tắc validation cho dữ liệu đầu vào và giới hạn việc dữ liệu không đáng tin cậy đi vào nghiệp vụ.
- Nhận diện và giảm thiểu SSRF, lạm dụng tài nguyên và các rủi ro rò rỉ dữ liệu.
- Lập kế hoạch kiểm thử, ghi log và giám sát để phát hiện hành vi bất thường sau khi triển khai.

## 1. Bắt đầu từ tài sản, ranh giới tin cậy và luồng nghiệp vụ

Trước khi chọn thư viện bảo mật, hãy xác định API đang bảo vệ điều gì. Tài sản có thể là hồ sơ khách hàng, đơn hàng, số dư, tài liệu nội bộ, thông tin định danh, quyền quản trị hoặc khả năng thực hiện một giao dịch. Một endpoint thường có nhiều rủi ro hơn việc chỉ đọc hay ghi một URL: nó có thể cho phép xem dữ liệu, thay đổi trạng thái, chuyển tiền, gửi lời mời, tải tệp hoặc yêu cầu hệ thống truy cập một địa chỉ mạng khác.

Với mỗi luồng nghiệp vụ, hãy trả lời các câu hỏi:

1. Ai hoặc hệ thống nào được phép gọi API? Danh tính đó được xác minh bằng cơ chế nào?
2. Danh tính được phép thực hiện chức năng gì? Quyền có phụ thuộc vai trò, phạm vi OAuth, tổ chức, trạng thái tài khoản hay điều kiện nghiệp vụ không?
3. Danh tính được phép thao tác trên đối tượng nào? Ví dụ, người dùng chỉ được đọc đơn hàng thuộc tài khoản của mình hay nhân viên hỗ trợ được đọc đơn hàng trong nhóm được phân công?
4. Những thuộc tính nào được phép đọc hoặc cập nhật? Một người có quyền sửa hồ sơ không đồng nghĩa được sửa `role`, `ownerId`, `tenantId` hoặc `approvalStatus`.
5. Dữ liệu nào đi vào hệ thống từ bên ngoài? API có truy cập URL, tệp, webhook hoặc dịch vụ bên thứ ba theo dữ liệu do người gọi cung cấp không?
6. Tài nguyên nào có thể bị tiêu thụ? Một request có thể tạo hàng nghìn bản ghi, chạy truy vấn lớn, tải tệp rất nặng hoặc kích hoạt tác vụ tốn CPU không?

Lập sơ đồ luồng dữ liệu và đánh dấu ranh giới tin cậy: Internet, API Gateway, dịch vụ ứng dụng, cơ sở dữ liệu, hàng đợi, kho tệp và dịch vụ bên ngoài. Dữ liệu từ client, webhook hoặc hệ thống khác đều phải được xem là không đáng tin cậy cho đến khi được xác minh. Không nên mặc định rằng request đến từ mạng nội bộ là an toàn; dịch vụ nội bộ có thể bị xâm nhập hoặc bị lợi dụng làm điểm trung chuyển.

Một cách phân tích hữu ích là lập ma trận endpoint. Ma trận này buộc nhóm phát triển mô tả rõ ai được làm gì trên loại dữ liệu nào, đồng thời trở thành đầu vào cho code review và kiểm thử.

| Endpoint | Chức năng | Đối tượng cần kiểm tra | Quyền/điều kiện chính |
|---|---|---|---|
| `GET /orders/{id}` | Xem đơn hàng | Đơn hàng có thuộc người dùng hoặc phạm vi được giao không? | `order:read` và quyền truy cập đúng đơn hàng |
| `POST /orders` | Tạo đơn hàng | Khách hàng, sản phẩm và giá có hợp lệ không? | `order:create`; kiểm tra trạng thái và giới hạn mua |
| `PATCH /orders/{id}` | Sửa đơn hàng | Đơn hàng còn được phép sửa không? | `order:update`; chỉ cho sửa các trường được phép |
| `POST /orders/{id}/approve` | Duyệt đơn hàng | Người duyệt có thẩm quyền và không tự duyệt trái quy tắc không? | `order:approve`; kiểm tra phân tách nhiệm vụ và trạng thái |
| `GET /admin/users` | Tra cứu người dùng | Người gọi có thuộc nhóm quản trị phù hợp không? | Quyền quản trị riêng, có thể kèm phạm vi tổ chức |

Không nên dùng một quy tắc chung kiểu “đã đăng nhập thì được gọi API”. Quyền phải phù hợp với tác động của từng thao tác.

## 2. Xác thực: xác minh danh tính của bên gọi

**Xác thực (authentication)** trả lời câu hỏi “Ai đang gọi API?”. **Phân quyền (authorization)** trả lời “Danh tính này được phép làm gì trên dữ liệu nào?”. Hai bước liên quan chặt chẽ nhưng không thay thế cho nhau. Xác thực thành công chỉ tạo ra một danh tính đã được kiểm chứng; nó không tự động cấp quyền truy cập mọi endpoint hoặc mọi bản ghi.

Với API dùng access token, máy chủ cần kiểm tra tối thiểu:

- Chữ ký token hợp lệ theo khóa và thuật toán được cấu hình cho hệ thống. Không chấp nhận thuật toán tùy ý do token tự khai báo.
- `issuer` đúng nhà phát hành được tin cậy và `audience` đúng API nhận token.
- Token chưa hết hạn (`exp`) và, nếu được sử dụng, đã đến thời điểm hiệu lực (`nbf`).
- Các claim cần thiết có kiểu và giá trị hợp lệ; scope hoặc authority được ánh xạ theo chính sách của API.
- Khóa xác minh được quản lý và luân chuyển an toàn. Khi dùng JWKS, cần xử lý việc cập nhật khóa và cache theo hướng dẫn của nhà cung cấp định danh.

Access token dành cho API cần được phân biệt với ID token dành cho client đăng nhập người dùng. Không đưa token, API key hoặc thông tin xác thực vào URL vì URL thường xuất hiện trong lịch sử trình duyệt, proxy và log. Ưu tiên header `Authorization: Bearer ...` qua kết nối TLS.

API key hữu ích để nhận diện ứng dụng hoặc kiểm soát mức sử dụng, nhưng bản thân API key thường không chứng minh danh tính người dùng cuối và khó biểu đạt quyền chi tiết. Không dùng một API key dùng chung làm cơ chế phân quyền cho mọi khách hàng. Với giao tiếp máy-với-máy, cân nhắc OAuth 2.0 Client Credentials, thông tin xác thực có vòng đời ngắn, hoặc cơ chế danh tính dịch vụ phù hợp với hạ tầng.

Nếu dùng cookie để mang phiên đăng nhập, cần đặt thuộc tính `Secure`, `HttpOnly` và `SameSite` phù hợp; đồng thời đánh giá nguy cơ CSRF cho các thao tác thay đổi trạng thái. TLS bảo vệ dữ liệu trên đường truyền nhưng không sửa được token bị lộ, cấu hình xác thực sai hoặc quyền cấp quá rộng.

## 3. Phân quyền theo chức năng, đối tượng và thuộc tính

Phân quyền nên được kiểm tra ở phía máy chủ trên mỗi request. Không dựa vào nút giao diện bị ẩn, ID khó đoán, tham số do client gửi hoặc kiểm tra đã thực hiện ở một endpoint khác.

### 3.1. Quyền mức chức năng

Kiểm tra người gọi có được phép sử dụng chức năng tương ứng hay không. Ví dụ, `order:read`, `order:create` và `order:approve` là các quyền khác nhau. Người có quyền xem đơn hàng không mặc nhiên được duyệt đơn hàng. Các endpoint quản trị cần quyền riêng và nên được giới hạn theo vai trò, tổ chức hoặc điều kiện bổ sung.

RBAC (Role-Based Access Control) gán quyền qua vai trò như `CUSTOMER`, `SUPPORT` hoặc `ADMIN`. ABAC (Attribute-Based Access Control) quyết định dựa trên thuộc tính của chủ thể, đối tượng và ngữ cảnh, chẳng hạn nhân viên hỗ trợ chỉ được xem hồ sơ thuộc khu vực đang phụ trách. Có thể kết hợp hai mô hình: RBAC xác định quyền nền, ABAC giới hạn phạm vi thực tế.

### 3.2. Quyền mức đối tượng

Lỗi Broken Object Level Authorization (BOLA), trước đây thường được gọi là IDOR, xảy ra khi API kiểm tra người dùng đã đăng nhập nhưng không kiểm tra người đó có quyền trên đối tượng được yêu cầu hay không. Ví dụ, người dùng thay `/orders/1001` thành `/orders/1002` và đọc được đơn hàng của người khác.

Một biện pháp chắc chắn là đưa phạm vi quyền vào truy vấn lấy dữ liệu. Ví dụ minh họa với Spring Boot:

```java
@GetMapping("/orders/{id}")
@PreAuthorize("hasAuthority('order:read')")
public OrderResponse getOrder(
        @PathVariable UUID id,
        @AuthenticationPrincipal ApiPrincipal principal) {

    Order order = orderRepository
            .findByIdAndTenantId(id, principal.tenantId())
            .orElseThrow(OrderNotFoundException::new);

    return orderMapper.toResponse(order);
}
```

Trong ví dụ này, `ApiPrincipal` phải được tạo từ access token đã xác minh; `tenantId` lấy từ ngữ cảnh danh tính đáng tin cậy, không lấy từ query parameter hoặc body do client tự khai báo. Truy vấn giới hạn theo tenant ngay tại nơi tải đối tượng. Với hệ thống không đa tenant, có thể giới hạn theo `ownerId`, nhóm được phân công hoặc quan hệ quyền tương ứng.

Kiểm tra quyền cần diễn ra ở mọi đường truy cập đối tượng, kể cả khi đối tượng được lấy qua ID lồng nhau, tìm kiếm, tải tệp, export, tác vụ nền hoặc endpoint quản trị. Nếu chính sách yêu cầu che giấu sự tồn tại của đối tượng, có thể trả `404` cho cả trường hợp không tồn tại và không có quyền; nếu cần phân biệt, dùng `403` theo chính sách đã thống nhất. Điều quan trọng là không làm lộ dữ liệu qua thông báo lỗi hoặc thời gian xử lý.

### 3.3. Quyền mức thuộc tính

Broken Object Property Level Authorization xảy ra khi API trả về hoặc cho phép cập nhật thuộc tính mà người gọi không được phép truy cập. Ví dụ, endpoint cập nhật hồ sơ nhận trực tiếp entity từ JSON và vô tình cho phép client gửi thêm `role: "ADMIN"`, `tenantId` hoặc `verified: true`.

Hãy dùng request DTO chỉ chứa các trường được phép thay đổi, kiểm tra quyền theo từng trường nhạy cảm và tạo response DTO chỉ chứa dữ liệu được phép trả về. Tránh bind trực tiếp request vào entity của ORM. Quyền đọc và quyền ghi thuộc tính có thể khác nhau; một nhân viên có thể xem trạng thái phê duyệt nhưng không được thay đổi trạng thái đó.

### 3.4. Quyền theo trạng thái và luồng nghiệp vụ

Một người có quyền `order:update` vẫn không nhất thiết được sửa đơn hàng ở mọi thời điểm. Đơn đã giao có thể không được sửa; người tạo yêu cầu có thể không được tự phê duyệt; một giao dịch chỉ được hoàn tiền một lần. Vì vậy, phân quyền cần kết hợp kiểm tra trạng thái, chuyển trạng thái hợp lệ và quy tắc phân tách nhiệm vụ.

Thực hiện kiểm tra này trong lớp nghiệp vụ hoặc dịch vụ miền để mọi kênh gọi đều dùng chung chính sách. Với thao tác quan trọng, cần bảo đảm việc kiểm tra và cập nhật trạng thái có tính nguyên tử hoặc được bảo vệ bằng khóa/kiểm soát phiên bản để tránh hai request đồng thời vượt qua cùng một điều kiện.

## 4. Validation và xử lý dữ liệu không đáng tin cậy

Validation cần diễn ra ở ranh giới API trước khi dữ liệu đi sâu vào nghiệp vụ. Kiểm tra tối thiểu gồm:

- **Cấu trúc và kiểu:** JSON đúng schema, trường bắt buộc có mặt, kiểu dữ liệu chính xác, enum chỉ nhận giá trị đã định nghĩa.
- **Kích thước:** giới hạn độ dài chuỗi, số phần tử mảng, kích thước body, số trường lồng nhau và kích thước tệp.
- **Miền giá trị:** số dương khi phù hợp, ngày tháng hợp lệ, phân trang trong giới hạn, định dạng định danh đúng.
- **Quy tắc nghiệp vụ:** số lượng đặt mua không vượt tồn kho, ngày kết thúc sau ngày bắt đầu, trạng thái hiện tại cho phép chuyển sang trạng thái mới.
- **Quan hệ và quyền:** ID tham chiếu phải tồn tại trong phạm vi mà người gọi được phép truy cập.

Ví dụ DTO trong Java:

```java
public record CreateOrderRequest(
        @NotNull UUID productId,
        @Min(1) @Max(20) int quantity,
        @NotBlank @Size(max = 200) String deliveryNote) {
}
```

Controller có thể dùng `@Valid` để kích hoạt kiểm tra annotation trước khi gọi dịch vụ. Tuy nhiên, validation cấu trúc không thay thế kiểm tra nghiệp vụ và phân quyền. `productId` có định dạng UUID hợp lệ vẫn có thể trỏ đến sản phẩm thuộc tenant khác.

Không tin các trường định danh và quyền do client gửi như `userId`, `ownerId`, `tenantId`, `price`, `isAdmin` hoặc `approvedBy`. Máy chủ phải xác định các giá trị này từ danh tính đã xác thực và dữ liệu nghiệp vụ có thẩm quyền. Dùng truy vấn tham số hóa hoặc ORM an toàn để chống injection; không ghép chuỗi đầu vào trực tiếp vào SQL, lệnh hệ điều hành hoặc biểu thức truy vấn.

Hãy từ chối content type không được hỗ trợ, giới hạn độ sâu và kích thước dữ liệu lồng nhau, xử lý Unicode/canonicalization nhất quán và tránh cho phép trường tùy ý được cập nhật. Với dữ liệu đầu ra, mã hóa theo ngữ cảnh sử dụng và chỉ serialize các trường cần thiết. Validation không có nghĩa là mọi chuỗi phải loại bỏ ký tự đặc biệt; quy tắc phải phù hợp với kiểu dữ liệu và nơi dữ liệu được sử dụng.

## 5. Chống SSRF khi API truy cập tài nguyên bên ngoài

Server-Side Request Forgery (SSRF) xảy ra khi kẻ tấn công khiến máy chủ gửi request đến địa chỉ do họ kiểm soát. Rủi ro thường xuất hiện ở chức năng xem trước URL, nhập ảnh từ URL, webhook, proxy, tải tài liệu hoặc tích hợp dịch vụ bên thứ ba. Nếu máy chủ có thể truy cập mạng nội bộ, metadata của cloud hoặc dịch vụ quản trị, SSRF có thể biến API thành cầu nối để dò quét hoặc lấy thông tin nhạy cảm.

Biện pháp ưu tiên là thiết kế API nhận một định danh tài nguyên đã đăng ký thay vì URL tùy ý. Nếu nghiệp vụ bắt buộc phải nhận URL, cần kết hợp nhiều lớp:

1. Chỉ cho phép scheme cần thiết, thường là `https`; từ chối `file:`, `gopher:`, `ftp:` và scheme không sử dụng.
2. Dùng allowlist hostname/đích đến cụ thể nếu có thể. Kiểm tra hostname sau khi parse URL bằng thư viện chuẩn; từ chối user-info, port lạ và dạng địa chỉ không mong muốn.
3. Phân giải DNS và kiểm tra tất cả địa chỉ IPv4/IPv6 trả về. Chặn loopback, private, link-local, multicast, địa chỉ dành riêng và địa chỉ metadata của nhà cung cấp cloud.
4. Chống DNS rebinding: bảo đảm địa chỉ được kiểm tra cũng là địa chỉ thực sự được kết nối; cân nhắc egress proxy hoặc lớp mạng có chính sách allowlist.
5. Tắt tự động follow redirect hoặc kiểm tra lại toàn bộ đích đến ở từng bước redirect. Không cho phép redirect sang địa chỉ nội bộ.
6. Đặt timeout kết nối/đọc, giới hạn số byte phản hồi, loại nội dung và số lần gọi; không trả nguyên văn phản hồi nội bộ cho client.
7. Giới hạn quyền mạng của dịch vụ bằng firewall, security group hoặc egress policy. Ứng dụng không nên có quyền truy cập toàn bộ mạng nội bộ nếu không cần.

Chỉ kiểm tra chuỗi URL bằng regex hoặc chặn một vài hostname là chưa đủ. DNS có thể trả nhiều địa chỉ, biểu diễn IP có nhiều dạng và redirect có thể thay đổi đích đến. Phòng vệ hiệu quả cần kết hợp kiểm tra ở ứng dụng với giới hạn kết nối ở tầng mạng.

## 6. Giới hạn lạm dụng tài nguyên và hành vi tự động

Một API có thể đúng về quyền nhưng vẫn bị lạm dụng để gây cạn CPU, bộ nhớ, kết nối, dung lượng lưu trữ hoặc chi phí dịch vụ bên thứ ba. Ví dụ: gọi endpoint tìm kiếm với phạm vi quá lớn, yêu cầu export liên tục, tải tệp dung lượng cao, gửi OTP nhiều lần hoặc kích hoạt tác vụ tốn kém bằng script.

Áp dụng giới hạn theo nhiều chiều:

- Rate limit theo IP, danh tính, API key, tenant và loại thao tác. Giới hạn theo IP đơn lẻ không đủ khi nhiều người dùng dùng chung NAT hoặc kẻ tấn công phân tán request.
- Quota theo thời gian cho các nghiệp vụ tốn kém như gửi SMS/email, export, tạo báo cáo hoặc gọi API bên thứ ba.
- Phân trang có giới hạn `pageSize` tối đa; không cho client yêu cầu toàn bộ dữ liệu không giới hạn. Dùng cursor pagination khi tập dữ liệu lớn hoặc thay đổi liên tục.
- Giới hạn kích thước request/response, số bản ghi được xử lý, số phần tử trong batch, thời gian chạy, số kết nối đồng thời và kích thước upload.
- Đặt timeout và circuit breaker cho phụ thuộc bên ngoài; dùng hàng đợi và xử lý bất đồng bộ cho công việc dài.
- Bảo vệ thao tác có thể bị gửi lặp bằng idempotency key hoặc mã giao dịch duy nhất. Kiểm tra quyền và phạm vi của key, thời hạn lưu và hành vi khi cùng key được gửi với payload khác.
- Với GraphQL hoặc truy vấn linh hoạt, giới hạn độ sâu, độ phức tạp, số lượng node và thời gian thực thi.

Khi vượt giới hạn, trả `429 Too Many Requests` và có thể kèm `Retry-After` để client biết thời điểm thử lại. Giới hạn nên dựa trên năng lực thực tế và tác động nghiệp vụ; cần theo dõi để tránh chặn nhầm lưu lượng hợp lệ. CAPTCHA hoặc challenge chỉ là lớp bổ sung cho một số luồng, không thay thế quota và kiểm soát tài nguyên ở máy chủ.

## 7. Bảo vệ dữ liệu và cấu hình API

Chỉ thu thập và trả về dữ liệu cần cho chức năng. Phân loại dữ liệu theo mức nhạy cảm để chọn cách lưu trữ, mã hóa, kiểm soát truy cập và thời gian lưu giữ phù hợp.

- Dùng TLS cho mọi kết nối có dữ liệu hoặc thông tin xác thực; cân nhắc mTLS cho giao tiếp dịch vụ có yêu cầu danh tính hai chiều.
- Mã hóa dữ liệu nhạy cảm khi lưu trữ và quản lý khóa tách khỏi dữ liệu. Không tự tạo thuật toán mã hóa; dùng dịch vụ quản lý khóa hoặc thư viện đã được kiểm chứng.
- Lưu secret trong secret manager hoặc cơ chế quản lý bí mật tương đương; không commit vào mã nguồn, image, file cấu hình công khai hoặc log. Luân chuyển secret khi có nghi ngờ lộ lọt.
- Không ghi access token, refresh token, mật khẩu, API key, dữ liệu thanh toán hoặc nội dung cá nhân nhạy cảm vào log. Nếu cần liên kết request, dùng request ID và định danh đã được giảm thiểu hoặc giả danh hóa.
- Trả lỗi đủ hữu ích cho client nhưng không để lộ stack trace, câu SQL, đường dẫn nội bộ, tên máy chủ hoặc cấu hình. Dùng mã lỗi ổn định và lưu chi tiết kỹ thuật ở log nội bộ có kiểm soát truy cập.
- Thiết lập CORS theo danh sách origin cần thiết. CORS là chính sách cho trình duyệt, không phải cơ chế xác thực hoặc phân quyền; client ngoài trình duyệt vẫn có thể gọi API.
- Kiểm soát cache cho response chứa dữ liệu riêng tư; cân nhắc `Cache-Control: no-store` với dữ liệu nhạy cảm. Cấu hình header bảo mật và chính sách upload/download phù hợp.
- Với upload, kiểm tra kích thước, loại nội dung thực tế, tên tệp, quyền truy cập và vị trí lưu; không tin phần mở rộng hoặc `Content-Type` do client khai báo. Lưu tệp ngoài web root và quét nội dung khi mô hình rủi ro yêu cầu.

Nếu API dùng cookie cho xác thực, cần đánh giá CSRF vì trình duyệt có thể tự gửi cookie theo request. Với bearer token chỉ được client chủ động gắn vào header, mô hình CSRF khác nhưng token vẫn có thể bị đánh cắp qua XSS hoặc lưu trữ phía client không an toàn.

## 8. Kiểm thử bảo mật theo endpoint và luồng nghiệp vụ

Kiểm thử bảo mật phải kiểm tra cả trường hợp được phép và bị từ chối. Một bộ test chỉ chứng minh người dùng hợp lệ gọi thành công chưa đủ để chứng minh hệ thống an toàn.

Với từng endpoint, xây dựng ma trận kiểm thử gồm:

- Người chưa xác thực, token hết hạn, token sai issuer/audience hoặc thiếu scope.
- Người dùng đúng vai trò nhưng truy cập đối tượng của người khác hoặc tenant khác.
- Người dùng có quyền đọc nhưng thử ghi; có quyền cập nhật nhưng thử sửa trường nhạy cảm; có quyền gọi endpoint thông thường nhưng thử endpoint quản trị.
- Đối tượng ở trạng thái không cho phép thao tác; hai request đồng thời thực hiện cùng một chuyển trạng thái.
- Payload sai kiểu, thiếu trường, trường dư, chuỗi quá dài, số ngoài miền, mảng lớn, JSON lồng sâu và content type không hợp lệ.
- URL trỏ đến loopback, mạng private, địa chỉ metadata, hostname đổi DNS, redirect sang mạng nội bộ hoặc phản hồi quá lớn khi kiểm thử chức năng fetch URL.
- Request vượt rate limit, quota, kích thước, timeout, số lượng phần tử hoặc mức đồng thời.
- Response và log không làm lộ trường nhạy cảm, token, stack trace hoặc dữ liệu của tenant khác.

Kết hợp các lớp kiểm thử phù hợp:

| Lớp kiểm thử | Mục tiêu |
|---|---|
| Unit test | Kiểm tra quy tắc quyền, validation và chuyển trạng thái ở lớp nghiệp vụ |
| Integration test | Xác minh cấu hình security filter, truy vấn giới hạn tenant, serialization và xử lý lỗi |
| API security test | Gửi request với danh tính, quyền, ID và payload khác nhau theo ma trận endpoint |
| SAST và dependency scanning | Phát hiện mẫu code nguy hiểm và thư viện có lỗ hổng đã biết |
| DAST/fuzzing | Thử payload bất thường, dữ liệu sai cấu trúc và hành vi của API đang chạy |
| Penetration test | Đánh giá chuỗi tấn công và các ranh giới tin cậy trong bối cảnh hệ thống thực tế |

Đưa test phân quyền quan trọng vào CI để lỗi BOLA, quyền chức năng hoặc cập nhật thuộc tính nhạy cảm được phát hiện trước khi phát hành. Dùng dữ liệu test tách biệt; không kiểm thử xâm nhập trên hệ thống production khi chưa có phạm vi và lịch được phê duyệt.

## 9. Giám sát và phản ứng khi API chạy thật

Không phải mọi hành vi bất thường đều có thể bị ngăn chặn trước. Hệ thống cần ghi nhận đủ tín hiệu để phát hiện, điều tra và giới hạn thiệt hại.

Log có cấu trúc nên ghi request ID, endpoint hoặc route template, phương thức, kết quả, độ trễ, danh tính đã được giảm thiểu, tenant phù hợp và loại quyết định phân quyền. Không ghi token hoặc toàn bộ body mặc định. Với thao tác quan trọng như đổi quyền, duyệt giao dịch, hoàn tiền hoặc truy cập dữ liệu nhạy cảm, cần audit log có kiểm soát sửa/xóa và lưu được ai thực hiện, đối tượng nào, thời điểm nào, kết quả ra sao.

Theo dõi các chỉ số như tỷ lệ `401`/`403`/`404`/`429`, request lỗi, độ trễ, lưu lượng theo endpoint, mức sử dụng quota, lỗi phụ thuộc bên ngoài và số lần validation thất bại. Một đợt tăng đột biến `403` có thể là dấu hiệu dò quyền; nhiều request tới ID tuần tự có thể là dấu hiệu thử truy cập đối tượng; lưu lượng thấp nhưng truy vấn rất nặng có thể là lạm dụng tài nguyên.

Thiết lập cảnh báo theo ngưỡng và hành vi, tránh chỉ cảnh báo theo một mã HTTP đơn lẻ. Khi có sự cố, quy trình xử lý nên gồm xác định phạm vi, vô hiệu hóa hoặc luân chuyển thông tin xác thực bị lộ, giảm quyền hoặc chặn nguồn lạm dụng, bảo toàn log phục vụ điều tra, khôi phục an toàn và cập nhật test để ngăn tái diễn. API Gateway, WAF và hệ thống phát hiện xâm nhập có thể hỗ trợ quan sát hoặc chặn một số mẫu tấn công, nhưng chính sách quyền trên đối tượng và nghiệp vụ vẫn phải được thực thi trong ứng dụng.

## 10. Checklist trước khi phát hành một endpoint

Trước khi đưa endpoint vào production, nhóm phát triển và người review có thể dùng checklist sau:

- [ ] Đã xác định tài sản, người gọi hợp lệ, ranh giới tin cậy và tác động nghiệp vụ.
- [ ] Đã định nghĩa rõ phương thức, request/response schema, mã lỗi và giới hạn kích thước.
- [ ] Xác thực token hoặc danh tính dịch vụ bằng đầy đủ điều kiện cần thiết.
- [ ] Có kiểm tra quyền chức năng cho endpoint.
- [ ] Có kiểm tra quyền trên từng đối tượng và từng thuộc tính nhạy cảm.
- [ ] Quy tắc trạng thái và phân tách nhiệm vụ được thực thi ở lớp nghiệp vụ.
- [ ] Dữ liệu đầu vào được kiểm tra cấu trúc, miền giá trị, kích thước và quy tắc nghiệp vụ.
- [ ] Không tin ID, tenant, owner, role, giá hoặc trạng thái do client tự khai báo.
- [ ] Mọi kết nối ra ngoài có allowlist/chính sách đích đến, timeout, giới hạn phản hồi và egress control phù hợp; SSRF đã được đánh giá.
- [ ] Có rate limit, quota, phân trang và giới hạn tài nguyên phù hợp với tác động của endpoint.
- [ ] Response chỉ chứa trường cần thiết; secret và dữ liệu nhạy cảm không xuất hiện trong log hoặc lỗi.
- [ ] CORS, cache, cookie/CSRF, upload và download đã được cấu hình theo mô hình sử dụng.
- [ ] Có test cho cả trường hợp hợp lệ và các trường hợp bị từ chối trong ma trận quyền.
- [ ] Có log, audit và cảnh báo đủ để phát hiện lạm dụng hoặc truy cập bất thường.

## 11. Tình huống tổng hợp: API xem và duyệt đơn hàng

Giả sử một hệ thống thương mại điện tử có ba vai trò: khách hàng, nhân viên hỗ trợ và quản lý. API cung cấp `GET /orders/{id}`, `PATCH /orders/{id}` và `POST /orders/{id}/approve`.

Khách hàng chỉ được xem đơn thuộc tài khoản của mình. Nhân viên hỗ trợ được xem đơn trong phạm vi nhóm phụ trách nhưng không được duyệt. Quản lý được duyệt đơn trong khu vực quản lý, với điều kiện người duyệt không phải người tạo yêu cầu nếu chính sách yêu cầu phân tách nhiệm vụ. Khách hàng có thể cập nhật ghi chú giao hàng khi đơn còn ở trạng thái cho phép; họ không thể cập nhật giá, chủ sở hữu, tenant hoặc trạng thái phê duyệt.

Thiết kế an toàn sẽ thực hiện các bước sau:

1. Xác minh access token, issuer, audience, thời hạn và chữ ký; tạo principal đáng tin cậy cho request.
2. Kiểm tra quyền chức năng tương ứng với từng endpoint.
3. Truy vấn đơn hàng trong phạm vi khách hàng, nhóm hỗ trợ hoặc khu vực quản lý mà principal được phép truy cập.
4. Dùng DTO riêng cho ghi chú giao hàng; không bind request vào entity đơn hàng.
5. Kiểm tra trạng thái đơn trước khi cập nhật hoặc duyệt; thực hiện cập nhật có kiểm soát đồng thời để không duyệt hai lần.
6. Giới hạn tần suất gọi, ghi audit cho thao tác duyệt và theo dõi các lần truy cập bị từ chối.
7. Kiểm thử khách hàng truy cập ID của người khác, nhân viên hỗ trợ gọi endpoint duyệt, quản lý duyệt sai khu vực và client cố gửi thêm trường `approved` hoặc `price`.

Tình huống này cho thấy bảo mật API là sự kết hợp của xác thực, quyền chức năng, quyền trên đối tượng, quyền trên thuộc tính và quy tắc nghiệp vụ. Thiếu một lớp có thể khiến các lớp còn lại mất tác dụng.

## Kết luận

Một API an toàn cần trả lời chính xác ba câu hỏi ở mọi thao tác: **ai đang gọi, họ được phép làm gì, và họ được phép tác động lên dữ liệu nào trong điều kiện nghiệp vụ nào**. Từ đó, nhóm phát triển bổ sung validation, giới hạn tài nguyên, bảo vệ kết nối ra ngoài, giảm thiểu dữ liệu, kiểm thử và giám sát phù hợp. HTTPS và xác thực là nền tảng cần có; chất lượng bảo mật thực sự phụ thuộc vào việc các quy tắc đó được áp dụng nhất quán trên từng endpoint và toàn bộ vòng đời vận hành.
