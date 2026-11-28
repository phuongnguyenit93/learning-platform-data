# Phân biệt tài liệu kiến trúc với bằng chứng runtime

> **Chương:** Tổng quan  
> **Chủ đề:** Phân biệt tài liệu kiến trúc với bằng chứng runtime  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.  
> **Phạm vi:** Spring Modulith trong ứng dụng Spring Boot; module graph, tài liệu do `Documenter` sinh ra, Actuator, Micrometer metrics/tracing, event publication và context propagation.

## 1. Vì sao phải phân biệt hai loại thông tin?

Giả sử nhóm phát triển đang xây dựng một ứng dụng thương mại điện tử gồm các application module `order`, `inventory` và `notification`. Nhóm có sơ đồ cho biết `inventory` lắng nghe sự kiện `OrderCompleted` từ `order`. Khi đơn hàng được hoàn tất, một khách hàng phản ánh tồn kho chưa được cập nhật.

Sơ đồ kiến trúc **chỉ cho biết các thành phần có quan hệ hoặc được thiết kế để tương tác**. Nó không trả lời được liệu sự kiện của đơn hàng cụ thể đã được phát ra, listener có thực thi, xử lý có lỗi hay ngữ cảnh trace có bị mất khi chuyển sang luồng khác. Muốn trả lời các câu hỏi đó, cần bằng chứng từ một lần vận hành thực tế.

Có hai nhóm câu hỏi khác nhau:

- **Cấu trúc / kiến trúc:** Ứng dụng được chia thành những module nào? API công khai ở đâu? Module nào phụ thuộc module nào? Có vi phạm quy tắc phụ thuộc, truy cập implementation nội bộ hoặc tạo vòng phụ thuộc không?
- **Hành vi / vận hành:** Trong một khoảng thời gian cụ thể, lời gọi nào thực sự diễn ra? Sự kiện được phát bao nhiêu lần? Listener nào đã xử lý thành công hoặc thất bại? Độ trễ ở đâu? Dấu vết có được nối qua tác vụ bất đồng bộ không?

Spring Modulith cung cấp công cụ cho cả hai nhóm. Giá trị của nó nằm ở việc **kết hợp mô hình module và chứng cứ vận hành**, đồng thời hiểu chính xác giới hạn của từng nguồn.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích được sự khác biệt giữa **quan hệ phụ thuộc có trong mã nguồn** và **tương tác thực sự quan sát được**.
2. Phân loại kết quả từ `ApplicationModules`, `Documenter`, `verify()`, `/actuator/modulith`, metric, trace và Event Publication Registry.
3. Dùng một tình huống xử lý sự kiện giữa các module để xác định bằng chứng còn thiếu và cách thu thập.
4. Thiết kế quy trình đối chiếu tài liệu kiến trúc với runtime theo đúng phiên bản, môi trường và khoảng thời gian.

## 2. Hai góc nhìn lên cùng một ứng dụng

### 2.1. Tài liệu kiến trúc là mô hình cấu trúc

Spring Modulith nhận diện **application module** dựa trên cách tổ chức Java package và các quy ước/cấu hình module. Một module thường có phần API có thể dùng từ module khác và phần triển khai nội bộ không nên bị truy cập trực tiếp.

Ví dụ giả định:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java         # API công khai của module order
│   ├── OrderCompleted.java          # Kiểu sự kiện được chia sẻ
│   └── internal
│       └── OrderRepositoryAdapter.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── OrderCompletedListener.java
└── notification
    ├── NotificationManagement.java
    └── internal
        └── NotificationSender.java
~~~

Theo cách nhận diện module mặc định của một ứng dụng phù hợp với các quy ước này, `order`, `inventory` và `notification` là các module logic. Mô hình đó có thể sinh ra **module graph** và **Application Module Canvas**:

- **Module graph / component diagram:** cho biết những module đã được phát hiện và các quan hệ phụ thuộc mà công cụ phân tích mã nhận diện.
- **Application Module Canvas:** tóm tắt base package, Spring component được công bố, aggregate root, event được công bố/lắng nghe, cấu hình... tùy loại metadata mà công cụ có thể nhận diện.
- **Kiểm tra ràng buộc:** `ApplicationModules.verify()` xác minh các nguyên tắc như không có vòng phụ thuộc, không truy cập package nội bộ trái phép và tuân thủ `allowedDependencies` nếu đã khai báo.

Những kết quả này là **bằng chứng về cấu trúc của phiên bản mã đã phân tích**. Chúng không tự động chứng minh lưu lượng sự kiện, thời gian thực thi hoặc kết quả giao dịch.

### 2.2. Bằng chứng runtime là quan sát có ngữ cảnh

Bằng chứng runtime được tạo ra khi ứng dụng chạy, từ những nguồn như:

- **Trace/span:** ghi nhận một hành trình hoặc đoạn thực thi được instrument, ví dụ lời gọi đi vào public API của module hoặc listener sự kiện.
- **Metric:** số liệu tổng hợp theo thời gian, ví dụ số sự kiện đã được phát hoặc tổng số lần một phép đo được ghi nhận.
- **Event Publication Registry:** nếu được cấu hình lưu trữ phù hợp, lưu bản ghi các lần công bố sự kiện đến transactional listener và trạng thái xử lý của chúng.
- **Log có correlation:** các thông báo có `traceId`/`spanId` và thông tin nghiệp vụ được phép ghi, giúp ghép các mốc trong quá trình xử lý.

Dù vậy, bằng chứng runtime luôn có **phạm vi quan sát**: phiên bản triển khai, môi trường, traffic, thời điểm, sampling, instrumentation và khả năng xuất dữ liệu. Một trace không xuất hiện **không đủ để kết luận** một lời gọi chưa từng xảy ra.

### 2.3. Cùng một đường nối, hai ý nghĩa

Xét ví dụ `inventory` sử dụng kiểu `OrderCompleted` do `order` công bố:

~~~mermaid
flowchart LR
    subgraph Static["Mô hình cấu trúc"]
        I["inventory"] -->|"phụ thuộc kiểu OrderCompleted"| O["order"]
    end
    subgraph Runtime["Một lượt xử lý quan sát được"]
        P["order: publish OrderCompleted"] -->|"event được xử lý"| C["inventory: listener"]
    end
~~~

Trong **đồ thị phụ thuộc tĩnh**, mũi tên có thể biểu diễn `inventory → order` vì mã của listener trong `inventory` tham chiếu kiểu sự kiện của `order`. Trong **đồ thị luồng thực thi**, ta lại kể câu chuyện `order → inventory` vì `order` phát ra sự kiện và `inventory` xử lý. Hai mũi tên có thể ngược chiều nhưng **không mâu thuẫn**: chúng biểu diễn hai loại quan hệ khác nhau.

Vì thế không nên tự động so sánh từng cạnh của hai đồ thị bằng phép trừ tập hợp, khi chưa chuẩn hóa **ngữ nghĩa cạnh**, hướng cạnh và mức độ instrument.

## 3. Bảng phân biệt nguồn thông tin

| Nguồn | Bản chất | Trả lời được | Không đủ để khẳng định |
|---|---|---|---|
| `ApplicationModules` và module graph | Mô hình suy ra từ mã/cấu hình | Module nào tồn tại, phụ thuộc được phát hiện | Các cạnh đó đã được thực thi trong request cụ thể |
| `Documenter` (PlantUML, C4/UML, Canvas) | Tài liệu sinh từ mô hình module | Bản đồ cấu trúc để đọc, thảo luận, review | Listener đang hoạt động hoặc dữ liệu đã cập nhật |
| `ApplicationModules.verify()` | Kiểm tra quy tắc kiến trúc | Các ràng buộc được kiểm có đạt hay không | Tính đúng đắn của quy trình nghiệp vụ khi chạy |
| `GET /actuator/modulith` | Metadata kiến trúc lấy từ ứng dụng đang chạy | Module và dependency của artifact được triển khai | Số lần gọi module, kết quả xử lý event, latency |
| Micrometer metric | Số liệu tổng hợp lúc chạy | Xu hướng/tổng số cho sự kiện được instrument | Đường đi đầy đủ của một đơn hàng cụ thể |
| Trace/span | Quan sát một luồng thực thi được thu thập | Các bước, thời gian, quan hệ parent/child nếu có propagation | Tất cả các lần thực thi, đặc biệt khi sampling nhỏ |
| Event Publication Registry | Bản ghi vòng đời phát event đến listener thuộc phạm vi registry | Publication nào còn chờ, đang xử lý, hoàn tất, thất bại tùy phiên bản/cấu hình | Mọi event của ứng dụng đều được quản lý hoặc consumer chắc chắn đã hoàn thành toàn bộ tác dụng bên ngoài |
| Log có correlation | Bản ghi được lập trình viên/khung nền phát ra | Ngữ cảnh lỗi, thông điệp từng bước có thể liên kết | Sự đầy đủ, tính nhất quán hay thứ tự tuyệt đối trên mọi luồng |

**Quy tắc đọc:** Với mỗi bằng chứng, hãy ghi rõ *nó được thu ở đâu, khi nào, bằng phiên bản nào và bằng cơ chế nào*. Một tài liệu sinh từ commit A và trace từ phiên bản B có thể khác nhau chỉ vì mã đã thay đổi.

## 4. Tạo và kiểm chứng tài liệu kiến trúc bằng Spring Modulith

### 4.1. Xác minh phụ thuộc trước khi xuất tài liệu

Trong test dùng JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleArchitectureTests {

    @Test
    void verifyStructureAndWriteDocumentation() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        // Phát hiện các vi phạm quy tắc cấu trúc đã được hỗ trợ.
        modules.verify();

        // Sinh sơ đồ toàn hệ thống, sơ đồ theo module và canvas.
        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml()
                .writeModuleCanvases();
    }
}
~~~

Các import/test nằm trong dự án demo có `ShopApplication`; khi dùng thực tế, đặt lớp test trong package phù hợp và bảo đảm các artifact Spring Modulith đã có trong classpath test. Chẳng hạn `spring-modulith-starter-test` bao gồm hỗ trợ `spring-modulith-docs`. Dự án nên quản lý phiên bản qua Spring Modulith BOM tương thích với phiên bản Spring Boot hiện dùng.

Mặc định, tài liệu được sinh dưới thư mục `spring-modulith-docs` trong thư mục build. Tùy cấu hình, `Documenter` có thể tạo sơ đồ C4/UML và canvas ở dạng snippet AsciiDoc/PlantUML để đưa vào tài liệu dự án.

**Cần diễn giải đúng kết quả:**

- Test `verify()` chạy thành công cho biết **các quy tắc do công cụ kiểm tra không phát hiện vi phạm** trên mô hình đã tạo. Nó không thay cho kiểm thử giao dịch, phân quyền hay tích hợp.
- Một mũi tên `inventory → order` cho thấy phụ thuộc được nhận diện trong mã. Nó không cho biết event đã được phát bao nhiêu lần.
- Canvas liệt kê listener có nghĩa là khai báo listener được tìm thấy theo cơ chế nhận diện; chưa có kết luận rằng listener đã xử lý thành công sự kiện nào.

### 4.2. Actuator công bố kiến trúc của ứng dụng đã triển khai

Có thể thêm hỗ trợ Actuator và observability bằng Spring Modulith Insight starter, hoặc khai báo riêng `spring-modulith-actuator` và Spring Boot Actuator. Ví dụ với Gradle và BOM đã được cấu hình:

~~~groovy
dependencies {
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Cấu hình cho môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith,metrics
~~~

Sau khi khởi động và khi endpoint đã được cho phép truy cập:

~~~http
GET http://localhost:8080/actuator/modulith
~~~

Ví dụ dữ liệu **minh họa** (tên module và quan hệ phụ thuộc tùy dự án thực tế):

~~~json
{
  "order": {
    "basePackage": "com.acme.shop.order",
    "displayName": "Order",
    "dependencies": []
  },
  "inventory": {
    "basePackage": "com.acme.shop.inventory",
    "displayName": "Inventory",
    "dependencies": [
      {
        "target": "order",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

Endpoint **chính xác là `/actuator/modulith`**. Dù được gọi trên một JVM đang chạy, kết quả này vẫn là **metadata cấu trúc**, không phải lịch sử giao tiếp giữa các module. Nó hữu ích để xác nhận *bản triển khai hiện tại nhìn thấy cấu trúc gì* và đối chiếu với tài liệu được sinh trong CI.

Ở môi trường có dữ liệu thật, chỉ bật các Actuator endpoint cần thiết và kiểm soát quyền truy cập theo chính sách của hệ thống. Không dùng việc endpoint trả HTTP 200 để suy ra toàn bộ luồng nghiệp vụ đang khỏe.

## 5. Thu thập bằng chứng runtime

### 5.1. Span và trace: lần thực thi nào đã đi qua ranh giới module?

Spring Modulith observability có thể tạo Micrometer span khi các Spring component thuộc API module được gọi qua cơ chế instrument của nó. Với lời gọi được quan sát, các thuộc tính hữu ích bao gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `module.identifier` | Định danh module |
| `module.name` | Tên module |
| `module.invocation-type` | Kiểu lời gọi (ví dụ gọi bean hay event listener) |
| `module.method` | Phương thức được gọi |

Để thấy các span trong Zipkin, Grafana hoặc hệ thống tracing khác, cần có **tracer, cấu hình export và nơi tiếp nhận trace** tương thích; thêm Insight starter đơn lẻ không bảo đảm tự có giao diện trace.

Một mẫu trace giả định:

~~~text
Trace 94a... (request POST /orders/42/complete)
  ├─ HTTP POST /orders/42/complete
  ├─ module: order / OrderManagement.complete(...)
  └─ module: inventory / OrderCompletedListener.on(...)
       └─ InventoryRepository.updateStock(...)
~~~

Tên span phụ thuộc phiên bản và cấu hình, nên cây trên chỉ diễn giải *quan hệ xử lý*, không phải định dạng trace cố định. Nếu listener chạy bất đồng bộ, span của nó có thể nằm trong một trace khác hoặc thiếu liên kết cha-con nếu context propagation chưa được cấu hình đúng.

**Trace làm rõ câu hỏi:** “Với request/trace này, module nào thực sự được quan sát, mất bao lâu, và lỗi nổi lên ở đoạn nào?” Trace không chứng minh mọi trường hợp khác đều giống như vậy.

### 5.2. Metric: sự kiện xuất hiện thường xuyên đến mức nào?

Theo tài liệu Spring Modulith, hỗ trợ observability ghi các counter cho sự kiện domain, trong đó có:

- `module.events.published`: counter tổng hợp các lần publish event được công cụ ghi nhận.
- `module.events.published.$moduleIdentifier.$simpleEventTypeName`: counter theo module và loại event cụ thể.

Các tag có thể gồm `module.identifier`, `module.name` và `module.event.type` tùy metric. Với Micrometer/Actuator phù hợp, có thể xem meter qua endpoint metrics hoặc xuất về hệ thống giám sát.

Giả sử `module.events.published` tăng thêm 20 trong một đợt thử nghiệm. Điều này **không đồng nghĩa** 20 listener đã xử lý thành công. Một event có thể có nhiều listener; cũng có thể listener bất đồng bộ chưa chạy hoặc thất bại. Counter publish đo **hành động phát**, không tự động là counter “đã xử lý thành công”.

Với câu hỏi độ trễ, tỷ lệ lỗi hoặc lượng event còn tồn, cần thêm phép đo chuyên biệt, trạng thái registry hoặc trace; đừng gán nghĩa không có trong tên và cơ chế metric.

### 5.3. Event Publication Registry: tình trạng giao sự kiện tới listener

Spring Modulith hỗ trợ Event Publication Registry để theo dõi các lần publish được chuyển tới **transactional event listener** thuộc phạm vi registry. Khi có backend registry bền vững được cấu hình (ví dụ JDBC/JPA hoặc backend phù hợp khác), dữ liệu có thể giúp phân biệt:

1. Event đã được ghi nhận để giao cho listener.
2. Listener đã bắt đầu hoặc đang xử lý.
3. Listener hoàn thành thành công hoặc thất bại.
4. Publication còn tồn đọng và có cần xử lý lại hay không.

Các trạng thái và API quản trị cụ thể tùy phiên bản Spring Modulith. Chẳng hạn ở các phiên bản mới có vòng đời `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED` và trạng thái liên quan đến resubmit. Không nên áp dụng cứng danh sách đó cho mọi phiên bản cũ.

Ví dụ khi đơn hàng 42 hoàn tất nhưng chưa trừ tồn kho:

| Quan sát | Giải thích hợp lý cần kiểm tra tiếp |
|---|---|
| Metric event đã tăng | Publisher có hoạt động; **chưa chứng minh** listener xử lý thành công |
| Registry có publication chưa hoàn tất | Có công việc dành cho listener đang chờ, đang chạy hoặc lỗi; cần đọc trạng thái thực tế |
| Trace có span listener và exception | Có bằng chứng xử lý đã vào listener và gặp lỗi ở lần thực thi được ghi nhận |
| Registry hoàn tất nhưng tồn kho vẫn sai | Listener đã trả về thành công theo cơ chế ghi nhận; cần kiểm tra logic nghiệp vụ, giao dịch, tác dụng phụ và dữ liệu |
| Không có trace listener | Chưa đủ kết luận: có thể không thực thi, không instrument, bị sampling hoặc bị mất context |

**Phân biệt quan trọng:** Insight starter phục vụ Actuator/observability; nó **không tự chứng minh** dự án đã cấu hình backend lưu Event Publication Registry. Muốn dùng registry như bằng chứng bền vững, hãy xác nhận dependency, cơ chế persistence, phạm vi listener và chiến lược dọn dẹp/khôi phục tương ứng.

### 5.4. Context propagation: giữ liên kết khi chuyển sang xử lý bất đồng bộ

`@ApplicationModuleListener` là cách thuận tiện để khai báo listener với semantics bất đồng bộ, có giao dịch riêng sau sự kiện giao dịch nguồn theo cách Spring Modulith hỗ trợ. Khi công việc chuyển thread, thông tin gắn với thread ban đầu như observation hiện hành, trace context hoặc MDC **không nhất thiết tự đi theo**.

Micrometer Context Propagation cùng `ContextPropagatingTaskDecorator` có thể truyền những context được hỗ trợ sang tác vụ chạy bằng executor đã cấu hình. Ví dụ cấu hình một executor cho xử lý `@Async`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration
class AsyncConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Cấu hình này cần thư viện `io.micrometer:context-propagation` phù hợp trên classpath và cần được áp dụng **đúng executor thực sự chạy listener**. Tùy framework, phạm vi asynchronous execution và cơ chế tạo tác vụ, cần kiểm tra thực nghiệm span/log để xác nhận trace context được nối. Decorator **không** thay thế giao dịch riêng, cũng không bảo đảm khôi phục mọi loại context ứng dụng.

Hãy quan sát một request phát `OrderCompleted`:

- Trước cấu hình propagation: log của publisher có `traceId=A`, còn log listener thiếu ID hoặc có ID khác mà không có liên kết.
- Sau cấu hình và xác minh: log listener được liên hệ với trace gốc theo cơ chế tracing đang dùng; việc liên hệ có thể thể hiện bằng cùng trace ID hoặc liên kết trace/span thích hợp.

Đây là lý do **thiếu quan hệ cha-con trong màn hình trace chưa chắc là thiếu lời gọi nghiệp vụ**. Cần kiểm tra cả cấu hình executor, sampling và cách exporter ghi nhận span.

## 6. Tình huống thực hành: một đơn hàng đã hoàn tất nhưng tồn kho không đổi

### 6.1. Mô hình mong đợi

Module `order` phát event public `OrderCompleted`; module `inventory` nghe event để cập nhật kho. Code minh họa rút gọn:

~~~java
// Trong module order, kiểu sự kiện nằm ở API mà module khác có thể dùng.
package com.acme.shop.order;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {}
~~~

~~~java
// Trong module order.
@Service
class OrderManagement {

    private final ApplicationEventPublisher events;

    OrderManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId) {
        // Ghi trạng thái đơn hàng thành COMPLETED.
        // Mã cập nhật dữ liệu thực tế đã được lược bỏ.
        events.publishEvent(new OrderCompleted(orderId));
    }
}
~~~

~~~java
// Trong module inventory.
@Component
class OrderCompletedListener {

    private final InventoryManagement inventory;

    OrderCompletedListener(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        inventory.decreaseForOrder(event.orderId());
    }
}
~~~

Các đoạn code thể hiện **ý tưởng tích hợp**, chưa phải ứng dụng có thể chạy độc lập: cần thêm import Spring, hiện thực persistence, đảm bảo giao dịch và cấu hình các thành phần tương ứng. Listener không truy cập `order.internal`; nó chỉ dùng event API từ module `order`.

### 6.2. Cách kiểm chứng từng bước

Giả sử tài liệu kiến trúc cho thấy `inventory` lắng nghe `OrderCompleted`. Một quy trình điều tra có thể thực hiện như sau:

| Bước | Câu hỏi | Dữ liệu cần xem | Điều có thể kết luận |
|---|---|---|---|
| 1. Xác nhận phiên bản | Bản đang chạy có đúng cấu trúc trong tài liệu? | Commit/build ID, output `Documenter` và `/actuator/modulith` | Metadata tĩnh có tương ứng bản triển khai không |
| 2. Xác nhận trigger | Lệnh hoàn tất đơn hàng có chạy? | HTTP trace, log nghiệp vụ, trạng thái đơn hàng | Request đã vào đâu và có cập nhật trạng thái không |
| 3. Xác nhận publish | Event có phát trong lần đó? | Log có correlation, event metric, registry nếu phù hợp | Có bằng chứng phát event trong phạm vi quan sát không |
| 4. Xác nhận consume | Listener có được giao việc và chạy? | Publication state, trace/span listener | Listener đã bắt đầu, hoàn thành hoặc gặp lỗi thế nào |
| 5. Xác nhận nghiệp vụ | Tồn kho có được giảm đúng? | Giá trị dữ liệu, kiểm tra giao dịch, integration test | Kết quả cuối cùng có đúng với yêu cầu không |
| 6. Xác nhận quan sát | Nếu trace thiếu, do instrumentation hay thực thi? | Sampling, exporter, executor, context propagation | Có lỗ hổng quan sát cần xử lý không |

**Ví dụ diễn giải ba kết quả khác nhau:**

- **A – Tài liệu có cạnh, không có event nào:** nguồn tĩnh đúng nhưng kịch bản hoàn tất đơn hàng chưa được kích hoạt, hoặc chưa thấy bằng chứng runtime. Không được ghi “tích hợp đã chạy” chỉ vì sơ đồ có cạnh.
- **B – Metric tăng, registry báo failed:** publisher đã phát nhưng xử lý tại một listener có vấn đề; cần xem exception và chính sách retry. Tài liệu không phát hiện được lỗi này.
- **C – Registry completed, dữ liệu vẫn sai:** việc listener trả về thành công không tự chứng minh tính đúng đắn nghiệp vụ; cần kiểm tra cách cập nhật tồn kho, điều kiện cạnh tranh và tính nhất quán dữ liệu.

### 6.3. Thực nghiệm có kiểm soát

Có thể thực hành trong môi trường thử nghiệm theo kịch bản:

1. Chạy `ApplicationModules.of(ShopApplication.class).verify()` và sinh lại graph/canvas từ đúng phiên bản build.
2. Kiểm tra cấu trúc xuất qua `/actuator/modulith` khớp metadata của build đang chạy.
3. Gửi một request tạo/hoàn tất đơn hàng có ID thử nghiệm; ghi nhận khoảng thời gian và correlation ID.
4. Xem metric publish trước/sau, trace của request và publication liên quan nếu registry được bật.
5. Cố ý gây lỗi có kiểm soát ở listener trong môi trường test; quan sát publication state, exception và ảnh hưởng đến tồn kho.
6. Khắc phục lỗi, chạy lại test để xác nhận hành vi, bao gồm tác động của retry và tính idempotent nếu hệ thống có xử lý lại event.

Không nên chỉ nhìn số counter tổng cộng trước/sau rồi gắn nó cho một đơn hàng khi môi trường có traffic đồng thời. Hãy dùng định danh correlation phù hợp, dữ liệu thử nghiệm riêng và khung thời gian rõ ràng.

## 7. Quy trình đối chiếu kiến trúc và runtime trong nhóm phát triển

Một quy trình hiệu quả có ba tầng:

**Tầng 1 – Trước khi triển khai (CI):**

- Sinh tài liệu với `Documenter` từ revision đang build.
- Chạy `verify()` trong test để phát hiện vi phạm ranh giới module.
- Lưu artifact tài liệu cùng commit, build ID và phiên bản dependency.

**Tầng 2 – Khi ứng dụng khởi động (deploy):**

- Lấy cấu trúc từ `/actuator/modulith` ở ứng dụng đã triển khai để xem module model tương ứng với build nào.
- Xác nhận môi trường observability đã bật, backend tracing/metrics hoạt động và cơ chế lọc/sampling phù hợp.
- Kiểm soát quyền xem Actuator và dữ liệu trace/log.

**Tầng 3 – Khi thực thi kịch bản nghiệp vụ:**

- Ghi nhận trace/span của luồng được chọn, metric event, log correlation và publication state khi có registry.
- Đối chiếu với mô hình nhưng giữ đúng ngữ nghĩa: *dependency* khác với *event flow*; *event published* khác với *event handled*; *listener completed* khác với *business outcome correct*.
- Đưa ra kết luận có điều kiện: **“Trong môi trường X, build Y, khoảng thời gian Z, với sampling và instrumentation đã biết, chúng tôi quan sát được...”**

### Ma trận chọn bằng chứng theo câu hỏi

| Câu hỏi người vận hành đặt ra | Bằng chứng nên dùng trước |
|---|---|
| Module `inventory` có được phép truy cập nội bộ `order` không? | `verify()` + định nghĩa API/named interface, allowed dependencies |
| Bản deploy hiện có những module nào? | `/actuator/modulith` + build metadata |
| Lần gọi đơn hàng này có thực sự đi qua `inventory` không? | Trace của request/sự kiện + correlation log |
| Đang phát bao nhiêu `OrderCompleted`? | Event counter + khoảng thời gian/tag phù hợp |
| Vì sao listener chưa cập nhật kho? | Registry state (nếu có), trace lỗi, log và dữ liệu nghiệp vụ |
| Vì sao thiếu span listener dù listener vẫn chạy? | Instrumentation, sampling, exporter và context propagation |
| Sau đổi kiến trúc có tạo cycle hay đi vào internal package? | `ApplicationModules.verify()` trong CI |

## 8. Những kết luận sai thường gặp

| Phát biểu dễ nhầm | Cách hiểu chính xác |
|---|---|
| “Graph có đường nối nên hai module đã giao tiếp ở production.” | Graph thể hiện phụ thuộc theo mô hình; cần runtime evidence để nói về lần giao tiếp thực tế. |
| “`/actuator/modulith` là endpoint lưu các lần gọi module.” | Endpoint đó công bố **cấu trúc module**; spans, metrics và sự kiện mới phản ánh hành vi chạy. |
| “`verify()` pass nghĩa là tính năng xử lý đơn hàng đúng.” | `verify()` kiểm tra ràng buộc kiến trúc; nghiệp vụ vẫn cần kiểm thử riêng. |
| “Counter published tăng 1 nghĩa là listener đã thành công 1 lần.” | Một lần publish khác với kết quả của từng listener, đặc biệt khi bất đồng bộ hoặc có nhiều consumer. |
| “Không có span nên code không chạy.” | Có thể do sampling, instrumentation, exporter, context propagation hoặc truy vấn sai thời gian. |
| “Registry ghi completed nghĩa là dữ liệu cuối cùng luôn đúng.” | Registry phản ánh hoàn tất listener theo cơ chế của nó; cần xác minh tác động nghiệp vụ độc lập. |
| “Tài liệu sinh tự động thì luôn khớp production.” | Tài liệu có thể sinh từ revision khác; hãy gắn cùng build ID để đối chiếu. |

## 9. Tự kiểm tra hiểu bài

**Câu 1.** `/actuator/modulith` liệt kê module `inventory` có phụ thuộc kiểu `EVENT_LISTENER` đến `order`. Có thể kết luận rằng tất cả `OrderCompleted` đều đã được xử lý không?

**Đáp án:** Không. Endpoint cho thấy một quan hệ phụ thuộc được suy ra từ cấu trúc, không phải lịch sử giao sự kiện. Cần xem publication state hoặc dữ liệu xử lý ở runtime.

**Câu 2.** Trong 5 phút, counter `module.events.published` tăng nhưng không tìm thấy trace listener. Có chắc listener không chạy?

**Đáp án:** Chưa chắc. Cần kiểm tra sampling, tracing backend, instrument, executor/context propagation và cả event registry nếu có. Counter này cũng có thể chứa event khác nếu không lọc tag.

**Câu 3.** `verify()` thành công nhưng listener vẫn gọi nhầm phương thức nghiệp vụ và tồn kho bị trừ hai lần. Có mâu thuẫn không?

**Đáp án:** Không. Quy tắc kiến trúc khác với tính đúng đắn về dữ liệu, idempotency và hiệu ứng khi retry.

**Câu 4.** Vì sao mũi tên static `inventory → order` và mũi tên runtime `order → inventory` có thể cùng đúng?

**Đáp án:** Cạnh static chỉ hướng phụ thuộc mã của consumer đến loại event thuộc publisher; cạnh runtime diễn đạt chiều lưu chuyển sự kiện từ publisher đến consumer.

## 10. Ghi nhớ

- **Tài liệu kiến trúc** trả lời “Hệ thống *được tổ chức* ra sao, những ràng buộc và quan hệ nào tồn tại trong mô hình?”.
- **Bằng chứng runtime** trả lời “Trong lần chạy *đã quan sát*, điều gì thực sự xảy ra, với kết quả và độ trễ nào?”.
- **Bằng chứng tốt cần ghi phạm vi:** cùng build, môi trường, khoảng thời gian, kịch bản, sampling và instrumentation.
- **Kết luận vững chắc cần ghép nhiều nguồn:** `Documenter`/`verify()` cho cấu trúc; Actuator cho mô hình trên deploy; metrics, tracing, registry và kiểm tra dữ liệu cho hành vi.

## Tài liệu tham khảo

1. [Spring Modulith – Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html).
2. [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html).
3. [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html).
4. [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html).
5. [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
6. [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
7. [Spring Framework – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html).

