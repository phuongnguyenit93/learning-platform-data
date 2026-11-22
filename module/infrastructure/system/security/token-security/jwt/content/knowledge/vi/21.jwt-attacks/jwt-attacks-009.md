# Claims trùng tên, kiểu dữ liệu bất thường và khác biệt giữa bộ phân tích

## 1. Vì sao cách parse JWT là một phần của bảo mật?

JWT là một cấu trúc dữ liệu JSON được đóng gói theo định dạng JOSE. Sau khi decode, bên nhận phải diễn giải JOSE Header và JWT Claims Set để xác định issuer, subject, audience, thời hạn, scope và các thông tin authorization khác.

Một token có thể được xác minh chữ ký thành công nhưng vẫn bị diễn giải khác nhau giữa các thành phần nếu chúng xử lý JSON không thống nhất. Những khác biệt nguy hiểm thường xuất hiện khi:

- Một tên claim hoặc header parameter xuất hiện nhiều lần.
- Một claim có kiểu dữ liệu không đúng profile, nhưng parser hoặc ứng dụng tự ép kiểu.
- Giá trị số quá lớn hoặc có độ chính xác vượt khả năng biểu diễn của runtime.
- Tên thuộc tính dùng Unicode escape hoặc cách viết khác nhau.
- Gateway, API gateway, thư viện JWT và backend parse cùng bytes theo quy tắc khác nhau.
- Một thành phần xác minh token trên một cách diễn giải, còn thành phần khác cấp quyền dựa trên cách diễn giải khác.

Ví dụ, gateway có thể đọc role đầu tiên là user, trong khi backend đọc role cuối cùng là admin. Nếu cả hai cùng tin token đã được xác minh nhưng không thống nhất cách parse, ranh giới bảo mật giữa chúng bị phá vỡ.

Mục tiêu của bài học là xây dựng một quy tắc diễn giải JWT nhất quán: parse nghiêm ngặt, từ chối cấu trúc mơ hồ, kiểm tra kiểu dữ liệu theo profile và bảo đảm mọi quyết định bảo mật dùng cùng một tập claims đã xác minh.

Bài này thuộc phạm vi JWT/JOSE tổng quát, không phụ thuộc Java, Spring Security hay framework cụ thể.

## 2. Claims trùng tên trong JWT

RFC 7519 quy định tên claim trong JWT Claims Set phải là duy nhất. Đặc tả cho phép parser xử lý một JWT có claim trùng theo một trong hai cách:

1. Từ chối JWT có tên claim trùng lặp.
2. Giữ lại giá trị xuất hiện cuối cùng theo thứ tự trong JSON.

RFC 8259 cũng khuyến nghị tên thành viên JSON nên duy nhất và cảnh báo rằng hành vi khi có tên trùng không thống nhất giữa các implementation. Một số parser giữ giá trị đầu tiên, một số giữ giá trị cuối cùng, một số báo lỗi hoặc giữ nhiều giá trị.

Về mặt tương thích, quy tắc của RFC 7519 mô tả cách parser có thể xử lý. Với hệ thống xác thực và authorization, lựa chọn an toàn hơn là **từ chối mọi JWT có tên claim trùng lặp**, thay vì để kết quả phụ thuộc thư viện.

Ví dụ payload mơ hồ:

~~~json
{
  "iss": "https://identity.example",
  "sub": "alice",
  "role": "user",
  "role": "admin",
  "aud": "https://orders.example/"
}
~~~

Các parser có thể diễn giải khác nhau:

| Hành vi parser | Giá trị role được quan sát |
| --- | --- |
| First value wins | user |
| Last value wins | admin |
| Reject duplicates | Token bị từ chối |
| Preserve all values | Ứng dụng phải tự quyết định, có thể tiếp tục tạo bất đồng |

Không nên để một tầng kiểm tra quyền nhìn thấy user trong khi tầng thực thi nhìn thấy admin.

### Những claim nhạy cảm cần chú ý

Duplicate member đặc biệt nguy hiểm khi áp dụng cho:

- iss: hai thành phần có thể chọn issuer khác nhau và dùng trust configuration khác nhau.
- sub: audit hoặc ownership check có thể dùng subject khác với downstream.
- aud: một tầng thấy token dành cho API A, tầng khác thấy token dành cho API B.
- exp, nbf, iat: các tầng có thể đưa ra kết luận khác nhau về thời hạn.
- scope, roles, groups: khác biệt có thể dẫn đến cấp quyền quá mức.
- jti: hệ thống replay detection có thể theo dõi một ID khác với hệ thống audit.
- client_id, act, cnf: có thể làm sai lệch danh tính client, actor hoặc sender constraint.

Không chỉ claim ở cấp cao nhất mới cần kiểm tra. Nếu profile sử dụng object lồng nhau như act, cnf hoặc custom authorization object, các object đó cũng cần được parse theo quy tắc nghiêm ngặt.

## 3. Duplicate JOSE Header Parameter

JOSE Header cũng là JSON object và có thể chứa các parameter ảnh hưởng tới cách xác minh hoặc giải mã token. RFC 7515 và RFC 7516 yêu cầu tên header parameter phải duy nhất; parser có thể từ chối header trùng hoặc dùng giá trị xuất hiện cuối cùng theo quy tắc đặc tả.

Ví dụ:

~~~json
{
  "alg": "PS256",
  "kid": "trusted-key-01",
  "alg": "none"
}
~~~

Nếu một thành phần đọc giá trị đầu tiên và thành phần khác đọc giá trị cuối cùng, chúng có thể bất đồng về thuật toán. Các parameter khác cũng nhạy cảm:

- kid: có thể khiến các thành phần chọn khóa khác nhau.
- jku, x5u: có thể dẫn tới các nguồn khóa khác nhau.
- jwk, x5c, x5t, x5t#S256: có thể tạo bất đồng về khóa/chứng thư.
- crit: có thể làm một thành phần xử lý extension trong khi thành phần khác bỏ qua.
- b64: ảnh hưởng cách dựng signing input trong JWS theo RFC 7797.
- Với JWE, alg, enc, zip, epk, apu, apv và các parameter quản lý khóa cần được diễn giải thống nhất.

Không chọn parameter theo thứ tự xuất hiện và không để một parser xác minh còn parser khác chọn khóa/thuật toán từ một object đã được parse lại theo quy tắc khác.

## 4. Khác biệt giữa các bộ phân tích JSON

JSON có vẻ đơn giản nhưng các thư viện có thể khác nhau ở những trường hợp biên. Khi JWT đi qua nhiều thành phần, khác biệt nhỏ có thể trở thành lỗi authorization.

### First-wins và last-wins

Đây là khác biệt thường gặp nhất với duplicate member names. Một gateway có thể giữ giá trị đầu tiên, trong khi backend giữ giá trị cuối cùng. RFC 7519 cho phép reject hoặc lexical-last đối với duplicate claim names, nhưng các thành phần tự viết hoặc thư viện JSON tổng quát có thể có hành vi khác.

### Ép kiểu tự động

Một tầng có thể tự chuyển string "123" thành số 123; tầng khác có thể từ chối. Một tầng coi chuỗi "false" là false, tầng khác coi mọi chuỗi không rỗng là true. Điều này đặc biệt nguy hiểm nếu claim được dùng làm cờ quyền.

### Số lớn và độ chính xác

Một parser có thể giữ số nguyên lớn chính xác; parser khác dùng floating-point và làm tròn. Nếu số đó là NumericDate hoặc một custom quota/limit, các thành phần có thể đánh giá khác nhau.

### Unicode escape và tên thuộc tính

JSON cho phép biểu diễn ký tự bằng escape. Ví dụ role và \u0072ole sau khi decode đều là cùng một chuỗi tên. Duplicate detection phải thực hiện trên tên đã được JSON decode, không chỉ so sánh bytes thô.

### Thứ tự thành viên

Thứ tự member trong JSON object không mang ý nghĩa nghiệp vụ. Ứng dụng không được dựa vào thứ tự field để chọn giá trị, xác định ưu tiên hoặc xây dựng policy.

### Null, thiếu và giá trị rỗng

Một claim bị thiếu, có giá trị null, chuỗi rỗng, mảng rỗng hoặc số 0 là các trạng thái khác nhau. Nếu ứng dụng gộp chúng thành một giá trị mặc định, attacker có thể lợi dụng sự khác biệt giữa validator và authorization code.

## 5. Kiểm tra kiểu dữ liệu theo JWT và token profile

JWT định nghĩa kiểu/ý nghĩa cho một số registered claims. Token profile như RFC 9068 có thể bổ sung yêu cầu cụ thể. Ứng dụng cần kiểm tra kiểu JSON chính xác, sau đó mới kiểm tra giá trị.

| Claim/parameter | Kiểu dữ liệu cần hiểu | Lưu ý |
| --- | --- | --- |
| iss | String | So khớp với issuer tin cậy theo profile |
| sub | String | Định danh subject trong namespace của issuer |
| aud | String hoặc array of strings | Mỗi audience phải là string; phải chứa recipient dự kiến |
| exp | NumericDate (JSON number) | Không chấp nhận string hoặc boolean; kiểm tra miền giá trị và thời gian |
| nbf | NumericDate (JSON number) | Không chấp nhận string hoặc boolean |
| iat | NumericDate (JSON number) | Không chấp nhận string hoặc boolean; kiểm tra hợp lý theo policy |
| jti | String | Định danh JWT; không tự ngăn replay nếu không có state |
| scope trong JWT access token theo RFC 9068 | String | Danh sách scope theo quy ước phân tách bằng dấu cách |
| client_id theo RFC 9068 | String | Định danh OAuth client |
| cnf | Object | Chứa thông tin confirmation/key binding theo profile |
| alg trong JOSE Header | String | Phải thuộc allowlist |
| enc trong JWE Header | String | Phải thuộc allowlist |
| kid | String | Tra cứu trong tập khóa tin cậy, không phải đường dẫn tùy ý |
| crit | Array of strings | Mỗi extension critical phải được hỗ trợ |
| x5c | Array of strings | Phần tử là Base64 của chứng thư DER |
| jwk | Object | Phải thỏa cấu trúc và policy JWK |
| b64 | Boolean | Không nhận string "true" hoặc số 1 |

Bảng này không thay thế toàn bộ registry. Custom claims phải có schema rõ ràng trong token profile; không suy ra kiểu từ một giá trị mẫu.

### Trường hợp aud là string hoặc array

RFC 7519 cho phép aud là một string hoặc một array các string. Cả hai dạng đều có thể hợp lệ:

~~~json
{
  "aud": "https://orders.example/"
}
~~~

~~~json
{
  "aud": [
    "https://orders.example/",
    "https://inventory.example/"
  ]
}
~~~

Nhưng các dạng sau không hợp lệ theo kiểu claim:

~~~json
{
  "aud": ["https://orders.example/", 42]
}
~~~

~~~json
{
  "aud": {
    "primary": "https://orders.example/"
  }
}
~~~

Resource server phải kiểm tra đúng identifier của mình theo profile, không dùng substring hoặc coercion.

## 6. Type confusion trong claim và hậu quả authorization

Type confusion xảy ra khi ứng dụng hoặc parser chấp nhận một kiểu dữ liệu khác với kiểu profile yêu cầu, hoặc tự chuyển đổi kiểu theo cách không thống nhất.

Ví dụ:

~~~json
{
  "sub": ["alice"],
  "aud": "https://admin.example/",
  "exp": "1999999999",
  "is_admin": "false",
  "scope": ["orders.read", "orders.write"]
}
~~~

Nếu ứng dụng kỳ vọng:

- sub là string,
- exp là NumericDate,
- is_admin là boolean,
- scope là string theo access-token profile,

thì payload trên phải bị từ chối. Không được tự ép kiểu để cố xử lý.

Một lỗi thường gặp là kiểm tra boolean theo truthiness. Chuỗi "false" là chuỗi không rỗng và có thể bị một số ngôn ngữ coi là true. Tương tự, chuỗi "0" và số 0 có thể có hành vi khác nhau giữa các runtime.

### Không ép kiểu để “giúp” token hợp lệ

Không nên:

- Chuyển string thành number cho exp/nbf/iat.
- Chuyển number thành string cho sub, iss hoặc jti.
- Chuyển string "false" thành boolean theo truthiness.
- Chuyển object thành string để so sánh audience.
- Chấp nhận một phần tử sai kiểu trong mảng rồi âm thầm bỏ qua.
- Tự biến null hoặc claim thiếu thành giá trị mặc định có quyền cao hơn.

Nếu profile muốn hỗ trợ nhiều dạng biểu diễn, phải định nghĩa rõ dạng nào hợp lệ và áp dụng cùng một quy tắc ở tất cả thành phần. Với registered claims, phải tuân thủ kiểu được RFC quy định.

## 7. NumericDate, số lớn và độ chính xác

RFC 7519 định nghĩa NumericDate là giá trị JSON number biểu diễn số giây từ Unix epoch UTC, không tính leap seconds. Giá trị có thể có phần thập phân; không nên khẳng định mọi NumericDate bắt buộc là integer nếu profile không đặt thêm ràng buộc.

Các rủi ro cần kiểm soát:

- Number quá lớn gây overflow hoặc wrap-around.
- Floating-point làm tròn khiến thời hạn khác nhau giữa các runtime.
- Giá trị exponent hợp lệ về cú pháp JSON nhưng vượt miền mà ứng dụng cho phép.
- Boolean hoặc string bị ép thành number.
- Giá trị âm hoặc thời gian quá xa trong tương lai gây lỗi logic.
- Clock skew được áp dụng khác nhau giữa gateway và resource server.

### Quy tắc xử lý thời gian

1. Parse exp, nbf và iat như JSON number theo đúng profile.
2. Từ chối giá trị không hữu hạn hoặc vượt miền biểu diễn an toàn của hệ thống.
3. Nếu profile yêu cầu integer seconds, từ chối phần thập phân thay vì tự làm tròn.
4. Nếu profile cho phép fractional NumericDate, giữ đủ độ chính xác cần thiết khi so sánh.
5. Đặt giới hạn hợp lý cho thời gian phát hành và thời hạn token.
6. Dùng clock source được đồng bộ và một chính sách clock-skew leeway thống nhất.
7. Không chuyển đổi đơn vị nhầm giữa seconds và milliseconds.

Ví dụ lỗi đơn vị:

- exp = 1893453600 là thời gian theo giây.
- Diễn giải nhầm thành milliseconds sẽ khiến token có vẻ hết hạn từ rất lâu.
- Nhân thêm 1000 hai lần có thể làm token tồn tại lâu hơn dự kiến.

Đối với claim custom chứa số nguyên lớn như account sequence hoặc transaction ID, không dùng kiểu số có thể mất precision. Nên định nghĩa miền giá trị và cách biểu diễn nhất quán; nếu cần độ chính xác tuyệt đối, profile có thể dùng string với schema rõ ràng.

## 8. Null, missing, empty và false không giống nhau

JSON phân biệt các trạng thái:

~~~json
{}
~~~

~~~json
{
  "email_verified": null
}
~~~

~~~json
{
  "email_verified": false
}
~~~

~~~json
{
  "email_verified": true
}
~~~

Ứng dụng không nên gộp các trường hợp trên:

- Missing: claim không được phát hành.
- Null: claim có mặt nhưng không có giá trị theo JSON.
- False: claim boolean có giá trị false.
- True: claim boolean có giá trị true.

Nếu profile yêu cầu email_verified là boolean, null hoặc missing phải được xử lý theo policy (thường từ chối nếu claim bắt buộc); không coi chúng như true. Với quyền, mặc định an toàn là không cấp quyền khi dữ liệu thiếu hoặc sai kiểu.

Tương tự:

- aud thiếu khác với aud là mảng rỗng.
- scope thiếu khác với scope là chuỗi rỗng.
- exp thiếu khác với exp bằng 0.
- jti thiếu khác với jti là chuỗi rỗng.

Không dùng giá trị mặc định rộng quyền khi claim không tồn tại.

## 9. Unicode escape, case sensitivity và tên claim

Tên claim và JOSE Header Parameter là chuỗi JSON. JSON escape được giải mã trước khi ứng dụng truy cập tên member.

Ví dụ:

~~~json
{
  "role": "user",
  "\u0072ole": "admin"
}
~~~

Sau khi decode escape, cả hai tên đều là role. Parser nghiêm ngặt phải nhận diện đây là duplicate name và từ chối.

Các quy tắc:

- So sánh tên sau khi decode JSON escape.
- Tên claim phân biệt chữ hoa/chữ thường; role và Role là hai tên khác nhau.
- Không tự lowercase hoặc uppercase tên claim.
- Không tự Unicode-normalize tên claim để biến hai chuỗi khác nhau thành một tên khác nếu profile không quy định.
- Với subject, issuer và audience dạng định danh, dùng quy tắc so khớp chính xác do profile quy định; không tự trim, lowercase hoặc normalize URI theo suy đoán.
- Nếu custom claim dùng Unicode, quy định canonical representation và cách so sánh ngay từ profile.

Unicode confusable characters có thể khiến hai tên trông gần giống nhau nhưng khác code point. Chúng không phải duplicate theo JSON nếu code point khác, nhưng có thể gây nhầm lẫn cho người vận hành. Với tên claim bảo mật, nên dùng tên ASCII đã được định nghĩa và không chấp nhận alias gần giống.

## 10. Khác biệt giữa gateway, verifier và backend

Một kiến trúc thường có nhiều thành phần cùng đọc token:

~~~mermaid
flowchart LR
    C["Client"] --> G["API Gateway"]
    G --> V["JWT Verifier"]
    V --> A["Authorization Layer"]
    A --> B["Backend Service"]
    G -. "forward token/claims" .-> B
~~~

Nếu mỗi thành phần tự parse JWT, cần bảo đảm chúng dùng cùng quy tắc. Các lỗi thường gặp:

- Gateway lấy duplicate claim đầu tiên, backend lấy giá trị cuối.
- Gateway xác minh aud dạng string, backend chỉ hỗ trợ array hoặc tự chuyển object thành string.
- Gateway kiểm tra exp bằng floating-point, backend làm tròn sang integer.
- Gateway bỏ qua claim sai kiểu, backend áp dụng giá trị mặc định.
- Gateway xác minh một JOSE Header nhưng backend parse lại và chọn kid/alg khác.
- Gateway tin token đã xác minh rồi chuyển các claim qua header nội bộ, nhưng không bảo vệ hoặc ghi đè header do caller tự gửi.

### Nguyên tắc một cách diễn giải

- Dùng một parser nghiêm ngặt và một token-validation component dùng chung nếu kiến trúc cho phép.
- Xác minh chữ ký và parse claims trên cùng một biểu diễn dữ liệu.
- Sau khi xác minh, truyền một authenticated context có cấu trúc qua kênh nội bộ đã xác thực; không truyền các header do client tự đặt.
- Nếu backend tự xác minh token, phải áp dụng cùng profile và cùng quy tắc duplicate/type validation.
- Không xác minh token trên một object đã parse rồi serialize lại theo cách có thể thay đổi signing input.
- Không dùng parser thứ hai với cấu hình khác để ra quyết định authorization.

Chữ ký JWS bảo vệ bytes của protected header và payload trong signing input. Nó không bảo đảm hai parser diễn giải JSON giống nhau. Một issuer có thể vô tình phát hành JSON có duplicate member names; các verifier khác nhau vẫn có thể xác minh cùng chữ ký nhưng đưa ra kết quả authorization khác nhau.

## 11. Parse đúng thứ tự trong JWS, JWE và Nested JWT

### JWS

1. Giới hạn kích thước token và kiểm tra Compact/JSON Serialization.
2. Decode protected header theo Base64URL nghiêm ngặt.
3. Parse JSON header, từ chối duplicate parameter và kiểm tra kiểu.
4. Chọn thuật toán trong allowlist và khóa từ nguồn tin cậy.
5. Xác minh chữ ký trên signing input gốc.
6. Chỉ sau khi chữ ký hợp lệ mới coi payload claims là dữ liệu đáng tin.
7. Parse/validate claims theo schema nghiêm ngặt; từ chối duplicate names và type mismatch.

Header cần được parse trước để chọn thuật toán/khóa, nhưng mọi giá trị trong header vẫn là dữ liệu chưa tin cậy cho tới khi chữ ký hợp lệ. Việc chọn khóa phải bị giới hạn bởi policy độc lập, không để token điều khiển nguồn tin cậy tùy ý.

### JWE

Với JWE, bên nhận phải xác thực quá trình giải mã và authentication tag trước khi xử lý plaintext như JWT claims. Không parse, cấp quyền hoặc thực hiện hành động dựa trên plaintext chưa được xác thực.

Sau khi JWE được xác thực thành công, nếu plaintext là JWT hoặc JSON claims, vẫn phải áp dụng duplicate/type validation tương ứng. Nếu JWE chứa một JWS lồng bên trong, tiếp tục xác minh lớp JWS theo profile.

### Nested JWT

Không bỏ qua một lớp bảo vệ chỉ vì lớp ngoài hợp lệ. Nếu profile yêu cầu sign-then-encrypt hoặc encrypt-then-sign, phải xác minh đúng thứ tự và đúng loại đối tượng. Claims chỉ được sử dụng sau khi toàn bộ lớp bảo vệ bắt buộc đã được xác minh.

## 12. Quy trình validation nghiêm ngặt

Một token profile nên định nghĩa schema và chính sách parser rõ ràng. Quy trình tổng quát:

1. **Giới hạn đầu vào:** giới hạn token bytes, số segment, kích thước header/payload và độ sâu JSON.
2. **Kiểm tra serialization:** chỉ chấp nhận Compact hoặc JSON Serialization mà endpoint hỗ trợ.
3. **Decode nghiêm ngặt:** Base64URL đúng bảng ký tự, UTF-8 hợp lệ, không chấp nhận segment bị cắt.
4. **Parse object:** header và claims phải là JSON object ở cấp cao nhất theo cấu trúc JOSE/JWT.
5. **Từ chối duplicate:** kiểm tra duplicate member sau khi decode tên JSON escape, bao gồm các object lồng nhau mà profile sử dụng.
6. **Kiểm tra kiểu:** registered claims và custom claims phải đúng kiểu đã định nghĩa.
7. **Kiểm tra miền giá trị:** NumericDate, độ dài string, số phần tử array, enum và identifier nằm trong giới hạn.
8. **Kiểm tra header:** alg/enc allowlist, kid, crit và vị trí protected/unprotected theo profile.
9. **Xác minh mật mã:** xác minh JWS hoặc xác thực/giải mã JWE bằng khóa tin cậy.
10. **Kiểm tra claims:** iss, aud, exp, nbf, typ, scope, subject và các ràng buộc token profile.
11. **Authorization:** chỉ dùng authenticated claims đã được validate để kiểm tra quyền trên resource.
12. **Nhất quán liên thành phần:** gateway, verifier và backend phải dùng cùng kết quả validation hoặc cùng profile parser.

~~~mermaid
flowchart TD
    A["Nhận JWT chưa tin cậy"] --> B["Giới hạn kích thước và serialization"]
    B --> C["Decode Base64URL và UTF-8 nghiêm ngặt"]
    C --> D["Parse JSON object"]
    D --> E{"Duplicate names hoặc JSON sai?"}
    E -- Có --> X["Từ chối"]
    E -- Không --> F["Kiểm tra kiểu và miền giá trị"]
    F --> G{"Schema/profile hợp lệ?"}
    G -- Không --> X
    G -- Có --> H["Kiểm tra JOSE algorithm/key policy"]
    H --> I["Xác minh chữ ký hoặc JWE authentication"]
    I --> J{"Bảo vệ mật mã hợp lệ?"}
    J -- Không --> X
    J -- Có --> K["Validate issuer, audience, time và token type"]
    K --> L{"Claims hợp lệ?"}
    L -- Không --> X
    L -- Có --> M["Authorization bằng authenticated context"]
~~~

### Mã giả độc lập nền tảng

~~~text
function validateJwtStrictly(token, profile):
    require byteLength(token) <= profile.maxTokenBytes
    parts = parseSupportedJoseSerialization(token, profile)

    headerBytes = strictBase64UrlDecode(parts.protectedHeader)
    header = parseJsonObject(
        headerBytes,
        rejectDuplicateNames = true,
        rejectInvalidUtf8 = true,
        maxDepth = profile.maxJsonDepth
    )
    validateHeaderTypesAndAllowlist(header, profile)

    if parts.isJwe:
        plaintext = authenticateAndDecryptJwe(parts, trustedKeyPolicy(profile))
        require authenticationSucceeded
        payloadBytes = plaintext
    else:
        require verifyJwsSignature(parts, trustedKeyPolicy(profile), profile.algorithms)
        payloadBytes = strictBase64UrlDecode(parts.payload)

    claims = parseJsonObject(
        payloadBytes,
        rejectDuplicateNames = true,
        rejectInvalidUtf8 = true,
        maxDepth = profile.maxJsonDepth
    )
    validateRegisteredClaimTypes(claims, profile)
    validateCustomClaimSchema(claims, profile)
    validateIssuerAudienceAndTime(claims, profile)

    return authenticatedClaims(claims)
~~~

Đây là mã giả mô tả thứ tự xử lý. Với JWS, chữ ký phải được xác minh trên signing input nguyên gốc; không serialize lại JSON rồi xác minh trên bytes mới. Với JWE, chỉ xử lý plaintext sau khi authentication thành công.

## 13. Xử lý lỗi và log an toàn

Token có duplicate claim, kiểu sai hoặc cấu trúc mơ hồ nên bị từ chối theo fail-closed. Không cố sửa token bằng cách tự chọn một giá trị hoặc ép kiểu để request tiếp tục.

Thông tin log hữu ích:

- Loại lỗi validation: duplicate claim, invalid type, invalid NumericDate, malformed UTF-8, invalid audience.
- Tên claim/parameter gây lỗi nếu không chứa dữ liệu nhạy cảm.
- Issuer đã cấu hình hoặc profile ID, nếu có thể ghi an toàn.
- Request/correlation ID do hệ thống quản lý.
- Thành phần parser và phiên bản policy để điều tra parser differential.

Không log raw JWT, toàn bộ payload, Authorization header hoặc dữ liệu cá nhân không cần thiết. Nếu cần liên kết sự kiện, dùng fingerprint/token ID đã được xử lý theo chính sách.

Đối với client, trả lỗi xác thực chung phù hợp với giao thức; không tiết lộ chi tiết nội bộ về khóa, parser hoặc cấu trúc claims nếu điều đó giúp attacker dò cấu hình.

## 14. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chấp nhận duplicate claims và để parser tự chọn | Gateway và backend có thể thấy giá trị khác nhau | Từ chối duplicate names |
| Chỉ kiểm tra duplicate trên raw bytes | Unicode escape có thể tạo tên trùng sau decode | So sánh tên sau JSON string decoding |
| Chỉ kiểm tra duplicate ở top-level nhưng dùng object lồng nhau cho authorization | Nested claim có thể có parser differential | Áp dụng quy tắc duplicate cho mọi object được profile sử dụng |
| Ép string thành number hoặc boolean | Các runtime có thể tạo quyết định khác nhau | Kiểm tra kiểu JSON chính xác |
| Chấp nhận aud object hoặc array có phần tử sai kiểu | Audience validation không nhất quán | Chỉ chấp nhận string hoặc array of strings |
| Parse NumericDate bằng số có precision không đủ | exp/nbf có thể bị làm tròn hoặc overflow | Giới hạn miền số và giữ precision theo profile |
| Coi missing, null, empty và false là giống nhau | Claim bắt buộc có thể bị bỏ qua hoặc quyền bị cấp sai | Định nghĩa riêng từng trạng thái trong schema |
| Lowercase tên claim hoặc tự normalize URI | Có thể làm thay đổi định danh | So khớp theo quy tắc profile, không tự chuẩn hóa |
| Gateway và backend dùng parser khác cấu hình | Một token có thể được xác minh và cấp quyền theo hai cách hiểu | Dùng chung validation component/profile |
| Tin claims trước khi xác minh chữ ký | Token giả có thể điều khiển subject/role/audience | Chỉ tin claims sau khi xác minh mật mã |
| Parse JWE plaintext trước khi xác minh authentication tag | Dữ liệu chưa xác thực có thể kích hoạt xử lý | Authenticate/decrypt thành công rồi mới parse claims |
| Re-serialize JSON trước khi xác minh JWS | Signing input thay đổi và semantics có thể khác | Verify trên bytes/signing input nguyên gốc |
| Bỏ qua claim sai kiểu rồi dùng giá trị mặc định | Token không đáp ứng schema vẫn có thể được chấp nhận | Fail closed khi claim bắt buộc sai kiểu/thiếu |

## 15. Bộ ca kiểm thử

Giả sử API nhận JWT access token theo profile đã công bố, yêu cầu iss/sub dạng string, aud dạng string hoặc array of strings, exp là NumericDate và scope là string.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Payload có claim names duy nhất và mọi kiểu đúng profile | Tiếp tục xác minh/authorization |
| Payload có hai member role | **Từ chối** |
| Payload có iss trùng với hai giá trị khác nhau | **Từ chối** |
| Payload có aud trùng, một giá trị cho API A và một giá trị cho API B | **Từ chối** |
| Protected header có alg trùng lặp | **Từ chối** |
| Header có kid trùng với hai giá trị khác nhau | **Từ chối** |
| Header có alg/crit trùng sau khi giải mã JSON escape | **Từ chối** |
| Tên role và \u0072ole cùng xuất hiện | **Từ chối** vì trùng sau JSON decoding |
| Claim aud là string hợp lệ | Chấp nhận kiểu; tiếp tục kiểm tra audience chính xác |
| Claim aud là array chỉ chứa string | Chấp nhận kiểu; tiếp tục kiểm tra audience |
| Claim aud là object hoặc array có number | **Từ chối** |
| Claim exp là JSON number hợp lệ trong miền profile | Chấp nhận kiểu; tiếp tục kiểm tra thời gian |
| Claim exp là string chứa chữ số | **Từ chối** |
| Claim exp là boolean/null/object | **Từ chối** |
| Claim exp quá lớn gây overflow/precision loss | **Từ chối** |
| Claim exp fractional khi profile yêu cầu integer | **Từ chối** |
| Claim scope là array nhưng profile yêu cầu string | **Từ chối** |
| Claim is_admin là string "false" nhưng profile yêu cầu boolean | **Từ chối** |
| Claim bắt buộc bị thiếu | **Từ chối** |
| Claim bắt buộc có giá trị null | **Từ chối** |
| Claim boolean là false | Giữ đúng false; không biến thành true hoặc coi như thiếu |
| Gateway và backend parse cùng token có duplicate member | Cả hai phải từ chối theo cùng policy |
| JWT có chữ ký hợp lệ nhưng payload có duplicate claim | **Từ chối** theo strict profile |
| JWE authentication tag không hợp lệ | **Từ chối trước khi parse plaintext** |
| Token có JSON nesting vượt giới hạn | **Từ chối** |
| Token có UTF-8 không hợp lệ hoặc Base64URL sai | **Từ chối** |

Nên chạy cùng một bộ test vector trên mọi parser/verifier được dùng tại gateway, authorization service và backend. Mục tiêu là mọi thành phần cho cùng kết quả accept/reject và cùng cách diễn giải đối với tất cả token hợp lệ.

## 16. Ghi nhớ

- JWT Claims Set và JOSE Header không nên chứa tên member trùng lặp; profile bảo mật nên từ chối duplicate thay vì phụ thuộc first-wins/last-wins.
- RFC 7519 và RFC 7515 mô tả quy tắc duplicate riêng; JSON parser tổng quát có thể có hành vi khác.
- Duplicate detection phải thực hiện trên tên sau khi giải mã JSON escape và áp dụng cho object lồng nhau có ý nghĩa bảo mật.
- Kiểm tra kiểu dữ liệu chính xác: iss/sub/jti là string; aud là string hoặc array of strings; exp/nbf/iat là NumericDate; custom claims theo schema đã định nghĩa.
- Không ép kiểu string/number/boolean, không gộp missing/null/empty/false và không tự tạo giá trị mặc định có quyền cao hơn.
- NumericDate là JSON number theo giây; giới hạn miền số, precision, clock skew và quy tắc integer/fractional theo profile.
- Chữ ký hợp lệ không bảo đảm các parser diễn giải JSON giống nhau; gateway và backend phải dùng cùng quy tắc.
- Không tin claims trước khi xác minh JWS; không xử lý JWE plaintext trước khi authentication tag hợp lệ.
- Dùng một authenticated context đã validate cho authorization; không parse lại token theo cấu hình khác.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 4](https://www.rfc-editor.org/rfc/rfc7519): registered claims, kiểu dữ liệu, NumericDate, jti và tên claim duy nhất.
- [RFC 7515 — JSON Web Signature (JWS), mục 4](https://www.rfc-editor.org/rfc/rfc7515): JOSE Header và tính duy nhất của header parameter.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): header parameter, authenticated decryption và xử lý plaintext.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format, mục 4](https://www.rfc-editor.org/rfc/rfc8259): tên object member, duplicate names và hành vi parser.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): validation theo issuer, audience, algorithm và token profile.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): kiểu và ngữ nghĩa claim trong JWT access token.
