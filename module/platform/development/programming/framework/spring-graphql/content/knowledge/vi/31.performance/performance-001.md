# Chi phí query execution

## Mục tiêu

Sau bài học này, bạn có thể:

- Mô tả các giai đoạn xử lý một GraphQL request ở server.
- Nhận diện các nguồn tiêu tốn CPU, I/O, bộ nhớ và băng thông trong query execution.
- Ước lượng chi phí từ số field, độ sâu, độ rộng và kích thước các collection lồng nhau.
- Giải thích vì sao query nông vẫn có thể rất đắt và query sâu chưa chắc đã đắt.
- Phân tích N+1 và dùng DataLoader hoặc @BatchMapping để giảm số lần truy cập backend.
- Giới hạn page size, query depth, query complexity và thời gian xử lý.
- Dùng GraphQL Java Instrumentation và Micrometer để đo hiệu năng.
- Phân biệt cache document với cache dữ liệu và chọn cách tối ưu phù hợp.

## Chi phí của một GraphQL request

GraphQL cho phép client tự chọn field trong response. Tính linh hoạt này khiến server phải xử lý nhiều hình dạng query khác nhau, kể cả query có nhiều field lồng nhau hoặc collection lớn.

Một request có thể tiêu tốn tài nguyên ở nhiều nơi:

| Nguồn chi phí | Ví dụ | Tài nguyên bị ảnh hưởng |
| --- | --- | --- |
| Parse và validate | Parse document, kiểm tra field, argument, fragment và variable | CPU, bộ nhớ |
| Data fetching | Đọc database, gọi REST API hoặc message broker | I/O, connection pool, độ trễ |
| Nested field resolution | Phân giải author, reviews, permissions cho từng object | CPU, số lần gọi backend |
| Collection completion | Duyệt và hoàn thiện nhiều phần tử của list | CPU, bộ nhớ |
| Scalar serialization | Chuyển dữ liệu thành response map và JSON | CPU, bộ nhớ |
| Response transfer | Trả payload lớn qua HTTP hoặc WebSocket | Băng thông, thời gian mạng |
| Concurrent requests | Nhiều query cùng tải dữ liệu lớn | Thread, connection pool, heap và downstream capacity |

Một query chỉ có vài field vẫn có thể đắt nếu một field gọi dịch vụ bên ngoài chậm hoặc tải hàng chục nghìn bản ghi. Ngược lại, một query có nhiều scalar field đọc từ object đã có sẵn có thể rất rẻ.

Do đó, số lượng field là một tín hiệu để ước lượng chi phí, không phải phép đo thời gian thực thi. Cần kết hợp cấu trúc query với cách resolver lấy dữ liệu và kích thước dữ liệu trả về.

## Các giai đoạn xử lý query

Một request GraphQL đi qua các bước chính:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[Parse document]
    B --> C[Validate against schema]
    C --> D[Coerce variables and select operation]
    D --> E[Execute root fields]
    E --> F[Resolve nested fields]
    F --> G[Complete lists and scalar values]
    G --> H[Build and serialize response]
    H --> I[Return response]
~~~

**Parse và validate** chuyển document thành cấu trúc AST và xác minh operation phù hợp với schema. Nếu client gửi lại cùng một document nhiều lần, parse và validate lặp lại có thể trở thành chi phí đáng kể.

**Variable coercion và operation selection** kiểm tra giá trị variables, áp dụng default value và xác định query hoặc mutation cần thực thi.

**Data fetching và field completion** là phần thường chiếm nhiều thời gian nhất. GraphQL gọi data fetcher cho các field được chọn, sau đó tiếp tục phân giải nested field và hoàn thiện list, object, scalar.

**Response serialization** xây dựng kết quả theo selection set rồi chuyển thành định dạng transport. Query trả về nhiều object và field sẽ cần nhiều bộ nhớ hơn, kể cả khi backend đã tải dữ liệu nhanh.

Spring for GraphQL dùng ExecutionGraphQlService làm abstraction thực thi request. Các transport như HTTP chuyển request tới service này; GraphQlSource cung cấp GraphQL Java engine được cấu hình để thực thi. [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)

## Query depth và query breadth

Độ sâu (depth) là số tầng nested field từ root tới field sâu nhất. Độ rộng (breadth) là số field hoặc số phần tử được yêu cầu ở cùng một tầng.

Query sâu:

~~~graphql
query {
  me {
    manager {
      manager {
        manager {
          name
        }
      }
    }
  }
}
~~~

Query rộng:

~~~graphql
query {
  books(first: 100) {
    id
    title
    publishedAt
    author {
      id
      name
    }
    publisher {
      id
      name
    }
    category {
      id
      name
    }
  }
}
~~~

Query đầu có nhiều tầng nhưng mỗi tầng có thể chỉ đọc một object. Query thứ hai ít tầng hơn, nhưng có thể tải 100 sách cùng nhiều quan hệ.

Một query có thể vừa sâu vừa rộng khi nested field trả về list:

~~~graphql
query {
  books(first: 50) {
    reviews(first: 20) {
      reviewer {
        friends(first: 10) {
          name
        }
      }
    }
  }
}
~~~

Số object tiềm năng ở tầng cuối có thể lên tới:

\[
50 \times 20 \times 10 = 10\,000
\]

Đây mới chỉ là số phần tử ở tầng friends, chưa tính Book, Review, Reviewer và các field khác. Giới hạn depth đơn lẻ không ngăn được query rộng có collection lớn.

## Ước lượng chi phí từ selection set

Một mô hình đơn giản có thể gán mỗi field một chi phí cơ bản và nhân chi phí con với số phần tử mà field collection có thể trả về.

Gọi:

- \(C(f)\) là chi phí ước lượng của field f.
- \(B(f)\) là chi phí cơ bản để xử lý field.
- \(M(f)\) là số phần tử tối đa dự kiến nếu field trả về collection.
- \(Children(f)\) là các field con được chọn.

Với field đơn:

\[
C(f) = B(f) + \sum C(child)
\]

Với field trả về list:

\[
C(f) = B(f) + M(f) \times \max(1, \sum C(child))
\]

Đây là mô hình minh họa để hiểu cách collection nhân chi phí. Production cần điều chỉnh theo resolver, loại backend, page size và dữ liệu thực tế. Không nên coi điểm complexity là số mili giây.

Ví dụ schema:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  title: String!
  author: Author
  reviews(first: Int = 10): [Review!]!
}

type Author {
  name: String!
}

type Review {
  rating: Int!
  reviewer: User
}

type User {
  displayName: String!
}
~~~

Query:

~~~graphql
query {
  books(first: 50) {
    title
    author {
      name
    }
    reviews(first: 10) {
      rating
      reviewer {
        displayName
      }
    }
  }
}
~~~

Trong ví dụ, server có thể phải hoàn thiện 50 Book, tối đa 500 Review và tối đa 500 User reviewer. Dù mỗi field chỉ xuất hiện một lần trong document, nested field của list được thực thi cho từng phần tử tương ứng.

Khi ước lượng, hãy nhìn vào các argument phân trang như first, last, các field có khả năng trả list và những field gọi backend. Một field gọi dịch vụ tính phí hoặc truy vấn tìm kiếm phức tạp có thể cần trọng số cao hơn field đọc property đơn giản.

### Alias và fragment ảnh hưởng thế nào?

Fragment giúp tái sử dụng selection set:

~~~graphql
fragment BookCard on Book {
  id
  title
  author {
    name
  }
}

query {
  books(first: 20) {
    ...BookCard
  }
}
~~~

Fragment không phải một lần fetch độc lập. GraphQL mở rộng fragment vào selection set để xác định các field cần thực thi.

Alias tạo response key khác nhau và có thể khiến cùng một field được thực thi nhiều lần:

~~~graphql
query {
  firstBook: book(id: "book-1") {
    title
  }
  secondBook: book(id: "book-1") {
    title
  }
}
~~~

Hai alias tạo hai field response riêng. Nếu resolver không có cache phù hợp, backend có thể bị gọi hai lần dù cùng truy cập một ID.

Directive @skip và @include ảnh hưởng field nào được thực thi theo variables. Complexity calculator cần tính tới điều kiện directive nếu muốn ước lượng sát hơn; không giả định mọi nhánh luôn được chạy hoặc luôn bị bỏ qua.

## N+1 làm tăng chi phí backend

Một query có thể trả 50 sách, mỗi sách có một tác giả. Nếu resolver tải tác giả riêng cho từng sách, số lần truy cập database có thể là:

- Một query tải danh sách sách.
- Năm mươi query tải tác giả.

Tổng cộng 51 query. Đây là vấn đề N+1.

Resolver không batching:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.authorId())
            .orElse(null);
}
~~~

Khi field author được chọn cho 50 Book, method có thể được gọi 50 lần. Chi phí không chỉ nằm ở số lần gọi method mà còn ở round trip, connection pool, transaction và thời gian chờ database.

### Dùng @BatchMapping

Với quan hệ một Book tới một Author, có thể tải theo batch:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        Map<String, Author> authors =
                authorService.findAllByIds(authorIds);

        Map<Book, Author> result = new HashMap<>();
        books.forEach(book ->
                result.put(book, authors.get(book.authorId())));
        return result;
    }
}
~~~

Trong ví dụ, service có thể tải tất cả Author theo một danh sách ID thay vì thực hiện một truy vấn cho từng Book. HashMap cho phép value null nếu không tìm thấy Author; field author trong schema cũng được khai báo nullable. @BatchMapping tạo batch loader và data fetcher tương ứng cho field. Key trong Map phải khớp source object; nếu dùng Map với entity làm key, equality và hashCode cần ổn định.

### Dùng DataLoader và BatchLoaderRegistry

Khi cần kiểm soát nhiều hơn, đăng ký batch loader qua BatchLoaderRegistry:

Trong ví dụ này, AuthorService.findAllByIds nhận tập author ID và trả về Mono<Map<String, Author>>.

~~~java
@Configuration
public class GraphQlBatchConfiguration {

    private final AuthorService authorService;

    public GraphQlBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {
        this.authorService = authorService;
        registry.forTypePair(String.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds));
    }
}
~~~

Sau đó resolver dùng DataLoader:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
~~~

DataLoader gom các lời gọi load() trong cùng request để dispatch theo batch và cache kết quả theo key trong phạm vi request. BatchLoaderRegistry đăng ký loader cho từng request và hỗ trợ chia sẻ GraphQLContext với batch loading function.

@BatchMapping phù hợp cho trường hợp đơn giản. BatchLoaderRegistry linh hoạt hơn khi cần custom key, context hoặc nhiều cách tải. [Spring for GraphQL – Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)

Batching giảm số round trip backend, nhưng không làm biến mất chi phí hoàn thiện từng object hoặc kích thước response. Query yêu cầu 10.000 object vẫn cần server tạo và serialize 10.000 object, ngay cả khi chúng được tải trong một batch.

## Giới hạn page size và collection

Không để client yêu cầu page size tùy ý. Schema có thể khai báo argument phân trang:

~~~graphql
type Query {
  books(first: Int = 20, after: String): [Book!]!
}
~~~

Resolver cần áp dụng giới hạn phía server:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    int requested = first != null ? first : 20;
    int pageSize = Math.min(Math.max(requested, 1), 100);
    return bookService.findFirstPage(pageSize);
}
~~~

Không chỉ giới hạn ở UI hoặc client SDK. Một client bất kỳ có thể gửi request trực tiếp với first: 1000000.

Với collection lớn, dùng cursor pagination hoặc keyset pagination khi phù hợp. Cursor cần gắn với thứ tự ổn định; nếu sort không ổn định, client có thể nhận trùng hoặc bỏ sót item giữa các trang. Spring for GraphQL hỗ trợ Connection/Edge/PageInfo và các adapter cho Spring Data Window hoặc Slice.

Hãy giới hạn page size ở resolver hoặc tầng service/repository, đồng thời đưa giới hạn đó vào query complexity calculator để điểm ước lượng phản ánh số item server thực sự có thể tải.

## Giới hạn query depth và query complexity

GraphQL Java cung cấp hai instrumentation hữu ích:

- MaxQueryDepthInstrumentation từ chối query vượt quá số tầng cho phép.
- MaxQueryComplexityInstrumentation từ chối query vượt quá điểm complexity cho phép.

Depth bảo vệ khỏi selection set lồng nhau quá sâu. Complexity giúp kiểm soát số field và chi phí con; khi dùng calculator tùy chỉnh, có thể nhân chi phí với argument phân trang.

Ví dụ cấu hình Spring Boot bằng các Instrumentation bean:

~~~java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlQueryCostConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        FieldComplexityCalculator calculator =
                (environment, childComplexity) -> {
                    if (environment.getFieldDefinition() == null) {
                        return 1 + childComplexity;
                    }

                    boolean paginated = environment.getFieldDefinition()
                            .getArguments().stream()
                            .anyMatch(argument ->
                                    argument.getName().equals("first")
                                    || argument.getName().equals("last"));

                    if (!paginated) {
                        return 1 + childComplexity;
                    }

                    Object rawSize = environment.getArguments().get("first");
                    if (!(rawSize instanceof Number)) {
                        rawSize = environment.getArguments().get("last");
                    }

                    int pageSize = rawSize instanceof Number number
                            ? number.intValue()
                            : 20; // Phải khớp page size mặc định của resolver.

                    return 1 + Math.max(1, pageSize)
                            * Math.max(1, childComplexity);
                };

        return new MaxQueryComplexityInstrumentation(1500, calculator);
    }
}
~~~

Spring Boot GraphQL starter phát hiện các bean Instrumentation để đưa vào GraphQL engine. Nếu tự tạo GraphQlSource, hãy đăng ký instrumentation trong GraphQlSource.Builder hoặc GraphQL.Builder. Khi ứng dụng đã có instrumentation cho metrics/tracing, hãy ghép chúng bằng ChainedInstrumentation thay vì vô tình ghi đè instrumentation đang dùng.

Trong ví dụ:

- Query depth tối đa là 8 tầng.
- Mỗi field có chi phí cơ bản là 1 cộng với chi phí con.
- Field có first hoặc last nhân chi phí con với page size.
- Nếu không truyền page size, calculator dùng 20, phải đồng bộ với default của resolver.
- Complexity tối đa là 1500 điểm.

Các con số chỉ là giá trị minh họa. Hãy hiệu chỉnh dựa trên benchmark và tải thật. Nếu resolver dùng argument khác như limit, count hoặc pageSize, calculator cần tính các argument đó. Nếu một field đắt do gọi dịch vụ bên ngoài, hãy gán trọng số riêng cho field đó.

Mặc định complexity calculator của GraphQL Java cộng một đơn vị cho field và chi phí con (1 + childComplexity). Nó không tự suy ra số lượng item mà resolver sẽ trả về. Vì vậy, query books(first: 1000) và books(first: 1) có thể có cùng điểm với calculator mặc định. Custom FieldComplexityCalculator giúp đưa page size vào ước lượng.

Depth và complexity là guard trước khi thực thi, không thay thế validation nghiệp vụ, page size cap, authorization hoặc rate limit theo người dùng.

## Cache parse và validation

GraphQL Java phải parse và validate document trước khi thực thi. Nếu một operation ổn định được gọi nhiều lần, có thể cache kết quả parse/validation bằng PreparsedDocumentProvider.

Spring for GraphQL cho phép đăng ký PreparsedDocumentProvider thông qua GraphQlSource.Builder#configureGraphQl. Một số lựa chọn gồm:

- Cache document đã parse và validate theo query text.
- Dùng persisted query để client tham chiếu operation đã đăng ký.
- Dùng allowlist operation cho API có tập query được kiểm soát.

Document cache giúp giảm CPU parse/validation khi cùng operation được gửi lại. Nó không cache dữ liệu từ database, không bỏ qua authorization và không làm resolver chạy nhanh hơn.

Khi triển khai cache:

- Đặt giới hạn kích thước và chính sách eviction.
- Tránh cache không giới hạn các query text duy nhất do client tự sinh.
- Xem xét invalidation khi schema thay đổi.
- Với persisted query, xác minh operation ID ánh xạ tới đúng document.
- Không dùng cache document như một cơ chế bảo vệ dữ liệu.

Nếu cần cache response, đó là một lớp khác. Cache response phải xét variables, principal, tenant, quyền truy cập và độ mới của dữ liệu; không dùng chung response có dữ liệu riêng tư giữa các người dùng.

## Query timeout và cancellation

Một request có thể tiêu tốn tài nguyên quá lâu do database chậm, downstream timeout hoặc publisher không kết thúc. Spring for GraphQL cung cấp TimeoutWebGraphQlInterceptor cho web transports:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor graphQlTimeoutWebInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
~~~

Khi request vượt timeout, interceptor gửi cancellation signal lên chuỗi xử lý. Reactive data fetcher có thể nhận cancellation và dừng công việc đang chạy. Đây là giới hạn thời gian cho request qua web handler; các downstream client và database vẫn nên có timeout riêng.

Không phải mọi thao tác blocking đều có thể bị dừng ngay khi GraphQL request timeout. Nếu resolver đang block trong JDBC hoặc một thư viện không hỗ trợ interruption/cancellation, cần timeout ở chính driver/client hoặc thực thi trên executor phù hợp.

## Mô hình thực thi và concurrency

GraphQL Java mặc định dùng AsyncExecutionStrategy cho query. Các field cùng cấp có thể được khởi chạy đồng thời nếu data fetcher trả về CompletionStage hoặc kiểu reactive được Spring for GraphQL adapter hỗ trợ.

Điều này giúp giảm thời gian chờ khi một query cần nhiều nguồn dữ liệu độc lập. Tuy nhiên, nó cũng có nghĩa nhiều resolver có thể chạy cùng lúc:

- Không dùng mutable state không thread-safe chung cho nhiều request hoặc field.
- Không tạo quá nhiều thread mới bên trong từng resolver.
- Theo dõi giới hạn connection pool của database và HTTP client.
- Dùng batch loading để giảm số công việc downstream thay vì chỉ tăng concurrency.
- Không gọi blocking repository trên event-loop của WebFlux.

Với Spring WebFlux, data fetcher nên trả về Mono, Flux hoặc CompletionStage phù hợp với nguồn dữ liệu. Một lời gọi blocking đặt bên trong Mono.just(blockingCall()) vẫn chạy blocking trước khi Mono được tạo. Cần chọn reactive driver hoặc executor phù hợp cho tác vụ blocking.

Các root field của mutation được thực thi tuần tự theo semantics của GraphQL. Không giả định mutation có thể chạy song song giống query; thứ tự có thể quan trọng vì mỗi field có thể thay đổi trạng thái.

Spring for GraphQL hỗ trợ reactive data fetcher, CompletionStage, Kotlin coroutine và Callable cho @SchemaMapping/@BatchMapping khi cấu hình executor phù hợp. [Spring for GraphQL – Thread Model](https://docs.spring.io/spring-graphql/reference/request-execution.html)

## Đo và quan sát query execution

Không tối ưu dựa trên cảm giác hoặc chỉ nhìn thời gian tổng. Hãy đo request và các data fetcher quan trọng.

Spring for GraphQL tích hợp Micrometer Observation:

| Observation | Ý nghĩa | Dữ liệu hữu ích |
| --- | --- | --- |
| graphql.request | Toàn bộ GraphQL request | Operation type, outcome, operation name, execution ID |
| graphql.datafetcher | Data fetcher không trivial | Field name, field path, thời gian và outcome |
| graphql.dataloader | Batch loader và @BatchMapping | Loader name, số phần tử được tải, outcome |

Để phát observation, ứng dụng cần có ObservationRegistry và cấu hình GraphQlObservationInstrumentation. Spring Boot có auto-configuration cho GraphQL observation khi observability infrastructure phù hợp được bật.

Data fetcher observation chỉ được tạo cho thao tác fetch không trivial. Đọc property đơn giản từ Java object thường không tạo observation riêng. DataLoader observation theo dõi @BatchMapping và DataLoader đã đăng ký.

Khi xem dashboard hoặc trace, hãy tìm:

- Operation có p95/p99 cao bất thường.
- Field path có thời gian xử lý lớn.
- DataLoader có batch size nhỏ hoặc số lần dispatch lớn bất thường.
- Request lỗi hoặc timeout tăng sau khi thay đổi schema/resolver.
- Sự khác biệt giữa thời gian GraphQL request và thời gian database/downstream.

Không đưa raw query, email, user ID hoặc giá trị argument có cardinality cao vào metric tag. Dùng operation name, field name, outcome và execution ID để truy vết; giữ thông tin nhạy cảm trong log/trace có kiểm soát truy cập.

## Cách benchmark một query

Một quy trình đo có thể lặp lại:

1. Chuẩn bị dataset có số lượng và phân bố quan hệ gần với production.
2. Gửi operation với page size và selection set cố định.
3. Warm up ứng dụng và connection pool trước khi ghi số liệu.
4. Đo p50, p95, p99, throughput và tỷ lệ lỗi.
5. Ghi số query database, số lần gọi downstream, batch size và response bytes.
6. Tăng concurrency để quan sát khi nào connection pool hoặc CPU bão hòa.
7. Thay đổi một yếu tố mỗi lần: pagination, batching, selection set, cache hoặc resolver.
8. So sánh cùng điều kiện trước và sau thay đổi.

Đối với database chậm, dùng query plan hoặc EXPLAIN ANALYZE ở tầng database để biết bottleneck là index, join, sort hay số hàng được đọc. Một GraphQL field có thể nhanh ở resolver nhưng query SQL phía dưới vẫn quét quá nhiều dữ liệu.

Không chỉ đo một lần ở local. Độ trễ mạng, connection pool, cache warm/cold và tải đồng thời có thể làm kết quả khác xa production.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query ít field nhưng vẫn chậm | Một resolver gọi downstream chậm hoặc database query kém | Đo data fetcher và query plan |
| Query depth thấp nhưng tải quá nhiều dữ liệu | Collection lớn hoặc nested list có page size cao | Giới hạn page size và dùng complexity có multiplier |
| Query depth cao nhưng server không quá tải | Nhiều field chỉ đọc property đã có sẵn | Kết hợp depth với complexity và số liệu thực |
| Một query danh sách tạo hàng chục query SQL | N+1 ở nested resolver | Dùng @BatchMapping hoặc DataLoader |
| Batching giảm SQL nhưng response vẫn chậm | Payload lớn hoặc nhiều object cần serialize | Giảm selection set, page size và dữ liệu trả về |
| Complexity limit không chặn page size lớn | Dùng default calculator không xét argument | Viết FieldComplexityCalculator theo first/last/limit |
| Query hợp lệ nhưng chạy quá lâu | Không có request/downstream timeout | Cấu hình TimeoutWebGraphQlInterceptor và timeout riêng |
| CPU cao với document lặp lại | Parse và validation lặp lại | Cân nhắc PreparsedDocumentProvider hoặc persisted query |
| Cache document tăng heap liên tục | Cache mọi query text mà không giới hạn | Đặt maximum size, eviction và theo dõi hit/miss |
| WebFlux bị nghẽn dù resolver trả Mono | Blocking call chạy trước khi Mono được tạo hoặc chạy trên event-loop | Dùng reactive driver hoặc executor cho blocking work |
| Observation không thấy field đơn giản | PropertyDataFetcher được xem là trivial | Theo dõi request observation và đo các resolver quan trọng |
| Tăng concurrency làm database chậm hơn | Connection pool hoặc downstream đã bão hòa | Giới hạn concurrency và giảm số lần I/O bằng batching |

## Thực hành tổng hợp

Xây dựng chính sách chi phí cho API thư viện:

1. Khai báo Query.books(first: Int = 20) và Book.reviews(first: Int = 10).
2. Tạo query lấy 50 Book, mỗi Book có Author và 10 Review.
3. Tính số object tối đa có thể được yêu cầu và giải thích vì sao depth đơn lẻ không phản ánh chi phí.
4. Viết resolver nested field theo cách N+1 và đo số lần truy cập repository.
5. Thay resolver bằng @BatchMapping hoặc DataLoader; so sánh số query database.
6. Giới hạn page size tối đa ở service/resolver.
7. Đăng ký MaxQueryDepthInstrumentation và MaxQueryComplexityInstrumentation.
8. Viết FieldComplexityCalculator sử dụng first hoặc last để nhân chi phí con.
9. Kiểm thử query nằm dưới và vượt complexity threshold.
10. Cấu hình PreparsedDocumentProvider nếu cùng document được gửi lặp lại nhiều lần.
11. Bật Micrometer GraphQL observations và quan sát request, data fetcher, DataLoader.
12. Cấu hình TimeoutWebGraphQlInterceptor và xác minh reactive publisher nhận cancellation.
13. Benchmark trước/sau với cùng dataset, concurrency và selection set.

Sau khi hoàn thành, hãy giải thích vì sao DataLoader không làm giảm response size, vì sao depth limit không thay thế complexity limit và tại sao cache parsed document không phải cache response.

## Ghi nhớ

Chi phí GraphQL request đến từ parse/validation, data fetching, nested field completion, collection size, serialization và network transfer. Depth chỉ đo số tầng; breadth và page size quyết định số object có thể được tải. N+1 làm tăng số round trip backend; DataLoader và @BatchMapping gom các lần tải nhưng không làm giảm số object client yêu cầu. Hãy giới hạn page size, ước lượng query bằng MaxQueryComplexityInstrumentation với FieldComplexityCalculator, kết hợp depth limit và timeout. PreparsedDocumentProvider giảm chi phí parse/validation nhưng không cache dữ liệu. Dùng Micrometer observations, query plan và benchmark p95/p99 để xác định bottleneck trước khi tối ưu.

## Tài liệu tham khảo

- [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL – Annotated Controllers and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java – Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java – Limits](https://graphql-java.com/documentation/limits/)
- [GraphQL Java – Batching](https://graphql-java.com/documentation/batching/)
