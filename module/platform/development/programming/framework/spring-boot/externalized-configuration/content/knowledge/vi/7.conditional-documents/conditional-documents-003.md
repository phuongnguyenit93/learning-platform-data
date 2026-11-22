# Thứ tự xử lý và ghi đè giữa các tài liệu trong cùng tệp

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Tài liệu có điều kiện

## 1. Vấn đề cần giải quyết

Trong Spring Boot, một tệp `application.yml` hoặc `application.properties` có thể chứa **nhiều tài liệu cấu hình (documents)**, được ngăn cách bằng ký hiệu phân tách. Mỗi document mô tả một nhóm thuộc tính và có thể có điều kiện kích hoạt, chẳng hạn một profile hoặc một cloud platform cụ thể.

Một câu hỏi thường gặp là: nếu cùng một khóa được khai báo nhiều lần, Spring Boot lấy giá trị ở đâu? Muốn trả lời, cần xác định **những document nào được kích hoạt**, sau đó mới xét **thứ tự xuất hiện của chúng trong cùng tệp**.

Quy tắc trọng tâm:

> Trong cùng một tệp cấu hình nhiều document, các document được xử lý theo thứ tự từ trên xuống dưới. Khi những document đang có hiệu lực cùng khai báo một khóa, **document xuất hiện sau sẽ ghi đè giá trị của document xuất hiện trước** trong phạm vi nguồn config data của tệp đó.

Đây là quy tắc cấu hình cho **nhiều document**. Nó không nên bị nhầm với cách Java Collections merge, với thứ tự bean khởi tạo, hay với thứ tự ưu tiên giữa mọi nguồn externalized configuration khác nhau.

Sau bài này, bạn có thể:

- Nhận biết ranh giới document trong YAML và properties.
- Xác định document thường trực và document có điều kiện `spring.config.activate.*`.
- Dự đoán kết quả khi document trước và sau cùng khai báo một khóa.
- Phân biệt ghi đè giữa các document trong cùng tệp với ưu tiên giữa các **tệp** hoặc các **nguồn** cấu hình khác nhau.
- Tự kiểm tra cấu hình theo profile, cloud platform và các tình huống trùng khóa.

## 2. Một tệp YAML có nhiều document

### 2.1. Phân tách bằng `---`

Giả sử `src/main/resources/application.yml`:

~~~yaml
app:
  title: "Catalog Service"
  timeout: 10s
  feature-enabled: false

---
app:
  timeout: 20s

---
app:
  feature-enabled: true
~~~

Ba đoạn trên là **ba YAML documents** trong cùng một file. Dòng `---` là dấu phân tách document. Nó không phải một tên thuộc tính, không phải giá trị của `app` và cũng không tạo ba file khác nhau.

Khi cả ba document đều có hiệu lực:

| Khóa | Document 1 | Document 2 | Document 3 | Kết quả |
| --- | --- | --- | --- | --- |
| `app.title` | `Catalog Service` | không khai báo | không khai báo | `Catalog Service` |
| `app.timeout` | `10s` | `20s` | không khai báo | `20s` |
| `app.feature-enabled` | `false` | không khai báo | `true` | `true` |

Document phía sau ghi đè **khóa mà nó khai báo**. Khóa không được khai báo ở các document sau vẫn có thể giữ giá trị từ document trước.

Trong ví dụ này, các document không có `spring.config.activate.*`, nên chúng được xét như các document cấu hình thông thường. Các giá trị cuối cùng vẫn có thể bị nguồn bên ngoài tệp ghi đè, ví dụ biến môi trường hoặc tham số dòng lệnh.

### 2.2. Không phải mọi giá trị đều ghi đè toàn bộ object

Ví dụ:

~~~yaml
service:
  host: "internal.example"
  port: 8080
---
service:
  port: 9090
~~~

Kết quả khi truy cập các property thông thường:

~~~text
service.host = internal.example
service.port = 9090
~~~

Việc document thứ hai khai báo `service.port` không có nghĩa rằng `service.host` tự bị xóa chỉ vì chúng cùng nằm dưới `service` trong YAML. Cơ chế xử lý flatten các khóa đơn giản và tra cứu theo nguồn ưu tiên, chứ không thay nguyên khối một Java object trong lúc đọc YAML.

Tuy nhiên, khi bind các cấu trúc **phức tạp** (nhất là list), quy tắc merge có thể khác với scalar properties; phần sau sẽ phân biệt trường hợp đó.

## 3. Một tệp properties cũng có thể có nhiều document

### 3.1. Ranh giới trong `application.properties`

Spring Boot hỗ trợ phân tách các document logic trong file `.properties` bằng dòng separator đặc biệt. Ví dụ:

~~~properties
app.title=Catalog Service
app.timeout=10s
app.feature-enabled=false

#---
app.timeout=20s

#---
app.feature-enabled=true
~~~

Trong ví dụ `.properties`, `#---` là **dấu phân tách** do Spring Boot nhận biết. Nó khác với một comment thông thường như `# app.timeout=...`.

Để separator được nhận diện, dùng đúng cú pháp độc lập trên một dòng. Trong Spring Boot, separator có thể dùng dạng `#---` hoặc `!---`; không đặt các dòng comment dùng cùng prefix ngay sát separator theo cách làm mất hiệu lực phân tách. Với tài liệu nhiều đoạn, cách trình bày rõ ràng nhất là đặt mỗi `#---` trên dòng riêng, có khoảng trắng hoặc dòng dữ liệu bao quanh khi cần.

Khi cả ba document đều active, kết quả cũng là:

~~~text
app.title = Catalog Service
app.timeout = 20s
app.feature-enabled = true
~~~

**Chú ý:** Một tệp `.properties` nhiều document không giống với việc lặp lại cùng một khóa trong cùng một logical document. Cần phân biệt hai tình huống khi đọc file và khi chẩn đoán kết quả; bài này tập trung vào precedence **giữa các document**.

### 3.2. YAML và properties có cùng ý tưởng precedence

| Tiêu chí | YAML | Properties |
| --- | --- | --- |
| Đuôi file thường gặp | `application.yml`, `application.yaml` | `application.properties` |
| Dấu phân tách document | `---` | `#---` hoặc `!---` |
| Khai báo thuộc tính | Cấu trúc key/value thụt lề | `key=value` |
| Điều kiện kích hoạt document | `spring.config.activate.*` | `spring.config.activate.*` |
| Quy tắc document cùng active | Document sau ghi đè khóa trùng với document trước | Tương tự |

Spring Boot tải các multi-document config files thông qua cơ chế **Config Data** của nó. Không nên mặc định mọi công cụ nạp YAML/properties khác cũng thực hiện cùng cơ chế activation hoặc thứ tự precedence này. Chẳng hạn, các annotation `@PropertySource` và `@TestPropertySource` không hỗ trợ trực tiếp mô hình multi-document property files theo cách Spring Boot config-data loader xử lý.

## 4. Document mặc định và document có điều kiện

### 4.1. Document chỉ kích hoạt với một profile

Một ứng dụng có cấu hình mặc định, sau đó bổ sung giá trị riêng cho `dev` và `prod`:

~~~yaml
# application.yml — document 1: không có điều kiện
app:
  display-name: "Catalog"
  log-detail: false
  endpoint: "https://default.example"

---
# document 2: chỉ áp dụng khi profile dev khớp
spring:
  config:
    activate:
      on-profile: "dev"

app:
  log-detail: true
  endpoint: "http://localhost:8081"

---
# document 3: chỉ áp dụng khi profile prod khớp
spring:
  config:
    activate:
      on-profile: "prod"

app:
  endpoint: "https://catalog.prod.internal"
~~~

Khi khởi động mà không có profile `dev` hay `prod` hoạt động, chỉ document 1 góp các thuộc tính `app.*` của ví dụ.

Khi chạy:

~~~bash
java -jar catalog.jar --spring.profiles.active=dev
~~~

document 2 được kích hoạt, còn document 3 không khớp. Giá trị nhận được là:

~~~text
app.display-name = Catalog
app.log-detail   = true
app.endpoint     = http://localhost:8081
~~~

Khi chạy:

~~~bash
java -jar catalog.jar --spring.profiles.active=prod
~~~

document 3 được kích hoạt. Kết quả:

~~~text
app.display-name = Catalog
app.log-detail   = false
app.endpoint     = https://catalog.prod.internal
~~~

Có hai bước suy luận khác nhau:

1. **Activation:** document nào thỏa điều kiện và được đưa vào tập nguồn cấu hình?
2. **Precedence:** trong những document có hiệu lực ở cùng tệp, khóa trùng sẽ lấy giá trị của document xuất hiện sau.

Điều kiện `on-profile` có thể là một biểu thức profile, không chỉ một tên duy nhất. Vì vậy, không được suy ra rằng file có ba document sẽ luôn áp dụng cả ba; chỉ những document thỏa điều kiện trong môi trường cụ thể mới được dùng.

### 4.2. Hai document cùng thỏa điều kiện

Đây là tình huống thể hiện rõ quy tắc “document sau thắng”:

~~~yaml
app:
  timeout: 5s
  retry-limit: 1

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  timeout: 15s
  retry-limit: 3

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  timeout: 25s
~~~

Với profile `prod` active, cả document 2 và 3 đều thỏa điều kiện. Sau khi xét đúng thứ tự xuất hiện:

~~~text
app.timeout     = 25s
app.retry-limit = 3
~~~

Tại sao? Document 3 ghi đè `app.timeout` vì có cùng khóa với document 2, nhưng không khai báo `app.retry-limit` nên giá trị `3` của document 2 vẫn dùng được.

Nếu profile `prod` không active, hai document có điều kiện không tham gia và ứng dụng thấy giá trị từ document 1 (`5s`, `1`), giả sử không có nguồn cấu hình khác ưu tiên cao hơn.

### 4.3. Nhiều profile hoạt động đồng thời

Giả sử thứ tự document như sau:

~~~yaml
app:
  mode: "default"

---
spring:
  config:
    activate:
      on-profile: "team"

app:
  mode: "team"

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  mode: "production"
~~~

Nếu **cả `team` và `prod` đều active**, cả document 2 và document 3 đều được kích hoạt. Trong phạm vi cùng file này, document 3 nằm sau nên `app.mode` là `production`.

Đừng chỉ dựa vào thứ tự liệt kê profile trên CLI để giải thích xung đột **giữa các document của cùng một file**. Cần nhìn **điều kiện có khớp hay không** và **vị trí document trong file**. Thứ tự profile có thể quan trọng ở các tình huống khác như nguồn file profile-specific, nhưng đó là một cấp precedence khác.

### 4.4. Dùng biểu thức profile có điều kiện kết hợp

Ví dụ:

~~~yaml
app:
  audit-enabled: false

---
spring:
  config:
    activate:
      on-profile: "prod & !maintenance"

app:
  audit-enabled: true
~~~

Document sau chỉ có hiệu lực nếu biểu thức profile `prod & !maintenance` được thỏa. Do đó:

- Active `prod`, không active `maintenance`: document sau tham gia; `app.audit-enabled=true`.
- Active cả `prod` và `maintenance`: điều kiện không khớp; giữ giá trị từ document đầu.
- Chỉ active `dev`: điều kiện không khớp; giữ giá trị từ document đầu.

Biểu thức profile có thể dùng phép phủ định và kết hợp theo cú pháp Spring hỗ trợ. Nên đặt trong dấu nháy YAML để ký tự `!` hoặc toán tử không bị nhầm với cú pháp khác.

## 5. Điều kiện dựa trên cloud platform

Bên cạnh `spring.config.activate.on-profile`, Spring Boot có thể kích hoạt document theo `spring.config.activate.on-cloud-platform`. Ví dụ:

~~~yaml
app:
  storage-path: "./data"
  mode: "local"

---
spring:
  config:
    activate:
      on-cloud-platform: "kubernetes"

app:
  storage-path: "/var/lib/catalog"
  mode: "cluster"
~~~

Document thứ hai chỉ có hiệu lực khi Spring Boot **nhận diện môi trường** là cloud platform tương ứng. Chỉ đặt giá trị `kubernetes` trong YAML không tự biến môi trường đang chạy thành Kubernetes.

Nếu điều kiện khớp, document sau có thể ghi đè:

~~~text
app.storage-path = /var/lib/catalog
app.mode         = cluster
~~~

Nếu điều kiện không khớp, ứng dụng lấy giá trị từ document mặc định, trừ khi có nguồn khác ưu tiên cao hơn.

Một document có thể khai báo cả điều kiện profile và cloud platform; lúc đó các điều kiện của document cần được thỏa theo cơ chế activation tương ứng. Khi chẩn đoán, phải xem **cả trạng thái profile lẫn môi trường cloud**, không suy đoán rằng document hoạt động chỉ vì một điều kiện đã khớp.

## 6. Cách Spring Boot quyết định giá trị cuối cùng

Có thể hình dung quá trình bằng ba pha:

~~~text
Đọc các vị trí config data được cấu hình
             |
             v
Phân chia một file thành các document theo thứ tự xuất hiện
             |
             v
Xét activation của từng document và các import liên quan
             |
             v
Đưa các document có hiệu lực vào cấu hình theo precedence
             |
             v
Giải quyết từng khóa khi Environment / Binder đọc
~~~

Mô hình này giúp suy nghĩ, nhưng **không** có nghĩa toàn bộ xử lý profile, import và location của Boot là một vòng lặp tuyến tính đơn giản; thực tế có nhiều nguồn cấu hình và quy tắc config data riêng.

Trong phạm vi một file và không có import phức tạp, bạn có thể dùng quy trình:

1. Chia file theo separator thành document 1, 2, 3, ...
2. Ghi lại điều kiện `on-profile` hoặc `on-cloud-platform` nếu có.
3. Xác định document nào active trong ngữ cảnh khởi động.
4. Với mỗi key cần xét, đi qua các document đang active theo thứ tự từ đầu đến cuối. Gặp khai báo mới của key thì cập nhật giá trị.
5. Sau khi có giá trị từ file này, tiếp tục xét precedence với **những file, import và property sources khác**.

### 6.1. Bảng dự đoán kết quả

Xét file:

~~~yaml
catalog:
  endpoint: "https://base.example"
  timeout: 4s
  feature-a: false

---
spring:
  config:
    activate:
      on-profile: "dev"

catalog:
  endpoint: "http://localhost:9000"
  feature-a: true

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  endpoint: "https://prod.internal"
  timeout: 12s

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  timeout: 20s
~~~

Bảng kết quả trong phạm vi tệp đó:

| Profile active | `catalog.endpoint` | `catalog.timeout` | `catalog.feature-a` |
| --- | --- | --- | --- |
| Không có `dev` hoặc `prod` | `https://base.example` | `4s` | `false` |
| `dev` | `http://localhost:9000` | `4s` | `true` |
| `prod` | `https://prod.internal` | `20s` | `false` |
| Cả `dev` và `prod` | `https://prod.internal` | `20s` | `true` |

Ở hàng cuối, document `dev` vẫn đóng góp `catalog.feature-a=true` vì các document `prod` ở phía sau không khai báo lại khóa đó. Nhưng `catalog.endpoint` được document `prod` ghi đè và `catalog.timeout` được document `prod` cuối ghi đè thêm một lần.

Bảng mô tả **kết quả trong cùng file**, chưa xét tác động của `application-prod.yml` bên ngoài file này, biến môi trường, CLI, các imports hoặc property sources tùy chỉnh.

## 7. Không nhầm precedence giữa document với precedence giữa file

Trong Spring Boot có nhiều mức cấu hình:

- Nhiều document trong một file `application.yml`.
- Nhiều file config data: `application.yml`, `application-prod.yml`, bản trên classpath hoặc ngoài filesystem.
- Nhiều vị trí tìm kiếm và nhiều nhóm vị trí do `spring.config.location` / `spring.config.additional-location` quy định.
- Các nguồn ngoài config data: OS environment variables, Java system properties, JSON config, command-line arguments và những nguồn khác.

**Document sau thắng document trước** là quy tắc **trong cùng file**. Không được mở rộng thành “dòng xuất hiện cuối cùng trong mọi file luôn thắng”.

### 7.1. Ví dụ file mặc định và file theo profile

Giả sử:

~~~text
src/main/resources/
├── application.yml
└── application-prod.yml
~~~

`application.yml`:

~~~yaml
catalog:
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  timeout: 10s
~~~

`application-prod.yml`:

~~~yaml
catalog:
  timeout: 30s
~~~

Khi profile `prod` active và cả hai file đều được nạp theo thứ tự location mặc định, file `application-prod.yml` là một nguồn profile-specific có thể có ưu tiên cao hơn dữ liệu tương ứng từ `application.yml`. Giá trị cuối cùng trong ví dụ thông thường là `30s`, **không phải** `10s` chỉ vì document có điều kiện ở file đầu được viết sau.

Nếu có file ngoài JAR như `./config/application-prod.yml`, kết quả còn phụ thuộc thứ tự và nhóm vị trí bên ngoài/inside cùng các quy tắc profile-specific config data.

### 7.2. Ví dụ tham số dòng lệnh thắng tất cả document trong file

Vẫn `application.yml` đa document:

~~~yaml
catalog:
  timeout: 5s
---
spring:
  config:
    activate:
      on-profile: "prod"
catalog:
  timeout: 10s
~~~

Khi chạy:

~~~bash
java -jar catalog.jar \
  --spring.profiles.active=prod \
  --catalog.timeout=60s
~~~

`catalog.timeout` thường là `60s` nhờ ưu tiên của command-line arguments trong cơ chế cấu hình mặc định của Boot. Document sau có thể thắng document trước **trong file**, nhưng không tự thắng mọi nguồn có precedence cao hơn.

Tương tự, Java system properties hoặc biến môi trường có thể ghi đè config data; nguồn thực tế được chọn phụ thuộc vào key, môi trường và cấu hình của ứng dụng.

### 7.3. Import là một cấp precedence khác

Document có thể khai báo:

~~~yaml
spring:
  config:
    import: "optional:file:./config/overrides.yml"

catalog:
  timeout: 5s
~~~

Spring Boot xem nội dung được `spring.config.import` nhập như các tài liệu cấu hình bổ sung. Import có quy tắc precedence riêng: tài liệu import thường có ưu tiên cao hơn document khai báo import, và thứ tự nhiều import cũng quan trọng.

Không thể quyết định giá trị cuối cùng chỉ bằng vị trí YAML document trong file gốc **nếu đang có config imports**. Khi cần xử lý trường hợp này, hãy xác định các tài liệu được import, vị trí của chúng và thứ tự precedence thực tế.

## 8. Ghi đè scalar, map và list: điểm cần phân biệt

### 8.1. Scalar values: khóa sau ghi đè khóa trước

~~~yaml
app:
  mode: basic
---
app:
  mode: advanced
~~~

Kết quả: `app.mode=advanced` khi cả hai document được nạp. Đây là ví dụ trực tiếp nhất của quy tắc document sau thắng.

### 8.2. Map: các entry có thể kết hợp theo tên khóa

Ví dụ bind qua `@ConfigurationProperties`:

~~~yaml
catalog:
  headers:
    source: default
    region: global

---
catalog:
  headers:
    region: asia
    channel: mobile
~~~

Với một cấu trúc map thông thường, các entry có thể được hợp nhất theo từng key từ nhiều property source, và khóa trùng lấy giá trị theo precedence:

~~~text
catalog.headers.source  = default
catalog.headers.region  = asia
catalog.headers.channel = mobile
~~~

Không nên diễn giải “document sau có `headers`” thành “toàn bộ các entry trong map trước đều bị xóa”. Binding map thường có semantics kết hợp các key.

### 8.3. List: thường bị thay thế khi binding

Trường hợp list rất dễ gây nhầm lẫn:

~~~yaml
catalog:
  servers:
    - "a.internal"
    - "b.internal"

---
catalog:
  servers:
    - "c.internal"
~~~

Khi bind `catalog.servers` vào `List<String>` qua `@ConfigurationProperties`, Spring Boot áp dụng quy tắc binding list: **list của nguồn ưu tiên cao được dùng thay cho list của nguồn ưu tiên thấp**, không mặc định nối `a,b` với `c`. Trong trường hợp này, kết quả thường là list chứa `c.internal`.

Điều này khác với cách đọc từng scalar property. Cần phân biệt **precedence giữa property sources** với **semantics của Binder cho loại dữ liệu**. Không suy ra rằng mọi kiểu collection đều merge theo cùng một cách.

### 8.4. Giá trị rỗng và `null`

Một document phía sau có thể khai báo một giá trị rỗng, hoặc YAML `null`. Nhưng điều đó không đồng nghĩa mọi API và mọi kiểu binder sẽ hành xử như thao tác “xóa hoàn toàn key” khỏi các nguồn thấp hơn.

Đặc biệt, YAML `null` được xử lý theo quy tắc của nguồn cấu hình; không nên dựa vào nó như một công cụ chắc chắn để ghi đè giá trị từ property source ưu tiên thấp bằng null. Nếu muốn tắt một tính năng, hãy thiết kế khóa rõ ràng như `feature.enabled=false`; nếu muốn xóa một phần tử collection, hãy xem xét semantics binder và chỉnh cấu hình nguồn cao hơn cho phù hợp.

## 9. Ví dụ riêng cho `application.properties` có document điều kiện

Giả sử `application.properties` chứa:

~~~properties
app.name=Invoices
app.cache.enabled=false
app.worker.threads=2

#---
spring.config.activate.on-profile=dev
app.cache.enabled=false
app.worker.threads=1

#---
spring.config.activate.on-profile=prod
app.cache.enabled=true
app.worker.threads=6

#---
spring.config.activate.on-profile=prod
app.worker.threads=8
~~~

Khi profile `dev` active, document 2 được thêm vào cùng document mặc định, dẫn tới:

~~~text
app.name = Invoices
app.cache.enabled = false
app.worker.threads = 1
~~~

Khi profile `prod` active, document 3 và 4 cùng có hiệu lực:

~~~text
app.name = Invoices
app.cache.enabled = true
app.worker.threads = 8
~~~

Document 4 chỉ có `app.worker.threads`, nên không xóa hoặc thay `app.name` và `app.cache.enabled`. Ví dụ này có nguyên tắc giống YAML, chỉ khác dấu phân tách và cú pháp khai báo key.

Khi cần ghi file `.properties` trong IDE, bảo đảm serializer hoặc formatter không đổi `#---` thành cú pháp comment khác khiến Spring Boot không nhận diện ranh giới. Nếu một tool xử lý file mà chỉ hiểu Java Properties chuẩn, có thể nó không bảo toàn semantics của multi-document Boot.

## 10. Những giới hạn quan trọng của activation

### 10.1. `spring.config.activate.on-profile` không phải `spring.profiles.active`

- `spring.profiles.active` dùng để **chọn những profile nào hoạt động**.
- `spring.config.activate.on-profile` dùng để **xác định document hiện tại có được đưa vào config data hay không** dựa trên profile đang hoạt động.

Ví dụ hợp lệ về ý tưởng:

~~~yaml
catalog:
  mode: default

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  mode: production
~~~

Profile `prod` có thể được chọn bằng tham số dòng lệnh:

~~~bash
java -jar catalog.jar --spring.profiles.active=prod
~~~

Không viết `spring.profiles.active=prod` ngay bên trong một document được kích hoạt bằng `spring.config.activate.on-profile` rồi dựa vào document đó để tự kích hoạt chính nó. Spring Boot giới hạn các thuộc tính chọn profile như `spring.profiles.active` / `spring.profiles.default` trong profile-specific documents hoặc documents có điều kiện `on-profile` để tránh logic kích hoạt vòng tròn, khó dự đoán.

### 10.2. Điều kiện chưa khớp nghĩa là document không đóng góp khóa

Ví dụ:

~~~yaml
app:
  audit: false

---
spring:
  config:
    activate:
      on-profile: "qa"

app:
  audit: true
  endpoint: "https://qa.internal"
~~~

Khi `qa` không active, document 2 không đóng góp `app.audit` hoặc `app.endpoint`. Ứng dụng vẫn có thể có `app.endpoint` từ một nguồn khác; nếu không, tra cứu có thể trả về null hoặc bị lỗi nếu dùng cơ chế yêu cầu khóa bắt buộc.

Nội dung document không active không “được tải rồi chờ override”: nó không đóng góp các thuộc tính của document đó vào `Environment` cho tình huống khởi động đang xét.

### 10.3. Document có điều kiện theo môi trường cloud

~~~yaml
app:
  proxy-required: false

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  proxy-required: true
~~~

Nếu Spring Boot không phát hiện Kubernetes, document sau không có hiệu lực. Nếu có, document sau có thể ghi đè `app.proxy-required` thành `true`. Cần kiểm tra cách Spring Boot nhận diện cloud platform trong môi trường cụ thể, không giả định container Docker bất kỳ cũng được tính là Kubernetes.

## 11. Quan sát giá trị được giải quyết trong ứng dụng

Trong ứng dụng Spring Boot, sử dụng `Environment` để đọc giá trị:

~~~java
package com.example.catalog;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CatalogDiagnostics {

    private final Environment environment;

    public CatalogDiagnostics(Environment environment) {
        this.environment = environment;
    }

    public void printResolvedTimeout() {
        String value = environment.getProperty("catalog.timeout");
        System.out.println("catalog.timeout = " + value);
    }
}
~~~

Khi cần binding có kiểu:

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        Duration timeout,
        boolean featureEnabled
) {}
~~~

Bật `@ConfigurationPropertiesScan` trên một lớp cấu hình hoặc đăng ký `CatalogProperties` bằng cơ chế thích hợp, sau đó inject vào service. Với file:

~~~yaml
catalog:
  timeout: 5s
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  timeout: 20s
~~~

ở profile `prod`, bean thường nhận `timeout=20s` và `featureEnabled=false`, giả sử không có nguồn ưu tiên cao hơn.

### 11.1. Xem thứ tự PropertySource để chẩn đoán

`ConfigurableEnvironment` cung cấp các `PropertySource` theo thứ tự ưu tiên. Với một **khóa thử nghiệm không nhạy cảm**, có thể quan sát nguồn nào cung cấp giá trị:

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigOrderProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigOrderProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.timeout";

        System.out.println("Resolved: " + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

Điều này cho phép thấy cả document, file hoặc property source có liên quan, tùy cách Spring Boot biểu diễn nguồn đã nạp. Tuy nhiên, tên hoặc định dạng nguồn có thể thay đổi theo phiên bản Spring Boot và cấu trúc ứng dụng; không nên viết logic nghiệp vụ phụ thuộc vào string tên `PropertySource`.

Không chạy đoạn log này với mật khẩu, token, private key hay các property nhạy cảm. Khi sử dụng Spring Boot Actuator `env` và `configprops`, cần bảo vệ endpoint và cấu hình hiển thị an toàn vì chúng có thể chứa thông tin môi trường nhạy cảm.

### 11.2. Không dùng `@Value` để suy ra thứ tự document

`@Value("${catalog.timeout}")` chỉ cho biết **giá trị cuối** sau khi Spring giải quyết property. Nó không chỉ ra document nào cung cấp giá trị. Muốn điều tra nguồn, dùng cơ chế origin tracking/diagnostics của Spring Boot và xem đúng các source được nạp.

## 12. Cách tự xác định kết quả theo từng profile

Cho `application.yml`:

~~~yaml
catalog:
  client:
    connect-timeout: 3s
    read-timeout: 10s
  show-details: false

---
spring:
  config:
    activate:
      on-profile: "dev"

catalog:
  client:
    read-timeout: 30s
  show-details: true

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  client:
    connect-timeout: 1s
    read-timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod & blue"

catalog:
  client:
    read-timeout: 7s
~~~

Có thể suy luận:

| Profiles active | connect-timeout | read-timeout | show-details |
| --- | --- | --- | --- |
| `dev` | `3s` | `30s` | `true` |
| `prod` | `1s` | `5s` | `false` |
| `prod,blue` | `1s` | `7s` | `false` |
| `dev,prod` | `1s` | `5s` | `true` |
| Không có các profile trên | `3s` | `10s` | `false` |

Để giải thích `prod,blue`, document 2 không khớp, document 3 khớp, document 4 cũng khớp và xuất hiện sau document 3, nên `read-timeout` từ `5s` thành `7s`. Trong khi đó `connect-timeout` vẫn lấy từ document 3.

Với `dev,prod`, document 2 và 3 đều active; document 3 xuất hiện sau nên ghi đè `read-timeout` của document 2, còn `show-details` không được khai báo lại nên vẫn là `true`.

Bài tập này cố ý chỉ xét các document trong tệp nêu trên. Trong một ứng dụng thực tế, tệp theo profile, import, environment variables hoặc tham số CLI có thể thay đổi kết quả cuối.

## 13. Các lỗi hiểu sai thường gặp

| Nhầm lẫn | Điều cần hiểu |
| --- | --- |
| “Document cuối luôn thắng mọi khóa.” | Chỉ ghi đè những **khóa trùng** và chỉ khi document đó **active**; các khóa khác có thể đến từ document trước |
| “Có profile `prod` thì mọi document đều active.” | Chỉ document không có điều kiện hoặc thỏa điều kiện tương ứng được áp dụng |
| “Document cuối trong `application.yml` luôn thắng `application-prod.yml`.” | Phải xét precedence của **các file config data** và profile-specific sources |
| “Đặt `spring.profiles.active` trong document đang chờ profile kích hoạt sẽ tự bật document đó.” | Chọn profile và kích hoạt document là hai bước khác nhau; cách đặt này bị giới hạn/không hợp lệ |
| “Hai document khai báo map thì map sau xóa mọi key trước.” | Binding map có thể kết hợp các entry theo key với precedence |
| “Hai document khai báo list thì hai list được nối lại.” | Binding list thường thay thế cả list theo nguồn ưu tiên cao |
| “Dấu `---` trong properties có nghĩa giống YAML.” | Với Boot properties, dùng separator `#---` hoặc `!---`, không dùng nguyên dòng YAML `---` |
| “Kết quả `@Value` cho biết document nguồn.” | `@Value` trả giá trị đã resolve; muốn biết nguồn cần xem property sources/origin |
| “Document không active có thể cung cấp fallback.” | Một document không được kích hoạt không góp khóa vào `Environment` cho lần khởi động đó |

## 14. Bài tập thực hành

### Bài tập A: ưu tiên giữa ba document YAML

Tạo `application.yml`:

~~~yaml
lesson:
  color: "gray"
  page-size: 10
---
lesson:
  color: "blue"
---
lesson:
  page-size: 50
~~~

Dự đoán `lesson.color` và `lesson.page-size`. Sau đó đọc bằng `Environment`. Khi cả ba document active, kết quả là `blue` và `50`.

### Bài tập B: profile điều kiện xuất hiện nhiều lần

Tạo tệp:

~~~yaml
lesson:
  status: "base"
  timeout: 1s

---
spring:
  config:
    activate:
      on-profile: "prod"

lesson:
  status: "primary"
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod"

lesson:
  timeout: 9s
~~~

Chạy lần lượt không có profile `prod` và có `--spring.profiles.active=prod`. Khi `prod` active, `lesson.status=primary` và `lesson.timeout=9s`. Khi không active, lấy `base` và `1s`.

### Bài tập C: YAML và properties

Chuyển ví dụ ở bài tập B sang `application.properties`, dùng `#---` để phân tách documents và `spring.config.activate.on-profile=prod` để đặt điều kiện. Chạy với hai trạng thái profile và so sánh kết quả.

### Bài tập D: precedence của file khác

Tạo `application-prod.yml` riêng, đặt `lesson.timeout=30s`. Chạy profile `prod` và xem nó ảnh hưởng thế nào so với document `prod` trong `application.yml`. Tiếp theo chạy thêm tham số `--lesson.timeout=45s` để quan sát precedence của command-line argument. Mục tiêu là nhận ra có **hai tầng quyết định**: thứ tự trong file và thứ tự giữa các nguồn.

### Bài tập E: danh sách và map

Tạo một `application.yml` đa document, trong đó:

- Document đầu có `lesson.tags` gồm hai phần tử và `lesson.labels.a`, `lesson.labels.b`.
- Document sau chỉ có `lesson.tags` gồm một phần tử và `lesson.labels.b`, `lesson.labels.c`.
- Bind vào một `@ConfigurationProperties` class có `List<String> tags` và `Map<String,String> labels`.

Quan sát rằng kết quả binding list khác với cơ chế kết hợp map theo entry; không mặc định nối hai list như cách merge hai tập hợp.

## 15. Checklist khi chẩn đoán cấu hình trùng khóa

Khi Spring Boot trả giá trị bất ngờ cho `some.property`:

1. **Tìm đúng file config data.** Ứng dụng có đang nạp file trên classpath, file bên ngoài JAR, file theo profile hay file import không?
2. **Chia file thành document.** Đọc đúng `---` trong YAML hoặc `#---`/`!---` trong properties.
3. **Xem điều kiện activation.** Kiểm tra `on-profile`, `on-cloud-platform` và trạng thái môi trường thực tế.
4. **Đi theo thứ tự document.** Chỉ xét document active, ghi lại lần khai báo cuối cùng của khóa trong file.
5. **Xem các nguồn khác.** Có `application-prod.yml`, import, biến môi trường, system properties hoặc CLI nào ghi đè không?
6. **Xem kiểu dữ liệu đích.** Scalar, map và list có semantics binding khác nhau.
7. **Quan sát tại runtime.** Đọc `Environment`, xem tên `PropertySource` hoặc metadata origin nếu cần và bảo đảm không lộ giá trị bí mật.

Điều quan trọng là dùng **cùng một lần khởi động, cùng profile và cùng thứ tự config data** khi đối chiếu dự đoán với kết quả. Chỉ thay đổi một yếu tố mỗi lần để tránh nhầm nguyên nhân.

## 16. Ghi nhớ

- Multi-document YAML phân tách bằng `---`; multi-document properties dùng `#---` hoặc `!---`.
- Spring Boot xử lý các document theo thứ tự xuất hiện; **document sau được kích hoạt sẽ ghi đè key trùng** từ document trước trong cùng file.
- Document không thỏa `spring.config.activate.on-profile` hoặc `spring.config.activate.on-cloud-platform` không đóng góp các key của nó.
- “Document sau thắng” là quy tắc một **tầng precedence**; các file profile-specific, vị trí ngoài JAR, imports và các property sources khác vẫn ảnh hưởng kết quả cuối.
- Với scalar/map/list, xem cả cơ chế ghi đè property lẫn quy tắc binding của kiểu dữ liệu.
- Muốn chẩn đoán, xác định document active trước, rồi xét thứ tự, sau đó xem nguồn cấu hình có ưu tiên cao hơn.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): đa document YAML/properties, activation, import và precedence.
- [Spring Boot Reference — Working With Multi-Document Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.multi-document): cú pháp separator và thứ tự document.
- [Spring Boot Reference — Activation Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.activation-properties): `on-profile` và `on-cloud-platform`.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): cách binder xử lý dữ liệu có cấu trúc.
