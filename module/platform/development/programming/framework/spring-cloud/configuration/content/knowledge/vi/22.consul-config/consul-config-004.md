# Giá trị KV rời so với khối YAML hoặc properties

Consul KV có thể lưu cấu hình theo hai cách phổ biến khi tích hợp Spring Cloud Consul Config: lưu từng thuộc tính thành một cặp key/value riêng, hoặc lưu cả tài liệu YAML/PROPERTIES trong một KV entry. Hai cách cùng dùng Consul làm nơi lưu trữ, nhưng khác nhau về cách tổ chức key, cách chỉnh sửa, phạm vi cập nhật và khả năng review thay đổi.

Với **KEY_VALUE**, mỗi thuộc tính có một key riêng trong Consul. Với **YAML** hoặc **PROPERTIES**, một key chứa toàn bộ nội dung của tài liệu cấu hình cho một context. Chọn đúng format giúp cấu hình dễ quản lý, tránh ghi đè ngoài ý muốn và làm rõ cách Spring Cloud Config Client phân giải application, profile và giá trị cuối cùng.

## 1. Consul KV trong Spring Cloud Consul Config

Spring Cloud Consul Config cho phép ứng dụng Spring Boot đọc cấu hình từ Consul Key/Value store. Các giá trị được tổ chức dưới những prefix/context để phân biệt cấu hình dùng chung, cấu hình theo ứng dụng và cấu hình theo profile.

Một số thuộc tính định vị thường dùng:

| Thuộc tính | Vai trò |
|---|---|
| `spring.cloud.consul.host` | Hostname hoặc địa chỉ Consul agent/server. |
| `spring.cloud.consul.port` | Cổng HTTP API của Consul, thường là `8500` trong cấu hình mặc định. |
| `spring.cloud.consul.config.enabled` | Bật/tắt tích hợp Consul Config. |
| `spring.cloud.consul.config.prefix` | Prefix gốc của vùng cấu hình, mặc định thường là `config`. |
| `spring.cloud.consul.config.default-context` | Context dùng chung, mặc định thường là `application`. |
| `spring.cloud.consul.config.profile-separator` | Ký tự phân cách tên context và profile, mặc định thường là dấu phẩy. |
| `spring.cloud.consul.config.format` | Cách diễn giải dữ liệu: `KEY_VALUE`, `YAML`, `PROPERTIES` hoặc `FILES`. |
| `spring.cloud.consul.config.data-key` | Tên key chứa nội dung tài liệu trong format dạng block, mặc định thường là `data`. |

Ví dụ cấu hình client:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "consul:"
  cloud:
    consul:
      host: consul.internal
      port: 8500
      config:
        enabled: true
        prefix: config
        default-context: application
        profile-separator: ","
        format: KEY_VALUE
```

Ví dụ dùng Config Data API. Ứng dụng cũ có thể dùng bootstrap context tùy phiên bản Spring Cloud Consul; không trộn hai cơ chế nạp cấu hình nếu chưa xác nhận thứ tự và hành vi của release train đang dùng.

## 2. Cách tổ chức context theo application và profile

Giả sử client có:

```yaml
spring:
  application:
    name: orders-service
```

và đang chạy profile `prod`. Với prefix `config`, default context `application` và profile separator `,`, các context thường gặp gồm:

```text
config/application
config/application,prod
config/orders-service
config/orders-service,prod
```

Ý nghĩa:

- `config/application`: cấu hình mặc định dùng chung.
- `config/application,prod`: cấu hình dùng chung cho profile `prod`.
- `config/orders-service`: cấu hình mặc định riêng cho `orders-service`.
- `config/orders-service,prod`: cấu hình riêng của `orders-service` trong profile `prod`.

Spring Cloud Consul Config đọc các context phù hợp và đưa chúng vào Environment dưới dạng property source. Thứ tự ưu tiên chính xác cần được xác nhận theo phiên bản và cấu hình context đang dùng; không chỉ dựa vào thứ tự nhìn thấy trong Consul UI. Khi có khóa trùng nhau, hãy kiểm tra Environment/PropertySources của client để xác định nguồn thắng.

## 3. Format KEY_VALUE: mỗi thuộc tính là một KV entry

Với `format: KEY_VALUE`, mỗi thuộc tính được lưu thành một cặp key/value riêng dưới context. Ví dụ context `orders-service,prod`:

```text
config/
└── orders-service,prod/
    ├── app.payment.endpoint = https://payments.internal
    ├── app.payment.timeout = 3s
    ├── app.retry.max-attempts = 4
    └── logging.level.root = INFO
```

Một số key có thể được ghi bằng Consul CLI:

```bash
consul kv put config/orders-service,prod/app.payment.endpoint https://payments.internal
consul kv put config/orders-service,prod/app.payment.timeout 3s
consul kv put config/orders-service,prod/app.retry.max-attempts 4
consul kv put config/orders-service,prod/logging.level.root INFO
```

Trong ví dụ, path sau context là tên property và value là nội dung của thuộc tính. Cần giữ quy ước key nhất quán, đặc biệt với dấu chấm, dấu gạch nối và tên property lồng nhau. Cách ánh xạ key path thành property name phụ thuộc Spring Cloud Consul Config; nên kiểm tra Environment API khi dùng key có dấu `/` hoặc cấu trúc phân cấp.

### Ưu điểm của KEY_VALUE

- Có thể cập nhật một thuộc tính mà không phải ghi lại toàn bộ tài liệu cấu hình.
- Dễ quản lý quyền theo prefix/key nếu ACL được thiết kế phù hợp.
- Phù hợp với tập thuộc tính nhỏ, độc lập hoặc được cập nhật thường xuyên.
- Dễ xem giá trị từng key trong Consul UI và thao tác bằng CLI/API.

### Giới hạn của KEY_VALUE

- Số lượng KV entry tăng theo số thuộc tính.
- Cấu hình có cấu trúc lồng nhau phải được biểu diễn bằng quy ước key riêng.
- Một thay đổi gồm nhiều key có thể được quan sát ở các thời điểm khác nhau nếu ghi từng key riêng lẻ.
- Khó review một thay đổi lớn như một tài liệu hoàn chỉnh nếu không có quy trình export/versioning riêng.

## 4. Format YAML: lưu cả tài liệu trong một key

Với `format: YAML`, Spring Cloud Consul Config đọc nội dung YAML từ một KV entry trong context. Tên key chứa tài liệu được cấu hình bằng `data-key`, mặc định thường là `data`.

Ví dụ cấu hình client:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "consul:"
  cloud:
    consul:
      config:
        prefix: config
        default-context: application
        format: YAML
        data-key: data
```

Consul KV có thể được tổ chức như sau:

```text
config/
└── orders-service,prod/
    └── data = "app:\n  payment:\n    timeout: 3s\n..."
```

Giá trị của key `config/orders-service,prod/data` là toàn bộ tài liệu:

```yaml
app:
  payment:
    endpoint: https://payments.internal
    timeout: 3s
  retry:
    max-attempts: 4

logging:
  level:
    root: INFO
```

Có thể ghi nội dung từ file bằng Consul CLI:

```bash
consul kv put config/orders-service,prod/data @orders-service-prod.yml
```

Hoặc dùng HTTP API với body là nội dung YAML:

```bash
curl --request PUT \
  --data-binary @orders-service-prod.yml \
  http://localhost:8500/v1/kv/config/orders-service,prod/data
```

Với YAML block, cấu trúc lồng nhau được giữ nguyên và dễ đọc như file `application.yml` quen thuộc. Một lần cập nhật key `data` thay thế toàn bộ tài liệu ở context đó; vì vậy, nếu chỉ sửa một thuộc tính, cần gửi lại tài liệu đầy đủ để không vô tình xóa các thuộc tính khác.

## 5. Format PROPERTIES: lưu cả nội dung properties trong một key

`PROPERTIES` cũng lưu tài liệu trong một KV entry, nhưng nội dung theo cú pháp Java properties:

```properties
app.payment.endpoint=https://payments.internal
app.payment.timeout=3s
app.retry.max-attempts=4
logging.level.root=INFO
```

Ví dụ cấu hình:

```yaml
spring:
  cloud:
    consul:
      config:
        format: PROPERTIES
        data-key: data
```

Context Consul:

```text
config/orders-service,prod/data = "app.payment.endpoint=https://payments.internal\napp.payment.timeout=3s\n..."
```

Có thể ghi file properties bằng:

```bash
consul kv put config/orders-service,prod/data @orders-service-prod.properties
```

Properties block phù hợp khi nhóm đã dùng cú pháp `.properties`, muốn cấu trúc phẳng hoặc cần tương thích với quy trình quản lý file hiện có. YAML thường dễ đọc hơn khi cấu hình có nhiều object lồng nhau; properties thường rõ ràng với các khóa phẳng.

## 6. So sánh KV rời và block YAML/PROPERTIES

| Tiêu chí | KEY_VALUE rời | YAML block | PROPERTIES block |
|---|---|---|---|
| Đơn vị lưu trữ | Một entry cho mỗi thuộc tính. | Một entry cho cả tài liệu YAML. | Một entry cho cả tài liệu properties. |
| Cấu trúc | Key/value riêng, thường dùng tên property làm key. | Hỗ trợ cấu trúc lồng nhau. | Cấu trúc phẳng bằng tên property đầy đủ. |
| Sửa một thuộc tính | Ghi đúng entry tương ứng. | Đọc/sửa/ghi lại toàn bộ block. | Đọc/sửa/ghi lại toàn bộ block. |
| Cập nhật nhiều thuộc tính | Nhiều thao tác nếu không dùng transaction. | Một lần ghi thay toàn bộ tài liệu. | Một lần ghi thay toàn bộ tài liệu. |
| Review | Từng key dễ xem; thay đổi nhiều key cần gom lại để review. | Diff toàn bộ tài liệu rõ ràng nếu lưu file trong Git. | Diff toàn bộ tài liệu rõ ràng nếu lưu file trong Git. |
| Phù hợp | Thuộc tính độc lập, cập nhật riêng lẻ. | Cấu hình có cấu trúc, nhiều nhóm thuộc tính. | Cấu hình phẳng hoặc hệ thống đã chuẩn hóa `.properties`. |
| Rủi ro | Cập nhật từng key có thể tạo trạng thái trung gian. | Ghi đè block có thể làm mất key nếu dùng bản tài liệu cũ. | Tương tự YAML block; cần tránh ghi đè toàn bộ bằng bản cũ. |

Không có format nào luôn tốt hơn. Chọn theo cách nhóm vận hành cập nhật và review cấu hình, số lượng thuộc tính, mức độ liên quan giữa các khóa và nhu cầu cập nhật nguyên tử.

## 7. Tính nhất quán khi cập nhật nhiều giá trị

Giả sử một lần phát hành cần đổi đồng thời endpoint và timeout:

```text
app.payment.endpoint
app.payment.timeout
```

Với KEY_VALUE, nếu ghi hai entry bằng hai lệnh riêng, client hoặc watcher có thể quan sát trạng thái trung gian: endpoint mới nhưng timeout cũ, hoặc ngược lại. Nếu hai thuộc tính phải thay đổi cùng nhau, cần một cách ghi có tính nguyên tử được Consul hỗ trợ và được client/version tích hợp sử dụng đúng, hoặc dùng một block tài liệu để thay đổi trong một KV write.

Với YAML/PROPERTIES block, cả tài liệu nằm trong một KV entry. Một lần PUT thay thế giá trị của entry đó, nên các thuộc tính trong block được cập nhật cùng một thao tác lưu trữ. Tuy nhiên, điều này không làm cho toàn bộ nhiều context khác nhau trở thành một giao dịch duy nhất; nếu cần thay đổi đồng bộ giữa `application` và `orders-service`, vẫn cần quy trình phát hành và kiểm tra rõ ràng.

Consul có hỗ trợ transaction API cho một số thao tác KV, nhưng transaction có giới hạn về số thao tác và điều kiện. Nếu dùng, hãy kiểm tra khả năng của phiên bản Consul và API client, đồng thời thiết kế xử lý lỗi khi transaction bị từ chối. Không giả định nhiều lệnh CLI riêng lẻ tự động được gom thành một transaction.

## 8. Application, profile và nhiều context với từng format

Cả KEY_VALUE và block format đều sử dụng context theo application/profile. Khác biệt chỉ nằm ở cách lưu nội dung bên trong mỗi context.

Ví dụ với `orders-service` và profile `prod`:

**KEY_VALUE**

```text
config/application/app.region = ap-southeast-1
config/application,prod/logging.level.root = INFO
config/orders-service/app.retry.max-attempts = 3
config/orders-service,prod/app.payment.timeout = 3s
```

**YAML block**

```text
config/application/data = <YAML dùng chung>
config/application,prod/data = <YAML dùng chung cho prod>
config/orders-service/data = <YAML riêng orders>
config/orders-service,prod/data = <YAML riêng orders-prod>
```

Trong cả hai trường hợp, client yêu cầu application và profile theo cấu hình Spring Boot. Context mặc định và context theo profile được đọc theo quy tắc của Spring Cloud Consul Config. Nếu nhiều context có cùng property, cần kiểm tra property source order và giá trị cuối ở phía client.

Khi dùng nhiều profile, `profile-separator` quyết định cách tạo context profile. Nếu thay separator, phải cập nhật layout Consul đồng bộ; nếu không, client có thể không tìm thấy context dù KV entry vẫn tồn tại.

## 9. Cấu hình watch và áp dụng thay đổi

Spring Cloud Consul Config có cơ chế watch để phát hiện thay đổi trong context. Ví dụ:

```yaml
spring:
  cloud:
    consul:
      config:
        watch:
          enabled: true
          delay: 1000
          wait-time: 55
        reload:
          enabled: true
          strategy: REFRESH
```

Các tùy chọn watch/reload và giá trị mặc định có thể thay đổi theo phiên bản Spring Cloud Consul. Cần kiểm tra reference documentation của release train đang dùng. Watch phát hiện thay đổi không đồng nghĩa mọi bean hay hạ tầng đều tự cập nhật; reload strategy cần được bật/cấu hình phù hợp và các bean phải hỗ trợ refresh.

Với KEY_VALUE, thay đổi một entry có thể kích hoạt watch cho context tương ứng. Với YAML/PROPERTIES, thay đổi nội dung `data` cũng là một thay đổi KV của context. Nếu ứng dụng không tự áp dụng thay đổi, có thể cần endpoint refresh, Spring Cloud Bus hoặc restart tùy kiến trúc và loại thuộc tính.

Nhớ phân biệt:

- **Watch:** phát hiện Consul KV đã thay đổi.
- **Reload/refresh:** yêu cầu Spring nạp lại hoặc cập nhật cấu hình.
- **Restart:** tạo lại application context và tài nguyên chỉ được khởi tạo lúc startup.

## 10. Quyền truy cập và bảo vệ dữ liệu

Consul KV là kho key/value cấu hình, không nên mặc định xem mọi dữ liệu lưu trong đó đã được bảo vệ như một secret manager chuyên dụng. Hãy bật Consul ACL, giới hạn token theo prefix/application và dùng TLS cho kết nối giữa ứng dụng với Consul.

Ví dụ policy ACL theo prefix:

```hcl
key_prefix "config/orders-service/" {
  policy = "read"
}

key_prefix "config/orders-service,prod/" {
  policy = "read"
}
```

Đây là ví dụ định hướng; cú pháp policy và cách tổ chức prefix phải được kiểm tra theo phiên bản Consul và layout thực tế. Tách token đọc runtime khỏi token ghi cấu hình. Chỉ pipeline phát hành hoặc operator được cấp quyền write.

Với dữ liệu nhạy cảm như mật khẩu database, API token hoặc private key, ưu tiên Vault hoặc secret manager chuyên dụng. Nếu vẫn lưu giá trị nhạy cảm trong Consul, phải đánh giá ACL, TLS, encryption at rest, audit và phạm vi backup theo chính sách tổ chức; không commit secret dạng rõ vào repository hay file cấu hình.

## 11. Lựa chọn format theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Một vài cờ cấu hình độc lập được cập nhật riêng | KEY_VALUE | Thay đổi từng key, không phải ghi lại toàn bộ block. |
| Nhiều thuộc tính lồng nhau, liên quan trong một lần phát hành | YAML | Cấu trúc dễ đọc và thay thế trong một KV entry. |
| Nhóm quen thuộc với Java properties | PROPERTIES | Cú pháp phẳng, tương thích quy trình hiện tại. |
| Cần diff/review rõ ràng theo commit | File YAML/PROPERTIES trong Git hoặc pipeline quản lý artifact | Consul KV tự thân không cung cấp quy trình review Git đầy đủ. |
| Secret có độ nhạy cảm cao | Vault/secret manager | Chính sách secret, lease, rotation và audit chuyên biệt. |

Một hệ thống có thể dùng nhiều format ở các context hoặc ứng dụng khác nhau, nhưng nên chuẩn hóa trong từng nhóm để người vận hành không phải đoán một context đang lưu key rời hay block `data`.

## 12. Kiểm tra và xử lý lỗi

Khi client không nhận đúng giá trị, kiểm tra từ Consul KV đến Spring Environment:

1. Xác nhận `spring.application.name` và profile thực tế của client.
2. Xác nhận prefix, default-context và profile separator.
3. Xác nhận `format` của client khớp layout dữ liệu đang lưu.
4. Với KEY_VALUE, kiểm tra từng key và value dưới context.
5. Với YAML/PROPERTIES, kiểm tra key `data-key` tồn tại và nội dung block hợp lệ.
6. Xác nhận Consul ACL token có quyền đọc prefix tương ứng.
7. Kiểm tra watch/reload có được bật và client có nhận thay đổi không.
8. Kiểm tra property source order nếu cùng khóa xuất hiện trong nhiều context.

Có thể đọc một KV entry qua CLI:

```bash
consul kv get config/orders-service,prod/app.payment.timeout
```

Hoặc lấy raw value qua HTTP API:

```bash
curl "http://localhost:8500/v1/kv/config/orders-service,prod/data?raw"
```

Các lỗi thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Client không tìm thấy cấu hình | Sai prefix, application name, profile hoặc profile separator. |
| KEY_VALUE đọc được nhưng YAML không đọc được | `format` không khớp hoặc thiếu `data-key`. |
| YAML parse error | Nội dung block sai cú pháp, encoding hoặc indentation. |
| Chỉ một số property bị thiếu | Sai tên key, key path không ánh xạ như mong đợi hoặc property nằm ở context khác. |
| Ghi một thuộc tính làm mất các thuộc tính khác | Đã ghi đè toàn bộ block bằng tài liệu thiếu key. |
| Client thấy trạng thái trung gian | Nhiều KEY_VALUE entry được ghi riêng và watch xảy ra giữa các lần ghi. |
| Consul trả 403 | ACL token không có quyền đọc prefix. |
| KV đã đổi nhưng bean chưa đổi | Watch/reload chưa bật, bean không refreshable hoặc property cần restart. |

## 13. Tổng kết

- Spring Cloud Consul Config có thể lưu cấu hình dạng KEY_VALUE rời hoặc tài liệu YAML/PROPERTIES trong một KV entry.
- KEY_VALUE phù hợp với thuộc tính độc lập; mỗi property được cập nhật qua key riêng.
- YAML/PROPERTIES block gom nhiều thuộc tính vào một key `data` (hoặc `data-key` tùy chỉnh); thay đổi block cần ghi lại toàn bộ tài liệu.
- `prefix`, `default-context`, `profile-separator`, `format` và `data-key` quyết định cách client tìm và diễn giải dữ liệu.
- Nhiều context application/profile có thể chứa cùng property; xác minh thứ tự `PropertySource` ở client thay vì suy đoán.
- Cập nhật nhiều key riêng có thể tạo trạng thái trung gian; dùng block hoặc Consul transaction đã được kiểm chứng khi cần tính nhất quán.
- Watch phát hiện thay đổi, reload/refresh áp dụng cấu hình và restart cần thiết cho thay đổi startup-only.
- Bảo vệ Consul bằng ACL và TLS; dùng Vault hoặc secret manager cho dữ liệu nhạy cảm.
