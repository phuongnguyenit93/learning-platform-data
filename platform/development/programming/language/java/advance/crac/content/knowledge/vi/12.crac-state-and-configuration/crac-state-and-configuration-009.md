# Không dùng checkpoint thay cho sao lưu cơ sở dữ liệu hoặc nhật ký giao dịch

CRaC (Coordinated Restore at Checkpoint) giúp lưu và khôi phục trạng thái của một tiến trình Java. Ảnh checkpoint có thể giữ heap, thread state và các trạng thái tiến trình khác theo khả năng của JVM, CRaC và nền tảng. Nó giúp ứng dụng tiếp tục nhanh từ một trạng thái đã chuẩn bị, nhưng **không phải bản sao lưu dữ liệu bền vững của database và không thay thế transaction log/WAL**.

Cơ sở dữ liệu quản lý tính bền vững của dữ liệu bằng cơ chế riêng: transaction, write-ahead log (WAL), redo/undo log, backup, replication và quy trình recovery. Những dữ liệu này thuộc vòng đời và storage của database. Ảnh CRaC của ứng dụng không tự sao lưu các file dữ liệu database, không bảo đảm log đã được lưu trữ đầy đủ, và không cung cấp khả năng khôi phục database về một thời điểm tùy chọn.

Một hệ thống production cần cả hai cơ chế: checkpoint để rút ngắn thời gian đưa ứng dụng Java trở lại hoạt động, và backup/transaction log để bảo vệ, phục hồi dữ liệu database. Hai quy trình cần phối hợp về transaction đang chạy, version schema, credential và trạng thái dịch vụ, nhưng có mục tiêu và cách kiểm chứng riêng.

## 1. Phân biệt CRaC checkpoint, database checkpoint và database backup

Từ “checkpoint” được dùng trong nhiều lớp, nhưng không có nghĩa giống nhau.

| Cơ chế | Phạm vi được lưu | Mục tiêu chính | Có thay thế backup database không? |
| --- | --- | --- | --- |
| CRaC process checkpoint | Trạng thái tiến trình Java theo khả năng của runtime/nền tảng: heap, thread và các vùng trạng thái tiến trình | Khôi phục ứng dụng nhanh từ trạng thái đã chuẩn bị | Không. |
| Database checkpoint | Cơ chế nội bộ của database ghi/đồng bộ các trang dữ liệu và trạng thái recovery theo thiết kế của engine | Giới hạn lượng log cần replay và hỗ trợ database recovery | Không phải bản backup độc lập. |
| Database backup | Bản sao dữ liệu database, có thể là full, differential, incremental hoặc snapshot nhất quán theo công cụ database/storage | Khôi phục dữ liệu sau mất mát, hỏng hóc hoặc lỗi vận hành | Đây là cơ chế backup; cần kết hợp log nếu muốn point-in-time recovery. |
| Transaction log / WAL archive | Các bản ghi thay đổi dữ liệu và metadata transaction theo định dạng của database | Recovery sau crash, replication và point-in-time recovery theo khả năng engine | Không thay thế full backup trong mọi hệ thống; thường phải kết hợp base backup. |
| Replication | Bản sao dữ liệu được chuyển tới node khác | Availability và failover | Không thay thế backup; thao tác xóa/hỏng dữ liệu có thể được replicate sang bản sao. |

CRaC checkpoint và database checkpoint là hai thao tác ở hai lớp khác nhau. Khi nói “tạo checkpoint”, cần nêu rõ đang nói tới process image của Java hay checkpoint nội bộ database để tránh hiểu nhầm trong quy trình vận hành.

## 2. Vì sao ảnh CRaC không phải bản backup database?

Ảnh CRaC lưu trạng thái của tiến trình được checkpoint. Ứng dụng có thể chứa trong heap:

- Object domain và dữ liệu đã đọc từ database.
- Cache, kết quả truy vấn và dữ liệu tạm.
- Đối tượng `DataSource`, connection pool và thông tin cấu hình.
- Transaction context hoặc object đại diện cho transaction đang chạy.
- Buffer ứng dụng chưa được gửi hoặc chưa được commit.

Những object này không phải bản sao đầy đủ, nhất quán và có thể khôi phục độc lập của database. Chúng chỉ là trạng thái trong bộ nhớ của ứng dụng tại một thời điểm.

Ví dụ, ứng dụng đã đọc một hàng dữ liệu vào heap. Sau checkpoint, hàng đó bị cập nhật hoặc xóa trong database. Khi restore, object cũ vẫn có thể nằm trong heap dù dữ liệu nguồn đã đổi. Ngược lại, một transaction đã commit thành công trong database trước checkpoint vẫn tồn tại theo durability policy của database, dù ứng dụng được restore từ ảnh cũ.

Tương tự, nếu ứng dụng đang gom dữ liệu trong buffer hoặc ORM persistence context mà chưa commit, việc object còn trong heap không chứng minh thay đổi đó đã được ghi bền vững. Database backup và transaction log phải được quản lý ở database layer.

CRaC cũng không tự tạo một bản sao độc lập của file dữ liệu database đang được một server khác quản lý. Nếu database chạy trên máy/cluster khác, process checkpoint của Java chỉ lưu trạng thái process Java; database tiếp tục có vòng đời riêng. Nếu database chạy cùng host hoặc cùng container, việc lưu ảnh process vẫn không tương đương với backup database files và có thể còn phụ thuộc vào cách storage được quản lý.

## 3. Transaction đang chạy tại thời điểm checkpoint

Rủi ro quan trọng nhất khi checkpoint ứng dụng có kết nối database là trạng thái transaction. Một request có thể đang ở giữa nhiều bước:

```text
Nhận request
    |
    v
BEGIN transaction
    |
    v
Đọc/ghi dữ liệu
    |
    +---- checkpoint xảy ra tại đây
    |
    v
COMMIT hoặc ROLLBACK
    |
    v
Trả response
```

Nếu checkpoint diễn ra khi transaction chưa hoàn tất, ảnh process có thể chứa object và context liên quan đến transaction. Tuy nhiên, database server có thể tiếp tục, rollback transaction khi connection mất, hết timeout hoặc xử lý session theo quy tắc riêng. Không nên giả định transaction có thể được tiếp tục an toàn chỉ vì object Java vẫn còn trong heap.

Một quy trình chuẩn bị an toàn thường thực hiện:

1. Ngừng nhận request hoặc công việc mới có thể sử dụng database.
2. Chờ các request/transaction đang chạy hoàn tất trong thời hạn hữu hạn.
3. Với công việc không thể hoàn tất trong thời hạn, áp dụng chính sách hủy/rollback rõ ràng.
4. Xác nhận không còn transaction ứng dụng cần giữ mở qua checkpoint.
5. Đóng hoặc giải phóng connection pool/socket theo API được hỗ trợ.
6. Chỉ sau khi trạng thái ứng dụng an toàn mới tiếp tục tạo CRaC checkpoint.

Không nên tự ý gọi `commit()` trong callback để “cứu” tất cả transaction đang mở. Commit là quyết định nghiệp vụ, không chỉ là thao tác kỹ thuật. Callback nên phối hợp với transaction manager và request lifecycle để mỗi transaction được commit hoặc rollback theo đúng logic của nó.

## 4. Tính bền vững do database đảm nhiệm

Database thường sử dụng transaction log hoặc WAL để bảo đảm thay đổi được ghi theo quy tắc durability. Tùy engine và cấu hình, một transaction commit thành công có thể yêu cầu log được flush tới storage bền vững trước khi xác nhận commit.

Ví dụ khái quát:

```text
Ứng dụng gửi UPDATE
       |
       v
Database xử lý transaction
       |
       v
Ghi log thay đổi (WAL/redo log)
       |
       v
Flush log theo durability policy
       |
       v
COMMIT được xác nhận
       |
       v
Ứng dụng nhận kết quả commit
```

Chi tiết khác nhau theo database engine, synchronous commit, storage và cấu hình replication. Ứng dụng không nên suy luận durability chỉ từ việc đã gọi `Connection.commit()`; cần hiểu cấu hình database và bảo đảm storage/backup đáp ứng yêu cầu của hệ thống.

CRaC không thay thế bước ghi log của database. Nếu một ứng dụng được checkpoint ngay sau khi nhận xác nhận commit, dữ liệu đã commit được bảo vệ bởi database durability mechanism và backup policy. Nếu process được restore từ ảnh cũ rồi thực hiện lại cùng nghiệp vụ, ứng dụng vẫn cần xử lý khả năng duplicate operation.

## 5. Transaction log, WAL và point-in-time recovery

Transaction log ghi lại thông tin cần thiết để database phục hồi thay đổi sau crash và, tùy hệ thống, tái tạo trạng thái tại một thời điểm. WAL (Write-Ahead Logging) là nguyên tắc phổ biến: log cần được ghi bền vững trước khi các trang dữ liệu tương ứng được ghi theo trình tự do engine quy định.

Trong nhiều database, point-in-time recovery (PITR) cần:

- Một base/full backup phù hợp.
- Chuỗi transaction log/WAL liên tục từ thời điểm backup tới thời điểm cần phục hồi.
- Metadata và cấu hình cần thiết để database engine replay log.
- Quy trình restore theo tài liệu của database.

CRaC process image không chứa chuỗi WAL đầy đủ và không thể thay thế base backup. Nó cũng không phải nguồn xác định LSN/SCN hoặc recovery position của database trừ khi một quy trình tích hợp chuyên biệt lấy metadata đó từ database và quản lý nó theo cách được engine hỗ trợ.

Ví dụ về hai luồng độc lập:

```text
Luồng ứng dụng Java                    Luồng bảo vệ database
--------------------                    ----------------------
Chuẩn bị Resource                      Database tạo WAL/redo log
      |                                         |
      v                                         v
CRaC checkpoint                         Backup database
      |                                         |
      v                                         v
Restore process                         Replay log khi cần PITR
      |                                         |
      v                                         v
Mở lại traffic                           Database được phục hồi
```

Hai luồng có thể cần một kế hoạch phối hợp, nhưng thành công của luồng này không chứng minh luồng kia đã hoàn tất.

## 6. Backup, replication và checkpoint phục vụ các mục tiêu khác nhau

| Cơ chế | Khôi phục sau lỗi dữ liệu | Chuyển đổi/failover nhanh | Khôi phục trạng thái ứng dụng |
| --- | --- | --- | --- |
| CRaC checkpoint | Không | Có thể rút ngắn thời gian khởi động process trên môi trường tương thích | Có |
| Full/incremental backup | Có, theo phạm vi và thời điểm backup | Thường cần thời gian restore | Không |
| WAL/transaction log archive | Hỗ trợ replay/PITR khi có base backup và log liên tục | Tùy kiến trúc | Không |
| Database replication | Có thể hỗ trợ failover sang replica; không bảo vệ khỏi mọi lỗi logic | Có | Không |
| Application cache snapshot | Chỉ phục hồi dữ liệu cache nếu có thiết kế riêng | Có thể | Chỉ một phần trạng thái ứng dụng |

Replication không phải backup độc lập. Nếu một câu lệnh xóa nhầm dữ liệu được commit và replicate, replica có thể nhận cùng thay đổi. Backup có retention và PITR cho phép phục hồi về thời điểm trước lỗi theo khả năng database.

CRaC giúp process Java trở lại nhanh hơn, nhưng không làm cho database primary/replica khỏe mạnh hơn, không tạo thêm bản backup và không sửa được dữ liệu đã bị xóa hoặc ghi sai.

## 7. Thiết kế lifecycle Resource cho database

Một `Resource` có thể điều phối connection pool trong chu kỳ CRaC. Mục tiêu là đưa ứng dụng về trạng thái không còn transaction đang mở và tạo lại kết nối sau restore.

```java
import org.crac.Context;
import org.crac.Resource;

public final class DatabaseResource implements Resource {
    private final DatabaseWorkCoordinator workCoordinator;
    private final DatabasePoolProvider poolProvider;

    public DatabaseResource(
            DatabaseWorkCoordinator workCoordinator,
            DatabasePoolProvider poolProvider) {
        this.workCoordinator = workCoordinator;
        this.poolProvider = poolProvider;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        workCoordinator.stopAcceptingNewWork();
        if (!workCoordinator.awaitTransactionsToFinish()) {
            throw new IllegalStateException(
                    "Database transactions did not drain before checkpoint");
        }

        poolProvider.closeCurrentPool();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        poolProvider.createAndValidateNewPool();
        workCoordinator.resumeAcceptingNewWork();
    }
}
```

`DatabaseWorkCoordinator` và `DatabasePoolProvider` là abstraction của ứng dụng. Trong triển khai thực tế:

- `stopAcceptingNewWork()` phải ngăn request/job mới bắt đầu transaction.
- `awaitTransactionsToFinish()` phải có deadline và không chờ vô hạn.
- Transaction đang chạy phải tự hoàn tất hoặc rollback theo logic nghiệp vụ.
- `closeCurrentPool()` phải dùng API đúng của pool, sau khi đã drain connection đang mượn.
- `createAndValidateNewPool()` phải tạo pool phù hợp với credential/endpoint hiện tại và xác nhận kết nối database.
- Chỉ resume traffic khi pool mới và các dependency cần thiết đã sẵn sàng.

Nếu callback trước checkpoint thất bại sau khi đã dừng nhận việc hoặc đóng pool, ứng dụng cần đường rollback/resume riêng cho checkpoint bị abort. Không dựa vào `afterRestore` để hoàn tác một checkpoint thất bại. Việc điều phối và rollback phải thuộc lifecycle coordinator hoặc deployment state machine.

## 8. Không giữ transaction mở qua checkpoint

Một transaction thường gắn với connection và session cụ thể. Session có thể bị database timeout hoặc bị đóng trong khi ứng dụng ở trạng thái checkpoint. Ngay cả khi process restore thành công, transaction context cũ cũng không mặc nhiên còn hợp lệ.

Các nguyên tắc thực hành:

- Giữ transaction ngắn, không đặt network call lâu hoặc xử lý người dùng trong transaction.
- Không mở transaction trước khi chờ một callback, timer hoặc tác vụ nền có thể kéo dài.
- Trước checkpoint, drain transaction và kết thúc chúng theo quy tắc nghiệp vụ.
- Không serialize hoặc giữ một `Connection` để kỳ vọng tiếp tục transaction sau restore.
- Sau restore, tạo connection mới và bắt đầu transaction mới khi ứng dụng đã sẵn sàng.
- Với thao tác kéo dài qua nhiều bước, dùng workflow bền vững, saga hoặc state machine lưu trạng thái vào database thay vì giữ transaction mở trong thời gian dài.

Nếu nghiệp vụ cần một chuỗi thao tác nhiều bước, mỗi bước nên có trạng thái được lưu bền vững để có thể tiếp tục hoặc bù trừ sau khi process bị dừng. Transaction database không nên được dùng như một cơ chế giữ khóa xuyên qua khoảng thời gian checkpoint.

## 9. Xử lý request đã commit nhưng response chưa tới client

Một tình huống dễ bị bỏ qua:

1. Ứng dụng gửi transaction và database commit thành công.
2. Ứng dụng bị checkpoint hoặc dừng trước khi response tới client.
3. Client không biết kết quả nên retry request sau khi service restore.
4. Nghiệp vụ có thể được thực hiện lần thứ hai.

Database backup không tự giải quyết duplicate request. Ứng dụng cần idempotency key hoặc cơ chế deduplication cho những thao tác có side effect.

Ví dụ, client gửi `POST /payments` với `Idempotency-Key`. Server lưu key và kết quả cùng transaction nghiệp vụ. Khi request được retry, server tra cứu key và trả lại kết quả đã commit thay vì tạo thanh toán thứ hai.

Một bảng idempotency có thể chứa:

| Trường | Vai trò |
| --- | --- |
| `idempotency_key` | Khóa duy nhất cho một yêu cầu nghiệp vụ. |
| `request_hash` | Phát hiện cùng key nhưng payload khác. |
| `status` | Trạng thái `IN_PROGRESS`, `COMPLETED` hoặc trạng thái lỗi được định nghĩa. |
| `result_reference` | Tham chiếu kết quả đã commit để trả lại khi retry. |
| `created_at` / `expires_at` | Phục vụ retention và dọn dữ liệu deduplication theo policy. |

Việc ghi idempotency record và thay đổi nghiệp vụ cần nằm trong cùng transaction hoặc có cơ chế nhất quán tương đương. Nếu không, hệ thống có thể ghi nhận key nhưng không ghi nghiệp vụ, hoặc ghi nghiệp vụ nhưng không ghi key.

## 10. Transactional outbox và inbox

Nếu một transaction database đồng thời cần phát event ra message broker, việc commit database và gửi message là hai thao tác khác nhau. Process có thể bị checkpoint/dừng giữa hai thao tác.

Transactional outbox giải quyết vấn đề bằng cách ghi thay đổi nghiệp vụ và một outbox record trong cùng transaction database. Một publisher riêng đọc outbox và gửi event; sau khi gửi, record được đánh dấu đã xử lý theo cơ chế idempotent.

```text
BEGIN DB transaction
      |
      +--> Update business row
      |
      +--> Insert outbox event
      |
      v
COMMIT
      |
      v
Outbox publisher sends event
      |
      v
Mark event published / retry safely
```

Nếu checkpoint xảy ra sau commit nhưng trước khi publisher gửi event, outbox record vẫn nằm trong database và publisher có thể gửi sau restore. Nếu publisher gửi thành công nhưng bị dừng trước khi đánh dấu published, event có thể được gửi lại; consumer nên idempotent.

Transactional inbox hoặc bảng deduplication phía consumer giúp tránh xử lý một message nhiều lần. CRaC không thay thế outbox/inbox và không bảo đảm một side effect bên ngoài database chỉ xảy ra đúng một lần.

## 11. Phối hợp CRaC với backup và PITR

Khi cần một điểm phục hồi nhất quán cho cả ứng dụng và database, hãy định nghĩa rõ quy trình điều phối. Một ảnh CRaC riêng lẻ không tạo ra một distributed snapshot nguyên tử giữa process và database.

Một quy trình có thể gồm:

1. Chuyển service sang chế độ bảo trì hoặc quiesce, ngừng nhận request mới.
2. Drain request và transaction đang chạy; xác nhận không còn transaction ứng dụng cần giữ mở.
3. Xác nhận database backup/WAL archiving đang hoạt động theo chính sách của database.
4. Nếu yêu cầu một điểm phục hồi chung, ghi nhận database recovery marker/LSN/SCN hoặc metadata tương ứng theo công cụ database được hỗ trợ.
5. Tạo backup/snapshot database bằng cơ chế native và lưu transaction log cần thiết theo retention policy.
6. Tạo CRaC checkpoint của ứng dụng sau khi Resource đã chuẩn bị an toàn.
7. Lưu metadata liên kết: application build, JDK/CRaC version, schema version, database identity, backup id và recovery position nếu có.
8. Kiểm thử restore database theo quy trình riêng, rồi restore ứng dụng trong môi trường tương thích và xác nhận ứng dụng kết nối tới đúng database state.

Thứ tự chính xác phụ thuộc yêu cầu nhất quán, database engine và công cụ backup. Với một số hệ thống, backup online có thể diễn ra trong khi database vẫn nhận ghi; với hệ thống khác cần snapshot/lock hoặc cơ chế backup riêng. Không tự tạo file copy của data directory khi database đang chạy nếu database không hỗ trợ cách đó.

Nếu không cần một điểm phục hồi đồng bộ giữa app và DB, vẫn cần bảo đảm khi restore app nó có thể tương thích với trạng thái database hiện tại: schema, dữ liệu, credential, endpoint và event consumer offset.

## 12. Schema migration và tương thích phiên bản ứng dụng

Checkpoint có thể giữ object được tạo bởi một phiên bản ứng dụng cũ. Trong khi đó, database có thể đã được migration sang schema mới hoặc dữ liệu đã được cập nhật theo release mới.

Trước khi dùng checkpoint, cần xác nhận:

- Application build trong ảnh tương thích với schema database hiện tại.
- Migration đã hoàn tất trước khi instance restore nhận traffic.
- Code cũ không ghi vào cột/bảng đã bị loại bỏ hoặc đổi semantics.
- Các enum, serialized object và dữ liệu cache trong heap không mâu thuẫn với schema/version mới.
- Consumer offset và event format tương thích với version message hiện tại.

Chiến lược expand-and-contract thường hữu ích khi triển khai rolling upgrade: thêm schema tương thích trước, deploy ứng dụng mới, chuyển traffic, rồi mới loại bỏ schema cũ sau khi không còn instance cũ. Không restore một checkpoint cũ vào database đã thay đổi không tương thích chỉ vì ảnh process vẫn đọc được.

## 13. Bảo vệ backup, WAL và checkpoint như các tài sản riêng

Database backup và WAL có thể chứa toàn bộ dữ liệu nghiệp vụ. Ảnh CRaC có thể chứa dữ liệu heap, credential, token, cache và thông tin nhạy cảm khác. Cả hai cần được bảo vệ, nhưng retention và access policy có thể khác nhau.

Đối với database backup/WAL:

- Mã hóa khi lưu và truyền theo policy của database/organization.
- Giới hạn quyền đọc, ghi, xóa và restore.
- Duy trì retention phù hợp với yêu cầu pháp lý và RPO.
- Lưu bản sao ở failure domain khác khi kiến trúc yêu cầu.
- Theo dõi tính liên tục của WAL archive và lỗi backup.
- Kiểm thử restore định kỳ; backup chưa từng restore thử không đủ chứng minh khả năng khôi phục.

Đối với CRaC checkpoint:

- Lưu trên storage có kiểm soát quyền và bảo vệ dữ liệu.
- Gắn metadata build/runtime/host compatibility.
- Không đưa ảnh vào artifact công khai hoặc log.
- Có retention và quy trình xóa ảnh cũ.
- Không giả định ảnh checkpoint có thể dùng để khôi phục database hoặc di chuyển tùy ý giữa mọi host.

## 14. RPO và RTO: checkpoint không thay thế mục tiêu backup

RPO (Recovery Point Objective) là mức mất dữ liệu tối đa có thể chấp nhận, thường biểu diễn bằng thời gian. RTO (Recovery Time Objective) là thời gian tối đa để khôi phục dịch vụ.

CRaC chủ yếu có thể giúp giảm một phần RTO của ứng dụng bằng cách giảm công việc khởi động JVM và chuẩn bị trạng thái. Nó không tự đáp ứng RPO của database. RPO phụ thuộc backup cadence, WAL/log archiving, replication và durability policy của database.

| Mục tiêu | Cơ chế chính | Vai trò của CRaC |
| --- | --- | --- |
| Giảm thời gian khởi động ứng dụng | CRaC checkpoint/restore, image và warm-up | Có thể giảm phần khởi tạo process. |
| Giảm lượng dữ liệu có thể mất | Backup, WAL archive, replication và durability policy | Không thay thế. |
| Phục hồi database về thời điểm trước thao tác lỗi | Base backup và transaction log/PITR | Không thay thế. |
| Đưa ứng dụng trở lại sau khi database đã phục hồi | CRaC restore kết hợp refresh resource/config và readiness | Có thể giúp app sẵn sàng nhanh hơn sau khi dependency đã đúng. |

Không nên quảng bá thời gian restore CRaC như RTO tổng thể của hệ thống nếu database restore, DNS, credential refresh, schema compatibility và dependency recovery chưa được tính vào.

## 15. Các tình huống dễ nhầm lẫn

| Tình huống | Điều CRaC có thể làm | Điều vẫn cần database/application đảm nhiệm |
| --- | --- | --- |
| Database mất data volume | Restore process Java từ checkpoint | Restore database từ backup và replay log; sau đó kết nối app tới database phục hồi. |
| Một transaction chưa commit khi checkpoint | Lưu trạng thái process theo cơ chế checkpoint | Drain/commit/rollback transaction trước checkpoint; không dựa vào object Java để tiếp tục transaction. |
| Commit thành công nhưng response chưa tới client | Restore process từ ảnh đã lưu | Idempotency/deduplication để request retry không thực hiện nghiệp vụ hai lần. |
| Message chưa được publish sau commit | Restore publisher/process | Transactional outbox và retry publisher. |
| Message đã publish nhưng chưa được ack/đánh dấu | Restore consumer/publisher tùy kiến trúc | Consumer idempotency/inbox để xử lý duplicate. |
| Dữ liệu bị xóa nhầm và replicate sang replica | Restore ứng dụng không hoàn tác thay đổi | PITR từ backup/WAL tới thời điểm trước thao tác xóa. |
| Ứng dụng restore từ build cũ sau migration | Khôi phục object process cũ | Schema/version compatibility và rollout strategy. |
| Cache trong heap khác dữ liệu DB hiện tại | Khôi phục cache cũ | Invalidate, refresh hoặc kiểm tra version trước khi dùng. |

## 16. Kiểm thử quy trình phục hồi end-to-end

Một bài kiểm thử tốt cần xác nhận cả khả năng khôi phục process lẫn dữ liệu database. Có thể chia thành các bài kiểm thử độc lập và một bài kiểm thử phối hợp.

### Kiểm thử CRaC

1. Khởi chạy ứng dụng trên JDK/CRaC được hỗ trợ.
2. Chuẩn bị Resource và drain transaction trước checkpoint.
3. Tạo checkpoint.
4. Restore process trong môi trường tương thích.
5. Xác nhận connection pool mới, credential và endpoint hiện hành.
6. Chạy health check và nghiệp vụ đọc/ghi thử.

### Kiểm thử database backup/PITR

1. Tạo base backup theo công cụ database.
2. Tạo các transaction đã biết và xác nhận commit.
3. Bảo đảm WAL/transaction log được archive liên tục.
4. Phục hồi vào môi trường test từ backup và replay log tới recovery target.
5. Xác nhận dữ liệu ở thời điểm phục hồi đúng với transaction mong đợi.
6. Đo thời gian restore và lượng dữ liệu có thể mất.

### Kiểm thử phối hợp

1. Quiesce ứng dụng và drain transaction.
2. Ghi lại backup id/recovery position cùng application build/checkpoint id.
3. Tạo database backup/marker và CRaC checkpoint theo quy trình được thiết kế.
4. Thử một kịch bản lỗi: mất database node, rollback transaction, hoặc phục hồi PITR trong môi trường cô lập.
5. Restore database trước khi đưa ứng dụng trở lại, nếu kịch bản yêu cầu.
6. Restore ứng dụng và xác nhận cache, pool, credential, schema và consumer offset phù hợp với database state.
7. Gửi request có idempotency key và xác nhận không phát sinh duplicate side effect.
8. Xác nhận RPO/RTO thực tế bằng số đo.

Không thử PITR trên database production đang phục vụ traffic nếu chưa có quy trình an toàn. Dùng môi trường khôi phục cô lập để xác nhận backup và log.

## 17. Checklist vận hành

- [ ] Phân biệt rõ CRaC process checkpoint và database-native checkpoint.
- [ ] Có database backup độc lập với ảnh CRaC.
- [ ] Có transaction log/WAL archive và kiểm tra tính liên tục theo yêu cầu PITR.
- [ ] Hiểu durability policy của database và storage.
- [ ] Trước checkpoint, dừng nhận việc mới và drain transaction đang chạy.
- [ ] Không giữ transaction/connection mở qua checkpoint với kỳ vọng tiếp tục session cũ.
- [ ] Có chính sách commit/rollback rõ ràng cho request đang chạy.
- [ ] Xử lý idempotency khi commit thành công nhưng response bị mất hoặc request được retry.
- [ ] Dùng outbox/inbox khi cần phối hợp transaction database với message broker.
- [ ] Sau restore, tạo connection pool mới và validate database connectivity.
- [ ] Kiểm tra schema/version tương thích với application checkpoint.
- [ ] Refresh cache, credential, endpoint và consumer offset theo nguồn có thẩm quyền.
- [ ] Bảo vệ backup, WAL và checkpoint bằng access control/retention phù hợp.
- [ ] Có metadata liên kết build, checkpoint id, backup id và recovery position khi cần.
- [ ] Đã kiểm thử restore backup/PITR và CRaC riêng, sau đó kiểm thử end-to-end.
- [ ] RPO/RTO được đo cho toàn hệ thống, không chỉ thời gian restore JVM.

## 18. Kết luận

CRaC checkpoint lưu trạng thái của tiến trình Java để khôi phục ứng dụng nhanh. Database backup lưu dữ liệu bền vững; transaction log/WAL hỗ trợ crash recovery, replication và point-in-time recovery theo khả năng của database. Database-native checkpoint cũng là cơ chế nội bộ của engine và không đồng nghĩa với ảnh CRaC.

Hãy drain và kết thúc transaction theo logic nghiệp vụ trước khi checkpoint, đóng các kết nối theo lifecycle được hỗ trợ, và tạo lại pool sau restore. Dùng backup/WAL để bảo vệ dữ liệu, idempotency để xử lý request retry, outbox/inbox để phối hợp database với message broker, và kiểm thử PITR độc lập. CRaC có thể giảm thời gian khởi động ứng dụng, nhưng khả năng khôi phục dữ liệu vẫn phụ thuộc hoàn toàn vào chiến lược backup và recovery của database.
