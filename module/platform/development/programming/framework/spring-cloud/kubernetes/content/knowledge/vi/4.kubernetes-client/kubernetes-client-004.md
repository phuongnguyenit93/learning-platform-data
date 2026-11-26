# Vòng đời Kubernetes client và tái sử dụng kết nối

Một ứng dụng Spring Cloud Kubernetes có thể gọi Kubernetes API để đọc Service, EndpointSlice, ConfigMap hoặc Secret. Mỗi lần gọi API không nên tạo một Kubernetes client mới rồi bỏ đi. Client thường quản lý HTTP transport, connection pool, TLS, credential, timeout và đôi khi cả watch hoặc cache. Tạo client theo từng request làm tăng số socket, handshake TLS, mức dùng CPU và tải lên API server.

Thiết kế đúng cần phân biệt ba đối tượng:

| Đối tượng | Vai trò | Vòng đời nên cân nhắc |
| --- | --- | --- |
| Kubernetes client | Gửi request tới Kubernetes API server | Thường sống cùng application context |
| HTTP connection/connection pool | Giữ và tái sử dụng kết nối tới một host | Do transport của client quản lý |
| Request/watch | Một thao tác hoặc luồng theo dõi tài nguyên | Có timeout, retry và cách đóng riêng |

Spring Cloud Kubernetes có thể dùng client bên dưới để discovery hoặc đọc cấu hình. Ứng dụng cũng có thể dùng Kubernetes client trực tiếp cho một nhu cầu riêng. Dù cách tích hợp nào được chọn, nguyên tắc vẫn là quản lý client như một dependency có vòng đời rõ ràng, giới hạn phạm vi truy cập và không biến mỗi request nghiệp vụ thành một lần khởi tạo transport mới.

Bài học thuộc chương **Kubernetes client** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là hiểu vòng đời client, cách tái sử dụng kết nối an toàn, khác biệt giữa request ngắn và watch dài, cùng các quyết định về cache, RBAC, timeout, retry và shutdown.

## 1. Kubernetes client làm những việc gì?

Một Kubernetes client thường thực hiện nhiều lớp công việc:

1. Chọn cách kết nối tới API server.
2. Đọc địa chỉ API server, CA và credential.
3. Tạo HTTP transport và connection pool.
4. Gửi request tới resource và namespace.
5. Chuyển response thành object Java.
6. Theo dõi resource bằng watch hoặc cơ chế cache nếu được bật.
7. Đóng stream, pool và executor khi application dừng.

Luồng khái niệm:

~~~text
Spring application context
          |
          v
Kubernetes client singleton
          |
          +--> TLS configuration
          +--> ServiceAccount credential
          +--> HTTP connection pool
          +--> request executor
          |
          v
Kubernetes API server
~~~

Client API server khác với HTTP client gọi nghiệp vụ qua Kubernetes Service. Một WebClient gọi http://catalog-api không thay thế Kubernetes client đọc ConfigMap. Ngược lại, Kubernetes client không phải là client để gọi endpoint nghiệp vụ của catalog-api.

Không nên trộn hai loại credential:

- Token dùng để gọi Kubernetes API phải được bảo vệ và cấp theo RBAC.
- Credential nghiệp vụ dùng để gọi database hoặc service khác có vòng đời và phạm vi khác.
- Token của Kubernetes API không nên được gửi tới Service nghiệp vụ.
- Secret của ứng dụng không nên được dùng để xác thực thay cho ServiceAccount nếu thiết kế yêu cầu danh tính in-cluster.

## 2. Vì sao nên tái sử dụng client?

Một request tới API server có thể sử dụng kết nối đang mở trong pool hoặc phải tạo kết nối mới. Khi ứng dụng tạo client mới theo từng request, nó có thể gây:

- TLS handshake lặp lại.
- Tạo nhiều connection pool nhỏ, mỗi pool ít khi được tái sử dụng.
- Tăng số socket và file descriptor.
- Tăng số thread hoặc executor.
- Đọc lại token, CA và cấu hình nhiều lần.
- Gửi nhiều request discovery không cần thiết.
- Gây tải không đều lên Kubernetes API server.
- Làm shutdown khó đoán vì client tạm thời chưa được đóng.

Mẫu không nên dùng:

~~~java
public ServiceInfo readService(String name) {
    KubernetesClient client = createClientForEveryCall();
    return client.services()
            .inNamespace("shop")
            .withName(name)
            .get();
}
~~~

Mẫu tốt hơn là client được tạo ở ranh giới cấu hình và inject vào thành phần dùng nó:

~~~java
@Service
public class ServiceReader {

    private final KubernetesClient client;

    public ServiceReader(KubernetesClient client) {
        this.client = client;
    }

    public ServiceInfo readService(String name) {
        return client.services()
                .inNamespace("shop")
                .withName(name)
                .get();
    }
}
~~~

Đoạn mã chỉ minh họa ý tưởng và API có thể khác theo thư viện client. Điểm chính là KubernetesClient không được tạo bên trong mỗi lần gọi readService. Spring quản lý bean, còn client quản lý pool và transport bên dưới.

Tái sử dụng không có nghĩa giữ một request đang treo vô hạn. Client dùng chung vẫn cần timeout theo request, giới hạn pool, xử lý lỗi và cơ chế đóng khi application context dừng.

## 3. Đặt client ở đâu trong Spring?

Trong ứng dụng Spring, client thường được tạo ở một @Configuration hoặc do starter/integration cung cấp. Nếu tự tạo client, cần xác định rõ ownership: bean nào tạo, bean nào đóng và ai được phép dùng.

Ví dụ khái niệm:

~~~java
@Configuration
public class KubernetesClientConfiguration {

    @Bean
    KubernetesClient kubernetesClient() {
        return createInClusterOrConfiguredClient();
    }
}
~~~

Nếu thư viện client hỗ trợ Closeable, AutoCloseable hoặc cơ chế shutdown riêng, Spring có thể gọi lifecycle callback khi context dừng tùy cách bean được khai báo. Cần kiểm tra ownership khi bean được tạo qua factory của thư viện:

- Nếu Spring tạo object, Spring thường có thể quản lý destruction callback.
- Nếu một starter tạo client bên trong, không tạo thêm client thứ hai nếu không cần.
- Nếu client được cung cấp bởi SDK có global singleton, phải hiểu cách SDK đóng resource.
- Nếu inject client từ module khác, không tự close ở một service con khi service đó chưa sở hữu client.

Không nên có nhiều client giống hệt nhau trong cùng JVM chỉ vì mỗi service tự gọi new. Có thể cần client riêng khi endpoint, credential, namespace hoặc policy khác nhau; nhưng đó phải là quyết định có chủ ý và có giới hạn.

## 4. Tạo client trong cluster và ngoài cluster

Trong cluster, client thường lấy API server và credential từ môi trường in-cluster. Các thành phần có thể gồm:

- Địa chỉ Kubernetes API server.
- CA certificate để xác minh TLS.
- ServiceAccount token hoặc cơ chế credential được cluster hỗ trợ.
- Namespace mặc định hoặc namespace do ứng dụng cấu hình.
- Timeout và proxy theo môi trường.

Ngoài cluster, client có thể dùng kubeconfig, endpoint được cấu hình hoặc credential của một môi trường phát triển. Không nên đưa kubeconfig của máy phát triển vào image production.

Luồng chọn cấu hình nên rõ:

~~~text
Profile local
  -> kubeconfig hoặc mock client
  -> không dùng token in-cluster của production

Profile kubernetes
  -> API server trong cluster
  -> CA + ServiceAccount hoặc cơ chế xác thực được phê duyệt
  -> RBAC theo workload
~~~

Không nên tự suy ra profile chỉ từ việc một biến môi trường tồn tại rồi cấp quyền rộng hơn. Profile chỉ chọn cách cấu hình; API server và RBAC vẫn phải được kiểm tra.

Nếu client không kết nối được trong local, hãy dùng mock hoặc test configuration thay vì nuốt lỗi rồi tạo client production-like bằng credential không rõ nguồn. Nếu client không kết nối được trong production, lỗi nên được phân loại rõ là DNS, TLS, authentication, authorization, timeout hay API response.

## 5. Connection pool và keep-alive

HTTP transport thường giữ connection pool theo host, scheme và cấu hình TLS. Kết nối keep-alive có thể được tái sử dụng cho các request tới cùng API server khi server và client cho phép.

Các tham số cần xem xét:

| Tham số | Tác dụng | Rủi ro nếu sai |
| --- | --- | --- |
| Max connections | Giới hạn số kết nối đồng thời | Quá thấp gây chờ; quá cao gây tải API server |
| Per-host limit | Giới hạn theo API server | Không phù hợp khi có nhiều endpoint hoặc proxy |
| Idle timeout | Đóng connection nhàn rỗi | Quá ngắn làm mất lợi ích keep-alive |
| Connect timeout | Giới hạn thời gian mở connection | Quá dài làm thread chờ khi route lỗi |
| Read/response timeout | Giới hạn thời gian chờ response | Quá dài làm request treo và chiếm pool |
| TLS settings | Xác minh API server | Sai CA gây lỗi handshake hoặc tạo cám dỗ tắt verify |
| Retry policy | Thử lại lỗi tạm thời | Retry sai có thể nhân tải hoặc lặp thao tác không an toàn |

Không nên tắt TLS verification để “sửa” lỗi certificate. Hãy kiểm tra CA, hostname, proxy và thời gian hệ thống. Một client dùng chung với TLS sai sẽ làm mọi chức năng Kubernetes trong JVM lỗi theo cùng cách.

Một pool quá lớn không làm API server nhanh hơn. Hãy đặt giới hạn theo số request đồng thời thật sự, loại thao tác và quota của cluster. Discovery polling, config watch và request nghiệp vụ tới API server cần được tính cùng nhau.

## 6. Request ngắn và watch dài là hai kiểu vòng đời

Request GET một resource thường bắt đầu, nhận response rồi kết thúc. Watch là một stream dài hơn, chờ sự kiện thay đổi và có thể bị ngắt bởi network, timeout, API server hoặc resource version.

~~~text
Request ngắn:
mở hoặc lấy connection -> gửi -> nhận response -> trả pool

Watch:
mở connection -> giữ stream -> nhận nhiều event
       -> reconnect khi cần -> đóng khi context dừng
~~~

Không nên dùng cùng cách timeout cho request và watch:

- Request đọc ConfigMap cần response timeout hữu hạn.
- Watch cần cơ chế stream/read timeout và reconnect phù hợp.
- Watch phải đóng khi application dừng.
- Reconnect phải có backoff và xử lý resource version.
- Watch không nên tạo thêm một client mới mỗi lần reconnect nếu transport có thể tái sử dụng.

Nếu watch bị đứt, client có thể cần liệt kê lại resource hoặc dùng resource version mới trước khi tiếp tục. Logic này thường thuộc thư viện informer/cache. Không nên tự nối stream bằng cách bỏ qua mọi lỗi hoặc lặp tight loop.

Một watch đang bị treo không nên giữ toàn bộ thread pool của ứng dụng. Cần tách executor hoặc cấu hình async phù hợp nếu thư viện hỗ trợ. Đồng thời, hãy đặt giới hạn số watch theo namespace và resource.

## 7. Cache và informer giảm tải API server

Discovery hoặc config integration có thể dùng cache để tránh đọc API server cho mọi request. Một cache thường có luồng:

~~~text
list resource ban đầu
        |
        v
watch thay đổi
        |
        v
cập nhật local cache
        |
        v
application đọc cache
~~~

Lợi ích:

- Giảm số GET lặp lại.
- Giảm độ trễ cho lookup.
- Có thể cung cấp danh sách instance nhanh hơn.
- Giảm tải cho API server khi nhiều request nghiệp vụ cùng cần metadata.

Đổi lại:

- Cache có độ trễ và có thể tạm thời cũ.
- Watch có thể mất kết nối hoặc bị reset.
- Bộ nhớ tăng theo số resource lưu.
- RBAC cần phù hợp với list/watch.
- Khi cache lỗi, ứng dụng cần quyết định fail, refresh hoặc dùng dữ liệu cũ.

Cache không nên được xem là nguồn sự thật vĩnh viễn. Nếu route tới một Pod vừa bị xóa, client vẫn phải xử lý connection failure và retry an toàn. Discovery cache cho biết thông tin tại thời điểm gần đây; nó không loại bỏ race condition giữa lúc chọn endpoint và lúc kết nối.

Với Secret, cache cần được xem xét chặt hơn vì dữ liệu nhạy cảm có thể tồn tại trong heap lâu hơn. Chỉ cache Secret khi thật sự cần, giới hạn scope và tránh đưa giá trị vào log hoặc metric.

## 8. Namespace và phạm vi client

Một client dùng chung có thể được cấu hình với namespace mặc định, nhưng mỗi thao tác vẫn có thể chỉ rõ namespace. Không nên để service layer tự nối chuỗi namespace từ input người dùng mà không kiểm tra.

Có ba kiểu phạm vi thường gặp:

| Phạm vi | Khi phù hợp | Yêu cầu |
| --- | --- | --- |
| Một namespace | Ứng dụng chỉ quản lý resource của chính nó | Role namespaced và namespace cố định |
| Nhiều namespace được chọn | Platform service theo dõi vài namespace | RBAC và filter rõ từng namespace |
| Toàn cluster | Thành phần hạ tầng thật sự cần | ClusterRole hẹp, audit và quota nghiêm ngặt |

Một client có thể dùng cùng API server nhưng không nên mặc định có quyền toàn cluster. Namespace mặc định trong cấu hình không tự giới hạn RBAC; Role/RoleBinding mới quyết định phạm vi quyền.

Nếu ứng dụng chỉ cần đọc ConfigMap của namespace shop, hãy cấu hình namespace đó và Role giới hạn. Nếu discovery cần xem Service ở nhiều namespace, hãy ghi rõ lý do và kiểm tra ảnh hưởng khi có resource trùng tên.

## 9. RBAC gắn với thao tác của client

Kubernetes client có thể gọi nhiều verb khác nhau:

- get: đọc một resource theo tên.
- list: lấy danh sách resource.
- watch: nhận thay đổi resource.
- create/update/patch/delete: thay đổi resource, chỉ dùng khi có nhu cầu rõ.

Ví dụ Role đọc ConfigMap đã biết tên:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-config-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["order-settings"]
    verbs: ["get"]
~~~

Một informer hoặc watch thường cần list và watch, không chỉ get. Một client discovery có thể cần đọc Service và EndpointSlice tùy implementation. Không nên đoán quyền từ tên class; hãy xem tài nguyên và thao tác mà code thực sự gọi.

RoleBinding gắn Role với ServiceAccount của Pod:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-api
  namespace: shop
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-config-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-api
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-config-reader
~~~

Nếu Kubernetes client chạy trong workload riêng như Configuration Watcher hoặc Discovery Server, quyền phải gắn với ServiceAccount của workload đó. Không mở rộng Role của ứng dụng nghiệp vụ khi thành phần thực sự nhận 403 là watcher.

## 10. Token, CA và xoay vòng credential

Kubernetes client thường cần credential và CA để gọi API server. Các dữ liệu này có vòng đời:

- Token có thể được xoay vòng hoặc thay thế.
- CA có thể thay đổi khi cluster được quản lý lại.
- API server endpoint có thể thay đổi theo môi trường.
- Proxy hoặc NetworkPolicy có thể thay đổi.
- Kubelet có thể cập nhật file mounted từ Secret/ServiceAccount.

Client đọc token một lần khi khởi tạo có thể không tự nhận giá trị mới. Khả năng reload phụ thuộc loại token, thư viện và cách cấu hình. Nếu cluster dùng projected token hoặc credential rotation, hãy kiểm tra client có đọc lại file, hỗ trợ refresh hoặc cần khởi tạo lại an toàn.

Không nên copy token vào một biến string global lâu hơn cần thiết hoặc log token để debug. Nếu client cần giữ credential trong memory để gửi request, hãy giảm scope, bảo vệ log và hiểu rằng JVM heap vẫn có thể chứa dữ liệu cho tới khi được thu hồi.

CA certificate không nên bị bỏ qua bằng trust-all hoặc hostname verification disabled. Nếu lỗi TLS xuất hiện sau rotation, kiểm tra file CA, volume projection, path, permission và lifecycle của HTTP transport.

Khi cần recreate client để nhận credential mới, không được tạo client mới trước mỗi request. Hãy dùng lifecycle controller có giới hạn: tạo client mới, chuyển traffic, đóng client cũ sau khi request/watch đã kết thúc.

## 11. Timeout, retry và idempotency

Kubernetes API server có thể chậm, bị giới hạn hoặc tạm thời không truy cập được. Client cần timeout và retry có chủ đích.

| Loại lỗi | Có thể retry? | Lưu ý |
| --- | --- | --- |
| DNS/TCP timeout tạm thời | Có thể | Backoff, giới hạn số lần và kiểm tra tải |
| TLS lỗi chứng thư | Không nên retry mù | Sửa CA/hostname/cấu hình |
| 401 Unauthorized | Không retry vô hạn | Kiểm tra token hoặc credential |
| 403 Forbidden | Không retry mù | Kiểm tra RBAC và resource |
| 404 Not Found | Tùy semantics | Resource có thể đã bị xóa hoặc sai namespace |
| 409 Conflict | Có thể với chiến lược read-modify-write | Dùng resourceVersion và xử lý cạnh tranh |
| 429 Too Many Requests | Có thể | Tôn trọng Retry-After/backoff và quota |
| 5xx API server | Có thể | Backoff, circuit behavior và quan sát |

GET thường dễ retry hơn thao tác mutation, nhưng vẫn cần giới hạn. PATCH hoặc update có thể cần resourceVersion để tránh ghi đè thay đổi của thành phần khác. Không lặp lại create mà không xử lý AlreadyExists hoặc idempotency.

Retry cho watch phải khác retry cho request. Khi reconnect, dùng backoff có jitter để nhiều replica không cùng reconnect tại một thời điểm. Nếu mọi Pod đều tạo watch mới sau cùng một delay cố định, API server có thể nhận một đợt tải đột biến.

Timeout phải bao gồm cả thời gian chờ connection và response phù hợp. Timeout vô hạn che giấu API server lỗi và làm cạn thread/connection pool.

## 12. Thread safety và chia sẻ client

Nhiều Kubernetes client hiện đại được thiết kế để dùng đồng thời, nhưng không nên suy đoán mọi object trong SDK đều thread-safe. Cần phân biệt:

- Client hoặc HTTP transport có thể được chia sẻ.
- Builder thường chỉ nên dùng trong giai đoạn tạo client.
- Request builder hoặc operation object có thể chứa state và không nên chia sẻ bừa bãi.
- Object model trả về có thể được sửa trong memory; không dùng chung mutable object giữa thread nếu không cần.
- Cache/informer có synchronization riêng, nhưng callback của ứng dụng vẫn phải an toàn.

Một nguyên tắc an toàn là share client cấp application, tạo operation/request chain cho từng thao tác, và không lưu object request mutable vào singleton dùng chung.

Nếu client có async callback, callback không nên thực hiện công việc nặng trên thread nhận sự kiện. Đưa công việc sang executor có giới hạn và xử lý backpressure. Nếu callback ném exception, cần biết thư viện có dừng watch, retry hay chỉ log.

## 13. Đóng client khi ứng dụng dừng

Khi Spring context dừng do rollout, SIGTERM hoặc scale down, client cần giải phóng:

- HTTP connection pool.
- Watch stream.
- Scheduled task.
- Executor.
- Timer và callback.
- File hoặc resource liên quan đến TLS/credential nếu thư viện giữ riêng.

Một shutdown đúng nên theo thứ tự:

~~~text
Nhận tín hiệu dừng
      |
      v
Ngừng nhận request/watch mới
      |
      v
Đợi thao tác đang chạy trong thời gian giới hạn
      |
      v
Đóng watch và client transport
      |
      v
Thoát container
~~~

Kubernetes gửi SIGTERM rồi chờ termination grace period theo cấu hình. Nếu client đóng quá muộn, Pod có thể bị kill khi stream hoặc connection chưa được giải phóng. Nếu đóng quá sớm, request nghiệp vụ đang phục vụ có thể lỗi.

Không nên gọi close() từ một request handler hoặc từ service con khi client là singleton dùng chung. Hãy giao quyền đóng cho bean sở hữu client hoặc lifecycle của application context.

Nếu thư viện client không tự tích hợp với Spring lifecycle, cần bọc nó trong bean có @PreDestroy, DisposableBean hoặc cơ chế lifecycle tương ứng, sau khi kiểm tra API thực tế của thư viện.

## 14. Một Kubernetes client hay nhiều client?

Một client dùng chung thường đủ khi:

- Cùng API server.
- Cùng credential.
- Chính sách TLS giống nhau.
- Cùng giới hạn và namespace logic.
- Các thao tác có thể chia sẻ pool.

Có thể cân nhắc client riêng khi:

- Hai API server khác nhau.
- Credential và tenant khác nhau.
- TLS/proxy khác nhau.
- Một workload phải tách rõ quyền hoặc quota.
- Watch dài cần transport riêng để không chiếm pool request.
- Chính sách timeout khác biệt lớn và không thể cấu hình theo operation.

Nhiều client làm tăng chi phí và complexity. Mỗi client có thể tạo pool, executor, watch và metric riêng. Nếu tạo client riêng vì namespace khác nhưng cùng API server và credential, hãy xem liệu namespace scope ở operation và RBAC đã đủ hay chưa.

Nếu tách client vì bảo mật, tách cả ServiceAccount/workload khi cần. Chỉ tạo hai object Java trong cùng JVM không tạo ra ranh giới RBAC; cả hai vẫn dùng cùng danh tính Pod nếu gọi API in-cluster.

## 15. Cache, stale data và race condition

Một client discovery có thể đọc endpoint từ cache rồi gọi tới một Pod đã bị thay thế. Đây là race condition bình thường trong hệ phân tán:

~~~text
T0: cache thấy Pod A
T1: ứng dụng chọn Pod A
T2: Kubernetes loại Pod A khỏi Service
T3: request tới Pod A thất bại
T4: client refresh hoặc chọn đích khác
~~~

Thiết kế phải xử lý lỗi ở T3. Không nên coi cache là cam kết rằng endpoint còn sống. Timeout, retry an toàn, load balancing và readiness chỉ giảm xác suất; chúng không loại bỏ cửa sổ thay đổi.

Khi dùng Service DNS, lớp Service của Kubernetes có thể chọn endpoint hiện tại, nhưng một connection keep-alive hoặc DNS cache cũng có semantics riêng. HTTP client cần xử lý connection reset và retry request chỉ khi nghiệp vụ cho phép.

Khi dùng EndpointSlice trực tiếp, cần hiểu điều kiện ready, serving và terminating theo cơ chế client/library. Không nên tự lọc endpoint bằng một quy tắc đơn giản mà bỏ qua trạng thái rollout hoặc termination.

## 16. Kiểm tra hiệu năng và tải API server

Trước khi tăng replica ứng dụng, hãy ước lượng tải client:

| Nguồn tải | Ví dụ |
| --- | --- |
| Request discovery | Mỗi request đọc danh sách Service |
| Polling config | Mỗi Pod GET ConfigMap theo chu kỳ |
| Watch | Mỗi Pod hoặc mỗi workload giữ stream resource |
| Reconnect | Watch reconnect sau network/API error |
| Startup | Mọi replica list/get resource khi rollout |
| Retry | Request lặp lại khi timeout hoặc 429 |

Tái sử dụng connection giảm handshake nhưng không tự giảm số request. Cache và watch có thể giảm polling, nhưng watch cần RBAC và quản lý reconnect. Một ứng dụng có hàng trăm replica không nên để mỗi request nghiệp vụ gọi API server để tìm cùng một Service.

Hãy theo dõi:

- Latency tới Kubernetes API.
- Tỷ lệ 401/403/404/409/429/5xx.
- Số request theo resource và verb.
- Số connection đang mở và idle.
- Số watch đang hoạt động và reconnect.
- Kích thước cache và tuổi dữ liệu.
- Thời gian chờ shutdown.
- Số Pod readiness fail do client không khởi tạo được.

## 17. Ví dụ thiết kế client trong Spring

Ví dụ dưới chỉ minh họa ranh giới ownership, không phụ thuộc vào một SDK cụ thể:

~~~java
@Configuration
public class KubernetesClientConfig {

    @Bean(destroyMethod = "close")
    KubernetesClient kubernetesClient() {
        return createClientFromApplicationConfiguration();
    }
}

@Service
public class ConfigMapReader {

    private final KubernetesClient client;

    public ConfigMapReader(KubernetesClient client) {
        this.client = client;
    }

    public String readOrderLimit() {
        ConfigMap configMap = client.configMaps()
                .inNamespace("shop")
                .withName("order-settings")
                .get();

        if (configMap == null || configMap.getData() == null) {
            throw new IllegalStateException("Required ConfigMap is missing");
        }

        return configMap.getData().get("ORDER_MAX_ITEMS");
    }
}
~~~

Tên type và method trong ví dụ cần thay theo SDK thực tế. Ý nghĩa thiết kế là:

- Bean client được tạo một lần theo application context.
- Service inject client thay vì tự tạo client.
- Resource lookup có namespace và name rõ.
- Dữ liệu bắt buộc được validate.
- Lifecycle đóng client thuộc bean sở hữu.

Nếu SDK không dùng method close hoặc Spring starter đã sở hữu client, không thêm destroyMethod mù quáng. Có thể làm client bị đóng hai lần hoặc đóng client mà bean khác còn dùng. Hãy xác định ownership trước khi cấu hình shutdown.

## 18. Chẩn đoán lỗi vòng đời client

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Số connection tăng theo request | Tạo client trong service method | Đường tạo client, pool metric, heap/thread |
| API server bị nhiều GET lặp lại | Không cache hoặc polling quá ngắn | Request rate, discovery/config strategy |
| Watch reconnect liên tục | Timeout, network, resourceVersion hoặc backoff sai | Watch log, API response, jitter |
| 403 ngay sau startup | ServiceAccount/RoleBinding không đúng | Pod identity, namespace, verbs/resources |
| TLS handshake lỗi | CA, hostname hoặc proxy sai | CA path, certificate chain, system time |
| App dừng chậm | Watch/executor/client không đóng | SIGTERM log, termination grace period |
| Config cũ sau rotation | Client đọc token/config một lần | Reload semantics, file mount, client lifecycle |
| Retry làm tải tăng | Retry không có backoff hoặc retry lỗi không nên retry | Status code, retry budget, jitter |
| Local cố dùng in-cluster config | Profile hoặc detection sai | Active profiles, environment, kubeconfig |

Khi lỗi xảy ra, hãy xác định nó thuộc lớp nào: tạo client, TLS, authentication, authorization, transport, API semantics, cache/watch hay shutdown. Một lỗi 403 không được sửa bằng cách tăng connection pool; lỗi pool không được sửa bằng cách mở RBAC.

## 19. Checklist thiết kế

Trước khi đưa Kubernetes client vào ứng dụng Spring, hãy kiểm tra:

- Client được tạo ở một ranh giới lifecycle rõ ràng.
- Không tạo client mới theo từng request.
- Connection pool, timeout và giới hạn đồng thời phù hợp tải thật.
- Request ngắn và watch dài dùng semantics timeout/reconnect riêng.
- Watch được đóng khi application context dừng.
- Retry có backoff, jitter, budget và phân loại status code.
- Mutation có xử lý conflict và idempotency.
- Client và operation object được chia sẻ theo thread-safety của SDK.
- Namespace và resource scope được giới hạn.
- ServiceAccount, Role và RoleBinding thuộc đúng workload.
- Token, CA và credential rotation đã được xem xét.
- Không tắt TLS verification để né lỗi certificate.
- Cache có giới hạn tuổi, bộ nhớ và xử lý stale data.
- Discovery không gọi API server cho mọi request nghiệp vụ nếu cache/Service đủ dùng.
- Secret không đi vào log, metric, dump hoặc exception.
- Client được đóng đúng một lần bởi owner.
- Readiness và shutdown phản ánh khả năng client thật sự sẵn sàng.

## 20. Tự kiểm tra

1. Vì sao tạo Kubernetes client theo mỗi request gây hại cho connection pool và API server?
2. Khác biệt giữa Kubernetes client và HTTP client gọi Service là gì?
3. Khi nào nên dùng một client singleton trong Spring?
4. Vì sao watch cần lifecycle và retry khác request GET?
5. Cache discovery có thể trả dữ liệu cũ trong tình huống nào?
6. Tại sao client có token vẫn có thể nhận 403?
7. Khi nào cần nhiều client thay vì một client dùng chung?
8. Vì sao tắt TLS verification không phải cách xử lý lỗi CA?
9. Client cần làm gì khi token hoặc CA được xoay vòng?
10. Khi Pod nhận SIGTERM, những resource nào cần được đóng trước khi process thoát?
11. Vì sao tăng connection pool không giải quyết được lỗi RBAC?
12. Bằng chứng nào cho thấy client đang được tái sử dụng thay vì tạo mới theo request?

Kubernetes client nên được xem là một thành phần hạ tầng có connection pool, credential, cache và vòng đời riêng. Hãy tạo client ở cấp application, tái sử dụng transport, giới hạn namespace và RBAC, quản lý watch/retry theo đúng semantics, rồi đóng client có kiểm soát khi Spring dừng. Với Spring Cloud Kubernetes, thiết kế này giúp discovery và config giảm tải API server mà vẫn xử lý được stale data, credential rotation và lỗi mạng trong thực tế.

