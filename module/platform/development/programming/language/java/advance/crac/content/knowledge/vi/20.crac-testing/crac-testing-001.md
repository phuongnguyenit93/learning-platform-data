# Xây dựng tiêu chí đúng đắn cho ứng dụng trước và sau restore

Với CRaC (Coordinated Restore at Checkpoint), một ứng dụng có thể lưu trạng thái tiến trình tại checkpoint rồi tiếp tục từ trạng thái đó sau restore. Việc JVM khởi động lại thành công chưa đủ để chứng minh ứng dụng đúng. Sau một khoảng thời gian dừng, database có thể đã thay đổi, token có thể hết hạn, broker có thể đã phân phối lại message, file log có thể đã được xoay vòng và lease có thể đã được cấp cho tiến trình khác.

Do đó, kiểm thử CRaC cần trả lời một câu hỏi rộng hơn “ứng dụng có chạy lại không?”: **các bảo đảm nghiệp vụ và vận hành nào phải tiếp tục đúng sau khi tiến trình được khôi phục?** Những bảo đảm này cần được viết thành tiêu chí có thể quan sát và kiểm chứng trước khi thiết kế test.

Một bộ tiêu chí tốt xác định:

- Trạng thái nào phải được giữ nguyên qua checkpoint.
- Công việc nào phải hoàn tất, rollback hoặc được phép chạy lại.
- Tài nguyên nào phải đóng trước checkpoint và tạo lại sau restore.
- Dữ liệu hoặc credential nào phải được làm mới vì thời gian đã trôi qua.
- Khi nào instance được phép nhận request hoặc message.
- Hành vi nào được chấp nhận khi checkpoint hoặc restore thất bại.
- Bằng chứng nào chứng minh ứng dụng đáp ứng các bảo đảm đó.

Tài liệu này trình bày cách xây dựng tiêu chí đúng đắn cho cả hai phía của checkpoint: giai đoạn chuẩn bị trước khi tạo ảnh và giai đoạn phục hồi trước khi ứng dụng tiếp tục phục vụ.

## 1. Định nghĩa đúng đắn của một lần restore

Một lần restore được xem là đúng khi ứng dụng tiếp tục hoạt động mà vẫn giữ các invariant đã cam kết với người dùng và hệ thống phụ thuộc. Invariant là điều kiện phải luôn đúng, bất kể tiến trình đã chạy liên tục hay trải qua checkpoint/restore.

Ví dụ:

- Một đơn hàng đã commit trước checkpoint không bị mất sau restore.
- Một message chưa được xử lý thành công không bị acknowledgment như thể đã xử lý xong.
- Một request có thể được gửi lại không tạo ra hai khoản thanh toán.
- Một replica không tiếp tục thực hiện quyền leader sau khi lease cũ đã hết hạn.
- Một kết nối được dùng sau restore phải là kết nối hợp lệ với peer hiện tại.
- Một token hết hạn trong lúc JVM dừng không được tiếp tục dùng.
- Một instance chỉ nhận traffic khi các dependency bắt buộc đã sẵn sàng.
- Một file log sau rotation phải ghi vào đích hiện hành.

Đúng đắn không có nghĩa mọi trạng thái trong heap phải giữ nguyên. Một số trạng thái cần giữ nguyên, một số cần được tính lại, và một số phải loại bỏ. Tiêu chí phải nói rõ trạng thái nào thuộc nhóm nào.

### 1.1. Phân biệt process recovery và application recovery

| Mức | Câu hỏi | Bằng chứng |
|---|---|---|
| Process recovery | JVM có restore và tiếp tục thực thi không? | Runtime báo restore thành công, process tồn tại |
| Framework recovery | Framework và lifecycle component có hoạt động đúng không? | Bean/context, worker, scheduler và callback ở trạng thái mong đợi |
| Resource recovery | Socket, pool, file, client và native resource có hợp lệ không? | Kết nối mới, thao tác đọc/ghi thành công, không dùng handle cũ |
| Business recovery | Dữ liệu và side effect có giữ đúng invariant không? | Database, broker và kết quả nghiệp vụ nhất quán |
| Service recovery | Instance có thể nhận traffic an toàn không? | Readiness chỉ mở sau khi các điều kiện bắt buộc hoàn tất |

Một test chỉ kiểm tra process recovery có thể pass trong khi ứng dụng vẫn lỗi ở request đầu tiên. Vì vậy, tiêu chí cần bao phủ tới mức nghiệp vụ và service recovery.

### 1.2. Xác định phạm vi của tiêu chí

Trước khi viết test, hãy mô tả:

- Loại ứng dụng: HTTP service, batch worker, consumer, scheduler, CLI hay ứng dụng kết hợp.
- Loại checkpoint: JVM CRaC hay container checkpoint.
- Engine và JDK/runtime được dùng.
- Các dependency bắt buộc: database, broker, cache, API, secret manager, filesystem.
- Mô hình triển khai: một instance, nhiều replica, autoscaling hoặc rolling deployment.
- Khoảng thời gian có thể dừng giữa checkpoint và restore.
- Trạng thái nghiệp vụ có thể tồn tại tại thời điểm checkpoint.
- Cam kết về mất dữ liệu, xử lý trùng và thời gian phục hồi.

Một tiêu chí phù hợp với HTTP service không nhất thiết phù hợp với consumer xử lý message. Một worker có thể cần giữ offset và acknowledgment; một API có thể cần bảo đảm idempotency cho request bị retry.

## 2. Xây dựng bộ invariant trước khi viết test

Hãy bắt đầu từ các invariant của ứng dụng hiện tại. CRaC là một thay đổi về vòng đời tiến trình; nó không nên làm thay đổi ngữ nghĩa nghiệp vụ mà ứng dụng đã cam kết.

### 2.1. Invariant dữ liệu

Xác định:

- Dữ liệu nào đã được commit phải tồn tại sau restore.
- Dữ liệu chưa commit phải được rollback hoặc tiếp tục theo một giao thức có thể phục hồi.
- Cache nào có thể stale và cần refresh.
- Bộ đếm hoặc sequence nào phải đơn điệu và duy nhất.
- Dữ liệu nào nằm trong heap nhưng nguồn có thẩm quyền là database hoặc dịch vụ ngoài.

Ví dụ, một đơn hàng đã commit trong database trước checkpoint phải còn tồn tại sau restore. Nếu ứng dụng có cache trong heap, cache có thể giữ bản cũ; tiêu chí phải yêu cầu cache được invalidation hoặc xác minh version trước khi dùng cho quyết định nghiệp vụ.

### 2.2. Invariant về side effect

Side effect là hành động thay đổi trạng thái bên ngoài như ghi database, gửi message, thanh toán, gửi email hoặc gọi API tạo tài nguyên.

Xác định:

- Side effect nào đã hoàn tất trước checkpoint.
- Side effect nào có thể đã được gửi nhưng chưa nhận được phản hồi.
- Side effect nào có thể được gửi lại sau restore.
- Cơ chế nào ngăn thao tác trùng: transaction, idempotency key, unique constraint, inbox/outbox hoặc deduplication.

Không thể chỉ dựa vào trạng thái trong heap để biết một request bên ngoài đã được xử lý hay chưa. Nếu client gửi request, server thực hiện side effect nhưng phản hồi bị mất trước checkpoint, ứng dụng có thể không biết kết quả. Tiêu chí phải yêu cầu truy vấn trạng thái hoặc retry bằng idempotency key ổn định.

### 2.3. Invariant về quyền sở hữu và concurrency

Với ứng dụng phân tán, xác định:

- Một tài nguyên có thể có bao nhiêu owner đồng thời?
- Lease có thời hạn bao lâu?
- Ai cấp quyền leader?
- Có fencing token hoặc generation để ngăn owner cũ ghi không?
- Consumer member ID có phải duy nhất cho từng instance không?
- Nhiều replica restore từ cùng ảnh có thể cùng thực hiện tác vụ nào?

Một boolean leader trong heap không chứng minh quyền leader vẫn hợp lệ. Sau restore, ứng dụng phải xác minh lại với coordinator và chỉ thực hiện side effect khi có lease/fencing token còn hiệu lực.

### 2.4. Invariant về bảo mật

Xác định:

- Token, session, certificate và key material có thời hạn hoặc có thể bị thu hồi không?
- Credential có gắn với một replica hay workload identity không?
- Truststore hoặc policy có thể được rotate trong lúc JVM dừng không?
- Checkpoint image có chứa bí mật không?
- Restore có phải xác minh identity của môi trường hiện tại không?

Tiêu chí bảo mật phải xác nhận ứng dụng không tiếp tục dùng credential hết hạn, bị thu hồi hoặc thuộc replica khác. Không ghi token hay private key vào log để chứng minh test.

### 2.5. Invariant về thời gian

Thời gian vẫn trôi trong lúc JVM dừng. Các trạng thái phụ thuộc thời gian có thể thay đổi:

- Access token, refresh token và session.
- TLS certificate và session ticket.
- Lease, distributed lock và heartbeat.
- Cache TTL và scheduler deadline.
- DNS TTL, connection max lifetime và idle timeout.
- Business deadline hoặc thời hạn xử lý request.

Tiêu chí cần nói rõ ứng dụng dùng thời gian hiện tại sau restore để kiểm tra validity. Không sử dụng một cờ hoặc bộ đếm đã snapshot làm bằng chứng rằng một trạng thái có thời hạn vẫn còn hợp lệ.

## 3. Phân loại trạng thái để quyết định giữ, làm mới hay loại bỏ

Một cách hữu ích là lập danh mục trạng thái mà ứng dụng giữ trước checkpoint. Với từng mục, ghi nguồn có thẩm quyền, vòng đời và hành động sau restore.

| Nhóm trạng thái | Ví dụ | Chính sách sau restore |
|---|---|---|
| Cấu hình bất biến | Tên dịch vụ, schema version, parser config | Có thể giữ lại nếu phiên bản và môi trường tương thích |
| Dữ liệu bền vững | Record đã commit, offset đã lưu | Đọc hoặc xác minh từ nguồn có thẩm quyền |
| Cache có thể tái tạo | Reference data, lookup cache | Giữ nếu còn freshness; nếu không thì refresh |
| Tài nguyên hệ điều hành | Socket, file descriptor, native handle | Đóng trước checkpoint hoặc xác minh và tạo lại |
| Client/pool | JDBC pool, HTTP client, broker client | Drain/close và khởi tạo lại theo API thư viện |
| Trạng thái thời hạn | Token, lease, certificate, session | Kiểm tra lại theo thời gian hiện tại; lấy mới khi cần |
| Identity riêng instance | Instance ID, consumer member ID, temp path | Tạo hoặc truy vấn lại cho instance hiện tại |
| Công việc đang chạy | Request, transaction, message, scheduled job | Hoàn tất, rollback, lưu checkpoint nghiệp vụ hoặc retry idempotent |
| Trạng thái quyền sở hữu | Leader flag, lock, lease | Acquire lại và xác minh với coordinator |

Danh mục này giúp biến các khái niệm chung thành hành động cụ thể. Chẳng hạn, “database phải hoạt động sau restore” còn quá rộng. Tiêu chí có thể là “mọi connection thuộc pool cũ được loại bỏ trước checkpoint; pool mới chỉ mở readiness sau khi tạo được connection và chạy health query thành công”.

## 4. Tiêu chí trước checkpoint

Checkpoint chỉ nên diễn ra khi ứng dụng đã đạt một điểm an toàn. Điều này không nhất thiết có nghĩa dừng toàn bộ process, nhưng mọi công việc đang thực hiện phải có trạng thái được xác định.

### 4.1. Ngừng nhận công việc mới

Khi bắt đầu chuẩn bị checkpoint:

1. Đưa instance sang trạng thái quiescing.
2. Ngừng nhận request mới hoặc chuyển traffic sang instance khác.
3. Ngừng nhận message mới từ broker.
4. Dừng scheduler tạo tác vụ mới.
5. Không cho producer nội bộ tạo thêm công việc trong lúc drain.

Tiêu chí kiểm thử:

- Sau khi quiescing bắt đầu, không có request mới được giao vào worker đang chuẩn bị đóng.
- Message consumer không nhận thêm message mới ngoài chính sách đã định.
- Scheduler không tạo thêm lần chạy mới trong khoảng chuẩn bị checkpoint.
- Readiness hoặc routing phản ánh trạng thái instance đang rời khỏi phục vụ.

### 4.2. Drain công việc đang chạy

Một ứng dụng cần định nghĩa thế nào là “đã drain”:

- Request đang chạy đã trả response hoặc được hủy theo hợp đồng.
- Task trong queue đã hoàn tất hoặc còn nguyên để xử lý lại.
- Worker không còn thao tác ghi dở.
- Message đang xử lý đã commit kết quả trước acknowledgment, hoặc được trả lại để broker phân phối lại.
- Không còn transaction ở trạng thái không xác định.

Đặt deadline cho drain. Nếu không thể hoàn tất trong thời hạn, ứng dụng phải có chính sách rõ ràng: hủy checkpoint, hủy công việc an toàn, rollback transaction hoặc lưu trạng thái nghiệp vụ bền vững để tiếp tục sau restore.

Không dùng sleep cố định làm bằng chứng worker đã dừng. Hãy dùng latch, condition, counter, queue state hoặc API shutdown/awaitTermination để xác nhận trạng thái thực tế.

### 4.3. Transaction và ranh giới commit

Một transaction không nên bị checkpoint ở trạng thái không xác định. Trước checkpoint:

- Commit transaction đã hoàn tất về mặt nghiệp vụ.
- Rollback transaction chưa thể hoàn tất.
- Không acknowledgment message trước khi kết quả nghiệp vụ đã bền vững.
- Nếu kết quả commit không rõ do lỗi mạng, truy vấn nguồn có thẩm quyền trước khi retry.
- Với distributed transaction hoặc saga, lưu trạng thái bước đã hoàn thành ở nơi bền vững.

Tiêu chí ví dụ:

> Với mỗi request tạo đơn hàng được chấp nhận trước khi quiescing, sau restore phải tồn tại đúng một order record hoặc request được trả về trạng thái có thể retry an toàn. Không được tồn tại trường hợp response thành công nhưng order record bị mất.

### 4.4. Flush và đóng tài nguyên

Từng resource cần có tiêu chí riêng:

| Resource | Tiêu chí trước checkpoint |
|---|---|
| File writer/appender | Buffer được flush, writer được đóng, không còn thread ghi vào handle |
| JDBC pool | Không còn transaction hoặc connection đang được sử dụng; pool được suspend/close theo API |
| HTTP client | Request đang chạy được drain; client/connection pool được đóng theo lifecycle được hỗ trợ |
| Message consumer | Ngừng nhận message; acknowledgment/offset phản ánh kết quả đã commit |
| Scheduler | Ngừng schedule task mới; task đang chạy hoàn tất hoặc được ghi nhận để tính lại |
| Socket tùy biến | Luồng I/O dừng ở ranh giới giao thức; socket được đóng hoặc xử lý theo integration |
| Native resource | Được giải phóng hoặc có integration xác nhận khả năng checkpoint |
| Lease/lock | Được giải phóng hoặc có cơ chế fencing ngăn owner cũ tiếp tục ghi |

Không đóng trực tiếp một file descriptor hoặc socket bên dưới thư viện nếu thư viện vẫn giữ tham chiếu. Hãy gọi API lifecycle chính thức của owner.

### 4.5. Callback phải hoàn tất trong thời hạn

Một callback beforeCheckpoint có thể thất bại vì timeout, dependency không phản hồi hoặc worker không drain được. Tiêu chí cần quy định:

- Thời gian tối đa cho mỗi resource và toàn bộ quá trình chuẩn bị.
- Lỗi nào làm checkpoint bị hủy.
- Lỗi nào có thể retry.
- Resource đã đóng một phần được rollback hoặc đưa về trạng thái an toàn thế nào.
- Log và metric nào được phát ra khi callback thất bại.

Không đánh dấu ứng dụng “sẵn sàng checkpoint” nếu một resource bắt buộc chưa hoàn tất cleanup. Một checkpoint không nhất quán có thể khó phát hiện hơn một checkpoint thất bại rõ ràng.

## 5. Tiêu chí sau restore

Restore chỉ là bước đầu. Trước khi mở traffic, ứng dụng cần tạo lại trạng thái phụ thuộc vào môi trường và xác nhận các invariant.

### 5.1. Tạo lại tài nguyên bên ngoài

Tiêu chí phổ biến:

- Mọi socket cũ được loại bỏ hoặc không được sử dụng lại.
- Database pool tạo connection mới và chạy được health query.
- HTTP client tạo kết nối mới và xác minh TLS/hostname.
- Consumer tham gia lại group và nhận assignment hợp lệ.
- File writer mở đúng đường dẫn hiện hành sau rotation.
- Scheduler được tạo lại với lịch tính từ thời gian hiện tại.
- Native resource được khởi tạo theo integration được hỗ trợ.

Không coi một object Java khác null là bằng chứng tài nguyên bên dưới vẫn hợp lệ. Phải kiểm tra bằng thao tác thực tế phù hợp với giao thức.

### 5.2. Làm mới trạng thái có thời hạn

Sau restore, ứng dụng cần xác minh:

- Token còn hạn và đúng audience/scope.
- Certificate còn hiệu lực, hostname và trust chain đúng.
- Session ticket hoặc session cache có thể được dùng theo policy.
- Lease còn hiệu lực và thuộc instance hiện tại.
- DNS và endpoint được phân giải theo policy hiện hành.
- Cache TTL và business deadline chưa hết hạn.

Nếu một trạng thái hết hạn, ứng dụng phải lấy mới hoặc chuyển sang trạng thái chưa sẵn sàng. Không tiếp tục sử dụng dữ liệu cũ chỉ vì nó còn nằm trong heap.

### 5.3. Tạo lại identity của instance

Nếu checkpoint image có thể được dùng cho nhiều replica, các giá trị trong heap có thể giống nhau. Tiêu chí cần phân biệt:

- Service identity được chia sẻ theo thiết kế.
- Replica identity phải riêng cho mỗi bản sao.
- Process incarnation ID có thể đổi mỗi lần restore.
- Business ID và idempotency key phải ổn định theo thao tác nghiệp vụ.
- Consumer member ID, lease token và local resource path được cấp lại theo phạm vi.

Kiểm thử nhiều replica từ cùng một ảnh để phát hiện ID trùng và trạng thái quyền sở hữu bị nhân bản.

### 5.4. Thứ tự phục hồi và readiness

Các resource có quan hệ phụ thuộc phải được phục hồi đúng thứ tự. Ví dụ, database pool phải sẵn sàng trước khi worker bắt đầu xử lý message cần ghi database.

Một tiêu chí readiness tốt gồm:

1. Identity hiện tại đã được xác minh.
2. Credential bắt buộc đã được làm mới hoặc xác nhận còn hiệu lực.
3. Các client và pool bắt buộc đã tạo kết nối mới.
4. Consumer/scheduler đã đăng ký đúng trạng thái.
5. Lease và quyền sở hữu đã được xác nhận.
6. Health check nghiệp vụ tối thiểu thành công.

Liveness chỉ xác nhận process còn sống. Readiness mới quyết định instance có thể nhận traffic. Không mở readiness chỉ vì callback afterRestore đã bắt đầu hoặc JVM đã restore thành công.

## 6. Viết tiêu chí chấp nhận có thể đo được

Một tiêu chí tốt cần có điều kiện đầu vào, hành động, kết quả mong đợi và bằng chứng. Tránh các câu chung như “restore thành công”, “không mất dữ liệu” hoặc “kết nối ổn định” nếu không định nghĩa cách đo.

### 6.1. Mẫu tiêu chí

~~~text
ID:
Tên tiêu chí:
Phạm vi:
Điều kiện trước:
Thao tác checkpoint:
Điều kiện trong thời gian dừng:
Thao tác restore:
Kết quả mong đợi:
Giới hạn thời gian:
Bằng chứng:
Hành vi khi thất bại:
~~~

### 6.2. Ví dụ tiêu chí cụ thể

**AC-01 — Dữ liệu đã commit**

- Điều kiện trước: tạo một record và xác nhận transaction đã commit.
- Thao tác: checkpoint, dừng JVM, restore.
- Kết quả: record vẫn tồn tại và nội dung không thay đổi.
- Bằng chứng: truy vấn database bằng connection mới và so sánh key/value.
- Thất bại: instance không mở readiness nếu không thể xác minh database.

**AC-02 — Message đang xử lý**

- Điều kiện trước: consumer nhận message có ID xác định và bắt đầu xử lý.
- Thao tác: yêu cầu checkpoint trong lúc xử lý.
- Kết quả: message hoặc được commit đúng một lần về mặt nghiệp vụ, hoặc được broker giao lại và xử lý idempotent; không được acknowledgment trước khi kết quả bền vững.
- Bằng chứng: message ID, business record, offset/ack và số lần side effect.

**AC-03 — Kết nối database**

- Điều kiện trước: ứng dụng có pool đang hoạt động.
- Thao tác: đóng pool trước checkpoint, restart database trong thời gian dừng, restore.
- Kết quả: pool mới kết nối được sau khi database sẵn sàng; không dùng connection cũ.
- Bằng chứng: connection creation metric, health query và log pool lifecycle.
- Giới hạn: readiness chỉ mở trong thời hạn cấu hình; nếu vượt hạn, instance giữ trạng thái chưa sẵn sàng.

**AC-04 — Token hết hạn**

- Điều kiện trước: token có thời hạn ngắn và được cấp trước checkpoint.
- Thao tác: để thời gian dừng vượt quá thời hạn token rồi restore.
- Kết quả: token cũ không được gửi; ứng dụng lấy token mới trước khi gọi API được bảo vệ.
- Bằng chứng: token issuer/audience/expiry ở dạng metadata không nhạy cảm và request audit phía dịch vụ.

**AC-05 — Lease hết hạn**

- Điều kiện trước: replica A đang giữ lease và có fencing token N.
- Thao tác: checkpoint A; trong lúc dừng, lease hết hạn và replica B nhận token lớn hơn.
- Kết quả: sau restore, A không ghi bằng token N; A phải acquire lease mới hoặc ở trạng thái follower.
- Bằng chứng: coordinator lease record và storage từ chối write có token cũ.

**AC-06 — Nhiều replica**

- Điều kiện trước: một checkpoint image có thể dùng để khởi chạy ít nhất hai replica.
- Thao tác: restore đồng thời hai bản sao.
- Kết quả: service identity giống nhau theo cấu hình; replica/incarnation ID khác nhau; không trùng member ID hoặc local path.
- Bằng chứng: metadata từng replica, registry record và log/metric.

**AC-07 — File rotation**

- Điều kiện trước: ứng dụng đang ghi file log.
- Thao tác: đóng writer trước checkpoint; đổi tên file và tạo file mới khi JVM dừng; restore.
- Kết quả: log sau restore được ghi vào active path.
- Bằng chứng: nội dung file cũ/mới, inode hoặc file identity và marker log sau restore.

### 6.3. Định lượng giới hạn

Các giới hạn cần được thống nhất theo SLO của hệ thống:

- Thời gian tối đa cho beforeCheckpoint.
- Thời gian tối đa cho afterRestore.
- Thời gian từ restore tới readiness.
- Số lần retry và backoff tối đa.
- Số request hoặc message được phép retry.
- Mức mất dữ liệu cho phép (RPO) nếu có.
- Thời gian phục hồi tối đa (RTO).
- Tỷ lệ restore thành công trong một tập lần chạy.

Không chọn các con số tùy tiện. Lấy baseline startup, SLO, latency dependency và thời gian checkpoint/restore thực tế để đặt ngưỡng.

## 7. Thiết kế test matrix trước và sau restore

Một test matrix giúp bảo đảm không chỉ kiểm thử đường đi thuận lợi.

| Nhóm | Điều kiện trước checkpoint | Thay đổi trong lúc dừng | Tiêu chí sau restore |
|---|---|---|---|
| Dữ liệu | Có record đã commit | Không thay đổi hoặc có cập nhật từ replica khác | Đọc dữ liệu mới nhất theo consistency contract |
| Transaction | Có transaction đang mở | JVM dừng | Commit/rollback xác định; không để transaction mồ côi |
| HTTP request | Có request đang chạy | Client timeout hoặc retry | Không tạo side effect trùng |
| Message | Consumer giữ message | Broker session hết hạn | Join group lại, xử lý lại an toàn hoặc xác nhận kết quả |
| Database | Pool đang hoạt động | Database restart/credential rotate | Pool mới và health query thành công |
| TLS | Có TLS connection | Certificate/CA rotate | Handshake mới xác minh đúng certificate và hostname |
| File | Writer đang mở | Rename/create hoặc copytruncate | Writer mở lại đúng active path |
| Scheduler | Có lịch định kỳ | Deadline trôi qua | Chạy/bỏ qua lần missed run theo policy |
| Lease | Instance đang giữ lease | Lease hết hạn, owner khác nhận lease | Owner cũ không thể ghi bằng token cũ |
| Token | Access token còn hạn | Token hết hạn hoặc bị revoke | Refresh/re-auth trước khi gọi dịch vụ |
| Cache | Cache đã warm-up | Dữ liệu nguồn thay đổi | Cache refresh hoặc version validation |
| Identity | Instance ID trong heap | Restore thành nhiều replica | Mỗi replica có identity riêng |
| Native resource | Thư viện giữ handle | Runtime checkpoint/restore | Resource được tái tạo hoặc checkpoint bị từ chối rõ ràng |
| Filesystem | Có volume và file tạm | Mount/permission thay đổi | Đường dẫn và quyền được xác minh |
| Security | Process có policy hiện tại | Secret/certificate/policy rotate | Restore không dùng credential hoặc security context lỗi thời |
| Khả năng phục hồi | Ứng dụng khỏe mạnh | Callback hoặc dependency thất bại | Không mở readiness; lỗi được quan sát và retry theo policy |

### 7.1. Kiểm thử khoảng dừng ngắn và dài

Không chỉ restore ngay sau checkpoint. Chạy nhiều khoảng dừng:

- Gần như ngay lập tức.
- Lớn hơn idle timeout của connection.
- Lớn hơn thời hạn token hoặc session.
- Lớn hơn thời hạn lease.
- Qua thời điểm rotation chứng chỉ hoặc cấu hình.
- Đủ lâu để cache TTL và scheduler deadline thay đổi.

Khoảng dừng nên được chọn từ các timeout thật của dependency. Một test dừng 1 giây không thể chứng minh hệ thống an toàn khi production có thể dừng vài phút hoặc vài giờ.

### 7.2. Kiểm thử checkpoint lặp lại

Một ứng dụng có thể được checkpoint nhiều lần trong vòng đời. Kiểm tra:

- Callback không tích lũy listener hoặc resource trùng lặp.
- Executor không bị shutdown rồi dùng lại sai trạng thái.
- Client cũ không bị giữ lại sau mỗi lần restore.
- Mỗi incarnation tạo identity đúng chính sách.
- Cache và token được làm mới theo vòng đời.
- Không tăng dần số thread, socket, file descriptor hoặc connection.

Kiểm thử lặp giúp phát hiện resource leak và callback không idempotent.

### 7.3. Kiểm thử nhiều replica từ một checkpoint

Nếu môi trường có scale-out, restore ít nhất hai instance từ cùng một ảnh. Xác nhận:

- Replica identity khác nhau.
- Service identity vẫn giống nhau nếu đó là hợp đồng.
- Không dùng chung lease hoặc leader state.
- Consumer group có member riêng.
- File tạm, socket path và metric label không trùng.
- Credential được cấp theo policy.
- Hai replica không tạo duplicate side effect khi nhận cùng một request/message.

## 8. Kiểm thử failure path

Kiểm thử đúng đắn phải bao gồm cả tình huống không thể hoàn tất checkpoint hoặc restore.

### 8.1. beforeCheckpoint thất bại

Các lỗi có thể xảy ra:

- Worker không drain trong thời hạn.
- Database không rollback được transaction.
- File writer không flush hoặc close được.
- Client không thể đóng kết nối.
- Resource phụ thuộc chưa sẵn sàng.

Tiêu chí:

- Lỗi được báo rõ ràng.
- Checkpoint không được coi là thành công nếu resource bắt buộc chưa chuẩn bị xong.
- Ứng dụng không tiếp tục nhận traffic trong trạng thái quiescing không xác định.
- Resource đã thay đổi một phần được phục hồi hoặc ứng dụng chuyển sang shutdown có kiểm soát.

### 8.2. afterRestore thất bại

Các lỗi có thể xảy ra:

- Secret manager chưa sẵn sàng.
- Database hoặc broker đang restart.
- Chứng chỉ mới không được trust.
- Lease đã thuộc replica khác.
- Volume chưa mount hoặc chuyển read-only.

Tiêu chí:

- Instance chưa mở readiness.
- Retry có giới hạn, backoff và jitter.
- Lỗi có mã hoặc thông tin chẩn đoán phù hợp.
- Không sử dụng credential hoặc socket cũ để lách lỗi.
- Khi quá thời hạn, instance chuyển sang trạng thái lỗi có thể quan sát và được orchestrator xử lý.

### 8.3. Restore thất bại giữa chừng

Một số resource có thể đã được tạo lại trong khi resource khác thất bại. Cần xác định:

- Có thể retry callback hoặc bootstrap mà không tạo tài nguyên trùng không?
- Tài nguyên đã tạo có được đóng khi bước tiếp theo thất bại không?
- Resource nào có thể được phục hồi độc lập?
- Có cần hủy instance và tạo lại từ checkpoint không?
- Readiness có bị giữ đóng cho tới khi toàn bộ dependency bắt buộc sẵn sàng không?

Thiết kế bootstrap theo kiểu idempotent giúp có thể thử lại mà không tạo nhiều client, thread hoặc subscription trùng lặp.

### 8.4. Checkpoint image không tương thích

Checkpoint có thể gắn với JDK build, native library, kernel, filesystem và runtime cụ thể. Kiểm thử các tình huống:

- Restore bằng JDK version khác.
- Thay đổi native library hoặc agent.
- Thay đổi CPU feature hoặc node architecture.
- Thay đổi mount, volume hoặc network namespace.
- Thay đổi container runtime hoặc checkpoint engine.

Nếu môi trường không tương thích, hệ thống phải từ chối restore rõ ràng hoặc dùng đường khởi động bình thường. Không đánh dấu instance sẵn sàng khi runtime chưa xác minh được trạng thái.

## 9. Bằng chứng và observability

Một tiêu chí chỉ hữu ích nếu có thể chứng minh đã đạt. Hãy thiết kế log, metric và trace ngay từ đầu.

### 9.1. Log lifecycle

Ghi các mốc:

- Checkpoint preparation bắt đầu.
- Quiescing bắt đầu và hoàn tất.
- Số request/task/message đang chạy.
- Từng resource bắt đầu và kết thúc callback.
- Checkpoint được yêu cầu, thành công hoặc thất bại.
- Restore bắt đầu và kết thúc.
- Từng resource phục hồi thành công hoặc lỗi.
- Dependency health check.
- Readiness đóng và mở.

Mỗi log cần có service identity, replica identity, process incarnation ID và correlation ID phù hợp. Không ghi access token, refresh token, password hoặc private key.

### 9.2. Metric gợi ý

| Metric | Ý nghĩa |
|---|---|
| checkpoint_prepare_duration_seconds | Thời gian chuẩn bị trước checkpoint |
| checkpoint_resource_callback_duration_seconds | Thời gian callback theo resource |
| checkpoint_failure_total | Số lần checkpoint thất bại |
| restore_duration_seconds | Thời gian runtime restore |
| restore_resource_failure_total | Số resource phục hồi thất bại |
| restore_to_ready_seconds | Thời gian từ restore tới readiness |
| active_requests_at_checkpoint | Số request còn hoạt động khi bắt đầu checkpoint |
| pending_messages_at_checkpoint | Số message chưa hoàn tất |
| recreated_connections_total | Số connection được tạo lại |
| stale_credential_rejection_total | Số lần credential cũ bị từ chối |
| lease_reacquire_failure_total | Số lần acquire lease thất bại |
| duplicate_operation_detected_total | Số side effect trùng được phát hiện/chặn |

Tên metric là gợi ý; cần tuân thủ convention và cardinality policy của hệ thống quan sát. Không đưa request ID, user ID hoặc instance UUID vào label metric có cardinality cao. Những giá trị này phù hợp hơn trong log hoặc trace.

### 9.3. Trace và correlation

Một request có thể bắt đầu trước checkpoint và được retry sau restore. Trace nên giữ correlation hoặc idempotency key theo thao tác nghiệp vụ, trong khi process incarnation ID thay đổi theo tiến trình mới. Nhờ vậy, có thể phân biệt một thao tác nghiệp vụ duy nhất đi qua nhiều incarnation với hai thao tác khác nhau.

Không dùng process ID hoặc thread ID làm correlation nghiệp vụ ổn định. Những ID này có thể thay đổi hoặc được tái sử dụng sau restore.

## 10. Phân tầng kiểm thử

Không một loại test đơn lẻ nào đủ để xác nhận toàn bộ ứng dụng CRaC.

### 10.1. Unit test cho logic Resource

Kiểm thử riêng từng resource:

- beforeCheckpoint gọi đúng trình tự pause, drain, flush và close.
- afterRestore tạo lại resource và không dùng object cũ.
- Lỗi trong bước khởi tạo không công bố trạng thái ready.
- Retry không tạo tài nguyên trùng.
- Callback có thể được gọi nhiều lần theo lifecycle được hỗ trợ mà không rò rỉ.

Mock các dependency bên ngoài để kiểm tra thứ tự và chính sách lỗi. Không mock CRaC rồi kết luận kernel checkpoint hoạt động.

### 10.2. Integration test với CRaC runtime thật

Chạy trên JDK/runtime có CRaC support:

1. Khởi động ứng dụng với cấu hình production-like.
2. Warm-up theo đúng quy trình.
3. Gửi request/message và tạo dữ liệu kiểm thử.
4. Yêu cầu checkpoint.
5. Thay đổi trạng thái dependency trong thời gian dừng.
6. Restore từ ảnh.
7. Gửi request/message mới và kiểm tra invariant.
8. Thu thập log, metric, trạng thái database/broker và thời gian readiness.

Integration test cần cùng loại filesystem, network, runtime và dependency quan trọng như môi trường đích.

### 10.3. End-to-end test

Kiểm thử toàn luồng từ client tới database, broker và dịch vụ bên ngoài. Đặc biệt quan trọng với:

- Thanh toán và thao tác có side effect.
- Saga hoặc workflow nhiều bước.
- Consumer group và offset.
- API có retry/idempotency.
- Scheduler và batch job.
- Hệ thống có nhiều replica restore đồng thời.

### 10.4. Chaos và fault injection

Trong môi trường kiểm thử có kiểm soát, chủ động:

- Restart database hoặc broker khi JVM dừng.
- Chặn DNS hoặc network trong thời gian restore.
- Rotate certificate và token.
- Hết lease hoặc thay leader.
- Chuyển volume sang read-only.
- Làm callback timeout.
- Từ chối một lần cấp credential.
- Gửi cùng message/request nhiều lần.

Mục tiêu là chứng minh ứng dụng giữ invariant trong điều kiện lỗi, không chỉ ở đường đi thuận lợi.

## 11. Ví dụ một kịch bản kiểm thử end-to-end

Giả sử ứng dụng Orders xử lý request tạo đơn hàng, lưu database và gửi event tới broker. Ứng dụng có HTTP client tới dịch vụ pricing và một cache tham chiếu.

### 11.1. Điều kiện ban đầu

- Database chứa dữ liệu tham chiếu version 10.
- Broker có consumer group orders-events.
- Instance có token gọi pricing còn hạn 30 giây.
- Cache trong heap đã warm-up với version 10.
- Một request tạo đơn hàng có idempotency key K-100 đang được xử lý.

### 11.2. Chuẩn bị checkpoint

1. Chuyển instance sang quiescing và đóng readiness.
2. Ngừng nhận request mới.
3. Request K-100 hoàn tất transaction và ghi outbox record hoặc được rollback theo policy.
4. Consumer dừng nhận message mới; acknowledgment chỉ diễn ra sau commit.
5. HTTP client và database pool được đóng theo API.
6. Cache được đánh dấu cần xác minh version sau restore.
7. Callback resource hoàn tất và checkpoint được tạo.

### 11.3. Thay đổi trong lúc dừng

- Database được cập nhật lên reference data version 11.
- Token pricing hết hạn.
- Broker đóng session cũ và phân phối partition lại.
- Lease của instance hết hạn.

### 11.4. Phục hồi

1. Tạo process incarnation ID mới.
2. Lấy token pricing mới.
3. Tạo HTTP client và database pool mới.
4. Đọc version dữ liệu tham chiếu từ database; refresh cache từ version 10 lên 11.
5. Tham gia lại consumer group và nhận assignment mới.
6. Acquire lease mới; nếu không được cấp thì không chạy tác vụ leader.
7. Xác minh health check.
8. Mở readiness.

### 11.5. Assertion

- Kết quả của K-100 chỉ tồn tại một lần.
- Outbox event được phát đúng theo transaction contract.
- Không có message bị acknowledgment trước khi kết quả bền vững.
- Request mới dùng token mới.
- Cache không trả version 10 sau khi ứng dụng đã xác nhận version 11 là bắt buộc.
- Consumer có member identity mới.
- Instance không ghi bằng lease token cũ.
- Readiness chỉ mở sau khi các bước bắt buộc hoàn tất.
- Log/trace phân biệt được process incarnation trước và sau restore.

Kịch bản này kiểm tra một chuỗi invariant xuyên nhiều hệ thống. Nó có giá trị hơn việc chỉ kiểm tra endpoint trả HTTP 200 sau restore.

## 12. Xử lý kết quả và tiêu chí pass/fail

Trước khi chạy test, hãy xác định cách đánh giá:

### Pass

- Tất cả invariant bắt buộc được giữ.
- Resource được đóng và tạo lại đúng lifecycle.
- Không có side effect trùng hoặc dữ liệu mất ngoài hợp đồng.
- Credential và quyền sở hữu được xác minh lại.
- Readiness chỉ mở khi đủ điều kiện.
- Thời gian phục hồi nằm trong ngưỡng SLO.
- Log/metric đủ để chứng minh kết quả.

### Fail

- Dữ liệu đã commit bị mất.
- Side effect bị thực hiện trùng hoặc message bị mất do acknowledgment sai thứ tự.
- Instance dùng socket, token, lease hoặc identity đã hết hiệu lực.
- Callback bắt buộc thất bại nhưng checkpoint/restore vẫn bị coi là thành công.
- Readiness mở trước khi dependency bắt buộc sẵn sàng.
- Restore tạo tài nguyên hoặc worker trùng lặp.
- Thời gian phục hồi vượt ngưỡng mà không có hành vi fallback được định nghĩa.

### Inconclusive

- Test không thu thập đủ bằng chứng.
- Dependency test không phản ánh môi trường đích.
- Checkpoint/restore không thực sự diễn ra bằng engine dự kiến.
- Không thể xác định kết quả side effect hoặc transaction.

Không biến test inconclusive thành pass chỉ vì process vẫn sống. Nếu thiếu bằng chứng, cần bổ sung instrumentation hoặc thiết kế lại test.

## 13. Tổ chức bộ tiêu chí trong dự án

Một bộ tiêu chí có thể được lưu dưới dạng tài liệu hoặc test case có mã định danh. Mỗi tiêu chí nên liên kết với:

- Invariant nghiệp vụ mà nó bảo vệ.
- Resource hoặc component chịu trách nhiệm.
- Test unit/integration/e2e thực hiện xác minh.
- Metric hoặc log dùng làm bằng chứng.
- SLO hoặc giới hạn thời gian.
- Owner xử lý khi test thất bại.

Ví dụ mapping:

| Tiêu chí | Invariant | Component | Test | Bằng chứng |
|---|---|---|---|---|
| AC-01 dữ liệu commit | Không mất dữ liệu đã commit | Repository/transaction manager | DB integration | Record và transaction state |
| AC-02 message | Không ack trước commit | Consumer/outbox | Broker integration | Offset, ack, business record |
| AC-03 connection | Không dùng connection cũ | DataSource/HTTP client | Resource + integration | Connection ID, health query |
| AC-04 credential | Không dùng token hết hạn | Token provider | Expiry fault test | Issuer/audience/expiry metadata |
| AC-05 lease | Owner cũ không thể ghi | Coordinator/storage | Lease expiry test | Fencing token và rejected write |
| AC-06 replica | Instance ID không trùng | Bootstrap/identity provider | Multi-replica test | Replica metadata |
| AC-07 readiness | Chỉ nhận traffic khi sẵn sàng | Health/readiness endpoint | E2E | Readiness transition |

Khi code thay đổi resource lifecycle, chạy lại các test liên quan. Khi nâng JDK, framework, driver, pool hoặc container runtime, chạy lại integration test CRaC vì hành vi resource có thể thay đổi theo version.

## 14. Những lỗi khi xây dựng tiêu chí

| Lỗi | Vì sao không đủ | Cách sửa |
|---|---|---|
| Chỉ kiểm tra JVM restore thành công | Không chứng minh dependency và nghiệp vụ hoạt động | Kiểm tra tới readiness và side effect |
| Chỉ kiểm tra HTTP 200 | Request đơn giản có thể không chạm database/broker | Kiểm tra luồng nghiệp vụ có dependency thật |
| Không mô phỏng thời gian dừng | Không phát hiện token, lease, TTL hoặc connection timeout | Dừng lâu hơn timeout thực tế |
| Chỉ test một replica | Không phát hiện ID, lease hoặc member identity bị nhân bản | Restore nhiều replica từ cùng ảnh |
| Chỉ test callback bằng mock | Không kiểm tra kernel, socket, file descriptor và native resource | Thêm checkpoint/restore thật |
| Không test lỗi callback | Không biết ứng dụng xử lý trạng thái một phần ra sao | Fault injection ở từng resource |
| Dùng sleep để drain | Không chứng minh task đã dừng | Dùng cơ chế đồng bộ và trạng thái có thể quan sát |
| Không kiểm tra idempotency | Retry sau restore có thể lặp side effect | Dùng idempotency key và kiểm tra storage |
| Mở readiness ngay sau restore | Dependency có thể chưa sẵn sàng | Readiness theo health check bắt buộc |
| Không kiểm tra checkpoint image provenance | Có thể restore artifact sai môi trường hoặc không tin cậy | Xác minh digest, version, nguồn và policy |
| Không đặt ngưỡng thời gian | Không thể đánh giá RTO hoặc callback bị treo | Định nghĩa timeout và SLO |
| Không giữ log theo incarnation | Khó phân biệt lỗi trước/sau restore | Gắn process incarnation ID vào log/trace |

## 15. Checklist xây dựng tiêu chí đúng đắn

### Trước khi viết test

- [ ] Xác định loại ứng dụng và checkpoint engine.
- [ ] Liệt kê dependency và tài nguyên do ứng dụng sở hữu.
- [ ] Viết invariant dữ liệu, side effect, concurrency và security.
- [ ] Phân loại trạng thái giữ lại, làm mới hoặc loại bỏ.
- [ ] Xác định khoảng dừng tối đa và các timeout có thể hết hạn.
- [ ] Xác định cách xử lý request, transaction, message và scheduler đang chạy.

### Trước checkpoint

- [ ] Ngừng nhận công việc mới.
- [ ] Drain request, worker và queue.
- [ ] Commit/rollback transaction theo hợp đồng.
- [ ] Flush/close file và client theo API chính thức.
- [ ] Xác nhận lease/lock và quyền sở hữu.
- [ ] Có deadline cho callback và hành vi khi thất bại.

### Sau restore

- [ ] Tạo lại socket, pool, client và native resource.
- [ ] Refresh token, certificate, session và secret khi cần.
- [ ] Xác minh identity và lease.
- [ ] Refresh hoặc xác minh cache.
- [ ] Tham gia lại broker group và scheduler.
- [ ] Health check dependency bắt buộc.
- [ ] Chỉ mở readiness sau khi mọi điều kiện cần thiết đạt.

### Kiểm thử và bằng chứng

- [ ] Có unit test cho từng Resource.
- [ ] Có integration test dùng CRaC runtime thật.
- [ ] Có test khoảng dừng ngắn và dài.
- [ ] Có test callback failure và dependency unavailable.
- [ ] Có test nhiều lần checkpoint/restore.
- [ ] Có test nhiều replica từ cùng ảnh nếu cần scale-out.
- [ ] Có test side effect/idempotency và message acknowledgment.
- [ ] Có log/metric/trace phân biệt incarnation.
- [ ] Có ngưỡng RTO, timeout và retry rõ ràng.
- [ ] Có tiêu chí pass, fail và inconclusive.

## 16. Nguyên tắc cần nhớ

- Đúng đắn sau restore được định nghĩa bằng invariant nghiệp vụ và vận hành, không chỉ bằng việc JVM còn sống.
- Phân biệt process recovery, resource recovery, business recovery và service readiness.
- Mỗi trạng thái cần có chính sách rõ: giữ nguyên, xác minh, làm mới, tạo lại hoặc loại bỏ.
- Trước checkpoint, ngừng nhận việc mới, drain công việc và đưa transaction về ranh giới xác định.
- Callback resource phải có deadline, lỗi rõ ràng và chính sách cho trạng thái cleanup một phần.
- Sau restore, tạo lại kết nối, làm mới credential và xác minh quyền sở hữu trước khi phục vụ.
- Dùng idempotency và nguồn dữ liệu có thẩm quyền để xử lý side effect hoặc message có thể được gửi lại.
- Kiểm thử khoảng dừng đủ dài để token, lease, cache và connection timeout có thể thay đổi.
- Restore nhiều replica từ cùng ảnh để phát hiện identity và trạng thái quyền sở hữu bị nhân bản.
- Unit test callback không thay thế integration test bằng CRaC runtime thật.
- Readiness phải phản ánh khả năng phục vụ nghiệp vụ; không mở chỉ vì JVM restore thành công.
- Mọi tiêu chí cần có kết quả mong đợi, giới hạn đo được và bằng chứng.

Xây dựng tiêu chí đúng đắn trước và sau restore giúp nhóm phát triển biết rõ điều gì phải được bảo toàn, điều gì cần tái tạo và khi nào instance được phép hoạt động trở lại. Khi các invariant được viết thành acceptance criteria có thể đo được, kiểm thử CRaC sẽ phát hiện được lỗi dữ liệu, side effect, resource, identity và security trước khi checkpoint image được đưa vào vận hành.
