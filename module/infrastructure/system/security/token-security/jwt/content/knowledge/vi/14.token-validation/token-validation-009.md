# Kiểm tra exp, nbf, iat theo chính sách thời gian

## 1. Vì sao thời gian là một phần của xác minh JWT?

JWT thường được phát hành để sử dụng trong một khoảng thời gian nhất định. Chữ ký hợp lệ chứng minh dữ liệu token khớp với khóa ký, nhưng không chứng minh token vẫn còn hiệu lực ở thời điểm request đến. Một token đã hết hạn vẫn có thể có chữ ký hoàn toàn chính xác.

Ba claims thời gian thường gặp trong JWT:

- **exp (Expiration Time):** thời điểm token hết hạn; token không được chấp nhận tại hoặc sau thời điểm này, có thể áp dụng một khoảng dung sai nhỏ theo chính sách.
- **nbf (Not Before):** thời điểm token bắt đầu có hiệu lực; token không được chấp nhận trước thời điểm này, có thể áp dụng dung sai nhỏ.
- **iat (Issued At):** thời điểm token được phát hành; có thể dùng để kiểm tra tính hợp lý của thời điểm phát hành và giới hạn tuổi token.

Các claims này dùng kiểu **NumericDate**, tính bằng giây kể từ Unix epoch theo RFC 7519. Chúng không phải chuỗi ngày giờ tùy ý và không mặc định là mili giây.

Điều quan trọng là phân biệt quy tắc của chuẩn JWT với chính sách ứng dụng. RFC 7519 định nghĩa ý nghĩa và cách xử lý khi các claim xuất hiện; token profile hoặc hợp đồng ứng dụng quyết định claim nào bắt buộc, thời lượng sống tối đa, clock skew và các ràng buộc bổ sung. Không phải mọi JWT đều bắt buộc có cả exp, nbf và iat.

Nội dung này thuộc Security - JSON Web Token (JWT), áp dụng chung cho mọi ngôn ngữ và nền tảng, không phụ thuộc Java hoặc Spring Security.

## 2. NumericDate: biểu diễn thời gian trong JWT

RFC 7519 định nghĩa NumericDate là một giá trị số biểu diễn số giây từ **1970-01-01T00:00:00Z** đến thời điểm được chỉ định, không tính giây nhuận. Giá trị có thể là số nguyên hoặc số có phần thập phân.

Ví dụ minh họa:

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Các giá trị trên tương ứng một khoảng thời gian 15 phút kể từ thời điểm phát hành. Đây chỉ là dữ liệu minh họa; hệ thống phải tính theo đồng hồ thực tế và policy của mình.

### 2.1. Giây, không phải mili giây

Một lỗi phổ biến là lấy Unix timestamp tính bằng mili giây rồi ghi trực tiếp vào JWT. Ví dụ:

| Biểu diễn | Giá trị ví dụ | Ý nghĩa |
| --- | ---: | --- |
| Unix time theo giây | 1893456000 | NumericDate thường dùng trong JWT |
| Unix time theo mili giây | 1893456000000 | Không phải đơn vị NumericDate theo RFC 7519 |

Nếu bên phát hành ghi mili giây nhưng bên nhận hiểu là giây, token có thể được coi là còn hiệu lực trong hàng chục nghìn năm. Nếu bên phát hành ghi giây nhưng bên nhận hiểu là mili giây, token có thể bị coi là hết hạn gần như ngay lập tức.

Hai phía phải thống nhất đơn vị theo chuẩn và profile. Không tự đoán đơn vị dựa trên số chữ số.

### 2.2. Số thập phân và độ chính xác

NumericDate có thể có phần lẻ. Ví dụ:

~~~json
{
  "exp": 1893456000.5
}
~~~

Không được tự động làm tròn theo cách khiến token được chấp nhận lâu hơn policy. Bộ xác minh cần dùng kiểu số và phép so sánh đủ chính xác, kiểm tra tràn số và tránh mất độ chính xác khi chuyển đổi giữa các biểu diễn.

Nếu profile của hệ thống quy định timestamp nguyên giây, phải áp dụng quy tắc đó một cách nhất quán ở cả bên phát hành và bên nhận. Đừng tự áp đặt quy tắc số nguyên cho mọi JWT nếu profile không yêu cầu.

### 2.3. Kiểm tra kiểu dữ liệu

Claims exp, nbf và iat phải được biểu diễn bằng JSON number theo NumericDate. Các giá trị sau không hợp lệ theo kiểu dữ liệu của claim:

~~~json
{
  "exp": "1893456000",
  "nbf": true,
  "iat": {"seconds": 1893456000}
}
~~~

Không ép chuỗi thành số, boolean thành số hoặc object thành thời gian. Việc ép kiểu dễ khiến các thành phần trong hệ thống diễn giải cùng một token khác nhau.

Ngoài kiểu dữ liệu, cần kiểm tra giá trị có nằm trong miền số mà hệ thống hỗ trợ hay không. Từ chối NaN, Infinity, giá trị gây tràn khi đổi đơn vị hoặc tính toán, và các giá trị ngoài phạm vi profile. JSON chuẩn không có literal NaN/Infinity; parser nghiêm ngặt vẫn cần bảo đảm không tạo ra giá trị không hữu hạn qua bước chuyển đổi.

## 3. Kiểm tra expiration time (exp)

Claim **exp** chỉ thời điểm sau đó token không còn được chấp nhận. Theo RFC 7519, nếu exp có mặt, token không được chấp nhận tại hoặc sau thời điểm hết hạn.

Không có clock skew:

~~~text
accept_exp = now < exp
reject_exp = now >= exp
~~~

Ví dụ token có exp là 12:00:00 UTC:

| Thời điểm kiểm tra | Kết quả khi không có leeway |
| --- | --- |
| 11:59:59 UTC | Chưa hết hạn |
| 12:00:00 UTC | Đã hết hạn |
| 12:00:01 UTC | Đã hết hạn |

So sánh tại ranh giới phải nhất quán. Không dùng phép kiểm tra chỉ so ngày hoặc chỉ so phút; phải so timestamp đầy đủ với độ chính xác mà policy và NumericDate hỗ trợ.

### 3.1. exp là điều kiện thời gian, không phải thời hạn duy nhất

exp xác định thời điểm kết thúc hiệu lực, nhưng một policy có thể đặt thêm giới hạn:

- Thời lượng sống tối đa của token, tính từ iat.
- Thời gian tối đa kể từ lần xác thực người dùng.
- Giới hạn riêng theo loại token hoặc mức độ nhạy cảm của tài nguyên.
- Thời điểm kết thúc phiên hoặc trạng thái tài khoản được quản lý ngoài JWT.

Ví dụ, token có exp còn 24 giờ nhưng policy chỉ cho phép access token sống tối đa 15 phút kể từ iat thì token vẫn phải bị từ chối nếu vượt giới hạn tuổi.

### 3.2. exp không tự cung cấp cơ chế thu hồi

Một JWT đã phát hành thường không thể bị sửa exp mà vẫn giữ chữ ký hợp lệ. Tuy nhiên, việc chờ tới exp mới hết hiệu lực có thể không phù hợp khi người dùng đăng xuất, tài khoản bị khóa hoặc khóa ký bị lộ.

Nếu cần thu hồi sớm, hệ thống phải có cơ chế bổ sung như trạng thái phiên, denylist jti, introspection hoặc vô hiệu hóa khóa theo policy. Kiểm tra exp một mình không đảm bảo token chưa bị thu hồi.

## 4. Kiểm tra not-before time (nbf)

Claim **nbf** chỉ thời điểm trước đó token chưa được phép sử dụng. Nếu nbf có mặt, bên nhận không được chấp nhận token trước thời điểm này.

Không có clock skew:

~~~text
accept_nbf = now >= nbf
reject_nbf = now < nbf
~~~

Ví dụ token được phát hành trước nhưng chỉ có hiệu lực từ 12:05:00 UTC:

| Thời điểm kiểm tra | Kết quả khi không có leeway |
| --- | --- |
| 12:04:59 UTC | Chưa có hiệu lực |
| 12:05:00 UTC | Bắt đầu có hiệu lực |
| 12:05:01 UTC | Có hiệu lực |

nbf hữu ích khi token cần được phát hành trước thời điểm sử dụng, chẳng hạn credential được chuẩn bị cho một cửa sổ triển khai hoặc một nhiệm vụ đã lên lịch. Tuy nhiên, việc sử dụng nbf cần được cân nhắc vì đồng hồ bên phát hành và bên nhận có thể lệch nhau.

### 4.1. Quan hệ giữa nbf và exp

Nếu cả hai claim xuất hiện, policy nên yêu cầu khoảng hiệu lực có ý nghĩa:

~~~text
nbf < exp
~~~

Nếu nbf bằng hoặc sau exp, không tồn tại khoảng thời gian token có thể được sử dụng theo cách thông thường. Nên từ chối token có quan hệ thời gian mâu thuẫn, trừ khi một profile đặc biệt định nghĩa rõ cách diễn giải khác.

Không suy ra nbf từ iat hoặc exp nếu issuer không phát hành claim đó và profile không định nghĩa phép suy luận.

## 5. Kiểm tra issued-at time (iat)

Claim **iat** cho biết thời điểm token được phát hành. Khác với exp và nbf, iat không tự định nghĩa thời điểm token hết hạn hoặc bắt đầu có hiệu lực. Nó thường được dùng để kiểm tra tính hợp lý của token và thực thi giới hạn tuổi tối đa theo policy.

### 5.1. Phát hiện iat nằm trong tương lai

Nếu iat nằm quá xa trong tương lai so với đồng hồ hiện tại, có thể có:

- Đồng hồ bên phát hành bị cấu hình sai.
- Đồng hồ bên nhận bị lệch.
- Token được tạo với dữ liệu thời gian giả mạo hoặc bất thường.
- Lỗi chuyển đổi đơn vị hoặc độ chính xác timestamp.

Policy có thể cho phép một sai số nhỏ, nhưng phải có giới hạn:

~~~text
require iat <= now + allowedClockSkew
~~~

Nếu iat vượt ranh giới này, từ chối token. Không chấp nhận một iat tương lai tùy ý chỉ vì exp vẫn nằm trong tương lai.

### 5.2. Giới hạn tuổi token bằng iat

Nếu policy quy định tuổi tối đa **maxTokenAge**, kiểm tra:

~~~text
token_age = now - iat
require token_age <= maxTokenAge + applicableLeeway
~~~

Việc cộng leeway vào max age cần được quy định rõ trong policy; một hệ thống có thể chọn không cộng hoặc áp dụng dung sai riêng. Không được để mỗi endpoint tự hiểu khác nhau.

Ví dụ:

| Policy | Giá trị |
| --- | ---: |
| maxTokenAge | 900 giây |
| clock skew | 60 giây |
| iat | 10:00:00 UTC |
| now | 10:15:30 UTC |

Tuổi token là 930 giây. Nếu policy cho phép leeway 60 giây cho phép kiểm tra tuổi, token vẫn nằm trong giới hạn 960 giây; nếu policy không áp leeway cho max age, token vượt giới hạn 900 giây và bị từ chối. Điểm quyết định là policy phải nêu rõ cách áp dụng dung sai, không để thư viện hoặc từng endpoint tự suy đoán.

### 5.3. iat không thay thế exp

Một token có iat rất mới vẫn có thể hết hạn nếu exp đã qua hoặc nằm trước thời điểm hiện tại. Ngược lại, token có exp xa trong tương lai vẫn có thể bị từ chối vì iat quá cũ theo maxTokenAge.

Do đó:

- exp kiểm tra thời điểm kết thúc hiệu lực.
- nbf kiểm tra thời điểm bắt đầu hiệu lực.
- iat ghi nhận thời điểm phát hành và hỗ trợ kiểm tra tuổi/tính hợp lý.

Không dùng riêng iat để xác định token còn hiệu lực.

## 6. Chính sách thời gian tổng thể

Một policy thời gian nên định nghĩa tối thiểu:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Required claims | exp, nbf, iat có bắt buộc không? |
| Maximum lifetime | Thời lượng exp - iat tối đa là bao nhiêu? |
| Maximum token age | Token được phép cũ tối đa bao lâu tính từ iat? |
| Clock skew/leeway | Hai đồng hồ được phép lệch bao nhiêu? |
| Time source | Lấy thời gian hiện tại từ nguồn đồng hồ nào? |
| Precision | So sánh tới giây hay hỗ trợ phần thập phân? |
| Missing claims | Thiếu claim bắt buộc thì xử lý thế nào? |
| Relationship | Quan hệ nbf, iat, exp nào phải thỏa mãn? |
| Profile | Quy tắc riêng của access token, ID token hoặc assertion là gì? |

Ví dụ policy minh họa:

~~~yaml
timeValidation:
  requireExp: true
  requireIat: true
  requireNbf: false
  maxTokenLifetimeSeconds: 900
  maxTokenAgeSeconds: 900
  clockSkewSeconds: 60
  rejectFutureIatBeyondSkew: true
  requireNbfBeforeExp: true
~~~

Đây không phải cú pháp cấu hình chuẩn của JWT. Đây là cách biểu diễn một hợp đồng ứng dụng. Hệ thống thực tế cần xác định chính xác leeway được áp dụng cho từng điều kiện, thay vì dùng một giá trị dung sai không rõ phạm vi.

### 6.1. Quy tắc thời gian phải gắn với token profile

Không nên dùng cùng một thời lượng sống cho mọi JWT:

| Loại token | Cách thiết kế thời gian thường gặp |
| --- | --- |
| Access token | Thời hạn tương đối ngắn; giới hạn max age theo rủi ro API |
| ID token | Theo OIDC Core và thời hạn do OpenID Provider phát hành; client kiểm tra exp và các điều kiện flow |
| Client assertion | Thường có thời hạn ngắn và quy tắc chống replay theo profile |
| JWT bearer assertion | Theo hợp đồng trao đổi token; có thể cần jti và kiểm tra sử dụng lại |
| Token nội bộ | Theo rủi ro, khả năng đồng bộ đồng hồ và mức độ nhạy cảm giữa các dịch vụ |
| Token dùng một lần | Ngoài thời gian còn cần trạng thái sử dụng/nonce/jti để chống replay |

Đây là định hướng thiết kế, không phải giá trị thời hạn bắt buộc cho mọi hệ thống. Policy phải xuất phát từ profile và mô hình đe dọa cụ thể.

## 7. Clock skew và đồng bộ đồng hồ

**Clock skew** là độ lệch giữa đồng hồ của issuer, resource server và các hệ thống liên quan. Nếu issuer phát hành token với iat/nbf/exp theo đồng hồ nhanh hơn bên nhận, token hợp lệ có thể bị từ chối quá sớm. Nếu bên nhận có đồng hồ chậm, token hết hạn có thể được chấp nhận lâu hơn dự kiến.

### 7.1. Dùng leeway nhỏ và nhất quán

Một policy có thể cho phép dung sai L:

~~~text
exp: accept only when now < exp + L
nbf: accept only when now + L >= nbf
iat: reject when iat > now + L
~~~

Đây là cách biểu diễn phổ biến cho dung sai thời gian. Điều kiện max token age và maximum lifetime cần được quy định riêng; không mặc định cộng L vào mọi phép so sánh nếu policy không nói rõ.

Leeway nên:

- Nhỏ và phù hợp với sai lệch đồng hồ đã đo được.
- Giống nhau giữa các instance dùng chung policy.
- Có giá trị tối đa được quản trị, không để request hoặc token tự chọn.
- Được giám sát và giảm khi hạ tầng đồng bộ tốt hơn.
- Không được dùng để che lỗi clock drift kéo dài.

Leeway quá lớn làm cửa sổ sử dụng token rộng hơn, khiến token hết hạn hoặc chưa có hiệu lực vẫn có thể được chấp nhận trong khoảng thời gian đáng kể.

### 7.2. Đồng bộ thời gian hệ thống

Các máy chủ cần đồng bộ thời gian UTC bằng nguồn tin cậy, thường thông qua dịch vụ đồng bộ thời gian của hạ tầng. Vận hành cần:

- Theo dõi độ lệch đồng hồ giữa các node và cảnh báo khi vượt ngưỡng.
- Bảo đảm container, VM và host dùng nguồn thời gian nhất quán.
- Tránh chỉnh đồng hồ thủ công tùy tiện trong khi hệ thống đang phục vụ request.
- Kiểm tra tình trạng đồng bộ sau khi resume VM, failover hoặc khôi phục máy chủ.
- Dùng đồng hồ monotonic cho đo thời lượng và timeout; dùng đồng hồ wall-clock UTC đã đồng bộ để so sánh NumericDate.

Đồng hồ monotonic không thay thế UTC wall clock khi so sánh timestamp Unix, nhưng hữu ích để đo elapsed time mà không bị ảnh hưởng bởi việc đồng hồ hệ thống được điều chỉnh.

### 7.3. Không tin thời gian do client gửi

Không dùng header, query parameter hoặc body do client tự gửi làm thời điểm hiện tại để xác minh JWT. Thời điểm kiểm tra phải đến từ đồng hồ của bên xác minh hoặc nguồn thời gian nội bộ đã được tin cậy.

## 8. Quan hệ giữa các claim thời gian

Khi profile yêu cầu nhiều claim, policy có thể kiểm tra các quan hệ hợp lý:

~~~text
iat <= exp
nbf < exp
exp - iat <= maxTokenLifetime
now - iat <= maxTokenAge
~~~

Các điều kiện này là ví dụ chính sách, không phải tất cả đều là yêu cầu bắt buộc của RFC 7519 cho mọi JWT. Cần xác định điều kiện nào thuộc chuẩn/profile và điều kiện nào là quy tắc bổ sung của ứng dụng.

Một số trường hợp:

| Tình huống | Diễn giải | Hành vi theo policy thông thường |
| --- | --- | --- |
| exp nhỏ hơn hoặc bằng iat | Token hết hạn trước hoặc ngay khi phát hành | Từ chối |
| nbf bằng exp | Không có khoảng hiệu lực hữu ích | Từ chối |
| nbf sau exp | Khoảng hiệu lực mâu thuẫn | Từ chối |
| iat nằm quá xa trong tương lai | Đồng hồ hoặc token bất thường | Từ chối |
| exp còn xa nhưng iat quá cũ | Token vượt max age | Từ chối nếu policy có giới hạn tuổi |
| Không có exp nhưng policy yêu cầu exp | Thiếu claim bắt buộc | Từ chối |
| Không có nbf và policy không yêu cầu | Claim tùy chọn vắng mặt | Tiếp tục kiểm tra các điều kiện khác |

Không tự tạo giá trị mặc định cho claim bị thiếu. Nếu policy yêu cầu exp mà token không có exp, không được coi token là không bao giờ hết hạn.

## 9. Ví dụ tính thời gian

Giả sử policy quy định:

- exp bắt buộc.
- iat bắt buộc.
- nbf tùy chọn.
- maxTokenLifetime = 900 giây.
- maxTokenAge = 900 giây.
- clock skew = 30 giây.
- Leeway chỉ áp dụng cho exp, nbf và kiểm tra iat tương lai; maxTokenAge không cộng leeway.

Token có:

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

| now (Unix seconds) | Kiểm tra | Kết quả |
| ---: | --- | --- |
| 1893455970 | now + 30 = nbf | Có thể chấp nhận nbf theo leeway; vẫn kiểm tra các điều kiện khác |
| 1893456000 | now = iat = nbf | Bắt đầu có hiệu lực |
| 1893456750 | now < exp | Chưa hết hạn |
| 1893456920 | now = exp + 20 | Có thể chấp nhận exp theo leeway 30 giây |
| 1893456930 | now = exp + 30 | Hết dung sai nếu quy tắc yêu cầu now < exp + L |
| 1893456960 | now = exp + 60 | Hết hạn, từ chối |

Trong ví dụ này, token có thời lượng exp - iat đúng 900 giây. Nếu thời gian hiện tại vượt iat hơn 900 giây thì maxTokenAge cũng có thể làm token bị từ chối, kể cả khi exp còn nằm trong cửa sổ leeway. Các điều kiện phải được áp dụng đồng thời.

## 10. Mã giả kiểm tra exp, nbf và iat

Đoạn mã giả sau giả định chữ ký hoặc authenticated decryption đã thành công và claims đã được parse với kiểu dữ liệu đúng:

~~~text
function validateTimeClaims(claims, policy, trustedNow):
    require claims is a verified JSON object

    if policy.requireExp:
        require claims.exp exists
    if policy.requireIat:
        require claims.iat exists
    if policy.requireNbf:
        require claims.nbf exists

    validateNumericDateTypeAndRange(claims.exp, when present)
    validateNumericDateTypeAndRange(claims.nbf, when present)
    validateNumericDateTypeAndRange(claims.iat, when present)

    now = trustedNow.unixSeconds
    leeway = policy.clockSkewSeconds

    if claims.exp exists:
        require now < claims.exp + leeway

    if claims.nbf exists:
        require now + leeway >= claims.nbf

    if claims.iat exists:
        require claims.iat <= now + leeway

    if claims.exp and claims.iat exist:
        require claims.exp > claims.iat
        if policy.maxTokenLifetimeSeconds is configured:
            require claims.exp - claims.iat <= policy.maxTokenLifetimeSeconds

    if claims.nbf and claims.exp exist:
        require claims.nbf < claims.exp

    if claims.iat exists and policy.maxTokenAgeSeconds is configured:
        require now - claims.iat <= policy.maxTokenAgeSeconds

    return TimeValidationResult(valid = true)
~~~

Đây là pseudocode minh họa. Hệ thống phải xác định rõ maxTokenAge có áp dụng leeway hay không, cách xử lý NumericDate thập phân và các điều kiện riêng của profile. Hàm lấy thời điểm hiện tại phải dùng đồng hồ của bên xác minh đã được đồng bộ, không từ dữ liệu client.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Bỏ qua exp | Token có thể được dùng vô thời hạn | Bắt buộc exp theo profile access token và kiểm tra khi có |
| Kiểm tra exp bằng ngày/phút | Chấp nhận quá hạn trong phần thời gian còn lại | So timestamp đầy đủ |
| Nhầm giây với mili giây | Token hết hạn sai hoặc sống quá lâu | Dùng NumericDate theo giây |
| Ép chuỗi thành NumericDate | Parser không nhất quán | Từ chối sai kiểu |
| Bỏ qua nbf | Token được dùng trước thời điểm cho phép | Kiểm tra nbf khi có hoặc khi profile yêu cầu |
| Coi iat là exp | Hiểu sai ý nghĩa thời gian | Dùng exp cho hết hạn; iat cho thời điểm phát hành/tuổi |
| Không giới hạn max age | Token có exp xa vẫn được dùng lâu hơn dự kiến | Áp dụng maxTokenAge nếu rủi ro yêu cầu |
| Clock skew quá lớn | Mở rộng cửa sổ chấp nhận token | Leeway nhỏ, có đo lường và giám sát |
| Dùng đồng hồ client | Người gửi có thể điều khiển kết quả | Dùng trusted server clock |
| Không kiểm tra quan hệ claims | Token có khoảng hiệu lực vô lý | Kiểm tra iat/nbf/exp theo policy |
| Coi exp là cơ chế thu hồi | Token bị lộ vẫn dùng được tới exp | Có cơ chế revoke/session khi cần |

## 12. Kiểm thử ranh giới thời gian

Kiểm thử thời gian cần tập trung vào các giá trị ngay trước, đúng tại và ngay sau ranh giới:

| Claim | Ca kiểm thử |
| --- | --- |
| exp | now = exp - 1; now = exp; now = exp + 1 |
| exp với leeway | now = exp + L - epsilon; now = exp + L; now = exp + L + epsilon |
| nbf | now = nbf - 1; now = nbf; now = nbf + 1 |
| nbf với leeway | now = nbf - L; now = nbf - L - epsilon |
| iat | iat = now; iat = now + L; iat = now + L + epsilon |
| max age | now - iat = maxAge - 1; = maxAge; = maxAge + 1 |
| maximum lifetime | exp - iat đúng giới hạn; vượt một giây; giá trị âm |
| Claim presence | Thiếu exp/nbf/iat khi bắt buộc và khi tùy chọn |
| Kiểu dữ liệu | String, boolean, null, object, số quá lớn, số thập phân |
| Clock behavior | Đồng hồ lệch, đồng hồ nhảy, node khác nhau, sau failover/resume |

Nên cố định đồng hồ trong unit test thay vì chờ thời gian thực. Dùng epsilon phù hợp với độ chính xác của hệ thống; nếu profile hỗ trợ NumericDate phần lẻ, cần kiểm thử cả phần lẻ.

### 12.1. Kiểm thử clock skew giữa nhiều node

Trong môi trường nhiều resource server, cùng một token không nên bị chấp nhận ở node này nhưng bị từ chối ở node khác chỉ vì cấu hình leeway khác nhau. Kiểm thử:

- Các node dùng cùng policy thời gian.
- Clock offset thực tế nằm trong giới hạn đã định.
- Khi một node lệch giờ vượt ngưỡng, hệ thống cảnh báo hoặc đưa node ra khỏi phục vụ theo quy trình vận hành.
- Sau khi đồng hồ được đồng bộ lại, token được đánh giá nhất quán.

## 13. Vận hành và giám sát thời gian

Thời gian là phụ thuộc vận hành. Cần theo dõi:

- Độ lệch đồng hồ giữa các máy chủ và nguồn thời gian.
- Tỷ lệ token bị từ chối do exp, nbf, iat hoặc max age.
- Số token có iat trong tương lai.
- Số token có lifetime vượt policy.
- Phân bố thời gian sống thực tế của token theo issuer/profile.
- Các trường hợp cùng token cho kết quả khác nhau giữa các node.

Log chỉ nên ghi mã lỗi và metadata cần thiết như policy ID, issuer ID đã xác minh, thời điểm xử lý và loại claim gây lỗi. Không ghi toàn bộ token hoặc claims nhạy cảm.

Ví dụ mã lỗi nội bộ:

~~~text
TOKEN_EXPIRED
TOKEN_NOT_YET_VALID
TOKEN_ISSUED_IN_FUTURE
TOKEN_TOO_OLD
TOKEN_LIFETIME_EXCEEDED
INVALID_NUMERIC_DATE
REQUIRED_TIME_CLAIM_MISSING
CLOCK_OFFSET_OUT_OF_POLICY
~~~

Phản hồi công khai có thể dùng thông báo xác thực không hợp lệ chung; log nội bộ mới phân biệt lý do để vận hành và điều tra.

## 14. Checklist triển khai

1. [ ] exp, nbf và iat được parse như NumericDate theo giây, không phải mili giây.
2. [ ] Sai kiểu, số không hợp lệ, tràn số và giá trị ngoài miền profile bị từ chối.
3. [ ] exp được kiểm tra tại ranh giới now >= exp, có leeway nhỏ nếu policy cho phép.
4. [ ] nbf được kiểm tra để từ chối token trước thời điểm có hiệu lực.
5. [ ] iat không bị nhầm với exp; kiểm tra iat tương lai và max token age khi policy yêu cầu.
6. [ ] Required claims được xác định theo token profile, không mặc định mọi JWT phải có cả ba.
7. [ ] Quan hệ exp/iat/nbf và maximum lifetime được kiểm tra nếu policy quy định.
8. [ ] Clock skew có giá trị nhỏ, thống nhất và được áp dụng rõ cho từng điều kiện.
9. [ ] Thời gian hiện tại lấy từ trusted server clock; không dùng timestamp client.
10. [ ] Các node được đồng bộ thời gian và có giám sát clock drift.
11. [ ] Có negative tests tại ranh giới thời gian, số thập phân, sai đơn vị và thiếu claims.
12. [ ] Có cơ chế thu hồi/phiên nếu cần vô hiệu token trước exp.
13. [ ] Log không chứa token hoặc claims nhạy cảm.

## 15. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** NumericDate và các claims exp, nbf, iat.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán JOSE; không thay thế quy tắc thời gian của JWT.
- **RFC 8725 — JSON Web Token Best Current Practices:** thực hành xác minh JWT và áp dụng profile/claims.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** yêu cầu claims và validation cho access token dạng JWT.
- **OpenID Connect Core 1.0:** quy tắc thời gian và xác minh ID token trong các authentication flow.

**Nguyên tắc ghi nhớ:** exp xác định thời điểm kết thúc hiệu lực, nbf xác định thời điểm bắt đầu hiệu lực, iat ghi nhận thời điểm phát hành và hỗ trợ kiểm tra tuổi token. Hãy parse đúng NumericDate, dùng đồng hồ đáng tin cậy, áp dụng leeway nhỏ theo policy và kiểm tra các quan hệ thời gian trước khi chấp nhận JWT.
