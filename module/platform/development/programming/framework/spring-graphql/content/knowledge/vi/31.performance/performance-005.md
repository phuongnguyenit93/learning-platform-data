# Query complexity limit trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao GraphQL cần giới hạn độ sâu và độ phức tạp của query.
- Phân biệt query depth với query complexity.
- Nhận diện query sâu, query rộng, alias và nested list có nguy cơ tiêu tốn tài nguyên.
- Cấu hình `MaxQueryDepthInstrumentation` và `MaxQueryComplexityInstrumentation`.
- Đưa GraphQL Java instrumentation vào `GraphQlSource` của Spring Boot.
- Thiết kế field cost dựa trên số phần tử pagination và chi phí resolver.
- Kết hợp complexity limit với pagination, DataLoader, timeout và rate limiting.
- Kiểm thử query bị từ chối trước khi DataFetcher thực thi.
- Chọn ngưỡng phù hợp dựa trên workload và đo đạc thực tế.

## 1. Vì sao cần query complexity limit?

GraphQL cho phép client tự chọn field và cấu trúc dữ liệu cần trả về. Một request HTTP nhỏ có thể yêu cầu server tải nhiều quan hệ lồng nhau, gọi nhiều DataFetcher hoặc tạo ra một lượng dữ liệu rất lớn.

Ví dụ một query có vẻ hợp lệ:

~~~graphql
query {
    books(first: 100) {
        edges {
            node {
                id
                title
                author {
                    name
                    books(first: 100) {
                        edges {
                            node {
                                title
                            }
                        }
                    }
                }
            }
        }
    }
}
~~~

Nếu mỗi `author` lại tải danh sách sách, số object được yêu cầu có thể tăng nhanh theo từng cấp lồng nhau. Query vẫn nhỏ về số byte nhưng chi phí thực thi có thể lớn.

Các biện pháp bảo vệ như giới hạn request body, authentication hoặc rate limit vẫn cần thiết, nhưng chúng không đo trực tiếp lượng công việc mà một GraphQL selection yêu cầu.

Query complexity limit đặt một ngân sách cho cấu trúc operation trước khi server thực thi các DataFetcher. Nó giúp từ chối query quá sâu hoặc quá tốn kém trước khi tạo tải lớn lên database và downstream services.

## 2. Query depth và query complexity khác nhau thế nào?

Hai giới hạn giải quyết hai kiểu query khác nhau:

| Giới hạn | Đo lường | Phát hiện tốt |
| --- | --- | --- |
| Query depth | Số cấp field lồng nhau | Query có nested relation quá sâu |
| Query complexity | Tổng chi phí ước tính của các field | Query rộng hoặc có nhiều field/list tốn kém |

Query depth là số tầng selection lồng nhau theo quy ước của instrumentation. Query complexity là tổng cost được tính từ field và các field con.

Ví dụ query rộng nhưng nông:

~~~graphql
query {
    books { id }
    authors { id }
    publishers { id }
    categories { id }
    reviews { id }
}
~~~

Query này có depth thấp nhưng có nhiều root field. Depth limit có thể không phát hiện được tải tổng hợp từ nhiều field.

Ngược lại, query sâu:

~~~graphql
query {
    author(id: "author-1") {
        books {
            reviews {
                author {
                    books {
                        reviews {
                            id
                        }
                    }
                }
            }
        }
    }
}
~~~

Query này có thể vượt depth limit dù mỗi cấp chỉ chọn một field.

Trong thực tế nên kết hợp depth và complexity limit. Depth giới hạn hình dạng lồng nhau; complexity giới hạn tổng ngân sách field.

## 3. Query complexity không phải thời gian thực thi

Complexity là ước lượng dựa trên GraphQL document, arguments và quy tắc cost đã cấu hình. Nó không phải phép đo chính xác số mili giây hoặc số câu SQL sẽ chạy.

Hai field có thể có cost thực tế rất khác nhau:

- Field đọc một thuộc tính đã có trong parent object.
- Field gọi một downstream service.
- Field tìm kiếm toàn văn bản.
- Field tải một danh sách lớn.
- Field thực hiện phép tính hoặc truy vấn tổng hợp.

Nếu mọi field đều có cost bằng nhau, instrumentation không thể biết field nào đắt hơn trong business logic. Vì vậy ứng dụng cần xác định cost model phù hợp với schema và workload.

Complexity limit là một hàng rào dự phòng. Nó không thay thế profiling, query plan, timeout hoặc kiểm soát truy cập dữ liệu.

## 4. GraphQL Java instrumentation

Spring for GraphQL dùng GraphQL Java để parse, validate và thực thi GraphQL operation. GraphQL Java cung cấp các instrumentation để kiểm tra query trước và trong quá trình execution.

Hai instrumentation thường dùng cho query limits:

- `MaxQueryDepthInstrumentation`: từ chối operation có depth vượt ngưỡng.
- `MaxQueryComplexityInstrumentation`: từ chối operation có complexity vượt ngưỡng.

Các class nằm trong package `graphql.analysis`.

Depth instrumentation nhận giới hạn depth tối đa. Complexity instrumentation nhận giới hạn complexity tối đa và có thể nhận thêm field complexity calculator để định nghĩa cost cho từng field.

Các giới hạn này cần được cấu hình ở GraphQL runtime. Chỉ đặt một property tùy ý trong `application.yml` sẽ không tự kích hoạt instrumentation nếu Spring Boot/Spring for GraphQL phiên bản đang dùng không cung cấp property tương ứng.

## 5. Cấu hình giới hạn query depth

Ví dụ tạo instrumentation với depth tối đa là 8:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;

MaxQueryDepthInstrumentation depthLimit =
        new MaxQueryDepthInstrumentation(8);
~~~

Ngưỡng `8` chỉ là ví dụ để minh họa. Giá trị phù hợp phụ thuộc schema, nested relation hợp lệ và cách ứng dụng sử dụng fragments.

Khi query vượt giới hạn, GraphQL Java từ chối operation và trả GraphQL error. Các DataFetcher của operation bị từ chối không nên được thực thi.

Depth limit có ích với schema có nhiều quan hệ lồng nhau, chẳng hạn:

- Organization → teams → members → projects → tasks.
- Book → author → books → reviews → author.
- Category → children → products → variants.

Không đặt ngưỡng quá thấp khiến client không thể thực hiện use case hợp lệ. Hãy đo depth của các operation thực tế và dành khoảng an toàn cho những truy vấn cần thiết.

## 6. Cấu hình giới hạn query complexity

Ví dụ dùng complexity instrumentation với ngân sách tối đa 200:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;

MaxQueryComplexityInstrumentation complexityLimit =
        new MaxQueryComplexityInstrumentation(200);
~~~

Với cấu hình mặc định, GraphQL Java dùng field complexity calculator mặc định để cộng cost của field và các field con. Cách tính cụ thể cần được đối chiếu với phiên bản GraphQL Java mà ứng dụng đang dùng.

Ngưỡng `200` không phải giá trị mặc định phù hợp cho mọi hệ thống. Một schema nhỏ có thể cần ngân sách thấp hơn; một API có nhiều field đơn giản có thể cần ngưỡng cao hơn.

Complexity limit đặc biệt hữu ích với query rộng, nhiều aliases hoặc nhiều nhánh selection. Tuy nhiên, nếu list field có thể trả hàng trăm hoặc hàng nghìn phần tử, cần đưa kích thước list vào cost model thay vì chỉ tính mỗi field một đơn vị.

## 7. Đăng ký instrumentation trong Spring Boot

Với Spring Boot GraphQL auto-configuration, có thể đăng ký các GraphQL Java `Instrumentation` dưới dạng Spring beans. Boot thu thập các bean này theo thứ tự và đưa chúng vào `GraphQlSource`:

~~~java
import graphql.execution.instrumentation.Instrumentation;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GraphQlQueryLimitConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(200);
    }
}
~~~

Mỗi bean đóng góp một instrumentation vào GraphQL runtime. Cách đăng ký này cho phép Boot kết hợp các instrumentation do ứng dụng cung cấp với những instrumentation khác được cấu hình trong context, chẳng hạn observation. Nếu cần thứ tự cụ thể, khai báo `@Order` hoặc triển khai `Ordered` và kiểm tra thứ tự đó trong integration test.

Với ứng dụng không dùng Spring Boot, có thể cấu hình danh sách instrumentation trực tiếp trên `GraphQlSource.Builder` hoặc GraphQL Java `GraphQL.Builder`. Khi tự lắp ráp danh sách, hãy ghép depth/complexity limits với instrumentation hiện có thay vì vô tình thay thế chúng.

Sau khi khởi động ứng dụng, kiểm thử query vượt giới hạn qua GraphQL endpoint để xác nhận instrumentation thực sự đã được cài vào runtime.

## 8. Tùy chỉnh field cost

Một query complexity calculator có thể gán cost khác nhau cho từng field. GraphQL Java hỗ trợ `FieldComplexityCalculator` để tính cost dựa trên field environment và complexity của các field con.

Ví dụ minh họa: field thông thường có cost cơ bản là 1; nếu field nhận argument `first`, cost của các field con được nhân theo số phần tử yêu cầu:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;

MaxQueryComplexityInstrumentation complexityLimit =
        new MaxQueryComplexityInstrumentation(
                500,
                (environment, childComplexity) -> {
                    int multiplier = 1;

                    Object first = environment.getArguments().get("first");
                    if (first instanceof Number number) {
                        multiplier = Math.max(1, Math.min(number.intValue(), 100));
                    }

                    if (environment.getArguments().containsKey("first")) {
                        return 1 + multiplier * (1 + childComplexity);
                    }

                    return 1 + childComplexity;
                }
        );
~~~

Công thức minh họa:

\[
C(field) = 1 + multiplier \times C(children)
\]

Với field có argument `first`, nếu client yêu cầu 100 phần tử, cost của mỗi phần tử cùng các field con được nhân lên đến 100 lần. Field không có argument `first` vẫn dùng công thức cơ bản `1 + childComplexity`.

Đây là cost model đơn giản. Với schema thực tế, cần phân biệt field list với field scalar và áp dụng multiplier đúng cho các field có pagination. Không nhân cost của mọi field chỉ vì chúng có argument tên `first`.

Ví dụ trên giả định các field có argument `first` là field pagination và không có default page size khác cần áp dụng. Nếu SDL khai báo default như `first: Int = 20`, hãy bảo đảm calculator tính đúng giá trị mặc định khi client bỏ argument. Trong hệ thống production, nên xác định field pagination theo parent type và field name, rồi áp dụng default cùng maximum page size tương ứng của từng field.

## 9. Đưa pagination vào cost model

Một list field thường có chi phí tăng theo số phần tử được trả về. Vì vậy `first`, `limit` hoặc `pageSize` là các argument quan trọng khi tính complexity.

Ví dụ SDL:

~~~graphql
type Query {
    books(first: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

Một query:

~~~graphql
query {
    books(first: 50) {
        id
        reviews(first: 20) {
            id
        }
    }
}
~~~

Nếu mỗi book tải tối đa 20 review và client yêu cầu 50 book, số review tối đa có thể là 1.000. Một complexity model không tính multiplier có thể đánh giá thấp đáng kể chi phí này.

Nếu client bỏ `first`, calculator vẫn phải tính theo default đã khai báo trong schema hoặc default do service áp dụng. Nếu không, một operation có thể bỏ argument để nhận page mặc định lớn nhưng bị tính cost như một phần tử.

Nên:

- Đặt default page size nhỏ và rõ ràng.
- Giới hạn page size tối đa trong resolver/service hoặc input validation.
- Tính list multiplier trong complexity calculator.
- Tính nested list theo từng cấp.
- Dùng cost model bảo thủ cho field gọi downstream hoặc truy vấn tổng hợp.

Complexity calculator chỉ là một lớp bảo vệ. Resolver vẫn phải từ chối page size vượt giới hạn để tránh client gọi field qua một đường không được calculator bao phủ.

## 10. Gán cost theo loại field

Không phải field nào cũng có cùng chi phí. Có thể thiết kế cost model theo field coordinates hoặc metadata schema:

| Loại field | Ví dụ | Cost gợi ý |
| --- | --- | --- |
| Scalar trên parent | `Book.title` | Thấp |
| Quan hệ một-một | `Book.author` | Trung bình |
| Quan hệ danh sách | `Author.books(first: ...)` | Theo page size |
| Search | `searchBooks(query: ...)` | Cao hơn truy vấn ID |
| Aggregate/report | `salesSummary(range: ...)` | Cao |
| External lookup | `shippingEstimate` | Theo chi phí downstream |

Bảng trên chỉ là cách phân loại để thiết kế cost, không phải con số mặc định của GraphQL Java.

Với field đắt, có thể dùng cost cố định cao hơn hoặc tính theo argument. Tránh dùng nội dung query, ID người dùng hoặc giá trị tùy ý của client làm metric dimension chỉ để phục vụ cost model.

Một cost model tốt phải dễ giải thích, có giới hạn trên và được kiểm thử bằng các operation đại diện cho workload thực tế.

## 11. Fragments, aliases và query breadth

GraphQL cho phép tái sử dụng selection bằng fragment:

~~~graphql
fragment BookSummary on Book {
    id
    title
    author {
        name
    }
}

query {
    first: books(first: 20) {
        ...BookSummary
    }
    second: books(first: 20) {
        ...BookSummary
    }
}
~~~

Aliases cho phép client gọi cùng một field nhiều lần với arguments khác nhau. Điều này có thể làm tăng số nhánh cần thực thi dù document nhìn gọn nhờ fragment.

Depth limit chủ yếu kiểm soát độ lồng nhau. Complexity limit cần phản ánh các field selection thực tế sau khi phân tích document, bao gồm fragment và alias theo cách GraphQL Java phiên bản đang dùng tính toán.

Hãy thêm test cho:

- Một fragment được dùng ở nhiều vị trí.
- Cùng field được gọi qua nhiều alias.
- Nhiều root fields trong một operation.
- Nested list kết hợp fragment.
- Directives `@skip` và `@include` nếu chúng ảnh hưởng tới workload mà ứng dụng cần dự đoán.

Không giả định một fragment được khai báo một lần thì cost chỉ được tính một lần. Điều quan trọng là số lần selection có thể được thực thi trong operation.

## 12. Giới hạn complexity không thay thế DataLoader

Query complexity limit ước lượng công việc theo GraphQL selection. Nó không tự giải quyết N+1 database queries.

Ví dụ query lấy 100 book và mỗi book tải author. Nếu resolver gọi repository một lần cho mỗi book, server có thể vẫn phát sinh N+1 dù complexity nằm dưới ngưỡng.

DataLoader hoặc `@BatchMapping` giúp gom các lần tải quan hệ thành batch. Hai cơ chế có mục tiêu khác nhau:

- Complexity limit giới hạn lượng công việc client có thể yêu cầu.
- DataLoader giảm số lần gọi backend khi nhiều field cần dữ liệu liên quan.

Một hệ thống tốt cần cả hai. Không tăng complexity limit chỉ vì đã thêm DataLoader; batch vẫn có thể truy xuất và serialize một lượng dữ liệu rất lớn.

## 13. Kết hợp với các lớp bảo vệ khác

Query complexity chỉ là một phần của defense in depth:

| Lớp bảo vệ | Vấn đề được kiểm soát |
| --- | --- |
| HTTP request body limit | Request document hoặc variables quá lớn |
| Authentication/authorization | Ai được phép gọi operation và field |
| Query depth limit | Nested selection quá sâu |
| Query complexity limit | Tổng cost ước tính quá cao |
| Pagination max size | List trả quá nhiều phần tử |
| DataLoader/batching | Số lần gọi backend lặp lại |
| Timeout | Operation hoặc downstream call chạy quá lâu |
| Rate limiting | Một client gửi quá nhiều request |
| Concurrency limit | Quá nhiều operation đồng thời |
| Persisted query/allowlist | Giới hạn document được phép chạy |

Các lớp này bổ sung cho nhau. Một query complexity thấp vẫn có thể gọi một field downstream bị treo; timeout vẫn cần thiết. Một query hợp lệ vẫn có thể lạm dụng tài nguyên bằng cách gửi hàng trăm request; rate limit vẫn cần thiết.

## 14. Xử lý query bị từ chối

Khi instrumentation từ chối query vì depth hoặc complexity vượt ngưỡng, GraphQL execution trả về error theo cơ chế của GraphQL Java. Client cần nhận được lỗi đủ rõ để biết operation không được chấp nhận.

Không trả stack trace hoặc chi tiết nội bộ của schema và instrumentation cho client. Có thể chuẩn hóa error code ở tầng xử lý lỗi nếu API cần contract ổn định.

Cần phân biệt:

- Query bị từ chối bởi depth/complexity limit.
- Query hợp lệ nhưng resolver phát sinh business error.
- Resolver hoặc hạ tầng gặp internal error.
- HTTP request bị từ chối trước GraphQL execution do body size, authentication hoặc rate limit.

HTTP status cụ thể phụ thuộc GraphQL over HTTP handling, media type và cấu hình server. Client nên kiểm tra GraphQL `errors` thay vì giả định mọi query vượt complexity đều trả cùng một HTTP status.

## 15. Kiểm thử depth limit

Nên kiểm thử một query hợp lệ ở dưới ngưỡng và một query vượt ngưỡng.

Ví dụ test logic bằng GraphQL tester:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

@Test
void shouldRejectQueryThatExceedsDepthLimit() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                author(id: "author-1") {
                    books {
                        author {
                            books {
                                id
                            }
                        }
                    }
                }
            }
            """)
            .execute();

    response.errors().satisfy(errors ->
            assertThat(errors).isNotEmpty()
    );
}
~~~

Test cần dùng schema có các relation tương ứng và depth limit được cấu hình trong GraphQL runtime. Để xác minh query bị chặn trước DataFetcher, có thể dùng spy hoặc counter trong service:

~~~java
assertThat(bookServiceInvocationCount.get()).isZero();
~~~

Assertion này phải được đặt sau khi request đã hoàn tất và test fixture phải đảm bảo không có invocation nào từ setup hoặc test khác.

Không chỉ assert có error; một business error cũng có thể làm test pass. Nếu phiên bản instrumentation cung cấp message hoặc error classification ổn định, hãy kiểm tra code/message thuộc contract của ứng dụng.

## 16. Kiểm thử complexity limit và field cost

Tạo các operation có cost thấp và cao để xác minh ngưỡng hoạt động.

Các trường hợp nên có:

- Một query nhỏ nằm dưới ngưỡng.
- Một query rộng có nhiều root fields.
- Một query có nested list với page size lớn.
- Một query gọi field có cost cố định cao.
- Một query lặp field qua aliases.
- Một query dùng fragments ở nhiều vị trí.
- Argument pagination thiếu, null hoặc vượt giới hạn.
- Query có variables để truyền page size thay vì inline literal.

Nếu calculator sử dụng argument `first`, hãy test cả giá trị mặc định và giá trị runtime trong `variables`. Điều này xác minh calculator nhận argument đã được GraphQL xử lý theo đúng contract của phiên bản đang dùng.

Test phải chứng minh operation vượt ngân sách không gọi các service đắt. Đồng thời, query hợp lệ cần chạy thành công để bảo đảm giới hạn không chặn nhầm use case.

Ví dụ assertion cho operation có page size vượt ngân sách:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.graphql.test.tester.GraphQlTester;

GraphQlTester.Response response = graphQlTester.document("""
        query Books($first: Int!) {
            books(first: $first) {
                id
                title
            }
        }
        """)
        .variable("first", 100)
        .execute();

response.errors().satisfy(errors ->
        assertThat(errors).anySatisfy(error ->
                assertThat(error.getMessage())
                        .contains("maximum query complexity exceeded")
        )
);
assertThat(bookServiceInvocationCount.get()).isZero();
~~~

Ví dụ dùng message mặc định của GraphQL Java để minh họa. Nếu ứng dụng tùy chỉnh error message hoặc nâng phiên bản GraphQL Java, hãy assert error code/classification ổn định do API của ứng dụng công bố.

## 17. Chọn ngưỡng từ workload thực tế

Không nên chọn depth hoặc complexity limit chỉ dựa trên một con số phổ biến trên Internet.

Quy trình chọn ngưỡng:

1. Thu thập các operation hợp lệ từ client và môi trường test.
2. Đo depth và complexity của operation đại diện.
3. Xác định các query có cost cao nhất nhưng vẫn là use case hợp lệ.
4. Đặt ngưỡng cao hơn workload hợp lệ với một khoảng dự phòng.
5. Thử các query cực đoan và xác minh bị từ chối trước resolver.
6. Theo dõi error rate do query limit sau khi triển khai.
7. Điều chỉnh ngưỡng khi schema hoặc client operation thay đổi.

Có thể bắt đầu bằng ngưỡng tương đối rộng trong môi trường staging, thu thập dữ liệu rồi siết dần. Không dùng metrics high-cardinality như raw query text làm tag. Nếu cần biết operation nào vượt ngưỡng, ghi nhận operation name trong trace hoặc log đã được kiểm soát.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query sâu vẫn chạy | Depth instrumentation chưa được gắn vào GraphQL runtime | Kiểm tra GraphQlSource customizer và instrumentation chain |
| Complexity limit không có tác dụng | Chỉ tạo object instrumentation nhưng chưa đăng ký | Đưa instrumentation vào GraphQL builder |
| Metrics/tracing biến mất sau khi thêm limit | Instrumentation cũ bị thay thế thay vì được compose | Ghép instrumentation trong chain và kiểm tra Observation |
| Query rộng vẫn qua depth limit | Depth không đo số lượng sibling fields | Thêm complexity limit |
| Query list rất lớn vẫn có cost thấp | Cost model không nhân theo page size | Tùy chỉnh field complexity calculator |
| Page size vượt ngưỡng | Chỉ dựa vào query complexity | Validate max page size trong resolver/service |
| Fragment hoặc alias làm tải tăng | Test chưa bao phủ các selection được tái sử dụng | Bổ sung operation có fragment và alias |
| Query bị từ chối nhưng test vẫn pass sai | Chỉ assert có errors, có thể là business error | Kiểm tra error code/message và DataFetcher không được gọi |
| Query limit chặn operation hợp lệ | Ngưỡng quá thấp hoặc cost model quá bảo thủ | Đo workload hợp lệ và hiệu chỉnh |
| Đã có DataLoader nhưng server vẫn quá tải | Batching giảm round trip nhưng không giới hạn số object | Giữ complexity, pagination và timeout |
| Subscription tồn tại lâu gây tải | Complexity không giới hạn connection lifetime hoặc event rate | Thêm connection quota, rate limit và giới hạn publisher |

## 19. Quy trình triển khai Query complexity limit

Khi bảo vệ GraphQL API bằng query limits, hãy thực hiện theo trình tự:

1. **Đo workload.** Thu thập operation hợp lệ và xác định các query tốn kém.
2. **Chọn depth limit.** Giới hạn số cấp nested selection phù hợp schema.
3. **Chọn complexity limit.** Đặt ngân sách cho tổng field cost.
4. **Đăng ký instrumentation.** Cấu hình `MaxQueryDepthInstrumentation` và `MaxQueryComplexityInstrumentation` trong GraphQL runtime.
5. **Thiết kế cost model.** Tính tới pagination, nested list và field gọi downstream.
6. **Bảo vệ page size.** Validate giới hạn list tại service/resolver.
7. **Compose instrumentation.** Giữ observation và tracing instrumentation hiện có.
8. **Kiểm thử negative cases.** Bao gồm query sâu, rộng, aliases, fragments và nested lists.
9. **Kiểm tra trước resolver.** Xác minh operation bị từ chối không gọi service đắt.
10. **Theo dõi và hiệu chỉnh.** Quan sát query bị từ chối và thay đổi workload theo thời gian.

## 20. Tổng kết

Query complexity limit giúp Spring for GraphQL bảo vệ server trước các operation có cấu trúc quá sâu hoặc yêu cầu quá nhiều công việc. `MaxQueryDepthInstrumentation` giới hạn nested selection depth; `MaxQueryComplexityInstrumentation` tính ngân sách field cost. Hai cơ chế bổ sung cho nhau và nên được đăng ký vào GraphQL Java runtime thông qua cấu hình `GraphQlSource`.

Cost model mặc định chỉ là ước lượng. Với list field, cần tính pagination multiplier và đặt page size tối đa ở service. Complexity limit không thay thế DataLoader, timeout, authentication, rate limiting hoặc concurrency control. Hãy kiểm thử cả query hợp lệ và query bị từ chối, xác minh DataFetcher không chạy khi operation vượt ngưỡng, rồi hiệu chỉnh giới hạn dựa trên workload thực tế.

## Tài liệu tham khảo

- [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot – GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java – Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java – MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java – MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)

