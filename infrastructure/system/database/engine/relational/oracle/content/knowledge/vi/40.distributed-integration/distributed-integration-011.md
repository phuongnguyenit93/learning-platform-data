# ORDS, REST-enabled SQL và ranh giới với ứng dụng Spring Boot

Oracle REST Data Services (ORDS) là tầng dịch vụ chạy bên ngoài Oracle Database, cung cấp giao diện HTTP/REST để ứng dụng và công cụ truy cập dữ liệu Oracle. ORDS có thể xuất bản REST API dựa trên bảng, view, PL/SQL handler hoặc SQL query đã được định nghĩa. ORDS cũng có tính năng REST-enabled SQL cho phép client gửi câu lệnh SQL qua HTTP trong một phạm vi schema được cấp quyền.

Khi một hệ thống đã có ứng dụng Spring Boot, cần xác định rõ phần nào thuộc ORDS và phần nào thuộc Spring Boot. Cả hai đều có thể tiếp nhận HTTP request và truy cập Oracle, nhưng vai trò thiết kế khác nhau:

- ORDS là lớp tích hợp gần database, phù hợp để xuất bản dữ liệu hoặc thao tác database theo contract REST được kiểm soát, cũng như hỗ trợ công cụ quản trị và tích hợp dữ liệu.
- Spring Boot là lớp ứng dụng, phù hợp để thực thi nghiệp vụ, phối hợp nhiều hệ thống, xác thực và phân quyền theo người dùng/nghiệp vụ, quản lý quy trình và cung cấp API ổn định cho client.
- REST-enabled SQL là giao diện truy cập SQL từ xa, không phải một API nghiệp vụ hoàn chỉnh. Nó cần được bảo vệ chặt chẽ và chỉ nên bật cho nhóm client, schema và mục đích đã được phê duyệt.

Một kiến trúc có thể dùng ORDS độc lập, Spring Boot độc lập hoặc kết hợp cả hai. Quyết định phải dựa trên quyền sở hữu nghiệp vụ, yêu cầu bảo mật, khả năng vận hành và hợp đồng API cần cung cấp.

## 1. ORDS là gì và nằm ở đâu trong kiến trúc?

ORDS là một middle tier của Oracle, triển khai như dịch vụ Java và kết nối tới Oracle Database thông qua connection pool. Client gửi HTTP request tới ORDS; ORDS xác thực, kiểm tra quyền, định tuyến tới REST handler hoặc REST-enabled SQL endpoint, sau đó thực thi thao tác tương ứng trong database và trả response HTTP.

Mô hình tổng quát:

    Web / Mobile / Integration client
                  |
               HTTPS
                  |
                  v
          Oracle REST Data Services
          +--------------------------+
          | Authentication          |
          | Authorization            |
          | REST routing             |
          | SQL / PL/SQL handlers    |
          | Connection pools         |
          +--------------------------+
                  |
          JDBC / database connection
                  |
                  v
             Oracle Database
          +--------------------------+
          | Tables / Views           |
          | PL/SQL packages          |
          | Schemas / Roles          |
          | Transactions             |
          +--------------------------+

ORDS có thể chạy độc lập với database server và thường được đặt sau reverse proxy hoặc load balancer. Database không cần trực tiếp mở HTTP endpoint ra Internet. Hệ thống mạng nên chỉ cho phép traffic tới ORDS qua HTTPS, còn kết nối từ ORDS tới database được giới hạn theo network policy.

ORDS không phải là một database engine mới và cũng không thay thế Oracle Net/JDBC trong mọi ứng dụng. Nó cung cấp lớp HTTP cho các thao tác database được cấu hình. Các transaction, constraint, privilege và dữ liệu vẫn do Oracle Database quản lý.

### 1.1. Các thành phần chính

Một triển khai ORDS thường có các thành phần:

- **ORDS runtime**: dịch vụ HTTP chạy trong Java container hoặc chế độ standalone tùy phiên bản và cách triển khai.
- **Database connection pool**: tập kết nối JDBC từ ORDS tới database service/schema được cấu hình.
- **ORDS metadata**: metadata nội bộ lưu cấu hình REST, module, handler, privilege, pool và các thành phần ORDS.
- **REST modules and handlers**: định nghĩa endpoint, template, HTTP method, source type và cách tạo response.
- **Authentication and authorization**: cơ chế xác thực client và kiểm tra quyền truy cập endpoint.
- **REST-enabled SQL**: endpoint cho phép gửi SQL qua HTTP theo chính sách và quyền được cấu hình.

Tên lệnh cấu hình, giao diện quản trị và yêu cầu triển khai thay đổi giữa các phiên bản ORDS. Khi triển khai thật, phải dùng tài liệu đúng phiên bản đang chạy và kiểm tra ma trận tương thích với Oracle Database, Java và các công cụ liên quan.

### 1.2. ORDS và Oracle Database

ORDS cần một hoặc nhiều database pool. Pool chứa thông tin kết nối, schema parsing, user và các thiết lập liên quan. Một request có thể mượn một connection từ pool, thực thi SQL/PLSQL, sau đó trả connection về pool.

Do đó, các giới hạn connection của ORDS cũng liên quan tới giới hạn session/process ở Oracle. Nếu có nhiều ORDS instance, mỗi instance có pool riêng, tổng connection tiềm năng là tổng capacity của các pool trên mọi instance và mọi database pool.

Không nên cấu hình pool size của ORDS mà không tính tới các ứng dụng JDBC khác, Spring Boot, batch job, monitoring và kết nối DBA. ORDS cũng có thể tạo tải lớn nếu endpoint cho phép truy vấn tốn kém hoặc client gửi request đồng thời quá nhiều.

## 2. REST API do ORDS xuất bản

ORDS cho phép xuất bản tài nguyên database thành REST endpoint. Có nhiều cách tạo REST API:

1. **AutoREST**: bật REST access cho bảng hoặc view theo cấu hình được hỗ trợ.
2. **REST modules**: định nghĩa module, URI template và handler cho từng HTTP method.
3. **PL/SQL handler**: gọi procedure hoặc package để thực thi nghiệp vụ database.
4. **Query handler**: trả dữ liệu từ SQL query đã được định nghĩa.
5. **ORDS metadata APIs**: quản lý hoặc tích hợp cấu hình theo quyền và phiên bản phù hợp.

Một REST API được thiết kế tốt có resource path ổn định, HTTP method rõ nghĩa, payload được xác thực, phân quyền cụ thể và response có cấu trúc.

Ví dụ minh họa:

    GET /ords/app/orders/1001
    POST /ords/app/orders
    PATCH /ords/app/orders/1001
    DELETE /ords/app/orders/1001

Các đường dẫn trên chỉ minh họa cách thiết kế resource. Endpoint thực tế phụ thuộc base path, schema alias, module và template đã cấu hình trong ORDS.

### 2.1. AutoREST

AutoREST có thể bật REST access cho bảng hoặc view mà ORDS hỗ trợ. Sau khi cấu hình, ORDS cung cấp endpoint để đọc hoặc thao tác dữ liệu theo khả năng và quyền đã cấp.

AutoREST có thể phù hợp với:

- Công cụ nội bộ cần truy cập một tập bảng đã được phê duyệt.
- Prototype hoặc tích hợp dữ liệu đơn giản.
- Các bảng tham chiếu có cấu trúc ổn định.
- Trường hợp cần tạo nhanh giao diện REST mà không viết nhiều handler.

Tuy nhiên, AutoREST không tự tạo ra quy tắc nghiệp vụ đầy đủ. Nếu một thao tác cần kiểm tra tồn kho, giới hạn tín dụng, chuyển trạng thái đơn hàng, ghi audit hoặc phối hợp nhiều bảng, chỉ mở CRUD trực tiếp trên bảng có thể bỏ qua quy trình nghiệp vụ.

Không nên bật AutoREST hàng loạt cho schema ứng dụng chỉ vì tiện. Mỗi bảng được mở ra có thể trở thành một bề mặt truy cập dữ liệu mới. Cần kiểm soát bảng, cột, quyền, dữ liệu nhạy cảm, thao tác DML và cách client được xác thực.

### 2.2. REST module, template và handler

REST module cho phép định nghĩa API theo contract riêng thay vì phụ thuộc trực tiếp vào cấu trúc bảng.

Các khái niệm thường gặp:

- **Module**: nhóm endpoint có base path và tên module.
- **Template**: URI pattern, ví dụ orders/:orderId.
- **Handler**: cách xử lý request theo HTTP method.
- **Source type**: loại nội dung handler thực thi, chẳng hạn query hoặc PL/SQL.
- **Parameter**: giá trị path, query hoặc header được truyền vào handler.
- **Privilege/role**: điều kiện quyền truy cập endpoint.
- **Pagination and response format**: cách phân trang, định dạng dữ liệu và metadata response.

Ví dụ contract:

    GET /ords/app/v1/orders/:orderId

Handler có thể lấy orderId từ path, kiểm tra tham số, truy vấn dữ liệu và trả response JSON. Với thao tác thay đổi dữ liệu, nên gọi PL/SQL package có kiểm soát transaction và quy tắc nghiệp vụ thay vì ghép SQL tùy ý từ chuỗi đầu vào.

REST handler có thể tách API contract khỏi tên bảng vật lý. Khi schema nội bộ thay đổi, handler có thể giữ response contract ổn định nếu được quản lý cẩn thận.

### 2.3. Dùng PL/SQL package làm lớp nghiệp vụ database

Trong một số hệ thống, nghiệp vụ được đóng gói trong PL/SQL package. ORDS có thể gọi package thông qua handler. Cách này có thể phù hợp khi logic phải chạy gần dữ liệu, cần transaction nhất quán và được DBA/nhóm database quản lý.

Ví dụ minh họa:

    CREATE OR REPLACE PACKAGE order_api AS
      PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_id OUT NUMBER
      );
    END order_api;
    /

ORDS handler nhận request, kiểm tra input, gọi package và trả mã trạng thái cùng payload phù hợp. Cần thống nhất nơi chịu trách nhiệm commit/rollback, xử lý exception và trả lỗi HTTP. Không nên để cùng một request vừa commit trong package vừa phụ thuộc một transaction khác ở handler mà không hiểu rõ semantics.

Nếu package chứa nghiệp vụ quan trọng, cần quản lý version, test, quyền EXECUTE, dependency và migration tương tự code ứng dụng.

## 3. REST-enabled SQL là gì?

REST-enabled SQL là tính năng ORDS cho phép client gửi câu lệnh SQL qua HTTP endpoint được cấu hình cho schema. Thay vì định nghĩa riêng một REST resource cho từng thao tác, client gửi request chứa SQL statement và các bind parameter; ORDS thực thi câu lệnh trong context được cấp quyền rồi trả kết quả.

Endpoint thường có dạng:

    POST /ords/{schema-alias}/_/sql

Đây là dạng URL minh họa phổ biến. Base path, schema alias, endpoint availability và contract request/response phụ thuộc phiên bản ORDS và cấu hình deployment. Hãy lấy endpoint từ tài liệu hoặc metadata của môi trường đang chạy thay vì hard-code theo ví dụ.

REST-enabled SQL có thể hữu ích cho:

- Công cụ phân tích hoặc quản trị được cấp quyền.
- SQL client tích hợp qua HTTP.
- Tác vụ nội bộ cần truy vấn có tham số mà không tạo một REST module riêng cho từng câu lệnh.
- Một số workflow phát triển hoặc kiểm thử dữ liệu.

Đặc điểm quan trọng là client gửi SQL. Vì thế, phạm vi quyền của database user, cách xác thực và khả năng giới hạn câu lệnh quyết định mức độ rủi ro. Không nên xem REST-enabled SQL như một endpoint public để ứng dụng mobile hoặc browser tùy ý gửi query.

### 3.1. Luồng request và response

Luồng khái quát:

    Client
      |
      | HTTPS POST + SQL statement + binds
      v
    ORDS REST-enabled SQL endpoint
      |
      | authenticate / authorize
      | validate request
      | borrow database connection
      v
    Oracle Database
      |
      | execute statement
      | produce rows / status
      v
    ORDS serializes response
      |
      v
    Client receives JSON response

Ví dụ payload minh họa cho một truy vấn có bind:

    {
      "statementText": "select order_id, status from orders where customer_id = :customer_id",
      "binds": [
        {
          "name": "customer_id",
          "type": "NUMBER",
          "value": 1001
        }
      ],
      "offset": 0,
      "limit": 50
    }

Cấu trúc field, kiểu bind được hỗ trợ, giới hạn số hàng, xử lý nhiều statement và format response cần được xác nhận theo phiên bản ORDS. Ví dụ trên chỉ mô tả ý tưởng parameterized SQL, không phải cam kết đầy đủ về mọi phiên bản endpoint.

Client nên dùng bind variables thay vì nối input vào SQL string. Bind giúp tách dữ liệu khỏi cú pháp SQL, tránh nhiều dạng SQL injection và hỗ trợ database tái sử dụng execution plan trong các trường hợp phù hợp.

### 3.2. SQL statement và quyền database

REST-enabled SQL không làm mất các quy tắc privilege của Oracle. SQL được thực thi trong database context của user/schema đã được cấu hình cho endpoint. User đó chỉ nên có quyền tối thiểu cho mục đích tích hợp.

Nếu user có quyền đọc nhiều schema hoặc quyền DML rộng, client qua REST-enabled SQL có thể tác động đến phạm vi dữ liệu tương ứng. Vì vậy, bảo vệ endpoint cần bắt đầu từ database account:

- Dùng account chuyên dụng cho từng nhóm tích hợp.
- Chỉ cấp SELECT/EXECUTE hoặc DML trên object cần thiết.
- Không dùng SYS, SYSTEM hoặc account DBA cho ứng dụng.
- Tách read-only integration khỏi write integration.
- Giới hạn schema, network, authentication và quota phù hợp.
- Kiểm tra quyền truy cập object qua role và direct grant theo yêu cầu thực thi của môi trường.

Không cấp quyền truy cập SQL tổng quát chỉ vì một client cần đọc một vài báo cáo. Có thể tạo view hoặc package giới hạn dữ liệu, sau đó xuất bản API có contract rõ ràng.

### 3.3. REST-enabled SQL không phải REST API nghiệp vụ

Một endpoint SQL tổng quát khiến client phụ thuộc vào cấu trúc database: tên bảng, tên cột, kiểu dữ liệu, join, quy tắc filter và quyền SQL. Nếu schema thay đổi, query phía client có thể hỏng. Client cũng có thể tự tạo truy vấn không được dự kiến nếu quyền quá rộng.

Một API nghiệp vụ thường chỉ cung cấp các thao tác mà hệ thống cho phép, ví dụ:

    POST /orders
    GET /orders/{id}
    POST /orders/{id}/approve

Contract nghiệp vụ có thể biểu diễn ý nghĩa như tạo đơn, xem đơn và phê duyệt đơn. Client không cần biết các bảng ORDER_HEADER, ORDER_LINE hay package nội bộ được tổ chức ra sao.

REST-enabled SQL nên được xem là công cụ truy cập dữ liệu có kiểm soát cho nhóm client đáng tin cậy. Nếu cần public API ổn định, versioning, validation, business authorization, orchestration và backward compatibility, hãy xây dựng resource API riêng.

## 4. Ranh giới giữa ORDS và ứng dụng Spring Boot

Spring Boot và ORDS có thể cùng nằm trong một hệ thống, nhưng cần phân định trách nhiệm để tránh hai nơi cùng sở hữu một API hoặc một quy tắc nghiệp vụ.

### 4.1. Khi nào dùng ORDS?

ORDS phù hợp khi:

- Cần xuất bản một tập dữ liệu Oracle thành REST resource với ít tầng trung gian.
- API chủ yếu đọc/ghi dữ liệu trong một schema và có contract đơn giản.
- PL/SQL package là nơi sở hữu nghiệp vụ database và muốn xuất bản package qua HTTP.
- DBA hoặc nhóm database chịu trách nhiệm vận hành API gần database.
- Cần REST-enabled SQL cho công cụ hoặc integration client được kiểm soát.
- Có nhu cầu dùng các tính năng ORDS gắn với Oracle như SQL Developer Web, REST API hoặc khả năng quản trị liên quan.

Ví dụ: một schema chứa bảng danh mục sản phẩm chỉ đọc. ORDS có thể xuất bản endpoint GET cho ứng dụng nội bộ, với privilege giới hạn và response đã định nghĩa.

### 4.2. Khi nào dùng Spring Boot?

Spring Boot phù hợp khi:

- API cần phối hợp nhiều database, message broker hoặc external service.
- Nghiệp vụ có nhiều bước, trạng thái, quy tắc phê duyệt hoặc saga.
- Cần xác thực người dùng cuối và phân quyền theo tenant, tổ chức hoặc quyền nghiệp vụ.
- Cần kiểm soát contract, versioning, validation, rate limiting và observability ở cấp ứng dụng.
- Cần tách vòng đời release API khỏi vòng đời database schema.
- Logic cần được kiểm thử độc lập và quản lý như một application service.
- Cần hỗ trợ nhiều loại database hoặc khả năng thay đổi persistence layer.

Ví dụ: tạo đơn hàng phải xác thực người mua, kiểm tra tồn kho, tính giá, áp dụng coupon, ghi order và phát sự kiện sang hệ thống giao hàng. Đây là quy trình ứng dụng phù hợp để Spring Boot điều phối; ORDS có thể là một integration endpoint phụ nếu cần.

### 4.3. Bảng so sánh

| Tiêu chí | ORDS | Spring Boot |
|---|---|---|
| Vai trò chính | HTTP interface cho Oracle Database | Application/API layer |
| Nơi thực thi | SQL, PL/SQL và handler trong database context | Java application service, repository và client tích hợp |
| Contract API | Module/template/handler hoặc AutoREST | Controller, DTO, service và API specification |
| Tích hợp nhiều hệ thống | Có thể gọi qua PL/SQL hoặc cơ chế tích hợp khác, nhưng không phải vai trò cốt lõi | Phù hợp cho orchestration và integration |
| Nghiệp vụ phức tạp | Có thể đặt trong PL/SQL nhưng dễ gắn chặt với database | Phù hợp cho quy trình nhiều bước và domain logic ứng dụng |
| Truy cập SQL tổng quát | REST-enabled SQL có thể cho phép SQL qua HTTP theo quyền | Không nên cung cấp SQL tổng quát cho client |
| Database coupling | Cao hơn, gần schema và PL/SQL | Có thể che giấu database sau repository/service |
| Authentication | Cấu hình ORDS/OAuth2/identity integration theo môi trường | Spring Security và tích hợp identity provider |
| Connection management | ORDS database pool | JDBC pool trong từng application instance |
| Deployment | ORDS runtime và cấu hình database metadata | Java service, container hoặc runtime ứng dụng |
| Đối tượng vận hành chính | DBA/nhóm database và platform | Nhóm backend/application platform |

Không có quy tắc rằng ORDS luôn nhanh hơn Spring Boot hoặc Spring Boot luôn an toàn hơn ORDS. Hiệu năng và bảo mật phụ thuộc cách triển khai, truy vấn, pool, quyền, network, payload, cache và vận hành.

## 5. Kiến trúc kết hợp ORDS và Spring Boot

Một kiến trúc kết hợp có thể dùng Spring Boot làm public API và ORDS làm interface nội bộ cho một số tác vụ database hoặc công cụ dữ liệu.

Ví dụ:

    Browser / Mobile / Partner
              |
            HTTPS
              |
              v
        API Gateway / WAF
              |
              v
       Spring Boot services
       +----------------------+
       | Authentication       |
       | Business rules       |
       | Validation           |
       | Orchestration        |
       | Audit / Observability|
       +----------------------+
           |             |
           | JDBC        | HTTPS (selected integration)
           v             v
       Oracle DB         ORDS
                           |
                           v
                       Oracle DB

Trong mô hình này, Spring Boot có thể kết nối trực tiếp Oracle qua JDBC cho giao dịch nghiệp vụ chính. ORDS có thể cung cấp một REST API riêng cho nhóm tích hợp, reporting hoặc công cụ quản trị. Không nhất thiết mọi thao tác Spring Boot phải đi qua ORDS; thêm một hop HTTP giữa hai tầng có thể tăng latency và tạo thêm điểm lỗi nếu không có lợi ích kiến trúc rõ ràng.

Một số nguyên tắc:

- Chọn một nơi sở hữu contract API cho mỗi use case.
- Không tạo cùng một endpoint ở Spring Boot và ORDS mà không có lý do rõ ràng.
- Nếu Spring Boot gọi ORDS, định nghĩa timeout, retry, circuit breaker, authentication và trace propagation.
- Tránh vòng lặp gọi Spring Boot → ORDS → Spring Boot.
- Không để client public gọi thẳng REST-enabled SQL nếu use case cần API nghiệp vụ.
- Giữ transaction boundary rõ ràng. Một transaction JDBC trong Spring Boot không tự động bao trùm một HTTP request riêng tới ORDS.
- Đồng bộ schema migration, API version và release plan giữa các nhóm sở hữu.

### 5.1. Spring Boot gọi ORDS như một external HTTP service

Nếu một use case thực sự cần gọi ORDS, Spring Boot có thể dùng WebClient hoặc HTTP client để gọi endpoint. Nên đóng gói client trong adapter/service riêng thay vì để controller tự tạo URL và HTTP request.

Ví dụ minh họa với WebClient:

    @Configuration
    class OrdsClientConfiguration {

        @Bean
        WebClient ordsWebClient(
                WebClient.Builder builder,
                OrdsProperties properties) {
            return builder
                    .baseUrl(properties.baseUrl())
                    .build();
        }
    }

    @ConfigurationProperties(prefix = "integration.ords")
    public record OrdsProperties(String baseUrl) {}

    @Service
    class CatalogClient {

        private final WebClient webClient;

        CatalogClient(WebClient ordsWebClient) {
            this.webClient = ordsWebClient;
        }

        Mono<CatalogItem> findItem(String itemId) {
            return webClient.get()
                    .uri("/ords/catalog/v1/items/{id}", itemId)
                    .retrieve()
                    .bodyToMono(CatalogItem.class);
        }
    }

Đoạn code chỉ minh họa cấu trúc adapter. Trong ứng dụng thực tế cần cấu hình OAuth2/client credentials hoặc cơ chế xác thực được ORDS hỗ trợ, timeout, error mapping, connection pool HTTP, correlation ID và chính sách retry. Không retry tự động mọi POST/PUT nếu thao tác không idempotent.

Nếu API ORDS chỉ phục vụ truy vấn dữ liệu đơn giản mà Spring Boot có thể đọc trực tiếp qua repository, hãy cân nhắc liệu HTTP hop có thực sự cần thiết. Dùng ORDS khi cần một contract REST độc lập hoặc khi nó là cổng tích hợp được quản lý bởi nhóm database.

### 5.2. Transaction boundary khi gọi qua HTTP

Một transaction database thường gắn với connection/session cụ thể. Nếu Spring Boot mở transaction JDBC rồi gọi HTTP tới ORDS, ORDS mượn một connection khác từ pool của nó. Hai connection này không tự động tham gia cùng một local transaction.

Ví dụ:

    Spring Boot transaction A
        |
        +-- UPDATE order_header
        |
        +-- HTTP request to ORDS
                |
                +-- ORDS transaction B
                        |
                        +-- UPDATE inventory

Nếu transaction B commit nhưng transaction A rollback, tồn kho và đơn hàng có thể lệch nhau. Nếu A commit nhưng B thất bại, trạng thái cũng không đồng nhất. Không được giả định @Transactional của Spring Boot tự quản lý transaction của HTTP request ORDS.

Với nghiệp vụ cần atomicity trên cùng database, thường nên thực hiện trong cùng transaction boundary bằng JDBC hoặc gọi một stored procedure/package qua một connection. Nếu cần phối hợp nhiều dịch vụ qua HTTP, thiết kế saga, outbox/inbox, idempotency và compensating action thay vì dựa vào một transaction cục bộ không thể bao phủ nhiều service.

### 5.3. Quyền sở hữu schema và API

Cần xác định rõ:

- Nhóm nào sở hữu database schema.
- Nhóm nào sở hữu PL/SQL package.
- Nhóm nào sở hữu ORDS module và privilege.
- Nhóm nào sở hữu Spring Boot API contract.
- Ai quản lý authentication, certificate, secret và rotation.
- Ai chịu trách nhiệm versioning và tương thích ngược.
- Ai theo dõi hiệu năng, quota, connection pool và lỗi production.

Nếu Spring Boot và ORDS cùng thay đổi một schema, cần có quy trình migration tương thích với cả hai. Không triển khai DDL phá vỡ endpoint ORDS trong khi Spring Boot vẫn dùng schema cũ, hoặc ngược lại.

## 6. Bảo mật ORDS và REST-enabled SQL

ORDS là một bề mặt HTTP truy cập database. Nếu cấu hình sai, endpoint có thể làm lộ dữ liệu hoặc cho phép thao tác vượt quá mục đích tích hợp. Bảo mật phải được thiết kế ở nhiều lớp.

### 6.1. HTTPS và network boundary

- Chỉ sử dụng HTTPS cho traffic client tới ORDS.
- Đặt ORDS sau load balancer/reverse proxy hoặc gateway có kiểm soát.
- Giới hạn network path từ ORDS tới database; chỉ mở port và service cần thiết.
- Không expose database listener trực tiếp ra Internet.
- Tách endpoint nội bộ và public bằng network policy, hostname hoặc gateway policy.
- Quản lý certificate, expiry và rotation.
- Không tin header identity từ client trừ khi được gateway xác thực và chuyển tiếp theo cơ chế đáng tin cậy.

### 6.2. Authentication và authorization

Authentication trả lời client là ai; authorization trả lời client được phép làm gì. Hai khái niệm này phải được kiểm soát riêng.

ORDS có thể tích hợp các cơ chế xác thực được hỗ trợ theo phiên bản và môi trường, chẳng hạn OAuth 2.0, database authentication hoặc identity provider integration. Cần chọn flow phù hợp với loại client:

- Machine-to-machine integration: client credentials hoặc cơ chế service identity được hỗ trợ.
- User-facing application: delegated user identity hoặc gateway/identity provider phù hợp.
- Administrative access: account riêng, MFA và network restriction theo chính sách tổ chức.

Sau khi xác thực, privilege/role phải giới hạn endpoint và object mà client được phép truy cập. Không nên cấp một role chung có toàn quyền schema cho mọi integration client.

### 6.3. Least privilege ở database

Tạo database user riêng cho từng ứng dụng hoặc nhóm tích hợp. Ví dụ một user chỉ đọc báo cáo nên có quyền SELECT trên các view được phê duyệt, không cần quyền UPDATE/DELETE trên bảng giao dịch.

Có thể tạo view giới hạn cột và dòng:

    CREATE VIEW reporting_order_summary AS
    SELECT order_id, order_date, status, total_amount
    FROM orders
    WHERE status <> 'INTERNAL';

    GRANT SELECT ON reporting_order_summary TO report_api_user;

Điều kiện WHERE chỉ là ví dụ minh họa. Nếu dữ liệu cần phân quyền theo tenant hoặc người dùng, cần cơ chế bảo đảm predicate không thể bị client thay đổi để đọc tenant khác. Có thể dùng view, VPD/row-level security, application context hoặc handler có kiểm soát tùy kiến trúc.

Không dùng tài khoản owner của schema với quyền rộng cho client REST-enabled SQL.

### 6.4. SQL injection và bind variables

REST-enabled SQL nhận SQL từ client, nên cần kiểm soát quyền và cách tạo statement rất chặt chẽ. Với API handler, tuyệt đối tránh nối trực tiếp dữ liệu request vào câu SQL:

    -- Không an toàn: input được ghép trực tiếp vào SQL
    sql_text := 'SELECT * FROM orders WHERE customer_id = ' || p_customer_id;

Ưu tiên bind variables:

    SELECT order_id, status
    FROM orders
    WHERE customer_id = :customer_id;

Bind variables tách giá trị khỏi cú pháp SQL. Tuy nhiên, bind không thể thay thế tên bảng, tên cột hoặc từ khóa SQL. Nếu cần dynamic SQL với identifier, phải dùng allowlist và kiểm tra identifier bằng cơ chế phù hợp như DBMS_ASSERT, không nhận identifier tùy ý từ client.

Với REST-enabled SQL, client gửi statement trực tiếp nên bind variable giúp bảo vệ giá trị nhưng không biến endpoint thành an toàn tuyệt đối. Một client có quyền gửi SQL tùy ý vẫn có thể đọc hoặc thay đổi mọi object mà database user đó được phép truy cập. Least privilege và giới hạn endpoint là yêu cầu nền tảng.

### 6.5. Bảo vệ dữ liệu nhạy cảm

- Không trả password, token, secret hoặc dữ liệu xác thực trong response.
- Không xuất bản bảng chứa thông tin cá nhân nếu không có mục đích và phân quyền rõ ràng.
- Giới hạn cột được trả về, đặc biệt dữ liệu định danh và tài chính.
- Thiết lập audit cho truy cập nhạy cảm theo yêu cầu.
- Giữ log không chứa payload bí mật hoặc SQL literal có thông tin nhạy cảm.
- Xác định thời gian lưu log và ai được đọc log.
- Kiểm tra masking/anonymization khi dùng dữ liệu production trong môi trường test.

### 6.6. Rate limit, payload và query cost

Một REST endpoint đọc database có thể bị lạm dụng bằng request tần suất cao hoặc query trả về quá nhiều dữ liệu. Cần đặt:

- Rate limit và concurrency limit ở gateway/ORDS theo năng lực database.
- Pagination và giới hạn page size.
- Timeout cho statement và HTTP request.
- Giới hạn payload request/response.
- Kiểm soát SQL plan và index cho query quan trọng.
- Giám sát connection pool, active session, CPU, I/O và wait event.
- Chính sách cancel request và xử lý client disconnect.

Không nên để endpoint cho phép full table scan hoặc truy vấn không giới hạn trên bảng lớn mà không có kiểm soát.

## 7. Connection pool, concurrency và hiệu năng

ORDS có database connection pool. Mỗi ORDS instance và mỗi pool có thể mở một số connection tối đa. Nếu chạy nhiều instance sau load balancer, tổng số session tiềm năng có thể tăng đáng kể.

Ví dụ:

    3 ORDS instances
    2 database pools per instance
    20 maximum connections per pool

    Maximum potential connections
      = 3 x 2 x 20
      = 120

Con số này chưa cộng connection từ Spring Boot, batch job, monitoring và DBA. Với Oracle dedicated server, mỗi session ứng dụng thường có server process riêng; vì vậy cần đối chiếu với PROCESSES và SESSIONS, cũng như capacity của database host.

### 7.1. Không tăng pool vô hạn

Pool lớn hơn có thể tăng concurrency, nhưng cũng tăng session, process, memory và cạnh tranh tài nguyên. Nếu database đã bão hòa CPU hoặc I/O, tăng pool có thể làm latency tệ hơn.

Hãy đo:

- Số request active và pending ở ORDS.
- Connection pool active/available/borrow timeout.
- Số session theo service/module/schema.
- SQL execution time, wait event, CPU và I/O.
- Throughput và p95/p99 latency.
- Tỷ lệ lỗi HTTP và database error.

### 7.2. ORDS và Spring Boot có pool riêng

Nếu cả Spring Boot và ORDS kết nối cùng database, chúng có hai nhóm connection pool độc lập. Ví dụ:

    Spring Boot replicas: 4
    Hikari maximumPoolSize: 20
    Potential Spring Boot sessions: 80

    ORDS instances: 2
    ORDS pool maximum: 30
    Potential ORDS sessions: 60

    Combined potential: 140 sessions

Đây chỉ là phép tính capacity theo cấu hình tối đa. Cần cộng batch, monitoring, job, background session/process và headroom. Với RAC, kiểm tra từng instance vì phân phối kết nối có thể không đều.

### 7.3. Connection timeout và query timeout

Cần phân biệt:

- Thời gian chờ lấy connection từ pool.
- Thời gian thực thi SQL ở database.
- Thời gian xử lý request ở ORDS.
- Timeout ở reverse proxy/API gateway.
- Timeout của client.

Nếu proxy timeout ngắn hơn thời gian query, client có thể nhận lỗi trong khi database vẫn đang xử lý. Hãy thiết kế timeout theo thứ tự hợp lý, có khả năng cancel statement và giải phóng connection khi request bị hủy.

## 8. HTTP semantics và thiết kế API

ORDS REST module nên tuân thủ semantics HTTP để client hiểu đúng tác động của request.

| Method | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| GET | Đọc resource, không thay đổi trạng thái nghiệp vụ | Lấy chi tiết order |
| POST | Tạo resource hoặc thực hiện command | Tạo order |
| PUT | Thay thế representation của resource theo contract | Cập nhật toàn bộ cấu hình |
| PATCH | Cập nhật một phần resource | Đổi trạng thái được phép |
| DELETE | Xóa hoặc đánh dấu xóa resource theo contract | Xóa draft |

Không nên dùng GET để thực hiện DML. Proxy, cache hoặc browser có thể retry GET theo các giả định về tính an toàn của method. Một handler GET có side effect sẽ làm hệ thống khó dự đoán và khó bảo vệ.

### 8.1. Status code và error response

Thiết kế response cần nhất quán:

- 200 OK cho thao tác đọc hoặc cập nhật thành công có response.
- 201 Created khi tạo resource thành công, có thể kèm Location.
- 204 No Content khi thao tác thành công không cần body.
- 400 Bad Request khi input sai định dạng.
- 401 Unauthorized khi chưa xác thực hoặc credential không hợp lệ.
- 403 Forbidden khi đã xác thực nhưng không có quyền.
- 404 Not Found khi resource không tồn tại hoặc không được phép hiển thị theo policy.
- 409 Conflict khi trạng thái hoặc constraint xung đột.
- 422 Unprocessable Content nếu contract dùng để biểu diễn dữ liệu hợp lệ về cú pháp nhưng vi phạm validation.
- 429 Too Many Requests khi rate limit bị vượt.
- 500 Internal Server Error cho lỗi không dự kiến; không lộ stack trace hoặc SQL nội bộ.

Mã lỗi cụ thể cần tuân theo contract API của hệ thống. Không trả toàn bộ Oracle error stack cho client public vì có thể tiết lộ tên bảng, schema, SQL, đường dẫn hoặc thông tin nội bộ.

### 8.2. Pagination và sorting

API đọc danh sách nên có giới hạn page size và pagination ổn định. Với dataset lớn, offset pagination có thể chậm khi offset cao; keyset pagination theo khóa sắp xếp có thể phù hợp hơn.

Sort field phải được allowlist. Không ghép trực tiếp giá trị sort hoặc column name do client gửi vào SQL. Nếu endpoint dùng query handler, mapping giữa sort option và cột SQL phải do server kiểm soát.

### 8.3. Idempotency và retry

Client có thể retry khi timeout hoặc mất kết nối. Với thao tác tạo đơn hàng hoặc thanh toán, retry có thể tạo dữ liệu trùng nếu API không có idempotency strategy.

Một command API nên cân nhắc idempotency key, unique constraint, request ledger hoặc cơ chế deduplication. Retry chỉ nên thực hiện tự động khi operation an toàn để retry hoặc có idempotency guarantee.

## 9. Quản lý version và vòng đời API

ORDS module và Spring Boot API đều cần versioning khi client phụ thuộc vào contract.

Ví dụ:

    /ords/app/v1/orders
    /ords/app/v2/orders

Hoặc version trong header theo chính sách của tổ chức. Không đổi kiểu dữ liệu, ý nghĩa field, status code hoặc quyền truy cập mà không đánh giá tác động client.

Khi database schema thay đổi:

1. Xác định API/handler nào sử dụng object bị đổi.
2. Triển khai schema theo hướng tương thích ngược nếu cần.
3. Cập nhật PL/SQL package và ORDS module theo release plan.
4. Cập nhật Spring Boot adapter hoặc DTO nếu contract thay đổi.
5. Kiểm thử client cũ và mới.
6. Chỉ loại bỏ API version cũ sau khi client migration hoàn tất.

Có thể dùng expand-and-contract migration: thêm cột hoặc package mới trước, chuyển client sang dùng, sau đó mới loại bỏ cấu trúc cũ ở release sau. Cách này giảm nguy cơ ORDS và Spring Boot lệch phiên bản schema trong lúc rollout.

## 10. Quan sát, logging và audit

ORDS là một tầng riêng nên cần observability độc lập và liên kết với database.

Các thông tin nên ghi nhận:

- Request ID/correlation ID.
- HTTP method, route và status code.
- Client identity hoặc application identity ở mức an toàn.
- Thời gian xử lý tổng, thời gian chờ pool và thời gian database.
- Module/handler hoặc endpoint được gọi.
- Database service, schema/pool và session/module nếu được cấu hình.
- Số hàng trả về hoặc số hàng tác động, tránh ghi payload nhạy cảm.
- Oracle error code đã được ánh xạ an toàn.
- Kết quả authentication/authorization ở mức phù hợp.

Không ghi access token, password, bind value nhạy cảm hoặc toàn bộ SQL chứa dữ liệu cá nhân vào log. Nếu cần audit SQL, thiết kế retention, quyền truy cập và masking theo chính sách dữ liệu.

Spring Boot nên truyền correlation ID sang ORDS nếu gọi qua HTTP, để có thể nối log ở gateway, service, ORDS và database. Với JDBC trực tiếp, Spring Boot cũng nên đặt module/action hoặc client identifier phù hợp để DBA nhận diện session trong V$SESSION.

## 11. Triển khai và vận hành ORDS

Một triển khai production cần quản lý cả runtime ORDS và metadata database.

Các điểm cần chuẩn bị:

- Phiên bản ORDS, Java runtime và Oracle Database tương thích.
- ORDS configuration directory và cách quản lý secret.
- Database pool, service name, schema mapping và connection limits.
- HTTPS certificate, reverse proxy, load balancer và network firewall.
- Authentication provider, OAuth client, role và privilege.
- Backup metadata/configuration phù hợp.
- Log, metrics, health check và alert.
- Patch management và kế hoạch upgrade.
- HA/DR cho ORDS runtime và database backend.

Không đặt password database trong source code hoặc file cấu hình được commit. Dùng secret manager hoặc cơ chế bảo vệ cấu hình mà platform hỗ trợ; phân quyền đọc secret và lên lịch rotation.

### 11.1. Health check và readiness

Health check cần phân biệt ORDS process đang chạy với database pool thực sự có thể phục vụ request. Một process có thể trả HTTP response nhưng database connection pool đã hết hoặc database không sẵn sàng.

Nên giám sát tối thiểu:

- Runtime process và HTTP listener.
- Kết nối tới database pool.
- Authentication/authorization dependency.
- Request error rate và latency.
- Connection pool saturation.
- Database service health.

Health endpoint không nên tiết lộ thông tin nhạy cảm về database hoặc cấu hình nội bộ.

### 11.2. HA và scaling

Có thể chạy nhiều ORDS instance sau load balancer. Mỗi instance cần cấu hình nhất quán và kết nối tới database service phù hợp. Scaling ORDS tăng khả năng xử lý HTTP nhưng cũng có thể làm tăng tổng connection tới database.

Trước khi scale out, tính tổng pool capacity trên tất cả instance và kiểm tra Oracle SESSIONS/PROCESSES. Nếu database là nút thắt, thêm ORDS instance có thể làm tăng tải mà không tăng throughput.

### 11.3. Upgrade và tương thích

Khi nâng cấp ORDS:

- Đọc release notes và yêu cầu phiên bản Java/database.
- Backup cấu hình và database chứa ORDS metadata.
- Kiểm tra custom module, handler, privilege và authentication.
- Kiểm thử endpoint cũ và SQL-enabled endpoint cần thiết.
- Triển khai rolling hoặc blue/green nếu kiến trúc hỗ trợ.
- Có kế hoạch rollback runtime và metadata migration phù hợp.

Không nâng cấp runtime production mà chưa thử trên môi trường tương đương, đặc biệt nếu API là dependency của hệ thống khác.

## 12. Chọn ORDS hay Spring Boot cho từng use case

Một cách ra quyết định là bắt đầu từ câu hỏi: client cần truy cập dữ liệu database hay cần thực hiện một hành vi nghiệp vụ?

| Use case | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Công cụ nội bộ chạy query đã được phê duyệt | REST-enabled SQL có kiểm soát | Client kỹ thuật cần gửi SQL và có quyền giới hạn |
| Xuất bản bảng tham chiếu read-only | ORDS REST API hoặc view handler | Contract đơn giản, dữ liệu gần database |
| CRUD đơn giản cho một schema với owner rõ ràng | ORDS REST module | Có thể xuất bản resource gần database |
| Tạo đơn hàng qua nhiều bước | Spring Boot | Cần orchestration, validation và domain logic |
| Gọi payment, inventory và message broker | Spring Boot | Cần phối hợp nhiều hệ thống và xử lý lỗi phân tán |
| API public cho mobile/partner | Spring Boot thường phù hợp | Cần versioning, business authorization và contract ổn định |
| Công cụ DBA hoặc data integration tin cậy | ORDS/REST-enabled SQL tùy phạm vi | Gần database và phù hợp cho truy cập có kiểm soát |
| Nghiệp vụ đã đóng gói trong PL/SQL package | ORDS handler có thể phù hợp | Có thể xuất bản package mà không di chuyển logic |

Đây là hướng lựa chọn, không phải giới hạn cứng. Một hệ thống có thể dùng ORDS cho endpoint database-centric và Spring Boot cho API nghiệp vụ, miễn là ownership và security boundary rõ ràng.

## 13. Tình huống minh họa: hệ thống quản lý đơn hàng

Giả sử hệ thống có:

- Spring Boot Order Service sở hữu quy trình đặt hàng.
- Oracle Database lưu order, customer và inventory.
- ORDS xuất bản API đọc danh mục sản phẩm cho một integration client nội bộ.
- Một công cụ DBA dùng REST-enabled SQL trong mạng quản trị để chạy truy vấn được phép.

Luồng tạo đơn:

    Mobile client
        |
        | POST /api/orders
        v
    Spring Boot Order Service
        |
        +--> Validate user and request
        +--> Check business rules
        +--> Update order and inventory in DB transaction
        +--> Write outbox event
        |
        v
    HTTP response

Luồng đọc danh mục:

    Internal integration client
        |
        | GET /ords/catalog/v1/products
        v
    ORDS REST handler
        |
        | query approved view
        v
    Oracle Database

Luồng truy vấn quản trị:

    Admin SQL tool
        |
        | HTTPS + authenticated SQL request
        v
    ORDS REST-enabled SQL
        |
        | restricted database account
        v
    Oracle Database

Trong thiết kế này, Spring Boot là owner của quy trình đặt hàng. ORDS không tạo endpoint thứ hai để cập nhật order nếu việc đó sẽ bỏ qua validation và transaction logic của Order Service. ORDS chỉ cung cấp dữ liệu danh mục đã được phê duyệt. REST-enabled SQL được giới hạn cho công cụ quản trị, user riêng và network riêng.

Nếu sau này integration client cần tạo yêu cầu đặt hàng, nên gọi Spring Boot API có contract nghiệp vụ thay vì cấp quyền DML tổng quát qua REST-enabled SQL.

## 14. Các lỗi thiết kế thường gặp

### 14.1. Public REST-enabled SQL

Cho phép Internet client gửi SQL tùy ý làm tăng đáng kể bề mặt tấn công và coupling. Một lỗi phân quyền có thể cho phép đọc hoặc sửa dữ liệu ngoài dự kiến.

Hướng xử lý: chỉ bật cho client được kiểm soát, dùng account quyền tối thiểu, network restriction và authentication mạnh. Với public use case, tạo REST resource riêng hoặc Spring Boot API.

### 14.2. AutoREST trực tiếp bảng nghiệp vụ

Bật CRUD trực tiếp trên bảng order, payment hoặc account có thể bỏ qua business rule, audit và workflow. Hướng xử lý: xuất bản view read-only hoặc PL/SQL handler gọi package có kiểm soát; giữ command nghiệp vụ trong application service nếu Spring Boot sở hữu domain.

### 14.3. Spring Boot gọi ORDS cho mọi query

Đưa mọi thao tác JDBC qua HTTP tới ORDS có thể tạo thêm latency, connection pool, điểm lỗi và transaction boundary. Chỉ làm khi cần contract REST hoặc boundary tích hợp độc lập. Nếu Spring Boot sở hữu use case và cần transaction với Oracle, JDBC trực tiếp thường đơn giản hơn.

### 14.4. Hai nơi cùng sở hữu nghiệp vụ

Nếu Spring Boot và PL/SQL cùng thực hiện một quy tắc tính giá hoặc phê duyệt, logic có thể lệch nhau theo thời gian. Cần chọn owner duy nhất cho từng quy tắc và biến phần còn lại thành adapter. Nếu nghiệp vụ nằm trong PL/SQL, Spring Boot nên gọi package qua repository/adapter và không tái hiện quy tắc theo cách khác.

### 14.5. Không tính tổng connection

ORDS, Spring Boot, batch và công cụ quản trị có pool độc lập. Nếu chỉ xem pool của một ứng dụng, database có thể chạm SESSIONS hoặc PROCESSES khi tất cả cùng tăng tải. Hãy cộng maximum pool size trên mọi replica và giữ headroom.

### 14.6. Lộ lỗi database ra HTTP

Trả raw SQL, stack trace hoặc Oracle error message cho client có thể tiết lộ schema, object và cấu trúc nội bộ. Hãy ánh xạ lỗi sang error code ổn định, giữ chi tiết kỹ thuật trong log có kiểm soát và gửi correlation ID cho client.

## 15. Checklist thiết kế và vận hành

### Trước khi xuất bản endpoint

- Xác định endpoint phục vụ user, service hay công cụ quản trị.
- Chọn ORDS REST module, AutoREST, PL/SQL handler hay REST-enabled SQL.
- Xác định owner của contract và nghiệp vụ.
- Giới hạn database user, schema, object và privilege.
- Thiết kế authentication, authorization và HTTPS.
- Xác định pagination, timeout, payload limit, rate limit và error mapping.
- Kiểm tra SQL/PLSQL, index, execution plan và khả năng chịu tải.
- Kiểm tra dữ liệu nhạy cảm và audit requirement.
- Kiểm thử client hợp lệ và client không có quyền.

### Khi kết hợp với Spring Boot

- Chỉ gọi ORDS qua adapter/client có cấu hình tập trung.
- Định nghĩa timeout, retry, circuit breaker và idempotency.
- Không giả định @Transactional bao phủ HTTP request ORDS.
- Không để ORDS và Spring Boot cùng sở hữu một business rule.
- Theo dõi connection pool của cả hai tầng.
- Truyền correlation ID và đặt module/action để truy vết.
- Quản lý schema migration tương thích với cả ORDS và Spring Boot.
- Có versioning và kế hoạch deprecation cho endpoint.

### Sau khi triển khai

- Theo dõi HTTP status, latency và error rate.
- Theo dõi ORDS pool, database session/process và SQL wait.
- Rà soát privilege và OAuth client định kỳ.
- Kiểm tra certificate và secret rotation.
- Kiểm thử upgrade và rollback.
- Kiểm tra log không chứa token/password/PII ngoài chính sách.
- Diễn tập khi database hoặc ORDS runtime không sẵn sàng.

## 16. Nguyên tắc cần nhớ

- ORDS là middle tier cung cấp HTTP/REST interface cho Oracle Database.
- REST API của ORDS có thể được tạo bằng AutoREST, module/template/handler hoặc PL/SQL package.
- REST-enabled SQL cho phép gửi SQL qua HTTP và phải được bảo vệ như một giao diện truy cập database có quyền.
- Spring Boot phù hợp với API nghiệp vụ, orchestration, tích hợp nhiều hệ thống và authorization theo domain.
- Không đưa SQL tổng quát ra public client khi chỉ cần một vài thao tác nghiệp vụ.
- ORDS và Spring Boot có connection pool riêng; phải tính tổng session trên mọi instance và dịch vụ.
- HTTP call từ Spring Boot sang ORDS tạo transaction boundary riêng; @Transactional không tự bao trùm hai connection.
- Cần một owner rõ ràng cho API contract và từng business rule.
- Bảo mật cần kết hợp HTTPS, authentication, authorization, least privilege, bind variables, rate limit và audit.
- Hiệu năng cần theo dõi cả HTTP request, ORDS pool và Oracle Database.

ORDS và Spring Boot có thể bổ sung cho nhau khi mỗi tầng giữ đúng trách nhiệm. ORDS cung cấp giao diện REST gần database và công cụ truy cập SQL có kiểm soát; Spring Boot cung cấp lớp ứng dụng để bảo vệ contract, điều phối nghiệp vụ và tích hợp hệ thống. Ranh giới rõ ràng giúp API dễ bảo trì, transaction dễ hiểu, quyền truy cập có thể giới hạn và database không bị mở rộng bề mặt truy cập ngoài nhu cầu thực tế.
