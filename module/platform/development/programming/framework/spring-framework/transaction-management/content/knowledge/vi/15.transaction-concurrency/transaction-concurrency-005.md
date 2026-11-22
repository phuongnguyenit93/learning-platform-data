# Thao tác cập nhật nguyên tử thay cho đọc rồi ghi thiếu bảo vệ

## 1. Vấn đề: câu lệnh đúng nhưng kết quả sai khi có nhiều request

Trong một ứng dụng Spring có nhiều request đồng thời, mẫu code rất quen thuộc là **đọc giá trị, tính toán trong Java, rồi ghi lại**:

```java
int current = jdbc.queryForObject(
    "SELECT total FROM counters WHERE id = ?",
    Integer.class, 1);

int next = current + 10;

jdbc.update(
    "UPDATE counters SET total = ? WHERE id = ?",
    next, 1);
```

Nếu chỉ có một request, code có vẻ hợp lý. Nhưng khi hai transaction đọc cùng giá trị ban đầu trước khi một trong hai ghi lại, cả hai có thể tính cùng một kết quả và ghi đè thay đổi của nhau. Đây là ví dụ điển hình của **lost update (cập nhật bị mất)** khi triển khai *read–modify–write* không có cơ chế kiểm soát concurrency.

Thay thế phù hợp cho phép cộng đơn giản:

```sql
UPDATE counters
SET total = total + 10
WHERE id = 1;
```

Đây là **một lệnh SQL cập nhật nguyên tử ở phía database**: phép cộng sử dụng giá trị hàng mà database đang cập nhật, thay vì dựa trên bản sao `current` đã đọc trước đó trong ứng dụng. Với PostgreSQL ở `READ COMMITTED`, các writer cập nhật cùng hàng được phối hợp bởi row locking; writer sau có thể phải chờ writer trước và tiếp tục với phiên bản hàng đã cập nhật.

Một điều kiện nghiệp vụ như “chỉ giảm tồn kho nếu còn đủ” còn cần đưa **điều kiện kiểm tra** vào chính câu `UPDATE`:

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1 AND stock >= 5;
```

Sau đó **kiểm tra số hàng thực sự được cập nhật** để biết yêu cầu có thành công không. Không được suy ra thành công chỉ từ việc SQL không ném exception.

Mục tiêu bài học:

1. Nhìn rõ lịch chạy gây lost update dù code có `@Transactional`.
2. Phân biệt **lệnh SQL nguyên tử**, **giao dịch nhiều bước**, **điều kiện nghiệp vụ** và **idempotency**.
3. Dùng `JdbcTemplate.update(...)` và row count để triển khai tăng đếm, giảm tồn kho, trừ tiền có kiểm tra.
4. Hiểu cơ chế PostgreSQL `READ COMMITTED` chờ lock và kiểm tra lại `WHERE`.
5. Chạy ví dụ Java 17 + Spring Boot + PostgreSQL có **hai request đồng thời**: cách sai cho kết quả 110, cách nguyên tử cho 120, và chỉ một trong hai yêu cầu giữ hàng được chấp nhận.
6. Nhận diện khi nào cần optimistic locking, `SELECT ... FOR UPDATE`, constraint hoặc isolation mạnh hơn thay cho chỉ một câu `UPDATE`.

> **Nguyên tắc chính:** Khi nghiệp vụ có thể diễn tả bằng một phép biến đổi trên hàng hiện tại, ưu tiên để **database vừa kiểm tra vừa cập nhật**. Tránh chuyển các giá trị dễ thay đổi ra khỏi database rồi tính một giá trị tuyệt đối và ghi đè mà không có guard.

## 2. Lost update hình thành như thế nào?

Giả sử `counters(id=1, total=100)`. Hai giao dịch T1 và T2 đều muốn tăng 10.

### 2.1. Mẫu không an toàn

```text
Thời điểm      T1                                      T2
-----------    -------------------------------------   --------------------------------
t0             total đã commit = 100
t1             BEGIN
t2                                                     BEGIN
t3             SELECT total -> 100
t4                                                     SELECT total -> 100
t5             Java tính next = 110
t6                                                     Java tính next = 110
t7             UPDATE SET total=110 WHERE id=1
t8             COMMIT
t9                                                     UPDATE SET total=110 WHERE id=1
t10                                                    COMMIT
t11            Giá trị cuối cùng = 110
```

Hai request đều đã chạy `UPDATE` thành công và đều có thể nhận HTTP 200, nhưng giá trị cuối cùng chỉ tăng **10 thay vì 20**.

**Điểm lỗi:** T2 không bảo đảm rằng `current=100` vẫn là giá trị hợp lệ khi T2 ghi. Database có thể khóa và tuần tự hóa hai **lệnh UPDATE**, nhưng khóa đó **không tự sửa giá trị 110 cũ mà ứng dụng truyền vào**.

Mẫu `@Transactional` đơn thuần chưa giải quyết:

```java
@Transactional
public void addTen() {
    int current = jdbc.queryForObject(
        "SELECT total FROM counters WHERE id=1",
        Integer.class);

    jdbc.update(
        "UPDATE counters SET total=? WHERE id=1",
        current + 10);
}
```

`@Transactional` tạo transaction boundary; nó không mặc định biến hai SQL statements và phép tính Java ở giữa thành một phép cập nhật bất khả phân chia với transaction khác. Ở PostgreSQL `READ COMMITTED`, tình huống timeline trên hoàn toàn có thể xảy ra.

### 2.2. Tại sao không phải lúc nào test cũng thấy lỗi?

Nếu request thứ hai đọc **sau khi request thứ nhất đã commit**, nó có thể thấy 110 rồi ghi 120. Kết quả đúng do **lịch thực thi thuận lợi**, không phải code an toàn.

Vì vậy, test gọi hai thread rồi `sleep(100)` có thể bỏ sót lost update. Muốn minh họa ổn định, cần đồng bộ sao cho **cả hai đọc 100 rồi mới được phép viết**. Ví dụ chạy được ở phần 8 sử dụng `CyclicBarrier` cho đúng mục đích này.

### 2.3. Lost update khác non-repeatable read

- **Non-repeatable read:** một transaction đọc lại cùng hàng và thấy giá trị khác vì transaction khác đã commit.
- **Lost update:** một cập nhật ghi đè kết quả cập nhật trước đó do dùng giá trị cũ hoặc thiếu cơ chế kiểm tra xung đột.

Hai hiện tượng liên quan concurrency nhưng không đồng nhất. Kể cả khi ứng dụng chỉ SELECT **một lần**, việc ghi giá trị được tính từ snapshot cũ vẫn có thể gây lost update. Một cách sửa là chuyển logic vào SQL, một cách khác là dùng optimistic version check hoặc khóa đọc-để-ghi.

## 3. Cập nhật nguyên tử nghĩa là gì trong trường hợp này?

Với một hàng đơn lẻ:

```sql
UPDATE counters
SET total = total + 10
WHERE id = 1;
```

Database thực hiện việc đọc giá trị hàng cần cập nhật, đánh giá biểu thức `total + 10` và thay đổi hàng như **một SQL update statement** trong cơ chế transaction/concurrency của nó. Hai statement đồng thời trên cùng hàng phải được điều phối sao cho không âm thầm ghi đè chỉ vì cả hai đọc giá trị cũ từ Java trước đó.

Với PostgreSQL ở `READ COMMITTED`:

1. T1 lock hàng mục tiêu và thực hiện `total = total + 10`.
2. T2 muốn update cùng hàng có thể phải **đợi T1 kết thúc**.
3. Nếu T1 commit, T2 xử lý phiên bản đã cập nhật của hàng và **kiểm tra lại điều kiện `WHERE`**.
4. Nếu vẫn khớp, T2 áp phép biến đổi dựa trên giá trị hàng tương ứng; ví dụ 110 + 10 = 120.
5. Nếu T1 rollback, T2 có thể tiếp tục dựa trên trạng thái hợp lệ còn lại.

Đây là đặc điểm PostgreSQL được tài liệu transaction isolation mô tả cho `UPDATE` dưới `READ COMMITTED`. Không suy từ đó rằng tất cả database và mọi mức isolation hoạt động y hệt; PostgreSQL `REPEATABLE READ`/`SERIALIZABLE` có thể báo serialization error cho cạnh tranh cập nhật thay vì âm thầm tiếp tục.

### 3.1. Đúng cách và sai cách khi tăng bộ đếm

| Mẫu | Tính đúng đắn khi nhiều writer cùng tăng một hàng |
| --- | --- |
| `SELECT total` → Java `total + 10` → `UPDATE SET total=?` | **Nguy hiểm:** có thể ghi đè tính toán của writer khác |
| `UPDATE SET total=total+10 WHERE id=?` | Phép tăng trong một statement, phù hợp với bộ đếm đơn hàng |
| `SELECT ... FOR UPDATE` → Java tính → `UPDATE` trong cùng transaction | Có thể đúng nếu đọc khóa được giữ tới khi ghi/commit, nhưng dài và dễ giữ lock lâu |
| `UPDATE ... WHERE version=?` và kiểm tra row count | Optimistic compare-and-swap; khi xung đột cần retry/từ chối |
| `synchronized` trong một JVM rồi đọc/ghi | Không bảo vệ qua nhiều JVM/instance, batch job, ứng dụng khác ghi cùng DB |

**Lưu ý:** “UPDATE nguyên tử” ở đây là bảo đảm của **phép cập nhật SQL cụ thể**, không có nghĩa toàn bộ quy trình gồm thêm email, API, thanh toán ngoài hệ thống cũng là một transaction nguyên tử.

### 3.2. Kiểm tra số hàng cập nhật

Ngay cả câu đúng như `UPDATE counters SET total=total+10 WHERE id=?` cũng có thể cập nhật **0 hàng** nếu ID không tồn tại. Với khóa chính ID duy nhất, mong đợi:

- `1` hàng cập nhật: hàng mục tiêu đã được xử lý.
- `0` hàng cập nhật: không có hàng khớp; với lệnh có điều kiện có thể do không đủ tồn kho/điều kiện thất bại.
- `>1` hàng: trái với giả định “một ID duy nhất”, cần xem lại SQL/schema hoặc xử lý như lỗi.

`JdbcTemplate.update(...)` trả về số hàng ảnh hưởng, không trả về giá trị của cột sau khi cập nhật. Phải **kiểm tra kết quả** thay vì bỏ qua.

## 4. Đưa điều kiện nghiệp vụ vào chính UPDATE

Một counter tăng đơn giản không cần điều kiện phức tạp. Nhưng nghiệp vụ trừ số dư, giữ hàng hoặc giới hạn quota có điều kiện **chỉ được phép ghi khi trạng thái hiện tại thỏa predicate**.

### 4.1. Kiểu sai: kiểm tra một lần rồi ghi sau

Giả sử kho còn 7 món; hai khách cùng đặt 5:

```text
T1: SELECT stock -> 7; Java: 7 >= 5, cho phép đặt
T2: SELECT stock -> 7; Java: 7 >= 5, cho phép đặt
T1: UPDATE inventory SET stock=2 WHERE id=1; COMMIT
T2: UPDATE inventory SET stock=2 WHERE id=1; COMMIT
```

Hai yêu cầu đều được thông báo thành công, tổng hàng hứa bán là **10** dù tồn thực tế ban đầu chỉ **7**. Số tồn cuối `2` nhìn qua có vẻ không âm, nhưng hệ thống đã **oversell**.

Một biến thể cũng sai:

```java
int stock = readStock();
if (stock >= requested) {
    jdbc.update(
        "UPDATE inventory SET stock = stock - ? WHERE id = ?",
        requested, itemId);
}
```

Dù câu `UPDATE` trong nhánh `if` sử dụng phép trừ nguyên tử, **quyết định “còn đủ hàng” vẫn được đưa ra từ kết quả SELECT cũ**. Hai yêu cầu có thể cùng pass `if` rồi trừ, làm stock âm hoặc gặp constraint error. Phép biến đổi nguyên tử **không đủ** nếu predicate nghiệp vụ bị tách rời khỏi chính statement.

### 4.2. Kiểu đúng: một conditional UPDATE

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1
  AND stock >= 5;
```

Hai yêu cầu đồng thời trên hàng kho stock=7 không thể cùng thành công chỉ bằng cách nhìn snapshot 7 cũ ở Java:

- Yêu cầu được xử lý trước: giảm 7 → 2, số hàng cập nhật = 1.
- Yêu cầu còn lại: sau khi hàng được cập nhật, điều kiện `stock >= 5` không còn đúng; số hàng cập nhật = 0 ở PostgreSQL `READ COMMITTED`.
- Kết quả: **đúng một yêu cầu được chấp nhận**, kho còn 2.

Điều kiện `stock >= ?` nằm **trong cùng lệnh** với `stock = stock - ?`. Đó là điểm cốt lõi. Kiểm tra điều kiện rồi mới update trong một SQL khác không tương đương.

### 4.3. Kết hợp constraint ở database

Ví dụ schema PostgreSQL:

```sql
CREATE TABLE inventory (
    id INTEGER PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
```

`CHECK (stock >= 0)` là một hàng rào bổ sung: các writer khác không được phép làm stock âm mà vẫn commit theo thiết kế thông thường. Nó **không thay thế** conditional UPDATE: nếu chỉ có constraint, một trong hai request có thể nhận SQL exception thay vì kết quả nghiệp vụ “hết hàng”, và việc nhìn thấy số stock không âm vẫn chưa chứng minh không có oversell ở luồng cấp phát khác.

Hãy kết hợp:

1. **Atomic conditional UPDATE** để ra quyết định thành công/thất bại tại điểm ghi.
2. **DB constraint** để ngăn trạng thái bất hợp lệ dù có code path khác.
3. **Đếm hàng cập nhật** để phản ánh kết quả nghiệp vụ.
4. **Transaction rộng hơn** nếu cần ghi thêm đơn hàng hoặc ledger cùng với thay đổi stock.

### 4.4. Không cho đầu vào âm/0 thay đổi ý nghĩa

Nếu `requested=-5`, câu `stock = stock - requested` lại **tăng** tồn kho. Nếu `requested=0`, nó có thể trả row count 1 dù không có thay đổi hữu ích. Validate đầu vào:

```java
if (requested <= 0) {
    throw new IllegalArgumentException(
        "Quantity must be positive");
}
```

Tương tự với amount trừ tiền: yêu cầu positive, chọn kiểu số tiền phù hợp như `DECIMAL/NUMERIC` và `BigDecimal`, không dùng `double` cho số tiền đòi hỏi chính xác.

## 5. Ba mẫu SQL nên biết

### 5.1. Counter / số lượt / số lượng tăng giảm

```sql
UPDATE counters
SET total = total + 1
WHERE id = :id;
```

SQL trên minh họa **named parameter**, cần `NamedParameterJdbcTemplate` hoặc SQL client hỗ trợ named parameter; `JdbcTemplate` thuần dùng placeholder `?`. Đây là mẫu phù hợp khi cần tăng một bộ đếm dựa trên giá trị hiện tại.

Với thao tác giảm có điều kiện không âm:

```sql
UPDATE counters
SET total = total - :decrement
WHERE id = :id
  AND total >= :decrement;
```

Kiểm tra row count và validate `decrement > 0`.

### 5.2. Trừ tiền nếu đủ số dư

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :accountId
  AND balance >= :amount;
```

Nên có `CHECK (balance >= 0)` nếu nghiệp vụ cấm âm, ràng buộc kiểu số tiền chính xác, và idempotency/ledger khi xử lý request có thể được gửi lại.

Không dùng:

```text
balance = SELECT ...
if (balance >= amount) {
    UPDATE accounts SET balance = balance - amount
}
```

vì `if` đã nằm ngoài statement, trừ khi đã khóa thích hợp trên hàng trong cùng transaction. Ngay cả một statement an toàn về số dư **không tự bảo đảm toàn bộ nghiệp vụ chuyển tiền**; xem phần multi-row.

### 5.3. Compare-and-swap / optimistic version check

Khi không thể biểu diễn thay đổi bằng một phép số học đơn giản, có thể yêu cầu bản ghi **vẫn ở đúng version** mà client đã đọc:

```sql
UPDATE accounts
SET display_name = :newName,
    version = version + 1
WHERE id = :accountId
  AND version = :expectedVersion;
```

Nếu 1 hàng được cập nhật, thay đổi được chấp nhận. Nếu 0 hàng, có thể có conflict do writer khác đã tăng version, hoặc ID không tồn tại; cần **retry với dữ liệu mới hoặc báo conflict**, không được âm thầm trả thành công.

Điều kiện thiết yếu: **mọi code path sửa bản ghi cần tôn trọng cơ chế version** (hoặc có chiến lược tương thích). Nếu một writer dùng `UPDATE accounts SET ... WHERE id=?` nhưng không tăng version, optimistic locking ở code khác có thể không phát hiện thay đổi đó.

Spring Data JPA hỗ trợ `@Version` trong cơ chế optimistic locking cho managed entities; manual SQL compare-and-swap là mẫu tương tự ở mức row count. Không coi `@Version` và `UPDATE SET total=total+1` là cùng một công cụ; mỗi loại giải quyết kiểu cập nhật khác nhau.

## 6. Dùng `JdbcTemplate.update` đúng cách

Spring JDBC cung cấp API:

```java
int affected = jdbc.update(
    "UPDATE inventory " +
    "SET stock = stock - ? " +
    "WHERE id = ? AND stock >= ?",
    requested, productId, requested);
```

Kết quả `affected` là số hàng mà JDBC driver báo đã cập nhật. Với `id` là primary key và không có trigger bất thường trong ví dụ:

```java
public boolean reserveStock(
        JdbcTemplate jdbc,
        int productId,
        int requested) {

    if (requested <= 0) {
        throw new IllegalArgumentException(
            "Quantity must be positive");
    }

    int affected = jdbc.update(
        "UPDATE inventory SET stock = stock - ? " +
        "WHERE id = ? AND stock >= ?",
        requested, productId, requested);

    if (affected == 1) {
        return true;
    }
    if (affected == 0) {
        return false;
    }
    throw new IllegalStateException(
        "More than one row updated: " + affected);
}
```

Đây là một **method Java minh họa**; đặt trong một class, import `JdbcTemplate` và bảo đảm đúng DataSource. Phần 8 có project Spring Boot hoàn chỉnh.

**`false` ở đây nghĩa là không có hàng nào được giảm**. Nó có thể do:

- ID không tồn tại.
- Có hàng nhưng số tồn không đủ.
- Predicate khác không thỏa.

Một SELECT sau thất bại có thể giúp tạo thông báo chi tiết hơn, nhưng **không dùng SELECT sau đó để đảo lại quyết định `affected==0`**. Trạng thái có thể tiếp tục thay đổi vì request khác. Nếu cần phân biệt không tồn tại và thiếu hàng với guarantee chặt chẽ, hãy thiết kế model/API và kiểm soát transaction phù hợp.

### 6.1. Prepared parameters, không nối chuỗi SQL từ input

Đúng:

```java
jdbc.update(
    "UPDATE inventory SET stock=stock-? " +
    "WHERE id=? AND stock>=?",
    qty, id, qty);
```

Sai:

```java
String sql = "UPDATE inventory SET stock=stock-" + qty
    + " WHERE id=" + id;
```

Kể cả demo dùng số nguyên, hãy hình thành thói quen prepared parameters để tránh SQL injection ở các đường input khác, rõ kiểu dữ liệu và dễ kiểm thử.

### 6.2. `@Transactional` vẫn cần cho nghiệp vụ nhiều câu SQL

Một `UPDATE` đơn lẻ thường đã được database thực thi nguyên tử ở mức statement ngay cả khi application gọi ở chế độ autocommit. Nhưng nếu nghiệp vụ cần **giảm kho + tạo đơn + ghi ledger** thành một đơn vị commit/rollback, cần một transaction bao trọn những câu SQL đó:

```java
@Transactional
public void createOrder(int productId, int quantity) {
    int changed = jdbc.update(
        "UPDATE inventory SET stock=stock-? " +
        "WHERE id=? AND stock>=?",
        quantity, productId, quantity);

    if (changed != 1) {
        throw new InsufficientStockException(
            "Stock not available");
    }

    jdbc.update(
        "INSERT INTO orders(product_id, quantity) VALUES (?, ?)",
        productId, quantity);
}
```

Đây là **mảnh minh họa**, cần định nghĩa `InsufficientStockException extends RuntimeException` và bảng `orders`. Nếu INSERT thất bại sau khi giảm stock, default rollback cho runtime exception sẽ hoàn tác cả UPDATE stock khi hai SQL cùng thuộc transaction thực sự.

Không dùng `@Transactional` như “bùa” chống stale-read: chính điều kiện `UPDATE` mới là yếu tố tránh oversell trong trường hợp trên.

## 7. Cách database bảo vệ conditional UPDATE khi có tranh chấp

### 7.1. PostgreSQL READ COMMITTED

Giả sử stock 7, T1 và T2 cùng gửi:

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1 AND stock >= 5;
```

Với PostgreSQL `READ COMMITTED`, `UPDATE` tìm hàng đủ điều kiện; nếu một writer khác đang sửa cùng hàng, nó có thể **chờ** writer đó commit hoặc rollback. Khi writer trước commit, PostgreSQL tiếp tục với phiên bản hàng mới và **đánh giá lại `WHERE`** cho hàng mục tiêu. Vì 2 không còn lớn hơn hoặc bằng 5, statement sau sẽ cập nhật 0 hàng.

Điều này khiến **điều kiện và thay đổi ở cùng statement** trở nên quan trọng. Nếu T2 dùng:

```sql
UPDATE inventory
SET stock = 2
WHERE id = 1;
```

thì dù đã chờ lock, nó vẫn đặt literal 2 từ phép tính cũ. Row lock giúp điều phối truy cập DB, nhưng không biết ý nghĩa “đặt mua 5 hàng” và không biến literal cũ thành phép trừ đúng.

### 7.2. Không đồng nhất hành vi ở mọi isolation level

Ở PostgreSQL `REPEATABLE READ` hoặc `SERIALIZABLE`, một concurrent update có thể khiến một transaction bị hủy với serialization error thay vì thành công với row count 0 như kịch bản `READ COMMITTED`. Code production phải có chính sách retry hoặc trả lỗi phù hợp khi DB báo conflict; **không khẳng định row count luôn đủ để phân biệt mọi kết quả**.

Trong MySQL InnoDB, các locking/current reads, transaction isolation và unique/foreign key constraints có quy tắc riêng. Mẫu conditional UPDATE cũng hữu ích, nhưng cần test đúng engine/level/version. Đừng lấy output H2 làm chứng cứ tuyệt đối cho PostgreSQL hoặc MySQL.

### 7.3. Lock chỉ được giữ tới ranh giới transaction thích hợp

Để tránh deadlock và giữ throughput:

- Giữ transaction ngắn, **không gọi HTTP/email dài** khi đang giữ row lock trừ khi thiết kế bắt buộc và đã đánh giá kỹ.
- Có index/primary key phù hợp với `WHERE id=?` để tránh quét rộng, làm tăng phạm vi tranh chấp.
- Với nhiều hàng cần cập nhật, dùng thứ tự lock ổn định và xử lý deadlock/serialization retries có giới hạn.
- Chọn quy tắc nghiệp vụ rõ ràng nếu update 0 hàng: hết hàng, conflict, hay không tồn tại.

## 8. Ví dụ chạy được: unsafe vs atomic vs conditional reservation

Bài thực hành này cố ý sử dụng **PostgreSQL** để kiểm tra hành vi `READ COMMITTED` của chính database, không dựa vào in-memory simulation. Một project **Java 17 + Spring Boot 3.3.13 + Spring JDBC + PostgreSQL 16** có đủ mã nguồn và lệnh chạy. Số phiên bản cố định phục vụ tái hiện, **không có nghĩa là bản mới nhất**.

### 8.1. Cấu trúc project

```text
atomic-update-lab/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/atomic/
    │   ├── AtomicUpdateApplication.java
    │   └── AtomicOperations.java
    └── resources/
        └── application.yml
```

Dùng Gradle Wrapper của project do Spring Initializr/Gradle tạo ra, tương thích với Java 17 và Spring Boot 3.3. Đây là **project nhiều file**, không thể chạy từng file Java chỉ bằng `javac` khi thiếu classpath Spring.

**`settings.gradle`**

```groovy
rootProject.name = 'atomic-update-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot starter JDBC cung cấp `JdbcTemplate`, transaction infrastructure và connection pool (thường là HikariCP). PostgreSQL JDBC driver là runtime dependency; Boot quản lý phiên bản các starter/driver trong cấu hình này.

### 8.2. Database chỉ dành cho lab

Có thể tạo PostgreSQL container với Docker (cổng 55434 cần chưa bị sử dụng):

```bash
docker run -d --name atomic-lab-pg \
  -e POSTGRES_DB=atomiclab \
  -e POSTGRES_USER=atomiclab \
  -e POSTGRES_PASSWORD=local_only \
  -p 55434:5432 postgres:16
```

Trên Windows PowerShell, dùng một dòng:

```powershell
docker run -d --name atomic-lab-pg -e POSTGRES_DB=atomiclab -e POSTGRES_USER=atomiclab -e POSTGRES_PASSWORD=local_only -p 55434:5432 postgres:16
```

Kiểm tra database đã sẵn sàng:

```bash
docker exec atomic-lab-pg pg_isready -U atomiclab -d atomiclab
```

Password `local_only` là **mật khẩu demo**, không tái sử dụng trong production. Không mở PostgreSQL lab trên mạng không đáng tin; nếu cần, chỉ bind port localhost và cấu hình bảo mật theo môi trường.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:postgresql://localhost:55434/atomiclab"
    username: ${DB_USER:atomiclab}
    password: ${DB_PASSWORD:local_only}
    hikari:
      maximum-pool-size: 5
```

Pool 5 connection đủ để **hai transaction đồng thời** giữ connection trong thí nghiệm. Không dùng pool size=1 khi cả hai task cần mở transaction rồi đợi nhau tại barrier, vì worker thứ hai có thể không lấy được connection và worker thứ nhất sẽ đợi đến timeout.

### 8.3. Service với ba phương thức

**`src/main/java/demo/atomic/AtomicOperations.java`**

```java
package demo.atomic;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AtomicOperations {
    private final JdbcTemplate jdbc;

    public AtomicOperations(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Cố ý sai để biểu diễn lost update trong môi trường đồng thời.
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void unsafeAddTen(CyclicBarrier bothRead) {
        int current = jdbc.queryForObject(
            "SELECT total FROM counters WHERE id=1",
            Integer.class
        );

        // Cả hai giao dịch phải đọc 100 trước khi ghi lại.
        waitUntilBothRead(bothRead);

        jdbc.update(
            "UPDATE counters SET total=? WHERE id=1",
            current + 10
        );
    }

    // Đúng cho phép tăng đơn giản: dùng giá trị hiện tại ở DB.
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public int atomicAddTen() {
        return jdbc.update(
            "UPDATE counters SET total=total+10 WHERE id=1"
        );
    }

    // Vừa kiểm tra vừa thay đổi stock trong cùng statement.
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public boolean reserveFive() {
        int changed = jdbc.update(
            "UPDATE inventory " +
            "SET stock=stock-5 " +
            "WHERE id=1 AND stock>=5"
        );

        if (changed == 0) {
            return false;
        }
        if (changed == 1) {
            return true;
        }
        throw new IllegalStateException(
            "Unexpected updated row count: " + changed);
    }

    private static void waitUntilBothRead(CyclicBarrier barrier) {
        try {
            barrier.await(15, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Interrupted during demo", ex);
        } catch (BrokenBarrierException | TimeoutException ex) {
            throw new IllegalStateException(
                "Failed to coordinate concurrent reads", ex);
        }
    }
}
```

Giải thích:

- `unsafeAddTen` đọc số `current` **ra Java**, đồng bộ hai reader qua barrier rồi ghi một số **literal** `current+10`; không an toàn nhưng cần cho thí nghiệm đối chiếu.
- `atomicAddTen` làm phép cộng trực tiếp trong một câu `UPDATE`. `int` trả về là **số hàng cập nhật**, không phải giá trị `total`; với ID 1 tồn tại, mong đợi 1.
- `reserveFive` đưa `stock>=5` vào `WHERE` và dựa vào row count, không SELECT trước. Kết quả true/false biểu diễn thành công hay không thành công của thao tác giữ hàng.
- Mỗi method public được gọi qua bean proxy từ coordinator nên `@Transactional` có hiệu lực. `waitUntilBothRead` là helper static, không cần annotation.
- Barrier **chỉ phục vụ tái hiện lịch chạy**, không phải kỹ thuật nên dùng trong xử lý request production.

### 8.4. Runner khởi tạo dữ liệu và gọi hai worker

**`src/main/java/demo/atomic/AtomicUpdateApplication.java`**

```java
package demo.atomic;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class AtomicUpdateApplication {

    public static void main(String[] args) {
        SpringApplication.run(AtomicUpdateApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            JdbcTemplate jdbc,
            AtomicOperations operations) {

        return args -> {
            // Chỉ chạy trên database LAB.
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS counters (" +
                "id INTEGER PRIMARY KEY, " +
                "total INTEGER NOT NULL)"
            );

            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS inventory (" +
                "id INTEGER PRIMARY KEY, " +
                "stock INTEGER NOT NULL CHECK (stock >= 0))"
            );

            jdbc.execute("TRUNCATE TABLE counters, inventory");

            jdbc.update(
                "INSERT INTO counters(id, total) VALUES (1, 100)"
            );
            jdbc.update(
                "INSERT INTO inventory(id, stock) VALUES (1, 7)"
            );

            ExecutorService workers = Executors.newFixedThreadPool(2);

            try {
                // A. Hai transaction cùng SELECT 100 rồi ghi lại 110.
                CyclicBarrier bothRead = new CyclicBarrier(2);

                Future<?> unsafe1 =
                    workers.submit(() ->
                        operations.unsafeAddTen(bothRead));
                Future<?> unsafe2 =
                    workers.submit(() ->
                        operations.unsafeAddTen(bothRead));

                unsafe1.get(30, TimeUnit.SECONDS);
                unsafe2.get(30, TimeUnit.SECONDS);

                System.out.println(
                    "Unsafe final total: " + total(jdbc));

                // B. Reset tổng, hai request cùng dùng atomic UPDATE.
                jdbc.update(
                    "UPDATE counters SET total=100 WHERE id=1"
                );

                CountDownLatch startAtomic = new CountDownLatch(1);

                Future<Integer> atomic1 = workers.submit(() -> {
                    startAtomic.await();
                    return operations.atomicAddTen();
                });
                Future<Integer> atomic2 = workers.submit(() -> {
                    startAtomic.await();
                    return operations.atomicAddTen();
                });

                startAtomic.countDown();

                if (atomic1.get(30, TimeUnit.SECONDS) != 1
                        || atomic2.get(30, TimeUnit.SECONDS) != 1) {
                    throw new IllegalStateException(
                        "Counter row was not updated");
                }

                System.out.println(
                    "Atomic final total: " + total(jdbc));

                // C. Hai request cùng xin 5, tồn kho ban đầu chỉ 7.
                CountDownLatch startReserve = new CountDownLatch(1);

                Future<Boolean> reserve1 = workers.submit(() -> {
                    startReserve.await();
                    return operations.reserveFive();
                });
                Future<Boolean> reserve2 = workers.submit(() -> {
                    startReserve.await();
                    return operations.reserveFive();
                });

                startReserve.countDown();

                boolean ok1 = reserve1.get(30, TimeUnit.SECONDS);
                boolean ok2 = reserve2.get(30, TimeUnit.SECONDS);

                int accepted = (ok1 ? 1 : 0) + (ok2 ? 1 : 0);

                System.out.println(
                    "Accepted reservations: " + accepted);
                System.out.println(
                    "Remaining stock: " + stock(jdbc));
            } finally {
                workers.shutdownNow();
            }
        };
    }

    private static int total(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT total FROM counters WHERE id=1",
            Integer.class
        );
    }

    private static int stock(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT stock FROM inventory WHERE id=1",
            Integer.class
        );
    }
}
```

Điểm QA của runner:

- `CREATE TABLE IF NOT EXISTS` và `TRUNCATE` chỉ thao tác trên **hai bảng demo**, nhưng `TRUNCATE` xóa dữ liệu hiện có; dùng database lab riêng, tuyệt đối không trỏ nhầm production.
- Không có `@Transactional` trên runner. Hai task gọi `operations` qua **Spring proxy** từ thread khác nhau; mỗi lời gọi mở transaction riêng tại `READ_COMMITTED`.
- Sau hai `unsafe` futures hoàn tất, mọi transaction tương ứng đã hoàn tất qua proxy trước khi đọc `total`.
- `CyclicBarrier(2)` buộc cả hai task lấy được số `100` trước khi phép ghi diễn ra, nên lịch mất cập nhật được tái hiện có chủ đích.
- `CountDownLatch` đồng bộ thời điểm cho hai task atomic/reserve, nhưng tính đúng đắn của SQL **không phụ thuộc vào tốc độ thread**.
- Các thao tác reset dữ liệu được chạy **sau khi những task trước đã xong**, không sửa dữ liệu giữa lúc transaction trước vẫn chạy.

### 8.5. Chạy chương trình và stdout

Với Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Sau các log của Gradle/Spring Boot, chương trình in chính xác bốn dòng sau **khi database chạy, không có writer khác, không timeout và mã/config đúng như trên**:

```text
Unsafe final total: 110
Atomic final total: 120
Accepted reservations: 1
Remaining stock: 2
```

Giải thích:

1. **Unsafe 110:** cả hai cùng SELECT 100, mỗi bên tính `100+10=110` rồi viết literal 110; chỉ một lần tăng thực sự được phản ánh.
2. **Atomic 120:** reset về 100, hai câu `UPDATE total=total+10` cập nhật cùng hàng; mỗi lần 1 hàng, cuối cùng có 120.
3. **Accepted 1:** từ stock=7, yêu cầu đầu tiên giảm 5 thành 2; yêu cầu còn lại không thỏa `stock>=5` và nhận row count 0.
4. **Stock 2:** hệ thống chỉ chấp nhận lượng hàng thực sự có; không oversell.

Phần unsafe được thiết kế để **chứng minh lỗi**, không sao chép vào production. Nếu database đang ở một isolation khác (ví dụ PostgreSQL `REPEATABLE READ`) hoặc có trigger/constraint khác, một trong các transaction có thể bị abort thay vì hoàn tất lịch trên; đây là lý do ví dụ khai rõ `READ_COMMITTED` và dùng DB lab riêng.

## 9. Thực hành kiểm chứng bằng hai cửa sổ psql

Không cần Java để quan sát cơ chế khóa của database. Mở hai terminal `psql`/hai session riêng trên PostgreSQL sandbox. Khởi tạo khi không còn transaction đang mở:

```sql
CREATE TABLE IF NOT EXISTS manual_stock (
    id INTEGER PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);

TRUNCATE TABLE manual_stock;
INSERT INTO manual_stock(id, stock) VALUES (1, 7);
```

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE manual_stock
SET stock=stock-5
WHERE id=1 AND stock>=5;
-- UPDATE 1

-- Chưa COMMIT; giữ session ở trạng thái transaction mở.
```

**Session B (bắt đầu trong lúc A chưa commit):**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE manual_stock
SET stock=stock-5
WHERE id=1 AND stock>=5;
-- Có thể phải CHỜ row lock của Session A.
```

**Session A:**

```sql
COMMIT;
```

**Session B tiếp tục:**

```text
UPDATE 0
```

B thực hiện:

```sql
COMMIT;
SELECT stock FROM manual_stock WHERE id=1;
-- 2
```

Đây là timeline điển hình khi A commit trước: B chờ rồi kiểm tra lại `stock>=5` trên phiên bản mới; thấy stock=2 nên không cập nhật. Nếu A **ROLLBACK** thay vì commit, B có thể tiếp tục từ stock=7 và được cập nhật 1 hàng; kết quả phụ thuộc thời điểm/kết cục transaction trước, nhưng không vì snapshot cũ mà tự động trừ hai lần khi hàng không đủ.

**Đừng** chạy lab này trên DB thật có kết nối ứng dụng khác. Lệnh `TRUNCATE` sẽ xóa toàn bộ hàng của bảng demo.

## 10. UPDATE ... RETURNING: vừa cập nhật vừa lấy giá trị mới

PostgreSQL hỗ trợ `RETURNING` cho `UPDATE`:

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1 AND stock >= 5
RETURNING id, stock;
```

Nếu đủ hàng, statement trả một row gồm ID và số tồn **sau khi cập nhật**. Nếu không còn hàng thỏa điều kiện, nó trả **không có row**. Cách này tránh một `SELECT` riêng sau UPDATE chỉ để đọc lại số tồn, vốn có thể nhìn thấy thay đổi mới từ request khác trước khi ứng dụng đọc.

Trong Spring JDBC, query có `RETURNING` là SQL sinh **result set**. Có thể dùng `JdbcTemplate.query(...)`:

```java
List<Integer> remaining = jdbc.query(
    "UPDATE inventory " +
    "SET stock = stock - ? " +
    "WHERE id = ? AND stock >= ? " +
    "RETURNING stock",
    (rs, rowNum) -> rs.getInt("stock"),
    requested, productId, requested
);

if (remaining.isEmpty()) {
    // Không có hàng thỏa điều kiện.
} else if (remaining.size() == 1) {
    int newStock = remaining.get(0);
    // Đã cập nhật, có số tồn mới của chính statement.
} else {
    throw new IllegalStateException("Expected one inventory row");
}
```

Đây là một **mảnh code Java minh họa**; cần import `java.util.List`, có biến `jdbc`, `requested`, `productId`, và transaction manager phù hợp. PostgreSQL JDBC driver phải hỗ trợ câu `RETURNING` theo cách thông thường; không copy nguyên SQL này sang mọi dialect mà không xác minh.

Đừng viết:

```java
int affected = jdbc.update(
    "UPDATE inventory ... RETURNING stock");
```

rồi kỳ vọng `affected` là **số tồn mới**. `JdbcTemplate.update` được thiết kế trả **update count**, trong khi `RETURNING` trả row dữ liệu và thường dùng query API. Nếu dùng `queryForObject`, trường hợp 0 row có thể ném `EmptyResultDataAccessException`; `query` trả danh sách rỗng dễ xử lý như một thất bại điều kiện hơn.

## 11. Optimistic locking: khi cần đọc, tính toán phức tạp rồi ghi

Không phải mọi logic đều có thể diễn tả gọn bằng `SET total=total+1`. Có thể cần đọc nhiều field, áp dụng quy tắc nghiệp vụ ở Java rồi cập nhật cả aggregate.

Mẫu optimistic locking với version:

1. Đọc hàng cùng `version=5`.
2. Tính trạng thái mới trong Java.
3. Gửi:

```sql
UPDATE customer_profiles
SET display_name = ?,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = ?
  AND version = ?;
```

4. Nếu row count 1: đã update trên đúng version.
5. Nếu row count 0: dữ liệu bị xóa hoặc có thay đổi cạnh tranh; không tự ghi đè bằng bản cũ. Tải lại và **quyết định retry hoặc báo HTTP 409 Conflict** theo hợp đồng API.

### 11.1. Compare-and-swap với giá trị cũ

Nếu schema không có version nhưng một cột có thể làm guard, có thể viết:

```sql
UPDATE settings
SET current_value = :newValue
WHERE id = :id
  AND current_value = :expectedValue;
```

Tương tự CAS: chỉ ghi nếu giá trị vẫn là thứ vừa đọc. Tuy nhiên nếu giá trị đã đổi **A → B → A** giữa hai thời điểm (*ABA problem*), phép so sánh giá trị cũ có thể không phát hiện thay đổi trung gian. Version tăng đơn điệu thường phù hợp hơn khi cần phát hiện **mọi lần sửa**.

### 11.2. Không retry vô hạn

Khi optimistic update trả 0 hàng do conflict, retry cần:

- Giới hạn số lần và cân nhắc backoff.
- Đọc lại trạng thái, **tính lại nghiệp vụ**, không chỉ lặp lại literal đã cũ.
- Giữ side effects ngoài DB (email, thanh toán, event) ngoài các attempt có thể bị retry hoặc dùng idempotency/outbox.
- Phân biệt không tồn tại, conflict version và business rejection.

Với API có tốc độ ghi cao vào cùng một “hot row”, retry liên tục có thể gây thêm tải. Đôi khi một `UPDATE SET x=x+?` trực tiếp phù hợp hơn optimistic version cho trường hợp tăng đếm đơn giản.

## 12. Khi nào `SELECT ... FOR UPDATE` thích hợp?

Một cách khác để bảo vệ read-modify-write phức tạp là **khóa hàng trước khi đọc**, rồi ghi trong **cùng transaction**:

```java
@Transactional
public void changeAccountComplexly(long accountId) {
    AccountSnapshot account = jdbc.queryForObject(
        "SELECT id, balance, status FROM accounts " +
        "WHERE id=? FOR UPDATE",
        (rs, rowNum) -> new AccountSnapshot(
            rs.getLong("id"),
            rs.getBigDecimal("balance"),
            rs.getString("status")),
        accountId
    );

    // Tính logic nghiệp vụ bằng giá trị đã đọc trong lock.
    // Thực hiện UPDATE ở cùng transaction/connection.
}
```

Đây là **mã minh họa**, cần định nghĩa record/class `AccountSnapshot` và UPDATE thực tế. `SELECT ... FOR UPDATE` trong PostgreSQL có thể lấy row lock và khiến writer khác phải đợi; lock được giữ theo ranh giới transaction. Nếu thiếu transaction bao ngoài, kết nối dùng autocommit có thể nhả lock ngay sau SELECT, không bảo vệ đoạn Java tính toán kế tiếp.

So sánh lựa chọn:

| Yêu cầu | Phương án thường nên ưu tiên |
| --- | --- |
| Tăng một counter | `UPDATE SET counter=counter+?` |
| Giảm tồn kho nếu đủ | `UPDATE ... SET stock=stock-? WHERE stock>=?` |
| Chỉ sửa khi client còn version mới nhất | `UPDATE ... WHERE id=? AND version=?` hoặc JPA `@Version` |
| Tính quy tắc phức tạp cần trạng thái hàng nhất quán | `SELECT ... FOR UPDATE` trong transaction ngắn, hoặc optimistic version |
| Kiểm tra invariant trên tập nhiều hàng | Constraint, lock phù hợp, `SERIALIZABLE` với retry, hoặc thiết kế lại schema; một khóa hàng chưa chắc đủ |

Nếu câu `SELECT` trả **không có hàng**, `FOR UPDATE` không tự khóa mọi “khoảng trống” cần chặn một INSERT tương lai trên mọi engine. Với booking trùng lịch/giới hạn theo predicate, hãy cân nhắc unique/exclusion constraint hoặc chiến lược serialization riêng.

## 13. Không phải mọi thay đổi nghiệp vụ đều vừa một câu SQL

### 13.1. Chuyển tiền giữa hai tài khoản

Một câu trừ có guard tránh âm:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :fromId
  AND balance >= :amount;
```

Nhưng chuyển tiền còn cần **cộng vào tài khoản đích** và có thể thêm ledger. Muốn tránh “đã trừ nhưng chưa cộng”, cần chung transaction:

```text
BEGIN transaction
  UPDATE source SET balance=balance-amount
    WHERE id=source AND balance>=amount
  assert affected=1, otherwise rollback
  UPDATE destination SET balance=balance+amount
    WHERE id=destination
  assert affected=1, otherwise rollback
  INSERT transfer_ledger(...)
COMMIT transaction
```

Đó là **pseudocode**, không phải một lệnh SQL duy nhất. Dùng `@Transactional` ở service boundary qua Spring proxy để cả bước trừ, cộng, ledger cùng commit/rollback. Cần kiểm tra tài khoản đích tồn tại, hạn mức, định danh request, lock ordering và tiền tệ chính xác.

### 13.2. Invariant trên nhiều hàng

Ví dụ: “không quá 100 đơn OPEN” là invariant của **tập kết quả**. Hai request có thể cùng thấy COUNT=99 rồi cùng INSERT; một atomic update trên một hàng order riêng **không đủ** bảo đảm invariant tổng.

Có thể đưa capacity vào **một hàng quota** và dùng conditional decrement/claim; hoặc dùng constraint, lock, serializable. Phương án phải phù hợp schema và loại cạnh tranh.

### 13.3. Không đồng nhất database atomicity và external side effects

Gửi email, gọi payment provider, publish Kafka hoặc ghi file ngoài DB không tự nằm trong transaction JDBC. Một transaction rollback không thu hồi API call đã hoàn tất. Khi có retry, nguy cơ side effect bị lặp càng lớn. Cần transactional outbox, idempotency, after-commit processing hoặc cơ chế bù trừ tùy nghiệp vụ.

## 14. Spring Data JPA: bulk update và persistence context

Nếu dự án dùng Spring Data JPA, có thể diễn đạt conditional update bằng JPQL:

```java
public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update Inventory i
        set i.stock = i.stock - :quantity
        where i.id = :id and i.stock >= :quantity
        """)
    int reserve(
        @Param("id") Long id,
        @Param("quantity") int quantity
    );
}
```

Đây là **mảnh minh họa**, cần entity `Inventory` với field `stock` và `id`, các import của Spring Data JPA và transaction boundary thích hợp. Return `int` là số hàng được update; service phải kiểm tra. `@Modifying` báo rằng đây là modifying query, không thay cho `@Transactional` của nghiệp vụ. JPQL không đồng nhất cú pháp SQL của mọi dialect.

**Cảnh báo lớn:** bulk JPQL update đi thẳng tới database, không tự cập nhật mọi object `Inventory` đã được load trong `EntityManager`. `clearAutomatically=true` có thể xóa trạng thái managed khỏi persistence context; nếu còn thay đổi chưa flush, bạn có nguy cơ mất những thay đổi đó. `flushAutomatically=true` cũng ảnh hưởng thứ tự SQL. Chọn các option theo kiến trúc thực tế; không bật mù quáng khi còn pending managed changes.

Một hướng khác là đọc entity và dùng `@Version` để Hibernate/JPA thực hiện optimistic locking. Nó phù hợp khi muốn entity-level semantics và các giá trị tính bằng Java. Tuy nhiên phải xử lý `OptimisticLockException` và retry/response; không coi `@Version` là cách tự động sửa mọi truy vấn cập nhật bulk hoặc writer ngoài JPA.

### 14.1. Dữ liệu cache và read-after-write

Trong transaction có JPA persistence context, sau bulk update, một entity đã được load có thể vẫn giữ field `stock` cũ trong RAM. Đừng dùng field đó làm câu trả lời “stock còn bao nhiêu” nếu chưa đồng bộ/cập nhật đúng. Có thể dùng SQL `RETURNING` hoặc query lại trong ngữ cảnh đúng, quản lý refresh/clear có chủ đích. Trong bài JDBC chính, `JdbcTemplate` không có first-level entity cache như JPA.

## 15. Atomic không đồng nghĩa idempotent

Một lệnh:

```sql
UPDATE inventory SET stock=stock-5
WHERE id=1 AND stock>=5;
```

là atomic về phép kiểm tra-trừ trên hàng, nhưng **nếu cùng một request bị gửi lại hai lần**, mỗi lần là một yêu cầu hợp lệ riêng và có thể trừ hai lần nếu vẫn đủ hàng.

Ví dụ:

- Client gửi request giữ 2 món, server đã giảm stock và commit.
- Response HTTP bị mất do network.
- Client retry cùng payload.
- Server thực hiện lần nữa nếu không nhận diện đây là **cùng một business request**.

Cần idempotency key (ví dụ `request_id` unique), ledger hoặc cơ chế ghi nhận giao dịch đã xử lý. Một luồng thiết kế:

1. Mỗi thao tác mang `request_id` duy nhất và người dùng/client xác định.
2. Trong cùng transaction, thử đăng ký `request_id` vào bảng có **UNIQUE constraint**.
3. Nếu key đã được xử lý, trả kết quả ghi nhận trước đó theo chính sách, **không trừ stock lần nữa**.
4. Nếu key mới, thực thi guarded UPDATE và ghi trạng thái outcome rồi commit cùng nhau.

Điều này đòi hỏi thiết kế thêm table/trạng thái và xử lý cạnh tranh cùng key; `@Transactional` + unique constraint giúp đồng bộ, nhưng không thể thay bằng một boolean Java trên một app instance. **Atomic update bảo vệ tính nhất quán của một lần xử lý; idempotency bảo vệ chống xử lý trùng cùng ý định nghiệp vụ.**

## 16. Transaction isolation và lỗi cạnh tranh không tự biến mất

### 16.1. READ COMMITTED

Trong PostgreSQL `READ COMMITTED`, row-level UPDATE với predicate đơn giản là mô hình phù hợp cho guarded increment/decrement. Trong một transaction có nhiều câu SELECT/UPDATE trên các hàng khác nhau, mỗi statement có snapshot/điều phối riêng; không suy rằng toàn bộ invariant nhiều hàng tự được bảo vệ bởi một update.

### 16.2. REPEATABLE READ / SERIALIZABLE

Ở isolation mạnh hơn, PostgreSQL có thể từ chối một cạnh tranh update với **serialization failure (SQLSTATE 40001)**. Cần retry **toàn bộ transaction** bằng dữ liệu mới, không chỉ lặp lại câu SQL trên transaction đã lỗi. `SERIALIZABLE` có thể ngăn anomalies phức tạp bằng cách abort một số transaction có xung đột.

**Không** diễn giải atomic update thành “không bao giờ có deadlock/serialization exception”. Việc đúng đắn khi có conflict có thể yêu cầu transaction thất bại rồi retry.

### 16.3. Deadlock khi cập nhật nhiều hàng

Hai transfer cùng chạm tài khoản A và B nhưng lock theo thứ tự ngược nhau có thể deadlock. Cách hạn chế:

- Cập nhật/lock các ID theo thứ tự ổn định nếu có thể.
- Giữ transaction ngắn.
- Có index phù hợp.
- Retry có giới hạn cho lỗi deadlock/serialization phù hợp.
- Không bỏ qua exception rồi trả thành công.

### 16.4. Kiểm tra read-only và proxy

`@Transactional(readOnly=true)` là hint/chính sách đọc, không biến một `UPDATE` thành atomic hay làm phép ghi được phép. Method ghi cần transaction policy phù hợp. Method chỉ nhận advice khi đi qua Spring-managed proxy trong proxy mode thông thường; self-invocation `this.method()` có thể bỏ qua một ranh giới transaction mới.

Một câu `UPDATE` vẫn được DB xử lý theo transaction/autocommit thực tế, nhưng những SQL bổ sung có thể không cùng atomic unit nếu Spring advice không kích hoạt như dự định.

## 17. Hiệu năng, hotspot và kiểu dữ liệu

### 17.1. Hàng bị tranh chấp cao

Nếu mọi request tăng một counter duy nhất, một hot row sẽ trở thành điểm contention; atomic SQL **giữ correctness**, không bảo đảm throughput vô hạn. Khi load lớn, cân nhắc:

- Counter sharding / striped counters nếu business cho phép tổng hợp eventual consistency.
- Tích lũy sự kiện vào bảng riêng rồi aggregate sau.
- Batch update hoặc kiến trúc queue khi yêu cầu độ chính xác khác nhau.
- Đo transaction latency, lock waits, deadlocks dưới tải thật.

Đổi từ `SELECT + UPDATE` sang một SQL thường giảm round trip, nhưng một row hot vẫn phải điều phối nhiều writer.

### 17.2. Giới hạn số nguyên và tiền tệ

- Với bộ đếm có thể lớn, dùng `BIGINT` ở DB và kiểu Java `long`; vẫn kiểm soát overflow.
- Với tiền tệ, ưu tiên `NUMERIC/DECIMAL` và Java `BigDecimal`, ràng buộc số lượng chữ số thập phân.
- Với stock, constraint `stock >= 0` và validation `requested > 0`; nếu có tổng số lớn, chọn `BIGINT` khi phù hợp.
- Không cho rằng phép cập nhật nguyên tử ngăn input không hợp lệ hoặc overflow.

### 17.3. Row count và thông báo nghiệp vụ

Ví dụ reserve với row count 0 là tín hiệu **không được phép trừ theo điều kiện hiện tại**. Ứng dụng có thể trả HTTP 409 Conflict, 422 Unprocessable Content hoặc thông điệp hết hàng tùy API contract. Cần phân biệt lỗi kỹ thuật (DB down/timeout/deadlock) và thất bại business condition (không đủ hàng). Không diễn giải mọi SQL exception thành “hết hàng”.

## 18. Quy trình kiểm thử concurrency

Một test đáng tin phải chủ động kiểm soát lịch chạy, không dựa vào số lượng request ngẫu nhiên.

### 18.1. Kịch bản tối thiểu

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Hai worker cùng đọc 100 rồi `SET total=110` | Lost update: cuối cùng 110 |
| Hai worker cùng `SET total=total+10` | Cuối cùng 120 |
| Stock 7, hai worker cùng yêu cầu 5 qua guarded UPDATE | Chính xác 1 thành công; stock=2 |
| Stock 3, yêu cầu 5 | 0 hàng được cập nhật; stock=3 |
| Stock 7, yêu cầu 0 hoặc âm | Validate đầu vào, không cập nhật |
| Trả 0 ở optimistic version UPDATE | Báo conflict/reload, không trả success |
| Guarded UPDATE thành công rồi INSERT khác thất bại trong cùng transaction | Rollback toàn bộ theo policy; stock về trước thao tác |
| Cùng request_id được retry | Không trừ hai lần nếu idempotency đã triển khai |

### 18.2. Đo đúng kết quả

1. Dùng database production-like, hai transaction/connection thật sự khác nhau.
2. Gọi service qua Spring-managed proxy, không gọi `new` hay self-invocation.
3. Đồng bộ lịch đọc/ghi bằng `CyclicBarrier`/`CountDownLatch` để tái hiện race, không dùng `Thread.sleep` làm bằng chứng.
4. Đặt timeout bảo vệ test, nhưng không dựa vào timeout để đảm bảo thứ tự.
5. Kiểm tra **row count** và đọc dữ liệu **sau khi transaction của worker kết thúc**.
6. Tách test `READ COMMITTED` khỏi test isolation khác để không kỳ vọng kết quả giống nhau.
7. Test cả trường hợp conflict/0 row, không chỉ đường thành công.
8. Nếu test có `@Transactional` bao ngoài, cần hiểu transaction test có thể rollback cuối test hoặc khiến các lời gọi cùng thread tham gia transaction test. Đừng làm như thể đã quan sát commit thật.
9. Khi dùng Spring Data JPA, loại ảnh hưởng persistence-context cache nếu mục tiêu là quan sát giá trị DB ngay sau commit.

### 18.3. Không chỉ đếm số SQL statements

Một ứng dụng có thể dùng đúng **một UPDATE** nhưng vẫn sai nếu:

- `WHERE` thiếu điều kiện nghiệp vụ.
- `SET` dùng literal tính từ giá trị stale.
- Không kiểm tra row count 0.
- Cập nhật đúng hàng nhưng ghi nhầm tenant/account do thiếu predicate `tenant_id=?`.
- Trùng request và thiếu idempotency.
- Nghiệp vụ thực sự cần atomicity ở nhiều bảng nhưng chỉ bảo vệ một statement.
- Bỏ qua deadlock/serialization errors.
- DB constraint và versioning không được áp dụng thống nhất ở mọi đường ghi.

Vì vậy, đơn vị đánh giá không chỉ là số câu SQL mà là **predicate, phép biến đổi, ranh giới transaction và kết quả nghiệp vụ**.

## 19. Những ngộ nhận thường gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Có `@Transactional` thì SELECT → Java compute → UPDATE tự an toàn” | Không; các transaction vẫn chạy đồng thời, giá trị đọc có thể stale |
| “Database có row lock nên `SET total=110` sẽ thành 120” | Row lock không biết phép tính `+10` đã làm trong Java; literal vẫn là 110 |
| “`UPDATE stock=stock-?` luôn ngăn oversell” | Chỉ đúng khi điều kiện `stock>=?` được kiểm tra cùng statement hoặc có bảo vệ tương đương |
| “Một `SELECT` trước UPDATE đủ để kiểm tra stock” | Kết quả SELECT có thể hết hiệu lực khi writer khác commit |
| “SQL không ném lỗi tức đã update thành công” | `UPDATE 0` có thể là kết quả hợp lệ; phải kiểm tra row count |
| “`JdbcTemplate.update` trả số dư mới” | Nó trả số hàng được driver báo cập nhật |
| “Atomic đồng nghĩa idempotent” | Gửi lại cùng request có thể tạo thêm một phép trừ; cần request key/ledger |
| “Atomic một statement bảo vệ cả email và API” | Local DB transaction không tự hoàn tác external side effects |
| “REPEATABLE_READ/SERIALIZABLE khiến mọi update tự thành công” | Có thể deadlock/serialization failure cần xử lý |
| “`@Version` tự động bảo vệ mọi bulk JPQL update” | Bulk updates không tự động dùng entity-level version semantics nếu query không khai tương ứng |
| “`synchronized` là đủ trong ứng dụng nhiều server” | Chỉ bảo vệ các threads chia sẻ cùng JVM/monitor |
| “Đọc lại ngay sau UPDATE cho giá trị được RETURNING bảo đảm” | SELECT riêng có thể thấy commit mới của transaction khác; dùng `RETURNING` nếu cần giá trị của chính statement |

## 20. Câu hỏi tự kiểm tra

**1. Hai request cùng đọc tổng 100, mỗi request tính 110 rồi viết `SET total=110`. Vì sao giá trị cuối có thể là 110?**

Vì cả hai update dùng cùng giá trị literal cũ được tính ở Java; một update ghi đè kết quả mà request khác đã làm. Đây là lost update.

**2. Đổi sang `SET total=total+10` giúp gì?**

Phép cộng chạy trong statement tại DB, dựa trên giá trị hàng được database cập nhật. Với PostgreSQL `READ COMMITTED`, hai lần tăng một hàng đều thành công thì tổng từ 100 thành 120.

**3. Một request kiểm tra `stock >= 5` bằng SELECT rồi chạy `UPDATE stock=stock-5`. Đã an toàn chưa?**

Chưa. Writer khác có thể giảm stock sau SELECT và trước UPDATE. Đưa `stock>=5` vào `WHERE` của chính UPDATE và kiểm tra row count.

**4. Vì sao `UPDATE 0` không nhất thiết là lỗi SQL?**

Vì không có hàng thỏa predicate là một kết quả hợp lệ của UPDATE. Trong guarded reservation, đây là thất bại điều kiện business, không phải statement syntax error.

**5. Nếu cần thay đổi cả source account và destination account thì một guarded UPDATE có đủ không?**

Không. Cần transaction bao trùm các bước liên quan cùng manager/resource, kiểm tra row count của từng thao tác, rollback nếu thất bại và bảo vệ idempotency cho request chuyển tiền.

**6. Version check trả 0 hàng thì xử lý thế nào?**

Coi đó là conflict/không tồn tại tùy giao ước; tải dữ liệu mới và tính lại hoặc trả lỗi. Không tự động ghi đè bằng bản Java cũ.

**7. Có nên dùng `REQUIRES_NEW` chỉ để “chắc chắn” mỗi update nguyên tử?**

Không. Nó tạo transaction vật lý độc lập, thay đổi atomicity của nghiệp vụ nhiều bước. Một guarded UPDATE thường không cần riêng `REQUIRES_NEW`; chọn propagation theo transaction boundary cần thiết.

**8. Hai request cùng ID giảm 2 món hai lần, mỗi lệnh đều atomic và đủ stock. Có đảm bảo chỉ trừ một lần không?**

Không. Atomicity không phải idempotency. Cần nhận diện request_id trùng và từ chối/hoàn trả kết quả trước đó thay vì xử lý lại.

**9. `UPDATE ... RETURNING stock` có lợi gì?**

Nó trả số stock mới từ **chính statement vừa cập nhật**, giúp tránh một SELECT riêng có thể nhìn thấy thay đổi cạnh tranh sau đó. Đây là cú pháp PostgreSQL; dùng query API phù hợp để đọc result set.

## 21. Tổng kết

Khi nhiều transaction có thể ghi cùng một dữ liệu, **read–modify–write không được bảo vệ** làm phát sinh lost update và quyết định dựa trên trạng thái đã cũ. `@Transactional` là cơ chế quản lý transaction, **không phải** phép tự động kiểm tra rằng dữ liệu Java vừa đọc còn mới lúc ghi.

Hãy chọn công cụ theo bài toán:

- **Counter:** `UPDATE SET total=total+?`.
- **Stock/quota/balance có điều kiện:** `UPDATE ... SET x=x-? WHERE x>=?`, validate input và kiểm tra row count.
- **Trạng thái phức tạp từ snapshot:** optimistic version/CAS hoặc `SELECT FOR UPDATE` trong transaction thích hợp.
- **Nhiều bảng/invariant rộng:** transaction boundary, constraints/locking/serializable và retry có kiểm soát.
- **Request có thể gửi lặp:** idempotency key/ledger, không chỉ atomic SQL.

Bài học quan trọng nhất không phải “hãy dùng ít SQL hơn”, mà là **đưa điều kiện dễ thay đổi cùng phép ghi vào một thao tác được database điều phối**, rồi biến kết quả số hàng cập nhật/exception thành quyết định nghiệp vụ rõ ràng. Kiểm chứng bằng hai transaction thật và lịch chạy xác định, thay vì tin rằng code chạy đúng khi thử một thread là đủ.

## Tài liệu chính thức

- PostgreSQL — Transaction Isolation, `READ COMMITTED` và việc `UPDATE` chờ/recheck `WHERE`: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — `UPDATE`, row count và matching conditions: https://www.postgresql.org/docs/current/sql-update.html
- PostgreSQL — `RETURNING` for `UPDATE`: https://www.postgresql.org/docs/current/dml-returning.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- Spring Framework — Declarative Transaction Management và `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework API — `JdbcTemplate`, update returns update count: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Data JPA — Query Methods và modifying queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA — Locking: https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html
