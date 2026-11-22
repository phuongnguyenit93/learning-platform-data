# Giới hạn kích thước query

GraphQL cho phép client chọn nhiều field và lồng nhiều cấp trong cùng một operation. Tính linh hoạt này có thể tạo ra request rất lớn hoặc tốn nhiều tài nguyên: document dài, selection set quá sâu, nhiều nhánh, truy vấn list lồng nhau với page size lớn, hoặc variables chứa payload khổng lồ.

Trong Spring for GraphQL, GraphQL Java thực hiện parse, validate và execute operation. Vì vậy, giới hạn kích thước query cần được áp dụng ở nhiều lớp: giới hạn HTTP request body, giới hạn parser, giới hạn độ sâu và độ phức tạp của operation, cùng với pagination và rate limit. Một giới hạn đơn lẻ không kiểm soát được tất cả kiểu tải.

Bài học này trình bày cách đặt các giới hạn đó, cách cấu hình `ParserOptions` và `Instrumentation` với Spring Boot, cách kiểm thử query vượt giới hạn và các lỗi thường gặp khi triển khai.

## 1. Vì sao cần giới hạn kích thước query?

Một query nhỏ về số ký tự vẫn có thể yêu cầu lượng dữ liệu lớn:

~~~graphql
query {
    customers(first: 100) {
        orders(first: 100) {
            items(first: 100) {
                product {
                    reviews(first: 100) {
                        author {
                            name
                        }
                    }
                }
            }
        }
    }
}
~~~

Nếu mỗi cấp trả tối đa 100 phần tử, số nhánh dữ liệu tiềm năng tăng rất nhanh. Chỉ bốn cấp list đã có thể tạo ra lượng công việc lớn, dù document không dài.

Một query khác có thể chứa hàng nghìn alias hoặc field:

~~~graphql
query {
    a1: customer(id: "1") { id }
    a2: customer(id: "2") { id }
    a3: customer(id: "3") { id }
    a4: customer(id: "4") { id }
}
~~~

Các trường hợp này có thể làm tăng thời gian đọc request body và parse document, bộ nhớ dùng để tạo AST, thời gian validate và tính toán query, số lần gọi DataFetcher, kích thước response và chi phí serialize.

Giới hạn query là một phần của bảo vệ tài nguyên server và giữ độ trễ ổn định khi nhiều client gửi request đồng thời.

## 2. Bốn lớp giới hạn cần phân biệt

| Lớp | Kiểm soát điều gì? | Cơ chế thường dùng |
| --- | --- | --- |
| HTTP request body | Tổng kích thước payload truyền qua mạng, gồm query, variables và metadata | Reverse proxy, gateway, HTTP server hoặc request decoder |
| Parser | Độ dài document, số token, whitespace token và độ sâu grammar | GraphQL Java `ParserOptions` |
| Query shape | Độ sâu selection set, số field và cấu trúc operation | `MaxQueryDepthInstrumentation`, `MaxQueryComplexityInstrumentation` |
| Runtime/data access | Số bản ghi, thời gian xử lý, số request và mức tiêu thụ dependency | Pagination, timeout, rate limit, DataLoader và giới hạn nghiệp vụ |

Các lớp này bổ trợ cho nhau:

- `ParserOptions` giới hạn document GraphQL được parse; nó không giới hạn tổng JSON body.
- HTTP body limit bảo vệ payload đầu vào; nó không biết query có selection set sâu hay tốn kém hay không.
- Depth limit ngăn query lồng quá nhiều cấp; nó không ngăn query có hàng nghìn field cùng cấp.
- Complexity limit ước lượng chi phí operation; nó không thay thế giới hạn số bản ghi thực tế trong database.

Nên kết hợp các lớp theo rủi ro và năng lực của ứng dụng.

## 3. Giới hạn mặc định của GraphQL Java ParserOptions

`ParserOptions` là cấu hình của GraphQL Java parser. Các giới hạn mặc định phổ biến trong GraphQL Java gồm:

| Giới hạn | Giá trị mặc định | Mục đích |
| --- | ---: | --- |
| `maxCharacters` | 1.048.576 ký tự | Ngăn document có chuỗi ký tự quá dài |
| `maxTokens` | 15.000 token | Hạn chế số token cú pháp |
| `maxWhitespaceTokens` | 200.000 token | Hạn chế document chứa quá nhiều khoảng trắng |
| `maxRuleDepth` | 500 cấp | Ngăn grammar lồng quá sâu khi parse |

Đây là giới hạn parser, không phải giới hạn byte của HTTP request. Một JSON body có thể lớn do variables dù document GraphQL ngắn; ngược lại, document dài có thể vượt giới hạn parser dù body vẫn nằm trong mức gateway cho phép.

Các giá trị mặc định thuộc phiên bản GraphQL Java mà ứng dụng đang dùng. Hãy kiểm tra dependency version thực tế trước khi dựa vào con số cố định, nhất là khi Spring Boot quản lý phiên bản GraphQL Java.

`maxRuleDepth` là độ sâu của grammar khi parser đọc document. Nó không thay thế giới hạn selection depth của operation; phần đó được kiểm soát bằng instrumentation ở bước phân tích query.

## 4. Tùy chỉnh giới hạn parser cho operation

GraphQL Java cho phép tạo `ParserOptions` với các giới hạn riêng. Với request operation, dùng `setDefaultOperationParserOptions(...)` để thiết lập parser options mặc định trước khi server nhận request.

Ví dụ cấu hình giới hạn thấp hơn mức mặc định:

~~~java
import graphql.parser.ParserOptions;

public final class GraphQlParserLimits {

    private GraphQlParserLimits() {
    }

    public static void configure() {
        ParserOptions operationOptions = ParserOptions.newParserOptions()
                .maxCharacters(256 * 1024)
                .maxTokens(8_000)
                .maxWhitespaceTokens(50_000)
                .maxRuleDepth(200)
                .build();

        ParserOptions.setDefaultOperationParserOptions(operationOptions);
    }
}
~~~

Gọi cấu hình này một lần khi ứng dụng khởi động, trước khi xử lý GraphQL operation:

~~~java
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        GraphQlParserLimits.configure();
        SpringApplication.run(Application.class, args);
    }
}
~~~

`ParserOptions.setDefaultOperationParserOptions(...)` thay đổi cấu hình mặc định ở phạm vi JVM. Nếu cùng JVM chạy nhiều GraphQL application context, chúng cùng chịu cấu hình này. Hãy chọn giá trị phù hợp với tất cả ứng dụng trong process và không thay đổi cấu hình giữa các request.

Không tăng các giới hạn parser một cách tùy tiện. Nếu một client hợp lệ thực sự cần document lớn, hãy đo kích thước, số token và thời gian parse trước khi điều chỉnh.

## 5. Giới hạn HTTP request body riêng với parser

HTTP GraphQL request thường có payload JSON tương tự:

~~~json
{
    "query": "query Search($filter: SearchFilter!) { search(filter: $filter) { id } }",
    "operationName": "Search",
    "variables": {
        "filter": {
            "keywords": ["spring", "graphql"],
            "metadata": {
                "source": "web"
            }
        }
    }
}
~~~

Parser chỉ xử lý giá trị `query`. HTTP body còn có `operationName`, `variables` và có thể có `extensions`. Vì vậy, nếu chỉ cấu hình `ParserOptions`, client vẫn có thể gửi variables JSON rất lớn.

Đặt giới hạn body ở reverse proxy, API gateway hoặc HTTP server phù hợp với hạ tầng triển khai. Gateway có thể từ chối payload vượt quá giới hạn byte trước khi chuyển tiếp đến ứng dụng.

Khi chọn body limit, cần tính đến query document, variables, metadata, encoding thực tế của JSON (thường là UTF-8) và các endpoint khác dùng chung HTTP server hoặc gateway.

Không nhầm giới hạn body với `maxCharacters`: body limit thường tính byte, trong khi parser giới hạn ký tự của GraphQL document. Hai con số không thể thay thế trực tiếp cho nhau.

## 6. Giới hạn độ sâu bằng MaxQueryDepthInstrumentation

Query depth là số cấp lồng nhau trong selection set. Ví dụ:

~~~graphql
query {
    book {
        author {
            organization {
                address {
                    city
                }
            }
        }
    }
}
~~~

Độ sâu lớn làm tăng số tầng field cần resolve và có thể dẫn đến nhiều lần truy cập dữ liệu lồng nhau.

GraphQL Java cung cấp `MaxQueryDepthInstrumentation`. Nếu depth của operation vượt quá ngưỡng, instrumentation từ chối thực thi operation.

Với Spring Boot, có thể đăng ký instrumentation bean:

~~~java
import graphql.execution.instrumentation.Instrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlQueryLimitConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(12);
    }
}
~~~

Spring Boot tự phát hiện bean `Instrumentation` khi tạo `GraphQlSource`. Giá trị `12` chỉ là ví dụ; hãy chọn ngưỡng dựa trên schema, query hợp lệ của client và dữ liệu quan sát được.

Depth limit chỉ kiểm soát chiều sâu. Một operation có thể có depth thấp nhưng hàng trăm hoặc hàng nghìn field cùng cấp, nên vẫn cần giới hạn complexity.

## 7. Giới hạn độ phức tạp bằng MaxQueryComplexityInstrumentation

Query complexity là điểm ước lượng chi phí của operation dựa trên các field được chọn và cấu trúc con của chúng.

GraphQL Java cung cấp `MaxQueryComplexityInstrumentation`. Mặc định, calculator cộng chi phí của field với tổng complexity của các field con theo công thức `1 + childComplexity`.

Ví dụ đăng ký giới hạn complexity:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

@Bean
Instrumentation maxQueryComplexityInstrumentation() {
    return new MaxQueryComplexityInstrumentation(500);
}
~~~

Nếu complexity vượt quá ngưỡng, operation bị từ chối trước khi DataFetcher chạy.

Giới hạn complexity có thể chặn query rộng với nhiều field, kể cả khi query không sâu. Tuy nhiên, cách tính mặc định không tự hiểu chi phí của một list có `first: 1000` so với `first: 10`. Với API có pagination, nên định nghĩa `FieldComplexityCalculator` riêng để đưa kích thước page vào phép tính.

## 8. Tính complexity dựa trên pagination argument

Một query có thể lồng nhiều collection:

~~~graphql
query {
    books(first: 50) {
        reviews(first: 20) {
            author {
                name
            }
        }
    }
}
~~~

Nếu calculator chỉ cộng một điểm cho mỗi field, hai query có cùng cấu trúc nhưng page size rất khác nhau có thể có cùng complexity. Điều đó không phản ánh chi phí thực tế.

`FieldComplexityCalculator` nhận `FieldComplexityEnvironment` và `childComplexity`. Từ environment có thể đọc field definition và arguments đã được resolve, gồm giá trị được truyền qua variables.

Ví dụ minh họa calculator tính chi phí cho hai collection `books` và `reviews`:

~~~java
import graphql.analysis.FieldComplexityCalculator;
import org.springframework.context.annotation.Bean;

@Bean
FieldComplexityCalculator paginationAwareCalculator() {
    return
        (environment, childComplexity) -> {
            if (environment.getFieldDefinition() == null) {
                return 1 + childComplexity;
            }

            String fieldName =
                    environment.getFieldDefinition().getName();

            if ("books".equals(fieldName) || "reviews".equals(fieldName)) {
                Object first = environment.getArguments().get("first");

                int pageSize = first instanceof Number number
                        ? Math.min(Math.max(number.intValue(), 1), 100)
                        : 20;

                return 1 + pageSize * childComplexity;
            }

            return 1 + childComplexity;
        };
}
~~~

Ở ví dụ này, page size được chặn ở 100 và dùng 20 làm mặc định khi client không truyền `first`. Các con số phải đồng bộ với giới hạn pagination thật của resolver.

Đây là mô hình tính điểm minh họa. Trong ứng dụng thật, cần tính đến nhiều collection field, các argument như `last`, `limit`, nested connection, field gọi service đắt tiền và default value trong schema.

## 9. Kết hợp depth và complexity instrumentation

Một ứng dụng có thể dùng cả hai instrumentation. Spring Boot nhận bean `Instrumentation` và GraphQL Java có `ChainedInstrumentation` để chạy nhiều instrumentation trong cùng execution.

Ví dụ:

~~~java
import java.util.List;

import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.ChainedInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;

@Bean
Instrumentation queryLimitsInstrumentation(
        FieldComplexityCalculator paginationAwareCalculator) {
    return new ChainedInstrumentation(List.of(
            new MaxQueryDepthInstrumentation(12),
            new MaxQueryComplexityInstrumentation(
                    10_000,
                    paginationAwareCalculator
            )
    ));
}
~~~

Kết hợp các giới hạn có ý nghĩa:

- Parser giới hạn kích thước document và chi phí parse.
- Depth instrumentation giới hạn số cấp lồng nhau.
- Complexity instrumentation giới hạn tổng chi phí ước lượng.
- Pagination giới hạn số phần tử resolver có thể trả về.

Nếu ứng dụng đã có instrumentation cho metrics, tracing hoặc DataLoader, hãy kiểm tra cách Spring Boot kết hợp các instrumentation bean để tất cả cùng hoạt động. Tránh tự thay thế instrumentation hiện có khi chỉ muốn thêm một giới hạn query.

Ví dụ chain ở phần này là cấu hình thay thế nếu muốn gom depth và complexity vào một bean. Khi dùng chain, bỏ bean depth/complexity riêng ở các ví dụ trước để tránh đăng ký cùng một giới hạn hai lần.

## 10. Pagination là giới hạn dữ liệu, không phải chỉ là tiện ích API

Ngay cả khi query vượt qua parser, depth và complexity, resolver vẫn có thể tải quá nhiều dữ liệu nếu không giới hạn collection.

Ví dụ schema có pagination:

~~~graphql
type Query {
    books(first: Int = 20, after: String): BookConnection!
}
~~~

Resolver cần áp dụng giới hạn tối đa ở phía server:

~~~java
@QueryMapping
public BookConnection books(
        @Argument Integer first,
        @Argument String after) {

    int pageSize = first == null ? 20 : Math.min(Math.max(first, 1), 100);

    return bookService.findBooks(pageSize, after);
}
~~~

Không chỉ dựa vào client để truyền page size nhỏ. Client có thể gửi `first: 100000`; server phải clamp hoặc từ chối theo hợp đồng API.

Với query có nhiều collection lồng nhau, mỗi collection cần có giới hạn phù hợp. Tổng số item tiềm năng có thể tăng theo tích của các page size ở nhiều cấp.

## 11. Alias, fragment và field lặp có thể làm query rộng

Query có thể dùng alias để yêu cầu cùng một field nhiều lần với argument khác nhau:

~~~graphql
query {
    recent: books(first: 20, sort: NEWEST) {
        id
    }
    popular: books(first: 20, sort: POPULAR) {
        id
    }
}
~~~

Một document có thể chứa nhiều alias như vậy. Mỗi nhánh có thể tạo công việc riêng cho resolver.

Fragments giúp tái sử dụng selection set:

~~~graphql
fragment BookDetails on Book {
    id
    title
    author {
        name
    }
}

query {
    books(first: 20) {
        ...BookDetails
    }
}
~~~

Khi đánh giá query, không chỉ đếm số dòng hoặc số field nhìn thấy trực tiếp. Fragment spread và inline fragment cũng đóng góp vào operation sau khi được mở rộng.

Query complexity instrumentation của GraphQL Java phân tích operation và selection set, vì vậy phù hợp hơn việc đếm chuỗi thủ công. Nếu tự viết analyzer, cần xử lý fragments, aliases, directives và biến thể operation đúng theo GraphQL semantics.

## 12. Kiểm soát introspection và các field đặc biệt

Introspection cho phép client khám phá schema qua `__schema` và `__type`. Một số ứng dụng công khai cần introspection để hỗ trợ GraphQL IDE, code generation hoặc tooling; một số môi trường production có thể muốn hạn chế nó.

Tuy nhiên, tắt introspection không thay thế query size limit. Client vẫn có thể gửi query nghiệp vụ rất lớn.

Nếu bật introspection, hãy tính đến việc các query introspection cũng có thể lớn. GraphQL Java có các giới hạn riêng cho good-faith introspection trong một số phiên bản, nhưng vẫn nên kiểm tra hành vi và cấu hình theo phiên bản đang dùng.

Các field đặc biệt như `__typename` cũng cần được tính đúng khi đánh giá query. Không nên tự loại mọi field bắt đầu bằng `__` khỏi bộ đếm mà không hiểu semantics của chúng.

## 13. Persisted queries và operation allowlist

Persisted query cho phép client gửi một định danh hoặc hash của document đã đăng ký thay vì gửi toàn bộ query text mỗi lần.

Lợi ích:

- Giảm kích thước document truyền qua mạng.
- Giảm chi phí parse và validation khi có thể tái sử dụng parsed document.
- Dễ quản lý danh sách operation đã được client phát hành.
- Có thể hỗ trợ chính sách chỉ cho phép operation đã đăng ký.

Spring for GraphQL hỗ trợ cấu hình `PreparsedDocumentProvider` qua `GraphQlSource.Builder#configureGraphQl(...)`. GraphQL Java cũng có hỗ trợ persisted query.

Cần phân biệt hai cơ chế:

- **Document cache:** cache kết quả parse/validation để tránh lặp công việc; client vẫn có thể gửi query text mới.
- **Persisted query allowlist:** chỉ chấp nhận hash/document đã được đăng ký; query không nằm trong danh sách bị từ chối.

Persisted query không tự động trở thành allowlist nếu server vẫn cho phép client gửi document tùy ý. Nó cũng không thay thế giới hạn complexity, pagination hay runtime timeout.

## 14. Cache parse và validation không thay thế giới hạn thực thi

GraphQL Java phải parse và validate operation trước khi execute. `PreparsedDocumentProvider` có thể cache document đã parse/validate để tái sử dụng.

Cơ chế này giảm chi phí lặp lại khi cùng operation được gọi nhiều lần, nhưng không làm giảm chi phí fetch dữ liệu của mỗi request.

Một operation đã cache vẫn có thể truy vấn hàng nghìn bản ghi nếu resolver cho phép. Vì vậy, nên kết hợp:

- Preparsed document cache cho operation lặp lại.
- Parser limits cho document đầu vào.
- Depth/complexity instrumentation cho cấu trúc operation.
- Pagination và giới hạn dữ liệu cho resolver.
- Timeout và rate limit cho runtime.

Cache là tối ưu hiệu năng cho request hợp lệ, không phải hàng rào bảo vệ đầy đủ.

## 15. Rate limit và timeout theo người dùng

Giới hạn query áp dụng cho từng operation, nhưng một client có thể gửi hàng trăm operation hợp lệ liên tiếp. Do đó, hệ thống cần rate limit ở tầng gateway hoặc application.

Có thể đặt chính sách dựa trên user ID hoặc API key đã xác thực, tenant, IP address khi chưa có danh tính đáng tin cậy, operation type hoặc mức tiêu thụ tài nguyên/complexity score.

Timeout server cũng giúp giải phóng request mất quá nhiều thời gian. Spring for GraphQL cung cấp `TimeoutWebGraphQlInterceptor` cho web transport. Tuy nhiên, timeout không thay thế parser, complexity hay pagination: server vẫn có thể tiêu tốn đáng kể CPU trước khi timeout xảy ra.

Rate limit, timeout và query complexity cần được phối hợp để kiểm soát cả một request lẫn tần suất request.

## 16. Kiểm thử query vượt giới hạn parser

Sau khi cấu hình parser options, cần xác minh operation quá dài bị từ chối trước khi resolver thực thi.

Ví dụ tạo document vượt giới hạn ký tự trong test:

~~~java
@Test
void rejectsDocumentAboveCharacterLimit() {
    String longFieldName = "x".repeat(300_000);
    String document = "query { " + longFieldName + " }";

    graphQlTester.document(document)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

Ví dụ trên giả định parser được cấu hình giới hạn thấp hơn 300.000 ký tự. Test kiểm tra request-level error xuất hiện; nó không phụ thuộc vào nguyên văn message parser.

Có thể tạo thêm test riêng cho token limit, whitespace limit và parser rule depth. Các test này giúp xác nhận từng giới hạn đang được áp dụng đúng.

## 17. Kiểm thử depth và complexity instrumentation

Với depth limit, tạo một query có selection set sâu hơn ngưỡng:

~~~java
@Test
void rejectsQueryAboveMaximumDepth() {
    graphQlTester.document("""
            query {
                category {
                    children {
                        children {
                            children {
                                id
                            }
                        }
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

Với complexity, tạo query có collection argument vượt ngân sách:

~~~java
@Test
void rejectsQueryAboveMaximumComplexity() {
    graphQlTester.document("""
            query {
                books(first: 100) {
                    reviews(first: 100) {
                        id
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

Các test này cần dùng schema có field tương ứng và instrumentation thật được cấu hình trong test context. Nếu query lỗi do schema validation hoặc field không tồn tại, test vẫn thấy `errors`; vì vậy hãy bảo đảm query hợp lệ trước khi dùng nó để kiểm tra depth hoặc complexity.

Nên có thêm test query nằm dưới ngưỡng để bảo đảm instrumentation không chặn nhầm operation hợp lệ.

## 18. Lỗi thường gặp khi giới hạn query

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query dài vẫn đi vào parser | Chỉ đặt HTTP body limit, chưa cấu hình `ParserOptions` | Thiết lập parser operation options |
| Variables lớn vẫn được chấp nhận | `maxCharacters` chỉ giới hạn document GraphQL | Đặt HTTP body limit và giới hạn input riêng |
| Query rất sâu vẫn chạy | Chưa đăng ký `MaxQueryDepthInstrumentation` | Thêm instrumentation bean và kiểm thử |
| Query nhiều field cùng cấp vẫn chạy | Chỉ có depth limit | Bổ sung complexity limit |
| Query list lồng nhau tốn nhiều tài nguyên | Complexity mặc định không nhân theo page size | Dùng calculator có tính pagination argument |
| Query bị từ chối dù hợp lệ | Ngưỡng quá thấp hoặc complexity calculator đánh giá quá cao | Đo query thực tế và hiệu chỉnh ngưỡng |
| Tăng parser limit nhưng vẫn bị từ chối | Gateway hoặc HTTP server giới hạn body trước parser | Kiểm tra body limit tại ingress và transport |
| Persisted query vẫn nhận document tùy ý | Chỉ dùng cache, chưa bật allowlist | Từ chối document/hash chưa đăng ký |
| Cache làm request vẫn chậm | Parse đã cache nhưng DataFetcher vẫn tốn tài nguyên | Kiểm tra resolver, pagination, DataLoader và database |
| Query nhỏ nhưng response quá lớn | Page size hoặc field collection không có giới hạn | Clamp pagination ở server |
| Test giới hạn pass vì query sai schema | Query không hợp lệ từ trước | Xác minh query baseline hợp lệ rồi mới kiểm tra limit |

## 19. Quy trình thiết lập query limits

Khi đưa giới hạn vào một Spring for GraphQL server, có thể triển khai theo trình tự:

1. Đo document hợp lệ lớn nhất mà client thực sự cần.
2. Đặt HTTP request body limit ở gateway hoặc server, tính cả variables.
3. Cấu hình `ParserOptions` cho operation: characters, tokens, whitespace tokens và rule depth.
4. Đăng ký `MaxQueryDepthInstrumentation`.
5. Đăng ký `MaxQueryComplexityInstrumentation`.
6. Với collection field, tính complexity dựa trên page size và chi phí truy vấn thực tế.
7. Đặt giới hạn pagination ở resolver/service, không chỉ dựa vào client.
8. Cân nhắc persisted query allowlist nếu API có tập operation ổn định.
9. Bổ sung rate limit và timeout theo user/tenant.
10. Kiểm thử query dưới ngưỡng, query vượt từng ngưỡng và variables/body quá lớn.
11. Theo dõi tỷ lệ request bị từ chối, query complexity, thời gian parse/execute và kích thước response.
12. Điều chỉnh ngưỡng dựa trên dữ liệu production và nhu cầu client hợp lệ.

Không áp dụng một con số chung cho mọi hệ thống. Query limits cần phản ánh schema, số lượng dữ liệu, năng lực database, timeout mục tiêu và loại client đang sử dụng.

## 20. Những điểm cần ghi nhớ

- Kích thước query có nhiều khía cạnh: HTTP body, document characters, token count, parser depth, selection depth và execution complexity.
- `ParserOptions` kiểm soát document trước khi GraphQL Java thực thi operation.
- `setDefaultOperationParserOptions(...)` thiết lập parser options cho operation ở phạm vi JVM.
- `MaxQueryDepthInstrumentation` giới hạn số cấp selection set.
- `MaxQueryComplexityInstrumentation` giới hạn điểm chi phí ước lượng của operation.
- Complexity cần tính đến page size của collection để phản ánh tải dữ liệu.
- Pagination phải được clamp ở server.
- Persisted query cache giảm chi phí parse; allowlist mới giới hạn operation được phép.
- HTTP body limit cần tính cả variables, không chỉ query text.
- Rate limit và timeout bảo vệ hệ thống trước nhiều request hợp lệ liên tiếp.

Giới hạn kích thước query giúp Spring for GraphQL xử lý request có kiểm soát hơn. Khi kết hợp giới hạn parser, depth, complexity, request body và pagination, server có thể từ chối sớm operation quá lớn, đồng thời giữ những query hợp lệ ở mức tài nguyên phù hợp.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphqlsource)
- [GraphQL Java — ParserOptions API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/parser/ParserOptions.html)
- [GraphQL Java — ParserOptions.Builder API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/parser/ParserOptions.Builder.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [GraphQL Java — FieldComplexityCalculator API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/FieldComplexityCalculator.html)
