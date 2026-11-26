# Phân biệt địa chỉ Pod, ClusterIP và địa chỉ DNS

Thuộc chương **ServiceInstance và cổng** của module **SPRING_CLOUD_KUBERNETES**.

Khi tích hợp ứng dụng Spring với Kubernetes, cùng một dịch vụ có thể được biểu diễn bằng tên logic trong DiscoveryClient, địa chỉ của một Pod, ClusterIP hoặc tên DNS. Nhầm các giá trị này thường dẫn đến việc gọi đúng ứng dụng bằng sai cổng, kết nối thành công trong cluster nhưng thất bại trên máy phát triển, hoặc chọn thêm cơ chế discovery khi DNS đã đáp ứng nhu cầu.

Module bao quát DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer, Configuration Watcher, RBAC và theo dõi sức khỏe Pod. Bài này tập trung vào ý nghĩa của địa chỉ và cổng, giúp bạn đọc đúng ServiceInstance và lựa chọn đường kết nối cần thiết cho triển khai.

Sau bài học, bạn có thể:

- Nhận biết địa chỉ nào trỏ tới một Pod và địa chỉ nào đại diện cho Kubernetes Service.
- Giải thích DNS của Service thông thường phân giải tới đâu và vì sao headless Service có hành vi khác.
- Ghép đúng host, port và scheme khi đọc ServiceInstance hoặc tạo URI.
- Đối chiếu kết quả discovery với Service, EndpointSlice và truy vấn DNS trong cluster.
- Phân biệt lỗi khám phá địa chỉ, lỗi phân giải tên và lỗi kết nối tới ứng dụng.

## 1. Một dịch vụ, nhiều cách biểu diễn địa chỉ

Giả sử dịch vụ `inventory-api` chạy trong namespace `address-lab`, có hai Pod và một Service:

| Thành phần | Giá trị minh họa |
| --- | --- |
| Tên Kubernetes Service | `inventory-api` |
| Namespace | `address-lab` |
| Pod thứ nhất | `10.244.1.23`, ứng dụng nghe cổng `8080` |
| Pod thứ hai | `10.244.2.37`, ứng dụng nghe cổng `8080` |
| ClusterIP của Service | `10.96.40.12` |
| Cổng Service | `80` |
| Cổng đích trên Pod | `8080` |
| DNS của Service | `inventory-api.address-lab.svc.cluster.local` |

Các IP chỉ là dữ liệu minh họa; cluster của bạn sẽ cấp địa chỉ khác. Bài dùng `cluster.local` làm cluster domain giả định. Nếu cluster dùng domain khác, phải thay phần hậu tố tương ứng.

Service được mô tả như sau:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-api
  namespace: address-lab
spec:
  type: ClusterIP
  selector:
    app: inventory-demo
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: http
~~~

Trong Pod được chọn, cổng có tên `http` tương ứng với cổng ứng dụng:

~~~yaml
ports:
  - name: http
    containerPort: 8080
~~~

Từ đây có ba cách biểu diễn đích kết nối:

~~~text
Một Pod cụ thể:
http://10.244.1.23:8080/

Service qua địa chỉ ảo:
http://10.96.40.12:80/

Service qua tên DNS:
http://inventory-api.address-lab.svc.cluster.local:80/
~~~

Ba URI này có thể dẫn tới cùng loại phản hồi nghiệp vụ, nhưng đường tìm đích và thành phần chịu trách nhiệm chọn backend khác nhau. Không thay một host bằng host khác rồi giữ nguyên cổng mà chưa kiểm tra ý nghĩa của cặp địa chỉ–cổng.

## 2. Pod IP: địa chỉ của một đơn vị thực thi

Pod IP cho phép client liên lạc với Pod cụ thể khi mạng và chính sách truy cập cho phép. Các container trong cùng Pod chia sẻ không gian mạng; hai container cùng Pod không có hai Pod IP độc lập để client bên ngoài lựa chọn. [Mô hình mạng Kubernetes](https://kubernetes.io/docs/concepts/services-networking/).

Trong ví dụ, gọi:

~~~text
http://10.244.1.23:8080/
~~~

có nghĩa là nhắm tới listener cổng 8080 trên Pod mang IP đó. Lời gọi không cần đi qua ClusterIP của Service `inventory-api` để nhờ Service chọn Pod.

“Gọi trực tiếp Pod” mô tả cách chọn địa chỉ đích. Trên đường truyền vẫn có thể có CNI, NetworkPolicy, sidecar hoặc cơ chế mạng khác. Không thể suy ra rằng gọi Pod IP sẽ bỏ qua mọi lớp kiểm soát.

### 2.1. Độ ổn định của Pod IP

Pod có thể bị thay thế khi rollout, reschedule hoặc khi controller tạo replica mới. Một tiến trình container khởi động lại trong cùng Pod khác với việc cả Pod bị thay thế. Khi Pod mới xuất hiện, không nên kỳ vọng nó giữ nguyên địa chỉ của Pod cũ.

Vì vậy, không ghi cố định Pod IP vào cấu hình nghiệp vụ dài hạn. Nếu cần chọn từng instance, hãy dùng một nguồn discovery cập nhật theo vòng đời endpoint và chấp nhận việc địa chỉ thay đổi giữa lúc chọn instance và lúc kết nối.

Một địa chỉ từng kết nối được cũng không phải định danh vĩnh viễn của một replica. Log điều tra nên đi kèm thời điểm quan sát, namespace và thông tin Pod liên quan nếu có.

### 2.2. Khi nào chọn Pod IP có ích?

Các tình huống phù hợp gồm kiểm tra một instance cụ thể, cân bằng tải ở phía client hoặc giao thức cần biết danh sách peer. Mỗi tình huống đều cần xử lý endpoint biến mất, timeout và thay đổi readiness.

Pod IP không phải lựa chọn mặc định cho mọi client. Nếu chỉ cần gọi một dịch vụ HTTP trong cluster, tên DNS của Service thường là điểm bắt đầu đơn giản hơn.

## 3. ClusterIP: địa chỉ ảo đại diện cho Service

ClusterIP là địa chỉ của Kubernetes Service trong không gian mạng dịch vụ. Service xác định tập backend; cơ chế mạng của cluster đưa lưu lượng tới endpoint phù hợp.

Với ví dụ trên:

~~~text
10.96.40.12:80 -> một endpoint như 10.244.1.23:8080
~~~

ClusterIP không phải IP của một container chuyên chạy “Service”. Tùy hạ tầng, cơ chế thực hiện có thể dựa trên kube-proxy hoặc một thành phần mạng thay thế. Không nên hình dung luôn có một tiến trình ứng dụng đang lắng nghe trực tiếp trên địa chỉ ảo đó. [Service và cơ chế virtual IP của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/service/).

### 3.1. Phạm vi ổn định

ClusterIP thường giữ nguyên trong vòng đời của Service, kể cả khi các Pod phía sau thay đổi. Nếu xóa rồi tạo lại Service, địa chỉ được cấp có thể khác. Tên DNS giúp client tiếp tục tham chiếu Service bằng tên thay vì lưu IP này.

ClusterIP là địa chỉ phục vụ kết nối trong cluster theo thiết kế của mạng Kubernetes. Máy phát triển hoặc một máy bên ngoài không tự có route tới nó. Một môi trường có VPN, routing hoặc gateway riêng có thể mở rộng khả năng truy cập, nhưng đó là cấu hình mạng bổ sung.

### 3.2. ClusterIP không đồng nghĩa với một Pod cố định

Nhiều kết nối tới cùng ClusterIP có thể tới các Pod khác nhau. Một kết nối TCP đã thiết lập thường tiếp tục gắn với backend của kết nối đó; HTTP keep-alive hoặc HTTP/2 có thể tái sử dụng kết nối cho nhiều yêu cầu.

Vì vậy, gọi lặp lại một URL rồi thấy cùng tên Pod vài lần không chứng minh Service chỉ có một backend. Ngược lại, hai lần nhận hai tên Pod khác nhau cũng không chứng minh cơ chế phân phối luôn chia đều từng yêu cầu.

Tính khả dụng còn phụ thuộc endpoint, readiness, chính sách lưu lượng và trạng thái mạng. Có ClusterIP không bảo đảm ứng dụng luôn trả lời thành công.

## 4. DNS: tên để tìm đích, không phải một cổng mạng mới

Với Service thông thường trong ví dụ:

~~~text
inventory-api.address-lab.svc.cluster.local
    -> 10.96.40.12
~~~

DNS phân giải tên thành địa chỉ. Sau khi có địa chỉ, client mới thực hiện kết nối tới cổng của URI. Với Service thông thường, tên DNS là một cách tham chiếu ClusterIP; không có thêm một tầng “DNS proxy” chuyển mọi gói HTTP.

### 4.1. Tên ngắn và namespace

Trong Pod có cấu hình DNS thông thường của Kubernetes, có thể gặp các dạng:

| Dạng tên | Ý nghĩa trong ví dụ |
| --- | --- |
| `inventory-api` | Tên ngắn, được tìm theo search domain của Pod gọi |
| `inventory-api.address-lab` | Có thêm namespace trong cấu hình DNS thông thường |
| `inventory-api.address-lab.svc.cluster.local` | Tên đầy đủ theo cluster domain giả định của bài |

Nếu client cũng ở `address-lab`, tên ngắn thường đủ. Nếu client ở namespace khác, tên ngắn có thể trỏ tới Service cùng tên trong namespace của client hoặc không tìm thấy gì. Cần chỉ rõ namespace khi thiết kế lời gọi qua namespace.

Kubernetes cấu hình search domain cho Pod; tên DNS của Service thông thường có bản ghi A hoặc AAAA tương ứng với ClusterIP. Headless Service là ngoại lệ cần hiểu riêng ở phần sau. [DNS cho Service và Pod](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/).

Không áp dụng nguyên xi quy tắc search domain của Pod cho laptop. Máy phát triển có thể dùng DNS doanh nghiệp hoặc DNS Internet, không biết zone nội bộ của cluster.

### 4.2. DNS A/AAAA không cung cấp cổng HTTP

Phân giải `inventory-api.address-lab.svc.cluster.local` thành công không nói rằng phải dùng cổng 8080. Với Service trong ví dụ, client dùng cổng 80 vì `spec.ports[].port` là 80.

Bản ghi SRV có thể mô tả cổng được đặt tên, nhưng một HTTP client thông thường không tự thực hiện truy vấn SRV chỉ vì nhận được URL HTTP. Khi cấu hình URL, vẫn cần biết scheme và cổng thích hợp.

Tên cổng `http` là tên cấu hình, không phải lệnh làm server tự mở cổng 80. Tương tự, dùng `https://` cần listener và TLS phù hợp; đổi scheme trong URI không biến một listener HTTP thành HTTPS.

## 5. Ghép đúng địa chỉ với cổng

Với Service `port: 80`, `targetPort: http` và cổng Pod có tên `http` là 8080:

| Đích kết nối | Cổng dùng trong ví dụ | Giải thích |
| --- | --- | --- |
| Pod IP `10.244.1.23` | `8080` | Đây là cổng listener trên endpoint |
| ClusterIP `10.96.40.12` | `80` | Đây là cổng được công bố bởi Service |
| DNS Service thông thường | `80` | Tên phân giải tới ClusterIP |
| `localhost` trong Pod client | Cổng của tiến trình trong chính Pod client | Không tự đại diện cho Service inventory |
| DNS headless trong lab mở rộng | `8080` | Tên phân giải tới Pod IP; không có virtual IP để ánh xạ 80 sang 8080 |

Hai phép ghép dễ sai là:

~~~text
http://10.244.1.23:80/
http://10.96.40.12:8080/
~~~

Trong ví dụ, không có cấu hình nào bảo đảm hai địa chỉ này phục vụ HTTP. Lỗi không nằm ở việc “Kubernetes chưa cập nhật DNS”; client đã ghép host thuộc một tầng với cổng thuộc tầng khác.

### 5.1. containerPort không tự khởi động listener

Khai báo `containerPort: 8080` mô tả cổng và cho phép tham chiếu bằng tên. Ứng dụng trong container vẫn phải thực sự mở listener ở cổng 8080.

Nếu server chỉ bind vào loopback trong Pod, truy cập qua Pod IP có thể không hoạt động như mong đợi. Cần kiểm tra cả cấu hình ứng dụng, không chỉ manifest.

### 5.2. host, port, scheme và URI là các trường khác nhau

Một biểu diễn hợp lệ:

~~~text
host   = 10.244.1.23
port   = 8080
scheme = http
uri    = http://10.244.1.23:8080
~~~

Không đưa `http://10.244.1.23:8080` vào trường `host` nếu API yêu cầu riêng host và port. Khi dùng IPv6, URI còn cần dấu ngoặc vuông quanh địa chỉ, ví dụ `http://[fd00::23]:8080/`; dùng API dựng URI hoặc URI do thư viện cung cấp sẽ tránh được nhiều lỗi ghép chuỗi.

Một URI không có cổng tường minh có thể sử dụng cổng mặc định của scheme ở phía HTTP client. Điều đó khác với việc Kubernetes tự dò `targetPort` từ tên DNS.

## 6. ServiceInstance trong Spring Cloud Kubernetes biểu diễn điều gì?

`DiscoveryClient.getInstances("inventory-api")` truy vấn các instance theo tên dịch vụ. Tham số này là service ID mà provider discovery hiểu; với Spring Cloud Kubernetes, đó thường là tên Kubernetes Service trong phạm vi namespace được cấu hình.

Kết quả discovery dựa trên endpoint thường chứa địa chỉ của các instance phía sau Service. Vì vậy, ServiceInstance có `serviceId` là `inventory-api` nhưng `host` là Pod IP là một biểu diễn bình thường.

Ví dụ minh họa khi khám phá các endpoint của Service trong bài:

~~~json
[
  {
    "serviceId": "inventory-api",
    "host": "10.244.1.23",
    "port": 8080,
    "uri": "http://10.244.1.23:8080"
  },
  {
    "serviceId": "inventory-api",
    "host": "10.244.2.37",
    "port": 8080,
    "uri": "http://10.244.2.37:8080"
  }
]
~~~

Đây là biểu diễn rút gọn do ứng dụng quan sát có thể tạo ra, không phải cam kết mọi phiên bản đều serialize ServiceInstance thành đúng JSON trên. Cần đối chiếu `host` với địa chỉ và `port` với cổng endpoint thực tế; không lấy cổng 80 của Service gán lại cho mọi instance.

Spring Cloud Kubernetes mô tả các trường như serviceId, host, port, URI và metadata của instance. Việc lựa chọn cổng còn phụ thuộc cấu hình khi Service có nhiều cổng. [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

### 6.1. Không mặc định host luôn là Pod IP

Ý nghĩa của host phụ thuộc provider và loại đối tượng được khám phá. Một Service `ExternalName` có thể dẫn tới tên DNS bên ngoài thay vì Pod IP. Một Service không selector cũng có thể được hậu thuẫn bởi endpoint do người vận hành quản lý.

Vì vậy, quy tắc phù hợp là: **đọc host cùng port và nguồn tạo instance**. Không suy “mọi host của ServiceInstance đều là ClusterIP”, cũng không đóng cứng “mọi host luôn là Pod IP”.

Service ID là tên logic để tìm danh sách instance. Nó không phải bằng chứng rằng hệ điều hành của client có thể phân giải đúng chuỗi đó bằng DNS.

### 6.2. Đoạn Java quan sát dữ liệu

Ví dụ dùng Java 17 trở lên, Spring Boot và một starter discovery tương thích của Spring Cloud Kubernetes, chẳng hạn starter Fabric8. Các phiên bản cần được quản lý bằng BOM phù hợp của dự án.

Lớp cấu hình dưới đây có thể đặt trong package được ứng dụng quét:

~~~java
package example.discovery;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@EnableDiscoveryClient
@Profile("address-inspection")
public class AddressInspectionConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(AddressInspectionConfiguration.class);

    @Bean
    CommandLineRunner inspectInventory(DiscoveryClient discoveryClient) {
        return args -> {
            var instances =
                    discoveryClient.getInstances("inventory-api");

            for (var instance : instances) {
                log.info("serviceId={}, host={}, port={}, uri={}",
                        instance.getServiceId(),
                        instance.getHost(),
                        instance.getPort(),
                        instance.getUri());
            }

            log.info("instanceCount={}", instances.size());
        };
    }
}
~~~

Cấu hình cho ví dụ chạy trong cluster:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - address-lab
        use-endpoint-slices: true
        primary-port-name: http
~~~

Bật profile `address-inspection` cho lượt quan sát. Cần cấp cho ServiceAccount quyền đọc Service và EndpointSlice tương ứng; nếu backend hoặc tính năng sử dụng thêm tài nguyên khác, quyền đọc phải phù hợp với yêu cầu của backend đó.

Ví dụ chỉ ghi dữ liệu địa chỉ, không gọi tới mọi URI và không coi số lượng instance là kết quả kiểm tra sức khỏe. Nếu cache discovery chưa hoàn tất hoặc endpoint đang thay đổi, cần đọc lại sau khi hệ thống hội tụ thay vì kết luận từ một lần log duy nhất.

Không cần bật ConfigMap, Secret hoặc Configuration Watcher chỉ để đọc các địa chỉ. Các tính năng cấu hình không tạo route mạng tới Pod và không đổi ý nghĩa của ClusterIP.

## 7. Gọi DNS thông thường và gọi qua LoadBalancer là hai đường xử lý

Một ứng dụng có thể dùng HTTP client thông thường:

~~~text
URL đầu vào:
http://inventory-api.address-lab.svc.cluster.local:80/

Diễn tiến:
DNS -> ClusterIP:80 -> endpoint Pod:8080
~~~

Trong đường này, HTTP client không bắt buộc dùng DiscoveryClient. Khả năng đọc Kubernetes API cũng không phải điều kiện mặc định chỉ để phân giải DNS và gọi Service.

Một HTTP client đã tích hợp Spring Cloud LoadBalancer có thể nhận URL logic:

~~~text
URL đầu vào:
http://inventory-api/

Diễn tiến có thể có:
service ID -> nguồn instance -> chọn một đích -> kết nối
~~~

URL nhìn giống nhau không bảo đảm cơ chế bên trong giống nhau. Cần biết client bean nào có interceptor hoặc filter của LoadBalancer.

### 7.1. POD và SERVICE trong Spring Cloud Kubernetes LoadBalancer

Spring Cloud Kubernetes LoadBalancer hỗ trợ chế độ `POD` và `SERVICE`, chọn qua `spring.cloud.kubernetes.loadbalancer.mode`. Chế độ POD sử dụng DiscoveryClient để lấy instance; chế độ SERVICE tạo đích theo Service và cổng Service. [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Hai sơ đồ minh họa cho cùng `inventory-api`:

~~~text
POD:
URL logic inventory-api
 -> DiscoveryClient
 -> chọn 10.244.1.23:8080
 -> Pod đã chọn

SERVICE:
URL logic inventory-api
 -> xác định Service và namespace
 -> inventory-api.address-lab.svc.cluster.local:80
 -> cơ chế Service chọn endpoint
~~~

Đổi chế độ LoadBalancer không có nghĩa là mọi lời gọi `DiscoveryClient.getInstances()` khác trong ứng dụng tự đổi thành danh sách ClusterIP. Đó là các điểm sử dụng có hợp đồng riêng.

Một client có LoadBalancer cũng có thể diễn giải toàn bộ hostname trong URL thành service ID. Vì vậy, không tùy tiện đưa FQDN Kubernetes vào client đang kỳ vọng tên logic rồi giả định nó sẽ dùng DNS theo cách của client thông thường. Cần chọn client và nguồn địa chỉ nhất quán với đường gọi.

### 7.2. Tránh thêm nhiều tầng chọn đích không cần thiết

Nếu client đã chọn Pod IP từ discovery, Kubernetes Service không thực hiện thêm bước chọn backend qua ClusterIP cho chính địa chỉ đó. Nếu client chọn Service, tầng Service vẫn tham gia đưa kết nối tới endpoint.

Mục tiêu không phải tối đa hóa số lớp cân bằng tải. Hãy xác định tầng nào chịu trách nhiệm chọn replica, cập nhật endpoint, áp dụng timeout và xử lý kết nối lỗi.

Không lưu cache Pod IP vô thời hạn chỉ vì đã có Circuit Breaker. Cũng không giả định DNS sẽ đổi backend cho một kết nối HTTP/2 đang tồn tại.

## 8. Hai ngoại lệ làm tên DNS không trỏ tới ClusterIP

### 8.1. Headless Service

Headless Service có `clusterIP: None`. Với selector chọn Pod trong ví dụ, DNS có thể trả về các địa chỉ Pod tương ứng thay vì một virtual IP.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-peers
  namespace: address-lab
spec:
  clusterIP: None
  selector:
    app: inventory-demo
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: http
~~~

Ở đây, DNS của `inventory-peers` hướng client tới các endpoint; không có bước ánh xạ qua ClusterIP từ cổng 80 sang 8080. Ví dụ chọn cổng 8080 để khớp listener của Pod.

~~~text
inventory-peers.address-lab.svc.cluster.local
    -> 10.244.1.23
    -> 10.244.2.37

Kết nối HTTP:
http://inventory-peers.address-lab.svc.cluster.local:8080/
~~~

Client hoặc resolver quyết định cách sử dụng các địa chỉ nhận được. Danh sách DNS không tự bảo đảm chia đều từng yêu cầu, không thay cho cơ chế kiểm tra lỗi kết nối và có thể chịu ảnh hưởng của cache.

Tập địa chỉ được công bố còn liên quan tới readiness và chính sách của Service. Không suy rằng DNS headless sẽ luôn trả mọi Pod bất kể trạng thái. Với nhu cầu định danh ổn định cho từng peer, cần thêm thiết kế hostname, subdomain hoặc StatefulSet phù hợp. [Headless Services trong Kubernetes](https://kubernetes.io/docs/concepts/services-networking/service/#headless-services).

### 8.2. ExternalName

Một Service kiểu `ExternalName` có thể đặt bí danh DNS nội bộ tới một hostname khác:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: partner-api
  namespace: address-lab
spec:
  type: ExternalName
  externalName: api.partner.example
~~~

DNS của tên Service trả quan hệ CNAME; không tạo cơ chế proxy Pod hoặc ánh xạ cổng cho hostname bên ngoài. Việc truy cập HTTP hoặc HTTPS còn phụ thuộc cổng, header Host, SNI và chứng thư của đích.

Ví dụ này chỉ minh họa cấu trúc; `api.partner.example` không phải endpoint thực hành đang được cung cấp. Khi dùng discovery cho ExternalName, phải kiểm tra khả năng hỗ trợ và cấu hình của provider Spring đang sử dụng.

Hai ngoại lệ trên cho thấy “địa chỉ DNS” là một cách đặt tên. Muốn biết tên dẫn tới Pod, ClusterIP hay hệ thống ngoài, phải biết loại Service và kết quả phân giải.

## 9. Lab: kiểm chứng ba đường truy cập

### 9.1. Chuẩn bị workload riêng cho lab

Bạn cần cluster thử nghiệm, `kubectl`, quyền tạo tài nguyên trong namespace lab và khả năng kéo image BusyBox. Các lệnh trong bài dành cho người học thực hiện; địa chỉ, tên Pod và thời gian khởi động phụ thuộc cluster.

Lưu manifest sau vào môi trường lab của bạn rồi áp dụng bằng `kubectl apply -f <tệp>`:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: address-lab
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-api
  namespace: address-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-demo
  template:
    metadata:
      labels:
        app: inventory-demo
    spec:
      containers:
        - name: http
          image: busybox:1.36
          command: ["sh", "-c"]
          args:
            - |
              mkdir -p /www
              hostname > /www/index.html
              exec httpd -f -p 8080 -h /www
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 3
---
apiVersion: v1
kind: Service
metadata:
  name: inventory-api
  namespace: address-lab
spec:
  type: ClusterIP
  selector:
    app: inventory-demo
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: http
---
apiVersion: v1
kind: Pod
metadata:
  name: address-client
  namespace: address-lab
spec:
  automountServiceAccountToken: false
  restartPolicy: Never
  containers:
    - name: client
      image: busybox:1.36
      command: ["sleep", "3600"]
~~~

Server trả về hostname của Pod để người học nhận biết backend. Pod `address-client` chỉ dùng DNS và kết nối mạng; không cần token ServiceAccount để đọc Kubernetes API. Việc tạo, quan sát tài nguyên từ `kubectl` vẫn sử dụng quyền của người vận hành.

Chờ workload sẵn sàng:

~~~bash
kubectl rollout status deployment/inventory-api --namespace address-lab

kubectl wait --for=condition=Ready pod/address-client --namespace address-lab --timeout=120s
~~~

Pod client tồn tại trong khoảng thời gian sleep của lab. Nếu quay lại sau thời gian đó, cần khởi tạo lại client thử nghiệm theo quy trình của môi trường bạn.

### 9.2. Lấy ba nguồn dữ liệu riêng

~~~bash
kubectl get pods --namespace address-lab --selector app=inventory-demo --output wide

kubectl get service inventory-api --namespace address-lab --output yaml

kubectl get endpointslices --namespace address-lab --selector kubernetes.io/service-name=inventory-api --output yaml
~~~

Ghi lại:

| Nguồn | Giá trị cần lấy |
| --- | --- |
| Pod | IP của từng Pod |
| Service | `spec.clusterIP`, `port`, `targetPort` và selector |
| EndpointSlice | `addresses`, cổng endpoint, condition và `targetRef` |

EndpointSlice có thể được chia thành nhiều tài nguyên. Cần đối chiếu toàn bộ tập slice mang nhãn của Service, không lấy một IP đầu tiên rồi kết luận đó là ClusterIP.

Trong lab, cổng endpoint phải phù hợp với listener 8080. ClusterIP lấy từ Service là một giá trị riêng, không phải một phần tử bắt buộc trong danh sách endpoint.

### 9.3. Phân giải tên từ vị trí client thực sự chạy

~~~bash
kubectl exec --namespace address-lab address-client -- nslookup inventory-api
~~~

Kỳ vọng tên Service thông thường phân giải tới ClusterIP vừa đọc. Kết quả `nslookup` thường hiển thị cả địa chỉ DNS server; không nhầm địa chỉ nameserver với địa chỉ được trả về cho `inventory-api`.

Thử tên đầy đủ, với cluster domain của bài:

~~~bash
kubectl exec --namespace address-lab address-client -- nslookup inventory-api.address-lab.svc.cluster.local
~~~

Nếu tên ngắn hoạt động nhưng tên đầy đủ ví dụ không hoạt động, hãy xác nhận cluster domain thực tế. Có thể xem cấu hình resolver trong Pod:

~~~bash
kubectl exec --namespace address-lab address-client -- cat /etc/resolv.conf
~~~

Các thông tin này phải được quan sát trong Pod gọi. Kết quả phân giải trên laptop không thay thế kiểm tra trong Pod. [Hướng dẫn Kubernetes về điều tra DNS](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/).

### 9.4. Gọi qua DNS của Service

~~~bash
kubectl exec --namespace address-lab address-client -- wget -T 3 -qO- http://inventory-api/
~~~

URL dùng HTTP không ghi cổng nên HTTP client sử dụng cổng mặc định 80, khớp cổng Service của lab.

Kỳ vọng nhận hostname của một Pod `inventory-api`. Có thể chạy lại để quan sát, nhưng không đặt điều kiện bắt buộc hai lần liên tiếp phải tới hai Pod khác nhau.

### 9.5. Gọi ClusterIP và Pod IP với đúng cổng

Giả sử giá trị bạn đọc được đúng bằng các IP minh họa, các lệnh tương ứng là:

~~~bash
kubectl exec --namespace address-lab address-client -- wget -T 3 -qO- http://10.96.40.12:80/

kubectl exec --namespace address-lab address-client -- wget -T 3 -qO- http://10.244.1.23:8080/
~~~

**Thay cả hai IP bằng dữ liệu của cluster trước khi chạy.**

Lệnh qua ClusterIP có thể trả về hostname của một trong hai Pod. Lệnh gọi Pod IP phải nhắm tới Pod cụ thể ứng với IP đó, miễn là Pod chưa thay đổi và kết nối được phép.

Bảng đối chiếu của bạn nên chứa:

| Lời gọi | Đích biểu diễn | Kết quả cần đối chiếu |
| --- | --- | --- |
| DNS Service, cổng 80 | Tên dẫn tới Service | Hostname thuộc tập backend |
| ClusterIP, cổng 80 | Service trực tiếp bằng IP | Hostname thuộc tập backend |
| Pod IP, cổng 8080 | Một endpoint cụ thể | Hostname của đúng Pod được chọn |

Không dùng việc nhận cùng nội dung phản hồi làm bằng chứng rằng ba dạng địa chỉ là một. Chính việc đối chiếu Service và endpoint mới giải thích được tại sao chúng cùng dẫn tới workload này.

### 9.6. Quan sát khi thay thế Pod

Ghi lại ClusterIP hiện tại, sau đó thực hiện rollout trong lab:

~~~bash
kubectl rollout restart deployment/inventory-api --namespace address-lab

kubectl rollout status deployment/inventory-api --namespace address-lab

kubectl get pods --namespace address-lab --selector app=inventory-demo --output wide

kubectl get service inventory-api --namespace address-lab --output wide
~~~

Sau rollout:

- Tên và danh tính các Pod có thể đổi; Pod IP cũ không phải địa chỉ bền vững của dịch vụ.
- Service không bị tạo lại nên ClusterIP của nó vẫn giữ nguyên.
- DNS Service vẫn tham chiếu tên Service; client không cần ghi lại từng Pod IP.
- Discovery dựa trên endpoint cần nhận tập endpoint mới, với khoảng trễ cập nhật tùy cơ chế.

IP có thể được tái sử dụng, vì vậy không đặt điều kiện bắt buộc mọi IP sau rollout đều khác trước. Điều quan trọng là client không dựa vào một Pod IP cố định để biểu diễn toàn bộ dịch vụ.

### 9.7. Mở rộng lab với headless Service

Áp dụng manifest `inventory-peers` ở phần 8, rồi truy vấn:

~~~bash
kubectl exec --namespace address-lab address-client -- nslookup inventory-peers
~~~

Kỳ vọng nhìn thấy các địa chỉ endpoint phù hợp thay vì ClusterIP của `inventory-api`. Sau đó gọi:

~~~bash
kubectl exec --namespace address-lab address-client -- wget -T 3 -qO- http://inventory-peers:8080/
~~~

Service headless này dùng cổng 8080, không phải cổng 80 của Service thông thường trong lab. Sự khác biệt về cổng giúp làm rõ rằng DNS headless không cung cấp bước ánh xạ qua virtual IP.

## 10. Đối chiếu lỗi theo đúng tầng

| Hiện tượng | Tầng nên kiểm tra | Điều cần tránh suy luận |
| --- | --- | --- |
| `UnknownHostException` hoặc không phân giải được tên | Tên, namespace, cluster domain, resolver và DNS | Chưa có căn cứ kết luận Pod đã tắt |
| Phân giải được ClusterIP nhưng HTTP timeout | Route, NetworkPolicy, Service, endpoint và listener | DNS thành công không bảo đảm kết nối thành công |
| Pod IP:8080 chạy được nhưng ClusterIP:80 lỗi | Selector, EndpointSlice, cổng Service và cơ chế Service | Không mặc định lỗi nằm ở mã Java |
| DNS Service:8080 lỗi trong lab | Cổng sai ở URL Service | Không dùng cổng Pod cho mọi host |
| Discovery trả host nhưng client không kết nối được | Vị trí client, cổng, endpoint cũ, chính sách mạng và TLS | Discovery không kiểm tra toàn bộ đường truyền |
| HTTP 401 hoặc 403 từ ứng dụng đích | Xác thực, phân quyền HTTP, gateway hoặc mesh liên quan | Không tự đồng nhất với lỗi RBAC Kubernetes |
| Kubernetes API trả 403 khi discovery đọc endpoint | ServiceAccount và quyền API | Không sửa DNS để chữa quyền đọc API |
| HTTP phản hồi từ một Pod ngoài dự kiến | Selector, namespace, Service ID, cache và tầng chọn đích | Không suy địa chỉ IP từ tên nghiệp vụ trong log |

Một trình tự chẩn đoán hiệu quả là lấy dữ liệu theo từng lớp: Pod có IP và listener nào, Service chọn Pod nào, endpoint công bố cổng nào, DNS trả địa chỉ nào và client cuối cùng kết nối tới host:port nào.

Kubernetes cũng hướng dẫn kiểm tra Service bằng cách đối chiếu selector, endpoint, cổng và khả năng truy cập backend. Thứ tự này giúp tách lỗi cấu hình Service khỏi lỗi ứng dụng. [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/).

### 10.1. Máy phát triển không đại diện cho mạng trong cluster

Một chương trình Java chạy trên laptop có thể đọc Kubernetes API nhờ kubeconfig, nhưng vẫn không có route tới Pod IP được discovery trả về. Quyền đọc API và khả năng kết nối dữ liệu là hai điều độc lập.

Để kiểm tra ứng dụng trong lab từ máy phát triển, có thể dùng:

~~~bash
kubectl port-forward --namespace address-lab service/inventory-api 18080:80
~~~

Sau đó:

~~~bash
curl http://localhost:18080/
~~~

Ở đây, `localhost:18080` thuộc máy chạy port-forward. Đây là đường truy cập do công cụ thiết lập tới backend, không chứng minh laptop đã định tuyến trực tiếp được tới ClusterIP. Port-forward cũng không phải phép kiểm chứng toàn bộ đường cân bằng tải của Service.

### 10.2. Tên và IP không thay thế cấu hình bảo mật

Gọi IP thay cho DNS có thể làm HTTP Host header hoặc tên kiểm tra chứng thư TLS khác đi. Một lỗi TLS sau khi thay host chưa chắc là do cổng không mở.

Không vô hiệu hóa kiểm tra chứng thư để che khác biệt này. Cần dùng tên, chứng thư và chính sách xác thực đúng với đường gọi được thiết kế.

## 11. Chọn cách truy cập theo nhu cầu

| Nhu cầu | Điểm bắt đầu phù hợp | Trách nhiệm cần tính tới |
| --- | --- | --- |
| Gọi dịch vụ HTTP thông thường trong cluster | DNS của Service | Cổng Service, timeout và khả năng truy cập |
| Xem từng replica để điều tra | Endpoint hoặc Pod IP được quan sát tại thời điểm đó | Địa chỉ thay đổi, cổng quản trị và quyền truy cập |
| Chọn replica ở phía Spring client | DiscoveryClient và LoadBalancer phù hợp | Làm mới danh sách, readiness, chọn cổng và xử lý lỗi |
| Tìm peer với yêu cầu định danh riêng | Headless Service và thiết kế workload phù hợp | Giao thức peer, DNS cache, readiness và vòng đời thành viên |
| Gọi ứng dụng từ bên ngoài cluster | Ingress, Gateway, LoadBalancer hoặc cơ chế truy cập đã thiết kế | DNS ngoài cluster, TLS và định tuyến tới dịch vụ |
| Kiểm tra cục bộ trong thời gian ngắn | Port-forward | Phân biệt đường kiểm tra với đường truy cập triển khai |

Nếu yêu cầu chỉ là gọi `inventory-api` bằng tên Service, không cần tự viết mã lấy ClusterIP rồi lưu lại trong ConfigMap. Nếu cần dùng ConfigMap để quản lý URL, nên quản lý đúng tên logic hoặc URL phù hợp với HTTP client đang dùng; cập nhật cấu hình không thay đổi hợp đồng của cặp host–port.

Secret quản lý thông tin nhạy cảm, Configuration Watcher phục vụ luồng cập nhật cấu hình và DiscoveryClient phục vụ tìm dịch vụ. Chúng không thay thế DNS, đường mạng hay listener HTTP. Việc hiểu đúng từng lớp giúp chỉ bật những tính năng Spring Cloud Kubernetes thực sự cần.

## 12. Những điểm cần nhớ

Pod IP hướng tới một đơn vị thực thi cụ thể. ClusterIP đại diện cho Service bằng địa chỉ ảo. DNS là tên được phân giải theo loại Service và môi trường resolver: Service thông thường thường dẫn tới ClusterIP, headless Service dẫn tới endpoint, còn ExternalName tạo bí danh tới hostname khác.

Khi đọc ServiceInstance, hãy xem service ID, host, port và URI cùng nhau rồi đối chiếu với nguồn endpoint. Với ví dụ `port: 80` và listener Pod ở 8080, kết nối tới Service dùng cổng 80, còn kết nối trực tiếp Pod dùng cổng 8080. Đường gọi chỉ rõ ràng khi bạn biết cả địa chỉ đại diện cho tầng nào và thành phần nào chịu trách nhiệm chọn backend.