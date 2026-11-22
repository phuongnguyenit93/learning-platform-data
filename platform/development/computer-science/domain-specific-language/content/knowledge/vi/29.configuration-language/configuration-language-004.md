# Profile môi trường

Trong một DSL cấu hình, cùng một ứng dụng thường phải chạy ở nhiều môi trường như development, test, staging và production. Mỗi môi trường có thể dùng endpoint, database, giới hạn tài nguyên, logging level hoặc feature flag khác nhau. **Profile môi trường (environment profile)** là một tập cấu hình có tên, mô tả những giá trị và chính sách cần áp dụng khi ứng dụng chạy trong một môi trường cụ thể.

Profile giúp giữ cấu hình dùng chung ở một nơi, đồng thời tách những khác biệt theo môi trường thành các lớp có thể lựa chọn rõ ràng. Thay vì sao chép toàn bộ cấu hình cho từng môi trường, người viết DSL có thể định nghĩa cấu hình cơ sở rồi ghi đè một số trường trong profile `development`, `staging` hoặc `production`.

Ví dụ, cấu hình cơ sở có thể định nghĩa port, timeout và tên dịch vụ; profile production chỉ thay endpoint, bật TLS, tăng số replica và tắt debug. Khi triển khai, hệ thống chọn profile phù hợp, hợp nhất các lớp cấu hình, thay thế tham số môi trường, kiểm tra schema và tạo cấu hình hiệu lực (effective configuration).

## 1. Profile môi trường là gì?

Profile môi trường là một nhóm thiết lập được đặt tên để biểu diễn một cách cấu hình ứng dụng hoặc một dịch vụ trong một bối cảnh vận hành. Profile có thể bao gồm:

- Endpoint của dịch vụ ngoài và database.
- Tên database, connection pool và timeout.
- Logging level, tracing và metrics.
- Feature flags và giới hạn chức năng.
- Số worker, replica, concurrency và tài nguyên.
- Chính sách retry, cache và circuit breaker.
- TLS, authentication và quyền truy cập.
- Tham chiếu đến secret hoặc credential.
- Các giới hạn và chính sách đặc thù của môi trường.

Profile không nhất thiết tương ứng một-một với hạ tầng vật lý. Một nhóm có thể có nhiều profile cho các mục tiêu khác nhau, ví dụ `local`, `ci`, `integration`, `staging` và `production`; một môi trường cũng có thể kích hoạt nhiều profile theo các chiều cấu hình nếu DSL hỗ trợ composition.

### 1.1. Cấu hình cơ sở và cấu hình theo môi trường

Cấu hình cơ sở (base configuration) chứa các giá trị đúng cho phần lớn môi trường. Profile chỉ mô tả khác biệt cần thiết.

```text
config service {
    port = 8080
    requestTimeout = 30s
    logging.level = INFO
}

profile development {
    logging.level = DEBUG
}

profile production {
    requestTimeout = 10s
    logging.level = WARN
}
```

Khi chọn `development`, hệ thống giữ `port` và `requestTimeout` từ cấu hình cơ sở nhưng đổi logging level thành `DEBUG`. Khi chọn `production`, timeout thành `10s` và logging level thành `WARN`.

### 1.2. Profile không phải bản sao toàn bộ cấu hình

Nếu mỗi môi trường chứa một bản sao đầy đủ, các giá trị chung dễ bị lệch khi ứng dụng phát triển. Base plus overlay giúp giảm trùng lặp và làm nổi bật chính xác những điểm khác nhau.

### 1.3. Profile không thay thế validation

Profile chỉ mô tả giá trị. Hệ thống vẫn cần kiểm tra kiểu, trường bắt buộc, quan hệ giữa trường và chính sách bảo mật trước khi dùng cấu hình. Một profile tên `production` không tự động làm cấu hình an toàn.

## 2. Vì sao cần tách profile môi trường?

Các môi trường có mục đích khác nhau. Development cần phản hồi nhanh và thông tin debug; test cần dữ liệu xác định và dịch vụ giả lập; staging cần gần production để kiểm tra triển khai; production cần tính sẵn sàng, bảo mật và khả năng quan sát.

| Môi trường | Mục tiêu thường gặp | Cấu hình có thể khác |
|---|---|---|
| Local/development | Phát triển nhanh, debug | Debug logging, mock service, database local |
| Test/CI | Kết quả lặp lại, chạy tự động | Database tạm, clock giả, retry ngắn |
| Integration | Kiểm tra kết nối hệ thống | Endpoint sandbox, credentials thử nghiệm |
| Staging | Mô phỏng production | Quy mô nhỏ hơn, dữ liệu kiểm thử, telemetry đầy đủ |
| Production | Phục vụ người dùng thật | TLS, secret thật, giới hạn chặt, replica và monitoring |

Việc tách profile giúp:

- Tránh hard-code endpoint và credential vào mã nguồn.
- Làm rõ cấu hình nào thay đổi theo môi trường.
- Hạn chế dùng nhầm tài nguyên production trong test.
- Tạo cấu hình có thể kiểm tra và review trước khi triển khai.
- Hỗ trợ cùng một artifact chạy ở nhiều môi trường.
- Giảm nguy cơ cấu hình phát triển vô tình được triển khai production.

### 2.1. Cấu hình là một phần của hợp đồng triển khai

Ứng dụng không chỉ phụ thuộc vào code. Nó còn phụ thuộc vào database, endpoint, quyền, timeout và feature flags. Profile là một phần của hợp đồng giữa ứng dụng, runtime và môi trường triển khai.

### 2.2. Tránh phân nhánh logic theo môi trường trong code

Nếu code chứa nhiều điều kiện như `if production` hoặc `if development`, cấu hình dễ bị phân tán. Nên để profile cung cấp các giá trị hoặc capability cần thiết, còn logic nghiệp vụ dùng một interface thống nhất. Một số hành vi thật sự khác nhau vẫn có thể cần policy riêng, nhưng phải được mô hình hóa rõ.

## 3. Cấu trúc một profile

Một profile thường có tên, metadata tùy chọn và một tập cấu hình. DSL có thể dùng cú pháp block:

```text
profile staging {
    application {
        debug = false
        requestTimeout = 20s
    }

    database {
        url = env("STAGING_DB_URL")
        pool.maxSize = 10
    }

    observability {
        logging.level = INFO
        tracing.enabled = true
    }
}
```

Các thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| Profile name | Định danh profile để kích hoạt |
| Base/parent | Nguồn cấu hình được kế thừa |
| Sections | Nhóm cấu hình theo dịch vụ hoặc miền |
| Overrides | Các giá trị thay thế cấu hình trước |
| Parameters | Giá trị được cung cấp lúc triển khai |
| Secret references | Tham chiếu đến secret store |
| Constraints | Điều kiện profile phải thỏa |
| Metadata | Mô tả, owner, version hoặc mục đích |

### 3.1. Tên profile

Tên nên ổn định, dễ hiểu và không phụ thuộc máy cá nhân. Nên dùng quy ước thống nhất như chữ thường và dấu gạch ngang: `development`, `test`, `staging`, `production`.

Không nên dùng tên mơ hồ như `new`, `temp` hoặc `latest` cho profile triển khai quan trọng. Nếu có profile theo khách hàng hoặc vùng địa lý, nên thể hiện chiều đó rõ ràng, ví dụ `production-eu`.

### 3.2. Section

Section nhóm các trường có liên quan như `database`, `logging`, `http`, `cache` hoặc `security`. Nhóm cấu hình giúp validation theo schema và quản lý ownership tốt hơn.

### 3.3. Metadata

Metadata có thể mô tả mục đích, người sở hữu, ngày hết hạn hoặc phạm vi sử dụng. Metadata không nên được dùng để thay thế cấu hình runtime hoặc chứa secret.

## 4. Base profile và kế thừa

Profile có thể kế thừa cấu hình từ một profile cơ sở hoặc profile cha. Cấu hình con chỉ cần ghi các trường khác biệt.

Ví dụ:

```text
profile base {
    http.port = 8080
    http.compression = true
    database.pool.min = 2
    database.pool.max = 20
    logging.level = INFO
}

profile development extends base {
    logging.level = DEBUG
    database.url = "jdbc:postgresql://localhost/dev"
}

profile production extends base {
    http.compression = true
    database.pool.max = 80
    logging.level = WARN
}
```

Khi chọn `development`, các giá trị từ `base` được kế thừa rồi các giá trị của `development` được áp dụng. `production` cũng kế thừa `base`, nhưng có override riêng.

### 4.1. Kế thừa một cấp và nhiều cấp

Có thể cho phép profile kế thừa trực tiếp một profile cha hoặc tạo chuỗi nhiều cấp:

```text
base -> cloud -> production -> production-eu
```

Chuỗi dài có thể giảm lặp lại nhưng làm khó truy vết nguồn của giá trị cuối. Nên giới hạn độ sâu hoặc yêu cầu công cụ hiển thị effective configuration cùng nguồn gốc từng trường.

### 4.2. Phát hiện vòng lặp kế thừa

Ví dụ `A extends B`, `B extends C`, `C extends A` tạo chu trình. Resolver phải phát hiện vòng lặp và báo lỗi trước khi hợp nhất. Không nên để kết quả phụ thuộc thứ tự duyệt.

### 4.3. Nhiều parent profile

Một số hệ thống cho phép composition nhiều profile, ví dụ kết hợp `cloud`, `region-eu` và `production`. Khi đó phải xác định precedence giữa các parent. Nếu hai parent cùng định nghĩa một trường với giá trị khác nhau, hệ thống cần báo conflict hoặc áp dụng thứ tự ưu tiên đã khai báo.

### 4.4. Kế thừa không đồng nghĩa với copy

Profile con tham chiếu đến cấu hình cha theo mô hình composition. Khi base thay đổi, effective configuration của profile con có thể thay đổi theo. Điều này cần được xem xét khi review thay đổi và quản lý version.

## 5. Overlay và thứ tự ưu tiên

Ngoài kế thừa, cấu hình thường được ghép từ nhiều lớp (overlay). Một thứ tự phổ biến:

```text
Built-in defaults
       |
       v
Application base
       |
       v
Environment profile
       |
       v
Deployment-specific values
       |
       v
Runtime environment variables
       |
       v
Effective configuration
```

Đây chỉ là một ví dụ. Một hệ thống có thể đặt secret resolution trước hoặc sau overlay, hoặc tách chúng thành bước riêng. Điều quan trọng là precedence phải được định nghĩa và kiểm tra.

### 5.1. Quy tắc ưu tiên

Có thể định nghĩa nguồn ở phía sau ghi đè nguồn phía trước:

```text
defaults < base < profile < deployment < runtime
```

Ví dụ, base đặt `logging.level = INFO`, profile production đặt `WARN`, còn biến môi trường runtime đặt `ERROR`. Kết quả cuối là `ERROR` nếu policy cho phép runtime override trường này.

### 5.2. Không để precedence ngầm

Nếu precedence chỉ dựa vào thứ tự file được đọc, kết quả có thể thay đổi theo môi trường hoặc thứ tự filesystem. Nên khai báo danh sách nguồn và thứ tự rõ ràng.

### 5.3. Field-level precedence

Không phải nguồn nào cũng có quyền ghi đè mọi trường. Ví dụ, deployment layer có thể được phép thay endpoint nhưng không được thay `security.requireTls`. Có thể định nghĩa quyền ghi đè theo section hoặc field.

### 5.4. Conflict khi hai lớp cùng định nghĩa

Với các trường có tính chất bảo mật hoặc invariant quan trọng, thay vì âm thầm chọn nguồn cuối, hệ thống có thể yêu cầu khai báo override tường minh hoặc báo conflict.

## 6. Kích hoạt profile

Runtime hoặc deployment system cần biết profile nào sẽ được áp dụng. Cách kích hoạt có thể gồm:

- Tham số dòng lệnh như `--profile production`.
- Biến môi trường như `APP_PROFILE=staging`.
- Thuộc tính JVM hoặc tham số runtime.
- Cấu hình trong manifest triển khai.
- API của ứng dụng hoặc bootstrap code.
- Profile được chọn bởi orchestrator hoặc nền tảng hosting.

### 6.1. Chọn profile một cách tường minh

Đối với môi trường quan trọng, nên chọn profile tường minh thay vì suy đoán từ hostname hoặc địa chỉ IP. Suy đoán dễ tạo lỗi khi ứng dụng chạy trong container, proxy hoặc môi trường cloud có topology thay đổi.

### 6.2. Default profile

Có thể có profile mặc định như `development` khi chạy local. Tuy nhiên, production nên yêu cầu khai báo profile hoặc deployment mode rõ ràng để tránh vô tình chạy với cấu hình phát triển.

### 6.3. Một hay nhiều profile hoạt động?

Một số ứng dụng chỉ cho phép một profile môi trường chính; hệ thống khác cho phép ghép nhiều profile độc lập, chẳng hạn `production` cùng `region-eu` và `feature-preview`.

Nếu cho phép nhiều profile, cần định nghĩa thứ tự, tính tương thích và cách xử lý conflict. Không nên coi danh sách profile là tập hợp không có thứ tự nếu thứ tự ảnh hưởng kết quả.

### 6.4. Kiểm tra profile không tồn tại

Nếu yêu cầu kích hoạt `prodution` do lỗi chính tả, runtime không nên âm thầm quay về default. Cần báo profile không tồn tại và liệt kê các profile gần giống nếu có.

## 7. Biến môi trường và tham số triển khai

Profile thường chứa placeholder hoặc biểu thức lấy giá trị từ môi trường runtime.

Ví dụ:

```text
profile production {
    database.url = env("DATABASE_URL")
    http.port = envInt("PORT", default = 8080)
    service.region = env("REGION", required = true)
}
```

Biến môi trường hữu ích để truyền cấu hình ở thời điểm triển khai mà không phải sửa file DSL.

### 7.1. Required và optional parameters

Một tham số bắt buộc phải có giá trị trước khi ứng dụng khởi động. Tham số tùy chọn có thể có default.

```text
parameter DATABASE_URL: String required
parameter HTTP_PORT: Integer default 8080
```

Validation nên phát hiện tham số bắt buộc bị thiếu trước khi mở kết nối hoặc thực hiện tác dụng phụ.

### 7.2. Chuyển đổi kiểu

Biến môi trường thường là chuỗi. Nếu schema yêu cầu integer, Boolean, duration hoặc URI, resolver phải chuyển đổi và báo lỗi nếu giá trị không hợp lệ.

Ví dụ `HTTP_PORT=abc` cần tạo diagnostic chỉ rõ tham số và kiểu mong đợi, không để lỗi xuất hiện muộn ở tầng network.

### 7.3. Placeholder và interpolation

DSL có thể cho phép tham chiếu một giá trị trong chuỗi:

```text
service.url = "https://${HOST}:${PORT}/api"
```

Cần xác định interpolation xảy ra lúc parse, lúc resolve profile hay lúc runtime. Nếu cho phép biểu thức lồng nhau, cần kiểm soát chu trình tham chiếu và escape literal `${...}` khi muốn giữ nguyên văn bản.

### 7.4. Không đưa giá trị môi trường vào log tùy tiện

Biến môi trường có thể chứa credential hoặc thông tin nhạy cảm. Diagnostic nên chỉ ra tên biến bị thiếu hoặc sai định dạng, tránh in giá trị secret vào log.

## 8. Secret và thông tin nhạy cảm

Profile production có thể cần database password, API token, private key hoặc credential. Những giá trị này không nên được ghi trực tiếp vào tệp DSL được lưu trong repository.

Thay vào đó, profile lưu tham chiếu đến secret store:

```text
profile production {
    database.username = secret("prod/database/username")
    database.password = secret("prod/database/password")
    payment.apiKey = secret("prod/payment/api-key")
}
```

Runtime lấy giá trị từ secret manager hoặc nền tảng triển khai khi có quyền phù hợp.

### 8.1. Secret reference khác secret value

File DSL chỉ chứa định danh secret. Giá trị thật được cung cấp ở runtime hoặc trong một bước cấp phát an toàn. Điều này giúp review cấu hình mà không làm lộ credential.

### 8.2. Quyền truy cập theo môi trường

Credential production chỉ nên được cấp cho workload production. Profile development không nên có khả năng truy cập secret production chỉ vì dùng chung một file cấu hình.

### 8.3. Rotation

Secret có thể được xoay vòng. Runtime cần quy định lấy secret lúc khởi động hay refresh định kỳ, cách xử lý khi secret bị thu hồi và có cần restart dịch vụ không.

### 8.4. Redaction

Khi hiển thị effective configuration, log hoặc diagnostic, các trường secret phải được che giá trị. Có thể hiển thị `****` hoặc chỉ báo nguồn secret đã được resolve thành công.

### 8.5. Không commit secret vào profile

Ngay cả file tên `production.local` hoặc `secrets.yml` cũng có thể bị commit nhầm. Nên dùng secret store, file mount được quản lý an toàn hoặc cơ chế credential của nền tảng.

## 9. Schema và validation của profile

Profile là dữ liệu cấu hình có cấu trúc nên cần schema. Schema mô tả trường được phép, kiểu, cardinality, default, giá trị hợp lệ và quan hệ giữa các trường.

Ví dụ schema khái niệm:

```text
ServiceConfig {
    port: Integer where 1 <= port <= 65535
    debug: Boolean
    requestTimeout: Duration
    database: DatabaseConfig
}

DatabaseConfig {
    url: URI
    poolSize: Integer where poolSize > 0
    username: String
    password: SecretReference
}
```

### 9.1. Kiểm tra kiểu

Giá trị phải đúng kiểu yêu cầu. `poolSize = "ten"` cần bị từ chối nếu schema yêu cầu Integer.

### 9.2. Required fields

Profile production có thể yêu cầu database URL, TLS và secret reference. Nếu trường bắt buộc không được cung cấp sau khi hợp nhất tất cả lớp, validation phải thất bại.

### 9.3. Range và enum

Port phải nằm trong miền hợp lệ; logging level có thể chỉ nhận `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`. Kiểm tra cần diễn ra sau khi resolve placeholder và merge.

### 9.4. Cross-field constraints

Một số điều kiện phụ thuộc nhiều trường:

- Nếu `tls.enabled = true`, phải có certificate hoặc tham chiếu đến certificate.
- Nếu `replicas > 1`, storage/session state phải hỗ trợ chia sẻ hoặc replication.
- Nếu `debug = true`, production profile có thể không được phép.
- Nếu retry bật, `maxAttempts` và `backoff` phải nằm trong giới hạn.

Các điều kiện này nên được biểu diễn thành validation rules thay vì chỉ dựa vào tài liệu.

### 9.5. Unknown fields

Khi profile có trường không thuộc schema, hệ thống có thể từ chối để bắt lỗi chính tả, hoặc cho phép extension namespace. Bỏ qua unknown fields âm thầm có thể khiến người dùng nghĩ một cấu hình đã được áp dụng trong khi runtime không sử dụng nó.

## 10. Effective configuration

Effective configuration là kết quả cuối cùng sau khi:

1. Nạp default và base configuration.
2. Chọn profile hoạt động.
3. Áp dụng parent profiles hoặc overlays.
4. Resolve tham số và biến môi trường.
5. Resolve secret references theo quyền.
6. Chuyển đổi kiểu.
7. Validate schema và invariant.

Ví dụ:

```text
base:       logging.level = INFO
production: logging.level = WARN
runtime:    LOG_LEVEL = ERROR

effective:  logging.level = ERROR
```

Kết quả có thể được biểu diễn thành immutable configuration object để ứng dụng sử dụng. Nếu runtime cho phép thay đổi cấu hình động, cần xác định phần nào được cập nhật và thời điểm thay đổi có hiệu lực.

### 10.1. Xem effective configuration

Công cụ CLI hoặc IDE có thể hiển thị cấu hình cuối cùng sau merge. Đây là cách hữu ích để kiểm tra vì sao một giá trị cụ thể được chọn.

### 10.2. Nguồn gốc từng giá trị

Ngoài giá trị, công cụ nên hiển thị provenance:

```text
http.port = 8080
  source: base.dsl

logging.level = WARN
  source: profile production
  overrides: base.dsl
```

Với secret, chỉ hiển thị tên secret reference hoặc trạng thái đã resolve, không hiển thị nội dung.

### 10.3. Không sửa trực tiếp effective output

Effective configuration thường là artifact được tính toán. Nếu cần thay đổi, người dùng nên sửa base, profile, deployment parameter hoặc nguồn tương ứng, sau đó tạo lại kết quả.

## 11. Profile và cấu hình nhiều lớp

Một hệ thống thực tế có thể cần nhiều chiều cấu hình hơn chỉ tên môi trường.

Ví dụ:

```text
environment = production
region = eu-west
tenant = acme
deployment = blue
```

Có thể tổ chức thành các lớp:

- Base application profile.
- Environment profile như `production`.
- Region profile như `eu-west`.
- Tenant profile như `acme`.
- Deployment slot như `blue` hoặc `green`.

### 11.1. Tránh tạo quá nhiều tổ hợp profile

Nếu tạo một profile cho mọi tổ hợp environment × region × tenant × feature, số lượng profile tăng rất nhanh. Composition giúp tách các chiều độc lập.

### 11.2. Tương thích giữa các chiều

Không phải mọi tổ hợp đều hợp lệ. Ví dụ `production` có thể không cho phép `debug-preview`; một region có thể không hỗ trợ một database engine. Cần khai báo constraints cho tổ hợp profile.

### 11.3. Precedence đa chiều

Khi nhiều profile cùng cung cấp một field, cần thứ tự ưu tiên. Có thể quy định environment trước tenant, hoặc tenant trước region, tùy quyền sở hữu dữ liệu. Nên dùng một quy tắc được công bố và có thể xem trong effective configuration.

## 12. Profile và feature flags

Feature flag bật/tắt một chức năng. Profile có thể cung cấp giá trị mặc định cho flag theo môi trường:

```text
profile development {
    features.newCheckout = true
}

profile production {
    features.newCheckout = false
}
```

Feature flag khác với profile: profile chọn một nhóm cấu hình, còn flag là một giá trị điều khiển tính năng. Flag có thể được quản lý động bởi hệ thống riêng và thay đổi khi ứng dụng đang chạy.

### 12.1. Static flags và dynamic flags

Static flag được xác định lúc khởi động hoặc triển khai. Dynamic flag có thể được cập nhật qua service mà không redeploy. DSL cần phân biệt hai loại và không giả định mọi flag đều nằm trong file profile.

### 12.2. Không dùng profile để thay thế authorization

Tắt một feature trong production không phải biện pháp bảo mật đủ mạnh. Quyền truy cập phải được kiểm tra bằng authorization policy ở runtime. Feature flag chỉ điều khiển khả năng hiển thị hoặc thực thi tính năng theo mục đích đã định.

## 13. Profile và môi trường triển khai

Profile được dùng trong pipeline triển khai để tạo cấu hình phù hợp với môi trường đích.

Quy trình điển hình:

```text
DSL source + profile files
          |
          v
Parse and validate
          |
          v
Select environment profile
          |
          v
Merge base and overlays
          |
          v
Resolve parameters/secrets
          |
          v
Validate effective configuration
          |
          v
Generate deployment artifacts
          |
          v
Deploy to target environment
```

### 13.1. Build once, configure per environment

Một nguyên tắc hữu ích là tạo cùng một application artifact rồi cung cấp cấu hình theo môi trường khi triển khai. Điều này giảm khác biệt giữa binary chạy ở staging và production.

Không phải mọi hệ thống đều có thể tách hoàn toàn build-time và runtime configuration. Một số giá trị cần compile vào artifact; nếu vậy, phải ghi rõ vì chúng làm artifact phụ thuộc môi trường.

### 13.2. Promotion giữa các môi trường

Có thể promote cùng artifact từ test sang staging rồi production. Profile được chọn ở mỗi bước; không nên rebuild artifact khác nhau nếu mục tiêu là kiểm tra đúng artifact sẽ chạy production.

### 13.3. Staging parity

Staging nên mô phỏng các đặc điểm quan trọng của production như phiên bản dịch vụ, database engine, TLS và observability. Quy mô có thể nhỏ hơn, nhưng khác biệt cần được ghi nhận.

### 13.4. Drift detection

Configuration drift xảy ra khi cấu hình thực tế khác với profile hoặc khai báo mong muốn. Hệ thống có thể so sánh desired configuration với runtime state và báo khác biệt. Cần phân biệt drift được phép (ví dụ autoscaling) với drift ngoài chính sách.

## 14. Profile trong container và orchestration

Trong môi trường container, profile có thể được kích hoạt bằng environment variable, command argument hoặc manifest. Giá trị thực tế thường được cung cấp qua ConfigMap, mounted file hoặc secret manager.

Ví dụ manifest khái niệm:

```yaml
containers:
  - name: order-service
    image: example/order-service:1.4.0
    env:
      - name: APP_PROFILE
        value: production
      - name: PORT
        value: "8080"
```

Profile `production` được chọn khi container khởi động. `PORT` có thể override port nếu schema và policy cho phép.

### 14.1. ConfigMap và Secret

ConfigMap hoặc cấu hình tương đương phù hợp với giá trị không nhạy cảm. Secret resource hoặc secret manager phù hợp với credential. Không nên đưa secret vào image hoặc manifest văn bản được chia sẻ rộng.

### 14.2. Read-only configuration

Ứng dụng nên biết nguồn cấu hình nào được mount read-only. Nếu runtime sửa file profile trong container, thay đổi có thể mất khi container được tạo lại và làm khó kiểm soát desired state.

### 14.3. Reload cấu hình

Có thể reload profile khi file hoặc secret thay đổi. Cần xác định thành phần nào hỗ trợ reload, cách validate trước khi áp dụng và hành vi nếu cấu hình mới không hợp lệ. Thường nên giữ cấu hình cũ nếu reload thất bại.

## 15. Bảo mật profile môi trường

Profile production có thể điều khiển quyền, network, credential và hành vi bảo mật. Vì vậy, việc chọn và merge profile là một ranh giới bảo mật.

### 15.1. Least privilege

Workload chỉ nên nhận secret và quyền cần thiết cho nhiệm vụ. Profile development không nên có quyền truy cập tài nguyên production.

### 15.2. Cấm cấu hình nguy hiểm trong production

Có thể đặt policy như:

- `debug` phải false.
- TLS bắt buộc cho endpoint bên ngoài.
- Không cho phép anonymous access.
- Không cho phép wildcard CORS nếu policy không chấp nhận.
- Secret phải đến từ secret manager được duyệt.
- Logging không được ghi dữ liệu nhạy cảm.

Những điều kiện này cần được validation tự động.

### 15.3. Profile activation phải được bảo vệ

Người dùng hoặc service không được tùy ý kích hoạt profile có quyền cao hơn. Quyền chọn profile production hoặc profile chứa capability đặc biệt cần được kiểm soát bởi deployment pipeline và access policy.

### 15.4. Không tin profile từ nguồn không xác thực

Profile tải từ repository, artifact store hoặc API bên ngoài cần xác thực nguồn và version. Nếu profile có thể chứa resolver hoặc expression thực thi code, chỉ cho phép thành phần đã đăng ký và giới hạn quyền.

### 15.5. Audit

Ghi lại profile nào được kích hoạt, version nào được dùng, ai hoặc pipeline nào chọn nó và hash của effective configuration. Không ghi secret value vào audit.

## 16. Thay đổi profile và reload runtime

Không phải mọi trường cấu hình đều có thể thay đổi khi ứng dụng đang chạy.

Có thể chia:

- **Startup-only:** port, database pool, thread model hoặc cấu trúc runtime cần khởi động lại.
- **Reloadable:** logging level, một số feature flags hoặc danh sách endpoint.
- **Dynamic external:** giá trị được truy vấn từ service cấu hình hoặc secret manager.

### 16.1. Phân loại reloadability

Schema có thể đánh dấu field là `startupOnly` hoặc `reloadable`. Nếu profile thay đổi một trường startup-only, deployment system cần restart hoặc rolling update.

### 16.2. Validate trước khi áp dụng

Runtime nên tạo effective configuration mới, resolve đầy đủ và validate trước. Chỉ khi toàn bộ cấu hình hợp lệ mới chuyển sang trạng thái mới.

### 16.3. Atomic swap

Có thể tạo immutable configuration snapshot rồi thay reference hiện tại một cách nguyên tử. Request đang chạy có thể tiếp tục dùng snapshot cũ, request mới dùng snapshot mới. Cách này tránh đọc một cấu hình bị cập nhật dở dang.

### 16.4. Rollback

Nếu cấu hình mới gây lỗi, hệ thống có thể khôi phục snapshot trước hoặc quay lại profile version đã biết là tốt. Cần lưu version/hash để xác định trạng thái nào được khôi phục.

## 17. Versioning và quản lý profile

Profile thay đổi theo ứng dụng, schema và hạ tầng. Nên quản lý version hoặc revision để biết chính xác cấu hình nào đã được triển khai.

### 17.1. Profile version

Có thể gắn version hoặc revision ID cho profile. Khi schema thay đổi, profile cũ có thể cần migration hoặc được đánh dấu không còn tương thích.

### 17.2. Schema compatibility

Khi đổi tên field, thay kiểu hoặc thay default, cần xem xét các profile hiện có. CI có thể validate toàn bộ profile mẫu theo schema mới để phát hiện lỗi trước khi triển khai.

### 17.3. Immutable release configuration

Đối với deployment quan trọng, nên tạo artifact hoặc snapshot cấu hình bất biến cho một lần release. Thay đổi sau đó tạo revision mới thay vì sửa ngầm nội dung của revision đã triển khai.

### 17.4. Deprecation

Profile hoặc field cũ có thể được đánh dấu deprecated, phát warning và thời hạn loại bỏ. Không nên xóa ngay nếu môi trường đang chạy vẫn phụ thuộc vào chúng.

## 18. Kiểm tra và kiểm thử profile

Profile cần được kiểm tra độc lập và trong tổ hợp cấu hình thực tế.

Các loại kiểm tra hữu ích:

1. Parse và syntax validation của mọi file profile.
2. Schema validation cho từng profile.
3. Kiểm tra profile parent tồn tại và không có inheritance cycle.
4. Kiểm tra conflict giữa nhiều parent hoặc overlay.
5. Resolve tất cả parameter bắt buộc.
6. Kiểm tra secret reference có định dạng và quyền hợp lệ.
7. Validate cross-field constraints.
8. Kiểm tra profile production không chứa cấu hình debug nguy hiểm.
9. Snapshot effective configuration cho từng môi trường.
10. Kiểm tra profile composition hợp lệ.
11. Kiểm thử reload và rollback nếu runtime hỗ trợ.
12. Kiểm tra cùng artifact hoạt động trong các profile mục tiêu.

### 18.1. Unit tests cho merge

Có thể kiểm tra base plus profile tạo effective values như mong đợi. Test cần xác nhận cả giá trị được kế thừa lẫn giá trị bị override.

### 18.2. Profile matrix

Với nhiều chiều như environment, region và tenant, có thể tạo ma trận các tổ hợp được hỗ trợ. Không cần test mọi tổ hợp nếu số lượng lớn; có thể test từng chiều và các tổ hợp quan trọng, đồng thời có validation ngăn tổ hợp bị cấm.

### 18.3. Snapshot tests

Snapshot effective configuration giúp phát hiện thay đổi ngoài ý muốn. Secret cần được redact trước khi snapshot để không ghi credential vào test artifact.

### 18.4. Integration tests

Có thể khởi chạy service với profile test, database tạm và endpoint giả lập để xác nhận ứng dụng thực sự đọc đúng cấu hình và kết nối đúng tài nguyên.

### 18.5. Không dùng dữ liệu production trong test

Test nên dùng secret và dữ liệu riêng. Profile test không được trỏ nhầm đến database hoặc API production.

## 19. Diagnostic cho lỗi profile

Khi profile không hợp lệ, thông báo cần chỉ rõ tên profile, field, nguồn và nguyên nhân.

Ví dụ:

```text
Invalid value for profile "production":
  database.pool.max = "many"
Expected: Integer greater than 0
Source: profiles/production.dsl:12
```

Hoặc:

```text
Cannot resolve required parameter "DATABASE_URL"
Profile: staging
Source: environment parameter declaration
```

Diagnostic hữu ích nên gồm:

- Profile và field liên quan.
- Giá trị mong đợi hoặc constraint bị vi phạm.
- Nguồn cấu hình đã cung cấp giá trị.
- Nguồn nào đã override giá trị trước đó.
- Gợi ý sửa nếu có.

Với secret, không in giá trị thực tế. Với conflict, nên chỉ rõ các nguồn đang đưa ra giá trị khác nhau và policy được áp dụng hoặc còn thiếu.

## 20. Ví dụ tổng hợp: cấu hình ứng dụng theo môi trường

Base profile:

```text
config orderService {
    http.port = 8080
    http.requestTimeout = 30s
    logging.level = INFO
    database.pool.min = 2
    database.pool.max = 20
    security.tlsRequired = true
    features.newCheckout = false
}
```

Development:

```text
profile development extends orderService {
    logging.level = DEBUG
    database.url = "jdbc:postgresql://localhost/orders_dev"
    database.pool.max = 5
    features.newCheckout = true
}
```

Staging:

```text
profile staging extends orderService {
    logging.level = INFO
    database.url = env("STAGING_DATABASE_URL", required = true)
    database.pool.max = 10
    observability.tracing = true
}
```

Production:

```text
profile production extends orderService {
    logging.level = WARN
    database.url = env("DATABASE_URL", required = true)
    database.username = secret("prod/orders/username")
    database.password = secret("prod/orders/password")
    database.pool.max = 80
    features.newCheckout = false
    security.tlsRequired = true
    security.debugEndpoints = false
}
```

Khi kích hoạt production, hệ thống hợp nhất base với profile, resolve database URL và secret reference, chuyển kiểu, rồi validate các ràng buộc. Chỉ sau khi thành công mới tạo effective configuration và khởi động dịch vụ.

### 20.1. Một số invariant của ví dụ

- `http.port` phải nằm trong khoảng 1 đến 65535.
- `database.pool.min` không lớn hơn `database.pool.max`.
- `database.url` phải là URI hợp lệ.
- Production phải bật TLS.
- `security.debugEndpoints` phải false trong production.
- Secret phải đến từ nguồn được phê duyệt.

Nếu một invariant không thỏa, ứng dụng nên từ chối khởi động hoặc deployment pipeline phải dừng trước khi triển khai.

## 21. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Sao chép toàn bộ cấu hình cho từng môi trường | Các giá trị chung dần lệch nhau | Dùng base profile và overlay |
| Không định nghĩa precedence | Giá trị cuối phụ thuộc thứ tự nạp tình cờ | Khai báo thứ tự và policy rõ |
| Dùng development làm default ở production | Dịch vụ có thể chạy debug hoặc dùng tài nguyên sai | Yêu cầu profile production tường minh |
| Ghi secret trực tiếp trong file | Credential có thể bị commit hoặc lộ log | Dùng secret reference và secret store |
| Không validate sau merge | Profile riêng lẻ hợp lệ nhưng kết quả cuối sai | Validate effective configuration |
| Coi absent và null giống nhau | Giá trị bị xóa hoặc giữ ngoài ý muốn | Định nghĩa rõ semantics của missing/null |
| Cho phép override mọi field | Lớp ít tin cậy có thể hạ bảo mật | Field-level policy và protected settings |
| Không phát hiện profile cycle | Resolver có thể lặp vô hạn hoặc kết quả không rõ | Kiểm tra đồ thị kế thừa |
| Quá nhiều profile tổ hợp | Khó hiểu và khó kiểm thử | Composition theo các chiều độc lập |
| Không quản lý version | Không tái tạo được cấu hình đã triển khai | Lưu revision và schema version |
| Reload không nguyên tử | Request có thể đọc cấu hình nửa cũ nửa mới | Snapshot và atomic swap |
| Không theo dõi drift | Runtime khác desired state mà không ai biết | So sánh effective profile với runtime state |

## 22. Nguyên tắc thiết kế profile môi trường cho DSL

Khi thiết kế cơ chế profile, có thể áp dụng các nguyên tắc sau:

1. **Tách base khỏi khác biệt môi trường.** Chỉ override những giá trị thực sự khác.
2. **Dùng tên profile ổn định.** Mô tả rõ mục đích và phạm vi.
3. **Định nghĩa inheritance và overlay.** Quy định chu trình, nhiều parent và precedence.
4. **Kích hoạt tường minh.** Không suy đoán production từ hostname hoặc điều kiện không ổn định.
5. **Phân biệt absent, null và default.** Mỗi trạng thái phải có semantics rõ.
6. **Dùng tham số có kiểu.** Chuyển đổi và validate biến môi trường trước khi runtime sử dụng.
7. **Tham chiếu secret an toàn.** Không lưu credential trực tiếp trong repository.
8. **Validate effective configuration.** Kiểm tra cả field riêng lẻ lẫn invariant giữa nhiều trường.
9. **Bảo vệ trường nhạy cảm.** Không cho overlay ít tin cậy ghi đè chính sách bảo mật.
10. **Giữ provenance.** Có thể biết giá trị cuối đến từ file, profile hay runtime parameter nào.
11. **Quản lý version và drift.** Tái tạo được cấu hình đã triển khai và phát hiện khác biệt.
12. **Thiết kế reload có kiểm soát.** Validate trước, áp dụng nguyên tử và có rollback khi cần.
13. **Kiểm thử profile matrix.** Bao phủ môi trường và các tổ hợp được hỗ trợ.
14. **Giữ artifact và cấu hình tách biệt khi có thể.** Cùng một binary có thể được cấu hình khác nhau khi triển khai.

## 23. Kết luận

Profile môi trường là một tập cấu hình có tên dùng để điều chỉnh ứng dụng theo bối cảnh development, test, staging, production hoặc các chiều triển khai khác. Trong DSL cấu hình, profile thường kết hợp với base configuration, kế thừa và overlay để tránh sao chép toàn bộ thiết lập.

Một hệ thống profile đáng tin cậy cần quy định rõ cách kích hoạt, thứ tự ưu tiên, semantics của giá trị thiếu/null, tham số môi trường, secret reference và validation sau merge. Effective configuration nên có thể xem, truy vết nguồn gốc, version hóa và kiểm thử trước khi ứng dụng hoặc deployment system sử dụng.

Khi profile được quản lý như một phần của hợp đồng triển khai, nhóm có thể dùng cùng artifact qua nhiều môi trường, hạn chế cấu hình sai, bảo vệ credential và tái tạo chính xác trạng thái đã phát hành. Điều quan trọng là mọi khác biệt theo môi trường phải được khai báo có chủ đích, kiểm tra tự động và có thể giải thích.
