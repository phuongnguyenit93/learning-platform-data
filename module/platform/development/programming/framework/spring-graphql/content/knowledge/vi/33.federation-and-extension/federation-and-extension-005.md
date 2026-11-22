# Federated type

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích federated type và entity trong Apollo Federation.
- Phân biệt entity với value type thông thường.
- Dùng directive @key để xác định danh tính của một entity.
- Hiểu vai trò của @extends và @external khi một subgraph bổ sung field cho entity.
- Mô tả entity representation và luồng gọi Query._entities từ router.
- Cấu hình Spring for GraphQL bằng FederationSchemaFactory.
- Viết @EntityMapping để khôi phục entity từ key.
- Dùng @SchemaMapping, @BatchMapping và DataLoader cho các field của entity.
- Phân biệt cú pháp Federation 1 và Federation 2 ở mức cần thiết khi thiết kế schema.
- Kiểm thử entity resolution và xử lý lỗi khi entity không tồn tại.

## Federated type là gì?

Trong một ứng dụng GraphQL đơn khối, một schema thường được triển khai bởi một server. Khi hệ thống lớn lên, nhiều nhóm có thể cần sở hữu các phần dữ liệu khác nhau. Ví dụ:

- Nhóm Catalog quản lý Product, tên và giá.
- Nhóm Reviews quản lý đánh giá và nhận xét của Product.
- Nhóm Inventory quản lý tồn kho của Product.

Apollo Federation cho phép các GraphQL service độc lập, gọi là subgraph, cùng đóng góp field vào một graph thống nhất. Một object type có thể xuất hiện trong nhiều subgraph; mỗi subgraph sở hữu và phân giải các field thuộc phạm vi của mình.

Một federated type thường được gọi là entity. Entity là object type có một hoặc nhiều key ổn định để router có thể nhận diện cùng một đối tượng khi đi qua các subgraph. Ví dụ, Product có thể được Catalog subgraph định nghĩa tên và giá, còn Reviews subgraph bổ sung reviews.

Các subgraph không cần chia sẻ database hoặc Java model. Chúng chỉ cần thống nhất schema contract và cách định danh entity. Router dùng key để chuyển từ subgraph này sang subgraph khác, sau đó ghép các field thành response cho client.

Spring for GraphQL cung cấp integration với thư viện federation-jvm để tạo schema của một subgraph và xử lý yêu cầu phân giải federated entity. Spring application đóng vai trò subgraph; việc composition và điều phối nhiều subgraph do một federation gateway/router đảm nhiệm. [Spring for GraphQL – Federation](https://docs.spring.io/spring-graphql/reference/federation.html)

## Entity khác gì value type?

Không phải mọi object type được dùng ở nhiều subgraph đều cần trở thành entity.

| Đặc điểm | Entity | Value type |
| --- | --- | --- |
| Danh tính | Có key xác định một instance | Không cần danh tính độc lập |
| Directive điển hình | @key | Có thể dùng @shareable trong Federation 2 khi nhiều subgraph cùng phân giải field |
| Cách router liên kết | Dùng representation và entity resolution | Ghép theo quy tắc composition của schema |
| Ví dụ | Product, User, Order | Money, Address, Dimensions |

Product có thể được tra cứu độc lập bằng ID, vì vậy phù hợp làm entity. Money thường chỉ là giá trị gồm amount và currency; nó không cần một key để router quay lại tải chính object Money từ một subgraph khác.

Entity trong Federation là khái niệm của schema phân tán. Nó không bắt buộc phải tương ứng với một JPA entity hoặc một bảng database. Một subgraph có thể trả về DTO, projection hoặc object reference chỉ chứa key cần thiết để phân giải field tiếp theo.

## Xác định entity bằng @key

Directive @key đánh dấu một object type là entity và khai báo field set dùng để nhận diện entity đó:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String!
  price: Int
}
~~~

Trong ví dụ, Product được định danh bằng id. Router có thể dùng id để yêu cầu một subgraph khác phân giải thêm field của cùng Product.

Key có thể gồm nhiều field:

~~~graphql
type Product @key(fields: "tenantId sku") {
  tenantId: ID!
  sku: String!
  name: String!
}
~~~

Đây là compound key. Một Product chỉ được xác định khi có cả tenantId và sku. Compound key thường hữu ích khi ID chỉ duy nhất trong phạm vi tenant hoặc một namespace.

Field set của key cũng có thể chứa nested selection:

~~~graphql
type Product @key(fields: "id organization { id }") {
  id: ID!
  organization: Organization!
  name: String!
}
~~~

Một entity có thể có nhiều key nếu subgraph implementation hỗ trợ repeatable @key:

~~~graphql
type Product
  @key(fields: "id")
  @key(fields: "sku") {
  id: ID!
  sku: String!
  name: String!
}
~~~

Router có thể sử dụng key phù hợp với query plan và dữ liệu hiện có. Khi chọn key, hãy lưu ý:

- Các field phải xác định duy nhất một instance trong phạm vi graph.
- Nên ưu tiên key ổn định, không thay đổi theo thời gian.
- Key field thường nên non-null để router luôn có thể nhận diện entity.
- Key phải có thể được cung cấp cho subgraph cần phân giải entity.
- Field set của key không chứa field có argument hoặc field trả về union/interface.
- Nếu dùng nhiều key, kiểm tra phiên bản Federation và subgraph library có hỗ trợ repeatable @key hay không.

Không chọn tên hiển thị, email có thể thay đổi hoặc giá trị không duy nhất làm key nếu có một định danh ổn định hơn.

## Entity được chia sẻ giữa các subgraph

Giả sử hệ thống thư viện bán sách có hai subgraph.

**Catalog subgraph** sở hữu Product, id, name và price:

~~~graphql
type Query {
  product(id: ID!): Product
}

type Product @key(fields: "id") {
  id: ID!
  name: String!
  price: Int!
}
~~~

**Reviews subgraph** bổ sung field reviews cho cùng Product:

~~~graphql
type Product @key(fields: "id") @extends {
  id: ID! @external
  reviews: [Review!]!
}

type Review {
  id: ID!
  text: String!
  rating: Int!
}
~~~

Đây là kiểu khai báo extension mà tài liệu Spring for GraphQL dùng trong ví dụ federation-jvm. @key cho router biết hai định nghĩa Product có cùng danh tính; @extends biểu thị subgraph này đang mở rộng entity đã được định nghĩa ở nơi khác; @external khai báo id được tham chiếu từ subgraph khác và không do Reviews subgraph phân giải.

Reviews subgraph chỉ cần cung cấp reviews. Nó không cần sở hữu name hoặc price và không cần tải lại toàn bộ Product từ Catalog. Khi nhận một representation có id, nó có thể tạo một Product reference nhỏ rồi dùng id để tải reviews từ kho dữ liệu của mình.

Sau composition, router nhìn thấy một Product với các field name, price và reviews. Client không cần biết field nào nằm ở subgraph nào.

### Khác biệt cú pháp Federation 1 và Federation 2

Ví dụ @extends ở trên phản ánh kiểu khai báo được dùng trong tài liệu tích hợp Spring for GraphQL và federation-jvm. Khi làm việc với Federation 2, schema phải khai báo @link để liên kết phiên bản Federation và import các directive được sử dụng. Federation 2 không bắt buộc dùng @extends cho entity extension.

Ví dụ Federation 2:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external"]
  )

type Product @key(fields: "id") {
  id: ID! @external
  reviews: [Review!]!
}

type Review {
  id: ID!
  text: String!
  rating: Int!
}
~~~

Trong Federation 2, mỗi subgraph có thể định nghĩa entity cùng @key và composition hợp nhất các field. Không thêm @extends theo thói quen từ Federation 1 nếu schema đang theo Federation 2.

Hãy kiểm tra phiên bản Federation mà router composition hỗ trợ và phiên bản federation-jvm tương thích với Spring GraphQL đang dùng. Các directive mới của Federation 2 không mặc nhiên được hỗ trợ chỉ vì ứng dụng đã có FederationSchemaFactory. Tài liệu Spring hiện tại minh họa integration với federation-jvm; khả năng sử dụng từng directive phụ thuộc phiên bản thư viện và công cụ composition. [Apollo Federation Directives](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives)

## Entity representation

Khi router cần gọi một subgraph để lấy field của entity, nó gửi một representation. Representation là object chứa:

- __typename: tên GraphQL object type.
- Các field thuộc một @key hợp lệ của entity.

Ví dụ representation của Product:

~~~json
{
  "__typename": "Product",
  "id": "product-101"
}
~~~

Nếu Product dùng compound key:

~~~json
{
  "__typename": "Product",
  "tenantId": "tenant-7",
  "sku": "BOOK-101"
}
~~~

Representation không phải toàn bộ object Product. Nó chỉ chứa đủ thông tin để subgraph xác định instance cần phân giải. Subgraph có thể dùng key để tải dữ liệu từ database, gọi service nội bộ hoặc tạo một reference object rồi để nested resolver tải field.

Key là định danh, không phải bằng chứng authorization. Subgraph vẫn cần kiểm tra người dùng có quyền truy cập entity và field tương ứng. Không tin tenant hoặc owner trong representation nếu chúng chưa được ràng buộc với identity đã xác thực.

## Các thành phần Federation được thêm vào schema

Một subgraph tương thích Federation cần các thành phần đặc biệt để router có thể khám phá schema và yêu cầu entity:

| Thành phần | Vai trò |
| --- | --- |
| _Any | Scalar biểu diễn entity representation |
| _Entity | Union gồm các entity object type trong subgraph |
| Query._entities | Nhận danh sách representations và trả về các entity tương ứng |
| Query._service | Trả về thông tin schema của subgraph |
| _Service.sdl | Chuỗi SDL dùng cho việc khám phá/composition schema |

Trong subgraph, _Entity được tạo dựa trên các object type có @key. Query._entities nhận một list representations. Router dùng field này để bắt đầu phân giải các field do subgraph hiện tại sở hữu.

Query._service trả về SDL của subgraph, bao gồm metadata Federation cần thiết cho composition. Field này phục vụ mục đích tích hợp giữa router và subgraph; nó không phải field nghiệp vụ mà client thông thường cần gọi.
Các field Federation nội bộ như _service và _entities thuộc schema của subgraph; chúng không xuất hiện như field nghiệp vụ trong API schema đã compose cho client.

Khi dùng Spring FederationSchemaFactory, các định nghĩa và data fetcher cần thiết cho Federation được tạo trong quá trình xây dựng GraphQL schema. Không tự khai báo một _Entity union cố định nếu factory cần sinh union từ các entity thực tế trong schema.

## Cấu hình FederationSchemaFactory trong Spring Boot

Spring for GraphQL tích hợp với federation-jvm. Cần có Spring Boot GraphQL starter và dependency federation-graphql-java-support tương thích với phiên bản Spring GraphQL/GraphQL Java của ứng dụng.

Ví dụ Gradle Groovy, thay placeholder bằng phiên bản federation-jvm đã được xác minh tương thích với GraphQL Java mà Spring Boot quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'com.apollographql.federation:federation-graphql-java-support:<compatible-version>'
}
~~~

Khai báo factory và gắn nó vào GraphQlSource builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration
public class FederationConfig {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {
        return builder ->
                builder.schemaFactory(factory::createGraphQLSchema);
    }
}
~~~

Import của GraphQlSourceBuilderCustomizer phụ thuộc Spring Boot release line. Spring Boot 4 dùng package org.springframework.boot.graphql.autoconfigure; Spring Boot 3 dùng package org.springframework.boot.autoconfigure.graphql. Phần còn lại của cấu hình giữ cùng ý tưởng. Không ép một phiên bản federation-jvm mới hơn vào dự án nếu nó kéo theo GraphQL Java khác với phiên bản mà Spring for GraphQL hỗ trợ.

Factory phát hiện các controller method có @EntityMapping, tạo schema Federation tương thích và thiết lập entity data fetcher cùng type resolver cho _Entity. Nếu subgraph có entity resolvable nhưng không có mapping phù hợp, cấu hình có thể thất bại ngay khi khởi động. Đây là lỗi nên được phát hiện sớm thay vì đợi router gọi _entities ở production.

Spring application vẫn cần schema SDL trong classpath, ví dụ src/main/resources/graphql. Factory bổ sung Federation support vào schema được tạo từ các resource đó; nó không tự tạo domain type Product hoặc business resolver cho reviews.

## Phân giải entity bằng @EntityMapping

Spring for GraphQL dùng @EntityMapping để ánh xạ việc tải entity từ representation do router gửi qua Query._entities.

Ví dụ Reviews subgraph:

~~~java
public record Product(String id) {
}

public record Review(
        String id,
        String text,
        int rating) {
}
~~~

Controller:

~~~java
import java.util.List;

import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductReviewsController {

    private final ReviewService reviewService;

    public ProductReviewsController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @EntityMapping
    public Product product(@Argument("id") String id) {
        return new Product(id);
    }

    @SchemaMapping(typeName = "Product", field = "reviews")
    public List<Review> reviews(Product product) {
        return reviewService.findByProductId(product.id());
    }
}
~~~

Khi router gửi representation Product có id, method product nhận id thông qua @Argument và trả về một Product reference. Sau đó GraphQL tiếp tục phân giải field reviews bằng @SchemaMapping. Resolver dùng id từ Product reference để tải Review trong Reviews subgraph.

Không nhất thiết phải tải toàn bộ Product trong @EntityMapping. Nếu subgraph chỉ cần key để phân giải field riêng, một reference object tối thiểu là đủ. Cách này tránh gọi lại hệ thống sở hữu entity chỉ để lấy các field mà subgraph hiện tại không dùng.

### Argument và representation map

@Argument đọc một field từ representation và chuyển đổi sang kiểu Java:

~~~java
@EntityMapping
public Product product(@Argument("id") String id) {
    return new Product(id);
}
~~~

Nếu key gồm nhiều field, method có thể nhận nhiều argument:

~~~java
@EntityMapping
public Product product(
        @Argument("tenantId") String tenantId,
        @Argument("sku") String sku) {
    return productService.reference(tenantId, sku);
}
~~~

Khi cần xử lý representation đầy đủ, có thể nhận Map<String, Object>:

~~~java
import java.util.Map;

@EntityMapping
public Product product(Map<String, Object> representation) {
    String id = (String) representation.get("id");
    return productService.reference(id);
}
~~~

Spring for GraphQL cũng hỗ trợ List<Map<String, Object>> khi một method xử lý nhiều representation cùng loại. Ngoài ra, method có thể nhận GraphQLContext, @ContextValue, Principal, @AuthenticationPrincipal, DataFetchingEnvironment hoặc DataLoader tùy use case.

### Batch entity resolution

Nếu router gửi nhiều Product representation trong cùng một _entities request, Spring hỗ trợ một @EntityMapping method nhận danh sách key và trả về danh sách entity theo đúng thứ tự:

~~~java
@EntityMapping
public List<Product> product(@Argument("id") List<String> idList) {
    return productService.findReferencesInOrder(idList);
}
~~~

Quy ước tên idList giúp Spring suy ra danh sách giá trị cho argument id. Có thể chỉ rõ tên bằng @Argument("id") nếu muốn tên tham số khác.

Kết quả phải giữ đúng thứ tự tương ứng với danh sách representation đầu vào. Nếu repository trả về kết quả theo thứ tự khác, cần sắp xếp lại theo key trước khi return. Nếu không, router có thể ghép field của Product này vào representation của Product khác.

Khi cần tải entity bất đồng bộ hoặc gom nhiều lần load theo key, có thể dùng DataLoader:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;

@EntityMapping
public CompletableFuture<Product> product(
        @Argument("id") String id,
        DataLoader<String, Product> productLoader) {
    return productLoader.load(id);
}
~~~

Ngoài entity object đồng bộ, @EntityMapping cũng hỗ trợ các kiểu trả về bất đồng bộ như Mono, CompletableFuture và Callable. BatchLoaderRegistry có thể đăng ký loader cho Product và gom các key trong cùng request. Cách này hữu ích khi resolver được gọi nhiều lần hoặc entity resolution cần chia sẻ cơ chế batching với các field khác.

## Entity mapping và các field còn lại

@EntityMapping chỉ giải quyết bước tìm entity từ representation. Các field khác của entity vẫn dùng các cơ chế data fetching thông thường:

- @SchemaMapping cho nested field cần logic riêng.
- @BatchMapping để tải field cho nhiều parent object.
- DataLoader để gom truy vấn theo key.
- Default property data fetcher cho property có sẵn trên object.

Ví dụ, Reviews subgraph có thể trả Product reference chỉ chứa id. Field reviews được xử lý bằng @SchemaMapping; field productId nội bộ không nhất thiết xuất hiện trong schema.

Một entity có thể được nhiều subgraph mở rộng. Mỗi subgraph cần entity mapping nếu router có thể định tuyến tới subgraph đó để phân giải entity. Subgraph không sở hữu field nào của entity có thể chỉ tham chiếu entity theo cách phù hợp với directive và khả năng của Federation version; hãy kiểm tra tùy chọn resolvable của @key và support trong library đang dùng.

## Xử lý entity không tồn tại và lỗi mapping

Entity mapping có thể gặp các tình huống:

- Representation thiếu __typename.
- Representation thiếu key field bắt buộc.
- Key không hợp lệ hoặc không tìm thấy entity.
- Service/repository gặp lỗi khi tải entity.
- Người dùng không được phép truy cập entity.

Spring for GraphQL cung cấp exception handling cho @EntityMapping. Có thể dùng @GraphQlExceptionHandler trong controller hoặc @ControllerAdvice để chuyển exception thành GraphQLError. Các lỗi này được đưa vào response của _entities query.

Ví dụ:

~~~java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;

@GraphQlExceptionHandler
public GraphQLError handleProductNotFound(ProductNotFoundException exception) {
    return GraphqlErrorBuilder.newError()
            .message("Không tìm thấy Product được yêu cầu")
            .extensions(Map.of("code", "PRODUCT_NOT_FOUND"))
            .build();
}
~~~

Trong production, cần quyết định rõ khi entity không tồn tại thì trả null, trả lỗi hay che giấu sự tồn tại của entity. Với dữ liệu nhạy cảm, không để message lỗi tiết lộ key hoặc thông tin nội bộ. Cũng cần kiểm tra authorization ở subgraph; gateway authentication không thay thế kiểm tra quyền ở nơi dữ liệu thực sự được đọc.

## Luồng router gọi entity giữa các subgraph

Client gửi một query thông thường tới router:

~~~graphql
query ProductDetails($id: ID!) {
  product(id: $id) {
    id
    name
    price
    reviews {
      rating
      text
    }
  }
}
~~~

Router có thể thực hiện các bước:

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant R as Federation Router
    participant P as Catalog Subgraph
    participant V as Reviews Subgraph
    C->>R: product(id)
    R->>P: Query Product fields
    P-->>R: id, name, price
    R->>V: Query._entities([{__typename, id}])
    V->>V: @EntityMapping Product reference
    V->>V: @SchemaMapping Product.reviews
    V-->>R: reviews
    R-->>C: Merged Product response
~~~

Router dùng key id từ kết quả Catalog để tạo representation cho Reviews. Reviews subgraph không nhận lại toàn bộ query của client; nó nhận yêu cầu phân giải entity và selection set mà router cần từ subgraph đó.

Một query có thể đi qua nhiều subgraph và cùng một entity có thể được tham chiếu nhiều lần. Vì vậy, entity resolution nên hỗ trợ batching, tránh N+1 và giới hạn số lần gọi downstream.

## Kiểm tra _entities trực tiếp trong development

Thông thường client gọi supergraph endpoint, không gọi _entities trực tiếp. Tuy nhiên, khi phát triển hoặc debug một subgraph, có thể gửi operation tới subgraph để kiểm tra entity mapping:

~~~graphql
query ResolveProduct {
  _entities(
    representations: [
      {
        __typename: "Product"
        id: "product-101"
      }
    ]
  ) {
    ... on Product {
      id
      reviews {
        id
        rating
        text
      }
    }
  }
}
~~~

Operation này kiểm tra:

1. Schema Federation đã tạo _entities và _Entity.
2. Representation có __typename và key hợp lệ.
3. @EntityMapping trả về đúng Product reference.
4. @SchemaMapping phân giải reviews.
5. Response có dữ liệu đúng cho entity được yêu cầu.

Nếu subgraph có nhiều entity type, union _Entity sẽ chứa các object type tương ứng. Query phải dùng inline fragment để chọn field của từng concrete type.

## Kiểm thử entity mapping bằng GraphQlTester

Có thể dùng GraphQlTester với GraphQL execution đã cấu hình FederationSchemaFactory:

Đoạn test sau giả định GraphQlTester đã được cấu hình để thực thi schema của Reviews subgraph:

~~~java
@Test
void resolvesProductRepresentation() {
    graphQlTester.document("""
            query {
                _entities(representations: [
                    { __typename: "Product", id: "product-101" }
                ]) {
                    ... on Product {
                        id
                        reviews {
                            rating
                            text
                        }
                    }
                }
            }
            """)
            .execute()
            .path("_entities[0].id")
            .entity(String.class)
            .isEqualTo("product-101");
}
~~~

Nên có test cho:

- Representation hợp lệ với key đơn.
- Compound key và chuyển đổi kiểu argument.
- Nhiều representation trong cùng request, kết quả đúng thứ tự.
- Entity không tồn tại.
- Entity mapping trả lỗi và GraphQL error extensions.
- Nested @SchemaMapping hoặc @BatchMapping được gọi đúng.
- Authorization theo principal và tenant.
- DataLoader gom các key thay vì gọi repository từng lần.

Test _entities xác minh subgraph. Nó không chứng minh router composition thành công hoặc query plan giữa các subgraph đúng. Cần một integration test riêng với federation router hoặc composition tool khi muốn xác minh toàn bộ supergraph.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Router không ghép được hai định nghĩa Product | Key không giống hoặc không ổn định giữa subgraph | Chọn key chung và kiểm tra composition |
| Subgraph không có _entities | Chưa cấu hình FederationSchemaFactory | Gắn factory vào GraphQlSource builder |
| Entity type không có trong _Entity | Thiếu @key hoặc schema chưa được biến đổi Federation | Kiểm tra SDL và schema factory |
| @EntityMapping không được gọi | Representation thiếu __typename/key hoặc method mapping sai | Kiểm tra type name, @Argument và entity mapping registration |
| Startup báo unmapped entity type | Entity resolvable nhưng chưa có @EntityMapping | Viết resolver cho entity hoặc cấu hình resolvable đúng nếu được hỗ trợ |
| Entity mapping trả sai object | Key được bind nhầm hoặc method dùng sai representation | Kiểm tra argument và full representation map |
| Field mở rộng trả null | Chưa có @SchemaMapping hoặc source object thiếu key cần thiết | Bổ sung resolver và giữ key trong reference object |
| Nhiều entity bị ghép nhầm dữ liệu | Batch resolver trả List sai thứ tự | Trả kết quả theo thứ tự representation hoặc dùng Map đúng key |
| Một _entities request tạo nhiều truy vấn | Entity resolver tải từng key riêng | Dùng batch entity mapping hoặc DataLoader |
| Federation 2 composition lỗi directive | Thiếu @link hoặc import directive không đúng | Khai báo Federation 2 link và kiểm tra version support |
| Subgraph trả lỗi lộ dữ liệu | Error message chứa key hoặc thông tin nội bộ | Dùng error code ổn định và message an toàn |
| _entities chạy được nhưng supergraph query lỗi | Chưa kiểm tra router composition hoặc query plan | Test qua gateway/router tích hợp |

## Thực hành tổng hợp

Xây dựng hai subgraph Catalog và Reviews:

1. Trong Catalog, khai báo Product với @key(fields: "id"), id, name và price.
2. Trong Reviews, khai báo Product mở rộng với cùng key và field reviews.
3. Chọn cú pháp Federation phù hợp với router và federation-jvm version đang dùng.
4. Thêm dependency federation-graphql-java-support tương thích.
5. Cấu hình FederationSchemaFactory và GraphQlSourceBuilderCustomizer.
6. Tạo Product reference chỉ chứa id.
7. Viết @EntityMapping để lấy id từ representation.
8. Viết @SchemaMapping cho Product.reviews.
9. Gửi _entities query trực tiếp tới Reviews subgraph để kiểm tra entity resolution.
10. Gửi query ProductDetails tới router và xác minh field từ cả hai subgraph được ghép.
11. Thử compound key hoặc nhiều representation và kiểm tra thứ tự kết quả.
12. Thêm DataLoader hoặc batch entity mapping để giảm số truy vấn khi router gửi nhiều entity.
13. Kiểm thử entity không tồn tại, lỗi resolver và authorization theo tenant.

Sau khi hoàn thành, hãy giải thích vì sao @key chỉ định danh entity nhưng không tải dữ liệu, vai trò của @EntityMapping trong _entities, và khác biệt giữa test một subgraph với test toàn supergraph.

## Ghi nhớ

Federated type là object type có thể được nhiều subgraph đóng góp field. Entity được định danh bằng @key; representation mang __typename cùng key field để router yêu cầu subgraph khác phân giải entity qua Query._entities. @extends và @external xuất hiện trong cách khai báo Federation 1; Federation 2 dùng @link và không bắt buộc @extends. Trong Spring for GraphQL, FederationSchemaFactory tạo schema Federation và đăng ký cơ chế entity resolution; @EntityMapping lấy entity từ representation, còn @SchemaMapping/@BatchMapping xử lý các field còn lại. Key phải ổn định và duy nhất, batch result phải ghép đúng representation, và authorization vẫn phải được kiểm tra ở subgraph. Test _entities giúp xác minh subgraph; router composition test xác minh toàn supergraph.

## Tài liệu tham khảo

- [Spring for GraphQL – Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL – FederationSchemaFactory API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Apollo Federation – Introduction to Entities](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/entities/intro)
- [Apollo Federation – Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Apollo Federation – Directives](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives)
- [Apollo Federation JVM – GraphQL Java Support](https://github.com/apollographql/federation-jvm/tree/main/graphql-java-support)
