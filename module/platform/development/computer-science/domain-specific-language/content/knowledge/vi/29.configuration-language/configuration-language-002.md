# Giá trị mặc định môi trường trong DSL cấu hình

Một DSL (*Domain-Specific Language*) dùng để cấu hình hệ thống thường cần chạy trong nhiều môi trường như development, test, staging và production. Các môi trường có thể dùng cùng một cấu trúc cấu hình nhưng khác endpoint, số lượng tài nguyên, mức log, timeout hoặc tính năng được bật. Nếu người viết phải khai báo lại mọi giá trị ở từng môi trường, cấu hình sẽ dài, khó bảo trì và dễ lệch nhau.

**Giá trị mặc định môi trường** (*environment defaults*) là các giá trị được hệ thống sử dụng khi cấu hình không cung cấp giá trị cụ thể cho một thuộc tính trong một môi trường. Chúng giúp cấu hình ngắn gọn hơn, cung cấp lựa chọn hợp lý khi thiếu khai báo và cho phép áp dụng chính sách khác nhau theo môi trường.

Ví dụ, một DSL khai báo dịch vụ có thể cho phép:

```text
service "catalog" {
    image = "catalog:v3"
}
```

Nếu schema quy định replicas mặc định là 1 trong development và 3 trong production, hệ thống có thể hoàn thiện cấu hình sau khi xác định môi trường. Người viết không cần lặp lại giá trị nếu muốn dùng default.

Giá trị mặc định cần được thiết kế rõ ràng. Người dùng phải biết giá trị nào được áp dụng, đến từ đâu, khi nào một giá trị khác ghi đè nó và làm thế nào để xem cấu hình hiệu lực trước khi triển khai.

## 1. Vì sao cần giá trị mặc định theo môi trường?

Một cấu hình thường chứa cả những giá trị dùng chung và những giá trị phụ thuộc môi trường.

Ví dụ:

- Development có thể bật debug logging và dùng một dịch vụ giả lập.
- Test có thể dùng database tạm, timeout ngắn và dữ liệu fixture.
- Staging có thể gần production nhưng dùng tài nguyên nhỏ hơn.
- Production có thể bật bảo mật nghiêm ngặt, giới hạn quyền và cấu hình dự phòng.

Nếu mọi giá trị đều bắt buộc phải khai báo, người dùng phải lặp lại nhiều trường không thực sự khác nhau. Nếu một cấu hình không có default hợp lý, người dùng có thể vô tình chạy với giá trị rỗng hoặc giá trị không an toàn.

Environment defaults giúp:

1. Giảm cấu hình lặp lại.
2. Cung cấp giá trị ban đầu hợp lý cho từng môi trường.
3. Tạo sự nhất quán giữa các dự án.
4. Giữ cấu hình ngắn gọn và dễ đọc.
5. Tách giá trị chung khỏi khác biệt theo môi trường.
6. Làm rõ chính sách khi thuộc tính không được khai báo.
7. Hỗ trợ kiểm tra và hiển thị cấu hình hiệu lực.

Default không thay thế việc xác định rõ những giá trị quan trọng. Với các trường có ảnh hưởng lớn như endpoint production, credential, quyền truy cập hoặc chính sách xóa dữ liệu, hệ thống có thể yêu cầu khai báo tường minh thay vì tự chọn một giá trị mặc định.

## 2. Phân biệt environment, profile và default

Ba khái niệm thường được dùng cùng nhau nhưng có ý nghĩa khác nhau.

**Environment** là môi trường triển khai hoặc thực thi, chẳng hạn development, test, staging và production. Nó thường xác định những dịch vụ, tài nguyên và chính sách nào đang được sử dụng.

**Profile** là một nhóm cấu hình có thể bật để thay đổi hành vi. Ví dụ, profile debug có thể tăng mức log; profile performance có thể bật cache hoặc thay đổi giới hạn.

**Default** là giá trị được chọn khi không có khai báo cụ thể hơn theo quy tắc phân giải cấu hình.

Một environment có thể sử dụng nhiều profile. Ví dụ, staging có thể bật profile observability và profile performance. Default có thể đến từ schema chung, environment hoặc profile.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Environment | Cấu hình đang chạy ở đâu? | staging |
| Profile | Nhóm hành vi nào đang được bật? | debug, performance |
| Default | Giá trị nào được dùng khi chưa khai báo? | timeout = 30s |

Không nên dùng tên profile thay thế hoàn toàn cho environment nếu hai khái niệm có vòng đời và quyền quản lý khác nhau. Tách chúng giúp cấu hình dễ mở rộng.

## 3. Các nguồn cung cấp giá trị mặc định

Default có thể đến từ nhiều nơi. DSL cần xác định nguồn nào được phép cung cấp giá trị và cách kết hợp chúng.

Các nguồn phổ biến:

1. **Language built-in defaults:** giá trị mặc định được định nghĩa trực tiếp trong ngôn ngữ hoặc runtime.
2. **Schema defaults:** giá trị do schema của một resource hoặc thuộc tính quy định.
3. **Project defaults:** cấu hình chung của repository hoặc dự án.
4. **Environment defaults:** giá trị dành riêng cho development, test, staging hoặc production.
5. **Profile defaults:** giá trị được cung cấp khi một profile được bật.
6. **User defaults:** tùy chọn của người dùng hoặc workspace.
7. **Command-line overrides:** giá trị truyền khi chạy công cụ.
8. **Environment variables:** giá trị được inject từ môi trường tiến trình.
9. **External configuration:** cấu hình lấy từ service hoặc configuration store.

Không phải DSL nào cũng cần tất cả nguồn. Càng nhiều nguồn thì càng cần quy tắc precedence rõ và công cụ giải thích giá trị hiệu lực.

### Default thuộc về schema hay deployment?

Schema có thể định nghĩa giá trị mặc định về mặt ngôn ngữ, ví dụ một thuộc tính retryCount mặc định là 0. Deployment configuration có thể định nghĩa giá trị theo môi trường, ví dụ timeout production là 45 giây.

Cần phân biệt hai loại:

- Default mang ý nghĩa của thuộc tính trong DSL.
- Default phụ thuộc môi trường triển khai.

Nếu gộp chúng mà không có quy tắc, một thay đổi deployment có thể vô tình làm thay đổi semantics của chương trình DSL ở mọi môi trường.

## 4. Quy tắc precedence – nguồn nào được ưu tiên?

Khi cùng một thuộc tính được khai báo ở nhiều nguồn, hệ thống cần biết giá trị nào thắng.

Một thứ tự ví dụ từ ưu tiên thấp tới cao:

```text
Built-in default
    < Schema default
    < Project default
    < Environment default
    < Profile override
    < Explicit configuration
    < Command-line override
```

Thứ tự trên chỉ là một lựa chọn thiết kế, không phải quy tắc bắt buộc cho mọi DSL. Một hệ thống có thể đặt profile ở trước environment hoặc cấm một số nguồn ghi đè nguồn khác. Điều quan trọng là thứ tự phải được tài liệu hóa và nhất quán giữa CLI, editor, CI và runtime.

Ví dụ, nếu schema quy định timeout mặc định 20s, environment staging quy định 40s và cấu hình cụ thể của service quy định 60s, giá trị cuối cùng phụ thuộc precedence.

| Nguồn | timeout |
|---|---:|
| Schema default | 20s |
| Staging default | 40s |
| Service config | 60s |
| Giá trị hiệu lực theo thứ tự ví dụ | 60s |

### Không nên dựa vào thứ tự đọc file

Nếu hai file cấu hình cùng khai báo một thuộc tính, kết quả không nên phụ thuộc vào thứ tự filesystem hoặc thứ tự ngẫu nhiên của collection. Nguồn và precedence cần được biểu diễn rõ trong mô hình cấu hình.

### Xung đột cần được phát hiện

Một số hệ thống không cho phép ghi đè giữa các nguồn nhất định. Ví dụ, policy bảo mật có thể bắt buộc TLS và không cho project config tắt đi. Trong trường hợp này, giá trị không chỉ được chọn theo thứ tự; validator phải báo rằng override vi phạm policy.

## 5. Giá trị không khai báo, null và chuỗi rỗng

Một trong những quyết định quan trọng nhất của DSL cấu hình là phân biệt các trạng thái của một thuộc tính.

- **Absent:** thuộc tính không xuất hiện.
- **Null:** thuộc tính được khai báo nhưng có giá trị null.
- **Empty:** thuộc tính có giá trị rỗng, chẳng hạn chuỗi rỗng hoặc danh sách rỗng.
- **Explicit value:** thuộc tính có giá trị cụ thể.

Ví dụ:

```text
service "catalog" {
    # replicas absent
}

service "worker" {
    description = null
}

service "batch" {
    tags = []
}

service "api" {
    replicas = 4
}
```

Các trạng thái này không nhất thiết tương đương.

Một quy tắc phổ biến:

- Absent: dùng default.
- Null: xóa giá trị kế thừa hoặc biểu thị không có giá trị, nếu schema cho phép.
- Empty: giữ giá trị rỗng có chủ đích.
- Explicit value: dùng giá trị đã khai báo.

Nếu DSL xem null giống absent, người dùng không thể chủ động xóa một giá trị được kế thừa. Nếu xem empty giống absent, người dùng không thể khai báo danh sách rỗng để tắt một nhóm tùy chọn.

Schema cần định nghĩa rõ nullability và cách xử lý absent/empty cho từng thuộc tính.

## 6. Default chung và default theo environment

Một cấu hình thường có giá trị chung, sau đó một số môi trường ghi đè.

Ví dụ dạng minh họa:

```text
defaults {
    logLevel = "info"
    replicas = 1
    timeout = 30s
}

environment "development" {
    logLevel = "debug"
    replicas = 1
}

environment "production" {
    logLevel = "warn"
    replicas = 4
    timeout = 60s
}
```

Khi chọn development, hệ thống kết hợp default chung với phần ghi đè development. Khi chọn production, nó kết hợp default chung với phần ghi đè production.

| Thuộc tính | Default chung | Development | Production |
|---|---|---|---|
| logLevel | info | debug | warn |
| replicas | 1 | 1 | 4 |
| timeout | 30s | 30s | 60s |

Cách tổ chức này giúp các môi trường chỉ khai báo khác biệt. Tuy nhiên, không nên để default chung chứa endpoint hoặc credential cụ thể của production. Giá trị nhạy cảm nên được cấp từ secret manager hoặc hệ thống triển khai.

## 7. Kế thừa cấu hình và merge semantics

Một DSL có thể cho phép cấu hình môi trường kế thừa từ cấu hình chung hoặc từ environment khác.

Ví dụ:

```text
environment "staging" extends "production" {
    replicas = 2
    logLevel = "info"
}
```

Nếu staging kế thừa production, nó nhận các giá trị production rồi ghi đè replicas và logLevel.

Kế thừa cần có quy tắc merge cho từng loại dữ liệu.

### Scalar values

Với số, boolean, string hoặc enum, cách phổ biến là giá trị ở lớp ưu tiên cao thay thế giá trị thấp hơn.

### Nested objects

Với object lồng nhau, có hai lựa chọn thường gặp:

- Replace toàn bộ object.
- Deep merge từng thuộc tính con.

Ví dụ, nếu parent khai báo resource limits gồm cpu và memory, child chỉ ghi cpu, deep merge giữ memory từ parent. Replace toàn bộ object có thể làm memory trở thành absent hoặc quay về default khác.

DSL phải chọn và tài liệu hóa một semantics nhất quán.

### Lists

Danh sách có thể:

- Replace toàn bộ.
- Append phần tử.
- Merge theo key.
- Deduplicate theo quy tắc.
- Xóa phần tử bằng cú pháp riêng.

Không nên mặc định append chỉ vì dữ liệu là list. Với allowlist hoặc firewall rules, append có thể làm quyền rộng hơn ngoài ý muốn.

### Merge theo loại field

Một schema có thể khai báo merge strategy riêng cho từng thuộc tính:

| Kiểu thuộc tính | Strategy ví dụ |
|---|---|
| String/number/boolean | Replace |
| Nested object | Deep merge |
| Ordered list | Replace hoặc append theo khai báo |
| Set | Union hoặc replace |
| Map | Merge theo key |
| Security policy | Restrict-only hoặc explicit approval |

## 8. Phát hiện vòng lặp kế thừa

Nếu environment A kế thừa B và B lại kế thừa A, quá trình resolve sẽ không kết thúc.

Ví dụ:

```text
environment "development" extends "test" {}
environment "test" extends "staging" {}
environment "staging" extends "development" {}
```

Resolver cần phát hiện cycle trong đồ thị kế thừa và trả diagnostic chỉ ra chuỗi gây vòng lặp. Không nên tiếp tục merge một phần rồi trả cấu hình không xác định.

Nếu cho phép nhiều parent, cần quy định thứ tự hợp nhất và phát hiện cycle trên toàn đồ thị, không chỉ theo một nhánh.

## 9. Profile và tổ hợp cấu hình

Profile cho phép bật một nhóm cấu hình theo mục đích sử dụng.

Ví dụ:

```text
profile "observability" {
    tracing = true
    metrics = true
    logLevel = "debug"
}

profile "performance" {
    cacheEnabled = true
    workerCount = 8
}
```

Một environment có thể bật cả hai profile. Nếu hai profile ghi đè cùng một thuộc tính, hệ thống cần quy định thứ tự hoặc báo xung đột.

Có thể áp dụng các quy tắc:

- Profile được sắp xếp rõ ràng.
- Profile không được ghi đè thuộc tính protected.
- Hai profile xung đột tạo diagnostic.
- Một profile có thể yêu cầu profile khác.
- Profile chỉ được dùng ở environment được phép.

Tránh để thứ tự profile phụ thuộc vào thứ tự không xác định của set hoặc map.

## 10. Environment variables và external overrides

Nhiều hệ thống dùng environment variables để truyền cấu hình từ nền tảng triển khai vào runtime.

Ví dụ:

```text
APP_LOG_LEVEL=warn
APP_TIMEOUT=45s
APP_REGION=ap-southeast
```

DSL có thể hỗ trợ ánh xạ biến môi trường vào thuộc tính. Tuy nhiên, việc đọc trực tiếp biến môi trường từ mọi vị trí khiến chương trình khó tái lập và khó kiểm thử.

Một thiết kế rõ hơn là có bước configuration resolver đọc environment variables theo schema và chuyển chúng thành typed values trước khi thực thi DSL.

### Quy tắc đặt tên

Có thể dùng prefix riêng để tránh va chạm với biến của host. Ví dụ, APP_TIMEOUT được ánh xạ tới service.timeout.

### Kiểm soát nguồn ghi đè

Không phải biến môi trường nào cũng được phép ghi đè mọi thuộc tính. Schema có thể đánh dấu một số field chỉ được thiết lập bởi deployment controller hoặc secret provider.

### External configuration store

Nếu cấu hình đến từ service bên ngoài, cần ghi nhận version hoặc revision của nguồn. Nếu store thay đổi giữa lúc resolve và lúc chạy, execution có thể dùng một tổ hợp giá trị không nhất quán.

## 11. Type checking và chuyển đổi giá trị default

Default phải phù hợp với kiểu dữ liệu của thuộc tính.

Ví dụ:

```text
schema Service {
    replicas: Integer = 1
    enabled: Boolean = true
    timeout: Duration = 30s
    region: String
}
```

Nếu environment default gán replicas = "three", resolver cần báo type error. Không nên âm thầm chuyển một chuỗi bất kỳ thành số.

### Typed defaults

Giá trị nên được parse thành kiểu nội bộ của schema trước khi merge. Điều này tránh so sánh chuỗi với số hoặc xử lý đơn vị không nhất quán.

Ví dụ, 30s và 30000ms có thể cùng biểu diễn một Duration nếu DSL định nghĩa conversion đó. Resolver nên chuẩn hóa về một representation thống nhất.

### Conversion rules

Chỉ thực hiện conversion được đặc tả rõ. Không nên tự đoán rằng một số là giây hay mili giây, hoặc chuỗi "false" luôn được hiểu là Boolean false trong mọi ngữ cảnh.

### Validation sau khi resolve

Ngay cả khi từng nguồn riêng lẻ hợp lệ, kết quả merge có thể vi phạm constraint. Ví dụ, replicas trong development là 1, production là 4, nhưng policy chung yêu cầu giá trị tối đa 3. Cần validate cấu hình hiệu lực sau khi áp dụng toàn bộ default và override.

## 12. Default an toàn và security-sensitive settings

Một default thuận tiện có thể gây rủi ro nếu nó mở quyền quá rộng.

Ví dụ:

- TLS bị tắt mặc định.
- Public access được bật.
- Logging chứa dữ liệu nhạy cảm.
- Retry quá nhiều gây tải hệ thống.
- Timeout vô hạn.
- CORS cho phép mọi origin.
- Tài khoản chạy có quyền quản trị.

Với thuộc tính bảo mật, nên ưu tiên default an toàn hoặc yêu cầu khai báo rõ.

### Fail closed

**Fail closed** nghĩa là khi thiếu thông tin hoặc không thể xác minh, hệ thống từ chối thao tác thay vì mở quyền.

Ví dụ, nếu không xác định được policy truy cập resource, runtime nên từ chối truy cập. Không nên mặc định cho phép chỉ để cấu hình chạy được.

### Không dùng default cho secret

Password, API token và private key không nên có giá trị mặc định được lưu trong DSL hoặc source repository. Chúng cần được cấp từ secret manager hoặc cơ chế credential an toàn.

### Default theo môi trường không làm giảm kiểm tra quyền

Development có thể cho phép debug endpoint hoặc mock service, nhưng điều đó không có nghĩa production được bỏ qua authorization hoặc TLS.

## 13. Phân giải cấu hình thành effective configuration

Runtime thường cần một bước **configuration resolution** để kết hợp các nguồn thành một cấu hình cuối cùng.

Quy trình có thể gồm:

1. Đọc cấu hình DSL và schema.
2. Xác định environment đang được chọn.
3. Nạp project defaults.
4. Nạp environment defaults.
5. Nạp các profile được bật theo thứ tự.
6. Áp dụng explicit values trong cấu hình.
7. Áp dụng override được phép từ CLI hoặc deployment.
8. Parse và chuẩn hóa kiểu dữ liệu.
9. Kiểm tra policy và constraints.
10. Tạo immutable effective configuration cho execution.

Kết quả này thường được gọi là **effective configuration** hoặc resolved configuration.

### Vì sao cần một bước resolve riêng?

Nếu mỗi thành phần tự tìm default khi đọc thuộc tính, các phần của runtime có thể dùng những giá trị khác nhau. Một thành phần có thể đọc environment variable, thành phần khác lại dùng schema default.

Một resolver tập trung giúp mọi consumer dùng cùng một kết quả, cùng precedence và cùng metadata nguồn gốc.

## 14. Giải thích giá trị hiệu lực đến từ đâu

Khi người dùng thấy timeout = 60s, họ có thể cần biết vì sao giá trị này được chọn.

Resolver nên giữ provenance hoặc source metadata cho từng field:

```text
Effective value:
  service.timeout = 60s

Resolved from:
  source: environment "production"
  overridden by: service block
  schema default: 30s
```

Thông tin nguồn gốc giúp:

- Giải thích vì sao giá trị khác với default chung.
- Tìm override ngoài ý muốn.
- Điều tra cấu hình giữa các môi trường.
- Hỗ trợ review và audit.
- Phát hiện giá trị bị ghi đè mà người dùng không biết.

Một CLI có thể cung cấp lệnh tương tự:

```bash
dslc config explain service.timeout --environment production
```

Tên lệnh chỉ minh họa. Công cụ thực tế cần hiển thị cả giá trị cuối, nguồn, precedence và các override đã bị thay thế.

## 15. Kiểm tra cấu hình trước khi chạy

Không nên đợi tới lúc runtime sử dụng một field mới phát hiện giá trị default sai.

Có thể cung cấp các chế độ:

- **Parse:** kiểm tra cú pháp.
- **Validate:** kiểm tra schema, kiểu và constraints.
- **Resolve:** tính effective configuration.
- **Explain:** giải thích nguồn của từng giá trị.
- **Plan/Dry run:** hiển thị thay đổi dự kiến mà không thực hiện tác dụng phụ.

Ví dụ:

```text
dslc validate config.dsl --environment staging
dslc config resolve config.dsl --environment staging
dslc config explain replicas --environment staging
```

CI có thể chạy validate và resolve cho mọi environment được hỗ trợ. Điều này phát hiện sớm trường hợp một default chỉ hợp lệ trong development nhưng sai trong production.

## 16. Tính nhất quán và reproducibility

Một lần chạy DSL có thể cho kết quả khác nhau nếu default thay đổi theo thời gian, môi trường host hoặc phiên bản schema.

Để tái lập execution, cần ghi nhận:

- Environment name.
- Schema version.
- DSL version.
- Runtime version.
- Profile list và thứ tự.
- Nguồn configuration và revision.
- Các explicit overrides.
- Giá trị effective đã resolve hoặc hash của nó.
- Locale, timezone và các yếu tố ảnh hưởng khác nếu có.

### Snapshot cấu hình

Một cách là tạo snapshot immutable khi bắt đầu execution. Các thành phần trong lần chạy đều đọc cùng snapshot, không tự nạp lại default giữa chừng.

Nếu external configuration store cập nhật trong lúc execution đang chạy, lần chạy hiện tại vẫn dùng revision đã chụp. Lần chạy sau có thể nhận revision mới.

### Tránh phụ thuộc máy host

Không nên dùng hostname, user profile hoặc biến môi trường bất kỳ của máy chạy làm default ngầm. Nếu giá trị đó có ảnh hưởng tới kết quả, cần đưa nó vào execution context và ghi nhận rõ.

## 17. Default và cấu hình bất biến

Sau khi resolve và validate, effective configuration thường nên được đóng băng hoặc coi là immutable trong suốt execution.

Điều này giúp:

- Mọi thành phần đọc cùng một giá trị.
- Không có thread thay đổi cấu hình trong khi thread khác đang sử dụng.
- Dễ tái hiện lỗi.
- Dễ ghi nhận audit.
- Tránh việc default được tính lại khác nhau ở từng thời điểm.

Nếu ứng dụng hỗ trợ reload cấu hình, nên tạo snapshot mới và chuyển execution mới sang snapshot đó. Không nên âm thầm thay đổi giá trị giữa một transaction hoặc workflow đang chạy trừ khi semantics cho phép.

## 18. Ví dụ đầy đủ: cấu hình dịch vụ theo môi trường

Giả sử DSL có schema:

```text
schema Service {
    replicas: Integer = 1
    logLevel: LogLevel = "info"
    timeout: Duration = 30s
    tlsEnabled: Boolean = true
}
```

Cấu hình chung và môi trường:

```text
defaults {
    replicas = 1
    logLevel = "info"
    timeout = 30s
    tlsEnabled = true
}

environment "development" {
    logLevel = "debug"
    timeout = 10s
}

environment "production" {
    replicas = 4
    logLevel = "warn"
    timeout = 60s
}
```

Service khai báo:

```text
service "catalog" {
    image = "catalog:v3"
    replicas = 6
}
```

Nếu precedence cho phép service block ghi đè environment defaults, kết quả có thể là:

| Thuộc tính | Giá trị development | Giá trị production |
|---|---|---|
| replicas | 1 | 6 |
| logLevel | debug | warn |
| timeout | 10s | 60s |
| tlsEnabled | true | true |

Trong ví dụ này, service block ghi đè replicas = 1 hoặc replicas = 4 bằng 6. Nếu policy production giới hạn replicas tối đa 5, bước validation phải từ chối cấu hình hiệu lực. Precedence xác định giá trị được chọn; policy xác định giá trị đó có được phép hay không.

## 19. Migration khi thay đổi default

Thay đổi default có thể làm hành vi chương trình thay đổi dù người dùng không sửa DSL.

Ví dụ, schema version trước có timeout mặc định 30s, phiên bản mới đổi thành 60s. Những cấu hình không khai báo timeout sẽ tự động nhận giá trị mới.

Đây là một thay đổi có thể ảnh hưởng tới production.

Khi thay default:

1. Xác định những cấu hình đang dựa vào giá trị ngầm.
2. Đánh giá tác động lên latency, chi phí và semantics.
3. Ghi rõ thay đổi trong release notes.
4. Cân nhắc warning cho default sắp thay đổi.
5. Có thể yêu cầu người dùng khai báo explicit value nếu hành vi cần giữ nguyên.
6. Version hóa schema hoặc configuration contract khi cần.
7. Cung cấp công cụ giải thích giá trị trước và sau migration.

### Default và backward compatibility

Nếu chương trình cũ không khai báo một field, thay default có thể làm chương trình thay đổi hành vi. Vì vậy, backward compatibility cần xét cả giá trị tường minh và giá trị ngầm được áp dụng.

## 20. Test environment defaults

CI và test suite nên kiểm tra default theo từng environment, không chỉ kiểm tra cấu hình có giá trị tường minh.

Các loại test hữu ích:

- Không khai báo field: default đúng được áp dụng.
- Field được khai báo: explicit value thắng theo precedence.
- Environment override: giá trị đúng theo environment.
- Profile override: thứ tự và xung đột được xử lý.
- Null, absent và empty: phân biệt đúng.
- Kế thừa: merge scalar, object và list theo schema.
- Cycle: phát hiện vòng lặp kế thừa.
- Type mismatch: trả diagnostic.
- Policy violation: từ chối giá trị không an toàn.
- External override: chỉ áp dụng nguồn được cho phép.
- Snapshot: cùng execution dùng cùng resolved configuration.

Ví dụ test bảng:

| Input | Environment | Expected effective value |
|---|---|---|
| Không khai báo replicas | development | 1 |
| Không khai báo replicas | production | 4 |
| replicas = 2 | production | 2 nếu policy cho phép |
| replicas = 8 | production | Validation error nếu max là 5 |

Test cần kiểm tra cả giá trị hiệu lực và nguồn gốc của giá trị khi provenance là một phần của contract.

## 21. Quan sát và quản lý cấu hình hiệu lực

Một hệ thống vận hành tốt nên cung cấp cách xem cấu hình sau khi resolve mà không làm lộ secret.

Có thể hiển thị:

- Giá trị cuối cùng.
- Nguồn default hoặc override.
- Environment và profile được chọn.
- Schema version.
- Các field bị bỏ qua hoặc deprecated.
- Cảnh báo về override không cần thiết.
- Hash hoặc revision của snapshot.

Với secret, chỉ hiển thị trạng thái như “được cấp từ secret provider” hoặc tên reference đã được phép, không hiển thị nội dung.

Audit có thể ghi nhận ai thay đổi default, thay đổi ở nguồn nào, thời điểm và revision. Điều này hữu ích khi cấu hình production thay đổi ngoài dự kiến.

## 22. Những lỗi thường gặp

**Không định nghĩa precedence.** Người dùng không biết nguồn nào thắng khi nhiều file cùng khai báo một field. Cần công bố thứ tự và phát hiện xung đột.

**Coi absent, null và empty là giống nhau.** Người dùng không thể chủ động xóa giá trị kế thừa hoặc đặt danh sách rỗng. Cần định nghĩa semantics riêng.

**Merge mọi object và list theo cùng một cách.** Append list có thể mở rộng quyền ngoài dự kiến; replace object có thể làm mất thuộc tính khác. Merge strategy cần gắn với schema.

**Dùng default bảo mật không an toàn.** Ví dụ tắt TLS hoặc cho phép public access để cấu hình dễ chạy. Sensitive fields nên fail closed hoặc yêu cầu explicit value.

**Đưa secret vào default trong source.** Secret có thể bị commit, log hoặc hiển thị trong resolved config. Dùng secret provider và credential có scope.

**Đọc environment variable ở nhiều nơi.** Các thành phần có thể thấy giá trị khác nhau. Dùng resolver tập trung và snapshot.

**Không validate sau khi merge.** Từng nguồn hợp lệ nhưng kết quả cuối có thể vi phạm constraint. Validate effective configuration.

**Kế thừa không phát hiện cycle.** Resolver có thể chạy vô hạn hoặc trả kết quả không xác định. Kiểm tra đồ thị trước khi merge.

**Thay default mà không xem xét tương thích.** Cấu hình cũ có thể đổi hành vi dù không sửa source. Version hóa và thông báo migration.

**Không ghi nhận nguồn của giá trị.** Khó điều tra vì sao production dùng giá trị khác với schema. Lưu provenance và cung cấp explain command.

**Tính lại default giữa execution.** Các thành phần có thể dùng snapshot khác nhau. Resolve một lần và dùng cấu hình immutable.

## 23. Quy trình thiết kế environment defaults

Khi xây dựng DSL cấu hình, có thể thực hiện theo trình tự:

1. Liệt kê thuộc tính và kiểu dữ liệu trong schema.
2. Phân loại field nào có default, field nào bắt buộc khai báo.
3. Xác định nguồn default: schema, project, environment, profile hoặc deployment.
4. Định nghĩa precedence và các nguồn không được phép ghi đè.
5. Quy định semantics của absent, null, empty và explicit value.
6. Định nghĩa merge strategy cho scalar, object, map và list.
7. Phát hiện cycle trong inheritance và profile dependencies.
8. Parse và chuẩn hóa typed values trước khi merge.
9. Resolve cấu hình thành một effective configuration.
10. Validate constraints và security policy sau khi merge.
11. Ghi nhận provenance cho từng giá trị.
12. Tạo snapshot immutable cho execution.
13. Cung cấp lệnh validate, resolve và explain.
14. Viết test cho từng environment và trường hợp override.
15. Quản lý migration khi default hoặc schema thay đổi.

## 24. Câu hỏi tự kiểm tra

1. Giá trị mặc định môi trường là gì và vì sao DSL cấu hình cần nó?
2. Environment khác profile như thế nào?
3. Default có thể đến từ những nguồn nào?
4. Precedence giải quyết vấn đề gì khi nhiều nguồn khai báo cùng một field?
5. Phân biệt absent, null, empty và explicit value.
6. Vì sao merge strategy cần khác nhau giữa scalar, object và list?
7. Làm thế nào để phát hiện vòng lặp trong environment inheritance?
8. Profile xung đột có thể được xử lý theo những cách nào?
9. Vì sao nên resolve environment variables qua schema thay vì đọc tùy ý ở mọi nơi?
10. Typed defaults và validation sau merge có vai trò gì?
11. Vì sao security-sensitive settings cần default an toàn hoặc explicit declaration?
12. Secret nên được cấp cho runtime theo cách nào?
13. Effective configuration và provenance giúp điều tra sự cố ra sao?
14. Snapshot immutable hỗ trợ reproducibility như thế nào?
15. Thay đổi default có thể ảnh hưởng backward compatibility ra sao?
16. Những test nào cần có cho environment defaults?
17. Vì sao không nên tính lại default ở nhiều thành phần trong cùng một execution?
18. Hãy thiết kế default cho development, staging và production của một service DSL, nêu precedence, merge strategy, validation và cách explain giá trị hiệu lực.

Giá trị mặc định môi trường giúp DSL cấu hình tái sử dụng được giữa các môi trường mà vẫn thể hiện rõ khác biệt cần thiết. Khi precedence, inheritance, kiểu dữ liệu, validation, security và provenance được định nghĩa nhất quán, người dùng có thể hiểu chính xác cấu hình nào sẽ được áp dụng trước khi thực thi hoặc triển khai.

