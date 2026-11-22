# Giới hạn query depth

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích query depth và lý do cần giới hạn độ sâu của GraphQL operation.
- Đếm độ sâu của một query có field lồng nhau.
- Nhận biết schema có quan hệ đệ quy dễ tạo query sâu.
- Cấu hình `MaxQueryDepthInstrumentation` trong Spring for GraphQL.
- Đăng ký instrumentation bằng Spring Boot và hiểu vị trí nó tham gia execution.
- Phân biệt depth limit với pagination, amount limit và query complexity.
- Hiểu ảnh hưởng của fragment, alias và nhiều operation đến việc đánh giá query.
- Kiểm thử query vượt ngưỡng và xác nhận DataFetcher không được chạy.
- Kết hợp depth limit với các biện pháp bảo vệ GraphQL khác.

## 1. Query depth là gì?

GraphQL cho phép client chọn field lồng nhau theo cấu trúc schema. Một query có thể đi từ root type xuống object type, rồi tiếp tục chọn field con của object đó.

Ví dụ:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

Đường đi sâu nhất của query là:

`Query.books → Book.author → Author.name`

Độ sâu của query, hay *query depth*, biểu diễn số cấp field lồng nhau từ root operation tới field sâu nhất. Một cách đếm phổ biến trong GraphQL Java là tính root field ở depth 1, mỗi field con thêm một cấp.

Với query trên:

| Field | Depth |
|---|---:|
| `Query.books` | 1 |
| `Book.author` | 2 |
| `Author.name` | 3 |

Các field cùng cấp như `Book.id` và `Book.title` không làm tăng độ sâu tối đa của query. Depth limit tập trung vào đường đi lồng nhau sâu nhất, không phải tổng số field xuất hiện trong document.

Một query có depth nhỏ vẫn có thể tốn kém nếu nó yêu cầu hàng nghìn bản ghi hoặc lặp lại nhiều field bằng alias. Vì vậy, depth là một tín hiệu bảo vệ quan trọng nhưng không đại diện cho toàn bộ chi phí thực thi.

## 2. Vì sao query quá sâu có thể gây rủi ro?

Schema GraphQL thường mô tả các quan hệ hai chiều hoặc quan hệ có thể quay lại type ban đầu.

Ví dụ:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  author: Author
  relatedBooks(first: Int = 10): [Book!]!
}

type Author {
  id: ID!
  books(first: Int = 10): [Book!]!
}
~~~

Book có Author, Author lại có danh sách Book. Book cũng có thể liên kết với Book khác. Schema hợp lệ này cho phép client lặp lại các field theo nhiều cấp:

~~~graphql
query {
  books {
    author {
      books {
        author {
          books {
            author {
              id
            }
          }
        }
      }
    }
  }
}
~~~

Nếu mỗi resolver truy vấn database hoặc gọi service bên ngoài, một query sâu có thể tạo ra nhiều lần tải dữ liệu, tăng số lượng resolver được thực thi và làm thời gian xử lý khó dự đoán.

Rủi ro thường tăng khi kết hợp:

- Quan hệ đệ quy hoặc quan hệ hai chiều trong schema.
- Field list không giới hạn số phần tử.
- Resolver có chi phí cao hoặc gọi service bên ngoài.
- Nhiều cấp field lồng nhau cùng kích hoạt DataFetcher.
- Client gửi nhiều alias hoặc nhiều nhánh truy vấn.
- Thiếu timeout, rate limit và giới hạn tài nguyên.

Depth limit giúp chặn operation có cấu trúc lồng nhau vượt ngưỡng trước khi các resolver bắt đầu tải dữ liệu.

## 3. Đếm depth của một GraphQL query

Giả sử schema có các type:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  author: Author
}

type Author {
  id: ID!
  organization: Organization
}

type Organization {
  id: ID!
  address: Address
}

type Address {
  city: String!
}
~~~

Query:

~~~graphql
query {
  book(id: "b-01") {
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

Độ sâu được tính theo đường đi từ root:

| Field | Depth |
|---|---:|
| `Query.book` | 1 |
| `Book.author` | 2 |
| `Author.organization` | 3 |
| `Organization.address` | 4 |
| `Address.city` | 5 |

Vì vậy, depth tối đa của query này là 5 theo cách đếm của `MaxQueryDepthInstrumentation`.

Một query khác có nhiều field cùng cấp:

~~~graphql
query {
  book(id: "b-01") {
    id
    author {
      id
      name
    }
  }
}
~~~

Depth lớn nhất là 3:

- `Query.book`: depth 1.
- `Book.author`: depth 2.
- `Author.name`: depth 3.

Các field `id` cùng cấp không tạo thêm độ sâu. Instrumentation đánh giá đường đi sâu nhất, không cộng tất cả field thành một con số duy nhất.

Khi chọn ngưỡng, hãy dùng query thực tế của client làm cơ sở. Nếu ngưỡng quá thấp, các màn hình hợp lệ có nhiều field lồng nhau sẽ bị từ chối. Nếu ngưỡng quá cao, nó có thể không ngăn được các query có cấu trúc bất thường.

## 4. MaxQueryDepthInstrumentation trong GraphQL Java

GraphQL Java cung cấp `MaxQueryDepthInstrumentation` để giới hạn độ sâu operation.

Class này thuộc package:

~~~java
graphql.analysis.MaxQueryDepthInstrumentation
~~~

Instrumentation phân tích operation được chọn và tính depth của các field. Nếu depth lớn hơn `maxDepth`, execution bị hủy bằng `AbortExecutionException` trước khi DataFetcher của operation được chạy.

Ví dụ tạo instrumentation với ngưỡng 8:

~~~java
Instrumentation instrumentation =
        new MaxQueryDepthInstrumentation(8);
~~~

Constructor nhận một số nguyên là độ sâu tối đa được phép. Query có depth bằng ngưỡng vẫn được chấp nhận; query có depth lớn hơn ngưỡng bị từ chối.

Có thể hiểu quy tắc:

- Depth 7: cho phép nếu maxDepth là 8.
- Depth 8: cho phép.
- Depth 9: từ chối.

Ngưỡng trong ví dụ chỉ để minh họa. Ứng dụng nên xác định ngưỡng bằng cách đo các operation hợp lệ, độ phức tạp schema và khả năng xử lý của backend.

## 5. Đăng ký instrumentation trong Spring Boot

Spring Boot auto-configuration của Spring for GraphQL phát hiện các bean có kiểu `graphql.execution.instrumentation.Instrumentation` và đưa chúng vào GraphQL runtime.

Vì vậy, cách đơn giản là khai báo một bean:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlSecurityConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }
}
~~~

Khi ứng dụng khởi động:

1. Spring Boot phát hiện bean `Instrumentation`.
2. GraphQlSource được cấu hình với instrumentation đó.
3. Khi GraphQL nhận operation, instrumentation phân tích query depth.
4. Nếu depth vượt ngưỡng, operation bị abort trước khi gọi resolver.
5. Nếu depth nằm trong giới hạn, GraphQL tiếp tục thực thi bình thường.

Không cần tự tạo HTTP filter để đếm số dấu ngoặc hoặc parse chuỗi query. Instrumentation hoạt động trên GraphQL document đã được GraphQL Java parse và có schema để hiểu quan hệ giữa các field.

### Khi ứng dụng tự cấu hình GraphQlSource

Nếu ứng dụng tự tạo `GraphQlSource` thay vì dùng auto-configuration của Spring Boot, cần đăng ký instrumentation vào builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResources)
        .configureRuntimeWiring(runtimeWiringConfigurer)
        .instrumentation(new MaxQueryDepthInstrumentation(8))
        .build();
~~~

Ví dụ trên minh họa điểm tích hợp; các resource và runtime wiring được cung cấp theo cấu hình của ứng dụng.

Nếu đã có instrumentation cho metrics, tracing hoặc các chức năng khác, cần phối hợp chúng bằng cơ chế chaining của GraphQL Java, chẳng hạn `ChainedInstrumentation`. Tránh thay thế instrumentation hiện có mà không kiểm tra vì có thể làm mất metrics hoặc tracing.

Với Spring Boot auto-configuration, ưu tiên khai báo các bean Instrumentation và để Boot tích hợp chúng. Nếu cần custom GraphQlSource, chịu trách nhiệm kết hợp đầy đủ các instrumentation đang dùng.

## 6. Instrumentation chạy ở giai đoạn nào?

Query depth cần được kiểm tra trước khi các DataFetcher thực thi để operation vượt ngưỡng không thể kích hoạt tải dữ liệu.

Về khái quát, GraphQL request đi qua các giai đoạn:

~~~mermaid
flowchart TD
    A[HTTP GraphQL request] --> B[Parse document]
    B --> C[Validate against schema]
    C --> D[Coerce variables and select operation]
    D --> E[MaxQueryDepthInstrumentation]
    E -->|Within limit| F[Execute fields and DataFetchers]
    E -->|Exceeds limit| G[Abort operation and create errors]
    F --> H[GraphQL response]
    G --> H
~~~

Instrumentation đánh giá document và operation được chọn. Nếu depth vượt ngưỡng, GraphQL Java hủy operation trước khi chạy các resolver.

Điều này quan trọng với bảo mật: một query bị từ chối do quá sâu không nên tạo các truy vấn database từ những field nằm trong operation đó.

Tuy nhiên, parse và validation vẫn cần tài nguyên. Depth limit không thay thế giới hạn kích thước request body, timeout cho parse/validation, rate limiting hoặc các biện pháp bảo vệ ở HTTP layer.

## 7. Ảnh hưởng của fragment và inline fragment

GraphQL cho phép tái sử dụng selection set bằng fragment.

Ví dụ:

~~~graphql
fragment AuthorDetails on Author {
  id
  organization {
    id
    address {
      city
    }
  }
}

query {
  book(id: "b-01") {
    author {
      ...AuthorDetails
    }
  }
}
~~~

Fragment không phải một cấp field trong schema. Các field bên trong fragment vẫn được tính theo vị trí mà fragment được sử dụng trong query.

Đường đi sâu nhất:

- `Query.book`: depth 1.
- `Book.author`: depth 2.
- `Author.organization`: depth 3.
- `Organization.address`: depth 4.
- `Address.city`: depth 5.

Inline fragment cũng không tạo thêm một cấp field chỉ vì có cú pháp fragment:

~~~graphql
query {
  search {
    ... on Book {
      author {
        organization {
          id
        }
      }
    }
  }
}
~~~

Depth được tính theo field selection thực tế trong nhánh query. Không nên tự viết bộ đếm chuỗi đơn giản vì cách đó dễ đếm sai fragment, inline fragment, alias và cú pháp GraphQL khác.

## 8. Alias và nhiều nhánh query

Alias cho phép client yêu cầu cùng một field nhiều lần với argument khác nhau:

~~~graphql
query {
  firstBook: book(id: "b-01") {
    author {
      name
    }
  }

  secondBook: book(id: "b-02") {
    author {
      name
    }
  }
}
~~~

Hai nhánh có cùng độ sâu tối đa. Alias không tự làm tăng depth vì nó chỉ thay đổi response key.

Tuy nhiên, alias có thể làm tăng số field được thực thi. Nếu client tạo hàng trăm alias với các argument khác nhau, depth limit đơn thuần có thể vẫn cho phép query đó.

Ví dụ:

~~~graphql
query {
  a: book(id: "b-01") { title }
  b: book(id: "b-02") { title }
  c: book(id: "b-03") { title }
}
~~~

Depth thấp nhưng có nhiều nhánh root field. Vì vậy, cần kết hợp depth limit với query complexity, giới hạn alias/field nếu cần, rate limiting và kiểm soát số lượng truy vấn dữ liệu.

## 9. Depth limit không giới hạn số lượng phần tử

Một query nông có thể yêu cầu số lượng phần tử rất lớn:

~~~graphql
query {
  books(first: 100000) {
    id
    title
  }
}
~~~

Depth của query này thấp, nhưng server có thể phải tải và serialize một lượng dữ liệu rất lớn nếu resolver chấp nhận argument đó.

Depth limit không đọc ý nghĩa nghiệp vụ của argument `first` để giới hạn số phần tử. Cần có amount limit hoặc pagination riêng.

Ví dụ resolver áp dụng giới hạn:

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

Nên kiểm tra giới hạn ở service hoặc tầng truy vấn dữ liệu nữa nếu cùng service được gọi từ nhiều entry point. Không dựa hoàn toàn vào validation ở GraphQL controller.

Với danh sách lớn, ưu tiên cursor pagination hoặc connection type để client tải dữ liệu theo từng trang.

## 10. Phân biệt depth, complexity và amount limit

Các biện pháp này giải quyết những loại chi phí khác nhau:

| Biện pháp | Kiểm soát | Ví dụ rủi ro |
|---|---|---|
| Query depth limit | Số cấp field lồng nhau | Quan hệ đệ quy tạo query rất sâu |
| Query complexity limit | Chi phí ước tính của các field | Nhiều field hoặc resolver đắt tiền |
| Amount limit | Số phần tử được tải ở mỗi field list | `first: 100000` |
| Alias/field limit | Số nhánh hoặc field trong operation | Hàng trăm alias root field |
| Timeout | Thời gian xử lý tối đa | Resolver hoặc downstream bị chậm |
| Rate limit | Số request trong một khoảng thời gian | Một client gửi quá nhiều operation |

GraphQL Java cũng cung cấp `MaxQueryComplexityInstrumentation`. Nó có thể tính độ phức tạp dựa trên các field và một `FieldComplexityCalculator` tùy chỉnh.

Ví dụ khai báo complexity instrumentation ở mức khái niệm:

~~~java
Instrumentation complexityInstrumentation =
        new MaxQueryComplexityInstrumentation(500);
~~~

Ngưỡng complexity cần được thiết kế theo cost model của ứng dụng. Nếu field list có argument `first`, calculator nên tính đến số phần tử yêu cầu; nếu không, một field tải 1 item và một field tải 1.000 item có thể bị đánh giá quá giống nhau.

Không nên dùng một con số depth để thay thế complexity hoặc amount limit. Các biện pháp nên phối hợp để kiểm soát cả cấu trúc query lẫn lượng công việc thực tế.

## 11. Ngưỡng depth nên được chọn như thế nào?

Không có một ngưỡng đúng cho mọi GraphQL API. Giá trị phù hợp phụ thuộc vào schema, cách client sử dụng API và chi phí resolver.

Quy trình chọn ngưỡng:

1. Thu thập các operation hợp lệ từ client hoặc persisted query registry.
2. Đo depth lớn nhất của các operation thực tế.
3. Xác định operation nào có độ sâu lớn nhưng vẫn cần thiết cho nghiệp vụ.
4. Chọn ngưỡng cao hơn các use case hợp lệ một khoảng hợp lý.
5. Kiểm thử query ngay dưới ngưỡng, bằng ngưỡng và vượt ngưỡng.
6. Theo dõi số request bị từ chối và điều chỉnh khi schema thay đổi.

Ví dụ, nếu các operation được hỗ trợ có depth từ 2 đến 6, ngưỡng 8 có thể là điểm bắt đầu để kiểm thử. Đây không phải khuyến nghị cố định; cần đo backend và tải thực tế.

Có thể dùng log hoặc metric để theo dõi:

- Số operation bị abort do depth.
- Depth của operation bị từ chối.
- Tên operation hoặc persisted query ID.
- Principal/client đã gửi operation, theo chính sách log bảo mật.
- Thời gian parse, validation và execution.

Không log toàn bộ query variables nếu có thể chứa dữ liệu nhạy cảm. Khi ghi operation, cân nhắc dùng operation name hoặc persisted query hash.

## 12. Xử lý query vượt ngưỡng

`MaxQueryDepthInstrumentation` mặc định abort operation khi depth vượt quá giới hạn. GraphQL Java tạo execution error từ `AbortExecutionException`.

Ví dụ message mặc định có dạng:

~~~text
maximum query depth exceeded 9 > 8
~~~

Response GraphQL có thể chứa errors mà không có kết quả data thực thi thông thường, vì operation bị dừng trước khi field resolver chạy.

Client nên nhận một lỗi có thể nhận diện để điều chỉnh query. Trong production, không nhất thiết phải công khai chi tiết nội bộ hoặc toàn bộ ngưỡng nếu chính sách bảo mật yêu cầu hạn chế thông tin.

Nếu muốn tùy chỉnh hành vi khi vượt ngưỡng, `MaxQueryDepthInstrumentation` có constructor nhận thêm một function `QueryDepthInfo -> Boolean`. Function này quyết định có ném abort exception hay không. Khi cần một response contract cụ thể, hãy kiểm thử cách exception được chuyển thành GraphQL error trong phiên bản GraphQL Java và Spring for GraphQL đang sử dụng.

Không nên trả dữ liệu giả hoặc âm thầm bỏ các field sâu để làm query có vẻ thành công. Query vượt chính sách cần bị từ chối rõ ràng.

## 13. Kiểm thử depth limit trong Spring for GraphQL

Nên kiểm thử qua GraphQL runtime để xác nhận instrumentation được đăng ký và thực sự ngăn resolver chạy.

Ví dụ cấu hình:

~~~java
@Configuration
class GraphQlSecurityConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(3);
    }
}
~~~

Giả sử schema:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  author: Author
}

type Author {
  books: [Book!]!
}
~~~

Query vượt ngưỡng:

~~~graphql
query {
  books {
    author {
      books {
        author {
          books
        }
      }
    }
  }
}
~~~

Đường đi sâu nhất lớn hơn 3, vì vậy operation phải bị từ chối trước khi resolver tải dữ liệu.

Ví dụ test:

~~~java
@Test
void shouldRejectQueryWhenDepthExceedsLimit() {
    graphQlTester.document("""
            query {
              books {
                author {
                  books {
                    author {
                      books {
                        id
                      }
                    }
                  }
                }
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).isNotEmpty();
                assertThat(errors.get(0).getMessage())
                        .contains("maximum query depth exceeded");
            });

    verifyNoInteractions(bookService);
}
~~~

Test này giả định instrumentation được đăng ký trong test application context và resolver dùng `bookService`. Điều quan trọng là kiểm tra cả GraphQL error lẫn việc service không bị gọi.

Nên có thêm các test:

1. Query depth thấp hơn ngưỡng được thực thi.
2. Query depth đúng bằng ngưỡng được chấp nhận.
3. Query depth lớn hơn ngưỡng bị từ chối.
4. Query dùng fragment vẫn bị tính đúng depth.
5. Query dùng inline fragment không bị đếm sai cấp.
6. Query có alias không làm sai depth.
7. Document có nhiều operation chỉ đánh giá operation được chọn.
8. Resolver không được gọi khi depth limit abort.
9. Các instrumentation khác như metrics/tracing vẫn hoạt động sau khi thêm depth limit.
10. HTTP response có error contract mà client có thể xử lý.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query sâu vẫn chạy | Instrumentation chưa được đăng ký vào GraphQL runtime | Kiểm tra bean Instrumentation hoặc GraphQlSource builder |
| Tất cả query đều bị từ chối | Ngưỡng quá thấp hoặc cách đếm depth chưa được kiểm tra | Viết test cho các độ sâu 1, ngưỡng và ngưỡng + 1 |
| Thêm instrumentation làm mất tracing | Thay thế instrumentation hiện có | Kết hợp bằng ChainedInstrumentation hoặc cơ chế Boot auto-configuration |
| Query nhiều alias vẫn tốn tài nguyên | Depth không đo tổng số field/nhánh | Thêm complexity và alias/field limit |
| Query depth thấp vẫn tải quá nhiều dữ liệu | Không giới hạn argument list | Thêm amount limit và pagination |
| Query có fragment bị đánh giá sai | Tự đếm cú pháp bằng chuỗi | Dùng MaxQueryDepthInstrumentation trên GraphQL document |
| Resolver vẫn chạy khi query bị từ chối | Test chưa chạy qua GraphQL runtime có instrumentation hoặc kiểm tra nhầm service | Xác minh application context và verify service |
| Client nhận message nội bộ | Abort exception được trả nguyên văn | Chuẩn hóa error response theo chính sách ứng dụng |

## 15. Checklist triển khai

Trước khi bật giới hạn query depth trong production:

- [ ] Có instrumentation `MaxQueryDepthInstrumentation` trong GraphQL runtime.
- [ ] Ngưỡng được chọn từ operation hợp lệ và tải backend thực tế.
- [ ] Quy ước đếm root field và nested field đã được kiểm thử.
- [ ] Fragment và inline fragment được tính đúng.
- [ ] Query ngay dưới, bằng và vượt ngưỡng có test.
- [ ] Query vượt ngưỡng bị abort trước DataFetcher.
- [ ] Instrumentation metrics/tracing hiện có vẫn hoạt động.
- [ ] Có amount limit cho field list và pagination.
- [ ] Có query complexity limit cho các field tốn kém.
- [ ] Có timeout và rate limit ở các tầng phù hợp.
- [ ] Error response không làm lộ thông tin nội bộ.
- [ ] Theo dõi operation bị từ chối và điều chỉnh khi schema thay đổi.

## Kết luận

Query depth là số cấp field lồng nhau trên đường đi sâu nhất của một GraphQL operation. Schema có quan hệ đệ quy có thể cho phép client tạo query rất sâu, khiến nhiều resolver và nguồn dữ liệu bị kích hoạt.

Spring for GraphQL có thể sử dụng `MaxQueryDepthInstrumentation` của GraphQL Java để từ chối operation vượt ngưỡng. Trong Spring Boot, đăng ký instrumentation dưới dạng bean là cách tích hợp đơn giản. Depth limit cần được kết hợp với complexity limit, amount limit, pagination, timeout và rate limiting vì một query nông vẫn có thể tốn nhiều tài nguyên.

Hãy chọn ngưỡng dựa trên operation hợp lệ, kiểm thử fragment/alias và xác nhận resolver không chạy khi query bị abort. Đây là cách biến depth limit thành một lớp bảo vệ có thể đo lường và duy trì khi schema phát triển.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — GraphQL Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — Query Complexity Instrumentation](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [OWASP — GraphQL Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)
