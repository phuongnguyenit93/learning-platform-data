# Phân biệt client ứng dụng với HTTP DiscoveryClient

## 1. Vì sao hai khái niệm dễ bị nhầm?

Trong một ứng dụng Spring chạy trên Kubernetes, từ “client” có thể chỉ nhiều thành phần khác nhau:

- HTTP client gửi request đến API nghiệp vụ;
- DiscoveryClient tìm service hoặc instance;
- Kubernetes API client đọc resource của cluster;
- Spring Cloud LoadBalancer chọn một instance từ danh sách;
- DNS resolver phân giải tên Service.

Các thành phần này có thể xuất hiện trong cùng một đường gọi, nhưng chúng không làm cùng một việc. Nếu chỉ muốn checkout gọi orders bằng http://orders:8080, ứng dụng cần HTTP client và DNS. Nó không nhất thiết cần HTTP DiscoveryClient hoặc Kubernetes API client.

Nếu muốn ứng dụng biết những instance nào đang tồn tại, cần DiscoveryClient hoặc một cơ chế discovery khác. Nếu muốn đọc ConfigMap hay Secret trực tiếp từ Kubernetes API, cần một integration hoặc client API có danh tính và quyền RBAC. Nếu muốn chọn instance theo policy riêng, discovery và load balancing có thể cùng tham gia.

Bài này thuộc phần Kubernetes client của module SPRING_CLOUD_KUBERNETES. Mục tiêu là tách rõ nhiệm vụ, dữ liệu đầu vào, đường mạng và quyền của từng client để tránh thêm dependency hoặc RBAC không cần thiết.

## 2. Bốn lớp trong một đường gọi

~~~text
Ứng dụng checkout
      |
      | 1. Discovery: tìm tên hoặc danh sách instance
      v
DiscoveryClient / nguồn discovery
      |
      | 2. Load balancing: chọn đích nếu cần
      v
HTTP client
      |
      | 3. Gửi request qua DNS hoặc IP đã chọn
      v
orders Service hoặc orders instance
~~~

Một đường gọi thực tế có thể bỏ qua hai bước đầu:

~~~text
HTTP client
      |
      | http://orders:8080
      v
Kubernetes DNS -> Service -> Pod
~~~

Hoặc có thể dùng Kubernetes API riêng để đọc dữ liệu:

~~~text
Ứng dụng
   |
   | HTTPS + ServiceAccount token
   v
Kubernetes API -> Service/EndpointSlice/ConfigMap/Secret
~~~

HTTPS đến Kubernetes API không phải là HTTP request đến API nghiệp vụ orders. Hai đường có authentication, authorization, timeout và failure mode khác nhau.

## 3. HTTP client ứng dụng làm gì?

HTTP client là thành phần tạo và gửi request đến một HTTP server. Trong Spring, có thể dùng RestClient, WebClient hoặc client khác tùy mô hình đồng bộ, bất đồng bộ và dependency của dự án.

Nó chịu trách nhiệm cho các việc như:

- tạo method, URL, header và body;
- mở hoặc tái sử dụng connection;
- đặt connect timeout và read timeout;
- đọc status code và response body;
- ánh xạ response thành DTO;
- xử lý lỗi, retry và circuit breaker theo chính sách ứng dụng;
- truyền authentication của API nghiệp vụ.

Ví dụ client gọi một URL cấu hình:

~~~java
package com.example.checkout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersHttpClientConfiguration {

    @Bean
    RestClient ordersClient(OrdersProperties properties) {
        return RestClient.builder()
                .baseUrl(properties.baseUrl())
                .build();
    }
}
~~~

Gateway dùng client:

~~~java
package com.example.checkout;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class OrdersGateway {

    private final RestClient client;

    public OrdersGateway(
            @Qualifier("ordersClient") RestClient client) {
        this.client = client;
    }

    public String getOrder(String id) {
        return client.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .body(String.class);
    }
}
~~~

HTTP client không tự biết Pod nào đang chạy. Nếu base URL là http://orders:8080, hostname orders được resolver xử lý theo DNS của môi trường chạy. HTTP client chỉ cần gửi request tới hostname đó.

## 4. DiscoveryClient làm gì?

DiscoveryClient là abstraction để hỏi thông tin service hoặc instance từ một nguồn discovery. Nó thường trả về service ID, địa chỉ, cổng và có thể có metadata. Nó không phải HTTP client dùng để gửi request nghiệp vụ.

Một mô hình khái niệm:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("orders");
~~~

Sau khi có danh sách, một thành phần khác mới chọn instance và gửi HTTP request. Có thể là code ứng dụng, Spring Cloud LoadBalancer hoặc một integration khác.

DiscoveryClient có ý nghĩa khi ứng dụng cần:

- liệt kê service hoặc instance;
- biết host và port từng instance;
- đọc metadata để lọc hoặc ưu tiên;
- dùng một abstraction thống nhất qua nhiều môi trường;
- phản ứng với thay đổi danh sách backend.

DiscoveryClient không tự cung cấp:

- hợp đồng API nghiệp vụ;
- timeout HTTP phù hợp;
- authentication của orders;
- retry an toàn;
- serialization DTO;
- xử lý transaction;
- bảo đảm instance được chọn vẫn khỏe sau lúc discovery.

Đó vẫn là trách nhiệm của HTTP client và ứng dụng.

## 5. HTTP DiscoveryClient và Kubernetes API client

Tên “HTTP DiscoveryClient” có thể gây nhầm với “Kubernetes API client”. Cần phân biệt:

| Thành phần | Giao tiếp với | Mục tiêu | Ví dụ dữ liệu |
| --- | --- | --- | --- |
| HTTP client ứng dụng | API nghiệp vụ | Gửi request xử lý nghiệp vụ | GET order, POST payment |
| DiscoveryClient | Nguồn discovery qua abstraction | Tìm service hoặc instance | Host, port, metadata |
| Kubernetes API client | kube-apiserver | Đọc resource cluster | Service, EndpointSlice, ConfigMap |
| DNS resolver | DNS nội bộ | Phân giải hostname | orders thành địa chỉ Service |
| LoadBalancer | Danh sách instance | Chọn đích cho request | Instance phù hợp theo policy |

DiscoveryClient có thể dùng Kubernetes API phía dưới, nhưng abstraction và mục tiêu của nó vẫn là discovery. Kubernetes API client là lớp giao tiếp trực tiếp với API server và cần quan tâm đến resource path, authentication, RBAC, watch và resource version.

HTTP client ứng dụng gọi orders qua Service không cần biến thành Kubernetes API client. Ngược lại, Kubernetes API client không thay thế HTTP client gọi API nghiệp vụ.

## 6. Hai đường HTTP khác nhau

### 6.1. HTTP đến API nghiệp vụ

~~~text
checkout Pod
   |
   | HTTP: orders:8080/orders/123
   v
orders Service
   |
   v
orders Pod
~~~

Authentication có thể là token ứng dụng, mTLS hoặc cơ chế của gateway. DNS, Service và NetworkPolicy ảnh hưởng đường mạng.

### 6.2. HTTPS đến Kubernetes API

~~~text
checkout Pod
   |
   | HTTPS: Kubernetes API
   | ServiceAccount identity
   v
kube-apiserver
   |
   +--> Service
   +--> EndpointSlice
   +--> ConfigMap
   +--> Secret
~~~

Authentication và authorization dựa trên danh tính của Pod. RBAC quyết định resource và verb được phép. Lỗi 403 trên đường này là lỗi quyền Kubernetes API, không phải lỗi authorization của orders.

Hai đường có thể đồng thời tồn tại trong một process, nhưng nên có timeout, log và metric riêng để tránh chẩn đoán nhầm.

## 7. Gọi Service bằng DNS: không cần DiscoveryClient

Giả sử checkout gọi orders trong cùng namespace. Cấu hình đơn giản:

~~~yaml
orders:
  base-url: http://orders:8080
~~~

Manifest Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

HTTP client dùng base URL này. Khi Pod orders đổi IP hoặc tăng replica, checkout vẫn dùng tên orders. Kubernetes cập nhật endpoint phía sau Service.

Trong kịch bản này:

- HTTP client cần DNS và network access;
- readiness của orders ảnh hưởng endpoint;
- timeout và retry thuộc client;
- không cần list Pod qua Kubernetes API;
- không cần DiscoveryClient chỉ để tìm orders;
- không cần Spring Cloud LoadBalancer nếu Service dataplane đáp ứng nhu cầu.

Đây thường là điểm bắt đầu phù hợp cho một API nội bộ đơn giản.

## 8. Dùng DiscoveryClient khi cần instance information

Giả sử checkout phải chọn backend theo metadata vùng hoặc phiên bản. Một URL Service duy nhất có thể không biểu đạt đầy đủ thông tin này. Khi đó, discovery có thể trả danh sách instance:

~~~text
orders:
  - host: 10.10.1.12
    port: 8080
    metadata: zone=a, version=v2
  - host: 10.10.2.15
    port: 8080
    metadata: zone=b, version=v2
~~~

Ứng dụng phải giải quyết các câu hỏi:

- Danh sách này đến từ Kubernetes Service, EndpointSlice hay registry khác?
- Địa chỉ trả về có thể gọi trực tiếp từ Pod không?
- Instance có cần qua Service hoặc gateway không?
- Metadata có ổn định và được cập nhật không?
- Khi danh sách rỗng, ứng dụng trả lỗi hay dùng fallback?
- Cache danh sách trong bao lâu?
- Khi instance bị xóa ngay sau discovery, request xử lý thế nào?

Discovery không phải health check hoàn chỉnh. Instance xuất hiện trong danh sách không bảo đảm request kế tiếp thành công. Cần readiness, timeout và xử lý lỗi ở HTTP client.

## 9. Kubernetes API client và RBAC

Nếu DiscoveryClient hoặc Config integration đọc trực tiếp Kubernetes API, Pod cần ServiceAccount và quyền phù hợp. Ví dụ quyền đọc resource trong một namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-discovery-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Binding:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-discovery-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: checkout
    namespace: shop
roleRef:
  kind: Role
  name: checkout-discovery-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Đây chỉ là ví dụ kiến trúc. Resource và verb thực tế phải khớp implementation và phiên bản dependency. Không thêm quyền Secret nếu discovery chỉ đọc Service và EndpointSlice. Không dùng ClusterRoleBinding nếu Role trong namespace là đủ.

Một ứng dụng chỉ gọi http://orders:8080 có thể không cần Role này. Cấp quyền discovery cho mọi ứng dụng làm tăng bề mặt truy cập mà không cải thiện DNS.

## 10. DiscoveryClient và Spring Cloud LoadBalancer

DiscoveryClient tìm danh sách; LoadBalancer chọn từ danh sách. Hai thành phần có thể được kết hợp:

~~~text
service ID orders
        |
        v
DiscoveryClient -> danh sách instance
        |
        v
LoadBalancer -> instance được chọn
        |
        v
HTTP client -> request
~~~

LoadBalancer có thể chọn round-robin, random hoặc policy tùy chỉnh. Nhưng cần xác định địa chỉ mà discovery trả về:

- Nếu là địa chỉ Pod, client cần network route trực tiếp đến Pod.
- Nếu là ClusterIP, Service vẫn chọn Pod phía sau; policy client không trực tiếp chọn Pod.
- Nếu là gateway, policy cuối cùng có thể nằm ở gateway.
- Nếu là địa chỉ ngoài cluster, cần egress và authentication phù hợp.

Không nên thêm LoadBalancer chỉ vì đã thêm DiscoveryClient. Nếu client chỉ cần một URL Service ổn định, Service đã thực hiện phân phối ở hạ tầng.

Khi dùng HTTP client có service ID, kiểm tra bean hoặc interceptor thực sự xử lý service ID. Một hostname thông thường và một service ID không luôn có cùng semantics.

## 11. Client ứng dụng không phải client quản trị cluster

Một ứng dụng Spring có thể có hai nhóm client:

### Client nghiệp vụ

- Gọi orders, catalog hoặc payment.
- Dùng token API, mTLS hoặc credential ứng dụng.
- Quan tâm DTO, status code, timeout và retry.
- Không cần quyền Kubernetes API nếu dùng Service DNS.

### Client quản trị hoặc tích hợp Kubernetes

- Đọc Service, EndpointSlice, ConfigMap hoặc Secret.
- Dùng ServiceAccount của Pod.
- Chịu RBAC, namespace, watch và resource version.
- Cần xử lý reconnect và API errors.

Không đưa logic quản trị cluster vào client nghiệp vụ nếu chỉ cần gọi HTTP. Điều này làm code khó kiểm thử, quyền rộng hơn và failure mode phức tạp hơn.

Một lỗi HTTP 404 từ orders nghĩa là request đã đến API nhưng path hoặc dữ liệu sai. Một lỗi 403 từ kube-apiserver nghĩa là danh tính không có quyền resource. Hai lỗi cần được log và metric tách biệt.

## 12. ConfigMap, Secret và client configuration

HTTP client cần base URL, timeout và credential. Các giá trị này có thể đến từ environment hoặc ConfigMap/Secret:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-settings
  namespace: shop
data:
  ORDERS_BASE_URL: http://orders:8080
  ORDERS_TIMEOUT_MS: "800"
~~~

Credential nên ở Secret:

~~~yaml
env:
  - name: ORDERS_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: orders-client
        key: token
~~~

Đọc cấu hình qua environment không giống với đọc ConfigMap qua Kubernetes API. Với environment, Kubernetes đưa dữ liệu vào lúc container tạo; process không tự nhận giá trị mới khi ConfigMap đổi. Với API integration hoặc watcher, ứng dụng có thể nhận sự kiện nhưng phải thiết kế refresh và validation.

DiscoveryClient không thay thế Config integration. Kubernetes API client có thể được dùng bởi cả hai, nhưng resource và mục tiêu khác nhau.

## 13. Các lỗi nhầm lớp thường gặp

### Dùng Kubernetes API để gọi API nghiệp vụ

Kubernetes API biết resource của cluster, không biết hợp đồng orders trừ khi ứng dụng tự lưu metadata. Gọi orders phải dùng URL API nghiệp vụ.

### Gọi DNS nhưng thêm quyền list Pod

DNS Service không cần ứng dụng list Pod. Hãy kiểm tra Service, EndpointSlice và mạng trước khi mở RBAC.

### Discovery thành công nhưng request thất bại

Danh sách instance có thể cũ, instance có thể NotReady hoặc client không route được đến địa chỉ. Cần cache có hạn, timeout và xử lý lỗi.

### Có LoadBalancer nhưng request vẫn cùng một Pod

Connection pool và keep-alive có thể giữ request trên cùng connection. Ngoài ra LoadBalancer có thể chọn Service thay vì Pod. Xác định tầng chọn đích trước khi kết luận lỗi.

### API client bị 403 nên đổi URL orders

403 từ kube-apiserver cần phân tích RBAC. Đổi URL HTTP nghiệp vụ không sửa được quyền đọc ConfigMap hoặc EndpointSlice.

### Đọc Secret rồi ghi ra log

Đây là rủi ro bảo mật. Log chỉ nên ghi tên resource, key hoặc fingerprint an toàn khi cần chẩn đoán.

## 14. Quy trình xác minh client

Thực hiện theo câu hỏi, không trộn các đường:

1. Host của HTTP client là DNS Service, service ID hay địa chỉ instance?
2. Nếu là DNS Service, Service có selector đúng và endpoint Ready không?
3. Nếu là service ID, bean nào chuyển service ID thành instance?
4. Discovery lấy dữ liệu từ nguồn nào và có cache không?
5. Nếu gọi Kubernetes API, ServiceAccount có đúng resource và verb không?
6. Timeout của API nghiệp vụ và timeout của Kubernetes API có tách nhau không?
7. Log có phân biệt request orders với request kube-apiserver không?
8. Khi danh sách instance trống hoặc API tạm thời lỗi, fallback là gì?
9. Khi ConfigMap hoặc Secret đổi, client dùng giá trị cũ hay refresh?

Các lệnh kiểm tra dưới đây là ví dụ dành cho môi trường có quyền:

~~~bash
kubectl -n shop get service orders
kubectl -n shop get endpointslices -l kubernetes.io/service-name=orders
kubectl auth can-i list endpointslices \
  --as=system:serviceaccount:shop:checkout -n shop
~~~

Lệnh auth can-i kiểm tra quyền của ServiceAccount, không kiểm tra API nghiệp vụ. Không cần cấp quyền này cho checkout nếu ứng dụng chỉ gọi Service bằng DNS.

## 15. Bảng quyết định nhanh

| Câu hỏi | Lựa chọn phù hợp |
| --- | --- |
| Chỉ cần gọi API nội bộ bằng tên ổn định? | HTTP client + Service DNS |
| Cần danh sách service hoặc instance? | DiscoveryClient hoặc registry |
| Cần đọc resource Kubernetes trực tiếp? | Kubernetes API client/integration + RBAC |
| Cần chọn instance theo policy? | Discovery + Spring Cloud LoadBalancer |
| Cần cấu hình startup? | Environment, ConfigMap/Secret env hoặc volume |
| Cần cấu hình runtime? | Config integration, watcher và cơ chế refresh |
| Cần gọi API nghiệp vụ? | HTTP client, không dùng Kubernetes API client |
| Cần kiểm tra mạng? | DNS, Service, endpoint, NetworkPolicy và timeout |

Bảng này không quyết định thay cho kiến trúc cụ thể, nhưng giúp tránh bắt đầu từ dependency thay vì bắt đầu từ nhu cầu.

## 16. Kết luận

HTTP client ứng dụng gửi request đến API nghiệp vụ. DiscoveryClient tìm service hoặc instance. Kubernetes API client đọc resource cluster. DNS phân giải tên Service. Spring Cloud LoadBalancer chọn instance nếu ứng dụng cần kiểm soát lựa chọn ở phía client.

Một ứng dụng checkout chỉ gọi http://orders:8080 thường cần HTTP client, DNS và quyền mạng; không nhất thiết cần DiscoveryClient, Kubernetes API client hoặc LoadBalancer. Khi cần discovery, cấu hình trực tiếp hoặc watcher, hãy bổ sung integration tương ứng, giới hạn RBAC và tách timeout, log cùng metric của từng đường.

Phân biệt đúng các client làm dự án Spring Cloud Kubernetes nhỏ hơn, an toàn hơn và dễ chẩn đoán hơn.
