# graphql.field.path

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích ý nghĩa của key `graphql.field.path` trong Spring for GraphQL.
- Phân biệt `graphql.field.path` với `graphql.field.name`.
- Hiểu vai trò của observation `graphql.datafetcher` trong Micrometer.
- Đọc field path trong distributed trace để xác định vị trí resolver chậm hoặc phát sinh lỗi.
- Hiểu vì sao field path được phân loại là high-cardinality key.
- Phân biệt metadata dùng cho metrics với metadata dùng cho tracing.
- Bật observability cho GraphQL bằng Spring Boot Actuator và Micrometer.
- Nhận biết giới hạn của DataFetcher observation và cách kết hợp với request/DataLoader observations.
- Thiết kế logging, tracing và dashboard an toàn, tránh cardinality explosion.

## 1. graphql.field.path là gì?

Một GraphQL operation có thể yêu cầu nhiều field lồng nhau. Khi GraphQL Java thực thi operation, mỗi field được resolve tại một vị trí cụ thể trong cây response.

Ví dụ:

~~~graphql
query BookDetails($id: ID!) {
  bookById(id: $id) {
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

Một request có thể thực thi các DataFetcher cho những field như:

- `Query.bookById`
- `Book.author`
- `Author.organization`

Spring for GraphQL tích hợp Micrometer Observation để đo thời gian của các DataFetcher có xử lý thực sự. Observation này có tên `graphql.datafetcher` và mang metadata mô tả field đang được resolve.

Key `graphql.field.path` cho biết đường dẫn tới field trong execution tree, ví dụ:

~~~text
/bookById
/bookById/author
/bookById/author/organization
~~~

Nhờ đường dẫn này, khi xem trace của một GraphQL request, bạn có thể xác định resolver nào ở nhánh nào đang mất nhiều thời gian hoặc phát sinh lỗi.

`graphql.field.path` là metadata phục vụ observability. Nó không phải một field trong GraphQL schema, không phải argument mà client gửi và cũng không phải giá trị được trả về trong response GraphQL.

## 2. Phân biệt graphql.field.name và graphql.field.path

Spring for GraphQL tạo cả tên field và đường dẫn field trong DataFetcher observation. Hai key này trả lời hai câu hỏi khác nhau.

| Key | Ý nghĩa | Ví dụ |
|---|---|---|
| `graphql.field.name` | Tên schema field đang được fetch | `author` |
| `graphql.field.path` | Vị trí của field trong response tree | `/bookById/author` |

Giả sử một query lấy nhiều sách:

~~~graphql
query {
  featuredBooks {
    author {
      name
    }
  }
  recentBooks {
    author {
      name
    }
  }
}
~~~

Field `author` xuất hiện ở hai nhánh khác nhau:

~~~text
/featuredBooks/0/author
/recentBooks/0/author
~~~

Cả hai observation có thể cùng có:

~~~text
graphql.field.name = author
~~~

Nhưng field path khác nhau, giúp phân biệt nhánh dữ liệu đang được resolve.

Điều này đặc biệt hữu ích khi cùng một resolver được dùng tại nhiều vị trí trong schema. Chỉ nhìn field name sẽ không đủ để biết nó đang được gọi từ root query nào hoặc từ nhánh object nào.

## 3. graphql.field.path nằm trong observation nào?

Spring for GraphQL cung cấp các observation chính ở tầng GraphQL server:

| Observation name | Đo lường | Một số metadata mặc định |
|---|---|---|
| `graphql.request` | Toàn bộ GraphQL request | operation type, outcome, operation name, execution ID |
| `graphql.datafetcher` | Một lần thực thi DataFetcher không tầm thường | field name, field path, outcome, error type |
| `graphql.dataloader` | Lần gọi DataLoader hoặc `@BatchMapping` | loader name, loader size, outcome, error type |

`graphql.field.path` thuộc observation `graphql.datafetcher`.

Một request có thể tạo một observation `graphql.request` và nhiều observation `graphql.datafetcher`. Ví dụ một Query tải Book, sau đó tải Author và Organization, sẽ có các span/observation con tương ứng nếu các DataFetcher đó được xem là non-trivial.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A[graphql.request] --> B[graphql.datafetcher: bookById]
    B --> C[graphql.datafetcher: author]
    C --> D[graphql.datafetcher: organization]
    C --> E[graphql.dataloader: authorLoader]
~~~

Sơ đồ chỉ minh họa quan hệ quan sát. Số lượng observation thực tế phụ thuộc DataFetcher được đăng ký, DataLoader có được sử dụng hay không và cấu hình instrumentation.

## 4. Vì sao field path là high-cardinality key?

Một key có cardinality thấp thường chỉ có một số lượng giá trị hữu hạn, ổn định. Ví dụ:

- Operation type: `query`, `mutation`, `subscription`.
- Outcome: `SUCCESS`, `ERROR`.
- Field name: `bookById`, `author`, `organization`.

Trong khi đó, field path có thể thay đổi theo cấu trúc query:

~~~text
/bookById/author
/featuredBooks/0/author
/featuredBooks/1/author
/recentBooks/0/author
/search/results/12/book/author
~~~

Khi query có alias, nhiều nhánh hoặc danh sách có nhiều phần tử, số đường dẫn có thể tăng nhanh. Vì thế Spring for GraphQL phân loại `graphql.field.path` là high-cardinality key.

Micrometer phân chia metadata thành:

- Low-cardinality key: phù hợp để đưa vào metric tags vì tập giá trị được giới hạn.
- High-cardinality key: phù hợp hơn với trace hoặc log vì số giá trị có thể rất lớn.

Đây là lý do cần hiểu rõ `graphql.field.path` khi phân tích trace và khi thiết kế metric dashboard.

## 5. Không đưa graphql.field.path vào metric tags

Metric backend như Prometheus tạo time series theo tổ hợp tên metric và tags. Nếu mỗi path khác nhau tạo ra một tag metric riêng, số lượng time series có thể tăng mạnh.

Ví dụ không nên tạo metric theo cách:

~~~text
graphql.datafetcher.duration{
  graphql.field.path="/books/0/author"
}
graphql.datafetcher.duration{
  graphql.field.path="/books/1/author"
}
graphql.datafetcher.duration{
  graphql.field.path="/books/2/author"
}
~~~

Nếu query trả hàng nghìn phần tử, metric có thể phát sinh rất nhiều series chỉ vì index khác nhau.

Micrometer Observation chỉ dùng low-cardinality key values làm meter tags. High-cardinality key values như `graphql.field.path` không được đưa vào metrics mặc định; chúng có thể được giữ trong tracing output hoặc hệ thống log hỗ trợ metadata có cardinality cao.

Nên dùng các key có tập giá trị giới hạn cho dashboard metrics:

- `graphql.field.name`
- `graphql.outcome`
- `graphql.error.type`
- `graphql.operation.type`

Dùng `graphql.field.path` khi cần drill down vào một trace cụ thể để tìm đúng nhánh resolver.

## 6. Cấu hình observability trong Spring Boot

Spring GraphQL dùng Micrometer Observation để tạo request và DataFetcher observations. Các observation chỉ được publish khi ứng dụng có `ObservationRegistry` và instrumentation GraphQL được cấu hình.

Với Spring Boot, cách phổ biến là thêm Actuator:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-actuator")
~~~

Nếu muốn xuất metrics sang Prometheus, thêm registry tương ứng:

~~~groovy
runtimeOnly("io.micrometer:micrometer-registry-prometheus")
~~~

Spring Boot cung cấp `ObservationRegistry` và auto-configuration cho GraphQL observations khi các điều kiện cần thiết được đáp ứng. Spring Boot 3.x có `GraphQlObservationAutoConfiguration` từ dòng 3.0; Spring Boot 4 tiếp tục có auto-configuration tương ứng trong module GraphQL.

Với ứng dụng Spring Boot được cấu hình chuẩn, hãy kiểm tra Actuator và observation registry trước khi tự đăng ký instrumentation. Không tạo thêm một `GraphQlObservationInstrumentation` thứ hai nếu auto-configuration đã tạo sẵn.

Ví dụ cấu hình expose các endpoint chẩn đoán:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Endpoint `/actuator/metrics` hữu ích để kiểm tra metric đã được tạo. Endpoint Prometheus chỉ khả dụng nếu registry Prometheus được thêm và endpoint được expose.

### Trường hợp tự cấu hình GraphQlSource

Nếu ứng dụng không dùng GraphQL auto-configuration của Spring Boot và tự tạo GraphQlSource, cần thêm `GraphQlObservationInstrumentation` vào builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResources)
        .instrumentation(List.of(
                new GraphQlObservationInstrumentation(observationRegistry)))
        .build();
~~~

`schemaResources` và `observationRegistry` là các dependency đã được chuẩn bị trong cấu hình của ứng dụng. Nếu GraphQL runtime đang có instrumentation khác, hãy đưa chúng vào cùng danh sách thay vì ghi đè danh sách hiện có.

Với Spring Boot starter, không cần tự tạo đoạn builder trên trong trường hợp thông thường. Boot có thể tự phát hiện Instrumentation bean và thêm vào GraphQlSource builder; auto-configuration quan sát GraphQL tạo instrumentation khi có ObservationRegistry.

Constructor mặc định dùng các convention của Spring GraphQL, bao gồm `DefaultDataFetcherObservationConvention`, nơi `graphql.field.path` được tạo như high-cardinality key.

## 7. Những metadata mặc định của DataFetcher observation

Observation `graphql.datafetcher` sử dụng `DataFetcherObservationContext` và `DefaultDataFetcherObservationConvention`.

Các low-cardinality keys mặc định:

| Key | Mô tả | Ví dụ |
|---|---|---|
| `graphql.error.type` | Tên class của lỗi khi DataFetcher thất bại | `AccessDeniedException` |
| `graphql.field.name` | Tên field đang được fetch | `author` |
| `graphql.outcome` | Kết quả fetch | `SUCCESS`, `ERROR` |

High-cardinality key mặc định:

| Key | Mô tả | Ví dụ |
|---|---|---|
| `graphql.field.path` | Đường dẫn tới field đang được fetch | `/bookById/author` |

Những key này giúp quan sát một DataFetcher theo ba chiều:

1. Field nào đang được resolve.
2. Field nằm ở đâu trong GraphQL response tree.
3. Lần fetch thành công hay thất bại và lỗi thuộc loại nào.

Không phải tất cả field được client chọn đều tạo observation riêng. Spring GraphQL chỉ tạo DataFetcher observations cho các thao tác fetch được xem là non-trivial. Việc đọc property trực tiếp từ Java object bằng default property fetcher là thao tác trivial và thường không tạo observation riêng.

Vì vậy, không nên mong đợi một span `graphql.datafetcher` cho mọi scalar field như `Book.id` hoặc `Book.title` nếu chúng chỉ được đọc từ property có sẵn.

## 8. Dùng field path để tìm resolver chậm

Giả sử một query trả danh sách sách và thông tin tác giả:

~~~graphql
query {
  books(first: 20) {
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

Một trace có thể hiển thị:

~~~text
graphql.request                 850 ms
  graphql.datafetcher           120 ms  /books
  graphql.datafetcher           640 ms  /books/0/author
  graphql.datafetcher            12 ms  /books/0/author/organization
  graphql.datafetcher           610 ms  /books/1/author
  graphql.datafetcher            10 ms  /books/1/author/organization
~~~

Đây là số liệu minh họa. Khi phân tích trace thực tế:

1. Mở observation hoặc span `graphql.request` có tổng thời gian bất thường.
2. Xem các observation `graphql.datafetcher` bên trong request.
3. Sắp xếp theo duration để tìm fetcher tốn nhiều thời gian.
4. Đọc `graphql.field.name` để nhận diện loại field.
5. Đọc `graphql.field.path` để xác định nhánh cụ thể.
6. Kiểm tra error type nếu outcome là `ERROR`.
7. Mở span downstream hoặc log tương quan để tìm database query, HTTP call hay xử lý nghiệp vụ gây chậm.

Nếu `/books/0/author` và `/books/1/author` đều chậm, có thể resolver đang gọi database riêng cho từng Book. Đây là dấu hiệu cần kiểm tra N+1 và cân nhắc DataLoader hoặc `@BatchMapping`.

Nếu chỉ một path cụ thể chậm, hãy kiểm tra dữ liệu hoặc service được gọi từ nhánh đó. Không kết luận nguyên nhân chỉ từ field path; path chỉ cho biết vị trí thực thi, còn trace con và log cung cấp bằng chứng về thời gian và dependency.

## 9. Phân biệt field path với execution path trong GraphQL Java

GraphQL Java cũng cung cấp execution path cho DataFetcher thông qua `DataFetchingEnvironment`.

Ví dụ:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(
        Book book,
        DataFetchingEnvironment environment) {

    String executionPath =
            environment.getExecutionStepInfo()
                    .getPath()
                    .toString();

    log.debug("Resolving author at path={}", executionPath);

    return authorService.findByBookId(book.id());
}
~~~

Execution path có thể được dùng để ghi log trong resolver khi cần debug cục bộ. Tuy nhiên, không cần tự tạo observation chỉ để lưu path nếu GraphQL observation instrumentation đã được bật.

Phân biệt hai cách sử dụng:

- `environment.getExecutionStepInfo().getPath()`: API của GraphQL Java cho phép resolver đọc vị trí field hiện tại trong lúc thực thi.
- `graphql.field.path`: key do Spring GraphQL đưa vào Micrometer DataFetcher observation để quan sát từ trace.

Hai thông tin cùng mô tả vị trí field, nhưng nằm ở hai lớp khác nhau: một là execution API, một là observability metadata.

Không nên log toàn bộ path ở mọi resolver nếu hệ thống đã thu thập trace đầy đủ. Ghi log lặp lại có thể tạo lượng log lớn và làm tăng chi phí lưu trữ.

## 10. Kết hợp graphql.field.path với request observation

Một GraphQL request có thể gọi nhiều DataFetcher. Chỉ quan sát field riêng lẻ đôi khi không đủ để hiểu trải nghiệm tổng thể.

Request observation `graphql.request` cung cấp metadata như:

| Key | Cardinality | Ý nghĩa |
|---|---|---|
| `graphql.operation.type` | Low | `query`, `mutation`, `subscription` hoặc `operation` |
| `graphql.outcome` | Low | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| `graphql.execution.id` | High | Execution ID của request |
| `graphql.operation.name` | High | Tên operation do client cung cấp |

Khi xem trace, dùng request span làm điểm bắt đầu, sau đó mở các DataFetcher span để tìm field path có vấn đề.

Ví dụ:

~~~text
graphql.request
  graphql.operation.type = query
  graphql.outcome = SUCCESS
  graphql.operation.name = BookDetails

  graphql.datafetcher
    graphql.field.name = bookById
    graphql.field.path = /bookById

  graphql.datafetcher
    graphql.field.name = author
    graphql.field.path = /bookById/author
~~~

Operation name và execution ID giúp định vị request. Field name và field path giúp định vị DataFetcher trong request đó.

Không dùng operation name do client gửi làm nhãn metric nếu client có thể gửi vô hạn tên operation. Trong cấu hình mặc định, operation name là high-cardinality key để dùng trong trace.

## 11. Kết hợp với DataLoader observation để tìm N+1

Khi GraphQL query tải các field quan hệ, DataFetcher observation cho biết field nào được gọi. DataLoader observation cho biết các lần batch load.

Spring GraphQL tạo observation `graphql.dataloader` cho:

- Controller method được đánh dấu `@BatchMapping`.
- DataLoader được đăng ký và gọi thủ công.

Một số metadata mặc định:

| Key | Cardinality | Mô tả |
|---|---|---|
| `graphql.loader.name` | Low | Tên DataLoader |
| `graphql.outcome` | Low | `SUCCESS` hoặc `ERROR` |
| `graphql.error.type` | Low | Class lỗi nếu batch thất bại |
| `graphql.loader.size` | High | Kích thước danh sách phần tử được load |

Khi nghi ngờ N+1:

1. Tìm nhiều DataFetcher observation có field name giống nhau và path khác nhau.
2. Xem thời gian từng field path.
3. Tìm observation `graphql.dataloader` tương ứng.
4. So sánh số lần gọi loader và loader size.
5. Kiểm tra batch method có thực sự gom nhiều key vào một lần truy vấn không.

Ví dụ:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .map(authors -> mapAuthorsToBooks(books, authors));
    }
}
~~~

Ví dụ minh họa một batch mapping. Trong ứng dụng thực tế, cần bảo đảm kết quả được map đúng với từng source object và xử lý trường hợp không có Author.

Field path giúp tìm nhánh DataFetcher; DataLoader observation giúp kiểm tra cơ chế batch. Hai loại observation bổ sung cho nhau.

## 12. Đọc metrics và traces ở các công cụ giám sát

### Metrics

Metrics phù hợp để trả lời câu hỏi tổng quan:

- Bao nhiêu GraphQL request được xử lý?
- Thời gian xử lý trung bình hoặc phân vị là bao nhiêu?
- Tỷ lệ request lỗi thay đổi thế nào?
- Field nào thường xuyên có lỗi?
- DataLoader có đang được gọi hay không?

Với Micrometer, observation được chuyển thành timer/counter theo các low-cardinality key values. Ví dụ có thể kiểm tra metric:

~~~http
GET /actuator/metrics/graphql.datafetcher
~~~

Tên meter thực tế và cách chuẩn hóa tag có thể khác nhau theo registry. Hãy xem danh sách meter và tag do ứng dụng xuất ra thay vì giả định mọi backend hiển thị giống nhau.

### Distributed traces

Trace phù hợp để trả lời câu hỏi chi tiết:

- Request cụ thể nào chậm?
- DataFetcher nào chiếm phần lớn thời gian?
- Field nằm ở nhánh nào?
- Resolver gọi service hoặc database nào?
- Lỗi xuất hiện ở span nào?

`graphql.field.path` được dùng ở đây vì tracing backend có thể lưu high-cardinality metadata tốt hơn metrics backend.

### Logs

Log phù hợp để ghi thông tin chẩn đoán có chủ đích:

- Execution ID hoặc trace ID để tương quan.
- Operation name nếu được phép.
- Field path trong trường hợp cần debug cụ thể.
- Error type và thông tin xử lý an toàn.

Tránh ghi arguments, token, dữ liệu cá nhân hoặc toàn bộ GraphQL variables nếu không có yêu cầu nghiệp vụ và chính sách bảo vệ dữ liệu rõ ràng.

## 13. Tùy chỉnh convention khi cần

Spring GraphQL sử dụng observation convention để quyết định tên observation và các key values được ghi nhận. Mặc định, `DefaultDataFetcherObservationConvention` cung cấp `graphql.field.name`, `graphql.field.path`, `graphql.outcome` và `graphql.error.type`.

Nếu ứng dụng cần bổ sung metadata, có thể triển khai `DataFetcherObservationConvention` tùy chỉnh và đăng ký bean theo hướng dẫn của phiên bản Spring GraphQL đang dùng.

Ví dụ các metadata có thể cân nhắc:

- Tên nhóm nghiệp vụ có tập giá trị hữu hạn.
- Loại DataFetcher như controller hoặc repository adapter.
- Phiên bản API nội bộ nếu có số lượng giá trị giới hạn.

Không chuyển path, entity ID, user ID hoặc giá trị argument thành low-cardinality tag chỉ để dashboard dễ lọc. Nếu cần các giá trị đó, hãy giữ chúng ở high-cardinality metadata, log có kiểm soát hoặc trace attributes.

Khi thay convention mặc định, cần giữ lại các key mặc định cần thiết hoặc chủ động xác nhận dashboard và alert đã được cập nhật. Việc thay convention không tự động thay đổi GraphQL execution; nó chỉ thay đổi metadata quan sát.

## 14. Bảo vệ dữ liệu và tránh cardinality explosion

Field path có thể phản ánh alias hoặc vị trí phần tử trong danh sách. Do đó, một client có thể tạo nhiều path khác nhau bằng query có nhiều alias hoặc list lớn.

Các nguyên tắc:

- Giữ `graphql.field.path` ở high-cardinality metadata.
- Không chuyển field path thành metric tag.
- Không tạo metric name động từ path.
- Không thêm argument values hoặc entity IDs vào low-cardinality tags.
- Giới hạn query complexity và pagination để kiểm soát số field được thực thi.
- Giới hạn kích thước trace/log và thời gian lưu trữ theo chính sách vận hành.
- Kiểm tra trace sampling để không lưu mọi request có chi phí cao trong hệ thống lớn.
- Không ghi dữ liệu nhạy cảm vào span attributes hoặc log.

High-cardinality key không có nghĩa là có thể lưu mọi dữ liệu tùy ý. Tracing backend cũng có giới hạn về dung lượng, chi phí truy vấn và chính sách retention.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy `graphql.datafetcher` | Chưa có ObservationRegistry hoặc instrumentation | Kiểm tra Actuator và GraphQL observation auto-configuration |
| Chỉ thấy `graphql.request` | DataFetcher là property fetcher trivial hoặc không có instrumentation fetcher | Kiểm tra resolver thực sự được đăng ký |
| Không thấy `graphql.field.path` trong metrics | Đây là high-cardinality key, không phải metric tag mặc định | Xem distributed trace |
| Nhiều metric series tăng nhanh | Đã đưa path hoặc ID vào low-cardinality tags | Loại bỏ key động khỏi metric tags |
| Không phân biệt được hai field cùng tên | Chỉ xem `graphql.field.name` | Xem thêm `graphql.field.path` |
| Trace không có span HTTP cha | Transport tracing chưa cấu hình hoặc context propagation chưa đúng | Kiểm tra HTTP observation và tracing setup |
| Request chậm nhưng từng field không chậm | Chi phí nằm ở parse, validation, serialization hoặc transport | Xem request span và HTTP span |
| Nhiều field path tương tự đều chậm | Có thể đang gặp N+1 hoặc downstream dùng chung bị chậm | Đối chiếu DataLoader observation và dependency span |
| Error path không rõ trong dashboard | Đang xem metric aggregate | Mở trace cụ thể và kiểm tra error events |

## 16. Checklist triển khai

Trước khi dùng `graphql.field.path` để giám sát production:

- [ ] Có `ObservationRegistry` trong ứng dụng.
- [ ] `GraphQlObservationInstrumentation` được đăng ký đúng một lần trong GraphQL runtime.
- [ ] Quan sát được `graphql.request`.
- [ ] Quan sát được `graphql.datafetcher` cho các resolver non-trivial.
- [ ] Hiểu khác biệt giữa `graphql.field.name` và `graphql.field.path`.
- [ ] Dùng field path trong trace/log có kiểm soát.
- [ ] Không đưa field path vào metric tags.
- [ ] Dùng low-cardinality keys cho dashboard và alert.
- [ ] Có tracing để drill down vào request cụ thể.
- [ ] Đối chiếu DataLoader observation khi tìm N+1.
- [ ] Không ghi dữ liệu nhạy cảm vào metadata.
- [ ] Theo dõi cardinality và dung lượng trace/log.
- [ ] Kiểm thử cả trường hợp resolver thành công và thất bại.

## Kết luận

`graphql.field.path` là high-cardinality key trong observation `graphql.datafetcher` của Spring for GraphQL. Nó cho biết vị trí field đang được fetch trong cây thực thi GraphQL, giúp phân biệt các lần resolve cùng tên field ở những nhánh khác nhau.

Dùng `graphql.field.name` và `graphql.outcome` cho metrics tổng quan; dùng `graphql.field.path` trong distributed trace để tìm resolver chậm hoặc lỗi ở đúng nhánh. Kết hợp request observation, DataFetcher observation và DataLoader observation sẽ giúp phân tích hiệu năng GraphQL từ toàn request tới từng lần tải dữ liệu.

Không đưa field path vào metric tags vì số lượng giá trị có thể tăng theo alias, nhánh query và index danh sách. Giữ key này ở tracing/log có kiểm soát sẽ giúp chẩn đoán chi tiết mà không tạo cardinality explosion trong metrics backend.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL — Request Execution and Context](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
