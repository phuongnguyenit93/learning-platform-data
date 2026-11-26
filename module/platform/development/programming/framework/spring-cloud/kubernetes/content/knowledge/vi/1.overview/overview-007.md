# Thành phần chạy trong ứng dụng và thành phần triển khai riêng

Khi tích hợp một ứng dụng Spring với Kubernetes, thêm một thư viện vào ứng dụng và triển khai thêm một dịch vụ trong cluster là hai quyết định kiến trúc khác nhau. Chúng làm thay đổi nơi chạy mã, danh tính truy cập Kubernetes API, đường đi của yêu cầu và cách xử lý sự cố.

Spring Cloud Kubernetes có cả thành phần tích hợp vào tiến trình ứng dụng và những thành phần có thể triển khai độc lập để cung cấp chức năng dùng chung. Hiểu ranh giới này giúp tránh hai nhầm lẫn phổ biến: cho rằng mọi starter đều cần một server riêng, hoặc cho rằng chỉ thêm thư viện là đã có Configuration Watcher hoạt động trong cluster.

Bài học thuộc phần **Tổng quan** của module **SPRING_CLOUD_KUBERNETES**. Phạm vi là cách bố trí DiscoveryClient, tích hợp ConfigMap/Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời liên hệ đến RBAC, cập nhật cấu hình và sức khỏe Pod để chọn đúng những thành phần cần thiết.

## 1. Phân loại theo nơi chạy và trách nhiệm

Một thành phần **chạy trong ứng dụng** là mã thư viện được đóng gói cùng ứng dụng, thường được Spring khởi tạo thành bean trong cùng JVM. Nó chia sẻ vòng đời tiến trình, tài nguyên và danh tính Kubernetes của Pod ứng dụng.

Một thành phần **triển khai riêng** có tiến trình và workload riêng, thường là Deployment với Pod, ServiceAccount và cấu hình vận hành riêng. Ứng dụng giao tiếp với nó qua mạng hoặc nhận tín hiệu từ nó.

| Tiêu chí | Chạy trong ứng dụng | Triển khai riêng |
| --- | --- | --- |
| Đơn vị phân phối | Dependency trong bản build của ứng dụng | Container image và manifest của một workload khác |
| Nơi thực thi | Cùng JVM với mã nghiệp vụ | Tiến trình riêng, thường trong Pod riêng |
| Vòng đời | Khởi động và dừng cùng ứng dụng | Có thể nâng cấp, khởi động lại và mở rộng độc lập |
| Danh tính Kubernetes | ServiceAccount của Pod ứng dụng nếu truy cập API | ServiceAccount của workload riêng nếu truy cập API |
| Đường kết nối bổ sung | Có thể gọi Kubernetes API trực tiếp từ ứng dụng | Có thêm kết nối ứng dụng–dịch vụ dùng chung hoặc dịch vụ dùng chung–ứng dụng |
| Phạm vi ảnh hưởng khi lỗi | Gắn với từng replica ứng dụng | Có thể ảnh hưởng nhiều ứng dụng cùng sử dụng dịch vụ đó |

Cùng namespace không có nghĩa là cùng tiến trình. Cùng Pod cũng chưa chắc cùng tiến trình: sidecar là một container khác trong cùng Pod, không phải bean được nhúng vào JVM ứng dụng. Việc triển khai sidecar là một lựa chọn bố trí riêng, không phải yêu cầu chung để sử dụng Spring Cloud Kubernetes.

## 2. Những thành phần thường chạy trong ứng dụng

### 2.1. DiscoveryClient và implementation khám phá

`DiscoveryClient` là abstraction của Spring Cloud để truy vấn dịch vụ và instance. Khi dùng một implementation của Spring Cloud Kubernetes truy cập Kubernetes API trực tiếp, mã khám phá chạy trong chính ứng dụng và sử dụng thông tin tài nguyên trong cluster làm nguồn dữ liệu.

Luồng khái niệm:

```text
JVM của order-api
  mã nghiệp vụ hoặc thành phần Spring Cloud
                 |
                 v
          DiscoveryClient
                 |
                 v
    Kubernetes client trong ứng dụng
                 |
                 v
         Kubernetes API server
```

Mỗi replica ứng dụng có instance của các bean và trạng thái nội bộ riêng. Nếu implementation dùng cache hoặc cơ chế theo dõi tài nguyên, các trạng thái đó cũng gắn với từng tiến trình; không nên hình dung có một đối tượng Java dùng chung cho tất cả replica.

Trong mô hình này, ServiceAccount của `order-api` phải có quyền trên những tài nguyên mà implementation thực sự truy cập. Phạm vi namespace và loại tài nguyên cần đọc phụ thuộc cấu hình và phiên bản, chẳng hạn Service cùng thông tin endpoint liên quan. Không nên mặc định rằng mọi tính năng discovery đều cần quyền trên toàn cluster.

Nếu chỉ cần gọi một Service bằng tên DNS như `http://catalog-api:8080`, ứng dụng có thể dùng HTTP client thông thường mà không cần `DiscoveryClient`. DNS và cơ chế định tuyến Service thuộc hạ tầng Kubernetes, không phải một server Spring Cloud Kubernetes phải được triển khai thêm cho từng ứng dụng.

### 2.2. Thành phần đưa ConfigMap và Secret vào cấu hình Spring

Tích hợp cấu hình của Spring Cloud Kubernetes có thể chạy trong JVM ứng dụng để đưa nguồn cấu hình Kubernetes vào Spring `Environment`. Khi chọn cách đọc qua API, ứng dụng cần cấu hình nguồn dữ liệu, kết nối API và quyền thích hợp.

Điểm cần phân biệt là **nơi lưu dữ liệu** và **nơi chạy mã đọc dữ liệu**:

- ConfigMap và Secret là tài nguyên Kubernetes.
- Bean đọc và chuyển đổi dữ liệu thành property source có thể nằm trong ứng dụng.
- Dữ liệu tồn tại trong cluster không có nghĩa là mọi ứng dụng tự nhìn thấy hoặc tự nạp dữ liệu đó.

Đọc Secret qua API cần được bật và cấp quyền theo nhu cầu thực tế. Không nên coi khả năng hỗ trợ Secret của một thư viện là lý do để cấp quyền đọc Secret cho mọi ServiceAccount.

Kubernetes cũng có thể cung cấp cấu hình qua biến môi trường hoặc volume. Với cách này, tiến trình ứng dụng có thể chỉ đọc môi trường hoặc file bằng cơ chế thông thường của Spring Boot. Ứng dụng không nhất thiết cần thư viện Spring Cloud Kubernetes để lấy những giá trị đã được Kubernetes cung cấp sẵn.

### 2.3. Spring Cloud LoadBalancer nằm ở phía client được tích hợp

Spring Cloud LoadBalancer thực hiện việc chọn đích ở trong tiến trình của client sử dụng nó. Khi `order-api` dùng HTTP client đã tích hợp LoadBalancer, việc chọn instance diễn ra trong `order-api`.

```text
JVM order-api
  HTTP client đã tích hợp LoadBalancer
                 |
                 v
       nguồn danh sách instance
                 |
                 v
         chọn một đích gọi
                 |
                 v
      catalog-api hoặc Service của nó
```

Nguồn instance và loại địa chỉ đích phụ thuộc cách tích hợp. Một chế độ có thể chọn endpoint cụ thể; chế độ khác có thể hướng tới Service. Cần xác định cấu hình thực tế trước khi kết luận đường gọi có đi qua Service hay không.

Một dịch vụ cung cấp danh sách instance không đồng nghĩa dịch vụ đó chuyển tiếp mọi yêu cầu HTTP nghiệp vụ. Tương tự, có discovery chưa đủ để khẳng định một HTTP client thông thường đã sử dụng Spring Cloud LoadBalancer.

Nếu LoadBalancer nằm trong một gateway thì quyết định chọn đích được thực hiện ở tiến trình gateway. Các ứng dụng nằm sau gateway không tự có LoadBalancer chỉ vì gateway đã sử dụng nó.

### 2.4. Endpoint sức khỏe và thành phần nhận refresh

Endpoint sức khỏe của Spring Boot Actuator thường chạy trong tiến trình ứng dụng. Nó có thể dùng cổng quản trị khác với cổng nghiệp vụ, nhưng việc tách cổng không tự tạo một Deployment hay một server JVM khác.

Nếu ứng dụng nhận tín hiệu refresh qua endpoint quản trị, phần tiếp nhận và xử lý tín hiệu cũng nằm trong ứng dụng. Configuration Watcher triển khai riêng chỉ có thể gửi tín hiệu hoặc phối hợp theo cơ chế đã cấu hình; nó không trực tiếp thay đổi bộ nhớ của JVM từ bên ngoài.

Việc nhận được tín hiệu không bảo đảm mọi đối tượng trong ứng dụng tự đổi giá trị. Bean, connection pool hoặc HTTP client đã khởi tạo cần hỗ trợ cơ chế cập nhật thích hợp, hoặc phải được tạo lại theo thiết kế.

## 3. Những thành phần có thể triển khai riêng

### 3.1. Kubernetes Discovery Server và HTTP DiscoveryClient

Một lựa chọn kiến trúc của Spring Cloud Kubernetes là triển khai Discovery Server riêng, rồi để ứng dụng sử dụng HTTP DiscoveryClient phù hợp để truy vấn thông tin khám phá qua server đó. Khả năng và cách cấu hình cụ thể phải khớp với dòng phiên bản được chọn.

```text
order-api: HTTP DiscoveryClient ----+
                                   |
payment-api: HTTP DiscoveryClient --+--> Discovery Server
                                              |
                                              v
                                    Kubernetes API server
```

Discovery Server tập trung phần truy cập Kubernetes API phục vụ khám phá. Ứng dụng sử dụng server vẫn có mã client trong JVM của mình; triển khai server không loại bỏ thành phần client.

Trong mô hình này, quyền đọc các tài nguyên Kubernetes phục vụ discovery có thể tập trung ở ServiceAccount của server. Các ứng dụng chỉ truy vấn server có thể không cần quyền đọc Kubernetes API cho chức năng khám phá đó. Tuy nhiên, nếu ứng dụng đồng thời đọc ConfigMap qua API, nó vẫn cần quyền riêng cho phần cấu hình.

Đổi lại, server trở thành một phụ thuộc vận hành dùng chung. Cần xem xét khả năng sẵn sàng, dung lượng xử lý, timeout từ client, cách bảo vệ truy cập và hành vi khi server gián đoạn. Nếu có cache, hiệu lực và độ cũ của dữ liệu phụ thuộc implementation; không nên mặc định client sẽ tiếp tục hoạt động vô hạn khi server mất kết nối.

Sau khi lấy được địa chỉ đích, yêu cầu nghiệp vụ thường đi từ client tới đích đã chọn theo cách tích hợp. Discovery Server không tự trở thành reverse proxy của các yêu cầu đó. Muốn có gateway hoặc proxy cần một thành phần đảm nhiệm trách nhiệm tương ứng.

### 3.2. Configuration Watcher

Configuration Watcher có thể được triển khai thành ứng dụng riêng để theo dõi thay đổi của những ConfigMap hoặc Secret được chọn và kích hoạt luồng cập nhật cấu hình cho ứng dụng đích.

Một mô hình khái niệm:

```text
Kubernetes API server
        |
        | sự kiện thay đổi tài nguyên cấu hình
        v
Configuration Watcher
        |
        | tín hiệu theo cơ chế đã cấu hình
        v
Thành phần nhận refresh trong order-api
        |
        v
Nạp lại cấu hình và cập nhật những thành phần hỗ trợ
```

Tùy dòng phiên bản và lựa chọn tích hợp, cơ chế thông báo có thể liên quan đến HTTP hoặc hạ tầng sự kiện như Spring Cloud Bus. Phải chọn cơ chế được hỗ trợ, triển khai đủ các thành phần tương ứng và cấu hình bảo vệ đường truyền. Không nên giả định mọi cơ chế đều được bật sẵn.

Watcher cần biết phạm vi theo dõi và cách xác định ứng dụng đích. Nếu cơ chế định vị ứng dụng yêu cầu khám phá Service hoặc tài nguyên khác, quyền của Watcher phải bao gồm đúng những thao tác cần thiết, ngoài quyền theo dõi cấu hình.

Ba điều kiện phải được kiểm tra riêng:

1. Watcher có nhận được thay đổi của tài nguyên mong muốn không?
2. Tín hiệu có tới được các replica cần cập nhật không?
3. Mỗi replica có thực sự sử dụng giá trị mới không?

Có Pod Watcher ở trạng thái Running mới chỉ chứng minh tiến trình đã được chạy. Nó chưa chứng minh luồng cập nhật đã hoàn thành, cũng chưa chứng minh tất cả replica có cùng cấu hình.

### 3.3. Thành phần của cluster và thành phần dùng chung khác

API server, hệ thống DNS của cluster, scheduler và các controller của Kubernetes là hạ tầng Kubernetes. Chúng không phải các thư viện được đóng gói vào ứng dụng và cũng không phải các Deployment Spring Cloud Kubernetes bắt buộc phải tạo thêm khi cài starter.

Nếu chọn dùng message broker cho luồng thông báo cấu hình, broker là một phụ thuộc triển khai riêng nữa. Nếu chọn dùng gateway, gateway cũng có vòng đời và đường kết nối riêng. Chỉ đưa những thành phần đó vào mô hình khi có chức năng thực sự sử dụng chúng.

## 4. Ba mô hình triển khai để lựa chọn

### 4.1. Mô hình A: dùng cơ chế nền tảng của Kubernetes

Trong mô hình tối giản, ứng dụng gọi dịch vụ qua DNS, nhận cấu hình qua biến môi trường hoặc file, và dùng probe để báo tình trạng phục vụ.

```text
order-api ---- DNS/Service ----> catalog-api
    ^
    |
biến môi trường hoặc file từ ConfigMap/Secret
```

Mô hình này có thể không cần thành phần Spring Cloud Kubernetes nào. Đây là điểm xuất phát hợp lý nếu không có yêu cầu về discovery abstraction, truy cập cấu hình qua API hoặc refresh động.

Khi cấu hình được cấp bằng biến môi trường, thay đổi ConfigMap hay Secret không tự đổi môi trường của container đang chạy. Một rollout có kiểm soát có thể là phương thức áp dụng cấu hình mới. Với file được mount, vẫn cần xác định cơ chế cập nhật file và cách ứng dụng đọc lại; không được coi việc file thay đổi là bằng chứng bean đã thay đổi.

### 4.2. Mô hình B: tích hợp trực tiếp trong từng ứng dụng

Ứng dụng có DiscoveryClient truy cập API và có thể có cả thành phần cấu hình đọc qua API. Những thành phần này chạy cùng mã nghiệp vụ.

```text
order-api [discovery + config] -----+
                                   +--> Kubernetes API server
payment-api [discovery + config] ---+
```

Ưu điểm là không cần thêm một Discovery Server chỉ để cung cấp dữ liệu discovery. Tuy nhiên, mỗi ứng dụng có thể phát sinh kết nối, cache, watcher nội bộ và yêu cầu RBAC riêng, tùy cách client hoạt động.

Khi số replica tăng, cần quan sát ảnh hưởng đến API server và tài nguyên trong ứng dụng. Không nên đồng nhất “không thêm workload riêng” với “không có chi phí vận hành”.

### 4.3. Mô hình C: tách một số chức năng dùng chung

Ứng dụng dùng HTTP DiscoveryClient để truy vấn Discovery Server; Configuration Watcher được triển khai riêng nếu cần cơ chế phát hiện thay đổi tập trung.

```text
order-api ---- truy vấn khám phá ----> Discovery Server ----> API server
    ^
    |
    +---- tín hiệu cập nhật ---------- Configuration Watcher <-- API server
```

Đây không phải một gói bắt buộc gồm hai server. Có thể chỉ dùng Watcher mà vẫn khám phá trực tiếp; cũng có thể chỉ dùng Discovery Server và áp dụng cấu hình mới bằng rollout.

Tập trung quyền đọc discovery tại server không tự tập trung mọi quyền đọc cấu hình. Ứng dụng nhận refresh rồi tự đọc ConfigMap qua API vẫn cần danh tính và quyền cho thao tác đọc đó.

Mô hình này làm rõ sự tách biệt trách nhiệm, nhưng thêm phụ thuộc mạng và vận hành. Nếu một server phục vụ nhiều ứng dụng hoặc namespace, phạm vi ảnh hưởng khi cấu hình sai hoặc gián đoạn cũng rộng hơn.

## 5. Ví dụ tối giản: không cần thêm server Spring Cloud Kubernetes

Giả sử `order-api` chỉ cần một giới hạn nghiệp vụ từ ConfigMap và gọi `catalog-api` qua DNS. Đoạn manifest dưới minh họa ServiceAccount, ConfigMap và Deployment trong namespace `shop` đã tồn tại.

Ứng dụng được giả định đã bind thuộc tính `order.max-items`, dùng biến môi trường `ORDER_MAXITEMS`, và bật các endpoint probe phù hợp của Spring Boot Actuator trên cổng `8080`. Image là địa chỉ minh họa, cần thay bằng image ứng dụng thực tế trước khi triển khai.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-api
  namespace: shop
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
  namespace: shop
data:
  max-items: "20"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      serviceAccountName: order-api
      automountServiceAccountToken: false
      containers:
        - name: order-api
          image: registry.example.com/shop/order-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: ORDER_MAXITEMS
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: max-items
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
```

Trong ví dụ này, tiến trình không cần token ServiceAccount để tự gọi Kubernetes API. Kubernetes cung cấp giá trị môi trường khi container được tạo. Việc không mount token vẫn cho phép ứng dụng dùng DNS và gọi dịch vụ mạng, với điều kiện chính sách mạng và dịch vụ đích cho phép.

Manifest chưa định nghĩa Service công bố `order-api`; nó chỉ minh họa nơi chạy cấu hình và probe. Service `catalog-api` cũng được giả định đã có. Các chu kỳ probe là giá trị minh họa, cần điều chỉnh theo thời gian khởi động và đặc tính ứng dụng.

Nếu chuyển sang đọc cấu hình hoặc discovery trực tiếp qua Kubernetes API, cần thiết kế lại phần xác thực và RBAC. Với cách xác thực in-cluster dùng token, cấu hình không mount token ở trên sẽ không đáp ứng yêu cầu đó.

Việc bổ sung Configuration Watcher cũng chưa làm biến môi trường này tự cập nhật. Phải thay cách nạp và áp dụng cấu hình theo cơ chế refresh tương thích, hoặc tiếp tục dùng rollout để tạo Pod mới.

## 6. RBAC phải đi theo thành phần thực sự gọi API

Cách bố trí tiến trình quyết định vị trí của quyền truy cập. Một dependency trong JVM thường hoạt động với danh tính của Pod ứng dụng; một server riêng thường hoạt động với ServiceAccount của server.

| Thành phần | Có thể cần gọi Kubernetes API? | Quyền cần xem xét |
| --- | --- | --- |
| Ứng dụng chỉ gọi Service qua DNS | Không cần cho riêng việc gọi DNS/HTTP | Không cấp quyền đọc tài nguyên chỉ vì có cuộc gọi dịch vụ |
| DiscoveryClient truy cập API trực tiếp | Có | Tài nguyên discovery, namespace và thao tác theo implementation |
| HTTP DiscoveryClient chỉ gọi Discovery Server | Không cần cho riêng luồng truy vấn server | Quyền truy cập server qua mạng và cơ chế xác thực của server |
| Discovery Server | Có | Đọc thông tin discovery trong phạm vi được phục vụ |
| Thành phần cấu hình đọc ConfigMap/Secret qua API | Có | Nguồn cấu hình thực sự sử dụng; chỉ đọc Secret khi cần |
| Configuration Watcher | Có | Theo dõi nguồn cấu hình và quyền bổ sung để định vị đích nếu cách tích hợp yêu cầu |

Các thao tác `get`, `list` và `watch` không thay thế cho nhau. Đọc một ConfigMap theo tên bằng `get` khác với khởi tạo một cơ chế liệt kê và theo dõi nhiều tài nguyên. Một Role chỉ có `get` không tự đủ cho một Watcher cần `list/watch`.

Role trong namespace phù hợp cho phạm vi một namespace; nếu có nhu cầu nhiều namespace, cần thiết kế binding và phạm vi quyền tương ứng. Không nên bắt đầu bằng quyền quản trị cluster chỉ để tránh lỗi `403 Forbidden`.

Với server phục vụ nhiều ứng dụng, RBAC của server chỉ kiểm soát server truy cập API được đến đâu. Nó không tự định nghĩa ứng dụng nào được xem dữ liệu do server trả về. Cần xem xét thêm xác thực, phân quyền ở lớp server và giới hạn truy cập mạng theo kiến trúc thực tế.

Nếu nhiều container cùng nằm trong một Pod, chúng không tự có các ServiceAccount Kubernetes độc lập. Vì vậy, đưa một thành phần vào sidecar chưa chắc tạo được ranh giới danh tính mong muốn. Deployment riêng với ServiceAccount riêng thường làm ranh giới đó rõ ràng hơn.

## 7. Cập nhật cấu hình là một chuỗi trách nhiệm

Xét yêu cầu tăng giới hạn đơn hàng từ `20` lên `30` mà không dừng toàn hệ thống. Cần lập bản đồ trách nhiệm trước khi chọn Watcher:

| Bước | Thành phần chịu trách nhiệm | Bằng chứng cần có |
| --- | --- | --- |
| Lưu giá trị mới | Kubernetes lưu ConfigMap được cập nhật | Tài nguyên đã mang giá trị mới |
| Phát hiện thay đổi | Watcher riêng hoặc cơ chế theo dõi đã chọn | Sự kiện thay đổi được xử lý |
| Xác định và thông báo đích | Thành phần thông báo theo cấu hình | Đúng ứng dụng và replica được nhận tín hiệu |
| Nạp lại nguồn cấu hình | Thành phần bên trong ứng dụng | Giá trị mới xuất hiện ở nguồn cấu hình đang dùng |
| Áp dụng vào hành vi | Bean hoặc tài nguyên có hỗ trợ cập nhật | Yêu cầu nghiệp vụ thực sự dùng giới hạn mới |

Nếu ứng dụng chỉ đọc biến môi trường tại khởi động, chuỗi này không thể hoàn tất bằng một tín hiệu refresh đơn thuần. Nếu một đối tượng giữ bản sao giá trị cũ, việc cập nhật `Environment` cũng chưa đủ để thay đổi đối tượng đó.

Cần dự tính trường hợp hai replica nhận cập nhật lệch thời điểm. Với cấu hình yêu cầu tính nhất quán chặt giữa nhiều dịch vụ, phải thiết kế cách chuyển đổi an toàn thay vì mặc định các tiến trình đổi trạng thái đồng thời.

Khi bật endpoint refresh hoặc một đường nhận sự kiện quản trị, chỉ cho các thành phần được phép sử dụng. Bảo vệ endpoint và tránh log giá trị Secret là một phần trực tiếp của thiết kế luồng cấu hình.

## 8. Sức khỏe Pod và lỗi của phụ thuộc dùng chung

Tách Deployment giúp quan sát và khởi động lại từng thành phần, nhưng không tự loại bỏ phụ thuộc giữa chúng. Cần phân biệt tiến trình còn sống, ứng dụng sẵn sàng phục vụ và chức năng tích hợp đang hoạt động đúng.

| Tình huống | Nơi kiểm tra trước | Cách diễn giải |
| --- | --- | --- |
| Discovery trực tiếp nhận `403` | Danh tính và RBAC của Pod ứng dụng | Ứng dụng đang bị từ chối ở luồng API trực tiếp |
| Ứng dụng không gọi được Discovery Server | DNS, Service, endpoint, mạng, xác thực và sức khỏe server | Luồng client–server bị gián đoạn, chưa chứng minh RBAC của ứng dụng sai |
| Discovery Server nhận `403` từ API server | ServiceAccount và RBAC của Discovery Server | Cần sửa quyền ở thành phần thực sự gọi API |
| Watcher Running nhưng cấu hình không đổi | Sự kiện, lựa chọn đích, thông báo và cơ chế áp dụng trong ứng dụng | Trạng thái Pod chưa xác nhận luồng refresh thành công |
| ConfigMap đã đổi nhưng biến môi trường giữ giá trị cũ | Cách cấp cấu hình và thời điểm tạo container | Cần tạo lại Pod hoặc chuyển sang cơ chế cập nhật phù hợp |
| Một server dùng chung ngừng phục vụ | Khả năng sẵn sàng và hành vi timeout/cache của client | Có thể ảnh hưởng nhiều ứng dụng cùng phụ thuộc |

Readiness dùng để biểu thị khả năng nhận lưu lượng; liveness dùng để phát hiện trạng thái cần khởi động lại; startup probe hỗ trợ giai đoạn khởi động. Không nên gắn liveness của mọi ứng dụng với sự tồn tại tức thời của một server discovery dùng chung, vì một sự cố ở server có thể gây chuỗi khởi động lại không giải quyết được nguyên nhân.

Một client đang có dữ liệu khám phá được lưu tạm có thể còn phục vụ được trong một số tình huống, nhưng điều đó phải được xác định từ implementation và cấu hình. Thiết kế timeout, retry và giới hạn tải vẫn là trách nhiệm của ứng dụng và các thành phần liên quan.

Không nên tự tăng số replica của Watcher rồi kết luận đã có cơ chế xử lý sự kiện đúng một lần. Khả năng phối hợp, thông báo trùng và cách ứng dụng xử lý refresh phải phù hợp với mô hình triển khai được hỗ trợ.

## 9. Chọn thành phần theo nhu cầu

Trước mỗi quyết định thêm dependency hoặc Deployment, hãy mô tả nhu cầu bằng hành vi cụ thể.

- Nếu chỉ cần gọi một Service đã biết tên, bắt đầu với DNS và Service.
- Nếu cần abstraction khám phá trong Spring Cloud, chọn implementation DiscoveryClient thích hợp và quyết định nơi truy cập Kubernetes API.
- Nếu muốn tập trung phần đọc dữ liệu discovery, cân nhắc Discovery Server cùng HTTP client tương ứng; đồng thời thiết kế khả năng sẵn sàng và kiểm soát truy cập server.
- Nếu chỉ cần cấu hình lúc khởi động, biến môi trường hoặc file cùng rollout có thể đã đủ.
- Nếu cần thay đổi cấu hình trong lúc chạy, xác định nguồn dữ liệu, thành phần phát hiện, cơ chế thông báo và thành phần áp dụng trước khi thêm Configuration Watcher.
- Nếu cần chọn instance ở phía client, tích hợp Spring Cloud LoadBalancer tại chính client thực hiện cuộc gọi.
- Nếu cần thay thế Pod lỗi hoặc duy trì replica, cấu hình Kubernetes workload và probe; đây không phải chức năng của Discovery Server hay Watcher.

Tên dependency, image server, thuộc tính cấu hình và khả năng tích hợp thay đổi theo tổ hợp Spring Boot, Spring Cloud và Spring Cloud Kubernetes. Chốt tổ hợp tương thích trước khi chuyển bản đồ kiến trúc này thành cấu hình triển khai chi tiết.

## 10. Tự kiểm tra

1. Trong hệ thống của bạn, mã nào chạy trong JVM nghiệp vụ và workload nào có tiến trình riêng?
2. Thành phần nào thực sự mở kết nối đến Kubernetes API, và nó dùng ServiceAccount nào?
3. Nếu chuyển từ discovery trực tiếp sang HTTP DiscoveryClient, những quyền nào của ứng dụng có thể bỏ và những quyền cấu hình nào vẫn cần giữ?
4. Sau khi triển khai Watcher, ứng dụng còn phải có những khả năng nào để nhận và áp dụng cấu hình mới?
5. Khi Discovery Server không hoạt động, cuộc gọi nào bị ảnh hưởng trước: truy vấn danh sách instance hay mọi yêu cầu nghiệp vụ? Cấu hình cache và đường gọi có làm thay đổi câu trả lời không?
6. Endpoint Actuator ở cổng riêng có đồng nghĩa với một Deployment riêng không?
7. Bằng chứng nào cho thấy cả hai replica đã dùng giá trị ConfigMap mới, thay vì chỉ cho thấy Watcher đang Running?

Một thiết kế rõ ràng luôn chỉ ra được nơi chạy, danh tính, đường kết nối và vòng đời của từng thành phần. Từ đó, có thể chọn tích hợp Spring Cloud Kubernetes đúng mức, cấp RBAC đúng nơi và kiểm chứng việc khám phá, cập nhật cấu hình cùng theo dõi sức khỏe theo từng luồng cụ thể.