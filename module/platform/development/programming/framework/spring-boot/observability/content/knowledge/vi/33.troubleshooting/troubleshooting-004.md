# Khắc phục lỗi sai `service.name` trong Spring Boot Observability

Trong một hệ thống Spring Boot có nhiều service, tên service là thuộc tính nhận diện giúp gom log, metric và trace về đúng ứng dụng. Khi tên này sai hoặc không nhất quán, dashboard có thể hiển thị một service thành nhiều service khác nhau, trace bị phân tán, hoặc dữ liệu của nhiều ứng dụng bị gộp chung. Việc điều tra cũng khó hơn vì log và metric không còn khớp với trace đang được xem.

Bài này thuộc chương **Chẩn đoán sự cố** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; trong đó có propagation ngữ cảnh, tag và cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực. Nội dung tập trung vào cách nhận biết, truy tìm nguồn cấu hình và sửa lỗi tên service.

## 1. Hiểu đúng các tên định danh

Trước khi sửa cấu hình, cần phân biệt tên ứng dụng trong Spring Boot với thuộc tính tài nguyên mà hệ thống telemetry sử dụng.

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `spring.application.name` | Tên logic của ứng dụng Spring Boot, thường được dùng trong cấu hình và tích hợp của ứng dụng | `orders-service` |
| `service.name` | Tên logic của service trong OpenTelemetry Resource; backend dùng nó để nhóm span và dữ liệu telemetry theo service | `orders-service` |
| `service.namespace` | Không gian tên giúp phân biệt các service có cùng tên ở những miền hoặc hệ thống khác nhau | `commerce` |
| `service.instance.id` | Định danh một instance đang chạy, chẳng hạn một pod hoặc một tiến trình | `orders-service-7f9c8d6b5-x2kq4` |
| `deployment.environment.name` | Môi trường triển khai của service | `production` |

`service.name` mô tả **ứng dụng logic**, vì vậy các replica của cùng một service thường dùng chung giá trị. Mỗi replica có thể có `service.instance.id` riêng. Nếu gán tên pod, hostname hoặc mã request vào `service.name`, backend sẽ coi các instance là những service khác nhau và làm phân mảnh dữ liệu.

`spring.application.name` và `service.name` có quan hệ gần nhau nhưng không nên mặc định rằng mọi thư viện, exporter hoặc agent đều tự ánh xạ hai thuộc tính này giống nhau. Spring Boot, Micrometer, OpenTelemetry SDK, Java agent và OpenTelemetry Collector có thể tham gia vào các bước cấu hình khác nhau. Cần xác minh Resource thực tế được gửi đi thay vì chỉ nhìn một dòng trong `application.yml`.

## 2. Dấu hiệu nhận biết tên service bị sai

Một số biểu hiện thường gặp:

- Trace backend xuất hiện `unknown_service`, `unknown_service:java`, tên mặc định hoặc tên không giống tên ứng dụng.
- Cùng một ứng dụng nhưng trace ở môi trường local, staging và production lại nằm dưới các tên service khác nhau ngoài dự kiến.
- Một service xuất hiện thành nhiều mục trong danh sách service vì mỗi pod hoặc mỗi phiên bản triển khai gửi một tên khác nhau.
- Trace của hai ứng dụng không liên quan bị gom vào cùng một service vì cả hai dùng chung tên.
- Dashboard metric lọc theo nhãn `application` hoặc `service` không tìm thấy dữ liệu, dù ứng dụng vẫn xuất metric.
- Log có trường service khác với `service.name` trên trace, khiến thao tác chuyển từ log sang trace không nhất quán.

Không phải mọi trường hợp metric thiếu nhãn `service.name` đều là lỗi. Với Prometheus hoặc Micrometer registry, tên ứng dụng có thể được biểu diễn bằng một common tag như `application`; OpenTelemetry lại biểu diễn `service.name` như một Resource attribute. Hai cách biểu diễn này thuộc hai mô hình dữ liệu khác nhau. Khi điều tra, hãy kiểm tra tên và vị trí của thuộc tính trong từng pipeline.

## 3. Xác định tín hiệu nào đang mang tên sai

Hãy lấy một request cụ thể và đối chiếu cả ba tín hiệu. Việc kiểm tra cùng một thời điểm và cùng một instance giúp tránh nhầm lẫn do cấu hình giữa các môi trường.

### 3.1. Kiểm tra trace

Mở một trace mới được tạo sau lần triển khai gần nhất. Trong phần Resource hoặc resource attributes của span, tìm:

```text
service.name
service.namespace
service.instance.id
deployment.environment.name
```

Đọc `service.name` ở cấp Resource, không nhầm nó với một span attribute do ứng dụng tự thêm. Nếu các span trong cùng một trace có Resource khác nhau, hãy kiểm tra việc khởi tạo SDK hoặc cách các tiến trình gửi trace. Với một service đơn giản, các span do cùng tiến trình tạo ra thường chia sẻ cùng Resource.

### 3.2. Kiểm tra metric

Nếu ứng dụng có Actuator, endpoint `/actuator/metrics` cho phép kiểm tra các meter đang được đăng ký. Với Prometheus registry, xem `/actuator/prometheus` và tìm các nhãn mà hệ thống đang dùng, ví dụ `application`. Có thể cấu hình endpoint để phục vụ kiểm tra trong môi trường phát triển:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Chỉ mở các endpoint cần thiết và bảo vệ chúng theo chính sách truy cập của môi trường. Không công khai endpoint chẩn đoán cấu hình hoặc biến môi trường ra Internet.

Nếu metric được gửi bằng OTLP, kiểm tra Resource attributes của metric tại backend hoặc Collector. Đừng kết luận rằng `service.name` bị thiếu chỉ vì Prometheus series không có nhãn cùng tên; registry Prometheus có thể đang dùng common tag khác.

### 3.3. Kiểm tra log

Tìm một log record phát sinh từ cùng request hoặc cùng instance. Kiểm tra trường định danh service mà log pipeline sử dụng, chẳng hạn `service`, `service_name` hoặc một trường do log shipper bổ sung. Đồng thời kiểm tra `traceId` và `spanId` nếu hệ thống đã bật correlation.

Spring Boot có thể đưa thông tin tương quan trace vào MDC khi cấu hình Micrometer Tracing phù hợp, nhưng điều đó không tự đảm bảo rằng mọi định dạng log đều có trường service. Trường tên service trong log thường cần được thêm bởi cấu hình logging, encoder hoặc Collector. Hãy kiểm tra JSON log thực tế sau khi đi qua pipeline, vì shipper có thể đổi tên hoặc ghi đè trường.

## 4. Truy tìm nguồn cấu hình đang ghi đè

Một tên service sai thường xuất phát từ việc có nhiều nguồn cấu hình cùng tồn tại. Kiểm tra theo thứ tự từ ứng dụng đến hạ tầng:

1. **Cấu hình Spring Boot:** kiểm tra `spring.application.name`, các file `application-{profile}.yml` và biến cấu hình theo profile đang chạy.
2. **Cấu hình OpenTelemetry của Spring Boot:** nếu phiên bản Spring Boot đang dùng hỗ trợ `management.opentelemetry.resource-attributes`, kiểm tra các thuộc tính Resource được khai báo tại đây.
3. **OpenTelemetry Java agent hoặc SDK autoconfigure:** kiểm tra `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, tham số JVM và cấu hình khởi chạy agent. Khi dùng OpenTelemetry SDK autoconfigure, `OTEL_SERVICE_NAME` là biến chuyên biệt cho `service.name` và có độ ưu tiên cao hơn giá trị `service.name` trong `OTEL_RESOURCE_ATTRIBUTES`.
4. **Môi trường triển khai:** kiểm tra Deployment, Helm values, ConfigMap, Secret và biến môi trường mà nền tảng đưa vào container. Đảm bảo staging và production không vô tình dùng chung giá trị hoặc giá trị mặc định.
5. **OpenTelemetry Collector hoặc gateway:** kiểm tra processor có thêm, đổi tên hoặc ghi đè Resource attribute hay không. Giá trị tại Collector có thể khác với giá trị ứng dụng gửi ban đầu.
6. **Backend quan sát:** kiểm tra quy tắc chuẩn hóa, grouping hoặc mapping của backend. Một số giao diện có thể hiển thị tên service đã được biến đổi từ Resource.

Trong Spring Boot, Actuator có thể hỗ trợ kiểm tra cấu hình đã được nạp thông qua các endpoint như `env` hoặc `configprops`, nếu ứng dụng đã bật chúng. Chỉ bật và truy cập các endpoint này trong môi trường được bảo vệ. Khi đọc kết quả, chú ý nguồn property và profile đang có hiệu lực, không chỉ giá trị mặc định trong file cấu hình.

## 5. Chuẩn hóa tên service trong Spring Boot

Chọn một tên logic ổn định cho mỗi service, sau đó dùng tên đó nhất quán trong các pipeline. Ví dụ, ứng dụng xử lý đơn hàng có thể dùng `orders-service` ở mọi môi trường.

### 5.1. Đặt tên ứng dụng

Khai báo tên ứng dụng trong cấu hình Spring Boot:

```yaml
spring:
  application:
    name: orders-service
```

Đây là điểm cấu hình trung tâm dễ đọc và dễ tái sử dụng. Không đưa tên pod, mã phiên bản triển khai hoặc tên môi trường vào giá trị này nếu chúng làm thay đổi danh tính logic của service.

### 5.2. Cấu hình Resource của OpenTelemetry

Nếu phiên bản Spring Boot đang sử dụng cung cấp property `management.opentelemetry.resource-attributes`, có thể khai báo rõ Resource attributes để tên service được gửi cùng telemetry:

```yaml
spring:
  application:
    name: orders-service

management:
  opentelemetry:
    resource-attributes:
      service.name: ${spring.application.name}
      service.namespace: commerce
      deployment.environment.name: ${APP_ENV:local}
```

Property và khả năng tự ánh xạ Resource có thể thay đổi theo phiên bản Spring Boot và cách ứng dụng khởi tạo OpenTelemetry. Hãy đối chiếu tài liệu đúng phiên bản đang chạy. Nếu property này không được phiên bản hỗ trợ, đừng để cấu hình nằm im mà không có tác dụng; hãy dùng cơ chế cấu hình Resource được hỗ trợ bởi SDK hoặc agent đang triển khai, rồi xác minh kết quả ở trace backend.

### 5.3. Cấu hình khi dùng OpenTelemetry Java agent hoặc SDK autoconfigure

Với môi trường sử dụng OpenTelemetry Java agent hoặc SDK autoconfigure, có thể cấu hình bằng biến môi trường:

```bash
OTEL_SERVICE_NAME=orders-service
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment.name=production
```

`OTEL_SERVICE_NAME` là cách trực tiếp để đặt `service.name` trong các cấu hình OpenTelemetry hỗ trợ biến môi trường này. Tránh khai báo hai giá trị `service.name` khác nhau trong `OTEL_SERVICE_NAME` và `OTEL_RESOURCE_ATTRIBUTES`, vì biến chuyên biệt sẽ được ưu tiên trong SDK autoconfigure. Nếu ứng dụng chỉ dùng cấu hình OpenTelemetry do Spring Boot quản lý mà không bật agent hoặc SDK autoconfigure tương ứng, không giả định các biến trên chắc chắn được đọc; hãy xác minh cơ chế cấu hình thực tế.

### 5.4. Gắn nhãn metric của Micrometer

Với registry dạng Prometheus, có thể thêm common tag để dashboard nhận diện ứng dụng:

```yaml
management:
  metrics:
    tags:
      application: ${spring.application.name}
```

Common tag `application` là nhãn metric của Micrometer. Nó không thay thế Resource attribute `service.name` của OpenTelemetry. Nếu cùng ứng dụng xuất metric qua nhiều registry, hãy kiểm tra nhãn thực tế ở từng registry và thống nhất quy ước truy vấn dashboard.

### 5.5. Đồng bộ trường service trong log

Nếu log được xuất dưới dạng JSON, cấu hình encoder hoặc log shipper để bổ sung trường service từ cùng nguồn tên ứng dụng. Chọn một tên trường thống nhất theo schema của hệ thống log, ví dụ `service.name`, và tránh để ứng dụng, agent và Collector ghi các giá trị khác nhau lên cùng trường.

Kiểm tra log record sau khi đã đi qua toàn bộ pipeline. Nếu backend dùng `service` trong khi trace dùng `service.name`, hãy cấu hình mapping rõ ràng ở bước ingest hoặc truy vấn. Không nên suy ra rằng hai trường đã đồng nhất chỉ vì chúng có giá trị giống nhau ở local.

## 6. Quy trình sửa lỗi theo từng bước

Có thể áp dụng quy trình sau khi phát hiện tên service sai:

1. **Ghi nhận giá trị hiện tại:** lấy một trace, một metric và một log record; ghi lại tên service, instance và môi trường của từng tín hiệu.
2. **Chọn tên chuẩn:** thống nhất một tên logic, ví dụ `orders-service`, cùng `service.namespace` nếu cần phân biệt các miền nghiệp vụ.
3. **Tìm nguồn ghi đè:** kiểm tra profile Spring, biến môi trường, tham số JVM, Java agent, manifest triển khai và Collector processor.
4. **Sửa nguồn có thẩm quyền:** chọn một nguồn cấu hình chính cho `service.name`; loại bỏ hoặc đồng bộ các giá trị xung đột.
5. **Triển khai một instance thử nghiệm:** khởi động lại ứng dụng hoặc rollout một replica để tránh trộn dữ liệu cũ và mới trong lúc xác minh.
6. **Tạo request mới:** không chỉ mở trace cũ, vì trace đã lưu giữ Resource tại thời điểm được tạo.
7. **Đối chiếu ba tín hiệu:** kiểm tra trace Resource, nhãn metric và trường service trong log. Xác nhận các replica có cùng `service.name` nhưng `service.instance.id` khác nhau.
8. **Kiểm tra Collector và dashboard:** bảo đảm pipeline không ghi đè tên chuẩn và truy vấn dashboard đang lọc đúng tên trường.

Sau khi đổi tên, dữ liệu lịch sử có thể vẫn hiển thị dưới tên cũ. Đây là hành vi bình thường vì Resource của trace và metric đã được ghi tại thời điểm phát sinh. Đánh giá kết quả bằng dữ liệu mới sau khi cấu hình được triển khai.

## 7. Ví dụ: hai replica bị hiển thị thành hai service

Giả sử `orders-service` chạy hai replica. Cấu hình sai đặt tên service theo hostname:

```text
Replica A: service.name = orders-service-7f9c8d6b5-x2kq4
Replica B: service.name = orders-service-7f9c8d6b5-m8n7p
```

Trace backend sẽ nhóm dữ liệu thành hai service. Dashboard tổng hợp latency của `orders-service` có thể chỉ lấy được một replica hoặc phải truy vấn cả hai tên.

Cấu hình đúng giữ tên logic ổn định và dùng instance ID cho từng replica:

```text
Replica A:
  service.name = orders-service
  service.instance.id = orders-service-7f9c8d6b5-x2kq4

Replica B:
  service.name = orders-service
  service.instance.id = orders-service-7f9c8d6b5-m8n7p
```

Khi đó backend gom trace theo một service, đồng thời vẫn cho phép phân tích theo instance khi cần tìm replica có lỗi hoặc độ trễ bất thường.

## 8. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Bỏ trống `spring.application.name` | Một số tích hợp có thể dùng tên mặc định hoặc tên không mong muốn | Đặt tên ứng dụng rõ ràng và kiểm tra Resource thực tế |
| Chỉ đổi `spring.application.name` nhưng agent vẫn đặt tên riêng | Trace vẫn mang tên cũ hoặc tên mặc định | Kiểm tra `OTEL_SERVICE_NAME`, cấu hình SDK và agent |
| Đặt `OTEL_SERVICE_NAME` khác với `service.name` trong `OTEL_RESOURCE_ATTRIBUTES` | Giá trị cuối cùng không giống giá trị mong đợi | Đồng bộ hai nguồn hoặc chỉ giữ một nguồn cấu hình tên |
| Dùng hostname/pod name làm `service.name` | Mỗi replica bị nhóm thành một service | Chuyển hostname sang `service.instance.id` |
| Nhiều ứng dụng dùng cùng `service.name` | Dữ liệu của các ứng dụng bị gộp | Đặt tên logic duy nhất; dùng `service.namespace` để phân vùng khi phù hợp |
| Metric dùng nhãn `application`, trace dùng `service.name` | Truy vấn dashboard có thể không khớp | Hiểu đúng schema của từng pipeline và chuẩn hóa quy ước truy vấn |
| Collector ghi đè Resource attribute | Giá trị ở backend khác với giá trị ứng dụng gửi | Kiểm tra và sửa processor hoặc transform tại Collector |
| Chỉ xem trace cũ sau khi sửa | Tưởng rằng cấu hình mới chưa có tác dụng | Tạo request mới và kiểm tra telemetry phát sinh sau triển khai |

## 9. Checklist xác minh sau khi sửa

- [ ] `spring.application.name` có giá trị ổn định và đúng với tên service đã thống nhất.
- [ ] Resource của trace mới có `service.name` đúng.
- [ ] Các replica của cùng service dùng chung `service.name`.
- [ ] `service.instance.id` phân biệt được từng instance nếu hệ thống cần theo dõi thuộc tính này.
- [ ] Metric có nhãn ứng dụng phù hợp với registry và quy ước dashboard.
- [ ] Log record có trường service đúng sau khi đi qua log pipeline.
- [ ] `traceId` và `spanId` vẫn được ghi nhận nếu ứng dụng cần liên kết log với trace.
- [ ] Không còn biến môi trường, tham số JVM hoặc Collector processor ghi đè ngoài dự kiến.
- [ ] Dashboard và cảnh báo đã truy vấn theo tên hoặc nhãn mới.

Tên service đúng giúp hệ thống observability nhóm dữ liệu ổn định và liên kết các tín hiệu đáng tin cậy hơn. Khi gặp lỗi, hãy lần theo giá trị từ cấu hình Spring Boot qua SDK hoặc agent đến Collector và backend; kết quả cuối cùng cần được xác nhận trên telemetry mới của cả log, metric và trace.
