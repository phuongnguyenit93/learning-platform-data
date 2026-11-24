# Cú pháp rút gọn so với khai báo `name` và `args` đầy đủ trong Spring Cloud Gateway

Trong **SPRING_CLOUD_GATEWAY**, một route thường gồm URI đích, **route predicates** để chọn request và **Gateway filters** để biến đổi hoặc kiểm soát luồng xử lý. Khi đọc tài liệu, bạn sẽ gặp hai cách khai báo cùng một predicate/filter:

- **Cú pháp rút gọn (shortcut notation)**: gói tên factory và các tham số vào một chuỗi như `Path=/api/orders/**` hoặc `StripPrefix=1`.
- **Cú pháp đầy đủ (fully expanded notation)**: viết rõ tên factory trong `name`, rồi đặt các tham số có tên dưới `args`.

Bài này thuộc chương **Cấu hình tuyến**, giải thích cách chuyển đổi giữa hai cách viết, xác định khi nào chúng tương đương, cách tránh lỗi phân tách tham số và cách kiểm chứng bằng request thực. Đây là kỹ năng nền để cấu hình định tuyến, biến đổi path/header, khám phá dịch vụ, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request trong hệ thống microservices.

> **Phạm vi:** Các ví dụ YAML dùng cách khai báo phổ biến ở **Spring Cloud Gateway Server WebFlux 4.x** với `spring.cloud.gateway.routes`. Ở các dòng phát hành khác, namespace hoặc tên starter có thể thay đổi; Gateway Server MVC cũng có cấu hình và API riêng. Hãy chọn tài liệu khớp đúng phiên bản và biến thể trước khi sao chép.

## 1. Hai cách viết biểu diễn cùng một định nghĩa

Ví dụ một route nhận request tới `/api/orders/**` và bỏ phân đoạn path đầu tiên trước khi chuyển tiếp tới backend.

**Cú pháp rút gọn:**

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

**Cú pháp đầy đủ:**

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/orders/**
          filters:
            - name: StripPrefix
              args:
                parts: 1
~~~

Ở hai ví dụ, giả định backend `localhost:9090` có endpoint `GET /orders/42`, thì `GET /api/orders/42` đi qua gateway sẽ được chuyển tiếp thành `GET /orders/42` (nếu không có filter khác đổi path). Cả hai cách đều mô tả **cùng predicate Path** và **cùng filter StripPrefix** với giá trị tương đương.

Điểm chung không nằm ở việc chuỗi YAML giống nhau, mà ở **cấu hình cuối cùng được bind cho factory**:

| Thành phần | Rút gọn | Đầy đủ | Ý nghĩa |
|---|---|---|---|
| Predicate | `Path=/api/orders/**` | `name: Path` + `args.patterns` | So khớp URL path |
| Filter | `StripPrefix=1` | `name: StripPrefix` + `args.parts: 1` | Loại một phân đoạn ở đầu path |
| Nơi khai báo | Một phần tử chuỗi trong danh sách | Một phần tử object/map trong danh sách | Đều được đọc thành định nghĩa route |
| Khả năng diễn đạt | Gọn, các giá trị theo thứ tự vị trí | Tường minh, giá trị có tên trường | Dễ rà soát khi có nhiều tham số |

**Không phải có hai loại filter khác nhau.** Trong các trường hợp tương đương, Gateway chuyển cả hai cách khai báo thành một cấu hình dùng chung và tạo object xử lý tương ứng.

## 2. Cấu trúc YAML cần nhớ

Một `RouteDefinition` mô tả ID, URI, predicates và filters:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: my-route
          uri: http://localhost:9090
          order: 0
          predicates: []
          filters: []
~~~

Ba tầng không được nhầm lẫn:

1. **Route**: `id`, `uri`, `order`, `predicates`, `filters`. `uri` là đích routing; nó không phải tham số của predicate/filter.
2. **Một phần tử predicate hoặc filter**: có thể là chuỗi shortcut hoặc map chứa `name` và `args`.
3. **Tham số của factory**: những khóa cụ thể dưới `args`, ví dụ `patterns`, `parts`, `name`, `value`.

Cùng chữ `name` nhưng hai vị trí khác nhau:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

- `filters[0].name` chọn factory **AddRequestHeader**.
- `filters[0].args.name` là **tên HTTP header** `X-Edge-Origin`.
- `filters[0].args.value` là **giá trị header** `gateway`.

Nếu đặt `X-Edge-Origin` ngay vào `filters[0].name` hoặc bỏ `args` khi dùng dạng đầy đủ, Gateway sẽ không có đúng tên factory/tham số.

## 3. Gateway diễn giải cú pháp rút gọn như thế nào?

Cú pháp rút gọn thường có mẫu:

~~~text
- <FactoryName>=<giá trị-1>,<giá trị-2>,...
~~~

Ví dụ:

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
filters:
  - AddRequestHeader=X-Edge-Origin,gateway
  - StripPrefix=1
~~~

Một cách hình dung quá trình nạp route WebFlux:

~~~mermaid
flowchart TD
    Y["YAML route"] --> D{"Một phần tử predicate/filter có dạng nào?"}
    D -->|"Chuỗi Shortcut"| S["Tách tên factory và các giá trị theo vị trí"]
    D -->|"Map name + args"| F["Lấy tên factory và map tham số có tên"]
    S --> B["Bind và kiểm tra cấu hình factory"]
    F --> B
    B --> C["RoutePredicateFactory / GatewayFilterFactory"]
    C --> R["Tạo predicate hoặc GatewayFilter thực thi"]
    R --> RT["Route dùng cho request"]
~~~

Trong các implementation tương ứng, shortcut được chuyển thành các tham số nội bộ theo thứ tự do factory định nghĩa (chẳng hạn qua cơ chế `shortcutFieldOrder()` của `ShortcutConfigurable`). Vì vậy:

- **Thứ tự giá trị là một phần của cú pháp rút gọn.** `AddRequestHeader=X-Edge-Origin,gateway` khác `AddRequestHeader=gateway,X-Edge-Origin`.
- **Khóa trong `args` là tên trường cấu hình**, không phải vị trí thứ nhất, thứ hai. Với `AddRequestHeader`, tên thông dụng là `name` và `value`.
- **Không phải factory nào cũng có shortcut**, và không phải mọi cấu hình phức tạp đều phù hợp để ép vào một dòng.
- Thông tin về thứ tự, số lượng và kiểu tham số **phụ thuộc vào factory và phiên bản**. Không tự suy từ ví dụ của factory khác.

Trong nội bộ `PredicateDefinition` hoặc `FilterDefinition`, shortcut có thể được lưu thành các khóa tham số tổng hợp như `_genkey_0`, rồi được chuyển theo cấu hình factory khi tạo Route. Những khóa này là **chi tiết triển khai**; người viết cấu hình nên ưu tiên các tên trường công khai trong dạng `name`/`args`.

## 4. Các ví dụ predicate tương đương

### 4.1. Path: điều kiện URL path

Rút gọn:

~~~yaml
predicates:
  - Path=/api/products/**
~~~

Đầy đủ:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/products/**
~~~

Dạng đầy đủ cho phép trình bày nhiều pattern rõ ràng:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/products/**
        - /catalog/**
~~~

Nhiều pattern trong **một Path predicate** thường được hiểu là các mẫu thay thế nhau. Ngược lại, nhiều **predicate khác nhau** trong cùng route thường phải **đồng thời thỏa** (AND).

Nếu cần tùy chọn nâng cao như xử lý dấu gạch chéo cuối, hãy kiểm tra API/config fields của `PathRoutePredicateFactory` ở đúng phiên bản; không đoán rằng tên tham số của phiên bản này dùng được ở phiên bản khác.

### 4.2. Method: giới hạn HTTP method

Rút gọn:

~~~yaml
predicates:
  - Method=GET,POST
~~~

Đầy đủ:

~~~yaml
predicates:
  - name: Method
    args:
      methods:
        - GET
        - POST
~~~

Ở đây `GET` và `POST` là các phương thức được chấp nhận bởi **một Method predicate**. Nếu một route đồng thời khai báo `Path` và `Method`, thì request phải khớp cả path lẫn một phương thức trong danh sách.

### 4.3. Header: tên header và biểu thức chính quy

Rút gọn khi regex không chứa dấu phẩy:

~~~yaml
predicates:
  - Header=X-Client-Id,.+
~~~

Đầy đủ:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Id
      regexp: '.+'
~~~

Header predicate kiểm tra giá trị header theo regex, không kiểm tra header bằng chuỗi “gần giống”. Khi regex phức tạp hoặc chứa dấu phẩy, dạng đầy đủ dễ đọc và an toàn hơn:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Id
      regexp: '^[0-9]{1,3}$'
~~~

Biểu thức `^[0-9]{1,3}$` nhận một đến ba chữ số. Dấu phẩy ở `{1,3}` là **một phần của regex**; nếu đưa toàn bộ regex vào shortcut có dấu phẩy phân tách tham số, chuỗi có thể bị tách sai. Dùng dạng đầy đủ để giữ nguyên giá trị.

## 5. Các ví dụ GatewayFilter tương đương

### 5.1. StripPrefix: bỏ phân đoạn đường dẫn

Rút gọn:

~~~yaml
filters:
  - StripPrefix=2
~~~

Đầy đủ:

~~~yaml
filters:
  - name: StripPrefix
    args:
      parts: 2
~~~

Với request `/api/v1/orders/42`, `StripPrefix=2` bỏ hai phân đoạn `api` và `v1`, để backend nhận path `/orders/42` nếu không có thành phần khác thay đổi path.

### 5.2. AddRequestHeader: bổ sung header tới downstream

Rút gọn:

~~~yaml
filters:
  - AddRequestHeader=X-Edge-Origin,gateway
~~~

Đầy đủ:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

Lưu ý khác biệt ý nghĩa giữa các factory:

- **AddRequestHeader** bổ sung một giá trị header; nếu header đã tồn tại, request có thể mang nhiều giá trị.
- **SetRequestHeader** đặt/thay thế giá trị của header theo cơ chế factory.
- **RemoveRequestHeader** xóa header theo tên.

Các factory có chức năng khác nhau, dù đều liên quan đến HTTP header. Không đổi tên factory chỉ để “viết ngắn hơn”.

### 5.3. AddRequestParameter: bổ sung query parameter

Rút gọn:

~~~yaml
filters:
  - AddRequestParameter=source,gateway
~~~

Đầy đủ:

~~~yaml
filters:
  - name: AddRequestParameter
    args:
      name: source
      value: gateway
~~~

Ví dụ request `GET /items?sort=asc` có thể được chuyển tiếp với query parameter `source=gateway`. Đây là thay đổi request tới downstream, **không phải một Route Predicate**.

### 5.4. SetResponseHeader: chỉnh header của response

Rút gọn:

~~~yaml
filters:
  - SetResponseHeader=X-Served-By,edge-gateway
~~~

Đầy đủ:

~~~yaml
filters:
  - name: SetResponseHeader
    args:
      name: X-Served-By
      value: edge-gateway
~~~

Khác với `AddRequestHeader`, filter này xử lý **response header**. Khi kiểm chứng, xem header ở response client nhận được; không tìm nó trong request downstream.

### Bảng đối chiếu nhanh

| Thành phần | Cú pháp rút gọn | Trường `args` ở dạng đầy đủ |
|---|---|---|
| Path predicate | `Path=/api/**` | `patterns: [/api/**]` |
| Method predicate | `Method=GET,POST` | `methods: [GET, POST]` |
| Header predicate | `Header=X-Token,.+` | `header: X-Token`, `regexp: '.+'` |
| StripPrefix filter | `StripPrefix=1` | `parts: 1` |
| AddRequestHeader filter | `AddRequestHeader=X-Trace,edge` | `name: X-Trace`, `value: edge` |
| AddRequestParameter filter | `AddRequestParameter=source,edge` | `name: source`, `value: edge` |
| SetResponseHeader filter | `SetResponseHeader=X-Edge,yes` | `name: X-Edge`, `value: 'yes'` |

Đây là **ví dụ của các factory được nêu**, không phải quy tắc suy ra tên trường cho mọi predicate/filter. Nếu muốn khai báo `Retry`, `CircuitBreaker`, `RequestRateLimiter` hay filter khác, hãy tra đúng trường `args` mà factory tương ứng hỗ trợ.

## 6. Ví dụ đầy đủ: hai route được cấu hình theo hai cách viết

Hai route bên dưới phục vụ **hai API riêng biệt**. Route sản phẩm dùng cú pháp rút gọn, route đơn hàng dùng cú pháp đầy đủ để minh họa hai cách trong cùng một ứng dụng Gateway WebFlux.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: products
          uri: http://localhost:9091
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Edge-Origin,gateway

        - id: orders
          uri: http://localhost:9092
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/orders/**
            - name: Method
              args:
                methods:
                  - GET
          filters:
            - name: StripPrefix
              args:
                parts: 1
            - name: AddRequestHeader
              args:
                name: X-Edge-Origin
                value: gateway
~~~

Ví dụ giả định có hai backend sẵn sàng nhận `GET /products/42` tại cổng 9091 và `GET /orders/42` tại cổng 9092. Cả hai route thực hiện **cùng loại kiểm tra** và **cùng kiểu biến đổi** đối với request khớp.

| Request vào Gateway cổng 8080 | Route dự kiến | Path tại backend | Ghi chú |
|---|---|---|---|
| `GET /api/products/42` | `products` | `/products/42` | Filter rút gọn |
| `GET /api/orders/42` | `orders` | `/orders/42` | Filter đầy đủ |
| `POST /api/products/42` | Không khớp route `products` | Không chuyển theo route này | `Method=GET` không khớp |
| `GET /api/unknown/42` | Không khớp hai route | Không chuyển theo hai route này | `Path` không khớp |

Nếu không có route/handler khác, các request không khớp thường nhận HTTP 404. Nếu backend đích không chạy, route có thể **khớp nhưng bước kết nối downstream thất bại**, thường sinh lỗi 5xx; đó không phải lỗi cú pháp predicate.

### Sơ đồ luồng từ cấu hình tới request

~~~mermaid
sequenceDiagram
    participant C as Config YAML
    participant R as RouteDefinitionRouteLocator
    participant P as Predicate/Filter factories
    participant G as Gateway request pipeline
    participant B as Backend
    C->>R: Cung cấp định nghĩa route
    R->>P: Bind args và tạo predicate/filter
    P-->>R: Đối tượng runtime
    R-->>G: Route đã tạo
    G->>G: Chọn route khớp Path và Method
    G->>G: Chạy StripPrefix, AddRequestHeader
    G->>B: Chuyển tiếp request đã biến đổi
    B-->>G: Response
~~~

Sơ đồ tập trung vào quá trình tạo route từ **cấu hình dữ liệu**. Nếu route được tạo bằng Java DSL, nó có thể đi qua con đường khác để tạo `Route`, nhưng request vẫn được xử lý thông qua pipeline phù hợp.

## 7. Những điểm khác nhau thật sự giữa shortcut và fully expanded

| Tiêu chí | Cú pháp rút gọn | `name` + `args` đầy đủ |
|---|---|---|
| Độ dài | Ngắn, hợp với một hoặc hai tham số đơn giản | Dài hơn, tường minh hơn |
| Thứ tự tham số | **Có ý nghĩa**, phải theo factory | Chủ yếu dựa vào tên khóa trong map |
| Dấu phẩy trong giá trị | Dễ xung đột với dấu phẩy phân tách | Giá trị nằm trong field riêng, dễ bảo toàn hơn |
| Regex hoặc danh sách | Có thể khó đọc/escape | Dễ trình bày regex và list |
| Kiểm tra code review | Nhanh với cấu hình ít tham số | Thuận tiện rà từng tham số |
| Tham số tùy chọn | Dễ khó nhớ thứ tự/default | Có thể khai báo rõ thuộc tính được hỗ trợ |
| Khi factory không hỗ trợ shortcut | Không dùng được | Thường là lựa chọn phù hợp |
| Kết quả xử lý request | Không có lợi thế riêng khi cấu hình tương đương | Không có lợi thế riêng khi cấu hình tương đương |

**Độ dài YAML không quyết định hiệu năng xử lý HTTP.** Khi route được tạo thành công với cùng predicate/filter/config, Gateway thực thi cùng kiểu đối tượng xử lý. Chọn cú pháp dựa trên độ rõ ràng, độ phức tạp tham số và khả năng bảo trì.

### Quy tắc chọn thực tế

- Dùng **shortcut** cho các factory có tham số ngắn, dễ hiểu như `Path`, `Method`, `StripPrefix` và trường hợp đơn giản của `AddRequestHeader`.
- Dùng **expanded** khi có nhiều trường, giá trị chứa dấu phẩy, regex, list, tham số tùy chọn hoặc cần công khai ý nghĩa từng tham số.
- Dùng **expanded và tài liệu factory** khi thiết lập rate limiting, circuit breaker, retry hoặc các tích hợp bên ngoài; không đoán các cặp `name`/`args` theo ví dụ khác.
- Trong một ứng dụng có thể dùng **cả hai cách** cho các route hoặc các phần tử khác nhau. Nên áp dụng quy ước nhất quán trong từng nhóm cấu hình để dễ review.

## 8. Các bẫy khi khai báo YAML

### 8.1. Nhầm cấu trúc list và map

Đúng — `predicates` là danh sách, mỗi phần tử map có `name` và `args`:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/orders/**
  - name: Method
    args:
      methods:
        - GET
~~~

Sai — đặt `Method` cùng cấp với `args` trong **một phần tử map** như thể nó là tham số của Path:

~~~yaml
# SAI: cấu trúc không diễn đạt hai predicates riêng biệt
predicates:
  - name: Path
    args:
      patterns:
        - /api/orders/**
    Method: GET
~~~

### 8.2. Nhầm tên trường `args`

Sai:

~~~yaml
# SAI: StripPrefix thường nhận trường "parts", không phải "prefix"
filters:
  - name: StripPrefix
    args:
      prefix: 1
~~~

Đúng:

~~~yaml
filters:
  - name: StripPrefix
    args:
      parts: 1
~~~

Nếu tham số sai tên, binding/validation có thể gây lỗi khởi động, refresh hoặc tạo filter, tùy factory và phiên bản. Không luôn có lỗi cú pháp YAML rõ ràng vì YAML vẫn có thể hoàn toàn hợp lệ.

### 8.3. Đổi thứ tự tham số shortcut

Sai ý định:

~~~yaml
# Muốn thêm X-Edge-Origin: gateway, nhưng viết ngược thứ tự
filters:
  - AddRequestHeader=gateway,X-Edge-Origin
~~~

Với factory `AddRequestHeader`, giá trị đầu dùng làm **tên header**, giá trị sau là **nội dung header**; kết quả không còn đáp ứng ý định ban đầu. Dạng đầy đủ giúp tránh nhầm:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

### 8.4. Giá trị chứa dấu phẩy và ký tự đặc biệt

Regex có lượng lặp như `{1,3}`, giá trị header chứa dấu phẩy hoặc biểu thức viết lại đường dẫn có nhóm capture đều cần cẩn thận khi dùng shortcut. Ưu tiên `name` và `args` để **tách cấu trúc tham số khỏi nội dung giá trị**.

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Id
      regexp: '^[A-Z]{2,4}[0-9]{1,3}$'
~~~

Với `RewritePath`, thay đổi path có thể liên quan regex, nhóm capture và chuỗi thay thế mang cú pháp `$` cộng tên nhóm. Phải tuân thủ hướng dẫn escaping của đúng phiên bản Spring Cloud Gateway để tránh **Spring property placeholder** xử lý nhầm ký hiệu. Đừng chỉ thử thêm dấu nháy hoặc dấu gạch ngược theo cảm tính mà không kiểm chứng bằng request tới downstream.

YAML có các ký tự đặc biệt khác như `:`, `#`, `&`, `*` và dấu ngoặc. Khi giá trị có nguy cơ bị parser hiểu khác ý định, dùng dấu nháy phù hợp. Trong **single-quoted YAML string**, dấu gạch ngược thường được giữ nguyên; trong **double-quoted string**, dấu gạch ngược tham gia cơ chế escape của YAML.

### 8.5. Quên quote chuỗi trông giống Boolean hoặc số

Một số giá trị trong `args` phải là **chuỗi ký tự**, nhưng YAML parser có thể diễn giải `true`, `false` hoặc số theo kiểu dữ liệu riêng. Ví dụ `SetResponseHeader` với giá trị chữ `true` nên khai báo tường minh:

~~~yaml
filters:
  - name: SetResponseHeader
    args:
      name: X-Feature-Enabled
      value: 'true'
~~~

Điều này đặc biệt hữu ích khi xem lại config hoặc khi placeholder/environment override tham gia. Trường nào thực sự nhận kiểu Boolean hoặc số thì vẫn cần giá trị đúng kiểu mà factory hỗ trợ.

### 8.6. Nhầm nhiều predicate là OR

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
~~~

Ở đây Gateway chỉ chọn route khi **Path AND Method** đều phù hợp. Nếu muốn một trong nhiều path, khai báo nhiều pattern trong **một Path predicate** theo cú pháp mà phiên bản hỗ trợ, chẳng hạn ví dụ `patterns` dạng danh sách đã nêu; đừng thêm hai phần tử `Path` độc lập rồi tự giả định Gateway sẽ dùng OR.

### 8.7. Trộn cấu hình WebFlux và Server MVC

Không thể kết luận một factory hoặc khóa `args` dùng được cho Gateway Server MVC chỉ vì nó có tên gần giống với WebFlux. Hai biến thể có thể có starter, namespace, DSL và cách xử lý filter khác nhau. Với ví dụ trong bài, phải xác nhận dự án thực sự dùng **Gateway Server WebFlux** và phiên bản tương ứng.

## 9. Cú pháp đầy đủ cho cấu hình nâng cao

Khi chuyển sang xác thực, chống quá tải, circuit breaker và retry, nhiều filter có thêm trường và tích hợp ngoài. Cách viết đầy đủ giúp nhìn rõ từng điều kiện.

Ví dụ một filter Retry cho một route **chỉ nhận GET**, ở phiên bản WebFlux có hỗ trợ cấu hình này:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: reports
          uri: http://localhost:9093
          predicates:
            - Path=/api/reports/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: Retry
              args:
                retries: 2
                methods:
                  - GET
                statuses:
                  - BAD_GATEWAY
~~~

Ví dụ giả định downstream cổng 9093 đang chạy và phù hợp với retry idempotent GET. Filter có thể thử lại khi gặp trạng thái được cấu hình, với điều kiện khớp cơ chế của factory/phiên bản. Đừng hiểu `retries: 2` là hạn chế tổng số HTTP request trên toàn hệ thống; nó mô tả số lần thử lại theo cấu hình filter trong phạm vi xử lý liên quan. Các tham số backoff, exception và trạng thái lỗi cần đối chiếu tài liệu cùng phiên bản.

**Lưu ý vận hành:** retry có thể khuếch đại tải và thời gian xử lý. Không tùy tiện retry request POST tạo giao dịch hoặc các request không idempotent; cần kiểm tra timeout, circuit breaker, giới hạn retry và chính sách idempotency của downstream.

Với **RequestRateLimiter**, một cấu hình đầy đủ thường cần tham số rate limiter và có thể cần bean `KeyResolver`, Redis hoặc backend khác. Với **CircuitBreaker**, có thể cần tên circuit breaker, fallback và thư viện resilience tương ứng. Các factory này không nên được lắp ghép từ shortcut suy đoán; phải đối chiếu tên field, dependency và version.

## 10. Khi có service discovery hoặc bảo mật

Cú pháp `name`/`args` **chỉ liên quan trực tiếp đến phần khai báo predicate và GatewayFilter**. Những yếu tố khác của route không bị thay đổi chỉ vì chọn shortcut hay expanded.

**Service discovery:** ví dụ route dùng `lb://order-service`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: lb://order-service
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/orders/**
          filters:
            - StripPrefix=1
~~~

`lb://order-service` thuộc **`uri` của route**, không thuộc `args` của `Path` hoặc `StripPrefix`. Để chạy thực tế cần các thành phần discovery/load balancer được cấu hình và có instance của dịch vụ `order-service`. Việc dùng dạng đầy đủ không tự bật discovery.

**Xác thực:** Spring Security có thể chặn request ở tầng web trước khi Gateway chọn route; các GatewayFilter liên quan token relay hoặc authorization lại có phạm vi và điều kiện riêng. Việc chuyển `Path=/api/orders/**` sang `name: Path` + `args` **không thay đổi bản chất chính sách bảo mật**.

**TLS và quan sát request:** HTTPS listener, trust của HTTP client, Micrometer/tracing hoặc Actuator được cấu hình ở các thành phần liên quan, không phải chỉ qua shortcut. Route ID, filter và URI vẫn là thông tin quan trọng để gắn log/metric và kiểm tra request đi đúng downstream.

## 11. Cách chẩn đoán khi dạng đầy đủ và shortcut cho kết quả khác nhau

Nếu một refactor từ rút gọn sang dạng đầy đủ làm route không match hoặc biến đổi request sai, hãy kiểm tra theo thứ tự:

1. **Dự án thực chạy phiên bản nào?** Xác nhận Spring Boot, Spring Cloud BOM, artifact Gateway và WebFlux/MVC; đọc tài liệu tương ứng.
2. **YAML có parse và bind đúng không?** Kiểm tra indent của `predicates`/`filters`, dấu `-` và các khóa `name`, `args`.
3. **Factory nào được chọn?** Tên `Path`, `Header`, `AddRequestHeader`... có đúng không? Tên factory không phải tên HTTP header hay tên route.
4. **Tên trường nào được dùng?** `patterns`, `methods`, `header`, `regexp`, `parts`, `value` phải đúng với cấu hình của factory; không đổi tùy ý số ít/số nhiều.
5. **Giá trị có giữ nguyên nghĩa?** Kiểm tra regex, dấu phẩy, dấu nháy, kiểu dữ liệu, placeholder và thứ tự positional args.
6. **Route có được xây dựng và nạp lại?** Kiểm tra log startup/refresh và danh sách route đang hoạt động; có thể cần restart hoặc refresh theo cơ chế được hỗ trợ.
7. **Request thật đi qua các bước nào?** Phân biệt không match predicate, filter không chạy, downstream không kết nối và response bị filter khác thay đổi.

Với các phiên bản có Spring Boot Actuator/Gateway management endpoint phù hợp, có thể xem route đã được nhận và refresh theo tài liệu chính thức. Các endpoint quản trị không nhất thiết được bật sẵn; chỉ expose trong môi trường và với quyền truy cập được kiểm soát, đặc biệt không công khai quyền ghi/sửa route.

| Triệu chứng | Nghi ngờ ưu tiên | Bằng chứng cần tìm |
|---|---|---|
| YAML không nạp | Sai indent, sai list/map, sai prefix config | Log binding hoặc cấu hình đã được bind |
| Nạp dữ liệu nhưng không tạo được route | Không tìm thấy factory, `args` sai tên/kiểu | Log tạo RouteDefinition/Route, lỗi validation |
| Route có nhưng trả 404 | Predicate không match hoặc route order | Method, Path, Host/Header thực tế |
| Path downstream sai | `StripPrefix` hoặc `RewritePath` không tương đương | Request đến backend, filter order |
| Header downstream sai | `args.name`/`args.value` nhầm vị trí, có filter khác ghi đè | Log/echo header của downstream |
| Refactor xong nhưng vẫn chạy cấu hình cũ | Route/cache chưa làm mới, sai profile/instance | Danh sách route tại instance thực nhận traffic |
| Status 5xx dù route match | Backend/TLS/DNS/discovery hoặc filter lỗi | Trạng thái route, log routing và downstream |

## 12. Bài thực hành tự kiểm chứng hai cách viết

**Điều kiện:** một Gateway Server WebFlux hỗ trợ namespace cấu hình trong bài, chạy ở `http://localhost:8080`; một backend giả lập ở `http://localhost:9090` có thể ghi lại path, method và header request, trả HTTP 200 cho `GET /orders/42`.

### Bước 1 — Cấu hình shortcut

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Edge-Origin,gateway
~~~

Gọi request:

~~~bash
curl -i http://localhost:8080/api/orders/42
curl -i -X POST http://localhost:8080/api/orders/42
~~~

Ghi lại: route nào được chọn, path/header tại backend, HTTP status ở client. Request GET dự kiến đến backend qua đường dẫn `/orders/42` và có header `X-Edge-Origin: gateway`. POST không khớp `Method=GET` của route này.

### Bước 2 — Chuyển sang đầy đủ

Thay chỉ `predicates` và `filters` bằng:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/orders/**
  - name: Method
    args:
      methods:
        - GET
filters:
  - name: StripPrefix
    args:
      parts: 1
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

Đoạn trên là **các trường bên trong một route**, không phải file application YAML độc lập. Giữ nguyên `id`, `uri` và các phần khác. Restart ứng dụng hoặc dùng quy trình nạp lại route phù hợp phiên bản; xác nhận route mới đã được sử dụng rồi chạy lại hai lệnh `curl`.

### Bước 3 — So sánh bằng chứng

| Tiêu chí | Shortcut | Expanded | Kỳ vọng |
|---|---|---|---|
| ID và URI | `orders`, `localhost:9090` | Giống shortcut | Không đổi |
| GET match | Có | Có | Giống nhau |
| POST match route này | Không | Không | Giống nhau |
| Path backend của GET | `/orders/42` | `/orders/42` | Giống nhau |
| Header backend | `X-Edge-Origin: gateway` | Cùng tên/giá trị | Giống nhau |
| Response status/body | Phụ thuộc backend | Phụ thuộc backend | Không khác do cách viết |

Nếu kết quả khác nhau, **không kết luận ngay rằng cú pháp đầy đủ chậm hoặc lỗi**. So sánh RouteDefinition/Route thực sự được nạp, tham số đã bind và request đi qua chain để tìm điểm không tương đương.

### Bước 4 — Thử lỗi có chủ đích

Trong môi trường học tập, thay `parts: 1` bằng `prefix: 1` hoặc đảo hai giá trị của shortcut `AddRequestHeader`. Quan sát log/cách nạp route và thông tin backend nhận được; sau đó khôi phục cấu hình đúng. Bài thử giúp phân biệt **YAML hợp lệ về mặt cú pháp** với **cấu hình factory đúng về mặt ngữ nghĩa**.

## 13. Checklist trước khi đưa route vào hệ thống microservices

- [ ] Tôi đã xác nhận phiên bản và biến thể **Spring Cloud Gateway Server WebFlux** hoặc **Server MVC**.
- [ ] Tôi biết `predicates` và `filters` là **danh sách**, có thể chứa shortcut hoặc `name`/`args` theo phiên bản hỗ trợ.
- [ ] Tôi hiểu shortcut dùng **giá trị theo thứ tự**, còn expanded dùng **tên field**.
- [ ] Tôi đã kiểm tra `args` đúng tên như `patterns`, `methods`, `parts`, `name`, `value`.
- [ ] Tôi chọn expanded khi regex, danh sách, dấu phẩy hoặc cấu hình phức tạp có thể gây hiểu nhầm.
- [ ] Tôi đã phân biệt **Add** và **Set**, request header và response header.
- [ ] Tôi biết nhiều predicates cùng route thường kết hợp AND, độc lập với thứ tự route và filter.
- [ ] Tôi đã thử request thật, quan sát path/header ở downstream và response ở client.
- [ ] Tôi đã kiểm tra cơ chế refresh/restart và danh sách Route đang chạy sau khi sửa cấu hình.
- [ ] Tôi không nhầm URI `lb://`, xác thực, TLS hoặc quan sát hệ thống thành tham số của predicate/filter.
- [ ] Tôi đã rà soát bảo mật, giới hạn lưu lượng, retry/circuit breaker theo đúng factory và dependency khi những tính năng đó được bật.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tài liệu route configuration, route predicates, GatewayFilter factories và những ví dụ fully expanded/shortcut; luôn chọn đúng phiên bản.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — thông tin dự án, release và đường dẫn tài liệu.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — cách Spring Boot đọc YAML/properties và property placeholders.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — nền tảng xử lý HTTP reactive được Gateway Server WebFlux sử dụng.

**Ghi nhớ:** `Path=/api/**` và `name: Path` kèm `args.patterns` có thể tạo cùng predicate; `StripPrefix=1` và `name: StripPrefix` kèm `args.parts: 1` có thể tạo cùng filter. Hãy đánh giá **tên factory, tham số thực sự được bind và hành vi request**, vì chính ba yếu tố đó quyết định một route có hoạt động đúng hay không.
