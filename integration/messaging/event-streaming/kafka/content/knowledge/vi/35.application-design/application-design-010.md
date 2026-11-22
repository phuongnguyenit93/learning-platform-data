# Tránh lạm dụng Kafka như cơ sở dữ liệu truy vấn hoặc bộ lập lịch

Apache Kafka là nền tảng event streaming được xây dựng quanh một distributed log có khả năng lưu trữ bền vững và phân phối record đến nhiều consumer. Kafka rất phù hợp để truyền sự kiện giữa các dịch vụ, giữ lịch sử record trong một khoảng thời gian, phát lại luồng và xử lý dữ liệu theo thứ tự trong từng partition. Tuy nhiên, Kafka không cung cấp đầy đủ các đặc tính của một cơ sở dữ liệu truy vấn nghiệp vụ hoặc một bộ lập lịch tác vụ.

Một thiết kế tốt cần đặt Kafka đúng vai trò trong kiến trúc. Producer công bố sự kiện hoặc command theo hợp đồng; consumer xử lý luồng và có thể xây dựng read model; một hệ thống lưu trữ chuyên dụng phục vụ truy vấn; một scheduler hoặc workflow engine quản lý thời điểm thực thi và trạng thái công việc kéo dài. Các thành phần này có thể phối hợp qua Kafka mà không buộc Kafka đảm nhiệm mọi trách nhiệm.

Bài học tập trung vào hai kiểu lạm dụng thường gặp: đọc Kafka như thể đó là cơ sở dữ liệu có thể tìm kiếm tùy ý, và dùng thời gian lưu record hoặc consumer để giả lập chức năng lập lịch. Sau bài học, người học có thể:

- Giải thích vì sao Kafka không phù hợp với truy vấn tùy ý theo nhiều trường.
- Phân biệt log, offset, retention, log compaction và read model.
- Thiết kế projection phục vụ truy vấn bằng Kafka Streams hoặc consumer kết hợp cơ sở dữ liệu.
- Chọn nơi lưu dữ liệu nguồn và nơi phục vụ truy vấn theo trách nhiệm.
- Phân biệt thời điểm phát record với thời điểm một công việc được phép thực thi.
- Chọn scheduler, retry topic hoặc workflow engine theo loại yêu cầu.
- Xử lý duplicate, crash, ordering và phục hồi khi điều phối tác vụ qua Kafka.

## 1. Kafka cung cấp log, không phải cơ sở dữ liệu truy vấn tổng quát

Một topic Kafka là một log được chia thành nhiều partition. Record được ghi nối tiếp vào partition và có offset xác định vị trí trong partition đó. Consumer đọc record theo thứ tự offset, theo dõi tiến độ bằng consumer offset và có thể đọc lại record nếu record vẫn còn trong log.

Cách tổ chức này khác với cơ sở dữ liệu quan hệ hoặc cơ sở dữ liệu tài liệu:

| Nhu cầu | Kafka | Cơ sở dữ liệu truy vấn |
|---|---|---|
| Ghi dữ liệu | Ghi record nối tiếp vào partition | Ghi theo bảng, document hoặc cấu trúc lưu trữ |
| Đọc tuần tự | Rất phù hợp qua offset | Có thể thực hiện nhưng không phải lúc nào cũng tối ưu |
| Tìm theo nhiều điều kiện | Không có truy vấn SQL tùy ý trên topic | Có index, query planner và ngôn ngữ truy vấn |
| Cập nhật một bản ghi | Thông thường ghi record mới; log là append-oriented | Có thể update/delete theo khóa hoặc điều kiện |
| Quan hệ và join | Cần xử lý stream/table hoặc ứng dụng riêng | Có thể hỗ trợ join và ràng buộc dữ liệu |
| Phục vụ API tra cứu | Thường cần projection hoặc storage bên ngoài | Là một vai trò phổ biến |
| Phát lại lịch sử | Là khả năng cốt lõi khi record còn được giữ | Phụ thuộc mô hình lưu trữ và audit |

Kafka có thể giữ lượng dữ liệu lớn và đọc tuần tự với throughput cao. Điều đó không có nghĩa broker là nơi thích hợp để thực hiện mọi câu hỏi như:

- Tìm tất cả đơn hàng của một khách hàng trong tháng trước.
- Lọc giao dịch theo trạng thái, khoảng tiền và khu vực.
- Tìm bản ghi có một trường JSON cụ thể.
- Sắp xếp kết quả theo nhiều thuộc tính và trả về trang thứ 20.
- Cập nhật trạng thái của một đơn hàng theo điều kiện.

Để trả lời những câu hỏi này, ứng dụng thường phải đọc nhiều record, tự lọc và tự duy trì trạng thái. Cách làm đó tốn tài nguyên, tạo độ trễ không ổn định và khiến consumer phụ thuộc vào cách topic được phân vùng hoặc lưu giữ.

Hãy xem Kafka như một nguồn dữ liệu dạng log để các ứng dụng tiêu thụ theo luồng. Nếu người dùng cần tìm kiếm hoặc đọc trạng thái hiện tại nhanh chóng, hãy tạo một read model phù hợp với mẫu truy vấn.

## 2. Hiểu đúng offset, retention và log compaction

Ba khái niệm này thường bị hiểu nhầm thành khả năng lưu trữ và truy vấn như database.

### 2.1. Offset là vị trí trong partition

Offset là vị trí của record trong một partition. Nó không phải ID nghiệp vụ, không phải thứ tự toàn cục của toàn topic và cũng không phải số thứ tự liên tục giữa các partition.

Ví dụ, topic có ba partition:

~~~text
orders partition 0: offset 0, 1, 2, 3, ...
orders partition 1: offset 0, 1, 2, 3, ...
orders partition 2: offset 0, 1, 2, 3, ...
~~~

Consumer có thể lưu offset đã xử lý để tiếp tục từ vị trí phù hợp sau khi khởi động lại. Offset giúp điều khiển việc đọc tuần tự và phát lại; nó không cung cấp truy vấn kiểu “tìm mọi record có customerId = C102”.

Không nên dùng offset thay cho orderId, paymentId hoặc eventId. Offset chỉ có ý nghĩa trong ngữ cảnh một topic-partition cụ thể. Khi record được sao chép sang topic khác hoặc topic được tái tạo, offset có thể khác.

### 2.2. Retention xác định thời gian hoặc dung lượng lưu record

Chính sách retention quyết định Kafka giữ record trong bao lâu hoặc trong giới hạn dung lượng nào. Khi record hết hạn, Kafka có thể xóa các segment cũ theo chính sách. Retention không có nghĩa Kafka sẽ giữ mọi lịch sử nghiệp vụ mãi mãi.

Ví dụ, nếu topic giữ dữ liệu trong bảy ngày và một consumer ngừng hoạt động mười ngày, consumer có thể không còn đọc được toàn bộ record mà nó đã bỏ lỡ. Một hệ thống cần khả năng phục hồi lâu hơn phải tính retention theo thời gian gián đoạn, thời gian tái xử lý và yêu cầu kiểm toán; hoặc lưu dữ liệu lịch sử vào một hệ thống phù hợp hơn.

Retention cũng không phải cơ chế hẹn giờ. Một record được giữ trong bảy ngày có thể được consumer đọc ngay sau khi nó được ghi. Thời gian lưu record không trì hoãn việc giao record đến consumer.

### 2.3. Log compaction giữ trạng thái mới nhất theo key

Topic bật log compaction có thể loại bỏ các phiên bản cũ hơn của cùng một key để giữ lại giá trị mới nhất, cùng với tombstone theo quy tắc compact. Mô hình này hữu ích cho changelog hoặc topic biểu diễn trạng thái hiện tại theo key.

Ví dụ:

~~~text
key=order-42, value={status: "CREATED"}
key=order-42, value={status: "PAID"}
key=order-42, value={status: "SHIPPED"}
~~~

Sau quá trình compact, Kafka có thể chỉ giữ bản ghi mới nhất cho key order-42. Vì vậy, topic compacted không còn là lịch sử đầy đủ của mọi lần chuyển trạng thái. Consumer mới có thể dựng lại trạng thái hiện tại từ các key còn hiệu lực, nhưng không thể mặc định tái dựng toàn bộ chuỗi chuyển trạng thái đã bị compact.

Log compaction cũng không tạo index cho các trường bên trong value. Nếu cần tìm mọi đơn hàng có trạng thái SHIPPED, compaction theo orderId không tự giúp truy vấn theo status. Nó tối ưu việc giữ giá trị mới nhất theo key, không phải truy vấn theo mọi thuộc tính.

## 3. Xây dựng read model cho nhu cầu truy vấn

Một read model là cấu trúc dữ liệu được tối ưu cho cách ứng dụng đọc thông tin. Trong kiến trúc event-driven, consumer có thể nhận event từ Kafka rồi cập nhật read model riêng. Đây là cách phổ biến để áp dụng CQRS: mô hình ghi và mô hình đọc có thể khác nhau vì chúng phục vụ những mục đích khác nhau.

Ví dụ, dịch vụ Orders sở hữu trạng thái đơn hàng. Một API cho màn hình quản trị cần tìm đơn theo khách hàng, trạng thái và ngày tạo. Thay vì truy vấn trực tiếp Kafka, kiến trúc có thể là:

~~~mermaid
flowchart LR
    A["Orders Service"] --> B[("Orders Database")]
    A --> C[("Outbox")]
    C --> D[("Kafka: order-events")]
    D --> E["Projection Consumer"]
    E --> F[("Read Database")]
    F --> G["Order Query API"]
    G --> H["Admin UI"]
~~~

Orders vẫn sở hữu dữ liệu và quy tắc nghiệp vụ. Outbox ghi nhận event cần phát trong cùng transaction với cập nhật dữ liệu nguồn. Consumer xây dựng projection trong cơ sở dữ liệu đọc. API truy vấn cơ sở dữ liệu đọc theo index phù hợp.

Read model có thể được thiết kế theo từng nhu cầu:

| Mẫu truy vấn | Read model gợi ý |
|---|---|
| Tra cứu một đơn theo orderId | Bảng hoặc document theo khóa orderId |
| Liệt kê đơn của khách hàng theo thời gian | Index kết hợp customerId và createdAt |
| Lọc đơn theo trạng thái và khu vực | Index theo các trường lọc thường dùng |
| Tổng hợp doanh thu theo ngày | Bảng aggregate theo ngày hoặc kho phân tích |
| Tìm kiếm toàn văn trên mô tả | Search engine phù hợp với full-text search |
| Báo cáo nhiều chiều trên dữ liệu lớn | Data warehouse hoặc OLAP store |

Không cần tạo một read database duy nhất cho mọi truy vấn. Có thể có nhiều projection độc lập, mỗi projection có schema và index phù hợp. Một consumer phục vụ màn hình hỗ trợ khách hàng có thể giữ thông tin tóm tắt đơn; consumer khác phục vụ báo cáo có thể tổng hợp theo ngày và vùng.

### 3.1. Read model là dữ liệu dẫn xuất

Read model được xây dựng từ event nên thường có độ trễ so với database nguồn. Đây là eventual consistency. Khi Orders vừa phát OrderPlaced, projection có thể mất một khoảng thời gian ngắn để nhận event và cập nhật. API cần thể hiện rõ hành vi này, đặc biệt khi người dùng vừa ghi dữ liệu xong rồi lập tức truy vấn.

Có một số cách giảm bất ngờ:

- API ghi trả về trạng thái đã ghi ở nguồn, không hứa rằng mọi projection đã cập nhật tức thì.
- API đọc có thể nhận một version hoặc correlation token để chờ projection đạt đến mức cần thiết.
- Giao diện có thể hiển thị trạng thái đang đồng bộ trong khoảng trễ chấp nhận được.
- Những quyết định nghiệp vụ cần tính nhất quán mạnh nên được kiểm tra tại miền sở hữu dữ liệu, không dựa vào read model trễ.

Không nên cho phép consumer tự sửa read model theo ý muốn mà không có quy tắc tái dựng. Nếu projection bị hỏng, cần có khả năng xóa và dựng lại từ event còn lưu, snapshot hoặc dữ liệu nguồn. Điều này đòi hỏi schema, version và quy trình replay được quản lý.

### 3.2. Kafka Streams và state store

Kafka Streams cung cấp API để xử lý stream và table, thực hiện filter, map, join, aggregate và duy trì state store. Một KTable biểu diễn trạng thái được cập nhật theo key; nó rất hữu ích để tạo projection hoặc kết hợp dữ liệu đang thay đổi.

State store của Kafka Streams không tự biến ứng dụng thành một cơ sở dữ liệu truy vấn dùng chung cho toàn doanh nghiệp. Truy vấn interactive query thường gắn với instance đang giữ một phần state, vì vậy ứng dụng phải biết instance nào sở hữu key hoặc triển khai cơ chế định tuyến giữa các instance. State store còn phụ thuộc vào changelog và quá trình khôi phục.

Nếu nhiều ứng dụng, người dùng hoặc công cụ báo cáo cần truy vấn linh hoạt, hãy xuất projection đến một database hoặc search engine được thiết kế cho truy vấn đó. Kafka Streams có thể là bước tính toán để tạo projection; storage phục vụ truy vấn vẫn cần được chọn theo workload.

## 4. Chọn nguồn dữ liệu và nơi phục vụ truy vấn

Một câu hỏi quan trọng trong thiết kế là: dữ liệu nào là nguồn sự thật, và dữ liệu nào chỉ là bản chiếu phục vụ đọc?

Nguồn sự thật (source of truth) thuộc về miền sở hữu dữ liệu. Ví dụ, Orders Database là nơi Orders thực thi quy tắc và xác nhận trạng thái đơn. Một bảng projection trong Search Service chỉ là bản sao dẫn xuất. Nếu hai nơi mâu thuẫn, cần có quy tắc xác định nguồn nào có thẩm quyền và cách tái dựng projection.

| Loại dữ liệu | Vai trò | Ai chịu trách nhiệm? |
|---|---|---|
| Orders Database | Nguồn trạng thái đơn hàng | Orders |
| Order Events Topic | Phân phối sự kiện và lưu log theo retention | Miền phát event và nền tảng Kafka theo trách nhiệm vận hành |
| Search Projection | Tối ưu tìm kiếm và lọc | Search/Query service |
| Analytics Warehouse | Phân tích và báo cáo | Data/Analytics platform |
| Cache | Tăng tốc truy cập dữ liệu đã có nguồn chính | Dịch vụ sử dụng cache |

Không nên để nhiều dịch vụ cùng ghi vào một read model mà không có quy tắc ownership. Nếu nhiều consumer cập nhật cùng một bảng, thứ tự event và quy tắc hợp nhất có thể trở nên khó hiểu. Mỗi projection nên có một chủ sở hữu chịu trách nhiệm cập nhật, schema và replay.

Cũng cần phân biệt dữ liệu nghiệp vụ với dữ liệu kỹ thuật. Kafka có thể chứa event, CDC record hoặc telemetry, nhưng không nên để mọi ứng dụng truy vấn trực tiếp cấu trúc nội bộ của database nguồn. Nếu consumer cần hợp đồng nghiệp vụ ổn định, producer nên công bố integration event có ngữ nghĩa rõ ràng.

## 5. Kafka không phải bộ lập lịch tác vụ

Kafka không có chức năng native để nói rằng “hãy giao record này cho consumer vào 9 giờ sáng ngày mai”. Khi producer gửi record, record được ghi vào partition và consumer đang hoạt động có thể đọc nó ngay khi đến vị trí đó.

Timestamp trên record thường mô tả thời điểm tạo hoặc thời điểm broker nhận record tùy cấu hình timestamp type. Nó không phải thời điểm giao hàng và không làm record bị ẩn khỏi consumer cho đến một thời điểm tương lai.

Ví dụ, đoạn gửi record sau không đặt lịch cho ngày mai:

~~~java
kafkaTemplate.send("orders.events", orderId, event);
~~~

Nếu payload có trường dueAt hoặc scheduledAt, consumer vẫn nhận record ngay. Ứng dụng phải tự kiểm tra thời điểm đó và quyết định cách quản lý công việc đến hạn.

### 5.1. Phân biệt event, command và scheduled task

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Sự thật đã xảy ra | OrderPlaced, PaymentAuthorized |
| Command | Yêu cầu một dịch vụ thực hiện hành động | CapturePayment, ReleaseReservation |
| Scheduled task | Công việc cần được thực hiện tại hoặc sau thời điểm xác định | Gửi nhắc thanh toán sau 30 phút |
| Workflow | Quy trình có trạng thái, nhiều bước, timeout và nhánh kết quả | Hoàn tất đơn hàng với thanh toán, kho và giao vận |

Event thường được phát ngay khi sự thật xảy ra. Scheduled task mô tả một hành động tương lai. Nếu cần yêu cầu một dịch vụ thực hiện hành động vào thời điểm đến hạn, hãy biểu diễn nó thành command hoặc một bản ghi công việc có trạng thái, người sở hữu và chính sách retry rõ ràng.

Không nên giả mạo một event quá khứ để biểu diễn một công việc tương lai. Ví dụ, không phát OrderExpired ngay khi tạo đơn chỉ vì dự kiến đơn sẽ hết hạn sau 30 phút. Chỉ phát OrderExpired khi điều kiện hết hạn đã thực sự được xác nhận.

## 6. Chọn cơ chế lập lịch phù hợp

Các loại công việc khác nhau cần cơ chế khác nhau. Không có một giải pháp duy nhất phù hợp cho mọi trường hợp.

| Nhu cầu | Cơ chế phù hợp | Lưu ý |
|---|---|---|
| Tác vụ định kỳ đơn giản | CronJob, scheduler của nền tảng hoặc Spring scheduling | Cần kiểm soát chạy trùng khi có nhiều instance |
| Công việc một lần tại thời điểm tương lai | Scheduler lưu lịch và phát command khi đến hạn | Cần trạng thái bền vững, retry và idempotency |
| Retry một message sau một khoảng trễ | Retry topic hoặc delayed-retry service | Phải xem xét ordering và số lần retry |
| Quy trình dài có nhiều bước và timeout | Workflow engine hoặc Saga/process manager | Cần lưu trạng thái quy trình và hành động bù trừ |
| Xử lý thời gian trong stream | Kafka Streams window hoặc punctuator | Dùng cho xử lý stream, không thay scheduler nghiệp vụ tổng quát |

### 6.1. Tác vụ định kỳ

Với công việc định kỳ như tổng hợp báo cáo lúc nửa đêm hoặc kiểm tra dữ liệu hàng giờ, dùng scheduler phù hợp với nền tảng triển khai. Kubernetes CronJob hoặc scheduler của hệ thống điều phối có thể khởi chạy một job theo lịch.

Spring cung cấp @Scheduled cho ứng dụng Java. Tuy nhiên, nếu ứng dụng chạy nhiều replica, mỗi replica có thể kích hoạt cùng một lịch. Cần bảo đảm chỉ một instance thực thi tại một thời điểm hoặc thiết kế job idempotent và có cơ chế khóa/claim phân tán. Việc chỉ thêm @Scheduled không tự tạo distributed scheduler.

Sau khi job xác định công việc cần xử lý, nó có thể phát event hoặc command vào Kafka để các consumer xử lý song song. Scheduler quyết định khi nào job bắt đầu; Kafka phân phối phần việc đã đến hạn.

### 6.2. Công việc một lần trong tương lai

Ví dụ: sau khi khách hàng đặt hàng, nếu chưa thanh toán trong 30 phút thì yêu cầu Orders kiểm tra và có thể hủy đơn. Một thiết kế bền vững có thể lưu lịch hẹn trong database:

| scheduleId | orderId | dueAt | status |
|---|---|---|---|
| sch-901 | order-42 | 2026-11-20T10:00:00Z | PENDING |

Scheduler định kỳ tìm các công việc đến hạn, claim chúng một cách an toàn, rồi phát command đến Kafka. Khi kết quả xử lý được xác nhận, scheduler cập nhật trạng thái hoặc consumer ghi nhận kết quả qua một event.

Luồng minh họa:

~~~mermaid
sequenceDiagram
    participant O as Orders
    participant DB as Orders DB / Schedule
    participant S as Scheduler
    participant K as Kafka
    participant C as Consumer

    O->>DB: Lưu đơn và lịch kiểm tra
    S->>DB: Claim công việc đã đến hạn
    S->>K: Publish CheckUnpaidOrder
    K->>C: Deliver command
    C->>O: Kiểm tra trạng thái đơn
    O->>DB: Cập nhật kết quả
    O->>K: Publish OrderExpired nếu đủ điều kiện
~~~

Điểm quan trọng là scheduler chỉ yêu cầu kiểm tra. Consumer hoặc miền sở hữu đơn hàng phải xác nhận đơn vẫn chưa thanh toán và vẫn đủ điều kiện hết hạn. Một event thanh toán có thể đến sát thời điểm dueAt; nếu scheduler tự động phát OrderExpired mà không kiểm tra trạng thái mới nhất, hệ thống có thể hủy nhầm đơn đã thanh toán.

Bản ghi lịch cần có định danh ổn định, thời điểm đến hạn, trạng thái, số lần thử, thông tin lỗi và liên kết đến aggregate. Khi người dùng hủy hoặc thay đổi đơn, miền sở hữu phải cập nhật hoặc vô hiệu hóa lịch tương ứng.

### 6.3. Retry topic có độ trễ

Retry topic là một mẫu hữu ích khi consumer gặp lỗi tạm thời và muốn thử lại sau một khoảng thời gian. Ví dụ, một lần gọi dịch vụ bên ngoài thất bại do timeout; consumer có thể gửi record sang topic retry với metadata về lần thử và thời điểm thử tiếp theo.

Tuy nhiên, Kafka không tự trì hoãn record trong retry topic. Một retry consumer có thể đọc record ngay khi nó được ghi. Để tạo độ trễ, ứng dụng phải triển khai cơ chế như:

- Consumer kiểm tra dueAt và chỉ xử lý khi đến hạn.
- Một scheduler hoặc delay service chuyển record đã đến hạn sang topic xử lý.
- Tổ chức các retry topic theo khoảng trễ và có cơ chế chờ/đọc phù hợp.
- Dùng một hệ thống điều phối tác vụ chuyên dụng nếu thời gian chờ và trạng thái phức tạp.

Không nên cho consumer đọc record rồi ngủ trong thời gian dài để chờ dueAt. Điều đó có thể giữ partition bị chiếm, giảm throughput và làm các record sau bị chặn. Với retry có độ trễ lớn, nên để một thành phần quản lý thời điểm đến hạn rồi phát lại khi thích hợp.

Retry topic cũng có thể phá vỡ thứ tự. Giả sử OrderPlaced được chuyển sang retry trong khi OrderCancelled tiếp tục qua topic chính. Consumer có thể xử lý OrderCancelled trước OrderPlaced. Nếu thứ tự theo orderId là yêu cầu nghiệp vụ, cần thiết kế để các event sau của cùng aggregate không vượt qua event đang chờ retry, hoặc để handler xử lý trạng thái theo cách idempotent và kiểm tra version.

### 6.4. Kafka Streams punctuator và xử lý thời gian

Kafka Streams hỗ trợ windowing và Processor API với punctuator để thực hiện công việc định kỳ theo stream time hoặc wall-clock time. Đây là công cụ hữu ích cho các tác vụ gắn với xử lý stream, chẳng hạn phát kết quả tổng hợp theo cửa sổ hoặc kiểm tra state store theo chu kỳ.

Punctuator phụ thuộc vào topology và task đang chạy. Với stream-time punctuation, callback chỉ được kích hoạt khi stream time tiến lên; nếu không có record mới, thời điểm callback có thể không tiến triển. Wall-clock punctuation dựa trên thời gian thực của instance, nhưng vẫn cần hiểu việc task chuyển instance, phục hồi state và tính chất phân tán.

Do đó, punctuator phù hợp với xử lý thời gian trong một ứng dụng Kafka Streams. Nó không tự cung cấp đầy đủ tính năng quản lý lịch nghiệp vụ như hủy lịch, đổi lịch, theo dõi người chịu trách nhiệm, xử lý timeout nhiều bước và giao diện quản trị lịch.

## 7. Thiết kế scheduler và consumer có khả năng phục hồi

Khi một scheduler phát command qua Kafka, có thể xảy ra các tình huống:

- Scheduler claim công việc rồi dừng trước khi publish.
- Kafka nhận record nhưng scheduler mất xác nhận và publish lại.
- Consumer xử lý xong nhưng dừng trước khi commit offset.
- Công việc bị thay đổi hoặc hủy sau khi đã được phát.
- Một event khác đến làm cho công việc hết hạn không còn hợp lệ.

Thiết kế cần giả định có thể phát hoặc nhận trùng. Kafka producer idempotence giúp xử lý retry của producer trong phạm vi bảo đảm của Kafka, nhưng không thay thế idempotency nghiệp vụ.

Một mẫu dữ liệu công việc có thể gồm:

| Trường | Mục đích |
|---|---|
| taskId | Định danh duy nhất của lịch hoặc công việc |
| aggregateId | Đối tượng nghiệp vụ liên quan |
| taskType | Loại công việc cần thực hiện |
| dueAt | Thời điểm công việc đến hạn |
| status | PENDING, CLAIMED, PUBLISHED, COMPLETED, CANCELLED hoặc FAILED |
| attempt | Số lần đã thử |
| version | Phiên bản lịch để nhận biết lịch cũ |
| idempotencyKey | Khóa chống thực hiện cùng tác động nhiều lần |

### 7.1. Claim công việc an toàn

Nếu nhiều scheduler instance cùng đọc một bảng lịch, chúng cần cơ chế claim để không cùng xử lý một công việc. Có thể dùng transaction và khóa hàng, optimistic locking hoặc cơ chế claim nguyên tử phù hợp với database. Một instance claim công việc bằng cách chuyển trạng thái từ PENDING sang CLAIMED và ghi thông tin lease/claim owner.

Lease có thời hạn giúp phục hồi khi instance chết sau khi claim. Sau khi lease hết hạn, scheduler khác có thể claim lại. Tuy nhiên, nếu instance cũ vẫn tiếp tục chạy sau khi lease hết hạn, cả hai có thể publish. Consumer vẫn cần idempotency.

Không nên giữ transaction database mở trong suốt thời gian chờ Kafka hoặc chờ tác vụ hoàn tất. Hãy tách các bước claim, publish và cập nhật trạng thái, đồng thời thiết kế khả năng lặp an toàn cho từng bước.

### 7.2. Kết hợp outbox để tránh mất command

Nếu scheduler cập nhật trạng thái lịch trong database rồi publish command sang Kafka, ứng dụng có thể dừng giữa hai thao tác. Transactional outbox giải quyết khoảng hở này: trong cùng transaction, scheduler chuyển lịch sang trạng thái đã sẵn sàng phát và ghi command vào outbox. Relay phát outbox sang Kafka.

Nếu relay gửi lại, consumer có thể nhận duplicate. Vì vậy, command cần taskId hoặc idempotencyKey ổn định; consumer ghi nhận việc xử lý cùng transaction với thay đổi nghiệp vụ nếu có thể.

### 7.3. Hủy hoặc đổi lịch

Một lịch có thể được thay đổi sau khi command đã được gửi vào Kafka. Kafka không có thao tác thu hồi record đã ghi khỏi log theo cách một scheduler thu hồi lịch.

Có thể dùng version hoặc generation của lịch:

1. Mỗi lần tạo hoặc đổi lịch, tăng version.
2. Command chứa taskId và version tại thời điểm phát.
3. Consumer kiểm tra version với trạng thái hiện hành do miền sở hữu quản lý.
4. Nếu command đã cũ hoặc lịch đã hủy, consumer bỏ qua một cách an toàn.
5. Nếu version còn hiệu lực, consumer thực hiện hành động idempotent.

Ví dụ, lịch hủy đơn phiên bản 3 đã được phát; khách hàng gia hạn thanh toán khiến lịch tăng lên phiên bản 4. Khi command phiên bản 3 đến consumer, consumer thấy phiên bản hiện tại là 4 và không hủy đơn.

Không cần xóa record cũ khỏi Kafka để thực hiện thay đổi lịch. Hợp đồng và trạng thái hiện hành phải đủ để consumer nhận biết command đã lỗi thời.

## 8. Ví dụ Spring: scheduler phát command đã đến hạn

Ví dụ dưới đây minh họa cách tổ chức một scheduler đơn giản. Phần truy vấn và claim database được đóng gói trong repository; triển khai thật cần transaction, lease hoặc locking phù hợp với loại database.

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DueTaskPublisher {
    private final ScheduledTaskRepository repository;
    private final KafkaTemplate<String, CheckUnpaidOrder> kafkaTemplate;

    public DueTaskPublisher(
            ScheduledTaskRepository repository,
            KafkaTemplate<String, CheckUnpaidOrder> kafkaTemplate) {
        this.repository = repository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Scheduled(fixedDelayString = "PT5S")
    public void publishDueTasks() {
        List<ScheduledTask> tasks =
                repository.claimDueTasks(Instant.now(), 100);

        for (ScheduledTask task : tasks) {
            CheckUnpaidOrder command = new CheckUnpaidOrder(
                    task.taskId(),
                    task.orderId(),
                    task.version()
            );

            kafkaTemplate.send(
                    "orders.commands",
                    task.orderId(),
                    command
            );
        }
    }
}
~~~

Đây là ví dụ cấu trúc, chưa phải một triển khai đầy đủ để đưa vào production. Repository phải claim công việc một cách nguyên tử và có lease để phục hồi khi publisher dừng. Việc đánh dấu đã publish cần dựa trên kết quả gửi hoặc được quản lý qua outbox. Nếu nhiều instance chạy cùng lịch, cần distributed coordination hoặc thiết kế claim phân tán.

Command cần chứa taskId và version để consumer kiểm tra trạng thái. Consumer phải xác nhận đơn vẫn chưa thanh toán, lịch chưa bị hủy và version còn hiệu lực trước khi yêu cầu hủy đơn.

Một DTO command có thể như sau:

~~~java
public record CheckUnpaidOrder(
    String taskId,
    String orderId,
    long scheduleVersion
) {}
~~~

Nếu việc phát command là một phần của transaction cập nhật lịch, hãy ghi command vào outbox trong transaction đó. Một relay riêng sẽ gửi outbox đến Kafka. Cách này tránh tình huống database đánh dấu công việc đã phát nhưng command chưa bao giờ đến Kafka.

## 9. Khi nào nên dùng workflow engine?

Một scheduler đơn giản phù hợp với công việc độc lập có thời điểm đến hạn rõ ràng. Nhưng quy trình nghiệp vụ dài có thể có nhiều trạng thái, nhiều dịch vụ, timeout, retry, nhánh quyết định và hành động bù trừ.

Ví dụ, quy trình xử lý đơn hàng có thể gồm:

1. Chờ thanh toán.
2. Nếu quá hạn, kiểm tra trạng thái và yêu cầu hủy.
3. Nếu thanh toán thành công, yêu cầu kho giữ chỗ.
4. Nếu kho không đủ hàng, hoàn tiền hoặc chọn phương án khác.
5. Khi giao vận hoàn tất, đóng quy trình.

Nếu tự xây dựng toàn bộ state machine bằng nhiều topic và bảng trạng thái, nhóm phải tự xử lý version, timeout, retry, lịch sử, replay, correlation và công cụ vận hành. Khi quy trình đủ phức tạp, một workflow engine hoặc process manager chuyên dụng có thể phù hợp hơn.

Kafka vẫn có vai trò trong kiến trúc đó: workflow engine có thể gửi command đến dịch vụ qua Kafka và nhận event kết quả. Engine quản lý trạng thái quy trình và thời điểm; Kafka vận chuyển thông điệp giữa các thành phần.

| Đặc điểm | Scheduler đơn giản | Workflow engine |
|---|---|---|
| Công việc định kỳ hoặc một lần | Phù hợp | Có thể hỗ trợ |
| Nhiều bước có trạng thái | Cần tự xây dựng | Là chức năng cốt lõi |
| Timeout theo từng bước | Cần tự quản lý | Thường được hỗ trợ |
| Retry và hành động bù trừ | Cần tự phối hợp | Có mô hình điều phối |
| Theo dõi tiến trình | Thường qua bảng/log | Thường có trạng thái và lịch sử workflow |
| Độ phức tạp vận hành | Thấp hơn cho tác vụ đơn giản | Cao hơn, phù hợp quy trình phức tạp |

Không nên đưa workflow engine vào mọi tác vụ nhỏ. Hãy chọn theo số bước, thời gian tồn tại, yêu cầu quan sát, khả năng thay đổi lịch và chi phí vận hành.

## 10. Những lỗi thường gặp khi dùng Kafka sai vai trò

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Đọc toàn topic để tìm một đơn hàng | Tốn I/O, độ trễ tăng theo lượng dữ liệu | Tạo read model theo orderId hoặc index truy vấn |
| Dùng compacted topic làm database tìm kiếm | Compaction chỉ tối ưu theo key, không index các trường value | Xuất projection đến database/search engine |
| Coi retention là lịch sử vĩnh viễn | Record có thể hết hạn theo policy | Đặt retention theo yêu cầu replay và lưu lịch sử ở storage phù hợp |
| Dùng offset làm ID nghiệp vụ | Offset chỉ có nghĩa trong một partition | Dùng eventId, taskId và aggregateId |
| Gửi record có dueAt rồi mong Kafka chờ | Consumer có thể đọc record ngay | Dùng scheduler hoặc delay service để phát khi đến hạn |
| Cho consumer ngủ để chờ thời gian | Chặn xử lý partition, giảm throughput | Đưa việc quản lý thời điểm đến hạn ra scheduler |
| Dùng retry topic cho lịch nghiệp vụ dài hạn | Retry không thay thế trạng thái và lịch nghiệp vụ | Lưu lịch bền vững hoặc dùng workflow engine |
| Cho rằng producer idempotence ngăn mọi duplicate | Không bao phủ tác động ngoài Kafka hoặc mọi lần xử lý consumer | Dùng idempotency tại consumer và dịch vụ đích |
| Hủy lịch bằng cách mong xóa record Kafka | Record đã ghi vẫn có thể được consumer đọc | Dùng trạng thái hủy và version để bỏ qua command cũ |
| Dùng @Scheduled trên nhiều replica mà không điều phối | Mỗi replica có thể chạy cùng một job | Distributed claim/lock hoặc scheduler có coordination |

## 11. Checklist thiết kế trước khi triển khai

Trước khi dùng Kafka cho một luồng dữ liệu hoặc công việc có thời điểm đến hạn, hãy trả lời:

- [ ] Kafka đang phân phối event/command hay bị dùng làm nơi truy vấn tùy ý?
- [ ] Đã xác định source of truth và miền sở hữu dữ liệu?
- [ ] Mẫu truy vấn có read model, database hoặc search engine phù hợp?
- [ ] Đã hiểu offset chỉ thuộc một partition và không phải ID nghiệp vụ?
- [ ] Retention đáp ứng thời gian phục hồi và replay cần thiết?
- [ ] Có hiểu rõ topic compacted chỉ giữ trạng thái theo key, không phải toàn bộ lịch sử?
- [ ] Projection có owner, schema, index và quy trình rebuild?
- [ ] API có xử lý độ trễ eventual consistency?
- [ ] Công việc cần chạy tương lai có scheduler và trạng thái bền vững?
- [ ] Retry topic được dùng cho retry, không thay cho lịch nghiệp vụ tùy ý?
- [ ] Scheduler có claim/lease, xử lý crash và chống chạy trùng?
- [ ] Command có taskId, idempotency key và version để nhận biết lịch cũ?
- [ ] Consumer kiểm tra trạng thái nghiệp vụ hiện tại trước tác động quan trọng?
- [ ] Quy trình nhiều bước có timeout hoặc bù trừ đã có process manager/workflow phù hợp?
- [ ] Có metric, log, cảnh báo và quy trình xử lý công việc quá hạn hoặc thất bại?

## 12. Bài tập tự kiểm tra

**Bài tập 1:** Một màn hình quản trị cần tìm đơn theo customerId, trạng thái, ngày tạo và sắp xếp theo tổng tiền. Nhóm đề xuất đọc toàn bộ topic orders rồi lọc trong API. Hãy phân tích rủi ro và đề xuất kiến trúc.

**Gợi ý:** Kafka phù hợp để phân phối OrderPlaced và các event liên quan. Một projection consumer có thể cập nhật read database với index theo customerId, status, createdAt và totalAmount. API truy vấn read database thay vì quét topic.

**Bài tập 2:** Một producer gửi record vào topic với trường scheduledAt là ngày mai. Consumer đang chạy có nhận record ngay hôm nay không? Vì sao?

**Gợi ý:** Có. Kafka ghi record vào partition và consumer có thể đọc theo offset ngay khi record đến vị trí đọc. scheduledAt chỉ là dữ liệu trong payload; ứng dụng phải triển khai scheduler hoặc delay service để trì hoãn việc phát command.

**Bài tập 3:** Một lịch tự động hủy đơn đã được phát vào Kafka. Khách hàng thanh toán ngay sau đó. Làm sao ngăn command cũ hủy đơn?

**Gợi ý:** Consumer kiểm tra trạng thái đơn và version lịch hiện tại tại miền Orders trước khi thực hiện. Command chứa taskId và scheduleVersion. Nếu đơn đã thanh toán hoặc version đã thay đổi, consumer bỏ qua command cũ một cách idempotent.

**Bài tập 4:** Một ứng dụng Spring chạy bốn replica và có phương thức @Scheduled chạy lúc nửa đêm. Điều gì có thể xảy ra và cần giải quyết thế nào?

**Gợi ý:** Cả bốn replica có thể chạy job, tạo bốn lần thực thi. Dùng scheduler có coordination, distributed lock/claim hoặc thiết kế job idempotent với khóa duy nhất để chỉ một kết quả nghiệp vụ được ghi nhận.

Kafka phát huy hiệu quả khi được dùng để lưu và phân phối luồng sự kiện theo partition. Cơ sở dữ liệu và read model phục vụ truy vấn theo cấu trúc mà ứng dụng cần; scheduler và workflow engine quản lý thời điểm cùng trạng thái của công việc. Khi mỗi thành phần đảm nhiệm đúng trách nhiệm, hệ thống dễ mở rộng, phục hồi và giải thích hành vi hơn.

