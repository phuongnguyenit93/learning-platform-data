# data-key và cách tổ chức cấu hình nhiều tài liệu

Spring Cloud Consul Config dùng Consul Key/Value (KV) làm nguồn cấu hình tập trung. Thay vì đọc một tệp YAML trực tiếp từ Git, Config Client truy vấn các key theo prefix, application context và profile. Khi chọn định dạng YAML hoặc Properties, mỗi context thường được lưu thành một nội dung tài liệu trong một KV entry riêng. Tên key cuối cùng chứa tài liệu đó được điều khiển bởi thuộc tính <code>spring.cloud.consul.config.data-key</code>.

<code>data-key</code> không phải tên ứng dụng, profile hay prefix của toàn bộ repository. Nó là tên KV entry chứa nội dung tài liệu bên trong một context. Mặc định thường là <code>data</code>. Nếu muốn chia cấu hình thành nhiều tài liệu độc lập, cần chọn cách tổ chức phù hợp: dùng nhiều context theo application/profile, dùng định dạng FILES để lưu nhiều file riêng, hoặc dùng KEY_VALUE để lưu từng thuộc tính thành một KV entry.

Bài học này giải thích cấu trúc KV, ý nghĩa của <code>data-key</code>, cách tổ chức tài liệu dùng chung và riêng theo dịch vụ, sự khác nhau giữa các format, thứ tự ưu tiên, cập nhật an toàn và cách chẩn đoán khi client không nạp đúng tài liệu.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa prefix, default context, application name, profile và data-key.
- Tạo KV path đúng cho YAML hoặc Properties document.
- Thay đổi data-key và xác định đường dẫn Consul tương ứng.
- Chọn giữa YAML, PROPERTIES, FILES và KEY_VALUE.
- Tổ chức cấu hình dùng chung, theo profile, theo ứng dụng và theo môi trường.
- Hiểu cách các context được ghép và xác minh nguồn thắng trong Spring Environment.
- Cập nhật nhiều tài liệu có kiểm soát, dùng Consul ACL và kiểm tra version.
- Chẩn đoán trường hợp KV có dữ liệu nhưng Config Client không nhận được cấu hình mong muốn.

## 1. Consul KV là cây key/value, không phải thư mục file thông thường

Consul KV lưu mỗi giá trị dưới một key. Dấu <code>/</code> trong key giúp tổ chức dữ liệu theo cấu trúc phân cấp, nhưng bản thân KV không phải filesystem. Ví dụ:

~~~text
config/
  application/
    data
  orders-service/
    data
  inventory-service/
    data
~~~

Các key đầy đủ trong ví dụ là:

~~~text
config/application/data
config/orders-service/data
config/inventory-service/data
~~~

Với format YAML, giá trị của key <code>config/orders-service/data</code> có thể là toàn bộ nội dung của một YAML document:

~~~yaml
orders:
  timeout: 3s
  retry:
    max-attempts: 3
    backoff: 200ms
~~~

Config Client không đọc một file từ đường dẫn <code>config/orders-service/data</code> như filesystem. Nó truy vấn Consul KV, lấy value của key đó và đưa nội dung qua parser tương ứng với format đã cấu hình.

Cần phân biệt ba khái niệm:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Prefix | <code>config</code> | Gốc cây KV dành cho cấu hình |
| Context | <code>orders-service</code> hoặc <code>application,prod</code> | Phạm vi cấu hình dùng chung, theo app hoặc profile |
| Data key | <code>data</code> | KV entry chứa nội dung YAML/Properties của context |

Nếu nhầm <code>data-key</code> với prefix, client sẽ truy vấn sai key. Nếu nhầm context với data-key, dữ liệu có thể được lưu đúng trong Consul nhưng không được Config Client tìm thấy.

## 2. Vai trò của prefix, context và profile

Spring Cloud Consul Config xây dựng các context cần đọc từ một số thuộc tính:

| Thuộc tính | Giá trị mặc định thường gặp | Ý nghĩa |
|---|---|---|
| <code>spring.cloud.consul.config.prefix</code> | <code>config</code> | Prefix gốc trong KV |
| <code>spring.cloud.consul.config.default-context</code> | <code>application</code> | Context cấu hình dùng chung |
| <code>spring.cloud.consul.config.name</code> | <code>spring.application.name</code> | Tên application context |
| <code>spring.cloud.consul.config.profile-separator</code> | <code>,</code> | Ký tự nối context với profile |
| <code>spring.cloud.consul.config.data-key</code> | <code>data</code> | Tên KV entry chứa document |
| <code>spring.cloud.consul.config.format</code> | <code>KEY_VALUE</code> | Cách diễn giải dữ liệu KV |

Ví dụ ứng dụng:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  cloud:
    consul:
      host: consul.internal
      port: 8500
      config:
        enabled: true
        prefix: config
        default-context: application
        name: orders-service
        profile-separator: ","
        format: YAML
        data-key: data
~~~

Với ví dụ này, các context thường được truy vấn gồm:

- <code>config/application</code>: cấu hình mặc định dùng chung.
- <code>config/application,prod</code>: cấu hình dùng chung cho profile prod.
- <code>config/orders-service</code>: cấu hình mặc định riêng cho orders-service.
- <code>config/orders-service,prod</code>: cấu hình riêng orders-service cho profile prod.

Khi format là YAML và <code>data-key</code> là <code>data</code>, KV entry chứa document được đặt dưới từng context:

~~~text
config/application/data
config/application,prod/data
config/orders-service/data
config/orders-service,prod/data
~~~

Đây là cấu trúc ví dụ theo các giá trị cấu hình đã nêu. Nếu đổi prefix, default context, application name hoặc profile separator, đường dẫn KV cần thay đổi tương ứng.

## 3. data-key là gì và khi nào cần đổi?

<code>spring.cloud.consul.config.data-key</code> chỉ định tên key cuối cùng chứa nội dung YAML hoặc Properties trong mỗi context. Giá trị mặc định thường là <code>data</code>.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    consul:
      config:
        format: YAML
        data-key: settings
~~~

Khi đó, thay vì đọc:

~~~text
config/orders-service/data
~~~

client đọc:

~~~text
config/orders-service/settings
~~~

Giá trị của key <code>config/orders-service/settings</code> là nội dung YAML:

~~~yaml
orders:
  timeout: 3s
  retry:
    max-attempts: 3
~~~

### data-key không làm thay đổi context

Nếu đổi <code>data</code> thành <code>settings</code>, client vẫn dùng prefix, application và profile đã cấu hình. Chỉ phần tên KV entry chứa document thay đổi.

| Thành phần | Trước | Sau |
|---|---|---|
| Prefix | <code>config</code> | <code>config</code> |
| Context | <code>orders-service,prod</code> | <code>orders-service,prod</code> |
| Data key | <code>data</code> | <code>settings</code> |
| KV entry | <code>config/orders-service,prod/data</code> | <code>config/orders-service,prod/settings</code> |

Thay đổi data-key ở client mà không chuyển dữ liệu sang key mới sẽ khiến client không tìm thấy document. Trong lúc migration, cần đồng bộ thay đổi cấu hình client và KV path; không xóa key cũ cho tới khi các instance đã chuyển sang key mới và được xác minh.

### data-key không phải danh sách tên file

Thuộc tính này biểu diễn một tên KV entry cho mỗi context. Nó không tự động tìm tất cả file trong một context và không phải cơ chế đặt tên nhiều YAML file. Nếu cần nhiều file độc lập, hãy xem format FILES ở phần sau.

## 4. Lưu YAML document trong Consul KV

Khi chọn <code>format: YAML</code>, mỗi context có thể chứa một YAML document trong key được xác định bởi data-key.

Ví dụ tạo key dùng chung:

~~~bash
consul kv put config/application/data @application.yml
~~~

Nội dung <code>application.yml</code>:

~~~yaml
platform:
  company-name: Example
  default-timeout: 2s

logging:
  level:
    root: INFO
~~~

Tạo key riêng cho orders-service:

~~~bash
consul kv put config/orders-service/data @orders-service.yml
~~~

Nội dung:

~~~yaml
orders:
  reservation:
    timeout: 3s
    max-attempts: 3
~~~

Tạo key riêng cho profile production:

~~~bash
consul kv put config/orders-service,prod/data @orders-service-prod.yml
~~~

Nội dung:

~~~yaml
orders:
  reservation:
    timeout: 1s
    max-attempts: 2
~~~

Trong các ví dụ, <code>@filename</code> là cú pháp Consul CLI để đọc nội dung file làm value. File nguồn chỉ là cách chuẩn bị document; Consul lưu nội dung dưới dạng value của một KV key.

Có thể đọc lại:

~~~bash
consul kv get config/orders-service,prod/data
~~~

Kết quả trả về là nội dung YAML đang được lưu trong KV entry. Nếu cần kiểm tra metadata, dùng lệnh hoặc API Consul tương ứng để xem <code>CreateIndex</code>, <code>ModifyIndex</code> và <code>Flags</code> khi có.

## 5. Gửi YAML document bằng Consul HTTP API

Consul KV HTTP API nhận value trong request body. Ví dụ:

~~~bash
curl --request PUT \
  --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
  --data-binary "@orders-service.yml" \
  "https://consul.internal/v1/kv/config/orders-service/data"
~~~

API thường trả boolean cho biết thao tác ghi được chấp nhận. Dùng <code>--data-binary</code> để gửi nguyên nội dung file, giữ newline và ký tự theo file nguồn.

Để đọc key:

~~~bash
curl \
  --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
  "https://consul.internal/v1/kv/config/orders-service/data"
~~~

API GET trả metadata và value đã được Base64-encode trong trường <code>Value</code> của JSON response. Công cụ Consul CLI thường giải mã và hiển thị value thuận tiện hơn.

Không đưa token thật vào repository, tài liệu hoặc log CI. Với môi trường production, dùng HTTPS, Consul ACL và danh tính dịch vụ được cấp quyền tối thiểu.

## 6. Tổ chức cấu hình dùng chung, profile và ứng dụng

Một cấu trúc dễ quản trị là chia theo phạm vi từ rộng tới hẹp:

~~~text
config/
  application/
    data
  application,dev/
    data
  application,prod/
    data
  orders-service/
    data
  orders-service,dev/
    data
  orders-service,prod/
    data
  inventory-service/
    data
  inventory-service,prod/
    data
~~~

Mỗi <code>data</code> là một YAML document độc lập.

### Cấu hình dùng chung

<code>config/application/data</code> có thể chứa các mặc định dùng chung cho nhiều dịch vụ:

~~~yaml
platform:
  connect-timeout: 500ms
  request-timeout: 3s

logging:
  level:
    root: INFO
~~~

Không đặt thông tin bí mật dùng riêng cho một ứng dụng vào context dùng chung. Tất cả client có quyền đọc context chung có thể nhận các thuộc tính đó.

### Cấu hình chung theo môi trường

<code>config/application,prod/data</code> chứa các giá trị dùng chung cho profile production:

~~~yaml
platform:
  request-timeout: 2s

logging:
  level:
    root: WARN
~~~

### Cấu hình riêng theo ứng dụng

<code>config/orders-service/data</code> chứa cấu hình riêng của orders-service:

~~~yaml
orders:
  reservation:
    max-attempts: 4
    timeout: 3s
~~~

### Cấu hình riêng theo ứng dụng và profile

<code>config/orders-service,prod/data</code> chứa override riêng cho orders production:

~~~yaml
orders:
  reservation:
    max-attempts: 2
    timeout: 1s
~~~

Tổ chức như vậy giảm việc sao chép toàn bộ cấu hình giữa các môi trường. Context chung giữ default, context hẹp hơn chỉ khai báo những thuộc tính cần ghi đè.

## 7. Thứ tự ưu tiên và cách kiểm tra giá trị cuối cùng

Spring Cloud Consul Config ghép các context thành nhiều property source. Theo cách tổ chức mặc định phổ biến, cấu hình dùng chung có độ ưu tiên thấp hơn cấu hình riêng theo ứng dụng; profile-specific có thể ghi đè giá trị không profile tương ứng.

Với ví dụ trên, thứ tự từ thấp tới cao thường được hiểu như sau:

1. <code>config/application</code>
2. <code>config/application,prod</code>
3. <code>config/orders-service</code>
4. <code>config/orders-service,prod</code>

Với <code>orders.reservation.timeout</code>, giá trị cuối cùng theo ví dụ là <code>1s</code>; <code>max-attempts</code> là <code>2</code>. Nếu khóa chỉ xuất hiện trong context chung, ứng dụng vẫn có thể nhận giá trị đó mà không cần lặp lại ở context riêng.

Không chỉ dựa vào danh sách trên để kết luận runtime. Thứ tự property source thực tế còn phụ thuộc phiên bản Spring Cloud Consul, các profile đang active, cách nạp cấu hình và những nguồn Spring Boot khác như biến môi trường, system property hoặc command line. Hãy kiểm tra Environment của client và giá trị đã bind vào bean khi cần xác minh.

### Ví dụ property được ghi đè

Giả sử:

| Context | <code>orders.reservation.timeout</code> |
|---|---:|
| <code>application</code> | <code>3s</code> |
| <code>application,prod</code> | <code>2s</code> |
| <code>orders-service</code> | <code>4s</code> |
| <code>orders-service,prod</code> | <code>1s</code> |

Nếu các property source được áp dụng theo thứ tự ưu tiên nêu trên, orders-service production dùng <code>1s</code>. Một biến môi trường hoặc tham số khởi chạy có độ ưu tiên cao hơn vẫn có thể ghi đè giá trị này ở phía client.

## 8. Format YAML, PROPERTIES, FILES và KEY_VALUE

<code>data-key</code> chỉ có ý nghĩa với các format lưu nội dung document trong một KV entry. Cần chọn format theo cách nhóm muốn quản trị dữ liệu.

| Format | Cách lưu | Vai trò của data-key |
|---|---|---|
| <code>YAML</code> | Một YAML document trong một KV entry của mỗi context | Dùng để chọn key chứa document |
| <code>PROPERTIES</code> | Một Java Properties document trong một KV entry của mỗi context | Dùng để chọn key chứa document |
| <code>FILES</code> | Nhiều file riêng được lưu thành các KV entry dưới context | Không dùng data-key theo cách của YAML/PROPERTIES |
| <code>KEY_VALUE</code> | Mỗi property được lưu thành một KV entry | Không cần một document data-key |

Tên format và chi tiết parser phụ thuộc phiên bản Spring Cloud Consul. Hãy dùng giá trị được phiên bản của dự án hỗ trợ.

### YAML: một document cho mỗi context

Ví dụ:

~~~yaml
spring:
  cloud:
    consul:
      config:
        format: YAML
        data-key: data
~~~

KV entry <code>config/orders-service/data</code> chứa toàn bộ YAML. Cách này phù hợp khi muốn nhóm các thuộc tính liên quan trong một document và review thay đổi như một đơn vị.

### PROPERTIES: một document dạng key=value

Ví dụ:

~~~yaml
spring:
  cloud:
    consul:
      config:
        format: PROPERTIES
        data-key: application.properties
~~~

KV entry <code>config/orders-service/application.properties</code> có thể chứa:

~~~properties
orders.reservation.timeout=3s
orders.reservation.max-attempts=3
logging.level.root=INFO
~~~

Ở đây tên data-key được đổi thành <code>application.properties</code>, vì vậy path KV kết thúc bằng tên đó.

### FILES: nhiều tài liệu độc lập

Khi muốn chia thành nhiều file nhỏ, FILES thường phù hợp hơn việc nhét tất cả vào một YAML document.

Ví dụ cấu trúc minh họa:

~~~text
config/
  orders-service/
    application.yml
    reservation.yml
    integrations.yml
    logging.properties
  orders-service,prod/
    application.yml
    reservation.yml
~~~

Mỗi file được lưu dưới một KV key tương ứng với tên file. Client đọc các file được hỗ trợ trong context và phân tích theo phần mở rộng. Kiểm tra chính xác quy ước path, phần mở rộng và parser của phiên bản đang dùng trước khi chuyển dữ liệu.

Ưu điểm:

- Nhóm cấu hình theo domain hoặc nhóm sở hữu.
- Review và cập nhật một tài liệu nhỏ mà không phải ghi lại toàn bộ document.
- Giảm xung đột khi nhiều nhóm cùng quản lý cấu hình.
- Có thể áp dụng quyền ghi theo prefix/file nếu policy được thiết kế phù hợp.

Nhược điểm:

- Nhiều KV entry cần được cập nhật đồng bộ khi một thay đổi liên quan nhiều file.
- Trùng khóa giữa các file có thể làm thứ tự property source trở nên khó hiểu.
- Cần quy ước tên file và quyền sở hữu rõ ràng.

### KEY_VALUE: mỗi thuộc tính là một entry

Ví dụ:

~~~text
config/orders-service/orders.reservation.timeout = 3s
config/orders-service/orders.reservation.max-attempts = 3
config/orders-service/logging.level.root = INFO
~~~

Cách này phù hợp với một số thuộc tính đơn giản, cần chỉnh sửa riêng lẻ hoặc được cập nhật bởi automation. Tuy nhiên, khi số lượng khóa tăng, cây KV có thể khó review như một thay đổi tổng thể. Cần có quy ước key name, namespace và kiểm tra khóa thừa.

## 9. Khi nào nên dùng một data-key và khi nào nên chia nhiều file?

Có thể dùng các nguyên tắc sau:

| Nhu cầu | Cách tổ chức nên cân nhắc |
|---|---|
| Cấu hình dịch vụ nhỏ, thay đổi cùng nhau | Một YAML document với data-key |
| Cấu hình dùng chung và riêng theo profile | Nhiều context, mỗi context một document |
| Nhiều nhóm sở hữu các miền cấu hình độc lập | FILES với file name theo domain |
| Automation chỉ cập nhật một vài scalar property | KEY_VALUE |
| Muốn giữ file YAML/Properties quen thuộc | FILES hoặc một document YAML/PROPERTIES |
| Muốn tách quyền đọc theo ứng dụng | Prefix/context riêng và Consul ACL |

Không chia nhỏ chỉ vì có thể tạo nhiều KV key. Nếu các thuộc tính phải thay đổi cùng nhau để giữ invariant, nên lưu và phát hành chúng như một đơn vị hoặc có quy trình cập nhật đồng bộ.

Ngược lại, một document quá lớn chứa cấu hình của nhiều domain có thể làm việc review khó khăn và khiến một nhóm phải có quyền ghi lên mọi thuộc tính. Hãy chia theo vòng đời thay đổi, quyền sở hữu và quan hệ phụ thuộc.

## 10. Multi-document YAML và profile của Consul

Spring Boot có cú pháp nhiều YAML document phân cách bằng <code>---</code>. Tuy nhiên, không nên mặc định rằng cơ chế profile activation của Spring Boot trong một tệp <code>application.yml</code> sẽ hoạt động giống hệt khi nội dung được lưu như value của Consul KV và nạp bằng parser của Spring Cloud Consul.

Với Consul Config, cách rõ ràng để tách cấu hình theo profile là dùng các context riêng được tạo từ <code>profile-separator</code>:

~~~text
config/application/data
config/application,dev/data
config/application,prod/data
config/orders-service/data
config/orders-service,dev/data
config/orders-service,prod/data
~~~

Mỗi key chứa document của đúng context. Cách này giúp người vận hành nhìn thấy profile qua KV path và không phụ thuộc vào việc parser có hỗ trợ các chỉ thị profile bên trong YAML hay không.

Nếu dự án muốn dùng nhiều YAML document trong cùng một KV value, hãy xác minh parser và phiên bản Spring Cloud Consul cụ thể bằng integration test. Không trộn hai cơ chế profile mà không có quy ước rõ ràng.

## 11. Tách môi trường bằng prefix và ACL

Có thể tách cây KV theo môi trường bằng prefix riêng:

~~~yaml
spring:
  cloud:
    consul:
      config:
        prefix: config/prod
~~~

Khi đó, context dùng chung có thể nằm dưới:

~~~text
config/prod/application/data
config/prod/orders-service/data
config/prod/orders-service,prod/data
~~~

Một cách khác là dùng Consul namespace hoặc cluster/partition theo năng lực và edition đang triển khai. Chọn cách phân tách sao cho danh tính của service chỉ đọc được vùng cấu hình cần thiết.

Ví dụ ACL policy chỉ cho orders-service đọc prefix riêng:

~~~hcl
key_prefix "config/prod/orders-service/" {
  policy = "read"
}
~~~

Nếu ứng dụng cần đọc context dùng chung, cấp thêm quyền read cho đúng prefix chung. Không cấp quyền write cho Config Client runtime chỉ vì nó cần đọc cấu hình.

Pipeline phát hành cấu hình có thể có quyền write riêng, giới hạn vào các prefix mà pipeline quản lý. Tách token đọc của ứng dụng khỏi token ghi của automation.

Consul KV không tự biến value thành secret chỉ vì key nằm dưới một prefix có tên <code>secrets</code>. Dùng ACL để giới hạn truy cập, TLS để bảo vệ đường truyền và secret manager như Vault cho dữ liệu nhạy cảm cần rotation, audit hoặc lease. Không đưa password/token plaintext vào context dùng chung.

## 12. Cập nhật nhiều tài liệu an toàn

Một thay đổi có thể cần cập nhật nhiều context hoặc nhiều file. Nếu client đọc dữ liệu đúng lúc các KV entry đang được ghi lần lượt, nó có thể nhìn thấy trạng thái trộn giữa bản cũ và bản mới.

Ví dụ cần cập nhật đồng thời:

- <code>config/application/data</code>: timeout mặc định.
- <code>config/orders-service/data</code>: retry policy.
- <code>config/orders-service,prod/data</code>: override production.

Consul KV cung cấp cơ chế index và compare-and-set (CAS) cho từng key. Consul cũng có transaction API cho một nhóm thao tác KV trong giới hạn của transaction. Không nên mặc định nhiều lệnh <code>consul kv put</code> độc lập là một transaction nguyên tử.

Một quy trình phát hành an toàn:

1. Chuẩn bị toàn bộ tài liệu candidate trong repository hoặc workspace phát hành.
2. Parse YAML/Properties và kiểm tra schema.
3. Kiểm tra cấu hình bằng đúng phiên bản ứng dụng.
4. Kiểm tra các invariant liên quan giữa nhiều context.
5. Ghi candidate vào prefix thử nghiệm hoặc namespace riêng.
6. Cho một client kiểm thử đọc toàn bộ candidate và xác minh giá trị cuối cùng.
7. Nếu cần cập nhật nhiều key nguyên tử, dùng Consul transaction API trong giới hạn được hỗ trợ; nếu không, promote theo batch và có version marker.
8. Theo dõi client refresh và rollback nếu có instance nhận trạng thái không nhất quán.

Nếu cần bảo đảm các giá trị chuyển cùng nhau, có thể gom chúng vào một document/entry hoặc dùng một version marker mà ứng dụng chỉ chấp nhận khi mọi phần cùng phiên bản. Không giả định một loạt lệnh <code>consul kv put</code> riêng lẻ là transaction toàn bộ cây KV.

### Compare-and-set cho một key

Consul KV HTTP API hỗ trợ CAS theo <code>ModifyIndex</code> của key. Khi ghi, truyền index mong đợi qua tham số <code>cas</code>:

~~~bash
curl --request PUT \
  --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
  --data-binary "@orders-service.yml" \
  "https://consul.internal/v1/kv/config/orders-service/data?cas=12345"
~~~

Ví dụ <code>12345</code> là ModifyIndex đã đọc trước đó. Nếu key đã thay đổi kể từ lần đọc, CAS không chấp nhận ghi theo index cũ. Cơ chế này giúp tránh ghi đè thay đổi mới hơn, nhưng chỉ bảo vệ thao tác trên key đó; nó không tạo transaction cho nhiều key.

## 13. Thay đổi data-key hoặc format mà không làm client mất cấu hình

Đổi từ <code>data</code> sang <code>settings</code> hoặc đổi format từ YAML sang FILES là thay đổi giao thức lưu trữ giữa Config Client và Consul KV.

Cần thực hiện theo trình tự:

1. Xác định toàn bộ client đang dùng prefix, context, format và data-key hiện tại.
2. Chuẩn bị dữ liệu ở cấu trúc mới song song với cấu trúc cũ.
3. Kiểm tra bằng một client thử nghiệm dùng cấu hình mới.
4. Xác nhận application, profile và giá trị đã bind đầy đủ.
5. Chuyển client theo batch hoặc rollout có kiểm soát.
6. Theo dõi lỗi lookup, parse và refresh.
7. Chỉ xóa key cũ khi không còn client nào cần đọc chúng và có bản sao phục hồi.

Không đổi data-key ở một số instance rồi xóa key cũ ngay. Các replica chạy phiên bản cấu hình khác nhau có thể đọc các key khác nhau trong cùng thời điểm.

Nếu format là YAML, <code>data-key</code> được dùng để tìm document. Nếu chuyển sang FILES, phải tạo các KV entry theo quy ước file và cấu hình format mới; chỉ đổi <code>data-key</code> không chuyển một document thành nhiều file.

## 14. Kiểm tra client đã nạp đúng tài liệu

Khi client không nhận được cấu hình như dự kiến, kiểm tra theo thứ tự:

1. <code>spring.application.name</code> và <code>spring.cloud.consul.config.name</code>.
2. Active profiles và <code>spring.cloud.consul.config.profile-separator</code>.
3. Prefix và default context.
4. Format và data-key.
5. KV path đầy đủ của từng context.
6. ACL token có quyền read đúng prefix.
7. Nội dung value có parse được bằng format đã chọn.
8. Property source và giá trị cuối cùng trong Spring Environment.
9. Các nguồn khác ở phía client như environment variable hoặc command line có ghi đè không.

Có thể dùng Consul CLI để kiểm tra:

~~~bash
consul kv get config/application/data
consul kv get config/orders-service/data
consul kv get config/orders-service,prod/data
~~~

Nếu CLI đọc được key nhưng client không nhận giá trị, kiểm tra path mà client thực sự truy vấn, format, data-key và log của Config Client. Đọc được một key không chứng minh đó là key thuộc context đang active.

### Một số lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| KV có dữ liệu nhưng client không thấy | Sai prefix, context, profile hoặc application name | Đối chiếu path client đang truy vấn |
| YAML không được parse | Format chưa đặt YAML hoặc value sai cú pháp | Kiểm tra <code>spring.cloud.consul.config.format</code> và nội dung |
| Client không tìm thấy document | data-key ở client khác tên key đã lưu | So sánh leaf key trong KV |
| Đổi data-key xong cấu hình biến mất | Chưa tạo key mới dưới data-key mới | Kiểm tra KV path mới trước khi rollout |
| Thuộc tính bị ghi đè bất ngờ | Cùng khóa tồn tại trong nhiều context hoặc nguồn runtime | Kiểm tra PropertySource order và origin |
| Một số instance có giá trị khác nhau | Active profile, prefix, token hoặc thời điểm refresh khác nhau | So sánh cấu hình và KV index theo instance |
| FILES chỉ nạp một phần | Tên file, phần mở rộng hoặc cấu trúc context không đúng | Kiểm tra quy ước FILES của phiên bản |
| Consul trả 403 | ACL token không có quyền read | Kiểm tra policy và token của client |
| Consul không truy cập được | DNS, TLS, address hoặc datacenter sai | Kiểm tra kết nối và cấu hình Consul client |

## 15. Theo dõi thay đổi và khôi phục

Spring Cloud Consul Config có thể theo dõi thay đổi KV để làm mới cấu hình theo cơ chế watch nếu được bật. Hành vi watch, khoảng chờ và cách refresh phụ thuộc phiên bản và cấu hình. Một thay đổi KV không đồng nghĩa mọi bean của ứng dụng đã được cập nhật thành công.

Khi theo dõi một đợt thay đổi, ghi nhận:

- Context và KV key đã thay đổi.
- ModifyIndex hoặc version metadata của key.
- Application, profile và instance đã nạp.
- Thời điểm phát hiện thay đổi và refresh.
- Kết quả parse, bind và validation.
- Trạng thái readiness và lỗi nghiệp vụ sau refresh.

Đối với rollback, lưu lại nội dung và index/phiên bản trước khi cập nhật. Nếu candidate gây lỗi, phục hồi value đã xác nhận, sau đó xác minh client đã đọc lại và các bean hỗ trợ refresh đã nhận giá trị mong muốn. Nếu không thể chứng minh trạng thái runtime đồng bộ, dùng rolling restart theo phiên bản cấu hình đã biết.

Consul KV có index metadata nhưng không cung cấp nhánh Git hoặc label theo cách Spring Cloud Config Git backend làm. Nếu cần quản lý branch/tag, review pull request và lịch sử cấu hình như mã nguồn, có thể dùng Git làm nơi authoring rồi triển khai đồng bộ sang Consul, hoặc dùng backend phù hợp với yêu cầu versioning. Không gọi <code>ModifyIndex</code> là Git label.

## 16. Checklist tổ chức data-key và nhiều tài liệu

- [ ] Đã xác định prefix, default context, application name và profile separator.
- [ ] Đã chọn format phù hợp: YAML, PROPERTIES, FILES hoặc KEY_VALUE.
- [ ] Nếu dùng YAML/PROPERTIES, data-key khớp chính xác leaf KV entry.
- [ ] Đã hiểu data-key không phải prefix, application name hoặc danh sách file.
- [ ] Cấu hình chung, profile và application được chia theo context rõ ràng.
- [ ] Không mặc định multi-document YAML của Spring Boot giống cách Consul Config parse.
- [ ] Nếu dùng FILES, đã kiểm tra path, file name và extension với phiên bản dự án.
- [ ] Quy tắc trùng khóa và precedence đã được kiểm tra trong client.
- [ ] Consul ACL chỉ cấp quyền read cho ứng dụng và write cho pipeline cần thiết.
- [ ] Secret được lưu bằng cơ chế phù hợp, không dựa vào tên prefix để coi KV là secret store.
- [ ] Cập nhật nhiều key có kế hoạch candidate, kiểm tra và rollback.
- [ ] Dùng CAS khi cần tránh ghi đè một key đã bị thay đổi.
- [ ] Thay data-key/format theo rollout tương thích, chưa xóa key cũ quá sớm.
- [ ] Đã xác minh property source và giá trị cuối cùng trên client.
- [ ] Có log/metric về context, index và kết quả refresh mà không làm lộ secret.

<code>data-key</code> là tên KV entry chứa một YAML hoặc Properties document trong từng context; nó không quyết định application, profile hay prefix. Để tổ chức cấu hình nhiều tài liệu, hãy chia context theo phạm vi dùng chung/profile/application hoặc chọn FILES khi cần nhiều file độc lập, và chọn KEY_VALUE khi muốn quản lý từng thuộc tính. Kết hợp quy ước path rõ ràng, xác minh precedence, ACL tối thiểu và rollout có kiểm soát giúp Config Client nạp đúng tài liệu từ Consul và tránh trạng thái cấu hình không nhất quán.

