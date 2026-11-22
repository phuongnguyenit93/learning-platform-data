# Xử lý claim trùng tên, tên khác hoa thường và dữ liệu mơ hồ

JWT mang các claims dưới dạng JSON, vì vậy cách hệ thống phân tích JSON ảnh hưởng trực tiếp đến quyết định bảo mật. Một payload có thể chứa cùng tên thuộc tính nhiều lần, tên chỉ khác chữ hoa/chữ thường, hoặc cùng một giá trị được biểu diễn bằng kiểu dữ liệu khác nhau. Nếu gateway, thư viện xác minh và service nghiệp vụ hiểu payload khác nhau, chúng có thể đưa ra những quyết định khác nhau về danh tính và quyền truy cập.

Bài học thuộc chương **Thiết kế claims** của module **Security – JSON Web Token (JWT)**. Nội dung áp dụng cho mọi nền tảng và ngôn ngữ: từ quy tắc JSON/JWT, cách parser xử lý dữ liệu mơ hồ đến thiết kế schema claims, xác minh nhất quán và kiểm thử chống parser differential.

## 1. Vì sao dữ liệu mơ hồ trong claims là vấn đề bảo mật?

Một JSON object được biểu diễn bằng các cặp tên và giá trị. Nếu một object có nhiều cách diễn giải, hai thành phần có thể hiểu cùng một token theo những cách khác nhau.

Ví dụ:

~~~json
{
  "sub": "user-42",
  "role": "user",
  "role": "admin"
}
~~~

Một bộ phân tích có thể giữ giá trị xuất hiện đầu tiên, bộ khác giữ giá trị cuối cùng, bộ khác từ chối JSON trùng tên. Nếu gateway nhìn thấy role là user nhưng service phía sau nhìn thấy role là admin, hai lớp bảo mật đã không thống nhất về chủ thể.

Các nhóm mơ hồ thường gặp:

1. **Duplicate member names:** một JSON object có cùng tên thuộc tính nhiều lần.
2. **Case variants:** tên khác nhau chỉ ở chữ hoa/chữ thường, ví dụ role và Role.
3. **Escaped member names:** cùng một tên được viết bằng ký tự trực tiếp hoặc escape Unicode, ví dụ iss và \u0069ss.
4. **Type ambiguity:** cùng một claim được biểu diễn bằng string, number, boolean, array hoặc null ở các token khác nhau.
5. **Conflicting claims:** nhiều claim khác tên nhưng cùng diễn đạt một ý nghĩa bảo mật, ví dụ role, roles, groups và permissions.
6. **Parser differential:** các thành phần xử lý cùng dữ liệu nhưng khác quy tắc parse, chuẩn hóa hoặc ép kiểu.

Trong xác thực và phân quyền, dữ liệu mơ hồ có thể dẫn tới:

- Bypass kiểm tra quyền hoặc leo thang đặc quyền.
- Nhầm issuer, subject, audience hoặc loại token.
- Sai quyết định giữa API gateway và resource server.
- Sai liên kết tài khoản hoặc tenant.
- Bỏ qua claim hết hạn, claim bắt buộc hoặc claim bị thu hồi.
- Khó điều tra sự cố vì log và service nghiệp vụ ghi nhận các giá trị khác nhau.

## 2. Quy tắc JSON và JWT về tên thuộc tính trùng nhau

### 2.1. JSON khuyến nghị tên trong object phải duy nhất

Theo RFC 8259, tên thành viên của JSON object nên duy nhất. Khi một object có tên lặp, hành vi của các parser có thể khác nhau: có parser giữ giá trị cuối, có parser giữ giá trị đầu, có parser báo lỗi, và có parser trả về tất cả cặp tên/giá trị.

Ví dụ JSON có tên trùng:

~~~json
{
  "iss": "https://identity.example.org",
  "iss": "https://attacker.example.net"
}
~~~

JSON có thể được một số thư viện chấp nhận, nhưng các thành phần không nhất thiết thống nhất giá trị issuer.

### 2.2. JWT quy định claim names phải duy nhất

RFC 7519 quy định các Claim Names trong JWT Claims Set **MUST be unique**. Parser JWT phải:

- Từ chối JWT có Claim Names trùng nhau; hoặc
- Dùng parser JSON chỉ trả về thành viên trùng tên xuất hiện cuối cùng theo thứ tự văn bản, như quy tắc được nêu trong Section 15.12 (Object) của ECMAScript 5.1.

Vì vậy, JWT có quy tắc rõ hơn khuyến nghị chung của JSON. Dù tiêu chuẩn cho phép cách xử lý thành viên cuối cùng, chính sách an toàn và dễ tương thích nhất trong hệ thống mới là **từ chối mọi object có tên trùng**, đặc biệt khi token đi qua nhiều parser hoặc thành phần bảo mật.

Quy tắc uniqueness cũng áp dụng cho JOSE Header. RFC 7515 yêu cầu tên tham số trong JOSE Header phải duy nhất; bên nhận phải từ chối tham số trùng hoặc dùng parser trả về thành viên cuối cùng theo quy tắc nêu trong tiêu chuẩn.

### 2.3. Không chỉ kiểm tra trùng ở payload cấp cao nhất

Payload có thể chứa object lồng nhau:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "profile": {
    "department": "sales",
    "department": "finance"
  }
}
~~~

Nếu ứng dụng sử dụng object profile để quyết định quyền, trùng tên bên trong vẫn tạo ra cách hiểu khác nhau. Nên áp dụng chính sách JSON nghiêm ngặt cho mọi object trong payload, bao gồm object lồng nhau và object trong array.

## 3. Phân biệt duplicate name với tên chỉ khác hoa thường

### 3.1. Tên claim phân biệt chữ hoa/chữ thường

JWT Claim Names là các chuỗi phân biệt chữ hoa/chữ thường. Vì vậy:

~~~json
{
  "sub": "user-42",
  "Sub": "admin",
  "SUB": "root"
}
~~~

Theo quy tắc tên JSON/JWT, sub, Sub và SUB là ba tên khác nhau, không phải một claim bị lặp. Tuy nhiên, đây là thiết kế dễ gây nhầm lẫn nếu các thư viện hoặc tầng nghiệp vụ áp dụng so sánh không phân biệt hoa thường.

Ví dụ:

- JWT validator tra cứu chính xác sub và nhận user-42.
- Một lớp mapping tự động chuyển tên thuộc tính về chữ thường, khiến Sub hoặc SUB va chạm với sub.
- Một lớp nghiệp vụ lại chọn giá trị khác do thứ tự mapping.

Kết quả là các thành phần có thể gắn request với chủ thể khác nhau.

**Nguyên tắc:** giữ nguyên tên claim theo đúng chuẩn và profile đã định nghĩa; không tự động lowercase, uppercase hoặc case-fold tên claim trước khi xác minh và sử dụng.

### 3.2. Case variants không phải cách ghi thay thế cho registered claim

Các registered claims có tên chuẩn như:

| Tên chuẩn | Tên khác hoa thường | Ý nghĩa |
| --- | --- | --- |
| iss | ISS, Iss | Issuer |
| sub | SUB, Sub | Subject |
| aud | AUD, Aud | Audience |
| exp | EXP, Exp | Expiration time |
| nbf | NBF, Nbf | Not before |
| iat | IAT, Iat | Issued at |
| jti | JTI, Jti | JWT ID |

Chỉ tên chuẩn có ý nghĩa registered claim tương ứng. EXP không thay thế exp; Sub không thay thế sub. Nếu profile của ứng dụng không định nghĩa các claim case variant, không sử dụng chúng làm đầu vào cho quyết định bảo mật.

Để tránh nhầm lẫn, có thể dùng schema allowlist cho các claim được phép và từ chối tên gần giống claim đặc quyền đã biết nếu chúng xuất hiện ngoài hợp đồng.

### 3.3. Không tự chuẩn hóa tên claim

Các thao tác sau có thể làm thay đổi cách nhận diện tên:

- Chuyển toàn bộ tên thành chữ thường hoặc chữ hoa.
- Xóa khoảng trắng ở đầu/cuối.
- Unicode normalization.
- So sánh không phân biệt dấu hoặc ký tự tương tự.
- Thay thế dấu gạch ngang, gạch dưới hoặc dấu chấm theo quy ước riêng.

JSON so sánh tên member như chuỗi Unicode; JWT Claim Names phân biệt hoa thường. Các tên có ký tự Unicode nhìn giống nhau không nhất thiết là cùng một chuỗi. Ví dụ ký tự Latin thường và ký tự Cyrillic tương tự về hình dạng có thể có code point khác nhau.

Trong thiết kế claims, ưu tiên tên ASCII theo profile đã công bố. Với public claim names, dùng tên collision-resistant như URI theo RFC 7519; với private claim names, thống nhất schema giữa issuer và resource server. Không tự chuẩn hóa tên trong một tầng rồi giữ nguyên ở tầng khác.

## 4. Escape Unicode có thể tạo tên trùng sau khi parse

JSON cho phép biểu diễn ký tự bằng escape Unicode. Vì vậy, hai cách viết khác nhau trong văn bản có thể giải mã thành cùng một tên member.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org",
  "\u0069ss": "https://attacker.example.net"
}
~~~

Ký tự Unicode escape trong tên thứ hai có thể giải mã thành ký tự i. Sau khi giải mã JSON string, cả hai tên đều trở thành iss. Do đó đây là duplicate member name theo ý nghĩa dữ liệu, dù chuỗi byte trong JSON khác nhau.

Một kiểm tra chỉ tìm chuỗi văn bản iss trước khi giải mã escape có thể bỏ sót trường hợp này. Duplicate detection phải được thực hiện trên **tên member sau khi JSON escape đã được giải mã**, trước khi ứng dụng sử dụng object cho xác thực hoặc phân quyền.

### 4.1. Unicode normalization và ký tự nhìn giống nhau

Không nên tự áp dụng Unicode normalization để biến các claim names thành tương đương, trừ khi profile có quy tắc cụ thể. JSON/JWT không mặc định coi mọi chuỗi nhìn giống nhau là cùng tên.

Rủi ro thực tế là người vận hành khó phân biệt tên claim bằng mắt, còn parser so sánh theo code point. Để tránh:

- Ưu tiên claim names ASCII.
- Không tạo private claims bằng ký tự có hình dạng dễ nhầm.
- Không cho phép tên claim tùy ý ảnh hưởng trực tiếp đến quyền.
- Hiển thị tên claim ở dạng escaped/code point trong công cụ audit khi cần điều tra.
- Dùng schema rõ ràng để chỉ chấp nhận các tên đã định nghĩa.

## 5. Parser differential: cùng token, nhiều cách hiểu

Parser differential xảy ra khi hai thành phần diễn giải cùng một JSON/JWT khác nhau. Đây là rủi ro đặc biệt quan trọng khi token đi qua gateway, proxy, authorization middleware, service nghiệp vụ hoặc nhiều ngôn ngữ.

### 5.1. Khác nhau về duplicate handling

Xét payload:

~~~json
{
  "sub": "user-42",
  "role": "user",
  "role": "admin"
}
~~~

Giả sử:

| Thành phần | Cách xử lý giả định | Giá trị role |
| --- | --- | --- |
| Gateway | Giữ giá trị đầu tiên | user |
| Service nghiệp vụ | Giữ giá trị cuối cùng | admin |

Gateway cho phép request vì thấy role user, nhưng service thực thi lại dùng role admin. Nếu token được issuer tin cậy ký nhưng payload có duplicate do lỗi phát hành hoặc dữ liệu bị tạo có chủ đích, sự khác biệt parser có thể biến thành lỗ hổng quyền.

Không nên dựa vào việc parser hiện tại giữ giá trị đầu hoặc service luôn lấy giá trị cuối. Các thư viện có thể thay đổi phiên bản hoặc khác nhau giữa runtime. Chính sách thống nhất nên là từ chối JSON trùng tên.

### 5.2. Khác nhau về hoa thường

Một gateway có thể tra cứu role theo tên chính xác, trong khi lớp mapping của service chuyển tất cả tên thành chữ thường. Token có cả role và Role khi đó có thể gây va chạm ở service dù gateway không thấy duplicate.

Giải pháp là giữ tên chính xác, dùng schema thống nhất và không dùng cơ chế binding tự động không rõ quy tắc cho claims có ý nghĩa bảo mật.

### 5.3. Khác nhau về kiểu dữ liệu

Một thành phần có thể chấp nhận exp dạng số, thành phần khác tự chuyển chuỗi thành số. Một thành phần có thể coi admin: true là boolean, thành phần khác coi "true" là chuỗi truthy. Đây là nguồn gây sai khác trong quyết định bảo mật.

Ví dụ:

~~~json
{
  "exp": "2000000000",
  "admin": "false",
  "aud": ["https://billing-api.example.org"]
}
~~~

Nếu một parser ép exp từ string thành number và một parser khác từ chối, hoặc nếu một ngôn ngữ coi chuỗi false là truthy, các lớp có thể không đồng ý về trạng thái token và quyền.

**Không tự ép kiểu claims bảo mật.** Kiểu dữ liệu phải đúng schema đã công bố.

## 6. Xác định kiểu dữ liệu rõ ràng cho từng claim

JWT Claims Set là JSON object, nhưng từng claim có kiểu dữ liệu và ngữ nghĩa riêng. Không nên để issuer và resource server tự suy đoán kiểu.

### 6.1. Các registered claims quan trọng

| Claim | Kiểu dữ liệu theo JWT | Lưu ý xác minh |
| --- | --- | --- |
| iss | String | So khớp issuer theo định danh đã cấu hình |
| sub | String | Định danh subject trong ngữ cảnh issuer |
| aud | String hoặc array of strings | Resource server phải có mặt trong audience |
| exp | NumericDate (number) | Không tự nhận chuỗi ngày hoặc chuỗi số |
| nbf | NumericDate (number) | Kiểm tra thời điểm bắt đầu hiệu lực |
| iat | NumericDate (number) | Dùng theo chính sách tuổi token |
| jti | String | Định danh JWT; không tự tạo trạng thái thu hồi |

Các kiểu trên phải được kiểm tra theo RFC 7519 và profile token mà API chấp nhận. Không dùng giá trị null, chuỗi rỗng hoặc kiểu khác thay cho claim bắt buộc.

### 6.2. NumericDate và giới hạn số

exp, nbf và iat dùng NumericDate: số giây kể từ Unix epoch theo quy định của RFC 7519. NumericDate có thể là số nguyên hoặc số có phần thập phân; không nên mặc định mọi thư viện đều xử lý số rất lớn giống nhau.

Những rủi ro cần xem xét:

- Một runtime có thể dùng kiểu số dấu phẩy động với độ chính xác hữu hạn.
- Một giá trị quá lớn có thể tràn, bị làm tròn hoặc được chuyển thành infinity ở tầng ứng dụng.
- Một parser có thể chấp nhận chuỗi 2000000000 rồi ép kiểu, trong khi parser khác từ chối.
- Các JSON token đặc biệt như NaN và Infinity không phải giá trị JSON hợp lệ theo RFC 8259.

Chọn giới hạn NumericDate phù hợp với thời gian thực tế của hệ thống, từ chối giá trị ngoài phạm vi hỗ trợ và xử lý độ lệch đồng hồ theo chính sách. Không ép chuỗi thành số hoặc cắt phần thập phân một cách tùy tiện.

### 6.3. Audience là string hoặc array, không phải bất kỳ kiểu nào

RFC 7519 cho phép aud là một string hoặc array các string. Ví dụ hợp lệ:

~~~json
{
  "aud": "https://billing-api.example.org"
}
~~~

hoặc:

~~~json
{
  "aud": [
    "https://billing-api.example.org",
    "https://reporting-api.example.org"
  ]
}
~~~

Các dạng sau không nên tự động chuyển đổi:

~~~json
{
  "aud": 42
}
~~~

~~~json
{
  "aud": ["https://billing-api.example.org", 42]
}
~~~

Nếu profile của hệ thống chỉ chấp nhận một audience, có thể quy định chặt hơn JWT tổng quát và từ chối dạng array. Nếu chấp nhận cả hai, chuẩn hóa chúng vào một cấu trúc nội bộ duy nhất **sau khi parse và xác minh kiểu**, không dùng ép kiểu ngầm.

### 6.4. Claims tùy chỉnh cũng cần schema

Ví dụ profile nội bộ định nghĩa:

~~~json
{
  "tenant_id": "company-7",
  "roles": ["billing-reader"],
  "is_verified": true,
  "risk_level": 2
}
~~~

Schema phải quy định rõ:

| Claim | Kiểu mong đợi | Quy tắc |
| --- | --- | --- |
| tenant_id | String | Không rỗng; phải thuộc tenant mà subject được phép truy cập |
| roles | Array of strings | Chỉ chứa role đã đăng ký; không chấp nhận object/string thay thế |
| is_verified | Boolean | Không chuyển true/false dạng chuỗi thành boolean |
| risk_level | Integer trong miền xác định | Từ chối số thập phân, chuỗi hoặc giá trị ngoài miền |

Ví dụ này là schema minh họa, không phải các registered claims của JWT. Issuer và resource server cần thống nhất phiên bản schema và cách xử lý khi thêm claim mới.

## 7. Giá trị thiếu, null, rỗng và giá trị mặc định

Các trạng thái sau không giống nhau:

~~~json
{}
~~~

~~~json
{
  "tenant_id": null
}
~~~

~~~json
{
  "tenant_id": ""
}
~~~

~~~json
{
  "tenant_id": "company-7"
}
~~~

Chúng lần lượt biểu diễn: không có claim, claim có giá trị null, claim là chuỗi rỗng và claim có chuỗi định danh. Nếu ứng dụng tự chuyển tất cả thành một giá trị mặc định, có thể vô tình cấp quyền cho trường hợp thiếu dữ liệu.

Nguyên tắc:

- Claim bắt buộc phải có mặt; thiếu thì từ chối.
- Nếu null không được schema cho phép, từ chối thay vì coi như không có.
- Chuỗi rỗng không phải định danh hợp lệ nếu schema yêu cầu non-empty.
- Không tự điền role hoặc tenant mặc định có quyền cao.
- Không dùng truthiness để kiểm tra boolean hoặc quyền.
- Quy định rõ cách xử lý unknown claims; claim không được định nghĩa không được tự động cấp quyền.

## 8. Nhiều claim diễn đạt cùng một ý nghĩa

Không phải mọi mơ hồ đều là duplicate key. Hai claim khác tên có thể cùng mô tả quyền:

~~~json
{
  "role": "user",
  "roles": ["admin"],
  "groups": ["superuser"],
  "permissions": ["invoice:write"]
}
~~~

JSON không coi đây là duplicate names. Tuy nhiên, nếu gateway dùng role, một service dùng roles, còn một service khác suy quyền từ groups, hệ thống có thể có nhiều nguồn sự thật không thống nhất.

### 8.1. Chọn một nguồn quyền có thẩm quyền

Với mỗi quyết định bảo mật, phải xác định claim hoặc policy nào là nguồn có thẩm quyền:

- Role được định nghĩa bởi issuer hay bởi resource server?
- Scope có phải quyền gọi API hay chỉ là nhãn mô tả?
- Claim tenant có được phép quyết định phạm vi dữ liệu không?
- Nếu role và permission mâu thuẫn, thành phần nào có quyền quyết định?
- Quyền có cần kiểm tra lại từ nguồn dữ liệu hiện hành không?

Không hợp nhất quyền bằng cách lấy tất cả claim có vẻ thuận lợi nhất. Ví dụ, không lấy quyền cao nhất từ role, groups hoặc permissions mà không có quy tắc ưu tiên được định nghĩa.

### 8.2. Tránh claim names dễ va chạm

RFC 7519 phân biệt:

- **Registered Claim Names:** tên được đăng ký trong tiêu chuẩn.
- **Public Claim Names:** tên được chọn theo cách collision-resistant, ví dụ dùng URI.
- **Private Claim Names:** tên do các bên thỏa thuận, có nguy cơ va chạm giữa các bên.

Trong hệ thống tích hợp nhiều issuer hoặc đối tác, nên dùng tên public claim có namespace rõ ràng cho extension. Với private claims, tài liệu hóa schema, chủ sở hữu, kiểu dữ liệu và phiên bản; tránh dùng tên chung chung như role, type, status nếu không có quy ước thống nhất.

## 9. Header JOSE cũng phải được xử lý nghiêm ngặt

Vấn đề duplicate và mơ hồ không chỉ nằm trong payload. JOSE Header có các tham số bảo mật như alg, kid, typ, cty, crit, enc và zip.

Ví dụ header trùng alg:

~~~json
{
  "alg": "RS256",
  "kid": "trusted-key",
  "alg": "none"
}
~~~

Các parser có thể diễn giải khác nhau. Vì alg quyết định thuật toán xác minh, sự khác biệt có thể ảnh hưởng trực tiếp tới an toàn token.

Quy tắc cần áp dụng:

1. Tên JOSE Header Parameters phải duy nhất.
2. Từ chối header có duplicate parameter names theo chính sách an toàn.
3. Chỉ chấp nhận thuật toán trong allowlist được cấu hình ngoài token.
4. kid chỉ dùng chọn khóa trong nguồn đã tin cậy; không cho token tự chỉ định nguồn khóa tùy ý.
5. Kiểm tra typ và profile token để phân biệt loại token khi cần.
6. Xử lý crit đúng theo extension đã hỗ trợ; từ chối critical parameter không hiểu.
7. Không tự diễn giải lại header theo quy tắc khác ở gateway và resource server.

Header có thể phải được parse trước khi xác minh chữ ký để tìm ứng viên khóa, nhưng mọi giá trị header khi đó vẫn là dữ liệu chưa tin cậy. Chỉ sử dụng chúng trong phạm vi chọn khóa/thuật toán đã được cấu hình; không cấp quyền hoặc tin issuer từ header chưa xác minh.

## 10. Quy trình xử lý claims an toàn

Một pipeline an toàn nên bảo đảm mọi thành phần dùng cùng một cách hiểu dữ liệu:

~~~mermaid
flowchart TD
    A["Nhận compact JWT"] --> B["Kiểm tra kích thước và cấu trúc"]
    B --> C["Parse header bằng JSON parser nghiêm ngặt"]
    C --> D{"Header có duplicate/invalid member?"}
    D -- "Có" --> X["Từ chối"]
    D -- "Không" --> E["Chọn khóa và thuật toán từ cấu hình tin cậy"]
    E --> F["Xác minh chữ ký/MAC"]
    F --> G{"Mật mã hợp lệ?"}
    G -- "Không" --> X
    G -- "Có" --> H["Parse payload với duplicate detection"]
    H --> I{"JSON hợp lệ, tên duy nhất?"}
    I -- "Không" --> X
    I -- "Có" --> J["Kiểm tra schema và kiểu claims"]
    J --> K{"Schema hợp lệ?"}
    K -- "Không" --> X
    K -- "Có" --> L["Kiểm tra iss, aud, thời hạn và profile"]
    L --> M["Đánh giá scope và quyền trên tài nguyên"]
    M --> N["Tạo security context từ claims đã xác minh"]
~~~

### 10.1. Các bước kiểm tra cụ thể

1. **Giới hạn đầu vào:** giới hạn kích thước token, độ sâu JSON, số lượng member, độ dài tên/giá trị và thời gian parse để giảm DoS.
2. **Parse header nghiêm ngặt:** từ chối JSON sai cú pháp, duplicate parameter names, encoding không hợp lệ và cấu trúc không được hỗ trợ.
3. **Chọn thuật toán/khóa theo cấu hình:** header chưa xác minh chỉ là dữ liệu gợi ý; allowlist và issuer trust phải nằm ở cấu hình tin cậy.
4. **Xác minh JWS/JWE:** xác minh mật mã theo đúng loại token và profile.
5. **Parse payload nghiêm ngặt:** phát hiện duplicate member names sau khi giải mã JSON escapes; không âm thầm giữ first/last.
6. **Kiểm tra schema:** xác nhận claim bắt buộc, tên chính xác, kiểu, miền giá trị, độ dài và quan hệ giữa claims.
7. **Kiểm tra claims chuẩn:** issuer, audience, expiration, not-before, issued-at và token type theo hợp đồng.
8. **Kiểm tra quyền:** không dùng claim chưa xác minh; đánh giá scope, tenant, subject, actor và quyền tài nguyên.
9. **Chuẩn hóa nội bộ một lần:** chỉ sau khi token đã hợp lệ và schema được xác nhận, chuyển claims sang một cấu trúc nội bộ có kiểu rõ ràng.
10. **Chuyển cùng ngữ cảnh đã xác minh:** gateway và service phía sau không tự parse lại theo schema hoặc quy tắc khác nếu có thể truyền security context đáng tin qua ranh giới đã bảo vệ.

### 10.2. Pseudocode trung lập ngôn ngữ

~~~text
function validate_access_token(compact_token, trusted_profile):
    enforce_size_and_resource_limits(compact_token)

    header = parse_json_strict(
        decode_protected_header(compact_token),
        reject_duplicate_names = true
    )

    require(header.alg in trusted_profile.allowed_algorithms)
    key = select_key_from_trusted_issuer_jwks(
        trusted_profile.issuer,
        header.kid
    )
    require(verify_jws(compact_token, key, trusted_profile.allowed_algorithms))

    payload_bytes = get_verified_payload_bytes(compact_token)
    claims = parse_json_strict(
        payload_bytes,
        reject_duplicate_names = true
    )

    validate_claim_schema(claims, trusted_profile.schema)
    require(claims.iss == trusted_profile.issuer)
    require(audience_contains(claims.aud, trusted_profile.resource_id))
    require(valid_time_claims(claims))
    require(valid_token_profile(claims, header, trusted_profile))

    context = build_typed_security_context(claims)
    return authorize_request(context)
~~~

Đây là pseudocode mô tả nguyên tắc, không phải một thư viện JWT hoàn chỉnh. Các hàm parse, verify và validate phải tuân thủ profile thực tế, xử lý đúng JWS/JWE và không dùng dữ liệu chưa xác minh để cấp quyền.

## 11. Thiết kế schema claims thống nhất

Một schema claims tốt nên quy định tối thiểu:

| Thuộc tính schema | Câu hỏi cần trả lời |
| --- | --- |
| Tên claim | Tên chính xác là gì? Có phân biệt hoa thường không? Có namespace không? |
| Kiểu dữ liệu | String, number, boolean, array hay object? |
| Bắt buộc/tùy chọn | Claim có thể vắng mặt không? Null có được phép không? |
| Miền giá trị | Độ dài, range, enum hoặc pattern hợp lệ là gì? |
| Nguồn có thẩm quyền | Issuer, client hay resource server được phép quyết định giá trị? |
| Ý nghĩa bảo mật | Claim được dùng cho xác thực, phân quyền, định tuyến hay chỉ hiển thị? |
| Phiên bản | Khi thay đổi schema, token cũ được xử lý thế nào? |
| Xử lý unknown | Claim không biết được bỏ qua, ghi nhận hay từ chối? Có được ảnh hưởng quyền không? |

### 11.1. Ví dụ schema profile minh họa

~~~yaml
token_profile: billing_access_v1
claims:
  iss:
    type: string
    required: true
  sub:
    type: string
    required: true
  aud:
    type: string_or_array_of_strings
    required: true
  exp:
    type: numeric_date
    required: true
  scope:
    type: space_delimited_string
    required: true
  tenant_id:
    type: non_empty_string
    required: true
  roles:
    type: array_of_strings
    required: false
json_policy:
  duplicate_member_names: reject
  claim_names: exact_case_sensitive
  implicit_type_coercion: reject
~~~

Đây là ví dụ profile nội bộ để minh họa cách tài liệu hóa schema; không phải schema bắt buộc của mọi JWT. Một profile có thể chặt hơn RFC JWT tổng quát, miễn là issuer và resource server cùng tuân thủ.

### 11.2. Quản lý thay đổi schema

Khi thêm hoặc đổi claim:

- Không đổi kiểu của claim đang được dùng mà không có kế hoạch tương thích.
- Không tái sử dụng tên claim cũ với ý nghĩa khác.
- Tăng phiên bản profile hoặc dùng một claim phiên bản được quy định rõ.
- Xác định cách xử lý token được phát hành trước khi thay đổi.
- Kiểm tra tất cả resource server, gateway, analytics và consumer có parse token.
- Không cho một claim mới chưa được hiểu làm thay đổi quyền mặc định.

## 12. Kiểm thử các trường hợp mơ hồ

Kiểm thử không chỉ xác nhận token hợp lệ được chấp nhận. Cần tạo các token thử nghiệm có cấu trúc sai, tên trùng, case variant và kiểu dữ liệu không đúng để xác nhận mọi thành phần có cùng chính sách.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Duplicate iss trong payload | Từ chối |
| Duplicate role với hai giá trị khác nhau | Từ chối |
| iss và \u0069ss cùng xuất hiện | Từ chối sau khi giải mã JSON escape |
| Duplicate alg trong JOSE header | Từ chối |
| sub và Sub cùng xuất hiện | Không coi là cùng claim; từ chối nếu Sub không nằm trong schema/allowlist |
| exp là string thay vì NumericDate | Từ chối |
| aud là number hoặc array trộn string và number | Từ chối |
| admin là chuỗi false trong khi schema yêu cầu boolean | Từ chối |
| Claim bắt buộc bị thiếu | Từ chối |
| Claim bắt buộc có giá trị null hoặc chuỗi rỗng | Từ chối theo schema |
| JSON có NaN, Infinity hoặc cú pháp sai | Từ chối |
| Object lồng nhau có duplicate member | Từ chối |
| Gateway và resource server parse cùng token | Kết quả phải thống nhất; token mơ hồ phải bị từ chối ở mọi nơi |
| Unknown claim cố gắng nâng quyền | Không được dùng để cấp quyền |

### 12.1. Kiểm thử parser differential

Với kiến trúc có gateway và nhiều service:

1. Chuẩn bị corpus token có duplicate keys, escaped names, case variants và type mismatch.
2. Chạy cùng corpus qua mọi thành phần parse hoặc xác minh token.
3. So sánh kết quả chấp nhận/từ chối và security context được tạo ra.
4. Nếu một thành phần chấp nhận token mà thành phần khác từ chối hoặc diễn giải khác, coi đó là lỗi cần xử lý.
5. Khóa phiên bản parser và thư viện JWT; chạy lại bộ kiểm thử khi nâng cấp.
6. Kiểm tra cả nested JSON claims, JOSE headers và các serialization được hệ thống hỗ trợ.

Mục tiêu là có một cách diễn giải duy nhất. Trong hệ thống phân tán, cách đơn giản nhất thường là từ chối dữ liệu mơ hồ ngay tại ranh giới xác minh đầu tiên và bảo đảm các thành phần sau nhận security context đã được xác thực.

## 13. Tình huống thực tế

### Tình huống A — Gateway và service chọn hai role khác nhau

Issuer phát hành payload có hai claim role. Gateway giữ giá trị đầu tiên là user; service phía sau giữ giá trị cuối là admin. Gateway cho qua nhưng service thực thi quyền quản trị.

**Bài học:** duplicate claim names phải bị phát hiện và từ chối; không dựa vào mặc định parser.

### Tình huống B — Claim viết hoa bị ánh xạ thành claim chuẩn

Token chứa sub và Sub. Validator dùng so sánh phân biệt hoa thường, còn lớp mapping tự chuyển tên thành chữ thường. Hai giá trị có thể va chạm và gây nhầm chủ thể.

**Bài học:** tên claim phân biệt hoa thường; không case-fold hoặc chuẩn hóa tên trước khi áp dụng schema.

### Tình huống C — Tên claim trùng qua Unicode escape

Payload chứa iss và \u0069ss. Bộ lọc kiểm tra raw text chỉ tìm iss và không nhận ra tên thứ hai. JSON parser giải mã cả hai thành cùng tên.

**Bài học:** duplicate detection phải thực hiện sau khi giải mã escape của JSON string.

### Tình huống D — Chuỗi false được hiểu là true

Issuer gửi admin: "false" vì lỗi schema. Một lớp kiểm tra string chính xác và từ chối, nhưng service khác dùng truthiness và coi chuỗi không rỗng là true.

**Bài học:** boolean phải là JSON boolean; không ép kiểu và không dùng truthiness cho quyết định quyền.

### Tình huống E — exp được tự động chuyển từ string sang number

Token có exp: "2000000000". Một thư viện tự chuyển thành số và chấp nhận; thư viện khác từ chối theo kiểu NumericDate. Hệ thống có thể đưa ra quyết định hết hạn khác nhau.

**Bài học:** xác định schema NumericDate và từ chối kiểu sai; không dựa vào coercion.

### Tình huống F — Nhiều claim quyền mâu thuẫn

Token có role: "user", roles: ["admin"] và permissions: ["invoice:write"]. Các service khác nhau chọn claim khác nhau để phân quyền.

**Bài học:** xác định một nguồn quyền có thẩm quyền, tài liệu hóa quan hệ giữa claims và kiểm tra quyền trên tài nguyên.

## 14. Checklist xử lý claims mơ hồ

### JSON và JOSE parsing

- [ ] Từ chối JSON object có duplicate member names.
- [ ] Duplicate detection thực hiện sau khi giải mã JSON escape.
- [ ] Từ chối duplicate parameters trong JOSE Header.
- [ ] Parse JSON nghiêm ngặt; từ chối cú pháp mở rộng hoặc giá trị không hợp lệ.
- [ ] Giới hạn kích thước, độ sâu và số lượng member để giảm DoS.
- [ ] Không parse cùng token bằng các quy tắc khác nhau giữa gateway và service.

### Tên claim

- [ ] Giữ nguyên tính phân biệt hoa thường của claim names.
- [ ] Không tự lowercase, trim hoặc Unicode-normalize tên claim.
- [ ] Ưu tiên tên ASCII và namespace collision-resistant cho public claims.
- [ ] Từ chối claim gần giống claim đặc quyền nếu không thuộc schema.
- [ ] Tài liệu hóa private claims và tránh nhiều claim cùng diễn đạt một quyền.

### Kiểu và ý nghĩa dữ liệu

- [ ] Quy định kiểu cho từng claim.
- [ ] Không ép kiểu string/number/boolean/array/object.
- [ ] Kiểm tra NumericDate trong miền số hỗ trợ.
- [ ] Xử lý aud theo đúng string hoặc array of strings.
- [ ] Phân biệt missing, null, empty và default.
- [ ] Không dùng unknown claims để nâng quyền.
- [ ] Xác định nguồn có thẩm quyền khi nhiều claim quyền mâu thuẫn.

### Xác minh và kiểm thử

- [ ] Xác minh chữ ký/MAC trước khi sử dụng claims.
- [ ] Kiểm tra issuer, audience, thời hạn, token profile và schema.
- [ ] Chỉ tạo security context từ claims đã xác minh.
- [ ] Có bộ kiểm thử duplicate, escaped names, case variants và type confusion.
- [ ] So sánh hành vi parser giữa mọi thành phần xử lý token.
- [ ] Chạy lại kiểm thử khi thay đổi thư viện JSON/JWT hoặc runtime.

## 15. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| JWT có cho phép Claim Names trùng nhau không? | **Không.** RFC 7519 yêu cầu tên claim phải duy nhất; parser phải từ chối hoặc dùng quy tắc thành viên cuối theo tiêu chuẩn. |
| role và Role có phải duplicate claim không? | **Không.** Tên claim phân biệt hoa thường, nhưng case variant không được tự động coi là claim hợp lệ tương đương. |
| iss và \u0069ss có thể trở thành duplicate sau parse không? | **Có.** Cả hai giải mã thành cùng chuỗi iss. |
| Chỉ tìm duplicate bằng cách quét raw JSON text có đủ không? | **Không.** Cần xét tên member sau khi giải mã JSON escape. |
| exp dạng string có tương đương exp dạng number không? | **Không.** NumericDate phải là JSON number; không tự ép chuỗi thành số. |
| Claim jti hoặc một claim bất kỳ có tự ngăn duplicate không? | **Không.** Tính duy nhất của member phải được kiểm tra khi parse JSON. |
| Nếu gateway giữ giá trị đầu và service giữ giá trị cuối thì có thể an toàn vì cả hai đều parse thành công không? | **Không.** Đây là parser differential; token mơ hồ cần bị từ chối. |
| aud có thể là mảng không? | **Có.** JWT cho phép string hoặc array of strings; profile có thể quy định chặt hơn. |
| Có nên dùng roles, groups và permissions thay thế nhau tùy service? | **Không.** Cần schema và nguồn quyền có thẩm quyền thống nhất. |

## 16. Ghi nhớ

- JWT Claims Set là JSON object; tên claim phải duy nhất. Từ chối duplicate names là chính sách an toàn và dễ tương thích.
- Duplicate detection phải xử lý tên sau khi JSON escape được giải mã, không chỉ so khớp raw text.
- Claim names phân biệt hoa thường. sub khác Sub; không tự case-fold hoặc chuẩn hóa tên.
- Kiểu dữ liệu có ý nghĩa bảo mật. NumericDate là number; aud là string hoặc array of strings; không ép kiểu ngầm.
- Missing, null, empty và default là các trạng thái khác nhau; quy định rõ trong schema.
- Không để nhiều claims quyền mâu thuẫn mà không có nguồn có thẩm quyền.
- JOSE Header cũng cần tên tham số duy nhất, allowlist thuật toán và nguồn khóa tin cậy.
- Gateway, validator và resource server phải có cùng cách diễn giải; dữ liệu mơ hồ phải bị từ chối trước khi cấp quyền.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT), Section 4](https://www.rfc-editor.org/rfc/rfc7519#section-4)
- [RFC 7515 – JSON Web Signature (JWS), Section 4](https://www.rfc-editor.org/rfc/rfc7515#section-4)
- [RFC 8259 – The JavaScript Object Notation (JSON) Data Interchange Format, Section 4](https://www.rfc-editor.org/rfc/rfc8259#section-4)
- [RFC 8259 – String Comparison, Section 8.3](https://www.rfc-editor.org/rfc/rfc8259#section-8.3)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
