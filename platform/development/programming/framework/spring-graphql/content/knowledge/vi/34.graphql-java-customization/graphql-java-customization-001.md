# Custom DataFetcher

Trong Spring for GraphQL, mỗi field trong GraphQL schema cần một cách lấy giá trị khi client truy vấn. GraphQL Java giao nhiệm vụ đó cho `DataFetcher`. Một data fetcher có thể đọc dữ liệu từ repository, gọi application service, tính giá trị từ object cha hoặc kết hợp nhiều nguồn dữ liệu để trả về giá trị cho field.

Spring for GraphQL thường khuyến nghị dùng `@QueryMapping`, `@MutationMapping` và `@SchemaMapping` trong controller vì chúng tích hợp tốt với dependency injection, argument binding và các cơ chế của Spring. Tuy vậy, có những trường hợp cần đăng ký trực tiếp một `DataFetcher`, chẳng hạn tích hợp resolver GraphQL Java hiện có, tùy chỉnh một field đặc biệt hoặc dùng API GraphQL Java mà controller annotation không diễn đạt thuận tiện.

Bài này trình bày cách xây dựng `DataFetcher`, đọc `DataFetchingEnvironment`, đăng ký field bằng `RuntimeWiringConfigurer`, xử lý lỗi, truyền local context, kết hợp DataLoader và kiểm thử.

## 1. DataFetcher nằm ở đâu trong quá trình thực thi?

Một GraphQL schema mô tả kiểu và field mà client có thể yêu cầu. Khi GraphQL Java thực thi một operation, nó gọi `DataFetcher` được gắn với từng field để lấy giá trị runtime.

~~~mermaid
flowchart TD
    A[GraphQL document] --> B[Validate against schema]
    B --> C[Execute selected field]
    C --> D[Invoke DataFetcher]
    D --> E[Read arguments and context]
    E --> F[Call service or repository]
    F --> G[Return value]
    G --> H[Complete child fields]
    H --> I[Build GraphQL response]
~~~

Ví dụ schema:

~~~graphql
type Query {
    books(term: String!, limit: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

Field `Query.books` cần lấy danh sách sách theo từ khóa và giới hạn. Field `Book.title` có thể chỉ cần đọc thuộc tính `title` từ object `Book` mà field cha trả về. Hai field đều có data fetcher, nhưng cách lấy dữ liệu khác nhau.

GraphQL Java thường dùng `PropertyDataFetcher` làm data fetcher mặc định để đọc property từ source object. Vì vậy, không phải field nào cũng cần viết resolver riêng. Chỉ tạo custom `DataFetcher` khi cần truy vấn dữ liệu, áp dụng nghiệp vụ, gọi dịch vụ ngoài hoặc chuyển đổi dữ liệu.

## 2. Hợp đồng của DataFetcher

`DataFetcher<T>` là interface của GraphQL Java với một phương thức chính:

~~~java
public interface DataFetcher<T> {
    T get(DataFetchingEnvironment environment) throws Exception;
}
~~~

Generic `T` biểu thị kiểu giá trị mà data fetcher trả về. Giá trị đó có thể là object đơn, collection, `CompletionStage`, reactive publisher được cấu hình hỗ trợ, hoặc `DataFetcherResult`.

Phương thức `get` nhận `DataFetchingEnvironment`, chứa thông tin của lần resolve field hiện tại. Data fetcher không cần tự phân tích GraphQL document để tìm argument hoặc field đang chạy.

Một data fetcher nên có các đặc điểm:

- Chỉ thực hiện công việc cần thiết để resolve field.
- Nhận dependency qua constructor hoặc Spring dependency injection.
- Không giữ dữ liệu riêng của request trong instance field.
- Không tự tạo `GraphQL` instance hoặc tự thực thi lại document.
- Trả về kiểu dữ liệu tương thích với kiểu field trong schema.

Nếu data fetcher ném exception, GraphQL Java chuyển exception qua `DataFetcherExceptionHandler` đã cấu hình. Spring for GraphQL có thể kết hợp `DataFetcherExceptionResolver` để chuyển exception thành GraphQL error.

## 3. DataFetchingEnvironment cung cấp những gì?

`DataFetchingEnvironment` là điểm truy cập chính của custom data fetcher. Một số phương thức thường dùng:

| Phương thức | Mục đích |
| --- | --- |
| `getArgument(name)` | Đọc argument của field |
| `containsArgument(name)` | Kiểm tra argument có được gửi hay không |
| `getSource()` | Lấy object cha đang được resolve |
| `getGraphQlContext()` | Đọc context dùng chung trong GraphQL execution |
| `getLocalContext()` | Đọc context được truyền từ field cha |
| `getField()` | Lấy thông tin field hiện tại |
| `getExecutionStepInfo()` | Lấy thông tin vị trí và kiểu của bước thực thi |
| `getSelectionSet()` | Kiểm tra các field con được yêu cầu |
| `getLocale()` | Lấy locale của execution |
| `getDataLoader(name)` | Lấy DataLoader đã đăng ký |

Ví dụ đọc argument:

~~~java
String term = environment.getArgument("term");
Integer limit = environment.getArgument("limit");
~~~

`getArgument` là generic method. Hãy gán kết quả vào kiểu phù hợp với GraphQL schema và kiểm tra null khi argument có thể vắng mặt hoặc có default value.

Có thể dùng `containsArgument` khi cần phân biệt client không gửi argument với client gửi giá trị `null`:

~~~java
if (environment.containsArgument("limit")) {
    Integer requestedLimit = environment.getArgument("limit");
    // Apply the requested value according to the API contract.
}
~~~

Không nên đọc trực tiếp raw variables rồi tự bind lại. GraphQL Java đã thực hiện parse, validation và coercion argument theo schema trước khi gọi data fetcher.

## 4. Viết custom DataFetcher cho Query.books

Giả sử application service có phương thức tìm sách:

~~~java
package com.example.books.application;

import java.util.List;
import java.util.Optional;

public interface BookCatalogService {
    List<BookView> search(String term, int limit);
    Optional<BookView> findById(String id);
}
~~~

Tạo data fetcher riêng:

~~~java
package com.example.books.graphql;

import java.util.List;

import com.example.books.application.BookCatalogService;
import com.example.books.application.BookView;

import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.stereotype.Component;

@Component
public class BookSearchDataFetcher implements DataFetcher<List<BookView>> {

    private final BookCatalogService catalogService;

    public BookSearchDataFetcher(BookCatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public List<BookView> get(DataFetchingEnvironment environment) {
        String term = environment.getArgument("term");
        Integer requestedLimit = environment.getArgument("limit");

        int limit = requestedLimit == null
            ? 20
            : Math.min(Math.max(requestedLimit, 1), 100);

        return catalogService.search(term, limit);
    }
}
~~~

Data fetcher dùng constructor injection để nhận service. Nó áp dụng giới hạn mặc định là 20 và chặn giá trị client yêu cầu trong khoảng từ 1 đến 100. Giới hạn này bảo vệ backend khỏi truy vấn quá lớn; trong ứng dụng thực tế, nên đồng bộ giới hạn với chính sách phân trang của API.

Không lưu `term`, `limit` hoặc `DataFetchingEnvironment` vào field của `BookSearchDataFetcher`. Bean được Spring quản lý thường có singleton scope và nhiều request có thể thực thi đồng thời trên cùng instance. Dữ liệu request phải nằm trong biến local của lần gọi `get`.

## 5. Đăng ký DataFetcher bằng RuntimeWiringConfigurer

GraphQL Java gắn data fetcher với một field cụ thể trong schema. Trong Spring for GraphQL, `RuntimeWiringConfigurer` cho phép tùy chỉnh `RuntimeWiring.Builder`.

~~~java
package com.example.books.graphql;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class BookGraphQlConfiguration {

    @Bean
    RuntimeWiringConfigurer bookSearchConfigurer(
            BookSearchDataFetcher bookSearchDataFetcher) {

        return wiringBuilder -> wiringBuilder.type(
            "Query",
            typeBuilder -> typeBuilder.dataFetcher(
                "books",
                bookSearchDataFetcher
            )
        );
    }
}
~~~

Cấu hình trên đăng ký `BookSearchDataFetcher` cho tọa độ field `Query.books`. Tên type và field phải khớp với schema SDL đã nạp.

Với Spring Boot GraphQL starter, các bean kiểu `RuntimeWiringConfigurer` được phát hiện và áp dụng vào `GraphQlSource.Builder`. Thông thường không cần tự tạo `GraphQL` hoặc `GraphQlSource` chỉ để đăng ký một data fetcher.

Nếu ứng dụng tự xây dựng `GraphQlSource` mà không dùng Boot auto-configuration, hãy áp dụng configurer vào builder trong quá trình tạo schema/runtime wiring.

## 6. Chọn đúng cách đăng ký resolver

Có nhiều cách để gắn logic resolve vào field:

| Cách | Khi nên dùng |
| --- | --- |
| `@QueryMapping` | Query root field trong Spring controller |
| `@MutationMapping` | Mutation root field trong Spring controller |
| `@SubscriptionMapping` | Subscription root field |
| `@SchemaMapping` | Field của một GraphQL object type |
| `RuntimeWiringConfigurer` + `DataFetcher` | Cần wiring trực tiếp theo GraphQL Java |
| `PropertyDataFetcher` | Field chỉ đọc property từ source object |

Ví dụ controller:

~~~java
import com.example.books.application.BookCatalogService;
import com.example.books.application.BookNotFoundException;
import com.example.books.application.BookView;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookCatalogService catalogService;

    public BookQueryController(BookCatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public BookView book(@Argument String id) {
        return catalogService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Spring đăng ký method `book` thành data fetcher cho field `Query.book`. Đây vẫn là `DataFetcher` ở tầng GraphQL Java, nhưng Spring tạo và quản lý việc wiring từ annotation.

Không đăng ký đồng thời `@QueryMapping` và `RuntimeWiringConfigurer` cho cùng một tọa độ `Query.book`. Hai cơ chế cùng cố gắng định nghĩa resolver cho một field sẽ khiến cấu hình khó hiểu và phụ thuộc thứ tự đăng ký. Mỗi field nên có một cơ chế wiring rõ ràng.

Dùng annotation controller làm lựa chọn mặc định cho resolver thông thường. Chọn `RuntimeWiringConfigurer` khi cần kiểm soát trực tiếp GraphQL Java runtime wiring hoặc tái sử dụng một `DataFetcher` đã có.

## 7. Resolve field con bằng source object

Data fetcher không chỉ dùng cho root field. Với một field thuộc object cha, `environment.getSource()` trả về giá trị mà data fetcher của field cha đã cung cấp.

Ví dụ, field Book.author cần lấy tác giả từ authorId của sách:

~~~java
import com.example.books.application.AuthorService;
import com.example.books.application.AuthorView;
import com.example.books.application.BookView;

import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.stereotype.Component;

@Component
public class BookAuthorLookupDataFetcher implements DataFetcher<AuthorView> {

    private final AuthorService authorService;

    public BookAuthorLookupDataFetcher(AuthorService authorService) {
        this.authorService = authorService;
    }

    @Override
    public AuthorView get(DataFetchingEnvironment environment) {
        BookView book = environment.getSource();
        return authorService.findById(book.authorId());
    }
}
~~~

Đăng ký field con:

~~~java
@Bean
RuntimeWiringConfigurer bookAuthorConfigurer(
        BookAuthorLookupDataFetcher authorDataFetcher) {

    return builder -> builder.type(
        "Book",
        type -> type.dataFetcher("author", authorDataFetcher)
    );
}
~~~

Trong trường hợp field author chỉ tương ứng với property có sẵn trên source object, không cần custom data fetcher. PropertyDataFetcher mặc định có thể đọc getter hoặc property phù hợp. Chỉ dùng resolver riêng khi cần truy vấn, kiểm tra quyền, chuyển đổi hoặc áp dụng logic bổ sung.

## 8. Dùng GraphQlContext cho dữ liệu theo request

DataFetchingEnvironment.getGraphQlContext() cung cấp context dùng chung trong một lần GraphQL execution. Ứng dụng có thể đưa vào đây dữ liệu đã xác thực hoặc metadata request, ví dụ tenant hiện tại, correlation ID hoặc locale đã được xác định ở tầng transport.

Ví dụ data fetcher lấy tenant từ GraphQL context:

~~~java
@Override
public List<BookView> get(DataFetchingEnvironment environment) {
    String tenantId = environment.getGraphQlContext().get("tenantId");
    String term = environment.getArgument("term");

    return catalogService.searchForTenant(tenantId, term);
}
~~~

Giá trị tenantId phải được thiết lập từ nguồn đáng tin cậy như authenticated principal hoặc request interceptor. Không lấy tenant ID do client truyền trong argument rồi coi đó là danh tính đã xác thực. Application service vẫn cần kiểm tra quyền truy cập dữ liệu theo chính sách bảo mật của ứng dụng.

GraphQL context được chia sẻ trong execution. Không dùng nó làm nơi lưu trạng thái mutable dùng chung giữa nhiều field song song. Nếu một field cha cần truyền dữ liệu riêng cho các field con của nó, cân nhắc localContext.

## 9. Truyền dữ liệu xuống field con bằng local context

DataFetcherResult cho phép trả về data cùng local context, errors hoặc extensions. Local context được truyền xuống các data fetcher của field con thông qua getLocalContext().

Ví dụ field cha đã tải thông tin chính sách hiển thị và muốn field con sử dụng lại:

~~~java
import graphql.execution.DataFetcherResult;
import graphql.schema.DataFetchingEnvironment;

@Override
public DataFetcherResult<BookView> get(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");
    BookView book = catalogService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));

    BookViewPolicy policy = policyService.policyFor(book);

    return DataFetcherResult.<BookView>newResult()
        .data(book)
        .localContext(policy)
        .build();
}
~~~

Data fetcher của field con có thể đọc context đó:

~~~java
@Override
public String get(DataFetchingEnvironment environment) {
    BookView book = environment.getSource();
    BookViewPolicy policy = environment.getLocalContext();

    return policy.canShowInternalCode()
        ? book.internalCode()
        : null;
}
~~~

Local context gắn với nhánh dữ liệu của field cha, phù hợp cho metadata chỉ cần truyền xuống các field con. Nó không thay thế GraphQL context dùng chung toàn execution, cũng không nên chứa object mutable để nhiều field cùng sửa.

Dùng DataFetcherResult khi cần truyền thêm metadata có chủ đích. Nếu chỉ trả một object bình thường, hãy trả object trực tiếp để resolver đơn giản hơn.

## 10. Trả data và GraphQL error bằng DataFetcherResult

Một data fetcher đôi khi có thể trả dữ liệu một phần đồng thời thêm lỗi vào response. DataFetcherResult hỗ trợ trường hợp đó:

~~~java
import graphql.execution.DataFetcherResult;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

@Override
public DataFetcherResult<BookView> get(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");
    BookView book = catalogService.findById(id).orElse(null);

    if (book == null) {
        return DataFetcherResult.<BookView>newResult()
            .data(null)
            .error(
                GraphqlErrorBuilder.newError(environment)
                    .message("Không tìm thấy sách")
                    .build()
            )
            .build();
    }

    return DataFetcherResult.<BookView>newResult()
        .data(book)
        .build();
}
~~~

DataFetcherResult hữu ích khi data fetcher cần chủ động tạo GraphQL error có path phù hợp hoặc truyền local context. Nó không tự biến lỗi thành một HTTP status riêng; GraphQL vẫn trả response theo quy tắc của execution và transport.

Cần chú ý nullability trong schema. Nếu field được khai báo non-null mà data fetcher trả null, GraphQL sẽ áp dụng null propagation lên parent theo schema. Thiết kế schema và cách trả partial data phải nhất quán với contract của API.

Không dùng DataFetcherResult để che giấu exception kỹ thuật. Lỗi kết nối database, lỗi hệ thống hoặc lỗi không mong đợi nên được xử lý qua exception resolver và logging tập trung.

## 11. Ném exception và xử lý tập trung

Một data fetcher có thể ném exception thay vì tự tạo DataFetcherResult:

~~~java
@Override
public BookView get(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");

    return catalogService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

GraphQL Java chuyển exception từ data fetcher qua exception handler. Với custom DataFetcher không xuất phát từ annotated controller, hãy đăng ký bean triển khai DataFetcherExceptionResolver. @GraphQlExceptionHandler mặc định áp dụng cho các lần gọi controller được quản lý bởi AnnotatedControllerConfigurer. Nếu muốn tái sử dụng exception handler của annotated controller cho custom fetcher, cần lấy resolver từ AnnotatedControllerConfigurer và đăng ký vào GraphQlSource.

Ví dụ resolver tập trung:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class BookExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .build();
        }

        return null;
    }
}
~~~

Khi resolver không xử lý exception, trả null để resolver tiếp theo trong chain có cơ hội xử lý. Không trả message chứa SQL, stack trace, token hoặc thông tin nội bộ cho client. Ghi log chi tiết ở server với correlation ID phù hợp.

Dùng exception resolver cho lỗi cần chuyển đổi nhất quán trên nhiều field. Dùng DataFetcherResult cho trường hợp một resolver chủ động trả partial data và metadata lỗi như một phần của kết quả.

## 12. DataFetcher bất đồng bộ

GraphQL Java hỗ trợ data fetcher trả về CompletionStage<T>. Điều này hữu ích khi application service đã cung cấp API bất đồng bộ:

~~~java
import java.util.concurrent.CompletionStage;

import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.stereotype.Component;

@Component
public class AsyncBookDataFetcher
        implements DataFetcher<CompletionStage<BookView>> {

    private final AsyncBookCatalogService catalogService;

    public AsyncBookDataFetcher(AsyncBookCatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public CompletionStage<BookView> get(DataFetchingEnvironment environment) {
        String id = environment.getArgument("id");
        return catalogService.findById(id);
    }
}
~~~

GraphQL Java chờ completion stage trước khi hoàn tất field và tiếp tục hoàn thiện response. Hãy để tầng service quản lý executor, timeout và lỗi bất đồng bộ. Không tạo thread mới cho từng field hoặc dùng CompletableFuture.supplyAsync với common pool để bọc một lời gọi blocking mà không có kế hoạch quản lý tài nguyên.

Spring for GraphQL mặc định cấu hình GraphQlSource để hỗ trợ data fetcher trả về Reactor Mono hoặc Flux: với query/mutation, các giá trị reactive được chuyển đổi để GraphQL Java xử lý theo cơ chế asynchronous; với subscription, publisher được giữ để phát các sự kiện. Nếu tự thay builder hoặc execution strategy, cần kiểm tra lại khả năng hỗ trợ reactive đã được bật.

Không trộn blocking JDBC/JPA với reactive pipeline chỉ bằng cách đổi kiểu return. Chọn đúng programming model và tránh block event-loop thread.

## 13. Kết hợp DataLoader để tránh N+1

Một custom data fetcher resolve field quan hệ bằng cách gọi repository cho từng parent có thể tạo N+1 query.

Ví dụ, client yêu cầu tác giả của nhiều sách. Nếu mỗi lần resolve Book.author đều gọi database riêng, một request có thể tạo một truy vấn lấy sách và N truy vấn lấy tác giả.

DataLoader gom các key trong cùng execution thành một batch. Data fetcher có thể lấy loader từ environment:

~~~java
import java.util.concurrent.CompletionStage;

import org.dataloader.DataLoader;
import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;

import com.example.books.application.AuthorView;
import com.example.books.application.BookView;
import org.springframework.stereotype.Component;

@Component
public class BookAuthorDataFetcher
        implements DataFetcher<CompletionStage<AuthorView>> {

    @Override
    public CompletionStage<AuthorView> get(DataFetchingEnvironment environment) {
        BookView book = environment.getSource();

        DataLoader<String, AuthorView> authorLoader =
            environment.getDataLoader("authorById");

        return authorLoader.load(book.authorId());
    }
}
~~~

DataLoader tên authorById phải được đăng ký trong DataLoaderRegistry của execution. Trong ứng dụng Spring for GraphQL, có thể tích hợp batch loader qua BatchLoaderRegistry hoặc dùng @BatchMapping cho quan hệ phù hợp.

DataLoader thường có cache theo request/execution. Không tự tạo một loader singleton dùng chung giữa các request vì có thể làm lẫn dữ liệu hoặc phạm vi cache giữa người dùng/tenant. Loader phải được tạo và đăng ký theo lifecycle mà Spring GraphQL quản lý.

Ví dụ đăng ký loader trong Spring Boot. Giả sử AuthorService.findByIds nhận tập ID và trả về Mono<Map<String, AuthorView>>:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import com.example.books.application.AuthorService;
import com.example.books.application.AuthorView;

@Configuration
public class AuthorBatchConfiguration {

    public AuthorBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, AuthorView.class)
            .withName("authorById")
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findByIds(authorIds)
            );
    }
}
~~~

BatchLoaderRegistry là bean do Spring Boot starter cung cấp. Tên đăng ký authorById phải trùng với tên mà custom data fetcher truyền vào getDataLoader.

Custom DataFetcher nên tập trung resolve field và gọi DataLoader. Logic gom batch, ánh xạ key sang kết quả và xử lý key không tồn tại thuộc batch loader.

## 14. Bảo mật và kiểm soát chi phí truy vấn

Custom data fetcher là một điểm thực thi backend, vì vậy cần áp dụng các giới hạn tương tự API thông thường:

- Kiểm tra quyền truy cập trong application service hoặc lớp security phù hợp.
- Lấy principal/tenant từ context đáng tin cậy, không tin ID do client tự khai báo.
- Giới hạn page size, số lượng item và kích thước input.
- Không đưa toàn bộ argument, token hoặc dữ liệu nhạy cảm vào log.
- Dùng DataLoader hoặc batch query cho field quan hệ có nguy cơ N+1.
- Tránh thực hiện lời gọi mạng hoặc database không cần thiết nếu field không được yêu cầu.

environment.getSelectionSet() có thể giúp kiểm tra field con mà client yêu cầu, nhưng không nên biến selection set thành cơ chế authorization. Quyền truy cập phải được kiểm tra ở server cho từng dữ liệu và operation có liên quan.

GraphQL query complexity, depth limit, timeout và rate limit là các lớp bảo vệ bổ sung. Custom DataFetcher không thay thế các giới hạn ở cấp GraphQL request.

## 15. Kiểm thử custom DataFetcher

Có thể unit test data fetcher trực tiếp bằng Mockito mà không cần khởi động GraphQL server. Ví dụ kiểm tra giới hạn tối đa được áp dụng trước khi gọi service:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.books.application.BookCatalogService;
import com.example.books.application.BookView;

import graphql.schema.DataFetchingEnvironment;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class BookSearchDataFetcherTests {

    @Mock
    BookCatalogService catalogService;

    @Mock
    DataFetchingEnvironment environment;

    @InjectMocks
    BookSearchDataFetcher dataFetcher;

    @Test
    void capsRequestedLimitAtOneHundred() {
        when(environment.<String>getArgument("term")).thenReturn("spring");
        when(environment.<Integer>getArgument("limit")).thenReturn(500);
        when(catalogService.search("spring", 100)).thenReturn(List.of());

        List<BookView> result = dataFetcher.get(environment);

        assertThat(result).isEmpty();
        verify(catalogService).search("spring", 100);
    }
}
~~~

Unit test xác minh logic của data fetcher: đọc đúng argument, áp dụng default/limit, gọi service với tham số phù hợp và trả kết quả mong đợi.

Nên bổ sung integration test dùng GraphQlTester để xác minh field đã được đăng ký đúng tọa độ trong schema, argument được GraphQL coercion đúng kiểu, response có đúng cấu trúc và nullability, exception được chuyển thành GraphQL error như mong đợi và DataLoader được gọi theo batch thay vì một lần cho từng parent.

Unit test không chứng minh RuntimeWiringConfigurer đã được Spring Boot phát hiện. Integration test mới kiểm tra được wiring từ schema đến response.

## 16. Lỗi thường gặp khi đăng ký DataFetcher

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field không chạy custom fetcher | Sai tên GraphQL type hoặc field | Đối chiếu tên trong SDL và wiring |
| Ứng dụng lỗi khi tạo schema | Đăng ký field không tồn tại hoặc schema không hợp lệ | Kiểm tra schema và runtime wiring |
| Resolver chạy nhưng nhận argument null | Sai tên argument hoặc schema cho phép null | Kiểm tra getArgument và SDL |
| Custom resolver không được gọi | Có wiring khác cho cùng field hoặc controller mapping trùng | Chỉ giữ một resolver cho mỗi tọa độ field |
| Dữ liệu request bị lẫn giữa người dùng | Lưu request state trong singleton DataFetcher | Chỉ dùng biến local/context theo execution |
| Field quan hệ tạo nhiều query | Mỗi resolver gọi repository riêng | Dùng DataLoader hoặc @BatchMapping |
| Reactive field bị block | Dùng blocking API trên event loop | Chọn reactive API hoặc executor phù hợp |
| GraphQL trả null sau lỗi | Exception handler xử lý field error | Kiểm tra error list và nullability của schema |
| Client nhìn thấy thông tin nội bộ | Trả nguyên exception message | Ánh xạ exception sang message an toàn |

## 17. Checklist trước khi đưa vào production

- Field đã tồn tại trong schema và tên type/field wiring khớp?
- Có thực sự cần custom DataFetcher hay @QueryMapping/@SchemaMapping đã đủ?
- Mỗi tọa độ GraphQL field chỉ có một cơ chế đăng ký?
- DataFetcher nhận dependency qua constructor và không giữ request state?
- Argument được kiểm tra null, default và giới hạn đầu vào?
- Authorization dựa trên principal/context đáng tin cậy?
- Field quan hệ đã xem xét N+1 và DataLoader?
- Exception được ánh xạ tập trung, không lộ chi tiết nội bộ?
- Kiểu trả về phù hợp với scalar/object/list và nullability trong schema?
- Async/reactive work dùng đúng executor hoặc reactive pipeline?
- Có unit test cho logic và integration test cho runtime wiring?
- Logging không ghi token, raw variables hoặc dữ liệu nhạy cảm?

Custom DataFetcher là API thấp hơn để gắn logic lấy dữ liệu trực tiếp vào field của GraphQL Java. Trong Spring for GraphQL, hãy dùng RuntimeWiringConfigurer để đăng ký resolver và tận dụng Spring dependency injection; dùng annotation controller cho các field thông thường. Khi triển khai, chú ý phạm vi request, nullability, exception handling, authorization, DataLoader và kiểm thử integration để bảo đảm resolver hoạt động đúng trong toàn bộ GraphQL runtime.

## Tài liệu tham khảo

- [Spring Boot — GraphQL RuntimeWiring](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Data Integration](https://docs.spring.io/spring-graphql/reference/data.html)
- [GraphQL Java — Data Fetching](https://graphql-java.com/documentation/data-fetching/)
- [GraphQL Java — DataFetcher API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetcher.html)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [GraphQL Java — DataFetcherResult API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherResult.html)
