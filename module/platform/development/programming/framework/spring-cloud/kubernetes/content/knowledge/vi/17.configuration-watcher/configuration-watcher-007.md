# Địa chỉ ứng dụng, management port và đường dẫn Actuator

## Mục tiêu bài học

Trong chương **Configuration Watcher** của module **SPRING_CLOUD_KUBERNETES**, watcher có thể phát hiện ConfigMap thay đổi nhưng vẫn không refresh được ứng dụng vì gọi sai địa chỉ, cổng hoặc đường dẫn.

Một URL refresh cần khớp đồng thời:

```text
HTTP method + scheme + host + port + đường dẫn endpoint
```

Sau bài học, bạn có thể:

- Phân biệt địa chỉ Pod, địa chỉ Service và địa chỉ đi qua Ingress.
- Phân biệt cổng nghiệp vụ, cổng Service, cổng management và cổng của watcher.
- Tính đúng đường dẫn Actuator khi có context path hoặc management server riêng.
- Khai báo metadata để watcher xác định đích gọi.
- Chẩn đoán riêng lỗi discovery, kết nối, TLS, endpoint và phân quyền.

Ví dụ chính dùng ứng dụng `orders` trong namespace `shop`, chạy nghiệp vụ trên `8080` và management trên `9090`. Những chi tiết về thứ tự ưu tiên khi dựng URL được đối chiếu với mã nguồn watcher **5.1.0**; cần kiểm tra lại khi dùng dòng phiên bản khác.

## 1. Một địa chỉ ứng dụng có nhiều ý nghĩa

| Địa chỉ | Ví dụ minh họa | Khi nào sử dụng |
|---|---|---|
| Pod IP | `10.42.1.17` | Gọi trực tiếp một instance trong mạng cụm |
| Service DNS | `orders.shop.svc.cluster.local` | Truy cập Service để được định tuyến tới backend |
| ClusterIP của Service | `10.96.20.30` | Địa chỉ ảo của Service trong cụm |
| Tên miền Ingress | `orders.example.com` | Đi theo đường vào có routing, TLS hoặc rewrite |
| Loopback | `127.0.0.1` | Gọi tiến trình trong cùng network namespace |

Trong phương án HTTP, Configuration Watcher dùng DiscoveryClient để lấy các ServiceInstance rồi gửi yêu cầu tới từng instance phù hợp. Không mặc định watcher gọi tên miền Ingress của ứng dụng.

Các instance do discovery trả về có host, port, scheme và metadata. Chúng là đầu vào cần quan sát khi chẩn đoán, thay vì chỉ nhìn URL mà người dùng truy cập từ trình duyệt. Xem [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

### 1.1. localhost phụ thuộc nơi chạy lệnh

Nếu watcher chạy trong Pod riêng, `localhost:9090` trong watcher trỏ tới network namespace của Pod watcher. Nó không trỏ tới Pod `orders`.

Các container trong cùng một Pod thường dùng chung network namespace, nhưng điều đó không áp dụng giữa hai Deployment khác nhau.

Một lệnh `curl` chạy thành công trong container ứng dụng tới `localhost` chưa chứng minh watcher từ Pod khác kết nối được.

### 1.2. Một request qua Service không cập nhật mọi replica

Một request `POST` tới Service thường được đưa tới một backend. Khi có ba replica, gọi Service một lần không chứng minh ba replica đều nhận refresh.

DiscoveryClient giúp watcher xác định tập instance cần gọi. Spring Cloud LoadBalancer chọn đích cho một lời gọi cũng không tự tạo cơ chế phát tín hiệu tới tất cả instance.

## 2. Bốn loại cổng thường bị nhầm

| Cấu hình | Ví dụ | Ý nghĩa |
|---|---|---|
| `server.port` | `8080` | Listener HTTP nghiệp vụ của ứng dụng |
| `management.server.port` | `9090` | Listener management riêng nếu được cấu hình khác cổng nghiệp vụ |
| `Service.spec.ports[].port` | `80` | Cổng người gọi Service sử dụng |
| `Service.spec.ports[].targetPort` | `8080` hoặc tên `http` | Cổng backend mà Service chuyển tới |

Ngoài ra:

- `containerPort` mô tả cổng trong Pod spec; nó không làm JVM tự mở listener.
- Watcher có cổng quản trị của chính nó, thường là `8888` trong ví dụ triển khai chính thức. Cổng này không phải cổng management của `orders`.
- Cổng máy cá nhân dùng khi port-forward cũng không phải cổng mà watcher sẽ dùng trong cụm.

Ví dụ đường nghiệp vụ:

```text
orders:80
   -> Service chuyển tới Pod:8080

Đường quản trị trực tiếp:
watcher
   -> Pod:9090
```

Khi gọi trực tiếp `PodIP:9090`, request không đi qua phép ánh xạ `Service port -> targetPort`. Không thay `9090` bằng `80` chỉ vì Service đang công bố cổng `80`.

Kubernetes giải thích quan hệ giữa `port` và `targetPort` trong [Service](https://kubernetes.io/docs/concepts/services-networking/service/).

## 3. Xác định endpoint Actuator thực tế của Spring Boot

### 3.1. Cùng cổng nghiệp vụ

Với cấu hình Servlet:

```yaml
server:
  port: 8080
  servlet:
    context-path: /api

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,refresh
```

Nếu endpoint refresh tồn tại và được phép truy cập, đường gọi là:

```text
POST http://POD_IP:8080/api/manage/refresh
```

`/api` là context path của ứng dụng Servlet. Với ứng dụng reactive, xét `spring.webflux.base-path` tương ứng, không sao chép thuộc tính Servlet vào WebFlux.

### 3.2. Management server có cổng riêng

Ví dụ chính của bài:

```yaml
server:
  port: 8080
  servlet:
    context-path: /api

management:
  server:
    port: 9090
    base-path: /ops
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,refresh
  endpoint:
    health:
      probes:
        enabled: true
```

Các đường dự kiến:

```text
Nghiệp vụ:              http://POD_IP:8080/api/...
Health management:      http://POD_IP:9090/ops/manage/health
Refresh management:     POST http://POD_IP:9090/ops/manage/refresh
```

Khi management server dùng cổng riêng, base path của web endpoint được đặt tương đối với `management.server.base-path`. Không tự thêm `server.servlet.context-path=/api` vào đường management riêng.

Các quy tắc này được mô tả trong [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html).

### 3.3. Base path khác endpoint cuối

`/ops/manage` là base path trong ví dụ. `/refresh` là phần cuối xác định thao tác.

Nếu ứng dụng remap endpoint refresh sang tên khác bằng cơ chế path mapping, không giả định watcher tự đọc được mapping đó. Phải kiểm tra khả năng cấu hình của phiên bản watcher và URL nó thực sự dựng.

Chỉ thêm `refresh` vào exposure cũng chưa đủ nếu ứng dụng không có cơ chế refresh từ Spring Cloud, endpoint bị vô hiệu hóa hoặc bị giới hạn quyền thực thi. Actuator của Spring Boot và chức năng refresh của Spring Cloud là hai phần cần được tích hợp đúng.

## 4. Watcher dựng URL theo những đầu vào nào?

Theo triển khai `HttpRefreshTrigger` của watcher 5.1.0:

1. Scheme và host lấy từ ServiceInstance.
2. Nếu metadata có `boot.spring.io/actuator`, dùng nhánh xử lý annotation để lấy port và base path.
3. Nếu không có annotation, dùng `actuatorPath` phía watcher; port dùng `actuatorPort` nếu có cấu hình hợp lệ, nếu không dùng port của ServiceInstance.
4. Nối endpoint theo chiến lược: `/refresh` cho refresh hoặc `/shutdown` cho shutdown.

Xem [mã nguồn HttpRefreshTrigger 5.1.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-controllers/spring-cloud-kubernetes-configuration-watcher/src/main/java/org/springframework/cloud/kubernetes/configuration/watcher/HttpRefreshTrigger.java).

Mô hình minh họa cho chiến lược refresh:

```text
scheme từ instance
  + host từ instance
  + management port được chọn
  + management base path được chọn
  + /refresh
```

Ví dụ với instance có host `10.42.1.17` và scheme `http`:

| Management port | Base path | URL cần nhận được |
|---|---|---|
| 8080 | /actuator | `http://10.42.1.17:8080/actuator/refresh` |
| 8080 | /api/manage | `http://10.42.1.17:8080/api/manage/refresh` |
| 9090 | /ops/manage | `http://10.42.1.17:9090/ops/manage/refresh` |

Các IP trong bài chỉ dùng để minh họa. Không ghi cứng Pod IP vào cấu hình dài hạn; Pod có thể bị thay.

## 5. Khai báo management port và path trên Service

### 5.1. Annotation phải nằm trên Service được discovery sử dụng

Ví dụ Service nghiệp vụ:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop
  annotations:
    boot.spring.io/actuator: "http://:9090/ops/manage"
spec:
  selector:
    app.kubernetes.io/name: orders
  ports:
    - name: http
      port: 80
      targetPort: http
```

Với scheme/host discovery phù hợp, watcher dự kiến gửi:

```text
POST http://POD_IP:9090/ops/manage/refresh
```

Cú pháp `http://:9090/ops/manage` là metadata mô tả port và path theo quy ước watcher; không dùng nguyên chuỗi đó làm URL để `curl`.

Tài liệu chính thức giới thiệu annotation trong [Non-Default Management Port and Actuator Path](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html#non-default-management-port-and-actuator-path).

Đặt annotation này vào ConfigMap hoặc chỉ trong Pod template không tương đương với việc đặt nó trên Service mà watcher lấy metadata từ đó.

### 5.2. Không thêm /refresh vào annotation

Giá trị đúng cho ví dụ:

```yaml
boot.spring.io/actuator: "http://:9090/ops/manage"
```

Giá trị dễ gây gọi sai:

```yaml
boot.spring.io/actuator: "http://:9090/ops/manage/refresh"
```

Vì watcher còn nối endpoint thao tác, giá trị thứ hai có thể dẫn tới đường `/ops/manage/refresh/refresh`.

Dùng base path rõ ràng, tránh dấu gạch chéo dư ở cuối. Không mặc định mọi nhánh xử lý metadata đều chuẩn hóa chuỗi giống nhau.

### 5.3. Annotation không tự tạo listener

Thêm metadata không làm ứng dụng tự chuyển từ `8080` sang `9090`. Phải đồng bộ:

- Cấu hình Spring Boot.
- Listener mà JVM thực sự mở.
- Metadata Service.
- Đích discovery và đường mạng.
- Quy tắc bảo vệ endpoint.

Nếu ứng dụng vẫn chỉ nghe `8080`, annotation `9090` có thể đúng cú pháp nhưng request vẫn không kết nối được.

## 6. Cấu hình chung ở phía watcher

Khi các ứng dụng trong phạm vi watcher cùng dùng cổng và base path, có thể cấu hình ở watcher:

```yaml
spring:
  cloud:
    kubernetes:
      configuration:
        watcher:
          actuator-path: /ops/manage
          actuator-port: 9090
```

Đây là cấu hình của **Deployment watcher**, không phải cách mở management listener trong ứng dụng nghiệp vụ.

Nếu dùng biến môi trường, các tên tương ứng theo binding thuộc tính là:

```yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_ACTUATORPATH
    value: /ops/manage
  - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_ACTUATORPORT
    value: "9090"
```

Trong thuộc tính watcher, `actuator-path` vẫn là base path; không ghi cả `/refresh`.

Ở mã nguồn 5.1.0 đã đối chiếu, mặc định `actuatorPath` là `/actuator` và `actuatorPort` âm biểu thị dùng port instance. Xem [ConfigurationWatcherConfigurationProperties 5.1.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-controllers/spring-cloud-kubernetes-configuration-watcher/src/main/java/org/springframework/cloud/kubernetes/configuration/watcher/ConfigurationWatcherConfigurationProperties.java).

### 6.1. Annotation và cấu hình chung không phải lúc nào cũng được trộn từng trường

Trong nhánh dựng URI đã nêu, annotation có mặt được xử lý theo nhánh riêng. Không thiết kế dựa trên giả định “annotation chỉ có path thì port tự lấy từ cấu hình chung”.

Dùng một hợp đồng rõ ràng:

- Nếu dùng metadata theo Service, cung cấp đủ port và base path phù hợp.
- Nếu dùng cấu hình chung, tránh metadata còn sót làm ghi đè kỳ vọng.
- Khi thay cơ chế, xác minh URL cuối trong log watcher.

Đây là chi tiết theo phiên bản; tài liệu triển khai của nhóm nên ghi cả version watcher và nơi định nghĩa mỗi giá trị.

### 6.2. Metadata phải đi tới ServiceInstance

Annotation trên Service còn phải xuất hiện dưới key mà watcher đọc trong metadata discovery.

Khi cần khai báo rõ ở watcher:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        metadata:
          add-annotations: true
```

Nếu cấu hình prefix cho annotation metadata, kiểm tra key thực tế có còn khớp `boot.spring.io/actuator` mà phiên bản watcher tra cứu hay không. Không chỉ nhìn annotation trong YAML rồi kết luận watcher đã sử dụng nó.

## 7. Host và scheme không được suy từ hình thức của annotation

Một giới hạn quan trọng của mã nguồn watcher 5.1.0 là host và scheme được dựng từ ServiceInstance. Nhánh annotation lấy path và port; không dùng host/scheme của annotation làm một URL đích tùy ý.

Hệ quả cho thiết kế:

- Không đặt một host Ingress vào annotation rồi mặc định watcher sẽ chuyển sang gọi Ingress.
- Không mặc định đổi `http` thành `https` trong annotation là đã bật TLS cho request.
- Khi watcher vẫn gọi HTTP dù kỳ vọng HTTPS, kiểm tra scheme/security metadata của instance và URL thực tế.
- Khi cổng nghiệp vụ và management có chính sách TLS khác nhau, phải đánh giá rõ khả năng của phiên bản, discovery và HTTP client đang dùng.

Ví dụ chính của bài dùng HTTP nội bộ cho cả hai listener để làm rõ port/path. Với HTTPS, cần xét thêm CA tin cậy, tên trên chứng chỉ, SNI và danh tính gọi.

Nếu watcher gọi Pod IP nhưng chứng chỉ chỉ có tên DNS Service, kiểm tra chứng chỉ có thể thất bại. Không dùng việc tắt kiểm tra TLS làm quy trình sửa địa chỉ; chọn một thiết kế địa chỉ và chứng chỉ tương thích.

Các cấu hình `management.server.ssl.*` chỉ ảnh hưởng listener management phía ứng dụng. Chúng không tự cập nhật trust store hoặc cơ chế chọn scheme phía watcher.

## 8. Service có cần công bố cổng management không?

Cần phân biệt hai đường gọi:

| Đường gọi | Cần khai báo cổng management trên Service? |
|---|---|
| Trực tiếp `PodIP:9090` | Không bắt buộc chỉ để có listener trực tiếp |
| Qua `orders:9090` | Service phải có port tương ứng chuyển tới backend |
| Qua Service quản trị riêng | Service đó phải có selector và ánh xạ cổng đúng |
| Qua Ingress/gateway | Cần route và backend tương ứng theo thiết kế |

Với Service ở mục 5 chỉ có `port: 80`, việc gọi `orders:9090` không phải phép thử tương đương với `PodIP:9090`.

Nếu cần một Service quản trị riêng để chẩn đoán hoặc phục vụ hệ thống vận hành:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-management
  namespace: shop
spec:
  selector:
    app.kubernetes.io/name: orders
  ports:
    - name: management
      port: 9090
      targetPort: management
```

Service quản trị riêng không tự thay đích ứng dụng của watcher. Nếu watcher vẫn tìm ứng dụng `orders`, metadata cần được đặt trên Service phù hợp với đường discovery đó.

Không dùng kết quả gọi Service quản trị một lần để kết luận mọi Pod đã được refresh.

## 9. Chuẩn bị Pod: khai báo cổng và kiểm tra listener

Trích đoạn Pod template của ứng dụng:

```yaml
metadata:
  labels:
    app.kubernetes.io/name: orders
spec:
  containers:
    - name: orders
      image: registry.example.com/shop/orders:REPLACE_WITH_APPROVED_VERSION
      ports:
        - name: http
          containerPort: 8080
        - name: management
          containerPort: 9090
      readinessProbe:
        httpGet:
          path: /ops/manage/health/readiness
          port: management
      livenessProbe:
        httpGet:
          path: /ops/manage/health/liveness
          port: management
```

Đây là đoạn cấu hình để ghép vào Deployment phù hợp, không phải Deployment hoàn chỉnh. Thay image mẫu bằng ứng dụng thật đã có cấu hình và dependency cần thiết.

Hai lưu ý:

- Listener management chỉ bind `127.0.0.1` sẽ không nhận request từ watcher ở Pod khác dù `containerPort` đã khai báo.
- Probe chạy trên management server riêng có thể thành công trong khi đường phục vụ nghiệp vụ gặp lỗi. Thiết kế health check cần phản ánh khả năng phục vụ mà hệ thống yêu cầu.

`management.server.address` điều khiển địa chỉ bind của management server khi dùng cổng riêng; cần đối chiếu cấu hình thực tế. Cơ chế probe được mô tả trong [Kubernetes probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Không dùng `localhost` thành công hoặc trạng thái Pod Running thay cho kiểm tra kết nối liên Pod tới đúng listener.

## 10. Khi Service có nhiều port

Discovery có quy tắc chọn port cho ServiceInstance. Các đầu vào có thể bao gồm label `primary-port-name`, thuộc tính `spring.cloud.kubernetes.discovery.primary-port-name` và tên port `http`/`https`.

Ví dụ khai báo ý định cổng chính:

```yaml
metadata:
  name: orders
  labels:
    primary-port-name: http
spec:
  ports:
    - name: http
      port: 80
      targetPort: http
    - name: management
      port: 9090
      targetPort: management
```

Đừng phụ thuộc vào việc đảo thứ tự `ports` để watcher tình cờ chọn được cổng đúng. Với watcher cần management riêng, cung cấp metadata port/path rõ ràng.

Cổng discovery cũng có thể được thành phần gọi nghiệp vụ sử dụng. Đổi cổng chính toàn cục thành management để sửa refresh có thể làm các client nghiệp vụ gọi nhầm listener.

Kiểm tra cả dữ liệu Endpoints hoặc EndpointSlices và ServiceInstance thực tế. Khi sử dụng discovery backend khác hoặc phiên bản khác, không suy kết quả port chỉ từ một trường của Service.

## 11. Path Ingress và path bên trong Pod có thể khác

Giả sử Ingress nhận:

```text
https://orders.example.com/admin/refresh
```

rồi rewrite thành:

```text
http://POD_IP:9090/ops/manage/refresh
```

Nếu watcher gọi thẳng instance, nó cần đường **bên trong Pod**, không cần path trước rewrite.

Ngược lại, một lần `curl` thành công qua Ingress chỉ chứng minh đường Ingress hoạt động. Nó chưa chứng minh:

- Watcher có thể đi tới Pod IP.
- Cổng management cho phép nguồn watcher.
- URL watcher dựng trùng path nội bộ.
- HTTP client của watcher có đúng TLS và danh tính.

Khi có service mesh, ghi nhận cả chính sách mTLS, routing và quyền gọi của workload watcher. Host/path đúng vẫn có thể bị proxy từ chối.

Với IPv6 hoặc địa chỉ đặc biệt, để thư viện dựng URI và kiểm tra kết quả đúng cú pháp. Tránh ghép chuỗi IP và port thủ công trong mã tùy chỉnh.

## 12. Endpoint tồn tại, được expose và được phép gọi là ba việc khác nhau

Để `POST /ops/manage/refresh` có hiệu lực, cần đồng thời:

1. Ứng dụng có hỗ trợ endpoint refresh của Spring Cloud.
2. Endpoint không bị vô hiệu hóa hoặc giới hạn mất quyền thực thi.
3. Endpoint được expose qua HTTP.
4. Người gọi vượt qua HTTP authentication và authorization.
5. Quy tắc CSRF, nếu áp dụng, xử lý request quản trị theo thiết kế.
6. Mạng cho phép watcher kết nối đúng listener.

Cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,refresh
```

không tự cấp danh tính gọi cho watcher và không tự mở NetworkPolicy.

Kubernetes RBAC cho phép watcher đọc ConfigMap hoặc Service cũng không tương đương với quyền `POST` tới ứng dụng. Token Kubernetes không mặc nhiên là credential mà Spring Security của ứng dụng chấp nhận.

Spring Boot mô tả các lớp exposure và endpoint security trong [Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

Đổi base path không phải một biện pháp xác thực. Thiết kế mạng và danh tính gọi phù hợp, giữ quyền quản trị trong phạm vi cần thiết.

## 13. Kiểm tra mạng theo đúng hướng watcher gọi

Một rule ingress minh họa cho cổng management:

```yaml
# Trích đoạn rule bổ sung trong NetworkPolicy của ứng dụng.
ingress:
  - from:
      - podSelector:
          matchLabels:
            app.kubernetes.io/name: config-watcher
    ports:
      - protocol: TCP
        port: 9090
```

Với `podSelector` như trên, nguồn được chọn trong cùng namespace với policy. Watcher ở namespace khác cần thiết kế `namespaceSelector` và `podSelector` phù hợp.

Đây chỉ là một rule minh họa. Khi ghép thành NetworkPolicy đầy đủ, giữ các đường nghiệp vụ, health và vận hành cần thiết; không áp dụng nó như thể đã mô tả mọi lưu lượng của ứng dụng.

Nếu watcher bị cô lập egress, phía egress cũng phải cho phép kết nối cần thiết. Chính sách NetworkPolicy có tính cộng gộp và cần CNI hỗ trợ thực thi. Xem [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Một Pod chẩn đoán cùng namespace nhưng khác label, service account hoặc danh tính mesh có thể không có cùng quyền mạng với watcher.

## 14. Quy trình chẩn đoán URL refresh

### Bước 1: Xác định ứng dụng thực sự đang nghe ở đâu

Đối chiếu cấu hình listener, port và base path từ runtime hoặc nguồn cấu hình hiệu lực:

```text
server.port                  = 8080
management.server.port       = 9090
management.server.base-path  = /ops
management web base path     = /manage
endpoint thao tác            = /refresh
```

Từ đó lập URL mong muốn cho một Pod, không dùng Pod IP cũ đã bị thay.

### Bước 2: Kiểm tra Service và địa chỉ backend

```bash
kubectl get service orders -n shop -o yaml
kubectl get pods -n shop -l app.kubernetes.io/name=orders -o wide
kubectl get endpointslices -n shop -l kubernetes.io/service-name=orders -o yaml
```

Đối chiếu selector, Pod IP, readiness, tên port và port backend. Nếu discovery của phiên bản đang dùng đọc Endpoints, kiểm tra thêm tài nguyên tương ứng:

```bash
kubectl get endpoints orders -n shop -o yaml
```

Kết quả EndpointSlice đúng chưa tự chứng minh watcher có quyền đọc hoặc đang dùng backend đó.

### Bước 3: Đọc URL mà watcher thực sự gửi

```bash
kubectl logs deployment/config-watcher -n shop --tail=100
```

Tên Deployment cần khớp môi trường. Có thể bật DEBUG có kiểm soát cho package:

```yaml
logging:
  level:
    org.springframework.cloud.kubernetes.configuration.watcher: DEBUG
```

Đối chiếu scheme, host, port và path trong dòng gửi refresh với URL mong muốn. Không bật log toàn bộ payload Secret hoặc header xác thực để tìm một lỗi port/path.

### Bước 4: Kiểm tra endpoint từ port-forward

Trong môi trường lab được phép gọi refresh:

```bash
kubectl port-forward -n shop pod/TEN_POD_ORDERS 19090:9090
```

Ở terminal khác trên Windows:

```powershell
curl.exe --include --max-time 5 http://127.0.0.1:19090/ops/manage/health
curl.exe --include --max-time 10 --request POST http://127.0.0.1:19090/ops/manage/refresh
```

Thay tên Pod thật và dùng cơ chế xác thực của môi trường nếu cần. `19090` chỉ là cổng trên máy đang chạy port-forward; không đưa số này vào annotation của watcher.

Port-forward giúp xác minh listener và path trên một Pod. Nó không kiểm tra toàn bộ đường mạng từ watcher tới ứng dụng, nên thành công ở bước này chưa loại trừ NetworkPolicy hoặc mesh.

### Bước 5: Kiểm tra từ đường mạng tương đương watcher

Nếu một container chẩn đoán có sẵn `curl` và được cấp quyền phù hợp:

```bash
kubectl exec -n shop TEN_POD_CHAN_DOAN -- curl --include --max-time 5 http://POD_IP_THUC_TE:9090/ops/manage/health
```

Thay các giá trị mẫu. Không giả định image watcher hoặc image ứng dụng luôn có shell/curl. Muốn chứng minh chính sách áp dụng cho watcher, điểm kiểm tra phải có điều kiện mạng và danh tính tương đương.

Sau khi kết nối và path đã đúng, mới kiểm tra request `POST` theo quy trình lab hoặc vận hành đã được phép.

### Bước 6: Xác minh kết quả áp dụng

Một phản hồi HTTP thành công xác nhận request đã được xử lý theo endpoint, chưa chứng minh mọi bean hoặc mọi replica đã dùng dữ liệu mới.

Kiểm tra:

- Định danh cấu hình hiệu lực của từng Pod.
- Thuộc tính không nhạy cảm thực sự đổi.
- Hành vi của client hoặc tác vụ nghiệp vụ sử dụng cấu hình.
- Pod UID và số lần restart để phân biệt refresh với một lần thay Pod.

Một response chứa danh sách rỗng có thể chỉ ra không có key thay đổi theo cơ chế endpoint. Không tự quy response đó thành lỗi địa chỉ, cũng không dùng nó làm bằng chứng toàn bộ hệ thống đã hội tụ.

## 15. Phân loại lỗi theo bằng chứng

| Hiện tượng | Khả năng cần kiểm tra |
|---|---|
| Không tìm thấy instance | Namespace, tên ứng dụng, Service, selector, bộ lọc discovery, RBAC |
| DNS không phân giải | Sai tên Service/namespace hoặc đường DNS của điểm gọi |
| Connection refused | Sai port, listener chưa mở, bind loopback hoặc Pod đang khởi động lại |
| Timeout | NetworkPolicy, routing, mesh, kết nối hoặc ứng dụng không phản hồi kịp |
| TLS handshake lỗi | Scheme, CA tin cậy, tên chứng chỉ, SNI hoặc yêu cầu client certificate |
| HTTP 404 | Sai cổng/path, thiếu endpoint, chưa expose; cũng có thể bị lớp bảo mật che giấu |
| HTTP 405 | Dùng sai method trên một route có tồn tại; cần đối chiếu route cụ thể |
| HTTP 401 | Chưa xác thực hoặc credential không được chấp nhận |
| HTTP 403 | Thiếu quyền, CSRF hoặc chính sách của proxy/ứng dụng |
| HTTP 3xx tới trang đăng nhập | Đang đi vào luồng đăng nhập; chưa chứng minh refresh được thực thi |
| HTTP thành công nhưng giá trị cũ | Nguồn chưa đổi, bị override, bean không refresh hoặc kiểm tra nhầm Pod |

Mã trạng thái là dấu hiệu chẩn đoán, không phải kết luận duy nhất. Luôn xác định response đến từ JVM, proxy, gateway hay một ứng dụng khác đang nghe tại cổng đó.

Tránh tăng delay hoặc cấp thêm quyền Kubernetes chỉ để thử sửa một URL management đang sai.

## 16. Thực hành đối chiếu các biến thể

Dùng một ứng dụng lab hỗ trợ refresh, thay đổi từng yếu tố và ghi nhận URL thực tế:

| Trường hợp | URL refresh cần đạt với giả định HTTP |
|---|---|
| Cổng chung 8080, không context path, base mặc định | `http://POD_IP:8080/actuator/refresh` |
| Cổng chung 8080, context `/api`, base `/manage` | `http://POD_IP:8080/api/manage/refresh` |
| Management 9090, management base `/ops`, web base `/manage` | `http://POD_IP:9090/ops/manage/refresh` |
| Annotation có thêm `/refresh` | Quan sát lỗi nối lặp endpoint, rồi sửa về base path |
| Management bind loopback | Local có thể gọi được nhưng watcher ở Pod khác không gọi được |
| Service chỉ công bố port 80 | Phân biệt kiểm tra Service:9090 với kiểm tra Pod:9090 |

Với mỗi trường hợp, ghi rõ:

1. Cấu hình ứng dụng.
2. Cổng Pod và Service.
3. Metadata hoặc cấu hình chung phía watcher.
4. ServiceInstance/URL được quan sát.
5. HTTP status và lớp trả response.
6. Phiên bản cấu hình ứng dụng thực sự đang dùng.

Hợp đồng địa chỉ hoàn chỉnh phải trả lời được **watcher gọi instance nào, qua giao thức nào, cổng nào và path nào**. Khi bốn giá trị đó khớp runtime và chính sách truy cập, việc chẩn đoán các bước đọc lại nguồn và áp dụng cấu hình trong Spring mới có cơ sở rõ ràng.
