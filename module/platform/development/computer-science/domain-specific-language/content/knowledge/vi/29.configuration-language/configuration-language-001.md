# Khai báo cấu hình

Trong nhiều hệ thống phần mềm, hành vi của ứng dụng không chỉ được quyết định bởi mã nguồn. Nó còn phụ thuộc vào môi trường chạy, tài nguyên được cấp, kết nối dịch vụ, chính sách bảo mật, quy tắc nghiệp vụ và các tham số vận hành. **DSL cấu hình (Configuration Domain-Specific Language)** cung cấp một ngôn ngữ chuyên biệt để mô tả những thông tin đó theo cấu trúc rõ ràng.

Một phần quan trọng của DSL cấu hình là **khai báo cấu hình (configuration declaration)**: cách người viết khai báo một đối tượng, thuộc tính, tài nguyên, thành phần hoặc quy tắc cùng các giá trị và quan hệ của chúng. Khai báo giúp mô tả trạng thái mong muốn của hệ thống để công cụ có thể phân tích, kiểm tra, hợp nhất, triển khai hoặc chuyển thành định dạng mà nền tảng đích hiểu được.

Ví dụ, một DSL hạ tầng có thể mô tả dịch vụ:

~~~text
service "orders-api" {
    image = "example/orders:2.4"
    replicas = 3

    resources {
        cpu = "500m"
        memory = "512Mi"
    }

    network = network.backend
}
~~~

Khai báo này mô tả một service có tên, image, số replica, tài nguyên và network tham chiếu. Người viết tập trung vào trạng thái mong muốn. Công cụ DSL có thể kiểm tra kiểu, xác nhận network tồn tại, áp dụng mặc định, rồi sinh manifest cho nền tảng triển khai.

Khai báo cấu hình không chỉ là cú pháp gán giá trị. Một thiết kế tốt cần xác định tên nào hợp lệ, giá trị thuộc kiểu gì, thuộc tính nào bắt buộc, khối nào có thể lồng nhau, phạm vi của tham chiếu, cách xử lý giá trị mặc định và thứ tự ưu tiên khi có nhiều nguồn cấu hình.

## 1. Khai báo cấu hình là gì?

**Configuration declaration** là một cấu trúc trong DSL dùng để mô tả một thành phần cấu hình và các đặc tính của nó. Thành phần đó có thể là:

- Một ứng dụng hoặc service.
- Một database, network, queue hoặc storage.
- Một environment như development, staging hoặc production.
- Một rule hoặc policy.
- Một workflow hoặc task.
- Một schema, module hoặc package.
- Một nhóm tham số cho một thành phần khác.

Một khai báo thường có các phần:

1. Loại đối tượng hoặc từ khóa mở đầu.
2. Tên định danh nếu đối tượng cần được tham chiếu.
3. Thuộc tính và giá trị.
4. Các block con mô tả cấu trúc lồng nhau.
5. Tham chiếu tới những đối tượng khác.
6. Metadata hoặc annotation nếu DSL hỗ trợ.

Ví dụ:

~~~text
database "orders" {
    engine = "postgres"
    version = "16"
    storage = storage.ordersData
}
~~~

Ở đây, database là loại đối tượng, orders là tên, engine và version là thuộc tính, còn storage.ordersData là tham chiếu tới một khai báo khác.

### 1.1. Khai báo và gán giá trị

Trong nhiều DSL, cú pháp thuộc tính có dạng:

~~~text
replicas = 3
~~~

Nhìn giống phép gán trong ngôn ngữ lập trình, nhưng ý nghĩa thường là khai báo giá trị cấu hình trong một mô hình khai báo. Nó không nhất thiết là một câu lệnh thay đổi biến tại thời điểm thực thi.

Sự khác biệt này quan trọng:

- Phép gán trong ngôn ngữ mệnh lệnh có thể thay đổi trạng thái theo thứ tự chạy.
- Thuộc tính cấu hình mô tả giá trị mong muốn của một trường trong đối tượng.
- Công cụ có thể đọc toàn bộ khai báo, kiểm tra và quyết định cách áp dụng chúng.

### 1.2. Khai báo và định nghĩa

Một số DSL phân biệt declaration với definition:

- Declaration giới thiệu tên và loại thành phần.
- Definition cung cấp nội dung hoặc cấu hình đầy đủ.

Một DSL nhỏ có thể dùng cùng một cấu trúc cho cả hai. Nếu có tham chiếu trước khai báo, module hoặc khai báo từng phần, cần quy định rõ cách ghép declaration và definition.

## 2. Tư duy khai báo và tư duy mệnh lệnh

DSL cấu hình thường mang tính **declarative**: người viết mô tả hệ thống cần đạt trạng thái nào, còn công cụ quyết định cách tạo hoặc cập nhật trạng thái đó.

Ví dụ khai báo:

~~~text
service "catalog" {
    replicas = 4
}
~~~

Ví dụ mệnh lệnh:

~~~text
createService("catalog")
setReplicaCount("catalog", 4)
~~~

Hai cách có thể dẫn tới kết quả tương tự, nhưng mô hình xử lý khác nhau. Với khai báo, engine có thể so sánh trạng thái mong muốn với trạng thái hiện tại rồi tạo kế hoạch thay đổi. Với lệnh mệnh lệnh, thứ tự thực hiện các câu lệnh thường quyết định trực tiếp hành vi.

### 2.1. Desired state

Khai báo cấu hình thường mô tả **desired state**. Ví dụ, replicas = 4 có nghĩa service nên có bốn bản chạy. Nếu hiện tại chỉ có ba, hệ thống điều phối có thể tạo thêm một bản.

Desired state có thể được dùng theo nhiều cách:

- Sinh cấu hình cho hệ thống đích.
- Tạo kế hoạch thay đổi.
- So sánh cấu hình mong muốn với cấu hình hiện tại.
- Phát hiện drift.
- Đồng bộ trạng thái theo chu kỳ.

### 2.2. Idempotent application

Nếu engine áp dụng cùng một khai báo nhiều lần mà không tạo thêm tài nguyên trùng lặp ngoài ý muốn, thao tác có tính idempotent theo hợp đồng của engine.

Khai báo:

~~~text
queue "orders" {
    durable = true
}
~~~

Không nên được hiểu là cứ mỗi lần chạy lại sẽ tạo thêm một queue mới tên khác. Engine thường xác định tài nguyên theo identity và cập nhật trạng thái nếu cần.

### 2.3. Khi nào cần câu lệnh mệnh lệnh?

Một DSL cấu hình vẫn có thể chứa expression, function hoặc action. Tuy nhiên, cần xác định ranh giới giữa:

- Mô tả trạng thái.
- Tính toán giá trị cấu hình.
- Thực thi side effect.

Giữ khai báo cấu hình ít side effect giúp việc phân tích, review và tái lập kết quả dễ hơn.

## 3. Cấu trúc cơ bản của một khai báo

Một DSL có thể chọn cú pháp gần JSON, YAML, HCL hoặc thiết kế riêng. Ví dụ:

~~~text
service "payment-api" {
    replicas = 2
    public = false
    image = "payment:1.8"
}
~~~

Các thành phần:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Keyword | service | Xác định loại khai báo |
| Identifier | payment-api | Định danh đối tượng |
| Block | { ... } | Nhóm nội dung thuộc đối tượng |
| Attribute | replicas | Tên trường cấu hình |
| Expression | 2 | Giá trị hoặc biểu thức |
| Reference | network.backend | Liên kết tới đối tượng khác |

### 3.1. Keyword khai báo

Keyword cho biết loại đối tượng đang được định nghĩa. Ví dụ:

~~~text
service "api" { ... }
database "main" { ... }
network "private" { ... }
environment "production" { ... }
~~~

DSL cần xác định keyword nào được phép ở cấp module, cấp environment hoặc bên trong một block cụ thể.

### 3.2. Tên định danh

Tên thường dùng để tham chiếu tới khai báo từ nơi khác. Một DSL cần quy định:

- Ký tự hợp lệ.
- Phân biệt chữ hoa và chữ thường hay không.
- Có cho phép dấu gạch ngang không.
- Tên có duy nhất trong module hay trong toàn project.
- Có cho phép namespace.
- Có cho phép tên trùng ở scope khác.

Ví dụ:

~~~text
network "backend" { ... }
service "orders" {
    network = network.backend
}
~~~

Tên backend được dùng như identity của resource trong phạm vi thích hợp.

### 3.3. Thuộc tính

Attribute mô tả một trường đơn hoặc một giá trị có cấu trúc:

~~~text
replicas = 3
enabled = true
region = "ap-southeast-1"
~~~

Checker cần biết thuộc tính có được phép trong loại đối tượng hiện tại, kiểu dữ liệu nào được chấp nhận và giá trị có thỏa constraint không.

### 3.4. Block lồng nhau

Block nhóm những thuộc tính cùng thuộc một khái niệm:

~~~text
service "api" {
    resources {
        cpu = "500m"
        memory = "512Mi"
    }

    healthCheck {
        path = "/health"
        interval = 10s
    }
}
~~~

Block lồng nhau giúp mô hình phản ánh cấu trúc miền, nhưng cần giới hạn loại block, độ sâu và số lần xuất hiện nếu schema yêu cầu.

## 4. Các kiểu dữ liệu trong khai báo cấu hình

Giá trị cấu hình không chỉ là chuỗi. DSL nên có hệ kiểu rõ ràng để kiểm tra và chuyển đổi chính xác.

Các kiểu phổ biến:

| Kiểu | Ví dụ | Ý nghĩa |
|---|---|---|
| Boolean | true | Bật/tắt |
| Integer | 3 | Số nguyên |
| Decimal | 0.75 | Số thập phân |
| String | "production" | Văn bản |
| Duration | 30s, 5m | Khoảng thời gian |
| Size | 512Mi, 2Gi | Dung lượng |
| List | ["a", "b"] | Danh sách |
| Map | { key = "value" } | Ánh xạ khóa-giá trị |
| Object | Block có field | Đối tượng cấu trúc |
| Enum | "read-only" | Một giá trị trong tập hữu hạn |
| Reference | network.backend | Tham chiếu tới khai báo khác |
| Optional | null hoặc absent | Giá trị có thể không tồn tại |

### 4.1. Boolean

Boolean phù hợp với các tùy chọn bật/tắt:

~~~text
enabled = true
public = false
~~~

DSL cần quyết định có chấp nhận các dạng như yes/no hoặc 1/0 hay không. Hạn chế nhiều cách viết cho cùng một giá trị giúp cấu hình nhất quán.

### 4.2. Số nguyên và số thập phân

Số nguyên thường dùng cho số lượng, giới hạn hoặc cổng:

~~~text
replicas = 3
port = 8080
~~~

Số thập phân dùng cho tỷ lệ hoặc trọng số:

~~~text
trafficWeight = 0.25
~~~

Checker cần xác định range, overflow và cách làm tròn. Với tiền tệ hoặc giá trị cần độ chính xác thập phân, không nên mặc định dùng floating-point nhị phân.

### 4.3. String và escaping

Chuỗi có thể chứa dấu nháy, newline hoặc ký tự đặc biệt:

~~~text
description = "Public API for order management"
message = "Line one\nLine two"
~~~

Grammar cần định nghĩa escape sequence và encoding. Khi sinh cấu hình cho target, emitter phải encode lại literal theo quy tắc của định dạng đích.

### 4.4. Duration và size

Đơn vị tường minh giúp tránh nhầm lẫn:

~~~text
timeout = 30s
cacheTtl = 5m
memory = 512Mi
disk = 20Gi
~~~

Checker có thể xác nhận đơn vị được hỗ trợ, giá trị không âm và giới hạn hợp lý. Nếu cho phép số không có đơn vị, cần định nghĩa đơn vị mặc định rõ ràng.

### 4.5. List và map

List dùng khi thứ tự có ý nghĩa hoặc cần nhiều giá trị:

~~~text
allowedOrigins = [
    "https://app.example",
    "https://admin.example"
]
~~~

Map dùng khi cần ánh xạ:

~~~text
labels = {
    team = "commerce"
    tier = "backend"
}
~~~

DSL cần xác định map có bảo toàn thứ tự không, key có duy nhất không và cách xử lý key trùng.

### 4.6. Enum

Enum giới hạn giá trị hợp lệ:

~~~text
access = "read-only"
~~~

Nếu chỉ chấp nhận read-only, read-write và admin, checker có thể báo lỗi khi gặp giá trị khác. Enum giảm lỗi chính tả và làm tài liệu hóa rõ hơn.

### 4.7. Reference

Reference liên kết một khai báo với một đối tượng khác:

~~~text
network "backend" { ... }

service "api" {
    network = network.backend
}
~~~

Reference có kiểu riêng và cần được resolve. Không nên coi mọi chuỗi có cùng nội dung là tương đương với reference đã kiểm tra.

## 5. Schema của khai báo

**Schema** mô tả hình dạng và quy tắc hợp lệ của một loại khai báo. Nó định nghĩa thuộc tính, kiểu, block con, tính bắt buộc, giá trị mặc định và constraint.

Ví dụ schema khái niệm:

~~~yaml
type: Service
attributes:
  image:
    type: String
    required: true
  replicas:
    type: Integer
    required: false
    default: 1
    minimum: 1
    maximum: 100
  public:
    type: Boolean
    default: false
blocks:
  resources:
    required: false
    maxOccurrences: 1
    attributes:
      cpu:
        type: CpuQuantity
      memory:
        type: MemorySize
~~~

Schema giúp parser hoặc checker hiểu nội dung nào hợp lệ trong từng context.

### 5.1. Attribute được phép

Nếu khai báo service chứa thuộc tính unknown:

~~~text
service "api" {
    repilcas = 3
}
~~~

Checker có thể phát hiện repilcas không tồn tại và gợi ý replicas nếu khoảng cách tên đủ gần.

### 5.2. Required attribute

Một số field bắt buộc phải có:

~~~text
service "api" {
    replicas = 2
}
~~~

Nếu image là required, checker báo thiếu image. Cần phân biệt field bị thiếu với field có giá trị null; hai trường hợp có thể có semantics khác nhau.

### 5.3. Block cardinality

Schema có thể quy định block:

- Không bắt buộc.
- Bắt buộc đúng một lần.
- Có thể xuất hiện nhiều lần.
- Có số lần tối thiểu hoặc tối đa.

Ví dụ:

~~~text
service "api" {
    port {
        name = "http"
        number = 8080
    }

    port {
        name = "metrics"
        number = 9090
    }
}
~~~

Nếu schema cho phép nhiều port block, đây là cấu trúc hợp lệ. Nếu chỉ cho một block, checker cần báo duplicate block.

### 5.4. Schema có điều kiện

Một thuộc tính có thể bắt buộc khi một tùy chọn khác được bật:

~~~text
service "api" {
    tls = true
    certificate = secret.apiCertificate
}
~~~

Khi tls = true, certificate có thể là required. Khi tls = false, trường đó có thể không được phép hoặc không cần thiết. Đây là constraint liên thuộc tính, thường cần domain validation.

## 6. Giá trị mặc định

Giá trị mặc định (default) được dùng khi người viết không khai báo một thuộc tính tùy chọn. Nó giúp cấu hình ngắn hơn và cung cấp hành vi nhất quán.

Ví dụ:

~~~text
service "api" {
    image = "api:1.0"
}
~~~

Nếu schema quy định replicas mặc định là 1 và public mặc định là false, mô hình sau khi áp dụng default tương đương:

~~~text
service "api" {
    image = "api:1.0"
    replicas = 1
    public = false
}
~~~

### 6.1. Default trong schema và default theo môi trường

Có thể có nhiều nguồn mặc định:

- Default của ngôn ngữ hoặc schema.
- Default của module.
- Default của environment.
- Default do ứng dụng chủ cung cấp.

Phải quy định thứ tự ưu tiên và thời điểm áp dụng. Không nên để người dùng phải đoán giá trị cuối cùng được lấy từ đâu.

### 6.2. Default tĩnh và default tính toán

Default tĩnh:

~~~text
replicas = 1
~~~

Default tính toán có thể phụ thuộc môi trường:

~~~text
region = environment.defaultRegion
~~~

Default động cần quy định context và thời điểm đánh giá. Nếu giá trị thay đổi theo môi trường hoặc thời gian, kết quả cấu hình có thể không tái lập nếu không ghi lại context.

### 6.3. Không nhầm absent với null

Absent nghĩa là người viết không cung cấp field. Null là một giá trị được khai báo tường minh nếu DSL hỗ trợ null.

Ví dụ:

~~~text
description = null
~~~

Có thể có nghĩa xóa description hoặc đặt description thành rỗng, trong khi bỏ hẳn dòng description có thể làm dùng default. Schema cần định nghĩa khác biệt này.

### 6.4. Materialize default

Một số engine chỉ áp dụng default trong semantic model, không ghi ngược vào source. Một số công cụ có lệnh render để hiển thị cấu hình sau khi áp dụng default. Giữ source nguyên bản giúp phân biệt giá trị người dùng khai báo với giá trị được suy ra.

## 7. Khai báo bắt buộc, tùy chọn và giá trị rỗng

Một field có thể có các trạng thái:

- Được khai báo với giá trị hợp lệ.
- Không được khai báo.
- Được khai báo null.
- Được khai báo nhưng biểu thức không thể đánh giá.
- Được kế thừa từ nguồn cấu hình khác.

Ví dụ:

~~~text
service "api" {
    description = null
}
~~~

Checker cần phân biệt các trạng thái này khi áp dụng required/default và merge.

### 7.1. Optional field

Optional field có thể bỏ qua. Nếu không có default, semantic model có thể giữ trạng thái absent.

### 7.2. Required field

Required field phải có giá trị hợp lệ sau khi áp dụng các nguồn được phép. Nếu default hợp lệ được schema cung cấp, field có thể không cần xuất hiện trong source nhưng vẫn có giá trị trong cấu hình hiệu lực.

### 7.3. Nullable field

Nullable field cho phép giá trị null. Nullable không đồng nghĩa với optional: một field có thể bắt buộc xuất hiện nhưng giá trị được phép là null.

### 7.4. Empty collection

Danh sách rỗng và field absent có thể khác nhau:

~~~text
allowedOrigins = []
~~~

Có thể có nghĩa không cho phép origin nào. Bỏ field có thể dùng default, chẳng hạn danh sách origin mặc định. Checker và merge engine cần giữ được sự khác biệt.

## 8. Phạm vi và namespace của khai báo

Một DSL cần quy định nơi tên khai báo có hiệu lực và cách tham chiếu chúng.

Các phạm vi phổ biến:

- Toàn bộ project.
- Module hoặc package.
- Environment.
- Một block cha.
- Một document.
- Một local expression hoặc template.

Ví dụ:

~~~text
module commerce {
    network "backend" { ... }

    service "orders" {
        network = network.backend
    }
}
~~~

network.backend có thể được resolve trong module commerce.

### 8.1. Namespace

Namespace giúp tránh trùng tên:

~~~text
network "backend" { ... }
network "monitoring.backend" { ... }
~~~

Hoặc dùng tên đầy đủ:

~~~text
network = commerce.network.backend
~~~

DSL cần xác định separator, alias và cách xử lý tên mơ hồ.

### 8.2. Scope lồng nhau

Block con có thể kế thừa scope cha. Ví dụ một service trong environment production có thể nhìn thấy region mặc định của environment. Tuy nhiên, cần xác định rõ thuộc tính nào được kế thừa và thuộc tính nào phải tham chiếu tường minh.

### 8.3. Shadowing

Nếu scope con khai báo cùng tên với scope cha, DSL cần quyết định có cho phép shadowing không. Shadowing có thể tiện nhưng cũng gây nhầm lẫn khi giá trị cấu hình được kế thừa ngầm.

### 8.4. Visibility

Module có thể export một số khai báo và giữ những khai báo khác private. Checker cần kiểm tra quyền truy cập khi resolve reference, không chỉ kiểm tra tên có tồn tại.

## 9. Tham chiếu giữa các khai báo

Các khai báo cấu hình hiếm khi hoàn toàn độc lập. Service có thể tham chiếu network, database, secret, storage hoặc policy.

Ví dụ:

~~~text
secret "dbPassword" {
    source = vault("production/database/password")
}

database "orders" {
    engine = "postgres"
    password = secret.dbPassword
}

service "orders-api" {
    database = database.orders
}
~~~

Reference tạo quan hệ giữa các đối tượng. Checker có thể xác nhận:

- Đích tham chiếu tồn tại.
- Đích thuộc loại phù hợp.
- Đích có thể truy cập từ scope hiện tại.
- Version hoặc schema tương thích.
- Không có dependency cycle bị cấm.

### 9.1. Forward reference

Một khai báo có thể tham chiếu tới đối tượng xuất hiện sau trong file:

~~~text
service "api" {
    network = network.backend
}

network "backend" {
    cidr = "10.20.0.0/16"
}
~~~

Nếu DSL cho phép forward reference, parser chỉ tạo reference node và semantic analysis resolve sau khi thu thập declarations. Nếu DSL yêu cầu khai báo trước, checker cần báo tham chiếu xuất hiện quá sớm.

### 9.2. Dependency graph

Các reference có thể tạo đồ thị phụ thuộc. Engine có thể dùng đồ thị để:

- Xác định thứ tự tạo tài nguyên.
- Phát hiện cycle.
- Xác định thành phần cần cập nhật khi một khai báo đổi.
- Xây dựng kế hoạch triển khai.

### 9.3. Reference và literal string

Hai giá trị sau có thể khác semantics:

~~~text
network = network.backend
networkName = "backend"
~~~

Giá trị đầu là reference có thể resolve và kiểm tra kiểu. Giá trị thứ hai chỉ là chuỗi; engine không nên tự coi nó là reference nếu DSL không định nghĩa quy tắc chuyển đổi.

## 10. Biểu thức trong giá trị cấu hình

DSL có thể cho phép biểu thức để tính giá trị:

~~~text
replicas = baseReplicas + 2
memory = 256Mi * 2
region = environment.region
~~~

Cho phép expression giúp tái sử dụng và tránh lặp. Tuy nhiên, cần xác định:

- Những toán tử nào được phép.
- Có function call không.
- Biểu thức có được phép tạo side effect không.
- Giá trị được tính ở compile-time hay runtime.
- Có thể tham chiếu biến môi trường hoặc secret không.
- Cách xử lý lỗi đánh giá.

### 10.1. Constant expression

Biểu thức chỉ dùng literal và hằng có thể được tính tĩnh:

~~~text
workerCount = 2 * 4
~~~

Checker có thể suy ra 8 và kiểm tra range ngay.

### 10.2. Expression phụ thuộc environment

~~~text
region = environment.defaultRegion
~~~

Giá trị chỉ được biết khi chọn environment. Checker có thể kiểm tra type và reference tĩnh, sau đó evaluate trong context cụ thể.

### 10.3. Pure expression

Một lựa chọn thiết kế an toàn là chỉ cho phép biểu thức thuần trong khai báo. Pure expression không thay đổi trạng thái bên ngoài và cùng input cho cùng output. Điều này giúp checker, formatter, preview và plan engine đánh giá cấu hình mà không gây side effect.

### 10.4. Giới hạn expression

Nếu DSL cho phép gọi function tùy ý, việc kiểm tra cấu hình có thể vô tình chạy mã. Cần giới hạn function có thể gọi, timeout, memory và quyền truy cập. Không nên coi file cấu hình là dữ liệu vô hại chỉ vì nó có đuôi config hoặc dsl.

## 11. Thứ tự khai báo và thứ tự xử lý

Khai báo có thể xuất hiện theo thứ tự bất kỳ nếu quan hệ được resolve toàn cục. Nhưng thứ tự trong source vẫn có thể ảnh hưởng:

- Cách merge thuộc tính lặp.
- Thứ tự xử lý list.
- Thứ tự khai báo block.
- Độ ưu tiên override.
- Thứ tự sinh output.

Ví dụ:

~~~text
firewall "web" {
    allow "https"
    deny "all"
}
~~~

Nếu firewall rule được áp dụng theo thứ tự, việc đổi hai dòng có thể đổi semantics. Nếu DSL coi rules là tập không thứ tự, thứ tự source không được ảnh hưởng kết quả.

### 11.1. Attribute trùng

Ví dụ:

~~~text
service "api" {
    replicas = 2
    replicas = 4
}
~~~

DSL cần quyết định:

- Báo duplicate attribute.
- Cho phép giá trị cuối ghi đè.
- Hợp nhất theo một quy tắc cụ thể.

Với cấu hình quan trọng, báo lỗi duplicate thường dễ hiểu hơn vì tránh việc thứ tự vô tình quyết định giá trị.

### 11.2. Block lặp

Nhiều block cùng loại có thể là danh sách hợp lệ:

~~~text
service "api" {
    port {
        name = "http"
        number = 8080
    }
    port {
        name = "metrics"
        number = 9090
    }
}
~~~

Schema cần xác định block lặp được phép hay không và cách định danh từng phần tử.

### 11.3. Dependency order

Thứ tự tạo resource có thể khác thứ tự source. Nếu database phụ thuộc network, engine có thể tạo network trước dù khai báo database nằm trước trong file. Dependency graph là cơ sở tốt hơn cho scheduling.

## 12. Hợp nhất và ghi đè cấu hình

Trong thực tế, cấu hình có thể đến từ nhiều nguồn:

- Giá trị mặc định của schema.
- File cấu hình gốc.
- File theo environment.
- File local của developer.
- Environment variables.
- Tham số dòng lệnh.
- Cấu hình do ứng dụng chủ truyền vào.

Engine cần quy tắc precedence và merge rõ ràng.

Ví dụ:

~~~text
base configuration:
    replicas = 2
    logLevel = "info"

production override:
    replicas = 5
    logLevel = "warn"
~~~

Kết quả hiệu lực:

~~~text
replicas = 5
logLevel = "warn"
~~~

### 12.1. Precedence

Một thứ tự minh họa:

1. Schema defaults.
2. Base project configuration.
3. Environment-specific configuration.
4. Local override.
5. Environment variables.
6. Explicit CLI arguments.

Thứ tự thật phụ thuộc sản phẩm. Cần công bố rõ nguồn nào có ưu tiên cao hơn và có cho phép nguồn cấp thấp ghi đè nguồn policy bắt buộc hay không.

### 12.2. Merge object

Khi hai nguồn cùng khai báo object, engine có thể merge từng field:

~~~text
base:
    resources:
        cpu = "250m"
        memory = "256Mi"

override:
    resources:
        memory = "512Mi"
~~~

Kết quả có thể giữ cpu = 250m và đổi memory thành 512Mi. Đây là deep merge theo field.

### 12.3. Merge list

List có nhiều chính sách:

- Replace toàn bộ list.
- Append phần tử.
- Merge theo key của phần tử.
- Union và loại trùng.

Ví dụ, override allowedOrigins có thể thay toàn bộ danh sách hoặc thêm một origin. Không có một quy tắc đúng cho mọi kiểu list; schema nên định nghĩa merge strategy theo thuộc tính.

### 12.4. Xóa giá trị kế thừa

Một override có thể cần xóa field được khai báo ở base. Có thể dùng null, tombstone hoặc cú pháp unset. Phải phân biệt xóa giá trị, đặt null và bỏ field để dùng default.

### 12.5. Provenance của giá trị

Khi cấu hình cuối cùng được hợp nhất, công cụ có thể lưu nguồn của từng giá trị: default, file nào, dòng nào hoặc environment variable nào. Provenance giúp giải thích vì sao giá trị hiệu lực khác với source đang xem.

## 13. Environment và profile

Một ứng dụng có thể chạy trong nhiều môi trường với cùng cấu trúc nhưng khác tham số:

- development.
- test.
- staging.
- production.

DSL có thể định nghĩa profile:

~~~text
environment "development" {
    replicas = 1
    logLevel = "debug"
}

environment "production" {
    replicas = 4
    logLevel = "warn"
}
~~~

### 13.1. Base và override

Để tránh lặp, có thể khai báo base:

~~~text
service "api" {
    image = "api:2.0"
    port = 8080

    profile "development" {
        replicas = 1
    }

    profile "production" {
        replicas = 4
    }
}
~~~

Engine chọn profile tương ứng rồi áp dụng merge rules.

### 13.2. Profile không nên làm mơ hồ identity

Một service vẫn nên có identity ổn định giữa các profile. Profile thay đổi thuộc tính cấu hình, trừ khi DSL định nghĩa rõ việc tạo hoặc bỏ resource.

### 13.3. Kiểm tra mọi profile

CI có thể kiểm tra tất cả profile, không chỉ profile đang được deploy. Điều này giúp phát hiện cấu hình production bị lỗi dù developer thường chạy development.

### 13.4. Profile kế thừa

Profile có thể kế thừa profile cha. Cần phát hiện vòng lặp kế thừa và quy định field nào được merge, field nào phải override tường minh.

## 14. Environment variables và tham số bên ngoài

Một DSL có thể đọc environment variable để đưa cấu hình từ môi trường triển khai vào:

~~~text
port = env("PORT", default = 8080)
region = env("REGION")
~~~

### 14.1. Chuyển đổi kiểu

Environment variable thường là string. Checker hoặc runtime cần chuyển đổi theo kiểu mong đợi:

- "8080" thành Integer.
- "true" thành Boolean theo quy tắc parsing đã định.
- "30s" thành Duration.
- "512Mi" thành MemorySize.

Nếu chuyển đổi thất bại, diagnostics cần chỉ ra tên biến và kiểu mong đợi, không nhất thiết in giá trị nhạy cảm.

### 14.2. Required environment variable

Nếu biến REGION bắt buộc mà không tồn tại, cấu hình không thể hoàn tất. Checker có thể xác nhận tên biến được khai báo, nhưng chỉ runtime hoặc môi trường CI mới biết biến có thực sự được cung cấp.

### 14.3. Tính tái lập

Nếu cấu hình phụ thuộc environment variables, cần ghi lại tên biến và giá trị đã resolve trong metadata an toàn hoặc deployment record khi cần tái hiện. Không ghi secret vào log.

### 14.4. Tránh truy cập môi trường tùy tiện

Cho phép mọi expression đọc mọi environment variable có thể khiến cấu hình phụ thuộc máy đang chạy. Có thể yêu cầu khai báo danh sách biến được phép để tăng tính minh bạch và khả năng kiểm tra.

## 15. Secret và dữ liệu nhạy cảm

Secret như password, token và private key không nên được ghi trực tiếp vào file cấu hình được commit.

Ví dụ không nên:

~~~text
database "orders" {
    username = "app"
    password = "plain-text-password"
}
~~~

Thay vào đó, DSL có thể tham chiếu secret provider:

~~~text
database "orders" {
    username = "app"
    password = secret("production/orders/password")
}
~~~

### 15.1. Secret reference

Secret reference chỉ lưu định danh hoặc đường dẫn tới secret. Giá trị thật được resolve trong môi trường có quyền phù hợp.

### 15.2. Không in secret khi render

Lệnh hiển thị cấu hình hiệu lực cần redaction:

~~~text
database.password = ********
~~~

### 15.3. Kiểm tra quyền

Checker có thể xác nhận secret reference hợp lệ theo schema hoặc policy. Runtime/secret manager vẫn phải xác thực quyền truy cập thật.

### 15.4. Rotation

Nếu secret được rotate, resource có thể cần reload hoặc restart. DSL nên phân biệt secret được resolve khi khởi tạo với secret được đọc động mỗi lần sử dụng.

## 16. Validation của khai báo cấu hình

Validation xác nhận khai báo tuân thủ schema và quy tắc miền.

Các lớp kiểm tra:

1. Syntax validation: cấu trúc source hợp lệ.
2. Schema validation: field, block và kiểu hợp lệ.
3. Reference validation: tên và resource tham chiếu tồn tại.
4. Constraint validation: range, pattern và cardinality.
5. Cross-field validation: các thuộc tính tương thích với nhau.
6. Domain validation: quy tắc nghiệp vụ.
7. Environment validation: resource và capability có sẵn trong môi trường đích.

Ví dụ:

~~~text
service "api" {
    replicas = 0
    public = true
    authentication = "none"
    port = 70000
}
~~~

Checker có thể phát hiện:

- replicas phải lớn hơn 0.
- Service public phải bật authentication.
- Port nằm ngoài khoảng cho phép.

### 16.1. Validation tĩnh và validation phụ thuộc môi trường

Một số lỗi có thể phát hiện từ source:

- Sai kiểu.
- Thiếu field bắt buộc.
- Enum không hợp lệ.
- Dependency cycle.

Một số lỗi cần môi trường:

- Network có tồn tại trong cloud account không.
- Image có thể pull được không.
- Secret có được cấp quyền không.
- Quota thực tế còn đủ không.

Checker nên phân biệt invalid, valid và unknown/incomplete thay vì coi mọi thứ không kiểm tra được là hợp lệ.

### 16.2. Validation không nên tạo side effect

Lệnh check hoặc plan nên tránh tạo resource thật. Nếu cần gọi API để xác thực metadata, phải nêu rõ đây là truy vấn và cần giới hạn quyền. Tách validation khỏi apply giúp người dùng review an toàn hơn.

## 17. Khai báo và kế thừa cấu hình

Kế thừa cho phép một khai báo dùng lại cấu hình từ một mẫu hoặc đối tượng cha.

Ví dụ:

~~~text
template "small-service" {
    replicas = 1
    resources {
        cpu = "250m"
        memory = "256Mi"
    }
}

service "catalog" extends template.small-service {
    image = "catalog:3.1"
}
~~~

### 17.1. Kế thừa và composition

Kế thừa thường mô tả một khai báo dựa trên một khai báo khác. Composition ghép nhiều cấu phần:

~~~text
service "catalog" {
    use common.logging
    use common.healthChecks
    image = "catalog:3.1"
}
~~~

Composition có thể linh hoạt hơn nhưng cần quy tắc xử lý conflict khi hai cấu phần cùng khai báo một field.

### 17.2. Conflict resolution

Nếu template và service cùng đặt replicas, DSL cần quy định giá trị nào thắng. Có thể yêu cầu override tường minh:

~~~text
service "catalog" extends template.small-service {
    override replicas = 3
}
~~~

### 17.3. Inheritance cycle

Checker cần phát hiện template A kế thừa B, B kế thừa A. Kế thừa vòng lặp khiến cấu hình không thể được mở rộng theo thứ tự xác định.

### 17.4. Kế thừa có kiểm soát

Không phải mọi thuộc tính đều nên override. Một số field như security policy hoặc owner có thể bị khóa theo policy tổ chức. Schema có thể đánh dấu final, immutable hoặc restricted.

## 18. Module và tái sử dụng cấu hình

Module gom các khai báo liên quan thành một đơn vị có thể import hoặc version.

Ví dụ:

~~~text
module shared.networking {
    network "backend" {
        cidr = "10.20.0.0/16"
    }
}

module application.orders {
    import shared.networking

    service "api" {
        network = shared.networking.network.backend
    }
}
~~~

Module giúp:

- Chia cấu hình theo trách nhiệm.
- Tái sử dụng resource.
- Quản lý namespace.
- Kiểm soát dependency.
- Phát hành template hoặc module dùng chung.

### 18.1. Module input và output

Module có thể nhận input:

~~~text
module "service" {
    input name: String
    input image: String
    input replicas: Integer = 1

    service name {
        image = image
        replicas = replicas
    }
}
~~~

Module có thể export output hoặc reference để module khác sử dụng. Cần xác định kiểu, default, required và visibility của input/output.

### 18.2. Version module

Nếu module được phân phối qua registry, project nên pin version hoặc dùng lockfile. Thay đổi module có thể làm cấu hình hiệu lực đổi dù file source của ứng dụng không thay đổi.

## 19. Biến và tham số trong cấu hình

Để tránh lặp giá trị, DSL có thể cho phép khai báo biến:

~~~text
let defaultPort = 8080
let serviceName = "orders"

service serviceName {
    port = defaultPort
}
~~~

Biến cấu hình khác với attribute của resource:

- Variable cung cấp giá trị có thể tái sử dụng trong phạm vi.
- Attribute gắn giá trị vào một field của đối tượng.
- Input module là tham số do caller truyền vào.
- Output module là giá trị được export từ module.

### 19.1. Kiểu và scope

Biến nên có kiểu suy luận hoặc kiểu khai báo rõ. Scope cần được xác định để tránh tên toàn cục làm cấu hình khó hiểu.

### 19.2. Immutable configuration value

Biến cấu hình thường nên bất biến trong một lần evaluate. Điều này giúp cùng một biểu thức luôn dùng cùng giá trị và tránh phụ thuộc vào thứ tự thực thi.

### 19.3. Biến và secret

Không nên coi biến là cơ chế bảo vệ secret. Nếu biến giữ secret, metadata và output của checker/renderer cần đánh dấu sensitive để không in giá trị.

## 20. Annotation và metadata

Khai báo có thể chứa metadata phục vụ tài liệu hóa, owner, version hoặc công cụ khác:

~~~text
@owner("team-commerce")
@documentation("Public API for orders")
service "orders-api" {
    replicas = 3
}
~~~

Annotation có thể dùng cho:

- Ownership.
- Documentation.
- Deprecation.
- Versioning.
- Policy.
- Code generation.
- Tooling và dashboard.

### 20.1. Annotation không thay thế schema

Annotation bổ sung thông tin cho khai báo, nhưng không nên là cách duy nhất để xác định kiểu và tính hợp lệ của field. Schema vẫn cần định nghĩa cấu trúc cốt lõi.

### 20.2. Annotation có phạm vi

Một annotation có thể áp dụng cho module, resource, attribute hoặc block. DSL cần xác định vị trí hợp lệ và liệu annotation có được kế thừa hay không.

### 20.3. Annotation không được hiểu bởi tool

Nếu compiler hoặc checker không biết annotation, cần quy tắc rõ: từ chối, bỏ qua có warning hay giữ nguyên để tool khác xử lý. Bỏ qua âm thầm có thể làm mất policy quan trọng.

## 21. Comment và documentation

Comment giúp giải thích lý do của cấu hình:

~~~text
# Keep two replicas during the regional migration.
service "orders-api" {
    replicas = 2
}
~~~

Một số DSL hỗ trợ documentation block hoặc metadata có cấu trúc. Công cụ có thể trích xuất nội dung này vào tài liệu hoặc catalog.

Comment thường không ảnh hưởng semantics. Tuy nhiên, directive comment như suppression hoặc formatter instruction có thể ảnh hưởng hành vi tooling và cần được parse theo quy tắc riêng.

## 22. Render và biểu diễn cấu hình hiệu lực

Source cấu hình có thể chứa default, variable, reference, profile và override. **Rendered configuration** là mô hình sau khi resolve các yếu tố đó trong một context cụ thể.

Ví dụ source:

~~~text
let baseReplicas = 2

service "api" {
    replicas = baseReplicas
}
~~~

Sau evaluation:

~~~json
{
  "service": "api",
  "replicas": 2
}
~~~

### 22.1. Render theo environment

Cùng source có thể tạo output khác nhau theo profile:

~~~text
render --environment development
render --environment production
~~~

### 22.2. Render và provenance

Output hữu ích có thể chỉ ra:

| Field | Giá trị hiệu lực | Nguồn |
|---|---|---|
| replicas | 4 | production.dsl:12 |
| logLevel | warn | environment default |
| memory | 512Mi | service schema default |

Provenance giúp debug precedence và hiểu tại sao giá trị cuối cùng khác source gốc.

### 22.3. Redaction

Rendered configuration không nên tiết lộ secret. Có thể hiển thị reference, trạng thái đã resolve hoặc giá trị đã che.

### 22.4. Render không đồng nghĩa apply

Render chỉ tính hoặc serialize cấu hình. Apply có thể tạo hoặc cập nhật resource thật. Tách hai thao tác giúp review trước khi có side effect.

## 23. Diff, plan và drift detection

Khi có desired configuration và trạng thái hiện tại, engine có thể so sánh chúng.

### 23.1. Diff

Diff cho biết field nào thay đổi:

~~~text
service.orders-api:
    replicas: 2 -> 4
    memory: 256Mi -> 512Mi
~~~

### 23.2. Plan

Plan có thể phân loại hành động:

- Create resource.
- Update field.
- Replace resource.
- Delete resource.
- No change.

Plan giúp người dùng review tác động trước khi apply.

### 23.3. Drift

Drift là khác biệt giữa trạng thái mong muốn và trạng thái thực tế do thay đổi bên ngoài hoặc thao tác thủ công.

Checker hoặc plan engine có thể báo drift nhưng cần phân biệt:

- Source không hợp lệ.
- Cấu hình hiệu lực hợp lệ nhưng khác trạng thái hiện tại.
- Không đủ quyền hoặc dữ liệu để quan sát trạng thái.

Drift detection thường cần kết nối môi trường và có thể chỉ đọc. Nó không nên tự sửa trạng thái nếu người dùng chưa yêu cầu apply hoặc reconciliation.

## 24. Sinh cấu hình cho nền tảng đích

DSL cấu hình thường là lớp trừu tượng trên một hoặc nhiều định dạng đích.

Ví dụ source:

~~~text
service "web" {
    image = "web:2.0"
    replicas = 3
    port = 8080
}
~~~

Công cụ có thể sinh JSON/YAML hoặc manifest nền tảng. Pipeline:

~~~mermaid
flowchart TD
    A[Configuration DSL] --> B[Parse]
    B --> C[Typed configuration model]
    C --> D[Apply defaults and overrides]
    D --> E[Validate references and policies]
    E --> F[Target model]
    F --> G[Serializer / generator]
    G --> H[Target configuration]
~~~

### 24.1. Target model

Không nên sinh chuỗi YAML trực tiếp từ token nếu DSL có schema và reference. Một mô hình typed trung gian giúp xác nhận giá trị trước khi serialize.

### 24.2. Serializer

Serializer cần:

- Encode string đúng định dạng.
- Giữ kiểu số và boolean.
- Xử lý null và absent theo semantics.
- Sắp xếp output ổn định nếu cần.
- Không làm mất dữ liệu hoặc precision.
- Xử lý escaping và Unicode.

### 24.3. Nhiều target

Một DSL có thể sinh Kubernetes manifest, Terraform-like model hoặc cấu hình ứng dụng riêng. Mỗi backend cần công bố capability và giới hạn. Không phải mọi khái niệm DSL đều có biểu diễn tương đương ở mọi nền tảng.

## 25. Versioning của schema và cấu hình

Schema và ngôn ngữ cấu hình thay đổi theo thời gian. Một field có thể được thêm, đổi kiểu, deprecated hoặc bị loại bỏ.

Ví dụ:

~~~text
configurationVersion = 2
~~~

### 25.1. Schema version

Version schema cho biết cách diễn giải field và constraint. Checker cần chọn đúng schema dựa trên manifest hoặc declaration version.

### 25.2. Deprecated field

Khi field cũ còn được hỗ trợ nhưng không nên dùng nữa, checker có thể tạo warning và gợi ý field thay thế.

### 25.3. Migration

Migration tool có thể chuyển cấu hình cũ sang cấu trúc mới. Cần giữ semantics, đặc biệt khi default hoặc merge behavior thay đổi.

### 25.4. Forward compatibility

Khi gặp field chưa biết, DSL có thể:

- Báo lỗi nghiêm ngặt.
- Cho phép extension namespace.
- Giữ metadata cho tool khác.

Không nên bỏ qua field lạ nếu nó có thể ảnh hưởng bảo mật hoặc hành vi triển khai.

## 26. Bảo mật trong khai báo cấu hình

File cấu hình có thể dẫn tới việc tạo resource, cấp quyền hoặc thực thi hành động. Vì vậy, khai báo cần được kiểm tra như đầu vào có ảnh hưởng tới hệ thống.

Các nguyên tắc:

- Không hardcode secret.
- Giới hạn capability và quyền.
- Xác thực URI, path và resource reference.
- Dùng allowlist cho image, package hoặc endpoint khi cần.
- Không thực thi expression tùy ý trong lúc chỉ kiểm tra.
- Phân biệt render, plan và apply.
- Ghi audit cho thay đổi có tác động.
- Redact dữ liệu nhạy cảm trong diagnostics và log.

### 26.1. Cấu hình có thể thực thi mã

Một DSL có function call hoặc plugin có thể tạo side effect. Checker cần xác định lệnh nào thuần và lệnh nào có thể truy cập môi trường. Lệnh validate không nên vô tình chạy hành động tạo hoặc xóa resource.

### 26.2. Path traversal

Nếu cấu hình tham chiếu file:

~~~text
template = file("../../secrets/private.key")
~~~

Engine cần kiểm tra path sau khi canonicalize, symlink và workspace boundary. Chỉ kiểm tra chuỗi có chứa hai dấu chấm liên tiếp là chưa đủ.

### 26.3. Supply chain

Nếu khai báo package hoặc module từ registry, cần pin version, kiểm tra checksum hoặc chữ ký theo policy và ghi lại dependency đã resolve.

## 27. Diagnostics cho khai báo cấu hình

Một checker cần chỉ ra lỗi bằng ngôn ngữ gần với mô hình cấu hình.

Ví dụ unknown attribute:

~~~text
service "api" {
    repilcas = 3
}
~~~

Diagnostic:

~~~text
services/api.dsl:2:5
error CFG101: Unknown attribute 'repilcas' in Service.
Did you mean 'replicas'?
~~~

Ví dụ missing required field:

~~~text
services/api.dsl:1:1
error CFG110: Required attribute 'image' is missing.
~~~

Ví dụ invalid reference:

~~~text
services/api.dsl:4:15
error CFG203: Network 'backend' was not found in module 'application'.
~~~

Ví dụ deprecated field:

~~~text
services/api.dsl:7:5
warning CFG310: Attribute 'legacyPort' is deprecated.
Use 'port' instead.
~~~

Diagnostics nên có:

- Rule ID ổn định.
- Severity.
- Source range.
- Loại khai báo và tên đối tượng liên quan.
- Giá trị hiện tại nếu an toàn để hiển thị.
- Gợi ý sửa khi có căn cứ.
- Related location cho declaration hoặc schema liên quan.

## 28. Kiểm thử khai báo cấu hình

Khai báo cấu hình cần được kiểm thử ở nhiều lớp.

### 28.1. Parser tests

- Khai báo đơn giản.
- Block lồng nhau.
- String escaping.
- List và map.
- Reference syntax.
- Comment và annotation.

### 28.2. Schema tests

- Field hợp lệ.
- Field không tồn tại.
- Field bắt buộc bị thiếu.
- Sai kiểu.
- Giá trị ngoài range.
- Block xuất hiện quá số lần.

### 28.3. Resolution tests

- Reference hợp lệ.
- Reference không tồn tại.
- Reference sai loại.
- Namespace mơ hồ.
- Forward reference theo chính sách.
- Dependency cycle.

### 28.4. Default và merge tests

- Default được áp dụng đúng.
- Explicit value ghi đè default.
- Absent khác null.
- Deep merge object.
- List replace/append/merge theo schema.
- Precedence giữa base, profile và environment.

### 28.5. Environment tests

- Profile hợp lệ.
- Thiếu environment variable bắt buộc.
- Chuyển kiểu thất bại.
- Secret được redact.
- Cấu hình có thể tái lập với cùng context.

### 28.6. Serialization tests

- Output parse được bởi target.
- Unicode và escaping đúng.
- Kiểu dữ liệu không bị đổi.
- Output ổn định.
- Không rò rỉ secret.

### 28.7. Integration tests

Chạy toàn bộ pipeline từ DSL source qua validation, render và target parser. Test cũng cần xác nhận lệnh check/render không tạo side effect ngoài hợp đồng.

## 29. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Coi attribute là biến runtime | Người dùng hiểu sai tính declarative | Định nghĩa rõ semantics của declaration |
| Không có schema | Không biết field, type và required rule | Xây schema cho từng loại khai báo |
| Dùng string cho mọi giá trị | Khó kiểm tra và chuyển đổi | Dùng type system có đơn vị và reference |
| Không phân biệt absent với null | Default và merge cho kết quả bất ngờ | Định nghĩa presence semantics |
| Không công bố precedence | Giá trị hiệu lực khó giải thích | Định nghĩa thứ tự nguồn và provenance |
| Merge list không nhất quán | Override có thể thêm hoặc xóa ngoài ý muốn | Chọn merge strategy theo field |
| Cho phép duplicate attribute mơ hồ | Kết quả phụ thuộc thứ tự | Báo lỗi hoặc quy định override tường minh |
| Reference chỉ là string | Bỏ qua type và existence checking | Dùng reference node có kiểu |
| Không kiểm tra dependency cycle | Engine không xác định được thứ tự xử lý | Xây graph và phát hiện cycle |
| Default động không kiểm soát | Cấu hình khó tái lập | Ghi rõ context và thời điểm evaluate |
| Đọc secret vào output | Lộ thông tin nhạy cảm | Redaction và secret reference |
| Trộn validation với apply | Kiểm tra có thể tạo side effect | Tách check, render, plan và apply |
| Bỏ qua schema version | Cùng source có thể được hiểu khác | Pin schema và migration |
| Không lưu provenance | Khó giải thích giá trị hiệu lực | Gắn nguồn vào từng field |

## 30. Quy trình thiết kế một DSL khai báo cấu hình

Khi xây dựng DSL cấu hình, có thể đi theo các bước:

1. **Xác định domain model:** những loại resource, environment, rule và module nào cần mô tả?
2. **Thiết kế declaration form:** keyword, identifier, attribute, block và reference.
3. **Định nghĩa type system:** Boolean, số, string, duration, size, collection, enum và domain type.
4. **Xây schema:** required, optional, default, cardinality, range và cross-field constraints.
5. **Định nghĩa scope và namespace:** nơi khai báo có hiệu lực và cách resolve reference.
6. **Chọn expression model:** literal-only, pure expression hoặc khả năng tính toán có kiểm soát.
7. **Định nghĩa duplicate và ordering:** attribute trùng, block lặp và thứ tự xử lý.
8. **Thiết kế merge/precedence:** base, profile, environment, variables và CLI overrides.
9. **Quản lý sensitive data:** secret reference, redaction và capability.
10. **Xây semantic model:** giữ type, binding, default, provenance và dependency.
11. **Thiết kế validation:** syntax, schema, reference, domain, policy và environment.
12. **Xây renderer/backend:** chuyển mô hình đã kiểm tra sang target format.
13. **Thiết kế tooling:** formatter, checker, plan, diff và Language Server.
14. **Quản lý version:** schema, module, dependency và migration.
15. **Kiểm thử:** parser, semantic, merge, environment, serialization và side-effect boundary.

Mỗi loại khai báo nên có tài liệu mô tả mục đích, field, kiểu, default, reference, ví dụ hợp lệ và diagnostics thường gặp. Điều này giúp người viết DSL hiểu hợp đồng cấu hình mà không cần đọc implementation của compiler.

## 31. Ví dụ tổng hợp: khai báo một ứng dụng nhiều môi trường

Xét cấu hình:

~~~text
module commerce {
    let appImage = "registry.example/commerce:4.2"

    network "backend" {
        cidr = "10.30.0.0/16"
    }

    database "orders" {
        engine = "postgres"
        version = "16"
        storage = "100Gi"
        password = secret("commerce/orders/password")
    }

    service "orders-api" {
        image = appImage
        replicas = 2
        port = 8080
        network = network.backend
        database = database.orders

        resources {
            cpu = "500m"
            memory = "512Mi"
        }
    }

    profile "production" {
        service.orders-api.replicas = 5
        service.orders-api.resources.memory = "1Gi"
    }
}
~~~

Một engine có thể xử lý:

1. Parse module, network, database, service và profile.
2. Thu thập declarations và tạo scope.
3. Resolve appImage, secret reference, network và database.
4. Kiểm tra kiểu của replicas, port, cpu, memory và storage.
5. Áp dụng default từ schema.
6. Áp dụng profile production theo merge rules.
7. Kiểm tra policy như secret reference, network range và replica limits.
8. Tạo dependency graph.
9. Render cấu hình hiệu lực cho target.
10. Tạo plan hoặc diff nếu có trạng thái hiện tại.

### 31.1. Cấu hình hiệu lực

Khi chọn profile production, service có thể có:

~~~text
image = "registry.example/commerce:4.2"
replicas = 5
port = 8080
resources.cpu = "500m"
resources.memory = "1Gi"
~~~

Giá trị replicas và memory đến từ profile; các field còn lại đến từ khai báo gốc hoặc default. Provenance giúp công cụ giải thích nguồn của từng giá trị.

### 31.2. Dependency order

Engine có thể xác định database và network cần sẵn sàng trước service. Thứ tự này được suy ra từ reference, không nhất thiết theo thứ tự source.

### 31.3. Kiểm tra trước khi apply

Checker có thể xác nhận cấu hình tĩnh. Plan engine có thể truy vấn môi trường để xác định image, quota và resource availability. Apply mới thực hiện thay đổi thật theo quyền đã cấp.

## 32. Tiêu chí của khai báo cấu hình tốt

Một DSL cấu hình tốt làm cho trạng thái mong muốn dễ đọc, dễ kiểm tra và dễ tái lập. Mỗi khai báo có identity, schema, kiểu dữ liệu, phạm vi và quy tắc tham chiếu rõ. Các nguồn default và override có thứ tự xác định; công cụ có thể giải thích giá trị hiệu lực và truy vết về source ban đầu.

Các câu hỏi quan trọng:

- Loại khai báo và thuộc tính được phép được định nghĩa ở đâu?
- Field nào required, optional, nullable hoặc có default?
- Giá trị dùng kiểu cụ thể hay chỉ là string?
- Block lồng nhau có cardinality và scope nào?
- Reference được resolve và kiểm tra kiểu ra sao?
- Expression có thuần và có thể đánh giá tĩnh không?
- Duplicate attribute và thứ tự khai báo được xử lý thế nào?
- Các nguồn cấu hình được merge theo precedence nào?
- Profile và environment có thể override những field nào?
- Secret được tham chiếu, resolve và redact ra sao?
- Checker phân biệt lỗi tĩnh với điều kiện phụ thuộc môi trường thế nào?
- Render, plan và apply có ranh giới side effect rõ không?
- Schema và module version được quản lý thế nào?
- Có thể truy vết provenance của giá trị cuối cùng không?

Khai báo cấu hình là nền tảng để DSL mô tả hệ thống bằng một mô hình có cấu trúc thay vì các chuỗi tham số rời rạc. Khi cú pháp, schema, kiểu, scope, reference, default, merge và validation được đặc tả rõ, công cụ có thể chuyển khai báo thành cấu hình hiệu lực đáng tin cậy, giải thích được và phù hợp với nhiều môi trường triển khai.
