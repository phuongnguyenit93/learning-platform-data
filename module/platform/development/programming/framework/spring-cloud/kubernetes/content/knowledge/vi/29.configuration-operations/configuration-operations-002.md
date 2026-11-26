# Đối chiếu trạng thái khai báo với trạng thái đang chạy

## 1. Mục tiêu và tình huống

Trong chương **Vận hành cấu hình** của module **SPRING_CLOUD_KUBERNETES**, bài này giải quyết câu hỏi: cấu hình đã được khai báo và cập nhật trên Kubernetes có thực sự là cấu hình mà từng replica Spring đang sử dụng hay không?

Sau bài học, bạn có thể:

- Phân biệt nguồn khai báo, tài nguyên trong API, dữ liệu tới Pod và cấu hình có hiệu lực trong ứng dụng.
- Xác định lớp đầu tiên xuất hiện sai lệch thay vì liên tục apply hoặc restart.
- Đối chiếu theo từng Pod, phiên bản cấu hình và nhóm triển khai.
- Thiết kế thông tin quan sát an toàn để không phải công khai toàn bộ cấu hình hoặc Secret.
- Chọn cách khắc phục phù hợp: sửa nguồn, refresh, rollout hoặc khôi phục phiên bản cấu hình.

Ví dụ xuyên suốt: `orders-api` có ba replica. Nhóm vận hành muốn đổi cấu hình hiển thị từ `display-v41` sang `display-v42`, đồng thời bật gợi ý sản phẩm. ConfigMap đã có dữ liệu mới và cả ba Pod đều Ready, nhưng người dùng vẫn nhận hành vi cũ ở một số request.

**Ready, Running hoặc apply thành công là bằng chứng về một phần của hệ thống. Chúng chưa chứng minh mọi replica đang dùng đúng cấu hình nghiệp vụ.**

Các ví dụ thao tác dành cho namespace lab `config-ops-lab`. Tên revision và thông tin endpoint trong bài là quy ước do ứng dụng thiết kế, không phải trường quản lý cấu hình mà Spring Cloud Kubernetes tự sinh.

## 2. Chuỗi trạng thái cần đối chiếu

Kubernetes phân biệt trạng thái mong muốn của đối tượng và trạng thái được hệ thống quan sát. Với cấu hình ứng dụng, còn phải xét các lớp bên trong tiến trình Spring. Xem [Objects In Kubernetes](https://kubernetes.io/docs/concepts/overview/working-with-objects/).

~~~mermaid
flowchart TD
    A["Nguồn được duyệt: Git, values, cấu hình môi trường"]
    B["Manifest đã render cho đúng cluster/namespace"]
    C["Đối tượng hiện có trong Kubernetes API"]
    D["Dữ liệu Pod nhận: env, volume hoặc API client"]
    E["Spring Environment và đối tượng đã bind"]
    F["Thành phần nghiệp vụ thực sự sử dụng"]
    A --> B --> C --> D --> E --> F
~~~

| Lớp | Câu hỏi đối chiếu | Bằng chứng phù hợp |
| --- | --- | --- |
| Nguồn được duyệt | Thay đổi mong muốn là gì và áp dụng cho môi trường nào? | Commit, change record, giá trị môi trường được duyệt |
| Manifest render | Công cụ đã tạo đúng tên nguồn, namespace và tham chiếu chưa? | Kết quả render của đúng overlay/values |
| Đối tượng API | Cluster hiện đang lưu gì? | GET tài nguyên đúng context/namespace |
| Dữ liệu tới Pod | Tiến trình nhận được env/tệp hoặc kết quả API nào? | Quan sát ở đúng Pod và đúng nguồn |
| Spring | Giá trị nào thắng trong Environment; bean đã bind thành gì? | Endpoint/telemetry có chọn lọc, thông tin nguồn |
| Nghiệp vụ | Request đang dùng chính sách/client/pool nào? | Snapshot hoạt động, phiên bản đã áp dụng, phép kiểm tra hành vi |

### 2.1. Sai lệch khai báo và sai lệch áp dụng là hai việc khác nhau

**Sai lệch khai báo:** nguồn được duyệt yêu cầu v42 nhưng API vẫn đang lưu v41. Có thể do sai context, render sai môi trường, pipeline chưa áp dụng hoặc một chủ thể khác sửa tài nguyên.

**Sai lệch áp dụng:** API có v42 nhưng một tiến trình vẫn dùng v41. Có thể do env chỉ được tạo khi container khởi động, volume chưa cập nhật, chưa refresh bean hoặc thành phần nghiệp vụ giữ lại giá trị cũ.

Hai loại sai lệch cần hành động khác nhau. Refresh ứng dụng không đưa manifest chưa được apply vào cluster. Apply lại một ConfigMap không tự làm một singleton đọc lại giá trị đã chụp lúc khởi tạo.

### 2.2. Không coi một lần đọc là ảnh chụp nguyên tử toàn hệ thống

API, kubelet, Spring và các replica không được đọc cùng một thời điểm trong quy trình chẩn đoán. Một mẫu có thể nằm giữa quá trình cập nhật hợp lệ.

Vì vậy, cần ghi thời điểm quan sát, xác định rollout/refresh còn diễn ra không và lấy lại mẫu sau một khoảng ổn định theo chính sách của hệ thống. Không gọi mọi khác biệt tức thời là lỗi kéo dài.

Nếu có nhiều đợt thay đổi chồng nhau, chốt revision mục tiêu trước khi kết luận. Không so trạng thái lấy lúc bắt đầu triển khai v42 với nguồn đã chuyển sang v43.

## 3. Xác định danh tính và phiên bản cần so sánh

### 3.1. Chọn đơn vị đối chiếu

Một báo cáo theo replica nên có:

| Thông tin | Mục đích |
| --- | --- |
| Cluster/context, namespace, workload | Tránh đối chiếu nhầm môi trường |
| Pod name và Pod UID | Phân biệt các đời Pod dù tên có thể giống nhau |
| Container, số lần restart, thời điểm tiến trình bắt đầu nếu có | Phân biệt Pod tồn tại lâu với JVM mới khởi động |
| Image và image ID/digest quan sát được | Xác định mã đang chạy |
| Revision cấu hình mục tiêu | Mốc thay đổi được duyệt |
| Revision và giá trị an toàn trong Spring | Xác định cấu hình đã được nạp |
| Revision và giá trị đang hoạt động | Xác định trạng thái phục vụ thực tế |
| Thời điểm lấy mẫu và lỗi quan sát | Đánh giá tính mới của bằng chứng |

Cùng Pod UID không có nghĩa cùng đời tiến trình: container có thể đã restart trong Pod đó. Cùng image tag cũng chưa đủ định danh nội dung image nếu tag được phép thay đổi.

### 3.2. Không đánh đồng các loại revision

| Dấu hiệu | Có thể cho biết | Không chứng minh |
| --- | --- | --- |
| Commit/config release ID | Nguồn được duyệt | Pod đã áp dụng nguồn đó |
| ConfigMap `resourceVersion` | Phiên bản đối tượng để đối chiếu/giao thức API | Mức mới của cấu hình trong mọi JVM |
| Deployment `metadata.generation` | Thế hệ mong muốn của đối tượng Deployment | Bean đã nhận ConfigMap mới |
| Deployment `status.observedGeneration` | Thế hệ controller đã quan sát | Tất cả chức năng đã dùng đúng cấu hình |
| `pod-template-hash` | Nhận diện template liên quan tới ReplicaSet | Hash nội dung ConfigMap được tham chiếu |
| Annotation revision/checksum do pipeline đặt | Ý định hoặc dấu vết triển khai | Thành phần nghiệp vụ đã áp dụng thành công |
| Revision do runtime báo sau khi áp dụng | Trạng thái mà thành phần báo đã chấp nhận | Mọi replica khác cũng đồng bộ |

`observedGeneration`, số replica updated, ready và available có ý nghĩa riêng trong Deployment status. Xem [Deployment API](https://kubernetes.io/docs/reference/kubernetes-api/apps/deployment-v1/).

Không dùng phép lớn hơn/nhỏ hơn trên `resourceVersion` của những đối tượng khác nhau để suy ra thứ tự cấu hình nghiệp vụ. Nó không thay thế revision ứng dụng được quản lý rõ ràng.

### 3.3. Marker phải đi cùng giá trị thực

Với cấu hình không nhạy cảm, dùng marker dễ đọc, chẳng hạn:

~~~yaml
orders:
  display:
    revision: "display-v42"
    show-recommendations: true
~~~

Nhưng chỉ revision đúng chưa đủ. Một nguồn ưu tiên cao hơn có thể ghi đè riêng `show-recommendations` mà giữ nguyên revision.

Đối chiếu ít nhất cặp:

~~~text
revision = display-v42
showRecommendations = true
~~~

Với tập cấu hình lớn hơn, có thể tạo fingerprint cho một danh sách trường **không nhạy cảm** đã chuẩn hóa kiểu dữ liệu và thứ tự. Đừng hash toàn bộ Environment rồi công khai: hash của giá trị bí mật đơn giản vẫn có thể tạo điều kiện dò đoán.

Nếu có nhiều ConfigMap/Secret độc lập, cần danh tính cho từng nguồn hoặc một bộ phiên bản được phát hành cùng nhau. Một marker ở ConfigMap A không chứng minh Secret B đã được cập nhật.

## 4. Ví dụ khai báo và đường tiêu thụ cấu hình

### 4.1. ConfigMap mục tiêu

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-display
  namespace: config-ops-lab
data:
  application.yaml: |-
    orders:
      display:
        revision: "display-v42"
        show-recommendations: true
~~~

Đây là cấu hình hiển thị không chứa bí mật. Không đưa password hoặc token vào ConfigMap để tiện đối chiếu.

### 4.2. Trường hợp đọc tệp qua Config Data

Đoạn sau là phần cần ghép vào Deployment lab đã có image và những trường bắt buộc khác:

~~~yaml
spec:
  template:
    metadata:
      annotations:
        config.example.com/target-revision: "display-v42"
    spec:
      containers:
        - name: orders-api
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "file:/etc/orders/application.yaml"
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_UID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
          volumeMounts:
            - name: display-config
              mountPath: /etc/orders
              readOnly: true
      volumes:
        - name: display-config
          configMap:
            name: orders-display
~~~

Mẫu không dùng `subPath`. Annotation `config.example.com/target-revision` là quy ước do pipeline quản lý; nó không phải xác nhận của JVM.

Có hai hành động độc lập:

1. Đổi nội dung ConfigMap.
2. Đổi annotation trong Pod template.

Kubernetes rollout khi Pod template thay đổi. Chỉ đổi ConfigMap tham chiếu, trong khi template giữ nguyên, không tự tạo cùng hiệu ứng. Xem [Updating a Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#updating-a-deployment).

Nếu annotation được đổi sang v42 trong một rollout, nó đánh dấu Pod dự định nhận v42; vẫn phải kiểm chứng dữ liệu và trạng thái hoạt động.

### 4.3. Trường hợp nạp ConfigMap qua Kubernetes API

Khi dùng Spring Cloud Kubernetes PropertySource, kiểm tra dependency, client, cơ chế import và cấu hình nguồn đúng phiên bản. Nhánh tài liệu hiện hành mô tả `spring.config.import: "kubernetes:"` cho Config Data. Xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

Trong hồ sơ đối chiếu, ghi rõ:

- Tên ứng dụng dùng để tìm nguồn.
- ConfigMap name và namespace thực tế.
- Danh sách `sources`, nguồn theo label hoặc profile nếu có.
- Cách đọc theo tên hay theo tập tài nguyên.
- Có nguồn cũ hoặc nguồn khác trùng khóa không.
- Refresh dùng cơ chế nào, áp dụng cho những bean nào.

Không đồng thời dùng hai đường nhập cùng nguồn rồi suy đoán thứ tự thắng. Nếu có nhiều đường, phải ghi rõ ý định và kiểm tra precedence thực tế.

ConfigMap PropertySource có quy tắc chọn tên và nhiều nguồn cấu hình; không phải cứ có ConfigMap đúng tên trong cluster là ứng dụng đang đọc nó. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

## 5. Đối chiếu từ nguồn khai báo tới từng Pod

Các lệnh sau là hướng dẫn cho lab; bài viết không thực thi chúng trên cluster.

### 5.1. Chốt môi trường và revision mục tiêu

~~~powershell
kubectl config current-context
kubectl -n config-ops-lab get deployment orders-api
kubectl -n config-ops-lab get configmap orders-display -o jsonpath='{.metadata.uid}'
kubectl -n config-ops-lab get configmap orders-display -o jsonpath='{.metadata.resourceVersion}'
~~~

Tiếp theo, đối chiếu nguồn được duyệt với bản đã render cho đúng môi trường. Với manifest chỉ chứa tài nguyên không nhạy cảm, có thể dùng:

~~~powershell
kubectl -n config-ops-lab diff -f .\orders-display.yaml
~~~

`kubectl diff` so trạng thái online với cấu hình dự kiến nếu apply; mã thoát 0 là không có khác biệt, 1 là có khác biệt, lớn hơn 1 là lỗi. Đây không phải phép kiểm tra cấu hình trong JVM. Xem [kubectl diff](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_diff/).

Tên tệp trên là tệp manifest do người thực hành chuẩn bị. Không dùng diff tràn cả thư mục có Secret rồi lưu đầu ra vào log CI không được bảo vệ. Cần so theo phạm vi và tránh nhầm metadata mặc định/controller quản lý với trường cấu hình do nhóm sở hữu.

Với ConfigMap minh họa không nhạy cảm, có thể lấy nội dung đang lưu bằng PowerShell:

~~~powershell
$configMapState = kubectl -n config-ops-lab get configmap orders-display -o json | ConvertFrom-Json
$configMapState.data.'application.yaml'
~~~

GET thành công ở bước này chứng minh API trả dữ liệu đó cho người vận hành. Nó chưa chứng minh ServiceAccount ứng dụng đọc được hoặc đã dùng dữ liệu đó.

### 5.2. Kiểm tra Deployment và các nhóm Pod

~~~powershell
$deploymentState = kubectl -n config-ops-lab get deployment orders-api -o json | ConvertFrom-Json

[pscustomobject]@{
  Generation = $deploymentState.metadata.generation
  ObservedGeneration = $deploymentState.status.observedGeneration
  DesiredReplicas = $deploymentState.spec.replicas
  UpdatedReplicas = $deploymentState.status.updatedReplicas
  ReadyReplicas = $deploymentState.status.readyReplicas
  AvailableReplicas = $deploymentState.status.availableReplicas
}

kubectl -n config-ops-lab get replicasets -l app=orders-api
kubectl -n config-ops-lab get pods -l app=orders-api -o wide
kubectl -n config-ops-lab rollout status deployment/orders-api --timeout=180s
~~~

Sau khi chọn Pod, kiểm tra owner reference tới ReplicaSet và Deployment mong muốn. Label ứng dụng chỉ là bước tìm ban đầu, có thể trùng với workload khác.

Trong rolling update có thể tồn tại Pod cũ, Pod mới, Pod chưa Ready và Pod đang kết thúc. Phân nhóm rõ trước khi kết luận:

| Nhóm | Cách đánh giá |
| --- | --- |
| Pod mới dự kiến phục vụ v42 | Phải nhận đúng dữ liệu và runtime v42 theo hạn hội tụ |
| Pod cũ còn trong giai đoạn chuyển tiếp | Có thể còn v41 trong cửa sổ được chấp nhận |
| Canary có mục tiêu riêng | So với revision được gán cho nhóm canary |
| Pod không thuộc workload | Không gộp vào báo cáo |
| Pod đang kết thúc | Ghi riêng tình trạng còn phục vụ/lưu lượng đang xử lý |
| Pod không lấy được bằng chứng | Đánh dấu thiếu bằng chứng, không tự tính là khớp |

Nếu mọi Pod Ready nhưng có hai revision đang phục vụ ngoài kế hoạch, đó vẫn là vấn đề cấu hình cần điều tra.

### 5.3. Kiểm tra dữ liệu thực sự đến Pod

Đường tiêu thụ quyết định điều cần quan sát:

| Đường tiêu thụ | Điều phải kiểm tra |
| --- | --- |
| Biến môi trường | Giá trị trong đời container hiện tại; tham chiếu nguồn trong PodSpec |
| Volume | Đường mount, nội dung không nhạy cảm, `subPath`, thời điểm quan sát |
| Kubernetes API client | Danh tính, namespace/name/selector và kết quả đồng bộ của ứng dụng |
| Config Data trong Spring | Import thực tế và PropertySource thắng |
| Nhiều nguồn cùng khóa | Thứ tự ưu tiên và giá trị cuối cùng |

ConfigMap đưa vào env không tự cập nhật biến môi trường của tiến trình. Volume thông thường cập nhật trễ; `subPath` không nhận cập nhật tự động. Xem [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Với image có công cụ `cat` và chỉ với tệp lab không nhạy cảm:

~~~powershell
kubectl -n config-ops-lab exec pod/orders-api-example -- cat /etc/orders/application.yaml
~~~

Thay `orders-api-example` bằng tên Pod đã xác minh. Image tối giản có thể không có công cụ này; khi đó dùng cơ chế quan sát ứng dụng đã chuẩn bị. Không bật shell đặc quyền chỉ để xem một tệp cấu hình.

Không chạy `printenv` toàn bộ, không in tệp Secret và không dump token vào biên bản kiểm tra. Đối với nguồn nhạy cảm, dùng thông tin phiên bản/định danh không tiết lộ giá trị và phép kiểm tra chức năng được phép.

## 6. Đối chiếu trong Spring và thành phần nghiệp vụ

### 6.1. Environment không phải trạng thái cuối của mọi bean

Spring Boot có nhiều nguồn cấu hình và quy tắc precedence. Biến môi trường, system property hoặc command-line argument có thể ghi đè giá trị từ Config Data. Xem [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Ví dụ:

~~~text
ConfigMap:
  revision = display-v42
  show-recommendations = true

Một biến môi trường có ưu tiên cao hơn:
  ORDERS_DISPLAY_SHOW_RECOMMENDATIONS=false

Environment cuối cùng:
  revision = display-v42
  show-recommendations = false
~~~

Tùy cơ chế bootstrap/Config Data và phiên bản, cần kiểm tra đúng vị trí nguồn Kubernetes trong chuỗi PropertySource. Không áp một thứ tự nhớ từ cấu hình cũ cho mọi dự án.

Có ba mốc cần tách:

1. **Environment:** lần đọc thuộc tính hiện tại trả gì?
2. **Đối tượng đã bind:** bean `@ConfigurationProperties` đang có giá trị gì?
3. **Trạng thái hoạt động:** bộ phận xử lý request đang dùng chính sách nào?

Một HTTP client có thể được tạo bằng timeout cũ rồi giữ nguyên dù bean cấu hình đã đổi. Một connection pool có thể còn các kết nối cũ trong giai đoạn chuyển tiếp. Một hằng được chụp qua constructor không tự thay bằng việc sửa ConfigMap.

### 6.2. Refresh không bảo đảm mọi đối tượng cập nhật giống nhau

Spring Cloud Context có cơ chế rebind và refresh scope, nhưng không phải mọi loại bean đều hỗ trợ cùng hành vi. Tài liệu nêu giới hạn với constructor binding/Java record và một số tài nguyên như HikariDataSource. Xem [Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#refresh-scope).

Vì vậy, sau khi trigger refresh:

- Xác minh nguồn đã đọc lại.
- Xác minh bean thuộc phạm vi dự kiến.
- Xác minh tài nguyên hoặc chính sách nghiệp vụ đã chuyển sang bản mới.
- Kiểm tra các request/kết nối đang diễn ra theo hợp đồng chuyển đổi.

Không dùng “đã nhận HTTP 200 từ refresh” để thay cho các bằng chứng này. Không đặt `@RefreshScope` lên mọi thứ rồi mặc định đã có một giao dịch cập nhật nguyên tử toàn ứng dụng.

### 6.3. Quan sát có chọn lọc

Actuator có thể cung cấp `env`, `configprops` và endpoint tùy biến. Các endpoint cấu hình có thể chứa thông tin nhạy cảm và được sanitization theo cấu hình. Xem [Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

Một endpoint vận hành riêng có thể chỉ trả:

~~~json
{
  "podName": "orders-api-example",
  "podUid": "uid-do-kubernetes-cap",
  "observedAt": "2026-11-25T03:00:00Z",
  "environment": {
    "revision": "display-v42",
    "showRecommendations": "true"
  },
  "bound": {
    "revision": "display-v42",
    "showRecommendations": true
  },
  "effective": {
    "revision": "display-v41",
    "showRecommendations": false,
    "appliedAt": "2026-11-25T02:50:00Z"
  }
}
~~~

Đây là dữ liệu minh họa: Environment và bean đã mới nhưng trạng thái hoạt động còn cũ. Endpoint chỉ đáng tin nếu `effective` được lấy từ đối tượng mà đường nghiệp vụ thực sự đọc, không chép từ annotation hoặc trả lại marker mong muốn.

## 7. Ví dụ Java: quan sát ba lớp cấu hình

Ví dụ Java 17+ sau minh họa cấu hình hiển thị không nhạy cảm. Đặt lớp trong package được ứng dụng quét và dùng dependency Spring Boot web/Actuator cùng bộ phiên bản tương thích của dự án.

Mã tạo:

- Một JavaBean `@ConfigurationProperties`.
- Một snapshot hoạt động mà logic nghiệp vụ có thể đọc.
- Một Actuator endpoint chỉ đọc `configstate`.

**Đoạn mã không tự cài đặt reload hoặc refresh.** Trong hồ sơ đọc tệp lúc khởi động, cập nhật ConfigMap chưa làm các đối tượng này tự đổi. Nếu hệ thống hỗ trợ cập nhật động, bộ điều phối cập nhật phải được thiết kế riêng và gọi bước áp dụng theo đúng hợp đồng.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(
        ConfigurationObservability.DisplayProperties.class)
public class ConfigurationObservability {

    public record Values(
            String revision,
            Boolean showRecommendations) {
    }

    public record AppliedDisplay(
            String revision,
            boolean showRecommendations,
            Instant appliedAt) {
    }

    @ConfigurationProperties(prefix = "orders.display")
    public static class DisplayProperties {
        private String revision;
        private Boolean showRecommendations;

        public String getRevision() {
            return revision;
        }

        public void setRevision(String revision) {
            this.revision = revision;
        }

        public Boolean getShowRecommendations() {
            return showRecommendations;
        }

        public void setShowRecommendations(Boolean value) {
            this.showRecommendations = value;
        }

        public Values snapshot() {
            return new Values(revision, showRecommendations);
        }
    }

    public static final class DisplayRuntime {
        private final AtomicReference<AppliedDisplay> active =
                new AtomicReference<>();

        public DisplayRuntime(Values initial) {
            apply(initial);
        }

        public void apply(Values candidate) {
            if (candidate == null
                    || candidate.revision() == null
                    || candidate.revision().isBlank()
                    || candidate.showRecommendations() == null) {
                throw new IllegalArgumentException(
                        "Display configuration is incomplete");
            }

            active.set(new AppliedDisplay(
                    candidate.revision(),
                    candidate.showRecommendations(),
                    Instant.now()));
        }

        public AppliedDisplay current() {
            return active.get();
        }
    }

    @Endpoint(id = "configstate")
    public static final class ConfigStateEndpoint {
        private final Environment environment;
        private final DisplayProperties properties;
        private final DisplayRuntime runtime;

        public ConfigStateEndpoint(
                Environment environment,
                DisplayProperties properties,
                DisplayRuntime runtime) {
            this.environment = environment;
            this.properties = properties;
            this.runtime = runtime;
        }

        @ReadOperation
        public Map<String, Object> read() {
            Values bound = properties.snapshot();
            AppliedDisplay effective = runtime.current();

            return Map.of(
                    "podName",
                    environment.getProperty("POD_NAME", "<unknown>"),
                    "podUid",
                    environment.getProperty("POD_UID", "<unknown>"),
                    "observedAt",
                    Instant.now(),
                    "environment",
                    Map.of(
                            "revision",
                            environment.getProperty(
                                    "orders.display.revision",
                                    "<missing>"),
                            "showRecommendations",
                            environment.getProperty(
                                    "orders.display.show-recommendations",
                                    "<missing>")),
                    "bound",
                    bound,
                    "effective",
                    effective);
        }
    }

    @Bean
    DisplayRuntime displayRuntime(DisplayProperties properties) {
        return new DisplayRuntime(properties.snapshot());
    }

    @Bean
    ConfigStateEndpoint configStateEndpoint(
            Environment environment,
            DisplayProperties properties,
            DisplayRuntime runtime) {
        return new ConfigStateEndpoint(
                environment, properties, runtime);
    }
}
~~~

### 7.1. Điều gì làm effective trở thành bằng chứng?

Trong ví dụ, đường nghiệp vụ phải thực sự dùng snapshot:

~~~java
ConfigurationObservability.AppliedDisplay active =
        displayRuntime.current();

boolean includeRecommendations =
        active.showRecommendations();
~~~

Nếu nghiệp vụ lại đọc một biến khác được chụp từ lúc khởi động, endpoint `effective` không còn đại diện đúng cho hành vi đó. Quan sát phải gắn với chính đối tượng phục vụ request.

Với tài nguyên phức tạp hơn như connection pool hoặc HTTP client, chỉ cập nhật revision sau khi hoàn tất bước chuyển cấu hình theo thiết kế. Không gọi `apply` trước rồi mới bắt đầu tạo tài nguyên và coi đó là đã thành công.

`AtomicReference` làm việc công bố snapshot này nguyên tử; nó không tạo giao dịch cho toàn ApplicationContext và không giải quyết kết quả bất đồng bộ đến muộn. Bộ điều phối phải bảo đảm thứ tự cập nhật.

### 7.2. Giới hạn của ảnh chụp endpoint

Environment, bean mutable và runtime được đọc tuần tự. Nếu refresh đang diễn ra, một phản hồi có thể chứa dữ liệu ở hai thời điểm gần nhau. Việc sao chép hai getter của bean mutable cũng không tự tạo giao dịch với rebind.

Vì vậy:

- Dùng snapshot bất biến cho dữ liệu mà nghiệp vụ phải đọc nhất quán.
- Đánh giá sau cửa sổ ổn định hoặc bổ sung cơ chế snapshot đồng bộ nếu cần bảo đảm mạnh hơn.
- Không cập nhật `appliedAt` khi chỉ đọc endpoint.
- Chuẩn hóa chuỗi `"true"` của Environment với boolean `true` trước khi so sánh.
- Coi `<missing>`, null, parse lỗi hoặc `<unknown>` là thiếu bằng chứng, không tự coi là khớp.

### 7.3. Expose có chọn lọc và bảo vệ endpoint

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,configstate
  endpoint:
    configstate:
      cache:
        time-to-live: 0s
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Với base path mặc định, endpoint ví dụ là `GET /actuator/configstate`. Cách tạo endpoint bằng `@Endpoint` và `@ReadOperation` được Actuator hỗ trợ. Cần đối chiếu cấu hình access/security theo phiên bản Boot của dự án.

Exposure không thay thế xác thực, phân quyền hoặc giới hạn mạng. Chỉ cho kênh vận hành được phép truy cập; không tự công khai endpoint vì dữ liệu không chứa mật khẩu.

Các trường `env.show-values` và `configprops.show-values` không tự che dữ liệu tùy ý trong endpoint `configstate`. Endpoint tùy biến phải tự chỉ trả danh sách trường đã được duyệt. Không thêm toàn bộ Environment, request header, URL chứa credential hoặc Secret vào payload.

Nếu có cache ở proxy hoặc collector, phải xét tuổi của mẫu ở lớp đó. `cache.time-to-live: 0s` không điều khiển mọi bộ đệm bên ngoài Actuator.

## 8. Lấy bằng chứng theo từng replica

### 8.1. Không dùng một URL Service để chứng minh mọi Pod đã khớp

Một request qua Service hoặc LoadBalancer chỉ quan sát được instance được chọn cho request đó. Session affinity, connection pooling hoặc thuật toán chọn đích có thể khiến nhiều request liên tiếp vẫn tới cùng một Pod.

Danh sách instance từ DiscoveryClient cũng không phải bằng chứng trạng thái cấu hình của từng tiến trình. Danh mục có thể thay đổi trong lúc lấy mẫu.

Quy trình cần:

1. Lấy danh sách Pod thuộc đúng workload.
2. Chọn nhóm Pod cần đánh giá theo kế hoạch triển khai.
3. Truy cập trực tiếp từng Pod qua kênh quản trị phù hợp.
4. Đối chiếu Pod UID trong bằng chứng với Pod UID đang tồn tại.
5. Ghi nhận Pod không truy cập được thay vì bỏ qua.
6. Kiểm tra lại khi nhóm Pod thay đổi trong quá trình lấy mẫu.

### 8.2. Ví dụ truy cập trực tiếp Pod trong lab

Trong một terminal, dùng tên Pod đã xác minh:

~~~powershell
kubectl -n config-ops-lab port-forward pod/orders-api-example 18080:8080
~~~

Trong terminal khác, sau khi đã chuẩn bị `$opsHeaders` bằng cơ chế xác thực vận hành được quản lý:

~~~powershell
$runtimeState = Invoke-RestMethod -Uri 'http://127.0.0.1:18080/actuator/configstate' -Headers $opsHeaders -TimeoutSec 10

$runtimeState |
  Select-Object podName, podUid, observedAt, environment, bound, effective
~~~

Biến header được chuẩn bị qua kênh an toàn; không ghi token trực tiếp vào tài liệu, log hoặc lịch sử lệnh.

Nếu management dùng cổng hoặc đường dẫn khác, đổi cả port-forward và URL tương ứng. Port-forward không tự thay thế chính sách phân quyền HTTP của ứng dụng.

Dừng port-forward khi hoàn tất Pod đó, rồi lặp với các Pod còn lại bằng tên/UID được xác minh. Quyền tạo port-forward là quyền của người vận hành, không phải lý do cấp thêm quyền cho ServiceAccount runtime.

### 8.3. Bảng bằng chứng minh họa

Giả sử mục tiêu là v42, bật gợi ý, không có canary hoặc rollout đang diễn ra:

| Pod | Environment | Bean đã bind | Effective | Kết luận tại thời điểm lấy mẫu |
| --- | --- | --- | --- | --- |
| A | v42 / true | v42 / true | v42 / true | Khớp |
| B | v42 / true | v42 / true | v41 / false | Sai lệch ở bước áp dụng nghiệp vụ |
| C | v42 / false | v42 / false | v42 / false | Marker khớp nhưng giá trị không khớp; điều tra nguồn ghi đè |
| D nếu mới phát sinh | Không truy cập được | Không có mẫu | Không có mẫu | Thiếu bằng chứng, cần lấy mẫu bổ sung |

Không tổng kết “100% khớp” nếu chỉ lấy được A. Không chỉ so revision rồi tính C là thành công.

Nếu mục tiêu là phục vụ toàn bộ ba replica v42, một snapshot runtime hợp lệ ở A không bù được việc B chưa áp dụng hay C dùng giá trị sai.

## 9. Vai trò của Configuration Watcher trong đối chiếu

Configuration Watcher có thể theo dõi nguồn và phát thông báo refresh qua HTTP hoặc Bus. Với HTTP, việc chọn đích liên quan tới discovery; với nguồn mount có thêm độ trễ chiếu tệp. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Tách các mốc sau trong bằng chứng:

~~~text
Nguồn đổi
  -> Watcher phát hiện
  -> Watcher xác định đích
  -> Thông báo được gửi/nhận
  -> Ứng dụng đọc đúng phiên bản nguồn
  -> Bean/tài nguyên được cập nhật
  -> Hành vi nghiệp vụ được xác nhận
~~~

Những câu hỏi cần trả lời:

| Mốc | Câu hỏi |
| --- | --- |
| Phát hiện | Watcher theo dõi đúng namespace, loại nguồn và nhãn chưa? |
| Chọn đích | Danh mục discovery có bao phủ những replica cần cập nhật không? |
| Gửi thông báo | Đúng cổng, đường dẫn và credential HTTP/broker chưa? |
| Đọc nguồn | Dữ liệu mới đã tới nơi ứng dụng đọc chưa? |
| Áp dụng | Cơ chế refresh có tác động tới đối tượng cần thay đổi không? |
| Kết quả | Từng replica báo effective đúng và kiểm tra chức năng đạt chưa? |

Log “đã gửi refresh” chỉ xác nhận một mốc trong chuỗi. Thời gian delay của Watcher là điều chỉnh vận hành theo môi trường, không phải chứng minh rằng kubelet đã chiếu xong dữ liệu trên mọi node.

Nếu một replica bỏ lỡ thông báo, quy trình đối chiếu phải phát hiện nó qua bằng chứng runtime. Không giả định mọi sự kiện trung gian được phát lại đúng một lần sau gián đoạn.

Đối với Secret, không dựa vào việc Watcher xử lý ConfigMap thành công để suy ra Secret được theo dõi; kiểm tra tính năng bật và chính sách truy cập riêng của phiên bản đang dùng.

## 10. Phân loại kết quả và chọn hành động

### 10.1. Trạng thái báo cáo do hệ thống vận hành định nghĩa

Các tên sau là quy ước đề xuất, không phải trạng thái tự có của Spring Cloud Kubernetes:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `MATCHED` | Các lớp bắt buộc có bằng chứng phù hợp với mục tiêu của nhóm Pod |
| `CONVERGING` | Đang trong cửa sổ chuyển đổi được duyệt, chưa đến hạn hội tụ |
| `DRIFTED` | Có bằng chứng lệch khỏi mục tiêu ngoài cửa sổ cho phép |
| `UNKNOWN` | Không đủ hoặc không còn mới bằng chứng để kết luận |
| `NOT_APPLICABLE` | Lớp đó không có trong đường tiêu thụ, ví dụ không dùng volume |

`UNKNOWN` không phải `MATCHED`. Với hệ thống chỉ đọc cấu hình qua API, cột kiểm tra tệp có thể là `NOT_APPLICABLE`, không phải lỗi vì không có tệp.

Ngân sách hội tụ phải xét đường truyền: rollout, env lúc khởi động, volume update hay refresh động. Không đặt một con số chung rồi dùng cho mọi đường tiêu thụ.

### 10.2. Sửa lớp đầu tiên bị lệch

| Bằng chứng | Hướng điều tra/hành động |
| --- | --- |
| Nguồn đúng, bản render sai | Sửa overlay, values, profile hoặc tham số render |
| Bản render đúng, API sai | Kiểm tra pipeline, context, quyền apply và chủ thể quản lý tài nguyên |
| API đúng, Pod tham chiếu sai tên/namespace | Sửa tham chiếu trong nguồn triển khai |
| API đúng, env cũ | Cần thay đời container/rollout theo chính sách; refresh không viết lại env hệ điều hành |
| API đúng, volume cũ kéo dài | Kiểm tra mount, subPath, node/kubelet và nguồn thực tế |
| Dữ liệu Pod đúng, Environment sai | Kiểm tra import, PropertySource, precedence và nguồn ghi đè |
| Environment đúng, bean cũ | Kiểm tra loại binding, phạm vi refresh và vòng đời bean |
| Bean đúng, effective cũ | Sửa bước tái tạo/công bố tài nguyên nghiệp vụ |
| Chỉ một số Pod lệch | Đối chiếu nhóm rollout, thông báo, lỗi cục bộ và đời tiến trình |
| Revision đúng, giá trị sai | Kiểm tra marker tái sử dụng hoặc một nguồn ghi đè riêng từng khóa |

Tôn trọng chủ thể quản lý nguồn. Nếu dùng GitOps, chỉnh nguồn và quy trình reconcile tương ứng; một sửa tay trong cluster có thể bị controller ghi đè.

Đừng liên tục rollout toàn bộ chỉ vì chưa phân biệt được hai lớp cuối. Rollout có thể làm triệu chứng tạm biến mất mà không giải thích cơ chế refresh đang sai.

### 10.3. Có thể dùng rollout khi hợp đồng là cấu hình lúc khởi động

Nếu ứng dụng đã được thiết kế để đọc cấu hình một lần khi khởi động, rollout có kiểm soát là phương án hợp lệ. Sau khi nguồn đã đúng và thay đổi được phê duyệt cho lab:

~~~powershell
kubectl -n config-ops-lab rollout restart deployment/orders-api
kubectl -n config-ops-lab rollout status deployment/orders-api --timeout=180s
~~~

Sau lệnh vẫn phải lấy bằng chứng runtime của các Pod mới. Hoàn tất rollout không tự xác nhận giá trị trong endpoint nghiệp vụ.

Hướng dẫn Kubernetes về cập nhật ConfigMap cũng phân biệt ứng dụng đọc lại tệp với dữ liệu env cần Pod mới và khả năng tồn tại giá trị cũ/mới đồng thời. Xem [Updating Configuration via a ConfigMap](https://kubernetes.io/docs/tutorials/configuration/updating-configuration-via-a-configmap/).

Trong triển khai thực tế, cập nhật annotation revision hoặc tham chiếu nguồn theo quy trình phát hành thường cung cấp dấu vết rõ hơn một lần restart rời rạc. Các annotation như `checksum/config` là quy ước của công cụ/pipeline nếu được dùng, không phải phép kiểm chứng tự động của Kubernetes.

## 11. Rollback cũng phải đối chiếu lại

Giả sử v42 gây lỗi và nhóm quyết định trở về v41. Cần phục hồi cả **ý định cấu hình** và **trạng thái đang phục vụ**, không chỉ đổi image.

Lưu ý: rollback Deployment chỉ khôi phục Pod template của revision tương ứng. Nó không tự khôi phục nội dung của ConfigMap cùng tên đã bị sửa. Điều này được nêu trong [Rolling Back a Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-back-a-deployment).

Ví dụ:

~~~text
Template cũ:
  tham chiếu ConfigMap orders-display

ConfigMap hiện tại:
  vẫn chứa display-v42

Rollback template:
  vẫn tham chiếu orders-display
  -> Pod mới có thể tiếp tục đọc v42
~~~

Một thiết kế khác là dùng ConfigMap có tên theo phiên bản và quản lý nội dung bất biến, rồi đổi tham chiếu trong template. Cách đó giúp liên kết template với nguồn cụ thể hơn, nhưng vẫn phải quản lý việc giữ nguồn cũ, tương thích ứng dụng và bằng chứng runtime.

Quy trình phục hồi:

1. Chốt image và bộ phiên bản cấu hình cần quay về.
2. Khôi phục nguồn qua chủ thể quản lý đúng.
3. Chọn refresh hoặc rollout theo hợp đồng ứng dụng.
4. Đối chiếu từng Pod với mục tiêu phục hồi.
5. Kiểm tra hành vi nghiệp vụ và trạng thái kết nối/tài nguyên đang chuyển tiếp.
6. Kết thúc khi có bằng chứng, không chỉ khi lệnh rollback trả thành công.

Nếu một Secret đã bị thu hồi, không coi phiên bản credential cũ là phương án rollback mặc định. Quyết định phục hồi cấu hình phải tôn trọng vòng đời credential và chính sách bảo mật.

## 12. Bài thực hành với ba replica

### 12.1. Chuẩn bị

Trong namespace lab riêng:

- Ứng dụng có Actuator endpoint quan sát chọn lọc và hành vi hiển thị dùng cùng `DisplayRuntime`.
- Ba replica dùng ConfigMap mount như ví dụ.
- Ban đầu ConfigMap có `display-v41`, `show-recommendations: false`.
- Có nguồn được duyệt cho v42 và công cụ render/phát hành của lab.
- Có quyền đọc tài nguyên và kênh truy cập endpoint vận hành.
- Ghi rõ cấu hình nào cần rollout và cấu hình nào có cơ chế refresh thực sự.

Mẫu Java phần 7 không tự gắn reload. Với mẫu đó, phép kiểm tra đơn giản nhất là đối chiếu trước/sau rollout. Chỉ chạy nhánh refresh động nếu đã bổ sung cơ chế đúng phiên bản và kiểm chứng vòng đời bean.

### 12.2. Các tình huống cần tạo

| Tình huống lab | Cách tạo | Dấu hiệu cần tìm |
| --- | --- | --- |
| API chưa đổi | Chỉ thay nguồn/render, chưa apply | Nguồn mục tiêu v42 nhưng API v41 |
| Tệp đã mới, tiến trình cũ | Đổi ConfigMap mount, chưa rollout/refresh | Volume có v42 nhưng Environment/bound/effective có thể vẫn v41 |
| Đã cập nhật đồng bộ theo hợp đồng startup | Rollout sau khi nguồn đúng | Mọi Pod mục tiêu có v42/true ở các lớp bắt buộc |
| Nguồn ghi đè | Thêm env false cho khóa gợi ý rồi rollout trong lab | Revision v42 nhưng giá trị cuối là false |
| Nhóm Pod hỗn hợp | Giữ Pod cũ và tạo replica mới trong giai đoạn nguồn đã đổi | Phải thống kê theo từng Pod, không lấy một mẫu Service |
| Thiếu bằng chứng | Một endpoint không truy cập được hoặc trả Pod UID không khớp | Báo UNKNOWN, không bỏ qua replica |
| Bean đã đổi nhưng tài nguyên chưa áp dụng | Chỉ với bộ điều phối động được chuẩn bị riêng | Bound mới nhưng effective cũ |
| Phục hồi | Đưa nguồn về mục tiêu đã duyệt và áp dụng lại | Cả nguồn lẫn mọi runtime cần thiết đều phù hợp |

Với thử nghiệm nguồn ghi đè, xóa override qua nguồn triển khai được quản lý, rồi thực hiện cách áp dụng đã chọn. Không sửa trực tiếp Environment của tiến trình bằng các phương tiện không thuộc thiết kế.

### 12.3. Dữ liệu cần ghi sau mỗi bước

~~~text
target:
  namespace
  workload
  image/config revision
  expected non-sensitive values
  rollout/refresh plan

evidence:
  observed time
  API object identity/version
  Pod name/UID and cohort
  source delivery mode
  Environment values selected for inspection
  bound configuration
  effective configuration
  request/observation errors

result:
  MATCHED / CONVERGING / DRIFTED / UNKNOWN
  first mismatching layer
  next corrective action
~~~

Không ghi Secret, token, Authorization header hoặc toàn bộ env vào bản ghi trên.

Sau thực hành, khôi phục cấu hình lab về trạng thái đã chọn và đối chiếu lại toàn bộ Pod cần phục vụ. Không kết thúc thử nghiệm ngay khi một request ngẫu nhiên qua LoadBalancer đã cho kết quả đúng.

## 13. Tiêu chí kết luận cấu hình đã hội tụ

Một đợt thay đổi chỉ được kết luận phù hợp khi:

1. Nguồn được duyệt và bản render mô tả cùng mục tiêu.
2. Tài nguyên API đúng phạm vi và những trường do nhóm quản lý phù hợp mục tiêu.
3. Workload đã tới trạng thái triển khai yêu cầu; các nhóm chuyển tiếp/canary được giải thích rõ.
4. Mỗi replica cần đánh giá có bằng chứng đủ mới, đúng Pod UID và đúng đời tiến trình khi cần.
5. Các lớp dữ liệu, Environment, bean và effective bắt buộc đều phù hợp.
6. Cả revision lẫn các giá trị không nhạy cảm quan trọng đã được so sánh.
7. Kiểm tra hành vi nghiệp vụ xác nhận ứng dụng sử dụng trạng thái được báo.
8. Không còn replica thiếu bằng chứng bị tính nhầm là thành công.

Sự nhất quán được đánh giá trong một phạm vi và khoảng quan sát xác định. Khi replica mới xuất hiện hoặc nguồn lại thay đổi, cần tiếp tục đối chiếu theo revision mới.

Bài học cốt lõi của vận hành cấu hình là tìm được mối liên hệ có bằng chứng từ ý định khai báo tới hành vi của từng tiến trình. Kubernetes quản lý tài nguyên và vòng đời Pod; ứng dụng vẫn phải cung cấp cách chứng minh cấu hình nào đang thực sự được dùng.
