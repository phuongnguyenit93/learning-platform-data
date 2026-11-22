# Hợp nhất và merge

Trong một DSL (Domain-Specific Language), dữ liệu và cấu hình thường được lưu thành nhiều tệp hoặc trao đổi giữa nhiều hệ thống. Một dự án có thể có cấu hình mặc định, cấu hình theo môi trường, phần ghi đè của từng khách hàng và các bản cập nhật được nhập từ bên ngoài. Khi các nguồn này cùng mô tả một đối tượng hoặc cùng tác động lên một tập dữ liệu, hệ thống cần kết hợp chúng theo những quy tắc nhất quán. Quá trình đó được gọi là **hợp nhất (merge)**.

Merge không đơn giản là nối hai tệp hoặc ghi đè toàn bộ dữ liệu cũ bằng dữ liệu mới. Nó là một phép kết hợp có ngữ nghĩa: xác định phần tử nào đại diện cho cùng một thực thể, trường nào được giữ, trường nào được thay thế, cách xử lý xung đột và cách bảo đảm kết quả hợp lệ theo schema của DSL.

Trong chương lưu trữ và trao đổi, merge thường xuất hiện khi ghép nhiều lớp cấu hình, nhập dữ liệu, đồng bộ bản sao, áp dụng patch, hợp nhất snapshot hoặc xử lý thay đổi đồng thời. Thiết kế tốt cần xác định rõ chiến lược cho từng loại dữ liệu, quy tắc ưu tiên, cách xử lý giá trị thiếu và xóa, tính xác định, tính nguyên tử và khả năng truy vết nguồn gốc.

## 1. Merge là gì?

Merge là thao tác kết hợp hai hoặc nhiều nguồn dữ liệu thành một kết quả theo một chính sách đã định nghĩa. Có thể ký hiệu:

```text
result = merge(base, incoming, policy)
```

Trong đó `base` là dữ liệu đang có, `incoming` là dữ liệu được đưa vào và `policy` xác định cách kết hợp. Một số hệ thống còn có `local`, `remote` và `commonBase` để xử lý thay đổi đồng thời.

Ví dụ hai tệp cấu hình:

```yaml
# defaults.yml
service:
  port: 8080
  timeout: 30
logging:
  level: INFO
  file: app.log
```

```yaml
# production.yml
service:
  timeout: 60
logging:
  level: WARN
```

Nếu dùng deep merge với chính sách thay thế scalar, kết quả có thể là:

```yaml
service:
  port: 8080
  timeout: 60
logging:
  level: WARN
  file: app.log
```

Các trường không được khai báo trong `production.yml` vẫn được giữ từ cấu hình mặc định. Đây là một cách dùng phổ biến của merge trong DSL cấu hình.

### 1.1. Merge khác với nối (concatenation)

Nối thường đặt các phần tử của nguồn này sau nguồn kia, ví dụ ghép hai danh sách. Merge phải hiểu cấu trúc dữ liệu và quy tắc trùng lặp. Với map, nó có thể kết hợp theo khóa; với record, theo trường; với danh sách, có thể nối, thay thế hoặc hợp nhất theo identity.

### 1.2. Merge khác với overwrite

Overwrite thay toàn bộ giá trị đích bằng giá trị nguồn. Merge chỉ thay đổi những phần mà chính sách cho phép, giữ lại các phần khác và có thể phát hiện xung đột.

### 1.3. Merge khác với synchronization

Synchronization giữ nhiều bản sao tiến tới cùng trạng thái theo một giao thức. Merge có thể là một bước bên trong đồng bộ, nhưng đồng bộ còn phải xử lý phát hiện thay đổi, truyền dữ liệu, thứ tự cập nhật, xác nhận và xử lý lỗi mạng.

## 2. Những tình huống cần merge trong DSL

Các tình huống thường gặp gồm:

- **Cấu hình nhiều lớp:** kết hợp mặc định, môi trường, tenant và cấu hình ghi đè.
- **Nhập dữ liệu:** ghép bản ghi từ nhiều tệp hoặc nguồn API vào kho dữ liệu.
- **Cập nhật một phần:** áp dụng patch chỉ chứa những trường thay đổi.
- **Snapshot:** kết hợp trạng thái đã lưu với thay đổi mới.
- **Đồng bộ:** xử lý thay đổi từ client, server hoặc nhiều replica.
- **Schema evolution:** chuyển dữ liệu từ định dạng cũ sang mới rồi hợp nhất.
- **Mô hình miền:** ghép các thuộc tính của một entity từ nhiều nguồn có thẩm quyền khác nhau.
- **Workflow:** hợp nhất kết quả từ nhiều bước hoặc nhánh song song.

Ví dụ, một DSL mô tả cấu hình có thể khai báo:

```text
config service {
    defaults from "defaults.yml"
    overlay from "production.yml"
    overlay from "tenant-acme.yml"
    conflict = prefer_later_source
}
```

Cú pháp trên chỉ minh họa. Ngữ nghĩa cần nói rõ thứ tự lớp, cách merge map/list, xử lý null, cách xác định khóa và trường hợp hai nguồn cùng thay đổi một giá trị.

## 3. Cấu trúc dữ liệu quyết định chiến lược merge

Không có một chính sách merge duy nhất phù hợp với mọi kiểu dữ liệu. Cách kết hợp phải dựa trên cấu trúc và ý nghĩa của từng giá trị.

| Kiểu dữ liệu | Các chiến lược thường gặp |
|---|---|
| Scalar (số, chuỗi, Boolean, enum) | Thay thế, ưu tiên nguồn, giữ giá trị cũ, báo xung đột |
| Record/object | Merge theo từng trường, deep merge, merge có schema |
| Map/dictionary | Hợp nhất theo khóa, xử lý khóa trùng |
| List/array | Thay thế, nối, hợp nhất theo identity, giữ thứ tự |
| Set | Hợp, giao, hiệu hoặc thêm/xóa phần tử |
| Counter | Cộng delta hoặc dùng cấu trúc counter phân tán |
| Quan hệ tham chiếu | Hợp nhất theo ID và kiểm tra toàn vẹn tham chiếu |
| Blob/file | Thay thế toàn bộ, so sánh hash hoặc merge theo định dạng chuyên biệt |

Ví dụ, hai danh sách người nhận email có thể được hợp nhất bằng union để loại phần tử trùng. Nhưng hai danh sách bước trong workflow có thứ tự thực thi không thể được union tùy tiện vì thứ tự là một phần semantics.

## 4. Các chiến lược merge cơ bản

### 4.1. Replace (thay thế)

Giá trị mới thay hoàn toàn giá trị cũ:

```text
merge(oldValue, newValue) = newValue
```

Chiến lược này phù hợp với scalar, cấu hình được quản lý như một đơn vị hoặc danh sách mà nguồn mới đại diện cho toàn bộ nội dung mong muốn.

Ví dụ:

```yaml
features: [search, export]
```

Nếu nguồn incoming là `[search, audit]`, replace tạo `[search, audit]`; `export` bị loại khỏi kết quả.

### 4.2. Keep existing (giữ giá trị cũ)

Giá trị cũ được giữ nếu đã tồn tại; incoming chỉ cung cấp giá trị cho trường chưa có. Cách này thường dùng khi nguồn nền có quyền ưu tiên cao hơn nguồn bổ sung, nhưng cần tên chính sách rõ để tránh nhầm với replace.

### 4.3. Prefer incoming (ưu tiên nguồn mới)

Incoming thay thế giá trị hiện có khi cả hai cùng cung cấp trường. Đây là chính sách đơn giản cho cấu hình override:

```text
merge(base, incoming) = incoming khi incoming có giá trị
```

Cần phân biệt “không có trường” với “trường có giá trị null”. Nếu incoming không chứa trường, thường giữ base; nếu chứa null, kết quả tùy semantics null đã công bố.

### 4.4. Deep merge

Deep merge đi vào các object lồng nhau và hợp nhất từng trường thay vì thay toàn bộ object.

```yaml
# base
database:
  host: db.internal
  port: 5432
  pool:
    min: 2
    max: 10
```

```yaml
# incoming
database:
  host: db.production
  pool:
    max: 30
```

Kết quả deep merge:

```yaml
database:
  host: db.production
  port: 5432
  pool:
    min: 2
    max: 30
```

Deep merge thường áp dụng cho map hoặc record. Khi gặp hai scalar cùng trường, chính sách scalar như prefer incoming hoặc conflict error sẽ được dùng.

### 4.5. Append (nối danh sách)

Append đặt phần tử incoming ở cuối danh sách hiện có:

```text
merge([A, B], [C, D]) = [A, B, C, D]
```

Chiến lược này phù hợp với log hoặc danh sách sự kiện có thứ tự, nếu nguồn incoming luôn chứa phần tử mới. Nếu incoming có thể gửi lại cùng dữ liệu, append có nguy cơ tạo bản ghi trùng.

### 4.6. Union (hợp tập hợp)

Union kết hợp các phần tử và loại bỏ trùng theo quy tắc equality hoặc identity:

```text
merge({A, B}, {B, C}) = {A, B, C}
```

Phải xác định thế nào là hai phần tử giống nhau. So sánh toàn bộ object, khóa ID hay một thuộc tính nghiệp vụ có thể tạo kết quả khác nhau.

### 4.7. Merge theo khóa (keyed merge)

Với danh sách record, có thể dùng một trường làm identity:

```yaml
users:
  - id: u1
    role: reader
  - id: u2
    role: editor
```

Incoming có thể cập nhật `u2` và thêm `u3`. Thay vì nối cả danh sách, resolver tìm phần tử theo `id`, rồi merge các trường của từng record. Chính sách cần xác định xử lý ID trùng, ID thiếu và thứ tự phần tử.

## 5. Xác định identity của dữ liệu

Merge chỉ có thể kết hợp đúng khi biết hai phần tử có đại diện cho cùng một thực thể hay không.

Các lựa chọn identity:

- Khóa chính như `id` hoặc `code`.
- Khóa ghép từ nhiều trường.
- Qualified key gồm namespace và tên.
- Hash nội dung nếu dữ liệu bất biến và equality theo nội dung phù hợp.
- Natural key như email hoặc mã nghiệp vụ, nếu có tính duy nhất được bảo đảm.

Ví dụ hai record:

```json
{"id":"order-42","status":"PAID","total":120000}
```

```json
{"id":"order-42","status":"SHIPPED"}
```

Nếu `id` là identity, hai record mô tả cùng một order và có thể được merge theo trường. Nếu không có identity ổn định, hệ thống có thể coi chúng là hai phần tử riêng, dẫn đến trùng dữ liệu.

### 5.1. Identity không nhất thiết là tên hiển thị

Tên khách hàng hoặc nhãn có thể thay đổi và không bảo đảm duy nhất. Dùng chúng làm khóa merge có thể gộp nhầm hai thực thể khác nhau hoặc tách một thực thể sau khi đổi tên.

### 5.2. Namespace và khóa trùng

Khi dữ liệu đến từ nhiều hệ thống, ID `123` có thể tồn tại ở cả hai nguồn nhưng đại diện cho hai đối tượng khác nhau. Có thể dùng khóa ghép `(source, id)` hoặc một định danh toàn cục.

### 5.3. Identity thay đổi

Nếu khóa nghiệp vụ có thể đổi, cần cơ chế alias hoặc mapping từ ID cũ sang ID mới. Nếu không, merge có thể tạo một record mới thay vì cập nhật record cũ.

## 6. Merge hai chiều và ba chiều

Có hai mô hình thường gặp: merge hai nguồn trực tiếp và merge ba chiều có common base.

### 6.1. Two-way merge

Two-way merge kết hợp hai phiên bản:

```text
result = merge(left, right)
```

Nó phù hợp khi nguồn có thứ tự ưu tiên rõ, hoặc khi các trường có thể kết hợp độc lập. Nhưng nếu cả hai phía cùng thay đổi một trường, chỉ nhìn hai giá trị hiện tại thường không đủ để biết đó là thay đổi có chủ ý hay giá trị cũ.

### 6.2. Three-way merge

Three-way merge dùng một phiên bản gốc chung (base) cùng hai phiên bản đã thay đổi:

```text
              common base
               /      \\
              v        v
          local       remote
              \\      /
               v    v
             three-way merge
                    |
                    v
                 result
```

Với mỗi trường, so sánh local và remote với base:

- Chỉ local thay đổi: chọn local.
- Chỉ remote thay đổi: chọn remote.
- Cả hai không thay đổi: giữ base.
- Cả hai thay đổi thành cùng giá trị: giữ giá trị đó.
- Cả hai thay đổi khác nhau: phát hiện conflict hoặc gọi resolver.

Ví dụ base có `status = DRAFT`. Local đổi thành `REVIEW`; remote vẫn `DRAFT`. Kết quả là `REVIEW`, vì chỉ local thay đổi. Nếu remote đổi thành `APPROVED`, cả hai cùng thay đổi khác nhau và cần giải quyết xung đột.

### 6.3. Vì sao common base quan trọng?

Không có base, resolver không biết giá trị nào là thay đổi mới và giá trị nào chỉ là giá trị cũ còn tồn tại. Three-way merge giảm xung đột giả và giữ được thay đổi độc lập ở hai phía.

### 6.4. Merge không có lịch sử

Với dữ liệu nhập từ file không có version hoặc base, có thể dùng ưu tiên nguồn, timestamp hoặc conflict error. Cần ghi rõ giới hạn vì timestamp không phải lúc nào cũng phản ánh thứ tự thực sự, đặc biệt khi đồng hồ các hệ thống lệch nhau.

## 7. Xung đột merge (merge conflict)

Conflict xảy ra khi các nguồn đưa ra thay đổi không thể kết hợp tự động theo chính sách hiện tại.

Ví dụ base:

```yaml
order:
  status: DRAFT
  note: Original
```

Local:

```yaml
order:
  status: REVIEW
  note: Updated locally
```

Remote:

```yaml
order:
  status: APPROVED
  note: Original
```

Trường `status` bị thay đổi ở cả hai phía thành hai giá trị khác nhau; trường `note` chỉ thay đổi ở local. Three-way merge có thể tự lấy `note` từ local và báo conflict ở `status`.

### 7.1. Các chiến lược giải quyết conflict

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Reject | Dừng merge và yêu cầu xử lý | Dữ liệu quan trọng, không có ưu tiên rõ |
| Prefer local | Chọn giá trị local | Local là nguồn có thẩm quyền |
| Prefer incoming/remote | Chọn giá trị incoming | Nguồn mới được xác định là authoritative |
| Prefer latest timestamp | Chọn thay đổi có thời gian mới hơn | Timestamp đáng tin và có đồng bộ |
| Custom resolver | Áp dụng logic nghiệp vụ | Có quy tắc miền rõ ràng |
| Manual resolution | Người dùng chọn kết quả | Thay đổi có ý nghĩa cần quyết định |

### 7.2. Conflict ở cấp trường và cấp đối tượng

Có thể merge độc lập từng trường nếu chúng không có phụ thuộc ngữ nghĩa. Tuy nhiên, một số thuộc tính cần được xử lý cùng nhau. Ví dụ `startDate` và `endDate` phải thỏa `startDate <= endDate`; merge từng trường có thể tạo cặp ngày không hợp lệ.

Trong trường hợp này, resolver cần kiểm tra invariant của cả đối tượng sau khi merge và có thể báo conflict ở cấp record.

### 7.3. Conflict không phải lúc nào cũng là lỗi

Conflict là thông tin cho biết không có kết quả duy nhất theo policy hiện tại. Ứng dụng có thể chờ người dùng giải quyết, đưa vào hàng đợi hoặc áp dụng quy tắc ưu tiên đã được công bố.

## 8. Giá trị thiếu, null và xóa

Một trong những nguồn lỗi phổ biến là coi absent, null và delete như cùng một trạng thái.

Có thể phân biệt:

- **Absent:** nguồn không cung cấp trường; thường có nghĩa là không yêu cầu thay đổi trường đó.
- **Null:** nguồn cung cấp trường với giá trị null; có thể nghĩa là xóa giá trị, chưa biết hoặc không áp dụng.
- **Delete:** yêu cầu xóa rõ ràng, có thể cần tombstone hoặc thao tác riêng.
- **Default:** giá trị được lấy từ schema hoặc cấu hình mặc định.

Ví dụ patch:

```json
{
  "displayName": "Lan",
  "middleName": null
}
```

Nếu absent có nghĩa giữ nguyên, `middleName: null` có thể xóa hoặc đặt null tùy hợp đồng. Không nên để người dùng đoán.

### 8.1. Tombstone

Trong đồng bộ phân tán, xóa một record bằng cách chỉ loại nó khỏi một bản sao có thể khiến bản sao khác gửi lại record cũ và làm nó xuất hiện trở lại. Tombstone là dấu xóa được lưu như một thay đổi có version hoặc timestamp để các replica biết record đã bị xóa.

### 8.2. Default không phải dữ liệu incoming

Nếu trường bị bỏ qua, hệ thống có thể áp dụng default khi tạo object mới. Nhưng khi merge object đã tồn tại, tự động áp dụng default có thể ghi đè dữ liệu cũ. Cần phân biệt quy tắc tạo mới và quy tắc merge.

### 8.3. Patch semantics

Patch mô tả các thay đổi cần áp dụng, không nhất thiết là một snapshot đầy đủ. Ví dụ, một patch có thể có các thao tác `set`, `remove`, `append` hoặc `test`. Merge patch cần định nghĩa rõ thứ tự và cách xử lý khi một thao tác thất bại.

## 9. Merge theo schema và kiểu dữ liệu

Không nên merge dữ liệu chỉ dựa trên tên trường. Schema DSL xác định kiểu, quyền, identity, default và invariant.

Ví dụ schema:

```text
entity Customer {
    id: CustomerId key
    name: String
    email: EmailAddress?
    tags: Set<String>
    addresses: List<Address>
}
```

Policy có thể quy định:

- `id`: immutable, dùng làm identity.
- `name`: prefer incoming hoặc conflict nếu hai bên cùng đổi.
- `email`: null có nghĩa xóa nếu patch khai báo explicit delete.
- `tags`: union theo giá trị.
- `addresses`: keyed merge theo `addressId`, không nối mù.

### 9.1. Type compatibility trước khi merge

Nếu một nguồn gửi `age` dưới dạng chuỗi còn schema yêu cầu Integer, cần validate hoặc chuyển đổi theo quy tắc tường minh trước khi merge. Không nên đưa dữ liệu sai kiểu vào kết quả rồi mới phát hiện ở bước lưu.

### 9.2. Schema version

Hai nguồn có thể được tạo theo hai phiên bản schema khác nhau. Trước khi merge, hệ thống có thể cần migrate chúng về một phiên bản chuẩn. Nếu một trường đã đổi kiểu hoặc đổi ý nghĩa, merge trực tiếp có thể không an toàn.

### 9.3. Unknown fields

Khi gặp trường không có trong schema hiện tại, DSL có thể từ chối, bỏ qua, giữ lại như extension data hoặc chuyển tiếp cho phiên bản mới. Quyết định này ảnh hưởng khả năng tương thích ngược và trao đổi giữa hệ thống.

### 9.4. Invariant sau merge

Ngay cả khi từng trường đều đúng kiểu, toàn bộ record có thể vi phạm invariant. Ví dụ tổng tiền không khớp các dòng hàng, ngày kết thúc trước ngày bắt đầu hoặc trạng thái `SHIPPED` nhưng thiếu tracking code. Cần validate đối tượng hoàn chỉnh sau khi merge.

## 10. Thứ tự nguồn và precedence

Khi merge nhiều lớp, thứ tự nguồn thường quyết định giá trị cuối cùng. Ví dụ:

```text
defaults < organization < environment < tenant < request
```

Trong mô hình ưu tiên, nguồn bên phải có thể ghi đè nguồn bên trái. Tuy nhiên, thứ tự phải được định nghĩa và hiển thị rõ.

### 10.1. Precedence không nên dựa vào thứ tự tình cờ

Không nên để kết quả phụ thuộc thứ tự duyệt map, thứ tự file hệ điều hành trả về hoặc thứ tự thread hoàn thành. Danh sách nguồn phải có thứ tự có chủ đích hoặc resolver phải dùng quy tắc ưu tiên độc lập.

### 10.2. Priority theo trường

Có thể một nguồn có thẩm quyền với trường này nhưng không có thẩm quyền với trường khác. Ví dụ hệ thống HR là nguồn chính cho `employeeName`, còn hệ thống IAM là nguồn chính cho `accessRoles`.

Khi đó policy có thể gắn priority theo field hoặc domain owner thay vì một thứ tự nguồn chung.

### 10.3. Timestamp và clock skew

Prefer latest có thể hữu ích nhưng timestamp cần đáng tin. Đồng hồ lệch, độ phân giải thời gian thấp hoặc việc import lại dữ liệu cũ có thể khiến thứ tự sai. Có thể dùng version number, logical clock hoặc sequence do nguồn cấp.

## 11. Tính chất toán học của merge

Các tính chất của phép merge quyết định cách nó hoạt động khi được áp dụng nhiều lần hoặc theo thứ tự khác nhau.

### 11.1. Idempotence

Một phép merge idempotent khi áp dụng cùng thay đổi nhiều lần không làm kết quả thay đổi thêm:

```text
merge(merge(A, B), B) = merge(A, B)
```

Tính chất này hữu ích khi hệ thống có retry hoặc gửi lại message. Union theo identity thường có thể idempotent; append thông thường thì không.

### 11.2. Commutativity

Một phép merge commutative khi đổi thứ tự nguồn không đổi kết quả:

```text
merge(A, B) = merge(B, A)
```

Union tập hợp có thể commutative. Prefer incoming hoặc append có thứ tự thường không commutative.

### 11.3. Associativity

Một phép merge associative khi cách nhóm các nguồn không ảnh hưởng kết quả:

```text
merge(merge(A, B), C) = merge(A, merge(B, C))
```

Tính chất này hữu ích khi hợp nhất dữ liệu theo từng batch hoặc cây giảm song song. Nếu policy dựa vào nguồn ưu tiên hoặc timestamp, cần bảo đảm phép nhóm không làm mất metadata cần thiết.

### 11.4. Không phải mọi merge cần đủ ba tính chất

Merge cấu hình theo precedence thường cố ý phụ thuộc thứ tự. Merge trạng thái phân tán có thể cần commutativity và associativity để hội tụ. Chọn tính chất theo mục tiêu hệ thống, không nên tuyên bố merge “an toàn” nếu chưa xác định những thuộc tính thực sự được bảo đảm.

## 12. Merge trong hệ thống phân tán

Khi nhiều client hoặc replica có thể cập nhật cùng dữ liệu mà không liên lạc tức thời, merge trở thành vấn đề đồng thời và hội tụ.

### 12.1. Last-write-wins

Last-write-wins (LWW) chọn thay đổi có timestamp hoặc version lớn nhất. Cách này đơn giản nhưng có thể làm mất cập nhật nếu timestamp không đáng tin hoặc hai thay đổi có ý nghĩa khác nhau.

### 12.2. Version vector và causal order

Version vector hoặc metadata nhân quả giúp nhận biết hai thay đổi có quan hệ trước-sau hay phát sinh độc lập. Nếu hai cập nhật độc lập cùng sửa một trường, hệ thống có thể nhận diện concurrent update và áp dụng resolver phù hợp.

### 12.3. CRDT

Conflict-free Replicated Data Type (CRDT) là nhóm cấu trúc dữ liệu được thiết kế để các bản sao có thể hợp nhất theo phép toán có tính chất hội tụ. Ví dụ, grow-only set có thể merge bằng union; một số counter dùng metadata riêng để cộng dồn thay đổi mà không đếm trùng.

CRDT không phải giải pháp cho mọi dữ liệu. Các thao tác nghiệp vụ phức tạp như chuyển trạng thái đơn hàng hoặc thay đổi số dư cần invariants và quy tắc miền riêng.

### 12.4. Event log và merge trạng thái

Thay vì merge snapshot, hệ thống có thể lưu event bất biến rồi dựng trạng thái bằng cách áp dụng event theo thứ tự. Khi đó, vấn đề chính là ordering, duplicate delivery, idempotency và xử lý event đến muộn.

## 13. Quy trình merge có kiểm soát

Một pipeline merge có thể chia thành các bước:

```text
Nhận các nguồn / patch
          |
          v
Parse và kiểm tra định dạng
          |
          v
Xác định schema và version
          |
          v
Chuẩn hóa dữ liệu
          |
          v
Xác định identity và provenance
          |
          v
So sánh base/local/incoming
          |
          v
Áp dụng merge policy
          |
          v
Phát hiện và giải quyết conflict
          |
          v
Validate kiểu và invariant
          |
          v
Commit kết quả nguyên tử
          |
          v
Ghi audit và version mới
```

### 13.1. Parse và validate nguồn

Không nên merge nội dung chưa parse được hoặc không tuân schema. Nếu một nguồn lỗi, chính sách có thể dừng toàn bộ merge hoặc cách ly nguồn lỗi, nhưng cần xác định rõ tính nguyên tử.

### 13.2. Normalize

Chuẩn hóa có thể gồm chuẩn hóa tên trường, đơn vị, enum, định dạng ngày giờ và canonical representation. Chỉ chuẩn hóa khi semantics cho phép; không được làm mất phân biệt có ý nghĩa.

### 13.3. Xác định identity

Resolver xác định record hoặc phần tử nào ở các nguồn đại diện cho cùng một thực thể. Kết quả cần có metadata về nguồn và khóa được dùng.

### 13.4. Áp dụng policy

Policy có thể khác nhau theo kiểu dữ liệu, trường hoặc loại thao tác. Nên dùng policy khai báo rõ thay vì một hàm merge tổng quát không biết ngữ nghĩa miền.

### 13.5. Validate kết quả

Sau merge, kiểm tra type, required fields, uniqueness, reference integrity và invariants của toàn đối tượng hoặc tập dữ liệu.

### 13.6. Commit nguyên tử

Nếu kết quả hợp lệ, ghi vào storage theo transaction hoặc cơ chế atomic replace phù hợp. Nếu một phần thất bại, rollback hoặc giữ trạng thái trước merge để tránh dữ liệu nửa cũ nửa mới.

## 14. Merge policy có thể khai báo trong DSL

Một DSL có thể cho người dùng mô tả policy thay vì viết logic merge thủ công.

Ví dụ cú pháp minh họa:

```text
merge policy CustomerMerge {
    identity by id

    field name prefer incoming
    field email conflict if both changed
    field tags union
    field addresses merge by addressId
    field createdAt keep existing
}
```

Policy này xác định identity và cách xử lý từng trường. Compiler có thể kiểm tra tên trường tồn tại, kiểu của trường phù hợp với strategy và policy có đầy đủ quy tắc cần thiết.

### 14.1. Strategy cần tương thích kiểu

Không phải strategy nào cũng áp dụng cho mọi kiểu. `union` phù hợp với set; `append` phù hợp với list; `sum` có thể phù hợp với counter; `deep` phù hợp với record/map. Nếu người dùng chọn `append` cho scalar, compiler nên báo lỗi.

### 14.2. Policy mặc định

Có thể có default strategy, nhưng cần tránh policy quá rộng. Một default như prefer incoming có thể phù hợp với cấu hình override nhưng nguy hiểm với dữ liệu tài chính hoặc trạng thái workflow.

### 14.3. Resolver tùy chỉnh

Với trường có semantics nghiệp vụ, DSL có thể cho phép gọi resolver đã đăng ký:

```text
field balance resolve with mergeBalance
```

Resolver cần có hợp đồng kiểu, quyền và tính xác định. Nếu chạy trong môi trường phân tán, nên xác định resolver có thuần (pure) và idempotent không.

## 15. Ví dụ merge cấu hình nhiều lớp

Giả sử có ba nguồn:

```yaml
# defaults
app:
  timeout: 20
  retries: 2
features:
  search: true
  export: false
```

```yaml
# environment
app:
  timeout: 45
features:
  export: true
```

```yaml
# tenant
app:
  retries: 5
features:
  customBranding: true
```

Với deep merge và precedence `defaults < environment < tenant`, kết quả:

```yaml
app:
  timeout: 45
  retries: 5
features:
  search: true
  export: true
  customBranding: true
```

Kết quả cho thấy mỗi lớp chỉ cần khai báo phần cần override. Khi một trường bị xóa, DSL cần một cú pháp hoặc marker xóa rõ ràng; bỏ trường khỏi file tenant không có nghĩa xóa giá trị kế thừa từ defaults.

## 16. Ví dụ merge danh sách record theo identity

Base:

```json
{
  "rules": [
    {"id":"r1","enabled":true,"priority":10},
    {"id":"r2","enabled":true,"priority":20}
  ]
}
```

Incoming:

```json
{
  "rules": [
    {"id":"r2","enabled":false},
    {"id":"r3","enabled":true,"priority":30}
  ]
}
```

Với keyed merge theo `id`, kết quả có thể là:

```json
{
  "rules": [
    {"id":"r1","enabled":true,"priority":10},
    {"id":"r2","enabled":false,"priority":20},
    {"id":"r3","enabled":true,"priority":30}
  ]
}
```

Kết quả giả định phần tử incoming có `id = r2` chỉ cập nhật trường được cung cấp và giữ `priority` cũ. Phần tử `r3` được thêm mới. Thứ tự danh sách được giữ theo base rồi thêm phần tử mới theo thứ tự incoming. Những lựa chọn này phải được nêu trong policy.

## 17. Patch và thao tác merge có điều kiện

Patch là tập thao tác mô tả thay đổi. Ví dụ:

```text
patch order-42 {
    test status == PAID
    set shippingAddress.city = "Da Nang"
    remove note
    append tags "priority"
}
```

Các thao tác có thể gồm:

- `test`: chỉ áp dụng nếu điều kiện hiện tại đúng.
- `set`: đặt giá trị trường.
- `remove`: xóa trường hoặc phần tử.
- `append`: thêm phần tử vào danh sách.
- `increment`: tăng counter.
- `merge`: hợp nhất object con.

### 17.1. Điều kiện precondition

`test` giúp tránh áp dụng patch lên trạng thái không còn như mong đợi. Ví dụ, nếu `status` đã chuyển từ `PAID` sang `CANCELLED`, patch chỉ hợp lệ khi điều kiện vẫn đúng.

### 17.2. Thứ tự thao tác

Patch thường có thứ tự; `remove` trước `set` có thể khác `set` trước `remove`. DSL cần quy định thao tác được áp dụng tuần tự hay gom theo field.

### 17.3. Patch thất bại một phần

Nên xác định patch là atomic hay cho phép partial success. Với cập nhật có nhiều trường phụ thuộc nhau, atomic patch thường dễ bảo đảm invariant hơn.

## 18. Merge, transaction và tính toàn vẹn

Merge thường thay đổi nhiều trường hoặc nhiều record. Nếu chỉ ghi được một phần, dữ liệu có thể rơi vào trạng thái không nhất quán.

### 18.1. Atomicity

Atomic merge nghĩa là toàn bộ thay đổi được commit hoặc không thay đổi gì. Có thể dùng transaction của database, write-ahead log, staging table hoặc ghi ra file tạm rồi atomic rename.

### 18.2. Consistency

Kết quả sau merge phải thỏa schema và domain invariants. Ví dụ, một đơn hàng không thể có tổng tiền âm nếu miền không cho phép; quan hệ foreign key phải trỏ đến record tồn tại.

### 18.3. Isolation

Nếu hai merge chạy đồng thời trên cùng dữ liệu, cần cơ chế khóa, optimistic concurrency hoặc version check để tránh lost update.

### 18.4. Durability

Sau khi commit thành công, kết quả cần được lưu bền vững theo bảo đảm của storage. Audit và version metadata nên được ghi cùng transaction nếu chúng là phần bắt buộc của lịch sử thay đổi.

### 18.5. Optimistic concurrency

Một client có thể gửi version mà nó đã đọc. Khi merge, storage kiểm tra version hiện tại có còn khớp không. Nếu đã thay đổi, merge phải được tính lại hoặc báo conflict thay vì ghi đè mù.

## 19. Provenance, audit và khả năng truy vết

Khi kết quả được tạo từ nhiều nguồn, cần biết giá trị cuối cùng đến từ đâu và vì sao được chọn.

Provenance có thể lưu:

- Nguồn dữ liệu và định danh bản ghi.
- Version hoặc timestamp của từng nguồn.
- Field nào được lấy từ nguồn nào.
- Strategy được áp dụng.
- Conflict nào đã xuất hiện và cách giải quyết.
- Người dùng hoặc service đã yêu cầu merge.
- Hash đầu vào và kết quả.

Ví dụ audit:

```text
field: service.timeout
base value: 20
incoming value: 45
strategy: prefer incoming
result: 45
source: production.yml
```

Thông tin này hữu ích khi điều tra cấu hình sai, giải thích dữ liệu sau đồng bộ và đáp ứng yêu cầu kiểm toán.

### 19.1. Không ghi secret vào audit

Provenance không có nghĩa phải lưu toàn bộ giá trị nhạy cảm. Có thể lưu source ID, field name, hash hoặc trạng thái thay đổi mà không ghi token, password hay dữ liệu cá nhân không cần thiết.

### 19.2. Lịch sử merge

Có thể lưu merge result cùng input versions để tái tạo hoặc giải thích kết quả. Với dữ liệu lớn, lưu event hoặc metadata thay vì nhân bản toàn bộ snapshot sau mỗi lần merge.

## 20. Merge và schema evolution

Khi DSL hoặc format dữ liệu thay đổi, các nguồn có thể không cùng schema version.

Ví dụ phiên bản cũ dùng:

```yaml
customer:
  fullName: Lan Nguyen
```

Phiên bản mới tách thành:

```yaml
customer:
  firstName: Lan
  lastName: Nguyen
```

Trước khi merge, có thể cần migration để đưa dữ liệu về schema canonical. Nếu một nguồn đã có `firstName` và nguồn khác chỉ có `fullName`, migration cần quy tắc phân tách hoặc conflict khi không thể suy ra chính xác.

### 20.1. Migrate trước hay sau merge?

Thông thường nên migrate từng nguồn về cùng schema đích trước khi merge để các field có ý nghĩa tương ứng. Nhưng một số migration cần thông tin từ nhiều nguồn hoặc cần merge dữ liệu trước; khi đó thứ tự phải được thiết kế theo dependency rõ ràng.

### 20.2. Backward và forward compatibility

Consumer mới có thể đọc dữ liệu cũ nếu migration hoặc default được định nghĩa. Consumer cũ có thể không hiểu trường mới. Hệ thống trao đổi cần xác định unknown field được giữ, bỏ qua hay từ chối.

### 20.3. Version của merge policy

Thay đổi strategy từ replace sang keyed merge có thể làm kết quả khác dù input không đổi. Nên version policy hoặc ghi lại phiên bản compiler/resolver trong metadata để tái lập kết quả.

## 21. Merge trong workflow và xử lý kết quả song song

Workflow có thể chạy nhiều nhánh cùng lúc rồi hợp nhất kết quả tại một bước join.

Ví dụ:

```text
                 START
                   |
            +------+------+
            |             |
            v             v
       checkInventory  checkCredit
            |             |
            +------+------ +
                   |
                   v
                MERGE
                   |
                   v
                decision
```

Khi hai nhánh cùng ghi một trường, engine cần policy. Có thể mỗi nhánh ghi vào namespace riêng, sau đó bước merge kết hợp kết quả; hoặc chỉ cho phép một nhánh sở hữu trường cụ thể.

### 21.1. Merge kết quả độc lập

Nếu hai nhánh cập nhật các trường khác nhau, có thể hợp nhất theo field. Nếu chúng cùng cập nhật `decision`, cần conflict resolver hoặc bước nghiệp vụ quyết định.

### 21.2. Partial failure

Nếu một nhánh thất bại, workflow cần quy định có chờ, retry, dùng kết quả còn lại hay hủy toàn bộ. Merge không nên tự giả định một kết quả thất bại tương đương với giá trị rỗng.

### 21.3. Idempotency khi retry

Workflow engine có thể gửi lại kết quả sau timeout. Các thao tác merge cần có event ID, operation ID hoặc identity ổn định để tránh append trùng hoặc cộng counter nhiều lần.

## 22. Bảo mật và tin cậy nguồn merge

Merge có thể kết hợp dữ liệu từ người dùng, file bên ngoài, plugin hoặc hệ thống khác. Nguồn không đáng tin cậy có thể gửi trường lạ, khóa trùng, dữ liệu quá lớn hoặc giá trị gây lỗi.

Các biện pháp cần xem xét:

- Xác thực nguồn và quyền được phép cập nhật từng field.
- Kiểm tra schema, kiểu và giới hạn kích thước trước khi merge.
- Không để nguồn ít tin cậy ghi đè field có thẩm quyền cao.
- Kiểm tra path và tên file nếu merge artifact.
- Giới hạn độ sâu object để tránh input lồng quá sâu.
- Phát hiện duplicate key và dữ liệu không chuẩn hóa.
- Không thực thi script hoặc resolver tùy ý từ nguồn chưa tin cậy.
- Ghi audit phù hợp nhưng bảo vệ secret và dữ liệu cá nhân.

### 22.1. Field-level authorization

Một nguồn có thể được phép cập nhật `displayName` nhưng không được phép thay `accountStatus` hoặc `roles`. Quyền cần được kiểm tra ở cấp field hoặc thao tác, không chỉ ở cấp file.

### 22.2. Trusted resolver

Resolver tùy chỉnh có thể thực thi logic. Chỉ cho phép resolver đã đăng ký, có chữ ký kiểu rõ và quyền hạn giới hạn. Không tải hoặc thực thi code tùy ý chỉ vì một file merge yêu cầu.

## 23. Kiểm thử merge

Merge cần được kiểm tra bằng ví dụ và các tính chất của policy.

Các trường hợp nên có:

1. Hai nguồn có field khác nhau.
2. Hai nguồn cùng cung cấp một scalar.
3. Object lồng nhau và deep merge.
4. List có phần tử trùng hoặc thiếu identity.
5. Set union và thứ tự phần tử.
6. Absent, null, delete và default.
7. Conflict khi cả hai phía cùng thay đổi.
8. Three-way merge với thay đổi độc lập.
9. Schema version khác nhau và migration.
10. Reference integrity và domain invariants.
11. Retry cùng patch để kiểm tra idempotence.
12. Hai merge đồng thời và optimistic concurrency.
13. Input sai kiểu hoặc nguồn không có quyền.
14. Partial failure và rollback.
15. Kết quả có provenance và audit đúng.

### 23.1. Property-based tests

Với policy có tính chất đã định nghĩa, có thể sinh dữ liệu ngẫu nhiên và kiểm tra:

- Idempotence nếu policy cam kết.
- Commutativity nếu thứ tự nguồn không có ý nghĩa.
- Associativity nếu merge theo batch cần kết quả nhất quán.
- Schema validity sau mọi merge thành công.
- Không mất thay đổi độc lập trong three-way merge.

Không áp dụng một tính chất toán học cho mọi strategy. Ví dụ prefer incoming cố ý không commutative.

### 23.2. Golden tests và conflict fixtures

Có thể lưu input base/local/remote và kết quả mong đợi cho từng conflict scenario. Khi policy thay đổi, test cho thấy hành vi mới khác ở đâu.

## 24. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng một strategy cho mọi kiểu | List, set và record bị kết hợp sai semantics | Chọn policy theo kiểu và ý nghĩa miền |
| Nối list không có identity | Dữ liệu trùng khi retry hoặc import lại | Keyed merge hoặc dedup theo khóa ổn định |
| Coi absent như null | Trường bị xóa ngoài ý muốn | Tách absent, null và delete marker |
| Dùng last-write-wins không kiểm soát | Mất cập nhật có ý nghĩa | Version/causal metadata hoặc conflict error |
| Merge field mà không validate object | Record vi phạm invariant | Validate toàn bộ entity sau merge |
| Không có common base khi cần 3-way merge | Không phân biệt thay đổi mới và giá trị cũ | Lưu version/base hoặc dùng policy rõ |
| Dựa vào thứ tự đọc file tình cờ | Kết quả không xác định | Khai báo precedence tường minh |
| Commit từng phần không có transaction | Dữ liệu ở trạng thái nửa cập nhật | Atomic commit hoặc rollback |
| Không lưu provenance | Khó giải thích giá trị cuối | Ghi source và policy đã áp dụng |
| Không xử lý schema version | Trường cũ/mới bị gộp sai | Migrate về schema chuẩn và version policy |
| Resolver tùy chỉnh không giới hạn | Rủi ro thực thi code và tác dụng phụ | Dùng resolver đã đăng ký, giới hạn quyền |

## 25. Nguyên tắc thiết kế merge cho DSL

Khi thiết kế cơ chế merge, có thể áp dụng các nguyên tắc sau:

1. **Định nghĩa semantics trước cú pháp.** Nêu rõ merge kết hợp dữ liệu nào và kết quả có ý nghĩa gì.
2. **Chọn identity ổn định.** Dùng ID hoặc khóa ghép có tính duy nhất, không dựa vào nhãn dễ thay đổi.
3. **Chọn strategy theo kiểu.** Scalar, record, list, set, counter và reference có chính sách riêng.
4. **Phân biệt snapshot với patch.** Nguồn đầy đủ và nguồn chỉ chứa thay đổi không được xử lý giống nhau.
5. **Tách absent, null và delete.** Định nghĩa rõ hành vi của từng trạng thái.
6. **Xử lý conflict tường minh.** Reject, ưu tiên nguồn, resolver hoặc manual resolution phải được công bố.
7. **Dùng common base khi cần three-way merge.** Không đoán thay đổi chỉ từ hai giá trị hiện tại.
8. **Validate schema và invariant.** Kiểm tra kiểu, identity, reference và toàn bộ object sau merge.
9. **Bảo đảm transaction.** Không để lỗi giữa chừng tạo dữ liệu nửa cũ nửa mới.
10. **Thiết kế idempotency và concurrency.** Retry và cập nhật đồng thời không được gây trùng hoặc mất dữ liệu ngoài dự kiến.
11. **Giữ provenance và audit.** Có thể giải thích nguồn gốc từng giá trị.
12. **Version schema và policy.** Kết quả có thể tái lập khi dữ liệu hoặc quy tắc thay đổi.
13. **Bảo vệ ranh giới tin cậy.** Kiểm tra quyền nguồn và giới hạn resolver.
14. **Kiểm thử theo tính chất đã cam kết.** Không mặc định mọi phép merge đều commutative, associative hoặc idempotent.

## 26. Kết luận

Hợp nhất và merge là cơ chế kết hợp dữ liệu hoặc cấu hình từ nhiều nguồn theo những quy tắc có ngữ nghĩa. Trong DSL, merge cần hiểu kiểu dữ liệu, identity, schema, thứ tự nguồn và mục đích của thay đổi. Replace, deep merge, append, union, keyed merge và three-way merge giải quyết những tình huống khác nhau; không có một chiến lược duy nhất phù hợp cho mọi cấu trúc.

Một thiết kế đáng tin cậy phải phân biệt snapshot với patch, absent với null và delete, phát hiện conflict, kiểm tra invariant sau khi hợp nhất và ghi kết quả theo transaction. Với hệ thống phân tán hoặc workflow, cần thêm idempotency, versioning, concurrency control và provenance để tránh mất hoặc nhân đôi thay đổi.

Khi policy được khai báo rõ và gắn với schema, người dùng DSL có thể kết hợp cấu hình và dữ liệu từ nhiều nguồn một cách dự đoán được. Runtime cũng có thể giải thích vì sao một giá trị được chọn, phát hiện xung đột đúng chỗ và duy trì tính toàn vẹn của dữ liệu sau mỗi lần merge.
