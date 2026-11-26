# Chọn ConfigMap theo label khi chức năng được hỗ trợ

## Mục tiêu và phạm vi

Trong chương **ConfigMap** của module **SPRING_CLOUD_KUBERNETES**, chọn nguồn theo label giúp ứng dụng Spring lấy một nhóm cấu hình mà không cần ghi cố định tên từng ConfigMap. Ví dụ, ứng dụng catalog ở môi trường dev có thể đọc cả cấu hình giao diện lẫn giới hạn phân trang thuộc cùng một nhóm runtime.

Điều kiện quan trọng là phiên bản Spring Cloud Kubernetes, implementation client và đường nạp đang dùng phải hỗ trợ cách chọn này. Kubernetes có label selector không đồng nghĩa mọi thư viện tích hợp đều cung cấp cùng một cú pháp cấu hình.

Sau bài này, bạn có thể:

- Xác định điều kiện hỗ trợ trước khi dùng bộ chọn label.
- Khai báo label trên ConfigMap và tiêu chí chọn trong ứng dụng.
- Kiểm chứng nguồn được chọn, nguồn bị loại và giá trị thực sự đi vào Spring Environment.
- Xử lý tập khớp rỗng, trùng khóa, nguồn theo tên bổ sung và quyền RBAC.
- Phân biệt chọn cấu hình lúc khởi động với theo dõi thay đổi bằng Configuration Watcher.

Bài thực hành chỉ cần tính năng nạp ConfigMap qua Kubernetes API. Secret, DiscoveryClient và Spring Cloud LoadBalancer phục vụ các nhu cầu khác của module; không cần bật chúng để chọn ConfigMap theo label.

## 1. Label chọn một tập tài nguyên

Một ConfigMap có thể mang các label sau:

~~~yaml
metadata:
  name: catalog-core-dev
  labels:
    app: catalog
    environment: dev
    config-set: runtime
~~~

Bộ chọn tương ứng trong bài là:

~~~text
app=catalog,environment=dev,config-set=runtime
~~~

Các điều kiện kết hợp theo **AND**: tài nguyên phải có đủ cả ba cặp khóa–giá trị. Tài nguyên có thêm label khác vẫn có thể khớp. Label nằm trong `metadata.labels` của chính ConfigMap; gắn cùng label lên Pod không tự làm ConfigMap được chọn.

Label không cung cấp tính duy nhất. Một bộ chọn có thể khớp không, một hoặc nhiều tài nguyên trong namespace được truy vấn. Quy tắc chung của Kubernetes được trình bày tại [Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/).

Trong cấu hình Spring Cloud Kubernetes minh họa, `labels` là một map các cặp bằng nhau. Không coi nó là nơi nhập tùy ý mọi biểu thức selector Kubernetes, chẳng hạn `in`, `notin` hoặc `matchExpressions`, nếu phiên bản thư viện không tài liệu hóa khả năng đó.

~~~mermaid
flowchart LR
    A[Ứng dụng Spring] --> B[Bộ nạp ConfigMap]
    B --> C[Namespace cm-label-lab]
    C --> D{Khớp toàn bộ label?}
    D -->|Có| E[Đọc và hợp nhất dữ liệu]
    D -->|Không| F[Loại khỏi tập được chọn bằng label]
    E --> G[Spring Environment]
    G --> H[Bind và kiểm tra giá trị ứng dụng]
~~~

Việc loại khỏi tập label chưa khẳng định tài nguyên không thể được nạp bằng một đường khác, chẳng hạn nguồn theo tên được khai báo riêng.

## 2. Xác nhận hỗ trợ trước khi viết cấu hình

Ghi nhận bốn thông tin của ứng dụng đang triển khai:

| Thông tin | Điều cần xác nhận |
| --- | --- |
| Phiên bản | Nhánh Spring Cloud Kubernetes và BOM Spring Cloud thực tế đang dùng |
| Implementation | Fabric8, Kubernetes Java Client hoặc một đường tích hợp khác |
| Cách nạp | Config Data import, legacy bootstrap hoặc file được mount |
| Thuộc tính | Phiên bản đó có hỗ trợ `config.sources[].labels` và các tùy chọn liên quan không? |

Các ví dụ dưới đây dùng **Spring Cloud Kubernetes 3.3.x với Fabric8 và Config Data import**. Đây là mốc minh họa có tài liệu hỗ trợ tìm ConfigMap theo label, không phải yêu cầu nâng hay hạ phiên bản của mọi ứng dụng. Xem [ConfigMap PropertySource — phiên bản 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

Với nhánh khác, đối chiếu tài liệu đúng phiên bản và kiểm tra bằng một ConfigMap thử có khóa nhận diện riêng. Việc ứng dụng vẫn khởi động sau khi thêm một thuộc tính lạ chưa chứng minh thuộc tính đó được hỗ trợ hoặc đã được áp dụng.

Nếu cách nạp hiện tại chỉ đọc file đã mount, map label dưới cấu hình Kubernetes API không tự làm thay đổi các file được mount. Khi chưa xác nhận hỗ trợ, dùng danh sách ConfigMap theo tên như phần cuối bài.

## 3. Chuẩn bị bộ dữ liệu có cả trường hợp được chọn và bị loại

Giả sử có namespace thực hành `cm-label-lab`. Tạo bốn ConfigMap sau trong namespace đó. Dữ liệu đều là giá trị minh họa, không chứa thông tin xác thực.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-core-dev
  namespace: cm-label-lab
  labels:
    app: catalog
    environment: dev
    config-set: runtime
    component: core
data:
  catalog.title: "Catalog DEV"
  lab.probe.core: "core-dev-v1"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-limits-dev
  namespace: cm-label-lab
  labels:
    app: catalog
    environment: dev
    config-set: runtime
    component: limits
data:
  catalog.page-size: "25"
  lab.probe.limits: "limits-dev-v1"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-core-prod
  namespace: cm-label-lab
  labels:
    app: catalog
    environment: prod
    config-set: runtime
data:
  lab.probe.prod: "prod-must-not-load"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: billing-core-dev
  namespace: cm-label-lab
  labels:
    app: billing
    environment: dev
    config-set: runtime
data:
  lab.probe.foreign: "billing-must-not-load"
~~~

Tập kết quả mong đợi:

| ConfigMap | Có khớp bộ chọn không? | Lý do |
| --- | --- | --- |
| `catalog-core-dev` | Có | Đủ app, environment và config-set |
| `catalog-limits-dev` | Có | Đủ ba điều kiện; component bổ sung không làm mất khớp |
| `catalog-core-prod` | Không | Environment là prod |
| `billing-core-dev` | Không | App là billing |

Hai ConfigMap khớp dùng các khóa nghiệp vụ khác nhau để lượt thử chưa phụ thuộc thứ tự ghi đè. Mỗi nguồn có một khóa đánh dấu riêng; nguồn bị loại cũng có khóa riêng để phát hiện việc nạp rộng ngoài dự kiến.

Trong namespace lab, không tạo ConfigMap tên `label-config-demo`, là tên ứng dụng sẽ dùng ở phần tiếp theo. Điều này giúp kiểm soát đường tra cứu theo tên mặc định được giải thích bên dưới.

## 4. Cấu hình ứng dụng để đọc theo label

### 4.1. Dependency và import

Dự án Spring Boot web có lớp khởi động thông thường, dùng dependency management tương thích với nhánh Spring Cloud Kubernetes đã chọn. Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
</dependency>
~~~

Chọn một implementation cho chức năng này; không cần thêm đồng thời hai starter client chỉ để tìm ConfigMap theo label.

Khai báo trong cấu hình local của ứng dụng, chẳng hạn `application.yaml` đóng gói cùng ứng dụng:

~~~yaml
spring:
  application:
    name: label-config-demo
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        enable-api: true
        namespace: cm-label-lab
        fail-fast: true
        include-profile-specific-sources: false
        use-name-as-prefix: false
        retry:
          enabled: false
        sources:
          - labels:
              app: catalog
              environment: dev
              config-set: runtime
      secrets:
        enabled: false
      discovery:
        enabled: false

logging:
  level:
    org.springframework.cloud.kubernetes: DEBUG
~~~

Các thiết lập xác định namespace, bộ chọn và cách xử lý lỗi phải có sẵn trước khi đọc ConfigMap. Không đặt chúng duy nhất trong chính nguồn cần tìm.

Bài dùng Config Data và không bật thêm legacy bootstrap cho cùng chức năng. Hai cách nạp này cần được lựa chọn rõ ràng theo hướng dẫn [Kubernetes PropertySource implementations — 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

Đặt `include-profile-specific-sources: false` trong ví dụ nhằm cô lập đường chọn label ở nhánh minh họa. Nếu dùng phiên bản khác, kiểm tra hỗ trợ của tùy chọn này trên nguồn label; không coi mọi nhánh có cùng hành vi. Label `environment: dev` cũng không tự kích hoạt Spring profile `dev`.

### 4.2. Kiểm soát các đường nạp bổ sung

Không giả định thêm `labels` sẽ luôn xóa bỏ mọi tra cứu theo tên. Trong Spring Cloud Kubernetes 3.3.3, bước chuẩn hóa nguồn có thể tạo cả nguồn theo tên, dùng tên mặc định từ ứng dụng, và nguồn theo label. Đây là hành vi thể hiện trong [ConfigMapConfigProperties của tag v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ConfigMapConfigProperties.java).

Vì vậy, với lượt thử này:

- Chỉ khai báo một phần tử `sources` có các label cần kiểm tra.
- Không có ConfigMap tên `label-config-demo` cung cấp dữ liệu qua tên mặc định.
- Không khai báo nguồn mount hoặc import khác chứa các khóa `catalog.*` và `lab.probe.*` của phép thử.
- Không cấp cùng giá trị bằng biến môi trường hoặc tham số có độ ưu tiên cao hơn.

Nếu log chỉ ra nguồn theo tên được thử nhưng rỗng, điều đó khác với một ConfigMap ngoài selector có dữ liệu đã được nạp. Cần đối chiếu tên nguồn và giá trị thực tế, thay vì yêu cầu log tuyệt đối không được nhắc tới tên ứng dụng.

Khi cấu hình có cả `name` lẫn `labels`, kiểm tra cách phiên bản đó chuẩn hóa hai phần. Không tự hiểu chúng là điều kiện `tên bằng X AND khớp label`; chúng có thể tạo các nguồn bổ sung.

## 5. Cấp quyền đúng phạm vi namespace

Ứng dụng cần xác thực với Kubernetes API và có quyền đọc ConfigMap. Với đường đọc Fabric8 3.3 trong bài, dữ liệu có thể được lấy theo namespace rồi lọc; quyền `list` vì vậy cần được xét cùng quyền `get`.

RBAC minh họa cho namespace thực hành:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: label-config-reader
  namespace: cm-label-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: label-config-reader
  namespace: cm-label-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: label-config-reader
  namespace: cm-label-lab
subjects:
  - kind: ServiceAccount
    name: label-config-reader
    namespace: cm-label-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: label-config-reader
~~~

Deployment thực hành phải dùng `serviceAccountName: label-config-reader`. Thêm quyền `watch` khi chức năng thực sự được bật và cần quyền ấy; lượt thử chỉ nạp lúc khởi động không cần biến thành bài triển khai watcher.

Nếu tài khoản vận hành có quyền impersonation, kiểm tra:

~~~powershell
kubectl auth can-i list configmaps -n cm-label-lab --as=system:serviceaccount:cm-label-lab:label-config-reader
kubectl auth can-i get configmaps -n cm-label-lab --as=system:serviceaccount:cm-label-lab:label-config-reader
~~~

Kết quả mong đợi là `yes`. Nếu lệnh bị từ chối impersonation, cần kiểm tra bằng tài khoản đủ quyền; đó chưa phải kết luận về quyền ứng dụng.

**Label là tiêu chí chọn dữ liệu, không phải ranh giới phân quyền.** Role trên cho phép đọc ConfigMap trong namespace theo các động từ đã cấp. Việc ứng dụng chỉ chọn `app=catalog` không làm ServiceAccount mất khả năng đọc ConfigMap của billing trong namespace ấy. Dùng namespace và RBAC để tổ chức quyền phù hợp; quy tắc RBAC nằm tại [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Khả năng sửa label cũng cần được quản lý: đổi label có thể làm một ConfigMap gia nhập tập cấu hình mà ứng dụng đọc ở lượt nạp tiếp theo.

## 6. Kiểm chứng trong Spring Environment

Trong package được ứng dụng Spring Boot quét, thêm lớp kiểm chứng dành riêng cho lab:

~~~java
package example.labels;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class LabelSelectionProbe implements ApplicationRunner {
    private static final Logger log =
            LoggerFactory.getLogger(LabelSelectionProbe.class);

    private final Environment environment;

    public LabelSelectionProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String title = environment.getRequiredProperty("catalog.title");
        Integer pageSize = environment.getRequiredProperty(
                "catalog.page-size", Integer.class);
        String core = environment.getRequiredProperty("lab.probe.core");
        String limits = environment.getRequiredProperty("lab.probe.limits");
        boolean prodPresent = environment.containsProperty("lab.probe.prod");
        boolean foreignPresent =
                environment.containsProperty("lab.probe.foreign");

        if (!"Catalog DEV".equals(title) || pageSize != 25
                || !"core-dev-v1".equals(core)
                || !"limits-dev-v1".equals(limits)) {
            throw new IllegalStateException(
                    "Giá trị cấu hình không khớp bộ dữ liệu lab.");
        }
        if (prodPresent || foreignPresent) {
            throw new IllegalStateException(
                    "Phát hiện khóa đánh dấu của nguồn phải bị loại.");
        }

        log.info("LABEL_SELECTION_OK title={} pageSize={} core={} limits={} "
                        + "prodPresent={} foreignPresent={}",
                title, pageSize, core, limits, prodPresent, foreignPresent);
    }
}
~~~

Kết quả kỳ vọng trong log:

~~~text
LABEL_SELECTION_OK title=Catalog DEV pageSize=25 core=core-dev-v1 limits=limits-dev-v1 prodPresent=false foreignPresent=false
~~~

Đây là đầu ra minh họa, không phải log đã chạy sẵn trong cluster. Lớp trên cố ý ràng buộc vào dữ liệu lab để một lượt chọn sai không bị xem là thành công. Với mã ứng dụng thực tế, mô hình hóa cấu hình bằng `@ConfigurationProperties` và kiểm tra các ràng buộc nghiệp vụ phù hợp.

Khóa đánh dấu giúp nhận biết kết quả trong một môi trường đã kiểm soát nguồn. Nó không phải bằng chứng nguồn gốc tuyệt đối nếu cùng khóa còn được đặt trong biến môi trường, file local hoặc import khác. Hãy kết hợp kết quả này với danh sách ConfigMap và log nguồn đã nạp.

Ứng dụng khởi động được hoặc Pod Running chưa đủ chứng minh chọn đúng tập tài nguyên. Cần thấy cả hai dấu hiệu: giá trị từ hai nguồn mong đợi có mặt, giá trị đánh dấu của hai nguồn bị loại vắng mặt.

## 7. Đối chiếu kết quả ở ba tầng

### 7.1. Tầng Kubernetes: selector khớp những tài nguyên nào?

Trong terminal PowerShell của môi trường lab:

~~~powershell
$labelSelector = 'app=catalog,environment=dev,config-set=runtime'
kubectl -n cm-label-lab get configmaps -l $labelSelector --show-labels
kubectl -n cm-label-lab get configmaps -l $labelSelector -o name
~~~

Kỳ vọng có đúng:

~~~text
configmap/catalog-core-dev
configmap/catalog-limits-dev
~~~

Thứ tự hiển thị không phải thứ tự ưu tiên cấu hình. Nếu kết quả khác, sửa namespace hoặc label trước khi điều tra binding trong Spring.

Lệnh `kubectl` thường dùng danh tính của người vận hành. Nó cho biết selector khớp gì dưới quyền của danh tính đó, chưa chứng minh ServiceAccount ứng dụng có quyền hoặc client đã áp dụng cùng tiêu chí.

### 7.2. Tầng bộ nạp: ứng dụng đã đọc những nguồn nào?

Giả sử Deployment tên `label-config-demo`, một replica, có nhãn Pod `app=label-config-demo`, image đã chứa mã và cấu hình ở trên:

~~~powershell
kubectl -n cm-label-lab rollout status deployment/label-config-demo
kubectl -n cm-label-lab get pods -l app=label-config-demo -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,RESTARTS:.status.containerStatuses[0].restartCount'
~~~

Chọn đúng Pod mới và thay `TEN_POD`:

~~~powershell
kubectl -n cm-label-lab logs TEN_POD --timestamps --tail=300
~~~

Đối chiếu namespace, tên hai ConfigMap mong đợi và lỗi API nếu có. Tên thông báo debug phụ thuộc phiên bản; không buộc mọi phiên bản phải in cùng một chuỗi. Một log về việc liệt kê hoặc đưa tài nguyên vào cache cũng chưa đồng nghĩa mọi dữ liệu của tài nguyên đó đã được đưa vào Environment.

Nếu container đã restart, dùng thêm `--previous` để xem lần chạy trước khi log còn được giữ lại. Với nhiều container, chọn đúng container ứng dụng bằng `-c`.

### 7.3. Tầng ứng dụng: giá trị nào thực sự được sử dụng?

Tìm `LABEL_SELECTION_OK` trong đúng lần chạy container. Đối chiếu các giá trị và xác nhận không có lỗi khởi động sau đó. Nếu có readiness probe của ứng dụng, chờ Pod mới Ready theo quy trình triển khai.

Bảng ghi kết quả tối thiểu:

| Tầng | Bằng chứng |
| --- | --- |
| Kubernetes | Hai tên ConfigMap khớp bộ chọn trong đúng namespace |
| Bộ nạp | Nguồn mong đợi được xử lý, không có lỗi quyền hoặc kết nối bị bỏ sót |
| Environment | Hai marker dương đúng giá trị, hai marker âm vắng mặt |
| Lần triển khai | Pod UID, image/phiên bản ứng dụng, thời điểm và lần chạy container |

## 8. Thử bỏ một nguồn khỏi tập bằng cách đổi label

Chỉ thực hiện trên dữ liệu lab. Trước tiên bỏ label environment khỏi ConfigMap giới hạn:

~~~powershell
kubectl -n cm-label-lab label configmap catalog-limits-dev environment-
kubectl -n cm-label-lab get configmaps -l 'app=catalog,environment=dev,config-set=runtime' -o name
~~~

Kỳ vọng selector chỉ còn `catalog-core-dev`. Việc thiếu một điều kiện làm `catalog-limits-dev` không khớp, dù app và config-set vẫn đúng.

Lượt thử không bật reload. Để quan sát một lần nạp mới:

~~~powershell
kubectl -n cm-label-lab rollout restart deployment/label-config-demo
~~~

Pod mới cần được kiểm tra bằng log. Với lớp probe của bài và các đường nạp bổ sung đã được kiểm soát, lượt khởi động này phải thất bại vì thiếu `catalog.page-size` hoặc `lab.probe.limits`. Không dùng log thành công của Pod cũ để đánh giá Pod mới. Một rolling update có thể vẫn giữ Pod cũ đang phục vụ khi phiên bản mới khởi động lỗi.

Khôi phục label và nạp lại:

~~~powershell
kubectl -n cm-label-lab label configmap catalog-limits-dev environment=dev --overwrite
kubectl -n cm-label-lab get configmaps -l 'app=catalog,environment=dev,config-set=runtime' -o name
kubectl -n cm-label-lab rollout restart deployment/label-config-demo
kubectl -n cm-label-lab rollout status deployment/label-config-demo
~~~

Kiểm tra lại log của Pod mới và dấu mốc thành công. Các lệnh trên là hướng dẫn thực hành, không yêu cầu bật cơ chế cập nhật động chỉ để hoàn tất bài.

## 9. Khi nhiều ConfigMap cùng khớp

### 9.1. Bộ chọn không bầu ra một ConfigMap thắng

Hai nguồn cùng khớp đều có thể đóng góp dữ liệu. Nếu chúng chứa cùng một property, giá trị cuối cùng phụ thuộc cách thư viện xử lý nguồn và thứ tự ưu tiên có hiệu lực.

Không suy ra thứ tự ghi đè từ:

- Tên ConfigMap đứng trước trong kết quả `kubectl get`.
- Tên có hậu tố `latest`, thời điểm tạo mới hơn hoặc resourceVersion lớn hơn.
- Chuỗi tên property source đã được sắp xếp để hiển thị.

Trong implementation minh họa, bộ lọc label kiểm tra các cặp khóa–giá trị và xử lý dữ liệu của nhiều nguồn; các chi tiết nằm trong [ConfigUtils — mã nguồn chính thức nhánh 3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/3.3.x/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ConfigUtils.java). Đừng thiết kế nghiệp vụ dựa trên một thứ tự chưa được xác nhận cho phiên bản đang dùng.

Cách tổ chức dễ kiểm chứng là để các ConfigMap trong cùng nhóm có các khóa không trùng nhau, giống `catalog.title` và `catalog.page-size` của bài.

### 9.2. Prefix có thể giúp tách nhóm khóa

Nếu phiên bản hỗ trợ `explicit-prefix` hoặc `use-name-as-prefix`, các tùy chọn đó thay đổi tên property sau khi nạp. Chúng không làm selector chỉ khớp một tài nguyên.

Ví dụ một nhóm nguồn riêng có prefix cố định:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        namespace: cm-label-lab
        sources:
          - labels:
              app: catalog
              environment: dev
              config-set: runtime
            explicit-prefix: selected
~~~

Với cách thêm prefix được hỗ trợ trong nhánh minh họa, khóa `catalog.title` đi vào ứng dụng dưới dạng `selected.catalog.title`; mã đọc cấu hình phải đổi tương ứng. Đây là biến thể riêng, không ghép vào lượt thử đang đọc các khóa chưa có prefix.

Prefix chung của một nhóm vẫn không giải quyết hai ConfigMap cùng đóng góp `catalog.title` cho chính nhóm đó. Khi dùng prefix suy từ tên nguồn và selector khớp nhiều ConfigMap, phải xác nhận chính xác cách phiên bản thư viện dựng tên khóa; không mặc định mọi implementation đều tạo một namespace property riêng cho từng ConfigMap.

### 9.3. Tập khớp rỗng cần được kiểm tra rõ ràng

Không có nguồn khớp có thể được xử lý thành tập dữ liệu rỗng, thay vì một lỗi API. Vì vậy, `fail-fast: true` không thay thế kiểm tra rằng dữ liệu nghiệp vụ bắt buộc đã có.

Bài dùng `getRequiredProperty` và marker để chặn tình huống thiếu dữ liệu. Với ứng dụng thực tế, dùng binding/validation và theo dõi cấu hình đang có hiệu lực. Không coi map label rỗng là cách diễn đạt chắc chắn “không chọn gì”; ngữ nghĩa khi tiêu chí rỗng phụ thuộc đường xử lý của thư viện.

## 10. Label key có dấu chấm và dấu gạch chéo

Label Kubernetes thường dùng khóa có prefix miền, chẳng hạn `app.kubernetes.io/name`. Khi map được bind qua Spring Boot, ký tự đặc biệt cần được giữ nguyên.

Trên ConfigMap, khai báo khóa Kubernetes bình thường:

~~~yaml
metadata:
  labels:
    app.kubernetes.io/name: catalog
    config.example.com/environment: dev
~~~

Trong cấu hình ứng dụng bind vào map, dùng bracket notation khi cần giữ nguyên khóa có dấu `/`:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        sources:
          - labels:
              "[app.kubernetes.io/name]": "catalog"
              "[config.example.com/environment]": "dev"
~~~

Dấu ngoặc vuông trong ví dụ thứ hai phục vụ binding của Spring; nó không phải một phần tên label trên ConfigMap. Quy tắc giữ nguyên map key được mô tả ở phần Binding Maps của [Spring Boot Externalized Configuration — 3.5](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html).

Biến thể này thay đổi bộ tiêu chí so với ba label đơn giản của lượt thử chính. Hãy cập nhật cả manifest ConfigMap lẫn selector và kiểm chứng lại; không chỉ đổi một phía.

Giá trị label nên được viết dưới dạng chuỗi, đặc biệt các giá trị như `"true"` hoặc chuỗi số. Khi selector không khớp dù nhìn gần giống nhau, đối chiếu chính xác key, value, namespace và map sau binding.

## 11. Chọn nguồn khác với theo dõi thay đổi

| Cơ chế | Vai trò |
| --- | --- |
| `spring.cloud.kubernetes.config.sources[].labels` | Tiêu chí tìm ConfigMap cho bộ nạp cấu hình được hỗ trợ |
| Label của Configuration Watcher | Điều kiện theo dõi hoặc phát thông báo thay đổi theo cấu hình watcher |
| Label selector của Service | Tìm Pod đích cho lưu lượng mạng |
| Label trên Pod | Metadata của Pod; không tự chuyển thành tiêu chí tìm ConfigMap |

Ví dụ label `spring.cloud.kubernetes.config: "true"` có vai trò trong cơ chế Configuration Watcher của nhánh 3.3. Nó không tự khiến mọi ứng dụng nạp ConfigMap đó vào Environment. Tương tự, thêm `environment: dev` cho ConfigMap không tự làm bean trong một tiến trình đang chạy được refresh. Xem [Spring Cloud Kubernetes Configuration Watcher — 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Muốn cập nhật động, cần thiết kế cả việc phát hiện thay đổi, xác định ứng dụng nhận thông báo, đường refresh/restart và cách bean áp dụng giá trị mới. Với bài này, khởi động Pod mới tạo mốc nạp rõ ràng để kiểm chứng selector trước.

Khi nhiều ConfigMap tạo thành một bộ cấu hình, việc đổi label hoặc cập nhật từng tài nguyên cũng không tự tạo một giao dịch cập nhật đồng thời cho cả bộ. Nếu cần các phiên bản đồng bộ, có thể thêm label revision vào tiêu chí chọn và quản lý vòng đời bộ cấu hình theo quy trình phát hành. Vẫn cần kiểm soát các đường nạp bổ sung và kiểm tra giá trị thực tế của từng bản sao ứng dụng.

## 12. Phương án khi chưa có hỗ trợ chọn theo label

Nếu implementation hoặc phiên bản hiện tại chưa xác nhận hỗ trợ, dùng nguồn theo tên đã được hỗ trợ:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        namespace: cm-label-lab
        include-profile-specific-sources: false
        use-name-as-prefix: false
        sources:
          - name: catalog-core-dev
          - name: catalog-limits-dev
~~~

Đây là **cấu hình thay thế** cho phần sources chọn label. Gỡ tiêu chí label ở cả cấp mặc định và từng source nếu chúng không còn là chính sách mong muốn. Không để hai cấu hình cạnh nhau rồi giả định thư viện tự chọn một cách.

Bạn vẫn có thể giữ label trên tài nguyên để quản lý và tìm kiếm bằng `kubectl`. Việc gắn label là metadata của Kubernetes, còn khả năng đọc theo label là chức năng phải được bộ nạp triển khai.

Chọn theo tên phù hợp khi muốn công bố rõ các tài nguyên đầu vào hoặc cần tập nguồn cố định. Chọn theo label phù hợp khi tổ chức nguồn thành nhóm có quy ước ổn định và có kiểm tra tập kết quả. Quyết định dựa trên hành vi đã xác nhận của phiên bản dùng trong triển khai.

## 13. Chẩn đoán nhanh và tiêu chí hoàn tất

| Hiện tượng | Kiểm tra ưu tiên |
| --- | --- |
| `kubectl` không tìm thấy nguồn | Namespace, label trên chính ConfigMap, thiếu một điều kiện AND |
| `kubectl` thấy nguồn nhưng ứng dụng không có giá trị | Hỗ trợ thư viện, đường nạp API, map sau binding, quyền ServiceAccount |
| Nạp thêm nguồn ngoài dự kiến | Selector quá rộng, nguồn theo tên mặc định, sources khác hoặc profile-specific source |
| Giá trị cuối cùng khác dữ liệu trong ConfigMap | Trùng property, prefix hoặc nguồn có độ ưu tiên cao hơn |
| Thêm label nhưng tiến trình cũ chưa đổi | Cơ chế hiện tại chỉ nạp lúc khởi động; kiểm tra thiết kế refresh/restart |
| Thêm cấu hình labels mà ứng dụng không báo lỗi | Thuộc tính có thể chưa được tiêu thụ; dùng marker để chứng minh hỗ trợ |
| Thiếu nguồn nhưng khởi động vẫn thành công | Có fallback hoặc không kiểm tra khóa bắt buộc; đối chiếu validation |
| Có lỗi Forbidden | Kiểm tra ServiceAccount, RoleBinding và đúng động từ API; sửa label không chữa RBAC |

Một lượt thực hành hoàn tất khi bạn ghi lại được:

1. Phiên bản, implementation và cách nạp có hỗ trợ chức năng đang dùng.
2. Namespace cùng bộ cặp label thực sự được bind vào ứng dụng.
3. Danh sách tài nguyên khớp mong đợi và các nguồn bị loại.
4. Các đường tra cứu theo tên, profile hoặc import bổ sung đã được kiểm soát.
5. Giá trị từ cả hai nguồn mong đợi có mặt, các marker âm vắng mặt trong đúng lần chạy ứng dụng.
6. Việc bỏ rồi khôi phục một label thay đổi tập nguồn ở lượt nạp mới đúng như dự kiến.
7. Quy tắc xử lý nguồn rỗng và trùng property đủ rõ để vận hành.

Kết quả cần chứng minh là ứng dụng đã nhận đúng bộ cấu hình theo chính sách được hỗ trợ, với quyền phù hợp và dữ liệu kiểm chứng được. Từ đó mới quyết định có cần bổ sung Configuration Watcher hay giữ quy trình nạp cấu hình qua mỗi lần triển khai.
