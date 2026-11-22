# Thao tác tăng giảm nguyên tử tại nơi lưu trữ

Khi hai yêu cầu cùng tăng lượt xem, trừ tồn kho hoặc cập nhật số dư, việc mỗi yêu cầu tự đọc một giá trị rồi ghi lại kết quả tính trong Java có thể làm mất cập nhật. Cách giải quyết cơ bản là **đưa phép tăng/giảm vào chính câu lệnh tại nơi lưu trữ**: yêu cầu cơ sở dữ liệu tính từ giá trị hiện hành và thực hiện cập nhật như một đơn vị nguyên tử. Với nghiệp vụ có điều kiện, cần đưa cả **điều kiện kiểm tra và phép thay đổi** vào cùng thao tác.

Bài thuộc chương **Kiểm soát đồng thời** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Trong phạm vi lưu trữ dữ liệu bền vững cho ứng dụng Java, người học cần nắm vững mô hình dữ liệu, truy vấn, giao dịch, cô lập và xử lý xung đột; biết thiết kế ranh giới persistence để tránh lỗi cạnh tranh, xử lý sự cố kết nối và tối ưu tải. Bài tập trung vào thao tác tăng/giảm số tại cơ sở dữ liệu quan hệ, minh họa bằng **PostgreSQL, JDBC và Spring**. Một phần cuối đối chiếu với thao tác nguyên tử ở kho key-value như Redis; bảo đảm của từng hệ quản trị cần được kiểm tra riêng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích lỗi **lost update** do mẫu đọc–tính–ghi bên ngoài cơ sở dữ liệu.
- Viết **UPDATE counter = counter + delta** và **UPDATE stock = stock - amount WHERE stock >= amount** để tăng/giảm nguyên tử trong một câu lệnh.
- Hiểu vai trò của khóa hàng, mức cô lập và **số hàng được cập nhật** khi hai yêu cầu cùng thay đổi một hàng.
- Phân biệt nguyên tử của **một câu UPDATE** với nguyên tử của **nhiều câu SQL trong cùng giao dịch**.
- Triển khai thao tác bằng **PreparedStatement** hoặc **JdbcTemplate**, xử lý yêu cầu lặp, lỗi kết nối, ràng buộc và giới hạn hiệu năng.
- Biết khi nào phép tăng/giảm ở nơi lưu trữ vẫn chưa đủ để bảo vệ một quy tắc nghiệp vụ liên quan đến nhiều hàng hoặc nhiều hệ thống.

## 2. Vì sao đọc–tính–ghi trong Java có thể làm mất cập nhật?

Giả sử một bản ghi thống kê đang có **views = 5**. Hai yêu cầu A và B cùng muốn tăng thêm 1. Cách làm dễ mắc lỗi:

~~~java
long current = repository.findViews(articleId); // SELECT views
long next = current + 1;
repository.updateViews(articleId, next);        // UPDATE views = ?
~~~

Các thao tác trên có thể xen kẽ như sau:

~~~text
Thời gian          Yêu cầu A                      Yêu cầu B
     1             SELECT -> 5
     2                                            SELECT -> 5
     3             Tính 5 + 1 = 6
     4                                            Tính 5 + 1 = 6
     5             UPDATE views = 6
     6                                            UPDATE views = 6
Kết quả            views = 6, trong khi hai lần tăng phải được 7
~~~

**Lost update** xảy ra vì mỗi yêu cầu ghi một **giá trị tuyệt đối đã tính từ bản đọc cũ**. Dù bản thân từng câu UPDATE được thực thi nguyên tử, toàn bộ chuỗi **SELECT → tính trong Java → UPDATE** không tự động nguyên tử. Bật giao dịch mà không chọn cơ chế cô lập hoặc khóa phù hợp cũng không nhất thiết sửa được lỗi này.

Cách viết khác chuyển phép tăng vào nơi lưu trữ:

~~~sql
UPDATE article_stats
SET views = views + 1
WHERE article_id = 42;
~~~

Khi hai yêu cầu thực hiện câu này trên cùng hàng trong PostgreSQL, việc cập nhật được đồng bộ qua cơ chế khóa và quản lý phiên bản hàng. Yêu cầu cập nhật tiếp theo sẽ không chỉ chép lại một số **6** đã tính ở client; nó thực hiện phép tăng dựa trên phiên bản phù hợp khi tới lượt cập nhật. Với hai lần cập nhật đều commit thành công và không có thay đổi khác, từ **5** sẽ thành **7**.

Điều quan trọng là **phép toán nằm trong UPDATE**: **SET views = views + 1**, không phải chỉ chuyển phép cộng từ một method Java sang một method repository nhưng vẫn gửi **SET views = :oldValuePlusOne**.

## 3. “Nguyên tử” trong thao tác tăng giảm nghĩa là gì?

Một thao tác nguyên tử được nhìn nhận như một thay đổi không bị quan sát ở trạng thái dở dang ở phạm vi bảo đảm của hệ lưu trữ. Với một câu **UPDATE** trong cơ sở dữ liệu quan hệ hỗ trợ giao dịch:

- Các thay đổi thuộc câu lệnh có tính nguyên tử theo giao dịch hiện tại: nếu câu lệnh thất bại, không để lại một nửa kết quả của chính câu lệnh.
- Khi nhiều giao dịch cùng cập nhật **một hàng**, hệ quản trị điều phối ghi để tránh hai phép tăng hợp lệ vô tình ghi đè nhau như ví dụ đọc–tính–ghi.
- Nếu câu lệnh chạy dưới **auto-commit**, một lần cập nhật thành công thường được commit ở ranh giới câu lệnh; nếu nằm trong giao dịch tường minh, thay đổi **chưa bền vững cho đến khi COMMIT**.
- Tính nguyên tử không bảo đảm client biết kết quả khi mạng mất đúng lúc nhận phản hồi commit; đó là bài toán **kết quả không chắc chắn** và **idempotency**.

**Phân biệt ba phạm vi bảo đảm:**

| Phạm vi | Ví dụ | Điều được bảo vệ |
| --- | --- | --- |
| Một câu SQL cập nhật một hàng | **SET quantity = quantity - 1** | Một phép thay đổi trên hàng đó |
| Một câu SQL cập nhật nhiều hàng | **UPDATE ... WHERE ...** | Tính nguyên tử của cả câu lệnh trong giao dịch, dù số hàng có thể lớn hơn 1 |
| Nhiều câu SQL trong một giao dịch | Trừ tiền nguồn, cộng tiền đích, ghi lịch sử | Toàn bộ các bước commit/rollback cùng nhau nếu cùng tham gia transaction |

Vì vậy, khi chỉ cần tăng một bộ đếm, một UPDATE có thể đủ. Khi còn phải tạo đơn hàng hay ghi bản ghi kiểm toán, cần xác định ranh giới giao dịch rộng hơn.

## 4. Tăng bộ đếm bằng SQL

Giả sử bảng:

~~~sql
CREATE TABLE article_stats (
    article_id BIGINT PRIMARY KEY,
    views BIGINT NOT NULL DEFAULT 0 CHECK (views >= 0)
);

INSERT INTO article_stats(article_id, views)
VALUES (42, 5);
~~~

Tăng một đơn vị:

~~~sql
UPDATE article_stats
SET views = views + 1
WHERE article_id = 42;
~~~

Tăng theo biến **delta**:

~~~sql
UPDATE article_stats
SET views = views + :delta
WHERE article_id = :articleId;
~~~

Đây là cú pháp tham số đặt tên thường gặp trong Spring, không phải SQL trực tiếp có thể gửi qua JDBC thuần. Trong JDBC, thay các tham số bằng dấu **?**. **delta** cần được xác thực: nếu nghiệp vụ chỉ cho tăng, yêu cầu **delta > 0**; nếu cho tăng lẫn giảm, phải bảo vệ biên dưới và trên.

PostgreSQL cho phép trả về giá trị **sau cập nhật**:

~~~sql
UPDATE article_stats
SET views = views + 1
WHERE article_id = 42
RETURNING views;
~~~

Với bảng giả lập đã có hàng, câu lệnh trả một dòng chứa giá trị mới. **RETURNING** giúp tránh phải gửi thêm một SELECT chỉ để nhận kết quả của cập nhật. Tuy nhiên, trong giao dịch chưa commit, giá trị trả về vẫn có thể bị rollback.

Nếu bài toán chỉ cần đếm số sự kiện và **không nhất thiết phải chính xác đến từng lần** (ví dụ số lượt hiển thị không quan trọng cho thanh toán), có thể chấp nhận xử lý theo lô. Nếu số đếm là dữ liệu nghiệp vụ có ràng buộc chặt, phải xem xét cả yêu cầu lặp, độ bền, giới hạn và khả năng đối soát.

## 5. Giảm tồn kho có điều kiện: kiểm tra và trừ cùng lúc

Phép giảm đơn giản:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE tenant_id = 10 AND product_id = 1001;
~~~

không đủ nếu nghiệp vụ cấm tồn kho âm. Khi hai người cùng mua đơn vị hàng cuối cùng, cần bảo đảm điều kiện **còn đủ hàng** và phép trừ được xử lý như một thao tác duy nhất:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE tenant_id = :tenantId
  AND product_id = :productId
  AND available >= :quantity;
~~~

Mẫu trên có ba phần cần đi cùng nhau:

1. **Xác định đúng hàng** theo khóa nghiệp vụ, bao gồm tenant nếu ứng dụng phân tách dữ liệu theo tenant.
2. **Giảm dựa trên giá trị hiện hành trong DB** bằng **available = available - :quantity**.
3. **Kiểm tra điều kiện giới hạn ngay trong WHERE** bằng **available >= :quantity**.

Ứng dụng phải kiểm tra **số hàng cập nhật**. Nếu khóa (**tenant_id, product_id**) là duy nhất, kết quả mong đợi:

| Số hàng cập nhật | Cách hiểu |
| --- | --- |
| **1** | Đã trừ thành công trong giao dịch hiện tại; nếu transaction chưa commit, vẫn có thể rollback |
| **0** | Không có hàng thỏa điều kiện, có thể vì thiếu hàng hoặc không đủ tồn kho |
| **Lớn hơn 1** | Trái với giả định khóa duy nhất; cần kiểm tra mô hình dữ liệu và câu WHERE |

Không được chỉ dựa vào giá trị boolean do một API trả về rồi mặc định đơn hàng đã được xác nhận. Nếu nằm trong giao dịch nhiều bước, câu UPDATE trả **1** mới có nghĩa bước trừ kho **đã chạy**, không đồng nghĩa **toàn giao dịch đã commit**.

### 5.1. Lược đồ bảo vệ bất biến

Trong PostgreSQL, có thể bắt đầu từ:

~~~sql
CREATE TABLE inventory (
    tenant_id  BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    available  BIGINT NOT NULL DEFAULT 0,
    reserved   BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, product_id),
    CHECK (available >= 0),
    CHECK (reserved >= 0)
);
~~~

Với yêu cầu **giữ chỗ** thay vì bán ngay, một câu UPDATE có thể chuyển số lượng từ **available** sang **reserved**:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    reserved  = reserved + :quantity
WHERE tenant_id = :tenantId
  AND product_id = :productId
  AND available >= :quantity
RETURNING available, reserved;
~~~

Trong PostgreSQL, các biểu thức bên phải của **SET** trong cùng UPDATE được đánh giá từ giá trị của hàng trước cập nhật, nên **reserved + quantity** và **available - quantity** tạo ra một chuyển dịch nhất quán trên cùng hàng. Hai CHECK giúp ngăn giá trị âm ở tầng DB, kể cả khi có đường ghi khác. Nếu số nguyên vượt phạm vi kiểu **BIGINT**, PostgreSQL sẽ báo lỗi; chương trình không được mặc định mọi hệ quản trị có cùng cách xử lý tràn số.

Ví dụ SQL dùng **:quantity** là tham số giả lập, chưa phải lệnh đầy đủ để chạy trực tiếp trong psql; khi thực thi cần thay bằng tham số của công cụ hoặc literal thử nghiệm. Cần kiểm tra **quantity > 0** từ ứng dụng; điều kiện **available >= quantity** với quantity âm sẽ cho phép hành vi ngược ý định.

## 6. Hai yêu cầu đồng thời mua đơn vị cuối cùng

Giả sử **inventory.available = 1**, hai người đều yêu cầu trừ **1** trên cùng hàng. Với PostgreSQL **READ COMMITTED**, một lịch thực thi có thể là:

~~~text
Phiên T1                               Phiên T2
BEGIN;
UPDATE ... available >= 1;
  --> cập nhật 1 thành 0, giữ khóa
                                       BEGIN;
                                       UPDATE ... available >= 1;
                                         --> chờ khóa hàng
COMMIT;
                                       Kiểm tra lại trên phiên bản mới
                                       --> available = 0; cập nhật 0 hàng
                                       COMMIT;

Kết quả: available = 0, chỉ một lượt mua được chấp nhận.
~~~

Có thể tái hiện trên hai kết nối PostgreSQL độc lập bằng lược đồ ở phần 5:

**Chuẩn bị trong môi trường thử nghiệm:**

~~~sql
INSERT INTO inventory(tenant_id, product_id, available, reserved)
VALUES (10, 1001, 1, 0);
~~~

**Phiên T1:**

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE inventory
SET available = available - 1
WHERE tenant_id = 10
  AND product_id = 1001
  AND available >= 1
RETURNING available;
-- Trả về 0, chưa COMMIT.
~~~

**Phiên T2, chạy khi T1 vẫn đang giữ giao dịch mở:**

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE inventory
SET available = available - 1
WHERE tenant_id = 10
  AND product_id = 1001
  AND available >= 1
RETURNING available;
-- Có thể phải chờ T1 kết thúc.
~~~

Sau đó **T1 COMMIT**. **T2** tiếp tục và trả **0 dòng**, vì phiên bản hàng đã được cập nhật còn available = 0; **T2 COMMIT** để kết thúc thử nghiệm. Tại PostgreSQL READ COMMITTED, khi một UPDATE đợi giao dịch khác cập nhật cùng hàng, điều kiện WHERE có thể được đánh giá lại trên phiên bản phù hợp sau khi giao dịch kia kết thúc.

Hai lưu ý quan trọng:

- Nếu T1 **ROLLBACK** thay vì commit, yêu cầu T2 có thể cập nhật thành công vì available vẫn là 1.
- Ở PostgreSQL **REPEATABLE READ** hoặc **SERIALIZABLE**, một xung đột cập nhật kiểu này có thể dẫn đến **serialization failure** thay vì kết quả 0 hàng; ứng dụng phải xử lý lỗi và retry toàn bộ giao dịch khi thích hợp.

Ví dụ chỉ chứng minh đúng cho **một hàng duy nhất và điều kiện được đặt vào UPDATE**. Nếu cả hai giao dịch phải kiểm tra tổng tồn của nhiều kho hàng hoặc nhiều sản phẩm, cần thiết kế đồng thời rộng hơn.

## 7. JDBC: phép trừ an toàn bằng PreparedStatement

Đoạn Java dưới đây dùng một **Connection** và một câu UPDATE. Ở chế độ auto-commit, một câu lệnh thành công sẽ được commit khi hoàn tất; nếu connection đã tham gia giao dịch do tầng trên điều phối, thao tác này là một bước trong giao dịch đó.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class InventoryRepository {
    private final DataSource dataSource;

    public InventoryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean tryDecrease(
            long tenantId, long productId, long quantity
    ) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải > 0");
        }

        String sql = """
            UPDATE inventory
            SET available = available - ?
            WHERE tenant_id = ?
              AND product_id = ?
              AND available >= ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, quantity);
            statement.setLong(2, tenantId);
            statement.setLong(3, productId);
            statement.setLong(4, quantity);

            int rows = statement.executeUpdate();
            if (rows > 1) {
                throw new SQLException(
                        "Số hàng cập nhật vượt quá khóa nghiệp vụ");
            }
            return rows == 1;
        }
    }
}
~~~

Điểm đáng chú ý:

- Dùng **PreparedStatement** để truyền số lượng và định danh; không ghép chuỗi từ dữ liệu người dùng.
- Không có **SELECT available** trước câu trừ: điều kiện và phép trừ cùng nằm trong UPDATE.
- **quantity > 0** được kiểm tra trước; khóa chính hai cột bảo đảm mỗi tổ hợp tenant/sản phẩm chỉ có một hàng.
- **0 hàng** là kết quả nghiệp vụ bình thường, không phải SQLException. Ứng dụng có thể trả thông báo “hết hàng”, nhưng cũng cần phân biệt trường hợp không tồn tại hoặc không có quyền nếu quy tắc an toàn thông tin yêu cầu.
- Đoạn code chỉ an toàn về nguyên tử cho **phép trừ đơn lẻ**. Nó **không** tạo transaction cho các bước tiếp theo như lưu order, ghi reservation hoặc ledger.

Khi dùng connection pool, transaction manager hoặc framework, cần biết ai sở hữu và commit connection. Nếu thao tác đơn lẻ cần tự xác định giao dịch, cấu hình auto-commit phải được quản lý thống nhất. Không tùy tiện gọi **setAutoCommit(true)** ở cuối một DAO được gọi từ giao dịch của lớp service vì có thể commit ngoài ranh giới mong muốn.

### 7.1. Nhận giá trị mới bằng PostgreSQL RETURNING

Nếu cần giá trị tồn kho còn lại ngay sau trừ, dùng một query có RETURNING thay vì UPDATE rồi SELECT tách rời:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE tenant_id = :tenantId
  AND product_id = :productId
  AND available >= :quantity
RETURNING available;
~~~

Trong JDBC với PostgreSQL, có thể gửi câu SQL tương ứng và đọc **ResultSet**. Nếu không có dòng kết quả nghĩa là câu UPDATE không tác động hàng phù hợp. Giá trị RETURNING thuộc trạng thái hiện tại của transaction; giao dịch vẫn có thể rollback sau đó. Cú pháp RETURNING và API liên quan không có mức hỗ trợ giống nhau ở mọi DBMS.

## 8. Khi phải tạo đơn hàng cùng với trừ kho

Giả sử nghiệp vụ “đặt hàng” phải làm hai việc: **trừ số lượng có thể bán** và **tạo bản ghi đơn hàng**. Nếu trừ kho đã auto-commit rồi lệnh INSERT order lỗi, hệ thống có thể mất hàng trong tồn kho mà không có đơn tương ứng. **Tính nguyên tử của UPDATE không thay thế transaction bao quanh toàn bộ nghiệp vụ**.

Một luồng đúng ở mức ranh giới giao dịch:

~~~sql
BEGIN;

UPDATE inventory
SET available = available - 2
WHERE tenant_id = 10
  AND product_id = 1001
  AND available >= 2;
-- Nếu không cập nhật đúng một hàng: ROLLBACK, không INSERT order.

INSERT INTO orders (tenant_id, request_id, product_id, quantity)
VALUES (10, '2e0a716e-6e7a-43c1-860f-19b5bb5e407a', 1001, 2);

COMMIT;
~~~

Đây là **minh họa thuật toán**, không phải một script tự động rẽ nhánh khi UPDATE trả 0 hàng: ứng dụng hoặc stored procedure phải kiểm tra số hàng và ra quyết định commit/rollback. Bảng **orders** giả định tồn tại và cần có lược đồ, khóa ngoại cùng ràng buộc phù hợp.

### 8.1. Ví dụ Spring với một transaction service

Với Spring JDBC và một **PlatformTransactionManager** được cấu hình cho DataSource tương ứng:

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class ReservationService {
    private final JdbcTemplate jdbc;

    public ReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(
            long tenantId, long productId, long quantity, UUID requestId
    ) {
        if (quantity <= 0 || requestId == null) {
            throw new IllegalArgumentException("Đầu vào không hợp lệ");
        }

        int changed = jdbc.update(
                """
                UPDATE inventory
                SET available = available - ?
                WHERE tenant_id = ? AND product_id = ?
                  AND available >= ?
                """,
                quantity, tenantId, productId, quantity);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Sản phẩm không tồn tại hoặc không đủ tồn kho");
        }

        jdbc.update(
                """
                INSERT INTO reservations
                    (tenant_id, request_id, product_id, quantity)
                VALUES (?, ?, ?, ?)
                """,
                tenantId, requestId, productId, quantity);
    }
}
~~~

Phương thức trên minh họa rằng **cả phép trừ và INSERT đều phải tham gia một transaction**. Mặc định Spring rollback với **RuntimeException/Error**, vì vậy lỗi nghiệp vụ và lỗi ràng buộc không bị nuốt sẽ khiến toàn bộ transaction rollback. Cần gọi service qua proxy transaction phù hợp, không qua self-invocation bỏ qua proxy; cũng không mở một connection độc lập ngoài transaction manager bên trong DAO.

Nếu **reservations** có **UNIQUE (tenant_id, request_id)** và yêu cầu bị gửi lại với cùng request ID, INSERT trùng có thể thất bại, khiến phép trừ trước nó được rollback trong transaction mới. Để trả về kết quả “đã xử lý” một cách đúng đắn, ứng dụng cần **đọc và đối chiếu kết quả của request gốc sau khi xử lý lỗi**; không tự động coi mọi lỗi trùng khóa là thành công hoặc coi hai payload khác nhau có cùng request ID là cùng nghiệp vụ.

## 9. Lỗi yêu cầu lặp: tăng nguyên tử không đồng nghĩa đúng một lần

Giả sử ứng dụng gửi:

~~~sql
UPDATE wallets
SET balance = balance - 100
WHERE wallet_id = 22 AND balance >= 100;
~~~

Database thực thi và commit thành công, nhưng mạng bị mất trước khi client nhận phản hồi. Client không thể biết chắc kết quả đã commit hay chưa. Nếu chạy lại y nguyên, thao tác có thể **trừ thêm 100 lần thứ hai**, dù mỗi lần trừ đều nguyên tử.

**Nguyên tử** trả lời “một lần cập nhật có bị chia nhỏ không?”; **idempotency** trả lời “gửi lại cùng một yêu cầu có tạo thêm tác động không?”. Hai vấn đề khác nhau.

Một thiết kế có thể kết hợp:

1. Mỗi yêu cầu nghiệp vụ có **request_id duy nhất và ổn định**.
2. Bảng sổ cái/nhật ký thao tác có ràng buộc **UNIQUE** trên định danh nghiệp vụ thích hợp.
3. Ghi nhận yêu cầu và cập nhật số dư/tồn kho trong **cùng transaction**.
4. Khi request lặp, kiểm tra trạng thái đã lưu và xác minh payload (tài khoản, số tiền, đơn vị tiền, người gửi), rồi trả về kết quả cũ thay vì thực hiện lại.
5. Khi commit không rõ kết quả, **đối soát qua request_id** trước khi quyết định retry.

Với tiền, điểm thưởng hoặc hạn mức, cần dùng kiểu dữ liệu chính xác (**NUMERIC/DECIMAL** với quy tắc làm tròn rõ ràng), ràng buộc hợp lệ và bản ghi lịch sử có thể kiểm toán. Một câu UPDATE đúng về đồng thời không đủ thay thế thiết kế sổ cái.

## 10. Tăng giảm nhiều trường trên cùng một hàng

Khi một thao tác chuyển đơn vị giữa hai bộ đếm nằm **trên cùng hàng**, có thể cập nhật cả hai trong một câu:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity
WHERE tenant_id = :tenantId
  AND product_id = :productId
  AND available >= :quantity;
~~~

Nếu available và reserved lần lượt là **5** và **2**, sau khi giữ chỗ **3** đơn vị, chúng trở thành **2** và **5**. Tổng vẫn là **7** do hai phép thay đổi trong cùng UPDATE. Ràng buộc **NOT NULL**, **CHECK** và khóa chính bảo vệ mô hình ngay cả khi chương trình khác truy cập bảng.

Để **hủy giữ chỗ**, thao tác ngược cũng cần điều kiện:

~~~sql
UPDATE inventory
SET reserved = reserved - :quantity,
    available = available + :quantity
WHERE tenant_id = :tenantId
  AND product_id = :productId
  AND reserved >= :quantity;
~~~

Nếu phải đồng thời cập nhật **hai hàng khác nhau** (chuyển tiền giữa hai ví, chuyển hàng giữa hai kho), một câu SQL đơn lẻ có thể không biểu diễn được quy tắc nghiệp vụ một cách đơn giản. Khi ấy hãy dùng **transaction**, khóa/ràng buộc phù hợp và xác minh kết quả từng bước.

## 11. Dùng UPSERT để tạo mới hoặc tăng bộ đếm

Một trường hợp phổ biến là bộ đếm được lưu theo ngày và tenant; lúc đầu chưa có hàng để UPDATE. Mẫu nguy hiểm:

~~~text
SELECT daily_counter WHERE tenant_id = 10 AND day = hôm nay
Nếu không tồn tại -> INSERT (hits = 1)
Nếu tồn tại      -> UPDATE (hits = hits + 1)
~~~

Hai yêu cầu có thể cùng thấy “chưa tồn tại” rồi cùng INSERT. Với PostgreSQL, một cách an toàn hơn cho **một bộ đếm theo khóa duy nhất** là dùng **INSERT ... ON CONFLICT DO UPDATE**:

~~~sql
CREATE TABLE daily_counters (
    tenant_id BIGINT NOT NULL,
    counter_date DATE NOT NULL,
    hits BIGINT NOT NULL DEFAULT 0 CHECK (hits >= 0),
    PRIMARY KEY (tenant_id, counter_date)
);

INSERT INTO daily_counters(tenant_id, counter_date, hits)
VALUES (10, DATE '2026-11-22', 1)
ON CONFLICT (tenant_id, counter_date)
DO UPDATE
SET hits = daily_counters.hits + EXCLUDED.hits
RETURNING hits;
~~~

**PRIMARY KEY** quyết định hàng nào đại diện một bộ đếm; chỉ mục duy nhất giúp hai thao tác cùng khóa không tạo hai hàng trùng. Nhánh UPDATE tính từ giá trị hiện hành của hàng đã có, thay vì viết đè một giá trị client tính trước. **EXCLUDED.hits** trong PostgreSQL chỉ giá trị được đề xuất INSERT. Một lần gửi thành công tạo bộ đếm mới ở 1 hoặc tăng bộ đếm cũ thêm 1.

Tương tự phép UPDATE thông thường, **UPSERT không tự chống việc gửi lại cùng một sự kiện**. Nếu một sự kiện phải được tính đúng một lần, cần có **event_id** hoặc sổ sự kiện với ràng buộc duy nhất, rồi cập nhật số đếm trong transaction tương ứng.

## 12. Atomic UPDATE, khóa và các mức cô lập

Trong hệ cơ sở dữ liệu hỗ trợ giao dịch, UPDATE một hàng phải phối hợp với transaction khác đang ghi vào cùng hàng. Tuy nhiên, **cách xử lý khi chờ và khi phát hiện xung đột có thể khác theo isolation**.

| Tình huống | Hành vi thường gặp trong PostgreSQL |
| --- | --- |
| Hai UPDATE tăng cùng hàng tại **READ COMMITTED** | Một thao tác có thể chờ thao tác còn lại; mỗi lần tăng đã commit được áp dụng, không tự ghi đè delta |
| Hai UPDATE có điều kiện **available >= 1** tại READ COMMITTED | Sau khi chờ, điều kiện có thể được xét lại trên phiên bản mới; yêu cầu thứ hai có thể cập nhật 0 hàng |
| Hai transaction tại **REPEATABLE READ** cùng sửa hàng sau khi snapshot được xác lập | Một transaction có thể bị lỗi serialization khi hàng đã bị giao dịch khác cập nhật |
| UPDATE một hàng trong transaction nhiều câu lệnh | Khóa có thể giữ tới commit/rollback; transaction dài làm tăng thời gian chờ |
| UPDATE ảnh hưởng nhiều hàng với thứ tự khóa khác nhau | Có thể hình thành deadlock; DB có thể hủy một transaction |

Không nên kết luận rằng **READ COMMITTED luôn tránh mọi lost update**. Nếu mã Java đọc **value = 5** rồi UPDATE **SET value = 6**, hệ quản trị vẫn có thể chấp nhận một bản ghi đè không mong muốn. Bảo đảm mong muốn đến từ **cách viết biểu thức UPDATE** và các ràng buộc đi kèm.

Nếu cần tính toán phức tạp phải thực hiện ở Java, có thể cân nhắc:

- **SELECT ... FOR UPDATE** trong một transaction để khóa hàng trước khi đọc và quyết định. Cách này giữ khóa trong khi tính toán, làm tăng thời gian chờ; luôn giữ transaction ngắn.
- **Optimistic locking** bằng trường **version** và UPDATE có điều kiện so khớp version; khi không cập nhật được hàng, đọc lại dữ liệu và quyết định retry.
- **SERIALIZABLE** cho quy tắc cần kết quả tương đương một lịch giao dịch chạy tuần tự; xử lý lỗi **SQLSTATE 40001** bằng retry toàn bộ transaction phù hợp.

Ví dụ kiểm soát phiên bản lạc quan:

~~~sql
UPDATE accounts
SET display_name = :newName,
    version = version + 1
WHERE account_id = :accountId
  AND version = :expectedVersion;
~~~

Nếu UPDATE trả **0 hàng**, bản ghi đã được sửa hoặc không tồn tại. Đây là cơ chế riêng cho việc **ghi đè có chủ đích từ một bản đọc trước**, không cần thay thế câu **SET counter = counter + 1** vốn đã phù hợp với bộ đếm đơn giản.

## 13. Những bất biến mà một câu tăng giảm không bảo vệ được

Các mẫu SQL trong bài đặc biệt phù hợp với quy tắc có thể kiểm tra trên **một hàng**. Nhưng nhiều nghiệp vụ liên quan đồng thời nhiều đối tượng:

| Bất biến | Vì sao một UPDATE đơn giản chưa đủ? | Hướng thiết kế |
| --- | --- | --- |
| Tổng số tiền của hai tài khoản không đổi khi chuyển | Trừ và cộng hai hàng riêng | Transaction cho cả hai UPDATE; kiểm tra đủ số dư và ghi lịch sử |
| Một ca trực luôn có ít nhất một bác sĩ | Hai người có thể đọc cùng tập hàng rồi sửa các hàng khác nhau | Transaction SERIALIZABLE hoặc khóa một tài nguyên chung; bảo vệ quy tắc xuyên hàng |
| Một đơn hàng chỉ tạo đúng một lần | Client có thể gửi lại thao tác sau timeout | Request ID, unique constraint, trạng thái/idempotency |
| Tồn kho ở nhiều kho cộng lại không âm | Điều kiện chỉ trên một hàng không kiểm tra tổng tồn/đặt hàng nhiều kho | Thiết kế phân bổ, transaction và kiểm soát đồng thời xuyên hàng |
| Cập nhật DB đồng thời gửi message | DB commit không thể hoàn tác việc đã gửi bên ngoài | Transactional outbox và consumer idempotent |

**Atomicity của một phép toán không tự động truyền sang toàn bộ luồng nghiệp vụ**. Chọn biên đúng trước, rồi quyết định phần nào đặt trong một câu SQL, phần nào buộc phải chung transaction và phần nào cần phối hợp hệ thống.

## 14. Số học và ràng buộc dữ liệu

Ngay cả khi tránh được lost update, dữ liệu vẫn có thể sai vì toán học hoặc kiểu dữ liệu:

**Giá trị NULL.** Trong SQL, **NULL + 1** cho ra **NULL**. Nếu bộ đếm luôn phải có số, định nghĩa **NOT NULL DEFAULT 0** và làm sạch dữ liệu cũ. Dùng **COALESCE(counter, 0) + 1** chỉ khi mô hình chấp nhận cách diễn giải NULL thành 0.

**Giá trị âm.** Phép **available = available - :n** phải đi kèm **available >= :n** khi không cho âm; **:n** phải dương. Đặt **CHECK (available >= 0)** làm lớp phòng vệ ở DB. Không trông chờ ứng dụng web là nơi duy nhất chặn đầu vào sai.

**Tràn số.** Kiểu **INTEGER/BIGINT** có phạm vi hữu hạn. PostgreSQL báo lỗi khi phép toán số nguyên vượt phạm vi; DBMS/kiểu dữ liệu khác có thể có quy tắc khác. Chọn kiểu và ngưỡng cảnh báo theo quy mô dự kiến, không để bộ đếm vượt trần trong âm thầm.

**Số tiền.** Tránh dùng **float/double** để lưu số tiền cần chính xác. Dùng **NUMERIC/DECIMAL** hoặc đơn vị nhỏ nhất bằng số nguyên, thống nhất làm tròn và kiểm tra phạm vi. Các phép cập nhật có điều kiện **balance >= amount** chỉ đúng khi hai vế cùng đơn vị.

**Không có hàng.** **UPDATE ... WHERE id = ?** có thể trả 0 nếu hàng không tồn tại; tăng nguyên tử không tự tạo bản ghi. Cần lược đồ/ràng buộc và quyết định liệu đây là lỗi, thao tác bỏ qua hay trường hợp dùng UPSERT.

## 15. Hiệu năng: hàng nóng và lựa chọn thiết kế bộ đếm

Phép tăng/giảm trên một hàng đảm bảo đúng về mặt cập nhật nhưng có thể trở thành **điểm tranh chấp** khi rất nhiều yêu cầu cùng cập nhật **chính một hàng**. Ví dụ một bài viết có hàng trăm nghìn lượt xem mỗi giây, mọi UPDATE vào hàng **article_stats(article_id=42)** phải điều phối ghi trên cùng tài nguyên.

Một số lựa chọn khi cần mở rộng:

1. **Giữ một hàng duy nhất** nếu tần suất cập nhật thấp hoặc vừa, tính chính xác thời gian thực quan trọng và độ trễ đo được đạt yêu cầu. Đây thường là lựa chọn đơn giản và dễ kiểm chứng.
2. **Gộp sự kiện theo lô**: tích lũy số lần tăng trong hàng đợi hoặc tiến trình xử lý, rồi UPDATE **counter = counter + batch_delta**. Giảm số lần ghi nhưng thay đổi yêu cầu độ trễ/độ bền.
3. **Chia bộ đếm thành nhiều shard**: mỗi yêu cầu chọn một shard, cập nhật hàng của shard; phép đọc tổng cần cộng các shard. Cần quy tắc phân bổ, chấp nhận chi phí đọc và bảo vệ chính xác khi shard được thay đổi.
4. **Dùng kho sự kiện làm nguồn sự thật** nếu cần đối soát đúng từng sự kiện, còn bảng counter là projection được cập nhật từ sự kiện; khi xử lý lại cần cơ chế chống trùng.
5. **Cân nhắc bộ đếm ở Redis hoặc hệ key-value** khi tính chất tải phù hợp, nhưng phải xác định bảo đảm độ bền, replication, mất kết nối và chiến lược đồng bộ với DB nguồn.

Không tối ưu bằng sharding/batching trước khi đo **tần suất cập nhật, lock wait, thời gian commit, băng thông WAL, pool pressure và mức độ chính xác nghiệp vụ cần có**. Sharding có thể làm giảm tranh chấp tại một hàng nhưng đồng thời tăng độ phức tạp, chi phí truy vấn tổng và khả năng nhận giá trị trễ.

## 16. Redis INCRBY có nghĩa gì với thao tác nguyên tử?

Redis cung cấp các lệnh như **INCR**, **DECR**, **INCRBY** để cập nhật giá trị số của một key theo cách nguyên tử trong phạm vi thực thi lệnh trên một Redis instance:

~~~text
INCR article:42:views
INCRBY article:42:views 10
DECR article:42:views
~~~

Hai client gửi **INCR** đến cùng một key không thực hiện kiểu đọc giá trị cũ ở Java rồi SET đè. Tuy nhiên, không được suy ra từ “lệnh nguyên tử” rằng hệ thống đã có mọi tính chất của giao dịch SQL:

- **INCRBY** chỉ xử lý số của một key trong phạm vi lệnh; thay đổi nhiều key cùng điều kiện nghiệp vụ đòi hỏi cơ chế điều phối bổ sung (ví dụ script chạy nguyên tử trên Redis phù hợp với mô hình triển khai).
- Tính bền vững khi Redis crash hoặc chuyển vai trò phụ thuộc cấu hình persistence và replication; một phản hồi thành công không tự đảm bảo độ bền tương đương một giao dịch DB đã được cấu hình phù hợp.
- Khi client timeout, retry một lệnh INCR có thể tăng lần nữa; vấn đề **idempotency** vẫn hiện diện.
- Redis Cluster có hạn chế khi chạy thao tác/script nhiều key ở các hash slot khác nhau; thiết kế phải tuân mô hình phân mảnh thực tế.

Với ứng dụng có PostgreSQL làm nguồn dữ liệu chính nhưng dùng Redis làm cache, cần định nghĩa **nguồn sự thật** và chính sách cập nhật/invalidate cache. Nếu DB và Redis đều được tăng riêng lẻ, hai phép tăng không tạo ra một giao dịch ACID xuyên hệ thống.

## 17. Thử nghiệm cạnh tranh và điều cần quan sát

Có thể kiểm tra thao tác nguyên tử với hai kết nối SQL như phần 6. Khi viết kiểm thử tích hợp chạy nhiều request, hãy tập trung vào **bất biến**, không chỉ xác nhận câu lệnh không ném exception.

Một kịch bản kiểm thử cho bộ đếm:

~~~text
Khởi tạo counter = 0
Chạy đồng thời N yêu cầu, mỗi yêu cầu UPDATE counter = counter + 1
Chờ tất cả yêu cầu kết thúc và xác nhận đã commit thành công
Đọc counter từ DB primary
Kỳ vọng: counter = số yêu cầu đã commit thành công
~~~

Nếu có retry hoặc timeout, phải phân biệt **số lời gọi client** với **số thao tác nghiệp vụ duy nhất đã commit**. Đọc lại từ replica có thể chưa thấy commit mới nhất do replication lag; kiểm chứng correctness nên dùng đường đọc có mức nhất quán thích hợp.

Một kịch bản kiểm thử tồn kho:

~~~text
Khởi tạo available = 1
Cho 2 request cùng trừ quantity = 1
Kỳ vọng:
  - Đúng 1 request cập nhật được 1 hàng và commit
  - Request còn lại cập nhật 0 hàng hoặc bị lỗi cần xử lý theo isolation
  - available cuối = 0, không âm
~~~

Nếu dùng Spring/JDBC, cần kiểm tra các request thật sự chạy trên các connection độc lập và giao dịch có ranh giới đúng. Không dùng một connection JDBC chung cho nhiều thread; API Connection không phải một transaction context chia sẻ an toàn cho tất cả luồng. Dùng môi trường test riêng có dữ liệu xác định, không mô phỏng cạnh tranh bằng việc gọi tuần tự hai method trên cùng thread.

Các tín hiệu nên xem khi chạy tải:

- **Tỷ lệ UPDATE trả 0 hàng** do hết tồn kho, không phải lỗi kỹ thuật.
- **Lock wait / deadlock / timeout** khi nhiều transaction chạm vào cùng hàng.
- **SQLSTATE 40001, 40P01** ở PostgreSQL khi cần retry giao dịch theo chính sách.
- **Độ trễ phân vị cao (p95/p99)** khi có nhiều yêu cầu cùng ghi một hàng.
- **Số lần thực thi lại**, định danh yêu cầu và kết quả đối soát sau khi mạng lỗi.

## 18. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| SELECT rồi ghi **SET counter = newValue** | Dễ mất phép tăng khi nhiều client đọc cùng giá trị cũ | Viết **SET counter = counter + delta** |
| Kiểm tra **stock >= quantity** bằng SELECT rồi mới trừ | Hai client có thể đều thấy đủ hàng | Đưa điều kiện vào **WHERE** của UPDATE |
| Không kiểm tra số hàng cập nhật | Có thể xác nhận đơn hàng dù không trừ được tồn kho | Kiểm tra **rows == 1**, xử lý 0 hàng như một nhánh nghiệp vụ |
| Chỉ cập nhật stock rồi INSERT order ngoài transaction | Lỗi INSERT có thể làm tồn kho giảm không có đơn | Bao tất cả bước bắt buộc trong cùng giao dịch |
| Xem câu UPDATE thành công là đã commit | Giao dịch cha có thể rollback | Phân biệt kết quả câu lệnh và commit của transaction |
| Retry phép trừ/tăng sau timeout không có request ID | Có thể tạo tác động hai lần | Idempotency key, unique constraint, đối soát kết quả |
| Cho phép quantity âm hoặc NULL | Có thể tăng hàng sai chiều hoặc tính toán thành NULL | Xác thực đầu vào, NOT NULL và CHECK ở DB |
| Dùng UPDATE nguyên tử để bảo vệ quy tắc xuyên nhiều hàng | Có thể vẫn gặp write skew hoặc bất nhất liên bảng | Transaction, ràng buộc, khóa hoặc SERIALIZABLE phù hợp |
| Dồn mọi lượt truy cập vào một hàng duy nhất ở tải cực lớn | Một hàng trở thành điểm nghẽn khóa/ghi | Đo tải, cân nhắc batching hoặc sharded counters |
| Cho rằng DB và Redis tăng cùng nhau là một giao dịch | Cache và nguồn dữ liệu có thể lệch | Chọn nguồn sự thật, cơ chế đồng bộ và idempotency |

## 19. Bài tập vận dụng

**Bài 1 — Lost update.** Bộ đếm đang là **8**. Hai thread đọc cùng 8 và đều gọi UPDATE để đặt giá trị 9. Kết quả có thể là gì? Thay bằng câu SQL nào để bảo đảm hai lần tăng đều được tính nếu cả hai commit?

**Gợi ý:** Có thể là **9**, mất một lần tăng. Thay bằng **UPDATE counters SET value = value + 1 WHERE id = ?**. Khi hai lần cập nhật đều commit, kết quả là **10**.

**Bài 2 — Hết hàng.** Một sản phẩm còn **1** đơn vị, hai request cùng đặt mua **1**. Vì sao truy vấn **SELECT available** rồi **UPDATE available = available - 1** không đủ? Hãy viết một câu UPDATE phù hợp.

**Gợi ý:** Giá trị đọc có thể lỗi thời trước lúc ghi. Dùng **UPDATE inventory SET available = available - 1 WHERE tenant_id = ? AND product_id = ? AND available >= 1**; kiểm tra số hàng được cập nhật.

**Bài 3 — Hai hàng.** Một ứng dụng trừ 50 điểm từ ví A rồi cộng 50 điểm cho ví B bằng hai câu UPDATE nguyên tử. Nếu câu thứ hai lỗi, vì sao dữ liệu vẫn có thể sai và cần làm gì?

**Gợi ý:** Hai câu UPDATE là hai bước riêng; nếu auto-commit, bước đầu có thể đã commit. Phải đặt cả hai trong cùng một transaction, xác thực kết quả và rollback khi lỗi.

**Bài 4 — Retry.** Client gửi lệnh trừ 100 rồi mất kết nối trong lúc chờ kết quả commit. Có nên gửi lại ngay không?

**Gợi ý:** Không được mặc định lần trước chưa commit. Dùng **request_id** duy nhất, unique constraint, trạng thái nghiệp vụ và cơ chế đối soát trước retry.

**Bài 5 — Tồn kho được giữ chỗ.** Bảng có hai cột **available = 6**, **reserved = 2**. Viết UPDATE giữ chỗ 3 đơn vị sao cho tổng không đổi và không cho available âm.

**Gợi ý:**

~~~sql
UPDATE inventory
SET available = available - 3,
    reserved = reserved + 3
WHERE tenant_id = 10
  AND product_id = 1001
  AND available >= 3;
~~~

Nếu cập nhật được một hàng, hai giá trị lần lượt là **3** và **5**. Nếu không đủ hàng thì UPDATE 0 hàng.

**Bài 6 — Điều kiện phức tạp.** Doanh nghiệp quy định tổng giá trị đang giữ chỗ trên **nhiều kho** không vượt hạn mức của khách hàng. Một UPDATE tồn kho tại một kho có đủ để bảo đảm quy tắc không?

**Gợi ý:** Chưa đủ vì bất biến liên quan nhiều hàng hoặc bảng. Xác định transaction boundary, chọn dữ liệu/khóa chung hoặc mức cô lập phù hợp, dùng ràng buộc có thể thực thi và kiểm tra dưới tải đồng thời.

## 20. Ghi nhớ khi thiết kế persistence

Khi thay đổi một giá trị số trong hệ lưu trữ, hãy ưu tiên **thực hiện phép tăng/giảm ngay tại nơi lưu trữ**, thay cho đọc về Java rồi ghi lại giá trị đã tính từ bản đọc cũ. Với giảm có giới hạn, ghép **điều kiện và phép trừ trong cùng UPDATE**, đồng thời **kiểm tra số hàng bị ảnh hưởng**. Đây là một kỹ thuật cốt lõi để tránh lost update và overselling trên một hàng.

Tuy nhiên, hãy luôn xác định rõ **phạm vi nguyên tử**: một câu UPDATE, một transaction nhiều câu lệnh hay một luồng nghiệp vụ trải qua nhiều hệ thống. Kết hợp SQL nguyên tử với **ràng buộc DB, transaction, isolation, xử lý lỗi kết nối và idempotency** phù hợp. Sau khi bảo đảm đúng dữ liệu, mới đo tranh chấp khóa, hàng nóng và chi phí ghi để quyết định có cần batching, sharding hoặc kiến trúc bộ đếm khác.
