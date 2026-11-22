# Token mang quyền truy cập và rủi ro khi bị chiếm đoạt

Access token là thông tin xác thực mà client trình cho API hoặc resource server để yêu cầu truy cập tài nguyên. Với **bearer access token**, bên nào sở hữu token hợp lệ thường có thể sử dụng nó trong phạm vi quyền và thời hạn được cấp. Vì vậy, token bị đánh cắp có thể trở thành chìa khóa cho kẻ tấn công, ngay cả khi token là JWT được ký đúng và chưa bị chỉnh sửa.

Bài học thuộc chương **Nền tảng tin cậy** của module **Security – JSON Web Token (JWT)**. Nội dung tập trung vào bản chất của access token, cách token bị lộ và bị phát lại, tác động của sự cố, cùng các biện pháp giảm thiểu và ứng phó áp dụng cho trình duyệt, ứng dụng di động, backend và API ở mọi nền tảng.

## 1. Access token là gì và tại sao nó có giá trị?

Access token đại diện cho quyền truy cập đã được cấp cho một client hoặc chủ thể trong một phạm vi nhất định. Client gửi token tới resource server để chứng minh rằng request đang mang thông tin ủy quyền phù hợp.

Ví dụ, sau khi người dùng cấp quyền đọc hóa đơn cho ứng dụng, authorization server có thể cấp access token chứa hoặc đại diện cho:

- **Chủ thể:** người dùng hoặc ứng dụng được đại diện.
- **Client:** ứng dụng đã xin token.
- **Audience:** API hoặc nhóm tài nguyên được phép nhận token.
- **Scope/permission:** các thao tác được cấp, ví dụ `invoice:read`.
- **Thời hạn:** thời điểm bắt đầu và kết thúc hiệu lực.
- **Ngữ cảnh khác:** tenant, tổ chức, mức xác thực hoặc ràng buộc người gửi nếu hồ sơ token hỗ trợ.

Access token có thể là chuỗi **opaque** (không có cấu trúc mà client cần hiểu) hoặc có dạng **JWT**. Resource server phải xác minh token bằng cơ chế phù hợp với loại token: JWT có thể được xác minh chữ ký và claims; opaque token có thể cần introspection hoặc cơ chế tra cứu trạng thái do authorization server cung cấp.

### 1.1. Token giống một quyền truy cập có thể trình ra

Với bearer token, resource server thường không yêu cầu client chứng minh thêm quyền sở hữu khóa riêng cho từng request. Client chỉ cần trình token đúng cách, thường trong HTTP header:

~~~http
GET /invoices/42 HTTP/1.1
Host: billing.example.org
Authorization: Bearer <access-token>
~~~

Ai lấy được chuỗi token có thể thử dùng token đó cho đến khi token hết hạn, bị vô hiệu hóa hoặc bị chặn bởi một chính sách khác. Chữ ký JWT chứng minh nội dung được bảo vệ chưa bị sửa và có thể xác thực bên phát hành khi khóa được tin cậy; **chữ ký không chứng minh người đang gửi request chính là người dùng hợp pháp**.

Đó là lý do token cần được bảo vệ như mật khẩu hoặc credential có quyền tương ứng, dù token có thể có thời hạn ngắn hơn mật khẩu.

### 1.2. Phân biệt access token, ID token và refresh token

| Loại | Mục đích | Nơi sử dụng | Nếu bị lộ |
| --- | --- | --- | --- |
| **Access token** | Truy cập API/tài nguyên trong phạm vi được cấp | Resource server tương ứng với audience | Kẻ giữ token có thể gọi API bằng quyền còn hiệu lực |
| **ID token** | Truyền thông tin về lần xác thực cho client trong OpenID Connect | Ứng dụng client có audience phù hợp | Có thể làm lộ thông tin xác thực hoặc hỗ trợ tấn công vào phiên nếu client xử lý sai; không dùng nó như access token |
| **Refresh token** | Xin access token mới theo chính sách authorization server | Authorization server/token endpoint | Kẻ tấn công có thể duy trì quyền truy cập lâu hơn bằng cách xin token mới, nếu refresh token còn hợp lệ |

Refresh token thường có giá trị cao vì có thể tạo ra access token mới. Vì thế, việc bảo vệ refresh token và phát hiện tái sử dụng refresh token đã bị xoay vòng là một phần quan trọng của quản lý phiên.

## 2. Token bị chiếm đoạt và token bị phát lại

Hai khái niệm thường xuất hiện cùng nhau nhưng có ý nghĩa khác nhau:

- **Token theft (đánh cắp token):** kẻ tấn công lấy được bản sao token từ thiết bị, trình duyệt, log, bộ nhớ, kho lưu trữ hoặc kênh truyền.
- **Token replay (phát lại token):** kẻ tấn công gửi lại token hợp lệ đã lấy được để thực hiện request khác. Token có thể bị phát lại nguyên vẹn mà không cần sửa một byte nào.

~~~mermaid
flowchart TD
    A["Authorization Server cấp access token"] --> B["Client lưu và sử dụng token"]
    B --> C["Token bị lộ qua thiết bị, XSS, log hoặc hệ thống trung gian"]
    C --> D["Kẻ tấn công sao chép token"]
    D --> E["Gửi request tới API với token bị đánh cắp"]
    E --> F{"Token còn được chấp nhận?"}
    F -- "Có" --> G["API có thể thực thi request theo quyền token"]
    F -- "Không" --> H["Từ chối request"]
~~~

Một token bị đánh cắp không cần có chữ ký giả. Nếu token vẫn còn thời hạn, đúng audience, đúng issuer và không bị vô hiệu hóa, phép xác minh JWT có thể thành công. Đây là điểm khác biệt giữa **toàn vẹn token** và **an toàn của phiên/thiết bị đang sử dụng token**.

### 2.1. Vì sao JWT không tự chống replay?

JWT là định dạng mang claims. Chữ ký JWS bảo vệ phần dữ liệu được ký khỏi thay đổi trái phép; nó không mặc định ghi nhớ token đã được sử dụng ở request trước.

Claim `jti` có thể cung cấp mã định danh duy nhất cho token, nhưng chỉ thêm `jti` **không tự ngăn replay**. Hệ thống phải lưu trạng thái hoặc áp dụng một giao thức ràng buộc request để phát hiện và từ chối việc dùng lại khi đó là yêu cầu bảo mật.

Các claim thời gian như `exp` và `nbf` giúp giới hạn khoảng thời gian token được chấp nhận. Chúng không bảo đảm token chỉ được dùng một lần trong khoảng thời gian đó.

## 3. Token có thể bị lộ ở đâu?

Token đi qua nhiều thành phần trong vòng đời của nó. Mỗi nơi lưu, xử lý, hiển thị hoặc ghi lại token đều có thể trở thành điểm rò rỉ.

### 3.1. Trình duyệt và mã chạy phía client

| Nguồn rò rỉ | Cách token bị lấy | Rủi ro |
| --- | --- | --- |
| XSS | Mã độc chạy cùng origin đọc token trong `localStorage`, `sessionStorage` hoặc bộ nhớ JavaScript | Kẻ tấn công gửi token tới máy chủ của mình hoặc dùng trực tiếp từ trình duyệt |
| Browser extension độc hại/quá nhiều quyền | Extension có thể đọc trang, request hoặc dữ liệu tùy quyền được cấp | Token và thông tin phiên có thể bị thu thập |
| Thiết bị dùng chung | Token còn trong storage hoặc phiên chưa đăng xuất | Người dùng tiếp theo có thể sử dụng phiên trước |
| Công cụ debug và clipboard | Token bị sao chép vào ticket, ảnh chụp, tài liệu hoặc cuộc trò chuyện | Token có thể lan ra ngoài nhóm được phép |
| URL, lịch sử và referrer | Token được đặt trong query string hoặc fragment rồi bị lưu/chia sẻ ngoài ý muốn | Query string có thể vào lịch sử và log proxy/server; fragment không được gửi trong HTTP request nhưng có thể lộ qua lịch sử, script, extension hoặc liên kết bị chia sẻ |

Không đặt access token trong URL. Query string có thể xuất hiện trong lịch sử trình duyệt, log server/proxy, hệ thống phân tích và header `Referer` tùy điều hướng/chính sách. Fragment không được gửi trong HTTP request nhưng vẫn có thể bị lộ qua lịch sử, mã chạy trong trang, extension hoặc thao tác chia sẻ liên kết. Dùng header `Authorization` hoặc cơ chế session cookie được thiết kế đúng.

### 3.2. Backend, gateway và hệ thống quan sát

Token có thể vô tình được ghi vào:

- Access log ghi toàn bộ request header.
- Log lỗi, exception, debug trace hoặc bản dump request.
- Distributed tracing, APM, telemetry và công cụ giám sát.
- Message queue, dead-letter queue, event payload hoặc bản sao dữ liệu.
- Hệ thống hỗ trợ khách hàng, báo cáo sự cố và ảnh chụp màn hình.
- File cấu hình, repository, pipeline CI/CD hoặc biến môi trường bị lộ.

Các hệ thống trung gian thường có quyền truy cập rộng và lưu dữ liệu lâu hơn thời hạn token. Nếu log chứa bearer token, người đọc log có thể sử dụng token trực tiếp. Vì vậy phải **che hoặc loại bỏ** header `Authorization`, cookie và mọi trường nhạy cảm trước khi ghi log.

### 3.3. Mạng và thiết bị

Kẻ tấn công có thể lấy token qua kết nối không được bảo vệ, proxy hoặc thiết bị đã bị xâm nhập. TLS làm giảm nguy cơ nghe lén/chỉnh sửa trên đường truyền khi cấu hình và xác minh chứng chỉ đúng, nhưng không ngăn mã độc trên endpoint hợp lệ, extension có quyền truy cập, hoặc log ở hai đầu kết nối làm lộ token.

### 3.4. Bí mật bị commit hoặc chia sẻ nhầm

Token thử nghiệm, token production, refresh token hoặc khóa ký có thể bị commit vào repository, gửi trong chat, đính kèm ticket hoặc xuất hiện trong script mẫu. Xóa chuỗi khỏi commit mới chưa chắc xóa được khỏi lịch sử Git, bản clone, cache hoặc artifact đã phát hành. Khi credential thực sự bị lộ, cần đánh giá và thu hồi/luân chuyển theo mức độ, đồng thời xử lý nguồn rò rỉ.

## 4. Điều gì xảy ra khi token bị đánh cắp?

Tác động phụ thuộc vào **quyền, audience, thời hạn, loại token, cách resource server kiểm tra và khả năng ràng buộc token với người gửi**.

| Đặc điểm token | Tác động tiềm tàng |
| --- | --- |
| Scope chỉ đọc một loại dữ liệu | Kẻ tấn công có thể đọc dữ liệu trong phạm vi được cấp |
| Scope ghi hoặc thực hiện giao dịch | Có thể sửa dữ liệu, tạo lệnh, thay đổi cấu hình hoặc thực hiện hành động nhạy cảm |
| Audience quá rộng | Token bị dùng ở nhiều API hơn nhu cầu ban đầu |
| TTL dài | Kẻ tấn công có nhiều thời gian khai thác token |
| Refresh token bị lộ | Có thể xin access token mới và kéo dài sự cố |
| Token gắn với người gửi bằng DPoP/mTLS | Bản sao token đơn lẻ có thể không đủ để sử dụng nếu kẻ tấn công không có khóa/chứng chỉ tương ứng |
| Token không có trạng thái thu hồi hiệu quả | Một JWT đã ký có thể tiếp tục được chấp nhận đến khi hết hạn nếu resource server chỉ xác minh offline |

Token bị lộ không nhất thiết dẫn đến toàn quyền hệ thống. Nguyên tắc quyền tối thiểu, audience hẹp, phân quyền theo tài nguyên và kiểm soát nghiệp vụ có thể giới hạn thiệt hại.

### 4.1. Ví dụ: access token đọc hóa đơn bị lấy cắp

Alice đăng nhập vào ứng dụng và nhận JWT có các claims minh họa:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "alice",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "exp": 2000000000,
  "jti": "token-unique-id"
}
~~~

Một đoạn mã XSS đọc được token từ nơi lưu trong browser và gửi bản sao tới kẻ tấn công. Kẻ tấn công gửi request:

~~~http
GET /invoices/42 HTTP/1.1
Host: billing.example.org
Authorization: Bearer <stolen-access-token>
~~~

Nếu token còn hạn và billing API chấp nhận bearer token đó, request có thể vượt qua bước xác thực token. API vẫn phải kiểm tra Alice có quyền đọc hóa đơn 42 hay không. Nếu có, kẻ tấn công có thể đọc dữ liệu như Alice cho tới khi token bị vô hiệu hóa hoặc không còn được chấp nhận.

Chữ ký JWT không bị phá vỡ trong ví dụ này. Sự cố nằm ở việc **credential hợp lệ bị người khác chiếm hữu**.

### 4.2. Ví dụ: refresh token bị lộ

Kẻ tấn công lấy được refresh token còn hiệu lực và gửi tới token endpoint. Nếu authorization server không ràng buộc refresh token với client/phiên hoặc không phát hiện việc tái sử dụng sau rotation, kẻ tấn công có thể liên tục nhận access token mới. Khi đó, chỉ chờ access token hiện tại hết hạn là chưa đủ để chấm dứt sự cố.

## 5. Giảm thiểu nguy cơ token bị chiếm đoạt

Không có một biện pháp đơn lẻ giải quyết mọi nguồn rò rỉ. Cần kết hợp bảo vệ thiết bị/client, giảm giá trị token, giới hạn nơi token được chấp nhận và có khả năng thu hồi.

### 5.1. Giảm quyền và phạm vi token

1. **Scope tối thiểu:** chỉ cấp các thao tác cần thiết cho use case hiện tại.
2. **Audience cụ thể:** cấp token cho đúng resource server; tránh audience chung kiểu “mọi API nội bộ” nếu không thật sự cần.
3. **Tenant và đối tượng:** API kiểm tra tenant, quan hệ sở hữu và quyền trên từng tài nguyên.
4. **Thời hạn hợp lý:** access token có TTL ngắn phù hợp với độ nhạy và trải nghiệm; TTL ngắn giới hạn cửa sổ khai thác nhưng không thay thế thu hồi.
5. **Claims tối thiểu:** không đưa dữ liệu nhạy cảm không cần thiết vào payload. Payload JWS thường có thể đọc được; ký không phải mã hóa.
6. **Tách credential:** dùng token và khóa riêng cho môi trường, workload và mục đích khác nhau.

### 5.2. Bảo vệ nơi lưu và nơi truyền

**Đối với ứng dụng browser:**

- Cân nhắc mô hình BFF để access token và refresh token được giữ ở server, browser chỉ giữ session cookie.
- Nếu SPA trực tiếp sử dụng token, tránh lưu bền vững trong `localStorage` khi có phương án phù hợp; giảm TTL, scope và thời gian token tồn tại trong bộ nhớ.
- Dùng HTTPS/TLS mọi nơi; không truyền token trong URL, query string hoặc fragment.
- Giảm XSS bằng output encoding, API DOM an toàn, Content Security Policy, kiểm soát dependency và loại bỏ script bên thứ ba không cần thiết.
- Nếu dùng cookie phiên, cấu hình `Secure`, `HttpOnly`, `SameSite` phù hợp và có biện pháp chống CSRF. `HttpOnly` ngăn JavaScript đọc cookie nhưng không ngăn XSS gửi request thay người dùng.

**Đối với ứng dụng native/mobile:**

- Không nhúng client secret hoặc khóa ký dùng chung vào gói cài đặt.
- Dùng Authorization Code Flow với PKCE và external user-agent theo hướng dẫn cho native app.
- Bảo vệ token bằng vùng lưu trữ an toàn do hệ điều hành cung cấp khi phù hợp.
- Tránh ghi token vào log, clipboard, file thông thường hoặc bản sao lưu không cần thiết.

**Đối với backend và service:**

- Lưu credential trong secret manager hoặc kho bí mật được kiểm soát truy cập; giới hạn người và workload được đọc.
- Loại bỏ token khỏi log, trace, error report và dữ liệu gửi sang hệ thống analytics.
- Bảo vệ kết nối bằng TLS; cân nhắc mTLS giữa workload.
- Không chuyển tiếp token tới service không nằm trong audience; dùng token exchange/delegation khi cần quyền đại diện người dùng.

### 5.3. Giới hạn thời gian sống và quản lý refresh token

Access token TTL ngắn giúp giảm thời gian sử dụng sau khi bị lộ. Tuy nhiên TTL quá ngắn có thể làm tăng tần suất refresh và tải cho authorization server. Chọn TTL theo mức nhạy dữ liệu, rủi ro thiết bị, khả năng thu hồi và trải nghiệm người dùng.

Với refresh token:

- Cấp riêng cho client/phiên và lưu ở vị trí có kiểm soát.
- Dùng **refresh token rotation** nếu authorization server hỗ trợ: mỗi lần refresh cấp token mới và làm token cũ mất hiệu lực.
- Phát hiện việc dùng lại refresh token đã bị thay thế (*reuse detection*); khi phát hiện, có thể thu hồi cả token family hoặc phiên liên quan theo chính sách.
- Có thể ràng buộc refresh token với client hoặc thiết bị bằng cơ chế phù hợp.
- Thu hồi khi logout, đổi mật khẩu, khóa tài khoản, phát hiện thiết bị bị mất hoặc có dấu hiệu xâm nhập, tùy chính sách hệ thống.

Rotation không giúp ích nếu token mới tiếp tục bị lấy cắp hoặc hệ thống không phát hiện reuse. Cần xử lý sự kiện, thông báo và thu hồi theo thiết kế.

## 6. Ràng buộc token với người gửi để giảm replay

Bearer token chỉ cần được sở hữu để sử dụng. **Sender-constrained token** bổ sung bằng chứng rằng request được tạo bởi client sở hữu khóa hoặc chứng chỉ đã ràng buộc với token.

### 6.1. DPoP

**Demonstrating Proof of Possession (DPoP)** là cơ chế ở tầng ứng dụng OAuth. Client tạo một cặp khóa và gửi bằng chứng ký cho request. Access token được ràng buộc với khóa công khai tương ứng; resource server kiểm tra proof và việc token gắn với khóa đó.

Về khái quát, proof có thể ràng buộc:

- Phương thức HTTP và URI đích.
- Thời điểm phát hành proof và mã định danh duy nhất để hỗ trợ phát hiện replay.
- Hash của access token trong một số ngữ cảnh.
- Nonce do server cung cấp khi cấu hình giao thức yêu cầu.

Kẻ tấn công chỉ lấy được access token nhưng không có khóa riêng tương ứng sẽ khó dùng bản sao token để gọi API. Tuy nhiên, DPoP không bảo vệ hoàn toàn khỏi mã độc đang chạy trên chính thiết bị và có khả năng sử dụng khóa hoặc yêu cầu client ký proof.

### 6.2. Mutual TLS (mTLS) và certificate-bound token

Với mTLS, client và server xác thực chứng chỉ của nhau trong TLS. Authorization server có thể cấp access token ràng buộc với chứng chỉ client. Resource server kiểm tra kết nối mTLS và đối chiếu chứng chỉ với thông tin ràng buộc trong token.

Kẻ tấn công có bản sao token nhưng không có khóa riêng tương ứng với chứng chỉ sẽ không thể đơn giản sử dụng token qua kết nối khác. Đổi lại, hệ thống cần quản lý chứng chỉ, cấp phát, gia hạn, thu hồi và định tuyến TLS đúng cách.

### 6.3. So sánh bearer và sender-constrained token

| Tiêu chí | Bearer token | DPoP-bound token | mTLS-bound token |
| --- | --- | --- | --- |
| Bằng chứng khi gọi API | Trình token | Trình token và proof ký bằng khóa riêng | Trình token qua kết nối có chứng chỉ client phù hợp |
| Token bị sao chép đơn lẻ | Có thể dùng lại nếu còn hợp lệ | Thường không đủ nếu thiếu khóa riêng | Thường không đủ nếu thiếu khóa/chứng chỉ |
| Thành phần cần quản lý | Token | Token, khóa DPoP, kiểm tra proof và replay | Token, chứng chỉ, khóa riêng và hạ tầng mTLS |
| Giới hạn | Dễ bị replay khi lộ | Không chống được malware có khả năng dùng khóa tại endpoint | Phụ thuộc bảo vệ khóa/chứng chỉ và cấu hình TLS |

Sender constraint làm giảm giá trị của bản sao token, nhưng không thay thế TTL, scope tối thiểu, kiểm tra audience, bảo vệ thiết bị hoặc phân quyền.

## 7. Thu hồi token và giới hạn của JWT tự chứa

Một JWT đã ký có thể được resource server xác minh offline bằng khóa công khai mà không cần hỏi authorization server ở mỗi request. Cách này giảm phụ thuộc mạng và độ trễ, nhưng tạo ra thách thức: nếu token bị đánh cắp hoặc quyền bị thu hồi, resource server có thể tiếp tục chấp nhận token cho đến khi hết hạn nếu không có cơ chế kiểm tra trạng thái bổ sung.

### 7.1. Các cách xử lý

| Cơ chế | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **TTL ngắn** | Token hết hạn nhanh | Giảm cửa sổ khai thác; không vô hiệu hóa ngay lập tức |
| **Revocation endpoint** | Client yêu cầu authorization server thu hồi token theo giao thức | Resource server phải có cách biết trạng thái đã thay đổi nếu đang xác minh JWT offline |
| **Token introspection** | Resource server hỏi authorization server về trạng thái và metadata token | Có trạng thái tập trung, nhưng tăng độ trễ và phụ thuộc dịch vụ introspection |
| **Denylist theo `jti`** | Lưu ID token bị từ chối và kiểm tra trước khi chấp nhận | Cần đồng bộ, thời hạn lưu và kiểm tra ở mọi resource server liên quan |
| **Luân chuyển khóa ký** | Ngừng tin khóa đã lộ và chuyển sang khóa mới | Có thể ảnh hưởng nhiều token cùng ký bằng khóa đó; cần quản lý JWKS/cache và chuyển đổi |
| **Thu hồi phiên/refresh token** | Chặn việc xin access token mới từ phiên hoặc refresh token | Access token đã phát hành có thể vẫn được chấp nhận nếu resource server không kiểm tra trạng thái |

Không nên nhầm **thu hồi refresh token** với **thu hồi mọi access token đã phát hành**. Hai việc có thể có hiệu lực khác nhau. Một JWT đã phát hành không tự biến mất khỏi client khi authorization server thu hồi refresh token.

### 7.2. Khi nào dùng JWT offline và khi nào cần kiểm tra trạng thái?

- JWT offline phù hợp khi cần xác minh nhanh, có thể chấp nhận một cửa sổ hiệu lực ngắn và có quy trình xử lý sự cố phù hợp.
- Introspection hoặc trạng thái trung tâm phù hợp khi cần thu hồi gần thời gian thực, token opaque hoặc chính sách yêu cầu kiểm tra trạng thái thường xuyên.
- Denylist theo `jti` phù hợp khi cần chặn một số token cụ thể, với điều kiện mọi resource server liên quan đều tra cứu danh sách này và cache không làm mất hiệu lực yêu cầu.
- Với sự cố lộ khóa ký, cần ngừng tin khóa bị lộ, cập nhật cấu hình khóa tin cậy và xử lý toàn bộ token có thể bị giả mạo bằng khóa đó; chỉ thêm một `jti` vào denylist là không đủ.

## 8. Phát hiện token bị lạm dụng

Không phải lúc nào cũng xác định được token bị đánh cắp chỉ bằng một request. Cần kết hợp telemetry, sự kiện bảo mật và dấu hiệu bất thường, đồng thời tránh ghi lại chính bearer token.

### 8.1. Tín hiệu cần quan sát

- Cùng một token xuất hiện từ các địa chỉ mạng, vùng địa lý hoặc thiết bị bất thường trong thời gian ngắn.
- Số lượng request, tần suất, loại endpoint hoặc mẫu truy cập thay đổi đột ngột.
- Token được dùng cho nhiều API/audience ngoài hành vi bình thường.
- Các lần xác thực thất bại, token hết hạn, sai issuer/audience hoặc thiếu scope tăng đột biến.
- Refresh token cũ được sử dụng lại sau khi đã rotation.
- Tài khoản vừa đăng nhập/đổi mật khẩu/được cấp quyền nhưng ngay sau đó xuất hiện hành vi nhạy cảm bất thường.
- Một token đọc dữ liệu hàng loạt hoặc thực hiện giao dịch ngoài mô hình sử dụng bình thường.

Địa chỉ IP và user-agent có thể thay đổi hợp lệ do mạng di động, VPN, proxy hoặc cập nhật trình duyệt. Không nên tự động kết luận token bị đánh cắp chỉ dựa trên một tín hiệu đơn lẻ.

### 8.2. Ghi log mà không làm lộ token

Log nên ghi các thông tin phục vụ điều tra như:

- Thời điểm, service, endpoint, hành động và kết quả quyết định.
- Issuer, audience, client ID hoặc subject ở dạng được phép theo chính sách dữ liệu.
- `jti` hoặc mã tham chiếu nội bộ nếu token có định danh và việc ghi nhận được cho phép.
- Lý do từ chối: chữ ký sai, hết hạn, audience sai, token bị thu hồi, thiếu scope hoặc không có quyền trên tài nguyên.
- Request ID/correlation ID để nối các sự kiện qua service.

Không ghi nguyên access token, refresh token, authorization code, cookie phiên, khóa riêng hoặc secret. Nếu cần đối chiếu một token giữa log, có thể cân nhắc fingerprint được tạo bằng HMAC với khóa log riêng và quy trình kiểm soát truy cập; không dùng raw token làm định danh log.

## 9. Ứng phó khi nghi ngờ token bị lộ

Ứng phó cần nhanh chóng hạn chế khả năng sử dụng token, bảo toàn bằng chứng cần thiết và xử lý nguồn rò rỉ. Mức hành động phụ thuộc token nào bị lộ và khóa nào bị ảnh hưởng.

### 9.1. Trình tự xử lý

1. **Xác định phạm vi:** access token, refresh token, ID token, client secret hay khóa ký; issuer, audience, subject, scope, thời điểm, thiết bị và hệ thống liên quan.
2. **Chặn khả năng sử dụng tiếp:** thu hồi token/refresh token hoặc phiên liên quan, chặn `jti` nếu có denylist, vô hiệu hóa client/credential khi cần và buộc xác thực lại theo chính sách.
3. **Xử lý nguồn rò rỉ:** loại token khỏi log/ticket/repository hoặc kho chia sẻ, sửa cấu hình ghi log, vá XSS, cô lập thiết bị hoặc service bị xâm nhập.
4. **Đánh giá hành động đã xảy ra:** truy vấn audit log, request ID, phạm vi dữ liệu đã đọc/sửa và các giao dịch được thực hiện trong cửa sổ rủi ro.
5. **Luân chuyển bí mật bị ảnh hưởng:** nếu client secret, khóa HMAC, khóa riêng ký JWT hoặc khóa mã hóa bị lộ, thay khóa theo kế hoạch và xử lý token/credential phụ thuộc khóa cũ.
6. **Khôi phục và theo dõi:** cấp phiên/token mới khi an toàn, xác minh quyền hiện hành, tăng giám sát và thông báo theo quy trình ứng phó của tổ chức.

### 9.2. Phân biệt mức độ xử lý

| Sự cố | Hành động thường cần cân nhắc |
| --- | --- |
| Một access token bearer bị lộ | Thu hồi/chặn token cụ thể hoặc phiên liên quan; kiểm tra request đã dùng token; xử lý nguồn rò rỉ |
| Refresh token bị lộ hoặc reuse | Thu hồi token family/phiên theo chính sách, buộc đăng nhập lại và điều tra thiết bị/client |
| Client secret bị lộ | Vô hiệu hóa/luân chuyển secret của client, rà soát token đã cấp và hoạt động của client |
| Khóa HMAC dùng chung bị lộ | Thay khóa ở tất cả bên liên quan; xem xét token có thể bị giả mạo bằng khóa đó |
| Khóa riêng ký JWT bị lộ | Ngừng tin khóa, phát hành khóa mới, cập nhật JWKS/trust config, xử lý token ký bằng khóa cũ và điều tra khả năng giả mạo |
| Thiết bị bị mất hoặc nhiễm malware | Thu hồi phiên/refresh token, đánh giá token đã lưu trên thiết bị, xóa/khóa thiết bị từ xa nếu có cơ chế phù hợp |

Không cần luân chuyển khóa ký toàn hệ thống chỉ vì một access token người dùng bị lộ nếu khóa ký không bị ảnh hưởng. Ngược lại, nếu khóa riêng ký token bị lộ, chỉ thu hồi một token đã biết sẽ không xử lý được khả năng kẻ tấn công tự tạo token mới.

## 10. Các tình huống thực tế

### Tình huống A — XSS đọc token trong localStorage

Một ứng dụng lưu access token dài hạn trong `localStorage`. Lỗ hổng XSS cho phép mã độc chạy cùng origin và gửi token ra ngoài. Kẻ tấn công dùng token để gọi API từ thiết bị khác.

**Bài học:** giảm nguy cơ XSS, tránh lưu token bền vững khi có lựa chọn phù hợp, cân nhắc BFF, giảm scope/TTL và có cơ chế thu hồi.

### Tình huống B — Token bị lộ trong log reverse proxy

Reverse proxy ghi toàn bộ header request. Một request chứa `Authorization: Bearer ...` được lưu trong hệ thống log có nhiều người truy cập. Người đọc log sao chép token và gọi API.

**Bài học:** scrub header/cookie ở proxy, APM và log collector; giới hạn quyền đọc log; kiểm tra lịch sử lưu trữ và thu hồi token đã lộ.

### Tình huống C — JWT bị đánh cắp nhưng chữ ký vẫn hợp lệ

Kẻ tấn công sao chép một JWT có chữ ký đúng, `aud` đúng và `exp` chưa đến. Resource server chỉ xác minh chữ ký và thời hạn, không kiểm tra trạng thái thu hồi.

**Bài học:** chữ ký bảo vệ tính toàn vẹn, không chứng minh người gửi là chủ token; cân nhắc TTL ngắn, sender constraint, denylist hoặc introspection tùy yêu cầu.

### Tình huống D — Token đọc hóa đơn bị dùng để truy cập tenant khác

Token có scope `invoice:read` bị lộ. API chỉ kiểm tra scope mà không kiểm tra tenant và quyền sở hữu. Kẻ tấn công sửa ID trên URL để đọc hóa đơn tổ chức khác.

**Bài học:** scope không thay thế phân quyền theo đối tượng. Resource server phải kiểm tra tenant, quan hệ sở hữu và chính sách dữ liệu.

### Tình huống E — Refresh token cũ được dùng lại

Client đã đổi refresh token R1 thành R2. Kẻ tấn công giữ bản sao R1 và gửi nó sau đó. Authorization server có rotation và reuse detection nên nhận ra token cũ đã bị dùng lại, rồi thu hồi token family hoặc phiên liên quan theo chính sách.

**Bài học:** rotation cần đi cùng lưu trữ an toàn, phát hiện reuse và xử lý sự kiện. Nếu chỉ cấp R2 nhưng vẫn chấp nhận R1, lợi ích bảo vệ bị suy giảm.

### Tình huống F — Token bị lộ nhưng được ràng buộc DPoP

Kẻ tấn công lấy được access token nhưng không có khóa riêng DPoP trên thiết bị. Resource server yêu cầu proof hợp lệ gắn với token, method và URI nên bản sao token đơn lẻ không đủ để gọi API.

**Bài học:** sender constraint làm giảm khả năng replay token bị sao chép; vẫn phải bảo vệ endpoint và khóa riêng khỏi malware.

## 11. Checklist thiết kế access token an toàn

### Khi cấp token

- [ ] Xác định token dành cho resource server/audience cụ thể.
- [ ] Chỉ cấp scope và quyền tối thiểu cho tác vụ.
- [ ] Đặt TTL phù hợp với độ nhạy và khả năng thu hồi.
- [ ] Chỉ đưa claims cần thiết; không coi JWS là cơ chế giữ bí mật.
- [ ] Chọn bearer hay sender-constrained token dựa trên mô hình đe dọa.
- [ ] Quản lý khóa ký, khóa MAC và khóa mã hóa theo vòng đời riêng.

### Khi client lưu và sử dụng token

- [ ] Không nhúng client secret hoặc khóa phát hành vào browser/mobile app.
- [ ] Không đặt token trong URL, query string, fragment, log hoặc analytics.
- [ ] Bảo vệ token tại nơi lưu; cân nhắc BFF cho ứng dụng browser.
- [ ] Dùng TLS; bảo vệ cookie và xử lý CSRF nếu dùng session cookie.
- [ ] Bảo vệ refresh token, áp dụng rotation/reuse detection khi hỗ trợ.
- [ ] Tránh chia sẻ token giữa môi trường, client và mục đích khác nhau.

### Khi API nhận token

- [ ] Xác minh token bằng đúng cơ chế và khóa tin cậy.
- [ ] Kiểm tra issuer, audience, thời hạn, loại token và claims bắt buộc.
- [ ] Kiểm tra scope/permission và quyền trên từng tài nguyên.
- [ ] Kiểm tra trạng thái thu hồi/introspection nếu chính sách yêu cầu.
- [ ] Xác minh proof/chứng chỉ nếu token được ràng buộc người gửi.
- [ ] Không ghi token vào log; có giới hạn lưu lượng và giám sát bất thường.

### Khi có sự cố

- [ ] Xác định loại credential và phạm vi token bị ảnh hưởng.
- [ ] Thu hồi token/phiên/refresh token hoặc credential liên quan.
- [ ] Xử lý nguồn rò rỉ và bảo toàn audit evidence.
- [ ] Đánh giá dữ liệu và hành động đã bị truy cập.
- [ ] Luân chuyển khóa nếu chính khóa bị ảnh hưởng.
- [ ] Theo dõi dấu hiệu tiếp tục sử dụng token hoặc credential cũ.

## 12. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| JWT có chữ ký hợp lệ có thể bị đánh cắp và phát lại không? | **Có.** Chữ ký không ràng buộc token với người gửi trong bearer model. |
| Claim `jti` tự ngăn token bị sử dụng hai lần không? | **Không.** Cần trạng thái hoặc giao thức kiểm tra replay sử dụng định danh đó. |
| Token hết hạn sau 10 phút có nghĩa kẻ tấn công không thể sử dụng trong 10 phút đó không? | **Không.** Token vẫn có thể bị sử dụng trong cửa sổ hiệu lực nếu chưa bị chặn. |
| Thu hồi refresh token có chắc chắn làm mọi JWT access token đã phát hành mất hiệu lực ngay không? | **Không.** Resource server offline có thể tiếp tục chấp nhận JWT đến khi hết hạn nếu không kiểm tra trạng thái. |
| Nếu một access token bị lộ thì luôn phải thay khóa ký JWT không? | **Không.** Chỉ thay khóa ký khi khóa bị lộ hoặc có căn cứ cho thấy khóa bị xâm phạm; token đơn lẻ cần xử lý theo phạm vi của nó. |
| DPoP có làm bản sao access token đơn lẻ khó sử dụng hơn không? | **Có**, nếu resource server kiểm tra proof và token được ràng buộc đúng với khóa; endpoint bị chiếm quyền vẫn là rủi ro. |
| Có thể ghi token vào log để thuận tiện debug rồi xóa sau không? | **Không nên.** Log có thể được sao chép, lưu lâu và chia sẻ rộng; hãy che token và dùng mã tham chiếu an toàn. |
| Token có scope `invoice:read` có thể đọc mọi hóa đơn không? | **Không mặc định.** API còn phải kiểm tra tenant, quyền sở hữu và chính sách trên đối tượng. |

## 13. Ghi nhớ

Access token là credential mang quyền truy cập. Khi token bị đánh cắp, kẻ tấn công có thể sử dụng token hợp lệ mà không cần phá chữ ký hay biết mật khẩu của người dùng. JWT tự chứa không mặc định chống replay hoặc thu hồi tức thời.

Thiết kế an toàn cần đồng thời:

- Giới hạn **quyền, audience và thời hạn** để giảm giá trị token.
- Bảo vệ **nơi lưu, nơi truyền và hệ thống ghi log** để giảm khả năng token bị lộ.
- Dùng **refresh token rotation**, thu hồi, introspection hoặc denylist theo yêu cầu về trạng thái.
- Cân nhắc **DPoP/mTLS** để ràng buộc token với người gửi và giảm khả năng sử dụng bản sao.
- Xác minh token và phân quyền **tại resource server**, kể cả khi gateway đã kiểm tra trước.
- Có quy trình **phát hiện, thu hồi, điều tra và luân chuyển khóa** tương ứng với phạm vi sự cố.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 6750 – The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8705 – OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
