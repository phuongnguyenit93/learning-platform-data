# Đọc annotation riêng của ứng dụng để sinh siêu dữ liệu

Trong một ứng dụng Spring Boot, nhiều controller có thể dùng chung một quy ước nghiệp vụ mà annotation chuẩn của Spring MVC hoặc OpenAPI chưa thể hiện hết. Ví dụ, nhóm phát triển muốn đánh dấu operation thuộc miền catalog, xác định endpoint nội bộ, gắn mã nghiệp vụ, mô tả mức độ nhạy cảm của một parameter hoặc áp dụng một quy tắc tài liệu cho nhiều controller.

Java cho phép tạo **custom annotation** để lưu metadata ngay tại class, method hoặc parameter. springdoc-openapi cung cấp các điểm mở rộng như **OperationCustomizer** và **ParameterCustomizer** để đọc metadata đó rồi bổ sung vào đối tượng OpenAPI đang được tạo.

Luồng xử lý có hai phần: annotation riêng lưu ý định của ứng dụng; customizer đọc annotation và chuyển ý định đó thành metadata OpenAPI. Cách này giúp tái sử dụng quy ước tài liệu trên nhiều endpoint mà không phải lặp lại cùng một cấu hình ở từng operation.

## 1. Khi nào cần custom annotation?

Các annotation chuẩn đã đáp ứng phần lớn nhu cầu:

- @GetMapping và @PostMapping xác định route Spring MVC.
- @Operation mô tả summary, description, operationId và tags.
- @Parameter mô tả parameter HTTP.
- @Schema mô tả cấu trúc dữ liệu.
- @ApiResponse mô tả response của operation.

Custom annotation phù hợp khi ứng dụng có metadata riêng, chẳng hạn:

| Metadata riêng | Ví dụ nhu cầu |
|---|---|
| Miền nghiệp vụ | Đánh dấu operation thuộc catalog, orders hoặc billing |
| Phạm vi công bố | Đánh dấu operation nội bộ hoặc dành cho đối tác |
| Mã chức năng | Gắn mã use case để hệ thống tài liệu hoặc kiểm tra hợp đồng đọc được |
| Quy tắc parameter | Mô tả mã định danh, giá trị nhạy cảm hoặc quy ước deprecated |
| Metadata phục vụ công cụ | Thêm extension x-* cho cổng API hoặc pipeline |

Không cần tạo custom annotation chỉ để thay thế một thuộc tính đã có trong @Operation hoặc @Schema. Annotation riêng hữu ích khi nó đóng gói một quy ước của ứng dụng, được dùng lặp lại và có một nơi xử lý nhất quán.

Ví dụ, nếu nhiều operation cần gắn mã miền nghiệp vụ vào OpenAPI, ta có thể khai báo @ApiDomain trên controller hoặc method, sau đó dùng OperationCustomizer đọc annotation và thêm extension x-business-domain.

## 2. Khai báo custom annotation đúng cách

Một annotation dùng để đọc lúc chạy cần có ba thành phần quan trọng:

- **@Target** xác định nơi annotation được phép xuất hiện.
- **@Retention(RetentionPolicy.RUNTIME)** giữ annotation trong bytecode để reflection đọc được.
- **@Documented** cho phép annotation xuất hiện trong Javadoc của phần tử được đánh dấu.

Ví dụ annotation mô tả metadata operation:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.METHOD,
    ElementType.ANNOTATION_TYPE
})
public @interface ApiDomain {

    String value();

    String description() default "";

    boolean internal() default false;

    boolean deprecated() default false;
}
~~~

Ý nghĩa:

- **TYPE** cho phép đánh dấu controller hoặc class.
- **METHOD** cho phép ghi đè metadata ở từng handler method.
- **ANNOTATION_TYPE** cho phép dùng ApiDomain làm meta-annotation để tạo annotation chuyên biệt khác.
- **RUNTIME** là điều kiện để customizer đọc được annotation bằng reflection.
- **value** là tên miền nghiệp vụ; các thuộc tính còn lại có giá trị mặc định để người dùng không phải khai báo mọi trường.

Các kiểu hợp lệ của thuộc tính annotation gồm primitive, String, Class, enum, annotation và mảng của các kiểu này. Không thể đặt trực tiếp một object tùy ý hoặc collection làm thuộc tính annotation.

### Vì sao RetentionPolicy.RUNTIME quan trọng?

Java có ba chính sách retention:

| Retention | Annotation còn ở đâu? | Có thể đọc bằng reflection lúc chạy? |
|---|---|---|
| SOURCE | Chỉ trong source code trước khi biên dịch | Không |
| CLASS | Được lưu trong class file nhưng không bắt buộc có trong reflection runtime | Không theo cơ chế reflection thông thường |
| RUNTIME | Được lưu để reflection truy cập | Có |

Nếu custom annotation dùng SOURCE hoặc CLASS, customizer không thể đọc nó bằng các API reflection thông thường. Với metadata mà springdoc cần xử lý khi ứng dụng khởi động hoặc tạo tài liệu, hãy dùng RUNTIME.

## 3. Gắn annotation lên controller và method

Annotation có thể đặt ở cấp class để cung cấp metadata mặc định cho toàn controller:

~~~java
@ApiDomain(
    value = "catalog",
    description = "Các thao tác tra cứu và quản lý danh mục"
)
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @GetMapping("/books")
    public List<BookResponse> listBooks() {
        // ...
        return List.of();
    }

    @GetMapping("/authors")
    public List<AuthorResponse> listAuthors() {
        // ...
        return List.of();
    }
}
~~~

Nếu một method có metadata riêng, đặt annotation trực tiếp trên method:

~~~java
@ApiDomain(
    value = "catalog-search",
    description = "Tìm kiếm sách theo từ khóa"
)
@GetMapping("/search")
public List<BookResponse> search(
    @RequestParam String keyword
) {
    // ...
    return List.of();
}
~~~

Một quy ước đơn giản là **method-level thắng class-level**. Nếu method có @ApiDomain, dùng metadata của method; nếu không, lấy metadata từ controller. Chính sách ưu tiên phải được định nghĩa rõ trong customizer để kết quả không phụ thuộc vào suy đoán của người đọc.

Có thể dùng annotation ở cả hai cấp mà không tạo xung đột:

- Controller khai báo miền mặc định catalog.
- Method search khai báo catalog-search.
- Method listBooks và listAuthors kế thừa metadata catalog theo quy ước của customizer.

## 4. Đọc annotation bằng Java Reflection

Java Reflection cho phép lấy annotation trực tiếp từ class hoặc method:

~~~java
ApiDomain classMetadata =
    CatalogController.class.getAnnotation(ApiDomain.class);

Method method = CatalogController.class.getMethod("listBooks");
ApiDomain methodMetadata =
    method.getAnnotation(ApiDomain.class);
~~~

Nếu annotation được khai báo trực tiếp, cách này hoạt động. Tuy nhiên, getAnnotation không phải lúc nào cũng đủ cho ứng dụng Spring:

- Nó không tự giải quyết mọi composed annotation.
- Nó không áp dụng quy tắc alias attribute của Spring.
- Việc tìm metadata trên interface, superclass hoặc method được override cần chính sách tra cứu phù hợp.

Spring cung cấp **AnnotatedElementUtils** và **MergedAnnotations** để tìm annotation theo quy tắc merged annotation. Các API này hữu ích khi custom annotation được kết hợp từ nhiều annotation hoặc có @AliasFor.

Ví dụ tìm annotation đã hợp nhất:

~~~java
ApiDomain metadata =
    AnnotatedElementUtils.findMergedAnnotation(
        handlerMethod.getMethod(),
        ApiDomain.class
    );
~~~

Đối với class controller:

~~~java
ApiDomain classMetadata =
    AnnotatedElementUtils.findMergedAnnotation(
        handlerMethod.getBeanType(),
        ApiDomain.class
    );
~~~

**findMergedAnnotation** có thể tìm annotation trực tiếp và meta-annotation theo cơ chế của Spring, đồng thời tổng hợp các thuộc tính alias. Nếu hệ thống đặt annotation trên interface hoặc method của superclass, cần xác định rõ có muốn tra cứu toàn bộ type hierarchy hay không và dùng MergedAnnotations với SearchStrategy phù hợp. Đừng mặc định rằng mọi cách gọi reflection đều tìm được annotation ở mọi vị trí kế thừa.

### @Inherited không giải quyết mọi trường hợp

@Inherited của Java chỉ ảnh hưởng đến việc tìm annotation trên class con khi annotation được khai báo ở superclass. Nó không làm annotation tự kế thừa qua interface, không áp dụng cho method và không áp dụng cho parameter.

Nếu cần đọc annotation từ interface hoặc method hierarchy, hãy dùng cơ chế tìm merged annotation của Spring với chiến lược phù hợp và viết test cho quy ước kế thừa đó.

## 5. Tạo composed annotation bằng meta-annotation và @AliasFor

Khi nhiều controller thuộc cùng một miền, có thể tạo annotation chuyên biệt để người dùng không phải lặp lại giá trị domain.

~~~java
import org.springframework.core.annotation.AliasFor;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.METHOD,
    ElementType.ANNOTATION_TYPE
})
@ApiDomain(value = "catalog")
public @interface CatalogApi {

    @AliasFor(
        annotation = ApiDomain.class,
        attribute = "description"
    )
    String description() default "";
}
~~~

Sử dụng:

~~~java
@CatalogApi(
    description = "Các thao tác tra cứu sách và tác giả"
)
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {
    // ...
}
~~~

**@AliasFor** cho Spring biết thuộc tính description của CatalogApi ánh xạ tới thuộc tính description của ApiDomain. Khi dùng AnnotatedElementUtils.findMergedAnnotation để tìm ApiDomain, Spring có thể trả về metadata đã hợp nhất từ composed annotation.

Các điều kiện cần giữ:

- Annotation gốc phải cho phép ANNOTATION_TYPE nếu được dùng làm meta-annotation.
- Composed annotation phải có RUNTIME retention nếu customizer cần đọc lúc chạy.
- Kiểu và default value của thuộc tính alias phải tương thích với thuộc tính đích.
- Không tạo alias vòng hoặc ánh xạ các thuộc tính có ý nghĩa khác nhau.

Nếu chỉ cần một giá trị cố định, meta-annotation không cần @AliasFor. Dùng alias khi muốn người dùng annotation chuyên biệt tùy chỉnh một phần metadata của annotation gốc.

## 6. Đọc metadata operation bằng OperationCustomizer

**OperationCustomizer** cho phép thay đổi một Operation trong lúc springdoc xây dựng tài liệu. Trong springdoc-openapi 2.x, interface nằm trong package **org.springdoc.core.customizers** và nhận Operation cùng HandlerMethod.

~~~java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.util.StringUtils;
import org.springframework.web.method.HandlerMethod;
import io.swagger.v3.oas.models.Operation;

@Configuration
public class OpenApiCustomizationConfiguration {

    @Bean
    OperationCustomizer apiDomainCustomizer() {
        return (operation, handlerMethod) -> {
            ApiDomain metadata =
                AnnotatedElementUtils.findMergedAnnotation(
                    handlerMethod.getMethod(),
                    ApiDomain.class
                );

            if (metadata == null) {
                metadata =
                    AnnotatedElementUtils.findMergedAnnotation(
                        handlerMethod.getBeanType(),
                        ApiDomain.class
                    );
            }

            if (metadata == null) {
                return operation;
            }

            operation.addExtension(
                "x-business-domain",
                metadata.value()
            );

            if (metadata.internal()) {
                operation.addExtension("x-internal", true);
            }

            if (metadata.deprecated()) {
                operation.setDeprecated(true);
            }

            if (StringUtils.hasText(metadata.description())
                    && !StringUtils.hasText(operation.getDescription())) {
                operation.setDescription(metadata.description());
            }

            return operation;
        };
    }
}
~~~

Customizer thực hiện các bước:

1. Nhận handler method mà springdoc đang mô tả.
2. Tìm ApiDomain trên method trước.
3. Nếu method không có, tìm trên class controller.
4. Nếu không tìm thấy metadata, giữ nguyên operation.
5. Nếu có, thêm vendor extension x-business-domain.
6. Đánh dấu operation nội bộ hoặc deprecated khi annotation yêu cầu.
7. Chỉ đặt description nếu operation chưa có description, tránh ghi đè mô tả @Operation đã khai báo.

**HandlerMethod** cho biết method và bean type liên quan đến operation. Đây là cầu nối để customizer đọc annotation của ứng dụng thay vì chỉ xử lý đối tượng OpenAPI đã được tạo.

### Vendor extension x-*

OpenAPI cho phép thêm metadata mở rộng với tên bắt đầu bằng **x-**. Ví dụ:

~~~yaml
paths:
  /api/catalog/books:
    get:
      operationId: listBooks
      x-business-domain: catalog
      x-internal: false
~~~

Vendor extension có thể được công cụ riêng đọc, chẳng hạn cổng API, hệ thống sinh tài liệu hoặc pipeline kiểm tra. Chỉ thêm dữ liệu có kiểu JSON phù hợp như string, number, boolean, array hoặc object. Không đưa secret, token hoặc thông tin nhạy cảm vào extension vì chúng sẽ được công bố cùng tài liệu.

Extension không thay thế tags, security requirement hoặc response metadata chuẩn. Nếu thông tin có cấu trúc OpenAPI chính thức tương ứng, hãy dùng thuộc tính chuẩn; extension chỉ dành cho metadata riêng của ứng dụng.

## 7. Đọc annotation trên parameter bằng ParameterCustomizer

Khi metadata nằm trên một tham số method, **ParameterCustomizer** có thể nhận đối tượng Parameter của OpenAPI và MethodParameter của Spring. Từ MethodParameter, customizer truy cập annotation trên tham số Java.

Khai báo annotation:

~~~java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE
})
public @interface ApiParameterDoc {

    String description();

    String example() default "";

    boolean deprecated() default false;

    boolean sensitive() default false;
}
~~~

Sử dụng trên controller:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @ApiParameterDoc(
        description = "Từ khóa tìm kiếm theo tên sách",
        example = "Spring"
    )
    @RequestParam(name = "keyword")
    String keyword
) {
    // ...
    return List.of();
}
~~~

Customizer:

~~~java
import org.springdoc.core.customizers.ParameterCustomizer;
import org.springframework.core.MethodParameter;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.util.StringUtils;
import io.swagger.v3.oas.models.parameters.Parameter;

@Bean
ParameterCustomizer apiParameterCustomizer() {
    return (parameter, methodParameter) -> {
        ApiParameterDoc metadata =
            AnnotatedElementUtils.findMergedAnnotation(
                methodParameter.getParameter(),
                ApiParameterDoc.class
            );

        if (metadata == null) {
            return parameter;
        }

        parameter.setDescription(metadata.description());

        if (metadata.deprecated()) {
            parameter.setDeprecated(true);
        }

        if (metadata.sensitive()) {
            parameter.setExample(null);
        } else if (StringUtils.hasText(metadata.example())) {
            parameter.setExample(metadata.example());
        }

        return parameter;
    };
}
~~~

Ví dụ này dùng custom annotation để chuẩn hóa description, example và deprecated. Nếu parameter được đánh dấu sensitive, customizer không đưa ví dụ vào tài liệu. Đây là quy ước tài liệu; server vẫn phải bảo vệ và xử lý dữ liệu nhạy cảm theo cơ chế runtime riêng.

ParameterCustomizer chỉ áp dụng cho các OpenAPI Parameter được springdoc tạo từ tham số method. Nó không tự xử lý request body, DTO property hoặc mọi annotation trên method. Với request body hoặc schema property, cần dùng điểm mở rộng phù hợp với đối tượng tương ứng.

## 8. Phân biệt customizer theo đối tượng được xử lý

Chọn đúng extension point giúp tránh đọc sai metadata hoặc sửa nhầm cấp:

| Extension point | Đối tượng nhận được | Dùng khi |
|---|---|---|
| **OperationCustomizer** | Operation và HandlerMethod | Đọc annotation trên controller/method, thêm metadata operation |
| **ParameterCustomizer** | Parameter và MethodParameter | Đọc annotation trên tham số Java, sửa parameter OpenAPI |
| **OpenApiCustomizer** | Toàn bộ OpenAPI document | Chỉnh sửa paths, tags, servers hoặc components ở cấp tài liệu |
| **GlobalOpenApiCustomizer** | Tài liệu mặc định và các group theo cơ chế global | Áp dụng thay đổi cấp tài liệu cho nhiều document |
| **GroupedOpenApi customizer** | Tài liệu của group được cấu hình | Chỉ áp dụng quy tắc cho một group |

OperationCustomizer thích hợp khi cần HandlerMethod để biết annotation nào tạo ra operation. OpenApiCustomizer nhận tài liệu OpenAPI đã được xây dựng; nó không mặc nhiên có HandlerMethod cho từng operation. Nếu cần đọc custom annotation gắn trên method, hãy xử lý ở OperationCustomizer hoặc tự duy trì một cơ chế ánh xạ phù hợp.

Trong springdoc 2.x, có thể đăng ký customizer bằng bean Spring. Nếu chỉ muốn áp dụng cho một group, dùng API customizer gắn với GroupedOpenApi tương ứng. Phạm vi áp dụng giữa bean toàn cục và group có thể phụ thuộc loại customizer cùng phiên bản; hãy kiểm tra endpoint tài liệu của từng group sau cấu hình.

## 9. Đọc annotation trên interface và method kế thừa

Một số dự án khai báo hợp đồng controller trên interface:

~~~java
@ApiDomain(value = "catalog", description = "API danh mục")
public interface CatalogOperations {

    @GetMapping("/api/catalog/books")
    List<BookResponse> listBooks();
}

@RestController
public class CatalogController implements CatalogOperations {

    @Override
    public List<BookResponse> listBooks() {
        // ...
        return List.of();
    }
}
~~~

Nếu customizer chỉ gọi findMergedAnnotation trên method triển khai và bean class, metadata đặt trên interface có thể không được tìm theo cách bạn mong đợi. Khi cho phép annotation trên interface hoặc superclass, hãy định nghĩa chiến lược tìm kiếm tường minh.

Spring cung cấp **MergedAnnotations.SearchStrategy.TYPE_HIERARCHY** để tìm trên type hierarchy:

~~~java
MergedAnnotation<ApiDomain> merged =
    MergedAnnotations.from(
        handlerMethod.getBeanType(),
        MergedAnnotations.SearchStrategy.TYPE_HIERARCHY
    ).get(ApiDomain.class);

ApiDomain metadata =
    merged.isPresent() ? merged.synthesize() : null;
~~~

Với method, có thể dùng MergedAnnotations trên method cùng chiến lược hierarchy thích hợp cho phiên bản Spring. Cần viết test cho các trường hợp class trực tiếp, method trực tiếp, interface và superclass để xác nhận thứ tự ưu tiên.

Không dùng @Inherited như cách thay thế cho mọi chiến lược này. @Inherited không làm annotation method hoặc interface tự động được kế thừa theo mọi trường hợp.

## 10. Xác định thứ tự ưu tiên khi có nhiều annotation

Một controller có thể có annotation ở class, method và composed annotation. Nếu không định nghĩa ưu tiên, metadata có thể khó dự đoán.

Một chính sách đơn giản:

1. Annotation trực tiếp hoặc composed annotation trên method có ưu tiên cao nhất.
2. Nếu method không có, lấy annotation từ controller class.
3. Nếu class không có, có thể tìm interface/superclass nếu dự án đã bật quy tắc hierarchy.
4. Nếu không tìm thấy, không bổ sung metadata riêng.

Có thể tách việc tìm metadata thành helper để tránh lặp logic:

~~~java
private ApiDomain resolveApiDomain(HandlerMethod handlerMethod) {
    ApiDomain methodMetadata =
        AnnotatedElementUtils.findMergedAnnotation(
            handlerMethod.getMethod(),
            ApiDomain.class
        );

    if (methodMetadata != null) {
        return methodMetadata;
    }

    return AnnotatedElementUtils.findMergedAnnotation(
        handlerMethod.getBeanType(),
        ApiDomain.class
    );
}
~~~

Nếu cho phép interface hoặc superclass, mở rộng helper bằng MergedAnnotations và xác định thứ tự cụ thể. Tránh tự động gộp hai annotation thành một object nếu chưa có quy tắc rõ ràng cho từng thuộc tính.

Ví dụ: method-level domain có thể ghi đè domain của class, nhưng description rỗng ở method có thể được xem là “không cung cấp” và kế thừa description class. Nếu muốn hành vi này, hãy viết logic merge theo từng thuộc tính thay vì chỉ chọn toàn bộ annotation method.

## 11. Tách metadata tài liệu khỏi hành vi runtime

Custom annotation được đọc bởi OperationCustomizer hoặc ParameterCustomizer chỉ thay đổi OpenAPI document. Nó không tự:

- Đăng ký route Spring MVC.
- Thay đổi cách Spring bind query, path, header hoặc body.
- Kích hoạt Bean Validation.
- Cấp hoặc từ chối quyền truy cập.
- Thay đổi status code và payload response.
- Ẩn endpoint khỏi server runtime.

Ví dụ @ApiDomain(internal = true) ở trên thêm extension x-internal vào tài liệu. Nó không bảo vệ endpoint. Muốn chặn truy cập, phải cấu hình Spring Security hoặc kiểm tra quyền trong tầng phù hợp.

Tương tự, ApiParameterDoc(sensitive = true) chỉ ngăn customizer thêm example theo quy ước đã viết. Nó không mã hóa giá trị, không xóa dữ liệu khỏi log và không bảo vệ request.

Nếu metadata cần ảnh hưởng runtime, hãy xây dựng một thành phần runtime riêng sử dụng annotation đó. Không giả định customizer tài liệu sẽ được gọi trong luồng xử lý HTTP.

## 12. Kiểm tra customizer bằng OpenAPI JSON

Sau khi ứng dụng khởi động, lấy tài liệu tại **/v3/api-docs**. Nếu operation có annotation ApiDomain, kiểm tra extension:

~~~json
{
  "paths": {
    "/api/catalog/books": {
      "get": {
        "x-business-domain": "catalog",
        "description": "Các thao tác tra cứu và quản lý danh mục"
      }
    }
  }
}
~~~

Nếu parameter có ApiParameterDoc, kiểm tra name, description, example và deprecated ở phần parameters của operation.

Có thể dùng jq:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/catalog/search"].get'
~~~

Để kiểm tra parameter:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/catalog/search"].get.parameters'
~~~

Nếu ứng dụng có nhiều GroupedOpenApi, gọi đúng endpoint của từng group và xác nhận customizer có phạm vi mong muốn. Một extension có mặt trong tài liệu mặc định nhưng vắng trong group có thể là dấu hiệu customizer được đăng ký sai phạm vi.

## 13. Viết integration test cho annotation và customizer

Có thể kiểm tra metadata được sinh ra bằng MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiDomainDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void addsBusinessDomainExtension() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/catalog/books'].get['x-business-domain']"
            ).value("catalog"));
    }

    @Test
    void appliesParameterMetadata() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/catalog/search'].get.parameters[0].description"
            ).value("Từ khóa tìm kiếm theo tên sách"));
    }
}
~~~

Test nên bao phủ:

- Annotation trực tiếp trên method.
- Annotation ở cấp class và fallback xuống method.
- Composed annotation với @AliasFor.
- Annotation trên parameter.
- Trường hợp không có annotation.
- Method-level override class-level.
- Group-specific document nếu customizer có phạm vi theo group.

Nếu dùng interface hoặc superclass, thêm test xác nhận hierarchy search. Test JSON giúp phát hiện lỗi metadata không được đọc hoặc customizer ghi đè thông tin OpenAPI có sẵn.

## 14. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Customizer không tìm thấy annotation | Retention không phải RUNTIME hoặc target không phù hợp | Kiểm tra @Retention và @Target |
| getAnnotation trả null với composed annotation | Reflection trực tiếp không tìm merged metadata | Dùng AnnotatedElementUtils hoặc MergedAnnotations |
| Annotation trên interface không được đọc | Chỉ tìm trên method triển khai và class | Dùng hierarchy search có chủ đích và test |
| Method metadata bị class metadata ghi đè | Thứ tự ưu tiên chưa rõ hoặc code luôn đọc class trước | Ưu tiên method-level rồi mới fallback class-level |
| @AliasFor không phản ánh thuộc tính | Alias target hoặc default không tương thích | Kiểm tra annotation gốc, attribute và composed annotation |
| ParameterCustomizer không chạy cho request body | Request body không phải OpenAPI Parameter Object | Dùng extension point dành cho operation/body/schema |
| Description @Operation bị mất | Customizer ghi đè description không điều kiện | Chỉ bổ sung khi trống hoặc merge theo quy tắc rõ ràng |
| Extension không xuất hiện trong group | Customizer chưa được áp dụng cho group đó | Kiểm tra đăng ký global và group-specific |
| Dùng extension để bảo vệ endpoint | Nhầm metadata tài liệu với authorization | Cấu hình Spring Security hoặc runtime authorization |
| Ví dụ nhạy cảm xuất hiện trong tài liệu | Customizer không áp dụng quy tắc sensitive | Loại ví dụ và dùng dữ liệu giả lập |

## 15. Quy trình triển khai custom annotation

Khi cần đưa metadata riêng vào OpenAPI, thực hiện theo thứ tự:

1. **Xác định metadata:** thông tin nào không được annotation chuẩn biểu diễn và công cụ nào sẽ đọc nó?
2. **Chọn vị trí:** class, method hay parameter; tránh cho phép target rộng hơn nhu cầu.
3. **Khai báo annotation:** đặt RUNTIME retention, target phù hợp và default rõ ràng.
4. **Quy định kế thừa:** xác định method có ghi đè class không, có đọc interface/superclass không.
5. **Chọn customizer:** OperationCustomizer cho operation/HandlerMethod; ParameterCustomizer cho parameter/MethodParameter.
6. **Chuyển thành OpenAPI metadata:** dùng field chuẩn nếu phù hợp, hoặc extension x-* cho metadata riêng.
7. **Giữ nguyên thông tin có sẵn:** không ghi đè summary, description, schema hoặc response nếu không có quy tắc merge.
8. **Kiểm thử:** đọc /v3/api-docs và từng group; xác nhận annotation có và không có đều cho kết quả đúng.
9. **Kiểm tra ranh giới runtime:** bảo đảm không nhầm metadata tài liệu với route, validation hoặc bảo mật.

## 16. Nguyên tắc thiết kế dễ bảo trì

- Tạo custom annotation cho một quy ước có ý nghĩa, không tạo wrapper cho từng annotation chuẩn nếu không có giá trị bổ sung.
- Dùng RUNTIME retention nếu metadata được đọc khi chạy.
- Chọn @Target hẹp nhất đáp ứng nhu cầu.
- Dùng Spring merged annotation utilities khi cần composed annotation hoặc alias.
- Định nghĩa rõ method-level, class-level và hierarchy precedence.
- Dùng OperationCustomizer khi cần HandlerMethod; dùng ParameterCustomizer khi cần MethodParameter.
- Giữ metadata chuẩn trong OpenAPI ở các thuộc tính chuẩn; chỉ dùng x-* cho thông tin riêng.
- Không ghi secret hoặc dữ liệu thật nhạy cảm vào extension/example.
- Không dùng customizer tài liệu thay cho Spring Security, Bean Validation hoặc logic binding.
- Viết integration test để bảo đảm metadata được sinh đúng trên tài liệu mặc định và group liên quan.

## Kết luận

Custom annotation cho phép ứng dụng lưu metadata riêng trên controller, method và parameter. Để đọc được lúc chạy, annotation cần RUNTIME retention và target phù hợp. Spring merged-annotation utilities giúp xử lý composed annotation và @AliasFor; OperationCustomizer đọc metadata gắn với HandlerMethod, còn ParameterCustomizer đọc metadata của MethodParameter. Customizer chuyển thông tin đó thành thuộc tính OpenAPI hoặc vendor extension x-*. Hãy quy định rõ thứ tự ưu tiên, giữ nguyên mô tả OpenAPI đã có và kiểm tra JSON đầu ra. Metadata tài liệu chỉ thay đổi hợp đồng được công bố; hành vi route, binding, validation và bảo mật vẫn cần được triển khai ở tầng runtime tương ứng.
