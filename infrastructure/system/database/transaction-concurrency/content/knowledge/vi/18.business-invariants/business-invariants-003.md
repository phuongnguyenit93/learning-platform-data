# Trừ tồn kho bằng UPDATE có điều kiện để tránh bán vượt số lượng

Khi nhiều khách hàng cùng đặt một sản phẩm, ứng dụng phải bảo đảm số lượng đã bán hoặc đã giữ chỗ không vượt lượng hàng có thể cung cấp. Một cách dễ mắc lỗi là đọc tồn kho trước, kiểm tra ở tầng ứng dụng rồi mới gửi UPDATE. Hai yêu cầu đồng thời có thể cùng đọc một số lượng cũ và cùng cho rằng đơn hàng của mình hợp lệ.

Cách đơn giản và chắc chắn hơn cho một hàng tồn kho là đưa điều kiện kiểm tra vào chính câu UPDATE: chỉ trừ số lượng nếu tồn kho hiện tại vẫn đủ. Việc kiểm tra và thay đổi được cơ sở dữ liệu thực hiện như một thao tác ghi nguyên tử trên cùng hàng.

## 1. Vì sao đọc trước rồi mới trừ có thể bán vượt tồn kho?

Giả sử sản phẩm P có 10 đơn vị còn khả dụng. Hai khách hàng cùng đặt 7 đơn vị.

Một luồng ứng dụng thường được viết như sau:

1. SELECT số lượng tồn kho.
2. So sánh số lượng đọc được với số lượng khách muốn mua.
3. Nếu đủ, tính số lượng mới trong ứng dụng.
4. UPDATE tồn kho bằng giá trị mới đã tính.
5. Tạo đơn hàng.

Nếu T1 và T2 cùng đọc trước khi một transaction ghi xong, cả hai đều thấy 10. Mỗi giao dịch kết luận rằng 7 đơn vị có thể được bán.

| Thời điểm | T1 | T2 | Tồn kho đã commit |
|---|---|---|---:|
| 1 | Đọc tồn kho = 10 | | 10 |
| 2 | | Đọc tồn kho = 10 | 10 |
| 3 | Tính 10 - 7 = 3 | | 10 |
| 4 | | Tính 10 - 7 = 3 | 10 |
| 5 | Ghi giá trị 3 và commit | | 3 |
| 6 | | Ghi giá trị 3 và commit | 3 |

Ví dụ trên có thể gây mất cập nhật: cả hai đơn hàng được chấp nhận nhưng tồn kho chỉ giảm một lần. Nếu cách triển khai dùng phép trừ riêng nhưng vẫn kiểm tra bằng dữ liệu đã đọc cũ, kết quả còn có thể làm số lượng âm. Nguyên nhân chung là bước kiểm tra và bước thay đổi không được phối hợp nguyên tử.

Không nên xem một lần SELECT thành công là quyền giữ trước số hàng đã đọc. Dữ liệu có thể thay đổi ngay sau khi câu SELECT kết thúc.

## 2. Đưa điều kiện vào cùng câu UPDATE

Giả sử bảng tồn kho lưu số lượng còn khả dụng:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available_qty BIGINT NOT NULL,
    CONSTRAINT ck_inventory_nonnegative
        CHECK (available_qty >= 0)
);
~~~

Câu lệnh trừ tồn kho có điều kiện:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :requested_qty
WHERE product_id = :product_id
  AND :requested_qty > 0
  AND available_qty >= :requested_qty;
~~~

Các điều kiện có ý nghĩa:

- product_id = :product_id: chỉ cập nhật đúng sản phẩm cần đặt. Khóa chính bảo đảm tối đa một hàng được khớp.
- :requested_qty > 0: không cho phép số lượng đặt bằng 0 hoặc âm. Ứng dụng vẫn nên kiểm tra đầu vào trước khi gửi SQL.
- available_qty >= :requested_qty: chỉ trừ nếu lượng hiện có đủ.
- available_qty = available_qty - :requested_qty: phép trừ được thực hiện trên giá trị của hàng tại thời điểm hệ quản trị xử lý thao tác ghi.

Nếu có 10 đơn vị và hai transaction cùng yêu cầu trừ 7, một transaction có thể cập nhật hàng trước. Sau khi nó commit, transaction còn lại phải xử lý trên trạng thái hàng đã thay đổi hoặc nhận lỗi xung đột theo isolation level. Điều kiện available_qty >= 7 không còn đúng, nên lần cập nhật thứ hai không thành công.

Kết quả mong muốn:

| Transaction | Số lượng yêu cầu | Kết quả UPDATE | Tồn kho sau thao tác |
|---|---:|---|---:|
| T1 | 7 | Cập nhật 1 hàng | 3 |
| T2 | 7 | Cập nhật 0 hàng hoặc bị lỗi xung đột cần xử lý | 3 |

Không có thời điểm nào mà hai đơn cùng được chấp nhận để bán tổng cộng 14 đơn vị từ kho chỉ có 10 đơn vị.

Đây là một thao tác ghi có điều kiện (*conditional update*). Kiểm tra điều kiện và phép trừ nằm trong cùng một câu lệnh, nên ứng dụng không tạo ra khoảng thời gian giữa SELECT và UPDATE để một yêu cầu khác chen vào dựa trên cùng số lượng cũ.

## 3. Hiểu kết quả số hàng được cập nhật

Sau khi chạy câu UPDATE, ứng dụng cần kiểm tra số hàng bị tác động.

| Số hàng được cập nhật | Diễn giải |
|---:|---|
| 1 | Sản phẩm tồn tại, số lượng yêu cầu hợp lệ và đủ tồn kho; thao tác trừ thành công |
| 0 | Không có hàng thỏa toàn bộ điều kiện: sản phẩm không tồn tại, không đủ tồn kho hoặc điều kiện trạng thái không hợp lệ |
| Lớn hơn 1 | Thiết kế khóa sản phẩm hoặc điều kiện truy vấn có vấn đề; với product_id là primary key thì kết quả này không nên xảy ra |

Một kết quả 0 hàng thường là kết quả nghiệp vụ bình thường: không thể giữ đủ hàng cho yêu cầu hiện tại. Ứng dụng có thể trả thông báo hết hàng hoặc không đủ số lượng.

Nếu cần phân biệt sản phẩm không tồn tại với sản phẩm tồn tại nhưng thiếu hàng, ứng dụng có thể đọc trạng thái sau khi UPDATE không thành công. Việc đọc thêm chỉ phục vụ thông báo hoặc chẩn đoán; không được dùng kết quả đó để quay lại quyết định trừ tồn kho theo cách không nguyên tử.

Ở một số hệ quản trị, có thể dùng RETURNING hoặc OUTPUT để nhận lại hàng đã được cập nhật:

~~~sql
-- PostgreSQL
UPDATE inventory
SET available_qty = available_qty - 3
WHERE product_id = 42
  AND available_qty >= 3
RETURNING product_id, available_qty;
~~~

~~~sql
-- SQL Server
UPDATE dbo.Inventory
SET AvailableQty = AvailableQty - 3
OUTPUT inserted.ProductId, inserted.AvailableQty
WHERE ProductId = 42
  AND AvailableQty >= 3;
~~~

Cú pháp trả về dữ liệu sau UPDATE khác nhau theo hệ quản trị. Với JDBC, executeUpdate() thường trả số hàng bị cập nhật; nếu cần lấy giá trị sau cập nhật, dùng API/cú pháp được driver và database hỗ trợ.

## 4. Ví dụ Java JDBC

Với JDBC, dấu hỏi ? là placeholder cho tham số. Ta có thể dùng một câu lệnh duy nhất để kiểm tra và trừ tồn kho:

~~~java
private static final String DECREMENT_STOCK = """
    UPDATE inventory
    SET available_qty = available_qty - ?
    WHERE product_id = ?
      AND ? > 0
      AND available_qty >= ?
    """;

static boolean reserveStock(
        Connection connection,
        long productId,
        long requestedQty) throws SQLException {

    if (requestedQty <= 0) {
        throw new IllegalArgumentException(
            "Số lượng đặt phải lớn hơn 0"
        );
    }

    try (PreparedStatement statement =
             connection.prepareStatement(DECREMENT_STOCK)) {

        statement.setLong(1, requestedQty);
        statement.setLong(2, productId);
        statement.setLong(3, requestedQty);
        statement.setLong(4, requestedQty);

        int updatedRows = statement.executeUpdate();

        if (updatedRows == 1) {
            return true;
        }

        if (updatedRows == 0) {
            return false;
        }

        throw new SQLException(
            "Số hàng tồn kho được cập nhật không hợp lệ: "
                + updatedRows
        );
    }
}
~~~

Hàm này trả về true khi đã giữ được số lượng yêu cầu, false khi điều kiện không thỏa. Nó không tự commit vì quyền quyết định transaction thuộc về luồng nghiệp vụ gọi nó.

Sử dụng PreparedStatement giúp truyền tham số đúng kiểu và tránh ghép dữ liệu đầu vào trực tiếp vào chuỗi SQL. Kiểm tra requestedQty > 0 ở Java làm rõ lỗi đầu vào; điều kiện trong SQL là lớp bảo vệ bổ sung nếu có một đường gọi khác bỏ qua validation.

Nếu dùng kiểu số có giới hạn, hãy chọn kiểu dữ liệu đủ lớn cho số lượng và kiểm soát giới hạn nghiệp vụ. Không để phép tính tràn số hoặc chuyển kiểu ngoài dự kiến.

## 5. Đặt thao tác trừ kho và tạo đơn trong cùng transaction

Trừ tồn kho thành công nhưng tạo đơn thất bại sẽ làm số lượng bị giữ mà không có đơn tương ứng nếu hai thao tác không cùng transaction.

Một luồng tạo đơn đơn giản:

~~~sql
BEGIN;

UPDATE inventory
SET available_qty = available_qty - 2
WHERE product_id = 42
  AND available_qty >= 2;

-- Ứng dụng kiểm tra UPDATE có tác động đúng 1 hàng.
-- Nếu không, ROLLBACK và trả kết quả không đủ hàng.

INSERT INTO orders (order_id, customer_id, status)
VALUES (9001, 77, 'PENDING');

INSERT INTO order_item (order_id, product_id, quantity)
VALUES (9001, 42, 2);

COMMIT;
~~~

Các bước cần được thực hiện trong cùng transaction:

1. Kiểm tra đầu vào và xác định sản phẩm/số lượng cần giữ.
2. Chạy UPDATE có điều kiện để trừ hoặc giữ hàng.
3. Nếu số hàng cập nhật không bằng 1, rollback toàn bộ transaction.
4. Tạo đơn và các dòng chi tiết.
5. Commit khi tất cả thao tác thành công.

Nếu INSERT đơn hàng hoặc một dòng chi tiết thất bại, rollback sẽ hoàn tác cả phần trừ tồn kho. Nếu transaction commit, đơn hàng và số lượng tồn kho cùng được ghi nhận.

Trong code JDBC, ranh giới transaction có thể được triển khai như sau:

~~~java
static long createOrder(
        DataSource dataSource,
        long customerId,
        long productId,
        long quantity) throws SQLException {

    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "Số lượng phải lớn hơn 0"
        );
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            if (!reserveStock(connection, productId, quantity)) {
                throw new InsufficientStockException(productId);
            }

            long orderId = insertOrder(connection, customerId);
            insertOrderItem(connection, orderId, productId, quantity);

            connection.commit();
            return orderId;
        } catch (SQLException | RuntimeException error) {
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

Các hàm insertOrder và insertOrderItem là phần triển khai theo schema của ứng dụng. Điểm quan trọng là chúng dùng cùng connection và transaction với reserveStock.

Trong ví dụ, InsufficientStockException là lỗi nghiệp vụ riêng của ứng dụng. Khi triển khai thực tế, hãy bảo đảm rollback được gọi cho cả lỗi nghiệp vụ lẫn lỗi SQL. Nếu exception được ném sau khi rollback đã hoàn tất, lớp gọi có thể chuyển nó thành phản hồi “không đủ hàng”.

## 6. Không dùng SELECT tồn kho làm quyết định cuối cùng

Ứng dụng vẫn có thể SELECT tồn kho để hiển thị số lượng dự kiến cho người dùng, nhưng kết quả đó chỉ là thông tin tại thời điểm đọc.

Ví dụ:

~~~sql
SELECT available_qty
FROM inventory
WHERE product_id = 42;
~~~

Con số trả về có thể thay đổi trước khi khách nhấn nút đặt hàng. Khi người dùng gửi yêu cầu, câu UPDATE có điều kiện mới là bước quyết định có thể giữ hàng hay không.

Một giao diện có thể hiển thị “còn 5 sản phẩm” rồi yêu cầu đặt 3 sản phẩm, nhưng nếu một khách hàng khác đã giữ 4 sản phẩm trước đó, UPDATE có điều kiện sẽ không cho phép trừ thêm 3.

Điều này không có nghĩa phải bỏ mọi truy vấn đọc tồn kho. Nó có nghĩa không được dựa vào một lần đọc cũ để ghi giá trị tuyệt đối hoặc cho phép bán hàng mà không kiểm tra lại nguyên tử ở bước ghi.

## 7. Khác biệt khi nhiều hệ quản trị xử lý UPDATE đồng thời

Các hệ quản trị có thể dùng locking hoặc MVCC theo cách khác nhau, nhưng câu UPDATE có điều kiện vẫn là mẫu phù hợp để bảo vệ một bất biến trên cùng hàng.

| Hệ quản trị | Hành vi liên quan |
|---|---|
| PostgreSQL | UPDATE lấy khóa ghi trên hàng. Ở READ COMMITTED, nếu phải chờ một UPDATE cạnh tranh, hệ thống có thể kiểm tra lại điều kiện trên phiên bản hàng mới nhất; nếu điều kiện không còn đúng, hàng không được cập nhật. Ở REPEATABLE READ hoặc SERIALIZABLE, xung đột có thể làm transaction nhận lỗi serialization. |
| MySQL InnoDB | UPDATE là thao tác ghi và dùng khóa trên các bản ghi phù hợp. Các transaction cạnh tranh trên cùng hàng được điều phối; điều kiện và phép trừ được thực hiện trong câu lệnh. Phạm vi khóa còn phụ thuộc chỉ mục và isolation level. |
| SQL Server | UPDATE lấy các khóa cần thiết cho thao tác ghi. Với locking READ COMMITTED, các yêu cầu ghi cạnh tranh trên cùng hàng được điều phối. Khi dùng row versioning cho đọc, thao tác UPDATE vẫn cần bảo vệ dữ liệu ghi. |

Đừng dựa vào giả định rằng mọi engine đều trả cùng một loại lỗi cho mọi lịch chạy cạnh tranh. Với isolation level cao hơn, một transaction có thể bị hủy do serialization conflict thay vì đơn giản nhận kết quả 0 hàng. Ứng dụng phải xử lý cả kết quả nghiệp vụ và lỗi đồng thời theo driver/database đang dùng.

Điểm cốt lõi của mẫu này là phép kiểm tra available_qty >= requested_qty nằm trong cùng câu lệnh với phép trừ. Nếu transaction bị hủy bởi deadlock hoặc serialization failure, phải rollback và thử lại toàn bộ transaction trong một transaction mới; không dùng lại quyết định từ lần đọc cũ.

## 8. Ràng buộc CHECK là lớp bảo vệ bổ sung

Bảng tồn kho nên có ràng buộc không cho số lượng âm:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_nonnegative
CHECK (available_qty >= 0);
~~~

Ràng buộc này bảo vệ dữ liệu ngay tại database, kể cả khi một đường ghi khác quên điều kiện trong câu UPDATE.

Tuy nhiên, CHECK không thay thế câu UPDATE có điều kiện:

- CHECK (available_qty >= 0) ngăn giá trị âm được lưu.
- WHERE available_qty >= requested_qty xác định liệu yêu cầu hiện tại có thể được chấp nhận hay không.
- SET available_qty = available_qty - requested_qty thực hiện thay đổi nguyên tử.

Nếu câu UPDATE thiếu điều kiện, constraint có thể làm câu lệnh thất bại khi phép trừ tạo số âm. Điều đó bảo vệ dữ liệu, nhưng ứng dụng cần xử lý lỗi constraint như một kết quả không đủ hàng. Câu UPDATE có điều kiện thường cho phép xử lý rõ ràng hơn bằng số hàng được cập nhật.

Nên kết hợp cả hai để có lớp kiểm tra ở câu lệnh và lớp bảo vệ ở schema. Đồng thời dùng NOT NULL để tránh giá trị NULL làm điều kiện so sánh trở thành UNKNOWN và khiến logic nghiệp vụ khó đoán.

## 9. Nhiều sản phẩm trong một đơn hàng

Một đơn hàng có thể chứa nhiều SKU. Khi đó, transaction phải giữ đủ số lượng cho tất cả dòng hàng hoặc rollback toàn bộ đơn nếu một dòng không đủ.

Giả sử đơn có:

| Sản phẩm | Số lượng cần |
|---|---:|
| P10 | 2 |
| P20 | 1 |
| P30 | 4 |

Transaction có thể chạy UPDATE có điều kiện cho từng sản phẩm rồi mới tạo đơn. Nếu P10 và P20 thành công nhưng P30 không đủ hàng, phải rollback để hoàn lại P10 và P20.

Pseudo-code:

~~~java
connection.setAutoCommit(false);

try {
    for (OrderLine line : lines) {
        boolean reserved = reserveStock(
            connection,
            line.productId(),
            line.quantity()
        );

        if (!reserved) {
            throw new InsufficientStockException(
                line.productId()
            );
        }
    }

    long orderId = insertOrder(connection, customerId);
    insertOrderLines(connection, orderId, lines);

    connection.commit();
} catch (Exception error) {
    connection.rollback();
    throw error;
}
~~~

Không commit sau mỗi dòng hàng nếu nghiệp vụ yêu cầu đơn phải được chấp nhận toàn bộ. Một đơn hàng chỉ nên ở trạng thái thành công khi mọi dòng đã được giữ đủ số lượng và dữ liệu đơn đã được lưu.

### 9.1. Gộp các dòng trùng SKU

Giỏ hàng có thể chứa cùng một sản phẩm ở nhiều dòng do biến thể, khuyến mãi hoặc cách biểu diễn dữ liệu. Trước khi trừ kho, hãy gộp số lượng theo khóa tồn kho thực sự, chẳng hạn product_id hoặc tổ hợp warehouse_id và product_id.

Ví dụ hai dòng cùng P10 với số lượng 2 và 3 phải được kiểm tra như một yêu cầu 5 đơn vị. Nếu kiểm tra riêng từng dòng, ứng dụng có thể bỏ qua quan hệ giữa các dòng hoặc cập nhật lặp lại không cần thiết.

Việc gộp cần dùng kiểu số đủ lớn và kiểm tra tổng không vượt giới hạn nghiệp vụ. Khi lưu order_item, có thể giữ các dòng gốc nếu cần thể hiện chi tiết khuyến mãi; nhưng lượng tồn kho phải được trừ theo tổng yêu cầu tương ứng.

### 9.2. Cập nhật theo thứ tự ổn định để giảm deadlock

Hai đơn hàng có thể chứa cùng các SKU nhưng theo thứ tự khác nhau:

- T1 trừ P10 rồi P20.
- T2 trừ P20 rồi P10.

T1 có thể giữ khóa P10 và chờ P20, trong khi T2 giữ P20 và chờ P10. Đây là deadlock do thứ tự lấy khóa.

Để giảm nguy cơ, hãy sắp xếp các sản phẩm theo một thứ tự thống nhất, ví dụ product_id tăng dần, trước khi chạy các UPDATE. Nếu tồn kho được phân theo kho, thứ tự có thể là (warehouse_id, product_id).

Quy tắc này phải được dùng ở mọi luồng cập nhật liên quan. Nó giảm deadlock do đảo thứ tự, nhưng không loại bỏ mọi deadlock khác trong hệ thống. Nếu database vẫn hủy transaction, ứng dụng phải xử lý lỗi và retry toàn bộ transaction.

## 10. Tồn kho khả dụng, tồn kho vật lý và hàng đang giữ

Không phải hệ thống nào cũng trừ trực tiếp số lượng vật lý ngay khi khách đặt hàng. Cần xác định rõ cột đang biểu diễn điều gì.

Một mô hình đơn giản:

- on_hand_qty: số lượng vật lý trong kho.
- reserved_qty: số lượng đã được giữ cho các đơn chưa hoàn tất.
- available_qty: lượng có thể tiếp tục bán, thường bằng on_hand_qty - reserved_qty.

Có thể lưu available_qty trực tiếp để cập nhật nhanh, hoặc tính từ hai cột. Nếu lưu cả ba giá trị, cần bảo đảm quan hệ giữa chúng luôn đúng trong cùng transaction.

Một thiết kế giữ hàng có thể tăng reserved_qty nếu lượng chưa giữ còn đủ:

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty + :requested_qty
WHERE product_id = :product_id
  AND on_hand_qty - reserved_qty >= :requested_qty
  AND :requested_qty > 0;
~~~

Ở đây không giảm on_hand_qty ngay. Khi đơn được xuất kho, hệ thống mới giảm cả số lượng vật lý và số lượng đang giữ theo một transaction phù hợp.

Khi đơn bị hủy hoặc hết thời gian giữ, phải giải phóng phần đã reserve đúng một lần. Nếu một worker và thao tác người dùng cùng xử lý hủy đơn, cần có điều kiện trạng thái đơn hoặc idempotency để tránh giảm reserved_qty hai lần.

Nếu dùng available_qty riêng:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :requested_qty
WHERE product_id = :product_id
  AND available_qty >= :requested_qty
  AND :requested_qty > 0;
~~~

Hãy định nghĩa rõ thời điểm trừ: lúc tạo đơn, lúc thanh toán, hay lúc xác nhận giữ hàng. Quy tắc này quyết định khi nào cần hoàn lại tồn kho và cách xử lý đơn hết hạn.

## 11. Xử lý yêu cầu lặp và retry an toàn

Một yêu cầu HTTP có thể được gửi lại vì timeout mạng, người dùng nhấn nút nhiều lần hoặc client không nhận được phản hồi. Nếu mỗi lần nhận yêu cầu ứng dụng đều trừ kho, một đơn có thể bị trừ tồn kho nhiều lần.

Hãy dùng một mã yêu cầu duy nhất (*idempotency key*) hoặc mã đơn hàng có ràng buộc duy nhất. Việc ghi nhận yêu cầu và trừ kho phải nằm trong cùng transaction.

Mẫu khái quát:

1. Nhận idempotency key từ client.
2. Tạo hoặc kiểm tra bản ghi yêu cầu với unique constraint.
3. Nếu yêu cầu đã hoàn tất, trả lại kết quả trước đó.
4. Nếu là yêu cầu mới, trừ kho bằng UPDATE có điều kiện.
5. Tạo đơn và lưu kết quả gắn với idempotency key.
6. Commit.

Nếu transaction gặp deadlock hoặc serialization failure, rollback rồi chạy lại toàn bộ transaction. Unique constraint trên idempotency key giúp ngăn việc tạo hai đơn cho cùng một yêu cầu khi client gửi lại.

Không nên đặt idempotency key chỉ ở bộ nhớ của một instance ứng dụng, vì request retry có thể đi đến instance khác. Cơ chế chống lặp cần được lưu bền vững ở nơi các instance cùng kiểm tra được.

## 12. Phân biệt hết hàng với lỗi đồng thời

Kết quả UPDATE bằng 0 và lỗi transaction là hai tình huống khác nhau:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| UPDATE thành công 1 hàng | Đã giữ/trừ đủ số lượng | Tiếp tục tạo đơn trong transaction |
| UPDATE thành công 0 hàng | Điều kiện nghiệp vụ không thỏa | Rollback nếu có thay đổi trước đó; trả kết quả không đủ hàng hoặc không tìm thấy sản phẩm |
| Deadlock | Transaction bị chọn làm nạn nhân | Rollback và retry toàn bộ transaction có giới hạn |
| Serialization failure | Lịch chạy không đáp ứng isolation level | Transaction mới, đọc lại và chạy lại toàn bộ nghiệp vụ |
| Lock timeout | Chờ khóa vượt ngưỡng | Điều tra thời gian chờ; retry chỉ theo chính sách |
| Lỗi constraint | Một ràng buộc dữ liệu bị vi phạm | Phân loại nguyên nhân; không retry mù quáng |

Nếu UPDATE trả 0 hàng vì thiếu tồn kho, retry ngay thường không giúp gì trừ khi lượng hàng được bổ sung hoặc một transaction khác hoàn trả hàng. Đây là kết quả nghiệp vụ, không phải lỗi kỹ thuật.

Nếu transaction bị hủy do deadlock, việc thử lại có thể thành công vì transaction khác đã hoàn tất. Tuy nhiên, lần thử mới phải thực hiện lại cả bước kiểm tra tồn kho.

## 13. Tối ưu khi một sản phẩm có lượng đặt rất lớn

Một sản phẩm phổ biến có thể trở thành hàng nóng. Nhiều transaction cùng UPDATE một hàng tồn kho sẽ phải chờ nhau vì hệ quản trị cần điều phối các lần ghi.

Mẫu UPDATE có điều kiện bảo vệ đúng dữ liệu nhưng không làm biến mất giới hạn tuần tự hóa trên một hàng duy nhất. Nếu lưu lượng quá lớn, có thể cần thay đổi kiến trúc:

- Phân vùng tồn kho theo kho, khu vực hoặc lô hàng nếu nghiệp vụ cho phép.
- Dùng các bucket tồn kho có khóa riêng rồi phân phối số lượng hợp lệ giữa chúng.
- Giữ hàng theo lô hoặc theo batch để giảm số lần ghi.
- Dùng hàng đợi cho sản phẩm cực nóng nếu cần tuần tự hóa yêu cầu đặt.
- Giảm thời gian transaction và tránh gọi dịch vụ ngoài trong lúc đang giữ khóa.
- Theo dõi thời gian chờ khóa, tỷ lệ UPDATE trả 0, tỷ lệ deadlock và số lần retry.

Không nên chia một lượng tồn kho thành nhiều bucket chỉ để tăng throughput nếu việc tổng hợp và chuyển hàng giữa bucket không có quy tắc bảo vệ tổng số lượng. Bất biến toàn cục “tổng số hàng đã giữ không vượt hàng vật lý” vẫn phải được duy trì.

## 14. Kiểm thử cạnh tranh để chứng minh không bán vượt

Một bài kiểm thử hữu ích cần chạy nhiều transaction thật sự đồng thời trên database dùng cho kiểm thử.

Ví dụ:

- Tạo sản phẩm P42 với available_qty = 10.
- Khởi chạy hai worker đồng thời.
- Mỗi worker yêu cầu giữ 7 đơn vị bằng cùng câu UPDATE có điều kiện.
- Dùng barrier để hai worker bắt đầu gần như cùng thời điểm.
- Ghi lại số hàng được cập nhật và kết quả transaction.
- Đọc tồn kho sau khi cả hai kết thúc.

Kết quả kỳ vọng:

| Chỉ số | Kết quả hợp lệ |
|---|---|
| Số yêu cầu được chấp nhận | 1 |
| Tổng số lượng đã giữ | 7 |
| Tồn kho còn lại | 3 |
| Tồn kho âm | Không bao giờ |
| Số đơn được tạo thành công | 1 |

Nếu kiểm thử dùng cách SELECT rồi UPDATE với giá trị tính sẵn, có thể tái hiện mất cập nhật hoặc bán vượt tùy cách ghi. Nếu dùng UPDATE có điều kiện, một yêu cầu phải thất bại hoặc được xử lý lại sau khi đọc trạng thái mới.

Hãy kiểm tra cả tình huống một đơn có nhiều SKU, một dòng không đủ hàng sau khi các dòng trước đã cập nhật, client gửi lại cùng idempotency key và transaction gặp deadlock.

Không chỉ kiểm tra trạng thái cuối cùng. Cũng cần xác nhận rằng các đơn thất bại không để lại phần tồn kho bị trừ dở dang và retry không tạo bản ghi đơn trùng.

## 15. Checklist khi triển khai trừ tồn kho

- [ ] Số lượng yêu cầu được xác thực là số dương và nằm trong giới hạn kiểu dữ liệu?
- [ ] Câu UPDATE vừa kiểm tra số lượng đủ vừa trừ trong cùng câu lệnh?
- [ ] Điều kiện WHERE định danh đúng một hàng bằng khóa duy nhất?
- [ ] Cột tồn kho có NOT NULL và CHECK không âm?
- [ ] Ứng dụng kiểm tra số hàng được cập nhật?
- [ ] Trừ kho và tạo đơn/chi tiết đơn có nằm trong cùng transaction?
- [ ] Nếu một SKU không đủ, mọi thay đổi trước đó của đơn có được rollback?
- [ ] Nhiều SKU được xử lý theo thứ tự khóa ổn định?
- [ ] Các dòng trùng SKU được gộp trước khi kiểm tra tổng số lượng?
- [ ] Quy tắc reserve, xuất kho, hủy đơn và hoàn hàng được định nghĩa rõ?
- [ ] Request retry có idempotency key được lưu bền vững?
- [ ] Deadlock và serialization failure có retry toàn bộ transaction trong transaction mới?
- [ ] Kiểm thử có chạy nhiều transaction đồng thời và xác nhận tồn kho không âm?

Trừ tồn kho bằng UPDATE có điều kiện là một cách trực tiếp để bảo vệ bất biến trên một hàng: chỉ giảm số lượng khi giá trị hiện tại vẫn đủ đáp ứng yêu cầu. Đặt phép kiểm tra trong cùng câu lệnh ghi giúp loại bỏ khoảng trống giữa đọc và cập nhật. Khi kết hợp với constraint không âm, transaction bao trọn việc tạo đơn, thứ tự khóa ổn định cho nhiều SKU và idempotency cho yêu cầu lặp, hệ thống có thể tránh bán vượt số lượng ngay cả khi nhiều khách hàng đặt cùng lúc.
