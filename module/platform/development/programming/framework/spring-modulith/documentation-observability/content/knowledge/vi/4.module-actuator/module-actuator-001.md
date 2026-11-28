# Spring Modulith actuator cung cấp thông tin gì

Trong ứng dụng **Spring Boot** sử dụng **Spring Modulith**, ta thường cần trả lời hai nhóm câu hỏi: *“Hệ thống được chia thành những application module nào, chúng phụ thuộc vào nhau ra sao?”* và *“Khi chạy thật, các module có tương tác đúng như thiết kế không?”* **Application Module Actuator** trả lời chủ yếu nhóm câu hỏi thứ nhất: xuất mô hình cấu trúc các module đang được Spring Modulith nhận diện qua một endpoint của Spring Boot Actuator.

Bài này thuộc chương **Module Actuator** trong mô-đun học `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Mục tiêu rộng hơn của mô-đun học là dùng **module graph**, tài liệu ranh giới module, **Actuator**, **event metrics**, **tracing** và **context propagation** để hiểu và kiểm chứng kiến trúc mô-đun khi hệ thống vận hành. Vì vậy, cần hiểu chính xác **dữ liệu nào có trong response `/actuator/modulith`** và dữ liệu nào phải lấy từ công cụ khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chức năng của Spring Modulith Actuator và cách nó liên hệ với `ApplicationModules`.
2. Bật và truy cập endpoint `GET /actuator/modulith` trong ứng dụng Spring Boot.
3. Đọc được `displayName`, `basePackage`, `parent`, `nested` và `dependencies` trong JSON trả về.
4. Giải thích ý nghĩa chính xác của `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER` và **chiều** dependency.
5. Dùng JSON để đối chiếu module graph, phát hiện điểm cần điều tra và xác định giới hạn của endpoint.
6. Phân biệt cấu trúc module từ Actuator với số liệu sự kiện, trace và kết quả kiểm thử kiến trúc.

## 2. Spring Modulith Actuator là gì?

Spring Boot Actuator cung cấp cơ chế expose thông tin quản trị và chẩn đoán qua HTTP/JMX. Spring Modulith bổ sung một endpoint riêng, có ID **`modulith`**, để công bố thông tin về **cấu trúc application module** mà thư viện phát hiện từ ứng dụng.

- **Endpoint ID:** `modulith`.
- **Đường dẫn HTTP thông thường:** `GET /actuator/modulith` (nếu dùng base path mặc định và cho phép expose).
- **Định dạng phản hồi qua HTTP:** JSON có các khóa cấp cao nhất là **technical module name**.
- **Nguồn thông tin:** mô hình module được Spring Modulith suy ra từ cấu trúc package, các khai báo/module customization và quan hệ phụ thuộc trong mã ứng dụng.
- **Mục đích:** quan sát kiến trúc ứng dụng dưới dạng dữ liệu có thể truy vấn, chia sẻ hoặc dùng để đối chiếu.

Một hình dung đơn giản:

~~~mermaid
flowchart LR
    A["Mã nguồn Spring Boot<br/>package + module metadata"] --> B["Spring Modulith<br/>ApplicationModules"]
    B --> C["Application Module Actuator<br/>/actuator/modulith"]
    C --> D["JSON: module names<br/>packages, dependencies"]
    D --> E["Đối chiếu module graph<br/>và tài liệu kiến trúc"]
~~~

**Phạm vi quan trọng:** `/actuator/modulith` là một **cái nhìn cấu trúc** (architectural model), không phải bản ghi từng lần gọi hàm trong runtime. Nó không tự trả thời gian xử lý request, thống kê số event đã publish, span ID hay trace ID.

## 3. Endpoint cung cấp những trường nào?

Theo tài liệu chính thức của Spring Modulith, response của module actuator có cấu trúc JSON như bảng sau. Ký hiệu `{moduleName}` đại diện cho định danh kỹ thuật của từng module, chẳng hạn `orders` hoặc `inventory`.

| JSONPath | Thông tin | Cách đọc |
| --- | --- | --- |
| `$.{moduleName}` | Định danh kỹ thuật của application module | Khóa top-level trong JSON; đích tham chiếu của `dependencies[].target` |
| `$.{moduleName}.displayName` | Tên module thân thiện với người đọc | Dùng khi trình bày báo cáo hoặc module graph |
| `$.{moduleName}.basePackage` | Java package gốc của module | Giúp xác định module ứng với phần mã nguồn nào |
| `$.{moduleName}.parent` | Tên module cha, **nếu có** | Liên hệ với **nested application module** |
| `$.{moduleName}.nested` | Danh sách tên các module con, **nếu có** | Cho thấy cấu trúc module lồng nhau |
| `$.{moduleName}.dependencies[]` | Các quan hệ phụ thuộc **đi ra** từ module hiện tại | Mỗi phần tử mô tả module hiện tại phụ thuộc vào một module khác |
| `$.{moduleName}.dependencies[].target` | Tên kỹ thuật của module đích | Tham chiếu tới khóa của một module khác trong response |
| `$.{moduleName}.dependencies[].types[]` | Phân loại các dạng phụ thuộc đến cùng module đích | Có thể chứa nhiều loại `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER` |

### 3.1. Vì sao cần cả tên kỹ thuật và tên hiển thị?

Trong JSON:

~~~json
{
  "orders": {
    "displayName": "Order Management",
    "basePackage": "com.example.shop.orders",
    "dependencies": []
  }
}
~~~

`orders` là **technical name** dùng để nối các tham chiếu giữa các module, trong khi `Order Management` là tên có ích cho người đọc. `basePackage` giúp xác định phần mã nguồn tương ứng. Không nên dùng `displayName` như khóa tham chiếu, bởi `dependencies[].target` trỏ đến **technical name**.

### 3.2. `parent` và `nested` có phải luôn tồn tại?

Không. Hai thuộc tính này hỗ trợ tình huống **nested modules** trong các phiên bản Spring Modulith có hỗ trợ, và chỉ có ý nghĩa khi mô hình chứa quan hệ cha–con. Với bố cục chỉ gồm các module ngang cấp, bạn có thể không thấy chúng trong JSON.

Cũng cần phân biệt hai loại quan hệ:

- **Cha–con:** quan hệ phân cấp tổ chức module (`parent` / `nested`).
- **Phụ thuộc:** quan hệ sử dụng một module khác (`dependencies`).

Một module con không tự động mang ý nghĩa “đã gọi” module cha. Hai quan hệ này giải thích những khía cạnh khác nhau của kiến trúc.

## 4. Đọc ví dụ response của `/actuator/modulith`

Giả sử ứng dụng bán hàng có ba application module: `orders`, `payments` và `inventory`. Module `orders` sử dụng một bean dịch vụ thanh toán từ `payments`. Module `inventory` nhận sự kiện nghiệp vụ `OrderPlaced` do `orders` khai báo.

Một response minh họa là:

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.example.shop.orders",
    "dependencies": [
      {
        "target": "payments",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "payments": {
    "displayName": "Payments",
    "basePackage": "com.example.shop.payments",
    "dependencies": []
  },
  "inventory": {
    "displayName": "Inventory",
    "basePackage": "com.example.shop.inventory",
    "dependencies": [
      {
        "target": "orders",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

Đây là **dữ liệu minh họa**, không phải response đã chạy từ một dự án cụ thể. Các kiểu dependency thực tế phụ thuộc vào cách code khai báo, Spring Modulith nhận diện các module và các hình thức tương tác.

Từ JSON, có thể dựng đồ thị:

~~~mermaid
flowchart LR
    O["orders"]
    P["payments"]
    I["inventory"]
    O -->|"USES_COMPONENT"| P
    I -->|"EVENT_LISTENER"| O
~~~

Cách đọc đúng:

- `orders → payments`: code trong module `orders` phụ thuộc vào Spring component của module `payments`.
- `inventory → orders`: module `inventory` có listener phụ thuộc vào sự kiện được công bố dưới dạng type của module `orders`.
- `payments.dependencies = []`: mô hình **không ghi nhận dependency đi ra** nào từ `payments` đến các application module khác. Điều này không nói rằng `payments` không có code nội bộ, không gọi database hay không được module khác sử dụng.

**Điểm dễ nhầm:** Một luồng nghiệp vụ có thể diễn ra theo thời gian như `orders phát event → inventory xử lý event`, nhưng **mũi tên trong dependency graph** vẫn có thể là **`inventory → orders`**, vì listener của `inventory` cần biết **kiểu sự kiện** do `orders` công bố. **Dependency direction diễn tả “ai phụ thuộc vào ai”, không diễn tả “ai kích hoạt ai theo thời gian”.**

## 5. Ba kiểu dependency nói lên điều gì?

Mỗi phần tử `dependencies[]` có một `target` và danh sách `types[]`. Tài liệu Modulith mô tả ba loại:

| Giá trị trong `types[]` | Cách hiểu | Ví dụ có thể gặp |
| --- | --- | --- |
| `DEFAULT` | Phụ thuộc type/tham chiếu mã nguồn thông thường | Type của module A được module B tham chiếu |
| `USES_COMPONENT` | Phụ thuộc vào Spring bean/component của module đích | `orders` tiêm và gọi `PaymentService` thuộc `payments` |
| `EVENT_LISTENER` | Quan hệ phụ thuộc phát sinh từ event listener | `inventory` khai báo listener nhận `OrderPlaced` thuộc `orders` |

### 5.1. `types[]` là một mảng, không phải một giá trị đơn

Một module có thể phụ thuộc cùng một module đích theo nhiều cách. Do đó, dạng:

~~~json
{
  "target": "orders",
  "types": ["EVENT_LISTENER", "USES_COMPONENT"]
}
~~~

có nghĩa là hệ thống nhận diện **cả hai kiểu phụ thuộc** đến `orders`. Nó không nói có đúng hai lần gọi hay có đúng hai bean. Đây là **phân loại quan hệ kiến trúc**, không phải bộ đếm runtime.

### 5.2. Không suy ra sự kiện đã được xử lý thành công

Nếu thấy `inventory.dependencies[].types` chứa `EVENT_LISTENER`, bạn có bằng chứng rằng **mô hình** nhận diện quan hệ listener/event. Kết quả đó không chứng minh:

- Sự kiện `OrderPlaced` đã thực sự được publish khi chạy.
- Listener `inventory` đã chạy ở mọi tình huống.
- Listener đã commit thay đổi thành công hoặc đã hoàn thành retry.
- Trace context giữa publisher và listener đã được truyền qua ranh giới bất đồng bộ.

Các câu hỏi vận hành này cần event publication registry, metrics, logs hoặc tracing tùy mục tiêu điều tra.

## 6. Cách bật và truy cập module actuator

Cần hai nhóm điều kiện: **có dependency cung cấp endpoint** và **Spring Boot cho phép truy cập endpoint**.

### 6.1. Thêm dependency

**Cách 1 — Chỉ cần module actuator:** với một ứng dụng Gradle đã có Spring Boot và quản lý phiên bản Spring Modulith tương thích:

~~~gradle
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
}
~~~

**Cách 2 — Cần actuator cùng observability của Spring Modulith:**

~~~gradle
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

`spring-modulith-starter-insight` gom khả năng Actuator và Modulith observability. Việc **xuất traces sang backend** như Zipkin/Tempo/Jaeger vẫn cần cấu hình và dependency tracing/exporter phù hợp theo phiên bản Spring Boot. Thêm `starter-insight` một mình không khiến dữ liệu trace tự xuất hiện trong dashboard.

Các ví dụ Gradle trên **giả định dự án đã quản lý phiên bản dependency**, chẳng hạn dùng Spring Modulith BOM tương thích với phiên bản Spring Boot. Nếu không có cơ chế quản lý phiên bản, bạn phải khai báo phiên bản cụ thể nhất quán với dự án. Không sao chép số phiên bản trong một bài viết mà chưa đối chiếu compatibility matrix của hệ thống đang dùng.

### 6.2. Cho phép expose endpoint qua HTTP

Ví dụ `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith"
~~~

Mặc định, Spring Boot chỉ expose một tập endpoint hạn chế qua HTTP (thường là `health`). Do đó, có dependency chưa chắc đã truy cập được `/actuator/modulith` qua HTTP. Bạn phải kiểm tra cả **endpoint availability/access**, cấu hình **web exposure**, và quyền truy cập nếu ứng dụng có Spring Security hoặc bộ lọc mạng.

### 6.3. Truy cập

Với ứng dụng web chạy ở `localhost:8080`, context path và management base path mặc định:

~~~bash
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/modulith
~~~

Lệnh đầu trả về danh sách resource liên kết của Actuator, trong đó có thể thấy liên kết `modulith` nếu được công bố. Lệnh thứ hai trả về JSON cấu trúc application module.

Ví dụ phần liên kết có thể gặp trong `GET /actuator`:

~~~json
{
  "_links": {
    "self": { "href": "http://localhost:8080/actuator", "templated": false },
    "health": { "href": "http://localhost:8080/actuator/health", "templated": false },
    "modulith": {
      "href": "http://localhost:8080/actuator/modulith",
      "templated": false
    }
  }
}
~~~

Địa chỉ cổng/đường dẫn sẽ khác nếu ứng dụng thiết lập `management.server.port`, `management.endpoints.web.base-path` hoặc context path. Liên kết discovery cũng có thể không xuất hiện nếu đã tắt discovery; khi đó cần kiểm tra cấu hình endpoint trực tiếp.

### 6.4. Đọc dữ liệu bằng công cụ dòng lệnh

Nếu có `jq`:

~~~bash
# Xem toàn bộ cấu trúc với định dạng dễ đọc
curl -fsS http://localhost:8080/actuator/modulith | jq .

# Tên kỹ thuật của các module được nhận diện
curl -fsS http://localhost:8080/actuator/modulith | jq -r 'keys[]'

# Dependency đi ra từ module orders
curl -fsS http://localhost:8080/actuator/modulith | jq '.orders.dependencies'

# Các module đang phụ thuộc vào orders
curl -fsS http://localhost:8080/actuator/modulith \
  | jq -r 'to_entries[] | select(any(.value.dependencies[]?; .target == "orders")) | .key'
~~~

Truy vấn cuối rất hữu ích khi muốn biết **module nào đang sử dụng `orders`**: thay vì chỉ đọc `orders.dependencies` (phụ thuộc **đi ra**), ta duyệt các module khác để tìm tham chiếu có `target=orders` (phụ thuộc **đi vào**).

## 7. Ứng dụng kết quả để kiểm chứng kiến trúc

### 7.1. Đối chiếu ranh giới package

`basePackage` hỗ trợ kiểm tra rằng các phần nghiệp vụ được nhận diện thành những module như mong muốn. Ví dụ:

| Kỳ vọng | Kiểm tra ở response |
| --- | --- |
| Có application module `orders` | JSON có khóa top-level `orders` |
| Module `orders` nằm ở package dự kiến | `orders.basePackage` tương ứng với package đã thiết kế |
| `inventory` phụ thuộc `orders` vì nhận event | Có `inventory.dependencies[].target = orders` và kiểu phù hợp |
| `orders` dùng payment service | Có dependency từ `orders` tới `payments` với `USES_COMPONENT` nếu được nhận diện |

Nếu thiếu module hoặc package không như dự kiến, kiểm tra base package của Spring Boot application, quy tắc nhận diện module của Spring Modulith, nested module, và các customizations trong production code. Cấu hình phát hiện module chỉ có trong test source không nhất thiết được Actuator dùng khi chạy ứng dụng thật.

### 7.2. Phân tích chiều phụ thuộc

Giả sử một hệ thống kỳ vọng `shipping` chỉ tiêu thụ API/event từ `orders`, nhưng response lại cho thấy `orders.dependencies[]` trỏ tới `shipping`. Đây là tín hiệu cần kiểm tra có dependency từ đơn hàng sang vận chuyển ngoài thiết kế hay không.

Cần đọc **kiểu dependency** trước khi kết luận, vì một reference type, một bean call và một event listener có ý nghĩa kỹ thuật khác nhau. Actuator giúp **phát hiện điều cần điều tra**; việc dependency có **vi phạm quy tắc cho phép hay không** phải đối chiếu với thiết kế và kiểm thử kiến trúc.

### 7.3. Kết hợp với `ApplicationModules.verify()`

Khi cần **xác minh ràng buộc cấu trúc**, dùng API kiểm thử của Spring Modulith thay vì xem sự hiện diện của endpoint như bằng chứng dự án đã pass kiểm tra kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ShopApplication` là lớp `@SpringBootApplication` của ví dụ; cần thêm dependency test tương ứng với phiên bản Modulith. Phép `verify()` giúp phát hiện những vi phạm kiến trúc mà Spring Modulith kiểm tra, chẳng hạn phụ thuộc tới package nội bộ không được expose hoặc vấn đề ràng buộc dependency. **Actuator công bố cấu trúc, còn verify xác minh cấu trúc theo quy tắc.**

### 7.4. Kết hợp với tài liệu module graph

Spring Modulith còn cung cấp cơ chế sinh tài liệu/diagram (ví dụ `Documenter`) dựa trên mô hình `ApplicationModules`. Có thể dùng Actuator để xem **mô hình được nhận diện trong ứng dụng đã khởi chạy**, sau đó đối chiếu với sơ đồ và tài liệu được tạo ở giai đoạn phát triển.

Kết quả Actuator là JSON mô tả quan hệ module; nó **không mặc nhiên trả một file SVG/Mermaid/PlantUML đã dựng sẵn**. Muốn tạo hình hoặc báo cáo thiết kế, dùng công cụ tài liệu hoặc tự chuyển đổi dữ liệu JSON thành đồ thị.

## 8. Actuator, tracing và event metrics: những công cụ bổ sung

Để tránh dùng sai công cụ, phân biệt chức năng:

| Công cụ / dữ liệu | Trả lời câu hỏi | Đặc trưng |
| --- | --- | --- |
| **`GET /actuator/modulith`** | Có module nào? Package gốc? Phụ thuộc vào module nào? | Cấu trúc ứng dụng; JSON module/dependency |
| **Module graph / tài liệu được sinh** | Kiến trúc module trông như thế nào trên sơ đồ/tài liệu? | Trình bày trực quan cấu trúc và ranh giới |
| **Module entry span trong distributed tracing** | Khi một luồng chạy, request đã đi vào module nào và mất bao lâu? | Một tương tác runtime cụ thể; có trace/span context |
| **Event publication metrics** | Bao nhiêu event đã được publish theo các chiều đo được instrument? | Dữ liệu đếm/xu hướng; không chứng minh listener đã xử lý thành công |
| **Event publication registry / logs** | Publication nào đã/chưa được hoàn tất, lỗi nào xảy ra? | Tùy cấu hình registry, logs và cơ chế xử lý sự kiện |
| **`ApplicationModules.verify()`** | Cấu trúc hiện tại có vi phạm một số quy tắc module được kiểm tra không? | Xác minh kiến trúc trong test/build |

Các loại dữ liệu thường được kết hợp trong điều tra:

1. **Actuator:** Kiểm tra `inventory` được nhận diện có quan hệ listener tới `orders` hay không.
2. **Metric/event publication:** Xem ứng dụng có ghi nhận việc publish `OrderPlaced` không.
3. **Trace/log:** Xem listener có chạy, bao lâu, có lỗi không và quan hệ trace context thế nào.
4. **Kiểm thử kiến trúc:** Xác minh các quan hệ package/API tuân thủ quy tắc cấu trúc.

Một trace không thể thay thế toàn bộ module graph; ngược lại, JSON của actuator không chứng minh một luồng đã chạy thành công.

## 9. Các giới hạn và cách hiểu đúng

| Nhận định dễ nhầm | Cách hiểu chính xác |
| --- | --- |
| “`/actuator/modulith` là danh sách mọi request đã gọi vào module.” | Endpoint trả **mô hình module**, không trả lịch sử request. |
| “Không có `dependencies` nghĩa là không có ai sử dụng module.” | `dependencies` chỉ liệt kê **phụ thuộc đi ra**; để tìm ai sử dụng module, hãy truy vấn các module khác trỏ tới nó. |
| “`EVENT_LISTENER` là mũi tên publisher gửi tới consumer.” | Dependency chỉ chiều **consumer phụ thuộc vào type/module cung cấp event**. |
| “Có `EVENT_LISTENER` nghĩa là event đã xử lý thành công.” | Quan hệ được nhận diện ở mức code/model; trạng thái xử lý runtime cần nguồn quan sát khác. |
| “`USES_COMPONENT` cho biết số lần gọi hoặc thời gian xử lý.” | Đây là loại quan hệ sử dụng Spring component, không phải counter/timer. |
| “`displayName` là khóa định danh để tra dependency.” | `target` tham chiếu **technical module name**. |
| “Có endpoint là đã tự động có trace dashboard.” | Cần instrumentation, tracing backend/exporter, context propagation và sampling phù hợp. |
| “Endpoint hiện ra nghĩa là kiến trúc đã verify pass.” | Muốn kiểm tra ràng buộc kiến trúc, chạy `ApplicationModules.verify()` hoặc quy trình kiểm thử tương đương. |
| “Module graph trong Actuator sẽ đổi ngay khi mã nguồn đang chỉnh sửa.” | Mô hình phản ánh ứng dụng đã build/khởi chạy; thay mã nguồn thường cần build/deploy/restart để có dữ liệu mới. |

### 9.1. Bảo mật khi expose endpoint

Dù chỉ trả dữ liệu cấu trúc, JSON có thể tiết lộ package, tên module và hướng phụ thuộc của hệ thống. Trong môi trường production, nên giới hạn khả năng truy cập `/actuator/modulith` cho người hoặc hệ thống quản trị có quyền.

Chỉ expose những endpoint thực sự cần, dùng Spring Security hoặc rào chắn mạng, và cân nhắc management port riêng. Không nên bật rộng `management.endpoints.web.exposure.include: "*"` cho môi trường công khai chỉ để xem một endpoint.

### 9.2. Khi bị lỗi HTTP

| Triệu chứng | Nơi cần kiểm tra |
| --- | --- |
| `404 Not Found` | Dependency Modulith Actuator; cấu hình web exposure; base path/port; endpoint access có bị vô hiệu hóa không |
| `401 Unauthorized` / `403 Forbidden` | Spring Security, xác thực, phân quyền hoặc gateway |
| Có `/actuator` nhưng không có liên kết `modulith` | Endpoint không được expose/khả dụng hoặc discovery bị tắt |
| JSON thiếu module dự kiến | Vùng base package, quy tắc phát hiện/customization module, cấu hình production source |
| Dependency hiển thị ngược với luồng event mong đợi | Phân biệt **chiều phụ thuộc code** với **chiều kích hoạt runtime** |

## 10. Bài thực hành

### Bài 1 — Đọc cấu trúc JSON

Xét response trong mục 4, hãy trả lời:

1. Có bao nhiêu application module?
2. Module nào phụ thuộc `payments` và theo kiểu nào?
3. Module nào phụ thuộc `orders` và vì sao có thể là `EVENT_LISTENER`?
4. `payments.dependencies = []` có đồng nghĩa `payments` không được ai gọi không?

**Gợi ý đáp án:** Có ba module; `orders` phụ thuộc `payments` qua `USES_COMPONENT`; `inventory` phụ thuộc `orders` qua kiểu event listener; danh sách rỗng của `payments` không nói lên dependency **đi vào**.

### Bài 2 — So sánh mô hình với thiết kế

Trong một ứng dụng lab dùng Modulith:

1. Thêm dependency và exposure để gọi được `GET /actuator/modulith`.
2. Ghi lại tất cả technical module name và `basePackage`.
3. Với từng module, liệt kê `dependencies[].target` và `types[]`.
4. Đối chiếu với module graph hoặc sơ đồ kiến trúc được nhóm thiết kế.
5. Chọn một dependency và giải thích bằng tham chiếu mã nguồn/bean/event listener tương ứng.

Ghi chú trong báo cáo rằng response lấy từ **bản build và lần khởi chạy nào**, tránh so sánh dữ liệu từ các phiên bản ứng dụng khác nhau.

### Bài 3 — Phân biệt dữ liệu tĩnh và runtime

Cho tình huống “`inventory` không cập nhật tồn kho sau khi đặt hàng”:

1. Chỉ ra câu hỏi nào `/actuator/modulith` **có thể** trả lời.
2. Chỉ ra câu hỏi nào cần event registry, metric, log hoặc trace.
3. Giải thích tại sao việc thấy `inventory → orders` kiểu `EVENT_LISTENER` chưa đủ để kết luận listener đã chạy thành công.

### Bài 4 — Tìm phụ thuộc ngược

Cho mẫu JSON có `orders`, `payments`, `inventory`, hãy viết biểu thức `jq` tìm mọi module **phụ thuộc vào `orders`**. Đối chiếu kết quả với lệnh chỉ đọc `.orders.dependencies` và giải thích sự khác nhau giữa **incoming** và **outgoing** dependencies.

## 11. Tự kiểm tra nhanh

1. HTTP endpoint của Spring Modulith Actuator có ID là gì?
2. Trường nào cho biết package gốc của một module?
3. `dependencies[].target` trỏ đến `displayName` hay technical module name?
4. Ba loại dependency mà tài liệu chính thức mô tả là gì?
5. Vì sao event consumer có thể phụ thuộc vào event publisher về mặt mã nguồn, dù luồng event chạy theo hướng ngược lại?
6. Vì sao không dùng `/actuator/modulith` để xác nhận một event listener đã xử lý xong?
7. Cần thêm điều kiện nào ngoài dependency để có thể gọi endpoint qua HTTP?
8. Công cụ nào của Spring Modulith nên sử dụng để **verify** quy tắc ranh giới kiến trúc?

## 12. Tóm tắt

**Spring Modulith Actuator công bố một bản đồ kiến trúc dạng JSON tại `/actuator/modulith`.** Bản đồ cho biết tên kỹ thuật/tên hiển thị của module, base package, quan hệ module lồng nhau khi có, và các dependency **đi ra** được phân loại thành `DEFAULT`, `USES_COMPONENT` hoặc `EVENT_LISTENER`. Đây là một kênh quan sát **cấu trúc** rất hữu ích để đối chiếu ranh giới mô-đun với mô hình thiết kế.

Khi cần biết hệ thống **đã chạy như thế nào**, hãy kết hợp trace, event metrics, logs và context propagation. Khi cần biết quan hệ kiến trúc **có hợp lệ hay không**, hãy chạy kiểm thử xác minh cấu trúc. Hiểu đúng vai trò từng công cụ giúp tránh kết luận sai từ JSON actuator.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Application Module Actuator, mô tả JSON và dependency types](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith — Fundamentals: Application Modules và cấu trúc module](https://docs.spring.io/spring-modulith/reference/fundamentals.html).
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html).
- [Spring Boot — Actuator Endpoints: endpoint availability, exposure và security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Modulith — Appendix: artifact spring-modulith-actuator và starter](https://docs.spring.io/spring-modulith/reference/appendix.html).
