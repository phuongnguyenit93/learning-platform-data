# Tranh chấp kiểm tra rồi hành động (check-then-act)

## 1. Bản chất của check-then-act

**Check-then-act** là mẫu xử lý gồm hai bước: đọc trạng thái và kiểm tra điều kiện (*check*), sau đó thực hiện thay đổi dựa trên kết quả (*act*). Khi chỉ có một luồng xử lý, mẫu này thường dễ hiểu. Khi nhiều transaction cùng chạy, một transaction khác có thể thay đổi dữ liệu sau bước kiểm tra nhưng trước lúc hành động.

Ví dụ, cửa hàng chỉ còn một sản phẩm. Hai yêu cầu mua hàng cùng đọc tồn kho bằng 1, kiểm tra đủ hàng và cùng tạo đơn. Nếu cả hai ghi tồn kho thành 0 dựa trên giá trị đã đọc, hệ thống xác nhận hai đơn cho một sản phẩm.

~~~text
Ban đầu: stock = 1

T1: CHECK stock >= 1  -> TRUE
T2: CHECK stock >= 1  -> TRUE
T1: ACT tạo đơn, stock = 0
T2: ACT tạo đơn, stock = 0

Kết quả nghiệp vụ: hai đơn cho một sản phẩm
~~~

Phép so sánh không sai tại thời điểm mỗi transaction thực hiện nó. Vấn đề là kết quả kiểm tra không còn được bảo đảm đúng khi hành động diễn ra. Đây là race condition giữa thao tác đọc/kiểm tra và thao tác ghi.

Một tên thường dùng cho lỗi này là **TOCTOU (Time Of Check To Time Of Use)**: trạng thái tại thời điểm kiểm tra khác trạng thái tại thời điểm sử dụng.

~~~text
Thời điểm kiểm tra                         Thời điểm sử dụng
       |                                          |
       v                                          v
   đọc và kiểm tra ------------------------- thực hiện hành động
                         ^
                         |
          transaction khác có thể cập nhật dữ liệu
~~~

Các ví dụ thường gặp: đọc số dư thấy đủ tiền rồi mới trừ; kiểm tra username chưa tồn tại rồi đăng ký; kiểm tra ghế trống rồi tạo booking; kiểm tra hạn mức còn dư rồi cấp phát; kiểm tra quyền rồi thực hiện thao tác nhạy cảm.

TOCTOU cũng xuất hiện trong filesystem, cache và API phân tán. Bài này tập trung vào trường hợp nhiều database transaction cùng kiểm tra và thay đổi dữ liệu.

### 1.1. Đặt hai câu lệnh trong cùng transaction chưa chắc đã đủ

Một hiểu nhầm là chỉ cần đặt SELECT và UPDATE trong cùng BEGIN/COMMIT thì không có race condition. Transaction bảo đảm ranh giới commit/rollback cho nhóm thao tác, nhưng mức cô lập và cách engine xử lý xung đột mới quyết định transaction khác có thể quan sát hoặc thay đổi dữ liệu ra sao.

Ở READ COMMITTED, hai transaction có thể cùng đọc một giá trị đã commit trước đó. Nếu cập nhật bằng giá trị cố định được tính từ lần đọc cũ, transaction sau có thể ghi đè kết quả của transaction trước.

~~~sql
BEGIN;

SELECT stock
FROM products
WHERE id = 10;

-- Ứng dụng kiểm tra stock >= 1.

UPDATE products
SET stock = 0
WHERE id = 10;

INSERT INTO orders(product_id, quantity)
VALUES (10, 1);

COMMIT;
~~~

Hai transaction có thể cùng đi qua SELECT và cùng tạo đơn. Điều kiện cần được bảo vệ tại thời điểm ghi bằng câu lệnh cập nhật nguyên tử, ràng buộc, khóa hoặc isolation thích hợp.

### 1.2. Khi nào check-then-act có thể chấp nhận?

Nếu dữ liệu không thể bị actor khác thay đổi trong khoảng giữa check và act, hoặc nếu kết quả có thể cũ mà không ảnh hưởng bất biến nghiệp vụ, việc tách hai bước có thể phù hợp. Đọc một cấu hình giao diện có thể chấp nhận dữ liệu cũ vài giây. Nhưng cấp vé cuối cùng, trừ tiền, giữ chỗ hoặc xác nhận quyền truy cập thường cần kiểm soát chặt.

Trước khi chọn kỹ thuật, hãy xác định dữ liệu nào quyết định điều kiện; actor khác có thể thay đổi dữ liệu đó không; hậu quả nếu điều kiện thay đổi; có thể kiểm tra ngay trong câu lệnh ghi không; và nếu quyết định phụ thuộc nhiều hàng thì tất cả được phối hợp qua đâu.

## 2. Các lịch xen kẽ gây tranh chấp

### 2.1. Lost update do đọc rồi ghi giá trị cũ

Giả sử bộ đếm ban đầu bằng 10. T1 và T2 cùng muốn tăng một đơn vị:

~~~text
T1: READ value = 10
T2: READ value = 10
T1: tính 11
T2: tính 11
T1: WRITE value = 11; COMMIT
T2: WRITE value = 11; COMMIT

Giá trị cuối = 11, trong khi đúng ra phải là 12.
~~~

Đây là **lost update**. Cả hai transaction đều thực hiện đủ bước đọc và ghi, nhưng lần cập nhật sau ghi đè kết quả của lần trước.

Với một hàng, câu lệnh nguyên tử sau thường phù hợp hơn:

~~~sql
UPDATE counters
SET value = value + 1
WHERE id = 1;
~~~

Database thực hiện phép cộng trên giá trị hiện hành theo cơ chế điều phối ghi của engine. Hai lệnh cập nhật cạnh tranh trên cùng hàng không còn cùng ghi giá trị 11 đã tính từ hai lần đọc cũ ở ứng dụng.

### 2.2. Bán vượt tồn kho

Cho stock = 5, hai khách cùng mua 4 sản phẩm:

| Thứ tự | T1 | T2 |
|---:|---|---|
| 1 | Đọc stock = 5 | |
| 2 | | Đọc stock = 5 |
| 3 | Kiểm tra 5 >= 4, đúng | |
| 4 | | Kiểm tra 5 >= 4, đúng |
| 5 | Tạo đơn 4 sản phẩm | |
| 6 | | Tạo đơn 4 sản phẩm |
| 7 | Ghi stock = 1 | |
| 8 | | Ghi stock = 1 |

Tồn kho cuối là 1, nhưng hệ thống đã xác nhận tổng cộng 8 sản phẩm trong khi chỉ có 5. Cột tồn kho không âm nên CHECK (stock >= 0) đơn giản không phát hiện việc bán vượt lượng hàng ban đầu. Không được đồng nhất giá trị cuối hợp lệ về kiểu dữ liệu với việc bất biến nghiệp vụ được bảo toàn.

### 2.3. Hai người đăng ký cùng username

Hai yêu cầu đăng ký username alice cùng SELECT và đều không thấy hàng; sau đó cả hai cùng thử INSERT. Nếu không có ràng buộc duy nhất, hai request có thể tạo dữ liệu trùng. Cách bảo vệ cuối cùng là UNIQUE trong database; ứng dụng xử lý lỗi xung đột như kết quả nghiệp vụ bình thường.

### 2.4. Write skew trên nhiều hàng

Một ca trực có hai bác sĩ A và B; bất biến là luôn có ít nhất một người trực. T1 đọc cả hai đều trực rồi cho A nghỉ. T2 cũng đọc trạng thái ban đầu rồi cho B nghỉ. Mỗi transaction cập nhật một hàng khác nhau nên cơ chế chỉ phát hiện ghi cùng hàng chưa chắc ngăn được kết quả cả hai nghỉ.

~~~text
T1: đọc A=on, B=on -> cập nhật A=off
T2: đọc A=on, B=on -> cập nhật B=off
T1: COMMIT
T2: COMMIT

Kết quả: A=off, B=off, bất biến bị vi phạm.
~~~

Đây là **write skew**. Một câu UPDATE nguyên tử trên một hàng không đủ khi quyết định phụ thuộc vào tập hàng. Cần điểm phối hợp chung, khóa thích hợp hoặc SERIALIZABLE isolation có retry.

## 3. Gộp điều kiện và hành động thành SQL nguyên tử

Với một hàng hoặc điều kiện có thể kiểm tra ngay trong câu lệnh ghi, đây thường là cách ngắn gọn và hiệu quả.

### 3.1. Trừ tồn kho có điều kiện

Thay cho SELECT trước rồi mới UPDATE:

~~~sql
UPDATE products
SET stock = stock - :quantity
WHERE id = :product_id
  AND :quantity > 0
  AND stock >= :quantity;
~~~

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

- 1 hàng: phép trừ đã thực hiện.
- 0 hàng: sản phẩm không tồn tại, số lượng không hợp lệ hoặc tồn kho không đủ.
- Lớn hơn 1: vi phạm giả định định danh duy nhất; cần điều tra schema.

Với id là khóa chính, cập nhật thông thường chỉ ảnh hưởng tối đa một hàng.

Có thể thêm CHECK như một lớp bảo vệ:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
~~~

CHECK ngăn số tồn kho âm, còn điều kiện stock >= quantity bảo vệ quy tắc đủ hàng tại thời điểm cập nhật.

### 3.2. Trừ kho và tạo đơn cùng transaction

~~~sql
BEGIN;

UPDATE products
SET stock = stock - :quantity
WHERE id = :product_id
  AND :quantity > 0
  AND stock >= :quantity;

-- Chỉ tiếp tục khi UPDATE ảnh hưởng đúng một hàng.

INSERT INTO orders(request_key, product_id, quantity)
VALUES (:request_key, :product_id, :quantity);

COMMIT;
~~~

Nếu INSERT đơn thất bại, transaction rollback và việc trừ kho được hoàn tác. Nếu UPDATE ảnh hưởng 0 hàng, ứng dụng không được tiếp tục insert; cần kết thúc transaction phù hợp và trả kết quả hết hàng/không hợp lệ.

Đây là khung minh họa: ứng dụng phải thực sự kiểm tra số hàng ảnh hưởng giữa UPDATE và INSERT.

### 3.3. Idempotency key

Client có thể timeout sau khi database đã commit. Nếu gửi lại yêu cầu dưới một mã mới, hệ thống có thể tạo đơn và trừ kho lần nữa.

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_request_key UNIQUE (request_key);
~~~

request_key phải ổn định theo cùng một thao tác nghiệp vụ. Khi nhận trùng key, ứng dụng tra cứu đơn đã tồn tại và trả lại kết quả phù hợp. Cũng cần xác minh payload có cùng ý nghĩa; không coi key giống nhau với tham số mâu thuẫn là cùng request hợp lệ.

Idempotency nhận diện việc gửi lặp ở biên ứng dụng; atomic update giải quyết tranh chấp khi thay đổi dữ liệu. Thực tế thường cần cả hai.

### 3.4. Trừ số dư có điều kiện

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :account_id
  AND :amount > 0
  AND balance >= :amount;
~~~

Sau đó xác định thành công dựa trên số hàng cập nhật. Có thể thêm CHECK (balance >= 0) nếu tài khoản không cho phép thấu chi. Với chuyển tiền, cần tăng tài khoản nhận và ghi sổ cái trong cùng transaction, phối hợp thứ tự khóa và idempotency.

## 4. Constraint bảo vệ điều kiện nghiệp vụ

### 4.1. UNIQUE thay cho SELECT rồi INSERT

~~~sql
CREATE UNIQUE INDEX uq_user_username
ON users(username);
~~~

Ứng dụng insert và xử lý duplicate key. Có thể SELECT trước để cải thiện trải nghiệm người dùng, nhưng UNIQUE mới là lớp bảo vệ cuối cùng khi hai request cạnh tranh. Cần định nghĩa quy tắc chuẩn hóa và so sánh username/email, chẳng hạn chữ hoa thường, khoảng trắng và collation.

### 4.2. CHECK cho bất biến trên một hàng

~~~sql
CREATE TABLE reservations (
    id BIGINT PRIMARY KEY,
    capacity INTEGER NOT NULL CHECK (capacity >= 0),
    used INTEGER NOT NULL CHECK (used >= 0),
    CONSTRAINT ck_reservation_capacity CHECK (used <= capacity)
);
~~~

CHECK bảo đảm used không vượt capacity trên trạng thái hàng được ghi. Nếu nhiều transaction cùng tăng used, vẫn cần cập nhật nguyên tử hoặc khóa.

### 4.3. FOREIGN KEY và exclusion constraint

FOREIGN KEY bảo vệ tham chiếu; UNIQUE bảo vệ tính duy nhất; CHECK bảo vệ biểu thức trên hàng. Một số hệ quản trị có exclusion constraint để ngăn khoảng thời gian hoặc tài nguyên chồng lấn.

Ví dụ PostgreSQL:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_bookings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL,
    booked_period TSTZRANGE NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        booked_period WITH &&
    )
);
~~~

Ràng buộc này không cho hai booking cùng phòng có khoảng thời gian giao nhau. Khi hai transaction insert khoảng chồng lấn, database điều phối xung đột và không cho cả hai commit vi phạm constraint. Không phải mọi bất biến nhiều hàng đều biểu diễn được bằng constraint đơn giản.

## 5. Khóa dữ liệu giữa check và act

### 5.1. SELECT FOR UPDATE

Khi SQL nguyên tử không đủ biểu đạt logic, có thể đọc dữ liệu cùng khóa rồi kiểm tra trong lúc khóa còn được giữ.

~~~sql
BEGIN;

SELECT stock
FROM products
WHERE id = :product_id
FOR UPDATE;

-- Kiểm tra stock >= quantity trong khi giữ row lock.

UPDATE products
SET stock = stock - :quantity
WHERE id = :product_id;

INSERT INTO orders(request_key, product_id, quantity)
VALUES (:request_key, :product_id, :quantity);

COMMIT;
~~~

FOR UPDATE khóa các hàng được chọn theo quy tắc engine. Transaction khác muốn lấy khóa ghi không tương thích trên cùng hàng phải chờ hoặc bị xử lý theo quy tắc xung đột. Cần kiểm tra hàng tồn tại và đủ số lượng, cập nhật đúng hàng đã khóa trong cùng transaction/connection, và không gọi HTTP hay làm tác vụ chậm khi giữ khóa.

Khóa hàng hiện hữu không bảo vệ một hàng chưa tồn tại hoặc toàn bộ tập kết quả. Deadlock vẫn có thể xảy ra nếu các transaction khóa nhiều hàng theo thứ tự khác nhau.

### 5.2. Thứ tự lấy khóa thống nhất

Chuyển khoản giữa A và B có thể deadlock nếu T1 khóa A rồi chờ B, còn T2 khóa B rồi chờ A. Một cách giảm nguy cơ là mọi transaction luôn lấy khóa theo cùng thứ tự, chẳng hạn account_id tăng dần, bất kể hướng chuyển tiền.

### 5.3. Predicate và hàng chưa tồn tại

Nếu kiểm tra chưa có booking cho phòng 5 trong một khoảng rồi insert, FOR UPDATE trên kết quả rỗng không nhất thiết khóa được hàng chưa tồn tại. Có thể dùng exclusion/unique constraint, SERIALIZABLE, predicate/range lock khi engine hỗ trợ, hoặc một hàng đại diện cho phòng làm điểm khóa chung.

## 6. Optimistic concurrency control

Khóa bi quan thích hợp khi xung đột cao và quyết định ngắn. Với dữ liệu ít xung đột hoặc form được mở lâu, có thể dùng version check.

~~~sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Ứng dụng đọc version = 5. Khi lưu:

~~~sql
UPDATE documents
SET title = :title,
    body = :body,
    version = version + 1
WHERE id = :document_id
  AND version = :expected_version;
~~~

Nếu UPDATE ảnh hưởng 1 hàng, cập nhật thành công. Nếu 0 hàng, dữ liệu đã đổi, bản ghi không tồn tại hoặc điều kiện không thỏa. Ứng dụng tải lại/hợp nhất hoặc trả conflict. Điều kiện version phải xuất hiện trong chính câu UPDATE; SELECT version rồi so sánh trong bộ nhớ vẫn có khoảng TOCTOU.

Version trên từng hàng không bảo vệ bất biến tập hợp nếu hai transaction sửa hai hàng khác nhau.

## 7. Isolation level phù hợp

### 7.1. READ COMMITTED

READ COMMITTED thường ngăn dirty read, nhưng hai transaction vẫn có thể cùng đọc một giá trị đã commit rồi đưa ra cùng quyết định. Nếu câu UPDATE không có điều kiện, kết quả kiểm tra cũ không được xác minh lại.

### 7.2. REPEATABLE READ

REPEATABLE READ thường giữ snapshot nhất quán trong transaction, tùy engine. Nó có thể ngăn một số lần đọc thay đổi nhưng không mặc nhiên ngăn mọi write skew. Hai transaction có thể cùng đọc một snapshot rồi ghi các hàng khác nhau.

### 7.3. SERIALIZABLE

SERIALIZABLE yêu cầu kết quả các transaction đã commit tương đương một thứ tự tuần tự. Với quyết định nhiều hàng, database có thể phát hiện lịch nguy hiểm và abort một transaction để ứng dụng thử lại.

~~~text
T1: BEGIN SERIALIZABLE
    đọc số người trực = 2
    cho A nghỉ

T2: BEGIN SERIALIZABLE
    đọc số người trực = 2
    cho B nghỉ

Database phát hiện xung đột phụ thuộc
Một transaction có thể abort với serialization failure
Ứng dụng chạy lại toàn bộ logic trên snapshot mới
~~~

Serializable không có nghĩa không cần retry. Retry phải dùng transaction mới và chạy lại toàn bộ quyết định.

| Chiến lược | Phù hợp | Chi phí/rủi ro |
|---|---|---|
| Atomic conditional UPDATE | Điều kiện trên một hàng | Cần kiểm tra affected rows |
| UNIQUE/CHECK/FK/exclusion | Quy tắc biểu diễn được bằng constraint | Giới hạn phạm vi constraint |
| Pessimistic lock | Xung đột cao, thao tác ngắn | Lock wait, deadlock |
| Optimistic version | Xung đột thấp, chỉnh sửa kéo dài | Conflict/retry |
| SERIALIZABLE | Bất biến nhiều hàng/phạm vi | Serialization failure và retry |

## 8. Ví dụ nghiệp vụ

### 8.1. Đặt ghế

~~~sql
CREATE TABLE seat_bookings (
    show_id BIGINT NOT NULL,
    seat_no TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    PRIMARY KEY (show_id, seat_no)
);
~~~

Hai request cùng đặt ghế có thể cùng kiểm tra chưa tồn tại, nhưng chỉ một INSERT thành công nhờ khóa chính. Request còn lại nhận duplicate key và trả kết quả ghế đã được đặt.

Nếu ghế có hàng trạng thái, có thể chuyển trạng thái có điều kiện:

~~~sql
UPDATE seats
SET status = 'BOOKED',
    customer_id = :customer_id
WHERE show_id = :show_id
  AND seat_no = :seat_no
  AND status = 'AVAILABLE';
~~~

Chỉ request cập nhật được hàng từ AVAILABLE sang BOOKED thành công.

### 8.2. Giữ chỗ trước thanh toán

~~~sql
UPDATE seats
SET status = 'HELD',
    customer_id = :customer_id,
    hold_until = :expiry
WHERE show_id = :show_id
  AND seat_no = :seat_no
  AND (
      status = 'AVAILABLE'
      OR (status = 'HELD' AND hold_until < CURRENT_TIMESTAMP)
  );
~~~

Cần quy định thời hạn, múi giờ, ai được gia hạn và cách xử lý callback thanh toán đến muộn. Tiến trình dọn chỗ hết hạn cũng cần cập nhật có điều kiện để tránh giải phóng chỗ vừa được gia hạn.

### 8.3. Cấp phát hạn mức

Giả sử khách hàng có hạn mức 100. Hai dịch vụ cùng cấp phát 70. Có thể mô hình hóa một hàng tổng hợp:

~~~sql
UPDATE credit_limits
SET allocated = allocated + :requested
WHERE customer_id = :customer_id
  AND allocated + :requested <= credit_limit;
~~~

Nếu thành công, ghi bản phân bổ chi tiết trong cùng transaction. Nếu hạn mức nằm trên nhiều database/dịch vụ, transaction local không bảo vệ bất biến toàn cục; cần authority cho hạn mức, reservation/lease hoặc quota phân bổ.

## 9. Java và Spring

### 9.1. Repository cập nhật có điều kiện

~~~java
@Repository
public class InventoryRepository {
    private final JdbcTemplate jdbc;

    public InventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean decreaseIfAvailable(long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        int affected = jdbc.update("""
            UPDATE products
               SET stock = stock - ?
             WHERE id = ?
               AND stock >= ?
            """,
            quantity, productId, quantity
        );

        return affected == 1;
    }
}
~~~

Repository không cần SELECT riêng rồi mới trừ kho. Câu UPDATE vừa kiểm tra điều kiện, vừa thay đổi dữ liệu.

### 9.2. Service gom thay đổi trong transaction

~~~java
@Service
public class OrderService {
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public OrderService(InventoryRepository inventory,
                        OrderRepository orders) {
        this.inventory = inventory;
        this.orders = orders;
    }

    @Transactional
    public void placeOrder(long productId, int quantity, String requestKey) {
        boolean decreased =
                inventory.decreaseIfAvailable(productId, quantity);

        if (!decreased) {
            throw new IllegalStateException("Product is unavailable");
        }

        orders.insert(requestKey, productId, quantity);
    }
}
~~~

Nếu insert đơn thất bại với exception được cấu hình rollback, thay đổi tồn kho cũng rollback. Nếu muốn trả về hết hàng thay vì ném exception, cần xác định transaction kết thúc thế nào và không chạy bước insert.

### 9.3. Optimistic locking trong JPA

~~~java
@Entity
public class Document {
    @Id
    private Long id;

    @Version
    private Long version;

    private String title;
    private String body;
}
~~~

Hibernate/JPA có thể đưa version vào UPDATE và ném optimistic locking exception khi hàng đã bị transaction khác cập nhật. Service cần bắt lỗi ở ranh giới phù hợp, trả conflict hoặc tải lại và hợp nhất. @Version bảo vệ cập nhật cùng entity, không tạo khóa chung cho bất biến nhiều entity.

### 9.4. Quy tắc dùng @Transactional

Gọi qua proxy transaction của Spring; self-invocation có thể bỏ qua interceptor. Bảo đảm repository dùng cùng transaction manager/connection context. Xác định rollback rules cho exception. Tránh gọi dịch vụ ngoài khi giữ transaction và khóa lâu. Không tự ý commit connection do Spring quản lý.

Retry deadlock/serialization failure phải tạo transaction mới và chạy lại toàn bộ quyết định. Vòng retry bên trong transaction đã bị đánh dấu rollback-only không thể phục hồi transaction đó.

## 10. Check-then-act ngoài database

**Filesystem:** kiểm tra file chưa tồn tại rồi tạo có race condition. Khi cần tạo duy nhất, dùng API có chế độ create-new nguyên tử thay vì kiểm tra tồn tại rồi tạo riêng rẽ.

**Quyền truy cập:** kiểm tra quyền của một đường dẫn rồi mở lại đường dẫn có thể bị thay thế trong khoảng giữa. Tùy hệ điều hành, cần mở handle an toàn và kiểm tra quyền trên đối tượng đã mở.

**API và cache:** service kiểm tra số lượng còn trống trong cache rồi gọi API reservation có thể bị service khác lấy mất tài nguyên. API đích cần thao tác reservation có điều kiện hoặc idempotency key. Cache hỗ trợ đọc nhanh nhưng không nên là nguồn quyết định cuối cùng khi dữ liệu có tranh chấp.

**Quyền bị thu hồi:** nếu quyền phải còn hiệu lực đến thời điểm commit, cần phối hợp thu hồi và hành động bằng version, khóa hoặc authority thích hợp. Nếu chính sách chỉ yêu cầu quyền tại thời điểm bắt đầu request, snapshot quyền có thể chấp nhận được. Yêu cầu thời gian phải được quy định rõ.

## 11. Quy trình phân tích và kiểm thử

Với mỗi use case:

1. Viết bất biến: một ghế một booking, tồn kho không âm, tổng cấp phát không vượt hạn mức.
2. Xác định dữ liệu quyết định check: một hàng, nhiều hàng, predicate hay dữ liệu ngoài.
3. Dựng lịch xen kẽ: hai transaction cùng đọc trạng thái ban đầu rồi thay đổi.
4. Tìm cách diễn đạt atomic: UPDATE có điều kiện, INSERT với UNIQUE, UPSERT hoặc constraint.
5. Nếu phải đọc nhiều bước, xác định khóa chung hoặc isolation level bảo vệ tập dữ liệu.
6. Xử lý affected rows = 0, duplicate key, optimistic conflict, deadlock và serialization failure.
7. Retry bằng transaction mới, key ổn định, giới hạn số lần và backoff.
8. Kiểm thử đồng thời nhiều request và xác nhận bất biến sau commit.
9. Đo lock wait, conflict rate, retry, throughput và latency.

### 11.1. Kịch bản kiểm thử

**Hai người mua sản phẩm cuối cùng:** khởi tạo stock = 1, dùng hai kết nối độc lập và barrier để hai yêu cầu bắt đầu gần nhau. Kết quả đúng là chỉ một request giảm kho, chỉ một đơn commit, stock cuối bằng 0; request còn lại nhận hết hàng/conflict. Barrier và session độc lập đáng tin cậy hơn sleep ngẫu nhiên.

**Hai request cùng username:** gửi đồng thời hai request đăng ký một username. Một insert thành công, insert còn lại nhận unique violation; database chỉ có một hàng.

**Optimistic version:** hai client đọc version 4. Client A cập nhật thành 5. Client B gửi expected version 4 và phải nhận conflict.

**Bất biến nhiều hàng:** hai transaction cùng cho hai bác sĩ nghỉ. Kết quả phải còn ít nhất một người trực; serialization failure được retry từ đầu.

**Timeout sau commit:** gửi request với idempotency key cố định, mô phỏng mất phản hồi sau commit, gửi lại cùng key và xác nhận chỉ có một đơn. Timeout không chứng minh transaction đã rollback.

## 12. Sai lầm thường gặp

- **Chỉ kiểm tra trước:** SELECT rồi UPDATE bằng giá trị tính sẵn tạo khoảng tranh chấp.
- **Cho rằng transaction tự khóa mọi dữ liệu:** bảo vệ phụ thuộc isolation level và cơ chế của engine.
- **FOR UPDATE nhưng transaction kết thúc sớm:** khóa nhả trước bước act.
- **Chỉ dùng CHECK để ngăn overselling:** CHECK stock >= 0 không phát hiện hai đơn cùng bán một đơn vị.
- **Retry bằng key mới:** có thể tạo giao dịch nghiệp vụ thứ hai.
- **Retry transaction cũ:** dữ liệu đọc trước đó có thể đã lỗi thời; phải chạy lại trong transaction mới.
- **Cho rằng SERIALIZABLE không cần retry:** serialization failure là kết quả có thể dự kiến.
- **Giữ transaction quá lâu:** gọi API hoặc chờ người dùng khi đang giữ khóa làm tăng contention.

## 13. Bài tập tự luyện

### Bài 1 — Phân tích overselling

stock = 3. T1 mua 2, T2 mua 2. Cả hai SELECT thấy 3 rồi ghi stock = 1.

**Câu hỏi:** giá trị stock cuối nói lên điều gì, và điều gì vẫn sai?

**Gợi ý:** bảng kho còn 1 nhưng nghiệp vụ đã hứa 4 sản phẩm trong khi chỉ có 3. Hãy viết UPDATE có điều kiện stock >= 2 và kiểm tra affected rows.

### Bài 2 — Chọn UNIQUE hay SELECT

Hai user đăng ký cùng email. Cả hai SELECT đều không thấy email.

**Đáp án:** UNIQUE constraint trên email là lớp bảo vệ cuối cùng, có xét chuẩn hóa/case theo chính sách hệ thống. SELECT trước chỉ hỗ trợ trải nghiệm người dùng.

### Bài 3 — Version check

T1 và T2 cùng đọc version 10. T1 cập nhật thành 11. T2 gửi UPDATE với WHERE version = 10.

**Đáp án:** affected rows = 0; ứng dụng xử lý conflict và không ghi đè dữ liệu mới.

### Bài 4 — Bất biến nhiều hàng

Một chi nhánh có hai máy chủ trực. Hai transaction cùng đọc cả hai đang hoạt động rồi mỗi transaction tắt một máy khác nhau.

**Đáp án:** version trên từng hàng không đủ vì hai transaction ghi các hàng khác nhau. Cần hàng phối hợp chung, khóa phạm vi hoặc SERIALIZABLE cùng retry.

### Bài 5 — Atomic update và idempotency

Câu UPDATE có điều kiện giúp không trừ kho vượt số lượng. Vì sao vẫn cần idempotency key?

**Đáp án:** client có thể gửi lại cùng đơn sau timeout; lần gửi thứ hai vẫn có thể là một UPDATE hợp lệ và tiếp tục trừ kho. Atomicity bảo vệ cạnh tranh tại thời điểm ghi; idempotency nhận diện cùng yêu cầu gửi nhiều lần.

### Bài 6 — Thiết kế đặt vé

Mỗi ghế có một booking; người dùng giữ ghế 5 phút để thanh toán; retry không tạo booking trùng.

**Gợi ý:** unique key theo suất chiếu và ghế; cập nhật trạng thái bằng điều kiện AVAILABLE hoặc HELD đã hết hạn; lưu owner/expiry; idempotency key; transaction ghi trạng thái và reservation. Quy định gia hạn và callback thanh toán đến muộn.

## 14. Nguyên tắc ghi nhớ

Tranh chấp check-then-act xuất hiện khi một quyết định dựa trên dữ liệu tại thời điểm đọc, nhưng hành động diễn ra sau khi transaction khác có cơ hội thay đổi dữ liệu. Đặt hai câu lệnh trong cùng transaction chưa chắc giải quyết vấn đề; cần bảo vệ điều kiện tại thời điểm ghi hoặc giữ quyền kiểm soát dữ liệu suốt thời gian cần thiết.

- Với một hàng: ưu tiên câu SQL nguyên tử có điều kiện và kiểm tra số hàng ảnh hưởng.
- Với tính duy nhất hoặc giá trị hợp lệ: dùng UNIQUE, CHECK, khóa ngoại hoặc exclusion constraint.
- Với logic nhiều bước: dùng khóa bi quan trong transaction ngắn hoặc optimistic version check.
- Với bất biến nhiều hàng/phạm vi: chọn điểm phối hợp chung hoặc SERIALIZABLE cùng retry.
- Với request có thể gửi lại: dùng idempotency key và lưu kết quả nguyên tử.
- Với dữ liệu ngoài database: dùng reservation, outbox hoặc cơ chế phân tán phù hợp; transaction local không thể tự khóa mọi hệ thống.

Thiết kế đúng bắt đầu từ bất biến nghiệp vụ và lịch xen kẽ có thể xảy ra. Khi các đường đi cạnh tranh được phân tích, ứng dụng mới bảo đảm hành động phù hợp với trạng thái dữ liệu tại thời điểm commit.
