# Quản lý trạng thái và lựa chọn thành phần không lưu trạng thái

Khi thiết kế ứng dụng trên đám mây, một quyết định nền tảng là **trạng thái (*state*) của hệ thống được lưu ở đâu, ai sở hữu nó và trạng thái tồn tại bao lâu**. Quyết định này ảnh hưởng đến cách mở rộng dịch vụ, xử lý sự cố, bảo vệ dữ liệu, chi phí và khả năng vận hành. Lựa chọn **thành phần không lưu trạng thái (*stateless component*)** giúp nhiều lớp ứng dụng triển khai và mở rộng linh hoạt hơn, nhưng không làm nhu cầu quản lý dữ liệu hay tính nhất quán biến mất.

Trong phạm vi kiến trúc cloud, bài học này nối yêu cầu nghiệp vụ với lựa chọn compute, mạng, kho dữ liệu và mô hình triển khai. Mục tiêu là biết **khi nào nên giữ compute không lưu trạng thái, khi nào cần thành phần có trạng thái (*stateful*), và cách phối hợp cả hai** để đáp ứng độ tin cậy, bảo mật, hiệu năng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Trạng thái là gì? Phân biệt stateless và stateful

**Trạng thái** là thông tin mà kết quả xử lý hiện tại hoặc tương lai phụ thuộc vào: dữ liệu đơn hàng, phiên đăng nhập, số dư, kết quả công việc đang thực hiện, bộ đếm, tiến trình xử lý hoặc dữ liệu được lưu tạm.

Một thành phần **stateful** giữ hoặc phụ thuộc vào trạng thái từ những lần tương tác trước. Một thành phần **stateless** không yêu cầu trạng thái phiên hay trạng thái tác vụ từ yêu cầu trước phải nằm trong bộ nhớ hoặc ổ đĩa cục bộ của chính instance ấy để xử lý yêu cầu tiếp theo. Cùng một yêu cầu hợp lệ có thể được điều phối tới instance khác tương đương.

Ví dụ:

- API xác nhận đơn hàng chỉ cần nhận yêu cầu, xác thực và đọc/ghi vào cơ sở dữ liệu dùng chung: **các instance API có thể stateless**, trong khi **hệ thống tổng thể vẫn có state**.
- API giữ giỏ hàng chỉ trong RAM của máy chủ A: instance A **stateful đối với phiên**; nếu lần gọi sau vào máy chủ B, giỏ hàng có thể không tồn tại.
- Database lưu đơn hàng, hàng đợi giữ thông điệp chờ xử lý và object storage lưu tệp: đó là những thành phần **có trách nhiệm duy trì trạng thái**.

> **Quy tắc cốt lõi:** Thiết kế stateless không có nghĩa là “không lưu dữ liệu”. Nó có nghĩa là **đưa trạng thái cần duy trì ra khỏi các instance xử lý có thể thay thế**, tới thành phần lưu trữ hoặc cơ chế phối hợp được thiết kế cho yêu cầu đó.

### Hai nghĩa của “stateless” dễ bị nhầm lẫn

1. **Stateless ở lớp compute:** Instance web/API không phụ thuộc trạng thái cục bộ của riêng nó giữa các request. Một instance khác có thể tiếp nhận request sau, nếu có quyền truy cập cùng nguồn trạng thái được quản lý.
2. **Stateless ở giao thức hoặc kiểu tương tác:** Mỗi request mang đủ ngữ cảnh cần thiết để máy chủ hiểu và xử lý, thay vì phụ thuộc trạng thái phiên hội thoại do máy chủ nắm giữ. Trong ràng buộc *stateless* của REST, trạng thái phiên phía client được gửi kèm request; việc chỉ chuyển server-side session từ RAM sang một kho dùng chung **không tự động làm giao thức trở thành stateless theo nghĩa REST**.

Trong thực hành cloud, cụm “stateless service” thường mô tả **khả năng thay thế và mở rộng các instance compute**. Cần ghi rõ đang dùng nghĩa nào để không đánh giá sai kiến trúc.

## 2. Nhận diện và phân loại trạng thái trước khi chọn công nghệ

Trạng thái có vòng đời, mức độ quan trọng và yêu cầu nhất quán khác nhau. Không nên đẩy mọi loại dữ liệu vào cùng một kho chỉ vì kho đó có tốc độ truy cập cao.

| Loại trạng thái | Ví dụ | Đặc điểm cần làm rõ | Vị trí thường phù hợp |
|---|---|---|---|
| **Nghiệp vụ bền vững** | Đơn hàng, thanh toán, tồn kho, quyền sở hữu tài sản | Không được mất tùy tiện; có quy tắc nhất quán và kiểm toán | Database giao dịch hoặc kho dữ liệu bền vững phù hợp |
| **Phiên người dùng** | Session ID, giỏ hàng chưa đặt, thông tin đăng nhập tạm | Thời hạn sống, thu hồi, phân quyền, xử lý nhiều thiết bị | Token phía client, session store dùng chung hoặc database tùy yêu cầu |
| **Trạng thái công việc** | Job đang chạy, tiến độ nhập dữ liệu, công việc chờ retry | Có cần tiếp tục sau khi worker chết? Có được xử lý lặp lại? | Durable queue, database trạng thái job, workflow engine |
| **Trạng thái tạm để tăng tốc** | Cache kết quả tìm kiếm, dữ liệu tính toán có thể tạo lại | Được mất không? Chịu được dữ liệu cũ bao lâu? | Cache trong bộ nhớ hoặc cache dùng chung có TTL và chính sách invalidation |
| **Trạng thái cục bộ ngắn hạn** | Biến cục bộ trong một request, buffer, dữ liệu trung gian | Không cần tồn tại sau request; mất khi instance chết là chấp nhận được | RAM instance xử lý |
| **Tệp và đối tượng** | Ảnh, hóa đơn PDF, bản xuất báo cáo | Độ bền, phân quyền, vòng đời, tải xuống | Object storage hoặc hệ thống lưu trữ phù hợp |
| **Cấu hình và bí mật** | Feature flag, khóa API, mật khẩu database | Nhạy cảm; cần phân phối, thay đổi và thu hồi an toàn | Dịch vụ quản lý cấu hình/secret; cung cấp tại runtime |

Với mỗi loại, hãy trả lời: **Ai là nguồn dữ liệu chuẩn (*source of truth*)? Ai được ghi? Có cần nhất quán ngay lập tức? Dữ liệu có thể bị mất hay tạo lại không? Thời gian lưu và yêu cầu phục hồi là gì?**

Ví dụ: cache hiển thị kết quả tìm kiếm có thể chấp nhận dữ liệu trễ vài giây; trạng thái “ghế đã được đặt” cần quy tắc đồng thời chặt chẽ để tránh hai giao dịch cùng giữ một ghế. Nếu cache trở thành nơi duy nhất lưu kết quả đặt chỗ thì lỗi mất cache có thể gây mất dữ liệu nghiệp vụ.

## 3. Vì sao các instance compute stateless thường phù hợp với cloud?

Các nền tảng cloud thường cung cấp cân bằng tải, nhiều bản sao ứng dụng, triển khai mới, tự mở rộng và tự thay thế instance. Những cơ chế này phát huy hiệu quả khi instance **có thể được tạo, xóa hoặc thay thế mà không làm mất trạng thái quan trọng**.

~~~mermaid
flowchart TB
    CLIENT["Người dùng"] --> LB["Load balancer"]
    LB --> API1["API instance A: stateless"]
    LB --> API2["API instance B: stateless"]
    LB --> API3["API instance C: stateless"]
    API1 --> DB[("Database: nguồn dữ liệu chuẩn")]
    API2 --> DB
    API3 --> DB
    API1 -. "nếu cần session chia sẻ" .-> SESSION[("Shared session store")]
    API2 -.-> SESSION
    API3 -.-> SESSION
~~~

Trong thiết kế này, request thứ nhất và request thứ hai của cùng người dùng có thể đến **hai instance khác nhau**. Tất cả instance dùng chung nguồn dữ liệu bền vững và, nếu ứng dụng dùng phiên ở server, cùng truy cập kho phiên phù hợp.

Lợi ích chính:

- **Mở rộng ngang:** Tăng số bản sao khi tải tăng, giảm khi tải giảm mà không phải di chuyển phiên gắn với từng máy.
- **Phục hồi:** Một instance lỗi có thể được thay bằng instance khác; request đang chạy có thể thất bại nhưng các request mới không bị phụ thuộc vào bộ nhớ instance đã mất.
- **Triển khai:** Có thể thay dần phiên bản ứng dụng theo rolling deployment, canary hoặc blue/green, nếu tương thích API và dữ liệu được duy trì.
- **Phân phối lưu lượng:** Cân bằng tải có thể chọn instance khỏe thay vì cố gắng đưa người dùng trở lại một máy cố định.
- **Vận hành:** Hạ tầng khai báo bằng mã và autoscaling đơn giản hơn khi không cần gắn ổ đĩa hoặc chuyển trạng thái riêng cho từng instance.

Tuy nhiên, stateless compute **không tự giải quyết nút thắt database, mất mát request đang xử lý hoặc lỗi logic**. Nếu 20 instance đồng thời tạo quá nhiều kết nối database, ứng dụng có thể chậm hơn hệ thống chỉ có 5 instance. Cần kiểm soát connection pool, lưu lượng, timeout và năng lực của các phụ thuộc stateful.

### Những gì vẫn có thể nằm cục bộ trên instance

Biến cục bộ trong phạm vi request, bộ đệm ngắn hạn và cache có thể tạo lại hoàn toàn vẫn có thể đặt trong RAM. Điều kiện là **tính đúng đắn của nghiệp vụ không phụ thuộc việc một giá trị cụ thể còn tồn tại ở instance cũ**. Cache cục bộ có thể làm giảm độ trễ nhưng cần TTL và invalidation thích hợp; dữ liệu cũ có thể trở thành rủi ro nếu được dùng để quyết định những thao tác quan trọng.

## 4. Quản lý trạng thái phiên và danh tính

Phiên đăng nhập là nơi dễ đưa trạng thái vào sai chỗ. Có nhiều cách triển khai, với đánh đổi khác nhau:

| Phương án | Cách hoạt động | Ưu điểm | Giới hạn và rủi ro |
|---|---|---|---|
| **Session trong RAM instance** | Máy chủ lưu session theo người dùng | Đơn giản cho một instance | Khó mở rộng ngang; mất session khi khởi động lại; cần điều phối để giữ người dùng vào đúng máy |
| **Sticky session tại load balancer** | Điều phối một người dùng về cùng instance | Giảm thay đổi đối với ứng dụng cũ | Mất cân bằng tải; instance lỗi vẫn có thể làm mất session; không thay thế cho lưu trữ bền vững |
| **Shared session store** | Instance lưu/đọc session qua kho dùng chung, client giữ session ID | API instance có thể thay thế; dễ thu hồi session tập trung | Thêm phụ thuộc mạng/kho phiên; cần HA, TTL, mã hóa, kiểm soát quyền và bảo vệ session ID |
| **Token tự chứa có chữ ký** | Client gửi token đã được ký để server kiểm tra | Có thể xác thực nhiều request mà không đọc session trung tâm | Thu hồi trước hạn khó hơn; cần giới hạn thời hạn, bảo vệ token, kiểm tra claims/audience/issuer và quản lý khóa |
| **Token ngắn hạn + trạng thái phiên/refresh tập trung** | Access token ngắn hạn; refresh/thu hồi được quản lý tập trung | Cân bằng hiệu năng và khả năng kiểm soát phiên | Nhiều thành phần hơn, cần chính sách xoay vòng và phát hiện lạm dụng |

**Token có chữ ký không đồng nghĩa với token được mã hóa.** JWT dạng JWS thường có nội dung payload đọc được; tránh đưa dữ liệu nhạy cảm không cần thiết vào claims. Server phải xác minh chữ ký với thuật toán/khóa tin cậy, thời hạn, issuer, audience và các ràng buộc liên quan; không chấp nhận token chỉ vì nội dung có vẻ hợp lệ.

Việc dùng shared session store giúp **instance compute** không gắn với phiên riêng, nhưng chính shared store lại là **thành phần stateful** và phải được thiết kế theo yêu cầu bảo mật, độ sẵn sàng, phục hồi. Nếu mất kho phiên, người dùng có thể bị đăng xuất hoặc API lỗi; điều này cần được đưa vào đánh giá SLO và sơ đồ phụ thuộc.

## 5. Không có state cục bộ không có nghĩa là không cần tính nhất quán

Vấn đề khó nhất thường xuất hiện khi nhiều instance đồng thời sửa cùng một tài nguyên. Ví dụ: hai người cùng đặt một chỗ trống. Cả hai request có thể đến hai instance API khác nhau và đọc “còn chỗ”. Nếu ứng dụng chỉ kiểm tra trước rồi ghi sau, cả hai đều có thể thành công sai.

Đối với dữ liệu nghiệp vụ quan trọng, **tính đúng đắn phải được bảo đảm ở cơ chế có thẩm quyền kiểm soát ghi**, chẳng hạn transaction, ràng buộc duy nhất, cập nhật có điều kiện, khóa hợp lý hoặc cơ chế kiểm soát đồng thời của database.

Giả sử mỗi chỗ được bán theo khung giờ cố định. Có thể dùng ràng buộc duy nhất trên cặp (seat_id, slot_start) cho các bản ghi đặt thành công nếu mô hình dữ liệu phù hợp:

~~~sql
-- Minh họa cho mô hình mỗi ghế chỉ có một lượt đặt tại một mốc giờ.
CREATE TABLE reservations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    seat_id BIGINT NOT NULL,
    slot_start TIMESTAMP NOT NULL,
    user_id BIGINT NOT NULL,
    UNIQUE (seat_id, slot_start)
);

-- Hai instance cùng INSERT một ghế và slot:
-- database chỉ cho phép một giao dịch thành công.
INSERT INTO reservations (seat_id, slot_start, user_id)
VALUES (101, TIMESTAMP '2026-12-01 09:00:00', 17);
~~~

Ví dụ này giả định slot rời rạc với thời lượng cố định. Nếu hệ thống cho đặt **khoảng thời gian giao nhau** hoặc có trạng thái hủy/giữ chỗ, cần thiết kế ràng buộc và transaction theo đúng nghiệp vụ; một UNIQUE đơn giản có thể không đủ.

### Idempotency cho thao tác có tác dụng phụ

Một request đặt chỗ có thể **thành công ở database nhưng client không nhận phản hồi** do timeout. Client thử lại sẽ tạo nguy cơ đặt chỗ lần hai nếu API không nhận biết yêu cầu trùng.

Có thể yêu cầu client gửi Idempotency-Key riêng cho mỗi thao tác tạo mới:

~~~http
POST /reservations HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: 57ea43ca-bc46-49a6-8384-2d4903cce997
Content-Type: application/json

{"seatId": 101, "slotStart": "2026-12-01T09:00:00Z"}
~~~

Ứng dụng lưu khóa, định danh người gọi, nội dung hoặc dấu vân tay request, trạng thái xử lý và kết quả vào **kho dùng chung có cơ chế ghi nguyên tử** (thường là database). Các lần gửi lại hợp lệ cùng khóa nhận cùng kết quả theo chính sách đã định; cùng khóa nhưng payload khác phải bị từ chối. Cần xác định phạm vi của khóa, thời hạn giữ, cách xử lý đồng thời và trạng thái đang xử lý. Chỉ dùng Map trong RAM của một API instance không đủ vì retry có thể tới instance khác.

**Stateless compute** và **idempotent operation** là hai thuộc tính khác nhau: stateless nói về nơi đặt trạng thái giữa các lần xử lý; idempotent nói về tác dụng của việc thực hiện lặp lại cùng một thao tác. Cả hai thường cần được thiết kế đồng thời trong ứng dụng phân tán.

## 6. Trạng thái của tác vụ nền, hàng đợi và sự kiện

Một request có thể khởi tạo công việc dài hơn thời gian HTTP timeout: gửi thông báo, xử lý ảnh, xuất báo cáo hoặc đồng bộ dữ liệu. Không nên giữ tiến độ duy nhất trong RAM của API instance rồi hy vọng instance luôn sống đến khi xong.

Một cách phổ biến là lưu công việc ở queue/workflow có độ bền phù hợp, để worker stateless lấy công việc và ghi kết quả vào kho trạng thái công việc.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as API stateless
    participant D as Database
    participant Q as Durable queue
    participant W as Worker stateless

    U->>A: Tạo đơn / yêu cầu xử lý
    A->>D: Ghi đơn và trạng thái nghiệp vụ
    D-->>A: Transaction thành công
    A->>Q: Phát yêu cầu xử lý nền
    A-->>U: Trả kết quả hoặc job ID
    Q->>W: Giao thông điệp
    W->>D: Đọc/ghi trạng thái công việc
    W-->>Q: Xác nhận sau xử lý
~~~

Sơ đồ trên mô tả luồng khái niệm. **Ghi database thành công rồi phát queue thất bại** là một khoảng hở cần xử lý. Nếu nghiệp vụ yêu cầu bảo đảm một sự kiện cuối cùng phải được phát cho giao dịch đã commit, có thể dùng **transactional outbox**: ghi bản ghi nghiệp vụ và bản ghi outbox trong cùng transaction, sau đó một tiến trình phát bản ghi outbox tới queue và đánh dấu trạng thái đã phát. Tiến trình phát có thể thử lại, nên consumer vẫn phải xử lý thông điệp trùng.

Các yêu cầu quan trọng với worker:

1. **Ack đúng lúc:** Chỉ xác nhận message sau khi công việc đã ghi kết quả cần thiết; nếu worker chết trước ack, thông điệp có thể được phát lại.
2. **Idempotent consumer:** Dựa vào event ID hoặc khóa nghiệp vụ để không thực hiện trùng tác dụng phụ.
3. **Retry có giới hạn:** Backoff, jitter và dead-letter queue khi phù hợp để lỗi cố định không làm nghẽn hệ thống.
4. **Chống xử lý quá tải:** Giới hạn concurrency, kiểm soát backpressure, quan sát độ sâu và tuổi của message.
5. **Lưu tiến độ có chủ đích:** Công việc không thể chạy lại từ đầu phải checkpoint ra ngoài worker; mỗi checkpoint cần có quy tắc nhất quán.

Queue managed giúp giảm trách nhiệm vận hành broker, nhưng đội ứng dụng vẫn phải quyết định thứ tự xử lý, thời gian lưu, semantics giao nhận (ví dụ *at-least-once*), cách chống trùng và khôi phục khi tích hợp thất bại. Không nên mặc định mọi queue đều giao đúng một lần trong mọi tình huống.

## 7. Chọn thành phần stateful phù hợp với loại dữ liệu

Chuyển state khỏi compute không có nghĩa là chuyển mọi dữ liệu sang một Redis hay database duy nhất. Hãy chọn theo **độ bền, tính nhất quán, mô hình truy cập, độ trễ và chi phí**:

| Nhu cầu | Lựa chọn thường gặp | Điều cần kiểm chứng |
|---|---|---|
| Giao dịch đặt chỗ/thanh toán | Relational database với transaction và constraint | Isolation, concurrent writes, HA, backup/restore, RTO/RPO |
| Phiên đăng nhập có TTL | Shared session store hoặc hệ thống token/phân quyền phù hợp | Thu hồi, bảo mật token, phụ thuộc vào kho phiên |
| Cache truy vấn | Cache managed hoặc local cache có TTL | Cache miss, stale data, invalidation, memory pressure |
| Trạng thái công việc chạy dài | Durable queue và database theo dõi job, hoặc workflow engine | Retry, checkpoint, độ bền, idempotency, observability |
| Ảnh, tệp lớn, tài liệu sinh ra | Object storage | Phân quyền, lifecycle, versioning, retention, mã hóa |
| Dữ liệu sự kiện cần phát lại | Event log/stream hoặc kho sự kiện phù hợp | Thứ tự trong phạm vi được hỗ trợ, retention, offset, khả năng replay |
| Trạng thái theo từng instance thực sự cần bền vững | Persistent volume và hệ điều phối workload stateful | Identity, gắn volume, lịch backup, failover, quản lý nâng cấp |

### Managed service và ranh giới trách nhiệm

Dùng database managed, cache managed hoặc queue managed có thể giảm công quản lý hạ tầng, vá lỗi và thay thế node. Nhưng nhà cung cấp không mặc nhiên bảo đảm tính đúng đắn của schema, giao dịch ứng dụng, TTL, quy tắc retry, phân quyền và RPO theo kỳ vọng doanh nghiệp. Ví dụ, một cache managed có replication vẫn có thể mất dữ liệu gần nhất ở một số chế độ failover; vì vậy **không được xem cache là nguồn dữ liệu chuẩn** nếu hợp đồng độ bền của dịch vụ không phù hợp.

Khi cần triển khai workload stateful lên Kubernetes, phân biệt:

- **Deployment** thường phù hợp cho các bản sao ứng dụng **có thể thay thế**; khởi động lại pod không được làm mất dữ liệu quan trọng.
- **StatefulSet** hỗ trợ **định danh ổn định** và phối hợp lưu trữ ổn định cho pod stateful; bản thân nó **không tạo ra cơ chế replication, backup hay consistency** của database.
- **PersistentVolume** giúp dữ liệu tồn tại ngoài vòng đời một pod trong phạm vi năng lực lưu trữ, nhưng không thay thế chính sách backup, đa vùng hoặc khôi phục thảm họa.

Một ứng dụng stateful không nhất thiết phải chạy trong Kubernetes. Nếu database managed đáp ứng yêu cầu, có thể tránh vận hành cụm database riêng, tùy ràng buộc kỹ thuật và chi phí.

## 8. Ứng dụng mẫu: nền tảng đặt chỗ có compute stateless

Giả sử hệ thống đặt chỗ cần đáp ứng các yêu cầu sau:

- Người dùng có thể đăng nhập và đặt chỗ từ nhiều thiết bị.
- Mỗi khung giờ chỉ được xác nhận một đặt chỗ cho cùng tài nguyên.
- Lưu lượng giờ cao điểm tăng gấp nhiều lần so với bình thường.
- API instance hoặc một vùng sẵn sàng có thể gặp lỗi mà dữ liệu đặt chỗ đã xác nhận vẫn được bảo vệ theo RPO thiết kế.
- Email xác nhận có thể gửi sau; việc gửi email lỗi không được làm sai kết quả ghi đặt chỗ.

Thiết kế minh họa:

~~~mermaid
flowchart TB
    U["Web / Mobile"] --> EDGE["DNS, CDN, lớp bảo vệ biên"]
    EDGE --> LB["Load balancer"]
    subgraph NET["Mạng riêng trên nền tảng cloud"]
        LB --> API1["Booking API 1 - stateless"]
        LB --> API2["Booking API 2 - stateless"]
        API1 --> DB[("Transactional database - stateful")]
        API2 --> DB
        API1 -. "tùy cơ chế phiên" .-> S[("Shared session store - stateful")]
        API2 -.-> S
        API1 -. "truy vấn có thể cache" .-> C[("Cache - dữ liệu tạo lại được")]
        API2 -.-> C
        DB --> OUT["Outbox publisher"]
        OUT --> Q[("Durable queue - stateful")]
        Q --> W1["Notification worker A - stateless"]
        Q --> W2["Notification worker B - stateless"]
    end
~~~

**Phân chia trạng thái theo vai trò:**

1. **API stateless:** Không cất trạng thái giỏ hàng/đơn đã xác nhận duy nhất trong RAM. Xác thực và phân quyền mỗi request; ghi dữ liệu qua transaction của nguồn dữ liệu chuẩn.
2. **Database stateful:** Là nguồn dữ liệu chuẩn của đặt chỗ; chịu kiểm soát đồng thời bằng cơ chế phù hợp, có chính sách backup và khôi phục.
3. **Kho phiên nếu cần:** Chỉ chứa thông tin phiên phù hợp TTL; không thay thế database nghiệp vụ.
4. **Cache:** Tăng tốc các truy vấn đọc có thể chấp nhận dữ liệu trễ; không dùng trạng thái cache để quyết định độc quyền của tài nguyên.
5. **Hàng đợi và worker:** Tách xử lý thông báo; hỗ trợ retry, chống gửi trùng và quan sát backlog.

**Đường xử lý đặt chỗ:** Client gửi request có định danh thao tác → load balancer chọn một API instance bất kỳ → API xác thực và thực hiện transaction kiểm soát đặt trùng → ghi outbox cùng transaction nếu cần phát sự kiện chắc chắn → trả kết quả → publisher chuyển sự kiện ra queue → worker gửi thông báo. Nếu API instance chết sau khi transaction commit nhưng trước response, retry cùng idempotency key giúp client truy xuất kết quả cũ mà không tạo tác dụng phụ trùng.

Lưu ý: **Mở rộng API từ 2 lên 20 instance không có nghĩa khả năng ghi database tăng 10 lần**. Phải đo transaction/s, p95 latency, kết nối, khóa tranh chấp và giới hạn dịch vụ. Nếu database là nút thắt, cần tối ưu truy vấn/chỉ mục, connection pooling, phân chia đọc-ghi có kiểm soát hoặc thay đổi mô hình dữ liệu khi thật sự cần, thay vì chỉ tăng bản sao API.

## 9. Đánh đổi quan trọng: tin cậy, bảo mật, mở rộng, chi phí, vận hành

| Khía cạnh | Lợi ích khi dùng compute stateless | Rủi ro/chi phí cần dự liệu | Cách kiểm chứng |
|---|---|---|---|
| **Độ tin cậy** | Instance hỏng dễ thay; phân tán tải qua nhiều instance/AZ | Shared database/session store/queue trở thành phụ thuộc quan trọng | Kill một instance, failover kho trạng thái, thử backup/restore |
| **Bảo mật** | Instance ít chứa dữ liệu bền vững; quyền truy cập có thể chuẩn hóa | Token bị đánh cắp, session store lộ dữ liệu, quyền truy cập DB quá rộng | Threat modeling, IAM tối thiểu, mã hóa, audit log, thử thu hồi phiên |
| **Mở rộng** | Scale ngang API/worker nhanh, linh hoạt | Database connection, lock contention, cache stampede, quota | Load test nhiều mức đồng thời, p95/p99, error rate, saturation |
| **Hiệu năng** | Dễ đưa compute gần nguồn tải, cân bằng tải | Mỗi lần cần state có thể phát sinh network hop | Profile thời gian gọi DB/cache; đo cache hit và latency thực |
| **Chi phí** | Có thể scale to demand và giảm compute nhàn rỗi | Dịch vụ managed, traffic mạng, cache, lưu trữ, backup và log có phí | Lập dự toán ở tải thấp/trung bình/đỉnh; đo cost/request |
| **Vận hành** | Rollout và tự phục hồi compute thuận lợi | Vận hành hệ phân tán, truy vết nhiều hop, migration dữ liệu | Trace xuyên dịch vụ, dashboard SLO, runbook và diễn tập sự cố |

Mẫu **stateless API + stateful storage** không tự động tạo khả dụng cao. Nếu database chỉ có một điểm lỗi, thành phần nền tảng đó có thể khiến toàn bộ chức năng ngừng dù API còn nhiều bản sao. Phải xác định mục tiêu khả dụng, **RTO** (thời gian khôi phục tối đa) và **RPO** (mức mất dữ liệu tối đa chấp nhận được) của chức năng nghiệp vụ, sau đó cấu hình và kiểm thử HA/DR phù hợp. Backup không thay thế cho HA và replication không thay thế cho backup chống xóa hoặc sửa sai dữ liệu.

### Các điểm kỹ thuật vận hành cần có

- **Graceful shutdown/draining:** Khi scale in hoặc deploy, ngừng nhận request mới, cho request đang xử lý hoàn tất trong giới hạn thời gian; worker phải xử lý quy tắc ack/retry khi bị dừng.
- **Readiness và health check:** Chỉ đưa request tới instance sẵn sàng; tránh cấu hình health check sai khiến toàn bộ instance bị loại đồng thời khi một phụ thuộc ngoài gặp sự cố tạm thời.
- **Connection pool và timeout:** Giới hạn kết nối đến database; có timeout, retry có điều kiện, exponential backoff và jitter để tránh khuếch đại sự cố.
- **Quan sát hệ thống:** Theo dõi request ID/trace ID, p95 latency, tỉ lệ lỗi, kết nối database, lock waits, cache hit ratio, độ sâu queue và tỉ lệ xử lý trùng.
- **Cấu hình và secret:** Triển khai cấu hình qua cơ chế phù hợp môi trường, quản lý secret an toàn, hạn chế quyền truy cập và có quy trình xoay vòng.
- **Dữ liệu và schema:** Migration tương thích trong lúc nhiều phiên bản API đồng thời hoạt động; rollback code không đảm bảo rollback dữ liệu.

## 10. Nguyên tắc chọn stateless hay stateful cho từng thành phần

Không phải thành phần nào cũng nên cố biến thành stateless. Một quy trình lựa chọn có thể thực hiện qua sáu câu hỏi:

1. **Trạng thái có phải dữ liệu nghiệp vụ quan trọng?** Nếu có, thiết kế nguồn dữ liệu chuẩn, transaction, kiểm toán và phương án khôi phục trước.
2. **Trạng thái có cần sống lâu hơn một request hay một instance không?** Nếu có, không để bản sao duy nhất trong RAM hoặc ổ đĩa tạm của compute.
3. **Yêu cầu tính nhất quán và đồng thời là gì?** Nếu nhiều instance có thể ghi cùng tài nguyên, cần cơ chế đồng bộ ở cấp nguồn dữ liệu.
4. **Có thể tạo lại trạng thái từ nguồn khác không?** Nếu có, có thể dùng cache và chấp nhận mất cache theo ngưỡng; nếu không, cần bảo đảm độ bền tương ứng.
5. **Có cần cố định danh tính instance hoặc tài nguyên lưu trữ không?** Nếu thực sự có (ví dụ node của hệ thống dữ liệu tự quản lý), cân nhắc mô hình stateful với identity/volume ổn định; dự trù vận hành khó hơn.
6. **Năng lực managed service và tổng chi phí có phù hợp không?** So sánh chi phí dịch vụ, công vận hành, tính năng, giới hạn, bảo mật và rủi ro phụ thuộc nhà cung cấp.

~~~mermaid
flowchart TD
    A["Một thành phần cần giữ thông tin?"] --> B{"Thông tin cần tồn tại sau request/instance?"}
    B -- "Không" --> C["Xử lý tạm cục bộ; instance có thể stateless"]
    B -- "Có" --> D{"Có thể tạo lại, mất tạm chấp nhận được?"}
    D -- "Có" --> E["Cache có TTL và invalidation phù hợp"]
    D -- "Không" --> F{"Cần giao dịch / quy tắc nhất quán mạnh?"}
    F -- "Có" --> G["Nguồn dữ liệu bền vững có transaction/constraint"]
    F -- "Không / tùy nghiệp vụ" --> H["Chọn object store, queue, event log, session store hoặc kho phù hợp"]
    E --> I["Compute truy cập state qua hợp đồng rõ ràng"]
    G --> I
    H --> I
~~~

Đây là **cây quyết định định hướng**, không phải thuật toán chọn dịch vụ tự động. Nhiều bài toán dùng hơn một kho: database làm nguồn dữ liệu chuẩn, cache để đọc nhanh, queue để xử lý nền. Mục tiêu là phân ranh giới và trách nhiệm dữ liệu rõ ràng.

## 11. Các lỗi thiết kế thường gặp

**Lỗi 1 — Lưu giỏ hàng chỉ trong RAM và bật autoscaling.** Khi người dùng bị chuyển sang instance khác, giỏ hàng biến mất. Khắc phục bằng lưu giỏ hàng trong kho dùng chung phù hợp hoặc bằng mô hình client-side state được xác minh và đồng bộ đúng cách; sticky session chỉ là biện pháp tạm với giới hạn rõ ràng.

**Lỗi 2 — Dùng cache như database chính cho giao dịch quan trọng.** Cache có thể evict key, có TTL hoặc mất dữ liệu khi failover. Khắc phục bằng nguồn dữ liệu chuẩn bền vững và quy tắc cache-aside/refresh/invalidation theo mức nhất quán yêu cầu.

**Lỗi 3 — Nghĩ stateless API thì không cần concurrency control.** Hai instance vẫn có thể đọc cùng dữ liệu rồi ghi xung đột. Khắc phục bằng transaction, ràng buộc và kiểm soát ghi tại thành phần sở hữu state.

**Lỗi 4 — Retry mọi request mà không có idempotency.** Timeout có thể xảy ra sau khi nghiệp vụ đã commit, retry dẫn đến trừ tiền hoặc đặt chỗ hai lần. Khắc phục bằng khóa nghiệp vụ/idempotency phù hợp, trạng thái xử lý nguyên tử và chính sách retry theo lỗi.

**Lỗi 5 — Chỉ quan sát CPU của API.** CPU thấp nhưng database đã chạm giới hạn connection, lock hoặc IOPS. Khắc phục bằng đo end-to-end và theo dõi phụ thuộc stateful.

**Lỗi 6 — Dùng StatefulSet rồi cho rằng database đã HA.** StatefulSet hỗ trợ danh tính ổn định của pod, còn replication/consistency/backup/failover phải do hệ thống dữ liệu và thiết kế vận hành đảm nhận.

**Lỗi 7 — Đưa tất cả dữ liệu vào JWT để khỏi gọi database.** JWT dài, khó thu hồi và có thể chứa thông tin nhạy cảm hoặc quyền đã lỗi thời. Giới hạn claims, bảo vệ token, đặt thời hạn phù hợp và kiểm tra lại trạng thái/ủy quyền với các thao tác nhạy cảm nếu yêu cầu.

## 12. Đánh giá theo tư duy Well-Architected

Hãy xem kiến trúc trạng thái như một chuỗi **quyết định có bằng chứng**, không chỉ là nhãn “stateless” hoặc “managed”.

| Trụ cột đánh giá | Câu hỏi dành cho thiết kế trạng thái | Bằng chứng cần có |
|---|---|---|
| Vận hành xuất sắc | Có biết request/job đang ở trạng thái nào và phục hồi sau lỗi ra sao? | Trace, log, trạng thái job, runbook, quy trình rollback và migration |
| Bảo mật | State ở đâu, ai đọc/ghi, token/secret được giữ và thu hồi thế nào? | IAM, mã hóa, phân quyền dữ liệu, audit, thử thu hồi phiên |
| Độ tin cậy | Mất instance, cache, một AZ hoặc database primary thì điều gì xảy ra? | Fault injection, failover/restore, đo RTO/RPO và mất mát dữ liệu |
| Hiệu quả hiệu năng | Stateless compute tăng bản sao có còn đạt p95 mục tiêu khi state store bị tải cao? | Load test, kết nối, lock, cache hit, database metrics |
| Tối ưu chi phí | Chi phí kho phiên/cache/backup và network tăng thế nào theo người dùng? | Dự toán, phân bổ chi phí, số liệu sử dụng và review cấu hình |
| Bền vững | Có loại tài nguyên nhàn rỗi và lưu dữ liệu quá thời hạn cần thiết? | Autoscaling hợp lý, TTL, lifecycle, right-sizing |

Ví dụ, mục tiêu thiết kế có thể là **p95 API dưới 400 ms ở 1.000 request/giây** và **RPO tối đa 5 phút** cho một nhóm dữ liệu. Đây chỉ là **giả định để thực hành**; mục tiêu thực tế cần căn cứ tác động nghiệp vụ và ngân sách. Muốn kiểm chứng, cần đo lúc tải cao và thử khôi phục theo cách được chọn. Một sơ đồ có hai API và database managed chưa chứng minh đạt bất kỳ con số nào.

## 13. Bài tập thực hành: thay đổi kiến trúc có trạng thái cục bộ

Một hệ thống bán vé hiện có ba máy chủ API sau load balancer. Mỗi máy lưu session và giỏ hàng trong RAM; đặt vé được kiểm tra bằng cache trước khi ghi database; email xác nhận gửi đồng bộ trong request. Khi thêm máy thứ tư, một số người dùng mất giỏ hàng. Khi nhà cung cấp email chậm, đặt vé thường timeout. Khi hai khách cùng chọn ghế, đôi khi phát sinh xác nhận trùng.

**Yêu cầu:** Đề xuất sửa đổi để hệ thống mở rộng theo lưu lượng, vẫn bảo vệ dữ liệu nghiệp vụ và có thể kiểm thử hành vi khi lỗi.

Một hướng giải quyết:

1. **Phân loại state:** Session và giỏ hàng cần tồn tại qua nhiều request; vé đã bán là dữ liệu bền vững; cache chỉ dùng tăng tốc; email là tác vụ nền.
2. **Làm API instance stateless:** Chuyển phiên/giỏ hàng sang cơ chế dùng chung hoặc thiết kế token và dữ liệu phía client phù hợp; bảo đảm request có thể tới instance bất kỳ.
3. **Đưa tính nhất quán về nguồn dữ liệu chuẩn:** Sử dụng transaction và ràng buộc tránh bán trùng ghế; cache không quyết định việc xác nhận vé.
4. **Tách email:** Ghi sự kiện qua outbox hoặc cơ chế tin cậy tương đương, đưa vào queue; worker idempotent xử lý thông báo và retry có kiểm soát.
5. **Thiết kế HA và bảo mật:** Xem lại database, session store, queue và quyền truy cập; xác định RTO/RPO; diễn tập khi mất instance/kho phiên/database.
6. **Đo trước và sau:** Kiểm thử routing ngẫu nhiên qua bốn instance, tăng tải, lỗi email, retry của client, hai request tranh chấp cùng ghế, và khả năng phục hồi từ backup.

**Câu hỏi tự kiểm tra:**

- Nếu bỏ một API instance, dữ liệu nào tuyệt đối không được mất? Dữ liệu nào có thể tạo lại?
- Vì sao shared session store làm instance API dễ thay thế hơn nhưng lại xuất hiện một phụ thuộc stateful mới?
- Nếu client timeout sau khi database commit, làm thế nào xác minh retry không tạo thêm vé?
- Cần theo dõi metric nào khi tăng số API instance nhưng p95 latency vẫn xấu đi?
- Khi nào tự vận hành một workload stateful là hợp lý hơn dịch vụ managed, và đội vận hành phải nhận thêm trách nhiệm gì?

Một thiết kế cloud tốt không cố làm **toàn bộ hệ thống** không có trạng thái. Nó xác định chính xác **trạng thái nào cần duy trì, ranh giới sở hữu và mức bảo đảm cần thiết**, rồi giữ những thành phần xử lý có thể thay thế ở trạng thái *stateless* khi điều đó phù hợp. Nhờ vậy, việc lựa chọn compute, database, cache, queue và mô hình triển khai phục vụ đúng yêu cầu nghiệp vụ và những đánh đổi có thể đo lường.
