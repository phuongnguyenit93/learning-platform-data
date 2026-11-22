# Giao dịch chưa hoàn tất và ranh giới checkpoint an toàn

Khi ứng dụng Java dùng CRaC, checkpoint ghi nhận trạng thái của tiến trình tại một thời điểm. Database vẫn là một hệ thống độc lập và tiếp tục quản lý session, transaction, lock, log và dữ liệu theo vòng đời của chính nó. Vì vậy, một transaction đang mở không thể được xem như một phần trạng thái heap có thể đưa về đúng thời điểm cũ chỉ bằng cách restore JVM.

Ranh giới checkpoint an toàn đối với ứng dụng có database thường là một điểm mà mọi công việc đang thực hiện đã kết thúc transaction theo đúng quy tắc nghiệp vụ. Ứng dụng cần ngừng nhận công việc mới, chờ request và tác vụ đang chạy hoàn tất, xác nhận không còn transaction chưa kết thúc, rồi mới cho phép checkpoint. Sau restore, ứng dụng tạo hoặc xác minh lại kết nối và tiếp tục từ trạng thái dữ liệu thực tế của database.

## 1. Transaction và checkpoint thuộc hai vòng đời khác nhau

Một transaction database có trạng thái do database và transaction manager quản lý. Với JDBC, ứng dụng thường bắt đầu transaction bằng cách tắt auto-commit, thực hiện các câu SQL, sau đó gọi commit hoặc rollback.

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Thực hiện các câu SQL thuộc cùng một transaction.
        updateInventory(connection);
        insertOrder(connection);
    } catch (Exception error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }

    // Commit được thực hiện sau khi phần công việc SQL đã hoàn tất.
    // Nếu commit ném lỗi do mất kết nối, kết quả có thể chưa xác định.
    connection.commit();
}
~~~

Trong khi đó, checkpoint của CRaC ghi trạng thái tiến trình Java. Nó không tạo snapshot đồng bộ cho database và không đưa database quay về trạng thái tại thời điểm checkpoint.

Có thể phân biệt:

- **Trạng thái trong JVM:** object Connection, repository, service, biến cục bộ, trạng thái điều phối và các tham chiếu Java.
- **Trạng thái trong database:** session, transaction, lock, cursor, dữ liệu đã commit và transaction log.
- **Trạng thái giữa hai hệ thống:** một lệnh commit đã gửi nhưng phản hồi chưa về, một message đã phát nhưng chưa xác nhận, hoặc một request đã được xử lý nhưng response chưa tới client.

Các trạng thái này không tự động được checkpoint như một đơn vị nguyên tử. Object Connection còn trong heap không chứng minh session phía database còn hoạt động. Tương tự, khôi phục biến Java về giá trị trước checkpoint không làm mất một giao dịch đã commit ở database sau thời điểm đó.

## 2. Vì sao transaction chưa hoàn tất là trạng thái không an toàn?

Giả sử một request đặt hàng thực hiện ba bước:

1. Đọc tồn kho.
2. Giảm số lượng tồn kho.
3. Tạo bản ghi đơn hàng.

Nếu checkpoint xảy ra khi transaction còn mở, tiến trình có thể được khôi phục với các object và luồng ở trạng thái cũ, trong khi database đã xử lý session theo vòng đời của nó. Transaction chưa commit có thể bị rollback khi session bị đóng hoặc mất; thời điểm và cách giải phóng tài nguyên phụ thuộc database và driver. Nếu lệnh commit đã tới database nhưng phản hồi bị mất, ứng dụng có thể không biết transaction đã commit hay chưa.

Điều này tạo ra các tình huống khó xử:

- Ứng dụng nghĩ đơn hàng chưa được tạo, nhưng database đã commit đơn hàng.
- Ứng dụng khôi phục một biến trạng thái trước commit rồi gửi lại cùng thao tác, tạo dữ liệu trùng.
- Database vẫn đang giữ lock trong lúc JVM không còn xử lý request tương ứng.
- Một cursor hoặc result set cũ được tham chiếu trong heap nhưng session đã hết hiệu lực.
- Một request đang thực hiện dở bị xử lý lại sau restore trong khi thao tác cũ đã hoàn tất ở hệ thống bên ngoài.

Vì vậy, không nên giữ transaction đang mở xuyên qua checkpoint. Hãy hoàn tất hoặc rollback transaction trước khi cho phép checkpoint, đồng thời xử lý riêng tình huống kết quả commit chưa xác định.

## 3. Các trạng thái transaction và vị trí checkpoint

Một transaction thông thường có thể được nhìn theo các giai đoạn:

~~~text
Chưa bắt đầu
    |
    v
Đang thực hiện SQL
    |
    +------> Rollback hoàn tất
    |
    v
Yêu cầu commit
    |
    +------> Commit được xác nhận
    |
    +------> Phản hồi không rõ / mất kết nối
~~~

Các điểm cần phân biệt:

| Trạng thái | Ý nghĩa | Xử lý trước checkpoint |
|---|---|---|
| Chưa bắt đầu | Chưa có transaction database | Có thể checkpoint nếu không còn công việc khác đang sử dụng dependency |
| Đang thực hiện SQL | Transaction đang mở, có thể đang giữ lock và thay đổi chưa commit | Chờ hoàn tất hoặc rollback theo quy tắc nghiệp vụ |
| Đang rollback | Ứng dụng hoặc transaction manager đang hủy thay đổi | Chờ rollback hoàn tất và xác nhận trạng thái |
| Commit đã được xác nhận | Database đã xác nhận transaction commit thành công | Có thể đi tiếp sau khi hoàn tất phần công việc liên quan |
| Commit chưa rõ kết quả | Lệnh commit có thể đã được database xử lý nhưng phản hồi không tới ứng dụng | Không retry mù; cần đối soát bằng định danh nghiệp vụ/idempotency key |
| XA/in-doubt | Transaction phân tán có thể đang ở trạng thái prepared hoặc chờ coordinator quyết định | Để transaction manager thực hiện recovery theo log và cấu hình XA |

Checkpoint an toàn thường nằm giữa các đơn vị công việc đã hoàn tất, khi không còn transaction đang hoạt động và không còn kết quả commit chưa được xử lý ở tầng nghiệp vụ.

Một request có thể chứa nhiều transaction riêng biệt. Chỉ cần transaction hiện tại đã hoàn tất chưa chắc toàn bộ request đã an toàn: request có thể còn bước gọi dịch vụ ngoài, phát message hoặc cập nhật trạng thái khác. Ranh giới checkpoint cần xét toàn bộ đơn vị công việc, không chỉ cờ transaction của JDBC.

## 4. Ranh giới checkpoint an toàn được hình thành như thế nào?

Ranh giới an toàn là một điểm được ứng dụng chủ động tạo ra bằng cơ chế điều phối công việc. Nó không tự xuất hiện chỉ vì CRaC bắt đầu gọi callback.

Một quy trình điển hình:

1. **Ngừng nhận công việc mới.** Đánh dấu instance không còn nhận traffic mới, tạm dừng lịch chạy và ngừng nhận message mới.
2. **Drain công việc đang chạy.** Chờ request, job và consumer handler hiện tại kết thúc hoặc hủy theo chính sách đã định.
3. **Hoàn tất transaction.** Mỗi transaction phải commit hoặc rollback; không để connection ở trạng thái transaction mở.
4. **Xử lý kết quả chưa rõ.** Nếu commit gặp lỗi kết nối và chưa xác định được kết quả, đánh dấu đơn vị công việc cần đối soát; không gửi lại một cách mù quáng.
5. **Giải phóng tài nguyên phụ thuộc transaction.** Đóng cursor, result set và connection theo hướng dẫn của JDBC driver/connection pool; nhả lock hoặc lease nếu chính sách yêu cầu.
6. **Kiểm tra điều kiện checkpoint.** Xác nhận không còn transaction hoặc công việc cần giữ tính liên tục trong tiến trình.
7. **Thực hiện checkpoint.** Chỉ khi ứng dụng đã đạt trạng thái quiescent mới cho phép runtime tạo checkpoint.

Sau restore, ứng dụng xác minh dependency, khởi động lại consumer và scheduler, rồi mới mở traffic. Cần thực hiện theo thứ tự để không có request mới đi vào trong khi pool hoặc transaction manager chưa sẵn sàng.

## 5. Quản lý transaction ở ranh giới service

Transaction nên có phạm vi rõ ràng, thường được bao quanh bởi một đơn vị công việc ngắn. Với JDBC thuần, try-with-resources giúp connection được đóng hoặc trả về pool khi khối công việc kết thúc.

~~~java
public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createOrder(OrderCommand command) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            boolean commitAttempted = false;

            try {
                insertOrder(connection, command);
                updateInventory(connection, command);
                commitAttempted = true;
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                if (commitAttempted) {
                    throw new CommitOutcomeUnknownException(
                            command.requestId(), error);
                } else {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                }
                throw error;
            }
        }
    }

    private static final class CommitOutcomeUnknownException
            extends SQLException {
        CommitOutcomeUnknownException(String requestId, Throwable cause) {
            super("Commit outcome must be reconciled for request "
                    + requestId, cause);
        }
    }

    private void insertOrder(Connection connection, OrderCommand command)
            throws SQLException {
        // INSERT đơn hàng bằng PreparedStatement.
    }

    private void updateInventory(Connection connection, OrderCommand command)
            throws SQLException {
        // UPDATE tồn kho trong cùng transaction.
    }
}
~~~

Đoạn mã minh họa phạm vi transaction nằm trong một lần gọi service. Ứng dụng cần bảo đảm các phương thức thao tác SQL thực sự dùng cùng connection và không giữ transaction sau khi method kết thúc.

Với Spring, một phương thức được quản lý bởi @Transactional thường có transaction được mở trước khi phần thân phương thức chạy và được commit/rollback khi interceptor kết thúc lời gọi. Vì vậy, tầng điều phối checkpoint cần chờ các lời gọi transactional đang chạy kết thúc hoàn toàn. Chỉ chờ phần thân method trả về ở một tầng khác, trong khi interceptor chưa commit xong, là chưa đủ.

Không nên lưu Connection, Statement, ResultSet hoặc transaction-scoped EntityManager vào một object sống lâu để tiếp tục sử dụng sau restore. Các object này thuộc một phạm vi thao tác cụ thể và phụ thuộc session/database transaction. Hãy lấy tài nguyên từ pool trong mỗi đơn vị công việc và trả lại khi transaction hoàn tất.

## 6. Commit thất bại không đồng nghĩa transaction chắc chắn chưa commit

Một trong những tình huống quan trọng nhất là lỗi xảy ra đúng lúc gọi commit:

~~~java
connection.commit();
~~~

Ví dụ, ứng dụng gửi lệnh commit tới database. Database xử lý và commit thành công, nhưng kết nối bị đứt trước khi phản hồi đến JVM. Ứng dụng nhận SQLException nhưng không thể suy ra chỉ từ exception rằng database đã rollback.

Gọi rollback sau đó cũng không giải quyết được sự không chắc chắn: transaction có thể đã commit rồi. Gửi lại toàn bộ nghiệp vụ có thể tạo bản ghi hoặc side effect trùng lặp.

### Dùng idempotency key

Mỗi yêu cầu nghiệp vụ có thể có một định danh ổn định, ví dụ requestId hoặc orderRequestId. Database lưu định danh này cùng kết quả nghiệp vụ trong cùng transaction và đặt unique constraint để cùng một yêu cầu không được áp dụng hai lần.

~~~sql
CREATE TABLE processed_request (
    request_id VARCHAR(100) PRIMARY KEY,
    result_code VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Trong transaction:

1. Kiểm tra hoặc ghi nhận requestId theo cơ chế bảo đảm duy nhất.
2. Nếu request đã được xử lý, trả lại kết quả đã lưu.
3. Nếu chưa, thực hiện thay đổi nghiệp vụ.
4. Lưu kết quả xử lý và commit cùng transaction.

Sau restore, nếu kết quả commit trước checkpoint chưa rõ, ứng dụng mở kết nối mới và tra cứu requestId trong database. Nếu đã có kết quả, dùng lại kết quả đó; nếu chưa có, thực hiện lại theo chính sách nghiệp vụ. Việc kiểm tra và ghi requestId phải được thiết kế chống race condition, thường bằng unique constraint và xử lý duplicate key trong transaction.

Idempotency key chỉ hiệu quả khi được dùng xuyên suốt các lần retry và được lưu bền vững cùng thay đổi nghiệp vụ. Một biến boolean trong heap không thể thay thế cơ chế này.

## 7. Phối hợp database transaction với message broker

Một request có thể vừa cập nhật database vừa phát message. Nếu database commit thành công nhưng message chưa được gửi, hệ thống có thể thiếu sự kiện. Nếu message đã gửi nhưng trạng thái publish chưa được ghi nhận, sau restore ứng dụng có thể phát message lần nữa.

Transactional outbox là một mẫu thường dùng:

1. Trong cùng transaction database, cập nhật dữ liệu nghiệp vụ và ghi một bản ghi vào bảng outbox.
2. Commit transaction.
3. Một publisher riêng đọc các bản ghi outbox và gửi message.
4. Publisher đánh dấu bản ghi đã gửi theo cơ chế có thể retry.
5. Consumer xử lý idempotent hoặc dùng inbox/deduplication để phát hiện message lặp.

~~~text
Request
  |
  v
Database transaction
  |-- cập nhật dữ liệu nghiệp vụ
  |-- ghi sự kiện vào Outbox
  |
  v
Commit
  |
  v
Outbox publisher
  |
  v
Message broker
  |
  v
Consumer (idempotent / deduplication)
~~~

Với mẫu này, checkpoint có thể diễn ra sau khi transaction ghi outbox đã commit. Publisher có thể tiếp tục sau restore từ các bản ghi outbox còn chờ. Việc gửi message có thể lặp nếu publisher gặp lỗi ở ranh giới giữa gửi và đánh dấu đã gửi; consumer vẫn cần xử lý trùng an toàn.

Không nên giả định một transaction JDBC thông thường tự bao trùm nguyên tử cả database và broker. Nếu cần distributed transaction/XA, phải cấu hình và dùng transaction manager tương ứng.

## 8. XA và transaction phân tán

Trong XA, transaction có thể đi qua nhiều resource manager. Transaction manager điều phối prepare và commit/rollback. Có thể tồn tại trạng thái in-doubt khi một participant đã prepare nhưng chưa nhận quyết định cuối cùng.

Checkpoint của JVM không thay thế log bền vững của transaction manager và không snapshot đồng bộ trạng thái của mọi resource manager. Với XA:

- Không tự ý đóng hoặc rollback XAResource đang được transaction manager quản lý.
- Chờ transaction manager đưa các giao dịch đang hoạt động tới ranh giới phù hợp trước checkpoint.
- Bảo đảm transaction recovery log được lưu ở vị trí bền vững và có thể truy cập sau restore.
- Để transaction manager thực hiện recovery theo giao thức XA sau khi kết nối lại với resource manager.
- Kiểm tra cấu hình recovery identity, credentials và quyền truy cập cần thiết.

Nếu hệ thống còn giao dịch prepared/in-doubt, cần làm theo hướng dẫn vận hành của transaction manager và database. Không suy đoán rằng restore heap sẽ tự quyết định commit hay rollback thay cho coordinator.

## 9. Đưa ranh giới transaction vào CRaC Resource

Resource có thể kết nối vòng đời checkpoint với bộ điều phối công việc của ứng dụng. Các interface trong ví dụ dưới đây là interface do ứng dụng tự định nghĩa; chúng biểu diễn khả năng ngừng nhận việc, drain công việc và kiểm tra transaction.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabaseCheckpointBoundary implements Resource {
    public interface WorkCoordinator {
        void stopAdmission() throws Exception;
        void drainInFlightWork() throws Exception;
        void assertNoActiveTransactions() throws Exception;
        void verifyDatabaseReady() throws Exception;
        void resumeAdmission() throws Exception;
    }

    private final WorkCoordinator coordinator;

    public DatabaseCheckpointBoundary(WorkCoordinator coordinator) {
        this.coordinator = coordinator;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        coordinator.stopAdmission();
        coordinator.drainInFlightWork();
        coordinator.assertNoActiveTransactions();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        coordinator.verifyDatabaseReady();
        coordinator.resumeAdmission();
    }
}
~~~

Trong ví dụ:

- stopAdmission chặn request, job hoặc message mới đi vào vùng công việc cần drain.
- drainInFlightWork chờ các đơn vị công việc đang chạy kết thúc.
- assertNoActiveTransactions xác nhận không còn transaction mở trong phạm vi ứng dụng quản lý.
- verifyDatabaseReady kiểm tra database và connection pool đã sẵn sàng sau restore.
- resumeAdmission chỉ mở lại công việc khi dependency cần thiết hoạt động.

Đây là khung tích hợp, không phải bộ transaction tracker có sẵn của CRaC. Ứng dụng cần triển khai các phương thức theo kiến trúc thực tế, bao gồm mọi đường tạo transaction như HTTP request, scheduler, consumer, async task và callback nội bộ.

Đặc biệt, Resource không tự phát hiện transaction do thư viện hoặc thread không được đăng ký quản lý tạo ra. Nếu connection pool, JDBC driver hoặc framework đã có CRaC integration, hãy dùng đúng hướng dẫn của phiên bản đó để quản lý connection. Không tự đóng pool hoặc XA resource trong callback của ứng dụng nếu điều đó xung đột với integration.

Việc dừng admission cần được phối hợp với hệ thống triển khai. Ví dụ, readiness có thể chuyển sang trạng thái không nhận traffic và load balancer ngừng gửi request mới. Nhưng readiness thay đổi không có nghĩa request đang chạy đã kết thúc; vẫn cần drain và kiểm tra transaction.

afterRestore chỉ phục vụ tiến trình được khôi phục. Nếu thao tác chuẩn bị checkpoint thất bại hoặc yêu cầu checkpoint bị hủy và tiến trình ban đầu tiếp tục chạy, không thể dựa vào afterRestore để mở admission trở lại. Bộ điều phối phát lệnh checkpoint cần có đường xử lý thất bại riêng: phục hồi những tài nguyên đã đóng, xác minh transaction state và chỉ mở lại traffic khi hệ thống trở về trạng thái an toàn. Nếu không thể phục hồi, giữ instance ở trạng thái không sẵn sàng để được xử lý theo quy trình vận hành.

## 10. Những hiểu nhầm thường gặp

**“Connection còn trong heap thì transaction vẫn còn.”**

Không đúng. Object Connection là đại diện Java; session và transaction do database quản lý. Sau restore, handle có thể không còn hợp lệ và transaction chưa commit có thể đã bị database xử lý theo vòng đời session.

**“Restore sẽ rollback transaction đang mở về đúng thời điểm checkpoint.”**

Không đúng. CRaC không snapshot database. Database tự xử lý session/transaction theo quy tắc của nó; JVM không thể đưa dữ liệu bên ngoài về quá khứ.

**“SQLException từ commit có nghĩa database chưa ghi dữ liệu.”**

Không chắc chắn. Lệnh commit có thể đã được xử lý nhưng phản hồi bị mất. Cần đối soát bằng định danh idempotency hoặc transaction recovery phù hợp.

**“Chỉ cần đóng connection pool trong beforeCheckpoint.”**

Đóng pool khi request vẫn đang dùng connection có thể làm hỏng transaction. Trước tiên phải dừng công việc mới và drain các thao tác hiện tại; sau đó làm theo hướng dẫn CRaC của pool/driver.

**“Một phương thức @Transactional đã trả về thì chắc chắn toàn bộ request đã an toàn.”**

Transaction có thể đã hoàn tất, nhưng request còn có thể gọi dịch vụ khác, phát message hoặc cập nhật trạng thái khác. Ranh giới an toàn cần xét toàn bộ đơn vị công việc và side effect của nó.

**“Database và message broker sẽ cùng rollback khi JVM restore.”**

Không đúng nếu không có một cơ chế distributed transaction được cấu hình và quản lý đúng. Transaction thông thường của JDBC chỉ bảo đảm phạm vi database tương ứng.

## 11. Kiểm thử ranh giới checkpoint

Nên kiểm thử trên đúng JDK/CRaC runtime, JDBC driver, connection pool, database và transaction manager dự kiến triển khai.

Các tình huống cần kiểm tra:

- Yêu cầu checkpoint khi không có request hoặc transaction đang chạy.
- Yêu cầu checkpoint khi một transaction đang thực hiện nhiều câu SQL.
- Yêu cầu checkpoint trong lúc transaction đang commit hoặc rollback.
- Database restart hoặc đóng session trong thời gian ứng dụng tạm dừng.
- Mất kết nối đúng lúc commit và kiểm tra cơ chế đối soát idempotency.
- Transaction rollback thất bại hoặc connection không thể trả về pool.
- Consumer nhận message nhưng chưa xác nhận tại thời điểm dừng.
- Publisher gửi message thành công nhưng chưa đánh dấu outbox đã gửi.
- Restore khi database chưa sẵn sàng và xác minh ứng dụng chưa mở traffic.
- Nhiều chu kỳ checkpoint/restore để phát hiện connection cũ, transaction rò rỉ hoặc consumer bị khởi động trùng.

Log và metric nên cho biết số request đang chạy, số transaction đang hoạt động, số transaction cần đối soát, trạng thái connection pool và thời gian drain. Không ghi password, access token hoặc dữ liệu nhạy cảm vào log.

Một checkpoint chỉ nên được coi là an toàn khi điều kiện quiescence được xác nhận. Nếu còn transaction hoặc kết quả commit chưa rõ, ứng dụng cần tiếp tục xử lý hoặc chuyển đơn vị công việc đó sang cơ chế recovery trước khi checkpoint.

## 12. Kết luận

Transaction database và checkpoint JVM thuộc hai vòng đời khác nhau. CRaC lưu trạng thái tiến trình; database tiếp tục quản lý transaction và dữ liệu của nó. Vì vậy, transaction chưa hoàn tất không nên được giữ xuyên qua checkpoint.

Ứng dụng cần tạo ranh giới an toàn bằng cách ngừng nhận công việc mới, drain request và consumer, hoàn tất commit/rollback, đối soát kết quả commit chưa rõ và xác nhận không còn transaction đang hoạt động. Sau restore, kết nối và pool cần được xác minh, transaction manager phải phục hồi theo cơ chế riêng, còn các thao tác có thể được gửi lại cần idempotency hoặc deduplication để tránh side effect trùng lặp.
