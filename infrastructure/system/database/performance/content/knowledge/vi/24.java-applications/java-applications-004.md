# JDBC batch: kích thước lô, ranh giới giao dịch và kiểm chứng số lượt gửi

Khi ứng dụng Java ghi hàng nghìn hoặc hàng triệu bản ghi, gửi từng câu lệnh riêng lẻ có thể tạo nhiều lượt trao đổi giữa ứng dụng và cơ sở dữ liệu. Mỗi lần gửi đều có thể phát sinh chi phí truyền mạng, xử lý giao thức, phân tích hoặc thực thi câu lệnh, kiểm tra ràng buộc và ghi log. JDBC batch cho phép gom nhiều thao tác cùng mẫu vào một batch để driver gửi và xử lý theo cách phù hợp với hệ quản trị. Tuy nhiên, một lời gọi \`executeBatch()\` không bảo đảm mọi driver biến toàn bộ lô thành một câu SQL duy nhất hoặc đúng một network round trip.

Trong chương **Ứng dụng Java** của module **DATABASE_PERFORMANCE**, bài học này trình bày cách dùng JDBC batch, chọn kích thước lô, xác định ranh giới giao dịch và kiểm chứng số lượt gửi thực tế. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Vì vậy, tối ưu batch cần đánh giá cả ứng dụng, JDBC driver, giao thức, database và workload đồng thời, đồng thời giữ đúng yêu cầu toàn vẹn dữ liệu.

## 1. JDBC batch giải quyết chi phí nào?

Nếu ứng dụng gửi một câu INSERT cho từng hàng, luồng xử lý thường lặp lại:

1. Ứng dụng bind tham số cho câu lệnh.
2. Driver chuyển câu lệnh và tham số thành thông điệp giao thức.
3. Database nhận và thực thi câu lệnh.
4. Database trả trạng thái hoặc số hàng bị ảnh hưởng.
5. Ứng dụng tiếp tục với bản ghi kế tiếp.

Với số lượng lớn, chi phí cố định cho mỗi lần gửi có thể chiếm tỷ lệ đáng kể. Batch cho phép ứng dụng chuẩn bị nhiều bộ tham số cho cùng một câu lệnh rồi gọi executeBatch để driver xử lý chúng theo một nhóm.

Các lợi ích có thể đạt được:

- Giảm số lần ứng dụng gọi API thực thi riêng lẻ.
- Cho driver cơ hội gửi nhiều thao tác trong cùng một lần trao đổi hoặc tối ưu giao thức.
- Tái sử dụng PreparedStatement và kế hoạch thực thi.
- Giảm chi phí parse/prepare lặp lại trong các trường hợp driver và database hỗ trợ.
- Tăng thông lượng khi ghi nhiều bản ghi có cấu trúc giống nhau.

Batch không loại bỏ chi phí xử lý từng hàng ở database. Mỗi hàng vẫn cần kiểm tra kiểu dữ liệu, constraint, index, trigger, foreign key, transaction log và các quy tắc nghiệp vụ. Nếu nút thắt là index maintenance, lock contention, I/O log hoặc trigger đắt, gom lệnh thành batch có thể chỉ cải thiện một phần.

## 2. Phân biệt batch API, network round trip và transaction

Ba khái niệm thường bị nhầm:

- **Batch API:** ứng dụng gom nhiều lệnh hoặc bộ tham số và gọi executeBatch.
- **Network round trip:** một lượt trao đổi thực tế giữa client và server qua giao thức. Một lần gọi API có thể tạo một hoặc nhiều lượt mạng tùy driver và protocol.
- **Transaction:** đơn vị commit hoặc rollback theo ranh giới ACID. Một batch có thể nằm trong một transaction, hoặc có thể được chia qua nhiều transaction.

Ví dụ, một batch gồm 500 bộ tham số có thể được driver gửi trong một thông điệp hoặc nhiều gói; server cũng có thể thực thi từng câu lệnh riêng, hoặc driver viết lại thành dạng multi-row INSERT nếu hỗ trợ và được bật. Việc gọi executeBatch một lần không chứng minh đã có một round trip duy nhất.

Tương tự, executeBatch không tự động có nghĩa toàn bộ batch được commit nguyên tử. Nếu autoCommit đang bật, hành vi commit theo từng statement và cách driver triển khai batch cần được hiểu rõ. Khi cần một đơn vị công việc có thể rollback, ứng dụng nên quản lý transaction tường minh.

## 3. Dùng PreparedStatement để tạo batch

PreparedStatement phù hợp khi nhiều hàng dùng cùng mẫu SQL và khác nhau ở giá trị tham số.

Ví dụ:

~~~java
String sql = """
    INSERT INTO order_items
        (order_id, product_id, quantity, unit_price)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderItem item : items) {
        ps.setLong(1, item.orderId());
        ps.setLong(2, item.productId());
        ps.setInt(3, item.quantity());
        ps.setBigDecimal(4, item.unitPrice());
        ps.addBatch();
    }

    int[] updateCounts = ps.executeBatch();
}
~~~

Mỗi lần addBatch lưu bộ tham số hiện tại vào batch của PreparedStatement. executeBatch yêu cầu driver thực thi các phần tử đã được thêm.

Ưu điểm của PreparedStatement:

- Câu lệnh có cấu trúc cố định, tham số được bind theo kiểu.
- Giảm nguy cơ SQL injection so với nối chuỗi.
- Có thể tái sử dụng phần chuẩn bị câu lệnh.
- Tránh parse lại toàn bộ SQL text cho mỗi hàng trong những trường hợp driver/database hỗ trợ reuse.

Không nên tạo một PreparedStatement mới cho từng hàng nếu mục tiêu là batch. Hãy tạo một statement cho nhóm thao tác, thêm tham số và thực thi theo lô, sau đó đóng statement đúng cách.

## 4. Batch insert nhiều hàng

Một quy trình insert thường gồm chuẩn bị statement, thêm từng bộ tham số, thực thi batch và kiểm tra kết quả.

~~~java
connection.setAutoCommit(false);

String sql = """
    INSERT INTO events (event_id, event_type, occurred_at)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Event event : events) {
        ps.setLong(1, event.id());
        ps.setString(2, event.type());
        ps.setObject(3, event.occurredAt());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
    verifyBatchCounts(counts, events.size());

    connection.commit();
} catch (SQLException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    connection.setAutoCommit(true);
}
~~~

Đây là mẫu minh họa. Trong ứng dụng thực tế, connection thường được lấy từ connection pool; cần quản lý việc trả connection, trạng thái autoCommit và lỗi khi reset trạng thái. Không được để một connection quay lại pool với transaction đang mở hoặc cấu hình session ngoài dự kiến.

Nếu vòng lặp có thể thêm hàng triệu phần tử, không nên giữ tất cả trong một batch duy nhất. Hãy chia thành các chunk để giới hạn bộ nhớ và kiểm soát transaction.

## 5. Batch update và delete

Batch cũng phù hợp với các thao tác cập nhật hoặc xóa có cùng mẫu câu lệnh:

~~~java
String sql = """
    UPDATE inventory
    SET available_quantity = available_quantity - ?
    WHERE product_id = ?
      AND available_quantity >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Reservation reservation : reservations) {
        ps.setInt(1, reservation.quantity());
        ps.setLong(2, reservation.productId());
        ps.setInt(3, reservation.quantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

Cần hiểu số hàng bị ảnh hưởng. Với câu UPDATE có điều kiện, kết quả 0 có thể có nghĩa bản ghi không tồn tại, không đủ tồn kho hoặc không thỏa điều kiện. Không được tự động coi mọi phần tử trong batch đều thành công chỉ vì executeBatch không ném exception.

Nếu nghiệp vụ cần phân biệt nguyên nhân, có thể cần truy vấn bổ sung, thiết kế câu lệnh trả trạng thái rõ hơn hoặc dùng cơ chế database-specific. Hãy tránh thêm một SELECT cho từng hàng nếu điều đó tái tạo chi phí round trip mà batch đang muốn giảm.

## 6. Chọn kích thước batch

Batch size là số thao tác hoặc bộ tham số được gửi trong một lần executeBatch. Không có một giá trị tối ưu chung cho mọi hệ thống.

Batch quá nhỏ có thể làm tăng số lần gọi executeBatch và số lượt trao đổi. Batch quá lớn có thể:

- Giữ nhiều bộ tham số trong heap của ứng dụng hoặc driver.
- Tăng kích thước thông điệp mạng.
- Tạo transaction dài và giữ lock lâu.
- Tăng bộ nhớ và công việc xử lý ở database.
- Làm transaction log hoặc undo/redo phát sinh đột biến.
- Tăng thời gian rollback khi lỗi.
- Làm một batch thất bại có phạm vi ảnh hưởng lớn.
- Tăng độ trễ cho các request khác do cạnh tranh CPU, I/O hoặc connection.

Kích thước lô nên được xác định bằng thử nghiệm. Có thể bắt đầu với một vài mức như 100, 250, 500 hoặc 1.000 hàng tùy kích thước bản ghi và driver, rồi đo. Đây chỉ là các điểm thử, không phải khuyến nghị cố định.

### 6.1. Các yếu tố ảnh hưởng đến batch size

- Kích thước trung bình của mỗi hàng và số tham số.
- Số byte dữ liệu gửi trong một batch.
- Giới hạn packet/message của driver, proxy và database.
- Thời gian thực thi của mỗi câu lệnh.
- Số index, trigger và constraint cần cập nhật.
- Mức độ tranh chấp khóa.
- Khả năng ghi log và I/O của database.
- Bộ nhớ heap của JVM và driver.
- Số batch chạy đồng thời.
- Yêu cầu atomicity và thời gian rollback chấp nhận được.

Một batch 1.000 hàng có thể nhỏ với các hàng chỉ gồm vài số nguyên, nhưng rất lớn nếu mỗi hàng chứa nhiều JSON hoặc BLOB. Hãy cân nhắc giới hạn theo số hàng và số byte, không chỉ theo count.

### 6.2. Chọn batch size theo đo đạc

Thử một số mức tăng dần trên dữ liệu đại diện. Ghi nhận:

- Thời gian tổng của toàn bộ công việc.
- Thời gian mỗi executeBatch.
- Số batch và số hàng mỗi batch.
- Thông lượng hàng/giây.
- p50, p95 và p99 của thời gian batch.
- Heap usage và garbage collection.
- CPU, I/O và transaction log của database.
- Lock wait, deadlock và timeout.
- Số lượt trao đổi mạng nếu có thể quan sát.

Thông lượng có thể tăng khi tăng batch size rồi đạt điểm bão hòa. Sau điểm đó, batch lớn hơn có thể làm p99, lock duration hoặc memory pressure tăng mà throughput không cải thiện đáng kể. Chọn điểm cân bằng đáp ứng SLO và tải đồng thời.

## 7. Chia chunk và flush batch

Với tập dữ liệu lớn, ứng dụng thường thêm phần tử rồi thực thi batch khi đạt ngưỡng:

~~~java
int batchSize = 500;
int pending = 0;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Event event : events) {
        bindEvent(ps, event);
        ps.addBatch();
        pending++;

        if (pending == batchSize) {
            int[] counts = ps.executeBatch();
            verifyBatchCounts(counts, pending);
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        int[] counts = ps.executeBatch();
        verifyBatchCounts(counts, pending);
        ps.clearBatch();
    }
}
~~~

executeBatch thường tiêu thụ batch hiện tại, nhưng clearBatch giúp thể hiện rõ ý định xóa các lệnh đang chờ và tránh giữ trạng thái không cần thiết. Cần kiểm tra hành vi driver nếu có extension riêng.

Đếm số phần tử đã thêm giúp xử lý phần dư ở cuối. Nếu bỏ qua phần dư, số hàng cuối cùng nhỏ hơn batchSize sẽ không được thực thi.

Nếu batch chạy trong transaction, quyết định commit theo từng chunk hay sau toàn bộ dữ liệu là quyết định riêng. Flush batch không đồng nghĩa commit.

## 8. Ranh giới transaction: commit theo lô hay commit toàn bộ?

Có hai chiến lược phổ biến:

**Một transaction cho toàn bộ công việc:** mọi chunk được executeBatch trong cùng transaction và chỉ commit khi toàn bộ thành công. Nếu lỗi, rollback toàn bộ.

Ưu điểm:

- Atomicity ở cấp toàn bộ công việc.
- Không để lại các chunk đã commit một phần.
- Đơn giản hơn khi nghiệp vụ yêu cầu tất cả hoặc không gì cả.

Giới hạn:

- Transaction có thể rất dài.
- Lock và version dữ liệu có thể được giữ lâu.
- Transaction log/undo có thể tăng lớn.
- Rollback có thể tốn thời gian và tài nguyên.
- Tăng nguy cơ deadlock hoặc ảnh hưởng workload khác.

**Một transaction cho mỗi chunk:** sau khi một chunk thành công, commit chunk đó rồi tiếp tục chunk kế tiếp.

Ưu điểm:

- Giới hạn lượng công việc rollback.
- Giải phóng lock sớm hơn.
- Giảm kích thước transaction và log cần giữ cho một đơn vị.
- Dễ tiếp tục từ checkpoint nếu quy trình được thiết kế hỗ trợ.

Giới hạn:

- Toàn bộ công việc không còn atomic.
- Lỗi ở chunk sau không tự rollback các chunk đã commit.
- Cần checkpoint, khả năng chạy lại và xử lý trùng lặp.
- Báo cáo có thể quan sát dữ liệu đã nạp một phần.

Chọn ranh giới transaction theo hợp đồng nghiệp vụ. Nếu nhập một file phải hoàn toàn thành công hoặc thất bại, có thể cần một transaction lớn hoặc mô hình staging rồi publish nguyên tử. Nếu nạp dữ liệu theo batch có thể tiếp tục, commit từng chunk cùng checkpoint có thể phù hợp hơn.

## 9. Ví dụ commit theo từng chunk

~~~java
int batchSize = 500;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    connection.setAutoCommit(false);

    int pending = 0;

    for (Event event : events) {
        bindEvent(ps, event);
        ps.addBatch();
        pending++;

        if (pending == batchSize) {
            int[] counts = ps.executeBatch();
            verifyBatchCounts(counts, pending);
            connection.commit();
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        int[] counts = ps.executeBatch();
        verifyBatchCounts(counts, pending);
        connection.commit();
        ps.clearBatch();
    }
} catch (SQLException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
}
~~~

Mẫu này minh họa ranh giới commit theo chunk. Khi một chunk đã commit, rollback ở chunk sau không thể hoàn tác các chunk trước. Trong ứng dụng dùng pool, cần đặt autoCommit và cleanup trong cấu trúc quản lý connection an toàn, kể cả khi có exception.

Cũng cần tránh giữ một connection lâu trong khi ứng dụng đang chờ đọc file, gọi HTTP hoặc thực hiện công việc không liên quan đến database. Chuẩn bị dữ liệu ngoài transaction nếu có thể, sau đó mở transaction cho phần ghi cần thiết.

## 10. Kiểm tra update counts

executeBatch trả về mảng update counts, mỗi phần tử tương ứng với một lệnh trong batch theo quy tắc JDBC và driver. Các giá trị thường gặp:

- Số không âm: số hàng bị ảnh hưởng hoặc kết quả đếm do driver/database cung cấp.
- Statement.SUCCESS_NO_INFO: lệnh thành công nhưng driver không biết số hàng chính xác.
- Statement.EXECUTE_FAILED: lệnh thất bại trong batch khi driver tiếp tục xử lý các phần tử sau lỗi.

Không phải mọi driver trả về cùng mức chi tiết. Với batch được viết lại thành multi-row statement, số lượng update count và cách ánh xạ có thể phụ thuộc driver.

Ví dụ kiểm tra:

~~~java
static void verifyBatchCounts(int[] counts, int expected) throws SQLException {
    if (counts.length != expected) {
        throw new SQLException(
            "Unexpected batch result count: " + counts.length
        );
    }

    for (int i = 0; i < counts.length; i++) {
        int count = counts[i];

        if (count == Statement.EXECUTE_FAILED) {
            throw new SQLException("Batch item failed at index " + i);
        }

        if (count == Statement.SUCCESS_NO_INFO) {
            continue;
        }

        if (count < 0) {
            throw new SQLException("Unknown update count at index " + i);
        }
    }
}
~~~

Không giả định mọi INSERT luôn trả đúng 1 hoặc mọi UPDATE trả đúng 1. Một số driver trả SUCCESS_NO_INFO; một số thao tác có thể ảnh hưởng 0 hàng hoặc nhiều hàng. Hãy định nghĩa điều kiện thành công theo nghiệp vụ và khả năng của driver.

Nếu cần xác nhận số hàng được tạo, có thể đối chiếu bằng khóa nghiệp vụ hoặc truy vấn tổng hợp theo batch ID. Tránh chỉ tin vào số update count nếu driver không cung cấp số liệu chính xác.

## 11. Xử lý BatchUpdateException và lỗi một phần

Khi một phần tử trong batch thất bại, JDBC có thể ném BatchUpdateException. Exception này cung cấp update counts cho các lệnh đã được xử lý theo hành vi của driver.

Có hai kiểu hành vi thường gặp:

- Driver dừng tại lệnh lỗi và trả các kết quả trước đó.
- Driver tiếp tục thực thi một số lệnh còn lại và đánh dấu lỗi tương ứng.

Hành vi cụ thể phụ thuộc driver và database. Hãy đọc getUpdateCounts hoặc getLargeUpdateCounts, SQLException chain và thông tin lỗi gốc.

Ví dụ:

~~~java
try {
    int[] counts = ps.executeBatch();
    verifyBatchCounts(counts, expected);
} catch (BatchUpdateException ex) {
    int[] counts = ex.getUpdateCounts();

    logBatchFailure(counts, ex.getSQLState(), ex.getErrorCode());

    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }

    throw ex;
}
~~~

Nếu toàn bộ batch nằm trong một transaction chưa commit, rollback có thể đưa transaction về trạng thái trước batch theo khả năng của database. Nếu autoCommit hoặc driver đã commit một số thao tác, hoặc ứng dụng đã commit các chunk trước đó, rollback hiện tại không thể hoàn tác phần đã commit.

Không tự động retry toàn bộ batch mà không biết phần nào đã thành công. Retry có thể tạo bản ghi trùng hoặc trừ tồn kho hai lần. Cần thiết kế idempotency bằng khóa nghiệp vụ, unique constraint, import batch ID hoặc bảng checkpoint.

## 12. Savepoint và xử lý một phần

Nếu nghiệp vụ cho phép một chunk thất bại nhưng muốn giữ các thao tác trước đó trong cùng transaction, có thể cân nhắc Savepoint. Tuy nhiên, việc rollback đến savepoint, tiếp tục transaction và cách driver xử lý batch cần được kiểm thử với database cụ thể.

Ví dụ khái niệm:

~~~java
Savepoint beforeChunk = connection.setSavepoint();

try {
    int[] counts = ps.executeBatch();
    verifyBatchCounts(counts, expected);
} catch (BatchUpdateException ex) {
    connection.rollback(beforeChunk);
    recordRejectedChunk(ex);
}
~~~

Sau rollback đến savepoint, transaction vẫn có thể tiếp tục tùy hệ quản trị. Không phải mọi lỗi đều cho phép tiếp tục; một số database đánh dấu transaction failed cho đến khi rollback toàn bộ hoặc rollback đến savepoint hợp lệ.

Nếu cần cách ly từng bản ghi lỗi, một batch lớn có thể không phù hợp. Có thể chia nhỏ hơn, ghi dữ liệu vào staging table rồi xác thực, hoặc xử lý riêng các bản ghi lỗi sau khi xác định nhóm thất bại. Cách xử lý phải cân bằng khả năng chẩn đoán với chi phí round trip.

## 13. Driver có thể viết lại batch như thế nào?

JDBC định nghĩa API batch, nhưng tối ưu giao thức cụ thể là trách nhiệm của driver và hệ quản trị.

Một số khả năng:

- Gửi nhiều execution request trong một lần trao đổi.
- Dùng protocol pipelining hoặc cơ chế batch riêng.
- Viết lại nhiều INSERT cùng mẫu thành một multi-row INSERT.
- Dùng prepared statement và truyền nhiều bộ tham số.
- Thực thi tuần tự từng câu lệnh nhưng vẫn giảm một số chi phí ở phía client.
- Chia batch lớn thành nhiều nhóm nhỏ theo giới hạn giao thức.

Ví dụ, một số driver có tùy chọn cấu hình để viết lại INSERT batch. MySQL Connector/J có tùy chọn rewriteBatchedStatements; PostgreSQL JDBC có reWriteBatchedInserts. Tên, mặc định, điều kiện áp dụng và tác động khác nhau theo phiên bản driver. Không bật một tùy chọn chỉ vì tên nghe có vẻ tối ưu.

Cần kiểm tra:

- Driver có thực sự rewrite câu lệnh không?
- Có giới hạn số hàng hoặc kích thước statement không?
- Generated keys có được hỗ trợ đúng khi rewrite không?
- Update counts có thay đổi semantics không?
- Batch có bị chia nhỏ bên trong driver không?
- Server log hoặc network trace cho thấy bao nhiêu request?
- Câu lệnh có trigger, returning clause hoặc đặc điểm làm rewrite không áp dụng không?

## 14. Kiểm chứng số lượt gửi thực tế

Để biết batch có giảm round trip hay không, cần quan sát ở nhiều tầng.

**Ở ứng dụng:**

- Số lần gọi executeBatch.
- Số phần tử trong mỗi batch.
- Thời gian bind, executeBatch và commit.
- Số connection đang sử dụng.
- Thời gian chờ lấy connection từ pool.

**Ở driver và giao thức:**

- Driver trace hoặc logging phù hợp.
- Số request/response theo protocol nếu công cụ hỗ trợ.
- Kích thước thông điệp gửi.
- Số lần chia batch nội bộ.
- Hành vi rewrite hoặc pipelining.

**Ở database:**

- Số lần thực thi statement.
- Số parse/prepare nếu có thống kê.
- Số hàng insert/update.
- Thời gian CPU và elapsed.
- Log bytes, I/O và lock wait.
- Các wait event liên quan đến client/network.

Không lấy số lần executeBatch làm số round trip. Cũng không lấy số câu lệnh ghi trong SQL log làm số gói mạng. Một lần gửi có thể chứa nhiều statement; một batch có thể bị driver chia thành nhiều lượt gửi.

Nếu không có network tracing, hãy kết hợp driver diagnostics, database statement statistics và thời gian ứng dụng. Kết luận cần ghi rõ đó là số lần gọi API, số statement được server thực thi hay số lượt mạng được quan sát.

## 15. Batch size và độ trễ đuôi

Batch lớn thường tăng throughput đến một điểm, nhưng có thể làm thời gian hoàn tất một chunk dài hơn. Điều này ảnh hưởng p95/p99 và các request phải chờ cùng connection hoặc tài nguyên database.

Nếu batch được chạy đồng bộ trong request người dùng, batch lớn có thể làm request giữ connection lâu. Nếu chạy nền, batch quá lớn có thể làm các transaction khác chờ lock hoặc I/O.

Đo riêng:

- Thời gian một executeBatch.
- Thời gian commit.
- Thời gian toàn bộ import.
- Độ trễ request tương tác trong lúc import chạy.
- p95/p99 của các truy vấn khác.
- Lock wait và deadlock.
- Connection pool wait.

Không tối ưu throughput import bằng cách làm suy giảm đáng kể độ trễ của workload tương tác. Có thể cần giới hạn tốc độ nạp, chạy ngoài giờ cao điểm, dùng queue hoặc phân bổ connection riêng có giới hạn.

## 16. Bulk loading có thể phù hợp hơn JDBC batch

JDBC batch phù hợp với nhiều thao tác ứng dụng cần transaction và bind tham số. Nhưng khi nạp hàng chục triệu hàng, cơ chế bulk load chuyên biệt có thể hiệu quả hơn.

Ví dụ tùy hệ quản trị:

- PostgreSQL COPY.
- SQL Server BULK INSERT hoặc bcp.
- Oracle SQL*Loader hoặc direct-path insert.
- MySQL LOAD DATA.

Bulk loading có thể giảm overhead giao thức và tối ưu đường ghi. Đổi lại, nó có thể có semantics về constraint, trigger, logging, transaction và error handling khác với INSERT thông thường. Không chuyển sang bulk load nếu chưa kiểm tra các yêu cầu toàn vẹn, quyền truy cập, khả năng rollback và cách xử lý bản ghi lỗi.

Hãy benchmark JDBC batch với bulk loading trên cùng dữ liệu, cùng index/constraint và cùng yêu cầu transaction. So sánh thời gian tổng, throughput, log, I/O và khả năng phục hồi.

## 17. Generated keys và thứ tự ánh xạ

Một số batch insert cần lấy khóa được database sinh tự động. JDBC hỗ trợ yêu cầu generated keys qua prepareStatement với RETURN_GENERATED_KEYS hoặc API tương ứng, nhưng khả năng trả khóa cho batch và thứ tự ánh xạ phụ thuộc driver.

Không giả định:

- Mọi driver đều trả generated keys cho batch.
- Số khóa trả về luôn bằng số phần tử đã gửi.
- Thứ tự khóa luôn tương ứng thứ tự addBatch.
- Rewrite multi-row INSERT vẫn giữ cùng hành vi generated keys.

Nếu cần ánh xạ chắc chắn, hãy dùng khóa do ứng dụng sinh trước khi insert, một import correlation ID, hoặc cơ chế RETURNING/OUTPUT đặc thù hệ quản trị đã được kiểm thử. Nếu phải đọc generated keys, xác nhận driver và phiên bản hỗ trợ đúng trường hợp batch đang dùng.

## 18. Kiểu dữ liệu, NULL và tham số trong batch

Mỗi bộ tham số phải được bind đúng kiểu. Một lỗi kiểu ở một phần tử có thể làm hỏng batch hoặc khiến driver chuyển đổi dữ liệu không mong muốn.

Ví dụ:

~~~java
ps.setBigDecimal(1, item.amount());

if (item.note() == null) {
    ps.setNull(2, Types.VARCHAR);
} else {
    ps.setString(2, item.note());
}
~~~

Không giữ lại giá trị tham số của hàng trước khi thuộc tính hàng mới là NULL. Nếu bỏ qua setNull, driver có thể dùng lại giá trị đã bind trước đó cho cùng vị trí tham số, tùy cách code bind.

Cần kiểm tra:

- Kiểu số và precision/scale.
- Timestamp và timezone.
- Chuỗi và độ dài cột.
- NULL và SQL type tương ứng.
- Giá trị binary/LOB.
- Character encoding.
- Giá trị vượt giới hạn cột hoặc constraint.

Batch làm tăng số lượng dữ liệu được gửi cùng lúc, nên một lỗi dữ liệu có thể khiến một phần lớn lô thất bại. Validate dữ liệu ở ứng dụng có thể giảm lỗi rõ ràng, nhưng constraint trong database vẫn là hàng rào toàn vẹn cuối cùng.

## 19. Connection pool và quản lý trạng thái transaction

Batch thường chạy lâu hơn một câu lệnh đơn. Cần giữ connection ổn định trong toàn bộ nhóm thao tác, đặc biệt khi bảng tạm, transaction hoặc session setting được dùng.

Nguyên tắc:

- Lấy một connection cho một đơn vị batch/transaction.
- Không trả connection về pool trước khi commit hoặc rollback hoàn tất.
- Khôi phục autoCommit và các session setting đã thay đổi.
- Đóng PreparedStatement và ResultSet bằng try-with-resources.
- Không chia các bước cùng transaction qua nhiều connection.
- Giới hạn số worker ghi đồng thời để tránh cạn pool.
- Xử lý exception khi commit, rollback hoặc reset connection.

Nếu connection bị mất trong lúc commit, ứng dụng có thể không biết transaction đã commit hay chưa. Đây là tình huống kết quả không chắc chắn. Retry an toàn cần idempotency key hoặc cơ chế đối soát trạng thái ở database, không chỉ dựa trên việc gửi lại batch.

## 20. Ví dụ hoàn chỉnh: nạp sự kiện theo chunk có checkpoint

Giả sử một job nhập dữ liệu sự kiện từ nguồn ngoài. Mỗi sự kiện có event_id duy nhất. Job ghi 500 hàng mỗi chunk và lưu checkpoint sau khi commit thành công.

Mẫu bảng:

~~~sql
CREATE TABLE imported_events (
    event_id BIGINT PRIMARY KEY,
    import_job_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    occurred_at TIMESTAMP NOT NULL
);
~~~

Bảng checkpoint:

~~~sql
CREATE TABLE import_checkpoint (
    import_job_id VARCHAR(64) PRIMARY KEY,
    last_event_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Trong mỗi chunk, ứng dụng thực hiện theo cùng một transaction:

1. Insert các sự kiện bằng PreparedStatement.addBatch.
2. Gọi executeBatch.
3. Kiểm tra update counts hoặc xử lý SUCCESS_NO_INFO.
4. Cập nhật checkpoint trong cùng transaction.
5. Commit.
6. Chỉ sau commit mới đánh dấu chunk hoàn tất ở phía điều phối.

Nếu event_id đã tồn tại, unique constraint sẽ phát hiện trùng. Job cần quy định rõ: bỏ qua bản ghi đã nhập, cập nhật bản ghi, hay xem đó là lỗi. Có thể dùng câu lệnh upsert theo hệ quản trị hoặc xử lý lỗi có kiểm soát. Không nuốt mọi duplicate exception vì có thể che giấu dữ liệu xung đột thực sự.

Checkpoint phải được cập nhật trong cùng transaction với dữ liệu chunk. Nếu cập nhật checkpoint sau khi commit dữ liệu bằng một transaction khác, lỗi giữa hai bước có thể khiến job đọc checkpoint cũ và gửi lại chunk. Idempotency vẫn cần thiết để bảo vệ retry.

## 21. Quy trình benchmark JDBC batch

Để chọn batch size và xác nhận lợi ích, hãy thực hiện thử nghiệm có kiểm soát:

1. **Tạo baseline:** đo insert từng hàng với cùng dữ liệu, index, constraint và transaction semantics.
2. **Giữ ổn định môi trường:** dùng cùng phiên bản JVM, JDBC driver, database, network và dữ liệu.
3. **Thử nhiều batch size:** tăng dần theo số hàng và kích thước byte.
4. **Thử ranh giới transaction:** một transaction toàn bộ và commit theo chunk nếu nghiệp vụ cho phép.
5. **Kiểm tra driver option:** bật/tắt rewrite hoặc batching option theo tài liệu.
6. **Đo số lượt gửi:** kết hợp application metrics, driver trace và database statistics.
7. **Đo hiệu năng:** throughput, p50/p95/p99, CPU, I/O, log bytes, lock wait và pool wait.
8. **Đo bộ nhớ:** heap, allocation rate, garbage collection và kích thước batch giữ trong driver.
9. **Thử lỗi:** duplicate key, timeout, deadlock, network disconnect và lỗi giữa chunk.
10. **Đối chiếu dữ liệu:** số hàng, khóa, checksum hoặc tổng hợp theo batch ID.
11. **Thử concurrency:** nhiều writer cùng chạy và workload đọc/ghi tương tác.
12. **Chọn điểm cân bằng:** ưu tiên cấu hình đáp ứng SLO, tính toàn vẹn và khả năng phục hồi.

Đo cả thời gian tạo batch, bind tham số, executeBatch và commit. Nếu chỉ đo executeBatch, chi phí parse dữ liệu nguồn, chuyển kiểu hoặc commit có thể bị bỏ sót.

## 22. Các sai lầm thường gặp

- **Cho rằng một executeBatch tương đương một round trip.** Driver có thể chia hoặc thực thi theo nhiều request.
- **Cho rằng batch tự tạo một transaction nguyên tử.** Transaction phụ thuộc autoCommit và ranh giới commit thực tế.
- **Chọn batch size càng lớn càng tốt.** Batch lớn làm tăng memory, lock duration, log và phạm vi rollback.
- **Giữ hàng triệu bộ tham số trong một batch.** Có thể gây áp lực heap và GC.
- **Commit mỗi hàng.** Làm tăng chi phí commit và round trip; chỉ phù hợp khi yêu cầu nghiệp vụ buộc như vậy.
- **Commit chunk mà không có checkpoint/idempotency.** Retry có thể tạo trùng hoặc xử lý lặp.
- **Bỏ qua update counts.** executeBatch không ném exception không có nghĩa mọi hàng đều ảnh hưởng đúng số lượng mong muốn.
- **Retry toàn bộ sau BatchUpdateException.** Một phần có thể đã thực thi hoặc commit.
- **Tin generated keys luôn đúng thứ tự.** Hành vi phụ thuộc driver và cách rewrite.
- **Bật driver rewrite trong production mà không kiểm thử.** Update counts, generated keys và giới hạn statement có thể thay đổi.
- **Đo số lần gọi API thay cho round trip.** Hai số liệu không tương đương.
- **Tối ưu import mà bỏ qua workload tương tác.** Batch có thể chiếm connection, CPU, log và I/O của hệ thống.
- **Không kiểm tra trạng thái connection sau lỗi.** Connection chưa rollback hoặc chưa reset có thể gây lỗi cho request tiếp theo.

## 23. Checklist thiết kế JDBC batch

- [ ] Đã xác định thao tác có cùng mẫu SQL và phù hợp để batch.
- [ ] Đã dùng PreparedStatement và bind tham số đúng kiểu.
- [ ] Đã xác định batch size theo số hàng và kích thước byte.
- [ ] Đã flush phần dư ở cuối chunk.
- [ ] Đã phân biệt executeBatch với commit và network round trip.
- [ ] Đã xác định driver có rewrite/pipeline hay chia batch nội bộ không.
- [ ] Đã chọn ranh giới transaction theo yêu cầu atomicity.
- [ ] Đã xác định xử lý lỗi, update counts và BatchUpdateException.
- [ ] Đã thiết kế idempotency/checkpoint cho chunk có thể retry.
- [ ] Đã kiểm tra generated keys nếu nghiệp vụ cần.
- [ ] Đã quản lý connection pool, autoCommit, rollback và cleanup.
- [ ] Đã kiểm tra NULL, precision/scale, timestamp và dữ liệu vượt giới hạn.
- [ ] Đã đo round trip bằng bằng chứng từ driver/protocol/database.
- [ ] Đã đo throughput, p95/p99, CPU, I/O, log, lock và heap.
- [ ] Đã kiểm tra ảnh hưởng lên truy vấn khác dưới concurrency.
- [ ] Đã đối chiếu số hàng và dữ liệu sau khi nạp.

## 24. Nguyên tắc cần ghi nhớ

JDBC batch gom nhiều bộ tham số hoặc thao tác cùng mẫu để driver có cơ hội giảm overhead gửi lệnh và xử lý. Hiệu quả phụ thuộc driver, giao thức, database, kích thước hàng, index, constraint, transaction và tải đồng thời. Một lần gọi executeBatch không bảo đảm một network round trip hoặc một transaction nguyên tử.

Hãy chọn batch size bằng benchmark, quản lý transaction theo yêu cầu atomicity, kiểm tra update counts và xử lý BatchUpdateException có tính đến phần đã thực thi. Với batch commit theo chunk, cần checkpoint và idempotency để retry an toàn. Cuối cùng, xác nhận số lượt gửi bằng số liệu ở tầng ứng dụng, driver hoặc protocol và database; đo toàn bộ quy trình cùng tác động lên p95/p99, bộ nhớ, log, lock và I/O.
