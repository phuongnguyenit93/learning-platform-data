# Schema và validation

Trong một DSL cấu hình (*configuration Domain-Specific Language*), **schema** mô tả cấu trúc và quy tắc của dữ liệu cấu hình; **validation** là quá trình kiểm tra dữ liệu thực tế có tuân theo schema và các quy tắc miền hay không. Hai khái niệm này giúp một cấu hình không chỉ đúng cú pháp mà còn có kiểu, giá trị và quan hệ hợp lệ để hệ thống có thể sử dụng an toàn.

Ví dụ, một DSL cấu hình dịch vụ có thể cho phép:

~~~text
service "catalog" {
    replicas = 3
    region = "asia-southeast1"
    image = "registry.example.com/catalog:v2"
}
~~~

Schema của service có thể quy định:

- replicas là số nguyên, bắt buộc và lớn hơn 0.
- region là chuỗi thuộc một tập vùng được hỗ trợ.
- image là chuỗi có định dạng image reference hợp lệ.
- Tên dịch vụ phải duy nhất trong project.

Parser có thể chấp nhận được các ký tự và cấu trúc block của ví dụ, nhưng validation mới xác định replicas bằng 0 có hợp lệ hay không, vùng có được hỗ trợ hay không và tên image có đúng định dạng hay không.

Schema và validation là nền tảng của DSL cấu hình vì chúng giúp phát hiện lỗi sớm, tạo thông báo dễ hiểu, hỗ trợ editor, sinh tài liệu và giữ dữ liệu cấu hình nhất quán giữa các môi trường.

## 1. Schema là gì?

Schema là mô tả có cấu trúc về dữ liệu được phép xuất hiện. Một schema thường định nghĩa:

- Tên và loại của object hoặc resource.
- Các thuộc tính và kiểu dữ liệu.
- Thuộc tính bắt buộc hay tùy chọn.
- Giá trị mặc định.
- Giới hạn và constraint.
- Kiểu lồng nhau và collection.
- Enum hoặc tập giá trị được phép.
- Quan hệ tham chiếu giữa các object.
- Quy tắc version và khả năng mở rộng.

Ví dụ schema khái niệm:

~~~text
schema Service {
    name: String required
    replicas: Integer required min(1) max(100)
    region: Region required
    image: ImageReference required
    enabled: Boolean default(true)
}
~~~

Schema này mô tả hình dạng dữ liệu của một Service. Một cấu hình cụ thể là một instance của schema:

~~~text
Service {
    name = "catalog"
    replicas = 3
    region = "asia-southeast1"
    image = "registry.example.com/catalog:v2"
}
~~~

### 1.1. Schema như một hợp đồng

Schema là hợp đồng giữa người viết cấu hình và hệ thống đọc cấu hình. Người viết biết thuộc tính nào được phép dùng, còn compiler hoặc runtime biết dữ liệu nào có thể tin cậy sau khi validation thành công.

Hợp đồng này có thể được dùng ở nhiều nơi:

- Parser và semantic analyzer.
- CLI validation command.
- IDE completion, hover và diagnostics.
- Code generator.
- Runtime configuration loader.
- Documentation generator.
- Schema registry và công cụ migration.

Nếu mỗi thành phần tự định nghĩa quy tắc riêng, cùng một cấu hình có thể hợp lệ trong IDE nhưng thất bại khi chạy. Một schema model dùng chung giúp giảm sự sai khác này.

### 1.2. Schema khác cú pháp

Cú pháp mô tả cách viết chương trình; schema mô tả dữ liệu và ràng buộc được phép.

Ví dụ, grammar có thể chấp nhận:

~~~text
replicas = "many"
~~~

Vì đây là một assignment hợp lệ về mặt cú pháp. Nhưng nếu schema yêu cầu replicas là Integer, validation sẽ báo lỗi kiểu.

### 1.3. Schema khác dữ liệu

Schema là mô tả; dữ liệu là giá trị cụ thể. Một schema có thể được áp dụng cho nhiều file cấu hình hoặc nhiều môi trường:

~~~text
config/
├── service.dev.dsl
├── service.staging.dsl
└── service.prod.dsl
~~~

Cả ba file có thể tuân theo cùng một schema Service, nhưng giá trị khác nhau.

## 2. Validation là gì?

Validation là quá trình kiểm tra dữ liệu đầu vào so với schema và các quy tắc nghiệp vụ. Kết quả thường là tập diagnostics, trạng thái hợp lệ và có thể là một cấu trúc dữ liệu đã được chuẩn hóa.

Ví dụ:

~~~text
service "catalog" {
    replicas = 0
    region = "moon-base"
}
~~~

Validator có thể phát hiện:

~~~text
error: replicas must be greater than or equal to 1
error: region "moon-base" is not supported
~~~

Validation không chỉ kiểm tra một giá trị riêng lẻ. Nó có thể kiểm tra quan hệ giữa nhiều thuộc tính, tham chiếu sang resource khác, uniqueness toàn project hoặc điều kiện phụ thuộc môi trường.

### 2.1. Validation và parsing

Parsing kiểm tra cấu trúc văn bản có tuân theo grammar không và tạo AST. Validation kiểm tra AST hoặc dữ liệu đã parse có thỏa các quy tắc schema và miền không.

~~~text
Source text
    |
    v
Lexer / Parser
    |
    v
AST
    |
    v
Schema validation
    |
    v
Validated model
~~~

Ví dụ, biểu thức gán thiếu giá trị có thể là lỗi cú pháp. Gán chuỗi vào trường Integer có thể parse được nhưng sai kiểu. Gán số 0 vào trường có minimum bằng 1 có thể đúng kiểu nhưng vi phạm constraint.

### 2.2. Validation và execution

Validation thường xảy ra trước khi cấu hình được áp dụng. Một hệ thống có thể từ chối thực thi khi còn lỗi nghiêm trọng. Một số cảnh báo vẫn cho phép chạy nếu policy cho phép.

### 2.3. Validation không tự sửa dữ liệu

Validator nên báo vấn đề và có thể gợi ý cách sửa. Việc tự thay đổi giá trị là một thao tác riêng, thường gọi là normalization, migration hoặc autofix. Cần phân biệt rõ kiểm tra với ghi sửa.

## 3. Các lớp validation

Một hệ thống DSL thường kiểm tra dữ liệu qua nhiều lớp. Mỗi lớp phát hiện một loại lỗi khác nhau.

~~~text
Raw source
   |
   v
1. Syntax validation
   |
   v
2. Structural validation
   |
   v
3. Type validation
   |
   v
4. Constraint validation
   |
   v
5. Reference validation
   |
   v
6. Cross-field / domain validation
   |
   v
7. Environment / runtime preflight
~~~

Không phải DSL nào cũng có đủ các bước trên. Thứ tự cũng có thể thay đổi tùy cách compiler tổ chức pipeline.

### 3.1. Syntax validation

Kiểm tra token, dấu ngoặc, block, assignment và grammar.

~~~text
service "catalog" {
    replicas = 3
~~~

Nếu thiếu dấu đóng block, parser có thể báo lỗi cú pháp.

### 3.2. Structural validation

Kiểm tra object có đúng loại, field có được phép xuất hiện và cấu trúc lồng nhau có đúng không.

Ví dụ replicas không được đặt ở root nếu schema chỉ cho phép nó trong service.

### 3.3. Type validation

Kiểm tra kiểu của giá trị có tương thích với kiểu schema hay không.

~~~text
replicas = "three"
~~~

Nếu schema yêu cầu Integer, chuỗi three không hợp lệ.

### 3.4. Constraint validation

Kiểm tra giới hạn như min/max, pattern, length, range, format hoặc tập giá trị.

~~~text
replicas = 0
~~~

Giá trị có kiểu Integer nhưng có thể vi phạm minimum bằng 1.

### 3.5. Reference validation

Kiểm tra tham chiếu đến resource, module, secret, network hoặc symbol khác có tồn tại và có thể truy cập không.

~~~text
service "catalog" {
    network = ref("network.private")
}
~~~

Nếu network.private không tồn tại hoặc không được export, validator phát diagnostic.

### 3.6. Cross-field validation

Kiểm tra quan hệ giữa nhiều trường. Ví dụ, nếu tls bằng true, thuộc tính certificate phải được khai báo. Nếu mode bằng managed, người dùng không được đồng thời cung cấp manualAddress.

### 3.7. Domain validation

Kiểm tra quy tắc nghiệp vụ cụ thể của miền. Ví dụ, database replica count không thể lớn hơn giới hạn của service tier, hoặc một loại resource không được dùng trong region nhất định.

### 3.8. Environment validation

Một số điều kiện chỉ có thể xác định trong môi trường thực tế: credential có quyền truy cập không, endpoint có reachable không, quota có đủ không. Những kiểm tra này thường thuộc preflight hoặc runtime validation, không nên trộn tất cả vào parser.

## 4. Kiểu dữ liệu trong schema

Schema cần có hệ thống kiểu rõ ràng để validator biết giá trị nào được phép.

### 4.1. Primitive types

Các kiểu cơ bản thường gồm:

| Kiểu | Ví dụ | Ý nghĩa |
|---|---|---|
| String | "catalog" | Văn bản |
| Integer | 3 | Số nguyên |
| Decimal | 12.50 | Số thập phân |
| Boolean | true | Đúng hoặc sai |
| Duration | 30s | Khoảng thời gian |
| Size | 512MB | Kích thước |
| Date | 2026-11-15 | Ngày |
| Timestamp | 2026-11-15T10:00:00Z | Thời điểm |
| Identifier | service.catalog | Định danh |

Một DSL có thể có thêm kiểu miền như IPAddress, URL, ImageReference, Port, CPU hoặc Memory.

### 4.2. Integer và Decimal

Không nên tùy tiện chuyển Decimal sang Integer nếu việc đó làm mất phần thập phân. Nếu schema yêu cầu Integer, giá trị 3.5 cần bị từ chối hoặc chuyển đổi theo quy tắc tường minh.

Với giá trị tài chính, Decimal thường phù hợp hơn floating point nhị phân vì tránh một số sai số biểu diễn.

### 4.3. Boolean

Boolean nên phân biệt rõ true và false. Không nên tự coi chuỗi "false" là false nếu DSL không định nghĩa coercion như vậy.

### 4.4. Kiểu có đơn vị

Một kiểu như Duration có thể cho phép:

~~~text
timeout = 30s
retryDelay = 500ms
~~~

Validator cần kiểm tra cú pháp đơn vị, giá trị âm, giới hạn và khả năng chuyển đổi. 30s và 30000ms có thể tương đương về giá trị nhưng vẫn cần chuẩn hóa về một representation thống nhất.

### 4.5. Kiểu miền

Kiểu miền đóng gói quy tắc của một khái niệm:

~~~text
type Port = Integer where value >= 1 and value <= 65535
type EmailAddress = String where matches(EMAIL_PATTERN)
~~~

Kiểu miền giúp tái sử dụng validation và làm schema diễn đạt rõ ý nghĩa hơn kiểu primitive chung.

## 5. Required, optional và nullable

Ba khái niệm này cần được phân biệt.

- **Required:** thuộc tính phải xuất hiện.
- **Optional:** thuộc tính có thể không xuất hiện.
- **Nullable:** thuộc tính có thể xuất hiện với giá trị null.

Ví dụ:

~~~text
schema User {
    id: String required
    nickname: String optional
    middleName: String nullable
}
~~~

Ngữ nghĩa cụ thể của optional và nullable phụ thuộc DSL. Có thể có trường vừa optional vừa nullable.

### 5.1. Absent khác null

Trong cấu hình dạng object:

~~~json
{}
~~~

không có thuộc tính middleName.

~~~json
{ "middleName": null }
~~~

có thuộc tính nhưng giá trị null.

Validator cần biết schema cho phép trường hợp nào. Default thường được áp dụng khi field absent; có thể không áp dụng khi field explicit null.

### 5.2. Required có default

Một trường có default có thể không cần xuất hiện trong source:

~~~text
enabled: Boolean default(true)
~~~

Sau khi áp dụng default, validated model có thể chứa enabled bằng true dù source không khai báo.

Tuy nhiên, schema phải định nghĩa default có được materialize vào output hay chỉ là giá trị ngầm định khi đọc.

### 5.3. Optional field trong API

Với cấu hình được truyền qua API, absent có thể nghĩa là giữ giá trị hiện tại, còn null có thể nghĩa là xóa giá trị. Hai trạng thái có tác động khác nhau và không nên bị gộp nếu API dựa vào chúng.

## 6. Object và nested schema

Schema thường mô tả object gồm nhiều thuộc tính.

~~~text
schema Database {
    name: String required
    engine: String required
    storage: StorageConfig required
}

schema StorageConfig {
    size: Size required
    encrypted: Boolean default(true)
}
~~~

Cấu hình:

~~~text
database "orders" {
    engine = "postgres"
    storage {
        size = 100GB
    }
}
~~~

Validator cần đi sâu vào object lồng nhau và gắn lỗi vào đúng vị trí của thuộc tính sai.

### 6.1. Nested object

Nested object giúp nhóm các thuộc tính có quan hệ:

~~~text
service "api" {
    resources {
        cpu = 2
        memory = 4GB
    }
}
~~~

Schema có thể yêu cầu resources là object có cpu và memory, mỗi trường có kiểu và constraint riêng.

### 6.2. List

~~~text
ports = [8080, 8443]
~~~

Schema có thể quy định:

~~~text
ports: List<Port> minItems(1) uniqueItems
~~~

Validator kiểm tra từng phần tử, số lượng và tính duy nhất.

### 6.3. Map

~~~text
labels = {
    team = "platform"
    environment = "production"
}
~~~

Schema có thể quy định key là String và value cũng là String, hoặc có pattern cho key.

### 6.4. Tuple

Tuple có số phần tử và kiểu theo vị trí:

~~~text
coordinates: Tuple<Decimal, Decimal>
~~~

Khác với list đồng nhất, tuple có thể yêu cầu phần tử thứ nhất và thứ hai mang kiểu hoặc ý nghĩa khác nhau.

## 7. Enum và tập giá trị cho phép

Enum giới hạn một thuộc tính vào các giá trị đã biết.

~~~text
enum Environment {
    DEVELOPMENT
    STAGING
    PRODUCTION
}

schema Deployment {
    environment: Environment required
}
~~~

Cấu hình:

~~~text
environment = PRODUCTION
~~~

Giá trị TESTING sẽ không hợp lệ nếu enum chưa định nghĩa thành viên đó.

### 7.1. Enum dạng string

Một DSL có thể cho phép:

~~~text
environment = "production"
~~~

Schema phải xác định casing, alias và quy tắc phân biệt chữ hoa/thường.

### 7.2. Unknown enum value

Với dữ liệu đến từ hệ thống khác, có thể gặp giá trị enum mới hơn. Validator cần policy: reject, giữ raw value, ánh xạ sang UNKNOWN hoặc cảnh báo. Chọn cách nào phụ thuộc yêu cầu an toàn và khả năng tương thích.

### 7.3. Enum có metadata

Enum member có thể có mô tả, alias hoặc trạng thái deprecated:

~~~text
enum Environment {
    DEVELOPMENT
    STAGING
    PRODUCTION
    @deprecated("Use STAGING")
    PRE_RELEASE
}
~~~

Metadata này có thể hỗ trợ validation, completion và documentation.

## 8. Constraints

Constraint là điều kiện bổ sung mà giá trị phải thỏa ngoài kiểu dữ liệu.

### 8.1. Minimum và maximum

~~~text
replicas: Integer min(1) max(100)
~~~

Validator kiểm tra giá trị nằm trong khoảng cho phép.

### 8.2. Length

~~~text
name: String minLength(1) maxLength(64)
~~~

Length có thể được tính theo code point, grapheme cluster hoặc đơn vị khác. DSL nên quy định rõ nếu giới hạn này quan trọng với Unicode.

### 8.3. Pattern

~~~text
resourceName: String pattern("^[a-z][a-z0-9-]*$")
~~~

Pattern thường dùng regular expression. Cần quy định regex dialect, xử lý Unicode và giới hạn độ phức tạp để tránh biểu thức gây backtracking quá mức.

### 8.4. Format

~~~text
endpoint: URL
email: EmailAddress
createdAt: Timestamp
~~~

Format validator kiểm tra hình dạng dữ liệu. Một URL hợp lệ về cú pháp chưa chắc endpoint có thể truy cập; đó là một loại kiểm tra khác.

### 8.5. Unique

~~~text
ports: List<Port> uniqueItems
~~~

Constraint unique yêu cầu các phần tử không trùng theo quy tắc equality đã định nghĩa.

### 8.6. Multiple-of

~~~text
memory: Size multipleOf(256MB)
~~~

Constraint này có thể yêu cầu dung lượng là bội số của đơn vị cấp phát.

### 8.7. Allowed và forbidden values

~~~text
region: String allowed("asia-east1", "asia-southeast1")
~~~

Có thể dùng forbidden hoặc not để loại trừ một tập giá trị. Cần tránh để constraint phủ định chồng chéo khó hiểu.

## 9. Default values

Default là giá trị được dùng khi người viết không cung cấp thuộc tính theo quy tắc schema.

~~~text
schema Service {
    replicas: Integer default(1)
    enabled: Boolean default(true)
    restartPolicy: String default("on-failure")
}
~~~

### 9.1. Khi áp dụng default

Default có thể được áp dụng khi parse object, trong bước schema normalization, khi tạo validated model hoặc khi runtime đọc cấu hình. Thời điểm áp dụng cần nhất quán vì nó ảnh hưởng diagnostics, serialization và cách phân biệt source với giá trị hiệu lực.

### 9.2. Default tĩnh và default động

Default tĩnh là giá trị cố định như 1 hoặc true. Default động có thể phụ thuộc môi trường hoặc biến khác.

~~~text
region: Region default(environment.defaultRegion)
~~~

Default động cần được kiểm soát dependency và thời điểm đánh giá. Nếu nó phụ thuộc network hoặc secret store, validation có thể cần phân biệt phần tĩnh với preflight.

### 9.3. Default không thay thế constraint

Nếu default của replicas là 0 nhưng constraint yêu cầu tối thiểu 1, schema tự mâu thuẫn. Schema compiler nên phát hiện lỗi thiết kế này.

### 9.4. Hiển thị giá trị hiệu lực

CLI có thể cung cấp lệnh inspect để hiển thị cấu hình sau khi áp dụng default:

~~~bash
dsl config show --effective project.dslproj
~~~

Nên phân biệt giá trị được viết trong source với giá trị được suy ra từ default.

## 10. Unknown fields và strictness

Khi cấu hình chứa một thuộc tính không có trong schema, validator cần policy rõ ràng.

~~~text
service "catalog" {
    replica = 3
}
~~~

Nếu schema dùng replicas, thuộc tính replica có thể là lỗi đánh máy.

### 10.1. Strict mode

Trong strict mode, unknown field thường là error:

~~~bash
dsl check --strict project.dslproj
~~~

### 10.2. Permissive mode

Trong một số DSL mở rộng, unknown field có thể được giữ lại hoặc bỏ qua để hỗ trợ plugin. Tuy nhiên, bỏ qua âm thầm dễ che lỗi chính tả.

### 10.3. Extension namespace

Một cách cân bằng là yêu cầu trường mở rộng có namespace rõ:

~~~text
service "catalog" {
    replicas = 3
    x-monitoring.scrape = true
}
~~~

Schema có thể cho phép prefix x- hoặc namespace plugin đã đăng ký, trong khi vẫn reject typo ở thuộc tính chuẩn.

### 10.4. Gợi ý tên gần đúng

Nếu gặp replica, validator có thể gợi ý replicas khi độ tương đồng cao. Gợi ý không nên tự sửa dữ liệu nếu người dùng chưa yêu cầu.

## 11. Reference và quan hệ giữa resource

Một cấu hình thường định nghĩa nhiều resource liên kết với nhau.

~~~text
network "private" {
    cidr = "10.0.0.0/16"
}

service "catalog" {
    network = ref("private")
}
~~~

Validator cần kiểm tra resource được tham chiếu có tồn tại, có đúng loại, nằm trong scope nhìn thấy được, có quyền tham chiếu nếu DSL có access control và không tạo vòng phụ thuộc bị cấm.

### 11.1. Name resolution

Tên tham chiếu có thể là tên cục bộ, qualified name hoặc symbol được import. Validator nên dùng cùng cơ chế name resolution với các phần khác của compiler.

### 11.2. Type-safe reference

Nếu thuộc tính yêu cầu Network, tham chiếu đến Database phải bị từ chối dù resource đó tồn tại.

### 11.3. Dependency graph

Các reference có thể tạo đồ thị phụ thuộc:

~~~text
service.catalog ---> network.private
service.catalog ---> secret.api-key
database.orders ---> network.private
~~~

Đồ thị giúp phát hiện tham chiếu thiếu, chu trình và thứ tự tạo resource.

### 11.4. Circular reference

Một số quan hệ vòng có thể hợp lệ, nhưng nhiều DSL không cho phép resource phụ thuộc trực tiếp hoặc gián tiếp vào chính nó. Validator cần xác định loại cạnh nào được phép tạo chu trình.

## 12. Cross-field validation

Một thuộc tính có thể hợp lệ khi đứng riêng nhưng không hợp lệ trong tổ hợp với thuộc tính khác.

Ví dụ:

~~~text
database "orders" {
    encryption = true
    encryptionKey = "secret.orders"
}
~~~

Quy tắc có thể yêu cầu encryptionKey khi encryption bằng true.

### 12.1. Required-if

~~~text
if tls == true then certificate is required
~~~

### 12.2. Mutually exclusive

~~~text
exactlyOne(publicEndpoint, privateEndpoint)
~~~

Hoặc:

~~~text
notBoth(manualAddress, automaticAddress)
~~~

### 12.3. Dependent range

Ví dụ maxReplicas phải lớn hơn hoặc bằng minReplicas.

~~~text
scaling {
    minReplicas = 2
    maxReplicas = 10
}
~~~

### 12.4. Validation ở cấp object

Một object validator có thể nhận toàn bộ object thay vì chỉ một giá trị:

~~~text
validateScaling(config):
    require config.minReplicas >= 1
    require config.maxReplicas >= config.minReplicas
~~~

Diagnostics nên gắn với trường gây lỗi hoặc với cả hai trường liên quan.

## 13. Domain validation

Domain validation kiểm tra quy tắc đặc thù của miền mà kiểu và constraint tổng quát không diễn tả đủ.

Ví dụ trong DSL triển khai dịch vụ:

- Một region không hỗ trợ loại instance được chọn.
- Replicas vượt quota của subscription.
- Một storage class không hỗ trợ encryption mode.
- Hai resource yêu cầu cùng một địa chỉ IP.
- Một policy không cho phép public endpoint ở production.

### 13.1. Tách quy tắc tĩnh và quy tắc môi trường

Quy tắc tĩnh có thể kiểm tra từ schema và project, chẳng hạn production không được bật debug. Quy tắc môi trường cần truy cập trạng thái bên ngoài, chẳng hạn quota còn lại.

Nên tách validation tĩnh khỏi preflight có network để lệnh check vẫn nhanh và có thể chạy offline.

### 13.2. Policy theo môi trường

~~~text
policy production {
    require encryption = true
    forbid publicEndpoint
    require replicas >= 2
}
~~~

Validator cần xác định environment nào đang được chọn và policy nào áp dụng.

### 13.3. Policy conflict

Nếu hai policy đưa ra yêu cầu mâu thuẫn, compiler hoặc policy engine nên phát lỗi cấu hình policy thay vì tùy tiện chọn một bên.

## 14. Schema composition và reuse

Schema lớn thường được xây dựng từ các phần nhỏ có thể tái sử dụng.

### 14.1. Reusable schema

~~~text
schema Metadata {
    labels: Map<String, String>
    annotations: Map<String, String>
}

schema Service {
    metadata: Metadata
    replicas: Integer min(1)
}
~~~

### 14.2. Composition

Một schema có thể kết hợp nhiều schema:

~~~text
schema Deployable = Metadata + NetworkConfig + ResourceLimits
~~~

Phép composition cần quy định xử lý field trùng tên, constraint xung đột và default khác nhau.

### 14.3. Inheritance

Một DSL có thể hỗ trợ schema kế thừa:

~~~text
schema BaseService {
    name: String required
    replicas: Integer default(1)
}

schema WebService extends BaseService {
    port: Port required
}
~~~

Khi kế thừa, cần quy định subclass có được nới lỏng constraint của base hay không. Thường schema con không nên làm mất những bảo đảm mà consumer của schema cha dựa vào.

### 14.4. Union và discriminated union

Một thuộc tính có thể nhận một trong nhiều cấu trúc:

~~~text
storage =
    LocalStorage { path = "/data" }
  | CloudStorage { bucket = "catalog-data" }
~~~

Discriminator như kind bằng local giúp validator xác định nhánh schema áp dụng.

### 14.5. Composition conflict

Nếu hai schema cùng khai báo timeout nhưng kiểu hoặc default khác nhau, cần báo conflict hoặc yêu cầu override tường minh. Không nên âm thầm dùng định nghĩa được nạp sau cùng.

## 15. Schema và JSON Schema

JSON Schema là định dạng phổ biến để mô tả và kiểm tra dữ liệu JSON. Một DSL cấu hình có thể dùng schema nội bộ rồi sinh JSON Schema để tích hợp với editor hoặc công cụ khác.

Ví dụ JSON Schema:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["name", "replicas"],
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1
    },
    "replicas": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100
    },
    "enabled": {
      "type": "boolean",
      "default": true
    }
  },
  "additionalProperties": false
}
~~~

### 15.1. Ánh xạ DSL schema sang JSON Schema

Các khái niệm như object, required, type, enum, minimum và pattern thường có thể ánh xạ tương đối trực tiếp.

Một số quy tắc miền phức tạp như tham chiếu resource, kiểm tra quota hoặc truy vấn môi trường có thể không biểu diễn đầy đủ trong JSON Schema. Khi đó cần validator riêng.

### 15.2. Schema dialect

JSON Schema có nhiều dialect/version. Generator cần khai báo dialect đích và chỉ sinh keyword được hỗ trợ.

### 15.3. additionalProperties

Thiết lập này kiểm soát thuộc tính không được khai báo. false giúp phát hiện typo; schema mở có thể cho phép extension. Lựa chọn phụ thuộc thiết kế DSL.

### 15.4. Default trong JSON Schema

Keyword default chủ yếu mô tả metadata; validator không nhất thiết tự điền giá trị. Nếu DSL cần materialize default, phải có bước normalization riêng.

## 16. Validation pipeline trong compiler

Một pipeline điển hình:

~~~text
Source files
    |
    v
Lexing and parsing
    |
    v
AST construction
    |
    v
Schema loading and resolution
    |
    v
Name and reference resolution
    |
    v
Type checking
    |
    v
Constraint validation
    |
    v
Cross-resource and domain validation
    |
    v
Normalized validated model
    |
    v
Code generation / execution
~~~

### 16.1. Load schema

Schema có thể được tích hợp sẵn, import từ module hoặc tải từ package. Cần resolve version và dependency trước khi validation.

### 16.2. Build model

Parser tạo AST. Compiler có thể chuyển AST sang một model có kiểu rõ ràng để validator xử lý.

### 16.3. Resolve references

Tên resource và symbol được phân giải thành identity cụ thể. Bước này cần thông tin về scope, module và visibility.

### 16.4. Type check

Kiểm tra giá trị và expression có phù hợp kiểu thuộc tính. Có thể có type inference hoặc coercion nếu DSL cho phép.

### 16.5. Constraints và domain rules

Chạy các predicate, cross-field rules và policy.

### 16.6. Normalization

Áp dụng default, chuẩn hóa đơn vị, canonicalize tên hoặc tạo representation thống nhất. Cần giữ source provenance để diagnostics và tooling biết giá trị nào do người dùng viết, giá trị nào được sinh.

### 16.7. Tạo validated model

Chỉ khi các lỗi nghiêm trọng đã được xử lý, compiler mới tạo model được đánh dấu validated để các giai đoạn sau sử dụng. Không nên để code generator nhận object nửa hợp lệ mà không biết trạng thái.

## 17. Diagnostics của validation

Một validator hữu ích cần chỉ rõ điều gì sai, ở đâu, vì sao sai và cách sửa.

~~~text
service.dsl:4:16: error DSL-SCHEMA-0012:
replicas must be at least 1; found 0

  replicas = 0
              ^
Hint: set replicas to a positive integer.
~~~

### 17.1. Thành phần của diagnostic

Một diagnostic có thể gồm:

- Code ổn định.
- Severity.
- Message.
- Source range.
- Related locations.
- Hint hoặc documentation link.
- Data bổ sung cho code action.

### 17.2. Severity

Thông thường:

- Error: cấu hình không thể được chấp nhận.
- Warning: cấu hình có thể chạy nhưng có rủi ro hoặc dùng tính năng deprecated.
- Information: thông tin hữu ích.
- Hint: gợi ý cải thiện.

### 17.3. Mã lỗi ổn định

Mã như DSL-SCHEMA-0012 giúp người dùng tìm tài liệu, lọc diagnostics và viết test. Không nên đổi mã tùy tiện nếu script hoặc editor phụ thuộc vào nó.

### 17.4. Source range

Validator nên gắn lỗi với trường hoặc giá trị liên quan. Nếu lỗi là quan hệ giữa hai trường, có thể dùng primary location và related location để chỉ cả hai.

### 17.5. Gợi ý sửa

Hint nên cụ thể và không giả định dữ liệu mà validator không biết. Gợi ý replicas lớn hơn hoặc bằng 1 là rõ; tự chọn giá trị 3 có thể không phù hợp nghiệp vụ.

### 17.6. Gom nhóm lỗi

Một lỗi có thể gây ra nhiều lỗi dây chuyền. Validator nên tránh phát hàng trăm diagnostics vô ích sau khi một schema hoặc reference gốc không resolve được.

## 18. Validation khi source chưa hoàn chỉnh

Trong editor, người dùng thường đang gõ dở. Validator cần phân biệt lỗi chắc chắn với lỗi tạm thời do source chưa hoàn chỉnh.

Ví dụ:

~~~text
service "catalog" {
    replicas =
}
~~~

Parser có thể tạo error node. Semantic analyzer không nên phát thêm nhiều lỗi kiểu giả định như replicas có unknown type nếu nguyên nhân là biểu thức chưa được nhập.

### 18.1. Error recovery

Parser có thể tạo AST một phần và tiếp tục phân tích các vùng khác. Validator nên bỏ qua hoặc giảm severity cho những kiểm tra phụ thuộc node lỗi.

### 18.2. Incomplete value

Nếu một trường đang có giá trị một phần, editor có thể hiển thị completion hoặc hint thay vì error cuối cùng.

### 18.3. Validation theo snapshot

Kết quả validation nên gắn với document/workspace version. Khi source thay đổi, diagnostics cũ cần được thay thế hoặc invalidated.

## 19. Validation ở CLI và IDE

Schema và validator có thể phục vụ cả command line và editor.

### 19.1. CLI validation

~~~bash
dsl check project.dslproj
~~~

CLI thường kiểm tra toàn project và trả exit code. Có thể hỗ trợ JSON hoặc SARIF cho CI.

### 19.2. IDE validation

IDE thường kiểm tra file đang mở theo incremental update. Diagnostics xuất hiện ngay khi người dùng gõ.

### 19.3. Dùng chung validation service

CLI và IDE nên dùng chung schema resolver, type checker và domain validator. Khác biệt chủ yếu nằm ở cách nhận input, thời điểm chạy và cách hiển thị kết quả.

### 19.4. Full validation và incremental validation

Full validation kiểm tra toàn bộ project. Incremental validation chỉ tính lại phần bị ảnh hưởng bởi thay đổi, dựa trên dependency graph và snapshot.

Kết quả incremental cần tương đương với full validation cho cùng source version.

## 20. Validation và external dependencies

Schema có thể phụ thuộc module hoặc package ngoài project.

~~~text
import cloud.compute.v2

service "catalog" {
    machineType = ComputeType.MEDIUM
}
~~~

Validator cần biết dependency đã được resolve chưa, version nào đang được sử dụng, schema package có tương thích với compiler không, symbol có được export không và package có đáng tin cậy theo policy không.

### 20.1. Lockfile

Lockfile giúp cố định version dependency để validation có kết quả tái hiện.

### 20.2. Offline validation

Nếu dependency đã được cache, validator có thể chạy offline. Nếu thiếu schema package, cần báo rõ thay vì âm thầm bỏ qua rule.

### 20.3. Remote schema

Nếu schema được tải từ remote registry, cần cache, version pinning, timeout và xác minh nguồn. Không nên tải lại schema không kiểm soát trong mỗi lần gõ hoặc mỗi lần validate.

## 21. Schema evolution và versioning

Schema thay đổi theo thời gian khi DSL thêm thuộc tính hoặc thay đổi quy tắc. Cần có chính sách tương thích.

### 21.1. Thêm optional field

~~~text
schema Service {
    name: String
    replicas: Integer
    description: String?
}
~~~

Thêm trường tùy chọn thường dễ tương thích nếu reader mới chấp nhận cấu hình cũ thiếu description.

### 21.2. Thêm required field

Thêm trường bắt buộc có thể khiến cấu hình cũ không hợp lệ. Cần default có ý nghĩa, migration hoặc giai đoạn chuyển tiếp.

### 21.3. Đổi tên field

Đổi tên field có thể tương đương xóa field cũ và thêm field mới đối với dữ liệu đã lưu. Có thể cần alias hoặc migration.

### 21.4. Đổi kiểu

Đổi kiểu cần kiểm tra dữ liệu hiện có, khả năng chuyển đổi và semantics. Parse được không có nghĩa là diễn giải đúng.

### 21.5. Deprecation

Một field có thể được đánh dấu deprecated trước khi xóa:

~~~text
@deprecated(since = "2.1", replacement = "replicas")
instanceCount: Integer
~~~

Validator có thể phát warning và tài liệu hóa thời điểm dự kiến loại bỏ.

### 21.6. Schema version

Có thể gắn version vào schema hoặc project:

~~~text
schema Service version 2 {
    name: String
    replicas: Integer default(1)
}
~~~

Compiler cần xác định schema version nào được hỗ trợ và cách nâng cấp dữ liệu cũ.

## 22. Schema migration và normalization

Migration chuyển dữ liệu từ schema cũ sang schema mới. Normalization chuyển dữ liệu hợp lệ sang representation chuẩn hóa.

### 22.1. Migration

Ví dụ đổi instanceCount thành replicas:

~~~text
migration Service_v1_to_v2 {
    rename instanceCount -> replicas
}
~~~

Migration cần xác định xử lý khi cả hai trường cùng tồn tại hoặc dữ liệu cũ thiếu trường.

### 22.2. Normalization

Ví dụ chuẩn hóa region về lowercase:

~~~text
region = "ASIA-SOUTHEAST1"
~~~

Validated model có thể lưu canonical value asia-southeast1 nếu DSL quy định case-insensitive. Cần giữ source mapping để editor vẫn trỏ được về giá trị gốc.

### 22.3. Validation trước và sau migration

Migration nên kiểm tra dữ liệu đầu vào theo schema cũ, chuyển đổi, rồi validate theo schema mới. Nếu có bản ghi không thể chuyển đổi, cần báo và có chính sách tiếp tục/dừng.

### 22.4. Không âm thầm sửa lỗi

Normalization không nên biến dữ liệu sai thành dữ liệu khác mà không có quy tắc được công bố. Tự động trim chuỗi hoặc đổi đơn vị có thể làm mất ý nghĩa nếu không được schema cho phép.

## 23. Validation và security

Configuration có thể điều khiển tài nguyên, quyền truy cập, network, secret và process. Validation là một lớp bảo vệ nhưng không thay thế authorization hoặc runtime security.

### 23.1. Path traversal

~~~text
output = "../../sensitive"
~~~

Nếu command chỉ được phép ghi trong project root, cần resolve canonical path và kiểm tra boundary trước khi ghi. Kiểm tra chuỗi ../ đơn giản có thể không đủ khi có symlink.

### 23.2. URL và network target

Kiểm tra URL syntax không đảm bảo endpoint an toàn. Nếu DSL cho phép gọi URL, cần policy về scheme, host, redirect và network boundary ở lớp thực thi.

### 23.3. Secret values

~~~text
apiKey: Secret required
~~~

Validator không nên in raw secret trong diagnostic, log hoặc normalized config output. Có thể hiển thị trạng thái đã khai báo/thiếu mà không tiết lộ giá trị.

### 23.4. Regex và expression constraints

Nếu schema cho phép biểu thức validation do người dùng cung cấp, cần giới hạn thời gian, độ phức tạp và quyền thực thi để tránh denial of service hoặc thực thi mã không mong muốn.

### 23.5. Resource limits

Schema validation cũng cần giới hạn kích thước file, độ sâu object, số lượng phần tử và độ dài chuỗi nếu dữ liệu đến từ nguồn không tin cậy.

## 24. Hiệu năng validation

Project lớn có thể có hàng nghìn resource và nhiều dependency. Validation cần hiệu quả mà vẫn giữ kết quả chính xác.

### 24.1. Validate theo tầng

Chạy các kiểm tra rẻ trước như syntax, field existence và primitive type. Những kiểm tra tốn kém như network preflight chỉ chạy khi cần hoặc theo command riêng.

### 24.2. Cache schema

Schema package đã resolve có thể được cache theo version và content hash.

### 24.3. Cache kết quả

Kết quả validation có thể được cache theo input hash, schema version, dependency graph và policy config. Cache key thiếu một dependency sẽ gây stale result.

### 24.4. Incremental validation

Khi một field thay đổi, chỉ những rule phụ thuộc vào field đó và các resource liên quan cần được tính lại. Cần theo dõi dependency giữa giá trị và validation rule.

### 24.5. Giới hạn diagnostics

Một lỗi gốc có thể gây ra nhiều lỗi dây chuyền. Có thể giới hạn số diagnostics, nhưng cần thông báo rằng kết quả đã bị cắt và không được coi là validation đầy đủ.

## 25. Kiểm thử schema và validator

Schema và validation cần được kiểm thử bằng cả dữ liệu hợp lệ và không hợp lệ.

### 25.1. Positive cases

~~~text
service "catalog" {
    replicas = 3
    enabled = true
}
~~~

Các cấu hình đúng schema phải được chấp nhận.

### 25.2. Negative cases

~~~text
service "catalog" {
    replicas = "three"
    unknownOption = true
}
~~~

Kiểm tra sai kiểu, thiếu trường, unknown field và constraint.

### 25.3. Boundary tests

Nếu replicas có range 1..100, cần thử:

- 0: dưới min.
- 1: đúng min.
- 100: đúng max.
- 101: vượt max.

### 25.4. Cross-field tests

Kiểm tra các tổ hợp field, không chỉ từng field riêng. Ví dụ TLS bật nhưng thiếu certificate; minReplicas lớn hơn maxReplicas.

### 25.5. Reference tests

Kiểm tra reference tồn tại, sai loại, không visible, bị cycle và dependency chưa resolve.

### 25.6. Property-based tests

Có thể sinh nhiều dữ liệu ngẫu nhiên theo schema và xác nhận validator chấp nhận dữ liệu hợp lệ, từ chối dữ liệu vi phạm invariant.

### 25.7. Snapshot diagnostics

Snapshot test có thể giữ output diagnostics để phát hiện thay đổi không chủ ý về message, code và source range. Khi cập nhật snapshot, cần hiểu thay đổi trước khi chấp nhận.

### 25.8. Compatibility tests

Kiểm tra schema version mới với các fixture cấu hình cũ để bảo đảm migration và backward compatibility theo policy.

## 26. Ví dụ tổng hợp: schema cho service

Giả sử DSL định nghĩa schema:

~~~text
enum Region {
    ASIA_SOUTHEAST1
    US_CENTRAL1
}

schema Resources {
    cpu: Decimal min(0.25) max(64)
    memory: Size min(256MB)
}

schema Service {
    name: String required pattern("^[a-z][a-z0-9-]*$")
    replicas: Integer default(1) min(1) max(50)
    region: Region required
    image: ImageReference required
    enabled: Boolean default(true)
    resources: Resources required
}
~~~

Cấu hình hợp lệ:

~~~text
service "catalog" {
    name = "catalog"
    replicas = 3
    region = ASIA_SOUTHEAST1
    image = "registry.example.com/catalog:v2"
    resources {
        cpu = 2
        memory = 4GB
    }
}
~~~

Cấu hình sai:

~~~text
service "Catalog API" {
    name = "Catalog API"
    replicas = 0
    region = MOON_BASE
    image = "not a valid image"
    resources {
        cpu = 0
        memory = 64MB
    }
}
~~~

Validator có thể phát hiện tên không khớp pattern, replicas nhỏ hơn minimum, enum region không tồn tại, image reference sai format, CPU nhỏ hơn minimum và memory nhỏ hơn minimum.

Nếu resources là object bắt buộc, việc thiếu block này cũng là lỗi. Sau validation, compiler có thể áp dụng default cho enabled và replicas nếu source không khai báo.

## 27. Ví dụ schema cho database

~~~text
enum DatabaseEngine {
    POSTGRES
    MYSQL
}

schema Database {
    engine: DatabaseEngine required
    version: String required
    storage: Size min(10GB) max(10TB)
    encrypted: Boolean default(true)
    backupRetentionDays: Integer min(1) max(365) default(7)
}

validate Database {
    if engine == MYSQL then version must be supportedMysqlVersion(version)
    if engine == POSTGRES then version must be supportedPostgresVersion(version)
    if environment == PRODUCTION then encrypted must be true
}
~~~

Ví dụ cấu hình:

~~~text
database "orders" {
    engine = POSTGRES
    version = "16"
    storage = 100GB
}
~~~

Schema validator kiểm tra kiểu và range. Domain validator kiểm tra version có được hỗ trợ và policy production có được tuân thủ. encrypted và backupRetentionDays có thể nhận default.

## 28. Kết quả validation và validated model

Một kiến trúc tốt có thể biểu diễn kết quả validation riêng với AST nguồn:

~~~text
ValidationResult {
    status: Valid | Invalid
    diagnostics: List<Diagnostic>
    model: Optional<ValidatedModel>
}
~~~

Khi không có error, ValidatedModel chứa giá trị đã resolve và chuẩn hóa. Ví dụ:

~~~text
Source:
    replicas = 3
    enabled omitted

Validated model:
    replicas = 3
    enabled = true
~~~

### 28.1. Provenance

Mỗi giá trị trong validated model có thể lưu nguồn gốc: được viết trực tiếp, lấy từ default, sinh bởi migration hay suy ra từ expression. Provenance giúp diagnostics và công cụ inspect giải thích vì sao giá trị hiệu lực có được.

### 28.2. Không dùng model invalid như model hợp lệ

Nếu validation thất bại, downstream stage cần biết trạng thái. Code generator không nên giả định mọi thuộc tính đã có giá trị hoặc mọi reference đã resolve.

### 28.3. Partial result

Editor có thể cần partial semantic model để tiếp tục completion và hover dù file có lỗi. Partial result cần được đánh dấu rõ, khác với validated model dùng cho execution.

## 29. Tích hợp schema với editor

Schema có thể cung cấp dữ liệu cho trải nghiệm soạn thảo:

- Completion đề xuất field hợp lệ trong context.
- Hover hiển thị type, default và description.
- Diagnostics báo field lạ hoặc giá trị sai.
- Go to definition mở nơi khai báo schema.
- Rename cập nhật reference theo symbol identity.
- Documentation generator tạo reference guide.

### 29.1. Completion theo schema

Trong một block service rỗng, editor có thể đề xuất name, replicas, region, image và resources, đồng thời loại bỏ field đã khai báo nếu schema không cho phép lặp.

### 29.2. Hover metadata

Hover trên replicas có thể hiển thị kiểu Integer, default 1, range 1..50 và mô tả.

### 29.3. Diagnostics nhất quán

IDE và CLI nên dùng chung validation code và error code để cùng một cấu hình không có kết quả mâu thuẫn.

## 30. Những sai lầm thường gặp

**Đồng nhất parsing với validation.** Một cấu trúc parse được vẫn có thể sai kiểu hoặc vi phạm rule.

**Chỉ kiểm tra kiểu primitive.** Cấu hình còn có constraint, reference, cross-field rule và semantics miền.

**Nhầm absent với null.** Hai trạng thái có thể có ý nghĩa khác nhau và ảnh hưởng default.

**Cho phép unknown field mà không policy rõ.** Điều này có thể che typo và làm cấu hình sai được chấp nhận.

**Áp dụng default không nhất quán.** CLI, IDE và runtime có thể diễn giải cùng cấu hình theo cách khác nhau.

**Dùng validation tĩnh để khẳng định trạng thái bên ngoài.** URL đúng format không có nghĩa service đang reachable hoặc người dùng có quyền.

**Không gắn diagnostic với source range.** Người dùng khó tìm đúng trường gây lỗi.

**Phát quá nhiều lỗi dây chuyền.** Một reference không resolve có thể tạo nhiều lỗi phụ không hữu ích.

**Tải schema từ xa không kiểm soát.** Build có thể chậm hoặc cho kết quả khác nhau theo thời điểm.

**Không quản lý schema version.** Cấu hình cũ có thể bị đọc bằng quy tắc mới mà không có migration.

**Tự sửa dữ liệu trong validation.** Việc thay đổi giá trị cần là normalization hoặc migration được định nghĩa riêng.

**Cho code generation dùng dữ liệu chưa validated mà không có trạng thái.** Backend có thể tạo artifact sai hoặc gặp lỗi khó hiểu.

## 31. Ghi nhớ

- Schema mô tả cấu trúc, kiểu, thuộc tính, default và constraint của dữ liệu cấu hình.
- Validation kiểm tra dữ liệu có tuân theo schema và quy tắc miền hay không.
- Parsing kiểm tra grammar; validation kiểm tra cấu trúc, kiểu, constraint, reference và semantics.
- Primitive type, domain type, collection, enum và nested object giúp mô hình hóa dữ liệu rõ ràng.
- Required, optional, nullable, absent và default cần có semantics tường minh.
- Constraint có thể kiểm tra range, length, pattern, format, uniqueness và allowed values.
- Cross-field và domain validation kiểm tra quan hệ giữa nhiều thuộc tính hoặc resource.
- Reference validation cần name resolution, visibility và dependency graph.
- Validation pipeline nên tách các bước tĩnh với preflight cần môi trường hoặc network.
- Diagnostics cần code ổn định, severity, message, source range và hint hữu ích.
- CLI và IDE nên dùng chung schema resolver và validation service.
- Schema versioning, migration và deprecation giúp cấu hình tiến hóa có kiểm soát.
- Validated model cần phân biệt với AST nguồn và partial model của editor.
- Validation là một lớp bảo vệ; security và authorization vẫn cần được kiểm tra ở nơi thực thi.

## 32. Câu hỏi tự kiểm tra

1. Schema là gì và nó đóng vai trò hợp đồng như thế nào trong DSL cấu hình?
2. Phân biệt schema, dữ liệu, grammar và validation.
3. Vì sao một chương trình có thể parse thành công nhưng validation thất bại?
4. Phân biệt syntax, structural, type, constraint, reference và domain validation.
5. Required, optional và nullable khác nhau như thế nào?
6. Absent và explicit null có thể ảnh hưởng default ra sao?
7. Nêu ví dụ về constraint range, pattern, uniqueness và allowed values.
8. Cross-field validation kiểm tra những quan hệ nào?
9. Vì sao reference validation cần symbol resolution và dependency graph?
10. Strict mode và permissive mode xử lý unknown fields khác nhau ra sao?
11. JSON Schema có thể biểu diễn loại rule nào và loại rule nào cần validator riêng?
12. Một validation pipeline điển hình gồm những bước nào?
13. Vì sao IDE cần partial validation khi source chưa hoàn chỉnh?
14. Làm thế nào để CLI và IDE cho kết quả validation nhất quán?
15. Schema migration và normalization khác nhau như thế nào?
16. Vì sao validator không nên tự ý sửa dữ liệu?
17. Những rủi ro bảo mật nào liên quan đến path, URL, secret và expression constraints?
18. Hãy thiết kế schema và cross-field rules cho một service có TLS, replicas, region và certificate.
