# Phân biệt endpoint `health` với endpoint `modulith`

## 1. Hai endpoint cùng thuộc Actuator nhưng trả lời hai câu hỏi khác nhau

Trong ứng dụng Spring Boot dùng **Spring Modulith**, cả `GET /actuator/health` và `GET /actuator/modulith` đều có thể xuất hiện dưới đường dẫn quản trị của Spring Boot Actuator. Tuy cùng được truy cập bằng HTTP và thường trả JSON, hai endpoint phục vụ hai mục đích rõ rệt:

- **`health`:** Ứng dụng có đang ở tình trạng hoạt động được, theo những phép kiểm tra sức khỏe đã cấu hình, hay không?
- **`modulith`:** Phiên bản ứng dụng đang chạy được Spring Modulith nhận diện thành những *application module* nào, và các module có những phụ thuộc cấu trúc nào?

Điểm khác biệt cốt lõi là **trạng thái vận hành** và **mô hình kiến trúc**. Một ứng dụng có thể trả `{"status":"UP"}` ở `health` nhưng vẫn có thiết kế module chưa hợp lý. Ngược lại, `modulith` có thể công bố đầy đủ module graph ngay cả khi cơ sở dữ liệu mất kết nối và health của hệ thống báo `DOWN`, miễn là tiến trình và management endpoint vẫn có thể phục vụ yêu cầu.

Trong phạm vi **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, việc phân biệt hai endpoint giúp kết hợp kiểm chứng ranh giới application module với quan sát hành vi hệ thống. Chúng hỗ trợ nhau; không endpoint nào thay thế được endpoint còn lại.

### Mục tiêu học tập

Sau bài này, bạn có thể giải thích ý nghĩa dữ liệu, điều kiện kích hoạt, cách bảo vệ và các trường hợp sử dụng của hai endpoint; đọc kết quả mà không nhầm sức khỏe hệ thống với tính đúng đắn của ranh giới module; và chọn thêm metrics, traces hoặc kiểm thử kiến trúc khi câu hỏi vượt quá khả năng của Actuator.

## 2. Bức tranh tổng thể: tình trạng, cấu trúc và tương tác

Xét một ứng dụng bán hàng có ba application module:

~~~text
com.example.shop
├── ShopApplication.java
├── ordering
│   ├── OrderService.java
│   └── OrderPlaced.java
├── inventory
│   └── InventoryService.java
└── notification
    └── OrderPlacedListener.java
~~~

`ordering` gọi `inventory` để giữ hàng, sau đó phát sự kiện `OrderPlaced`. `notification` xử lý sự kiện và gửi thông báo. Khi ứng dụng chạy, người vận hành có thể cần biết liệu dịch vụ có sẵn sàng nhận traffic, kỹ sư kiến trúc cần biết quan hệ phụ thuộc nào tồn tại, còn người xử lý lỗi cần biết yêu cầu đặt hàng đã đi qua module nào.

~~~mermaid
flowchart LR
    A["Spring Boot + Spring Modulith"]
    H["/actuator/health"]
    M["/actuator/modulith"]
    O["Metrics / Traces / Logs"]
    A --> H
    A --> M
    A --> O
    H --> HS["Sức khỏe và độ sẵn sàng được kiểm tra"]
    M --> MS["Cấu trúc module và dependencies"]
    O --> OS["Tần suất và đường đi thực thi đã quan sát"]
~~~

| Câu hỏi | Nguồn thông tin phù hợp |
| --- | --- |
| Dịch vụ có đang báo `UP` hay `DOWN`? | `/actuator/health`. |
| Pod có nên nhận request mới không? | Health group `readiness` khi được kích hoạt và cấu hình phù hợp. |
| Ứng dụng có các module nào? | `/actuator/modulith`. |
| `ordering` phụ thuộc module nào? | `/actuator/modulith` và tài liệu module graph. |
| Có phụ thuộc vòng hoặc truy cập trái phép vào package internal? | `ApplicationModules.verify()` trong test/CI. |
| Request chậm do thao tác nào? | Traces và metrics được instrument phù hợp. |

Sơ đồ và bảng trên xác định **trách nhiệm của từng nguồn** trước khi đi vào cấu hình cụ thể.

## 3. Endpoint `health`: kiểm tra tình trạng hoạt động

### 3.1. `health` thuộc Spring Boot Actuator

`health` là endpoint có sẵn của Spring Boot Actuator, không phải một endpoint do Spring Modulith định nghĩa. Khi dự án khai báo `spring-boot-starter-actuator` và endpoint được phép truy cập, URL HTTP mặc định thường là:

~~~http
GET /actuator/health
~~~

Theo mặc định, Spring Boot chỉ expose `health` trong các Actuator endpoint qua HTTP. Câu trả lời đơn giản thường có dạng:

~~~json
{
  "status": "UP"
}
~~~

`UP` là kết quả tổng hợp từ các *health contributor* đang được đăng ký trong ứng dụng, theo quy tắc tổng hợp trạng thái. Các trạng thái thường gặp gồm `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN`. `HealthIndicator` có thể kiểm tra các thành phần như datasource, disk space, Redis hoặc một dịch vụ bên ngoài, nếu tương ứng có trong ứng dụng và được bật.

**Không nên diễn giải `UP` thành “mọi thao tác nghiệp vụ đều đúng”.** Ví dụ: một health indicator cơ sở dữ liệu có thể kiểm tra kết nối thành công nhưng không biết hàm đặt hàng có lỗi logic, có gửi nhầm event hay có vi phạm ranh giới module không. Kết quả `UP` chỉ phản ánh phạm vi những phép kiểm tra hiện có.

### 3.2. Chi tiết sức khỏe và quyền truy cập

Các thuộc tính `management.endpoint.health.show-details` và `management.endpoint.health.show-components` quyết định mức thông tin về health được trả ra. Các mức hỗ trợ gồm `never`, `when-authorized` và `always`; mặc định chi tiết bị ẩn.

Ví dụ **minh họa** khi bật hiển thị các thành phần:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" },
    "ping": { "status": "UP" }
  }
}
~~~

Danh sách `components` và nội dung `details` thay đổi theo các `HealthIndicator` thực sự có mặt; Spring Boot không bắt buộc mọi ứng dụng phải có ba thành phần trên. Ở môi trường production, không tùy tiện dùng `show-details: always` cho endpoint công khai vì chi tiết kiểm tra có thể tiết lộ cấu hình hoặc thành phần nội bộ.

### 3.3. Health groups: liveness và readiness

Trong triển khai container/Kubernetes, Spring Boot hỗ trợ *health groups* để biểu đạt hai góc nhìn:

- **Liveness:** tiến trình còn ở trạng thái có thể tiếp tục hoạt động hay không; một probe liveness lỗi có thể khiến hệ thống điều phối khởi động lại tiến trình.
- **Readiness:** ứng dụng đã sẵn sàng nhận thêm request hay chưa; readiness lỗi thường dẫn đến tạm ngừng chuyển lưu lượng mới vào instance.

Khi được kích hoạt và expose phù hợp, có thể truy vấn:

~~~http
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Các group này chỉ phục vụ mục tiêu điều phối vận hành. Chúng **không trả danh sách module**. Đặc biệt, không nên thêm kiểm tra phụ thuộc ngoài như database vào liveness một cách máy móc; nếu hệ thống phụ thuộc ngoài gặp sự cố, việc khởi động lại hàng loạt instance có thể khiến tình hình xấu hơn. Nên thiết kế readiness theo khả năng phục vụ traffic của ứng dụng.

### 3.4. Mã trạng thái HTTP

Với mapping mặc định của Spring Boot, trạng thái tổng hợp `DOWN` và `OUT_OF_SERVICE` được ánh xạ thành HTTP 503; `UP` thường là HTTP 200. Mapping có thể được tùy biến. Khi giám sát, cần đọc **cả HTTP status code và nội dung JSON**; không nên mặc định mọi phản hồi 200 đều tương đương tình trạng sức khỏe hoàn toàn tốt trong mọi cấu hình.

## 4. Endpoint `modulith`: công bố cấu trúc application module

### 4.1. `modulith` do Spring Modulith cung cấp

Khác với `health`, endpoint có ID `modulith` được triển khai bởi thành phần **Spring Modulith Actuator**. Nó cần dependency `spring-modulith-actuator` cùng hạ tầng Spring Boot Actuator, hoặc starter tổng hợp `spring-modulith-starter-insight`.

Khi endpoint được phép truy cập và expose qua HTTP, URL thường là:

~~~http
GET /actuator/modulith
~~~

Kết quả là một tài liệu JSON mô tả **tập application module được nhận diện ở runtime**. Mỗi khóa cấp cao là định danh kỹ thuật của một module; các trường chính gồm `displayName`, `basePackage` và `dependencies`. Nếu có module lồng nhau, cấu trúc còn có thể chứa `parent` hoặc `nested`.

Ví dụ trả lời **minh họa**:

~~~json
{
  "ordering": {
    "displayName": "Ordering",
    "basePackage": "com.example.shop.ordering",
    "dependencies": [
      {
        "target": "inventory",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "inventory": {
    "displayName": "Inventory",
    "basePackage": "com.example.shop.inventory",
    "dependencies": []
  },
  "notification": {
    "displayName": "Notification",
    "basePackage": "com.example.shop.notification",
    "dependencies": [
      {
        "target": "ordering",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

Không có trường `status: UP` hoặc `status: DOWN` dành cho các module trong kiểu payload này. `modulith` mô tả **module và dependency**, không tính tình trạng sức khỏe của từng module.

### 4.2. Đọc các trường phụ thuộc

| Trường | Ý nghĩa |
| --- | --- |
| `ordering`, `inventory`, `notification` | Định danh module, cũng là khóa mà `dependencies[].target` tham chiếu. |
| `displayName` | Tên hiển thị dễ đọc. |
| `basePackage` | Package gốc thuộc module. |
| `dependencies[]` | Danh sách các phụ thuộc **đi ra** từ module hiện tại. |
| `dependencies[].target` | Module đích được module hiện tại sử dụng/tham chiếu. |
| `dependencies[].types[]` | Các loại phụ thuộc: `DEFAULT`, `USES_COMPONENT` hoặc `EVENT_LISTENER`. |
| `parent`, `nested` | Thông tin về module cha và các module lồng nhau nếu tồn tại. |

Giải thích các loại quan hệ theo mô hình Spring Modulith:

- `DEFAULT` biểu thị quan hệ phụ thuộc kiểu mã nguồn thông thường.
- `USES_COMPONENT` biểu thị quan hệ sử dụng Spring component.
- `EVENT_LISTENER` biểu thị quan hệ được nhận diện qua listener sự kiện.

Một module có thể có nhiều loại quan hệ với cùng đích. `dependencies[].types[]` khi đó là một mảng, không nhất thiết chỉ có một giá trị.

### 4.3. Chiều phụ thuộc khác chiều sự kiện

Ví dụ `notification` chứa listener nhận `OrderPlaced` do `ordering` công bố. Mã `notification` tham chiếu kiểu event từ `ordering` nên graph có thể có cạnh **`notification → ordering`**, trong khi thông điệp nghiệp vụ thực tế đi từ `ordering` đến `notification`.

~~~mermaid
flowchart LR
    subgraph Static["Phụ thuộc cấu trúc (Actuator)"]
        N1["notification"] -->|"EVENT_LISTENER"| O1["ordering"]
    end
    subgraph Runtime["Luồng phát sự kiện nghiệp vụ"]
        O2["ordering"] -->|"publish OrderPlaced"| N2["notification"]
    end
~~~

Hai chiều biểu diễn hai quan hệ khác nhau và không mâu thuẫn. Cũng vì vậy, đọc `modulith` không thể chứng minh listener đã chạy, đã gửi email hoặc đã xử lý event thành công.

### 4.4. Ranh giới của dữ liệu kiến trúc

Endpoint `modulith` không cho biết số request, error rate, thời gian thực thi module hoặc lượng event được phát. Nó cũng không phải bộ kiểm tra tự động toàn bộ quy tắc kiến trúc. Muốn phát hiện phụ thuộc vòng, truy cập vào internal package trái phép hoặc vi phạm `allowedDependencies`, nên chạy `ApplicationModules.verify()` trong test/CI.

Một chi tiết quan trọng khi dùng Spring Modulith: nếu custom module detection được đặt **chỉ trong test sources**, tính năng runtime như Actuator có thể không nhận đúng cấu trúc mà test mong đợi. Muốn chúng nhất quán, hãy cấu hình phần phát hiện module cần thiết trong production sources.

## 5. Bảng so sánh trực tiếp

| Tiêu chí | `/actuator/health` | `/actuator/modulith` |
| --- | --- | --- |
| Nguồn cung cấp | Spring Boot Actuator. | Spring Modulith Actuator. |
| Mục tiêu | Quan sát sức khỏe, khả năng hoạt động của hệ thống theo các phép kiểm tra. | Công bố cấu trúc application module và quan hệ phụ thuộc. |
| Dữ liệu cốt lõi | `status`, có thể có `components` và `details`. | Tên module, `basePackage`, `dependencies`, loại phụ thuộc. |
| Tính biến động | Có thể thay đổi ngay khi tình trạng hệ thống thay đổi. | Thường ổn định theo phiên bản code/cấu hình đang chạy; không đếm lời gọi. |
| Phụ thuộc cần thiết | `spring-boot-starter-actuator`. | `spring-modulith-actuator` và Actuator, hoặc `spring-modulith-starter-insight`. |
| HTTP exposure mặc định | `health` được expose mặc định. | Cần đưa `modulith` vào danh sách expose nếu muốn gọi qua HTTP. |
| Dùng cho orchestration/probes | Có thể làm health, liveness, readiness probe. | Không dùng để quyết định restart hoặc phân phối traffic. |
| Mức độ nhạy cảm | Chi tiết HealthIndicator có thể tiết lộ nội bộ. | Tiết lộ cấu trúc package/module và quan hệ bên trong. |
| Trả lời “module nào gọi module nào lúc 10:30?” | Không. | Không; muốn biết tương tác theo request phải dùng traces/logs. |
| Trả lời “module graph có đúng quy tắc?” | Không. | Hỗ trợ xem cấu trúc, nhưng cần kiểm chứng tĩnh bằng `ApplicationModules.verify()`. |

## 6. Cấu hình cho ứng dụng mẫu

### 6.1. Khai báo dependency

Nếu dự án dùng cả Actuator module và observability, có thể chọn **Insight Starter**:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
}
~~~

Ví dụ Gradle Kotlin DSL trên giả định dự án đã quản lý phiên bản Spring Modulith tương thích với Spring Boot bằng BOM/plugin. Insight Starter đưa vào hỗ trợ Actuator của Spring Modulith, observability và hạ tầng Spring Boot Actuator. Việc hiển thị traces trên Zipkin/Tempo hoặc xuất metrics qua Prometheus cần các registry, tracer và exporter riêng khi có nhu cầu.

Nếu chỉ cần `modulith` endpoint mà chưa cần quan sát tương tác giữa các module:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-actuator")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Trong ví dụ này, hai dependency đủ xác định ý tưởng cấu hình; quản lý phiên bản vẫn cần tương thích với project. Chỉ dùng `spring-boot-starter-actuator` sẽ có `health` nhưng **không tự có `modulith`**.

### 6.2. Expose hai endpoint

Ví dụ `application.yml` cho môi trường học tập hoặc mạng quản trị đã được bảo vệ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,modulith"
  endpoint:
    health:
      show-details: never
~~~

Điều này làm rõ hai ý:

1. `health` vốn là endpoint được expose mặc định; việc liệt kê lại giúp cấu hình minh bạch.
2. `modulith` cần xuất hiện trong `management.endpoints.web.exposure.include` nếu muốn truy vấn qua HTTP; expose **không tự cấp quyền vượt qua lớp bảo mật**.

Trong các phiên bản Spring Boot mới, endpoint còn chịu cấu hình quyền truy cập như `management.endpoint.<id>.access`. Nếu endpoint bị vô hiệu hóa ở mức access hoặc bị chặn bởi Spring Security, chỉ thêm `exposure.include` là chưa đủ để truy cập.

**Không dùng `management.endpoints.web.exposure.include: "*"` một cách tùy tiện** trong môi trường production. Việc mở toàn bộ endpoint có thể làm lộ thông tin quản trị không cần thiết. Giới hạn đường truy cập bằng xác thực, phân quyền và mạng nội bộ; với `modulith` cần lưu ý nó tiết lộ kiến trúc ứng dụng.

### 6.3. Truy vấn và so sánh phản hồi

Khi ứng dụng đã khởi động tại `localhost:8080` và cổng management trùng cổng ứng dụng:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/modulith
~~~

Giả sử cơ sở dữ liệu không truy cập được nhưng ứng dụng vẫn đủ khả năng phục vụ management endpoint, `health` có thể trả HTTP 503 cùng nội dung:

~~~json
{
  "status": "DOWN"
}
~~~

Trong khi đó, `modulith` có thể tiếp tục trả cấu trúc module như ví dụ ở mục 4, vì graph không được tính từ kết nối database. Nếu toàn bộ tiến trình chết hoặc management server không phục vụ được HTTP, **cả hai URL** đều có thể không truy cập được. Endpoint `modulith` không bảo đảm luôn sẵn sàng trong mọi trạng thái lỗi.

Đường dẫn `/actuator` và cổng `8080` chỉ là mặc định thường gặp. Nếu có `management.server.port` hoặc `management.endpoints.web.base-path`, phải dùng đúng địa chỉ và đường dẫn tương ứng.

## 7. Bốn tình huống giúp tránh nhầm lẫn

### Tình huống A: `health=UP` nhưng thiết kế module sai

Nhóm phát triển vô tình cho `ordering` gọi trực tiếp vào lớp `inventory.internal.InventoryJpaAdapter` thay vì đi qua API công khai của `inventory`. Các HealthIndicator vẫn thành công nên `/actuator/health` trả `UP`.

Ở đây, `UP` chỉ xác nhận tình trạng của những phép kiểm tra được đăng ký. Để xác định và ngăn chặn truy cập internal, nên chạy test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithArchitectureTests {

    @Test
    void modulesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test giả định dự án đã thêm dependency kiểm thử Spring Modulith tương ứng và `ShopApplication` nằm trong classpath. Khi vi phạm quy tắc được Spring Modulith kiểm tra, phép xác minh sẽ phát hiện vấn đề. `modulith` cho ta sơ đồ quan hệ được nhận diện, còn `verify()` thực thi kiểm chứng quy tắc.

### Tình huống B: `health=DOWN` nhưng module graph vẫn hợp lệ

Kết nối datasource bị ngắt. HealthIndicator `db` báo `DOWN`, khiến health tổng hợp bị ảnh hưởng và hệ thống giám sát báo lỗi. Nhưng ba module `ordering`, `inventory`, `notification` cùng quan hệ phụ thuộc của chúng không hề thay đổi. `modulith` vẫn có thể cung cấp cùng đồ thị.

Kết luận đúng: **sự cố vận hành không mặc nhiên đồng nghĩa lỗi tổ chức module**. Hướng điều tra là datasource, kết nối mạng, cấu hình hoặc hạ tầng, dựa trên health details và logs phù hợp.

### Tình huống C: `health=UP` nhưng `/actuator/modulith` trả 404

Chỉ có `spring-boot-starter-actuator` trong classpath hoặc endpoint `modulith` chưa được expose. `health` xuất hiện bình thường, nhưng không có tài nguyên `modulith` qua HTTP.

Đừng kết luận ứng dụng không dùng module hoặc mọi module đã bị xóa. Hãy kiểm tra artifact Spring Modulith Actuator, HTTP exposure, endpoint access, base path, cổng management và cấu hình bảo mật. HTTP 401/403 thường liên quan đến quyền truy cập; 404 có nhiều nguyên nhân, trong đó có endpoint không được đăng ký hoặc không được expose.

### Tình huống D: `modulith` có cạnh nhưng trace không có lời gọi

JSON cho thấy `ordering` phụ thuộc `inventory` nhưng trace của một request không có span `inventory`. Điều này **không chứng minh** graph sai. Request có thể đi qua nhánh xử lý khác, instrumentation chưa quan sát được điểm vào API, sampling đã bỏ trace hoặc context của luồng bất đồng bộ không được truyền.

Muốn điều tra một giao dịch cụ thể phải kết hợp **traces**, **metrics** và **logs**, chứ không đọc `modulith` như nhật ký lời gọi.

## 8. `health` có phải “sức khỏe từng application module” không?

Không mặc định. Spring Boot `health` thu thập trạng thái từ các `HealthIndicator`/**`HealthContributor`** đã đăng ký, còn application module là cách tổ chức mã nguồn theo ranh giới chức năng. Spring Modulith không tự biến mỗi module thành một HealthIndicator chỉ vì đã dùng `spring-modulith-starter-insight`.

Ví dụ: nếu muốn kiểm tra một integration bên ngoài mà `payment` phụ thuộc, bạn có thể viết `HealthIndicator` cho integration đó và đưa vào health group phù hợp. Kết quả vẫn là **sức khỏe của một điều kiện vận hành cụ thể**, không phải điểm số “độ sạch kiến trúc” của module `payment`.

Không nên gán cho từng module các trạng thái `UP/DOWN` chỉ dựa vào việc nó có xuất hiện trong `/actuator/modulith`. Ngược lại, nếu có HealthIndicator riêng đặt tên `paymentGateway`, đó là chỉ báo kết nối hoặc nghiệp vụ được lập trình có chủ đích, **không phải trường chuẩn trong JSON của `modulith`**.

## 9. Đối chiếu với metrics, traces và tài liệu kiến trúc

Spring Modulith hỗ trợ quan sát tương tác module bằng Micrometer. Khi cấu hình observability phù hợp, các lời gọi đi qua API module có thể sinh observation/span; domain event được phát có thể được ghi nhận bằng metrics như `module.events.published`. Các tín hiệu này bổ sung góc nhìn mà `health` và `modulith` không cung cấp.

Một quy trình điều tra thực tế:

1. **Kiểm tra `health`:** dịch vụ có đang báo lỗi vận hành hoặc không sẵn sàng nhận traffic?
2. **Đọc `modulith`:** phiên bản runtime nhận diện các module và quan hệ phụ thuộc nào?
3. **Đọc metrics:** tần suất sự kiện hay độ trễ có bất thường không, trong phạm vi những meter đã instrument?
4. **Đọc traces/logs:** request cụ thể đi qua những bước nào, chậm ở đâu, có mất trace context ở ranh giới bất đồng bộ không?
5. **Chạy kiến trúc test:** những dependency có tuân thủ quy tắc module không?

Các nguồn này trả lời các phần khác nhau của cùng một câu chuyện. **Health không kiểm tra ranh giới module; module graph không đo uptime; metrics/traces không tự thay thế phép kiểm tra kiến trúc tĩnh.**

## 10. Bài thực hành ngắn

**Bối cảnh:** ứng dụng Shop có `ordering`, `inventory`, `notification`; nhóm vận hành cần phân biệt tín hiệu lỗi kết nối database với tín hiệu cấu trúc module.

**Bước 1.** Thêm `spring-modulith-starter-insight` hoặc cặp `spring-modulith-actuator` và `spring-boot-starter-actuator` theo cấu hình ở mục 6. Kiểm tra phiên bản Spring Boot/Spring Modulith tương thích.

**Bước 2.** Bật `management.endpoints.web.exposure.include: "health,modulith"` trong môi trường thử nghiệm có quyền truy cập phù hợp.

**Bước 3.** Gọi hai endpoint bằng `curl -i`. Ghi lại HTTP status code, các trường JSON và sự khác nhau trong nội dung.

**Bước 4.** Nếu có môi trường thử nghiệm an toàn, gây mất kết nối datasource để quan sát thay đổi ở `health`. So sánh xem cấu trúc JSON của `modulith` có thay đổi hay không khi tiến trình vẫn chạy.

**Bước 5.** Tạo một phụ thuộc mã nguồn không mong muốn *trong nhánh thử nghiệm*, chạy `ApplicationModules.verify()` để xem phép kiểm chứng ranh giới phát hiện được gì. Hoàn tác thay đổi thử nghiệm sau khi học.

**Bước 6.** Tổng hợp kết quả vào bảng:

| Quan sát | Diễn giải đúng |
| --- | --- |
| `health` báo `UP` | Các phép health check được đăng ký đang tổng hợp ra trạng thái tốt; chưa chứng minh logic/kiến trúc đúng. |
| `health` báo `DOWN` | Có health contributor báo tình trạng lỗi theo quy tắc tổng hợp; cần đọc thêm chi tiết/log. |
| `modulith` trả danh sách module | Có thể kiểm tra cấu trúc runtime được nhận diện; chưa kết luận được tình trạng vận hành. |
| `modulith` có cạnh không mong muốn | Có tín hiệu để kiểm tra thiết kế và test kiến trúc; JSON tự nó không cho biết mức độ ảnh hưởng hoặc thời điểm thực thi. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `/actuator/health` trả `UP` không đủ để khẳng định ứng dụng tuân thủ quy tắc Spring Modulith?

**Trả lời:** Vì health chỉ tổng hợp các phép kiểm tra vận hành đã cấu hình; phát hiện phụ thuộc sai trong mã nguồn cần xác minh kiến trúc, chẳng hạn bằng `ApplicationModules.verify()`.

**Câu 2.** Có thể dùng `/actuator/modulith` làm Kubernetes liveness probe không?

**Trả lời:** Không nên. Endpoint này mô tả cấu trúc module và không được thiết kế để quyết định tiến trình cần restart. Nên dùng health group liveness/readiness theo cấu hình vận hành.

**Câu 3.** Vì sao có `/actuator/health` mà không có `/actuator/modulith`?

**Trả lời:** `health` thuộc Spring Boot Actuator; `modulith` cần hỗ trợ Spring Modulith Actuator hoặc Insight Starter, đồng thời phải được expose và được cấp quyền truy cập.

**Câu 4.** Module graph cho thấy `notification → ordering` theo loại `EVENT_LISTENER`. Điều này có phủ nhận việc `ordering` phát `OrderPlaced` cho `notification` không?

**Trả lời:** Không. Mũi tên graph biểu diễn chiều tham chiếu/quan hệ phụ thuộc mã nguồn; luồng sự kiện nghiệp vụ có thể đi theo chiều ngược lại.

**Câu 5.** Muốn biết trong một request cụ thể `inventory` có bị gọi và chậm hay không, nên dùng endpoint nào?

**Trả lời:** Dùng traces/logs và instrumentation phù hợp; `health` không mô tả đường đi request, còn `modulith` chỉ mô tả dependency có trong kiến trúc.

## 12. Tài liệu tham khảo

- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): HTTP exposure, bảo mật, dữ liệu `health`, HealthIndicator và health groups.
- [Spring Boot – Actuator Health API](https://docs.spring.io/spring-boot/api/rest/actuator/health.html): cấu trúc phản hồi health.
- [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): `spring-modulith-actuator`, `spring-modulith-starter-insight` và JSON của endpoint `modulith`.
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): xác minh ranh giới và phụ thuộc module.
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): vai trò observation, metrics và traces.

**Ghi nhớ:** `/actuator/health` kiểm tra **tình trạng vận hành** theo những chỉ báo đã khai báo; `/actuator/modulith` công bố **cấu trúc application module** đang được nhận diện. Khi cần đánh giá hoạt động qua ranh giới, kết hợp metrics, traces và kiểm thử kiến trúc; không suy luận kết quả của nguồn dữ liệu này từ nguồn dữ liệu kia.
