# Tái dựng URI sau khi thay tên dịch vụ bằng địa chỉ thật

Trong kiến trúc microservices, một ứng dụng thường biết **tên logic** của dịch vụ cần gọi, nhưng không cần biết địa chỉ từng bản sao đang chạy. Spring Cloud LoadBalancer cho phép code gọi **inventory-service** trong URI. Sau khi chọn một **ServiceInstance**, nó phải chuyển URI đó thành địa chỉ vật lý mà HTTP client có thể kết nối. Bước này được gọi là **tái dựng URI (URI reconstruction)**.

Ví dụ, Order Service tạo yêu cầu:

~~~text
GET http://inventory-service/api/v1/stock/BOOK-01?warehouse=HCM
~~~

LoadBalancer chọn một instance có host **10.20.1.17**, port **8082**, dùng HTTP. URI gửi xuống connector trở thành:

~~~text
GET http://10.20.1.17:8082/api/v1/stock/BOOK-01?warehouse=HCM
~~~

Chỉ tìm đúng instance là chưa đủ. Nếu tái dựng sai scheme, port, path hoặc query, request có thể gửi nhầm endpoint, không bắt tay TLS được hoặc làm thay đổi dữ liệu nghiệp vụ. Bài này đi sâu vào các quy tắc tái dựng URI của Spring Cloud LoadBalancer và cách chúng xuất hiện trong RestClient, WebClient, OpenFeign.

## 1. Phân biệt URI logic với URI vật lý

**URI logic** là địa chỉ do code nghiệp vụ sử dụng. Phần host là service ID, ví dụ **inventory-service**. Nó không nhất thiết là một DNS hostname có thể phân giải ngoài hệ thống.

~~~text
https://inventory-service:9000/api/items/BOOK-01?include=price#details
|-----| |---------------| |--| |----------------| |-----------| |-----|
scheme       host         port       path           query       fragment
~~~

**URI vật lý** chứa địa chỉ instance được chọn. Ví dụ:

~~~text
https://inventory-02.internal:8443/api/items/BOOK-01?include=price#details
~~~

| Thành phần | Nguồn dữ liệu sau khi chọn instance | Quy tắc cơ bản |
| --- | --- | --- |
| Scheme | URI gốc và thuộc tính instance | Có thể thay đổi theo getScheme() / isSecure() |
| Host | ServiceInstance.getHost() | Thay service ID bằng hostname/IP thật |
| Port | ServiceInstance.getPort() | Thay port của URI gốc bằng port instance |
| Path | URI request gốc | Giữ path; không tự thêm context path từ instance |
| Query | URI request gốc | Giữ tham số truy vấn đã được client tạo |
| Fragment | URI request gốc | Có thể còn trong URI object, nhưng không được gửi đến server bằng HTTP |

Tên logic trả lời câu hỏi **gọi dịch vụ nào**; ServiceInstance trả lời câu hỏi **gọi bản sao nào**. Khi một instance được thay thế trong registry, code nghiệp vụ tiếp tục gọi service ID như cũ, nhưng URI vật lý có thể thay đổi theo từng request.

## 2. Tái dựng URI nằm ở đâu trong chuỗi xử lý?

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ tạo URI logic"] --> B["RestClient / WebClient / OpenFeign"]
    B --> C["Tích hợp Spring Cloud LoadBalancer"]
    C --> D["Lấy service ID từ host"]
    D --> E["ServiceInstanceListSupplier"]
    E --> F["Discovery, cache, health và bộ lọc"]
    F --> G["LoadBalancer chọn một instance"]
    G --> H{"Tìm thấy instance?"}
    H -->|Có| I["Lấy host, port, scheme, isSecure"]
    I --> J["Tái dựng URI"]
    J --> K["HTTP connector gửi request"]
    H -->|Không| L["Báo lỗi không có instance"]
~~~

Luồng này có các bước cụ thể:

1. **HTTP client** tạo request từ URI template và các tham số.
2. **LoadBalancer integration** nhận diện service ID ở phần host của URI logic.
3. **LoadBalancer** lấy danh sách ServiceInstance từ supplier, sau đó chọn instance theo Round Robin hoặc chính sách định tuyến khác.
4. **URI reconstruction** tính scheme, host và port đích, kế thừa phần còn lại của URI gốc.
5. **HTTP connector** gửi method, headers và body tới địa chỉ đã được tái dựng.

Discovery và thuật toán chọn instance không phải thành phần sửa đường dẫn API. Spring Cloud LoadBalancer chọn **đích kết nối**; các phép rewrite path riêng của Gateway hoặc filter khác phải được xem xét độc lập.

Nếu không tìm được instance, request có thể thất bại ngay ở bước 3. Khi đó **chưa có URI vật lý hợp lệ** để gửi. Thay đổi thuật toán tái dựng URI sẽ không giải quyết được lỗi không tìm thấy instance.

## 3. Những thuộc tính ServiceInstance tham gia tái dựng

Spring Cloud Commons định nghĩa interface **org.springframework.cloud.client.ServiceInstance**. Các thuộc tính quan trọng:

| API | Ví dụ | Vai trò |
| --- | --- | --- |
| getServiceId() | inventory-service | Định danh logic để truy vấn danh sách instance |
| getHost() | 10.20.1.17 | Host thật của kết nối |
| getPort() | 8082 | Cổng thật của kết nối |
| isSecure() | false | Tín hiệu hỗ trợ tính scheme đích |
| getScheme() | null, http, https | Scheme do instance cung cấp nếu có |
| getUri() | http://10.20.1.17:8082 | URI đại diện instance; không thay cho URI request nghiệp vụ |

Ví dụ dựng một instance để kiểm chứng:

~~~java
ServiceInstance instance = new DefaultServiceInstance(
        "inventory-2",       // instance ID
        "inventory-service", // service ID
        "10.20.1.17",        // host
        8082,                // port
        false                // isSecure
);
~~~

Trong production, ServiceInstance thường được trả từ Eureka, Consul hoặc nguồn khám phá dịch vụ khác. Cần đăng ký **host, port và scheme nhất quán với cấu hình mạng/TLS của instance**, vì LoadBalancer dựa trên thông tin này để xây dựng đích thật.

**Phân biệt getUri() với URI sau tái dựng:** mã nguồn **LoadBalancerUriTools.reconstructURI(...)** sử dụng getHost(), getPort(), getScheme()/isSecure() cùng URI gốc. Nó không lấy một path tùy ý từ getUri() rồi tự ghép vào request. Nếu backend được triển khai dưới tiền tố /inventory, client hoặc một tầng định tuyến riêng phải đưa tiền tố đó vào path trước lúc gửi request.

## 4. LoadBalancerUriTools.reconstructURI hoạt động ra sao?

Trong Spring Cloud Commons có utility:

~~~java
URI physicalUri = LoadBalancerUriTools.reconstructURI(
        selectedInstance,
        originalUri
);
~~~

Trong implementation hiện hành, logic thực tế có thể diễn giải thành sáu bước:

1. Kiểm tra **selectedInstance** khác null; trường hợp null ném IllegalArgumentException.
2. Lấy host đích từ **getHost()**.
3. Xác định scheme: ưu tiên **getScheme()** nếu có; nếu null, sử dụng scheme gốc hoặc mặc định, có xét **isSecure()**.
4. Xác định port: dùng **getPort()** khi giá trị không âm; nếu âm, sử dụng port mặc định theo scheme.
5. Nếu host, port và scheme đều bằng URI gốc, trả URI ban đầu.
6. Nếu khác, tạo URI mới từ URI gốc bằng **UriComponentsBuilder**, chỉ thay scheme, host và port.

Mã giả để hiểu rõ thứ tự:

~~~java
// Pseudocode: deriveScheme, defaultPort, rebuildFromOriginal
// chỉ mô tả ý tưởng, không phải API công khai của Spring Cloud.
String host = selectedInstance.getHost();

String scheme = selectedInstance.getScheme() != null
        ? selectedInstance.getScheme()
        : deriveScheme(originalUri.getScheme(), selectedInstance.isSecure());

int port = selectedInstance.getPort() >= 0
        ? selectedInstance.getPort()
        : defaultPort(scheme);

URI result = rebuildFromOriginal(originalUri, scheme, host, port);
~~~

Thực tế ứng dụng có **@LoadBalanced** HTTP client thường không gọi utility thủ công. Spring Cloud sẽ thực hiện thay đổi URI trong interceptor hoặc exchange filter. Utility hữu ích khi muốn kiểm chứng riêng phép biến đổi hoặc tự triển khai một adapter tích hợp.

### 4.1. Bảng ví dụ URI trước và sau

Giả sử instance không khai báo scheme riêng (**getScheme() == null**):

| URI ban đầu | Instance đã chọn | URI sau tái dựng |
| --- | --- | --- |
| http://inventory-service/api/items/42 | 10.0.0.12:8081, secure=false | http://10.0.0.12:8081/api/items/42 |
| http://inventory-service:9000/api/items/42?lang=vi | inventory-02.internal:18080, secure=false | http://inventory-02.internal:18080/api/items/42?lang=vi |
| http://inventory-service/api/items/42 | inventory-03.internal:8443, secure=true | https://inventory-03.internal:8443/api/items/42 |
| https://inventory-service/api/items/42 | inventory-04.internal:8080, secure=false | https://inventory-04.internal:8080/api/items/42 |
| http://inventory-service/api/items/42 | 10.0.0.15, port=-1, secure=false | http://10.0.0.15:80/api/items/42 |

Lưu ý từ hai ví dụ quan trọng:

- **Port gốc không quyết định port đích:** URI gốc có port 9000 nhưng instance chọn port 18080, nên URI vật lý sử dụng 18080.
- **isSecure=false không tự đổi https thành http:** với implementation đang tham chiếu, nếu URI gốc là HTTPS và instance không khai báo scheme riêng, scheme HTTPS vẫn được giữ. Nếu backend thực tế chỉ mở HTTP, kết nối có thể thất bại ở TLS.

## 5. Scheme và port được suy ra như thế nào?

### 5.1. getScheme() được ưu tiên

Nếu instance có **getScheme() != null**, scheme đó được dùng trực tiếp. Một implementation tùy chỉnh có thể khai báo scheme cụ thể, ví dụ https.

Nếu metadata của instance cho **getScheme() = "http"** nhưng **isSecure() = true**, scheme riêng vẫn có độ ưu tiên cao hơn. Hai thuộc tính mâu thuẫn có thể khiến kết nối đi sai giao thức. Cần chuẩn hóa chúng từ nguồn discovery.

### 5.2. Khi getScheme() là null

Với DefaultServiceInstance, getScheme() thường là null. Theo mã nguồn LoadBalancerUriTools hiện hành:

- URI gốc không có scheme thì lấy mặc định **http**.
- Nếu **isSecure=true**, scheme **http** được nâng thành **https**.
- Nếu **isSecure=true**, scheme **ws** được nâng thành **wss**.
- Những scheme khác không nằm trong bảng nâng cấp được giữ nguyên.
- Khi **isSecure=false**, scheme gốc được giữ nguyên.

Hãy xem cờ secure như **dữ liệu định tuyến**. Nó không tự cấu hình chứng chỉ TLS, truststore hoặc kết nối đến port HTTPS. Cả client và service đích vẫn phải được triển khai với cấu hình TLS đúng.

### 5.3. Trường hợp instance không công bố port

Trong implementation hiện hành:

- **getPort() >= 0:** dùng port do instance công bố.
- **getPort() < 0** và scheme là **https:** dùng port 443.
- **getPort() < 0** với scheme khác: dùng port 80.

Đây là quy tắc fallback của helper, không phải bảo đảm rằng server đang lắng nghe đúng cổng đó. Registry nên công bố port rõ ràng trong môi trường có cổng tùy biến.

### 5.4. Vì sao không nên dùng lb:// tùy tiện?

Với RestClient và WebClient được tích hợp qua @LoadBalanced, ví dụ thông thường sử dụng URL:

~~~text
http://inventory-service/api/items/42
~~~

Scheme **lb://inventory-service** thường xuất hiện trong cấu hình route của **Spring Cloud Gateway**. Gateway có filter chuyên trách để diễn giải lb và xác định URI backend. Nếu tự truyền một URI lb:// thẳng vào LoadBalancerUriTools, helper không mặc định là một bộ chuyển mọi scheme tùy biến thành HTTP; kết quả có thể giữ scheme lb nếu instance không đưa ra scheme riêng.

Hãy phân biệt:

| Ngữ cảnh | Cách khai báo thường dùng | Ai xử lý? |
| --- | --- | --- |
| RestClient / WebClient có @LoadBalanced | http://inventory-service/api/items | LoadBalancer integration của HTTP client |
| OpenFeign dùng service ID | @FeignClient(name = "inventory-service") | Feign load-balancing adapter |
| Spring Cloud Gateway route | lb://inventory-service | Gateway LoadBalancer filter |

## 6. Điều gì xảy ra với path và query?

### 6.1. Giữ đúng đường dẫn tài nguyên

URI logic:

~~~text
http://inventory-service/api/v2/items/BOOK-01?warehouse=HCM&details=true
~~~

Nếu chọn instance **10.20.1.18:8083**, URI vật lý là:

~~~text
http://10.20.1.18:8083/api/v2/items/BOOK-01?warehouse=HCM&details=true
~~~

Các phần **/api/v2/items/BOOK-01** và **warehouse=HCM&details=true** không bị xóa hay đổi tên chỉ vì chọn instance khác. LoadBalancer không tự biến /api/v2 thành /v1, không tự strip prefix và không thay query parameter.

Nếu backend cần prefix khác, điều đó phải được thể hiện bằng URI logic hoặc một filter/router riêng có trách nhiệm sửa path.

### 6.2. Percent-encoding và dấu %

Một phần tử path có thể chứa ký tự đặc biệt. Ví dụ SKU là **BOOK/2026** nhưng dấu / thuộc giá trị SKU, không phải dấu phân tách path segment. URI có thể cần biểu diễn thành:

~~~text
http://inventory-service/api/items/BOOK%2F2026?city=Ho%20Chi%20Minh
~~~

Sau tái dựng đúng:

~~~text
http://10.20.1.18:8083/api/items/BOOK%2F2026?city=Ho%20Chi%20Minh
~~~

LoadBalancerUriTools dùng UriComponentsBuilder và có logic kiểm tra raw path, raw query, raw fragment chứa dấu % để nhận biết URI đã percent-encode. Nếu URI chỉ được encode một phần hoặc dữ liệu đầu vào không hợp lệ, một lần encode mới có thể khiến phần trăm bị mã hóa tiếp, ví dụ **%2F** thành **%252F**.

Đây là nguyên nhân của một số lỗi chỉ xuất hiện với ID chứa dấu /, khoảng trắng, dấu % hoặc query phức tạp. Nên:

1. Dùng URI builder/URI template của Spring thay vì nối chuỗi thủ công từ dữ liệu người dùng.
2. Encode theo đúng ngữ cảnh **path segment** hay **query parameter**.
3. Chỉ chọn một chiến lược encode nhất quán cho toàn bộ client.
4. Không encode sẵn một nửa tham số rồi để một tầng khác encode lại toàn bộ URI.
5. Kiểm tra raw path và raw query khi chẩn đoán double-encoding.

Tái dựng URI nhằm bảo toàn ý nghĩa path/query; nó không sửa được mọi URI đầu vào đã mã hóa sai từ trước.

### 6.3. Fragment

URI object có thể chứa fragment, ví dụ:

~~~text
http://inventory-service/api/items/42#description
~~~

UriComponentsBuilder có thể giữ fragment trong URI sau tái dựng. Tuy nhiên, fragment không được gửi trong HTTP request-target và server không thể dùng nó làm tham số định tuyến. Dữ liệu mà backend cần phải nằm ở path, query, header hoặc body theo contract API.

### 6.4. User info

Một URI dạng **http://user:password@inventory-service/...** chứa user info. Vì utility bắt đầu từ URI gốc, thành phần đó có thể được kế thừa. Không đặt password, access token hoặc credential trong URI: chúng dễ lọt vào log, metric và stack trace. Sử dụng header/cơ chế xác thực phù hợp.

## 7. Thực hành Java: tái dựng URI mà không cần chạy registry

Ví dụ sau sử dụng trực tiếp LoadBalancerUriTools để chỉ quan sát phép biến đổi:

~~~java
import java.net.URI;

import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerUriTools;

public class UriReconstructionExample {

    public static void main(String[] args) {
        URI original = URI.create(
                "http://inventory-service/api/items/BOOK%2F2026?warehouse=HCM");

        ServiceInstance instance = new DefaultServiceInstance(
                "inventory-2",
                "inventory-service",
                "10.20.1.17",
                8082,
                false);

        URI actual = LoadBalancerUriTools.reconstructURI(instance, original);

        System.out.println("Logical:  " + original);
        System.out.println("Physical: " + actual);
    }
}
~~~

Kết quả mong đợi:

~~~text
Logical:  http://inventory-service/api/items/BOOK%2F2026?warehouse=HCM
Physical: http://10.20.1.17:8082/api/items/BOOK%2F2026?warehouse=HCM
~~~

Đoạn mã này **không tự tìm hay chọn instance, không gửi request và không kiểm tra health**. Instance được đưa vào sẵn để kiểm chứng riêng phép tái dựng.

Nếu đổi instance thành secure=true và port 8443, có thể quan sát scheme được nâng từ http thành https.

## 8. RestClient sử dụng URI vật lý như thế nào?

Với Spring Cloud hỗ trợ RestClient, tạo builder có @LoadBalanced:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Sử dụng trong client nghiệp vụ:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    InventoryResponse getStock(String sku, String warehouse) {
        return restClient.get()
                .uri(
                        "http://inventory-service/api/stock/{sku}?warehouse={wh}",
                        sku,
                        warehouse)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

Ở đường gọi blocking:

1. RestClient dựng URI logic từ template.
2. Interceptor lấy service ID từ URI host.
3. BlockingLoadBalancerClient chọn ServiceInstance tương ứng.
4. Phương thức **LoadBalancerClient.reconstructURI()** tái dựng đích, với implementation **BlockingLoadBalancerClient** ủy quyền cho LoadBalancerUriTools.
5. HTTP client thực hiện request tới URI vật lý.

Ví dụ request tới service ID:

~~~text
GET http://inventory-service/api/stock/BOOK-01?warehouse=HCM
~~~

có thể thực sự đến:

~~~text
GET http://10.20.1.17:8082/api/stock/BOOK-01?warehouse=HCM
~~~

Nếu tạo RestClient thông thường bằng RestClient.create() mà không có LoadBalancer integration, việc dùng host inventory-service không tự động kích hoạt lựa chọn instance. Tùy môi trường, request có thể gặp lỗi DNS nếu hostname logic không tồn tại trong hệ thống phân giải tên.

## 9. WebClient tái dựng URI trong pipeline reactive

Spring Cloud cung cấp ReactorLoadBalancerExchangeFilterFunction để tích hợp chọn instance cho WebClient reactive:

~~~java
@Configuration(proxyBeanMethods = false)
class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Client nghiệp vụ:

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> getStock(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

Filter lấy service ID từ request URI, yêu cầu ReactiveLoadBalancer chọn instance, tái dựng URI và chuyển ClientRequest tiếp theo đến địa chỉ vật lý. Nếu discovery và HTTP stack đều reactive, luồng chọn instance có thể thực hiện không chặn event-loop.

Không gọi **block()** trong WebFlux handler để chờ LoadBalancer hay response. Tái dựng URI là một phép biến đổi nhẹ; thời gian chờ mạng vẫn cần được quản lý bằng timeout, retry có giới hạn và các cơ chế chịu lỗi khác.

## 10. OpenFeign giữ URI template và đổi endpoint vật lý

OpenFeign cho phép khai báo HTTP client bằng interface:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    InventoryResponse getStock(
            @PathVariable("sku") String sku,
            @RequestParam("warehouse") String warehouse);
}
~~~

Feign chuyển annotation và tham số thành request. Khi đã có Spring Cloud LoadBalancer và không cấu hình URL cố định, **FeignBlockingLoadBalancerClient** chọn instance rồi tái dựng URL trước khi gửi.

**Quan trọng:** nếu @FeignClient khai báo **url** cố định hoặc cấu hình URL cố định tương ứng, Feign có thể gọi thẳng endpoint đó và bỏ qua bước LoadBalancer. Muốn dùng tên logic, khai báo name và kiểm tra dependency spring-cloud-starter-loadbalancer.

RestClient, WebClient và OpenFeign có adapter khác nhau, nhưng mục tiêu chung là chuyển service ID thành đích kết nối thật trong khi vẫn giữ endpoint nghiệp vụ mà client đã xây dựng.

## 11. Những tầng khác có thể thay đổi URI

LoadBalancerUriTools xử lý scheme/host/port dựa trên ServiceInstance; các thành phần khác trong ứng dụng có thể sửa path/query:

- **URI template expansion:** thay {sku} bằng giá trị và encode theo quy tắc.
- **HTTP client interceptor/filter:** có thể thêm query parameter, header hoặc sửa URL.
- **API Gateway:** strip prefix, rewrite path, chọn route và backend.
- **Reverse proxy/ingress:** có thể thay path hoặc định tuyến dựa trên header.
- **Service mesh:** có thể bổ sung một tầng route hoặc proxy bên ngoài process.

Ví dụ:

~~~text
URI logic:        http://inventory-service/v1/items/42
Gateway rewrite:  /items/42
Chọn instance:    inventory-02.internal:8080
URI tới backend:  http://inventory-02.internal:8080/items/42
~~~

Đường dẫn thay đổi vì bộ lọc rewrite, còn LoadBalancer cung cấp đích instance. Khi dùng Spring Cloud Gateway với lb://, cần chú ý thứ tự giữa LoadBalancer filter và các filter sửa path như StripPrefix hoặc SetPath.

## 12. Hệ quả liên quan đến TLS, header và retry

### 12.1. Scheme sai có thể làm lỗi TLS

Nếu registry đăng ký secure=true nhưng service chỉ mở HTTP, URI sau tái dựng có thể dùng https và kết nối không thành công. Ngược lại, URI gốc dùng https có thể giữ nguyên scheme ngay cả với instance secure=false nếu không có getScheme riêng.

Với TLS, hostname vật lý cũng liên quan đến **certificate hostname verification** và **SNI**. Nếu chứng chỉ chỉ đúng với service ID logic nhưng HTTP client thực sự kết nối bằng một hostname khác, cần xem lại chiến lược chứng chỉ và cách proxy kết thúc TLS. Không tắt xác minh certificate để che dấu lỗi cấu hình.

### 12.2. Host header và HTTP authority

URI vật lý và HTTP Host/:authority có liên quan, nhưng adapter/proxy có thể ghi đè header. HTTP client thường lấy authority từ URI đích; tuy nhiên, không nên khẳng định mọi request sẽ giữ service ID logic hay luôn gửi host vật lý. Nếu backend dựa vào virtual host, hãy kiểm tra request thực tế ở phía nhận.

### 12.3. Retry có thể tạo URI vật lý khác

Request đầu có thể đến **10.20.1.17:8082**, còn lần retry được LoadBalancer chuyển sang **10.20.1.18:8083**. Khi đó mỗi lần thử có URI vật lý khác, dù service ID, path và dữ liệu nghiệp vụ giống nhau.

Với POST/PUT/PATCH có side effect, phải áp dụng hợp đồng retry an toàn. Một lần timeout không chứng minh server chưa hoàn thành nghiệp vụ. Với thao tác không tự lũy đẳng, cần idempotency key hoặc cách khử trùng tương ứng.

### 12.4. Instance cũ vẫn có thể được chọn

Tái dựng URI có thể đúng hoàn toàn về mặt cú pháp nhưng trỏ tới instance đã chết vì registry hoặc cache chưa cập nhật. Cần kiểm tra discovery, health check và TTL cache. Bản thân LoadBalancerUriTools không mở kết nối để xác minh health.

## 13. Chẩn đoán lỗi theo đúng từng tầng

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| UnknownHostException với service ID | Dùng HTTP client không tích hợp LoadBalancer | Kiểm tra builder @LoadBalanced và adapter/dependency |
| Không tìm thấy instance | Discovery hoặc supplier trả danh sách rỗng | Kiểm tra service ID, registry, cache, health filter |
| Kết nối sai port | Port trong registry sai | Kiểm tra getPort() của instance được chọn |
| SSLHandshakeException | Scheme/certificate/TLS không nhất quán | Kiểm tra getScheme(), isSecure(), SNI, truststore |
| Backend 404 dù đã chọn đúng instance | Path sai hoặc bị rewrite bởi filter/proxy | So sánh URI logic, URI sau filter và route backend |
| Query xuất hiện %252F hoặc %2520 | Encode nhiều lần hoặc đầu vào encode một phần | Kiểm tra raw path/query và URI builder |
| Retry chuyển sang instance khác rồi lỗi | Cache hoặc state cục bộ giữa instance không đồng nhất | Kiểm tra health, discovery, session, idempotency |
| Backend thấy Host header lạ | Adapter/proxy/filter thay đổi authority | Ghi nhận header ở phía server và kiểm tra adapter |

Thứ tự điều tra nên là **URI logic → service ID → danh sách instance → instance đã chọn → URI tái dựng → request trên mạng → response**. Cách này giúp xác định lỗi trước hay sau bước tái dựng.

## 14. Thực hành kiểm chứng URI reconstruction

### 14.1. Thử với hai bản sao local

Giả sử có hai instance inventory-service cùng cung cấp GET /api/stock/{sku}:

| Instance | Địa chỉ | Response trả về |
| --- | --- | --- |
| Inventory A | http://localhost:8081 | instanceId=inventory-a |
| Inventory B | http://localhost:8082 | instanceId=inventory-b |

Cấu hình SimpleDiscoveryClient:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Thực hành tuần tự:

1. Tạo @LoadBalanced RestClient.Builder trong ứng dụng caller đã có spring-cloud-starter-loadbalancer.
2. Gọi nhiều lần URI logic **http://inventory-service/api/stock/BOOK-01?warehouse=HCM**.
3. Kiểm tra response có instanceId thay đổi theo chính sách chọn instance, thường là Round Robin nếu giữ mặc định.
4. Kiểm tra backend nhận path **/api/stock/BOOK-01** và query **warehouse=HCM** ở cả hai instance.
5. Thử URI có path segment chứa ký tự đặc biệt; xác nhận không có hiện tượng double-encoding.
6. Thử một endpoint HTTPS được cấu hình thực sự và xác nhận scheme của URI vật lý phù hợp.
7. Dừng một instance rồi quan sát thời gian cập nhật của discovery/cache/health. Request thất bại trong cửa sổ cache cũ không nhất thiết là lỗi tái dựng URI.

**SimpleDiscoveryClient** hữu ích cho kiểm thử local bằng danh sách tĩnh; nó không tự phát hiện tiến trình mới hoặc mất và không thay thế registry có cập nhật động.

### 14.2. Phép kiểm tra riêng port và query

Không cần server đang chạy để kiểm tra phép tái dựng thuần túy:

~~~java
URI original = URI.create(
        "http://inventory-service:9000/api/items/42?lang=vi");

ServiceInstance instance = new DefaultServiceInstance(
        "inventory-b", "inventory-service", "localhost", 8082, false);

URI result = LoadBalancerUriTools.reconstructURI(instance, original);

URI expected = URI.create(
        "http://localhost:8082/api/items/42?lang=vi");

if (!expected.equals(result)) {
    throw new IllegalStateException("Unexpected URI: " + result);
}
~~~

Kết quả xác nhận port 9000 trong URI logic được thay bằng port 8082 của instance; path và query không đổi. Có thể mở rộng phép kiểm tra với instance secure=true, URI gốc https, giá trị path encoded hoặc port -1.

## 15. Checklist

- [ ] URI logic có service ID đúng ở phần host.
- [ ] HTTP client đã được tích hợp @LoadBalanced hoặc adapter Feign tương ứng.
- [ ] Host, port, getScheme() và isSecure() của instance nhất quán.
- [ ] Port của URI gốc được thay bằng port của instance.
- [ ] Path, query và dữ liệu nghiệp vụ vẫn đúng sau khi chọn instance.
- [ ] Các tham số có ký tự đặc biệt được encode đúng ngữ cảnh và chỉ một lần.
- [ ] Không giả định getUri() của instance tự thêm context path vào request.
- [ ] Phân biệt URL http://service-id của client với lb:// của Gateway.
- [ ] Kiểm tra TLS, SNI, chứng chỉ và hostname verification khi scheme đổi.
- [ ] Retry có giới hạn và có idempotency khi thao tác có side effect.
- [ ] Chỉ log URI đã loại bỏ token, credential và dữ liệu nhạy cảm.

## 16. Kết luận

**Tái dựng URI là cầu nối từ việc chọn ServiceInstance sang kết nối HTTP thật.** Spring Cloud LoadBalancer dựa vào thông tin của instance để thay scheme, host, port, đồng thời kế thừa path/query của URI logic. Khi có lỗi, cần phân biệt lỗi không tìm thấy instance, lỗi biến đổi URI và lỗi giao tiếp với backend.

Hiểu rõ các trường hợp secure, cổng mặc định, percent-encoding và các filter rewrite giúp ứng dụng phối hợp RestClient, WebClient và OpenFeign ổn định hơn khi triển khai nhiều bản sao.

## 17. Tài liệu tham khảo

- [Spring Cloud LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): tích hợp HTTP clients và lựa chọn ServiceInstance.
- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): service discovery và client-side load balancing.
- [LoadBalancerUriTools.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerUriTools.java): hiện thực xác định scheme, host, port và xử lý encoded URI.
- [BlockingLoadBalancerClient.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/blocking/client/BlockingLoadBalancerClient.java): đường tích hợp blocking và reconstructURI.
- [ServiceInstance.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java): contract dữ liệu instance.
- [Spring Cloud Gateway LoadBalancer Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/loadbalancer.html): cú pháp lb:// và thứ tự filter route.
