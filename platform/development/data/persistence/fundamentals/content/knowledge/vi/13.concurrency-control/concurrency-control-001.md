# Phân biệt an toàn luồng trong JVM với đồng thời tại kho dữ liệu

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **an toàn luồng (thread safety)** của đối tượng Java với **tính đúng đắn của dữ liệu** khi nhiều transaction cùng truy cập cơ sở dữ liệu.
2. Giải thích vì sao `synchronized`, `ReentrantLock`, `volatile` hoặc `AtomicInteger` không tự bảo vệ dữ liệu trên nhiều JVM, nhiều máy chủ và nhiều kết nối.
3. Nhận diện lost update, tranh chấp khóa, thao tác kiểm tra rồi ghi (*check-then-act*) và sai lệch do hai request xử lý cùng lúc.
4. Chọn công cụ phù hợp: thao tác SQL nguyên tử, ràng buộc duy nhất, optimistic locking, row lock, mức cô lập và cơ chế retry an toàn.
5. Viết một phương thức Java/JDBC tránh trừ tồn kho quá mức, đồng thời thiết kế kiểm thử với nhiều kết nối độc lập.

Bài thuộc chương **Kiểm soát đồng thời** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Trong ứng dụng Java, lưu trữ bền vững còn bao gồm mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, giao dịch, cô lập, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Một lựa chọn về khóa chỉ đúng khi xác định rõ **dữ liệu được chia sẻ ở đâu**, **ai có thể thay đổi nó** và **bất biến nghiệp vụ nào phải luôn được giữ**.

## 1. Hai phạm vi đồng thời khác nhau

**An toàn luồng trong JVM** là tính chất của mã và dữ liệu ở bộ nhớ của một tiến trình Java khi nhiều thread truy cập cùng lúc. Ví dụ: nhiều thread cùng tăng một bộ đếm, dùng chung cache hoặc sửa một `HashMap`.

**Kiểm soát đồng thời tại kho dữ liệu** là bảo vệ tính đúng đắn khi nhiều kết nối, transaction, tiến trình hoặc dịch vụ cùng đọc/ghi bản ghi bền vững. Các thao tác có thể đi qua cùng một ứng dụng Java, nhiều bản sao ứng dụng sau load balancer, một batch job hoặc dịch vụ khác viết trực tiếp vào database.

| Câu hỏi | Trong một JVM | Tại kho dữ liệu |
| --- | --- | --- |
| Đơn vị cạnh tranh | Thread cùng truy cập đối tượng/bộ nhớ | Transaction và các câu lệnh từ nhiều kết nối |
| Phần trạng thái liên quan | Field, object, collection, cache trong heap | Hàng, khóa, chỉ mục, ràng buộc, phiên bản dữ liệu bền vững |
| Công cụ điển hình | `synchronized`, `Lock`, `Atomic*`, concurrent collections | Transaction, `UPDATE` có điều kiện, UNIQUE, row lock, version, isolation |
| Phạm vi bảo vệ | Thông thường trong một tiến trình/JVM, theo đúng đối tượng khóa | Qua các kết nối và tiến trình cùng sử dụng một DB |
| Sự cố tiến trình | Trạng thái/khóa trong RAM biến mất khi JVM dừng | Dữ liệu đã commit tồn tại theo cam kết bền vững của DB |
| Rủi ro thường gặp | Race condition trên biến trong bộ nhớ, lỗi visibility | Lost update, ghi trùng, write skew, tranh chấp khóa, deadlock |
| Ai thực thi bảo vệ | JVM và chương trình Java | Hệ quản trị cơ sở dữ liệu, lược đồ và transaction |

Cả hai phạm vi đều quan trọng. Một repository có thể thread-safe về mặt đối tượng Java nhưng thực thi một thao tác SQL gây mất cập nhật. Ngược lại, một câu SQL có thể cập nhật số dư chính xác trong DB nhưng phần cache `HashMap` dùng chung ở Java lại bị race condition.

### 1.1. Sơ đồ nhiều điểm truy cập

~~~text
                   Load balancer
                   /           \
              JVM A             JVM B
           Thread 1, 2       Thread 1, 2
                |                 |
          synchronized         synchronized
          chỉ khóa JVM A       chỉ khóa JVM B
                |                 |
          JDBC Connection    JDBC Connection
                 \               /
                  \             /
                   Database
                 Cùng một hàng
               và cùng bất biến
~~~

Ngay cả khi JVM A và JVM B đều khóa đúng cách đối tượng của **mỗi tiến trình**, chúng không sử dụng chung một monitor Java. Vì vậy, chỉ DB hoặc một cơ chế phối hợp thật sự có phạm vi liên tiến trình mới có thể điều phối quyền ghi cho bản ghi chung.

## 2. Thread safety trong Java thực sự giải quyết điều gì?

Xét bộ đếm số request đang xử lý:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class InFlightRequests {
    private final AtomicInteger current = new AtomicInteger();

    public int entered() {
        return current.incrementAndGet();
    }

    public int left() {
        return current.decrementAndGet();
    }

    public int get() {
        return current.get();
    }
}
~~~

`AtomicInteger.incrementAndGet()` giúp thao tác tăng bộ đếm này là nguyên tử đối với các thread cùng dùng **chính instance** đó. Đây là lựa chọn hợp lý cho số request đang chạy trong một tiến trình.

Nhưng nếu `current` được xem là tồn kho của cả hệ thống bán hàng, kết quả sai ngay khi:

- Có hai instance của ứng dụng, mỗi instance sở hữu một biến `current` riêng.
- Một batch job thay đổi tồn kho trực tiếp trong DB mà không đi qua instance ấy.
- JVM khởi động lại, khiến trạng thái trong RAM không phản ánh dữ liệu đã commit.
- Hai lệnh SQL đọc và cập nhật DB diễn ra ngoài phạm vi thao tác nguyên tử của bộ đếm.

`volatile` chủ yếu cung cấp các bảo đảm về visibility/thứ tự bộ nhớ cho biến được khai báo; nó không biến phép `x++` gồm nhiều bước thành thao tác nguyên tử. `synchronized` và `ReentrantLock` có thể tạo vùng tới hạn (*critical section*) trong một JVM khi tất cả bên tham gia tuân thủ cùng một khóa. `ConcurrentHashMap` bảo vệ các thao tác theo hợp đồng của collection; một chuỗi nhiều thao tác vẫn có thể cần cơ chế nguyên tử riêng.

**Điều cần xác định trước khi chọn khóa:** những người có thể ghi cùng một dữ liệu có chắc chắn ở trong cùng JVM và dùng chung đúng đối tượng khóa không? Với bản ghi nghiệp vụ đã lưu trong database, câu trả lời thường là **không**.

### 2.1. `synchronized` có thể đúng trong phạm vi hẹp

Ví dụ:

~~~java
public final class LocalSequence {
    private long value;

    public synchronized long next() {
        return ++value;
    }
}
~~~

Một đối tượng `LocalSequence` được chia sẻ đúng cách giữa các thread trong **một JVM** sẽ trả về các số tăng liên tiếp mà không mất phép tăng. Nhưng nếu tạo hai đối tượng `LocalSequence` hoặc chạy hai JVM, mỗi đối tượng có dãy số riêng. Không được dùng nó để bảo đảm số hóa đơn duy nhất trên toàn hệ thống.

Đối với số định danh bền vững, có thể sử dụng identity/sequence của database hoặc một cơ chế cấp ID toàn cục có hợp đồng rõ ràng. Cũng cần phân biệt **duy nhất** với **liên tục không có khoảng trống**: sequence của DB thường cho tính duy nhất nhưng có thể có khoảng trống do rollback, cache hoặc lỗi.

## 3. Ví dụ kinh điển: hai request cùng mua món hàng cuối

Giả sử cơ sở dữ liệu có:

~~~sql
CREATE TABLE products (
    id       BIGINT PRIMARY KEY,
    name     TEXT NOT NULL,
    stock    INTEGER NOT NULL CHECK (stock >= 0)
);

INSERT INTO products (id, name, stock)
VALUES (101, 'Bàn phím', 1);
~~~

Hai request từ hai JVM khác nhau đều muốn mua **một** sản phẩm `id = 101`.

Mã ứng dụng ngây thơ thường làm:

~~~text
stock = SELECT stock FROM products WHERE id = 101
if stock > 0:
    UPDATE products SET stock = stock - 1 WHERE id = 101
    trả lời "đặt hàng thành công"
~~~

Nếu hai request cùng đọc `stock = 1`, cả hai đều vượt qua phép kiểm tra ở Java. Sau đó cả hai thử trừ tồn kho.

Ràng buộc `CHECK (stock >= 0)` có thể khiến một giao dịch gặp lỗi khi cố tạo tồn kho âm; nếu ứng dụng xử lý sai lỗi, người dùng vẫn có thể nhận hai xác nhận thành công hoặc trạng thái đơn hàng không đồng nhất. Quan trọng hơn, **kiểm tra trong Java và cập nhật trong DB là hai hành động tách biệt**. Giá trị có thể đổi ở khoảng giữa chúng.

Một biến thể dẫn tới **lost update** rất rõ: hai request đọc `stock = 10`, mỗi request tính `newStock = 9` trong Java, rồi cùng chạy:

~~~sql
UPDATE products SET stock = 9 WHERE id = 101;
~~~

Hai câu cập nhật đều có thể thành công, nhưng tồn kho chỉ giảm từ 10 xuống 9 dù đã xử lý hai yêu cầu mua hàng. Đó là ghi đè dữ liệu dựa trên giá trị cũ.

### 3.1. Lịch thực thi làm mất một cập nhật

| Thứ tự | Transaction A | Transaction B | Tồn kho đã commit |
| --- | --- | --- | --- |
| T0 | — | — | 10 |
| T1 | Đọc 10, tính 9 | — | 10 |
| T2 | — | Đọc 10, tính 9 | 10 |
| T3 | `UPDATE SET stock = 9`, commit | — | 9 |
| T4 | — | `UPDATE SET stock = 9`, commit | 9 |
| T5 | Trả thành công | Trả thành công | **9 thay vì 8** |

Ở một số engine, B phải chờ A nhả khóa hàng rồi mới cập nhật. Việc **chờ khóa không làm phép tính `newStock = 9` ở Java tự được tính lại**. B vẫn có thể ghi một giá trị đã cũ.

Ngay cả nếu đặt toàn bộ phương thức mua hàng trong `synchronized`, vấn đề vẫn tồn tại khi A và B chạy trên các JVM khác nhau, hoặc khi mã/tiến trình khác bỏ qua monitor Java đó.

## 4. Giải pháp cơ bản: chuyển bất biến vào một câu SQL nguyên tử

Khi nghiệp vụ là “trừ `quantity` khỏi tồn kho **chỉ khi** còn đủ”, diễn đạt cả điều kiện và phép trừ trong **cùng một lệnh UPDATE**:

~~~sql
UPDATE products
SET stock = stock - :quantity
WHERE id = :product_id
  AND stock >= :quantity;
~~~

Cú pháp `:quantity`/`:product_id` là cách ký hiệu tham số trong ví dụ; JDBC trực tiếp sử dụng dấu `?`. Ứng dụng phải kiểm tra `quantity > 0` (và nên có validation tại biên API) trước khi chạy.

Cơ sở dữ liệu thực thi điều kiện và thay đổi bên trong cùng một statement. Ở PostgreSQL READ COMMITTED, các `UPDATE` cùng một hàng được phối hợp qua khóa hàng; nếu phải chờ giao dịch khác commit, lệnh tiếp theo sẽ kiểm tra lại điều kiện trên phiên bản hàng thích hợp. Với tồn kho ban đầu là 1, **chỉ một lệnh trừ 1 có thể cập nhật thành công**, lệnh kia tác động 0 hàng khi thấy không còn đủ.

### 4.1. Ví dụ Java/JDBC đầy đủ

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

    /**
     * @return true nếu trừ tồn kho thành công;
     *         false nếu không có sản phẩm hoặc không đủ tồn kho.
     */
    public boolean reserve(long productId, int quantity)
            throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        String sql = """
                UPDATE products
                SET stock = stock - ?
                WHERE id = ?
                  AND stock >= ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setInt(1, quantity);
            statement.setLong(2, productId);
            statement.setInt(3, quantity);

            // Mỗi lời gọi lấy một Connection riêng từ DataSource.
            // Ví dụ một statement này dùng autocommit mặc định.
            int changedRows = statement.executeUpdate();
            return changedRows == 1;
        }
    }
}
~~~

Ví dụ dùng cú pháp Java 17 và giả định connection của ví dụ được cấp ở chế độ `autoCommit = true`. Nếu tầng ứng dụng đang quản lý một transaction lớn hơn thì **việc thành công của statement chưa tương đương commit thành công**: dịch vụ chỉ nên xác nhận nghiệp vụ sau khi toàn bộ transaction đã commit.

**Ý nghĩa của số hàng bị thay đổi:**

- `1`: tại thời điểm statement thực thi, đã có hàng phù hợp và phép trừ được áp dụng trong transaction.
- `0`: sản phẩm không tồn tại hoặc không đủ tồn kho; ứng dụng có thể truy vấn thêm nếu phải phân biệt hai trường hợp.
- Exception: transaction hoặc câu lệnh lỗi; cần xử lý theo loại lỗi, không biến mọi `SQLException` thành “hết hàng”.

Ràng buộc `CHECK (stock >= 0)` vẫn hữu ích vì nó bảo vệ database nếu sau này có code path khác bỏ quên điều kiện `WHERE`. **Ràng buộc của schema là tuyến bảo vệ chung cho tất cả client**, không phụ thuộc Java method nào được gọi.

### 4.2. Vì sao `UPDATE stock = stock - 1` khác `UPDATE stock = 9`?

Với một statement như `stock = stock - 1`, phép thay đổi dựa trên trạng thái mà DB xử lý khi lệnh ghi thực sự thực hiện. Với `stock = 9`, giá trị 9 đã được tính từ thông tin có thể cũ ở Java; DB không biết rằng phép ghi này tượng trưng cho “trừ 1” và không tự thay đổi nó thành 8.

Tuy vậy, một phép `UPDATE` đơn hàng không tự giải quyết toàn bộ quy trình đặt hàng. Nếu phải **trừ tồn kho, ghi đơn, ghi chi tiết đơn** thì tất cả các thay đổi DB liên quan cần được phối hợp trong một transaction, với xử lý rollback khi có lỗi.

## 5. Giữ đúng nguyên tử khi một nghiệp vụ gồm nhiều câu lệnh

Ví dụ quy trình đặt hàng cơ bản:

~~~sql
BEGIN;

UPDATE products
SET stock = stock - 1
WHERE id = 101 AND stock >= 1;

-- Ứng dụng kiểm tra: phải có đúng 1 hàng được cập nhật.
-- Nếu không thì ROLLBACK và báo hết hàng.

INSERT INTO orders (id, product_id, quantity)
VALUES (5001, 101, 1);

COMMIT;
~~~

Bảng `orders` ở đây là một phần giả định của ứng dụng; ví dụ chỉ thể hiện **ranh giới transaction**, không phải schema hoàn chỉnh. Nếu INSERT thất bại, transaction phải rollback để tồn kho không bị trừ mà không có đơn hàng.

Trên JDBC, cần bảo đảm hai statement chạy **trên cùng một Connection** và trong cùng transaction:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // UPDATE tồn kho bằng connection, kiểm tra số hàng = 1.
        // INSERT đơn hàng bằng cùng connection.
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackEx) {
            ex.addSuppressed(rollbackEx);
        }
        throw ex;
    }
}
~~~

Đây là khung điều phối transaction, chưa phải hàm đặt hàng đầy đủ. Các câu lệnh bên trong phải sử dụng `connection` được truyền xuống; nếu repository tự mở connection khác, thao tác đó có thể nằm **ngoài** transaction. Khi sử dụng Spring `@Transactional`, cần hiểu transaction manager liên kết connection và lời gọi repository như thế nào.

**Khóa Java và transaction DB là hai cơ chế khác nhau.** Monitor của `synchronized` gắn với object ở JVM; khóa hàng DB gắn với transaction và được giải phóng theo các quy tắc commit/rollback của engine. Không được suy luận rằng kết thúc một block `synchronized` đồng nghĩa transaction đã commit, nhất là khi commit do transaction interceptor ở bên ngoài lời gọi method thực hiện.

## 6. Optimistic locking: cập nhật chỉ khi phiên bản chưa đổi

Đối với biểu mẫu chỉnh sửa, nghiệp vụ đọc rồi xử lý lâu hoặc cần người dùng xác nhận, có thể dùng **optimistic locking**. Mỗi hàng có cột phiên bản tăng sau cập nhật:

~~~sql
ALTER TABLE products
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
~~~

Đầu tiên ứng dụng đọc:

~~~sql
SELECT id, stock, version
FROM products
WHERE id = 101;
-- Giả sử stock = 10, version = 7.
~~~

Khi lưu thay đổi, ứng dụng gửi phiên bản đã đọc:

~~~sql
UPDATE products
SET stock = 9,
    version = version + 1
WHERE id = 101
  AND version = 7;
~~~

Nếu một giao dịch khác đã sửa hàng và tăng `version` lên 8, statement này tác động **0 hàng**. Ứng dụng nhận biết xung đột, không ghi đè âm thầm; nó có thể hiển thị thông báo, tải lại dữ liệu hoặc tính lại và retry **nếu thao tác an toàn khi lặp**.

Với JPA/Hibernate, `@Version` thường biểu diễn nguyên tắc này, nhưng vẫn phải xác định các câu UPDATE ngoài ORM có tuân thủ việc cập nhật version hay không. Chỉ thêm cột `version` nhưng một client khác vẫn cập nhật mà không tăng version sẽ làm suy yếu cơ chế phát hiện xung đột.

| Cách làm | Đặc tính | Khi nào phù hợp? |
| --- | --- | --- |
| `UPDATE ... SET stock = stock - ? WHERE stock >= ?` | Kiểm tra và thay đổi nguyên tử trong DB | Trừ/tăng số lượng theo điều kiện cụ thể |
| `UPDATE ... WHERE version = ?` | Phát hiện dữ liệu đổi từ lúc đọc | Biểu mẫu sửa, read-modify-write có giá trị đã tính ở ứng dụng |
| `SELECT ... FOR UPDATE` | Khóa hàng trước khi xử lý tiếp | Cần giữ quyền cập nhật một hàng trong một transaction ngắn |
| `UNIQUE` hoặc khóa chính | Ràng buộc trạng thái hợp lệ ở DB | Không cho tạo trùng mã, ghế, yêu cầu duy nhất |
| `SERIALIZABLE` | Hướng tới kết quả tương đương lịch thực thi tuần tự | Bất biến nhiều hàng/giao dịch khó bảo vệ bằng một UPDATE |

Không có giải pháp nào tối ưu cho tất cả trường hợp. Chọn theo bất biến, tần suất tranh chấp, độ phức tạp xử lý và mức cô lập của DB.

## 7. Pessimistic locking: khóa hàng trong transaction

Khi nghiệp vụ phải đọc một hàng rồi thực hiện vài bước trước khi cập nhật, PostgreSQL có `SELECT ... FOR UPDATE`:

~~~sql
BEGIN;

SELECT stock
FROM products
WHERE id = 101
FOR UPDATE;

-- Kiểm tra logic nghiệp vụ, rồi cập nhật.
UPDATE products
SET stock = stock - 1
WHERE id = 101 AND stock >= 1;

COMMIT;
~~~

Khóa hàng được DB điều phối giữa các kết nối, kể cả từ những JVM khác. Một giao dịch khác cố khóa hoặc cập nhật hàng xung đột có thể phải chờ; thời gian chờ và chi tiết khóa phụ thuộc engine cùng mức cô lập.

Không giữ transaction đang khóa hàng trong khi chờ API ngoài, input người dùng hoặc xử lý lâu không cần thiết. Thời gian giữ khóa dài làm tăng độ trễ và có thể gây deadlock khi nhiều transaction lấy khóa theo thứ tự khác nhau.

**Giới hạn cần nhớ:** `FOR UPDATE` khóa những hàng được chọn theo quy tắc DB; nó không bảo đảm “mọi hàng có thể xuất hiện trong tương lai” đều bị khóa. Nếu hai giao dịch cùng kiểm tra điều kiện trên **một tập hàng** rồi mỗi giao dịch tạo hàng mới, chỉ khóa những hàng đang tồn tại có thể không bảo vệ được bất biến. Cần dùng UNIQUE, locking phù hợp hoặc SERIALIZABLE tùy ngữ cảnh.

### 7.1. Deadlock không phải lỗi thread safety của Java

Ví dụ:

~~~text
Transaction A: khóa hàng product 10 -> chờ hàng product 20
Transaction B: khóa hàng product 20 -> chờ hàng product 10
~~~

Đây là vòng chờ khóa ở database. DBMS có thể phát hiện và hủy một transaction. `synchronized` ở JVM không tự giải quyết vì các transaction có thể đến từ nhiều tiến trình. Những cách giảm nguy cơ gồm: lấy khóa theo một thứ tự nhất quán, giữ transaction ngắn, chỉ khóa dữ liệu cần thiết và xử lý lỗi deadlock/serialization bằng retry có giới hạn khi thao tác an toàn.

## 8. Check-then-insert: ràng buộc UNIQUE thay cho kiểm tra tại Java

Một trường hợp phổ biến là giữ một ghế xem phim cho tối đa một người trong mỗi suất chiếu. Đoạn logic sau **không an toàn** dưới tải đồng thời:

~~~text
if (SELECT COUNT(*) FROM reservations
    WHERE event_id = ? AND seat_id = ?) == 0:
    INSERT INTO reservations(...)
~~~

Hai transaction có thể cùng thấy chưa có reservation rồi cùng INSERT. Việc khóa một object Java trong một instance không ngăn request ở instance khác.

Đặt bất biến vào schema:

~~~sql
CREATE TABLE reservations (
    tenant_id BIGINT NOT NULL,
    event_id  BIGINT NOT NULL,
    seat_id   BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, event_id, seat_id)
);
~~~

Với PostgreSQL, thao tác đặt chỗ có thể viết:

~~~sql
INSERT INTO reservations (tenant_id, event_id, seat_id, user_id)
VALUES (42, 730, 15, 9001)
ON CONFLICT (tenant_id, event_id, seat_id)
DO NOTHING;
~~~

Nếu hai request cùng đặt một ghế, chỉ một bản ghi có thể tồn tại cho bộ khóa duy nhất; request còn lại không tạo được hàng trùng. Ứng dụng phải kiểm tra số hàng INSERT thành công (`1` hoặc `0`) và chỉ báo “giữ ghế thành công” khi giao dịch có hiệu lực.

Tùy nghiệp vụ, có thể dùng `INSERT ... ON CONFLICT DO UPDATE` nhưng phải rất cẩn thận: tự động ghi đè `user_id` của người đặt trước sẽ phá hỏng ý nghĩa “một ghế chỉ một người được chọn”.

**Tham chiếu tenant là điều kiện dữ liệu và bảo mật, không chỉ để tối ưu truy vấn.** Quyền được đặt ghế cho tenant/event nào vẫn phải được xác thực tại tầng ứng dụng hoặc bằng chính sách DB thích hợp.

## 9. Giao dịch và mức cô lập giải quyết phạm vi rộng hơn khóa một hàng

Một transaction cho phép gộp các thay đổi thành đơn vị commit/rollback. **Isolation** quyết định cách transaction quan sát và tương tác với cập nhật từ transaction khác.

Ví dụ ở PostgreSQL:

- `READ COMMITTED`: `SELECT` thông thường có snapshot theo từng statement, nên hai lần đọc có thể khác nhau khi transaction khác commit.
- `REPEATABLE READ`: `SELECT` thông thường sử dụng snapshot nhất quán trong transaction, nhưng không tự bảo đảm mọi bất biến liên hàng.
- `SERIALIZABLE`: hướng đến lịch thực thi tương đương một thứ tự tuần tự; transaction có thể bị hủy với lỗi serialization và phải retry đúng cách.

**Không có mức isolation nào thay thế việc mô tả rõ bất biến dữ liệu.** Dùng mức cao nhất cho mọi giao dịch có thể tăng xung đột và chi phí; ngược lại READ COMMITTED đủ cho nhiều thao tác khi điều kiện nghiệp vụ đã được thực thi nguyên tử trong SQL hoặc bằng constraint.

### 9.1. Ví dụ write skew trên nhiều hàng

Giả sử quy định: trong một ca trực phải luôn có **ít nhất một bác sĩ đang trực**. Hai bác sĩ A và B đều đang trực; hai transaction đồng thời:

1. Transaction T1 kiểm tra số bác sĩ đang trực là 2; quyết định cho A nghỉ.
2. T2 cũng kiểm tra số bác sĩ đang trực là 2; quyết định cho B nghỉ.
3. T1 cập nhật hàng của A; T2 cập nhật hàng của B. Hai transaction sửa **hai hàng khác nhau**.
4. Nếu cả hai commit mà không có cơ chế bảo vệ đủ mạnh, kết quả còn 0 người trực, vi phạm bất biến.

Khóa hoặc version **riêng trên hàng A** không trực tiếp xung đột với phép cập nhật **hàng B**. Một giải pháp có thể là SERIALIZABLE với retry, khóa một hàng “đại diện ca trực”, hoặc tái thiết kế dữ liệu/constraint phù hợp. Đây là lý do phải phân biệt tranh chấp trên **một hàng** với bất biến trên **một tập hàng**.

### 9.2. Khác biệt engine

PostgreSQL, MySQL InnoDB và SQL Server đều hỗ trợ transaction, nhưng có khác biệt về locking, snapshot và cách hiện thực các mức isolation. Ví dụ, READ COMMITTED có thể dùng snapshot theo statement ở PostgreSQL, trong khi SQL Server có thể dựa trên khóa hoặc row versioning tùy cấu hình. Vì vậy, kết luận về việc đọc lại, chờ khóa hay retry phải được kiểm chứng trên **DBMS thật** của hệ thống.

## 10. Phạm vi chia sẻ JDBC, connection pool và transaction manager

Một API Java thường có các thành phần:

~~~text
HTTP threads
    |
    v
Service / @Transactional
    |
    v
Repository / DAO
    |
    v
DataSource / connection pool
    |
    v
JDBC Connection ---- SQL transaction ---- Database
~~~

Các quy tắc quan trọng:

- Một `DataSource` được thiết kế để cung cấp connection cho nhiều request; các pool phổ biến được thiết kế cho truy cập đồng thời. **Không chia sẻ cùng `Connection`, `PreparedStatement` hoặc `ResultSet` cho nhiều thread** trừ khi driver/hợp đồng cụ thể cho phép và có phối hợp phù hợp.
- Mỗi request/transaction phải dùng đúng connection và ranh giới transaction. `@Transactional` không biến object Java thành thread-safe; `synchronized` không tự gộp nhiều statement JDBC thành một transaction.
- Với JDBC thủ công, `autoCommit = true` thường khiến mỗi statement là một transaction riêng. Nếu nghiệp vụ cần cập nhật nhiều bảng cùng nhau, thiết lập và quản lý transaction hoặc dùng transaction manager.
- Connection pool làm tăng khả năng nhiều transaction chạy đồng thời; cấu hình pool là công cụ giới hạn tài nguyên, **không phải khóa dữ liệu nghiệp vụ**.
- Không để shared mutable state (như `lastOrderId`, `currentCustomer`) trong singleton service/repository mà không có bảo vệ. Lỗi này thuộc phạm vi thread safety và có thể xảy ra ngay cả khi các câu SQL bên dưới đúng.
- Với ORM, kiểm tra câu SQL thực mà nó phát ra, quy tắc flush và transaction boundary. Entity manager/session không nên tùy tiện chia sẻ giữa nhiều thread.

Một ứng dụng có thể chứa một lớp service hoàn toàn stateless, chỉ dùng biến local và bất biến đầu vào, nên bản thân service an toàn cho nhiều thread. Tuy vậy, **hai lời gọi service vẫn có thể xung đột tại DB** nếu cùng chỉnh sửa một bản ghi.

## 11. Retry, idempotency và tác dụng phụ bên ngoài

Giả sử người dùng bấm “mua hàng” hai lần hoặc client gửi lại request sau timeout. Hai request có thể đều hợp lệ ở tầng thread safety và đều thực hiện một transaction riêng. **Kiểm soát đồng thời không tự loại bỏ yêu cầu trùng lặp nghiệp vụ.**

Một chiến lược phổ biến là sử dụng **idempotency key** duy nhất cho một yêu cầu logic, kèm ràng buộc UNIQUE ở database:

~~~sql
CREATE TABLE purchase_requests (
    tenant_id       BIGINT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status          TEXT NOT NULL,
    order_id        BIGINT,
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

Các request mang cùng khóa phải được điều phối sao cho một yêu cầu logic chỉ được xử lý theo quy tắc đã định; ứng dụng cần xét trạng thái `IN_PROGRESS`, `COMPLETED` hoặc lỗi khi retry. **Chỉ tạo bảng UNIQUE không tự hoàn thiện toàn bộ protocol idempotency**: transaction nào ghi kết quả, khóa bao lâu, request thứ hai nhận phản hồi gì đều cần thiết kế.

Khi transaction deadlock hoặc gặp serialization failure, có thể retry toàn bộ nghiệp vụ **nếu nó an toàn khi lặp**. Giới hạn số lần, thêm backoff phù hợp và xem xét mã lỗi theo DBMS. Đừng retry vô điều kiện mọi SQLException, đặc biệt lỗi ràng buộc, dữ liệu sai hoặc quyền truy cập.

Nếu một transaction đồng thời gửi email hoặc gọi cổng thanh toán, rollback database **không thể thu hồi** cuộc gọi ngoài đã thực hiện. Cần xem xét cơ chế outbox, trạng thái xử lý, idempotency và khả năng bù trừ. Khóa Java và khóa DB không tạo ra transaction phân tán tự động.

## 12. Kiểm thử đúng phạm vi: dùng nhiều kết nối độc lập

Kiểm thử chỉ tạo nhiều thread cùng gọi một phương thức `synchronized` trong một JVM chưa chứng minh ứng dụng đúng khi triển khai nhiều bản sao.

Để tái hiện lost update theo kiểu đọc – tính – ghi trên PostgreSQL, chuẩn bị bảng kiểm thử `products` và đặt `stock = 10`. Mở hai phiên SQL độc lập:

| Bước | Phiên A | Phiên B |
| --- | --- | --- |
| 1 | `BEGIN ISOLATION LEVEL READ COMMITTED;` | `BEGIN ISOLATION LEVEL READ COMMITTED;` |
| 2 | `SELECT stock ... WHERE id=101;` → 10 | — |
| 3 | — | `SELECT stock ... WHERE id=101;` → 10 |
| 4 | `UPDATE products SET stock=9 WHERE id=101;` | — |
| 5 | `COMMIT;` | — |
| 6 | — | `UPDATE products SET stock=9 WHERE id=101;` |
| 7 | — | `COMMIT;` |
| 8 | `SELECT stock` → 9 | Kỳ vọng nghiệp vụ hai lần trừ: 8 |

Sau đó khởi tạo lại `stock = 10` và thử cùng lịch với hai statement:

~~~sql
UPDATE products
SET stock = stock - 1
WHERE id = 101 AND stock >= 1;
~~~

Nếu cả hai giao dịch thành công, tồn kho cuối cùng là 8. Nếu đặt tồn kho ban đầu là 1, chỉ một lần trừ có thể cập nhật một hàng; lần còn lại phải ghi nhận `0` hàng. Mỗi lần thử cần **kiểm tra số hàng bị tác động, commit thực tế và trạng thái cuối**.

Khi kiểm thử ứng dụng, tăng phạm vi dần:

1. **Unit test JVM:** chứng minh counter/cache dùng chung không bị race condition trong một instance.
2. **Integration test DB:** chạy hai connection thật với lịch thực thi có kiểm soát, kiểm tra kết quả commit, constraint và số hàng cập nhật.
3. **Nhiều instance:** gửi request đồng thời đến hai tiến trình Java độc lập cùng dùng DB; kiểm tra rằng bất biến vẫn đúng.
4. **Failure test:** mô phỏng transaction rollback, deadlock, timeout trước/sau commit và request gửi lại; xác minh idempotency và không mất dữ liệu nghiệp vụ.
5. **Kiểm tra dưới tải:** theo dõi transaction throughput, p95/p99, lock wait, deadlock, CPU/IO và pool saturation; tối ưu sau khi đã chứng minh đúng đắn.

Thử nghiệm được thực hiện trên dữ liệu độc lập; không chạy kịch bản phá dữ liệu thật ở production. Khi một request timeout ở client, kết quả commit có thể chưa chắc chắn đối với client. Thiết kế API cần cơ chế tra cứu trạng thái/idempotency thay vì mặc nhiên cho rằng transaction thất bại.

## 13. Những ngộ nhận thường gặp

**“Method được đánh dấu `synchronized` thì dữ liệu DB được an toàn.”** Chỉ đúng đối với những truy cập đồng bộ bằng **cùng monitor trong cùng JVM**; nó không khóa các tiến trình hoặc client khác của database.

**“Dùng `AtomicInteger` để giữ tồn kho là đủ.”** Bộ đếm nguyên tử bảo vệ một giá trị RAM; trạng thái có thể không khớp với tồn kho đã commit trong DB, đặc biệt khi restart hoặc chạy nhiều node.

**“Đã có `@Transactional` thì không xảy ra lost update.”** Transaction tạo ranh giới commit/rollback nhưng tại mức cô lập thông dụng, kiểu đọc – tính – ghi có thể vẫn ghi đè giá trị cũ. Cần điều kiện nguyên tử, version, khóa hoặc isolation phù hợp.

**“SELECT kiểm tra không trùng rồi INSERT là an toàn.”** Hai giao dịch có thể cùng thấy dữ liệu chưa tồn tại. Đặt quy tắc duy nhất trong schema, rồi xử lý conflict có chủ đích.

**“Chỉ cần tăng mọi transaction lên SERIALIZABLE.”** SERIALIZABLE có thể phù hợp với bất biến phức tạp, nhưng cần hiểu cách engine phát hiện xung đột, xử lý retry và tác động hiệu năng. Bất biến đơn giản thường diễn đạt rõ hơn bằng constraint hoặc một conditional UPDATE.

**“Row lock bảo vệ mọi hàng thỏa một điều kiện trong tương lai.”** Khóa hàng hiện có không tự bảo vệ tập kết quả trước thao tác insert gây phantom; cần xác định bất biến trên hàng hay trên tập hàng.

**“JVM chạy một instance nên khóa Java sẽ luôn đủ.”** Bối cảnh triển khai có thể thay đổi: scale-out, batch worker, migration script, console admin, dịch vụ khác. Quy tắc dữ liệu bền vững nên được bảo vệ tại điểm chung mà mọi writer phải đi qua.

## 14. Bài tập thực hành

**Bài 1 — phân loại lỗi.** Một singleton Java service chứa `HashMap<Long, String>` được nhiều HTTP thread ghi đồng thời; cùng lúc hai service instance đều đọc `stock=5`, tính `4` và ghi `stock=4`. Xác định lỗi nào thuộc an toàn luồng JVM, lỗi nào thuộc đồng thời database. Đề xuất một giải pháp riêng cho mỗi lỗi.

*Gợi ý:* `HashMap` dùng chung cần thiết kế lại thành dữ liệu bất biến, cấu trúc concurrent hoặc đồng bộ hóa đúng; thao tác cập nhật tồn kho cần DB atomic UPDATE/optimistic locking. Chỉ đổi `HashMap` thành `ConcurrentHashMap` không sửa lỗi lost update.

**Bài 2 — sửa quy trình giữ ghế.** Hai người cùng đặt `seat_id=15` cho `event_id=730` trong tenant 42. Viết một schema UNIQUE phù hợp và SQL INSERT giải quyết conflict. Giải thích vì sao `SELECT COUNT(*)` trước INSERT chưa đủ.

**Bài 3 — xác định transaction boundary.** Một thao tác mua hàng cần trừ 1 sản phẩm, tạo đơn và ghi một sự kiện gửi email. Hãy xác định những thay đổi phải ở cùng transaction DB, cách kiểm tra số hàng UPDATE, và cách dùng outbox để xử lý email khi commit thành công. Giải thích việc retry khi client mất kết nối sau COMMIT.

**Bài 4 — đo tranh chấp.** Dùng hai connection trên database thử nghiệm để chạy cùng lúc conditional UPDATE trên một sản phẩm tồn kho 1. Dự đoán số lần UPDATE trả 1 và số lần trả 0, kiểm tra tồn kho cuối và lý do `synchronized` trên một Java service singleton không đủ chứng minh kết quả cho hai JVM.

## Ghi nhớ

**Thread safety bảo vệ tính nhất quán của trạng thái chia sẻ trong phạm vi JVM; kiểm soát đồng thời tại kho dữ liệu bảo vệ các bất biến bền vững trước nhiều transaction và nhiều tiến trình.** Một ứng dụng Java cần cả hai, nhưng chúng xử lý các ranh giới khác nhau. Khi quy tắc nghiệp vụ nằm trên dữ liệu của database, hãy thực thi nó càng gần dữ liệu càng tốt bằng **constraint, SQL nguyên tử, transaction, khóa hoặc kiểm tra phiên bản**, rồi kiểm thử trên nhiều kết nối và nhiều instance.
