# Vai trò của ElasticsearchClient, transport và lớp HTTP

Trong ứng dụng Java, việc gọi Elasticsearch không chỉ là tạo một object client rồi gửi truy vấn. Phía sau API mà lập trình viên sử dụng còn có một tầng transport để chuyển request thành dữ liệu truyền đi, một HTTP client để quản lý kết nối và một giao thức HTTP để giao tiếp với Elasticsearch server.

Với Elasticsearch Java API Client hiện đại, ba thành phần cần phân biệt là:

- **ElasticsearchClient:** API Java cấp cao, có kiểu dữ liệu rõ ràng và các phương thức tương ứng với API của Elasticsearch như search, index, update, delete và quản lý index.
- **ElasticsearchTransport:** tầng trung gian thực thi request, chuyển đổi request/response giữa mô hình Java và định dạng JSON, đồng thời kết nối API client với một cơ chế truyền tải cụ thể.
- **HTTP client và lớp HTTP:** chịu trách nhiệm gửi HTTP request qua mạng đến REST API của Elasticsearch, nhận HTTP response và xử lý các vấn đề kết nối như timeout, TLS, xác thực và connection pooling.

Các thành phần này phối hợp với nhau. ElasticsearchClient cung cấp API cho mã ứng dụng; transport nối API đó với cơ chế truyền tải; HTTP client thực hiện giao tiếp mạng; Elasticsearch server tiếp nhận và xử lý request.

## 1. Nhìn tổng thể đường đi của một request

Một ứng dụng Spring Boot có thể sử dụng Elasticsearch thông qua repository, ElasticsearchOperations hoặc gọi ElasticsearchClient trực tiếp. Khi một truy vấn được gửi bằng Java API Client, luồng điển hình như sau:

    Service
       |
       v
    Spring Data Elasticsearch
    Repository / ElasticsearchOperations
       |
       v
    ElasticsearchClient
    Java API có kiểu
       |
       v
    ElasticsearchTransport
    Điều phối và chuyển đổi dữ liệu
       |
       v
    RestClientTransport
    Bộ chuyển tiếp sang low-level client
       |
       v
    RestClient
    Quản lý HTTP request và kết nối
       |
       v
    HTTP / HTTPS
       |
       v
    Elasticsearch REST API
       |
       v
    Elasticsearch node

Response đi ngược từ server về HTTP client, qua transport để được giải tuần tự hóa thành kiểu response Java, rồi trả về ElasticsearchClient và cuối cùng đến service.

Sơ đồ trên mô tả cấu hình phổ biến dùng RestClientTransport. ElasticsearchTransport là abstraction của tầng transport; ứng dụng có thể dùng implementation khác nếu kiến trúc yêu cầu. Không nên đồng nhất ElasticsearchClient với RestClient: chúng phục vụ hai mức API khác nhau.

## 2. ElasticsearchClient: API Java mà ứng dụng gọi

ElasticsearchClient thuộc Elasticsearch Java API Client, thường được sử dụng qua package co.elastic.clients.elasticsearch. Đây là client cấp cao cung cấp các phương thức Java tương ứng với những API của Elasticsearch.

Ví dụ, ứng dụng muốn tìm sản phẩm có tên liên quan đến từ khóa coffee:

    SearchResponse<Product> response = elasticsearchClient.search(
        request -> request
            .index("products")
            .query(query -> query
                .match(match -> match
                    .field("name")
                    .query("coffee")
                )
            ),
        Product.class
    );

Đoạn mã thể hiện các đặc điểm của ElasticsearchClient:

- Lập trình viên gọi phương thức Java search thay vì tự tạo URL và HTTP body.
- Request được xây dựng bằng các builder và kiểu dữ liệu của Java API Client.
- Response được giải tuần tự hóa thành SearchResponse<Product>.
- Kiểu Product được cung cấp để client ánh xạ phần document trong response thành object Java.

Client cung cấp API cho nhiều nhóm chức năng:

| Nhóm API | Ví dụ thao tác |
|---|---|
| Document | index, get, update, delete |
| Search | search, count, explain |
| Bulk | gửi nhiều thao tác document trong một request |
| Index management | create, get, update mapping, delete index |
| Cluster và các API khác | gọi những endpoint được client phiên bản đó hỗ trợ |

ElasticsearchClient không phải Elasticsearch server, không lưu dữ liệu và cũng không tự tạo một cluster. Nó chỉ là thành phần phía ứng dụng dùng để gọi API của server.

### Client cấp cao và REST client cấp thấp

Elasticsearch Java API Client được xây dựng phía trên một transport. Trong cấu hình REST thông dụng, transport kết nối với low-level RestClient.

Low-level RestClient làm việc gần HTTP hơn: nó gửi request đến endpoint và nhận response HTTP. Nếu sử dụng riêng low-level client, mã ứng dụng phải tự quản lý nhiều chi tiết như đường dẫn endpoint, HTTP method, body JSON và cách đọc response.

ElasticsearchClient cung cấp abstraction theo API Elasticsearch. Ví dụ, lập trình viên gọi search và tạo query bằng các kiểu Java thay vì tự tạo POST request đến endpoint search.

| Tiêu chí | ElasticsearchClient | Low-level RestClient |
|---|---|---|
| Mức API | API Elasticsearch có kiểu | HTTP/REST ở mức thấp |
| Request | Builder và kiểu request Java | Request HTTP, path, method, entity/body |
| Response | Kiểu response theo API Elasticsearch | HTTP response |
| JSON | Transport và mapper xử lý | Ứng dụng hoặc lớp gọi tự xử lý |
| Mục đích | Gọi API Elasticsearch thuận tiện, có kiểu | Điều khiển HTTP request ở mức thấp |

Không nên nhầm low-level RestClient với Elasticsearch REST API. REST API là tập endpoint do Elasticsearch server cung cấp; RestClient là thư viện Java dùng để gửi HTTP request đến những endpoint đó.

## 3. ElasticsearchTransport: tầng nối API và giao tiếp mạng

ElasticsearchTransport là abstraction trung tâm giữa ElasticsearchClient và cơ chế truyền tải cụ thể. Java API Client không cần gắn cứng toàn bộ logic API với một thư viện HTTP duy nhất. Thay vào đó, client gửi request qua transport.

Transport đảm nhiệm các công việc chính:

1. Nhận request được tạo từ ElasticsearchClient.
2. Chuyển đổi request thành dạng mà cơ chế truyền tải có thể gửi đi.
3. Sử dụng JSON mapper để tuần tự hóa dữ liệu Java thành JSON khi cần.
4. Thực thi request qua transport implementation.
5. Đọc HTTP response và giải tuần tự hóa JSON thành kiểu response Java.
6. Chuyển lỗi thực thi hoặc lỗi response về phía client gọi API.

Có thể xem transport là ranh giới giữa API Java có kiểu và cách request thực sự được truyền đến server.

### JSON mapper làm gì?

Elasticsearch Java API Client sử dụng mô hình JSON-P để biểu diễn và xử lý JSON. Khi ứng dụng muốn ánh xạ document thành một class Java riêng, transport cần một mapper phù hợp để chuyển đổi dữ liệu.

Một mapper thường dùng là JacksonJsonpMapper. Nó tích hợp Jackson với cơ chế JSON-P của client, giúp ánh xạ các class Java của ứng dụng sang JSON và ngược lại.

Ví dụ, với class:

    public class Product {
        private String id;
        private String name;
        private double price;

        // constructors, getters and setters
    }

Khi index một Product, mapper chuyển object thành JSON để gửi trong request. Khi search trả về document, mapper đọc JSON và tạo object Product tương ứng.

Mapper không quyết định query có đúng hay không và cũng không thực hiện tìm kiếm. Nó chỉ xử lý việc biểu diễn dữ liệu giữa Java và JSON. Việc document được lưu, phân tích, lập chỉ mục và tìm kiếm vẫn do Elasticsearch server thực hiện.

### RestClientTransport

RestClientTransport là một implementation của ElasticsearchTransport dành cho low-level RestClient. Nó nối Java API Client với REST client hiện có của Elasticsearch.

Trong cấu hình này:

- ElasticsearchClient cung cấp các API Java cấp cao.
- RestClientTransport chuyển request của Java API Client sang request mà RestClient có thể thực thi, đồng thời chuyển response trở lại.
- RestClient thực hiện giao tiếp HTTP.
- JacksonJsonpMapper hoặc mapper tương thích xử lý chuyển đổi JSON.

RestClientTransport thường được khởi tạo cùng một RestClient và một JSON mapper. Đây là cách triển khai phổ biến trong ứng dụng Java và trong cấu hình Spring Boot/Spring Data Elasticsearch hiện đại.

## 4. Lớp HTTP: nơi request thực sự đi qua mạng

Elasticsearch cung cấp REST API qua HTTP. Java client gửi request đến các endpoint của server, thường dùng JSON làm định dạng body.

Một request search ở mức HTTP có thể được biểu diễn khái quát như sau:

    POST /products/_search
    Content-Type: application/json

    {
      "query": {
        "match": {
          "name": "coffee"
        }
      }
    }

Khi sử dụng ElasticsearchClient, lập trình viên không cần tự viết HTTP request này trong trường hợp thông thường. Client và transport xây dựng request tương ứng rồi giao cho RestClient thực hiện.

Lớp HTTP có những trách nhiệm không thuộc logic tìm kiếm:

- **Địa chỉ đích:** host, port và path prefix nếu hệ thống triển khai sử dụng.
- **HTTP method và path:** ví dụ POST đến endpoint search hoặc PUT đến endpoint index/document.
- **Header:** Content-Type, Accept, Authorization và những header cần thiết khác.
- **TLS/HTTPS:** mã hóa dữ liệu truyền trên mạng và xác minh chứng thư theo cấu hình.
- **Timeout:** giới hạn thời gian chờ kết nối hoặc chờ response.
- **Connection pooling:** tái sử dụng kết nối để tránh tạo kết nối mới cho mọi request.
- **Node selection và retry:** lựa chọn node đích và xử lý một số tình huống lỗi theo chính sách của REST client.

Các thiết lập cụ thể phụ thuộc phiên bản REST client và cấu hình triển khai. Không phải mọi lỗi đều có thể retry an toàn: request đọc thường dễ retry hơn request ghi có tác động nghiệp vụ nếu trạng thái thực thi chưa rõ. Ứng dụng cần xem xét tính idempotent và chính sách retry của từng thao tác.

### HTTP, HTTPS và TCP

Các lớp giao tiếp có quan hệ như sau:

    ElasticsearchClient
          |
          v
    Transport và HTTP client
          |
          v
    HTTP request / response
          |
          v
    TLS nếu dùng HTTPS
          |
          v
    TCP connection
          |
          v
    Mạng và Elasticsearch node

HTTP định nghĩa cách client và server trao đổi request/response. HTTPS bổ sung TLS để mã hóa và xác thực kết nối. TCP là tầng vận chuyển bên dưới kết nối HTTP trong mô hình thông dụng.

TLS không thay thế xác thực người dùng của Elasticsearch. TLS bảo vệ kênh truyền và xác minh máy chủ theo cấu hình; thông tin xác thực như Basic Authentication hoặc API key vẫn được gửi theo cơ chế authentication của Elasticsearch qua header HTTP.

## 5. Cấu hình các thành phần bằng Java thuần

Ví dụ dưới đây tạo một low-level RestClient, bọc nó bằng RestClientTransport, rồi tạo ElasticsearchClient:

    RestClient restClient = RestClient.builder(
        new HttpHost("localhost", 9200, "http")
    ).build();

    ElasticsearchTransport transport = new RestClientTransport(
        restClient,
        new JacksonJsonpMapper()
    );

    ElasticsearchClient elasticsearchClient =
        new ElasticsearchClient(transport);

Các import chính trong ví dụ:

    import co.elastic.clients.elasticsearch.ElasticsearchClient;
    import co.elastic.clients.json.jackson.JacksonJsonpMapper;
    import co.elastic.clients.transport.ElasticsearchTransport;
    import co.elastic.clients.transport.rest_client.RestClientTransport;
    import org.apache.http.HttpHost;
    import org.elasticsearch.client.RestClient;

Sau khi khởi tạo, ứng dụng có thể dùng elasticsearchClient để gọi các API như search, index hoặc delete. Khi ứng dụng tự quản lý vòng đời client, cần đóng tài nguyên HTTP client khi ứng dụng dừng:

    restClient.close();

RestClient quản lý tài nguyên kết nối và cần được đóng đúng vòng đời. Trong ứng dụng Spring, nếu client được tạo và quản lý bởi Spring container, nên để container quản lý việc hủy bean theo cấu hình; service chỉ inject và sử dụng client, không tự đóng client dùng chung sau mỗi request.

### Ví dụ gọi search sau khi khởi tạo

    SearchResponse<Product> response = elasticsearchClient.search(
        search -> search
            .index("products")
            .query(query -> query
                .match(match -> match
                    .field("name")
                    .query("coffee")
                )
            ),
        Product.class
    );

    for (Hit<Product> hit : response.hits().hits()) {
        Product product = hit.source();
        // Process product
    }

Lệnh search đi qua ElasticsearchClient, transport, RestClient và HTTP trước khi Elasticsearch server xử lý. Khi response quay về, document JSON được ánh xạ thành Product theo mapper đã cấu hình.

## 6. Cấu hình trong Spring Boot và Spring Data Elasticsearch

Trong ứng dụng Spring Boot, cách thông dụng là dùng starter:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
    }

Với cấu hình tự động của Spring Boot, địa chỉ cluster có thể khai báo trong application.yml:

    spring:
      elasticsearch:
        uris: http://localhost:9200

Spring Boot và Spring Data Elasticsearch phối hợp tạo các bean cần thiết cho kết nối và thao tác dữ liệu. Ở các dòng Spring Data Elasticsearch hiện đại, ElasticsearchClient được dùng ở tầng giao tiếp; ElasticsearchOperations/ElasticsearchTemplate cung cấp abstraction cho ứng dụng.

Service có thể inject ElasticsearchClient nếu thật sự cần gọi API Java trực tiếp:

    @Service
    public class ProductAdminService {

        private final ElasticsearchClient client;

        public ProductAdminService(ElasticsearchClient client) {
            this.client = client;
        }

        public void deleteProduct(String id) throws IOException {
            client.delete(request -> request
                .index("products")
                .id(id)
            );
        }
    }

Trong trường hợp CRUD hoặc truy vấn có thể diễn đạt qua repository, nên cân nhắc dùng repository. Khi cần truy vấn phức tạp nhưng vẫn muốn Spring Data quản lý mapping entity, ElasticsearchOperations là abstraction phù hợp. Gọi ElasticsearchClient trực tiếp hữu ích khi cần API cụ thể hoặc muốn kiểm soát request ở mức Java API Client.

Nếu cung cấp cấu hình client tùy chỉnh, cần bảo đảm Spring Data, ElasticsearchClient, transport và REST client sử dụng cùng cấu hình kết nối. Không nên vô tình tạo hai bộ client độc lập với địa chỉ, chứng thực hoặc TLS khác nhau rồi inject lẫn lộn trong cùng ứng dụng.

### Xác thực và TLS

Môi trường thật thường yêu cầu HTTPS và xác thực. Cấu hình cần quan tâm:

- URI dùng HTTPS và hostname đúng với chứng thư máy chủ.
- Trust material hoặc certificate được cấu hình theo chính sách bảo mật của môi trường.
- Username/password hoặc API key được truyền qua cơ chế authentication phù hợp.
- Timeout, proxy và path prefix được đặt theo hạ tầng triển khai.
- Bí mật được cung cấp qua secret hoặc biến môi trường, không commit trực tiếp vào source control.

Không nên tắt xác minh chứng thư TLS chỉ để làm cho kết nối chạy được. Cần cấu hình CA hoặc truststore đúng với chứng thư của Elasticsearch.

## 7. Xử lý lỗi ở từng tầng

Khi request thất bại, cần xác định lỗi xuất hiện ở tầng nào vì cách khắc phục khác nhau.

| Tầng | Ví dụ lỗi | Hướng kiểm tra |
|---|---|---|
| Cấu hình client | Sai host, port, path prefix | Kiểm tra URI và cấu hình môi trường |
| Kết nối HTTP | Connection refused, timeout, DNS | Kiểm tra mạng, firewall, node và timeout |
| TLS | Certificate không tin cậy, hostname không khớp | Kiểm tra certificate, CA và hostname |
| Authentication | HTTP 401 hoặc 403 | Kiểm tra credentials, API key và quyền |
| Elasticsearch API | Index không tồn tại, mapping/query không hợp lệ | Đọc status và error response của server |
| JSON mapping | Không chuyển được response thành class Java | Kiểm tra mapper, kiểu field và dữ liệu JSON |

Với lời gọi đồng bộ, lỗi I/O ở tầng giao tiếp thường được biểu diễn qua IOException. Các lỗi API của Elasticsearch có thể được client biểu diễn bằng exception chứa thông tin response và nguyên nhân từ server. Cần xem exception cụ thể của phiên bản client đang dùng thay vì gom mọi lỗi thành một loại.

Không nên retry mù quáng mọi exception. Ví dụ, timeout khi gửi thao tác ghi có thể khiến client không biết server đã thực hiện thao tác hay chưa. Trước khi retry, cần đánh giá thao tác có idempotent không và có cơ chế định danh hoặc kiểm soát phiên bản để tránh ghi lặp hay không.

## 8. Tái sử dụng client và quản lý vòng đời

Một ứng dụng thường tạo client ở cấp ứng dụng và tái sử dụng cho nhiều request. Không nên tạo RestClient và ElasticsearchClient mới cho mỗi lần gọi repository hoặc mỗi HTTP request đến ứng dụng.

Lý do:

- HTTP client quản lý connection pool và tài nguyên mạng.
- Tái sử dụng client giảm chi phí thiết lập kết nối.
- Cấu hình timeout, TLS và xác thực được quản lý tập trung.
- Vòng đời tài nguyên dễ kiểm soát hơn khi client do Spring container quản lý.

Trong Spring, hãy inject bean client vào service cần dùng. Không đóng client dùng chung trong phương thức service sau khi hoàn tất một truy vấn. Việc đóng tài nguyên thuộc về vòng đời ứng dụng hoặc bean sở hữu client.

Đồng thời, không nên chia sẻ một client được cấu hình cho cluster hoặc danh tính bảo mật này sang nghiệp vụ cần cluster khác nếu điều đó làm sai ranh giới bảo mật. Khi cần nhiều cluster, mỗi cấu hình kết nối cần có bean và vòng đời rõ ràng.

## 9. Phân biệt trách nhiệm của từng thành phần

| Thành phần | Câu hỏi mà nó giải quyết | Trách nhiệm chính |
|---|---|---|
| Spring Data Elasticsearch | Ứng dụng Spring thao tác dữ liệu theo abstraction nào? | Repository, operations, mapping entity và tích hợp Spring |
| ElasticsearchClient | Gọi API Elasticsearch bằng Java như thế nào? | API request/response có kiểu |
| ElasticsearchTransport | Chuyển request/response giữa Java API và phương thức truyền tải ra sao? | Điều phối thực thi và chuyển đổi dữ liệu |
| RestClientTransport | Kết nối Java API Client với low-level RestClient thế nào? | Adapter giữa transport và REST client |
| RestClient | Gửi request HTTP và quản lý kết nối thế nào? | HTTP request, node, connection và response |
| HTTP/HTTPS | Dữ liệu được trao đổi qua giao thức nào? | Request/response, header, body và bảo mật kênh truyền |
| Elasticsearch REST API/server | Request được xử lý ở đâu? | Thực thi search, indexing, update và quản lý dữ liệu |

Việc tách trách nhiệm này giúp khoanh vùng lỗi nhanh hơn. Nếu query DSL sai, cần xem request và mapping. Nếu không kết nối được, cần xem HTTP client, TLS, mạng và địa chỉ. Nếu JSON không ánh xạ được thành object, cần kiểm tra mapper và cấu trúc document.

## 10. Những nhầm lẫn thường gặp

### Cho rằng ElasticsearchClient tự gửi HTTP mà không cần transport

ElasticsearchClient cung cấp API cấp cao. Request cần được thực thi qua ElasticsearchTransport và một transport implementation. Với cấu hình REST thông dụng, implementation đó là RestClientTransport.

### Nhầm ElasticsearchTransport với HTTP client

Transport là abstraction ở tầng Java API Client, có trách nhiệm điều phối và chuyển đổi request/response. RestClient là HTTP client thực hiện giao tiếp mạng. RestClientTransport là adapter nối hai tầng này.

### Nhầm RestClient với ElasticsearchClient

RestClient làm việc ở mức HTTP/REST thấp hơn. ElasticsearchClient cung cấp API theo nghiệp vụ Elasticsearch với kiểu request và response. Một RestClient có thể được dùng bên dưới một ElasticsearchClient thông qua RestClientTransport.

### Cho rằng JacksonJsonpMapper thực hiện mapping index

JacksonJsonpMapper chuyển đổi dữ liệu giữa object Java và JSON. Nó không tạo index mapping trên Elasticsearch server và không quyết định analyzer, field type hoặc cách server tìm kiếm. Mapping index là cấu hình phía Elasticsearch, có thể được quản lý qua API hoặc metadata của Spring Data.

### Tạo client mới cho mỗi thao tác

Việc tạo client liên tục gây lãng phí tài nguyên và làm mất lợi ích của connection pooling. Hãy tái sử dụng client dùng chung trong vòng đời ứng dụng.

### Đóng client sau mỗi lần gọi service

Nếu client được chia sẻ bởi nhiều service hoặc request, đóng nó sau một lần gọi sẽ khiến các thao tác tiếp theo thất bại. Chỉ thành phần sở hữu tài nguyên mới chịu trách nhiệm đóng nó khi vòng đời kết thúc.

### Nghĩ HTTPS tự động cung cấp quyền truy cập

HTTPS mã hóa kênh truyền và hỗ trợ xác minh máy chủ. Nó không tự cấp quyền truy cập vào index. Elasticsearch vẫn áp dụng authentication và authorization theo cấu hình bảo mật.

## Kết luận

ElasticsearchClient là API Java cấp cao mà ứng dụng dùng để gọi các chức năng của Elasticsearch. ElasticsearchTransport là tầng nối API đó với cơ chế truyền tải và xử lý việc chuyển đổi request/response. Trong cấu hình REST phổ biến, RestClientTransport kết nối với low-level RestClient; RestClient chịu trách nhiệm gửi HTTP request và quản lý kết nối đến Elasticsearch REST API.

HTTP/HTTPS là giao thức giao tiếp trên mạng, còn Elasticsearch server là nơi thực sự thực thi truy vấn và lưu trữ document. Khi hiểu ranh giới này, lập trình viên có thể chọn đúng abstraction, cấu hình client và mapper phù hợp, quản lý tài nguyên đúng vòng đời, đồng thời xác định lỗi ở tầng API, transport, HTTP hay server.
