# Endpoint `modulith` và vị trí trong Spring Boot Actuator

> **Chương:** Module Actuator  
> **Phạm vi:** Spring Modulith trong ứng dụng Spring Boot, tập trung vào việc công bố mô hình application module qua Actuator để kiểm chứng ranh giới kiến trúc khi ứng dụng vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích endpoint `modulith` thuộc hệ sinh thái **Spring Boot Actuator** và có vai trò gì trong Spring Modulith.
2. Kích hoạt `/actuator/modulith` bằng dependency và cấu hình HTTP exposure phù hợp; phân biệt việc **có endpoint**, **được phép truy cập**, **được expose** và **đã được xác thực**.
3. Đọc JSON mô tả module, base package, quan hệ cha–con và các dependency có kiểu `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER`.
4. Dùng dữ liệu endpoint để kiểm tra mô hình ranh giới module đã được nhận diện trong một ứng dụng đang chạy.
5. Phân biệt **module structure** với tài liệu module được sinh khi build/test, cũng như metrics, tracing và event publications khi chạy.
6. Chẩn đoán những trường hợp endpoint trả `404`, `401/403`, không xuất hiện ở discovery page hoặc cho kết quả khác kỳ vọng.

## 2. Endpoint `modulith` là gì?

Spring Modulith giúp phát hiện các **application module** trong ứng dụng Spring Boot, mô tả API module và quan hệ phụ thuộc giữa chúng. Ngoài việc sinh tài liệu module graph khi phát triển, Spring Modulith có khả năng đưa **thông tin kiến trúc đó vào ứng dụng đang vận hành** thông qua một endpoint mở rộng của Spring Boot Actuator.

Endpoint có **ID là `modulith`**, do thành phần `ApplicationModulesEndpoint` của Spring Modulith cung cấp. Với đường dẫn Actuator mặc định và cổng HTTP mặc định của ứng dụng mẫu:

~~~http
GET http://localhost:8080/actuator/modulith
~~~

Đây là một **management endpoint**: nó nằm cùng cơ chế đăng ký, exposure, truy cập và bảo mật với các endpoint Actuator khác. Nó không phải REST API nghiệp vụ như `POST /orders`; người dùng endpoint thường là lập trình viên, người vận hành, công cụ kiểm tra hoặc hệ thống quản trị nội bộ.

~~~mermaid
flowchart TB
    subgraph App["Ứng dụng Spring Boot"]
        subgraph Modules["Application modules"]
            Orders["orders"]
            Inventory["inventory"]
            Notifications["notifications"]
        end
        Metadata["Spring Modulith<br/>ApplicationModules metadata"]
        Actuator["Spring Boot Actuator"]
        ModEndpoint["Endpoint ID: modulith"]
        Health["health"]
        Metrics["metrics"]
        HttpTrace["traces trong backend quan sát"]
        Modules --> Metadata
        Metadata --> ModEndpoint
        ModEndpoint --> Actuator
        Health --> Actuator
        Metrics --> Actuator
    end
    Client["Công cụ quản trị nội bộ"] -->|"GET /actuator/modulith"| Actuator
    App -.-> HttpTrace
~~~

Sơ đồ thể hiện vị trí khái niệm: endpoint `modulith` là một thành phần được Spring Modulith đăng ký **vào Actuator**, còn tracing backend là hệ thống quan sát riêng. Endpoint không tự tạo ra trace hoặc metrics chỉ vì đã được thêm vào.

## 3. Endpoint nằm ở đâu so với các khả năng khác?

| Khả năng | Câu hỏi trả lời | Kết quả điển hình |
| --- | --- | --- |
| `/actuator/modulith` | Ứng dụng hiện được nhận diện gồm những module nào? Chúng phụ thuộc nhau thế nào? | JSON module metadata và dependency graph |
| `/actuator/health` | Ứng dụng có đang sẵn sàng hoặc khỏe mạnh không? | Trạng thái health, thông tin chi tiết theo quyền |
| `/actuator/info` | Có metadata bổ sung nào về ứng dụng không? | Các trường info được cấu hình |
| `/actuator/metrics` | Có những metric nào đang được ghi nhận? | Danh sách/tên metric và phép đo tùy cấu hình |
| Tracing qua Micrometer và exporter | Request hoặc sự kiện đi qua các operation nào, bao lâu, trong trace nào? | Span/trace trên Zipkin, Tempo, Jaeger... |
| Tài liệu sinh bởi Spring Modulith `Documenter` | Cần bản vẽ và tài liệu kiến trúc để đọc hoặc lưu cùng source code? | Diagram, canvas hay tài liệu được sinh trong quá trình phát triển/test |
| Event Publication Registry | Một publication tới event listener đã hoàn tất hay cần xử lý lại? | Trạng thái publication được lưu theo cơ chế event publication đã cấu hình |

**Điểm cốt lõi:** `modulith` cho cái nhìn về **cấu trúc kiến trúc** mà Spring Modulith nhận diện; trace và metrics cho cái nhìn về **hành vi thực thi**. Một module có trong JSON không có nghĩa nó đã được gọi ở request vừa rồi. Một dependency tồn tại trong cấu trúc cũng không chứng minh module đích đã gây lỗi hoặc chậm.

## 4. Kích hoạt endpoint trong dự án Spring Boot

### 4.1. Chọn dependency

Cách gọn nhất nếu muốn cả Module Actuator và observability là dùng starter:

~~~xml
<!-- pom.xml: ví dụ với dependency management/BOM phù hợp -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Starter `spring-modulith-starter-insight` tập hợp hỗ trợ Actuator module, observability và Spring Boot Actuator. Tuy nhiên, để **xuất traces** sang backend cần thêm bridge/exporter tương ứng; starter không tự cấu hình mọi hệ thống tracing bên ngoài.

Nếu chỉ cần endpoint kiến trúc, có thể khai báo các dependency hẹp hơn:

~~~xml
<!-- pom.xml: phần Actuator tối thiểu -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-actuator</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Tương đương trong Gradle:

~~~groovy
// build.gradle, khi đã áp dụng Spring Boot và BOM tương thích
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

**Chọn một cách** theo nhu cầu; không cần khai báo trùng `spring-modulith-actuator` nếu starter Insight đã kéo dependency này vào. Các ví dụ cố ý không pin phiên bản: dùng **Spring Modulith BOM / Spring Boot dependency management phù hợp với dự án** để tránh kết hợp các phiên bản không tương thích.

### 4.2. Expose endpoint qua HTTP

Spring Boot Actuator quản lý việc endpoint có được công bố qua web hay không. Theo cấu hình mặc định của Spring Boot, chỉ `health` được expose qua HTTP; vì vậy hãy **khai báo `modulith` tường minh** cho ứng dụng thử nghiệm:

~~~yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith"
~~~

Nếu chỉ định kiểm tra cấu trúc module, có thể giữ phạm vi hẹp hơn:

~~~properties
# application.properties
management.endpoints.web.exposure.include=health,modulith
~~~

Khi ứng dụng dùng cổng `8080`, đường dẫn mặc định của endpoint sẽ là `http://localhost:8080/actuator/modulith`. Bạn phải xét **hai điều kiện riêng**: Spring có đăng ký endpoint trong ApplicationContext và Actuator có expose endpoint qua giao thức được gọi. Nếu bị chặn bởi cấu hình access hoặc security, việc thêm `exposure.include` cũng chưa đủ.

### 4.3. Trường hợp quản lý ở cổng hoặc base path riêng

Một triển khai có thể tách management server:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: "/manage"
      exposure:
        include: "health,modulith"
~~~

Khi đó đường dẫn để truy vấn từ mạng có quyền truy cập là:

~~~http
GET http://localhost:8081/manage/modulith
~~~

Cổng `8080` vẫn phục vụ API nghiệp vụ, trong khi cổng `8081` phục vụ management endpoint. Nếu dùng `server.servlet.context-path`, `spring.webflux.base-path` hoặc `management.server.base-path`, hãy tính đường dẫn theo quy tắc của Spring Boot phiên bản đang chạy. Có thể cấu hình riêng `management.endpoints.web.path-mapping.modulith` để đổi phần đường dẫn của endpoint.

### 4.4. Bảo vệ endpoint

JSON của `modulith` có thể tiết lộ tên module, base package và dependency nội bộ. Do đó, **chỉ expose cho đối tượng quản trị có quyền**, ví dụ:

- Chỉ cho truy cập từ mạng quản trị, VPN hoặc management port không mở ra internet.
- Xác thực và phân quyền với Spring Security hoặc hệ thống gateway; kiểm tra các `SecurityFilterChain` tự cấu hình để chắc chắn Actuator vẫn được bảo vệ.
- Chỉ include các endpoint cần thiết, không mở toàn bộ Actuator bằng `include: "*"` trong môi trường production khi chưa đánh giá quyền truy cập.
- Không dùng endpoint để trả metadata kiến trúc cho người dùng cuối của API nghiệp vụ.

Phân biệt lỗi: `401 Unauthorized` thường là chưa xác thực, `403 Forbidden` là không đủ quyền; `404 Not Found` có thể là endpoint chưa được tạo, chưa expose hoặc bạn đang gọi sai path/port.

## 5. Đọc discovery page trước khi gọi endpoint

Actuator có discovery page mô tả các endpoint HTTP đang được expose. Với base path mặc định:

~~~bash
curl -i http://localhost:8080/actuator
~~~

Ví dụ rút gọn từ cấu trúc discovery response (danh sách thực tế phụ thuộc exposure và security):

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://localhost:8080/actuator/health",
      "templated": false
    },
    "modulith": {
      "href": "http://localhost:8080/actuator/modulith",
      "templated": false
    }
  }
}
~~~

Nếu thấy relation `"modulith"`, ứng dụng đang quảng bá URL truy cập endpoint này. Điều đó **không thay thế** việc xác thực/quyền khi gọi URL; endpoint có thể bị security bảo vệ. Ngược lại, discovery page có thể bị tắt hoặc đổi URL, vì thế **không nhìn thấy link** chưa phải bằng chứng duy nhất rằng endpoint không tồn tại.

Sau đó thử:

~~~bash
curl -i http://localhost:8080/actuator/modulith
~~~

Ở môi trường có bảo mật, dùng cơ chế xác thực được hệ thống cung cấp. Không đưa thông tin đăng nhập, access token hoặc dữ liệu nội bộ vào log công khai khi chia sẻ kết quả.

## 6. Cấu trúc JSON của `/actuator/modulith`

Endpoint trả về một đối tượng JSON, trong đó **mỗi key cấp cao nhất là tên kỹ thuật của một application module**.

Giả sử ứng dụng thương mại điện tử nhận diện ba module `orders`, `inventory` và `notifications`:

~~~json
{
  "orders": {
    "basePackage": "com.example.shop.orders",
    "displayName": "Orders",
    "dependencies": [
      {
        "target": "inventory",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "inventory": {
    "basePackage": "com.example.shop.inventory",
    "displayName": "Inventory",
    "dependencies": []
  },
  "notifications": {
    "basePackage": "com.example.shop.notifications",
    "displayName": "Notifications",
    "dependencies": [
      {
        "target": "orders",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

Đây là **dữ liệu ví dụ minh họa**, không phải response cố định của Spring Modulith. Các module và dependency sẽ khác theo package, cấu hình kiến trúc và code thực tế.

### 6.1. Những trường quan trọng

| JSONPath | Ý nghĩa | Cách đọc |
| --- | --- | --- |
| `$.{moduleName}` | Tên kỹ thuật của module, đồng thời là đích tham chiếu trong `dependencies[].target` | `orders`, `inventory` |
| `$.{moduleName}.displayName` | Tên dễ đọc của module | `Orders` |
| `$.{moduleName}.basePackage` | Package gốc của module | `com.example.shop.orders` |
| `$.{moduleName}.parent` | Tên module cha, nếu là module lồng nhau | Trường **tùy chọn** |
| `$.{moduleName}.nested` | Danh sách tên module con, nếu có | Trường **tùy chọn** |
| `$.{moduleName}.dependencies[]` | Các dependency **đi ra từ module hiện tại** | Danh sách rỗng nếu không có dependency được ghi nhận |
| `$.{moduleName}.dependencies[].target` | Tên kỹ thuật của module đích | Có thể đối chiếu với key cấp cao nhất |
| `$.{moduleName}.dependencies[].types[]` | Một hoặc nhiều kiểu phụ thuộc đến module đích | `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER` |

Với JSON ví dụ, `orders.dependencies[0].target = "inventory"` có nghĩa Spring Modulith nhận diện một quan hệ **từ `orders` sang `inventory`**. Không đọc ngược rằng `inventory` phụ thuộc vào `orders`.

### 6.2. Ba kiểu dependency

| Kiểu | Diễn giải | Ví dụ minh họa |
| --- | --- | --- |
| `DEFAULT` | Phụ thuộc kiểu thông thường giữa các type, không được phân loại thành hai loại chuyên biệt bên cạnh | Mã trong `orders` tham chiếu type do module `inventory` công bố |
| `USES_COMPONENT` | Module hiện tại sử dụng Spring component/bean của module đích | `OrderService` sử dụng `InventoryApi` |
| `EVENT_LISTENER` | Module hiện tại khai báo cơ chế lắng nghe sự kiện từ module đích | `notifications` có listener cho sự kiện của `orders` |

Một dependency có thể có **nhiều type đồng thời**, ví dụ:

~~~json
{
  "target": "orders",
  "types": ["EVENT_LISTENER", "USES_COMPONENT"]
}
~~~

Đây là sự tổng hợp **quan hệ kiến trúc**. Một type `EVENT_LISTENER` không cho biết sự kiện đã từng được publish hay listener đã xử lý thành công. Muốn biết hành vi thực tế, phải kết hợp công cụ quan sát/event publication phù hợp.

### 6.3. Nếu module lồng nhau

Khi dự án dùng nested application modules, kết quả có thể có quan hệ `parent` và `nested`. Ví dụ minh họa rút gọn:

~~~json
{
  "sales": {
    "basePackage": "com.example.sales",
    "displayName": "Sales",
    "nested": ["sales::pricing"],
    "dependencies": []
  },
  "sales::pricing": {
    "basePackage": "com.example.sales.pricing",
    "displayName": "Pricing",
    "parent": "sales",
    "dependencies": []
  }
}
~~~

Các chuỗi tên nested trong ví dụ chỉ giúp hình dung **quan hệ khóa tham chiếu**; dạng định danh được phát ra phụ thuộc mô hình module và phiên bản đang dùng. Khi phân tích dữ liệu thật, coi các giá trị `parent`, `nested[]` và `dependencies[].target` là tham chiếu đến key module xuất hiện trong **cùng response**.

## 7. Đọc module graph từ JSON

Giả sử ta có JSON của phần 6. Vẽ lại mũi tên theo hướng **module chứa `dependencies[]` → module đích**:

~~~mermaid
flowchart LR
    Orders["orders"] -->|"USES_COMPONENT"| Inventory["inventory"]
    Notifications["notifications"] -->|"EVENT_LISTENER"| Orders
~~~

Graph trả lời ba nhóm câu hỏi quan trọng:

1. **Module nào tồn tại?** Liệt kê các key cấp cao nhất; so sánh với thiết kế module mong muốn.
2. **Ranh giới package ở đâu?** Đọc `basePackage` và nested modules để kiểm tra cách chia mã nguồn.
3. **Chiều dependency ra sao?** Với mỗi module, duyệt `dependencies[]` và `target`; từ đó tìm dependency bất ngờ hoặc hướng phụ thuộc không phù hợp kiến trúc.

Ví dụ, thiết kế đặt `payments` và `orders` là hai module độc lập, chỉ cho `orders → payments`. Nếu response thực tế lại có `payments → orders`, đây là tín hiệu cần **kiểm tra source code hoặc cấu hình module**. Bản thân endpoint không kết luận đây là vi phạm: mô hình được phép phụ thuộc ra sao còn do quy tắc kiến trúc của dự án.

**Lưu ý về static versus runtime:** Spring Modulith xác định cấu trúc từ code và metadata trong ứng dụng chạy. Endpoint **không** phải bản ghi từng lời gọi runtime, không biểu thị tần suất sử dụng và không tự đo thời gian chạy giữa module. “Có dependency” khác với “đã thực sự gọi trong request này”.

## 8. Mối quan hệ với tài liệu kiến trúc và observability

Spring Modulith thường xuất hiện trong hệ thống cùng lúc dưới ba hình thức:

~~~mermaid
flowchart LR
    Code["Source code và metadata module"]
    Docs["Tài liệu / module diagrams<br/>tạo ở build/test"]
    Endpoint["Actuator /modulith<br/>mô hình module của ứng dụng đang chạy"]
    Obs["Observation, metrics, traces<br/>các tương tác đã diễn ra"]
    Code --> Docs
    Code --> Endpoint
    Code --> Obs
~~~

- **Tài liệu module:** `Documenter` có thể sinh module diagrams, canvas và các tài liệu trong quy trình phát triển. Đầu ra hữu ích khi review kiến trúc, viết tài liệu hoặc lưu artifact cùng version source. Nó không phải HTTP endpoint.
- **Endpoint module:** `/actuator/modulith` đưa thông tin module graph của **binary đang chạy** ra qua Actuator. Nó hữu ích để xác nhận môi trường nào đã triển khai cấu trúc module nào, và có thể so sánh với thiết kế kỳ vọng.
- **Quan sát runtime:** các instrumentation của Spring Modulith, Micrometer, Actuator metrics và tracing backend cho biết lời gọi/sự kiện thực sự xảy ra thế nào. Thông tin module chỉ là một phần ngữ cảnh giúp đọc trace.

Trong module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`, sự kết hợp này giải quyết mục tiêu “**dùng module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành**”. Endpoint chứng minh **cấu trúc được nhận diện**; event metrics theo dõi **hoạt động phát sự kiện**; tracing và context propagation giúp kết nối **đường đi xử lý thực tế** qua module/thread.

Điều đó cũng có nghĩa:

- Thêm `spring-modulith-actuator` **không** tự mang trace context qua `Executor` hoặc Reactor.
- Thêm tracing bridge/exporter **không** tự expose `/actuator/modulith`.
- Metrics công bố event **không** chứng minh event đã được listener xử lý xong; cần theo dõi kết quả xử lý và cơ chế publication registry tương ứng.

## 9. Quy trình kiểm tra endpoint từ đầu đến cuối

### Bước 1 — Kiểm tra dependency và application module

Ứng dụng cần có Spring Modulith và module được nhận diện theo cấu trúc package/cấu hình của dự án. Chọn `spring-modulith-starter-insight` hoặc `spring-modulith-actuator` cộng với `spring-boot-starter-actuator`. Nếu dự án tùy biến cách phát hiện module, hãy đặt cấu hình đó trong **production sources** khi cần cho runtime; cấu hình chỉ có trong test có thể khiến endpoint nhận diện khác với tài liệu tạo trong test.

### Bước 2 — Cấu hình exposure rõ ràng

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,modulith"
~~~

Chạy ứng dụng ở môi trường thử nghiệm, ghi nhận cổng và base path thực tế. Nếu hệ thống có Spring Security, dùng danh tính được cấp quyền đọc management endpoint.

### Bước 3 — Truy vấn discovery page và endpoint

~~~bash
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/modulith
~~~

Xác nhận HTTP thành công và response endpoint có JSON object chứa các module. Nếu response trả về trang lỗi HTML hoặc redirect đến trang login, đừng xem đó là module graph hợp lệ.

### Bước 4 — Đối chiếu cấu trúc

Dựa trên JSON thực tế, lập bảng:

| Module | Base package | Dependency trực tiếp | Type |
| --- | --- | --- | --- |
| `orders` | `com.example.shop.orders` | `inventory` | `USES_COMPONENT` |
| `inventory` | `com.example.shop.inventory` | Không có | — |
| `notifications` | `com.example.shop.notifications` | `orders` | `EVENT_LISTENER` |

Đây là bảng lấy theo **response giả định** của phần 6. Trong ứng dụng thật, phải điền bằng JSON truy vấn được. Nếu số lượng module thấp hơn kỳ vọng, hãy kiểm tra root package, cấu hình module detection và sự khác biệt giữa artifact vừa build với phiên bản đang deploy.

### Bước 5 — So sánh với các tín hiệu runtime

Thực hiện một luồng nghiệp vụ (ví dụ tạo đơn hàng), rồi xem metrics/traces đã cấu hình. Một module có trong Actuator nhưng không xuất hiện trong trace có thể **chưa được gọi**, **không được instrument**, **bị sampling loại bỏ** hoặc **bị mất context**. Chỉ từ JSON endpoint không thể phân biệt các khả năng này.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Khả năng cần kiểm tra | Hành động đề xuất |
| --- | --- | --- |
| `GET /actuator/modulith` trả `404` | Thiếu dependency, endpoint bị hạn chế access, chưa expose, path/port khác | Kiểm tra dependency, `management.endpoints.web.exposure.include`, `management.endpoint.modulith.access` nếu phiên bản hỗ trợ, base path và port |
| Discovery page không có `modulith` | Endpoint không được expose, discovery tắt hoặc link bị ảnh hưởng bởi cấu hình/web security | Truy vấn đúng endpoint và xem cấu hình Actuator/management port |
| Trả `401` hoặc `403` | Đang bị chặn bởi xác thực/phân quyền | Cấp quyền đọc endpoint theo chính sách quản trị; không tắt bảo mật chỉ để thử |
| Trả `200` nhưng không thấy module mong muốn | Module detection khác thiết kế hoặc runtime artifact chưa cập nhật | Kiểm tra package, module customization trong production source, bản deploy |
| Kết quả khác diagram đã sinh trong test | Code/version và cấu hình module ở test khác runtime | So sánh artifact, môi trường và cách phát hiện module |
| Có mũi tên phụ thuộc ngược kỳ vọng | Code thật có type reference, bean use hoặc event listener | Kiểm tra module nguồn và loại `dependencies[].types[]` rồi chạy quy tắc kiểm chứng kiến trúc |
| Không thấy trace mặc dù endpoint có module | Chưa tích hợp observability, tracer/exporter, sampling hoặc propagation | Kiểm tra tracing độc lập; endpoint cấu trúc không bảo đảm trace |
| URL trước đây hoạt động, sau đổi cấu hình thì mất | Thay đổi base path, management port, path mapping hoặc security chain | Xác minh cấu hình HTTP và security của đúng môi trường |

**Phân biệt access và exposure:** với Spring Boot phiên bản mới, `management.endpoint.<id>.access` và `management.endpoints.access.default` có thể giới hạn tính sẵn có của endpoint, ngoài `management.endpoints.web.exposure.include`. Endpoint bị cấm access có thể bị loại khỏi ApplicationContext; việc chỉ thêm nó vào danh sách HTTP exposure sẽ không khôi phục được endpoint.

## 11. Bài thực hành: xác nhận module graph của bản đang chạy

**Bối cảnh:** bạn triển khai ứng dụng Spring Boot có ba module `orders`, `inventory`, `notifications`. Thiết kế mong muốn: `orders` được phép dùng `inventory`; `notifications` lắng nghe sự kiện `orders`; `inventory` không phụ thuộc vào hai module còn lại.

Thực hiện:

1. Thêm dependency Actuator của Spring Modulith theo phần 4, chạy ứng dụng ở profile thử nghiệm.
2. Expose duy nhất `health` và `modulith` qua HTTP; bảo vệ quyền truy cập.
3. Truy vấn `GET /actuator` để kiểm tra discovery; tiếp tục truy vấn `GET /actuator/modulith`.
4. Viết ra các cặp **module nguồn → module đích** theo `dependencies[]` và phân loại theo `types[]`.
5. Dựa trên response thật, vẽ một module graph ngắn. Chỉ ra ít nhất một dependency hợp lệ và giải thích lý do. Nếu có dependency lạ, tra code nguồn thay vì kết luận vi phạm chỉ dựa vào endpoint.
6. Gửi một request `POST /orders`, theo dõi tracing/metrics nếu đã bật, rồi giải thích vì sao số span nhìn thấy có thể khác số mũi tên trên graph.
7. Thử đổi `management.endpoints.web.base-path` thành `/manage` và xác nhận URL mới (theo port hiện hành), sau đó hoàn nguyên cấu hình thử nghiệm.

**Tiêu chí đạt:**

- Chỉ đúng endpoint ID và URL Actuator; biết xử lý thay đổi cổng/path.
- Giải thích được cấu trúc JSON và hướng dependency; không đọc `EVENT_LISTENER` thành bằng chứng sự kiện đã chạy.
- Chỉ ra được vai trò khác nhau của `modulith`, tài liệu `Documenter` và tracing.
- Biết cách giới hạn exposure và chẩn đoán các mã lỗi HTTP phổ biến.

## 12. Ghi nhớ và tài liệu tham khảo

**Ghi nhớ:** `/actuator/modulith` là cửa sổ **kiến trúc module của ứng dụng đang chạy**, được phục vụ theo cơ chế Spring Boot Actuator. Nó hữu ích để đối chiếu các module và dependency với thiết kế, nhưng không phải module diagram generator, không phải công cụ trace và không tự cho biết sự kiện đã được xử lý thành công. Khi cần giải thích kiến trúc **và** hành vi vận hành, hãy kết hợp endpoint này với kiểm thử ranh giới, metrics, tracing và cơ chế truyền context.

Tài liệu chính thức:

- [Spring Modulith — Production-ready Features / Application Module Actuator](https://docs.spring.io/spring-modulith/reference/production-ready.html)
- [Spring Modulith — `ApplicationModulesEndpoint` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/actuator/ApplicationModulesEndpoint.html)
- [Spring Modulith — Appendix: modules and starters](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Boot — Actuator Endpoints: access, exposure, security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)

> **Lưu ý phiên bản:** tên endpoint hiện hành theo tài liệu Spring Modulith là `modulith`; một số ví dụ của bản rất cũ có thể dùng tên khác. Các thuộc tính access/exposure, dependency và cơ chế security chịu ảnh hưởng của phiên bản Spring Boot/Spring Modulith. Khi triển khai, đối chiếu reference guide đúng với BOM của dự án.
