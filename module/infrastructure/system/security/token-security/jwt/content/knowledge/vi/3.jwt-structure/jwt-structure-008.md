# Kiểu dữ liệu JSON, giá trị null và thuộc tính bị thiếu

## 1. Vì sao kiểu dữ liệu và giá trị trong JSON quan trọng với JWT?

JWT mang các thông tin gọi là *claims*. Với JWT thông thường, claims được biểu diễn bằng một **JSON object**. JSON không chỉ có tên và giá trị; mỗi giá trị còn có kiểu dữ liệu cụ thể. Một claim có thể là string, number, boolean, null, object hoặc array.

Khi hệ thống nhận token, việc parse JSON thành công chưa đủ. Ứng dụng cần kiểm tra:

- Claim có tồn tại hay không.
- Claim có kiểu dữ liệu đúng theo đặc tả hoặc hợp đồng ứng dụng hay không.
- Giá trị có nằm trong miền được phép hay không.
- Giá trị null, rỗng hoặc mặc định có được chấp nhận trong ngữ cảnh đó hay không.

Ví dụ, các payload sau không tương đương:

~~~json
{"active": true}
~~~

~~~json
{"active": "true"}
~~~

~~~json
{"active": 1}
~~~

~~~json
{"active": null}
~~~

Chúng lần lượt chứa boolean, string, number và null. Nếu ứng dụng chỉ kiểm tra giá trị theo cách ép kiểu lỏng lẻo, các hệ thống có thể diễn giải token khác nhau và tạo ra lỗi xác thực hoặc phân quyền.

**Nguyên tắc:** kiểm tra kiểu dữ liệu trước khi dùng claim. Không tự động chuyển string thành number, number thành boolean hoặc null thành giá trị mặc định trừ khi hợp đồng của ứng dụng quy định rõ.

## 2. Sáu loại giá trị trong JSON

JSON định nghĩa các kiểu giá trị sau:

| Kiểu JSON | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **String** | "customer-42" | Chuỗi ký tự |
| **Number** | 1893456300, 19.5 | Giá trị số |
| **Boolean** | true, false | Giá trị đúng/sai |
| **Null** | null | Giá trị null được biểu diễn tường minh |
| **Object** | {"region":"apac"} | Tập hợp các cặp tên/giá trị |
| **Array** | ["reader","auditor"] | Danh sách giá trị có thứ tự |

Ví dụ một JWT Claims Set kết hợp nhiều kiểu:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "active": true,
  "login_count": 12,
  "profile": {
    "region": "apac",
    "verified": false
  },
  "roles": ["reader", "auditor"],
  "middle_name": null
}
~~~

Trong ví dụ:

- iss và sub là string.
- active và profile.verified là boolean.
- login_count là number.
- profile là object lồng nhau.
- roles là array các string.
- middle_name có mặt nhưng giá trị là null.

JSON không có kiểu riêng cho date, timestamp, UUID hoặc binary. Những dữ liệu đó cần được biểu diễn theo quy ước của giao thức, thường là string hoặc number. Ví dụ, các claim thời gian JWT dùng NumericDate, không phải chuỗi ngày giờ tùy ý.

## 3. Phân biệt thuộc tính bị thiếu, null và giá trị rỗng

Đây là một trong những điểm dễ gây lỗi khi xử lý claims. Một thuộc tính có thể ở nhiều trạng thái khác nhau:

~~~json
{}
~~~

~~~json
{"middle_name": null}
~~~

~~~json
{"middle_name": ""}
~~~

~~~json
{"middle_name": "An"}
~~~

Các trường hợp này mang ý nghĩa khác nhau:

| Trạng thái | Ví dụ | Cách hiểu |
| --- | --- | --- |
| **Thiếu thuộc tính** | Object không có middle_name | Không có claim đó trong object |
| **Có thuộc tính với null** | middle_name có giá trị null | Claim tồn tại và giá trị được đặt rõ là null |
| **Có chuỗi rỗng** | middle_name là "" | Claim là string có độ dài bằng 0 |
| **Có chuỗi không rỗng** | middle_name là "An" | Claim là string với nội dung cụ thể |

Một số hệ thống nghiệp vụ có thể định nghĩa thiếu thuộc tính là “không cung cấp”, null là “đã biết nhưng không có giá trị”, còn chuỗi rỗng là một giá trị string cụ thể. Hệ thống khác có thể không cho phép null hoặc chuỗi rỗng. **JSON và JWT không tự quyết định ngữ nghĩa nghiệp vụ của các trạng thái này**; hợp đồng claim phải định nghĩa.

### Không dùng phép kiểm tra truthy/falsy thay cho kiểm tra hiện diện

Một số ngôn ngữ có phép kiểm tra giá trị theo kiểu truthy/falsy. Cách kiểm tra này có thể gộp nhiều giá trị khác nhau:

- boolean false.
- number 0.
- chuỗi rỗng "".
- null.
- thuộc tính không tồn tại.

Những giá trị đó không tương đương. Ví dụ false có thể là câu trả lời hợp lệ; login_count bằng 0 có thể là số lần đăng nhập hợp lệ; scope rỗng có thể biểu thị không có scope theo hợp đồng ứng dụng. Không được xem chúng như thuộc tính bị thiếu nếu đặc tả không quy định như vậy.

Cách kiểm tra đúng gồm hai bước khái niệm:

1. Kiểm tra object có chứa tên claim hay không.
2. Nếu có, kiểm tra kiểu và giá trị có đáp ứng hợp đồng hay không.

## 4. null không phải là false, 0 hoặc chuỗi rỗng

Các giá trị sau có ý nghĩa và kiểu khác nhau:

~~~json
{
  "enabled": false,
  "retry_count": 0,
  "label": "",
  "comment": null
}
~~~

| Giá trị | Kiểu | Có thể biểu thị |
| --- | --- | --- |
| false | Boolean | Trạng thái tắt hoặc không |
| 0 | Number | Số lượng bằng không |
| "" | String | Chuỗi rỗng |
| null | Null | Giá trị null tường minh |

Không nên chuyển tất cả các giá trị trên thành một trạng thái “không có”. Nếu claim có vai trò bảo mật, sự nhập nhằng có thể làm thay đổi kết quả quyết định:

- enabled là false có thể phải từ chối một chức năng.
- enabled bị thiếu có thể là token không đạt hợp đồng.
- enabled là null có thể là dữ liệu không hợp lệ.
- enabled là string "false" không phải boolean false.

Một ứng dụng cần quy định rõ mỗi claim có cho phép null hay không, có cho phép giá trị rỗng hay không và giá trị mặc định nào được áp dụng. Đối với claim ảnh hưởng đến danh tính, thời hạn hoặc quyền, nên có quy tắc rõ ràng và từ chối dữ liệu không đúng kiểu thay vì tự suy đoán.

## 5. Kiểu dữ liệu của các registered claims

RFC 7519 định nghĩa một số tên claim chuẩn và kiểu dữ liệu tương ứng. Các claim này **không bắt buộc xuất hiện trong mọi JWT**; ứng dụng hoặc profile cụ thể sẽ quy định claim nào cần có.

| Claim | Kiểu dữ liệu theo JWT | Ý nghĩa và cách kiểm tra |
| --- | --- | --- |
| **iss** | String | Nhà phát hành; so sánh với issuer được cấu hình tin cậy |
| **sub** | String | Chủ thể; diễn giải theo quy ước của issuer |
| **aud** | String hoặc array các String | Đối tượng nhận; token phải dành cho dịch vụ đang xử lý |
| **exp** | Number (NumericDate) | Hết hạn; từ chối khi thời điểm hiện tại ở hoặc sau thời điểm hết hạn |
| **nbf** | Number (NumericDate) | Chưa có hiệu lực trước thời điểm này; từ chối nếu thời điểm hiện tại còn trước mốc |
| **iat** | Number (NumericDate) | Thời điểm phát hành; dùng để đánh giá tuổi token theo chính sách |
| **jti** | String | Định danh token; có thể hỗ trợ thu hồi hoặc chống phát lại khi có cơ chế trạng thái |

Một số điểm cần nhớ:

- iss, sub và jti là string; một number hoặc object không thể thay thế.
- aud chấp nhận một string hoặc một array các string. Nếu là array, dịch vụ nhận cần có mặt trong tập audience theo quy tắc áp dụng.
- exp, nbf và iat dùng NumericDate, tức số giây kể từ Unix epoch. Đặc tả cho phép giá trị số có phần thập phân; ứng dụng phải xử lý theo quy tắc thời gian của mình.
- exp là claim tùy chọn trong định nghĩa JWT cơ bản. Một profile bảo mật có thể yêu cầu mọi access token phải có exp; nếu thiếu thì từ chối theo profile đó.
- Nếu claim thời gian có mặt nhưng là null hoặc string, nó không còn đúng kiểu NumericDate và phải bị từ chối.

### Ví dụ đúng kiểu và sai kiểu

Đúng kiểu cho một JWT Claims Set:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "exp": 1893456300
}
~~~

Sai kiểu cho các claim tương ứng:

~~~json
{
  "iss": 123,
  "sub": null,
  "aud": 42,
  "iat": "1893456000",
  "exp": null
}
~~~

Đối tượng JSON thứ hai có thể hợp lệ về cú pháp JSON, nhưng không đáp ứng kiểu dữ liệu được yêu cầu cho các registered claims này. **JSON parse thành công không đồng nghĩa JWT claims hợp lệ.**

## 6. aud: string và array không được nhầm lẫn

Claim aud có thể là một string hoặc một array các string:

~~~json
{"aud":"orders-api"}
~~~

~~~json
{"aud":["orders-api","profile-api"]}
~~~

Hai dạng này đều có thể hợp lệ. Một bộ xác minh JWT cần xử lý cả hai theo đặc tả, sau đó kiểm tra audience của chính mình.

Các dạng sau không hợp lệ về kiểu:

~~~json
{"aud": 7}
~~~

~~~json
{"aud": ["orders-api", 7]}
~~~

~~~json
{"aud": null}
~~~

Không nên ép number thành string hoặc bỏ qua phần tử sai kiểu. Nếu một phần tử trong array không phải string, dữ liệu không đáp ứng kiểu của claim aud và cần bị từ chối theo chính sách nghiêm ngặt.

Cũng không nên giả định mọi JWT đều dùng cùng một audience. Một token có thể dành cho nhiều bên nhận; mỗi dịch vụ chỉ được chấp nhận token nếu định danh của mình xuất hiện trong audience theo quy tắc áp dụng.

## 7. Kiểu dữ liệu của claim do ứng dụng định nghĩa

Ngoài registered claims, ứng dụng có thể định nghĩa claim riêng. Ví dụ:

~~~json
{
  "tenant_id": "tenant-17",
  "roles": ["reader", "auditor"],
  "permissions": ["orders:read", "profile:view"],
  "mfa_verified": true,
  "risk_score": 0.12
}
~~~

JWT không tự áp đặt kiểu dữ liệu chung cho mọi claim riêng. Hợp đồng của ứng dụng cần quy định:

| Claim ứng dụng | Kiểu được chọn trong ví dụ | Quy tắc có thể cần |
| --- | --- | --- |
| tenant_id | String | Không rỗng; thuộc tenant hợp lệ |
| roles | Array các String | Mỗi role thuộc danh sách cho phép |
| permissions | Array các String | Mỗi quyền có tên và phạm vi xác định |
| mfa_verified | Boolean | Chỉ true khi thỏa điều kiện xác minh đa yếu tố |
| risk_score | Number | Nằm trong miền cho phép, ví dụ từ 0 đến 1 |

Đây là ví dụ hợp đồng do ứng dụng định nghĩa, không phải quy tắc mặc định của JWT. Một hệ thống khác có thể chọn kiểu khác, nhưng bên phát hành và bên nhận phải thống nhất.

### Không tự suy luận kiểu theo tên claim

Tên roles không tự động chứng minh giá trị phải là array; tên active cũng không tự động chứng minh kiểu boolean. Cần có schema hoặc tài liệu hợp đồng xác định kiểu và miền giá trị.

Đối với claim có tác động đến authorization, nên xác định:

- Kiểu dữ liệu chính xác.
- Có bắt buộc hay không.
- Có cho phép null hay không.
- Có cho phép mảng rỗng hoặc chuỗi rỗng hay không.
- Miền giá trị, độ dài và số phần tử tối đa.
- Ý nghĩa của giá trị theo issuer, audience và loại token.

## 8. Missing, null và optional claims trong chính sách bảo mật

JWT cơ bản cho phép nhiều registered claims là tùy chọn. Tuy nhiên, “tùy chọn theo đặc tả” không có nghĩa “ứng dụng nào cũng nên bỏ qua”.

Ví dụ một profile access token có thể yêu cầu:

| Claim | Yêu cầu của profile ví dụ | Khi thiếu | Khi null/sai kiểu |
| --- | --- | --- | --- |
| iss | Bắt buộc | Từ chối | Từ chối |
| sub | Bắt buộc | Từ chối | Từ chối |
| aud | Bắt buộc | Từ chối | Từ chối |
| exp | Bắt buộc theo profile | Từ chối | Từ chối |
| iat | Tùy chọn | Theo chính sách | Từ chối nếu có nhưng sai kiểu |
| jti | Tùy chọn | Theo chính sách | Từ chối nếu có nhưng sai kiểu |

Đây chỉ là ví dụ về profile do ứng dụng quy định, không phải yêu cầu bắt buộc cho mọi JWT. Khi định nghĩa profile, cần phân biệt rõ:

- **Optional:** claim có thể vắng mặt.
- **Required:** claim phải có.
- **Nullable:** claim có thể hiện diện với giá trị null.
- **Non-null:** nếu có mặt thì không được null.
- **Empty allowed:** có thể chấp nhận string hoặc array rỗng.
- **Non-empty:** yêu cầu giá trị có nội dung hoặc phần tử.

Một claim có thể là optional nhưng non-null khi hiện diện. Ví dụ iat có thể không bắt buộc trong một profile, nhưng nếu có thì phải là NumericDate hợp lệ. Không nên nhầm optional với nullable.

### Chính sách fallback cần được định nghĩa tường minh

Nếu claim bị thiếu, hệ thống có thể từ chối hoặc dùng giá trị mặc định theo profile. Với claim bảo mật như quyền, issuer, audience hoặc thời hạn, việc tự gán mặc định rộng có thể mở ra quyền không mong muốn.

Ví dụ, nếu roles bị thiếu, không nên tự động cấp role mặc định có quyền cao. Nếu mfa_verified bị thiếu, không được diễn giải thành true. Hành vi an toàn phải được định nghĩa trước và nhất quán ở mọi dịch vụ nhận token.

## 9. Number, NumericDate và giới hạn biểu diễn

JSON Number có thể biểu diễn số nguyên hoặc số thập phân. JWT dùng Number cho NumericDate:

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456300
}
~~~

NumericDate tính bằng số giây kể từ 1970-01-01T00:00:00Z. Không được nhầm giây với mili giây. Ví dụ, một timestamp tính theo mili giây có thể lớn hơn NumericDate dự kiến khoảng một nghìn lần.

Các dạng sau khác nhau về kiểu hoặc giá trị:

~~~json
{"exp": 1893456300}
~~~

~~~json
{"exp": "1893456300"}
~~~

~~~json
{"exp": 1893456300000}
~~~

- Dạng đầu là Number có giá trị giây theo ví dụ.
- Dạng thứ hai là String, sai kiểu NumericDate.
- Dạng thứ ba là Number nhưng có thể là mili giây bị dùng nhầm, làm thời điểm hết hạn sai lệch rất lớn.

Một số môi trường xử lý số dùng độ chính xác hữu hạn. Nếu claim ứng dụng chứa số nguyên rất lớn, cần đánh giá nguy cơ làm tròn và chọn biểu diễn phù hợp. Với NumericDate thông thường, giới hạn và độ chính xác phải được kiểm tra theo thư viện và chính sách thời gian.

## 10. Array và object lồng nhau

JSON cho phép array và object lồng nhau trong claims. Ví dụ:

~~~json
{
  "profile": {
    "region": "apac",
    "verified": true
  },
  "permissions": [
    "orders:read",
    "profile:view"
  ]
}
~~~

Việc parse thành công không có nghĩa mọi cấu trúc lồng nhau đều được ứng dụng chấp nhận. Cần quy định:

- Có cho phép object hoặc array lồng sâu hay không.
- Độ sâu tối đa và kích thước tối đa.
- Kiểu phần tử trong array.
- Tên thuộc tính hợp lệ trong object.
- Có cho phép null trong phần tử hay không.
- Có chấp nhận phần tử trùng lặp hay không.

Ví dụ, nếu permissions được định nghĩa là array các string, dữ liệu sau phải bị từ chối:

~~~json
{
  "permissions": ["orders:read", null, 12]
}
~~~

Không nên bỏ qua phần tử sai kiểu rồi tiếp tục phân quyền. Việc lọc âm thầm có thể làm các thành phần khác diễn giải cùng token khác nhau.

## 11. Tên claim trùng lặp và cách parser diễn giải

JSON object có thể bị tạo với hai thuộc tính cùng tên:

~~~json
{
  "role": "reader",
  "role": "admin"
}
~~~

Các parser có thể xử lý tên trùng lặp khác nhau: giữ giá trị đầu tiên, giữ giá trị cuối cùng hoặc từ chối. RFC 7519 yêu cầu tên claim trong JWT Claims Set phải duy nhất; parser phải từ chối tên trùng lặp hoặc dùng thành viên trùng tên xuất hiện sau cùng trong văn bản JSON. Đối với hệ thống bảo mật, từ chối tên trùng lặp là lựa chọn rõ ràng và dễ kiểm soát.

Tương tự, các tham số JOSE header cũng cần tuân thủ quy tắc tên duy nhất của đặc tả tương ứng. Không nên để một thành phần xác minh dùng giá trị role đầu tiên còn thành phần phân quyền dùng giá trị cuối cùng.

## 12. Quy trình kiểm tra kiểu và giá trị claim

~~~mermaid
flowchart TD
    A["Xác minh chữ ký hoặc giải mã JWE thành công"] --> B["Parse JWT Claims Set"]
    B --> C{"JSON object hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Kiểm tra tên claim và duplicate names"]
    D --> E{"Claim bắt buộc có mặt?"}
    E -- "Không" --> X
    E -- "Có" --> F["Kiểm tra kiểu dữ liệu"]
    F --> G{"Kiểu đúng và null policy hợp lệ?"}
    G -- "Không" --> X
    G -- "Có" --> H["Kiểm tra miền giá trị, thời gian và audience"]
    H --> I{"Giá trị đáp ứng profile?"}
    I -- "Không" --> X
    I -- "Có" --> J["Áp dụng authorization"]
~~~

Thứ tự xử lý quan trọng:

1. Hoàn tất xác minh JWS hoặc giải mã có xác thực JWE trước khi tin cậy payload.
2. Parse payload thành JSON object theo parser có hành vi xác định.
3. Từ chối cấu trúc không hợp lệ, tên claim trùng lặp hoặc dữ liệu vượt giới hạn.
4. Kiểm tra sự hiện diện của từng claim bắt buộc.
5. Kiểm tra kiểu dữ liệu chính xác, bao gồm quy tắc null và giá trị rỗng.
6. Kiểm tra miền giá trị, thời gian, issuer, audience và quy tắc riêng của profile.
7. Chỉ sau đó mới dùng claims làm đầu vào cho authorization.

Nếu một thư viện JWT tự động chuyển kiểu hoặc cung cấp claim qua API tiện dụng, cần xác định hành vi thực tế của thư viện. Không nên cho rằng API trả về string đã chứng minh token gốc chứa JSON string; có thể có chuyển đổi ở lớp thư viện.

## 13. Ví dụ: một claim quyền bị thiếu hoặc sai kiểu

Một API đơn hàng mong đợi payload theo hợp đồng:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "aud": "orders-api",
  "exp": 1893456300,
  "permissions": ["orders:read"]
}
~~~

Các trường hợp sau cần được xử lý khác nhau:

| Payload rút gọn | Tình trạng | Xử lý theo hợp đồng ví dụ |
| --- | --- | --- |
| Không có permissions | Claim bắt buộc bị thiếu | Từ chối |
| permissions là null | Sai kiểu/không nullable | Từ chối |
| permissions là string orders:read | String thay vì array | Từ chối |
| permissions là [] | Array đúng kiểu nhưng rỗng | Không có quyền; từ chối thao tác cần quyền |
| permissions là ["orders:read"] | Đúng kiểu và có quyền | Có thể tiếp tục sau các kiểm tra khác |
| permissions là ["orders:read", 7] | Có phần tử sai kiểu | Từ chối toàn bộ claims theo chính sách nghiêm ngặt |

Một API không nên tự đổi string thành array, bỏ phần tử sai kiểu hoặc coi null như mảng rỗng nếu hợp đồng không cho phép. Cách xử lý nhất quán giúp giảm lỗi phân quyền và khác biệt giữa các thành phần.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi thuộc tính thiếu và null là một | Mất ý nghĩa của trạng thái dữ liệu | Kiểm tra riêng sự hiện diện và giá trị |
| Dùng truthy/falsy để kiểm tra claim | Gộp false, 0, chuỗi rỗng và null | Kiểm tra kiểu và hiện diện tường minh |
| Ép string thành number | Chấp nhận dữ liệu sai schema | Từ chối sai kiểu |
| Coi "false" là boolean false | Logic kiểm tra có thể sai | Chỉ chấp nhận JSON boolean |
| Coi exp dạng string là NumericDate | Kiểm tra thời hạn không đúng | Yêu cầu JSON Number theo JWT |
| Nhầm giây và mili giây | Token có thể hết hạn sai thời điểm | Quy định NumericDate theo giây |
| Bỏ qua phần tử sai kiểu trong array | Các thành phần có thể diễn giải quyền khác nhau | Từ chối claims không đáp ứng schema |
| Tự gán quyền mặc định khi claim thiếu | Có thể cấp quyền vượt mong muốn | Định nghĩa fallback an toàn; mặc định từ chối khi cần |
| Không xử lý tên claim trùng lặp | Parser có thể chọn giá trị khác nhau | Từ chối tên trùng lặp |
| Cho rằng mọi claim chuẩn đều bắt buộc | Từ chối token hợp lệ theo profile khác | Phân biệt JWT base spec với profile ứng dụng |
| Cho rằng claim optional luôn được null | Nới lỏng schema ngoài dự kiến | Quy định optional và nullable riêng biệt |

## 15. Checklist xây dựng hợp đồng claims

Với mỗi claim, hãy xác định:

- Tên claim và ý nghĩa.
- Claim thuộc nhóm registered hay do ứng dụng định nghĩa.
- Kiểu JSON chính xác.
- Claim bắt buộc hay tùy chọn.
- Có cho phép null khi hiện diện hay không.
- Có cho phép chuỗi rỗng, mảng rỗng hoặc object rỗng hay không.
- Miền giá trị, độ dài và số phần tử tối đa.
- Cách xử lý khi thiếu hoặc sai kiểu.
- Claim được dùng cho xác thực, ngữ cảnh hay authorization.
- Profile, issuer và audience nào áp dụng hợp đồng đó.

**Ghi nhớ:** Thuộc tính bị thiếu, null, false, 0, chuỗi rỗng và mảng rỗng là các trạng thái khác nhau. Registered claims của JWT có kiểu dữ liệu được quy định; claim riêng cần có hợp đồng rõ ràng. Một payload có thể parse thành công nhưng vẫn không hợp lệ với profile bảo mật. Hãy xác minh cơ chế bảo vệ trước, sau đó kiểm tra sự hiện diện, kiểu, null policy và miền giá trị của từng claim trước khi sử dụng nó.

### Tài liệu chuẩn để tra cứu

- **RFC 7519 — JSON Web Token (JWT):** JWT Claims Set, registered claims, kiểu dữ liệu và tên claim duy nhất.
- **RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format:** kiểu dữ liệu JSON, object, array, number, string, boolean và null.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh JWT, kiểm tra claim và xử lý an toàn.
- **RFC 7515 — JSON Web Signature (JWS):** xác minh chữ ký trước khi tin cậy payload.
- **RFC 7516 — JSON Web Encryption (JWE):** giải mã có xác thực trước khi sử dụng plaintext.
