# Kích thước lô, tần suất COMMIT và thời gian chiếm tài nguyên

Khi xử lý nhiều bản ghi, hiệu năng đồng thời phụ thuộc đáng kể vào số thao tác được gửi cùng một lô, số thao tác nằm trong một transaction và thời điểm transaction kết thúc. Gộp quá ít thao tác làm tăng round trip và chi phí commit. Gộp quá nhiều thao tác làm transaction kéo dài, giữ khóa lâu, chiếm connection, tăng lượng log và khiến rollback hoặc phục hồi tốn kém.

Thiết kế tốt cần tách ba khái niệm:

- **Batch size:** số câu lệnh hoặc bản ghi được gửi/thi hành cùng một đợt.
- **Transaction size:** số thao tác được bảo vệ bởi cùng một ranh giới BEGIN/COMMIT.
- **Commit frequency:** số lần commit trong một lượng công việc nhất định, thường được biểu diễn bằng số bản ghi hoặc thời gian giữa hai lần commit.

Ba giá trị này liên quan nhưng không bắt buộc bằng nhau. Một ứng dụng có thể gửi batch 200 bản ghi mỗi lần, thực hiện năm batch trong một transaction rồi mới commit 1.000 bản ghi. Hiểu đúng sự khác biệt này giúp cân bằng throughput, độ trễ, mức tranh chấp và khả năng phục hồi.

## 1. Batch size và transaction size giải quyết hai vấn đề khác nhau

Giả sử một job cần nhập 10.000 dòng dữ liệu.

Có thể gửi từng dòng riêng lẻ:

~~~text
INSERT row 1
INSERT row 2
INSERT row 3
...
INSERT row 10000
~~~

Cách này tạo nhiều lần gọi database, nhiều lần xử lý protocol và có thể nhiều round trip. JDBC batch cho phép gom nhiều câu lệnh tương tự trước khi gửi hoặc thực thi:

~~~java
for (ImportRow row : rows) {
    statement.setLong(1, row.id());
    statement.setString(2, row.name());
    statement.addBatch();
}
statement.executeBatch();
~~~

executeBatch() không tự đồng nghĩa với COMMIT. Nếu connection đang ở chế độ transaction thủ công, các câu lệnh trong batch vẫn thuộc transaction hiện tại cho đến khi commit hoặc rollback.

Ví dụ một transaction có thể chạy:

~~~text
BEGIN
  executeBatch 200 rows
  executeBatch 200 rows
  executeBatch 200 rows
  executeBatch 200 rows
  executeBatch 200 rows
COMMIT
~~~

Trong ví dụ này:

- Batch size là 200.
- Transaction size là 1.000 dòng.
- Commit frequency là một lần sau mỗi 1.000 dòng.

Nếu thay đổi batch size thành 100 mà vẫn commit mỗi 1.000 dòng, transaction vẫn có cùng quy mô nhưng có nhiều lần executeBatch() hơn. Nếu giữ batch size 200 nhưng commit mỗi 400 dòng, mỗi transaction có hai batch.

Đừng gọi mọi hình thức gom dữ liệu là “batch transaction”. Hãy ghi rõ số dòng mỗi lần gửi, số dòng mỗi transaction và tần suất commit.

## 2. Vì sao batch quá nhỏ làm giảm throughput?

Mỗi lần gửi câu lệnh có thể tạo chi phí cố định:

- Truyền request và nhận response qua network.
- Parse hoặc chuẩn bị câu lệnh, tùy driver và prepared statement.
- Chuyển đổi tham số và tạo object trong ứng dụng.
- Điều phối câu lệnh, kiểm tra constraint, index và trigger.
- Chi phí transaction/commit nếu ứng dụng commit sau từng câu lệnh.

Nếu gửi từng bản ghi riêng và commit từng lần, hệ thống có thể trả nhiều thời gian cho protocol và commit hơn là xử lý dữ liệu.

Batch giúp giảm số lần gọi và tận dụng prepared statement. Một số driver còn hỗ trợ rewrite batch thành một câu INSERT nhiều giá trị hoặc tối ưu protocol. Hành vi này phụ thuộc driver, cấu hình và hệ quản trị; addBatch() không bảo đảm mọi driver sẽ biến các lệnh thành một round trip duy nhất.

Ví dụ:

~~~sql
INSERT INTO event_log (event_id, event_type)
VALUES
    (101, 'CREATED'),
    (102, 'UPDATED'),
    (103, 'CANCELLED');
~~~

Một câu INSERT nhiều hàng có thể giảm overhead so với ba câu INSERT riêng. Nhưng câu lệnh lớn cũng có giới hạn về số tham số, kích thước packet, bộ nhớ và thời gian thực thi. Cần chọn kích thước phù hợp với driver và database.

## 3. Vì sao batch hoặc transaction quá lớn làm tăng tranh chấp?

Khi một transaction cập nhật nhiều hàng, nó có thể giữ nhiều khóa cho đến khi kết thúc. Transaction khác cần các hàng hoặc phạm vi liên quan phải chờ.

Ví dụ:

~~~sql
BEGIN;

UPDATE account
SET status = 'REVIEW'
WHERE customer_id = 77;

-- Xử lý thêm hàng nghìn bản ghi và tính toán.
-- Transaction vẫn chưa commit.

COMMIT;
~~~

Nếu UPDATE tác động hàng nghìn tài khoản, transaction có thể giữ nhiều khóa ghi trong suốt phần công việc còn lại. Một transaction nhỏ khác chỉ muốn cập nhật một tài khoản trong tập đó vẫn có thể phải chờ.

Transaction dài có thể gây:

- Lock wait lâu hơn và giảm số transaction có thể tiến triển đồng thời.
- Tăng xác suất deadlock khi nhiều transaction cùng giữ các tập khóa lớn.
- Tăng nguy cơ lock escalation ở những hệ quản trị có cơ chế nâng cấp khóa.
- Giữ connection từ pool lâu, làm các request khác thiếu connection.
- Tăng lượng dữ liệu phải rollback khi gặp lỗi.
- Giữ phiên bản cũ hoặc undo cần thiết lâu hơn trong hệ quản trị MVCC.
- Tạo lượng log lớn và làm phục hồi sau crash hoặc replication catch-up nặng hơn.

Không phải mọi khóa đều tồn tại đến COMMIT. Một số khóa đọc hoặc khóa nội bộ chỉ tồn tại trong thời gian câu lệnh; nhưng các khóa ghi và nhiều khóa bảo vệ transaction thường được giữ đến khi transaction kết thúc. Cần xem loại khóa và engine cụ thể.

Ngoài ra, transaction dài không đồng nghĩa mọi tài nguyên CPU hoặc latch đều bị giữ suốt thời gian đó. Latch thường bảo vệ cấu trúc bộ nhớ trong thời gian ngắn. Hãy phân biệt khóa transaction, latch, connection, phiên bản dữ liệu và log khi phân tích tài nguyên.

## 4. Tần suất COMMIT tạo ra sự đánh đổi

Commit thường yêu cầu database hoàn tất các công việc bảo đảm tính bền vững theo cấu hình. Với database ghi log, commit có thể phải chờ log record được flush theo durability policy. Một số hệ thống dùng group commit để nhiều transaction chia sẻ một lần flush; vì vậy không nên giả định mỗi COMMIT luôn gây một lần ghi vật lý độc lập.

### 4.1. Commit quá thường xuyên

Nếu commit sau mỗi dòng:

- Tăng số lần commit và chi phí điều phối.
- Có thể tăng số lần chờ log flush hoặc xác nhận commit.
- Mỗi dòng trở thành một đơn vị nguyên tử riêng, nên job có thể để lại kết quả một phần.
- Nếu dòng sau thất bại, các dòng đã commit trước đó không tự rollback.

Ưu điểm là transaction ngắn, khóa thường được giải phóng sớm và lượng công việc phải rollback trong một transaction nhỏ. Đây có thể là lựa chọn đúng nếu mỗi dòng là một nghiệp vụ độc lập và chấp nhận xử lý một phần.

### 4.2. Commit quá thưa

Nếu commit sau hàng trăm nghìn hoặc hàng triệu dòng:

- Transaction giữ tài nguyên lâu.
- Log/undo hoặc row version cần giữ có thể tăng.
- Rollback một lỗi ở cuối có thể phải hoàn tác lượng công việc rất lớn.
- Một transaction thất bại có thể làm lãng phí thời gian xử lý trước đó.
- Có thể làm tăng thời gian phục hồi và gây ảnh hưởng đến các transaction khác.

Ưu điểm là giảm số lần commit trên mỗi bản ghi và giữ tính nguyên tử cho một khối công việc lớn. Nhưng chỉ nên dùng khi ranh giới nghiệp vụ thực sự yêu cầu tất cả hoặc không gì cả và hệ thống có đủ tài nguyên.

### 4.3. Commit theo chunk

Một cách cân bằng là chia job thành các chunk độc lập:

~~~text
Chunk 1: 1.000 rows -> COMMIT
Chunk 2: 1.000 rows -> COMMIT
Chunk 3: 1.000 rows -> COMMIT
...
~~~

Cách này giới hạn thời gian giữ khóa và phạm vi rollback. Nếu chunk 4 thất bại, ba chunk đã commit vẫn tồn tại. Vì vậy, ứng dụng cần có checkpoint và khả năng chạy lại an toàn.

Không được đổi từ một transaction toàn bộ sang commit theo chunk nếu nghiệp vụ yêu cầu toàn bộ 10.000 dòng phải xuất hiện nguyên tử. Việc chia transaction làm thay đổi ngữ nghĩa nhất quán và khả năng nhìn thấy dữ liệu trung gian.

## 5. Ví dụ so sánh ba chiến lược

Giả sử job nhập 10.000 dòng:

| Chiến lược | Batch size | Transaction size | Số lần commit | Đặc điểm |
|---|---:|---:|---:|---|
| Từng dòng | 1 | 1 | 10.000 | Đơn giản, transaction rất ngắn, overhead commit cao |
| Một transaction lớn | 500 | 10.000 | 1 | Ít commit, nhưng giữ tài nguyên lâu và rollback lớn |
| Commit theo chunk | 250 | 1.000 | 10 | Giới hạn quy mô transaction, có checkpoint và xử lý partial progress |

Các con số chỉ là ví dụ khởi đầu, không phải giá trị tối ưu cho mọi database. Batch 250 có thể quá nhỏ với driver này nhưng quá lớn với driver khác. Transaction 1.000 dòng có thể phù hợp với bảng append-only nhưng gây tranh chấp cao với một bảng có nhiều hàng nóng và trigger.

Hãy đo trên workload gần production thay vì chọn một con số theo cảm tính.

## 6. Mẫu JDBC: gửi batch nhỏ, commit theo chunk lớn hơn

Ví dụ sau nhập dữ liệu theo chunk 1.000 dòng, trong đó mỗi lần executeBatch() gửi tối đa 200 dòng. Cả năm batch nằm trong cùng một transaction.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public final class BatchImporter {
    private static final int BATCH_SIZE = 200;
    private static final int CHUNK_SIZE = 1_000;

    public void importRows(Connection connection, List<ImportRow> rows)
            throws SQLException {

        connection.setAutoCommit(false);

        String sql = """
            INSERT INTO event_log (event_id, event_type)
            VALUES (?, ?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            int inChunk = 0;

            for (ImportRow row : rows) {
                statement.setLong(1, row.id());
                statement.setString(2, row.type());
                statement.addBatch();

                inChunk++;

                if (inChunk % BATCH_SIZE == 0) {
                    statement.executeBatch();
                }

                if (inChunk == CHUNK_SIZE) {
                    if (inChunk % BATCH_SIZE != 0) {
                        statement.executeBatch();
                    }

                    connection.commit();
                    inChunk = 0;
                }
            }

            if (inChunk > 0) {
                if (inChunk % BATCH_SIZE != 0) {
                    statement.executeBatch();
                }
                connection.commit();
            }
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        }
    }
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng thật, cần xác định ai sở hữu connection và transaction, reset autoCommit trước khi trả connection về pool, và xử lý đúng ngoại lệ từ cả executeBatch() lẫn commit().

Điểm cần chú ý:

- executeBatch() gửi/thi hành các lệnh đang chờ nhưng không commit transaction.
- Mỗi chunk kết thúc bằng commit().
- Chunk cuối có thể nhỏ hơn CHUNK_SIZE.
- Nếu một batch trong chunk thất bại, rollback chunk hiện tại theo chính sách all-or-nothing.
- Các chunk đã commit trước đó vẫn tồn tại.

Nếu cần một transaction duy nhất cho toàn bộ danh sách, hãy chuyển commit() ra sau vòng lặp. Khi đó transaction size bằng toàn bộ số dòng, dù vẫn có thể gọi executeBatch() nhiều lần.

## 7. Xử lý lỗi trong batch và kết quả cập nhật từng phần

JDBC có thể ném BatchUpdateException khi một batch thất bại. getUpdateCounts() cung cấp thông tin về các lệnh driver báo đã thực thi hoặc trạng thái không xác định theo quy ước driver.

Không nên giả định mọi driver dừng batch ở cùng vị trí hoặc trả cùng một dạng update count. Một số driver có thể tiếp tục các lệnh còn lại; một số có thể dừng khi gặp lỗi. Hãy đọc tài liệu driver và kiểm tra kết quả thực tế.

Nếu yêu cầu là chunk nguyên tử:

1. Bắt lỗi từ executeBatch().
2. Rollback toàn bộ transaction chunk hiện tại.
3. Ghi nhận chunk và nguyên nhân lỗi.
4. Không đánh dấu checkpoint chunk là hoàn tất.
5. Chỉ retry khi lỗi được phân loại là tạm thời và thao tác có thể lặp an toàn.

Nếu mỗi dòng là nghiệp vụ độc lập và cho phép thành công một phần, có thể dùng savepoint hoặc tách từng nhóm thành transaction riêng. Khi đó phải lưu kết quả thành công/thất bại theo từng bản ghi và định nghĩa cách xử lý các dòng phụ thuộc nhau.

Đừng dùng getUpdateCounts() làm bằng chứng rằng dữ liệu đã commit. Batch execution và transaction commit là hai sự kiện khác nhau.

## 8. Checkpoint để tiếp tục job sau khi commit theo chunk

Commit theo chunk giúp job phục hồi tốt hơn, nhưng cần biết chunk nào đã hoàn tất. Một checkpoint có thể lưu job ID và khóa cuối cùng đã xử lý:

~~~sql
CREATE TABLE import_progress (
    job_id       BIGINT PRIMARY KEY,
    last_item_id BIGINT NOT NULL,
    updated_at   TIMESTAMP NOT NULL
);
~~~

Trong cùng transaction với chunk, hãy:

1. Ghi các bản ghi của chunk.
2. Cập nhật last_item_id thành khóa cuối cùng đã xử lý.
3. Commit cả dữ liệu và checkpoint.

Nếu dữ liệu đã commit nhưng checkpoint chưa commit, job có thể chạy lại chunk và tạo dữ liệu trùng. Nếu checkpoint commit trước dữ liệu, job có thể bỏ qua các bản ghi chưa được lưu. Vì vậy, hai thay đổi phải nằm trong cùng transaction database.

Ví dụ luồng:

~~~sql
BEGIN;

-- Ghi dữ liệu của chunk hiện tại.
INSERT INTO event_log (event_id, event_type)
VALUES
    (1001, 'CREATED'),
    (1002, 'UPDATED');

-- Checkpoint phải được ghi cùng transaction.
UPDATE import_progress
SET last_item_id = 1002,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = 55;

COMMIT;
~~~

Khi tiếp tục, lấy các bản ghi có khóa lớn hơn last_item_id theo thứ tự ổn định. Keyset pagination thường phù hợp hơn OFFSET lớn vì dữ liệu có thể được thêm/xóa trong khi job chạy.

Nếu nguồn dữ liệu có thể thay đổi trong lúc import, cần xác định snapshot hoặc watermark của nguồn. Chỉ lưu khóa cuối cùng không đủ để bảo đảm không bỏ sót các bản ghi được thêm muộn với khóa nhỏ hơn.

## 9. Dùng khóa idempotent để chạy lại chunk an toàn

Checkpoint giúp biết vị trí tiếp tục, còn idempotency bảo vệ trường hợp chunk bị gửi lại. Có thể dùng unique key cho từng bản ghi nguồn hoặc cho tổ hợp job ID và source ID.

Ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_import_job_source
ON imported_event (job_id, source_event_id);
~~~

Khi retry chunk, database có thể từ chối các bản ghi đã được nhập trước đó hoặc dùng cú pháp upsert phù hợp. Cần xác định rõ duplicate có nghĩa là:

- Bản ghi đã được xử lý thành công trước đó.
- Bản ghi trùng do dữ liệu nguồn.
- Xung đột dữ liệu cần điều tra.

Không nên dùng ON CONFLICT DO NOTHING hoặc INSERT IGNORE một cách mù quáng nếu nó có thể che giấu một payload khác cho cùng source ID. Có thể lưu fingerprint để xác nhận nội dung lần chạy lại giống dữ liệu đã ghi.

Nếu chunk tạo nhiều loại dữ liệu liên quan, tất cả thay đổi và checkpoint cần cùng transaction. Một unique key đơn lẻ không tự bảo vệ các bảng liên quan khỏi trạng thái nửa hoàn tất.

## 10. Thời gian chiếm tài nguyên không chỉ phụ thuộc số dòng

Hai transaction cùng cập nhật 1.000 hàng vẫn có thể có thời gian giữ tài nguyên rất khác nhau.

Các yếu tố ảnh hưởng:

- **Index:** thiếu index phù hợp có thể khiến UPDATE quét và khóa phạm vi rộng hơn.
- **Hot rows:** nhiều transaction cùng cập nhật một hàng summary sẽ phải chờ nhau.
- **Trigger:** mỗi hàng có thể kích hoạt thêm SELECT/INSERT/UPDATE, làm tăng tập đọc/ghi.
- **Foreign key và constraint:** việc kiểm tra tham chiếu hoặc tính hợp lệ có thể cần thêm truy cập.
- **Thứ tự cập nhật:** hai transaction khóa các bảng hoặc hàng theo thứ tự khác nhau có thể tạo deadlock.
- **Network và application work:** gọi dịch vụ ngoài, xử lý file hoặc tính toán trong khi transaction mở kéo dài thời gian giữ tài nguyên.
- **Log throughput:** transaction ghi nhiều dữ liệu có thể chờ log flush hoặc chịu giới hạn I/O.
- **Connection pool:** transaction dài giữ connection, khiến request khác phải chờ lấy connection.
- **MVCC cleanup:** transaction đọc lâu có thể giữ snapshot cũ, làm một số phiên bản dữ liệu chưa thể được dọn.

Hãy đo cả thời gian từ lúc transaction bắt đầu đến commit và thời gian thực tế giữ khóa. Chúng liên quan nhưng không hoàn toàn giống nhau. Ví dụ, một transaction có thể mở trước khi đọc dữ liệu, nhưng khóa ghi chỉ xuất hiện ở giữa transaction.

## 11. MVCC, undo và log khi transaction kéo dài

Trong hệ quản trị dùng MVCC, một transaction đọc snapshot cũ có thể cần các phiên bản dữ liệu trước đó để tiếp tục nhìn thấy trạng thái nhất quán.

Transaction kéo dài có thể khiến hệ thống phải giữ lại các phiên bản cũ lâu hơn:

- PostgreSQL có thể chưa vacuum loại bỏ các tuple version mà snapshot cũ còn cần.
- InnoDB có thể phải giữ undo history để phục vụ consistent read của transaction còn hoạt động.
- SQL Server row versioning sử dụng version store; transaction đọc lâu có thể kéo dài thời gian cần giữ row versions.
- Oracle dùng undo để tái tạo consistent read; workload đọc lâu có thể tăng áp lực lên undo retention và dung lượng undo.

Cơ chế và triệu chứng khác nhau theo sản phẩm. Nhưng nguyên tắc chung là transaction/snapshot càng kéo dài, thời gian hệ thống phải duy trì lịch sử dữ liệu có thể càng dài.

Một job chỉ đọc lâu cũng có thể gây áp lực MVCC, dù nó không giữ nhiều khóa ghi. Do đó, không chỉ đo số UPDATE hoặc số khóa; hãy quan sát vacuum/undo/version store và tuổi transaction.

## 12. Tác động đến replication và phục hồi

Transaction lớn thường tạo ra lượng log lớn. Tùy hệ thống, log có thể là WAL, redo log hoặc transaction log. Replica phải nhận và áp dụng các thay đổi này theo cơ chế replication tương ứng.

Transaction lớn có thể:

- Tạo burst log lớn.
- Làm tăng thời gian replica apply một transaction lớn.
- Làm tăng replication lag.
- Tăng thời gian rollback hoặc recovery nếu transaction bị hủy hoặc database crash.
- Tạo áp lực I/O và dung lượng log.

Commit thường xuyên hơn có thể làm các phần log được xác nhận và replica tiến triển theo từng đơn vị nhỏ hơn, nhưng lại tăng overhead commit. Tác động thực tế phụ thuộc replication mode, group commit, log flush policy và khả năng song song hóa apply của engine.

Không nên chia transaction chỉ vì muốn giảm replication lag nếu điều đó làm mất tính nguyên tử nghiệp vụ. Hãy đo log bytes, commit latency, replica lag và thời gian apply trước khi thay đổi transaction boundary.

## 13. Chunking có làm thay đổi tính đúng đắn nghiệp vụ?

Có. Đây là điều phải quyết định trước khi tối ưu.

Giả sử một lần import cập nhật 10.000 tài khoản. Nếu commit mỗi 1.000 tài khoản, các transaction khác có thể nhìn thấy 1.000 tài khoản đầu đã cập nhật trong khi 9.000 tài khoản còn lại chưa cập nhật.

Nếu nghiệp vụ yêu cầu tất cả tài khoản đổi trạng thái cùng lúc, chunk commit không đáp ứng yêu cầu đó.

Có một số lựa chọn:

- **Một transaction lớn:** phù hợp khi toàn bộ thay đổi phải nguyên tử và workload nằm trong giới hạn tài nguyên.
- **Chunk độc lập:** phù hợp khi từng chunk là một đơn vị nghiệp vụ có thể commit riêng.
- **Staging rồi publish:** nhập và kiểm tra dữ liệu trong bảng staging theo chunk, sau đó chuyển trạng thái/publish bằng một thao tác nguyên tử nhỏ nếu schema và kiến trúc hỗ trợ.
- **Trạng thái job:** công bố tiến độ rõ ràng và chỉ đánh dấu job hoàn tất sau khi mọi chunk thành công.
- **Compensation:** nếu nghiệp vụ cho phép nhiều chunk commit riêng nhưng cần hoàn tác toàn bộ về mặt nghiệp vụ, thiết kế hành động bù trừ có idempotency và audit.

Không nên nói “batch nhỏ luôn an toàn hơn”. Batch nhỏ có thể làm tăng số lần commit và tạo trạng thái trung gian mà nghiệp vụ không cho phép.

## 14. Thứ tự khóa ổn định khi xử lý nhiều hàng

Khi transaction cập nhật nhiều tài khoản hoặc SKU, hãy xử lý theo một thứ tự nhất quán, chẳng hạn theo primary key tăng dần.

Ví dụ T1 cập nhật account 10 rồi 20, trong khi T2 cập nhật account 20 rồi 10. Hai transaction có thể tạo chu trình chờ.

~~~text
T1: khóa account 10 -> chờ account 20
T2: khóa account 20 -> chờ account 10
~~~

Sắp xếp danh sách khóa trước khi chạy batch giúp giảm nguy cơ deadlock do đảo thứ tự. Nếu nhiều bảng tham gia, thống nhất thứ tự bảng rồi đến thứ tự khóa trong từng bảng.

Điều này không loại bỏ mọi deadlock. Trigger, foreign key, index và các luồng ghi khác có thể yêu cầu thêm khóa. Ứng dụng vẫn cần nhận diện deadlock và retry toàn bộ transaction trong một transaction mới khi nghiệp vụ cho phép.

## 15. Cách chọn batch size và commit frequency

Không có một con số chung đúng cho mọi hệ thống. Hãy bắt đầu bằng một cấu hình nhỏ, đo, rồi tăng dần có kiểm soát.

Một quy trình thực tế:

1. Chọn batch size ban đầu vừa phải, ví dụ 100 hoặc 200 dòng.
2. Chọn transaction chunk lớn hơn batch size, ví dụ 500 hoặc 1.000 dòng, nếu nghiệp vụ cho phép commit từng chunk.
3. Chạy với dữ liệu có phân bố giống production và mức đồng thời dự kiến.
4. Tăng batch size trong khi quan sát throughput, CPU, memory, network và thời gian executeBatch().
5. Tăng transaction size riêng biệt và quan sát lock wait, deadlock, thời gian transaction và log/undo/version pressure.
6. Giảm kích thước khi p95/p99 latency, lock wait, replication lag hoặc rollback cost tăng mạnh.
7. Kiểm tra lỗi và phục hồi giữa các chunk, không chỉ đo trường hợp thành công.
8. Ghi cấu hình cuối cùng cùng database version, driver, schema và workload.

Các chỉ số nên theo dõi:

| Chỉ số | Điều nó cho biết |
|---|---|
| Rows/sec | Throughput xử lý |
| Batch execution latency | Chi phí mỗi lần gửi/thi hành batch |
| Commit latency | Thời gian chờ hoàn tất commit |
| Transaction duration p50/p95/p99 | Thời gian transaction mở |
| Lock wait duration | Thời gian chờ khóa |
| Deadlock count | Mức xung đột khóa |
| Connection pool wait/usage | Áp lực giữ connection |
| WAL/redo/transaction log bytes | Lượng log phát sinh |
| Undo/version store hoặc vacuum pressure | Áp lực giữ phiên bản cũ |
| Replication lag | Độ trễ áp dụng thay đổi trên replica |
| Rollback duration | Chi phí khi một chunk thất bại |

Đừng tối ưu rows/sec bằng cách bỏ qua tail latency. Một batch lớn có thể tăng throughput trung bình nhưng khiến request khác bị chờ lâu. Chọn điểm cân bằng theo SLA và mức tranh chấp mà hệ thống phải chịu.

## 16. Batch size nên thích ứng với loại thao tác

Các thao tác khác nhau có chi phí và phạm vi khóa khác nhau:

| Loại công việc | Hướng chọn ban đầu |
|---|---|
| INSERT append-only, ít index và ít trigger | Có thể thử batch lớn hơn vì ít tranh chấp trên hàng hiện hữu |
| UPDATE hàng nóng | Batch nhỏ hơn và transaction ngắn để giảm thời gian giữ khóa |
| DELETE theo phạm vi lớn | Chunk theo khóa/index, đo log và lock escalation |
| INSERT có nhiều foreign key/unique index | Batch vừa phải; kiểm tra chi phí constraint và duplicate |
| Cập nhật nhiều bảng liên quan | Chọn chunk theo đơn vị nghiệp vụ, thống nhất thứ tự khóa |
| Import dữ liệu có thể chạy lại | Kết hợp chunk commit, checkpoint và unique/idempotency key |
| Giao dịch thanh toán hoặc chuyển tiền | Giữ ranh giới nguyên tử theo nghiệp vụ; không chia commit tùy tiện |

Batch size cũng có thể bị giới hạn bởi kích thước payload và bộ nhớ. Nếu mỗi bản ghi chứa JSON lớn hoặc binary, 200 bản ghi có thể lớn hơn 10.000 bản ghi nhỏ. Hãy cân nhắc cả số dòng và số byte.

## 17. Các anti-pattern thường gặp

**Commit sau mỗi dòng dù các dòng thuộc cùng một nghiệp vụ.** Điều này tạo trạng thái một phần và overhead commit lớn.

**Một transaction kéo dài qua nhiều tác vụ ngoài database.** Ví dụ gọi HTTP, chờ người dùng hoặc xử lý file trong khi đang giữ khóa. Hãy hoàn thành phần chuẩn bị ngoài transaction nếu an toàn, rồi mở transaction ngắn cho thao tác database.

**Dùng executeBatch() như thể nó tự commit.** Batch execution không thay thế transaction boundary.

**Tăng batch vô hạn để tối đa throughput.** Driver, packet, parameter limit, memory và thời gian lock đều có giới hạn.

**Chia chunk mà không có checkpoint.** Sau crash, job không biết chunk nào đã commit và có thể nhập trùng hoặc bỏ sót.

**Cập nhật checkpoint trong transaction khác.** Có thể đánh dấu tiến độ trước khi dữ liệu thực sự commit hoặc ngược lại.

**Retry cả chunk mà thao tác không idempotent.** Có thể tạo duplicate hoặc trừ số lượng hai lần. Dùng unique key và checkpoint nguyên tử.

**Giữ connection trong khi không làm việc với database.** Điều này làm pool cạn dù database không bận xử lý câu lệnh.

**Chỉ đo throughput trung bình.** Có thể bỏ qua lock wait, commit latency và p99 của request tương tác.

## 18. Checklist triển khai

- [ ] Đã phân biệt batch size, transaction size và commit frequency?
- [ ] executeBatch() có được hiểu đúng là thực thi batch, không tự commit?
- [ ] Batch size có phù hợp giới hạn driver, packet, tham số và bộ nhớ?
- [ ] Transaction size có phù hợp đơn vị nguyên tử của nghiệp vụ?
- [ ] Commit frequency có cân bằng chi phí commit và thời gian giữ tài nguyên?
- [ ] Công việc ngoài database có được thực hiện trước hoặc sau transaction khi phù hợp?
- [ ] Các bảng, trigger và constraint bổ sung có được tính vào tập đọc/ghi?
- [ ] Nhiều hàng có được xử lý theo thứ tự khóa ổn định?
- [ ] Chunk commit có checkpoint được cập nhật trong cùng transaction?
- [ ] Retry chunk có idempotency hoặc unique key bảo vệ?
- [ ] Có chính sách xử lý partial success và lỗi BatchUpdateException?
- [ ] Có xử lý trường hợp kết quả COMMIT không rõ do mất kết nối?
- [ ] Đã đo transaction duration, lock wait, commit latency và replication lag?
- [ ] Đã kiểm thử dưới mức đồng thời gần production?
- [ ] Có ghi lại lý do nghiệp vụ nếu chọn một transaction lớn hoặc commit theo chunk?

Batch size quyết định cách gom câu lệnh để giảm overhead gửi và thực thi; transaction size quyết định phạm vi nguyên tử và lượng tài nguyên có thể bị giữ; commit frequency quyết định thời điểm giải phóng nhiều khóa và xác nhận kết quả bền vững theo cấu hình. Tăng batch có thể cải thiện throughput, còn tăng transaction size có thể làm thời gian chiếm tài nguyên và chi phí rollback lớn hơn. Hãy điều chỉnh từng chiều riêng, giữ nguyên ranh giới nghiệp vụ cần thiết, và đo lock wait, commit latency, log pressure cùng khả năng phục hồi trước khi chọn cấu hình triển khai.
