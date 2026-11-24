# Refresh token và mục đích đổi access token

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **refresh token** dùng để xin access token mới, và vì sao refresh token không phải bằng chứng truy cập API nghiệp vụ.
- Phân biệt thời hạn của **access token**, thời hạn/điều kiện sử dụng **refresh token** và trạng thái phiên đăng nhập hoặc sự ủy quyền.
- Mô tả luồng OAuth 2.0 với **grant_type=refresh_token**, bao gồm kiểm tra tại Authorization Server, phát hành token mới và xử lý lỗi.
- Giải thích cách **refresh token rotation**, sender-constrained token, thu hồi và giới hạn thời gian giảm rủi ro khi token bị lộ.
- Đề xuất cách lưu trữ, đồng bộ các yêu cầu refresh và xử lý logout, thay đổi quyền, token hết hạn hoặc bị tái sử dụng.

## 1. Hai loại token, hai nhiệm vụ khác nhau

Một hệ thống OAuth 2.0 thường có ba thành phần:

- **Client**: ứng dụng web, mobile hoặc backend muốn gọi API.
- **Authorization Server (AS)**: máy chủ cấp token sau khi kiểm tra việc ủy quyền.
- **Resource Server (RS)**: API bảo vệ dữ liệu, kiểm tra access token và phân quyền cho từng yêu cầu.

**Access token** là thông tin mà client trình cho Resource Server để được xem xét truy cập. Token này gắn với phạm vi quyền (scope), đối tượng nhận (audience), điều kiện hiệu lực và có thể gắn với một chủ thể. Access token có thể là **JWT** hoặc **opaque token**; đây là hai dạng biểu diễn khác nhau, không quyết định mục đích của token.

**Refresh token** là thông tin mà client trình **cho Authorization Server, tại token endpoint**, để xin access token mới theo phạm vi ủy quyền vẫn còn hợp lệ. Refresh token thường không được gửi đến Resource Server. Nó không phải “access token có hạn dài hơn”, vì **khác nơi nhận, khác mục đích và khác quy tắc xử lý**.

| Tiêu chí | Access token | Refresh token |
| --- | --- | --- |
| Dùng để làm gì? | Gọi API thuộc phạm vi được cấp. | Xin access token mới khi chính sách cho phép. |
| Nơi nhận | Resource Server, ví dụ Orders API. | Authorization Server, thường là token endpoint. |
| Độ dài vòng đời | Thường tương đối ngắn để giảm cửa sổ lạm dụng. | Có thể sống lâu hơn, nhưng chịu giới hạn, thu hồi và chính sách phiên. |
| Kiểm tra quan trọng | Issuer, audience, chữ ký/trạng thái, thời gian, scope và quyền trên tài nguyên. | Trạng thái refresh token, client được ràng buộc, thời hạn, rotation, sự ủy quyền và chính sách cấp mới. |
| Khi bị đánh cắp | Có thể dùng để gọi API đến khi bị từ chối hoặc hết hạn. | Có thể xin thêm access token, vì thế cần bảo vệ và phát hiện lạm dụng đặc biệt. |
| Có thể dùng cho API nghiệp vụ? | Có, nếu đúng loại token, audience, scope và quyền. | **Không**: API nghiệp vụ không nên chấp nhận refresh token làm Bearer access token. |

> Ý chính: **Access token cho phép thử thực hiện một yêu cầu API; refresh token cho phép thử gia hạn khả năng gọi API.** Không loại nào tạo ra quyền vĩnh viễn.

## 2. Vì sao không cấp access token sống mãi?

Giả sử hệ thống bán hàng cấp access token 15 phút cho một nhân viên. Khi token bị sao chép, kẻ tấn công có thể thử gửi token đó đến API trong khoảng thời gian token còn được chấp nhận. Nếu access token sống nhiều tháng, cửa sổ lạm dụng cũng có thể kéo dài nhiều tháng trừ khi có cơ chế thu hồi đủ hiệu quả.

**Access token sống ngắn** giúp thu hẹp thời gian một bản sao có thể bị lợi dụng. Tuy nhiên, nếu cứ hết 15 phút lại buộc người dùng nhập mật khẩu, trải nghiệm đăng nhập sẽ bị gián đoạn liên tục. Refresh token giúp client có thể xin một access token mới mà không cần yêu cầu người dùng thực hiện lại toàn bộ luồng tương tác ở mỗi lần hết hạn.

Ví dụ vòng đời:

| Thời điểm | Diễn biến | Kết luận |
| --- | --- | --- |
| 10:00 | AS cấp access token hiệu lực 15 phút và refresh token theo chính sách. | Client có thể gọi API bằng access token. |
| 10:14 | Client gần hết hạn access token và yêu cầu refresh. | Client liên hệ AS, không liên hệ Orders API để đổi token. |
| 10:14 | AS kiểm tra refresh token, client và trạng thái ủy quyền. | Nếu đủ điều kiện, AS cấp access token mới. |
| 10:15 | Access token cũ đến hạn hết hiệu lực. | Resource Server phải từ chối token cũ sau hạn. |
| 11:00 | Quản trị viên thu hồi phiên hoặc quyền ủy quyền. | AS có thể từ chối refresh tiếp theo; access token cũ đang lưu hành cần chính sách thu hồi/kiểm tra quyền riêng. |

Các mốc và thời hạn chỉ là **ví dụ minh họa**, không phải giá trị mặc định bắt buộc của OAuth.

**Refresh không đồng nghĩa đăng nhập lại.** Một lần đổi token thành công chứng minh client đã đáp ứng điều kiện đổi token của AS; nó **không tự chứng minh người dùng vừa nhập mật khẩu, thực hiện MFA, hay còn quyền với từng tài nguyên**. Các thao tác rủi ro cao có thể yêu cầu xác thực lại (step-up/re-authentication) theo chính sách riêng.

## 3. Luồng refresh token diễn ra như thế nào?

Trong một luồng phù hợp, client đã nhận access token và refresh token từ Authorization Server. Khi cần access token mới, client gửi refresh token đến **token endpoint** qua kết nối được bảo vệ bằng TLS.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource Server

    U->>C: Đăng nhập và chấp thuận quyền theo luồng phù hợp
    C->>AS: Authorization Code + kiểm tra client/PKCE theo luồng
    AS-->>C: Access token + refresh token (nếu được cấp)
    C->>API: GET /orders + access token
    API-->>C: Dữ liệu được phép truy cập
    Note over C: Access token gần hết hạn
    C->>AS: POST /token, grant_type=refresh_token
    AS->>AS: Kiểm refresh token, client, hạn dùng, chính sách
    AS-->>C: Access token mới (+ refresh token mới nếu rotation)
    C->>API: GET /orders + access token mới
    API-->>C: Dữ liệu hoặc từ chối theo quyền hiện hành
~~~

Luồng trên mô tả một ứng dụng dùng Authorization Code. Việc **có được cấp refresh token hay không phụ thuộc grant type, loại client và chính sách AS**. OAuth không bảo đảm mọi lần cấp access token đều đi kèm refresh token. Ví dụ, luồng **client credentials** thường có thể yêu cầu access token mới bằng chính thông tin xác thực của client và không cần refresh token.

Nếu access token đã hết hạn, client có thể thử refresh. Nếu refresh token cũng hết hiệu lực hoặc bị thu hồi, client cần thực hiện lại luồng ủy quyền/xác thực phù hợp với người dùng hoặc chính sách, thay vì lặp vô hạn yêu cầu đổi token.

## 4. Yêu cầu và phản hồi tại token endpoint

Theo OAuth 2.0 (RFC 6749, mục 6), yêu cầu refresh sử dụng **grant_type=refresh_token** và giá trị **refresh_token**. Ví dụ HTTP sau dùng dữ liệu giả, không chứa credential thật:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
~~~

Trong thực tế, **confidential client phải xác thực với AS theo cách đã đăng ký**, ví dụ một cơ chế client authentication phù hợp. **Public client** không thể dựa vào một client secret nhúng trong ứng dụng để chứng minh danh tính; AS cần bảo vệ refresh token bằng cơ chế thích hợp như rotation hoặc sender-constraining theo hồ sơ bảo mật áp dụng. Request ví dụ ở trên chỉ minh họa hai tham số cốt lõi, không thể hiện đầy đủ xác thực/ràng buộc client của từng triển khai.

Khi thành công, AS có thể trả về:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "EXAMPLE_NEW_REFRESH_TOKEN",
  "scope": "orders:read"
}
~~~

Các điểm cần hiểu:

- **access_token** là token mới để client gửi đến API đích.
- **token_type** cho biết cách sử dụng, ví dụ Bearer; trong hệ thống dùng token ràng buộc bên gửi, cần áp dụng cơ chế token type và proof đúng theo profile.
- **expires_in** biểu thị số giây access token còn hiệu lực kể từ lúc phát hành/phản hồi theo định nghĩa giao thức. Con số 900 chỉ để minh họa.
- **refresh_token** mới có thể được trả về, thường gặp ở cơ chế rotation. Nếu có, client phải thay token cũ theo quy tắc AS; **không nên tiếp tục dùng song song bản cũ**.
- **scope** nếu được trả về cho biết phạm vi liên quan; **không được mặc định rằng lần refresh đã được mở rộng quyền**. Scope yêu cầu ở lần refresh (nếu có) không thể bao gồm quyền ngoài những gì đã được cấp ban đầu, và AS có thể giới hạn phạm vi.
- Phản hồi chứa token cần được xử lý như dữ liệu nhạy cảm, **không cache công khai, không ghi log nguyên chuỗi**.

Không phải AS nào cũng cấp access token theo cùng định dạng. Client không nên tự phân tích JWT rồi tin vào mọi trường để quyết định quyền; Resource Server mới là nơi phải xác minh access token theo hợp đồng issuer và audience.

### Khi token endpoint từ chối refresh

Yêu cầu đổi token có thể thất bại vì refresh token đã hết hạn, bị thu hồi, sai client, đã được dùng theo cơ chế rotation hoặc không còn thuộc sự ủy quyền có hiệu lực. Một lỗi thường gặp là:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

Đây là phản hồi minh họa. AS có thể trả lỗi khác, chẳng hạn **invalid_client** cho lỗi xác thực client theo cơ chế HTTP và profile áp dụng.

Với lỗi **invalid_grant** mang ý nghĩa refresh token không còn sử dụng được, client cần **dừng dùng refresh token đó**, xóa hoặc vô hiệu hóa thông tin liên quan ở phía client và khởi động lại quy trình xác thực/ủy quyền khi cần. Với lỗi mạng tạm thời, cần chính sách retry có giới hạn; phải tránh gửi đồng thời nhiều yêu cầu sử dụng cùng refresh token nếu AS dùng rotation một lần.

## 5. Những ranh giới thời gian phải phân biệt

Một thiết kế token cần tách tối thiểu ba trạng thái:

**Thời hạn access token.** Ví dụ JWT có claim **exp**; opaque token có trạng thái/TTL do AS quản lý. Hết hạn access token chỉ nói rằng **token này không còn được chấp nhận**, không tự động có nghĩa người dùng bị đăng xuất khỏi mọi hệ thống.

**Thời hạn refresh token.** Refresh token có thể có hạn tuyệt đối, hạn không hoạt động (inactivity timeout), vòng đời gắn với phiên hoặc trạng thái ủy quyền, và có thể bị thu hồi trước hạn. Nó không bảo đảm sẽ có thể đổi token mãi mãi.

**Phiên đăng nhập và sự ủy quyền.** User session, consent, policy doanh nghiệp, trạng thái tài khoản và khả năng xác thực lại có thể có vòng đời riêng. Một refresh token còn tồn tại ở client cũng chưa đủ nếu AS đã chấm dứt phiên hoặc từ chối cấp token mới theo chính sách.

~~~text
Access token:     |------ hiệu lực ngắn ------|
Refresh token:    |---------- có thể xin token mới, nếu AS chấp nhận ----------|
User session:     |------ chính sách phiên / yêu cầu xác thực lại ------|

Các khoảng có thể không trùng nhau và có thể bị kết thúc sớm.
~~~

Ví dụ người dùng được cấp refresh token nhưng tài khoản bị khóa vì sự cố bảo mật. Khi token endpoint nhận yêu cầu refresh, AS phải tuân thủ chính sách khóa tài khoản thay vì chỉ nhìn refresh token chưa đến hạn.

Mặt khác, **thu hồi refresh token không tự động làm mọi access token đã phát hành hết hạn ngay** trong hệ thống dùng JWT xác minh ngoại tuyến. Nếu cần chặn quyền truy cập ngay lập tức, Resource Server cần kiểm tra trạng thái quyền hiện hành, danh sách thu hồi, introspection hoặc cơ chế đồng bộ phù hợp.

## 6. Refresh token rotation: mỗi lần đổi token sẽ thay chìa khóa gia hạn

Với **refresh token rotation**, AS phát hành refresh token mới khi đổi token thành công và vô hiệu hóa refresh token cũ. Theo một mô hình đơn giản:

~~~text
Lần cấp ban đầu:       AT-1, RT-1
Dùng RT-1 hợp lệ:      AT-2, RT-2      => RT-1 bị vô hiệu
Dùng RT-2 hợp lệ:      AT-3, RT-3      => RT-2 bị vô hiệu
Dùng lại RT-1/RT-2:   Bị từ chối và có thể kích hoạt xử lý nghi lộ token
~~~

**AT** là access token, **RT** là refresh token. Các chuỗi trên chỉ là ký hiệu ví dụ.

~~~mermaid
flowchart TD
    A["Client gửi RT hiện hành"] --> B{"AS kiểm tra trạng thái và ràng buộc"}
    B -->|Hợp lệ| C["Cấp AT mới và RT mới"]
    C --> D["Vô hiệu RT đã dùng; lưu quan hệ token family"]
    D --> E["Client thay RT lưu trữ bằng RT mới"]
    B -->|RT cũ bị dùng lại hoặc không hợp lệ| F["Từ chối refresh"]
    F --> G["Phân tích tái sử dụng, áp dụng chính sách thu hồi phiên/family"]
~~~

Một số triển khai theo dõi **token family** (chuỗi token kế thừa từ cùng phiên/cấp quyền). Nếu phát hiện token cũ bị dùng lại bất thường, AS có thể vô hiệu toàn bộ nhánh hoặc family để giảm khả năng kẻ tấn công giữ được refresh token mới nhất.

Điểm khó là AS không phải lúc nào phân biệt được người dùng hợp lệ và kẻ tấn công chỉ từ việc dùng lại token cũ. Ví dụ, máy người dùng đã nhận kết quả cấp token mới nhưng kết nối bị đứt trước khi lưu RT mới; client có thể vô tình gửi lại RT cũ. Chính sách **reuse detection** cần xét tính chất luồng, xử lý cạnh tranh và độ nhạy, không gắn nhãn tất cả lần tái sử dụng là bằng chứng chắc chắn đã bị xâm nhập.

### Rotation khác với gia hạn thời hạn access token như thế nào?

Khi AS đổi RT-1 thành RT-2, việc RT-1 bị vô hiệu **không mặc nhiên làm AT-1 hết hiệu lực ngay**. Access token có thời hạn và cơ chế thu hồi riêng. Rotation chủ yếu bảo vệ **khả năng tiếp tục nhận access token**, không tự xóa khả năng sử dụng access token đã phát hành.

### Rotation có đủ chống đánh cắp không?

Rotation có thể **phát hiện xung đột sử dụng** token cũ, nhưng không ngăn hoàn toàn kẻ tấn công sử dụng RT đã đánh cắp trước client hợp lệ. Nếu kẻ tấn công đang sở hữu token mới nhất và chạy trước, người dùng hợp lệ có thể gặp lỗi ở lần refresh sau. Vì thế cần kết hợp bảo vệ nơi lưu trữ, TTL, thu hồi khi có rủi ro và theo dõi bất thường.

## 7. Sender-constrained refresh token: giới hạn ai được dùng bản sao

Refresh token dạng **bearer** có thể bị kẻ nắm giữ bản sao sử dụng nếu các điều kiện khác vẫn đáp ứng. Cơ chế **sender-constraining** ràng buộc việc sử dụng token với bằng chứng sở hữu một khóa hoặc chứng chỉ của client.

Hai ví dụ phổ biến trong các ngữ cảnh thích hợp:

- **DPoP** (RFC 9449): client gửi proof được ký bằng khóa riêng, gắn với request; AS kiểm tra proof và ràng buộc token. Proof cần được xác minh theo đúng thuộc tính, thời gian và quy tắc chống phát lại của giao thức.
- **mTLS** (RFC 8705): token có thể ràng buộc với chứng chỉ client và chỉ được chấp nhận khi client chứng minh quyền sở hữu khóa liên quan.

Các cách này làm bản sao refresh token **khó sử dụng hơn** nếu kẻ tấn công không có khóa tương ứng. Chúng không loại bỏ rủi ro trên thiết bị bị kiểm soát, nơi kẻ tấn công có thể thao tác với khóa hoặc môi trường client.

Theo **OAuth 2.0 Security Best Current Practice (RFC 9700)**, refresh token cấp cho **public client** cần được bảo vệ bằng **rotation hoặc sender-constraining** để phát hiện/hạn chế lạm dụng. Cấu hình cụ thể tùy profile và loại ứng dụng; tránh giả định rằng một client secret nhúng trong SPA/mobile là bí mật thực sự.

## 8. Lưu trữ refresh token theo loại client

Refresh token có khả năng xin access token mới nên nơi lưu trữ của nó là một phần của mô hình bảo mật, không chỉ là lựa chọn tiện lợi của lập trình viên.

| Môi trường | Hướng thiết kế phù hợp | Rủi ro cần xử lý |
| --- | --- | --- |
| **Backend/confidential client** | Lưu ở phía server trong kho secret hoặc vùng dữ liệu được bảo vệ, hạn chế quyền truy cập và mã hóa phù hợp; dùng client authentication. | Rò rỉ log, backup, database, secret của client, truy cập nội bộ vượt quyền. |
| **Web có backend trung gian (BFF)** | Để backend quản lý token; trình duyệt giữ cookie phiên được cấu hình an toàn. | Cần cookie **HttpOnly**, **Secure**, **SameSite** phù hợp, chống CSRF và XSS; bảo vệ session store. |
| **SPA thuần trên trình duyệt** | Cân nhắc hạn chế cấp/lưu refresh token dài hạn; nếu cấp, áp dụng cơ chế bảo vệ theo BCP và chính sách AS. | XSS có thể đọc token nếu JavaScript có quyền truy cập, kể cả khi token nằm trong localStorage; refresh token rotation không tự triệt tiêu XSS. |
| **Ứng dụng mobile/native** | Sử dụng cơ chế lưu trữ an toàn của hệ điều hành như Keychain hoặc Keystore khi phù hợp, tránh log và backup không bảo vệ. | Thiết bị bị xâm nhập, backup rò rỉ, sao chép token giữa thiết bị, quản lý khóa. |
| **CLI/desktop app** | Dùng kho credential của hệ điều hành khi có thể; hạn chế quyền đọc file và xóa khi logout. | File cấu hình, shell history, chụp lỗi hoặc log chứa token. |

Không đưa refresh token vào **URL query string**, báo cáo lỗi, dữ liệu analytics, hoặc log ứng dụng. Chỉ gửi đến đúng token endpoint qua TLS. Nếu dùng cookie, **HttpOnly** ngăn JavaScript đọc trực tiếp cookie nhưng không tự chặn các yêu cầu độc hại được trình duyệt gửi; cần chống CSRF, XSS và cấu hình cookie phù hợp.

Việc lưu refresh token trong bộ nhớ chỉ đến khi tab đóng hay lưu lâu dài là quyết định chính sách. Thời gian tồn tại trên thiết bị cần phù hợp với yêu cầu đăng xuất, đăng nhập lại và mức rủi ro của ứng dụng.

## 9. Đồng bộ refresh khi nhiều yêu cầu API cùng hết hạn

Một lỗi thường xảy ra ở ứng dụng web: năm yêu cầu API nhận **401 Unauthorized** gần như cùng lúc, nên cả năm cùng gọi token endpoint bằng **cùng refresh token**. Nếu AS có rotation, yêu cầu đầu tiên có thể thành công và làm RT cũ vô hiệu, các yêu cầu còn lại bị xem là reuse.

Một client nên dùng cơ chế **single-flight**: tại một thời điểm, một phiên chỉ có **một** yêu cầu refresh đang chạy; các request khác chờ kết quả và sử dụng chung access token mới.

Mã giả:

~~~text
function getValidAccessToken():
    if cachedAccessToken is usableWithSafetyMargin:
        return cachedAccessToken

    if refreshPromise exists:
        return await refreshPromise

    refreshPromise = refreshAtAuthorizationServer(
        currentRefreshToken,
        requiredClientBindingOrAuthentication
    )

    try:
        response = await refreshPromise
        atomicallyStoreTokens(
            response.accessToken,
            response.refreshTokenIfProvided
        )
        return response.accessToken
    finally:
        refreshPromise = null
~~~

**atomicallyStoreTokens** ở đây có ý nghĩa: khi AS cấp RT mới, ứng dụng phải tránh trạng thái lưu **AT mới nhưng RT cũ** do cập nhật dang dở. Với nhiều tab, nhiều tiến trình hoặc nhiều instance backend, single-flight trong một tiến trình có thể chưa đủ; cần cơ chế khóa/đồng bộ phù hợp với phạm vi sử dụng token.

### Có nên refresh sau mọi lỗi 401?

Chỉ nên thử refresh khi có căn cứ **access token hết hạn/không còn phù hợp về thời gian** và hệ thống còn khả năng refresh. Không phải mọi 401 đều được khắc phục bằng cách refresh; token sai audience, cấu hình sai issuer hoặc thông tin xác thực bị từ chối cần được xử lý đúng nguyên nhân.

- **401** thường liên quan thiếu hoặc không chấp nhận credential; một lần refresh có kiểm soát có thể hữu ích khi access token hết hạn.
- **403 Forbidden** thường nghĩa là request được nhận diện nhưng **không đủ quyền**. Refresh không phải giải pháp tự động để “xin thêm scope” hoặc vượt policy.
- Với yêu cầu tạo hoặc thay đổi dữ liệu, việc **retry request sau refresh** cần chú ý tính idempotent/idempotency key để không gây hành vi nghiệp vụ trùng lặp.
- Hạn chế retry, tránh vòng lặp vô hạn và phải xóa trạng thái/token không còn dùng được khi AS trả lỗi chấm dứt quyền refresh.

## 10. Hết hạn, thu hồi và các tình huống sự cố

Refresh token giúp duy trì trải nghiệm liên tục, nhưng phải có quy tắc **kết thúc**.

| Tình huống | AS/Resource Server cần xem xét | Hành vi client phù hợp |
| --- | --- | --- |
| **Access token hết hạn, RT còn hợp lệ** | AS kiểm RT, client, ràng buộc và chính sách hiện hành; cấp AT mới nếu được phép. | Refresh một lần có kiểm soát, lưu token mới, gọi API lại nếu an toàn. |
| **RT hết hạn hoặc bị thu hồi** | AS từ chối, thường bằng lỗi invalid_grant. | Dừng refresh bằng RT đó, khởi động lại đăng nhập/ủy quyền nếu cần. |
| **Người dùng chủ động đăng xuất** | Thu hồi RT/phiên ở AS khi hệ thống hỗ trợ, xử lý AT đang lưu hành theo chính sách. | Xóa credential/token cục bộ, kết thúc phiên UI, không chỉ ẩn giao diện. |
| **Tài khoản bị khóa hoặc quyền bị rút** | AS từ chối cấp mới theo policy; API tiếp tục kiểm quyền hiện hành trên tài nguyên. | Không dùng access token còn hạn để bỏ qua quyết định của API. |
| **RT bị đánh cắp và dùng lại** | Theo dõi token family, xác minh sender binding, phát hiện reuse và thu hồi theo chính sách. | Xóa phiên bị ảnh hưởng, yêu cầu xác thực lại, thông báo lỗi có kiểm soát. |
| **AS tạm thời không khả dụng** | Quy tắc xử lý lỗi và tính sẵn sàng; không cấp quyền chỉ vì không tra cứu được. | Retry có giới hạn/backoff, không ghi token vào log, không xoay vòng tự tạo. |
| **Client cần scope hoặc audience khác** | Kiểm tra yêu cầu ủy quyền mới, policy, và giao thức có hỗ trợ hay không. | Không tự coi refresh là cơ chế đổi bất kỳ token nào thành quyền rộng hơn. |

Đăng xuất khỏi client bằng cách xóa token **không bảo đảm** những bản sao đã bị lộ ở nơi khác lập tức mất hiệu lực. OAuth 2.0 có cơ chế **revocation** (RFC 7009), còn Resource Server có thể dùng **introspection** (RFC 7662) hoặc giải pháp trạng thái/thu hồi khác tùy loại token.

Trong hệ thống JWT access token tự xác minh ngoại tuyến, RT đã bị thu hồi không đồng nghĩa các AT đã cấp tự đổi chữ ký hay hết hạn sớm. Đối với tác vụ có yêu cầu thu hồi gần như ngay lập tức, cần cơ chế để API biết thay đổi quyền/phiên, ngoài việc đặt AT có thời hạn ngắn.

## 11. Refresh token trong OAuth 2.0 và OpenID Connect (OIDC)

**OAuth 2.0** mô tả cơ chế ủy quyền. Access token cho API, còn refresh token (nếu được cấp) cho AS một cơ sở để xem xét phát hành access token mới. Việc phát hành refresh token là tùy theo grant type, client và policy.

**OIDC** bổ sung lớp thông tin xác thực và **ID token** dành cho client. Khi ứng dụng cần duy trì truy cập API, nó dùng **access token**; ID token không phải credential để Resource Server chấp nhận thay access token.

Các điểm thường nhầm:

- Scope **openid** kích hoạt yêu cầu thuộc OIDC; bản thân scope này không có nghĩa cho phép thao tác API nghiệp vụ.
- **offline_access** là một scope OIDC dùng khi yêu cầu khả năng truy cập lúc người dùng không hiện diện, kèm điều kiện consent và chính sách tương ứng. Việc yêu cầu offline_access **không bảo đảm** AS sẽ cấp refresh token.
- Refresh token trong OIDC có thể được dùng để xin token mới theo quy tắc token endpoint. Nếu AS trả ID token mới, client phải xác minh theo OIDC; **refresh không tự chứng minh người dùng vừa xác thực lại**.
- Nếu thao tác cần xác thực gần đây, hệ thống có thể dùng cơ chế OIDC như **max_age**, **auth_time** hoặc quy trình step-up phù hợp. Không nên dựa vào thời điểm access token được refresh để suy ra thời điểm user nhập lại mật khẩu/MFA.

### Refresh không phải token exchange

**Refresh token grant** trong OAuth 2.0 là cách xin token mới trong khuôn khổ ủy quyền đang có. **Token exchange** (RFC 8693) là một cơ chế khác, với mục đích và tham số riêng để trao đổi token trong những tình huống được AS hỗ trợ. Không dùng refresh token grant như đường tắt để tự chuyển token của API A thành token cho API B hoặc nâng scope khi không có chính sách cho phép.

Trong mô hình **client credentials**, ứng dụng có thể xin AT mới trực tiếp với grant tương ứng và cơ chế xác thực client; không nên áp đặt mô hình refresh token của phiên người dùng lên mọi dịch vụ.

## 12. Một trường hợp kiểm chứng end-to-end

Giả sử ứng dụng dashboard dùng **Authorization Code + PKCE**, và AS cấp:

~~~text
AT-1:
    aud = orders-api
    scope = "orders:read orders:write"
    hạn dùng = 10 phút

RT-1:
    được ràng buộc với client dashboard theo chính sách
    chỉ dùng tại token endpoint của AS
    bị vô hiệu khi rotation cấp RT-2
~~~

**Tình huống 1 — Access token hết hạn, chính sách không đổi.** Dashboard gửi RT-1 hợp lệ đến AS; AS có thể cấp AT-2 và RT-2. Dashboard cập nhật RT mới theo cách an toàn và gọi Orders API bằng AT-2. Đây là mục đích điển hình của refresh token.

**Tình huống 2 — Người dùng mất quyền sửa đơn hàng.** RT vẫn có thể còn hiệu lực, nhưng AS hoặc policy của hệ thống có thể giảm scope khi cấp AT mới, hoặc API từ chối thao tác cập nhật dựa trên permission hiện tại. **AT có orders:write không tự bảo đảm permission sửa từng đơn hàng.**

**Tình huống 3 — RT-1 bị đánh cắp, rồi dùng lại sau rotation.** AS phát hiện RT-1 đã vô hiệu. Theo chính sách, AS từ chối request, đánh dấu tín hiệu reuse và có thể thu hồi token family. Để xác định phạm vi ảnh hưởng, hệ thống cần giám sát, khóa phiên và quy trình phản ứng sự cố phù hợp.

**Tình huống 4 — Người dùng đăng xuất.** Dashboard xóa trạng thái đăng nhập cục bộ và, nếu được hỗ trợ, yêu cầu AS thu hồi refresh token/phiên. Access token đã phát hành phải được xử lý theo thời hạn và cơ chế thu hồi/kiểm tra quyền của Resource Server. Không khẳng định một lần logout tự vô hiệu hóa tất cả JWT ngoại tuyến.

**Tình huống 5 — Client gửi RT đến Orders API.** Orders API phải từ chối vì refresh token không phải access token dành cho Resource Server. Token endpoint của AS là nơi xem xét refresh token.

## 13. Những sai lầm cần tránh

**“Refresh token là access token có exp dài.”** Sai về mục đích. Refresh token thuộc luồng cấp token tại AS, không phải giấy phép gọi API.

**“Access token hết hạn nghĩa là người dùng đã logout.”** Không nhất thiết. Client có thể xin token mới khi RT và sự ủy quyền còn hợp lệ; user session và AT có vòng đời khác nhau.

**“Cứ có refresh token là có thể xin token vô hạn.”** Không. AS có thể áp dụng hết hạn tuyệt đối, hạn không hoạt động, đổi token một lần, xác thực client, trạng thái phiên, thu hồi và chính sách thay đổi.

**“Rotation ngăn hoàn toàn việc đánh cắp RT.”** Rotation giúp giới hạn/phát hiện việc sử dụng lại token cũ, còn RT mới nhất vẫn có thể bị kẻ tấn công khai thác nếu môi trường hoặc khóa bị chiếm quyền.

**“Dùng RT để lấy scope mới nào cũng được.”** Không. Refresh không được dùng để tự mở rộng phạm vi đã cấp; yêu cầu quyền mới có thể cần luồng ủy quyền mới và sự chấp thuận tương ứng.

**“Frontend báo logout thì JWT access token cũ chắc chắn không dùng được.”** Không tự động. Cần chiến lược thu hồi/kiểm tra phù hợp tại AS và RS.

**“Mọi 401 và 403 đều phải refresh rồi retry.”** Không. Chỉ refresh khi vấn đề thực sự có thể được khắc phục bằng access token mới; 403 do thiếu quyền cần điều chỉnh quyền hoặc từ chối.

## 14. Checklist triển khai refresh an toàn

Khi thiết kế cơ chế refresh token trong một hệ thống thực tế, nên xác định rõ:

1. **Điều kiện cấp RT:** Những client/grant nào nhận RT? Có cần consent, offline access, thiết bị tin cậy, chính sách doanh nghiệp hay không?
2. **Bảo vệ token:** RT được lưu ở đâu, ai có thể đọc, có bị ghi log/backup không, có TLS và ràng buộc đúng client không?
3. **Chính sách vòng đời:** RT có hết hạn tuyệt đối, hết hạn khi không hoạt động hoặc khi kết thúc phiên không? Hành vi khi người dùng bị khóa, thu hồi quyền hoặc logout là gì?
4. **Rotation hoặc sender binding:** Public client áp dụng biện pháp chống sao chép nào? AS lưu trạng thái token family và xử lý reuse ra sao?
5. **Đồng bộ client:** Có single-flight refresh, cập nhật RT một cách nhất quán, xử lý nhiều tab/instance và retry có giới hạn không?
6. **Bảo vệ API:** RS kiểm access token đúng issuer, audience, scope, hiệu lực và quyền theo tài nguyên; có từ chối refresh token dùng sai nơi không?
7. **Phản ứng sự cố:** Có khả năng thu hồi, theo dõi token bất thường, xóa session và yêu cầu đăng nhập lại không?
8. **Kiểm thử:** Có thử AT hết hạn; RT sai/hết hạn/thu hồi; dùng lại RT cũ; race giữa các refresh; login/logout; sai client; sai audience; thay đổi role/scope trong phiên; AS bị lỗi không?

Thiết kế tốt nhất là thiết kế có thể trả lời cụ thể: **khi token bị lộ, tài khoản bị khóa hoặc ủy quyền thay đổi, mất bao lâu để client không thể lấy thêm access token và API không còn chấp nhận những quyền cũ?**

## Kết luận

**Refresh token là một công cụ quản lý vòng đời quyền truy cập**, cho phép client xin access token mới ở Authorization Server khi vẫn thỏa điều kiện ủy quyền. Nó giải quyết nhu cầu kết hợp **access token sống ngắn** với trải nghiệm sử dụng liên tục, nhưng đổi lại cần bảo vệ một credential có giá trị lớn trong thời gian dài hơn.

Một hệ thống OAuth 2.0/OIDC an toàn phải phân biệt rõ nơi nhận và ý nghĩa của access token, refresh token và ID token; kiểm tra scope, audience và quyền hiện hành; quản lý thời hạn và thu hồi; đồng thời thiết kế **rotation hoặc sender-constraining, lưu trữ an toàn và xử lý refresh cạnh tranh**. Việc cấp lại token thành công không biến quyền truy cập thành vĩnh viễn và không thay thế quyết định phân quyền của Resource Server.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 6: Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Refresh Token](https://openid.net/specs/openid-connect-core-1_0.html#RefreshTokens)
