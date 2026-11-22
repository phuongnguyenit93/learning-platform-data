# Gateway và subgraph trong GraphQL Federation

GraphQL Federation cho phép nhiều GraphQL service độc lập cùng đóng góp vào một API thống nhất. Mỗi service được gọi là **subgraph** và sở hữu một phần schema cùng dữ liệu của domain mình. Một **gateway/router** đứng trước các subgraph, kết hợp schema của chúng thành supergraph, lập kế hoạch thực thi query, gọi các subgraph cần thiết và ghép kết quả trả về cho client.

Spring for GraphQL có tích hợp với thư viện `federation-jvm` để xây dựng một service Spring GraphQL hoạt động như subgraph. Tích hợp này cung cấp `FederationSchemaFactory` và `@EntityMapping` để xử lý entity representation mà gateway gửi tới. Gateway là một tiến trình riêng, có thể dùng Apollo Router, GraphOS Router hoặc một router tương thích Federation.

## 1. Vì sao cần gateway và subgraph?

Trong một hệ thống thương mại điện tử, dữ liệu có thể được quản lý bởi nhiều nhóm:

- Product service quản lý sản phẩm, giá và danh mục.
- Review service quản lý đánh giá sản phẩm.
- Account service quản lý khách hàng và hồ sơ.
- Order service quản lý đơn hàng và trạng thái giao dịch.

Nếu mỗi service chỉ cung cấp GraphQL endpoint riêng, client phải biết endpoint nào chứa dữ liệu nào, tự gọi nhiều lần và tự ghép kết quả. Federation đặt một router ở phía trước để client chỉ gọi một GraphQL endpoint.

Ví dụ client muốn lấy sản phẩm cùng đánh giá:

```graphql
query ProductDetails {
    products {
        id
        name
        price
        reviews {
            id
            rating
            comment
        }
    }
}
```

Field `products`, `name` và `price` có thể do Products subgraph sở hữu. Field `reviews` do Reviews subgraph sở hữu. Gateway hiểu quan hệ giữa hai schema và gọi cả hai service để tạo một response.

## 2. Phân biệt gateway, subgraph và supergraph

| Thành phần | Vai trò | Trách nhiệm chính |
|---|---|---|
| Subgraph | GraphQL service thuộc một domain | Sở hữu một phần schema, resolver và dữ liệu. |
| Gateway/router | Điểm vào GraphQL thống nhất | Composition, query planning, định tuyến và ghép response. |
| Supergraph | Schema liên kết của toàn hệ thống | Mô tả các type, field, entity và subgraph chịu trách nhiệm. |
| Subgraph schema | Schema do một service công bố | Mô tả phần graph mà service đóng góp. |

Supergraph không nhất thiết là một server hay database riêng. Nó là schema đã được composition cùng metadata định tuyến để router biết field nào do subgraph nào xử lý.

Gateway Federation cũng khác một HTTP reverse proxy thông thường. Reverse proxy có thể chuyển request tới service theo URL/path. Federation router hiểu GraphQL schema và selection set, có thể chia một operation thành nhiều request GraphQL con rồi ghép các kết quả theo quan hệ entity.

## 3. Kiến trúc tổng thể

```text
                         GraphQL client
                               |
                               v
                     Gateway / Graph Router
                     - supergraph schema
                     - query planner
                     - subgraph routing
                     - response merge
                        /          \
                       /            \
                      v              v
             Products subgraph   Reviews subgraph
             Spring GraphQL      Spring GraphQL
             Product fields      Product.reviews
                  |                   |
                  v                   v
             Product DB           Review DB
```

Các service có thể được triển khai, scale và phát hành độc lập. Gateway cung cấp một API thống nhất cho client, còn mỗi subgraph giữ quyền sở hữu dữ liệu và logic domain của mình.

## 4. Gateway thực hiện những việc gì?

Gateway/router thường đảm nhiệm các công việc sau:

1. Nạp supergraph schema đã được composition.
2. Nhận GraphQL operation từ client.
3. Validate operation theo supergraph schema.
4. Lập query plan xác định field nào cần gọi subgraph nào.
5. Gửi request con tới các subgraph, có thể chạy song song khi phụ thuộc dữ liệu cho phép.
6. Truyền entity representation để subgraph khác phân giải phần field mà nó sở hữu.
7. Ghép kết quả và lỗi thành GraphQL response.
8. Áp dụng các chính sách ở lớp router như giới hạn request, tracing, timeout và routing configuration.

Gateway không nên trở thành nơi chứa quy tắc nghiệp vụ của Product, Order hoặc Review. Quy tắc domain thuộc subgraph sở hữu dữ liệu đó.

## 5. Subgraph chịu trách nhiệm những gì?

Một subgraph cần:

- Công bố SDL mô tả các type và field mà service sở hữu.
- Khai báo entity key nếu type cần được các subgraph khác tham chiếu.
- Cung cấp resolver cho field do service sở hữu.
- Có khả năng tải entity từ representation mà gateway gửi tới.
- Trả dữ liệu và lỗi theo hợp đồng GraphQL.
- Bảo vệ dữ liệu bằng authorization, tenant isolation và service-to-service security.
- Duy trì tương thích schema để supergraph có thể composition.

Subgraph không cần biết client đã gửi query ban đầu như thế nào. Nó nhận một GraphQL request con từ gateway và thực hiện phần công việc được phân công.

## 6. Entity là cầu nối giữa các subgraph

Trong Federation, một object type được nhiều subgraph đóng góp field thường được mô hình hóa thành **entity**. Entity có một hoặc nhiều key xác định duy nhất một instance.

Ví dụ Product entity có key là `id`:

```graphql
type Product @key(fields: "id") {
    id: ID!
    name: String!
    price: Float!
}
```

`@key(fields: "id")` cho gateway biết có thể nhận diện Product bằng field `id`. Subgraph khác có thể định nghĩa thêm field trên cùng entity Product; gateway dùng key này để yêu cầu subgraph sở hữu field phân giải dữ liệu.

Representation của một entity có dạng JSON:

```json
{
  "__typename": "Product",
  "id": "product-101"
}
```

- `__typename` xác định entity type.
- `id` là key field được khai báo trong `@key`.

Với composite key, representation phải có đủ tất cả field thuộc field set của key.

## 7. `@key` và quyền sở hữu field

Một supergraph có thể có nhiều subgraph cùng định nghĩa entity Product, nhưng mỗi field cần có chủ sở hữu rõ ràng.

Ví dụ:

| Subgraph | Entity | Field sở hữu |
|---|---|---|
| Products | `Product @key(fields: "id")` | `id`, `name`, `price`. |
| Reviews | `Product @key(fields: "id")` | `id`, `reviews`. |

Key field là thông tin nhận diện chung. Field nghiệp vụ như `name`, `price`, `reviews` được phân công cho subgraph tương ứng.

Trong Federation 2, các subgraph có thể khai báo cùng entity type với cùng key. Không cần dùng cú pháp `@extends`/`@external` chỉ để biểu thị việc mở rộng entity như cách thường gặp ở Federation 1. `@extends` chủ yếu phục vụ schema theo kiểu Federation 1; `@external` vẫn được dùng trong Federation 2 cho field được tham chiếu bởi `@requires` hoặc `@provides` nhưng không do subgraph hiện tại sở hữu.

Trong Federation 2, các field nằm trong `@key` tự động được xem là shareable, vì vậy `id` trong ví dụ không cần thêm `@shareable`. Nếu nhiều subgraph cùng chịu trách nhiệm phân giải một field khác ngoài key, phải dùng `@shareable` trong mọi subgraph định nghĩa field đó và bảo đảm các resolver có ngữ nghĩa tương thích. Không đánh dấu `@shareable` chỉ để vượt qua lỗi composition.

## 8. Composition tạo ra supergraph schema

Composition là bước kết hợp các subgraph schema và kiểm tra tính tương thích. Kết quả là supergraph schema chứa metadata cho router biết cách phân giải các field.

Quy trình cơ bản:

```text
Products schema -----+
                     |
Reviews schema ------+----> Composition ----> supergraph.graphql
                     |                            |
Accounts schema -----+                            v
                                             Gateway/router
```

Composition có thể được thực hiện qua Apollo GraphOS build pipeline hoặc bằng Rover CLI. Với quy trình CI/CD, cần validate composition trước khi triển khai schema mới. Trong production, nên tạo và kiểm tra supergraph artifact ở build/release pipeline; không nên phụ thuộc vào việc router tự introspect và composition động tất cả subgraph mỗi lần khởi động.

Một số lỗi composition phổ biến:

- Hai subgraph định nghĩa cùng một field nhưng không khai báo shareable phù hợp.
- Kiểu trả về hoặc argument type của field dùng chung không tương thích.
- Entity key không nhất quán giữa các subgraph.
- Một field không thể được phân giải trong một số query plan hợp lệ.
- Subgraph sử dụng directive mà Federation version được chọn chưa hỗ trợ.

## 9. Federation 2 và directive `@link`

Federation 2 yêu cầu schema khai báo `@link` để opt-in vào Federation specification và import các directive được sử dụng.

Ví dụ:

```graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key"]
    )
```

Nếu schema dùng thêm `@shareable`, `@requires` hoặc directive khác, cần import các directive đó trong `import` list hoặc sử dụng namespace tương ứng theo quy tắc Federation.

`@link` cho biết schema đang dùng Federation 2. Version trong URL phải tương thích với phiên bản composition và router. Không chọn Federation version mới hơn khả năng hỗ trợ của router hoặc thư viện subgraph.

## 10. Ví dụ hai subgraph Products và Reviews

Products subgraph sở hữu thông tin sản phẩm:

```graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key"]
    )

type Query {
    products: [Product!]!
    product(id: ID!): Product
}

type Product @key(fields: "id") {
    id: ID!
    name: String!
    description: String
    price: Float!
}
```

Reviews subgraph đóng góp field `reviews` cho cùng Product entity:

```graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key"]
    )

type Query {
    reviewsByProduct(productId: ID!): [Review!]!
}

type Product @key(fields: "id") {
    id: ID!
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
```

`Product.id` là key để Reviews subgraph nhận diện entity. Products subgraph sở hữu `name`, `description`, `price`; Reviews subgraph sở hữu `reviews`.

Trong một schema thật, các subgraph phải có SDL hợp lệ với GraphQL root operation và các directive được hỗ trợ. Một subgraph có thể chủ yếu phục vụ entity resolution mà không cần query nghiệp vụ riêng; hãy kiểm tra schema cuối cùng do federation library tạo ra qua `_service` và `_entities`.

Resolver ở Products subgraph có thể cung cấp query gốc và tải Product theo entity key:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class ProductsController {

    private final ProductCatalog products;

    ProductsController(ProductCatalog products) {
        this.products = products;
    }

    @QueryMapping
    List<Product> products() {
        return products.findAll();
    }

    @EntityMapping(name = "Product")
    Product productEntity(@Argument("id") String id) {
        return products.findById(id).orElse(null);
    }
}
```

`ProductCatalog` là service/repository adapter của Products domain. Khi router cần field do Products subgraph sở hữu từ một representation, `productEntity` tải Product thật từ kho dữ liệu của service.

Các kiểu dùng trong ví dụ:

```java
import java.util.List;
import java.util.Optional;

public record Product(String id, String name, String description, double price) {}

public interface ProductCatalog {
    List<Product> findAll();
    Optional<Product> findById(String id);
}
```

## 11. Spring for GraphQL hỗ trợ subgraph như thế nào?

Spring for GraphQL tích hợp thư viện `federation-jvm`, được xây dựng trên GraphQL Java. Thư viện này biến schema GraphQL thông thường thành schema tương thích Federation bằng cách bổ sung các thành phần Federation cần thiết, bao gồm directive, scalar `_Any`, union `_Entity` và resolver cho entity. Bảng tương thích của Apollo hiện liệt kê Spring GraphQL cùng `federation-jvm` và đánh dấu các thành phần Federation 1/2 như `_service`, `@key`, `@link`, `@shareable`, `@requires`, `@provides` và các directive mở rộng là được hỗ trợ. Khi dùng directive mới, vẫn cần kiểm tra phiên bản thư viện và router đang triển khai.

Spring cung cấp hai thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| `FederationSchemaFactory` | Tạo federated `GraphQLSchema`, đăng ký resolver cho `_entities` và type resolver. |
| `@EntityMapping` | Ánh xạ method Java để tải entity từ representation do gateway gửi tới. |

Các field còn lại vẫn có thể dùng `@QueryMapping`, `@SchemaMapping`, `@BatchMapping` và DataLoader như một Spring GraphQL service thông thường.

Spring for GraphQL hỗ trợ triển khai subgraph. Gateway/router được triển khai riêng và có thể dùng Apollo Router hoặc một implementation tương thích Federation.

## 12. Thêm dependency Federation JVM

Ngoài starter Spring GraphQL, thêm thư viện Federation JVM vào service cần chạy như subgraph:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'com.apollographql.federation:federation-graphql-java-support:<compatible-version>'
}
```

Thay `<compatible-version>` bằng phiên bản được công bố và tương thích với phiên bản GraphQL Java mà Spring for GraphQL đang sử dụng. Không tự nâng GraphQL Java riêng lẻ nếu dependency management của Spring Boot đã quản lý phiên bản đó.

Artifact `federation-graphql-java-support` cung cấp phần tích hợp Federation cho GraphQL Java. Spring for GraphQL sử dụng thư viện này thông qua `FederationSchemaFactory`.

## 13. Cấu hình `FederationSchemaFactory`

Với Spring Boot, khai báo bean `FederationSchemaFactory` và `GraphQlSourceBuilderCustomizer` để dùng factory khi tạo schema:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration(proxyBeanMethods = false)
class FederationConfiguration {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {

        return builder -> builder.schemaFactory(factory::createGraphQLSchema);
    }
}
```

Import `GraphQlSourceBuilderCustomizer` ở trên dành cho Spring Boot 3.x. Với Spring Boot 4.x, package tương ứng là `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer`. `FederationSchemaFactory` vẫn thuộc package `org.springframework.graphql.data.federation`.

Sau khi cấu hình, Spring Boot sử dụng factory để tạo schema Federation. `FederationSchemaFactory` phát hiện các method `@EntityMapping` trong annotated controller và đăng ký logic xử lý entity.

## 14. `@EntityMapping` xử lý entity representation

Khi gateway gọi `_entities`, nó gửi một danh sách representation. Mỗi representation chứa `__typename` và các key field. `@EntityMapping` ánh xạ một method Java để tìm hoặc dựng entity tương ứng.

Ví dụ trong Reviews subgraph:

```java
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

public record Product(String id) {}

@Controller
class ProductEntityController {

    @EntityMapping
    Product product(@Argument("id") String id) {
        return new Product(id);
    }
}
```

Tên method `product` được chuyển thành entity type `Product` theo quy ước mặc định. Có thể chỉ định tên entity rõ ràng bằng `@EntityMapping(name = "Product")` nếu method không theo quy ước tên.

Ở ví dụ này, Reviews subgraph không sở hữu toàn bộ Product. Nó chỉ cần một reference có `id` để các resolver field của subgraph phân giải dữ liệu Review. Trong hệ thống thực tế, entity mapping cần áp dụng chính sách truy cập và xác minh sự tồn tại khi nghiệp vụ yêu cầu.

## 15. Phân giải field do subgraph sở hữu

Sau khi entity Product được dựng từ representation, `@SchemaMapping` có thể xử lý field `reviews`:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class ProductReviewController {

    private final ReviewQueryService reviews;

    ProductReviewController(ReviewQueryService reviews) {
        this.reviews = reviews;
    }

    @QueryMapping
    List<Review> reviewsByProduct(@Argument String productId) {
        return reviews.findByProductId(productId);
    }

    @SchemaMapping(typeName = "Product", field = "reviews")
    List<Review> reviews(Product product) {
        return reviews.findByProductId(product.id());
    }
}
```

`@EntityMapping` giải quyết câu hỏi “representation này tương ứng với entity nào?”. `@SchemaMapping` giải quyết câu hỏi “field mà Reviews subgraph sở hữu có giá trị gì?”. Hai method có trách nhiệm khác nhau và phối hợp để gateway lấy dữ liệu.

Model và service được controller sử dụng:

```java
import java.util.List;

public record Review(String id, int rating, String comment) {}

public interface ReviewQueryService {
    List<Review> findByProductId(String productId);
}
```

## 16. Entity mapping có thể nhận representation đầy đủ

Nếu entity dùng composite key hoặc cần nhiều thông tin trong representation, method có thể nhận `Map<String, Object>`:

Trong ví dụ này, `Product` là model thay thế có thêm `region`; field `region` cũng phải xuất hiện trong SDL và trong `@key` của subgraph.

SDL tương ứng khai báo cả hai field trong key:

```graphql
type Product @key(fields: "id region") {
    id: ID!
    region: String!
}
```

```java
import java.util.Map;

import org.springframework.graphql.data.federation.EntityMapping;

public record Product(String id, String region) {}

@EntityMapping(name = "Product")
Product product(Map<String, Object> representation) {
    String id = (String) representation.get("id");
    String region = (String) representation.get("region");

    return new Product(id, region);
}
```

Các method `@EntityMapping` có thể nhận những tham số như:

- `@Argument` để lấy một key field đã được bind và chuyển kiểu.
- `Map<String, Object>` để đọc toàn bộ representation.
- `List<Map<String, Object>>` khi xử lý nhiều representation trong một method.
- `@ContextValue`, `@LocalContextValue`, `GraphQLContext`.
- `Principal` hoặc `@AuthenticationPrincipal` nếu Spring Security context có sẵn.
- `DataLoader<I, E>` để tải entity bất đồng bộ hoặc theo batch.
- `DataFetchingFieldSelectionSet` và `DataFetchingEnvironment` khi cần thông tin execution.

Method có thể trả entity trực tiếp, `Mono`, `CompletableFuture` hoặc `Callable` theo kiểu xử lý phù hợp.

Nếu `@EntityMapping` ném exception, có thể dùng `@GraphQlExceptionHandler` trong cùng controller hoặc `@ControllerAdvice` để ánh xạ exception thành `GraphQLError`. Lỗi đó được đưa vào response của `_entities`, vì vậy gateway có thể xử lý như lỗi GraphQL từ subgraph.

## 17. Batch load nhiều entity

Gateway có thể gửi nhiều representation của cùng entity type trong một lần `_entities` request. Spring for GraphQL cho phép method `@EntityMapping` nhận danh sách ID và trả về `List` hoặc `Flux` entity theo đúng thứ tự representation.

Ví dụ:

```java
import java.util.List;

import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;

@EntityMapping
List<Product> product(@Argument List<String> idList) {
    return productService.findAllInOrder(idList);
}
```

Tên tham số `idList` theo quy ước giúp Spring nhận biết đây là danh sách giá trị của key `id`. Có thể khai báo tên argument rõ ràng bằng `@Argument`.

Điểm quan trọng là kết quả phải giữ cùng thứ tự với danh sách representation tương ứng. Nếu service trả kết quả theo thứ tự database tùy ý, cần ghép lại theo ID trước khi return.

## 18. Kết hợp `@EntityMapping` với DataLoader

Khi entity resolution cần gom nhiều key hoặc tải dữ liệu bất đồng bộ, có thể dùng DataLoader được đăng ký qua `BatchLoaderRegistry`:

Đây là phương án thay thế cho việc gọi service trực tiếp trong `@EntityMapping`; chỉ cần chọn một cách đăng ký entity loader phù hợp với subgraph.

```java
import java.util.Set;

import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
class ProductBatchLoaderConfiguration {

    ProductBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            ProductService products) {

        registry.forTypePair(String.class, Product.class)
            .registerMappedBatchLoader((ids, environment) ->
                products.findAllByIds(ids)
            );
    }
}
```

Service được giả định trả về map theo key:

```java
import java.util.Map;
import java.util.Set;

import reactor.core.publisher.Mono;

public interface ProductService {
    Mono<Map<String, Product>> findAllByIds(Set<String> ids);
}
```

Entity mapping sử dụng DataLoader:

```java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

@Controller
class ProductEntityDataLoaderController {

    @EntityMapping
    CompletableFuture<Product> product(
            @Argument String id,
            DataLoader<String, Product> productLoader) {

        return productLoader.load(id);
    }
}
```

DataLoader giúp gom key trong cùng GraphQL execution và cache theo request. Điều này có thể giảm số lần truy cập database khi router gửi nhiều representation. Cache DataLoader không phải cache dùng chung giữa các request.

## 19. `_service` và `_entities` là gì?

Federation subgraph cần hai field đặc biệt được tích hợp vào schema:

| Field | Mục đích |
|---|---|
| `Query._service { sdl }` | Trả SDL của subgraph, bao gồm các Federation directive để router/composition tool đọc schema. |
| `Query._entities(representations)` | Cho phép router gửi entity representation để subgraph trả về entity tương ứng. |

`FederationSchemaFactory` cùng federation-jvm thiết lập các thành phần Federation cần thiết, bao gồm resolver cho `_entities` và type resolver của `_Entity`.

`_service` chủ yếu phục vụ schema discovery/composition. Nó không phải field nghiệp vụ dành cho client cuối và không xuất hiện trong API supergraph đã composition. Cần quản lý quyền truy cập tới endpoint subgraph và không expose các endpoint nội bộ ra Internet nếu không có lý do.

## 20. Gateway chuyển entity representation như thế nào?

Giả sử client gửi query:

```graphql
query {
    products {
        id
        name
        reviews {
            rating
            comment
        }
    }
}
```

Gateway biết `products` và `name` thuộc Products subgraph, còn `reviews` thuộc Reviews subgraph. Query plan khái quát:

1. Gọi Products subgraph để lấy `id`, `name` và các key cần thiết.
2. Từ mỗi Product tạo representation gồm `__typename` và `id`.
3. Gọi Reviews subgraph bằng `_entities(representations: ...)`.
4. Reviews subgraph dùng `@EntityMapping` để nhận diện Product và `@SchemaMapping` để lấy reviews.
5. Gateway ghép reviews vào đúng Product rồi trả một response cho client.

Request nội bộ tới Reviews subgraph có dạng:

```graphql
query ResolveProductReviews($representations: [_Any!]!) {
    _entities(representations: $representations) {
        ... on Product {
            reviews {
                rating
                comment
            }
        }
    }
}
```

Một representation tương ứng:

```json
{
  "__typename": "Product",
  "id": "product-101"
}
```

`_Entity` là union nên router dùng inline fragment `... on Product` để yêu cầu field theo entity type cụ thể.

## 21. Chạy thử subgraph và gateway tại local

Một môi trường local đơn giản có thể chạy hai Spring Boot service:

| Service | Endpoint ví dụ | Port |
|---|---|---:|
| Products subgraph | `http://localhost:8080/graphql` | 8080 |
| Reviews subgraph | `http://localhost:8081/graphql` | 8081 |
| Apollo Router | `http://localhost:4000/graphql` | 4000 |

Mỗi subgraph phải được cấu hình `FederationSchemaFactory`, có SDL Federation hợp lệ và các controller cần thiết. Khởi động hai ứng dụng Spring Boot trước khi chạy router.

## 22. Khai báo supergraph composition bằng Rover

Tạo file `supergraph.yaml`:

```yaml
federation_version: =2.11.0
subgraphs:
  products:
    routing_url: http://localhost:8080/graphql
    schema:
      file: ./products-schema.graphql
  reviews:
    routing_url: http://localhost:8081/graphql
    schema:
      file: ./reviews-schema.graphql
```

File này chỉ ra schema file và routing URL của từng subgraph. Chọn Federation version tương thích với phiên bản router và các directive mà subgraph sử dụng. `2.11.0` ở đây là phiên bản minh họa; cần kiểm tra compatibility matrix khi nâng version.

Sau khi cài Rover CLI, composition supergraph:

```bash
rover supergraph compose \
  --config ./supergraph.yaml \
  --output ./supergraph.graphql
```

Lệnh tạo `supergraph.graphql` từ các subgraph schema. Nếu composition thất bại, đọc lỗi để sửa xung đột schema trước khi khởi động gateway.

## 23. Chạy Apollo Router

Tạo file `router.yaml` tối giản:

```yaml
supergraph:
  listen: 127.0.0.1:4000
  path: /graphql
```

Khởi động router với supergraph đã composition:

```bash
./router --config ./router.yaml --supergraph ./supergraph.graphql
```

Router lấy routing URL của subgraph từ supergraph schema. Có thể override URL trong cấu hình router khi môi trường triển khai thay đổi địa chỉ service.

## 24. Gửi query qua gateway

Client chỉ cần gửi query tới endpoint của router:

```bash
curl http://localhost:4000/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query { products { id name reviews { rating comment } } }"}'
```

Client không cần biết Products và Reviews đang chạy ở port nào. Gateway điều phối các subgraph và trả về một GraphQL response thống nhất.

## 25. Kiểm tra trực tiếp subgraph

Trước khi kiểm tra toàn bộ supergraph, cần xác minh từng subgraph hoạt động độc lập.

Kiểm tra Federation SDL:

```graphql
query FederationServiceInfo {
    _service {
        sdl
    }
}
```

Response phải chứa SDL cùng các directive như `@key`. Nếu `_service` không tồn tại hoặc SDL không chứa Federation metadata, schema factory/dependency chưa được cấu hình đúng.

Kiểm tra entity resolution trực tiếp:

```graphql
query ResolveEntity {
    _entities(representations: [
        { __typename: "Product", id: "product-101" }
    ]) {
        ... on Product {
            id
            reviews {
                rating
            }
        }
    }
}
```

Nếu `_entities` không trả đúng Product hoặc field `reviews` lỗi, hãy kiểm tra `@EntityMapping`, key name, type name và resolver của field trước khi điều tra gateway.

## 26. Bảo mật giữa gateway và subgraph

Gateway là điểm vào của client, nhưng subgraph vẫn là service có dữ liệu và cần bảo vệ độc lập.

Các nguyên tắc nên áp dụng:

- Xác thực client tại gateway và truyền identity/claims qua kênh service-to-service đáng tin cậy.
- Subgraph xác minh token hoặc credentials theo chính sách hệ thống, không tin header do client tùy ý gửi.
- Phân quyền tại subgraph theo dữ liệu mà service sở hữu.
- Kiểm tra tenant và ownership trong `@EntityMapping` hoặc application service khi tải entity.
- Không expose trực tiếp subgraph ra public network nếu chỉ gateway được phép gọi.
- Dùng TLS, service identity, network policy và secret rotation phù hợp.
- Giới hạn query depth/complexity, request size, timeout và rate limit ở gateway lẫn service.

Gateway không thể thay thế authorization trong từng subgraph. Một request có thể đến subgraph qua router, job nội bộ hoặc một client service khác; subgraph phải tự bảo vệ dữ liệu của nó.

## 27. Xử lý lỗi và tính sẵn sàng

Federated query phụ thuộc vào nhiều subgraph. Nếu một subgraph timeout hoặc trả lỗi, router có thể trả partial data kèm GraphQL errors theo execution plan và khả năng xử lý lỗi của router.

Thiết kế subgraph cần chú ý:

- Timeout cho database và outbound call.
- Giới hạn concurrency và connection pool.
- Retry chỉ với thao tác an toàn và lỗi tạm thời.
- Không retry mutation không idempotent một cách mù quáng.
- Health check và readiness riêng cho từng service.
- Log/trace có correlation ID để nối request từ router tới subgraph.
- Error message không tiết lộ stack trace hoặc chi tiết nội bộ.

Gateway cũng cần có timeout tổng và timeout theo subgraph. Một subgraph chậm có thể kéo dài toàn bộ GraphQL request dù các subgraph khác đã hoàn thành.

## 28. Schema ownership và quy trình thay đổi

Mỗi subgraph nên có team/domain owner rõ ràng. Trước khi thay đổi schema:

1. Xác định field thuộc subgraph nào.
2. Kiểm tra field có được client hoặc subgraph khác sử dụng không.
3. Thêm field theo hướng backward-compatible khi có thể.
4. Đánh dấu deprecated trước khi xóa field đang được dùng.
5. Chạy schema composition trong CI.
6. Kiểm tra query plan và integration test qua router.
7. Triển khai subgraph tương thích trước khi gateway bắt đầu gửi field mới tới nó.

Composition thành công không chứng minh resolver runtime đã đúng. Cần kiểm thử entity lookup, authorization, response mapping và lỗi ở runtime.

## 29. Kiểm thử Federation trong Spring GraphQL

Có thể chia kiểm thử thành nhiều lớp:

| Loại test | Mục tiêu |
|---|---|
| Unit test `@EntityMapping` | Kiểm tra cách representation được chuyển thành entity/reference. |
| GraphQL subgraph test | Kiểm tra `_service`, `_entities`, resolver và error mapping. |
| Schema composition test | Kiểm tra các SDL có thể kết hợp thành supergraph. |
| Router integration test | Kiểm tra query xuyên nhiều subgraph và response được ghép đúng. |
| Contract/security test | Kiểm tra key, auth context, tenant isolation và tương thích schema. |

Với `GraphQlTester`, có thể gửi trực tiếp `_entities` query tới subgraph đã cấu hình federation factory. Khi test gateway, khởi động router cùng các subgraph test hoặc dùng môi trường integration riêng.

## 30. Kiểm thử entity mapping với representation

Một test subgraph có thể gửi representation như gateway thực hiện:

Dependencies test minh họa với Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest({ProductEntityController.class, ProductReviewController.class})
@Import(FederationConfiguration.class)
class ProductEntityMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    ReviewQueryService reviewQueryService;

    @Test
    void resolvesReviewsForFederatedProduct() {
        given(reviewQueryService.findByProductId("product-101"))
            .willReturn(List.of(new Review("review-1", 5, "Great")));

        graphQlTester.document("""
                query {
                    _entities(representations: [
                        { __typename: "Product", id: "product-101" }
                    ]) {
                        ... on Product {
                            reviews {
                                id
                                rating
                            }
                        }
                    }
                }
                """)
            .execute()
            .path("_entities[0].reviews[0].id")
            .entity(String.class)
            .isEqualTo("review-1");
    }
}
```

Ví dụ giả định schema Federation, `FederationSchemaFactory`, `ProductEntityController`, `ProductReviewController` và `ReviewQueryService` đã được cấu hình. Trong test slice, cần import cấu hình federation cần thiết hoặc dùng integration test nếu auto-configuration không tự tạo schema factory.

Imports `@GraphQlTest` ở đây dùng Spring Boot 3.x. Với Spring Boot 4.x, dùng package `org.springframework.boot.graphql.test.autoconfigure.GraphQlTest`. `@MockitoBean` yêu cầu Spring Framework 6.2 trở lên; các phiên bản Spring Boot cũ hơn có thể dùng `@MockBean`.

## 31. Kiểm thử composition và gateway

CI có thể thực hiện các bước:

```bash
# Compose schemas from all subgraphs
rover supergraph compose --config ./supergraph.yaml --output ./supergraph.graphql

# Start the router with the composed artifact in the integration environment
./router --config ./router.yaml --supergraph ./supergraph.graphql
```

Sau đó chạy GraphQL integration query qua endpoint gateway và kiểm tra dữ liệu từ nhiều subgraph. Không chỉ kiểm tra từng subgraph riêng lẻ; cần ít nhất một test xác minh entity handoff và response merge thực sự.

Với GraphOS, có thể publish schema từng subgraph và để build pipeline thực hiện composition, schema checks và cập nhật supergraph theo quy trình quản lý schema của tổ chức.

## 32. Những lỗi thường gặp

**Cho rằng Spring GraphQL tự cung cấp gateway.** Spring for GraphQL cung cấp tích hợp để service chạy như subgraph. Gateway/router cần được triển khai riêng, ví dụ Apollo Router.

**Quên cấu hình `FederationSchemaFactory`.** Schema có `@key` nhưng thiếu `_entities` hoặc entity type resolver. Đăng ký factory qua `GraphQlSourceBuilderCustomizer`.

**Thiếu dependency Federation JVM.** `FederationSchemaFactory` cần thư viện `federation-graphql-java-support` tương thích.

**Entity representation thiếu `__typename` hoặc key field.** Gateway cần biết type và key để subgraph tải entity. Kiểm tra `@key` và method `@EntityMapping`.

**Tên entity mapping không khớp GraphQL type.** Tên method mặc định được chuyển thành type name với chữ cái đầu viết hoa. Dùng `@EntityMapping(name = "...")` khi cần chỉ định rõ.

**Batch entity resolver trả kết quả sai thứ tự.** Khi nhận danh sách representation, kết quả phải tương ứng đúng thứ tự đầu vào.

**Mỗi subgraph tự định nghĩa field giống nhau.** Composition có thể thất bại nếu field bị sở hữu trùng và không được khai báo shareable đúng cách.

**Dùng key không ổn định.** Entity key nên duy nhất, bất biến và có thể được các subgraph liên quan truy xuất.

**Cho rằng composition thành công nghĩa là runtime đúng.** Composition chỉ kiểm tra schema; cần test `_entities`, query plan và resolver thực tế.

**Để subgraph tin mọi header từ client.** Chỉ chấp nhận identity/claims từ nguồn đáng tin cậy và vẫn kiểm tra quyền tại subgraph.

**Đặt nghiệp vụ của nhiều domain trong gateway.** Gateway nên điều phối GraphQL; quy tắc nghiệp vụ thuộc subgraph sở hữu domain.

## Kết luận

Trong GraphQL Federation, subgraph là service sở hữu một phần schema và dữ liệu; gateway/router composition các schema thành supergraph, lập query plan và ghép kết quả cho client. Spring for GraphQL hỗ trợ xây dựng subgraph qua `federation-jvm`, `FederationSchemaFactory` và `@EntityMapping`. Entity key `@key` cho phép router nhận diện entity, `_service` công bố SDL, còn `_entities` chuyển representation tới subgraph để tải entity và phân giải các field do service sở hữu. Gateway nên được triển khai riêng, composition cần kiểm tra trong CI, và mỗi subgraph vẫn phải tự chịu trách nhiệm về authorization, tenant isolation, lỗi và tính sẵn sàng.

## Tài liệu tham khảo

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL API — `FederationSchemaFactory`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Spring Boot — Testing Spring GraphQL Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Apollo Federation — Introduction](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/federation)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Apollo Federation — Schema Composition](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/composition)
- [Apollo Federation — Compatible Subgraph Implementations](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/compatible-subgraphs)
- [Apollo Rover — Supergraph Commands](https://www.apollographql.com/docs/rover/commands/supergraphs)
- [Apollo Router — Configuration](https://www.apollographql.com/docs/graphos/routing/configuration/yaml)
- [Apollo Federation JVM — Spring GraphQL Example](https://github.com/apollographql/federation-jvm-spring-example)
