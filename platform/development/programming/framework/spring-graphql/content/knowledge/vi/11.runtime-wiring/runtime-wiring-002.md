# DataFetcher registration trong Spring for GraphQL

Trong GraphQL Java, **DataFetcher** là thành phần cung cấp giá trị cho một field khi GraphQL thực thi operation. Schema SDL mô tả field có tên gì, nhận argument nào và trả về kiểu nào; DataFetcher thực hiện phần lấy dữ liệu hoặc gọi logic nghiệp vụ để tạo giá trị đó.

Spring for GraphQL hỗ trợ nhiều cách đăng ký DataFetcher. Với controller, các annotation như `@QueryMapping`, `@MutationMapping` và `@SchemaMapping` giúp Spring tự phát hiện phương thức và đăng ký handler tương ứng. Khi cần cấu hình ở mức GraphQL Java, có thể dùng `RuntimeWiringConfigurer` để gắn DataFetcher trực tiếp vào type và field trong schema.

## DataFetcher làm nhiệm vụ gì?

Mỗi field được GraphQL thực thi cần có cách lấy giá trị. Với field gốc như `Query.product`, DataFetcher có thể gọi service để tìm sản phẩm theo ID. Với field lồng nhau như `Product.seller`, DataFetcher có thể dùng object cha để tìm người bán liên quan.

Ví dụ SDL:

```graphql
type Query {
  product(id: ID!): Product
  products: [Product!]!
}

type Product {
  id: ID!
  name: String!
  seller: Seller
}

type Seller {
  id: ID!
  name: String!
}
```

Trong schema này, các field `product`, `products` và `seller` đều cần giá trị khi được client chọn. DataFetcher có thể được đăng ký tường minh cho cả ba field, hoặc GraphQL Java có thể dùng cơ chế mặc định để đọc property từ object nguồn nếu không có DataFetcher riêng.

DataFetcher không phải là nơi bắt buộc phải viết toàn bộ nghiệp vụ. Nên giữ DataFetcher mỏng: đọc argument hoặc source, gọi service phù hợp, sau đó trả kết quả đúng với kiểu đã khai báo trong SDL.

## Đăng ký DataFetcher bằng RuntimeWiringConfigurer

`RuntimeWiringConfigurer` là extension point của Spring for GraphQL để tùy chỉnh GraphQL Java runtime wiring. Có thể khai báo bean này trong một lớp `@Configuration`, sau đó đăng ký DataFetcher theo tên type và tên field trong schema.

```java
import graphql.schema.DataFetcher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

import java.util.List;

@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer productDataFetchers(
            ProductService productService,
            SellerService sellerService) {

        DataFetcher<Product> productById = environment -> {
            String id = environment.getArgument("id");
            return productService.findById(id).orElse(null);
        };

        DataFetcher<List<Product>> products = environment ->
                productService.findAll();

        DataFetcher<Seller> seller = environment -> {
            Product product = environment.getSource();
            return sellerService.findById(product.getSellerId()).orElse(null);
        };

        return builder -> builder
                .type("Query", type -> type
                        .dataFetcher("product", productById)
                        .dataFetcher("products", products))
                .type("Product", type -> type
                        .dataFetcher("seller", seller));
    }
}
```

Trong ví dụ này:

- `type("Query", ...)` chọn object type `Query` trong SDL.
- `dataFetcher("product", productById)` đăng ký DataFetcher cho field `Query.product`.
- `dataFetcher("products", products)` đăng ký DataFetcher cho field `Query.products`.
- `type("Product", ...)` chọn object type `Product`; DataFetcher `seller` xử lý field `Product.seller`.
- `ProductService` và `SellerService` được inject từ Spring container, giúp DataFetcher gọi logic nghiệp vụ mà không tự quản lý vòng đời dependency.

Tên type và field phải khớp với SDL. Nếu schema đổi tên `product` thành `findProduct` nhưng runtime wiring vẫn đăng ký `product`, cấu hình không còn mô tả đúng hợp đồng. Nên để ứng dụng kiểm tra schema lúc khởi động và có test xác nhận các field quan trọng được đăng ký.

## DataFetchingEnvironment cung cấp dữ liệu gì?

Khi GraphQL gọi DataFetcher, nó truyền vào một `DataFetchingEnvironment`. Đối tượng này chứa thông tin của field đang được thực thi và ngữ cảnh của operation.

| Phương thức | Nội dung |
| --- | --- |
| `getSource()` | Giá trị source do field cha cung cấp. Với field gốc, giá trị này phụ thuộc root object được truyền vào execution và thường là `null` nếu ứng dụng không cấu hình riêng. |
| `getArgument("name")` | Lấy giá trị của một argument theo tên. |
| `getArguments()` | Lấy toàn bộ arguments của field dưới dạng map. |
| `getGraphQlContext()` | Lấy GraphQL context dùng chung trong quá trình thực thi request. |
| `getLocalContext()` | Lấy local context được truyền từ bước thực thi cha xuống field con. |
| `getSelectionSet()` | Xem các field con được client chọn. |
| `getDataLoader("name")` | Lấy DataLoader đã đăng ký với registry của request. |
| `getExecutionStepInfo()` | Lấy thông tin về vị trí và kiểu của field trong execution tree. |

### Đọc argument

Với field có argument:

```graphql
type Query {
  product(id: ID!): Product
}
```

DataFetcher đọc argument bằng tên:

```java
DataFetcher<Product> productById = environment -> {
    String id = environment.getArgument("id");
    return productService.findById(id).orElse(null);
};
```

Tên argument trong `getArgument("id")` phải trùng với tên khai báo trong SDL. Với input object phức tạp, có thể lấy toàn bộ giá trị bằng `getArgument("input")`; tùy cách cấu hình mapping, giá trị có thể được biểu diễn dưới dạng map hoặc được chuyển đổi sang kiểu Java phù hợp.

### Đọc source của field lồng nhau

Với field `Product.seller`, source chính là object `Product` đã được resolve ở bước cha. DataFetcher dùng source để tìm dữ liệu liên quan:

```java
DataFetcher<Seller> sellerFetcher = environment -> {
    Product product = environment.getSource();
    return sellerService.findById(product.getSellerId()).orElse(null);
};
```

Điểm này giúp phân biệt hai trường hợp: `getArgument()` lấy dữ liệu client gửi vào field, còn `getSource()` lấy source mà GraphQL truyền từ bước cha. Không nên giả định mọi field đều có source giống nhau; field gốc thường không có object nghiệp vụ cha và có thể nhận source `null`.

### Đọc GraphQL context

Context dùng để chia sẻ thông tin theo request như principal đã xác thực, tenant hoặc correlation ID. Thông tin này thường được thêm vào bởi interceptor hoặc thành phần xử lý request trước khi DataFetcher chạy.

```java
DataFetcher<List<Product>> productsFetcher = environment -> {
    String tenantId = environment.getGraphQlContext().get("tenantId");
    return productService.findAllForTenant(tenantId);
};
```

Context phải được tạo từ nguồn đáng tin cậy phía server. Không dùng giá trị role hoặc tenant do client tự khai báo trong argument để thay thế việc xác thực. Với dữ liệu thay đổi theo request, tránh lưu vào field mutable của singleton DataFetcher hoặc singleton service.

## Default PropertyDataFetcher

Không phải field nào cũng cần đăng ký DataFetcher tường minh. GraphQL Java có `PropertyDataFetcher` làm cơ chế mặc định cho field object khi không có fetcher riêng. Nó tìm giá trị từ object nguồn thông qua property, getter hoặc key của map theo các quy tắc truy cập thuộc tính của GraphQL Java.

Ví dụ Java:

```java
public class Product {
    private String id;
    private String name;

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Khi DataFetcher của `Query.product` trả về một `Product`, GraphQL có thể tự lấy `id` và `name` từ getter tương ứng mà không cần đăng ký fetcher riêng cho từng field.

PropertyDataFetcher phù hợp khi field phản ánh trực tiếp dữ liệu đã có trong object nguồn. Nên đăng ký DataFetcher riêng khi cần gọi service/repository, áp dụng quy tắc nghiệp vụ, chuyển đổi dữ liệu, kiểm tra quyền hoặc tính toán giá trị.

## DataFetcher đồng bộ và bất đồng bộ

DataFetcher có thể trả về giá trị đồng bộ hoặc kết quả bất đồng bộ. Với một truy vấn đơn giản trong bộ nhớ, trả trực tiếp object là đủ. Khi gọi dịch vụ I/O bất đồng bộ, có thể trả về `CompletionStage` hoặc `CompletableFuture` để GraphQL tiếp tục xử lý khi kết quả sẵn sàng.

Ví dụ service đã cung cấp phương thức bất đồng bộ:

```java
DataFetcher<CompletableFuture<Product>> productFetcher = environment -> {
    String id = environment.getArgument("id");
    return productService.findByIdAsync(id);
};
```

`CompletableFuture` cho phép GraphQL phối hợp kết quả mà không cần DataFetcher chặn thread để chờ I/O. Nếu tự tạo future bằng `supplyAsync`, hãy dùng executor được quản lý với giới hạn phù hợp thay vì mặc định đẩy mọi công việc lên common pool.

Với các ứng dụng dùng Reactor, Spring for GraphQL cũng hỗ trợ kiểu reactive ở các điểm tích hợp tương ứng. Hãy giữ kiểu trả về nhất quán với stack đang dùng và tránh chuyển qua lại giữa blocking và reactive mà không có ranh giới rõ ràng.

## Trả lỗi và dữ liệu một phần

Khi DataFetcher ném exception, GraphQL ghi nhận execution error tại field đang thực thi. Spring for GraphQL cho phép ánh xạ exception sang GraphQL error bằng cơ chế như `DataFetcherExceptionResolver`, giúp kiểm soát message, error code và thông tin được phép công bố cho client.

Với một số tình huống, DataFetcher có thể trả về `DataFetcherResult` để kết hợp dữ liệu và lỗi trong cùng kết quả:

```java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;

DataFetcherResult<Product> result = DataFetcherResult.<Product>newResult()
        .data(product)
        .error(GraphqlErrorBuilder.newError(environment)
                .message("Một số thông tin bổ sung chưa tải được")
                .build())
        .build();
```

`DataFetcherResult` hữu ích khi một field có thể trả dữ liệu chính nhưng đồng thời cần báo lỗi hoặc metadata bổ sung. Cần thiết kế nullability trong SDL phù hợp vì lỗi ở field Non-Null có thể làm null lan lên field cha. Không đưa stack trace, câu SQL, token hoặc thông tin hạ tầng vào lỗi trả về client.

## DataFetcher cho field lồng nhau và vấn đề N+1

GraphQL thực thi field theo selection set. Nếu client yêu cầu danh sách nhiều Product và mỗi Product đều có field `seller`, DataFetcher của `Product.seller` có thể được gọi một lần cho mỗi Product.

Ví dụ query:

```graphql
query ProductsWithSellers {
  products {
    id
    name
    seller {
      id
      name
    }
  }
}
```

Nếu `products` trả về 100 sản phẩm và mỗi lần chạy `seller` đều gọi một truy vấn database riêng, hệ thống có thể tạo 1 truy vấn lấy sản phẩm cộng 100 truy vấn lấy người bán. Đây là vấn đề N+1.

Đăng ký DataFetcher đúng cách chưa tự giải quyết N+1. Có thể dùng DataLoader hoặc `@BatchMapping` trong Spring for GraphQL để gom các lần tải seller theo batch. DataLoader thường được đăng ký theo request để các key trong cùng operation được gom lại và ánh xạ kết quả về đúng source object.

Khi có thể, hãy dùng `@BatchMapping` cho field quan hệ phù hợp với controller model của Spring. Nếu đang dùng DataFetcher cấp thấp, có thể lấy DataLoader từ `DataFetchingEnvironment` và gọi `load(key)` thay vì gọi repository trực tiếp cho từng parent.

## Chọn RuntimeWiringConfigurer hay annotation mapping?

Spring for GraphQL cung cấp hai phong cách phổ biến để đăng ký logic xử lý field:

| Cách làm | Khi phù hợp |
| --- | --- |
| `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` | Root operation được triển khai trong controller Spring; muốn inject dependency và viết handler theo kiểu phương thức. |
| `@SchemaMapping` | Field của object type cần resolver riêng, đặc biệt là quan hệ hoặc computed field. |
| `RuntimeWiringConfigurer` + `DataFetcher` | Cần tùy chỉnh runtime wiring trực tiếp, tích hợp GraphQL Java hoặc đăng ký fetcher theo cấu hình. |

Ví dụ annotation mapping:

```java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id).orElse(null);
    }
}
```

Spring for GraphQL tự phát hiện controller và đăng ký phương thức làm DataFetcher cho field tương ứng. Nếu đã dùng annotation mapping cho `Query.product`, không nên đồng thời đăng ký một DataFetcher khác cho chính field đó trong `RuntimeWiringConfigurer`; hai cơ chế cùng cấu hình một field có thể dẫn tới handler được chọn phụ thuộc thứ tự wiring và làm ứng dụng khó bảo trì.

Có thể kết hợp hai cách trong cùng ứng dụng nếu chúng phục vụ các field khác nhau. Chẳng hạn controller xử lý `Query.product`, còn `RuntimeWiringConfigurer` đăng ký một custom scalar hoặc DataFetcher cho field riêng chưa có annotation handler.

## Kiểm thử DataFetcher registration

Kiểm thử nên xác nhận schema field thực sự gọi đúng logic và trả response đúng cấu trúc. Với Spring for GraphQL, `GraphQlTester` cho phép gửi operation và kiểm tra dữ liệu trả về:

```java
@Test
void productQueryUsesRegisteredFetcher() {
    graphQlTester.document("""
        query {
          product(id: "p-100") {
            id
            name
          }
        }
        """)
        .execute()
        .path("product.id")
        .entity(String.class)
        .isEqualTo("p-100");
}
```

Ngoài kết quả thành công, nên kiểm tra:

- Field name trong SDL khớp với tên dùng trong `.dataFetcher(...)`.
- Argument được đọc đúng và xử lý khi thiếu hoặc không hợp lệ.
- Field lồng nhau nhận đúng source object.
- Giá trị không tìm thấy tuân theo nullability đã khai báo.
- Exception được ánh xạ thành lỗi công khai phù hợp.
- DataFetcher bất đồng bộ hoàn tất đúng và xử lý lỗi từ future.
- Context và quyền truy cập được áp dụng đúng theo request.
- DataLoader hoặc batch fetcher giảm số lần gọi repository khi trả về danh sách.

Khi kiểm thử bean `RuntimeWiringConfigurer`, nên khởi tạo `GraphQlSource` hoặc Spring application context để xác minh cấu hình thực sự được nạp. Unit test riêng lambda DataFetcher không chứng minh rằng nó đã được đăng ký vào schema đang chạy.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field trả `null` dù service có dữ liệu | DataFetcher đăng ký sai type/field hoặc source không đúng. | Đối chiếu SDL, tên mapping và `getSource()`. |
| `getArgument()` trả null | Sai tên argument, input nullable hoặc client không gửi giá trị. | Kiểm tra SDL, operation và variables. |
| DataFetcher không được gọi | Controller mapping hoặc wiring chưa được đăng ký, hoặc operation không chọn field. | Kiểm tra startup configuration, schema và query. |
| Field lồng nhau không resolve | Object cha không có property tương ứng và thiếu DataFetcher riêng. | Dùng `@SchemaMapping` hoặc đăng ký DataFetcher cho field đó. |
| Một field bị xử lý bởi handler không mong muốn | Annotation mapping và RuntimeWiringConfigurer cùng đăng ký một field. | Chọn một cơ chế làm handler duy nhất cho field. |
| Query danh sách tạo nhiều truy vấn database | Resolver quan hệ gọi repository riêng cho từng object. | Dùng DataLoader hoặc `@BatchMapping`. |
| Lỗi nội bộ xuất hiện trong response | Exception chưa được ánh xạ theo chính sách API. | Cấu hình `DataFetcherExceptionResolver` và kiểm soát thông tin lỗi. |

## Ghi nhớ

DataFetcher là thành phần cung cấp giá trị cho từng field trong quá trình GraphQL thực thi. Nó nhận `DataFetchingEnvironment`, từ đó đọc argument, source object, GraphQL context và thông tin selection. GraphQL Java có thể dùng `PropertyDataFetcher` mặc định cho các field phản ánh trực tiếp property của object nguồn.

Trong Spring for GraphQL, dùng `RuntimeWiringConfigurer` để đăng ký DataFetcher trực tiếp theo type và field; dùng `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping` khi muốn triển khai handler bằng controller annotation. Hãy chọn một cơ chế cho mỗi field, giữ DataFetcher mỏng, xử lý lỗi có kiểm soát và dùng DataLoader hoặc `@BatchMapping` khi field lồng nhau có nguy cơ N+1.
