# Kiểm thử endpoint trong môi trường chạy thật

## 1. Vai trò của Module Actuator trong kiểm thử runtime

Spring Modulith giúp chia một ứng dụng Spring Boot thành các **application module** có API công khai và quan hệ phụ thuộc rõ ràng. Tài liệu module graph cho thấy **cấu trúc được phát hiện từ code**; còn **Spring Modulith Actuator** cung cấp metadata module từ **bản ứng dụng đã khởi động**. Khi triển khai, cần xác nhận rằng bản đang chạy thực sự nhận diện đúng module, công bố endpoint hợp lệ, và chỉ người có quyền được đọc thông tin kiến trúc.

Bài thuộc chương **Module Actuator** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Toàn module học bao quát tài liệu ranh giới application module và quan sát tương tác bằng module graph, Actuator, event metrics, tracing và context propagation. Bài này tập trung vào **kiểm thử endpoint trong môi trường chạy thật**: từ dependency và HTTP exposure, đến JSON assertions, truy cập qua Docker/Kubernetes, bảo mật và smoke test sau deploy.

Sau khi học, bạn cần:

1. Phân biệt endpoint **đã đăng ký**, **được expose qua HTTP**, **có thể truy cập** và **trả đúng kiến trúc**.
2. Gọi endpoint trên đúng host, port, base path và profile.
3. Kiểm tra mã HTTP, cấu trúc JSON, module và loại phụ thuộc.
4. Tạo smoke test chạy lại được trên một bản build cụ thể.
5. Biết khi nào cần đối chiếu với module graph, kiểm thử kiến trúc và telemetry vận hành.

## 2. Endpoint nào cần kiểm thử?

Trong các phiên bản Spring Modulith hiện hành, endpoint kiến trúc có **ID modulith**, mặc định truy cập theo URL:

~~~http
GET /actuator/modulith HTTP/1.1
Host: localhost:8080
~~~

Endpoint đọc metadata của các application module mà ứng dụng nhận diện: tên kỹ thuật, tên hiển thị, package gốc và các quan hệ phụ thuộc. Nó không phải endpoint để chạy lại kiểm thử kiến trúc, gọi listener hoặc phát lại event.

**Lưu ý phiên bản:** API Spring Modulith hiện tại dùng đường dẫn **/actuator/modulith**; phiên bản rất cũ từng dùng endpoint ID **applicationmodules**. Khi ứng dụng thuộc một release train cũ, cần đối chiếu tài liệu chính xác của version, dependency và Actuator discovery trước khi kết luận một URL bị sai.

~~~mermaid
flowchart LR
    Test["Người kiểm thử / CI"] --> Net["Network / Gateway / Port-forward"]
    Net --> Auth["Bảo mật + HTTP exposure"]
    Auth --> Endpoint["GET /actuator/modulith"]
    Endpoint --> Json["JSON module metadata"]
    Json --> Check["So tên module, package, dependencies"]
    Check --> Verdict{"Khớp hợp đồng?"}
    Verdict -->|Có| Pass["PASS"]
    Verdict -->|Không| Investigate["Điều tra build, profile, cấu trúc"]
~~~

Để một lần kiểm thử có ý nghĩa, **HTTP 200 chỉ là bước đầu**. Body JSON vẫn có thể thiếu module, chứa package sai hoặc quan hệ không phù hợp với kiến trúc mong đợi.

## 3. Chuẩn bị dependency và cấu hình

### 3.1. Dependency

Nếu cần cả Module Actuator lẫn instrumentation quan sát giữa các module, dùng Spring Modulith **Insight starter**:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Starter bao gồm tích hợp Actuator và observability của Spring Modulith cùng hỗ trợ Actuator nền tảng. Nếu chỉ cần endpoint metadata, dùng các dependency thành phần:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
}
~~~

Các ví dụ giả định ứng dụng đã khai báo **BOM hoặc dependency management tương thích** với Spring Boot và Spring Modulith; không tự trộn các version của hai hệ sinh thái. Chỉ có **spring-boot-starter-actuator** sẽ không tự tạo endpoint kiến trúc của Spring Modulith.

### 3.2. Expose endpoint trên HTTP

Ví dụ cấu hình **application.yml** dành cho môi trường lab:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,modulith,metrics
~~~

Nếu server chạy ở cổng 8080 và không cấu hình management port riêng, địa chỉ thường là **http://localhost:8080/actuator/modulith**.

Spring Boot Actuator **không expose mọi endpoint qua HTTP theo mặc định**. Cài dependency để đăng ký bean endpoint và cấu hình exposure để công bố HTTP endpoint là hai việc độc lập. Sau exposure, Spring Security, policy mạng hoặc gateway vẫn có thể chặn yêu cầu. Trên production, chỉ expose danh sách endpoint cần thiết và bảo vệ metadata kiến trúc khỏi truy cập công khai.

### 3.3. Dùng cổng quản trị riêng

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,modulith,metrics
~~~

Lúc này, từ đúng môi trường mạng của ứng dụng, thử **http://localhost:9090/actuator/modulith**. Nếu dùng **management.endpoints.web.base-path** khác, quản trị trên context path riêng hoặc đi qua ingress có rewrite, URL thực tế sẽ đổi theo. Không suy ra cổng quản trị bằng cổng nghiệp vụ 8080.

## 4. Đọc đúng JSON metadata của các module

Giả sử có các module:

- **order** tạo đơn hàng và công bố sự kiện **OrderPlaced**.
- **payment** cung cấp public API xử lý thanh toán.
- **notification** lắng nghe sự kiện **OrderPlaced**.

Một luồng phụ thuộc hợp lý là:

~~~mermaid
flowchart LR
    O["order"] -->|"USES_COMPONENT"| P["payment"]
    N["notification"] -->|"EVENT_LISTENER"| O
~~~

Chiều mũi tên là chiều **module nguồn phụ thuộc vào module đích**. Với event listener, **notification** phụ thuộc vào event contract do **order** công bố; **order** không phải gọi trực tiếp vào triển khai **notification**.

Các trường chính của response:

| JSONPath | Ý nghĩa |
| --- | --- |
| **$.{moduleName}** | Key của object gốc, chính là tên kỹ thuật module. |
| **$.{moduleName}.displayName** | Tên hiển thị. |
| **$.{moduleName}.basePackage** | Package gốc được nhận diện. |
| **$.{moduleName}.parent** | Module cha nếu có nested module. |
| **$.{moduleName}.nested** | Danh sách nested module nếu có. |
| **$.{moduleName}.dependencies[]** | Các phụ thuộc đi ra từ module hiện tại. |
| **dependencies[].target** | Tên module đích; tham chiếu tới key module khác. |
| **dependencies[].types[]** | Các kiểu **DEFAULT**, **USES_COMPONENT**, **EVENT_LISTENER**. |

Ví dụ JSON **minh họa**, không phải dữ liệu từ hệ thống của bạn:

~~~json
{
  "order": {
    "displayName": "Order",
    "basePackage": "com.example.shop.order",
    "dependencies": [
      { "target": "payment", "types": ["USES_COMPONENT"] }
    ]
  },
  "payment": {
    "displayName": "Payment",
    "basePackage": "com.example.shop.payment",
    "dependencies": []
  },
  "notification": {
    "displayName": "Notification",
    "basePackage": "com.example.shop.notification",
    "dependencies": [
      { "target": "order", "types": ["EVENT_LISTENER"] }
    ]
  }
}
~~~

Nên kiểm thử theo **ngữ nghĩa các field**, không so khớp toàn bộ chuỗi JSON. Thứ tự key không phải hợp đồng quan trọng; các module và quan hệ cụ thể phải dựa trên thiết kế thật của dự án.

## 5. Quy trình kiểm thử thủ công bằng HTTP

### Bước 1 — Xác minh ứng dụng sẵn sàng

Ví dụ dùng management port 9090:

~~~bash
curl -i http://127.0.0.1:9090/actuator/health
~~~

Health thành công giúp xác nhận có một ứng dụng trả lời trên đường quản trị, nhưng **không chứng minh endpoint Modulith đã được đăng ký hoặc expose**.

### Bước 2 — Kiểm tra Actuator discovery

~~~bash
curl -i http://127.0.0.1:9090/actuator
~~~

Nếu Actuator discovery được bật và client có quyền, JSON có thể chứa liên kết **_links.modulith.href**. Trang discovery có thể bị tắt theo cấu hình; khi đó tiếp tục kiểm tra URL cụ thể thay vì kết luận endpoint không tồn tại.

### Bước 3 — Gọi endpoint với HTTP GET

~~~bash
curl -i -H "Accept: application/json" \
  http://127.0.0.1:9090/actuator/modulith
~~~

Kỳ vọng: **HTTP 200**, body là JSON object và có các module dự kiến. Content-Type có thể là **application/json** hoặc vendor media type của Actuator tùy phiên bản và negotiation; không nên viết test kiểm tra duy nhất một chuỗi content type.

Nếu endpoint dùng Bearer token theo cấu hình của chính ứng dụng:

~~~bash
# ACTUATOR_TOKEN được lấy từ secret manager hoặc môi trường bảo mật.
curl --fail --silent --show-error \
  -H "Authorization: Bearer $ACTUATOR_TOKEN" \
  "https://management.internal.example/actuator/modulith"
~~~

Ví dụ trên chỉ áp dụng khi hệ thống thực sự dùng Bearer. Hệ thống dùng Basic Auth, mTLS hoặc session phải cung cấp thông tin xác thực tương ứng; không ghi token vào log pipeline hay mã nguồn.

### Bước 4 — Phân tích JSON

Với jq trên Linux/macOS:

~~~bash
curl -fsS http://127.0.0.1:9090/actuator/modulith \
  | jq 'keys'

curl -fsS http://127.0.0.1:9090/actuator/modulith \
  | jq '.notification.dependencies'
~~~

Với PowerShell:

~~~powershell
$data = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:9090/actuator/modulith'
$data.PSObject.Properties.Name
$data.notification.dependencies
~~~

Nếu endpoint yêu cầu quyền, bổ sung credentials bằng cách phù hợp; những lệnh chưa xác thực ở trên chỉ phục vụ lab hoặc môi trường quản trị nội bộ đã được cấp quyền.

## 6. Smoke test tự động sau triển khai

Một smoke test hữu ích cần kiểm tra **HTTP**, **hình dạng JSON**, **module chủ chốt** và **một vài quan hệ trọng yếu**. Ví dụ Bash, giả sử endpoint nội bộ cho phép đọc không cần token (hệ thống có auth cần truyền credentials phù hợp):

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Ví dụ: export ACTUATOR_BASE=http://127.0.0.1:9090/actuator
: "$ACTUATOR_BASE"

response="$(curl --fail --silent --show-error \
  "$ACTUATOR_BASE/modulith")"

# JSON phải là object và có đủ ba module.
jq -e '
  type == "object"
  and has("order")
  and has("payment")
  and has("notification")
' <<< "$response" > /dev/null

# Module order phải thuộc package dự kiến.
jq -e '
  .order.basePackage
  | type == "string" and startswith("com.example.shop.order")
' <<< "$response" > /dev/null

# Notification phụ thuộc vào event contract của order.
jq -e '
  .notification.dependencies
  | any(.[]; .target == "order"
      and (.types | index("EVENT_LISTENER") != null))
' <<< "$response" > /dev/null

echo "PASS: Modulith endpoint matches expected module architecture"
~~~

Đây là script **dành cho kiến trúc ví dụ**. Khi dùng trong dự án thật, thay tên module và package thành các giá trị được chấp thuận. Script thất bại khi curl không nhận HTTP 2xx, JSON không hợp lệ hoặc assertion không khớp, nhờ đó có thể dừng pipeline triển khai tại bước smoke test.

Nếu muốn xác minh **không có phụ thuộc ngược** từ order sang notification:

~~~bash
printf '%s' "$response" | jq -e '
  .order.dependencies
  | all(.[]; .target != "notification")
' > /dev/null
~~~

Chỉ đưa những ràng buộc thực sự quan trọng vào smoke test. Một dependency không tự là lỗi; lỗi nằm ở việc nó vi phạm hợp đồng kiến trúc. Mọi đổi mới có chủ đích trong module graph cần được review và cập nhật assertion đồng bộ.

## 7. Kiểm thử trong Docker và Kubernetes

### Docker

Ví dụ container mở cổng nghiệp vụ 8080 và cổng quản trị 9090:

~~~bash
docker run --rm \
  --name shop-modulith \
  -p 18080:8080 \
  -p 19090:9090 \
  shop-modulith:local

# Gọi từ host qua cổng đã publish.
curl -i http://127.0.0.1:19090/actuator/modulith
~~~

Image và cổng chỉ là ví dụ. Nếu management listener bind vào **127.0.0.1 bên trong container**, cổng publish từ host có thể không truy cập được. Cần đối chiếu **management.server.address**, network container, port mapping và firewall. Trong production, nên chỉ cho phép mạng quản trị kết nối vào endpoint này.

### Kubernetes

Để kiểm tra một Pod cụ thể, dùng port-forward từ môi trường có quyền cluster:

~~~bash
# Thay <pod-name> bằng tên Pod thực tế.
kubectl -n shop port-forward pod/<pod-name> 19090:9090

# Trong terminal khác:
curl -i http://127.0.0.1:19090/actuator/modulith
~~~

Nên kiểm tra đúng **Pod và revision** đang được đánh giá. Trong rolling deployment, truy cập qua Service có thể được load balance tới Pod ở phiên bản trước. Port-forward không tự bỏ qua xác thực HTTP của ứng dụng và không thay thế chính sách bảo mật hạ tầng.

Khi ghi bằng chứng kiểm thử, lưu **namespace, Pod/instance, image digest/tag, environment/profile, thời điểm và URL quản trị**. JSON đúng nhưng đọc từ nhầm bản release không có giá trị xác nhận bản cần kiểm thử.

## 8. Chẩn đoán HTTP và bảo mật

| Kết quả | Nguyên nhân nên xem xét | Cách chẩn đoán |
| --- | --- | --- |
| **200 + JSON hợp lệ** | Endpoint hoạt động. | Tiếp tục kiểm tra module list và dependencies. |
| **401 Unauthorized** | Thiếu/sai thông tin xác thực. | Kiểm tra token, auth scheme, policy gateway. |
| **403 Forbidden** | Có danh tính nhưng thiếu quyền hoặc policy chặn. | Kiểm tra role/authority, Spring Security, gateway. |
| **404 Not Found** | Sai path/port/endpoint ID, thiếu artifact hoặc exposure; cũng có thể từ proxy. | Kiểm tra discovery, dependency, base-path, route và log nguồn 404. |
| **502/503/504** | Gateway hoặc upstream không sẵn sàng. | Xem ingress, Pod, readiness và timeout. |
| **Connection refused/timeout** | Không có listener/cổng không tới được. | Kiểm tra process, port, address, firewall, container network. |
| **200 nhưng thiếu module** | Sai build/profile, package thay đổi, custom detection. | Đối chiếu artifact và cấu hình application modules. |
| **200 nhưng dependency sai** | Thay đổi API, bean reference hoặc listener contract. | So module graph, architecture test và diff code. |

**Không suy nguyên nhân duy nhất từ status code.** Một HTTP 404 có thể đến từ ingress hoặc reverse proxy trước khi request đến Spring Boot; cần nhìn response headers/log và kiểm tra từ mạng nội bộ gần ứng dụng hơn.

### Positive và negative security test

Với môi trường có chính sách phân quyền:

1. **Client không được cấp quyền:** endpoint phải bị từ chối (chẳng hạn HTTP 401/403) hoặc không thể tới qua mạng quản trị, đúng chính sách triển khai.
2. **Client được cấp quyền:** endpoint trả 200 và JSON hợp lệ.

Ví dụ kiểm tra HTTP status mà không in body:

~~~bash
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  "https://management.internal.example/actuator/modulith"
~~~

Nếu dự án tự định nghĩa **SecurityFilterChain**, Spring Boot có thể nhường cơ chế kiểm soát cho cấu hình ấy. Không mặc định endpoint an toàn chỉ vì có Spring Security trên classpath. Metadata kiến trúc có thể chứa tên package nội bộ, nên cần giới hạn phạm vi expose và quyền đọc.

## 9. So khớp runtime với kiểm thử kiến trúc

| Công cụ | Điều chứng minh | Điều chưa chứng minh |
| --- | --- | --- |
| **Module graph / tài liệu sinh từ code** | Cấu trúc và quan hệ của bản code dùng tạo tài liệu. | Bản đang chạy có đúng artifact đó hay không. |
| **ApplicationModules.verify()** | Bản code được kiểm thử tuân thủ các quy tắc ranh giới module. | Endpoint đã expose hoặc có bảo mật đúng hay chưa. |
| **GET /actuator/modulith** | Bản đã khởi động nhận diện module, package và dependencies nào. | Một event listener đã hoàn tất, event đã giao bền vững hoặc trace đã xuất thành công. |

Ví dụ test kiến trúc trước khi triển khai:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ShopApplication** là class chính giả định. Nên chạy kiểm thử này trong pipeline build, sau đó chạy HTTP smoke check trên đúng bản đã deploy. Hai cách kiểm tra bổ sung cho nhau.

Các thay đổi trong JSON cần điều tra: module mới hoặc biến mất, **basePackage** đổi bất ngờ, dependency **USES_COMPONENT** từ order sang notification (trong thiết kế event-driven muốn tránh gọi trực tiếp), hoặc **EVENT_LISTENER** không còn được nhận diện. Khi phát hiện khác biệt, kiểm tra mã nguồn và cấu hình trước khi kết luận đây là lỗi runtime.

## 10. Kết hợp Module Actuator với observability

**/actuator/modulith** trả lời câu hỏi **“những module nào tồn tại và chúng phụ thuộc nhau ra sao?”**. Nó không cho biết luồng xử lý nghiệp vụ vừa chạy như thế nào. Các nguồn bổ sung:

| Câu hỏi vận hành | Nguồn phù hợp |
| --- | --- |
| Bản chạy có cấu trúc module nào? | Module Actuator JSON. |
| Ứng dụng có sẵn sàng nhận traffic? | **/actuator/health**, readiness probes. |
| Có bao nhiêu domain event được phát? | Micrometer event metrics của Spring Modulith, ví dụ **module.events.published**. |
| Tương tác module nào chậm? | Module spans và tracing qua Zipkin hoặc OTLP/backend phù hợp. |
| Listener bất đồng bộ nào lỗi? | Structured logs, trace, metrics theo outcome khi được instrument. |
| Publication nào còn chưa hoàn tất? | Event Publication Registry nếu được cấu hình với backend tương ứng. |
| Trace bị ngắt khi đổi thread? | Kiểm tra context propagation, executor và tương quan bằng eventId. |

Ví dụ: module notification không gửi email sau khi đặt đơn. Actuator có thể cho thấy module **notification** tồn tại và có quan hệ **EVENT_LISTENER** với **order**. Để biết sự kiện **OrderPlaced** đã được công bố và listener chạy đến đâu, phải xem metric công bố, logs có eventId, tracing và trạng thái publication; HTTP 200 từ endpoint kiến trúc không đủ.

~~~mermaid
flowchart TD
    M["Module Actuator"] --> Arch["Ranh giới và quan hệ module"]
    H["Health"] --> Ready["Sẵn sàng phục vụ"]
    E["Event metrics"] --> Count["Số sự kiện phát"]
    T["Tracing"] --> Calls["Đường đi và thời gian"]
    L["Logs + eventId"] --> Errors["Chi tiết lỗi"]
    P["Publication Registry"] --> Pending["Việc chưa hoàn tất nếu có"]
    Arch --> Investigation["Đối chiếu kiến trúc và runtime"]
    Ready --> Investigation
    Count --> Investigation
    Calls --> Investigation
    Errors --> Investigation
    Pending --> Investigation
~~~

## 11. Checklist kiểm thử sau deploy

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| **Đúng bản chạy** | Xác nhận image/revision, Pod/instance và profile. |
| **Endpoint** | URL quản trị đúng; client có quyền nhận HTTP 200. |
| **JSON** | Parse được; object gốc và các module bắt buộc có mặt. |
| **Cấu trúc** | basePackage và quan hệ target/types đúng kiến trúc. |
| **Phụ thuộc cấm** | Không có dependency trực tiếp trái hợp đồng. |
| **Phân quyền** | Client không có quyền không đọc được metadata. |
| **Đồng nhất** | Các replica cùng revision trả metadata nhất quán. |
| **Đối chiếu** | Architecture test trong build tương ứng đã chạy. |
| **Điều tra** | Khi cần có metrics/logs/traces bổ sung. |

Lưu bằng chứng gồm **môi trường, thời điểm, revision, instance, status, module list và kết quả assertion**; không lưu token vào log CI. Với hệ thống nhiều module, nên kiểm tra những hợp đồng có ý nghĩa nghiệp vụ thay vì cố đóng băng mọi chi tiết không ảnh hưởng kiến trúc.

## 12. Câu hỏi tự kiểm tra

1. Vì sao **/actuator/health** trả 200 nhưng **/actuator/modulith** vẫn có thể trả 404?
2. HTTP 200 từ Module Actuator chứng minh được điều gì và chưa chứng minh được điều gì?
3. Nếu notification nhận sự kiện do order công bố, loại dependency EVENT_LISTENER đi theo chiều nào?
4. Vì sao localhost trong container khác localhost trên máy host?
5. Smoke test metadata runtime khác gì kiểm thử **ApplicationModules.verify()**?
6. Trong sự cố listener bất đồng bộ, vì sao phải kết hợp Actuator với metrics, tracing và context propagation?

## 13. Nguồn tham khảo chính thức

- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — Insight starter, Module Actuator, metadata JSON, observability.
- **Spring Modulith — ApplicationModulesEndpoint API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/actuator/ApplicationModulesEndpoint.html — endpoint ID và nhiệm vụ công bố module metadata.
- **Spring Boot — Actuator Endpoints:** https://docs.spring.io/spring-boot/reference/actuator/endpoints.html — HTTP exposure, access, bảo mật, discovery.
- **Spring Boot — Monitoring and Management Over HTTP:** https://docs.spring.io/spring-boot/reference/actuator/monitoring.html — cổng và đường dẫn quản trị.

## 14. Tổng kết

Kiểm thử **Module Actuator trong môi trường chạy thật** là kiểm tra theo bốn lớp: **dependency và exposure**, **host/port/path cùng phân quyền**, **HTTP và schema JSON**, **module/dependency so với hợp đồng kiến trúc**. Thực hiện trên đúng bản đã deploy sẽ giúp phát hiện thiếu artifact, sai profile hoặc kiến trúc bị thay đổi ngoài mong đợi.

Kết hợp kết quả endpoint với module graph, **ApplicationModules.verify()**, Actuator health, event metrics, tracing và logs giúp nối **kiến trúc dự kiến** với **hành vi quan sát được**. Mỗi loại bằng chứng trả lời một câu hỏi khác nhau; dùng đúng nguồn sẽ giúp quá trình kiểm chứng và điều tra sự cố đáng tin cậy hơn.
