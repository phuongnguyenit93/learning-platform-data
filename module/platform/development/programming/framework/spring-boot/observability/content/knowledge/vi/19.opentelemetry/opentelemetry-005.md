# OTEL_SERVICE_NAME: định danh service trong OpenTelemetry và Spring Boot

> **Chương:** OpenTelemetry  
> **Bài:** OTEL_SERVICE_NAME  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần một tên service thống nhất?

Một hệ thống có thể gồm api-gateway, order-service, inventory-service và payment-service. Mỗi tiến trình phát ra traces, metrics và logs. Khi dữ liệu tới OpenTelemetry Collector hoặc observability backend, người vận hành cần biết **tiến trình nào tạo ra telemetry** để lọc, nhóm và so sánh.

Trong OpenTelemetry, danh tính này được biểu diễn chủ yếu bằng resource attribute:

~~~text
service.name = order-service
~~~

**OTEL_SERVICE_NAME** là biến môi trường chuẩn dùng để đặt giá trị của resource attribute **service.name** trong những SDK/autoconfiguration có hỗ trợ OpenTelemetry environment variables.

Ví dụ chạy Spring Boot:

~~~bash
OTEL_SERVICE_NAME=order-service java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
java -jar app.jar
~~~

Khi OpenTelemetry SDK phù hợp đọc cấu hình môi trường, telemetry của tiến trình sẽ được gắn resource identity này. Tên service xuất hiện trong resource, không phải tag tùy ý cần thêm vào mọi span.

Mục tiêu bài học là hiểu OTEL_SERVICE_NAME, phân biệt nó với spring.application.name, service.namespace và instance identity; cấu hình theo môi trường; xác minh resource trên trace/metric/log; tránh tạo nhiều tên không nhất quán cho cùng một service.

## 2. Resource trong OpenTelemetry là gì?

**Resource** mô tả thực thể tạo telemetry, chẳng hạn một service process, container, host hoặc workload. Resource thường gắn với nhiều spans, metrics và log records từ cùng một tiến trình hoặc SDK.

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
service.instance.id = order-service-pod-k2m4p
~~~

| Resource attribute | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| service.name | Tên logic ổn định của service | order-service |
| service.namespace | Nhóm chứa service | commerce |
| service.version | Phiên bản ứng dụng | 2.4.1 |
| deployment.environment.name | Môi trường triển khai | production |
| service.instance.id | Định danh instance | ID pod/process |

service.name nên ổn định giữa replicas của cùng một service. Không đặt pod ID, hostname ngẫu nhiên, request ID hoặc version build vào service.name; chúng là những chiều khác nhau.

~~~mermaid
flowchart TD
  A["Resource của tiến trình"] --> B["service.name: order-service"]
  A --> C["service.namespace: commerce"]
  A --> D["service.version: 2.4.1"]
  A --> E["service.instance.id: pod/process"]
  B --> F["Spans, metrics, logs"]
  C --> F
  D --> F
  E --> F
~~~

Resource giúp backend trả lời telemetry đến từ service nào, phiên bản nào và instance nào. Nếu cùng ứng dụng chạy 10 replicas, replicas thường chia sẻ service.name, trong khi service.instance.id phân biệt từng instance.

## 3. OTEL_SERVICE_NAME thiết lập điều gì?

OTEL_SERVICE_NAME là biến môi trường dành cho OpenTelemetry SDK configuration. Khi SDK/autoconfiguration tương thích đọc biến này, giá trị được dùng làm service.name trong resource.

~~~bash
OTEL_SERVICE_NAME=inventory-service
~~~

Resource mong muốn:

~~~text
service.name = inventory-service
~~~

Các điểm cần nhớ:

- Đây là tên logic của service, không phải tên jar, class Java hay URL endpoint.
- Cùng một service có thể có nhiều process/containers nhưng cùng service.name.
- Mỗi instance có thể được nhận diện bằng service.instance.id.
- Đổi biến thường tác động tới telemetry được tạo bởi process khởi động với cấu hình mới.
- Biến này không tự tạo spans, metrics, logs và không thay thế exporter.
- Nếu ứng dụng dùng SDK không đọc OpenTelemetry environment variables, đặt biến có thể không tạo hiệu lực.

**Điều kiện quan trọng:** phải biết tiến trình đang dùng OpenTelemetry Java agent, OpenTelemetry SDK autoconfiguration hay một bridge/integration khác. Không giả định mọi ứng dụng Spring Boot có Micrometer đều tự đọc OTEL_SERVICE_NAME.

## 4. OTEL_SERVICE_NAME và OTEL_RESOURCE_ATTRIBUTES

OpenTelemetry hỗ trợ cấu hình resource qua nhiều biến môi trường:

- OTEL_SERVICE_NAME: giá trị chuyên biệt cho service.name.
- OTEL_RESOURCE_ATTRIBUTES: danh sách resource attributes, ví dụ service.namespace=commerce,service.version=2.4.1.

Bash:

~~~bash
export OTEL_SERVICE_NAME=order-service
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
$env:OTEL_RESOURCE_ATTRIBUTES = "service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -jar app.jar
~~~

Resource mong muốn:

| Key | Value |
| --- | --- |
| service.name | order-service |
| service.namespace | commerce |
| service.version | 2.4.1 |
| deployment.environment.name | production |

Theo quy tắc OpenTelemetry SDK environment configuration, OTEL_SERVICE_NAME là cách chuyên biệt để đặt service.name và được ưu tiên khi thuộc tính đó đồng thời xuất hiện trong OTEL_RESOURCE_ATTRIBUTES. Tránh khai báo hai giá trị mâu thuẫn; dùng một nguồn có chủ đích và xác minh resource cuối cùng.

Value có dấu phẩy hoặc ký tự đặc biệt cần được escape theo cú pháp SDK hỗ trợ. Giữ resource values đơn giản và không nhạy cảm.

## 5. Phân biệt với spring.application.name

Trong Spring Boot, spring.application.name thường được dùng làm tên ứng dụng trong hệ sinh thái Spring và có thể được tích hợp vào tên service trong cấu hình Micrometer/Tracing.

~~~yaml
spring:
  application:
    name: order-service
~~~

Hai cấu hình thuộc những lớp cấu hình khác nhau:

| Cấu hình | Lớp sở hữu | Mục đích |
| --- | --- | --- |
| spring.application.name | Spring Boot / Spring Environment | Tên ứng dụng Spring |
| OTEL_SERVICE_NAME | OpenTelemetry SDK environment configuration | Đặt resource attribute service.name |
| OTEL_RESOURCE_ATTRIBUTES | OpenTelemetry SDK environment configuration | Đặt resource attributes |
| service.instance.id | Resource/deployment configuration | Phân biệt instance |

Không nên khẳng định hai giá trị luôn tự động đồng bộ trong mọi stack. Kết quả phụ thuộc tracing implementation, bridge, exporter và auto-configuration.

### 5.1. Khi dùng Micrometer Tracing bridge

Spring Boot có thể dùng Micrometer Observation/Tracing với Brave hoặc OpenTelemetry bridge. Nếu telemetry được tạo bởi Micrometer và exporter tương ứng, resource được tạo bởi integration/SDK đó. Việc OTEL_SERVICE_NAME có hiệu lực hay không phụ thuộc đường cấu hình resource thực tế.

- Với OpenTelemetry Java agent hoặc SDK autoconfiguration, các environment variables chuẩn được xử lý theo cấu hình SDK/agent.
- Với Micrometer Tracing bridge tới OpenTelemetry, cần xác minh OpenTelemetry SDK/resource được khởi tạo và autoconfiguration có đọc biến môi trường không.
- Với Brave bridge/Zipkin reporter, không mặc định OpenTelemetry environment variables được áp dụng chỉ vì ứng dụng có Micrometer Observation.

Nếu spring.application.name là order-api nhưng resource backend thể hiện unknown_service:java hoặc tên khác, kiểm tra integration/resource configuration thay vì đổi hàng loạt span names.

## 6. Thiết lập biến môi trường theo môi trường chạy

### 6.1. Linux/macOS shell

~~~bash
export OTEL_SERVICE_NAME=order-service
java -jar target/order-service.jar
~~~

Biến trong shell hiện tại và tiến trình con được khởi chạy từ shell đó nhận giá trị. Terminal khác hoặc service manager có environment riêng.

### 6.2. PowerShell

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
java -jar .\target\order-service.jar
~~~

Xóa biến khỏi session hiện tại:

~~~powershell
Remove-Item Env:OTEL_SERVICE_NAME
~~~

Thao tác trong session hiện tại không sửa cấu hình của Windows Service, container đang chạy hoặc deployment đã tạo.

### 6.3. Docker

~~~dockerfile
ENV OTEL_SERVICE_NAME=order-service
~~~

Hoặc lúc chạy:

~~~bash
docker run --rm -e OTEL_SERVICE_NAME=order-service order-service:latest
~~~

Docker Compose:

~~~yaml
services:
  order-service:
    image: order-service:latest
    environment:
      OTEL_SERVICE_NAME: order-service
      OTEL_RESOURCE_ATTRIBUTES: service.namespace=commerce,deployment.environment.name=staging
~~~

Nhiều replicas của cùng một service nên dùng cùng OTEL_SERVICE_NAME. Đừng đặt tên theo container ID; instance identity cần thuộc tính riêng.

### 6.4. Kubernetes

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:2.4.1
          env:
            - name: OTEL_SERVICE_NAME
              value: order-service
            - name: OTEL_RESOURCE_ATTRIBUTES
              value: service.namespace=commerce,deployment.environment.name=production
~~~

Đây là ví dụ rút gọn; Deployment thực tế cần các trường vận hành khác. Có thể dùng Downward API đưa pod identity vào resource attribute riêng nếu SDK/integration hỗ trợ. Không đặt pod name vào service.name, vì mỗi pod sẽ xuất hiện như một service riêng.

## 7. Gắn service.name cho traces, metrics và logs

service.name là resource attribute. Khi cùng một OpenTelemetry Resource được dùng cho nhiều signal, backend có thể nhóm telemetry theo cùng service identity:

~~~text
Resource:
  service.name = order-service
  service.namespace = commerce
  service.version = 2.4.1

Trace:
  span = orders.create
  trace_id = ...

Metric:
  name = orders.processing.duration
  value = ...

Log:
  body = "order accepted"
  trace_id = ...
~~~

Các signal có thể được xuất qua pipeline khác nhau. Nhìn thấy service.name trên trace không tự chứng minh metrics và logs cũng dùng cùng SDK/resource. Nếu metrics đến từ Prometheus scrape, labels do Prometheus target/relabeling gắn có thể khác resource attributes của OTLP traces.

**Resource identity giúp liên kết, không thay thế correlation:** trace ID/span ID nối spans và log records liên quan đến một request; service.name cho biết service tạo telemetry.

### 7.1. Một service, nhiều signal

| Signal | Metadata mong muốn |
| --- | --- |
| Traces | Resource service.name=order-service |
| OTLP metrics | Resource service.name=order-service |
| OTLP logs | Resource service.name=order-service |
| Prometheus scrape | Target labels như job, instance, có thể map về service |

Nếu các pipeline có cấu hình resource riêng, phải thống nhất quy ước tên. Không dùng order-api trên traces, orders trên metrics và order-service-prod trên logs nếu chúng là cùng một service logic, trừ khi có lý do rõ ràng.

## 8. service.name, namespace, version và instance ID

Resource attributes tạo thành danh tính có cấu trúc:

~~~text
service.namespace = commerce
service.name = order-service
service.version = 2.4.1
service.instance.id = order-service-pod-7d9f
deployment.environment.name = production
~~~

Một cách hiểu hữu ích:

- Namespace nhóm các service thuộc một miền.
- Name là định danh ổn định của service logic.
- Version giúp so sánh các phiên bản triển khai.
- Instance ID phân biệt một process/container/replica.
- Environment phân biệt staging, production và môi trường khác.

| Pod | service.namespace | service.name | service.instance.id |
| --- | --- | --- | --- |
| order-abc | commerce | order-service | order-abc |
| order-def | commerce | order-service | order-def |
| order-ghi | commerce | order-service | order-ghi |

Backend có thể hiển thị một service logic với ba instances. Nếu dùng pod name làm service.name, dashboard/service map có thể phân mảnh thành ba service giả.

Không có quy tắc duy nhất cho cách sinh instance ID ở mọi runtime. Chọn ID ổn định trong vòng đời instance, duy nhất trong phạm vi backend cần phân biệt, và tránh dùng một giá trị thay đổi giữa mỗi request.

## 9. Resource attribute không phải span attribute hay metric label

Một lỗi thường gặp là đặt tên service bằng cách thêm service.name vào mỗi span thủ công. Với OpenTelemetry, service identity phù hợp ở **resource scope**, không nên lặp lại trong từng span nếu SDK đã cung cấp resource.

| Cấp dữ liệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Resource | service.name=order-service | Tiến trình/service tạo dữ liệu |
| Span attribute | http.request.method=POST | Chi tiết một hoạt động |
| Metric attribute | outcome=error | Phân biệt metric theo chiều có cardinality kiểm soát |
| Log attribute | event.action=order-created | Metadata của log record |

Với metric, mỗi tổ hợp attribute có thể góp phần tạo series. Nếu lấy user ID hoặc request ID làm metric labels, cardinality có thể bùng nổ. service.name là resource identity có tập giá trị thường nhỏ theo số service logic, nhưng vẫn cần naming nhất quán.

Không thêm service.name thủ công trên mọi Observation chỉ để nó xuất hiện trên backend. Trước hết kiểm tra resource được tạo ở SDK/bridge.

## 10. Java Agent và SDK autoconfiguration

Có nhiều cách đưa OpenTelemetry vào ứng dụng Java. Cần phân biệt vì OTEL_SERVICE_NAME chỉ có tác dụng khi thành phần cấu hình tương ứng đọc nó.

### 10.1. OpenTelemetry Java Agent

Java agent thường được gắn khi khởi chạy JVM qua -javaagent:

~~~bash
OTEL_SERVICE_NAME=order-service \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
java -javaagent:/opt/otel/opentelemetry-javaagent.jar \
     -jar target/order-service.jar
~~~

Ví dụ giả định agent file tồn tại, endpoint Collector có thể truy cập và cấu hình exporter phù hợp với phiên bản agent. Agent có autoconfiguration và instrumentation cho nhiều thư viện được hỗ trợ.

Không cần thêm một OpenTelemetry SDK riêng trong code chỉ để sử dụng agent, trừ khi ứng dụng có yêu cầu tích hợp đặc biệt.

### 10.2. OpenTelemetry SDK autoconfiguration

Ứng dụng khởi tạo OpenTelemetry SDK có thể dùng autoconfiguration để đọc environment variables. Khi SDK đó tạo resource, OTEL_SERVICE_NAME được áp dụng theo quy tắc cấu hình SDK.

Nếu code tự tạo Resource rồi nối vào provider, cần hiểu thứ tự merge resource và SDK configuration. Không giả định biến môi trường luôn ghi đè bất kỳ resource nào do code tự thiết lập theo mọi implementation.

### 10.3. Micrometer Tracing bridge

Spring Boot có thể kết nối Micrometer Tracing với OpenTelemetry bridge. Cần xác định OpenTelemetry/SdkTracerProvider được tạo bởi auto-configuration nào và Resource được cấu hình ở đâu. Nếu integration không chạy OpenTelemetry SDK autoconfiguration, OTEL_SERVICE_NAME có thể không được đọc như kỳ vọng.

**Không cài Java agent cùng instrumentation thủ công trùng chức năng mà không chủ đích.** Hai lớp instrumentation có thể tạo spans trùng cho cùng HTTP request hoặc JDBC operation. Khi dùng agent, kiểm tra thư viện agent đã tự instrument trước khi thêm Observation thủ công.

## 11. Kiểm tra service name thực tế

Đừng chỉ đọc biến môi trường rồi kết luận backend đã nhận đúng resource. Cần xác minh telemetry sau khi qua SDK và exporter.

### 11.1. Kiểm tra process environment

Linux/macOS:

~~~bash
echo "$OTEL_SERVICE_NAME"
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME
~~~

Docker:

~~~bash
docker exec <container-name> printenv OTEL_SERVICE_NAME
~~~

Kiểm tra này chỉ chứng minh biến có trong environment của process/container. Nó chưa chứng minh SDK đã đọc hoặc exporter đã gửi resource.

### 11.2. Kiểm tra Collector hoặc backend

Trong môi trường test, tạo request rồi tìm trace. Mở resource attributes và xác minh:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
~~~

Nếu có OTLP metrics/logs, kiểm tra resource attributes tương tự ở từng signal. Với Prometheus, kiểm tra target labels và cấu hình relabeling; cách biểu diễn resource khác OTLP.

### 11.3. Kiểm tra giá trị mặc định

Nếu không có service name cấu hình, một số OpenTelemetry SDK có thể dùng giá trị mặc định như unknown_service hoặc biến thể có runtime/process. Điều này làm dashboard khó nhóm và không nên được xem là danh tính production tốt.

Đặt tên ổn định và kiểm tra sau deploy. Đừng dựa vào giá trị mặc định vì runtime/SDK có thể biểu diễn khác nhau.

## 12. Quy tắc đặt tên service.name

Tên service là định danh vận hành, nên chọn quy ước ổn định và dùng nhất quán:

- Dùng tên logic dễ hiểu như order-service, inventory-service, payment-service.
- Dùng cùng một tên cho replicas của cùng service.
- Tránh gắn môi trường vào service name nếu môi trường đã có resource attribute riêng.
- Tránh gắn version vào service name nếu version đã có service.version.
- Tránh tên chứa pod ID, hostname, request ID, user ID hoặc dữ liệu động.
- Định nghĩa owner và naming convention khi tạo service mới.

| Không nên | Nên dùng | Lý do |
| --- | --- | --- |
| order-service-prod | order-service + environment=production | Tách service logic khỏi môi trường |
| order-service-v2.4.1 | order-service + version=2.4.1 | Dễ so sánh version |
| order-service-7d9f8c | order-service + instance ID | Tránh mỗi replica thành service riêng |
| /api/orders/12345 | order-service | Không dùng route/request làm service identity |

Thay đổi service name có thể làm lịch sử metrics/traces bị chia thành hai nhóm trên backend, ảnh hưởng dashboard, alert và service map.

## 13. Xung đột cấu hình thường gặp

| Nguồn | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| OTEL_SERVICE_NAME | order-service | SDK autoconfiguration có đọc biến không? |
| OTEL_RESOURCE_ATTRIBUTES | service.name=orders,service.version=2.4.1 | Có giá trị mâu thuẫn không? |
| spring.application.name | order-api | Bridge/Spring Boot mapping có dùng giá trị này không? |
| Java agent config | Resource attributes của agent | Có được nạp và merge không? |
| SDK code configuration | Resource được tạo trong code | Thứ tự merge/override là gì? |
| Collector processor | Resource attribute transform | Có đổi tên sau khi nhận không? |

Khi thấy service.name không như mong muốn, kiểm tra từ source đến backend:

1. Process environment thật.
2. SDK/agent/autoconfiguration đang khởi tạo tracer.
3. Resource được merge và attribute precedence.
4. Bridge hoặc exporter.
5. Collector processor có sửa resource không.
6. Backend có mapping hoặc cách hiển thị riêng không.

Đừng thay đổi tất cả nguồn cùng lúc. Thay từng nguồn trong môi trường test và quan sát resource cuối để xác định nguồn có hiệu lực.

## 14. Rủi ro khi cấu hình sai service name

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Nhiều service cùng hiện unknown_service | SDK không đọc service name hoặc chưa cấu hình Resource | Kiểm tra agent/autoconfiguration và resource |
| Mỗi pod thành service riêng | Pod ID đặt trong OTEL_SERVICE_NAME | Dùng tên logic ổn định; đưa pod identity vào instance ID |
| Traces mang tên khác metrics | Signal dùng SDK/resource pipeline khác nhau | Đồng bộ resource identity và kiểm tra exporter |
| spring.application.name đúng nhưng OTel resource sai | SDK/bridge không lấy Spring property hoặc nguồn khác ghi đè | Kiểm tra mapping/effective resource |
| Thay env var nhưng backend không đổi | Process chưa restart hoặc service manager không truyền env | Kiểm tra environment process đang chạy |
| service.name thay theo môi trường | Tên service bị ghép -dev, -prod | Dùng environment attribute riêng |
| Span name bị dùng thay service name | Nhầm operation name với resource identity | Đặt resource và span name đúng cấp |
| Collector hiển thị tên khác | Processor transform/override resource | Kiểm tra pipeline Collector |
| Span trùng do Java agent và manual instrumentation | Instrumentation chồng lấp | Chọn một owner cho mỗi ranh giới |

## 15. Tình huống thực tế: ba replicas của order-service

**Bối cảnh:** order-service chạy ba replicas trong Kubernetes. Ban đầu nhóm đặt OTEL_SERVICE_NAME bằng tên pod, khiến backend hiển thị ba service khác nhau.

~~~text
order-service-7dd6-x1
order-service-7dd6-y2
order-service-7dd6-z3
~~~

Dashboard tìm order-service không gom được dữ liệu và service map phân mảnh.

### Bước 1 — thống nhất logical name

~~~yaml
- name: OTEL_SERVICE_NAME
  value: order-service
~~~

### Bước 2 — phân biệt từng instance

~~~text
service.name = order-service
service.instance.id = order-service-7dd6-x1
~~~

Lặp lại với các pods còn lại. Backend có thể nhóm ba replicas dưới cùng service name và vẫn phân biệt từng instance.

### Bước 3 — giữ environment và version riêng

~~~text
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
~~~

### Bước 4 — xác minh tất cả signals

Kiểm tra resource ở traces, metrics và logs. Service name giống nhau, instance IDs khác nhau, metrics/traces/logs không sử dụng naming conventions mâu thuẫn.

**Kết quả mong muốn:** dashboard nhóm service đúng, có thể so sánh version và drill down từng instance mà không tạo service giả cho mỗi pod.

## 16. Bài thực hành

### Bài tập A — kiểm tra environment variable

1. Khởi chạy ứng dụng có OpenTelemetry SDK/agent autoconfiguration phù hợp.
2. Đặt OTEL_SERVICE_NAME=order-service.
3. Gửi request tạo trace.
4. Mở resource attributes trên backend.
5. Xác minh service.name là order-service.
6. Bỏ biến trong môi trường test và quan sát fallback của SDK đang dùng.

### Bài tập B — so sánh các nguồn cấu hình

Trong môi trường cô lập, thiết lập:

- OTEL_SERVICE_NAME=order-service
- OTEL_RESOURCE_ATTRIBUTES=service.name=orders,service.namespace=commerce
- spring.application.name=order-api

Quan sát service.name cuối cùng và giải thích nguồn nào thực sự được đọc, quy tắc ưu tiên nào áp dụng trong stack. Không áp dụng thử nghiệm cấu hình mâu thuẫn trên production.

### Bài tập C — multi-instance

Chạy ba replicas với cùng OTEL_SERVICE_NAME và instance IDs khác nhau. Xác minh backend gom chung service nhưng vẫn drill down tới từng replica.

### Bài tập D — nhiều signal

Kiểm tra traces, OTLP metrics và logs. So sánh resource attributes service.name, service.version, service.namespace. Nếu Prometheus scrape metrics, so sánh target labels với resource attributes của OTLP.

### Câu hỏi tự kiểm tra

1. OTEL_SERVICE_NAME thiết lập resource attribute nào?
2. Resource khác span attributes ở điểm nào?
3. OTEL_SERVICE_NAME khác OTEL_RESOURCE_ATTRIBUTES thế nào?
4. Vì sao service.name không nên chứa pod ID?
5. spring.application.name có luôn tự động override OTEL_SERVICE_NAME không?
6. Khi nào OpenTelemetry Java agent/SDK đọc biến môi trường?
7. Vì sao cấu hình Micrometer Tracing không nhất thiết tự đọc mọi OTEL_* variable?
8. service.instance.id khác service.name thế nào?
9. Vì sao metrics và traces có thể thể hiện service name khác nhau?
10. Collector có thể thay đổi resource attributes sau khi nhận telemetry không?
11. Nếu backend hiển thị unknown_service, cần kiểm tra những lớp nào?
12. Vì sao không nên dùng sampling hoặc span name để sửa lỗi resource identity?

**Tiêu chí hoàn thành:** giải thích OTEL_SERVICE_NAME và service.name; phân biệt resource, span attributes và instance identity; phân biệt với Spring application.name; cấu hình process/container; hiểu agent/SDK/bridge; kiểm tra resource cuối trên traces/metrics/logs và xử lý conflict.

## 17. Ghi nhớ

- OTEL_SERVICE_NAME là biến môi trường OpenTelemetry dùng để đặt resource attribute service.name khi SDK/autoconfiguration tương ứng hỗ trợ.
- service.name là tên logic ổn định của service; replicas cùng service dùng chung tên.
- service.instance.id, service.version, service.namespace và environment mô tả các chiều khác nhau; không ghép tất cả vào tên service.
- OTEL_RESOURCE_ATTRIBUTES đặt resource attributes khác; tránh khai báo service.name mâu thuẫn với OTEL_SERVICE_NAME.
- spring.application.name thuộc Spring Boot. Mapping sang OTel resource phụ thuộc integration; không giả định mọi bridge đọc OTEL_SERVICE_NAME.
- Java agent, SDK autoconfiguration và Micrometer bridge là các cách tích hợp khác nhau. Xác định thành phần thực sự tạo Resource trước khi debug.
- Resource identity có thể dùng chung cho traces/metrics/logs nếu pipelines được cấu hình nhất quán. Prometheus target labels vẫn là lớp metadata riêng.
- Kiểm tra resource cuối tại backend. Environment variable tồn tại trong process chưa chứng minh exporter đã gửi đúng giá trị.

## Tài liệu tham khảo

- [OpenTelemetry — Semantic Conventions: Service](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [OpenTelemetry Specification — SDK Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/)
- [OpenTelemetry Java — Agent configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)

