# Đo hiệu quả chống N+1

Batch mapping và DataLoader giúp giảm số lần truy cập dữ liệu khi GraphQL resolve các field quan hệ. Tuy nhiên, việc thêm `@BatchMapping` chưa đủ để kết luận vấn đề N+1 đã được giải quyết. Cần đo số lần gọi batch method, số câu SQL, số key trong mỗi batch và thời gian xử lý trên cùng một operation trước và sau khi thay đổi.

Mục tiêu của việc đo là xác nhận ba điều: số truy vấn không còn tăng tuyến tính theo số object cha, kết quả vẫn được ghép đúng object, và độ trễ thực tế được cải thiện dưới tải đại diện. Bài học này tập trung vào cách kiểm chứng trong Spring for GraphQL, đặc biệt với `@BatchMapping`, DataLoader và JPA.

## N+1 thể hiện như thế nào?

Giả sử API trả danh sách sách và mỗi sách có một tác giả:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
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
```

Client lấy danh sách cùng tác giả:

```graphql
query BooksWithAuthors {
  books(first: 20) {
    id
    title
    author {
      id
      name
    }
  }
}
```

Resolver thông thường có thể gọi repository cho từng sách:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.getAuthorId()).orElse(null);
}
```

Với 20 sách, hệ thống có thể chạy một truy vấn lấy sách và thêm 20 truy vấn lấy tác giả. Tổng số là 21 câu SQL. Khi số sách tăng từ 20 lên 100, số truy vấn quan hệ cũng tăng từ 20 lên 100. Đây là dấu hiệu điển hình của N+1.

## Sau khi chuyển sang `@BatchMapping`

`@BatchMapping` cho phép Spring for GraphQL gom các source object của cùng field thành một lần gọi batch method. Ví dụ:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<Long> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        Map<Long, Author> authorsById = authorService.findAllByIds(authorIds);

        return books.stream()
                .filter(book -> authorsById.containsKey(book.getAuthorId()))
                .collect(Collectors.toMap(
                        Function.identity(),
                        book -> authorsById.get(book.getAuthorId())));
    }
}
```

Batch method nhận danh sách `Book`, lấy các `authorId` duy nhất, tải tác giả theo nhóm rồi trả về map từ từng `Book` sang `Author` tương ứng. Trong ví dụ, key của map là source object và value là dữ liệu cho field `author`.

Với 20 sách có author ID nằm trong giới hạn một batch, kỳ vọng có một truy vấn lấy sách và một truy vấn lấy tác giả. Tổng cộng khoảng 2 câu SQL thay vì 21. Nếu danh sách lớn hoặc bị chia thành nhiều batch, số truy vấn quan hệ có thể lớn hơn một.

Không đăng ký đồng thời `@SchemaMapping` và `@BatchMapping` cho cùng một field trong ví dụ thực tế. Khi đo trước/sau, mỗi lần chỉ để một cách mapping hoạt động để kết quả so sánh rõ ràng.

## Kỳ vọng số truy vấn theo kích thước danh sách

Để thấy xu hướng, hãy chạy cùng một GraphQL operation với số lượng sách khác nhau. Giả sử mỗi sách có một tác giả khác nhau và tất cả ID đều nằm trong giới hạn batch:

| Số sách (N) | Resolver riêng từng sách | Một batch cho quan hệ |
| ---: | ---: | ---: |
| 1 | 2 SQL | 2 SQL |
| 10 | 11 SQL | 2 SQL |
| 20 | 21 SQL | 2 SQL |
| 50 | 51 SQL | 2 SQL |
| 100 | 101 SQL | 2 SQL nếu vẫn nằm trong một batch |

Đây là mô hình minh họa, không phải cam kết cố định về số SQL của mọi ứng dụng. Kết quả thực tế còn phụ thuộc số key duy nhất, batch size, số tầng field lồng nhau, fetch strategy, cache và cách repository triển khai truy vấn.

Nếu batch giới hạn 50 key, 100 author ID duy nhất có thể cần hai lần tải quan hệ. Khi đó tổng SQL kỳ vọng là một truy vấn sách cộng hai truy vấn batch. Điều cần quan sát là số truy vấn tăng theo số batch, thay vì tăng theo từng object cha.

## Đo những chỉ số nào?

Không nên chỉ đo thời gian response. Một response nhanh trong dataset nhỏ vẫn có thể chạy N+1; ngược lại, số SQL giảm nhưng truy vấn batch quá nặng vẫn có thể làm response chậm.

| Chỉ số | Cho biết điều gì | Nên quan sát ở đâu |
| --- | --- | --- |
| Số lần gọi batch method | Batch mapping có gom nhiều source object vào cùng lần gọi hay không. | Counter trong `@BatchMapping` hoặc spy ở test. |
| Số key mỗi batch | Kích thước nhóm dữ liệu được tải. | Distribution summary hoặc histogram. |
| Số câu SQL/JDBC statement | N+1 có giảm ở tầng persistence hay không. | Hibernate Statistics hoặc datasource instrumentation. |
| Thời gian batch service | Truy vấn dữ liệu quan hệ mất bao lâu. | Timer quanh service batch. |
| Tổng thời gian GraphQL request | Client thực sự chờ bao lâu cho operation. | HTTP server metrics, tracing hoặc test timer. |
| Số hàng đọc và dữ liệu trả về | Batch có tải quá nhiều dữ liệu hay không. | Database metrics, query plan và log truy vấn. |
| p50, p95, p99 latency | Hệ thống hoạt động thế nào ở các mức tải khác nhau. | Load test và observability. |
| Cache hit/miss và số key trùng | DataLoader có tránh tải lặp trong request hay không. | DataLoader instrumentation hoặc metric tùy chỉnh. |
| Connection pool wait/active | Truy vấn có gây nghẽn pool database hay không. | HikariCP metrics hoặc datasource metrics. |

Đếm số câu SQL giúp phát hiện N+1; đo thời gian, số hàng và pool giúp đánh giá chi phí thực tế. Cần xem các chỉ số cùng nhau.

## Đếm batch method invocation

Với `@BatchMapping`, một cách đơn giản là ghi nhận mỗi lần phương thức batch được gọi và số source object trong batch. Micrometer có thể cung cấp `Counter`, `DistributionSummary` và `Timer` cho mục đích này.

Ví dụ minh họa với batch method đồng bộ:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Controller
public class BookController {

    private final AuthorService authorService;
    private final Counter batchCalls;
    private final DistributionSummary batchSize;
    private final Timer batchDuration;

    public BookController(AuthorService authorService, MeterRegistry registry) {
        this.authorService = authorService;
        this.batchCalls = Counter.builder("graphql.batch.invocations")
                .tag("loader", "book-author")
                .register(registry);
        this.batchSize = DistributionSummary.builder("graphql.batch.unique_keys")
                .tag("loader", "book-author")
                .register(registry);
        this.batchDuration = Timer.builder("graphql.batch.duration")
                .tag("loader", "book-author")
                .register(registry);
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        batchCalls.increment();
        List<Long> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();
        batchSize.record(authorIds.size());

        return batchDuration.record(() -> {
            Map<Long, Author> authorsById = authorService.findAllByIds(authorIds);
            return books.stream()
                    .filter(book -> authorsById.containsKey(book.getAuthorId()))
                    .collect(Collectors.toMap(
                            Function.identity(),
                            book -> authorsById.get(book.getAuthorId())));
        });
    }
}
```

`graphql.batch.invocations` đếm số lần batch method chạy; `graphql.batch.unique_keys` ghi nhận số author ID duy nhất trong mỗi batch; `graphql.batch.duration` đo thời gian xử lý batch service. Tên metric và tag trong ví dụ do ứng dụng định nghĩa.

Với phương thức trả về `CompletableFuture`, `Mono` hoặc `Flux`, không dừng timer ngay khi method trả publisher/future vì lúc đó công việc có thể chưa hoàn tất. Hãy dừng timer khi future hoàn tất hoặc publisher kết thúc, đồng thời ghi nhận cả trường hợp lỗi và cancellation nếu phù hợp.

Không gắn tag có cardinality cao như `bookId`, `authorId`, email, tenant tùy ý hoặc toàn bộ GraphQL query. Dùng tag ổn định như tên loader, GraphQL operation type hoặc tên operation đã được kiểm soát. Cardinality cao làm tăng bộ nhớ và chi phí hệ thống metrics.

**Lưu ý:** số lần field resolver logic được yêu cầu vẫn liên quan tới số object cha. Điều cần giảm là số lần batch method và số lần truy cập dữ liệu. Đừng kết luận batching thất bại chỉ vì GraphQL vẫn resolve field `author` cho từng `Book`.

## Đếm SQL bằng Hibernate Statistics

Với ứng dụng dùng Hibernate/JPA, có thể bật statistics trong cấu hình test:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Trong test, lấy `Statistics` từ `SessionFactory`, xóa số liệu trước operation rồi đọc số prepared statement sau khi GraphQL hoàn tất:

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;

class BookGraphQlIntegrationTests {

    private final GraphQlTester graphQlTester;
    private final Statistics statistics;

    BookGraphQlIntegrationTests(
            GraphQlTester graphQlTester,
            EntityManagerFactory entityManagerFactory) {
        this.graphQlTester = graphQlTester;
        this.statistics = entityManagerFactory
                .unwrap(SessionFactory.class)
                .getStatistics();
    }

    @Test
    void booksAndAuthorsUseBoundedNumberOfStatements() {
        statistics.clear();

        graphQlTester.document("""
            query {
              books(first: 20) {
                id
                title
                author {
                  id
                  name
                }
              }
            }
            """)
            .execute()
            .errors()
            .verify();

        long preparedStatements = statistics.getPrepareStatementCount();
        assertThat(preparedStatements).isLessThanOrEqualTo(2L);
    }
}
```

Ngưỡng `2` chỉ hợp lý với fixture và cấu hình đơn giản: một câu lấy sách, một câu lấy tác giả, không có truy vấn phụ khác. Trong dự án thực tế, hãy xác định baseline và ngưỡng dựa trên SQL thực sự cần chạy, không sao chép con số này một cách máy móc.

`getPrepareStatementCount()` đếm prepared statement do Hibernate chuẩn bị trong phạm vi `SessionFactory`; nó hữu ích để so sánh nhưng không phải bộ đếm hoàn hảo cho từng GraphQL request. Statistics có phạm vi rộng hơn request và có thể bị ảnh hưởng bởi test khác chạy song song. Nên cô lập test, tránh chạy đồng thời hoặc dùng datasource proxy/instrumentation để đo statement theo request.

Ngoài số prepared statement, Hibernate Statistics còn cung cấp các số liệu về entity fetch, collection fetch và query execution. Chọn đúng chỉ số theo câu hỏi cần trả lời; không coi `queryExecutionCount` là tổng số mọi SQL statement.

## Đo SQL ở tầng datasource

Khi cần đếm chính xác các lệnh JDBC trong một operation, có thể dùng datasource proxy hoặc công cụ quan sát JDBC tương đương. Công cụ này bọc `DataSource` để ghi nhận statement được thực thi, thời gian chạy và lỗi.

Ưu điểm so với việc chỉ đọc Hibernate Statistics:

- Có thể quan sát câu SQL do nhiều thư viện JDBC phát ra, không chỉ các truy vấn ORM được Hibernate thống kê.
- Có thể thu thập số lần execute và thời gian statement ở tầng datasource.
- Có thể gắn thông tin đo vào request hoặc test context nếu cấu hình instrumentation phù hợp.

Không nên bật log đầy đủ bind parameter trong production nếu tham số có dữ liệu cá nhân hoặc bí mật. Với môi trường production, ưu tiên metrics tổng hợp, tracing có kiểm soát và sampling; giữ SQL chi tiết ở môi trường test hoặc debug có bảo vệ.

## So sánh trước và sau một cách công bằng

Để phép đo có ý nghĩa, giữ nguyên các điều kiện giữa hai lần chạy:

1. **Cùng GraphQL operation:** chọn đúng các field và argument giống nhau. Nếu query sau batching lấy ít field hơn, số SQL giảm không chứng minh batching hiệu quả.
2. **Cùng dữ liệu:** dùng cùng số sách, số tác giả duy nhất, tỷ lệ ID trùng và kích thước từng quan hệ.
3. **Cùng cache state:** phân biệt cache lạnh và cache nóng. JPA persistence context, second-level cache, query cache và cache của ứng dụng có thể che giấu N+1.
4. **Cùng pagination:** giữ `first`, filter và sort giống nhau để so sánh cùng khối lượng công việc.
5. **Cùng môi trường:** dùng cùng database, index, connection pool, cấu hình JVM và network.
6. **Lặp lại nhiều lần:** chạy warm-up trước, sau đó thu thập nhiều mẫu thay vì kết luận từ một lần đo.
7. **Tách thời gian:** phân biệt thời gian GraphQL tổng thể, thời gian batch service và thời gian SQL. Chúng bao gồm các phần chi phí khác nhau.

Khi đo cache lạnh, cần tạo request mới và bảo đảm không vô tình dùng lại persistence context. Khi đo cache nóng, hãy ghi rõ cache nào đang bật. Không trộn hai chế độ trong cùng một thống kê.

## Kiểm chứng xu hướng theo N

Một cách thực tế để phát hiện N+1 là thay đổi số lượng object cha trong cùng một loại operation. Chạy các mức như 1, 10, 25, 50 và 100 sách, sau đó vẽ số SQL theo N.

Với resolver riêng từng sách, số truy vấn thường có dạng gần `1 + N` (một truy vấn cha và N truy vấn con). Với batching, số truy vấn thường gần `1 + số batch`, trong đó số batch phụ thuộc số key duy nhất, batch size và các đợt dispatch.

```text
Số sách (N):       1    10    20    50    100
Resolver riêng:    2    11    21    51    101 SQL
Một batch:         2     2     2     2      2 SQL
```

Ví dụ chỉ mô tả trường hợp tất cả key có thể tải trong một batch và không có truy vấn phụ. Khi batch size là 50, số SQL của batching sẽ tăng theo số nhóm key, không còn giữ nguyên ở mức 2.

Đừng chỉ nhìn một điểm N=10. Một resolver có thể vô tình chạy hai truy vấn cho N=10 do cache, nhưng sẽ lộ N+1 khi N tăng hoặc tỷ lệ key khác nhau. Xu hướng theo N đáng tin cậy hơn một con số đơn lẻ.

## Đo thời gian và hiệu năng dưới tải

Giảm SQL count không luôn đồng nghĩa response nhanh hơn. Một câu SQL batch có thể join quá nhiều bảng, trả nhiều cột hoặc đọc quá nhiều hàng. Vì vậy, sau khi xác nhận số truy vấn, cần đo:

- Thời gian thực thi SQL batch và query plan của database.
- Tổng thời gian GraphQL operation, gồm resolver, serialize và truyền response.
- p50, p95, p99 latency ở tải thấp và tải đồng thời.
- Throughput, số lỗi timeout và số request bị từ chối.
- Số connection đang dùng, thời gian chờ connection và queue của executor.
- Kích thước response, số hàng đọc và bộ nhớ sử dụng.

Chạy load test với dữ liệu có kích thước và phân bố giống production. Tăng concurrency từng bước để xác định điểm mà database hoặc connection pool bắt đầu bão hòa. Đo cả trường hợp nhiều object cùng một foreign key và trường hợp tất cả key đều khác nhau vì cache DataLoader sẽ có hiệu quả khác nhau.

## Phân biệt batching với các cách tối ưu khác

N+1 có thể được xử lý bằng nhiều chiến lược. `@BatchMapping` và DataLoader không phải lựa chọn duy nhất:

| Chiến lược | Phù hợp khi | Điều cần kiểm tra |
| --- | --- | --- |
| `@BatchMapping` | Cần tải field quan hệ cho một nhóm source object. | Số batch, số key, thứ tự/map kết quả và nullability. |
| DataLoader tường minh | Cần batching, cache theo key hoặc logic loader có thể tái sử dụng. | Request scope, cache invalidation và dispatch. |
| JPA fetch join / EntityGraph | Quan hệ có thể tải hiệu quả cùng truy vấn cha. | Join có nhân bản hàng, phân trang và số lượng dữ liệu. |
| Projection/DTO query | Chỉ cần một tập field cụ thể cho use case. | Cấu trúc query, tính linh hoạt và tái sử dụng. |
| Cache ứng dụng | Dữ liệu ít thay đổi và có thể cache an toàn. | TTL, invalidation, quyền truy cập và tenant isolation. |

Có thể dùng fetch join để giảm số SQL, nhưng join nhiều collection có thể tạo tích Descartes, nhân bản hàng hoặc làm phân trang không đúng như mong muốn. Có thể dùng DataLoader cho quan hệ cần tải riêng. Hãy đo query plan và response thực tế để chọn chiến lược.

## Những kết quả đo dễ gây hiểu nhầm

- **Chỉ đo thời gian:** cache nóng hoặc database nhanh có thể che N+1. Đếm SQL và thay đổi N để kiểm tra xu hướng.
- **Chỉ đo số lần resolver:** GraphQL vẫn resolve field trên từng object; hãy đếm batch method và SQL thay vì kỳ vọng field resolver biến mất.
- **Chỉ đo một request nhỏ:** batch có thể chưa bộc lộ lợi ích ở N nhỏ. Tăng N và dùng dữ liệu đại diện.
- **Để cache dùng chung giữa các test:** cache làm truy vấn sau trông nhanh hơn hoặc ít SQL hơn. Cô lập request và ghi rõ cache state.
- **Không tính truy vấn phụ:** lazy loading từ serializer, logging hoặc code service khác có thể phát sinh SQL ngoài batch method.
- **So sánh operation khác nhau:** số field, filter hoặc pagination khác nhau khiến kết quả không tương đương.
- **Bỏ qua lỗi và timeout:** một batch thất bại nhanh có thể làm latency trông thấp nhưng operation không thành công.

## Checklist kiểm chứng trong dự án

- Chọn một GraphQL operation có quan hệ gây N+1 và lưu lại document/variables cố định.
- Tạo fixture với số object cha và số foreign key duy nhất đã biết.
- Đo baseline SQL count, batch invocation, latency và connection pool.
- Chuyển field resolver sang `@BatchMapping` hoặc DataLoader.
- Chạy lại cùng operation và cùng dữ liệu.
- Xác nhận batch method nhận nhiều source object trong mỗi lần gọi.
- Xác nhận kết quả được ghép đúng source object, kể cả khi database trả thứ tự khác.
- Kiểm tra missing key, nullability, lỗi batch và dữ liệu trùng key.
- Tăng N để kiểm tra số SQL tăng theo số batch thay vì theo từng parent.
- Chạy load test và xem p95/p99, DB time, throughput cùng pool saturation.
- Kiểm tra không có cache hoặc test song song làm sai lệch số đo.

## Ghi nhớ

Đo hiệu quả chống N+1 cần kết hợp số lần gọi batch method, số key mỗi batch, số SQL/JDBC statement và thời gian thực thi. Với resolver riêng từng object, số SQL thường tăng gần `1 + N`; với batching, số SQL quan hệ tăng theo số batch của các key duy nhất. Số cụ thể phụ thuộc batch size, dispatch, cache và cách truy vấn.

Trong Spring for GraphQL, có thể instrument `@BatchMapping` bằng Micrometer, đếm SQL bằng Hibernate Statistics hoặc datasource proxy, rồi dùng `GraphQlTester` để kiểm thử cùng operation trước và sau thay đổi. Sau khi xác nhận số truy vấn giảm, tiếp tục đo latency, query plan, rows, connection pool và p95/p99 dưới tải đại diện. Một giải pháp chỉ được xem là hiệu quả khi vừa giảm truy vấn dư thừa vừa giữ đúng dữ liệu và cải thiện chi phí thực tế.
