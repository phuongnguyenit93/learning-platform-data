# Đối chiếu kết quả DiscoveryClient với trạng thái cluster

Trong chương **Khám phá dịch vụ** của module **SPRING_CLOUD_KUBERNETES**, bài này hướng dẫn kiểm chứng dữ liệu mà Spring Cloud DiscoveryClient trả về bằng trạng thái Kubernetes thực tế. Mục tiêu là giải thích được từng service ID, từng địa chỉ và từng cổng, đồng thời nhận diện chênh lệch do phạm vi khám phá, bộ lọc, readiness, quyền RBAC hoặc thời gian cập nhật.

Việc thấy một Service bằng `kubectl` chưa đủ chứng minh ứng dụng phải khám phá được Service đó. Tương tự, thấy một `ServiceInstance` chưa đủ chứng minh lời gọi HTTP sẽ thành công. Đối chiếu đúng cần đặt các quan sát vào cùng cluster, namespace, cấu hình và khoảng thời gian.

Sau bài học, bạn có thể:

- Phân biệt danh sách service ID, danh sách instance và trạng thái kết nối tới dịch vụ.
- Lần theo quan hệ Service → selector → Pod → EndpointSlice.
- So sánh host và port theo đúng mô hình khám phá của ứng dụng.
- Xác định chênh lệch hợp lệ khi Pod chưa Ready, đang kết thúc hoặc cluster đang rollout.
- Chẩn đoán dữ liệu thiếu, dữ liệu cũ và quyền đọc chưa đủ mà không vội thay đổi cấu hình.

Các dữ liệu địa chỉ, tên Pod và kết quả trong bài là minh họa. Chỉ chạy các lệnh thực hành trong môi trường của bạn; bài viết không khẳng định đã truy cập hay kiểm thử một cluster cụ thể.

## 1. Ba câu hỏi khác nhau cần được kiểm chứng riêng

Spring Cloud cung cấp hai phép quan sát cơ bản qua `DiscoveryClient`:

```java
List<String> serviceIds = discoveryClient.getServices();
List<ServiceInstance> instances = discoveryClient.getInstances("catalog-api");
```

Hai lời gọi này trả lời hai câu hỏi:

| Quan sát | Câu hỏi được trả lời | Điều chưa được chứng minh |
| --- | --- | --- |
| `getServices()` | Client đang liệt kê những service ID nào? | Mỗi Service có endpoint sử dụng được hay không. |
| `getInstances(serviceId)` | Client đang trả về những instance nào cho tên được hỏi? | Kết nối mạng và giao thức ứng dụng có hoạt động hay không. |
| Gọi ứng dụng từ nơi tiêu thụ thực tế | Đường mạng và request cụ thể có thành công không? | Mọi instance đều khỏe mạnh hoặc danh sách khám phá đã cập nhật hoàn toàn. |

Ở phía Kubernetes, các quan sát cũng có giới hạn:

- Service tồn tại chứng minh đối tượng Service đã có trong API, không chứng minh có Pod đích sẵn sàng.
- Pod ở pha `Running` không đồng nghĩa điều kiện `Ready` là `True`.
- EndpointSlice mô tả các endpoint cùng thông tin cổng và điều kiện; nó không phải kết quả một request HTTP vừa được thực hiện.
- Quyền đọc API của tài khoản vận hành không đại diện cho quyền đọc của ServiceAccount ứng dụng.

Vì vậy, không dùng một kết quả duy nhất làm kết luận cho toàn bộ chuỗi khám phá và gọi dịch vụ.

## 2. Mô hình dữ liệu để đối chiếu

Với Service thông thường có selector, luồng dữ liệu có thể hình dung như sau:

```text
Service.metadata.name, namespace, labels
                   |
                   | spec.selector chọn Pod trong cùng namespace
                   v
Pod labels, địa chỉ, readiness, trạng thái kết thúc
                   |
                   | bộ điều khiển Kubernetes cập nhật dữ liệu endpoint
                   v
Một hoặc nhiều EndpointSlice của Service
                   |
                   | phạm vi, RBAC, bộ lọc, cách đọc và cache của client
                   v
DiscoveryClient.getServices() / getInstances(serviceId)
                   |
                   | lựa chọn instance, cache và kết nối của bên gọi
                   v
Lời gọi ứng dụng, có thể đi qua Spring Cloud LoadBalancer
```

Đây là mô hình phục vụ chẩn đoán. Implementation DiscoveryClient có thể dùng Endpoints hoặc EndpointSlice, đọc trực tiếp hoặc dùng informer/cache. Mô hình DiscoveryServer qua HTTP còn có một thành phần trung gian. Cần xác định đường đi thật trước khi lựa chọn tài nguyên để đối chiếu.

Một số kiểu Service có đường đi khác:

| Kiểu triển khai | Điểm cần điều chỉnh khi đối chiếu |
| --- | --- |
| Service thông thường có selector | Kiểm tra selector, Pod phù hợp và dữ liệu endpoint do Kubernetes quản lý. |
| Headless Service có `clusterIP: None` | Không chờ một ClusterIP để so sánh; xem địa chỉ endpoint và cách client ánh xạ chúng. |
| Service không có selector | Endpoint có thể được quản lý riêng; không mặc định phải có Pod do selector chọn. |
| `ExternalName` | Đích liên quan tên DNS bên ngoài, không mặc định có Pod hoặc EndpointSlice do selector tạo; kiểm tra client có hỗ trợ và bật loại Service này không. |

Trong bài thực hành chính, ta sử dụng Service thông thường có selector để tập trung vào phép đối chiếu.

## 3. Cố định ngữ cảnh trước khi so sánh

### 3.1. Xác nhận cluster và namespace của lệnh vận hành

```bash
kubectl config current-context
kubectl config view --minify -o jsonpath='{.contexts[0].context.namespace}'
kubectl -n commerce get service catalog-api
```

Kết quả namespace rỗng trong kubeconfig không có nghĩa tài nguyên nằm trong một namespace tên rỗng. Khi không có chỉ định khác, `kubectl` dùng namespace mặc định. Trong quá trình đối chiếu, viết rõ `-n commerce` để giảm nhầm lẫn.

Ở phía ứng dụng, ghi nhận tối thiểu:

- Ứng dụng đang chạy trong cluster hay chạy ngoài cluster qua kubeconfig.
- Namespace của Pod và phạm vi namespace mà DiscoveryClient được cấu hình khám phá.
- Kubernetes DiscoveryClient trực tiếp, HTTP DiscoveryClient hay một CompositeDiscoveryClient đang trả kết quả.
- Các bộ lọc label hoặc biểu thức đang có hiệu lực.
- Cách chọn cổng và chính sách sử dụng endpoint chưa sẵn sàng.

Ứng dụng đặt trong namespace `frontend` có thể được cấu hình đọc Service ở `commerce`, nhiều namespace hoặc chỉ namespace của chính nó. Không suy phạm vi khám phá chỉ từ namespace của Pod gọi.

### 3.2. Đối chiếu đúng cấu hình đang chạy

File cấu hình trong mã nguồn không luôn trùng cấu hình hiệu lực của Pod. Biến môi trường, profile, tham số khởi động, ConfigMap hoặc nguồn cấu hình khác có thể ghi đè giá trị.

Trong phạm vi module này, ConfigMap và Secret có thể cung cấp cấu hình, còn Configuration Watcher có thể tham gia thông báo thay đổi khi được thiết lập. Tuy nhiên, việc nguồn cấu hình đã đổi không chứng minh bean DiscoveryClient đã được tạo lại hoặc nhận mọi giá trị mới. Cần xác minh vòng đời cấu hình của chính triển khai đó.

Chỉ ghi nhận các giá trị cần cho chẩn đoán như namespace, bộ lọc và chế độ chọn endpoint. Không in toàn bộ môi trường, Secret, token ServiceAccount hay kubeconfig để chứng minh cấu hình.

### 3.3. Gắn thời gian cho từng quan sát

Kubernetes liên tục thay đổi trạng thái trong lúc rollout, scale hoặc xử lý Pod lỗi. Một ảnh chụp từ `kubectl` lúc 10:00:00 và một log DiscoveryClient lúc 10:00:10 có thể phản ánh hai trạng thái hợp lệ khác nhau.

Ghi lại thời điểm bắt đầu và kết thúc lấy dữ liệu. Có thể lưu ý `resourceVersion` để nhận diện phiên bản của từng đối tượng, nhưng không dùng giá trị này như đồng hồ thời gian hoặc giả định các lần đọc Service, Pod và EndpointSlice tạo thành một transaction nguyên tử.

## 4. Thu thập dữ liệu cluster theo đúng quan hệ

### 4.1. Đọc Service trước khi chọn Pod

```bash
kubectl -n commerce get service catalog-api -o yaml
```

Giả sử phần quan trọng của kết quả là:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: commerce
  labels:
    app.kubernetes.io/part-of: commerce
    discovery-enabled: "true"
spec:
  type: ClusterIP
  clusterIP: 10.96.132.40
  publishNotReadyAddresses: false
  selector:
    app: catalog
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
```

Những dữ liệu cần ghi nhận:

| Trường | Giá trị minh họa | Ý nghĩa khi đối chiếu |
| --- | --- | --- |
| `metadata.name` | `catalog-api` | Tên Service dùng làm đối tượng tra cứu. |
| `metadata.namespace` | `commerce` | Phân biệt với Service trùng tên ở namespace khác. |
| `metadata.labels` | `discovery-enabled: "true"` | Có thể quyết định Service có vượt qua bộ lọc khám phá không. |
| `spec.selector` | `app: catalog` | Chọn Pod; khác với label của chính Service. |
| `spec.clusterIP` | `10.96.132.40` | Địa chỉ ảo của Service, không phải địa chỉ một Pod. |
| `ports[].port` | `80` | Cổng của Service khi đi qua địa chỉ Service. |
| `ports[].targetPort` | `8080` | Cổng đích phía endpoint trong ví dụ dùng giá trị số này. |

Nếu Service có nhiều cổng, ghi lại tên, protocol và từng cặp cổng. Không lấy cổng ở dòng đầu rồi giả định client luôn chọn cổng đó.

### 4.2. Dùng selector thực của Service để đọc Pod

Với selector `app: catalog` trong ví dụ:

```bash
kubectl -n commerce get pods -l app=catalog -o wide
```

Giả sử dữ liệu quan sát được như sau:

| Pod | Pod IP | Pha | `Ready` | Đang kết thúc |
| --- | --- | --- | --- | --- |
| `catalog-a` | `10.244.2.17` | Running | True | Không |
| `catalog-b` | `10.244.3.22` | Running | False | Không |

Lệnh liệt kê Pod cho cột readiness và trạng thái tổng quát. Khi cần biết nguyên nhân, đọc chi tiết Pod thực tế:

```bash
kubectl -n commerce describe pod catalog-b
kubectl -n commerce get pod catalog-b -o yaml
```

Các tên Pod ở đây là minh họa; thay bằng tên thu được từ lệnh liệt kê. Kiểm tra readiness probe, các điều kiện Pod, sự kiện và `deletionTimestamp` thay vì chỉ nhìn chữ `Running`.

`app: catalog` phải xuất phát từ selector của Service. Không đoán selector từ tên `catalog-api`, cũng không lấy label của Service rồi mặc định đó là bộ label của Pod.

### 4.3. Đọc toàn bộ EndpointSlice thuộc Service

```bash
kubectl -n commerce get endpointslices \
  -l kubernetes.io/service-name=catalog-api -o yaml
```

Một Service có thể liên quan nhiều EndpointSlice. Phải xét tất cả slice phù hợp trong cùng namespace, không chỉ slice đầu tiên hoặc một tên slice được nhớ từ lần triển khai trước.

Dữ liệu minh họa rút gọn của một slice:

```yaml
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: catalog-api-example
  namespace: commerce
  labels:
    kubernetes.io/service-name: catalog-api
addressType: IPv4
ports:
  - name: http
    protocol: TCP
    port: 8080
endpoints:
  - addresses:
      - 10.244.2.17
    conditions:
      ready: true
      serving: true
      terminating: false
    targetRef:
      kind: Pod
      namespace: commerce
      name: catalog-a
  - addresses:
      - 10.244.3.22
    conditions:
      ready: false
      serving: false
      terminating: false
    targetRef:
      kind: Pod
      namespace: commerce
      name: catalog-b
```

Đây là ví dụ đọc kết quả, không phải manifest để tự apply sửa tài nguyên do controller quản lý. Khi sai dữ liệu endpoint, trước tiên tìm nguyên nhân ở selector, Pod, readiness hoặc cơ chế quản lý endpoint.

Nếu implementation đang dùng API Endpoints, đọc thêm tài nguyên mà nó thực sự tiêu thụ:

```bash
kubectl -n commerce get endpoints catalog-api -o yaml
```

Với Endpoints, phân biệt địa chỉ sẵn sàng trong `subsets[].addresses` và địa chỉ chưa sẵn sàng trong `subsets[].notReadyAddresses`, cùng các cổng của subset. Không buộc kết quả Endpoints và EndpointSlice phải giống nhau bằng cách so sánh số dòng; mô hình chia nhóm, khả năng biểu đạt và giới hạn của hai API khác nhau.

Cú pháp nối dòng bằng `\` trong các lệnh minh họa dành cho shell kiểu Bash. Khi dùng PowerShell, có thể viết nguyên lệnh trên một dòng.

## 5. Lấy ảnh chụp từ DiscoveryClient

Trong một ứng dụng đã có dependency Kubernetes DiscoveryClient và cấu hình truy cập cluster phù hợp, có thể dùng probe khởi động sau để quan sát:

```java
import java.time.Instant;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DiscoverySnapshotConfiguration {

    @Bean
    ApplicationRunner discoverySnapshot(DiscoveryClient discoveryClient) {
        return args -> {
            String serviceId = "catalog-api";
            Instant startedAt = Instant.now();

            System.out.println("snapshot.startedAt=" + startedAt);
            System.out.println("client.type="
                    + discoveryClient.getClass().getName());

            List<String> serviceIds = discoveryClient.getServices();
            serviceIds.stream()
                    .sorted()
                    .forEach(id -> System.out.println("serviceId=" + id));

            List<ServiceInstance> instances =
                    discoveryClient.getInstances(serviceId);

            System.out.println("lookup.serviceId=" + serviceId);
            System.out.println("lookup.instanceCount=" + instances.size());

            for (ServiceInstance instance : instances) {
                System.out.printf(
                        "instance serviceId=%s host=%s port=%d secure=%s%n",
                        instance.getServiceId(),
                        instance.getHost(),
                        instance.getPort(),
                        instance.isSecure());
            }

            System.out.println("snapshot.finishedAt=" + Instant.now());
        };
    }
}
```

Probe này không chủ động gửi request mạng tới dịch vụ đích. `secure` là thông tin mà client cung cấp cho instance, không phải chứng cứ một TLS handshake đã thành công.

Probe cũng chỉ chạy một lần khi khởi tạo ứng dụng. Nếu cần xem dữ liệu sau rollout, phải lấy một ảnh chụp mới qua công cụ chẩn đoán được kiểm soát của dự án; không tiếp tục dùng log khởi động cũ để đại diện trạng thái hiện tại. Không mở endpoint chẩn đoán công khai chỉ để in toàn bộ dữ liệu discovery.

Một số lưu ý khi đọc log:

- Tên lớp có thể là proxy hoặc CompositeDiscoveryClient; dòng `client.type` là điểm bắt đầu điều tra, không luôn xác định đầy đủ client bên dưới.
- Trong mô hình HTTP DiscoveryClient, dữ liệu có thể đến từ DiscoveryServer cùng cache của nó. Cần quan sát phía server truy vấn Kubernetes khi xác định độ trễ hoặc quyền đọc.
- Hai lời gọi `getServices()` và `getInstances()` không tạo một ảnh chụp nguyên tử; cluster có thể thay đổi giữa chúng.
- Metadata instance phụ thuộc implementation và cấu hình. Không giả định luôn có một key namespace hay pod-name cụ thể, và không in tất cả metadata một cách mặc định.

## 6. So sánh đúng host và port

### 6.1. Phân biệt địa chỉ endpoint với địa chỉ Service

Trong ví dụ:

```text
Địa chỉ Service: 10.96.132.40:80
Endpoint Pod:   10.244.2.17:8080
```

Cả hai cặp địa chỉ có thể đúng trong các đường đi khác nhau. Địa chỉ Service dùng cổng `spec.ports[].port`; địa chỉ endpoint trong ví dụ dùng cổng đích được công bố ở EndpointSlice.

Nếu DiscoveryClient đang cung cấp instance theo endpoint, kết quả minh họa có thể là:

```text
instance serviceId=catalog-api host=10.244.2.17 port=8080 secure=false
```

Không kết luận sai cổng chỉ vì Service khai báo `port: 80`. Phải xác định client trả instance ở cấp endpoint hay cấp Service trước khi chọn dữ liệu chuẩn để so sánh. Một chế độ cung cấp địa chỉ Service hoặc DNS cần được so với địa chỉ và cổng tương ứng của Service; không mặc định mọi implementation hỗ trợ mọi chế độ đó.

Spring Cloud LoadBalancer có thể dùng danh sách instance để chọn đích. Nếu nó nhận Pod IP và cổng endpoint, việc lấy ClusterIP làm chuẩn đối chiếu duy nhất sẽ tạo ra một cảnh báo sai.

### 6.2. Service nhiều cổng và named targetPort

Giả sử một Service có:

```yaml
ports:
  - name: http
    port: 80
    targetPort: web
  - name: management
    port: 9090
    targetPort: management
```

`targetPort` ở đây là tên, không phải số cổng có thể đem so trực tiếp với `ServiceInstance.getPort()`. Kubernetes phải ánh xạ tên tới cổng container phù hợp. Kiểm tra dữ liệu cổng trong EndpointSlice, cấu hình Pod và quy tắc chọn cổng của implementation đang sử dụng.

Khi chẩn đoán, ghi rõ client đang chọn cổng nghiệp vụ hay cổng quản trị. Khám phá đúng Pod nhưng chọn cổng quản trị vẫn có thể làm lời gọi nghiệp vụ thất bại. Không sửa Service chỉ để hai con số trong hai tầng khác nhau trông giống nhau.

### 6.3. Chuẩn hóa đơn vị so sánh

Đối với trường hợp một namespace, một cổng TCP và instance theo endpoint, dùng tập các cặp `(address, port)` làm đơn vị cơ bản. Khi cần phân biệt nhiều loại đích, bổ sung namespace, Service, protocol và address family.

Tránh các phép so sánh dễ gây kết luận sai:

- Số Pod bằng số instance: không đúng trong mọi cấu hình readiness, dual-stack, chọn endpoint hoặc cách tổng hợp.
- Số EndpointSlice bằng số instance: một slice có thể chứa nhiều endpoint và một Service có nhiều slice.
- Một chuỗi IP bằng tên DNS: cần xác định cách biểu diễn và ngữ cảnh phân giải trước.
- Nối host và port tùy ý bằng dấu `:` rồi parse lại: dễ nhầm với địa chỉ IPv6; giữ host và port thành hai trường riêng khi so sánh.

Khi hợp nhất dữ liệu từ nhiều slice, nhận diện endpoint trùng theo khóa phù hợp. Đồng thời ghi nhận số phần tử gốc nếu cần phát hiện một implementation trả dữ liệu trùng. Việc dùng tập hợp để so sánh không nên che giấu lỗi nhân đôi dữ liệu.

## 7. Readiness quyết định tập endpoint kỳ vọng như thế nào?

### 7.1. Tính tập kỳ vọng theo chính sách thực tế

Với dữ liệu ở mục 4, giả sử triển khai minh họa có các điều kiện:

- Dùng instance theo endpoint.
- Chỉ nhận địa chỉ sẵn sàng.
- Chọn cổng `http` của endpoint.
- Không có bộ lọc bổ sung loại `catalog-api`.
- Dữ liệu đã hội tụ sau thay đổi.

Tập địa chỉ kỳ vọng là:

```text
E_cluster = {(10.244.2.17, 8080)}
```

Pod `catalog-b` đang `Running` nhưng endpoint của nó có `ready: false`, nên không thuộc tập kỳ vọng theo chính sách đang giả định. Danh sách chỉ có một instance không tự động là lỗi thiếu dữ liệu.

Nếu cấu hình chủ động lấy cả địa chỉ chưa sẵn sàng và implementation hỗ trợ điều đó, tập dự kiến có thể khác. Phải ghi rõ chính sách trước khi dùng số lượng làm tiêu chí kiểm chứng.

### 7.2. Không đồng nhất mọi điều kiện trạng thái

| Trường hoặc trạng thái | Ý nghĩa cần xét |
| --- | --- |
| Pod `phase: Running` | Pod đã ở pha chạy; không đủ để kết luận sẵn sàng nhận lưu lượng. |
| Điều kiện Pod `Ready` | Trạng thái sẵn sàng ở cấp Pod; xem thêm probe và readiness gate khi có. |
| EndpointSlice `ready` | Tín hiệu sẵn sàng của endpoint theo ngữ nghĩa API và cấu hình Service. |
| EndpointSlice `serving` | Thông tin phục vụ liên quan trạng thái endpoint, có ích khi xét endpoint đang kết thúc. |
| EndpointSlice `terminating` | Cho biết endpoint có đang trong quá trình kết thúc hay không. |

Một condition có thể vắng mặt hoặc có giá trị chưa xác định. Không tự đồng nhất trường bị thiếu với `false` mà chưa kiểm tra quy ước của API và cách implementation diễn giải nó.

`Service.spec.publishNotReadyAddresses` cũng làm thay đổi cách công bố địa chỉ chưa sẵn sàng. Khi tính kỳ vọng, đọc trường này thay vì coi `ready` trong EndpointSlice luôn là bản sao trực tiếp của điều kiện `Ready` trên Pod.

Với Pod đang kết thúc, kiểm tra đồng thời thời gian, `deletionTimestamp`, các condition endpoint và chính sách của client. Không quy định máy móc rằng một endpoint sẽ biến mất khỏi mọi cache đúng tại thời điểm Pod bắt đầu kết thúc.

## 8. Tính phần thiếu và phần thừa từ hai tập quan sát

Sau khi chuẩn hóa dữ liệu trong cùng ngữ cảnh, gọi:

```text
E_cluster   = tập endpoint kỳ vọng theo chính sách đã chọn
E_discovery = tập instance DiscoveryClient vừa trả về

Missing = E_cluster - E_discovery
Extra   = E_discovery - E_cluster
```

Trong ví dụ một endpoint Ready:

| `E_discovery` | `Missing` | `Extra` | Hướng diễn giải ban đầu |
| --- | --- | --- | --- |
| `{(10.244.2.17,8080)}` | Rỗng | Rỗng | Khớp trong ảnh chụp và chính sách này. |
| Rỗng | `{(10.244.2.17,8080)}` | Rỗng | Kiểm tra bộ lọc, namespace, quyền đọc, chọn cổng và thời gian đồng bộ. |
| Có cả hai IP Pod | Rỗng | `{(10.244.3.22,8080)}` | Kiểm tra chính sách not-ready hoặc dữ liệu cũ trước khi kết luận. |
| Chỉ có `(10.96.132.40,80)` | Không so trực tiếp | Không so trực tiếp | Xác minh chế độ địa chỉ trước; có thể đang so hai tầng khác nhau. |

`Missing` và `Extra` là dấu hiệu để điều tra. Chúng chỉ có ý nghĩa khi đã thống nhất cách dựng tập kỳ vọng. Nếu một tập là Pod IP còn tập kia là địa chỉ Service, phép trừ tập hợp vẫn chạy được về mặt toán học nhưng kết luận chẩn đoán không đúng.

Đối với `getServices()`, thực hiện phép so sánh riêng trên tập service ID được phép xuất hiện sau khi áp dụng phạm vi và bộ lọc. Một Service có tên trong danh sách nhưng không có endpoint Ready có thể dẫn tới danh sách instance rỗng mà không mâu thuẫn.

Ngược lại, việc một tên không có trong `getServices()` không đủ để dự đoán mọi đường tra cứu trực tiếp của mọi implementation. Kiểm tra riêng `getInstances(serviceId)` khi điều tra hành vi thực tế.

## 9. Vì sao quan sát của ứng dụng có thể chậm hơn cluster?

Có nhiều khoảng cập nhật khác nhau:

```text
Pod đổi trạng thái
    -> controller cập nhật endpoint
    -> watch, informer hoặc lần truy vấn của discovery nhận dữ liệu
    -> cache discovery thay đổi
    -> cache của luồng LoadBalancer, nếu có, thay đổi
    -> request tiếp theo chọn một đích
```

Không gán một thời hạn đồng bộ chung như “luôn cập nhật ngay” hoặc “luôn mất 30 giây” cho mọi triển khai. Khoảng trễ phụ thuộc implementation, cấu hình, trạng thái kết nối tới API server và các cache đang được sử dụng.

Khi điều tra một đợt rollout, có thể quan sát biến động:

```bash
kubectl -n commerce get pods -l app=catalog -w
kubectl -n commerce get endpointslices \
  -l kubernetes.io/service-name=catalog-api -w
```

Các lệnh watch chạy ở phiên terminal riêng và được người vận hành dừng khi đủ dữ liệu. Kết hợp thời gian quan sát với các ảnh chụp DiscoveryClient mới, thay vì so một log khởi động cũ với dữ liệu cluster đang thay đổi.

Nếu kết quả không hội tụ sau khoảng quan sát phù hợp với cấu hình, kiểm tra log lỗi watch, reconnect, informer, lỗi quyền hoặc lỗi truy cập API server. Việc một lần `kubectl get` thành công bằng tài khoản cá nhân không loại trừ các lỗi đó ở ứng dụng.

## 10. Kiểm tra RBAC dưới đúng danh tính

Giả sử ứng dụng dùng ServiceAccount `storefront` trong namespace `commerce`. Người có quyền impersonation phù hợp có thể kiểm tra một phần quyền đọc:

```bash
kubectl auth can-i list services \
  --as=system:serviceaccount:commerce:storefront -n commerce

kubectl auth can-i list endpointslices.discovery.k8s.io \
  --as=system:serviceaccount:commerce:storefront -n commerce

kubectl auth can-i watch endpointslices.discovery.k8s.io \
  --as=system:serviceaccount:commerce:storefront -n commerce
```

Chọn tài nguyên và verb theo implementation. Nếu client đọc Endpoints thì kiểm tra quyền tương ứng cho Endpoints; nếu dùng thao tác `get` hoặc watch Service thì kiểm tra những quyền đó. Các lệnh trên là ví dụ, không phải danh sách RBAC đầy đủ cho mọi cấu hình.

Phân biệt ba khả năng:

1. API server trả tài nguyên nhưng bộ lọc của ứng dụng chủ động loại bỏ.
2. API server từ chối truy cập vì thiếu quyền.
3. Ứng dụng không truy cập được API server do mạng, chứng thực hoặc cấu hình địa chỉ.

Ba tình huống này có cách xử lý khác nhau. Không cấp quyền toàn cluster chỉ vì kết quả khám phá rỗng; trước tiên xác định đúng namespace, tài nguyên và thao tác bị thiếu. Bộ lọc label tại client không tự thu hẹp quyền mà RBAC đã cấp, và cũng không cấp thêm quyền đọc.

## 11. Bảng chẩn đoán theo dấu hiệu

| Dấu hiệu | Điều cần xác minh trước | Hướng xử lý tiếp theo |
| --- | --- | --- |
| `kubectl` thấy Service nhưng `getServices()` không có | Cùng cluster, namespace, client và cấu hình lọc chưa? | Đọc label Service, biểu thức, quyền ServiceAccount và cấu hình hiệu lực. |
| Có service ID nhưng instance rỗng | Service có endpoint phù hợp và Ready không? | Kiểm tra selector, Pod, slice hoặc Endpoints và chính sách readiness. |
| Ít instance hơn số Pod `Running` | Có Pod chưa Ready hoặc đang kết thúc không? | So sánh condition endpoint và chính sách của client, không chỉ đếm Pod. |
| Instance dùng Pod IP trong khi Service có ClusterIP khác | Đang dùng mô hình địa chỉ nào? | So với endpoint khi client trả địa chỉ endpoint. |
| Port khác `Service.port` | Instance đại diện Service hay endpoint? | Đọc endpoint port, named targetPort và quy tắc chọn cổng. |
| IP của Pod cũ vẫn xuất hiện sau rollout | Ảnh chụp có mới và dữ liệu đã hội tụ chưa? | Quan sát watch, cache và lỗi cập nhật phía discovery; kiểm tra cả cache LoadBalancer. |
| Trả cả địa chỉ chưa Ready | Client có chủ động cho phép không, Service có công bố not-ready không? | Đối chiếu chính sách trước khi coi là lỗi. |
| Có tên hoặc địa chỉ ngoài dự kiến | Có nhiều namespace, Service trùng tên hoặc nhiều DiscoveryClient không? | Tách nguồn dữ liệu, ghi rõ namespace và cách tổng hợp. |
| DiscoveryClient đúng nhưng request vẫn thất bại | Lỗi ở instance nào và từ Pod gọi nào? | Kiểm tra đường mạng, NetworkPolicy, port, giao thức, TLS và hành vi ứng dụng. |
| Chỉ ứng dụng lỗi đọc API, `kubectl` cá nhân vẫn thành công | Hai bên có dùng cùng danh tính không? | Kiểm tra ServiceAccount, RBAC và chứng thực của ứng dụng. |

Với Service trùng tên ở nhiều namespace, `serviceId` dạng tên đơn có thể không đủ để diễn đạt ý định. Cách tổng hợp hoặc phân biệt phụ thuộc implementation và cấu hình đa namespace. Không suy ra rằng client tự chọn đúng namespace nghiệp vụ chỉ vì các đối tượng cùng tên.

## 12. Từ dữ liệu đúng tới lời gọi thành công

Sau khi `E_discovery` khớp tập kỳ vọng, kiểm tra đường gọi từ đúng nơi tiêu thụ. Một Pod ở namespace khác có thể chịu chính sách mạng khác; một lệnh thử từ máy cá nhân cũng có đường đi khác với request của ứng dụng.

Nếu ứng dụng dùng Spring Cloud LoadBalancer, cần xác định đích mà lời gọi thực tế đã chọn. Danh sách DiscoveryClient đúng không bảo đảm một cache khác đã nhận dữ liệu mới, cũng không bảo đảm lần gọi vừa rồi sử dụng đúng cổng và giao thức.

Tách các bằng chứng:

| Bằng chứng | Kết luận có thể đưa ra |
| --- | --- |
| Service và endpoint đúng | Dữ liệu Kubernetes đang biểu đạt đích dự kiến. |
| DiscoveryClient khớp endpoint kỳ vọng | Luồng khám phá được kiểm tra đang phản ánh dữ liệu phù hợp trong ảnh chụp đó. |
| Kết nối TCP từ Pod gọi thành công | Đường kết nối tới host và port được thử hoạt động tại thời điểm thử. |
| Request nghiệp vụ thành công | Đường mạng, giao thức và xử lý cho request cụ thể đã hoạt động. |

Một readiness probe là tín hiệu cho điều phối lưu lượng, không thay thế toàn bộ kiểm thử nghiệp vụ. Ngược lại, một request lỗi do chứng thực không chứng minh endpoint đã được khám phá sai.

Đối chiếu giúp quyết định thành phần thật sự cần thiết. Nếu ứng dụng chỉ gọi Service qua DNS cố định, có thể không cần thêm Kubernetes DiscoveryClient hoặc LoadBalancer chỉ để liệt kê tài nguyên. Nếu đã dùng khám phá động, cần theo dõi cả tính đúng của dữ liệu và sự hội tụ sau thay đổi.

## 13. Bài thực hành có kết quả kỳ vọng

Thực hành trong namespace thử nghiệm với Service `catalog-api`, hai Pod phù hợp selector và một ứng dụng quan sát đã được cấp quyền đọc cần thiết. Không sửa readiness của môi trường production chỉ để tạo tình huống minh họa.

### Bước 1: Chụp trạng thái ổn định

- Đọc Service, toàn bộ EndpointSlice liên quan và các Pod được selector chọn.
- Ghi lại cluster, namespace, chính sách readiness, cổng được chọn và thời điểm.
- Lấy ảnh chụp mới của `getServices()` và `getInstances("catalog-api")`.

**Kỳ vọng:** trong cấu hình theo endpoint, chỉ lấy Ready và một cổng đã xác định, các cặp host–port từ client khớp tập endpoint phù hợp sau khi dữ liệu hội tụ.

### Bước 2: Tạo một Pod chưa sẵn sàng theo kịch bản thử nghiệm

Dùng cơ chế của workload thử nghiệm để một Pod không đạt readiness. Giữ nguyên selector và kiểm tra rằng Pod có thể vẫn `Running` trong khi `Ready=False`.

**Kỳ vọng:** endpoint thay đổi condition; khi chính sách chỉ lấy Ready và dữ liệu đã hội tụ, Pod đó không thuộc tập instance sử dụng được theo chính sách. Không cần Service biến mất khỏi danh sách service ID.

### Bước 3: Quan sát rollout hoặc scale

Thực hiện thay đổi được môi trường thử nghiệm cho phép. Quan sát Pod và endpoint, rồi lấy thêm các ảnh chụp DiscoveryClient có gắn thời gian.

**Kỳ vọng:** có thể có giai đoạn chuyển tiếp. Sau khi hệ thống ổn định, instance của Pod cũ không còn trong tập kỳ vọng và instance mới xuất hiện theo readiness cùng chính sách của client.

### Bước 4: Tạo chênh lệch có chủ đích bằng bộ lọc

Trong cấu hình thử nghiệm, áp dụng một bộ lọc label không khớp với label của Service và triển khai cấu hình theo quy trình hiện có. Giữ nguyên workload.

**Kỳ vọng:** tài nguyên và endpoint vẫn có thể tồn tại trong cluster, nhưng kết quả khám phá trên đường chịu bộ lọc thay đổi. Đây là ví dụ phân biệt dữ liệu bị loại theo cấu hình với dữ liệu không tồn tại ở Kubernetes.

### Bước 5: Khôi phục và ghi kết luận

Khôi phục cấu hình, readiness và số replica của môi trường thử nghiệm theo quy trình của nhóm. Xác nhận dữ liệu đã hội tụ rồi ghi kết quả theo mẫu:

```text
Cluster/context:
Namespace được quan sát:
Client/implementation:
Khoảng thời gian lấy dữ liệu:
Phạm vi namespace và bộ lọc:
Mô hình địa chỉ và cổng được chọn:
Chính sách readiness:
Tập endpoint kỳ vọng:
Tập instance quan sát:
Missing:
Extra:
Kết quả gọi từ nơi tiêu thụ, nếu có:
Nguyên nhân chênh lệch và bằng chứng:
```

Không ghi “DiscoveryClient đúng” chỉ vì có một service ID hoặc một IP xuất hiện. Kết luận cần gắn với phạm vi, chính sách và thời điểm đã quan sát.

## 14. Tự kiểm tra kiến thức

**Service tồn tại nhưng `getInstances()` rỗng có luôn là lỗi thư viện không?**

Không. Service có thể không chọn được Pod, chưa có endpoint Ready, không có cổng phù hợp hoặc không vượt qua điều kiện của client. Cũng cần xét namespace, quyền và thời điểm cập nhật.

**Vì sao không lấy số Pod `Running` làm số instance bắt buộc?**

`Running` không đồng nghĩa `Ready`. Ngoài ra, việc chọn endpoint, address family, cổng và cách tổng hợp có thể làm số lượng khác nhau. Cần so các địa chỉ hợp lệ theo chính sách đã xác định.

**DiscoveryClient trả `10.244.2.17:8080`, còn Service là `10.96.132.40:80`. Có phải sai không?**

Chưa thể kết luận. Nếu instance đại diện endpoint, Pod IP và cổng endpoint là dữ liệu cần so sánh. Nếu client dự kiến cung cấp địa chỉ Service thì dùng chuẩn khác. Phải xác định mô hình địa chỉ trước.

**Lệnh `kubectl` cá nhân đọc được dữ liệu có chứng minh Pod có đủ RBAC không?**

Không. Hai bên có thể dùng hai danh tính và hai cấu hình truy cập khác nhau. Kiểm tra ServiceAccount thật cùng các tài nguyên và verb mà implementation sử dụng.

**Tập instance đã khớp endpoint có đủ chứng minh request thành công không?**

Không. Cần kiểm tra riêng đường gọi từ nơi tiêu thụ, cổng, giao thức, mạng và xử lý ứng dụng. Đối chiếu discovery chứng minh tính phù hợp của dữ liệu quan sát trong một ngữ cảnh cụ thể.

Khi hoàn thành bài, bạn cần lần theo được mỗi instance từ cấu hình client tới Service, endpoint và workload liên quan, hoặc giải thích được vì sao trường hợp đặc biệt không đi theo quan hệ Pod thông thường. Một báo cáo đối chiếu có giá trị luôn nêu dữ liệu kỳ vọng, dữ liệu thực tế, chênh lệch và bằng chứng đủ để hành động.
