# Thuộc tính bắt buộc

## 1. Thuộc tính bắt buộc trong kiểm tra ngữ nghĩa

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường cho phép người dùng khai báo đối tượng, tài nguyên, quy trình hoặc quy tắc bằng các thuộc tính. Ví dụ, một khai báo dịch vụ có thể có tên, image, số bản sao và cổng mạng. Một khai báo kết nối có thể cần địa chỉ máy chủ, tên cơ sở dữ liệu và phương thức xác thực.

Không phải thuộc tính nào cũng có thể bỏ qua. Một số thuộc tính là điều kiện cần để đối tượng có ý nghĩa hoặc để engine thực hiện thao tác. **Thuộc tính bắt buộc (required attribute)** là thuộc tính mà một khai báo phải cung cấp theo quy tắc của DSL trước khi được chấp nhận ở giai đoạn kiểm tra tương ứng.

Ví dụ DSL giả định:

~~~text
service "billing" {
    image "billing:2.1"
    replicas 3
    port 8080
}
~~~

Nếu schema của service yêu cầu image, khai báo trên có thể hợp lệ. Nếu người dùng viết:

~~~text
service "billing" {
    replicas 3
    port 8080
}
~~~

thì parser vẫn có thể phân tích được block. Cú pháp đúng chưa bảo đảm khai báo đầy đủ. Semantic analyzer cần biết loại service yêu cầu thuộc tính nào và phát hiện image bị thiếu.

Thuộc tính bắt buộc là một phần của hợp đồng ngữ nghĩa giữa người viết DSL và hệ thống thực thi. Nó giúp ngăn cấu hình thiếu dữ liệu quan trọng đi sâu vào runtime, giảm lỗi khó hiểu và làm cho ý định của khai báo rõ ràng hơn.

## 2. Phân biệt thuộc tính, trường, tham số và giá trị

Các khái niệm này có thể được dùng gần nhau trong tài liệu DSL, nhưng nên được định nghĩa rõ:

- **Thuộc tính (attribute/property):** một đặc điểm hoặc cấu hình gắn với đối tượng DSL, chẳng hạn image, replicas hoặc timeout.
- **Trường dữ liệu (field):** một phần tử trong bản ghi hoặc schema dữ liệu, chẳng hạn customer_id hoặc amount.
- **Tham số (parameter):** giá trị đầu vào của hàm, thao tác hoặc lời gọi quy trình.
- **Giá trị (value):** nội dung cụ thể được gán cho thuộc tính, trường hoặc tham số.
- **Khai báo (declaration):** cấu trúc giới thiệu đối tượng hoặc tên vào chương trình.

Trong bài này, thuật ngữ thuộc tính bắt buộc chủ yếu nói về các thuộc tính của một khai báo DSL. Cùng nguyên tắc có thể áp dụng cho tham số bắt buộc và trường bắt buộc trong schema, nhưng quy tắc của từng loại có thể khác nhau.

Ví dụ:

~~~text
database "analytics" {
    host "db.internal"
    database_name "warehouse"
    username "reporter"
}
~~~

host, database_name và username là thuộc tính. Chuỗi db.internal là giá trị của host. Nếu DSL quy định host và database_name là bắt buộc, việc thiếu một trong hai phải được phát hiện khi kiểm tra khai báo database.

## 3. Vì sao DSL cần thuộc tính bắt buộc?

Thuộc tính bắt buộc mang lại một số lợi ích quan trọng:

1. **Bảo đảm đối tượng đủ thông tin.** Engine không phải suy đoán giá trị thiết yếu từ một khai báo thiếu.
2. **Phát hiện lỗi sớm.** Người viết nhận được chẩn đoán trước khi triển khai hoặc thực thi.
3. **Làm rõ hợp đồng của miền.** Người dùng biết mỗi loại đối tượng cần những dữ liệu nào.
4. **Giảm trạng thái không hợp lệ.** Các giai đoạn sau có thể dựa vào những điều kiện đã được xác nhận.
5. **Hỗ trợ công cụ phát triển.** IDE có thể gợi ý thuộc tính còn thiếu và hiển thị tài liệu theo schema.
6. **Tăng tính nhất quán.** Các tệp DSL khác nhau tuân theo cùng một quy tắc cho cùng loại khai báo.

Không nên đánh dấu mọi thuộc tính là bắt buộc. Một thuộc tính chỉ nên bắt buộc khi miền thực sự cần nó hoặc khi thiếu nó làm cho kết quả không xác định, không an toàn hay không thể thực hiện.

## 4. Required khác với optional như thế nào?

Một thuộc tính có thể được phân loại theo mức độ bắt buộc:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Required | Phải được cung cấp hoặc phải có giá trị hiệu lực theo chính sách | image của service |
| Optional | Có thể bỏ qua; engine có thể dùng hành vi mặc định hoặc không thực hiện phần liên quan | description |
| Optional with default | Có thể bỏ qua; nếu thiếu thì dùng giá trị mặc định | timeout mặc định 30 giây |
| Conditional required | Chỉ bắt buộc khi một điều kiện khác được thỏa mãn | certificate khi TLS được bật |
| Derived | Được tính từ thuộc tính hoặc ngữ cảnh khác | endpoint được tạo từ host và port |

Ví dụ:

~~~text
service "billing" {
    image "billing:2.1"
    replicas 2
    timeout 45s
    description "Billing API"
}
~~~

Giả sử image là bắt buộc, replicas có mặc định là 1, timeout có mặc định là 30s và description là tùy chọn. Khi người dùng bỏ replicas, engine có thể sử dụng 1. Khi bỏ image, khai báo không hợp lệ nếu không có nguồn mặc định nào khác được DSL cho phép.

### 4.1. Required không nhất thiết đồng nghĩa với phải viết tường minh

Đây là quyết định ngữ nghĩa quan trọng. Có hai cách hiểu:

- **Explicitly required:** người dùng phải ghi thuộc tính trực tiếp trong khai báo.
- **Effectively required:** sau khi áp dụng mặc định, kế thừa hoặc cấu hình môi trường, đối tượng phải có giá trị hợp lệ.

Ví dụ, nếu image có thể lấy từ profile triển khai, khai báo service không ghi image có thể vẫn hợp lệ theo chính sách effectively required. Nếu quy định image phải xuất hiện trực tiếp trong từng block, profile không thể thay thế.

Đặc tả DSL cần nói rõ thuộc tính bắt buộc được kiểm tra trên văn bản nguồn hay trên cấu hình hiệu lực sau khi hợp nhất các nguồn.

## 5. Phân biệt thiếu, null, rỗng và giá trị mặc định

Một nguồn lỗi phổ biến là coi mọi trường hợp không có giá trị như nhau. Trên thực tế, ít nhất bốn trạng thái cần được phân biệt:

1. Thuộc tính không xuất hiện.
2. Thuộc tính xuất hiện với giá trị null.
3. Thuộc tính xuất hiện với giá trị rỗng.
4. Thuộc tính có giá trị cụ thể.

Ví dụ:

~~~text
service "api" {
    image "api:1.0"
}
~~~

Thuộc tính description không xuất hiện.

~~~text
service "api" {
    image "api:1.0"
    description null
}
~~~

description xuất hiện nhưng được gán null, nếu DSL hỗ trợ null.

~~~text
service "api" {
    image "api:1.0"
    description ""
}
~~~

description có giá trị chuỗi rỗng.

Ba trường hợp này có thể mang ý nghĩa khác nhau. Không xuất hiện có thể cho phép dùng mặc định; null có thể yêu cầu xóa giá trị kế thừa; chuỗi rỗng có thể là một giá trị hợp lệ hoặc bị từ chối theo ràng buộc.

### 5.1. Required và nullable là hai quy tắc riêng

Required trả lời câu hỏi thuộc tính có phải hiện diện hay không. Nullable trả lời câu hỏi giá trị null có được chấp nhận hay không.

| Required | Nullable | Ý nghĩa |
|---|---|---|
| Có | Không | Phải có thuộc tính và giá trị không được null |
| Có | Có | Phải có thuộc tính, nhưng giá trị có thể là null |
| Không | Không | Có thể bỏ qua; nếu xuất hiện thì không được null |
| Không | Có | Có thể bỏ qua hoặc cung cấp null |

Ví dụ một thuộc tính note có thể optional và nullable, trong khi image là required và không nullable. Không nên suy ra nullable chỉ từ việc thuộc tính optional.

### 5.2. Giá trị rỗng

Một chuỗi rỗng, danh sách rỗng hoặc map rỗng không phải lúc nào cũng là giá trị thiếu:

- Chuỗi rỗng có thể hợp lệ với thuộc tính label nhưng không hợp lệ với host.
- Danh sách rỗng có thể hợp lệ với danh sách exclude nhưng không hợp lệ với danh sách endpoints bắt buộc có ít nhất một phần tử.
- Map rỗng có thể hợp lệ nếu mọi cấu hình đều dùng mặc định, nhưng không hợp lệ nếu phải có ít nhất một rule.

Vì vậy, cần tách required khỏi các ràng buộc như non-empty, minItems hoặc minLength.

## 6. Khai báo schema thuộc tính

Để kiểm tra thuộc tính bắt buộc, compiler cần biết schema của từng loại khai báo. Schema mô tả thuộc tính nào được phép, thuộc tính nào bắt buộc, kiểu dữ liệu và các ràng buộc đi kèm.

Ví dụ schema khái niệm cho service:

| Thuộc tính | Kiểu | Bắt buộc | Mặc định | Ràng buộc |
|---|---|---:|---|---|
| image | String | Có | Không | Không rỗng |
| replicas | Integer | Không | 1 | Lớn hơn hoặc bằng 1 |
| port | Integer | Không | Không | Từ 1 đến 65535 |
| timeout | Duration | Không | 30s | Lớn hơn 0 |
| description | String | Không | Không | Tùy chọn |

Schema có thể được định nghĩa trong mã nguồn compiler, file metadata, plugin hoặc chính DSL. Dù lưu ở đâu, compiler cần có một mô hình thống nhất để kiểm tra.

### 6.1. Metadata cho thuộc tính

Một descriptor thuộc tính có thể gồm:

- Tên chuẩn.
- Loại giá trị.
- Trạng thái required.
- Trạng thái nullable.
- Giá trị mặc định hoặc biểu thức mặc định.
- Quy tắc kiểm tra bổ sung.
- Mô tả cho người dùng.
- Vị trí hoặc phiên bản schema.
- Chính sách kế thừa và ghi đè.

Ví dụ metadata minh họa:

~~~yaml
service:
  attributes:
    image:
      type: string
      required: true
      nullable: false
      minLength: 1
    replicas:
      type: integer
      required: false
      default: 1
      minimum: 1
    timeout:
      type: duration
      required: false
      default: 30s
      exclusiveMinimum: 0
~~~

Đây là schema minh họa, không phải định dạng bắt buộc của mọi DSL. Nếu dùng YAML hoặc JSON để lưu schema, cần có quy tắc kiểm tra chính schema đó để tránh metadata sai định dạng.

### 6.2. Danh sách thuộc tính được phép

Ngoài việc kiểm tra thiếu thuộc tính bắt buộc, semantic analyzer thường cần kiểm tra thuộc tính không được nhận diện:

~~~text
service "billing" {
    image "billing:2.1"
    replica_count 3
}
~~~

Nếu tên chuẩn là replicas, replica_count có thể là lỗi unknown attribute. Công cụ không nên âm thầm bỏ qua tên sai, vì người dùng có thể nghĩ cấu hình đã được áp dụng.

Có thể hỗ trợ alias có thời hạn để tương thích:

~~~text
replica_count -> replicas
~~~

Khi alias được dùng, công cụ có thể phát cảnh báo khuyến nghị chuyển sang tên chuẩn.

## 7. Kiểm tra thuộc tính bắt buộc trong pipeline ngữ nghĩa

Việc kiểm tra required thường là một phần của semantic analysis, sau khi parser đã xác định cấu trúc khai báo.

Một pipeline tổng quát:

~~~text
Source text
    |
    v
Lexer and parser
    |
    v
AST with attribute presence
    |
    v
Resolve declaration type
    |
    v
Load attribute schema
    |
    v
Apply defaults and inheritance
    |
    v
Validate required attributes
    |
    v
Validate types and constraints
    |
    v
Cross-attribute validation
    |
    v
Valid configuration / diagnostics
~~~

Thứ tự chính xác phụ thuộc DSL. Nếu required có nghĩa là phải viết tường minh, kiểm tra sự hiện diện phải diễn ra trước khi mặc định được materialize. Nếu required có nghĩa là phải có giá trị hiệu lực, có thể áp dụng mặc định và kế thừa trước rồi mới kiểm tra.

### 7.1. Parser ghi nhận sự hiện diện

Parser hoặc AST builder cần giữ thông tin thuộc tính có xuất hiện trong nguồn hay không. Nếu AST chỉ lưu giá trị mặc định ngay từ đầu, compiler có thể không phân biệt được người dùng đã viết thuộc tính hay chưa.

Ví dụ:

~~~text
ServiceDeclaration
    name = "billing"
    attributes:
        image = Missing
        replicas = Present(3)
        timeout = Missing
~~~

Trạng thái Missing và Present cần được biểu diễn tường minh nếu chính sách required hoặc default phụ thuộc vào sự hiện diện.

### 7.2. Xác định loại khai báo

Schema thuộc tính phụ thuộc loại đối tượng. Thuộc tính bắt buộc của service có thể khác với database, pipeline hoặc rule. Resolver cần xác định khai báo đang được kiểm tra thuộc loại nào trước khi tra schema.

### 7.3. Áp dụng mặc định và kế thừa

Nếu DSL hỗ trợ profile, template hoặc cấu hình môi trường, compiler có thể hợp nhất các nguồn. Cần định nghĩa rõ thứ tự ưu tiên, ví dụ:

1. Giá trị mặc định của schema.
2. Giá trị từ profile.
3. Giá trị kế thừa từ template.
4. Giá trị tường minh trong khai báo.

Đây chỉ là thứ tự minh họa. Một DSL khác có thể ưu tiên template hơn profile. Điều quan trọng là quy tắc hợp nhất phải xác định và có thể dự đoán.

### 7.4. Kiểm tra required

Sau khi đã xác định tập thuộc tính có hiệu lực, validator duyệt schema. Với mỗi thuộc tính required, nó kiểm tra điều kiện theo chính sách:

- Có xuất hiện trong nguồn hay không.
- Có giá trị sau khi áp dụng default hay không.
- Giá trị có phải null hay không.
- Giá trị có đáp ứng ràng buộc non-empty hay không.

### 7.5. Kiểm tra kiểu và ràng buộc

Thuộc tính có thể hiện diện nhưng sai kiểu hoặc sai miền giá trị. Required chỉ là một điều kiện; nó không thay thế type checking hay validation constraint.

Ví dụ:

~~~text
service "billing" {
    image "billing:2.1"
    replicas "three"
}
~~~

image đã có mặt, nhưng replicas có kiểu chuỗi thay vì số nguyên. Đây là lỗi kiểu, không phải lỗi thiếu thuộc tính.

## 8. Thuộc tính bắt buộc có điều kiện

Một số thuộc tính chỉ bắt buộc khi một thuộc tính hoặc trạng thái khác được chọn. Đây là conditional requiredness.

Ví dụ:

~~~text
service "public-api" {
    tls true
    certificate "certs/api.pem"
    private_key "secrets/api-key.pem"
}
~~~

Nếu tls là true, certificate và private_key có thể bắt buộc. Nếu tls là false, hai thuộc tính này có thể không cần thiết hoặc thậm chí không được phép xuất hiện.

Có thể mô tả quy tắc:

~~~text
if tls == true:
    require certificate
    require private_key
~~~

### 8.1. Điều kiện theo giá trị

Ví dụ:

~~~text
database "warehouse" {
    authentication "password"
    username "reporter"
    password secret("warehouse-password")
}
~~~

Nếu authentication là password, username và password cần có. Nếu authentication là workload_identity, DSL có thể yêu cầu identity_provider và không nhận password.

### 8.2. Điều kiện theo loại đối tượng

Một khai báo có thể có các biến thể:

~~~text
storage "archive" {
    kind "object"
    bucket "monthly-archive"
}
~~~

Nếu kind là object, bucket bắt buộc. Nếu kind là filesystem, root_path có thể bắt buộc. Validator cần xác định biến thể trước khi kiểm tra schema tương ứng.

### 8.3. Điều kiện theo môi trường

Một thuộc tính có thể bắt buộc trong production nhưng tùy chọn trong môi trường phát triển:

~~~text
deployment "billing" {
    environment "production"
    replicas 3
    health_check "/health"
}
~~~

Ví dụ, production có thể yêu cầu health_check trong khi development không yêu cầu. Nếu môi trường chỉ biết tại runtime, kiểm tra required có thể phải trì hoãn hoặc dùng profile môi trường đã resolve trước khi thực thi.

### 8.4. Tránh điều kiện mơ hồ

Nếu nhiều điều kiện cùng tác động đến một thuộc tính, cần định nghĩa cách kết hợp AND/OR và thứ tự ưu tiên. Tránh để validator áp dụng những quy tắc khác nhau tùy thứ tự duyệt thuộc tính.

## 9. Ràng buộc giữa nhiều thuộc tính

Có những quy tắc không thể biểu diễn bằng required riêng lẻ. Chúng liên quan đến sự hiện diện hoặc giá trị của nhiều thuộc tính.

### 9.1. Bắt buộc cùng nhau

Nếu có username thì password cũng phải có, hoặc ngược lại:

~~~text
if username is present:
    require password
if password is present:
    require username
~~~

### 9.2. Chính xác một thuộc tính

Một cấu hình có thể yêu cầu người dùng chọn đúng một trong hai cách cung cấp thông tin xác thực:

~~~text
authentication {
    password secret("db-password")
}
~~~

Hoặc:

~~~text
authentication {
    identity_file "keys/worker.json"
}
~~~

Quy tắc XOR yêu cầu có đúng một lựa chọn. Nếu không có lựa chọn nào, cấu hình thiếu thông tin. Nếu có cả hai, cấu hình mơ hồ hoặc vi phạm chính sách.

### 9.3. Ít nhất một thuộc tính

Một endpoint có thể cần ít nhất một trong các địa chỉ:

~~~text
endpoint "orders" {
    url "https://orders.internal"
}
~~~

Quy tắc có thể cho phép url, host và port, nhưng yêu cầu ít nhất một dạng kết nối hợp lệ. Đây là ràng buộc nhóm (at-least-one), khác với việc yêu cầu từng thuộc tính.

### 9.4. Phụ thuộc thứ tự hoặc quan hệ giá trị

Ví dụ:

~~~text
retention {
    minimum_days 7
    maximum_days 90
}
~~~

Cả hai thuộc tính có thể bắt buộc, đồng thời minimum_days phải nhỏ hơn hoặc bằng maximum_days. Kiểm tra sự hiện diện riêng lẻ không đủ để xác nhận cấu hình hợp lệ.

### 9.5. Ràng buộc tổng hợp

Một thuộc tính có thể bắt buộc khi một biểu thức kết hợp nhiều giá trị đúng:

~~~text
if region == "restricted" and external_access == true:
    require approval_reference
~~~

Các ràng buộc phức tạp nên được đặt tên và mô tả rõ. Điều này giúp thông báo lỗi có ý nghĩa hơn một biểu thức Boolean dài khó hiểu.

## 10. Giá trị mặc định và thuộc tính bắt buộc

Default là giá trị được dùng khi người viết không cung cấp thuộc tính. Required và default có thể cùng tồn tại, nhưng cần quy định rõ chúng tương tác thế nào.

### 10.1. Required không có default

~~~text
database "warehouse" {
    host "db.internal"
}
~~~

Nếu database_name bắt buộc và không có default, khai báo trên không hợp lệ.

### 10.2. Optional có default

~~~text
service "billing" {
    image "billing:2.1"
}
~~~

Nếu replicas optional với default 1, cấu hình hiệu lực sẽ có replicas bằng 1 dù nguồn không ghi thuộc tính này.

### 10.3. Required với default

Một schema có thể đánh dấu thuộc tính required nhưng cung cấp default. Điều này chỉ có ý nghĩa nếu required áp dụng lên cấu hình hiệu lực: giá trị phải tồn tại sau khi default được áp dụng. Nếu required có nghĩa phải viết tường minh, default không thể đáp ứng yêu cầu đó.

Vì vậy, schema nên tránh chỉ có một cờ required nếu ngôn ngữ cần phân biệt sự hiện diện tường minh và giá trị hiệu lực. Có thể dùng hai thuộc tính metadata riêng như explicitRequired và effectiveRequired.

### 10.4. Default phụ thuộc ngữ cảnh

Default có thể được tính từ môi trường:

~~~text
service "billing" {
    region current_environment.default_region
}
~~~

Khi default phụ thuộc môi trường hoặc dữ liệu runtime, validator cần biết thời điểm giá trị có thể được tính. Nếu không thể xác định trước khi chạy, công cụ có thể đánh dấu thuộc tính là deferred validation và kiểm tra trước khi thao tác cần nó.

### 10.5. Null không nhất thiết kích hoạt default

Một chính sách có thể áp dụng default chỉ khi thuộc tính không xuất hiện; nếu người dùng ghi null, đó là một giá trị tường minh và được xử lý theo quy tắc nullable. Một chính sách khác có thể coi null giống missing. Hai cách đều có thể dùng, nhưng phải được đặc tả và áp dụng nhất quán.

## 11. Kế thừa, template và hợp nhất cấu hình

DSL có thể cho phép một đối tượng kế thừa thuộc tính từ template hoặc profile:

~~~text
template "standard-service" {
    replicas 2
    timeout 45s
}

service "billing" extends "standard-service" {
    image "billing:2.1"
}
~~~

Nếu image là required và không có trong template, khai báo service phải cung cấp image. replicas và timeout được kế thừa.

### 11.1. Kiểm tra trước hay sau khi hợp nhất?

Có hai chính sách:

- Kiểm tra từng block riêng: mỗi block phải tự chứa mọi thuộc tính required.
- Kiểm tra cấu hình hiệu lực: hợp nhất template, profile, default và khai báo cụ thể rồi mới kiểm tra required.

Chính sách thứ hai phù hợp với DSL cấu hình có kế thừa, nhưng cần làm rõ nguồn gốc giá trị để chẩn đoán. Nếu thuộc tính được kế thừa, công cụ nên chỉ ra template đã cung cấp nó.

### 11.2. Quy tắc ghi đè

Khi nhiều nguồn cùng đặt một thuộc tính, DSL cần xác định:

- Nguồn nào có ưu tiên cao nhất.
- Có cho phép ghi đè thuộc tính immutable không.
- Có cho phép ghi đè bằng null không.
- Giá trị bị ghi đè có được cảnh báo không.
- Hai giá trị không tương thích có tạo lỗi hay không.

### 11.3. Xóa giá trị kế thừa

Nếu người dùng muốn xóa một thuộc tính được kế thừa, DSL có thể dùng cú pháp unset hoặc null có ý nghĩa đặc biệt. Điều này khác với việc không khai báo thuộc tính. Validator phải giữ được trạng thái để phân biệt.

## 12. Required trong danh sách, map và cấu trúc lồng nhau

Required không chỉ áp dụng cho thuộc tính đơn. Nó còn có thể áp dụng cho phần tử của cấu trúc dữ liệu.

### 12.1. Danh sách không rỗng

~~~text
cluster "main" {
    nodes [
        "node-a",
        "node-b"
    ]
}
~~~

Thuộc tính nodes có thể required và phải chứa ít nhất một phần tử. Hai điều kiện này khác nhau:

- required: thuộc tính nodes phải xuất hiện.
- minItems = 1: danh sách không được rỗng.

### 12.2. Phần tử bắt buộc trong map

~~~text
labels {
    team "finance"
    environment "production"
}
~~~

Schema có thể yêu cầu key team trong map labels, trong khi các key khác tùy chọn. Validator cần kiểm tra tập key bắt buộc và phân biệt key thiếu với key có giá trị rỗng.

### 12.3. Cấu trúc lồng nhau

~~~text
database "warehouse" {
    connection {
        host "db.internal"
        port 5432
    }
}
~~~

connection có thể là thuộc tính required của database. Bên trong connection, host bắt buộc còn port có default. Nếu toàn bộ connection bị thiếu, validator nên báo ở cấp database. Nếu connection có nhưng thiếu host, báo ở cấp connection.

### 12.4. Cardinality

Một thuộc tính dạng collection có thể có quy tắc:

- minItems: số phần tử tối thiểu.
- maxItems: số phần tử tối đa.
- uniqueItems: phần tử phải duy nhất.
- itemRequired: mỗi phần tử phải có một số trường.

Các quy tắc này bổ sung cho required của thuộc tính collection.

## 13. Thuộc tính bắt buộc trong DSL có schema động

Một số DSL làm việc với nguồn dữ liệu hoặc plugin mà schema chỉ biết khi kết nối đến hệ thống bên ngoài. Khi đó, không thể xác minh mọi thuộc tính ngay lúc biên dịch.

Ví dụ:

~~~text
source "customer-api" using connector "crm"
filter customer.status == "ACTIVE"
~~~

Nếu connector chỉ cung cấp schema khi runtime khởi tạo kết nối, công cụ có thể chưa biết customer có trường status hay không tại thời điểm parse.

### 13.1. Kiểm tra tĩnh và kiểm tra trì hoãn

Có thể phân loại ràng buộc:

- Statically verifiable: biết từ grammar, schema đã tải hoặc metadata module.
- Environment-dependent: phụ thuộc profile, quyền hoặc cấu hình triển khai.
- Runtime-dependent: chỉ biết sau khi đọc dữ liệu hoặc gọi dịch vụ.

Một thuộc tính required của khai báo DSL thường nên kiểm tra tĩnh nếu schema đã có. Ràng buộc phụ thuộc hệ thống ngoài có thể được đánh dấu deferred và phải được xác minh trước khi thực hiện thao tác có rủi ro.

### 13.2. Không bỏ qua kiểm tra vì schema động

Schema động không có nghĩa validator nên chấp nhận mọi thứ. Có thể kiểm tra các điều kiện đã biết trước, sau đó xác minh phần còn lại khi connector trả metadata. Nếu metadata không thể tải, đây là lỗi khởi tạo hoặc lỗi môi trường cần được báo rõ.

### 13.3. Phiên bản schema

Nếu schema bên ngoài thay đổi, một thuộc tính từng được xem là optional có thể trở thành required hoặc ngược lại. Để tái lập kết quả, execution nên ghi nhận phiên bản schema hoặc metadata snapshot đã dùng khi validate.

## 14. Thiết kế thông báo lỗi cho thuộc tính bắt buộc

Một lỗi required tốt cần chỉ ra:

- Loại khai báo đang được kiểm tra.
- Tên thuộc tính bị thiếu.
- Vị trí khai báo hoặc block chứa thuộc tính.
- Lý do thuộc tính bắt buộc.
- Điều kiện khiến nó trở thành bắt buộc nếu là conditional required.
- Nguồn giá trị có thể cung cấp nếu DSL hỗ trợ template hoặc profile.

Ví dụ nguồn:

~~~text
service "billing" {
    replicas 2
}
~~~

Thông báo:

~~~text
billing.dsl:1:1: error DSL-REQUIRED-001
Thiếu thuộc tính bắt buộc "image" trong khai báo service "billing".
Hãy cung cấp image trong service hoặc trong template được kế thừa.
~~~

### 14.1. Mã lỗi ổn định

Mã lỗi nên tách khỏi nội dung message. Ví dụ:

| Mã | Ý nghĩa |
|---|---|
| DSL-REQUIRED-001 | Thiếu thuộc tính bắt buộc |
| DSL-REQUIRED-002 | Thiếu thuộc tính bắt buộc theo điều kiện |
| DSL-REQUIRED-003 | Không có lựa chọn nào trong nhóm required |
| DSL-REQUIRED-004 | Có nhiều lựa chọn trong nhóm chỉ cho phép một |
| DSL-ATTRIBUTE-001 | Thuộc tính không được nhận diện |
| DSL-ATTRIBUTE-002 | Thuộc tính có giá trị null không được phép |
| DSL-ATTRIBUTE-003 | Thuộc tính có giá trị rỗng không hợp lệ |

Đây là nhóm mã minh họa. Một dự án nên duy trì registry để tránh dùng cùng mã cho hai nghĩa khác nhau.

### 14.2. Vị trí nguồn

Khi thuộc tính bị thiếu, không có token cụ thể để đánh dấu. Công cụ có thể trỏ đến:

- Vị trí bắt đầu khai báo.
- Tên đối tượng.
- Dấu mở block.
- Vị trí nơi thuộc tính thường được đặt theo quy ước.

Nếu thiếu thuộc tính trong một cấu trúc lồng nhau, nên trỏ đến block gần nhất có trách nhiệm cung cấp nó.

### 14.3. Gom nhóm lỗi

Nếu một khai báo thiếu nhiều thuộc tính, validator có thể báo tất cả trong một lượt:

~~~text
service "billing" {
    replicas 2
}
~~~

~~~text
service "billing":
  - missing required attribute: image
  - missing required attribute: region
~~~

Gom nhóm giúp người dùng sửa nhiều lỗi cùng lúc. Tuy nhiên, nếu một lỗi khiến các kiểm tra tiếp theo không còn đáng tin cậy, validator nên tránh phát sinh thông báo dây chuyền.

## 15. Kiểm tra required trong Java

Một triển khai Java có thể mô hình hóa schema thuộc tính bằng descriptor và dùng validator chung cho nhiều loại khai báo.

### 15.1. Descriptor thuộc tính

Ví dụ giản lược:

~~~java
record AttributeDescriptor(
    String name,
    boolean required,
    boolean nullable,
    Object defaultValue
) {
}
~~~

Descriptor mô tả một thuộc tính. Trong hệ thống thực tế, có thể bổ sung type descriptor, validator, source documentation, conditional rule và thông tin vị trí khai báo schema.

### 15.2. Biểu diễn sự hiện diện

Không nên chỉ dùng null để biểu diễn cả missing và explicit null. Có thể dùng kiểu riêng:

~~~java
sealed interface AttributeValue {
    record Missing() implements AttributeValue {}
    record ExplicitNull() implements AttributeValue {}
    record Present(Object value) implements AttributeValue {}
}
~~~

Nhờ đó validator phân biệt được:

- Không có thuộc tính.
- Có thuộc tính nhưng được gán null.
- Có thuộc tính với giá trị cụ thể.

### 15.3. Validator cơ bản

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

record Diagnostic(String code, String message) {
}

final class RequiredAttributeValidator {
    List<Diagnostic> validate(
        Map<String, AttributeValue> values,
        List<AttributeDescriptor> schema
    ) {
        List<Diagnostic> diagnostics = new ArrayList<>();

        for (AttributeDescriptor descriptor : schema) {
            AttributeValue value = values.getOrDefault(
                descriptor.name(),
                new AttributeValue.Missing()
            );

            if (descriptor.required()
                    && value instanceof AttributeValue.Missing) {
                diagnostics.add(new Diagnostic(
                    "DSL-REQUIRED-001",
                    "Missing required attribute: " + descriptor.name()
                ));
                continue;
            }

            if (!descriptor.nullable()
                    && value instanceof AttributeValue.ExplicitNull) {
                diagnostics.add(new Diagnostic(
                    "DSL-ATTRIBUTE-002",
                    "Attribute cannot be null: " + descriptor.name()
                ));
            }
        }

        return List.copyOf(diagnostics);
    }
}
~~~

Đây là ví dụ nền tảng, chưa áp dụng default, conditional rule, kiểu dữ liệu hoặc source span. Điểm chính là validator kiểm tra từng descriptor và tạo diagnostics thay vì dừng ngay ở thuộc tính đầu tiên.

### 15.4. Áp dụng default đúng thời điểm

Nếu default đáp ứng required theo chính sách effective value, có thể tạo bước chuẩn hóa:

~~~java
Object effectiveValue(
    AttributeValue supplied,
    AttributeDescriptor descriptor
) {
    if (supplied instanceof AttributeValue.Missing
            && descriptor.defaultValue() != null) {
        return descriptor.defaultValue();
    }
    if (supplied instanceof AttributeValue.Present present) {
        return present.value();
    }
    return null;
}
~~~

Trong triển khai đầy đủ, cần phân biệt default có giá trị null với không có default. Có thể dùng Optional hoặc một kiểu DefaultValue riêng thay vì dùng null làm dấu hiệu vắng mặt.

### 15.5. Conditional validator

Quy tắc có điều kiện có thể được mô hình hóa riêng:

~~~java
record ConditionalRequirement(
    String controllingAttribute,
    Object expectedValue,
    List<String> requiredAttributes
) {
}
~~~

Validator đọc giá trị hiệu lực của controllingAttribute. Nếu nó bằng expectedValue, validator yêu cầu mọi thuộc tính trong requiredAttributes phải có giá trị theo chính sách.

Trong DSL lớn, nên biểu diễn điều kiện bằng một mô hình rule có kiểu thay vì dùng chuỗi biểu thức tùy ý. Điều đó giúp kiểm tra kiểu và báo lỗi rõ ràng hơn.

## 16. Thuộc tính bắt buộc và thiết kế builder API

Nếu DSL có API Java để tạo cấu hình thay vì chỉ đọc văn bản, có thể dùng builder để làm rõ thuộc tính bắt buộc.

Ví dụ:

~~~java
ServiceConfig config = ServiceConfig.builder()
    .name("billing")
    .image("billing:2.1")
    .replicas(3)
    .build();
~~~

Một builder có thể yêu cầu image trước khi build, hoặc tạo đối tượng rồi để validator kiểm tra. Có hai chiến lược:

- **Compile-time API constraint:** thiết kế kiểu hoặc builder theo nhiều trạng thái để không thể gọi build trước khi cung cấp trường bắt buộc.
- **Runtime validation:** cho phép xây dựng linh hoạt nhưng kiểm tra đầy đủ khi build.

Compile-time constraint có thể an toàn hơn nhưng làm API phức tạp. Runtime validation dễ mở rộng và phù hợp khi schema chỉ biết lúc chạy.

### 16.1. Constructor yêu cầu tham số thiết yếu

Nếu đối tượng có ít thuộc tính bắt buộc, constructor có thể nhận chúng trực tiếp:

~~~java
record ServiceConfig(String name, String image, int replicas) {
    ServiceConfig {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (image == null || image.isBlank()) {
            throw new IllegalArgumentException("image is required");
        }
        if (replicas < 1) {
            throw new IllegalArgumentException("replicas must be positive");
        }
    }
}
~~~

Đối với cấu hình có nhiều thuộc tính hoặc schema động, constructor lớn không phải lựa chọn phù hợp. Có thể dùng builder cùng validator để giữ mô hình dễ mở rộng.

## 17. Tương thích phiên bản schema

Khi DSL phát triển, một thuộc tính optional có thể trở thành required. Thay đổi này có thể làm các tệp cũ không còn hợp lệ.

Ví dụ phiên bản 1:

~~~text
service "billing" {
    image "billing:1.0"
}
~~~

Trong phiên bản 2, schema yêu cầu region. Tệp cũ thiếu region sẽ phát sinh lỗi nếu được kiểm tra theo schema mới.

### 17.1. Chiến lược chuyển đổi

Có thể:

- Giữ default hợp lý trong một giai đoạn chuyển tiếp.
- Phát warning trước khi nâng mức thành required.
- Yêu cầu khai báo phiên bản DSL hoặc schema.
- Cung cấp migration tool để thêm thuộc tính mới.
- Từ chối cấu hình cũ nếu thiếu dữ liệu thiết yếu và không có default an toàn.

### 17.2. Versioned validation

Validator nên biết phiên bản schema đang áp dụng. Cùng một văn bản có thể hợp lệ với schema v1 nhưng không hợp lệ với schema v2. Diagnostics cần nêu phiên bản hoặc profile đã dùng nếu điều đó giúp người dùng xử lý.

### 17.3. Không tự điền giá trị tùy tiện

Migration có thể thêm thuộc tính required chỉ khi có giá trị mặc định được miền chấp nhận. Không nên tự suy đoán region, quyền, thông tin xác thực hoặc các giá trị có ảnh hưởng bảo mật và vận hành.

## 18. Hiệu năng và tính nhất quán của validator

Kiểm tra required thường có chi phí nhỏ, nhưng DSL lớn có thể có nhiều đối tượng, nhiều schema và nhiều quy tắc điều kiện.

Một số nguyên tắc triển khai:

- Tải và cache schema theo phiên bản.
- Chuẩn hóa tên thuộc tính một lần theo quy tắc của DSL.
- Duyệt thuộc tính theo thứ tự ổn định để diagnostics có kết quả nhất quán.
- Tránh đánh giá cùng một biểu thức điều kiện nhiều lần nếu có thể lưu kết quả an toàn.
- Phân biệt validation tĩnh với validation phụ thuộc môi trường.
- Giới hạn số lượng diagnostics nếu đầu vào cực lớn, đồng thời báo rằng kết quả đã bị giới hạn.
- Không để validator sửa trực tiếp AST nguồn theo cách làm mất thông tin thuộc tính đã được cung cấp.

Nếu validator áp dụng default hoặc hợp nhất template, nên tạo một cấu hình hiệu lực riêng hoặc lưu provenance cho từng giá trị. Điều này giúp biết giá trị đến từ nguồn nào và giải thích tại sao một thuộc tính được xem là đã có.

## 19. Bảo mật và quyền khi kiểm tra thuộc tính bắt buộc

Thuộc tính bắt buộc đôi khi chứa dữ liệu nhạy cảm hoặc điều khiển quyền truy cập:

- Secret hoặc credential.
- Đường dẫn file.
- Tên tài khoản và role.
- Endpoint nội bộ.
- Chính sách mạng.
- Tham chiếu tài nguyên có quyền hạn cao.

Validator cần xác nhận sự hiện diện và hình dạng của thuộc tính mà không ghi giá trị nhạy cảm vào diagnostics hoặc log. Với secret, có thể chỉ báo thiếu secret theo tên tham chiếu thay vì hiển thị nội dung.

Việc thuộc tính đã có mặt không chứng minh giá trị đó an toàn. Một trường path vẫn cần được kiểm tra phạm vi truy cập; một endpoint vẫn cần chính sách mạng; một role vẫn cần authorization. Required validation là điều kiện về tính đầy đủ, không phải cơ chế bảo mật toàn diện.

## 20. Quy trình thiết kế và triển khai thuộc tính bắt buộc

Khi bổ sung quy tắc required cho một loại khai báo DSL, có thể thực hiện theo trình tự:

1. **Xác định đối tượng miền.** Làm rõ loại khai báo và ý nghĩa của nó.
2. **Liệt kê thuộc tính.** Phân loại thuộc tính thiết yếu, tùy chọn, có default và được suy ra.
3. **Định nghĩa requiredness.** Nêu rõ bắt buộc tường minh hay bắt buộc trên cấu hình hiệu lực.
4. **Định nghĩa null và empty.** Phân biệt missing, null, chuỗi rỗng và collection rỗng.
5. **Xác định schema.** Khai báo kiểu, default, giới hạn và metadata của từng thuộc tính.
6. **Đặc tả điều kiện.** Nêu rõ quan hệ giữa các thuộc tính, biến thể và môi trường.
7. **Định nghĩa hợp nhất.** Quy định thứ tự default, profile, template và giá trị tường minh.
8. **Tích hợp semantic analyzer.** Kiểm tra sự hiện diện trước hoặc sau chuẩn hóa theo chính sách.
9. **Tạo diagnostics.** Dùng mã ổn định, vị trí nguồn và tên thuộc tính.
10. **Bảo toàn provenance.** Ghi nhận nguồn của giá trị hiệu lực để giải thích kết quả.
11. **Xem xét tương thích.** Đánh giá ảnh hưởng khi schema hoặc DSL version thay đổi.
12. **Tài liệu hóa hợp đồng.** Mô tả thuộc tính nào bắt buộc và cách người dùng đáp ứng yêu cầu.

Các bước này là một phần của thiết kế ngữ nghĩa. Chúng cần được thống nhất giữa người thiết kế DSL, người triển khai compiler và người dùng miền.

## 21. Những sai lầm thường gặp

### 21.1. Coi missing, null và empty là một trạng thái

Điều này làm validator không thể áp dụng đúng default hoặc quy tắc nullable. Hãy biểu diễn sự hiện diện tường minh nếu các trạng thái có ý nghĩa khác nhau.

### 21.2. Dùng required thay cho mọi ràng buộc

Một thuộc tính có thể hiện diện nhưng sai kiểu, rỗng hoặc nằm ngoài miền giá trị. Required chỉ kiểm tra tính hiện diện theo chính sách; cần các validator riêng cho kiểu và giới hạn.

### 21.3. Không nói rõ default có đáp ứng required không

Nếu một thuộc tính vừa required vừa có default, người dùng và compiler có thể hiểu khác nhau. Hãy xác định required áp dụng cho văn bản nguồn hay cấu hình hiệu lực.

### 21.4. Kiểm tra từng block trước khi hợp nhất

Với DSL có template hoặc profile, kiểm tra từng block riêng có thể báo thiếu thuộc tính vốn được kế thừa hợp lệ. Hãy xác định thời điểm validation tương ứng với mô hình cấu hình.

### 21.5. Bỏ qua thuộc tính không nhận diện

Tên sai có thể khiến cấu hình bị bỏ qua và tạo cảm giác rằng thao tác đã được áp dụng. Nên báo unknown attribute hoặc dùng alias được quản lý rõ ràng.

### 21.6. Dừng ở lỗi required đầu tiên

Với nhiều thuộc tính thiếu, báo một lỗi mỗi lần khiến quá trình sửa tốn công. Có thể gom các lỗi độc lập trong cùng khai báo, nhưng tránh thông báo dây chuyền khi dữ liệu nền không đáng tin cậy.

### 21.7. Dùng điều kiện required quá phức tạp

Một biểu thức điều kiện dài và không có tên khiến khó hiểu tại sao thuộc tính bị yêu cầu. Hãy chia quy tắc thành các điều kiện có ý nghĩa miền và tạo diagnostics giải thích điều kiện kích hoạt.

### 21.8. Tự tạo giá trị cho thuộc tính thiết yếu

Không phải thuộc tính nào cũng có default an toàn. Tự đoán endpoint, credential hoặc vùng triển khai có thể tạo cấu hình sai hoặc rủi ro. Chỉ dùng default khi có căn cứ rõ.

### 21.9. Chỉ kiểm tra ở giao diện người dùng

Một cấu hình có thể được tạo qua CLI, API, file hoặc plugin. Required validation phải nằm ở lớp ngữ nghĩa dùng chung hoặc ranh giới tin cậy của hệ thống, không chỉ dựa vào giao diện.

## 22. Câu hỏi tự kiểm tra

1. Thuộc tính bắt buộc là gì và nó thuộc giai đoạn nào trong xử lý DSL?
2. Phân biệt thuộc tính required, optional, optional with default và conditional required.
3. Vì sao phải phân biệt missing, null và giá trị rỗng?
4. Required và nullable là hai quy tắc riêng như thế nào?
5. Một schema thuộc tính nên mô tả những thông tin nào ngoài tên thuộc tính?
6. Trình bày các bước kiểm tra required trong semantic analysis.
7. Khi nào default có thể đáp ứng yêu cầu required? Khi nào default không được tính là giá trị tường minh?
8. Giải thích conditional requiredness bằng ví dụ TLS hoặc phương thức xác thực.
9. Phân biệt quy tắc exactly-one với at-least-one.
10. Với DSL có template và profile, nên kiểm tra required trước hay sau khi hợp nhất? Nêu lý do và điều kiện.
11. Vì sao thuộc tính bắt buộc trong schema động có thể cần deferred validation?
12. Một thông báo lỗi thiếu thuộc tính nên cung cấp những thông tin nào?
13. Hãy mô tả cách Java validator phân biệt Missing, ExplicitNull và Present.
14. Khi nâng phiên bản schema và thêm thuộc tính required, có những chiến lược tương thích nào?
15. Vì sao required validation không thay thế kiểm tra kiểu, giới hạn giá trị hoặc authorization?
