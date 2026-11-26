# Các starter theo chức năng và loại Kubernetes client

## 1. Starter giải quyết vấn đề gì?

Khi tạo một ứng dụng Spring cho Kubernetes, việc thêm một dependency “all” có thể làm dự án chạy nhanh nhưng khó biết ứng dụng đang bật chức năng nào, cần quyền RBAC nào và đang phụ thuộc vào client nào. Cách an toàn hơn là bắt đầu từ nhu cầu thật:

- Ứng dụng có cần khám phá Service hay chỉ gọi DNS?
- Cấu hình đến từ file, ConfigMap, Secret hay một hệ thống khác?
- Có cần Spring Cloud LoadBalancer ở phía client không?
- Có cần cập nhật cấu hình khi tài nguyên Kubernetes thay đổi không?
- Thành phần nào trực tiếp gọi Kubernetes API?
- Dòng Spring Boot, Spring Cloud và Spring Cloud Kubernetes có tương thích không?
- Starter đang chọn Fabric8 hay Kubernetes Java Client?

Trong module **Spring Cloud Kubernetes**, các starter là điểm nối giữa ứng dụng Spring và Kubernetes. Starter thường kéo theo auto-configuration, integration và một Kubernetes client. Nó có thể làm ứng dụng tự tạo bean DiscoveryClient, nguồn cấu hình hoặc cơ chế theo dõi, nhưng không tự bảo đảm rằng ứng dụng có quyền RBAC hay rằng tính năng đó cần thiết cho triển khai.

Cùng một mục tiêu có thể có nhiều cách:

```text
Gọi Service cố định
    -> URL/DNS + HTTP client
    -> Không nhất thiết cần starter Kubernetes

Discovery động
    -> starter discovery
    -> Kubernetes client
    -> Service/EndpointSlice -> ServiceInstance

Cấu hình Kubernetes
    -> starter config
    -> Kubernetes client hoặc file mount
    -> ConfigMap/Secret -> Environment Spring
```

Mục tiêu của việc chọn starter là tạo đúng khả năng cần dùng với số dependency, quyền và hành vi vận hành có thể giải thích được.

## 2. Ba lớp cần tách khi khởi tạo dự án

Một cấu hình khởi đầu thường có ba lớp:

1. **Nền tảng Spring:** Spring Boot, Actuator, Web, cấu hình và lifecycle.
2. **Khả năng Spring Cloud Kubernetes:** discovery, config, load balancer hoặc watcher.
3. **Kubernetes client:** thư viện thực hiện các lệnh tới API server.

Có thể hình dung:

```text
Spring Boot application
        |
        v
Spring Cloud Kubernetes integration
        |
        v
Kubernetes client implementation
        |
        v
Kubernetes API server
```

Starter ở lớp thứ hai thường quyết định lớp thứ ba. Không nên thêm đồng thời hai họ starter dùng các client khác nhau cho cùng một khả năng nếu chưa biết cách auto-configuration chọn bean. Hai client có thể cùng xuất hiện trong classpath nhưng gây nhầm lẫn về transport, cấu hình, exception và bean được sử dụng.

Bộ phiên bản cũng là một phần của thiết kế. Spring Boot, Spring Cloud release train và Spring Cloud Kubernetes cần nằm trong ma trận tương thích của dòng dự án. Tên artifact hoặc cơ chế cấu hình có thể thay đổi giữa các dòng major/minor. Vì vậy, ví dụ dependency phải được đối chiếu với BOM và tài liệu của đúng phiên bản dự án trước khi áp dụng.

## 3. Starter theo chức năng

### 3.1. Discovery

Discovery starter dùng khi ứng dụng cần lấy danh sách instance từ Kubernetes theo abstraction DiscoveryClient. Nó phù hợp hơn việc tự viết code gọi API khi một thành phần Spring Cloud đã cần `ServiceInstance`.

Một dependency theo họ Kubernetes client có thể có tên dạng:

```xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-starter-kubernetes-client-discovery</artifactId>
</dependency>
```

Tên artifact trong ví dụ phải được kiểm tra theo release train đang dùng. Một số dòng có biến thể cho client khác hoặc có starter tổng hợp.

Discovery thường cần hiểu:

- Service nào được phép nhìn thấy?
- Namespace nào được quét?
- Backend là ClusterIP hay địa chỉ từng Pod?
- Endpoint chưa ready có được loại khỏi danh sách không?
- Dữ liệu được lấy bằng polling, list/watch hoặc cache nào?
- Cần đọc Service, EndpointSlice, Endpoints, Pod hay metadata khác?

Nếu ứng dụng chỉ gọi một URL như `http://inventory-service:8080`, discovery starter là phụ thuộc có thể không cần. Kubernetes Service và DNS đã cung cấp tên ổn định. Discovery có giá trị khi ứng dụng cần danh sách instance, lựa chọn động, metadata hoặc tích hợp với abstraction Spring Cloud.

### 3.2. ConfigMap và Secret

Config starter đưa dữ liệu cấu hình từ Kubernetes vào Environment của Spring. Tùy cấu hình, nguồn có thể là ConfigMap, Secret hoặc tài nguyên được mount.

Ví dụ minh họa theo họ Kubernetes client:

```xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-starter-kubernetes-client-config</artifactId>
</dependency>
```

Starter config không có nghĩa mọi thuộc tính của ứng dụng tự thay đổi khi ConfigMap đổi. Cần tách các bước:

```text
ConfigMap/Secret thay đổi
    -> client hoặc volume nhận giá trị mới
    -> Spring Environment được đọc lại
    -> bean hỗ trợ refresh được cập nhật
    -> connection pool/HTTP client áp dụng chính sách riêng
```

Nếu cấu hình chỉ cần ở lúc khởi động, rollout có kiểm soát thường dễ kiểm thử hơn refresh động. Nếu Secret được mount thành file, ứng dụng có thể đọc file mà không cần quyền đọc Secret qua API, nhưng vẫn phải xử lý quyền file, cập nhật và việc áp dụng giá trị.

Config starter có thể cần `get/list/watch` trên ConfigMap hoặc Secret tùy chế độ. Không cấp quyền `list secrets` chỉ vì ứng dụng có một cấu hình bí mật; hãy xác định tài nguyên và thao tác thật sự.

### 3.3. Spring Cloud LoadBalancer

LoadBalancer không phải là Kubernetes client. Nó chọn một instance từ danh sách do DiscoveryClient hoặc nguồn khác cung cấp.

Khi dùng client-side load balancing, dependency thường nằm ở lớp Spring Cloud LoadBalancer:

```xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Luồng đầy đủ có thể là:

```text
Ứng dụng cần gọi inventory-service
    -> DiscoveryClient lấy ServiceInstance
    -> Spring Cloud LoadBalancer chọn instance
    -> HTTP client gửi request
```

Nếu ứng dụng chỉ gọi ClusterIP của Service, Kubernetes vẫn có thể phân phối lưu lượng ở lớp nền tảng. Nếu LoadBalancer chọn địa chỉ Pod, ứng dụng đang tham gia cân bằng tải phía client. Cần xác định hai lớp đang chọn cùng một loại đích hay đang chồng chính sách.

LoadBalancer không tự cấp danh sách instance. Nếu bật LoadBalancer mà không có DiscoveryClient hoặc service instance supplier phù hợp, lời gọi có thể không hoạt động như mong đợi. Cũng cần kiểm tra timeout, connection pool và retry để tránh một request nghiệp vụ bị gửi lặp.

### 3.4. Configuration Watcher

Configuration Watcher là thành phần theo dõi thay đổi cấu hình và kích hoạt luồng cập nhật cho các ứng dụng Spring. Nó không biến mọi bean thành bean có thể refresh và cũng không tự giải quyết việc rollback.

Một thiết kế có watcher thường có hai workload:

```text
Watcher
  |-- đọc/watch ConfigMap hoặc Secret bằng ServiceAccount riêng
  '-- gửi thông báo refresh

Ứng dụng Spring
  |-- nhận thông báo
  |-- đọc lại nguồn nếu cần
  '-- áp dụng vào bean hỗ trợ cập nhật
```

Trước khi thêm watcher, hãy trả lời:

- Nguồn thay đổi là ConfigMap, Secret hay một nguồn khác?
- Watcher cần đọc namespace nào?
- Ứng dụng nhận thông báo qua kênh nào và được xác thực ra sao?
- Ứng dụng có tự đọc lại giá trị hay watcher gửi giá trị?
- Bean nào hỗ trợ refresh an toàn?
- Khi thông báo bị mất, cơ chế hội tụ hoặc refresh lại là gì?
- Khi Secret đổi, kết nối đang mở có cần khởi tạo lại không?

Nếu ứng dụng chỉ cần cấu hình tại thời điểm khởi động, watcher làm tăng số thành phần và quyền mà chưa chắc đem lại lợi ích. Nếu cần thay đổi động, phải thử nghiệm toàn bộ đường đi từ nguồn cấu hình đến hành vi đang chạy.

## 4. Hai họ Kubernetes client

### 4.1. Fabric8 Kubernetes Client

Fabric8 là một client phổ biến trong hệ sinh thái Java/Kubernetes. Nó cung cấp model tài nguyên, API fluent và các cơ chế watch/informer theo phiên bản thư viện.

Khi dự án dùng họ starter Fabric8, tên artifact thường thể hiện `fabric8` hoặc một hậu tố tương ứng trong dòng Spring Cloud Kubernetes. Ví dụ khái quát:

```xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-starter-kubernetes-fabric8-discovery</artifactId>
</dependency>
```

Đây là mẫu định hướng tên, không phải giá trị có thể sao chép mà không kiểm tra BOM. Điểm cần kiểm tra là:

- Artifact có tồn tại trong release train đã chọn không?
- Starter có kéo đúng module discovery hoặc config không?
- Phiên bản Fabric8 được quản lý bởi BOM nào?
- Cấu hình namespace, master URL, token và TLS có tương thích không?
- Các bean auto-configured có xung đột với client khác trong classpath không?

### 4.2. Kubernetes Java Client

Kubernetes Java Client là client Java do cộng đồng Kubernetes duy trì, cung cấp các API model và operation theo OpenAPI của Kubernetes. Một số dòng Spring Cloud Kubernetes có starter dựa trên client này.

Tên artifact thường chứa `client` thay vì `fabric8`, ví dụ theo mẫu:

```xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-starter-kubernetes-client-discovery</artifactId>
</dependency>
```

Trong cách đặt tên của từng dòng, từ `client` có thể chỉ họ Kubernetes Java Client; cần đọc dependency tree hoặc tài liệu phiên bản để xác định chính xác. Không suy ra loại client chỉ từ một phần tên artifact nếu release train đang dùng có quy ước khác.

Kubernetes Java Client thường có model và exception khác Fabric8. Code tự viết dựa trên một client không thể đổi họ client chỉ bằng cách đổi một dependency rồi kỳ vọng API giống nhau. Nếu dùng abstraction Spring Cloud Kubernetes, việc đổi client có thể ít ảnh hưởng hơn, nhưng vẫn cần kiểm thử auto-configuration, quyền, watch, timeout và lỗi.

### 4.3. Không trộn hai client một cách vô thức

Bảng so sánh ở mức lựa chọn:

| Tiêu chí | Fabric8 | Kubernetes Java Client |
|---|---|---|
| API Java | Fluent API và model theo thư viện | API/model theo OpenAPI client |
| Tích hợp starter | Chọn biến thể Fabric8 của release train nếu có | Chọn biến thể client tương ứng của release train |
| Code tự viết | Phụ thuộc trực tiếp vào API Fabric8 | Phụ thuộc trực tiếp vào API Java Client |
| Watch/informer | Cơ chế và kiểu sự kiện của Fabric8 | Cơ chế và kiểu sự kiện của Java Client |
| Khi đổi client | Có thể phải sửa code, cấu hình và test | Có thể phải sửa code, cấu hình và test |
| Cách giảm phụ thuộc | Dùng DiscoveryClient/config abstraction | Dùng DiscoveryClient/config abstraction |

Một ứng dụng nên chọn một họ client làm nền cho tính năng tích hợp. Nếu một thư viện khác bắt buộc client còn lại, hãy kiểm tra phiên bản, classpath và bean trước khi đưa vào production. Có thể tách trách nhiệm sang một workload riêng nếu hai thư viện không nên cùng tồn tại trong một tiến trình.

## 5. Chọn starter bằng ma trận nhu cầu

| Nhu cầu | Starter cần xem xét | Có cần Kubernetes API trong Pod? |
|---|---|---|
| Gọi Service cố định | Web/HTTP client và URL cấu hình | Không nhất thiết |
| Discovery động | Discovery starter theo client đã chọn | Thường có |
| Đọc ConfigMap lúc khởi động | Config starter hoặc file mount | Có thể có hoặc không |
| Đọc Secret lúc khởi động | Config/Secret integration hoặc Secret mount | Có thể có hoặc không |
| Chọn instance phía client | Spring Cloud LoadBalancer + nguồn instance | Phụ thuộc nguồn discovery |
| Theo dõi thay đổi cấu hình | Configuration Watcher và cơ chế refresh | Watcher thường có |
| Kiểm tra sức khỏe Pod | Actuator + probe | Không cần đọc API chỉ để kubelet gọi probe |
| Quản lý tài nguyên Kubernetes | Client/controller chuyên trách | Có, với quyền rộng hơn |

Đừng biến cột “có thể” thành mặc định. Hãy truy tìm luồng dữ liệu: ai đọc tài nguyên, đọc bằng phương thức nào và dữ liệu được dùng ở đâu.

## 6. Bộ dependency khởi đầu theo từng kịch bản

### Kịch bản A: gọi Service bằng DNS

Ứng dụng `order-service` gọi `inventory-service` bằng URL cấu hình:

```text
order-service
    -> http://inventory-service.shop.svc:8080
```

Bộ tối thiểu có thể chỉ gồm Spring Boot Web/HTTP client, Actuator nếu cần health endpoint và nguồn cấu hình thông thường. Không thêm discovery starter chỉ vì ứng dụng chạy trên Kubernetes.

Ưu điểm:

- Ít dependency.
- Không cần RBAC đọc Service hoặc EndpointSlice cho lời gọi này.
- Hành vi dễ hiểu: DNS, Service, endpoint, mạng và HTTP.

### Kịch bản B: discovery động và client-side load balancing

Ứng dụng cần danh sách instance để chọn theo metadata hoặc chiến lược phía client:

```text
Discovery starter theo họ client
+ Spring Cloud LoadBalancer
+ HTTP client tích hợp
```

Cần kiểm tra backend discovery cung cấp host, port, scheme và metadata gì. Nếu EndpointSlice chứa nhiều cổng hoặc nhiều loại Service, ánh xạ sang ServiceInstance phải được xác định rõ.

Cần RBAC đọc đúng tài nguyên. Cache discovery phải chịu được EndpointSlice thay đổi và watch reconnect. Retry phải gắn với idempotency của thao tác.

### Kịch bản C: cấu hình từ ConfigMap/Secret

Ứng dụng cần đọc cấu hình do Kubernetes quản lý:

```text
Config starter theo họ client
+ nguồn cấu hình Spring
+ Actuator/refresh nếu thực sự cần refresh
```

Nếu dùng volume mount, có thể thay Config starter bằng cơ chế file/config import phù hợp. Khi đó quyền API của Pod có thể giảm, nhưng phải kiểm tra độ trễ cập nhật và cơ chế reload.

Secret cần được tách khỏi ConfigMap trong đánh giá quyền. Không log Environment sau khi đã nạp để “kiểm tra nhanh”.

### Kịch bản D: watcher tập trung

Nhiều ứng dụng cần cùng một cơ chế phát hiện thay đổi:

```text
Configuration Watcher
+ ServiceAccount/Role riêng
+ cơ chế thông báo
+ ứng dụng có khả năng refresh
```

Tính đúng đắn phụ thuộc cả watcher và ứng dụng. Có thông báo không đồng nghĩa bean đã dùng giá trị mới. Cần metric cho lần phát hiện, lần gửi, lần nhận và lần áp dụng.

## 7. Quản lý dependency bằng BOM

Không nên tự chỉ định rời rạc phiên bản cho mọi starter Spring Cloud Kubernetes, Spring Cloud LoadBalancer và Kubernetes client. Dự án nên dùng BOM hoặc dependency management được release train hỗ trợ:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-dependencies</artifactId>
      <version>...</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
```

Dấu `...` là chỗ phải thay bằng phiên bản phù hợp với Spring Boot của dự án; không phải giá trị thực thi. Sau đó khai báo starter không lặp lại phiên bản nếu BOM đã quản lý.

Khi gặp lỗi khởi động hoặc `NoSuchMethodError`, kiểm tra:

- Spring Boot và Spring Cloud release train có nằm trong ma trận tương thích không?
- Có kéo hai phiên bản Kubernetes client do dependency khác nhau không?
- Có override phiên bản transitively mà BOM không dự kiến không?
- Auto-configuration đang tạo bean nào?
- Một property đã đổi tên hoặc thay đổi ý nghĩa giữa các phiên bản không?

Dependency tree là công cụ điều tra hữu ích, nhưng việc kiểm tra phải làm trong quy trình build của dự án ở bước phù hợp. Bài học này chỉ mô tả cách suy luận lựa chọn starter; không coi một tên artifact minh họa là bảo đảm cho mọi phiên bản.

## 8. Cấu hình và profile khi chạy ngoài cluster

Trong môi trường local, ứng dụng có thể không chạy trong Pod. Client có thể dùng kubeconfig, context hiện tại hoặc một cấu hình riêng. Quyền của tài khoản local thường rộng hơn ServiceAccount production, nên test local không đủ để xác nhận RBAC.

Nên tách profile:

```text
local
  -> mock, containerized Kubernetes hoặc kubeconfig giới hạn

cluster
  -> in-cluster API server, ServiceAccount, CA và RBAC production
```

Không đưa kubeconfig cá nhân vào image. Không commit token hoặc Secret vào repository. Khi dùng profile local để thử ConfigMap/Discovery, cần ghi rõ đang xác thực điều gì và điều gì chỉ được kiểm chứng trong cluster.

Nếu ứng dụng có thể chạy mà không cần Kubernetes API ở local nhưng lại bắt buộc gọi API khi ở cluster, hãy kiểm thử cả hai đường khởi động. Lỗi API server không nên làm liveness probe khởi động lại vô hạn nếu chức năng đó có thể dùng cache hoặc giá trị đã cấp.

## 9. Các dấu hiệu chọn sai starter

| Dấu hiệu | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Không có DiscoveryClient bean | Chưa thêm discovery starter, sai biến thể client hoặc auto-configuration bị tắt | Kiểm tra capability và loại client |
| Ứng dụng gọi DNS được nhưng discovery rỗng | Discovery không cần thiết hoặc thiếu RBAC/cache/namespace | So sánh nhu cầu với Service/DNS |
| `403` khi đọc EndpointSlice | Role thiếu API group/resource/verb hoặc binding sai | Kiểm tra ServiceAccount và RoleBinding |
| `NoSuchMethodError` | Lệch BOM hoặc trộn phiên bản client | Đồng bộ release train và dependency management |
| ConfigMap đổi nhưng bean không đổi | Thiếu refresh hoặc bean không hỗ trợ cập nhật | Thiết kế lại chuỗi áp dụng cấu hình |
| Có nhiều bean client | Trộn Fabric8 và Kubernetes Java Client hoặc thư viện khác | Giữ một họ client cho trách nhiệm tích hợp |
| Pod health tốt nhưng request lỗi | Readiness không phản ánh điều kiện nghiệp vụ hoặc lỗi Service | Kiểm tra endpoint, port, network và dependency |

Không sửa lỗi bằng cách thêm nhiều starter tổng hợp hơn. Hãy xác định capability đang thiếu, client đang được dùng và request Kubernetes nào thất bại.

## 10. Checklist tạo dự án

Trước khi chốt `pom.xml` hoặc `build.gradle`, hãy trả lời:

- Ứng dụng có cần Kubernetes API hay chỉ cần Service/DNS?
- Tính năng nào cần bật: discovery, config, load balancer hay watcher?
- Starter nào tương ứng với đúng release train?
- Starter đang chọn Fabric8 hay Kubernetes Java Client?
- Có một BOM quản lý các phiên bản liên quan không?
- Có dependency nào kéo họ client thứ hai vào classpath không?
- Ứng dụng cần đọc Service, EndpointSlice, ConfigMap, Secret hay Pod?
- Role và RoleBinding tối thiểu cho ServiceAccount là gì?
- Cấu hình được đọc lúc khởi động hay cần refresh động?
- LoadBalancer chọn ClusterIP hay địa chỉ từng instance?
- Retry và connection pool tương tác với thay đổi endpoint ra sao?
- Local profile có đang che giấu lỗi RBAC production không?
- Actuator probe có phân biệt startup, liveness và readiness không?

Một starter tốt là starter giải quyết một nhu cầu đã xác định, nằm trong ma trận phiên bản được hỗ trợ và có quyền vận hành rõ ràng. Với Spring Cloud Kubernetes, quyết định về starter đồng thời là quyết định về discovery, nguồn cấu hình, loại Kubernetes client, RBAC và cách ứng dụng phản ứng khi control plane tạm thời không sẵn sàng.
