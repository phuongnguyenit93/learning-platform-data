# Ứng dụng kết nối trực tiếp Kubernetes API và các phương án thay thế

## 1. Đặt vấn đề: ứng dụng cần biết gì về Kubernetes?

Một ứng dụng Spring chạy trong Pod có thể gọi dịch vụ khác, nhận cấu hình và được kiểm tra sức khỏe mà không tự truy vấn Kubernetes API. Nền tảng đã cung cấp Service, DNS, biến môi trường, volume và các cơ chế probe cho những nhu cầu này.

Spring Cloud Kubernetes bổ sung khả năng tích hợp sâu hơn: ứng dụng có thể khám phá dịch vụ bằng DiscoveryClient, lấy cấu hình từ ConfigMap hoặc Secret, kết hợp Spring Cloud LoadBalancer và tham gia luồng cập nhật cấu hình do Configuration Watcher kích hoạt. Đổi lại, hệ thống phải quản lý quyền truy cập, kết nối tới API server, bộ nhớ đệm và cách xử lý khi dữ liệu nền tảng thay đổi.

Câu hỏi thiết kế quan trọng là:

> Quyết định nào thật sự cần dữ liệu Kubernetes ở thời điểm chạy, và thành phần nào nên chịu trách nhiệm đọc dữ liệu đó?

Bài học này thuộc phần tổng quan của module **Spring Cloud Kubernetes**. Mục tiêu là hiểu ranh giới giữa ứng dụng nghiệp vụ và Kubernetes API, rồi chọn cách tích hợp vừa đủ cho từng nhu cầu.

Sau bài học, bạn có thể:

- Phân biệt lưu lượng nghiệp vụ với truy cập API quản lý Kubernetes.
- Giải thích trách nhiệm phát sinh khi ứng dụng trực tiếp dùng Kubernetes client.
- So sánh cách truy cập trực tiếp với DNS/Service, cấu hình được cấp vào Pod và một thành phần theo dõi tập trung.
- Chọn vị trí đặt DiscoveryClient, LoadBalancer và Configuration Watcher.
- Nhận diện các yêu cầu RBAC, khả năng phục hồi và quan sát cần có trước khi đưa thiết kế vào vận hành.

## 2. Hai loại kết nối có mục đích khác nhau

Giả sử `order-service` cần gọi `inventory-service` trong namespace `shop`.

### 2.1. Kết nối để xử lý nghiệp vụ

Ứng dụng gửi HTTP tới tên Service:

```text
http://inventory-service.shop.svc.cluster.local:8080
```

Đây là dạng tên minh họa cho cluster dùng miền DNS `cluster.local`. Miền cluster và cổng Service phải khớp với cấu hình thực tế. Nếu hai ứng dụng cùng namespace, tên ngắn `inventory-service` thường đã đủ để DNS phân giải.

Đường đi khái quát:

```text
order-service
    |
    | HTTP nghiệp vụ
    v
inventory-service (Kubernetes Service)
    |
    v
Pod đích nằm trong tập endpoint sẵn sàng
```

Với Service thông thường có ClusterIP, DNS cung cấp địa chỉ Service; cơ chế mạng của cluster chuyển tiếp kết nối tới backend thích hợp. Chi tiết cách chuyển tiếp phụ thuộc triển khai mạng. Headless Service có hành vi DNS khác, nên không thể mặc định mọi Service đều có một IP ảo.

Ứng dụng không cần quyền `list pods` hay `get services` chỉ để gọi một tên Service qua mạng. DNS và mạng vẫn cần hoạt động, nhưng đó là phụ thuộc khác với việc chính ứng dụng đăng nhập Kubernetes API.

### 2.2. Kết nối để đọc trạng thái nền tảng

Một Kubernetes client có thể gửi yêu cầu như:

```http
GET /api/v1/namespaces/shop/services/inventory-service
GET /api/v1/namespaces/shop/endpoints
```

Hoặc truy vấn EndpointSlice bằng API tương ứng. Đây là yêu cầu tới API server để đọc tài nguyên Kubernetes, không phải yêu cầu tới API nghiệp vụ của kho hàng.

Phân biệt hai loại địa chỉ:

| Địa chỉ | Bên tiếp nhận | Mục đích |
|---|---|---|
| `http://inventory-service:8080` | Service dẫn tới ứng dụng kho | Tra cứu tồn kho, giữ hàng |
| API server của cluster | Kubernetes API server | Đọc Service, endpoint, cấu hình hoặc metadata |
| Endpoint quản trị của ứng dụng Spring | Ứng dụng Spring | Sức khỏe, thông tin vận hành, thao tác quản trị được cho phép |

Kubernetes API nằm trong mặt phẳng điều khiển (*control plane*). Lưu lượng phục vụ đơn hàng nằm trong mặt phẳng dữ liệu (*data plane*). Một thiết kế tốt tránh biến mỗi yêu cầu đặt hàng thành một yêu cầu mới lên control plane.

## 3. “Kết nối trực tiếp” có nhiều hình thức

Trong phạm vi bài này, truy cập trực tiếp nghĩa là **tiến trình ứng dụng dùng danh tính của mình để gọi Kubernetes API**.

Có thể gặp ba hình thức:

1. Mã ứng dụng tự khởi tạo Kubernetes client và gọi API.
2. Thư viện tích hợp, chẳng hạn một thành phần của Spring Cloud Kubernetes, gọi API thay cho ứng dụng.
3. Một agent hoặc dịch vụ độc lập gọi API, rồi cung cấp dữ liệu hoặc tín hiệu cho ứng dụng.

Hai hình thức đầu đều khiến Pod ứng dụng cần đường mạng và quyền phù hợp tới API server. Dùng abstraction như DiscoveryClient giúp giảm mã phụ thuộc vào Kubernetes trong lớp nghiệp vụ, nhưng không tự loại bỏ phụ thuộc vận hành ở bên dưới.

Hình thức thứ ba chuyển điểm kết nối API sang thành phần trung gian. Ví dụ, Configuration Watcher có thể theo dõi thay đổi cấu hình và thông báo tới ứng dụng theo cơ chế được thiết lập. Khi đó phải kiểm tra toàn bộ luồng: bên theo dõi đọc tài nguyên nào, bên ứng dụng lấy giá trị cấu hình mới từ đâu, và thông báo có được xử lý thành công hay không.

Không thể kết luận “ứng dụng không cần Kubernetes API” chỉ vì đã triển khai một watcher. Nếu nguồn cấu hình của ứng dụng vẫn đọc ConfigMap qua client trong tiến trình, ứng dụng vẫn cần quyền cho phần đọc đó.

## 4. Khi ứng dụng đọc Kubernetes API, nó phải chịu trách nhiệm gì?

### 4.1. Xác thực, namespace và TLS

Trong cluster, thư viện client thường có thể sử dụng thông tin được cấp cho Pod: địa chỉ API server, chứng thư CA và token của ServiceAccount. Cách tự cấu hình cụ thể tùy thư viện và cách triển khai Pod.

Những dữ liệu này trả lời các câu hỏi khác nhau:

- **Địa chỉ API server:** gửi yêu cầu tới đâu?
- **CA:** làm sao xác thực máy chủ TLS?
- **Token ServiceAccount:** bên gọi mang danh tính nào?
- **Namespace:** tài nguyên cần đọc thuộc phạm vi nào?
- **RBAC:** danh tính đó được làm những thao tác gì?

ServiceAccount không tự tạo ra quyền đọc mọi tài nguyên. Pod có token hợp lệ vẫn có thể nhận `403 Forbidden` nếu thiếu quyền.

Không tắt kiểm tra TLS để “sửa nhanh” lỗi kết nối. Không đưa token, nội dung Secret hoặc toàn bộ kubeconfig vào log. Nếu token được cấp qua volume có cơ chế thay mới, client cũng phải tương thích với vòng đời token đó; không giả định token là chuỗi cố định dùng mãi.

Khi chạy ngoài cluster, môi trường phát triển có thể dùng kubeconfig hoặc cơ chế xác thực khác. Quyền quản trị trên máy lập trình viên không phản ánh quyền của Pod sản xuất.

### 4.2. RBAC theo nhu cầu thực tế

Ví dụ sau minh họa một ServiceAccount chỉ được đọc Service và dữ liệu endpoint trong namespace `shop`. Đây là ví dụ để hiểu phạm vi quyền, không phải manifest bao phủ mọi tính năng Spring Cloud Kubernetes.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-runtime
  namespace: shop
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-discovery-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-discovery-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-runtime
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-discovery-reader
```

Pod muốn sử dụng danh tính này phải được gán `serviceAccountName: order-runtime`.

Trong triển khai thật, chỉ giữ tài nguyên và động từ mà client đã chọn cần dùng. Một cách discovery có thể cần metadata Pod; cách khác chỉ cần Service hoặc EndpointSlice. Không cấp quyền đọc Pod, ConfigMap, Secret và toàn bộ namespace một cách mặc định.

Nếu ứng dụng chỉ cần đọc một ConfigMap đã biết tên, nhu cầu có thể hẹp hơn một client chuyên `list/watch` cả tập tài nguyên. Cần đánh giá hành vi API thực sự của client trước khi giới hạn theo tên tài nguyên; quyền `get` một tên cụ thể không mặc nhiên đáp ứng các thao tác `list/watch`.

Đặc biệt, quyền `list secrets` có thể cho phép đọc nội dung Secret trong phạm vi được cấp. Đó không chỉ là quyền xem danh sách tên.

Ứng dụng không dùng Kubernetes API có thể cân nhắc tắt tự gắn token ServiceAccount. Chỉ áp dụng sau khi chắc chắn không có thành phần trong Pod phụ thuộc vào token đó.

### 4.3. Số lượng kết nối và tải lên API server

Giả sử có 120 Pod ứng dụng, mỗi Pod định kỳ đọc ba nhóm tài nguyên mỗi 15 giây:

```text
120 Pod × 3 yêu cầu / 15 giây = 24 yêu cầu mỗi giây
```

Đây là ước tính minh họa, chưa tính phân trang, retry, khởi động đồng loạt hoặc các namespace khác. Nếu mỗi yêu cầu nghiệp vụ lại đọc tài nguyên, tải sẽ còn phụ thuộc trực tiếp vào lượng truy cập của người dùng.

Một vòng `list/watch` hợp lý thường tốt hơn polling dày cho dữ liệu hay thay đổi, nhưng watch cũng có chi phí:

- Kết nối có thể đóng hoặc mất mạng.
- Client phải nối lại, có backoff và tránh nhiều Pod retry đồng thời.
- Khi phiên bản tài nguyên không còn phù hợp, có thể phải lấy lại danh sách rồi thiết lập watch mới.
- Cache có thể tạm thời chậm hơn trạng thái thực tế.
- Nhiều bản sao ứng dụng vẫn có thể tạo nhiều watch riêng.

Watch không phải hàng đợi sự kiện nghiệp vụ có cam kết xử lý đúng một lần. Không dùng sự kiện tài nguyên Kubernetes thay thế cơ chế giao dịch hoặc hàng đợi đơn hàng.

### 4.4. Khi API server tạm thời không truy cập được

Cần tách hai tình huống:

- **Ứng dụng đã chạy ổn định:** có thể tiếp tục dùng cấu hình hoặc danh sách instance trong cache nếu chính sách cho phép.
- **Ứng dụng vừa khởi động:** chưa chắc đã có dữ liệu cần thiết để phục vụ an toàn.

Ví dụ, danh sách instance cũ có thể giúp vượt qua một gián đoạn ngắn, nhưng cũng có thể chứa Pod đã mất. Một cấu hình tính năng có thể cho phép dùng giá trị cũ; một thông tin xác thực đã bị thu hồi lại cần chính sách khác.

Cần quyết định rõ:

1. Dữ liệu nào bắt buộc phải có trước khi ứng dụng sẵn sàng?
2. Có chấp nhận giá trị cũ không, và trong bao lâu?
3. Khi không thể làm mới dữ liệu, ứng dụng báo động hoặc từ chối thao tác nào?
4. Timeout và backoff có ngăn việc chờ vô hạn hoặc retry dồn dập không?

Không gắn mọi lỗi Kubernetes API với liveness. Nếu gián đoạn control plane làm toàn bộ Pod bị khởi động lại, ứng dụng có thể mất luôn cache đang hữu ích và tạo thêm tải lúc khởi động.

## 5. Phương án thay thế cho từng nhu cầu

### 5.1. Khám phá dịch vụ bằng Kubernetes Service và DNS

Nếu `order-service` chỉ cần gửi HTTP tới `inventory-service`, một tên Service ổn định thường là điểm xuất phát phù hợp.

Ưu điểm:

- Mã nghiệp vụ không phải liệt kê Pod hoặc hiểu nhãn Kubernetes.
- Pod ứng dụng không cần quyền đọc tài nguyên chỉ để tìm đích gọi.
- Việc thay Pod và duy trì endpoint thuộc trách nhiệm của nền tảng.

Giới hạn cần hiểu:

- Client không trực tiếp nhận danh sách metadata của từng instance.
- Kết nối HTTP giữ lâu có thể tiếp tục sử dụng cùng backend; không nên suy diễn rằng mỗi HTTP request chắc chắn được chia đều.
- Cần quan sát DNS, kết nối, timeout và hành vi connection pool.

Nếu cần định tuyến theo metadata riêng của instance hoặc tích hợp một thành phần Spring Cloud yêu cầu DiscoveryClient, lúc đó discovery qua Kubernetes API mới có thêm giá trị rõ ràng.

### 5.2. Cấp ConfigMap và Secret vào Pod

Ứng dụng có thể nhận cấu hình thông qua biến môi trường hoặc file được mount vào container.

| Cách cấp cấu hình | Ứng dụng nhận dữ liệu | Điều cần lưu ý khi thay đổi |
|---|---|---|
| Biến môi trường | Giá trị tại lúc tạo container | Thay ConfigMap/Secret không cập nhật biến môi trường của tiến trình đang chạy; cần tạo lại Pod theo quy trình triển khai |
| Volume ConfigMap/Secret | File do nền tảng cấp | File có thể được cập nhật với độ trễ; ứng dụng phải có cơ chế đọc lại |
| Volume qua `subPath` | File ở đường mount cụ thể | Không dựa vào cơ chế này để nhận cập nhật tự động của ConfigMap/Secret |
| Client trong ứng dụng | Đọc tài nguyên qua Kubernetes API | Cần danh tính, RBAC, chính sách cache và cơ chế áp dụng giá trị mới |

Với volume, **file đổi không có nghĩa là bean Spring hoặc connection pool tự đổi**. Có ba bước riêng biệt:

```text
Nguồn cấu hình thay đổi
    -> giá trị mới đến được ứng dụng
    -> ứng dụng áp dụng giá trị đó vào hành vi đang chạy
```

Spring Boot có thể đọc cấu hình từ file hoặc nguồn nhập cấu hình được thiết lập phù hợp. Muốn cập nhật khi đang chạy phải có cơ chế riêng cho phần đọc lại và phần áp dụng.

Mount Secret giúp ứng dụng không cần tự gọi API để lấy Secret đó. Tuy nhiên, Secret vẫn nằm trong phạm vi truy cập của container; cần kiểm soát quyền đọc file, cách log và vòng đời thông tin xác thực. Dữ liệu Secret được biểu diễn bằng base64 không có nghĩa là đã được mã hóa an toàn.

### 5.3. Cập nhật cấu hình bằng rollout có kiểm soát

Không phải cấu hình nào cũng thích hợp để thay trực tiếp trong tiến trình. Ví dụ: thay các tham số khởi tạo thư viện, đổi cấu trúc kết nối hoặc cần kiểm tra đồng nhất trước khi phục vụ.

Một phương án là gắn phiên bản cấu hình vào Pod template hoặc dùng tên ConfigMap có phiên bản, sau đó triển khai Pod mới. Chỉ sửa ConfigMap đứng riêng thường không tự làm Deployment rollout.

Phương án này có lợi khi:

- Cần rollback về một bộ mã nguồn và cấu hình xác định.
- Ứng dụng chủ yếu đọc cấu hình ở lúc khởi động.
- Có nhiều bean không hỗ trợ cập nhật động an toàn.

Đổi lại, cần quản lý quá trình triển khai, readiness và dung lượng tài nguyên khi thay Pod. Việc rollout phải được kích hoạt bằng quy trình hoặc controller được chọn, không phát sinh tự động chỉ vì một key trong ConfigMap đổi.

### 5.4. Dùng Configuration Watcher hoặc thành phần theo dõi chung

Một thành phần theo dõi có thể nhận trách nhiệm quan sát tài nguyên cấu hình và gửi tín hiệu tới các ứng dụng cần cập nhật.

```text
Kubernetes API
    |
    | theo dõi thay đổi
    v
Configuration Watcher
    |
    | thông báo theo cơ chế đã cấu hình
    v
Ứng dụng Spring
    |
    | lấy/đọc lại dữ liệu và áp dụng
    v
Hành vi mới có hiệu lực
```

Cách này có thể giảm việc mỗi ứng dụng tự triển khai logic phát hiện thay đổi. Nhưng vẫn phải giải quyết:

- Watcher cần RBAC nào và được theo dõi namespace nào?
- Nó xác định ứng dụng nhận thông báo bằng cách nào?
- Ứng dụng có cần đọc Kubernetes API khi refresh không?
- Thông báo bị mất hoặc ứng dụng tạm ngừng thì hệ thống hội tụ lại ra sao?
- Endpoint quản trị có được xác thực và giới hạn truy cập không?
- Một lần refresh có thực sự thay đổi thành phần đang sử dụng cấu hình không?

Cơ chế thông báo và các yêu cầu triển khai phụ thuộc phiên bản, dependency và cấu hình được chọn. Không giả định chỉ cần thêm watcher là mọi ConfigMap, Secret và mọi bean đều cập nhật được.

Watcher là một workload khác cần vận hành: phải theo dõi lỗi, sức khỏe, quyền và khả năng khôi phục. Nếu watcher phải khám phá đích thông báo qua API, tổng nhu cầu quyền cũng có thể vượt phần đọc ConfigMap.

### 5.5. Dịch vụ cấu hình, secret manager hoặc controller chuyên trách

Ở hệ thống nhiều môi trường hoặc nhiều nền tảng triển khai, cấu hình có thể được quản lý bởi một dịch vụ cấu hình hoặc secret manager riêng. Một controller cũng có thể chuyển dữ liệu từ hệ thống đó thành tài nguyên hoặc volume cho workload.

Đây là cách di chuyển trách nhiệm tích hợp:

- Ứng dụng có thể đọc file hoặc gọi một API cấu hình riêng.
- Controller hoặc agent đảm nhiệm đồng bộ và danh tính đối với hệ thống nguồn.
- Kubernetes API có thể vẫn xuất hiện trong luồng, nhưng không nhất thiết do ứng dụng nghiệp vụ gọi.

Cần đánh giá thêm nguồn dữ liệu chuẩn, độ trễ đồng bộ, vòng đời thông tin xác thực, điểm lỗi và phạm vi ảnh hưởng. Một lớp trung gian có ích khi giải quyết được yêu cầu cụ thể; nó cũng tạo thêm thành phần cần vận hành.

## 6. Đặt Spring Cloud Kubernetes vào đúng vị trí

### 6.1. DiscoveryClient: abstraction cho khám phá dịch vụ

DiscoveryClient hữu ích khi ứng dụng hoặc thư viện Spring Cloud cần làm việc với tên dịch vụ và danh sách instance theo một abstraction chung.

Luồng tư duy:

```text
Thành phần Spring cần instance của inventory-service
    -> DiscoveryClient
    -> cơ chế khám phá Kubernetes đã chọn
    -> danh sách instance dùng để gọi
```

Ưu điểm của abstraction là lớp sử dụng không nhất thiết phải tự viết truy vấn Service, Pod hoặc EndpointSlice. Tuy nhiên, người vận hành vẫn cần biết backend đang đọc tài nguyên nào, có cache hay không và cập nhật dữ liệu theo cách nào.

Không dùng DiscoveryClient chỉ để đọc tất cả dịch vụ trong cluster nếu ứng dụng chỉ gọi một tên Service cố định.

### 6.2. Spring Cloud LoadBalancer: cần xác định đối tượng được chọn

Cần trả lời: load balancer phía ứng dụng đang chọn **instance Pod** hay chọn **địa chỉ Service**?

- Nếu chọn địa chỉ instance, ứng dụng tham gia cân bằng tải phía client và cần danh sách instance phù hợp.
- Nếu gọi địa chỉ Service, Kubernetes đã có cơ chế chuyển tiếp tới backend; lợi ích của một lớp chọn đích bổ sung phải được đánh giá theo thiết kế thực tế.

Các chế độ tích hợp cụ thể phụ thuộc cấu hình. Không suy luận rằng có Spring Cloud LoadBalancer thì lưu lượng luôn đi thẳng tới Pod, hoặc rằng client chắc chắn biết trạng thái sức khỏe tức thời của từng Pod.

Với mỗi cách chọn đích, cần xem xét cổng, giao thức, namespace, endpoint sẵn sàng, connection pool, timeout và retry. Retry có thể làm lặp thao tác nghiệp vụ; chỉ bật với hiểu biết rõ về tính an toàn của yêu cầu.

### 6.3. ConfigMap, Secret và cập nhật cấu hình

Spring Cloud Kubernetes có thể đưa cấu hình Kubernetes vào hệ sinh thái cấu hình Spring. Trước khi chọn cách này, hãy xác định:

1. Cấu hình được lấy qua API hay file đã mount?
2. Nguồn nào được ưu tiên khi cùng một thuộc tính xuất hiện ở nhiều nơi?
3. Lỗi lấy cấu hình lúc khởi động được xử lý thế nào?
4. Khi nguồn đổi, điều gì kích hoạt đọc lại?
5. Thành phần nào trong ứng dụng có khả năng nhận giá trị mới?

Secret nên được đánh giá riêng vì mức nhạy cảm và phạm vi quyền khác ConfigMap. Không xem việc bật đọc Secret như một tùy chọn tiện lợi mặc định.

### 6.4. Theo dõi sức khỏe Pod không đồng nghĩa với đọc API

Kubelet có thể gọi probe của container để biết ứng dụng đã khởi động, còn sống hoặc sẵn sàng. Với Spring Boot Actuator được cấu hình phù hợp, ứng dụng có thể cung cấp các endpoint sức khỏe cho cơ chế đó.

Phân biệt:

- **Startup probe:** ứng dụng đã vượt qua giai đoạn khởi động chưa?
- **Liveness probe:** có cần khởi động lại container không?
- **Readiness probe:** Pod đã sẵn sàng nhận lưu lượng chưa?

Ứng dụng không cần quyền đọc Pod chỉ để kubelet gọi endpoint sức khỏe của nó.

Ngược lại, một dashboard hoặc controller muốn quan sát nhiều Pod có thể cần đọc Kubernetes API. Đó là nhu cầu khác với việc một ứng dụng công bố sức khỏe của chính mình.

Readiness cũng không biến discovery thành dữ liệu nhất quán tức thời. Cần tính đến thời gian nền tảng cập nhật endpoint và thời gian cache phía client hội tụ. Hành vi còn phụ thuộc loại Service và cấu hình có công bố địa chỉ chưa sẵn sàng hay không.

## 7. Bảng lựa chọn theo yêu cầu

| Nhu cầu thực tế | Phương án nên xem xét trước | Khi nào cần tích hợp API sâu hơn? |
|---|---|---|
| Gọi một dịch vụ nội bộ qua HTTP | Kubernetes Service và DNS | Cần danh sách instance hoặc metadata phục vụ lựa chọn đích |
| Cấu hình chỉ cần đọc khi khởi động | Biến môi trường hoặc file, kết hợp rollout | Cần lấy dữ liệu theo tài nguyên Kubernetes và chấp nhận trách nhiệm client |
| Thay cấu hình khi ứng dụng đang chạy | Xác định cơ chế áp dụng trước, rồi chọn mount/watch/refresh | Có yêu cầu rõ về phát hiện thay đổi và nguồn dữ liệu qua API |
| Đọc thông tin bí mật | Cơ chế cấp Secret hoặc secret manager phù hợp | Ứng dụng cần tự truy xuất, có thiết kế quyền và vòng đời rõ ràng |
| Kubelet kiểm tra sức khỏe ứng dụng | Probe và endpoint sức khỏe | Không cần API chỉ cho luồng probe |
| Theo dõi nhiều tài nguyên hoặc tự động điều khiển cluster | Controller/agent hoặc client chuyên trách | Đây là chức năng cốt lõi phụ thuộc tài nguyên Kubernetes |
| Nhiều ứng dụng cần cùng một luồng thông báo cấu hình | Watcher hoặc cơ chế điều phối chung | Cần kiểm soát tập trung việc theo dõi và phân phối thông báo |

Không có một phương án tốt nhất cho mọi ứng dụng. Tiêu chí là lợi ích của dữ liệu Kubernetes có lớn hơn chi phí quyền truy cập, khả năng phục hồi và vận hành mà nó tạo ra hay không.

## 8. Tình huống thiết kế: hệ thống đặt hàng

Hệ thống gồm `order-service`, `inventory-service` và `pricing-service`. Tất cả chạy trong namespace `shop`.

### 8.1. Yêu cầu ban đầu

- Order gọi Inventory và Pricing bằng HTTP.
- Cấu hình giới hạn số mặt hàng được đọc lúc khởi động.
- Thông tin xác thực được cấp cho container qua cơ chế đã chọn.
- Các dịch vụ công bố endpoint sức khỏe.

Thiết kế có thể bắt đầu bằng:

```text
order-service
  |-- HTTP -> inventory-service (DNS/Service)
  |-- HTTP -> pricing-service   (DNS/Service)
  |-- cấu hình từ biến môi trường/file
  |-- thông tin xác thực từ nguồn được cấp
  '-- endpoint sức khỏe <- kubelet probe
```

Ở mức yêu cầu này, chưa có lý do bắt buộc để Order tự liệt kê Pod hoặc mở watch Kubernetes API.

### 8.2. Xuất hiện yêu cầu định tuyến theo metadata

Giả sử Order cần chọn nhóm instance Pricing theo một metadata nghiệp vụ đã được chuẩn hóa. Nhóm phải xác định:

- Metadata nào biểu diễn lựa chọn và ai quản lý nó?
- Có thể biểu diễn nhóm bằng Service riêng và selector không?
- Nếu cần client chọn instance, dữ liệu metadata có được backend discovery cung cấp đúng cách không?
- Khi cache chậm cập nhật, lựa chọn sai nhóm có ảnh hưởng nghiệp vụ nào?

Nếu các nhóm ổn định và biểu diễn được bằng Service riêng, Order có thể gọi các tên Service đó. Nếu cần quyết định động theo instance, DiscoveryClient cùng một chiến lược lựa chọn đích có thể phù hợp hơn.

Không coi nhãn hoặc annotation trên Pod là dữ liệu tự động có mặt trong mọi đối tượng ServiceInstance. Cần thiết lập và xác minh ánh xạ của cơ chế discovery được dùng.

### 8.3. Xuất hiện yêu cầu cập nhật cấu hình nhanh

Nhóm muốn đổi một cờ tính năng mà không tạo lại Pod. Khi đó cần thiết kế trọn luồng:

```text
Cập nhật nguồn cấu hình
    -> phát hiện thay đổi
    -> chuyển tín hiệu/giá trị
    -> đọc lại
    -> áp dụng vào thành phần hỗ trợ cập nhật
    -> quan sát phiên bản đang có hiệu lực
```

Có thể chọn Configuration Watcher và cơ chế refresh phù hợp, hoặc chọn một cách cấp cấu hình khác. Chỉ triển khai khi đã xác định bean nào sẽ dùng giá trị mới, lỗi cập nhật xử lý thế nào và có cần rollback không.

Với cấu hình không thể áp dụng an toàn trong tiến trình, rollout vẫn là một lựa chọn hợp lệ ngay cả khi hệ thống đã có watcher.

## 9. Quan sát và xử lý sự cố theo đúng lớp

Khi thiết kế có truy cập API, nên có tín hiệu vận hành về:

- Số lần gọi API, độ trễ, timeout và lỗi theo loại thao tác.
- Lần đồng bộ thành công gần nhất, lỗi nối lại watch và độ cũ của cache.
- Số instance mà discovery nhìn thấy.
- Phiên bản cấu hình đang có hiệu lực hoặc thời điểm áp dụng gần nhất.
- Số lần thông báo refresh thành công/thất bại, nếu dùng watcher.

Chỉ ghi định danh hoặc thông tin phiên bản cần thiết; tránh lộ giá trị nhạy cảm. Việc “nhận được thông báo” và “đã áp dụng cấu hình” nên là hai tín hiệu phân biệt.

| Biểu hiện | Lớp cần kiểm tra trước | Hướng suy luận |
|---|---|---|
| Gọi tên Service thất bại | DNS, Service, endpoint và mạng | Không mặc định là lỗi RBAC |
| API trả `401` | Danh tính và token | Kiểm tra token có hợp lệ, đúng cơ chế xác thực không |
| API trả `403` | RBAC | Kiểm tra đúng ServiceAccount, tài nguyên, động từ và namespace |
| API timeout | Mạng tới API server, TLS, timeout, tải | Tách lỗi control plane khỏi lỗi HTTP nghiệp vụ |
| Discovery không thấy instance | Namespace, bộ lọc, quyền, endpoint và cache | So sánh dữ liệu mong đợi với dữ liệu client đang dùng |
| File cấu hình đổi nhưng hành vi cũ | Đọc lại và áp dụng cấu hình trong ứng dụng | Mount thành công chưa chứng minh refresh thành công |
| Cập nhật ConfigMap nhưng Pod không rollout | Quy trình triển khai/Pod template | Sửa ConfigMap không tự tạo ReplicaSet mới |
| API gián đoạn làm nhiều Pod khởi động lại | Thiết kế probe và phụ thuộc lúc khởi động | Xem có gắn phụ thuộc từ xa vào liveness quá chặt không |

Nếu nhận `403`, không chữa bằng cách cấp `cluster-admin` cho ứng dụng. Hãy xác định yêu cầu API cụ thể bị từ chối và cấp đúng phạm vi cần thiết.

## 10. Những nhầm lẫn dễ dẫn tới thiết kế dư thừa

### “Chạy trên Kubernetes thì phải dùng Spring Cloud Kubernetes”

Ứng dụng Spring có thể chạy trên Kubernetes với Service/DNS, biến môi trường, volume và probe mà không cần bật các tính năng tích hợp API. Chọn Spring Cloud Kubernetes theo nhu cầu discovery, cấu hình hoặc theo dõi thực sự có ích.

### “Có ServiceAccount thì đã có đủ quyền”

ServiceAccount cung cấp danh tính. RBAC quyết định quyền; mạng và TLS quyết định khả năng thiết lập kết nối an toàn. Các phần này phải được kiểm tra riêng.

### “Watch giúp dữ liệu luôn đúng ngay lập tức”

Watch giảm nhu cầu polling và giúp nhận thay đổi, nhưng vẫn có độ trễ, cache, mất kết nối và quá trình đồng bộ lại. Ứng dụng phải chịu được việc trạng thái nhìn thấy tạm thời khác trạng thái thực tế.

### “Đổi Secret là mọi kết nối đổi theo”

Giá trị mới cần đến được tiến trình, rồi thành phần sử dụng phải đọc lại hoặc khởi tạo lại an toàn. Kết nối đang mở có thể vẫn dùng thông tin cũ. Cần thiết kế cả phía cấp thông tin lẫn phía sử dụng.

### “Có watcher thì không còn ai trong ứng dụng cần quyền API”

Watcher chỉ chuyển trách nhiệm của phần việc mà nó thực hiện. Nếu ứng dụng vẫn đọc cấu hình hoặc discovery qua API, phần quyền tương ứng vẫn cần tồn tại.

### “Càng nhiều tầng cân bằng tải càng tốt”

Cần biết từng tầng chọn đích nào và giải quyết vấn đề gì. Service, client load balancer, connection pool và retry phối hợp không đúng có thể tạo hành vi phân phối khó dự đoán.

## 11. Câu hỏi tự kiểm tra trước khi chọn kiến trúc

1. Nếu bỏ quyền gọi Kubernetes API của Pod, chức năng nghiệp vụ cụ thể nào ngừng hoạt động?
2. Một tên Service ổn định có đáp ứng việc gọi dịch vụ không?
3. Cấu hình cần thay ngay trong tiến trình, hay có thể gắn với một lần rollout?
4. Ai đọc ConfigMap/Secret: ứng dụng, kubelet, watcher, agent hay controller?
5. Khi API server gián đoạn, ứng dụng đang chạy và ứng dụng mới khởi động phản ứng khác nhau thế nào?
6. Client cần `get`, `list`, `watch` trên tài nguyên và namespace nào?
7. Khi một Pod không còn sẵn sàng, mất bao lâu để nơi chọn đích ngừng dùng nó?
8. Có bằng chứng cấu hình đã có hiệu lực, ngoài việc file hoặc tài nguyên nguồn đã đổi không?
9. Bật DiscoveryClient hoặc LoadBalancer đang giải quyết yêu cầu nào mà Service/DNS chưa đáp ứng?
10. Thành phần nào chịu trách nhiệm phục hồi nếu bỏ lỡ thông báo thay đổi cấu hình?

Nếu chưa trả lời được các câu hỏi này, nên làm rõ yêu cầu và luồng dữ liệu trước khi thêm dependency. Spring Cloud Kubernetes phát huy giá trị khi nó cung cấp đúng khả năng ứng dụng cần, trong một thiết kế có ranh giới quyền, cơ chế cập nhật và hành vi khi lỗi rõ ràng.
