# Lấy danh sách service ID và các ServiceInstance

## 1. Service ID và ServiceInstance là gì?

Trong Spring Cloud, discovery thường được trình bày qua hai khái niệm:

- **Service ID** là tên logic của một dịch vụ, chẳng hạn orders hoặc catalog.
- **ServiceInstance** là một địa chỉ có thể gọi của một instance thuộc service ID đó, thường gồm host, port, scheme, metadata và thông tin bảo mật tùy implementation.

Service ID giúp ứng dụng không phải ghi cứng host của backend. ServiceInstance cung cấp dữ liệu để một client hoặc LoadBalancer chọn đích cụ thể.

Khi dùng Kubernetes, cần nhớ rằng service ID trong abstraction Spring không tự động đồng nghĩa với:

- tên Deployment;
- tên Pod;
- tên namespace;
- tên DNS đầy đủ;
- địa chỉ mà client có thể kết nối trực tiếp.

Một integration có thể ánh xạ service ID đến Kubernetes Service, EndpointSlice hoặc một nguồn discovery khác. Vì vậy, trước khi dùng danh sách instance, phải biết dữ liệu được tạo từ resource nào và địa chỉ trả về thuộc tầng nào.

## 2. Đường đi của discovery

Một mô hình tổng quát:

~~~text
Ứng dụng Spring
      |
      | getServices() hoặc getInstances(serviceId)
      v
DiscoveryClient abstraction
      |
      +--> Kubernetes Service / EndpointSlice
      |       hoặc registry khác
      |
      v
ServiceInstance list
      |
      v
Spring Cloud LoadBalancer hoặc code ứng dụng
      |
      v
HTTP client gửi request
~~~

Nếu chỉ gọi một Kubernetes Service qua DNS, đường đi có thể ngắn hơn:

~~~text
HTTP client -> orders.shop.svc.cluster-domain -> ClusterIP -> Pod
~~~

Trong trường hợp đó, ứng dụng không cần lấy danh sách service ID hoặc instance để gọi API đơn giản. Discovery API chỉ cần khi ứng dụng thật sự cần thông tin danh sách.

## 3. DiscoveryClient cung cấp những thao tác nào?

Ở mức abstraction, DiscoveryClient thường có hai loại thao tác:

~~~java
List<String> serviceIds = discoveryClient.getServices();
List<ServiceInstance> instances =
        discoveryClient.getInstances("orders");
~~~

Tên method và interface cụ thể phụ thuộc dependency Spring Cloud. Ý nghĩa cần giữ:

- getServices trả về các service ID mà discovery source biết;
- getInstances nhận một service ID và trả các instance tương ứng;
- danh sách có thể rỗng;
- dữ liệu có thể có độ trễ hoặc cache;
- response không bảo đảm instance sẽ còn sẵn sàng ngay lúc request được gửi.

Không nên gọi getServices trên mỗi HTTP request để chọn backend. Discovery data nên được cache hoặc để LoadBalancer quản lý theo behavior của integration.

## 4. Service ID không phải hostname

Giả sử discovery trả service ID orders. Có ít nhất ba cách ánh xạ:

| Mô hình | Service ID orders được biến thành | Tầng chọn backend |
| --- | --- | --- |
| DNS Service | orders:8080 | Kubernetes Service |
| Instance discovery | host và port từng endpoint | Client hoặc LoadBalancer |
| Gateway discovery | URL gateway và metadata route | Gateway hoặc client |

Nếu HTTP client nhận URL http://orders:8080, orders là hostname được DNS phân giải. Nếu client nhận service ID orders, cần một resolver, interceptor hoặc LoadBalancer biết cách chuyển service ID thành ServiceInstance.

Không đổi hostname thành service ID chỉ bằng cách sửa chuỗi URL. Phải có integration xử lý service ID.

## 5. Cấu trúc của ServiceInstance

Một ServiceInstance thường có các dữ liệu khái niệm:

~~~text
serviceId: orders
host: 10.10.1.12
port: 8080
scheme: http
secure: false
metadata:
  zone: a
  version: v2
~~~

Các field thường được dùng:

- serviceId: tên logic của service;
- host: hostname hoặc IP của instance;
- port: cổng đích;
- scheme: http, https hoặc scheme được hỗ trợ;
- secure: tín hiệu về kết nối bảo mật;
- metadata: nhãn phục vụ policy chọn.

Không phải implementation nào cũng điền tất cả field giống nhau. Host có thể là địa chỉ Pod, địa chỉ Service, hostname gateway hoặc tên DNS. Metadata có thể không có hoặc không đồng nhất.

Trước khi dùng host và port để tạo URL, kiểm tra:

- client có route được tới host không;
- host có tồn tại trong network của Pod không;
- port có phải cổng client gọi không;
- scheme có khớp TLS không;
- metadata có được tin cậy cho policy không.

## 6. Kubernetes ánh xạ instance như thế nào?

Kubernetes có nhiều resource liên quan:

- Service cung cấp tên và cổng ổn định;
- EndpointSlice biểu diễn địa chỉ endpoint;
- Pod có IP và label;
- readiness ảnh hưởng endpoint sẵn sàng;
- namespace tạo scope cho Service và endpoint.

Một discovery integration có thể chọn Service làm đơn vị service ID và dùng endpoint phía sau để tạo ServiceInstance. Cách ánh xạ cụ thể phụ thuộc implementation và cấu hình.

~~~text
Service orders
  namespace: shop
  port: 8080
       |
       v
EndpointSlice
  10.10.1.12:8080 Ready
  10.10.2.18:8080 Ready
       |
       v
ServiceInstance list for orders
~~~

Nếu integration chỉ trả ClusterIP, hai instance Pod không nhất thiết xuất hiện thành hai ServiceInstance. Nếu integration trả endpoint trực tiếp, client cần có network path đến địa chỉ đó. Đừng suy ra behavior từ tên class; kiểm tra dữ liệu thực tế và tài liệu của version dependency.

## 7. Lấy danh sách service ID

Một use case có thể hiển thị danh sách service mà discovery source biết:

~~~java
@Service
public class ServiceCatalog {

    private final DiscoveryClient discoveryClient;

    public ServiceCatalog(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> serviceIds() {
        return discoveryClient.getServices();
    }
}
~~~

Không nên expose danh sách này công khai nếu nó chứa topology hoặc tên nội bộ. Nếu dùng cho diagnostics, bảo vệ endpoint và lọc dữ liệu.

Danh sách service ID có thể:

- không bao gồm service ngoài namespace;
- bao gồm service không có endpoint Ready;
- thay đổi theo RBAC;
- thay đổi theo label hoặc filter của integration;
- rỗng khi API server hoặc discovery source chưa sẵn sàng.

getServices không phải health check. Có service ID trong danh sách không bảo đảm service có thể phục vụ request.

## 8. Lấy ServiceInstance theo service ID

Ví dụ gateway lấy instance của orders:

~~~java
@Service
public class OrdersInstanceLookup {

    private final DiscoveryClient discoveryClient;

    public OrdersInstanceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findOrders() {
        return discoveryClient.getInstances("orders");
    }
}
~~~

Một lớp ứng dụng không nên tự chọn instance bằng cách lấy phần tử đầu tiên:

~~~java
// Không nên dùng như policy production
return discoveryClient.getInstances("orders").get(0);
~~~

Danh sách có thể rỗng, thứ tự không phải chính sách cân bằng tải và instance đầu tiên không nhất thiết khỏe hoặc phù hợp vùng. Dùng Spring Cloud LoadBalancer hoặc policy rõ ràng nếu cần chọn.

Nếu chỉ cần gọi API orders, cách đơn giản hơn có thể là base URL Service DNS. Discovery list chỉ nên được dùng khi metadata hoặc instance-level routing là yêu cầu thật.

## 9. Kết hợp với Spring Cloud LoadBalancer

Mô hình thường gặp:

~~~text
service ID orders
       |
       v
DiscoveryClient: [instance A, instance B, instance C]
       |
       v
LoadBalancer chọn một instance
       |
       v
HTTP client gọi instance
~~~

LoadBalancer chịu trách nhiệm policy chọn và có thể có cache. DiscoveryClient chịu trách nhiệm cung cấp dữ liệu. Cần tránh trộn hai lớp:

- discovery không bảo đảm retry request nghiệp vụ;
- LoadBalancer không tạo ra instance nếu discovery rỗng;
- HTTP client vẫn cần timeout;
- instance được chọn có thể mất sau khi chọn;
- connection pool có thể giữ request trên cùng connection.

Nếu discovery trả ClusterIP thay vì Pod endpoint, LoadBalancer có thể chọn ClusterIP; Kubernetes Service vẫn chọn Pod phía sau. Khi đó, client-side policy không kiểm soát trực tiếp Pod cuối cùng.

## 10. Namespace và service ID

Một service ID có thể bị trùng giữa các namespace:

~~~text
orders trong shop
orders trong staging
orders trong payments
~~~

Nếu discovery client chỉ nhận orders mà không có namespace context, cần biết integration xử lý scope thế nào. Có thể:

- chỉ discovery trong namespace hiện tại;
- service ID được mở rộng bằng namespace;
- cấu hình danh sách namespace;
- discovery source đã lọc theo label;
- ứng dụng tự đưa namespace vào metadata.

Không tự nối orders.shop thành service ID mới nếu integration không hỗ trợ. Với DNS, orders.shop là hostname hợp lệ trong mô hình cluster; với DiscoveryClient, service ID là dữ liệu logic theo abstraction.

Một lựa chọn an toàn là giới hạn discovery trong namespace workload và dùng tên Service rõ ràng. Cross-namespace discovery chỉ cần khi có yêu cầu kiến trúc được ghi rõ.

## 11. RBAC cho getServices và getInstances

Nếu discovery dựa trên Kubernetes API, danh sách service ID và instance yêu cầu quyền đọc resource. Resource cụ thể phụ thuộc integration, nhưng mô hình quyền có thể gồm Service và EndpointSlice:

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

Binding vào ServiceAccount:

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

Không cấp quyền đọc Secret nếu discovery chỉ cần Service và EndpointSlice. Không cấp list Pod chỉ vì muốn gọi Service qua DNS. Kiểm tra implementation trước khi chốt rule.

## 12. Readiness và danh sách instance

Discovery data cần được liên hệ với readiness:

~~~text
Pod process chạy
      |
      v
readiness probe
      |
      +--> NotReady: không nên là endpoint phục vụ thông thường
      |
      +--> Ready: có thể xuất hiện trong endpoint discovery
~~~

Có độ trễ giữa probe, EndpointSlice, cache discovery và request client. Một instance có thể được trả về ngay trước khi bị đánh dấu NotReady; client vẫn phải xử lý timeout và lỗi kết nối.

Discovery list không thay thế health check. Không gọi health endpoint của mọi instance trên mỗi getInstances nếu việc đó tạo tải và làm discovery chậm. Dùng tín hiệu Kubernetes cùng cơ chế quan sát phù hợp.

## 13. Cache và độ tươi của danh sách

ServiceInstance list có thể được cache để tránh gọi API server liên tục. Cache cần chính sách:

- thời gian sống;
- cập nhật khi nhận watch event;
- resync khi watch mất;
- behavior khi cache rỗng;
- behavior khi cache đã quá cũ;
- giới hạn bộ nhớ nếu nhiều service ID.

Ví dụ policy:

~~~text
Cache mới:
  dùng cho LoadBalancer.
Watch mất ngắn hạn:
  giữ cache và phát cảnh báo.
Cache quá tuổi:
  không chọn instance cũ vô hạn.
Không có instance ban đầu:
  trả lỗi rõ hoặc dùng Service DNS fallback.
~~~

Giá trị thời gian phải phụ thuộc độ nhạy của hệ thống. Một service thanh toán có policy khác một service đọc catalog.

Không tự tạo cache riêng nếu LoadBalancer hoặc discovery integration đã quản lý cache. Nhiều lớp cache làm khó biết instance nào đang được dùng.

## 14. Xử lý danh sách rỗng

getInstances có thể trả danh sách rỗng vì:

- service ID không tồn tại;
- namespace sai;
- selector không khớp;
- không có Pod Ready;
- RBAC lọc hoặc chặn resource;
- API server chưa truy cập được;
- discovery filter loại mọi instance;
- cache chưa khởi tạo.

Ứng dụng cần phân biệt:

~~~text
service ID sai
khác với
service tồn tại nhưng không có Ready endpoint
khác với
API server đang timeout
~~~

Ba trường hợp có thông báo, fallback và alert khác nhau. Không trả HTTP 500 chung chung mà không ghi nguyên nhân nội bộ có thể chẩn đoán an toàn.

Nếu fallback sang DNS Service, cần chắc chắn Service DNS là một đường được hỗ trợ và semantics routing chấp nhận được. Fallback không nên làm client vô tình bỏ qua yêu cầu chọn vùng hoặc tenant.

## 15. Metadata và routing

Metadata có thể hỗ trợ policy như zone, version hoặc capability:

~~~text
serviceId: orders
metadata:
  zone: a
  version: v2
  capability: refund
~~~

Không coi metadata là sự thật bảo mật. Metadata có thể đến từ label, annotation hoặc integration mapping và cần được kiểm soát bởi hệ thống triển khai.

Nếu policy chọn instance theo metadata:

1. xác định nguồn metadata;
2. kiểm tra key có luôn tồn tại không;
3. quy định khi metadata sai hoặc thiếu;
4. giới hạn tập instance;
5. đặt timeout và fallback;
6. quan sát instance được chọn.

Không đưa tenant authorization vào metadata discovery rồi tin tuyệt đối. Quyền truy cập vẫn phải được xác thực ở API nghiệp vụ.

## 16. Không dùng getServices làm health endpoint

Một health endpoint gọi getServices mỗi lần có thể gây vấn đề:

- health probe chạy thường xuyên;
- API server bị tải thêm;
- API server chậm làm Pod bị NotReady;
- lỗi discovery làm liveness restart container;
- thông tin topology bị lộ.

Nếu cần health indicator cho discovery, dùng timeout ngắn, cache trạng thái và tách readiness khỏi liveness. Discovery có thể là dependency tùy chọn; không phải mọi lỗi API server đều cần restart process.

## 17. Chẩn đoán theo lớp

| Hiện tượng | Kiểm tra |
| --- | --- |
| getServices trả rỗng | Namespace, filter, RBAC, API availability |
| getInstances trả rỗng | Service name, selector, readiness, EndpointSlice |
| 403 từ API server | Role, Binding, ServiceAccount, verb và namespace |
| Instance host không gọi được | Network route, NetworkPolicy, port và scheme |
| Danh sách cũ | Cache age, watch reconnect, resync và resource version |
| Chọn instance lệch | LoadBalancer policy, cache, connection pool |
| Service DNS hoạt động nhưng discovery fail | Discovery API/RBAC riêng với DNS |
| Discovery hoạt động nhưng API 401 | Authentication của API nghiệp vụ riêng |

Các lệnh kiểm tra người vận hành có thể dùng:

~~~bash
kubectl -n shop get service orders
kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=orders
kubectl auth can-i list endpointslices \
  --as=system:serviceaccount:shop:checkout -n shop
~~~

Đây là thao tác chẩn đoán, không phải quyền mà checkout cần cho một đường gọi DNS thông thường.

## 18. Quy trình chọn cách gọi

Trước khi dùng getServices hoặc getInstances:

1. Client có thật sự cần danh sách service không?
2. Có thể gọi một Service bằng DNS không?
3. Nếu cần instance, địa chỉ trả về có thể kết nối trực tiếp không?
4. Metadata nào quyết định lựa chọn?
5. Discovery source là Service, EndpointSlice hay registry?
6. Namespace scope là gì?
7. RBAC resource và verb nào cần?
8. Cache và watch được quản lý ở lớp nào?
9. Danh sách rỗng và API timeout xử lý ra sao?
10. LoadBalancer có thực sự chọn Pod cuối cùng hay chỉ chọn Service?

Trả lời được các câu hỏi này trước khi thêm code giúp tránh biến một đường gọi đơn giản thành nhiều lớp discovery không cần thiết.

## 19. Kết luận

Service ID là tên logic của dịch vụ; ServiceInstance là dữ liệu địa chỉ và metadata của một đích có thể gọi. DiscoveryClient cung cấp danh sách, còn HTTP client gửi request và LoadBalancer có thể chọn instance. Kubernetes Service và DNS là một mô hình khác, thường đủ cho client gọi API nội bộ bằng tên ổn định.

Khi dùng DiscoveryClient trên Kubernetes, cần biết integration ánh xạ resource nào, scope namespace ra sao, host và port có thể gọi được không, readiness và cache ảnh hưởng thế nào, cùng RBAC cần những resource và verb nào. Danh sách rỗng, instance cũ và lỗi API server phải được phân biệt.

Chỉ lấy danh sách service ID hoặc ServiceInstance khi ứng dụng thật sự cần thông tin đó. Nếu không, dùng Service DNS và HTTP client thông thường sẽ giảm dependency, quyền RBAC và failure mode vận hành.
