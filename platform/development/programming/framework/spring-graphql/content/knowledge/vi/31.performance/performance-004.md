# Query depth limit

Trong Spring for GraphQL, client gửi operation theo schema SDL và có thể kết hợp Query, Mutation, Subscription với các field lồng nhau. DataFetcher, annotated controller và DataLoader phối hợp tạo response. Khi schema mô tả quan hệ nhiều tầng, query depth limit là một guardrail hiệu năng giúp giữ cấu trúc operation trong giới hạn mà backend có thể xử lý.

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích query depth và mối liên hệ giữa độ sâu với chi phí thực thi GraphQL.
- Tính depth của operation có field lồng nhau, fragment và nhiều nhánh.
- Phân biệt query sâu với query có fan-out lớn hoặc resolver đắt tiền.
- Dùng MaxQueryDepthInstrumentation để đặt giới hạn trong Spring for GraphQL.
- Chọn ngưỡng dựa trên workload hợp lệ và kết quả đo hiệu năng.
- Kết hợp depth limit với pagination, amount limit, query complexity và DataLoader.
- Kiểm thử ranh giới và benchmark để đánh giá hiệu quả của giới hạn.
- Theo dõi query bị từ chối mà không tạo metric cardinality cao.

## 1. Query depth là gì?

GraphQL cho phép client chọn field lồng nhau theo cấu trúc schema. Một operation bắt đầu từ root type như Query hoặc Mutation, sau đó đi qua các object field để lấy dữ liệu liên quan.

Ví dụ:

~~~graphql
query BookDetails {
  bookById(id: "b-01") {
    id
    title
    author {
      name
      organization {
        name
      }
    }
  }
}
~~~

Query depth là số cấp field lồng nhau trên đường đi sâu nhất của operation. Theo cách đếm của GraphQL Java MaxQueryDepthInstrumentation, root field bắt đầu ở depth 1 và mỗi field con tăng thêm một cấp.

| Field trên đường đi sâu nhất | Depth |
|---|---:|
| Query.bookById | 1 |
| Book.author | 2 |
| Author.organization | 3 |
| Organization.name | 4 |

Depth tối đa của operation trên là 4. Các scalar field khác như Book.id và Book.title không làm tăng đường đi sâu nhất vì chúng không có field con.

Depth limit đặt một ngưỡng cho cấu trúc lồng nhau này. Nếu operation vượt ngưỡng, GraphQL runtime từ chối operation trước khi chạy các DataFetcher của nó.

## 2. Vì sao query depth ảnh hưởng đến hiệu năng?

Schema GraphQL thường mô tả quan hệ giữa các object. Một Book có Author, Author có Books, Book có Reviews, Review lại có Author hoặc Replies. Client có thể đi theo các quan hệ đó qua nhiều cấp.

Ví dụ schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  author: Author
  reviews(first: Int = 10): [Review!]!
}

type Author {
  id: ID!
  books(first: Int = 10): [Book!]!
}

type Review {
  id: ID!
  author: Author
  replies(first: Int = 5): [Review!]!
}
~~~

Một query có thể lặp qua quan hệ Books, Author, Reviews và Replies. Mỗi cấp có thể kích hoạt thêm DataFetcher, service call, database query hoặc serialization.

Khi depth tăng, có thể tăng:

- Số tầng resolver cần thực thi.
- Số lần chuyển tiếp giữa các service hoặc repository.
- Số object cần giữ trong bộ nhớ để tạo response.
- Số field cần serialize.
- Khả năng query đi sâu vào các quan hệ đệ quy trong schema.

Depth limit là một guardrail giúp giới hạn độ sâu tối đa mà client có thể yêu cầu. Nó hữu ích khi schema có quan hệ đệ quy hoặc các nhánh dữ liệu có thể mở rộng qua nhiều tầng.

Tuy nhiên, depth chỉ đo cấu trúc lồng nhau. Nó không trực tiếp đo số object, số database round trip hay thời gian của từng resolver. Để hiểu hiệu năng, cần xem thêm fan-out và chi phí field.

## 3. Depth không đồng nghĩa với query cost

Hai query có cùng depth có thể có chi phí rất khác nhau.

Query A:

~~~graphql
query {
  bookById(id: "b-01") {
    reviews(first: 50) {
      author {
        name
      }
    }
  }
}
~~~

Query B:

~~~graphql
query {
  books(first: 100) {
    reviews(first: 50) {
      author {
        name
      }
    }
  }
}
~~~

Cả hai có đường đi field lồng nhau tối đa 4 cấp tính từ root. Query A chỉ tải reviews của một Book; Query B có thể tạo ra tối đa 100 Book và 5.000 Review nếu server chấp nhận các page size đó. Số object và số lần resolve có thể lớn hơn nhiều.

Có thể hình dung chi phí gần đúng theo số object ở từng cấp:

~~~text
N(next) = N(current) * fanOut(current)
~~~

Trong đó N(current) là số object ở cấp hiện tại, fanOut(current) là số phần tử trung bình của field list tiếp theo, và N(next) là số object ở cấp kế tiếp.

Với Query B:

- Root books(first: 100) tạo tối đa 100 Book.
- Mỗi Book có tối đa 50 Review.
- Tổng số Review tối đa là 100 x 50 = 5.000.
- Field author có thể được resolve cho hàng nghìn Review.

Depth vẫn thấp, nhưng fan-out lớn làm chi phí tăng nhanh.

Đây là lý do depth limit không thể thay thế amount limit hoặc query complexity analysis.

## 4. Mô hình chi phí theo depth, fan-out và resolver

Để phân tích một query, có thể dùng mô hình tư duy:

~~~text
W ~= sum(N[i] * C[i]), for i = 1..D
~~~

Trong đó:

- D là depth tối đa.
- N[i] là số lần một cấp field được resolve.
- C[i] là chi phí trung bình của resolver ở cấp đó.

Đây là mô hình ước lượng để so sánh workload, không phải công thức nội bộ mà GraphQL Java sử dụng.

Một query sâu có thể tạo nhiều tầng xử lý tuần tự. Một query nông nhưng có list lớn có thể tạo rất nhiều lần resolve song song. Một field gọi API bên ngoài chậm có thể chiếm phần lớn thời gian dù query chỉ có depth 2.

| Đặc điểm query | Rủi ro hiệu năng | Biện pháp phù hợp |
|---|---|---|
| Nhiều cấp object lồng nhau | Quá nhiều tầng resolver | Depth limit |
| List có page size lớn | Quá nhiều object | Amount limit, pagination |
| Nhiều field tốn kém | Tổng chi phí resolver cao | Query complexity |
| Nhiều field quan hệ gọi DB riêng | N+1 database calls | DataLoader, @BatchMapping |
| Nhiều alias cùng field | Nhiều nhánh thực thi | Giới hạn field/alias, complexity |
| Downstream phản hồi chậm | Request kéo dài | Timeout, bulkhead, cache |

Khi thiết kế chính sách, hãy xác định loại chi phí cần kiểm soát trước khi chọn công cụ.

## 5. Tính depth với nested fields

Giả sử schema:

~~~graphql
type Query {
  order(id: ID!): Order
}

type Order {
  customer: Customer
  items: [OrderItem!]!
}

type Customer {
  profile: CustomerProfile
}

type CustomerProfile {
  address: Address
}

type Address {
  city: String!
}
~~~

Query:

~~~graphql
query {
  order(id: "o-01") {
    customer {
      profile {
        address {
          city
        }
      }
    }
    items {
      id
    }
  }
}
~~~

Đường đi sâu nhất:

| Field | Depth |
|---|---:|
| Query.order | 1 |
| Order.customer | 2 |
| Customer.profile | 3 |
| CustomerProfile.address | 4 |
| Address.city | 5 |

Nhánh items.id chỉ có depth 3, nên không quyết định depth tối đa. Depth limit luôn quan tâm đường đi sâu nhất trong operation.

Khi đánh giá một query thực tế, hãy lần theo từng nhánh từ root tới field sâu nhất. Không cộng số lượng field ở các nhánh song song thành depth.

## 6. Fragment và inline fragment

Fragment cho phép tái sử dụng selection set. Fragment không tạo thêm một cấp field chỉ vì có cú pháp fragment; field bên trong fragment được tính theo vị trí mà fragment được sử dụng.

~~~graphql
fragment CustomerDetails on Customer {
  profile {
    address {
      city
    }
  }
}

query OrderDetails {
  order(id: "o-01") {
    customer {
      ...CustomerDetails
    }
  }
}
~~~

Đường đi sâu nhất vẫn là:

1. Query.order: depth 1.
2. Order.customer: depth 2.
3. Customer.profile: depth 3.
4. CustomerProfile.address: depth 4.
5. Address.city: depth 5.

Inline fragment cũng không tạo thêm cấp field:

~~~graphql
query {
  search {
    ... on Book {
      author {
        organization {
          name
        }
      }
    }
  }
}
~~~

Depth được tính theo các field trong nhánh thực thi sau khi áp dụng fragment. Hãy dùng GraphQL AST và instrumentation có sẵn để phân tích query thay vì tự đếm dấu ngoặc hoặc số dòng trong document.

## 7. Alias tạo thêm nhánh nhưng không tăng depth

Alias đổi tên response key của field. Alias không thêm một cấp lồng nhau, vì vậy không tự làm tăng depth.

~~~graphql
query {
  first: bookById(id: "b-01") {
    author {
      name
    }
  }
  second: bookById(id: "b-02") {
    author {
      name
    }
  }
}
~~~

Hai nhánh có cùng depth. Nhưng server có thể phải resolve bookById hai lần với hai argument khác nhau.

Một client có thể tạo nhiều alias:

~~~graphql
query {
  a: bookById(id: "b-01") { title }
  b: bookById(id: "b-02") { title }
  c: bookById(id: "b-03") { title }
  d: bookById(id: "b-04") { title }
}
~~~

Depth thấp không đồng nghĩa số resolver thấp. Nếu endpoint cho phép document tùy ý, cần xem xét giới hạn tổng field/alias hoặc query complexity cùng với depth limit.

## 8. Quan hệ đệ quy trong schema

Một số schema có quan hệ đệ quy tự nhiên:

~~~graphql
type Category {
  id: ID!
  name: String!
  parent: Category
  children(first: Int = 20): [Category!]!
}
~~~

Root query cần expose danh sách category:

~~~graphql
type Query {
  categories: [Category!]!
}
~~~

Client có thể yêu cầu cây category sâu:

~~~graphql
query {
  categories {
    children {
      children {
        children {
          children {
            name
          }
        }
      }
    }
  }
}
~~~

Nếu không có depth limit, client có thể tiếp tục lặp field children qua nhiều tầng. Mỗi cấp có thể mở rộng số object theo fan-out của danh sách con.

Với quan hệ đệ quy, nên kết hợp:

- Depth limit để giới hạn số tầng.
- Pagination hoặc amount limit cho mỗi danh sách children.
- Resolver tối ưu để không truy vấn database riêng cho từng node.
- DataLoader hoặc batch query khi cần tải quan hệ.
- Timeout và giới hạn tài nguyên ở tầng request.

Depth limit giúp giới hạn hình dạng cây, nhưng không bảo đảm cây có ít node nếu mỗi node có rất nhiều children.

## 9. Cấu hình MaxQueryDepthInstrumentation trong Spring for GraphQL

GraphQL Java cung cấp MaxQueryDepthInstrumentation để giới hạn độ sâu của operation. Spring Boot có thể tích hợp các bean Instrumentation vào GraphQL runtime.

Ví dụ đặt depth tối đa là 6:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlPerformanceConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(6);
    }
}
~~~

Trong ví dụ này:

- Query có depth nhỏ hơn 6 được phép qua depth check.
- Query có depth bằng 6 vẫn được phép.
- Query có depth lớn hơn 6 bị từ chối.

Spring Boot phát hiện instrumentation bean khi xây dựng GraphQL runtime. Nếu ứng dụng tự tạo GraphQlSource, cần thêm instrumentation vào builder cùng với instrumentation hiện có.

Không tạo instrumentation trùng lặp nếu Spring Boot auto-configuration đã cung cấp nó. Khi ứng dụng có tracing hoặc instrumentation tùy chỉnh, cần bảo đảm chúng vẫn được kết hợp sau khi thêm depth limit.

Ngưỡng 6 chỉ là ví dụ. Hãy đo các operation hợp lệ trước khi chọn giá trị production.

## 10. Depth check chạy trước DataFetcher

Depth instrumentation phân tích GraphQL operation trước khi các field resolver thực thi. Nếu query vượt giới hạn, GraphQL Java abort operation và không gọi DataFetcher của nó.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[HTTP GraphQL request] --> B[Parse document]
    B --> C[Validate schema and variables]
    C --> D[Depth instrumentation]
    D -->|Within budget| E[Execute DataFetchers]
    D -->|Over budget| F[Abort execution]
    E --> G[GraphQL response]
    F --> G
~~~

Depth check giúp tránh chi phí thực thi resolver cho operation vượt ngưỡng. Tuy vậy, server vẫn phải nhận request, parse document và thực hiện các bước xử lý cần thiết trước khi từ chối operation.

Vì thế, depth limit cần đi cùng giới hạn request body và rate limit. Một document cực lớn nhưng chỉ có các field ở cùng một cấp có thể không vượt depth limit, nhưng vẫn tiêu tốn CPU và bộ nhớ ở bước parse/validation.

## 11. Chọn ngưỡng dựa trên workload thực tế

Không có một giá trị depth phù hợp cho mọi GraphQL API. Ngưỡng nên dựa trên operation hợp lệ mà client thực sự sử dụng và ngân sách hiệu năng của backend.

Quy trình chọn ngưỡng:

1. Thu thập operation từ các client hoặc persisted query registry.
2. Tính depth của từng operation hợp lệ.
3. Xác định operation sâu nhất có nhu cầu nghiệp vụ thật.
4. Đo thời gian, số resolver, số object và database calls của các operation đó.
5. Chọn ngưỡng bao phủ các operation hợp lệ, có khoảng dự phòng phù hợp.
6. Kiểm thử operation ngay dưới, bằng và vượt ngưỡng.
7. Theo dõi số query bị từ chối sau khi triển khai.

Ví dụ, nếu operation hợp lệ sâu nhất có depth 5, có thể bắt đầu thử ngưỡng 6 hoặc 7. Không nên chọn một giá trị lớn chỉ để tránh ảnh hưởng client mà chưa đo chi phí.

Với API có nhiều client, cần thống kê operation theo use case. Một màn hình quản trị có thể cần query sâu hơn màn hình danh sách công khai. Nếu cùng một schema và endpoint, global depth limit cần bao phủ tất cả use case được hỗ trợ.

Khi schema thay đổi, hãy đánh giá lại các operation đã đăng ký. Thêm một quan hệ object mới có thể khiến một operation cũ sâu hơn dự kiến.

## 12. Đặt page size giới hạn ở mọi field list

Depth limit không đọc page size để xác định số phần tử. Vì vậy, mọi field list có thể tạo nhiều object cần giới hạn số lượng.

Ví dụ resolver:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    int pageSize = first == null ? 20 : first;

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException(
                "first must be between 1 and 100");
    }

    return bookService.findFirst(pageSize);
}
~~~

Với nested list, áp dụng giới hạn tương tự:

~~~graphql
type Book {
  reviews(first: Int = 10): [Review!]!
}
~~~

Không chỉ giới hạn root list. Một query có thể lấy 20 Book và yêu cầu 10.000 Review cho mỗi Book nếu resolver không kiểm tra argument.

Nên đặt giới hạn ở service/repository hoặc một lớp dùng chung để mọi entry point đều tuân thủ. GraphQL controller có thể validate đầu vào, nhưng service vẫn cần bảo vệ chính sách truy vấn dữ liệu.

Với tập dữ liệu lớn, ưu tiên cursor pagination thay vì trả một list không giới hạn.

## 13. Khi nào cần query complexity thay cho depth?

Depth limit chỉ giới hạn số tầng field lồng nhau. Nếu chi phí của field khác nhau đáng kể, cần query complexity analysis.

Ví dụ:

- Book.title đọc một property có sẵn.
- Book.author gọi service nội bộ.
- Book.recommendations gọi một hệ thống gợi ý bên ngoài.
- Book.reviews(first: 100) tải nhiều bản ghi.

Các field này có chi phí rất khác nhau dù nằm cùng depth.

GraphQL Java cung cấp MaxQueryComplexityInstrumentation với cơ chế tính complexity theo field. Ứng dụng có thể định nghĩa cost model để field list tính theo argument first, hoặc field tốn kém có trọng số cao hơn.

Một cách ước lượng đơn giản:

~~~text
C(field) = baseCost(field) + fanOut * sum(C(children))
~~~

Đây là công thức minh họa cho cost model, không phải công thức mặc định của GraphQL Java. Cần xây dựng calculator và trọng số dựa trên workload thực tế.

Dùng depth limit để chặn query quá sâu; dùng complexity để kiểm soát tổng chi phí ước lượng của các field.

## 14. DataLoader giảm số lần gọi backend, không giảm depth

DataLoader và @BatchMapping giúp gom nhiều lần tải dữ liệu liên quan thành batch. Chúng có thể giảm N+1 database calls, nhưng không làm thay đổi cấu trúc GraphQL operation.

Ví dụ client query 20 Book và Author:

~~~graphql
query {
  books(first: 20) {
    id
    author {
      id
      name
    }
  }
}
~~~

Nếu mỗi Book gọi repository riêng để lấy Author, server có thể tạo 20 database calls. Dùng DataLoader hoặc @BatchMapping có thể gom các author ID vào một batch.

Tuy nhiên:

- Query vẫn có cùng depth.
- Server vẫn phải tạo response cho 20 Book và Author.
- Serialization vẫn phải xử lý toàn bộ field được yêu cầu.
- Một query sâu với nhiều nhánh vẫn cần depth limit.
- Một query nông nhưng list rất lớn vẫn cần amount limit.

Không xem DataLoader là biện pháp thay thế depth limit hoặc pagination. Nó tối ưu cách tải dữ liệu, không giới hạn lượng dữ liệu mà client yêu cầu.

## 15. Kiểm thử depth boundary

Khi bật depth limit, nên có test cho ba trường hợp:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Depth thấp hơn ngưỡng | Operation được thực thi |
| Depth đúng bằng ngưỡng | Operation được thực thi |
| Depth lớn hơn ngưỡng | Operation bị abort |

Ví dụ cấu hình ngưỡng 3 và query hợp lệ:

Các ví dụ trong phần này giả định schema có Query.bookById, Book.author, Author.organization và Organization.name.

~~~graphql
query {
  bookById(id: "b-01") {
    author {
      name
    }
  }
}
~~~

Depth lớn nhất là 3 nên query được chấp nhận.

Query vượt ngưỡng:

~~~graphql
query {
  bookById(id: "b-01") {
    author {
      organization {
        name
      }
    }
  }
}
~~~

Depth lớn nhất là 4 nên query bị từ chối.

Test bằng GraphQlTester:

~~~java
@Test
void shouldRejectQueryBeyondDepthBudget() {
    graphQlTester.document("""
            query {
              bookById(id: "b-01") {
                author {
                  organization {
                    name
                  }
                }
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookService);
}
~~~

Test giả định bookService là dependency được resolver gọi để tải Book. Nếu depth instrumentation abort trước execution, service không được gọi.

Ngoài boundary test, cần kiểm tra fragment, inline fragment, alias và nhiều nhánh để bảo đảm query depth được tính đúng theo GraphQL document.

## 16. Benchmark trước và sau khi bật depth limit

Depth limit có chi phí phân tích AST, nhưng giúp từ chối query quá sâu trước khi resolver chạy. Cần đo cả overhead của instrumentation và lợi ích khi chặn workload không hợp lệ.

Một benchmark có thể so sánh:

| Kịch bản | Depth | Fan-out | Mục đích |
|---|---:|---:|---|
| Query cơ bản | 2 | Thấp | Đo baseline |
| Query quan hệ | 5 | Thấp | Đo chi phí thêm resolver |
| Query sâu | 9 | Thấp | Kiểm tra depth rejection |
| Query list lớn | 3 | Cao | Chứng minh depth không giới hạn amount |
| Query nhiều alias | 2 | Nhiều nhánh | Kiểm tra số DataFetcher |
| Query có DataLoader | 4 | Trung bình | So sánh số DB calls trước/sau batch |

Đo các chỉ số:

- Latency p50, p95 và p99.
- Throughput và tỷ lệ request lỗi.
- CPU và heap allocation.
- Số DataFetcher invocation.
- Số database queries.
- Số object được tạo và kích thước response.
- Thời gian parse, validation và execution nếu tracing hỗ trợ.

Chạy benchmark với cùng dữ liệu, cùng page size và cùng concurrency. Nếu thay đổi nhiều yếu tố cùng lúc, sẽ khó biết cải thiện đến từ depth limit, DataLoader hay database cache.

Depth limit không phải công cụ tăng tốc query hợp lệ. Mục đích chính là chặn operation có cấu trúc vượt ngân sách. Muốn tăng tốc operation hợp lệ, cần tối ưu resolver, query database, pagination và batching.

## 17. Theo dõi query bị từ chối

Sau khi triển khai, cần biết depth limit có đang chặn operation hợp lệ hay không.

Nên ghi nhận:

- Số operation bị từ chối do vượt depth.
- Depth của operation bị từ chối.
- Operation name hoặc persisted query ID nếu có.
- Client/application đã gửi request, theo chính sách bảo mật.
- Tỷ lệ query bị từ chối theo thời gian.

Không dùng toàn bộ GraphQL document, variables hoặc field path tùy ý làm metric tag. Những giá trị đó có thể có cardinality rất cao hoặc chứa dữ liệu nhạy cảm.

Metrics nên dùng key có tập giá trị giới hạn như outcome, operation type và loại lỗi. Depth cụ thể hoặc operation identifier có thể được lưu ở log/trace có kiểm soát.

Nếu tỷ lệ từ chối tăng đột ngột sau một lần release client, hãy kiểm tra operation mới và thay đổi schema trước khi tăng ngưỡng toàn cục.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query sâu vẫn chạy | Instrumentation chưa được gắn vào GraphQL runtime | Kiểm tra bean và GraphQlSource configuration |
| Query hợp lệ bị từ chối | Ngưỡng thấp hơn depth thực tế của client | Thu thập operation hợp lệ và hiệu chỉnh |
| Query nông vẫn chậm | Fan-out lớn hoặc resolver đắt | Thêm amount/complexity limit và tối ưu resolver |
| Nhiều database calls | Resolver tải quan hệ riêng lẻ | Dùng DataLoader hoặc @BatchMapping |
| Alias tạo tải lớn nhưng depth thấp | Depth không đo tổng số nhánh | Giới hạn alias/field và complexity |
| Document lớn vẫn tốn CPU | Depth limit không giới hạn kích thước AST | Giới hạn HTTP body và rate |
| Thêm instrumentation làm mất tracing | Thay thế instrumentation hiện có | Kết hợp instrumentation thay vì ghi đè |
| Test query vượt ngưỡng vẫn gọi service | Test không chạy qua runtime có instrumentation hoặc assertion nhầm dependency | Kiểm tra cấu hình test và verify service |
| Tăng ngưỡng làm p99 xấu đi | Query sâu hơn được phép thực thi | Đo workload và đánh giá complexity/fan-out |

## 19. Checklist triển khai Query depth limit

Trước khi đưa depth limit vào production:

- [ ] Đã tính depth của operation hợp lệ.
- [ ] Đã xác định ngưỡng dựa trên workload, không chọn tùy ý.
- [ ] MaxQueryDepthInstrumentation được đăng ký trong GraphQL runtime.
- [ ] Instrumentation khác như tracing/metrics vẫn hoạt động.
- [ ] Query ngay dưới, bằng và vượt ngưỡng có test.
- [ ] Fragment và inline fragment được tính đúng.
- [ ] Query có alias và nhiều nhánh được kiểm tra.
- [ ] DataFetcher không chạy khi operation bị abort.
- [ ] Tất cả field list đều có amount limit.
- [ ] Có pagination cho collection lớn.
- [ ] Có complexity limit cho field có chi phí khác nhau.
- [ ] DataLoader được dùng cho quan hệ dễ phát sinh N+1.
- [ ] HTTP request body và rate được giới hạn.
- [ ] Có metric/log theo dõi query bị từ chối.
- [ ] Không đưa query, variables hoặc field path tùy ý vào metric tags.

## Kết luận

Query depth limit giới hạn số cấp field lồng nhau trong GraphQL operation. Nó đặc biệt hữu ích với schema có quan hệ đệ quy hoặc nhiều tầng resolver, giúp từ chối query vượt ngân sách trước khi DataFetcher thực thi.

Trong Spring for GraphQL, có thể dùng MaxQueryDepthInstrumentation của GraphQL Java và tích hợp nó vào GraphQL runtime. Hãy chọn ngưỡng từ operation hợp lệ và đo hiệu năng thực tế. Depth limit chỉ kiểm soát độ sâu; fan-out, page size, alias và chi phí resolver cần được kiểm soát bằng amount limit, pagination, query complexity, DataLoader và các guardrail khác.

Đánh giá hiệu quả bằng boundary test, benchmark và quan sát query bị từ chối sẽ giúp duy trì hiệu năng khi schema và client phát triển.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — GraphQL Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [OWASP — GraphQL Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)
