# Bỏ qua exp, nbf hoặc xử lý sai đơn vị thời gian

JWT thường dùng các claim thời gian để giới hạn thời điểm token được chấp nhận. Nếu resource server bỏ qua thời hạn, đọc sai kiểu dữ liệu hoặc nhầm giây với mili giây, token có thể bị chấp nhận sau khi hết hạn, được dùng trước thời điểm hiệu lực hoặc bị từ chối sai. Đây là lỗi xác minh có thể mở rộng cửa sổ tấn công cho bearer token bị đánh cắp và làm các dịch vụ đưa ra quyết định không nhất quán.

Bài học thuộc chương **Tấn công JWT** của module **Security – JSON Web Token (JWT)**. Nội dung tập trung vào ngữ nghĩa của NumericDate, cách kiểm tra exp/nbf/iat, lỗi đơn vị thời gian, clock skew, độ chính xác số và kiểm thử ranh giới thời gian. Các nguyên tắc áp dụng cho mọi ngôn ngữ, runtime, API gateway và resource server.

## 1. Ba claim thời gian có ý nghĩa khác nhau

JWT Registered Claims định nghĩa ba claim thường gặp:

| Claim | Tên đầy đủ | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| exp | Expiration Time | Thời điểm token không còn được chấp nhận | Token đã hết hạn chưa? |
| nbf | Not Before | Thời điểm token bắt đầu được chấp nhận | Token đã tới thời điểm hiệu lực chưa? |
| iat | Issued At | Thời điểm token được phát hành | Token được tạo khi nào và có quá cũ hoặc nằm trong tương lai bất hợp lý không? |

Không được coi ba claim này là các biến thể của cùng một thời điểm:

- exp giới hạn cuối khoảng thời gian sử dụng.
- nbf giới hạn đầu khoảng thời gian sử dụng.
- iat ghi nhận thời điểm phát hành; bản thân claim này không thay thế exp.

Một JWT có thể không chứa một hoặc nhiều claim thời gian theo định nghĩa JWT tổng quát. Tuy nhiên, profile của access token hoặc chính sách của ứng dụng có thể yêu cầu chúng. Resource server phải kiểm tra đúng hợp đồng token mà nó chấp nhận, không tự giả định claim bắt buộc luôn có mặt.

## 2. NumericDate được tính bằng giây, không phải mili giây

RFC 7519 định nghĩa NumericDate là số giây kể từ Unix epoch, tức mốc 1970-01-01T00:00:00Z, theo UTC và bỏ qua leap seconds. Giá trị có thể là số nguyên hoặc số có phần thập phân.

Ví dụ minh họa:

~~~json
{
  "iat": 1735689600,
  "nbf": 1735689600,
  "exp": 1735693200
}
~~~

Các giá trị trên là giây Unix. Khoảng cách giữa nbf và exp là 3.600 giây, tức một giờ.

### 2.1. So sánh với đồng hồ hiện tại

Khi triển khai, cần đưa đồng hồ hiện tại về cùng đơn vị giây:

~~~text
now_seconds = current_unix_time_in_milliseconds / 1000
~~~

Sau đó so sánh trực tiếp với NumericDate:

~~~text
if exp exists and now_seconds >= exp + leeway:
    reject_expired_token

if nbf exists and now_seconds + leeway < nbf:
    reject_token_not_yet_valid
~~~

Đoạn pseudocode minh họa cách áp dụng một khoảng leeway nhỏ. Trong thực tế, phải định nghĩa rõ leeway, kiểu số, độ chính xác và quy tắc biên thống nhất giữa các thành phần.

### 2.2. Giây và mili giây khác nhau 1.000 lần

Một thời điểm có thể được biểu diễn như sau:

| Đơn vị | Ví dụ | Ý nghĩa |
| --- | ---: | --- |
| Unix seconds | 1735689600 | Số giây từ epoch |
| Unix milliseconds | 1735689600000 | Số mili giây từ epoch |

Hai con số biểu diễn cùng một thời điểm, nhưng không thể so sánh trực tiếp. Nếu một bên gửi giây còn bên kia hiểu là mili giây, kết quả sẽ lệch rất lớn.

## 3. Lỗi seconds/milliseconds có thể gây ra điều gì?

Lỗi đơn vị thời gian thường xuất hiện khi issuer, gateway và resource service dùng các API thời gian khác nhau. Một số runtime trả thời gian hiện tại bằng mili giây; trong khi JWT NumericDate yêu cầu giây.

### 3.1. Issuer phát hành mili giây nhưng verifier hiểu là giây

Giả sử issuer ghi:

~~~json
{
  "exp": 1735693200000
}
~~~

Issuer đã đưa mili giây vào claim exp. Resource server hiểu đúng quy tắc JWT và coi con số đó là giây kể từ epoch. Giá trị trở thành một thời điểm xa trong tương lai, khiến token có thể được xem như còn hiệu lực trong thời gian cực dài.

Hậu quả:

- Token bị đánh cắp có cửa sổ sử dụng kéo dài bất thường.
- Logout hoặc thu hồi refresh token không tự giải quyết được access JWT đã phát hành.
- Các API có thể chấp nhận token lâu hơn nhiều so với dự kiến của issuer.
- Sự cố có thể khó phát hiện nếu hệ thống chỉ kiểm tra chữ ký và so sánh exp.

### 3.2. Issuer phát hành giây nhưng verifier hiểu là mili giây

Giả sử issuer phát hành đúng:

~~~json
{
  "exp": 1735693200
}
~~~

Nhưng verifier coi giá trị này là mili giây kể từ epoch. Khi chuyển thành thời gian, nó rơi vào khoảng đầu năm 1970, nên token bị coi là đã hết hạn.

Hậu quả:

- Người dùng hợp lệ bị từ chối.
- API trả 401 dù token vẫn còn hạn theo chuẩn.
- Các dịch vụ có cách chuyển đổi khác nhau có thể cho kết quả không nhất quán.
- Nhóm vận hành có thể tìm cách tăng leeway quá lớn để chữa lỗi, vô tình tạo lỗ hổng thời hạn.

### 3.3. Chia hoặc nhân sai ở một phía

Các lỗi khác:

- Issuer chia thời gian milliseconds cho 1.000 hai lần, làm exp rơi gần epoch.
- Verifier nhân NumericDate với 1.000 nhưng lại so với đồng hồ hiện tại tính bằng giây.
- Gateway chuyển exp thành milliseconds, service phía sau lại coi là seconds.
- Một thành phần chuyển số sang chuỗi rồi thành phần khác parse theo quy tắc riêng.

Nguyên tắc là chọn một đơn vị nội bộ rõ ràng, chuyển đổi đúng một lần tại biên và kiểm thử hợp đồng issuer/verifier. Với JWT, giá trị NumericDate trên wire luôn mang đơn vị giây.

## 4. Ngữ nghĩa ranh giới của exp và nbf

Các phép so sánh tại đúng thời điểm biên rất quan trọng. Sai một toán tử có thể kéo dài hiệu lực token hoặc từ chối token quá sớm.

### 4.1. exp: không chấp nhận tại hoặc sau thời điểm hết hạn

RFC 7519 quy định thời điểm hiện tại phải đứng trước exp. Vì vậy:

- Khi now < exp: chưa hết hạn.
- Khi now = exp: đã tới thời điểm hết hạn, phải từ chối.
- Khi now > exp: đã hết hạn, phải từ chối.

Điều kiện không có leeway:

~~~text
valid_exp = now_seconds < exp
~~~

Một lỗi thường gặp là dùng now <= exp. Cách so sánh đó chấp nhận token đúng tại thời điểm exp, trái với ngữ nghĩa “current date/time MUST be before the expiration time”.

### 4.2. nbf: không chấp nhận trước thời điểm bắt đầu

Với nbf:

- Khi now < nbf: token chưa có hiệu lực.
- Khi now = nbf: token đã tới thời điểm bắt đầu và có thể được chấp nhận.
- Khi now > nbf: token đã qua thời điểm bắt đầu.

Điều kiện không có leeway:

~~~text
valid_nbf = now_seconds >= nbf
~~~

Một lỗi là dùng now > nbf, khiến token bị từ chối thêm tại đúng thời điểm bắt đầu.

### 4.3. exp và nbf tạo thành một khoảng hiệu lực

Nếu token có cả hai claim, khoảng thời gian hợp lệ dự kiến là:

~~~text
nbf <= now < exp
~~~

Nếu nbf lớn hơn hoặc bằng exp, token không có khoảng hiệu lực hữu ích. Nên từ chối token có quan hệ thời gian bất hợp lý theo profile thay vì cố diễn giải theo cách riêng.

~~~mermaid
flowchart LR
    A["Trước nbf"] -->|"Chưa hiệu lực"| B["Tại nbf"]
    B --> C["Trong khoảng hiệu lực"]
    C --> D["Tại exp"]
    D -->|"Hết hạn"| E["Sau exp"]
    style A fill:#fee2e2,stroke:#b91c1c,color:#111827
    style B fill:#dcfce7,stroke:#15803d,color:#111827
    style C fill:#dcfce7,stroke:#15803d,color:#111827
    style D fill:#fee2e2,stroke:#b91c1c,color:#111827
    style E fill:#fee2e2,stroke:#b91c1c,color:#111827
~~~

## 5. Bỏ qua exp là lỗi xác minh nghiêm trọng

Nếu resource server không kiểm tra exp, JWT có thể tiếp tục được chấp nhận sau thời điểm issuer dự định kết thúc quyền truy cập.

### 5.1. Các cách bỏ qua exp thường gặp

- Chỉ xác minh chữ ký mà không gọi bước kiểm tra expiration.
- Cấu hình thư viện tắt kiểm tra thời gian.
- Bắt exception expiration rồi tiếp tục xử lý request.
- Khi exp thiếu, tự gán giá trị vô hạn hoặc một thời điểm rất xa.
- Parse exp thất bại nhưng validator coi claim đó là không bắt buộc.
- Gateway kiểm tra exp nhưng service phía sau bỏ qua và nhận token trực tiếp.
- Một nhánh code kiểm tra exp, nhánh khác dành cho API nội bộ lại không kiểm tra.

### 5.2. Kịch bản tấn công

1. Người dùng đăng nhập và nhận access JWT có thời hạn ngắn.
2. Kẻ tấn công lấy được token từ browser storage, log hoặc thiết bị.
3. Token hết hạn theo exp.
4. Resource server chỉ kiểm tra chữ ký hoặc bỏ qua lỗi expiration.
5. Kẻ tấn công tiếp tục gọi API bằng token đã hết hạn.

Chữ ký vẫn hợp lệ vì token chưa bị sửa. Chỉ có thời hạn sử dụng đã kết thúc. Nếu API không kiểm tra exp, token vẫn được chấp nhận.

### 5.3. exp có bắt buộc trong mọi JWT không?

Trong JWT tổng quát, exp là claim tùy chọn. Nhưng profile ứng dụng có thể bắt buộc exp. Ví dụ, JWT Profile for OAuth 2.0 Access Tokens (RFC 9068) yêu cầu access token theo profile phải có exp.

Resource server cần phân biệt:

- JWT tổng quát mà hợp đồng cho phép không có exp.
- Access token profile yêu cầu exp.
- Token nội bộ có quy định thời hạn riêng.

Nếu API chỉ chấp nhận access token có thời hạn, hãy từ chối token thiếu exp. Không mặc định token không có exp là “không hết hạn”.

## 6. Bỏ qua nbf hoặc xử lý sai nbf

nbf ngăn token được sử dụng trước một thời điểm xác định. Claim này hữu ích khi token được tạo trước nhưng chỉ được phép sử dụng từ một thời điểm trong tương lai, hoặc khi hệ thống cần kiểm soát thời gian bắt đầu hiệu lực.

### 6.1. Bỏ qua nbf

Nếu verifier bỏ qua nbf, token có thể được sử dụng sớm hơn thời điểm issuer dự định. Điều này có thể gây:

- Quyền truy cập được kích hoạt trước lịch.
- Token được phát hành cho một đợt triển khai tương lai bị sử dụng sớm.
- Token được tạo trước thời điểm chuyển giao quyền có hiệu lực ngay lập tức.
- Các service không thống nhất về thời điểm bắt đầu chấp nhận token.

### 6.2. Nhầm đơn vị hoặc đảo điều kiện nbf

Các lỗi phổ biến:

- So sánh milliseconds hiện tại với nbf tính bằng seconds.
- Dùng now > nbf và từ chối tại đúng thời điểm nbf.
- Dùng now + leeway < nbf nhưng leeway quá lớn, khiến token được chấp nhận quá sớm.
- Coi nbf là thời điểm hết hạn và so sánh theo chiều ngược.
- Bỏ qua nbf khi claim có kiểu sai hoặc parse thất bại.

### 6.3. nbf không thay thế exp

Token có nbf nhưng không có exp có thể bắt đầu hiệu lực mà không có thời điểm kết thúc. Nếu profile yêu cầu token ngắn hạn, phải yêu cầu exp riêng. Không suy ra exp từ nbf hoặc từ thời gian phát hành nếu hợp đồng không định nghĩa rõ.

## 7. iat: thời điểm phát hành không phải thời điểm hết hạn

iat ghi nhận thời điểm JWT được phát hành. Claim này hữu ích cho audit, phát hiện token có thời gian phát hành nằm trong tương lai và áp dụng giới hạn tuổi token.

Tuy nhiên, iat không tự thay thế exp:

- Token có iat nhưng không có exp vẫn không có giới hạn hết hạn từ claim exp.
- Token có exp nhưng không có iat vẫn có thể được xác minh nếu profile không yêu cầu iat.
- Chỉ kiểm tra iat không chứng minh token còn trong thời hạn sử dụng.

### 7.1. Kiểm tra iat trong tương lai

Một token có iat nằm quá xa trong tương lai có thể chỉ ra:

- Đồng hồ issuer sai.
- Token được tạo sai.
- Một thành phần đang dùng sai đơn vị thời gian.
- Token giả hoặc dữ liệu bị tạo có chủ đích.

JWT tổng quát định nghĩa iat là NumericDate nhưng không tự áp đặt một quy tắc từ chối mọi iat tương lai cho mọi ứng dụng. Profile có thể quy định iat không được vượt quá thời gian hiện tại cộng leeway.

Ví dụ policy:

~~~text
if iat exists and iat > now_seconds + allowed_clock_skew:
    reject_future_issued_at
~~~

### 7.2. Giới hạn tuổi token bằng iat

Một ứng dụng có thể yêu cầu token không quá cũ:

~~~text
token_age = now_seconds - iat

if token_age > maximum_token_age + allowed_clock_skew:
    reject_token_too_old
~~~

Đây là policy bổ sung, không phải ý nghĩa mặc định của claim iat. Nếu áp dụng, phải quy định cách xử lý iat thiếu, iat trong tương lai và clock skew.

## 8. Clock skew giữa issuer, gateway và resource server

Ngay cả khi mọi thành phần dùng đúng đơn vị seconds, đồng hồ hệ thống vẫn có thể lệch nhau. Ví dụ:

- Issuer nhanh hơn resource server 90 giây.
- Gateway chậm hơn resource server 40 giây.
- Một node trong cluster chưa đồng bộ NTP.
- Container/VM bị suspend hoặc resume với đồng hồ không cập nhật đúng.
- Một node vừa được triển khai có cấu hình timezone hoặc thời gian sai.

### 8.1. Đồng hồ nhanh và chậm gây hậu quả khác nhau

| Đồng hồ verifier | Ảnh hưởng tới exp | Ảnh hưởng tới nbf |
| --- | --- | --- |
| Nhanh hơn thực tế | Có thể từ chối token sớm | Có thể chấp nhận token trước thời điểm thực tế |
| Chậm hơn thực tế | Có thể chấp nhận token hết hạn lâu hơn | Có thể từ chối token lâu hơn dù đã tới thời điểm hiệu lực |

Clock skew không chỉ gây lỗi trải nghiệm. Đồng hồ verifier chậm có thể kéo dài thời gian chấp nhận bearer token đã hết hạn; đồng hồ nhanh có thể làm token được chấp nhận sớm hơn nbf nếu logic cho phép leeway.

### 8.2. Dùng UTC/Unix time, không dùng giờ địa phương

NumericDate dựa trên Unix epoch, không phải giờ địa phương. Không cộng hoặc trừ timezone offset khi so sánh exp/nbf.

Ví dụ sai:

- Lấy giờ địa phương UTC+7 rồi coi đó là Unix seconds.
- Parse một chuỗi ngày không có timezone và mặc định theo timezone của máy.
- Áp dụng daylight saving time vào NumericDate.
- Chuyển timestamp sang chuỗi ngày rồi parse lại ở timezone khác.

Hãy dùng clock API cung cấp Unix epoch time và giữ cùng một quy ước ở mọi service.

### 8.3. Đồng bộ thời gian

Vận hành an toàn cần:

- Đồng bộ máy chủ qua nguồn thời gian tin cậy, thường dùng NTP hoặc dịch vụ thời gian được quản trị.
- Giám sát clock offset của node và cảnh báo khi vượt ngưỡng.
- Kiểm tra thời gian sau khi VM/container resume hoặc node thay thế.
- Không để mỗi service tự đặt timezone hoặc quy tắc thời gian riêng.
- Ghi nhận timestamp audit theo UTC.
- Kiểm thử hành vi khi clock nhảy tiến/lùi hoặc mất đồng bộ.

Đồng hồ monotonic phù hợp đo khoảng thời gian trong process, nhưng NumericDate là thời gian tuyệt đối theo epoch. Không so sánh trực tiếp monotonic clock với exp/nbf. Có thể dùng wall clock để kiểm tra thời điểm token, rồi dùng monotonic clock cho timeout/duration trong cùng một tiến trình.

## 9. Leeway: xử lý lệch đồng hồ có giới hạn

RFC 7519 cho phép một khoảng leeway nhỏ để bù clock skew khi xử lý exp và nbf. Leeway giúp các node có sai lệch nhỏ không từ chối token hợp lệ chỉ vì chênh lệch thời gian.

### 9.1. Leeway thay đổi ranh giới như thế nào?

Không có leeway:

~~~text
exp valid when now < exp
nbf valid when now >= nbf
~~~

Với leeway L:

~~~text
exp valid when now < exp + L
nbf valid when now + L >= nbf
~~~

Leeway có thể làm token được chấp nhận muộn hơn exp hoặc sớm hơn nbf. Vì vậy, leeway càng lớn thì cửa sổ sử dụng token ngoài khoảng thời gian danh nghĩa càng rộng.

### 9.2. Không dùng leeway lớn để che lỗi đơn vị

Nếu token bị sai seconds/milliseconds, tăng leeway không thể sửa đúng hợp đồng. Nó chỉ làm các quyết định thời gian khó dự đoán hơn và có thể tạo cửa sổ chấp nhận quá rộng.

Không dùng leeway để bù:

- Clock offset hàng giờ hoặc hàng ngày.
- Issuer phát hành milliseconds thay vì seconds.
- Verifier parse sai kiểu dữ liệu.
- Node chưa đồng bộ thời gian.
- Một service dùng local time, service khác dùng UTC.

Hãy sửa nguồn lệch và dùng leeway nhỏ, có giới hạn, được thống nhất giữa các resource server.

### 9.3. Định nghĩa leeway tập trung

Một profile cần quy định:

- Giá trị leeway tối đa.
- Leeway áp dụng cho exp, nbf và iat hay chỉ một số claim.
- Có khác biệt theo loại token hay không.
- Cách cấu hình giống nhau giữa gateway và resource service.
- Ai được phép thay đổi và cách audit.
- Cách đo clock skew để điều chỉnh leeway.

Không cho client hoặc token tự yêu cầu leeway lớn hơn policy.

## 10. Kiểu dữ liệu, precision và giá trị bất thường

NumericDate là JSON number. Không nên âm thầm chấp nhận mọi kiểu có thể chuyển thành số.

### 10.1. Không tự ép string thành number

Các payload sau không tương đương theo kiểu JSON:

~~~json
{
  "exp": 1735693200
}
~~~

~~~json
{
  "exp": "1735693200"
}
~~~

Ví dụ thứ hai là string, không phải NumericDate number. Nếu một service tự parse string trong khi service khác từ chối, chúng có thể bất đồng về thời hạn token.

### 10.2. Từ chối giá trị không phải JSON number hợp lệ

Các trường hợp cần từ chối theo schema:

- exp là null.
- nbf là boolean hoặc string.
- iat là array/object.
- JSON chứa NaN hoặc Infinity, vốn không phải JSON number hợp lệ theo RFC 8259.
- Giá trị vượt miền số mà runtime hoặc profile hỗ trợ.
- Số bị làm tròn khiến ranh giới thời gian không còn chính xác.

### 10.3. Precision và overflow

Một số runtime biểu diễn number bằng floating-point có độ chính xác hữu hạn. Một số khác có integer range giới hạn. Giá trị timestamp quá lớn có thể:

- Bị làm tròn.
- Tràn số.
- Chuyển thành infinity.
- Bị cắt phần thập phân.
- Chuyển sang kiểu signed/unsigned khác nhau.

Đặt miền NumericDate hợp lý cho hệ thống, kiểm tra finite/range và tránh giá trị cực lớn. Không cần chấp nhận timestamp xa hàng nghìn năm trong tương lai cho access token thông thường.

### 10.4. Fractional NumericDate

RFC 7519 cho phép NumericDate có phần thập phân. Nếu hệ thống hỗ trợ fractional seconds, tất cả thành phần phải có quy tắc precision nhất quán. Nếu profile nội bộ chỉ cho phép số nguyên giây, có thể từ chối giá trị thập phân theo profile đó; không tự làm tròn theo cách khác nhau giữa các service.

## 11. Claim thời gian bị thiếu hoặc có quan hệ bất hợp lý

Không được tự động diễn giải claim thiếu như một thời hạn vô hạn.

| Trường hợp | Rủi ro | Chính sách gợi ý |
| --- | --- | --- |
| Thiếu exp trong profile yêu cầu exp | Token không có giới hạn hết hạn | Từ chối |
| exp là null | Không có NumericDate hợp lệ | Từ chối |
| Thiếu nbf | Có thể hợp lệ nếu profile không yêu cầu | Áp dụng đúng schema |
| nbf lớn hơn exp | Không có khoảng hiệu lực hợp lý | Từ chối |
| iat lớn hơn exp | Thời điểm phát hành sau thời điểm hết hạn | Từ chối theo profile |
| iat quá xa trong tương lai | Đồng hồ sai hoặc token bất thường | Từ chối theo policy |
| exp ở quá xa tương lai | Token có thể sống quá lâu do lỗi đơn vị | Giới hạn maximum lifetime |
| exp âm hoặc ngoài miền hỗ trợ | Timestamp bất thường | Từ chối theo schema |

JWT tổng quát không quy định mọi quan hệ giữa exp, nbf và iat thành một bộ quy tắc bắt buộc cho mọi ứng dụng. Profile access token cần định nghĩa các ràng buộc bổ sung phù hợp với mô hình của mình.

### 11.1. Giới hạn maximum lifetime

Ngoài kiểm tra exp hợp lệ, hệ thống có thể giới hạn:

~~~text
if exp - iat > maximum_access_token_lifetime:
    reject_token_lifetime_too_long
~~~

Điều kiện này chỉ áp dụng khi profile yêu cầu cả exp và iat, đồng thời định nghĩa maximum lifetime. Nó giúp phát hiện token có exp bị đẩy quá xa do lỗi đơn vị hoặc lỗi phát hành.

Không nên chỉ dựa vào giới hạn lifetime để thay thế kiểm tra exp. Cả hai đều cần được xác minh.

## 12. Sai lệch giữa gateway và resource server

Một kiến trúc có thể kiểm tra JWT ở gateway rồi forward token tới service. Nếu hai nơi dùng đơn vị hoặc leeway khác nhau, cùng một token có thể được gateway chấp nhận nhưng service từ chối, hoặc ngược lại.

Ví dụ:

| Thành phần | Cấu hình sai | Hậu quả |
| --- | --- | --- |
| Gateway | Đọc exp theo seconds | Từ chối token đã hết hạn |
| Resource API | Đọc exp theo milliseconds | Cũng có thể từ chối token còn hạn |
| Gateway | Kiểm tra exp đầy đủ | Chặn token hết hạn |
| Resource API | Bỏ qua exp trên direct route | Token hết hạn vẫn được chấp nhận nếu đi đường khác |
| Gateway | Leeway 30 giây | Chấp nhận trong cửa sổ ngắn |
| Resource API | Leeway 10 phút | Chấp nhận token muộn hơn nhiều |

Các biện pháp:

- Chuẩn hóa một token profile dùng chung.
- Dùng cùng quy tắc NumericDate và kiểu dữ liệu.
- Quy định leeway tập trung.
- Không có route bỏ qua validation.
- Kiểm thử cùng một bộ token tại gateway và mọi resource server.
- Giám sát chênh lệch thời gian và kết quả xác minh theo service.

## 13. Cache có thể kéo dài việc chấp nhận token

Một số hệ thống cache kết quả xác minh hoặc authorization decision để giảm tải. Nếu cache entry còn hiệu lực lâu hơn exp, token đã hết hạn vẫn có thể được chấp nhận dựa trên kết quả cache cũ.

Nguyên tắc:

- Không đặt TTL cache vượt quá thời gian còn lại tới exp.
- Khi có leeway, tính TTL theo đúng chính sách leeway.
- Cache authorization decision cần tính thêm thay đổi quyền và trạng thái session.
- Không cache kết quả active của introspection lâu hơn SLA thu hồi.
- Dùng cùng clock basis khi tính cache expiration.
- Kiểm tra cache sau khi token hết hạn tại thời điểm biên.

Ví dụ:

~~~text
remaining_lifetime = exp - now_seconds
cache_ttl = min(configured_cache_ttl, max(0, remaining_lifetime))
~~~

Đây là cách minh họa; TTL thực tế cần tính leeway, revocation state và policy cache của ứng dụng. Không để cache khiến token sống lâu hơn thời hạn được chấp nhận.

## 14. Quy trình xác minh thời gian an toàn

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Xác minh chữ ký và token profile"]
    B --> C["Parse claims bằng JSON parser nghiêm ngặt"]
    C --> D{"exp/nbf/iat đúng kiểu NumericDate?"}
    D -- "Không" --> X["Từ chối"]
    D -- "Có" --> E["Lấy UTC Unix time theo giây"]
    E --> F["Kiểm tra miền số và maximum lifetime"]
    F --> G{"exp tồn tại nếu profile yêu cầu?"}
    G -- "Không" --> X
    G -- "Có" --> H["Kiểm tra now < exp + leeway"]
    H --> I{"nbf tồn tại?"}
    I -- "Có" --> J["Kiểm tra now + leeway >= nbf"]
    I -- "Không" --> K["Tiếp tục theo profile"]
    J --> L{"Các kiểm tra thời gian hợp lệ?"}
    K --> L
    L -- "Không" --> X
    L -- "Có" --> M["Tiếp tục kiểm tra issuer, audience và quyền"]
~~~

Một thứ tự triển khai thực tế có thể khác nhau tùy thư viện và profile, nhưng mọi claim thời gian phải được kiểm tra trước khi token được dùng để cấp quyền.

### 14.1. Pseudocode tổng quát

~~~text
function validate_time_claims(claims, profile, clock):
    now = clock.unix_time_seconds()
    leeway = profile.allowed_clock_skew_seconds

    require(now is finite)
    require(leeway >= 0 and leeway <= profile.maximum_leeway)

    if profile.require_exp:
        require(claims contains exp)

    if claims contains exp:
        require(exp is a valid JSON number)
        require(exp is finite and within supported range)
        require(now < exp + leeway)

    if claims contains nbf:
        require(nbf is a valid JSON number)
        require(nbf is finite and within supported range)
        require(now + leeway >= nbf)

    if profile.require_iat:
        require(claims contains iat)

    if claims contains iat:
        require(iat is a valid JSON number)
        require(iat is finite and within supported range)
        require(iat <= now + leeway)

    if profile.maximum_token_lifetime exists:
        require(exp exists and iat exists)
        require(exp >= iat)
        require(exp - iat <= profile.maximum_token_lifetime)

    if nbf exists and exp exists:
        require(nbf < exp)

    return valid
~~~

Đây là pseudocode minh họa policy nghiêm ngặt. Các điều kiện require_iat, maximum_token_lifetime và quan hệ giữa các claim là lựa chọn của profile, không phải mọi điều kiện đều là MUST của JWT tổng quát.

## 15. Tình huống tấn công và lỗi thực tế

### Tình huống A — Token sống lâu vì milliseconds bị hiểu là seconds

Issuer dùng clock API trả về milliseconds và ghi thẳng vào exp. Resource server hiểu đúng NumericDate theo seconds nên coi exp ở tương lai rất xa.

**Bài học:** xác minh đơn vị tại issuer và verifier; giới hạn maximum token lifetime.

### Tình huống B — Token hợp lệ bị từ chối vì seconds bị hiểu là milliseconds

Issuer phát hành exp theo giây. Gateway chuyển giá trị thành thời gian milliseconds và thấy nó thuộc năm 1970.

**Bài học:** chuyển đổi đúng một lần; dùng cùng đơn vị trong mọi phép so sánh.

### Tình huống C — API bỏ qua expiration exception

Thư viện xác minh phát hiện token hết hạn nhưng middleware bắt lỗi rồi tiếp tục xử lý request để tránh gián đoạn.

**Bài học:** lỗi expiration phải làm validation thất bại. Không được fail-open cho access token hết hạn.

### Tình huống D — now bằng exp nhưng token vẫn được chấp nhận

Verifier dùng điều kiện now <= exp. Tại đúng thời điểm exp, token vẫn được chấp nhận.

**Bài học:** nếu không có leeway, current time phải nhỏ hơn exp; tại hoặc sau exp thì từ chối.

### Tình huống E — nbf bị bỏ qua

Issuer phát hành token có nbf là 12:00 để quyền chỉ bắt đầu sau khi một hợp đồng có hiệu lực. API không kiểm tra nbf và chấp nhận token lúc 11:30.

**Bài học:** kiểm tra nbf khi claim có mặt; profile phải thống nhất cách xử lý.

### Tình huống F — Leeway quá lớn

Một nhóm vận hành đặt leeway 24 giờ để bù một node lệch đồng hồ. Token hết hạn vẫn được chấp nhận trong khoảng thời gian dài.

**Bài học:** sửa đồng hồ; leeway phải nhỏ, có giới hạn và theo dõi được.

### Tình huống G — Gateway và service dùng leeway khác nhau

Gateway chấp nhận token thêm 30 giây, resource service chấp nhận thêm 10 phút. Một token hết hạn có thể bị chặn trên một route nhưng được chấp nhận trên route khác.

**Bài học:** chuẩn hóa time validation policy và kiểm thử xuyên dịch vụ.

### Tình huống H — exp thiếu bị coi là vô hạn

Một access token profile yêu cầu exp nhưng validator chỉ kiểm tra nếu claim tồn tại. Token thiếu exp vẫn được chấp nhận.

**Bài học:** kiểm tra required claims theo profile; thiếu exp phải từ chối khi hợp đồng yêu cầu.

## 16. Checklist phòng chống lỗi thời gian JWT

### NumericDate và đơn vị

- [ ] Issuer phát hành exp, nbf và iat theo Unix seconds.
- [ ] Verifier so sánh bằng cùng đơn vị seconds.
- [ ] Chuyển đổi milliseconds sang seconds đúng một lần tại biên.
- [ ] Không dùng giờ địa phương hoặc timezone offset để so sánh NumericDate.
- [ ] Kiểm tra JSON number, finite value và miền số hỗ trợ.
- [ ] Không tự ép string, null hoặc boolean thành NumericDate.
- [ ] Giới hạn maximum lifetime hợp lý cho access token.

### Ngữ nghĩa claim

- [ ] Từ chối token tại hoặc sau exp theo quy tắc profile.
- [ ] Từ chối token trước nbf theo quy tắc profile.
- [ ] Kiểm tra exp bắt buộc nếu access token profile yêu cầu.
- [ ] Không coi iat là thay thế exp.
- [ ] Kiểm tra iat tương lai hoặc maximum age nếu profile quy định.
- [ ] Từ chối quan hệ thời gian bất hợp lý như nbf >= exp khi profile không cho phép.

### Clock và leeway

- [ ] Máy chủ được đồng bộ thời gian bằng nguồn tin cậy.
- [ ] Có giám sát clock offset giữa issuer, gateway và resource server.
- [ ] Leeway nhỏ, có giới hạn và được cấu hình thống nhất.
- [ ] Không dùng leeway để che lỗi seconds/milliseconds hoặc clock drift lớn.
- [ ] Kiểm thử khi clock nhanh, chậm, nhảy tiến và nhảy lùi.

### Hạ tầng và kiểm thử

- [ ] Gateway và mọi resource server đều thực hiện time validation.
- [ ] Cache không kéo dài thời hạn chấp nhận vượt policy.
- [ ] Không bắt expiration error rồi tiếp tục xử lý.
- [ ] Có test tại thời điểm trước, đúng và sau exp/nbf.
- [ ] Có test seconds/milliseconds theo cả hai chiều.
- [ ] Có test missing claim, wrong type, overflow, fractional value và future iat.
- [ ] Có test cùng corpus trên tất cả service và runtime.

## 17. Ma trận kiểm thử thời gian

| Đầu vào/kịch bản | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| exp còn ở tương lai | now < exp | Chấp nhận nếu các kiểm tra khác hợp lệ |
| now đúng bằng exp | now = exp, leeway = 0 | Từ chối |
| exp đã qua | now > exp | Từ chối |
| exp còn trong leeway | exp <= now < exp + leeway | Có thể chấp nhận theo policy leeway đã công bố |
| nbf ở tương lai ngoài leeway | now + leeway < nbf | Từ chối |
| now đúng bằng nbf | now = nbf | Chấp nhận theo ngữ nghĩa nbf |
| exp được gửi bằng milliseconds | Verifier mong NumericDate seconds | Từ chối do maximum lifetime/range hoặc contract validation |
| exp bằng seconds nhưng parser coi milliseconds | Đơn vị không khớp | Test phải phát hiện; verifier đúng phải dùng seconds |
| exp là string | Kiểu sai | Từ chối |
| exp là null | Kiểu sai | Từ chối |
| exp là Infinity/NaN | JSON không hợp lệ | Từ chối |
| exp vượt miền số hỗ trợ | Overflow/range | Từ chối |
| iat trong tương lai vượt leeway | Policy future-iat | Từ chối |
| iat quá cũ | Maximum age được cấu hình | Từ chối theo policy |
| Thiếu exp trong profile bắt buộc | Required claim missing | Từ chối |
| nbf >= exp | Không có khoảng hiệu lực hợp lệ | Từ chối theo profile |
| Gateway và service có leeway khác nhau | Cùng một token | Kiểm thử phát hiện cấu hình không thống nhất |
| Cache còn active sau exp | Cache TTL vượt thời gian còn lại | Kiểm thử phải thất bại |

## 18. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| NumericDate của JWT dùng seconds hay milliseconds? | **Seconds** kể từ Unix epoch. |
| Tại đúng thời điểm exp, token có còn hợp lệ không? | **Không** nếu không có leeway; current time phải đứng trước exp. |
| Tại đúng thời điểm nbf, token đã được phép sử dụng chưa? | **Có**, current time đã bằng nbf. |
| iat có thay thế exp không? | **Không.** iat ghi thời điểm phát hành, không tự đặt thời điểm hết hạn. |
| JWT tổng quát có luôn bắt buộc exp không? | **Không.** Nhưng profile access token có thể bắt buộc, ví dụ RFC 9068. |
| Nếu issuer ghi milliseconds vào exp nhưng verifier hiểu seconds thì điều gì xảy ra? | Token có thể bị coi là hết hạn ở một thời điểm rất xa trong tương lai. |
| Nếu issuer ghi seconds nhưng verifier hiểu milliseconds thì sao? | Token có thể bị coi là hết hạn từ khoảng năm 1970. |
| Leeway lớn có sửa được lỗi đơn vị không? | **Không.** Phải sửa chuyển đổi thời gian và đồng hồ. |
| Đồng hồ verifier chậm có thể gây rủi ro gì? | Có thể tiếp tục chấp nhận token sau exp lâu hơn dự kiến. |
| Có nên coi exp thiếu là không hết hạn không? | **Không** khi profile yêu cầu exp; phải từ chối token thiếu claim. |

## 19. Ghi nhớ

- exp là thời điểm hết hạn; tại hoặc sau exp, token không còn được chấp nhận theo quy tắc thời gian.
- nbf là thời điểm bắt đầu hiệu lực; tại nbf token đã có thể được chấp nhận.
- iat ghi thời điểm phát hành, không thay thế exp; kiểm tra future iat hoặc maximum age là policy của profile.
- NumericDate dùng Unix seconds, không phải milliseconds và không phụ thuộc timezone địa phương.
- Lỗi milliseconds bị hiểu là seconds có thể làm token sống lâu bất thường; lỗi ngược lại có thể làm token bị từ chối ngay.
- Không bỏ qua exp/nbf, không fail-open khi parse hoặc validation thời gian thất bại.
- Clock skew cần được giám sát; leeway chỉ nên nhỏ và có giới hạn.
- Kiểu dữ liệu, precision, overflow, missing claims và quan hệ thời gian phải được kiểm tra theo schema.
- Gateway, resource server và cache phải áp dụng cùng chính sách thời gian.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT), Section 2: NumericDate](https://www.rfc-editor.org/rfc/rfc7519#section-2)
- [RFC 7519 – JWT Registered Claim Names, Section 4.1.4–4.1.6](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.4)
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8259 – The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)
- [RFC 5905 – Network Time Protocol Version 4](https://www.rfc-editor.org/rfc/rfc5905)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP API Security Top 10](https://owasp.org/API-Security/)
