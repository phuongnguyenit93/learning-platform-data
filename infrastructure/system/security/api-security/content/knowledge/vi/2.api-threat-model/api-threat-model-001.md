# Attacker ẩn danh, user hợp lệ và client bị chiếm

## Vì sao cần phân biệt ba nhóm tác nhân?

Một API có thể xác thực người gọi thành công mà vẫn bị khai thác. Đăng nhập chỉ cho biết request đang mang danh tính nào; nó chưa chứng minh người đó được phép đọc một bản ghi, gọi một chức năng, sửa một trường dữ liệu hay thực hiện một bước trong quy trình nghiệp vụ. HTTPS bảo vệ dữ liệu trên đường truyền, nhưng không ngăn người dùng hợp lệ lạm quyền hoặc kẻ tấn công sử dụng một phiên đã bị đánh cắp.

Khi lập mô hình đe dọa API, hãy xem xét ít nhất ba nhóm tác nhân:

1. **Attacker ẩn danh** chưa có phiên đăng nhập hoặc thông tin xác thực hợp lệ.
2. **User hợp lệ** có tài khoản và phiên được xác thực, nhưng có thể tò mò, cố tình lạm quyền hoặc tự động hóa hành vi ngoài dự kiến.
3. **Client bị chiếm** là ứng dụng, thiết bị hoặc tiến trình phía client đã bị kiểm soát. Kẻ tấn công có thể sử dụng token, khóa hoặc quyền mà client đang nắm giữ và tự tạo request.

Đây là các trạng thái năng lực của tác nhân, không phải ba loại người luôn tách biệt. Một attacker ẩn danh có thể lấy được mật khẩu rồi trở thành người dùng đã xác thực. Một user hợp lệ có thể bị đánh cắp token, khiến phiên của họ trở thành mục tiêu của client bị chiếm. Mô hình cần theo dõi sự chuyển trạng thái này vì quyền truy cập mà API quan sát được có thể vẫn hợp lệ trong khi người điều khiển request đã thay đổi.

## 1. Attacker ẩn danh

Attacker ẩn danh không cần tài khoản để bắt đầu dò tìm bề mặt API. Họ có thể gửi request trực tiếp đến các endpoint công khai, endpoint đăng nhập, đăng ký, quên mật khẩu, tải tệp, tìm kiếm hoặc các endpoint vô tình bị cấu hình công khai. Công cụ tự động giúp họ thử nhiều đường dẫn, tham số và payload với tốc độ cao.

Các mục tiêu thường gặp gồm:

- **Khám phá và liệt kê tài nguyên:** dò ID người dùng, mã đơn hàng, tên đăng nhập hoặc trạng thái tài khoản từ phản hồi và thời gian xử lý.
- **Chiếm tài khoản:** thử mật khẩu rò rỉ, credential stuffing, brute force, lạm dụng quy trình đặt lại mật khẩu hoặc mã xác minh.
- **Khai thác đầu vào:** gửi payload sai định dạng, dữ liệu quá lớn, đường dẫn bất thường hoặc URL do attacker kiểm soát để tìm lỗi validation và SSRF.
- **Làm cạn tài nguyên:** gửi nhiều request, truy vấn tìm kiếm đắt đỏ, upload lớn hoặc tạo nhiều tác vụ nền.
- **Lợi dụng endpoint công khai:** lạm dụng chức năng gửi lời mời, gửi SMS/email, xem trước liên kết hoặc tra cứu dữ liệu vốn được thiết kế cho truy cập không cần đăng nhập.

### Cách phòng vệ

- Xác định rõ endpoint nào thực sự công khai. Mọi endpoint còn lại phải yêu cầu xác thực ở phía server; không dựa vào việc giao diện không hiển thị đường dẫn.
- Với đăng nhập và khôi phục tài khoản, áp dụng giới hạn tốc độ theo nhiều chiều như IP, tài khoản, thiết bị hoặc dấu hiệu rủi ro; dùng thời gian phản hồi và thông báo nhất quán để giảm khả năng dò tài khoản.
- Chỉ trả về dữ liệu tối thiểu cần thiết. Không tiết lộ stack trace, truy vấn nội bộ, thông tin hạ tầng, token hoặc lý do chi tiết giúp attacker phân biệt tài khoản tồn tại.
- Kiểm tra kiểu, kích thước, định dạng và miền giá trị của đầu vào trước khi xử lý. Dùng allowlist khi tập giá trị hợp lệ có thể xác định.
- Đặt hạn mức cho request, upload, tìm kiếm và tác vụ tốn tài nguyên. Giới hạn ở gateway cần được bổ sung bằng hạn mức trong dịch vụ để tránh một đường gọi nội bộ bỏ qua gateway.
- Theo dõi các dấu hiệu như nhiều lần đăng nhập thất bại, tăng đột biến mã 404/401, thử nhiều ID liên tiếp và lượng request bất thường từ một nguồn.

Endpoint công khai vẫn cần mô hình đe dọa riêng. “Không cần đăng nhập” không đồng nghĩa với “không có rủi ro” hoặc “được phép trả về dữ liệu không giới hạn”.

## 2. User hợp lệ

User hợp lệ có danh tính đã được xác thực. Tuy nhiên, họ chỉ được phép thực hiện những hành động phù hợp với vai trò, quan hệ với đối tượng dữ liệu, tenant và trạng thái nghiệp vụ hiện tại. Người dùng có thể thay ID trên URL, sửa JSON, gọi endpoint trực tiếp, phát lại request hoặc dùng script thay cho giao diện chính thức.

Những rủi ro nổi bật gồm:

| Rủi ro | Tình huống | Điều API phải kiểm tra |
|---|---|---|
| BOLA/IDOR (Broken Object Level Authorization) | User A thay `orderId` của mình bằng ID đơn hàng của user B. | Quyền trên đúng đối tượng: chủ sở hữu, tenant hoặc quan hệ được cấp quyền. |
| BFLA (Broken Function Level Authorization) | User thường gọi endpoint quản trị hoặc hoàn tiền mà giao diện không hiển thị. | Quyền gọi chức năng ở phía server cho từng request. |
| Phân quyền thuộc tính không đầy đủ | User gửi thêm `role`, `ownerId`, `price` hoặc `status` trong JSON. | Chỉ bind các trường được phép sửa; kiểm tra quyền đọc/ghi theo trường khi cần. |
| Lạm dụng quy trình nghiệp vụ | User gọi xác nhận trước khi thanh toán, hủy sau hạn chót hoặc yêu cầu hoàn tiền nhiều lần. | Điều kiện chuyển trạng thái, thứ tự bước, giới hạn và tính nguyên tử. |
| Lạm dụng tài nguyên bằng tài khoản thật | Một tài khoản gọi tìm kiếm nặng hoặc tạo hàng nghìn tác vụ. | Hạn mức theo user, tenant và loại thao tác; kiểm soát chi phí. |

### Phân quyền phải gắn với request, chức năng và đối tượng

Xác thực trả lời câu hỏi “ai đang gọi?”. Phân quyền trả lời “danh tính này được làm gì, trên đối tượng nào, trong điều kiện nào?”. Hai bước cần được thực hiện độc lập.

Với mỗi endpoint, kiểm tra tối thiểu:

1. **Quyền chức năng:** principal có quyền thực hiện hành động này không, ví dụ `order:read`, `order:cancel` hoặc `refund:create`?
2. **Quyền trên đối tượng:** đối tượng có thuộc user hoặc tenant mà principal được truy cập không? Có quan hệ chia sẻ hay ủy quyền hợp lệ không?
3. **Quyền trên thuộc tính:** user được đọc hoặc cập nhật những trường nào? Trường hệ thống như vai trò, chủ sở hữu, số dư và trạng thái thường không được nhận trực tiếp từ payload thông thường.
4. **Điều kiện nghiệp vụ:** thao tác có hợp lệ ở trạng thái hiện tại, trong hạn mức và đúng thứ tự không?

Thực hiện kiểm tra ở phía server trên mọi request, kể cả khi giao diện đã ẩn nút hoặc đã kiểm tra trước đó. Mặc định từ chối khi thiếu chính sách hoặc không xác định được quan hệ. Trong hệ thống nhiều tenant, truy vấn dữ liệu nên ràng buộc tenant ngay từ tầng truy xuất; không lấy bản ghi toàn cục rồi quên kiểm tra tenant ở một nhánh xử lý.

Không xem ID khó đoán là cơ chế phân quyền. UUID hoặc mã ngẫu nhiên có thể làm giảm khả năng dò quét, nhưng người có được ID vẫn không được truy cập nếu thiếu quyền. Tương tự, CORS, nút bị ẩn, kiểm tra JavaScript và header do client tự gửi không phải bằng chứng về quyền của người gọi.

## 3. Client bị chiếm

Client bị chiếm xảy ra khi attacker kiểm soát được ứng dụng hoặc môi trường chạy ứng dụng, lấy được token/khóa, hoặc có thể điều khiển request mà client hợp lệ gửi đi. Ví dụ: điện thoại bị cài mã độc, trình duyệt có extension độc hại, máy người dùng bị kiểm soát, ứng dụng desktop bị sửa đổi hoặc secret của một tiến trình tích hợp bị lộ.

Trong tình huống này, request có thể mang token còn hạn, chữ ký hợp lệ và các header đúng định dạng. API không thể kết luận người điều khiển request là người dùng thật chỉ dựa trên việc token hợp lệ.

Attacker có thể:

- Gọi API trực tiếp và bỏ qua mọi giới hạn chỉ được triển khai trong giao diện.
- Thay đổi body, query, ID đối tượng, số tiền, vai trò được yêu cầu hoặc thứ tự các bước nghiệp vụ.
- Phát lại request đã quan sát được, dùng token trên thiết bị khác hoặc tự động hóa thao tác bằng quyền của phiên bị đánh cắp.
- Đọc dữ liệu mà phiên đó được phép đọc và thực hiện hành động trong phạm vi quyền của token.
- Trích xuất API key hoặc client secret được đóng gói trong ứng dụng công khai. Secret đặt trong ứng dụng phân phối cho người dùng không thể được xem là bí mật dài hạn.

### Giảm tác động khi client bị chiếm

- Xem mọi dữ liệu đến từ client là dữ liệu không đáng tin cậy, kể cả `deviceId`, `appVersion`, `isAdmin`, cờ đã xác minh hoặc kết quả kiểm tra ở giao diện.
- Cấp token có audience, scope và thời hạn phù hợp; tránh token có quyền rộng hoặc thời gian sống quá dài. Có cơ chế thu hồi phiên/token và xoay vòng thông tin xác thực khi có dấu hiệu lộ lọt.
- Với OAuth cho ứng dụng public client, dùng Authorization Code với PKCE và luồng phù hợp; không nhúng client secret dùng chung vào ứng dụng di động hoặc SPA. Với tích hợp máy-với-máy, lưu secret ở môi trường server được bảo vệ và giới hạn quyền của credential.
- Với API nhạy cảm, cân nhắc ràng buộc token với client bằng cơ chế như mTLS hoặc DPoP khi kiến trúc và hệ sinh thái hỗ trợ. Đây là lớp giảm rủi ro phát lại/đánh cắp token, không thay thế phân quyền trên đối tượng và nghiệp vụ.
- Yêu cầu xác thực tăng cường hoặc xác nhận giao dịch cho hành động có hậu quả lớn; giới hạn giá trị, tần suất và người nhận theo chính sách nghiệp vụ.
- Phát hiện hành vi bất thường theo ngữ cảnh: vị trí hoặc thiết bị thay đổi đột ngột, tốc độ thao tác cao, nhiều lần đọc đối tượng không liên quan, thay đổi thông tin bảo mật hoặc hành động khác mẫu thông thường. Dùng tín hiệu thiết bị như một tín hiệu rủi ro, không coi chúng là chứng minh tuyệt đối.
- Không ghi access token, refresh token, mật khẩu, API key hoặc dữ liệu nhạy cảm đầy đủ vào log. Khi cần điều tra, ghi mã định danh phiên đã được bảo vệ hoặc dấu vân tay phù hợp.

Nếu token bị đánh cắp nhưng chưa hết hạn, API có thể vẫn chấp nhận request đúng giao thức. Vì vậy, giảm thời hạn và phạm vi token, khả năng thu hồi, kiểm soát giao dịch và giám sát hành vi đều quan trọng.

## 4. Đặt ba nhóm tác nhân vào cùng một mô hình endpoint

Hãy lập bảng theo từng hành động API, thay vì chỉ lập một danh sách chung về “người dùng đã đăng nhập”. Ví dụ với chức năng hủy đơn hàng:

| Tác nhân | Request hoặc hành vi | Câu hỏi đe dọa | Kiểm soát cần có |
|---|---|---|---|
| Attacker ẩn danh | Gọi `POST /api/orders/{id}/cancel` không có token. | Endpoint có vô tình cho phép truy cập công khai hoặc trả về thông tin đơn hàng không? | Yêu cầu xác thực; kiểm tra quyền ở server; phản hồi tối thiểu. |
| User hợp lệ, chủ đơn | Gọi hủy đơn do mình sở hữu. | Đơn còn ở trạng thái được hủy và còn trong thời hạn không? | Kiểm tra quan hệ chủ sở hữu, trạng thái, thời hạn và chính sách nghiệp vụ. |
| User hợp lệ, không phải chủ đơn | Thay `{id}` bằng ID đơn của người khác hoặc tenant khác. | Có thể đọc hoặc thay đổi đối tượng ngoài phạm vi được cấp không? | Kiểm tra object-level authorization và ranh giới tenant trên mỗi request. |
| Client của chủ đơn bị chiếm | Kẻ tấn công dùng token của chủ đơn để hủy hoặc phát lại request. | Phiên bị đánh cắp có thể tạo thao tác lặp hoặc thao tác có hậu quả lớn không? | Thu hồi phiên, hạn mức, idempotency, xác nhận tăng cường khi phù hợp và giám sát bất thường. |

Ví dụ triển khai ở tầng service (mã minh họa):

```java
@Transactional
public void cancelOrder(UUID orderId, Principal principal) {
    Order order = orderRepository
        .findByIdAndTenantId(orderId, principal.tenantId())
        .orElseThrow(OrderNotFoundException::new);

    authorization.require(principal, "order:cancel", order);
    order.cancel(clock.instant()); // Tự kiểm tra trạng thái và thời hạn hợp lệ.
    audit.record(principal.id(), "order.cancel", order.id());
}
```

Ví dụ này thể hiện các điểm cần giữ: truy xuất trong phạm vi tenant, kiểm tra quyền trên chính đối tượng, để miền nghiệp vụ xác nhận chuyển trạng thái và ghi nhận hành động. Trong ứng dụng thực tế, cần bảo đảm việc cập nhật trạng thái và xử lý idempotency được thực hiện nguyên tử; log kiểm toán chỉ chứa dữ liệu cần thiết. Cách phản hồi `404` hay `403` cho đối tượng không thuộc quyền truy cập cần được chọn nhất quán theo chính sách chống dò tìm tài nguyên.

## 5. Các ranh giới cần kiểm tra khi lập threat model

Với mỗi endpoint hoặc thao tác, đi lần lượt qua các câu hỏi sau:

| Khu vực | Câu hỏi cần trả lời | Ví dụ kiểm soát |
|---|---|---|
| Danh tính | Ai đang gọi? Token có chữ ký, issuer, audience, thời hạn và trạng thái hợp lệ không? | Xác minh token ở server; kiểm tra expiry, issuer, audience, scope; thu hồi khi cần. |
| Chức năng | Principal có được gọi hành động này không? | Quyền theo chức năng, vai trò và chính sách; mặc định từ chối. |
| Đối tượng | Principal có quan hệ hợp lệ với bản ghi và tenant không? | Kiểm tra quyền ở mức object; truy vấn có ràng buộc tenant. |
| Thuộc tính | Những trường nào được đọc hoặc ghi? | DTO allowlist; không bind trực tiếp entity từ payload; lọc trường trả về. |
| Đầu vào | Dữ liệu có đúng schema, kiểu, độ dài, miền giá trị và ngữ cảnh không? | Validation phía server, canonicalization phù hợp, truy vấn tham số hóa và encode đầu ra theo ngữ cảnh. |
| Luồng nghiệp vụ | Hành động có đúng trạng thái, thứ tự, hạn mức và số lần không? | State machine, transaction, idempotency key, kiểm tra giới hạn và xác nhận tăng cường. |
| Gọi hệ thống ngoài | API có truy cập URL, file, webhook hoặc dịch vụ do người dùng chỉ định không? | Allowlist đích, giới hạn giao thức/cổng, kiểm tra DNS và redirect, kiểm soát egress. |
| Tài nguyên | Request có thể tiêu tốn bao nhiêu CPU, bộ nhớ, kết nối, tiền hoặc tác vụ nền? | Giới hạn body, page size, độ sâu truy vấn, timeout, concurrency, quota và rate limit. |
| Dữ liệu | Response và log có tiết lộ dữ liệu vượt nhu cầu không? | Tối thiểu hóa dữ liệu, phân loại dữ liệu, mã hóa phù hợp và che thông tin nhạy cảm trong log. |
| Quan sát | Có thể phát hiện và điều tra hành vi lạm dụng không? | Audit event, metric, cảnh báo và quy trình thu hồi credential/phiên. |

### Chống SSRF khi API gọi URL do người dùng cung cấp

Nếu API tải ảnh, xem trước liên kết, gọi webhook hoặc lấy dữ liệu từ URL do client gửi, server đang thực hiện một request thay mặt người dùng. Attacker có thể lợi dụng để yêu cầu server truy cập dịch vụ nội bộ, địa chỉ loopback, link-local hoặc metadata của môi trường cloud.

Ưu tiên allowlist hostname/đích đến nếu nghiệp vụ cho phép. Nếu cần hỗ trợ URL linh hoạt, chỉ chấp nhận giao thức cần thiết; giới hạn cổng; phân giải DNS và từ chối địa chỉ IP private, loopback, link-local, multicast hoặc reserved; kiểm tra lại mọi redirect; kiểm soát kết nối outbound ở tầng mạng. Cần tính đến thay đổi kết quả DNS giữa lúc kiểm tra và lúc kết nối. Regex đơn giản hoặc kiểm tra URL một lần không đủ để ngăn SSRF.

### Chống lạm dụng tài nguyên

Giới hạn cần gắn với chi phí thật của thao tác. Ví dụ: `pageSize` tối đa, kích thước body/upload, số bộ lọc, độ sâu và độ phức tạp truy vấn, thời gian chờ, số request đồng thời, số tác vụ nền và quota theo user/tenant. Một giới hạn theo IP đơn lẻ có thể không đủ khi attacker phân tán request hoặc sử dụng nhiều tài khoản. Trả mã `429` và thông tin retry phù hợp khi vượt hạn mức; tránh để request bị giới hạn vẫn tạo tác dụng phụ ở hệ thống downstream.

## 6. Kiểm thử và giám sát theo tác nhân

Kiểm thử bảo mật cần xác nhận cả trường hợp được phép và bị từ chối. Với từng endpoint quan trọng, tạo ma trận gồm anonymous, user đúng quyền, user sai quyền, user cùng tenant nhưng không sở hữu đối tượng, user ở tenant khác và phiên/token có dấu hiệu bị lộ hoặc hết hạn.

Các kiểm thử thực tế nên bao gồm:

- Gọi endpoint không token, token sai chữ ký, sai audience, hết hạn hoặc thiếu scope.
- Thay object ID, tenant ID và các trường nhạy cảm trong request; thử đọc và ghi đối tượng không thuộc quyền.
- Gọi trực tiếp chức năng quản trị bằng tài khoản thường; bỏ qua giao diện và gửi payload tự tạo.
- Thử chuyển trạng thái sai thứ tự, gửi request lặp, phát lại request và gửi đồng thời các thao tác cạnh tranh.
- Gửi đầu vào sai schema, quá dài, có ký tự/encoding bất thường; thử URL nội bộ và redirect trong các chức năng tải URL.
- Đo hành vi khi vượt rate limit, quota, kích thước file, page size, timeout và giới hạn truy vấn.
- Xác nhận hành động nhạy cảm có audit event và log không chứa token, secret hoặc payload riêng tư không cần thiết.

Giám sát nên gắn sự kiện với actor, principal, tenant, endpoint, hành động, đối tượng ở mức định danh phù hợp, kết quả phân quyền, request ID và thời điểm. Theo dõi các cụm tín hiệu như nhiều lần bị từ chối, truy cập nhiều đối tượng không liên quan, request lặp, vượt quota, thay đổi trạng thái bất thường và kết nối outbound bị chặn. Cần có cách thu hồi phiên/credential, khóa hoặc giảm quyền một principal và điều tra các hành động đã xảy ra.

## 7. Checklist cho mỗi endpoint

- [ ] Endpoint có được xác định rõ là công khai hay cần xác thực?
- [ ] Server xác minh danh tính và thuộc tính token cần thiết?
- [ ] Có kiểm tra quyền chức năng cho hành động cụ thể?
- [ ] Có kiểm tra quyền trên đúng đối tượng, thuộc tính và tenant?
- [ ] Có kiểm tra trạng thái, thứ tự, hạn mức và tính lặp của nghiệp vụ?
- [ ] Đầu vào được xác thực theo schema và ngữ cảnh; truy vấn được tham số hóa?
- [ ] URL, file và lời gọi ra ngoài được giới hạn để giảm SSRF?
- [ ] Có hạn mức tài nguyên theo request, principal và tenant?
- [ ] Response chỉ chứa dữ liệu cần thiết; log không làm lộ bí mật?
- [ ] Có kiểm thử quyền bị từ chối và giám sát dấu hiệu lạm dụng?

Mô hình đe dọa API có chất lượng khi mỗi endpoint đều xác định được ai có thể gọi, họ được thao tác trên dữ liệu nào, trong trạng thái nghiệp vụ nào, với giới hạn tài nguyên nào và hệ thống phát hiện ra sao khi request vượt khỏi chính sách. Ba nhóm tác nhân trên giúp kiểm tra các giả định khác nhau: request không có danh tính, request từ người dùng có danh tính hợp lệ và request mang credential hợp lệ nhưng có thể do kẻ tấn công điều khiển.
