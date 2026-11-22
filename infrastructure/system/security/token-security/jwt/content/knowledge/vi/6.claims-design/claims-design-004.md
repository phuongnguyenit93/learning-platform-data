# Thiết kế lược đồ claims và kiểm tra kiểu dữ liệu

## 1. Vì sao cần lược đồ claims?

Một **JSON Web Token (JWT)** mang một tập claims (*JWT Claims Set*) được biểu diễn dưới dạng đối tượng JSON. Mỗi claim là một cặp tên–giá trị. Ví dụ, `sub` có thể xác định chủ thể, `aud` xác định bên nhận dự kiến, còn `tenant_id` có thể biểu thị tenant theo hợp đồng của một hệ thống.

Nếu issuer phát hành `exp` dưới dạng số nhưng consumer lại đọc như chuỗi, hoặc một bên gửi `roles` dưới dạng mảng trong khi bên kia mong đợi một chuỗi, hai thành phần sẽ không hiểu token theo cùng một cách. Sai kiểu có thể làm yêu cầu hợp lệ bị từ chối; nguy hiểm hơn, việc ép kiểu hoặc diễn giải mặc định không thống nhất có thể tạo ra lỗ hổng kiểm soát truy cập.

**Lược đồ claims (claims schema)** mô tả cấu trúc và các ràng buộc của Claims Set mà một hồ sơ token chấp nhận. Nó thường quy định:

- Những claim nào được phép xuất hiện và claim nào bắt buộc.
- Kiểu JSON của từng claim: string, number, boolean, array hoặc object.
- Cấu trúc phần tử bên trong array/object.
- Giới hạn độ dài, số lượng phần tử, miền giá trị và các quy tắc định dạng.
- Những quan hệ cần kiểm tra giữa nhiều claim.
- Cách xử lý claim thiếu, sai kiểu, không hợp lệ hoặc chưa được biết.

Lược đồ là một phần của **hợp đồng giữa issuer và consumer**. Nó giúp hai bên tạo, kiểm tra và thay đổi token nhất quán. Lược đồ không thay thế xác minh chữ ký, kiểm tra issuer/audience hay quyết định phân quyền.

## 2. Claims Set là một đối tượng JSON

### 2.1. Phân biệt header, payload và claims

Một JWT theo dạng compact JWS thường có ba phần: JOSE header, payload và chữ ký. Payload chứa Claims Set. Header mô tả thông tin bảo vệ/biểu diễn của token, ví dụ thuật toán ký hoặc loại nội dung.

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
       |                  |                    |
       |                  |                    +-- Bảo vệ tính toàn vẹn
       |                  +-- JWT Claims Set (đối tượng JSON)
       +-- JOSE Header (metadata của cơ chế bảo vệ)
```

Ví dụ, `alg` là tham số trong JOSE header; `iss`, `sub`, `exp` là claims trong payload. Không đưa quy tắc kiểm tra header vào lược đồ Claims Set, và không coi một trường trong header là claim nghiệp vụ.

JWT cũng có thể được mã hóa theo JWE hoặc được lồng theo các cấu trúc JOSE. Khi đó, quy trình giải mã/xác minh phụ thuộc loại token và hồ sơ được chấp nhận. Dù cách bảo vệ nào được dùng, consumer chỉ được tin Claims Set sau khi hoàn thành các bước xác minh mật mã và ràng buộc token cần thiết.

### 2.2. Các kiểu dữ liệu JSON cơ bản

JSON định nghĩa sáu loại giá trị:

| Kiểu JSON | Ví dụ | Cách dùng trong claims |
| --- | --- | --- |
| String | `"user_42"` | Định danh, tên, mã, scope theo hợp đồng |
| Number | `1893456900` | NumericDate như `exp`, `iat`, `nbf`; các giá trị số khác nếu hợp đồng định nghĩa |
| Boolean | `true` | Cờ đúng/sai, ví dụ claim tùy biến về trạng thái xác minh |
| Object | `{"id":"store_17"}` | Nhóm thông tin có cấu trúc khi hợp đồng thực sự cần |
| Array | `["read","write"]` | Danh sách audience, vai trò hoặc giá trị nhiều phần tử |
| Null | `null` | Giá trị rỗng tường minh; chỉ hợp lệ nếu hợp đồng cho phép |

Kiểu dữ liệu là một phần của hợp đồng. Các giá trị dưới đây **không tương đương**:

```json
{
  "exp": 1893456900,
  "enabled": true,
  "roles": ["order_reader", "order_creator"],
  "tenant_id": "tenant_17"
}
```

và:

```json
{
  "exp": "1893456900",
  "enabled": "true",
  "roles": "order_reader,order_creator",
  "tenant_id": 17
}
```

Ở ví dụ thứ hai, `exp` là chuỗi, `enabled` là chuỗi, `roles` là chuỗi và `tenant_id` là số. Nếu hợp đồng yêu cầu số, boolean, mảng chuỗi và mã tenant dạng chuỗi, token phải bị từ chối. Không tự động ép kiểu chỉ để làm dữ liệu “có vẻ hợp lệ”.

## 3. Kiểu và ngữ nghĩa của các registered claims

RFC 7519 định nghĩa kiểu dữ liệu và ý nghĩa cho các registered claims phổ biến. Khi thiết kế schema, cần phản ánh đúng các định nghĩa đó.

| Claim | Kiểu theo RFC 7519 | Quy tắc chính |
| --- | --- | --- |
| `iss` | StringOrURI | Chuỗi định danh issuer; consumer so khớp với issuer được tin cậy |
| `sub` | StringOrURI | Chuỗi định danh chủ thể trong phạm vi issuer/hợp đồng |
| `aud` | StringOrURI hoặc mảng StringOrURI | Token có thể dành cho một hoặc nhiều bên nhận |
| `exp` | NumericDate | Thời điểm hết hạn |
| `nbf` | NumericDate | Thời điểm bắt đầu được chấp nhận |
| `iat` | NumericDate | Thời điểm phát hành |
| `jti` | String | Định danh JWT |

**StringOrURI** là giá trị JSON kiểu string theo định nghĩa của RFC 7519. Nếu chuỗi chứa dấu hai chấm (`:`), nó phải là URI hợp lệ theo định nghĩa RFC. Không được biến `iss`, `sub` hay `aud` thành number hoặc object.

**NumericDate** biểu diễn số giây từ Unix epoch theo quy ước của RFC 7519. Giá trị có thể là số nguyên hoặc số có phần thập phân; không phải chuỗi ngày giờ và không phải số mili giây. Schema nên dùng kiểu number. Nếu hồ sơ ứng dụng chỉ cho phép mốc thời gian không âm hoặc giới hạn một miền thời gian cụ thể, ghi rõ đó là ràng buộc của hồ sơ ứng dụng.

Một điểm quan trọng: RFC 7519 không yêu cầu mọi JWT đều phải có đủ `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`. **Danh sách required do hồ sơ token của hệ thống quy định.** API thường cần quy định chặt hơn chuẩn nền để bảo đảm mục đích sử dụng cụ thể.

## 4. Thiết kế schema theo nhu cầu của consumer

### 4.1. Bắt đầu từ quyết định mà API cần đưa ra

Không nên sao chép toàn bộ cấu trúc cơ sở dữ liệu vào JWT. Hãy xác định:

1. Consumer nào nhận token và token được phát hành cho mục đích gì?
2. Consumer cần thông tin nào để xác định chủ thể, ngữ cảnh và phạm vi thao tác?
3. Claim nào cần thiết trong mọi yêu cầu, claim nào chỉ cần cho một số loại yêu cầu?
4. Dữ liệu nào ổn định đủ lâu để mang trong token, dữ liệu nào phải lấy từ nguồn hiện hành?
5. Nếu thiếu claim hoặc claim sai kiểu, consumer phải từ chối ở đâu?

Ví dụ, API đơn hàng đa tenant có thể yêu cầu `iss`, `sub`, `aud`, `exp` và `tenant_id`. API có thể chấp nhận `scope` để kiểm tra phạm vi endpoint. Vai trò chi tiết hoặc quyền trên một đơn hàng vẫn có thể cần kiểm tra bằng chính sách và dữ liệu hiện hành.

### 4.2. Phân loại required, optional và conditional

| Mức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Required** | Phải có trong mọi token thuộc hồ sơ | `iss`, `aud`, `exp` trong access token của API ví dụ |
| **Optional** | Có thể có hoặc không; thiếu không làm token sai nếu không dùng chức năng liên quan | `jti` khi hồ sơ không yêu cầu định danh từng JWT |
| **Conditional** | Bắt buộc khi thỏa một điều kiện nghiệp vụ | `tenant_id` bắt buộc với API đa tenant; `device_id` chỉ bắt buộc với token gắn thiết bị |

Không nhầm **optional** với **nullable**. Claim optional có thể vắng mặt. Claim nullable có mặt với giá trị `null`. Hai trạng thái này khác nhau và chỉ nên được chấp nhận khi schema mô tả rõ.

### 4.3. Ràng buộc cho giá trị

Ngoài kiểu dữ liệu, schema có thể định nghĩa:

- `minLength`, `maxLength`: giới hạn độ dài chuỗi.
- `pattern`: mẫu chuỗi, nếu có định dạng ổn định và được kiểm soát.
- `minimum`, `maximum`: giới hạn giá trị số theo chính sách ứng dụng.
- `minItems`, `maxItems`, `uniqueItems`: giới hạn mảng và yêu cầu phần tử duy nhất.
- `required`: các thuộc tính phải có trong object.
- `enum`: tập giá trị được phép khi miền giá trị nhỏ, ổn định.
- `additionalProperties`: có cho phép thuộc tính ngoài danh sách đã mô tả hay không.

Không áp đặt giới hạn tùy tiện làm token hợp lệ bị từ chối. Ngược lại, không để chuỗi, mảng hoặc object có kích thước không giới hạn vì có thể làm tăng tải bộ nhớ, thời gian phân tích và chi phí xử lý.

## 5. Ví dụ JSON Schema cho một access token

JSON Schema là một cách phổ biến để mô tả cấu trúc và ràng buộc của JSON. Ví dụ dưới đây dùng **JSON Schema Draft 2020-12** cho một hồ sơ access token của API đơn hàng. Đây là schema minh họa do ứng dụng đặt ra, không phải schema bắt buộc cho mọi JWT.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["iss", "sub", "aud", "exp", "tenant_id"],
  "properties": {
    "iss": {
      "type": "string",
      "minLength": 1
    },
    "sub": {
      "type": "string",
      "minLength": 1
    },
    "aud": {
      "oneOf": [
        {
          "type": "string",
          "minLength": 1
        },
        {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "minLength": 1
          }
        }
      ]
    },
    "exp": {
      "type": "number"
    },
    "nbf": {
      "type": "number"
    },
    "iat": {
      "type": "number"
    },
    "jti": {
      "type": "string",
      "minLength": 1
    },
    "tenant_id": {
      "type": "string",
      "minLength": 1,
      "maxLength": 128
    },
    "scope": {
      "type": "string",
      "maxLength": 2048
    },
    "roles": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "type": "string",
        "minLength": 1,
        "maxLength": 128
      }
    }
  },
  "additionalProperties": false
}
```

Các quyết định đáng chú ý trong schema:

- `required` bắt buộc `iss`, `sub`, `aud`, `exp`, `tenant_id` vì đây là hồ sơ access token đa tenant của ví dụ. Những trường này không bắt buộc trong mọi JWT.
- `aud` chấp nhận một chuỗi hoặc mảng chuỗi theo kiểu của RFC 7519; mảng phải có ít nhất một phần tử và không lặp.
- `exp`, `nbf`, `iat` là number vì chúng biểu diễn NumericDate.
- `roles` là mảng chuỗi theo hợp đồng riêng. JWT không tự định nghĩa claim `roles` hay ý nghĩa của các vai trò.
- `additionalProperties: false` tạo hồ sơ nghiêm ngặt: claim ngoài danh sách bị từ chối. Chỉ dùng lựa chọn này khi issuer và consumer đã thống nhất tập claim; nếu cần mở rộng tương thích, hãy thiết kế chính sách mở rộng có kiểm soát.

Schema trên kiểm tra kiểu và một số ràng buộc cấu trúc. Nó **chưa đủ** để chứng minh `iss` là issuer tin cậy, `aud` chứa API hiện tại, `exp` chưa qua, hay người dùng được phép truy cập đơn hàng. Những điều kiện đó cần bước xác minh ngữ nghĩa và chính sách riêng.

Ngoài ra, `type: "string"` chỉ xác nhận kiểu JSON. Nó chưa thực thi đầy đủ quy tắc **StringOrURI** của RFC 7519, theo đó chuỗi chứa dấu `:` phải là URI. Nếu hồ sơ cần quy tắc này, hãy bổ sung kiểm tra URI phù hợp trong bước kiểm tra ngữ nghĩa; không giả định mọi validator JSON Schema đều tự áp dụng quy tắc định dạng.

## 6. Kiểm tra kiểu dữ liệu và ngữ nghĩa

### 6.1. Kiểm tra kiểu trước khi diễn giải

Consumer nên xác minh kiểu JSON chính xác trước khi dùng claim:

| Claim | Hợp lệ theo schema ví dụ | Ví dụ sai kiểu |
| --- | --- | --- |
| `iss` | String | `{"iss": 17}` |
| `sub` | String | `{"sub": null}` |
| `aud` | String hoặc array of strings | `{"aud": 17}` |
| `exp` | Number | `{"exp": "1893456900"}` |
| `tenant_id` | String | `{"tenant_id": 17}` |
| `roles` | Array of non-empty strings | `{"roles": "admin"}` |

Không tự ép kiểu như chuyển số thành chuỗi, chuyển `"false"` thành boolean false, tách một chuỗi bằng dấu phẩy thành mảng, hoặc nhận `null` như thể claim không tồn tại. Nếu issuer thay đổi kiểu dữ liệu, đó là thay đổi hợp đồng cần quản lý phiên bản và tương thích.

### 6.2. Kiểm tra định dạng và miền giá trị

Một chuỗi có kiểu đúng vẫn có thể sai định dạng. Ví dụ, `tenant_id` là string nhưng có thể rỗng, quá dài hoặc chứa ký tự không hợp lệ theo quy ước mã tenant. Một mảng `roles` có thể chứa chuỗi rỗng hoặc giá trị ngoài tập vai trò được công bố.

Đặt ràng buộc cụ thể khi miền dữ liệu ổn định:

```json
{
  "tenant_id": "tenant_17",
  "roles": ["order_reader", "order_creator"]
}
```

Nếu hợp đồng quy định vai trò chỉ được chọn từ `order_reader`, `order_creator`, `order_manager`, consumer phải kiểm tra từng phần tử theo danh sách đó. Không chấp nhận giá trị bất kỳ chỉ vì nó là chuỗi.

Với định danh, hãy quy định rõ phạm vi duy nhất, cách viết và khả năng tái sử dụng. Đừng tự chuyển chữ hoa thành chữ thường hoặc loại bỏ ký tự để “sửa” mã nhận được nếu hợp đồng chưa định nghĩa cách chuẩn hóa.

### 6.3. Kiểm tra quan hệ giữa các claim

Schema cấu trúc thường chưa diễn tả hết các ràng buộc thời gian và nghiệp vụ. Consumer cần kiểm tra thêm:

- `exp` phải lớn hơn thời điểm hiện tại, có thể áp dụng clock skew nhỏ và có giới hạn rõ ràng.
- Nếu có `nbf`, token không được chấp nhận trước thời điểm đó, có tính đến clock skew theo chính sách.
- Nếu có `iat`, kiểm tra token không được phát hành trong tương lai quá giới hạn và không vượt tuổi tối đa mà hồ sơ cho phép.
- Nếu hồ sơ yêu cầu thứ tự thời gian, xác nhận `iat <= exp`, `nbf <= exp`; đây là quy tắc bổ sung của hồ sơ.
- `aud` phải chứa đúng định danh API nhận token, không chỉ đơn thuần là một chuỗi khác rỗng.
- `iss` phải khớp chính xác với một issuer được tin cậy cho loại token và audience đang xét.
- `tenant_id` phải thuộc phạm vi mà issuer được phép khẳng định; khi truy cập tài nguyên, tenant của tài nguyên phải được kiểm tra riêng.

Không dùng schema để thay thế kiểm tra thời gian bằng đồng hồ thực hoặc kiểm tra quan hệ giữa claims. Những phép so sánh này cần được thực hiện trong bước xác thực token theo hồ sơ.

## 7. Quy trình xác thực token và kiểm tra schema

Kiểm tra schema phải nằm trong một quy trình xác minh token hoàn chỉnh. Một luồng xử lý tổng quát:

```text
Nhận token
    |
    v
Kiểm tra kích thước, số phần và cấu trúc biểu diễn
    |
    v
Phân tích JOSE header an toàn, áp dụng allowlist thuật toán/khóa
    |
    v
Xác minh chữ ký JWS hoặc giải mã JWE theo hồ sơ được phép
    |
    v
Phân tích Claims Set thành JSON object
    |
    v
Kiểm tra tên claim trùng và cấu trúc JSON
    |
    v
Kiểm tra schema: required, type, format, bounds, arrays, objects
    |
    v
Kiểm tra ngữ nghĩa: iss, aud, exp, nbf, iat, loại token
    |
    v
Kiểm tra chính sách: chủ thể, tenant, scope, vai trò, tài nguyên
    |
    v
Chấp nhận hoặc từ chối yêu cầu
```

Thứ tự chi tiết phụ thuộc loại JWT và thư viện, nhưng có một nguyên tắc: **không sử dụng claims chưa được xác minh để cấp quyền hoặc thay đổi trạng thái**. Header cần được đọc để lựa chọn quy trình xác minh, song các giá trị trong header cũng là dữ liệu chưa tin cậy cho đến khi cơ chế bảo vệ được kiểm tra.

### 7.1. Giới hạn đầu vào trước khi xác thực

Token là dữ liệu đầu vào từ bên ngoài. Trước khi phân tích sâu, đặt giới hạn hợp lý cho:

- Tổng kích thước token và kích thước payload.
- Độ sâu lồng nhau của object/array.
- Số lượng claims và số phần tử trong mảng.
- Độ dài tên claim và giá trị chuỗi.
- Miền số, độ lớn số mũ và độ chính xác số được hỗ trợ.
- Thời gian xử lý và mức tài nguyên parser có thể sử dụng.

Giới hạn cần phù hợp với hồ sơ token thực tế; quá nhỏ có thể từ chối token hợp lệ, quá lớn có thể tạo cơ hội tiêu hao tài nguyên. Không cắt ngắn dữ liệu để biến một token sai thành token hợp lệ.

### 7.2. Tên claim trùng và parser JSON

RFC 7519 yêu cầu tên claim trong Claims Set là duy nhất. Parser phải từ chối đối tượng có tên trùng hoặc xử lý theo quy tắc thành viên xuất hiện cuối được RFC cho phép. Với dữ liệu bảo mật, nên từ chối tên trùng để tránh các thành phần khác nhau hiểu một token theo hai cách.

Việc phát hiện trùng phải diễn ra trước khi parser chuyển object thành map/dictionary và âm thầm ghi đè giá trị. Nếu thư viện không cung cấp chế độ phát hiện trùng, cần chọn parser phù hợp hoặc bổ sung bước kiểm tra có thể bảo toàn thông tin tên lặp.

### 7.3. Fail closed khi claim bắt buộc không hợp lệ

Nếu endpoint cần `tenant_id` nhưng token thiếu claim, sai kiểu hoặc giá trị không hợp lệ, không lấy tenant mặc định từ client và không tự suy ra từ một claim khác. Từ chối thao tác và ghi log ở mức an toàn. Log không nên ghi toàn bộ token hoặc dữ liệu nhạy cảm trong payload.

Với claim không biết, áp dụng chính sách rõ ràng: có thể bỏ qua claim mở rộng không liên quan nếu hồ sơ cho phép, nhưng tuyệt đối không dùng claim lạ để cấp quyền. Hồ sơ nghiêm ngặt có thể từ chối mọi claim ngoài allowlist.

## 8. Phân biệt schema validation với authorization

Một Claims Set vượt qua schema chỉ chứng minh dữ liệu có cấu trúc phù hợp với hợp đồng. Nó không chứng minh mọi khẳng định đều đúng trong thực tế hoặc chủ thể được phép thực hiện hành động.

Ví dụ token có:

```json
{
  "iss": "https://id.example.org",
  "sub": "user_42",
  "aud": "https://orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "scope": "orders:read",
  "roles": ["order_reader"]
}
```

Token có thể đúng schema, chữ ký hợp lệ và còn hạn. Tuy nhiên, khi người dùng đọc `order_777`, API vẫn phải kiểm tra:

1. Đơn hàng có thực sự thuộc `tenant_17` không?
2. Người dùng có quan hệ được phép với đơn hàng không?
3. Vai trò hoặc scope có áp dụng cho hành động và trạng thái hiện tại không?
4. Tài khoản hoặc quyền thành viên có bị thu hồi kể từ khi token được phát hành không?

Nếu đơn hàng thuộc tenant khác hoặc người dùng không được phép xem đơn cụ thể, yêu cầu phải bị từ chối. Schema không thay thế kiểm tra quyền trên tài nguyên.

## 9. Quản lý phiên bản schema và tương thích

### 9.1. Thay đổi nào tương thích?

| Thay đổi | Rủi ro tương thích | Hướng xử lý |
| --- | --- | --- |
| Thêm claim optional mới | Consumer cũ có thể bỏ qua; consumer strict có thể từ chối | Chỉ thêm khi chính sách unknown claim và allowlist cho phép |
| Thêm claim vào danh sách required | Token cũ không có trường mới sẽ bị từ chối | Phát hành schema/hồ sơ mới và có lộ trình chuyển đổi |
| Đổi string thành number | Consumer cũ có thể sai kiểu hoặc ép kiểu không an toàn | Coi là thay đổi không tương thích; dùng claim/version mới |
| Thu hẹp enum hoặc giới hạn giá trị | Token từng hợp lệ có thể bị từ chối | Kiểm tra dữ liệu đang phát hành trước khi áp dụng |
| Đổi ý nghĩa nhưng giữ tên | Consumer có thể đưa ra quyết định sai | Không đổi nghĩa tại chỗ; tạo tên hoặc phiên bản hợp đồng mới |
| Bỏ claim cũ | Consumer cũ có thể thiếu dữ liệu bắt buộc | Ngừng sử dụng theo lộ trình và thời gian sống tối đa của token |

### 9.2. Định danh phiên bản

Nếu hệ thống cần nhiều hồ sơ claims song song, có thể dùng một phiên bản hợp đồng được cấu hình theo issuer/audience, loại token hoặc một claim phiên bản riêng đã được định nghĩa. Không mặc định rằng một trường `version` tùy biến đã có ý nghĩa chuẩn trong JWT.

Consumer phải xác định schema nào áp dụng từ **ngữ cảnh tin cậy đã cấu hình**. Không cho một claim phiên bản chưa được xác minh tự chọn schema có yêu cầu yếu hơn. Nếu dùng claim phiên bản trong payload, chỉ sử dụng nó sau khi token đã được xác minh và vẫn phải ràng buộc với issuer, audience, loại token được phép.

### 9.3. Kiểm thử hợp đồng giữa issuer và consumer

Mỗi thay đổi schema nên có bộ trường hợp kiểm thử chung:

- Token hợp lệ tối thiểu với các claim bắt buộc.
- Token hợp lệ có các claim optional.
- Thiếu từng claim required.
- Sai kiểu cho từng loại JSON.
- Chuỗi rỗng, quá dài, sai pattern hoặc giá trị ngoài enum.
- Mảng rỗng, mảng quá lớn, phần tử trùng hoặc phần tử sai kiểu.
- NumericDate sai kiểu, quá xa trong tương lai hoặc thứ tự thời gian không hợp lệ.
- Claim không biết, claim trùng tên và JSON không hợp lệ.
- Issuer/audience không đúng, chữ ký không hợp lệ hoặc token hết hạn.
- Token cũ trong giai đoạn chuyển đổi schema.

Kiểm thử phải xác nhận cả kết quả chấp nhận/từ chối và việc không có tác dụng phụ khi token bị từ chối.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Lưu NumericDate thành chuỗi | Parser hoặc validator có thể diễn giải không nhất quán | Dùng JSON number theo RFC 7519 |
| Dùng `null` thay cho claim optional | Consumer có thể coi null là giá trị có mặt nhưng sai kiểu | Quy định rõ absent và nullable |
| Ép kiểu tự động | Chuỗi `"false"` có thể bị hiểu sai; dữ liệu sai định dạng được chấp nhận | Kiểm tra kiểu nghiêm ngặt, không coercion |
| Chỉ kiểm tra tên claim | Giá trị có thể sai kiểu, rỗng hoặc ngoài miền hợp lệ | Kiểm tra type, constraints và semantics |
| Coi schema là xác minh chữ ký | Kẻ tấn công có thể tạo payload đúng schema nhưng không đáng tin | Xác minh cơ chế bảo vệ trước khi sử dụng claims |
| Dùng `additionalProperties: false` mà không có chiến lược mở rộng | Token mới có thể bị consumer cũ từ chối | Quy định version và chính sách unknown claims |
| Cho phép object/mảng không giới hạn | Tăng nguy cơ tiêu hao bộ nhớ và CPU | Đặt giới hạn kích thước, độ sâu và số phần tử |
| Chỉ kiểm tra `scope` mà bỏ qua tài nguyên | Quyền ở mức endpoint bị nhầm thành quyền trên mọi đối tượng | Áp dụng authorization theo tài nguyên |

## 11. Tình huống tự kiểm tra

Một API yêu cầu access token có schema:

- `iss`: string và phải là issuer được cấu hình.
- `sub`: string không rỗng.
- `aud`: string hoặc mảng string chứa API hiện tại.
- `exp`: number theo NumericDate.
- `tenant_id`: string không rỗng.

Token nhận được có:

```json
{
  "iss": "https://id.example.org",
  "sub": "user_42",
  "aud": ["https://orders.example.org"],
  "exp": "1893456900",
  "tenant_id": "tenant_17"
}
```

**Câu hỏi:** Token có thể được chấp nhận chỉ vì `exp` biểu diễn một số nhìn giống Unix timestamp không?

**Trả lời:** Không. `exp` là string, trong khi schema yêu cầu number. Không tự ép kiểu chuỗi thành số. Token phải bị từ chối theo hồ sơ; issuer cần sửa cách phát hành. Sau khi kiểu đúng, consumer vẫn phải kiểm tra chữ ký, issuer, audience, thời gian thực và quyền nghiệp vụ.

Một tình huống khác: token có đúng schema và `tenant_id = "tenant_17"`, nhưng đơn hàng được yêu cầu thuộc `tenant_99`. API phải từ chối truy cập vì schema hợp lệ không chứng minh quyền truy cập tài nguyên.

## 12. Ghi nhớ

Thiết kế schema claims là xác định **cấu trúc dữ liệu mà một loại token cam kết cung cấp**: tên nào bắt buộc, kiểu gì được phép, miền giá trị nào hợp lệ và các điều kiện liên quan phải được kiểm tra ra sao. Hãy dùng đúng kiểu JSON theo RFC cho registered claims, định nghĩa chặt custom claims và quản lý thay đổi schema có lộ trình.

**Kiểm tra kiểu dữ liệu là điều kiện cần, không phải điều kiện đủ.** Một API chỉ nên sử dụng claims sau khi token được xác minh theo đúng issuer, audience, mục đích và các ràng buộc thời gian; quyết định cuối cùng vẫn phải tuân theo chính sách nghiệp vụ và quyền trên tài nguyên.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT Claims Set, StringOrURI, NumericDate và registered claims.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): kiểu dữ liệu JSON, object và array.
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12): từ vựng và quy tắc mô tả schema cho JSON.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành bảo mật khi xác minh và sử dụng JWT.
