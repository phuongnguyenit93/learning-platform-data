# Bảo vệ display code khỏi người khác

Bạn đang đăng nhập ứng dụng trên TV. TV hiện một mã ngắn, ví dụ **ABCD-EFGH**, cùng hướng dẫn mở trang xác minh của nhà cung cấp danh tính trên điện thoại để nhập mã. Người ngồi cạnh cũng nhìn thấy mã đó. Mã có phải mật khẩu truy cập tài khoản của bạn không? **Không.** Nhưng việc để người không liên quan sử dụng mã vẫn có thể gây **nhầm liên kết tài khoản với thiết bị**, và kẻ tấn công có thể lợi dụng chính cơ chế nhập mã để **lừa người dùng cấp quyền cho một thiết bị khác do kẻ tấn công kiểm soát**.

Trong **OAuth 2.0 Device Authorization Grant (RFC 8628)**, mã ngắn hiển thị để người dùng nhập trên thiết bị thứ hai được gọi là **user_code**, thường gọi trong giao diện là *display code* hoặc *device login code*. Mục đích của mã là giúp Authorization Server tìm ra **yêu cầu ủy quyền đang chờ của đúng thiết bị**. Nó **không phải access token, refresh token, ID token hoặc mật khẩu**. Tuy nhiên, mã vẫn là một phần của **giao dịch ủy quyền nhạy cảm theo thời gian**: phải hiển thị cho đúng người, trong đúng ngữ cảnh và tránh phát tán không cần thiết.

Bài học thuộc chương **Device authorization** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung đặt việc bảo vệ mã hiển thị vào mô hình tin cậy và vòng đời token: OAuth 2.0/OIDC, Authorization Server, Resource Server, JWT/opaque access token, refresh token, claims, scope, audience, lưu trữ, thu hồi và phòng ngừa credential bị đánh cắp hoặc phát lại.

Sau bài này, bạn có thể phân biệt các loại mã trong device flow, giải thích những kiểu tấn công liên quan đến mã hiển thị, thiết kế UI xác minh đáng tin, hạn chế mã bị chụp/lộ, chống đoán mã và phát lại, xây dựng kiểm thử âm, đồng thời xử lý sự cố khi mã hoặc token liên quan bị phát tán.

## 1. Vì sao Device Authorization Grant cần display code?

Nhiều thiết bị không thuận tiện cho việc mở browser đầy đủ hoặc nhập mật khẩu: TV, máy chơi game, máy in, thiết bị IoT có màn hình nhỏ và công cụ CLI chạy trong terminal. **Device Authorization Grant** tách quá trình đăng nhập thành hai kênh:

1. **Thiết bị cần quyền (device client)** liên hệ **device authorization endpoint** của Authorization Server (AS), xin một giao dịch chờ phê duyệt.
2. AS cấp **device_code**, **user_code**, **verification_uri** cùng thông tin hết hạn/polling.
3. Thiết bị hiển thị **user_code** và địa chỉ xác minh đáng tin; có thể hiển thị thêm QR nếu AS hỗ trợ.
4. **Người dùng** mở verification URI trên một **thiết bị có khả năng đăng nhập**, nhập hoặc xác nhận user_code, xác thực và xem thông tin cấp quyền.
5. AS ghi nhận quyết định **approve/deny** của người dùng cho giao dịch tương ứng.
6. Device client **poll token endpoint bằng device_code** theo nhịp được AS chỉ định. Khi được phê duyệt và điều kiện vẫn hợp lệ, AS có thể phát access token.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant D as TV / Device client
    participant AS as Authorization Server
    participant B as Browser trên điện thoại
    participant RS as Resource Server
    D->>AS: POST device_authorization_endpoint
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D-->>U: Hiển thị user_code và verification_uri
    U->>B: Mở địa chỉ xác minh đáng tin
    B->>AS: Nhập user_code hoặc xác nhận code đã điền
    AS->>U: Hiển thị client, quyền được yêu cầu, trạng thái liên kết
    U->>AS: Xác thực + chấp thuận/từ chối
    D->>AS: Poll token endpoint với device_code
    AS-->>D: pending hoặc access token khi được chấp thuận
    D->>RS: Bearer access token dành cho RS
    RS-->>D: Dữ liệu theo audience, scope và policy
~~~

**User_code dùng để liên kết hai kênh**, không phải credential để gọi API. Người dùng không nhập mật khẩu trên TV chỉ vì nó hiển thị mã; họ chỉ tương tác với **trang xác minh chính thức của AS** trên thiết bị đã chọn.

## 2. Bốn giá trị dễ bị nhầm trong device flow

Phản hồi từ device authorization endpoint có thể chứa:

~~~json
{
  "device_code": "<opaque-device-code>",
  "user_code": "ABCD-EFGH",
  "verification_uri": "https://auth.example.org/device",
  "verification_uri_complete": "https://auth.example.org/device?user_code=ABCD-EFGH",
  "expires_in": 600,
  "interval": 5
}
~~~

Đây là **dữ liệu giả**, không phải response của một dịch vụ cụ thể. \`verification_uri_complete\` là trường **tùy chọn**; các giá trị thời hạn và interval chỉ để minh họa. RFC 8628 quy định cấu trúc response và hành vi polling; không phải mọi AS đều cung cấp QR hoặc URI đã điền sẵn mã.

| Giá trị | Ai sử dụng? | Vai trò | Có nên hiển thị công khai? |
|---|---|---|---|
| **user_code / display code** | Người dùng nhập hoặc đối chiếu tại verification URI | Tìm đúng yêu cầu ủy quyền đang chờ | Hiển thị cho người đang liên kết thiết bị; **không phát tán rộng** |
| **device_code** | Device client gửi tới token endpoint | Định danh/bằng chứng của yêu cầu đang chờ khi polling | **Không hiển thị**; giữ tại client, không đưa vào QR/log |
| **verification_uri** | Người dùng mở trong browser | Trang xác minh/ủy quyền của AS | Có thể hiển thị như địa chỉ chính thức, phải lấy từ AS tin cậy |
| **verification_uri_complete** | Browser/QR trên thiết bị thứ hai | URI tiện lợi có thể mang sẵn user_code | Chỉ dùng trong flow hiện tại; tránh phát tán URL và tham số qua log/analytics |
| **access_token** | Device client dùng với Resource Server | Truy cập API theo audience/scope | **Không** hiện trên màn hình đăng nhập |
| **refresh_token** | Device client dùng với token endpoint nếu được cấp | Xin access token mới khi grant còn hiệu lực | **Không** hiện; lưu an toàn và áp dụng chính sách thu hồi |
| **OIDC ID token** | Client xác minh danh tính khi OIDC flow có cấp | Kết quả xác thực cho client | **Không** dùng thay user_code hoặc access token |

**Phân biệt mức độ bí mật:** user_code được thiết kế để người dùng nhìn và gõ, nên không thể đối xử như một private key không bao giờ hiển thị. Nhưng mã là **tham chiếu tới một authorization transaction**: người khác biết mã có thể thử truy cập chính giao dịch ấy. Trong khi đó, **device_code phải được bảo vệ chặt** vì nó được device client gửi tới token endpoint để nhận kết quả sau khi giao dịch được phê duyệt.

**Biết mỗi user_code không tự cấp được access token cho người nhìn thấy nó.** Để nhận token qua flow chuẩn, device client còn phải nắm device_code tương ứng và đáp ứng các điều kiện của AS. Tuy nhiên, người không liên quan sử dụng user_code vẫn có thể gây ra **liên kết sai tài khoản, từ chối dịch vụ hoặc thao túng quyết định phê duyệt** tùy kịch bản.

## 3. Hai kịch bản nguy hiểm có hướng tấn công ngược nhau

### Kịch bản A — Người khác thấy mã trên thiết bị của bạn

TV của bạn hiển thị \`ABCD-EFGH\). Một người đứng gần chụp được màn hình, mở **verification_uri** và nhập mã trước bạn. Nếu AS cho phép người ấy xác thực bằng tài khoản của họ rồi phê duyệt, **TV của bạn có thể được liên kết với tài khoản của họ**.

Hậu quả điển hình là **account confusion/account misbinding**: TV truy cập dữ liệu của tài khoản không mong muốn, hành vi/người dùng tiếp theo bị nhầm lẫn hoặc chịu tác động ngoài dự kiến. Tùy chính sách, AS có thể khóa giao dịch sau một lần quyết định và người dùng hợp pháp phải bắt đầu lại.

Điều này **không có nghĩa người chụp mã đã lấy được access token của tài khoản bạn**. Quyền nào được cấp phụ thuộc **ai đăng nhập, ai phê duyệt, trạng thái giao dịch và ai nắm device_code**. Không suy diễn “lộ display code = lộ toàn bộ tài khoản”.

### Kịch bản B — Kẻ tấn công đưa **mã của thiết bị họ** cho nạn nhân

Kẻ tấn công tự khởi tạo device flow trên thiết bị hoặc client mà họ kiểm soát và nhận **user_code X + device_code X**. Sau đó họ gửi user_code X qua email/chat hoặc giả danh nhân viên hỗ trợ, yêu cầu nạn nhân:

> “Để xác minh tài khoản, hãy vào trang chính thức này và nhập mã X.”

Nạn nhân có thể mở **đúng website đăng nhập thật** của AS, xác thực bằng tài khoản của mình, rồi vô tình **chấp thuận thiết bị của kẻ tấn công**. Kẻ tấn công vẫn giữ **device_code X**, tiếp tục polling và có thể nhận **access token của grant nạn nhân vừa phê duyệt**.

~~~mermaid
sequenceDiagram
    participant X as Thiết bị của attacker
    participant AS as Authorization Server
    actor U as Nạn nhân
    X->>AS: Khởi tạo device grant
    AS-->>X: device_code X + user_code X
    X-->>U: Dụ nhập user_code X qua chat/email
    U->>AS: Vào verification URI thật và nhập X
    AS->>U: Yêu cầu chấp thuận client/thiết bị
    U->>AS: Chấp thuận do hiểu nhầm
    X->>AS: Poll bằng device_code X
    AS-->>X: Access token nếu grant được duyệt
~~~

Đây là kiểu **device-code phishing / device authorization grant abuse**. Nó nguy hiểm vì URL đăng nhập có thể là **domain thật**: việc nhìn thấy HTTPS và trang login hợp lệ **không đủ** để kết luận giao dịch được khởi tạo bởi chính bạn.

**Bài học cốt lõi:** Chỉ nhập hoặc xác nhận mã của **thiết bị bạn đang chủ động kết nối**, và tại màn hình xác minh phải kiểm tra ứng dụng, thiết bị (nếu xác minh được), quyền được yêu cầu và tài khoản đang dùng. Một mã được gửi bất ngờ qua chat/email **không phải yêu cầu đăng nhập hợp lệ chỉ vì trang xác minh là trang chính thức**.

## 4. Threat model của mã hiển thị

| Tác nhân / tình huống | Khả năng | Mục tiêu hoặc hậu quả | Lớp giảm rủi ro |
|---|---|---|---|
| Người đứng gần nhìn màn hình TV | Đọc/chụp user_code | Liên kết nhầm thiết bị, làm phiền giao dịch | Mã ngắn hạn, hủy/thay mã, confirmation rõ ràng |
| Người xem ảnh chụp livestream | Nhìn mã đang hoạt động | Nhập mã trước chủ thiết bị | Không stream mã; thay mã khi nghi lộ |
| Người đoán mã tự động | Thử nhiều user_code | Ghép sai vào yêu cầu đang chờ | Entropy đủ, rate limiting, lockout/challenge thích hợp |
| Attacker có device_code của chính họ | Dụ người khác nhập user_code tương ứng | Nạn nhân cấp quyền cho thiết bị attacker | Anti-phishing UX, xác nhận client/thiết bị/scope, user education |
| Attacker có cả device_code và mã của người khác | Poll thay device/client khi grant được duyệt | Nhận token nếu các ràng buộc bị vượt | Giữ device_code bí mật, client binding, TLS và giới hạn thời hạn |
| SDK analytics, APM hoặc QR scanner | Thu URL có user_code | Phát tán giao dịch qua telemetry | Không log URL nhạy cảm, Referrer-Policy và cấu hình SDK |
| Người vận hành hoặc hệ thống hỗ trợ | Yêu cầu người dùng dán mã | Tăng nguy cơ lộ, social engineering | Không yêu cầu user_code qua kênh hỗ trợ trừ quy trình đặc biệt được phê duyệt |
| Người dùng trên thiết bị công cộng | Bỏ thiết bị ở màn hình chờ | Người khác tiếp tục flow | Timeout tự động, hủy pending grant, reset UI |

**Mối nguy lớn không phải chỉ là “mã bị nhìn thấy”, mà là người dùng hoặc hệ thống nhầm một mã với bằng chứng có quyền cao hơn thực tế.** Mã hiển thị phải được ràng buộc với **một giao dịch cụ thể**, và quyết định cấp token phải diễn ra trong **ngữ cảnh người dùng đã xác thực, với màn hình chấp thuận đủ rõ**.

## 5. Thiết kế màn hình display code cho người dùng thật

Một giao diện TV có thể hiển thị:

~~~text
KẾT NỐI TÀI KHOẢN

1. Trên điện thoại hoặc máy tính của bạn, mở:
   https://auth.example.org/device

2. Nhập mã đang hiển thị:
   ABCD-EFGH

3. Chỉ chấp thuận nếu bạn đang tự kết nối TV này.
   Kiểm tra ứng dụng, tài khoản và quyền trên trang xác minh.

Mã sẽ hết hiệu lực sau: [đồng hồ đếm ngược]
[Hủy]  [Lấy mã mới]
~~~

Đây là **UI minh họa**, không phải thiết kế bắt buộc của RFC. Những quyết định hữu ích:

1. **Hiển thị địa chỉ xác minh chính thức rõ ràng**, dễ đọc và kiểm tra; tránh viết tắt domain gây nhầm lẫn.
2. **Hiển thị mã dễ nhập** với ký tự/phân nhóm phù hợp chính sách AS; không tự thay đổi mã do AS phát.
3. **Nêu rõ người dùng chỉ được chấp thuận thiết bị họ đang trực tiếp kết nối**; không chuyển mã tới người khác qua tin nhắn.
4. **Hiển thị hết hạn**, hủy và lấy mã mới khi AS/client hỗ trợ; mã cũ phải không thể sử dụng sau thời gian quy định.
5. **Ẩn/loại mã khỏi màn hình khi flow kết thúc**, khi hủy hoặc khi hết hạn; đặc biệt với TV dùng chung và kiosk.
6. **Không hiển thị device_code, access_token, refresh_token hoặc ID token** trong giao diện.
7. **Không tạo screenshot/log tự động** chứa mã trong công cụ chẩn đoán hoặc trình quay màn hình; nếu ứng dụng có screen sharing, cần cảnh báo hoặc che thông tin khi phù hợp.

**Không được che toàn bộ user_code khiến người dùng hợp pháp không thể nhập mã.** Mã cần được nhìn thấy đúng lúc, đúng người; giảm **thời gian hiển thị và phạm vi nhìn thấy**, không làm hỏng trải nghiệm người dùng.

### Thiết bị dùng chung

Với TV trong phòng họp, khách sạn, thư viện hoặc quầy công cộng, nên cân nhắc:

- Màn hình chờ tự hết hạn và quay lại trạng thái chưa liên kết.
- Không tự tiếp tục giao dịch cũ khi người khác quay lại thiết bị.
- Xóa trạng thái pairing pending khi người dùng hủy, thiết bị đăng xuất hoặc reset.
- Kiểm soát quyền truy cập tài khoản đã liên kết về sau; **mã hiển thị là bước liên kết ban đầu**, không thay chính sách logout và xóa token.

## 6. Verification URI phải đáng tin, không phải URL tùy ý

Device client phải dùng **device authorization endpoint, verification URI và token endpoint** từ Authorization Server mà ứng dụng đã được cấu hình tin cậy. Không để một HTTP response tùy ý, QR scanner lạ hoặc tham số do người ngoài gửi thay đổi issuer/đích của flow.

Ví dụ:

~~~text
Authorization Server đã cấu hình:
  issuer: https://auth.example.org

Device authorization response:
  verification_uri: https://auth.example.org/device
  verification_uri_complete:
    https://auth.example.org/device?user_code=ABCD-EFGH
~~~

**verification_uri_complete** có thể được mã hóa thành QR để người dùng khỏi gõ code, nhưng:

- QR phải dẫn đến **địa chỉ thuộc AS đã tin**, không phải short link hoặc domain lạ do người khác tự thay.
- Nếu URL đã có user_code, người dùng nên **đối chiếu mã hiện ra trên browser với mã trên thiết bị** khi trải nghiệm AS hỗ trợ.
- Không click QR/link được gửi bất ngờ trong email/chat chỉ vì nó chứa domain chính thức; **đối chiếu nguồn của giao dịch**.
- Tránh đưa tham số user_code và dữ liệu OAuth vào analytics, Referer, browser history hoặc công cụ thu thập tự động ngoài phạm vi cần thiết.
- Với hệ thống hỗ trợ QR, nên có **đường nhập mã thủ công** để người dùng kiểm tra domain và xử lý khi QR không an toàn/không dùng được.

**Chỉ xác thực domain không đủ chặn device-code phishing.** Attacker có thể trỏ nạn nhân tới **đúng AS** để nạn nhân phê duyệt grant của attacker. Vì vậy cần cả **trusted URI** lẫn **transaction-specific user confirmation**.

## 7. Màn hình xác minh phải cho biết người dùng đang phê duyệt gì

Sau khi user_code được nhận diện, AS không nên coi mã đó là một lệnh “đăng nhập ngay”. Trang xác minh phải:

1. Đưa người dùng tới **quy trình xác thực phù hợp** hoặc sử dụng session đang đăng nhập với bảo vệ cần thiết.
2. Xác định **client/device grant pending** dựa trên user_code và trạng thái đáng tin phía AS.
3. Hiển thị **tên ứng dụng/client đã đăng ký**, không chỉ tên tự khai tùy ý trong request.
4. Hiển thị **quyền/scope và resource** đang được yêu cầu ở mức dễ hiểu; hành động nhạy cảm có thể cần step-up hoặc confirmation rõ hơn.
5. Nếu AS có **dữ liệu nhận diện thiết bị đáng tin cậy**, giúp người dùng đối chiếu thiết bị đang chờ; không khẳng định chính xác tên/loại thiết bị chỉ từ chuỗi attacker tự gửi.
6. Cung cấp **Approve** và **Deny** tách biệt; không tự phê duyệt khi chỉ nhập code hoặc truy cập \`verification_uri_complete\`.
7. Ràng buộc quyết định với **account đang xác thực**, grant hiện tại, client, scope, resource, thời hạn và trạng thái pending.
8. Sau khi approve/deny, **không thể dùng lại user_code** để tạo thêm một quyết định hoặc chuyển quyền sang account khác.

Một mẫu giao diện:

~~~text
Bạn có đang kết nối thiết bị này không?

Ứng dụng: Example TV (đã đăng ký)
Mã giao dịch: ABCD-EFGH
Tài khoản đang dùng: <account-visible-to-user>
Yêu cầu: Xem danh sách nội dung của bạn

Chỉ tiếp tục nếu mã này đang hiển thị trên thiết bị của bạn.
Không chấp thuận mã được gửi từ người lạ hoặc bộ phận hỗ trợ.

[Từ chối]    [Chấp thuận]
~~~

Ví dụ chỉ là mô tả UX. **Tên ứng dụng hoặc thiết bị không phải chứng cứ quyền** nếu nguồn hiển thị không tin cậy; AS phải ràng buộc với client registration và grant. Không hiển thị thông tin nhạy cảm không cần thiết cho người chỉ đang nhập một mã chưa hợp lệ.

### Trường hợp đa tài khoản

Người dùng có thể đăng nhập nhiều tài khoản trên browser. Trước khi phê duyệt, giao diện phải cho họ biết **tài khoản nào sẽ được liên kết với thiết bị**. Nếu là account không mong muốn, họ phải có cách đổi account hoặc từ chối và bắt đầu lại. Đây là cách giảm **account misbinding**, không chỉ tăng bảo mật chống attacker.

## 8. Mã phải ngắn để nhập được nhưng khó đoán

Trong RFC 8628, **user_code là mã nhập bằng con người**, vì vậy thiết kế thường cân bằng ba yếu tố:

- **Khả dụng:** ngắn, dễ đọc, có nhóm ký tự dễ nhập trên màn hình lớn/nhỏ.
- **Entropy:** khó đoán trong thời gian giao dịch còn hiệu lực.
- **Bảo vệ server:** giới hạn tốc độ thử và giám sát lạm dụng tại verification endpoint.

Một đoạn mã **ABCD-EFGH** trông có tám ký tự, nhưng lượng entropy thực tế phụ thuộc **bảng chữ cái, cách sinh và các ràng buộc loại bỏ ký tự**, không chỉ số ký tự. Không sinh user_code bằng timestamp, số thứ tự hoặc bộ đếm tăng dần.

### Mô hình ước tính không gian mã

Giả sử mã được chọn độc lập, đều trong bảng chữ cái kích thước \(A\) và có \(L\) ký tự ngẫu nhiên:

\[
N = A^L,\qquad H = L\log_2 A
\]

Trong đó \(N\) là số mã khả dĩ và \(H\) là entropy lý tưởng tính theo bit. Dấu phân nhóm như **-** có thể chỉ để đọc dễ hơn, không tự thêm entropy nếu cố định.

**Ví dụ minh họa**, nếu bảng có 20 ký tự và tạo ngẫu nhiên 8 ký tự:

\[
N = 20^8 = 25{,}600{,}000{,}000
\]

Không nên diễn giải con số này thành “đã an toàn tuyệt đối”: server còn có nhiều giao dịch pending đồng thời, tốc độ đoán, vòng đời mã, cách phân phối và chất lượng CSPRNG. Một mã có không gian lớn vẫn có thể dễ tấn công nếu verification endpoint cho phép thử hàng triệu lần mà không giới hạn.

### Rate limiting quan trọng như entropy

Authorization Server nên:

- Áp dụng **throttling/rate limiting** cho nhập user_code theo tài khoản/session, nguồn request và tín hiệu rủi ro phù hợp.
- Giới hạn số lần đoán, tránh cho attacker biết quá nhiều thông tin về **mã nào đang tồn tại**.
- Dùng CSPRNG và phân phối mã để giảm đoán trúng; quản lý va chạm user_code giữa các grant đang chờ.
- Hết hạn các yêu cầu pending đúng thời hạn, dọn trạng thái liên quan.
- Cân nhắc challenge/bảo vệ bổ sung khi hành vi đoán mã bất thường; tránh khóa hàng loạt người dùng hợp pháp do attacker cố tình gây DoS.
- Không cho nhập user_code hợp lệ mà **bỏ qua bước xác thực và consent**.

**Người có user_code không tự có quyền gọi Resource Server**, nhưng có thể thử tìm pending grant. Do đó phải bảo vệ cả **khâu nhập mã** và **khâu phê duyệt**.

## 9. User_code và device_code phải có vòng đời riêng

Device authorization endpoint trả về một cặp mã và TTL. Vòng đời ở mức khái niệm:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: AS tạo device grant
    PENDING --> APPROVED: User xác thực và chấp thuận
    PENDING --> DENIED: User từ chối
    PENDING --> EXPIRED: Quá expires_in
    PENDING --> CANCELLED: AS/client hủy nếu hỗ trợ
    APPROVED --> REDEEMED: Device poll hợp lệ và nhận token
    APPROVED --> EXPIRED: Grant quá hạn trước khi hoàn tất
    DENIED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    REDEEMED --> [*]
~~~

Sơ đồ là **mô hình thiết kế**, không phải trạng thái bắt buộc phải lưu nguyên tên. AS cần bảo đảm chuyển trạng thái **nhất quán** khi có nhiều người cùng nhập mã hoặc nhiều lượt polling, để một giao dịch không bị phê duyệt cho hai tài khoản khác nhau hoặc tạo nhiều nhánh token trái chính sách.

| Thời điểm | Display code | Device code và quyền cấp token |
|---|---|---|
| Mới cấp | Được hiển thị để người dùng tìm giao dịch | Device client giữ kín và poll theo interval |
| Chưa ai nhập | Còn hiệu lực trong TTL | AS trả \`authorization_pending\` khi token endpoint bị poll |
| Người dùng chấp thuận | Không cần tiếp tục hiển thị; AS gắn decision với grant | Device có thể nhận token khi poll hợp lệ |
| Người dùng từ chối | Không được dùng lại để xin consent | Token endpoint trả \`access_denied\` |
| Mã hết hạn | Xóa khỏi màn hình hoặc báo cần lấy mã mới | Token endpoint trả \`expired_token\` theo ngữ cảnh |
| Đã hoàn tất | Không dùng lại user_code cho giao dịch khác | Device grant đã tiêu thụ; token được quản lý trong vòng đời riêng |

**Không tái sử dụng một user_code vừa hết hạn hoặc đã kết thúc như thể nó vẫn đại diện cho phiên cũ.** Nếu AS có tái sử dụng giá trị mã sau thời gian đủ dài, nó vẫn phải bảo đảm không gây nhầm lẫn với pending grants và không làm mất tính nhất quán của giao dịch.

## 10. Đúng giao thức: device authorization response và token polling

### 10.1. Thiết bị xin mã

Một **public device client** minh họa gửi:

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

client_id=example-tv&scope=content%3Aread
~~~

**Đây không phải request đăng nhập bằng mật khẩu.** AS xác định client, quyền được phép, đăng ký device grant và tạo code. Với loại client/profile yêu cầu xác thực client, AS áp dụng phương thức xác thực tương ứng; không xem \`client_id\` của public client như một shared secret.

### 10.2. Device client poll token endpoint bằng device_code

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=<opaque-device-code>&client_id=example-tv
~~~

**Không đặt user_code trong tham số device_code**. User_code được dùng ở **verification URI phía người dùng**; device_code được gửi từ **device client tới token endpoint**. Grant type là:

~~~text
urn:ietf:params:oauth:grant-type:device_code
~~~

### 10.3. Khi người dùng chưa chấp thuận

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "authorization_pending"
}
~~~

Khi cần giảm tốc độ polling, AS có thể trả:

~~~json
{
  "error": "slow_down"
}
~~~

Theo RFC 8628, client phải tôn trọng **interval** do AS cấp; nếu không được cấp, giá trị polling mặc định là **5 giây**. Khi gặp **slow_down**, client phải tăng khoảng cách polling theo quy tắc của RFC, bao gồm tăng **ít nhất 5 giây** so với interval đang dùng. Khi gặp \`access_denied\` hoặc \`expired_token\`, dừng xử lý giao dịch cũ theo giao thức.

**Không polling nhanh liên tục** để “thấy token sớm hơn”. Polling là hoạt động trao đổi với token endpoint và có thể tạo tải hoặc kích hoạt biện pháp chống abuse; nó không làm tăng tốc người dùng phê duyệt.

### 10.4. Thành công không làm display code thành access token

Một response thành công có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<access-token-for-resource-server>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "content:read"
}
~~~

Chỉ sau khi AS phát hành **access token** thì device client mới có credential gọi API. Việc user_code từng được hiển thị và nhập đúng **không cho phép API trực tiếp chấp nhận user_code**.

## 11. Đừng xác thực nhầm tài khoản hoặc chấp thuận nhầm thiết bị

Một tình huống dễ gặp trên TV dùng chung:

1. Người A mở flow đăng nhập, TV hiện mã \`ABCD-EFGH\`.
2. A bỏ đi; người B tới, nhìn mã và nhập trên điện thoại của B.
3. AS xác thực B và chấp thuận.
4. TV nhận token **cho tài khoản B**, không phải A.
5. A quay lại, tưởng TV đã vào tài khoản A và thao tác nhầm.

Để giảm rủi ro:

- Trang xác minh cho người dùng thấy **tài khoản sẽ dùng** và **client/device đang được liên kết**.
- Thiết bị có màn hình trạng thái **đang chờ / đã kết nối / kết nối tài khoản nào** theo mức dữ liệu có thể hiển thị an toàn.
- Khi không còn người thực hiện, **hủy pending authorization** hoặc để code hết hạn; không giữ màn hình mã vô hạn.
- Với thiết bị công cộng, có **sign-out/reset** rõ ràng và cơ chế xóa token local.
- Với ứng dụng có nhiều tài khoản/tenant, cần xác minh quyền account/tenant, không mặc định user nhập mã nghĩa là đã chọn đúng account.

Không yêu cầu người dùng nhập **mật khẩu hoặc refresh token vào TV** chỉ để “chứng minh” mã thuộc về họ. Device flow tồn tại chính để tránh đưa credential tương tác của người dùng lên thiết bị có đầu vào hạn chế hoặc khó tin cậy hơn.

## 12. Phòng device-code phishing bằng xác nhận giao dịch

Nguyên tắc “chỉ mở URL chính thức” **cần nhưng chưa đủ**. Attacker có thể tạo flow bằng client hợp lệ hoặc client giả dạng tên quen thuộc và khiến nạn nhân đăng nhập ở website thật rồi chấp thuận.

### Dấu hiệu đáng nghi ở phía người dùng

- Nhận mã từ người lạ, nhân viên hỗ trợ không xác minh hoặc bot qua **email, chat, SMS, cuộc gọi**.
- Bị yêu cầu nhập mã khi **không có thiết bị của chính mình đang chờ kết nối**.
- Trang consent nói **ứng dụng, account hoặc quyền yêu cầu khác dự kiến**.
- Có yêu cầu khẩn cấp như “nhập mã để tránh khóa tài khoản”, “xác nhận lương”, “khôi phục đăng nhập” không liên quan đến thao tác trên thiết bị.
- QR hoặc short link chuyển qua domain lạ, dù trang cuối là AS thật.

### Thiết kế phòng thủ ở Authorization Server

AS có thể tăng chất lượng xác nhận bằng cách:

1. Hiển thị **client name đáng tin từ đăng ký** và cảnh báo không chấp thuận mã không xuất phát từ thiết bị chính mình.
2. Cho người dùng thấy **scope/resource** và account chính xác; ngăn màn hình “Allow” một cú click thiếu ngữ cảnh.
3. Tăng yêu cầu **step-up/authentication freshness** cho quyền nhạy cảm theo policy.
4. Giới hạn số pending grants, tốc độ tạo mã, tốc độ nhập mã và các dấu hiệu abuse theo client.
5. Giám sát bất thường như nhiều users khác nhau phê duyệt các device grants của cùng client trong thời gian ngắn, không thu thập quá mức dữ liệu nhạy cảm.
6. Cho phép người dùng **từ chối** và kiểm tra/thu hồi các ứng dụng/thiết bị đã cấp quyền.

**Không có một trường \`device_name\` tự khai nào đủ làm chứng cứ chính xác rằng người dùng đang kết nối TV cụ thể.** Nếu AS muốn hiển thị thông tin thiết bị, cần xác định nguồn tin cậy và mức bảo đảm của thông tin ấy. Trải nghiệm không nên đưa ra cam kết bảo mật vượt khả năng hệ thống.

## 13. QR code và verification_uri_complete: tiện nhưng dễ bị chuyển tiếp

QR code có thể chứa \`verification_uri_complete\` để browser tự điền user_code. Điều này giảm lỗi gõ, nhưng cũng có thể khiến người dùng **không nhận ra mã đang được dùng thuộc giao dịch nào**.

Rủi ro đáng lưu ý:

- Ảnh QR hiển thị trên livestream, ảnh chụp hoặc trong log hỗ trợ; người khác có thể mở URI kèm user_code.
- QR bị **dán đè** trên kiosk/TV vật lý hoặc nhúng trong thông báo giả khiến người dùng mở sai URL.
- Browser/session replay/analytics ghi URL có query **user_code**.
- Một trang web bên thứ ba được mở từ trang xác minh có thể nhận tham số URL thông qua **Referer** nếu không cấu hình phù hợp.
- Attacker gửi QR của **giao dịch do họ khởi tạo**, thúc ép nạn nhân chấp thuận.

Biện pháp:

- Hiển thị **hostname chính thức** cạnh QR, cùng mã dạng văn bản để người dùng đối chiếu.
- Nếu có \`verification_uri_complete\`, trang AS phải hiển thị **mã, ứng dụng và quyền đang được chấp thuận**, không tự approve chỉ vì query hợp lệ.
- Áp dụng **Referrer-Policy** phù hợp cho trang chứa mã, tránh third-party scripts không cần thiết và giới hạn telemetry.
- Không gửi QR/user_code qua email hay mạng xã hội khi không phải quy trình được quản trị.
- Có thể cho phép **nhập mã thủ công** thay QR, giúp người dùng chủ động mở địa chỉ đáng tin.

**QR không phải cơ chế mã hóa hoặc xác minh danh tính.** Nó chỉ là một cách biểu diễn dữ liệu URL; scanner phải bảo vệ người dùng trước địa chỉ tùy ý, và AS phải xác nhận authorization transaction trước khi cấp quyền.

## 14. Bảo vệ ở ứng dụng: đừng để user_code lọt vào log

Trong quá trình phát triển, những đoạn code sau dễ khiến giao dịch bị phát tán:

~~~java
// SAI: không ghi raw response hoặc URL có mã liên kết.
log.info("device authorization response={}", responseBody);
log.debug("verification link={}", verificationUriComplete);
log.info("user_code={}", userCode);
~~~

Thay bằng **audit metadata có cấu trúc**, không chứa user_code hoặc device_code:

~~~json
{
  "event": "device_authorization_started",
  "request_id": "req-example-401",
  "client_id": "example-tv",
  "result": "pending",
  "expires_in_bucket": "5-15m"
}
~~~

Một audit khi kết thúc:

~~~json
{
  "event": "device_authorization_finished",
  "request_id": "req-example-401",
  "result": "denied",
  "reason_code": "USER_DENIED"
}
~~~

Đây là schema minh họa, không phải trường tiêu chuẩn của OpenTelemetry hay RFC 8628. **client_id** chỉ nên đến từ registration/kiểm tra đáng tin, không coi chuỗi tự khai trong request chưa xác thực là danh tính đã được xác minh. Request ID phải là giá trị an toàn do server/ứng dụng kiểm soát, không lấy từ raw token hay mã hiển thị.

Những vị trí cần kiểm tra:

| Lớp | Trường dễ lộ | Biện pháp |
|---|---|---|
| **TV/CLI app** | user_code trên console, screenshot, crash dump | Không ghi vào log; chỉ hiển thị ở UI có thời hạn |
| **AS device endpoint** | Response chứa device_code/user_code | Không log raw response; allowlist audit |
| **AS verification page** | Query chứa user_code | Không ghi raw URL query vào analytics/access log |
| **AS token endpoint** | Request body có device_code; response có token | Không ghi request/response body hoặc Authorization |
| **API gateway / reverse proxy** | URI, headers, body của device flow | Redact/loại từ nguồn, hạn chế debug traffic |
| **APM/RUM/session replay** | QR/link, UI màn hình xác minh | Mask/disable capture nhạy cảm, kiểm payload xuất |
| **Support tools** | Ảnh chụp mã, ticket, chat | Không yêu cầu chia sẻ mã; hướng dẫn hủy và lấy mã mới |

Ngay cả nếu user_code không phải access token, việc log nó có thể tạo đường **tương quan authorization sessions** và làm tăng nguy cơ sử dụng trái ngữ cảnh trong thời gian mã còn hiệu lực. **Không cần log mã thô để debug device flow**.

## 15. Java: phân tách rõ display code và polling credential

Ví dụ thiết kế Java cho device client dưới dạng **pseudocode có kiểu**:

~~~java
// Mô hình minh họa; không phải OAuth SDK hoàn chỉnh.
record DeviceAuthorizationView(
        String verificationUri,
        String userCode,
        long expiresInSeconds
) {}

record DevicePollState(
        String deviceCode,
        String clientId,
        long intervalSeconds
) {}

final class DeviceFlowCoordinator {
    // Chỉ trả về dữ liệu cần hiển thị.
    DeviceAuthorizationView toUserView(DeviceAuthResponse r) {
        return new DeviceAuthorizationView(
                r.verificationUri(),
                r.userCode(),
                r.expiresInSeconds()
        );
    }

    // Chỉ thành phần polling được tiếp cận deviceCode.
    DevicePollState toPollState(DeviceAuthResponse r, String clientId) {
        return new DevicePollState(
                r.deviceCode(),
                clientId,
                r.intervalSeconds()
        );
    }

    // Audit không nhận userCode, deviceCode hoặc accessToken.
    void auditResult(String requestId, String safeResultCode) {
        // Ghi requestId và safeResultCode đã được kiểm soát.
    }
}
~~~

**Không đưa \`DevicePollState\` vào hàm render UI, analytics serializer, exception hoặc log.** Các kiểu record trong ví dụ Java **không tự đảm bảo bí mật**: Java record có \`toString()\` tự sinh nên **không được log toàn bộ record** này. Trong ứng dụng thực, nên dùng kiểu credential chuyên dụng có chính sách serialization/toString an toàn và quyền truy cập giới hạn.

Tại phía AS, các trạng thái pending/approved/redeemed phải được lưu theo cách **atomic** để hai polling requests hoặc hai confirmation requests chạy đồng thời không cấp nhiều token trái policy. Không tự xây logic OAuth với chỉ một \`Map\` trong bộ nhớ nếu AS chạy nhiều instance.

### Pseudocode hiển thị mã có thời hạn

~~~text
startDeviceFlow():
    response = requestDeviceAuthorizationAtTrustedAS()
    verifyResponseShapeAndExpectedVerificationUri(response)
    state = storeDeviceCodePrivately(response.device_code)

    showToUser(
        officialVerificationUri = response.verification_uri,
        displayCode = response.user_code,
        expiresAt = now + response.expires_in
    )

    while not expiredOrCancelled(state):
        pollTokenEndpoint(state.device_code, respectingInterval)
        if approved:
            hideDisplayCodeAndErasePendingCode()
            storeIssuedTokensSafely()
            return
        if deniedOrExpired:
            hideDisplayCodeAndErasePendingCode()
            showSafeFailureMessage()
            return

    hideDisplayCodeAndErasePendingCode()
    offerExplicitRestart()
~~~

Đây là logic khái niệm: request thực phải xử lý HTTP, TLS, lỗi OAuth, timeouts, client authentication theo loại client, đồng hồ tin cậy và đồng bộ polling. **Không đưa user_code vào token polling request**.

## 16. Sau khi người dùng đồng ý: access token cũng phải đúng mục đích

Authorization Server có thể cấp access token sau khi flow device hoàn tất. Nhưng **mã display đúng và được phê duyệt không tự chứng minh API request sau đó hợp lệ**.

| Phần tử | Bên nhận dự kiến | Điều cần kiểm |
|---|---|---|
| **user_code** | Trang verification của AS | Pending grant tồn tại, thời hạn, trạng thái; user consent |
| **device_code** | Token endpoint của AS | Đúng device grant/client, trạng thái, TTL, polling và một lần nhận kết quả theo policy |
| **JWT access token** | Resource Server theo \`aud\` | Chữ ký/key/issuer, \`aud\`, \`exp\`, type/profile, scope, policy tài nguyên |
| **Opaque access token** | Resource Server theo hợp đồng AS | Introspection hoặc cơ chế trạng thái đáng tin, đúng loại token/audience/scope |
| **Refresh token** | Token endpoint của AS | Client binding, grant, rotation/replay/revocation theo chính sách |
| **OIDC ID token** | OIDC client | Chữ ký, issuer, audience client, thời hạn và nonce/flow khi áp dụng |

Ví dụ access token JWT được phát cho Content API:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "content-api",
  "client_id": "example-tv",
  "scope": "content:read",
  "iat": 1795400000,
  "exp": 1795400900,
  "jti": "access-example-107"
}
~~~

Đây chỉ là **claims giả**, không phải JWT đã ký. JWT access token phải được xác minh đúng profile/chữ ký/claims bởi Resource Server; opaque token cần nguồn introspection tin cậy. API **không** được nhận user_code, device_code, ID token hoặc refresh token như Bearer access token.

Nếu AS đã cấp access token nhưng sau đó người dùng phát hiện mình phê duyệt thiết bị lạ, **hủy màn hình mã không đủ thu hồi token đã cấp**. Cần revoke grant/token và đánh giá access token còn hạn theo chính sách của hệ thống. JWT tự chứa có thể còn hiệu lực tại API đến \`exp\` nếu không có cơ chế thu hồi bổ sung.

## 17. Ma trận kiểm thử: display code không bị dùng sai

Một bộ kiểm thử tốt cần bao phủ cả **giao diện, Authorization Server, token endpoint và telemetry**, không chỉ mã HTTP.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| **S01** | Device client được phép xin mã | AS trả user_code/device_code/verification_uri/TTL hợp lệ |
| **S02** | Người dùng chủ động mở URI chính thức, nhập đúng mã, xác thực và chấp thuận | Device có thể nhận access token đúng grant/scope |
| **S03** | Người dùng chọn từ chối | Device polling kết thúc theo lỗi \`access_denied\`; không cấp token |
| **F01** | Nhập user_code sai | Không tìm/không phê duyệt grant; trả thông báo an toàn |
| **F02** | Nhập user_code của giao dịch đã hết hạn | Không phê duyệt/cấp token từ grant cũ |
| **F03** | Nhập user_code đã phê duyệt hoặc dùng xong | Không tạo thêm một lần cấp quyền |
| **F04** | Cùng user_code bị thử nhiều lần tự động | Rate limit/throttling và giám sát lạm dụng hoạt động |
| **F05** | Hai user sessions cố chấp thuận cùng một pending code | Một quyết định nhất quán, không liên kết hai account |
| **F06** | Người dùng đang ở account B nhưng nghĩ đang kết nối account A | Trang xác minh hiển thị account thực tế, cho phép deny/switch |
| **F07** | Request xác minh chưa đăng nhập nhưng chỉ có user_code | Không tự chấp thuận; yêu cầu auth/consent đúng policy |
| **F08** | QR dẫn sang domain khác issuer đã tin | Device/app hoặc người dùng được cảnh báo; không coi là URI xác minh hợp lệ |
| **F09** | verification_uri_complete mang user_code nhưng browser chưa chấp thuận | Không tự động cấp token chỉ vì URL được mở |
| **F10** | User_code bị phát qua chat, người khác chấp thuận | Flow phải hiển thị đúng client/account/scope và cảnh báo; có cơ chế từ chối/thu hồi |
| **F11** | Display code bị đưa vào error log, analytics hoặc tracing | Test phát hiện lỗi; payload telemetry không chứa mã thô |
| **F12** | Device_code vô tình xuất hiện trong view model/QR | Test phải phát hiện lỗi; không phơi polling credential |
| **F13** | Poll token endpoint bằng **user_code** thay device_code | Bị từ chối |
| **F14** | Poll bằng device_code chưa được phê duyệt | \`authorization_pending\`, không có token |
| **F15** | Poll nhanh hơn interval hoặc gặp \`slow_down\` | Client điều chỉnh nhịp, không tiếp tục flood token endpoint |
| **F16** | Poll device_code hết hạn | \`expired_token\` hoặc lỗi hợp lệ theo profile; không cấp token |
| **F17** | Hai poll requests đồng thời cho một grant đã approve | Không tạo nhiều nhánh phát hành trái policy |
| **F18** | Người dùng hủy pending flow trên UI (nếu hỗ trợ) | AS/client xử lý theo cơ chế hủy, không chấp thuận grant đã vô hiệu hóa |
| **F19** | Token được cấp cho \`content-api\` bị gửi đến \`orders-api\` | Resource Server từ chối sai audience |
| **F20** | Refresh token bị gửi làm Bearer tới Resource Server | API từ chối sai loại credential |
| **F21** | Thiết bị dùng chung đã đăng xuất | Không còn access/refresh token hoặc phiên local theo chính sách |
| **F22** | Nạn nhân đã chấp thuận thiết bị lạ, sau đó revoke | AS ngừng grant/token theo khả năng; RS thực thi chính sách thu hồi |
| **F23** | Gateway/APM bật chế độ debug khi flow chạy | Không có raw user_code, device_code, access/refresh token trong log |
| **F24** | Hệ thống nhiều AS/issuer | Device client dùng đúng endpoint của issuer tin cậy, không trộn các grants |

**Kiểm thử cần quan sát kết quả thật ở backend**: token issuance count, trạng thái grant, user account liên kết, quyền API và bản sao log. Một response lỗi **400** không đủ để kết luận hệ thống không cấp token nếu có race condition hoặc side effect đã xảy ra trước đó.

### Test mô phỏng hai người nhập một mã

~~~text
Given:
  Device D nhận user_code U1 và device_code D1.
  U1 còn hạn, pending và chưa có account phê duyệt.

When:
  Browser session A và B gần như đồng thời xác nhận U1.

Then:
  AS áp dụng trạng thái grant nhất quán/atomic.
  Không ghi nhận hai account phê duyệt cùng một device grant.
  Không phát nhiều token families trái policy.
  Audit chỉ chứa metadata an toàn, không chứa U1/D1 thô.
~~~

Đây là test kiến trúc, không phải yêu cầu lúc nào cũng phải từ chối cả hai bên. Chính sách có thể chọn một quyết định thắng cuộc, hoặc yêu cầu bắt đầu flow mới khi xung đột; **điều bắt buộc là không có trạng thái quyền mâu thuẫn**.

## 18. Ứng cứu khi display code hoặc device_code bị lộ

**Nếu chỉ user_code đang hiển thị bị chụp**, đánh giá xem giao dịch còn pending, có ai đã phê duyệt, và thiết bị có thực sự liên kết với đúng account không. Người dùng có thể **hủy/làm mới mã** và kiểm trạng thái liên kết. Không vội kết luận access token đã bị đánh cắp khi mới có bằng chứng lộ user_code.

**Nếu device_code hoặc token polling request bị lộ**, rủi ro cao hơn: bên khác có thể thử poll cùng grant hoặc lấy kết quả nếu các ràng buộc không ngăn được. Phải kiểm logs, token issuance, client binding và trạng thái grant; cân nhắc vô hiệu hóa pending grant hoặc revoke token đã phát.

**Nếu người dùng đã bị lừa phê duyệt một device flow của attacker**:

1. Xác định client/device grant vừa được chấp thuận và những quyền/scope đã cấp.
2. Thu hồi grant, access token/refresh token hoặc phiên liên quan qua cơ chế AS nếu có.
3. Kiểm Resource Server về truy cập bất thường trong cửa sổ token có thể còn hiệu lực.
4. Yêu cầu người dùng kiểm danh sách ứng dụng/thiết bị được cấp quyền và xác thực lại khi thích hợp.
5. Rà soát nguyên nhân social engineering, UX consent thiếu thông tin, rate limiting hoặc các điều kiện bảo mật chưa được đáp ứng.
6. Không yêu cầu người dùng gửi lại raw user_code, device_code hay access token trong ticket để “đối chiếu”.

**Thu hồi refresh token không mặc nhiên vô hiệu hóa tức thì mọi JWT access token đã cấp.** Resource Server cần cơ chế hỗ trợ thu hồi sớm hoặc chấp nhận cửa sổ còn hiệu lực đã đánh giá. Nếu chỉ có opaque access token được introspect, cache introspection cũng có thể tạo độ trễ.

Khi bằng chứng chỉ liên quan mã display của một device grant, **không tự động kết luận private signing key của Authorization Server bị lộ**. Thu hồi key/issuer là phản ứng ở mức gốc tin cậy, chỉ phù hợp khi có bằng chứng hoặc chính sách ứng cứu về xâm phạm tương ứng.

## 19. Checklist trước khi đưa device flow vào production

1. **Đúng mục đích:** Có thật sự cần Device Authorization Grant cho thiết bị hạn chế nhập liệu, thay vì ép người dùng nhập password trên TV?
2. **Nguồn tin cậy:** Device client dùng issuer, device authorization endpoint, verification URI và token endpoint từ cấu hình AS được phép?
3. **Tách mã:** User_code chỉ dùng cho màn hình và verification URI; device_code không hiển thị, không log, chỉ dùng để poll?
4. **Mã khó đoán:** User_code được tạo bằng cơ chế đủ entropy, tránh mã tuần tự và va chạm với pending grants?
5. **Rate limiting:** Verification endpoint có chống brute force, thử mã hàng loạt và abuse?
6. **TTL:** Pending grant, user_code và device_code có thời hạn hữu hạn, có cleanup/hủy và không tái sử dụng sai ngữ cảnh?
7. **UI trên thiết bị:** Có địa chỉ chính thức, mã dễ nhập, countdown, cancel/restart, không hiện token thật?
8. **Consent:** Trang AS hiển thị đúng client, account và scope/resource; yêu cầu approve rõ ràng, không auto-approve theo link?
9. **Anti-phishing:** Có cảnh báo không dùng mã được gửi qua chat/email và không chấp thuận thiết bị lạ?
10. **QR:** QR dựa trên URI của AS tin cậy; prefilled code không bỏ qua xác thực/consent, không làm lộ query cho bên thứ ba?
11. **Account binding:** Đã kiểm trường hợp hai users/two tabs nhập cùng code và account không mong muốn?
12. **Polling:** Đúng grant type, dùng device_code, tôn trọng interval/slow_down, dừng khi deny/expired?
13. **Atomicity:** AS bảo đảm chỉ trạng thái chấp thuận cuối cùng hợp lệ có thể đổi thành token theo policy?
14. **Token validation:** API chỉ nhận access token đúng issuer, audience, thời hạn, scope và quyền tài nguyên; không nhận user_code/device_code?
15. **Token storage:** Access/refresh/ID token sau thành công được lưu theo loại client và chính sách; không đưa token vào UI hay analytics?
16. **Logout/revocation:** Có cách xóa phiên trên thiết bị dùng chung, revoke grant và xử lý access token còn hạn?
17. **Observability:** Proxy, AS, app, APM, QR/session replay và support tools không ghi raw code/credential?
18. **Tests:** Có positive flow và negative tests cho sai mã, hết hạn, đoán mã, tranh chấp phê duyệt, polling, QR và phishing UX?
19. **Incident response:** Có thể vô hiệu hóa pending grant, điều tra token issuance và phản ứng khi user lỡ cấp quyền cho thiết bị lạ?

## 20. Câu hỏi tự đánh giá

**1. Display code trong RFC 8628 thường là trường nào?** Là **user_code**, giúp người dùng tìm đúng giao dịch device authorization đang chờ tại verification URI.

**2. Biết user_code có đồng nghĩa lấy được access token không?** Không. Device client còn cần device_code tương ứng; Authorization Server phải xác thực người dùng, kiểm grant và quyết định cấp quyền. Tuy nhiên, lộ user_code có thể gây liên kết tài khoản sai hoặc tạo cơ hội thao túng phê duyệt.

**3. Vì sao một website đăng nhập chính thức vẫn có thể xuất hiện trong device-code phishing?** Vì attacker có thể tự khởi tạo device grant rồi dụ nạn nhân dùng **mã của attacker** trên chính trang xác minh thật, sau đó attacker poll bằng device_code của họ.

**4. Khi TV hiện mã mà người dùng không chủ động kết nối thiết bị nào, có nên nhập mã được người lạ gửi không?** Không. Chỉ dùng mã từ thiết bị đang trực tiếp kết nối và kiểm client/account/scope trước khi approve.

**5. User_code và device_code có thể gửi thay nhau ở token endpoint không?** Không. User_code được nhập tại trang verification; device_code là credential để device client poll token endpoint với grant type device_code.

**6. QR có loại bỏ nguy cơ lừa đảo không?** Không. QR chỉ mã hóa URL để tiện mở; có thể chứa mã của attacker hoặc dẫn đến domain giả. Trang AS vẫn phải xác thực và yêu cầu chấp thuận có ngữ cảnh.

**7. Tại sao mã ngắn phải có rate limit?** Vì user_code dễ nhập nên không thể dài như private key; giới hạn số lần đoán giúp bảo vệ không gian mã và các pending grants khỏi brute force.

**8. Nếu người dùng phê duyệt rồi, mã display có nên tiếp tục hiện không?** Không cần. Nên ẩn và xóa trạng thái UI liên quan, tránh người khác dùng nhầm; AS cũng phải chặn việc dùng lại giao dịch đã hoàn thành.

**9. Khi polling nhận slow_down, client có thể giữ interval cũ không?** Không. Client phải tăng khoảng cách polling theo quy định giao thức và dừng khi grant bị denied/expired.

**10. Một access token cấp sau device flow có thể dùng cho mọi API không?** Không. Resource Server chỉ nhận đúng access token đã xác minh, dành cho audience và scope được cấp, còn hiệu lực và phù hợp policy tài nguyên.

**11. Nếu chụp ảnh màn hình TV có user_code, có cần xoay signing key của Authorization Server ngay không?** Không mặc định. Cần đánh giá pending grant/account binding và hủy/làm mới mã hoặc revoke token nếu đã cấp; xoay signing key chỉ khi có căn cứ xâm phạm khóa.

**Ghi nhớ:** **Display code (user_code) không phải mật khẩu hay access token, nhưng là điểm nối nhạy cảm giữa thiết bị đang chờ và quyết định cấp quyền của người dùng.** Bảo vệ nó bằng **thời hạn ngắn, entropy và rate limiting, hiển thị có kiểm soát, xác minh đúng thiết bị/client/account/scope, chống phishing, không log mã và xử lý hủy/thu hồi nhất quán**. Giữ **device_code** riêng cho token polling và giữ **access/refresh token** riêng trong vòng đời credential; Resource Server luôn phải xác minh token và quyền thay vì tin một mã từng hiển thị trên màn hình.
