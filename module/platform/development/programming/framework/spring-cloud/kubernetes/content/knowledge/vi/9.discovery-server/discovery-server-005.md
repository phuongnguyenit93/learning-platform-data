# Vai trò của HTTP client trong lấy danh sách dịch vụ

## Mục tiêu và bối cảnh

Trong chương **Discovery Server** của module **SPRING_CLOUD_KUBERNETES**, HTTP client là thành phần giúp ứng dụng lấy thông tin discovery qua một giao diện HTTP trung gian. Ứng dụng sử dụng dữ liệu đó để biết có những dịch vụ nào và mỗi dịch vụ có các instance nào.

Bài học tập trung vào luồng lấy danh mục, cách tích hợp với `DiscoveryClient` của Spring và những điều phải kiểm tra trước khi dùng kết quả. Ví dụ dùng:

- `order-service`: ứng dụng Spring Boot cần tra cứu dịch vụ.
- `kubernetes-discovery`: Kubernetes Service đưa request tới Discovery Server trong namespace `platform`.
- `catalog-api`: dịch vụ nghiệp vụ trong namespace `demo`, có hai instance HTTP trên cổng `8080`.

Các tên, IP và kết quả dưới đây là dữ liệu minh họa. Giả định những thành phần này đã được triển khai và có kết nối mạng phù hợp; bài không yêu cầu dựng toàn bộ cụm.

## 1. HTTP client đứng ở đâu trong kiến trúc?

Có ba vai trò dễ bị gọi chung là “client”:

| Thành phần | Trách nhiệm |
| --- | --- |
| HTTP client ở tầng vận chuyển | Gửi request, nhận status/header/body, quản lý kết nối và lỗi truyền tải |
| HTTP DiscoveryClient trong ứng dụng | Dùng giao tiếp HTTP với Discovery Server và cung cấp giao diện discovery của Spring |
| Kubernetes client phía Discovery Server | Đọc tài nguyên Kubernetes để hình thành thông tin dịch vụ và endpoint |

Ứng dụng nghiệp vụ có thể tiếp tục lập trình theo giao diện `DiscoveryClient`. Cách lấy dữ liệu bên dưới là HTTP thay vì mỗi ứng dụng trực tiếp giữ một Kubernetes client để đọc API.

~~~mermaid
sequenceDiagram
    participant App as order-service
    participant DC as HTTP DiscoveryClient
    participant Server as Discovery Server
    participant K8s as Kubernetes API
    App->>DC: getServices()
    DC->>Server: GET /apps
    Note over Server,K8s: Server đọc/theo dõi tài nguyên theo cấu hình
    Server->>K8s: Truy cập API bằng danh tính của server
    K8s-->>Server: Dữ liệu Service và endpoint
    Server-->>DC: JSON danh mục dịch vụ
    DC-->>App: List<String>
    App->>DC: getInstances("catalog-api")
    DC->>Server: GET /apps/catalog-api
    Server-->>DC: JSON các instance
    DC-->>App: List<ServiceInstance>
~~~

Sơ đồ diễn tả trách nhiệm và luồng dữ liệu, không cam kết mỗi request HTTP tới server đều tạo một request mới tới Kubernetes API. Server có thể trả lời từ dữ liệu đã được đồng bộ; client hoặc các lớp tích hợp cũng có thể có cache.

Spring Cloud Kubernetes cung cấp starter `spring-cloud-starter-kubernetes-discoveryclient` cho cách discovery qua HTTP với Discovery Server. Hai lựa chọn Fabric8 và Kubernetes Java Client phục vụ cách đọc Kubernetes theo triển khai tương ứng. [Tài liệu Kubernetes DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)

**HTTP client giúp lấy thông tin về đích; nó không tự thực hiện toàn bộ lời gọi nghiệp vụ tới đích đó.**

## 2. Hai câu hỏi khác nhau: có dịch vụ nào và có instance nào?

Giao diện Spring cần được đọc theo đúng mức dữ liệu:

~~~java
List<String> serviceIds = discoveryClient.getServices();

List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-api");
~~~

`getServices()` trả về danh sách tên dịch vụ, chẳng hạn:

~~~json
["catalog-api", "payment-api"]
~~~

`getInstances("catalog-api")` trả về những đối tượng mô tả đích cụ thể, chẳng hạn:

~~~text
serviceId    host          port
catalog-api  10.42.1.21    8080
catalog-api  10.42.2.35    8080
~~~

Tên dịch vụ không mang ý nghĩa “chắc chắn có instance dùng được ngay”. Service có thể tồn tại trong Kubernetes trong khi backend chưa sẵn sàng hoặc đang được thay thế.

Cũng không nên lấy `getServices().size()` để suy ra số Pod. Hai dịch vụ có thể có số replica rất khác nhau; một dịch vụ có thể có nhiều instance.

Với phạm vi nhiều namespace, tên Service có thể trùng. Khi cần phân biệt đích, phải xem phạm vi discovery và dữ liệu namespace liên quan, thay vì giả định một tên ngắn là duy nhất trên toàn cụm.

## 3. HTTP API mang dữ liệu gì?

Discovery Server công bố các endpoint HTTP để truy vấn danh mục và instance. Hình dạng dữ liệu trên đường truyền không giống hoàn toàn kiểu trả về của `DiscoveryClient` trong ứng dụng. [API của Discovery Server](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html#_endpoints)

### 3.1. GET /apps: danh mục và dữ liệu instance theo dịch vụ

Ví dụ phản hồi được rút gọn về một dịch vụ:

~~~json
[
  {
    "name": "catalog-api",
    "serviceInstances": [
      {
        "instanceId": "catalog-instance-a",
        "serviceId": "catalog-api",
        "host": "10.42.1.21",
        "port": 8080,
        "uri": "http://10.42.1.21:8080",
        "secure": false,
        "metadata": {
          "app": "catalog-api"
        },
        "namespace": "demo",
        "scheme": "http"
      },
      {
        "instanceId": "catalog-instance-b",
        "serviceId": "catalog-api",
        "host": "10.42.2.35",
        "port": 8080,
        "uri": "http://10.42.2.35:8080",
        "secure": false,
        "metadata": {
          "app": "catalog-api"
        },
        "namespace": "demo",
        "scheme": "http"
      }
    ]
  }
]
~~~

Đây là mảng đối tượng, mỗi đối tượng có `name` và `serviceInstances`. Không được giải mã trực tiếp body này thành `List<String>` chỉ vì phương thức `getServices()` trả về `List<String>`.

Lớp adapter của discovery chịu trách nhiệm cung cấp dữ liệu theo giao diện Spring. Nếu tự viết công cụ HTTP, bạn phải hiểu schema phản hồi và tự trích xuất tên khi cần.

### 3.2. GET /apps/{name}: các instance của một dịch vụ

~~~http
GET /apps/catalog-api HTTP/1.1
Host: kubernetes-discovery.platform.svc.cluster.local
Accept: application/json
~~~

Body là mảng mô tả instance, không còn lớp bọc `name` và `serviceInstances` của toàn danh mục:

~~~json
[
  {
    "instanceId": "catalog-instance-a",
    "serviceId": "catalog-api",
    "host": "10.42.1.21",
    "port": 8080,
    "uri": "http://10.42.1.21:8080",
    "secure": false,
    "metadata": {},
    "namespace": "demo",
    "scheme": "http"
  }
]
~~~

Mảng một phần tử này chỉ minh họa schema. Số phần tử thực tế phụ thuộc dữ liệu mà server đang nhìn thấy và chính sách discovery.

### 3.3. GET /app/{name}/{instanceid}: một instance cụ thể

Endpoint tra một instance dùng đường dẫn `/app` số ít:

~~~text
/app/catalog-api/catalog-instance-a
~~~

Không suy đoán đường dẫn từ việc thêm hoặc bỏ chữ `s`. Với ứng dụng Spring thông thường, nên dùng giao diện discovery mà starter cung cấp; endpoint tra một instance có ích khi khảo sát API hoặc chẩn đoán.

`instanceId` trong ví dụ là định danh minh họa. Không tự suy ra giá trị đó từ tên Pod hay IP nếu chưa biết triển khai đang sinh định danh như thế nào.

## 4. HTTP client phải làm những việc nào?

Để biến một URL thành danh sách dùng được, tầng client phải đi qua nhiều bước:

1. **Xác định URL server:** có scheme, host, cổng và đường dẫn phù hợp.
2. **Thiết lập đường truyền:** phân giải tên, mở kết nối và thực hiện TLS nếu dùng HTTPS.
3. **Gửi HTTP request:** chọn method, đường dẫn và các header cần thiết.
4. **Kiểm tra kết quả HTTP:** phân biệt thành công với lỗi xác thực, lỗi đường dẫn hoặc lỗi phía server.
5. **Giải mã body:** đọc JSON theo schema mà server thực sự trả về.
6. **Chuyển thành dữ liệu discovery:** cung cấp tên dịch vụ hoặc đối tượng `ServiceInstance` cho ứng dụng.
7. **Bộc lộ lỗi và thông tin quan sát:** để ứng dụng biết request thất bại hoặc dữ liệu không giải mã được.

Starter thực hiện việc tích hợp theo thư viện và phiên bản tương ứng. Danh sách trên mô tả trách nhiệm cần có, không có nghĩa người dùng phải tự viết lại từng bước.

Một phản hồi HTTP 200 chưa đủ chứng minh danh sách đúng. Ví dụ reverse proxy có thể trả về trang HTML đăng nhập với status 200; client cần phát hiện body không phải schema JSON mong đợi.

Ngược lại, nhận được một JSON hợp lệ cũng chưa chứng minh tất cả instance đều đang nhận request thành công. Discovery mô tả đích theo dữ liệu hiện có; khả năng gọi đích còn phụ thuộc mạng, cổng, TLS và trạng thái ứng dụng.

## 5. Tích hợp HTTP DiscoveryClient trong ứng dụng Spring

### 5.1. Dependency

Trong dự án đã quản lý bộ phiên bản Spring Boot/Spring Cloud tương thích, thêm starter HTTP discovery:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-discoveryclient</artifactId>
</dependency>
~~~

Ví dụ controller bên dưới dùng Spring MVC, nên ứng dụng cũng cần web starter nếu chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Version của dependency cần do bộ quản lý phiên bản dự án cung cấp; không chọn ngẫu nhiên một tag server và một phiên bản client khác dòng. Khi nâng cấp, kiểm tra tính tương thích của cả hai phía HTTP và các tính năng đang dùng.

Không thêm đồng thời nhiều starter discovery chỉ để “chắc chắn có client”. Nếu classpath có nhiều triển khai, hãy xác minh bean hoặc lớp tổng hợp nào thực sự xử lý lời gọi.

### 5.2. URL bootstrap của Discovery Server

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    kubernetes:
      discovery:
        enabled: true
        discovery-server-url: http://kubernetes-discovery.platform.svc.cluster.local:80
~~~

`spring.cloud.kubernetes.discovery.discovery-server-url` là thuộc tính URL của Discovery Server. [Danh mục thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html)

Trong ví dụ:

- `kubernetes-discovery` là tên Kubernetes Service dẫn tới Discovery Server.
- `platform` là namespace của server.
- `80` là cổng Service mà client gọi.
- `demo` là namespace dữ liệu nghiệp vụ server sẽ khám phá; nó không xuất hiện trong URL bootstrap này.

Cổng Service có thể là `80` trong khi container server nghe `8761`. HTTP client phải dùng cổng ở điểm truy cập mà nó kết nối, không tự lấy cổng container thay vào URL.

Tên DNS trên dành cho ngữ cảnh mạng trong cụm và giả định miền `cluster.local`. Nếu chạy ứng dụng bên ngoài cụm, cần một địa chỉ truy cập thích hợp. Ngoài ra, truy cập được Discovery Server chưa đồng nghĩa truy cập được các PodIP mà server trả về.

URL bootstrap cần tìm được bằng một cơ chế sẵn có như DNS hoặc cấu hình. Không thiết kế đường lấy địa chỉ Discovery Server lại phụ thuộc chính danh mục chưa tải được từ server.

### 5.3. Lớp khởi động

~~~java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootApplication
@EnableDiscoveryClient
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Ví dụ giả định ứng dụng chạy trong môi trường kích hoạt cấu hình Kubernetes phù hợp với bộ phiên bản đang dùng. Nếu bean discovery không được tạo, kiểm tra dependency, điều kiện auto-configuration và môi trường thay vì thêm một URL vào mọi nhóm thuộc tính có chữ “client”.

### 5.4. Quan sát dữ liệu qua giao diện Spring

~~~java
package example.discovery;

import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiscoveryInspectionController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryInspectionController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/internal/discovery/services")
    public List<String> services() {
        return discoveryClient.getServices();
    }

    @GetMapping("/internal/discovery/instances/{serviceId}")
    public List<InstanceView> instances(
            @PathVariable("serviceId") String serviceId) {

        return discoveryClient.getInstances(serviceId).stream()
                .map(this::toView)
                .toList();
    }

    private InstanceView toView(ServiceInstance instance) {
        return new InstanceView(
                instance.getInstanceId(),
                instance.getServiceId(),
                instance.getHost(),
                instance.getPort(),
                instance.getUri().toString());
    }

    public record InstanceView(
            String instanceId,
            String serviceId,
            String host,
            int port,
            String uri) {
    }
}
~~~

Đoạn mã dùng Java 17. Nó gọi `DiscoveryClient`, không tự xử lý JSON của `/apps`. Chỉ cho phép truy cập các endpoint quan sát này trong phạm vi môi trường thực hành hoặc nơi đã có kiểm soát truy cập phù hợp.

Đây là ví dụ đồng bộ cho Spring MVC. Nếu xây ứng dụng reactive, chọn giao diện và cách thực thi phù hợp; không chặn event loop bằng lời gọi discovery đồng bộ.

## 6. Cấu hình nào thuộc server, cấu hình nào thuộc client?

Một URL đúng không quyết định server được phép nhìn thấy dữ liệu nào.

| Vấn đề | Nơi xử lý chính |
| --- | --- |
| Ứng dụng gọi Discovery Server ở đâu | Cấu hình URL phía ứng dụng HTTP client |
| Server đọc namespace nào | Cấu hình discovery phía Discovery Server |
| Server được phép đọc tài nguyên nào | ServiceAccount và RBAC của Discovery Server |
| Có đưa endpoint chưa ready vào danh sách không | Chính sách discovery tại thành phần đọc dữ liệu Kubernetes |
| Client tới server được không | DNS, mạng, cổng, TLS và cơ chế truy cập HTTP |
| Ứng dụng gọi được instance không | Đường mạng và giao thức từ ứng dụng tới đích |

Ví dụ phần biến môi trường đặt trong container **Discovery Server** để giới hạn namespace:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_ALL_NAMESPACES
    value: "false"
  - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACES_0
    value: "demo"
~~~

Đây là một đoạn cấu hình container, không phải manifest triển khai hoàn chỉnh. Phạm vi namespace của HTTP discovery cần được thiết lập ở server, nơi đọc Kubernetes API. [Cấu hình phạm vi Kubernetes DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)

Server cũng cần RBAC phù hợp trong namespace được đọc. Nếu server chạy ở `platform` nhưng đọc dữ liệu `demo`, việc gán quyền chỉ trong `platform` không tự cho nó quyền đọc `demo`.

Ứng dụng chỉ sử dụng HTTP discovery không cần quyền Kubernetes API chỉ cho thao tác này. Điều đó không miễn quyền cho các chức năng khác nếu ứng dụng còn trực tiếp đọc ConfigMap hoặc Secret.

Quyền Kubernetes API của server và quyền gọi HTTP tới server là hai lớp khác nhau. RBAC không tự trở thành cơ chế xác thực cho endpoint `/apps`. Cần giới hạn truy cập danh mục theo mô hình triển khai, nhất là khi phản hồi chứa IP nội bộ và metadata.

## 7. Sau khi có danh sách, ai chọn instance và ai gửi request nghiệp vụ?

Giả sử HTTP DiscoveryClient đã trả về:

~~~text
catalog-api -> [
    http://10.42.1.21:8080,
    http://10.42.2.35:8080
]
~~~

Đến đây, việc lấy thông tin discovery đã cung cấp các ứng viên. Để gọi một API, còn cần:

~~~text
danh sách ứng viên
    -> chọn một instance
    -> xây hoặc điều chỉnh URI nghiệp vụ
    -> gửi request bằng HTTP client nghiệp vụ
    -> xử lý phản hồi nghiệp vụ
~~~

Spring Cloud LoadBalancer có thể tham gia lựa chọn instance khi được tích hợp và cấu hình tương ứng. Việc inject `DiscoveryClient` rồi đọc danh sách không tự tạo một HTTP client đã bật load balancing.

Cũng cần phân biệt hai kết nối độc lập:

~~~text
Kết nối discovery:
order-service -> kubernetes-discovery:80 -> GET /apps/catalog-api

Kết nối nghiệp vụ:
order-service -> 10.42.1.21:8080 -> GET /products/42
~~~

Discovery Server không mặc nhiên đứng giữa và chuyển tiếp `GET /products/42`. Vì vậy, cấu hình proxy cho đường discovery không tự giải quyết khả năng truy cập PodIP ở đường nghiệp vụ.

Tương tự, server trả một URI `http://...` không có nghĩa mọi đường gọi đều nên bỏ TLS. Scheme và cổng phải phù hợp với giao thức thực tế của instance.

## 8. Timeout, lỗi và dữ liệu cũ phải được xử lý rõ ràng

### 8.1. Giới hạn thời gian chờ

HTTP discovery là phụ thuộc qua mạng. Nếu không giới hạn thời gian chờ, lỗi server hoặc đường truyền có thể làm các request ứng dụng chờ lâu.

Khi cấu hình transport mà phiên bản starter thực sự sử dụng, xem xét:

| Giới hạn | Mục đích |
| --- | --- |
| Thời gian thiết lập kết nối | Tránh chờ quá lâu khi không tới được server |
| Thời gian chờ phản hồi | Giới hạn thời gian server hoặc đường truyền giữ request |
| Ngân sách tổng cho thao tác | Kiểm soát cả nhiều lần thử và thời gian chờ giữa các lần |
| Giới hạn kết nối và hàng đợi | Tránh nhiều request discovery làm cạn tài nguyên client |

Tên thuộc tính và điểm tùy biến phụ thuộc HTTP transport, starter và phiên bản. Không mặc nhiên dùng timeout của Kubernetes client phía server để điều khiển kết nối HTTP phía ứng dụng: đó là hai đoạn đường truyền khác nhau.

### 8.2. Không biến mọi lỗi thành “không có dịch vụ”

Phải phân biệt:

~~~text
A. Server phản hồi thành công và danh sách thật sự rỗng
B. Request không tới được server
C. Server báo lỗi HTTP
D. Body không giải mã được theo schema
E. Ứng dụng đang dùng bản dữ liệu cũ theo chính sách cache
~~~

Nếu tự viết lớp bọc như sau, lỗi vận hành bị che khuất:

~~~java
try {
    return loadCatalog();
} catch (Exception error) {
    return List.of();
}
~~~

Đoạn trên là phản ví dụ về xử lý lỗi, không phải mã cần thêm vào ứng dụng. Khi mọi trường hợp trở thành `[]`, người vận hành không biết cụm thật sự trống hay discovery đã mất kết nối.

Hành vi cụ thể của starter khi lỗi cần được xác nhận với phiên bản sử dụng. Thiết kế quan sát nên giữ được nguyên nhân lỗi và phân biệt dữ liệu lấy mới với dữ liệu dự phòng.

### 8.3. Retry có giới hạn

Các request đọc danh mục phù hợp hơn với việc thử lại có kiểm soát khi xảy ra lỗi tạm thời, nhưng retry không nên chạy vô hạn hoặc áp dụng như nhau cho mọi lỗi.

Ví dụ, lỗi kết nối ngắn hạn có thể phục hồi; URL sai dẫn đến 404 cần sửa cấu hình. Nếu server dùng xác thực HTTP và trả 401/403, tăng số lần thử không thay thế được việc sửa danh tính hoặc quyền truy cập.

Tổng thời gian các lần thử phải nằm trong ngân sách của thao tác. Nếu nhiều ứng dụng cùng retry ngay khi server chậm, tải tăng có thể làm server khó phục hồi hơn.

### 8.4. Cache và tính cập nhật

Dữ liệu đi qua nhiều bước cập nhật:

~~~text
trạng thái Kubernetes
    -> dữ liệu mà server đã đồng bộ
    -> phản hồi HTTP
    -> cache phía client hoặc thành phần dùng discovery, nếu có
    -> danh sách dùng để chọn đích
~~~

Không suy ra mỗi lần gọi `getServices()` đều bảo đảm một bản chụp mới nhất của toàn cụm. Cũng không suy ra HTTP client mặc nhiên có một cache với TTL cố định.

Nếu chọn dùng dữ liệu cũ khi discovery lỗi, phải có giới hạn tuổi dữ liệu và cách quan sát. Một Pod đã bị xóa có thể vẫn còn trong bản cache cũ; danh sách không rỗng không đồng nghĩa các địa chỉ còn dùng được.

## 9. Quan sát và kiểm chứng theo từng chặng

Các thao tác dưới đây dành cho môi trường thực hành đã triển khai các thành phần trong ví dụ.

### Bước 1: Gọi trực tiếp HTTP endpoint của server

Từ nơi có DNS và đường mạng phù hợp:

~~~sh
curl -i --connect-timeout 2 --max-time 5 \
  http://kubernetes-discovery.platform.svc.cluster.local:80/apps

curl -i --connect-timeout 2 --max-time 5 \
  http://kubernetes-discovery.platform.svc.cluster.local:80/apps/catalog-api
~~~

Các giá trị thời gian là lựa chọn minh họa cho lệnh kiểm tra, không phải mặc định của starter. Với PowerShell, có thể dùng `curl.exe` và đặt mỗi lệnh trên một dòng; cú pháp xuống dòng bằng dấu `\` ở trên dành cho shell kiểu POSIX.

Kiểm tra cả HTTP status, content type và cấu trúc body. Body `/apps` phải được đọc theo danh mục gồm `name` và `serviceInstances`, trong khi `/apps/catalog-api` trả về danh sách instance.

### Bước 2: Gọi endpoint quan sát của ứng dụng

~~~text
GET /internal/discovery/services
GET /internal/discovery/instances/catalog-api
~~~

Nếu gọi trực tiếp server thành công nhưng ứng dụng thất bại, tập trung vào URL thực tế đã bind, bean discovery đang được dùng, TLS/proxy phía ứng dụng, lỗi giải mã và cache.

Nếu ứng dụng trả danh sách khác server, ghi thời điểm lấy cả hai kết quả và kiểm tra các lớp trung gian. Không kết luận dữ liệu sai chỉ từ hai lần đọc cách nhau trong lúc Pod đang thay đổi.

### Bước 3: Kiểm tra dữ liệu đầu vào của server

Người có quyền vận hành kiểm tra namespace, selector, endpoint và log của server. Nếu thấy lỗi `Forbidden` từ Kubernetes API trong log server, xử lý quyền của ServiceAccount server với tài nguyên đó.

Một HTTP client nhận lỗi không có nghĩa ServiceAccount của ứng dụng thiếu quyền đọc Kubernetes. Xác định request lỗi ở chặng **ứng dụng → server** hay **server → Kubernetes API** trước khi sửa RBAC.

### Bước 4: Kiểm tra khả năng gọi instance

Từ chính môi trường của `order-service`, thử đích và cổng mà discovery trả về bằng một endpoint nghiệp vụ đã biết. Nếu việc lấy danh mục thành công mà kết nối tới instance thất bại, tiếp tục điều tra đường nghiệp vụ.

Tình huống điển hình: laptop gọi được Discovery Server qua một địa chỉ được công bố, nhận về `10.42.1.21:8080`, nhưng mạng laptop không có route tới PodIP đó. HTTP discovery vẫn có thể hoạt động đúng; cần giải quyết cách truy cập đích phù hợp với kiến trúc.

### Bước 5: Quan sát thay đổi và sự cố có kiểm soát

Trong môi trường thử nghiệm, quan sát khi một instance không còn đủ điều kiện discovery hoặc khi Discovery Server tạm không truy cập được.

Ghi lại kết quả request, độ trễ, số instance và thời điểm dữ liệu thay đổi. Xác nhận ứng dụng phân biệt được lỗi lấy danh mục với danh mục hợp lệ không có instance.

Các chỉ số hữu ích gồm số request discovery theo kết quả, độ trễ, số lần retry, lỗi giải mã, số instance và tuổi bản cập nhật thành công nếu ứng dụng có theo dõi.

## 10. Những hiểu nhầm thường gây sai thiết kế

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| HTTP DiscoveryClient chính là Kubernetes Java Client trong ứng dụng | Nó giao tiếp với Discovery Server; server đảm nhiệm đường đọc Kubernetes trong mô hình này |
| GET /apps trả về một mảng tên | API trả các đối tượng danh mục; giao diện Spring mới cung cấp danh sách tên |
| Có tên Service nghĩa là có Pod nhận traffic | Phải xem danh sách instance và điều kiện backend |
| Đã lấy được danh sách thì gọi nghiệp vụ chắc chắn thành công | Cần kiểm tra đường mạng, cổng, giao thức và sức khỏe đích |
| Cấp Role cho ứng dụng sẽ sửa mọi lỗi discovery | Quyền phải cấp cho đúng danh tính ở đúng chặng đang lỗi |
| Đổi namespace ở client luôn đổi phạm vi server đọc | Phạm vi dữ liệu HTTP discovery được cấu hình tại server |
| Discovery Server đăng ký ứng dụng giống mọi registry khác | Dữ liệu ở đây được lấy từ Kubernetes; không tự suy ra cần đăng ký hoặc gửi lease từ ứng dụng |
| Discovery Server tự proxy mọi request nghiệp vụ | Chức năng đang xét là cung cấp dữ liệu discovery |
| Mọi lỗi đều nên chuyển thành danh sách rỗng | Phải giữ sự khác biệt giữa dữ liệu hợp lệ và lỗi lấy dữ liệu |

Cổng `8761` xuất hiện trong ví dụ triển khai Discovery Server không đủ để kết luận hệ thống đang dùng Eureka hoặc cần cấu hình Eureka client. Chọn giao thức và starter dựa trên thành phần thực sự triển khai.

## 11. Chọn tính năng thực sự cần cho triển khai

HTTP discovery hữu ích khi muốn tập trung việc đọc Kubernetes API tại server và cho các ứng dụng lấy thông tin qua giao diện HTTP. Đổi lại, server trở thành một phụ thuộc cần vận hành: có đường truy cập ổn định, dữ liệu được cập nhật, quyền phù hợp và khả năng phục vụ tải truy vấn.

Tập trung Kubernetes access không loại bỏ toàn bộ tải discovery. Nhiều client gọi `/apps` thường xuyên vẫn tạo nhiều request HTTP và có thể truyền nhiều dữ liệu. Nếu chỉ cần một dịch vụ, không nên định kỳ lấy toàn danh mục rồi gọi tiếp từng dịch vụ chỉ để tạo một bản sao giống dữ liệu vừa tải.

Nếu ứng dụng chỉ cần gọi một Kubernetes Service qua DNS và không cần liệt kê instance hoặc dùng metadata, đánh giá xem có thật sự cần Discovery Server và client tương ứng hay không.

ConfigMap và Secret có thể cung cấp cấu hình URL hoặc thông tin xác thực khi kiến trúc cần, nhưng việc cấu hình mới có hiệu lực phụ thuộc cơ chế nạp lại của ứng dụng. Configuration Watcher không đồng nghĩa HTTP client đang theo dõi thay đổi của danh mục dịch vụ.

Catalog watch của discovery là cơ chế khác với theo dõi cấu hình. Khi dùng tính năng này với HTTP discovery, phải kiểm tra khả năng hỗ trợ và cấu hình ở cả server lẫn client theo phiên bản; một request `GET /apps` thông thường không tự trở thành luồng Kubernetes watch.

Khi đánh giá vai trò HTTP client, hãy kiểm tra đủ ba kết quả: **lấy được phản hồi HTTP hợp lệ, chuyển được phản hồi thành dữ liệu discovery đúng cấu trúc và đưa dữ liệu đó tới đúng thành phần sử dụng**. Việc lựa chọn instance và gọi nghiệp vụ cần được xác minh ở bước tiếp theo của đường xử lý.
