# Kiểm tra tương thích giữa thư viện client và cluster

Một ứng dụng có thể biên dịch thành công nhưng vẫn không hoạt động đúng khi gọi Kubernetes API. Lý do có thể nằm ở sự lệch giữa thư viện client Java, phiên bản Spring Boot/Spring Cloud Kubernetes, API server, resource được bật, CRD, cơ chế xác thực hoặc CA của cluster.

“Tương thích” không chỉ có nghĩa client mở được kết nối TCP. Một client thật sự tương thích khi nó có thể xác thực, gọi đúng API group/version, hiểu response, xử lý trạng thái resource, dùng được tính năng cluster đã bật và vận hành an toàn trong giới hạn version skew được hỗ trợ.

Bài học thuộc chương **Kubernetes client** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là xây dựng ma trận tương thích, phân biệt client version với API resource version, kiểm tra cluster trước rollout, xử lý lỗi discovery/auth/TLS và nâng cấp thư viện hoặc cluster theo từng lớp.

## 1. Những phiên bản cần theo dõi

Một hệ thống Spring Cloud Kubernetes thường có nhiều lớp version:

| Lớp | Ví dụ ý nghĩa | Vì sao ảnh hưởng |
| --- | --- | --- |
| JDK | Runtime chạy ứng dụng | Thư viện có thể yêu cầu mức Java tối thiểu |
| Spring Boot | Framework và auto-configuration | Quyết định API nền tảng, property và lifecycle |
| Spring Cloud release train | Bộ module Spring Cloud tương thích | Quản lý module discovery/config/load balancer |
| Spring Cloud Kubernetes | Tích hợp Kubernetes cho Spring | Chọn client, property và resource behavior |
| Java Kubernetes client | SDK hoặc transport bên dưới | Hiểu API, auth, watch và model object |
| Kubernetes API server | Control plane của cluster | Có API group, version và feature được phục vụ |
| CRD/operator | Resource mở rộng của cluster | Schema và endpoint có thể thuộc extension riêng |
| CA/TLS/auth | Cách kết nối và xác thực | Client có thể không handshake hoặc nhận 401/403 |

Có thể hình dung quan hệ:

~~~text
JDK
  |
  v
Spring Boot <--> Spring Cloud release train
                         |
                         v
              Spring Cloud Kubernetes
                         |
                         v
                 Java Kubernetes client
                         |
                         v
           Kubernetes API server + resources
                         |
                         v
              RBAC / TLS / CRD / feature gates
~~~

Một thay đổi ở một lớp không tự làm các lớp còn lại tương thích. Nâng Java có thể làm ứng dụng chạy được nhưng không sửa API mismatch. Nâng client library có thể thêm API support nhưng không tạo CRD trên cluster. Nâng cluster có thể thay đổi resource behavior nhưng không cập nhật dependency trong image.

## 2. Phân biệt bốn loại tương thích

### 2.1. Tương thích build

Maven hoặc Gradle resolve được dependency, mã biên dịch được và test compile pass. Đây là điều kiện cần nhưng chưa đủ.

Lỗi thường gặp:

- Spring Boot và Spring Cloud release train không thuộc tổ hợp hỗ trợ.
- Hai module Cloud dùng version khác nhau do override.
- SDK client yêu cầu Java hoặc HTTP library khác.
- Dependency transitively kéo một API cũ.
- Class có trong compile classpath nhưng bị thiếu ở runtime.

### 2.2. Tương thích khởi động

Application context tạo bean, đọc configuration và khởi động mà không lỗi. Lớp này có thể thất bại khi auto-configuration cố tạo client hoặc đọc ConfigMap ngay lúc startup.

Cần kiểm tra:

- API server endpoint có được cấu hình không.
- CA và credential có sẵn không.
- Profile có bật đúng integration không.
- ServiceAccount có được mount hoặc cơ chế auth tương ứng không.
- Resource bắt buộc có tồn tại không.
- RBAC có cho phép thao tác startup không.

### 2.3. Tương thích API

Client gọi đúng path, group, version, verb và schema mà API server phục vụ. Một resource có thể tồn tại trong cluster nhưng không ở API version client đang yêu cầu.

Ví dụ khái niệm:

~~~text
Client yêu cầu:
  group/version/resource + verb + namespace

API server kiểm tra:
  resource có được discovery không?
  version có served không?
  verb có được hỗ trợ không?
  schema request có hợp lệ không?
  ServiceAccount có quyền không?
~~~

### 2.4. Tương thích vận hành

Ứng dụng tiếp tục hoạt động trong rollout, watch reconnect, token rotation, API throttling, graceful shutdown và thay đổi endpoint. Một client có thể gọi GET thành công nhưng vẫn không tương thích vận hành nếu watch bị reset mà không reconnect hoặc retry làm API server quá tải.

## 3. Client version không phải API version

Một thư viện Java có version riêng, còn Kubernetes resource có apiVersion trong manifest. Hai khái niệm liên quan nhưng không đồng nhất.

| Khái niệm | Ví dụ | Được quyết định bởi |
| --- | --- | --- |
| Version thư viện | Version của Java client hoặc Spring Cloud Kubernetes | Build file và BOM |
| API group/version | core/v1, apps/v1, resource API version | Kubernetes API server và resource |
| Schema resource | Trường metadata/spec/status | API server, conversion và CRD |
| Version cluster | Phiên bản control plane/node | Cluster lifecycle |
| Version CRD | Version served/storage của CRD | CRD/operator |

Không nên thấy client library có version mới rồi tự đổi apiVersion của manifest. Ngược lại, không nên đổi apiVersion chỉ vì cluster được nâng cấp mà chưa kiểm tra client, controller và resource conversion.

API discovery là nguồn kiểm tra hữu ích:

~~~text
GET /version
GET /api
GET /apis
GET /apis/apps
GET /apis/discovery.k8s.io
~~~

Client library thường gọi discovery ở bên dưới hoặc dùng model đã biết. Nếu API group/resource không được serve, lỗi 404 hoặc resource not found có thể xuất hiện dù RBAC đúng.

## 4. API stability và version skew

Kubernetes có nhiều API group với mức ổn định khác nhau. API ổn định thường có version như v1; API thử nghiệm hoặc beta có quy tắc khác và có thể thay đổi nhanh hơn. CRD còn phụ thuộc schema và conversion webhook của riêng tổ chức.

Khi đánh giá tương thích, cần ghi:

- Client gọi API group/version nào.
- Cluster đang serve version nào.
- Version nào là preferred hoặc storage.
- Client có hỗ trợ version fallback không.
- Resource có conversion giữa các version không.
- Field nào client gửi và field nào server bỏ qua hoặc từ chối.
- Feature gate hoặc admission policy có ảnh hưởng không.

Không nên dựa vào tên resource trong UI để kết luận API path. Ví dụ cùng một khái niệm có thể được truy cập qua group khác với core API. Hãy dùng API discovery và tài liệu của client để xác nhận.

Quy tắc version skew chính xác phụ thuộc dòng Kubernetes và loại client. Khi lập kế hoạch, hãy dùng ma trận hỗ trợ của phiên bản client và cluster đang chọn, thay vì suy ra từ một lần test thành công. Một khoảng lệch nhỏ có thể được hỗ trợ cho request cơ bản nhưng không đủ cho watch, subresource hoặc tính năng mới.

## 5. Ma trận tương thích tối thiểu

Trước khi nâng dependency hoặc cluster, hãy lập ma trận:

| Thành phần | Version hiện tại | Version đích | Nguồn xác nhận | Kiểm tra |
| --- | --- | --- | --- | --- |
| JDK | Đang chạy | Mục tiêu | Runtime/library requirements | Compile, startup, test |
| Spring Boot | Trong build | Mục tiêu | Spring compatibility | Context test |
| Spring Cloud | Release train | Mục tiêu | Supported Boot mapping | Dependency tree |
| Spring Cloud Kubernetes | Module | Mục tiêu | Release notes/reference | Discovery/config test |
| Java Kubernetes client | Transitive/direct | Mục tiêu | Client support matrix | API/watch test |
| Kubernetes API server | Cluster | Mục tiêu | Cluster lifecycle | Discovery/preflight |
| CRD/operator | Installed | Mục tiêu | Operator compatibility | Apply/reconcile test |
| CA/auth | Current | Rotation plan | Platform policy | TLS/401/403 test |

Cột “Nguồn xác nhận” không nên chỉ ghi “chạy thử”. Hãy ghi release notes, compatibility matrix, API discovery, cluster policy hoặc test evidence tương ứng. Một test local không có API server không thể xác nhận tương thích cluster.

## 6. Kiểm tra phiên bản cluster và API discovery

Một preflight job hoặc diagnostic có thể kiểm tra version endpoint và API resources trước rollout:

~~~text
GET /version
GET /api
GET /apis
GET /apis/apps/v1
GET /apis/discovery.k8s.io/v1
~~~

Kết quả cần được ghi ở mức an toàn:

- Major/minor của API server.
- API group/version cần dùng có được serve không.
- Resource và subresource cần thiết có tồn tại không.
- Verb cần thiết có được RBAC cho phép không.
- Không ghi token hoặc header Authorization.
- Không coi HTTP 200 của /version là bằng chứng mọi tính năng đã sẵn sàng.

Nếu dùng Java client, có thể thực hiện preflight trong một thành phần riêng hoặc startup validator. Validator nên có timeout, lỗi rõ và phạm vi resource nhỏ. Không nên list toàn bộ cluster chỉ để kiểm tra một ConfigMap của namespace ứng dụng.

Một preflight tốt phân biệt:

- Không kết nối được API server.
- TLS handshake thất bại.
- 401 do credential.
- 403 do RBAC.
- 404 do group/resource không được serve.
- 429 do throttling.
- 5xx do server hoặc proxy.

## 7. Tương thích với Spring Boot và Spring Cloud Kubernetes

Spring Cloud Kubernetes phải khớp với dòng Spring Boot và Spring Cloud release train. Khi chọn dependency, hãy để BOM quản lý các module cùng hệ sinh thái nếu BOM hỗ trợ chúng. Không ghép một starter từ release train này với module core từ release train khác chỉ vì artifact cùng tên.

Các điểm cần kiểm tra sau khi đổi phiên bản:

- Auto-configuration có đổi điều kiện không.
- Property discovery/config có đổi tên hoặc semantics không.
- Cấu hình import có thay đổi không.
- Client bên dưới có đổi transport hoặc auth behavior không.
- Watch/cache có đổi cách reconnect không.
- Actuator health indicator có đổi trạng thái startup/readiness không.
- Module nào đã bị deprecated hoặc tách thành artifact khác.

Nếu application chỉ gọi Service qua DNS, việc thêm Spring Cloud Kubernetes discovery có thể tạo thêm dependency và API access không cần thiết. Tương thích tốt nhất đôi khi là không bật integration mà bài toán không cần.

Nếu application đọc ConfigMap/Secret qua API, cần kiểm tra đồng thời dependency, namespace, RBAC và semantics reload. Dependency resolve thành công không chứng minh ServiceAccount có get/list/watch đúng resource.

## 8. Java client và transport bên dưới

Spring Cloud Kubernetes có thể sử dụng Java Kubernetes client thông qua integration hoặc starter. Client bên dưới thường chịu trách nhiệm:

- Xây dựng request path.
- Serialize/deserialize resource.
- TLS và hostname verification.
- Bearer token hoặc cơ chế auth.
- Connection pool và timeout.
- Watch stream và reconnect.
- Xử lý status code.

Khi nâng client trực tiếp hoặc thông qua Spring Cloud Kubernetes, cần xem thay đổi ở cả API và runtime behavior. Một transport mới có thể có default timeout khác; một model mới có thể bỏ qua field; một watch implementation có thể thay đổi cách xử lý resourceVersion.

Không nên override Java client version một cách riêng lẻ nếu release train đã quản lý nó, trừ khi có issue rõ, kiểm thử và kế hoạch quay về. Nếu buộc phải override do lỗ hổng, hãy kiểm tra binary compatibility và mọi module cùng sử dụng transport.

## 9. Tương thích authentication và TLS

Client có thể tương thích API path nhưng vẫn không gọi được cluster vì auth/TLS:

| Lỗi | Lớp cần kiểm tra | Không nên làm |
| --- | --- | --- |
| Certificate unknown | CA bundle, path, projected volume, proxy | Tắt TLS verification |
| Hostname mismatch | API server hostname, SNI, proxy | Bỏ hostname verification |
| 401 Unauthorized | Token, credential provider, thời hạn | Retry vô hạn |
| 403 Forbidden | ServiceAccount, Role, RoleBinding | Cấp cluster-admin ngay lập tức |
| Connection reset | NetworkPolicy, proxy, server idle timeout | Tăng retry không giới hạn |
| Timeout | Route, connect/read timeout, API load | Đặt timeout vô hạn |

Projected ServiceAccount token có thể được xoay vòng. Client cần hỗ trợ đọc lại hoặc có cơ chế reload phù hợp. Nếu client giữ token tại thời điểm khởi tạo, hãy kiểm tra behavior khi token cũ hết hạn.

CA rotation cũng cần được kiểm chứng. Một process đã nạp CA vào SSL context có thể không tự đọc file mới. Khi đó, cần lifecycle reload hoặc restart có kiểm soát. Không nên chờ tới lúc mọi request 5xx mới phát hiện CA đã thay đổi.

## 10. Tương thích RBAC và hành vi client

RBAC phải khớp với thao tác thực tế, không chỉ với tên tính năng:

| Hành vi client | Thao tác có thể cần |
| --- | --- |
| Đọc một ConfigMap theo tên | get ConfigMap |
| Liệt kê ConfigMap rồi lọc | list ConfigMap |
| Theo dõi ConfigMap | list/watch ConfigMap tùy cơ chế |
| Discovery Service | get/list/watch Service |
| Discovery EndpointSlice | get/list/watch EndpointSlice |
| Theo dõi nhiều namespace | Quyền tương ứng ở từng namespace hoặc cluster scope |
| Đọc Secret | get/list/watch Secret, chỉ khi thật sự cần |

Client mới có thể thay đổi từ GET từng resource sang list/watch cache. Vì vậy, nâng version có thể làm Role cũ không còn đủ dù mã ứng dụng không đổi. Sau nâng cấp, kiểm tra audit log hoặc preflight với danh tính thật của Pod.

Một Role có resourceNames phù hợp với get resource đã biết tên nhưng có thể không phù hợp với list/watch. Không kết luận rằng thêm list/watch với resourceNames là đủ cho mọi client. Hãy xác nhận request thực tế.

## 11. CRD và operator

CRD không được quản lý giống resource built-in. Tương thích giữa client và CRD cần xét:

- CRD đã cài chưa.
- API group/version có được serve không.
- Version nào là storage.
- Schema có bật preserve unknown fields hay validation chặt không.
- Conversion webhook có hoạt động không.
- Operator version có tương thích CRD không.
- Client gửi field nào và operator reconcile field nào.
- RBAC có bao gồm status hoặc finalizer subresource không.

Một client có thể gọi /apis/example.io/v1 thành công nhưng request bị từ chối vì schema CRD không nhận field. Ngược lại, response có thể thành công nhưng operator chưa reconcile vì version operator không phù hợp.

Không nên nâng Java client hoặc Spring Cloud Kubernetes và coi CRD tự được nâng theo. CRD/operator là phần platform phải có kế hoạch version riêng, migration và rollback riêng.

## 12. Resource field và schema compatibility

Khi client serialize object, field có thể gặp các tình huống:

- Field không tồn tại ở version cũ.
- Field đã deprecated nhưng vẫn được serve.
- Field bị server default nếu không gửi.
- Field bị validation từ chối.
- Unknown field bị prune.
- ResourceVersion hoặc UID bị dùng sai trong update.
- Status và spec có quyền khác nhau.

Đọc resource thường ít rủi ro hơn ghi resource, nhưng client vẫn phải hiểu response schema. Với thao tác update/patch, hãy dùng optimistic concurrency và xử lý conflict.

Nếu ứng dụng chỉ discovery và config read-only, tránh thêm quyền mutation và tránh dùng client API ghi resource. Giảm surface area giúp tương thích dễ hơn vì ít phụ thuộc vào admission, webhook và schema mutation.

## 13. Watch và compatibility

Watch là nơi version mismatch và network behavior dễ lộ. Cần kiểm tra:

- API version của resource được watch.
- ResourceVersion semantics.
- Event type mà client hỗ trợ.
- Timeout hoặc bookmark behavior.
- Cách xử lý 410 Gone khi resourceVersion quá cũ.
- Re-list sau disconnect.
- Backoff khi API server trả lỗi.
- Shutdown khi Pod nhận SIGTERM.

Luồng watch an toàn thường có dạng:

~~~text
List resource ban đầu
      |
      v
Lưu resourceVersion
      |
      v
Watch từ resourceVersion
      |
      +--> Added/Modified/Deleted -> cập nhật cache
      |
      +--> 410 hoặc stream lỗi -> list lại
      |
      +--> stop signal -> đóng watch
~~~

Một client mới có thể thay đổi implementation informer mà không đổi API Java của application. Vì vậy, test cần kiểm tra behavior, không chỉ compile.

Không nên tự xử lý 410 bằng cách retry cùng resourceVersion vô hạn. Hãy list lại theo semantics của client và API server.

## 14. Feature gates và hành vi cluster

Cluster có thể bật hoặc tắt feature gates, admission plugin, API priority/fairness, NetworkPolicy hoặc policy bảo mật. Client phải tương thích với hành vi thực tế của cluster:

- Resource hoặc field có thể chưa được bật.
- Request có thể bị admission webhook sửa hoặc từ chối.
- API server có thể throttle theo priority.
- Policy có thể chặn namespace hoặc service account.
- EndpointSlice và readiness có thể được xử lý khác theo cấu hình cluster.
- Pod Security hoặc admission policy có thể từ chối manifest chứa token/mount không phù hợp.

Không nên kiểm tra trên một cluster dev rồi giả định production có cùng feature gates và admission rules. Preflight cần chạy với cluster class tương ứng, còn integration test cần kiểm tra những behavior platform quan trọng.

## 15. Kiểm tra tương thích trước rollout

Một preflight có thể gồm nhiều lớp:

~~~text
Build
  -> dependency tree và Java runtime
  -> startup context test
  -> TLS/auth smoke test
  -> API discovery
  -> RBAC với ServiceAccount thật
  -> resource read/watch test
  -> readiness và shutdown test
  -> canary rollout
~~~

Chi tiết:

1. Resolve dependency với BOM và kiểm tra override.
2. Kiểm tra Java runtime của image.
3. Khởi động application với profile Kubernetes.
4. Xác minh TLS tới API server.
5. Xác minh danh tính bằng một thao tác read tối thiểu.
6. Xác minh API group/resource/version cần dùng.
7. Xác minh ConfigMap, Service hoặc EndpointSlice cần thiết.
8. Mở watch thử nếu production dùng watch.
9. Gửi SIGTERM và đo thời gian đóng client.
10. Chạy canary với một replica trước khi rollout rộng.

Preflight nên dùng cùng image, profile, ServiceAccount và NetworkPolicy với workload production. Một script chạy bằng quyền admin từ máy developer không chứng minh Pod runtime tương thích.

## 16. Test contract cho Kubernetes client

Có thể chia test theo phạm vi:

| Loại test | Kiểm tra | Không chứng minh được |
| --- | --- | --- |
| Unit test | Logic chọn resource, retry, mapping | API server thật và RBAC thật |
| Context test | Bean, auto-configuration, property | Network và API resource |
| Client integration test | Request/response với API giả hoặc cluster test | Policy production nếu môi trường khác |
| API discovery test | Group/version/resource được serve | Hành vi nghiệp vụ cuối |
| RBAC test | Danh tính có verb/resource cần thiết | TLS hoặc cache/watch lâu dài |
| Watch test | Reconnect, 410, shutdown | Tải production đầy đủ |
| Canary test | Startup, readiness, traffic thật hạn chế | Mọi namespace/replica path |

Một test compatibility hữu ích ghi lại cluster version, API resources, client version và các thao tác đã kiểm tra. Không ghi token hoặc Secret vào artifact test.

Nếu dùng mock API server, hãy bổ sung test against real Kubernetes hoặc môi trường tương thích để phát hiện khác biệt ở admission, watch, throttling và RBAC.

## 17. Nâng cấp client và cluster theo thứ tự

Có hai hướng nâng cấp phổ biến:

### Nâng client trước

- Giữ cluster hiện tại.
- Nâng Spring Cloud Kubernetes hoặc Java client.
- Kiểm tra API calls, RBAC, watch và TLS.
- Rollout canary.
- Sau đó mới nâng cluster nếu cần.

Ưu điểm là thay đổi cluster nhỏ hơn; rủi ro là client mới có thể cần API hoặc behavior chưa có ở cluster hiện tại.

### Nâng cluster trước

- Nâng control plane theo quy trình platform.
- Kiểm tra resource/API compatibility của workload cũ.
- Sau đó nâng client để dùng tính năng mới.

Ưu điểm là platform có API mới; rủi ro là cluster có thể loại bỏ API deprecated mà client cũ vẫn dùng.

Trong cả hai hướng, không nâng đồng thời mọi lớp nếu không cần. Tách thay đổi giúp biết nguyên nhân khi canary lỗi. Nếu bắt buộc nâng đồng thời, phải có test matrix và kế hoạch rollback rõ.

## 18. Rollback và version pinning

Pin version giúp build tái tạo được. Không nên dùng version range cho Spring Boot, Spring Cloud hoặc Java client trong workload production nếu điều đó làm dependency thay đổi ngoài review.

Rollback cần xác định:

- Có thể quay image về phiên bản client cũ không.
- Cluster đã thay đổi API/CRD không thể rollback bằng image.
- CRD/operator có migration một chiều không.
- CA/token đã rotation không.
- ConfigMap/Secret schema có tương thích với image cũ không.
- Watch/cache cũ có hiểu resource version mới không.

Rollback application sau khi nâng cluster có thể không đủ nếu cluster đã bỏ API version hoặc resource. Vì vậy, compatibility plan phải là hai chiều: image mới với cluster cũ trong giới hạn hỗ trợ, và image cũ với cluster mới trong thời gian rollback.

## 19. Quan sát tương thích trong production

Các tín hiệu nên theo dõi:

- Client library version và application build revision.
- API server version đã kiểm tra ở preflight.
- Request count/latency theo group, version, resource và verb.
- Tỷ lệ 401, 403, 404, 409, 410, 429 và 5xx.
- Watch reconnect và cache resync.
- TLS handshake failure.
- Pool exhaustion và request timeout.
- Startup/readiness failure.
- Thời gian graceful shutdown.
- Số resource/cache đang giữ.

Không nên gắn token, Secret hoặc full URL có credential vào metric label. Version label là dữ liệu an toàn hơn, nhưng vẫn cần giới hạn cardinality.

Một health indicator có thể báo client đã cấu hình, nhưng không nên gọi list toàn cluster trong mỗi health check. Health check cần timeout ngắn, resource nhỏ và semantics rõ. Nếu Kubernetes API tạm thời không truy cập được, quyết định readiness/liveness phải phù hợp với khả năng phục vụ nghiệp vụ.

## 20. Checklist kiểm tra tương thích

Trước khi phát hành image mới hoặc nâng cluster, hãy kiểm tra:

- JDK, Spring Boot, Spring Cloud và Spring Cloud Kubernetes thuộc tổ hợp được hỗ trợ.
- Java Kubernetes client không bị override ngoài kiểm soát.
- API group/version/resource cần dùng được cluster serve.
- CRD/operator có version và schema tương thích.
- TLS CA, hostname và auth provider được kiểm tra.
- ServiceAccount có đúng get/list/watch cần thiết.
- Client không yêu cầu quyền mutation nếu ứng dụng chỉ đọc.
- Timeout, connection pool và retry phù hợp tải.
- Watch có xử lý disconnect, 410 và shutdown.
- Cache có xử lý stale data và giới hạn memory.
- Preflight chạy với image và identity thật của Pod.
- Test không chỉ dùng quyền admin hoặc kubeconfig developer.
- Canary kiểm tra startup, readiness, API read và watch nếu cần.
- Log/metric không lộ credential.
- Rollback xét cả application, cluster, CRD và Secret rotation.
- Version pinning và dependency tree được review.
- Có quan sát đủ để phân biệt 401, 403, 404, 429, TLS và timeout.

## 21. Tự kiểm tra

1. Vì sao build thành công chưa chứng minh client tương thích với cluster?
2. Khác biệt giữa version của Java client và apiVersion của Kubernetes resource là gì?
3. Những lớp nào cần đưa vào ma trận tương thích của ứng dụng Spring Cloud Kubernetes?
4. Làm thế nào phân biệt lỗi TLS, authentication, authorization và API discovery?
5. Vì sao một Role chỉ có get có thể không đủ cho informer hoặc watch?
6. CRD/operator khác resource built-in ở điểm nào khi kiểm tra compatibility?
7. Tại sao test bằng quyền admin từ máy developer không đại diện cho Pod production?
8. Khi watch nhận 410 Gone, client nên xử lý theo hướng nào?
9. Vì sao nâng client và nâng cluster cùng lúc làm chẩn đoán rollback khó hơn?
10. Những metric nào giúp phát hiện client mới làm tăng tải API server?
11. Làm thế nào kiểm tra credential rotation mà không log Secret?
12. Bằng chứng nào đủ để kết luận một release client đã tương thích về build, API và vận hành?

Tương thích giữa thư viện client và cluster là một hợp đồng nhiều lớp: dependency phải đúng, API phải được serve, auth/TLS phải hoạt động, RBAC phải khớp, resource schema phải tương thích và watch/cache phải vận hành ổn định. Hãy lập ma trận version, chạy preflight bằng đúng identity của Pod, kiểm tra API discovery cùng behavior thật, rồi rollout canary trước khi mở rộng. Với Spring Cloud Kubernetes, sự tương thích đáng tin cậy đến từ kiểm chứng có cấu trúc, không chỉ từ việc application khởi động thành công.

