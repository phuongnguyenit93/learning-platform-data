# Cấu hình bằng application properties

Spring Boot cho phép cấu hình Spring for GraphQL thông qua các thuộc tính có tiền tố **spring.graphql**. Thay vì viết Java configuration cho mọi thiết lập thông thường, ứng dụng có thể khai báo endpoint, vị trí schema, GraphiQL, WebSocket, RSocket và CORS trong **application.properties** hoặc **application.yml**.

Các thuộc tính này được Spring Boot bind vào cấu hình auto-configuration. Khi ứng dụng khởi động, Boot dựa vào classpath và các giá trị cấu hình để tạo những thành phần cần thiết như GraphQlSource, HTTP endpoint và các transport adapter được hỗ trợ. Cấu hình properties giúp điều chỉnh hành vi theo môi trường triển khai mà không phải sửa code.

Bài này tập trung vào cách tổ chức cấu hình, những thuộc tính Spring GraphQL thường dùng, cách ghi bằng properties/YAML, profile, biến môi trường, kiểm tra giá trị hiệu lực và các giới hạn của cấu hình khai báo.

## 1. Vai trò của application properties

Spring Boot sử dụng externalized configuration để đọc cấu hình từ nhiều nguồn: file properties/YAML, biến môi trường, Java system properties, tham số dòng lệnh và các nguồn cấu hình khác. Các giá trị được bind vào những nhóm cấu hình mà thư viện hoặc ứng dụng công bố.

Với Spring for GraphQL, phần lớn thuộc tính tích hợp bắt đầu bằng:

~~~text
spring.graphql
~~~

Ví dụ:

~~~properties
spring.graphql.path=/api/graphql
spring.graphql.graphiql.enabled=false
~~~

Hai giá trị trên lần lượt thay đổi HTTP endpoint và trạng thái bật/tắt GraphiQL. Spring Boot đọc cấu hình khi tạo application context, sau đó auto-configuration sử dụng các giá trị đã bind.

Properties phù hợp với các thiết lập có thể biểu diễn bằng giá trị đơn, danh sách, đường dẫn hoặc thời lượng. Những hành vi cần logic tùy biến như phân quyền theo tài nguyên, chuyển đổi custom scalar, resolve interface/union, DataLoader hoặc xử lý exception nghiệp vụ thường cần Java bean, annotation hoặc cấu hình chuyên biệt.

Không phải mọi thuộc tính bắt đầu bằng **spring.graphql** đều có sẵn trong mọi phiên bản Spring Boot. Hãy dùng cấu hình metadata và tài liệu đúng phiên bản Spring Boot của dự án để xác nhận tên, kiểu dữ liệu và giá trị mặc định.

## 2. Cấu hình endpoint HTTP

Thuộc tính cơ bản nhất là **spring.graphql.path**. Giá trị mặc định thường là **/graphql**. Có thể đổi endpoint để phù hợp với quy ước URL của ứng dụng:

~~~properties
spring.graphql.path=/api/graphql
~~~

Sau khi thay đổi, client gửi request đến path mới. Ví dụ:

~~~http
POST /api/graphql HTTP/1.1
Content-Type: application/json

{
  "query": "{ books { id title } }"
}
~~~

Path của GraphQL endpoint cần được phân biệt với context path của web application. Ví dụ, nếu Spring MVC có:

~~~properties
server.servlet.context-path=/catalog
spring.graphql.path=/api/graphql
~~~

URL bên ngoài sẽ bao gồm cả context path và GraphQL path:

~~~text
/catalog/api/graphql
~~~

Với WebFlux, base path của ứng dụng có thể được cấu hình bằng thuộc tính của WebFlux. Khi đặt ứng dụng sau reverse proxy hoặc API gateway, hãy kiểm tra URL mà client nhìn thấy và URL mà backend thực sự nhận được. Việc đổi **spring.graphql.path** không tự thay đổi route của proxy, firewall hoặc gateway.

### Chọn HTTP runtime

Spring for GraphQL có thể tích hợp với Spring MVC hoặc Spring WebFlux. Việc chọn web stack chủ yếu phụ thuộc dependency và loại application context được Spring Boot khởi tạo:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Nếu ứng dụng dùng WebFlux, thay starter web MVC bằng starter WebFlux tương ứng:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

Không có một thuộc tính **spring.graphql.mvc.enabled** hoặc **spring.graphql.webflux.enabled** để tùy ý đổi runtime. Classpath và cấu hình web application quyết định integration nào được kích hoạt. Tránh thêm cả hai web starter nếu dự án không có nhu cầu rõ ràng, vì điều đó có thể làm lựa chọn web application type khó đoán hơn.

## 3. Cấu hình vị trí và phần mở rộng của schema

Spring Boot tìm các file SDL trên classpath theo vị trí mặc định, thường là:

~~~text
classpath:graphql/**/
~~~

Các file schema thường dùng phần mở rộng **.graphqls** hoặc **.gqls**. Có thể khai báo vị trí khác bằng:

~~~properties
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

Ví dụ cấu trúc resource:

~~~text
src/main/resources/
└── graphql/
    ├── common.graphqls
    ├── book.graphqls
    ├── author.graphqls
    └── input/
        └── book-input.gqls
~~~

Spring GraphQL ghép các định nghĩa schema tìm được thành một GraphQL schema có thể thực thi. Vì vậy, nhiều file có thể cùng định nghĩa các type khác nhau hoặc mở rộng một type đã tồn tại bằng **extend type**. Mỗi type phải có định nghĩa hợp lệ trong schema tổng hợp.

Có thể dùng nhiều location pattern, tùy cách binder của phiên bản Spring Boot đang dùng hỗ trợ:

~~~properties
spring.graphql.schema.locations=classpath:graphql/,classpath:shared-graphql/
~~~

Nếu ứng dụng đóng gói schema trong một dependency JAR hoặc nhiều module, cần chọn location pattern có thể tìm thấy resource trong các artifact đó. Không nên mặc định đường dẫn tương đối theo working directory sẽ hoạt động giống classpath resource.

Khi schema không được tìm thấy, hãy kiểm tra:

1. File SDL có nằm dưới resource directory được đóng gói vào artifact hay không.
2. Tên file có phần mở rộng nằm trong danh sách cấu hình hay không.
3. Location có đúng prefix như **classpath:** hoặc pattern cần thiết hay không.
4. Có profile hoặc biến môi trường nào ghi đè location mặc định không.
5. Schema có lỗi cú pháp hoặc tham chiếu đến type chưa được định nghĩa không.

## 4. Cấu hình bằng application.properties

Ví dụ cấu hình cơ bản cho một ứng dụng quản lý sách:

~~~properties
spring.application.name=book-catalog

# GraphQL HTTP endpoint
spring.graphql.path=/api/graphql

# Schema SDL
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls

# GraphiQL chỉ bật trong môi trường phát triển
spring.graphql.graphiql.enabled=false

# WebSocket transport cho subscription
spring.graphql.websocket.path=/api/graphql
spring.graphql.websocket.connection-init-timeout=60s

# RSocket route nếu ứng dụng có bật RSocket transport
spring.graphql.rsocket.mapping=graphql
~~~

Các nhóm cấu hình có thể được tách riêng theo chức năng. Điều này giúp người đọc nhận ra endpoint, schema và transport nào đang được bật.

### Cấu hình tương đương bằng application.yml

Nếu dự án dùng YAML, cấu hình có thể viết:

~~~yaml
spring:
  application:
    name: book-catalog
  graphql:
    path: /api/graphql
    schema:
      locations: classpath:graphql/
      file-extensions:
        - .graphqls
        - .gqls
    graphiql:
      enabled: false
    websocket:
      path: /api/graphql
      connection-init-timeout: 60s
    rsocket:
      mapping: graphql
~~~

Hai định dạng biểu diễn cùng một cấu hình. Dùng **application.properties** khi nhóm thích các cặp key-value đơn giản; dùng **application.yml** khi cấu hình có nhiều nhóm lồng nhau. Không nên khai báo cùng một key ở nhiều file mà không hiểu quy tắc ưu tiên, vì giá trị cuối cùng có thể khác điều người đọc mong đợi.

## 5. Các thuộc tính Spring GraphQL thường dùng

Bảng dưới đây tóm tắt những nhóm thuộc tính thường gặp. Giá trị mặc định có thể thay đổi theo phiên bản Spring Boot, vì vậy cần kiểm tra configuration metadata của dependency đang dùng.

| Thuộc tính | Công dụng |
|---|---|
| **spring.graphql.path** | Path HTTP GraphQL endpoint |
| **spring.graphql.schema.locations** | Vị trí hoặc pattern tìm file schema |
| **spring.graphql.schema.file-extensions** | Các phần mở rộng file SDL được tìm kiếm |
| **spring.graphql.schema.printer.enabled** | Bật/tắt hỗ trợ in schema theo cấu hình Spring Boot |
| **spring.graphql.graphiql.enabled** | Bật/tắt giao diện GraphiQL |
| **spring.graphql.graphiql.path** | Path phục vụ giao diện GraphiQL |
| **spring.graphql.websocket.path** | Path WebSocket endpoint |
| **spring.graphql.websocket.connection-init-timeout** | Thời gian chờ thông điệp khởi tạo kết nối WebSocket |
| **spring.graphql.rsocket.mapping** | Route/mapping cho GraphQL qua RSocket |
| **spring.graphql.cors.allowed-origins** | Danh sách origin được phép truy cập cross-origin |
| **spring.graphql.cors.allowed-methods** | HTTP methods được phép qua CORS |
| **spring.graphql.cors.allowed-headers** | Request headers được phép |
| **spring.graphql.cors.allow-credentials** | Có cho phép gửi credentials qua CORS hay không |
| **spring.graphql.cors.max-age** | Thời gian cache kết quả preflight CORS |

Không phải tất cả các nhóm đều có tác dụng nếu transport tương ứng chưa được đưa vào classpath hoặc chưa được kích hoạt. Ví dụ, đặt **spring.graphql.websocket.path** không tự thêm WebSocket runtime dependency cho ứng dụng.

## 6. Bật GraphiQL cho môi trường phát triển

GraphiQL là giao diện trên trình duyệt giúp viết và gửi GraphQL operation, xem kết quả và khám phá schema. Có thể bật bằng:

~~~properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
~~~

Khi bật, developer có thể mở path đã cấu hình để thử Query, Mutation và variables. GraphiQL hữu ích trong quá trình học, phát triển và debug API.

Không nên bật giao diện phát triển một cách mặc định trên môi trường production. Công cụ này có thể làm lộ thông tin schema hoặc tạo điều kiện để người dùng thử các operation không cần thiết. Nếu production có yêu cầu hỗ trợ vận hành, hãy kiểm soát quyền truy cập bằng security policy và chỉ bật đúng tính năng cần thiết.

Ví dụ tách cấu hình:

**application-dev.properties**

~~~properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
~~~

**application-prod.properties**

~~~properties
spring.graphql.graphiql.enabled=false
~~~

GraphiQL là công cụ dành cho developer. Bật GraphiQL không thay thế authorization của GraphQL field và cũng không tự cấu hình CORS cho frontend.

## 7. Cấu hình WebSocket và Subscription

Nếu ứng dụng cần subscription qua WebSocket, có thể khai báo:

~~~properties
spring.graphql.websocket.path=/api/graphql
spring.graphql.websocket.connection-init-timeout=60s
~~~

Path WebSocket được cấu hình độc lập với **spring.graphql.path**. Nếu muốn HTTP và WebSocket dùng chung path, hãy đặt cả hai giá trị giống nhau. Việc dùng chung path không có nghĩa chúng dùng chung cách truyền dữ liệu: HTTP gửi request-response, còn WebSocket thực hiện handshake và trao đổi message trên kết nối lâu dài.

**connection-init-timeout** giới hạn thời gian chờ thông điệp khởi tạo kết nối theo protocol. Đây là timeout ở giai đoạn thiết lập kết nối, không phải thời gian tối đa cho một subscription tồn tại. Subscription cần chính sách timeout, giới hạn số lượng, cleanup và xử lý reconnect riêng.

Để WebSocket hoạt động, ứng dụng cần dependency WebSocket phù hợp với Spring MVC hoặc WebFlux stack. Reverse proxy cũng phải chuyển tiếp header upgrade và duy trì kết nối đủ lâu. Khi cấu hình không hoạt động, hãy kiểm tra cả dependency, path, proxy và protocol mà client sử dụng.

## 8. Cấu hình RSocket

Spring for GraphQL có thể phục vụ GraphQL qua RSocket nếu ứng dụng có RSocket integration và runtime phù hợp. Thuộc tính mapping xác định route được sử dụng:

~~~properties
spring.graphql.rsocket.mapping=graphql
~~~

Client cần gửi GraphQL payload tới route tương ứng theo interaction model mà server hỗ trợ. Request-response thường phù hợp cho Query hoặc Mutation; request-stream phù hợp cho kết quả phát liên tục.

RSocket không phải chỉ là một cách đặt URL khác cho HTTP. Nó có protocol, route, metadata và mô hình tương tác riêng. Khi triển khai, cần kiểm tra dependency RSocket server/client, security metadata, serialization, gateway và công cụ quan sát. Nếu ứng dụng chỉ cần API cho trình duyệt theo request-response, HTTP thường đơn giản hơn; nếu cần subscription trên web, WebSocket là lựa chọn quen thuộc hơn.

Việc đặt **spring.graphql.rsocket.mapping** không tự tạo route ở API gateway hoặc service mesh. Những thành phần bên ngoài vẫn cần được cấu hình để định tuyến traffic đến đúng RSocket server.

## 9. Cấu hình CORS cho frontend

CORS kiểm soát việc trình duyệt cho phép trang web ở origin này gọi tài nguyên của origin khác hay không. Nếu frontend và backend chạy trên origin khác nhau, cần cấu hình origin, method và header phù hợp.

Ví dụ chỉ cho phép frontend phát triển tại một origin:

~~~properties
spring.graphql.cors.allowed-origins=http://localhost:3000
spring.graphql.cors.allowed-methods=GET,POST
spring.graphql.cors.allowed-headers=Authorization,Content-Type
spring.graphql.cors.allow-credentials=false
spring.graphql.cors.max-age=30m
~~~

Khi triển khai production, thay origin local bằng domain thực tế:

~~~properties
spring.graphql.cors.allowed-origins=https://app.example.com
spring.graphql.cors.allowed-methods=GET,POST
spring.graphql.cors.allowed-headers=Authorization,Content-Type
spring.graphql.cors.allow-credentials=true
~~~

Nếu bật credentials, không dùng wildcard origin **\***. Hãy khai báo origin cụ thể hoặc cấu hình origin pattern có giới hạn theo yêu cầu của ứng dụng. CORS không phải cơ chế xác thực hay phân quyền; nó là chính sách trình duyệt cho phép JavaScript truy cập response. Client ngoài trình duyệt vẫn có thể gọi endpoint nếu không có lớp bảo vệ phía server.

Nếu ứng dụng đã có Spring Security hoặc cấu hình CORS ở gateway, hãy bảo đảm các lớp cấu hình không mâu thuẫn. Cấu hình CORS tại GraphQL endpoint không nhất thiết thay thế CORS policy của toàn bộ ứng dụng.

## 10. Profile và cấu hình theo môi trường

Một ứng dụng thường có các môi trường local, test, staging và production. Không nên sửa cùng một file mỗi lần triển khai. Spring Boot hỗ trợ profile-specific configuration.

**application.properties** chứa cấu hình chung:

~~~properties
spring.application.name=book-catalog
spring.graphql.path=/api/graphql
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

**application-dev.properties**:

~~~properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
spring.graphql.websocket.path=/api/graphql
~~~

**application-prod.properties**:

~~~properties
spring.graphql.graphiql.enabled=false
spring.graphql.websocket.path=/api/graphql
spring.graphql.cors.allowed-origins=https://app.example.com
spring.graphql.cors.allowed-methods=GET,POST
spring.graphql.cors.allowed-headers=Authorization,Content-Type
~~~

Kích hoạt profile bằng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=dev
~~~

Hoặc truyền khi chạy ứng dụng:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Profile cho phép giữ cùng một codebase nhưng thay đổi giá trị cấu hình theo môi trường. Các thiết lập bảo mật, origin, GraphiQL và endpoint cần được rà soát khi chuyển profile. Không đưa password, private key hoặc access token vào file cấu hình được commit; hãy dùng secret manager hoặc biến môi trường do nền tảng triển khai quản lý.

## 11. Override bằng biến môi trường và command line

Trong container hoặc nền tảng cloud, cấu hình thường được truyền bằng biến môi trường. Spring Boot hỗ trợ relaxed binding để chuyển tên property sang dạng environment variable.

Ví dụ:

| Property | Environment variable |
|---|---|
| **spring.graphql.path** | **SPRING_GRAPHQL_PATH** |
| **spring.graphql.websocket.path** | **SPRING_GRAPHQL_WEBSOCKET_PATH** |
| **spring.graphql.graphiql.enabled** | **SPRING_GRAPHQL_GRAPHIQL_ENABLED** |
| **spring.graphql.schema.locations** | **SPRING_GRAPHQL_SCHEMA_LOCATIONS** |
| **spring.graphql.websocket.connection-init-timeout** | **SPRING_GRAPHQL_WEBSOCKET_CONNECTIONINITTIMEOUT** |

Quy tắc chuyển đổi tên environment variable của Spring Boot là đổi dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang và viết hoa. Vì vậy các từ nối bằng dấu gạch ngang trong property name không nhất thiết được phân tách bằng dấu gạch dưới ở environment variable.

Ví dụ trong PowerShell:

~~~powershell
$env:SPRING_GRAPHQL_PATH = "/api/graphql"
$env:SPRING_GRAPHQL_GRAPHIQL_ENABLED = "false"
java -jar app.jar
~~~

Có thể override bằng command-line argument:

~~~bash
java -jar app.jar --spring.graphql.path=/internal/graphql
~~~

Khi cùng một property xuất hiện ở nhiều nguồn, Spring Boot áp dụng thứ tự ưu tiên của externalized configuration. Giá trị truyền từ command line hoặc system environment có thể ghi đè giá trị trong file cấu hình. Khi ứng dụng chạy sai endpoint, hãy kiểm tra cả file, profile đang active, biến môi trường và tham số command line.

## 12. Cấu hình danh sách và thời lượng

Một số thuộc tính nhận danh sách, ví dụ schema locations, file extensions, allowed origins và allowed methods. Trong **application.properties**, danh sách thường được phân tách bằng dấu phẩy:

~~~properties
spring.graphql.schema.file-extensions=.graphqls,.gqls
spring.graphql.cors.allowed-methods=GET,POST
~~~

Trong YAML, có thể viết thành sequence:

~~~yaml
spring:
  graphql:
    schema:
      file-extensions:
        - .graphqls
        - .gqls
    cors:
      allowed-methods:
        - GET
        - POST
~~~

Thuộc tính thời lượng có thể dùng đơn vị rõ ràng:

~~~properties
spring.graphql.websocket.connection-init-timeout=60s
~~~

Việc ghi đơn vị như **ms**, **s**, **m** giúp người đọc hiểu ý nghĩa giá trị và tránh nhầm số nguyên là milliseconds hay seconds. Không nên dùng một timeout rất dài để che giấu vấn đề kết nối; cần cân nhắc thời gian handshake, thời gian xử lý operation và thời gian sống của subscription như những chính sách khác nhau.

## 13. Properties không thay thế Java configuration

Application properties chỉ điều khiển những tùy chọn mà Spring Boot đã công bố. Nhiều hành vi của Spring for GraphQL cần logic hoặc thành phần runtime cụ thể.

| Nhu cầu | Cách cấu hình thường phù hợp |
|---|---|
| Đổi HTTP endpoint | **spring.graphql.path** |
| Chọn vị trí SDL | **spring.graphql.schema.locations** |
| Bật GraphiQL | **spring.graphql.graphiql.enabled** |
| Chọn WebSocket path | **spring.graphql.websocket.path** |
| Cấu hình CORS cơ bản | **spring.graphql.cors.*** |
| Ánh xạ Query/Mutation/field | Annotated controller như **@QueryMapping**, **@SchemaMapping** |
| Gom tải dữ liệu để giảm N+1 | **@BatchMapping** hoặc DataLoader |
| Chuyển đổi custom scalar | GraphQL scalar/coercing và runtime wiring |
| Xác định kiểu cụ thể cho interface/union | TypeResolver/runtime wiring |
| Chuẩn hóa lỗi nghiệp vụ | DataFetcherExceptionResolver |
| Phân quyền theo field/resource | Spring Security và kiểm tra quyền ở service/resolver |
| Thêm instrumentation | GraphQL Java Instrumentation hoặc tích hợp tương ứng |

Ví dụ, không có một property tổng quát để tự động biến mọi field quan hệ thành batch resolver. Cần thiết kế batch loader hoặc dùng **@BatchMapping** với logic Java phù hợp. Tương tự, bật CORS không tạo ra chính sách authorization cho từng field.

Khi cần thay đổi hành vi auto-configuration, hãy xem bean nào đang được Spring Boot tạo và extension point mà Spring for GraphQL cung cấp. Chỉ định nghĩa bean tùy chỉnh khi có yêu cầu cụ thể; một bean thay thế có thể làm một phần auto-configuration mặc định không còn được áp dụng.

## 14. Kiểm tra cấu hình hiệu lực

Khi một property không có tác dụng như mong đợi, nên kiểm tra theo thứ tự:

1. **Tên property:** chính tả, prefix và cấu trúc phân cấp có đúng không?
2. **Phiên bản:** property có tồn tại trong phiên bản Spring Boot của ứng dụng không?
3. **Profile:** profile mong muốn đã active chưa?
4. **Nguồn override:** biến môi trường, system property hoặc command line có ghi đè file không?
5. **Classpath:** dependency cho MVC, WebFlux, WebSocket hoặc RSocket đã có chưa?
6. **Resource:** file SDL có được đóng gói và tìm thấy theo location pattern không?
7. **Hạ tầng bên ngoài:** reverse proxy, gateway và CORS policy có khớp endpoint không?
8. **Auto-configuration:** có bean tùy chỉnh nào làm thay đổi điều kiện auto-configuration không?

Spring Boot Actuator có thể hỗ trợ quan sát môi trường và các bean được tạo nếu ứng dụng đã tích hợp và bảo vệ các endpoint quản trị phù hợp. Không nên công khai toàn bộ environment hoặc configuration endpoint cho người dùng không tin cậy vì chúng có thể làm lộ thông tin nhạy cảm.

IDE hỗ trợ Spring Boot configuration metadata có thể gợi ý property, kiểu dữ liệu và mô tả. Đây là cách hữu ích để kiểm tra tên property theo đúng dependency đang dùng. Khi cấu hình không được bind, kiểm tra startup log và cảnh báo về property không nhận diện được; không nên âm thầm giả định giá trị đã có hiệu lực.

## 15. Ví dụ cấu hình hoàn chỉnh theo hai môi trường

Một cấu hình thực tế có thể giữ các giá trị chung trong application.yml:

~~~yaml
spring:
  application:
    name: book-catalog
  graphql:
    path: /api/graphql
    schema:
      locations: classpath:graphql/
      file-extensions:
        - .graphqls
        - .gqls
    websocket:
      path: /api/graphql
      connection-init-timeout: 60s
~~~

Trong application-dev.yml:

~~~yaml
spring:
  graphql:
    graphiql:
      enabled: true
      path: /graphiql
    cors:
      allowed-origins:
        - http://localhost:3000
      allowed-methods:
        - GET
        - POST
      allowed-headers:
        - Authorization
        - Content-Type
~~~

Trong application-prod.yml:

~~~yaml
spring:
  graphql:
    graphiql:
      enabled: false
    cors:
      allowed-origins:
        - https://app.example.com
      allowed-methods:
        - GET
        - POST
      allowed-headers:
        - Authorization
        - Content-Type
      allow-credentials: true
~~~

Với cấu hình production có credentials, origin phải được chỉ định rõ ràng. Các secret dùng để xác thực vẫn được quản lý qua secret store hoặc môi trường triển khai, không đặt trong ví dụ cấu hình được commit vào repository.

## 16. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Gọi **/graphql** bị 404 sau khi đổi path | Client hoặc proxy vẫn dùng path cũ | Kiểm tra **spring.graphql.path**, context path và gateway |
| Schema không được tải | Location hoặc file extension không khớp | Kiểm tra **spring.graphql.schema.locations** và resource trong artifact |
| GraphiQL không mở được | Chưa bật hoặc dùng sai path | Kiểm tra **spring.graphql.graphiql.enabled** và path |
| WebSocket handshake thất bại | Thiếu dependency, sai path hoặc proxy không upgrade | Kiểm tra web stack, **spring.graphql.websocket.path** và proxy |
| Subscription bị ngắt sớm | Timeout hoặc giới hạn kết nối ở proxy/server | Kiểm tra connection timeout, idle timeout và cleanup |
| Frontend báo CORS | Origin, method hoặc header chưa được cho phép | Kiểm tra **spring.graphql.cors.*** và policy ở Security/gateway |
| Property có trong file nhưng không có tác dụng | Sai phiên bản, sai tên hoặc bị nguồn khác override | Kiểm tra metadata, active profile, environment và command line |
| RSocket route không nhận request | Chưa có RSocket runtime hoặc route không khớp | Kiểm tra dependency, mapping và cấu hình server/gateway |

## 17. Quy trình cấu hình một ứng dụng mới

Khi bắt đầu một Spring for GraphQL service, có thể thực hiện theo trình tự:

1. Chọn web stack MVC hoặc WebFlux và thêm starter phù hợp.
2. Đặt schema SDL dưới resource location mặc định hoặc khai báo location riêng.
3. Đặt HTTP endpoint bằng **spring.graphql.path** nếu cần thay đổi convention.
4. Chỉ bật GraphiQL trong môi trường phát triển hoặc môi trường được kiểm soát.
5. Nếu cần Subscription, thêm WebSocket support và cấu hình path, timeout.
6. Nếu cần giao tiếp RSocket, cấu hình RSocket runtime, mapping và metadata.
7. Thiết lập CORS theo origin thực tế của frontend.
8. Tách profile và secret theo môi trường triển khai.
9. Kiểm tra property binding, schema loading, endpoint và transport bằng test phù hợp.
10. Rà soát các bean tùy chỉnh để bảo đảm không vô tình thay thế auto-configuration cần thiết.

Application properties giúp Spring Boot điều chỉnh những lựa chọn cấu hình phổ biến của Spring for GraphQL một cách rõ ràng và nhất quán. Khi hiểu property nào thuộc schema, endpoint, transport hay môi trường, developer có thể xử lý phần lớn thay đổi vận hành mà không làm rối logic resolver. Những yêu cầu có tính nghiệp vụ hoặc cần hành vi runtime tùy chỉnh vẫn nên được triển khai bằng extension point của Spring for GraphQL và GraphQL Java.
