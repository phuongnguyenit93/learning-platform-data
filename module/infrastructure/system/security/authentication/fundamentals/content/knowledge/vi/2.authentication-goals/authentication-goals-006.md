# Bảo vệ tài nguyên

> **Chương:** Mục tiêu xác thực  
> **Phạm vi:** Security Authentication Fundamentals — nền tảng xác thực danh tính nhằm bảo vệ dữ liệu, chức năng và dịch vụ trước truy cập trái phép.

## 1. Vì sao xác thực phải bắt đầu từ tài nguyên?

Một hệ thống không yêu cầu người dùng đăng nhập chỉ để có một màn hình đăng nhập. Mục tiêu là **bảo vệ tài nguyên**: chỉ cho phép một chủ thể đã được nhận diện ở mức tin cậy phù hợp thực hiện hành động được phép trên tài nguyên tương ứng.

**Tài nguyên** có thể là dữ liệu, chức năng, phiên làm việc hoặc một hệ thống khác. Chẳng hạn, trong ứng dụng quản lý doanh nghiệp:

| Tài nguyên | Ví dụ | Hậu quả nếu bị truy cập trái phép |
|---|---|---|
| Dữ liệu cá nhân | Hồ sơ nhân viên, địa chỉ, số điện thoại | Lộ thông tin, mạo danh |
| Dữ liệu nhạy cảm | Bảng lương, hồ sơ bệnh án, thông tin thanh toán | Tổn hại riêng tư và tài chính |
| Chức năng đặc quyền | Duyệt chi, thay đổi quyền, vô hiệu hóa tài khoản | Thao túng nghiệp vụ, leo thang đặc quyền |
| Tài sản số | Tệp riêng tư, khóa API, báo cáo nội bộ | Rò rỉ tài sản và bí mật |
| Dịch vụ | API nội bộ, cơ sở dữ liệu, tài nguyên đám mây | Trích xuất dữ liệu, lạm dụng năng lực xử lý |
| Khả năng duy trì quyền truy cập | Phiên, refresh token, phương thức khôi phục | Chiếm quyền tài khoản kéo dài |

Ba câu hỏi khác nhau phải được trả lời trước khi cho phép truy cập:

1. **Ai hoặc điều gì đang yêu cầu?** Xác thực (authentication) kiểm tra bằng chứng về danh tính của người dùng, thiết bị hoặc dịch vụ.
2. **Chủ thể đó được làm gì trên tài nguyên này?** Phân quyền (authorization) áp dụng chính sách, vai trò, quan hệ sở hữu và ngữ cảnh.
3. **Hành động có được thực thi và ghi nhận an toàn không?** Ứng dụng cần kiểm tra ở phía tin cậy, bảo vệ dữ liệu và lưu dấu vết phù hợp.

Xác thực là **điều kiện cần** của nhiều quyết định truy cập, nhưng **không tự cấp quyền**. Một người đã đăng nhập hợp lệ vẫn không được xem bảng lương của phòng ban khác nếu chính sách không cho phép.

### Kết quả học tập

Sau bài này, người học có thể:

- Xác định tài nguyên cần bảo vệ, chủ thể yêu cầu và tác hại khi ranh giới tin cậy bị vượt qua.
- Phân biệt bằng chứng xác thực danh tính với quyền thực hiện hành động trên từng tài nguyên.
- Mô tả luồng kiểm tra đăng nhập, phiên hoặc token và quyền truy cập đối với mỗi yêu cầu.
- Lựa chọn mức xác thực phù hợp với độ nhạy của thao tác; nhận diện rủi ro phishing, replay, đánh cắp phiên và khôi phục yếu.
- Đánh giá một luồng truy cập bằng các tình huống thất bại và biện pháp kiểm soát cụ thể.

## 2. Mô hình hóa tài nguyên và ranh giới tin cậy

Trước khi chọn mật khẩu, MFA hay passkey, hãy lập bản đồ **chủ thể → bằng chứng → điểm kiểm tra → tài nguyên → hành động**.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Chủ thể (principal) | Ai đang gửi yêu cầu? | Nhân viên A, ứng dụng báo cáo, dịch vụ xử lý thanh toán |
| Bằng chứng xác thực | Căn cứ nào chứng minh chủ thể? | Phiên đăng nhập, passkey, chứng chỉ máy, access token |
| Điểm thực thi chính sách | Hệ thống kiểm tra ở đâu? | Backend API, gateway, dịch vụ tài nguyên |
| Tài nguyên | Đối tượng nào đang được bảo vệ? | Hồ sơ nhân viên số 152 |
| Hành động | Chủ thể muốn làm gì? | Xem, sửa, xuất, xóa |
| Điều kiện | Ngữ cảnh nào làm thay đổi quyết định? | Chủ sở hữu, vai trò, thiết bị, độ nhạy, thời điểm |

### Ranh giới tin cậy

Trình duyệt, ứng dụng di động, tham số URL và dữ liệu do client gửi nằm ngoài ranh giới kiểm soát của backend. Người dùng có thể sửa một mã tài nguyên trong URL, chép yêu cầu HTTP hoặc can thiệp vào giao diện. Vì vậy, việc ẩn nút “Xóa” **không phải** biện pháp bảo vệ tài nguyên.

~~~mermaid
flowchart LR
    U["Người dùng / ứng dụng"] -->|"Cung cấp bằng chứng"| ID["Dịch vụ xác thực"]
    ID -->|"Phiên hoặc token hợp lệ"| C["Client"]
    C -->|"Yêu cầu tài nguyên"| API["API / điểm kiểm tra tin cậy"]
    API -->|"Xác minh phiên hoặc token"| V{"Danh tính hợp lệ?"}
    V -->|"Không"| R1["Từ chối: 401"]
    V -->|"Có"| P{"Được phép hành động trên tài nguyên?"}
    P -->|"Không"| R2["Từ chối: 403 hoặc 404 theo chính sách"]
    P -->|"Có"| D["Truy cập tài nguyên"]
~~~

Sơ đồ diễn tả một mô hình khái niệm: hệ thống xác thực có thể phát hành phiên hoặc token; dịch vụ tài nguyên phải **kiểm tra tính hợp lệ** của bằng chứng và **kiểm tra quyền** ở ranh giới đáng tin cậy. Việc “đã đăng nhập ở giao diện” không thay thế hai bước này.

### Ví dụ: chống truy cập trực tiếp đối tượng của người khác

Một nhân viên A mở trang hồ sơ của mình tại đường dẫn:

~~~http
GET /api/employees/152
Authorization: Bearer <access_token>
~~~

Kẻ tấn công có tài khoản hợp lệ đổi mã thành 153. Nếu backend chỉ kiểm tra token còn hạn mà không kiểm tra đối tượng 153 có thuộc phạm vi của A hay không, dữ liệu của người khác có thể bị lộ. Đây là lỗi **kiểm soát truy cập ở cấp đối tượng**; đăng nhập thành công không ngăn được nó.

Quyết định truy cập cần gắn với *chủ thể + hành động + tài nguyên + ngữ cảnh*, ví dụ:

~~~text
allow(
  subject = "employee-A",
  action = "read",
  resource = "employee-153",
  context = { role: "staff" }
) = false
~~~

## 3. Xác thực bảo vệ những thuộc tính nào?

Khi kẻ tấn công không thể mạo danh chủ thể hợp lệ, cơ chế xác thực góp phần bảo vệ:

- **Tính bí mật (confidentiality):** hạn chế việc người lạ lấy dữ liệu qua chức năng yêu cầu đăng nhập.
- **Tính toàn vẹn (integrity):** hạn chế việc người lạ thay đổi dữ liệu hoặc gọi các lệnh có tác động.
- **Tính sẵn sàng (availability):** giúp kiểm soát một số hình thức lạm dụng chức năng hoặc tiêu thụ tài nguyên theo tài khoản, nhưng không đủ để ngăn tấn công từ chối dịch vụ.
- **Khả năng quy trách nhiệm:** liên kết hành động với một tài khoản hoặc danh tính kỹ thuật để phục vụ điều tra, với điều kiện có log an toàn và chống chiếm quyền.

Những mục tiêu này đòi hỏi các lớp bổ trợ: phân quyền, mã hóa trên đường truyền và khi lưu trữ, kiểm tra dữ liệu đầu vào, kiểm soát lưu lượng, quản lý bí mật và giám sát. Xác thực không biến một API thiếu phân quyền thành API an toàn.

### Nguyên tắc thiết kế có thể kiểm chứng

1. **Mặc định từ chối:** thiếu, hết hạn hoặc không xác minh được bằng chứng thì không cấp truy cập.
2. **Kiểm tra tại nơi sử dụng:** mỗi yêu cầu đến tài nguyên được bảo vệ đều phải đi qua cơ chế xác thực và phân quyền phía server; tránh chỉ dựa vào kiểm tra ở trang đăng nhập.
3. **Mức bảo đảm phù hợp với rủi ro:** xem tin công khai và thay đổi tài khoản nhận tiền không nên cần cùng một mức xác thực.
4. **Quyền tối thiểu:** bằng chứng hợp lệ chỉ đại diện cho danh tính, phạm vi và thời hạn cần thiết; không được mặc nhiên trao quyền quản trị.
5. **Không cho hạ cấp âm thầm:** không dùng một phương thức phục hồi hoặc đăng nhập yếu để né yêu cầu xác thực mạnh của thao tác nhạy cảm.
6. **Có khả năng thu hồi:** khi tài khoản hoặc phiên bị chiếm quyền, hệ thống cần cơ chế khóa hoặc thu hồi phù hợp với loại phiên và token.

## 4. Từ đăng nhập đến truy cập tài nguyên

Một luồng bảo vệ tài nguyên thường có các bước sau:

1. **Nhận diện yêu cầu:** hệ thống biết tài nguyên nào và hành động nào đang được yêu cầu; tài nguyên công khai có thể không cần đăng nhập.
2. **Thu thập bằng chứng:** người dùng dùng mật khẩu, passkey hoặc MFA; dịch vụ có thể dùng chứng chỉ hay định danh máy.
3. **Xác minh bằng chứng:** bên đáng tin cậy kiểm tra bằng chứng, trạng thái tài khoản và yêu cầu bảo đảm.
4. **Duy trì trạng thái đã xác thực:** cấp cookie phiên hoặc token giới hạn phạm vi, thời gian sử dụng và ngữ cảnh.
5. **Đánh giá từng yêu cầu truy cập:** backend xác minh phiên/token, xác định chủ thể, kiểm tra quyền trên tài nguyên cụ thể rồi thực thi hoặc từ chối.
6. **Xử lý thay đổi rủi ro:** hết hạn, đăng xuất, đổi mật khẩu, mất thiết bị, tăng rủi ro hoặc thao tác nhạy cảm có thể buộc xác thực lại hay thu hồi quyền truy cập.

Một thông điệp “Đăng nhập thành công” chỉ chứng minh rằng **một bước** của luồng đã thành công. Nếu cookie có thể bị đánh cắp, token được chấp nhận sai đối tượng nhận hoặc endpoint bỏ qua kiểm tra quyền, tài nguyên vẫn không an toàn.

### Ví dụ logic phía backend

~~~typescript
async function viewInvoice(request, invoiceId) {
  // verifySessionOrToken phải kiểm tra đầy đủ loại bằng chứng được chấp nhận.
  const subject = await verifySessionOrToken(request);
  if (!subject) return { status: 401 };

  const invoice = await findInvoice(invoiceId);
  if (!invoice) return { status: 404 };

  const allowed = await canReadInvoice(subject, invoice);
  if (!allowed) return { status: 403 };

  return { status: 200, body: invoice };
}
~~~

Đây là mã giả minh họa trách nhiệm, không phải thư viện xác thực hoàn chỉnh. Trong sản phẩm thực tế, bước xác minh phải dùng cơ chế chuẩn đáng tin cậy; chính sách cũng có thể trả 404 thay vì 403 để tránh tiết lộ sự tồn tại của tài nguyên. Điểm cốt lõi là **không suy ra quyền đọc hóa đơn chỉ từ việc có token hợp lệ**.

## 5. Chọn bằng chứng xác thực theo giá trị tài nguyên

Không có một phương thức xác thực tối ưu cho mọi tài nguyên. Cần cân nhắc mức độ thiệt hại, khả năng chống mạo danh, trải nghiệm người dùng và khả năng phục hồi.

| Bằng chứng hoặc cơ chế | Điểm mạnh | Hạn chế cần lưu ý | Ngữ cảnh thường gặp |
|---|---|---|---|
| Mật khẩu | Phổ biến, dễ triển khai rộng | Có thể bị đoán, tái sử dụng, phishing hoặc lộ qua sự cố | Đăng nhập cơ bản, kết hợp MFA |
| MFA | Yêu cầu thêm yếu tố độc lập, giảm rủi ro từ mật khẩu bị lộ | OTP và push vẫn có thể bị phishing hoặc lừa chấp thuận | Tài khoản nhân sự, dữ liệu nhạy cảm |
| Passkey / WebAuthn | Dùng mật mã khóa công khai, gắn xác thực với miền dịch vụ; chống phishing tốt hơn | Cần thiết kế đồng bộ thiết bị và khôi phục tài khoản | Đăng nhập người dùng có yêu cầu bảo vệ cao |
| Chứng chỉ và mTLS | Xác thực danh tính máy/dịch vụ ở kết nối tương ứng | Phải quản lý khóa riêng, vòng đời chứng chỉ và chính sách cấp phát | Giao tiếp giữa dịch vụ, thiết bị quản lý |
| Phiên hoặc access token | Cho phép nhiều yêu cầu sau khi xác thực ban đầu | Có thể bị tái sử dụng nếu bị đánh cắp; phải giới hạn đối tượng, phạm vi và tuổi thọ | Web app, API, ứng dụng di động |

**Hai lưu ý quan trọng:**

- MFA không đồng nghĩa luôn chống phishing. Một mã OTP có thể bị kẻ tấn công chuyển tiếp trong thời gian thực; WebAuthn/passkey có cơ chế gắn với miền truy cập giúp chống dạng mạo danh trang đăng nhập này.
- Token là **vật mang quyền sử dụng trong một ngữ cảnh**, không tự nó chứng minh người đang cầm token chính là chủ tài khoản. Với bearer token, ai có token hợp lệ có thể dùng nó cho đến khi hết hạn hoặc bị thu hồi, nếu không có cơ chế ràng buộc bổ sung.

### Phân loại thao tác theo rủi ro

| Thao tác | Rủi ro điển hình | Quyết định thiết kế |
|---|---|---|
| Đọc nội dung công khai | Thấp | Có thể cho truy cập ẩn danh; giới hạn lưu lượng khi cần |
| Xem hồ sơ cá nhân | Trung bình | Phiên hợp lệ, phân quyền theo chủ sở hữu |
| Xuất toàn bộ dữ liệu khách hàng | Cao | Xác thực mạnh, quyền xuất riêng biệt, giám sát và giới hạn khối lượng |
| Đổi email khôi phục hoặc thêm thiết bị xác thực | Cao | Kiểm tra lại danh tính gần thời điểm thao tác và thông báo thay đổi |
| Chuyển tiền hoặc cấp quyền quản trị | Rất cao | Xác thực tăng cường (step-up), kiểm tra quyền giao dịch và chống lạm dụng |

**Step-up authentication** là yêu cầu xác thực bổ sung ngay trước thao tác có rủi ro cao, kể cả khi phiên đang hợp lệ. Tuy nhiên, step-up phải kiểm tra đúng hành động và ngữ cảnh; yêu cầu thêm mã OTP một lần nhưng vẫn cho phép sửa nội dung giao dịch sau khi xác minh sẽ tạo khoảng trống bảo vệ.

## 6. Bảo vệ phiên và token sau khi đăng nhập

Phần lớn hành động diễn ra **sau** lần đăng nhập ban đầu. Vì vậy, kiểm soát phiên là một phần thiết yếu của mục tiêu bảo vệ tài nguyên.

### Phiên web

Với cookie phiên, server cần đặt thuộc tính phù hợp như **Secure**, **HttpOnly** và **SameSite**; dùng HTTPS; bảo vệ khỏi session fixation bằng cách cấp lại định danh phiên khi chuyển trạng thái đăng nhập; áp dụng thời hạn và cơ chế hủy phiên. Cookie tự động được trình duyệt gửi có thể tạo rủi ro **CSRF**; thuộc tính SameSite giúp giảm rủi ro nhưng ứng dụng nhạy cảm còn cần cơ chế CSRF phù hợp.

Định danh phiên phải đủ ngẫu nhiên, không chứa thông tin bí mật dễ đoán, và không được ghi ra log. Đăng xuất cần vô hiệu hóa trạng thái server khi dùng phiên phía server. Khi đổi yếu tố xác thực hoặc phát hiện chiếm quyền, cân nhắc thu hồi các phiên khác.

### Token dùng cho API

Một access token chỉ nên được chấp nhận nếu đáp ứng **toàn bộ** điều kiện áp dụng:

- Chữ ký hoặc trạng thái token được xác minh bằng cấu hình đáng tin cậy; không tin thuật toán hay khóa do đầu vào không tin cậy tự quyết định.
- Đúng **issuer** và **audience** của dịch vụ; còn hạn theo các mốc thời gian liên quan.
- Có phạm vi (scope), quyền và danh tính thích hợp; server vẫn kiểm tra chính sách trên tài nguyên cụ thể.
- Được truyền và lưu theo cách hạn chế rò rỉ; không đưa vào URL, log hay thông báo lỗi.
- Có tuổi thọ hợp lý và chiến lược thu hồi/đổi mới tương ứng với mức rủi ro.

Không được dùng **ID token** của đăng nhập OpenID Connect như thể đó là access token để gọi API. ID token phục vụ bên ứng dụng xác nhận kết quả đăng nhập; access token được cấp cho tài nguyên hoặc API theo audience và quyền tương ứng.

Việc một JWT có cấu trúc hợp lệ hoặc có thể đọc được nội dung **không đồng nghĩa** nó được xác minh hay được phép truy cập một tài nguyên.

## 7. Những cách kẻ tấn công vượt qua lớp bảo vệ

Hãy xét cả tấn công vào **lúc xác thực**, **sau khi xác thực** và **khi khôi phục tài khoản**:

| Kịch bản | Ranh giới bị vượt qua | Cách giảm rủi ro |
|---|---|---|
| Credential stuffing: thử mật khẩu đã lộ ở dịch vụ khác | Kẻ tấn công mạo danh tài khoản | Passkey/MFA, phát hiện đăng nhập bất thường, giới hạn tốc độ có cân nhắc, chống lộ danh sách tài khoản |
| Phishing: giả trang đăng nhập hoặc lừa lấy mã OTP | Người dùng trao bằng chứng cho kẻ gian | WebAuthn/passkey, kiểm soát miền, hướng dẫn nhận diện lừa đảo, phát hiện bất thường |
| Replay: phát lại bằng chứng, token hoặc yêu cầu đã thu được | Bằng chứng được chấp nhận ngoài ngữ cảnh dự kiến | TLS, nonce/challenge và giới hạn thời gian khi giao thức hỗ trợ, chống phát lại giao dịch, bảo vệ token |
| Đánh cắp cookie hoặc access token | Chiếm phiên sau đăng nhập | Chặn XSS, bảo vệ lưu trữ, cookie an toàn, token ngắn hạn, phát hiện và thu hồi |
| Truy cập URL/tài nguyên của người khác | API tin rằng “đăng nhập” đồng nghĩa “được phép” | Kiểm tra quyền cấp đối tượng và hành động ở từng endpoint |
| Lạm dụng khôi phục tài khoản | Luồng phục hồi yếu hơn luồng đăng nhập | Token một lần, hết hạn ngắn, xác thực yêu cầu theo rủi ro, thông báo và thu hồi phiên khi phù hợp |
| Tấn công dò tài khoản hoặc đăng nhập hàng loạt | Lộ danh tính hoặc cạn tài nguyên xác thực | Phản hồi không tiết lộ tài khoản, giới hạn lưu lượng, giám sát, chống lạm dụng nhiều lớp |

**Replay** cần được hiểu theo ngữ cảnh: mật khẩu hay bearer token bị lấy cắp có thể bị dùng lại; các giao thức dựa trên challenge/nonce, ràng buộc người dùng hoặc giao dịch có thể giảm khả năng phát lại bằng chứng. Chỉ dùng HTTPS là cần thiết để chống nghe lén trên đường truyền, nhưng không xử lý được mọi trường hợp bằng chứng đã bị lộ tại điểm cuối.

Đối với mật khẩu, hệ thống phải lưu **bản băm mật khẩu với thuật toán chuyên dụng có salt** (ví dụ Argon2id theo cấu hình phù hợp), không lưu mật khẩu dạng rõ hoặc chỉ dùng hàm băm nhanh thông thường. Khi có MFA, chính sách khôi phục và thay đổi yếu tố phải được bảo vệ tương đương mức rủi ro; nếu không, kẻ tấn công sẽ nhắm vào đường vòng yếu nhất.

## 8. Thiết kế luồng bảo vệ tài nguyên theo trạng thái

Xem một phiên như chuỗi trạng thái thay vì một cờ “đã đăng nhập” bất biến:

~~~mermaid
stateDiagram-v2
    [*] --> ChuaXacThuc
    ChuaXacThuc --> DaXacThuc: Xác minh thành công
    ChuaXacThuc --> ChuaXacThuc: Sai/thiếu bằng chứng
    DaXacThuc --> CanTangCuong: Thao tác rủi ro cao
    CanTangCuong --> DaXacThuc: Step-up thành công
    CanTangCuong --> TuChoi: Không đạt điều kiện
    DaXacThuc --> HetHieuLuc: Hết hạn / thu hồi / đăng xuất
    HetHieuLuc --> ChuaXacThuc: Yêu cầu đăng nhập lại
    TuChoi --> DaXacThuc: Giữ phiên nếu chính sách cho phép
~~~

Ngay cả ở trạng thái **Đã xác thực**, hệ thống vẫn phải đánh giá quyền đối với từng tài nguyên. Nếu phiên bị thu hồi, dịch vụ không được tiếp tục chấp nhận bằng chứng hết hiệu lực; với JWT tự chứa, cần cân nhắc sự đánh đổi giữa thời hạn ngắn và khả năng thu hồi ngay.

### Ba quyết định phải tách biệt

| Câu hỏi | Bằng chứng/kiểm tra | Kết quả |
|---|---|---|
| Phiên này đại diện cho ai? | Xác minh session/token, trạng thái tài khoản | Một danh tính đã xác thực hoặc từ chối |
| Danh tính đó có được đọc hóa đơn này? | Vai trò, quan hệ sở hữu, trạng thái tài nguyên, chính sách | Cho phép hoặc từ chối |
| Có cần xác thực mạnh hơn trước khi đổi tài khoản nhận tiền? | Mức rủi ro của thao tác, thời điểm xác thực gần nhất | Yêu cầu step-up hoặc từ chối |

Đánh dấu quyền “admin” trong dữ liệu client không thay thế được chính sách phía server. Tương tự, một token có claim về vai trò chỉ là một đầu vào được tin cậy sau khi token đã được xác minh và claim còn phù hợp với chính sách/quyền hiện hành.

## 9. Tình huống thực hành: cổng quản lý nhân sự

**Bối cảnh:** Công ty có ba nhóm: nhân viên, quản lý và bộ phận nhân sự. Hệ thống lưu hồ sơ cá nhân, đơn nghỉ phép và bảng lương. Nhân viên dùng tài khoản để xem thông tin của mình; quản lý duyệt đơn trong nhóm; nhân sự xử lý bảng lương.

**Bài toán:** Thiết kế cách ngăn người dùng hợp lệ lấy dữ liệu không thuộc quyền của họ.

| Yêu cầu | Xác thực cần có | Kiểm tra quyền bắt buộc | Bảo vệ bổ sung |
|---|---|---|---|
| Nhân viên xem hồ sơ của chính mình | Phiên hợp lệ | Chủ thể khớp chủ hồ sơ hoặc có quyền phù hợp | TLS, kiểm soát phiên |
| Nhân viên sửa mã hồ sơ trên URL để xem hồ sơ khác | Phiên vẫn hợp lệ | Từ chối vì không sở hữu đối tượng | Ghi nhận sự kiện truy cập bị từ chối |
| Quản lý duyệt đơn nghỉ phép | Phiên hợp lệ | Người duyệt quản lý đúng nhân viên/nhóm và đơn đang ở trạng thái cho phép | Chống thực hiện lặp giao dịch |
| Nhân sự tải bảng lương hàng loạt | Xác thực đủ mạnh; step-up khi chính sách yêu cầu | Quyền xuất dữ liệu cụ thể, phạm vi bộ phận | Giới hạn khối lượng, audit, cảnh báo bất thường |
| Người lạ dùng liên kết đặt lại mật khẩu đã hết hạn | Không đủ bằng chứng | Từ chối cấp quyền/đổi mật khẩu | Token phục hồi một lần và hết hạn ngắn |

**Phân tích một kịch bản thất bại:**

1. Nhân viên A đăng nhập đúng mật khẩu và có phiên hợp lệ.
2. A dùng công cụ HTTP gửi yêu cầu xem bảng lương của nhân viên B.
3. Middleware xác nhận phiên A hợp lệ và chuyển yêu cầu đến hàm lấy dữ liệu.
4. Nếu hàm chỉ kiểm tra “đã đăng nhập”, B bị lộ thông tin dù xác thực hoạt động đúng.
5. Khắc phục tại lớp truy cập dữ liệu/API: xác định chủ thể A, hành động đọc và bảng lương B; áp dụng quy tắc chỉ người được ủy quyền mới được xem; ghi nhận truy cập bị từ chối.

**Bài học:** Hỏng phân quyền có thể làm thất bại mục tiêu bảo vệ tài nguyên ngay cả khi cơ chế xác thực không có lỗi.

## 10. Danh sách kiểm tra khi thiết kế hoặc rà soát

Dùng các câu hỏi sau khi xem một chức năng xử lý tài nguyên:

- [ ] Tài nguyên có chủ sở hữu, độ nhạy và danh sách hành động được phép rõ ràng?
- [ ] Điểm truy cập nào là công khai; điểm nào bắt buộc xác thực?
- [ ] API xác minh bằng chứng ở phía tin cậy, kể cả khi truy cập thẳng endpoint?
- [ ] Server kiểm tra quyền **trên tài nguyên cụ thể**, không chỉ vai trò chung hoặc trạng thái đăng nhập?
- [ ] Bằng chứng có thời hạn, đối tượng nhận, phạm vi và cơ chế thu hồi phù hợp?
- [ ] Cookie/token được bảo vệ khi truyền, lưu trữ và sử dụng; không lộ trong URL hoặc log?
- [ ] Thao tác nhạy cảm có xác thực tăng cường và kiểm tra ý định giao dịch khi cần?
- [ ] Tấn công phishing, replay, brute force, credential stuffing và chiếm phiên được xem xét?
- [ ] Quy trình mất thiết bị, đặt lại mật khẩu, thay MFA và thêm passkey có chống chiếm tài khoản?
- [ ] Hệ thống ghi log sự kiện xác thực, từ chối quyền và thay đổi quan trọng mà không ghi bí mật?
- [ ] Có kiểm thử cho yêu cầu thiếu xác thực, token hết hạn/sai audience, truy cập chéo tài khoản và quyền vừa bị thu hồi?

### Tự kiểm tra

**Câu 1.** Một API nhận JWT hợp lệ nhưng cho phép người dùng A tải hồ sơ của B. Lớp nào đang thiếu?  
**Gợi ý:** Kiểm tra quyền truy cập cấp đối tượng; xác thực JWT mới trả lời được danh tính/ngữ cảnh token.

**Câu 2.** Một ứng dụng dùng MFA mạnh nhưng cho phép đổi số điện thoại khôi phục chỉ bằng email dễ chiếm. Tài nguyên còn được bảo vệ tốt không?  
**Gợi ý:** Không đủ; đường khôi phục yếu có thể hạ cấp bảo đảm xác thực và giúp chiếm tài khoản.

**Câu 3.** Vì sao access token còn hạn vẫn cần được kiểm tra ở mỗi API?  
**Gợi ý:** API phải xác minh issuer/audience/thời hạn/tính hợp lệ và kiểm tra quyền của danh tính đối với hành động, tài nguyên cụ thể.

## Ghi nhớ

**Bảo vệ tài nguyên** là mục tiêu xuyên suốt của xác thực: ngăn chủ thể không chứng minh được danh tính phù hợp vượt qua ranh giới tin cậy, rồi để hệ thống áp dụng đúng chính sách truy cập. Một thiết kế an toàn xem xét cả thời điểm đăng nhập, vòng đời phiên/token, từng lời gọi API, thao tác rủi ro cao và đường khôi phục tài khoản.

Câu hỏi quan trọng nhất khi rà soát không phải “người dùng đã đăng nhập chưa?”, mà là: **“Với danh tính đã được xác minh ở mức nào, chủ thể này có được thực hiện chính hành động này trên chính tài nguyên này, tại thời điểm này không?”**
