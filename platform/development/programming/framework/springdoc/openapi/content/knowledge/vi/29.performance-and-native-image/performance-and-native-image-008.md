# AOT, reflection và các kiểu chỉ xuất hiện trong siêu dữ liệu

Springdoc-openapi tạo tài liệu bằng cách đọc controller, DTO, cấu hình Spring và các annotation OpenAPI. Trên JVM thông thường, thư viện có thể dùng reflection để khám phá class, field, method và annotation khi ứng dụng chạy. Khi biên dịch GraalVM Native Image, chương trình được phân tích trước lúc chạy; những truy cập động mà bộ phân tích không suy ra được cần có reachability metadata.

Một trường hợp dễ bỏ sót là kiểu Java chỉ được nhắc trong annotation như `@Schema(implementation = ApiError.class)`, trong `@ApiResponse`, trong một schema được tham chiếu gián tiếp hoặc trong code gọi client bằng `bodyToMono(ApiError.class)`. Kiểu đó có thể không xuất hiện trong tham số hay kiểu trả về của controller. Spring AOT thường tự suy ra reflection hints từ kiểu request/response rõ ràng trên `@RestController`, nhưng không nên giả định mọi kiểu được nhắc trong metadata đều được đăng ký đủ cho schema introspection và JSON binding.

Bài học này giải thích cách phân biệt reachability của class với quyền truy cập reflection vào member, cách bổ sung hints cho DTO chỉ xuất hiện trong metadata, cách kiểm tra hints và cách chạy thử OpenAPI endpoint trên native executable.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao native image cần reachability metadata cho reflection và tài nguyên.
- Phân biệt kiểu xuất hiện trong chữ ký controller với kiểu chỉ xuất hiện trong OpenAPI annotation hoặc generic.
- Nhận diện trường hợp Spring AOT có thể tự suy ra binding hints.
- Dùng `@RegisterReflectionForBinding` cho DTO cần serialize/deserialize nhưng AOT không suy ra được.
- Dùng `RuntimeHintsRegistrar` và `@ImportRuntimeHints` khi cần hint tùy chỉnh.
- Phân biệt reflection hints cho JSON binding với Java Object Serialization.
- Giữ lại lớp cấu hình chỉ chứa `@OpenAPIDefinition` hoặc `@SecurityScheme`.
- Kiểm tra hints bằng `RuntimeHintsPredicates` và tracing agent.
- Xác minh `/v3/api-docs`, Swagger UI và các response JSON trên native executable.
- Thiết kế pipeline CI để phát hiện lỗi chỉ xuất hiện trong native image.

## 1. Vì sao AOT cần metadata?

Trên JVM HotSpot, ứng dụng có thể nạp class và dùng reflection để tìm method, field hoặc constructor khi đang chạy. GraalVM Native Image áp dụng mô hình closed-world: bộ dựng phân tích các đường đi có thể tới từ entry point và chỉ đưa các thành phần được xác định là cần thiết vào executable.

Một đoạn code gọi trực tiếp `new ProductResponse(...)` và truy cập method tường minh thường dễ được phân tích tĩnh. Nhưng nếu thư viện dùng `Class.forName`, `Class.getDeclaredFields`, `Method.invoke`, Jackson introspection hoặc tên class được quyết định từ cấu hình, bộ dựng có thể không biết trước thành phần nào sẽ được truy cập.

Reachability metadata cho Native Image khai báo những truy cập động cần giữ lại. Các nhóm phổ biến gồm:

| Nhóm metadata | Dùng khi |
|---|---|
| Reflection | Khám phá class, constructor, method, field hoặc record component |
| Resources | Đọc file trong classpath theo tên hoặc pattern |
| Java serialization | Dùng `ObjectInputStream`/`ObjectOutputStream` |
| JDK proxies | Tạo proxy động từ danh sách interface |
| JNI | Mã native truy cập class/member Java |

Spring AOT tạo source code, bytecode cho một số proxy và `RuntimeHints`. Native Image dùng các hint đó cùng phân tích tĩnh để xây dựng executable.

### Class có mặt chưa chắc member dùng reflection đã sẵn sàng

Cần phân biệt hai việc:

1. Class được giữ trong native image và có thể được tham chiếu.
2. Constructor, field, property, method hoặc record component của class được đăng ký cho đúng kiểu truy cập động.

Một class có thể còn tồn tại nhưng việc gọi `getDeclaredFields()` hoặc `Method.invoke()` vẫn thất bại nếu metadata không khai báo quyền truy cập tương ứng. Vì vậy, chỉ thấy class trong binary hoặc thấy annotation chứa `SomeDto.class` chưa chứng minh JSON binding sẽ hoạt động.

## 2. Spring AOT tự suy ra những kiểu nào?

Spring Framework thực hiện AOT processing trên `ApplicationContext` ở thời điểm build. Trong quá trình này, Spring phân tích bean definitions, controller mappings và các cấu trúc có thể xác định từ classpath.

Một số trường hợp Spring tự đăng ký reflection hints:

- Kiểu tham số của method `@RequestBody`.
- Kiểu trả về của method `@RestController` hoặc `@Controller` khi Spring nhận diện nó sẽ được serialize, thường là JSON.
- Kiểu cấu hình `@ConfigurationProperties` và các kiểu lồng nhau được khai báo đúng.
- Các thành phần Spring và thư viện đã cung cấp runtime hints tương ứng.

Ví dụ kiểu xuất hiện trực tiếp trong chữ ký controller:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    ProductResponse create(
            @RequestBody CreateProductRequest request) {
        // ...
    }
}
~~~

Spring có thể nhìn thấy `CreateProductRequest` là kiểu request và `ProductResponse` là kiểu response trong quá trình AOT. Các reflection hints cần thiết cho data binding thường được suy ra tự động.

Điều này không có nghĩa mọi DTO trong ứng dụng đều tự động được đăng ký. Kiểu được chọn từ tên class lúc chạy, kiểu nằm trong `Object`, kiểu chỉ được tạo qua client, hoặc kiểu chỉ được nhắc trong annotation có thể nằm ngoài những gì Spring suy ra từ chữ ký handler.

## 3. Kiểu chỉ xuất hiện trong OpenAPI metadata

Springdoc đọc annotation OpenAPI để xây dựng schema. Ví dụ:

~~~java
@Operation(
    operationId = "createOrder",
    responses = {
        @ApiResponse(
            responseCode = "201",
            description = "Đơn hàng đã được tạo"
        ),
        @ApiResponse(
            responseCode = "422",
            description = "Dữ liệu đơn hàng không hợp lệ",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    }
)
@PostMapping("/orders")
OrderResponse createOrder(
        @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

`ApiError` chỉ xuất hiện trong annotation; nó không nằm trong kiểu tham số hay kiểu trả về của method. Springdoc cần đọc class này để tạo schema cho response lỗi. Nếu ứng dụng cũng serialize `ApiError` ở runtime qua một handler trả về `Object`, `ResponseEntity<?>` hoặc kiểu tổng quát, AOT có thể không suy ra đầy đủ hints cho JSON binding.

Các vị trí thường tạo ra kiểu metadata-only:

- `@Schema(implementation = SomeDto.class)`.
- `@ApiResponse` và `@Content(schema = ...)`.
- `@Parameter` hoặc annotation khai báo kiểu bổ sung.
- Schema dùng qua `@OpenAPIDefinition`, customizer hoặc cấu hình Java.
- Lớp response lỗi được dựng trong `@ControllerAdvice` nhưng handler khai báo kiểu trả về quá tổng quát.
- Kiểu được truyền vào `WebClient`/`RestClient` trong thân method thay vì xuất hiện trong chữ ký bean.
- Kiểu được tải theo tên class hoặc được chọn bởi cấu hình/plugin.

Không phải mọi kiểu trong OpenAPI metadata đều cần JSON binding hints. Hãy xác định kiểu đó chỉ phục vụ schema generation hay còn được serialize/deserialize trong runtime:

| Vai trò của kiểu | Nhu cầu chính |
|---|---|
| Chỉ để Springdoc đọc annotation/property nhằm tạo schema | Reflection introspection cho đúng member Springdoc cần đọc |
| Là body JSON được Jackson serialize/deserialize | Reflection/binding hints cho constructor, property, field hoặc record component |
| Được tạo hoặc gọi bằng reflection tùy runtime | Hints cho đúng constructor/method/field được truy cập |
| Là class của OpenAPI config | Phải là bean/configuration được AOT phát hiện |

Một class literal trong annotation có thể tạo tham chiếu tới class, nhưng không nên coi đó là thay thế cho binding hints. Kiểm tra AOT output và native runtime để xác nhận.

## 4. Đăng ký DTO bằng @RegisterReflectionForBinding

Khi DTO cần serialize hoặc deserialize JSON nhưng không thể được Spring suy ra từ chữ ký controller, có thể dùng `@RegisterReflectionForBinding`.

Ví dụ DTO lỗi và kiểu lồng nhau:

~~~java
import java.util.List;

public record ApiError(
    String code,
    String message,
    List<FieldViolation> violations
) {
}

public record FieldViolation(
    String field,
    String reason
) {
}
~~~

Đăng ký các kiểu cần binding trên một Spring configuration:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    ApiError.class
})
class ApiNativeBindingConfiguration {
}
~~~

Hint cho binding của `ApiError` cũng bao gồm các kiểu được tham chiếu qua property và record component, chẳng hạn `FieldViolation`. Có thể khai báo tường minh thêm kiểu lồng nhau nếu muốn làm rõ phạm vi hoặc nếu kiểu đó được dùng độc lập ở nơi khác.

Annotation có thể đặt trên một bean ở cấp class hoặc trực tiếp trên method, field hay constructor phù hợp với vị trí cần hint. Đặt gần component sử dụng kiểu sẽ giúp người bảo trì hiểu vì sao hint tồn tại.

### Khi nào nên dùng?

Dùng `@RegisterReflectionForBinding` khi:

- DTO được truyền cho `WebClient`/`RestClient` và không nằm trong chữ ký method controller.
- DTO được deserialize từ response bên ngoài qua kiểu generic hoặc `Object`.
- DTO được serialize trong exception handler có kiểu trả về tổng quát.
- DTO chỉ được chọn qua metadata nhưng thực tế cũng được Jackson dùng để tạo JSON.

Nếu class chỉ phục vụ Springdoc đọc metadata và không được serialize/deserialize, không tự động đăng ký toàn bộ binding cho mọi model. Hãy xác định chính xác member cần introspection; dùng hints hẹp phù hợp với thao tác mà Springdoc thực hiện.

## 5. Lớp @OpenAPIDefinition phải được AOT giữ lại

Springdoc có ghi chú riêng về native image: nếu đặt `@OpenAPIDefinition` hoặc `@SecurityScheme` trên một class không có implementation/bean configuration, class đó có thể biến mất khi biên dịch native. Đặt annotation trên một class `@Configuration`:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0",
        description = "API quản lý đơn hàng"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiConfiguration {
}
~~~

Đừng tạo một class chỉ chứa annotation rồi để nó nằm ngoài component scan. Với native image, cấu hình cần tham gia `ApplicationContext` để Spring AOT có thể xử lý.

## 6. RuntimeHintsRegistrar cho trường hợp tùy chỉnh

Khi annotation tiện ích không diễn tả được cách truy cập, có thể tạo `RuntimeHintsRegistrar`. Đây là API của Spring để khai báo reflection, resource, Java serialization và JDK proxy hints.

Ví dụ đăng ký một method được gọi bằng reflection và một resource:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class ApiRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        Method method = ReflectionUtils.findMethod(
            ApiSchemaIntrospector.class,
            "describe",
            Class.class
        );

        if (method != null) {
            hints.reflection().registerMethod(
                method,
                ExecutableMode.INVOKE
            );
        }

        hints.resources().registerPattern(
            "openapi/examples/*.json"
        );
    }
}
~~~

Kích hoạt registrar bằng `@ImportRuntimeHints`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApiRuntimeHints.class)
class ApiNativeHintsConfiguration {
}
~~~

Đây là ví dụ minh họa cho một method introspection tùy chỉnh và resource mẫu. Trong ứng dụng thực tế, thay tên class/method và pattern bằng tài nguyên được dùng. Không đăng ký resource hoặc method chỉ vì chúng có thể hữu ích; chỉ thêm những truy cập đã được xác định.

### Hints cho class/member được đọc bằng reflection

Nếu một thư viện đọc field, constructor hoặc method của DTO mà `@RegisterReflectionForBinding` không đáp ứng đúng nhu cầu, có thể dùng `hints.reflection().registerType(...)` với các `MemberCategory` phù hợp. Chọn category theo lỗi thực tế:

- Hint cho việc introspection class/member khi cần khám phá member và metadata. Trong Spring Framework 7, introspection được thêm mặc định khi đăng ký reflection hint cho một type; các category `INTROSPECT_*` đã deprecated.
- `INVOKE_*` khi cần gọi constructor hoặc method.
- `ACCESS_DECLARED_FIELDS`/`ACCESS_PUBLIC_FIELDS` khi cần truy cập giá trị field trên Spring Framework 7. Các tên `DECLARED_FIELDS`/`PUBLIC_FIELDS` cũ đã deprecated.

Tên và khả năng của `MemberCategory` phụ thuộc phiên bản Spring Framework đi cùng Spring Boot. Kiểm tra API của BOM dự án và test hint thay vì sao chép category từ một phiên bản khác.

## 7. Phân biệt JSON binding với Java Serialization

Tên “serialization” có thể chỉ hai cơ chế khác nhau:

- JSON binding của Jackson hoặc HTTP message converter: cần reflection hints cho DTO, property, record component và constructor. Dùng `@RegisterReflectionForBinding` trong trường hợp Spring không suy ra được.
- Java Object Serialization qua `ObjectOutputStream`/`ObjectInputStream`: cần Java serialization metadata riêng.

Không đăng ký `registerJavaSerialization` chỉ vì endpoint trả JSON. Cũng không cho rằng `@RegisterReflectionForBinding` tự động hỗ trợ một class dùng Java `Serializable` qua object stream.

## 8. Reachability metadata JSON khi cần cấu hình tĩnh

Native Image có thể đọc `reachability-metadata.json` trong classpath, dưới thư mục `META-INF/native-image/...`. Ví dụ rút gọn:

~~~json
{
  "reflection": [
    {
      "type": "com.example.api.ApiError",
      "allDeclaredFields": true,
      "allPublicMethods": true,
      "allPublicConstructors": true
    }
  ]
}
~~~

Đường dẫn ví dụ:

~~~text
src/main/resources/
  META-INF/
    native-image/
      com.example/
        order-api-additional-hints/
          reachability-metadata.json
~~~

Spring Boot cũng sinh metadata trong thư mục riêng theo `groupId` và `artifactId`. Đặt file bổ sung ở thư mục không trùng với thư mục generated để tránh ghi đè kết quả AOT.

Metadata JSON hữu ích khi chia sẻ hints với một thư viện hoặc khi cần cấu hình tĩnh. Với hint thuộc ứng dụng Spring, ưu tiên API `RuntimeHints` để khai báo gần component sử dụng. Tránh bật toàn bộ field/method nếu chỉ cần một số member vì điều đó làm native image giữ nhiều phần tử hơn mức cần thiết.

## 9. Tài nguyên và proxy liên quan đến Swagger UI

Reflection không phải loại hint duy nhất cần kiểm tra:

- File OpenAPI YAML/JSON được tải từ classpath theo tên động cần resource hint.
- Swagger UI tùy biến có CSS, JavaScript hoặc file mẫu riêng cần được đóng gói và nhận diện.
- JDK dynamic proxy dùng trong tích hợp có thể cần proxy hints.
- Thư viện bên thứ ba cần reachability metadata riêng nếu chưa cung cấp hint.

Springdoc có hỗ trợ GraalVM native images, nhưng vẫn cần thử trên phiên bản Spring Boot/Springdoc thực tế. Nếu dùng starter chuẩn, nhiều hint cho chính thư viện đã được cung cấp; không tạo bản đăng ký trùng lặp theo suy đoán.

## 10. Kiểm tra hints bằng RuntimeHintsPredicates

Có thể kiểm tra registrar độc lập trước khi build native image:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class ApiRuntimeHintsTests {

    @Test
    void registersApiErrorReflectionHint() {
        RuntimeHints hints = new RuntimeHints();
        new ApiErrorRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onType(ApiError.class)
        ).accepts(hints);
    }
}

class ApiErrorRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        hints.reflection().registerType(
            ApiError.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );
    }
}
~~~

Ví dụ trên chỉ kiểm tra có reflection hint cho type. Nó không chứng minh mọi member Jackson cần đều đã được đăng ký. Với DTO dùng cho JSON binding, hãy kiểm tra hint do `@RegisterReflectionForBinding` tạo ra và tiếp tục chạy native integration test.

Đối với cấu hình dùng `@RegisterReflectionForBinding`, hãy kiểm tra hints được tạo ra trong quá trình AOT hoặc dùng test AOT phù hợp với Spring Boot version. `RuntimeHintsPredicates` có thể kiểm tra type, method, field, resource và proxy hints; nó không chứng minh endpoint OpenAPI thực sự hoạt động trong native executable.

## 11. Dùng tracing agent để tìm hint còn thiếu

GraalVM tracing agent quan sát các truy cập reflection, resource và proxy khi chạy trên JVM, sau đó ghi metadata để hỗ trợ native build.

Ví dụ chạy ứng dụng đã AOT xử lý với agent:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/order-api.jar
~~~

Sau khi ứng dụng khởi động:

1. Gọi `/v3/api-docs`.
2. Mở Swagger UI nếu ứng dụng phát hành giao diện.
3. Gọi operation có request DTO và response DTO.
4. Kích hoạt các response lỗi có schema được khai báo trong annotation.
5. Gọi những luồng `WebClient`/`RestClient` deserialize kiểu không xuất hiện trong chữ ký controller.
6. Dừng ứng dụng để agent ghi file metadata.

Agent chỉ ghi lại đường chạy đã được thực thi. Nếu không gọi một response lỗi hoặc một nhánh polymorphic, metadata của nhánh đó có thể không xuất hiện.

Khi chạy agent qua test suite, kết quả có thể chứa hint chỉ dành cho test framework. Dùng access filter và review file sinh ra trước khi đưa vào source. Không chép toàn bộ kết quả agent vào dự án mà không phân loại.

## 12. Bật chế độ kiểm tra reachability nghiêm ngặt

Các phiên bản GraalVM hiện hành có chế độ exact reachability metadata giúp phát hiện đăng ký thiếu sớm hơn. Có thể bật `--exact-reachability-metadata` ở native build; một số bản cho phép giới hạn theo package.

Khi chạy executable, chế độ báo cáo có thể đặt thành:

~~~text
-XX:MissingRegistrationReportingMode=Warn
~~~

`Warn` giúp ghi nhận nơi thiếu đăng ký để điều tra. Trong bài kiểm thử có kiểm soát, có thể dùng:

~~~text
-XX:MissingRegistrationReportingMode=Exit
~~~

`Exit` giúp test thất bại ngay cả khi code có khối `catch (Throwable)` vô tình nuốt lỗi đăng ký thiếu. Các cờ này phụ thuộc GraalVM version; kiểm tra tài liệu đúng distribution trước khi đưa vào build.

## 13. Kiểm tra OpenAPI và runtime trên native executable

JVM test thành công không đủ để kết luận native image đã có đầy đủ hints. Hãy chạy smoke test trên executable hoặc container native:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Kiểm tra ít nhất:

| Luồng | Điều cần xác minh |
|---|---|
| Tải OpenAPI JSON/YAML | Springdoc tạo được document và không lỗi reflection |
| Swagger UI | HTML, JavaScript, CSS và OpenAPI URL tải được |
| Controller request DTO | JSON được deserialize đúng |
| Controller response DTO | JSON được serialize đúng |
| Error response trong annotation | Schema có mặt và response runtime có cấu trúc tương ứng |
| DTO chỉ dùng qua WebClient/RestClient | Client deserialize được body |
| Record và DTO lồng nhau | Constructor/property/record component được truy cập đúng |
| Polymorphic DTO | Subtype được giữ và deserialize theo discriminator |
| Security metadata | Security scheme và requirement vẫn xuất hiện trong document |

Đối chiếu cả hai mặt: schema OpenAPI phải mô tả đúng body thực tế, và body runtime phải được serialize thành công. Một schema xuất hiện trong `/v3/api-docs` không chứng minh Jackson đã có đủ hints để xử lý kiểu tương ứng.

## 14. Những giới hạn AOT cần lưu ý

Spring AOT cần một mô hình bean có thể xác định ở build time. Một số hành vi runtime linh động không phù hợp với closed-world assumption:

- Classpath và tập dependency được cố định lúc build.
- Bean definitions không thể thay đổi tùy ý sau khi native image đã được tạo.
- Profile và điều kiện tạo bean như `@ConditionalOnProperty` được quyết định trong AOT build.
- Đăng ký singleton trực tiếp qua `registerSingleton` có thể không được AOT xử lý như bean definition thông thường.
- Classpath scanning không thể dựa vào việc quét classpath động ở native runtime.

Nếu API group, controller hoặc OpenAPI configuration phụ thuộc profile, hãy chọn profile khi AOT build và kiểm tra đúng cấu hình đó. Không kỳ vọng đổi một property runtime sẽ tạo thêm controller hoặc bean mà native image chưa đóng gói.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `/v3/api-docs` lỗi reflection trong native image | DTO chỉ xuất hiện trong OpenAPI annotation chưa có hint phù hợp | Xác định class/member thiếu, thêm binding hoặc reflection hint |
| Swagger UI mất API title hoặc security scheme | Class chỉ mang `@OpenAPIDefinition`/`@SecurityScheme` không được AOT giữ lại | Đặt annotation trên `@Configuration` được scan |
| JVM serialize được nhưng native image lỗi | Jackson cần field/constructor/record hint chưa được đăng ký | Dùng `@RegisterReflectionForBinding` cho DTO không suy ra được |
| Chỉ lỗi ở response lỗi | DTO lỗi nằm trong `@ApiResponse` nhưng không có trong controller signature | Kiểm tra kiểu handler thực tế và đăng ký hint |
| Client HTTP không deserialize được DTO | Kiểu chỉ được truyền vào `bodyToMono` hoặc `body(...)` | Đăng ký binding hint cho DTO client |
| Một số property biến mất | Chỉ có class hint, thiếu quyền truy cập field/property cần thiết | Kiểm tra member-level hint và Jackson access strategy |
| Resource Swagger UI tùy biến bị 404 | File không được đưa vào native image | Đăng ký resource pattern và kiểm tra packaging |
| Native image thiếu proxy | Tạo JDK proxy động nhưng chưa có proxy hint | Đăng ký proxy interface cần thiết |
| Tracing agent không tìm ra lỗi | Test không chạy nhánh gây lỗi | Mở rộng scenario và test mọi response/media type |
| Hints quá rộng, binary tăng | Đăng ký toàn bộ field/method cho nhiều DTO | Thu hẹp member categories và chỉ giữ kiểu cần thiết |

## 16. Quy trình đưa AOT/native image vào CI

Một pipeline thực tế nên có các bước:

1. Chốt Spring Boot, Spring Framework, Springdoc và GraalVM version theo BOM.
2. Chạy test JVM và contract test `/v3/api-docs`.
3. Chạy AOT processing với profile production dự kiến.
4. Kiểm tra các DTO metadata-only và custom hints.
5. Chạy `RuntimeHintsPredicates` tests cho hints do ứng dụng sở hữu.
6. Build native executable hoặc native container.
7. Khởi động native executable trong CI.
8. Gọi `/v3/api-docs` và `/v3/api-docs.yaml`.
9. Gọi operation có DTO request/response và các response lỗi.
10. Kiểm tra luồng WebClient/RestClient, polymorphic DTO và resource tùy biến.
11. Chạy exact reachability metadata hoặc missing-registration reporting nếu GraalVM hỗ trợ.
12. Lưu native build log và kết quả smoke test làm bằng chứng release.

Với Maven, dự án Spring Boot đã cấu hình native profile thường có thể build image bằng:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Với Gradle, dự án đã cấu hình Buildpacks native image có thể dùng:

~~~bash
./gradlew bootBuildImage
~~~

Các lệnh này phụ thuộc cấu hình build, plugin và Docker/Buildpacks của dự án. Nếu chỉ tạo AOT processed JAR, hãy xác minh JAR chứa generated code và native-image hint files trước khi chuyển sang bước build image.

## 17. Bài thực hành tổng hợp

Tạo một API đơn hàng có DTO thông thường và DTO lỗi chỉ được khai báo trong OpenAPI metadata:

~~~java
public record CreateOrderRequest(
    String productCode,
    int quantity
) {
}

public record OrderResponse(
    String orderId,
    String status
) {
}

public record ApiError(
    String code,
    String message,
    List<FieldViolation> violations
) {
}

public record FieldViolation(
    String field,
    String reason
) {
}
~~~

Thực hiện:

1. Tạo controller nhận `CreateOrderRequest` và trả `OrderResponse`.
2. Dùng `@ApiResponse` cùng `@Schema(implementation = ApiError.class)` để mô tả response lỗi.
3. Đảm bảo handler lỗi runtime trả body có cấu trúc tương ứng.
4. Tạo `@Configuration` cho `@OpenAPIDefinition` và `@SecurityScheme`.
5. Đăng ký `ApiError` bằng `@RegisterReflectionForBinding` nếu kiểu đó không được suy ra từ chữ ký handler.
6. Kiểm tra hints cho các record component và kiểu lồng nhau.
7. Nếu có DTO dùng qua `WebClient`, thêm binding hint cho DTO đó.
8. Build AOT/native image theo Spring Boot version của dự án.
9. Gọi `/v3/api-docs` và xác minh schema `ApiError`.
10. Gửi request hợp lệ và không hợp lệ để kiểm tra JSON serialization/deserialization.
11. Chạy tracing agent qua các nhánh response và review metadata sinh ra.
12. Chạy native smoke test trong CI và lưu log.

### Tiêu chí hoàn thành

- [ ] Phân biệt được AOT processing và Native Image compilation.
- [ ] Giải thích được vì sao class reachable chưa đồng nghĩa member reflection đã được đăng ký.
- [ ] Xác định được DTO xuất hiện trong controller signature và DTO chỉ xuất hiện trong annotation.
- [ ] Biết khi nào Spring tự suy ra binding hints.
- [ ] Dùng `@RegisterReflectionForBinding` cho kiểu cần JSON binding mà AOT không suy ra được.
- [ ] Dùng `RuntimeHintsRegistrar` khi cần hint tùy chỉnh.
- [ ] Lớp `@OpenAPIDefinition`/`@SecurityScheme` là configuration bean được AOT xử lý.
- [ ] Phân biệt JSON binding với Java Object Serialization.
- [ ] Có test cho hints và native runtime.
- [ ] `/v3/api-docs` và Swagger UI hoạt động trên native executable.
- [ ] Các response lỗi và DTO lồng nhau được serialize đúng.
- [ ] CI kiểm tra missing-registration và lưu bằng chứng native smoke test.

## Tiếp tục học

Sau bài này, hãy kết hợp AOT/native image với contract testing, schema generation, serialization và kiểm thử hiệu năng. Khi thêm một kiểu mới vào annotation OpenAPI hoặc customizer, hãy xác định nó có được dùng trong runtime hay chỉ dùng để dựng tài liệu, sau đó đăng ký đúng loại hint và kiểm tra trên native executable.

## Tài liệu tham khảo

- [Springdoc FAQ – GraalVM support](https://springdoc.org/#is-graalvm-supported)
- [Spring Boot – Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot – Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Framework – Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [GraalVM – Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM – Dynamic Features of Java](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/)
