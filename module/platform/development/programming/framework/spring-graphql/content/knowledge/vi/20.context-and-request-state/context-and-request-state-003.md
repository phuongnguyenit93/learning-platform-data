# @ContextValue trong Spring for GraphQL

`@ContextValue` liên kết một tham số của annotated controller với một thuộc tính trong **main `GraphQLContext`** của lần thực thi GraphQL hiện tại. Annotation này phù hợp để lấy metadata dùng chung trong một operation, chẳng hạn request ID, tenant đã được xác thực, locale hoặc thông tin phục vụ tracing.

`@ContextValue` không lấy argument do client truyền trong field, không tự đọc HTTP header và cũng không phải cơ chế xác thực. Dữ liệu phải được đưa vào `GraphQLContext` trước hoặc trong quá trình thực thi GraphQL, thường qua `WebGraphQlInterceptor`. Sau đó controller mới có thể lấy giá trị bằng `@ContextValue`.

## 1. GraphQLContext là gì?

GraphQL Java cung cấp `GraphQLContext` để mang dữ liệu dùng chung trong một GraphQL execution. Context có thể được đọc bởi nhiều data fetcher trong cùng operation, kể cả khi các field được resolve ở những nhánh khác nhau.

Ví dụ một request có thể cần các giá trị:

| Key trong context | Mục đích |
| --- | --- |
| `requestId` | Liên kết log và trace với request hiện tại |
| `tenantId` | Giới hạn dữ liệu theo tenant đã được xác định từ nguồn tin cậy |
| `locale` | Chọn ngôn ngữ hoặc định dạng phù hợp |
| `clientVersion` | Áp dụng tương thích theo phiên bản client |
| `featureFlags` | Chọn tính năng được bật cho execution hiện tại |

Main `GraphQLContext` có phạm vi toàn bộ query/operation. Vì vậy, đây là nơi phù hợp cho metadata có thể cần ở nhiều resolver. Context thuộc execution hiện tại, không phải một biến toàn cục dùng chung cho toàn application.

## 2. Đọc một giá trị bằng @ContextValue

Giả sử controller cần lấy request ID đã được đưa vào context:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestId(
            @ContextValue("requestId") String requestId
    ) {
        return requestId;
    }
}
~~~

`@ContextValue("requestId")` yêu cầu Spring lấy thuộc tính có key `requestId` từ main `GraphQLContext`, rồi bind giá trị vào tham số `String requestId`.

`value` là alias của `name`, vì vậy hai cách sau tương đương:

~~~java
@ContextValue("requestId") String requestId
~~~

~~~java
@ContextValue(name = "requestId") String requestId
~~~

Nếu không chỉ định tên, Spring suy luận key từ tên tham số method:

~~~java
@QueryMapping
public String requestId(@ContextValue String requestId) {
    return requestId;
}
~~~

Khi dùng cách suy luận, cần bảo đảm tên tham số được giữ trong bytecode, ví dụ bật compiler option `-parameters`. Trong code ứng dụng, chỉ định tên tường minh thường dễ đọc và ít phụ thuộc cấu hình build hơn.

## 3. Đưa dữ liệu vào GraphQLContext bằng WebGraphQlInterceptor

`@ContextValue` chỉ đọc context. Với HTTP hoặc WebSocket, `WebGraphQlInterceptor` là một nơi phù hợp để lấy metadata từ request và đưa vào `ExecutionInput` trước khi GraphQL Java thực thi operation.

Ví dụ đọc header `X-Request-Id` và lưu dưới key `requestId`:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class RequestMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String requestId = request.getHeaders().getFirst("X-Request-Id");

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(context -> {
                    if (requestId != null && !requestId.isBlank()) {
                        context.put("requestId", requestId);
                    }
                }).build()
        );

        return chain.next(request);
    }
}
~~~

Khi interceptor gọi `chain.next(request)`, request tiếp tục đến các interceptor sau và GraphQL engine. `requestId` đã nằm trong main `GraphQLContext` nên controller có thể đọc bằng `@ContextValue("requestId")`.

Kết hợp controller:

~~~java
@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestId(
            @ContextValue("requestId") String requestId
    ) {
        return requestId;
    }
}
~~~

SDL:

~~~graphql
type Query {
    requestId: String!
}
~~~

Nếu header không tồn tại, interceptor không thêm key `requestId`. Với chữ ký trên, `@ContextValue` mặc định là required nên resolver sẽ báo lỗi khi thiếu giá trị. Nếu request ID không bắt buộc, hãy dùng `required = false` hoặc `Optional` như phần tiếp theo.

## 4. Dùng HttpRequestHeaderInterceptor có sẵn

Nếu chỉ cần copy một số HTTP header vào GraphQL context, Spring for GraphQL có `HttpRequestHeaderInterceptor`. Không cần tự viết interceptor cho trường hợp đơn giản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Request-Id")
                .build();
    }
}
~~~

Sau khi header được ánh xạ vào context, controller có thể lấy giá trị theo key tương ứng:

~~~java
@QueryMapping
public String requestId(
        @ContextValue("X-Request-Id") String requestId
) {
    return requestId;
}
~~~

Interceptor có sẵn hữu ích khi key trong context có thể trùng tên header. Nếu muốn chuẩn hóa tên key, kết hợp nhiều nguồn metadata hoặc kiểm tra giá trị trước khi thêm vào context, dùng `WebGraphQlInterceptor` tùy chỉnh.

Chỉ copy những header thực sự cần cho resolver. Không đưa toàn bộ header vào context một cách mặc định vì chúng có thể chứa cookie, credential hoặc thông tin không liên quan.

## 5. Xử lý context value không bắt buộc

Theo mặc định, `@ContextValue` có `required = true`. Nếu key không có trong `GraphQLContext`, Spring ném lỗi khi bind tham số.

Khi giá trị có thể vắng mặt, có hai cách phổ biến.

**Cách 1: `required = false`**

~~~java
@QueryMapping
public String locale(
        @ContextValue(name = "locale", required = false) String locale
) {
    return locale != null ? locale : "vi";
}
~~~

Nếu key `locale` không tồn tại, tham số nhận `null`. Kiểu tham số cần cho phép null và method phải xử lý trường hợp đó.

**Cách 2: dùng `Optional<T>`**

~~~java
import java.util.Optional;

@QueryMapping
public String locale(
        @ContextValue("locale") Optional<String> locale
) {
    return locale.orElse("vi");
}
~~~

`Optional` thể hiện rõ trong chữ ký rằng context value có thể không có. Cả hai cách đều phù hợp; chọn một quy ước nhất quán trong project.

Không nên dùng `required = false` cho dữ liệu bắt buộc về bảo mật hoặc phân vùng dữ liệu rồi âm thầm chọn giá trị mặc định. Với `tenantId` hoặc metadata xác định quyền truy cập, thiếu context thường nên khiến request bị từ chối rõ ràng.

## 6. Truy cập nhiều giá trị bằng GraphQLContext

Khi method cần nhiều key hoặc cần đọc key động, có thể nhận trực tiếp `GraphQLContext`:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class RequestInfoController {

    @QueryMapping
    public RequestInfo requestInfo(GraphQLContext context) {
        String requestId = context.get("requestId");
        String tenantId = context.get("tenantId");
        String locale = context.get("locale");

        return new RequestInfo(requestId, tenantId, locale);
    }
}

public record RequestInfo(
        String requestId,
        String tenantId,
        String locale
) {}
~~~

Chọn `@ContextValue` khi method cần một hoặc vài key đã biết trước; chọn `GraphQLContext` trực tiếp khi cần một tập metadata thay đổi theo logic. Cả hai đều truy cập main context của cùng execution.

## 7. Phân biệt @ContextValue với @Argument

Hai annotation lấy dữ liệu từ hai nguồn khác nhau:

| Annotation | Nguồn dữ liệu | Ví dụ |
| --- | --- | --- |
| `@Argument("id")` | Argument khai báo trên field trong SDL và do client gửi | `book(id: "book-1")` |
| `@ContextValue("tenantId")` | Thuộc tính do server hoặc interceptor đưa vào main `GraphQLContext` | Tenant được xác định từ thông tin xác thực |
| `@LocalContextValue("permission")` | Thuộc tính trong local GraphQL context được truyền từ resolver cha | Metadata chỉ dành cho một nhánh dữ liệu con |

Ví dụ kết hợp argument với context:

~~~java
@QueryMapping
public Book book(
        @Argument("id") Long id,
        @ContextValue("tenantId") String tenantId
) {
    return bookService.findByTenantAndId(tenantId, id);
}
~~~

Client quyết định `id` thông qua GraphQL argument. Server xác định `tenantId` từ context đã được thiết lập sau khi xác thực. Resolver kết hợp cả hai khi truy vấn dữ liệu.

Không chuyển `tenantId` thành argument chỉ để client tự gửi nếu tenant phải được ràng buộc theo danh tính đã xác thực. Client có thể thay đổi argument; context nên được tạo từ nguồn server tin cậy.

## 8. Phân biệt main context và local context

Spring for GraphQL hỗ trợ hai loại context:

- **Main `GraphQLContext`:** dùng chung trong toàn bộ GraphQL execution. `@ContextValue` và tham số `GraphQLContext` truy cập context này.
- **Local `GraphQLContext`:** được truyền từ một data fetcher đến các data fetcher con trong một phần của cây kết quả. `@LocalContextValue` dùng để đọc giá trị này.

Ví dụ, resolver cha trả về `DataFetcherResult` có local context:

~~~java
import graphql.execution.DataFetcherResult;
import java.util.Map;

@QueryMapping
public DataFetcherResult<Book> book(@Argument("id") Long id) {
    Book book = bookService.findById(id);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(Map.of("includeInternalNotes", false))
            .build();
}
~~~

Resolver field con có thể đọc giá trị đó:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @LocalContextValue("includeInternalNotes") Boolean includeInternalNotes
) {
    if (!Boolean.TRUE.equals(includeInternalNotes)) {
        return null;
    }
    return bookService.findInternalNotes(book.id());
}
~~~

Ví dụ minh họa phạm vi truyền local context xuống nhánh con. Với dữ liệu cần dùng ở nhiều nhánh hoặc nhiều field không cùng quan hệ cha-con, main `GraphQLContext` phù hợp hơn. Không dùng local context như một biến toàn cục thay thế `@ContextValue`.

## 9. Dùng @ContextValue trong @SchemaMapping và @BatchMapping

`@ContextValue` có thể được dùng trong các annotated controller handler, không chỉ root query. Ví dụ resolver của field `Book.author` cần locale:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(
            Book book,
            @ContextValue("locale") String locale
    ) {
        return authorService.findLocalized(book.authorId(), locale);
    }
}
~~~

`@BatchMapping` cũng có thể nhận `@ContextValue` hoặc `GraphQLContext`. Context được truyền tới batch loader từ cùng `DataFetchingEnvironment` của GraphQL execution. Điều này hữu ích khi batch query cần tenant hoặc locale đã được xác định trước.

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> authors(
        List<Book> books,
        @ContextValue("tenantId") String tenantId
) {
    Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

    return authorService.findByTenantAndIds(tenantId, authorIds)
            .map(authorsById -> books.stream()
                    .filter(book -> authorsById.containsKey(book.authorId()))
                    .collect(Collectors.toMap(
                            book -> book,
                            book -> authorsById.get(book.authorId())
                    )));
}
~~~

Service nhận tenant như tham số và áp dụng tenant trong truy vấn. Không lưu tenant hiện tại vào field của singleton service vì nhiều GraphQL execution có thể chạy đồng thời.

## 10. @ContextValue không phải cơ chế xác thực

Context có thể chứa thông tin liên quan bảo mật, nhưng bản thân `@ContextValue` chỉ bind một giá trị. Nó không xác thực nguồn gốc, không kiểm tra chữ ký token và không cấp quyền truy cập.

Với danh tính người dùng, ưu tiên lấy `Principal` hoặc `@AuthenticationPrincipal` từ Spring Security context khi tích hợp Spring Security. Nếu cần đặt các claim hoặc metadata đã được xác minh vào GraphQLContext, hãy thực hiện việc đó sau bước xác thực và kiểm tra quyền ở security layer hoặc service.

Một số nguyên tắc:

1. Không tin `tenantId`, `userId`, role hoặc permission do client gửi trong GraphQL argument hay header chưa được xác minh.
2. Lấy danh tính và tenant từ principal hoặc token đã được xác thực.
3. Chỉ đưa các giá trị đã được xác minh vào `GraphQLContext`.
4. Resolver/service vẫn phải áp dụng authorization khi đọc hoặc cập nhật dữ liệu.
5. Không dùng cache hit hoặc sự hiện diện của context key làm bằng chứng quyền truy cập.

Ví dụ, header `X-Tenant-Id` có thể bị client giả mạo nếu hệ thống không xác minh nó. Nếu tenant gắn với tài khoản đăng nhập, hãy xác định tenant từ `Authentication` hoặc kiểm tra header với danh sách tenant mà principal được phép truy cập trước khi đưa vào context.

## 11. Context theo request và ThreadLocal

`GraphQLContext` được truyền qua GraphQL execution và có thể được đọc bởi data fetcher trên thread thực thi tương ứng. Nó không phải `ThreadLocal` và không phụ thuộc việc resolver chạy trên cùng thread với HTTP handler.

Không nên dùng một biến `static ThreadLocal` để thay thế `GraphQLContext`. Khi GraphQL execution chạy bất đồng bộ, các resolver có thể được thực thi trên thread khác; dữ liệu trong ThreadLocal không tự động đi theo execution nếu không có cơ chế context propagation riêng.

Với Spring MVC và WebFlux, Spring for GraphQL có cơ chế context propagation cho các trường hợp được hỗ trợ. Tuy nhiên, khi dữ liệu là metadata của GraphQL operation, truyền qua `GraphQLContext` vẫn là cách trực tiếp và rõ ràng nhất. Với Reactor-specific context, cần phân biệt nó với main GraphQLContext và chủ động bridge qua interceptor nếu ứng dụng yêu cầu.

## 12. Không dùng GraphQLContext làm nơi chứa mutable global state

Main context có thể được nhiều resolver đọc trong cùng execution. Một số API cho phép cập nhật context, nhưng không nên dùng nó như một vùng nhớ tùy ý để các resolver song song ghi đè trạng thái của nhau.

Nên:

- Đưa metadata cần thiết vào context trước khi GraphQL engine thực thi, thường trong interceptor.
- Xem context như dữ liệu đầu vào đã được chuẩn bị cho operation.
- Dùng key có tên rõ ràng và kiểu giá trị nhất quán.
- Chỉ lưu dữ liệu nhỏ, có ý nghĩa trong suốt một execution.
- Không lưu DataLoader, request body lớn, entity graph hoặc mutable collection dùng chung vào context nếu không có lý do rõ ràng.
- Không giữ tham chiếu đến context trong singleton service hoặc static field sau khi request hoàn tất.

Nếu resolver cần tạo dữ liệu chỉ dành cho các field con, hãy cân nhắc `DataFetcherResult.localContext` và `@LocalContextValue` thay vì sửa main context.

## 13. Kiểm thử @ContextValue bằng WebGraphQlTester

Vì giá trị thường được đưa vào context bởi `WebGraphQlInterceptor`, nên kiểm thử qua `WebGraphQlHandler` giúp xác nhận cả interceptor lẫn controller. `WebGraphQlTester` gửi mock web request qua interceptor chain trước khi GraphQL execution diễn ra.

Controller dùng request ID:

~~~java
@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestId(
            @ContextValue("requestId") String requestId
    ) {
        return requestId;
    }
}
~~~

SDL:

~~~graphql
type Query {
    requestId: String!
}
~~~

Integration test với `WebGraphQlTester`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

@SpringBootTest
class ContextValueTests {

    @Autowired
    WebGraphQlHandler handler;

    @Test
    void readsRequestIdFromHttpHeader() {
        WebGraphQlTester tester = WebGraphQlTester.builder(handler)
                .headers(headers -> headers.set("X-Request-Id", "req-test-123"))
                .build();

        tester.document("{ requestId }")
                .execute()
                .path("requestId")
                .entity(String.class)
                .isEqualTo("req-test-123");
    }
}
~~~

Test giả định `RequestMetadataInterceptor` là bean và `WebGraphQlHandler` được Spring Boot cấu hình. Header được thêm vào mock request, interceptor copy nó vào context, rồi controller đọc giá trị bằng `@ContextValue`.

Nên bổ sung test cho các trường hợp:

1. Context key tồn tại và được bind đúng kiểu.
2. Key bắt buộc bị thiếu thì request trả lỗi GraphQL phù hợp.
3. Key tùy chọn bị thiếu thì controller nhận `null` hoặc `Optional.empty()`.
4. Hai request với request ID hoặc tenant khác nhau không nhìn thấy context của nhau.
5. Giá trị tenant được xác định từ principal đã xác thực, không lấy trực tiếp từ header không tin cậy.
6. `@LocalContextValue` chỉ nhận giá trị được truyền từ resolver cha.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@ContextValue` báo thiếu giá trị | Context key chưa được thêm hoặc tên key không khớp | Kiểm tra interceptor và dùng tên tường minh |
| Giá trị luôn là `null` | Interceptor không chạy, header không có hoặc context được ghi bằng key khác | Kiểm tra thứ tự interceptor và `configureExecutionInput` |
| `@ContextValue` không lấy được HTTP header | Annotation chỉ đọc GraphQLContext, không đọc transport trực tiếp | Copy header vào context bằng interceptor |
| Tham số nhận sai kiểu | Giá trị đưa vào context khác kiểu Java được khai báo | Chuẩn hóa kiểu tại nơi tạo context hoặc dùng kiểu tương ứng |
| Key bị suy luận sai | Tên tham số không được giữ hoặc không trùng context key | Khai báo `@ContextValue("key")` rõ ràng |
| Lỗi khi key không bắt buộc | `required` mặc định là `true` | Dùng `required = false` hoặc `Optional<T>` |
| Dùng `@ContextValue` nhưng dữ liệu chỉ cần trong nhánh con | Chọn sai phạm vi context | Dùng `@LocalContextValue` và `DataFetcherResult.localContext` |
| Tenant bị lộ giữa request | Lưu tenant trong singleton/static mutable state | Dùng context theo execution và truyền tenant qua tham số service |
| Dữ liệu vẫn truy cập được dù context thiếu | Resolver dùng giá trị mặc định không an toàn | Fail closed và thực hiện authorization tại service/security layer |

## 15. Quy trình sử dụng @ContextValue

Khi một resolver cần metadata của request:

1. Xác định giá trị có thực sự dùng chung trong toàn operation hay chỉ thuộc một nhánh con.
2. Với metadata toàn operation, chọn main `GraphQLContext` và `@ContextValue`.
3. Đưa giá trị vào context từ interceptor hoặc cấu hình execution trước khi resolver chạy.
4. Chỉ copy các header cần thiết; xác minh nguồn gốc trước khi dùng dữ liệu liên quan tenant hoặc quyền.
5. Dùng tên key tường minh trong `@ContextValue`; chọn `required = false` hoặc `Optional` cho dữ liệu tùy chọn.
6. Dùng `GraphQLContext` trực tiếp khi cần nhiều key hoặc truy cập động.
7. Dùng `@LocalContextValue` cho metadata được truyền từ resolver cha xuống một nhánh con.
8. Không lưu request state vào static field hoặc singleton mutable state.
9. Kiểm thử interceptor và controller qua `WebGraphQlTester`, đồng thời kiểm tra cách ly giữa các request.

`@ContextValue` giúp annotated controller nhận metadata của GraphQL execution qua một tham số có tên rõ ràng. Khi kết hợp đúng với `WebGraphQlInterceptor`, `GraphQLContext` và cơ chế bảo mật của ứng dụng, resolver có thể dùng chung request metadata mà không phụ thuộc vào global state hoặc ThreadLocal.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — ContextValue API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/ContextValue.html)
- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Testing and WebGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
