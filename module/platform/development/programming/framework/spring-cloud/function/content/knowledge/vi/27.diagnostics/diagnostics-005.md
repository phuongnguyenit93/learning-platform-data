# Chữ ký generic bị mất sau đăng ký hoặc đóng gói

## 1. Triệu chứng: hàm có trong catalog nhưng đầu vào không còn đúng kiểu

Giả sử một ứng dụng **Spring Cloud Function** có hàm tiếp nhận đơn hàng:

~~~java
@Bean
public Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

Khi function được tra cứu qua `FunctionCatalog` và gọi bằng HTTP, message broker hoặc serverless adapter, framework thường cần biết `OrderEvent` là kiểu đầu vào để chuyển dữ liệu JSON thành đối tượng Java. Nhưng sau một lần refactor cách đăng ký, thêm proxy, thay plugin đóng gói hoặc chuyển sang native image, một số lỗi có thể xuất hiện:

- `FunctionCatalog.getNames(null)` vẫn chứa `acceptOrder`, nhưng adapter đưa vào `LinkedHashMap` thay vì `OrderEvent`.
- `ClassCastException` xuất hiện khi lambda truy cập `event.orderId()`.
- Metadata input/output trong Actuator hoặc log bị suy ra là `Object` thay vì DTO.
- Composition `normalize|acceptOrder` đột nhiên không chuyển đổi được kết quả giữa hai bước.
- Chương trình chạy khi khởi động trong IDE nhưng lỗi trong JAR hoặc native executable.
- `Function<Flux<OrderEvent>,Flux<OrderReceipt>>` nhận phần tử sai kiểu và chỉ báo lỗi khi subscriber thực sự tiêu thụ stream.
- Một lambda đăng ký động hoạt động tốt khi gọi trực tiếp với POJO nhưng converter không biết đích khi nhận JSON bytes.

Bài thuộc chương **Chẩn đoán**, với đề mục **“Chữ ký generic bị mất sau đăng ký hoặc đóng gói”**, trong module `SPRING_CLOUD_FUNCTION`. Module này hướng đến logic nghiệp vụ tái sử dụng bằng `Supplier`, `Function`, `Consumer`, tra cứu và composition qua `FunctionCatalog`, rồi triển khai cùng logic bằng HTTP, sự kiện hoặc serverless.

**Nguyên tắc trọng tâm:** có bean và có tên trong catalog **không đồng nghĩa** thông tin kiểu `I` và `O` trong `Function<I,O>` còn đầy đủ. Ngược lại, nhận `Map` cũng không tự chứng minh JAR đã làm mất metadata; có thể dữ liệu đã được native deserializer chuyển thành Map.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Java type erasure** với **generic Signature metadata** trong bytecode.
2. Giải thích vì sao `@Bean Function<OrderEvent,OrderReceipt>` thường giữ được kiểu còn `@Bean Function` raw thì không.
3. Sử dụng `FunctionRegistration` và `FunctionTypeUtils` khi đăng ký lambda theo functional startup.
4. Xác định sự khác nhau giữa generic trên factory method, interface của class và runtime class của lambda/proxy.
5. Giữ đúng các lớp generic trong `Message<OrderEvent>`, `Flux<OrderEvent>`, `Supplier<Flux<T>>` và `List<T>`.
6. So sánh thông tin kiểu ở source, Spring context, catalog và JAR thực sự deploy.
7. Điều tra công cụ shading/obfuscation, AOP proxy, AOT/native image mà không quy mọi trường hợp về cùng một nguyên nhân.
8. Viết kiểm thử signature, catalog, adapter HTTP, Stream, serverless và packaged artifact.

## 2. Java erasure không tự xóa hết generic declaration

Java generics chủ yếu được kiểm tra tại thời điểm biên dịch. Trong bytecode, lời gọi tới `Function.apply` về cơ bản làm việc với các kiểu đã bị erase, ví dụ `apply(Object)`. Tuy nhiên, compiler có thể ghi generic declaration vào thuộc tính `Signature` của class hoặc method.

Do đó hai điều cùng đúng:

- **Runtime object không nhất thiết mang đầy đủ type arguments.** Một lambda synthetic class có thể chỉ được nhìn thấy như `Function` không có `OrderEvent`/`OrderReceipt`.
- **Khai báo class/method vẫn có thể mang type arguments cho reflection.** `@Bean Function<OrderEvent,OrderReceipt>` hoặc `class OrderConverter implements Function<OrderEvent,OrderReceipt>` có metadata để Spring khám phá.

~~~mermaid
flowchart TD
    SOURCE["Khai báo Function<OrderEvent,OrderReceipt>"] --> COMPILER["javac"]
    COMPILER --> ERASED["JVM method: apply(Object)"]
    COMPILER --> SIGNATURE["Signature attribute trên method/class"]
    SIGNATURE --> SPRING["Spring ResolvableType / SCF type discovery"]
    SPRING --> CATALOG["FunctionCatalog wrapper"]
    CATALOG --> CONVERTER["Chuyển JSON sang OrderEvent"]
~~~

| Thứ cần phân biệt | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Erased method signature | `apply(Object)` | Bình thường trong Java |
| Generic declaration | `Function<OrderEvent,OrderReceipt>` | Có thể đọc qua reflection nếu được lưu |
| Spring bean type | Declared return type của factory `@Bean` | Một nguồn cho Spring suy generic |
| SCF registration type | `FunctionRegistration.type(...)` | Cung cấp kiểu khi đăng ký động |
| Adapter input runtime type | `Map`, `String`, `byte[]` hoặc `OrderEvent` | Kết quả sau converter/deserializer |

**Không có property nào “tắt Java type erasure”.** Cách sửa đúng là khai báo hoặc cung cấp metadata ở ranh giới framework sử dụng.

## 3. Ví dụ Java 17+ với DTO và function cụ thể

Các ví dụ trong bài dùng DTO record:

~~~java
package demo.generic;

public record OrderEvent(
    String orderId,
    long amountCents
) {}
~~~

~~~java
package demo.generic;

public record OrderReceipt(
    String orderId,
    String status
) {}
~~~

Và một implementation có generic interface rõ ràng:

~~~java
package demo.generic;

import java.util.function.Function;

public final class OrderConverter
        implements Function<OrderEvent, OrderReceipt> {

    @Override
    public OrderReceipt apply(OrderEvent event) {
        return new OrderReceipt(event.orderId(), "ACCEPTED");
    }
}
~~~

Spring configuration đúng:

~~~java
package demo.generic;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TypedOrderFunctions {

    @Bean
    public Function<OrderEvent, OrderReceipt> acceptOrder() {
        return new OrderConverter();
    }
}
~~~

Đây là thiết kế nên ưu tiên khi input/output là các DTO cố định. Metadata vừa có trong return type của method `acceptOrder()`, vừa có trong interface do `OrderConverter` implement.

### 3.1. Vì sao kiểu trả về của @Bean quan trọng?

Spring Cloud Function lazily đăng ký các functional beans phù hợp từ `ApplicationContext` vào `FunctionCatalog`. Với một bean được khai báo qua `@Bean`, generic return type của factory method là nguồn thông tin cho việc suy kiểu.

Nếu đổi thành:

~~~java
@Bean
public Object acceptOrder() {
    return new OrderConverter();
}
~~~

Spring chỉ nhìn thấy declared return type `Object` ở factory method. Tùy cơ chế khám phá bean, type information có thể mất hoặc function không còn được nhận diện sớm như functional bean.

Nếu đổi thành:

~~~java
@SuppressWarnings("rawtypes")
@Bean
public Function acceptOrder() {
    return new OrderConverter();
}
~~~

thì phương thức chỉ công bố `Function` raw. Catalog có thể tìm tên nhưng không còn type arguments cụ thể từ method.

### 3.2. Function<Object,Object> là một hợp đồng khác

~~~java
@Bean
public Function<Object, Object> acceptAnything() {
    return payload -> payload;
}
~~~

Function này thực sự yêu cầu xử lý `Object`. Nếu nhận JSON object và converter tạo `LinkedHashMap`, đó có thể là hành vi hợp lệ chứ không phải Jackson lỗi.

Đừng giải quyết bằng một unchecked cast:

~~~java
Function<OrderEvent, OrderReceipt> typed =
    (Function<OrderEvent, OrderReceipt>) raw;
~~~

Cast không tạo metadata mới ở registration và không biến một Map thành DTO.

## 4. Khai báo kiểu trên factory method khác runtime class của lambda

Xét:

~~~java
Function<OrderEvent, OrderReceipt> lambda =
    event -> new OrderReceipt(event.orderId(), "ACCEPTED");
~~~

Kiểu `OrderEvent`/`OrderReceipt` được compiler biết tại **điểm khai báo biến**. Nhưng khi chỉ truyền object cho API raw:

~~~java
void register(String name, Function function) {
    // API chỉ nhận kiểu Function không có type arguments.
}
~~~

thông tin generic của biến nguồn không tự chuyển thành một runtime token trong `function`.

### 4.1. Vì sao getClass() dễ đánh lừa người chẩn đoán?

~~~java
System.out.println(lambda.getClass().getName());
System.out.println(
    java.util.Arrays.toString(
        lambda.getClass().getGenericInterfaces()
    )
);
~~~

Lambda có thể là synthetic class; generic interfaces phản xạ được không nhất thiết thể hiện đầy đủ DTO types. Việc đó **không chứng minh file JAR đã strip `Signature`**: có thể generic declaration nằm trên một `@Bean` method, không nằm trên lambda runtime class.

### 4.2. Named class là một nguồn metadata khác

~~~java
public final class AcceptOrderFunction
        implements Function<OrderEvent, OrderReceipt> {

    @Override
    public OrderReceipt apply(OrderEvent event) {
        return new OrderReceipt(event.orderId(), "ACCEPTED");
    }
}
~~~

Interface declaration nằm trong class file của `AcceptOrderFunction`. Khi có thể, Spring `ResolvableType` có thể đọc `Function<OrderEvent,OrderReceipt>` từ class hierarchy.

**Quy tắc:** nếu function đăng ký bằng lambda động và không có factory method generic để đọc, hãy cung cấp metadata khi đăng ký; không mong framework suy types từ nội dung lambda body.

## 5. Functional registration: vai trò của FunctionRegistration

Spring Cloud Function có mô hình khai báo functional beans bằng `FunctionalSpringApplication` và `ApplicationContextInitializer<GenericApplicationContext>`. Tài liệu chính thức cho biết `FunctionRegistration` bao gồm **function và type information**, vì một phần thông tin vốn suy được từ `@Bean` method có thể bị mất khi đăng ký kiểu functional.

### 5.1. Ví dụ tối thiểu theo mô hình functional

~~~java
package demo.generic;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.cloud.function.context.FunctionRegistration;
import org.springframework.cloud.function.context.FunctionalSpringApplication;
import org.springframework.cloud.function.context.catalog.FunctionTypeUtils;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.support.GenericApplicationContext;

@SpringBootConfiguration
public class FunctionalDemoApplication
        implements ApplicationContextInitializer<GenericApplicationContext> {

    public static void main(String[] args) {
        FunctionalSpringApplication.run(
            FunctionalDemoApplication.class, args
        );
    }

    @Override
    public void initialize(GenericApplicationContext context) {
        Function<String, String> uppercase =
            value -> value.toUpperCase(Locale.ROOT);

        context.registerBean(
            "uppercase",
            FunctionRegistration.class,
            () -> new FunctionRegistration<>(uppercase)
                .type(FunctionTypeUtils.functionType(
                    String.class,
                    String.class
                ))
        );
    }
}
~~~

Đây là ví dụ thuộc **functional startup model**, không phải code cần chèn thêm vào mọi ứng dụng `@SpringBootApplication` thông thường. Khi dự án cần Spring Boot autoconfiguration rộng, hãy xem tài liệu về functional/hybrid mode và phiên bản dependency.

### 5.2. Đăng ký OrderEvent → OrderReceipt

Trong initializer:

~~~java
Function<OrderEvent, OrderReceipt> handler =
    event -> new OrderReceipt(event.orderId(), "ACCEPTED");

context.registerBean(
    "acceptOrder",
    FunctionRegistration.class,
    () -> new FunctionRegistration<>(handler)
        .type(FunctionTypeUtils.functionType(
            OrderEvent.class,
            OrderReceipt.class
        ))
);
~~~

`FunctionTypeUtils.functionType(input,output)` trả metadata `Type` cho một function; nó khác việc chỉ dùng `Function.class` hoặc một raw lambda instance.

### 5.3. Khi nào nên dùng class thay vì gắn type từ Class?

Nếu function có generic lồng nhau hoặc signature phản ứng, một class implement đầy đủ interface generic có thể giúp giữ metadata.

~~~java
public final class StreamOrderFunction
        implements Function<Flux<OrderEvent>, Flux<OrderReceipt>> {

    @Override
    public Flux<OrderReceipt> apply(Flux<OrderEvent> input) {
        return input.map(event ->
            new OrderReceipt(event.orderId(), "ACCEPTED")
        );
    }
}
~~~

Đăng ký dạng class được tài liệu mô tả:

~~~java
context.registerBean(
    "streamOrder",
    FunctionRegistration.class,
    () -> new FunctionRegistration<>(new StreamOrderFunction())
        .type(StreamOrderFunction.class)
);
~~~

Chữ ký generic của class chứa kiểu phần tử `OrderEvent` và `OrderReceipt`. Nếu dùng `FunctionTypeUtils.functionType(Flux.class,Flux.class)` thì **chỉ có raw Flux types**, chưa nói mỗi phần tử là class nào.

## 6. Cần bảo toàn cả generic bên ngoài lẫn kiểu phần tử

Các chữ ký khác nhau về số tầng generic:

~~~java
Function<OrderEvent, OrderReceipt>

Function<Message<OrderEvent>, Message<OrderReceipt>>

Function<Flux<OrderEvent>, Flux<OrderReceipt>>

Function<Flux<OrderEvent>, Mono<Void>>

Supplier<Flux<OrderEvent>>

Consumer<Flux<OrderEvent>>
~~~

Ví dụ:

~~~text
Function
 ├─ input: Flux
 │   └─ item: OrderEvent
 └─ output: Flux
     └─ item: OrderReceipt
~~~

Nếu chỉ giữ `Function<Flux,Flux>`, adapter không được cung cấp `OrderEvent` để chuyển từ JSON thành từng item. Nếu giữ `Function<Message<?>,Message<?>>`, kiểu payload bên trong Message vẫn không xác định.

| Chữ ký | Metadata cụ thể | Nguy cơ nếu mất |
| --- | --- | --- |
| `Function<OrderEvent,OrderReceipt>` | DTO input/output | JSON thành Map hoặc ép kiểu lỗi |
| `Function<Message<OrderEvent>,...>` | Payload type bên trong Message | Header còn nhưng payload không typed |
| `Function<Flux<OrderEvent>,...>` | Element type của publisher | Lỗi khi subscribe/consume |
| `Supplier<Flux<OrderEvent>>` | Output item type | Binder/serializer không biết schema |
| `Consumer<Flux<OrderEvent>>` | Input item type | Consumer nhận Map/String thay DTO |
| `Function<List<OrderEvent>,...>` | Element type của collection | Jackson tạo `List<Map>` |

### 6.1. Không nhầm Mono<Void> với kiểu payload đầu vào

`Function<Flux<OrderEvent>,Mono<Void>>` có input là Flux các sự kiện đơn hàng; `Mono<Void>` chỉ biểu thị hoàn tất hoặc lỗi, không phát payload. Một metadata `Mono<Object>` không phải lựa chọn tương đương khi output vốn là completion-only.

### 6.2. List<OrderEvent> khác List.class

~~~java
List<OrderEvent> orders = mapper.readValue(
    json,
    new TypeReference<List<OrderEvent>>() {}
);
~~~

Trong khi:

~~~java
List values = mapper.readValue(json, List.class);
// Các item JSON object có thể thành LinkedHashMap.
~~~

Vì vậy `FunctionTypeUtils.functionType(List.class,BatchReceipt.class)` chưa đủ để biểu diễn `Function<List<OrderEvent>,BatchReceipt>`. Cần `ParameterizedType` phù hợp hoặc khai báo method/class generic đầy đủ.

## 7. FunctionCatalog có tên nhưng converter vẫn có thể thiếu target type

~~~java
FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

System.out.println(catalog.getNames(null));

Function<OrderEvent, OrderReceipt> function =
    catalog.lookup(Function.class, "acceptOrder");
~~~

Có ba câu hỏi độc lập:

1. `getNames(null)` có `acceptOrder`?
2. `lookup` trả wrapper?
3. Wrapper và adapter có biết kiểu `OrderEvent` khi nhận bytes/Message không?

**`lookup != null` chỉ chứng minh function được tra cứu**, không chứng minh JSON conversion thành công. Ngoài ra, khi chỉ có một functional bean, single-function fallback có thể trả function duy nhất dù tên lookup gõ sai. Nếu cần kiểm tra tên chính xác, kết hợp inventory với property:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

### 7.1. Bean gốc và wrapper khác nhau

~~~java
Function<OrderEvent, OrderReceipt> raw =
    applicationContext.getBean("acceptOrder", Function.class);

Function<OrderEvent, OrderReceipt> wrapped =
    catalog.lookup(Function.class, "acceptOrder");
~~~

Bean gốc thực hiện logic, còn catalog wrapper có thể bổ sung chuyển đổi kiểu và composition. Không dùng test `assertSame(raw,wrapped)` để xác nhận contract; hãy kiểm tra tên, kiểu và hành vi tại ranh giới phù hợp.

### 7.2. Map không nhất thiết do generic metadata mất

Nếu Kafka native deserializer đã trả `Map`, hoặc HTTP body là envelope chứa `body` được decode thành Map trước khi gọi function, lỗi nằm ở adapter/input contract. Generic signature có thể còn nguyên. Luôn xác định ai tạo Map.

## 8. Đọc generic type trên factory method bằng ResolvableType

Spring Framework cung cấp `ResolvableType` để phân giải các generic arguments trong method return type.

~~~java
package demo.generic;

import java.lang.reflect.Method;
import java.util.function.Function;

import org.springframework.core.ResolvableType;

public final class SignatureInspector {

    public static void main(String[] args) throws Exception {
        Method method =
            TypedOrderFunctions.class.getMethod("acceptOrder");

        ResolvableType type =
            ResolvableType.forMethodReturnType(method)
                .as(Function.class);

        System.out.println(
            type.getGeneric(0).resolve()
        ); // OrderEvent.class

        System.out.println(
            type.getGeneric(1).resolve()
        ); // OrderReceipt.class
    }
}
~~~

Khi `TypedOrderFunctions.acceptOrder()` khai `Function<OrderEvent,OrderReceipt>`, hai type arguments có thể được phân giải chính xác.

### 8.1. Raw Function sẽ khác

Nếu method là:

~~~java
@Bean
public Function acceptOrder() {
    return new OrderConverter();
}
~~~

thì `ResolvableType` của **method declaration** không có input/output type arguments cụ thể. Đây là dấu hiệu lỗi nằm **trong source registration**, không cần đoán do JAR hoặc Jackson.

### 8.2. Không chỉ nhìn bean.getClass()

~~~java
Object bean = context.getBean("acceptOrder");

System.out.println(bean.getClass().getName());
~~~

Bean runtime có thể là lambda synthetic class, JDK proxy hoặc CGLIB subclass. Generic signature của **factory method/target class** và generic signature của **runtime object class** có thể khác nhau. Dùng nhiều nguồn thông tin, không kết luận từ một `getClass()`.

## 9. Kiểm tra class triển khai và type variables chưa được đóng

Với class implement interface:

~~~java
ResolvableType type =
    ResolvableType.forClass(OrderConverter.class)
        .as(Function.class);

Class<?> input = type.getGeneric(0).resolve();
Class<?> output = type.getGeneric(1).resolve();
~~~

`input` nên là `OrderEvent.class`, `output` là `OrderReceipt.class`.

### 9.1. Kế thừa generic qua base class

~~~java
public abstract class BaseFunction<I, O>
        implements Function<I, O> {
}

public final class ConcreteOrderFunction
        extends BaseFunction<OrderEvent, OrderReceipt> {

    @Override
    public OrderReceipt apply(OrderEvent event) {
        return new OrderReceipt(event.orderId(), "ACCEPTED");
    }
}
~~~

`ResolvableType` có thể lần theo generic hierarchy để xác định `I`/`O`. Nhưng nếu một class sử dụng raw `BaseFunction`, type variables không được bind cụ thể thì thông tin vẫn có thể thiếu.

### 9.2. Class generic chưa đủ cụ thể

~~~java
public class GenericAuditFunction<T>
        implements Function<T, String> {

    @Override
    public String apply(T value) {
        return String.valueOf(value);
    }
}
~~~

Khai báo này chỉ biết `T` là một biến kiểu, không xác định `T == OrderEvent`. Một instance đăng ký động vẫn cần metadata bổ sung nếu converter phải tạo `OrderEvent`.

## 10. AOP proxy và FactoryBean: phản xạ đúng đối tượng

Một function có thể được proxy bởi AOP/transaction/interceptor hoặc được tạo qua `FactoryBean`. Proxy class có thể chỉ công bố raw `Function`, dù bean definition hay target class còn type metadata.

### 10.1. Những trường hợp nên xem

- Factory method khai return type `Object` dù instance là typed function.
- JDK dynamic proxy công bố interface `Function` raw.
- Custom decorator tạo một function mới nhưng chỉ khai `Function<Object,Object>`.
- `FactoryBean.getObjectType()` quá chung.
- Class thực hiện generic interface có type variables chưa resolved.
- Functional registration che target class đằng sau lambda supplier.

### 10.2. Phép kiểm tra an toàn

~~~java
String beanName = "acceptOrder";

log.info("beanType={}", context.getType(beanName));

Object bean = context.getBean(beanName);

log.info("runtimeBeanClass={}", bean.getClass().getName());
~~~

Nếu dùng Spring AOP, có thể tham khảo target class bằng `AopUtils.getTargetClass(bean)` và so với `@Bean` method/class declaration. Không tháo proxy hoặc bỏ interceptor giao dịch khi chưa có chứng cứ proxy là nguyên nhân.

**Proxy tồn tại không có nghĩa generic đã biến mất.** Spring có thể suy từ bean definition thay vì từ runtime proxy class.

## 11. Nhận diện lỗi theo thời điểm xuất hiện

| Triệu chứng | Tầng lỗi nghi vấn | Kiểm tra đầu tiên |
| --- | --- | --- |
| Function không có trong catalog | Bean discovery/registration | `ApplicationContext`, bean name, profile |
| Catalog có tên nhưng input type hiển thị `object` | Type metadata | `@Bean` signature, `FunctionRegistration` |
| JSON body thành `LinkedHashMap` | Target quá chung hoặc native decoder | Signature + payload class + converter |
| `ClassCastException` khi invoke | Map/Object đưa tới typed lambda | Caller/wrapper và input runtime |
| Error chỉ khi subscribe `Flux` | Element type mismatch trong pipeline | `StepVerifier`, nested generic |
| JSON parse exception trước function | Jackson/schema/converter | Test Jackson, Content-Type |
| JAR khác IDE | Build transform hoặc runtime configuration | `javap`, dependency, profile |
| Native-only reflection exception | AOT hints | DTO reflection, generated context |
| Composition `a|b` lỗi | Type giữa các function | Input/output từng mắt xích |
| HTTP 404 | Web mapping/definition | Function selection và route |
| Stream không nhận event | Binder/binding | Destination, consumer group, logs |

Một `MessageConversionException` có thể bao bọc exception Jackson; hãy đọc **root cause** và stack trace để xác định lỗi xảy ra trước hay sau invocation.

## 12. Content-Type mô tả định dạng, generic mô tả kiểu đích

Ví dụ Message:

~~~text
contentType: application/json
payload bytes: {"orderId":"ORD-101","amountCents":150000}
~~~

`application/json` nói về wire format. `Function<OrderEvent,OrderReceipt>` nói input cần trở thành `OrderEvent`.

Nếu signature là `Function<Object,Object>`, một `LinkedHashMap` có thể là kết quả giải mã hợp lý. Không thể thay thế target type bằng việc đặt Content-Type đúng.

### 12.1. Message<T> giữ hai lớp kiểu

~~~java
@Bean
Function<Message<OrderEvent>, Message<OrderReceipt>> acceptMessage() {
    return message ->
        MessageBuilder.withPayload(
            new OrderReceipt(
                message.getPayload().orderId(),
                "ACCEPTED"
            )
        ).build();
}
~~~

Cần import `org.springframework.messaging.Message` và `MessageBuilder`. Với `Message<?>` hoặc `Message<Object>`, target payload không cụ thể.

### 12.2. Native deserialization là một ranh giới khác

Nếu Spring Cloud Stream dùng:

~~~properties
spring.cloud.stream.bindings.acceptOrder-in-0.consumer.useNativeDecoding=true
~~~

binder/client deserializer có thể tạo `Map` trước khi dữ liệu tới SCF converter. Khi đó không nên mặc định rằng chỉ bổ sung generic metadata sẽ tự sửa native decoder; cần kiểm tra deserializer và kiểu payload thực.

### 12.3. Serverless envelope không phải POJO trực tiếp

Một event có thể là:

~~~json
{
  "requestContext": {"requestId": "req-101"},
  "body": "{\"orderId\":\"ORD-101\",\"amountCents\":150000}"
}
~~~

Dù signature `Function<OrderEvent,OrderReceipt>` còn nguyên, nếu adapter đưa toàn envelope thì schema input vẫn không khớp. Đây là lỗi adapter/event contract, không tự chứng minh generic bị strip.

## 13. Mất kiểu khi composition

Hai function:

~~~java
@Bean
Function<String, OrderEvent> parseOrder(ObjectMapper mapper) {
    return json -> {
        try {
            return mapper.readValue(json, OrderEvent.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                "Invalid order JSON", error
            );
        }
    };
}

@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return new OrderConverter();
}
~~~

Có thể ghép:

~~~properties
spring.cloud.function.definition=parseOrder|acceptOrder
~~~

Nếu `parseOrder` được đổi thành `Function<String,Object>` và parse `Object.class`, JSON object có thể thành Map. Khi đó output của bước trước không còn contract rõ là `OrderEvent`.

**Một composition resolve đủ tên chưa chứng minh metadata và conversion giữa các bước đúng.** Nên test input/output của từng function và cả chuỗi thực thi.

## 14. Packaging: Spring Boot JAR thông thường không cố ý xóa generic Signature

`javac` thường ghi generic declaration của class/method vào `Signature` attribute. Spring Boot executable JAR thông thường chỉ đóng gói các `.class` và dependency, **không phải một bước được thiết kế để strip mọi generic Signature**.

Nếu local chạy được nhưng deployment không:

1. Artifact deploy có đúng commit và version?
2. Class trong JAR có đúng nội dung đã biên dịch?
3. Có shading, obfuscation, minimization, bytecode instrumentation không?
4. Có khác biệt active profiles/conditions không?
5. Có AOT/native image hay functional startup khác không?
6. Có thay đổi dependencies, Jackson module hoặc converter không?

### 14.1. Class còn tồn tại khác Signature còn tồn tại

Một archive có `OrderEvent.class` không chứng minh factory method `acceptOrder()` còn generic return type. Ngược lại, `Signature` còn nguyên chưa bảo đảm converter được nạp và DTO deserialize được.

Cần kiểm tra cả:

- **Class membership:** class có trong JAR không?
- **Method/class Signature:** generic metadata có trong bytecode không?
- **Runtime registration:** Spring có dùng đúng bean và signature đó không?
- **Adapter behavior:** JSON có đến business function đúng kiểu không?

## 15. Dùng javap để kiểm tra trước và sau đóng gói

Các lệnh dưới đây là **hướng dẫn học tập**, không được thực thi trong bước viết nội dung STEP_4.

### 15.1. Kiểm tra class trước đóng gói

Với Gradle:

~~~bash
javap -v -p \
  -classpath build/classes/java/main \
  demo.generic.TypedOrderFunctions
~~~

Với Maven:

~~~bash
javap -v -p \
  -classpath target/classes \
  demo.generic.TypedOrderFunctions
~~~

Tìm `acceptOrder` và `Signature` liên quan. Phần hiển thị rút gọn có thể tương tự:

~~~text
public java.util.function.Function<
    demo.generic.OrderEvent,
    demo.generic.OrderReceipt> acceptOrder();
...
Signature: (...)Ljava/util/function/Function<
    Ldemo/generic/OrderEvent;
    Ldemo/generic/OrderReceipt;>;
~~~

Đây là **mô phỏng rút gọn**, không phải descriptor chính xác từng byte của `javap`.

### 15.2. Kiểm tra executable JAR

~~~bash
jar tf build/libs/orders-app.jar \
  | grep 'TypedOrderFunctions.class'
~~~

Trong nhiều Spring Boot executable JAR, class nằm dưới `BOOT-INF/classes`. Có thể giải nén class vào một thư mục tạm dành riêng cho kiểm tra:

~~~bash
mkdir -p /tmp/scf-generic-inspect
cd /tmp/scf-generic-inspect

jar xf /path/to/orders-app.jar \
  BOOT-INF/classes/demo/generic/TypedOrderFunctions.class

javap -v -p \
  -classpath BOOT-INF/classes \
  demo.generic.TypedOrderFunctions
~~~

Đừng giải nén vào source tree nếu không cần. Cấu trúc của shaded/plain JAR khác với Boot executable JAR nên phải xem `jar tf` trước.

### 15.3. Cách đọc kết quả

| Build classes | Packaged class | Hướng suy luận |
| --- | --- | --- |
| `Signature` đúng | `Signature` đúng | Metadata ở class này không mất; xem registration/adapter |
| `Signature` đúng | `Signature` mất | Nghi bytecode transform/shrink |
| Cả hai không có generic cần thiết | Cả hai thiếu | Source registration có thể đã raw |
| Class thiếu khỏi archive | Không có | Packaging/classpath issue |
| Signature còn nhưng runtime báo `Object` | Có | Có thể đọc sai bean/proxy/registration |

`javap` chỉ chứng minh bytecode **đã lưu metadata**, không tự chứng minh `FunctionCatalog` dùng metadata đó.

## 16. Shading, obfuscation và bytecode transformation

Một số pipeline build sử dụng Maven Shade, Gradle Shadow, ProGuard, R8 hoặc tool bytecode rewriting. Chúng có thể thay đổi class names, resources hoặc attributes.

### 16.1. Shading không nhất thiết làm mất Signature

Relocation có thể cập nhật tên class trong metadata. Khi được cấu hình đúng, generic attributes vẫn có thể tồn tại. Không nên nói “cứ dùng shaded JAR là mất generics”.

Điều cần xác minh:

- Tool có bỏ `Signature` attribute không?
- Relocation có cập nhật tên DTO/interface trong metadata không?
- Shrinking có xóa class/constructor dùng bằng reflection không?
- Merge metadata của Spring autoconfiguration/service loader/Jackson có đúng không?
- Có nhiều phiên bản library bị gộp tạo type mismatch không?

### 16.2. Gợi ý đối với ProGuard

Nếu dự án **thực sự** dùng ProGuard, một cấu hình giữ attributes tham khảo là:

~~~text
-keepattributes Signature,*Annotation*,InnerClasses,EnclosingMethod
~~~

Dòng này **không đủ** để bảo đảm toàn bộ ứng dụng Spring hoạt động: còn cần keep rules phù hợp cho bean configurations, DTO constructors, reflection và serializers. Kiểm tra plugin/version và artifact bằng test thực tế.

### 16.3. Đừng nhầm -parameters với Signature

`-parameters` giúp lưu **tên tham số Java** cho reflection. `Signature` mô tả generic declarations. Đây là hai loại metadata khác nhau.

Nếu lỗi là method return `Function<Object,Object>`, bật `-parameters` không biến chữ ký thành `Function<OrderEvent,OrderReceipt>`. Nếu lỗi là Jackson constructor parameter binding, tên tham số lại có thể liên quan. Hãy xác định đúng metadata thiếu trước.

## 17. AOT/native image: kiểu đích và quyền reflection là hai vấn đề riêng

Với GraalVM native image hoặc quy trình Spring AOT, nhiều quyết định về bean được đưa về build time, còn một số reflection/resource usages phải được khai báo từ trước. Vì vậy, cần tách:

- **Type discovery:** `FunctionCatalog` có hiểu input/output là `OrderEvent` và `OrderReceipt` không?
- **Reflection/binding capability:** Jackson/converter có thể gọi constructor, accessor hoặc field cần thiết trong native image không?
- **Build-time registration:** bean có được tạo trong AOT context theo profile/condition tương ứng không?

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| Actuator/catalog hiển thị `Object` cả JVM lẫn native | Generic declaration/registration chưa rõ |
| JVM packaged JAR chạy đúng, native image báo lỗi reflection | RuntimeHints/Jackson binding metadata |
| Bean có ở local nhưng không có trong native | AOT build-time profiles/conditions/config |
| Class generic còn Signature nhưng Jackson không tạo được DTO | Reflection hints hoặc JSON schema |
| DTO deserialize đúng nhưng function chọn sai | Function definition, router, catalog |

### 17.1. Reflection hints không làm raw Function trở thành typed Function

Đăng ký DTO cho reflection không có nghĩa:

~~~java
Function<Object, Object>
~~~

sẽ tự đổi thành:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

Trước tiên cần sửa chữ ký hoặc `FunctionRegistration.type(...)`, sau đó mới xem DTO đã có reflection hints hay chưa.

### 17.2. Ví dụ đăng ký DTO cho binding ở phiên bản hỗ trợ

Spring Framework cung cấp `@RegisterReflectionForBinding` cho những trường hợp JSON binding chưa được AOT analysis tự phát hiện:

~~~java
@Configuration
@RegisterReflectionForBinding(OrderEvent.class)
class OrderBindingHints {
}
~~~

Đây là ví dụ phụ thuộc phiên bản Spring Framework, với import `org.springframework.aot.hint.annotation.RegisterReflectionForBinding`. Không phải mọi dự án cần thêm annotation này; framework có thể đã tự sinh hints. Chỉ thêm khi có bằng chứng native image thiếu reflection metadata.

### 17.3. Ba chế độ cần so sánh

1. Chạy IDE/test classpath trên JVM.
2. Chạy **JVM artifact đóng gói** thực sự, với profile và dependency giống deployment.
3. Chạy **native executable** nếu production dùng native.

Nếu lỗi đã xuất hiện ở bước 1, nghi registration/DTO; nếu chỉ bước 2 khác, nghi packaging/classpath/config; nếu chỉ bước 3 khác, điều tra AOT/native. Không đổ lỗi JVM type erasure cho mọi sự cố native.

## 18. FunctionCatalog wrapper và type conversion: kiểm tra đúng ranh giới

Một function được khai:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

thường được adapter đưa raw bytes/String/Message tới wrapper từ `FunctionCatalog`. Wrapper có thể hỗ trợ message conversion và composition, nhưng chỉ khi framework có đủ dữ liệu:

- Functional bean name và registration hợp lệ.
- Kiểu đầu vào/đầu ra hoặc metadata tương ứng.
- `contentType`/converter phù hợp với wire payload.
- DTO parse được và đúng schema.
- Adapter thực sự đi qua conversion path đó.

### 18.1. Vì sao test typed POJO có thể pass trong khi HTTP lỗi?

~~~java
OrderReceipt receipt = function.apply(
    new OrderEvent("ORD-101", 150000)
);
~~~

Ở đây caller đã cung cấp `OrderEvent`. Không có JSON cần deserialize.

Trong HTTP:

~~~text
HTTP JSON bytes
    → HTTP adapter
    → Message/ConversionService
    → FunctionCatalog wrapper
    → OrderEvent
    → business function
~~~

Nếu metadata bị mất ở đăng ký, đoạn typed Java test vẫn có thể pass nhưng HTTP nhận Map. Vì vậy cần **test ở cấp ingress**.

### 18.2. Vì sao cần kiểm tra cả output type?

Mất output type có thể khiến:

- Serializer chọn sai media type.
- Spring Cloud Stream binding gửi Map/String/bytes không như hợp đồng.
- Composition không biết kiểu để nối sang function tiếp theo.
- Serverless handler trả envelope/JSON structure khác mong đợi.
- Reactive `Mono<Void>` được hiểu sai là output có payload.

Đừng chỉ xem input type khi sự cố xảy ra ở serialization hoặc bước tiếp theo của composition.

## 19. Quy trình chẩn đoán dựa trên bằng chứng

~~~mermaid
flowchart TD
    START["Map thay POJO / type=Object / lỗi sau package"] --> JSON{"Jackson parse JSON thuần thành DTO được?"}
    JSON -->|Không| DTO["Sửa JSON/schema/DTO trước"]
    JSON -->|Có| CAT{"Catalog tìm đúng function?"}
    CAT -->|Không| REG["Kiểm tra @Bean, scan,\nFunctionRegistration, definition"]
    CAT -->|Có| DECL{"Factory method/class có generic đủ?"}
    DECL -->|Không| TYPE["Sửa raw/Object declaration\nhoặc cung cấp FunctionRegistration.type"]
    DECL -->|Có| BYTE{"JAR giữ Signature không?"}
    BYTE -->|Không| BUILD["Kiểm tra shading,\nobfuscator, bytecode transform"]
    BYTE -->|Có| ADAPTER{"Payload được decode tại đâu?"}
    ADAPTER -->|HTTP / MessageConverter| CONTENT["contentType, target type,\ncustom converter"]
    ADAPTER -->|Stream native decoding| NATIVE["Deserializer / schema / binder"]
    ADAPTER -->|Serverless event| ENV["Event shape / envelope"]
    ADAPTER -->|Native-only| AOT["RuntimeHints / AOT context"]
    DTO --> VERIFY["Kiểm thử lại từng tầng"]
    REG --> VERIFY
    TYPE --> VERIFY
    BUILD --> VERIFY
    CONTENT --> VERIFY
    NATIVE --> VERIFY
    ENV --> VERIFY
    AOT --> VERIFY
~~~

### 19.1. Các bước thực hiện

1. **Ghi nhận triệu chứng chính xác:** lỗi parse, `ClassCastException`, Actuator type là Object, hay lỗi khi subscribe Flux?
2. **Chỉ rõ môi trường:** IDE JVM, packaged JVM, serverless JAR hay native image?
3. **Xác minh JSON thuần:** Jackson có đọc raw payload thành `OrderEvent` không?
4. **Xác minh catalog name:** `catalog.getNames(null)`, function definition và typed lookup.
5. **Kiểm tra factory declaration:** `@Bean` return type có raw/Object không?
6. **Kiểm tra implementation type:** named class có implement generic đầy đủ không?
7. **Nếu functional registration:** có `FunctionRegistration.type(...)` đúng không?
8. **Nếu reactive/Message/List:** có đủ nested item type không?
9. **Nếu nghi packaging:** so `javap -v` ở build output và artifact.
10. **Nếu dùng AOP/FactoryBean:** kiểm tra bean definition/target, không chỉ runtime proxy class.
11. **Nếu adapter nhận Map:** xác định Map do SCF converter hay native deserializer tạo.
12. **Nếu native image:** so runtime hints và build-time context.
13. **Sửa một nguyên nhân rồi kiểm chứng lại** bằng test ở đúng ranh giới.
14. **Bổ sung regression test** cho artifact và adapter để lỗi không quay lại.

## 20. Test tầng 1: generic method và class bằng ResolvableType

Dùng JUnit 5 và AssertJ:

~~~java
package demo.generic;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.core.ResolvableType;

class SignatureDeclarationTest {

    @Test
    void beanFactoryDeclaresInputAndOutput() throws Exception {
        Method method =
            TypedOrderFunctions.class.getMethod("acceptOrder");

        ResolvableType type =
            ResolvableType.forMethodReturnType(method)
                .as(Function.class);

        assertThat(type.getGeneric(0).resolve())
            .isEqualTo(OrderEvent.class);

        assertThat(type.getGeneric(1).resolve())
            .isEqualTo(OrderReceipt.class);
    }

    @Test
    void implementationHasGenericInterface() {
        ResolvableType type =
            ResolvableType.forClass(OrderConverter.class)
                .as(Function.class);

        assertThat(type.getGeneric(0).resolve())
            .isEqualTo(OrderEvent.class);

        assertThat(type.getGeneric(1).resolve())
            .isEqualTo(OrderReceipt.class);
    }
}
~~~

Test này giúp phát hiện code bị refactor từ `Function<OrderEvent,OrderReceipt>` sang raw type. Nó **không** chứng minh converter và packaged artifact hoạt động đúng.

### 20.1. Negative test: raw Function không thể hiện DTO trên method

Ví dụ một class cấu hình cố tình có raw return type:

~~~java
class RawOrderFunctions {

    public Function acceptOrder() {
        return new OrderConverter();
    }
}
~~~

Một test có thể đọc `ResolvableType` của `RawOrderFunctions.acceptOrder()` và xác minh nó không phân giải đầu vào là `OrderEvent.class`. Test này chứng minh **mất generic declaration tại source**, chứ không phải lỗi do Jackson.

### 20.2. Mục tiêu của test này

| Phép test | Nó xác nhận |
| --- | --- |
| `ResolvableType.forMethodReturnType` | Kiểu khai báo factory method |
| `ResolvableType.forClass(...).as(Function.class)` | Generic interface của class triển khai |
| `FunctionRegistration.type` | Metadata runtime cho functional registration |
| `javap -v` packaged artifact | Signature thực sự có trong bytecode đã deploy |

Một runtime lambda class không nhất thiết vượt qua phép test thứ hai; không dùng nó như đại diện duy nhất của @Bean metadata.

## 21. Test tầng 2: FunctionCatalog vẫn đăng ký và xử lý typed input

Một cấu hình Spring Boot dành cho test (có cùng package với `TypedOrderFunctions`):

~~~java
package demo.generic;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GenericDiagnosticsApplication {
}
~~~

Test:

~~~java
package demo.generic;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = GenericDiagnosticsApplication.class)
class CatalogGenericTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void typedFunctionResolves() {
        assertThat(catalog.getNames(null))
            .contains("acceptOrder");

        Function<OrderEvent, OrderReceipt> fn =
            catalog.lookup(Function.class, "acceptOrder");

        assertThat(fn).isNotNull();

        OrderReceipt result = fn.apply(
            new OrderEvent("ORD-101", 150000L)
        );

        assertThat(result)
            .isEqualTo(
                new OrderReceipt("ORD-101", "ACCEPTED")
            );
    }
}
~~~

**Lưu ý:** test trực tiếp với typed `OrderEvent` có thể pass ngay cả khi function được đăng ký raw và adapter không biết type đích. Vì thế cần thêm test **JSON bytes → POJO**.

## 22. Test tầng 3: HTTP adapter với JSON thực

Nếu project có Spring Cloud Function web adapter và Spring Boot Web/test dependencies tương thích:

~~~java
package demo.generic;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    classes = GenericDiagnosticsApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.cloud.function.definition=acceptOrder",
        "spring.cloud.function.single-function-fallback-enabled=false"
    }
)
class HttpGenericTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void jsonBytesReachTypedFunction() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        String json =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        ResponseEntity<String> response = rest.exchange(
            "/acceptOrder",
            HttpMethod.POST,
            new HttpEntity<>(json, headers),
            String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful())
            .isTrue();

        assertThat(response.getBody())
            .contains("ORD-101")
            .contains("ACCEPTED");
    }
}
~~~

Ví dụ giả định web adapter map function ở `/acceptOrder`; các cấu hình dùng root path hoặc web base path khác phải điều chỉnh test theo mapping thực, không đổi generic signature chỉ vì 404.

### 22.1. Test trên chứng minh điều gì?

- Có HTTP endpoint tương ứng.
- JSON wire bytes được adapter nhận.
- Converter và wrapper chuyển được input sang kiểu business function mong đợi.
- Function tạo output có thể được serialize thành response.

Nó chưa chứng minh Spring Cloud Stream native decoding, serverless event envelope hoặc shaded JAR ở production hoạt động giống nhau.

### 22.2. Negative input test

Với:

~~~json
{"orderId":"ORD-101","amountCents":"abc"}
~~~

xác minh request không báo thành công và side effect nghiệp vụ không được thực thi. Status lỗi HTTP cụ thể có thể phụ thuộc version/exception handling; không gắn cứng một mã lỗi khi adapter không cam kết.

## 23. Test tầng 4: reactive generic được giữ ở từng phần tử

Với class `StreamOrderFunction` ở mục 5, kiểm thử bằng `reactor-test`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveGenericTest {

    @Test
    void streamProcessesTypedOrders() {
        StreamOrderFunction function =
            new StreamOrderFunction();

        StepVerifier.create(function.apply(
                Flux.just(
                    new OrderEvent("ORD-101", 150000L),
                    new OrderEvent("ORD-102", 200000L)
                )
            ))
            .expectNext(
                new OrderReceipt("ORD-101", "ACCEPTED"),
                new OrderReceipt("ORD-102", "ACCEPTED")
            )
            .verifyComplete();
    }
}
~~~

Test này xác minh logic/reactive flow với POJO đã có sẵn. Nếu integration input là Kafka bytes/Map, cần test thêm **converter từ wire format**.

### 23.1. Kiểm tra generic của reactive class

~~~java
ResolvableType type =
    ResolvableType.forClass(StreamOrderFunction.class)
        .as(Function.class);

ResolvableType input = type.getGeneric(0);
ResolvableType output = type.getGeneric(1);

assertThat(input.resolve()).isEqualTo(Flux.class);
assertThat(input.getGeneric(0).resolve())
    .isEqualTo(OrderEvent.class);

assertThat(output.resolve()).isEqualTo(Flux.class);
assertThat(output.getGeneric(0).resolve())
    .isEqualTo(OrderReceipt.class);
~~~

Đây mới là phép kiểm tra nested generic đúng: không chỉ assert `Flux.class`.

## 24. Test tầng 5: Spring Cloud Stream và native decoding

Với Spring Cloud Stream, có thể dùng test binder hoặc integration test broker để gửi JSON bytes qua binding thực.

Ví dụ:

~~~properties
spring.cloud.function.definition=acceptOrder
spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.acceptOrder-in-0.content-type=application/json
spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders-out
~~~

Thứ tự test:

1. Kiểm tra function definition và tên binding thực tế.
2. Gửi dữ liệu JSON UTF-8 với header contentType phù hợp.
3. Xác nhận business function nhận `OrderEvent`, không phải `LinkedHashMap`.
4. Xác nhận output serializer tạo payload dự kiến.
5. Nếu `useNativeDecoding=true`, test bằng chính deserializer trong deployment.
6. Test event sai schema và chính sách error handling của binder.

### 24.1. Tại sao lỗi trước function không bắt được bằng onErrorResume?

Nếu Kafka deserializer hoặc adapter message converter thất bại **trước khi gọi function**, một `onErrorResume` bên trong `Function<Flux<T>,Flux<R>>` chưa chắc có cơ hội nhận lỗi đó.

Không giả định đổi generic metadata là đủ chữa lỗi serializer, deserializer hoặc message conversion của broker. Xem stack trace để biết ranh giới thất bại.

## 25. Test artifact đã đóng gói: điều kiện xác nhận packaging là nguyên nhân

Chỉ có thể kết luận “generic bị mất **sau đóng gói**” khi có bằng chứng so sánh:

| Kiểm tra | Bằng chứng mong muốn |
| --- | --- |
| Source/compile output | `@Bean` hoặc implementation class chứa `Signature` đúng |
| Packaged JVM artifact | Class giống logic và còn generic `Signature` |
| Runtime Environment | `spring.cloud.function.definition`, profile, dependency đúng |
| Catalog | Function name và metadata/type wrapper phù hợp |
| Adapter | JSON bytes trở thành đúng POJO |
| Native artifact nếu dùng | Reflection hints, converter, event contract hoạt động |

Nếu source/compile output **đã raw**, đừng đổ lỗi packaging. Nếu artifact còn Signature nhưng custom functional registration chỉ truyền `Function.class`, sửa registration. Nếu packaged JVM hoạt động nhưng native image không deserialize DTO, kiểm tra AOT/reflection.

### 25.1. Một quy trình CI có thể áp dụng

~~~text
Compile
  → Unit tests: @Bean generic / class interface
  → Build executable JAR
  → Inspect Signature in packaged class (nếu dùng bytecode transforms)
  → Boot packaged app với profile đại diện
  → HTTP/Stream smoke test bằng JSON bytes
  → Optional native image integration test
  → Deploy
~~~

Trong STEP_4 này chỉ cần **mô tả** quy trình; vòng chạy build và Content QA được giao cho các bước sau, không tự thực hiện.

## 26. Bảng đối chiếu nguyên nhân và cách sửa

| Nguyên nhân | Dấu hiệu | Cách sửa ưu tiên |
| --- | --- | --- |
| `@Bean` khai raw `Function` | Method signature không có DTO types | Khai `Function<OrderEvent,OrderReceipt>` |
| `@Bean Object` trả function | Bean declared type quá chung | Dùng interface typed |
| Dynamic lambda registration không có type | Catalog thấy Function nhưng input/output `Object` | `FunctionRegistration.type(...)` |
| Generic class chưa bind type variable | `T` không resolve tới DTO | Concrete subclass hoặc explicit type |
| Nested `Flux.class`/`List.class` | Mất item type | Cung cấp nested Type/class signature |
| JDK proxy che runtime generic | `getClass()` không lộ DTO | Kiểm tra factory method/target và registry |
| Shading/obfuscator bỏ `Signature` | Khác biệt bytecode trước/sau | Sửa transformer/keep attributes |
| Minifier xóa DTO/class | Class thiếu hoặc reflection fail | Keep rules cho class/constructor/resources |
| Native-only Jackson reflection error | JVM OK, native fail | AOT/RuntimeHints |
| HTTP contentType không đúng | JSON như String/bytes | Sửa request media type/converter |
| Stream native decoder trả Map | `useNativeDecoding=true` | Cấu hình deserializer target type |
| Serverless event envelope | JSON không khớp DTO | Sửa event schema/adapter |
| Composition trả `Object` | `a|b` convert không rõ | Giữ output typed từ bước a |
| Function lookup sai | Catalog không có tên hoặc fallback | Sửa definition/naming; test strict lookup |

**Một giải pháp không nên dùng cho mọi trường hợp**: nhét `ObjectMapper.convertValue` vào đầu mọi function. Nó có thể che dấu hợp đồng input sai, tăng chi phí và biến schema errors thành lỗi muộn hơn.

## 27. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Java erasure nghĩa là không thể biết `Function<I,O>` ở runtime.” | Generic declaration có thể tồn tại trong `Signature` của method/class |
| “Nếu lambda.getClass() không có DTO types thì JAR chắc chắn strip generic.” | Generic có thể nằm ở factory method hoặc `FunctionRegistration` |
| “`@Bean Object` trả đúng instance thì catalog luôn suy type.” | Declared type quá chung có thể làm mất nguồn metadata |
| “Cast `Function<Object,Object>` sang typed Function sửa conversion.” | Cast không gắn type arguments vào registration |
| “FunctionCatalog lookup không null nghĩa input JSON sẽ đúng POJO.” | Lookup chỉ chọn function; conversion là bước khác |
| “`contentType=application/json` đủ để biết target class.” | Còn cần declared generic type hoặc dynamic type an toàn |
| “`Flux.class` đủ thay `Flux<OrderEvent>`.” | Mất kiểu của phần tử |
| “Bật `-parameters` là lưu được generic Signature.” | Hai metadata khác nhau |
| “Spring Boot fat JAR luôn loại bỏ generic.” | Normal packaging không tự strip `Signature` |
| “Dùng Shadow/Shade chắc chắn mất generic.” | Phụ thuộc transformer/relocation/keep rules |
| “Nhìn thấy JDK proxy là nguyên nhân chắc chắn.” | Bean definition/target có thể còn metadata |
| “Thêm RuntimeHints sửa được `Function<Object,Object>`.” | Hints không xác định target type cho function |
| “Một JSON Map là bằng chứng generic bị mất.” | Native decoder hoặc schema có thể chủ động tạo Map |
| “Gọi `apply(new OrderEvent)` pass là test JSON conversion.” | Chưa đưa dữ liệu raw qua converter |
| “Lỗi reactive luôn xuất hiện khi `apply`.” | Có thể chỉ phát lỗi khi subscribe |
| “Thêm bean mới có thể chữa lỗi type.” | Có thể thay catalog/function selection, không sửa metadata |

## 28. Checklist trước khi đưa function vào production

### 28.1. Khai báo và đăng ký

- [ ] Function có generic input/output cụ thể và đúng với contract.
- [ ] Không dùng raw `Function`/`Object` trừ khi là thiết kế đa kiểu có chủ đích.
- [ ] `Message<T>` giữ payload type.
- [ ] `Flux<T>`, `Mono<T>`, `List<T>` giữ item type.
- [ ] Functional lambda registration có `FunctionRegistration.type(...)`.
- [ ] Named implementation có generic interface đủ rõ.
- [ ] AOP/FactoryBean không làm registry suy sai type.

### 28.2. Build/packaging

- [ ] Artifact deploy có đúng class và BOM/version.
- [ ] `Signature` có trong class file nếu reflection cần đến nó.
- [ ] Shading/obfuscation/minification được kiểm tra bằng packaged JAR.
- [ ] Có test sau packaging, không chỉ test trong IDE.
- [ ] Nếu native image, có AOT/reflection tests phù hợp.

### 28.3. Adapter

- [ ] Function definition/composition chọn đúng tên.
- [ ] HTTP request có Content-Type và JSON schema đúng.
- [ ] Stream binding/contentType/native decoding khớp với function input.
- [ ] Serverless event shape đã được xác định, phân biệt envelope và body.
- [ ] Có test raw bytes → POJO → output DTO.
- [ ] Lỗi parse/convert không gây side effect sai hoặc retry vô hạn payload hỏng.

## 29. Câu hỏi tự đánh giá

1. Type erasure và generic `Signature` khác nhau ở đâu?
2. Vì sao `@Bean Function<OrderEvent,OrderReceipt>` có thể cung cấp metadata dù JVM xử lý `Function.apply(Object)`?
3. Vì sao runtime class của lambda không phải nơi duy nhất để suy type?
4. `@Bean Function` raw tạo rủi ro gì cho `FunctionCatalog`?
5. Cast `Function<Object,Object>` thành typed Function có khôi phục metadata không?
6. `FunctionRegistration` giúp gì trong functional startup?
7. Khi nào dùng `FunctionTypeUtils.functionType(OrderEvent.class,OrderReceipt.class)`?
8. Vì sao `FunctionTypeUtils.functionType(Flux.class,Flux.class)` chưa đủ cho một stream typed?
9. `Message<OrderEvent>` khác `Message<?>` ở điểm nào?
10. `ResolvableType.forMethodReturnType` và `ResolvableType.forClass` đang đọc hai nguồn metadata khác nhau như thế nào?
11. Vì sao một class generic có type variable `T` chưa được bind không cho biết chắc input là OrderEvent?
12. Cần quan sát gì trước khi đổ lỗi cho AOP proxy?
13. `javap -v` cho biết điều gì mà `jar tf` không cho biết?
14. Spring Boot executable JAR thông thường có tự động strip `Signature` không?
15. Shading/obfuscation có thể ảnh hưởng generic bằng những con đường nào?
16. `-parameters` có cùng vai trò với `Signature` không?
17. Khi nào native image cần RuntimeHints thay vì sửa function type?
18. Tại sao `FunctionCatalog.lookup` thành công nhưng HTTP vẫn có thể nhận Map?
19. Làm sao xác định Map do SCF converter hay Kafka native deserializer tạo?
20. Vì sao một reactive function có thể báo ClassCastException muộn sau `subscribe`?
21. Composition có thể lỗi khi output của bước trước là `Object` như thế nào?
22. Vì sao test `apply(new OrderEvent(...))` chưa chứng minh JSON conversion?
23. Bạn sẽ tổ chức smoke test trên packaged JVM artifact theo thứ tự nào?
24. Trong trường hợp JVM packaged chạy đúng nhưng native image lỗi, những nguồn bằng chứng nào cần so?

## 30. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — FunctionCatalog wrapper, composition, type conversion và các chữ ký imperative/reactive.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — sự khác nhau giữa `@Bean` và functional registration; `FunctionRegistration`, `FunctionTypeUtils`, khám phá và kiểm thử.
- [Spring Cloud Function — FunctionTypeUtils source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/FunctionTypeUtils.java) — cơ chế suy type; cần đối chiếu tag đúng dependency dự án.
- [Spring Cloud Function — BeanFactoryAwareFunctionRegistry source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/BeanFactoryAwareFunctionRegistry.java) — cách framework khai thác bean definition và đăng ký function.
- [Spring Framework — ResolvableType](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html) — truy vấn kiểu method, class và generic hierarchy.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html) — cách AOT phân tích bean và yêu cầu reflection/runtime hints.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — mô hình binding function và transport.
- [Spring Cloud Stream — Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/content-type-negotiation.html) — media type và message conversion.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` cho pipeline reactive.
- [Java Virtual Machine Specification — Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9) — generic signatures trong class-file format.

Các ví dụ dùng Java 17+ và các API của Spring Cloud Function/Spring Cloud Stream. Một số API functional startup, Spring AOT, web mapping và binder thay đổi theo BOM/phiên bản; cần xác nhận bằng dependency và artifact đang deploy. Những ví dụ về `javap`, JAR và test là hướng dẫn để thực hiện trong bước kiểm thử phù hợp, không phải lệnh đã được chạy trong bài này.

**Ghi nhớ:** Khi Spring Cloud Function có tên hàm nhưng không nhận đúng `OrderEvent` hoặc mất kiểu output, hãy kiểm tra **khai báo generic ở `@Bean`/class và metadata của `FunctionRegistration`** trước khi nghi Spring Boot JAR. Java type erasure vẫn cho phép compiler lưu `Signature` ở khai báo phù hợp; một lambda hoặc proxy runtime class không phải toàn bộ câu chuyện. Nếu nghi build làm mất kiểu, so bytecode trước và sau packaging bằng `javap`; nếu chỉ lỗi native, xem AOT reflection hints; nếu Map đến từ broker, xem native deserializer. Cuối cùng, xác minh riêng **catalog tìm được hàm** và **adapter chuyển raw JSON thành đúng POJO**, bằng kiểm thử trên chính artifact triển khai.
