# 11.9. Claims auth_time, acr và amr trong yêu cầu xác thực nâng cao

## 1. Vì sao ID Token hợp lệ vẫn có thể chưa đủ cho thao tác nhạy cảm?

Trong OpenID Connect (OIDC), một ứng dụng **Relying Party (RP)** hoặc **OIDC Client** có thể đăng nhập người dùng qua OpenID Provider (OP), nhận ID Token rồi xây dựng phiên đăng nhập ở Spring Security. Với đa số màn hình thông thường, xác minh chữ ký, issuer, audience, expiration, nonce (khi có) và các điều kiện OIDC khác là nền tảng để tin danh tính người dùng.

Nhưng khi người dùng thực hiện thao tác nhạy cảm, câu hỏi thường thay đổi:

- Người dùng **đã xác thực lần gần nhất khi nào**? Có phải xác thực từ nhiều giờ trước, dù token vừa được phát hành?
- **Mức bảo đảm xác thực** của lần đó có đáp ứng yêu cầu nghiệp vụ hay không?
- **Những phương thức xác thực nào** đã thực sự được nhà cung cấp sử dụng, chẳng hạn mật khẩu, OTP hoặc khóa bảo mật?
- Nếu chưa đủ, ứng dụng cần yêu cầu **xác thực lại (reauthentication)** hoặc **nâng mức xác thực (step-up authentication)** như thế nào?

OIDC cung cấp ba claim đặc biệt hữu ích:

| Claim trong ID Token | Kiểu dữ liệu | Câu hỏi được trả lời |
|---|---|---|
| **<code>auth_time</code>** | JSON number, Unix time tính bằng giây | Người dùng được OP xác thực vào lúc nào? |
| **<code>acr</code>** | JSON string | Phiên xác thực đã đáp ứng *Authentication Context Class* nào? |
| **<code>amr</code>** | JSON array of strings | OP sử dụng những *Authentication Methods* nào? |

Ba claim này có mục đích khác nhau. <code>auth_time</code> nói về **độ mới của lần xác thực**, <code>acr</code> nói về **lớp/mức bảo đảm theo chính sách của OP**, còn <code>amr</code> mô tả **các phương thức đã dùng**. Chúng bổ sung cho việc xác minh ID Token và authorization; không thay thế chữ ký, issuer, audience, scope hay quyền truy cập nghiệp vụ.

Ví dụ: người dùng đăng nhập SSO lúc 08:00 bằng mật khẩu, đến 14:00 mở trang chuyển tiền. OP có thể phát hành ID Token mới lúc 14:00 từ phiên SSO có sẵn mà không yêu cầu nhập lại yếu tố xác thực. <code>iat=14:00</code> không chứng minh người dùng vừa xác thực lúc 14:00; cần xét <code>auth_time</code> và chính sách xác thực đã hoàn tất.

## 2. Vị trí các claim trong ID Token

Một payload ID Token minh họa:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "sub": "248289761001",
  "aud": "finance-web",
  "iat": 1794808800,
  "exp": 1794812400,
  "auth_time": 1794808500,
  "acr": "urn:company:assurance:high",
  "amr": ["pwd", "otp"],
  "nonce": "random-nonce-from-client"
}
~~~

Ví dụ này chỉ trình bày payload để học; ID Token thực tế là token được OP ký (hoặc xử lý theo thuật toán thỏa thuận), và mọi claim chỉ đáng tin **sau khi Client hoàn tất ID Token validation**.

Trong ví dụ:

- <code>iat</code> là thời điểm **phát hành ID Token**.
- <code>auth_time</code> là thời điểm **người dùng được xác thực tại OP**.
- <code>acr</code> là mã lớp bảo đảm theo hợp đồng của OP <code>company</code>.
- <code>amr</code> cho biết OP báo cáo phương thức <code>pwd</code> (password) và <code>otp</code> (one-time password).

Các giá trị <code>urn:company:assurance:high</code> là ví dụ cho một chính sách **do tổ chức định nghĩa**, không phải mã ACR phổ quát của mọi Identity Provider. Tập ACR thực tế, ý nghĩa từng giá trị và cơ chế kích hoạt MFA/step-up phải được thống nhất với OP.

### 2.1. Những claim phải phân biệt

| Claim/thông tin | Mục đích | Không nên suy diễn |
|---|---|---|
| <code>exp</code> | Khi nào ID Token hết hiệu lực | Token còn hạn không đồng nghĩa xác thực còn mới |
| <code>iat</code> | Token được phát hành khi nào | Token mới không đồng nghĩa vừa nhập mật khẩu/MFA |
| <code>auth_time</code> | Lần xác thực người dùng xảy ra khi nào | Không cho biết phương thức/mức bảo đảm |
| <code>acr</code> | Lớp ngữ cảnh xác thực OP khẳng định đạt được | Không tự suy ra một tập phương thức cụ thể nếu chưa có hợp đồng |
| <code>amr</code> | Những phương thức xác thực được OP khai báo | Không tự suy ra chính sách ACR, độ mới hay phishing resistance |
| <code>nonce</code> | Liên kết ID Token với authorization request và chống replay theo OIDC | Không phải thời điểm xác thực hay mức MFA |
| <code>state</code> | Correlate authorization response/callback với request ban đầu | Không phải claim của ID Token dùng đánh giá assurance |
| Scope/role | Quyền hoặc phạm vi ứng dụng yêu cầu/cấp | Không chứng minh cách người dùng vừa được xác thực |

## 3. auth_time: thời điểm người dùng thực sự xác thực

### 3.1. Ý nghĩa và kiểu dữ liệu

Theo OpenID Connect Core 1.0, <code>auth_time</code> là thời điểm End-User authentication đã xảy ra. Giá trị là **JSON number** biểu diễn số **giây** kể từ <code>1970-01-01T00:00:00Z</code> (Unix time).

Ví dụ:

~~~json
{
  "auth_time": 1794808500
}
~~~

Nếu chuyển số đó thành thời điểm trong Java, dùng <code>Instant.ofEpochSecond(...)</code>, **không dùng milliseconds**. Dùng nhầm <code>ofEpochMilli</code> sẽ làm thời điểm sai nghiêm trọng.

OIDC quy định:

- Khi authorization request có **<code>max_age</code>**, ID Token **phải chứa <code>auth_time</code>**.
- Khi <code>auth_time</code> được yêu cầu dưới dạng **Essential Claim**, ID Token **phải chứa <code>auth_time</code>**.
- Trong các trường hợp khác, <code>auth_time</code> là claim **tùy chọn**, OP có thể không trả về.

Điều này có nghĩa một ID Token hoàn toàn hợp lệ cho đăng nhập thông thường vẫn có thể không chứa <code>auth_time</code>. Với API nhạy cảm yêu cầu xác thực gần đây, **thiếu <code>auth_time</code> không được mặc định hiểu là “vừa xác thực”**.

### 3.2. Kiểm tra độ mới

Giả sử nghiệp vụ yêu cầu người dùng đã xác thực trong vòng **5 phút**. Khi nhận ID Token hợp lệ, ứng dụng tính:

~~~text
age = now - auth_time

Cho phép theo yêu cầu freshness nếu:
    auth_time hiện diện, có kiểu hợp lệ
    auth_time không nằm quá xa trong tương lai
    age <= 5 phút (+ clock skew nhỏ, có kiểm soát)
~~~

Ví dụ:

| Thời điểm kiểm tra | <code>auth_time</code> | Độ tuổi xác thực | Quyết định với ngưỡng 5 phút |
|---|---|---|---|
| 10:04 | 10:00 | 4 phút | Đạt freshness |
| 10:06 | 10:00 | 6 phút | Không đạt |
| 10:06 | Vắng mặt | Không xác định | Không đạt cho thao tác yêu cầu freshness |
| 10:06 | 10:30 | Nằm xa trong tương lai | Không đạt; xem lại clock/OP |

Các thời điểm minh họa phải được hiểu theo cùng một múi giờ; khi lập trình nên chuyển về <code>Instant</code> UTC để tránh lỗi múi giờ.

### 3.3. auth_time không phải iat

Đây là nhầm lẫn quan trọng nhất khi xây step-up:

~~~text
08:00  Người dùng đăng nhập vào OP bằng mật khẩu
14:00  Ứng dụng khởi tạo OIDC flow mới
14:00  OP nhận ra SSO cookie, phát hành ID Token mới

ID Token mới:
    iat       ≈ 14:00
    auth_time ≈ 08:00
~~~

Nếu ứng dụng chỉ kiểm tra <code>iat</code>, người dùng có thể vượt điều kiện “vừa xác thực” dù OP không yêu cầu nhập lại bất kỳ yếu tố nào. Chính sách phải dựa vào <code>auth_time</code>.

### 3.4. max_age yêu cầu xác thực còn mới

Authorization request có thể truyền:

~~~text
max_age=300
~~~

<code>max_age</code> là **số giây tối đa cho phép trôi qua kể từ khi OP chủ động xác thực End-User**. Nếu lần xác thực gần nhất quá cũ, OP phải cố gắng xác thực lại người dùng theo yêu cầu giao thức.

Khi cần bắt đầu một lượt xác thực mới ngay:

~~~text
max_age=0
~~~

Giá trị <code>0</code> yêu cầu xác thực lại thay vì chỉ dùng SSO hiện có. Nhưng Client vẫn cần **đọc và kiểm tra <code>auth_time</code> trong ID Token cuối cùng**; không được cho rằng chỉ vì đã gửi <code>max_age</code> thì OP chắc chắn hoàn thành theo chính sách.

Tham số <code>prompt=login</code> có thể được OP dùng để yêu cầu hiển thị lại bước đăng nhập, nhưng <code>max_age</code> có ràng buộc độ mới và yêu cầu claim <code>auth_time</code> rõ ràng hơn. Không thay kiểm tra <code>auth_time</code> bằng việc quan sát giao diện hoặc chỉ gửi <code>prompt=login</code>.

## 4. acr: Authentication Context Class Reference

### 4.1. ACR mô tả lớp bảo đảm nào?

<code>acr</code> là một **chuỗi** nhận dạng Authentication Context Class mà OP xác nhận lần xác thực đã đáp ứng. Ví dụ:

~~~json
{
  "acr": "urn:company:assurance:high"
}
~~~

ACR thường biểu diễn một **chính sách xác thực**: cần yếu tố nào, cách đăng ký thiết bị, khả năng chống phishing, thời hạn phiên, điều kiện xác minh danh tính và những ràng buộc khác. ACR **không đơn giản là “số lượng yếu tố”**.

Tùy nhà cung cấp và tổ chức, có thể có các giá trị:

~~~text
urn:company:assurance:basic
urn:company:assurance:high
urn:company:assurance:phishing-resistant
~~~

Đây là ví dụ tự định nghĩa; **không có một trật tự “basic < high < phishing-resistant” được OIDC mặc định hiểu**. Ứng dụng phải có policy/allowlist riêng và hợp đồng rõ ràng với OP. Không so sánh <code>acr</code> theo thứ tự từ điển, không tách phần cuối URI rồi suy ra mức bảo đảm.

### 4.2. acr_values: yêu cầu mức xác thực theo thứ tự ưu tiên

OIDC hỗ trợ tham số authorization request:

~~~text
acr_values=urn:company:assurance:phishing-resistant urn:company:assurance:high
~~~

<code>acr_values</code> chứa một danh sách giá trị ACR **ngăn cách bằng dấu cách**, được sắp theo thứ tự ưu tiên của Client. Trong URL thật, dấu cách và ký tự đặc biệt phải được percent-encode bởi thư viện HTTP.

Đây là cách Client nêu **giá trị ACR mong muốn**, nhưng theo OIDC Core việc chỉ dùng <code>acr_values</code> yêu cầu <code>acr</code> theo dạng **Voluntary Claim**. OP có thể không đạt giá trị mong muốn và có thể trả ACR khác hoặc không trả claim, tùy khả năng và quy định.

Vì vậy sau khi nhận ID Token, ứng dụng vẫn phải:

1. Xác minh ID Token chuẩn.
2. Đọc <code>acr</code>.
3. Đối chiếu với **tập ACR được phép** cho thao tác.
4. Từ chối thao tác hoặc yêu cầu step-up tiếp nếu kết quả chưa đạt.

### 4.3. Yêu cầu acr như Essential Claim bằng claims parameter

OIDC hỗ trợ tham số <code>claims</code>, truyền một JSON object yêu cầu claim ở <code>id_token</code> hoặc <code>userinfo</code>. Khi OP hỗ trợ <code>claims</code>, Client có thể yêu cầu ACR cụ thể là **Essential Claim**:

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:company:assurance:phishing-resistant"
      ]
    },
    "auth_time": {
      "essential": true
    }
  }
}
~~~

Giá trị JSON này phải được URL-encode khi đặt vào tham số <code>claims</code> của authorization request. Không gửi nguyên JSON vào URL mà bỏ qua mã hóa.

Theo OIDC Core, khi OP **hỗ trợ claims parameter** và <code>acr</code> được yêu cầu là Essential với <code>value</code>/<code>values</code>, OP phải trả một giá trị <code>acr</code> thuộc tập đã yêu cầu; nếu không thể đáp ứng thì phải coi là thất bại xác thực. OP có thể yêu cầu người dùng xác thực lại hoặc thêm yếu tố để đạt yêu cầu.

Điều kiện “OP hỗ trợ” rất quan trọng. Không phải mọi nhà cung cấp triển khai <code>claims</code>, <code>acr</code> hay step-up cùng cách. Ngay cả khi OP tuyên bố đáp ứng, **RP vẫn phải xác minh giá trị <code>acr</code> nhận được** và áp dụng policy nội bộ.

> **Lưu ý giao thức:** Nếu vừa gửi <code>acr_values</code> vừa gửi yêu cầu <code>acr</code> riêng với <code>value</code>/<code>values</code> trong <code>claims</code>, OIDC Core quy định hành vi kết hợp là **không xác định**. Nên chọn một cơ chế rõ ràng cho mỗi yêu cầu và tuân theo tài liệu provider.

### 4.4. ACR không tự động bằng quyền truy cập

Một ID Token có ACR mạnh chỉ nói lần xác thực thỏa một context class. Nó không chứng minh người dùng có role quản trị, quyền duyệt thanh toán hay thuộc nhóm dữ liệu được phép đọc.

Ví dụ thao tác duyệt khoản thanh toán lớn cần **đồng thời**:

~~~text
Người dùng có quyền APPROVE_PAYMENT
AND ID Token hợp lệ
AND acr thuộc tập được phép cho thanh toán
AND auth_time đủ mới
AND yêu cầu giao dịch được đối chiếu đúng người dùng và phiên
~~~

Không dùng <code>acr</code> để thay thế hệ thống authorization nghiệp vụ.

## 5. amr: Authentication Methods References

### 5.1. Ý nghĩa và ví dụ

<code>amr</code> là **mảng các chuỗi** mà OP dùng để ghi nhận phương thức xác thực đã sử dụng:

~~~json
{
  "amr": ["pwd", "otp"]
}
~~~

Ví dụ các giá trị thường gặp:

| Giá trị AMR | Ý nghĩa khái quát |
|---|---|
| <code>pwd</code> | Password |
| <code>otp</code> | One-time password |
| <code>mfa</code> | Multi-factor authentication, nếu OP công bố theo quy ước tương ứng |
| <code>hwk</code> | Proof-of-possession của khóa phần cứng |
| <code>swk</code> | Proof-of-possession của khóa phần mềm |
| <code>fpt</code> | Fingerprint biometric |

Các mã trong ví dụ xuất hiện trong hệ sinh thái Authentication Method Reference; danh sách và ý nghĩa chuẩn hóa được quản lý qua **RFC 8176 / IANA Authentication Method Reference Values Registry**. Provider còn có thể dùng giá trị riêng, nhưng các bên phải thống nhất ý nghĩa của giá trị không được đăng ký.

<code>amr</code> **không phải một chuỗi chứa danh sách phân cách bằng dấu phẩy**, cũng không phải số lượng phương thức. Theo OIDC, claim là JSON **array of case-sensitive strings**, ví dụ <code>["pwd","otp"]</code>.

### 5.2. Những gì amr không chứng minh

Nhìn thấy <code>["pwd", "otp"]</code> không tự động đủ để kết luận authentication đáp ứng mọi chính sách “MFA cấp cao”:

- OTP có thể là ứng dụng xác thực, SMS hoặc dạng khác với mức chống phishing khác nhau.
- Không rõ thứ tự, yếu tố nào được dùng cho phiên hiện tại nếu chưa có hợp đồng cụ thể của OP.
- Provider có thể biểu diễn MFA bằng <code>"mfa"</code> hoặc chỉ liệt kê từng phương thức, tùy implementation.
- Một OP có thể không phát <code>amr</code> dù đã thực hiện MFA.
- <code>amr</code> không có timestamp riêng; độ mới vẫn cần <code>auth_time</code>.
- Một phương thức có tên “hardware” không tự động chứng minh phishing resistance hoặc device binding ở mức mà nghiệp vụ yêu cầu.

Nếu chính sách cần “xác thực chống phishing”, cách đáng tin cậy là **một ACR đã được OP cam kết rõ về assurance**, kết hợp yêu cầu thời gian và những ràng buộc khác; <code>amr</code> có thể làm tín hiệu bổ sung khi hợp đồng OP có quy định.

### 5.3. Có thể dùng amr trong quyết định quyền không?

Có, nhưng **chỉ khi đã có hợp đồng rõ ràng với OP** về cách phát AMR và ý nghĩa từng giá trị. Ví dụ một hệ thống nội bộ có thể yêu cầu:

~~~text
acr = urn:company:assurance:high
AND auth_time trong vòng 5 phút
AND amr chứa "mfa" theo hợp đồng với OP
~~~

Nếu OP không cam kết luôn gửi <code>amr</code>, chính sách này có thể khiến người dùng đã MFA vẫn bị từ chối. Nếu OP gửi <code>mfa</code> nhưng nội dung context không đáp ứng yêu cầu chống phishing, việc chỉ kiểm tra <code>mfa</code> có thể quá dễ dãi.

Với thao tác nhạy cảm, **thiếu claim mà chính sách yêu cầu** nên dẫn đến **chưa đủ điều kiện**, không mặc nhiên chấp nhận.

## 6. So sánh auth_time, acr, amr trong các kịch bản thực tế

| Kịch bản | <code>auth_time</code> | <code>acr</code> | <code>amr</code> | Kết luận |
|---|---|---|---|---|
| Người dùng đăng nhập bằng mật khẩu 4 giờ trước, OP phát ID Token mới qua SSO | 4 giờ trước | Basic | <code>["pwd"]</code> | Có thể dùng ứng dụng thông thường; không đạt yêu cầu “mới trong 5 phút” |
| Người dùng vừa xác thực lại bằng mật khẩu | Hiện tại | Basic | <code>["pwd"]</code> | Đạt freshness nhưng chưa chắc đạt yêu cầu assurance cao |
| Người dùng vừa hoàn thành MFA theo policy OP | Hiện tại | High | <code>["pwd","otp"]</code> | Có thể đạt chính sách cần High + freshness |
| OP vừa cấp token nhưng không có <code>auth_time</code> | Không có | High | <code>["mfa"]</code> | Không đủ chứng cứ về độ mới |
| OP trả ACR thấp hơn yêu cầu | Hiện tại | Basic | <code>["pwd","otp"]</code> | Không đạt policy dựa trên ACR; cần kiểm tra hợp đồng/OP |
| ACR cao nhưng vượt thời gian cho phép | 1 giờ trước | High | <code>["mfa"]</code> | Không đạt yêu cầu xác thực gần đây |

Kết luận từ bảng không phải quy tắc chung cho mọi tổ chức: giá trị ACR cụ thể, thời hạn và loại phương thức được chấp nhận phải do **policy nghiệp vụ và hợp đồng tích hợp OP** xác định.

## 7. Step-up authentication: từ yêu cầu ban đầu đến xác minh kết quả

**Step-up authentication** là việc yêu cầu người dùng thực hiện thêm xác thực hoặc nâng mức assurance **khi một hành động cụ thể cần mức cao hơn lần đăng nhập hiện có**.

Ví dụ ứng dụng quản trị:

1. Người dùng đăng nhập qua OIDC để xem danh sách báo cáo.
2. Khi bấm “Xuất dữ liệu nhạy cảm”, ứng dụng đánh giá ID Token hiện tại.
3. <code>auth_time</code> cũ hoặc <code>acr</code> không đạt, nên ứng dụng tạo **authorization request mới** tới OP với các tham số yêu cầu độ mới và assurance.
4. OP thực hiện reauthentication/MFA theo policy.
5. OP trả authorization code; Client đổi token và xác minh ID Token mới.
6. **Chỉ sau khi kiểm tra <code>auth_time</code> và <code>acr</code> của ID Token mới**, ứng dụng cho phép bước tiếp theo theo quyền nghiệp vụ.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Người dùng
    participant B as Browser
    participant RP as Spring Security OIDC Client
    participant OP as OpenID Provider
    U->>B: Yêu cầu thao tác nhạy cảm
    B->>RP: GET /payments/approve
    RP->>RP: Kiểm quyền + auth_time/acr của ID Token hiện tại
    alt Chưa đạt assurance/freshness
        RP-->>B: Yêu cầu bắt đầu OIDC step-up
        B->>RP: GET /oauth2/authorization/company?stepup=true
        RP->>RP: Tạo state, nonce, max_age và claims cần thiết
        RP-->>B: 302 tới authorization endpoint
        B->>OP: Authorization request có yêu cầu step-up
        OP->>U: Reauthentication / thêm yếu tố xác thực
        OP-->>B: Callback với code và state
        B->>RP: GET /login/oauth2/code/company?code=...&state=...
        RP->>OP: Token request
        OP-->>RP: Token response gồm ID Token
        RP->>RP: Xác minh token, auth_time, acr, danh tính
    end
    RP-->>B: Cho phép tiếp tục nếu policy và quyền nghiệp vụ đạt
~~~

Đây là mô hình khái niệm. Redirect sau step-up và việc tiếp tục thao tác cần được thiết kế rõ: không tự động thực hiện một hành động thay đổi dữ liệu chỉ vì người dùng vừa quay về callback. Với thanh toán hoặc thay đổi thông tin bảo mật, hãy yêu cầu xác nhận giao dịch theo luồng nghiệp vụ và chống CSRF phù hợp.

### 7.1. Truyền max_age, prompt và acr_values

Một authorization request có thể yêu cầu:

~~~text
response_type=code
client_id=finance-web
scope=openid profile
redirect_uri=https://app.example.org/login/oauth2/code/company
state=RANDOM_STATE
nonce=RANDOM_NONCE
max_age=300
acr_values=urn:company:assurance:high
~~~

Đây là biểu diễn **trước khi URL-encode**, mỗi tham số chỉ được hiển thị trên một dòng cho dễ học. Request thực tế đi qua HTTPS và các giá trị URL phải được mã hóa phù hợp.

Với yêu cầu assurance có tính bắt buộc, có thể dùng <code>claims</code> Essential thay cho <code>acr_values</code>. **Không gửi cả hai cách yêu cầu ACR có tập giá trị cụ thể trong cùng một request** nếu muốn hành vi xác định theo OIDC Core.

Nếu cần xác thực lại ngay lúc thao tác:

~~~text
max_age=0
~~~

Nếu chỉ muốn OP hiển thị lại bước đăng nhập:

~~~text
prompt=login
~~~

Trong cả hai trường hợp, RP phải kiểm tra kết quả cuối cùng, không suy đoán từ việc trình duyệt đã hiển thị một màn hình nào đó.

### 7.2. Mẫu yêu cầu Essential Claims

Ví dụ JSON cho <code>claims</code>:

~~~json
{
  "id_token": {
    "auth_time": {
      "essential": true
    },
    "acr": {
      "essential": true,
      "values": [
        "urn:company:assurance:high"
      ]
    }
  }
}
~~~

Kết hợp <code>max_age=0</code> để yêu cầu reauthentication ngay và <code>claims</code> để OP hỗ trợ bắt buộc có <code>auth_time</code> cùng ACR mong muốn. Việc OP hỗ trợ claims parameter và ý nghĩa ACR phải được kiểm tra trong tài liệu/metadata của nhà cung cấp trước khi phụ thuộc vào tính năng này.

## 8. Cấu hình Spring Security OAuth 2.0/OIDC Client cơ bản

Ví dụ một ứng dụng Spring Boot 3, Spring Security 6, sử dụng Servlet OAuth2 Login với issuer được cấu hình sẵn:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: finance-web
            client-secret: replace-with-secret-from-secure-storage
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Giá trị client secret là placeholder; sản phẩm thật phải cấp từ secret manager/biến môi trường, không commit bí mật vào repository. Issuer cũng là ví dụ và phải thay bằng issuer chính thức của OP.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Khi người dùng đăng nhập:

~~~text
GET /oauth2/authorization/company
~~~

Spring Security sử dụng ClientRegistration để tạo authorization request, lưu state, nhận callback tại <code>/login/oauth2/code/company</code> và xây dựng <code>OidcUser</code> từ ID Token đã được xử lý theo OIDC.

**Điểm quan trọng:** Cấu hình mặc định xác thực ID Token theo giao thức, nhưng ứng dụng **không được mặc nhiên coi một ACR cụ thể hoặc độ mới 5 phút đã được Spring Security kiểm tra theo yêu cầu nghiệp vụ**. Phần policy phải do ứng dụng định nghĩa.

## 9. Đọc auth_time, acr và amr từ OidcUser

Trong Spring Security, <code>OidcUser.getIdToken()</code> trả về <code>OidcIdToken</code>, có các accessor chuẩn qua <code>IdTokenClaimAccessor</code>:

- <code>getAuthenticatedAt()</code>: đọc <code>auth_time</code> thành <code>Instant</code>.
- <code>getAuthenticationContextClass()</code>: đọc <code>acr</code> thành chuỗi.
- <code>getAuthenticationMethods()</code>: đọc <code>amr</code> thành danh sách chuỗi.

Ví dụ controller chỉ trả trạng thái để minh họa:

~~~java
package example.web;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthenticationInfoController {

    @GetMapping("/me/assurance")
    public Map<String, Object> assurance(
            @AuthenticationPrincipal OidcUser user) {
        Instant authTime = user.getIdToken().getAuthenticatedAt();
        String acr = user.getIdToken().getAuthenticationContextClass();
        List<String> amr = user.getIdToken().getAuthenticationMethods();

        return Map.of(
            "hasAuthTime", authTime != null,
            "hasAcr", acr != null,
            "reportedAmrCount", amr == null ? 0 : amr.size()
        );
    }
}
~~~

Đoạn ví dụ trên tránh trả nguyên ID Token hoặc giá trị nhạy cảm. Với ứng dụng có nhiều loại authentication (không phải mọi principal đều là <code>OidcUser</code>), controller cần bảo đảm endpoint chỉ dành cho OIDC user hoặc xử lý trường hợp principal khác.

Các accessor phụ thuộc vào version Spring Security cụ thể; các tên trên có trong <code>IdTokenClaimAccessor</code> của Spring Security 5.8/6.x. Chú ý tên method là **<code>getAuthenticatedAt()</code>**, không phải <code>getAuthenticationTime()</code>.

## 10. Viết policy xác thực nâng cao bằng Java

Giả sử một endpoint xử lý thao tác nhạy cảm yêu cầu đồng thời:

1. Principal là người dùng đã đăng nhập bằng OIDC.
2. <code>auth_time</code> có mặt và không quá **5 phút**.
3. <code>acr</code> đúng một giá trị high-assurance đã được OP cam kết.
4. <code>amr</code> có thể được kiểm tra bổ sung **chỉ nếu hợp đồng với OP yêu cầu**.

Tạo policy độc lập để kiểm tra trên server:

~~~java
package example.security;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component("assurancePolicy")
public final class AssurancePolicy {
    private static final Duration MAX_AUTH_AGE = Duration.ofMinutes(5);
    private static final Duration CLOCK_SKEW = Duration.ofSeconds(30);
    private static final String REQUIRED_ACR =
        "urn:company:assurance:high";

    private final Clock clock;

    public AssurancePolicy() {
        this.clock = Clock.systemUTC();
    }

    public boolean isSatisfied(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        if (!(authentication.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        OidcIdToken idToken = user.getIdToken();
        if (idToken == null) {
            return false;
        }

        Instant authenticatedAt = idToken.getAuthenticatedAt();
        String acr = idToken.getAuthenticationContextClass();
        if (authenticatedAt == null || !REQUIRED_ACR.equals(acr)) {
            return false;
        }

        Instant now = clock.instant();
        if (authenticatedAt.isAfter(now.plus(CLOCK_SKEW))) {
            return false; // auth_time bất thường trong tương lai
        }

        // Không chấp nhận thời điểm xác thực quá ngưỡng cho phép.
        return !now.isAfter(
            authenticatedAt.plus(MAX_AUTH_AGE).plus(CLOCK_SKEW));
    }
}
~~~

Đây là một **policy minh họa**. Với thao tác đặc biệt nhạy cảm, tổ chức có thể quyết định không cộng clock skew vào độ tuổi tối đa hoặc cần ngưỡng chặt hơn. Nên inject <code>Clock</code> qua bean nếu cần kiểm thử điều kiện thời gian; ví dụ dùng <code>Clock.systemUTC()</code> để trình bày gọn.

Chính sách cũng có thể yêu cầu thêm <code>amr</code>, nhưng chỉ khi OP cam kết ý nghĩa và cách phát claim. Ví dụ:

~~~java
var methods = idToken.getAuthenticationMethods();
boolean hasOtp =
    methods != null && methods.contains("otp");
~~~

Không thay điều kiện <code>REQUIRED_ACR.equals(acr)</code> bằng <code>methods.contains("otp")</code> nếu chính sách yêu cầu assurance cụ thể. Một OTP qua kênh không an toàn và một phương thức chống phishing có thể có đặc tính rủi ro rất khác nhau.

### 10.1. Bảo vệ endpoint bằng method security

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Sau đó:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SensitiveOperationController {

    @PostMapping("/payments/approve")
    @PreAuthorize(
        "hasAuthority('PAYMENT_APPROVER') and " +
        "@assurancePolicy.isSatisfied(authentication)")
    public String approve() {
        // Thực tế: xác nhận giao dịch và gọi service nghiệp vụ an toàn.
        return "Approved";
    }
}
~~~

Ví dụ không triển khai persistence hay luồng chuyển tiền thật; nó thể hiện **hai điều kiện độc lập**: người dùng có quyền nghiệp vụ và ID Token hiện tại thỏa assurance/freshness. Quyền <code>PAYMENT_APPROVER</code> phải được cấp từ nguồn tin cậy theo chính sách ứng dụng; chỉ khai báo annotation không tạo ra quyền này.

Nếu người dùng đã đăng nhập nhưng policy chưa đạt, Spring Security có thể trả 403. Trong ứng dụng thực tế, UI/handler có thể đưa người dùng vào **quy trình step-up có kiểm soát**, sau đó yêu cầu họ xác nhận lại hành động. Tránh biến mọi lỗi 403 thành vòng lặp đăng nhập vô hạn.

### 10.2. Đừng dùng kiểm tra chỉ ở giao diện

Không chỉ dùng JavaScript để ẩn nút “Approve”. Một Client bị sửa hoặc request HTTP trực tiếp vẫn có thể gọi endpoint. Policy cần nằm ở backend, nơi đang giữ Authentication và ID Token đã được Spring Security xác minh.

Đối với transaction lớn, còn phải gắn bước xác thực lại với **đúng giao dịch** hoặc phiên thao tác; mới đáp ứng ACR và auth_time chưa chứng minh người dùng đồng ý với bất kỳ thay đổi dữ liệu nào do attacker chèn vào.

## 11. Thêm yêu cầu xác thực nâng cao vào authorization request

Spring Security cho phép tùy biến authorization request qua <code>DefaultOAuth2AuthorizationRequestResolver</code>. Ví dụ dưới đây minh họa cách yêu cầu mọi lượt đăng nhập đi qua resolver phải có:

- <code>max_age=300</code> để yêu cầu freshness tối đa 5 phút.
- <code>acr</code> là Essential Claim thuộc giá trị high đã thống nhất với OP.
- <code>auth_time</code> là Essential Claim trong ID Token.

### 11.1. Java configuration

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcAssuranceRequestConfig {

    private static final String ESSENTIAL_CLAIMS = """
        {
          "id_token": {
            "auth_time": {"essential": true},
            "acr": {
              "essential": true,
              "values": ["urn:company:assurance:high"]
            }
          }
        }
        """;

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations)
            throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            clientRegistrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
            builder.additionalParameters(parameters -> {
                parameters.put("max_age", "300");
                parameters.put("claims", ESSENTIAL_CLAIMS);
            }));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

Đoạn này là **một phương án cấu hình thay thế** cho <code>SecurityFilterChain</code> ở mục 8, không khai báo đồng thời hai bean có cùng phạm vi mà không chủ động thiết kế nhiều chain. Java text block yêu cầu Java 15+; ví dụ phù hợp Java 17 trong Spring Boot 3.

<code>DefaultOAuth2AuthorizationRequestResolver</code> vẫn dựng các tham số cơ bản như <code>state</code>, ClientRegistration, redirect URI và dữ liệu nội bộ cần thiết. Customizer chỉ bổ sung yêu cầu assurance vào <code>additionalParameters</code>; không tự tạo state tĩnh hay tự chuyển code verifier lên front channel.

**Lưu ý triển khai:** Cấu hình trên áp dụng yêu cầu high assurance cho **mọi authorization request đi qua resolver này**. Với step-up chỉ khi thực hiện thao tác nhạy cảm, hãy chọn áp dụng tham số theo flow/registration hoặc một resolver tùy biến có phân biệt request; không ép toàn bộ người dùng MFA lại ở mọi lần đăng nhập nếu chính sách nghiệp vụ không yêu cầu.

### 11.2. Không tự mất state, nonce hoặc PKCE

Nếu tự viết <code>OAuth2AuthorizationRequestResolver</code> để tạo authorization request mới từ đầu, rất dễ quên:

- <code>state</code> ngẫu nhiên và authorization request repository.
- <code>nonce</code> và correlation trong OIDC.
- PKCE <code>code_challenge</code>/<code>code_verifier</code> khi áp dụng.
- Redirect URI, registration ID, scopes và các thuộc tính framework dùng trong token exchange.

Nên **ủy quyền cho resolver mặc định** rồi thêm tham số một cách có kiểm soát. Nếu tạo builder mới từ request có sẵn, có thể dùng <code>OAuth2AuthorizationRequest.from(existing)</code> để giữ các thông tin cần thiết, rồi chỉ bổ sung những tham số được phép. Phải kiểm tra rằng customizer và các điểm mở rộng không vô tình xóa PKCE/nonce attributes mà Spring Security cần.

### 11.3. Thiết kế step-up riêng cho hành động nhạy cảm

Một ứng dụng có thể phân biệt:

~~~text
Đăng nhập thường:
    /oauth2/authorization/company
    → OIDC Authorization Code Flow thông thường

Yêu cầu step-up:
    /oauth2/authorization/company?stepup=true
    → authorization request có max_age và Essential Claims
~~~

<code>stepup=true</code> ở đây là **ví dụ dấu hiệu để resolver chọn thêm yêu cầu mạnh hơn**, không phải một token cấp quyền. Người dùng có thể tự yêu cầu step-up, nhưng **không được tự quyết định đã đạt step-up bằng tham số query**; backend phải dựa trên ID Token đã xác minh và policy.

Nếu hỗ trợ nhiều loại thao tác như đổi mật khẩu, cập nhật phương thức thanh toán, xuất dữ liệu, mỗi loại có thể có policy riêng. Không tự động lấy ACR từ tham số URL do browser gửi và tin đó là ngưỡng phải đạt: giá trị yêu cầu và tập ACR được chấp nhận phải đến từ cấu hình backend.

## 12. Validation: yêu cầu là một chuyện, kết quả là chuyện khác

Quá trình xử lý an toàn có hai pha độc lập:

1. **Request:** RP yêu cầu OP xác thực lại hoặc trả context phù hợp bằng <code>max_age</code>, <code>acr_values</code> hoặc <code>claims</code>.
2. **Response:** RP xác minh ID Token và tự kiểm tra <code>auth_time</code>, <code>acr</code> (và <code>amr</code> nếu chính sách thực sự phụ thuộc vào nó).

Ngay cả khi OP đã hỗ trợ yêu cầu Essential ACR, RP vẫn cần xác minh giá trị nhận được. Một implementation không tuân thủ chuẩn, proxy lỗi hoặc cấu hình tenant sai vẫn có thể tạo tình huống không đạt policy.

### 12.1. Validation nền tảng phải diễn ra trước

Để tin bất kỳ claim assurance nào, trước hết phải tin được ID Token:

| Điều kiện | Lý do |
|---|---|
| Chữ ký hợp lệ với key/algorithm của issuer tin cậy | Không chấp nhận token tự sửa nội dung |
| <code>iss</code> khớp issuer OP đã cấu hình | Không lấy claim assurance từ issuer khác |
| <code>aud</code> chứa Client ID phù hợp và kiểm tra <code>azp</code> khi áp dụng | Token được phát hành cho đúng Client |
| <code>exp</code>/<code>iat</code> hợp lệ theo chính sách thời gian | Không nhận token hết hạn hoặc thời điểm bất thường |
| <code>nonce</code> khớp request khi nonce được gửi | Liên kết ID Token với yêu cầu xác thực |
| Callback <code>state</code> hợp lệ | Liên kết authorization response với yêu cầu ban đầu |

Trong Spring Security OAuth2 Login/OIDC, framework thực hiện phần lớn validation giao thức. Ứng dụng phải duy trì cấu hình issuer, ClientRegistration, token processing và những extension phù hợp. **Không bỏ qua validation nền tảng để tiện đọc acr/amr.**

### 12.2. Đánh giá từng claim theo policy

Quy trình policy thường là:

~~~text
if principal không phải OidcUser:
    deny

if ID Token chưa được xác minh theo OIDC:
    deny

if thao tác yêu cầu xác thực gần đây:
    require auth_time hiện diện và trong ngưỡng

if thao tác yêu cầu ACR:
    require acr thuộc tập cho phép theo hợp đồng OP

if nghiệp vụ phụ thuộc AMR:
    require amr có dữ liệu đã được OP cam kết và phù hợp

if quyền nghiệp vụ không đạt:
    deny

allow
~~~

Trạng thái “không đạt” có thể dẫn tới điều hướng step-up thay vì trả lỗi vĩnh viễn, nhưng không được thực hiện thao tác nhạy cảm trước khi policy được đánh giá lại.

### 12.3. Thiếu claim không mặc định là không xác thực

Ví dụ ID Token hợp lệ nhưng thiếu <code>amr</code>. Người dùng có thể đã MFA nhưng OP không công bố method claims. Quyết định đúng là:

- Nếu thao tác **không phụ thuộc AMR**, không bắt buộc phải có AMR.
- Nếu policy **bắt buộc AMR theo hợp đồng OP**, coi yêu cầu chưa đạt và điều tra cấu hình.
- Không kết luận “người dùng chỉ đăng nhập bằng mật khẩu” khi không thấy AMR; thiếu dữ liệu không chứng minh một phương thức cụ thể đã hoặc chưa xảy ra.

Tương tự, khi thiếu <code>auth_time</code> mà thao tác yêu cầu freshness, phải kích hoạt flow lấy claim hoặc từ chối, không dùng <code>iat</code> làm giá trị thay thế.

## 13. Security considerations của step-up

### 13.1. Bảo vệ danh tính khi xác thực lại

Giả sử người dùng A đang đăng nhập và được chuyển tới OP để step-up. Nếu sau step-up OP đăng nhập bằng tài khoản B do người dùng chọn, application không nên tự động coi B đã xác nhận thao tác đang chờ của A.

Ứng dụng phải xác định policy thay đổi tài khoản:

- Nếu step-up nhằm xác nhận lại **chính người dùng hiện tại**, yêu cầu cặp <code>(iss, sub)</code> sau flow trùng danh tính trước flow.
- Nếu hỗ trợ account switching, phải xử lý như luồng chuyển tài khoản riêng, xóa/đánh giá lại ngữ cảnh nghiệp vụ đang chờ.
- Không dùng email làm khóa chắc chắn để so sánh danh tính OIDC liên provider.

<code>login_hint</code> có thể giúp OP gợi ý tài khoản, nhưng **không thay thế** việc RP kiểm tra danh tính sau callback.

### 13.2. Gắn step-up với phiên và hành động cần bảo vệ

Một bước xác thực thành công không nên là “vé thông hành vô hạn” cho mọi tác vụ. Cần cân nhắc:

- Chính sách thời hạn ngắn, được đánh giá tại **mỗi endpoint nhạy cảm**.
- Xác nhận lại giao dịch khi hành động có tác động lớn.
- Correlation giữa yêu cầu step-up với HTTP session, state và công việc đang chờ.
- CSRF protection cho các request thay đổi trạng thái.
- Tránh tự động thực hiện POST chuyển tiền ngay sau một callback GET.
- Chính sách vô hiệu hóa quyền nâng cao sau logout hoặc chuyển tài khoản.

Nếu cần *transaction signing* hoặc xác thực gắn nội dung giao dịch, chỉ dùng ACR + auth_time có thể chưa đủ; phải có cơ chế phù hợp với yêu cầu nghiệp vụ và mô hình đe dọa.

### 13.3. Thời gian, clock skew và refresh token

Server Client cần đồng hồ tương đối chính xác, thường qua đồng bộ thời gian hệ thống. Một lượng clock skew nhỏ có thể được cho phép để tránh từ chối sai do chênh lệch đồng hồ, nhưng không dùng clock skew lớn đến mức làm vô hiệu chính sách freshness.

Việc sử dụng **refresh token** để lấy access token/ID Token mới không chứng minh End-User vừa được xác thực lại. Chính sách phải dựa vào <code>auth_time</code> được OP xác nhận và flow xác thực thật sự, không coi thời điểm refresh là thời điểm người dùng hoàn tất MFA.

### 13.4. Không log dữ liệu nhạy cảm

Khi debug OIDC Login, tránh ghi:

- ID Token, access token, refresh token nguyên bản.
- Authorization code, PKCE verifier, nonce và state thực.
- URL callback kèm query parameter chứa code/state.
- Session cookie hoặc secret của Client.

Có thể ghi nhận các dữ liệu đã làm sạch như registration ID, mã kết quả validation, boolean <code>auth_time_present</code>, ACR đã allowlist, thời điểm kiểm tra và correlation ID nội bộ. Khi AMR mang thông tin phương thức xác thực, cần cân nhắc chính sách riêng tư trước khi đưa vào log hoặc telemetry.

## 14. Sự cố thường gặp

| Triệu chứng | Nguyên nhân cần xem | Hướng xử lý |
|---|---|---|
| ID Token không có <code>auth_time</code> | Không yêu cầu <code>max_age</code>/Essential auth_time, hoặc OP không đáp ứng yêu cầu | Bổ sung yêu cầu đúng chuẩn, kiểm tra provider support; không dùng iat thay thế |
| Gửi <code>max_age=0</code> nhưng không thấy đăng nhập lại | Provider không tuân thủ, request không đi đúng OP, customizer không được áp dụng hoặc session hành vi không như mong đợi | Kiểm tra authorization request gửi đi, metadata/OP policy và auth_time sau callback |
| <code>acr</code> khác giá trị mong muốn | <code>acr_values</code> chỉ là voluntary, OP không hỗ trợ context, hoặc chính sách chưa đạt | Dùng Essential ACR nếu OP hỗ trợ; luôn kiểm tra ACR nhận được |
| Provider bỏ qua <code>claims</code> | Provider không hỗ trợ claims parameter hoặc client không được phép | Xem tài liệu/metadata provider, chọn cơ chế step-up mà OP hỗ trợ |
| Gửi đồng thời <code>acr_values</code> và Essential <code>acr</code> có values | Hành vi không xác định theo OIDC Core | Chọn một cơ chế yêu cầu ACR rõ ràng |
| <code>amr</code> không có | Claim tùy chọn, provider không phát hoặc không khai báo tương thích | Chỉ bắt buộc khi có hợp đồng; không suy ra user chưa MFA |
| <code>amr</code> có <code>mfa</code> nhưng ACR không đạt | Tập AMR và ACR biểu diễn ngữ nghĩa khác nhau | Đối chiếu với chính sách và hợp đồng OP, không dùng amr thay acr |
| Step-up xong vẫn bị từ chối | <code>auth_time</code> vẫn cũ, ACR thấp, phiên app giữ ID Token cũ, hoặc dùng tài khoản khác | Kiểm tra ID Token mới, principal đang dùng, session và policy |
| Callback lỗi state/nonce | Session/correlation mất, nhiều tab, repository/PKCE config sai | Chẩn đoán authorization request repository và callback chain |
| Người dùng bị chuyển sang login liên tục | Redirect step-up không có điểm dừng khi OP không đáp ứng assurance | Giới hạn số lần, hiển thị lỗi có hướng dẫn, ghi nhận mã lỗi vận hành |
| Đọc <code>auth_time</code> thành thời điểm năm 1970 | Nhầm giây/mili giây Unix time | Dùng <code>Instant.ofEpochSecond</code> hoặc accessor Spring Security |
| Policy cho phép chỉ dựa vào ACR nhưng thiếu quyền | Trộn assurance với business authorization | Kết hợp policy role/permission riêng |

## 15. Các tình huống và bài tập thực hành

### Bài 1 — Phân biệt iat và auth_time

ID Token vừa được cấp:

~~~json
{
  "iat": 1794808800,
  "auth_time": 1794787200,
  "acr": "urn:company:assurance:high"
}
~~~

Giả sử hệ thống yêu cầu xác thực trong 5 phút gần nhất. Có thể dùng <code>iat</code> làm mốc không?

**Đáp án:** Không. <code>iat</code> chỉ là thời điểm phát token, trong khi <code>auth_time</code> phản ánh lần xác thực End-User tại OP. Nếu auth_time đã quá 5 phút, cần step-up/reauthentication dù ID Token mới được phát.

### Bài 2 — Voluntary và Essential ACR

Client gửi:

~~~text
acr_values=urn:company:assurance:high
~~~

OP trả:

~~~json
{"acr": "urn:company:assurance:basic"}
~~~

Hỏi Client có nên cho phép thao tác chỉ dành cho High không?

**Đáp án:** Không. <code>acr_values</code> là yêu cầu voluntary. RP phải kiểm tra kết quả thực tế; ACR Basic không đạt policy High. Nếu OP hỗ trợ Essential ACR qua <code>claims</code>, có thể dùng cơ chế đó cho yêu cầu bắt buộc.

### Bài 3 — AMR có đủ xác định MFA không?

OP trả:

~~~json
{"amr": ["pwd", "otp"]}
~~~

Hỏi có thể kết luận ngay rằng người dùng đạt một chuẩn xác thực chống phishing cụ thể không?

**Đáp án:** Không. AMR chỉ liệt kê phương thức, và đặc tính của OTP có thể khác nhau. Cần ACR và hợp đồng OP định nghĩa cụ thể chính sách; nếu nghiệp vụ yêu cầu phishing resistance, phải có bằng chứng đúng với tiêu chí đó.

### Bài 4 — Viết policy

Giả sử yêu cầu nghiệp vụ:

~~~text
Role: PAYMENT_APPROVER
Authentication age: <= 300 seconds
Required ACR: urn:company:assurance:high
~~~

Hãy viết điều kiện tại server kiểm tra:

1. Người dùng được xác thực và có quyền nghiệp vụ.
2. ID Token được Spring Security xác minh.
3. <code>auth_time</code> hiện diện, hợp lệ và đủ mới.
4. <code>acr</code> đúng giá trị high cho phép.

Có thể sử dụng <code>AssurancePolicy</code> ở mục 10 cùng method security; nếu không đạt, phản hồi theo luồng yêu cầu step-up nhưng chưa thực hiện thanh toán.

### Bài 5 — Gửi Essential Claims

Viết giá trị JSON <code>claims</code> yêu cầu:

- <code>auth_time</code> là Essential.
- <code>acr</code> là Essential, thuộc một trong hai lớp xác thực đã được doanh nghiệp cho phép.

Ví dụ:

~~~json
{
  "id_token": {
    "auth_time": {"essential": true},
    "acr": {
      "essential": true,
      "values": [
        "urn:company:assurance:high",
        "urn:company:assurance:phishing-resistant"
      ]
    }
  }
}
~~~

Nhớ URL-encode JSON này khi gửi authorization request, không đồng thời gửi <code>acr_values</code> với các giá trị được yêu cầu riêng như trên.

### Bài 6 — Rủi ro đổi tài khoản trong step-up

Người dùng A mở một biểu mẫu thanh toán và bị yêu cầu step-up. Tại OP, browser chuyển sang tài khoản B và thực hiện MFA. Ứng dụng nhận ID Token mới với ACR High.

**Câu hỏi:** Có thể hoàn tất giao dịch của A bằng authentication B không?

**Đáp án:** Không tự động. Nếu step-up nhằm xác nhận lại A, RP phải kiểm tra cặp <code>(iss, sub)</code> của principal sau flow tương ứng tài khoản A trước flow và recheck các quyền nghiệp vụ. Thay đổi tài khoản phải là luồng riêng, không được dùng để tiếp tục một giao dịch đã gắn với danh tính cũ.

## 16. Ghi nhớ

- <code>auth_time</code> là thời điểm End-User authentication diễn ra theo **Unix seconds**, khác với <code>iat</code> là thời điểm phát hành ID Token.
- <code>auth_time</code> **bắt buộc có trong ID Token** khi Client gửi <code>max_age</code> hoặc yêu cầu nó là Essential Claim; trong các trường hợp khác có thể vắng mặt.
- <code>acr</code> là chuỗi định danh **lớp ngữ cảnh xác thực** do OP cam kết. Ý nghĩa từng ACR là chính sách/hợp đồng của provider, không có thứ tự phổ quát.
- <code>acr_values</code> yêu cầu ACR theo dạng **voluntary**; <code>claims</code> có thể yêu cầu Essential ACR với danh sách giá trị nếu OP hỗ trợ. Tránh gửi hai cách yêu cầu ACR cụ thể đồng thời.
- <code>amr</code> là **mảng các phương thức xác thực** được OP khai báo, không đồng nghĩa mức bảo đảm hay thời điểm xác thực.
- Spring Security cung cấp <code>OidcIdToken.getAuthenticatedAt()</code>, <code>getAuthenticationContextClass()</code> và <code>getAuthenticationMethods()</code> để đọc các claim sau OIDC Login.
- **Step-up an toàn** cần yêu cầu xác thực mạnh/mới hơn, xác minh ID Token mới, kiểm tra chính sách assurance và quyền nghiệp vụ, cùng ràng buộc danh tính/phiên và hành động nhạy cảm.

### Tài liệu tham khảo

- **[OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)**: ID Token, <code>auth_time</code>, <code>acr</code>, <code>amr</code>, <code>max_age</code>, <code>acr_values</code>, <code>prompt</code> và claims parameter.
- **[RFC 8176 — Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176)**: cơ chế đăng ký AMR và các giá trị tham chiếu phương thức xác thực.
- **[IANA Authentication Method Reference Values Registry](https://www.iana.org/assignments/authentication-method-reference-values/authentication-method-reference-values.xhtml)**: các AMR value được đăng ký và tài liệu giải nghĩa.
- **[Spring Security — IdTokenClaimAccessor API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html)**: <code>getAuthenticatedAt</code>, <code>getAuthenticationContextClass</code>, <code>getAuthenticationMethods</code>.
- **Spring Security Reference — OAuth2 Login (Servlet)**: ClientRegistration, OIDC Login, tùy biến authorization request và việc xác minh ID Token.
- **Spring Security Reference — Method Security**: cách bảo vệ endpoint và service method bằng annotation và policy tùy biến.
