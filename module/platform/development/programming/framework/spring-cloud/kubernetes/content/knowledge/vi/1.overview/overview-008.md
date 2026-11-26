# Điều kiện nền tảng trước khi triển khai tích hợp

## Mục tiêu bài học

Trước khi thêm Spring Cloud Kubernetes vào một ứng dụng Spring, cần xác nhận nền tảng chạy ứng dụng, bộ phiên bản, mạng, danh tính, quyền truy cập và cách vận hành đã sẵn sàng. Nếu bỏ qua các điều kiện này, lỗi thường xuất hiện dưới dạng “discovery không thấy service”, “không đọc được ConfigMap”, “refresh không có tác dụng” hoặc “Pod bị restart liên tục”. Những triệu chứng đó có thể đến từ Kubernetes, ứng dụng, dependency hoặc RBAC chứ không nhất thiết do chính thư viện tích hợp.

Bài thuộc chương **Tổng quan** của module **SPRING_CLOUD_KUBERNETES**. Module tập trung vào việc tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn đúng tính năng cần thiết cho triển khai.

Mục tiêu của bài là tạo một cổng kiểm tra trước triển khai. Sau khi hoàn thành, bạn có thể:

- Xác định ứng dụng cần khả năng nào của Spring Cloud Kubernetes và khả năng nào Kubernetes đã cung cấp sẵn.
- Kiểm tra sự tương thích giữa Java, Spring Boot, Spring Cloud và Spring Cloud Kubernetes.
- Chuẩn bị namespace, Service, ServiceAccount và RBAC theo nguyên tắc quyền tối thiểu.
- Phân biệt đường gọi qua DNS của Kubernetes với discovery và load balancing ở phía client.
- Chọn cách đưa ConfigMap và Secret vào ứng dụng, cùng cách xử lý khi cấu hình thay đổi.
- Thiết kế probe, log và kiểm tra vận hành để phát hiện lỗi trước khi đưa traffic thật vào Pod.

## 1. Bắt đầu từ yêu cầu, không bắt đầu từ starter

Spring Cloud Kubernetes không phải điều kiện bắt buộc cho mọi ứng dụng Spring Boot chạy trong Kubernetes. Kubernetes đã có Service, DNS, ConfigMap, Secret, volume và cơ chế probe. Một ứng dụng có thể dùng các khả năng đó mà không gọi Kubernetes API từ trong tiến trình.

Spring Cloud Kubernetes trở nên có ích khi ứng dụng cần mô hình hoặc hành vi ở cấp Spring Cloud, chẳng hạn:

| Nhu cầu | Khả năng nền tảng có thể đáp ứng | Khi nào cân nhắc Spring Cloud Kubernetes |
| --- | --- | --- |
| Gọi một service nội bộ có tên ổn định | Service và DNS của Kubernetes | Mã nguồn đã dùng DiscoveryClient hoặc cần metadata instance |
| Tìm danh sách instance | Endpoint của Kubernetes hoặc cơ chế discovery khác | Ứng dụng cần abstraction discovery của Spring Cloud |
| Đưa cấu hình ngoài image | Biến môi trường, volume, ConfigMap và Secret | Muốn tích hợp nguồn cấu hình Kubernetes vào hệ thống cấu hình Spring |
| Chọn đích gọi ở phía ứng dụng | Service routing của Kubernetes | Cần Spring Cloud LoadBalancer hoặc chính sách chọn đích tại client |
| Nhận biết thay đổi cấu hình | Rollout Deployment | Có thiết kế refresh động và cần Configuration Watcher |
| Kiểm tra Pod | Startup, readiness và liveness probe | Cần health contributor hoặc tín hiệu liên quan đến tích hợp Spring |

Một quyết định tốt phải trả lời được bốn câu hỏi:

1. Ứng dụng cần dữ liệu hoặc hành vi nào mà Kubernetes cơ bản chưa cung cấp đủ?
2. Thành phần Spring Cloud Kubernetes nào đáp ứng nhu cầu đó?
3. Thành phần này cần đọc tài nguyên Kubernetes nào, bằng quyền nào?
4. Khi Kubernetes API, nguồn cấu hình hoặc service phụ thuộc tạm thời không sẵn sàng, ứng dụng sẽ làm gì?

Ví dụ, một ứng dụng chỉ gọi service “inventory” trong cùng namespace có thể bắt đầu bằng địa chỉ DNS:

    http://inventory/api/stocks/SKU-001

Nếu yêu cầu chỉ là gọi một điểm truy cập ổn định, thêm discovery client sẽ làm tăng dependency, cấu hình và quyền API mà chưa chắc tạo ra giá trị tương ứng. Nếu ứng dụng hiện có thư viện dùng DiscoveryClient để lấy instance hoặc metadata, tích hợp discovery lại có lý do rõ ràng hơn.

## 2. Mô hình các lớp cần kiểm tra

Trước triển khai, hãy kiểm tra theo thứ tự từ lớp thấp lên lớp cao:

    Java runtime
        ↓
    Spring Boot và dependency management
        ↓
    Container image và cấu hình tiến trình
        ↓
    Namespace, Service, ConfigMap, Secret
        ↓
    ServiceAccount và RBAC
        ↓
    Mạng, DNS, NetworkPolicy
        ↓
    Discovery, LoadBalancer, Configuration Watcher
        ↓
    Probe, log, metric và quy trình rollout

Lỗi ở lớp dưới có thể làm lớp trên trông như bị hỏng. Nếu container không khởi động, chưa thể kết luận discovery sai. Nếu ServiceAccount không có quyền đọc tài nguyên, việc chỉnh thuộc tính discovery sẽ không giải quyết được lỗi 403. Nếu ứng dụng vẫn giữ giá trị cấu hình trong một bean không hỗ trợ cập nhật, watcher có thể đã gửi thông báo thành công nhưng hành vi vẫn không đổi.

## 3. Kiểm tra bộ phiên bản và dependency

### 3.1. Các thành phần phải được chọn như một bộ

Ứng dụng cần xác định rõ:

- Phiên bản Java runtime dùng khi build và khi chạy.
- Phiên bản Spring Boot.
- Phiên bản Spring Cloud tương thích với Spring Boot.
- Phiên bản các module Spring Cloud Kubernetes.
- Phiên bản Kubernetes client hoặc implementation được module tích hợp sử dụng.
- Phiên bản thư viện HTTP client, actuator và các module liên quan.

Không nên ghép ngẫu nhiên từng starter theo phiên bản mới nhất riêng lẻ. Spring Cloud thường dùng BOM để quản lý một bộ phiên bản tương thích. Dependency management cần được xác định trước khi cấu hình tính năng, vì tên starter, thuộc tính và hành vi có thể thay đổi giữa các thế hệ release.

Một bảng tương thích nội bộ nên có ít nhất các cột sau:

| Thành phần | Giá trị được chọn | Câu hỏi kiểm tra |
| --- | --- | --- |
| Java | Ví dụ: JDK đã được tổ chức chuẩn hóa | Runtime trong image có đúng với runtime khi build không? |
| Spring Boot | Release của ứng dụng | Có thuộc phạm vi tương thích của Spring Cloud đã chọn không? |
| Spring Cloud | Release train phù hợp | BOM có quản lý các module cần dùng không? |
| Spring Cloud Kubernetes | Release của module | Discovery, config và watcher có cùng dòng tương thích không? |
| Kubernetes client | Implementation do module dùng | Có xung đột dependency hoặc nhiều client cùng vai trò không? |
| Actuator | Phiên bản đi cùng Spring Boot | Endpoint health và probe đã được bật đúng chưa? |

### 3.2. Kiểm tra dependency thực tế trong image

Có ba điều cần phân biệt:

1. Dependency có trong file build.
2. Dependency được đóng gói vào artifact hoặc image.
3. Tính năng tương ứng thực sự được bật bằng cấu hình.

Có dependency không có nghĩa là ứng dụng đã dùng tính năng. Ngược lại, bật thuộc tính mà thiếu module phù hợp có thể khiến ứng dụng không khởi động hoặc bỏ qua cấu hình.

Trước khi triển khai, cần kiểm tra log khởi động để xác định:

- Ứng dụng nhận đúng profile và nguồn cấu hình.
- Bean discovery, load balancer hoặc config client được tạo khi mong muốn.
- Không có cảnh báo do nhiều implementation cùng cung cấp một abstraction.
- Không có lỗi thiếu class, xung đột bean hoặc thuộc tính không được nhận diện.

Trong môi trường production, nên ghi lại danh sách dependency và mã digest của image trong metadata build. Khi có sự cố, đội vận hành cần biết chính xác image nào đang chạy thay vì suy đoán từ tag có thể bị tái sử dụng.

## 4. Kiểm tra cluster và namespace

### 4.1. Namespace là ranh giới vận hành

Namespace quyết định phạm vi tên của Service, ConfigMap, Secret, Role và nhiều tài nguyên khác. Cùng tên “inventory” ở hai namespace có thể là hai service khác nhau. Vì thế, trước khi cấu hình ứng dụng cần xác định:

- Namespace của Deployment.
- Namespace của service mà ứng dụng gọi.
- Namespace của ConfigMap và Secret.
- Việc discovery chỉ trong namespace hiện tại hay cần nhìn sang namespace khác.
- Chính sách mạng giữa các namespace.

Đối với lời gọi nội bộ, tên ngắn thường được phân giải trong namespace hiện tại:

    http://inventory

Khi gọi sang namespace khác, có thể dùng tên có namespace:

    http://inventory.team-a

Tên miền đầy đủ còn phụ thuộc domain cluster. Không nên ghi cứng một domain đầy đủ khi môi trường triển khai có thể thay đổi domain DNS.

### 4.2. Service phải có selector và endpoint

Một Service tồn tại chưa chứng minh nó có thể nhận traffic. Cần kiểm tra:

- Selector của Service có khớp label trên Pod không.
- Pod có ở trạng thái Ready không.
- Service công bố đúng port và targetPort không.
- Endpoint hoặc EndpointSlice có chứa địa chỉ backend không.
- Ứng dụng gọi đúng protocol và path không.

Luồng kiểm tra có thể mô tả như sau:

    client trong Pod
        → tên DNS của Service
        → Service port
        → targetPort của Pod
        → container đang lắng nghe
        → endpoint nghiệp vụ

Nếu readiness probe thất bại, backend có thể bị loại khỏi đường nhận traffic dù container vẫn đang chạy. Khi chẩn đoán, cần xem cả trạng thái Pod và danh sách endpoint, không chỉ kiểm tra DNS.

### 4.3. Cluster API và quyền truy cập

Những tính năng đọc discovery, ConfigMap, Secret hoặc theo dõi thay đổi qua Kubernetes API cần đường kết nối đến API Server. Cần xác định:

- Pod có thể phân giải và kết nối đến tên Kubernetes API không.
- NetworkPolicy hoặc firewall có chặn egress không.
- TLS và CA được cung cấp cho client có phù hợp không.
- ServiceAccount token được mount hoặc cung cấp theo chính sách cluster không.
- API Server có trả lỗi 401, 403, timeout hay lỗi TLS không.

Không nên biến mọi lỗi kết nối API thành liveness failure. API Server là một dependency bên ngoài; việc khởi động lại toàn bộ Pod có thể làm sự cố lan rộng mà không khôi phục được quyền hoặc mạng.

## 5. Kiểm tra container image và tiến trình ứng dụng

Một image sẵn sàng triển khai phải có:

- Java runtime đúng kiến trúc và phiên bản.
- Artifact đúng commit hoặc build version.
- Port ứng dụng lắng nghe đúng với containerPort dự kiến.
- Múi giờ, encoding và locale phù hợp với quy ước của hệ thống.
- Không chứa Secret cố định trong image hoặc trong layer build.
- Cấu hình mặc định an toàn khi chạy ngoài môi trường phát triển.
- Lệnh khởi động có exit code rõ ràng khi cấu hình bắt buộc bị thiếu.

Đừng chỉ kiểm tra rằng container “đã chạy”. Tiến trình có thể vẫn sống nhưng không lắng nghe cổng, không kết nối được dependency hoặc đang dùng nhầm profile. Cần kiểm tra log khởi động, cổng lắng nghe, endpoint health và một request có ý nghĩa.

Ví dụ, một phần cấu hình Deployment có thể chỉ rõ tên cổng để probe và Service cùng tham chiếu:

    ports:
      - name: http
        containerPort: 8080

    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http

Đây chỉ là phần minh họa. Endpoint phải được bật ở ứng dụng và không nên công khai thông tin nhạy cảm qua health endpoint.

## 6. Chuẩn bị ConfigMap và Secret

### 6.1. Xác định nguồn cấu hình

Có ba cách phổ biến để đưa dữ liệu Kubernetes vào ứng dụng:

| Cách đưa dữ liệu | Ứng dụng nhận như thế nào | Hành vi khi ConfigMap thay đổi |
| --- | --- | --- |
| Biến môi trường | Đọc qua property của tiến trình | Thường cần tạo Pod mới để tiến trình nhận giá trị mới |
| Volume mount | Đọc file được mount | Nội dung file có thể được đồng bộ theo cơ chế volume; ứng dụng phải đọc lại |
| Kubernetes API qua thành phần tích hợp | Client Spring đọc tài nguyên | Phụ thuộc cấu hình, RBAC, cơ chế refresh và phiên bản module |

Trước khi triển khai, phải chọn một nguồn làm hợp đồng rõ ràng. Việc vừa đưa một khóa vào biến môi trường, vừa mount file, vừa đọc cùng khóa từ API tạo ra nhiều nguồn cạnh tranh và khó xác định giá trị hiệu lực.

Một ConfigMap chỉ là dữ liệu được lưu trong Kubernetes. Nó không tự động trở thành property của Spring nếu Deployment và ứng dụng chưa nối tài nguyên đó vào nguồn cấu hình.

### 6.2. Phân loại dữ liệu nhạy cảm

ConfigMap dành cho dữ liệu không nhạy cảm. Secret dành cho dữ liệu cần kiểm soát truy cập chặt hơn, chẳng hạn mật khẩu hoặc token. Tuy nhiên, Secret được biểu diễn bằng Base64 không đồng nghĩa dữ liệu đã được bảo vệ hoàn toàn.

Trước triển khai, cần kiểm tra:

- Secret không bị commit vào mã nguồn hoặc image.
- RBAC chỉ cho phép đúng workload cần đọc.
- Log không in toàn bộ giá trị Secret.
- Endpoint chẩn đoán không trả lại credential.
- Quy trình xoay vòng credential có người sở hữu và thời điểm rõ ràng.
- Ứng dụng phản ứng phù hợp khi Secret hết hạn hoặc không đọc được.

Ví dụ khai báo tên nguồn dữ liệu nên giữ ở cấu hình không nhạy cảm; giá trị Secret vẫn được quản lý riêng:

    env:
      - name: SPRING_PROFILES_ACTIVE
        value: kubernetes
      - name: PAYMENT_TOKEN
        valueFrom:
          secretKeyRef:
            name: order-service-secret
            key: payment-token

Đoạn này chỉ minh họa việc đưa một khóa Secret vào biến môi trường. Nó không thay thế cơ chế quản lý Secret của tổ chức và không quyết định ứng dụng có tự refresh token hay không.

### 6.3. Thứ tự ưu tiên và giá trị bắt buộc

Một property có thể xuất hiện trong file đóng gói, file ngoài image, biến môi trường và nguồn cấu hình Kubernetes. Cần lập bảng cho các property quan trọng:

| Property | Nguồn dự kiến | Bắt buộc? | Khi thiếu hoặc lỗi |
| --- | --- | --- | --- |
| Địa chỉ service nghiệp vụ | Cấu hình triển khai hoặc DNS | Có | Không khởi động hoặc không nhận traffic |
| Mật khẩu database | Secret | Có | Dừng khởi động an toàn |
| Mức log | ConfigMap hoặc mặc định | Không | Dùng giá trị mặc định đã duyệt |
| Cờ tính năng | ConfigMap | Tùy tính năng | Rollout hoặc refresh theo thiết kế |

Không nên dùng giá trị mặc định vô hại cho một property thực ra là bắt buộc. Cách làm đó khiến Pod báo Ready nhưng mọi request nghiệp vụ đều thất bại sau đó.

## 7. Chuẩn bị ServiceAccount và RBAC

### 7.1. Khi nào cần RBAC?

Nếu ứng dụng chỉ gọi Service bằng DNS, nhận cấu hình qua biến môi trường hoặc volume, ứng dụng có thể không cần quyền đọc Kubernetes API. Nếu discovery hoặc configuration client truy vấn API, ServiceAccount cần các quyền tương ứng.

Các thành phần RBAC chính:

- ServiceAccount là danh tính được Pod sử dụng.
- Role mô tả quyền trong một namespace.
- RoleBinding gán Role cho ServiceAccount.
- ClusterRole và ClusterRoleBinding có phạm vi rộng hơn, cần dùng khi thật sự có yêu cầu.

ServiceAccount trong manifest không tự được Pod sử dụng nếu Pod template chưa chỉ rõ tên:

    spec:
      template:
        spec:
          serviceAccountName: order-service

### 7.2. Quyền tối thiểu theo tính năng

Không có một danh sách quyền chung đúng cho mọi phiên bản và mọi implementation. Quyền cần thiết phụ thuộc thành phần được bật, tài nguyên được truy cập và thao tác client thực hiện.

| Tính năng | Tài nguyên có thể cần | Động từ có thể cần |
| --- | --- | --- |
| Đọc ConfigMap theo tên | configmaps | get |
| Tìm nhiều service hoặc instance | services, endpoints hoặc EndpointSlice | get, list, watch tùy implementation |
| Đọc Secret | secrets | get, có thể cần list hoặc watch |
| Theo dõi thay đổi | tài nguyên được theo dõi | get, list, watch tùy cách watcher hoạt động |

Bảng này chỉ là điểm bắt đầu. Cần đối chiếu với tài liệu và hành vi của release đang dùng, sau đó kiểm tra bằng một danh tính cụ thể. Không cấp cluster-admin để giải quyết nhanh lỗi Forbidden.

Ví dụ Role giới hạn đọc một ConfigMap có tên xác định:

    apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    metadata:
      name: order-config-reader
      namespace: team-a
    rules:
      - apiGroups: [""]
        resources: ["configmaps"]
        resourceNames: ["order-service-config"]
        verbs: ["get"]

Role trên không đủ cho mọi discovery client hoặc watcher. Nếu client dùng list/watch để xây dựng cache, quyền get một tài nguyên riêng sẽ không đáp ứng được cách truy vấn đó.

### 7.3. Kiểm tra quyền bằng đúng danh tính

Kiểm tra quyền phải dùng đúng namespace và ServiceAccount của Pod. Một quyền được cấp cho tài khoản khác không giúp ứng dụng đang chạy.

Các câu hỏi cần xác nhận:

- Deployment có thực sự dùng ServiceAccount dự kiến không?
- RoleBinding có trỏ đúng namespace và đúng ServiceAccount không?
- Rule có đúng apiGroup, resource và verb không?
- Client cần đọc Secret nhưng Role chỉ cho ConfigMap hay không?
- Client cần watch nhưng rule chỉ cho get hay không?
- Quyền liên namespace có được cấp rõ ràng và được chấp nhận về bảo mật không?

Kết quả kiểm tra nên được ghi thành bằng chứng vận hành, chẳng hạn “ServiceAccount X được phép get ConfigMap Y trong namespace Z”, thay vì chỉ ghi “RBAC đã bật”.

## 8. Kiểm tra mạng, DNS và NetworkPolicy

### 8.1. Ba đường kết nối khác nhau

Trong một ứng dụng có tích hợp Spring Cloud Kubernetes, ít nhất ba đường kết nối có thể tồn tại:

    order-service → Service inventory → các Pod inventory

    order-service → Kubernetes API Server

    order-service → endpoint nhận thông báo của Configuration Watcher

Mỗi đường có DNS, port, TLS, NetworkPolicy và timeout riêng. Một đường hoạt động không chứng minh hai đường còn lại hoạt động.

Ví dụ, ứng dụng có thể gọi được inventory nhưng không truy cập được API Server. Khi đó lời gọi nghiệp vụ qua Service vẫn chạy, còn discovery hoặc đọc ConfigMap qua API thất bại. Thiết kế cần nêu rõ ứng dụng có được phép tiếp tục phục vụ bằng dữ liệu cache hay phải trở nên Not Ready.

### 8.2. Timeout và retry

Kubernetes API và service nghiệp vụ đều là mạng phân tán. Cần đặt timeout hữu hạn cho client. Retry phải có giới hạn, backoff và cân nhắc tính idempotent của thao tác.

Không nên retry vô hạn khi:

- API Server trả Forbidden do thiếu quyền.
- TLS sai hoặc CA không hợp lệ.
- Property bắt buộc không tồn tại.
- Request nghiệp vụ có tác dụng phụ nhưng không có idempotency key.

Timeout và retry không thay thế việc sửa DNS, port, quyền hoặc NetworkPolicy. Chúng chỉ kiểm soát hành vi khi lỗi tạm thời có thể xảy ra.

## 9. Chuẩn bị DiscoveryClient và Spring Cloud LoadBalancer

### 9.1. DiscoveryClient cần một hợp đồng instance

Trước khi dùng DiscoveryClient, cần xác định:

- Tên service logic mà ứng dụng sẽ tra cứu.
- Instance được lấy từ Service, Endpoint, EndpointSlice hay nguồn khác.
- Metadata nào là bắt buộc.
- Phạm vi namespace.
- Cách xử lý khi danh sách instance rỗng hoặc đã cũ.

Danh sách instance là ảnh chụp tại một thời điểm. Sau khi client nhận được một địa chỉ, Pod có thể bị xóa hoặc trở nên Not Ready. Mã gọi vẫn cần timeout, xử lý lỗi kết nối và chiến lược retry phù hợp.

### 9.2. Load balancing ở đâu?

Kubernetes Service và Spring Cloud LoadBalancer có thể tham gia vào những điểm khác nhau trong đường đi request:

| Cách gọi | Thành phần chọn backend | Hệ quả cần kiểm tra |
| --- | --- | --- |
| HTTP client thường gọi tên Service | DNS và dataplane của Kubernetes | Service selector, port và readiness phải đúng |
| Client dùng tên service logic với LoadBalancer | LoadBalancer chọn từ danh sách instance theo cấu hình | Discovery, cache, timeout và fallback phải đúng |
| Client gọi endpoint cụ thể | Ứng dụng tự chọn địa chỉ | Dễ phụ thuộc vào vòng đời Pod, chỉ dùng khi có lý do rõ |

Không nên khẳng định bật LoadBalancer sẽ luôn gửi request trực tiếp đến Pod. Đích thực tế phụ thuộc discovery provider và cấu hình. Hãy kiểm tra log hoặc metric của client, sau đó kiểm chứng bằng request an toàn.

### 9.3. Điều kiện sẵn sàng cho discovery

Một bài kiểm tra tối thiểu cần chứng minh:

1. Pod có danh tính đúng.
2. Client kết nối được API hoặc nguồn discovery.
3. Quyền đọc đúng tài nguyên.
4. Tên service logic trả về danh sách hợp lệ.
5. Client xử lý được danh sách rỗng.
6. Request có timeout và không làm lộ dữ liệu nhạy cảm trong log.

## 10. Chuẩn bị Configuration Watcher và cập nhật cấu hình

### 10.1. Tách sự kiện thay đổi thành các bước

Việc sửa ConfigMap hoặc Secret chỉ là bước đầu. Một quy trình cập nhật đầy đủ có thể là:

    tài nguyên Kubernetes thay đổi
        → watcher phát hiện thay đổi
        → watcher xác định ứng dụng đích
        → ứng dụng nhận tín hiệu
        → Environment hoặc source được nạp lại
        → bean có thể refresh nhận giá trị mới
        → metric và log xác nhận kết quả

Nếu một bước không được thiết kế, ứng dụng có thể giữ giá trị cũ mà không báo lỗi rõ ràng.

### 10.2. Các điều kiện cần kiểm tra

- Watcher theo dõi đúng namespace và tài nguyên.
- Watcher có quyền list/watch hoặc quyền tương ứng với implementation.
- Ứng dụng đích có endpoint hoặc kênh nhận thông báo đúng.
- Kết nối từ watcher đến ứng dụng được giới hạn và bảo vệ.
- Ứng dụng không dùng một bean bất biến cho giá trị cần refresh động.
- Các replica có thể nhận thông báo hoặc có cơ chế rollout thay thế.
- Thay đổi Secret không bị ghi ra log hoặc event không cần thiết.

Endpoint refresh có thể thay đổi hành vi ứng dụng. Không được mở endpoint này công khai chỉ để kiểm tra nhanh. Hãy dùng NetworkPolicy, authentication, authorization và phạm vi route phù hợp với thiết kế của hệ thống.

### 10.3. Chọn refresh hay rollout

| Loại thay đổi | Cách thường dễ kiểm soát hơn | Lý do |
| --- | --- | --- |
| Cấu hình log hoặc cờ tính năng đã thiết kế để động | Refresh có kiểm chứng | Không cần thay image, thời gian áp dụng ngắn |
| Biến môi trường của tiến trình | Rollout hoặc tạo Pod mới | Process đã nhận giá trị khi khởi động |
| Mật khẩu database | Refresh nếu pool hỗ trợ an toàn, nếu không thì rollout | Kết nối cũ có thể vẫn giữ credential cũ |
| Cấu hình thư viện đọc một lần | Khởi động lại thành phần hoặc rollout | Nạp lại property không tự tái tạo mọi object |
| Thay đổi cần đồng bộ giữa các replica | Rollout có theo dõi | Dễ xác định version và rollback |

Khi cần độ tin cậy cao, rollout có kiểm soát thường dễ quan sát hơn refresh động. Refresh chỉ nên dùng cho property và bean đã được kiểm chứng về vòng đời.

## 11. Thiết kế probe và tín hiệu sức khỏe

### 11.1. Phân biệt startup, readiness và liveness

| Probe | Câu hỏi | Hành động thường gắn với thất bại |
| --- | --- | --- |
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động chưa? | Tạm trì hoãn đánh giá liveness/readiness hoặc khởi động lại theo ngưỡng |
| Readiness | Pod có sẵn sàng nhận traffic không? | Loại Pod khỏi backend phục vụ |
| Liveness | Tiến trình có cần được khởi động lại không? | Restart container |

Readiness phục vụ quyết định định tuyến. Liveness phục vụ quyết định restart. Không dùng liveness để biểu diễn mọi dependency bên ngoài, vì một lỗi API tạm thời có thể tạo vòng restart lớn.

### 11.2. Probe phải phản ánh khả năng phục vụ

Một readiness endpoint có thể kiểm tra database hoặc service phụ thuộc nếu nghiệp vụ thật sự không thể hoạt động khi dependency đó không có. Tuy nhiên, đưa quá nhiều dependency vào readiness có thể làm mọi replica cùng bị loại khi một hệ thống bên ngoài gặp sự cố.

Một liveness endpoint nên kiểm tra tình trạng kẹt hoặc hỏng không thể tự phục hồi của tiến trình. Nếu Kubernetes API tạm thời không truy cập được nhưng ứng dụng vẫn phục vụ request từ dữ liệu đã nạp, không nên tự động làm liveness thất bại chỉ vì API đó.

Ví dụ cấu hình probe minh họa:

    startupProbe:
      httpGet:
        path: /actuator/health
        port: http
      failureThreshold: 30
      periodSeconds: 10

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

Các ngưỡng phải dựa trên thời gian khởi động và hành vi thực tế của ứng dụng. Không sao chép nguyên xi giá trị mẫu vào production.

### 11.3. Health không thay thế kiểm tra nghiệp vụ

Probe trả thành công chỉ chứng minh các kiểm tra được định nghĩa đã đạt. Sau khi Pod Ready, cần thực hiện smoke test an toàn:

- DNS và kết nối đến Service.
- Một endpoint nghiệp vụ không tạo dữ liệu hoặc có dữ liệu test riêng.
- Discovery trả về kết quả mong muốn.
- Cấu hình bắt buộc có giá trị hợp lệ.
- Không có lỗi Forbidden, timeout hoặc TLS trong log.

## 12. Quan sát và kế hoạch xử lý lỗi

Trước triển khai, hãy thống nhất những tín hiệu cần quan sát:

| Tín hiệu | Mục đích |
| --- | --- |
| Mã lỗi Kubernetes API | Phân biệt thiếu quyền, không tìm thấy, timeout và lỗi TLS |
| Thời điểm nạp cấu hình | Biết ứng dụng đã nhận nguồn nào |
| Mã phiên bản cấu hình không nhạy cảm | So sánh các replica mà không log Secret |
| Số instance discovery | Phát hiện cache rỗng hoặc dữ liệu cũ |
| Thời gian và lỗi gọi downstream | Nhận biết timeout hoặc backend không Ready |
| Số lần restart và lý do probe fail | Phân biệt lỗi tiến trình với lỗi dependency |
| Kết quả rollout | Biết phiên bản mới có đạt Ready và có thể rollback không |

Một log tốt không ghi toàn bộ credential. Có thể ghi tên nguồn, trạng thái thành công, namespace, số lượng instance và một checksum hoặc version identifier đã được thiết kế để không tiết lộ dữ liệu.

Bảng xử lý nhanh:

| Triệu chứng | Nhóm nguyên nhân cần kiểm tra đầu tiên |
| --- | --- |
| 403 khi đọc ConfigMap | ServiceAccount, RoleBinding, resource và verb |
| Discovery trả danh sách rỗng | Namespace, tên service, selector, readiness và quyền list/watch |
| Gọi service bị timeout | DNS, port, NetworkPolicy, endpoint và timeout client |
| ConfigMap đã sửa nhưng bean không đổi | Nguồn cấu hình, watcher, tín hiệu refresh và vòng đời bean |
| Pod Ready rồi bị restart | Liveness quá nhạy, startup chậm hoặc tiến trình thực sự lỗi |
| Chỉ một số replica có giá trị mới | Phạm vi thông báo, cache, rollout và thời điểm nạp |

## 13. Trình tự triển khai có thể kiểm soát

Một trình tự hợp lý cho môi trường thử nghiệm là:

1. Chốt bộ phiên bản và image digest.
2. Tạo namespace và các tài nguyên không nhạy cảm.
3. Tạo ServiceAccount, Role và RoleBinding tối thiểu.
4. Kiểm tra Service, selector, port và endpoint.
5. Triển khai ứng dụng với cấu hình tĩnh tối thiểu.
6. Kiểm tra startup, readiness, liveness và log.
7. Bật một tính năng tích hợp duy nhất, chẳng hạn đọc ConfigMap.
8. Kiểm tra quyền, dữ liệu nhận được và hành vi khi API tạm thời lỗi.
9. Thêm discovery hoặc LoadBalancer nếu yêu cầu ứng dụng cần.
10. Thêm watcher và refresh sau khi nguồn cấu hình đã ổn định.
11. Thực hiện thay đổi cấu hình có kiểm soát trên một replica hoặc môi trường test.
12. Kiểm tra tất cả replica, rollback và khả năng phục hồi.

Bật từng khả năng giúp liên kết nguyên nhân với kết quả. Nếu thêm discovery, config, watcher và load balancer cùng lúc, một lỗi khởi động hoặc lỗi request sẽ khó xác định xuất phát từ thành phần nào.

## 14. Checklist trước khi đưa traffic thật

### 14.1. Ứng dụng và dependency

- [ ] Java runtime trong image đúng với runtime đã kiểm tra.
- [ ] Spring Boot, Spring Cloud và Spring Cloud Kubernetes thuộc bộ tương thích.
- [ ] Dependency không có nhiều implementation cạnh tranh cùng vai trò.
- [ ] Image được định danh bằng version và digest.
- [ ] Property bắt buộc có quy tắc fail-fast hoặc fallback đã duyệt.

### 14.2. Kubernetes và mạng

- [ ] Namespace triển khai và namespace của dependency đã xác định.
- [ ] Service có selector, port và endpoint đúng.
- [ ] DNS phân giải được tên Service cần gọi.
- [ ] NetworkPolicy cho phép đúng các đường cần thiết.
- [ ] Pod kết nối được Kubernetes API nếu tính năng cần dùng API.
- [ ] Timeout và retry có giới hạn.

### 14.3. Cấu hình và bảo mật

- [ ] Mỗi property quan trọng có một nguồn chính rõ ràng.
- [ ] ConfigMap không chứa dữ liệu bí mật.
- [ ] Secret không nằm trong source, image hoặc log.
- [ ] ServiceAccount được chỉ định trong Pod template.
- [ ] RoleBinding gán đúng danh tính.
- [ ] Quyền chỉ bao phủ tài nguyên và động từ cần thiết.

### 14.4. Discovery, watcher và vận hành

- [ ] Tên service logic, namespace và nguồn instance đã xác định.
- [ ] Client xử lý danh sách rỗng, instance cũ và timeout.
- [ ] Watcher chỉ theo dõi tài nguyên cần thiết.
- [ ] Kênh thông báo refresh được bảo vệ.
- [ ] Bean cần thay đổi đã được kiểm tra khả năng refresh.
- [ ] Startup, readiness và liveness có mục đích riêng.
- [ ] Có smoke test, metric, log và kế hoạch rollback.

## 15. Tình huống minh họa: order-service và inventory

Giả sử “order-service” cần gọi “inventory”, đọc giới hạn đơn hàng từ ConfigMap và dùng Secret cho token thanh toán.

### Phương án nền tảng tối thiểu

- Gọi “http://inventory” qua Kubernetes Service.
- Đưa giới hạn đơn hàng qua ConfigMap được mount thành file hoặc biến môi trường.
- Đưa token thanh toán qua Secret.
- Dùng rollout khi thay đổi cấu hình.
- Dùng Actuator readiness và liveness cho probe.

Phương án này có thể không cần ứng dụng đọc Kubernetes API. Quyền RBAC của workload có thể được giảm đáng kể.

### Phương án có tích hợp Spring Cloud Kubernetes

- Dùng DiscoveryClient vì mã nguồn cần danh sách instance và metadata.
- Dùng Spring Cloud LoadBalancer để chọn đích theo chính sách phía client.
- Đọc nguồn cấu hình Kubernetes qua cơ chế đã chọn.
- Dùng Configuration Watcher khi cờ tính năng cần cập nhật động.
- Cấp quyền đúng cho discovery, ConfigMap, Secret hoặc watcher.

Phương án này có nhiều khả năng hơn nhưng cũng có nhiều điều kiện hơn. Cần kiểm tra từng đường kết nối và hành vi khi Kubernetes API không sẵn sàng.

### Câu hỏi quyết định

1. Nếu Service và DNS đã đáp ứng việc gọi inventory, metadata instance có thực sự cần không?
2. Nếu token chỉ thay đổi khi rollout, refresh động có làm tăng rủi ro không?
3. Nếu discovery không đọc được API trong 30 giây, order-service nên tiếp tục dùng cache hay chuyển Not Ready?
4. Nếu watcher gửi thông báo nhưng một replica không refresh, hệ thống có phát hiện được sự lệch phiên bản không?
5. Role hiện tại có cấp quyền rộng hơn nhu cầu thực tế không?

Các câu trả lời cần nằm trong thiết kế triển khai, runbook và kiểm tra tự động. Không nên để chúng chỉ tồn tại trong kinh nghiệm của một thành viên.

## 16. Những sai lầm thường gặp

**Thêm mọi starter để “đủ tính năng”.** Dependency nhiều hơn làm tăng bề mặt cấu hình và quyền. Chọn theo yêu cầu đã xác định.

**Dùng IP của Pod trong cấu hình.** Pod có vòng đời thay đổi. Dùng Service hoặc discovery theo đúng nhu cầu.

**Cấp cluster-admin để hết lỗi 403.** Cách này che giấu nguyên nhân và mở rộng phạm vi rủi ro. Xác định chính xác resource và verb cần thiết.

**Xem ConfigMap sửa thành công là ứng dụng đã cập nhật.** Cần chứng minh watcher, source reload, bean refresh và toàn bộ replica đã áp dụng.

**Dùng liveness để kiểm tra mọi dependency.** Lỗi dependency tạm thời có thể gây restart hàng loạt. Phân biệt readiness với liveness.

**Log toàn bộ cấu hình để debug.** Cách này có thể làm lộ Secret. Ghi trạng thái, tên nguồn và version identifier an toàn.

**Chỉ kiểm tra Pod Running.** Running chỉ mô tả container còn chạy. Cần kiểm tra Ready, endpoint, request an toàn và tín hiệu ứng dụng.

**Dựa vào tag image có thể thay đổi.** Dùng version và digest để có khả năng truy vết và rollback.

## 17. Tự kiểm tra mức độ hiểu

**Câu 1: Mọi ứng dụng Spring Boot trong Kubernetes có cần Spring Cloud Kubernetes không?**

Không. Nếu Service, DNS, ConfigMap, Secret, volume và rollout đã đáp ứng yêu cầu, không cần thêm tích hợp chỉ vì ứng dụng chạy trong Kubernetes.

**Câu 2: ServiceAccount có Role đọc ConfigMap là đủ cho mọi discovery client không?**

Không. Discovery có thể cần đọc Service, Endpoint hoặc EndpointSlice bằng get, list hoặc watch tùy implementation. Quyền phải được xác định theo client thực tế.

**Câu 3: Sửa ConfigMap có làm biến môi trường của Pod thay đổi ngay không?**

Thông thường không. Biến môi trường được tạo khi process khởi động; muốn nhận giá trị mới thường cần tạo Pod mới hoặc rollout. Cách mount file và cơ chế tích hợp API có hành vi khác.

**Câu 4: Liveness nên thất bại khi Kubernetes API tạm thời không truy cập được không?**

Không tự động. Hãy hỏi liệu restart process có sửa được lỗi đó không. Nếu ứng dụng vẫn phục vụ an toàn từ dữ liệu đã nạp, liveness không nên biến lỗi API thành vòng restart.

**Câu 5: Vì sao cần kiểm tra namespace trước khi kiểm tra discovery?**

Vì cùng một tên service có thể trỏ đến tài nguyên khác ở namespace khác, còn quyền và chính sách mạng cũng thường bị giới hạn theo namespace. Sai namespace có thể làm discovery rỗng dù service tồn tại.

**Câu 6: Khi nào rollout phù hợp hơn refresh?**

Khi cấu hình nằm trong biến môi trường, thư viện đọc giá trị một lần, thay đổi ảnh hưởng đến connection pool hoặc cần đồng bộ rõ ràng giữa các replica. Refresh chỉ phù hợp khi vòng đời bean và quy trình cập nhật đã được kiểm chứng.

## Kết luận

Điều kiện nền tảng trước khi triển khai Spring Cloud Kubernetes gồm một bộ phiên bản nhất quán, image có thể truy vết, namespace và Service đúng, đường mạng rõ ràng, ServiceAccount với RBAC tối thiểu, nguồn cấu hình được xác định, cùng các probe và tín hiệu quan sát phù hợp.

DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher đều có thể hữu ích, nhưng mỗi tính năng kéo theo dependency, quyền, đường kết nối và hành vi khi lỗi. Hãy triển khai từ khả năng nhỏ nhất đáp ứng yêu cầu, kiểm tra từng lớp bằng bằng chứng cụ thể, rồi mới mở rộng tích hợp. Một hệ thống sẵn sàng không chỉ là Pod khởi động thành công; đó là hệ thống mà nhóm có thể giải thích dữ liệu đến từ đâu, request đi qua đâu, quyền nào được dùng và sẽ phục hồi thế nào khi một thành phần tạm thời không sẵn sàng.
