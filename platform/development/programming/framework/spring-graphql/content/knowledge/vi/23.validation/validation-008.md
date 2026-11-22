# Validation groups

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao một DTO có thể cần nhiều bộ quy tắc validation.
- Khai báo validation group bằng interface và gắn constraint vào từng group.
- Chọn group cho từng mutation bằng Spring @Validated.
- Kết hợp group với @Valid, validation lồng nhau và group conversion.
- Dùng group sequence để điều khiển thứ tự kiểm tra.
- Phân biệt validation group với GraphQL SDL validation và kiểm tra nghiệp vụ.
- Kiểm thử các nhóm validation trong Spring for GraphQL.

## Validation groups giải quyết vấn đề gì?

Bean Validation cho phép khai báo constraint trên DTO bằng các annotation như @NotNull, @NotBlank, @Size và @Positive. Trong một API, cùng một loại dữ liệu có thể được dùng cho nhiều use case nhưng cần các quy tắc khác nhau.

Ví dụ, khi tạo sản phẩm, client chưa có ID nên server tạo ID mới. Khi cập nhật sản phẩm, ID phải được cung cấp. Giá sản phẩm bắt buộc khi tạo mới, nhưng có thể được giữ nguyên khi cập nhật một phần.

Nếu mọi constraint đều thuộc cùng một nhóm mặc định, rất khó mô tả khác biệt giữa các thao tác. Validation groups cho phép gom constraint thành các nhóm có tên, sau đó yêu cầu validator chạy một hoặc nhiều nhóm tùy use case.

Một group là một interface Java. Interface không chứa logic; nó chỉ định danh một tập constraint cần thực thi.

## Khai báo các group

Tạo interface riêng cho các use case:

~~~java
import jakarta.validation.groups.Default;

public interface OnCreate extends Default {
}

public interface OnUpdate extends Default {
}
~~~

Trong ví dụ này, hai group kế thừa Default. Khi validator chạy OnCreate hoặc OnUpdate, các constraint thuộc Default cũng được áp dụng. Điều này hữu ích khi DTO có một số quy tắc chung cho mọi thao tác.

Nếu không muốn dùng các constraint mặc định, có thể khai báo group riêng mà không kế thừa Default. Khi đó, các constraint không chỉ định groups vẫn thuộc Default và sẽ không tự động chạy khi chỉ yêu cầu group OnCreate hoặc OnUpdate.

Đây là điểm cần nhớ: khi chỉ định một custom group, Bean Validation không tự động chạy toàn bộ constraint của Default. Hãy chủ động chọn một trong hai cách:

- Cho custom group kế thừa Default nếu muốn bao gồm các constraint chung.
- Gắn các constraint cần chạy vào đúng group một cách tường minh.

## Gắn constraint vào group

Ví dụ một input dùng cho cả thao tác tạo và cập nhật sản phẩm:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record ProductInput(
        @Null(groups = OnCreate.class)
        @NotNull(groups = OnUpdate.class)
        String id,

        @NotBlank
        @Size(max = 120)
        String name,

        @NotNull(groups = OnCreate.class)
        @Positive
        BigDecimal price) {
}
~~~

Ý nghĩa:

- id phải null khi tạo mới vì server chịu trách nhiệm cấp ID.
- id phải có giá trị khi cập nhật.
- name không được để trống và tối đa 120 ký tự trong cả hai thao tác vì OnCreate và OnUpdate kế thừa Default.
- price bắt buộc khi tạo mới.
- Nếu price được cung cấp khi cập nhật, giá trị vẫn phải lớn hơn 0. Vì OnUpdate kế thừa Default nên @Positive cũng được áp dụng.

Các kiểu dữ liệu trong DTO nên là kiểu tham chiếu như String, Long và BigDecimal khi cần phân biệt giá trị bị thiếu với giá trị hợp lệ. Tránh dùng int hoặc boolean cho input có thể không được client gửi lên, vì kiểu nguyên thủy không biểu diễn được null.

Ví dụ trên mô tả một quy tắc cập nhật mà name vẫn bắt buộc, còn price có thể được bỏ qua. Nếu use case cho phép cập nhật từng field tùy ý, cần thiết kế rõ semantics của field omitted và explicit null; validation group tự nó không phân biệt hai trạng thái đó.

## Chọn group trong Spring for GraphQL bằng @Validated

Spring for GraphQL hỗ trợ Bean Validation trên annotated controller method. Khi có Validator bean trong application context, AnnotatedControllerConfigurer có thể kiểm tra các tham số được đánh dấu @Valid hoặc Spring @Validated trước khi gọi method.

Spring @Validated cho phép chỉ định group cần chạy:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.validation.annotation.Validated;

@Controller
public class ProductMutationController {

    private final ProductService productService;

    public ProductMutationController(ProductService productService) {
        this.productService = productService;
    }

    @MutationMapping
    public Product createProduct(
            @Argument("input")
            @Validated(OnCreate.class)
            ProductInput input) {

        return productService.create(input);
    }

    @MutationMapping
    public Product updateProduct(
            @Argument("input")
            @Validated(OnUpdate.class)
            ProductInput input) {

        return productService.update(input);
    }
}
~~~

Hai mutation dùng cùng ProductInput nhưng chọn group khác nhau. Khi createProduct được gọi, constraint OnCreate và Default được chạy. Khi updateProduct được gọi, constraint OnUpdate và Default được chạy.

Nếu input không hợp lệ, validation thất bại trước khi method controller được gọi. Vì vậy, service không nên nhận một DTO đã vi phạm các constraint được áp dụng ở boundary này.

Trong trường hợp không cần custom group, @Valid là cách ngắn gọn để chạy validation theo Default group:

~~~java
@MutationMapping
public Product createProduct(
        @Argument("input") @Valid ProductInput input) {
    return productService.create(input);
}
~~~

Hãy dùng @Validated khi cần chọn group cụ thể. Không cần đặt cả @Valid và @Validated trên cùng một tham số; @Validated đã là cách đánh dấu validation đồng thời chỉ định group.

## Cấu hình Bean Validation

Với Spring Boot, thêm validation starter nếu ứng dụng chưa có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Khi Bean Validation provider có mặt và Validator bean được đăng ký, Spring for GraphQL có thể phát hiện validator và bật validation cho annotated controller. Spring Boot thường tự cấu hình validator khi starter và provider phù hợp có trên classpath.

Nếu ứng dụng tự cấu hình GraphQlSource hoặc AnnotatedControllerConfigurer, hãy xác minh Validator được cung cấp cho configurer. Chỉ thêm annotation vào DTO không có nghĩa validation tự chạy nếu ứng dụng chưa cấu hình validator.

Nên kiểm tra dependency tree khi có nhiều phiên bản Jakarta Validation hoặc provider khác nhau. Spring Boot quản lý phiên bản tương thích; tránh thêm một phiên bản Hibernate Validator không tương thích một cách độc lập.

## GraphQL SDL và validation groups là hai lớp khác nhau

GraphQL engine kiểm tra operation, kiểu dữ liệu, argument và nullability trước khi gọi resolver. Bean Validation chạy sau khi GraphQL đã bind argument thành Java object.

Ví dụ SDL:

~~~graphql
scalar BigDecimal

input ProductInput {
  id: ID
  name: String
  price: BigDecimal
}

type Mutation {
  createProduct(input: ProductInput!): Product!
  updateProduct(input: ProductInput!): Product!
}
~~~

Các field id, name và price đều nullable trong SDL. Điều này cho phép cùng một input shape được gửi tới hai mutation. Validation group quyết định field nào bắt buộc trong từng use case.

Nếu khai báo name: String! trong SDL, GraphQL yêu cầu name cho mọi mutation sử dụng ProductInput. Validation group không thể làm cho field đó trở thành optional trong một mutation khác.

Ngược lại, nếu SDL khai báo name: String, GraphQL cho phép thiếu hoặc null. Bean Validation có thể yêu cầu name bằng @NotBlank trong các group phù hợp.

| Lớp kiểm tra | Thời điểm | Ví dụ |
| --- | --- | --- |
| GraphQL parsing và validation | Trước resolver | Field không tồn tại, argument sai kiểu |
| GraphQL input coercion | Trước resolver | ID hoặc BigDecimal không chuyển đổi được |
| Bean Validation group | Sau khi bind input, trước khi gọi method | id phải null khi tạo, phải có khi cập nhật |
| Business validation | Trong service/domain | SKU đã được dùng, người dùng không sở hữu sản phẩm |

Không dùng validation group để thay thế kiểm tra nghiệp vụ hoặc phân quyền. Constraint trên DTO thường kiểm tra dữ liệu cục bộ; trạng thái database và quyền truy cập cần được xác minh trong service hoặc security layer.

## Validation lồng nhau và @Valid

Khi DTO chứa input object khác, cần đánh dấu @Valid để kích hoạt cascade validation:

~~~java
public record AddressInput(
        @NotBlank(groups = OnCreate.class)
        String street,

        @NotBlank(groups = OnCreate.class)
        String city) {
}

public record CreateOrderInput(
        @NotBlank(groups = OnCreate.class)
        String customerId,

        @NotNull(groups = OnCreate.class)
        @Valid
        AddressInput shippingAddress) {
}
~~~

Nếu controller chọn OnCreate:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input")
        @Validated(OnCreate.class)
        CreateOrderInput input) {

    return orderService.create(input);
}
~~~

Group được truyền xuống object lồng nhau khi cascade validation. Do đó, các constraint thuộc OnCreate trên AddressInput cũng được kiểm tra.

Với collection, có thể cascade validation đến từng phần tử:

~~~java
public record CreateOrderInput(
        @NotEmpty(groups = OnCreate.class)
        List<@Valid OrderLineInput> items) {
}
~~~

Mỗi OrderLineInput được kiểm tra theo group đang chạy. Nếu list có thể chứa null, hãy thêm constraint phù hợp như @NotNull cho phần tử hoặc dùng kiểu generic annotation để loại bỏ phần tử null.

## Chuyển group cho object lồng nhau bằng @ConvertGroup

Đôi khi object con có bộ quy tắc riêng, không dùng cùng tên group với object cha. Khi đó, @ConvertGroup cho phép đổi group tại ranh giới cascade validation.

Ví dụ:

~~~java
public interface AddressCreate {
}

public record AddressInput(
        @NotBlank(groups = AddressCreate.class)
        String street,

        @NotBlank(groups = AddressCreate.class)
        String city) {
}

public record CreateOrderInput(
        @NotNull(groups = OnCreate.class)
        @Valid
        @ConvertGroup(
                from = OnCreate.class,
                to = AddressCreate.class)
        AddressInput shippingAddress) {
}
~~~

Khi validation chạy OnCreate trên CreateOrderInput, cascade tới shippingAddress sẽ chuyển group OnCreate thành AddressCreate. Các constraint của AddressInput thuộc AddressCreate được thực thi.

@ConvertGroup chỉ có tác dụng cùng cascade validation, tức là cần @Valid trên association. Có thể dùng @ConvertGroup.List khi cần ánh xạ nhiều group khác nhau.

Không nên tạo group conversion nếu parent và child dùng chung một bộ quy tắc. Dùng group conversion khi hai miền input thực sự có vocabulary validation riêng.

## Group inheritance và group sequence

Group inheritance và group sequence giải quyết hai nhu cầu khác nhau:

- Group inheritance giúp một group bao gồm các constraint của group cha.
- Group sequence điều khiển thứ tự chạy các group và dừng ở group đầu tiên có lỗi.

### Group inheritance

Trong ví dụ trước, OnCreate và OnUpdate kế thừa Default. Vì vậy, các constraint không khai báo groups được chạy khi một trong hai group này được chọn.

Có thể xây dựng group kế thừa lẫn nhau khi một use case mở rộng các quy tắc chung:

~~~java
public interface BasicChecks {
}

public interface CreateChecks extends BasicChecks {
}
~~~

Khi chạy CreateChecks, các constraint thuộc BasicChecks cũng được chạy. Điều này hữu ích khi nhiều use case có một tập quy tắc nền chung.

### Group sequence

Có trường hợp muốn chạy kiểm tra cơ bản trước, chỉ chạy kiểm tra nghiệp vụ tốn kém sau khi dữ liệu đã qua bước cơ bản:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public interface BasicChecks {
}

public interface BusinessChecks {
}

public record ProductCreateInput(
        @NotBlank(groups = BasicChecks.class)
        String name,

        @NotNull(groups = BasicChecks.class)
        @Positive(groups = BasicChecks.class)
        BigDecimal price,

        @NotBlank(groups = BusinessChecks.class)
        @Pattern(regexp = "[A-Z]{3}-[0-9]{6}", groups = BusinessChecks.class)
        String sku) {
}

@GroupSequence({
        BasicChecks.class,
        BusinessChecks.class
})
public interface ProductCreateChecks {
}
~~~

Khi controller dùng:

~~~java
@MutationMapping
public Product createProduct(
        @Argument("input")
        @Validated(ProductCreateChecks.class)
        ProductCreateInput input) {

    return productService.create(input);
}
~~~

Bean Validation chạy BasicChecks trước. Nếu group này có vi phạm, BusinessChecks không được chạy. Nếu không có lỗi, validator tiếp tục group kế tiếp.

Group sequence phải khai báo các group theo thứ tự mong muốn. Không đưa chính interface sequence vào danh sách group của nó. Nếu cần bao gồm Default, hãy đưa Default.class vào sequence một cách tường minh.

Ví dụ:

~~~java
@GroupSequence({
        Default.class,
        BasicChecks.class,
        BusinessChecks.class
})
public interface CompleteProductChecks {
}
~~~

Sequence phù hợp khi các bước validation có thứ tự rõ ràng. Không nên dùng sequence chỉ để gom nhiều group nếu không cần thứ tự hoặc short-circuit.

## Validation groups không tự phân biệt omitted và explicit null

Với input GraphQL, field nullable có thể bị bỏ qua hoặc được gửi tường minh với giá trị null. Một thuộc tính Java nullable thông thường có thể nhận null trong cả hai trường hợp.

Validation group quyết định constraint nào chạy; nó không tự cho biết client đã bỏ qua field hay gửi null. Với mutation cập nhật một phần, nếu hai trạng thái có ý nghĩa khác nhau, hãy dùng ArgumentValue<T>:

~~~java
import org.springframework.graphql.data.ArgumentValue;

public record PatchProductInput(
        ArgumentValue<String> name) {
}
~~~

Khi xử lý:

~~~java
if (!input.name().isOmitted()) {
    String name = input.name().value();
    if (name != null && name.isBlank()) {
        throw new InvalidProductNameException();
    }
    product.rename(name);
}
~~~

Ví dụ này minh họa hai cơ chế có trách nhiệm riêng: group chọn constraint cho thao tác update; ArgumentValue giữ trạng thái omitted để service quyết định có thay đổi field hay không. Nếu muốn dùng Bean Validation cho giá trị bên trong wrapper, cần xác minh hỗ trợ container value extraction của provider và phiên bản đang dùng; nếu không, hãy kiểm tra có điều kiện sau khi xác định field đã được gửi.

Nếu create và update có cấu trúc khác nhau nhiều, hai DTO riêng thường dễ hiểu hơn một DTO lớn với quá nhiều group. Validation groups phù hợp khi cấu trúc dữ liệu phần lớn giống nhau nhưng một số quy tắc thay đổi theo use case.

## Xử lý lỗi validation trong GraphQL

Khi validation thất bại, annotated controller method không được gọi và Spring for GraphQL phát sinh exception validation, thường là ConstraintViolationException. Exception được xử lý qua exception resolution chain để trở thành GraphQL error.

Có thể dùng @GraphQlExceptionHandler trong controller hoặc DataFetcherExceptionResolver dùng chung để chuẩn hóa lỗi. Ví dụ:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;
import jakarta.validation.ConstraintViolationException;

import java.util.Map;

@Controller
public class ProductMutationController {

    @GraphQlExceptionHandler
    public GraphQLError handleValidation(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .message("Dữ liệu đầu vào không hợp lệ")
                .errorType(ErrorType.BAD_REQUEST)
                .extensions(Map.of("code", "VALIDATION_FAILED"))
                .build();
    }
}
~~~

Đây là ví dụ minh họa handler; nếu cần trả lỗi theo từng field, hãy chuyển các constraint violations thành danh sách fieldErrors đã lọc và kiểm soát. Không gửi rejected value hoặc message mặc định nếu chúng có thể chứa dữ liệu nhạy cảm.

@GraphQlExceptionHandler trong controller áp dụng cho exception phát sinh từ các handler method thuộc controller đó. Nếu muốn dùng cùng một error contract cho nhiều controller, hãy cân nhắc một handler dùng chung hoặc DataFetcherExceptionResolver.

## Kiểm thử validation groups

Nên kiểm thử ở hai cấp:

1. Unit test cho DTO và group để xác minh constraint nào được chạy.
2. GraphQL test để xác minh mutation chọn đúng group, lỗi được chuyển thành response và service không được gọi khi input không hợp lệ.

Ví dụ unit test:

~~~java
Validator validator = Validation.buildDefaultValidatorFactory()
        .getValidator();

ProductInput input = new ProductInput(
        null,
        "Bàn phím cơ",
        null);

Set<ConstraintViolation<ProductInput>> createViolations =
        validator.validate(input, OnCreate.class);

Set<ConstraintViolation<ProductInput>> updateViolations =
        validator.validate(input, OnUpdate.class);
~~~

Với input trên:

- OnCreate phải báo lỗi vì price bắt buộc.
- OnUpdate phải báo lỗi vì id bắt buộc.
- Các constraint Default như @NotBlank và @Size vẫn được chạy do hai group kế thừa Default.

Ví dụ GraphQlTester cho mutation:

~~~java
graphQlTester.document("""
        mutation CreateProduct($input: ProductInput!) {
            createProduct(input: $input) {
                id
            }
        }
        """)
    .variable("input", Map.of(
            "name", "Bàn phím cơ"))
    .execute()
    .errors()
    .satisfy(errors -> {
        assertThat(errors).isNotEmpty();
    });
~~~

Trong test thực tế, hãy kiểm tra thêm error code VALIDATION_FAILED và xác minh ProductService.create không được gọi. Test tương tự cho update cần xác minh thiếu id bị từ chối, trong khi quy tắc riêng của OnCreate không bị áp dụng nhầm.

Nên có các trường hợp:

- Create hợp lệ và gọi đúng service.
- Create thiếu price và bị từ chối trước khi gọi service.
- Create gửi id do client tự đặt và bị từ chối.
- Update thiếu id và bị từ chối.
- Update có id và dữ liệu hợp lệ được chấp nhận.
- Constraint Default được chạy trong cả hai group nếu group kế thừa Default.
- Constraint chỉ thuộc OnCreate không chạy trong OnUpdate và ngược lại.
- Nested object được cascade theo group phù hợp.
- Group conversion đổi đúng group cho object con.
- Group sequence dừng khi group đầu tiên có vi phạm.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Constraint mặc định không chạy | Custom group không kế thừa Default | Cho group kế thừa Default hoặc gán constraint vào group rõ ràng |
| Constraint create chạy cả khi update | Constraint được gán nhầm group hoặc controller chọn sai group | Kiểm tra groups trên annotation và @Validated |
| Constraint của object con không chạy | Thiếu @Valid trên field lồng nhau | Bật cascade validation |
| Group của object cha không phù hợp với object con | Hai miền dùng group khác nhau | Dùng @ConvertGroup tại association |
| Group sequence vẫn chạy bước sau khi bước trước lỗi | Sequence khai báo sai hoặc đang validate các group riêng rẽ | Gọi sequence group và kiểm tra thứ tự |
| SDL từ chối trước khi Bean Validation chạy | Field được khai báo non-null hoặc sai kiểu | Điều chỉnh SDL nếu tính bắt buộc phụ thuộc use case |
| Update bị coi omitted và null như nhau | Chỉ dùng thuộc tính nullable thông thường | Dùng ArgumentValue khi cần phân biệt |
| Validation không chạy | Không có Validator bean hoặc tham số thiếu @Valid/@Validated | Kiểm tra validation starter và annotated controller configuration |
| Service vẫn chạy dù input sai | Validation không được bật hoặc test mock sai boundary | Kiểm tra validator, group và xác minh service invocation |
| Một DTO có quá nhiều group | Các use case có cấu trúc khác nhau đáng kể | Tách DTO theo use case để giảm độ phức tạp |

## Thực hành tổng hợp

Xây dựng hai mutation createProduct và updateProduct:

1. Khai báo ProductInput với id, name và price.
2. Tạo OnCreate và OnUpdate; cho chúng kế thừa Default để dùng chung constraint.
3. Dùng @Null(groups = OnCreate.class) và @NotNull(groups = OnUpdate.class) cho id.
4. Dùng @NotBlank và @Size cho name.
5. Dùng @NotNull(groups = OnCreate.class) và @Positive cho price.
6. Đặt @Validated(OnCreate.class) trên tham số createProduct.
7. Đặt @Validated(OnUpdate.class) trên tham số updateProduct.
8. Viết nested DTO có @Valid và thử chuyển group bằng @ConvertGroup.
9. Tạo một group sequence gồm BasicChecks và BusinessChecks.
10. Kiểm thử từng mutation bằng Validator và GraphQlTester, đồng thời xác minh service không được gọi khi validation thất bại.

Sau khi hoàn thành, hãy giải thích vì sao GraphQL SDL vẫn cần cho phép field nullable nếu tính bắt buộc thay đổi theo mutation, vì sao group không thay thế business validation và khi nào nên tách DTO.

## Ghi nhớ

Validation groups cho phép áp dụng các bộ constraint khác nhau cho từng use case. Khai báo group bằng interface, gắn constraint qua thuộc tính groups và chọn group tại annotated controller bằng Spring @Validated. Nhớ rằng constraint không chỉ định group thuộc Default; custom group chỉ chạy Default nếu kế thừa hoặc sequence bao gồm Default. Dùng @Valid để cascade, @ConvertGroup để đổi group cho object con và @GroupSequence khi cần thứ tự kiểm tra. GraphQL SDL vẫn kiểm tra kiểu và nullability trước Bean Validation; service tiếp tục chịu trách nhiệm về quy tắc nghiệp vụ và phân quyền. Dùng ArgumentValue khi cần phân biệt field omitted với explicit null, và tách DTO nếu các use case khác nhau quá nhiều.

## Tài liệu tham khảo

- [Spring for GraphQL – Annotated Controllers, Validation](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Jakarta Bean Validation – Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
