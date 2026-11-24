# Đối chiếu API, thuộc tính cấu hình và thay đổi hành vi mặc định

## 1. Nâng cấp thành công không có nghĩa hành vi còn giống trước

Giả sử một ứng dụng Spring Cloud Function có bean phân loại đơn hàng:

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> new OrderClassified(
            order.orderId(),
            order.totalInCents() >= 100_000L
                    ? "PRIORITY" : "STANDARD");
}
```

Trước khi nâng cấp, ứng dụng nhận JSON qua HTTP hoặc Kafka, chuyển dữ liệu thành `OrderCreated`, gọi `classifyOrder` rồi gửi kết quả. Sau khi nâng thư viện, ứng dụng vẫn **biên dịch** và thậm chí **khởi động thành công**, nhưng có thể thay đổi cách chọn bean mặc định, tên binding, kiểu payload được chuyển đổi, thời điểm poll, retry hoặc cách xử lý thông điệp lỗi.

Như vậy, kiểm tra nâng cấp không chỉ là hỏi “API cũ còn compile không?”, mà phải đối chiếu ba mặt:

1. **API:** lớp, interface, method, annotation, generic type và hợp đồng invocation có giữ được tính tương thích không?
2. **Cấu hình:** tên property, namespace, kiểu giá trị, phạm vi áp dụng, thứ tự ưu tiên và thuộc tính không còn được binder hỗ trợ có thay đổi không?
3. **Hành vi mặc định:** khi không khai báo property, ứng dụng thực sự chọn function nào, đọc destination/group nào, serialize payload ra sao, retry mấy lần và xử lý lỗi thế nào?

Bài thuộc chương **Nâng cấp** của module **SPRING_CLOUD_FUNCTION**. Trọng tâm là giữ các `Supplier`, `Function`, `Consumer` và `FunctionCatalog` có thể tái sử dụng trên HTTP, Spring Cloud Stream hoặc serverless, trong khi những adapter, phụ thuộc và cấu hình bên ngoài được nâng một cách có kiểm soát.

**Kết quả mong đợi:** bạn sẽ biết cách lập bảng đối chiếu trước–sau, tránh gán nhầm một thay đổi do cấu hình triển khai thành “breaking change của Function”, viết regression tests bằng payload thật và có kế hoạch khôi phục khi hành vi runtime không còn đáp ứng hợp đồng.

## 2. Xác định chính xác cặp phiên bản trước khi đối chiếu

Mọi câu nói “trước đây mặc định là X, bây giờ là Y” đều phải có **điểm đầu, điểm cuối và bối cảnh**. Một thay đổi trong Spring Cloud Function 5.1 có thể khác thay đổi của Boot 4 hoặc binder Kafka. Không dùng tài liệu phiên bản hiện tại để kết luận về hành vi của một ứng dụng đang ở dòng 3.x.

Ví dụ đối chiếu thế hệ tại **24/11/2026**:

| Trục | Baseline giả định | Mục tiêu minh họa | Nguồn kiểm chứng |
| --- | --- | --- | --- |
| Spring Boot | 3.5.x | 4.2.0 | Boot migration guide và system requirements |
| Spring Cloud BOM | 2025.0.x | 2026.0.0 | Ma trận Spring Cloud/Boot, release train notes |
| Spring Cloud Function | 4.3.x | 5.1.0 | Release notes của Function và dependency graph |
| Spring Cloud Stream | Dòng do BOM 2025.0.x quản lý | 5.1.0 | Release notes Stream và binder |
| Java target/runtime | Giá trị của ứng dụng hiện tại | Giá trị được chọn và kiểm thử | Build tool, image/serverless runtime |
| HTTP/Kafka/Rabbit/AWS adapter | Dependency cụ thể | Bản do BOM quản lý | Tài liệu adapter và integration test |

Spring Cloud **2026.0.0** phát hành ngày **20/11/2026**, dựa trên Boot **4.2.0**, gồm Function **5.1.0** và Stream **5.1.0**. Đây là **mốc minh họa có nguồn**, không phải tuyên bố rằng mọi ứng dụng buộc phải chuyển ngay sang các phiên bản đó.

Nguồn: [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/) và [Spring Cloud release compatibility](https://spring.io/projects/spring-cloud/).

### Đừng đánh đồng bốn loại thay đổi

| Loại | Ví dụ | Cách phát hiện |
| --- | --- | --- |
| **Source compatibility** | Method/annotation bị bỏ hoặc đổi signature | Compiler errors, API docs |
| **Binary compatibility** | `NoSuchMethodError` do module lệch version | Dependency graph và startup/integration tests |
| **Configuration compatibility** | Property không còn bind hoặc đổi namespace | Metadata, startup logs, thực nghiệm config |
| **Behavioral compatibility** | Không chọn đúng function, retry khác, message vào group khác | Contract/golden tests và observability |

Một API được đánh dấu **deprecated** chưa chắc đã bị xóa trong release hiện tại. Ngược lại, một property vẫn được chấp nhận về cú pháp chưa chắc đang có tác dụng ở adapter/binder đó.

## 3. Tạo bảng đối chiếu ba cột trước khi sửa bất kỳ thứ gì

Bắt đầu bằng bảng có ba câu hỏi bắt buộc: **cũ đang làm gì?**, **mới được tài liệu ghi nhận là gì?**, **bài kiểm thử nào chứng minh hành vi cần giữ?**

| Thành phần | Trạng thái baseline cần thu thập | Tiêu chí sau nâng cấp |
| --- | --- | --- |
| Function bean | Tên bean và generic signature | Catalog tìm được chính xác bean |
| Definition | Giá trị `spring.cloud.function.definition` ở runtime | Đúng hàm/composition; không phụ thuộc fallback tình cờ |
| HTTP endpoint | Path, method, content type, status và headers | Contract không đổi ngoài thay đổi đã được phê duyệt |
| Stream bindings | Tên input/output, alias | Binding tồn tại và nối đúng destination |
| Kafka/Rabbit | Group, offset/queue, codec | Không mất/đọc trùng ngoài dự tính, schema đúng |
| Source/Supplier | Tần suất poll, số message trên mỗi lần poll | Không phát thừa hoặc bỏ sót |
| Error path | `maxAttempts`, backoff, DLQ/DLT | Lỗi transient và permanent có tuyến phục hồi đúng |
| Reactive | Khi nào subscribe, `onError`, ordering | Một lỗi không gây dừng luồng trái hợp đồng |
| Serverless | Handler, env vars, runtime, event shape | Invoke thành công với sự kiện production mẫu |
| Security | Input routing, SpEL, payload size, deserialization | Không tạo đường thực thi/hạ tải nguy hiểm mới |

**Quy tắc bằng chứng:** đánh dấu mỗi nhận định là một trong các trạng thái:

- **CONFIRMED:** release notes hoặc API docs nêu rõ thay đổi ở đúng version.
- **OBSERVED:** đã quan sát bằng test trên baseline/mục tiêu.
- **ASSUMPTION:** chưa có bằng chứng, phải xác minh trước triển khai.

Không viết một “migration cheat sheet” đoán các property đổi tên chỉ vì một lệnh cũ không chạy. Cần phân biệt **property sai**, **property đúng nhưng gắn nhầm binding**, và **property đúng nhưng adapter không sử dụng**.

## 4. Kiểm kê API trước nâng cấp: đừng chỉ grep tên phiên bản

Với dự án sử dụng Spring Cloud Function, kiểm kê ít nhất:

- Các bean `Supplier<T>`, `Function<I,O>`, `Consumer<T>` và tên bean đã được công bố.
- Mọi nơi gọi `FunctionCatalog.lookup(...)` hoặc tương tác trực tiếp với `FunctionInvocationWrapper`.
- Composition, routing, `MessageRoutingCallback` và custom converters.
- `Message<T>`, generic type, headers, reactive `Flux`/`Mono`.
- `@PollableBean`, `StreamBridge`, `PollableMessageSource` và custom binding APIs.
- Adapter HTTP, Stream Kafka/Rabbit và AWS Lambda nếu hiện diện.
- Module/annotation legacy hoặc thư viện đã **deprecated**.
- Các SDK, auto-configuration hoặc bytecode transformation dựa vào API nội bộ.

### Những lệnh chỉ dùng để kiểm kê, không phải kết luận

```bash
# Maven: lấy phiên bản đã resolve và nguồn kéo dependency
mvn help:effective-pom
mvn dependency:tree

# Gradle: xem runtimeClasspath và nguyên nhân chọn phiên bản
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency spring-cloud-function-context

# Xác định JDK/build tool
java -version
mvn -version
./gradlew --version
```

Đây là **lệnh tham khảo cho môi trường của học viên**. Kết quả dependency graph phải lấy từ đúng artifact sẽ đóng gói lên production, không chỉ một module test. Không cần chạy các lệnh trên để hiểu bài học.

## 5. FunctionCatalog và bean Java: hai đường invocation khác nhau

Xét:

```java
@Bean
Function<String, String> normalize() {
    return String::trim;
}
```

Có hai cách lấy hàm:

```java
// Bean gốc do Spring ApplicationContext quản lý.
Function<String, String> original =
        applicationContext.getBean("normalize", Function.class);

// Hàm được lookup qua Spring Cloud Function.
Function<?, ?> fromCatalog = catalog.lookup("normalize");
```

**Không nên khẳng định hai object hoàn toàn giống nhau.** Tài liệu Spring Cloud Function mô tả hàm được tra qua `FunctionCatalog` có thể được **wrapped/instrumented**, bổ sung các đặc tính như chuẩn hóa lời gọi, composition và type conversion. Lấy bean gốc trực tiếp không bảo đảm đi qua chính các wrapper đó.

### 5.1. API đúng nhưng kiểu trả về có thể làm code test sai

Một đoạn code migration nguy hiểm:

```java
// Dễ quá tự tin vào kiểu runtime khi có wrapper/conversion.
@SuppressWarnings("unchecked")
Function<String, String> fn =
        (Function<String, String>) catalog.lookup("normalize");
```

Việc generic cast trong Java bị type erasure; nó không chứng minh payload thực tế lúc runtime là `String`. Nếu lookup trả wrapper xử lý `Message<?>`, hoặc adapter cung cấp dữ liệu với content type khác, cần kiểm thử đúng đường invocation và loại đối tượng.

Hãy chọn test theo **hợp đồng cần bảo vệ**:

1. Test trực tiếp bean `normalize` để chứng minh nghiệp vụ `" x " → "x"`.
2. Test lookup qua `FunctionCatalog` để chứng minh tên và invocation.
3. Test adapter HTTP hoặc Stream để chứng minh message conversion và headers.

### 5.2. Test trực tiếp logic trước

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class NormalizeBusinessTest {

    @Test
    void trimsText() {
        Function<String, String> fn = String::trim;
        assertEquals("ORD-101", fn.apply(" ORD-101 "));
    }
}
```

Đây là test nghiệp vụ thuần, không phụ thuộc Boot hoặc broker. Nó không thay thế integration test của `FunctionCatalog` sau nâng cấp.

## 6. Definition và hành vi tự phát hiện bean: nên explicit hóa

Tài liệu Spring Cloud Function mô tả **single-function fallback**: khi catalog chỉ có một functional bean đủ điều kiện, việc lookup không chỉ định tên có thể vẫn tìm được hàm đó. Với Spring Cloud Stream, một ứng dụng chỉ có một functional bean có thể được tự động bind.

Đây là hành vi **có điều kiện**, không phải hợp đồng tốt để phụ thuộc dài hạn.

Ví dụ ứng dụng ban đầu chỉ có:

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
```

Sau nâng cấp, một starter hoặc bean khác tình cờ đăng ký thêm functional bean. Khi đó “chỉ có một function” không còn đúng. Ứng dụng có thể không chọn được definition hoặc chọn sai cách tích hợp.

**Cấu hình phòng ngừa:**

```yaml
spring:
  cloud:
    function:
      definition: uppercase
```

Nếu ứng dụng yêu cầu lookup **chính xác theo tên**, Spring Cloud Function có property:

```yaml
spring:
  cloud:
    function:
      single-function-fallback-enabled: false
```

Không nên coi property này là một thay đổi mặc định của 5.1; đây là **công cụ cấu hình** để khóa behavior mà ứng dụng mong muốn. Phải test lại với version đang dùng.

### 6.1. Filtering các bean không muốn đăng ký

Spring Cloud Function có thể phát hiện các bean chức năng mà ứng dụng không định công bố. Tài liệu hỗ trợ:

```properties
spring.cloud.function.ineligible-definitions=internalNormalizer,debugFunction
```

Dùng khi có lý do thực sự, nhưng tốt hơn vẫn là **đặt `definition` tường minh**. Mỗi khi thay dependency/starter, audit danh sách bean trong `FunctionCatalog` để tránh vô tình mở một hàm chỉ phục vụ nội bộ ra adapter HTTP hoặc FaaS.

### 6.2. Bảng kiểm trước–sau

| Cần đối chiếu | Trước nâng | Sau nâng |
| --- | --- | --- |
| Tổng số bean `Supplier/Function/Consumer` | Ghi chính xác | Ghi lại; xác minh không có bean lạ |
| `spring.cloud.function.definition` | Có/không, giá trị | Explicit, cùng mục tiêu nghiệp vụ |
| Fallback một function | Có dựa vào không? | Quyết định khóa hoặc giữ có test |
| Bean eligibility | Những bean nào lọt catalog? | Không công bố bean nội bộ trái ý định |
| Lookup name | `catalog.lookup(...)` tên nào? | Tên ổn định, không bị trùng |

## 7. Composition, nhiều definition và contract của tên binding

Hai dấu quan trọng:

- `|` ghép nhiều hàm thành **một pipeline**.
- `;` chọn **nhiều definition độc lập** để Spring Cloud Stream bind chúng riêng.

```yaml
# Một pipeline: normalize chạy trước classify.
spring.cloud.function.definition: normalize|classify
```

```yaml
# Hai definition riêng; không có thứ tự xử lý liên-binder.
spring.cloud.function.definition: classify;audit
```

Một lỗi nâng cấp thực tế thường **không phải API đổi** mà là property bị rơi mất trong profile mới. Khi đó ứng dụng chuyển từ explicit pipeline thành chế độ autodiscovery; kết quả wiring có thể khác.

### 7.1. Chữ ký Function quyết định số binding

| Definition | Input binding | Output binding |
| --- | --- | --- |
| `uppercase` | `uppercase-in-0` | `uppercase-out-0` |
| `normalize|classify` | `normalize|classify-in-0` | `normalize|classify-out-0` |
| `audit` là `Consumer<T>` | `audit-in-0` | Không có output mặc định |
| `supply` là `Supplier<T>` | Không có input mặc định | `supply-out-0` |
| `classify;audit` | Mỗi definition có `-in-0` riêng | Chỉ definition trả kết quả mới có output |

Tên `-in-0`/`-out-0` là tên cổng logic, **không phải** broker destination. Nếu đổi tên bean, tên implicit binding cũng đổi; khi không cấu hình destination tường minh, message có thể trôi sang destination mặc định theo tên binding mới.

### 7.2. Alias không đổi semantics của function

```yaml
spring:
  cloud:
    function:
      definition: normalize|classify
    stream:
      function:
        bindings:
          "normalize|classify-in-0": ordersInput
          "normalize|classify-out-0": ordersOutput
      bindings:
        ordersInput:
          destination: orders.created
          group: classify-workers
        ordersOutput:
          destination: orders.classified
```

Sau khi alias, **các property của binding thực** nằm dưới `ordersInput`/`ordersOutput`. Migration sai thường giữ `spring.cloud.stream.bindings.normalize|classify-in-0.destination` trong một profile cũ và đưa alias vào profile mới, khiến cấu hình phân tán.

**Không suy luận** rằng Spring Cloud Function đã thay cơ chế naming trong một version cụ thể nếu chưa đọc release notes. Kiểm tra log binding và destination runtime là bằng chứng quan trọng hơn.

## 8. Đối chiếu routing API và thuộc tính routing

`RoutingFunction` là một phần của Spring Cloud Function, có tên catalog điển hình `functionRouter`. Nó có thể chọn hàm đích bằng property, message header hoặc `MessageRoutingCallback` tùy tình huống.

### 8.1. Các điểm cần giữ ổn định

| Cơ chế | Dấu hiệu cấu hình/API | Ý nghĩa kiểm thử |
| --- | --- | --- |
| Static definition | `spring.cloud.function.definition=classifyOrder` | Chọn hàm đích cố định |
| Routing function | `spring.cloud.function.definition=functionRouter` | Kích hoạt hàm routing khi dùng adapter thích hợp |
| Routing expression | `spring.cloud.function.routing-expression` | Quy tắc xác định hàm đích |
| Header routing | Header `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` | Chỉ phù hợp khi adapter hỗ trợ và message là đơn vị xử lý |
| Callback | Bean `MessageRoutingCallback` | Có thể quyết định route ưu tiên hơn header/property |
| Unroutable handling | `DefaultMessageRoutingHandler` | Quyết định lỗi hoặc fallback khi không có route |

Theo tài liệu Spring Cloud Function, độ ưu tiên của routing trong mô hình imperative gồm **callback → header → application property**. Nếu callback được thêm sau nâng cấp, cùng message có thể đi sang hàm khác dù property trong YAML không đổi.

**Lưu ý reactive:** Với `Function<Flux<T>, Flux<R>>`, routing theo header của **từng message** không có cùng semantics như imperative. Khi routing toàn stream, dùng application property/cơ chế phù hợp; không mặc định message header được đánh giá cho mỗi phần tử.

### 8.2. Vấn đề bảo mật không thể bỏ qua

Routing expressions có thể dùng SpEL. Khi cho phép caller bên ngoài ảnh hưởng header hoặc property routing, phải kiểm soát input và quyền truy cập. Dù Spring Cloud Function có áp dụng cơ chế evaluation hạn chế cho expression đến từ message headers, **không nên** coi đó là quyền công khai mọi bean hoặc mọi expression cho người dùng.

Khuyến nghị:

- Chỉ cho phép những function definitions đã được phê duyệt.
- Không tin tên function do HTTP caller tự gửi nếu route quyết định side effect nhạy cảm.
- Không công khai các cấu hình Actuator/mutation endpoints ngoài ý định.
- Sau nâng cấp, kiểm thử payload/header bất thường, biểu thức lỗi, route không tồn tại và quyền truy cập.
- Theo dõi các security advisories và ưu tiên patch phát hành.

Trong thông báo **2026.0.0**, Spring Cloud Function công bố các sửa lỗi bảo mật liên quan giới hạn JSON collection và class loading. Vì vậy, regression tests nên bao gồm kích thước payload, độ sâu/kiểu dữ liệu và input từ nguồn không tin cậy, không chỉ happy-path.

## 9. HTTP adapter: cùng Function nhưng endpoint contract phải được chụp lại

`spring-cloud-function-web` có thể công bố hàm thông qua HTTP khi dependency và web stack phù hợp được cung cấp. Nhưng một bean `Function<T,R>` **không tự chứng minh** đường dẫn HTTP, status code hoặc body encoding giữ nguyên giữa hai lần nâng cấp.

Ví dụ đơn giản:

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
```

Khi adapter web được cấu hình phù hợp, request gửi payload `"hello"` có thể được chuyển vào function. Đường dẫn cụ thể, HTTP method và content conversion cần xác minh **trên đúng adapter version và cấu hình ứng dụng**.

### Checklist HTTP contract

| Hạng mục | Baseline cần lưu | Sau nâng cấp |
| --- | --- | --- |
| URL và method | Path, verb | Không thay ngoài ý định |
| Request headers | `Content-Type`, `Accept`, correlation | Converter nhận đúng |
| Response | Status, headers, JSON/text body | Downstream không bị phá contract |
| Lỗi validation | HTTP status và error body | Không đột ngột trả 500 cho input sai |
| Routing | Headers, callback, expression | Không mở route ngoài quyền |
| Security | Authentication/authorization, CORS | Không giảm bảo vệ |
| Resource limits | Payload max size, timeout | Không tạo đường tải lớn nguy hiểm |

### Ví dụ kiểm thử ở mức HTTP

```bash
# Chỉ là ví dụ khi adapter đang cung cấp endpoint /uppercase.
curl -i -X POST http://localhost:8080/uppercase \
  -H "Content-Type: text/plain" \
  --data "hello"
```

Test phải xác nhận **nội dung, status và headers** trên baseline trước, rồi chạy lại sau nâng cấp. Đừng viết test chỉ gọi `uppercase.apply("hello")` rồi xem như đã kiểm tra HTTP adapter.

## 10. Cấu hình Spring Cloud Stream: property nào thuộc lớp nào?

Một lesson quan trọng là phân biệt namespace:

| Namespace | Đối tượng cấu hình | Ví dụ |
| --- | --- | --- |
| `spring.cloud.function.*` | Function selection, routing, catalog-related config | `spring.cloud.function.definition` |
| `spring.cloud.stream.bindings.<binding>.*` | Common binding config | `destination`, `group`, `content-type` |
| `spring.cloud.stream.bindings.<binding>.consumer.*` | Common consumer | `maxAttempts`, `concurrency`, `useNativeDecoding` |
| `spring.cloud.stream.bindings.<binding>.producer.*` | Common producer | `useNativeEncoding`, partition settings |
| `spring.cloud.stream.function.bindings.*` | Alias implicit binding name | `uppercase-in-0: inputName` |
| `spring.cloud.stream.kafka.bindings.<binding>.*` | Kafka binder-specific config | `consumer.enableDlq`, `consumer.ackMode` |
| `spring.cloud.stream.rabbit.bindings.<binding>.*` | Rabbit binder-specific config | `consumer.autoBindDlq` |
| `spring.integration.poller.*` | Default polling settings | `fixed-delay`, `max-messages-per-poll` |

**Ví dụ sai vị trí property:**

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          # Đừng đặt Kafka-specific enableDlq ở đây:
          # consumer:
          #   enableDlq: true
```

**Ví dụ đúng namespace Kafka:**

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: process-workers
          consumer:
            maxAttempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.errors
```

`maxAttempts` thuộc common consumer, trong khi `enableDlq` là thuộc tính riêng của Kafka binder. Một property xuất hiện ở YAML mà không có binding tương ứng **không có nghĩa** runtime đã áp dụng nó.

## 11. Điểm kiểm tra nguy hiểm: destination, group và offset mặc định

Spring Cloud Stream định nghĩa một số hành vi mặc định hữu ích nhưng dễ gây bất ngờ:

- Nếu không chỉ định `destination`, tên binding logic có thể được dùng làm destination.
- Nếu không chỉ định `group`, một consumer thường thuộc **anonymous group** theo cơ chế binder.
- `contentType` mặc định chung được tài liệu Spring Cloud Stream ghi nhận là `application/json`; điều đó vẫn phải kết hợp với wire format và native codec nếu có.

### 11.1. Đổi tên bean có thể khiến consumer đọc sai topic

Ban đầu:

```java
@Bean
Consumer<OrderCreated> auditOrder() { /* ... */ }
```

```yaml
spring:
  cloud:
    function:
      definition: auditOrder
    stream:
      bindings:
        auditOrder-in-0:
          destination: orders.created
          group: audit-workers
```

Nếu đổi bean thành `recordOrder` nhưng không đổi `definition` và binding, wiring sẽ sai. Nếu bỏ `destination` và để framework sử dụng tên binding làm mặc định, ứng dụng có thể đọc một destination khác mà không làm hỏng code Java.

**Khuyến nghị:** trong môi trường có broker, khai báo `definition`, `destination` và `group` rõ ràng cho mỗi consumer cần định danh/tiến độ ổn định.

### 11.2. Consumer group không chỉ là tên

Với Kafka, group quyết định tiến độ offset; với RabbitMQ, group thường quyết định queue nhận. Nếu đổi group trong quá trình nâng cấp:

- Kafka có thể áp dụng offset chưa tồn tại của group mới; chế độ startOffset, retention và topic partition cần kiểm tra.
- RabbitMQ có thể tạo queue group mới, topology và backlog khác queue cũ.
- Một nghiệp vụ vô tình có hai group có thể khiến **hai nhóm cùng thực hiện side effect**, tạo duplicate logic.

Vì vậy thay `group` là **thay đổi vận hành/data semantics**, không phải chỉ là đổi tên cho đẹp.

### 11.3. Không biến hành vi tài liệu thành lời hứa tuyệt đối

Trong Kafka binder, quy tắc `startOffset` cho group có tên và anonymous group được tài liệu mô tả, nhưng hành vi thực tế còn phụ thuộc **offset đã commit, resetOffsets, retention và config Kafka client**. Trước khi phát hành, dùng môi trường tích hợp để chứng minh một group mới sẽ đọc lại lịch sử hay chỉ nhận record mới như thiết kế.

## 12. API/conversion: POJO, Message<T>, headers và native codec

Ba chữ ký thường gặp:

```java
Function<OrderCreated, OrderClassified>

Function<Message<OrderCreated>, Message<OrderClassified>>

Function<Flux<OrderCreated>, Flux<OrderClassified>>
```

Chúng khác nhau về contract:

| Signature | Điều cần test khi nâng cấp |
| --- | --- |
| `Function<T,R>` | JSON/bytes → `T`, rule nghiệp vụ, `R` → output wire format |
| `Function<Message<T>,Message<R>>` | Tất cả điều trên + headers/correlation/type |
| `Function<Flux<T>,Flux<R>>` | Lifecycle reactive, subscription, onError, backpressure và các message liên tiếp |

### 12.1. Content-type không thay thế schema

```yaml
spring:
  cloud:
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          content-type: application/json
        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

Đây là **thông tin định dạng**; Java generic type và converter quyết định khả năng tạo đối tượng cụ thể. Nếu `OrderCreated` đổi tên field hoặc loại dữ liệu, payload JSON cũ có thể bị parse sai dù `content-type` không đổi.

Bài test nên dùng payload thật từ production (đã ẩn dữ liệu nhạy cảm), gồm trường thiếu, `null`, số lớn, Unicode, content type không mong đợi và header lạ.

### 12.2. Native conversion là một đường khác

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            useNativeDecoding: true
        processOrder-out-0:
          producer:
            useNativeEncoding: true
```

Khi dùng native decoding/encoding của binder, Kafka serializer/deserializer hoặc codec tương ứng cần được cấu hình đúng. `content-type: application/json` **không tự thay thế** một Kafka `StringDeserializer`/`JsonDeserializer` không tương thích.

**Phân biệt lỗi:**

- Deserializer native lỗi **trước** khi gọi function.
- Framework type conversion lỗi ở ranh giới message → Java.
- Business rule lỗi **trong** function.
- Output serializer lỗi **sau** khi function trả kết quả.

Retry/DLQ cần thiết kế đúng đường phát sinh lỗi; một `try/catch` trong function không bắt được mọi lỗi conversion.

### 12.3. Header mapping không giống nhau giữa các adapter

`Message<OrderCreated>` có thể chứa `correlationId`, nhưng Kafka headers, Rabbit message properties, HTTP headers và Lambda event metadata không tương đương 1:1. Sau nâng cấp:

1. Test input header đi vào bean dưới kiểu dữ liệu nào.
2. Test output chỉ chuyển tiếp headers cần thiết.
3. Kiểm tra `contentType` đầu ra khi payload đổi kiểu.
4. Không copy headers vận chuyển cũ một cách mù quáng.

## 13. Polling Supplier và dữ liệu theo lô: mặc định dễ tạo sự cố

Trong Spring Cloud Stream, một `Supplier<T>` imperative thường được poll bằng cơ chế mặc định với **`fixedDelay = 1000 ms`** và **`maxMessagesPerPoll = 1`** theo tài liệu hiện hành. Hãy ghi các giá trị thực tế của baseline; không suy ra chúng từ nhịp ghi log trên local machine.

```java
@Bean
Supplier<String> heartbeat() {
    return () -> "alive";
}
```

Nếu source luôn trả `"alive"`, nó có thể tiếp tục phát vô hạn. Thay đổi packaging, Bean registration hoặc deployment replicas có thể tăng số producer mà không cần thay đổi code này.

### 13.1. Khóa nhịp poll bằng cấu hình rõ ràng

```yaml
spring:
  integration:
    poller:
      fixed-delay: 5000
      max-messages-per-poll: 1
```

Hoặc poller riêng theo output binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        heartbeat-out-0:
          destination: system.heartbeat
          producer:
            poller:
              fixed-delay: 5000
              max-messages-per-poll: 1
```

`fixed-delay` được tính theo mili giây trong cấu hình mặc định. Kiểm thử runtime vẫn cần xét thời gian thực hiện và scheduling; config 5 giây không có nghĩa broker nhận record vào đúng các mốc 5 giây tuyệt đối.

### 13.2. Reactive supplier không giống imperative supplier

`Supplier<Flux<T>>` thông thường cung cấp Publisher, thường được lấy/subscribe một lần để phát theo vòng đời luồng. Với nguồn reactive **hữu hạn cần poll định kỳ**, dùng `@PollableBean`:

```java
import java.util.function.Supplier;
import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

@PollableBean(splittable = true)
public Supplier<Flux<String>> batchSource() {
    return () -> Flux.just("A", "B", "C");
}
```

Annotation `@PollableBean` đánh dấu nguồn có thể poll; `splittable=true` cho phép framework tách các phần tử để phát message riêng. Mặc định `splittable` được tài liệu mô tả là `true`; nếu đổi `false`, contract output có thể khác rõ rệt. Một `Supplier<List<T>>` và `Supplier<Flux<T>>` không có nghĩa giống nhau.

**Đặc biệt:** `maxMessagesPerPoll=1` không tự cắt một `Flux` sau phần tử đầu tiên. Khi nâng cấp, cần test **số lần poll** và **số message đầu ra** riêng biệt.

## 14. Imperative và reactive: mặc định lỗi/retry không tương đương

Đối chiếu:

```java
// Một invocation theo message ở mô hình imperative.
Function<OrderCreated, OrderClassified> classify

// Thiết lập một pipeline gồm nhiều phần tử.
Function<Flux<OrderCreated>, Flux<OrderClassified>> classifyReactive
```

Với imperative handler, framework/binder có thể quan sát exception mỗi message và áp dụng `consumer.maxAttempts`/error handler tương ứng. Với reactive function, hàm thường được gọi để **thiết lập Flux**, còn lỗi phát ra sau đó bằng `onError`; không mặc định retry/DLQ của imperative hoạt động giống hệt ở từng phần tử.

### 14.1. Regression test phải kiểm tra luồng sau lỗi

Ví dụ nguy hiểm:

```java
@Bean
Function<Flux<OrderCreated>, Flux<OrderClassified>> classifyReactive() {
    return orders -> orders.map(order -> {
        if (order.orderId() == null) {
            throw new IllegalArgumentException("Missing orderId");
        }
        return new OrderClassified(order.orderId(), "STANDARD");
    });
}
```

Nếu một phần tử sai làm stream phát `onError` và kết thúc, các message hợp lệ sau đó có thể không được xử lý như mong muốn. Test:

- Message hợp lệ trước message lỗi.
- Message lỗi với `orderId=null`.
- Message hợp lệ **sau** lỗi.
- Restart/resubscribe, retry và deduplication.
- Broker acknowledgement/offset nếu pipeline tương tác Stream binder.

Không dùng `retryWhen` trên toàn Publisher một cách vô điều kiện: resubscribe có thể chạy lại các side effect trước đó.

### 14.2. Mối liên hệ với nâng cấp 2026.0.0

Thông báo release train **2026.0.0** đề cập việc **deprecated reactive Kafka binder**. Điều này **không** có nghĩa mọi `Function<Flux<T>,Flux<R>>` bị loại bỏ. Phải phân biệt:

- **Reactive programming model** của Spring Cloud Function/Reactor.
- **Reactive Kafka binder artifact** thuộc Spring Cloud Stream.
- **Conventional Kafka binder** kết nối một functional bean reactive.

Thấy chữ “reactive” giống nhau không đủ để suy luận hai API có cùng lifecycle hay cùng lộ trình thay thế.

## 15. Retry, error handler và DLQ: chú ý defaults theo từng binder

Spring Cloud Stream có common consumer retry properties:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processors
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000
```

Tài liệu Binding Properties ghi `maxAttempts` mặc định là **3**, **bao gồm lần đầu**. Đặt `1` để tắt retry mechanism đó. Đây là thông tin mặc định **cần đối chiếu với version cụ thể và loại handler**, không có nghĩa đã bật DLQ.

### 15.1. Kafka DLQ là binder-specific

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.errors
```

Kafka DLT là topic riêng. Nếu không khai báo group, cơ chế Kafka binder DLQ có giới hạn đối với anonymous consumer. Producer serializer cho DLT phải phù hợp payload và native mode.

### 15.2. RabbitMQ DLQ khác Kafka DLT

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

RabbitMQ có exchange/queue, ack/nack/requeue và DLX. Không chuyển nguyên config Kafka sang Rabbit binder; tính tương đương cần được **kiểm thử**, không chỉ mapping tên property.

### 15.3. Custom error handler thay đổi tuyến recovery

Spring Cloud Stream hỗ trợ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          error-handler-definition: recordError
```

Trong tài liệu error handling, **custom ErrorMessage handler** được mô tả là loại trừ với các error handler mặc định/binder-specific. Khi bật nó, không nên mặc định DLQ vẫn chạy dù có `enableDlq`. Đây là ví dụ **thay đổi hành vi vì cấu hình**, không phải bằng chứng một bản nâng cấp đột ngột xóa DLQ.

**Bảng test tối thiểu:**

| Trường hợp | Kỳ vọng cần chứng minh |
| --- | --- |
| Message hợp lệ | Xử lý thành công, tiến độ commit/ack phù hợp |
| Lỗi transient | Retry và backoff có giới hạn |
| Lỗi permanent | Không retry vô hạn; recovery/quarantine đúng |
| Error handler tùy chỉnh | Không bỏ mất message vì handler nuốt exception |
| DLT/DLQ không ghi được | Có alert và đường recovery rõ |
| Crash sau DB commit trước ack | Không tạo side effect trùng |

## 16. Những thay đổi được thông báo trong release train 2026.0.0

Đây là phần cần phân biệt **sự kiện phát hành đã xác nhận** với **hành vi cần kiểm thử**.

Theo [Spring Cloud 2026.0.0 release announcement ngày 20/11/2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/):

| Lĩnh vực | Điều đã được công bố | Ảnh hưởng tới kế hoạch nâng cấp |
| --- | --- | --- |
| Spring Cloud Function | **Deprecated RSocket module** | Kiểm kê nếu đang dùng Function RSocket; lập kế hoạch thay thế, không coi đã bị xóa ngay |
| Spring Cloud Function | **Deprecated gRPC module** | Kiểm kê adapters và test gRPC nếu ứng dụng đang sử dụng |
| Spring Cloud Stream | **Deprecated reactive Kafka binder** | Tách rõ binder artifact khỏi việc sử dụng `Flux` trong function |
| Spring Cloud Stream | **Deprecated Schema Registry component** | Kiểm tra schema/serialization ecosystem và lộ trình hỗ trợ |
| Spring Cloud Bus | Được tích hợp vào Spring Cloud Stream; **artifact coordinates giữ nguyên** | Kiểm tra dependency resolution; không tự đổi toàn bộ tọa độ |
| Spring Cloud Function | Bản sửa bảo mật giới hạn JSON Collection và kiểm soát class loading | Test input không tin cậy và payload limits |
| Spring Cloud Stream | Bản sửa bảo mật về deserialization subpackage | Audit deserialization trust rules và security patches |

**Deprecated ≠ removed.** Đừng xóa dependency hoặc đổi endpoint chỉ vì release notes dùng từ deprecated. Hãy xem artifact đó còn hoạt động không, thời hạn hỗ trợ, hướng chuyển được khuyến nghị, phạm vi tính năng đang dùng và thời gian có thể chuyển đổi.

Ngược lại, **security fix** có thể thay đổi điều kiện chấp nhận dữ liệu từ nguồn không tin cậy. Một regression test thất bại vì payload vượt giới hạn mới không nhất thiết là lỗi cần “tắt bảo vệ”; cần điều chỉnh contract và kiểm soát kích thước/tính hợp lệ.

### Ma trận tác động thực tế

| Ứng dụng đang dùng | Việc cần làm |
| --- | --- |
| Chỉ `Function<String,String>` qua HTTP | Tập trung FunctionCatalog/web adapter, input/route security |
| `Function<T,R>` qua Kafka binder thông thường | Tập trung binding, conversion, offset/group, DLT |
| `Function<Flux<T>,Flux<R>>` qua Kafka binder | Test reactive lifecycle và binder riêng; đừng tự suy nó bị deprecated |
| Reactive Kafka binder artifact riêng | Review deprecation và lộ trình hỗ trợ/thay thế |
| gRPC/RSocket adapters của Function | Review deprecation đúng module |
| Schema Registry của Stream | Xác minh schema compatibility và lộ trình component |
| Spring Cloud Bus | Kiểm tra classpath/release train, dù coordinates hiện chưa đổi |

## 17. API legacy: không nhầm “khuyến nghị” với “bị xóa”

Spring Cloud Stream từng dùng các annotation/channel interfaces cho message handlers và `@StreamListener`. Từ Stream 3.x, tài liệu khuyến nghị **functional programming model** với `Supplier`, `Function`, `Consumer`. Tuy nhiên, việc một mô hình được khuyến nghị **không đủ chứng minh** mô hình cũ đã bị xóa trong mọi phiên bản hiện tại.

Lộ trình chuyển đổi hợp lý khi dự án legacy đang dùng annotation-based source/sink:

1. Ghi lại input/output destination, group, content type và native codec.
2. Xác định handler tương đương `Function<I,O>`, `Consumer<T>` hoặc `Supplier<T>`.
3. Tách business logic khỏi annotation và broker API.
4. Thay implicit/explicit channel names bằng `<function>-in-0` / `-out-0` hoặc alias có chủ đích.
5. So sánh message schema, headers, retry, group, offset/requeue.
6. Chỉ xóa legacy binding code sau khi integration tests đạt trên binder thật.

**Không coi** việc dùng `@Bean Function` là bảo đảm 100% tương đương với handler legacy về thread affinity, concurrency, headers hoặc acknowledgement. Những thông số này nằm ngoài business function.

## 18. Property migration: tạo bảng mapping, không đổi hàng loạt theo cảm giác

Hãy lập bảng từ **tài liệu baseline** và **tài liệu target**, kèm giá trị runtime quan sát được.

| Mục tiêu nghiệp vụ | Key/property hiện hành cần tìm | Cần kiểm chứng |
| --- | --- | --- |
| Chọn hàm | `spring.cloud.function.definition` | Tên bean, số definition, composition |
| Điều kiện routing | `spring.cloud.function.routing-expression` | Ưu tiên callback/header/property, security |
| Alias binding | `spring.cloud.stream.function.bindings.*` | Mapping implicit → explicit |
| Destination | `spring.cloud.stream.bindings.*.destination` | Topic/exchange thật |
| Consumer group | `spring.cloud.stream.bindings.*.group` | Offset/queue identity |
| Content type | `spring.cloud.stream.bindings.*.content-type` | Converter/codec và header |
| Input concurrency | `spring.cloud.stream.bindings.*.consumer.concurrency` | Ordering, scale và broker |
| Retry count | `spring.cloud.stream.bindings.*.consumer.maxAttempts` | Tổng attempts (gồm lần đầu) |
| Kafka DLT | `spring.cloud.stream.kafka.bindings.*.consumer.enableDlq` | Group, DLT, serializer |
| Rabbit DLQ | `spring.cloud.stream.rabbit.bindings.*.consumer.autoBindDlq` | DLX/queue topology |
| Poller mặc định | `spring.integration.poller.fixed-delay` | Nhịp Supplier |
| Poller riêng | `spring.cloud.stream.bindings.*.producer.poller.fixed-delay` | Đúng output binding |
| Native codec | `consumer.useNativeDecoding` / `producer.useNativeEncoding` | Serializer/deserializer phù hợp |

**Bảng là danh mục đối chiếu, không phải tuyên bố các key này đã được đổi tên trong 2026.0.0.** Nhiều key vẫn được tài liệu hiện hành dùng. Một migration đúng sẽ chỉ ghi “RENAME” nếu tài liệu hoặc metadata xác nhận property thực sự đổi; còn lại đánh dấu “RETAIN”, “SEMANTIC REVIEW”, “DEPRECATED” hoặc “REMOVED”.

### Bảng bằng chứng mẫu

| Property | Baseline | Target | Phân loại | Bằng chứng |
| --- | --- | --- | --- | --- |
| `spring.cloud.function.definition` | `classifyOrder` | `classifyOrder` | RETAIN | Startup + function lookup test |
| `processOrder-in-0.consumer.maxAttempts` | 3 | 3 | RETAIN / VERIFY | Binding metadata và retry test |
| `consumer.group` | `audit-workers` | `audit-workers` | RETAIN, quan trọng cho data | Kafka offset/Rabbit queue test |
| Một key tự đặt trong project | Chưa rõ | Chưa rõ | UNKNOWN | Tìm metadata, owner và logs |

Không đưa những ví dụ giả định chưa được xác minh vào danh sách “breaking changes đã xảy ra”.

## 19. Tạo một ví dụ Java có thể dùng làm regression fixture

Bộ fixture dưới đây giữ business logic thuần Java, đồng thời có một nhánh cần header để kiểm thử adapter:

```java
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
public class UpgradeFixtureApplication {

    public static void main(String[] args) {
        SpringApplication.run(UpgradeFixtureApplication.class, args);
    }

    public record OrderCreated(
            String eventId,
            String orderId,
            long totalInCents) {}

    public record OrderClassified(
            String eventId,
            String orderId,
            String priority) {}

    @Bean
    Function<OrderCreated, OrderClassified> classifyOrder() {
        return order -> {
            if (order.orderId() == null || order.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId required");
            }

            return new OrderClassified(
                    order.eventId(),
                    order.orderId(),
                    order.totalInCents() >= 100_000L
                            ? "PRIORITY" : "STANDARD");
        };
    }

    @Bean
    Function<Message<OrderCreated>,
             Message<OrderClassified>> classifyWithHeaders() {

        return input -> {
            OrderCreated order = input.getPayload();

            var output = new OrderClassified(
                    order.eventId(),
                    order.orderId(),
                    order.totalInCents() >= 100_000L
                            ? "PRIORITY" : "STANDARD");

            var builder = MessageBuilder.withPayload(output)
                    .setHeader("processedBy", "upgrade-fixture");

            Object correlationId =
                    input.getHeaders().get("correlationId");

            if (correlationId != null) {
                builder.setHeader("correlationId", correlationId);
            }

            return builder.build();
        };
    }

    @Bean
    Consumer<OrderClassified> auditOrder() {
        return value -> System.out.printf(
                "AUDIT %s %s %s%n",
                value.eventId(),
                value.orderId(),
                value.priority());
    }
}
```

**Lưu ý:** để test một pipeline, hãy chọn **definition cụ thể**. Không tự để cả ba bean cùng được bind mà chưa có lý do, vì `classifyOrder` và `classifyWithHeaders` cùng có thể đọc một destination nhưng xử lý khác nhau.

### Fixture payload

```json
{
  "eventId": "evt-101",
  "orderId": "ORD-101",
  "totalInCents": 150000
}
```

Output expected:

```json
{
  "eventId": "evt-101",
  "orderId": "ORD-101",
  "priority": "PRIORITY"
}
```

Giữ các event mẫu như contract fixtures; không đổi chúng cùng lúc với dependency để test có ý nghĩa so sánh.

## 20. Cấu hình Stream mẫu để đối chiếu trước–sau

Ví dụ chọn **một function** nhận POJO và phát POJO:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder

    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: classify-workers
          content-type: application/json
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000

        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

YAML này không tự chọn Kafka hay RabbitMQ khi dự án có nhiều binder chưa được cấu hình; dependency và kết nối binder phải được xác định. Trong test có broker, nên cấp port/URL/credential bằng test environment, không hard-code secret vào bài học.

### Khi muốn kiểm thử nhiều definition độc lập

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder;auditOrder

    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: classify-workers
          content-type: application/json

        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json

        auditOrder-in-0:
          destination: orders.classified
          group: audit-workers
          content-type: application/json
```

`;` chọn hai definition độc lập; `auditOrder` chỉ nhận output của `classifyOrder` **vì cùng destination**. Nếu đổi tên `orders.classified` ở một trong hai binding, chúng không tự nối nhau.

### Khi muốn kiểm thử một pipeline composition

Giả sử có hai bean `normalizeOrder` và `classifyOrder` tương thích kiểu:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|classifyOrder
    stream:
      bindings:
        "normalizeOrder|classifyOrder-in-0":
          destination: orders.created
          group: classify-workers
          content-type: application/json
        "normalizeOrder|classifyOrder-out-0":
          destination: orders.classified
          content-type: application/json
```

Đây là **cấu hình thay thế**, cần có bean `normalizeOrder` trả `OrderCreated` để chạy. Không gộp ba cấu hình mẫu vào một profile và kỳ vọng chúng là ba giai đoạn nối tiếp.

## 21. Kiểm thử API và hành vi theo tầng

### 21.1. Unit test nghiệp vụ

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class BusinessContractTest {

    @Test
    void mapsPriorityTheSameWay() {
        var app = new UpgradeFixtureApplication();
        var function = app.classifyOrder();

        var output = function.apply(
                new UpgradeFixtureApplication.OrderCreated(
                        "evt-101", "ORD-101", 150_000L));

        assertEquals("PRIORITY", output.priority());
        assertEquals("ORD-101", output.orderId());
    }

    @Test
    void rejectsInvalidOrder() {
        var app = new UpgradeFixtureApplication();
        var function = app.classifyOrder();

        assertThrows(IllegalArgumentException.class, () ->
                function.apply(
                        new UpgradeFixtureApplication.OrderCreated(
                                "evt-102", " ", 10L)));
    }
}
```

Các test này chạy với business bean và **không kiểm tra adapter**. Giữ chúng để biết khi nào lỗi bắt đầu từ nghiệp vụ chứ không phải migration framework.

### 21.2. Test headers

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

class MessageContractTest {

    @Test
    void keepsCorrelationId() {
        var app = new UpgradeFixtureApplication();
        var function = app.classifyWithHeaders();

        var request = MessageBuilder.withPayload(
                new UpgradeFixtureApplication.OrderCreated(
                        "evt-101", "ORD-101", 150_000L))
                .setHeader("correlationId", "trace-789")
                .build();

        var response = function.apply(request);

        assertEquals("trace-789",
                response.getHeaders().get("correlationId"));
        assertEquals("upgrade-fixture",
                response.getHeaders().get("processedBy"));
        assertEquals("PRIORITY",
                response.getPayload().priority());
    }
}
```

Sau khi test Java thành công, integration test phải xác nhận headers vẫn đi qua HTTP/Kafka/Rabbit/AWS như contract. Không coi một `MessageBuilder` unit test là bằng chứng về binder header mapping.

### 21.3. FunctionCatalog integration test

Với application context thực, test:

- Catalog có đúng function names cần công bố.
- `catalog.lookup("classifyOrder")` tìm được function.
- Composition `normalizeOrder|classifyOrder` được lookup đúng nếu có đủ bean.
- Khi cấu hình `single-function-fallback-enabled=false`, lookup tên sai không âm thầm chọn bean duy nhất.
- Không có bean debug hoặc internal function bị công bố ngoài ý định.

Có thể dùng `@SpringBootTest` hoặc test Spring context thích hợp. Vì catalog có thể trả wrapper, xác minh bằng dữ liệu/contract thực tế; đừng bắt buộc wrapper và bean gốc có cùng class.

### 21.4. Stream test binder và broker thật

Test binder của Spring Cloud Stream giúp kiểm tra selection, binding naming và conversion framework. Sau đó phải kiểm tra Kafka/RabbitMQ thật hoặc Testcontainers cho:

- Topic/queue và group identity.
- Payload bytes, content type và headers.
- Retry, backoff, DLQ/DLT khi handler ném lỗi.
- Redelivery sau restart và idempotency.
- Native serializer/deserializer.
- Offset/ack và thứ tự theo partition/concurrency.

**Contract test nên độc lập version**: cùng fixture, cùng expected semantics, cùng test suite chạy trên baseline và target. Khi kết quả khác, phân loại thay đổi trước khi sửa test.

## 22. Golden tests: so sánh trước–sau có thể lặp lại

Một golden test lưu **đầu vào cố định** và **đầu ra/hành vi được phê duyệt**, không chỉ snapshot toàn bộ log thay đổi theo timestamp.

| Test | Input | Quan sát cần lưu | Rủi ro được phát hiện |
| --- | --- | --- | --- |
| Lookup | Bean name `classifyOrder` | Catalog resolves đúng tên | Fallback/eligibility khác |
| HTTP | JSON `evt-101` | Status, body, headers | Routing/conversion đổi |
| Kafka | Record JSON + key/header | Output schema, partition behavior | Native codec/group đổi |
| RabbitMQ | AMQP message mẫu | Queue nhận, DLQ khi lỗi | Topology/ack đổi |
| Supplier | 2 chu kỳ poll | Số lần gọi và số message | Nhịp poll/splitting khác |
| Reactive | 2 hợp lệ + 1 lỗi + 1 hợp lệ | Stream còn sống hay dừng | `onError` làm mất luồng |
| Routing | Header hợp lệ, header lạ | Route đúng hoặc reject | Chọn nhầm function/security |
| Retry | Exception tạm thời 2 lần rồi thành công | Tổng attempts/backoff | Retry khác kỳ vọng |
| DLQ | Poison message | Payload lỗi còn được cách ly | Silent drop |
| Serverless | Event source thực tế | Handler, output, error shape | Adapter/runtime khác |

### Đặt ngưỡng và điều kiện đạt

- **Định tính:** destination, function name, schema, group và error route phải **đúng tuyệt đối**.
- **Định lượng:** latency, throughput, startup time có thể cho phép dao động theo ngưỡng được phê duyệt.
- **Bảo mật:** các input bị từ chối do giới hạn bảo mật mới phải được phân tích; không tự sửa test để chấp nhận dữ liệu nguy hiểm.
- **Determinism:** không so sánh thứ tự giữa hai Kafka partitions hoặc hai consumer groups khi kiến trúc không có bảo đảm ordering liên nhóm.

Golden tests cần dữ liệu đã ẩn thông tin nhạy cảm và nên lưu cùng phiên bản schema và expected contract.

## 23. Giám sát cấu hình thực tế: property có “bind” chưa?

Một property có mặt trong file YAML **không đủ** để kết luận framework đã sử dụng.

Các lý do thường gặp:

- Đang chạy profile khác file vừa sửa.
- Biến môi trường override giá trị trong `application.yml`.
- Binder name khác tên cấu hình (`kafka` so với một binder instance tự đặt tên).
- Binding được alias nhưng property vẫn gắn dưới tên implicit.
- Property thuộc consumer nhưng lại đặt dưới producer.
- Property nằm trong namespace của binder không có trên classpath.
- Property đã deprecated/removed và không còn được binder sử dụng.
- Artifact trong container là build cũ.

### Cách xác minh

1. Xem effective build dependencies.
2. Quan sát startup logs của FunctionCatalog, binding và binder.
3. Kiểm tra actuator configuration/bindings khi dự án có bật và **bảo vệ quyền truy cập**.
4. Dùng integration test gửi message tới **đúng destination**.
5. Quan sát topic/queue thực tế, consumer group/queue depth và DLQ.
6. Gắn test cho những property quan trọng thay vì chỉ assert file YAML chứa một dòng.

`/actuator/env`, `/actuator/configprops` hoặc management endpoints có thể để lộ thông tin nhạy cảm. Không công khai chúng ra Internet hoặc đưa credential nguyên vẹn vào log kiểm thử.

### Bảng kiểm nguồn cấu hình

```text
application.yml
    ↓
application-<profile>.yml
    ↓
environment variables / command-line args / config server
    ↓
Spring Environment (effective value)
    ↓
configuration binding to target object
    ↓
Function/Stream/binder runtime behavior
```

Sơ đồ chỉ là cách nhìn tổng quát; thứ tự ưu tiên chính xác của từng property source do Spring Boot quản lý và có thể có thêm nguồn như config server, test properties, system properties. Đừng dùng sơ đồ để thay bảng thứ tự chính thức của phiên bản Boot mục tiêu.

## 24. Đối chiếu môi trường AWS Lambda và serverless

Một function được tái sử dụng trên serverless có thêm lớp cần kiểm tra: **adapter handler**, **runtime Java**, **event source** và **cách truyền environment variables**.

Ví dụ Spring Cloud Function AWS adapter có handler thường gặp:

```text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
```

Một property Spring có dấu chấm có thể được ánh xạ sang environment variable theo cơ chế Spring Boot. Tài liệu AWS adapter đưa ví dụ:

```text
spring.cloud.function.definition
    -> spring_cloud_function_definition
```

Cần test giá trị thật mà runtime nhận. Không suy rằng mọi dấu gạch ngang, dấu chấm hoặc camelCase trong mọi tên property đều được platform/Boot diễn giải giống nhau trong mọi điều kiện.

### Kịch bản kiểm thử FaaS

- Một function duy nhất, chọn bằng env var tường minh.
- Nhiều function beans, có definition hoặc routing theo chính sách.
- Event JSON hoặc event từ SQS/Kinesis/API Gateway đúng schema.
- Lỗi parse/validation và retry/partial batch failure của event source.
- Timeout, cold start, memory và lựa chọn Java runtime.
- Secrets/permissions và log masking.
- Artifact layout/handler class sau khi nâng dependency adapter.

**Không áp quy tắc Kafka retry và DLT sang AWS Lambda chỉ vì cùng dùng `Function<T,R>`**. Cơ chế ack/retry của SQS/Kinesis/API Gateway do platform và integration event source quyết định.

## 25. Checklist quyết định triển khai, canary và rollback

### Trước nâng cấp

- [ ] Xác định phiên bản baseline/mục tiêu: Boot, Cloud BOM, Function, Stream, binder, Java runtime.
- [ ] Lưu kết quả dependency graph và artifact/image digest hiện tại.
- [ ] Ghi tất cả function names, composition, routing và message schemas.
- [ ] Ghi explicit `definition`, destination, group và nhịp Supplier.
- [ ] Ghi retry/DLQ, content type, native codec, header mapping và default assumptions.
- [ ] Xem release notes chính thức, deprecation và security advisories.
- [ ] Có dữ liệu test đại diện cho payload hợp lệ, lỗi và trường hợp biên.

### Trên staging

- [ ] Unit tests và FunctionCatalog lookup/composition tests đạt.
- [ ] HTTP/Stream/Lambda adapter contract tests đạt theo phạm vi sử dụng.
- [ ] Không có property vô hiệu hoặc binding nối sai destination.
- [ ] Retry/DLQ/ack và redelivery được kiểm thử với broker thật.
- [ ] Reactive stream chạy tiếp hoặc dừng đúng chính sách đã thiết kế.
- [ ] Khả năng backward/forward schema compatibility được xác nhận.
- [ ] Resource usage, startup latency và error rate trong ngưỡng.
- [ ] Các thay đổi security được giữ lại, không bị vô hiệu hóa để “qua test”.

### Khi phát hành

- [ ] Rollout canary theo từng nhóm và quan sát tỷ lệ lỗi, lag, queue depth, DLT/DLQ.
- [ ] Có ngưỡng tự động hoặc người trực canary có quyền dừng rollout.
- [ ] Có khả năng phục hồi artifact cũ bằng digest, không phụ thuộc tag trôi.
- [ ] Rollback không phá schema DB/event đã phát trong giai đoạn canary.
- [ ] Không để hai version consumer dùng **group khác nhau** ngoài chủ đích.
- [ ] Có phương án xử lý những message đã được target version phát trong thời gian thử.

### Cách phân loại kết quả

| Kết quả test | Hành động |
| --- | --- |
| API không compile | Xác định method/annotation bị thay và migration path |
| API compile nhưng contract khác | So sánh property/adapter và quyết định chấp nhận hay sửa |
| Lỗi property bị bỏ qua | Xác nhận namespace, key và metadata target |
| Behavior thay vì security fix | Không tự vô hiệu hóa bảo vệ; điều chỉnh contract |
| Error path khác và gây mất dữ liệu | Dừng rollout, sửa recovery và kiểm thử lại |
| Chỉ hiệu năng thay đổi | Đo ngưỡng, xem tuning, không che lỗi chức năng |
| Tất cả quality gates đạt | Canary có giám sát, rồi tăng tỷ lệ rollout |

Rollback một JAR hoặc image **không thể thu hồi** message đã phát hoặc migration dữ liệu đã áp dụng. Nếu cả producer và consumer đều đang chuyển phiên bản, phải bảo đảm event schema tương thích trong giai đoạn chạy song song.

## 26. Bài tập thực hành

### Bài tập 1: Phân loại một thay đổi

Bạn đổi tên bean `classifyOrder` thành `classify` nhưng giữ lại:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
```

Vì sao ứng dụng có thể không bind được hoặc bind sai? Đây có phải bằng chứng Spring Cloud Function đã đổi quy tắc tên binding không? Hãy đề xuất cách sửa và bài test.

### Bài tập 2: Một function trở thành hai function

Trước nâng cấp ứng dụng có duy nhất bean `uppercase` và không khai báo `definition`. Sau khi thêm `reverse`, application không chọn được bean như mong muốn. Hãy phân tích nguyên nhân, viết cấu hình tường minh và giải thích `single-function-fallback-enabled: false` giúp ích trong trường hợp nào.

### Bài tập 3: Phát hiện cấu hình DLQ sai tầng

Cho:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          consumer:
            enableDlq: true
```

Nếu đang dùng Kafka binder, hãy sửa namespace cho `enableDlq` và bổ sung `group`. Vì sao một property sai vị trí có thể đi qua build mà production vẫn không có DLT?

### Bài tập 4: Đối chiếu routing

Ứng dụng có `MessageRoutingCallback`, application property `routing-expression` và message header chỉ function đích khác. Hãy xác định thứ tự ưu tiên theo tài liệu Spring Cloud Function, rồi đề xuất test cho imperative và reactive model. Vì sao không nên cho untrusted caller tùy ý chọn hàm nội bộ?

### Bài tập 5: Baseline và target không khớp về Supplier

Trước nâng, một source phát một message mỗi 5 giây. Sau nâng, nó phát mỗi 1 giây. Hãy liệt kê nguyên nhân có thể từ cấu hình `fixed-delay`, active profile, number of replicas, Supplier type và `@PollableBean` trước khi kết luận framework đã đổi default.

### Bài tập 6: Chuyển sang native Kafka decoding

Một `Function<OrderCreated,OrderClassified>` đang nhận JSON qua converter. Sau thay đổi `useNativeDecoding: true`, consumer nhận `byte[]` hoặc `String` thay vì DTO. Hãy nêu những component cần kiểm tra và vì sao `content-type: application/json` có thể không đủ.

### Bài tập 7: Đánh giá release train 2026.0.0

Ứng dụng đang dùng `Function<Flux<T>,Flux<R>>` cùng Kafka binder thông thường và một module gRPC của Spring Cloud Function. Trong release 2026.0.0, phần nào bị thông báo deprecated? Vì sao không được suy rằng reactive Function API đã bị loại bỏ? Hãy viết migration inventory cho hai phần.

### Bài tập 8: Viết golden test

Chọn một nghiệp vụ xử lý đơn hàng qua HTTP hoặc Kafka, tự định nghĩa:

- Input event JSON và headers.
- Expected output schema, status/destination.
- Error case và recovery path.
- Default assumptions cần khóa bằng config.
- Cách chạy cùng bộ test với hai artifact baseline và target.

### Bài tập 9: Tình huống rollback

Một canary đã phát event có field mới mà version consumer cũ không hiểu. Nếu rollback producer và Function ngay lập tức, điều gì xảy ra với event đã có trong broker? Hãy thiết kế schema evolution và rollback plan trước khi triển khai.

### Câu hỏi tự đánh giá

1. API compatibility và behavioral compatibility khác nhau như thế nào?
2. `FunctionCatalog.lookup(...)` có luôn trả về bean gốc không?
3. Vì sao nên khai báo `spring.cloud.function.definition` ngay cả khi app chỉ có một function?
4. Dấu `|` và `;` có tạo topology giống nhau không?
5. Alias binding làm thay đổi thứ tự input/output của function không?
6. Khi đổi consumer group, Kafka offset/RabbitMQ queue có thể bị ảnh hưởng thế nào?
7. `content-type` có tự thay thế Kafka native serializer/deserializer không?
8. `maxAttempts` có tính lần gọi đầu tiên không?
9. Vì sao custom error handler có thể làm DLT không còn chạy như dự kiến?
10. Reactive Kafka binder deprecation có đồng nghĩa `Flux` function deprecation không?
11. Deprecated có đồng nghĩa removed không?
12. Làm sao chứng minh property trong YAML thật sự có hiệu lực?
13. Chạy unit test function thành công đã đủ chứng minh HTTP/Lambda adapter chưa?
14. Vì sao một security fix có thể thay đổi hành vi chấp nhận payload?
15. Khi nào cần dừng rollout và rollback, và rollback còn phụ thuộc event schema thế nào?

## 27. Tổng kết

Nâng cấp Spring Cloud Function phải là một **bài toán đối chiếu hợp đồng**, không đơn thuần là thay phiên bản dependency:

- **API:** kiểm tra functional bean, `FunctionCatalog`, wrapper invocation, composition, routing và adapters.
- **Cấu hình:** kiểm tra đúng namespace `spring.cloud.function.*`, `spring.cloud.stream.bindings.*`, Kafka/Rabbit binder properties, aliases, poller, content type và native codec.
- **Hành vi mặc định:** kiểm tra fallback một function, destination/group, Supplier polling, retry, DLQ, reactive `onError` và security limits bằng test trên đúng version.
- **Release notes:** phân biệt confirmed changes, deprecations và giả định chưa có bằng chứng; với Spring Cloud **2026.0.0**, cần chú ý các deprecation Function gRPC/RSocket, Stream reactive Kafka binder/Schema Registry và những bản sửa bảo mật đã công bố.
- **Kiểm thử:** dùng cùng bộ golden/contract tests trên baseline và target, rồi kiểm chứng broker, HTTP và serverless runtime thực tế.
- **Triển khai:** rollout theo giai đoạn, quan sát, có ngưỡng rollback và kế hoạch tương thích schema/event đang lưu.

Giữ các `Supplier`, `Function`, `Consumer` thuần nghiệp vụ giúp logic được tái sử dụng qua HTTP, sự kiện hoặc serverless. Nhưng **mỗi adapter có hợp đồng vận hành riêng**; vì vậy đánh giá “không đổi hành vi” chỉ đáng tin khi có bằng chứng ở đúng ranh giới của adapter và hệ thống.

### Tài liệu tham khảo

- [Spring Cloud 2026.0.0 — Release announcement ngày 20/11/2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud — Release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud Function — Programming model, FunctionCatalog, composition, routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Reference Documentation](https://docs.spring.io/spring-cloud-function/reference/)
- [Spring Cloud Function — AWS adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — Kafka Binder configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder reference](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
