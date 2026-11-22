# Thời hạn, độ mới và chính sách sai lệch đồng hồ

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Chính sách thời gian và vòng đời JWT ở mức giao thức/hệ thống, không phụ thuộc Java, Spring hay framework cụ thể.

Một JWT có chữ ký hợp lệ vẫn có thể phải bị từ chối vì **đã hết hạn, chưa đến thời điểm được phép sử dụng, được phát hành quá lâu hoặc có mốc thời gian bất hợp lý**. Các bên phát hành và tiếp nhận cũng có thể dùng đồng hồ lệch nhau: token vừa được phát hành có thể bị từ chối vì máy nhận chạy chậm, hoặc token đã hết hạn vẫn được chấp nhận vì máy nhận chạy chậm theo hướng ngược lại.

Hợp đồng token cần xác định rõ:

- Token bắt đầu có hiệu lực khi nào và hết hiệu lực khi nào?
- Token được phép sống tối đa bao lâu?
- Token có được chấp nhận nếu được phát hành quá lâu trước đó không?
- Đồng hồ giữa các hệ thống được phép lệch bao nhiêu?
- Cách xử lý token hết hạn, thu hồi, cache và các yêu cầu đang chạy ra sao?

**Thời hạn (lifetime), độ mới (freshness) và sai lệch đồng hồ (clock skew) là các chính sách khác nhau.** Chúng cần được thiết kế cùng nhau để tránh token sống quá lâu hoặc bị từ chối ngẫu nhiên.

## 1. Ba mốc thời gian chuẩn trong JWT

RFC 7519 định nghĩa ba registered claims thường được dùng để kiểm soát thời gian:

| Claim | Tên đầy đủ | Ý nghĩa | Kiểu dữ liệu |
|---|---|---|---|
| **iat** | Issued At | Thời điểm token được phát hành | NumericDate |
| **nbf** | Not Before | Thời điểm token bắt đầu có hiệu lực | NumericDate |
| **exp** | Expiration Time | Thời điểm token hết hiệu lực | NumericDate |

**NumericDate** là số JSON biểu diễn số giây từ Unix epoch (1970-01-01T00:00:00Z). Giá trị có thể có phần thập phân theo RFC; hợp đồng nên thống nhất độ chính xác và cách làm tròn để các bên không diễn giải khác nhau. Đơn vị là **giây**, không phải mili giây.

### 1.1. iat — thời điểm phát hành

Ví dụ:

~~~json
{
  "iat": 1794800000
}
~~~

Claim **iat** ghi lại thời điểm issuer tạo token. Nó hỗ trợ:

- Kiểm tra token có được phát hành trong tương lai bất hợp lý hay không.
- Tính tuổi token để áp dụng giới hạn freshness.
- Điều tra và truy vết thời điểm token được cấp.
- Áp dụng chính sách từ chối token phát hành trước một mốc, chẳng hạn sau khi thay đổi thông tin xác thực hoặc sau một sự cố.

**iat không tự làm token hết hạn.** Nếu không có **exp** hoặc một chính sách giới hạn tuổi riêng, một JWT có **iat** cũ vẫn có thể được chấp nhận theo các điều kiện khác. Không được nhầm “biết thời điểm phát hành” với “biết token còn hiệu lực”.

### 1.2. nbf — thời điểm bắt đầu có hiệu lực

Ví dụ:

~~~json
{
  "nbf": 1794800000
}
~~~

Token không được chấp nhận trước thời điểm **nbf**. Theo quy tắc JWT, token bắt đầu hợp lệ tại hoặc sau thời điểm này, có tính đến chính sách dung sai thời gian của bên xác minh.

**nbf** hữu ích khi token được phát hành trước nhưng chỉ được sử dụng từ một thời điểm đã định, ví dụ:

- Vé truy cập hoặc quyền được kích hoạt theo lịch.
- Token cho một giao dịch chỉ bắt đầu sau thời điểm phê duyệt.
- Token được tạo trước để phân phối nhưng chưa được sử dụng ngay.

Nếu không có nhu cầu này, không cần thêm **nbf** một cách máy móc. Claim bắt buộc hay tùy chọn phải theo token profile và hợp đồng.

### 1.3. exp — thời điểm hết hạn

Ví dụ:

~~~json
{
  "exp": 1794800600
}
~~~

Token không được chấp nhận tại hoặc sau thời điểm **exp**. Nói cách khác, điều kiện thời gian cơ bản là:

\[
\text{now} < \text{exp}
\]

Khi thời gian hiện tại bằng đúng **exp**, token đã hết hạn. Một số thư viện có thể cung cấp tham số dung sai; cách áp dụng phải được hiểu và cấu hình nhất quán, không nên vô tình cộng thêm thời gian sống cho token.

### 1.4. Quan hệ giữa ba mốc

Một hợp đồng thường kiểm tra:

- **iat ≤ exp:** token không thể hết hạn trước thời điểm phát hành.
- **nbf ≤ exp:** thời điểm bắt đầu không được sau thời điểm hết hạn.
- **iat** không vượt quá thời điểm hiện tại quá dung sai cho phép.
- **nbf** không nằm quá xa trong tương lai nếu hệ thống có giới hạn phát hành.
- **exp - iat** không vượt thời hạn tối đa của loại token.

Quan hệ giữa **iat** và **nbf** phụ thuộc mục đích. Nhiều token có **iat ≤ nbf ≤ exp**; tuy nhiên, không nên biến quan hệ này thành quy tắc phổ quát nếu profile cho phép trường hợp khác. Điều quan trọng là định nghĩa rõ chính sách và không chấp nhận các mốc mâu thuẫn.

## 2. Lifetime, freshness và validity window

Ba khái niệm này thường bị gộp làm một, dẫn đến hợp đồng khó kiểm soát.

| Khái niệm | Cách hiểu | Câu hỏi |
|---|---|---|
| **Lifetime** | Khoảng thời gian token được phép sống theo chính sách phát hành, thường là exp trừ iat | Token có thể tồn tại tối đa bao lâu? |
| **Freshness / token age** | Tuổi của token tại thời điểm kiểm tra, thường là now trừ iat | Token đã được phát hành từ bao lâu? |
| **Validity window** | Khoảng thời gian token thực sự được phép dùng, thường bắt đầu từ nbf và kết thúc trước exp | Token có hiệu lực tại thời điểm hiện tại không? |

Ví dụ: token được phát hành lúc 10:00, có **nbf = 10:02**, **exp = 10:10**. Thời gian sống tính từ lúc phát hành là 10 phút; cửa sổ hiệu lực là 8 phút. Khi kiểm tra lúc 10:08, token còn hiệu lực và có tuổi 8 phút.

### 2.1. Giới hạn lifetime

Hợp đồng có thể đặt:

\[
\text{exp} - \text{iat} \leq L_{\max}
\]

Trong đó \(L_{\max}\) là lifetime tối đa theo loại token. Ví dụ minh họa:

| Loại token | Lifetime tham khảo | Lý do |
|---|---:|---|
| Access token cho API có rủi ro cao | 5–10 phút | Giảm khoảng thời gian sử dụng nếu token bị lộ |
| Access token cho ứng dụng thông thường | 10–15 phút | Cân bằng bảo mật và trải nghiệm |
| Token xác minh một giao dịch nhạy cảm | Vài phút hoặc ngắn hơn | Gắn với một quy trình cụ thể |
| Token khôi phục mật khẩu | Ngắn, theo thời gian hoàn tất quy trình | Giảm cơ hội chiếm dụng liên kết khôi phục |
| ID token | Theo yêu cầu của OIDC và chính sách client | Không dùng lifetime của access token để thay thế quy tắc OIDC |

Các khoảng thời gian trên chỉ là **ví dụ thiết kế**, không phải giá trị bắt buộc của RFC. Thời hạn thực tế phải dựa trên mức độ nhạy cảm, cách lưu token, khả năng refresh, khả năng thu hồi và yêu cầu vận hành.

Không nên phát hành access token có thời hạn rất dài chỉ để tránh phải refresh. Nếu cần phiên người dùng dài, hãy thiết kế cơ chế gia hạn riêng với chính sách bảo vệ và thu hồi phù hợp.

### 2.2. Giới hạn freshness theo iat

Một hệ thống có thể yêu cầu token phải được phát hành gần thời điểm sử dụng:

\[
\text{now} - \text{iat} \leq A_{\max}
\]

Trong đó \(A_{\max}\) là tuổi tối đa được chấp nhận. Điều kiện này có ích khi:

- Token chỉ nên được dùng trong một phiên hoặc một giao dịch gần thời điểm xác thực.
- Một thao tác nhạy cảm yêu cầu xác thực lại gần đây.
- Hệ thống cần từ chối token cũ sau khi thay đổi chính sách hoặc thông tin xác thực.

Freshness không đồng nghĩa với lifetime. Một token có **exp** còn xa nhưng **iat** quá cũ vẫn có thể bị từ chối nếu hợp đồng giới hạn tuổi. Ngược lại, token vừa phát hành nhưng **nbf** ở tương lai chưa thể được sử dụng.

Đối với thao tác yêu cầu người dùng xác thực gần đây, không nên tự coi **iat** của mọi access token là bằng chứng đầy đủ rằng người dùng vừa đăng nhập. Token có thể được cấp lại bằng refresh token. Với OIDC, claim **auth_time** biểu diễn thời điểm xác thực người dùng; client có thể áp dụng **max_age** và kiểm tra **auth_time** theo quy tắc OIDC khi cần xác thực mới. Cần phân biệt thời điểm phát hành token (**iat**) với thời điểm người dùng thực sự xác thực (**auth_time**).

### 2.3. Cửa sổ hiệu lực

Nếu hợp đồng sử dụng cả **nbf** và **exp**, cửa sổ cơ bản là:

\[
\text{nbf} \leq \text{now} < \text{exp}
\]

Khi có dung sai đồng hồ, cách kiểm tra cụ thể có thể nới hoặc siết hai biên. Chính sách phải quy định rõ:

- Dung sai được áp dụng cho **exp**, **nbf**, **iat** hay tất cả?
- Dung sai có được cộng vào thời hạn token hay chỉ bù chênh lệch đồng hồ?
- Có áp dụng cùng một giá trị cho mọi loại token không?
- Có giới hạn thời gian hiệu lực tối đa độc lập với dung sai không?

Không để một tham số leeway chung của thư viện vô tình làm nới mọi điều kiện thời gian vượt quá ý định của hợp đồng.

## 3. Clock skew và đồng bộ thời gian

### 3.1. Vì sao đồng hồ lệch nhau?

Trong hệ thống phân tán, issuer và resource server có thể chạy trên nhiều máy, vùng mạng hoặc nhà cung cấp hạ tầng khác nhau. Đồng hồ có thể lệch vì:

- Máy chủ chưa đồng bộ thời gian hoặc cấu hình đồng bộ sai.
- Đồng hồ phần cứng bị trôi theo thời gian.
- Máy ảo/container nhận thời gian từ host không ổn định.
- Mạng hoặc dịch vụ đồng bộ thời gian gặp sự cố.
- Một hệ thống dùng thời gian cục bộ sai múi giờ hoặc chuyển đổi timestamp sai.

JWT NumericDate dựa trên thời gian tuyệt đối từ Unix epoch; múi giờ hiển thị không làm thay đổi giá trị. Hệ thống nên sử dụng đồng hồ hệ thống được đồng bộ với nguồn thời gian tin cậy, thường qua NTP hoặc cơ chế tương đương.

### 3.2. Minh họa clock skew

Giả sử issuer phát hành token với:

- **iat = 10:00:00**
- **nbf = 10:00:00**
- **exp = 10:10:00**

Nhưng đồng hồ của API nhanh hơn đồng hồ issuer 40 giây. API có thể đánh giá token hết hạn sớm hơn thực tế 40 giây. Nếu đồng hồ API chậm hơn 40 giây, token có thể tiếp tục được chấp nhận sau thời điểm hết hạn thực tế.

<text weight="semibold" size="sm">Ví dụ hai đồng hồ lệch 40 giây</text>

| Thời gian thực | Đồng hồ issuer | Đồng hồ API nhanh 40 giây | Tác động |
|---|---|---|---|
| 10:00:00 | 10:00:00 | 10:00:40 | API nhanh hơn sẽ tính token đã có tuổi 40 giây; việc kiểm tra nbf/iat phải dùng cùng chính sách dung sai |
| 10:09:40 | 10:09:40 | 10:10:20 | API có thể từ chối sớm vì đã qua exp theo đồng hồ API |
| 10:10:00 | 10:10:00 | 10:10:40 | Token đã hết hạn theo issuer và API |

Nếu API chậm 40 giây, tại thời điểm thực 10:10:20, API chỉ đọc 10:09:40 và có thể chấp nhận token đã hết hạn theo đồng hồ chuẩn. Vì vậy clock skew ảnh hưởng cả khả năng sẵn sàng lẫn giới hạn bảo mật.

### 3.3. Đồng bộ thời gian là biện pháp gốc

Clock skew tolerance chỉ là biện pháp bù sai lệch nhỏ, không thay thế đồng bộ thời gian. Hệ thống nên:

1. Đồng bộ thời gian cho issuer, API, gateway và các dịch vụ liên quan qua nguồn thời gian tin cậy.
2. Giám sát độ lệch đồng hồ (offset), trạng thái đồng bộ và thời điểm đồng bộ gần nhất.
3. Cảnh báo khi offset vượt ngưỡng vận hành.
4. Xử lý lỗi đồng bộ thời gian như một sự cố hạ tầng có ảnh hưởng đến xác thực.
5. Dùng thời gian UTC/Unix epoch cho logic so sánh; chỉ chuyển sang múi giờ địa phương khi hiển thị.

Đối với đo khoảng thời gian nội bộ trong một tiến trình, đồng hồ monotonic phù hợp hơn đồng hồ wall-clock vì không bị nhảy lùi/tiến do điều chỉnh thời gian. Tuy nhiên, so sánh **exp**, **nbf**, **iat** là so sánh với thời điểm tuyệt đối, nên cần wall-clock đã được đồng bộ; monotonic clock không thay thế NumericDate.

## 4. Chính sách leeway cho sai lệch đồng hồ

### 4.1. Leeway là gì?

**Leeway** (clock tolerance/skew allowance) là khoảng dung sai nhỏ mà bên xác minh cho phép để bù chênh lệch đồng hồ giữa các thành phần. RFC 7519 cho phép một lượng nhỏ leeway khi xử lý các mốc thời gian, đặc biệt **exp** và **nbf**.

Ví dụ, nếu hợp đồng cho phép leeway 30 giây, một API có thể chấp nhận token vừa mới đến **nbf** hoặc vừa qua **exp** trong giới hạn dung sai theo đúng quy tắc đã định nghĩa. Đây chỉ là ví dụ; con số thực tế phải dựa trên độ lệch đồng hồ đo được và mức rủi ro.

### 4.2. Cách biểu diễn điều kiện

Một cách mô tả chính sách phổ biến với leeway \(S\):

\[
\text{now} + S \geq \text{nbf}
\]

\[
\text{now} - S < \text{exp}
\]

Tức là cho phép token được chấp nhận sớm hơn **nbf** tối đa \(S\), và muộn hơn **exp** tối đa \(S\). Nếu áp dụng dung sai cho **iat**, cần quy định riêng cách kiểm tra thời điểm phát hành trong tương lai. Đây là mô hình giải thích; cần đối chiếu đúng semantics của thư viện và profile đang sử dụng.

### 4.3. Chọn leeway có căn cứ

Không chọn leeway lớn chỉ để “hết lỗi token hết hạn”. Nên:

- Đo độ lệch thời gian thực tế giữa issuer và các bên nhận.
- Chọn dung sai nhỏ đủ bao phủ sai lệch vận hành bình thường.
- Tách ngưỡng cảnh báo hạ tầng khỏi giá trị leeway trong xác minh.
- Áp dụng chính sách chặt hơn cho token có rủi ro cao hoặc quy trình một lần.
- Kiểm tra tổng thời gian sống hiệu quả sau khi cộng dung sai; không để lifetime bị mở rộng ngoài dự kiến.
- Định kỳ xem lại leeway khi hạ tầng và cơ chế đồng bộ thay đổi.

Nếu đồng hồ lệch vài phút hoặc vài giờ, nên sửa hạ tầng. Tăng leeway tương ứng có thể khiến token hết hạn tiếp tục được sử dụng trong thời gian quá dài.

### 4.4. Không cộng leeway nhiều lần

Một hệ thống có thể có gateway, API và thư viện xác minh riêng. Nếu mỗi tầng tự cộng leeway 30 giây, phạm vi chấp nhận thực tế có thể lớn hơn dự kiến hoặc các tầng có kết quả khác nhau.

Hợp đồng nên quy định:

- Thành phần nào là nơi xác minh thời gian chính.
- Các tầng sau có xác minh lại hay tin kết quả từ tầng trước.
- Nếu nhiều tầng cùng xác minh, mỗi tầng dùng cùng chính sách và không cộng dồn dung sai.
- Thời hạn token ở issuer đã được tính thế nào; không để issuer tự cộng leeway rồi API tiếp tục cộng thêm.

## 5. Quy tắc kiểm tra thời gian theo loại token

Không phải mọi loại JWT đều có cùng lifetime hoặc freshness policy. Cần xác định theo mục đích.

| Loại token | Quy tắc thời gian thường cần | Điểm chú ý |
|---|---|---|
| Access token | **exp**; thường có **iat**; **nbf** nếu cần; lifetime ngắn và giới hạn tuổi | Resource server kiểm tra tại mỗi yêu cầu |
| ID token | **iat**, **exp** theo OIDC; **auth_time** khi yêu cầu xác thực mới; **nonce** theo luồng | Client không áp dụng tùy tiện quy tắc access token |
| Refresh token dạng JWT (nếu dùng) | Hạn sử dụng, thời gian phát hành, trạng thái rotation/reuse và thu hồi | Chỉ authorization server/token endpoint xử lý |
| Password reset token | **exp** ngắn, **iat**, **jti** và trạng thái một lần dùng | Phải gắn với đúng yêu cầu khôi phục |
| Email verification token | **exp**, **jti** và trạng thái xác minh | Không cho phép dùng lại sau khi hoàn tất |
| Service-to-service token | **exp** ngắn, **iat**, giới hạn lifetime, danh tính client | Cân bằng tự động hóa và khả năng thu hồi |

### 5.1. Access token và refresh token

Access token thường có thời hạn ngắn để giảm khoảng thời gian bị lạm dụng khi lộ token. Khi hết hạn, client có thể yêu cầu token mới bằng refresh token theo giao thức. Refresh token có vòng đời và chính sách thu hồi riêng; không kéo dài **exp** của access token cũ.

Nếu refresh token được xoay vòng (rotation), authorization server cần phát hiện việc tái sử dụng token cũ theo chính sách. Chỉ kiểm tra **exp** là chưa đủ để xử lý replay hoặc reuse.

### 5.2. Xác thực mới và thao tác nhạy cảm

Một access token vừa được phát hành không nhất thiết chứng minh người dùng vừa nhập lại mật khẩu hoặc hoàn thành MFA. Với OIDC, **auth_time** biểu diễn thời điểm xác thực người dùng; yêu cầu **max_age** có thể buộc xác thực mới. Hệ thống cần kiểm tra claim phù hợp và các bằng chứng xác thực theo giao thức, thay vì chỉ so sánh **iat**.

### 5.3. Token một lần và chống phát lại

Token khôi phục mật khẩu hoặc xác nhận giao dịch có thể cần **jti** và kho trạng thái dùng một lần. Khi thao tác thành công, đánh dấu token/request đã tiêu thụ; các lần gửi lại phải bị từ chối dù **exp** vẫn còn ở tương lai.

Điều này cho thấy thời hạn là điều kiện cần nhưng không phải điều kiện đủ. Token còn hạn vẫn có thể bị từ chối vì đã sử dụng, đã bị thu hồi hoặc không còn khớp trạng thái nghiệp vụ.

## 6. Hết hạn, thu hồi và cache

### 6.1. Hết hạn không giống thu hồi

**Expiration** là mốc thời gian được ghi trong token. Khi đến mốc đó, token tự hết hiệu lực theo quy tắc thời gian.

**Revocation** là quyết định vô hiệu hóa token trước khi hết hạn, ví dụ:

- Người dùng đăng xuất khỏi tất cả thiết bị hoặc tài khoản bị khóa.
- Refresh token bị phát hiện tái sử dụng.
- Khóa ký token bị lộ.
- Quyền truy cập hoặc phiên bị quản trị viên thu hồi.
- Token một lần đã được sử dụng.

JWT tự chứa thường được xác minh offline bằng chữ ký và claim. Nếu không có kiểm tra trạng thái bên ngoài, resource server có thể tiếp tục chấp nhận token đã bị thu hồi cho đến khi hết hạn. Vì vậy lifetime ngắn, danh sách thu hồi, introspection hoặc cơ chế kiểm tra trạng thái có thể cần thiết tùy rủi ro.

### 6.2. Những lựa chọn kiểm soát trạng thái

| Cơ chế | Ưu điểm | Chi phí / giới hạn |
|---|---|---|
| Access token lifetime ngắn | Đơn giản, giảm cửa sổ bị lạm dụng | Không thu hồi tức thời |
| Denylist theo **jti** | Thu hồi token cụ thể | Cần lưu trạng thái đến khi token hết hạn; tra cứu mỗi lần hoặc qua cache |
| Token introspection | Resource server hỏi authorization server trạng thái token | Phụ thuộc mạng/dịch vụ; cần cache policy |
| Phiên hoặc version người dùng | Có thể vô hiệu hóa nhiều token cùng lúc | Cần trạng thái phía server và quy tắc đồng bộ |
| Thu hồi khóa | Vô hiệu hóa token ký bằng khóa bị xâm phạm | Có thể ảnh hưởng nhiều token hợp lệ khác |

Không có một cơ chế phù hợp cho mọi hệ thống. Chọn dựa trên yêu cầu thu hồi tức thời, quy mô, độ sẵn sàng và mức độ nhạy cảm.

### 6.3. Cache và thời hạn token

Nếu cache kết quả xác minh hoặc kết quả introspection:

- Không cache trạng thái hợp lệ lâu hơn **exp** còn lại.
- Cache denylist/revocation phải được cập nhật đủ nhanh so với yêu cầu thu hồi.
- Tính đến clock skew và thời gian lan truyền trạng thái giữa các node.
- Không dùng cache để kéo dài token sau khi hết hạn.
- Khi không thể kiểm tra trạng thái do lỗi mạng, phải có chính sách fail-open/fail-closed rõ theo mức rủi ro; không mặc định chấp nhận mọi token.

Một cache hợp lệ tại thời điểm T có thể không còn hợp lệ tại T+1 nếu token đã hết hạn hoặc bị thu hồi. Cache TTL phải bị chặn bởi thời gian còn lại và chính sách trạng thái.

## 7. Yêu cầu đang chạy và thời điểm kiểm tra

Một yêu cầu có thể bắt đầu ngay trước khi token hết hạn và hoàn thành sau đó. Hợp đồng cần nói rõ **thời điểm xác thực được đánh giá**:

- Với API thông thường, xác minh token tại thời điểm tiếp nhận yêu cầu thường là đủ; yêu cầu đã được chấp nhận có thể hoàn tất theo giới hạn xử lý của dịch vụ.
- Với kết nối dài, streaming, WebSocket hoặc tác vụ kéo dài, cần chính sách kiểm tra lại khi kết nối tiếp tục hoặc khi thực hiện thao tác nhạy cảm.
- Với giao dịch có thời gian xử lý lâu, có thể cần kiểm tra quyền và trạng thái ở thời điểm commit, không chỉ lúc bắt đầu.
- Không tự động ngắt mọi yêu cầu đang chạy đúng giây **exp** nếu kiến trúc và hợp đồng không yêu cầu; nhưng cũng không để token hết hạn mở quyền vô hạn cho kết nối kéo dài.

Hết hạn token không tự động hủy một giao dịch đã được chấp nhận hoặc thu hồi dữ liệu đã trả về. Những hành vi đó cần được thiết kế riêng trong nghiệp vụ.

## 8. Ví dụ chính sách thời gian

### 8.1. Ví dụ access token

Giả sử API đơn hàng dùng hợp đồng:

~~~yaml
token_time_policy:
  required_claims:
    - iat
    - exp
  not_before: optional
  max_lifetime_seconds: 600
  max_token_age_seconds: 600
  clock_skew_seconds: 30
  reject_future_iat_beyond_skew: true
  reject_expired_at_or_after_exp: true
~~~

Đây là chính sách minh họa, không phải cấu hình chuẩn. Nếu token có **iat = 10:00:00** và **exp = 10:10:00**, lifetime là 600 giây. API kiểm tra token lúc 10:08:00 thì tuổi token là 480 giây; nếu mọi điều kiện khác hợp lệ, token còn trong lifetime và freshness window. Nếu kiểm tra lúc 10:10:00 thì token hết hạn theo quy tắc cơ bản.

### 8.2. Ví dụ kiểm tra mốc thời gian

Giả sử thời điểm kiểm tra theo đồng hồ của bên nhận là 10:05:00, leeway là 30 giây:

| Token | iat | nbf | exp | Kết quả thời gian |
|---|---|---|---|---|
| A | 10:00:00 | 10:00:00 | 10:10:00 | Hợp lệ về thời gian |
| B | 10:06:00 | 10:06:00 | 10:15:00 | Chưa đến nbf; nằm ngoài leeway 30 giây, từ chối |
| C | 09:50:00 | 09:50:00 | 10:04:00 | Đã hết hạn quá leeway, từ chối |
| D | 10:05:20 | 10:05:20 | 10:15:00 | iat/nbf ở tương lai 20 giây; có thể chấp nhận theo leeway nếu profile và chính sách cho phép |
| E | 09:00:00 | 09:00:00 | 11:00:00 | Còn exp nhưng có thể bị từ chối do max lifetime hoặc max token age |

Bảng chỉ minh họa logic thời gian. Kết quả cuối cùng vẫn phụ thuộc cách profile và thư viện áp dụng leeway, claim bắt buộc, issuer, audience, chữ ký và quyền.

### 8.3. Pseudocode xác minh thời gian

~~~text
validateTime(claims, policy, now):
    require claims.exp nếu policy yêu cầu
    require claims.iat nếu policy yêu cầu
    require claims.nbf nếu policy yêu cầu

    reject nếu claim thời gian không phải NumericDate hợp lệ
    reject nếu giá trị nằm ngoài phạm vi thời gian cho phép

    S = policy.clockSkew

    reject nếu exp và iat mâu thuẫn
    reject nếu nbf và exp mâu thuẫn
    reject nếu iat > now + S
    reject nếu nbf > now + S
    reject nếu now >= exp + S

    nếu policy.maxLifetime tồn tại:
        reject nếu exp - iat > policy.maxLifetime

    nếu policy.maxTokenAge tồn tại:
        reject nếu now - iat > policy.maxTokenAge + S

    ACCEPT về mặt thời gian
~~~

Pseudocode mô tả một cách áp dụng leeway phổ biến, không phải thuật toán bắt buộc cho mọi thư viện. Cần xác minh semantics thực tế của thư viện đang dùng, nhất là điều kiện biên **exp**, cách xử lý phần thập phân và dung sai với **iat/nbf**. Không sao chép pseudocode nếu nó mâu thuẫn với profile hoặc chính sách đã chọn.

## 9. Kiểm thử thời gian và vận hành

### 9.1. Các ca kiểm thử tối thiểu

| Ca | Điều kiện | Kết quả mong đợi |
|---|---|---|
| T1 | now nhỏ hơn exp rõ ràng; nbf đã đến | Chấp nhận về mặt thời gian |
| T2 | now bằng exp | Từ chối |
| T3 | now lớn hơn exp | Từ chối |
| T4 | now nhỏ hơn nbf ngoài leeway | Từ chối |
| T5 | nbf nằm trong leeway | Kết quả theo chính sách leeway đã công bố |
| T6 | exp vừa qua trong leeway | Kết quả theo chính sách leeway đã công bố |
| T7 | iat vượt tương lai ngoài leeway | Từ chối |
| T8 | exp - iat vượt max lifetime | Từ chối |
| T9 | now - iat vượt max token age | Từ chối |
| T10 | Timestamp được gửi theo mili giây | Từ chối theo schema/phạm vi, không tự đổi đơn vị |
| T11 | Đồng hồ node nhanh/chậm hơn ngưỡng | Cảnh báo vận hành; xác minh theo chính sách đã định |
| T12 | Token còn hạn nhưng jti đã bị thu hồi/đã dùng | Từ chối theo trạng thái |
| T13 | Yêu cầu bắt đầu trước exp, hoàn tất sau exp | Xử lý theo chính sách yêu cầu dài đã định |
| T14 | Cache trạng thái hợp lệ có TTL vượt exp còn lại | TTL phải bị giới hạn; không chấp nhận quá exp |

### 9.2. Kiểm thử đồng hồ lệch

Không chỉ kiểm thử bằng cách chờ token thật hết hạn. Có thể dùng đồng hồ giả lập hoặc clock injection trong môi trường thử nghiệm để kiểm tra:

- Đồng hồ issuer và API bằng nhau.
- API nhanh hơn issuer một lượng nhỏ nằm trong leeway.
- API chậm hơn issuer một lượng nhỏ nằm trong leeway.
- Độ lệch vượt leeway theo cả hai hướng.
- Đồng hồ nhảy lùi hoặc nhảy tiến trong lúc xử lý.
- Cache hoặc nhiều node có thời điểm hiện tại khác nhau.

Không điều chỉnh đồng hồ production tùy tiện để thử nghiệm. Việc kiểm thử cần cô lập trong môi trường phù hợp.

### 9.3. Giám sát

Nên theo dõi:

- Clock offset giữa các node và trạng thái đồng bộ NTP.
- Tỷ lệ token bị từ chối do **exp**, **nbf**, **iat** hoặc max-age.
- Tỷ lệ token bị từ chối do sai đơn vị hoặc giá trị thời gian bất thường.
- Lỗi refresh, introspection, denylist và cập nhật trạng thái thu hồi.
- Số lượng token được phát hành với lifetime vượt policy (nếu có thể phát hiện ở issuer).

Log phục vụ điều tra nên ghi mã lỗi, contract ID, issuer đã được xác minh và thời điểm xử lý cần thiết; tránh ghi nguyên token hoặc dữ liệu nhạy cảm. Cần phân biệt lỗi clock skew bình thường với token bị phát hành sai hoặc có dấu hiệu lạm dụng.

## 10. Checklist chính sách thời gian

**Phát hành**

- [ ] Token profile xác định claim thời gian bắt buộc và tùy chọn.
- [ ] Issuer dùng NumericDate theo giây, nhất quán với RFC và profile.
- [ ] Lifetime tối đa được quy định theo từng loại token.
- [ ] iat, nbf và exp có quan hệ hợp lý; không phát hành token đã hết hạn hoặc có mốc mâu thuẫn.

**Xác minh**

- [ ] Kiểm tra exp theo điều kiện hết hạn chính xác, bao gồm thời điểm bằng exp.
- [ ] Kiểm tra nbf và iat theo chính sách tương ứng.
- [ ] Có giới hạn max lifetime và max token age khi rủi ro yêu cầu.
- [ ] Leeway nhỏ, có căn cứ và semantics nhất quán giữa các thành phần.
- [ ] Không nhầm iat với auth_time hoặc dùng iat để chứng minh xác thực mới khi không đủ cơ sở.

**Hạ tầng và vòng đời**

- [ ] Đồng hồ các node được đồng bộ và giám sát.
- [ ] Có quy tắc cho token bị thu hồi, token một lần và refresh token rotation.
- [ ] Cache không kéo dài trạng thái hợp lệ quá exp hoặc quá chính sách thu hồi.
- [ ] Có chính sách cho kết nối dài và yêu cầu bắt đầu trước khi token hết hạn.
- [ ] Có kiểm thử biên thời gian, clock skew, sai đơn vị và sự cố đồng bộ.

**Điều cần nhớ:** **exp** đặt hạn cuối; **nbf** đặt thời điểm bắt đầu; **iat** ghi thời điểm phát hành và hỗ trợ đo độ mới. Lifetime giới hạn token có thể sống bao lâu, freshness giới hạn token được phát hành cách đây bao lâu, còn leeway chỉ bù một sai lệch đồng hồ nhỏ. Không cơ chế nào trong số đó tự thay thế kiểm tra thu hồi hoặc quyền nghiệp vụ.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Registered claims **iat**, **nbf**, **exp**, NumericDate và quy tắc thời gian.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Hồ sơ access token và yêu cầu claim.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, **auth_time** và yêu cầu xác thực mới.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Kiểm tra trạng thái token qua authorization server.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Access token, refresh token và vòng đời ủy quyền.
