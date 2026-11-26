# Khóa khi tiếp tục execution và xử lý yêu cầu đồng thời

*Chương: Lưu trữ execution · Module: SPRING_WEB_FLOW*

Một flow execution thường được tiếp tục qua nhiều HTTP request. Trình duyệt gửi flow execution key để Spring Web Flow tìm lại trạng thái đang chạy, nhận event và chuyển tới state tiếp theo. Trong thực tế, cùng một execution có thể nhận nhiều request gần như đồng thời: người dùng bấm nút hai lần, mở cùng quy trình ở hai tab, trình duyệt gửi lại request sau timeout hoặc proxy retry một request chưa nhận được phản hồi.

Nếu hai request cùng đọc và cập nhật một execution mà không có cơ chế phối hợp, chúng có thể làm mất cập nhật, thực hiện action hai lần hoặc tạo ra trạng thái không nhất quán. Khóa execution giúp tuần tự hóa phần xử lý cần truy cập trạng thái của cùng một execution. Tuy nhiên, khóa này chỉ giải quyết cạnh tranh trên trạng thái flow theo phạm vi repository và cách triển khai; nó không tự bảo đảm một thao tác nghiệp vụ chỉ xảy ra một lần, không thay thế transaction database và không đồng bộ mọi tài nguyên bên ngoài.

Module SPRING_WEB_FLOW tập trung mô hình hóa hành trình web qua state, event, transition và subflow, đồng thời thực hành quản lý scope, phiên, tích hợp Spring MVC, kiểm thử và phục hồi lỗi. Bài học này giải thích vì sao cần khóa khi resume execution, cách xử lý request đồng thời, các giới hạn của khóa trong môi trường nhiều node và cách phối hợp với idempotency cùng transaction.

Sau bài học, bạn có thể:

- Mô tả vòng đời một request tiếp tục flow execution.
- Nhận diện race condition khi nhiều request dùng cùng execution key.
- Giải thích mục đích của khóa theo execution và vùng xử lý tới hạn.
- Phân biệt khóa execution với transaction, khóa dữ liệu nghiệp vụ và idempotency.
- Xử lý double submit, nhiều tab, retry và execution key cũ.
- Đánh giá cách khóa hoạt động khi ứng dụng chạy trên nhiều node.
- Thiết kế kiểm thử cho request đồng thời và tình huống tranh chấp.

## 1. Execution key và việc tiếp tục flow

Flow definition là bản mô tả các state và transition. Flow execution là một lần chạy cụ thể của definition, mang theo state hiện tại và dữ liệu trong các scope. Khi một view của flow được render, Spring Web Flow cung cấp thông tin để request kế tiếp có thể tiếp tục đúng execution.

Một request tiếp tục flow thường đi qua các bước khái quát:

1. Trình duyệt gửi URL, execution key và event cần xử lý.
2. Spring MVC ánh xạ request tới FlowHandlerAdapter.
3. FlowExecutor dùng repository để tìm execution tương ứng.
4. Execution được khôi phục hoặc lấy ra theo chiến lược lưu trữ.
5. Flow xử lý event, chạy action và cập nhật state/scope.
6. Execution được lưu lại hoặc tạo continuation/key phù hợp cho lần tiếp theo.
7. Kết quả được trả về view hoặc redirect.

Sơ đồ đơn giản:

~~~mermaid
sequenceDiagram
    participant Browser as Trình duyệt
    participant MVC as Spring MVC
    participant Executor as FlowExecutor
    participant Repo as Execution Repository
    participant Flow as Flow execution
    Browser->>MVC: Request + execution key + event
    MVC->>Executor: Resume execution
    Executor->>Repo: Tìm và khóa execution
    Repo-->>Executor: Execution có thể tiếp tục
    Executor->>Flow: Xử lý event và action
    Flow-->>Executor: State và dữ liệu mới
    Executor->>Repo: Lưu execution/continuation
    Executor->>Repo: Nhả khóa
    Executor-->>MVC: View hoặc redirect
    MVC-->>Browser: HTTP response
~~~

Execution key là định danh phục vụ việc tìm execution hoặc continuation trong repository. Nó không phải khóa database và cũng không phải bằng chứng người dùng có quyền thao tác. Mọi request vẫn phải đi qua xác thực và kiểm tra quyền phù hợp.

## 2. Race condition khi hai request cùng tiếp tục một execution

Giả sử người dùng đang ở state review và gửi event confirm. Do bấm đúp, trình duyệt gửi hai request A và B gần như cùng lúc. Nếu cả hai request cùng đọc một bản trạng thái cũ, chúng có thể cùng thấy state là review và cùng chạy service xác nhận đơn hàng.

Một tình huống không có phối hợp:

~~~text
Execution ban đầu: state = review, order = draft

Request A                         Request B
----------                        ----------
Đọc execution ở review
                                  Đọc execution ở review
Chạy confirmOrder()
                                  Chạy confirmOrder()
Lưu state = completed
                                  Lưu state = completed

Kết quả có thể xảy ra:
- Service tạo hai đơn hàng hoặc gửi hai yêu cầu thanh toán.
- Một cập nhật ghi đè cập nhật còn lại.
- Log và dữ liệu nghiệp vụ không phản ánh đúng số lần người dùng thao tác.
~~~

Đây là race condition: kết quả phụ thuộc vào thứ tự xen kẽ của các thao tác. Việc mỗi request riêng lẻ đều chạy đúng không bảo đảm toàn bộ execution đúng khi các request chạy đồng thời.

Các nguyên nhân thường gặp:

- Người dùng bấm đúp nút submit hoặc nhấn Enter nhiều lần.
- JavaScript gửi lại request vì không nhận được response đúng hạn.
- Hai tab cùng giữ một URL hoặc execution key.
- Trình duyệt khôi phục request sau khi kết nối mạng chập chờn.
- Reverse proxy hoặc client retry một request có kết quả chưa rõ.
- Hai node ứng dụng cùng tiếp nhận request cho một execution được lưu chung.

Không nên giả định một người dùng chỉ tạo một request tại một thời điểm. Giao diện có thể vô hiệu hóa nút submit sau lần bấm đầu tiên để cải thiện trải nghiệm, nhưng đó chỉ là biện pháp phía client; server vẫn cần xử lý cạnh tranh.

## 3. Khóa execution bảo vệ điều gì?

Khóa execution là cơ chế loại trừ tương hỗ cho việc truy cập hoặc tiếp tục cùng một execution trong một khoảng xử lý. Khi request A đã lấy được khóa, request B cần chờ, bị từ chối hoặc được xử lý theo chính sách tranh chấp của repository. Mục tiêu là tránh để hai request đồng thời thao tác trên cùng một trạng thái flow có thể thay đổi.

Với khóa độc quyền, luồng xử lý khái quát như sau:

~~~mermaid
flowchart TD
    A[Request A và B cùng tới] --> B[Tra cứu khóa execution]
    B --> C{Request nào lấy được khóa?}
    C -->|A| D[A đọc execution]
    D --> E[A xử lý event và lưu trạng thái]
    E --> F[A nhả khóa]
    F --> G[B được tiếp tục hoặc xử lý theo chính sách]
    G --> H[Đọc trạng thái/continuation phù hợp]
    H --> I{Event còn hợp lệ?}
    I -->|Có| J[Tiếp tục xử lý]
    I -->|Không| K[Trả lỗi hoặc hướng dẫn tải lại]
~~~

Khóa cần gắn với đúng phạm vi execution mà repository bảo vệ. Một khóa toàn cục cho mọi flow sẽ làm các người dùng không liên quan phải chờ nhau và giảm khả năng xử lý đồng thời. Khóa theo execution cho phép hai execution độc lập tiếp tục song song, trong khi những request tranh chấp cùng một execution được phối hợp.

Khóa thường chỉ được giữ trong lúc repository/executor đang lấy, khôi phục, xử lý và lưu execution. Nó không nên tồn tại suốt thời gian người dùng đọc màn hình và suy nghĩ. Nếu người dùng mất 10 phút để điền form, ứng dụng không giữ một mutex trong 10 phút đó; khóa chỉ bảo vệ đoạn xử lý request khi người dùng gửi event.

Trong Spring Web Flow, repository và flow executor chịu trách nhiệm phối hợp vòng đời execution. Cách khóa cụ thể phụ thuộc implementation và cấu hình repository. Các implementation có thể dùng khóa trong bộ nhớ, cơ chế lưu trữ có đồng bộ hoặc một chiến lược khác. Khi thay repository mặc định bằng implementation riêng, cần xác minh hợp đồng khóa và cách release khi có exception.

## 4. Vùng tới hạn và vòng đời khóa

Vùng tới hạn là phần thao tác cần được bảo vệ để trạng thái execution không bị hai request cập nhật đồng thời. Một vòng đời tổng quát:

1. Nhận execution key từ request.
2. Lấy khóa tương ứng theo chính sách repository.
3. Đọc hoặc khôi phục execution sau khi đã có quyền truy cập an toàn.
4. Áp dụng event, chạy action và cập nhật scope.
5. Lưu execution hoặc continuation mới.
6. Nhả khóa trong mọi đường thoát, kể cả khi xử lý phát sinh exception.

Pseudocode minh họa ý tưởng:

~~~java
// Pseudocode mô tả thứ tự phối hợp, không phải API thay thế
// FlowExecutor hoặc ExecutionRepository của Spring Web Flow.
lockRegistry.withLock(executionKey, () -> {
    FlowExecution execution = repository.load(executionKey);
    execution.handle(event);
    repository.save(execution);
});
~~~

Trong mã ứng dụng, không nên tự bọc một khóa quanh toàn bộ FlowExecutor nếu framework đã quản lý khóa. Hai lớp khóa chồng lên nhau có thể gây deadlock, chờ lâu hoặc làm sai thứ tự xử lý. Hãy kiểm tra implementation repository và tài liệu đúng phiên bản trước khi thêm cơ chế đồng bộ riêng.

Khóa phải được nhả bằng finally hoặc cơ chế tương đương để exception không làm execution bị khóa vĩnh viễn. Nếu dùng khóa phân tán có lease, cần tính tới trường hợp node giữ khóa bị dừng đột ngột và lease hết hạn trong khi thao tác cũ vẫn còn chạy. Các hệ thống yêu cầu tính đúng đắn cao có thể cần fencing token hoặc version check để ngăn một chủ khóa cũ tiếp tục ghi sau khi quyền khóa đã chuyển sang node khác.

## 5. Điều gì xảy ra khi request thứ hai phải chờ?

Khi request thứ hai tới trong lúc execution đang được xử lý, repository có thể chờ khóa, từ chối ngay, hoặc áp dụng một chính sách timeout. Cách phản hồi là quyết định của implementation và cấu hình; không nên giả định mọi repository đều chờ vô hạn hoặc đều trả cùng một mã HTTP.

| Chính sách | Hành vi | Đánh đổi |
|---|---|---|
| Chờ khóa | Request sau đợi request trước nhả khóa | Đơn giản về trải nghiệm nhưng tăng thời gian response |
| Chờ có timeout | Đợi trong giới hạn rồi báo tranh chấp | Tránh treo request lâu, cần thông điệp retry phù hợp |
| Từ chối ngay | Báo execution đang bận hoặc xung đột | Phản hồi nhanh nhưng người dùng có thể phải gửi lại |
| Optimistic version check | Cho phép đọc nhưng chỉ ghi nếu version chưa đổi | Tăng khả năng song song, cần xử lý conflict khi save |

Nếu ứng dụng tự định nghĩa phản hồi HTTP cho tranh chấp, hãy chọn mã và nội dung theo hợp đồng API. Với giao diện web, có thể hiển thị thông báo “Quy trình đang được xử lý ở một yêu cầu khác; hãy tải lại trước khi tiếp tục”. Với API, 409 Conflict có thể phù hợp cho trạng thái xung đột; 503 Service Unavailable có thể phù hợp khi tài nguyên tạm thời không thể phục vụ. Mã thực tế cần thống nhất với client và cách xử lý của adapter.

Không nên tự động gửi lại một event ghi dữ liệu chỉ vì request nhận timeout khi chờ khóa. Trước khi retry, client hoặc service cần biết lần trước đã được xử lý hay chưa. Nếu không rõ, hãy tải lại trạng thái hoặc tra cứu kết quả nghiệp vụ bằng một mã yêu cầu duy nhất.

## 6. Double submit và nhiều tab

### Double submit

Khi người dùng bấm nút hai lần, hai request có thể mang cùng execution key và cùng event. Khóa giúp ngăn hai request thao tác đồng thời trên cùng trạng thái. Sau khi request đầu hoàn tất, request thứ hai phải được xử lý dựa trên trạng thái/continuation mà repository cho phép. Nếu state đã chuyển khỏi review, event confirm có thể không còn hợp lệ.

Khóa không tự bảo đảm service confirmOrder chỉ chạy một lần. Nếu request thứ hai được phép tiếp tục theo một continuation khác hoặc client retry một lệnh nghiệp vụ ở endpoint khác, side effect vẫn có thể bị lặp. Vì vậy, thao tác xác nhận cần idempotency ở tầng nghiệp vụ.

### Nhiều tab

Hai tab có thể giữ cùng execution key hoặc các continuation key khác nhau của cùng conversation. Hành vi phụ thuộc cách repository lưu execution và continuation. Một số chiến lược lưu snapshot có thể cho phép mỗi tab tiếp tục từ một continuation cũ; chiến lược khác có thể phát hiện key đã hết hạn hoặc không còn hợp lệ.

Do đó, không nên kết luận rằng khóa execution luôn khiến tab thứ hai nhìn thấy trạng thái mới nhất. Khóa tuần tự hóa vùng xử lý mà repository bảo vệ; semantics của continuation quyết định một key cũ được khôi phục, bị từ chối hay được xem là một nhánh hợp lệ.

Thiết kế giao diện và nghiệp vụ cần cân nhắc:

- Hiển thị thông báo khi người dùng mở một bản nháp đang được xử lý ở nơi khác.
- Dùng version hoặc updatedAt để phát hiện dữ liệu nháp đã thay đổi.
- Khi nhận conflict, yêu cầu tải lại hoặc so sánh thay đổi thay vì âm thầm ghi đè.
- Không dùng flow scope làm nguồn dữ liệu chuẩn cho trạng thái nghiệp vụ lâu dài.
- Kiểm tra quyền và trạng thái bản ghi trong service ngay trước khi ghi.

Nếu hai tab được phép làm việc độc lập, hãy tạo hai execution riêng và dùng cơ chế cập nhật dữ liệu có version ở tầng persistence. Nếu hai tab phải thao tác cùng một bản nháp duy nhất, cần một chính sách rõ ràng cho việc chiếm quyền chỉnh sửa, conflict và hủy.

## 7. Khóa execution không thay thế transaction và idempotency

Ba cơ chế này giải quyết ba vấn đề khác nhau:

| Cơ chế | Bảo vệ điều gì? | Phạm vi |
|---|---|---|
| Execution lock | Tránh xử lý đồng thời trạng thái của cùng flow execution theo chính sách repository | Flow execution/repository |
| Database transaction | Bảo đảm nhóm thao tác dữ liệu tuân theo tính nguyên tử và cô lập theo cấu hình | Một hoặc nhiều thao tác trong database |
| Idempotency key | Nhận diện một yêu cầu nghiệp vụ lặp và trả lại kết quả đã xử lý | Một thao tác nghiệp vụ hoặc API |
| Optimistic locking/version | Phát hiện dữ liệu bị cập nhật kể từ lúc đọc | Bản ghi hoặc aggregate nghiệp vụ |

Ví dụ, flow có khóa trong lúc xử lý event confirm, nhưng service gọi cổng thanh toán bên ngoài. Transaction database không thể tự rollback khoản thanh toán đã được cổng thanh toán chấp nhận. Nếu request timeout và người dùng thử lại, khóa execution không đủ để ngăn hai lần thanh toán khi yêu cầu được gửi qua một đường khác hoặc execution continuation được khôi phục riêng.

Service nên dùng idempotency key ổn định cho yêu cầu thanh toán, lưu kết quả xử lý và trả lại cùng kết quả khi nhận lại cùng key. Transaction database cần ghi nhận trạng thái đơn và mã yêu cầu một cách nhất quán. Nếu có thao tác phát sự kiện sau commit, cân nhắc transactional outbox để không mất thông điệp khi ứng dụng dừng giữa commit và publish.

Khóa execution cũng không bảo vệ hai execution khác nhau cùng cập nhật một bản ghi đơn hàng. Trường hợp đó cần khóa/version ở tầng nghiệp vụ hoặc database. Ví dụ, hai flow độc lập cùng sửa một đơn cần kiểm tra version của đơn trước khi lưu.

## 8. Nhiều node và khóa phân tán

Trong triển khai một node, khóa trong bộ nhớ của process có thể phối hợp các request cùng tới node đó. Khi có nhiều node, mỗi process có vùng nhớ và khóa riêng. Nếu hai request cho cùng execution được chuyển tới hai node, khóa cục bộ của node A không ngăn node B xử lý.

Sticky session có thể làm giảm khả năng request cùng phiên đi tới các node khác nhau, nhưng không phải một bảo đảm đồng bộ dữ liệu. Node có thể bị thay thế, load balancer có thể định tuyến lại và client có thể gửi request từ nhiều kết nối.

Một triển khai nhiều node cần phối hợp cả lưu trữ execution lẫn đồng bộ:

- Execution repository phải cung cấp trạng thái có thể được các node nhìn thấy theo chính sách nhất quán đã chọn.
- Cơ chế khóa phải có phạm vi chung giữa các node nếu dùng khóa độc quyền.
- Hoặc repository cần chiến lược optimistic concurrency/versioning để phát hiện hai lần ghi cạnh tranh.
- Thao tác lấy khóa, đọc execution và ghi phiên bản mới phải được phối hợp nguyên tử theo thiết kế.
- Khi node dừng đột ngột, khóa không được giữ vô hạn; lease/timeout và phục hồi phải được kiểm thử.
- Khi khóa hết hạn, thao tác cũ không được ghi đè dữ liệu mới hơn.

Không phải cứ chuyển execution storage sang database hoặc Redis là tự động có khóa phân tán đúng. Việc lưu cùng một nơi và việc phối hợp quyền ghi là hai yêu cầu riêng. Cần đọc tài liệu của repository implementation đang dùng và kiểm thử tình huống hai node nhận cùng execution gần như đồng thời.

## 9. Thời gian giữ khóa và hiệu năng

Khóa quá rộng hoặc được giữ quá lâu làm giảm throughput. Một action gọi dịch vụ ngoài trong thời gian dài có thể khiến request khác phải chờ dù phần lớn thời gian đó không thao tác trên execution. Hãy giữ vùng tới hạn ngắn và giới hạn thời gian xử lý.

Các thực hành hữu ích:

- Không thực hiện tác vụ nền dài trong request tiếp tục flow nếu có thể tách thành job.
- Đặt timeout cho lời gọi mạng và truy vấn database.
- Không chờ người dùng hoặc một callback bên ngoài trong lúc giữ khóa.
- Tránh gọi service có thể chờ lâu trước khi xác định event/state có hợp lệ.
- Theo dõi thời gian chờ khóa, thời gian giữ khóa và số lần timeout.
- Dùng hàng đợi hoặc job có trạng thái riêng cho công việc dài; flow chỉ giữ job ID và trạng thái hiển thị.

Không tối ưu bằng cách bỏ khóa trước khi execution đã được lưu an toàn. Nếu nhả khóa quá sớm, request khác có thể đọc một trạng thái chưa hoàn chỉnh hoặc ghi đè kết quả chưa được commit.

## 10. Xử lý execution key cũ và request lặp

Sau khi một request hoàn tất, key được hiển thị trong view có thể đại diện cho continuation mới. Request gửi lại một key cũ có thể không còn hợp lệ, đã bị xóa hoặc vẫn đại diện cho một snapshot được repository giữ lại. Hành vi phụ thuộc chiến lược repository và giới hạn số continuation.

Ứng dụng cần phân biệt:

- **Execution không tồn tại hoặc đã hết hạn:** hướng dẫn người dùng bắt đầu lại hoặc khôi phục draft theo chính sách.
- **Request xung đột vì execution đang bận:** thông báo chờ/tải lại hoặc trả conflict.
- **Event không hợp lệ ở state hiện tại:** không chạy action; hiển thị kết quả phù hợp.
- **Yêu cầu nghiệp vụ đã hoàn tất:** trả lại kết quả đã lưu nếu cùng idempotency key.
- **Người dùng không có quyền:** từ chối theo chính sách bảo mật, không tiết lộ execution.

Không nên biến mọi trường hợp thành lỗi 500. Phản hồi cần giúp client quyết định có thể tải lại, bắt đầu mới hay liên hệ hỗ trợ. Với request POST, cân nhắc quy tắc redirect/response phù hợp để trình duyệt refresh không gửi lại thao tác ghi ngoài ý muốn.

## 11. Quan sát và chẩn đoán tranh chấp

Khi người dùng báo flow bị quay về bước cũ, gửi đơn hai lần hoặc thỉnh thoảng gặp lỗi execution, cần có log đủ để tái dựng trình tự request.

Nên ghi nhận:

- Correlation ID của HTTP request.
- Flow ID và state ID ở thời điểm nhận event.
- Một định danh execution đã được che hoặc băm theo chính sách bảo mật.
- Tên event, thời điểm bắt đầu/kết thúc và kết quả xử lý.
- Thời gian chờ khóa, thời gian giữ khóa và loại conflict/timeout.
- Node xử lý request và version dữ liệu nếu có.
- Mã nghiệp vụ/idempotency key đã che một phần khi cần đối chiếu.

Không ghi nguyên execution key, session token, thông tin xác thực hoặc toàn bộ flow scope vào log. Không ghi dữ liệu cá nhân hoặc dữ liệu thanh toán chỉ để điều tra race condition.

Các chỉ số hữu ích gồm số request đồng thời trên một execution, tỷ lệ lock timeout, thời gian chờ ở percentile cao, số lần stale key và số side effect bị từ chối do idempotency. Những chỉ số này giúp phân biệt khóa bị nghẽn với lỗi logic hoặc lỗi mạng.

## 12. Kiểm thử xử lý yêu cầu đồng thời

Test concurrency cần tạo ra sự xen kẽ có kiểm soát thay vì chỉ gửi hai request tuần tự. Có thể dùng latch/barrier trong test để hai thread cùng bắt đầu resume một execution, rồi xác minh hành vi repository và service.

Ma trận kiểm thử gợi ý:

| Kịch bản | Kỳ vọng cần xác minh |
|---|---|
| Hai request cùng execution key, cùng event | Không có hai thao tác cập nhật trạng thái đồng thời trái phép |
| Hai request cùng key, event khác nhau | Không mất cập nhật; event thứ hai được xử lý theo trạng thái/continuation hợp lệ |
| Hai execution key khác nhau | Có thể xử lý song song nếu không tranh chấp tài nguyên chung |
| Request thứ hai chờ quá timeout | Trả phản hồi tranh chấp có thể hiểu và có thể phục hồi |
| Exception trong lúc đang giữ khóa | Khóa được nhả, request sau không bị treo vĩnh viễn |
| Hai tab dùng continuation cũ | Hành vi đúng với repository strategy; không âm thầm ghi đè dữ liệu |
| Hai node nhận cùng execution | Cơ chế đồng bộ phân tán ngăn cập nhật cạnh tranh |
| Retry sau timeout của thao tác ghi | Idempotency ngăn side effect bị lặp |
| Hai execution sửa cùng bản ghi | Version/optimistic locking phát hiện xung đột ở tầng dữ liệu |

Ngoài state cuối, hãy kiểm tra số lần service được gọi, số bản ghi được tạo, số thông điệp được phát, trạng thái transaction và khóa có được giải phóng sau cả đường thành công lẫn exception hay không.

Một test chỉ xác minh hai request nhận HTTP 200 là chưa đủ. Cần chứng minh dữ liệu cuối cùng đúng và side effect chỉ xảy ra theo chính sách đã thiết kế.

## 13. Lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Cho rằng mỗi người dùng chỉ có một request | Double submit và retry tạo race condition | Bảo vệ execution ở server và idempotency ở nghiệp vụ |
| Tự thêm khóa toàn cục quanh mọi flow | Các execution độc lập phải chờ nhau | Dùng phạm vi khóa theo execution |
| Giữ khóa trong thời gian người dùng nhập form | Làm cạn tài nguyên và chặn request khác | Chỉ khóa trong lúc xử lý request |
| Tự bọc khóa khi framework đã quản lý | Deadlock hoặc khóa chồng lấn | Kiểm tra repository/executor trước khi thêm cơ chế riêng |
| Nghĩ khóa execution thay transaction | Dữ liệu database có thể vẫn ghi một phần | Dùng transaction cho thao tác persistence |
| Nghĩ khóa execution bảo vệ mọi endpoint | Endpoint khác hoặc execution khác vẫn có thể ghi cùng bản ghi | Dùng version/lock nghiệp vụ ở tầng dữ liệu |
| Dựa vào sticky session như khóa phân tán | Request chuyển node có thể cập nhật cạnh tranh | Dùng repository và đồng bộ có phạm vi cluster |
| Retry mù sau timeout | Tạo side effect trùng | Tra cứu trạng thái và dùng idempotency key |
| Không kiểm thử exception khi giữ khóa | Khóa có thể không được giải phóng | Test finally/cleanup và lock timeout |

## 14. Quy trình thiết kế và vận hành

Khi triển khai lưu trữ execution có xử lý request đồng thời, hãy làm theo trình tự:

1. Xác định repository đang dùng và cách nó lưu execution, conversation, continuation.
2. Xác định khóa được áp dụng theo execution key hay phạm vi khác, và thời điểm lấy/nhả khóa.
3. Xác định hành vi khi request thứ hai tới: chờ, timeout, conflict hay optimistic version check.
4. Kiểm tra triển khai một node và nhiều node; không suy ra khóa phân tán từ việc dùng storage chung.
5. Tách side effect nghiệp vụ khỏi giả định khóa execution; bổ sung transaction và idempotency.
6. Xác định chính sách cho nhiều tab, stale continuation, execution hết hạn và request retry.
7. Đặt giới hạn timeout, logging và monitoring cho thời gian chờ/giữ khóa.
8. Kiểm thử bằng nhiều thread và nhiều node với cả đường thành công lẫn exception.

Khi review, cần trả lời được: hai request cùng execution key được phối hợp ở đâu, request thứ hai nhận phản hồi gì, trạng thái nào được lưu, và làm sao chứng minh side effect không bị lặp. Nếu ứng dụng chạy nhiều node, cần trả lời thêm khóa và version được chia sẻ bằng cơ chế nào.

## Kết luận

Khóa khi tiếp tục execution giúp bảo vệ trạng thái flow khỏi các request cạnh tranh trong cùng vùng xử lý. Nó đặc biệt cần thiết khi người dùng bấm đúp, mở nhiều tab hoặc client retry. Repository và executor chịu trách nhiệm phối hợp việc đọc, xử lý và lưu execution theo chiến lược của implementation.

Khóa execution chỉ bảo vệ phạm vi execution mà nó quản lý. Transaction bảo vệ thao tác dữ liệu; idempotency bảo vệ yêu cầu nghiệp vụ lặp; optimistic locking phát hiện cập nhật cạnh tranh trên bản ghi. Trong môi trường nhiều node, cơ chế đồng bộ phải có phạm vi cluster hoặc dùng version check phù hợp. Khi kết hợp đúng các lớp bảo vệ và kiểm thử các tình huống đồng thời, flow có thể tiếp tục ổn định mà không tạo cập nhật mất mát hay side effect trùng.
