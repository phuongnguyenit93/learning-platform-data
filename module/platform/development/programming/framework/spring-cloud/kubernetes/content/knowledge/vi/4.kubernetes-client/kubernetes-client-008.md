# Kiểu dữ liệu tài nguyên và lỗi trả về từ Kubernetes API

## Mục tiêu bài học

Kubernetes API không chỉ trả về một chuỗi JSON đơn giản. Mỗi resource có metadata, trạng thái mong muốn, trạng thái quan sát được, kiểu dữ liệu riêng và các quy tắc cạnh tranh khi cập nhật. Khi dùng Kubernetes Java client, Fabric8 hoặc lớp tích hợp Spring Cloud Kubernetes, ứng dụng cần hiểu object model và phân loại lỗi để tránh đọc sai field, retry sai tình huống hoặc làm mất cập nhật của controller khác.

Bài thuộc chương **Kubernetes client** của module **SPRING_CLOUD_KUBERNETES**. Module học tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành phân quyền RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Phân biệt apiVersion, kind, metadata, spec và status.
- Hiểu các field như name, namespace, UID, resourceVersion và generation.
- Phân biệt object, list, watch event, status response và custom resource.
- Đọc kiểu dữ liệu Kubernetes thường gặp như quantity, duration, selector và condition.
- Phân loại lỗi theo HTTP code, reason, details và causes.
- Thiết kế retry, conflict handling, watch reconnect và log an toàn trong client Java.

## 1. Object Kubernetes là một hợp đồng dữ liệu

Một resource Kubernetes thường được biểu diễn bằng YAML khi con người đọc và JSON khi API client trao đổi:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: order-service
      namespace: team-a
    spec:
      replicas: 2
    status:
      availableReplicas: 2

Bốn nhóm chính:

| Nhóm | Vai trò | Ai thường ghi |
| --- | --- | --- |
| apiVersion | Nhóm API và phiên bản schema | Người khai báo manifest |
| kind | Loại resource | Người khai báo manifest |
| metadata | Identity, scope, label và lịch sử object | Người dùng và API Server |
| spec | Trạng thái mong muốn | Người dùng hoặc controller cấp trên |
| status | Trạng thái quan sát được | Controller hoặc Kubernetes |

Không phải mọi kind đều có spec và status giống nhau. Pod có containerStatuses, Deployment có replicas và conditions, ConfigMap có data, còn một resource cấp thấp hơn có thể có fields riêng.

Client cần deserialize đúng kind và apiVersion. Nếu dùng model của Deployment để đọc Service, code có thể lỗi, bỏ qua field hoặc tạo kết quả sai.

## 2. apiVersion và kind

### 2.1. apiVersion

apiVersion gồm nhóm API và version, ví dụ:

    v1
    apps/v1
    batch/v1
    rbac.authorization.k8s.io/v1

Nhóm v1 ở cấp lõi không có phần group trước dấu slash. apps/v1 thuộc nhóm apps. apiVersion ảnh hưởng endpoint API, schema, field và hành vi versioning.

Không nên xem version là số thứ tự đơn giản. alpha, beta và stable có chính sách hỗ trợ khác nhau; resource version cũ có thể bị loại bỏ hoặc chuyển đổi. Client cần dùng API version mà cluster và thư viện cùng hỗ trợ.

### 2.2. kind

kind mô tả loại object:

    Pod
    Service
    Deployment
    ConfigMap
    Secret
    Role
    CustomResourceDefinition

API path và model typed thường được suy ra từ group, version, kind và plural resource name. Một kind viết đúng nhưng resource endpoint không được client hỗ trợ vẫn có thể dẫn đến lỗi.

### 2.3. Resource name và kind không hoàn toàn giống nhau

Tên kind là dạng số ít và thường viết hoa. URL API thường dùng resource name dạng số nhiều, chữ thường:

    kind: ConfigMap
    resource: configmaps

RBAC dùng resource name, không dùng kind. Đây là lý do rule đọc configmaps cần viết đúng resource dù manifest dùng kind ConfigMap.

## 3. metadata: identity và phạm vi

### 3.1. name và namespace

name định danh object trong scope của nó. Với resource namespaced, cùng một name có thể tồn tại ở namespace khác:

    order-service trong team-a
    order-service trong team-b

namespace là một phần của identity khi client gọi API. Code chỉ truyền name mà bỏ namespace có thể đọc nhầm context mặc định hoặc không tìm thấy object.

Một số resource cluster-scoped không dùng namespace, chẳng hạn Node hoặc ClusterRole. Client không nên gửi namespace vào endpoint của resource cluster-scoped nếu API không hỗ trợ.

### 3.2. generateName

generateName là tiền tố để API Server tạo tên duy nhất khi create object. Sau khi tạo, object có name thực tế. Ứng dụng không nên giả định name bằng generateName và cần đọc response create để biết tên được cấp.

### 3.3. UID

UID là identity duy nhất của một object trong cluster. Một object bị xóa rồi tạo lại với cùng name vẫn có UID khác. UID hữu ích khi:

- nhận biết event thuộc object nào;
- phân biệt replacement;
- tạo ownerReference;
- tránh xử lý lặp một object cũ.

Không dùng UID làm URL hoặc tên service cho client nghiệp vụ. UID là metadata kỹ thuật.

### 3.4. resourceVersion

resourceVersion biểu diễn phiên bản quan sát của object trong storage hoặc API semantics. Nó được dùng cho:

- optimistic concurrency;
- list rồi watch từ một điểm;
- phát hiện dữ liệu đã thay đổi;
- điều khiển consistency trong một số request.

resourceVersion không phải version ứng dụng và không nên hiển thị như release version. Client không nên tự tăng hoặc tự tạo resourceVersion. Hãy dùng giá trị API trả về.

### 3.5. generation

generation thường thay đổi khi spec mong muốn của object thay đổi. Controller có thể ghi observedGeneration vào status để cho biết đã xử lý đến generation nào.

Ví dụ khái niệm:

    metadata.generation: 4
    status.observedGeneration: 4

Khi hai giá trị chưa bằng nhau, controller có thể chưa reconcile xong. Không phải mọi kind đều dùng hai field này giống nhau, nên client cần đọc theo schema của resource.

### 3.6. labels và annotations

Labels dùng cho selector, grouping và truy vấn:

    app.kubernetes.io/name: order-service

Annotations chứa metadata không dùng để chọn backend. Cả hai là map string-to-string. Client cần xử lý trường hợp map vắng mặt, key không tồn tại và giá trị dài.

Không coi annotation là schema ổn định nếu controller sở hữu annotation đó. Một controller khác có thể cập nhật hoặc xóa metadata theo reconciliation.

### 3.7. ownerReferences

ownerReferences mô tả object sở hữu resource. ReplicaSet thường sở hữu Pod, Deployment sở hữu ReplicaSet. Khi owner bị xóa, garbage collector có thể xử lý dependent object theo propagation policy.

Nếu client tạo resource con, cần hiểu ownerReference và UID của owner. Không đặt owner bằng name không có UID. Không tự ghi đè ownerReference của controller khác.

## 4. spec và status

### 4.1. spec là desired state

spec mô tả điều người dùng hoặc controller muốn:

- Deployment muốn bao nhiêu replica;
- Pod muốn chạy image nào;
- Service muốn chọn label nào;
- ConfigMap muốn chứa key nào;
- Role muốn cấp verb nào.

spec có thể được defaulting hoặc normalization bởi API Server. Object trả về sau create có thể có thêm field mà manifest ban đầu không ghi.

### 4.2. status là observed state

status mô tả controller quan sát:

- Pod Ready hay chưa;
- Deployment có available replica không;
- Job đã hoàn tất chưa;
- custom controller đã reconcile đến đâu.

Ứng dụng không nên sửa status của resource nếu không phải controller sở hữu status đó. Với custom resource, controller thường được cấp subresource status riêng để tránh xung đột với spec.

### 4.3. Conditions

Condition thường có:

    type
    status
    reason
    message
    lastTransitionTime
    observedGeneration

Ví dụ type có thể là Available, Progressing hoặc Ready tùy resource. Không chỉ kiểm tra status bằng chuỗi “True” mà bỏ qua type, reason và observedGeneration.

Một condition False có thể là trạng thái tạm thời trong rollout. Cần đọc message, event và thời điểm trước khi kết luận lỗi lâu dài.

## 5. Kiểu dữ liệu Kubernetes thường gặp

### 5.1. String và enum

Nhiều field là string nhưng chỉ nhận một tập giá trị có ý nghĩa, chẳng hạn protocol HTTP, TCP hoặc policy type. Client không nên giả định mọi string đều tự do.

Khi gặp enum chưa biết, code cần có behavior an toàn: giữ lại giá trị để quan sát, log tên field và không làm mất object khi deserialize nếu thư viện cho phép.

### 5.2. Boolean và số

replicas, port, failureThreshold hoặc timeout có kiểu số, nhưng giới hạn và đơn vị khác nhau. Một giá trị số hợp lệ về JSON vẫn có thể không hợp lệ về Kubernetes semantics.

Ví dụ:

- port là số cổng;
- periodSeconds là giây;
- replicas là số Pod;
- resource quantity không phải số nguyên đơn giản.

Client cần kiểm tra range ở lớp domain nếu logic ứng dụng phụ thuộc.

### 5.3. Quantity

CPU và memory trong Kubernetes thường dùng dạng quantity:

    cpu: 500m
    memory: 256Mi
    storage: 10Gi

500m CPU nghĩa là nửa CPU theo quy ước quantity, không phải 500 CPU. Mi và Gi là đơn vị nhị phân thường gặp; M và G có quy ước khác. Không parse quantity bằng cách bỏ chữ rồi dùng số nguyên.

Client Java nên dùng parser hoặc model quantity của thư viện thay vì tự viết logic:

- giữ nguyên giá trị khi chỉ cần chuyển tiếp;
- parse bằng thư viện khi cần so sánh;
- tránh làm tròn làm thay đổi ý nghĩa;
- kiểm tra overflow với resource lớn.

### 5.4. IntOrString

Một số field Kubernetes cho phép số hoặc chuỗi, điển hình targetPort:

    targetPort: 8080

hoặc:

    targetPort: http

Client phải phân biệt hai dạng. Nếu code chỉ ép sang integer, tên port sẽ lỗi. Nếu code chỉ coi mọi giá trị là string, logic so sánh số có thể sai.

### 5.5. Duration và timestamp

Kubernetes có field đếm giây như periodSeconds và field timestamp theo định dạng thời gian chuẩn. Không trộn thời điểm tuyệt đối với khoảng thời gian.

Khi log hoặc so sánh:

- parse timestamp có timezone rõ;
- dùng clock ổn định cho timeout;
- không dùng thời gian máy local để suy ra thứ tự event nếu clock có thể lệch;
- giữ raw value khi cần audit.

### 5.6. Map và list

data của ConfigMap và Secret là map key-value. containers, ports, volumes và conditions là list. Field có thể vắng mặt, có list rỗng hoặc có duplicate tùy validation.

Code an toàn cần phân biệt:

    field không tồn tại
    field tồn tại nhưng null
    field tồn tại với list rỗng
    field tồn tại với phần tử

Không gọi phần tử đầu tiên của list mà không kiểm tra rỗng.

## 6. List, WatchEvent và Status response

### 6.1. List response

Khi list resource, API thường trả object dạng List:

    apiVersion: v1
    kind: PodList
    metadata:
      resourceVersion: "12345"
    items:
      - metadata:
          name: order-service-a

List metadata có resourceVersion dùng làm điểm tham chiếu cho watch hoặc consistency. items có thể rỗng mà request vẫn thành công.

List có thể dùng pagination qua continue token. Client không nên giả định một lần list trả toàn bộ resource trong namespace lớn.

### 6.2. Watch event

Watch thường phát event với type và object:

    ADDED
    MODIFIED
    DELETED
    BOOKMARK
    ERROR

ADDED hoặc MODIFIED không có nghĩa object sẵn sàng phục vụ. Client phải đọc object và điều kiện liên quan. DELETED có thể cần xóa khỏi cache. ERROR cần được xử lý theo status object.

### 6.3. Status response

Lỗi API thường trả object kind Status thay vì resource business:

    apiVersion: v1
    kind: Status
    status: Failure
    message: ...
    reason: Forbidden
    code: 403

Client không nên deserialize mọi response vào Deployment, Pod hoặc ConfigMap. Hãy nhận biết HTTP status và content kind trước khi map.

## 7. Cấu trúc lỗi Status

Một lỗi Kubernetes API thường có các phần:

| Field | Ý nghĩa |
| --- | --- |
| status | Thường là Failure khi request không thành công |
| message | Mô tả chi tiết cho người đọc |
| reason | Nhóm nguyên nhân như Forbidden, NotFound hoặc Conflict |
| code | HTTP status code |
| details | Resource, name, group hoặc retry information |
| causes | Các nguyên nhân con, thường hữu ích với lỗi validation |

Client nên giữ code, reason và resource context trong exception domain. Message có thể thay đổi theo phiên bản hoặc admission plugin, nên không dùng toàn bộ message làm điều kiện logic duy nhất.

Ví dụ, cùng code 422 có thể chứa nhiều cause cho các field khác nhau. UI hoặc log cần hiển thị causes theo cách an toàn, còn retry policy nên dựa vào nhóm lỗi đã phân loại.

## 8. Phân loại lỗi theo HTTP code

### 8.1. 400 Bad Request

Request không đúng cú pháp hoặc tham số không hợp lệ. Nguyên nhân có thể là:

- query parameter sai;
- JSON không parse được;
- field không đúng kiểu;
- resource name hoặc label selector sai cú pháp.

Đây thường là lỗi cần sửa code hoặc input, không retry y nguyên request. Client nên log tên operation, resource và validation cause, không log Secret.

### 8.2. 401 Unauthorized

API Server không xác thực được danh tính. Có thể do:

- token thiếu hoặc hết hạn;
- certificate không hợp lệ;
- kubeconfig sai;
- client dùng credential của môi trường khác.

Retry ngay lập tức thường không giải quyết được. Cần refresh credential theo cơ chế được cấp phép hoặc đánh dấu integration unavailable. Không in token vào exception.

### 8.3. 403 Forbidden

Danh tính đã được nhận biết nhưng không có quyền thực hiện operation. Đây là lỗi RBAC hoặc admission policy cần điều tra:

- ServiceAccount nào đang được Pod dùng;
- namespace nào;
- resource và verb nào bị từ chối;
- RoleBinding trỏ đến subject nào;
- client có cần list/watch thay vì chỉ get không.

Không retry vô hạn và không cấp cluster-admin như một cách sửa tắt.

### 8.4. 404 Not Found

Resource hoặc endpoint không tồn tại. Các nguyên nhân thường gặp:

- sai name;
- sai namespace;
- resource đã bị xóa;
- API group/version không đúng;
- client gọi endpoint không được cluster hỗ trợ.

Trong controller, 404 khi đọc dependent resource có thể là trạng thái bình thường nếu object đã bị xóa. Trong request nghiệp vụ, 404 có thể là cấu hình sai. Cần phân biệt expected absence với lỗi hệ thống.

### 8.5. 409 Conflict

Resource đã thay đổi hoặc thao tác vi phạm trạng thái hiện tại. Conflict thường xảy ra khi:

- update dùng resourceVersion cũ;
- hai controller cùng sửa object;
- create trùng tên;
- finalizer hoặc deletion đang diễn ra.

Cách xử lý phổ biến:

1. Đọc object mới nhất.
2. Merge thay đổi của mình vào field được sở hữu.
3. Gửi update hoặc patch mới.
4. Giới hạn số lần retry.

Không dùng update toàn object từ bản cache cũ vì có thể ghi đè thay đổi của controller khác.

### 8.6. 422 Unprocessable Entity

Server hiểu request nhưng validation không chấp nhận dữ liệu. causes thường chỉ ra field sai:

- selector không hợp lệ;
- field bắt buộc thiếu;
- resource quantity sai;
- immutable field bị đổi;
- admission webhook từ chối object.

Đây là lỗi cần sửa input hoặc manifest. Retry không thay đổi payload sẽ tiếp tục thất bại.

### 8.7. 429 Too Many Requests

API Server hoặc một lớp trung gian đang giới hạn tốc độ. Client nên:

- tôn trọng Retry-After nếu được trả;
- dùng exponential backoff có jitter;
- giảm polling;
- dùng list-watch hoặc cache khi phù hợp;
- giới hạn concurrency;
- theo dõi request rate.

Retry đồng loạt không có jitter có thể tạo thundering herd sau khi API phục hồi.

### 8.8. 500, 502, 503 và 504

Đây là nhóm lỗi server hoặc đường mạng:

- 500: lỗi nội bộ;
- 502: gateway hoặc proxy không nhận response hợp lệ;
- 503: service tạm không sẵn sàng;
- 504: gateway timeout.

Có thể retry với backoff nếu operation idempotent và đã giới hạn attempts. Với create hoặc patch có tác dụng phụ, cần biết request đã được server xử lý chưa trước khi gửi lại.

## 9. Lỗi validation và causes

Khi tạo hoặc cập nhật object, response có thể cho biết field gây lỗi:

    details:
      causes:
        - field: spec.template.spec.containers[0].image
          reason: FieldValueInvalid
          message: ...

Client nên map causes thành lỗi có cấu trúc:

    resource = Deployment
    namespace = team-a
    name = order-service
    field = spec.template.spec.containers[0].image
    reason = FieldValueInvalid

Không chỉ trả về “API call failed”. Người vận hành cần biết object nào, field nào và request có nên retry không.

## 10. Lỗi khi deserialize và tương thích schema

### 10.1. Unknown field

Cluster có thể trả field mới hơn model client. Tùy serializer, field lạ có thể bị bỏ qua hoặc gây lỗi. Khi nâng cluster hoặc client:

- kiểm tra chính sách unknown field;
- test resource có field mới;
- không làm mất field khi read-modify-write;
- dùng unstructured model khi cần forward compatibility.

### 10.2. Null, thiếu field và giá trị mặc định

JSON thiếu field, field null và field rỗng có thể mang ý nghĩa khác nhau. API Server cũng có thể default field khi create. Code phải tránh:

- unbox null thành primitive gây exception;
- coi list null là list rỗng mà không hiểu semantics;
- ghi lại object với field null làm xóa giá trị;
- bỏ qua default đã được server thêm.

### 10.3. Typed và unstructured

| Mô hình | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Typed model | Compile-time, code rõ, IDE hỗ trợ | Phụ thuộc schema và version |
| Unstructured map | Linh hoạt với CRD và field mới | Dễ sai path, type và null |
| Raw JSON | Kiểm soát payload | Nhiều code parse và validation |

Resource chuẩn ổn định thường phù hợp typed model. CRD hoặc controller cần forward compatibility có thể cần unstructured kết hợp validation riêng.

## 11. Conflict và optimistic concurrency

Kubernetes có thể được nhiều actor sửa cùng object:

    controller A
    controller B
    operator
    client nghiệp vụ

Nếu client đọc object rồi update toàn bộ sau một khoảng thời gian, resourceVersion có thể đã thay đổi. API trả Conflict để bảo vệ cập nhật mới hơn.

Chiến lược an toàn:

- chỉ sở hữu field của mình;
- dùng patch có phạm vi nhỏ;
- đọc lại trước khi retry;
- tôn trọng managed fields hoặc field ownership nếu dùng apply;
- giới hạn attempts;
- ghi metric conflict.

Không dùng retry vô hạn. Conflict lặp lại có thể cho thấy hai controller đang tranh cùng một field.

## 12. Create, update, patch và apply

Các operation không thay thế nhau:

| Operation | Ý nghĩa | Rủi ro chính |
| --- | --- | --- |
| Create | Tạo object mới | Trùng name, request retry có thể tạo duplicate hoặc conflict |
| Update | Ghi object đầy đủ theo resourceVersion | Dễ ghi đè field của actor khác |
| Patch | Sửa một phần | Patch type sai hoặc path không tồn tại |
| Apply | Khai báo field ownership và desired state | Conflict field manager, thay đổi ownership |
| Delete | Xóa object | Controller hoặc garbage collector có thể tạo/xóa object liên quan |

Client cần chọn operation theo ownership. Nếu chỉ cần đổi một field do mình sở hữu, patch hẹp thường an toàn hơn update toàn object cache cũ.

## 13. Watch error và reconnect

Watch không phải một kết nối tồn tại vĩnh viễn. Client phải xử lý:

- HTTP error trước khi stream bắt đầu;
- ERROR event trong stream;
- stream đóng bình thường;
- timeout;
- resource version quá cũ;
- network interruption;
- duplicate hoặc event đến sau reconnect.

Quy trình khái quát:

    list resource
        → lưu items và resourceVersion
        → mở watch từ điểm phù hợp
        → xử lý ADDED, MODIFIED, DELETED
        → gặp lỗi hoặc disconnect
        → resync list
        → mở watch mới

Khi watch báo resource version quá cũ, client cần list lại thay vì cố dùng version cũ. Cache phải có cách xử lý khoảng thời gian giữa list và watch.

## 14. Lỗi trong Spring Cloud Kubernetes integration

Khi integration Spring báo lỗi, cần phân biệt:

| Lớp lỗi | Ví dụ | Cách điều tra |
| --- | --- | --- |
| Spring binding | property không bind được | tên key, kiểu dữ liệu, source priority |
| Client HTTP | timeout, TLS | endpoint API, CA, network |
| Kubernetes API | 401, 403, 404 | ServiceAccount, RBAC, name, namespace |
| Integration | không có instance hoặc refresh không chạy | module, provider, cache, watcher |
| Bean lifecycle | property đổi nhưng bean giữ giá trị cũ | refresh scope, recreate hoặc rollout |

Không chuyển mọi exception thành “Kubernetes unavailable”. Giữ nguyên cause chain ở log nội bộ và map ra thông báo vận hành không chứa Secret.

Ví dụ, ConfigMap get thành công nhưng property bind fail là lỗi Spring configuration, không phải RBAC. Ngược lại, property không xuất hiện vì client nhận 403 là lỗi quyền hoặc danh tính.

## 15. Kiểu dữ liệu custom resource

CRD có schema riêng và có thể có:

- spec domain;
- status do controller sở hữu;
- conditions;
- printer columns;
- versions;
- conversion webhook.

Client typed chỉ hoạt động thuận tiện khi có model tương ứng. Với CRD động, unstructured hoặc model sinh tự động có thể phù hợp hơn.

Khi làm việc với CRD:

1. Đọc group, version, plural và scope.
2. Xác nhận resource namespaced hay cluster-scoped.
3. Kiểm tra schema OpenAPI.
4. Phân biệt spec và status.
5. Theo dõi condition và observedGeneration.
6. Không update status qua endpoint spec.

Lỗi 404 có thể do CRD chưa được cài hoặc client gọi sai version, không nhất thiết object cụ thể bị mất.

## 16. Log lỗi và bảo mật

Một lỗi API nên ghi đủ context:

    operation=get
    resource=configmaps
    namespace=team-a
    name=order-service-config
    statusCode=403
    reason=Forbidden

Không ghi:

- bearer token;
- Secret data;
- toàn bộ Authorization header;
- payload có credential;
- kubeconfig.

Với lỗi validation, field path thường an toàn nhưng vẫn cần kiểm tra message để tránh message chứa giá trị Secret. Với lỗi ConfigMap hoặc Secret, log tên resource và status, không log nội dung data.

## 17. Capability và error matrix

Khi chọn client, nên ghi cả capability và lỗi cần xử lý:

| Capability | Thành công | Lỗi chính | Retry? |
| --- | --- | --- | --- |
| Get ConfigMap | object hoặc data | 403, 404, timeout | timeout có giới hạn; 403 không |
| List Service | ServiceList | 403, 429 | 429 có backoff |
| Watch EndpointSlice | event stream | 410, disconnect | list lại và reconnect |
| Patch Deployment | object mới | 409, 422, 403 | 409 đọc lại; 422 không |
| Read Secret | object | 403, 404 | không retry vô hạn |
| Discovery refresh | instance list | cache stale, API lỗi | fallback theo thiết kế |

Matrix này làm rõ client không chỉ “hỗ trợ API”, mà còn cần behavior khi API trả lỗi.

## 18. Những hiểu nhầm thường gặp

**“JSON trả về có field là mọi client đều đọc được.”** Client còn phụ thuộc model, apiVersion, serializer và resource scope.

**“resourceVersion là version ứng dụng.”** Nó phục vụ consistency và concurrency của API, không phải release version.

**“404 luôn là lỗi nghiêm trọng.”** Trong controller, dependent object bị xóa có thể là trạng thái bình thường. Trong config bắt buộc, 404 lại cần fail-fast.

**“403 có thể giải quyết bằng retry.”** 403 thường là thiếu RBAC. Cần sửa danh tính, namespace, resource hoặc verb.

**“Update toàn object là cách an toàn nhất.”** Update từ object cũ có thể ghi đè thay đổi của controller khác. Patch hoặc read-merge-update có thể phù hợp hơn.

**“Watch là stream không bao giờ cần tạo lại.”** Watch có thể đóng, hết resource version hoặc mất kết nối. Client cần reconnect và resync.

**“Quantity là số.”** CPU và memory có suffix, scale và đơn vị riêng. Cần parser đúng.

**“Status là nơi ứng dụng muốn Kubernetes làm gì.”** spec là desired state; status là observed state do controller ghi.

## 19. Checklist xử lý response Kubernetes API

### Trước khi gọi

- [ ] Biết group, version, kind và resource plural.
- [ ] Biết resource namespaced hay cluster-scoped.
- [ ] Có timeout và giới hạn concurrency.
- [ ] ServiceAccount có quyền đúng.

### Khi nhận thành công

- [ ] Deserialize đúng object hoặc List type.
- [ ] Kiểm tra object có tồn tại, list có rỗng không.
- [ ] Lưu resourceVersion nếu cần watch hoặc concurrency.
- [ ] Không coi object đã tạo là đã Ready.

### Khi nhận lỗi

- [ ] Giữ HTTP code, reason, message và causes.
- [ ] Phân loại expected absence, validation, permission và transient failure.
- [ ] Không retry 400, 401, 403, 422 y nguyên vô hạn.
- [ ] Dùng backoff cho 429 và lỗi mạng phù hợp.
- [ ] Xử lý 409 bằng đọc lại và merge có giới hạn.
- [ ] Không log token, Secret hoặc payload nhạy cảm.

### Khi dùng watch

- [ ] Xử lý ADDED, MODIFIED, DELETED và ERROR.
- [ ] Có resync khi version quá cũ.
- [ ] Có reconnect sau disconnect.
- [ ] Cache có giới hạn tuổi và metric stale.

## 20. Tự kiểm tra mức độ hiểu

**Câu 1: spec và status khác nhau thế nào?**

spec là trạng thái mong muốn do người dùng hoặc controller cấp trên khai báo. status là trạng thái quan sát được do Kubernetes hoặc controller cập nhật.

**Câu 2: resourceVersion dùng để làm gì?**

Nó hỗ trợ consistency, optimistic concurrency và liên kết list với watch. Nó không phải version của image hoặc release ứng dụng.

**Câu 3: Vì sao targetPort cần kiểu IntOrString?**

Vì targetPort có thể là số cổng như 8080 hoặc tên port như http. Client phải xử lý cả hai dạng.

**Câu 4: 403 và 404 khác nhau thế nào?**

403 nghĩa là danh tính được nhận biết nhưng không được phép thực hiện thao tác. 404 nghĩa là resource hoặc endpoint không được tìm thấy trong phạm vi đang gọi, thường do sai tên, namespace, version hoặc object đã bị xóa.

**Câu 5: Khi nào retry Conflict?**

Khi client có thể đọc object mới nhất, merge field mình sở hữu và gửi lại với giới hạn attempts. Không retry update toàn object cũ vì có thể ghi đè thay đổi của actor khác.

**Câu 6: Watch bị đóng thì làm gì?**

Đọc nguyên nhân, resync bằng list nếu cần, lấy resourceVersion phù hợp và mở watch mới. Không giả định cache vẫn phản ánh cluster.

**Câu 7: Vì sao client Spring nhận được ConfigMap nhưng bean chưa đổi?**

Vì nhận event hoặc cập nhật source chưa đủ; bean phải có cơ chế refresh hoặc được tạo lại. Nếu lifecycle không hỗ trợ, cần rollout hoặc cách áp dụng khác.

## Kết luận

Kubernetes API có object model giàu ngữ nghĩa: apiVersion, kind, metadata, spec, status, condition, resourceVersion, generation, list và watch event đều ảnh hưởng đến cách client phải đọc và cập nhật resource. Hiểu đúng kiểu dữ liệu giúp tránh lỗi parse quantity, null, IntOrString, namespace và schema version.

Lỗi API cũng cần được xem như dữ liệu có cấu trúc. HTTP code, reason, details và causes cho biết nên sửa input, sửa RBAC, đọc lại để giải quyết conflict, backoff vì rate limit hay reconnect watch. Khi client Java và integration Spring giữ được ngữ nghĩa này, DiscoveryClient, ConfigMap, Secret, LoadBalancer và Configuration Watcher sẽ có behavior dễ quan sát và an toàn hơn.
