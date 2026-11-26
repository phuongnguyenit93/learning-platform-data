# Các nhóm chức năng: khám phá dịch vụ, cấu hình và điều phối

Trong một ứng dụng Spring triển khai trên Kubernetes, ba câu hỏi xuất hiện rất sớm: ứng dụng gọi dịch vụ khác bằng cách nào, cấu hình được đưa vào và cập nhật ra sao, và ai chịu trách nhiệm giữ hệ thống hoạt động khi Pod được tạo hoặc thay thế?

Spring Cloud Kubernetes cung cấp các tích hợp để ứng dụng Spring làm việc với tài nguyên và cơ chế của Kubernetes. Các tích hợp này liên quan đến `DiscoveryClient`, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher. Tuy nhiên, không phải mọi ứng dụng Spring chạy trong cluster đều cần tất cả các tính năng đó. Kubernetes đã có cơ chế khám phá qua DNS, cung cấp cấu hình và điều phối vòng đời workload.

Bài học thuộc phần **Tổng quan** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là phân biệt ba nhóm chức năng, nhận biết phần Kubernetes đã đảm nhiệm và chọn phần tích hợp Spring Cloud Kubernetes thực sự cần cho một triển khai cụ thể.

## 1. Bản đồ trách nhiệm

Xét một hệ thống bán hàng gồm `order-api` và `catalog-api`. `order-api` cần gọi `catalog-api`, đọc giới hạn xử lý đơn hàng và tiếp tục phục vụ khi một bản sao của `catalog-api` bị thay thế.

| Nhóm chức năng | Câu hỏi chính | Kubernetes cung cấp | Spring Cloud Kubernetes có thể bổ sung |
| --- | --- | --- | --- |
| Khám phá dịch vụ | Dịch vụ ở đâu và có những instance nào? | Service, DNS và thông tin endpoint | Tích hợp `DiscoveryClient`; hỗ trợ đưa thông tin dịch vụ vào hệ sinh thái Spring Cloud |
| Cấu hình | Ứng dụng lấy tham số và thông tin nhạy cảm từ đâu? | ConfigMap, Secret, biến môi trường và volume | Đưa cấu hình Kubernetes vào Spring `Environment`; phối hợp phát hiện thay đổi với cơ chế refresh khi được cấu hình phù hợp |
| Điều phối và phối hợp vận hành | Ai tạo, thay thế, định tuyến đến Pod và phối hợp công việc giữa các bản sao? | Deployment, bộ lập lịch, controller, probe và cơ chế Service | Tích hợp thông tin môi trường cluster, khám phá phục vụ định tuyến và những cơ chế phối hợp tùy chọn được phiên bản đang dùng hỗ trợ |

**Điều phối workload thuộc Kubernetes.** Thêm Spring Cloud Kubernetes không biến ứng dụng thành bộ lập lịch Pod, không tự tạo Deployment và không thay thế controller của cluster.

Ngoài ra, khám phá dịch vụ và cân bằng tải là hai quyết định khác nhau. Khám phá trả lời “có thể gọi ai”; cân bằng tải trả lời “lần gọi này chọn đích nào”. Cấu hình cũng có hai giai đoạn riêng: lấy giá trị vào ứng dụng và làm cho hành vi đang chạy sử dụng giá trị mới.

## 2. Nhóm khám phá dịch vụ

### 2.1. Service tạo một địa chỉ ổn định trước tập Pod thay đổi

Pod có thể bị thay thế khi triển khai phiên bản mới, khi node gặp sự cố hoặc khi số replica thay đổi. Vì vậy, cấu hình cố định địa chỉ IP của từng Pod thường làm ứng dụng gọi đến địa chỉ đã hết hiệu lực.

Một Service dùng selector để gắn với nhóm Pod phù hợp. Trong cấu hình Service thông thường, lớp mạng của cluster chuyển lưu lượng tới các endpoint đủ điều kiện. DNS giúp ứng dụng tìm Service bằng tên.

Ví dụ dưới đây giả định namespace `shop` đã tồn tại và Pod của ứng dụng danh mục mang nhãn `app: catalog-api`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: shop
spec:
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

Từ `order-api` trong cùng namespace, một HTTP client thông thường có thể gọi:

```text
http://catalog-api:8080/products/42
```

Với tên đầy đủ, địa chỉ thường có dạng `catalog-api.shop.svc.cluster.local`; phần miền cluster có thể được cấu hình khác. Để gọi từ namespace khác, tên dạng `catalog-api.shop` cũng giúp xác định namespace đích trong môi trường DNS Kubernetes thông thường.

Đường đi này sử dụng cơ chế Service và DNS của Kubernetes. Ứng dụng không cần một `DiscoveryClient` chỉ để phân giải tên Service, và thông thường không cần quyền đọc Kubernetes API cho mục đích gọi HTTP qua DNS.

### 2.2. DiscoveryClient đưa khám phá dịch vụ vào mô hình Spring Cloud

Khi ứng dụng cần truy vấn danh sách dịch vụ hoặc instance bằng abstraction của Spring Cloud, tích hợp `DiscoveryClient` trở nên hữu ích. Một số trường hợp tiêu biểu là xây dựng định tuyến động, dùng thành phần Spring Cloud đã tích hợp discovery hoặc quan sát thông tin instance ở tầng ứng dụng.

Ví dụ sau minh họa việc đọc danh sách instance. Giả định ứng dụng đã cấu hình một implementation `DiscoveryClient` phù hợp của Spring Cloud Kubernetes và có quyền truy cập cần thiết:

```java
import java.net.URI;
import java.util.List;

import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogDirectory {

    private final DiscoveryClient discoveryClient;

    public CatalogDirectory(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-api")
                .stream()
                .map(instance -> instance.getUri())
                .toList();
    }
}
```

Đây là ví dụ về abstraction khám phá, không phải một HTTP client hoàn chỉnh. Danh sách có thể rỗng; thông tin discovery cũng có thể thay đổi giữa lúc tra cứu và lúc kết nối. Mã gọi thực tế vẫn cần xử lý timeout, lỗi kết nối và tình huống không có đích phục vụ.

Không nên giả định mọi implementation hoặc mọi chế độ discovery trả về cùng loại địa chỉ. Đích có thể liên quan đến địa chỉ Service hoặc các endpoint cụ thể tùy cách tích hợp và cấu hình. Khi một Service có nhiều cổng, việc chọn đúng cổng và giao thức cũng cần được cấu hình rõ ràng.

Phạm vi namespace là một phần của thiết kế. Cho phép khám phá tất cả namespace có thể làm tăng quyền truy cập và tạo nhầm lẫn khi nhiều namespace dùng cùng tên Service. Với hệ thống chỉ gọi nội bộ trong `shop`, hãy bắt đầu từ phạm vi đó.

### 2.3. Spring Cloud LoadBalancer chọn đích ở phía client

Spring Cloud LoadBalancer cung cấp cơ chế chọn instance ở phía ứng dụng. Khi kết hợp với nguồn instance phù hợp, nó có thể chọn đích cho một tên dịch vụ logic như `catalog-api`.

Cần phân biệt hai đường gọi:

```text
Gọi qua Service:
order-api -> DNS catalog-api -> Service -> endpoint đủ điều kiện

Gọi với cân bằng tải phía client theo endpoint:
order-api -> danh sách instance -> LoadBalancer chọn đích -> endpoint
```

Sơ đồ thứ hai mô tả trường hợp cấu hình cân bằng tải theo endpoint. Một cấu hình tích hợp khác có thể hướng client tới Service; khi đó Service vẫn tham gia đường đi. Không nên suy ra rằng cứ thêm Spring Cloud LoadBalancer là mọi cuộc gọi đều bỏ qua Service.

Một HTTP client thông thường chỉ thấy hostname trong URL. Để tên dịch vụ logic được xử lý bằng Spring Cloud LoadBalancer, client phải được tích hợp với LoadBalancer theo API mà phiên bản Spring đang dùng hỗ trợ. Chỉ thêm thư viện discovery hoặc chỉ viết URL mang tên Service chưa chứng minh rằng cân bằng tải phía client đã hoạt động.

Với nhiều ứng dụng, gọi qua Service đã đủ. Chỉ thêm cân bằng tải phía client khi có yêu cầu rõ về lựa chọn instance, metadata hoặc tích hợp với thành phần Spring Cloud khác. Cơ chế chọn đích không tự cung cấp timeout hợp lý, retry an toàn hay khả năng chống quá tải; các chính sách đó vẫn phải được thiết kế riêng.

## 3. Nhóm cấu hình

### 3.1. ConfigMap và Secret có mục đích khác nhau

ConfigMap phù hợp với các giá trị không nhạy cảm như giới hạn xử lý, cờ tính năng hoặc tên môi trường. Secret dùng cho dữ liệu nhạy cảm như mật khẩu hay token. Secret vẫn đòi hỏi kiểm soát quyền truy cập, bảo vệ dữ liệu lưu trữ và tránh đưa giá trị vào log; cách biểu diễn dữ liệu bằng Base64 không phải là mã hóa bảo mật.

Ví dụ ConfigMap cho `order-api`:


```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
  namespace: shop
data:
  ORDER_MAXITEMS: "20"
  ORDER_CATALOGTIMEOUT: "2s"
```

Các giá trị ở đây đều là chuỗi. Ứng dụng cần bind và kiểm tra chúng theo kiểu dữ liệu mong muốn, chẳng hạn số nguyên dương cho giới hạn mặt hàng và thời lượng hữu hạn cho timeout.

### 3.2. Hai cách đưa cấu hình vào ứng dụng

**Cách thứ nhất là để Kubernetes cung cấp cấu hình khi container chạy.** Ứng dụng đọc biến môi trường hoặc file đã mount bằng cơ chế cấu hình thông thường của Spring Boot. Cách này có thể đáp ứng nhu cầu mà không cần thành phần đọc ConfigMap qua Kubernetes API trong ứng dụng.

Đoạn dưới là phần cấu hình của một container trong Pod template, không phải manifest Deployment đầy đủ. Nó giả định ConfigMap `order-settings` và Secret `order-credentials` đã được tạo trong namespace của Pod:

```yaml
env:
  - name: ORDER_MAXITEMS
    valueFrom:
      configMapKeyRef:
        name: order-settings
        key: ORDER_MAXITEMS
  - name: ORDER_CATALOGTIMEOUT
    valueFrom:
      configMapKeyRef:
        name: order-settings
        key: ORDER_CATALOGTIMEOUT
  - name: ORDER_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: order-credentials
        key: api-token
```

Spring Boot có thể bind các biến môi trường theo quy tắc đặt tên của nó. Ví dụ lớp thuộc tính sau biểu diễn hai cấu hình không nhạy cảm:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "order")
public class OrderProperties {

    private int maxItems = 20;
    private Duration catalogTimeout = Duration.ofSeconds(2);

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }

    public Duration getCatalogTimeout() {
        return catalogTimeout;
    }

    public void setCatalogTimeout(Duration catalogTimeout) {
        this.catalogTimeout = catalogTimeout;
    }
}
```

Lớp cần được đăng ký, chẳng hạn bằng `@ConfigurationPropertiesScan` ở ứng dụng Spring Boot. Ví dụ chỉ minh họa binding ban đầu; việc có getter và setter không tự tạo khả năng refresh khi ConfigMap thay đổi. Trong ứng dụng thực tế, nên bổ sung kiểm tra giá trị để tránh chấp nhận giới hạn âm hoặc timeout không hợp lệ.

**Cách thứ hai là dùng tích hợp cấu hình của Spring Cloud Kubernetes.** Tích hợp phù hợp có thể đọc ConfigMap, và nếu được bật cùng quyền tương ứng thì cả Secret, để đưa dữ liệu vào Spring `Environment`. Ứng dụng có thể cần cấu hình nguồn, namespace, tên tài nguyên và cơ chế nạp cấu hình theo dòng phiên bản được sử dụng.

Hai cách không có cùng yêu cầu vận hành. Một tiến trình chỉ nhận biến môi trường không cần tự đọc Kubernetes API để lấy những giá trị đó. Một tiến trình dùng tích hợp đọc qua API cần danh tính, kết nối đến API server và quyền phù hợp. Không nên cấp quyền đọc Secret cho mọi ứng dụng chỉ vì một thành phần cấu hình có khả năng sử dụng Secret.

Tên starter, cơ chế nạp cấu hình và thuộc tính cấu hình cụ thể phụ thuộc tổ hợp Spring Boot, Spring Cloud và Spring Cloud Kubernetes. Bài tổng quan này xác định trách nhiệm và luồng dữ liệu; khi triển khai cần chọn tổ hợp tương thích trước khi viết cấu hình tích hợp chi tiết.

### 3.3. Thay đổi tài nguyên chưa đồng nghĩa ứng dụng đã đổi hành vi

Có ít nhất ba mốc cần phân biệt:

1. Giá trị mới đã được lưu trong ConfigMap hoặc Secret.
2. Giá trị mới đã đến nguồn cấu hình mà tiến trình có thể đọc.
3. Thành phần đang xử lý yêu cầu đã sử dụng giá trị mới.

Với biến môi trường, container đang chạy không tự nhận giá trị mới khi ConfigMap hoặc Secret thay đổi. Cần tạo lại Pod để tiến trình khởi động với môi trường mới.

Với file từ volume, Kubernetes có thể cập nhật nội dung sau một khoảng thời gian, nhưng ứng dụng vẫn phải đọc lại hoặc có cơ chế reload phù hợp. Mount qua `subPath` có giới hạn cập nhật riêng và không nên được chọn với giả định rằng file sẽ tự theo dõi thay đổi. Việc file đổi không buộc một bean Spring đã khởi tạo phải thay đổi.

Với cấu hình đọc qua API, cần xác định rõ thời điểm đọc và cơ chế phản ứng với thay đổi. Một HTTP client đã được tạo với timeout cũ có thể tiếp tục dùng timeout đó nếu không được tái cấu hình hoặc tái tạo theo thiết kế.

### 3.4. Configuration Watcher nối sự kiện thay đổi với hành động cập nhật

Configuration Watcher là một lựa chọn để theo dõi thay đổi cấu hình Kubernetes và kích hoạt cơ chế cập nhật cho ứng dụng được cấu hình tham gia. Đây là thành phần cần triển khai và thiết lập phù hợp; chỉ thêm ConfigMap không tạo ra luồng refresh hoàn chỉnh.

Một luồng khái niệm là:

```text
ConfigMap thay đổi
        |
        v
Watcher nhận sự kiện trong phạm vi được cấp quyền
        |
        v
Xác định ứng dụng đích theo cấu hình theo dõi
        |
        v
Gửi tín hiệu cập nhật qua cơ chế đã tích hợp
        |
        v
Ứng dụng nạp lại cấu hình và cập nhật thành phần hỗ trợ refresh
```

Muốn luồng này hoạt động, cần trả lời được các câu hỏi cụ thể:

- Watcher đang theo dõi tài nguyên, nhãn và namespace nào?
- Watcher dùng ServiceAccount nào, và có quyền nhận sự kiện cần thiết không?
- Tín hiệu cập nhật đến từng bản sao ứng dụng bằng cách nào?
- Ứng dụng có bật cơ chế nhận tín hiệu và cho phép nguồn gọi tương ứng không?
- Những bean hoặc tài nguyên nào có thể thay đổi khi đang chạy?
- Quan sát bằng cách nào để biết tất cả replica đã dùng cấu hình mới?

Không nên hiểu “có Watcher” là mọi bean đều cập nhật tức thời. Một số thay đổi thích hợp với refresh; một số thay đổi, như việc khởi tạo lại tài nguyên phức tạp, có thể cần rollout. Các replica cũng có thể cập nhật lệch thời điểm, vì vậy cần tính đến khoảng chuyển tiếp khi thiết kế cờ tính năng hoặc tham số giao thức.

Nếu sử dụng endpoint quản trị để nhận refresh, phải giới hạn truy cập bằng xác thực và chính sách mạng phù hợp. Endpoint đó không nên trở thành một chức năng công khai cho người dùng cuối.

## 4. Nhóm điều phối và phối hợp vận hành

### 4.1. Kubernetes quản lý vòng đời workload

Trong Kubernetes, người triển khai khai báo trạng thái mong muốn, chẳng hạn ba replica của `order-api`. Controller liên tục đối chiếu trạng thái thực với trạng thái mong muốn. Bộ lập lịch chọn node cho Pod mới; kubelet trên node chạy container và thực hiện các probe đã cấu hình.

Spring Cloud Kubernetes có thể giúp ứng dụng tích hợp với môi trường đó, nhưng không chịu trách nhiệm thay thế Pod chết hoặc quyết định node chạy Pod.

Với ba replica, các trách nhiệm vận hành thường gồm:

| Trách nhiệm | Thành phần chủ yếu |
| --- | --- |
| Duy trì số lượng replica | Deployment và ReplicaSet controller |
| Chọn node cho Pod | Kubernetes scheduler |
| Quyết định container có cần khởi động lại theo probe hay không | Kubelet và cấu hình liveness/startup probe |
| Xác định Pod đã sẵn sàng nhận lưu lượng | Readiness probe và trạng thái readiness |
| Cập nhật endpoint để phục vụ định tuyến | Cơ chế Service và controller quản lý endpoint |
| Cung cấp trạng thái sức khỏe ở tầng ứng dụng | Ứng dụng Spring, thường qua endpoint sức khỏe được cấu hình |

Spring Boot Actuator có thể cung cấp endpoint sức khỏe cho probe khi ứng dụng bật và cấu hình phù hợp. Chỉ có endpoint không làm Kubernetes tự sử dụng nó; manifest phải khai báo probe và bảo đảm đường dẫn, cổng, thời gian chờ khớp với ứng dụng.

### 4.2. Readiness, liveness và startup phục vụ các quyết định khác nhau

**Readiness** trả lời “Pod này đã sẵn sàng phục vụ chưa?”. Với Service thông thường, Pod không ready sẽ không được chọn như một endpoint phục vụ bình thường. Những cấu hình như công bố địa chỉ chưa ready có thể thay đổi hành vi đó.

**Liveness** trả lời “container có đang ở trạng thái cần khởi động lại không?”. Đặt phụ thuộc dùng chung, như cơ sở dữ liệu, vào điều kiện liveness một cách máy móc có thể khiến toàn bộ replica liên tục khởi động lại khi phụ thuộc đó gián đoạn.

**Startup probe** dành thời gian cho ứng dụng khởi động trước khi các kiểm tra liveness và readiness bắt đầu có hiệu lực theo cơ chế probe của Kubernetes. Nó hữu ích khi ứng dụng khởi động lâu nhưng không nên bị coi là treo ngay từ đầu.

Đối với `order-api`, việc `catalog-api` tạm thời không truy cập được cần được đánh giá theo yêu cầu nghiệp vụ. Nếu ứng dụng vẫn phục vụ được một số API, loại toàn bộ Pod khỏi lưu lượng có thể làm giảm khả năng phục vụ không cần thiết. Quyết định probe phải phản ánh khả năng của ứng dụng, không chỉ phản ánh việc có cài thư viện khám phá hay không.

### 4.3. Phối hợp giữa replica khác với điều phối Pod

Có những công việc ứng dụng chỉ muốn một bản sao thực hiện tại một thời điểm, ví dụ quét và tổng hợp dữ liệu theo lịch. Nhiều replica cùng chạy một phương thức theo lịch không tự biến thành một tác vụ duy nhất trong cluster.

Tùy phiên bản và giải pháp được lựa chọn, có thể dùng cơ chế phối hợp như bầu leader, khóa phân tán hoặc tách công việc sang Kubernetes Job/CronJob. Cần xác định rõ ai sở hữu công việc, cách chuyển quyền khi leader mất kết nối và cách ngăn kết quả trùng lặp.

Bầu leader không bảo đảm tác vụ được thực hiện chính xác một lần. Khi có gián đoạn hoặc chuyển leader, hai tiến trình có thể có những quan sát khác nhau trong một khoảng thời gian. Tác vụ quan trọng vẫn cần idempotency, ràng buộc dữ liệu hoặc cơ chế kiểm soát ghi phù hợp.

Nếu nhu cầu chỉ là chạy một công việc độc lập theo lịch, Job/CronJob có thể là điểm bắt đầu dễ vận hành hơn việc nhúng phối hợp leader vào mọi replica của dịch vụ web.

## 5. RBAC là điều kiện cho các tích hợp truy cập API

Một ứng dụng gọi `http://catalog-api:8080` qua Service không có cùng nhu cầu quyền với một ứng dụng truy vấn danh sách Service hoặc theo dõi ConfigMap qua Kubernetes API.

Trong cluster, tiến trình thường dùng danh tính ServiceAccount được cấp cho Pod. RBAC xác định danh tính đó được thực hiện thao tác nào trên tài nguyên nào và trong namespace nào.

Ví dụ sau chỉ minh họa quyền đọc một ConfigMap đã biết tên trong `shop`. Namespace và ConfigMap được giả định đã tồn tại:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-api
  namespace: shop
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-settings-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["order-settings"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-settings-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-api
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-settings-reader
```

Pod template của ứng dụng cần khai báo `serviceAccountName: order-api` để sử dụng danh tính này. RoleBinding chỉ liên kết quyền với danh tính, không tự chọn danh tính cho Pod.

Ví dụ trên **không phải bộ quyền đầy đủ cho mọi tính năng Spring Cloud Kubernetes**. Một client đọc ConfigMap theo tên bằng `get` có thể phù hợp với quyền đó. Một cơ chế discovery hoặc theo dõi thay đổi có thể cần `list`, `watch` và quyền trên những loại tài nguyên khác. Chính xác cần Service, Endpoints, EndpointSlice hay tài nguyên nào phải được xác định theo implementation và cách cấu hình thực tế.

Không nên thêm `list/watch` vào Role có `resourceNames` rồi mặc định rằng mọi client đều dùng được: các yêu cầu liệt kê hoặc theo dõi bị giới hạn theo tên còn phụ thuộc cách client tạo yêu cầu. Quyền của ứng dụng và quyền của Watcher nên được thiết kế theo từng trách nhiệm.

Lỗi `403 Forbidden` khi gọi Kubernetes API thường hướng việc kiểm tra đến danh tính và RBAC. Lỗi timeout khi gọi HTTP tới `catalog-api` cần kiểm tra thêm Service, endpoint, readiness, NetworkPolicy và khả năng phục vụ của ứng dụng đích. Hai loại lỗi nằm ở những luồng khác nhau.

## 6. Chọn chức năng theo nhu cầu thực tế

Với hệ thống bán hàng đang xét, có thể bắt đầu bằng một triển khai đơn giản: `order-api` gọi `catalog-api` qua Service, nhận cấu hình lúc khởi động và nhận cấu hình mới qua một rollout có kiểm soát. Sau đó bổ sung tích hợp khi xuất hiện yêu cầu cụ thể.

| Nhu cầu | Lựa chọn khởi đầu | Khi nào cân nhắc bổ sung |
| --- | --- | --- |
| Gọi một dịch vụ nội bộ có tên ổn định | DNS và Service của Kubernetes | Thêm `DiscoveryClient` nếu cần abstraction khám phá hoặc tích hợp Spring Cloud dựa trên discovery |
| Chọn instance theo thông tin ở tầng ứng dụng | Làm rõ Service hiện tại đã đáp ứng đến đâu | Dùng Spring Cloud LoadBalancer với nguồn instance và client được tích hợp phù hợp |
| Đọc cấu hình khi khởi động | Biến môi trường hoặc file được cung cấp cho Pod | Dùng tích hợp cấu hình qua API khi cần đưa nguồn Kubernetes trực tiếp vào `Environment` theo thiết kế đó |
| Áp dụng thay đổi cấu hình trong lúc chạy | Xác định rõ cấu hình có hỗ trợ đổi động không | Cân nhắc Configuration Watcher và refresh, hoặc rollout nếu việc khởi tạo lại phù hợp hơn |
| Duy trì số replica và thay thế Pod lỗi | Deployment, probe và controller của Kubernetes | Không cần thêm Spring Cloud Kubernetes chỉ cho mục tiêu này |
| Chỉ một replica xử lý công việc chung | Chọn Job/CronJob hoặc cơ chế phối hợp phù hợp | Bổ sung leader election hay khóa nếu mô hình ứng dụng đòi hỏi, kèm kiểm soát xử lý trùng |

Mỗi tích hợp truy cập Kubernetes API làm phát sinh trách nhiệm về quyền, phạm vi tài nguyên, khả năng kết nối và quan sát lỗi. Mỗi cơ chế refresh làm phát sinh trách nhiệm về trạng thái ứng dụng trong lúc chuyển đổi. Giá trị của tích hợp nằm ở việc giải quyết đúng nhu cầu, không nằm ở số lượng starter được thêm vào dự án.

## 7. Đi qua một tình huống vận hành

Giả sử hệ thống có hai replica `order-api`, ba replica `catalog-api`, một ConfigMap `order-settings` và một Secret `order-credentials`.

**Khi một Pod `catalog-api` được thay thế**, Deployment duy trì số replica, Pod mới trải qua quá trình khởi động và readiness, còn tập endpoint phục vụ được cập nhật. Nếu `order-api` gọi qua Service, nó tiếp tục dùng tên Service ổn định. Nếu gọi trực tiếp theo danh sách instance, thông tin khám phá có thể có độ trễ và client vẫn phải xử lý lỗi khi kết nối tới một đích vừa biến mất.

**Khi tăng `ORDER_MAXITEMS` từ `20` lên `30`**, cần xác định cách cấp cấu hình. Nếu giá trị đến từ biến môi trường, các Pod đang chạy vẫn giữ giá trị cũ cho đến khi được tạo lại. Nếu dùng nguồn cấu hình hỗ trợ refresh và Watcher đã được thiết lập, cần quan sát việc nhận sự kiện, gửi tín hiệu và cập nhật giá trị trên cả hai replica. Không thể kết luận thành công chỉ từ việc nhìn thấy ConfigMap đã đổi.

**Khi Watcher bị từ chối quyền truy cập**, hãy kiểm tra ServiceAccount của chính Watcher, namespace theo dõi và thao tác bị từ chối. Không mở rộng quyền của `order-api` nếu thành phần lỗi là Watcher. Tách danh tính giúp chẩn đoán rõ trách nhiệm và giới hạn phạm vi quyền.

**Khi `order-api` phản hồi chậm**, kiểm tra khả năng xử lý, timeout tới `catalog-api`, trạng thái endpoint và probe. DiscoveryClient cho biết thông tin đích; nó không sửa được truy vấn chậm, thread bị chặn hay thiết kế retry làm tăng tải.

## 8. Tự kiểm tra sau bài học

1. Nếu `order-api` chỉ gọi một Service cùng namespace qua HTTP, tại sao ứng dụng có thể không cần `DiscoveryClient`?
2. Trong triển khai của bạn, LoadBalancer chọn endpoint cụ thể hay chọn địa chỉ Service? Thành phần nào tiếp tục xử lý lưu lượng sau lựa chọn đó?
3. Sau khi đổi ConfigMap, bằng chứng nào cho thấy hành vi trên từng replica đã sử dụng giá trị mới?
4. Quyền đọc cấu hình thuộc ServiceAccount của ứng dụng hay của Watcher? Có thành phần nào thực sự cần đọc Secret không?
5. Khi một Pod không ready, điều gì xảy ra với lưu lượng qua Service? Điều đó khác gì với liveness thất bại?
6. Khi một công việc phải có một người thực hiện trong nhiều replica, điều phối Pod có tự bảo đảm công việc không chạy trùng không?

Nắm được các ranh giới này giúp chọn đúng phần tích hợp: dùng Kubernetes cho địa chỉ dịch vụ ổn định, cấp cấu hình và điều phối workload; dùng Spring Cloud Kubernetes khi ứng dụng cần kết nối các khả năng đó với mô hình Spring Cloud, đồng thời thiết kế rõ quyền truy cập, cập nhật cấu hình và quan sát sức khỏe Pod.