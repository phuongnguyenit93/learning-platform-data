# @RegisterReflectionForBinding cho kiểu dữ liệu được binding hoặc chuyển đổi

Khi chạy ứng dụng Spring Boot trên JVM, các thư viện như Spring MVC, Jackson hoặc cơ chế binding có thể dùng reflection để đọc constructor, field, property, getter/setter và record component của một kiểu dữ liệu. Với **GraalVM Native Image**, các truy cập reflection cần được nhận biết và đăng ký trong giai đoạn build. Nếu một DTO chỉ được sử dụng bên trong code của service hoặc thư viện, Spring AOT có thể không suy ra đầy đủ kiểu cần giữ lại.

**`@RegisterReflectionForBinding`** là annotation của Spring Framework dùng để đăng ký reflection hints phục vụ **data binding** hoặc **reflection-based serialization** cho các kiểu dữ liệu được chỉ định. Trong chương **Reflection** của module **`SPRING_BOOT_NATIVE_IMAGE`**, bài này giải thích cách chọn DTO, nơi đặt annotation, những thành viên và kiểu lồng nhau được đăng ký, cách kiểm chứng trên native executable, và các trường hợp cần dùng cơ chế hints khác.

> **Phạm vi phiên bản:** annotation có từ Spring Framework 6.0. Trong dòng Spring Framework 6.x, annotation dùng trên type hoặc method và cần chỉ định ít nhất một target class qua `value` hoặc `classes`. Hãy đối chiếu Javadoc đúng phiên bản Spring mà dự án đang dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một kiểu DTO chạy tốt trên JVM nhưng có thể thiếu reflection metadata trong Native Image.
- Sử dụng `@RegisterReflectionForBinding` trên configuration class hoặc Spring bean/method.
- Phân biệt thuộc tính `value` và `classes` của annotation.
- Hiểu phạm vi hints cho constructor, field, property, record component và các kiểu được dùng bắc cầu.
- Xác định khi nào nên dùng annotation cho JSON, HTTP body, binding hoặc serialization.
- Phân biệt binding hints với reflection hints tổng quát, resource hints và cấu hình converter.
- Kiểm thử để xác nhận kiểu dữ liệu thật sự được truy cập trong native executable.

## 2. Vì sao kiểu dữ liệu cần reflection hints?

Trên JVM, nhiều framework có thể khám phá cấu trúc class lúc chạy. Ví dụ, Jackson có thể đọc constructor hoặc property để deserialize JSON thành object; Spring có thể bind dữ liệu request vào DTO; thư viện serialization có thể đọc field hoặc record component.

Native Image thực hiện **reachability analysis** khi build. Nó cần biết những constructor, field, property hoặc thành phần khác nào sẽ được truy cập bằng reflection. Những thành phần chỉ được gọi gián tiếp qua reflection có thể không được giữ lại đầy đủ nếu không có metadata phù hợp.

Ví dụ DTO:

~~~java
package com.example.orders.api;

public class OrderRequest {
    private String customerId;
    private int quantity;

    public OrderRequest() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

Nếu thư viện binding dùng reflection để tạo object và gán property, Native Image cần các hints tương ứng. Nếu constructor hoặc property access không được đăng ký, lỗi có thể chỉ xuất hiện khi chạy executable native, dù cùng request đã thành công trên JVM.

**Không phải mọi DTO đều cần tự đăng ký annotation này.** Spring Boot và các tích hợp framework có thể tự nhận diện nhiều kiểu từ controller signature, configuration properties hoặc các cấu hình đã biết. Annotation hữu ích khi kiểu dữ liệu được sử dụng ở nơi AOT không suy ra được, chẳng hạn một DTO được truyền vào serializer trong thân phương thức service hoặc client.

## 3. Annotation làm gì?

Package:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
~~~

Annotation đăng ký các reflection hints phù hợp cho từng kiểu được chỉ định. Theo Javadoc Spring Framework, các nhóm thành phần được xử lý gồm:

- **Constructors:** constructor có thể cần để tạo object.
- **Fields:** field tham gia vào quá trình binding.
- **Properties:** thuộc tính Java được framework đọc/ghi, thường liên quan getter/setter hoặc property introspection.
- **Record components:** thành phần của Java record.
- **Các kiểu được dùng bắc cầu:** những kiểu xuất hiện trong property và record component của kiểu được đăng ký cũng được xử lý theo cơ chế binding hints.

Phạm vi này được thiết kế cho **binding và reflection-based serialization**. Nó không tương đương với việc mở toàn bộ reflection trên mọi method/private member của một class.

Spring nhận biết annotation trong quá trình AOT và chuyển nó thành Runtime Hints. Native Image build sử dụng các hints đã tổng hợp để giữ lại những thành phần cần thiết. Không nên giả định mỗi annotation luôn tạo một file `reflect-config.json` riêng; định dạng và vị trí metadata đầu ra phụ thuộc phiên bản Spring/GraalVM và cách tích hợp build.

Ví dụ cấu hình:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({OrderRequest.class, OrderResponse.class})
class OrderBindingHints {
}
~~~

Khi AOT xử lý configuration class này, Spring đăng ký hints cho `OrderRequest` và `OrderResponse` theo mục đích binding.

### `value` và `classes`

Hai thuộc tính là alias của nhau:

~~~java
@RegisterReflectionForBinding(OrderRequest.class)
~~~

Tương đương:

~~~java
@RegisterReflectionForBinding(classes = OrderRequest.class)
~~~

Có thể khai báo nhiều kiểu:

~~~java
@RegisterReflectionForBinding(
        classes = {OrderRequest.class, OrderResponse.class, CustomerDto.class})
~~~

Không cần khai báo đồng thời `value` và `classes` cho cùng một danh sách. Chọn một cách viết nhất quán trong dự án.

## 4. Đặt annotation ở đâu?

Spring Framework cho phép dùng annotation trên **type** hoặc **method**. Thông thường, hãy đặt annotation trên một configuration class để tập trung các DTO liên quan, hoặc trên bean/method thực sự sử dụng kiểu dữ liệu để thể hiện đúng phạm vi.

### 4.1. Đặt trên configuration class

Phù hợp khi nhiều DTO thuộc cùng một nhóm API hoặc một luồng binding:

~~~java
package com.example.orders.config;

import com.example.orders.api.OrderRequest;
import com.example.orders.api.OrderResponse;
import com.example.orders.api.OrderLineDto;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        OrderRequest.class,
        OrderResponse.class,
        OrderLineDto.class
})
class OrderReflectionConfiguration {
}
~~~

Configuration class phải được Spring đưa vào ApplicationContext trong quá trình AOT. Nếu class không được component scan, không được import và không được đăng ký bằng cách khác, chỉ đặt annotation trên một class không được xử lý sẽ không làm hints xuất hiện.

### 4.2. Đặt trên Spring bean

Phù hợp khi một service có một số kiểu dữ liệu cần binding/serialization:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Service;

@Service
@RegisterReflectionForBinding(PartnerResponse.class)
public class PartnerService {

    private final ObjectMapper objectMapper;

    public PartnerService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public PartnerResponse convert(String json) throws JsonProcessingException {
        // Ví dụ: chuyển JSON thành PartnerResponse bằng một serializer.
        return objectMapper.readValue(json, PartnerResponse.class);
    }
}
~~~

Annotation trên class giúp hints gắn với bean đó, dễ tìm khi điều tra service nào sử dụng DTO.

### 4.3. Đặt trên method

Nếu chỉ một phương thức cần kiểu dữ liệu, method-level annotation giúp thể hiện rõ vị trí sử dụng:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class PartnerClient {

    private final WebClient webClient;

    public PartnerClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(PartnerResponse.class)
    public Mono<PartnerResponse> fetchPartner() {
        return webClient.get()
                .uri("/partner")
                .retrieve()
                .bodyToMono(PartnerResponse.class);
    }
}
~~~

Đây là ví dụ minh họa việc dùng DTO trong thân method với WebClient. Spring AOT không phải lúc nào cũng suy luận được mọi kiểu được truyền vào API thư viện trong thân phương thức. Annotation chỉ ra kiểu cần binding reflection hints.

Method-level annotation phải nằm trên một phương thức thuộc **Spring bean được đóng góp vào context** để reflective processing của Spring xử lý. Không nên đặt annotation trên một helper class không được Spring quản lý rồi kỳ vọng AOT tự phát hiện.

### 4.4. Dùng trên test class

Annotation cũng có thể được đặt trên test class sử dụng Spring TestContext Framework để tải ApplicationContext:

~~~java
@SpringBootTest
@RegisterReflectionForBinding(OrderResponse.class)
class OrderNativeTests {

    @Test
    void shouldDeserializeOrder() {
        // Test binding/serialization với OrderResponse.
    }
}
~~~

Điều này hữu ích khi test cần binding một kiểu mà cấu hình production không tự suy ra. Tuy nhiên, hints được tạo trong test context không tự động thay thế việc đăng ký kiểu cần thiết cho **production application context**. Hãy đặt annotation ở nơi phù hợp với artifact bạn cần kiểm thử/phát hành.

## 5. Kiểu lồng nhau và record component

Giả sử một DTO chứa các kiểu khác:

~~~java
public record AddressDto(String city, String country) {
}

public record OrderLineDto(String sku, int quantity) {
}

public record CustomerDto(
        String customerId,
        AddressDto address) {
}

public record OrderResponse(
        String orderId,
        CustomerDto customer,
        List<OrderLineDto> lines) {
}
~~~

Khi đăng ký `OrderResponse`, binding hints registrar của Spring xử lý các thành phần record và những kiểu được dùng bắc cầu trong property/record component. Điều này giúp giảm nhu cầu liệt kê thủ công mọi nested type.

Tuy nhiên, không nên dựa vào suy đoán về toàn bộ kiểu generic hoặc mọi đường truy cập động của thư viện. Với collection, map, polymorphic type hoặc serializer có quy tắc riêng, hãy kiểm thử dữ liệu thực tế. Nếu một implementation/subtype được chọn bằng tên hoặc metadata động và không được AOT suy ra, đăng ký kiểu cần thiết một cách tường minh.

### Kiểu lồng nhau không đồng nghĩa mọi subtype đều tự được tìm thấy

Ví dụ:

~~~java
public interface PaymentMethod {
}

public class CardPayment implements PaymentMethod {
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String bankCode;
}

public record PaymentDto(PaymentMethod method) {
}
~~~

Nếu JSON chứa discriminator để serializer chọn `CardPayment` hoặc `BankTransfer`, việc chỉ đăng ký `PaymentDto` không nên được xem là bằng chứng mọi subtype đều đã được nhận diện. Hãy kiểm tra cách Jackson hoặc serializer cấu hình polymorphism và đăng ký các subtype cần thiết:

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        PaymentDto.class,
        CardPayment.class,
        BankTransfer.class
})
class PaymentBindingHints {
}
~~~

Đăng ký subtype không tự cấu hình polymorphic deserialization. Serializer vẫn cần cấu hình type information/allow-list phù hợp; hints chỉ cung cấp quyền truy cập reflection cần thiết cho Native Image.

## 6. Ví dụ thực tế: JSON dùng trong WebClient

Một trường hợp thường gặp là DTO được dùng trong service client, không xuất hiện trực tiếp trong signature của controller:

~~~java
public record InventoryItem(
        String sku,
        int availableQuantity) {
}
~~~

~~~java
@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(InventoryItem.class)
    public Mono<InventoryItem> getItem(String sku) {
        return webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryItem.class);
    }
}
~~~

`InventoryItem.class` được truyền vào API WebClient bên trong method. Annotation chỉ ra DTO cần hints cho binding/serialization. Nếu DTO có các kiểu nested cần xử lý, kiểm tra hints của các kiểu đó hoặc khai báo thêm theo yêu cầu.

### Ví dụ với Jackson trực tiếp

~~~java
@Component
public class ImportService {

    private final ObjectMapper objectMapper;

    public ImportService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @RegisterReflectionForBinding(ImportRecord.class)
    public ImportRecord read(String json) throws JsonProcessingException {
        return objectMapper.readValue(json, ImportRecord.class);
    }
}
~~~

Đây là một ví dụ reflection-based deserialization. Nếu serializer dùng constructor, property hoặc record metadata để tạo object, hints binding là đúng loại hỗ trợ cần xem xét. Các cấu hình Jackson như module Java Time, naming strategy, custom serializer/deserializer hoặc polymorphic typing vẫn phải được cấu hình riêng.

## 7. Ví dụ với Spring MVC và data binding

Một controller có thể nhận DTO trực tiếp:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping
    public void create(@RequestBody OrderRequest request) {
        // ...
    }
}
~~~

Spring AOT và các tích hợp framework có thể suy ra nhiều kiểu từ controller mapping, handler method và cấu hình được phân tích. Vì thế, **không nên tự động gắn annotation lên tất cả request/response DTO** khi framework đã đăng ký hints cho chúng.

Annotation hữu ích hơn với kiểu được sử dụng gián tiếp, ví dụ:

- DTO truyền vào `ObjectMapper` trong service.
- Kiểu được dùng trong WebClient/RestClient call nằm trong thân method.
- Kiểu dùng trong một thư viện binding/serialization mà Spring AOT không nhìn thấy qua bean/controller metadata.
- Kiểu test được dùng trong Spring TestContext nhưng không nằm trong signature mà AOT tự nhận diện.

Nếu đã đăng ký hints mà controller vẫn lỗi, cần kiểm tra đúng vấn đề: thiếu constructor/property reflection, thiếu resource, sai cấu hình Jackson, hay request binding logic có lỗi độc lập.

## 8. Annotation không làm những việc gì?

`@RegisterReflectionForBinding` chỉ đăng ký **reflection hints cho binding/serialization** của các kiểu được chỉ định. Nó không:

1. Tạo bean hoặc đăng ký DTO thành Spring component.
2. Thêm resource vào classpath hoặc native executable.
3. Tự cấu hình Jackson module, naming strategy, custom serializer/deserializer hay polymorphic type handling.
4. Đăng ký mọi method để gọi tùy ý bằng reflection.
5. Tạo JDK proxy hoặc CGLIB proxy.
6. Tạo hoặc đăng ký một `Converter` trong Spring `ConversionService`.
7. Sửa logic parse/validate dữ liệu hoặc bảo đảm JSON hợp lệ.

Ví dụ, nếu ứng dụng cần đọc `schemas/order.json` từ classpath, cần **resource hint** phù hợp. Annotation binding cho `OrderDto` không tự đưa file JSON schema vào executable.

Nếu một thư viện gọi một method bất kỳ qua reflection, không liên quan đến binding property, hãy cân nhắc reflection hints tổng quát qua `RuntimeHintsRegistrar` hoặc annotation `@RegisterReflection` ở phiên bản Spring Framework hỗ trợ. Chọn member categories phù hợp với thao tác thật sự.

Nếu muốn chuyển đổi một chuỗi thành kiểu dữ liệu tùy biến, cần cấu hình converter:

~~~java
public class CurrencyCodeConverter implements Converter<String, CurrencyCode> {
    @Override
    public CurrencyCode convert(String source) {
        return CurrencyCode.of(source);
    }
}
~~~

`@RegisterReflectionForBinding` không tự đăng ký converter trên vào `ConversionService`. Chỉ khi converter hoặc thư viện mà nó dùng cần reflection để binding/serialization thì mới đánh giá thêm hints.

## 9. So sánh với các cơ chế hints khác

| Cơ chế | Dùng khi | Ví dụ |
|---|---|---|
| `@RegisterReflectionForBinding` | DTO cần reflection cho binding hoặc reflection-based serialization | Jackson deserialize `OrderDto` |
| `@RegisterReflection` (Spring Framework 6.2+) | Cần đăng ký member categories reflection tổng quát | Gọi public methods hoặc fields theo reflection |
| `RuntimeHintsRegistrar` | Cần đăng ký hints bằng code, theo điều kiện hoặc cho thư viện | Đăng ký reflection/resource/proxy theo logic |
| Resource hints | Cần giữ file trên classpath | JSON schema, template, certificate, dictionary |
| Proxy hints | Native Image cần tạo proxy | JDK dynamic proxy cho interface |
| JNI hints | Mã native gọi qua JNI | Native library integration |

Ví dụ resource hint:

~~~java
public class AppRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("schemas/*.json");
    }
}
~~~

Đăng ký registrar bằng cơ chế Spring AOT phù hợp với dự án, chẳng hạn `@ImportRuntimeHints(AppRuntimeHints.class)` trên configuration class. Đây là cơ chế riêng, không cần thêm nếu chỉ đăng ký DTO binding và không có resource động cần giữ.

## 10. Phiên bản Spring Framework cần lưu ý

`@RegisterReflectionForBinding` có từ **Spring Framework 6.0**. Các ứng dụng Spring Boot 3.x thường dùng Spring Framework 6.x, nhưng phải đối chiếu phiên bản dependency thực tế của dự án.

Với Spring Framework 6.x:

- Annotation dùng trên type hoặc method.
- Chỉ định các kiểu cần đăng ký qua `value` hoặc `classes`.
- Javadoc 6.x yêu cầu ít nhất một target class được chỉ định.
- `value` là alias của `classes`.

Vì vậy, trong dự án Spring 6.x, đừng mặc định viết annotation không có đối số trên DTO rồi cho rằng chính DTO sẽ tự được đăng ký. Cách tương thích rõ ràng là:

~~~java
@RegisterReflectionForBinding(CustomerDto.class)
@Configuration(proxyBeanMethods = false)
class CustomerBindingConfiguration {
}
~~~

Các phiên bản Spring Framework mới hơn có thể mở rộng thuộc tính hoặc cách suy ra target type. Chỉ dùng API mới như `classNames` nếu phiên bản Spring Framework mà ứng dụng thực sự resolve hỗ trợ. Kiểm tra Javadoc theo đúng version thay vì sao chép cấu hình của nhánh mới vào dự án Spring 6.x.

## 11. Kiểm tra annotation đã được áp dụng chưa

### Bước 1: xác nhận dependency/version

Kiểm tra dependency Spring Framework thực tế:

~~~bash
# Maven
./mvnw dependency:tree -Dincludes=org.springframework:spring-core

# Gradle
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Đảm bảo project có `spring-core` chứa annotation và phiên bản đó tương thích với Spring Boot đang dùng. Nếu IDE không tìm thấy import, kiểm tra dependency management trước khi thay đổi package hoặc tự tạo annotation.

### Bước 2: đặt annotation trên phần Spring AOT có thể phát hiện

Đảm bảo configuration class được import/component scan hoặc bean/method được đưa vào ApplicationContext. Một annotation nằm trên class không được Spring xử lý sẽ không đóng góp hints vào AOT output.

### Bước 3: chạy AOT/native build

Với Maven (giả định đã có profile/plugin native):

~~~bash
./mvnw -Pnative package
~~~

Với Gradle:

~~~bash
./gradlew processAot
./gradlew nativeCompile
~~~

Tên profile/goal/task phụ thuộc cấu hình dự án. Đọc log để xác nhận Spring AOT và Native Image thực sự được chạy.

### Bước 4: kiểm thử thao tác binding trong native

Không chỉ kiểm tra build thành công. Hãy gọi đúng đường xử lý đã cần DTO:

- Deserialize JSON thành DTO.
- Serialize DTO thành JSON nếu ứng dụng có trả object.
- Kiểm tra constructor, property, nested DTO hoặc record component.
- Kiểm tra subtype nếu serializer dùng polymorphism.
- Kiểm tra resource riêng nếu serializer cần schema/template.

Native test có thể kiểm tra sớm nhưng vẫn nên chạy smoke/integration test trên executable ứng dụng cuối cùng.

### Bước 5: đọc lỗi theo loại truy cập

| Triệu chứng | Cần kiểm tra |
|---|---|
| Không tạo được DTO/constructor access bị chặn | Constructor hints và kiểu target đã đăng ký |
| Không đọc/ghi được property | Field/property hints, getter/setter và serializer configuration |
| Nested DTO bị lỗi | Các kiểu dùng trên property/record component đã được xử lý chưa |
| Polymorphic subtype không tạo được | Subtype hints và cấu hình discriminator/allow-list |
| Không tìm thấy file schema/template | Resource hints; annotation binding không đăng ký file |
| Converter không được chọn | Cấu hình `ConversionService`, converter bean và source/target type |
| Method reflection bị chặn nhưng không liên quan binding | Reflection hints tổng quát/member categories |

Thông báo lỗi Native Image thường cho biết kiểu hoặc member bị thiếu. Dùng thông tin đó để thu hẹp hints; không đăng ký reflection rộng cho toàn bộ package khi chưa có lý do.

## 12. Thực hành hoàn chỉnh

Giả sử service nhận JSON từ hệ thống đối tác và chuyển thành `PartnerOrder`:

~~~java
public record PartnerAddress(String city, String country) {
}

public record PartnerLine(String sku, int quantity) {
}

public record PartnerOrder(
        String orderId,
        PartnerAddress address,
        List<PartnerLine> lines) {
}
~~~

Service:

~~~java
@Service
public class PartnerOrderService {

    private final ObjectMapper objectMapper;

    public PartnerOrderService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @RegisterReflectionForBinding(PartnerOrder.class)
    public PartnerOrder parse(String payload) throws JsonProcessingException {
        return objectMapper.readValue(payload, PartnerOrder.class);
    }
}
~~~

**Bước 1:** Chạy test JVM với payload có đủ `address` và `lines`, xác nhận dữ liệu được deserialize đúng.

**Bước 2:** Build AOT/native theo Maven hoặc Gradle đã cấu hình. Kiểm tra annotation nằm trên Spring bean được xử lý.

**Bước 3:** Chạy native executable và thực hiện cùng thao tác parse. Nếu `PartnerAddress` hoặc `PartnerLine` không được nhận diện do cách serializer sử dụng generic type, đăng ký thêm các kiểu đó:

~~~java
@RegisterReflectionForBinding({
        PartnerOrder.class,
        PartnerAddress.class,
        PartnerLine.class
})
~~~

**Bước 4:** Nếu payload có subtype hoặc custom serializer, kiểm tra riêng reflection metadata và cấu hình Jackson. Annotation binding không tự giải quyết logic polymorphism.

**Bước 5:** Thử serialize ngược `PartnerOrder` thành JSON và so sánh cấu trúc với contract của hệ thống đối tác. Hints chỉ giúp Native Image cho phép truy cập; chúng không bảo đảm dữ liệu được chuyển đổi đúng nghiệp vụ.

## 13. Các lỗi thiết kế thường gặp

### Đăng ký DTO không được sử dụng trong context

Một class chỉ có annotation nhưng không được Spring đưa vào AOT processing có thể không tạo hints. Đặt annotation trên configuration/bean đã được import hoặc component scan.

### Đăng ký quá nhiều kiểu

Đưa toàn bộ model package vào một danh sách lớn có thể làm tăng reflection surface và khiến metadata khó quản lý. Bắt đầu từ kiểu thật sự được bind/serialize, sau đó bổ sung nested type khi có bằng chứng.

### Nhầm resource với reflection

Một JSON file hoặc template không phải DTO. Dùng resource hints cho file, binding hints cho kiểu Java.

### Nhầm converter với reflection

`Converter<S,T>` là logic chuyển đổi. Annotation không đăng ký converter và không sửa lỗi lựa chọn converter. Chỉ bổ sung reflection hints nếu implementation chuyển đổi dùng reflection-based binding.

### Cho rằng hints bảo đảm toàn bộ serializer tương thích

Jackson module, custom serializer, polymorphic type handling, naming policy và date/time format vẫn có quy tắc riêng. Kiểm thử trên native executable mới xác nhận được hành vi cuối.

## 14. Bài tập tự kiểm tra

**Câu 1.** `@RegisterReflectionForBinding` dùng để đăng ký gì?

**Gợi ý:** reflection hints phục vụ data binding hoặc reflection-based serialization cho các kiểu được chỉ định.

**Câu 2.** Annotation có thể đăng ký những thành phần nào của một DTO?

**Gợi ý:** constructor, field, property, record component và kiểu được dùng bắc cầu trên property/record component.

**Câu 3.** `value` và `classes` khác nhau thế nào?

**Gợi ý:** chúng là alias; chọn một trong hai để chỉ định danh sách target classes.

**Câu 4.** Vì sao DTO dùng trong thân method WebClient có thể cần annotation?

**Gợi ý:** AOT có thể không suy ra kiểu được truyền vào API thư viện từ code bên trong method; annotation chỉ rõ DTO cần binding hints.

**Câu 5.** Annotation có tự thêm file JSON schema vào native executable không?

**Gợi ý:** không. Cần resource hints nếu file được đọc từ classpath và không được Native Image tự nhận diện.

**Câu 6.** Annotation có tự đăng ký custom `Converter<String, CurrencyCode>` không?

**Gợi ý:** không. Converter phải được cấu hình trong Spring; binding hints chỉ giải quyết reflection cho kiểu dữ liệu khi cần.

**Câu 7.** Spring Framework 6.x có thể dùng annotation không chỉ định target class không?

**Gợi ý:** Javadoc 6.x yêu cầu chỉ định ít nhất một target qua `value` hoặc `classes`. Kiểm tra API của version cụ thể trước khi dùng cú pháp của Spring 7.

## 15. Checklist áp dụng trong dự án

- [ ] Xác định chính xác DTO/record nào được binding hoặc reflection-based serialization.
- [ ] Kiểm tra Spring Boot/Spring Framework version và package annotation.
- [ ] Đặt annotation trên configuration class hoặc Spring bean/method được AOT xử lý.
- [ ] Với Spring Framework 6.x, chỉ định target class qua `value` hoặc `classes`.
- [ ] Xác định nested types, collection element và subtype mà serializer thật sự sử dụng.
- [ ] Không đăng ký hàng loạt DTO nếu framework đã tự suy ra hints.
- [ ] Dùng resource hints cho file schema/template và reflection hints tổng quát cho method access không thuộc binding.
- [ ] Đăng ký converter riêng; không xem annotation là cơ chế cấu hình `ConversionService`.
- [ ] Chạy JVM tests và AOT/native build.
- [ ] Chạy native test hoặc native executable với payload thực tế, gồm nested DTO/record.
- [ ] Đọc diagnostic và bổ sung hints theo đúng kiểu/member bị thiếu.

## 16. Tài liệu tham khảo

- [Spring Framework 6.2 Javadoc — RegisterReflectionForBinding](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html): target, `value`/`classes`, constructor/field/property/record-component hints và kiểu được dùng bắc cầu.
- [Spring Framework Reference — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): cách Spring AOT phát hiện reflective usage, `@Reflective`, Runtime Hints và các annotation đăng ký reflection.
- [Spring Framework 6.2 Javadoc — RegisterReflection](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflection.html): reflection hints tổng quát và member categories.

**Ghi nhớ:** `@RegisterReflectionForBinding` giúp Spring AOT đăng ký đúng nhóm reflection hints cho DTO hoặc kiểu dữ liệu cần binding/serialization. Đặt annotation ở configuration hoặc Spring bean được AOT xử lý, chỉ định target class rõ ràng trên Spring 6.x, rồi kiểm thử payload trên native executable. Hãy dùng resource hints, reflection hints tổng quát và converter configuration cho những nhu cầu khác; annotation binding không thay thế các cơ chế đó.
