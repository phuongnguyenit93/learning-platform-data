# Mức cô lập mặc định và các bất thường cần hiểu theo phiên bản trong Neo4j

## 1. Bối cảnh: giao dịch ACID không đồng nghĩa với ảnh chụp dữ liệu bất biến

Trong mô hình **property graph** của Neo4j, một giao dịch có thể đọc và sửa node, relationship, property, index hoặc constraint. Cypher thực hiện các thao tác đó trong **transaction** để bảo đảm tính nguyên tử và duy trì tính nhất quán của hệ thống. Tuy nhiên, nếu nhiều ứng dụng cùng truy cập đồ thị, chúng vẫn có thể quan sát các thay đổi khác nhau theo thời điểm và gặp xung đột khi ghi.

Đây là bài học thuộc chương **Giao dịch** của module `DATABASE_ENGINE_GRAPH_NEO4J`, tập trung vào **mức cô lập mặc định**, các bất thường khi nhiều giao dịch chạy đồng thời, cách phòng tránh và những điểm phải **kiểm tra theo đúng phiên bản Neo4j/Driver**. Các tình huống này xuất hiện trong hệ thống quản lý kho, đặt chỗ, quan hệ tài khoản, mô hình phụ thuộc và ứng dụng dùng **Java Driver** hoặc **Spring Data Neo4j**.

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa chính xác của **read committed** và phân biệt nó với **repeatable read**, **snapshot isolation** và **serializable**.
2. Nhận diện *dirty read*, *non-repeatable read*, *phantom*, *lost update*, *write skew*, *missing/double read* và *deadlock*.
3. Hiểu khi nào Cypher tự lấy khóa ghi trước lúc đọc thuộc tính để tránh mất cập nhật.
4. Lựa chọn mô hình dữ liệu, câu truy vấn, khóa, constraint và retry phù hợp.
5. Đối chiếu tài liệu đúng phiên bản server, Java Driver và môi trường cluster, tránh suy đoán từ cách vận hành của cơ sở dữ liệu khác.

> **Phạm vi phiên bản:** Tài liệu Neo4j 4.4, dòng 5.x và tài liệu Operations Manual hiện hành đều mô tả **read committed** là mức cô lập mặc định. Những ví dụ về toán tử thực thi, hành vi khóa chi tiết, mã trạng thái lỗi và API Java có thể khác theo bản phát hành. Vì vậy, kết luận về *isolation* cần tách khỏi kết luận về *cách triển khai bên trong*.

## 2. Mức cô lập mặc định: read committed

Tài liệu chính thức của Neo4j nêu **read-committed isolation level** là mặc định. Điều này có hai ý quan trọng:

- Một giao dịch **không đọc được thay đổi chưa commit của giao dịch khác**. Bởi vậy, *dirty read* từ các cập nhật chưa commit không phải hành vi được phép.
- Khi giao dịch khác đã commit, một lần đọc sau đó **có thể thấy** giá trị mới, ngay cả khi giao dịch đọc đầu tiên chưa kết thúc. Chế độ mặc định **không hứa hẹn mọi lần đọc trong một transaction đều dựa trên một ảnh chụp bất biến của đồ thị**.

Ví dụ, nếu giao dịch A đọc `account.balance = 100`, giao dịch B sửa thành `80` rồi commit, A có thể đọc lại và nhìn thấy `80`. A vẫn không bao giờ được nhìn thấy `80` **trước khi B commit**.

### 2.1. Phân biệt các khái niệm

| Khái niệm | Cam kết chính | Có phải mặc định của Neo4j? |
| --- | --- | --- |
| **Read uncommitted** | Có thể thấy dữ liệu chưa commit của transaction khác | Không |
| **Read committed** | Không thấy dữ liệu chưa commit; các lần đọc có thể khác nhau | **Có** |
| **Repeatable read** | Khi đọc lại cùng dữ liệu trong transaction, tránh biến đổi do transaction khác | Không được Neo4j mặc định bảo đảm như một mức SQL có thể chọn |
| **Snapshot isolation** | Các lần đọc trong transaction thường nhìn một snapshot nhất quán theo cơ chế MVCC | Không nên tự giả định từ read committed |
| **Serializable** | Các giao dịch có hiệu ứng tương đương một thứ tự thực thi tuần tự | Không phải mức mặc định; cần đồng bộ đúng các tài nguyên chung để đạt bảo đảm nghiệp vụ tương ứng |

Các tên ở bảng là **khái niệm về tính cô lập**. Chúng không hàm ý rằng Neo4j cung cấp một cú pháp `SET TRANSACTION ISOLATION LEVEL` để tùy ý chuyển giữa tất cả các mức như một số hệ quản trị quan hệ.

### 2.2. ACID bảo vệ điều gì?

**Atomicity** bảo đảm một giao dịch hoặc commit toàn bộ thay đổi của nó, hoặc rollback. **Durability** bảo đảm dữ liệu đã commit có thể được khôi phục. **Isolation** quy định cách các giao dịch nhìn thấy dữ liệu của nhau. Vì thế, một hệ thống **ACID** vẫn có thể cho phép *non-repeatable read* ở mức **read committed** mà không mâu thuẫn với ACID.

Neo4j tự lấy **khóa ghi** khi cần thay đổi các thực thể, và khóa thường được giữ đến khi transaction kết thúc. Khóa giúp tránh việc hai giao dịch cùng thay đổi một tài nguyên ở đúng cùng thời điểm, nhưng **không tự biến mọi thao tác đọc–kiểm tra–ghi thành tuần tự hóa**.

## 3. Bảng các bất thường cần phân biệt

| Hiện tượng | Ví dụ trong property graph | Read committed mặc định |
| --- | --- | --- |
| **Dirty read** | A đọc giá trị B vừa `SET` nhưng B chưa commit | **Không được phép** |
| **Non-repeatable read** | A đọc cùng property hai lần và nhận 2 giá trị do B commit giữa hai lần đọc | **Có thể xảy ra** |
| **Phantom** | A chạy lại mẫu `MATCH` và thấy thêm/bớt node hoặc relationship do B commit | **Có thể xảy ra theo ngữ nghĩa read committed** |
| **Lost update** | A và B cùng đọc một giá trị cũ rồi ghi đè kết quả tính toán từ giá trị đó | **Có thể xảy ra** nếu không khóa trước khi đọc phụ thuộc |
| **Write skew** | Hai giao dịch cùng kiểm tra một điều kiện liên quan nhiều node, sau đó sửa **hai node khác nhau**, làm sai quy tắc chung | **Rủi ro cần thiết kế phòng tránh** |
| **Missing/double read** | Một lần quét index bỏ sót hoặc đọc trùng thực thể khi transaction khác đổi khóa index | **Có thể xảy ra** với một số toán tử quét index |
| **Deadlock** | A giữ khóa node X, đợi Y; B giữ khóa Y, đợi X | **Có thể xảy ra** khi tranh chấp khóa; đây là lỗi đồng thời, không phải một kiểu *read anomaly* |

Các hàng “có thể xảy ra” mô tả **khả năng**, không có nghĩa mọi lần chạy truy vấn đều tái hiện được. Kết quả còn phụ thuộc lịch thực thi, loại toán tử, thứ tự khóa, chỉ mục và phiên bản Neo4j.

## 4. Chuẩn bị môi trường thực hành

Các ví dụ dùng nhãn riêng `IsolationCounter` để không ảnh hưởng dữ liệu nghiệp vụ khác. Nên chạy trên **database thử nghiệm**, mở **hai phiên kết nối độc lập**, ký hiệu **A** và **B**. Một cửa sổ chạy nhiều query tự commit liên tiếp **không tương đương** với một transaction được giữ mở.

Tạo một thực thể để hai phiên cùng đọc/ghi:

```cypher
CREATE CONSTRAINT isolation_counter_id IF NOT EXISTS
FOR (c:IsolationCounter)
REQUIRE c.id IS UNIQUE;
```

```cypher
MERGE (c:IsolationCounter {id: 'shared'})
SET c.value = 0, c.version = 0
RETURN c.id, c.value, c.version;
```

Để kiểm tra trạng thái sau mỗi lần thử:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
RETURN c.value AS value, c.version AS version;
```

**Lưu ý công cụ:** Các dòng `:begin`, `:commit` và `:rollback` trong ví dụ kế tiếp là **lệnh quản lý transaction của một số client tương tác**, chẳng hạn Cypher Shell. Chúng **không phải clause Cypher** và không được gửi nguyên văn qua Java Driver. Với Java Driver, sử dụng `session.beginTransaction()` để chủ động giữ transaction mở. Mỗi phiên A/B phải sử dụng một transaction độc lập.

## 5. Hai lịch thực thi cơ bản: không dirty read, nhưng có thể non-repeatable read

### 5.1. Dirty read bị ngăn

Giả sử counter ban đầu bằng `0`.

| Thời điểm | Transaction A | Transaction B |
| --- | --- | --- |
| T1 | Bắt đầu transaction | Bắt đầu transaction |
| T2 | Đọc `value`, thấy `0` | |
| T3 | | Gán `value = 99`, **chưa commit** |
| T4 | Đọc lại; **không được thấy giá trị chưa commit `99`** | |
| T5 | | Rollback |
| T6 | Đọc lại; giá trị cuối cùng vẫn là `0` | |

Ở T4, một câu truy vấn cụ thể có thể đợi khóa hoặc thấy giá trị đã commit trước đó tùy tài nguyên và kế hoạch; ý nghĩa quan trọng là **không được trả về bản cập nhật chưa commit của B**.

### 5.2. Non-repeatable read

Thử với hai session khi counter ban đầu bằng `0`:

**Session A**, trong transaction chưa commit:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
RETURN c.value AS firstRead;
```

**Session B**, sau khi A đọc xong, thực thi và **commit**:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
SET c.value = 10
RETURN c.value AS writtenValue;
```

**Session A** đọc lại trong **chính transaction cũ**:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
RETURN c.value AS secondRead;
```

Trong lịch phù hợp, `firstRead = 0` và `secondRead = 10`. Cùng một transaction, cùng một node, nhưng hai lần đọc cho kết quả khác. Đây là **non-repeatable read**.

Ngay cả khi cùng một câu Cypher, các lần đọc cùng property ở các giai đoạn khác nhau của kế hoạch cũng có thể quan sát các giá trị khác nhau. Ví dụ mang tính minh họa:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
WITH c, c.value AS firstRead
// Một transaction khác có thể commit trong khoảng thời gian giữa hai lần đọc.
WITH c, firstRead, c.value AS secondRead
RETURN firstRead, secondRead;
```

Không có bảo đảm rằng hai cột luôn khác nhau; truy vấn sẽ thường chạy rất nhanh. Điểm cần nhớ là **đừng giả định hai lần truy cập property sẽ cố định cùng một giá trị**. Nếu cần dùng nhất quán một giá trị trong phép tính chỉ đọc, hãy đọc một lần và chuyển tiếp biến đã tính qua `WITH`.

## 6. Lost update: khác biệt giữa khóa ghi tự động và giá trị đọc từ trước

*Lost update* thường là vấn đề nghiêm trọng nhất trong ứng dụng đếm lượt, tích điểm, điều chỉnh tồn kho hoặc cập nhật chỉ số trên node.

### 6.1. Lịch mất cập nhật

Counter ban đầu bằng `0`. Cả A và B đều đọc giá trị đó, tính toán ngoài truy vấn, rồi lần lượt ghi giá trị đã tính.

| Bước | Transaction A | Transaction B |
| --- | --- | --- |
| 1 | Đọc `value = 0` | |
| 2 | | Đọc `value = 0` |
| 3 | Tính `newValue = 1` rồi ghi/commit | |
| 4 | | Tính `newValue = 1` từ dữ liệu cũ rồi ghi/commit |
| Kết quả | | **`value = 1`**, dù đã có hai yêu cầu tăng |

Đoạn ghi từ ứng dụng có thể tương đương:

```cypher
MATCH (c:IsolationCounter {id: $id})
SET c.value = $newValue
RETURN c.value;
```

Nếu cả hai client đã đọc `0` và cùng gửi `$newValue = 1`, **khóa khi ghi không sửa được lỗi nghiệp vụ**: transaction sau vẫn ghi đè bằng một giá trị đã tính từ dữ liệu cũ.

Tương tự, trong một câu Cypher, đưa giá trị đọc vào biến trước khi cập nhật có thể làm mất quan hệ phụ thuộc trực tiếp mà trình thực thi dùng để lấy khóa sớm:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
WITH c, c.value AS oldValue
SET c.value = oldValue + 1
RETURN c.value;
```

Theo tài liệu Neo4j về *lost updates*, cần hết sức thận trọng với cách tách đọc property khỏi biểu thức `SET` như thế này khi có các giao dịch đồng thời.

### 6.2. Mẫu tăng trực tiếp: Cypher có thể lấy khóa trước khi đọc

Khi vế phải của `SET` phụ thuộc **trực tiếp** vào chính property đang cập nhật:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
SET c.value = c.value + 1
RETURN c.value AS updatedValue;
```

Neo4j tài liệu hóa việc Cypher **tự lấy khóa ghi trước khi đọc giá trị phụ thuộc** trong trường hợp này. Khi hai transaction cùng tăng một counter, khóa bảo vệ thao tác đọc–cập nhật liên quan, nên tránh kiểu *lost update* nêu trên.

Điều này cũng áp dụng cho một số biểu thức bản đồ trực tiếp như `SET c += {value: c.value + 1}`, nhưng **không nên suy rộng** thành «mọi phép `SET` đều luôn tự bảo vệ mọi giá trị đã đọc trước đó».

### 6.3. Khi cần giữ khóa trước thao tác đọc–tính toán phức tạp

Tài liệu Neo4j có cách lấy khóa ghi một cách chủ động bằng cách sửa rồi xóa một property tạm trên node **trước khi đọc** giá trị cần tính:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
SET c._writeLock = true
REMOVE c._writeLock
WITH c, c.value AS oldValue
// Thực hiện tính toán từ oldValue sau khi đã lấy khóa.
SET c.value = oldValue + 1
RETURN c.value AS updatedValue;
```

Việc `REMOVE` property tạm **không giải phóng khóa đang giữ**; khóa được giữ đến khi transaction kết thúc. Đây là một thủ thuật được tài liệu hóa cho các trường hợp cần đọc–tính toán sau khi đã khóa. Nên kiểm tra lại trên phiên bản đang dùng và cân nhắc chi phí tranh chấp khóa; không lạm dụng property tạm khi chỉ cần một lệnh tăng trực tiếp.

**Quan trọng:** Khóa **một node** chỉ tuần tự hóa các transaction cùng dùng khóa của node đó. Nó không tự bảo đảm quy tắc liên quan **nhiều node** nếu các transaction không khóa một tài nguyên chung.

## 7. Phantom, write skew và những rủi ro riêng của đồ thị

### 7.1. Phantom: tập kết quả của mẫu đồ thị thay đổi

Giả sử A đếm các yêu cầu đặt chỗ đang chờ xử lý:

```cypher
MATCH (r:IsolationReservation {eventId: 'ev-1', state: 'PENDING'})
RETURN count(r) AS pendingCount;
```

Giữa hai lần A chạy câu này trong **cùng một transaction**, B tạo và commit một node:

```cypher
CREATE (:IsolationReservation {
  reservationId: 'res-new',
  eventId: 'ev-1',
  state: 'PENDING'
});
```

Sau commit của B, A có thể đọc lại và thấy **số lượng hoặc tập node tăng lên**. Đó là ví dụ *phantom* theo khái niệm các lần tìm tập thực thể theo điều kiện khác nhau trong cùng transaction. Tương tự, nếu B tạo/xóa relationship, kết quả của `MATCH (a)-[:CONNECTED_TO]->(b)` cũng có thể đổi.

Đừng dùng kết quả một lần `count(*)` làm «khóa giữ chỗ» cho các giao dịch ghi sau đó. Nếu cần bảo đảm ghế không bị đặt đôi, nên mô hình hóa khóa ghế hoặc khóa định danh nghiệp vụ với **unique constraint** phù hợp, bên cạnh transaction.

### 7.2. Write skew: mỗi transaction sửa một node, quy tắc toàn cục bị phá

Xét quy tắc: **mỗi ca trực phải luôn còn ít nhất một người đang làm việc**. Ban đầu có hai node `(:IsolationStaff {onDuty: true})` là An và Bình.

1. A đọc, thấy có **2** nhân viên đang trực.
2. B đọc, cũng thấy có **2**.
3. A cho An nghỉ (`onDuty = false`), rồi commit.
4. B cho Bình nghỉ (`onDuty = false`), rồi commit.
5. Không còn người trực, dù **mỗi giao dịch** đã tự kiểm tra «trước khi sửa còn hai người».

Hai transaction ghi **hai node khác nhau**, nên khóa ghi riêng của mỗi node chưa chắc tạo ra xung đột. Đây là rủi ro kiểu *write skew*: một ràng buộc trên **tập thực thể** không được bảo vệ chỉ bằng việc đọc tập đó.

Cách tiếp cận có thể là tạo **node bảo vệ chung** cho ca trực; mọi transaction thay đổi ca đó phải lấy khóa ghi trên node bảo vệ **trước khi đọc lại và kiểm tra điều kiện**. Chỉ các transaction **cùng tuân thủ một giao thức khóa** mới được bảo vệ bởi giao thức đó. Với quy tắc có thể biểu đạt bằng định danh duy nhất, constraint ở mức schema cũng nên được sử dụng.

### 7.3. Missing/double reads khi quét index

Tài liệu Neo4j hiện hành mô tả tình huống **một lần quét index có thể bỏ sót hoặc đọc trùng thực thể** nếu transaction khác đồng thời thay đổi giá trị khóa index, khiến thực thể được di chuyển tới vị trí đã hoặc chưa quét.

Ví dụ về hình thái truy vấn cần đánh giá:

```cypher
MATCH (i:IsolationItem)
WHERE i.score IS NOT NULL
RETURN i.itemId, i.score;
```

Nếu kế hoạch dùng toán tử quét index và transaction khác đang sửa `i.score`, không thể mặc định một lượt quét sẽ thấy mỗi thực thể chính xác một lần. **Việc có index không tự đồng nghĩa với snapshot nhất quán**. Không phải mọi kế hoạch hoặc mọi lần chạy query trên đều phát sinh bất thường; hãy dùng `EXPLAIN` hoặc `PROFILE` để xem toán tử thực tế.

### 7.4. Truy vấn đường đi không được bảo vệ khỏi sửa đổi đồng thời

Với truy vấn:

```cypher
MATCH p = (a:IsolationNode {id: 'start'})-[:NEXT*1..3]->(b:IsolationNode)
RETURN b.id, length(p);
```

giao dịch khác có thể thêm/xóa relationship hoặc đổi property trong lúc hệ thống thực hiện đọc. Vì Neo4j mặc định dùng read committed, **không nên xem kết quả của một cuộc duyệt đồ thị dài là ảnh chụp nhất quán của mọi quan hệ tại thời điểm bắt đầu transaction**. Nếu nghiệp vụ cần tính đúng trên một trạng thái được cố định, cần thiết kế cơ chế đồng bộ phù hợp với các node/relationship liên quan, cân nhắc giới hạn phạm vi giao dịch và tải ghi đồng thời.

## 8. Deadlock, khóa và retry: cách xử lý ở ứng dụng

### 8.1. Deadlock không đồng nghĩa với dữ liệu đã bị ghi sai

Hai transaction cập nhật cùng hai node nhưng theo thứ tự đảo ngược có thể mắc kẹt:

```text
Transaction A: khóa node X ---> đợi khóa node Y
                                   ^
                                   |
Transaction B: khóa node Y ---> đợi khóa node X
```

Neo4j có phát hiện deadlock và chấm dứt một giao dịch liên quan bằng lỗi có thể retry. Các thay đổi của transaction bị rollback không được commit một phần.

Các biện pháp phổ biến:

- Lấy khóa các node cần cập nhật theo **một thứ tự nhất quán** trong mọi luồng xử lý.
- Giữ transaction ngắn; không chờ network call hoặc thao tác UI trong lúc giữ khóa.
- Giảm số request cùng sửa một node «nóng»; thiết kế lại phân vùng dữ liệu hoặc gom cập nhật khi phù hợp.
- Có chính sách **retry hữu hạn** cho lỗi tạm thời, với thời gian chờ hợp lý; kiểm tra tính an toàn khi retry.

Ở tài liệu hiện hành, lỗi deadlock có mã Neo4j `Neo.TransientError.Transaction.DeadlockDetected`. Từ **Neo4j 5.25**, thông tin lỗi còn có GQLSTATUS `50N05`. Không nên viết ứng dụng chỉ phụ thuộc vào một chuỗi thông báo cụ thể, vì biểu diễn lỗi có thể thay đổi theo phiên bản.

### 8.2. Java Driver: managed transaction có cơ chế retry

Ví dụ với **Neo4j Java Driver phiên bản hỗ trợ `executeWrite`**:

```java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class CounterRepository {
    private final Driver driver;

    public CounterRepository(Driver driver) {
        this.driver = driver;
    }

    public long increment(String id) {
        try (var session = driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx ->
                tx.run(
                    """
                    MATCH (c:IsolationCounter {id: $id})
                    SET c.value = c.value + 1
                    RETURN c.value AS value
                    """,
                    Map.of("id", id)
                ).single().get("value").asLong()
            );
        }
    }
}
```

Ở đây:

- `executeWrite` chạy callback trong **managed transaction**; driver có thể **thử lại toàn bộ callback** với lỗi tạm thời đủ điều kiện, theo giới hạn thời gian retry được cấu hình.
- Câu `SET c.value = c.value + 1` giữ quan hệ phụ thuộc trực tiếp cần thiết để Neo4j lấy khóa ghi trước khi đọc.
- `Driver` có thể được chia sẻ, nhưng **Session không thread-safe**; mỗi luồng yêu cầu giao dịch đồng thời nên dùng session riêng.
- Callback có thể được gọi nhiều lần. **Không gửi email, trừ tiền từ hệ thống ngoài hoặc tạo side effect không thể hoàn tác bên trong callback** nếu chưa có cơ chế idempotency thích hợp.

Nếu dùng **explicit transaction** với `session.beginTransaction()`, ứng dụng tự quyết định `commit`/`rollback` và chiến lược retry. Việc retry callback do driver quản lý không tự động áp dụng theo cách giống managed transaction.

Với **Spring Data Neo4j**, `@Transactional` giúp gom các thao tác repository trong một transaction theo cấu hình transaction manager của Spring. Nhưng annotation này **không làm thay đổi mức cô lập mặc định của server**, cũng không tự làm mọi read–modify–write trở nên an toàn. Cần chú ý thiết kế Cypher, giới hạn transaction, phương án retry, và việc Spring có thực sự áp dụng transaction proxy cho lời gọi đó hay không.

### 8.3. Không nhầm bookmark và causal consistency với isolation

Trong cluster, **bookmark** của Neo4j Driver giúp duy trì thứ tự nhân–quả qua các transaction, chẳng hạn một thao tác đọc sau đó cần thấy dữ liệu đã ghi từ transaction trước. Đây là vấn đề **causal consistency giữa các giao dịch và replica**, khác với câu hỏi «hai lần đọc trong cùng transaction có nhất thiết bằng nhau không?».

Không nên kết luận rằng có bookmark thì một transaction trở thành **repeatable read** hay **serializable**. Khi triển khai nhiều database, cluster và read routing, hãy kiểm tra cấu hình session và bookmark thực tế theo Driver/DBMS version.

## 9. Hiểu đúng «theo phiên bản»: phần nào ổn định, phần nào phải đối chiếu?

### 9.1. Ma trận kiểm tra

| Khía cạnh | Neo4j 4.4 | Dòng 5.x, gồm 5.26 LTS | Tài liệu hiện hành (dòng bản phát hành mới) |
| --- | --- | --- | --- |
| Mức cô lập transaction mặc định | **Read committed** | **Read committed** | **Read committed**, theo Operations Manual hiện hành |
| Có thể xảy ra non-repeatable read | Có thể, theo read committed | Có thể | Được ghi rõ trong phần *Concurrent data access* |
| Lost update nếu tách giá trị đọc khỏi phép ghi | Cần cảnh giác; phụ thuộc việc lấy khóa trước khi đọc | Cần cảnh giác | Tài liệu nêu rõ khác biệt giữa `SET` có và không có phụ thuộc trực tiếp |
| Chi tiết khóa cho node dense/sparse và store format | Tra hướng dẫn phiên bản tương ứng | Tra hướng dẫn phiên bản tương ứng | Cơ chế có thể phụ thuộc store format; không sao chép giả định cấu trúc khóa từ bản cũ |
| Mã / cấu trúc lỗi deadlock | Kiểm tra tài liệu API tương ứng | Từ 5.25 có thêm GQLSTATUS `50N05` | Kiểm tra cả error code/GQLSTATUS và cơ chế retry |
| API Java Driver | Ví dụ cũ có thể dùng `writeTransaction` | `executeWrite` là API thường gặp ở Driver mới | Đối chiếu đúng major version của Driver đang dùng |

**Không suy ra phiên bản Neo4j từ phiên bản Java Driver**, và không suy ra phiên bản DBMS từ việc ứng dụng dùng Spring Data Neo4j. Server, driver, Spring Data và store format có vòng đời riêng. Bảng trên chủ yếu chỉ ra **việc cần xác minh**, không phải bảng hứa hẹn mọi thay đổi nội bộ giữa các phiên bản.

### 9.2. Xác định phiên bản đang chạy

Trên hệ thống mà tài khoản có quyền gọi thủ tục, có thể tham khảo:

```cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
```

Trong môi trường quản trị hạn chế hoặc một số dịch vụ đám mây, quyền gọi thủ tục và cách công bố phiên bản có thể khác nhau; nếu câu lệnh không được phép, xem thông tin bản phát hành từ công cụ quản trị/nhà cung cấp. Sau đó mở **đúng bộ tài liệu cùng version**, ưu tiên:

1. **Operations Manual → Database internals → Concurrent data access** để xem mặc định và các loại bất thường.
2. **Operations Manual → Database transactions / Locks** để xem giao dịch, lock contention, deadlock và timeout.
3. **Java Driver Manual → Run your own transactions** cho `executeRead`, `executeWrite`, explicit transaction, retry và session.
4. **Release notes** khi hệ thống đang nâng cấp, đặc biệt nếu có thay đổi runtime, store format, mã lỗi hoặc cơ chế khóa.

### 9.3. Đừng hứa serializable chỉ vì «có khóa»

Neo4j cho phép dùng khóa một cách chủ động để **mô phỏng hiệu ứng mức cô lập mạnh hơn** trong những trường hợp đã kiểm soát. Nhưng việc một transaction sửa node X và transaction khác sửa node Y không đủ để bảo đảm quy tắc **liên quan đồng thời đến X và Y**. Muốn đạt tính tuần tự hóa ở mức một quy tắc nghiệp vụ, phải xác định đúng tập tài nguyên cần bảo vệ và bảo đảm **tất cả đường ghi cùng tuân theo giao thức khóa hoặc constraint**.

## 10. Quy trình thiết kế transaction an toàn

Khi một API cập nhật graph, hãy áp dụng quy trình sau:

1. **Viết rõ bất biến nghiệp vụ.** Ví dụ: số dư không âm, mỗi ghế chỉ được bán một lần, luôn có ít nhất một người trực, hoặc mỗi định danh tài khoản là duy nhất.
2. **Xác định các node và relationship có thể cùng bị cập nhật.** Tìm điểm tranh chấp thật, không chỉ xem câu `SET` cuối cùng.
3. **Dùng index và constraint cho quy tắc có thể biểu đạt bằng schema.** Unique constraint giúp bảo vệ định danh độc nhất khi nhiều request cùng tạo thực thể.
4. **Ưu tiên phép cập nhật trực tiếp có phụ thuộc property**, ví dụ `SET n.counter = n.counter + 1`, khi bài toán là tăng một giá trị.
5. **Nếu có bước kiểm tra rồi ghi trên nhiều thực thể, lập giao thức đồng bộ rõ ràng.** Cân nhắc khóa chung, node guard, thiết kế lại mô hình hoặc tuần tự hóa request cho một khóa nghiệp vụ.
6. **Giữ transaction gọn, dùng tham số và retry có giới hạn** cho transient error. Phân biệt callback của managed transaction với side effect ngoài Neo4j.
7. **Thử bằng ít nhất hai session đồng thời** trên Neo4j phiên bản đang chạy; dùng `EXPLAIN`/`PROFILE` và log transaction/lock khi cần, vì các lịch đồng thời khó tái hiện chỉ bằng một truy vấn.

## 11. Bài tập thực hành

### Bài 1. Nhận diện mức cô lập

Transaction A đọc `value = 5` rồi tiếp tục mở. Transaction B cập nhật `value = 8` và commit. A đọc lại và thấy `8`.

**Câu hỏi:** Đây là bất thường gì? Kết quả này có trái read committed không?

**Đáp án gợi ý:** Đây là **non-repeatable read**. Kết quả có thể xảy ra ở **read committed** vì B đã commit trước lần đọc thứ hai; không phải dirty read.

### Bài 2. Chọn truy vấn tăng số đếm

Hai đoạn sau khác nhau như thế nào dưới tải đồng thời?

```cypher
// Mẫu A: giá trị cũ được chuyển qua biến.
MATCH (c:IsolationCounter {id: 'shared'})
WITH c, c.value AS oldValue
SET c.value = oldValue + 1;
```

```cypher
// Mẫu B: phép ghi phụ thuộc trực tiếp vào property.
MATCH (c:IsolationCounter {id: 'shared'})
SET c.value = c.value + 1;
```

**Đáp án gợi ý:** Mẫu B có phụ thuộc trực tiếp nên Neo4j có cơ chế lấy khóa ghi trước khi đọc property. Mẫu A có nguy cơ *lost update* theo lịch thực thi đồng thời; muốn đọc–tính toán phức tạp thì phải bảo vệ bước đọc ban đầu.

### Bài 3. Xác định vấn đề của quy tắc «còn ít nhất một người trực»

A và B đọc cùng thấy hai người trực, rồi mỗi bên cho một người khác nhau nghỉ. Việc hai transaction ghi lên **hai node khác nhau** có đủ đảm bảo quy tắc không bị vi phạm không?

**Đáp án gợi ý:** Không. Đây là rủi ro *write skew*. Cần một điểm đồng bộ chung, cơ chế khóa đúng tập thực thể hoặc thay đổi mô hình để mọi transaction cạnh tranh trên cùng một tài nguyên bảo vệ quy tắc.

### Bài 4. Phân biệt hiện tượng và cơ chế

Một giao dịch bị Neo4j dừng bởi `Neo.TransientError.Transaction.DeadlockDetected`. Có thể kết luận rằng đã xảy ra dirty read hoặc một phần dữ liệu đã commit sai không?

**Đáp án gợi ý:** Không. Đây là **deadlock** do xung đột thứ tự lấy khóa, không phải bằng chứng dirty read. Giao dịch bị rollback; ứng dụng có thể retry toàn bộ transaction với giới hạn phù hợp.

### Bài 5. Kiểm tra phiên bản thật

Trên môi trường thử nghiệm, xác định **Neo4j server version**, **Java Driver version** và tài liệu tương ứng. Kiểm tra: (a) mức cô lập mặc định, (b) ví dụ direct property dependency của `SET`, (c) retry của managed transaction, (d) cách mã hóa lỗi deadlock. Ghi lại các điểm khác so với ví dụ trong bài nếu dự án sử dụng bản cũ.

## 12. Tổng kết

Neo4j mặc định dùng **read committed**: transaction không nhìn thấy thay đổi **chưa commit** của transaction khác, nhưng có thể gặp **non-repeatable read**, thay đổi tập kết quả, *lost update* trong mẫu đọc–ghi không an toàn và những rủi ro khi nhiều transaction cùng cập nhật đồ thị. **Khóa ghi tự động không có nghĩa mọi kiểm tra nghiệp vụ nhiều bước đều được tuần tự hóa**. Cần hiểu mối quan hệ phụ thuộc khi dùng `SET`, bảo vệ bất biến nghiệp vụ bằng constraint hoặc khóa chung, và dùng retry đúng cách khi gặp deadlock. Khi học hoặc nâng cấp Neo4j, luôn đối chiếu **phiên bản DBMS, driver và tài liệu tương ứng** trước khi dựa vào hành vi chi tiết của khóa hoặc runtime.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual – Database internals and transactional behavior](https://neo4j.com/docs/operations-manual/current/database-internals/)
- [Neo4j Operations Manual – Concurrent data access](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Operations Manual – Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Documentation Archive – chọn tài liệu theo phiên bản](https://neo4j.com/docs/reference/docs-archive/)
