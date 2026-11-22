# Xác định tập endpoint tối thiểu cho từng môi trường và vai trò vận hành

## 1. Bắt đầu từ quyết định vận hành cần đưa ra

Một dịch vụ đang chạy cần trả lời những câu hỏi khác nhau: có nên nhận thêm yêu cầu, có cần khởi động lại, phiên bản nào vừa được triển khai, và tài nguyên đang biến động ra sao. Spring Boot Actuator cung cấp các điểm truy cập quản trị (management endpoint) để hỗ trợ những việc đó. Người vận hành phải chọn phần thực sự cần cho dịch vụ của mình.

**Tập endpoint tối thiểu** là tập đủ để thực hiện các nhiệm vụ đã xác định, với phạm vi dữ liệu và quyền thao tác nhỏ nhất cần thiết. Nó không đồng nghĩa với một danh sách cố định áp dụng cho mọi ứng dụng.

Ví dụ, dịch vụ đặt hàng chạy trên Kubernetes, được Prometheus thu thập số liệu, có thể cần thường trực:

- Hai đường dẫn kiểm tra khả năng sống và khả năng nhận yêu cầu.
- Một đường dẫn xuất số liệu cho bộ thu thập.
- Thông tin phiên bản đã được chọn lọc, nếu quy trình xác minh triển khai cần đến.

Trong khi đó, một chương trình xử lý theo lô không có máy chủ HTTP có thể gửi số liệu ra ngoài và dùng kết quả chạy của nền tảng. Chương trình đó không cần thêm máy chủ HTTP chỉ để có cùng tập endpoint.

Bài này dùng thuộc tính cấu hình của **Spring Boot 3.3.x**. Các ma trận bên dưới là **phương án thiết kế minh họa**, cần điều chỉnh theo nhiệm vụ, hạ tầng và dữ liệu thực tế.

## 2. Phân biệt bốn lớp của một quyết định truy cập

Trong Spring Boot 3.3, `enabled` quyết định bật endpoint; `exposure` quyết định công bố qua HTTP/JMX. Mặc định chỉ `health` được công bố; `exclude` ưu tiên hơn `include`. Hai lớp này chưa quyết định người gọi được làm gì. [Quy tắc endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

Có thể xem một yêu cầu quản trị đi qua bốn cổng:

```text
Có endpoint và đủ điều kiện khởi tạo?
        ↓
Được công bố trên giao thức đang dùng?
        ↓
Nguồn gọi kết nối được tới cổng/đường dẫn?
        ↓
Danh tính được phép dùng phương thức và dữ liệu đó?
```

Ví dụ, cho phép `prometheus` trong danh sách HTTP không tự tạo tài khoản cho Prometheus. Cho phép một tài khoản đọc endpoint cũng không tự mở tuyến mạng từ nơi đặt bộ thu thập.

Cần ghi nhận từng lớp bằng một quyết định riêng:

| Lớp | Câu hỏi phải trả lời |
| --- | --- |
| Khả năng có sẵn | Thư viện, cấu hình và tài nguyên cần thiết đã có chưa? |
| Công bố | Endpoint nào được mở qua HTTP, endpoint nào qua JMX? |
| Kết nối mạng | Từ đâu được kết nối, qua cổng nào, có qua proxy không? |
| Phân quyền và dữ liệu | Ai được gọi phương thức nào, được thấy dữ liệu nào? |

Tên endpoint, đường dẫn, phương thức HTTP và độ chi tiết phản hồi là các yếu tố khác nhau. Một chính sách chỉ ghi “nhóm vận hành được dùng Actuator” còn quá rộng để triển khai và kiểm chứng.

## 3. Lập danh sách nhu cầu trước khi lập danh sách endpoint

Với mỗi nhu cầu, trả lời sáu câu hỏi:

1. **Ai hoặc hệ thống nào sử dụng?**
2. **Dữ liệu giúp đưa ra quyết định gì?**
3. **Cần thường trực hay chỉ khi điều tra sự cố?**
4. **Chỉ đọc hay có thay đổi trạng thái?**
5. **Dữ liệu được phép rời khỏi phạm vi nào?**
6. **Ai chịu trách nhiệm rà soát và thu hồi quyền?**

Một bản ghi quyết định có thể như sau:

| Nhu cầu | Bên sử dụng | Tần suất | Cách đáp ứng dự kiến |
| --- | --- | --- | --- |
| Ngừng gửi yêu cầu vào bản sao chưa sẵn sàng | Bộ điều phối | Liên tục | Health group readiness |
| Xác định bản sao cần khởi động lại | Bộ điều phối | Liên tục | Health group liveness |
| Theo dõi độ trễ và bộ nhớ theo thời gian | Bộ thu thập số liệu | Theo chu kỳ | Prometheus hoặc cơ chế xuất số liệu đang dùng |
| Xác nhận đúng bản phát hành | Người triển khai | Sau triển khai | Metadata bản phát hành đã chọn lọc |
| Tìm nguyên nhân nghẽn luồng | Người trực sự cố | Khi có sự cố | Thu thập thread dump theo quyền tạm thời |
| Tăng log của một gói để điều tra | Người được cấp quyền thay đổi | Khi có sự cố | Thao tác có giới hạn và phương án hoàn nguyên |

Nếu bảng điều khiển đã trả lời câu hỏi về bộ nhớ, nhóm hỗ trợ có thể chỉ cần quyền xem bảng điều khiển. Họ không nhất thiết cần thêm tài khoản gọi endpoint trực tiếp.

Nếu một endpoint không gắn với người dùng, quyết định hoặc quy trình cụ thể, chưa đưa nó vào tập thường trực.

## 4. Ma trận theo môi trường

Giả sử dịch vụ minh họa có HTTP, dùng Kubernetes ở staging/production và dùng Prometheus để thu thập số liệu.

| Khả năng | Máy cá nhân, dữ liệu giả | Môi trường kiểm thử dùng chung | Staging | Production thường trực |
| --- | --- | --- | --- | --- |
| Health cơ bản | Có | Có, giới hạn thông tin | Có | Có nếu có bên sử dụng |
| Liveness/readiness | Khi thử quy trình triển khai | Khi kiểm thử bộ điều phối | Có, giống production | Có cho bộ điều phối |
| `info` | Khi cần | Metadata chọn lọc | Khi quy trình triển khai cần | Khi quy trình triển khai cần |
| `prometheus` | Khi chạy thử bộ thu thập | Khi có bộ thu thập | Có trong giả định này | Có trong giả định này |
| `metrics` | Có thể mở để khảo sát | Mở theo nhu cầu kiểm thử | Theo nhu cầu điều tra | Không nằm trong tập thường trực này |
| `loggers` | Có thể dùng | Quyền đọc/ghi riêng | Thử quy trình ứng cứu có kiểm soát | Chỉ mở tạm khi cần |
| `env`, `configprops`, `beans`, `mappings` | Chọn từng endpoint cần học/điều tra | Không mở rộng cho mọi người | Chỉ điều tra có phạm vi | Không mở thường trực |
| `threaddump`, `heapdump`, `logfile` | Theo bài thử | Cấp quyền theo yêu cầu | Theo quy trình điều tra | Theo quy trình ứng cứu và quản lý tệp |
| `shutdown` | Chỉ khi đang thử chức năng đó | Không cần cho thiết kế này | Không | Không |

Có ba điểm cần giải thích khi duyệt ma trận:

**Môi trường kiểm thử dùng chung vẫn có ranh giới quyền.** Một tài khoản kiểm thử nghiệp vụ không tự có quyền quản trị ứng dụng. Nếu dùng dữ liệu thật đã sao chép, phải đánh giá dữ liệu theo mức nhạy cảm thực tế.

**Staging nên chứng minh chính sách production hoạt động.** Nếu staging mở tất cả endpoint nhưng production đóng phần lớn, một lần kiểm thử thành công ở staging chưa chứng minh bộ thu thập và probe vẫn hoạt động ở production.

**Máy cá nhân chỉ là phạm vi tin cậy khi kết nối và dữ liệu đúng giả định.** Chạy profile dev trên máy chủ dùng chung hoặc chuyển tiếp cổng ra ngoài làm thay đổi giả định đó.

### Chọn đúng đường xuất số liệu

`metrics` phục vụ khảo sát các số đo hiện có, không phải API để scrape làm kho số liệu production. [REST API metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)

`prometheus` xuất định dạng cho Prometheus scrape. [REST API Prometheus](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)

Endpoint này cần `micrometer-registry-prometheus`. Nếu hệ thống dùng cơ chế xuất số liệu khác, đánh giá lại nhu cầu mở nó. [Cấu hình hệ thống số liệu của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)

Ví dụ bổ sung dependency trong dự án Gradle đã được Spring Boot quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Đây là đoạn bổ sung cho dự án Spring Boot hiện có, không phải một `build.gradle` độc lập. Chỉ đưa registry này vào khi kiến trúc thu thập thực sự dùng nó.

## 5. Ma trận theo vai trò: quyền đọc cũng cần có phạm vi

Trong thiết kế minh họa, các vai trò sau được cấp độc lập; quyền không tự bao hàm nhau:

| Vai trò | Quyền thường trực đề xuất | Điều không được suy ra từ vai trò |
| --- | --- | --- |
| Khách bên ngoài | Không có quyền quản trị | Không được xem số liệu, metadata nội bộ hoặc dump |
| Bộ điều phối | GET đúng đường dẫn probe | Không được xem toàn bộ thành phần health |
| Bộ thu thập số liệu | GET `/actuator/prometheus` | Không được đọc `env`, dump hoặc đổi log |
| Người hỗ trợ | Xem bảng điều khiển và metadata đã duyệt | Không mặc nhiên được gọi mọi endpoint |
| Người trực sự cố | Quyền health chi tiết; quyền điều tra được cấp thêm khi cần | Không tự có quyền thay đổi trạng thái |
| Người thao tác ứng cứu | Quyền thay đổi cụ thể, có thời hạn | Không có quyền quản trị mọi ứng dụng và mọi môi trường |
| Tài khoản triển khai | Kiểm tra phiên bản và trạng thái phục vụ theo quy trình | Không cần quyền `shutdown` chỉ vì có quyền triển khai |

Tên vai trò trong bảng là mô hình tổ chức, không phải các role được Spring Boot tự tạo.

Hãy viết quyền đủ cụ thể để có thể kiểm thử:

```text
Môi trường: production
Danh tính: bộ thu thập số liệu của dịch vụ đặt hàng
Nguồn mạng: vùng triển khai bộ thu thập đã duyệt
Đích: cổng quản trị 9001
Đường dẫn: /actuator/prometheus
Phương thức: GET
Quyền thay đổi trạng thái: không
Chủ sở hữu: nhóm nền tảng
Rà soát lại: khi thay đổi kiến trúc thu thập hoặc quyền mạng
```

Không dùng chung danh tính giữa bộ thu thập tự động và người trực sự cố. Khi một danh tính bị thu hồi, phạm vi ảnh hưởng sẽ rõ ràng hơn và lịch sử truy cập cũng dễ giải thích hơn.

### Tách đọc khỏi thay đổi trạng thái

Endpoint `loggers` hỗ trợ GET để đọc và POST để thay đổi mức log. [REST API loggers](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html)

Vì vậy, cho phép đường dẫn chưa đủ: quyền “xem mức log” và quyền “đổi mức log” phải là hai quyết định. Một quy trình đổi mức log cần ghi:

- Gói/logger cụ thể và mức trước thay đổi.
- Mục đích, người thực hiện và thời điểm hết hạn.
- Giới hạn thời gian thu thập, dung lượng và dữ liệu có thể xuất hiện.
- Cách khôi phục và cách xác nhận đã khôi phục.

Ví dụ, tăng DEBUG trong 10 phút cho một gói xử lý thanh toán khác hẳn việc bật TRACE cho toàn ứng dụng trong nhiều giờ. Cùng một endpoint nhưng phạm vi tác động khác nhau.

## 6. Cấu hình danh sách cho phép theo profile

Các tệp dưới đây là **cấu hình minh họa để ghép vào ứng dụng Spring Boot 3.3 hiện có**, không chứa lớp xác thực hay chính sách mạng. Chỉ triển khai lên môi trường dùng chung sau khi đã hiện thực và kiểm thử ma trận quyền ở phần 5.

### 6.1. Cấu hình chung chỉ bật health

`application.yml`:

```yaml
spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: [health]
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
      show-components: never
```

Đây là lựa chọn bật từng endpoint theo nhu cầu. Danh sách `include` dùng **ID endpoint**, không dùng URL. [Bật và công bố endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

JMX có chính sách riêng. `spring.jmx.enabled` chỉ chi phối phần quản lý JMX do Spring cung cấp; vẫn cần rà soát cấu hình JMX của JVM và thư viện khác nếu có. [Quản trị qua JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html)

Tắt discovery chỉ là lựa chọn giảm trang liệt kê liên kết. Việc kiểm chứng quyền vẫn phải gọi thẳng các đường dẫn, không chỉ xem trang `/actuator`.

### 6.2. Máy cá nhân: mở đúng công cụ đang dùng

`application-dev.yml`:

```yaml
management:
  server:
    port: 9001
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: [health, info, metrics, loggers]
  endpoint:
    info:
      enabled: true
    metrics:
      enabled: true
    loggers:
      enabled: true
    health:
      show-details: always
      show-components: always
```

Ví dụ dành cho máy cá nhân với dữ liệu giả. Cổng quản trị riêng có thể gắn vào loopback bằng `management.server.address`; địa chỉ quản trị riêng yêu cầu cổng khác cổng ứng dụng. [Cổng và địa chỉ quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-address)

Nếu cần `env` để điều tra, bổ sung chính endpoint đó và đánh giá dữ liệu trả về. Không đổi thành mở tất cả chỉ để tiết kiệm vài dòng cấu hình.

### 6.3. Production: health, số liệu và metadata nếu có nhu cầu

`application-prod.yml`:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: [health, prometheus, info]
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: [OPS_HEALTH]
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          show-details: never
          show-components: never
        readiness:
          show-details: never
          show-components: never
    prometheus:
      enabled: true
    info:
      enabled: true
```

Cấu hình này kế thừa tệp chung: các endpoint khác vẫn không được bật mặc định. Nếu không cần `info`, bỏ nó khỏi cả danh sách công bố lẫn phần bật endpoint.

Trong ví dụ, `info` chỉ được dùng khi nhóm triển khai đã chọn lọc dữ liệu từ các `InfoContributor`. [Cấu trúc thông tin ứng dụng](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html)

Không đưa đường dẫn máy nội bộ, cấu hình kết nối hay thông tin nhận dạng người dùng vào metadata bản phát hành.

Quyền xem chi tiết health và quyền đi vào đường dẫn là hai quyết định riêng; `health.roles` không cấp quyền truy cập endpoint khác. [Thông tin phản hồi health](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html), [thuộc tính health](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

Cần cấu hình mạng để cổng 9001 chỉ nhận nguồn đã duyệt. **Đổi cổng không tạo ranh giới tin cậy.** Nếu Prometheus chạy ở pod khác, gắn cổng quản trị vào `127.0.0.1` sẽ không phù hợp với cách kết nối đó.

Với staging, dùng cùng tập endpoint và quy tắc quyền như production, nhưng dùng danh tính, điểm thu thập và cấu hình mạng của staging. Không đồng thời kích hoạt profile dev trong lần kiểm chứng chính sách production.

## 7. Health tối thiểu phải đúng với hành động phía sau

Liveness trả lời câu hỏi về khả năng sống; readiness trả lời câu hỏi có nên tiếp tục nhận yêu cầu. Kubernetes xử lý probe thất bại theo loại probe và các ngưỡng đã cấu hình. [Cơ chế probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

Với Spring Boot, các health group có đường dẫn `/actuator/health/liveness` và `/actuator/health/readiness`. Bật additional paths tạo `/livez`, `/readyz` trên cổng ứng dụng. [Spring Boot health probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Trong thiết kế có cổng quản trị riêng, chọn kiểm tra trên cổng ứng dụng để phép kiểm tra đi qua nơi nhận yêu cầu thật. Dù vậy, phản hồi probe thành công vẫn chưa chứng minh mọi chức năng nghiệp vụ hoạt động đúng.

Đoạn sau nằm bên trong một phần tử `containers[]` của manifest Kubernetes; đây không phải manifest triển khai hoàn chỉnh:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 9001

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

Các con số chỉ là điểm bắt đầu cho bài thử; cần đo thời gian khởi động và đặc điểm tải. Startup probe trì hoãn liveness/readiness cho đến khi kiểm tra khởi động thành công. [Hành vi startup probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

Để kubelet dùng được ví dụ, các đường dẫn probe phải cho phép cách gọi thực tế của kubelet. Đồng thời, tuyến public không được tự động chuyển tiếp các đường dẫn quản trị hoặc probe ra ngoài.

Hãy xét một sự cố cơ sở dữ liệu chung:

- Nếu khởi động lại ứng dụng không sửa được cơ sở dữ liệu, dùng sự cố đó làm lý do restart mọi bản sao có thể làm phục hồi khó hơn.
- Với readiness, cần quyết định ứng dụng có còn phục vụ được chức năng hữu ích hay có cơ chế dự phòng không.
- Giữ health tổng hợp cho quan sát và cảnh báo khi cần; không gán cùng một health check cho mọi hành động vận hành.

Việc đưa hệ thống phụ thuộc vào readiness cần quyết định theo dịch vụ. Liveness không nên phụ thuộc vào hệ thống ngoài. [Phạm vi health group của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

## 8. Hiện thực phân quyền mà không làm rộng phạm vi ngoài dự kiến

Danh sách endpoint trong YAML là đầu vào cho chính sách quyền, không phải kết quả phân quyền hoàn chỉnh.

Với ứng dụng Servlet, `EndpointRequest` cung cấp matcher theo endpoint. [API EndpointRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

Khi tự khai báo `SecurityFilterChain`, phải tự bảo đảm cả đường quản trị và phần còn lại của ứng dụng được bảo vệ; không tiếp tục dựa vào cấu hình bảo mật Actuator tự động. [Bảo mật Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

Khi chuyển ma trận quyền sang cấu hình thực tế, cần kiểm tra:

1. Quy tắc GET cho probe chỉ bao phủ đúng đường dẫn đã duyệt.
2. Danh tính bộ thu thập chỉ gọi được điểm xuất số liệu.
3. Người xem health chi tiết được ánh xạ đúng vai trò.
4. Quyền đọc không vô tình cho phép POST/DELETE.
5. Mọi trường hợp ngoài danh sách được xử lý bằng quy tắc từ chối phù hợp.
6. Quy tắc của API nghiệp vụ vẫn được kiểm chứng sau thay đổi.

Các điểm này là yêu cầu triển khai của thiết kế, không phải mã Java có thể sao chép trực tiếp. Ứng dụng WebFlux cần cơ chế bảo mật reactive tương ứng; không dùng nguyên cấu hình Servlet.

Không xem một phản hồi 403 của thao tác ghi là bằng chứng duy nhất cho việc phân quyền đúng. Cần biết chính xác lớp nào đã từ chối và vẫn kiểm chứng quyền khi các điều kiện hợp lệ khác đã được đáp ứng.

## 9. Kiểm chứng từ cấu hình hiệu lực đến yêu cầu thật

### 9.1. Kiểm tra cấu hình đang thực sự chạy

Rà soát profile đang kích hoạt, biến môi trường, tham số khởi động và cấu hình ngoài tệp. Đặc biệt kiểm tra có nguồn nào mở rộng danh sách endpoint hoặc thay đổi các thuộc tính nhạy cảm hay không.

Không chứng minh cấu hình production chỉ bằng cách đọc `application-prod.yml`. Bằng chứng cần gắn với bản dựng và cách khởi động thực tế.

### 9.2. Lập ca kiểm tra cho cả quyền được cấp và quyền bị từ chối

| Ca kiểm tra | Tiêu chí chấp nhận |
| --- | --- |
| Kubelet gọi readiness | Đúng trạng thái sẵn sàng; không lộ chi tiết |
| Bộ thu thập dùng danh tính hợp lệ | Đọc được số liệu, định dạng đúng |
| Danh tính bộ thu thập gọi `env` | Không đọc được dữ liệu |
| Người có quyền health chi tiết | Chỉ thấy thông tin đúng phạm vi được duyệt |
| Người thường gọi endpoint quản trị | Không được cấp quyền ngoài ma trận |
| Nguồn mạng chưa được duyệt gọi cổng 9001 | Không kết nối được theo chính sách mạng |
| Gọi `loggers`, `heapdump`, `shutdown` trong production thường trực | Không thực hiện được thao tác hoặc lấy dữ liệu |
| Gọi qua địa chỉ public và gọi trực tiếp trong mạng nội bộ | Cả hai tuyến đều tuân thủ chính sách tương ứng |

Các câu lệnh minh họa dưới đây dành cho máy đang chạy ứng dụng, có `curl`/ `curl.exe` thực và các cổng đúng như cấu hình:

```bash
curl --include --max-time 3 http://127.0.0.1:8080/readyz
curl --include --max-time 3 http://127.0.0.1:9001/actuator/health
curl --include --max-time 3 http://127.0.0.1:9001/actuator/env
```

Cần chạy thêm từ vị trí của kubelet, bộ thu thập và một nguồn không được phép. Gọi thành công từ localhost chỉ chứng minh một tuyến kết nối.

Với health chỉ hiển thị trạng thái, khi nhóm đang UP, phần thân có thể là:

```json
{"status":"UP"}
```

Không cố định độ dài phản hồi, mọi header hoặc giá trị số liệu để làm kết quả mong đợi. Hãy kiểm tra ý nghĩa của phản hồi theo cấu hình và trạng thái ứng dụng.

Đối với yêu cầu phải bị chặn, kết quả có thể là 401, 403, 404 hoặc lỗi kết nối tùy lớp xử lý. Một 404 đơn lẻ không chứng minh endpoint đã bị tắt: có thể sai đường dẫn, sai cổng hoặc bị proxy xử lý. Cần đối chiếu cấu hình hiệu lực, tuyến mạng và danh tính dùng để thử.

### 9.3. Kiểm tra phản hồi và chi phí sử dụng

Sau khi kiểm tra mã trạng thái, tiếp tục xem:

- Health có lộ tên máy, thành phần hoặc thông tin kết nối ngoài chính sách không?
- Metadata phiên bản có chứa dữ liệu nội bộ không cần thiết không?
- Nhãn số liệu có chứa định danh người dùng, mã đơn hàng hoặc bí mật không?
- Tần suất probe/scrape có phù hợp với chi phí xử lý không?
- Tài khoản hoặc đường dẫn mới có đang được các công cụ cũ sử dụng không?

Chỉ giảm tập endpoint sau khi biết ai đang dùng chúng. Việc đóng một endpoint không còn tài liệu nhưng đang được giám sát sử dụng có thể tạo khoảng trống cảnh báo.

## 10. Endpoint chẩn đoán: mở có thời hạn và đóng có bằng chứng

Đối với endpoint không nằm trong tập thường trực, chuẩn bị quy trình trước khi có sự cố:

1. Ghi triệu chứng và câu hỏi điều tra; chọn công cụ trả lời được câu hỏi đó.
2. Xác định bản sao ứng dụng, endpoint, phương thức và thời hạn.
3. Chọn người thao tác, nguồn mạng và nơi lưu dữ liệu.
4. Đánh giá chi phí thu thập; hạn chế số lần gọi hoặc kích thước khi phù hợp.
5. Thực hiện trên đúng môi trường, ghi nhận thay đổi.
6. Khôi phục cấu hình, thu hồi quyền và kiểm tra đường dẫn đã đóng.
7. Xử lý tệp thu thập theo chính sách lưu giữ và truy cập.

Ví dụ: cần điều tra một bản sao bị treo, có thể thu thập bằng công cụ JVM nội bộ thay vì mở thêm endpoint HTTP. Nếu chọn endpoint, vẫn cần giới hạn đối tượng có thể lấy dữ liệu và cách bảo quản kết quả.

Với heap dump hoặc log, nên giả định tệp có thể chứa dữ liệu nhạy cảm cho đến khi đã đánh giá. Quyền tạo tệp, quyền tải tệp và quyền đọc tệp sau đó đều cần được xem xét.

Đừng kết thúc quy trình bằng câu “đã xử lý xong”. Kết quả cần chỉ ra endpoint nào đã đóng, quyền nào đã thu hồi, mức log nào đã khôi phục và tệp điều tra được lưu ở đâu theo chính sách.

## 11. Thực hành: chọn tập tối thiểu và giải thích được từng lựa chọn

**Tình huống:** dịch vụ đặt hàng có ba bản sao trên Kubernetes. Prometheus thu thập số liệu. Nhóm hỗ trợ có quyền xem dashboard. Nhóm triển khai cần xác minh phiên bản sau mỗi lần phát hành.

Hãy lập ba sản phẩm:

1. Ma trận endpoint cho máy cá nhân, kiểm thử dùng chung, staging và production.
2. Ma trận danh tính × đường dẫn × phương thức × mức dữ liệu.
3. Danh sách kiểm tra được cấp quyền, bị từ chối và đóng quyền sau sự cố.

**Một phương án hợp lý cho production thường trực:**

- Dùng `health` để cung cấp các probe đã chọn; phản hồi probe chỉ có thông tin cần cho quyết định.
- Bật `prometheus` vì bài toán có bộ thu thập Prometheus.
- Bật `info` nếu đó là cách đã chọn để xác minh phiên bản, với nội dung được duyệt.
- Nhóm hỗ trợ dùng dashboard; không tự động được cấp quyền Actuator.
- Chẩn đoán sâu và thay đổi mức log đi theo quy trình cấp quyền tạm thời.

**Biến thể cần tự giải thích:**

- Nếu số liệu được xuất qua hệ thống khác và không có Prometheus scrape, có còn cần endpoint `prometheus` không?
- Nếu nền tảng triển khai đã cung cấp metadata phiên bản đáng tin cậy, có còn cần `info` không?
- Nếu một chức năng có thể hoạt động khi cache lỗi, đưa cache vào readiness sẽ gây hậu quả gì?
- Nếu mở endpoint mới ở staging nhưng không có nhu cầu production, sẽ kiểm thử cơ chế đóng nó như thế nào?

Kết quả tốt là mỗi endpoint đều có lý do tồn tại, bên sử dụng, giới hạn quyền và ca kiểm chứng. Khi nhu cầu thay đổi, có thể chỉ ra chính xác quyết định nào cần được xem xét lại.
