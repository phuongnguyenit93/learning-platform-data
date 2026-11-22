# Reactive data fetcher

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách một GraphQL `DataFetcher` trả về `Mono` hoặc `Flux` trong Spring for GraphQL.
- Phân biệt hợp đồng bất đồng bộ của GraphQL Java với cơ chế hỗ trợ Reactor của Spring.
- Đăng ký reactive DataFetcher trực tiếp bằng `RuntimeWiringConfigurer`.
- Hiểu cách Spring chuyển reactive result thành `CompletableFuture` cho Query và Mutation.
- Phân biệt `Flux` được gom thành list trong Query với publisher dùng cho Subscription.
- Xử lý publisher rỗng, lỗi, Reactor Context và lời gọi blocking.
- Tích hợp reactive repository và kiểm thử DataFetcher bằng `GraphQlTester`.

## 1. Reactive DataFetcher là gì?

Trong GraphQL Java, `DataFetcher` là thành phần cung cấp giá trị cho một field trong schema. Một DataFetcher có thể trả về object thông thường hoặc một kết quả bất đồng bộ như `CompletionStage`.

Spring for GraphQL mở rộng cách tích hợp này để DataFetcher có thể trả về Reactor `Mono` hoặc `Flux`. GraphQL runtime vẫn thực thi operation theo cơ chế bất đồng bộ, còn Spring đảm nhiệm việc chuyển đổi publisher sang dạng mà GraphQL Java sử dụng.

Ví dụ, một field lấy sách theo ID có thể trả về `Mono<Book>`:

~~~java
DataFetcher<Mono<Book>> bookFetcher =
        environment -> bookService.findById(
                environment.getArgument("id"));
~~~

Một field lấy nhiều sách có thể trả về `Flux<Book>`:

~~~java
DataFetcher<Flux<Book>> booksFetcher =
        environment -> bookService.findAll();
~~~

Điểm quan trọng là reactive DataFetcher không cần tự gọi `subscribe()` để kích hoạt publisher. GraphQL runtime quản lý quá trình thực thi và nhận kết quả thông qua cơ chế tích hợp của Spring for GraphQL.

## 2. Spring chuyển Mono và Flux như thế nào?

Builder mặc định của `GraphQlSource` bật hỗ trợ reactive DataFetcher. Spring chuyển đổi kết quả Reactor theo loại GraphQL operation:

| Kết quả DataFetcher | Query hoặc Mutation | Subscription |
|---|---|---|
| `Mono<T>` | Chuyển thành `CompletableFuture<T>` | Publisher hoàn tất một giá trị hoặc không có giá trị |
| `Flux<T>` | Gom các phần tử thành List rồi chuyển thành `CompletableFuture<List<T>>` | Giữ publisher để phát các event theo thời gian |
| `T` | Trả giá trị trực tiếp | Có thể là giá trị khởi tạo tùy cách thiết kế operation |
| `CompletionStage<T>` | GraphQL Java xử lý bất đồng bộ | Phù hợp với kết quả bất đồng bộ đơn |

Với Query và Mutation, một `Flux<Book>` không làm response GraphQL được gửi thành nhiều lần. Spring thu thập các phần tử thành một list để hoàn thành response của operation.

Ví dụ SDL:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

DataFetcher trả `Flux<Book>` sẽ tạo dữ liệu cho field `books`. Client nhận một response chứa danh sách sách sau khi field hoàn tất.

Với Subscription, publisher được giữ lại để GraphQL Java xử lý luồng event. Đây là khác biệt quan trọng giữa một field list trong Query và một luồng cập nhật theo thời gian.

## 3. Đăng ký reactive DataFetcher bằng RuntimeWiringConfigurer

Khi cần làm việc trực tiếp với GraphQL Java, bạn có thể tạo DataFetcher trả về `Mono` hoặc `Flux` rồi đăng ký trong `RuntimeWiringConfigurer`.

SDL:

~~~graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

Service:

~~~java
public interface BookService {
    Mono<Book> findById(String id);
    Flux<Book> findFirst(int limit);
}
~~~

Cấu hình:

~~~java
@Configuration
public class ReactiveBookWiring {

    @Bean
    RuntimeWiringConfigurer reactiveBookFetchers(BookService bookService) {

        DataFetcher<Mono<Book>> bookFetcher = environment -> {
            String id = environment.getArgument("id");
            return bookService.findById(id);
        };

        DataFetcher<Flux<Book>> booksFetcher = environment -> {
            Integer first = environment.getArgument("first");
            int limit = first == null ? 20 : first;
            return bookService.findFirst(limit);
        };

        return builder -> builder.type("Query", typeBuilder ->
                typeBuilder
                        .dataFetcher("book", bookFetcher)
                        .dataFetcher("books", booksFetcher)
        );
    }
}
~~~

Các điểm cần chú ý:

- `DataFetcher` vẫn được đăng ký vào đúng GraphQL type và field trong SDL.
- `environment.getArgument(...)` lấy argument của field đang chạy.
- Service trả publisher; DataFetcher không tự chờ kết quả.
- Spring Boot tự phát hiện bean `RuntimeWiringConfigurer` và đưa vào quá trình xây dựng `GraphQlSource`.

Nên dùng constructor injection hoặc tham số bean method để cung cấp service cho configurer. Không tạo repository hoặc service mới bên trong DataFetcher.

## 4. Reactive return type trong annotated controller

Nếu không cần đăng ký DataFetcher thủ công, có thể dùng annotated controller. Spring đăng ký các method controller thành DataFetcher và hỗ trợ cùng các reactive return type.

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> books(@Argument Integer first) {
        int limit = first == null ? 20 : first;
        return bookService.findFirst(limit);
    }
}
~~~

Hai phong cách có cùng mục tiêu cung cấp dữ liệu bất đồng bộ cho field:

- Dùng annotated controller khi muốn method Java và annotation mô tả trực tiếp mapping.
- Dùng `RuntimeWiringConfigurer` khi cần kiểm soát DataFetcher ở tầng GraphQL Java hoặc tích hợp một thành phần tạo DataFetcher sẵn.

Không nên đăng ký cả controller mapping và một DataFetcher thủ công cho cùng một field nếu không có chủ đích rõ ràng. Hai nơi cùng sở hữu mapping có thể gây xung đột hoặc khiến cấu hình khó theo dõi.

## 5. Kết hợp nhiều reactive nguồn dữ liệu

Một DataFetcher có thể phối hợp nhiều service bất đồng bộ. Reactor cung cấp các toán tử để kết hợp publisher mà không phải block thread.

Ví dụ, trang chi tiết sách cần thông tin Book và số lượng review:

~~~graphql
type Query {
  bookSummary(id: ID!): BookSummary
}

type BookSummary {
  book: Book!
  reviewCount: Int!
}
~~~

DataFetcher:

~~~java
DataFetcher<Mono<BookSummary>> summaryFetcher = environment -> {
    String id = environment.getArgument("id");

    Mono<Book> book = bookService.findById(id);
    Mono<Integer> reviewCount = reviewService.countByBookId(id);

    return Mono.zip(book, reviewCount)
            .map(tuple -> new BookSummary(
                    tuple.getT1(),
                    tuple.getT2()));
};
~~~

`Mono.zip` kết hợp kết quả khi các publisher đầu vào đều phát ra giá trị. Các lời gọi độc lập có thể tiến triển bất đồng bộ mà không cần viết callback lồng nhau.

Nếu `bookService.findById` có thể trả `Mono.empty()`, `Mono.zip` cũng có thể hoàn tất rỗng và không tạo `BookSummary`. Hãy xác định hành vi khi không tìm thấy Book trước khi kết hợp:

~~~java
return bookService.findById(id)
        .switchIfEmpty(Mono.error(new BookNotFoundException(id)))
        .flatMap(book ->
                reviewService.countByBookId(id)
                        .map(count -> new BookSummary(book, count)));
~~~

Dùng `map` cho phép biến đổi giá trị đồng bộ; dùng `flatMap` khi bước tiếp theo trả về publisher. Tránh tạo publisher lồng nhau như `Mono<Mono<T>>` khi mục tiêu là một chuỗi xử lý duy nhất.

## 6. Xử lý Mono rỗng và nullability của GraphQL

`Mono.empty()` biểu diễn trường hợp publisher hoàn tất mà không phát ra giá trị. Khi được chuyển thành kết quả GraphQL, điều này tương ứng với field không có giá trị, thường được thể hiện là `null`.

Schema phải cho phép kết quả đó nếu đây là tình huống bình thường.

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Với field nullable, không tìm thấy sách có thể trả `null`. Nếu schema khai báo:

~~~graphql
type Query {
  book(id: ID!): Book!
}
~~~

thì resolver không được hoàn tất mà không có giá trị. Nếu DataFetcher trả `Mono.empty()`, GraphQL tạo lỗi thực thi và áp dụng quy tắc null propagation.

Có thể chuyển publisher rỗng thành lỗi nghiệp vụ nếu API yêu cầu sách phải tồn tại:

~~~java
return bookService.findById(id)
        .switchIfEmpty(Mono.error(
                new BookNotFoundException(id)));
~~~

Với field list:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

`Flux.empty()` tạo danh sách rỗng, không phải null. Đây là kết quả hợp lệ vì danh sách tồn tại nhưng không có phần tử.

Cần phân biệt:

- `Mono.empty()`: không có giá trị cho field đơn.
- `Flux.empty()`: danh sách không có phần tử trong Query.
- `Mono.error(...)` hoặc `Flux.error(...)`: publisher kết thúc bằng lỗi.

## 7. Xử lý lỗi từ reactive DataFetcher

Lỗi có thể phát sinh khi truy cập database, gọi service bên ngoài hoặc biến đổi dữ liệu. Lỗi trong reactive pipeline được truyền xuống GraphQL runtime khi publisher phát tín hiệu error.

Ví dụ chuyển lỗi kỹ thuật thành exception nghiệp vụ:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return bookService.findById(id)
            .onErrorMap(
                    DataAccessException.class,
                    ex -> new BookLookupException(
                            "Unable to load book " + id, ex)
            );
};
~~~

Spring for GraphQL có thể dùng `DataFetcherExceptionResolver` để chuyển exception thành GraphQL error phù hợp:

~~~java
@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Book was not found")
                    .errorType(ErrorType.NOT_FOUND)
                    .build();
        }

        return null;
    }
}
~~~

Resolver ví dụ trên chỉ xử lý loại lỗi được nhận diện; trả `null` cho loại khác để cơ chế xử lý tiếp theo áp dụng. Không nên đưa SQL, stack trace hoặc thông tin nhạy cảm vào message công khai.

Một số nguyên tắc:

- Dùng `onErrorMap` khi cần đổi loại exception.
- Dùng `onErrorResume` khi có kết quả thay thế hợp lệ.
- Không chuyển mọi lỗi thành `Mono.empty()`, vì điều đó che giấu sự cố.
- Giữ phân biệt giữa không tìm thấy dữ liệu, vi phạm nghiệp vụ và lỗi hạ tầng.
- Kiểm tra nullability của field để hiểu lỗi sẽ lan lên response như thế nào.

## 8. Phân biệt Flux trong Query với Flux trong Subscription

Spring for GraphQL xử lý `Flux` khác nhau tùy loại operation đang được thực thi.

Query lấy danh sách:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

~~~java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

Các phần tử Flux được gom thành list để tạo một GraphQL response cho Query. Client không nhận từng sách thành các response riêng biệt.

Subscription nhận event:

~~~graphql
type Subscription {
  bookAdded: Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return bookEventPublisher.events();
}
~~~

Với Subscription, Flux là publisher phát nhiều event theo thời gian. GraphQL Java thực thi các field được chọn cho mỗi event và phát kết quả subscription tương ứng.

| Tiêu chí | Flux trong Query | Flux trong Subscription |
|---|---|---|
| Ý nghĩa | Tập hợp phần tử của một field list | Luồng event theo thời gian |
| Spring xử lý | Aggregate thành List | Giữ Reactive Streams Publisher |
| Số GraphQL response | Một response cho operation | Nhiều response/event |
| Kết thúc | Khi publisher hoàn tất | Khi publisher hoàn tất hoặc subscription bị hủy |
| Ví dụ | Danh sách sách | Thông báo khi có sách mới |

Nếu cần giữ thứ tự event gốc trong trường hợp các event được thực thi bất đồng bộ, GraphQL Java có tùy chọn `SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED` trong `GraphQLContext`. Khi bật, GraphQL Java có thể cần buffer event để giữ thứ tự; hãy cân nhắc độ trễ và bộ nhớ trước khi áp dụng.

## 9. Reactive Context trong DataFetcher

Với WebFlux, Spring for GraphQL hỗ trợ truyền Reactor Context từ chuỗi xử lý request đến reactive DataFetcher. Nhờ đó, publisher có thể truy cập metadata được thiết lập ở tầng transport hoặc `WebGraphQlInterceptor`.

Ví dụ dùng Reactor Context trong service:

~~~java
public Mono<Book> findForCurrentTenant(String id) {
    return Mono.deferContextual(contextView -> {
        String tenantId = contextView.get("tenantId");
        return repository.findByIdAndTenantId(id, tenantId);
    });
}
~~~

DataFetcher có thể gọi service này như bình thường:

~~~java
DataFetcher<Mono<Book>> bookFetcher =
        environment -> bookService.findForCurrentTenant(
                environment.getArgument("id"));
~~~

Reactor Context phù hợp với metadata cần đi theo reactive chain. Nó khác với source object và GraphQL field argument:

| Dữ liệu | Phạm vi | Ví dụ |
|---|---|---|
| Source object | Field cha hiện tại | Book được trả về từ Query |
| Argument | Field đang thực thi | ID do client gửi |
| GraphQLContext | Một GraphQL request | Metadata dùng chung |
| Reactor Context | Reactive chain | Tenant, tracing hoặc security metadata được truyền qua pipeline |

Không lưu user hoặc tenant hiện tại trong field mutable của singleton DataFetcher. Các request đồng thời có thể ghi đè dữ liệu của nhau. Hãy dùng context có phạm vi đúng và chỉ tin metadata do tầng xác thực đáng tin cậy đưa vào.

## 10. Tránh blocking trong reactive DataFetcher

Một DataFetcher trả về Mono không tự làm cho thao tác bên trong trở thành non-blocking. Nếu publisher gọi JPA repository đồng bộ trực tiếp, thread vẫn bị giữ trong lúc database call chạy.

Không nên viết:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment ->
        Mono.just(jpaRepository.findById(
                environment.getArgument("id")).orElse(null));
~~~

Lời gọi JPA đã chạy ngay trước khi `Mono.just` được tạo. Nó vẫn là blocking.

Nếu tạm thời phải tích hợp API blocking, có thể trì hoãn lời gọi bằng `Mono.fromCallable` và chuyển nó sang bounded elastic scheduler:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return Mono.fromCallable(() ->
                    jpaRepository.findById(id).orElse(null))
            .subscribeOn(Schedulers.boundedElastic());
};
~~~

Cách này cô lập blocking call khỏi event-loop thread nhưng không biến JPA thành reactive. Thread của bounded elastic vẫn bị chiếm trong thời gian truy cập database.

Nếu có thể, hãy dùng reactive driver hoặc client phù hợp với hệ thống, ví dụ R2DBC cho database được hỗ trợ. Không dùng `Schedulers.parallel()` cho tác vụ blocking và không xem bounded elastic là tài nguyên vô hạn.

## 11. Reactive Spring Data DataFetcher

Spring for GraphQL có các tích hợp giúp tạo DataFetcher từ Spring Data repository. Với repository reactive, builder có thể tạo DataFetcher trả về `Mono` hoặc `Flux`.

Ví dụ với Querydsl:

~~~java
DataFetcher<Mono<Account>> accountFetcher =
        QuerydslDataFetcher.builder(reactiveRepository).single();

DataFetcher<Flux<Account>> accountsFetcher =
        QuerydslDataFetcher.builder(reactiveRepository).many();
~~~

Repository cần triển khai reactive Querydsl executor phù hợp, chẳng hạn `ReactiveQuerydslPredicateExecutor`. Tương tự, Query by Example có thể tạo DataFetcher reactive khi repository hỗ trợ `ReactiveQueryByExampleExecutor`.

Các DataFetcher này có thể được đăng ký qua `RuntimeWiringConfigurer`:

~~~java
@Bean
RuntimeWiringConfigurer accountFetchers(
        DataFetcher<Mono<Account>> accountFetcher,
        DataFetcher<Flux<Account>> accountsFetcher) {

    return builder -> builder.type("Query", typeBuilder ->
            typeBuilder
                    .dataFetcher("account", accountFetcher)
                    .dataFetcher("accounts", accountsFetcher)
    );
}
~~~

Đây là ví dụ về cách tổ chức wiring; các bean DataFetcher cần được tạo từ repository và builder tương ứng của ứng dụng. Trước khi dùng, kiểm tra module Spring Data, loại database và repository interface có hỗ trợ reactive Querydsl hoặc Query by Example hay không.

Không phải mọi Spring Data module đều có reactive repository cho mọi tính năng. Nếu repository chỉ hỗ trợ blocking, builder không thể tự biến truy cập blocking thành reactive.

## 12. Giới hạn kết quả và tài nguyên

Reactive publisher có thể phát ra rất nhiều phần tử. Với Query, Spring cần gom `Flux` thành list để hoàn thành response, vì vậy một Flux không giới hạn có thể làm tăng bộ nhớ và thời gian xử lý.

Hãy đặt giới hạn ngay trong schema và DataFetcher:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

~~~java
DataFetcher<Flux<Book>> booksFetcher = environment -> {
    Integer first = environment.getArgument("first");
    int limit = first == null ? 20 : first;

    if (limit < 1 || limit > 100) {
        return Flux.error(
                new IllegalArgumentException(
                        "first must be between 1 and 100"));
    }

    return bookService.findFirst(limit);
};
~~~

Với dữ liệu lớn, nên dùng cursor pagination hoặc connection type thay vì tải toàn bộ collection. Cần cân nhắc:

- Giới hạn số phần tử tối đa.
- Timeout cho lời gọi downstream.
- Giới hạn concurrency khi gọi nhiều service.
- Batch loading để tránh N+1.
- Theo dõi thời gian DataFetcher và số phần tử được trả về.
- Hủy publisher khi request hoặc subscription bị hủy.

Backpressure hữu ích với luồng reactive, nhưng Query vẫn cần thu thập kết quả để tạo response hoàn chỉnh. Giới hạn nghiệp vụ và pagination vẫn rất cần thiết.

## 13. Kiểm thử reactive DataFetcher

Có thể kiểm thử DataFetcher trực tiếp hoặc thông qua GraphQL runtime. Integration test qua `GraphQlTester` giúp xác nhận cả SDL, wiring, reactive adaptation và response.

Ví dụ:

~~~java
@Test
void shouldResolveBookFromReactiveDataFetcher() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "b-01")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("b-01");
}
~~~

Các trường hợp nên kiểm thử:

1. `Mono` phát một giá trị và field trả đúng object.
2. `Mono.empty()` với field nullable.
3. `Mono.empty()` với field non-null.
4. `Flux` phát nhiều phần tử và Query trả một list đúng thứ tự.
5. `Flux.empty()` tạo list rỗng cho field list non-null.
6. Publisher phát lỗi và exception resolver tạo GraphQL error phù hợp.
7. Reactive Context được truyền tới DataFetcher khi chạy qua WebFlux.
8. Subscription phát nhiều event và kết thúc đúng vòng đời.
9. Publisher bị hủy khi client hủy subscription.
10. Giới hạn pagination từ chối giá trị ngoài phạm vi.

Không gọi `subscribe()` thủ công trong test để kích hoạt DataFetcher. Hãy để GraphQL runtime và GraphQlTester thực thi operation, sau đó kiểm tra dữ liệu và errors.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Field trả về object Mono thay vì dữ liệu | Reactive adaptation không được cấu hình trong GraphQlSource | Dùng builder mặc định của Spring for GraphQL |
| Query list chỉ trả một response | Đây là hành vi request-response bình thường | Dùng Subscription nếu cần stream event |
| Query Flux tiêu thụ quá nhiều bộ nhớ | Flux phát quá nhiều phần tử và bị aggregate thành List | Thêm giới hạn và pagination |
| Field trả null ngoài dự kiến | Mono.empty hoặc service không tìm thấy dữ liệu | Kiểm tra nullability và switchIfEmpty |
| Lỗi bị biến thành null | Dùng onErrorResume thành Mono.empty không phù hợp | Giữ lỗi và xử lý bằng exception resolver |
| Event subscription sai thứ tự | Các event và field được thực thi bất đồng bộ | Cân nhắc tùy chọn giữ thứ tự của GraphQL Java |
| Event loop bị nghẽn | Gọi blocking API trực tiếp trong publisher | Dùng reactive client hoặc cô lập blocking call |
| Tenant/user bị lẫn giữa request | Lưu metadata trong state mutable dùng chung | Dùng Reactor Context hoặc GraphQLContext đúng phạm vi |

## 15. Nguyên tắc thiết kế reactive DataFetcher

Khi triển khai DataFetcher reactive:

- Trả `Mono` cho field đơn và `Flux` cho field list hoặc subscription phù hợp.
- Dùng builder mặc định của `GraphQlSource` để có reactive adaptation.
- Không gọi `block()` hoặc `subscribe()` bên trong DataFetcher.
- Kết hợp publisher bằng `map`, `flatMap`, `zip` theo đúng kiểu dữ liệu.
- Thiết kế nullability tương thích với `Mono.empty()` và kết quả list rỗng.
- Xử lý lỗi rõ ràng bằng Reactor operator và `DataFetcherExceptionResolver`.
- Không gọi blocking API trực tiếp trên event-loop thread.
- Dùng Reactor Context cho metadata theo reactive chain.
- Giới hạn kết quả Query và dùng pagination.
- Dùng reactive repository khi nguồn dữ liệu hỗ trợ.
- Kiểm thử cả Query, Subscription, empty, error và cancellation.

## Kết luận

Spring for GraphQL hỗ trợ DataFetcher trả về `Mono` và `Flux` thông qua reactive adaptation của `GraphQlSource`. Với Query và Mutation, publisher được chuyển thành `CompletableFuture`; các giá trị Flux được gom thành List. Với Subscription, publisher được giữ lại để phát nhiều GraphQL response theo thời gian.

Bạn có thể đăng ký reactive DataFetcher trực tiếp bằng `RuntimeWiringConfigurer` hoặc dùng annotated controller. Dù chọn cách nào, hãy giữ pipeline non-blocking, xử lý empty và error theo nullability, truyền context đúng phạm vi và giới hạn dữ liệu cần aggregate. Những nguyên tắc này giúp GraphQL runtime tận dụng được reactive stack mà vẫn giữ response, lỗi và vòng đời operation dễ kiểm soát.

## Tài liệu tham khảo

- [Spring for GraphQL — Reactive DataFetcher and Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and Return Values](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Reactive Data Integration](https://docs.spring.io/spring-graphql/reference/data.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [GraphQL Java — DataFetcher API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetcher.html)
