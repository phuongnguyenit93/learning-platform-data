# 8.10. Yêu cầu acr_values và mức xác thực mong muốn

## Mục tiêu bài học

Trong OpenID Connect (OIDC), xác thực thành công chưa chắc đáp ứng cùng một mức bảo đảm ở mọi nghiệp vụ. Một ứng dụng có thể chấp nhận lần đăng nhập SSO thông thường để đọc hồ sơ nhưng muốn **mức xác thực cao hơn** trước khi chuyển tiền, phê duyệt thanh toán hoặc thay đổi thông tin nhạy cảm.

Tham số **`acr_values`** trong OIDC Authentication Request cho phép **Relying Party (RP)** diễn đạt những **Authentication Context Class Reference (ACR)** mà RP muốn **OpenID Provider (OP)** áp dụng khi xác thực người dùng. Kết quả thực tế cần được xem xét qua claim **`acr`** trong ID token nếu OP cung cấp.

Sau bài học, bạn có thể:

- Giải thích **ACR** biểu diễn điều gì và tại sao giá trị ACR cần được OP cùng RP thống nhất về ngữ nghĩa.
- Tạo OIDC Authorization Request có `acr_values` và hiểu **thứ tự ưu tiên**, cách URL-encode và những giới hạn của tham số.
- Phân biệt **`acr_values` (yêu cầu)** và **`acr` (kết quả trong ID token)**.
- Phân biệt `acr`, `amr`, `auth_time`, `max_age` và `prompt=login`.
- Xây dựng một luồng **step-up authentication** bằng Spring Security OAuth 2.0 Client.
- Bổ sung tham số tùy biến qua `OAuth2AuthorizationRequestResolver` mà vẫn giữ `state`, `nonce`, redirect URI và cơ chế PKCE.
- Áp chính sách ứng dụng khi OP trả mức ACR không mong muốn hoặc không trả claim `acr`.

## 1. Vấn đề: “đã đăng nhập” và “đủ mức xác thực” là hai câu hỏi khác nhau

Giả sử ứng dụng **Finance Portal** sử dụng Spring Boot và đăng nhập bằng một OP của doanh nghiệp. Portal có ba nhóm chức năng:

| Chức năng | Nhu cầu xác thực điển hình |
|---|---|
| Xem hồ sơ | Một phiên đăng nhập OIDC hợp lệ |
| Xem báo cáo nhạy cảm | Phiên đăng nhập hợp lệ, có thể yêu cầu xác thực đủ mới |
| Phê duyệt chuyển tiền | Phiên đăng nhập hợp lệ và **mức bảo đảm xác thực** phù hợp chính sách |

Người dùng Alice có thể đã đăng nhập vào OP từ sáng. Khi truy cập Finance Portal, browser tái sử dụng phiên SSO và Portal nhận một ID token hợp lệ. Với trang hồ sơ, kết quả đó có thể đủ.

Nhưng trước thao tác phê duyệt khoản thanh toán lớn, ứng dụng cần biết **OP đã xác thực Alice trong ngữ cảnh nào**: ngữ cảnh này có đáp ứng chính sách phê duyệt hay không?

OIDC cho phép RP:

1. **Yêu cầu** những authentication context mong muốn bằng `acr_values` hoặc một yêu cầu claim `acr` phù hợp.
2. **Nhận và xem xét** giá trị `acr` trong ID token nếu OP phát hành.
3. **Tự áp dụng chính sách** cho thao tác nghiệp vụ, chẳng hạn chỉ cho phép tiếp tục khi `acr` thuộc nhóm được chấp nhận và lần xác thực đủ mới.

Ý nghĩa của `acr` do hệ sinh thái định danh/nhà cung cấp xác định. Không thể kết luận mức bảo mật chỉ từ việc ID token có một chuỗi ACR nhìn giống “high”.

## 2. ACR là gì?

### 2.1. Authentication Context Class Reference

**ACR** là viết tắt của **Authentication Context Class Reference**. Trong OIDC Core, một giá trị ACR là chuỗi định danh cho **một lớp/ngữ cảnh xác thực** mà OP áp dụng khi xác thực End-User.

Nó trả lời câu hỏi:

> “Kết quả xác thực này thuộc lớp bảo đảm xác thực nào theo quy ước của OP/hệ thống định danh?”

Ví dụ minh họa **do hệ thống giả định tự quy ước**:

~~~text
urn:example:acr:basic
urn:example:acr:strong
urn:example:acr:regulated
~~~

Giả sử doanh nghiệp định nghĩa:

- `urn:example:acr:basic`: điều kiện xác thực cơ bản theo chính sách nội bộ.
- `urn:example:acr:strong`: mức bảo đảm xác thực tăng cường theo chính sách nội bộ.
- `urn:example:acr:regulated`: mức bảo đảm dành cho quy trình phải tuân thủ yêu cầu đặc thù.

**Các URN trên chỉ là ví dụ trong bài, không phải danh sách giá trị chuẩn được mọi OP hiểu.** Khi triển khai, phải sử dụng **đúng chuỗi ACR mà nhà cung cấp hỗ trợ**, cùng định nghĩa và chính sách xác thực tương ứng.

ACR có thể được gắn với một mô hình bảo đảm được tổ chức hoặc ngành công nhận. Nếu OP dùng danh sách chính thức, cần đọc đúng tài liệu mô tả mức đó; không tự đặt ý nghĩa cho giá trị.

### 2.2. ACR là một mức/ngữ cảnh, không phải tên phương thức đăng nhập

Giả sử một người dùng đăng nhập bằng mật khẩu và mã OTP. Việc này cho biết **phương thức** có thể đã dùng, nhưng tự nó không đủ để suy ra OP đã đạt một lớp ACR cụ thể.

Một lớp ACR có thể phụ thuộc vào nhiều yếu tố:

- Cách tài khoản được đăng ký và danh tính được xác minh trước đó.
- Loại credential và cơ chế xác thực hiện tại.
- Việc dùng nhiều yếu tố, thiết bị hoặc yếu tố kháng phishing.
- Chính sách khôi phục tài khoản, quản lý vòng đời credential.
- Các yêu cầu khác do khuôn khổ bảo đảm xác thực của OP định nghĩa.

Đừng tự tạo quy tắc “có OTP thì ACR cao” nếu OP chưa công bố cách ánh xạ và chưa cam kết áp dụng quy tắc đó.

### 2.3. ACR thuộc sự kiện xác thực, không trực tiếp là quyền nghiệp vụ

Giá trị ACR nói về **ngữ cảnh xác thực người dùng**. Nó không mặc định cấp phép một hành động ứng dụng.

Ví dụ, Alice có thể có ACR mạnh nhưng **không thuộc nhóm người được phê duyệt giao dịch**. Finance Portal vẫn phải kiểm tra:

- Tài khoản được xác định qua issuer và subject nào?
- Người dùng có role/quyền nghiệp vụ phù hợp?
- Có được quyền xử lý đúng giao dịch cụ thể?
- Mức ACR và độ mới xác thực có đạt yêu cầu?

Một kết quả OIDC hợp lệ chỉ là một đầu vào của quyết định phân quyền.

## 3. `acr_values` nằm ở đâu trong Authorization Request?

### 3.1. Tham số chuẩn của OIDC Authentication Request

OIDC định nghĩa tham số tùy chọn:

~~~text
acr_values
~~~

Nó cho phép RP gửi **một chuỗi gồm một hoặc nhiều giá trị ACR, phân tách bằng dấu cách**, biểu diễn các Authentication Context Class Reference được yêu cầu.

Ví dụ RP muốn mức mạnh, và chỉ định mức cơ bản như lựa chọn ưu tiên thấp hơn:

~~~text
acr_values=urn:example:acr:strong urn:example:acr:basic
~~~

Khi đưa vào URL, dấu cách và ký tự đặc biệt phải được mã hóa. Một phần query có thể trở thành:

~~~text
acr_values=urn%3Aexample%3Aacr%3Astrong%20urn%3Aexample%3Aacr%3Abasic
~~~

**Thứ tự giá trị thể hiện ưu tiên của RP**: giá trị đứng trước được ưu tiên hơn giá trị đứng sau. Thứ tự **không** có nghĩa OP sẽ thử từng mức theo một thuật toán bắt buộc.

### 3.2. Ví dụ Authorization Request hoàn chỉnh

Giả sử client `finance-web` đã được đăng ký tại OP và sử dụng OIDC Authorization Code:

~~~http
GET /authorize?response_type=code&client_id=finance-web&redirect_uri=https%3A%2F%2Ffinance.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&scope=openid%20profile&state=RANDOM_STATE&nonce=RANDOM_NONCE&acr_values=urn%3Aexample%3Aacr%3Astrong&max_age=300&code_challenge=RANDOM_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: idp.example.com
~~~

Các giá trị `RANDOM_*` chỉ là placeholder, **không dùng chuỗi cố định trong ứng dụng thực**.

| Tham số | Trách nhiệm |
|---|---|
| `response_type=code` | Chọn Authorization Code flow |
| `client_id` | Xác định OAuth 2.0 Client/RP đã đăng ký |
| `redirect_uri` | Callback đã đăng ký tại OP |
| `scope=openid ...` | Yêu cầu xử lý theo OIDC |
| `state` | Liên kết authorization response với request ban đầu |
| `nonce` | Liên kết ID token với Authentication Request |
| `acr_values` | Nêu các authentication context được RP ưu tiên |
| `max_age` | Yêu cầu độ mới của lần xác thực, nếu có |
| `code_challenge` và `code_challenge_method` | Thành phần PKCE bảo vệ Authorization Code flow |

`acr_values` là **tham số yêu cầu gửi đến OP**. Nó không phải một claim đã được xác minh, và cũng không phải access token.

### 3.3. Ý nghĩa thực tế của việc “yêu cầu” ACR

`acr_values` là **yêu cầu ưu tiên** trong OIDC; chỉ đưa giá trị này vào URL **không bảo đảm** OP sẽ xác thực ở mức mong muốn hoặc trả đúng giá trị đã yêu cầu.

Tùy provider và chính sách, OP có thể:

- Thực hiện cơ chế xác thực phù hợp với một ACR được yêu cầu.
- Sử dụng phiên đăng nhập sẵn có nếu phiên đó đã đạt mức thích hợp.
- Yêu cầu người dùng thực hiện xác thực bổ sung.
- Không hỗ trợ giá trị ACR mà client yêu cầu.
- Trả kết quả xác thực với ACR khác hoặc không chứa claim `acr` trong ID token, tùy khả năng và ngữ cảnh giao thức.
- Trả lỗi nếu không thể hoàn thành yêu cầu theo chính sách hoặc theo cơ chế yêu cầu claim được sử dụng.

Vì vậy, khi nghiệp vụ có **điều kiện bắt buộc** về mức xác thực, RP phải kiểm tra **kết quả** và từ chối thao tác nếu chưa đạt. Không được coi “đã gửi `acr_values`” là tương đương “đã đạt ACR”.

## 4. Claim `acr` trong ID token

### 4.1. `acr` là kết quả OP công bố

Một ID token sau khi xác thực có thể chứa claim:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-1288",
  "aud": "finance-web",
  "iat": 1760000100,
  "exp": 1760003700,
  "auth_time": 1760000000,
  "acr": "urn:example:acr:strong"
}
~~~

Đây là **payload minh họa**, không phải token thật. Trong OIDC, `acr` là claim không bắt buộc xuất hiện trong mọi ID token.

Cách hiểu:

- `iss`: issuer phát hành ID token.
- `sub`: subject của End-User trong phạm vi issuer.
- `aud`: audience phải phù hợp với client/RP nhận token.
- `iat`, `exp`: thời gian phát hành và hết hạn token.
- `auth_time`: thời điểm OP xác thực End-User, nếu được cung cấp.
- `acr`: lớp/ngữ cảnh xác thực mà OP thông báo cho lần xác thực tương ứng.

RP cần xác minh ID token theo các quy tắc OIDC thông thường **trước khi tin claim `acr`**: chữ ký, issuer, audience, thời hạn và các điều kiện của flow như nonce khi áp dụng.

Đừng lấy một JSON chưa xác minh từ browser rồi so sánh `acr`; khi đó một bên không tin cậy có thể tự cung cấp bất kỳ giá trị nào.

### 4.2. Claim `acr` có thể vắng mặt

Nếu không có `acr`, điều đó **không tự động có nghĩa mức xác thực thấp hoặc cao**; chỉ có nghĩa RP không nhận được một giá trị ACR có thể dùng cho chính sách của mình.

Nếu ứng dụng yêu cầu một mức ACR tối thiểu để thực hiện nghiệp vụ nhạy cảm, cách xử lý thận trọng là:

> Không có `acr` hợp lệ và được chấp nhận → chưa đạt điều kiện assurance của nghiệp vụ.

Ứng dụng có thể hướng dẫn người dùng bắt đầu lại luồng xác thực phù hợp hoặc báo rằng OP không hỗ trợ mức bảo đảm cần thiết.

### 4.3. Chỉ so sánh những giá trị có định nghĩa được tin cậy

Giả sử tổ chức chấp nhận:

~~~text
urn:example:acr:strong
urn:example:acr:regulated
~~~

Trong code có thể sử dụng một tập giá trị được cấu hình trước. Không giả định rằng một chuỗi `acr` có chứa từ `strong` hay `mfa` thì đạt yêu cầu. Cũng không nên coi việc sắp xếp chữ cái, số cuối URN hoặc cách đặt tên của vendor là thang bậc phổ quát.

Nếu tổ chức muốn **mức tối thiểu**, cần có quy tắc ánh xạ và thứ tự mức **đã thống nhất với OP**. Việc tự so sánh chuỗi theo thứ tự từ điển là không có ý nghĩa bảo mật.

## 5. So sánh `acr_values`, `acr`, `amr`, `auth_time` và `max_age`

Các trường dễ bị nhầm vì đều liên quan xác thực, nhưng trả lời những câu hỏi khác nhau.

| Thành phần | Vị trí | Câu hỏi chính |
|---|---|---|
| `acr_values` | Authentication Request | RP muốn OP áp dụng lớp xác thực nào? |
| `acr` | ID token, khi có | OP công bố lớp/ngữ cảnh xác thực nào? |
| `amr` | ID token, khi có | Những phương thức xác thực nào đã tham gia? |
| `auth_time` | ID token, khi có | Người dùng được OP xác thực vào thời điểm nào? |
| `max_age` | Authentication Request | RP chấp nhận lần xác thực cũ tối đa bao nhiêu giây? |
| `prompt=login` | Authentication Request | RP có muốn OP yêu cầu xác thực lại không? |

### 5.1. `amr` cho biết phương thức, `acr` cho biết lớp/ngữ cảnh

`amr` là **Authentication Methods References**. Ví dụ một ID token có thể chứa:

~~~json
{
  "acr": "urn:example:acr:strong",
  "amr": ["pwd", "otp"]
}
~~~

Ở đây, OP công bố một lớp ACR và các phương thức xác thực liên quan. `pwd` và `otp` là những mã phương thức thường thấy, nhưng việc diễn giải chi tiết còn phụ thuộc provider và định nghĩa các giá trị được sử dụng.

Không thể suy ra theo chiều ngược rằng mọi token có `amr=["pwd","otp"]` đều đạt `urn:example:acr:strong`. Mức bảo đảm không chỉ phụ thuộc vào số phương thức.

Tương tự, một OP có thể cung cấp ACR mà không đưa `amr` vào ID token. Nếu chính sách nghiệp vụ yêu cầu ACR, hãy làm việc với OP để xác định giá trị `acr` có thể tin cậy.

### 5.2. `max_age` điều khiển độ mới, không xác định mức assurance

Ví dụ:

~~~text
acr_values=urn:example:acr:strong
max_age=300
~~~

RP vừa yêu cầu:

1. Lớp xác thực mong muốn là `urn:example:acr:strong`.
2. Lần xác thực phải đủ mới theo giới hạn 300 giây.

Hai điều kiện độc lập. Một người vừa nhập mật khẩu cách đây 10 giây có thể **chưa đạt** mức mạnh; một người đã dùng phương thức mạnh từ hôm qua có thể **không đạt** điều kiện 5 phút.

Khi có `max_age` trong OIDC Authentication Request, ID token phải có `auth_time` để RP có thể đánh giá độ mới. `iat` là thời điểm phát hành token, không thay thế `auth_time`.

### 5.3. `prompt=login` đề nghị xác thực lại, không tự xác định ACR

Nếu ứng dụng gửi:

~~~text
prompt=login
~~~

RP yêu cầu OP xác thực lại. Nhưng đó **không phải lời yêu cầu cụ thể về lớp ACR**.

Có thể kết hợp:

~~~text
prompt=login
acr_values=urn:example:acr:strong
~~~

để nêu đồng thời ý định xác thực lại và mức mong muốn. Với yêu cầu “trong vòng 5 phút”, `max_age` cùng `auth_time` giúp biểu diễn và kiểm tra freshness rõ ràng hơn việc chỉ nhìn `prompt=login`.

### 5.4. ID token hợp lệ nhưng `acr` không đạt vẫn phải xử lý

Hãy xét ba phản hồi:

| ID token sau khi được xác minh | Quyết định cho thao tác yêu cầu `strong` |
|---|---|
| `acr=urn:example:acr:strong` | Có thể đạt điều kiện ACR; tiếp tục kiểm tra quyền và freshness |
| `acr=urn:example:acr:basic` | Không đạt yêu cầu ACR; không thực hiện thao tác |
| Không có claim `acr` | Chưa có bằng chứng đáp ứng chính sách; không thực hiện thao tác |

Một ID token vẫn có thể **hợp lệ về mặt giao thức** dù chưa thỏa **chính sách assurance của ứng dụng**. Đây là hai lớp kiểm tra riêng.

## 6. `acr_values` là tham số ưu tiên; yêu cầu bắt buộc qua `claims`

### 6.1. Vì sao `acr_values` có giới hạn?

Theo OIDC, `acr_values` cho phép yêu cầu các ACR theo thứ tự ưu tiên. Tuy nhiên, bản thân yêu cầu đó không tạo nghĩa vụ chung rằng OP phải thất bại nếu không đáp ứng một giá trị cụ thể.

Khi RP cần diễn đạt một **claim ACR thiết yếu** theo cơ chế OIDC, nó có thể sử dụng tham số **`claims`** trong Authentication Request, với `acr` bên trong `id_token`.

Ví dụ nội dung JSON của `claims`:

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:acr:strong",
        "urn:example:acr:regulated"
      ]
    }
  }
}
~~~

Về ý nghĩa, RP đang yêu cầu claim `acr` trong ID token có một giá trị được cho phép và đánh dấu claim này là **essential**. JSON phải được URL-encode khi gửi trong Authorization Request.

Các OP có thể khác nhau về **hỗ trợ `claims` parameter** và cách đáp ứng những yêu cầu mở rộng. Cần kiểm tra tài liệu và khả năng provider thực tế.

### 6.2. `claims` và `acr_values` không phải cùng tham số

| Cách yêu cầu | Điều nó biểu đạt |
|---|---|
| `acr_values=urn:example:acr:strong` | Ưu tiên một authentication context |
| `claims` với `id_token.acr.essential=true` | Nêu yêu cầu claim ACR thiết yếu theo cơ chế yêu cầu claim của OIDC |
| `max_age=300` | Giới hạn độ cũ của xác thực |
| `prompt=login` | Đề nghị OP xác thực lại |

Việc dùng `claims` vẫn **không thay thế kiểm tra phía RP**. Ứng dụng phải xác minh ID token và kiểm tra giá trị ACR thực nhận. Nếu provider không đáp ứng yêu cầu hoặc không hỗ trợ cơ chế đó, RP không được tiếp tục thao tác nhạy cảm chỉ vì request đã gửi `essential=true`.

Một số provider cung cấp cú pháp khác hoặc cách ánh xạ assurance chuyên biệt. Hãy dựa trên giao thức và tài liệu cụ thể của nhà cung cấp thay vì mặc định họ hiểu các URN minh họa trong bài.

### 6.3. Ví dụ truyền `claims` và `acr_values`

Nội dung trước URL-encode:

~~~text
scope=openid
acr_values=urn:example:acr:strong
claims={"id_token":{"acr":{"essential":true,"values":["urn:example:acr:strong"]}}}
~~~

Trong URL thực, cả dấu ngoặc kép, dấu ngoặc nhọn, dấu cách và dấu hai chấm đều cần được mã hóa thích hợp bằng thư viện xây URI.

Không xây URL bằng nối chuỗi từ input tùy ý. Một `claims` JSON không hợp lệ hoặc một yêu cầu provider không hỗ trợ có thể khiến Authorization Request bị từ chối.

## 7. Luồng step-up authentication

### 7.1. Step-up là gì?

**Step-up authentication** là việc ứng dụng yêu cầu người dùng thực hiện hoặc chứng minh **mức xác thực mạnh hơn** khi họ chuẩn bị thực hiện một hành động cần assurance cao.

Ví dụ:

1. Alice mở Finance Portal bằng OIDC Login và được chấp nhận vào trang tổng quan.
2. Alice chọn “Phê duyệt giao dịch”.
3. Portal kiểm tra chính sách và thấy phiên hiện tại chưa có mức ACR cần thiết.
4. Portal tạo OIDC Authentication Request mới với `acr_values` thích hợp; có thể thêm `max_age` theo chính sách freshness.
5. OP xác thực Alice theo chính sách và trả callback OIDC.
6. Portal xác minh kết quả, đọc `acr` và `auth_time` trong ID token.
7. Chỉ khi assurance, freshness, danh tính và quyền nghiệp vụ đều phù hợp, Portal mới cho phép tiếp tục phê duyệt.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant RP as Finance Portal / Spring Security
    participant OP as OpenID Provider
    U->>RP: Truy cập dashboard
    RP->>OP: OIDC Login thông thường nếu cần
    OP-->>RP: ID token, có thể có ACR cơ bản
    RP-->>U: Dashboard
    U->>RP: Yêu cầu phê duyệt giao dịch
    Note over RP: Kiểm tra ACR / auth_time / quyền
    RP-->>U: Yêu cầu step-up
    RP->>OP: Authorization Request với acr_values mong muốn
    OP->>U: Xác thực bổ sung nếu chính sách đòi hỏi
    OP-->>RP: Callback OIDC và ID token
    Note over RP: Xác minh token, acr, auth_time, iss + sub
    alt Đáp ứng chính sách
        RP-->>U: Cho phép tiếp tục quy trình
    else Không đáp ứng
        RP-->>U: Từ chối và giải thích yêu cầu xác thực
    end
~~~

**Step-up không đồng nghĩa lúc nào cũng phải nhập lại mật khẩu.** OP có thể nhận thấy session hiện tại đã thỏa mức được yêu cầu, hoặc áp dụng cơ chế xác thực bổ sung như passkey/MFA theo chính sách.

### 7.2. Kiểm tra danh tính trước và sau step-up

Một tình huống quan trọng: browser có thể chứa nhiều tài khoản tại OP. Sau khi bị chuyển sang OP để step-up, người dùng có thể chọn tài khoản khác.

Nếu nghiệp vụ đang được thực hiện cho Alice, RP cần đảm bảo callback step-up thuộc **đúng chủ thể** theo yêu cầu nghiệp vụ, thường là cùng cặp **`iss` + `sub`** với người đã bắt đầu thao tác.

Không chỉ so sánh email hoặc tên hiển thị. Không cho phép kết quả step-up của Bob tự động xác nhận một giao dịch đang được chuẩn bị trong ngữ cảnh Alice.

### 7.3. Bảo vệ luồng nghiệp vụ trước khi quay lại

Khi step-up kết thúc, ứng dụng có thể muốn quay về trang phê duyệt. Cần bảo vệ những dữ liệu liên quan:

- Giao dịch nào được yêu cầu phê duyệt.
- Ai đã bắt đầu hành trình step-up.
- Chính sách ACR/freshness nào áp dụng.
- Thời điểm yêu cầu được tạo và thời hạn hiệu lực của yêu cầu.
- Trạng thái `state`/nonce/PKCE của Authorization Code.

Nên quản lý bước phê duyệt đang chờ bằng trạng thái phía server đã được ràng buộc với người dùng và phiên, cùng một mã giao dịch không đoán được khi cần. **Không** lấy một tham số URL kiểu `?transactionId=...&approved=true` rồi tự xem như bằng chứng step-up thành công.

Ngay trước khi thực hiện phê duyệt thật, backend cần kiểm tra lại quyền và chính sách đối với giao dịch hiện tại. Một callback thành công không đồng nghĩa mọi thao tác sau đó được phép vô thời hạn.

### 7.4. Tránh vòng lặp xác thực

Nếu OP không hỗ trợ ACR mà ứng dụng yêu cầu, browser có thể liên tục bị gửi lại màn hình đăng nhập khi RP không kiểm tra kết quả.

Hướng xử lý đúng:

1. Nếu `acr` không đạt, không tiếp tục nghiệp vụ nhạy cảm.
2. Thông báo rõ không thể xác minh mức bảo đảm yêu cầu.
3. Cho phép một luồng thử lại có giới hạn nếu hợp lý.
4. Không tự động lặp vô hạn cùng Authorization Request.
5. Có phương án quản trị hoặc yêu cầu người dùng liên hệ hỗ trợ khi OP không thể cấp assurance phù hợp.

## 8. Cấu hình OIDC Client trong Spring Boot

### 8.1. Dependency

Với Maven và Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 8.2. Registration và provider

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/company
~~~

Trong cấu hình:

- `corporate` là registration ID dùng trong Spring Security.
- `client-id` và `client-secret` được OP cấp khi đăng ký confidential client.
- `issuer-uri` là issuer đã tin cậy; Spring có thể sử dụng OIDC discovery để lấy endpoint và metadata.
- `scope=openid` khiến authorization request được xử lý như một yêu cầu OIDC.
- `authorization_code` là flow login với callback của ứng dụng.

**`acr_values` không phải một scope.** Không viết `acr_values` vào danh sách `scope` để yêu cầu ACR; nó là **additional parameter** của OIDC Authorization Request.

## 9. Thêm `acr_values` bằng `OAuth2AuthorizationRequestResolver`

### 9.1. Tại sao cần tùy biến Authorization Request?

Spring Security cung cấp `DefaultOAuth2AuthorizationRequestResolver` để tạo request gồm thông tin từ `ClientRegistration`, redirect URI và các giá trị liên kết callback.

Nếu cần gửi một tham số OIDC như `acr_values`, ta có thể **bọc resolver mặc định** và thêm `additionalParameters`. Cách này tiếp tục dùng cơ chế framework để tạo `state`, nonce OIDC và PKCE khi được cấu hình.

### 9.2. Ví dụ yêu cầu một ACR ưu tiên cho toàn bộ login OIDC

Ví dụ sau đặt ACR minh họa cho registration `corporate`. Nó là **cấu hình áp dụng cho mọi lần login của registration này**, phù hợp khi ứng dụng muốn toàn bộ phiên đăng nhập có assurance cao.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcAcrSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver delegate =
                new DefaultOAuth2AuthorizationRequestResolver(
                        registrations,
                        "/oauth2/authorization");

        OAuth2AuthorizationRequestResolver resolver =
                new OAuth2AuthorizationRequestResolver() {

                    @Override
                    public OAuth2AuthorizationRequest resolve(
                            HttpServletRequest request) {
                        return addAcrValues(delegate.resolve(request));
                    }

                    @Override
                    public OAuth2AuthorizationRequest resolve(
                            HttpServletRequest request,
                            String registrationId) {
                        return addAcrValues(
                                delegate.resolve(request, registrationId));
                    }
                };

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .authorizationEndpoint(endpoint -> endpoint
                                .authorizationRequestResolver(resolver)))
                .build();
    }

    private static OAuth2AuthorizationRequest addAcrValues(
            OAuth2AuthorizationRequest original) {

        if (original == null
                || !original.getScopes().contains("openid")) {
            return original;
        }

        return OAuth2AuthorizationRequest.from(original)
                .additionalParameters(parameters ->
                        parameters.put(
                                "acr_values",
                                "urn:example:acr:strong"))
                .build();
    }
}
~~~

Giải thích:

1. `delegate` tạo Authorization Request theo Spring Security với provider và registration đã cấu hình.
2. `addAcrValues(...)` giữ nguyên request trừ việc bổ sung tham số OIDC.
3. `getScopes().contains("openid")` giúp chỉ thêm ACR khi đây là yêu cầu OIDC.
4. `OAuth2AuthorizationRequest.from(original)` giữ các thông tin đã xây bởi framework.
5. `additionalParameters(...)` thêm `acr_values` vào request chuyển đến OP.
6. `oauth2Login(...)` dùng resolver mới để khởi tạo Authorization Code flow.

**Cần phân biệt:** Ví dụ này mới **yêu cầu** ACR. Nếu không có bước đánh giá claim `acr` sau callback, nó **chưa bảo đảm** người dùng đạt assurance chính sách.

Một registration khác không dùng OIDC nên được xử lý theo yêu cầu riêng; nếu hệ thống có nhiều registration OIDC với mức khác nhau, cần chọn chính sách theo registration/luồng nghiệp vụ tin cậy.

### 9.3. Thêm nhiều ACR theo thứ tự ưu tiên

Trong resolver, có thể đặt:

~~~java
parameters.put(
        "acr_values",
        "urn:example:acr:strong urn:example:acr:basic");
~~~

Spring Security xây query URI và thực hiện URL encoding ở bước tạo Authorization Request. **Giá trị truyền vào parameter map là chuỗi chưa URL-encode**; không cần tự thay dấu cách thành `%20` trước khi đưa vào map.

Nếu nghiệp vụ **không được phép** sử dụng mức `basic`, **đừng đặt mức basic vào danh sách như một kết quả chấp nhận được**. Hãy định nghĩa chính sách rõ và đối chiếu kết quả ACR.

### 9.4. Trường hợp chỉ cần step-up cho một chức năng

Đặt `acr_values` mạnh lên **mọi lần đăng nhập** có thể khiến người dùng phải thực hiện xác thực tăng cường ngay cả khi chỉ mở trang thông tin thông thường.

Với ứng dụng có cả chức năng thông thường và nhạy cảm:

- Đăng nhập ban đầu theo registration/luồng OIDC thông thường.
- Khi người dùng truy cập chức năng yêu cầu assurance cao, kiểm tra policy tại backend.
- Nếu chưa đạt, backend khởi động **một OIDC Authentication Request mới** có `acr_values` dành cho step-up.
- Khi callback thành công, backend kiểm tra `acr`, `auth_time` khi có chính sách freshness, danh tính và quyền nghiệp vụ.
- Tiếp tục chức năng chỉ sau khi toàn bộ điều kiện được đáp ứng.

Về kỹ thuật, có thể thiết kế **endpoint step-up riêng** được liên kết với một chiến lược `OAuth2AuthorizationRequestResolver`, hoặc dùng một registration/luồng đăng nhập riêng đã được cấu hình cho assurance cao. Khi dùng registration riêng nhưng cùng client/provider, callback/redirect URI cũng phải được OP cho phép.

**Đừng lấy thẳng `acr_values` từ query parameter không được kiểm soát** rồi cho client tùy ý quyết định mức assurance cần thiết. RP phải định nghĩa chính sách theo nghiệp vụ và kiểm soát lựa chọn giá trị.

## 10. Đọc claim `acr` trong Spring Security

### 10.1. Principal OIDC sau login

Sau OIDC Login trên Servlet stack, Authentication thường là `OAuth2AuthenticationToken` có principal `OidcUser`. ID token có thể được đọc từ principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AssuranceInfoController {

    @GetMapping("/me/assurance")
    AssuranceInfo assurance(
            @AuthenticationPrincipal OidcUser user) {

        String acr = user.getIdToken().getClaimAsString("acr");

        return new AssuranceInfo(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                acr,
                user.getIdToken().getAuthenticationTime()
        );
    }

    record AssuranceInfo(
            String issuer,
            String subject,
            String acr,
            java.time.Instant authenticationTime) {}
}
~~~

Ở đây:

- `user.getIdToken()` là ID token đã được xử lý bởi OIDC Login.
- `getClaimAsString("acr")` trả giá trị ACR, hoặc có thể `null` khi claim không tồn tại.
- `getAuthenticationTime()` trả thời điểm xác thực nếu có `auth_time`.
- `issuer` và `subject` dùng để xác định danh tính OP.

Endpoint trên chỉ để **quan sát**. Trả công khai thông tin assurance có thể không cần thiết trong production; cân nhắc bảo vệ endpoint và tối thiểu hóa dữ liệu.

**Không** chỉ hiển thị ACR trên giao diện rồi để frontend quyết định có cho phê duyệt giao dịch hay không. Quyết định bắt buộc phải được thực thi phía backend.

### 10.2. Ví dụ kiểm tra giá trị ACR trong logic nghiệp vụ

Một hàm policy đơn giản:

~~~java
import java.util.Set;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class AssurancePolicy {

    private static final Set<String> APPROVED_ACR = Set.of(
            "urn:example:acr:strong",
            "urn:example:acr:regulated"
    );

    private AssurancePolicy() {
    }

    public static boolean hasAcceptedAcr(OidcUser principal) {
        if (principal == null || principal.getIdToken() == null) {
            return false;
        }

        String acr = principal.getIdToken().getClaimAsString("acr");
        return acr != null && APPROVED_ACR.contains(acr);
    }
}
~~~

Chính sách `APPROVED_ACR` cần đến từ cấu hình đáng tin cậy và phải phản ánh **giá trị OP thực sự phát hành với ý nghĩa đã được tổ chức chấp thuận**.

Hàm này mới kiểm tra điều kiện ACR, **chưa** xác minh:

- `auth_time` có đủ mới hay không.
- Người dùng có quyền nghiệp vụ hay không.
- Giao dịch có thuộc người dùng hoặc phạm vi thao tác hợp lệ không.
- Chủ thể sau step-up có trùng chủ thể bắt đầu giao dịch không.

Các điều kiện còn lại phải được thực thi trong quy trình bảo vệ thao tác.

### 10.3. Bảo đảm ID token đã được kiểm tra trước khi sử dụng

Trong ví dụ, `OidcUser` đến từ OIDC Login của Spring Security. Ứng dụng cần để framework thực hiện đầy đủ các bước giao thức và kiểm tra token, cùng cấu hình issuer/provider đáng tin cậy.

Không viết controller nhận JWT tùy ý từ request body:

~~~java
// Không làm kiểu này để quyết định assurance:
// String acr = decodeWithoutVerification(jwt).get("acr");
~~~

Một giá trị `acr` chỉ có ý nghĩa khi nó được **OP mà RP tin cậy** phát hành và được kiểm tra theo điều kiện giao thức. Với hệ thống nhiều OP, chính sách ACR cũng cần được phân tách theo issuer, vì cùng một chuỗi ACR không nhất thiết có cùng định nghĩa ở hai nhà cung cấp.

## 11. Chặn login nếu ACR không đạt yêu cầu

Trong một ứng dụng **mà mọi lần đăng nhập đều phải đạt assurance cao**, có thể dùng extension point OIDC user service để đánh giá ACR trước khi chấp nhận principal.

Ví dụ Spring Security 6, Servlet stack:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Configuration
public class OidcAssuranceBeans {

    @Bean
    OidcUserService enforcingOidcUserService() {
        OidcUserService delegate = new OidcUserService();

        return new OidcUserService() {

            @Override
            public OidcUser loadUser(OidcUserRequest request)
                    throws OAuth2AuthenticationException {

                OidcUser user = delegate.loadUser(request);

                String acr =
                        request.getIdToken().getClaimAsString("acr");

                if (!"urn:example:acr:strong".equals(acr)) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(
                                    "insufficient_acr",
                                    "Requested authentication context was not met",
                                    null
                            )
                    );
                }

                return user;
            }
        };
    }
}
~~~

Cấu hình sử dụng service này trong `oauth2Login()`:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OidcUserService enforcingOidcUserService) throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(login -> login
                    .userInfoEndpoint(userInfo -> userInfo
                            .oidcUserService(enforcingOidcUserService)))
            .build();
}
~~~

Hai đoạn code là phần minh họa **các cấu hình phối hợp**: trong một dự án thật, hợp nhất bean/filter-chain theo thiết kế và đồng thời áp dụng resolver yêu cầu `acr_values` ở phần trước.

Ý nghĩa:

1. Spring Security xử lý OIDC Login theo flow thông thường.
2. `OidcUserService` tải hoặc xây thông tin principal từ các dữ liệu hợp lệ trong quá trình login.
3. Ứng dụng kiểm tra claim `acr` của **ID token trong `OidcUserRequest`**.
4. Nếu không đạt, ném `OAuth2AuthenticationException`; login không được coi thành công theo chính sách.
5. Nếu đạt, user service trả `OidcUser` để flow tiếp tục.

**Lưu ý phạm vi:** Đoạn code trên **bắt buộc ACR mạnh cho mọi lần OIDC Login** sử dụng service đó. Đối với hệ thống chỉ step-up cho một vài chức năng, chính sách cần được thiết kế riêng theo hành trình được backend kiểm soát để không vô tình chặn đăng nhập thông thường. Có thể đánh giá assurance tại bước phê duyệt và thiết kế workflow step-up có ràng buộc principal, freshness và giao dịch.

Không dùng một cờ `strongLogin=true` trong session do frontend có thể tự điều khiển để thay thế kết quả ACR đáng tin cậy.

## 12. Step-up và quản lý phiên đăng nhập Servlet

### 12.1. Bản chất của session sau khi đăng nhập

Ứng dụng Servlet thường lưu `SecurityContext` qua `HttpSession` sau OIDC Login. Principal có thể chứa thông tin ID token của lần xác thực đã hoàn thành.

Nếu người dùng đã login với ACR mạnh cách đây nhiều giờ, session Portal vẫn có thể còn hiệu lực. **Claim ACR trong principal không tự hết ý nghĩa chỉ vì thời gian trôi qua**, nhưng chính sách nghiệp vụ có thể yêu cầu kết hợp freshness.

Ví dụ:

~~~text
Điều kiện phê duyệt:
  acr thuộc nhóm accepted
  AND auth_time trong 5 phút gần nhất
  AND người dùng có authority/role phù hợp
  AND người dùng có quyền trên giao dịch
~~~

Nếu thiếu `auth_time` trong ngữ cảnh có yêu cầu `max_age` hoặc giá trị quá cũ theo chính sách, Portal cần thực hiện lại flow xác thực phù hợp.

### 12.2. Không coi thời hạn token như thời điểm xác thực

Các thời điểm sau khác nhau:

- `iat`: ID token được phát hành khi nào.
- `exp`: ID token hết hạn khi nào.
- `auth_time`: người dùng được OP xác thực khi nào.
- HttpSession timeout: phiên ứng dụng không hoạt động bao lâu thì hết hạn.
- Access token expiry: token gọi API còn hợp lệ đến khi nào.

Một ID token mới được phát hành có `iat` rất gần hiện tại **không chứng minh** user vừa được xác thực mạnh. Khi cần freshness, dùng `auth_time` và các điều kiện OIDC phù hợp.

### 12.3. Tránh mất liên kết giữa step-up và tác vụ nhạy cảm

Giả sử Alice đang chờ phê duyệt giao dịch `TX-4821`. Sau step-up, backend cần xác nhận:

- Request step-up này phục vụ chính giao dịch nào?
- Phiên/tài khoản bắt đầu step-up có còn tương ứng với callback hay không?
- Có bị chuyển sang tài khoản khác tại OP không?
- Giao dịch có bị sửa/xóa/chuyển quyền trong lúc xác thực không?
- ACR và freshness có còn đạt tại thời điểm **thực hiện thao tác** không?

Chỉ dựa vào URL quay lại sau login và giá trị ACR mà không ràng buộc giao dịch có thể tạo lỗ hổng trong các workflow nhiều bước.

## 13. Làm việc với provider: ACR không phải chuỗi phổ quát

### 13.1. Những điều cần xác nhận với OP

Trước khi triển khai assurance policy, cần thống nhất:

1. OP hỗ trợ những **ACR values** nào và định nghĩa của từng giá trị là gì?
2. OP có chấp nhận tham số `acr_values` trong Authorization Request hay không?
3. OP có trả claim `acr` trong ID token không? Trong những trường hợp nào?
4. OP có hỗ trợ `claims` parameter và yêu cầu `acr` thiết yếu không?
5. Nếu không đáp ứng ACR được yêu cầu, OP trả một ACR khác, bỏ qua claim hay trả lỗi?
6. OP có hỗ trợ step-up trên phiên SSO hiện tại không? Có cần tham số/cấu hình riêng?
7. Chính sách về `auth_time`, `max_age`, `amr` và cách xác thực bổ sung được áp dụng ra sao?

Nếu là môi trường có nhiều tenant hoặc OP, cần xác nhận từng issuer riêng biệt.

### 13.2. Đọc metadata để hiểu khả năng, nhưng không suy diễn quá mức

OIDC Discovery có thể cung cấp thông tin như:

~~~json
{
  "issuer": "https://idp.example.com/realms/company",
  "claims_supported": ["sub", "iss", "aud", "auth_time", "acr"],
  "acr_values_supported": [
    "urn:example:acr:basic",
    "urn:example:acr:strong"
  ]
}
~~~

Đây là ví dụ minh họa; provider thực tế có thể không công bố đầy đủ những trường này hoặc dùng danh sách khác.

`acr_values_supported` nếu được công bố cho biết các giá trị ACR mà OP nêu hỗ trợ. `claims_supported` mô tả các claim OP có khả năng cung cấp. **Sự hiện diện trong metadata không bảo đảm client của bạn được phép sử dụng mọi giá trị**, còn việc vắng một trường tùy chọn không nhất thiết chứng minh provider không hỗ trợ tính năng đó.

Một số sản phẩm ánh xạ ACR sang policy/authentication flow riêng của nhà cung cấp. Hãy dựa vào tài liệu và cấu hình provider, không chỉ metadata.

### 13.3. Một giá trị ACR ở hai issuer không nhất thiết có cùng ý nghĩa

Ví dụ:

~~~text
Issuer A: https://login-a.example.com
acr: urn:example:acr:strong

Issuer B: https://login-b.example.com
acr: urn:example:acr:strong
~~~

Dù chuỗi giống nhau, RP không nên tự mặc định hai OP có cùng kiểm soát và mức bảo đảm. Nếu ứng dụng liên kết nhiều OP, cần xây dựng **chính sách ánh xạ ACR theo issuer** và chỉ tin những issuer đã được xác định trước.

## 14. Lỗi và tình huống thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Gửi `acr_values` nhưng không thấy MFA bổ sung | OP đã chấp nhận session hiện tại, bỏ qua yêu cầu hoặc định nghĩa ACR khác kỳ vọng | Xem `acr` trả về và chính sách OP, đừng suy luận từ giao diện |
| ID token không có `acr` | OP không trả claim hoặc chưa cấu hình hỗ trợ | Không cho vượt yêu cầu assurance; kiểm tra khả năng provider |
| `acr` trả giá trị không nằm trong danh sách chấp nhận | OP không thể hoặc không chọn ACR mong muốn | Từ chối thao tác nhạy cảm, đề nghị luồng xác thực phù hợp |
| OP trả lỗi cho giá trị ACR | ACR không hỗ trợ, client không có quyền, yêu cầu claim không phù hợp | Đối chiếu giá trị với tài liệu provider |
| Đã có ACR mạnh nhưng vẫn không được phê duyệt | Thiếu authority hoặc không có quyền trên giao dịch | Kiểm tra chính sách authorization nghiệp vụ |
| `auth_time` quá cũ | Phiên SSO dùng lại kết quả cũ, freshness chưa đạt | Khởi động flow với `max_age`, kiểm tra thời điểm xác thực |
| Trang bị redirect login vô hạn | Chính sách đòi ACR mà provider không trả; callback tự khởi động lại | Chặn lặp, trả thông báo không đạt assurance |
| Người dùng sau step-up là tài khoản khác | OP cho chọn tài khoản khác trong khi browser có nhiều phiên | So sánh `iss` + `sub` với chủ thể bắt đầu workflow |
| `acr_values` xuất hiện thành một phần scope | Đã cấu hình sai ở registration `scope` | Chuyển sang `additionalParameters` của Authorization Request |
| Giá trị ACR có khoảng trắng bị cắt sai | Nối URL thủ công hoặc mã hóa sai | Để URI builder/framework encode giá trị request |
| Có `acr` trong JWT chưa xác minh | Ứng dụng tự decode và tin nội dung token | Dùng OIDC Login và kiểm tra token từ OP đã tin cậy |
| Login bình thường bị chặn do policy step-up | Áp ACR mạnh vào mọi callback thay vì riêng giao dịch | Thiết kế phân nhánh policy theo hành trình backend |

### 14.1. Không suy luận ACR từ giao diện người dùng

Màn hình OTP xuất hiện không có nghĩa RP có thể tự điền `acr=strong`. Chỉ OP công bố context đã áp dụng qua kết quả giao thức phù hợp; RP kiểm tra kết quả và ánh xạ nó theo chính sách đã thống nhất.

Ngược lại, việc không có màn hình MFA ở lượt đăng nhập hiện tại không nhất thiết có nghĩa OP không đáp ứng ACR. Chính sách OP có thể tính đến trạng thái phiên hoặc xác thực đã hoàn thành trước đó. Nếu nghiệp vụ yêu cầu sự kiện gần thời điểm hiện tại, cần thêm chính sách freshness.

### 14.2. Đừng cho frontend tự chọn mức assurance yêu cầu

Ví dụ nguy hiểm:

~~~text
POST /approve-payment?acr=basic
~~~

và backend coi giá trị `acr` trong query của browser là chính sách cần áp dụng.

Chính sách phải do backend xác định từ loại thao tác và rủi ro. Dữ liệu do browser gửi có thể đề nghị chuyển hướng hoặc khởi động một flow, nhưng không được **hạ mức bắt buộc** của nghiệp vụ.

### 14.3. Tránh dùng ACR thay cho xác thực giao dịch

Dù ACR cao, người dùng vẫn có thể bị dẫn tới phê duyệt một giao dịch sai nếu ứng dụng không kiểm tra **ngữ cảnh phê duyệt** và quyền trên tài nguyên.

ACR là một phần của chính sách truy cập, không tự chứng minh rằng người dùng đã xem hoặc đồng ý với một nội dung giao dịch cụ thể. Nếu nghiệp vụ yêu cầu xác nhận từng giao dịch, cần cơ chế xác nhận/ràng buộc giao dịch phù hợp.

## 15. Ví dụ thiết kế chính sách assurance theo chức năng

Một chính sách giả định cho Finance Portal:

| Hành động | ACR yêu cầu | Độ mới | Điều kiện khác |
|---|---|---|---|
| Xem trang hồ sơ | OIDC Login hợp lệ | Theo phiên ứng dụng | Đúng tài khoản |
| Xem báo cáo tài chính | Một ACR được tổ chức phê duyệt | Trong 30 phút nếu có yêu cầu | Có quyền xem báo cáo |
| Tạo lệnh thanh toán | `urn:example:acr:strong` | Trong 10 phút | Có quyền tạo |
| Phê duyệt giao dịch lớn | `urn:example:acr:regulated` | Trong 5 phút | Có quyền duyệt và không tự duyệt lệnh của mình |

Các giá trị, mốc thời gian và quyền ở bảng này **chỉ là chính sách minh họa**, không phải yêu cầu chung của OIDC hoặc một quy định pháp lý.

Một chiến lược triển khai:

1. Dùng OIDC Login bình thường cho các chức năng cơ bản.
2. Trước mỗi thao tác nhạy cảm, backend đánh giá danh tính, quyền, ACR và freshness.
3. Nếu thiếu assurance, bắt đầu OIDC Authorization Request mới với ACR cần thiết và `max_age` phù hợp.
4. Sau callback, kiểm tra ID token và người dùng đúng tài khoản.
5. Chỉ tiếp tục tác vụ nếu policy thỏa mãn ở thời điểm quyết định.
6. Ghi nhận sự kiện bảo mật cần thiết bằng correlation ID, không ghi token hoặc secret vào log.

Trong hệ thống thực tế, policy nên được cấu hình tập trung để các endpoint không tự đặt các quy tắc assurance khác nhau một cách vô tình.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `acr_values` có buộc OP luôn trả một giá trị `acr` giống hệt trong request không?

**Trả lời:** Không. `acr_values` diễn đạt các ACR được ưu tiên. RP phải kiểm tra ID token và giá trị `acr` thực nhận; nếu không đạt policy thì không cho phép thao tác yêu cầu assurance cao.

**Câu 2.** `acr` và `amr` khác nhau ở điểm nào?

**Trả lời:** `acr` biểu diễn lớp/ngữ cảnh xác thực mà OP công bố; `amr` mô tả các phương thức xác thực đã tham gia. Không được mặc định một danh sách phương thức tự động tương đương một lớp ACR.

**Câu 3.** Một ID token mới phát hành có `iat` gần hiện tại nhưng `auth_time` từ hôm qua. Có thể coi người dùng vừa được xác thực không?

**Trả lời:** Không. `iat` chỉ là thời điểm phát hành token. Để kiểm tra độ mới của xác thực, cần `auth_time` theo chính sách, thường kết hợp yêu cầu `max_age` trong flow phù hợp.

**Câu 4.** Đã gửi `acr_values=urn:example:acr:strong` nhưng ID token trả `acr=urn:example:acr:basic`. Có nên cho phép phê duyệt giao dịch đòi `strong`?

**Trả lời:** Không. Yêu cầu đã gửi không thay thế kết quả thực nhận; backend cần từ chối hoặc khởi động một luồng xác thực phù hợp nếu được hỗ trợ.

**Câu 5.** Muốn hỏi thêm một ACR, có viết `scope: [openid, acr_values]` trong `application.yml` không?

**Trả lời:** Không. `acr_values` là tham số OIDC Authorization Request, không phải scope. Trong Spring Security có thể thêm qua `OAuth2AuthorizationRequestResolver`.

**Câu 6.** Nếu OP đã xác thực người dùng ở mức mạnh nhưng từ lâu, làm sao yêu cầu thêm freshness?

**Trả lời:** Dùng `max_age` theo ngưỡng cần thiết, kiểm tra `auth_time` trong ID token sau flow. Không coi thời gian hết hạn của HTTP session hoặc `iat` là dấu mốc xác thực.

**Câu 7.** Hai OP đều trả chuỗi ACR `strong` thì ứng dụng có thể tin hai kết quả là ngang mức không?

**Trả lời:** Chỉ khi tổ chức đã xác minh và thống nhất ý nghĩa/độ tin cậy của giá trị đó cho từng issuer. ACR cần được diễn giải trong ngữ cảnh OP và chính sách xác thực của nó.

**Câu 8.** Step-up đã thành công với Bob nhưng Alice là người khởi tạo lệnh chuyển tiền. Có thể dùng callback của Bob để tiếp tục lệnh của Alice không?

**Trả lời:** Không tự động. Backend phải ràng buộc step-up với chủ thể và giao dịch đã khởi tạo, kiểm tra issuer + subject và quyền nghiệp vụ. Nếu không khớp, phải dừng hoặc bắt đầu lại theo quy trình đúng.

## Ghi nhớ

- **`acr_values` là tham số OIDC Authentication Request** dùng để yêu cầu các Authentication Context Class Reference theo **thứ tự ưu tiên**.
- **`acr` trong ID token** là kết quả OP công bố, nếu có. RP phải xác minh ID token, đối chiếu ACR theo chính sách và **không mặc định OP đã đáp ứng yêu cầu chỉ vì request chứa `acr_values`**.
- **`amr`** nói về phương thức xác thực; **`acr`** nói về ngữ cảnh/lớp xác thực; **`auth_time`** và **`max_age`** nói về độ mới của xác thực.
- Với thao tác nhạy cảm, triển khai **step-up authentication** cùng kiểm tra danh tính, ACR, freshness và quyền nghiệp vụ. Chính sách phải do backend thực thi.
- Trong **Spring Security OAuth 2.0 Client**, có thể bổ sung `acr_values` bằng `OAuth2AuthorizationRequestResolver` và đọc kết quả từ `OidcUser.getIdToken()`; sử dụng dữ liệu OP đáng tin cậy và extension point của framework để xử lý trạng thái đăng nhập.
