# Runbook khi resolver chậm

Resolver chậm làm tăng thời gian thực thi GraphQL, thường biểu hiện thành p95/p99 cao, request timeout hoặc một số field trả về chậm dù endpoint vẫn khỏe. Runbook này hướng dẫn khoanh vùng từ request GraphQL đến resolver, database và dịch vụ phụ thuộc; sau đó chọn biện pháp giảm tải, sửa nguyên nhân và xác nhận hiệu quả.

Phạm vi áp dụng là ứng dụng Spring for GraphQL dùng Query, Mutation, Subscription, `@SchemaMapping`, `@BatchMapping` và DataLoader. Quy trình tập trung vào resolver phía server. Nếu thời gian chậm nằm ở mạng, gateway hoặc client, vẫn cần ghi nhận ranh giới đó để chuyển đúng nhóm xử lý.

## Mục tiêu và nguyên tắc chẩn đoán

Một request GraphQL đi qua nhiều lớp: HTTP hoặc WebSocket, parse và validate document, lập kế hoạch thực thi, gọi các data fetcher/resolver, truy cập database hoặc dịch vụ ngoài, rồi serialize kết quả. Resolver chỉ là một mắt xích. Đừng kết luận resolver có lỗi chỉ từ tổng thời gian HTTP.

Khi xử lý sự cố, hãy trả lời lần lượt bốn câu hỏi:

1. Request nào chậm: operation, phiên bản ứng dụng, tenant hoặc nhóm người dùng nào, và trong khoảng thời gian nào?
2. Thời gian nằm ở đâu: chờ server, thực thi field, database, dịch vụ ngoài hay serialize response?
3. Chi phí tăng theo yếu tố nào: số phần tử trong danh sách, độ sâu truy vấn, số lần gọi backend, kích thước response hay mức tải đồng thời?
4. Thay đổi nào làm giảm latency mà vẫn giữ đúng dữ liệu, quyền truy cập và hành vi API?

Ưu tiên trace và số liệu có thể đối chiếu. Log một dòng “resolver mất 2 giây” không đủ nếu thiếu operation, field path, trace ID và thời gian của các dependency.

## Dấu hiệu cần kích hoạt runbook

- p95 hoặc p99 của GraphQL endpoint tăng vượt SLO, dù lưu lượng không tăng tương ứng.
- Một operation hoặc một field cụ thể chậm trong khi các operation khác bình thường.
- Thời gian phản hồi tăng theo số phần tử trả về, chẳng hạn truy vấn 10 bản ghi nhanh nhưng 100 bản ghi rất chậm.
- Số câu SQL hoặc số lần gọi dịch vụ ngoài tăng gần tuyến tính theo số object trong response.
- CPU, connection pool, worker pool hoặc hàng đợi tăng cao; request bắt đầu timeout hoặc bị hủy.
- Response có `errors` hoặc dữ liệu một phần do resolver/dependency timeout, lỗi hoặc bị từ chối.

Đối với Subscription, cần phân biệt thời gian thiết lập subscription, độ trễ của từng event và tốc độ tiêu thụ stream. Không dùng p95 của HTTP request ngắn để kết luận một subscription dài hạn đang khỏe.

## Quy trình xử lý 15 bước

### 1. Xác nhận phạm vi và mức độ ảnh hưởng

Ghi lại thời điểm bắt đầu, SLO bị vi phạm, tỷ lệ request ảnh hưởng, endpoint, môi trường, phiên bản ứng dụng và thay đổi vừa triển khai. Xác định sự cố ảnh hưởng toàn bộ GraphQL API hay chỉ một operation/field. So sánh với baseline cùng khung giờ để tránh nhầm đỉnh tải thông thường với sự cố.

Nếu lỗi đang lan rộng, ưu tiên khôi phục dịch vụ: giảm tải operation gây quá tải, giới hạn concurrency hoặc rollback bản phát hành liên quan theo quy trình vận hành của hệ thống. Ghi lại từng biện pháp giảm nhẹ và thời điểm áp dụng để có thể đối chiếu số liệu.

### 2. Thu thập một request đại diện

Chọn một request chậm có thể tái hiện và ghi nhận:

- `operationName`, loại operation và hash của document hoặc persisted query ID.
- Field path nghi vấn, ví dụ `Query.books[12].author`.
- Trace ID, request ID, thời điểm, phiên bản ứng dụng và tenant đã được ẩn danh.
- Số lượng phần tử, độ sâu và hình dạng response; loại bỏ giá trị nhạy cảm khỏi variables.
- Thời gian tổng, trạng thái HTTP, số lượng GraphQL error và việc request có bị timeout/hủy hay không.

Không ghi access token, cookie, mật khẩu, dữ liệu cá nhân hoặc toàn bộ variables vào log. Khi cần tái hiện, dùng dữ liệu giả lập hoặc fixture đã được làm sạch và giữ nguyên hình dạng truy vấn gây chậm.

### 3. Tách thời gian client, gateway và ứng dụng

Đối chiếu thời gian client đo được với thời gian gateway và server. Nếu client thấy 4 giây nhưng server chỉ ghi nhận 300 ms, kiểm tra mạng, proxy, hàng đợi gateway và truyền response. Nếu server cũng mất gần 4 giây, tiếp tục lần theo trace bên trong ứng dụng.

Đảm bảo các đồng hồ được đồng bộ và trace context được truyền qua gateway. Sai lệch đồng hồ hoặc trace bị đứt có thể làm thứ tự span gây hiểu nhầm.

### 4. Mở trace của request GraphQL

Spring for GraphQL tích hợp Micrometer Observation. Các instrumentation như `GraphQlObservationInstrumentation` và `DataFetcherObservationInstrumentation` có thể cung cấp quan sát ở mức request và data fetcher, tùy phiên bản Spring for GraphQL và cách cấu hình `GraphQlSource`. Với Spring Boot, kiểm tra instrumentation thực tế đã được auto-configure hoặc cấu hình trong ứng dụng; tránh đăng ký trùng.

Mở trace chậm và tìm span dài nhất. Xác định span đó là parse/validate, data fetcher, JDBC, HTTP client hay một công việc khác. Nếu trace chỉ có span HTTP tổng, bổ sung quan sát cho data fetcher và dependency trước khi suy luận từ log rời rạc.

Tên observation, span và tag có thể khác theo phiên bản hoặc convention tùy chỉnh. Dùng tên thực tế từ hệ thống telemetry của ứng dụng; không xây dashboard dựa trên một tên tag giả định.

### 5. Khoanh vùng field path và resolver

Tìm data fetcher có thời gian dài, số lần gọi bất thường hoặc nhiều span con. Field coordinate như `Book.author` giúp xác định resolver tương ứng. Đối chiếu với schema và controller đang xử lý field đó:

- `@QueryMapping` hoặc `@MutationMapping` cho field gốc của operation.
- `@SchemaMapping` cho field được resolve từ object cha.
- `@BatchMapping` cho việc nạp cùng một field của nhiều object theo lô.

Một operation có thể gọi cùng resolver nhiều lần cho nhiều object. Vì vậy hãy xem cả tổng thời gian, số lần gọi và thời gian trung bình mỗi lần. Một resolver 5 ms chạy 200 lần có thể gây chậm hơn resolver 300 ms chỉ chạy một lần.

### 6. Kiểm tra số lượng và thời gian truy vấn database

Đối chiếu trace với metric của connection pool và database. Kiểm tra số câu SQL trên một request, thời gian từng câu, số hàng đọc/trả về, lock wait, connection wait và query plan. Tìm các mẫu:

- Một câu truy vấn tương tự lặp lại theo từng object.
- Truy vấn lọc hoặc join không dùng index phù hợp.
- Đọc quá nhiều cột hoặc hàng trong khi GraphQL chỉ yêu cầu một phần dữ liệu.
- Nhiều truy vấn nhỏ nối tiếp thay vì một truy vấn theo tập ID.
- Connection pool cạn khiến resolver chủ yếu chờ lấy connection.

Dùng công cụ explain của database trên môi trường phù hợp và với quyền an toàn. Với hệ thống hỗ trợ, xem execution plan và buffer/read statistics; không chạy lệnh phân tích có thực thi đầy đủ trên production nếu có thể gây tải hoặc khóa ngoài dự kiến.

### 7. Kiểm tra dịch vụ phụ thuộc

Nếu resolver gọi REST, gRPC, search, cache hoặc dịch vụ nội bộ, kiểm tra span con, DNS, connection pool, timeout, retry và tỷ lệ lỗi. Một retry tự động có thể nhân số lần gọi khi dependency đang quá tải. Xác nhận timeout của dependency nhỏ hơn ngân sách thời gian còn lại của request và retry có giới hạn.

Nếu nhiều resolver cùng gọi một dịch vụ, xác định chúng có thể gom request, dùng API bulk hoặc tái sử dụng kết quả trong phạm vi request hay không. Không tạo cache dùng chung giữa người dùng nếu dữ liệu phụ thuộc quyền hoặc tenant.

### 8. Kiểm tra mức bão hòa của ứng dụng

Đối chiếu latency với CPU, heap, GC pause, thread/worker pool, hàng đợi, connection pool và số request đang chạy. Một resolver đồng bộ có thể giữ thread trong lúc chờ I/O. Trong ứng dụng WebFlux, gọi API blocking trực tiếp trên event-loop có thể làm chậm nhiều request cùng lúc.

Kiểm tra log thread starvation, rejected task, timeout và pool exhaustion. Nếu tài nguyên đã bão hòa, tăng timeout thường chỉ giữ request và connection lâu hơn. Trước tiên hãy giảm concurrency hoặc lưu lượng gây tải, sau đó sửa nguồn gây chờ.

### 9. Phân loại nguyên nhân chính

Chọn nhóm có bằng chứng rõ nhất:

| Nhóm nguyên nhân | Dấu hiệu thường gặp | Hướng xử lý đầu tiên |
|---|---|---|
| N+1 | Số SQL hoặc lời gọi backend tăng theo số object | Gom tải bằng `@BatchMapping` hoặc DataLoader |
| Truy vấn kém | Một vài SQL chiếm phần lớn thời gian | Sửa index, join, projection hoặc query plan |
| Dependency chậm | Span HTTP/gRPC/search dài hoặc retry tăng | Timeout hợp lý, bulk API, giới hạn retry, xử lý sự cố dependency |
| Bão hòa tài nguyên | Pool wait, hàng đợi, GC hoặc CPU tăng | Giảm concurrency/tải và xử lý điểm nghẽn |
| Query quá rộng | Nhiều field lồng nhau, danh sách lớn, response lớn | Pagination, giới hạn depth/complexity và kích thước trang |
| Công việc trong resolver | CPU profile cho thấy tính toán/serialize chiếm thời gian | Giảm tính toán lặp, tối ưu cấu trúc dữ liệu và payload |

Có thể có nhiều nguyên nhân cùng lúc. Chọn một nguyên nhân có tác động lớn nhất để sửa trước, rồi đo lại vì việc loại bỏ điểm nghẽn đầu tiên có thể làm lộ điểm nghẽn kế tiếp.

### 10. Áp dụng biện pháp giảm nhẹ có kiểm soát

Trong lúc chuẩn bị bản sửa, cân nhắc giới hạn tạm thời cho operation gây tải, giảm kích thước page, hạ concurrency đến dependency, tắt một phần dữ liệu tùy chọn hoặc rollback thay đổi mới. Chỉ áp dụng khi hợp đồng API và quy trình vận hành cho phép.

Với Mutation, không tự động retry chỉ vì client nhận timeout: mutation có thể đã được thực hiện ở server. Cần idempotency key hoặc cơ chế xác định kết quả trước khi retry. Với Query, retry cũng phải có giới hạn và không được khuếch đại tải khi dependency đang suy giảm.

### 11. Sửa N+1 bằng `@BatchMapping` hoặc DataLoader

N+1 thường xuất hiện khi resolver của field con tải dữ liệu riêng cho từng object cha. Ví dụ, truy vấn 50 sách rồi resolve tác giả từng cuốn có thể tạo 1 truy vấn lấy sách và 50 truy vấn lấy tác giả.

Resolver đơn lẻ có thể trông rất đơn giản:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Với dữ liệu có thể tải theo lô, chuyển sang `@BatchMapping`:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    Map<Book, Author> author(List<Book> books) {
        Set<UUID> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<UUID, Author> authors = authorService.findByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            Author author = book.authorId() == null
                    ? null
                    : authors.get(book.authorId());
            result.put(book, author);
        }
        return result;
    }
}
~~~

Ví dụ giả định `Book` là record có `authorId()`, `AuthorService.findByIds` thực hiện một truy vấn theo tập ID và trả về map theo ID. Hãy điều chỉnh kiểu dữ liệu cho domain thực tế. `@BatchMapping` là cách khai báo thuận tiện để Spring for GraphQL đăng ký batch loader; DataLoader gom các khóa được yêu cầu trong cùng quá trình thực thi request và phân phối kết quả về đúng object nguồn.

Khi triển khai, kiểm tra các điểm sau:

- Truy vấn batch thực sự giảm số SQL/lời gọi backend; không chỉ chuyển N+1 sang bên trong `findByIds`.
- Kết quả được ánh xạ đúng với từng object nguồn; xử lý rõ trường hợp thiếu dữ liệu hoặc ID null.
- Batch vẫn áp dụng tenant filter và quyền truy cập. Không tải dữ liệu của tenant khác chỉ vì ID xuất hiện trong cùng batch.
- DataLoader cache theo request là phù hợp với dữ liệu và quyền. Tránh chia sẻ cache giữa request hoặc người dùng nếu kết quả có thể khác nhau.
- Không đăng ký đồng thời hai resolver cho cùng field, ví dụ vừa giữ `@SchemaMapping` cũ vừa thêm `@BatchMapping` cho `Book.author`.
- Nếu batch rất lớn, chia lô theo giới hạn của database hoặc dịch vụ phụ thuộc.

`@BatchMapping` phù hợp khi nhiều object cha cần cùng một field. Với quan hệ hoặc cách nạp dữ liệu phức tạp hơn, dùng `BatchLoaderRegistry` và DataLoader tường minh; giữ nguyên nguyên tắc batch theo request và ánh xạ kết quả đúng thứ tự/khóa.

### 12. Tối ưu resolver và ranh giới I/O

Sau khi xử lý N+1, xem lại công việc của resolver:

- Chỉ lấy các cột cần thiết; dùng projection hoặc truy vấn phù hợp với dữ liệu thực sự trả về.
- Dùng pagination cho danh sách; tránh tải toàn bộ quan hệ rồi mới cắt ở Java.
- Chuyển logic nghiệp vụ dùng chung vào service để có thể đo, kiểm thử và tái sử dụng.
- Tránh gọi `.block()` hoặc thao tác blocking trên event-loop của WebFlux. Chọn API reactive xuyên suốt hoặc cô lập công việc blocking trên scheduler phù hợp.
- Không giữ transaction database trong khi chờ gọi dịch vụ ngoài. Giữ transaction ngắn quanh thao tác database cần tính nhất quán.
- Giới hạn concurrency khi gọi nhiều dependency; chạy song song không giới hạn có thể làm hệ thống phụ thuộc quá tải hơn.
- Dùng cache chỉ khi có chính sách rõ ràng về TTL, invalidation, tenant và quyền truy cập.

Không tối ưu bằng cách trả dữ liệu cũ hoặc bỏ kiểm tra quyền để đạt latency thấp hơn. Nếu cần stale-while-revalidate hoặc cache, phải xác định rõ field nào chấp nhận dữ liệu cũ và trong bao lâu.

### 13. Giới hạn chi phí của query GraphQL

Một operation có thể yêu cầu nhiều field lồng nhau và danh sách lớn. Kết hợp các biện pháp:

- Pagination có giới hạn page size; kiểm tra giới hạn ở server thay vì tin giá trị client gửi.
- Giới hạn query depth và complexity theo khả năng của schema và backend.
- Dùng persisted query hoặc allowlist khi phù hợp với mô hình sản phẩm.
- Đặt timeout cho request và dependency; truyền ngân sách thời gian nhất quán qua các lớp.
- Theo dõi kích thước response và số object được resolve, không chỉ số request mỗi giây.

Depth limit đơn thuần không chặn mọi query đắt tiền: một field có thể rất tốn tài nguyên dù query nông. Complexity nên tính đến multiplicity của list, chi phí field và giới hạn trang. Thông báo lỗi cần đủ rõ cho client phát hiện query vượt giới hạn nhưng không để lộ thông tin nội bộ.

### 14. Kiểm chứng trước và sau khi phát hành

Tái chạy đúng operation đại diện với cùng hình dạng dữ liệu và concurrency. So sánh trước/sau:

| Chỉ số | Kỳ vọng sau sửa |
|---|---|
| p50, p95, p99 của operation | Giảm và ổn định dưới SLO |
| Số lần gọi resolver theo field | Không tăng theo số object khi đã batch |
| Số SQL/lời gọi backend trên request | Giảm theo dự kiến |
| Database/connection pool wait | Không tăng bất thường |
| CPU, heap, GC và thread pool | Không tạo điểm nghẽn mới |
| GraphQL errors và dữ liệu trả về | Không tăng lỗi; kết quả và quyền vẫn đúng |

Kiểm thử cả danh sách rỗng, một phần tử, nhiều phần tử, ID thiếu, dữ liệu không tồn tại và trường hợp nhiều tenant. Với DataLoader, kiểm tra batch được gọi đúng số lần và kết quả được gắn đúng source object. Dùng kiểm thử tải hoặc staging với dữ liệu có phân bố gần production; không suy ra hiệu quả từ một request đơn lẻ.

Phát hành theo canary hoặc từng nhóm traffic nếu hệ thống hỗ trợ. Theo dõi operation và field đã sửa, đặt ngưỡng rollback rõ ràng. Nếu latency giảm nhưng error rate, DB load hoặc memory tăng mạnh, bản sửa chưa đạt.

### 15. Đóng sự cố và ngăn tái diễn

Ghi lại nguyên nhân gốc, bằng chứng trong trace/metric, operation gây ảnh hưởng, thay đổi đã triển khai, biện pháp giảm nhẹ và số liệu trước/sau. Tạo việc theo dõi cho những điểm chưa xử lý như query khác có cùng mẫu N+1, thiếu pagination hoặc dependency chưa có timeout.

Bổ sung dashboard và cảnh báo theo operation/field có giá trị vận hành. Giữ nhãn metric có cardinality thấp: operation name đã chuẩn hóa, field coordinate hoặc nhóm endpoint. Không gắn raw query, variables, user ID hay giá trị tùy ý vào metric label. Với truy vấn nhạy cảm, lưu query hash và metadata đã làm sạch.

## Mẫu checklist khi trực sự cố

- [ ] Xác nhận operation, khoảng thời gian, SLO và số người dùng bị ảnh hưởng.
- [ ] Lấy trace ID và một request tái hiện đã loại bỏ dữ liệu nhạy cảm.
- [ ] Tách thời gian client/gateway khỏi thời gian server.
- [ ] Tìm span data fetcher và field path chậm nhất.
- [ ] Đối chiếu số SQL, query plan, connection wait và dependency spans.
- [ ] Kiểm tra CPU, GC, thread/worker pool và hàng đợi.
- [ ] Xác định N+1, query kém, dependency chậm, bão hòa hay query quá rộng.
- [ ] Áp dụng biện pháp giảm nhẹ có kiểm soát nếu ảnh hưởng đang lan rộng.
- [ ] Đo lại sau sửa với cùng query shape và concurrency.
- [ ] Xác nhận dữ liệu, quyền truy cập, GraphQL errors và SLO trước khi đóng.

## Các lỗi vận hành cần tránh

**Chỉ tăng timeout:** việc này có thể làm request giữ thread, connection và bộ nhớ lâu hơn trong lúc điểm nghẽn vẫn còn.

**Chỉ xem thời gian endpoint:** tổng latency không cho biết field hay dependency nào gây chậm. Hãy bổ sung trace ở data fetcher và các lời gọi I/O.

**Batch nhưng không giảm số truy vấn:** batch loader vẫn có thể gọi repository một lần cho từng ID. Đo số câu SQL thực tế sau thay đổi.

**Cache không xét quyền:** cache dùng chung có thể trả dữ liệu sai tenant hoặc sai người dùng. Phạm vi cache phải khớp phạm vi dữ liệu và authorization.

**Retry không giới hạn:** retry khuếch đại tải và có thể làm sự cố dependency nghiêm trọng hơn. Với mutation, retry còn có nguy cơ thực hiện hành động hai lần.

**Gắn nhãn metric bằng dữ liệu tự do:** raw query, variables và ID làm cardinality tăng mạnh, gây tốn bộ nhớ telemetry và có thể lộ dữ liệu nhạy cảm.

## Tiêu chí hoàn tất

Chỉ đóng runbook khi đã xác định được vị trí gây chậm bằng bằng chứng có thể truy vết; có biện pháp sửa hoặc giảm nhẹ được ghi nhận; latency và mức tải đã được đo lại; kết quả GraphQL cùng quyền truy cập vẫn đúng; và có người/việc theo dõi các rủi ro còn lại. Nếu chưa tìm ra nguyên nhân, ghi rõ phần telemetry còn thiếu và hành động cụ thể để thu thập bằng chứng trong lần tái hiện tiếp theo.
