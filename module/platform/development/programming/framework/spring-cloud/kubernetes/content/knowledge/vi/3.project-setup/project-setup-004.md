# Phân biệt phụ thuộc khám phá dịch vụ, cấu hình và cân bằng tải

## 1. Ba nhu cầu thường bị trộn lẫn

Khi đưa ứng dụng Spring lên Kubernetes, một câu hỏi dễ xuất hiện là: “Có cần thêm Spring Cloud Kubernetes hay không?”. Câu hỏi này quá rộng. Cần tách thành ba nhu cầu khác nhau:

1. Ứng dụng cần biết dịch vụ hoặc instance nào đang tồn tại.
2. Ứng dụng cần đọc cấu hình từ môi trường triển khai.
3. Ứng dụng cần chọn một instance để gửi request.

Ba nhu cầu có thể cùng xuất hiện trong một hệ thống, nhưng không phải lúc nào cũng cần cùng một thư viện hoặc cùng một quyền Kubernetes API.

- **Khám phá dịch vụ** trả lời nơi tìm service hoặc instance.
- **Cấu hình** trả lời ứng dụng dùng giá trị vận hành nào.
- **Cân bằng tải** trả lời request cụ thể được chọn đến instance nào.

Kubernetes đã cung cấp Service và DNS cho nhiều đường gọi nội bộ. Vì vậy, một ứng dụng Spring chỉ gọi http://orders:8080 thường không cần DiscoveryClient hay Spring Cloud LoadBalancer chỉ để tên orders được phân giải. Tương tự, ConfigMap được mount thành file hoặc environment không nhất thiết yêu cầu ứng dụng tự gọi Kubernetes API.

Mục tiêu của bài thuộc phần Thiết lập dự án là giúp chọn dependency theo nhu cầu thật, tách dependency bắt buộc khỏi dependency tùy chọn và tránh cấp quyền RBAC rộng hơn cần thiết.

## 2. Mô hình tổng quan

~~~text
                    Ứng dụng Spring
                           |
       +-------------------+-------------------+
       |                   |                   |
       v                   v                   v
  Discovery           Configuration        Load balancing
  Tìm service/        Đọc giá trị           Chọn instance
  instance            vận hành              cho request
       |                   |                   |
       v                   v                   v
Kubernetes API       env/volume/API       danh sách instance
Service, Endpoint    ConfigMap, Secret    + policy chọn
                           |
                           v
                    Cách nạp lại runtime
~~~

Các nhánh có thể độc lập:

- Gọi Service bằng DNS chỉ dùng đường mạng và không nhất thiết đi qua Kubernetes API.
- Đọc cấu hình qua environment chỉ cần Kubernetes đưa dữ liệu vào Pod trước khi process chạy.
- Cân bằng tải phía client chỉ có ý nghĩa nếu client có nguồn instance và chính sách chọn rõ ràng.

Một dependency nên được thêm vì một khả năng cụ thể mà ứng dụng cần, không phải vì tên công nghệ trong mô tả hạ tầng.

## 3. Khám phá dịch vụ là gì?

### 3.1. Khám phá bằng Kubernetes Service và DNS

Kubernetes Service cung cấp tên ổn định cho một nhóm Pod. Client trong cùng cluster có thể dùng tên Service theo namespace:

~~~text
http://orders:8080
http://orders.shop:8080
http://orders.shop.svc.cluster-domain:8080
~~~

Tên đầy đủ phụ thuộc cluster-domain thực tế. Service selector tìm Pod theo label, còn EndpointSlice biểu diễn endpoint. Khi Pod đổi IP hoặc replica thay đổi, client vẫn dùng tên Service.

Trong mô hình này, Kubernetes dataplane thực hiện việc chuyển traffic từ ClusterIP đến backend. HTTP client không cần liệt kê Pod và không cần có quyền list hoặc watch Pod chỉ để gọi API.

Đây là lựa chọn đơn giản khi:

- API đích có một tên ổn định;
- các replica có hợp đồng xử lý tương đương;
- client không cần metadata của từng instance;
- cách phân phối kết nối của Service đáp ứng yêu cầu;
- không cần chọn instance theo dữ liệu nghiệp vụ.

### 3.2. DiscoveryClient

DiscoveryClient cung cấp một mô hình để ứng dụng hỏi danh sách service hoặc instance thay vì chỉ gọi một URL cố định. Ứng dụng có thể dùng service ID, metadata hoặc địa chỉ instance theo cách abstraction của hệ sinh thái Spring Cloud.

DiscoveryClient có ý nghĩa khi ứng dụng thật sự cần:

- liệt kê service theo tên hoặc thuộc tính;
- biết nhiều instance và metadata liên quan;
- chọn hoặc loại instance ở lớp ứng dụng;
- tích hợp với một cơ chế discovery thống nhất giữa nhiều môi trường;
- xử lý sự thay đổi danh sách instance ngoài khả năng mà URL Service cung cấp.

Nếu ứng dụng chỉ gọi một Service bằng DNS, DiscoveryClient có thể là một lớp phụ không cần thiết. Bật discovery không tự làm API nghiệp vụ tốt hơn và cũng không thay thế timeout, retry, authentication hay xử lý lỗi.

### 3.3. Discovery dựa trên Kubernetes API

Một integration discovery có thể đọc Service, EndpointSlice hoặc resource liên quan qua Kubernetes API. Tùy implementation và phiên bản dependency, resource cụ thể có thể khác. Cần kiểm tra tài liệu và behavior của phiên bản dự án trước khi viết RBAC.

Khi discovery gọi API, ứng dụng cần:

- ServiceAccount đúng;
- quyền đọc resource đúng;
- namespace hoặc phạm vi cluster đúng;
- xử lý lỗi API, reconnect và thay đổi danh sách;
- chiến lược cache nếu API tạm thời không truy cập được.

Quyền API của discovery không đồng nghĩa với quyền gọi API nghiệp vụ. Một ứng dụng có thể được phép đọc Service nhưng vẫn không được phép gọi HTTP đến Service nếu NetworkPolicy hoặc authentication của API đích chặn.

## 4. Cấu hình là một nhu cầu khác

### 4.1. Cấu hình tĩnh, environment và volume

Ứng dụng Spring cần các giá trị như URL dependency, timeout, cờ tính năng và thông tin kết nối. Kubernetes có thể đưa chúng vào Pod qua:

- biến môi trường;
- volume từ ConfigMap hoặc Secret;
- một file được đóng gói trong image;
- một hệ thống cấu hình bên ngoài;
- integration đọc Kubernetes API.

Ví dụ đưa ConfigMap vào environment:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-settings
  namespace: shop
data:
  ORDERS_BASE_URL: http://orders:8080
  CHECKOUT_TIMEOUT_MS: "800"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: shop
spec:
  template:
    spec:
      containers:
        - name: checkout
          image: registry.example.com/checkout:1.0.0
          envFrom:
            - configMapRef:
                name: checkout-settings
~~~

Với mô hình này, Pod nhận giá trị khi container được tạo. Một thay đổi ConfigMap không tự sửa environment của process đang chạy. Muốn giá trị mới có hiệu lực, thường cần rollout hoặc cơ chế nạp lại riêng.

### 4.2. Spring Cloud Kubernetes Config

Spring Cloud Kubernetes Config có thể giúp ứng dụng đọc cấu hình từ ConfigMap hoặc Secret theo integration được chọn. Ưu điểm là ứng dụng có mô hình truy cập cấu hình gần với môi trường Kubernetes. Đổi lại, ứng dụng phải có dependency, namespace, tên resource và quyền API phù hợp nếu đọc trực tiếp từ Kubernetes API.

Cấu hình minh họa ở mức khái niệm:

~~~yaml
spring:
  application:
    name: checkout
  cloud:
    kubernetes:
      config:
        enabled: true
        name: checkout-settings
~~~

Tên property và starter cần khớp với phiên bản dependency của dự án. Ví dụ này dùng để minh họa quyết định kiến trúc, không phải thay thế việc kiểm tra tài liệu phiên bản.

Khi chọn Config integration, cần quyết định:

- cấu hình được đọc lúc startup hay có thể đổi runtime;
- Secret có được phép đưa vào log hoặc actuator không;
- cấu hình sai làm ứng dụng fail startup hay giữ giá trị cũ;
- một Pod có thể dùng giá trị cũ trong bao lâu;
- cách rollback khi ConfigMap mới có lỗi.

### 4.3. Configuration Watcher và reload

Configuration Watcher theo dõi thay đổi resource và kích hoạt cách phản ứng đã thiết kế. Watcher không tự bảo đảm mọi bean Spring được cập nhật an toàn. Việc áp dụng cấu hình cần xét đến:

- bean có giữ giá trị cũ trong memory không;
- request đang chạy dùng giá trị cũ hay mới;
- thay đổi có cần refresh scope hoặc restart không;
- cấu hình mới có được validate trước khi áp dụng không;
- nếu API Kubernetes mất kết nối thì ứng dụng dùng giá trị nào.

Một ứng dụng có thể dùng ConfigMap để cấu hình lúc startup nhưng không cần watcher. Nếu cấu hình thay đổi không thường xuyên, rollout có kiểm soát có thể dễ vận hành hơn reload runtime.

## 5. Cân bằng tải là quyết định chọn instance

### 5.1. Cân bằng tải ở Service

Khi client gọi ClusterIP, Kubernetes Service chuyển traffic đến backend theo cơ chế của cluster. Đây là một hình thức cân bằng tải ở hạ tầng. Client chỉ biết một địa chỉ ổn định.

Ưu điểm:

- ứng dụng đơn giản;
- không cần đọc Kubernetes API để tìm Pod;
- thay đổi replica được xử lý ở hạ tầng;
- quyền API của client có thể nhỏ hơn.

Giới hạn:

- client không trực tiếp chọn Pod theo metadata;
- phân phối request có thể phụ thuộc kết nối TCP và keep-alive;
- không tự hiểu quy tắc theo user, header, tenant hoặc trọng số nghiệp vụ;
- không thay thế retry, timeout và circuit breaker.

Nhiều request HTTP có thể đi trên một connection lâu dài. Vì vậy, tăng số replica không bảo đảm mỗi Pod nhận đúng một phần số request.

### 5.2. Spring Cloud LoadBalancer

Spring Cloud LoadBalancer cung cấp một lớp chọn instance phía client. Nó cần một nguồn danh sách instance và một chính sách chọn, chẳng hạn round-robin hoặc logic tùy chỉnh.

LoadBalancer có ý nghĩa khi:

- client cần chọn instance trước khi mở request;
- muốn áp dụng quy tắc chọn ở phía ứng dụng;
- discovery trả về địa chỉ instance mà client có thể gọi trực tiếp;
- cần kết hợp metadata với chính sách chọn;
- môi trường có nhiều nguồn discovery nhưng muốn dùng một abstraction.

Chỉ thêm annotation hoặc starter LoadBalancer không tạo ra danh sách instance đúng. Cần biết client đang nhận:

1. địa chỉ Pod;
2. địa chỉ Service;
3. địa chỉ gateway;
4. một danh sách đã cache;
5. một danh sách từ nguồn discovery khác.

Nếu LoadBalancer chọn một địa chỉ Service rồi Service lại chọn Pod, quy tắc chọn phía client không nhất thiết kiểm soát Pod cuối cùng. Điều này có thể vẫn hữu ích nếu LoadBalancer chọn giữa nhiều Service hoặc vùng, nhưng không nên nhầm với cân bằng tải trực tiếp từng Pod.

### 5.3. Service ID và URL cố định

Một HTTP client gọi URL cố định như http://orders:8080 có semantics khác với client gọi service ID orders thông qua LoadBalancer. URL cố định dựa trên DNS hoặc resolver thông thường. Service ID cần một interceptor, client integration hoặc factory biết cách biến service ID thành instance.

Nếu dùng LoadBalancer, phải kiểm tra:

- client nào được tạo;
- bean nào có annotation hoặc interceptor;
- URL có host là service ID hay hostname thật;
- danh sách instance được cung cấp từ đâu;
- timeout và retry nằm ở lớp nào;
- log có cho thấy instance cuối cùng được chọn không.

Không nên vừa cấu hình DNS Service vừa kỳ vọng LoadBalancer đang chọn từng Pod nếu chưa có bằng chứng về nguồn instance.

## 6. Bảng phân biệt ba nhóm phụ thuộc

| Nhu cầu | Câu hỏi chính | Cơ chế có thể dùng | Kubernetes API/RBAC |
| --- | --- | --- | --- |
| Gọi API nội bộ đơn giản | Tên Service có ổn định không? | Service, DNS, HTTP client | Không nhất thiết cần |
| Liệt kê service | Ứng dụng cần biết service nào tồn tại? | DiscoveryClient | Thường cần quyền đọc resource |
| Biết từng instance | Cần địa chỉ hoặc metadata từng backend? | DiscoveryClient hoặc registry khác | Cần quyền và xử lý thay đổi |
| Đưa giá trị vào startup | Giá trị có thể cố định trong một lần chạy? | ConfigMap/Secret env hoặc volume | Có thể không cần app gọi API |
| Đọc cấu hình trực tiếp | Ứng dụng cần truy cập resource khi chạy? | Config integration | Cần quyền get/list tùy cách dùng |
| Cập nhật cấu hình runtime | Thay đổi phải có hiệu lực khi Pod không restart? | Watcher và cơ chế reload | Cần watch và reconnect |
| Chọn backend phía client | Client cần quy tắc chọn instance? | Spring Cloud LoadBalancer | Phụ thuộc nguồn instance |
| Chuyển traffic theo hạ tầng | Chỉ cần phân phối qua Service? | ClusterIP và dataplane | Không cần discovery trong app |

Bảng này là khung quyết định. Một dự án có thể cần nhiều dòng, nhưng mỗi dòng phải có lý do và cách kiểm chứng riêng.

## 7. Dependency tối thiểu theo kịch bản

### Kịch bản A: Gọi Service bằng DNS

Yêu cầu: checkout gọi orders trong cùng cluster; replica orders tương đương; không cần biết Pod.

Thiết kế:

~~~yaml
orders:
  base-url: http://orders:8080
~~~

Ứng dụng dùng HTTP client thông thường. Có thể dùng RestClient, WebClient hoặc thư viện khác phù hợp. Không cần DiscoveryClient chỉ để phân giải orders. Không cần Spring Cloud LoadBalancer nếu Service đã cung cấp điểm truy cập và cách phân phối phù hợp.

Cần tập trung vào timeout, status code, retry an toàn, authentication và quan sát.

### Kịch bản B: Chọn instance theo metadata

Yêu cầu: client chỉ gọi instance có label hoặc metadata phù hợp với vùng xử lý; danh sách backend thay đổi runtime.

Thiết kế cần:

1. Nguồn discovery trả về instance và metadata.
2. Chính sách loại bỏ hoặc ưu tiên instance.
3. LoadBalancer chọn instance cho request.
4. Cache và thời hạn dữ liệu discovery.
5. Cách phản ứng khi không còn instance phù hợp.

Trong kịch bản này, DiscoveryClient và Spring Cloud LoadBalancer có thể cùng cần thiết, nhưng phải xác định discovery trả về địa chỉ nào và client có thể kết nối đến địa chỉ đó hay không.

### Kịch bản C: Cấu hình lúc startup

Yêu cầu: timeout và cờ tính năng được đặt khi Pod tạo; đổi cấu hình sẽ rollout lại.

Thiết kế có thể dùng ConfigMap và Secret qua environment hoặc volume. Ứng dụng không cần Configuration Watcher nếu rollout là chính sách cập nhật.

Ưu điểm là vòng đời đơn giản và dễ kiểm toán. Hạn chế là thay đổi không có hiệu lực ngay trong process cũ.

### Kịch bản D: Cấu hình runtime

Yêu cầu: thay đổi một số cờ tính năng phải có hiệu lực mà không restart toàn bộ Pod.

Thiết kế cần:

- cơ chế nhận thay đổi;
- validation;
- lưu giá trị hiện hành;
- đồng bộ giữa các replica;
- hành vi khi watcher mất kết nối;
- rollback khi cấu hình không hợp lệ;
- metric hoặc log cho phiên bản cấu hình.

Configuration Watcher có thể là một phần của thiết kế, nhưng không tự giải quyết việc thread đang dùng giá trị cũ hoặc bean không hỗ trợ refresh.

## 8. Quan hệ giữa dependency và RBAC

Một dependency có thể làm thay đổi quyền API của Pod. Cần lập bảng quyền trước khi triển khai:

| Thành phần | Resource có thể cần | Verb có thể cần | Phạm vi cần kiểm tra |
| --- | --- | --- | --- |
| DNS/HTTP client gọi Service | Không cần đọc resource để gọi | Không cần | NetworkPolicy và API auth |
| DiscoveryClient | Service, EndpointSlice hoặc resource tương ứng | get, list, watch tùy implementation | Namespace hoặc cluster |
| Config integration | ConfigMap, Secret | get, list, watch tùy implementation | Namespace |
| Configuration Watcher | Resource cấu hình | watch và quyền đọc liên quan | Namespace hoặc phạm vi cấu hình |
| LoadBalancer | Danh sách instance từ discovery | Phụ thuộc discovery | Cùng nguồn instance |

ServiceAccount chỉ là danh tính. Role hoặc ClusterRole mới mô tả quyền; RoleBinding hoặc ClusterRoleBinding mới gắn quyền vào danh tính.

Nguyên tắc tối thiểu:

- Không cấp list/watch Pod chỉ vì ứng dụng gọi Service.
- Không cấp quyền đọc Secret nếu ứng dụng chỉ cần ConfigMap.
- Không dùng ClusterRoleBinding khi một Role trong namespace là đủ.
- Không thêm create, update, patch hoặc delete cho component chỉ đọc.
- Kiểm tra quyền của dependency thật sự đang bật, không cấp quyền cho mọi tính năng có thể bật trong tương lai.

RBAC không thay thế NetworkPolicy. Có quyền đọc Service không bảo đảm có thể mở TCP connection tới backend. Ngược lại, có network access không đồng nghĩa được đọc resource qua API.

## 9. Cấu hình dự án theo lớp

Một dự án nên tách dependency thành các lớp có thể giải thích:

### Lớp ứng dụng

Đây là HTTP client, serialization, timeout và xử lý lỗi. Lớp này cần tồn tại dù endpoint được định địa chỉ bằng DNS hay discovery.

### Lớp discovery

Chỉ thêm khi ứng dụng cần service hoặc instance information. Ghi rõ service ID nào được dùng, nguồn instance là gì và behavior khi danh sách rỗng.

### Lớp configuration

Chọn một phương thức chính cho từng loại cấu hình. Secret nhạy cảm cần chính sách log, quyền đọc và rotation. ConfigMap không nhạy cảm nhưng vẫn cần kiểm soát thay đổi.

### Lớp load balancing

Chỉ thêm khi cần chọn instance phía client hoặc policy mà Service không đáp ứng. Xác định load balancing xảy ra một lần cho mỗi request, mỗi connection hay ở một tầng khác.

### Lớp reload hoặc watcher

Chỉ thêm khi runtime update mang lại giá trị đủ lớn so với rollout. Xác định bean, cache và request nào bị ảnh hưởng.

Tách lớp giúp một lỗi được khoanh vùng: lỗi DNS không phải tự động là lỗi discovery; lỗi 403 từ Kubernetes API không phải lỗi HTTP API nghiệp vụ; cấu hình cũ không phải tự động là lỗi LoadBalancer.

## 10. Một ví dụ Spring minh họa

Giả sử checkout gọi orders. Cách đơn giản:

~~~yaml
orders:
  base-url: http://orders:8080
~~~

Trong ứng dụng, HTTP client dùng base URL này. Khi chạy trong Kubernetes, environment có thể truyền URL Service:

~~~yaml
env:
  - name: ORDERS_BASE_URL
    value: http://orders.shop:8080
~~~

Không gắn LoadBalancer nếu base URL là hostname mà DNS đã xử lý. Nếu chuyển sang mô hình service ID, phải thay đổi cách tạo client và cấu hình discovery/load balancing một cách có chủ đích.

Khi thêm ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-settings
  namespace: shop
data:
  ORDERS_BASE_URL: http://orders.shop:8080
  ORDERS_TIMEOUT_MS: "800"
~~~

Có thể inject vào Pod bằng envFrom. Nếu muốn cấu hình được đọc trực tiếp và theo dõi thay đổi qua Kubernetes API, khi đó mới thêm Config integration hoặc watcher cùng RBAC tương ứng.

Một hệ thống hoàn chỉnh có thể có cả ba nhóm, nhưng cần giữ các câu hỏi độc lập:

- Địa chỉ orders lấy từ đâu?
- Giá trị timeout lấy từ đâu?
- Instance cụ thể được chọn ở tầng nào?

## 11. Những ngộ nhận thường gặp

### “Dùng Kubernetes thì luôn phải dùng DiscoveryClient”

Không. Service và DNS đã cung cấp tên ổn định cho nhiều API nội bộ. Discovery chỉ cần khi ứng dụng cần thông tin discovery cụ thể.

### “Có DiscoveryClient thì tự động cân bằng tải”

Không. Discovery cung cấp thông tin; LoadBalancer áp dụng chính sách chọn. Hai việc có thể nằm trong cùng một integration nhưng vẫn là hai trách nhiệm.

### “Có LoadBalancer thì không cần Service”

Không nhất thiết. LoadBalancer cần nguồn instance và đường kết nối. Service có thể vẫn là lớp truy cập, hoặc discovery có thể trả địa chỉ riêng. Cần biết chính xác mô hình đang dùng.

### “ConfigMap thay đổi thì environment của Java tự đổi”

Không. Environment của process đã khởi chạy không tự cập nhật. Cần rollout, volume với cơ chế đọc lại hoặc integration reload.

### “Config Watcher làm mọi bean tự refresh”

Không. Watcher nhận sự kiện; ứng dụng phải có cơ chế áp dụng dữ liệu mới và xử lý an toàn.

### “Cấp quyền read mọi resource để discovery chạy”

Không nên. Xác định resource và verb mà implementation cần, giới hạn namespace nếu có thể và kiểm tra bằng ServiceAccount thực tế.

### “Service đã cân bằng tải nên không cần timeout”

Không. Service định tuyến traffic; HTTP client vẫn cần timeout, xử lý lỗi và retry có điều kiện.

## 12. Quy trình ra quyết định

Trước khi thêm dependency, trả lời lần lượt:

1. Client có chỉ cần một địa chỉ ổn định không? Nếu có, bắt đầu bằng Service và DNS.
2. Client có cần liệt kê service hoặc instance không? Nếu không, bỏ qua discovery.
3. Cấu hình có cần API access không, hay env/volume đủ? Chọn cách ít trạng thái hơn nếu phù hợp.
4. Thay đổi cấu hình có cần hiệu lực khi process đang chạy không? Nếu không, rollout có kiểm soát có thể đủ.
5. Client có cần chọn instance theo metadata hoặc policy riêng không? Nếu không, không thêm client-side load balancing.
6. Nếu cần LoadBalancer, nguồn instance là gì và địa chỉ có thể gọi được không?
7. Dependency mới cần RBAC verb nào, resource nào và namespace nào?
8. Khi API Kubernetes hoặc discovery tạm thời lỗi, ứng dụng dùng cache, giá trị cũ, retry hay fail startup?
9. Khi không có instance hoặc cấu hình mới sai, hành vi quan sát và rollback là gì?

Một decision record ngắn có thể ghi:

~~~text
Gọi orders: Service DNS, không dùng DiscoveryClient.
Cấu hình timeout: ConfigMap env, cập nhật qua rollout.
Dữ liệu nhạy cảm: Secret volume, không log giá trị.
Client-side selection: không cần.
RBAC của ứng dụng: không đọc Kubernetes API cho đường gọi orders.
~~~

Tài liệu như vậy giúp dependency trong build file, manifest và RBAC có lý do nhất quán.

## 13. Kiểm tra sau khi thiết lập

Không chạy build hoặc test trong bài này; các bước dưới đây là checklist để người học dùng trong môi trường phù hợp:

- Kiểm tra URL thực tế ứng dụng nhận được khi chạy trong Pod.
- Xác định host là DNS Service hay service ID cho LoadBalancer.
- Kiểm tra Service selector và endpoint khi gọi API.
- Nếu dùng discovery, xác định danh sách instance và metadata được trả về.
- Nếu dùng ConfigMap hoặc Secret, xác định dữ liệu đến qua env, volume hay Kubernetes API.
- Nếu dùng watcher, kiểm tra sự kiện thay đổi, reconnect và version cấu hình.
- Kiểm tra ServiceAccount và quyền tối thiểu theo đúng resource, verb, namespace.
- Quan sát timeout, retry, số connection và instance được chọn.
- Kiểm tra behavior khi backend không sẵn sàng hoặc danh sách instance rỗng.

Mỗi kiểm tra nên trả lời một câu hỏi kiến trúc cụ thể. Không thêm dependency hoặc RBAC chỉ để làm mất một lỗi mà chưa xác định lớp nguyên nhân.

## 14. Kết luận

Khám phá dịch vụ, cấu hình và cân bằng tải là ba nhu cầu liên quan nhưng khác nhau. Service và DNS thường đủ cho một client gọi API nội bộ bằng tên ổn định. DiscoveryClient phù hợp khi ứng dụng cần biết service hoặc instance. ConfigMap, Secret và Config integration cung cấp các lựa chọn đưa cấu hình vào ứng dụng; Configuration Watcher chỉ cần khi thay đổi runtime thật sự cần thiết. Spring Cloud LoadBalancer phù hợp khi client phải chọn instance theo chính sách riêng.

Chọn dependency theo nhu cầu làm giảm mã tích hợp, quyền RBAC và trạng thái vận hành. Trước khi bật một starter, hãy xác định địa chỉ được tìm ở đâu, cấu hình được nạp bằng cách nào và instance được chọn ở tầng nào. Khi ba câu hỏi này có câu trả lời rõ, thiết lập dự án Spring Cloud Kubernetes sẽ dễ kiểm tra và dễ chẩn đoán hơn.
