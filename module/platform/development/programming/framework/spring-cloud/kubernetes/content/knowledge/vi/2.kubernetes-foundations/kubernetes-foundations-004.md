# Service, selector và tập Pod phục vụ yêu cầu

Trong Kubernetes, Pod là nơi chạy container nhưng không phải là địa chỉ ổn định để ứng dụng khác gọi trực tiếp. Pod có thể bị thay thế, chuyển node, đổi địa chỉ IP hoặc tạm thời không sẵn sàng. Service tạo một điểm truy cập ổn định và dùng selector để xác định những Pod nào có thể nhận lưu lượng.

Đây là nền tảng quan trọng khi triển khai ứng dụng Spring với Kubernetes. order-api có thể gọi catalog-api bằng tên Service thay vì biết IP của từng Pod. Khi cần discovery ở tầng Spring Cloud, thông tin Service và tập endpoint có thể trở thành nguồn cho DiscoveryClient hoặc Spring Cloud LoadBalancer. Tuy vậy, gọi qua DNS của Service và truy vấn danh sách instance là hai cách dùng khác nhau, cần chọn theo nhu cầu thực tế.

Bài học thuộc chương **Nền tảng Kubernetes** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là hiểu luồng từ Service đến selector, EndpointSlice và Pod; biết vì sao readiness ảnh hưởng đến tập endpoint; và phân biệt khi nào chỉ cần DNS/Service, khi nào cần tích hợp discovery trong ứng dụng Spring.

## 1. Bốn đối tượng cần phân biệt

Một yêu cầu đi tới ứng dụng thường liên quan đến bốn lớp:

| Đối tượng | Vai trò | Tính ổn định |
| --- | --- | --- |
| Pod | Chạy một hoặc nhiều container của ứng dụng | Thấp; IP và vòng đời có thể thay đổi |
| Service | Điểm truy cập ổn định cho một nhóm Pod | Ổn định trong phạm vi cluster theo tên và địa chỉ Service |
| Selector | Điều kiện nhãn để Service chọn Pod | Do manifest khai báo; thay đổi selector có thể đổi tập đích |
| EndpointSlice | Danh sách các địa chỉ đích được quản lý cho Service | Thay đổi theo Pod, readiness và trạng thái endpoint |

Luồng khái niệm:

~~~text
HTTP client trong order-api
          |
          v
DNS catalog-api trong Kubernetes
          |
          v
Service catalog-api
          |
          | selector: app=catalog-api
          v
EndpointSlice
          |
          v
Pod catalog-api đủ điều kiện nhận lưu lượng
~~~

Service không chứa mã nghiệp vụ và không chạy container thay cho Pod. Nó là một abstraction mạng cùng cơ chế chọn và phân phối lưu lượng. Controller của Kubernetes cập nhật EndpointSlice khi các Pod phù hợp được tạo, xóa, đổi nhãn hoặc thay đổi trạng thái sẵn sàng.

## 2. Pod và nhãn: dữ liệu để Service chọn đích

Selector của Service thường khớp với nhãn trên metadata.labels của Pod hoặc nhãn trong spec.template.metadata.labels của Deployment. Selector không khớp với tên Deployment, tên container hay tên image.

Ví dụ Deployment tạo hai Pod có nhãn app: catalog-api và version: stable:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
        version: stable
    spec:
      containers:
        - name: catalog-api
          image: registry.example.com/shop/catalog-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
~~~

spec.selector.matchLabels của Deployment dùng để xác định Pod thuộc Deployment. Trong ví dụ này, nhãn app: catalog-api cũng được Service sử dụng để chọn Pod. Hai selector có liên quan đến cùng Pod nhưng thuộc hai đối tượng khác nhau: Deployment dùng selector để quản lý replica, còn Service dùng selector để chọn đích mạng.

Không nên đổi nhãn của Pod đang chạy bằng cách chỉ sửa thủ công rồi kỳ vọng Deployment và Service vẫn có cùng ý nghĩa. Nếu nhãn không còn khớp Service, Pod có thể bị loại khỏi tập endpoint; nếu thay đổi làm vi phạm selector của Deployment, việc quản lý rollout cũng có thể trở nên khó hiểu. Hãy thay đổi nhãn qua manifest và kiểm tra quan hệ giữa các selector.

## 3. Service selector tạo tập endpoint như thế nào?

Service có thể khai báo selector đơn giản:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: shop
spec:
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Trong ví dụ này:

- selector.app=catalog-api chọn các Pod có nhãn tương ứng trong namespace shop.
- port: 80 là cổng mà Service công bố cho client.
- targetPort: http trỏ tới cổng có tên http trong container đích, được khai báo là 8080 ở Pod template.
- Client gọi Service ở cổng 80; lưu lượng được chuyển tới cổng 8080 của một Pod phù hợp.

Có thể dùng số thay cho tên ở targetPort, nhưng tên cổng làm rõ ý nghĩa và tránh lặp số trong nhiều manifest. Tên cổng phải tồn tại trên Pod được chọn; nếu mapping sai, Service có thể tồn tại nhưng yêu cầu vẫn thất bại.

Mỗi Service có selector được controller sử dụng để xây dựng các EndpointSlice tương ứng. EndpointSlice biểu diễn các địa chỉ và trạng thái endpoint hiệu quả hơn mô hình Endpoints cũ khi số lượng đích lớn. Ứng dụng thường không cần tự đọc EndpointSlice chỉ để gọi Service qua DNS; kube-proxy hoặc cơ chế mạng của cluster xử lý phần phân phối lưu lượng.

Nếu Service không có Pod phù hợp, Service vẫn có thể được tạo nhưng không có endpoint phục vụ. DNS có thể vẫn phân giải tên Service, trong khi kết nối tới đó không có backend sẵn sàng. Vì vậy, “tên Service phân giải được” chưa đủ chứng minh ứng dụng đích đang phục vụ.

## 4. Readiness quyết định Pod có nên nhận lưu lượng

Pod có nhãn khớp selector chưa chắc đã sẵn sàng nhận yêu cầu. Readiness probe cho phép ứng dụng báo rằng nó đã khởi tạo đủ để phục vụ. Khi Pod chưa ready, endpoint của nó thường không được dùng cho lưu lượng Service thông thường.

Ví dụ phần container của một ứng dụng Spring Boot:

~~~yaml
containers:
  - name: catalog-api
    image: registry.example.com/shop/catalog-api:1.0.0
    ports:
      - name: http
        containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 5
      failureThreshold: 3
~~~

Endpoint phải được ứng dụng bật và cấu hình đúng. Kubernetes không tự biết /actuator/health/readiness có tồn tại chỉ vì image chứa Spring Boot Actuator. Cổng, đường dẫn, scheme, thời gian chờ và điều kiện sức khỏe phải khớp với ứng dụng.

Cần phân biệt ba trạng thái:

1. Container đang chạy: tiến trình có thể vẫn tồn tại.
2. Pod ready: Pod được xem là có thể nhận lưu lượng theo điều kiện readiness.
3. Ứng dụng xử lý đúng: yêu cầu nghiệp vụ thực tế trả kết quả đúng và trong thời gian chấp nhận được.

Readiness không phải là kiểm tra mọi phụ thuộc theo cách máy móc. Nếu catalog-api mất một chức năng phụ nhưng vẫn có thể phục vụ các API chính, đưa toàn bộ Pod về not ready có thể làm giảm khả năng phục vụ. Ngược lại, nếu ứng dụng chưa kết nối được nguồn dữ liệu bắt buộc, readiness cần phản ánh rằng Pod chưa nên nhận traffic.

livenessProbe phục vụ quyết định khởi động lại container khi container được coi là không còn hoạt động đúng theo tiêu chí liveness. startupProbe dành thời gian cho tiến trình khởi động lâu. Không nên dùng liveness để thay thế readiness, vì một phụ thuộc bên ngoài tạm thời lỗi có thể khiến Kubernetes khởi động lại hàng loạt Pod thay vì chỉ tạm thời loại chúng khỏi lưu lượng.

## 5. Port của Service và port của container

Một lỗi cấu hình phổ biến là trộn lẫn ba tên gọi:

| Trường | Nằm ở đâu | Ý nghĩa |
| --- | --- | --- |
| containerPort | Pod template | Cổng mà container dự kiến lắng nghe; chủ yếu mô tả và dùng trong tham chiếu tên cổng |
| targetPort | Service | Cổng trên Pod mà Service chuyển yêu cầu tới |
| port | Service | Cổng Service công bố cho client |

Ví dụ:

~~~yaml
# Pod template
ports:
  - name: http
    containerPort: 8080

# Service
ports:
  - name: http
    port: 80
    targetPort: http
~~~

Client trong cùng namespace gọi http://catalog-api:80. Service chuyển tới cổng có tên http của Pod, tương ứng 8080 trong ví dụ. Client không cần biết cổng container nếu Service đã cung cấp một cổng ổn định.

containerPort không tự mở firewall và không làm tiến trình tự lắng nghe. Ứng dụng vẫn phải bind đúng địa chỉ và cổng bên trong container. NetworkPolicy, firewall của node, CNI hoặc chính sách mạng của môi trường có thể tiếp tục ảnh hưởng đến khả năng kết nối.

Nếu Service có nhiều cổng, mỗi cổng nên có tên duy nhất:

~~~yaml
ports:
  - name: http
    port: 80
    targetPort: http
  - name: management
    port: 8081
    targetPort: management
~~~

Không nên công bố cổng quản trị như Actuator ra phạm vi rộng hơn nhu cầu. Có thể dùng Service riêng, NetworkPolicy và cơ chế xác thực để giới hạn đường truy cập quản trị.

## 6. DNS và phạm vi namespace

Service có tên DNS ổn định trong cluster. Từ Pod cùng namespace, client thường có thể dùng tên ngắn:

~~~text
http://catalog-api:80/products/42
~~~

Từ namespace khác, có thể dùng tên có namespace:

~~~text
http://catalog-api.shop:80/products/42
~~~

Tên đầy đủ thường có dạng:

~~~text
catalog-api.shop.svc.cluster.local
~~~

Hậu tố domain cluster có thể được cấu hình khác, nên ứng dụng không nên hard-code hậu tố nếu môi trường có quy ước riêng. Tên ngắn cũng chỉ có ý nghĩa trong phạm vi DNS search domain của Pod.

DNS giải quyết tên Service, không cung cấp danh sách instance cho mã Java. Nếu ứng dụng chỉ cần gọi một Service ổn định, WebClient, RestClient hoặc HTTP client tương ứng có thể gọi hostname đó mà không cần DiscoveryClient.

Nếu ứng dụng cần truy vấn danh sách instance theo abstraction Spring Cloud, nó có thể dùng DiscoveryClient với implementation phù hợp. Khi đó, ứng dụng có thêm yêu cầu về quyền, cách lấy dữ liệu và cách xử lý dữ liệu thay đổi. Không nên thêm discovery chỉ vì mọi cuộc gọi HTTP trong cluster đều được gọi là “service discovery”.

## 7. ClusterIP, headless Service và khi nào dùng

### 7.1. Service thông thường

Service thông thường thường có địa chỉ ảo trong cluster, thường được gọi là ClusterIP. Client gọi một địa chỉ ổn định; lớp mạng của cluster đưa yêu cầu đến một endpoint phù hợp.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

ClusterIP phù hợp khi client chỉ cần gọi một dịch vụ logic và để Kubernetes xử lý việc phân phối tới các Pod. Đây thường là lựa chọn đầu tiên cho một API nội bộ.

### 7.2. Headless Service

Khai báo clusterIP: None tạo headless Service. Khi đó, DNS không cung cấp cùng một địa chỉ ảo như Service thông thường; DNS có thể trả về các địa chỉ endpoint của Pod theo cơ chế discovery DNS của cluster.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-nodes
  namespace: shop
spec:
  clusterIP: None
  selector:
    app: catalog-node
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

Headless Service hữu ích khi client hoặc hệ thống cần biết từng địa chỉ thành viên, chẳng hạn một số mô hình stateful hoặc giao thức tự quản lý membership. Nó không tự cung cấp cân bằng tải phía client, retry, health policy hay bảo đảm ứng dụng sẽ chọn đúng endpoint.

Không nên dùng headless Service chỉ vì muốn “discovery chi tiết hơn” mà chưa xác định client cần làm gì với danh sách địa chỉ. Với API stateless thông thường, Service có ClusterIP và readiness rõ ràng thường đơn giản hơn.

### 7.3. Service không có selector

Một Service không có selector có thể dùng với EndpointSlice được quản lý thủ công hoặc cơ chế khác để trỏ tới đích bên ngoài cách chọn Pod thông thường. Đây là mô hình nâng cao; nó không tự tạo backend.

Nếu Service không có selector mà không có EndpointSlice phù hợp, client có thể phân giải tên Service nhưng không có nơi nhận lưu lượng. Hãy kiểm tra nguồn endpoint trước khi chẩn đoán lỗi ở ứng dụng.

## 8. Một Service không phải lúc nào cũng là một LoadBalancer bên ngoài

ClusterIP chỉ dành cho truy cập trong cluster. Nếu cần công bố ứng dụng ra ngoài, có thể dùng NodePort, LoadBalancer hoặc Ingress/Gateway tùy nền tảng và kiến trúc. Các cơ chế này mở rộng đường truy cập, nhưng không thay đổi nguyên tắc selector và tập Pod phía sau Service.

- ClusterIP: địa chỉ nội bộ ổn định.
- NodePort: mở một cổng trên node theo cơ chế Kubernetes hỗ trợ.
- LoadBalancer: yêu cầu môi trường cung cấp hoặc tích hợp load balancer bên ngoài.
- Ingress/Gateway: định tuyến HTTP hoặc TCP ở lớp cao hơn tới một hoặc nhiều Service.

Tên LoadBalancer của Kubernetes Service và Spring Cloud LoadBalancer chỉ giống về mục đích tổng quát, không phải cùng một thành phần. Kubernetes Service phân phối lưu lượng trong hạ tầng cluster hoặc tới điểm công bố bên ngoài. Spring Cloud LoadBalancer chọn instance ở phía client khi client được tích hợp với nó.

Cần tránh thiết kế vòng lặp khó quan sát, ví dụ client chọn endpoint bằng LoadBalancer rồi lại đi qua một Service phân phối khác mà không có lý do. Hãy xác định rõ mỗi lớp đang chọn gì và lớp nào chịu trách nhiệm timeout, retry, circuit breaker cùng quan sát lỗi.

## 9. Service và Spring Cloud Kubernetes

Có ba cách ứng dụng Spring có thể liên hệ với Service:

| Nhu cầu | Cách phù hợp | Quyền Kubernetes API cho ứng dụng |
| --- | --- | --- |
| Gọi API ổn định bằng tên | DNS + Service + HTTP client | Thường không cần quyền đọc Service chỉ cho việc gọi mạng |
| Lấy danh sách instance qua Spring Cloud abstraction | DiscoveryClient và implementation phù hợp | Có thể cần quyền đọc tài nguyên discovery |
| Chọn instance ở client | Spring Cloud LoadBalancer kết hợp nguồn instance | Phụ thuộc nguồn instance và cách tích hợp |

Khi dùng DiscoveryClient truy cập trực tiếp Kubernetes API, mỗi Pod ứng dụng có thể cần ServiceAccount và RBAC riêng. Các thao tác cần thiết có thể gồm get, list hoặc watch trên những tài nguyên cụ thể, tùy implementation và cấu hình. Không nên cấp quyền cluster-admin chỉ để giải quyết một lỗi discovery.

Khi dùng Discovery Server riêng, ứng dụng có thể gọi server qua HTTP thay vì trực tiếp đọc Kubernetes API cho luồng discovery. Khi đó, quyền đọc tài nguyên discovery tập trung hơn ở server, nhưng server trở thành một phụ thuộc vận hành dùng chung. Cách này không tự loại bỏ quyền mà ứng dụng cần cho ConfigMap, Secret hoặc các chức năng Kubernetes API khác.

Nếu selector được cấu hình sai, cả DNS client thông thường và DiscoveryClient có thể cho kết quả gây hiểu nhầm theo những cách khác nhau. Client DNS có thể kết nối tới Service nhưng nhận lỗi vì không có endpoint; DiscoveryClient có thể trả danh sách rỗng hoặc dữ liệu không như mong đợi. Kiểm tra nhãn Pod, selector, EndpointSlice và readiness theo đúng thứ tự sẽ giúp tách lỗi mạng khỏi lỗi ứng dụng.

## 10. Kiểm tra một Service không có backend

Giả sử order-api nhận lỗi timeout khi gọi http://catalog-api.shop:80. Hãy lần theo chuỗi sau:

1. Tên DNS có phân giải được trong Pod order-api không?
2. Service catalog-api có tồn tại trong đúng namespace không?
3. port và targetPort có khớp với cổng ứng dụng không?
4. Selector của Service có khớp nhãn thực tế trên Pod không?
5. EndpointSlice có địa chỉ backend nào không?
6. Pod có ready theo readiness probe không?
7. Ứng dụng trong Pod có lắng nghe đúng địa chỉ và cổng không?
8. NetworkPolicy hoặc cơ chế mạng có chặn namespace hoặc cổng không?
9. Ứng dụng đích có trả lời chậm, đóng kết nối hoặc từ chối yêu cầu không?

Bảng chẩn đoán nhanh:

| Quan sát | Khả năng cần kiểm tra |
| --- | --- |
| DNS không phân giải | Tên, namespace, DNS của cluster hoặc cấu hình resolver |
| Service tồn tại nhưng không có endpoint | Selector, nhãn Pod, namespace, readiness |
| Có endpoint nhưng kết nối bị từ chối | targetPort, tiến trình không lắng nghe, containerPort mô tả sai |
| Kết nối timeout | NetworkPolicy, route mạng, endpoint lỗi, ứng dụng không phản hồi |
| HTTP 404/500 | Yêu cầu đã tới ứng dụng; kiểm tra route và lỗi nghiệp vụ |
| DiscoveryClient trả danh sách rỗng | Phạm vi namespace, RBAC, loại tài nguyên hoặc cache của implementation |

Tên Service phân giải được chỉ xác nhận một phần của đường đi. EndpointSlice có địa chỉ cũng chỉ cho biết có đích được công bố; nó chưa chứng minh ứng dụng xử lý đúng request. Cần quan sát cả probe, log ứng dụng, metric và mã phản hồi.

## 11. Rollout và selector: giữ tập đích an toàn

Khi phát hành phiên bản mới, Deployment thường tạo Pod mới với nhãn tương thích rồi dần giảm Pod cũ. Service tiếp tục dùng selector chung, còn readiness kiểm soát thời điểm Pod mới tham gia nhận lưu lượng.

Một chiến lược có thể dùng nhãn app chung và nhãn version để phân biệt phiên bản:

~~~text
Pod cũ: app=catalog-api, version=stable
Pod mới: app=catalog-api, version=canary
Service chung: app=catalog-api
~~~

Với selector chung app=catalog-api, cả hai nhóm có thể nhận lưu lượng trong giai đoạn chuyển tiếp. Nếu muốn Service canary chỉ chọn một nhóm, cần Service riêng hoặc cơ chế định tuyến hỗ trợ selector/traffic policy tương ứng. Chỉ thêm nhãn version vào Pod không tự tạo tỷ lệ traffic hay phân chia lưu lượng.

Không nên thay selector của Service giữa rollout mà không lập bản đồ tập Pod trước và sau. Một thay đổi selector có thể đột ngột loại toàn bộ Pod khỏi dịch vụ hoặc đưa nhầm workload vào tập đích. Với Deployment, selector bất biến theo các quy tắc của API còn làm cho thay đổi một số trường trở thành thao tác không thể cập nhật trực tiếp.

Readiness giúp tránh gửi request tới Pod mới trước khi ứng dụng sẵn sàng, nhưng không giải quyết migration dữ liệu, tương thích giao thức hoặc request đang chạy trên Pod cũ. Rollout an toàn cần xét toàn bộ vòng đời ứng dụng.

## 12. Cấu hình mẫu cho một ứng dụng Spring nội bộ

Mẫu dưới đây biểu diễn một Service nội bộ cho catalog-api và một phần Deployment. Nó giả định namespace shop đã tồn tại, ứng dụng lắng nghe cổng 8080, và endpoint readiness đã được cấu hình trong Spring Boot.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: catalog-api
          image: registry.example.com/shop/catalog-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
~~~

order-api có thể gọi http://catalog-api hoặc http://catalog-api.shop tùy namespace. Service không cần biết số replica; khi Deployment thay đổi từ ba lên năm Pod, controller cập nhật EndpointSlice theo các Pod phù hợp và ready.

Nếu order-api cần danh sách từng instance để thực hiện logic riêng, hãy ghi rõ lý do đó trong thiết kế rồi chọn discovery abstraction phù hợp. Nếu chỉ cần một API ổn định, hostname của Service giảm số thành phần ứng dụng phải vận hành và giảm quyền Kubernetes API cần cấp.

## 13. Checklist thiết kế

Trước khi đưa Service vào triển khai, hãy kiểm tra:

- Selector của Service khớp đúng nhãn trên Pod template.
- Selector của Deployment và selector của Service được hiểu như hai quan hệ khác nhau.
- port là cổng client gọi, còn targetPort là cổng Pod nhận.
- Tên targetPort có tồn tại trên Pod nếu dùng dạng tên.
- Readiness probe phản ánh khả năng phục vụ thực tế.
- Startup và liveness không gây restart hàng loạt khi phụ thuộc bên ngoài tạm lỗi.
- DNS được gọi với đúng namespace và hậu tố môi trường.
- Loại Service phù hợp với nhu cầu: ClusterIP, headless hoặc loại công bố khác.
- NetworkPolicy và xác thực ứng dụng cho phép đường gọi cần thiết.
- DiscoveryClient hoặc LoadBalancer chỉ được thêm khi có nhu cầu rõ ràng.
- Nếu đọc Kubernetes API, ServiceAccount và RBAC thuộc đúng thành phần thực sự gọi API.
- Có quan sát cho DNS, endpoint, readiness, latency, mã phản hồi và lỗi ứng dụng.

## 14. Tự kiểm tra

1. Vì sao gọi trực tiếp IP của Pod làm client dễ hỏng khi Deployment thay thế Pod?
2. Service selector khớp với nhãn nào trong Pod template của bạn?
3. Khác biệt giữa port, targetPort và containerPort là gì?
4. Vì sao DNS phân giải được nhưng request vẫn timeout hoặc không có backend?
5. Readiness thất bại ảnh hưởng đến tập endpoint như thế nào, và khác gì với liveness thất bại?
6. Khi nào headless Service hợp lý hơn Service có ClusterIP?
7. Nếu ứng dụng chỉ gọi catalog-api bằng hostname, vì sao có thể không cần DiscoveryClient?
8. Thành phần nào cần RBAC nếu DiscoveryClient đọc Service và EndpointSlice trực tiếp qua Kubernetes API?
9. Khi rollout có Pod stable và canary, selector của Service đang chọn nhóm nào?
10. Bằng chứng nào cho thấy một Pod vừa được đưa vào EndpointSlice thực sự có thể phục vụ request?

Service là ranh giới giúp ứng dụng gọi một nhóm Pod bằng địa chỉ ổn định, còn selector và readiness quyết định nhóm đó có những Pod nào tại từng thời điểm. Khi nắm rõ ba lớp này, ứng dụng Spring có thể bắt đầu bằng DNS và Service của Kubernetes; chỉ bổ sung DiscoveryClient, Spring Cloud LoadBalancer hoặc các tích hợp khác khi cần hành vi mà Service nền tảng chưa cung cấp.

