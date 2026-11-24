# Đối chiếu tài liệu cũ với thế hệ dịch vụ đám mây hiện hành

## 1. Vì sao tài liệu cũ vẫn đúng nhưng không còn là hướng dẫn phù hợp cho dự án mới?

Một đội phát triển đang bảo trì ứng dụng Spring Cloud Stream từ nhiều năm trước. Code có các annotation như `@EnableBinding`, `@Input`, `@Output` và `@StreamListener`; một interface `Processor` định nghĩa kênh vào/ra; test dùng `MessageCollector`. Tài liệu đi kèm ứng dụng được viết cho một release train cũ và vẫn giải thích chính xác cách hệ thống đó hoạt động.

Khi nâng Spring Boot và Spring Cloud, đội phát triển tìm một bài hướng dẫn mới. Họ thấy ví dụ dùng `@Bean Function<T,R>`, `spring.cloud.function.definition`, binding name dạng `processOrder-in-0` và `InputDestination`/`OutputDestination`. Nhóm kết luận tài liệu cũ đã sai và xóa toàn bộ code. Nhưng cách làm đó có thể bỏ sót những chi tiết quan trọng như destination, consumer group, header, retry, binder và schema.

**Tài liệu cũ không tự động sai chỉ vì đã cũ.** Nó có thể là tài liệu chính xác cho phiên bản mà hệ thống đó đang chạy. Vấn đề xảy ra khi lấy ví dụ của một thế hệ framework, ghép với dependency của thế hệ khác rồi kỳ vọng chúng có cùng API, cấu hình và hành vi.

Bài thuộc chương **Nâng cấp** của module **SPRING_CLOUD_FUNCTION**. Module tập trung phát triển logic nghiệp vụ tái sử dụng bằng `Supplier`, `Function`, `Consumer`, `FunctionCatalog`, composition và message conversion, độc lập với giao thức gọi. Vì vậy, khi đối chiếu tài liệu, cần phân biệt phần nào là **hợp đồng nghiệp vụ ổn định**, phần nào là **API của framework**, và phần nào thuộc **adapter/binder/runtime**.

Sau bài này, bạn sẽ biết cách xác định đúng phiên bản tài liệu, đọc release train và ma trận tương thích, nhận diện mô hình annotation cũ, chuyển sang functional model, kiểm tra cấu hình/binding/error handling/test binder, và lập kế hoạch nâng cấp dựa trên bằng chứng thay vì copy ví dụ mới nhất một cách máy móc.

## 2. Bốn câu hỏi phải trả lời trước khi đọc một trang tài liệu

Khi gặp một ví dụ Spring Cloud Function hoặc Spring Cloud Stream, đừng bắt đầu bằng việc copy code. Hãy xác định:

1. **Trang tài liệu thuộc phiên bản nào?** Ví dụ 3.2.10, 5.0.x, 5.1.0 hay một bản SNAPSHOT?
2. **Release train và Spring Boot nào quản lý dependency?** Phiên bản module riêng lẻ không thay thế ma trận tương thích.
3. **Ví dụ đang dùng programming model nào?** Annotation/channel model, functional bean, Spring Integration hay reactive function?
4. **Ví dụ nói về lớp nào?** Business function, FunctionCatalog, Stream binder, HTTP/serverless adapter hay cloud provider runtime?

Một ví dụ có thể đúng về cú pháp nhưng sai với dự án hiện tại nếu khác một trong bốn yếu tố này.

### 2.1. Nhận diện version trên URL và banner

| Dấu hiệu | Cách hiểu | Cách dùng |
| --- | --- | --- |
| `/docs/3.2.10/reference/...` | Tài liệu gắn với phiên bản cụ thể | Dùng để hiểu hành vi baseline 3.2.10 |
| `/reference/5.0/...` | Tài liệu cho nhánh 5.0 | Chọn khi dependency target thuộc nhánh này |
| `/reference/` không có version | Thường là tài liệu mặc định/phiên bản hiện hành do site điều hướng | Kiểm tra banner, release và version hiển thị |
| `5.1-SNAPSHOT` hoặc `5.1.0-M1` | Bản phát triển/milestone | Không coi là tài liệu phát hành GA nếu dự án dùng GA |
| Blog phát hành | Tóm tắt thay đổi của một release | Dùng để phát hiện điểm cần đọc sâu trong reference/release notes |
| Javadoc | Chữ ký API và trạng thái deprecated theo artifact | Dùng để xác minh một class/method cụ thể |

**Không chỉ nhìn số version trong tiêu đề.** Một trang SNAPSHOT có thể chứa nội dung mới hơn bản GA nhưng vẫn thay đổi trước khi phát hành. Ngược lại, một trang reference mặc định có thể điều hướng đến nhánh ổn định khác với module mới nhất trong release train vừa công bố.

### 2.2. Một nguyên tắc quan trọng về nguồn

Ưu tiên nguồn theo thứ tự:

1. Release train compatibility matrix và release notes đúng version.
2. Reference documentation đúng version của module.
3. Javadoc/API docs của artifact đã resolve.
4. Migration guide và issue/changelog chính thức.
5. Blog kỹ thuật hoặc bài viết cộng đồng.
6. Q&A, snippet trên diễn đàn và ví dụ không ghi version.

Nguồn cấp thấp vẫn hữu ích để tìm manh mối, nhưng không nên là bằng chứng duy nhất cho quyết định migration.

## 3. Thế hệ phiên bản hiện hành tại thời điểm đối chiếu

Tại ngày **24/11/2026**, Spring Cloud **2026.0.0** đã được công bố GA ngày **20/11/2026**. Release train này dựa trên Spring Boot **4.2.0**; trang reference của release train liệt kê Spring Cloud Function **5.1.0** và Spring Cloud Stream **5.1.0**.

| Thành phần | Mốc hiện hành dùng trong bài | Vai trò |
| --- | --- | --- |
| Spring Boot | 4.2.0 | Nền tảng ứng dụng và auto-configuration |
| Spring Cloud release train | 2026.0.0 | Bộ phiên bản tương thích của các dự án Spring Cloud |
| Spring Cloud Function | 5.1.0 | Functional model, FunctionCatalog, conversion và adapters |
| Spring Cloud Stream | 5.1.0 | Binding, binder, messaging và test binder |
| Java runtime | Chọn theo Boot, adapter và cloud provider | JVM thực thi ứng dụng |
| Kafka/Rabbit binder | Artifact do release train quản lý | Kết nối middleware cụ thể |

Đây là **mốc tham chiếu tại thời điểm biên soạn**, không phải khuyến nghị mọi hệ thống phải nâng ngay. Nếu ứng dụng đang ở một release train còn được hỗ trợ, hãy chọn đúng nhánh tương thích thay vì nâng riêng từng module lên version cao nhất.

Nguồn chính thức:
- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Train Reference — 2026.0.0](https://docs.spring.io/spring-cloud-release/reference/index.html)

### 3.1. Release train version khác module version

`2026.0.0` là version của **release train**. `5.1.0` là version của từng project như Function và Stream. Spring Boot `4.2.0` là version của nền tảng Boot. Ba số này không thể thay thế nhau.

Một Maven BOM minh họa:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2026.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-context</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream</artifactId>
    </dependency>
</dependencies>
```

Ví dụ Gradle dùng platform:

```kotlin
dependencies {
    implementation(
        platform("org.springframework.cloud:spring-cloud-dependencies:2026.0.0")
    )
    implementation("org.springframework.cloud:spring-cloud-function-context")
    implementation("org.springframework.cloud:spring-cloud-stream")
}
```

Không đặt version riêng cho từng module nếu BOM đã quản lý, trừ khi có lý do và đã kiểm tra tương thích. Việc override một module có thể làm Function context, Stream binder, adapter và các dependency Spring khác lệch nhau.

### 3.2. Đọc dependency đã resolve, không chỉ đọc POM

```bash
# Maven
./mvnw help:effective-pom
./mvnw dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-cloud-function-context

java -version
./mvnw -version
./gradlew --version
```

Các lệnh này là hướng dẫn cho dự án của bạn; kết quả cần được lấy từ đúng module/artifact sẽ deploy. Một version trong parent POM không chứng minh đó là version thực sự nằm trong JAR cuối cùng.

## 4. Lịch sử chuyển dịch: từ channel/annotation sang functional model

Spring Cloud Stream bắt đầu với mô hình message channel và annotation. Người dùng định nghĩa interface có `@Input`/`@Output`, bật binding bằng `@EnableBinding` và xử lý message bằng `@StreamListener` hoặc Spring Integration annotations.

Spring Cloud Function đưa các Java functional interface `Supplier`, `Function` và `Consumer` thành programming model có thể dùng qua nhiều execution context. Spring Cloud Stream tích hợp functional model từ **2.1**. Tài liệu Stream **3.x** khuyến nghị functional implementations và đánh dấu native annotation-based model như `@EnableBinding`/`@StreamListener` deprecated.

| Giai đoạn | Dấu hiệu tài liệu/code | Ý nghĩa khi đọc |
| --- | --- | --- |
| Stream 1.x/2.0 và tài liệu cũ hơn | `@EnableBinding`, `@Input`, `@Output`, `@StreamListener` | Channel/annotation model là ví dụ phổ biến |
| Stream 2.1 | Tích hợp functional beans từ Spring Cloud Function | Có thể bắt đầu dùng `Supplier`/`Function`/`Consumer` |
| Stream 3.x | Functional model được khuyến nghị; native annotation model deprecated | Lập kế hoạch migration thay vì mở rộng code legacy |
| Stream 3.x trở đi | Reactive support chuyển sang native Reactor support của Function; module `spring-cloud-stream-reactive` ngừng phân phối | Dùng `Flux`/`Mono` trong functional signatures |
| Stream 3.x | Test support binder cũ/`MessageCollector` được thay thế dần bằng Integration Test Binder | Chuyển test sang `InputDestination`/`OutputDestination` |
| Stream 5.1.0 trong train 2026.0.0 | Functional model và binder tiếp tục được quản lý theo release train mới | Dùng reference đúng version, không copy cấu hình từ tài liệu 2.x |

**Cẩn thận:** “deprecated” không đồng nghĩa “đã bị xóa trong mọi phiên bản”. Tài liệu Stream 3.2.10 ghi rõ annotation model deprecated, trong khi reference hiện hành vẫn có thể mô tả một số cấu hình annotation/Integration như legacy hoặc lựa chọn tương thích. Hãy xác minh API thực sự có trong artifact target trước khi lập kế hoạch xóa.

### 4.1. Ba trạng thái không được gộp

- **Deprecated:** không nên tiếp tục dùng cho code mới; có thể vẫn chạy.
- **Discontinued/not distributed:** module không còn được phát hành theo cách cũ; có thể có cơ chế thay thế.
- **Removed:** API/artifact không còn trong version target.

Một dòng release notes nói “deprecated” không đủ để khẳng định artifact đã biến mất. Một dependency không còn được phân phối cũng không nhất thiết có cùng migration path với một annotation deprecated.

## 5. Đối chiếu mô hình cũ: @EnableBinding và @StreamListener

Một ví dụ legacy thường gặp:

```java
@EnableBinding(Processor.class)
public class LegacyOrderHandler {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public OrderClassified classify(OrderCreated order) {
        return new OrderClassified(
                order.orderId(),
                order.totalInCents() >= 100_000L
                        ? "PRIORITY" : "STANDARD");
    }
}
```

Ví dụ minh họa sử dụng interface `Processor` của mô hình cũ. Nó thể hiện ba ý:

1. `@EnableBinding` kích hoạt binding interfaces.
2. `Processor.INPUT` và `Processor.OUTPUT` là tên channel tường minh.
3. `@StreamListener` gắn method với input channel; `@SendTo` chỉ output channel.

Khi đọc tài liệu cũ, đừng bỏ qua phần cấu hình destination/group, content type, retry và binder. Chúng vẫn là thông tin vận hành cần được chuyển sang cấu hình mới.

### 5.1. Functional model tương ứng

Code hiện đại:

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> new OrderClassified(
            order.orderId(),
            order.totalInCents() >= 100_000L
                    ? "PRIORITY" : "STANDARD");
}
```

Cấu hình:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: order-classifiers
          content-type: application/json
        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

| Mô hình cũ | Functional model | Cần bảo toàn |
| --- | --- | --- |
| `@EnableBinding(Processor.class)` | Functional bean + Stream auto-configuration | Binder và topology |
| `Processor.INPUT` | `classifyOrder-in-0` | Input destination/group |
| `Processor.OUTPUT` | `classifyOrder-out-0` | Output destination |
| `@StreamListener` method | `Function<I,O>` | Nghiệp vụ, validation và exception semantics |
| `@SendTo` | Return value của Function | Output mapping |
| Interface channel names | Binding convention/alias | Tên cấu hình và profile |

Đây là ánh xạ về **ý tưởng**, không phải thay tên annotation một cách cơ học. Những chức năng phụ của handler cũ như header mapping, partitioning, conditional dispatch hoặc method overload phải được chuyển riêng và kiểm thử.

## 6. Source/Sink cũ và Supplier/Consumer hiện tại

Trong tài liệu Stream cũ, ứng dụng nguồn và ứng dụng nhận thường dùng các interface `Source` và `Sink`, cùng channel constants.

Mẫu cũ:

```java
@EnableBinding(Source.class)
public class LegacyOrderSource {

    @Bean
    @InboundChannelAdapter(
        value = Source.OUTPUT,
        poller = @Poller(fixedDelay = "1000"))
    public MessageSource<String> source() {
        return () -> new GenericMessage<>("order-created");
    }
}
```

Functional model thường dùng `Supplier<T>`:

```java
@Bean
Supplier<String> orderSource() {
    return () -> "order-created";
}
```

Cấu hình Stream:

```yaml
spring:
  cloud:
    function:
      definition: orderSource
    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
```

Consumer cũ có thể dùng channel listener; mô hình mới:

```java
@Bean
Consumer<OrderCreated> auditOrder() {
    return order -> auditService.record(order);
}
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

**Không tự động thay poller.** Với `Supplier`, phải xác định nó imperative hay reactive, tần suất poll, số message mỗi poll, source có hữu hạn hay vô hạn và số replica. Supplier trả `Flux<T>` có lifecycle khác Supplier trả một phần tử; nguồn reactive hữu hạn cần kiểm tra cơ chế poll, ví dụ marker `@PollableBean` ở các trường hợp phù hợp.

## 7. Functional model: FunctionCatalog là điểm chuẩn hóa invocation

Spring Cloud Function đăng ký các bean `Supplier`, `Function`, `Consumer` đủ điều kiện vào `FunctionCatalog`. Lookup qua catalog trả về function đã được framework instrument/wrap để hỗ trợ các tính năng như type conversion và composition.

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Autowired
FunctionCatalog catalog;

void invoke() {
    Function<?, ?> function = catalog.lookup("uppercase");
}
```

Lấy bean trực tiếp từ `ApplicationContext` không nhất thiết tương đương với lookup qua `FunctionCatalog`, vì bean gốc không được bảo đảm có cùng wrapper/conversion behavior.

### 7.1. Definition là cấu hình tích hợp

```yaml
spring:
  cloud:
    function:
      definition: uppercase
```

Nếu chỉ có một function, framework có thể tìm được nó qua fallback khi không chỉ định tên. Tuy nhiên, tài liệu khuyến nghị khai báo `spring.cloud.function.definition` trong tích hợp với framework khác như Spring Cloud Stream.

Khi muốn lookup chỉ đúng tên:

```yaml
spring:
  cloud:
    function:
      definition: uppercase
      single-function-fallback-enabled: false
```

Điều này giúp giảm sự phụ thuộc vào tình cờ chỉ có một functional bean trong application context.

### 7.2. Ineligible definitions

Một số dependency có thể đóng góp bean Java functional nhưng không phải function mà ứng dụng muốn công bố. Có thể lọc tên bean:

```properties
spring.cloud.function.ineligible-definitions=internalFunction,debugFunction
```

Hãy dùng nó như cấu hình kiểm soát catalog, không phải thay thế authentication/authorization ở adapter.

## 8. Binding name mới không giống tên channel cũ

Trong functional model, Spring Cloud Stream tạo binding name theo tên function và index:

- Input: `<functionName>-in-<index>`.
- Output: `<functionName>-out-<index>`.

Ví dụ `uppercase` có:

```text
uppercase-in-0
uppercase-out-0
```

Destination là tài nguyên broker; binding name là tên cổng cấu hình trong ứng dụng. Không nhầm hai khái niệm.

### 8.1. Alias để giữ tên cấu hình

Có thể ánh xạ implicit binding name sang explicit name:

```yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      function:
        bindings:
          uppercase-in-0: textInput
          uppercase-out-0: textOutput
      bindings:
        textInput:
          destination: text.raw
          group: text-workers
        textOutput:
          destination: text.uppercase
```

Sau alias, các thuộc tính binding tiếp theo tham chiếu `textInput`/`textOutput`. Alias không đổi tên bean, không đổi destination và không đổi event type.

Tài liệu Stream lưu ý alias tạo thêm một lớp mapping. Nếu không cần tên mô tả dài hơn, implicit name thường dễ truy vết hơn.

### 8.2. Tên binding của composition

Nếu definition là:

```yaml
spring:
  cloud:
    function:
      definition: normalize|classifyOrder
```

binding logic có thể chứa cả composition:

```text
normalize|classifyOrder-in-0
normalize|classifyOrder-out-0
```

Khi đổi composition thành `validate|normalize|classifyOrder`, binding implicit thay đổi. Alias có thể giúp giữ tên cấu hình ổn định, nhưng phải cập nhật đúng key implicit mới.

## 9. Composition hiện đại và cách đọc ví dụ cũ

Spring Cloud Function hỗ trợ declarative composition bằng `|` hoặc dấu phẩy:

```yaml
spring:
  cloud:
    function:
      definition: normalize|classifyOrder
```

Output của `normalize` đi vào `classifyOrder`. Cần tương thích type giữa hai bước.

Dấu chấm phẩy trong các cấu hình Stream dùng để chọn nhiều definition độc lập:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder;auditOrder
```

Hai function được bind riêng; dấu `;` không tự nối output của function thứ nhất vào input function thứ hai.

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `|` | Composition/pipeline |
| `,` | Cách viết composition khác được hỗ trợ |
| `;` | Nhiều definition độc lập trong ngữ cảnh Stream hỗ trợ |

Một số tài liệu cũ mô tả pipeline bằng channel/`@SendTo`; khi chuyển sang composition, hãy xác định có còn broker boundary hay không. Composition trong FunctionCatalog không tự tạo topic, queue, transaction hoặc durable checkpoint.

## 10. Reactive: module cũ ngừng phân phối, API Reactor nằm trong Function

Một số tài liệu cũ sử dụng dependency `spring-cloud-stream-reactive`. Tài liệu release train 2020.0.x và Stream 3.x ghi nhận module này đã ngừng phân phối từ Stream 3.0; reactive support được cung cấp trực tiếp qua Spring Cloud Function/Reactor.

Mẫu functional reactive:

```java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
```

Không cần thêm `spring-cloud-stream-reactive` chỉ để dùng `Flux` trong chữ ký function nếu phiên bản hiện hành đã cung cấp reactive support native.

### 10.1. Reactive không đồng nghĩa imperative handler có nhiều thread hơn

- Imperative `Function<T,R>` thường xử lý invocation/message theo handler semantics.
- Reactive `Function<Flux<T>,Flux<R>>` xây dựng pipeline trên publisher.
- `Supplier<Flux<T>>` có thể được gọi một lần để tạo stream dài hạn.
- Supplier reactive hữu hạn có thể cần cơ chế poll thích hợp; `@PollableBean` là marker cho trường hợp này trong tài liệu Function hiện hành.

Không áp retry/DLQ của imperative handler cho reactive stream một cách máy móc. Tài liệu Stream giải thích retry/error handling của reactive function dựa trên Reactor operators, trong khi retry template của imperative message handler có semantics khác.

### 10.2. Một lỗi dễ gặp khi nâng

Một nhóm đổi từ:

```java
Function<String, String>
```

sang:

```java
Function<Flux<String>, Flux<String>>
```

rồi giữ nguyên assumption rằng mỗi message lỗi được retry riêng bởi binder. Đây là thay đổi programming model, không chỉ đổi kiểu generic. Phải kiểm tra `onError`, `retryWhen`, resubscription, side effects và ordering.

## 11. Content-Type và conversion: đừng mang header cũ sang mặc định mới

Spring Cloud Function dùng `MessageConverter` cho message input và `ConversionService` cho dữ liệu không phải `Message` khi cần chuyển kiểu. Target type thường được lấy từ chữ ký function; `contentType` giúp lựa chọn converter.

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> classify(order);
}
```

Cấu hình binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        classifyOrder-in-0:
          content-type: application/json
        classifyOrder-out-0:
          content-type: application/json
```

### 11.1. Tài liệu cũ có thể nhắc original-content-type

Trong lịch sử Stream, header `original-content-type` từng được dùng trong các bước chuyển đổi cũ. Tài liệu Stream 3.x ghi nhận các tham chiếu header này đã bị loại sau khi deprecated từ 2.0.

Không thêm header đó chỉ vì thấy trong một ví dụ cũ. Hãy xem `contentType` thực tế, binding property, native codec và converter của version target.

### 11.2. @StreamMessageConverter

Tài liệu Stream 3.x đánh dấu `@StreamMessageConverter` deprecated vì mô hình functional và message conversion hiện tại không còn yêu cầu cách cấu hình cũ đó trong các tình huống tương ứng. Nếu dự án có annotation này, kiểm tra converter thực tế, thay thế bằng `MessageConverter` bean/extension point đúng phiên bản khi cần.

### 11.3. Kiểm tra kiểu dữ liệu trên wire

Không chỉ kiểm tra Java DTO được tạo thành công. Hãy lưu fixture bytes/JSON, content type, headers, unknown fields, nullability, số lớn, enum và Unicode. Native Kafka deserializer có thể xử lý trước Function conversion; `content-type: application/json` không tự cấu hình Kafka serializer/deserializer.

## 12. Dynamic destination: từ BinderAwareChannelResolver đến sendto.destination

Tài liệu Stream cũ sử dụng `BinderAwareChannelResolver` trong một số trường hợp gửi tới destination động. Stream 3.x đánh dấu resolver này deprecated trong hướng function-based và đề xuất sử dụng header/property `spring.cloud.stream.sendto.destination` trong các trường hợp phù hợp.

Ví dụ một function có thể trả `Message` chứa destination được chọn:

```java
@Bean
Function<OrderCreated, Message<OrderClassified>> routeOrder() {
    return order -> MessageBuilder
            .withPayload(classify(order))
            .setHeader("spring.cloud.stream.sendto.destination",
                    destinationFor(order))
            .build();
}
```

Đây là minh họa pattern, cần kiểm tra cơ chế dynamic destination và binder cụ thể của dự án. Không cho input bên ngoài tự chỉ định destination tùy ý; phải có allowlist hoặc mapping do server quản lý.

Dynamic destination có thể tạo topic/queue mới, ảnh hưởng quyền broker, retention và chi phí. Không coi nó là thay thế cho thiết kế topology có owner.

## 13. Error handling: tài liệu cũ và mới có thể nói về các lớp khác nhau

Spring Cloud Stream có error handling ở framework/binder level. Một imperative function ném exception có thể được binder retry theo consumer properties, sau đó chuyển tới DLQ/DLT nếu binder hỗ trợ và được cấu hình.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        classifyOrder-in-0:
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000
```

Tài liệu hiện hành mô tả `maxAttempts` mặc định là 3 cho message handler imperative. Nhưng reactive function không phải message handler theo cùng semantics; lỗi trong `Flux` cần được xử lý bằng Reactor operators và chính sách stream tương ứng.

### 13.1. Custom ErrorMessage handler có thể thay error handler mặc định

Một `Consumer<ErrorMessage>` được cấu hình làm custom error handler có thể loại trừ framework/binder error handlers; trong trường hợp đó, không giả định DLQ vẫn chạy như khi không có custom handler. Đọc đúng phần error handling của binder đang dùng.

### 13.2. Retry không phải bảo đảm exactly-once

Một message có thể được xử lý lại sau lỗi, crash hoặc redelivery. Nếu function đã ghi DB rồi mới ném exception, retry có thể lặp side effect. Dùng event ID, idempotency key, transactional outbox và dedupe phù hợp.

Không chuyển một cấu hình retry từ Kafka sang RabbitMQ hoặc một cloud event source khác mà không kiểm tra khả năng của binder/provider.

## 14. Test binder: MessageCollector cũ và InputDestination/OutputDestination

Tài liệu cũ có thể sử dụng:

```java
@Autowired
MessageCollector messageCollector;
```

và dependency `spring-cloud-stream-test-support`. Tài liệu Stream 3.2.10 ghi nhận test-support binder cũ được deprecate để chuyển sang Integration Test Binder mới.

Mẫu test hiện đại thường dùng `InputDestination` và `OutputDestination`:

```java
@SpringBootTest
class UppercaseStreamTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void transformsMessage() {
        input.send(new GenericMessage<>("hello".getBytes()));

        Message<byte[]> result = output.receive();

        assertThat(new String(result.getPayload()))
                .isEqualTo("HELLO");
    }

    @SpringBootApplication
    @Import(TestChannelBinderConfiguration.class)
    static class TestApplication {

        @Bean
        Function<String, String> uppercase() {
            return String::toUpperCase;
        }
    }
}
```

Đây là cấu trúc minh họa; imports, test binder dependency và cấu hình context cần lấy từ reference đúng version. Với nhiều binding, dùng tên destination/binding tường minh trong `send()`/`receive()`.

### 14.1. Test binder không thay thế broker thật

Integration Test Binder hữu ích để kiểm tra function wiring, binding names và conversion trong JVM. Nó không chứng minh:

- Kafka partition/offset/consumer group.
- Rabbit exchange/queue/ack.
- Native serializer/deserializer.
- Broker ACL, TLS, retry/DLQ topology.
- Message retention và redelivery thực tế.

Cần thêm broker integration test (ví dụ Testcontainers) cho các semantics mà test binder không mô phỏng.

## 15. Binder abstraction vẫn còn giá trị trong thế hệ mới

Một hiểu nhầm khi đọc tài liệu cũ là nghĩ rằng functional model loại bỏ Binder. Thực tế, Spring Cloud Stream vẫn dùng Binder abstraction để kết nối ứng dụng với middleware như Kafka hoặc RabbitMQ.

| Phần | Vai trò |
| --- | --- |
| Function bean | Logic xử lý dữ liệu |
| FunctionCatalog | Lookup/wrapper/composition/conversion |
| Stream binding | Cổng vào/ra của function |
| Binder | Adapter tới middleware |
| Destination | Topic/queue/exchange |
| Consumer group | Nhóm tiêu thụ và semantics phân phối |
| Broker | Hạ tầng lưu/chuyển message |

Functional model giảm coupling với channel APIs và giúp business logic độc lập hơn. Nó không biến Kafka/Rabbit thành cùng một broker semantics; binder-specific config, retry, DLQ, partition và native codec vẫn khác nhau.

## 16. Những điểm thay đổi được ghi nhận trong thế hệ 2026.0.0

Release announcement Spring Cloud 2026.0.0 liệt kê một số thay đổi đáng chú ý:

| Dự án | Điều được công bố | Ý nghĩa khi đối chiếu tài liệu |
| --- | --- | --- |
| Spring Cloud Function | Fix CVE-2026-59439 về JSON collection không giới hạn | Kiểm tra security patch và giới hạn payload |
| Spring Cloud Function | Fix CVE-2026-59440 về khả năng nạp class tùy ý | Kiểm tra dynamic MIME type và allowlist |
| Spring Cloud Function | Deprecation RSocket module | Nếu dùng adapter/module này, lập kế hoạch thay thế |
| Spring Cloud Function | Deprecation gRPC module | Kiểm tra dependency và adapter gRPC |
| Spring Cloud Stream | Fix CVE-2026-59441 về subpackage deserialization | Kiểm tra deserializer và trust policy |
| Spring Cloud Stream | Deprecation reactive Kafka Binder | Phân biệt binder artifact với reactive Function API |
| Spring Cloud Stream | Deprecation Schema Registry component | Xem chiến lược schema/registry của ứng dụng |
| Spring Cloud Bus | Được tích hợp vào Spring Cloud Stream; artifact coordinates giữ nguyên | Đọc release notes trước khi đổi dependency |

**Không suy rằng reactive Function API đã bị deprecated chỉ vì reactive Kafka Binder bị deprecated.** Một cái là programming model dùng Reactor; cái kia là binder artifact cụ thể. Tương tự, deprecation RSocket/gRPC module không đồng nghĩa `Function<T,R>` hay `FunctionCatalog` bị loại bỏ.

Đây là những điểm được công bố ở release train, không phải danh sách đầy đủ mọi thay đổi. Hãy đọc issue/release notes của module cụ thể nếu ứng dụng đang sử dụng tính năng liên quan.

## 17. Cách đối chiếu một đoạn tài liệu cũ theo quy trình

Giả sử bạn tìm được đoạn hướng dẫn cũ:

```java
@EnableBinding(Processor.class)
public class LegacyHandler {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String transform(String input) {
        return input.toUpperCase();
    }
}
```

Thực hiện theo các bước:

### Bước 1 — Xác định version tài liệu

Ghi version Spring Cloud Stream/Spring Cloud train mà ví dụ được viết. Nếu không có version, tìm dependency hoặc API trong ví dụ để suy ra nguồn cần kiểm tra, nhưng không tự gán version.

### Bước 2 — Xác định nghiệp vụ

Method làm gì? Input/output là gì? Có side effect, validation, header, transaction hoặc error path nào không?

Ở đây business logic là `String -> uppercase String`.

### Bước 3 — Xác định adapter

Đoạn code đang nói về Spring Cloud Stream channel model. Nó không phải API thuần của Spring Cloud Function.

### Bước 4 — Tra migration status

Đọc tài liệu Stream 3.x về annotation-based model deprecation và current functional model. Phân biệt deprecated với removed.

### Bước 5 — Chuyển business logic sang function

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
```

### Bước 6 — Viết definition và bindings

```yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: text.raw
          group: text-workers
        uppercase-out-0:
          destination: text.uppercase
```

### Bước 7 — Bảo toàn vận hành

Chuyển tiếp destination, group, content type, partitioning, retry, DLQ, consumer concurrency, headers và security. Không chỉ chuyển method Java.

### Bước 8 — Test trên target artifact

Chạy catalog lookup, test binder, broker thật và deployment-like test. So sánh behavior trước–sau bằng fixture giống nhau.

## 18. Bảng mapping: API/cấu hình cũ sang khái niệm hiện tại

| Legacy pattern | Functional/current concept | Lưu ý migration |
| --- | --- | --- |
| `@EnableBinding(Source.class)` | `Supplier<T>` | Giữ poller/production rate |
| `@EnableBinding(Sink.class)` | `Consumer<T>` | Giữ group, retry và side effects |
| `@EnableBinding(Processor.class)` | `Function<I,O>` | Giữ input/output destinations |
| `@Input`/`@Output` | Implicit binding names hoặc alias | Kiểm tra tên binding |
| `@StreamListener` | Functional bean + `spring.cloud.function.definition` | Chuyển logic và header/error semantics |
| `@SendTo` | Return value của Function hoặc explicit output | Xác minh output mapping |
| `@InboundChannelAdapter` | `Supplier<T>` + poller phù hợp | Kiểm tra tần suất và batch |
| `spring-cloud-stream-reactive` | Reactor types trong functional bean | Không thêm module cũ cho code mới |
| `MessageCollector` | Test Binder + `InputDestination`/`OutputDestination` | Cập nhật test dependencies |
| `@StreamMessageConverter` | `MessageConverter` bean/hiện trạng converter | Chỉ thay khi custom conversion cần |
| `original-content-type` | `contentType`/converter hiện hành | Header cũ đã bị loại bỏ |
| `BinderAwareChannelResolver` | `spring.cloud.stream.sendto.destination` trong trường hợp phù hợp | Kiểm soát dynamic destination |
| `@StreamRetryTemplate` cũ trong ví dụ | Consumer retry/binder config và error handling hiện tại | Xem version và binder cụ thể |

Bảng là bản đồ khái niệm, không phải script tự động đổi source code. Một handler cũ có thể thực hiện nhiều trách nhiệm; tách chúng ra trước khi chuyển.

## 19. Phân biệt thay đổi framework với thay đổi cloud provider

Spring Cloud Function giúp tái sử dụng business logic qua HTTP, stream và serverless. Nhưng cloud provider vẫn có runtime, trigger, identity, retry, scaling và event envelope riêng.

| Câu hỏi | Spring Cloud Function/Stream | Cloud provider |
| --- | --- | --- |
| Chọn function nào? | FunctionCatalog, definition, routing | Handler config/environment nếu adapter dùng |
| Chuyển JSON thành DTO? | MessageConverter/ConversionService | Có thể có event wrapper trước adapter |
| Gửi/nhận event? | Binding/Binder | Kafka, Rabbit, SQS, EventBridge, Pub/Sub, Azure triggers... |
| Retry? | Framework/binder nếu handler và binder hỗ trợ | Event source mapping/host/platform policy |
| Scale? | Consumer concurrency/replicas | Lambda concurrency, Functions host scale, Cloud Run |
| Identity? | Security/application context | IAM, RBAC, service account |
| Packaging? | Adapter/build plugin | JAR/ZIP/container/Functions package |
| Timeout/memory? | Một số application settings | Runtime/provider limits |

Không lấy một đoạn cấu hình `maxAttempts` của Stream binder để kết luận SQS, Azure Queue hay Pub/Sub có cùng retry semantics. Adapter chỉ là cầu nối; provider vẫn quyết định nhiều hành vi vận hành.

## 20. Tài liệu về adapter và runtime cũng có vòng đời riêng

Ví dụ một Java function có thể được triển khai trên AWS Lambda qua `spring-cloud-function-adapter-aws` và handler `FunctionInvoker`. Azure có adapter và Azure Java Worker annotations/DI. GCP có adapter riêng và Functions Framework.

Khi đọc tài liệu cũ, kiểm tra:

- Adapter artifact có còn được phát hành trong BOM target không?
- Handler FQN có còn đúng không?
- Cloud provider runtime còn hỗ trợ Java version đó không?
- Build plugin có tạo đúng artifact layout không?
- Trigger event schema có thay đổi không?
- IAM/RBAC và secret injection có giữ nguyên không?
- Retry/ack/partial batch behavior có đúng không?

Một Java class compile không chứng minh provider có thể load nó. Cần test **artifact cuối cùng** bằng local emulator/Functions Framework hoặc môi trường staging phù hợp.

## 21. Quản lý tài liệu trong dự án: tạo bảng provenance

Mỗi ví dụ quan trọng nên có provenance tối thiểu:

| Trường | Ví dụ |
| --- | --- |
| Document title | Spring Cloud Stream — Functional Binding Names |
| Version | 5.1.x |
| URL | URL reference chính thức |
| Retrieved/reviewed date | 24/11/2026 |
| Project artifact | `spring-cloud-stream` |
| Release train | `2026.0.0` |
| Boot baseline | `4.2.0` |
| Usage | Binding names cho `classifyOrder` |
| Migration status | Current / Deprecated / Removed / Unknown |
| Owner | Nhóm Orders Platform |
| Last verification | CI integration test run |

Một snippet không có version có thể trở thành technical debt. Khi framework nâng cấp, nhóm sẽ không biết snippet được lấy từ nhánh nào và tại sao có property đó.

### 21.1. Ghi rõ mức độ chắc chắn

Mỗi kết luận nên mang một trong các nhãn:

- **CONFIRMED:** release notes/Javadoc đúng version xác nhận.
- **DOCUMENTED:** reference docs mô tả behavior nhưng chưa test trong app.
- **OBSERVED:** đã chạy trên artifact mục tiêu.
- **ASSUMED:** chưa có bằng chứng; không dùng làm cơ sở release.

Một ví dụ blog cũ có thể là CONFIRMED cho Stream 2.0 nhưng chỉ là UNKNOWN cho Stream 5.1.0.

## 22. Kiểm thử migration bằng cùng bộ fixture

Giữ business fixtures giống nhau giữa baseline và target. Tối thiểu:

| Test | Điều cần chứng minh |
| --- | --- |
| FunctionCatalog lookup | Tên function vẫn resolve |
| Composition | Thứ tự function và type tương thích |
| Binding creation | Input/output binding names đúng |
| Destination/group | Broker topology giữ contract |
| JSON conversion | Content type và target DTO đúng |
| Header mapping | Metadata cần thiết không bị mất/leak |
| Supplier poll | Tần suất, batch và finite/reactive semantics đúng |
| Retry/DLQ | Lỗi transient/permanent đi đúng đường |
| Schema compatibility | Consumer mới đọc event cũ; consumer cũ đọc event mới nếu yêu cầu |
| Native codec | Kafka/Rabbit serializer/deserializer đúng |
| Test binder | Wiring/framework behavior đúng |
| Broker integration | Offset, partition, queue, ack và replay đúng |
| Cloud adapter | Handler, event envelope và permissions đúng |
| Rollback | Artifact cũ vẫn xử lý dữ liệu đã phát |

### 22.1. Phân biệt unit, binder test và broker test

- **Unit test:** kiểm tra business function thuần.
- **FunctionCatalog test:** kiểm tra lookup, wrapper và composition.
- **Test binder:** kiểm tra Stream bindings/conversion trong JVM.
- **Broker integration test:** kiểm tra semantics Kafka/Rabbit thực.
- **Cloud deployment test:** kiểm tra provider event source, IAM, packaging và retry.

Không một tầng test đơn lẻ thay thế tất cả tầng còn lại.

## 23. Case study: nâng một service cũ lên release train mới

Giả sử baseline có:

- Spring Boot 2.x/3.x theo dự án.
- Spring Cloud Stream 2.x hoặc 3.2.x.
- `@EnableBinding(Processor.class)`.
- `@StreamListener(Processor.INPUT)`.
- `MessageCollector` trong test.
- Kafka destination `orders.created`, group `order-classifiers`.

Target dự kiến chuyển sang Spring Cloud 2026.0.0/Boot 4.2.0/Function 5.1.0/Stream 5.1.0.

### Giai đoạn A — Inventory

Ghi lại:
- Java handler và mọi annotation.
- Input/output channel names.
- Topic, group, partitions, consumer concurrency.
- Content type và serializer.
- Retry, DLT, offset/ack.
- Event schema và consumer versions.
- Test binder và broker tests.

### Giai đoạn B — Tách nghiệp vụ

Đưa logic vào function bean:

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> classify(order);
}
```

Giữ DTO/event contract cũ trước khi đổi schema. Đặt definition rõ ràng.

### Giai đoạn C — Functional binding

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: order-classifiers
          content-type: application/json
          consumer:
            maxAttempts: 3
        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

Đối chiếu cấu hình binder-specific như Kafka DLT, partitioning, native decoding và ack mode. Không giả định common properties bao phủ mọi tính năng broker.

### Giai đoạn D — Thay test

Chuyển test từ `MessageCollector` sang test binder `InputDestination`/`OutputDestination`, sau đó giữ broker integration test riêng.

### Giai đoạn E — Nâng dependency theo BOM

- Chọn Spring Cloud release train tương thích với Boot 4.2.0.
- Import BOM `2026.0.0`.
- Xóa các version override không cần thiết.
- Kiểm tra dependency tree.
- Kiểm tra deprecation/removal và security advisories.

### Giai đoạn F — Canary

- Deploy consumer mới trước hay producer mới trước tùy schema compatibility.
- Theo dõi lag, DLT, conversion errors, retry, duplicate events.
- Giữ artifact và schema rollback path.
- Chỉ xóa legacy binding code sau khi tất cả consumer đã chuyển và dữ liệu lịch sử vẫn đọc được.

## 24. Những thay đổi trong release train 2026.0.0 cần đưa vào tài liệu nội bộ

Ngoài việc nâng API, release notes 2026.0.0 có một số điểm ảnh hưởng tới cách tổ chức module:

1. **Spring Cloud Bus được tích hợp vào Spring Cloud Stream.** Release notes nói artifact coordinates của các artifact Bus vẫn giữ nguyên. Không tự đổi dependency coordinates chỉ vì project được hợp nhất.
2. **Function gRPC và RSocket modules được đánh dấu deprecated.** Nếu ứng dụng dùng các adapter này, cần inventory và migration path riêng.
3. **Reactive Kafka Binder bị deprecated.** Điều này không có nghĩa Reactor hoặc reactive functional signatures bị loại bỏ.
4. **Schema Registry component của Stream bị deprecated.** Cần xem ứng dụng có dùng component này hay dùng registry bên ngoài/serializer riêng.
5. **Các security fixes** trong Function/Stream là một phần của release; cần xác minh bản vá và advisory tương ứng.

Đây là những thông tin được công bố trong release announcement. Với một hệ thống production, cần mở release notes đầy đủ của từng module và security advisory trước khi quyết định thay thế.

## 25. Các lỗi thường gặp khi đối chiếu tài liệu

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Copy `@EnableBinding` từ bài cũ nhưng API không còn phù hợp | Tài liệu thuộc annotation model deprecated | Chuyển sang functional bean theo version target |
| Dùng `@StreamListener` trong code mới | Lẫn tài liệu Stream 2.x/3.x | Kiểm tra deprecation và dùng function model |
| Không tìm thấy `MessageCollector` | Test support binder cũ đã deprecated | Dùng Integration Test Binder và destinations |
| Không tìm thấy `spring-cloud-stream-reactive` | Module đã ngừng phân phối từ Stream 3.0 | Dùng Reactor types trong function signatures |
| Binding name sai | Nhầm channel interface với implicit binding name | Tính `<function>-in/out-index` và kiểm tra alias |
| Destination đổi theo tên function | Coupling binding với destination | Đặt destination theo domain |
| `original-content-type` không có tác dụng | Header cũ đã bị loại bỏ | Dùng contentType hiện hành |
| `@StreamMessageConverter` không phù hợp | API converter cũ deprecated | Kiểm tra MessageConverter extension hiện tại |
| `BinderAwareChannelResolver` không còn được khuyến nghị | Dynamic send path cũ | Xem `spring.cloud.stream.sendto.destination` |
| Reactive handler không retry như trước | Khác biệt imperative/reactive error semantics | Dùng Reactor operators và test stream lifecycle |
| BOM Boot/Cloud không tương thích | Ghép version độc lập | Dùng release train compatibility matrix |
| Docs snapshot khác artifact GA | Đọc sai nhánh tài liệu | Chọn version-specific docs |
| Test binder đạt nhưng Kafka lỗi | Test binder không mô phỏng broker | Broker integration tests |
| Cloud runtime không load JAR | Packaging/handler khác nhau | Test artifact cuối cùng trên runtime mục tiêu |
| Deprecated bị hiểu là removed | Không kiểm tra API/Javadoc | Xác minh trạng thái theo artifact version |
| Schema Registry component deprecated bị hiểu là mọi registry bị bỏ | Nhầm module tích hợp với chuẩn/schema registry bên ngoài | Đọc phạm vi release note |
| Reactive Kafka Binder deprecated bị hiểu là Flux bị bỏ | Nhầm binder với programming model | Tách binder artifact và Reactor API |

## 26. Checklist đánh giá một trang tài liệu cũ

Trước khi áp dụng ví dụ:

- [ ] Ghi URL và version của trang.
- [ ] Ghi release train và Spring Boot tương ứng.
- [ ] Xác định programming model: annotation, functional, Spring Integration hay reactive.
- [ ] Xác định artifact/binder/adapter mà ví dụ dùng.
- [ ] Kiểm tra class/method/property có deprecated hoặc removed không.
- [ ] Đối chiếu migration guide và release notes.
- [ ] Tách business logic khỏi transport/handler.
- [ ] Kiểm tra binding names, destination, group và headers.
- [ ] Kiểm tra content type, converter và native codec.
- [ ] Kiểm tra retry, DLQ, ack, poller và concurrency.
- [ ] Cập nhật test binder và broker integration tests.
- [ ] Chạy cùng fixture trên baseline và target.
- [ ] Lưu provenance và kết quả xác minh của snippet.
- [ ] Không gỡ legacy API trước khi contract tests đạt.
- [ ] Có rollback plan cho artifact, schema và message đã phát.

## 27. Bài tập thực hành

### Bài tập 1: Đọc đúng phiên bản

Bạn tìm thấy ví dụ `@EnableBinding(Processor.class)` trong Spring Cloud Stream 2.0 và một trang functional binding names thuộc Stream 5.x. Hãy nêu những thông tin phải xác định trước khi so sánh hai đoạn code. Vì sao không thể kết luận trang 2.0 sai?

### Bài tập 2: Chuyển @StreamListener sang Function

Cho handler:

```java
@EnableBinding(Processor.class)
class LegacyHandler {
    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String uppercase(String value) {
        return value.toUpperCase();
    }
}
```

Hãy chuyển sang `Function<String,String>`, khai báo definition, input/output binding, destination và group. Liệt kê các behavior cần kiểm thử ngoài body output.

### Bài tập 3: Source/Sink thành Supplier/Consumer

Một ứng dụng cũ dùng `Source.OUTPUT` và `Sink.INPUT`. Hãy viết functional bean tương đương và giải thích cách kiểm tra poller, group và số replica sau nâng cấp.

### Bài tập 4: Phân biệt deprecated và removed

Một tài liệu Stream 3.2.10 ghi `@StreamListener` deprecated. Tài liệu hiện hành còn mô tả một số legacy/annotation configurations. Hãy đề xuất cách xác minh class còn tồn tại ở version target và quyết định có nên tiếp tục dùng hay không.

### Bài tập 5: Test binder migration

Một test dùng `MessageCollector` không còn compile sau nâng cấp. Hãy mô tả cách thay bằng `InputDestination`/`OutputDestination`, và liệt kê những test broker thật vẫn cần giữ.

### Bài tập 6: Reactive module cũ

Một ứng dụng phụ thuộc `spring-cloud-stream-reactive` và có handler dựa trên `Flux`. Hãy chuyển sang functional signature Reactor, giải thích `Supplier<Flux<T>>` và `@PollableBean`, rồi thiết kế test cho error/retry lifecycle.

### Bài tập 7: Release train hiện hành

Tại ngày 24/11/2026, hãy tra release train 2026.0.0 và xác định Boot, Function, Stream versions. Vì sao không được ghi 2026.0.0 vào property version của từng artifact?

### Bài tập 8: Tách binder và reactive API

Một hệ thống dùng reactive Kafka Binder và `Function<Flux<Order>,Flux<Result>>`. Release note ghi binder deprecated. Phần nào phải đánh giá migration? Phần nào không được kết luận là bị loại bỏ?

### Bài tập 9: Property cũ và content type

Một cấu hình có `original-content-type` header và custom `@StreamMessageConverter`. Hãy xác định trạng thái lịch sử của chúng và lập kế hoạch kiểm thử `contentType`/`MessageConverter` trên version target.

### Bài tập 10: Viết provenance cho snippet

Tạo một record cho mỗi ví dụ quan trọng gồm version, release train, artifact, URL, ngày kiểm tra, trạng thái migration và test evidence. Nêu cách CI có thể cảnh báo snippet dùng API deprecated.

### Câu hỏi tự đánh giá

1. Spring Cloud release train version khác Spring Cloud Function version thế nào?
2. Vì sao phải kiểm tra version trên URL và banner của docs?
3. Functional model được tích hợp vào Spring Cloud Stream từ phiên bản nào?
4. `@EnableBinding`/`@StreamListener` có trạng thái gì trong tài liệu Stream 3.x?
5. Deprecated khác discontinued và removed thế nào?
6. Tại sao không nên xóa mọi annotation chỉ vì một tài liệu mới dùng Function?
7. `FunctionCatalog.lookup` khác lấy bean trực tiếp từ ApplicationContext thế nào?
8. Binding name functional model được tạo theo quy tắc nào?
9. Alias binding có đổi destination không?
10. Vì sao `spring-cloud-stream-reactive` không còn cần cho reactive function model hiện hành?
11. Imperative và reactive error handling khác nhau ra sao?
12. Tại sao test binder không thay broker integration test?
13. `MessageCollector` được thay bằng cơ chế nào?
14. `original-content-type` có nên được copy từ tài liệu cũ không?
15. Binder abstraction còn vai trò gì trong functional model?
16. Release train 2026.0.0 dựa trên Boot version nào?
17. Deprecation reactive Kafka Binder có nghĩa Reactor API bị loại bỏ không?
18. Làm sao phân biệt một thay đổi do framework với thay đổi do cloud provider?
19. Những thông tin nào phải được giữ khi chuyển annotation model sang function model?
20. Tại sao phải có provenance cho ví dụ và tài liệu nội bộ?

## 28. Tổng kết

Đối chiếu tài liệu cũ với thế hệ dịch vụ đám mây hiện hành cần giữ đúng bối cảnh:

- **Tài liệu cũ có thể vẫn chính xác cho phiên bản cũ.** Ghi lại version, release train và artifact trước khi áp dụng.
- **Functional model là hướng được Spring Cloud Stream khuyến nghị từ thế hệ 3.x.** Các annotation native như `@EnableBinding`/`@StreamListener` được đánh dấu deprecated; không khẳng định mọi API legacy đã bị xóa nếu chưa kiểm tra target artifact.
- **Spring Cloud Function chuẩn hóa invocation qua FunctionCatalog.** `Supplier`, `Function`, `Consumer`, composition và conversion giúp tái sử dụng business logic.
- **Binding name, destination và event contract là những lớp khác nhau.** Chuyển programming model không tự cho phép đổi topic, group, schema hoặc header.
- **Reactive support được tích hợp qua Reactor types.** Module `spring-cloud-stream-reactive` đã ngừng phân phối; imperative retry và reactive stream error handling không giống nhau.
- **Test binder và broker test có phạm vi khác nhau.** `InputDestination`/`OutputDestination` kiểm tra wiring trong JVM; Kafka/Rabbit integration test kiểm tra semantics thực.
- **Release train 2026.0.0** là mốc hiện hành trong bài, dựa trên Boot 4.2.0 và liệt kê Function/Stream 5.1.0; cần theo dõi deprecation và security fixes của từng module.

Quy trình tốt là **xác định nguồn/version → kiểm tra release train → phân loại API cũ → tách nghiệp vụ khỏi transport → chuyển function và bindings → giữ event contract → cập nhật test → chạy trên broker/runtime thật → canary và rollback**.

Đừng copy nguyên một ví dụ cũ hoặc mới mà không hiểu phạm vi. Hãy giữ lại phần nghiệp vụ và hợp đồng đã được kiểm chứng, rồi chuyển từng lớp framework theo tài liệu của đúng release train. Như vậy logic `Supplier`, `Function`, `Consumer` có thể tiếp tục được dùng qua HTTP, sự kiện hoặc serverless mà không kéo theo những giả định lỗi thời về binder, runtime và cloud provider.

### Tài liệu tham khảo

- [Spring Cloud 2026.0.0 — Release announcement, 20/11/2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Train Reference — Version 2026.0.0, Boot compatibility và project versions](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Function — Current Reference Documentation](https://docs.spring.io/spring-cloud-function/reference/)
- [Spring Cloud Function 5.0 — Programming Model](https://docs.spring.io/spring-cloud-function/reference/5.0/spring-cloud-function/programming-model.html)
- [Spring Cloud Function 3.2.10 — Historical Reference](https://docs.spring.io/spring-cloud-function/docs/3.2.10/reference/html/spring-cloud-function.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binder Abstraction](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-abstraction.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream 3.2.10 — Historical Reference and Deprecations](https://docs.spring.io/spring-cloud-stream/docs/3.2.10/reference/html/spring-cloud-stream.html)
- [Spring Cloud Stream 3.0.x — Legacy annotation-based support](https://docs.spring.io/spring-cloud-stream/docs/3.0.x/reference/html/spring-cloud-stream.html)
- [Spring Cloud Stream — Testing and Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Function — AWS adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html)
- [Spring Cloud Function — Azure adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html)
- [CloudEvents Specification 1.0](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
