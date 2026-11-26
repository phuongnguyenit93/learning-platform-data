# Đặt spring.application.name và tên tài nguyên liên quan

## Mục tiêu bài học

Tên ứng dụng trong Spring Boot là một phần của cấu hình và metadata, còn tên tài nguyên Kubernetes là định danh được API Server, DNS, selector và các thành phần vận hành sử dụng. Hai nhóm tên thường liên quan nhưng không tự động đồng nhất trong mọi tình huống.

Bài thuộc chương **Thiết lập dự án** của module **SPRING_CLOUD_KUBERNETES**. Module học tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành phân quyền RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Đặt spring.application.name ổn định cho ứng dụng Spring Boot.
- Phân biệt application name, Service name, Deployment name, ConfigMap name và Secret name.
- Thiết kế quy ước tên dùng được trong DNS, label, discovery và log.
- Tránh để tên hiển thị, tên artifact và tên tài nguyên Kubernetes phụ thuộc lẫn nhau một cách khó kiểm soát.
- Truy vết từ một tên service logic đến Pod, cấu hình và quyền RBAC liên quan.

## 1. Vì sao tên ứng dụng quan trọng?

Một hệ thống Spring chạy trên Kubernetes có thể sử dụng cùng lúc nhiều loại định danh:

| Định danh | Nơi sử dụng | Ví dụ |
| --- | --- | --- |
| spring.application.name | Cấu hình và metadata ở cấp Spring | order-service |
| Tên artifact | Build và image | order-service.jar |
| Image name | Registry và Deployment | registry.example/order-service |
| Deployment name | Kubernetes controller | order-service |
| Service name | DNS và điểm truy cập nội bộ | order-service |
| ConfigMap name | Nguồn cấu hình Kubernetes | order-service-config |
| Secret name | Nguồn dữ liệu nhạy cảm | order-service-secret |
| Label app | Selector và quan sát | order-service |
| Tên container | Pod spec và logs | app |

Các tên này có thể giống nhau để dễ vận hành, nhưng chúng có ý nghĩa khác nhau. spring.application.name là tên logic của ứng dụng trong hệ sinh thái Spring. Service name là tên DNS của một resource Kubernetes. ConfigMap name là tên một object chứa cấu hình. Không nên cho rằng đổi một tên sẽ tự động đổi tất cả tên còn lại.

Một quy ước tên tốt giúp trả lời nhanh:

    request đến service nào
        → Service chọn Pod nào
        → Pod chạy image nào
        → Spring application name là gì
        → Pod đọc ConfigMap và Secret nào
        → ServiceAccount nào được dùng

## 2. Đặt spring.application.name

### 2.1. Ý nghĩa ở cấp Spring

Có thể đặt tên trong file cấu hình:

    spring:
      application:
        name: order-service

Hoặc dùng biến môi trường:

    SPRING_APPLICATION_NAME=order-service

Tên này thường được sử dụng trong metadata, log, tracing, các abstraction discovery hoặc các thành phần Spring Cloud cần định danh ứng dụng. Nó cũng giúp nhóm vận hành phân biệt các instance cùng chạy một workload.

Tên nên ổn định qua các lần restart và rollout. Nếu tên thay đổi theo Pod name hoặc image tag, việc tra cứu log, cấu hình và discovery sẽ trở nên khó dự đoán.

### 2.2. Tên logic và tên hiển thị

Tên ứng dụng không nhất thiết phải là tên sản phẩm hiển thị cho người dùng. Ví dụ:

- Tên sản phẩm: Quản lý đơn hàng.
- Tên domain: Order Management.
- spring.application.name: order-service.
- Tên Service: order-service.

Tên logic nên ngắn, rõ, ổn định và phù hợp với các quy tắc tên của nền tảng mà nó đi qua. Mô tả dài, ký tự có dấu hoặc tên marketing nên đặt ở label, annotation, tài liệu hoặc dashboard, không dùng làm service ID.

### 2.3. Tránh tên phụ thuộc môi trường

Không nên đổi spring.application.name thành order-service-dev, order-service-staging hoặc order-service-prod nếu ứng dụng vẫn là cùng một service logic. Môi trường nên được biểu diễn bằng namespace, cluster, profile, label hoặc metadata riêng.

Tên phụ thuộc môi trường có thể làm:

- discovery client tìm sai service ID;
- dashboard gom log thành nhiều ứng dụng giả;
- ConfigMap và Secret phải nhân bản theo quy tắc không nhất quán;
- Spring Cloud LoadBalancer không tìm thấy instance do tên logic thay đổi;
- watcher định tuyến thông báo đến sai nhóm ứng dụng.

Có thể dùng hậu tố môi trường trong tên resource nếu tổ chức yêu cầu cô lập tuyệt đối, nhưng cần quyết định rõ tên logic nào được dùng trong code và tên resource nào được dùng trong cluster.

## 3. Quy ước tên Kubernetes

### 3.1. Tên resource và giới hạn cú pháp

Tên Kubernetes thường đi qua quy tắc DNS hoặc DNS label. Vì vậy, quy ước an toàn thường dùng:

- chữ thường;
- chữ số;
- dấu gạch ngang;
- bắt đầu và kết thúc bằng chữ hoặc số;
- độ dài nằm trong giới hạn của loại resource;
- không dùng dấu cách, dấu gạch dưới hoặc ký tự có dấu.

Ví dụ hợp lệ về mặt quy ước:

    order-service
    order-service-config
    order-service-secret

Ví dụ dễ gây vấn đề:

    Order_Service
    order_service
    Đơn hàng
    order.service

Các quy tắc chính xác có thể khác theo loại resource và API version. Khi thiết kế tên dùng cho Service, DNS và selector, hãy chọn tập ký tự bảo thủ nhất để có thể tái sử dụng ở nhiều nơi.

### 3.2. Tên Service

Service name là điểm truy cập ổn định trong namespace. Nếu Service tên order-service thuộc namespace team-a, client trong cùng namespace có thể dùng tên logic tương ứng:

    http://order-service

Client khác namespace có thể dùng:

    http://order-service.team-a

Tên Service cần phản ánh service mà client gọi, không phải Pod cụ thể. Không đặt Service theo hash rollout hoặc tên node.

### 3.3. Tên Deployment

Deployment name định danh controller quản lý rollout. Có thể đặt giống Service để dễ đọc:

    Deployment: order-service
    Service: order-service

Tuy nhiên, hai resource vẫn độc lập. Một Deployment có thể được đặt tên order-service nhưng Service lại tên order-api nếu đó là hợp đồng DNS đã được chọn. Khi dùng hai tên khác nhau, phải ghi rõ mapping trong tài liệu và label.

### 3.4. Tên ConfigMap và Secret

ConfigMap và Secret thường có hậu tố mô tả vai trò:

    order-service-config
    order-service-secret
    order-service-tls

Hậu tố giúp người đọc phân biệt resource khi xem namespace. Không đặt Secret chỉ là order-service nếu namespace có nhiều loại credential và không có quy ước bổ sung.

Tên resource không bảo vệ dữ liệu. order-service-secret vẫn cần RBAC, cơ chế lưu trữ an toàn, audit và quy trình xoay vòng credential.

## 4. Giữ tên nhất quán bằng mapping rõ ràng

### 4.1. Một mapping tối thiểu

Với ứng dụng order-service, có thể lập bảng:

| Khái niệm | Giá trị | Vai trò |
| --- | --- | --- |
| Spring application name | order-service | service ID và metadata Spring |
| Deployment | order-service | rollout và replica |
| Service | order-service | DNS nội bộ |
| ConfigMap | order-service-config | cấu hình không nhạy cảm |
| Secret | order-service-secret | dữ liệu nhạy cảm |
| Pod label app | order-service | selector và truy vấn |
| Container | app | tên container trong Pod |
| ServiceAccount | order-service | danh tính workload |

Mapping này không bắt buộc mọi dự án phải dùng cùng một tên, nhưng cần có chủ ý. Nếu tên khác nhau, hãy ghi lý do và cách liên kết.

### 4.2. Tên logic, tên resource và tên instance

Ba cấp tên cần phân biệt:

    application name: order-service
        → resource name: order-service
            → instance: order-service-7d8f9d7c9f-x2k4m

Instance name có thể thay đổi khi Pod được tạo lại. Application name và Service name nên ổn định hơn. Không đưa instance name vào spring.application.name.

### 4.3. Tên của môi trường

Namespace thường là nơi biểu diễn môi trường hoặc tenant:

    order-service trong namespace dev
    order-service trong namespace staging
    order-service trong namespace production

Ba Service có cùng tên nhưng thuộc namespace khác nhau vẫn là ba DNS name khác nhau. Điều này cho phép giữ service ID nhất quán trong ứng dụng và cô lập resource theo namespace.

## 5. Đặt tên trong một project Spring Boot

### 5.1. Cấu hình cơ bản

Ví dụ application.yaml:

    spring:
      application:
        name: order-service
      profiles:
        active: default

Tên ứng dụng không nên lấy mặc định từ tên thư mục local. Tên thư mục hoặc tên module build có thể thay đổi vì lý do tổ chức code, trong khi service ID là hợp đồng runtime.

### 5.2. Biến môi trường trong Deployment

Một Pod template có thể đặt tên rõ ràng:

    spec:
      containers:
        - name: app
          image: registry.example/order-service:1.0.0
          env:
            - name: SPRING_APPLICATION_NAME
              value: order-service

Nếu tên đã được đóng gói trong application.yaml, việc lặp lại qua environment variable có thể tạo hai nguồn cấu hình. Chỉ lặp lại khi muốn cho môi trường ghi đè có chủ ý và đã xác định thứ tự ưu tiên.

Không nên tạo tên động từ Pod name trừ khi có yêu cầu đặc biệt. Pod name hữu ích cho instance metadata, nhưng không phải application identity ổn định.

### 5.3. Kiểm tra tên hiệu lực

Sau khi Pod chạy, có thể kiểm tra:

- Pod spec có env SPRING_APPLICATION_NAME không;
- log khởi động có hiển thị application name an toàn không;
- endpoint actuator được bảo vệ có trả metadata phù hợp không;
- discovery hoặc load balancer dùng service ID nào;
- cấu hình watcher định tuyến theo tên nào.

Kubernetes không tự chứng minh giá trị property bên trong JVM. Manifest chỉ chứng minh nguồn cấu hình được nối đến Pod. Ứng dụng cần log hoặc metric an toàn để xác nhận giá trị hiệu lực.

## 6. Đặt tên trong Deployment và Service

Manifest minh họa:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: order-service
      namespace: team-a
      labels:
        app.kubernetes.io/name: order-service
        app.kubernetes.io/component: api
    spec:
      replicas: 2
      selector:
        matchLabels:
          app.kubernetes.io/name: order-service
      template:
        metadata:
          labels:
            app.kubernetes.io/name: order-service
            app.kubernetes.io/component: api
        spec:
          containers:
            - name: app
              image: registry.example/order-service:1.0.0
              ports:
                - name: http
                  containerPort: 8080

    ---

    apiVersion: v1
    kind: Service
    metadata:
      name: order-service
      namespace: team-a
      labels:
        app.kubernetes.io/name: order-service
    spec:
      selector:
        app.kubernetes.io/name: order-service
      ports:
        - name: http
          port: 80
          targetPort: http

Điểm quan trọng:

1. Deployment selector phải khớp label của Pod template.
2. Service selector phải khớp label của Pod template.
3. Service port 80 được chuyển đến port container có tên http.
4. Service name là DNS endpoint, còn Deployment name là controller.
5. Label app.kubernetes.io/name có thể được dùng để quan sát nhất quán.

Không dùng selector theo version nếu Service phải nhận traffic từ cả phiên bản trong rollout, trừ khi chiến lược routing chủ ý yêu cầu như vậy.

## 7. Labels, annotations và application name

### 7.1. Labels để chọn và nhóm

Labels nên dùng cho các thuộc tính cần truy vấn hoặc selector:

    app.kubernetes.io/name: order-service
    app.kubernetes.io/instance: order-service-production
    app.kubernetes.io/component: api
    app.kubernetes.io/part-of: commerce
    app.kubernetes.io/managed-by: platform-team

Không đưa dữ liệu dài hoặc thay đổi liên tục vào label. Label có thể được dùng trong index, selector và dashboard nên cần ổn định.

### 7.2. Annotations để mô tả hoặc điều khiển

Annotations phù hợp với metadata không dùng để chọn backend, chẳng hạn:

    metadata:
      annotations:
        owner.example/team: commerce
        owner.example/runbook: order-service

Tên application có thể được lặp lại ở label hoặc annotation để công cụ quan sát đọc dễ hơn. Việc lặp lại cần dùng cùng một giá trị, nếu không sẽ tạo ba nguồn sự thật.

### 7.3. Tên display và tên máy

Một dashboard có thể hiển thị tên thân thiện “Order API”. Kubernetes resource và spring.application.name nên giữ tên máy “order-service”. Mapping giữa hai tên nên nằm trong label, annotation hoặc catalog dịch vụ.

## 8. Tên liên quan đến ConfigMap và Secret

### 8.1. ConfigMap theo ứng dụng

Một quy ước đơn giản:

    order-service-config

Khi ứng dụng có nhiều nhóm cấu hình, có thể tách:

    order-service-app-config
    order-service-observability-config
    order-service-feature-config

Không tách ConfigMap theo mọi property nhỏ nếu điều đó làm việc theo dõi phiên bản và RBAC trở nên quá phức tạp. Mỗi nhóm nên có lý do vận hành rõ.

### 8.2. Secret theo mục đích

Secret nên nói rõ mục đích mà không tiết lộ giá trị:

    order-service-database
    order-service-payment
    order-service-tls

Một Secret chứa nhiều credential không liên quan có thể làm quyền đọc quá rộng. Một Secret cho mọi thứ có vẻ đơn giản nhưng khó xoay vòng và khó giới hạn RBAC.

### 8.3. Nối tên qua envFrom hoặc volume

Ví dụ tham chiếu một ConfigMap:

    envFrom:
      - configMapRef:
          name: order-service-config

Ví dụ tham chiếu Secret:

    envFrom:
      - secretRef:
          name: order-service-database

Nếu dùng envFrom, nhiều key có thể đi vào environment cùng lúc. Cần kiểm soát collision với property khác. Nếu chỉ cần vài key, tham chiếu từng key giúp hợp đồng rõ hơn:

    env:
      - name: DB_HOST
        valueFrom:
          secretKeyRef:
            name: order-service-database
            key: host

Tên ConfigMap hoặc Secret đổi mà Deployment chưa đổi reference sẽ làm Pod mới không nhận được nguồn cũ. Vì vậy, đổi tên resource cần đi cùng thay đổi manifest và kiểm tra rollout.

## 9. Tên cho DiscoveryClient và Spring Cloud LoadBalancer

### 9.1. Service ID

Khi code dùng discovery hoặc load balancer, tên service logic thường là một chuỗi như order-service hoặc inventory. Chuỗi này cần khớp với tên mà discovery provider trả về hoặc mapping đã được cấu hình.

Ví dụ khái niệm:

    inventory service ID
        → discovery provider tìm instance
        → Spring Cloud LoadBalancer chọn instance
        → HTTP client gửi request

Không nên dùng URL đầy đủ làm service ID nếu abstraction đang chờ tên logic. Ngược lại, nếu client dùng DNS Service thông thường, URL phải phản ánh Service name và namespace.

### 9.2. Gọi bằng DNS hay service ID

| Cách gọi | Chuỗi sử dụng | Nguồn phân giải |
| --- | --- | --- |
| HTTP client thông thường | http://inventory | DNS và Service Kubernetes |
| Client tích hợp load balancer | http://inventory | Discovery và LoadBalancer theo cấu hình |
| Gọi khác namespace | http://inventory.team-a | DNS Kubernetes theo namespace |

Cùng chuỗi inventory có thể được xử lý khác nhau tùy client. Khi đổi từ HTTP client thường sang client có LoadBalancer, cần kiểm tra lại dependency, discovery provider, timeout và log đích.

### 9.3. Tên không đồng nhất là lỗi khó thấy

Ví dụ:

- spring.application.name là order-api;
- Deployment là order-service;
- Service là order;
- ConfigMap là order-config;
- code gọi service ID order-service.

Không có tên nào chắc chắn sai riêng lẻ, nhưng mapping thiếu rõ ràng sẽ gây lỗi khi tra cứu, log và cấu hình. Hãy lập bảng mapping và dùng test smoke để chứng minh đường nối.

## 10. Tên cho Configuration Watcher

Configuration Watcher cần biết tài nguyên nào liên quan ứng dụng nào. Tên ứng dụng và tên ConfigMap nên có quan hệ ổn định, nhưng watcher không tự suy ra mọi mapping chỉ từ hậu tố.

Thiết kế cần xác định:

- watcher theo dõi ConfigMap hoặc Secret nào;
- tài nguyên thuộc namespace nào;
- ứng dụng nhận thông báo được định danh bằng tên nào;
- các replica có dùng chung application name không;
- endpoint refresh hoặc kênh thông báo trỏ đến đâu;
- khi đổi tên ConfigMap, watcher và Deployment được cập nhật theo thứ tự nào.

Một quy ước có thể là:

    spring.application.name = order-service
    ConfigMap = order-service-config
    Secret = order-service-secret

Quy ước này làm người đọc đoán được quan hệ, nhưng vẫn cần cấu hình watcher rõ ràng. Hậu tố config không phải một giao thức tự động.

## 11. Namespace và tên đầy đủ

### 11.1. Cùng tên ở namespace khác nhau

Kubernetes cho phép cùng một tên resource trong namespace khác nhau:

    order-service/team-a
    order-service/team-b

DNS Service có namespace trong tên đầy đủ:

    order-service.team-a.svc.cluster.local

Ứng dụng không nên ghi cứng tên đầy đủ nếu cluster domain hoặc namespace có thể khác giữa môi trường. Có thể đưa namespace vào cấu hình khi thật sự cần gọi cross-namespace.

### 11.2. Tên resource không thay thế quyền

Biết đúng tên ConfigMap không cho phép Pod đọc nó. RBAC vẫn quyết định ServiceAccount được get, list hoặc watch resource nào. Tương tự, biết tên Service không bảo đảm NetworkPolicy cho phép đường kết nối.

Khi chẩn đoán, tách ba câu hỏi:

1. Resource có tồn tại với tên và namespace đó không?
2. Client có phân giải hoặc truy cập đúng resource không?
3. Danh tính của client có quyền và mạng phù hợp không?

## 12. Quy tắc đặt tên nên thống nhất từ đầu

Một quy ước thực dụng cho service Spring:

| Mục | Quy tắc đề xuất |
| --- | --- |
| spring.application.name | chữ thường, gạch ngang, tên service logic ổn định |
| Deployment | thường trùng service logic để dễ truy vết |
| Service | trùng tên endpoint logic nếu không có mapping đặc biệt |
| ConfigMap | service logic + hậu tố config |
| Secret | service logic + mục đích secret |
| Pod label | app.kubernetes.io/name trùng application name |
| Container | tên vai trò như app, proxy, metrics |
| Namespace | môi trường hoặc boundary do tổ chức quy định |
| Image | registry + service logic + version hoặc digest |

Quy tắc này không phải chuẩn duy nhất. Điều quan trọng là tên phải:

- ổn định;
- không phụ thuộc instance;
- dùng được trong cú pháp Kubernetes;
- dễ truy vết từ log đến resource;
- không che giấu phạm vi bảo mật;
- có owner và tài liệu mapping.

## 13. Một manifest hoàn chỉnh hơn

Ví dụ dưới đây minh họa cách giữ tên nhất quán:

    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: order-service-config
      namespace: team-a
      labels:
        app.kubernetes.io/name: order-service
    data:
      application.yaml: |
        spring:
          application:
            name: order-service
        orders:
          max-items: 20

    ---

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: order-service
      namespace: team-a
      labels:
        app.kubernetes.io/name: order-service
    spec:
      replicas: 2
      selector:
        matchLabels:
          app.kubernetes.io/name: order-service
      template:
        metadata:
          labels:
            app.kubernetes.io/name: order-service
        spec:
          containers:
            - name: app
              image: registry.example/order-service:1.0.0
              env:
                - name: SPRING_CONFIG_ADDITIONAL_LOCATION
                  value: file:/etc/order-service/
              volumeMounts:
                - name: application-config
                  mountPath: /etc/order-service
                  readOnly: true
          volumes:
            - name: application-config
              configMap:
                name: order-service-config

    ---

    apiVersion: v1
    kind: Service
    metadata:
      name: order-service
      namespace: team-a
    spec:
      selector:
        app.kubernetes.io/name: order-service
      ports:
        - name: http
          port: 80
          targetPort: 8080

Manifest này thể hiện mapping trực tiếp:

- application name là order-service;
- ConfigMap name là order-service-config;
- Deployment và Service cùng tên logic;
- label selector dùng application name;
- ConfigMap được mount vào container;
- Spring được chỉ dẫn thêm location để đọc file.

Đây vẫn là ví dụ khung. Cần kiểm tra cách Spring Boot version đang dùng xử lý file location, profile, thứ tự nguồn cấu hình và cập nhật file. Không nên xem việc mount ConfigMap là bằng chứng rằng mọi bean đã reload.

## 14. Đổi tên an toàn

Đổi tên resource là thay đổi hợp đồng, không chỉ là sửa một dòng:

    tên cũ
      → manifest tham chiếu
      → code gọi service
      → DNS
      → RBAC hoặc watcher
      → dashboard và runbook

Trước khi đổi tên:

1. Liệt kê nơi dùng tên cũ trong phạm vi project và manifest đã được cấp.
2. Xác định client nào gọi Service bằng DNS hoặc service ID.
3. Kiểm tra ConfigMap, Secret và watcher tham chiếu tên nào.
4. Quyết định có cần giữ alias hoặc Service chuyển tiếp không.
5. Triển khai theo thứ tự để không tạo khoảng trống endpoint.
6. Kiểm tra discovery, request, log và rollback.

Nếu đổi Service name trong một hệ thống đang có client gọi DNS cũ, việc xóa Service cũ trước khi client được cập nhật sẽ gây gián đoạn. Nếu chỉ muốn đổi tên hiển thị, nên dùng label hoặc annotation thay vì đổi service ID.

## 15. Quan sát tên hiệu lực

Khi một request không đến được service, hãy truy vết theo chuỗi:

    tên trong code
        → cấu hình HTTP client
        → service ID hoặc DNS
        → Service name và namespace
        → selector
        → Pod label
        → spring.application.name trong process

Các câu hỏi thực tế:

- Code đang gọi inventory hay inventory.team-a?
- Client có dùng LoadBalancer hay DNS thường?
- Service có đúng tên và namespace không?
- Selector có chọn Pod của workload đó không?
- Pod có label đúng không?
- spring.application.name trong log có phải order-service không?
- ConfigMap và Secret có hậu tố đúng không?

Tên có thể được xem trong manifest và output vận hành. Không lấy Pod name để thay thế application name.

## 16. Tên và log, metric, trace

Một request qua nhiều replica cần metadata nhất quán:

- application name;
- namespace;
- deployment hoặc workload;
- Pod name;
- container name;
- version hoặc image digest;
- trace ID hoặc correlation ID.

Application name nên là trường ổn định để dashboard gom nhóm. Pod name nên là trường instance để điều tra một bản sao. Version nên biểu diễn release, không trộn vào application name.

Ví dụ metadata log có thể có dạng:

    application=order-service
    namespace=team-a
    pod=order-service-7d8f9d7c9f-x2k4m
    version=1.0.0

Không đưa Secret, token hoặc toàn bộ environment vào log chỉ để kiểm tra tên.

## 17. Những hiểu nhầm thường gặp

**“spring.application.name tự tạo Kubernetes Service.”** Đây là cấu hình Spring, không tự tạo resource Kubernetes. Service phải được tạo bởi manifest, chart hoặc công cụ triển khai.

**“Tên Deployment và Service bắt buộc giống nhau.”** Không bắt buộc, nhưng trùng tên có thể dễ truy vết. Nếu khác, cần mapping rõ.

**“Đổi tên Pod sẽ đổi tên ứng dụng.”** Pod name là instance do controller tạo. Application identity nên ổn định độc lập với Pod.

**“ConfigMap order-service-config chắc chắn được ứng dụng order-service dùng.”** Cần kiểm tra Pod spec, volume hoặc config client. Tên tương tự chỉ tạo quy ước, không tạo liên kết tự động.

**“Dùng tên có môi trường trong spring.application.name sẽ dễ quản lý hơn.”** Điều đó có thể làm discovery, log và dashboard tách một service thành nhiều identity. Namespace hoặc metadata thường phù hợp hơn để biểu diễn môi trường.

**“Secret name đã đủ bảo vệ credential.”** Tên chỉ là định danh. Bảo vệ phụ thuộc RBAC, storage, audit, rotation và log hygiene.

**“LoadBalancer luôn tìm Service name bằng DNS.”** Cách phân giải phụ thuộc client, discovery provider và cấu hình. Cần xác định đường đi thực tế.

**“Chỉ cần đổi application.yaml.”** Nếu tên được tham chiếu ở Service, ConfigMap, watcher, code client hoặc dashboard, phải cập nhật toàn bộ mapping liên quan.

## 18. Checklist thiết lập tên

### Ứng dụng Spring

- [ ] spring.application.name được đặt rõ và ổn định.
- [ ] Tên dùng chữ thường và gạch ngang.
- [ ] Tên không phụ thuộc Pod, node hoặc image tag.
- [ ] Nguồn cấu hình cho application name không bị ghi đè ngoài ý muốn.
- [ ] Log hoặc metric có application name an toàn.

### Kubernetes

- [ ] Deployment name và Service name có mapping rõ.
- [ ] ConfigMap name có hậu tố mô tả mục đích.
- [ ] Secret name có mục đích rõ và không lộ dữ liệu.
- [ ] Pod labels khớp Deployment selector.
- [ ] Service selector khớp Pod labels.
- [ ] Namespace được ghi trong manifest và tài liệu.

### Spring Cloud Kubernetes

- [ ] Service ID trong discovery khớp mapping đã chọn.
- [ ] Client biết đang gọi DNS hay LoadBalancer.
- [ ] Config client tham chiếu đúng ConfigMap hoặc Secret.
- [ ] Watcher theo dõi đúng resource và ứng dụng đích.
- [ ] RBAC dùng đúng ServiceAccount cho các tên resource cần đọc.

### Vận hành

- [ ] Dashboard gom theo application name và tách theo namespace, version.
- [ ] Runbook có mapping từ tên logic đến resource.
- [ ] Quy trình đổi tên có kiểm tra client và rollback.
- [ ] Không log giá trị Secret khi chẩn đoán.

## 19. Tự kiểm tra mức độ hiểu

**Câu 1: spring.application.name có phải tên bắt buộc của Kubernetes Service không?**

Không. Đây là tên logic ở cấp Spring. Có thể đặt Service cùng tên để dễ truy vết, nhưng Kubernetes Service phải được khai báo và có selector riêng.

**Câu 2: Vì sao không nên dùng Pod name làm spring.application.name?**

Vì Pod name thay đổi khi replica bị thay thế hoặc rollout. Application name cần ổn định để discovery, log, metric và cấu hình nhận diện cùng một service.

**Câu 3: Service name và Deployment name khác nhau có được không?**

Được. Hai resource có trách nhiệm khác nhau. Cần ghi rõ Service nào trỏ đến label của Deployment nào và client dùng tên nào để gọi.

**Câu 4: Đổi ConfigMap name cần kiểm tra những gì?**

Kiểm tra volume, env, config client, watcher, RBAC, rollout và mọi runbook hoặc automation tham chiếu tên cũ. Tên mới không tự thay thế reference cũ.

**Câu 5: Làm sao biểu diễn môi trường mà không làm đổi application identity?**

Dùng namespace, cluster, profile, label, annotation hoặc metadata deployment. Giữ application name ổn định nếu vẫn là cùng service logic.

**Câu 6: Vì sao cần phân biệt service ID với DNS name?**

Vì client thường và client có discovery/load balancing có thể xử lý cùng một chuỗi theo cách khác nhau. Phân biệt hai khái niệm giúp chọn đúng cấu hình, dependency và cách kiểm tra.

## Kết luận

spring.application.name là điểm neo của identity ở cấp Spring, còn tên Deployment, Service, ConfigMap, Secret và label tạo thành mạng lưới định danh ở cấp Kubernetes. Các tên có thể được thiết kế nhất quán như order-service, nhưng sự giống nhau chỉ có giá trị khi mapping giữa chúng được khai báo và kiểm chứng.

Hãy chọn tên logic ổn định, dùng namespace để phân biệt môi trường, dùng hậu tố để mô tả loại cấu hình, giữ selector khớp label và kiểm tra đường đi từ service ID đến Pod. Khi tên được tổ chức rõ ràng, DiscoveryClient, Spring Cloud LoadBalancer, ConfigMap, Secret và Configuration Watcher sẽ dễ cấu hình, quan sát và vận hành hơn.
