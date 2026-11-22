# Tính bền vững: ý nghĩa của xác nhận COMMIT

Trong bốn thuộc tính **ACID** của giao dịch cơ sở dữ liệu, **Durability (tính bền vững)** trả lời một câu hỏi rất cụ thể: **Sau khi hệ quản trị cơ sở dữ liệu thông báo giao dịch đã COMMIT thành công, kết quả được bảo toàn trước những sự cố nào?**

Giả sử một giao dịch đã ghi nhận việc chuyển tiền, đặt hàng hoặc trừ tồn kho. Ứng dụng nhận được kết quả COMMIT thành công rồi trả lời người dùng rằng thao tác đã hoàn tất. Nếu máy chủ cơ sở dữ liệu đột ngột mất điện ngay sau đó, dữ liệu đã được xác nhận phải có khả năng được khôi phục theo cam kết độ bền của hệ thống. Nếu chỉ lưu thay đổi trong bộ nhớ RAM và chưa có cơ chế bảo vệ, lời xác nhận này sẽ không đáng tin cậy.

Điểm cốt lõi là **COMMIT vừa là ranh giới logic của giao dịch, vừa là một lời xác nhận theo hợp đồng độ bền mà DBMS và cấu hình triển khai thực sự cung cấp**. Độ bền không có nghĩa dữ liệu không bao giờ có thể mất trong mọi thảm họa; nó phải được hiểu trong phạm vi mô hình sự cố và mức bảo đảm đã cấu hình.

## 1. COMMIT xác nhận điều gì?

Một giao dịch có thể thực hiện nhiều câu lệnh SQL trước khi kết thúc:

~~~sql
-- SQL minh họa; cú pháp bắt đầu giao dịch tùy DBMS.
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 202;

COMMIT;
~~~

Khi COMMIT **thành công**, DBMS xác nhận ranh giới giao dịch: những thay đổi hợp lệ của giao dịch được chấp nhận thành một kết quả đã commit. Những thay đổi đó không còn là phần việc chưa quyết định để ứng dụng có thể hủy bằng ROLLBACK của chính giao dịch đã kết thúc.

Có hai góc nhìn cần tách rõ:

- **Góc nhìn logic:** Các cập nhật thuộc giao dịch được xác nhận theo quy tắc atomicity. Giao dịch đã commit sẽ trở thành một phần của lịch sử dữ liệu được DBMS chấp nhận.
- **Góc nhìn phục hồi:** DBMS phải có đủ thông tin bền vững để phục hồi kết quả đã xác nhận nếu một sự cố thuộc phạm vi được bảo đảm xảy ra ngay sau COMMIT.

Trong triển khai phổ biến sử dụng **write-ahead log (WAL)** hoặc **redo log**, DBMS thường không cần ghi ngay mọi trang dữ liệu bị thay đổi xuống tệp bảng trước khi trả lời COMMIT. Điều kiện quan trọng là **thông tin phục hồi cần thiết** đã đạt mức lưu trữ bền vững mà chế độ commit yêu cầu.

### Phân biệt với câu lệnh SQL đã chạy thành công

Một câu lệnh UPDATE trả về “1 row affected” chỉ cho biết câu lệnh đã ảnh hưởng một hàng theo báo cáo của DBMS. Nếu nó đang nằm trong giao dịch chưa commit, thay đổi vẫn có thể bị rollback.

~~~text
BEGIN
  |
  +-- UPDATE A thành công  --> thay đổi đang nằm trong giao dịch
  |
  +-- UPDATE B thành công  --> vẫn chưa phải kết quả đã commit
  |
  +-- COMMIT thành công    --> kết quả được xác nhận theo bảo đảm DBMS
~~~

Khi JDBC dùng chế độ **auto-commit**, một lần thực thi câu lệnh hoàn tất có thể đồng thời dẫn đến commit tự động. Vì vậy, không được kết luận “chưa gọi commit() nghĩa là chưa có commit” khi chưa biết cấu hình connection và hành vi driver.

## 2. Tại sao COMMIT có thể bền vững trước khi trang dữ liệu được ghi xuống đĩa?

Hệ quản trị CSDL thường dùng bộ nhớ đệm để tăng tốc đọc và ghi. Sau một UPDATE, bản sao trang dữ liệu trong bộ nhớ có thể đã thay đổi, trong khi trang tương ứng trên thiết bị lưu trữ chưa được ghi ngay.

Nếu DBMS bắt buộc phải ghi toàn bộ trang dữ liệu của mọi bảng và chỉ mục xuống thiết bị lưu trữ mỗi khi COMMIT, chi phí mỗi giao dịch có thể rất cao. Cơ chế ghi nhật ký trước (write-ahead logging) giải quyết vấn đề này bằng cách lưu thông tin đủ để khôi phục thay đổi.

Một dòng thời gian khái quát:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant DB as DBMS
    participant Log as WAL/Redo log
    participant Data as Trang dữ liệu

    App->>DB: UPDATE trong giao dịch
    DB->>DB: Cập nhật trạng thái trong bộ nhớ
    DB->>Log: Ghi bản ghi thay đổi/commit
    App->>DB: COMMIT
    DB->>Log: Bảo đảm log đạt mức bền vững yêu cầu
    Log-->>DB: Hoàn tất theo cấu hình
    DB-->>App: COMMIT thành công
    DB-->>Data: Ghi các trang dữ liệu về sau
~~~

Đây là sơ đồ nguyên lý của **chế độ commit đồng bộ với lưu trữ log**. Trình tự chi tiết có thể khác giữa PostgreSQL, MySQL/InnoDB, Oracle, SQL Server và các hệ thống khác. Trong một số cấu hình giảm độ bền để tăng hiệu năng, DBMS có thể xác nhận giao dịch trước khi log thực sự được đồng bộ xuống thiết bị lưu trữ bền vững.

### Ba loại trạng thái dễ bị nhầm

| Thành phần | Chứa gì? | Điều gì xảy ra khi mất điện? |
| --- | --- | --- |
| **Trang dữ liệu trong bộ nhớ** | Bản sao trang dữ liệu đang được cập nhật | Bộ nhớ mất điện có thể mất nội dung chưa được bảo vệ |
| **Bản ghi WAL/redo đã được lưu bền vững** | Thông tin để phục hồi các thay đổi đã commit | Có thể được DBMS phát lại trong quá trình phục hồi |
| **Trang dữ liệu đã ghi vào tệp bảng** | Hình ảnh dữ liệu lưu trong cấu trúc vật lý của DB | Có thể vẫn chưa chứa mọi cập nhật mới nhất; DBMS dùng log để đưa trạng thái về nhất quán |

**Durability không đòi hỏi tất cả các trang dữ liệu phải được ghi ngay khi COMMIT trả về.** Điều cần có là dữ liệu và thông tin phục hồi đáp ứng đúng hợp đồng lưu trữ của DBMS.

### Tại sao cần ghi log *trước*?

Nếu một trang dữ liệu được ghi xuống đĩa trong khi thông tin khôi phục tương ứng chưa an toàn, sự cố giữa chừng có thể để lại dữ liệu thiếu nhất quán hoặc khó xác định trạng thái của một giao dịch. Nguyên tắc write-ahead yêu cầu log cần thiết được ghi theo thứ tự phù hợp trước khi các trang liên quan được ghi bền vững.

Khi khởi động lại sau crash, hệ thống có thể sử dụng nhật ký để **redo** những thay đổi đã commit nhưng chưa phản ánh đủ trong tệp dữ liệu, đồng thời xử lý những thay đổi chưa commit theo thuật toán phục hồi của DBMS. Những DBMS khác nhau có kiến trúc undo/redo và phục hồi khác nhau; không phải tất cả đều dùng cùng một thuật toán.

## 3. Điều gì xảy ra nếu crash ở từng thời điểm?

Xét giao dịch tạo đơn hàng có mã \`ORD-2401\`:

~~~text
T0  BEGIN
T1  INSERT đơn hàng vào trạng thái giao dịch
T2  DBMS ghi/chuẩn bị các bản ghi nhật ký
T3  DBMS đạt ranh giới COMMIT bền vững theo cấu hình
T4  DBMS gửi phản hồi COMMIT thành công
T5  Ứng dụng nhận phản hồi
T6  Trang dữ liệu có thể được flush vào tệp bảng sau đó
~~~

Các mốc là sơ đồ khái niệm, không phải lịch thực thi cố định của mọi DBMS.

| Điểm xảy ra sự cố | Trạng thái từ góc nhìn ứng dụng | Kết luận có thể rút ra |
| --- | --- | --- |
| **Trước COMMIT bền vững** | Ứng dụng chưa nhận xác nhận thành công | Giao dịch có thể không được khôi phục như một giao dịch đã commit; phải kiểm tra kết quả thực tế |
| **Sau khi DBMS đã commit bền vững, trước khi ứng dụng nhận phản hồi** | Ứng dụng thấy timeout hoặc mất kết nối | **Kết quả không xác định ở phía ứng dụng**: giao dịch có thể đã commit dù client thấy lỗi |
| **Sau khi ứng dụng nhận COMMIT thành công** | Ứng dụng biết DBMS đã xác nhận | Trong phạm vi cam kết độ bền và cấu hình thực tế, kết quả đã commit phải tồn tại sau sự cố được bảo vệ |
| **Sau COMMIT, trước khi trang bảng được flush** | COMMIT đã thành công | Trang bảng chưa cập nhật hết không tự làm mất kết quả nếu log cần thiết còn bền vững và phục hồi thành công |

### Trường hợp nguy hiểm nhất: đã COMMIT nhưng phản hồi bị mất

Giả sử:

1. Client gửi COMMIT.
2. DBMS ghi nhận giao dịch thành công.
3. Mạng bị ngắt trước khi gói phản hồi tới client.
4. Driver JDBC ném \`SQLException\` hoặc báo timeout.

Client **không thể tự suy ra giao dịch đã rollback** chỉ từ lỗi gọi commit(). Nếu client gửi lại toàn bộ yêu cầu “chuyển thêm 100” mà không có cơ chế nhận diện thao tác cũ, người dùng có thể bị ghi nhận hai lần.

Đây là lý do cần tách hai câu hỏi:

- **DBMS đã commit hay chưa?** Trạng thái thực tế ở hệ thống lưu trữ.
- **Ứng dụng có nhận được xác nhận hay chưa?** Trạng thái hiểu biết của client.

Hai sự kiện này không phải lúc nào cũng đồng thời hoặc đều quan sát được.

## 4. COMMIT không đồng nghĩa với “mọi bản sao đều đã có dữ liệu”

Trong cơ sở dữ liệu triển khai nhiều nút, một primary có thể xác nhận COMMIT trong khi replica nhận thay đổi bất đồng bộ.

~~~mermaid
flowchart LR
    App["Ứng dụng"] --> P["Primary"]
    P -->|COMMIT thành công| App
    P -.->|Sao chép bất đồng bộ| R["Replica"]
    R --> Read["Truy vấn đọc ở replica"]
~~~

Nếu replica đang bị trễ, một truy vấn ngay sau COMMIT trên replica có thể chưa thấy đơn hàng vừa tạo. Điều đó **không nhất thiết phủ nhận việc giao dịch đã được commit trên primary**.

Tuy nhiên, replication bất đồng bộ còn đặt ra rủi ro khác: nếu primary chết vĩnh viễn trước khi replica nhận những giao dịch cuối cùng và replica cũ được nâng thành primary mới, có thể xảy ra **mất dữ liệu đã được primary xác nhận**. Hợp đồng độ bền của cả cụm vì vậy phụ thuộc chính sách replication, failover và cấu hình commit.

| Cơ chế | COMMIT thường chờ đến đâu? | Vấn đề cần xác định |
| --- | --- | --- |
| **Một máy, log đồng bộ bền vững** | Thông tin phục hồi đạt mức lưu trữ bền vững được cấu hình | Thiết bị lưu trữ, fsync, cache và phục hồi có bảo đảm đúng không? |
| **Replica bất đồng bộ** | Primary commit mà không nhất thiết chờ replica nhận | Lag, lựa chọn nút failover và nguy cơ mất commit mới nhất |
| **Replica đồng bộ** | Chờ một hoặc nhiều điều kiện xác nhận từ replica theo cấu hình | Replica chỉ “đã nhận”, “đã ghi” hay “đã flush bền vững”? |
| **Commit dựa trên quorum/consensus** | Chờ điều kiện đa số hoặc quorum phù hợp với giao thức | Mô hình lỗi, điều kiện quorum và hành vi khi mất liên lạc |

Tên gọi “synchronous replication” tự nó chưa đủ để kết luận mọi replica đều bền vững. Cần biết **điều kiện ACK cụ thể**, ví dụ đã nhận log qua mạng, đã ghi vào bộ nhớ đệm, đã flush ra lưu trữ bền vững hay đã áp dụng thay đổi để phục vụ truy vấn.

Tương tự, **COMMIT thành công không tự bảo đảm mọi yêu cầu đọc sau đó sẽ thấy dữ liệu**, nếu ứng dụng đọc từ một replica trễ hoặc hệ thống sử dụng mô hình nhất quán đọc khác.

## 5. Cấu hình lưu trữ quyết định mức độ đáng tin của xác nhận

DBMS phải kết hợp bộ nhớ đệm, hệ điều hành, hệ thống tệp và thiết bị lưu trữ. Những tầng này không có cùng khái niệm “đã ghi xong”:

~~~text
Ứng dụng gọi COMMIT
        |
DBMS tạo bản ghi WAL / redo
        |
Bộ đệm DBMS và bộ đệm hệ điều hành
        |
Đồng bộ ghi (fsync/fdatasync hoặc cơ chế tương đương)
        |
Thiết bị lưu trữ / bộ điều khiển
        |
ACK theo chính sách của hệ thống
~~~

**Ghi dữ liệu vào page cache của hệ điều hành** chưa nhất thiết đồng nghĩa với ghi bền vững xuống thiết bị. Tương tự, một thiết bị có cache ghi không được bảo vệ trước mất điện có thể không thực hiện đúng điều ứng dụng mong đợi nếu stack lưu trữ báo hoàn tất quá sớm hoặc không tuân thủ lệnh flush.

Các hệ quản trị và nền tảng cung cấp nhiều lựa chọn để cân bằng hiệu năng với độ bền. Ví dụ về nhóm quyết định cấu hình cần quan tâm:

- **PostgreSQL:** Chính sách đồng bộ WAL và \`synchronous_commit\` ảnh hưởng đến lúc nào client nhận xác nhận; ở chế độ giảm đồng bộ, một giao dịch đã được báo thành công có thể mất trong sự cố crash thích hợp.
- **MySQL/InnoDB:** Chính sách flush redo log như \`innodb_flush_log_at_trx_commit\` ảnh hưởng đến ranh giới lưu bền vững. Binlog còn có cấu hình đồng bộ riêng, quan trọng khi xét replication và phục hồi.
- **Các DBMS khác:** Đều có cơ chế và cấu hình tương ứng nhưng tên, hành vi và mô hình phục hồi khác nhau.

Không nên so sánh các hệ thống chỉ dựa trên tên tham số. Cần đối chiếu tài liệu phiên bản đang dùng, chế độ vận hành thực tế, phần cứng và các bài kiểm tra khôi phục. Đặc biệt, chế độ **COMMIT bất đồng bộ** có thể giảm thời gian chờ nhưng thay đổi chính xác điều một lời xác nhận thành công đang bảo đảm.

### Vì sao group commit hữu ích?

Nhiều giao dịch nhỏ có thể cần đồng bộ log, một thao tác có chi phí đáng kể. **Group commit** cho phép DBMS gom bản ghi của nhiều giao dịch để thực hiện chung một hoặc một số lượt đồng bộ log:

~~~text
T1 --\
T2 ---+--> Ghi/flush WAL theo nhóm --> ACK cho các giao dịch đủ điều kiện
T3 --/
~~~

Tính bền vững vẫn có thể được bảo toàn nếu DBMS chỉ xác nhận những giao dịch đã đạt điều kiện commit theo cấu hình. Group commit là một cách tối ưu thông lượng; không đồng nghĩa tự động nới lỏng cam kết độ bền.

## 6. Ví dụ nghiệp vụ: xác nhận một đơn hàng

Giả sử hệ thống bán hàng cần vừa trừ tồn kho vừa tạo đơn hàng. Với dữ liệu cùng nằm trong một DB giao dịch, hai thao tác có thể được gom thành một transaction:

~~~sql
-- SQL minh họa cho DBMS hỗ trợ kiểu ranh giới này.
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'BOOK-01'
  AND quantity >= 1;

-- Ứng dụng phải kiểm tra số hàng được UPDATE: phải đúng 1.
INSERT INTO orders (order_id, sku, status)
VALUES ('ORD-2401', 'BOOK-01', 'CONFIRMED');

COMMIT;
~~~

Cần có ràng buộc duy nhất trên \`orders.order_id\` và quy tắc kiểm tra số hàng cập nhật. Nếu hết hàng hoặc tạo đơn thất bại, ứng dụng phải rollback để hai thay đổi không bị tách rời. Khi COMMIT đã thành công, DBMS xác nhận **cả tập thay đổi thuộc giao dịch** theo cơ chế của hệ thống.

### Ứng dụng nên trả lời người dùng khi nào?

Trong thao tác yêu cầu kết quả đã lưu bền vững, ứng dụng thường chỉ trả lời “đơn hàng đã được ghi nhận” **sau khi nhận xác nhận COMMIT thành công**. Trả HTTP 200 ngay sau INSERT nhưng trước COMMIT có thể khiến người dùng nhận thông báo thành công, trong khi giao dịch cuối cùng bị rollback.

Dù vậy, một HTTP response thất bại **không chứng minh** DB transaction thất bại: ứng dụng có thể crash sau commit nhưng trước khi trả HTTP response. Vì thế API nên cung cấp cách tra cứu kết quả theo một mã thao tác ổn định.

### JDBC minh họa phạm vi COMMIT

~~~java
// Ví dụ minh họa; dataSource và orderId đã được cung cấp.
// Giả sử bảng orders có UNIQUE/PRIMARY KEY trên order_id.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    boolean commitAttempted = false;

    try (PreparedStatement insert = connection.prepareStatement(
            "INSERT INTO orders (order_id, status) VALUES (?, ?)")) {
        insert.setString(1, orderId);
        insert.setString(2, "CONFIRMED");

        if (insert.executeUpdate() != 1) {
            throw new SQLException("Không tạo được đơn hàng");
        }

        commitAttempted = true;
        connection.commit(); // Chỉ khi trả về thành công, client mới có xác nhận.
    } catch (SQLException error) {
        if (!commitAttempted) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
        }
        // Nếu commit() đã được gọi mà báo lỗi, trạng thái có thể chưa xác định.
        throw error;
    }
}
~~~

Ví dụ chỉ tập trung vào ranh giới commit của một thao tác INSERT. Trong ứng dụng thật, cần triển khai đầy đủ việc kiểm tra nghiệp vụ, quản lý trạng thái connection/pool và xử lý lỗi. Đặc biệt:

- \`executeUpdate() == 1\` **không chứng minh dữ liệu đã bền vững** khi transaction chưa commit.
- \`commit()\` trả về bình thường là sự kiện client có thể dùng làm **xác nhận thành công theo hợp đồng JDBC/DBMS**.
- Nếu \`commit()\` ném lỗi hoặc kết nối đứt trong lúc commit, code trên **không coi việc rollback là bằng chứng giao dịch chưa commit**. Phải đối chiếu trạng thái nghiệp vụ trong DB trước khi quyết định thử lại.
- Việc tự động trả connection về pool không thay thế thiết kế ranh giới transaction và chiến lược phục hồi khi kết quả commit chưa rõ.

## 7. Khi không biết COMMIT đã thành công: idempotency

Một trường hợp phổ biến của hệ thống phân tán:

~~~text
Client                   Ứng dụng                  Database
  |                         |                         |
  |---- POST tạo đơn ------>|                         |
  |                         |---- INSERT + COMMIT ---->|
  |                         |<--- COMMIT thành công ---|
  |                         X Ứng dụng crash          |
  |<---- timeout -----------|                         |
  |                         |                         |
  |---- POST lại ---------->|                         |
~~~

Nếu POST lần hai lại tạo một đơn mới, giao dịch đầu tiên có thể đã bền vững và hệ thống tạo ra đơn hàng trùng. Cách xử lý là thiết kế **idempotency**: cùng một yêu cầu nghiệp vụ có một mã định danh không đổi, ví dụ \`operation_id\`, \`payment_id\` hoặc \`order_id\`.

Một chiến lược điển hình:

1. Client gửi \`order_id = ORD-2401\` cho cùng một ý định tạo đơn.
2. DB có ràng buộc **UNIQUE(order_id)** hoặc bảng idempotency được bảo vệ giao dịch.
3. Nếu client timeout, lần gọi lại giữ nguyên mã thay vì tạo một mã mới.
4. Ứng dụng tra cứu trạng thái từ nguồn có độ nhất quán phù hợp, thường là primary hoặc một truy vấn đọc được cấu hình đúng; nếu bản ghi đã tồn tại và khớp yêu cầu, trả lại kết quả của lần trước.
5. Nếu chưa có bằng chứng kết quả, ứng dụng tiếp tục theo quy trình retry có kiểm soát, dùng chính ràng buộc duy nhất để ngăn ghi trùng.

Không nên chỉ dựa vào lệnh SELECT “chưa thấy bản ghi” trên replica có thể đang lag để kết luận COMMIT trước đó chắc chắn thất bại. Trong tình huống yêu cầu có trạng thái chưa xác định, **ràng buộc dữ liệu và mã thao tác ổn định** đáng tin hơn việc dự đoán kết quả từ timeout.

Với các hệ thống tài chính, quyết định retry còn cần đối chiếu sổ cái, trạng thái thanh toán và giao thức của nhà cung cấp dịch vụ ngoài. **Idempotency** giúp xử lý việc nhận lại yêu cầu, nhưng cần được triển khai xuyên suốt đường đi của nghiệp vụ để tránh tạo hiệu ứng phụ hai lần.

## 8. COMMIT của DB có đảm bảo email, Kafka hay HTTP API đã hoàn thành?

**Không.** Một giao dịch trong cơ sở dữ liệu quan hệ thông thường chỉ bao phủ những tài nguyên tham gia trong giao dịch đó. Ví dụ:

~~~text
BEGIN transaction trong DB
   INSERT đơn hàng
COMMIT DB thành công
   Gửi email xác nhận
   Publish sự kiện lên message broker
~~~

Nếu ứng dụng crash ngay sau COMMIT DB nhưng trước khi gửi sự kiện, đơn hàng vẫn tồn tại, còn email hoặc sự kiện có thể chưa xuất hiện. Ngược lại, nếu gửi sự kiện trước COMMIT, consumer có thể quan sát sự kiện trong khi giao dịch DB cuối cùng rollback.

Đây không phải lỗi của ACID trong DB; hai hệ thống có **ranh giới giao dịch khác nhau**. Để liên kết việc ghi dữ liệu và phát sự kiện, một phương án phổ biến là **transactional outbox**:

~~~text
Một transaction DB:
    +-- INSERT orders
    +-- INSERT outbox_events
    +-- COMMIT
                 |
          Worker đọc outbox
                 |
          Gửi sự kiện
                 |
          Đánh dấu đã xử lý
~~~

Khi commit DB thành công, cả đơn hàng lẫn bản ghi outbox được lưu theo cùng một giao dịch. Tiến trình phát sự kiện có thể thử lại sau crash. Tuy nhiên, thao tác gửi sự kiện vẫn có thể bị lặp nếu worker crash sau khi gửi nhưng trước lúc đánh dấu; consumer nên có cơ chế nhận diện trùng lặp phù hợp.

Giao dịch phân tán với giao thức phối hợp như two-phase commit có thể cung cấp cam kết khác khi các thành phần thực sự tham gia, nhưng không nên giả định một lệnh \`connection.commit()\` thông thường tự động bao phủ mọi hệ thống ngoài DB.

## 9. Durability khác gì với Atomicity, Consistency và Isolation?

Cả bốn thuộc tính bổ sung cho nhau, nhưng giải quyết các vấn đề khác nhau:

| Thuộc tính ACID | Câu hỏi trọng tâm | Ví dụ liên quan đến COMMIT |
| --- | --- | --- |
| **Atomicity** | Giao dịch được chấp nhận toàn bộ hay bị hủy toàn bộ? | Trừ tồn kho và tạo đơn phải là một đơn vị |
| **Consistency** | Các ràng buộc và bất biến dữ liệu được duy trì như thế nào? | Không được tạo đơn vi phạm khóa ngoại hoặc các ràng buộc được thực thi |
| **Isolation** | Các giao dịch chạy đồng thời nhìn thấy và ảnh hưởng nhau ra sao? | Hai giao dịch tranh chấp cùng một hàng có thể chờ khóa hoặc xung đột |
| **Durability** | Sau COMMIT được xác nhận, kết quả tồn tại qua sự cố được bảo đảm không? | Crash sau COMMIT không làm biến mất đơn hàng trong phạm vi bảo đảm lưu trữ |

Một số hiểu lầm dễ gặp:

- **“COMMIT thành công là không thể ROLLBACK.”** Không thể dùng ROLLBACK để hủy *chính giao dịch đã hoàn tất*. Nhưng một giao dịch mới có thể tạo **bút toán bù trừ** hoặc cập nhật dữ liệu theo nghiệp vụ, và dữ liệu vẫn có thể bị xóa hợp lệ sau đó.
- **“Durability nghĩa là không bao giờ mất dữ liệu.”** Thiên tai phá hủy toàn bộ thiết bị, lỗi phần cứng nghiêm trọng, thao tác quản trị hoặc sự cố failover ngoài hợp đồng có thể gây mất dữ liệu. Sao lưu, phục hồi và nhân bản vẫn là các biện pháp cần thiết.
- **“Đã COMMIT thì mọi truy vấn đều lập tức thấy dữ liệu.”** Khả năng nhìn thấy dữ liệu còn phụ thuộc isolation, snapshot đang dùng, tuyến đọc và độ trễ replica.
- **“COMMIT nhanh nhất luôn tốt nhất.”** Chính sách ghi không đồng bộ có thể tăng thông lượng nhưng giảm mức bảo vệ trước sự cố; phải chọn theo yêu cầu mất dữ liệu có thể chấp nhận.
- **“Driver báo lỗi tại commit() nghĩa là DB chắc chắn rollback.”** Phản hồi có thể đã mất sau khi DB commit. Cần xác minh qua dữ liệu nghiệp vụ và khóa idempotency.

## 10. Vận hành: xác nhận bền vững đến mức nào là đủ?

Các loại ứng dụng có yêu cầu khác nhau. Một hệ thống xử lý số dư hoặc đơn hàng cần biết chắc ý nghĩa của lời xác nhận. Một kho dữ liệu có thể chấp nhận nạp lại một số bản ghi sau sự cố để đổi lấy hiệu năng. Sự khác biệt nằm ở **mức mất dữ liệu cho phép (RPO)**, khả năng phục hồi và cam kết trải nghiệm người dùng.

Khi thiết kế một hệ thống, cần xác định rõ:

1. **Sự cố cần chống chịu:** crash của process DB, restart hệ điều hành, mất điện một máy, mất nút primary, mất toàn vùng hay hỏng thiết bị lưu trữ.
2. **Điều kiện để COMMIT được ACK:** chỉ vào bộ đệm, đồng bộ WAL/redo trên máy chính, hay chờ thêm replica/quorum.
3. **Chiến lược failover:** replica nào được phép lên primary; có thể mất những commit vừa xác nhận không?
4. **Đường đọc sau ghi:** người dùng có được đọc từ replica trễ ngay sau khi tạo dữ liệu hay không?
5. **Khôi phục và sao lưu:** có backup, point-in-time recovery, kiểm tra khả năng restore và bảo vệ khỏi xóa/hỏng dữ liệu không?
6. **Retry khi phản hồi không rõ:** có \`operation_id\`, unique constraint, trạng thái giao dịch nghiệp vụ và phương án tránh thực thi hai lần không?

Đánh giá độ bền cần xem **toàn bộ đường lưu trữ và phục hồi**, không chỉ việc ứng dụng có gọi \`commit()\` hay không. Đọc log DB, kiểm tra cấu hình flush/replication và thực hành restore từ backup là những hoạt động vận hành riêng biệt với việc chạy các câu SQL thành công.

### Ví dụ ngắn để tự kiểm tra

**Tình huống A:** UPDATE thành công nhưng ứng dụng gọi ROLLBACK trước COMMIT. Có bảo đảm durability cho UPDATE không?

**Không.** UPDATE đó chưa được xác nhận như kết quả cuối cùng của giao dịch. Với rollback thành công, DBMS hủy thay đổi chưa commit theo cơ chế giao dịch.

**Tình huống B:** COMMIT thành công, trang dữ liệu chưa được flush, DB process crash. Có nhất thiết mất dữ liệu không?

**Không.** Nếu WAL/redo cần thiết đã bền vững và cơ chế recovery hoạt động đúng, DBMS có thể phục hồi thay đổi đã commit từ log.

**Tình huống C:** COMMIT thành công trên primary, nhưng đọc ngay trên replica không thấy bản ghi. Có phải COMMIT đã thất bại không?

**Không thể kết luận như vậy.** Replica có thể chưa nhận hoặc chưa áp dụng thay đổi. Cần kiểm tra trạng thái trên nguồn đọc phù hợp và xem chính sách replication/failover.

**Tình huống D:** Ứng dụng nhận timeout khi gọi commit(). Có nên luôn retry cả giao dịch bằng một mã đơn hàng mới không?

**Không.** Timeout có thể xảy ra sau khi DBMS đã commit. Cần dùng định danh nghiệp vụ ổn định, kiểm tra trạng thái và ngăn ghi trùng.

**Tình huống E:** COMMIT DB thành công nhưng server ứng dụng chết trước khi gửi Kafka event. Điều gì được bảo đảm?

**Chỉ kết quả thuộc phạm vi transaction DB**, theo hợp đồng độ bền của DBMS. Việc phát Kafka event cần thiết kế bảo đảm riêng, ví dụ outbox cùng cơ chế retry và khử trùng lặp.

## 11. Kết luận về ý nghĩa của xác nhận COMMIT

Câu “giao dịch đã COMMIT thành công” có ý nghĩa hơn việc các câu SQL đã chạy mà không báo lỗi. Nó là **ranh giới mà DBMS xác nhận đã chấp nhận giao dịch**, đồng thời cam kết khả năng giữ và khôi phục kết quả theo chính sách độ bền đã cấu hình.

Với cơ sở dữ liệu có log bền vững đúng cách, dữ liệu đã commit có thể phục hồi ngay cả khi trang dữ liệu chưa được ghi hết xuống tệp bảng. Nhưng **thời điểm client nhận được ACK**, **bảo đảm bền vững trên thiết bị**, **cơ chế replication/failover** và **việc ứng dụng có biết chắc kết quả commit hay không** là bốn vấn đề cần phân biệt. Chỉ khi hiểu đầy đủ các ranh giới này, ứng dụng mới có thể nói chính xác một thao tác nghiệp vụ đã được lưu an toàn đến mức nào.
