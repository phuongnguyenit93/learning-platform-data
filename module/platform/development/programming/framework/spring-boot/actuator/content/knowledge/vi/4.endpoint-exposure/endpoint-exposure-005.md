# Thứ tự ưu tiên giữa exclude, include và trạng thái enabled

## 1. Hiểu đúng ba quyết định trước khi đọc cấu hình

Giả sử ứng dụng có endpoint `metrics`. Bạn đã thêm nó vào danh sách công bố qua HTTP nhưng yêu cầu vẫn không đến được endpoint. Có thể endpoint đang bị tắt, hoặc đồng thời nằm trong danh sách loại trừ. Muốn tìm đúng nguyên nhân, cần phân biệt ba quyết định:

| Thành phần | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| `enabled` | Cho phép bật endpoint | Theo ID endpoint |
| `include` | Chọn endpoint để công bố | Theo từng giao thức: HTTP hoặc JMX |
| `exclude` | Loại endpoint khỏi tập được công bố | Theo từng giao thức: HTTP hoặc JMX |

Bài này áp dụng **Spring Boot 3.3.x**, đối chiếu tài liệu 3.3.13. Trong nhánh này, endpoint phải được bật và được công bố để có sẵn qua giao thức tương ứng; các endpoint tích hợp còn phụ thuộc điều kiện tự cấu hình. [Điều kiện khả dụng của endpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

Hai quy tắc chính:

1. **`enabled=false` chặn endpoint; đưa ID vào `include` không bật lại endpoint.**
2. **Trong cùng giao thức, `exclude` thắng `include`, kể cả khi `include` dùng `"*"`.** [Quy tắc công bố endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Vì thế, nên hiểu đây là các điều kiện kết hợp. Một danh sách cho phép không tự xóa bỏ quyết định tắt hoặc loại trừ.

## 2. Đặt từng thuộc tính đúng chỗ

Ví dụ với ID `metrics`:

```properties
management.endpoint.metrics.enabled=true
management.endpoints.web.exposure.include=health,metrics
management.endpoints.web.exposure.exclude=metrics
```

Cấu hình đang nói:

- Cho phép bật `metrics`.
- Chọn `health`, `metrics` cho HTTP.
- Đồng thời loại `metrics` khỏi HTTP.

Kết quả chính sách: `metrics` bị loại khỏi công bố HTTP.

Lưu ý tên thuộc tính: `management.endpoint.<id>.enabled` dùng **`endpoint` số ít**; `management.endpoints.web.exposure.*` dùng **`endpoints` số nhiều**. Danh sách chứa ID như `metrics`, không chứa URL `/actuator/metrics`. Theo mặc định đường dẫn, ID này tương ứng URL đó. [Danh mục thuộc tính Actuator](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

Các thuộc tính JMX tương ứng là:

```properties
management.endpoints.jmx.exposure.include=health,metrics
management.endpoints.jmx.exposure.exclude=metrics
```

Đừng dùng việc sửa danh sách HTTP để suy ra rằng danh sách JMX cũng thay đổi.

## 3. Mô hình kết hợp và bảng đầy đủ

Đối với một endpoint và **một giao thức đang xét**, đặt:

- `E`: trạng thái bật/tắt hiệu lực của endpoint.
- `I`: ID được chọn bởi danh sách `include` hiệu lực, trực tiếp hoặc qua `"*"`.
- `X`: ID bị loại bởi danh sách `exclude` hiệu lực, trực tiếp hoặc qua `"*"`.

Mô hình ghi nhớ cho ba điều kiện:

```text
DuocChinhSachChoPhep = E AND I AND NOT X
```

Đây là biểu thức giải thích, không phải mã Java hay toàn bộ thuật toán khám phá endpoint. Nó giả định endpoint hỗ trợ giao thức đang xét; để thực sự gọi được còn cần thư viện/thành phần hỗ trợ, hạ tầng giao thức, đường dẫn và quyền truy cập phù hợp.

| E: bật | I: được chọn | X: bị loại | Qua ba điều kiện? | Lý do |
| --- | --- | --- | --- | --- |
| Không | Không | Không | Không | Đang tắt, cũng chưa được chọn |
| Không | Không | Có | Không | Đang tắt và bị loại |
| Không | Có | Không | Không | `include` không bật endpoint |
| Không | Có | Có | Không | Đang tắt và bị loại |
| Có | Không | Không | Không | Bật nhưng chưa được công bố ở giao thức này |
| Có | Không | Có | Không | Không được chọn, lại bị loại |
| Có | Có | Không | Có | Thỏa cả ba điều kiện |
| Có | Có | Có | Không | `exclude` thắng `include` |

Bảng giúp trả lời hai nhầm lẫn thường gặp:

- “Đã bật” chưa đồng nghĩa với “đã có đường dẫn HTTP”.
- “Không bị loại” chưa đồng nghĩa với “đã được chọn”.

Trong cấu hình mặc định 3.3, danh sách công bố HTTP chỉ chọn `health`. Vì vậy một endpoint khác không tự có HTTP chỉ vì bạn chưa viết `exclude`. [Giá trị mặc định các thuộc tính công bố](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

### Giá trị E được xác định trước như thế nào?

Khi phân tích một cấu hình, lấy giá trị hiệu lực theo thứ tự:

1. `management.endpoint.<id>.enabled` nếu đã đặt.
2. Nếu không có giá trị riêng, dùng `management.endpoints.enabled-by-default` nếu đã đặt.
3. Nếu cả hai đều không có, dùng mặc định riêng của endpoint.

Ví dụ, mặc định chung là `false` nhưng `management.endpoint.metrics.enabled=true` thì E của `metrics` là `true`. Tuy nhiên nó vẫn phải qua I và X. Thứ tự chọn E được thể hiện trong [mã điều kiện khả dụng của Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 4. Đọc bốn cấu hình dễ gây nhầm

Các ví dụ dưới đây là những cấu hình **độc lập**, không ghép tất cả khối `management:` vào cùng một file.

### 4.1. Cùng xuất hiện trong include và exclude

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
        exclude:
          - metrics
```

Đối với HTTP của `metrics`: E=true, I=true, X=true. Kết quả là không được công bố.

Nếu yêu cầu là “cho phép xem metrics qua HTTP”, thay đổi cần thiết trong ví dụ này là gỡ `metrics` khỏi `exclude`. Thêm lại `metrics` vào `include` lần nữa không giải quyết mâu thuẫn.

### 4.2. Bị tắt nhưng vẫn có trong include

```yaml
management:
  endpoint:
    metrics:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
```

Đối với `metrics`: E=false, I=true, X=false. Kết quả vẫn không được cung cấp. Nếu cần endpoint, phải thay quyết định bật/tắt; danh sách công bố không thay thế quyết định đó.

Với endpoint tích hợp do Spring Boot tự cấu hình, trạng thái khả dụng còn được dùng để quyết định tạo thành phần liên quan. Đừng hiểu `enabled=false` chỉ là một quy tắc phân quyền dành cho khách HTTP. [Cơ chế kiểm tra enabled và exposure](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

### 4.3. Include dùng ký tự đại diện, exclude chọn một ID

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - metrics
```

`metrics` vẫn bị loại khỏi HTTP. Tên gọi “chọn tất cả” không có nghĩa là bỏ qua các quyết định loại trừ.

Đây là ví dụ để quan sát quy tắc, không phải danh sách endpoint đề xuất cho mọi ứng dụng. Khi triển khai, chọn tập công bố theo nhu cầu quản trị cụ thể.

### 4.4. Exclude dùng ký tự đại diện, include chọn một ID

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include:
          - metrics
        exclude: "*"
```

Cấu hình loại mọi endpoint khỏi HTTP, kể cả `metrics` đã được bật và chọn riêng. Không có “ngoại lệ cho phép” bằng cách ghi ID cụ thể hơn vào `include`. Để ngừng công bố toàn bộ qua HTTP, Spring Boot có hỗ trợ chính cấu hình `web.exposure.exclude=*` này. [Tắt công bố HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

Trong YAML, phải đặt dấu nháy quanh ký tự `"*"`; không viết `include: *` hoặc `exclude: *`.

## 5. Loại khỏi HTTP khác với tắt endpoint

Giả sử nhóm vận hành muốn `metrics` chỉ xuất hiện qua JMX, còn HTTP chỉ phục vụ `health`. Ví dụ sau thể hiện sự khác nhau giữa hai giao thức:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
          - metrics
        exclude:
          - metrics
    jmx:
      exposure:
        include:
          - metrics
  endpoint:
    health:
      enabled: true
    metrics:
      enabled: true
```

Đọc riêng từng giao thức:

| Giao thức | E của metrics | I | X | Kết quả chính sách |
| --- | --- | --- | --- | --- |
| HTTP | true | true | true | Bị loại |
| JMX | true | true | false | Được chọn để công bố |

Trong ví dụ, việc liệt kê `metrics` cả ở include và exclude của HTTP nhằm làm rõ quy tắc xung đột. Khi không cần minh họa, có thể chỉ liệt kê `health` ở danh sách HTTP.

`spring.jmx.enabled=true` bật cơ chế JMX do Spring quản lý; mặc định tính năng này không bật. Danh sách JMX không tự bật cổng JMX từ xa. Với miền mặc định, có thể dùng công cụ JMX kết nối cục bộ đến JVM và tìm MBean endpoint trong miền `org.springframework.boot`. [Quản trị qua JMX trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Nếu đổi `management.endpoint.metrics.enabled` thành `false`, endpoint không còn vượt qua điều kiện E ở cả hai giao thức. Đây là khác biệt thực tế cần cân nhắc khi yêu cầu là “ẩn khỏi HTTP” hay “tắt hẳn endpoint tích hợp”.

## 6. Thử nghiệm HTTP bằng một thay đổi mỗi lần

### Chuẩn bị

Dùng ứng dụng Spring Boot 3.3.x đã có lớp khởi động, có `spring-boot-starter-web` và `spring-boot-starter-actuator`, chạy với Java 17 trở lên. Bài thử giả định:

- Ứng dụng lắng nghe trên `localhost:8080`, đường dẫn quản trị mặc định là `/actuator`.
- Không có Spring Security, proxy, endpoint tùy chỉnh hay nguồn cấu hình khác làm thay đổi kết quả.
- Giao thức HTTP đang được bật và các thành phần cần cho `metrics` đã được starter cung cấp.

Nếu ứng dụng thật đã có xác thực, kiểm tra bằng tài khoản có quyền thay vì gỡ bỏ cơ chế bảo vệ. Các mã dưới đây là **kết quả dự kiến theo giả định bài thử**, không phải kết quả đã chạy trên mọi dự án.

### Cấu hình ban đầu

Dùng nội dung sau trong `src/main/resources/application.yml` của ứng dụng thử:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
          - metrics
  endpoint:
    health:
      enabled: true
    metrics:
      enabled: true
```

Khởi động ứng dụng bằng cách chạy thông thường của dự án, rồi thực hiện lệnh sau trong PowerShell trên Windows:

```powershell
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/actuator/metrics"
```

Với cấu hình ban đầu, stdout dự kiến chính xác là một dòng:

```text
200
```

Lệnh bỏ phần thân, chỉ in mã HTTP và xuống dòng. Khi cần quan sát dữ liệu:

```powershell
curl.exe --silent "http://localhost:8080/actuator/metrics"
```

Phần thân thành công chứa trường `names` là danh sách tên các số đo hiện có; danh sách cụ thể phụ thuộc ứng dụng, nên không dùng một danh sách cố định để kết luận endpoint đúng hay sai. [API metrics 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### Chuỗi thay đổi để kiểm chứng

Sau mỗi dòng trong bảng, khởi động lại ứng dụng rồi chạy lại lệnh chỉ in mã HTTP:

| Lần | Thay đổi so với trạng thái ngay trước | E / I / X của metrics qua HTTP | Stdout dự kiến |
| --- | --- | --- | --- |
| A | Giữ cấu hình ban đầu | true / true / false | `200` |
| B | Thêm `exclude: metrics` dưới `management.endpoints.web.exposure` | true / true / true | `404` |
| C | Gỡ thuộc tính `exclude` vừa thêm | true / true / false | `200` |
| D | Đổi `management.endpoint.metrics.enabled` sang `false` | false / true / false | `404` |
| E | Đổi bật riêng về `true`, bỏ `metrics` khỏi danh sách `include` | true / false / false | `404` |
| F | Thêm `metrics` lại vào `include` | true / true / false | `200` |

Mỗi mã stdout trong bảng có ký tự xuống dòng do lệnh curl đã yêu cầu. Không cần thay controller hoặc viết mã Java để kiểm tra quy tắc cấu hình này.

Nhận xét quan trọng của bài thử: B, D và E đều có thể cho 404 nhưng nguyên nhân khác nhau. Việc cần sửa lần lượt là quyết định loại trừ, trạng thái bật/tắt hoặc tập được chọn.

## 7. Hai loại ưu tiên không nên trộn lẫn

Quy tắc `exclude` thắng `include` áp dụng khi đã biết **giá trị hiệu lực** của từng thuộc tính. Nhưng ứng dụng còn có bước xác định giá trị đó từ các nguồn cấu hình.

Ví dụ:

- File cấu hình đặt `management.endpoint.metrics.enabled=true`.
- Khi chạy, tham số dòng lệnh đặt `--management.endpoint.metrics.enabled=false`.

Với cơ chế tham số dòng lệnh mặc định của Spring Boot, giá trị dòng lệnh có thể ghi đè giá trị trong file. E sau khi giải quyết nguồn cấu hình là false, rồi mới áp dụng các điều kiện công bố. [Thứ tự nguồn cấu hình và tham số dòng lệnh](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Hãy tách ba câu hỏi:

1. **Nguồn cấu hình:** giá trị cuối cùng của mỗi khóa là gì?
2. **Bật endpoint:** giá trị riêng, mặc định chung hay mặc định endpoint quyết định E?
3. **Công bố theo giao thức:** ID được chọn và có bị loại không?

Không suy luận “`include` nằm ở cuối file nên thắng `exclude`”. Đó là hai khóa khác nhau, mỗi khóa có vai trò riêng. Thay vị trí trình bày của hai khóa trong cùng một cấu hình hợp lệ không đảo quy tắc loại trừ.

## 8. Tìm lỗi mà không mở rộng công bố tùy tiện

Khi endpoint không trả dữ liệu như mong muốn, ghi lại một dòng gồm **ID, giao thức, E, I, X**. Ví dụ:

```text
metrics | HTTP | E=true | I=true | X=true
```

Dòng này cho thấy chính sách loại trừ đang chặn. Nó giúp tránh sửa một thuộc tính khác chỉ vì cùng thấy chữ `metrics`.

Sau đó kiểm tra các điều kiện ngoài mô hình:

- **Đường dẫn và cổng:** nếu base path là `/manage` thì phải gọi `/manage/metrics`; nếu cổng quản trị khác cổng ứng dụng, dùng đúng cổng. [Đường dẫn và cổng quản trị HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).
- **Điều kiện tạo endpoint:** một số endpoint cần dependency hoặc bean riêng. E=true không tạo ra thư viện còn thiếu.
- **Cơ chế bảo vệ:** endpoint được công bố vẫn có thể yêu cầu xác thực và phân quyền. Mã 401/403 cần được đọc cùng cấu hình bảo vệ; một bộ lọc cũng có thể xử lý yêu cầu trước bước tìm đường dẫn. [Bảo vệ endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).
- **Cấu hình đã được áp dụng:** sau khi đổi file, khởi động lại ứng dụng thông thường; không mặc định rằng endpoint sẽ tự đổi trạng thái ngay.

Tránh ba cách sửa thiếu căn cứ: thêm ID lặp lại vào `include`, đổi thành `include: "*"` khi chưa xem `exclude`, hoặc tắt xác thực để xử lý một endpoint thực ra chưa được bật.

## 9. Tự đánh giá qua tình huống

**Câu 1.** `enabled=true`, `include=metrics`, `exclude=*`. Có công bố `metrics` qua giao thức đang xét không?

**Đáp án:** Không. Ký tự đại diện ở danh sách loại trừ khớp `metrics`; việc chọn riêng không tạo ngoại lệ.

**Câu 2.** `enabled=false`, `include=*`, không có loại trừ. Có endpoint HTTP không?

**Đáp án:** Không vượt qua điều kiện bật/tắt. Chọn công bố không bật lại endpoint.

**Câu 3.** `enabled=true`, HTTP loại `metrics`, JMX chọn `metrics` và không loại. HTTP không gọi được có chứng minh endpoint đã tắt hẳn không?

**Đáp án:** Không. Hãy kiểm tra riêng JMX cùng điều kiện hạ tầng của nó; loại trừ HTTP chỉ thuộc phạm vi HTTP.

**Câu 4.** Muốn bỏ `metrics` khỏi HTTP và vẫn giữ nó qua JMX thì nên đổi thuộc tính nào?

**Đáp án:** Sửa chính sách công bố HTTP, đồng thời giữ quyết định bật và cấu hình JMX cần thiết. Nếu tắt riêng endpoint, bạn đang thay đổi cả điều kiện E dùng chung.

**Câu 5.** Ba trường hợp “bị tắt”, “không nằm trong include” và “bị exclude” đều có thể dẫn tới 404 trong bài thử. Cần lưu thêm gì ngoài mã HTTP?

**Đáp án:** Giá trị hiệu lực E/I/X theo đúng ID và giao thức, cùng đường dẫn/cổng và điều kiện bảo vệ. Khi có các dữ kiện đó, thay đổi cấu hình mới có căn cứ.
