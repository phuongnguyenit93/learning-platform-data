# Giới hạn query complexity

## 1. Vì sao cần giới hạn query complexity?

GraphQL cho phép client tự chọn field, quan hệ lồng nhau và số lượng dữ liệu cần lấy trong một operation. Sự linh hoạt này giúp giảm số request từ client, nhưng cũng cho phép một operation yêu cầu lượng công việc rất lớn từ server.

Ví dụ, một client có thể yêu cầu hàng trăm quyển sách, mỗi quyển có nhiều review, mỗi review lại tải người dùng và lịch sử hoạt động. Dù client chỉ gửi một HTTP request, server có thể phải thực hiện nhiều truy vấn database, gọi nhiều service và tạo response lớn.

Query complexity là điểm số ước lượng chi phí của một operation dựa trên các field mà client chọn. Server tính điểm trước khi gọi các DataFetcher. Nếu điểm vượt giới hạn, server từ chối operation và không bắt đầu thực thi resolver.

Giới hạn complexity giúp bảo vệ CPU, bộ nhớ, database, dịch vụ phụ thuộc và thời gian phản hồi. Đây là một lớp demand control của GraphQL API, đặc biệt hữu ích khi API cho phép client bên ngoài tự viết query.

## 2. Phân biệt query complexity, query depth và query breadth

Ba khái niệm này đo những đặc điểm khác nhau của operation:

| Khái niệm | Đo lường | Ví dụ rủi ro |
| --- | --- | --- |
| Query depth | Độ sâu lồng nhau lớn nhất của selection set | `user { friends { friends { friends { ... } } } }` |
| Query breadth | Số field ở cùng cấp hoặc số alias trong một operation | Một query nông nhưng có hàng trăm alias gọi cùng field đắt tiền |
| Query complexity | Tổng chi phí ước lượng của các field, có thể gán trọng số và tính quy mô list | Một field trả về hàng nghìn item, mỗi item lại tải nhiều quan hệ |

Ví dụ query nông nhưng có nhiều field:

```graphql
query Dashboard {
    me {
        id
        name
        email
        orders { id }
        invoices { id }
        notifications { id }
        recommendations { id }
    }
}
```

Độ sâu của query không lớn, nhưng mỗi field có thể gọi một service hoặc truy vấn dữ liệu khác nhau. Giới hạn depth riêng lẻ không thể phản ánh đầy đủ chi phí này.

Ngược lại, một query có ít field nhưng lồng nhiều cấp cũng có thể gây tải lớn. Vì vậy, nên kết hợp complexity với depth, pagination, giới hạn alias/breadth và rate limiting.

## 3. Query complexity được tính như thế nào?

GraphQL specification không quy định một công thức complexity bắt buộc. Điểm số là chính sách do server lựa chọn, dựa trên cấu trúc schema và chi phí thực tế của các field.

GraphQL Java cung cấp `FieldComplexityCalculator` để tính chi phí của từng field. Công thức mặc định của `MaxQueryComplexityInstrumentation` là:

\[
C(field) = 1 + \sum C(child)
\]

Mỗi field có chi phí cơ bản là 1, cộng với tổng chi phí của các field con.

Ví dụ:

```graphql
query {
    book {
        id
        title
        author {
            name
        }
    }
}
```

Tính từ field sâu nhất:

| Field | Cách tính | Complexity |
| --- | --- | ---: |
| `name` | `1` | 1 |
| `author` | `1 + name` | 2 |
| `id` | `1` | 1 |
| `title` | `1` | 1 |
| `book` | `1 + id + title + author` | 5 |

Tổng complexity của operation là 5 theo công thức mặc định này. Điểm số không phải thời gian chạy tính bằng millisecond; nó là đơn vị tương đối dùng để so sánh và áp dụng giới hạn.

## 4. Vì sao công thức mặc định chưa đủ cho field dạng List?

Một field trả về object đơn và một field trả về danh sách 1.000 object không có cùng chi phí, dù cả hai có thể chỉ được tính là một field theo công thức mặc định.

Ví dụ:

```graphql
type Query {
    books(first: Int! = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews(first: Int! = 10): [Review!]!
}
```

Query:

```graphql
query {
    books(first: 100) {
        id
        title
        reviews(first: 20) {
            id
            rating
        }
    }
}
```

Nếu chỉ đếm số field, server có thể đánh giá query này khá rẻ. Nhưng trên thực tế, server có thể phải xử lý đến 100 sách và tối đa 2.000 review. Số lượng phần tử và field con làm chi phí tăng theo quy mô danh sách.

Một cost model thực tế nên xét:

- Số lượng item tối đa mà argument pagination cho phép.
- Chi phí cơ bản của từng field.
- Chi phí của các field con trên mỗi item.
- Những field gọi hệ thống ngoài hoặc truy vấn nặng.
- Những field có thể tạo ra danh sách lồng nhau.

Với list, có thể dùng công thức ước lượng:

\[
C(list) = 1 + pageSize \times (1 + C(children))
\]

Đây là công thức ví dụ cho ứng dụng, không phải quy tắc bắt buộc của GraphQL. Khi có list lồng nhau, phép nhân được áp dụng ở từng cấp nên điểm số phản ánh sự tăng trưởng của số item.

## 5. Dùng `MaxQueryComplexityInstrumentation`

GraphQL Java cung cấp `MaxQueryComplexityInstrumentation` trong package `graphql.analysis`. Instrumentation này phân tích operation và hủy execution nếu complexity vượt giới hạn.

Ví dụ cấu hình trực tiếp trong GraphQL Java:

```java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.GraphQL;

GraphQL graphQL = GraphQL.newGraphQL(schema)
    .instrumentation(new MaxQueryComplexityInstrumentation(500))
    .build();
```

Trong ví dụ, operation có complexity lớn hơn 500 sẽ bị từ chối. Operation có điểm bằng 500 vẫn nằm trong giới hạn.

Khi complexity vượt ngưỡng, GraphQL Java phát sinh lỗi abort execution. Response có thể chứa error tương tự:

```json
{
  "errors": [
    {
      "message": "maximum query complexity exceeded 620 > 500",
      "extensions": {
        "classification": "ExecutionAborted"
      }
    }
  ]
}
```

Thông báo cụ thể có thể thay đổi theo phiên bản GraphQL Java hoặc cách ứng dụng tùy chỉnh instrumentation. Điểm quan trọng là operation bị dừng trước khi các resolver bắt đầu truy cập dữ liệu.

## 6. Tích hợp instrumentation trong Spring Boot

Spring Boot tự cấu hình `GraphQlSource` và phát hiện các bean triển khai `graphql.execution.instrumentation.Instrumentation`. Vì vậy, trong ứng dụng Spring for GraphQL dùng Boot, có thể khai báo `MaxQueryComplexityInstrumentation` thành một bean.

```java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlSecurityConfig {

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(500);
    }
}
```

Spring Boot đưa instrumentation bean vào `GraphQlSource` trong quá trình auto-configuration. Không cần tự tạo `GraphQL` hoặc thay thế `ExecutionGraphQlService` chỉ để bật giới hạn complexity.

Nếu ứng dụng không dùng Spring Boot auto-configuration, hãy cấu hình instrumentation qua `GraphQlSource.Builder.instrumentation(...)` khi tạo `GraphQlSource`.

Lưu ý về phiên bản: Spring Boot 3.x và 4.x có thể thay đổi package của một số API tùy chỉnh `GraphQlSource`. Cách đăng ký bean `Instrumentation` giúp tránh phụ thuộc trực tiếp vào package của `GraphQlSourceBuilderCustomizer` trong ví dụ cơ bản.

## 7. Giới hạn cả query depth

`MaxQueryComplexityInstrumentation` và `MaxQueryDepthInstrumentation` giải quyết hai vấn đề khác nhau. Có thể đăng ký cả hai để chặn operation vừa quá sâu vừa quá tốn kém.

```java
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueryGuardConfig {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(500);
    }
}
```

Spring Boot phát hiện các instrumentation bean và kết hợp chúng trong GraphQL execution. Nếu operation có depth lớn hơn 8 hoặc complexity lớn hơn 500, instrumentation tương ứng có thể từ chối operation.

Giới hạn depth không nên được đặt quá thấp đến mức chặn những quan hệ hợp lệ của schema. Hãy đo độ sâu thường gặp từ các operation thực tế, sau đó chọn ngưỡng có khoảng an toàn cho các use case hợp lệ.

## 8. Tùy chỉnh chi phí bằng `FieldComplexityCalculator`

Trong nhiều ứng dụng, công thức mặc định chưa đủ vì một số field tốn kém hơn field khác. GraphQL Java cho phép truyền `FieldComplexityCalculator` vào constructor của `MaxQueryComplexityInstrumentation`.

Calculator nhận hai giá trị:

- `FieldComplexityEnvironment`: thông tin field hiện tại, parent type, định nghĩa field và arguments.
- `childComplexity`: tổng điểm complexity của các field con.

Ví dụ, field `recommendations` cần gọi nhiều dịch vụ và được gán chi phí cơ bản cao hơn field thông thường:

```java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

FieldComplexityCalculator calculator = (environment, childComplexity) -> {
    String fieldName = environment.getFieldDefinition().getName();

    if ("recommendations".equals(fieldName)) {
        return 25 + childComplexity;
    }

    return 1 + childComplexity;
};

Instrumentation instrumentation =
    new MaxQueryComplexityInstrumentation(500, calculator);
```

Trong ví dụ, mỗi lần chọn field `recommendations` có cost cơ bản 25. Nếu field có các field con, chi phí của chúng được cộng thêm.

Nên xác định trọng số dựa trên chi phí thực tế của resolver: số lần gọi database, thời gian gọi service bên ngoài, lượng dữ liệu trả về và mức sử dụng CPU. Trọng số cần được hiệu chỉnh theo telemetry và tải production, không chọn tùy ý.

## 9. Tính complexity theo pagination argument

Để phản ánh quy mô dữ liệu, calculator có thể đọc argument pagination từ `FieldComplexityEnvironment.getArguments()`.

Ví dụ schema:

```graphql
type Query {
    books(first: Int! = 20): [Book!]!
}
```

Calculator:

Thay bean complexity cơ bản ở phần trước bằng calculator tùy chỉnh này; không khai báo hai bean cùng tên.

```java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlComplexityConfig {

    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE_SIZE = 100;

    @Bean
    Instrumentation queryComplexityInstrumentation() {
        FieldComplexityCalculator calculator = (environment, childComplexity) -> {
            String parentType = environment.getParentType().getName();
            String fieldName = environment.getFieldDefinition().getName();

            if ("Query".equals(parentType) && "books".equals(fieldName)) {
                Object rawFirst = environment.getArguments().get("first");
                int requested = rawFirst instanceof Number number
                    ? number.intValue()
                    : DEFAULT_PAGE_SIZE;

                int pageSize = Math.max(0, Math.min(requested, MAX_PAGE_SIZE));
                return 1 + pageSize * (1 + childComplexity);
            }

            return 1 + childComplexity;
        };

        return new MaxQueryComplexityInstrumentation(500, calculator);
    }
}
```

Với field `books`, chi phí được tính dựa trên số item yêu cầu và tổng chi phí field con. Những field khác vẫn dùng công thức mặc định.

Giới hạn `MAX_PAGE_SIZE` trong calculator phải khớp với giới hạn thực tế ở resolver hoặc service. Nếu calculator chỉ giới hạn điểm số nhưng resolver vẫn cho phép lấy 10.000 item, mô hình sẽ đánh giá thấp chi phí thực tế. Hãy kiểm tra argument `first` bằng validation hoặc ép giới hạn ở service trước khi truy vấn database.

Khi có nhiều list field như `books`, `reviews`, `comments`, hãy áp dụng cost model cho từng field. Với list lồng nhau, phép nhân theo page size ở từng cấp giúp điểm số tăng nhanh hơn khi client yêu cầu nhiều tầng dữ liệu.

## 10. Xử lý field có chi phí rất cao

Một số field có thể rất tốn kém dù chỉ trả về một object. Ví dụ:

- `recommendations`: chạy thuật toán xếp hạng hoặc gọi mô hình gợi ý.
- `financialReport`: tổng hợp dữ liệu từ nhiều bảng và nhiều kỳ kế toán.
- `search`: truy vấn full-text hoặc gọi search cluster.
- `analytics`: tính toán thống kê trên lượng dữ liệu lớn.
- `externalProfile`: gọi một dịch vụ bên ngoài có latency cao.

Có thể gán cost cơ bản riêng cho các field đó:

```java
private static int baseCost(String parentType, String fieldName) {
    if ("Query".equals(parentType) && "financialReport".equals(fieldName)) {
        return 80;
    }

    if ("Query".equals(parentType) && "recommendations".equals(fieldName)) {
        return 30;
    }

    if ("Query".equals(parentType) && "search".equals(fieldName)) {
        return 15;
    }

    return 1;
}
```

Calculator có thể gọi `baseCost(...)` rồi cộng `childComplexity`. Việc phân biệt theo parent type giúp tránh áp dụng cùng một trọng số cho các field trùng tên nhưng khác nghiệp vụ.

Nếu chi phí còn phụ thuộc argument, hãy xét thêm các argument đó. Ví dụ `analytics(period: YEAR)` có thể đắt hơn `analytics(period: DAY)`. Không đưa dữ liệu nhạy cảm hoặc thông tin authorization vào cost model nếu không cần thiết.

## 11. Alias và fragment ảnh hưởng đến complexity

GraphQL cho phép gọi cùng một field nhiều lần bằng alias:

```graphql
query Compare {
    small: books(first: 10) {
        id
    }

    large: books(first: 100) {
        id
        reviews(first: 20) {
            rating
        }
    }
}
```

Hai alias `small` và `large` là hai lựa chọn field riêng trong operation. Chúng có thể tạo ra hai lần gọi resolver với argument khác nhau. Cost model cần tính cả hai, không chỉ nhìn tên field `books` một lần.

Fragment giúp tái sử dụng selection set:

```graphql
fragment BookDetails on Book {
    id
    title
    author {
        name
    }
}

query {
    books(first: 50) {
        ...BookDetails
    }
}
```

Fragment không phải một resolver mới. Các field trong fragment vẫn là phần selection set của operation và cần được tính trong complexity. Khi kiểm thử cost model, nên có ca alias, named fragment và inline fragment để bảo đảm phép phân tích bao quát các cấu trúc query mà client sử dụng.

## 12. Complexity limit không thay thế pagination và các guardrail khác

Không nên chỉ bật `MaxQueryComplexityInstrumentation` rồi cho phép mọi list trả về không giới hạn. Cost model là ước lượng; pagination và validation mới bảo đảm giới hạn dữ liệu thực tế.

Các lớp bảo vệ nên kết hợp:

| Biện pháp | Mục đích |
| --- | --- |
| Pagination bắt buộc cho list lớn | Giới hạn số item mà một field có thể trả về |
| `MaxQueryComplexityInstrumentation` | Giới hạn tổng cost ước lượng của operation |
| `MaxQueryDepthInstrumentation` | Chặn query lồng quá nhiều cấp |
| Giới hạn alias/breadth | Ngăn quá nhiều field hoặc alias ở cùng cấp |
| Giới hạn số operation trong HTTP batch | Tránh gửi nhiều operation trong một request batch |
| Rate limiting | Giới hạn tốc độ hoặc ngân sách truy vấn theo user/API key |
| Persisted/trusted documents | Chỉ cho phép operation đã được duyệt |
| Timeout và giới hạn tài nguyên | Hạn chế thời gian chạy và tài nguyên bị chiếm giữ |

GraphQL Java cung cấp instrumentation cho complexity và depth. Các chính sách breadth, alias hoặc số operation batch có thể cần custom instrumentation, validation riêng hoặc giới hạn ở transport/gateway. Không giả định hai instrumentation mặc định đã xử lý toàn bộ các trường hợp này.

## 13. DataLoader giảm N+1 nhưng không làm query rẻ đi

DataLoader và `@BatchMapping` giảm số lần gọi backend bằng cách gom nhiều yêu cầu dữ liệu thành một batch. Chúng xử lý vấn đề N+1, nhưng không nhất thiết làm giảm tổng số object mà server phải tải và trả về.

Ví dụ, một query yêu cầu 1.000 sách và mỗi sách có 20 review. DataLoader có thể giảm hàng nghìn truy vấn riêng lẻ xuống một vài batch query, nhưng server vẫn phải xử lý và serialize tối đa 20.000 review.

Vì vậy:

- DataLoader giảm round trip đến backend.
- Pagination giới hạn số item.
- Complexity ước lượng tổng công việc của operation.
- Depth giới hạn mức lồng nhau.
- Timeout và rate limit bảo vệ tài nguyên theo thời gian.

Các biện pháp này bổ sung cho nhau. Không nên giảm cost của list field chỉ vì resolver đã dùng DataLoader.

## 14. Chọn ngưỡng complexity như thế nào?

Không có một ngưỡng phù hợp cho mọi GraphQL API. Ngưỡng phụ thuộc vào schema, cách resolver truy cập dữ liệu, phần cứng, database, mức độ sử dụng và latency mục tiêu.

Quy trình thiết lập:

1. Thu thập các operation hợp lệ đang được client sử dụng.
2. Đo latency, số truy vấn database, số item trả về và thời gian gọi service ngoài.
3. Thiết kế trọng số cơ bản cho field và list field.
4. Tính complexity của các operation hợp lệ phổ biến.
5. Chọn ngưỡng đủ cho các operation hợp lệ, đồng thời chặn các query có cost quá cao.
6. Chạy thử ở staging hoặc chế độ quan sát trước khi bật chặn ở production.
7. Theo dõi số request bị từ chối và điều chỉnh cost model khi schema thay đổi.

Nên cân nhắc các nhóm client khác nhau. Client nội bộ có thể dùng persisted documents và ngân sách riêng; client public có thể cần ngưỡng thấp hơn, pagination chặt hơn và rate limit theo API key.

Nếu chỉ dùng một ngưỡng toàn cục, một số operation hợp lệ nhưng đặc biệt nặng có thể bị từ chối. Có thể dùng persisted operation, custom policy hoặc cost budget theo user/role để quản lý các trường hợp đó.

## 15. Kiểm thử query complexity bằng `ExecutionGraphQlServiceTester`

`ExecutionGraphQlServiceTester` là một biến thể của `GraphQlTester`, cho phép gửi operation trực tiếp vào `ExecutionGraphQlService` mà không cần dựng HTTP client. Cách này phù hợp để xác nhận instrumentation chặn operation trước khi resolver chạy.

Ví dụ dùng cấu hình ở phần pagination, trong đó complexity limit là 500 và `first` bị giới hạn tối đa 100 item:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

@SpringBootTest
class QueryComplexityTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    @Test
    void rejectsOperationAboveComplexityLimit() {
        ExecutionGraphQlServiceTester tester =
            ExecutionGraphQlServiceTester.create(executionGraphQlService);

        tester.document("""
            query {
                books(first: 100) {
                    id
                    title
                    author {
                        name
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).anySatisfy(error ->
                assertThat(error.getMessage())
                    .contains("maximum query complexity exceeded")
            ));
    }
}
```

Với calculator ở phần pagination, operation trên có cost ước lượng 501 và vượt giới hạn 500. Trong dự án thực tế, hãy kiểm tra error classification hoặc extension code ổn định nếu ứng dụng có chuẩn hóa lỗi; không phụ thuộc hoàn toàn vào nội dung message mặc định.

Ngoài response, nên xác nhận resolver/service không được gọi khi operation bị abort. Có thể dùng spy hoặc counter ở service trong test context để kiểm tra điều này.

Các ca kiểm thử nên có:

- Operation có complexity nhỏ hơn ngưỡng được thực thi.
- Operation có complexity bằng ngưỡng được chấp nhận.
- Operation có complexity lớn hơn ngưỡng bị từ chối.
- Query sâu vượt giới hạn depth bị từ chối.
- List field với pagination nhỏ và lớn có điểm khác nhau.
- Alias gọi cùng field nhiều lần được tính riêng.
- Fragment và inline fragment được phân tích đúng.
- Field có cost cao làm operation vượt ngưỡng.
- Argument pagination vượt mức tối đa bị validation/service từ chối.
- Service không chạy khi instrumentation abort operation.

## 16. Theo dõi và vận hành complexity limit

Khi đưa giới hạn vào production, cần quan sát cả request được chấp nhận và request bị từ chối.

Nên ghi nhận:

- Operation name hoặc persisted document ID.
- Complexity ước lượng và giới hạn áp dụng.
- Query depth và số field/alias nếu có thể đo.
- Client/API key hoặc nhóm quyền theo chính sách bảo mật.
- Số lượng request bị abort.
- Latency, số truy vấn database và kích thước response của operation hợp lệ.

Không log toàn bộ query hoặc variables nếu chúng có thể chứa thông tin nhạy cảm. Với production, ưu tiên operation name, hash/persisted ID và metadata đã được lọc.

Khi schema thay đổi, cost model cũng cần được cập nhật. Một field mới gọi dịch vụ ngoài hoặc một list field mới có thể làm tăng chi phí đáng kể dù query depth không thay đổi.

Nên xem xét các operation bị từ chối thường xuyên để phân biệt hai tình huống: client gửi query bất thường hoặc ngưỡng complexity đang quá thấp so với use case hợp lệ. Đừng tăng ngưỡng chỉ để làm một test hoặc một client hết lỗi mà chưa kiểm tra cost thực tế.

## 17. Các lỗi thường gặp khi giới hạn query complexity

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Instrumentation không hoạt động | Chưa đăng ký bean `Instrumentation` hoặc `GraphQlSource` tùy chỉnh bỏ qua bean | Kiểm tra Boot auto-configuration và GraphQlSource |
| Query lớn vẫn được thực thi | Ngưỡng quá cao hoặc cost model chỉ đếm field cơ bản | Hiệu chỉnh trọng số và tính pagination argument |
| List 1.000 item có cost gần bằng list 10 item | Chưa đưa page size vào calculator | Dùng `FieldComplexityCalculator` để tính theo số item |
| Query nông nhưng gây tải lớn | Chỉ bật depth limit | Bật complexity, breadth/alias limit và pagination |
| Query lồng sâu vẫn chạy | Chỉ bật complexity với cost field thấp | Bổ sung `MaxQueryDepthInstrumentation` |
| Query hợp lệ bị từ chối | Ngưỡng không phản ánh use case hoặc field bị gán cost quá cao | Đo operation thực tế và điều chỉnh cost model |
| Resolver vẫn tải quá nhiều dữ liệu | Calculator giới hạn điểm nhưng service không giới hạn page size | Enforce page size trong validation và service |
| DataLoader khiến cost bị đánh giá thấp | Giảm cost vì số round trip ít | Tính theo số item và lượng dữ liệu, không chỉ số truy vấn |
| Alias gọi field nặng nhiều lần nhưng không bị chặn | Cost model hoặc guardrail không tính alias/breadth | Kiểm thử alias và bổ sung giới hạn phù hợp |
| Lỗi trả quá nhiều chi tiết nội bộ | Đưa exception mặc định ra client | Chuẩn hóa GraphQL error và log chi tiết ở server |

## 18. Checklist triển khai query complexity limit

- [ ] Xác định các field có chi phí cao và list field có thể trả nhiều dữ liệu.
- [ ] Thiết kế công thức complexity phù hợp với schema.
- [ ] Đăng ký `MaxQueryComplexityInstrumentation` trong GraphQL execution.
- [ ] Dùng `FieldComplexityCalculator` khi cần trọng số riêng hoặc tính theo pagination.
- [ ] Đăng ký `MaxQueryDepthInstrumentation` để giới hạn query lồng sâu.
- [ ] Bắt buộc pagination cho list field có khả năng tăng lớn.
- [ ] Enforce page size trong validation hoặc service, không chỉ trong cost calculator.
- [ ] Kiểm tra alias, fragment và field có cost cao.
- [ ] Bổ sung breadth, batch-operation và rate limit khi phù hợp.
- [ ] Không xem DataLoader là biện pháp thay thế complexity limit.
- [ ] Kiểm thử operation dưới, bằng và vượt ngưỡng.
- [ ] Xác nhận resolver không chạy khi operation bị abort.
- [ ] Theo dõi complexity và request bị từ chối trong production.
- [ ] Điều chỉnh ngưỡng khi schema hoặc workload thay đổi.

## Kết luận

Giới hạn query complexity giúp Spring for GraphQL kiểm soát lượng công việc mà client yêu cầu trong một operation. GraphQL Java cung cấp `MaxQueryComplexityInstrumentation` để từ chối query vượt ngưỡng và `FieldComplexityCalculator` để gán chi phí theo field, argument và số lượng item. Spring Boot có thể tự phát hiện các bean `Instrumentation` và đưa chúng vào `GraphQlSource`.

Một chính sách hiệu quả cần kết hợp complexity với query depth, pagination, giới hạn alias/breadth, rate limiting và persisted documents. Hãy tính chi phí list theo page size, gán trọng số cao hơn cho field gọi dịch vụ nặng, enforce giới hạn dữ liệu ở service và kiểm thử để chắc chắn resolver không chạy khi query bị abort. Theo dõi workload thực tế để điều chỉnh cost model và ngưỡng theo sự phát triển của schema.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — FieldComplexityCalculator API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/FieldComplexityCalculator.html)
- [GraphQL — Security and Demand Control](https://graphql.org/learn/security/)
- [Spring for GraphQL — Testing with GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
