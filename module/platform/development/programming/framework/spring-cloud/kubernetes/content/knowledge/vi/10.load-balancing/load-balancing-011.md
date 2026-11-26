# Khi DNS, Gateway hoặc service mesh đã đáp ứng yêu cầu

## Mục tiêu và phạm vi

Trong chương **Cân bằng tải** của module **SPRING_CLOUD_KUBERNETES**, việc biết cấu hình Spring Cloud LoadBalancer cần đi cùng khả năng xác định khi nào không cần thêm nó vào ứng dụng.

Một ứng dụng có thể gọi dịch vụ ổn định qua DNS Kubernetes, qua Gateway hoặc qua service mesh đã có. Nếu đường gọi đó đáp ứng yêu cầu về định tuyến, sức khỏe backend, hiệu năng và vận hành, ứng dụng có thể dùng HTTP client thông thường thay vì tự đọc danh sách Pod rồi chọn đích.

Bài này giúp bạn:

- Xác định thành phần đang chịu trách nhiệm chọn backend.
- Phân biệt khả năng của DNS, Kubernetes Service, Gateway và mesh.
- Nhận ra chính sách bị lặp ở nhiều tầng.
- Kiểm chứng trước khi bỏ LoadBalancer phía ứng dụng.

Ví dụ dùng `order-service` gọi `catalog-api` trong namespace `demo`. API đích có `GET /products/{id}`. Tất cả tên, số liệu và chính sách minh họa cần được điều chỉnh theo môi trường thực tế.

## 1. Bắt đầu từ yêu cầu của đường gọi

Câu hỏi cần trả lời trước tiên là: ứng dụng cần gì ngoài việc gọi một API qua một tên ổn định?

| Yêu cầu | Điều cần kiểm tra ở hạ tầng hiện có |
| --- | --- |
| Gọi một tên Service ổn định | DNS và Service có hoạt động từ môi trường caller không? |
| Không đưa kết nối mới tới backend chưa sẵn sàng | Readiness và tập endpoint được sử dụng có đúng không? |
| Định tuyến theo path/header | Gateway hoặc thành phần mesh L7 có áp dụng chính sách đó không? |
| Chia traffic theo phiên bản | Có route/subset và dữ liệu đo xác nhận tỷ lệ không? |
| Timeout, retry, loại đích lỗi | Tầng nào sở hữu từng chính sách và phạm vi tác động? |
| Mã hóa, danh tính giữa workload | Cơ chế bảo mật nào thực sự nằm trên đường gọi? |
| Chọn đích theo dữ liệu nghiệp vụ riêng | Tầng hiện có có biểu đạt và thực hiện đúng yêu cầu đó không? |

Một hệ thống không cần mọi dòng trong bảng. Chỉ thêm cơ chế để đáp ứng yêu cầu cụ thể còn thiếu.

“Đã cài Gateway” hoặc “namespace đã bật mesh” là thông tin cấu hình ban đầu. Kết luận đã đáp ứng yêu cầu phải dựa trên traffic thực sự đi qua thành phần đó và kết quả quan sát.

## 2. Khi DNS Kubernetes cùng Service đã đủ

### 2.1. DNS tìm địa chỉ, Service cung cấp đường tới backend

Với Service thông thường:

~~~text
Ứng dụng gọi:
http://catalog-api.demo.svc.cluster.local/products/42

DNS:
catalog-api.demo.svc.cluster.local -> ClusterIP

Đường chuyển tiếp Service:
ClusterIP:cổng Service -> backend đủ điều kiện
~~~

A/AAAA của Service thông thường trỏ tới ClusterIP theo họ địa chỉ được cấu hình. Tên ngắn chịu ảnh hưởng namespace và DNS search của caller; dùng tên có namespace khi cần tránh nhầm. [Tài liệu DNS Kubernetes](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)

Cụm có thể sử dụng kube-proxy hoặc triển khai chuyển tiếp Service khác. DNS không phải thành phần tự kiểm tra từng request HTTP rồi chọn Pod theo nghiệp vụ.

Ví dụ Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: demo
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

Giả định các Pod đích có label phù hợp, đang nghe `8080` và có readiness probe đúng. HTTP client gọi cổng Service `80`; không thay bằng cổng container `8080` chỉ vì biết ứng dụng bên trong nghe cổng đó.

Ví dụ dùng miền `cluster.local`. Đổi theo miền cụm thực tế nếu khác.

### 2.2. Điều kiện để xem là đủ

DNS và Service có thể đáp ứng khi:

- Caller truy cập được tên Service và mạng nội bộ tương ứng.
- Ứng dụng chỉ cần API của Service, không cần danh sách Pod hay metadata từng instance.
- Cách phân phối kết nối hiện có đáp ứng tải và độ trễ yêu cầu.
- Hành vi khi backend thay đổi, dừng hoặc khởi động lại đã được kiểm chứng.
- Ứng dụng vẫn có timeout và cách xử lý lỗi phù hợp.

Trong trường hợp đó, mã nghiệp vụ không nhất thiết phải gọi Kubernetes API hoặc giữ cache instance.

### 2.3. Các giới hạn phải hiểu đúng

Với đường Service ở tầng kết nối, nhiều request trên một kết nối được giữ lại có thể tiếp tục tới cùng backend. HTTP/2 và gRPC có thể ghép nhiều request hoặc stream trên ít kết nối. Vì vậy, ba Pod không đồng nghĩa cứ ba request HTTP là mỗi Pod nhận đúng một request.

Readiness thay đổi cũng không mặc nhiên đóng ngay mọi kết nối đang tồn tại. Cần xét cập nhật endpoint, connection pool, graceful shutdown và hành vi của transport.

Nếu yêu cầu là chia theo từng request hoặc xử lý kết nối dài theo một chính sách cụ thể, hãy đo kết quả thực tế. Có thể cần một thành phần L7; cũng có thể điều chỉnh kết nối là đủ cho nhu cầu đã đặt.

### 2.4. Headless Service là trường hợp khác

Với `clusterIP: None`, DNS có thể trả địa chỉ backend thay vì ClusterIP. Kubernetes không tạo cơ chế chuyển tiếp qua IP ảo cho headless Service. Client hoặc thành phần khác phải sử dụng các địa chỉ đó theo cách phù hợp. [Tài liệu headless Service](https://kubernetes.io/docs/concepts/services-networking/service/#headless-services)

Không dùng câu “DNS đã đủ” như một kết luận chung cho mọi headless Service. Phải xem resolver lấy bao nhiêu địa chỉ, cache ra sao, client thử lại thế nào và lựa chọn cổng nào.

## 3. Ví dụ ứng dụng Spring dùng HTTP client thông thường

Giả định dự án Java 17 dùng bộ phiên bản Spring Boot phù hợp, có `RestClient` và web starter. Ví dụ này không yêu cầu ứng dụng đọc discovery chỉ để gọi API đích.

Cấu hình URL:

~~~yaml
catalog:
  base-url: http://catalog-api.demo.svc.cluster.local
~~~

Tạo một client riêng cho đường gọi DNS:

~~~java
package example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.web.client.RestClient;

@Configuration
public class CatalogHttpConfiguration {

    @Bean("catalogHttpClient")
    public RestClient catalogHttpClient(Environment environment) {
        String baseUrl =
                environment.getRequiredProperty("catalog.base-url");

        return RestClient.builder()
                .baseUrl(baseUrl)
                .build();
    }
}
~~~

Sử dụng client:

~~~java
package example.catalog;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogClient {

    private final RestClient httpClient;

    public CatalogClient(
            @Qualifier("catalogHttpClient") RestClient httpClient) {
        this.httpClient = httpClient;
    }

    public Product getProduct(long id) {
        return httpClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}
~~~

Kiểu dữ liệu:

~~~java
package example.catalog;

public record Product(long id, String name) {
}
~~~

Contract phản hồi minh họa:

~~~json
{
  "id": 42,
  "name": "Bàn phím"
}
~~~

Client này được build trực tiếp và không gắn `@LoadBalanced`. Host được xử lý theo đường resolver/DNS của transport, rồi request đi qua hạ tầng mạng thực tế của môi trường, bao gồm mesh nếu traffic thuộc phạm vi mesh.

Ví dụ giữ cấu hình ngắn để thể hiện cơ chế. Khi áp dụng, bổ sung timeout, observability, TLS và tùy biến transport cần thiết theo phiên bản Spring Boot đang dùng. Việc build trực tiếp không tự kế thừa mọi customizer của một builder được auto-configure.

Nếu ứng dụng vẫn có client LoadBalancer cho một nhu cầu khác, dùng bean và qualifier riêng. Không cần ép mọi HTTP client trong ứng dụng dùng chung một chính sách định tuyến.

## 4. Khi Gateway đã là nơi định tuyến phù hợp

### 4.1. Nhìn toàn bộ đường đi

Một đường gọi có thể là:

~~~mermaid
flowchart LR
    A[order-service hoặc client khác] --> B[Địa chỉ ổn định của Gateway]
    B --> C[Route catalog]
    C --> D[Service catalog-api]
    D --> E[Pod backend]
~~~

Gateway có thể sở hữu route theo path, xác thực ở biên, biến đổi header và những chính sách HTTP khác nếu được cấu hình. Caller chỉ cần gọi địa chỉ Gateway cùng contract được công bố.

Ví dụ:

~~~text
Caller gửi:
GET http://api-gateway.platform.svc.cluster.local/catalog/products/42

Gateway chuyển tiếp sau khi bỏ tiền tố /catalog:
GET http://catalog-api.demo.svc.cluster.local:80/products/42
~~~

Không giả định mọi traffic nội bộ đều qua Gateway. Gateway phục vụ traffic từ bên ngoài vào cụm không tự tham gia đường gọi trực tiếp giữa hai Service bên trong cụm.

Nếu đường hiện tại chỉ cần Service trực tiếp, không buộc traffic đi vòng qua một Gateway mới chỉ để tránh sử dụng một thư viện client. Phải xét thêm hop mạng, capacity, độ trễ và phạm vi ảnh hưởng của Gateway.

### 4.2. Ví dụ route Spring Cloud Gateway dùng DNS Service

Đoạn Java minh họa cho Spring Cloud Gateway Server WebFlux:

~~~java
package example.gateway;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogRoutes {

    @Bean
    public RouteLocator catalogRoutes(RouteLocatorBuilder builder) {
        return builder.routes()
                .route("catalog-route", route -> route
                        .path("/catalog/**")
                        .filters(filters -> filters.stripPrefix(1))
                        .uri("http://catalog-api.demo.svc.cluster.local:80"))
                .build();
    }
}
~~~

Giả định ứng dụng Gateway có dependency, môi trường DNS và bộ phiên bản phù hợp. Route này sử dụng URL HTTP có host DNS; đường tới backend không mặc nhiên cần một LoadBalancer phía caller để tìm Pod của `catalog-api`.

Caller phải gọi đúng path `/catalog/products/42`. Đổi địa chỉ từ Service trực tiếp sang Gateway mà giữ nhầm path `/products/42` có thể gây 404 dù DNS và mạng đều hoạt động.

### 4.3. Route lb:// vẫn dùng Spring Cloud LoadBalancer tại Gateway

Nếu route có URI:

~~~text
lb://catalog-api
~~~

Spring Cloud Gateway dùng LoadBalancer để chuyển tên dịch vụ thành host và port. Đây là trường hợp **tập trung lựa chọn đích tại Gateway**, không phải loại bỏ LoadBalancer khỏi toàn hệ thống. [Tài liệu filter của Spring Cloud Gateway](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html#_reactiveloadbalancerclientfilter)

Ứng dụng gọi Gateway có thể không cần discovery hoặc LoadBalancer riêng. Gateway vẫn cần dependency, nguồn ứng viên và quyền truy cập tương ứng với mô hình nó dùng.

Không dùng `lb://` trong một HTTP client thông thường rồi coi nó là giao thức mà DNS Kubernetes xử lý. Scheme đó có ý nghĩa tại thành phần đã được tích hợp để hiểu nó.

### 4.4. Chính sách ở Gateway không thay thế mọi trách nhiệm ứng dụng

Gateway có thể xác thực request ở một biên hệ thống, nhưng quyền nghiệp vụ với một đơn hàng hoặc một tài khoản vẫn cần được thiết kế đúng. Tương tự, Gateway có timeout không có nghĩa caller được chờ vô hạn.

Khi kết luận Gateway đã đủ, ghi rõ nó đáp ứng **yêu cầu định tuyến và phân phối đích nào trên đường gọi nào**.

## 5. Khi service mesh đã thực hiện chính sách cần thiết

Mesh có thể đưa một phần discovery, lựa chọn backend, timeout, retry, mã hóa và telemetry ra khỏi từng ứng dụng. Những khả năng cụ thể phụ thuộc sản phẩm, chế độ data plane và cấu hình. [Mô hình quản lý traffic của Istio](https://istio.io/latest/docs/concepts/traffic-management/)

Mô hình khái quát:

~~~text
Ứng dụng gọi tên Service bằng HTTP client thông thường
    -> data plane của mesh xử lý traffic thuộc phạm vi
    -> chính sách route/chọn backend được áp dụng
    -> backend nhận request
~~~

Để coi mesh đã đáp ứng yêu cầu, cần xác nhận:

- Caller và đích nằm trong phạm vi traffic được mesh quản lý.
- Tên host, cổng và giao thức được nhận diện đúng.
- Chính sách cần dùng đã được nạp vào thành phần data plane liên quan.
- Kết quả ở backend và telemetry chứng minh chính sách có hiệu lực.

### 5.1. Ví dụ chia traffic tại mesh

Giả định dùng Istio với đường HTTP đã có xử lý L7, các Pod đích cùng label `app: catalog-api`, nhưng có `version: v1` hoặc `version: v2`. Service chọn cả hai nhóm backend.

Ví dụ cấu hình subset và tỷ lệ:

~~~yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: catalog-versions
  namespace: demo
spec:
  host: catalog-api.demo.svc.cluster.local
  subsets:
    - name: stable
      labels:
        version: v1
    - name: canary
      labels:
        version: v2
---
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: catalog-traffic
  namespace: demo
spec:
  hosts:
    - catalog-api.demo.svc.cluster.local
  http:
    - route:
        - destination:
            host: catalog-api.demo.svc.cluster.local
            subset: stable
          weight: 90
        - destination:
            host: catalog-api.demo.svc.cluster.local
            subset: canary
          weight: 10
~~~

Đây là ví dụ cho môi trường có CRD Istio tương ứng và đường data plane phù hợp, không phải manifest cài mesh. Tỷ lệ cần được quan sát trên đủ traffic; không kỳ vọng cứ mười request là chính xác một request tới canary. [Bài thực hành traffic shifting của Istio](https://istio.io/latest/docs/tasks/traffic-management/traffic-shifting/)

Nếu chính sách mesh đã thực hiện đúng việc chia phiên bản, ứng dụng không cần thêm một bộ lọc instance rồi tự chia lại tỷ lệ ở phía client cho cùng mục tiêu.

### 5.2. Có mesh không đồng nghĩa có mọi tính năng L7

Trong Istio, sidecar và ambient có cấu trúc data plane khác nhau. Chế độ ambient có lớp xử lý L4; các khả năng L7 tương ứng cần đường qua thành phần như waypoint được cấu hình đúng. [Tài liệu các chế độ data plane của Istio](https://istio.io/latest/docs/overview/dataplane-modes/)

Vì vậy, bật mesh hoặc có mTLS không tự chứng minh đã có định tuyến theo header, chia request canary hay timeout theo từng HTTP request.

Nếu ứng dụng tự mã hóa end-to-end ở lớp mà proxy không giải mã, khả năng áp dụng một số chính sách L7 cũng cần được kiểm tra theo đường đi thực tế.

### 5.3. Gọi PodIP trực tiếp không có một kết quả cố định ở mọi mesh

Client tự chọn PodIP có thể làm thay đổi host, thông tin nhận diện dịch vụ hoặc cách route được áp dụng. Điều đó cần được đánh giá nếu muốn giữ chính sách theo tên Service.

Tuy nhiên, không được kết luận cứ gọi PodIP là chắc chắn thoát mesh hoặc mất mTLS. Traffic có thể vẫn bị data plane xử lý tùy chế độ và cấu hình. Phải xem route, upstream thực tế và bằng chứng bảo mật của kết nối.

Khi tầng mesh sở hữu lựa chọn backend, giữ cách gọi theo Service mà chính sách của nó được thiết kế để nhận diện thường giúp đường xử lý dễ giải thích hơn.

## 6. Vì sao lặp cùng chính sách ở nhiều tầng gây khó vận hành?

Nhiều tầng có thể phối hợp hợp lý: ứng dụng chọn dịch vụ nghiệp vụ, Gateway chọn route, mesh chọn backend, hạ tầng Service chuyển tiếp. Vấn đề xuất hiện khi nhiều tầng tự thực hiện cùng một quyết định mà không có hợp đồng rõ ràng.

### 6.1. Retry có thể khuếch đại request

Giả định:

~~~text
Ứng dụng: tối đa 2 lần thử tổng cộng
Gateway:  tối đa 2 lần thử cho mỗi lần ứng dụng gửi
Mesh:     tối đa 2 lần thử backend cho mỗi lần Gateway gửi
~~~

Trong điều kiện lỗi kích hoạt retry ở cả ba tầng:

~~~text
Số lần thử backend tối đa có thể là 2 × 2 × 2 = 8
~~~

Đây là ví dụ về số lần thử tổng cộng, không phải cách diễn giải mặc định của mọi thuộc tính có tên “retries”. Từng sản phẩm có thể tính số lần thử lại hoặc số lần thử tổng theo cách khác.

Tải nhân lên đặc biệt nguy hiểm với thao tác không idempotent. Cần phân công tầng sở hữu retry, loại lỗi được thử lại và ngân sách thời gian đầu cuối.

### 6.2. Timeout không thống nhất

Nếu caller chỉ chờ một giây nhưng tầng dưới vẫn tiếp tục thử nhiều lần trong ba giây, có thể phát sinh công việc không còn hữu ích cho caller.

Ứng dụng vẫn cần giới hạn chờ. Gateway/mesh vẫn cần giới hạn của chúng. Các giới hạn phải phối hợp theo deadline, thời gian truyền và hành vi hủy thực tế, thay vì sao chép một con số cho mọi tầng.

### 6.3. Nhiều nơi giữ danh sách hoặc loại backend

Readiness Kubernetes, cache discovery phía client và trạng thái loại đích lỗi ở proxy không nhất thiết cập nhật cùng lúc. Một tầng có thể vẫn chọn đích mà tầng khác đã hạn chế.

Nếu thêm client LoadBalancer chỉ để lặp lại chính sách đã đủ ở mesh, bạn có thêm một danh sách và một cơ chế cập nhật cần giải thích khi có sự cố.

### 6.4. Quyền đọc và chi phí tăng

Ứng dụng đọc Kubernetes API trực tiếp cần danh tính, RBAC và tài nguyên client/cache phù hợp. Nếu chỉ gọi DNS Service hoặc một URL Gateway, quyền đọc endpoint phục vụ riêng discovery có thể không cần nữa.

Điều này không có nghĩa mọi quyền Kubernetes đều được bỏ. Ứng dụng còn đọc ConfigMap, Secret hoặc thực hiện chức năng khác vẫn cần quyền tương ứng.

Mesh và Gateway cũng có chi phí của chúng. Khi chúng đã tồn tại và đáp ứng yêu cầu, tận dụng đúng chức năng có thể giảm phần cấu hình lặp; không có kết luận chung rằng xây thêm cả mesh luôn rẻ hơn một thư viện LoadBalancer.

## 7. Những trường hợp vẫn cần xem xét LoadBalancer phía ứng dụng

| Tình huống | Điều cần đánh giá thêm |
| --- | --- |
| Chọn shard theo dữ liệu nghiệp vụ | Chính sách có thể chuyển đúng sang hạ tầng hay phải nằm trong ứng dụng? |
| Chọn instance theo metadata không được tầng hiện có sử dụng | Nguồn metadata, độ mới và nơi áp dụng quyết định |
| Caller chạy ngoài phạm vi mesh | Đường truy cập và cơ chế chọn backend của caller đó |
| Giao thức hoặc kết nối dài không đạt yêu cầu với đường hiện tại | Đo phân phối, phục hồi và hỗ trợ của client/proxy |
| Cần một hành vi lựa chọn đích riêng chưa có ở Gateway/mesh | Lợi ích thực tế so với chi phí tích hợp thêm |
| Ứng dụng còn chức năng phải liệt kê từng instance | Có thể vẫn cần discovery dù request nghiệp vụ dùng DNS |

Không phải cứ có logic nghiệp vụ là phải chọn Pod trong ứng dụng. Chẳng hạn ứng dụng có thể đưa thông tin định tuyến đáng tin cậy vào request, rồi Gateway/mesh thực hiện lựa chọn theo một hợp đồng đã thiết kế.

Ngược lại, nếu quyết định cần dữ liệu mà tầng hạ tầng không có hoặc không thể sử dụng đúng, giữ quyết định trong ứng dụng có thể hợp lý. Khi đó ghi rõ phạm vi để tránh hai tầng cùng chọn theo hai chính sách mâu thuẫn.

## 8. Chuyển một đường gọi sang client thông thường có kiểm soát

Giả sử ứng dụng đang dùng `@LoadBalanced` nhưng muốn chuyển một đường gọi sang DNS hoặc Gateway đã có.

### Bước 1: Ghi đường đi hiện tại và hành vi phải giữ

Ghi lại URL logic, đích thực tế, cách lựa chọn cổng, timeout, retry, auth, tracing và policy theo metadata nếu có.

Không suy ra việc hai URL cùng trả HTTP 200 có nghĩa chúng có cùng chính sách bảo mật, định tuyến phiên bản và phục hồi.

### Bước 2: Chọn địa chỉ mà đường mới cần gọi

| Đường mới | Ví dụ địa chỉ | Điểm phải xác nhận |
| --- | --- | --- |
| Service trực tiếp | `http://catalog-api.demo.svc.cluster.local` | Cổng Service, DNS và network policy |
| Gateway | `http://api-gateway.platform.svc.cluster.local/catalog/products/42` | Route, tiền tố path và auth ở Gateway |
| Service qua mesh | Tên Service mà policy mesh nhận diện | Data plane, host/cổng và chính sách thực tế |

Không thay tên Service bằng IP của một Pod để né lỗi discovery. Cách đó tạo phụ thuộc vào vòng đời Pod và không tương đương mục tiêu chuyển sang hạ tầng ổn định.

### Bước 3: Tạo client hoặc builder riêng không gắn LoadBalancer

Dùng qualifier rõ ràng và giữ cấu hình transport, bảo mật, metrics cần thiết. Không chỉ đổi URL FQDN trong client vẫn gắn `@LoadBalanced`: host FQDN có thể tiếp tục bị hiểu thành service ID để tra discovery.

### Bước 4: Kiểm chứng với một phần traffic phù hợp

So sánh đường cũ và đường mới trên cùng loại request, contract và điều kiện tải. Đường mới phải đi qua thành phần được kỳ vọng, không chỉ thành công nhờ một fallback ngoài ý muốn.

### Bước 5: Thu gọn cấu hình còn thừa sau khi đã xác minh

Nếu toàn ứng dụng không còn cần Kubernetes discovery hoặc Kubernetes LoadBalancer, có thể đánh giá tắt các tính năng tương ứng:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        enabled: false
      loadbalancer:
        enabled: false
~~~

Chỉ áp dụng khi không có consumer khác còn cần chúng. Các cờ này không tự tháo mọi interceptor/filter trên client đã khai báo `@LoadBalanced` và không phải lệnh tắt mọi LoadBalancer trong toàn bộ hệ sinh thái Spring.

Gateway còn route `lb://` vẫn cần cơ chế tương ứng tại Gateway. Ứng dụng còn discovery cho chức năng khác cũng cần được giữ đúng.

Sau đó xem lại dependency và quyền đọc endpoint dành riêng cho đường đã bỏ. Không xóa cả nhóm dependency hoặc Role dùng chung khi ConfigMap, Secret hay chức năng khác vẫn sử dụng chúng.

### Bước 6: Giữ phương án quay lại rõ ràng

Ghi lại cấu hình/phiên bản có thể quay lại và điều kiện kích hoạt nếu đường mới không đạt yêu cầu. Quá trình chuyển đổi nên thay ít biến độc lập mỗi lần để có thể xác định nguyên nhân khi kết quả khác dự kiến.

## 9. Bằng chứng nào cho thấy tầng hiện có đã đủ?

Một phép đánh giá có ích cần cả hoạt động bình thường lẫn thay đổi backend.

| Kịch bản | Bằng chứng nên thu thập |
| --- | --- |
| Gọi API bình thường | Response đúng contract, route/upstream đúng và độ trễ đạt mục tiêu |
| Backend được thêm hoặc bớt | Kết nối/request mới thích ứng theo cơ chế dự kiến |
| Một Pod chưa Ready | Tập đích cho traffic mới phản ánh chính sách đã chọn sau thời gian cập nhật |
| Backend dừng có kiểm soát | Tỷ lệ lỗi và thời gian phục hồi nằm trong giới hạn |
| Kết nối HTTP được giữ lâu hoặc dùng HTTP/2 | Phân phối tải và hành vi phục hồi thực tế |
| Route canary thay đổi | Telemetry và backend xác nhận route/subset mong muốn |
| Lỗi tạm thời | Số lần thử và tổng thời gian không bị khuếch đại ngoài dự kiến |
| Bảo mật được yêu cầu | Danh tính, auth và bằng chứng TLS phù hợp với đường đi |

Số request và mức tải phải đủ đại diện cho nhu cầu. Không dùng một request thành công làm bằng chứng mọi tính năng đều đạt.

Một số lệnh đọc trong môi trường thực hành:

~~~sh
kubectl -n demo get service catalog-api -o yaml
kubectl -n demo get pods -l app=catalog-api -o wide
kubectl -n demo get endpointslices -l kubernetes.io/service-name=catalog-api -o yaml
~~~

Từ Pod công cụ có sẵn resolver và HTTP client phù hợp, kiểm tra DNS cùng URL Service. Việc phân giải tên từ máy cá nhân ngoài cụm có thể khác môi trường Pod, nên cần đo tại nơi caller thực sự chạy.

Với Gateway, xem route đang có hiệu lực và access log hoặc metric theo route. Với mesh, xem cấu hình data plane, upstream, phiên bản backend và telemetry của chính đường gọi.

Chú ý dữ liệu cache và thời điểm quan sát. Endpoint chuyển trạng thái không có nghĩa mọi lớp đã cập nhật ở cùng một mili giây.

### Ví dụ kết luận có đủ cơ sở

~~~text
Đường gọi:
order-service -> catalog-api qua DNS Service, trong namespace/mạng đã kiểm tra.

Yêu cầu:
API stateless, không chọn Pod theo metadata và không cần chia phiên bản
riêng tại caller.

Bằng chứng:
Contract đúng; tải mục tiêu đạt; thay thế backend được xử lý trong
giới hạn phục hồi; timeout và số lần thử đã được quan sát.

Quyết định:
Dùng HTTP client thông thường cho đường này.
Giữ discovery ở những consumer khác nếu chúng còn nhu cầu riêng.
~~~

Nếu yêu cầu thêm chia canary và mesh đã thực hiện đúng, bản kết luận cần ghi thêm route mesh cùng bằng chứng về phiên bản nhận traffic, thay vì chỉ ghi “có mesh”.

## 10. Giữ ranh giới tính năng trong Spring Cloud Kubernetes

Không cần LoadBalancer phía ứng dụng cho một đường gọi không có nghĩa toàn bộ Spring Cloud Kubernetes trở nên không cần thiết.

| Tính năng | Có thể vẫn hữu ích khi request dùng DNS/Gateway/mesh |
| --- | --- |
| ConfigMap | Cung cấp cấu hình ứng dụng theo cơ chế đã chọn |
| Secret | Cung cấp dữ liệu nhạy cảm theo cách triển khai phù hợp |
| Configuration Watcher | Thông báo hoặc hỗ trợ cập nhật cấu hình theo tích hợp thực tế |
| DiscoveryClient | Liệt kê instance cho chức năng quan sát hoặc logic khác nếu có |
| Spring Cloud LoadBalancer | Phục vụ những đường gọi khác còn cần chọn đích phía client |

Cập nhật ConfigMap chứa base URL cũng không bảo đảm một HTTP client đã build tự nhận URL mới. Cần cơ chế nạp lại cấu hình hoặc xây lại thành phần phù hợp; đây là vấn đề riêng với việc chọn tầng cân bằng tải.

Quyết định phù hợp là quyết định theo từng đường gọi: **biết tầng nào đang chọn đích, chứng minh tầng đó đáp ứng yêu cầu và chỉ giữ thêm cơ chế trong ứng dụng khi có một nhu cầu chưa được đáp ứng**.
