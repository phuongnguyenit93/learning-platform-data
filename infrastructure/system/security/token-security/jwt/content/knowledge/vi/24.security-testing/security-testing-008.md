# Claims trùng tên, sai kiểu và dữ liệu có độ sâu bất thường

## 1. Vì sao cần kiểm thử cấu trúc claims?

JSON Web Token (JWT) mang một tập claims được biểu diễn bằng JSON. Resource server thường dùng các claims như `iss`, `sub`, `aud`, `exp`, `scope` hoặc role để xác minh chủ thể và quyết định quyền truy cập.

Một token có thể có chữ ký hợp lệ nhưng vẫn chứa JSON mơ hồ, kiểu dữ liệu không đúng hợp đồng hoặc cấu trúc quá lớn và quá sâu. Nếu các thành phần trong hệ thống diễn giải token khác nhau, hoặc parser tiêu thụ quá nhiều CPU, bộ nhớ và stack, kẻ tấn công có thể tạo ra:

- Quyết định xác thực/authorization không nhất quán giữa gateway và API.
- Bỏ qua kiểm tra do ứng dụng tự chuyển đổi kiểu dữ liệu.
- Lỗi parser, exception không được xử lý hoặc crash tiến trình.
- Tấn công từ chối dịch vụ (DoS) bằng payload lớn hoặc cấu trúc lồng nhau bất thường.
- Rò rỉ thông tin qua log lỗi chứa nguyên token hoặc payload cá nhân.

Vì vậy, kiểm thử JWT cần xem xét cả tính hợp lệ mật mã lẫn tính hợp lệ cú pháp, schema, kiểu dữ liệu và giới hạn tài nguyên.

## 2. JSON object có tên thuộc tính trùng lặp

JSON object được biểu diễn bằng các cặp tên/giá trị. Theo RFC 8259, tên trong một object nên là duy nhất. Khi một object có tên trùng lặp, hành vi của parser có thể khác nhau: parser có thể giữ giá trị đầu, giữ giá trị cuối, báo lỗi hoặc xử lý theo cách riêng.

Ví dụ payload có hai claim `sub`:

~~~json
{
  "iss": "https://identity.example.test/",
  "sub": "user-42",
  "sub": "admin-1",
  "aud": "https://api.example.test/",
  "exp": 1893456000
}
~~~

Một thành phần có thể đọc `sub` đầu tiên là `user-42`, trong khi thành phần khác đọc giá trị cuối là `admin-1`. Nếu gateway và resource server sử dụng parser khác nhau, chúng có thể đưa ra quyết định khác nhau với cùng một chuỗi token.

### Quy tắc trong JOSE/JWT

- RFC 7519 quy định tên claims trong JWT Claims Set phải duy nhất. JWT parser phải từ chối tên claim trùng lặp hoặc sử dụng cách xử lý trả về member xuất hiện cuối theo quy tắc được nêu trong chuẩn.
- RFC 7515 quy định tên tham số trong JOSE Header phải duy nhất và áp dụng lựa chọn tương tự: từ chối hoặc dùng member xuất hiện cuối theo quy tắc tương ứng.
- RFC 8259 giải thích rằng khi tên bị lặp, hành vi của phần mềm nhận có thể không nhất quán.

Đối với hệ thống cần độ an toàn cao, chính sách dễ kiểm soát nhất là **từ chối mọi JSON object có tên thuộc tính trùng lặp**. Áp dụng chính sách này nhất quán cho protected header, claims set và các object lồng nhau mà ứng dụng xử lý.

### Trùng lặp ở JOSE header cũng nguy hiểm

Ví dụ header có hai giá trị `alg` hoặc `kid`:

~~~json
{
  "alg": "RS256",
  "alg": "none",
  "kid": "trusted-key-1"
}
~~~

Hoặc:

~~~json
{
  "alg": "RS256",
  "kid": "key-a",
  "kid": "key-b"
}
~~~

Nếu các thành phần hiểu header khác nhau, chúng có thể chọn thuật toán hoặc khóa khác nhau. Không được để sự khác biệt parser quyết định chính sách mật mã.

### Tên trùng lặp có thể bị che bởi escape

JSON cho phép biểu diễn một ký tự bằng escape sequence. Hai cách viết văn bản khác nhau có thể trở thành cùng một tên sau khi giải mã JSON:

~~~json
{
  "sub": "user-42",
  "\u0073ub": "admin-1"
}
~~~

Parser có khả năng phát hiện duplicate phải so sánh tên sau khi giải mã escape, không chỉ tìm chuỗi ký tự giống nhau trong văn bản JSON thô. Tên JSON phân biệt chữ hoa/chữ thường; `sub` và `Sub` là hai tên khác nhau, nhưng ứng dụng cũng cần tránh tự chuẩn hóa chúng thành cùng một claim.

## 3. Vì sao chữ ký hợp lệ không giải quyết được sự mơ hồ?

JWS xác minh tính toàn vẹn của signing input, tức các phần đã mã hóa của protected header và payload. Chữ ký chứng minh dữ liệu byte đã ký không bị thay đổi sau khi phát hành, nhưng không buộc mọi JSON parser phải diễn giải một object có tên trùng lặp theo cùng cách.

Nếu issuer phát hành payload có tên trùng lặp, hoặc token hợp lệ được đưa qua nhiều thành phần với parser khác nhau, chữ ký vẫn có thể hợp lệ trong khi cách diễn giải claims khác nhau.

Ví dụ:

1. Authorization gateway xác minh chữ ký và parser của nó giữ giá trị `sub` đầu tiên.
2. Gateway chuyển nguyên token tới resource server.
3. Resource server cũng xác minh token nhưng parser giữ giá trị `sub` cuối cùng.
4. Gateway ghi audit cho `user-42`, còn resource server thực thi request dưới `admin-1`.

Đây là lỗi nhất quán ngữ nghĩa giữa các thành phần. “Chữ ký hợp lệ” không đồng nghĩa mọi parser đều hiểu cùng một danh tính.

## 4. Chính sách xử lý duplicate member names

| Vị trí | Chính sách khuyến nghị |
| --- | --- |
| Protected JOSE header | Từ chối nếu có tên tham số trùng lặp |
| JWT Claims Set cấp cao nhất | Từ chối nếu có tên claim trùng lặp |
| Object lồng trong private/custom claim | Từ chối duplicate nếu ứng dụng đọc hoặc diễn giải object đó |
| JSON được chuyển tiếp giữa gateway và resource server | Giữ nguyên token đã xác minh; các bên phải dùng cùng quy tắc schema/duplicate |
| Dữ liệu JSON được tái phát hành thành token mới | Serialize từ object tin cậy sau khi xác thực schema; không âm thầm ghi đè member trùng |

Không nên parse JSON bằng parser đã tự loại bỏ member trùng rồi mới cố kiểm tra duplicate; thông tin trùng có thể đã mất. Cần dùng parser có chế độ duplicate detection hoặc một bước kiểm tra cú pháp có khả năng phát hiện member trùng trước khi dữ liệu được chuyển thành map/object thông thường.

Nếu một thư viện chỉ hỗ trợ quy tắc “last member wins” theo profile chuẩn mà không có chế độ reject, phải bảo đảm mọi thành phần liên quan dùng cùng cách diễn giải. Với dữ liệu đầu vào không tin cậy và hệ thống nhiều thành phần, từ chối duplicate thường dễ kiểm thử và giảm rủi ro hơn.

## 5. Claims sai kiểu dữ liệu

JSON có các kiểu dữ liệu cơ bản: string, number, boolean, null, array và object. Một claim có thể tồn tại nhưng vẫn không hợp lệ nếu giá trị không đúng kiểu mà chuẩn hoặc profile của ứng dụng yêu cầu.

Ví dụ:

~~~json
{
  "iss": 123,
  "sub": {
    "id": "user-42"
  },
  "aud": true,
  "exp": "1893456000",
  "scope": ["orders.read"]
}
~~~

Payload này có cú pháp JSON hợp lệ, nhưng nhiều claims không đúng kiểu mong đợi. Nếu ứng dụng tự ép kiểu, cách xử lý có thể không nhất quán và tạo ra lỗ hổng.

### Kiểu dữ liệu của registered claims

| Claim | Kiểu theo JWT | Lưu ý xác minh |
| --- | --- | --- |
| `iss` | String | So sánh với issuer tin cậy theo đúng quy tắc của profile |
| `sub` | String | Không tự chuyển object, number hoặc boolean thành chuỗi |
| `aud` | String hoặc array các string | Kiểm tra đúng audience của resource server |
| `exp` | NumericDate (JSON number) | Không nhận chuỗi số hoặc boolean; kiểm tra giới hạn và thời điểm |
| `nbf` | NumericDate (JSON number) | Không nhận chuỗi số; áp dụng clock skew có giới hạn |
| `iat` | NumericDate (JSON number) | Có thể kiểm tra thời điểm phát hành trong tương lai hoặc tuổi tối đa |
| `jti` | String | Dùng đúng định dạng và phạm vi định danh token của profile |

NumericDate là số giây kể từ Unix epoch theo định nghĩa của JWT. Chuẩn cho phép giá trị số không nhất thiết phải là số nguyên; nếu profile yêu cầu số nguyên thì phải ghi rõ yêu cầu đó. Dù chấp nhận số thập phân, verifier vẫn cần giới hạn miền giá trị và tránh tràn số khi chuyển sang kiểu thời gian của nền tảng.

### Kiểu dữ liệu theo profile và claim tùy chỉnh

Một số claims không có một kiểu dùng chung cho mọi ứng dụng:

- Trong OpenID Connect, `email_verified` là boolean; chuỗi `"true"` không tương đương boolean `true`.
- `auth_time` là NumericDate.
- `amr` là danh sách phương thức xác thực theo định nghĩa của profile.
- Trong JWT access token profile, `scope` là chuỗi scope được phân tách theo quy ước của profile.
- Claim `roles` hoặc `permissions` là claim riêng của ứng dụng; phải quy định rõ là string, array string hay schema khác.

Không nên chấp nhận linh hoạt cả string lẫn array chỉ vì “dễ dùng”. Nếu một claim được định nghĩa là array string, giá trị string đơn phải bị từ chối; nếu schema quy định string thì object hoặc array phải bị từ chối.

## 6. Nguy cơ từ việc tự động ép kiểu

Ép kiểu ngầm có thể làm thay đổi ý nghĩa của claims:

| Giá trị đầu vào | Cách xử lý không an toàn | Vấn đề |
| --- | --- | --- |
| `"exp": "1893456000"` | Chuyển chuỗi thành số | Một thành phần chấp nhận, thành phần khác từ chối |
| `"email_verified": "false"` | Chuyển sang boolean theo truthiness | Chuỗi không rỗng có thể bị hiểu thành true |
| `"sub": 42` | Chuyển thành `"42"` | Danh tính sai schema vẫn được chấp nhận |
| `"roles": "admin"` | Tự bọc thành array | Bỏ qua hợp đồng schema |
| `"roles": ["user", 7]` | Chuyển mọi phần tử thành chuỗi | Giá trị không hợp lệ đi vào quyết định quyền |
| `"aud": null` | Coi null như thiếu claim | Mất phân biệt giữa thiếu, null và sai kiểu |
| `"exp": true` | Chuyển boolean thành 1 hoặc 0 | Có thể tạo thời gian sai ngoài dự kiến |

Các quy tắc:

1. Kiểm tra kiểu JSON chính xác trước khi chuyển sang kiểu dữ liệu nội bộ.
2. Không dùng truthiness hoặc coercion mặc định để diễn giải boolean, number và string.
3. Phân biệt claim không tồn tại, claim có giá trị null và claim có kiểu sai.
4. Kiểm tra từng phần tử trong array; không chỉ kiểm tra kiểu của container.
5. Từ chối giá trị ngoài schema thay vì âm thầm bỏ qua hoặc chuyển đổi.

## 7. Kiểm tra miền giá trị, không chỉ kiểu dữ liệu

Một claim có đúng kiểu vẫn có thể mang giá trị nguy hiểm hoặc vô nghĩa.

Ví dụ với `exp`:

- Giá trị âm hoặc quá xa trong tương lai có thể không phù hợp với profile.
- Số quá lớn có thể gây overflow khi chuyển đổi timestamp.
- Số rất nhỏ hoặc số thập phân có thể bị làm tròn khác nhau giữa các thành phần.
- Giá trị hợp lệ về kiểu nhưng đã ở quá khứ phải bị từ chối theo quy tắc hết hạn.

Ví dụ với `aud`:

- String rỗng không nên tự động được coi là audience hợp lệ.
- Array chứa number, null hoặc object phải bị từ chối.
- Array quá lớn có thể tiêu tốn tài nguyên khi so khớp.
- Giá trị audience phải được so sánh theo quy tắc của profile; không tự chuẩn hóa tùy tiện.

Ví dụ với `sub` hoặc claim định danh:

- Giới hạn độ dài.
- Từ chối chuỗi rỗng nếu profile yêu cầu định danh.
- Quy định ký tự và encoding nếu hệ thống có schema cụ thể.
- Không dùng giá trị claim trực tiếp làm tên file, câu lệnh, truy vấn hoặc log format mà không có xử lý phù hợp.

## 8. Object và array lồng nhau quá sâu

JWT Claims Set cấp cao nhất là JSON object, nhưng private claims có thể chứa object hoặc array lồng nhau nếu profile cho phép. Một payload có thể tạo cấu trúc rất sâu:

~~~json
{
  "sub": "user-42",
  "custom": {
    "a": {
      "b": {
        "c": {
          "d": {
            "e": {
              "f": {
                "value": "data"
              }
            }
          }
        }
      }
    }
  }
}
~~~

Ví dụ này chỉ có vài cấp, nhưng cùng một mẫu có thể được lặp hàng nghìn cấp. Một parser hoặc đoạn code đệ quy có thể:

- Tràn stack do đệ quy quá sâu.
- Tốn CPU khi duyệt hoặc validate cấu trúc.
- Tốn bộ nhớ cho object, array và node trung gian.
- Tạo exception hoặc timeout trong request path.
- Kích hoạt lỗi ở thư viện serialize, log hoặc schema validator.

Một JWT được ký không tự động miễn nhiễm với DoS. Nếu hệ thống chấp nhận token từ nhiều issuer, có tích hợp liên kết hoặc có lỗi ở bước xác minh, cấu trúc dữ liệu bất thường vẫn cần được xử lý an toàn.

## 9. Giới hạn tài nguyên cho parser và claims

Giới hạn cần được áp dụng trước và trong quá trình parse:

| Giới hạn | Mục tiêu |
| --- | --- |
| Tổng chiều dài compact JWT | Ngăn token quá lớn trước khi decode/cấp phát bộ nhớ |
| Độ dài từng segment | Giới hạn header, payload và signature |
| Kích thước byte sau Base64URL decode | Kiểm soát bộ nhớ thực tế parser phải dùng |
| Độ sâu lồng nhau tối đa | Ngăn stack exhaustion và recursion DoS |
| Số member tối đa trong object | Ngăn object có quá nhiều thuộc tính |
| Số phần tử tối đa trong array | Ngăn danh sách lớn tiêu tốn CPU/bộ nhớ |
| Độ dài string tối đa | Ngăn claim string cực lớn |
| Độ dài biểu diễn number | Ngăn số có hàng triệu chữ số hoặc exponent bất thường |
| Số claims được phép | Giữ schema token nhỏ và dễ kiểm soát |
| Thời gian parse/validation | Bảo vệ request path khỏi input tốn tài nguyên |

Các con số cụ thể phụ thuộc hệ thống, kích thước token hợp lệ và giới hạn giao thức. Cần đo token hợp lệ trong môi trường thực tế rồi đặt ngưỡng có khoảng dự phòng; không sao chép một con số cố định mà không hiểu profile.

### Giới hạn phải áp dụng trước khi cấp phát lớn

Không nên decode một segment rất lớn vào bộ nhớ rồi mới kiểm tra kích thước. Trước tiên, kiểm tra tổng chiều dài chuỗi và độ dài từng segment; sau đó decode có giới hạn và kiểm tra số byte kết quả.

Nếu hỗ trợ nén trong JWE, cần giới hạn kích thước sau giải nén và tỷ lệ mở rộng. Một ciphertext nhỏ có thể tạo ra plaintext rất lớn nếu không có giới hạn giải nén.

## 10. Thứ tự xử lý an toàn

Với signed JWT, có thể xác minh chữ ký trên signing input mà không cần parse payload JSON thành object. Điều này cho phép trì hoãn việc xử lý claims cho đến khi token đã vượt qua xác minh mật mã.

Một pipeline tổng quát:

1. Kiểm tra kích thước compact token và số segment.
2. Kiểm tra Base64URL encoding và giới hạn độ dài từng segment.
3. Parse protected header bằng parser nghiêm ngặt có duplicate detection và giới hạn tài nguyên.
4. Kiểm tra `alg` theo allowlist cấu hình; kiểm tra `kid` chỉ để chọn khóa ứng viên từ nguồn tin cậy.
5. Xác minh chữ ký trên đúng signing input của token nhận được.
6. Chỉ sau khi xác minh thành công mới parse payload thành Claims Set bằng parser JSON nghiêm ngặt, có giới hạn độ sâu và kích thước.
7. Từ chối duplicate member names và top-level payload không phải JSON object.
8. Kiểm tra kiểu, miền giá trị và schema của registered claims/profile/custom claims.
9. Kiểm tra issuer, audience, thời gian, loại token và các ràng buộc nghiệp vụ.
10. Thực hiện authorization; không dùng dữ liệu chưa xác minh để tạo principal hoặc cấp quyền.

Với JWE, chỉ xử lý claims sau khi giải mã và xác thực bảo vệ JWE thành công. Nếu dùng nested JWT, mỗi lớp cần được xử lý theo đúng profile và giới hạn tài nguyên tương ứng.

Verifier có thể cần đọc protected header trước khi xác minh để chọn thuật toán và khóa. Vì vậy header phải được parse nghiêm ngặt, duplicate được phát hiện và thuật toán vẫn phải bị ràng buộc bởi cấu hình tin cậy. Không dùng header chưa xác minh làm nguồn chính sách.

## 11. Schema validation cho JWT Claims Set

Nên định nghĩa schema theo loại token thay vì áp dụng một schema quá rộng cho mọi JWT.

Ví dụ schema khái niệm cho một access token:

~~~text
ClaimsSet:
  required:
    iss: string
    sub: string
    aud: string | array<string>
    exp: NumericDate
  optional:
    iat: NumericDate
    nbf: NumericDate
    jti: string
    scope: string

Rules:
  - reject duplicate member names
  - reject unknown type for known claims
  - reject invalid NumericDate range
  - reject empty subject
  - require expected issuer
  - require this resource server in audience
  - enforce maximum token age when policy requires
  - validate scope against this API's permission model
~~~

Đây là schema minh họa, không phải yêu cầu bắt buộc cho mọi JWT. Một profile khác có thể quy định claim bắt buộc khác. Hợp đồng phải xuất phát từ RFC/profile và cấu hình issuer mà resource server tin cậy.

### Không nhầm schema với authorization

Schema validation trả lời “dữ liệu có đúng cấu trúc và kiểu không?”. Authorization trả lời “chủ thể này có được phép thực hiện hành động này trên tài nguyên này không?”.

Một token có schema hợp lệ vẫn có thể không đủ quyền. Ngược lại, một token có claim `role: "admin"` nhưng sai schema hoặc chưa được xác minh không được phép tạo quyền admin.

## 12. Parser differential giữa các thành phần

Trong kiến trúc phân tán, cùng một JWT có thể được đọc bởi API gateway, identity-aware proxy, backend resource server, service mesh sidecar, audit/analytics pipeline và hệ thống kiểm tra policy.

Nếu các thành phần dùng parser hoặc schema khác nhau, chúng có thể bất đồng về duplicate keys, kiểu số, Unicode, null, array hoặc giá trị thời gian.

| Thành phần | Cách xử lý | Rủi ro |
| --- | --- | --- |
| Gateway | Từ chối duplicate `sub` | Request bị từ chối ở gateway |
| Backend | Parser giữ member cuối | Backend hiểu một danh tính khác nếu token đến được đó |
| Audit service | Ép `sub` thành string | Log không phản ánh đúng quyết định authorization |
| Analytics | Bỏ qua claim sai kiểu | Sự kiện quan sát không khớp hành vi API |

Để tránh parser differential:

- Chuẩn hóa một profile token và schema được chia sẻ giữa các thành phần.
- Dùng thư viện parser có hành vi duplicate rõ ràng.
- Từ chối kiểu dữ liệu sai thay vì coercion.
- Giữ nguyên token compact đã xác minh khi chuyển tiếp; không parse rồi serialize lại để giả lập cùng token.
- Nếu một dịch vụ phát hành token mới, dịch vụ đó phải serialize từ object đã qua schema validation.
- Kiểm thử tích hợp qua toàn bộ đường đi gateway đến resource server.

## 13. Bộ test cho duplicate claims

Các trường hợp nên có trong test suite:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Claims Set có hai member `sub` | Từ chối |
| Claims Set có hai member `exp` | Từ chối |
| JOSE header có hai member `alg` | Từ chối |
| JOSE header có hai member `kid` | Từ chối |
| Tên trùng được viết một lần dạng literal và một lần dạng Unicode escape | Từ chối sau khi giải mã tên JSON |
| Duplicate nằm trong object custom claim được ứng dụng đọc | Từ chối |
| Duplicate nằm trong object không được dùng | Áp dụng chính sách JSON thống nhất; khuyến nghị từ chối ở mọi object |
| Cùng token được gửi qua gateway và backend | Mọi thành phần đưa ra cùng quyết định hoặc từ chối |
| Member trùng nhưng giá trị giống nhau | Vẫn từ chối theo chính sách strict duplicate |
| Member trùng ở vị trí đầu/cuối đảo ngược | Không có parser nào chọn một giá trị để tiếp tục |

Ví dụ duplicate escape:

~~~json
{
  "sub": "user-42",
  "\u0073ub": "admin-1"
}
~~~

Không chỉ kiểm thử duplicate ở payload; protected header cũng cần được kiểm tra vì nó ảnh hưởng đến việc chọn thuật toán và khóa.

## 14. Bộ test cho sai kiểu và giá trị ngoài miền

| Claim | Input bất thường | Kỳ vọng |
| --- | --- | --- |
| `iss` | Number, boolean, array, object, null | Từ chối |
| `sub` | Number, object, array, null hoặc chuỗi rỗng nếu profile cấm | Từ chối |
| `aud` | Boolean, object, array có phần tử không phải string | Từ chối |
| `exp` | String số, boolean, object, array, null | Từ chối |
| `exp` | Number vượt miền timestamp được hỗ trợ | Từ chối |
| `nbf` | String hoặc giá trị số ngoài miền | Từ chối |
| `iat` | Boolean, string hoặc timestamp tương lai vượt policy | Từ chối |
| `jti` | Number hoặc object | Từ chối |
| `email_verified` | Chuỗi `"true"` hoặc `"false"` | Từ chối theo OIDC schema |
| `scope` | Array/object khi profile yêu cầu string | Từ chối |
| `roles` | Array trộn string, number, object | Từ chối |
| Custom claim | Sai kiểu so với schema đã công bố | Từ chối |
| Bất kỳ claim | Giá trị null khi profile không cho phép | Từ chối |

Ngoài kiểu dữ liệu, cần test string rỗng, array rỗng, phần tử trùng, độ dài cực đại, số thập phân, số âm và giá trị biên thời gian theo profile cụ thể.

## 15. Bộ test cho cấu trúc sâu và payload quá lớn

Các test resource exhaustion nên chạy trong môi trường kiểm thử có giới hạn:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Token vượt max compact length | Từ chối trước khi decode toàn bộ |
| Header segment quá lớn | Từ chối trước khi parse header |
| Payload segment quá lớn | Từ chối trước khi parse payload |
| JSON lồng sâu hơn giới hạn | Từ chối có kiểm soát, không stack overflow |
| Array có quá nhiều phần tử | Từ chối theo giới hạn |
| Object có quá nhiều member | Từ chối theo giới hạn |
| Claim string vượt giới hạn | Từ chối |
| Numeric literal cực dài hoặc exponent cực lớn | Từ chối |
| Nhiều claim nhỏ nhưng tổng số lượng vượt giới hạn | Từ chối |
| JWE giải nén tạo plaintext vượt giới hạn | Dừng giải nén và từ chối |
| Parser gặp JSON không hợp lệ hoặc UTF-8 không hợp lệ | Từ chối, không fallback |
| Request lặp với payload gần ngưỡng | Latency và memory nằm trong ngân sách đã định |

Nên đo CPU, memory, thời gian parse và số lỗi trên từng ngưỡng. Không chỉ xác nhận request bị từ chối; cần xác nhận từ chối không khiến tiến trình hoặc worker bị cạn tài nguyên.

## 16. Fuzzing và kiểm thử property-based

Fuzzing giúp tìm những tổ hợp JSON và token mà bộ test viết tay thường bỏ sót.

Các nhóm dữ liệu có thể đưa vào fuzz:

- JSON object có tên trùng ở nhiều vị trí.
- Tên claim có escape sequence hoặc Unicode.
- String, number, boolean, null, array và object thay thế lẫn nhau.
- Số có exponent lớn, số âm, số thập phân và ranh giới timestamp.
- Array/object lồng sâu, nhiều member hoặc nhiều phần tử.
- Segment Base64URL bị cắt, sai alphabet hoặc có padding không đúng profile.
- Protected header có tham số lạ, duplicate hoặc `crit` không được hỗ trợ.
- Token có đúng cấu trúc compact nhưng payload không phải Claims Set object.

Một số property nên giữ:

1. Parser không bao giờ crash hoặc vượt giới hạn tài nguyên với input bị giới hạn kích thước.
2. Duplicate member bị từ chối theo chính sách.
3. Kiểu claim sai không được coercion thành kiểu hợp lệ.
4. Token không qua xác minh mật mã không tạo principal hoặc quyết định quyền.
5. Cùng một token và cùng profile phải có cùng kết quả ở gateway và resource server.
6. Mọi lỗi parse/validation đều dẫn đến từ chối, không fallback sang chế độ permissive.

Fuzzing cần chạy trong môi trường cô lập, có timeout, memory limit và lưu seed tái hiện lỗi. Không dùng payload DoS để thử trên production.

## 17. Xử lý lỗi và ghi log an toàn

Khi token có duplicate claim, sai kiểu hoặc vượt giới hạn:

- Từ chối request theo cách nhất quán.
- Không tạo principal một phần từ những claims parse được trước lỗi.
- Không bỏ qua claim sai kiểu nếu claim đó ảnh hưởng xác thực hoặc authorization.
- Không log raw JWT, toàn bộ payload hoặc dữ liệu cá nhân trong exception.
- Ghi mã lỗi nội bộ, loại lỗi, thành phần xử lý và request correlation ID.
- Giới hạn tần suất log để lỗi lặp lại không trở thành DoS qua logging.
- Tách thông báo cho client khỏi chi tiết parser nội bộ.

Ví dụ mã lỗi nội bộ:

~~~text
JWT_DUPLICATE_MEMBER
JWT_INVALID_CLAIM_TYPE
JWT_CLAIM_OUT_OF_RANGE
JWT_JSON_NESTING_LIMIT
JWT_TOKEN_SIZE_LIMIT
JWT_INVALID_JSON
~~~

Client có thể nhận lỗi xác thực chung như invalid token. Không trả lại tên claim nhạy cảm, nội dung payload hoặc vị trí chứa dữ liệu cá nhân nếu không cần thiết.

## 18. Checklist triển khai

- [ ] Đặt giới hạn tổng kích thước compact JWT và từng segment.
- [ ] Parse protected header bằng parser có giới hạn và duplicate detection.
- [ ] Từ chối duplicate member names trong header và claims set.
- [ ] Phát hiện tên trùng sau khi giải mã JSON escape sequence.
- [ ] Chỉ chấp nhận thuật toán trong allowlist cấu hình.
- [ ] Xác minh chữ ký/MAC trước khi tin claims; với JWE, xác thực giải mã trước khi tin plaintext.
- [ ] Dùng parser JSON nghiêm ngặt cho payload, yêu cầu top-level object.
- [ ] Kiểm tra kiểu chính xác cho registered claims và từng profile.
- [ ] Không tự động coercion string/number/boolean/null.
- [ ] Kiểm tra miền giá trị và giới hạn timestamp.
- [ ] Giới hạn độ sâu, số member, số phần tử, độ dài string và số.
- [ ] Có schema rõ cho custom claims.
- [ ] Kiểm thử parser differential qua gateway, backend và policy service.
- [ ] Có negative tests, fuzzing và regression tests.
- [ ] Không fallback sang decode-only khi parse hoặc verify thất bại.
- [ ] Không ghi raw token hoặc payload nhạy cảm vào log.

## 19. Sơ đồ pipeline xác minh và kiểm tra cấu trúc

~~~mermaid
flowchart TD
    A[Nhận compact JWT] --> B[Giới hạn tổng kích thước và segment]
    B --> C[Parse protected header nghiêm ngặt]
    C --> D{Duplicate hoặc header sai schema?}
    D -- Có --> X[Từ chối]
    D -- Không --> E[Kiểm tra algorithm allowlist và chọn khóa tin cậy]
    E --> F[Xác minh chữ ký hoặc xác thực JWE]
    F --> G{Bảo vệ mật mã hợp lệ?}
    G -- Không --> X
    G -- Có --> H[Parse Claims Set có giới hạn]
    H --> I{JSON hợp lệ, không duplicate, độ sâu trong giới hạn?}
    I -- Không --> X
    I -- Có --> J[Kiểm tra schema, kiểu và miền giá trị]
    J --> K{Claims hợp lệ?}
    K -- Không --> X
    K -- Có --> L[Kiểm tra iss, aud, thời gian và profile]
    L --> M{Token hợp lệ theo profile?}
    M -- Không --> X
    M -- Có --> N[Authorization theo tài nguyên]
    N --> O[Tiếp tục xử lý]
~~~

Sơ đồ mô tả pipeline khái quát cho token có bảo vệ mật mã. Protected header phải được đọc sớm để chọn thuật toán/khóa nhưng chưa được tin; claims payload chỉ được dùng sau khi chữ ký được xác minh hoặc JWE được giải mã và xác thực thành công.

## 20. Nguyên tắc cần ghi nhớ

1. JSON có tên member trùng lặp có thể được parser diễn giải khác nhau; kiểm thử duplicate là một phần của kiểm thử JWT.
2. RFC 7519 và RFC 7515 yêu cầu parser xử lý duplicate theo quy tắc cụ thể; hệ thống có thể chọn chính sách strict hơn là từ chối.
3. Phải phát hiện duplicate sau khi giải mã escape sequence, không chỉ so sánh văn bản thô.
4. Chữ ký hợp lệ không giải quyết parser differential hoặc schema mơ hồ.
5. Kiểm tra kiểu JSON chính xác cho registered claims, profile claims và custom claims.
6. Không tự động ép kiểu string, number, boolean, null, array và object.
7. Kiểm tra miền giá trị, độ dài và timestamp ngoài việc kiểm tra kiểu.
8. Giới hạn kích thước token, segment, độ sâu lồng nhau, số member, số phần tử và thời gian parse.
9. Với signed JWT, có thể xác minh signing input trước khi parse payload thành object; protected header vẫn cần parse nghiêm ngặt để chọn thuật toán/khóa.
10. Mọi thành phần xác minh token phải thống nhất schema và cách xử lý; kiểm thử end-to-end qua gateway và resource server.
11. Fuzzing và property-based testing giúp tìm parser edge cases nhưng cần chạy trong môi trường có giới hạn tài nguyên.
12. Parse/validation failure phải từ chối rõ ràng, không tạo principal một phần và không fallback sang chế độ ít an toàn.
13. Không ghi raw JWT hoặc payload nhạy cảm vào log khi điều tra lỗi.

### Tài liệu chuẩn tham khảo

- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format, mục 4](https://www.rfc-editor.org/rfc/rfc8259#section-4): tên member trong JSON object và hành vi khi tên trùng lặp.
- [RFC 7519 — JSON Web Token, mục 4 và 7.2](https://www.rfc-editor.org/rfc/rfc7519): claims, kiểu dữ liệu và xử lý JWT.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JOSE Header và xác minh JWS.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): schema và yêu cầu claims cho JWT access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): kiểu dữ liệu standard claims như `email_verified` và `auth_time`.
- [OWASP Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): giới hạn tài nguyên và giảm nguy cơ DoS.

**Kết luận:** JWT cần được kiểm tra như một cấu trúc dữ liệu không tin cậy, kể cả khi token có chữ ký hợp lệ. Từ chối member trùng lặp, xác thực kiểu và miền giá trị của claims, giới hạn độ sâu/kích thước parser và giữ cách diễn giải nhất quán giữa mọi thành phần sẽ giảm nguy cơ bypass authorization và từ chối dịch vụ.
