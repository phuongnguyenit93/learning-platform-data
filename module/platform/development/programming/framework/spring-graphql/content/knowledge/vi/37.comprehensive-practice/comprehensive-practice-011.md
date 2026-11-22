# Giới hạn query depth và complexity

GraphQL cho phép client tự chọn field, lồng object và yêu cầu nhiều collection trong cùng một operation. Sự linh hoạt này cũng tạo ra rủi ro: một query có thể rất sâu, rất rộng hoặc yêu cầu hàng nghìn bản ghi ở nhiều cấp. Nếu server chỉ giới hạn kích thước HTTP request, một document nhỏ vẫn có thể kích hoạt lượng công việc lớn ở resolver, database và downstream service.

Với Spring for GraphQL, GraphQL Java cung cấp hai cơ chế quan trọng để kiểm soát cấu trúc và chi phí của operation: `MaxQueryDepthInstrumentation` và `MaxQueryComplexityInstrumentation`. Depth giới hạn độ sâu của selection tree; complexity ước lượng tổng chi phí của các field, có thể tính thêm hệ số theo pagination và field đắt tiền.

Bài học này hướng dẫn cách hiểu hai giới hạn, cấu hình chúng trong Spring Boot, thiết kế công thức complexity phù hợp với schema, kiểm thử query bị từ chối và kết hợp với các lớp bảo vệ khác để tránh lạm dụng tài nguyên.

## 1. Vì sao cần giới hạn query?

Một endpoint GraphQL thường nhận nhiều loại operation:

- Query đơn giản lấy một object.
- Query lồng nhiều quan hệ như Author → Books → Reviews → User.
- Query lấy nhiều collection trong một operation.
- Query dùng alias để gọi cùng field nhiều lần với argument khác nhau.
- Query dùng fragment để tái sử dụng selection set.
- Query có pagination lớn hoặc collection lồng nhau.

Ví dụ, client có thể gửi:

~~~graphql
query DeepBook {
    book(id: "book-42") {
        author {
            books(first: 100) {
                reviews(first: 100) {
                    author {
                        books(first: 100) {
                            title
                        }
                    }
                }
            }
        }
    }
}
~~~

Document không quá dài, nhưng mỗi cấp có thể mở rộng thành nhiều object. Nếu resolver truy vấn database hoặc gọi service cho từng object, lượng công việc có thể tăng rất nhanh.

Một request hợp lệ về cú pháp vẫn có thể tiêu thụ quá nhiều CPU, memory, database connections hoặc downstream quota. Vì vậy, server cần đánh giá query trước khi chạy resolver và từ chối operation vượt ngân sách đã định.

## 2. Query depth là gì?

Query depth là số cấp field lồng nhau sâu nhất trong selection tree của một operation. Mỗi lần query đi từ một object field tới field con của object đó, độ sâu tăng thêm.

Ví dụ:

~~~graphql
query {
    book {
        id
        author {
            name
        }
    }
}
~~~

Nhánh sâu nhất là:

~~~text
book
  └── author
        └── name
~~~

Field `id` và `name` là leaf field. Query depth tập trung vào đường đi sâu nhất; nó không cộng tất cả field ngang hàng thành một con số.

Một query khác có thể chỉ sâu hai cấp nhưng chọn rất nhiều field:

~~~graphql
query {
    book {
        id
        title
        isbn
        summary
        description
        author { id name email }
        publisher { id name website }
        reviews { id rating body createdAt }
    }
}
~~~

Query này không quá sâu nhưng vẫn có thể tạo nhiều công việc. Đây là lý do depth cần được kết hợp với complexity.

## 3. Query complexity là gì?

Query complexity là điểm ước lượng chi phí của toàn bộ selection set. Mỗi field đóng góp một phần chi phí; field cha còn có thể cộng chi phí của các field con.

GraphQL Java có `MaxQueryComplexityInstrumentation`. Constructor đơn giản dùng công thức mặc định:

~~~java
new MaxQueryComplexityInstrumentation(500)
~~~

Công thức mặc định tính chi phí của field theo dạng `1 + childComplexity`, trong đó `childComplexity` là tổng chi phí của các field con. Nhờ vậy, query có nhiều field hoặc nhiều cấp con sẽ có điểm cao hơn.

Ví dụ một selection tree:

~~~graphql
query {
    book {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Nếu mỗi field có cost bằng 1, có thể hình dung điểm mặc định như sau:

| Field | Child complexity | Field complexity |
| --- | ---: | ---: |
| `id` | 0 | 1 |
| `title` | 0 | 1 |
| `author` | 2 | 3 |
| `book` | 5 | 6 |

Đây là mô hình minh họa cách cộng `1 + childComplexity`. Điểm thực tế do GraphQL Java tính trên operation đã parse và schema tương ứng.

Complexity không phải thời gian chạy tính bằng millisecond. Nó là một ngân sách ước lượng, cần được thiết kế và hiệu chỉnh dựa trên chi phí thực tế của resolver.

## 4. Phân biệt depth, complexity và các giới hạn khác

| Giới hạn | Đo lường | Bắt được trường hợp nào? | Không thay thế được |
| --- | --- | --- | --- |
| Query depth | Đường lồng field sâu nhất | Quan hệ object lồng nhiều cấp | Complexity, pagination |
| Query complexity | Điểm chi phí tổng của field | Query rộng, nhiều field hoặc field đắt | Giới hạn body, parser |
| Parser limits | Kích thước và độ phức tạp cú pháp | Document quá lớn hoặc parser phải xử lý quá nhiều token | Chi phí resolver |
| HTTP body limit | Số byte request body | Payload JSON quá lớn | Query nhỏ nhưng trả nhiều dữ liệu |
| Pagination limit | Số item tối đa mỗi collection | Collection trả quá nhiều bản ghi | Query nhiều nhánh collection |
| Rate/concurrency limit | Số request hoặc execution đồng thời | Client gửi nhiều operation liên tục | Một operation đơn lẻ quá đắt |

Không có một giới hạn nào đủ để bảo vệ toàn bộ GraphQL server. Depth và complexity xử lý cấu trúc operation; các lớp khác xử lý kích thước request, số lượng dữ liệu, tần suất và tài nguyên runtime.

## 5. Vì sao chỉ giới hạn depth là chưa đủ?

Một query có depth thấp vẫn có thể yêu cầu nhiều field hoặc lặp lại một field bằng alias:

~~~graphql
query WideSearch {
    first: searchBooks(text: "java") {
        id
        title
        author { name }
    }

    second: searchBooks(text: "graphql") {
        id
        title
        author { name }
    }

    third: searchBooks(text: "database") {
        id
        title
        author { name }
    }
}
~~~

Mỗi nhánh không sâu, nhưng cùng một resolver tìm kiếm được gọi nhiều lần trong một operation.

Một query khác có ít field nhưng yêu cầu danh sách lớn:

~~~graphql
query LargePage {
    books(first: 5000) {
        id
        title
    }
}
~~~

Depth không phản ánh số lượng item server phải tải và serialize. Complexity mặc định cũng chỉ đếm field theo cấu trúc; nếu không tính pagination, query trên có thể có điểm thấp hơn chi phí thực tế.

Do đó, hãy dùng depth để chặn lồng sâu và dùng complexity tùy chỉnh để tính thêm các yếu tố có ảnh hưởng tới công việc thực tế.

## 6. MaxQueryDepthInstrumentation trong GraphQL Java

`MaxQueryDepthInstrumentation` thuộc package `graphql.analysis`. Instrumentation duyệt selection tree và từ chối execution khi độ sâu vượt ngưỡng.

Ví dụ:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;

MaxQueryDepthInstrumentation depthLimit =
        new MaxQueryDepthInstrumentation(8);
~~~

Trong ví dụ, operation có depth lớn hơn 8 sẽ bị abort. Ngưỡng 8 chỉ là giá trị minh họa; cần đo schema và operation thực tế để chọn giới hạn phù hợp.

Khi vượt giới hạn, GraphQL Java phát sinh `AbortExecutionException`. Kết quả GraphQL có error với classification `ExecutionAborted`; các DataFetcher của operation bị từ chối sẽ không tiếp tục chạy.

Giới hạn này được đánh giá ở bước thực thi GraphQL, sau khi document đã được parse. Nó không phải giới hạn grammar parser và không bảo vệ chi phí đọc một HTTP body cực lớn trước khi parse.

## 7. MaxQueryComplexityInstrumentation trong GraphQL Java

`MaxQueryComplexityInstrumentation` cũng thuộc package `graphql.analysis`. Nó tính điểm complexity của operation và abort nếu tổng điểm vượt ngưỡng.

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;

MaxQueryComplexityInstrumentation complexityLimit =
        new MaxQueryComplexityInstrumentation(500);
~~~

Constructor một tham số dùng calculator mặc định `1 + childComplexity`. Cách này phù hợp để bắt query có nhiều field, nhưng chưa phản ánh đầy đủ chi phí của collection lớn hoặc resolver đặc biệt đắt.

GraphQL Java còn hỗ trợ constructor nhận `FieldComplexityCalculator` để ứng dụng tự định nghĩa chi phí cho từng field. Đây là cách nên cân nhắc khi schema có pagination, search, report, analytics hoặc các field gọi downstream tốn kém.

## 8. Cấu hình depth và complexity trong Spring Boot

Spring Boot GraphQL starter tự phát hiện các bean triển khai `graphql.execution.instrumentation.Instrumentation` và đăng ký chúng khi tạo `GraphQlSource`. Vì vậy, có thể khai báo hai instrumentation bean trong configuration:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlQueryLimitsConfiguration {

    @Bean
    MaxQueryDepthInstrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    MaxQueryComplexityInstrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(500);
    }
}
~~~

Khi ứng dụng khởi động, Spring Boot đưa các instrumentation vào GraphQL Java execution pipeline. Operation được kiểm tra trước khi resolver thực hiện công việc.

Hai ngưỡng trong ví dụ không phải giá trị mặc định phù hợp cho mọi ứng dụng. Hãy bắt đầu với mức thận trọng ở môi trường staging, chạy operation đại diện và điều chỉnh theo latency, số lượng resolver, kích thước response và tài nguyên database.

Nếu ứng dụng tự tạo `GraphQL` hoặc `GraphQlSource` mà không dùng cơ chế auto-configuration của Boot, cần đăng ký instrumentation trực tiếp. Khi đã có instrumentation cho metrics, tracing hoặc logging, hãy kết hợp chúng bằng `ChainedInstrumentation` thay vì ghi đè cấu hình đang có.

## 9. Tính complexity theo pagination

Đối với collection, chi phí thường phụ thuộc vào số item được trả về. Ví dụ `books(first: 100)` có thể cần tải 100 object và resolve các field con của mỗi object.

Một công thức phù hợp hơn là:

\[
C(field) = baseCost + pageSize \times childComplexity
\]

Với field trả về scalar list hoặc không có child field, vẫn cần tính chi phí theo số item:

\[
C(field) = baseCost + pageSize \times \max(1, childComplexity)
\]

Ví dụ:

- `books(first: 50)` có 3 field con, chi phí có thể xấp xỉ `1 + 50 × 3 = 151`.
- Mỗi book có `reviews(first: 10)`, chi phí review lại được nhân theo 10.
- Khi hai collection lồng nhau, chi phí có thể tăng theo tích số lượng item ở từng cấp.

Đây vẫn là mô hình ước lượng. Cần tính thêm chi phí field con và các resolver có công việc đặc biệt.

## 10. Viết FieldComplexityCalculator tùy chỉnh

Giả sử schema có các collection phân trang:

~~~graphql
type Query {
    books(first: Int = 20): [Book!]!
    searchBooks(text: String!, first: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}

type Review {
    body: String!
}
~~~

Ta muốn:

- Field thông thường có base cost bằng 1.
- `searchBooks` có base cost cao hơn vì thực hiện tìm kiếm.
- `books`, `searchBooks` và `reviews` nhân chi phí field con theo số item.
- Pagination được giới hạn tối đa 100 item ở cả resolver và calculator.

Ví dụ:

~~~java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlComplexityConfiguration {

    private static final int DEFAULT_BOOK_PAGE_SIZE = 20;
    private static final int DEFAULT_REVIEW_PAGE_SIZE = 10;
    private static final int MAX_PAGE_SIZE = 100;

    @Bean
    MaxQueryComplexityInstrumentation queryComplexityInstrumentation() {
        FieldComplexityCalculator calculator =
                (environment, childComplexity) -> {
                    String fieldName = environment.getField().getName();

                    int baseCost = "searchBooks".equals(fieldName) ? 10 : 1;

                    if ("books".equals(fieldName)
                            || "searchBooks".equals(fieldName)
                            || "reviews".equals(fieldName)) {

                        Object rawFirst =
                                environment.getArguments().get("first");

                        int defaultPageSize = "reviews".equals(fieldName)
                                ? DEFAULT_REVIEW_PAGE_SIZE
                                : DEFAULT_BOOK_PAGE_SIZE;

                        int requested = rawFirst instanceof Number
                                ? ((Number) rawFirst).intValue()
                                : defaultPageSize;

                        int pageSize = Math.max(
                                1,
                                Math.min(requested, MAX_PAGE_SIZE)
                        );

                        return baseCost
                                + pageSize * Math.max(1, childComplexity);
                    }

                    return baseCost + childComplexity;
                };

        return new MaxQueryComplexityInstrumentation(500, calculator);
    }
}
~~~

Đây là ví dụ calculator theo tên field để minh họa cách tính cost. Trong ứng dụng thực tế, nên xây dựng bảng cost theo schema coordinate như `Query.searchBooks`, `Query.books` và `Book.reviews`, tránh áp dụng cùng tên field cho những type có semantics khác nhau.

Nếu dùng calculator tùy chỉnh này, hãy thay bean complexity đơn giản ở mục cấu hình Spring Boot bằng bean ở đây; không đăng ký đồng thời hai `MaxQueryComplexityInstrumentation` cho cùng một policy.

Điểm quan trọng: resolver phải thực thi cùng giới hạn pagination tối đa 100. Nếu calculator giới hạn cost ở 100 nhưng resolver vẫn cho phép trả 5.000 item, điểm complexity sẽ đánh giá thấp chi phí thật.

Nếu server dùng default pagination khác 20 hoặc 10, calculator phải dùng đúng default đó. Quy tắc tính cost và quy tắc thực thi pagination phải thống nhất.

## 11. Tính chi phí cho field đắt tiền

Không phải field nào cũng có chi phí tương đương. Một field trả property từ object có thể rất rẻ, trong khi field khác gọi hệ thống tìm kiếm, tổng hợp báo cáo hoặc downstream API.

Có thể gán trọng số theo field:

| Field | Base cost minh họa | Lý do |
| --- | ---: | --- |
| `id`, `title` | 1 | Đọc thuộc tính đơn giản |
| `author` | 2 | Có thể cần truy vấn dữ liệu liên quan |
| `searchBooks` | 10 | Truy vấn hệ thống tìm kiếm |
| `exportReport` | 50 | Tổng hợp nhiều nguồn dữ liệu |
| `reviews(first:)` | Theo page size | Chi phí tăng theo số item |

Ví dụ calculator:

~~~java
FieldComplexityCalculator calculator = (environment, childComplexity) -> {
    String fieldName = environment.getField().getName();

    int baseCost = switch (fieldName) {
        case "searchBooks" -> 10;
        case "exportReport" -> 50;
        case "author" -> 2;
        default -> 1;
    };

    return baseCost + childComplexity;
};
~~~

Đây là ví dụ trọng số cơ bản cho field. Nếu cần tính pagination, hãy kết hợp base cost này với multiplier theo `pageSize` ở mục trước thay vì thay thế công thức pagination.

Trọng số nên được xác định từ profiling, query plan và số lần gọi downstream. Không nên đặt một con số tùy ý rồi coi đó là số đo chính xác của CPU hoặc database work.

## 12. Nested pagination và chi phí nhân theo cấp

Hãy xem query:

~~~graphql
query BookReviews {
    books(first: 50) {
        id
        title
        reviews(first: 10) {
            body
        }
    }
}
~~~

Nếu mỗi book có tối đa 10 review, server có thể phải xử lý đến 500 review cùng 50 book.

Với calculator nhân `pageSize × childComplexity`, chi phí của `reviews` được tính trước, rồi chi phí đó được nhân theo page size của `books`.

Nếu collection lồng thêm một cấp nữa, ví dụ review có reactions, chi phí tiếp tục tăng theo page size của reactions. Điều này giúp complexity phản ánh tốt hơn số object tiềm năng được trả về.

Cần bảo đảm mọi collection có khả năng trả nhiều item đều được tính multiplier. Nếu chỉ tính `books` mà bỏ qua `reviews`, client có thể tạo query tốn kém thông qua field lồng.

## 13. Alias, fragment và nhiều operation

GraphQL hỗ trợ alias và fragment để client tổ chức operation. Những tính năng này không tự làm query an toàn hơn.

Alias có thể gọi cùng một field nhiều lần:

~~~graphql
query {
    javaBooks: searchBooks(text: "java") {
        id
    }

    graphqlBooks: searchBooks(text: "graphql") {
        id
    }
}
~~~

Mỗi nhánh có thể tạo một lần gọi resolver riêng. Complexity cần tính các lần xuất hiện trong operation, không chỉ đếm tên field duy nhất.

Fragment giúp tái sử dụng selection set:

~~~graphql
fragment BookSummary on Book {
    id
    title
    author {
        name
    }
}

query {
    books(first: 20) {
        ...BookSummary
    }
}
~~~

Depth và complexity cần được đánh giá trên operation sau khi xử lý fragment và type condition. Không nên tự viết phép đếm chuỗi đơn giản để thay thế GraphQL parser/traverser.

Nếu document có nhiều operation, client thường gửi `operationName` để chọn một operation. Hãy kiểm thử cách instrumentation xử lý operation được chọn và operation không được chọn với phiên bản GraphQL Java mà ứng dụng đang dùng.

## 14. Parser limits và introspection limits

GraphQL Java còn có các giới hạn ở parser level. Chúng xử lý document quá lớn hoặc quá phức tạp về cú pháp trước khi instrumentation depth/complexity được áp dụng.

Tài liệu GraphQL Java v25 hiện công bố các giới hạn mặc định sau:

| Parser/introspection limit | Giá trị được tài liệu v25 nêu | Mục đích |
| --- | ---: | --- |
| Maximum query characters | 1 MB | Hạn chế document quá dài |
| Maximum query tokens | 15.000 | Hạn chế công việc tokenize |
| Maximum whitespace tokens | 200.000 | Hạn chế whitespace bất thường |
| Maximum grammar rule depth | 500 | Hạn chế parser stack depth |
| Good-faith introspection fields | 500 | Giới hạn kích thước introspection |
| Good-faith introspection depth | 20 | Giới hạn độ sâu introspection |

Đây là giá trị theo tài liệu GraphQL Java v25, không nên coi là mặc định bất biến của mọi phiên bản. Hãy kiểm tra dependency GraphQL Java mà Spring Boot đang quản lý trước khi dựa vào chúng.

Parser rule depth khác query depth:

- Parser rule depth bảo vệ quá trình phân tích cú pháp.
- Query depth instrumentation giới hạn đường lồng field trong operation hợp lệ.
- Complexity instrumentation ước lượng tổng chi phí field sau khi document được phân tích.

Ba cơ chế xử lý các giai đoạn và rủi ro khác nhau.

## 15. Pagination limit vẫn bắt buộc

Complexity calculator không thay thế validation và giới hạn pagination ở resolver.

Schema:

~~~graphql
type Query {
    books(first: Int = 20): [Book!]!
}
~~~

Schema trên cho phép argument `first` nhưng không tự áp đặt giá trị tối đa 100. Cần kiểm tra giới hạn ở tầng input/service:

~~~java
private static final int MAX_PAGE_SIZE = 100;

public List<Book> findBooks(int first) {
    if (first < 1 || first > MAX_PAGE_SIZE) {
        throw new IllegalArgumentException(
                "first must be between 1 and " + MAX_PAGE_SIZE
        );
    }

    return bookRepository.findFirstPage(first);
}
~~~

Có thể dùng custom scalar, Bean Validation hoặc validation logic trong service tùy kiến trúc. Dù chọn cách nào, giá trị tối đa phải được thực thi thực sự trước khi truy vấn dữ liệu.

Nếu resolver tự động clamp giá trị, hãy dùng cùng quy tắc clamp trong complexity calculator. Không để calculator giả định page size 100 trong khi resolver thực tế trả nhiều hơn.

## 16. DataLoader không thay thế complexity limit

DataLoader giúp gom các lần tải dữ liệu theo key để giảm N+1. Tuy nhiên, DataLoader không giới hạn số item mà query yêu cầu.

Ví dụ query tải 2.000 book và mỗi book có 100 review vẫn có thể tạo response rất lớn, dù các lookup được batch thành ít câu truy vấn hơn.

Hãy kết hợp:

- DataLoader hoặc `@BatchMapping` để giảm số lần gọi dữ liệu.
- Pagination để giới hạn số item.
- Query depth để giới hạn nesting.
- Query complexity để giới hạn tổng công việc ước lượng.
- Rate/concurrency limit để giới hạn số operation chạy đồng thời.

Tối ưu resolver giúp xử lý query hiệu quả hơn; complexity limit giúp từ chối query vượt ngân sách.

## 17. Kiểm thử query vượt depth bằng GraphQlTester

Nên có integration test xác minh operation vượt giới hạn bị từ chối. Ví dụ dưới đây dùng HTTP tester với server chạy trên random port:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QueryDepthLimitTests {

    @LocalServerPort
    private int port;

    private GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port + "/graphql")
                .build();

        graphQlTester = HttpGraphQlTester.create(client);
    }

    @Test
    void rejectsQueryThatExceedsDepthLimit() {
        graphQlTester.document("""
                query TooDeep {
                    book(id: "book-42") {
                        author {
                            books(first: 10) {
                                reviews(first: 10) {
                                    author {
                                        books(first: 10) {
                                            reviews(first: 10) {
                                                author {
                                                    books(first: 10) {
                                                        title
                                                    }
                                                }
                                            }
                                        }
                                    }
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
}
~~~

Ví dụ giả định schema có các field tương ứng và depth limit nhỏ hơn độ sâu operation. Trong test thực tế, nên xác minh thêm resolver/service không được gọi khi operation bị abort, để bảo đảm giới hạn được áp dụng trước khi thực thi field.

## 18. Kiểm thử complexity và pagination

Một test khác nên gửi operation có complexity vượt ngân sách:

~~~java
@Test
void rejectsQueryThatExceedsComplexityLimit() {
    graphQlTester.document("""
            query ExpensiveBooks {
                books(first: 100) {
                    id
                    title
                    reviews(first: 100) {
                        body
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

Test cần sử dụng calculator và threshold đã cấu hình trong ứng dụng. Nếu query vẫn chạy, hãy kiểm tra:

- Instrumentation bean đã được Spring Boot phát hiện chưa.
- Có `GraphQlSource` tùy chỉnh ghi đè instrumentation không.
- Operation có chọn đúng field collection không.
- Calculator có đọc được argument đã bind không.
- Default page size có khớp schema và resolver không.
- Complexity threshold có đủ thấp để test vượt ngưỡng không.

Ngoài test từ chối, cần test query hợp lệ ngay dưới giới hạn để tránh cấu hình quá chặt làm hỏng client bình thường.

Đặt method test này trong cùng test class đã khởi tạo `GraphQlTester` ở mục trước.

## 19. Chọn ngưỡng depth và complexity như thế nào?

Không có một ngưỡng phù hợp cho mọi GraphQL API. Ngưỡng phụ thuộc schema, loại resolver, pagination, database và SLA.

Một quy trình thực tế:

1. Thu thập operation đại diện từ log hoặc persisted query registry.
2. Chạy operation với dữ liệu gần production.
3. Ghi depth, complexity score, số resolver, số database calls và response size.
4. Đo p50/p95/p99 latency cùng CPU/memory.
5. Chọn threshold cao hơn nhu cầu hợp lệ thông thường nhưng thấp hơn vùng gây quá tải.
6. Kiểm thử operation lớn nhất được hỗ trợ.
7. Điều chỉnh theo traffic và thay đổi schema.

Ví dụ ban đầu có thể thử depth 8 và complexity 500, nhưng phải đo lại trước khi áp dụng production. Không nên lấy các số ví dụ trong tài liệu làm cấu hình mặc định.

Nếu có nhiều nhóm operation khác nhau, có thể cân nhắc persisted query allowlist, quota theo client hoặc một policy riêng cho nhóm operation đã được kiểm duyệt.

## 20. Theo dõi khi giới hạn chặn query

Khi instrumentation từ chối operation, cần có telemetry đủ để biết giới hạn nào đang kích hoạt và client có bị ảnh hưởng hợp lệ hay không.

Nên ghi nhận:

- Operation name hoặc persisted operation ID.
- Execution ID/correlation ID.
- Query depth hoặc complexity score.
- Configured maximum.
- Client identity đã được xác thực.
- Thời điểm và outcome.
- Nhóm field hoặc schema coordinate gây chi phí cao nếu có thể lấy an toàn.

Không log toàn bộ query variables nếu chúng có thể chứa thông tin cá nhân hoặc token. Tránh đưa raw query và ID có cardinality cao thành metric label.

Có thể theo dõi các metric như số request bị từ chối theo loại limit, phân bố complexity score, tỷ lệ lỗi và latency trước khi abort. Dùng log/trace để điều tra từng operation, metric dùng label ít biến thiên.

## 21. Subscription và operation chạy lâu

Subscription có vòng đời khác query thông thường. Depth và complexity có thể đánh giá selection set lúc client đăng ký subscription, nhưng không giới hạn số event server phát ra sau đó.

Cần có thêm chính sách cho subscription:

- Số subscription đồng thời trên mỗi connection/client.
- Tần suất event và giới hạn buffer.
- Timeout hoặc thời gian sống tối đa nếu phù hợp.
- Backpressure và cancellation.
- Chi phí của resolver cho mỗi event.
- Authorization trong suốt vòng đời subscription.

Không giả định một subscription có complexity thấp thì chi phí dài hạn cũng thấp. Một subscription nhẹ nhưng phát hàng nghìn event mỗi giây vẫn có thể gây tải lớn.

## 22. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query sâu vẫn chạy | Instrumentation chưa được đăng ký | Kiểm tra Spring Boot Instrumentation beans |
| Query nhiều field không bị chặn | Chỉ cấu hình depth | Bổ sung complexity instrumentation |
| Query có page size lớn vẫn được chấp nhận | Dùng complexity mặc định | Tính multiplier theo pagination |
| Calculator đánh giá thấp chi phí | Resolver không dùng cùng max page size/default | Đồng bộ calculator và resolver |
| Query bình thường bị từ chối | Threshold đặt quá thấp | Đo operation thực tế và điều chỉnh |
| Parser vẫn tốn tài nguyên trước khi depth check | Nhầm query depth với parser rule depth | Cấu hình parser/request limits |
| DataLoader có nhưng query vẫn rất nặng | Nhầm batching với giới hạn dữ liệu | Kết hợp pagination và complexity |
| Alias gọi field nhiều lần nhưng không được tính | Calculator chỉ đếm field name duy nhất | Đánh giá từng field occurrence trong operation |
| Subscription gây tải dài hạn | Chỉ giới hạn complexity lúc subscribe | Thêm event rate, concurrency và backpressure |
| Metrics không giải thích được request bị chặn | Thiếu log score và execution ID | Ghi nhận metadata giới hạn an toàn |

## 23. Bài thực hành: bảo vệ API thư viện sách

Giả sử ứng dụng có schema:

~~~graphql
type Query {
    book(id: ID!): Book
    books(first: Int = 20): [Book!]!
    searchBooks(text: String!, first: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author!
    reviews(first: Int = 10): [Review!]!
}

type Author {
    id: ID!
    name: String!
    books(first: Int = 20): [Book!]!
}

type Review {
    id: ID!
    body: String!
    author: Author!
}
~~~

Thực hiện các bước:

1. Tạo `MaxQueryDepthInstrumentation` với giới hạn ban đầu là 8.
2. Tạo `MaxQueryComplexityInstrumentation` với giới hạn ban đầu là 500.
3. Thêm calculator nhân chi phí theo `first` cho `books`, `searchBooks` và `reviews`.
4. Bảo đảm resolver/service áp dụng cùng default và maximum page size.
5. Viết một query nông, ít field và xác nhận query được chấp nhận.
6. Viết query lồng nhiều cấp và xác nhận depth instrumentation từ chối.
7. Viết query có nhiều collection lớn và xác nhận complexity instrumentation từ chối.
8. Viết query ngay dưới threshold và xác nhận vẫn hoạt động.
9. Kiểm tra service/repository không bị gọi khi query bị abort.
10. Ghi nhận metric cho query bị chặn và điều chỉnh threshold dựa trên benchmark.

Khi hoàn thành, hãy trả lời:

- Vì sao query depth thấp vẫn có thể gây quá tải?
- Vì sao complexity mặc định chưa phản ánh đủ chi phí của `books(first: 1000)`?
- Điều gì xảy ra nếu calculator giới hạn page size ở 100 nhưng resolver trả 1.000 item?
- DataLoader cải thiện điều gì và không giải quyết điều gì?
- Vì sao subscription cần thêm giới hạn ngoài depth và complexity?

## 24. Những điểm cần ghi nhớ

- Query depth đo đường lồng field sâu nhất trong selection tree.
- Query complexity ước lượng tổng chi phí của các field trong operation.
- `MaxQueryDepthInstrumentation` và `MaxQueryComplexityInstrumentation` là hai instrumentation có sẵn trong GraphQL Java.
- Spring Boot GraphQL starter có thể tự phát hiện các bean `Instrumentation`.
- `FieldComplexityCalculator` cho phép tính chi phí theo field, pagination và resolver đặc biệt.
- Calculator phải dùng cùng default và giới hạn pagination với resolver.
- Parser limits, body limits, pagination và rate limits xử lý những rủi ro khác nhau.
- DataLoader giảm N+1 nhưng không thay thế giới hạn số item hoặc complexity.
- Subscription cần thêm giới hạn event, concurrency và backpressure.
- Chọn threshold dựa trên operation thực tế và benchmark, không dùng số ví dụ một cách máy móc.

Giới hạn query depth và complexity giúp Spring for GraphQL kiểm soát operation trước khi resolver thực hiện công việc tốn kém. Khi kết hợp giới hạn nesting, cost theo pagination, parser safeguards, giới hạn dữ liệu và telemetry, server có thể bảo vệ tài nguyên tốt hơn mà vẫn phục vụ các query hợp lệ của client.

## Tài liệu tham khảo

- [GraphQL Java — Limits](https://graphql-java.com/documentation/limits/)
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [GraphQL Java — FieldComplexityCalculator API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/FieldComplexityCalculator.html)
- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
