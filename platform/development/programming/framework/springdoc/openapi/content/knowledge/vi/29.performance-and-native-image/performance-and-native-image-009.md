# Runtime hints cho phần mở rộng tùy chỉnh khi cần thiết

springdoc-openapi có thể chạy trong ứng dụng Spring Boot được biên dịch thành GraalVM Native Image. Tuy nhiên, khi ứng dụng có phần mở rộng OpenAPI tự viết, chẳng hạn OpenApiCustomizer, OperationCustomizer hoặc ModelConverter, một số thao tác chỉ xảy ra lúc chạy có thể không được Spring AOT suy ra đầy đủ.

Native Image cần biết trước những thành phần nào sẽ được truy cập bằng reflection, resource nào cần đóng gói, kiểu nào được dùng với Java serialization và JDK proxy nào cần tồn tại. Thông tin này được gọi là runtime hints.

Không phải mọi ứng dụng dùng springdoc đều cần tự khai báo hints. Spring AOT đã tự suy ra nhiều trường hợp thông thường, bao gồm các kiểu request/response của controller. Chỉ bổ sung hints khi extension có hành vi mà AOT không thể suy ra và lỗi hoặc phép kiểm tra cho thấy thiếu metadata.

Bài này giải thích cách nhận diện nhu cầu, dùng RuntimeHintsRegistrar và @ImportRuntimeHints, đăng ký reflection/resource/proxy hints, kiểm thử hints và xác minh OpenAPI endpoint trong native executable.

## 1. Vì sao Native Image cần runtime hints?

Ứng dụng chạy trên JVM thông thường có thể sử dụng reflection, đọc resource từ classpath hoặc tạo JDK proxy trong lúc chạy. JVM có class metadata và classpath đầy đủ để những thao tác đó hoạt động.

Native Image được phân tích và biên dịch trước khi chạy. Quá trình build cần biết những thành phần nào phải được giữ lại và cho phép truy cập. Một class hoặc method chỉ được tìm theo tên lúc runtime có thể không được giữ lại nếu không có hint tương ứng. Resource không được khai báo có thể không được đóng gói vào executable.

Ví dụ, extension có thể gọi:

~~~java
Class.forName("com.example.openapi.CustomSchemaProvider");
~~~

Hoặc đọc một file:

~~~java
new ClassPathResource("openapi/extensions/order-schema.yaml");
~~~

Trên JVM, các thao tác này có thể chạy bình thường. Trong native executable, class hoặc resource có thể không tồn tại theo cách extension mong đợi nếu AOT không phát hiện được.

Runtime hints bổ sung thông tin cho quá trình AOT/native-image build. Chúng không thay đổi logic nghiệp vụ hoặc tạo ra class/resource mới; chúng khai báo những truy cập động mà ứng dụng cần.

## 2. Spring AOT đã tự suy ra những gì?

Spring AOT phân tích ApplicationContext và các bean definition ở build time. Framework có thể tạo nhiều hint dựa trên cách ứng dụng được khai báo.

Một số trường hợp thường được suy ra tự động:

- Kiểu request body và response body được khai báo trong method của controller.
- DTO được Spring MVC/WebFlux phát hiện từ @RestController.
- Các bean và annotation Spring được xử lý bởi AOT processor.
- Một số proxy do Spring quản lý và tạo ở build time.
- Những resource hoặc reflection access mà thư viện đã cung cấp hint sẵn.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

Spring AOT có thể nhận diện CreateOrderRequest và OrderResponse trong contract của controller, từ đó tạo các hint cần thiết cho binding/serialization.

Vì vậy, không nên đăng ký reflection cho mọi DTO chỉ vì ứng dụng được build thành native image. Hãy bắt đầu bằng cách kiểm tra phần nào AOT đã nhận diện và chỉ bổ sung hint cho phần mở rộng còn thiếu.

## 3. Khi nào custom extension cần hint?

Một custom extension có thể cần hint nếu nó sử dụng:

- Reflection để tìm class, field, constructor hoặc method theo tên.
- Resource được chọn bằng tên hoặc pattern chỉ biết lúc runtime.
- Jackson hoặc cơ chế binding để serialize/deserialize một kiểu không xuất hiện trong signature của controller.
- JDK dynamic proxy được tạo bằng Proxy hoặc thư viện khác ngoài proxy do Spring AOT quản lý.
- Java Object Serialization qua ObjectInputStream/ObjectOutputStream.
- Thư viện bên thứ ba chưa cung cấp reachability metadata cần thiết.

Ví dụ, một ModelConverter tự quét field bằng reflection có thể cần reflection hints. Một OpenApiCustomizer tải schema fragment từ classpath theo tên có thể cần resource hints. Một extension gọi WebClient để lấy metadata và deserialize response vào DTO không xuất hiện trong controller có thể cần binding hints cho DTO đó.

Một customizer chỉ sửa title hoặc thêm một extension string vào OpenAPI model bằng các API thông thường thường không cần runtime hints riêng.

## 4. Phân biệt reflection, JSON binding và Java serialization

Ba trường hợp này dễ bị nhầm:

| Trường hợp | Ví dụ | Cách khai báo thường dùng |
|---|---|---|
| Reflection | Tìm method hoặc field theo tên | RuntimeHintsRegistrar hoặc @RegisterReflection |
| JSON binding | Jackson serialize/deserialize DTO | @RegisterReflectionForBinding khi AOT không suy ra |
| Java serialization | ObjectOutputStream ghi object Serializable | Hint cho Java serialization qua RuntimeHints |

JSON binding không phải Java serialization. Jackson thường dùng reflection hoặc metadata của bean/record để đọc và ghi JSON. Không đăng ký Java serialization hint chỉ vì ứng dụng trả JSON.

Nếu một DTO xuất hiện trong request/response của controller, Spring thường đã suy ra hint. Nếu DTO chỉ được dùng trong lời gọi WebClient hoặc RestClient ở bên trong service, AOT có thể không nhìn thấy kiểu đó qua signature của controller; khi đó @RegisterReflectionForBinding là lựa chọn phù hợp.

## 5. Các nhóm RuntimeHints

Spring cung cấp RuntimeHints để tập hợp các yêu cầu runtime metadata:

| Nhóm | Mục đích | Ví dụ |
|---|---|---|
| Reflection hints | Cho phép truy cập class/member bằng reflection | Method, constructor, field |
| Resource hints | Đóng gói resource cần đọc lúc runtime | YAML, JSON, template, file cấu hình |
| Proxy hints | Đăng ký JDK dynamic proxy | Proxy cho một hoặc nhiều interface |
| Serialization hints | Hỗ trợ Java serialization | Kiểu Serializable được dùng với ObjectInputStream/ObjectOutputStream |

Các hints được đóng góp trong giai đoạn AOT và được chuyển thành metadata mà native-image compiler sử dụng.

Hãy đăng ký đúng nhóm tương ứng với hành vi. Thêm reflection hint không làm một resource bị thiếu xuất hiện trong image; resource hint cũng không cho phép gọi một private method bằng reflection.

## 6. Đăng ký RuntimeHintsRegistrar

RuntimeHintsRegistrar là extension point để đăng ký hints bằng Java code.

Một class triển khai interface này và ghi các yêu cầu vào đối tượng RuntimeHints được Spring truyền vào:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OpenApiExtensionHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
        RuntimeHints hints,
        ClassLoader classLoader
    ) {
        // Register only the runtime access required by the extension.
    }
}
~~~

Spring gọi registerHints trong quá trình AOT processing. Vì vậy, method này nên mô tả metadata tĩnh, có thể xác định ở build time.

Không dùng registerHints để gọi API từ xa, truy vấn database hoặc phụ thuộc request của người dùng. Runtime hints phải được quyết định trong build, trước khi native executable chạy.

## 7. Kích hoạt registrar bằng @ImportRuntimeHints

Có thể gắn @ImportRuntimeHints lên một Spring bean hoặc configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration
@ImportRuntimeHints(OpenApiExtensionHints.class)
class OpenApiNativeConfiguration {
}
~~~

Spring phát hiện registrar và gọi nó trong quá trình AOT. Hãy đặt annotation gần component cần hints nếu có thể, để metadata chỉ được đóng góp khi component tương ứng tham gia ApplicationContext.

Với custom OpenApiCustomizer, có thể gắn annotation trực tiếp trên bean:

~~~java
@Component
@ImportRuntimeHints(OpenApiExtensionHints.class)
class SchemaCatalogCustomizer implements OpenApiCustomizer {
    // ...
}
~~~

Cách này giúp người bảo trì nhìn thấy mối liên hệ giữa customizer và hints của nó.

## 8. Ví dụ: customizer đọc schema fragment từ classpath

Giả sử ứng dụng có extension tải nội dung hướng dẫn schema từ resource:

~~~text
src/main/resources/
  openapi/
    extensions/
      order-schema.yaml
      customer-schema.yaml
~~~

Customizer đọc resource trong lúc tạo tài liệu:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import io.swagger.v3.oas.models.OpenAPI;

@Component
class SchemaCatalogCustomizer implements OpenApiCustomizer {

    @Override
    public void customise(OpenAPI openApi) {
        ClassPathResource resource =
            new ClassPathResource("openapi/extensions/order-schema.yaml");

        try (var input = resource.getInputStream()) {
            String text = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            );
            openApi.addExtension("x-order-schema-notes", text);
        }
        catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot load order schema extension",
                ex
            );
        }
    }
}
~~~

Trong JVM, resource thường được tìm thấy trên classpath. Khi chạy native image, cần bảo đảm file được đóng gói vào executable.

Đăng ký resource pattern:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class SchemaCatalogHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
        RuntimeHints hints,
        ClassLoader classLoader
    ) {
        hints.resources().registerPattern(
            "openapi/extensions/*.yaml"
        );
    }
}
~~~

Kích hoạt hints:

~~~java
@Configuration
@ImportRuntimeHints(SchemaCatalogHints.class)
class SchemaCatalogNativeConfiguration {
}
~~~

Pattern phải khớp đường dẫn resource tương đối với classpath. Không thêm tiền tố classpath: vào pattern của registerPattern. Nếu extension chỉ đọc một file cố định, đăng ký chính xác file đó thay vì dùng wildcard rộng.

Ví dụ trên thêm nội dung resource vào extension x-order-schema-notes để minh họa việc đọc resource. Nếu cần đưa YAML thành Schema Object thực sự, hãy parse nội dung bằng parser phù hợp và kiểm thử cả parser đó trong native image.

## 9. Đăng ký reflection cho method được gọi động

Giả sử custom extension gọi một method theo reflection:

~~~java
public class SchemaDescriptionProvider {

    public static String orderDescription() {
        return "Schema mở rộng cho đơn hàng";
    }
}
~~~

Extension tìm và gọi method:

~~~java
import java.lang.reflect.Method;

import org.springframework.util.ReflectionUtils;

class SchemaDescriptionExtension {

    String description() {
        Method method = ReflectionUtils.findMethod(
            SchemaDescriptionProvider.class,
            "orderDescription"
        );

        if (method == null) {
            throw new IllegalStateException(
                "orderDescription method not found"
            );
        }

        return (String) ReflectionUtils.invokeMethod(method, null);
    }
}
~~~

Vì method được tìm và gọi qua reflection, native image cần biết method đó phải được giữ lại và cho phép invoke.

Có thể đăng ký method hint:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class SchemaDescriptionHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
        RuntimeHints hints,
        ClassLoader classLoader
    ) {
        Method method = ReflectionUtils.findMethod(
            SchemaDescriptionProvider.class,
            "orderDescription"
        );

        if (method == null) {
            throw new IllegalStateException(
                "Cannot find orderDescription"
            );
        }

        hints.reflection().registerMethod(
            method,
            ExecutableMode.INVOKE
        );
    }
}
~~~

Sau đó import registrar bằng @ImportRuntimeHints.

Nếu extension dùng reflection để liệt kê field, constructor hoặc toàn bộ method thay vì gọi một method đã biết, cần đăng ký các member category tương ứng. Không cấp quyền truy cập rộng hơn nhu cầu thực tế.

## 10. Đăng ký reflection cho kiểu dữ liệu

Nếu cần đăng ký nhiều member của một kiểu, RuntimeHints cho phép khai báo type và member category.

Ví dụ, extension cần gọi public constructor và public method:

~~~java
hints.reflection().registerType(
    CustomSchemaPlugin.class,
    typeHint -> typeHint.withMembers(
        MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
        MemberCategory.INVOKE_PUBLIC_METHODS
    )
);
~~~

Các MemberCategory xác định loại truy cập cần giữ lại. Tùy nhu cầu, có thể cần introspection, invocation hoặc truy cập field.

Không chọn mọi category chỉ để tránh lỗi. Hints rộng có thể làm native image lớn hơn, giảm lợi ích của việc loại bỏ code không dùng và che khuất dependency thực tế của extension.

Nếu kiểu được biết tại build time, ưu tiên dùng class literal thay vì tên class dạng String. Nếu class được chọn từ cấu hình hoặc plugin name, cần kiểm soát tập class hợp lệ và đăng ký từng kiểu có thể được sử dụng.

## 11. Dùng @RegisterReflectionForBinding cho DTO JSON

Spring Framework cung cấp @RegisterReflectionForBinding để khai báo reflection metadata cho các kiểu được serialize/deserialize nhưng không được AOT suy ra từ controller.

Ví dụ service gọi WebClient:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
class SchemaRegistryClient {

    private final WebClient webClient;

    SchemaRegistryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(SchemaCatalogResponse.class)
    SchemaCatalogResponse loadCatalog() {
        return webClient.get()
            .uri("/internal/schema-catalog")
            .retrieve()
            .bodyToMono(SchemaCatalogResponse.class)
            .block();
    }
}
~~~

Ví dụ minh họa kiểu response được deserialize trong method body, không xuất hiện trong signature của controller. Annotation đăng ký metadata cần thiết cho constructor, field, property và record component của kiểu đó; các kiểu được tham chiếu qua property cũng được xử lý theo quy tắc của annotation.

Nếu service dùng RestClient hoặc Jackson trực tiếp, cách tiếp cận tương tự có thể áp dụng. Hãy xác định kiểu thực sự được bind và gắn annotation ở bean hoặc method thích hợp.

## 12. DTO được controller sử dụng thường không cần đăng ký lặp lại

Nếu DTO xuất hiện trong method signature của controller, Spring AOT thường có thể suy ra binding hints:

~~~java
@RestController
@RequestMapping("/api/schema")
class SchemaController {

    @PostMapping
    SchemaCatalogResponse create(
        @RequestBody SchemaCatalogRequest request
    ) {
        // ...
    }
}
~~~

Không cần thêm @RegisterReflectionForBinding cho mọi DTO trong dự án chỉ vì ứng dụng được build native.

Nếu DTO vừa xuất hiện trong controller vừa được sử dụng trong một luồng phản xạ khác, hãy kiểm tra luồng thứ hai có cần hint bổ sung hay không. Một hint đã được suy ra cho Jackson binding không tự động bao phủ mọi thao tác reflection tùy chỉnh trên cùng class.

## 13. Resource hints cho file OpenAPI tùy chỉnh

Custom extension có thể đọc:

- Schema fragment YAML/JSON.
- Template mô tả API.
- File mapping tên operation.
- Danh sách tag hoặc ví dụ.
- File cấu hình riêng của plugin.
- Resource được chọn theo locale.

Đăng ký resource chính xác:

~~~java
hints.resources().registerPattern(
    "openapi/extensions/order-schema.yaml"
);
~~~

Hoặc đăng ký pattern cho nhóm file có quy ước:

~~~java
hints.resources().registerPattern(
    "openapi/extensions/*.yaml"
);
~~~

Nếu extension đọc file theo locale:

~~~java
hints.resources().registerPattern(
    "openapi/messages/*.properties"
);
~~~

Pattern phải bao phủ các resource thật sự được sử dụng trong native executable. Nếu resource được tạo sau khi build hoặc lấy từ filesystem bên ngoài, resource hint không đóng gói nó; khi đó cần cấu hình đường dẫn và cách phân phối file ở runtime.

## 14. JDK proxy hints

Một số extension dùng java.lang.reflect.Proxy hoặc thư viện tạo JDK dynamic proxy từ một hoặc nhiều interface.

Ví dụ:

~~~java
public interface SchemaProvider {
    String schemaName();
}
~~~

Nếu custom extension tự tạo proxy:

~~~java
Object proxy = Proxy.newProxyInstance(
    SchemaProvider.class.getClassLoader(),
    new Class<?>[] { SchemaProvider.class },
    invocationHandler
);
~~~

Native Image cần biết interface proxy có thể được tạo. Có thể đăng ký:

~~~java
hints.proxies().registerJdkProxy(
    SchemaProvider.class
);
~~~

Nếu proxy implement nhiều interface, đăng ký đúng tập interface theo thứ tự và cấu hình mà ứng dụng sử dụng.

Không nhầm JDK proxy với proxy do Spring AOP hoặc Spring bean infrastructure tạo. Spring AOT có thể tạo trước nhiều proxy do framework quản lý. Chỉ bổ sung proxy hint khi extension có dynamic proxy riêng và quá trình AOT không nhận diện được.

## 15. Java serialization khác với Jackson JSON

RuntimeHints cũng hỗ trợ Java serialization. Đây là cơ chế của ObjectInputStream và ObjectOutputStream, không phải định dạng JSON.

Nếu extension thực sự dùng Java serialization:

~~~java
hints.reflection().registerJavaSerialization(
    LegacySchemaDescriptor.class
);
~~~

Nếu extension dùng Jackson:

~~~java
objectMapper.readValue(
    json,
    SchemaCatalogResponse.class
);
~~~

thì cần binding/reflection hints phù hợp, thường là @RegisterReflectionForBinding khi AOT không suy ra được kiểu.

Không đăng ký Java serialization hint cho mọi DTO Jackson. Làm như vậy không giải quyết được thiếu metadata cho JSON binding và khiến cấu hình native image khó hiểu hơn.

## 16. Đặt hints gần extension cần chúng

Một cách tổ chức dễ bảo trì là để registrar cạnh customizer hoặc converter:

~~~text
openapi/
  SchemaCatalogCustomizer.java
  SchemaCatalogHints.java
  SchemaDescriptionProvider.java
  SchemaCatalogResponse.java
~~~

Customizer mô tả OpenAPI. Registrar mô tả các truy cập động mà customizer cần. DTO chỉ được đánh dấu binding khi không được Spring AOT tự nhận diện.

Có thể dùng nested static class cho registrar:

~~~java
@Component
@ImportRuntimeHints(SchemaCatalogCustomizer.SchemaHints.class)
class SchemaCatalogCustomizer implements OpenApiCustomizer {

    public static class SchemaHints implements RuntimeHintsRegistrar {
        @Override
        public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader
        ) {
            hints.resources().registerPattern(
                "openapi/extensions/*.yaml"
            );
        }
    }
}
~~~

Cách này giữ hints sát component. Nếu customizer không còn được đóng góp vào ApplicationContext, hints gắn với bean đó cũng không cần được đóng góp.

## 17. Dùng META-INF/spring/aot.factories khi cần đăng ký toàn cục

Ngoài @ImportRuntimeHints, có thể đăng ký RuntimeHintsRegistrar toàn cục qua resource META-INF/spring/aot.factories.

Nội dung file:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=\
com.example.openapi.OpenApiExtensionHints
~~~

Cách đăng ký này phù hợp khi hints thuộc về một thư viện hoặc module muốn đóng góp metadata mà không gắn annotation lên bean cụ thể.

Với ứng dụng thông thường, @ImportRuntimeHints thường dễ đọc và dễ theo dõi hơn. Không đăng ký cùng một registrar bằng nhiều cơ chế nếu không có lý do, để tránh cấu hình trùng và khó kiểm tra.

## 18. Dùng file GraalVM JSON hints tĩnh

Nếu cần cung cấp metadata tĩnh, có thể đặt file JSON trong resource tree:

~~~text
src/main/resources/
  META-INF/
    native-image/
      com.example/
        orders-additional-hints/
          reflect-config.json
          resource-config.json
~~~

Spring Boot AOT cũng sinh metadata dưới thư mục META-INF/native-image/{groupId}/{artifactId}. Vì vậy, đặt hint bổ sung trong một thư mục riêng không xung đột với vị trí output do build tạo ra.

Ví dụ resource-config.json:

~~~json
{
  "resources": {
    "includes": [
      {
        "pattern": "openapi/extensions/.*\\.yaml"
      }
    ]
  }
}
~~~

Ví dụ reflect-config.json có thể khai báo class và method cần truy cập theo định dạng GraalVM Native Image tương ứng với phiên bản đang dùng.

Ưu tiên RuntimeHintsRegistrar nếu muốn metadata được kiểm thử bằng Spring API và nằm cạnh component. Dùng JSON tĩnh khi cần chia sẻ metadata ở cấp thư viện hoặc khi một công cụ bên ngoài đã sinh ra cấu hình reachability phù hợp.

Không chỉnh sửa trực tiếp file hints do AOT tự sinh trong target hoặc build output. Những file đó được tạo lại ở mỗi build.

## 19. Lưu ý riêng cho @OpenAPIDefinition và @SecurityScheme

springdoc-openapi v2 FAQ có lưu ý về native image: nếu đặt @OpenAPIDefinition hoặc @SecurityScheme trên một class chỉ chứa annotation nhưng không được Spring đăng ký như configuration, class đó có thể bị loại khi native compile.

Hãy khai báo class cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0"
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

Ví dụ này cho Spring biết class là một configuration bean được đưa vào ApplicationContext. Không dùng RuntimeHintsRegistrar để cố giữ một class cấu hình chưa được đăng ký đúng cách.

Lưu ý này được nêu trong FAQ v2 của springdoc. Khi dùng major version khác, hãy kiểm tra FAQ và hướng dẫn native image tương ứng với phiên bản đó.

## 20. Custom ModelConverter có cần reflection hints không?

ModelConverter có thể được dùng để thay đổi cách swagger-core suy ra Schema Object từ Java type.

Nếu converter chỉ gọi API công khai trên AnnotatedType, Schema, ModelResolver và các kiểu đã được liên kết tĩnh, có thể không cần custom hints.

Nếu converter:

- Quét private field theo tên.
- Gọi getter bằng reflection.
- Tải class từ plugin name.
- Tạo proxy để đọc metadata.
- Nạp resource chứa mapping kiểu.

thì cần kiểm tra từng thao tác và bổ sung hints tương ứng nếu AOT không suy ra được.

Ví dụ, converter đọc annotation trên các field được chọn động có thể cần introspection hints cho field hoặc type. Nếu converter chỉ sử dụng reflection để gọi một method cụ thể, chỉ đăng ký method cần invoke.

Không đăng ký tất cả member của toàn bộ model package ngay khi thêm một ModelConverter. Hãy kiểm tra chính xác code path của converter.

## 21. Customizer thêm metadata đơn giản thường không cần hints

Ví dụ customizer chỉ sửa Info:

~~~java
@Component
class ApiInfoCustomizer implements OpenApiCustomizer {

    @Override
    public void customise(OpenAPI openApi) {
        openApi.getInfo()
            .description("Tài liệu API được tạo từ Spring Boot");
    }
}
~~~

Đoạn code này gọi API Java thông thường, không đọc class theo tên, không tải resource và không tạo dynamic proxy. Thông thường không cần RuntimeHintsRegistrar riêng.

Tương tự, customizer thêm tag, server hoặc extension value bằng các model class đã được tham chiếu tĩnh thường không cần hints riêng.

Hãy tập trung vào phần mở rộng có truy cập động. Chỉ vì một class triển khai OpenApiCustomizer không có nghĩa class đó cần reflection hints.

## 22. Springdoc native support và giới hạn của thư viện bên thứ ba

springdoc-openapi v2 công bố hỗ trợ GraalVM Native Image trong hệ sinh thái Spring Boot 3. Điều đó không có nghĩa mọi custom extension hoặc thư viện bên thứ ba được ứng dụng kéo vào đều tự động native-ready.

Spring Boot và Spring Framework cung cấp nhiều hints cho chính framework. springdoc có thể hỗ trợ native image cho các đường đi chuẩn của nó. Nhưng một thư viện ngoài dùng reflection hoặc đọc resource động vẫn có thể cần reachability metadata riêng.

Khi gặp lỗi trong native executable:

1. Xác định stack trace đến từ Spring, springdoc hay thư viện custom.
2. Kiểm tra thư viện đó đã cung cấp native hints hoặc reachability metadata chưa.
3. Kiểm tra code extension có reflection/resource/proxy access động không.
4. Dùng tracing agent để thu thập các access bị bỏ sót.
5. Chỉ thêm hint cho phần ứng dụng chịu trách nhiệm.

Không dùng RuntimeHints của ứng dụng để che giấu một thư viện vốn không hỗ trợ native image. Nếu lỗi nằm trong thư viện, hãy kiểm tra release có hỗ trợ, metadata repository hoặc issue upstream.

## 23. Kiểm thử RuntimeHintsRegistrar bằng RuntimeHintsPredicates

Spring cung cấp RuntimeHintsPredicates để kiểm tra registrar có đăng ký đúng metadata hay không.

Ví dụ kiểm tra resource pattern:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class SchemaCatalogHintsTests {

    @Test
    void registersSchemaResources() {
        RuntimeHints hints = new RuntimeHints();

        new SchemaCatalogCustomizer.SchemaHints()
            .registerHints(hints, getClass().getClassLoader());

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("openapi/extensions/order-schema.yaml")
        ).accepts(hints);
    }
}
~~~

Test này xác minh registrar có đóng góp resource hint cần thiết. Nó không thay thế việc chạy native executable vì file vẫn có thể sai đường dẫn hoặc extension có thể dùng thêm reflection ở code path khác.

Có thể viết predicate tương ứng cho reflection, serialization hoặc proxy hints. Chọn predicate đúng với loại access mà extension thực hiện.

## 24. Kiểm tra reflection hints

Nếu registrar đăng ký method cụ thể, hãy viết test xác minh method đó có thể được invoke theo metadata đã đóng góp.

Với các phiên bản Spring Framework khác nhau, API predicate có thể có các overload khác nhau cho type, constructor hoặc method. Dùng đúng API của Spring Framework version đang được quản lý bởi Spring Boot BOM.

Một chiến lược kiểm tra ổn định là:

1. Tạo RuntimeHints rỗng.
2. Gọi registrar bằng classloader test.
3. Dùng RuntimeHintsPredicates kiểm tra method/type cụ thể.
4. Chạy extension trong JVM với tracing agent để ghi nhận access.
5. So sánh access đã ghi nhận với hints đã đăng ký.

Không chỉ kiểm tra class tồn tại. Native image có thể giữ class nhưng thiếu quyền invoke method hoặc truy cập field mà extension cần.

## 25. Dùng GraalVM tracing agent để tìm hints còn thiếu

Khi chưa biết extension sử dụng những truy cập động nào, GraalVM tracing agent có thể quan sát ứng dụng chạy trên JVM và ghi nhận reflection, resource hoặc proxy access.

Ví dụ chạy executable JAR đã có AOT assets:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/orders-service.jar
~~~

Sau khi ứng dụng khởi động:

1. Gọi endpoint OpenAPI.
2. Mở Swagger UI nếu ứng dụng cung cấp.
3. Gọi endpoint có request/response schema tùy chỉnh.
4. Kích hoạt customizer và ModelConverter.
5. Tải các group OpenAPI.
6. Gọi mọi nhánh extension có sử dụng resource hoặc reflection.
7. Dừng ứng dụng để agent ghi metadata ra thư mục cấu hình.

Agent chỉ ghi nhận code path đã được chạy. Nếu không gọi endpoint hoặc không kích hoạt extension, metadata tương ứng có thể không xuất hiện.

Kết quả từ test suite có thể chứa cả access của test framework. Hãy review và dùng access filter nếu cần trước khi đưa file sinh ra vào source tree.

## 26. Kiểm tra AOT trên JVM trước khi build native

Có thể chạy ứng dụng với AOT-generated assets trên JVM:

~~~bash
java -Dspring.aot.enabled=true \
  -jar target/orders-service.jar
~~~

JAR phải được build với AOT processing trước đó. Chế độ này giúp phát hiện một số lỗi do AOT-generated context hoặc điều kiện build-time, nhưng vẫn chạy trên JVM nên không thay thế native executable test.

Hãy kiểm tra:

- ApplicationContext có khởi động không.
- Các customizer bean có được đăng ký không.
- OpenAPI endpoint có trả document không.
- Resource tùy chỉnh có được đọc không.
- Group và security scheme có xuất hiện không.

Sau bước này, tiếp tục build native và kiểm thử executable thật.

## 27. Build native image bằng Maven

Với Maven project dùng spring-boot-starter-parent và Native Build Tools được cấu hình, profile native có thể kích hoạt AOT và native compilation.

Ví dụ:

~~~bash
./mvnw -Pnative native:compile
~~~

Hoặc tạo native container image bằng Buildpacks:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Tên executable và cấu hình plugin phụ thuộc project. Profile native của Spring Boot parent cung cấp cấu hình thuận tiện; nếu không dùng parent, cần tự cấu hình process-aot và Native Build Tools theo tài liệu Spring Boot.

Native compilation cần toolchain GraalVM phù hợp, Native Image compiler và môi trường build tương ứng. Hãy dùng cùng kiến trúc/OS mục tiêu mà ứng dụng sẽ triển khai nếu pipeline không hỗ trợ cross-compilation.

## 28. Build native image bằng Gradle

Với Gradle, thêm plugin GraalVM Native Build Tools:

~~~kotlin
plugins {
    id("org.springframework.boot")
    id("org.graalvm.buildtools.native")
}
~~~

Sau đó chạy:

~~~bash
./gradlew nativeCompile
~~~

Hoặc build image bằng Buildpacks:

~~~bash
./gradlew bootBuildImage
~~~

Spring Boot Gradle plugin tích hợp AOT tasks khi native plugin được áp dụng. Hãy kiểm tra phiên bản Gradle plugin và Native Build Tools phù hợp với Spring Boot đang dùng.

## 29. Test native executable với OpenAPI endpoints

Sau khi build, chạy native executable và kiểm tra endpoint:

~~~bash
./target/orders-service
~~~

Kiểm tra OpenAPI JSON:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Nếu có grouped documents:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/public -o openapi-public.json
curl -fsS http://localhost:8080/v3/api-docs/admin -o openapi-admin.json
~~~

Kiểm tra các phần mở rộng:

~~~bash
jq '.["x-order-schema-notes"]' openapi.json
~~~

Ngoài endpoint tài liệu, hãy gọi API thật để kiểm tra request/response DTO, validation, serialization và các custom extension được sử dụng khi xử lý request.

Nếu ứng dụng chỉ kiểm tra startup mà không gọi /v3/api-docs, customizer có thể chưa được thực thi. Một số lỗi resource/reflection chỉ xuất hiện khi document được tạo lần đầu.

## 30. Kiểm tra Swagger UI trong native image

Nếu triển khai Swagger UI cùng ứng dụng, cần kiểm tra cả static resources và OpenAPI document:

1. Mở /swagger-ui/index.html hoặc đường dẫn được cấu hình.
2. Xác minh trang HTML và JavaScript tải thành công.
3. Kiểm tra Swagger UI tải đúng /v3/api-docs.
4. Xác minh schema custom và security scheme xuất hiện.
5. Thử một operation có request body và response DTO.
6. Kiểm tra browser console và network response.

Springdoc đã có native support cho các đường đi chuẩn, nhưng custom transformer, resource riêng hoặc static asset do ứng dụng bổ sung có thể cần resource hints nếu được nạp động.

Không thêm resource hint cho toàn bộ WebJar của Swagger UI nếu thư viện đã đóng gói và cung cấp metadata phù hợp. Chỉ điều tra phần asset tùy chỉnh do ứng dụng quản lý hoặc lỗi được tái hiện.

## 31. Kiểm tra group và customizer trong AOT

Nếu ứng dụng dùng nhiều GroupedOpenApi, kiểm tra từng group:

~~~text
/v3/api-docs
/v3/api-docs/public
/v3/api-docs/partner
/v3/api-docs/admin
~~~

Mỗi group có thể dùng customizer riêng. Một extension chỉ được gọi ở group partner có thể không được kích hoạt khi chỉ tải document mặc định.

Khi chạy tracing agent hoặc smoke test native, hãy gọi từng endpoint group và xác minh:

- Group có được đăng ký trong ApplicationContext AOT không.
- OpenAPI document có đúng path và schema không.
- Customizer có được gọi không.
- Resource riêng của group có được tải không.
- Security scheme và extension có được thêm không.

Nếu group bean được tạo theo @Profile hoặc @Conditional, điều kiện có thể được đánh giá tại build time trong AOT. Hãy chọn profile/environment đúng khi chạy process-aot; không mong bean xuất hiện runtime nếu nó không được đưa vào AOT context.

## 32. AOT yêu cầu cấu hình bean ổn định tại build time

AOT phân tích ApplicationContext khi build. Một số điều kiện cần được quyết định ở giai đoạn này:

- Classpath cố định.
- Bean definitions không thay đổi tùy ý sau build.
- @Profile và @Conditional được đánh giá dựa trên môi trường AOT.
- Bean đăng ký bằng singleton instance hoặc supplier động có thể không được chuyển đổi như bean definition thông thường.
- Kiểu bean cần khai báo đủ chính xác để AOT tạo proxy/hints.

Nếu custom extension đăng ký ModelConverter hoặc OpenApiCustomizer bằng cách thêm bean thủ công sau khi context đã chạy, AOT có thể không nhìn thấy bean đó.

Ưu tiên đăng ký extension bằng @Bean, @Component hoặc cơ chế Spring được hỗ trợ AOT. Nếu cần đăng ký bean definition động, dùng cơ chế AOT-aware như ImportBeanDefinitionRegistrar khi phù hợp.

## 33. Những lỗi thường gặp khi chạy native image

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| OpenAPI endpoint chạy trên JVM nhưng lỗi native | Thiếu reflection/resource hint hoặc thư viện chưa native-ready |
| Custom schema provider không được tìm thấy | Class được tải theo tên nhưng không được giữ lại |
| Method invocation thất bại | Thiếu method invocation hint |
| YAML extension không đọc được | Resource không được đóng gói hoặc pattern sai |
| DTO từ WebClient deserialize lỗi | Binding type không được AOT suy ra |
| JDK proxy không tạo được | Chưa đăng ký proxy interface |
| @OpenAPIDefinition biến mất | Lớp annotation không được đăng ký như @Configuration theo lưu ý springdoc v2 |
| Chỉ group mặc định hoạt động | Chưa kích hoạt hoặc chưa test customizer/group tương ứng |
| Hints có trong source nhưng native vẫn lỗi | Registrar không được import hoặc access không khớp với hint |
| JVM AOT chạy nhưng native lỗi | Thiếu metadata chỉ native-image compiler mới yêu cầu |
| Image lớn bất thường | Hints quá rộng hoặc giữ lại nhiều member/resource không cần |
| Tracing agent không sinh hint cần thiết | Code path extension chưa được kích hoạt trong phiên chạy agent |

Đọc lỗi đầu tiên và stack trace để xác định loại access. Không thêm reflection, resource và proxy hints cùng lúc theo kiểu thử ngẫu nhiên.

## 34. Quy trình điều tra lỗi thiếu hint

Khi native executable gặp lỗi trong custom extension:

1. Xác định class và method gây lỗi.
2. Xác định extension đang làm reflection, binding, resource loading hay proxy creation.
3. Kiểm tra AOT có thể suy ra access đó từ bean/controller signature không.
4. Dùng tracing agent để ghi nhận code path.
5. Viết RuntimeHintsRegistrar hoặc annotation phù hợp.
6. Viết test bằng RuntimeHintsPredicates.
7. Rebuild AOT và native image.
8. Chạy lại đúng endpoint/group/operation gây lỗi.
9. Kiểm tra output OpenAPI có khớp với JVM không.
10. Xem lại hint có quá rộng hay không.

Nếu lỗi xuất phát từ thư viện bên thứ ba, kiểm tra reachability metadata của thư viện trước khi tự duy trì một bản hint riêng trong ứng dụng.

## 35. Checklist runtime hints cho custom extension

- [ ] Đã xác nhận ứng dụng thực sự chạy native image/AOT.
- [ ] Đã kiểm tra springdoc và Spring Boot version có hỗ trợ native image.
- [ ] Đã xác định extension nào sử dụng reflection hoặc resource động.
- [ ] Không thêm hints đại trà cho DTO đã được AOT suy ra.
- [ ] Đã phân biệt JSON binding với Java serialization.
- [ ] DTO ngoài controller dùng @RegisterReflectionForBinding khi cần.
- [ ] Reflection hint chỉ cấp quyền cho member thực sự được gọi.
- [ ] Resource pattern khớp chính xác đường dẫn classpath.
- [ ] JDK proxy hint chỉ thêm khi extension tự tạo proxy.
- [ ] RuntimeHintsRegistrar được kích hoạt bằng @ImportRuntimeHints hoặc cơ chế đăng ký phù hợp.
- [ ] Hints được đặt gần custom extension.
- [ ] @OpenAPIDefinition và @SecurityScheme nằm trên configuration bean phù hợp.
- [ ] Đã viết RuntimeHintsPredicates test.
- [ ] Đã chạy AOT trên JVM.
- [ ] Đã build và chạy native executable.
- [ ] Đã kiểm tra /v3/api-docs và mọi group.
- [ ] Đã kiểm tra customizer, converter, resource và DTO thật sự được sử dụng.
- [ ] Không chỉnh sửa file hints do build tự sinh.
- [ ] Không dùng hints rộng chỉ để che lỗi của thư viện bên thứ ba.

## 36. Nguồn tra cứu

- [Spring Boot – Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot – Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot – Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Boot – Testing Native Applications](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Framework – Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework API – RuntimeHintsRegistrar](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/RuntimeHintsRegistrar.html)
- [Spring Framework API – RegisterReflectionForBinding](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html)
- [springdoc-openapi v2 FAQ – GraalVM support](https://springdoc.org/v2/faq.html#is-graalvm-supported-)
- [GraalVM Native Image – Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

Runtime hints là metadata cho những truy cập động mà Spring AOT không thể suy ra. Với springdoc, phần lớn luồng controller, DTO và document tiêu chuẩn đã được hỗ trợ; custom extension chỉ cần hint khi tự dùng reflection, resource, binding hoặc JDK proxy ngoài những gì AOT nhận diện. Hãy xác định đúng access, đăng ký hint tối thiểu, kiểm tra bằng RuntimeHintsPredicates và chạy native executable với các OpenAPI endpoint/group thực tế trước khi phát hành.
