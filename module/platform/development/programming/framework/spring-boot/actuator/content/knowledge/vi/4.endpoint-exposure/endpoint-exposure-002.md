# Lựa chọn cơ chế bật mặc định hoặc chỉ bật endpoint được chỉ định

## 1. Vấn đề cần giải quyết

Một ứng dụng có Actuator không nhất thiết cần mọi khả năng quản trị. Giả sử nhóm vận hành chỉ cần kiểm tra sức khỏe, xem thông tin phiên bản và đọc số đo. Khi đó cần quyết định: giữ chính sách bật sẵn rồi tắt từng endpoint không dùng, hay tắt mặc định rồi khai báo rõ từng endpoint được phép bật?

Bài này dùng **Spring Boot 3.3.x**, với tài liệu đối chiếu ở 3.3.13. Các đoạn YAML là cấu hình cho một ứng dụng đã có Actuator; các lệnh HTTP ở phần thực hành có điều kiện chạy cụ thể. Khi nâng Spring Boot, cần đọc tài liệu đúng phiên bản trước khi giữ nguyên các thuộc tính.

### Ba khái niệm liên quan

- **Bật endpoint (enablement):** quyết định endpoint có được phép tham gia cơ chế tự cấu hình hay không.
- **Công bố endpoint (exposure):** chọn endpoint được cung cấp qua HTTP hoặc JMX.
- **Xác thực và phân quyền:** quyết định ai được thực hiện yêu cầu tới endpoint đã được cung cấp.

Trong Spring Boot 3.3, endpoint có sẵn để sử dụng khi được bật và được công bố; các endpoint tích hợp còn cần thỏa điều kiện tự cấu hình của chúng. Vì vậy, chỉ đặt `enabled: true` chưa đủ để khẳng định có thể gọi một URL. Mặc định của nhánh này bật các endpoint tích hợp trừ `shutdown`, nhưng chỉ công bố `health` qua HTTP và JMX. [Tài liệu endpoint Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

Ví dụ, tên `metrics` trong danh sách công bố là **ID endpoint**, còn `/actuator/metrics` là đường dẫn HTTP theo cấu hình đường dẫn mặc định. Không đưa đường dẫn HTTP vào thuộc tính vốn yêu cầu ID. [Quy ước URL Actuator](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html#urls).

## 2. Cơ chế chọn giá trị bật/tắt

Có hai cấp cấu hình:

| Phạm vi | Thuộc tính | Câu hỏi được trả lời |
| --- | --- | --- |
| Mặc định chung | `management.endpoints.enabled-by-default` | Nếu endpoint không có cấu hình riêng, có cho phép bật không? |
| Từng endpoint | `management.endpoint.<id>.enabled` | Endpoint mang ID này được bật hay tắt? |

Chú ý cách viết: cấp chung dùng **`endpoints` số nhiều**, cấp riêng dùng **`endpoint` số ít**. Ví dụ đúng là `management.endpoint.health.enabled=true`. [Danh mục thuộc tính Actuator 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

Trong mã điều kiện tự cấu hình của Spring Boot 3.3.13, thứ tự lựa chọn là:

1. Nếu có `management.endpoint.<id>.enabled`, dùng giá trị riêng đó.
2. Nếu không có giá trị riêng nhưng đã đặt `management.endpoints.enabled-by-default`, dùng giá trị chung.
3. Nếu cả hai đều không được đặt, dùng mặc định do chính endpoint khai báo.

Bảng sau diễn đạt kết quả của **chính sách bật/tắt**, chưa xét công bố hay điều kiện thư viện:

| Giá trị chung | Giá trị riêng của endpoint | Kết quả bật/tắt |
| --- | --- | --- |
| `false` | Không đặt | Tắt |
| `false` | `true` | Bật |
| `true` | `false` | Tắt |
| `true` | Không đặt | Bật |
| Không đặt | Không đặt | Theo mặc định riêng của endpoint |

Hệ quả cần nhớ: **không đặt giá trị chung khác với chủ động đặt giá trị chung là `true`**. Đây là kết luận từ thứ tự xử lý trong [`OnAvailableEndpointCondition` của 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 3. Cách thứ nhất: giữ mặc định, tắt những endpoint không cần

Cách này thường được gọi là **bật sẵn rồi loại trừ (opt-out)**. Cấu hình sau không đặt mặc định chung, giữ mặc định riêng của từng endpoint và chủ động tắt `env`, `beans`:

```yaml
management:
  endpoint:
    env:
      enabled: false
    beans:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
```

Đọc cấu hình theo hai câu hỏi độc lập:

- Với `env`, `beans`: có quyết định tắt riêng.
- Với HTTP: danh sách được chọn gồm `health`, `info`, `metrics`.

Ví dụ này thể hiện ý định: “giữ hành vi thông thường của Actuator, loại bỏ hai khả năng cụ thể, và cung cấp ba endpoint phục vụ vận hành”. Nó phù hợp khi nhóm muốn dựa vào mặc định của framework, đồng thời quản lý riêng những ngoại lệ.

### Trường hợp chủ động đặt `enabled-by-default: true`

Nếu muốn áp đặt mặc định chung là bật, cần viết rõ các ngoại lệ quan trọng:

```yaml
management:
  endpoints:
    enabled-by-default: true
    web:
      exposure:
        include:
          - health
          - info
          - metrics
  endpoint:
    shutdown:
      enabled: false
    env:
      enabled: false
    beans:
      enabled: false
```

Trong bảng thuộc tính 3.3, `shutdown` có mặc định riêng là `false`. Nhưng theo thứ tự ở mục 2, một giá trị chung `true` được đặt tường minh sẽ được xét trước mặc định riêng đó. Vì vậy ví dụ này tắt `shutdown` một cách tường minh, tránh hiểu nhầm rằng ngoại lệ mặc định của nó luôn thắng. [Mặc định thuộc tính `shutdown`](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

Hai cách viết ở mục này thể hiện hai ý định khác nhau: cách đầu tôn trọng mặc định riêng của endpoint; cách sau áp một mặc định chung rồi khai báo lại ngoại lệ. Khi rà soát cấu hình, hãy đọc ý định đó trước khi đếm số dòng YAML.

## 4. Cách thứ hai: tắt mặc định, chỉ bật endpoint được chỉ định

Cách này được gọi là **chỉ bật khi khai báo (opt-in)**. Đặt mặc định chung là `false`, sau đó bật từng ID cần dùng:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
          - info
          - metrics
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
    metrics:
      enabled: true
```

Có thể viết cùng chính sách bằng `application.properties`:

```properties
management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoint.metrics.enabled=true
management.endpoints.web.exposure.include=health,info,metrics
```

Dùng một định dạng nhất quán cho cấu hình thực tế. Nếu một nơi dùng YAML và nơi khác dùng properties, phải xét thêm thứ tự nguồn cấu hình thay vì coi chúng là hai bản có thể sửa độc lập.

Với ví dụ opt-in:

| Endpoint | Quyết định bật/tắt | Nằm trong danh sách HTTP |
| --- | --- | --- |
| `health` | Bật riêng | Có |
| `info` | Bật riêng | Có |
| `metrics` | Bật riêng | Có |
| `loggers` | Theo mặc định chung: tắt | Không |
| `shutdown` | Theo mặc định chung: tắt | Không |

Danh sách bật là một phần của hợp đồng vận hành: “ứng dụng này chủ động hỗ trợ ba khả năng đã chọn”. Khi sau này muốn dùng thêm `loggers`, người sửa phải trả lời cả hai câu hỏi: có bật nó không, và có cung cấp nó qua HTTP không?

Ví dụ phần bổ sung trong **cùng cây cấu hình**, sau khi quyết định cần `loggers`:

```properties
management.endpoint.loggers.enabled=true
management.endpoints.web.exposure.include=health,info,metrics,loggers
```

Đây là hai thay đổi giá trị trong cấu hình hiện có; không tạo thêm một khối YAML `management:` trùng ở cùng cấp.

`loggers` có cả khả năng đọc và thay đổi mức ghi log. Vì vậy quyết định đưa nó vào hợp đồng vận hành cần xét các thao tác được cho phép, thay vì chỉ thử một yêu cầu GET thành công. [API `loggers` 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 5. Chọn chính sách theo nhu cầu vận hành

| Tiêu chí | Giữ mặc định rồi tắt riêng | Tắt mặc định rồi bật riêng |
| --- | --- | --- |
| Cách diễn đạt ý định | Chấp nhận mặc định, quản lý ngoại lệ | Liệt kê chủ động từng khả năng cần dùng |
| Khi thêm nhu cầu quản trị | Xem endpoint có đang bị tắt riêng không | Bổ sung quyết định bật riêng |
| Câu hỏi khi nâng phiên bản/thêm thư viện | Mặc định hoặc endpoint khả dụng có đổi không? | Danh sách bật riêng có đáp ứng nhu cầu mới không? |
| Chi phí bảo trì | Ít dòng khi dùng nhiều khả năng | Rõ danh sách nhưng cần cập nhật có chủ đích |
| Tình huống phù hợp | Môi trường thử nghiệm hoặc hệ thống chủ động theo mặc định framework | Dịch vụ có danh sách quản trị được kiểm soát rõ |

Đây là tiêu chí thiết kế cho các ví dụ trong bài, không phải một quy tắc rằng mọi môi trường production đều phải dùng cùng cấu hình. Chẳng hạn:

- Một ứng dụng thử nghiệm đang khảo sát nhiều công cụ chẩn đoán có thể dùng opt-out, với danh sách HTTP được kiểm soát.
- Một dịch vụ thanh toán chỉ cho phép kiểm tra sức khỏe và thu thập số đo có thể dùng opt-in để ý định được nhìn thấy ngay trong cấu hình.
- Một nhóm chỉ muốn ngừng cung cấp `info` qua HTTP nhưng vẫn giữ qua JMX nên điều chỉnh công bố theo giao thức; không dùng thao tác tắt endpoint như thể nó chỉ tác động HTTP.

Để lựa chọn, hãy bắt đầu từ người dùng endpoint và nhiệm vụ của họ: hệ thống điều phối cần `health`, người trực vận hành cần dữ liệu nào, công cụ giám sát thu thập bằng cách nào? Sau đó ghi danh sách endpoint được bật và danh sách công bố cho từng giao thức.

Nếu chọn opt-in, nhớ đưa `health` vào danh sách bật khi nền tảng triển khai đang gọi nó. Việc kiểm soát chặt hơn nhưng vô tình làm mất đường kiểm tra sức khỏe vẫn là một lỗi vận hành.

## 6. Thực hành: thay đổi một điều kiện mỗi lần

### 6.1. Điều kiện của bài thử

Dùng một ứng dụng Spring Boot **3.3.x**, Java 17 trở lên; Java 21 phù hợp. Ứng dụng có hai dependency được quản lý phiên bản bởi Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đây là đoạn dependency trong một dự án Spring Boot đã được thiết lập plugin và lớp khởi động, không phải toàn bộ `build.gradle`. Thực hành không cần viết controller nghiệp vụ.

Để bảng kết quả dễ quan sát, giả định ứng dụng thử:

- Chạy trực tiếp trên `localhost:8080`, dùng base path `/actuator` mặc định.
- Không thêm Spring Security hoặc proxy thay đổi phản hồi.
- Không có nguồn cấu hình khác ghi đè các thuộc tính đang thử.
- Dùng cấu hình thông thường của starter, không có endpoint tùy chỉnh mang cùng ID.

Nếu hệ thống thật có xác thực, dùng thông tin đăng nhập hợp lệ và kiểm tra thêm quy tắc phân quyền; không tắt cơ chế bảo vệ chỉ để khớp bảng thử nghiệm.

### 6.2. Bắt đầu từ cấu hình opt-in

Đưa cấu hình YAML ở mục 4 vào `src/main/resources/application.yml`, khởi động lại ứng dụng, rồi chạy:

```powershell
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/info
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/metrics
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/loggers
```

Mỗi dòng là một lệnh chạy riêng trong PowerShell trên Windows. `-o NUL` bỏ phần thân, `-w` in mã HTTP; các lệnh không tự thêm ký tự xuống dòng. Với giả định sức khỏe là `UP`, kết quả dự kiến theo thứ tự là:

| URL | Mã HTTP dự kiến | Điều được kiểm tra |
| --- | --- | --- |
| `/actuator/health` | `200` | Bật riêng và công bố |
| `/actuator/info` | `200` | Bật riêng và công bố |
| `/actuator/metrics` | `200` | Bật riêng và công bố |
| `/actuator/loggers` | `404` | Không thuộc chính sách bật/công bố của bài thử |

Để xem phần thân của `health`:

```powershell
curl.exe -s http://localhost:8080/actuator/health
```

Nếu trạng thái tổng hợp là `UP` và không công khai chi tiết, phản hồi JSON thường thấy là:

```json
{"status":"UP"}
```

Đây là kết quả dự kiến theo điều kiện nêu trên, không phải cam kết rằng mọi ứng dụng đều khỏe. Cấu trúc phần thân và việc hiện chi tiết phụ thuộc cấu hình sức khỏe. [API `health`](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

`info` có thể trả về `{}` nếu không có thông tin đóng góp. HTTP 200 với một đối tượng rỗng vẫn khác việc không có đường dẫn; muốn có thông tin phiên bản phải cung cấp dữ liệu tương ứng. [API `info` và các thành phần đóng góp](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html).

### 6.3. Chứng minh bật và công bố là hai điều kiện

Thực hiện từng tình huống từ cấu hình mục 4 và khởi động lại sau mỗi thay đổi:

| Tình huống | Thay đổi | Kết quả dự kiến cho `GET /actuator/metrics` |
| --- | --- | --- |
| A | Không đổi | `200` |
| B | Xóa cấu hình riêng `metrics.enabled: true`, giữ `metrics` trong `include` | `404`: mặc định chung đang tắt |
| C | Khôi phục bật riêng, bỏ `metrics` khỏi `include` | `404`: không được công bố qua HTTP |
| D | Khôi phục bật riêng và `include`, thêm `exclude: metrics` dưới `web.exposure` | `404`: danh sách loại trừ thắng danh sách chọn |
| E | Gỡ thay đổi loại trừ ở D, giữ bật riêng và `include` | `200` |

Các tình huống này là suy luận áp dụng quy tắc cấu hình cho môi trường thử đã mô tả. Cùng một mã 404 có thể đến từ hai quyết định khác nhau; vì vậy chỉ nhìn mã phản hồi sẽ không đủ để biết cấu hình nào sai.

Điểm cần phân biệt thêm: tắt endpoint `metrics` là thay đổi khả năng truy vấn Actuator này. Không thể từ đó kết luận toàn bộ việc ghi nhận hoặc xuất số đo của Micrometer đã bị tắt; các registry và cấu hình xuất số đo có cơ chế riêng. [Cơ chế metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 7. Lỗi thường gặp và cách tìm nguyên nhân

### Chỉ cấu hình danh sách công bố

```properties
management.endpoints.enabled-by-default=false
management.endpoints.web.exposure.include=health,metrics
```

Người viết muốn dùng `health`, `metrics` nhưng chưa khai báo bật riêng. Cách sửa cho đúng ý định đó:

```properties
management.endpoint.health.enabled=true
management.endpoint.metrics.enabled=true
```

### Nhầm cấp cấu hình

- Sai: `management.endpoints.health.enabled=true`.
- Đúng: `management.endpoint.health.enabled=true`.
- Với danh sách HTTP, dùng `management.endpoints.web.exposure.include`.

Khi có nhiều cấu hình tương tự, kiểm tra đường dẫn thuộc tính đầy đủ thay vì chỉ tìm chữ `enabled`.

### Dùng ký tự đại diện mà hiểu là bật tất cả

`management.endpoints.web.exposure.include=*` là lựa chọn công bố. Nếu mặc định chung đang tắt và không có bật riêng, ký tự đại diện không thay thế các quyết định bật. Trong YAML, nếu thực sự cần ký tự đại diện, viết `include: "*"` với dấu nháy.

Một cấu hình dễ kiểm tra thường liệt kê rõ ID phục vụ nhu cầu hiện tại; không cần dùng ký tự đại diện chỉ vì muốn tiết kiệm vài dòng.

### Cấu hình trong file khác với giá trị hiệu lực

Ứng dụng có thể nhận thuộc tính từ file theo profile, biến môi trường hoặc tham số dòng lệnh. Vì vậy khi file YAML trông đúng nhưng hành vi khác dự kiến, kiểm tra profile đang hoạt động và các nguồn ghi đè của cùng khóa.

Ví dụ, tham số dòng lệnh đặt `--management.endpoint.metrics.enabled=false` có thể ghi đè giá trị bật trong file cấu hình. Cần phân biệt **ưu tiên giữa các nguồn cho cùng một khóa** với **ưu tiên giá trị riêng so với giá trị chung ở mục 2**. Đây là hai bước giải quyết khác nhau. [Thứ tự nguồn cấu hình Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### Đọc sai mã HTTP hoặc thay đổi cấu hình mà chưa áp dụng lại

Với ứng dụng thông thường, áp dụng cấu hình endpoint trong lần khởi động và khởi động lại sau khi đổi file; không giả định Actuator tự tải lại các giá trị này.

Nếu có sự cố, kiểm tra theo thứ tự:

1. Đúng ứng dụng, cổng và đường dẫn đang chạy chưa?
2. Endpoint cần thư viện hoặc thành phần hỗ trợ nào, đã có chưa?
3. Giá trị bật/tắt hiệu lực là gì?
4. ID có được chọn và không bị loại trừ ở đúng giao thức không?
5. Yêu cầu có đi qua xác thực, phân quyền hoặc proxy không?

`401` hoặc `403` thường hướng việc kiểm tra tới cơ chế bảo vệ. `404` cần xét đường dẫn và các điều kiện endpoint. Trong hệ thống có tùy biến, mã HTTP đơn lẻ không đủ chứng minh chính xác một nguyên nhân.

## 8. Tự kiểm tra quyết định của mình

**Tình huống 1:** Dịch vụ chỉ cần `health` và `metrics`; nhóm muốn mọi endpoint khác phải được đề xuất riêng.

Chọn opt-in: đặt mặc định chung là `false`, bật riêng hai ID và liệt kê hai ID trong công bố HTTP. Sau đó thử cả URL được phép lẫn một URL ngoài danh sách.

**Tình huống 2:** Ứng dụng đang dùng opt-in và cần thêm `info`. Một thay đổi chỉ thêm `info` vào `web.exposure.include` có đầy đủ không?

Chưa. Cần thêm quyết định `management.endpoint.info.enabled=true`; sau đó kiểm tra đường dẫn và dữ liệu phản hồi.

**Tình huống 3:** Nhóm nói “giữ nguyên mặc định của Spring Boot” nhưng thêm `enabled-by-default: true`. Có thể xem đó là thay đổi chỉ làm cấu hình rõ hơn không?

Không nên. Thứ tự lựa chọn trong 3.3 cho phép giá trị chung này thắng mặc định riêng của endpoint. Hãy bỏ giá trị chung nếu ý định là giữ mặc định từng endpoint, hoặc khai báo rõ các ngoại lệ cần tắt.

**Tình huống 4:** `metrics` trả 404 sau khi chuyển sang opt-in. Có nên lập tức đổi danh sách công bố thành `"*"` không?

Hãy kiểm tra bật riêng trước, rồi danh sách công bố và loại trừ. Thay đổi từng điều kiện sẽ chỉ ra nguyên nhân và giữ ý định cấu hình dễ đọc.
