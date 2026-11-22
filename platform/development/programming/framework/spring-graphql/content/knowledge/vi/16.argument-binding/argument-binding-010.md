# Setter binding

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích setter binding trong cơ chế argument binding của Spring for GraphQL.
- Tạo JavaBean DTO có no-argument constructor và setter để nhận dữ liệu GraphQL.
- Bind input object, object lồng nhau và collection bằng @Argument.
- Hiểu vai trò của tên property, ConversionService và GraphQlArgumentBinder.
- Phân biệt lỗi GraphQL input coercion với lỗi Java object binding.
- Kết hợp setter binding với Bean Validation và ArgumentValue<T>.
- Chọn khi nào nên dùng setter binding, constructor binding hoặc direct field access.

## Setter binding là gì?

Khi client gửi argument cho một GraphQL field, Spring for GraphQL cần chuyển dữ liệu đó thành tham số Java của controller method. Với @Argument, framework sử dụng GraphQlArgumentBinder để tạo và điền dữ liệu vào object đích.

Có hai cách khởi tạo object phổ biến:

1. **Constructor binding**: lấy dữ liệu argument và truyền vào primary/data constructor.
2. **Setter binding**: gọi default constructor để tạo object, sau đó ánh xạ các giá trị argument vào property thông qua setter.

Setter binding phù hợp với JavaBean DTO có constructor không tham số và các setter theo quy ước JavaBeans. Cách này hữu ích khi DTO cần mutable properties, tương thích với thư viện JavaBean hoặc được xây dựng theo phong cách class truyền thống.

Ví dụ, schema khai báo input:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  pageCount: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Client gửi mutation với variables:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

~~~json
{
  "input": {
    "title": "Spring for GraphQL",
    "authorId": "author-12",
    "pageCount": 320
  }
}
~~~

Spring for GraphQL có thể bind input trên vào một JavaBean CreateBookInput bằng cách tạo object trước rồi gọi các setter tương ứng.

## Quy ước JavaBean cho setter binding

Một DTO dùng setter binding thường có:

- Constructor không tham số để binder tạo instance.
- Setter cho từng property cần nhận từ GraphQL.
- Tên property Java tương ứng với tên field trong input object.
- Kiểu Java có thể biểu diễn dữ liệu đã được GraphQL coercion.

Ví dụ DTO:

~~~java
public class CreateBookInput {

    private String title;
    private String authorId;
    private Integer pageCount;

    public CreateBookInput() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getAuthorId() {
        return authorId;
    }

    public void setAuthorId(String authorId) {
        this.authorId = authorId;
    }

    public Integer getPageCount() {
        return pageCount;
    }

    public void setPageCount(Integer pageCount) {
        this.pageCount = pageCount;
    }
}
~~~

Trong ví dụ:

- CreateBookInput() cho phép binder khởi tạo object.
- setTitle nhận giá trị của field title.
- setAuthorId nhận giá trị của field authorId.
- setPageCount nhận giá trị của field pageCount.
- Getter giúp service hoặc phần code khác đọc dữ liệu sau khi binding.

Setter nên thực hiện việc gán giá trị đơn giản. Không nên gọi repository, ghi database hoặc thực hiện nghiệp vụ trong setter vì binder có thể gọi các setter theo thứ tự binding, không phải theo một quy trình nghiệp vụ được định nghĩa.

## Nhận DTO bằng @Argument

Controller nhận toàn bộ input object thông qua @Argument:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

@Argument("input") chỉ rõ method nhận argument có tên input trong field GraphQL. Tên argument được xác định ở schema; tên class DTO không quyết định tên argument.

Nếu bỏ tên trong annotation, Spring có thể suy ra tên từ tên tham số method khi thông tin tên tham số được giữ trong bytecode, ví dụ dự án biên dịch với tùy chọn -parameters. Ghi rõ @Argument("input") giúp mapping dễ đọc và tránh phụ thuộc vào cấu hình compiler.

@Argument không có thuộc tính required hoặc defaultValue. Tính bắt buộc và giá trị mặc định được khai báo trong SDL, sau đó GraphQL Java kiểm tra trước khi method controller được gọi.

## Luồng setter binding

Quá trình binding có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Client gửi GraphQL variables] --> B[GraphQL parse và input coercion]
    B --> C[GraphQL tạo argument map]
    C --> D[@Argument nhận argument input]
    D --> E[GraphQlArgumentBinder]
    E --> F[Gọi no-argument constructor]
    F --> G[Ánh xạ input field sang property]
    G --> H[Gọi setter tương ứng]
    H --> I[Bind object lồng nhau và collection]
    I --> J[Controller method nhận DTO]
    J --> K[Application service]
~~~

GraphQL kiểm tra cấu trúc theo SDL trước. Sau đó binder nhận argument đã được GraphQL chuyển đổi, tạo DTO và điền property. Khi binding thành công, controller method mới nhận object đã được tạo.

Setter binding được áp dụng đệ quy. Nếu DTO có property là một input DTO khác hoặc một danh sách input DTO, binder tiếp tục tạo object con và bind các giá trị bên trong theo cùng nguyên tắc.

## Binding input object lồng nhau

Giả sử mutation tạo đơn hàng có địa chỉ giao hàng và các dòng sản phẩm:

~~~graphql
input ShippingAddressInput {
  recipient: String!
  street: String!
  city: String!
  postalCode: String
}

input OrderItemInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  customerId: ID!
  shippingAddress: ShippingAddressInput!
  items: [OrderItemInput!]!
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

DTO Java có thể được thiết kế thành các JavaBean riêng:

~~~java
public class ShippingAddressInput {

    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    public ShippingAddressInput() {
    }

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
~~~

~~~java
public class OrderItemInput {

    private String productId;
    private Integer quantity;

    public OrderItemInput() {
    }

    public String getProductId() {
        return productId;
    }

    public void setProductId(String productId) {
        this.productId = productId;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

~~~java
import java.util.List;

public class CreateOrderInput {

    private String customerId;
    private ShippingAddressInput shippingAddress;
    private List<OrderItemInput> items;

    public CreateOrderInput() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public ShippingAddressInput getShippingAddress() {
        return shippingAddress;
    }

    public void setShippingAddress(ShippingAddressInput shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public List<OrderItemInput> getItems() {
        return items;
    }

    public void setItems(List<OrderItemInput> items) {
        this.items = items;
    }
}
~~~

Khi nhận CreateOrderInput, binder thực hiện các bước:

1. Tạo CreateOrderInput bằng constructor không tham số.
2. Tạo ShippingAddressInput, bind các property địa chỉ rồi gán qua setShippingAddress.
3. Tạo từng OrderItemInput trong danh sách items.
4. Gán danh sách đã bind qua setItems.
5. Gán customerId qua setCustomerId.

Controller chỉ cần nhận DTO cấp cao nhất:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Binder hỗ trợ cấu trúc collection và object lồng nhau, nhưng không kiểm tra thay các quy tắc nghiệp vụ. Ví dụ quantity có thể được bind thành số nguyên hợp lệ về kiểu nhưng vẫn cần kiểm tra phải lớn hơn 0.

## Kiểu dữ liệu và ConversionService

GraphQL input values được chuyển đổi theo scalar và enum trong schema. Khi cần chuyển tiếp sang kiểu Java đích, GraphQlArgumentBinder sử dụng ConversionService.

Một số kiểu thường gặp:

| GraphQL input | Kiểu Java thường dùng |
| --- | --- |
| String | String |
| ID | String hoặc kiểu định danh phù hợp |
| Int | Integer |
| Float | Double |
| Boolean | Boolean |
| BigDecimal custom scalar | BigDecimal nếu scalar trả kiểu này |
| DateTime custom scalar | Kiểu được scalar implementation quy định, ví dụ OffsetDateTime |
| Enum | Java enum có value tương ứng |
| List | List<T> hoặc collection tương thích |

Ưu tiên khai báo kiểu Java khớp với kết quả coercion của GraphQL scalar. ConversionService có thể hỗ trợ các chuyển đổi đã đăng ký, nhưng không nên dựa vào một phép chuyển đổi ngầm không được cấu hình hoặc kiểm thử.

Nếu ứng dụng cần định dạng riêng, có thể đăng ký converter hoặc formatter phù hợp với ConversionService được dùng cho argument binding. Với custom scalar, hãy xác định rõ Java runtime type ngay tại Coercing; không nên vừa parse thành một kiểu vừa khai báo DTO bằng một kiểu không tương thích rồi hy vọng binder tự xử lý.

## Tên field GraphQL và tên property Java

Mặc định, binder ánh xạ tên input field sang tên property tương ứng. Ví dụ:

| GraphQL input field | Java property | Setter |
| --- | --- | --- |
| firstName | firstName | setFirstName(...) |
| authorId | authorId | setAuthorId(...) |
| pageCount | pageCount | setPageCount(...) |

Nếu schema và Java sử dụng quy ước tên khác nhau, cần có cách ánh xạ rõ ràng. Ví dụ schema có thể dùng first_name, trong khi Java property dùng firstName. GraphQlArgumentBinder hỗ trợ cấu hình nameResolver để chuyển tên GraphQL sang tên property Java.

Ở các phiên bản Spring for GraphQL có GraphQlArgumentBinder.Options, có thể cấu hình tùy chọn binding qua AnnotatedControllerConfigurer. Cách cấu hình cụ thể phụ thuộc phiên bản framework; hãy đối chiếu API của phiên bản dự án trước khi khai báo bean tùy chỉnh. Nếu schema mới, nên thống nhất naming convention ngay từ đầu để tránh phải thêm mapping tùy chỉnh.

## Setter binding với validation

Setter binding chỉ bảo đảm dữ liệu được chuyển vào DTO. Nó không tự xác minh các điều kiện như chuỗi không rỗng, số lượng dương hoặc độ dài tối đa.

Có thể dùng Jakarta Bean Validation với các constraint trên field hoặc getter của JavaBean:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public class OrderItemInput {

    @NotBlank
    private String productId;

    @NotNull
    @Positive
    private Integer quantity;

    public OrderItemInput() {
    }

    public String getProductId() {
        return productId;
    }

    public void setProductId(String productId) {
        this.productId = productId;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Với object lồng nhau, dùng @Valid để kích hoạt validation cascade:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public class CreateOrderInput {

    @NotNull
    @Valid
    private ShippingAddressInput shippingAddress;

    @NotEmpty
    private List<@NotNull @Valid OrderItemInput> items;

    public CreateOrderInput() {
    }

    public ShippingAddressInput getShippingAddress() {
        return shippingAddress;
    }

    public void setShippingAddress(ShippingAddressInput shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public List<OrderItemInput> getItems() {
        return items;
    }

    public void setItems(List<OrderItemInput> items) {
        this.items = items;
    }
}
~~~

Controller kích hoạt validation trước khi gọi service:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Đảm bảo ứng dụng có dependency spring-boot-starter-validation và validator bean được cấu hình. Khi validation thất bại, controller method không tiếp tục thực hiện use case; exception có thể được ánh xạ thành GraphQL error theo chính sách lỗi của API.

Phân biệt ba lớp kiểm tra:

- GraphQL schema: kiểu dữ liệu, field bắt buộc, enum và nullability.
- Bean Validation: độ dài, chuỗi không rỗng, số dương, danh sách không rỗng.
- Application service: object có tồn tại, trạng thái có cho phép thao tác, người dùng có quyền thực hiện hay không.

Không đưa truy vấn database hoặc kiểm tra phân quyền vào setter. Setter chỉ nên cập nhật trạng thái DTO; service chịu trách nhiệm các quy tắc phụ thuộc vào dữ liệu và ngữ cảnh ứng dụng.

## Omitted và explicit null trong JavaBean

Với property Java thông thường, giá trị không được truyền và giá trị được truyền tường minh là null có thể cùng dẫn tới property có giá trị null. Nếu mutation cập nhật một phần cần phân biệt hai trạng thái này, có thể dùng ArgumentValue<T> làm kiểu property:

~~~java
import org.springframework.graphql.data.ArgumentValue;

public class UpdateBookInput {

    private ArgumentValue<String> subtitle;

    public UpdateBookInput() {
    }

    public ArgumentValue<String> getSubtitle() {
        return subtitle;
    }

    public void setSubtitle(ArgumentValue<String> subtitle) {
        this.subtitle = subtitle;
    }
}
~~~

Trong service:

~~~java
public Book updateSubtitle(Book book, UpdateBookInput input) {
    ArgumentValue<String> subtitle = input.getSubtitle();

    if (subtitle != null && !subtitle.isOmitted()) {
        book.setSubtitle(subtitle.value());
    }

    return bookRepository.save(book);
}
~~~

Với ArgumentValue, isOmitted() cho biết field bị bỏ qua hay được cung cấp. Nếu field được cung cấp với giá trị null, value() là null; service có thể hiểu đó là yêu cầu xóa phụ đề. Nếu field bị omitted, service giữ nguyên giá trị cũ.

Spring for GraphQL hỗ trợ ArgumentValue trong cấu trúc object của @Argument, kể cả property được khởi tạo thông qua setter. Hãy kiểm thử cả hai trạng thái trong phiên bản đang dùng. Chỉ dùng wrapper ở những field thực sự cần phân biệt; các property khác có thể tiếp tục dùng kiểu Java thông thường.

## Setter binding và constructor binding

Hai cách binding phục vụ các phong cách DTO khác nhau:

| Tiêu chí | Setter binding | Constructor binding |
| --- | --- | --- |
| Khởi tạo object | Default/no-argument constructor | Primary/data constructor |
| Điền dữ liệu | Gọi setter theo property | Truyền giá trị vào constructor parameter |
| DTO phù hợp | JavaBean mutable | Record hoặc class bất biến |
| Thay đổi trạng thái sau khởi tạo | Có thể qua setter | Thường không có setter |
| Yêu cầu chính | Constructor không tham số và setter phù hợp | Constructor và tên parameter tương ứng |

Ví dụ setter binding thường dùng class có constructor không tham số và setter công khai. Constructor binding thường tự nhiên hơn với Java record:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        Integer pageCount) {
}
~~~

Nếu một class có cả constructor phù hợp và default constructor, hãy kiểm tra quy tắc chọn constructor của binder trong phiên bản Spring for GraphQL đang sử dụng. Khi muốn chủ động dùng setter binding, thiết kế DTO JavaBean đơn giản với default constructor và không thêm constructor dữ liệu cạnh tranh.

Không cần ép toàn bộ DTO trong ứng dụng theo cùng một phong cách. Chọn cách binding dựa trên yêu cầu bất biến, cấu trúc code và thư viện đang tích hợp.

## Khi DTO không có setter: direct field access

Setter binding cần accessor method để gán property. Nếu target object không có setter, Spring for GraphQL có tùy chọn fallback sang direct field access. Tùy chọn này hữu ích với một số DTO có field package-private hoặc private nhưng không cung cấp accessor theo quy ước.

GraphQlArgumentBinder hỗ trợ tùy chọn fallBackOnDirectFieldAccess; trong các phiên bản phù hợp, tùy chọn này có thể được cấu hình qua AnnotatedControllerConfigurer hoặc GraphQlArgumentBinder.Options.

Direct field access làm giảm yêu cầu về setter nhưng khiến việc binding phụ thuộc vào cấu trúc field của class. Với JavaBean truyền thống, setter rõ ràng thường dễ đọc và dễ kiểm soát hơn. Không nên bật fallback chỉ để che giấu DTO thiếu property mapping; hãy chọn một mô hình DTO nhất quán và kiểm thử nó.

## Lỗi thường gặp khi setter binding

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| DTO nhận toàn giá trị null | Thiếu setter hoặc tên setter/property không khớp input field | Kiểm tra JavaBean property và tên field trong SDL |
| Không tạo được DTO | Không có default constructor phù hợp | Thêm constructor không tham số hoặc dùng constructor binding |
| Field lồng nhau không được bind | DTO con thiếu constructor/setter hoặc sai cấu trúc | Kiểm tra từng DTO con và collection generic type |
| Sai kiểu khi binding | Kiểu Java không tương thích scalar hoặc enum | Đồng bộ SDL, scalar coercion và DTO |
| Một số property bị bỏ qua | Setter sai tên, không thể truy cập hoặc naming convention khác | Sửa setter hoặc cấu hình name resolver phù hợp |
| Binding thất bại trước khi controller chạy | GraphQL coercion hoặc GraphQlArgumentBinder phát sinh lỗi | Phân biệt lỗi schema input với lỗi Java binding; xem field path trong lỗi |
| Omitted và null bị xử lý giống nhau | Property chỉ dùng kiểu nullable thông thường | Dùng ArgumentValue<T> cho property cần phân biệt |
| Validation không chạy | Thiếu validation starter, @Valid hoặc cascade validation | Kiểm tra validator và annotation trên DTO |

Khi binding thất bại, GraphQlArgumentBinder tích lũy các vấn đề thành BindException với field path tương ứng thay vì chỉ báo một lỗi đầu tiên. Ví dụ lỗi ở items[0].quantity giúp xác định phần tử và property gây lỗi.

## Kiểm thử setter binding bằng GraphQlTester

Nên kiểm thử thông qua GraphQL operation để xác nhận cả schema, @Argument, DTO setter và controller. Ví dụ:

~~~java
@Test
void bindsJavaBeanInput() {
    graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring for GraphQL",
            "authorId", "author-12",
            "pageCount", 320))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
}
~~~

Trong test slice @GraphQlTest, mock BookService và capture CreateBookInput để xác minh các setter đã nhận đúng dữ liệu. Integration test có application context đầy đủ sẽ giúp xác minh cả schema resources, controller discovery và runtime wiring.

Nên kiểm thử:

1. Input đầy đủ được bind đúng vào JavaBean.
2. Field nullable bị bỏ qua hoặc nhận null theo đúng contract.
3. Input object lồng nhau và danh sách được bind đúng.
4. Enum và custom scalar được chuyển sang kiểu Java tương ứng.
5. Thiếu field non-null hoặc sai kiểu bị GraphQL từ chối.
6. DTO không có setter hoặc thiếu no-argument constructor tạo lỗi binding dễ nhận biết.
7. Bean Validation phát hiện giá trị không hợp lệ trước khi gọi service.
8. ArgumentValue phân biệt omitted với explicit null.
9. Service không bị gọi khi coercion hoặc binding thất bại.

Ngoài response, hãy xác minh đối số DTO mà service nhận được. Điều đó giúp phát hiện lỗi tên property hoặc setter ngay cả khi resolver vẫn trả về một response có vẻ hợp lệ.

## Thực hành tổng hợp

Tạo mutation đăng ký sách bằng setter binding:

1. Khai báo CreateBookInput trong SDL với title, authorId và pageCount.
2. Tạo class JavaBean CreateBookInput có no-argument constructor, getter và setter.
3. Tạo @MutationMapping nhận @Argument("input") CreateBookInput.
4. Thêm PublisherInput lồng trong CreateBookInput và bind bằng setter.
5. Thêm List<String> hoặc list DTO cho tags.
6. Dùng @Valid cùng Bean Validation để kiểm tra title và pageCount.
7. Viết GraphQlTester test cho input hợp lệ, thiếu field bắt buộc, kiểu sai và nested input.
8. Thử chuyển DTO sang Java record để so sánh constructor binding với setter binding.
9. Thêm một field patch dùng ArgumentValue<String> và kiểm tra omitted với explicit null.

Sau bài thực hành, hãy giải thích binder tạo object bằng cách nào, setter được gọi để gán property ra sao và lỗi binding khác lỗi GraphQL input validation như thế nào.

## Ghi nhớ

Setter binding là cách GraphQlArgumentBinder tạo DTO bằng default constructor rồi điền giá trị GraphQL qua setter. DTO thường cần constructor không tham số, setter theo tên JavaBean và kiểu Java tương thích với scalar/enum trong schema. Cơ chế binding được áp dụng đệ quy cho input object lồng nhau và collection; ConversionService hỗ trợ chuyển đổi kiểu khi cần. Dùng @Argument để nhận DTO, @Valid để kiểm tra constraint và ArgumentValue<T> khi cần phân biệt omitted với explicit null. Ưu tiên setter rõ ràng cho JavaBean mutable; dùng constructor binding cho DTO bất biến phù hợp hơn.

## Tài liệu tham khảo

- [Spring for GraphQL – Annotated Controllers, @Argument và Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQlArgumentBinder API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/GraphQlArgumentBinder.html)
- [AnnotatedControllerConfigurer API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/support/AnnotatedControllerConfigurer.html)
