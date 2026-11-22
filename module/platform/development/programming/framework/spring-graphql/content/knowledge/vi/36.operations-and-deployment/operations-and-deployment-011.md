# Kiểm tra compatibility trước release

Một thay đổi GraphQL chỉ nên được phát hành khi server mới vẫn đáp ứng những operation và hành vi mà các client đang được hỗ trợ phụ thuộc vào. Việc schema SDL build thành công chưa đủ để kết luận release an toàn: operation cũ có thể không còn validate, resolver có thể trả dữ liệu khác, authorization có thể đổi, hoặc một subgraph có thể không còn compose được với phần còn lại của supergraph.

Với Spring for GraphQL, kiểm tra compatibility trước release cần kết hợp schema review, operation checks, contract tests, kiểm tra runtime và quy trình triển khai. Mục tiêu là tìm ra thay đổi gây ảnh hưởng trước khi nó đến production, đồng thời có bằng chứng rõ ràng để quyết định release tiếp tục hay dừng.

Bài học này trình bày một quy trình thực tế để kiểm tra compatibility cho GraphQL API trước release: chuẩn bị baseline, phân loại schema changes, kiểm thử operation cũ bằng Spring for GraphQL, kiểm tra Federation, đánh giá runtime/transport, thiết lập CI release gates và triển khai theo từng giai đoạn.

## 1. Compatibility trước release là gì?

Compatibility trước release là quá trình xác minh phiên bản sắp phát hành vẫn tương thích với các consumer và hệ thống phụ thuộc đang nằm trong phạm vi hỗ trợ.

Ví dụ, production hiện có schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    name: String!
}
~~~

Một release muốn đổi `name` thành `displayName`. Nếu chỉ sửa SDL thành:

~~~graphql
type Book {
    id: ID!
    displayName: String!
}
~~~

thì operation cũ chọn `name` sẽ không còn validate. Server có thể build thành công nhưng client cũ sẽ lỗi ngay khi gửi request.

Một thay đổi tương thích nên giữ field cũ trong thời gian migration:

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
~~~

Trước khi release, cần xác minh cả hai field có resolver, trả dữ liệu đúng và client cũ vẫn chạy. Chỉ sau khi usage của `name` đã được xử lý theo chính sách hỗ trợ mới cân nhắc removal.

## 2. Năm lớp cần kiểm tra

| Lớp | Cần xác minh | Ví dụ lỗi có thể xảy ra |
| --- | --- | --- |
| Schema | SDL mới còn hợp lệ và giữ operation cũ không? | Xóa field, đổi argument, thay type |
| Operation | Những query/mutation/subscription đang dùng có còn chạy không? | Client vẫn gửi argument cũ hoặc chọn field đã xóa |
| Runtime contract | Resolver còn trả đúng shape, nullability và semantics không? | Field đổi ý nghĩa, trả null ngoài dự kiến |
| Security và transport | Authentication, authorization, header, endpoint và protocol có còn tương thích không? | Client cũ bị 401/403 hoặc WebSocket không kết nối |
| Hệ thống phụ thuộc | Database, downstream service, DataLoader và Federation có tương thích không? | Migration dữ liệu chưa xong, composition thất bại |

Các lớp này bổ sung cho nhau. Schema diff chủ yếu phát hiện thay đổi trong type system; contract test kiểm tra hành vi của operation; integration test và rollout xác minh hệ thống hoạt động trong môi trường gần production.

## 3. Chuẩn bị baseline trước khi so sánh

Không thể đánh giá một thay đổi nếu không biết trạng thái hiện tại mà client đang sử dụng. Trước khi chạy compatibility checks, hãy thu thập baseline:

- Schema đang được publish hoặc schema production đang phục vụ.
- Schema candidate từ commit/release sắp phát hành.
- Các operation đã đăng ký hoặc operation telemetry của client.
- Client name, version, môi trường và nhóm người dùng liên quan.
- Persisted query/allowlist nếu API sử dụng cơ chế này.
- Danh sách subgraph, router và service phụ thuộc.
- Contract tests, integration tests và dữ liệu test đại diện.

Nên lưu schema production đã phát hành thành artifact có version hoặc commit rõ ràng. Không dùng schema từ branch bất kỳ làm baseline nếu nó có thể đã khác schema đang chạy.

Nếu có nhiều môi trường hoặc variant, hãy xác định schema nào đang được dùng bởi production client. Một schema staging mới nhất không nhất thiết đại diện cho hợp đồng production.

## 4. Thu thập operation mà client thực sự sử dụng

SDL cho biết server hỗ trợ những field nào; operation cho biết client đang gọi những field nào.

Một operation registry hoặc operation telemetry giúp xác định:

- Operation name và operation ID.
- Client name/version đã gửi operation.
- Field, argument và type được chọn.
- Tần suất gọi trong khoảng thời gian quan sát.
- Operation nào thuộc mobile client cũ hoặc consumer ít hoạt động.

Ví dụ operation:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        name
        author {
            displayName
        }
    }
}
~~~

Nếu release xóa `Book.name`, operation này sẽ bị ảnh hưởng dù một số test mới chỉ truy vấn `displayName`.

Operation telemetry có giới hạn: client offline, operation hiếm dùng hoặc client không gửi metadata có thể không xuất hiện trong tập dữ liệu. Vì vậy, cần kết hợp telemetry với danh sách consumer được hỗ trợ, operation fixtures và thông tin release của từng client.

Không ghi raw variables hoặc dữ liệu cá nhân chỉ để theo dõi usage. Chỉ thu thập metadata cần thiết để nhận diện operation và consumer.

## 5. Phân loại schema changes

Trước release, review schema diff và phân loại thay đổi theo ảnh hưởng:

| Nhóm | Ví dụ | Quyết định ban đầu |
| --- | --- | --- |
| Additive | Thêm field nullable vào object type | Thường có thể tiếp tục sau khi kiểm tra resolver |
| Breaking | Xóa field đang được operation dùng | Chặn release cho đến khi có migration hoặc ngoại lệ được phê duyệt |
| Dangerous | Thêm enum output value, đổi default, đổi nullability | Cần kiểm tra consumer và runtime cụ thể |
| Metadata-only | Sửa description hoặc thêm deprecation reason | Thường an toàn, vẫn cần review schema |
| Composition change | Thay field ownership hoặc entity key giữa subgraph | Cần composition check và review các consumer liên quan |

Các thay đổi thường cần được xem xét kỹ:

- Xóa hoặc đổi tên field, type, argument, input field hoặc enum value.
- Thêm required argument/input field không có default.
- Thay đổi scalar, object, list hoặc nullability.
- Thay đổi default argument/input.
- Thay đổi enum output hoặc member của union.
- Thay đổi directive, entity key hoặc field ownership trong Federation.

Một thay đổi additive về schema vẫn có thể nguy hiểm với client code generation hoặc exhaustive enum handling. Hãy dựa vào client thực tế và không chỉ dựa vào nhãn “non-breaking” từ schema diff.

## 6. Kiểm tra schema diff tự động

Nên chạy schema diff giữa schema production và schema candidate trong CI. Kết quả cần hiển thị:

- Thành phần được thêm, sửa hoặc xóa.
- Breaking changes.
- Dangerous changes cần đánh giá thêm.
- Field đã deprecated và lý do.
- Schema coordinate bị ảnh hưởng, ví dụ `Book.name` hoặc `Query.books(first:)`.

Nếu dùng Apollo GraphOS, Schema Checks có thể chạy qua Rover CLI và tích hợp vào pipeline. Build checks xác minh schema hợp lệ; với Federation, chúng còn kiểm tra các subgraph có compose được thành supergraph hay không. Operations checks so sánh schema candidate với operation history để xác định client bị ảnh hưởng.

Operations checks dựa trên operation metrics đã gửi về GraphOS. Khoảng thời gian mặc định là bảy ngày và có thể cấu hình. Nếu không có metrics để so sánh, các thay đổi có khả năng nguy hiểm sẽ bị đánh dấu không đạt; đây là trạng thái thiếu bằng chứng, không phải xác nhận rằng schema an toàn.

Ví dụ chạy check cho một graph:

~~~bash
rover graph check my-graph@production --schema ./schema.graphql
~~~

Với Federation subgraph:

~~~bash
rover subgraph check my-graph@production \
    --name books \
    --schema ./books/schema.graphql
~~~

Tên graph, variant, subgraph và đường dẫn schema phải thay bằng giá trị của dự án. Kiểm tra CLI version và hướng dẫn Rover hiện hành trước khi đưa lệnh vào pipeline chính thức.

Nếu không sử dụng GraphOS, có thể dùng schema snapshot/diff tool, GraphQL Java validation hoặc một operation registry nội bộ. Điều quan trọng là cùng một baseline và cùng một tập operation được kiểm tra nhất quán giữa các lần release.

## 7. Đánh giá operation checks và kết quả dangerous changes

Operation checks trả lời câu hỏi: với schema candidate, operation đã được ghi nhận có còn hợp lệ và an toàn để chạy không?

Kết quả thường phân biệt operation **broken** (không còn hợp lệ với schema mới) và **potentially affected** (vẫn hợp lệ nhưng có thể đổi hành vi hoặc ảnh hưởng client). Mở chi tiết từng operation để biết field/argument nào gây ảnh hưởng và consumer nào gửi operation đó.

Nên phân tích từng operation bị ảnh hưởng:

- Operation có mất field hoặc argument không?
- Biến được khai báo có còn tương thích với argument mới không?
- Operation có thể vẫn validate nhưng nhận thêm enum value hoặc shape khác không?
- Client nào đang gửi operation đó?
- Tần suất và mức độ quan trọng của client ra sao?
- Có bản client mới đã migration hay chưa?

Không bỏ qua dangerous change chỉ vì operation vẫn validate. Ví dụ thêm `SCHEDULED` vào enum output không làm query cũ lỗi validation, nhưng một client dùng `switch` exhaustive có thể không biết cách hiển thị giá trị mới.

Nếu check báo operation không sử dụng trong thời gian quan sát, hãy kiểm tra chính sách hỗ trợ và loại client trước khi cho phép removal. Một ứng dụng mobile cũ có thể không tạo traffic trong nhiều ngày nhưng vẫn nằm trong thời gian hỗ trợ.

## 8. Giữ operation cũ bằng contract tests trong Spring for GraphQL

Schema checks dựa trên operation history không thay thế test hành vi. Với Spring for GraphQL, `GraphQlTester` cung cấp cùng một workflow kiểm thử request cho nhiều transport.

Có thể lưu operation cũ dưới `src/test/resources/graphql-test/` và chạy lại sau mỗi thay đổi schema/resolver.

Ví dụ test một operation legacy:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookCompatibilityTests {

    @LocalServerPort
    private int port;

    private GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port + "/graphql")
                .build();
        this.graphQlTester = HttpGraphQlTester.create(client);
    }

    @Test
    void legacyBookOperationStillWorks() {
        graphQlTester.document("""
                query LegacyBook($id: ID!) {
                    book(id: $id) {
                        id
                        name
                    }
                }
                """)
                .variable("id", "book-42")
                .execute()
                .errors()
                .verify()
                .path("book.name")
                .entity(String.class)
                .isEqualTo("Clean Code");
    }
}
~~~

Ví dụ giả định test configuration đã cung cấp `GraphQlTester` kết nối tới ứng dụng. Trong test tích hợp, có thể tạo `HttpGraphQlTester` từ `WebTestClient` hoặc dùng `WebSocketGraphQlTester`/`RSocketGraphQlTester` cho transport tương ứng.

Với operation được lưu trong file, `documentName("legacyBook")` giúp test tái sử dụng document thay vì nhúng query text vào Java. Giữ operation fixtures trong version control để reviewer thấy release đang bảo vệ consumer contract nào.

## 9. Kiểm tra response, nullability và partial errors

Một operation có thể vẫn validate nhưng trả response khác trước. Contract test nên kiểm tra:

- Field cũ còn giá trị và đúng semantics.
- Field mới có giá trị mong đợi.
- Nullability không bị vi phạm.
- List không bất ngờ có item null hoặc list null.
- Error code và error path vẫn phù hợp với hợp đồng.
- Partial data được trả theo cách client có thể xử lý.

Ví dụ test cả hai field trong giai đoạn migration:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void legacyAndReplacementFieldsReturnSameValue() {
    graphQlTester.document("""
            query BookNames($id: ID!) {
                book(id: $id) {
                    name
                    displayName
                }
            }
            """)
            .variable("id", "book-42")
            .execute()
            .errors()
            .verify()
            .path("book")
            .entity(BookNames.class)
            .satisfies(book -> {
                assertThat(book.name()).isEqualTo("Clean Code");
                assertThat(book.displayName()).isEqualTo(book.name());
            });
}

record BookNames(String name, String displayName) {
}
~~~

Đây là ví dụ kiểm tra hai field có cùng semantics. Nếu field mới có ý nghĩa khác, hãy viết assertion riêng thay vì buộc chúng bằng nhau.

Khi test lỗi có chủ đích, dùng `errors().expect(...)` hoặc `errors().satisfy(...)` để xác minh error contract. Không lọc bỏ mọi error bằng `verify()` nếu release cần phát hiện lỗi resolver.

## 10. Kiểm tra input, validation và default values

Các thay đổi input thường bị bỏ sót khi chỉ test response field.

Trước release, cần xác minh:

- Client cũ không truyền argument tùy chọn vẫn chạy.
- Input object cũ vẫn được chấp nhận.
- Required argument mới không làm operation cũ lỗi.
- Default pagination, sort và filter không đổi ngoài chủ đích.
- Validation error vẫn có mã và path phù hợp.
- Custom scalar vẫn serialize/parse theo cùng định dạng.

Ví dụ nếu `books(first: Int = 20)` đổi default thành 100, operation cũ vẫn validate nhưng có thể tải nhiều dữ liệu hơn. Cần test trường hợp không truyền `first`, đo response size và xác minh giới hạn server vẫn được áp dụng.

Đừng chỉ kiểm tra query với mọi argument được truyền tường minh. Client thực tế thường dựa vào default value của schema.

## 11. Kiểm tra authorization và security compatibility

Một thay đổi authorization có thể làm client hợp lệ bị từ chối dù schema không đổi.

Hãy chạy contract test với các danh tính quan trọng:

- Anonymous client nếu API cho phép truy cập công khai.
- User đã đăng nhập.
- User có role thấp và role cao.
- Tenant khác nhau.
- Service account hoặc client credential.
- Client cũ sử dụng header hoặc token format đang được hỗ trợ.

Kiểm tra cả field-level authorization, `@PreAuthorize`, `DataFetcherExceptionResolver`, error classification và nội dung GraphQL error. Xác minh user không có quyền không thể đọc dữ liệu qua field lồng nhau, DataLoader hoặc entity resolver.

Không dùng một tài khoản admin cho toàn bộ test suite. Test chỉ chạy với quyền cao có thể che giấu regression về phân quyền.

## 12. Kiểm tra mutation và side effects

Mutation là contract hành vi: cùng một input cần giữ ý nghĩa và tác dụng đã cam kết.

Trước release, xác minh:

- Input cũ vẫn được bind và validate.
- Mutation không tạo side effect ngoài dự kiến.
- Idempotency key hoặc retry behavior vẫn nhất quán.
- Error không làm client hiểu nhầm mutation đã thành công.
- Response trả object/version/state đúng sau khi thay đổi.
- Transaction rollback và event publication vẫn theo đúng thứ tự.

Ví dụ, đổi `createOrder` để tự động capture payment là thay đổi lớn về semantics dù schema không đổi. Client cũ có thể chỉ mong muốn tạo đơn hàng ở trạng thái pending.

Hãy test mutation với database test hoặc dependency giả lập phù hợp, sau đó kiểm tra trạng thái thực tế thay vì chỉ kiểm tra response JSON.

## 13. Kiểm tra subscription và transport

Nếu release thay đổi WebSocket hoặc RSocket, cần kiểm tra transport riêng:

- Endpoint và protocol vẫn tương thích.
- Authentication header hoặc connection initialization payload không đổi ngoài kế hoạch.
- Client cũ vẫn subscribe và nhận event.
- `next`, `error`, `complete` được gửi theo đúng protocol.
- Reconnect và cancellation hoạt động.
- Heartbeat, timeout và connection limit phù hợp.
- Event payload giữ shape và semantics.

`GraphQlTester` hỗ trợ `WebSocketGraphQlTester` và `RSocketGraphQlTester`; subscription test có thể dùng `executeSubscription()` và Reactor `StepVerifier` để kiểm tra stream.

Một HTTP query test không chứng minh WebSocket subscription tương thích. Hãy chạy test qua đúng transport mà client production sử dụng.

## 14. Kiểm tra custom scalar và dữ liệu

Custom scalar thường đại diện cho định dạng mà client phụ thuộc trực tiếp, ví dụ `Date`, `DateTime`, `Money`, `URL` hoặc `UUID`.

Trước release, kiểm tra:

- Input serialization và output serialization.
- Time zone, offset và precision.
- Decimal rounding, currency và unit.
- Null và invalid value handling.
- Format có thay đổi giữa các phiên bản client không.
- JSON representation có giữ nguyên kiểu dữ liệu mong đợi không.

Ví dụ đổi `DateTime` từ ISO-8601 có offset sang chuỗi local time có thể làm client diễn giải sai thời điểm dù GraphQL type name vẫn là `DateTime`.

Nên lưu các giá trị biên trong contract fixtures: ngày qua nửa đêm UTC, số thập phân có nhiều chữ số, chuỗi rỗng, null và giá trị không hợp lệ.

## 15. Kiểm tra performance và giới hạn truy vấn

Một release tương thích về schema vẫn có thể gây sự cố vận hành nếu query cũ chậm hơn hoặc tiêu thụ nhiều tài nguyên hơn.

Cần kiểm tra các thay đổi ảnh hưởng:

- Resolver gọi thêm downstream service.
- DataLoader batch size hoặc cache scope.
- Query database và N+1.
- Pagination default/max page size.
- Query depth/complexity limit.
- Response size và serialization.
- Timeout, concurrency và rate limit.

Dùng operation đại diện từ production telemetry làm load-test input. So sánh latency percentile, error rate, throughput, database calls và memory với baseline trước release.

Nếu thêm field mới khiến resolver cũ phải tải thêm dữ liệu dù client không chọn field đó, cần xem lại implementation. GraphQL chỉ nên resolve field được chọn theo cách hiệu quả và không tạo chi phí ngoài dự kiến.

## 16. Kiểm tra Federation composition và downstream compatibility

Với Spring for GraphQL Federation, kiểm tra một subgraph riêng lẻ chưa đủ. Schema candidate cần compose thành supergraph và giữ các dependency giữa subgraph.

Trước release, kiểm tra:

- Entity `@key` còn ổn định và resolver có thể resolve representation.
- Field ownership không xung đột.
- `@requires` và `@provides` vẫn đúng với dữ liệu được cung cấp.
- Subgraph khác không còn phụ thuộc field sắp bị xóa.
- Operation qua router vẫn chạy sau composition.
- Router có thể tải supergraph schema mới.

Apollo GraphOS build checks xác minh schema subgraph có compose được với các subgraph còn lại. Operations checks tiếp tục xác minh các operation client đã ghi nhận có bị ảnh hưởng không.

Nếu không dùng GraphOS, chạy composition bằng Rover CLI hoặc công cụ Federation tương ứng trong CI. Đừng chờ đến khi publish production mới phát hiện schema không compose được.

## 17. Kiểm tra cấu hình và hạ tầng triển khai

Compatibility còn phụ thuộc cấu hình môi trường và dependency bên ngoài. So sánh candidate với production ở các điểm:

| Thành phần | Cần xác minh |
| --- | --- |
| HTTP endpoint | URL, HTTP method, content type, status code |
| Headers | Authorization, tracing, client identity, CORS |
| WebSocket/RSocket | Protocol, endpoint, handshake, reconnect |
| GraphQL configuration | Schema locations, scalar, instrumentation, exception resolver |
| Database | Migration đã chạy trước code mới, index và query plan |
| Downstream services | API contract, timeout, retry, credential |
| Runtime config | Feature flags, environment variables, secrets |
| Limits | Body size, depth, complexity, pagination, rate limit |
| Observability | Log, trace, metrics và alert đang hoạt động |

Nếu code mới phụ thuộc database column vừa thêm, triển khai migration theo kiểu expand-contract: thêm cấu trúc tương thích trước, deploy code dùng cấu trúc mới, chuyển dữ liệu, rồi mới xóa cấu trúc cũ khi mọi phiên bản ứng dụng đã chuyển xong.

## 18. Thiết lập release gates trong CI/CD

Một pipeline có thể tổ chức thành các gate theo thứ tự:

| Gate | Công việc | Điều kiện đạt |
| --- | --- | --- |
| 1. Build | Compile và tạo artifact | Build thành công |
| 2. Schema validation | Parse/validate SDL và schema wiring | Không có lỗi schema |
| 3. Schema diff | So sánh với production baseline | Không còn breaking change chưa xử lý |
| 4. Operation checks | Validate operation history/registry | Không có consumer bị ảnh hưởng chưa có phương án |
| 5. Contract tests | Chạy operation cũ và mới | Response/error/semantics đạt |
| 6. Security tests | Role, tenant và authentication | Không có regression quyền truy cập |
| 7. Federation checks | Compose subgraph và test qua router | Composition và operation checks đạt |
| 8. Integration/performance | Downstream, migration, load test | Trong ngưỡng SLO |
| 9. Release approval | Review bằng chứng và rollout plan | Có quyết định GO rõ ràng |

Không nên coi tất cả warning là pass. Mỗi dangerous change cần có người chịu trách nhiệm, consumer bị ảnh hưởng và bằng chứng chấp nhận rủi ro.

Với GraphOS, nên chạy schema check riêng cho từng variant cần bảo vệ, chẳng hạn staging và production. Lệnh Rover trong CI nên xác thực bằng secret `APOLLO_KEY` được lưu trong secret store của CI; không chạy bước đăng nhập tương tác trong pipeline.

Ví dụ một bước pipeline ở mức khái niệm:

~~~yaml
steps:
  - name: build-and-unit-tests
    run: ./gradlew test

  - name: schema-compatibility
    run: rover graph check my-graph@production --schema ./schema.graphql

  - name: contract-tests
    run: ./gradlew test --tests '*Compatibility*'

  - name: build-artifact
    run: ./gradlew bootJar
~~~

Đây là ví dụ minh họa. Điều chỉnh task Gradle, graph reference và lệnh theo build system cùng môi trường thực tế. Với Federation, thay graph check bằng subgraph check phù hợp.

## 19. Triển khai theo giai đoạn và thứ tự an toàn

Với thay đổi additive, quy trình thường an toàn hơn khi triển khai theo hướng expand:

1. Thêm field/type và resolver mới trong server.
2. Deploy server mới và đợi mọi replica sẵn sàng.
3. Publish schema candidate sau khi implementation đã hoạt động.
4. Cập nhật client để bắt đầu sử dụng field mới.
5. Theo dõi lỗi, latency và operation usage.
6. Sau thời gian migration, deprecate và lên kế hoạch removal field cũ.

Với Federation, Apollo khuyến nghị kiểm tra schema trước, deploy subgraph tới hạ tầng, đợi replicas cập nhật rồi mới publish schema tương ứng. Điều này tránh router nhận schema có field mới trong khi một số replica chưa có resolver để thực thi.

Nếu release có thay đổi không tương thích, cần migration plan riêng, thông báo consumer và có thể cần release theo nhiều giai đoạn. Không publish một breaking schema chỉ vì code mới đã được deploy.

## 20. Rollback và forward recovery

Rollback application không đồng nghĩa phải rollback schema ngay lập tức. Nếu client mới đã bắt đầu dùng field vừa thêm, xóa field đó khỏi schema có thể tạo thêm lỗi.

Một chiến lược an toàn hơn:

- Giữ schema additive nếu code implementation có thể rollback mà không làm field mới trả lỗi.
- Dùng feature flag để tắt hành vi mới trong khi giữ field contract.
- Tách schema publish khỏi application deploy khi nền tảng hỗ trợ.
- Chuẩn bị backward-compatible database migration.
- Theo dõi operation lỗi và client bị ảnh hưởng sau mỗi giai đoạn.
- Khi cần sửa schema, ưu tiên forward fix tương thích.

Với breaking change, cần biết rõ schema nào đang được router publish và client nào đã chuyển sang contract mới. Đừng giả định có thể khôi phục nguyên trạng chỉ bằng cách revert commit.

## 21. Release checklist và quyết định GO/NO-GO

Trước khi phát hành, người phụ trách có thể xác nhận các mục sau:

- [ ] Schema candidate đã được so sánh với schema production.
- [ ] Mọi breaking change đã được loại bỏ hoặc có migration/ngoại lệ được phê duyệt.
- [ ] Dangerous changes đã được đánh giá với client thực tế.
- [ ] Operation history và persisted operation đã được kiểm tra.
- [ ] Contract tests cho operation cũ và mới đều đạt.
- [ ] Nullability, defaults, enum và custom scalar đã được kiểm tra.
- [ ] Authentication, authorization và tenant isolation đều đạt.
- [ ] Mutation side effects và subscription streams đã được xác minh nếu có thay đổi.
- [ ] Federation composition và operation checks đã đạt nếu áp dụng.
- [ ] Database migration và downstream dependency đã sẵn sàng.
- [ ] Performance nằm trong SLO và query limits không chặn nhầm client hợp lệ.
- [ ] Metrics, logs, traces và alert có thể quan sát release.
- [ ] Rollout, rollback/forward recovery và người chịu trách nhiệm đã rõ.

**GO** khi tất cả gate bắt buộc đạt, các warning đã được xử lý hoặc chấp nhận có căn cứ, và rollout plan có thể thực hiện.

**NO-GO** khi còn operation production bị break chưa có migration, schema không compose, contract test quan trọng thất bại, quyền truy cập sai hoặc dependency chưa sẵn sàng.

Nếu một check không có đủ dữ liệu, ghi nhận là **UNKNOWN** và xác định cách bổ sung bằng chứng. Không tự chuyển UNKNOWN thành PASS.

## 22. Các lỗi thường gặp khi kiểm tra compatibility

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Schema build thành công nhưng client lỗi | Không chạy operation checks | So sánh schema với operation registry/telemetry |
| Schema diff báo pass nhưng response đổi nghĩa | Chỉ kiểm tra type system | Thêm runtime contract tests |
| Không phát hiện client cũ | Operation telemetry không đủ phạm vi | Kết hợp client inventory và persisted operation |
| Test chỉ chạy với admin | Không kiểm tra authorization theo role/tenant | Tạo test principal cho từng nhóm quyền |
| HTTP test pass nhưng subscription lỗi | Không kiểm tra WebSocket/RSocket | Chạy test qua transport thực tế |
| Subgraph chạy riêng nhưng router lỗi | Không chạy composition check | Kiểm tra supergraph candidate trong CI |
| Field mới có trong schema nhưng resolver chưa sẵn sàng | Publish schema trước khi deploy mọi replica | Deploy và health-check subgraph trước khi publish |
| Rollback làm client mới hỏng | Revert schema sau khi client đã sử dụng field mới | Giữ contract additive và dùng forward recovery |
| Load test không giống production | Dùng query nhân tạo không đại diện | Dùng operation telemetry đã được làm sạch |
| Check pass dù thiếu operation data | Không phân biệt dữ liệu thiếu với không có ảnh hưởng | Ghi trạng thái UNKNOWN và bổ sung operation coverage |

## 23. Những điểm cần ghi nhớ

- Compatibility trước release phải kiểm tra schema, operation, runtime, security, transport và dependency.
- Luôn so sánh schema candidate với baseline production đã phát hành.
- Schema diff và operation checks trả lời hai câu hỏi khác nhau.
- Dùng `GraphQlTester` để chạy lại operation cũ và kiểm tra response thực tế.
- Kiểm tra role/tenant, mutation, subscription và custom scalar khi release có thay đổi liên quan.
- Với Federation, chạy composition và operation checks qua supergraph.
- Deploy implementation trước khi publish schema có field mới.
- Theo dõi client usage trước khi xóa thành phần deprecated.
- Chuẩn bị forward recovery; rollback schema có thể làm hỏng client mới.
- Mọi release gate cần có bằng chứng và trạng thái GO/NO-GO/UNKNOWN rõ ràng.

Kiểm tra compatibility trước release biến một thay đổi GraphQL thành một quyết định có bằng chứng. Khi baseline, operation thực tế, contract tests, Federation checks và rollout plan cùng được xác minh, nhóm có thể phát hành thay đổi mới mà vẫn bảo vệ những client đang được hỗ trợ.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [Apollo GraphOS — Run Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks/run)
- [Apollo GraphOS — Deploying API Changes](https://www.apollographql.com/docs/graphos/platform/production-readiness/change-management)
- [Apollo GraphOS — Deployment Best Practices](https://www.apollographql.com/docs/graphos/platform/production-readiness/deployment-best-practices)
- [Apollo Federation — Schema Composition](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/composition)
