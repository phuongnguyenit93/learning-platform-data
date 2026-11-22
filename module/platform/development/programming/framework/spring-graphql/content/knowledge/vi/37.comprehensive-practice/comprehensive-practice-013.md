# Checklist production readiness

Đưa một Spring for GraphQL API lên production cần nhiều hơn việc endpoint trả về JSON đúng. Schema phải ổn định, resolver phải chịu được tải, mỗi field phải bảo vệ đúng dữ liệu, query phải có giới hạn chi phí, lỗi phải được xử lý an toàn và đội vận hành phải quan sát được request từ GraphQL đến database hoặc dịch vụ phụ thuộc.

Bài thực hành này cung cấp checklist để rà soát một dịch vụ GraphQL trước khi phát hành và trong quá trình vận hành. Mỗi mục cần có bằng chứng cụ thể như cấu hình, kiểm thử, dashboard, trace, runbook hoặc kết quả diễn tập. Một ô được đánh dấu hoàn thành chỉ khi có bằng chứng kiểm tra được và có người chịu trách nhiệm.

## 1. Cách sử dụng checklist

Thực hiện rà soát theo môi trường production hoặc staging có cấu hình tương đương production. Với mỗi mục, ghi trạng thái, bằng chứng, người phụ trách và việc còn thiếu. Không dùng một kết quả kiểm thử trên dữ liệu nhỏ để kết luận hệ thống chịu được tải production.

| Trạng thái | Ý nghĩa |
|---|---|
| `PASS` | Đã kiểm tra và có bằng chứng phù hợp |
| `FAIL` | Đã kiểm tra và phát hiện chưa đạt |
| `N/A` | Không áp dụng; phải ghi lý do |
| `TODO` | Chưa kiểm tra hoặc chưa có đủ bằng chứng |

Phân loại mức độ:

- **Release blocker:** rủi ro có thể làm lộ dữ liệu, phá vỡ hợp đồng API, gây mất dữ liệu, hoặc khiến dịch vụ không thể vận hành an toàn. Không phát hành khi còn mục blocker chưa xử lý hoặc chưa có quyết định chấp nhận rủi ro được phê duyệt.
- **High:** có thể gây suy giảm đáng kể, tăng lỗi hoặc khó khôi phục. Cần có phương án giảm thiểu, chủ sở hữu và thời hạn rõ ràng trước phát hành.
- **Operational:** cải thiện khả năng theo dõi, bảo trì và phục hồi; cần đưa vào kế hoạch vận hành.

Không đánh dấu `N/A` chỉ vì chưa có thời gian thực hiện. Nếu một khả năng không được dùng, ví dụ Subscription, ghi rõ transport không được bật và xác nhận không có route tương ứng.

## 2. Schema và hợp đồng API

Schema SDL là hợp đồng giữa client và server. Một thay đổi schema có thể ảnh hưởng đến nhiều client dù code server vẫn biên dịch thành công.

- [ ] **Release blocker** — Schema được lưu và quản lý phiên bản cùng mã nguồn; thay đổi được review và có lịch sử diff.
- [ ] **Release blocker** — Tên type, field, argument, input và enum nhất quán với domain; không để lộ tên bảng, cấu trúc nội bộ hoặc thông tin bí mật.
- [ ] **Release blocker** — Nullability phản ánh đúng khả năng dữ liệu. Với field `T!`, server có thể bảo đảm giá trị khác null trong mọi trường hợp hợp lệ.
- [ ] **High** — Danh sách lớn có pagination; giới hạn page size được kiểm tra ở server và có giá trị tối đa hợp lý.
- [ ] **High** — Mutation có input type rõ ràng, kiểm tra dữ liệu và quy tắc nghiệp vụ ở server.
- [ ] **High** — Field/argument cũ được deprecate trước khi xóa; có kế hoạch chuyển client và mốc ngừng hỗ trợ.
- [ ] **High** — Các thay đổi schema được kiểm tra tương thích với client/query đã sử dụng, gồm cả persisted operations nếu hệ thống có dùng.
- [ ] **Operational** — Mô tả field, enum và input đủ rõ để client hiểu ngữ nghĩa, đơn vị, giới hạn và hành vi null.
- [ ] **Operational** — Quy trình review schema có người sở hữu và tiêu chí chấp nhận thay đổi breaking.

Đặc biệt chú ý lỗi nullability. Nếu resolver trả null cho một field non-null, GraphQL có thể đẩy lỗi lên parent và làm null hóa một phần lớn response. Hãy kiểm thử các trường hợp dữ liệu thiếu, dependency lỗi và quyền truy cập bị từ chối theo đúng nullability của schema.

## 3. Cấu hình ứng dụng Spring for GraphQL

Kiểm tra ứng dụng thực tế tạo `GraphQlSource`, đăng ký schema và resolver như thế nào. Với Spring Boot, xác nhận các auto-configuration đang được sử dụng thay vì thêm cấu hình trùng lặp theo một ví dụ từ phiên bản khác.

- [ ] **Release blocker** — Ứng dụng khởi động và nạp toàn bộ schema SDL thành công; lỗi schema được phát hiện trong build/startup hoặc kiểm thử triển khai.
- [ ] **Release blocker** — Mỗi field có resolver rõ ràng hoặc có thể được resolve an toàn bằng property data fetcher mặc định.
- [ ] **Release blocker** — Không có hai data fetcher cạnh tranh cho cùng field do đăng ký trùng `@SchemaMapping`, `@QueryMapping`, `@MutationMapping` hoặc `@BatchMapping`.
- [ ] **High** — Cấu hình GraphQL khác nhau theo profile được kiểm tra; production không vô tình bật cấu hình debug của local/dev.
- [ ] **High** — Các scalar tùy chỉnh, directive, instrumentation và exception resolver được đăng ký đúng một lần.
- [ ] **High** — Giới hạn kích thước HTTP request, timeout và cấu hình server phù hợp với payload GraphQL dự kiến.
- [ ] **Operational** — Phiên bản Spring Boot, Spring for GraphQL và GraphQL Java được quản lý nhất quán; nâng cấp có kiểm thử tương thích.

Endpoint GraphQL thường nhận POST qua HTTP; nếu ứng dụng dùng WebSocket cho Subscription, hãy xác minh riêng endpoint và handshake. Chỉ bật các transport thực sự cần dùng. Không giả định rằng một kiểm thử HTTP cũng xác nhận được hành vi WebSocket hoặc transport khác.

## 4. Bảo mật endpoint và cấu hình mạng

GraphQL có một endpoint tập trung, nhưng mỗi operation và field vẫn cần quyền truy cập đúng. Bảo vệ endpoint ở tầng HTTP là lớp đầu tiên.

- [ ] **Release blocker** — Production chỉ nhận kết nối qua HTTPS/TLS theo chuẩn của hạ tầng.
- [ ] **Release blocker** — Spring Security bảo vệ đúng GraphQL endpoint; anonymous access chỉ được cho phép với operation công khai đã xác định.
- [ ] **Release blocker** — CORS dùng allowlist origin cần thiết; không kết hợp wildcard origin với credentials.
- [ ] **Release blocker** — Nếu xác thực bằng cookie/session, CSRF được xử lý phù hợp với cơ chế xác thực và transport. Không tắt CSRF chỉ để làm một request GraphQL chạy được.
- [ ] **High** — Giới hạn request body, header và tốc độ gửi request tại gateway/server.
- [ ] **High** — GraphiQL, GraphQL Playground, endpoint debug và giao diện phát triển không được mở công khai ngoài chủ đích.
- [ ] **High** — Secret, signing key, database password và token dịch vụ lấy từ secret manager hoặc cơ chế quản lý bí mật của môi trường; không commit vào repository.
- [ ] **High** — Header bảo mật, proxy và forwarded header được cấu hình đúng theo topology triển khai; không tin header do client tự giả mạo.
- [ ] **Operational** — Có quy trình xoay vòng credential và thu hồi token khi có sự cố.

**Lưu ý:** CORS không phải cơ chế xác thực hoặc authorization. Nó chủ yếu điều khiển việc trình duyệt cho phép JavaScript ở origin nào đọc response. API vẫn phải xác minh danh tính và quyền trên server.

## 5. Xác thực và authorization theo field

Một user có thể được phép gọi `Query.account` nhưng không được xem mọi field lồng bên dưới. Authorization phải được áp dụng tại ranh giới dữ liệu và hành động, kể cả khi client tự tạo query khác với giao diện chính thức.

- [ ] **Release blocker** — Xác thực principal từ nguồn đáng tin cậy; không nhận `userId`, role hoặc tenant đáng tin từ GraphQL variables để quyết định danh tính.
- [ ] **Release blocker** — Mỗi Query, Mutation và field nhạy cảm kiểm tra quyền tương ứng.
- [ ] **Release blocker** — Quyền truy cập object được kiểm tra theo owner, tenant hoặc quan hệ nghiệp vụ; biết ID không đồng nghĩa có quyền đọc object.
- [ ] **Release blocker** — Mutation kiểm tra quyền trên đối tượng đích và từng hành động, không chỉ kiểm tra quyền gọi endpoint.
- [ ] **High** — Quy tắc bảo mật được đặt ở service/domain layer hoặc method security để không bị bỏ qua khi cùng service được gọi từ REST, message handler hay job.
- [ ] **High** — Các field trả dữ liệu nhạy cảm có kiểm thử cho anonymous, user hợp lệ, user sai tenant và user thiếu quyền.
- [ ] **High** — Phản hồi khi không có quyền tuân thủ chính sách sản phẩm: trả lỗi phù hợp hoặc che giấu sự tồn tại của tài nguyên khi cần.
- [ ] **High** — Kiểm tra quyền được thực hiện ở mỗi event của Subscription nếu quyền hoặc trạng thái đối tượng có thể thay đổi trong thời gian stream đang mở.
- [ ] **Operational** — Log audit cho hành động quan trọng có actor, action, target và thời điểm; không ghi credential hoặc payload nhạy cảm.

Có thể dùng Spring Security method security, chẳng hạn `@PreAuthorize`, trên resolver hoặc service. Dù chọn vị trí nào, cần kiểm tra toàn bộ đường gọi. Một annotation ở resolver không bảo vệ service nếu service còn được gọi qua đường khác; ngược lại, chỉ bảo vệ service cũng không thay thế kiểm tra quyền theo field nếu resolver ghép nhiều nguồn dữ liệu.

## 6. Validation, lỗi và dữ liệu đầu vào

GraphQL kiểm tra cú pháp, kiểu và cấu trúc operation, nhưng không tự biết mọi quy tắc nghiệp vụ của ứng dụng.

- [ ] **Release blocker** — Input được validate ở server: độ dài chuỗi, miền giá trị, định dạng, giới hạn số phần tử và các trường bắt buộc.
- [ ] **Release blocker** — Kiểm tra quy tắc nghiệp vụ và trạng thái hiện tại trước khi ghi dữ liệu.
- [ ] **Release blocker** — Không trả stack trace, SQL, tên host nội bộ, đường dẫn file, secret hoặc exception message thô cho client production.
- [ ] **High** — Lỗi dự kiến được chuyển thành GraphQL error có mã/extension ổn định và thông điệp có thể hành động.
- [ ] **High** — Lỗi hệ thống không dự kiến được ghi log phía server với trace ID; client nhận thông báo tổng quát.
- [ ] **High** — Quyết định giữa partial data và fail-fast được xác định theo field, nullability và yêu cầu nghiệp vụ.
- [ ] **High** — Mutation có chiến lược idempotency khi client có thể retry sau timeout hoặc mất kết nối.
- [ ] **Operational** — Error code và tài liệu API được thống nhất để client không phải phân tích chuỗi message tự do.

Spring for GraphQL hỗ trợ xử lý exception bằng `DataFetcherExceptionResolver`/`DataFetcherExceptionResolverAdapter` và `@GraphQlExceptionHandler` ở nơi phù hợp với phiên bản đang dùng. Không để nhiều handler tạo cách ánh xạ lỗi mâu thuẫn. Hãy phân biệt lỗi validation, lỗi nghiệp vụ, lỗi authorization và lỗi dependency.

Ví dụ response có thể có cả `data` và `errors`:

```json
{
  "data": {
    "book": {
      "id": "b-101",
      "title": "Spring in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải thông tin tác giả",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_LOOKUP_FAILED"
      }
    }
  ]
}
```

Đây là ví dụ minh họa hợp đồng lỗi; mã HTTP, `data` và nội dung error thực tế phụ thuộc transport, loại lỗi và cấu hình server. Không dùng HTTP 200 làm bằng chứng rằng operation thành công hoàn toàn; client cần kiểm tra `errors`.

## 7. Kiểm soát chi phí query và chống lạm dụng

GraphQL cho phép client chọn field, lồng quan hệ và dùng alias. Một request duy nhất có thể tạo ra lượng công việc lớn hơn nhiều request REST thông thường.

- [ ] **Release blocker** — Mọi danh sách có giới hạn page size tối đa được enforce ở server.
- [ ] **Release blocker** — Query depth và/hoặc query complexity có giới hạn phù hợp với schema và dữ liệu.
- [ ] **Release blocker** — Request có timeout; thời gian chờ dependency và database nằm trong ngân sách request.
- [ ] **High** — Giới hạn kích thước request, số phần tử input, số alias hoặc các cấu trúc query có thể tạo fan-out lớn.
- [ ] **High** — Rate limit theo principal, client hoặc IP phù hợp; operation đắt tiền có thể cần giới hạn theo cost.
- [ ] **High** — Persisted query/allowlist được cân nhắc cho client có tập operation đã biết; server xử lý an toàn query không được phép.
- [ ] **High** — Introspection được quản lý theo yêu cầu sản phẩm và threat model; không xem việc tắt introspection là biện pháp thay thế authorization.
- [ ] **Operational** — Dashboard theo dõi query cost, depth, page size, response bytes và tỷ lệ bị từ chối do vượt giới hạn.

Depth limit không đủ để chặn mọi query đắt tiền. Một field có thể trả về hàng nghìn phần tử dù query chỉ sâu hai cấp. Complexity nên tính đến số lượng phần tử, pagination, field có chi phí cao và quan hệ fan-out. Các instrumentation/validator cụ thể phụ thuộc phiên bản GraphQL Java và cấu hình `GraphQlSource`; xác minh chúng thật sự được gọi trước khi phát hành.

## 8. Hiệu năng resolver, N+1 và DataLoader

Resolver cần thực hiện lượng công việc có giới hạn và truy cập backend hiệu quả. Đo trên query shape thực tế, bởi resolver chỉ chạy khi field đó được yêu cầu.

- [ ] **Release blocker** — Các operation phổ biến được kiểm thử tải với số lượng record, concurrency và query shape gần production.
- [ ] **High** — Field quan hệ không tạo N+1; dùng `@BatchMapping` hoặc DataLoader khi nhiều source object cần cùng một loại dữ liệu.
- [ ] **High** — Batch loader truy vấn theo tập khóa thật sự; không gọi repository đơn lẻ trong vòng lặp batch.
- [ ] **High** — Kết quả batch được ánh xạ đúng source/key; không dựa vào thứ tự trả về không được database bảo đảm.
- [ ] **High** — Batch size và số bind parameter có giới hạn; danh sách gốc được phân trang.
- [ ] **High** — Không tải cột/quan hệ không cần thiết; query plan và index được kiểm tra cho truy vấn quan trọng.
- [ ] **High** — Resolver không giữ transaction database trong khi chờ dependency ngoài nếu không cần thiết.
- [ ] **High** — Trong WebFlux, không gọi API blocking trực tiếp trên event-loop; cô lập công việc blocking theo scheduler phù hợp hoặc dùng API reactive.
- [ ] **High** — Gọi dependency song song có giới hạn concurrency và timeout; tránh fan-out không kiểm soát.
- [ ] **Operational** — Cache có TTL, invalidation, tenant và authorization scope rõ ràng; dữ liệu người dùng không bị chia sẻ sai.

Ví dụ batch resolver:

```java
@BatchMapping(typeName = "Book", field = "author")
Map<Book, Author> author(List<Book> books) {
    Set<UUID> authorIds = books.stream()
            .map(Book::authorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

    Map<UUID, Author> authors = authorService.findByIds(authorIds);
    Map<Book, Author> result = new HashMap<>();

    for (Book book : books) {
        result.put(book, book.authorId() == null
                ? null
                : authors.get(book.authorId()));
    }
    return result;
}
```

Ví dụ giả định `findByIds` dùng bulk query, áp dụng tenant/authorization và trả map theo ID. Nếu service vẫn gọi `findById` cho từng phần tử, N+1 vẫn còn. Cần đo SQL count và số lần gọi backend để chứng minh hiệu quả.

DataLoader thường phục vụ việc gom và cache key trong phạm vi một lần thực thi GraphQL. Không biến cache theo request thành cache dùng chung giữa người dùng. Với dữ liệu thay đổi trong cùng request hoặc loader tùy chỉnh, xem xét chính sách clear/prime cache và tính nhất quán.

## 9. Database và dịch vụ phụ thuộc

- [ ] **Release blocker** — Connection pool có giới hạn; pool wait và timeout được quan sát.
- [ ] **High** — Truy vấn quan trọng có index và execution plan phù hợp với dữ liệu thực tế.
- [ ] **High** — Mọi HTTP/gRPC dependency có connect/read/response timeout thích hợp.
- [ ] **High** — Retry có giới hạn, backoff và chỉ áp dụng cho thao tác an toàn để retry.
- [ ] **High** — Circuit breaker/bulkhead được cân nhắc cho dependency dễ suy giảm; không tạo thêm tải khi hệ thống đích quá tải.
- [ ] **High** — Transaction có phạm vi ngắn, isolation level phù hợp và không bao quanh công việc ngoài database kéo dài.
- [ ] **High** — Các mutation có xử lý cạnh tranh ghi, unique constraint và tính toàn vẹn dữ liệu ở database.
- [ ] **Operational** — Có dashboard cho pool usage, slow query, lock wait, dependency latency, timeout và error rate.

Timeout phía GraphQL không thay thế timeout database hoặc HTTP client. Nếu request bị hủy, kiểm tra việc hủy có được truyền tới công việc bên dưới hay không; nếu không, backend vẫn có thể tiếp tục tiêu tốn tài nguyên sau khi client đã ngắt kết nối.

## 10. Mutation và tính nhất quán

Mutation thường tạo tác động không thể tự động hoàn tác. Client có thể timeout dù server đã commit thành công, vì vậy retry phải được thiết kế rõ ràng.

- [ ] **Release blocker** — Mỗi mutation xác định rõ actor, đối tượng bị thay đổi và quyền thực hiện.
- [ ] **Release blocker** — Giao dịch có quy tắc commit/rollback rõ; không trả thành công trước khi thao tác bắt buộc hoàn tất.
- [ ] **Release blocker** — Có kiểm soát idempotency hoặc cơ chế tra cứu kết quả khi client retry thao tác có side effect.
- [ ] **High** — Input validation và domain validation chạy trước khi ghi dữ liệu.
- [ ] **High** — Xử lý duplicate request, optimistic locking hoặc xung đột cập nhật theo yêu cầu nghiệp vụ.
- [ ] **High** — Event phát ra sau commit hoặc dùng transactional outbox khi cần bảo đảm đồng bộ giữa database và message broker.
- [ ] **Operational** — Audit trail ghi nhận các mutation quan trọng và kết quả thực hiện.

Không retry mutation chỉ vì client không nhận được response. Trước tiên cần biết server đã thực hiện hay chưa. Với thao tác thanh toán, tạo đơn hàng hoặc thay đổi trạng thái, idempotency key nên được kiểm tra ở server và có ràng buộc lưu trữ phù hợp.

## 11. Subscription và kết nối dài hạn

Nếu module không cung cấp Subscription, đánh dấu `N/A` và xác nhận production không mở transport tương ứng. Nếu có, kiểm tra riêng vòng đời kết nối và event.

- [ ] **Release blocker** — Transport và subprotocol được cấu hình rõ; chỉ cho phép kết nối từ client/origin hợp lệ theo chính sách.
- [ ] **Release blocker** — Xác thực tại kết nối và authorization cho subscription/event được kiểm tra; token hết hạn hoặc bị thu hồi có hành vi xác định.
- [ ] **Release blocker** — Quyền truy cập dữ liệu được đánh giá lại khi event được phát, nhất là khi membership/tenant/role thay đổi.
- [ ] **High** — Có giới hạn số connection và số subscription trên principal/client.
- [ ] **High** — Có chiến lược heartbeat, timeout idle, reconnect và graceful shutdown.
- [ ] **High** — Có backpressure hoặc giới hạn hàng đợi; client chậm không làm bộ nhớ server tăng vô hạn.
- [ ] **High** — Subscription được đóng và giải phóng tài nguyên khi client ngắt kết nối hoặc hết quyền.
- [ ] **Operational** — Metric theo dõi connection active, event rate, dropped event, queue size và thời gian sống của subscription.
- [ ] **Operational** — Nếu chạy nhiều instance, cơ chế pub/sub hoặc event distribution bảo đảm event đến đúng subscriber theo kiến trúc triển khai.

Không dùng thời gian response HTTP ngắn để đánh giá sức khỏe của subscription dài hạn. Đo độ trễ event, số kết nối và tốc độ tiêu thụ riêng.

## 12. Kiểm thử trước phát hành

Một suite chỉ kiểm tra happy path không đủ cho GraphQL production. Kiểm thử cần bao phủ operation, field lồng nhau, lỗi từng phần và giới hạn tài nguyên.

- [ ] **Release blocker** — Unit test cho domain/service quan trọng và quy tắc authorization.
- [ ] **Release blocker** — Integration test nạp schema thật và thực thi Query/Mutation quan trọng.
- [ ] **Release blocker** — Kiểm thử anonymous, user hợp lệ, thiếu quyền, sai tenant và object không tồn tại.
- [ ] **Release blocker** — Kiểm thử nullability, resolver lỗi, partial data và GraphQL `errors`.
- [ ] **High** — Kiểm thử N+1: xác nhận batch loader chạy đúng và SQL/backend call count giảm.
- [ ] **High** — Kiểm thử pagination, page size tối đa, query depth/complexity và request vượt giới hạn.
- [ ] **High** — Kiểm thử dependency timeout, database unavailable, retry và cancellation.
- [ ] **High** — Kiểm thử mutation duplicate/retry và cạnh tranh cập nhật.
- [ ] **High** — Kiểm thử tải và soak test với concurrency, payload và phân bố dữ liệu gần production.
- [ ] **High** — Nếu có Subscription, kiểm thử auth, reconnect, client chậm, ngắt kết nối và nhiều instance.
- [ ] **Operational** — Có smoke test sau deploy cho health, schema và các operation quan trọng.

Ví dụ kiểm thử bằng `GraphQlTester`:

```java
graphQlTester.document("""
        query Books($first: Int!) {
            books(first: $first) {
                id
                title
                author { id name }
            }
        }
        """)
    .variable("first", 20)
    .execute()
    .path("books")
    .entityList(BookView.class)
    .hasSize(2);
```

`BookView` là DTO kiểm thử của ứng dụng; fixture trong test có hai sách nên assertion dùng `hasSize(2)`. Test này minh họa kiểm tra pagination và field quan hệ; cần bổ sung assertion cho dữ liệu, lỗi, quyền và số lần gọi repository. Cấu hình `GraphQlTester` có thể là tester trực tiếp hoặc tester qua HTTP tùy mục tiêu: kiểm tra resolver/schema hay cả transport/security chain.

## 13. Observability: log, metric và trace

Production readiness đòi hỏi trả lời được operation nào chậm, field nào gây lỗi và dependency nào chiếm thời gian mà không phải bật log nhạy cảm trên diện rộng.

- [ ] **Release blocker** — Mỗi request có correlation/trace ID xuyên qua gateway, GraphQL, service và dependency.
- [ ] **High** — Có metric request count, error rate, p50/p95/p99 latency và throughput.
- [ ] **High** — Có quan sát theo operation và data fetcher/field ở mức cardinality kiểm soát được.
- [ ] **High** — Có trace cho resolver và span con quan trọng như JDBC, HTTP client hoặc gRPC.
- [ ] **High** — Dashboard hiển thị connection pool, thread/worker pool, CPU, heap, GC, queue và dependency health.
- [ ] **High** — Log có operation name/hash, trace ID và error code; không ghi access token, cookie, raw variables hay PII.
- [ ] **High** — Metric label không chứa user ID, raw query, variables, URL tùy ý hoặc giá trị cardinality cao.
- [ ] **High** — Sampling được cấu hình để vẫn giữ trace của lỗi/chậm theo chính sách quan sát.
- [ ] **Operational** — Có dashboard phân biệt latency tổng với resolver/database/dependency latency.
- [ ] **Operational** — Retention, access control và redaction của telemetry phù hợp chính sách dữ liệu.

Spring for GraphQL tích hợp Micrometer Observation. Có thể dùng observation/instrumentation ở mức GraphQL request và data fetcher; tên observation, tag và khả năng có sẵn phụ thuộc phiên bản cùng cấu hình `GraphQlSource`. Kiểm tra trace thực tế trong môi trường staging. Không giả định tên tag trong ví dụ tài liệu là tên tag của ứng dụng.

## 14. Triển khai, cấu hình môi trường và rollback

- [ ] **Release blocker** — Artifact được build từ commit đã review; dependency và image được quản lý phiên bản.
- [ ] **Release blocker** — Secret và cấu hình production được inject từ hệ thống quản lý cấu hình/bí mật, không đóng gói cứng vào image.
- [ ] **Release blocker** — Database migration tương thích với chiến lược deploy/rollback; migration phá vỡ tương thích có kế hoạch nhiều bước.
- [ ] **High** — Liveness và readiness probe phân biệt tiến trình sống với khả năng nhận traffic.
- [ ] **High** — Graceful shutdown ngừng nhận request mới, cho request đang chạy thời gian hoàn tất hợp lý và đóng subscription/kết nối.
- [ ] **High** — CPU, memory, replica count và autoscaling được kiểm tra dưới tải dự kiến.
- [ ] **High** — Canary/rolling deployment có health gate; schema và resolver tương thích giữa các phiên bản cùng tồn tại trong quá trình rollout.
- [ ] **High** — Có rollback procedure đã diễn tập và biết rõ điều kiện kích hoạt.
- [ ] **Operational** — Config drift giữa staging và production được phát hiện; thay đổi cấu hình có review.

Đặc biệt với GraphQL schema, client có thể gọi field mới ngay khi một phần replica đã cập nhật. Rollout cần bảo đảm gateway/load balancer không gửi query mới đến replica chưa có schema/field đó, hoặc triển khai theo trình tự tương thích.

## 15. SLO, cảnh báo và runbook vận hành

- [ ] **Release blocker** — Có SLO cho latency và availability của các operation quan trọng.
- [ ] **High** — Alert dựa trên error budget/SLO burn hoặc ngưỡng có ý nghĩa, tránh cảnh báo chỉ vì một spike ngắn.
- [ ] **High** — Có cảnh báo cho p95/p99, error rate, timeout, saturation, connection pool exhaustion và dependency failure.
- [ ] **High** — Có dashboard phân biệt lỗi client (validation/authorization/rate limit) với lỗi server/dependency.
- [ ] **High** — Có runbook cho resolver chậm, N+1, database chậm, dependency timeout, tăng error rate và Subscription suy giảm nếu áp dụng.
- [ ] **High** — Xác định người nhận cảnh báo, escalation path và cách liên hệ on-call.
- [ ] **Operational** — Có quy trình post-incident review và theo dõi action item sau sự cố.
- [ ] **Operational** — Diễn tập khôi phục và rollback định kỳ.

Alert theo operation name hoặc field coordinate đã chuẩn hóa. Tránh alert/metric label theo query text hoặc input tự do vì cardinality có thể tăng không giới hạn.

## 16. Cổng quyết định phát hành

Trước khi phê duyệt, tổng hợp kết quả theo nhóm. Không lấy trung bình các mục để che lấp một release blocker.

| Nhóm | Điều kiện chấp nhận |
|---|---|
| Schema/API | Không có breaking change ngoài kế hoạch; nullability và pagination đã kiểm chứng |
| Security | Endpoint, authentication, field authorization, tenant isolation và secret handling đạt yêu cầu |
| Correctness | Query, Mutation, error mapping và partial data có kiểm thử phù hợp |
| Performance | Query cost có giới hạn; N+1 được xử lý; tải và dependency budget đạt SLO |
| Reliability | Timeout, pool, retry, cancellation, health probe và graceful shutdown đã kiểm tra |
| Observability | Dashboard, trace, alert và runbook đủ để phát hiện/khoanh vùng sự cố |
| Operations | Rollout, rollback, migration và on-call ownership được xác nhận |

Quyết định phát hành:

- **GO:** tất cả release blocker là `PASS`; mục High còn lại có owner, thời hạn và biện pháp giảm thiểu được chấp nhận; rollback sẵn sàng.
- **NO-GO:** còn release blocker `FAIL`/`TODO`, chưa chứng minh được quyền truy cập dữ liệu, hoặc không thể phát hiện và khôi phục sự cố nghiêm trọng.
- **GO WITH ACCEPTED RISK:** chỉ dùng khi người có thẩm quyền ghi nhận rõ mục High còn tồn tại, tác động, biện pháp giảm thiểu, thời hạn và điều kiện dừng/rollback. Không dùng trạng thái này để bỏ qua release blocker.

## 17. Mẫu biên bản readiness

Có thể sao chép mẫu sau vào ticket phát hành hoặc tài liệu review:

```text
Service:
Environment:
Release/version:
Commit:
Review date:
Reviewer:

Schema/API: PASS | FAIL | TODO | N/A
Security: PASS | FAIL | TODO | N/A
Validation/errors: PASS | FAIL | TODO | N/A
Query cost/performance: PASS | FAIL | TODO | N/A
Database/dependencies: PASS | FAIL | TODO | N/A
Mutation/consistency: PASS | FAIL | TODO | N/A
Subscription (if enabled): PASS | FAIL | TODO | N/A
Tests/load: PASS | FAIL | TODO | N/A
Observability: PASS | FAIL | TODO | N/A
Deployment/rollback: PASS | FAIL | TODO | N/A
SLO/runbooks/on-call: PASS | FAIL | TODO | N/A

Release blockers:
Accepted risks (owner, due date, mitigation):
Evidence links:
Rollback trigger and procedure:
Decision: GO | NO-GO | GO WITH ACCEPTED RISK
Approver:
```

Biên bản cần trỏ đến bằng chứng thật như pipeline run, test report, dashboard, trace, security review hoặc runbook. Không ghi `PASS` chỉ dựa trên lời xác nhận miệng.

## 18. Thực hành tổng hợp

Áp dụng checklist cho một Spring for GraphQL service mẫu hoặc service đang phát triển:

1. Chọn ba operation quan trọng nhất, gồm ít nhất một Query và một Mutation. Nếu có Subscription, chọn thêm một luồng event.
2. Lập danh sách field nhạy cảm và vẽ đường đi từ principal đến resolver, service và database. Kiểm tra tenant/owner ở từng đường đọc và ghi.
3. Chạy query có quan hệ lồng nhau với danh sách đủ lớn. Đo SQL count, batch size, p95/p99 và response bytes; sửa N+1 nếu phát hiện.
4. Gửi input sai, user thiếu quyền, query quá sâu/quá rộng, dependency timeout và mutation retry. Ghi nhận response GraphQL, log server và metric tương ứng.
5. Kiểm tra trace để xác nhận có thể phân biệt thời gian resolver, database và dependency.
6. Diễn tập rollout một phiên bản mới, health check, graceful shutdown và rollback trong staging.
7. Điền mẫu biên bản readiness; mọi mục `FAIL` hoặc `TODO` phải có owner và hành động tiếp theo.

## 19. Checklist nhanh trước giờ phát hành

- [ ] Schema tương thích và resolver đã được nạp đầy đủ.
- [ ] HTTPS, authentication, field authorization và tenant isolation hoạt động.
- [ ] Input validation và error mapping không làm lộ thông tin nội bộ.
- [ ] Pagination, query depth/complexity, timeout và rate limit được enforce.
- [ ] N+1 đã được xử lý; batch và DataLoader không vượt giới hạn backend.
- [ ] Query/Mutation quan trọng đã qua integration, security và load test.
- [ ] Dependency timeout, retry, transaction và idempotency được xác nhận.
- [ ] Log, metric, trace, dashboard và alert đã hoạt động trong staging.
- [ ] Health probe, graceful shutdown, migration và rollback đã được kiểm tra.
- [ ] On-call biết runbook, người phê duyệt và điều kiện rollback.

## 20. Tiêu chí hoàn thành

Một Spring for GraphQL API sẵn sàng production khi hợp đồng schema có thể duy trì, mọi đường đọc/ghi đều bảo vệ dữ liệu đúng quyền, query có chi phí giới hạn, resolver và dependency đáp ứng SLO, lỗi không làm lộ thông tin, và đội vận hành có thể phát hiện, chẩn đoán, giảm thiểu rồi khôi phục sự cố. Checklist chỉ có giá trị khi từng kết luận gắn với bằng chứng và người chịu trách nhiệm; việc đánh dấu đủ ô mà không kiểm tra thực tế không tạo ra readiness.
