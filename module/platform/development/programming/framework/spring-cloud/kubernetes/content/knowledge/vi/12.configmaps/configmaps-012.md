# Xử lý ConfigMap thiếu, rỗng hoặc có nội dung sai cú pháp

## Mục tiêu và phạm vi

Trong chương **ConfigMap** của module **SPRING_CLOUD_KUBERNETES**, một ứng dụng Spring chỉ có thể phục vụ đúng khi nhận được cấu hình đầy đủ và hợp lệ. ConfigMap tồn tại trong Kubernetes chưa đủ để bảo đảm điều đó: nguồn có thể không chứa dữ liệu, chứa chuỗi YAML hỏng hoặc cung cấp giá trị không chuyển được sang kiểu mà ứng dụng cần.

Bài này trình bày cách phân loại lỗi, thiết lập chính sách dừng phù hợp và khôi phục cấu hình bằng một phép thử có kiểm soát. Bạn sẽ phân biệt:

- Không có ConfigMap ở tên và namespace đang tra cứu.
- ConfigMap tồn tại nhưng không có dữ liệu hữu ích.
- Manifest Kubernetes hợp lệ nhưng nội dung cấu hình lồng bên trong sai cú pháp.
- Nội dung parse được nhưng thiếu khóa, sai kiểu hoặc vi phạm ràng buộc nghiệp vụ.

Ví dụ chính dùng ConfigMap qua Kubernetes API khi khởi động. Secret, DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher không cần bật để xử lý các lỗi này. Khi triển khai, chỉ chọn thêm tính năng Spring Cloud Kubernetes đáp ứng nhu cầu thực tế của ứng dụng.

## 1. Xác định lỗi nằm ở tầng nào

~~~mermaid
flowchart TD
    A[Manifest ConfigMap] --> B{Kubernetes chấp nhận tài nguyên?}
    B -->|Không| C[Sửa YAML ngoài hoặc schema tài nguyên]
    B -->|Có| D{Ứng dụng tìm và đọc được nguồn?}
    D -->|Không| E[Kiểm tra tên, namespace, RBAC và đường mạng]
    D -->|Có| F{Có dữ liệu cấu hình được nhận diện?}
    F -->|Không| G[Kiểm tra data, tên key và nguồn bổ sung]
    F -->|Có| H{Parse nội dung thành công?}
    H -->|Không| I[Sửa cú pháp nội dung YAML hoặc properties]
    H -->|Có| J{Bind và validation thành công?}
    J -->|Không| K[Sửa khóa, kiểu hoặc ràng buộc giá trị]
    J -->|Có| L[Xác nhận cấu hình có hiệu lực và ứng dụng sẵn sàng]
~~~

Mỗi tầng cần bằng chứng riêng. Một thông báo lỗi ở cuối quá trình thường bọc nhiều nguyên nhân; hãy đọc chuỗi `Caused by` và tìm lỗi gốc thay vì chỉ nhìn tên exception ngoài cùng.

| Trường hợp | Kubernetes có thể chấp nhận không? | Nơi thường phát hiện vấn đề |
| --- | --- | --- |
| YAML manifest ngoài bị hỏng | Không | Công cụ đọc manifest |
| Kiểu giá trị `data` không phù hợp schema | Không | Kiểm tra hoặc xử lý tài nguyên Kubernetes |
| Nguồn đúng tên không tồn tại | Không có đối tượng tương ứng | Kubelet hoặc bộ nạp API, tùy đường tích hợp |
| `data: {}` | Có | Bộ nạp trả dữ liệu rỗng hoặc bước kiểm tra cấu hình ứng dụng |
| `application.yaml` là chuỗi rỗng | Có | Bước parse hoặc kiểm tra dữ liệu hữu ích sau parse |
| YAML lồng sai cú pháp | Có thể có | Parser cấu hình trong ứng dụng |
| `page-size: "abc"` | Có | Binding sang kiểu số |
| `page-size: 0` với yêu cầu tối thiểu là 1 | Có | Validation nghiệp vụ |

Kubernetes cho phép cả `data` và `binaryData` là trường tùy chọn. Việc tạo được một ConfigMap không mang ý nghĩa rằng ứng dụng đã nhận được các khóa bắt buộc. Xem [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

## 2. Phân biệt ConfigMap thiếu với không được phép đọc

Trước khi sửa nội dung, xác nhận đúng tên và namespace:

~~~powershell
kubectl -n cm-recovery-lab get configmap catalog-runtime
kubectl -n cm-recovery-lab get configmap catalog-runtime -o yaml
~~~

Ba kết quả có ý nghĩa khác nhau:

- **NotFound:** không có đối tượng ở tên và namespace được hỏi dưới đường truy vấn đó.
- **Forbidden:** danh tính đang gọi không có quyền thực hiện thao tác; không thể từ đó kết luận nguồn không tồn tại.
- **Có đối tượng:** tiếp tục kiểm tra key trong `data` và nội dung thực tế.

Lệnh của người vận hành sử dụng danh tính từ kubeconfig, còn ứng dụng trong Pod thường dùng ServiceAccount. Người vận hành đọc được ConfigMap chưa chứng minh ứng dụng đọc được.

Với tài khoản được phép impersonation, có thể kiểm tra quyền tương ứng:

~~~powershell
kubectl auth can-i get configmaps -n cm-recovery-lab --as=system:serviceaccount:cm-recovery-lab:configmap-reader
kubectl auth can-i list configmaps -n cm-recovery-lab --as=system:serviceaccount:cm-recovery-lab:configmap-reader
~~~

Chỉ xét kết quả khi chính tài khoản chạy lệnh có quyền impersonation. Đối chiếu thêm tài nguyên và động từ bị từ chối trong log ứng dụng.

Đường nạp cũng quyết định lỗi xuất hiện ở đâu:

| Đường cung cấp ConfigMap | Nguồn bắt buộc bị thiếu có thể biểu hiện thế nào? |
| --- | --- |
| Tham chiếu volume hoặc environment trong PodSpec | Kubelet có thể chưa khởi động được container |
| Spring Cloud Kubernetes đọc API | Container chạy Java nhưng quá trình tìm nguồn hoặc khởi tạo Spring gặp vấn đề |
| Spring Boot import file đã mount | Phải xét cả bước mount và bước đọc location của Config Data |

Nếu tham chiếu Pod không đánh dấu optional và nguồn hoặc key bắt buộc không tồn tại, Pod có thể không khởi động được. Đọc Events để phân biệt lỗi mount hoặc thiết lập environment với lỗi trong Spring. Quy tắc này nằm tại [Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/).

## 3. Ba dạng “rỗng” không giống nhau

### 3.1. ConfigMap không có entry trong data

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-runtime
  namespace: cm-recovery-lab
data: {}
~~~

Tài nguyên tồn tại nhưng không cung cấp property nghiệp vụ nào. Kiểm tra đúng đối tượng hiện đang lưu trên API; một thao tác cập nhật không xóa được các key cũ có thể làm bạn tưởng đã thử dữ liệu rỗng nhưng thực tế chưa rỗng.

### 3.2. Có entry đại diện file nhưng nội dung file rỗng

~~~yaml
data:
  application.yaml: ""
~~~

Ở đây có một key nhưng không có cấu hình hữu ích bên trong. File chỉ có khoảng trắng hoặc comment cũng chưa chắc tạo ra các property ứng dụng cần. Chi tiết xử lý có thể khác theo parser và phiên bản; tiêu chí cuối cùng vẫn là những khóa bắt buộc có giá trị hợp lệ hay không.

### 3.3. Có key nghiệp vụ nhưng giá trị rỗng

~~~yaml
data:
  catalog.title: ""
  catalog.page-size: "25"
  catalog.config-revision: "lab-r1"
~~~

`catalog.title` đã tồn tại, nhưng chuỗi rỗng có thể không hợp lệ với nghiệp vụ. Chuỗi chỉ chứa dấu cách cũng cần được kiểm tra nếu yêu cầu là một tiêu đề có nội dung.

Kiểm tra “có key” không thay thế kiểm tra “giá trị được chấp nhận”. Tương tự, một giá trị mặc định cho property vắng mặt không tự giải quyết trường hợp property đã có nhưng chứa chuỗi rỗng.

## 4. Hai lớp YAML và giới hạn của dry-run

Ví dụ sau có manifest ngoài hợp lệ, nhưng chuỗi nằm trong `application.yaml` bị thiếu dấu đóng của danh sách:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-runtime
  namespace: cm-recovery-lab
data:
  application.yaml: |-
    catalog:
      title: "Catalog lab"
      page-size: [25
      config-revision: "lab-bad-yaml"
~~~

Kubernetes xem phần sau `|-` là một chuỗi. Nó không biết rằng ứng dụng dự định parse chuỗi này như YAML cấu hình Spring. Vì vậy, tài nguyên có thể được chấp nhận nhưng ứng dụng thất bại khi parse nội dung.

Nếu manifest được lưu trong file `catalog-runtime.yaml` của môi trường thực hành:

~~~powershell
kubectl apply --dry-run=server -f catalog-runtime.yaml
~~~

Lệnh này kiểm tra khả năng xử lý tài nguyên của API theo cơ chế dry-run; nó không thay thế việc parse nội dung lồng bằng đúng thư viện của ứng dụng. Admission tùy chỉnh có thể có kiểm tra riêng, nhưng không nên giả định schema ConfigMap tiêu chuẩn xác thực YAML cấu hình bên trong.

Một số lỗi dễ nhầm:

- Thụt lề sai có thể tạo YAML vẫn hợp lệ nhưng biến khóa thành một đường property khác.
- Tên sai như `catalog.page-szie` là một property khác, không nhất thiết là lỗi cú pháp.
- Chuỗi `"abc"` là YAML hợp lệ; lỗi xảy ra khi bind sang số.
- Cú pháp `.properties` khác YAML; một dòng không có dấu `=` chưa chắc là lỗi parser.
- Đổi tên key file không bảo đảm nội dung bị bỏ qua. Trong nhánh minh họa, một entry duy nhất kết thúc bằng `.yaml`, `.yml` hoặc `.properties` có thể được xử lý như file cấu hình ngay cả khi không mang tên `application`.

Cách nhận diện và xử lý entry được thể hiện trong [SourceDataEntriesProcessor — mã nguồn tag v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/SourceDataEntriesProcessor.java).

## 5. Thiết lập một ứng dụng có chính sách rõ ràng

### 5.1. Phạm vi phiên bản và dependency

Ví dụ dùng Java 17 trở lên, Spring Boot phù hợp với BOM Spring Cloud của dự án và **Spring Cloud Kubernetes 3.3.x với Fabric8**. Với phiên bản hoặc implementation khác, đối chiếu hành vi nguồn vắng mặt và xử lý exception của đúng phiên bản đang triển khai.

Các dependency cho ứng dụng web thực hành:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
</dependency>
~~~

Ứng dụng dùng Config Data import, không bật đồng thời legacy bootstrap cho cùng chức năng. Dùng dependency management tương thích thay vì tự ghép các phiên bản riêng lẻ.

### 5.2. Chính sách local trước khi đọc nguồn

~~~yaml
spring:
  application:
    name: configmap-recovery-demo
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        enable-api: true
        name: catalog-runtime
        namespace: cm-recovery-lab
        include-profile-specific-sources: false
        use-name-as-prefix: false
        fail-fast: true
        retry:
          enabled: false
      secrets:
        enabled: false
      discovery:
        enabled: false

logging:
  level:
    org.springframework.cloud.kubernetes: DEBUG
~~~

Giữ cấu hình tìm nguồn và chính sách lỗi ở nơi có thể đọc trước ConfigMap. Tắt retry trong lượt thử để lỗi nội dung được quan sát rõ; lặp lại thao tác đọc cùng dữ liệu hỏng không tự sửa cú pháp.

`fail-fast: true` giúp lỗi đọc hoặc xử lý nguồn được đưa ra trong quá trình khởi động theo cơ chế của bộ nạp. Tài liệu mô tả thuộc tính này tại [ConfigMap PropertySource — 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

Tuy nhiên, **fail-fast không phải kiểm tra đầy đủ tính tồn tại và nội dung nghiệp vụ**. Trong nhánh minh họa có đường trả về dữ liệu rỗng khi không tìm thấy nguồn; không phải mọi trường hợp thiếu ConfigMap đều biến thành exception đọc. Xem [NamedSourceData — tag v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/NamedSourceData.java).

### 5.3. Nguồn hợp lệ làm mốc

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-runtime
  namespace: cm-recovery-lab
data:
  application.yaml: |-
    catalog:
      title: "Catalog lab"
      page-size: 25
      config-revision: "lab-r1"
~~~

Trong ví dụ này, `page-size: 25` nằm **bên trong chuỗi YAML** nên có thể mang kiểu số khi parse. Nếu đặt trực tiếp `catalog.page-size` dưới `data`, hãy dùng giá trị chuỗi như `"25"` theo schema của ConfigMap.

## 6. Chặn dữ liệu thiếu, rỗng, sai kiểu và sai phạm vi

Khai báo một kiểu cấu hình có validation:

~~~java
package example.configrecovery;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        @NotBlank String title,
        @NotNull @Min(1) @Max(200) Integer pageSize,
        @NotBlank String configRevision) {
}
~~~

Đăng ký kiểu cấu hình trong lớp khởi động:

~~~java
package example.configrecovery;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(CatalogProperties.class)
public class ConfigRecoveryApplication {
    private static final Logger log =
            LoggerFactory.getLogger(ConfigRecoveryApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(ConfigRecoveryApplication.class, args);
    }

    @Bean
    ApplicationRunner configurationMarker(CatalogProperties properties) {
        return args -> log.info(
                "CONFIG_BOUND revision={} title={} pageSize={}",
                properties.configRevision(), properties.title(),
                properties.pageSize());
    }
}
~~~

Các ràng buộc giải quyết từng tình huống:

| Dữ liệu | Kết quả cần có |
| --- | --- |
| Không có `catalog.page-size` | `@NotNull` ngăn thiếu giá trị bắt buộc |
| `catalog.title` rỗng hoặc toàn khoảng trắng | `@NotBlank` ngăn giá trị không có nội dung |
| `page-size: "abc"` | Binding sang `Integer` thất bại trước khi đánh giá phạm vi |
| `page-size: 0` hoặc `201` | Validation phạm vi thất bại |
| Giá trị đủ và hợp lệ | Bean được tạo; có thể in dấu mốc sau binding |

Dùng `Integer` trong ví dụ giúp biểu diễn rõ trường hợp chưa có giá trị bằng `null`. Nếu chỉ dùng `@Min` mà thiếu `@NotNull` trên một trường số dạng wrapper, giá trị null không bị ràng buộc đó chặn.

Spring Boot hỗ trợ validation của `@ConfigurationProperties` khi kiểu cấu hình được đăng ký và có `@Validated` cùng validation implementation phù hợp. Xem [Externalized Configuration — ConfigurationProperties Validation](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html).

Dấu mốc thành công mong đợi:

~~~text
CONFIG_BOUND revision=lab-r1 title=Catalog lab pageSize=25
~~~

Dấu mốc này cho biết bean đã được bind và kiểm tra theo các ràng buộc trên. Tiếp tục xác nhận ứng dụng khởi động hoàn tất và readiness của Pod mới; một dòng log không đại diện toàn bộ sức khỏe ứng dụng.

## 7. Tránh để fallback che mất phép thử

Validation áp dụng lên cấu hình **sau khi các nguồn có hiệu lực được hợp nhất**. Nếu cùng khóa có sẵn trong biến môi trường, tham số khởi động hoặc nguồn khác, một ConfigMap thiếu dữ liệu vẫn có thể để lại giá trị hợp lệ.

Trước khi thử lỗi, bảo đảm không có các override như `CATALOG_TITLE`, `CATALOG_PAGESIZE` và `CATALOG_CONFIGREVISION`, cũng không có giá trị mặc định cho ba khóa này trong file local của lượt thử.

Phân biệt hai chính sách:

| Tính chất cấu hình | Cách xử lý phù hợp |
| --- | --- |
| Giá trị bắt buộc để vận hành đúng | Yêu cầu giá trị hợp lệ và dừng khởi động khi không đạt |
| Giá trị tùy chọn, có mặc định đã được chấp nhận | Khai báo mặc định rõ ràng và kiểm chứng khi nguồn thiếu |
| Giá trị có fallback theo môi trường | Ghi nhận môi trường, nguồn thay thế và giới hạn sử dụng |

`optional:` của Config Data hoặc `optional: true` trên tham chiếu Kubernetes chỉ tác động theo đường nạp tương ứng. Chúng không sửa YAML hỏng và không tự cung cấp giá trị nghiệp vụ. Cũng không coi bỏ `optional:` khỏi `kubernetes:` là kiểm tra đủ mọi khóa bắt buộc.

Nếu đã tắt fail-fast và bộ nạp bỏ qua lỗi parse, các giá trị local có thể khiến ứng dụng vẫn chạy. Chỉ lựa chọn cách đó khi fallback là chủ ý, có thể quan sát và đáp ứng yêu cầu nghiệp vụ; không dùng nó làm cách che một bản cấu hình bị lỗi.

## 8. Chuẩn bị môi trường lab để kiểm chứng

Giả sử namespace `cm-recovery-lab` đã được tạo, có Deployment `configmap-recovery-demo` một replica, nhãn Pod `app=configmap-recovery-demo`, image chứa mã và cấu hình ở trên. Deployment dùng ServiceAccount `configmap-reader`, được xác thực tới API.

RBAC cho đường nạp trong ví dụ:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: configmap-reader
  namespace: cm-recovery-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: configmap-reader
  namespace: cm-recovery-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: configmap-reader
  namespace: cm-recovery-lab
subjects:
  - kind: ServiceAccount
    name: configmap-reader
    namespace: cm-recovery-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: configmap-reader
~~~

Với implementation hoặc cách đọc khác, đối chiếu quyền API thực tế. Không cần cấp quyền Secret hoặc quyền quản trị cluster để sửa lỗi nội dung ConfigMap này.

Bắt đầu bằng ConfigMap hợp lệ và xác nhận lượt khởi động thành công. Không bật Configuration Watcher hoặc reload trong chuỗi thử; mỗi mẫu dữ liệu được kiểm tra bằng một Pod mới để tránh nhầm trạng thái cũ.

### 8.1. Thay toàn bộ data, tránh giữ sót key

Các lệnh dưới đây dành cho **PowerShell 7** trong môi trường lab. Hàm dùng JSON Patch để đặt toàn bộ trường `data` của đúng ConfigMap thử nghiệm, kể cả khi trường đó chưa có:

~~~powershell
function Set-LabConfigData {
    param([Parameter(Mandatory)][AllowEmptyCollection()][hashtable]$ConfigData)

    $patchOperations = @(
        @{
            op = 'add'
            path = '/data'
            value = $ConfigData
        }
    )
    $patchJson = ConvertTo-Json -InputObject $patchOperations -Depth 10 -Compress

    kubectl -n cm-recovery-lab patch configmap catalog-runtime --type=json --patch $patchJson
    if ($LASTEXITCODE -ne 0) {
        throw 'Không cập nhật được ConfigMap lab.'
    }
}

$goodYaml = @'
catalog:
  title: "Catalog lab"
  page-size: 25
  config-revision: "lab-r1"
'@
~~~

ConfigMap phải tồn tại trước khi gọi hàm. Trong JSON Patch, thao tác `add` tại một member của object sẽ thay giá trị member đó nếu đã tồn tại. Vì vậy, ở đây nó thay toàn bộ map `data`, thay vì hợp nhất từng key với dữ liệu cũ.

Đừng dùng merge patch `{"data":{}}` rồi mặc định các entry cũ đã bị xóa: hợp nhất một object rỗng có thể giữ nguyên nội dung cũ. Sau mọi thay đổi, đọc lại tài nguyên. Sự khác nhau giữa các kiểu patch được trình bày tại [Update API Objects in Place Using kubectl patch](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/update-api-object-kubectl-patch/).

### 8.2. Quy trình quan sát sau mỗi thay đổi

~~~powershell
kubectl -n cm-recovery-lab get configmap catalog-runtime -o yaml
kubectl -n cm-recovery-lab rollout restart deployment/configmap-recovery-demo
kubectl -n cm-recovery-lab get pods -l app=configmap-recovery-demo -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,RESTARTS:.status.containerStatuses[0].restartCount'
~~~

Chờ Pod mới được tạo và lấy đúng tên Pod trong kết quả. Thay `TEN_POD` trong các lệnh đọc bằng tên thực tế:

~~~powershell
kubectl -n cm-recovery-lab logs TEN_POD --timestamps --tail=300
kubectl -n cm-recovery-lab describe pod TEN_POD
~~~

Nếu container đã khởi động lại và lần chạy trước còn log:

~~~powershell
kubectl -n cm-recovery-lab logs TEN_POD --previous --timestamps --tail=300
~~~

Với nhiều container, chỉ rõ container ứng dụng bằng `-c`. Ghi Pod UID, thời gian và restart count để không trộn nhiều lần khởi động.

`rollout status` có thể chờ lâu hoặc báo lỗi khi bản cấu hình thử cố ý không hợp lệ. Hãy thu thập log của Pod mới thay vì đợi một rollout lỗi trở thành thành công. Pod cũ còn Ready trong rolling update không chứng minh Pod mới đã chấp nhận cấu hình.

## 9. Các lượt thử và cách khôi phục

### Lượt A — Mốc hợp lệ

~~~powershell
Set-LabConfigData -ConfigData @{ 'application.yaml' = $goodYaml }
~~~

Thực hiện quy trình khởi động và quan sát ở trên. Kỳ vọng `CONFIG_BOUND revision=lab-r1`, title và pageSize đúng, ứng dụng khởi động hoàn tất.

### Lượt B — Tên nguồn không tồn tại

Giữ ConfigMap chuẩn để còn phục hồi, nhưng cho ứng dụng tra cứu một tên không tồn tại trong namespace lab:

~~~powershell
kubectl -n cm-recovery-lab get configmap catalog-runtime-missing
kubectl -n cm-recovery-lab set env deployment/configmap-recovery-demo SPRING_CLOUD_KUBERNETES_CONFIG_NAME=catalog-runtime-missing
~~~

Lệnh đầu cần xác nhận NotFound; nếu tài nguyên đã tồn tại, chưa tạo được đúng tình huống thử. Lệnh `set env` thay đổi Pod template và tạo lượt triển khai mới, không cần restart thêm chỉ để áp dụng override này.

Kỳ vọng ứng dụng không khởi động thành công với các giá trị bắt buộc thiếu. Tùy implementation, lỗi có thể đến từ bộ nạp hoặc từ binding/validation sau một nguồn rỗng. Không bắt buộc mọi phiên bản phải đưa ra cùng một thông báo NotFound trong log Java.

Khôi phục tên cấu hình đóng gói:

~~~powershell
kubectl -n cm-recovery-lab set env deployment/configmap-recovery-demo SPRING_CLOUD_KUBERNETES_CONFIG_NAME-
~~~

Xác nhận lượt triển khai phục hồi trước khi chuyển sang mẫu dữ liệu tiếp theo.

### Lượt C — ConfigMap có data rỗng

~~~powershell
Set-LabConfigData -ConfigData @{}
~~~

Đọc lại tài nguyên rồi tạo Pod mới. Tài nguyên vẫn tồn tại, nhưng các khóa `catalog.*` không được cấp từ nguồn này. Với fallback đã được loại khỏi phép thử, ứng dụng phải không vượt qua kiểm tra cấu hình bắt buộc.

Kubernetes có thể không hiển thị lại trường data khi map rỗng; điều cần xác nhận là không còn entry cũ. Đừng chỉ đếm việc tài nguyên có hay không.

### Lượt D — File cấu hình rỗng

~~~powershell
Set-LabConfigData -ConfigData @{ 'application.yaml' = '' }
~~~

Quan sát lần nạp mới. Phân biệt parser từ chối nội dung trong phiên bản đang chạy với parser trả tập property rỗng. Trong cả hai trường hợp, phép thử không được coi là thành công nếu thiếu các giá trị bắt buộc.

### Lượt E — YAML bên trong sai cú pháp

~~~powershell
$badYaml = @'
catalog:
  title: "Catalog lab"
  page-size: [25
  config-revision: "lab-bad-yaml"
'@

Set-LabConfigData -ConfigData @{ 'application.yaml' = $badYaml }
~~~

API vẫn có thể chấp nhận thao tác patch vì giá trị là một chuỗi. Khi Pod mới nạp nguồn, kỳ vọng lỗi parser được đưa ra theo chính sách fail-fast. Không có dấu mốc thành công của bean cấu hình.

Nếu thông báo có số dòng hoặc cột, xác định nó đang chỉ vào chuỗi YAML lồng hay manifest ngoài. Dòng đầu của payload không nhất thiết có cùng số dòng với manifest tài nguyên.

### Lượt F — Chuỗi rỗng trong khóa bắt buộc

~~~powershell
$blankTitleYaml = @'
catalog:
  title: "   "
  page-size: 25
  config-revision: "lab-blank-title"
'@

Set-LabConfigData -ConfigData @{ 'application.yaml' = $blankTitleYaml }
~~~

YAML hợp lệ và giá trị có thể bind sang String, nhưng `@NotBlank` phải chặn tiêu đề chỉ có khoảng trắng. Đây là lỗi validation, không phải lỗi cú pháp YAML.

### Lượt G — Sai kiểu hoặc sai phạm vi

Ví dụ không bind được sang số:

~~~powershell
$wrongTypeYaml = @'
catalog:
  title: "Catalog lab"
  page-size: "abc"
  config-revision: "lab-wrong-type"
'@

Set-LabConfigData -ConfigData @{ 'application.yaml' = $wrongTypeYaml }
~~~

Kỳ vọng lỗi chuyển kiểu khi tạo `CatalogProperties`. Để thử validation phạm vi riêng, thay giá trị page-size bằng `0` trong một payload YAML hợp lệ và dùng revision khác. Lúc này parser và chuyển kiểu có thể thành công, nhưng giá trị không thỏa `@Min(1)`.

Muốn kiểm chứng thiếu key riêng, tạo payload vẫn có title và revision nhưng bỏ page-size. Kỳ vọng `@NotNull` chặn giá trị thiếu; đừng đổi đồng thời nhiều yếu tố nếu muốn xác định chính xác nguyên nhân.

### Lượt H — Phục hồi bản hợp lệ

~~~powershell
kubectl -n cm-recovery-lab set env deployment/configmap-recovery-demo SPRING_CLOUD_KUBERNETES_CONFIG_NAME-
Set-LabConfigData -ConfigData @{ 'application.yaml' = $goodYaml }
kubectl -n cm-recovery-lab get configmap catalog-runtime -o yaml
kubectl -n cm-recovery-lab rollout restart deployment/configmap-recovery-demo
kubectl -n cm-recovery-lab rollout status deployment/configmap-recovery-demo
~~~

Kiểm tra Pod mới và log đúng revision `lab-r1`. Các kết quả trên là **kỳ vọng của phép thử**, không phải số liệu đã thực thi sẵn trong cluster.

## 10. Đọc kết quả và khắc phục đúng nguyên nhân

| Quan sát | Ý nghĩa cần kiểm tra | Cách khắc phục |
| --- | --- | --- |
| Không có log Java, Events báo thiếu ConfigMap hoặc key | Container có thể chưa chạy được vì tham chiếu Pod bắt buộc | Tạo nguồn/key đúng hoặc sửa tham chiếu; xem tính optional có phù hợp không |
| Log có Forbidden | Lỗi quyền hoặc danh tính | Sửa ServiceAccount/RoleBinding và đúng động từ API |
| Có nguồn nhưng thiếu property | Data rỗng, sai key, profile, prefix hoặc nguồn không được xử lý như dự kiến | Đọc lại payload, đối chiếu cấu hình chọn nguồn và tên property |
| Lỗi scanner/parser YAML | Nội dung được chọn không parse được | Sửa payload bằng đúng cú pháp; giữ fail-fast cho dữ liệu bắt buộc |
| Conversion hoặc binding error | Giá trị không phù hợp kiểu đích | Sửa kiểu dữ liệu hoặc model cấu hình theo hợp đồng đã định |
| Constraint violation | Dữ liệu bind được nhưng vi phạm ràng buộc | Sửa giá trị trong giới hạn nghiệp vụ |
| Vẫn thấy giá trị cũ sau khi sửa | Tiến trình chưa nạp lại hoặc đang đọc nguồn khác | Đối chiếu Pod mới, revision, override và đường cập nhật cấu hình |
| Deployment vẫn phục vụ dù Pod mới lỗi | Replica cũ có thể còn hoạt động | Kiểm tra từng Pod, ReplicaSet và revision, không chỉ tình trạng phục vụ chung |

Đối với lỗi cố định như YAML hỏng hoặc sai property, cần sửa nguồn hay khôi phục bản cấu hình đã biết hợp lệ. Retry và restart chỉ tạo thêm lượt đọc nếu dữ liệu vẫn chưa được sửa.

Với lỗi kết nối API tạm thời, retry hữu hạn có thể phù hợp, nhưng đó là chính sách khác với việc chấp nhận cấu hình rỗng. Giữ kiểm tra giá trị bắt buộc ngay cả khi đã bật retry.

Nếu dùng ConfigMap bất biến (`immutable: true`), không dùng quy trình patch data của lab này. Tạo một nguồn phiên bản mới và cập nhật tham chiếu theo quy trình triển khai phù hợp thay vì cố sửa dữ liệu bị khóa.

## 11. Sau khi sửa nguồn, xác nhận mọi bản sao dùng đúng cấu hình

Cập nhật thành công đối tượng ConfigMap chưa đồng nghĩa mọi tiến trình Spring đã dùng dữ liệu mới. Lượt thử nạp qua API lúc khởi động cần Pod mới hoặc cơ chế refresh được thiết kế rõ ràng.

Nếu dùng volume, dữ liệu projected có thể cập nhật sau một khoảng thời gian, nhưng Spring không tự bind lại mọi bean chỉ vì file đã đổi. Nếu dùng environment của container, giá trị đang có cũng không tự thay đổi theo ConfigMap. Những giới hạn của đường cấp dữ liệu cần được xét trước khi kết luận sửa lỗi chưa có tác dụng.

Configuration Watcher có thể tham gia một quy trình thông báo và refresh khi ứng dụng đã được cấu hình phù hợp. Nó không thay thế parser, validation hay việc khởi tạo một context chưa từng thành công. Không mở rộng quyền hoặc bật thêm chức năng chỉ để che lỗi cấu hình ban đầu.

Khi xác nhận phục hồi, ghi nhận cho từng bản sao:

- Pod name và UID, image/phiên bản ứng dụng, thời điểm khởi động.
- Nguồn cấu hình được chọn cùng namespace và revision có hiệu lực.
- Các giá trị kiểm chứng không nhạy cảm đã bind thành công.
- Trạng thái Ready theo kiểm tra sức khỏe của ứng dụng.
- Việc không còn các override tạm hoặc payload lỗi từ lượt thử.

Revision trong payload là dấu hiệu hỗ trợ quan sát, không tự chứng minh nguồn gốc nếu cùng property có thể bị override. Kết hợp nó với đối chiếu cấu hình triển khai và nguồn dữ liệu thực tế.

## 12. Tiêu chí hoàn tất

Bạn đã xử lý được chủ đề khi có thể chứng minh:

1. Xác định rõ nguồn thiếu, không được phép đọc, data rỗng và giá trị rỗng là các tình huống khác nhau.
2. Phân biệt manifest Kubernetes hợp lệ với nội dung cấu hình bên trong parse được.
3. Chặn thiếu khóa, chuỗi trắng, sai kiểu và giá trị ngoài phạm vi ở tầng phù hợp.
4. Giải thích vì sao fail-fast và optional không thay thế validation nghiệp vụ.
5. Đọc đúng log và Events của lần chạy bị lỗi, tránh nhầm với Pod cũ hoặc lần restart khác.
6. Khôi phục được nguồn hợp lệ và xác nhận cấu hình có hiệu lực trên các bản sao cần phục vụ.

Một quy trình tốt kết thúc bằng bằng chứng rằng ứng dụng đang sử dụng cấu hình đúng và đủ, chứ không chỉ bằng việc ConfigMap đã được lưu thành công trên Kubernetes.
