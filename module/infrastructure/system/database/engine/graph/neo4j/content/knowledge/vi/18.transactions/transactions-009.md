# Kiểm thử rollback và bảo toàn bất biến nghiệp vụ

Trong một hệ thống sử dụng Neo4j, giao dịch (*transaction*) không chỉ là cách nhóm nhiều câu lệnh Cypher. Nó còn là ranh giới bảo đảm các thay đổi liên quan được **commit cùng nhau** hoặc **rollback cùng nhau** khi có lỗi. Nếu một thao tác chuyển tiền trừ số dư ví nguồn, cộng số dư ví đích và tạo lịch sử chuyển tiền, việc chỉ hoàn tất hai trong ba bước sẽ khiến đồ thị không nhất quán về nghiệp vụ.

Bài học thuộc chương **Giao dịch** của module `DATABASE_ENGINE_GRAPH_NEO4J`, nơi Neo4j được dùng để mô hình hóa **property graph**, truy vấn node/relationship bằng Cypher và triển khai ứng dụng qua Java Driver hoặc Spring Data Neo4j. Trọng tâm ở đây là **kiểm thử rollback và chứng minh các bất biến nghiệp vụ còn đúng sau lỗi**, kể cả khi một giao dịch gồm nhiều thao tác ghi.

Sau bài học, bạn sẽ:

- Phát biểu bất biến (*invariant*), tiền điều kiện và hậu điều kiện của một giao dịch.
- Tạo dữ liệu thử nghiệm và quan sát sự khác nhau giữa trạng thái **trong giao dịch** với dữ liệu **đã commit**.
- Kiểm thử `rollback()` tường minh, rollback do exception và rollback khi vi phạm constraint.
- Kiểm tra node, relationship và tổng giá trị sau thành công hoặc thất bại.
- Nhận diện giới hạn của các bài kiểm thử đơn luồng trước lỗi đồng thời, retry hoặc mất kết nối lúc commit.

## 1. Rollback phải bảo vệ những gì?

Xét mô hình đồ thị đơn giản:

~~~text
(:TxDemoWallet {walletId, balance})
       |                            ^
       | [:SENT]                    | [:RECEIVED_BY]
       v                            |
(:TxDemoTransfer {transferId, amount, status})
~~~

Mỗi lần chuyển tiền thành công tạo một node `TxDemoTransfer` có quan hệ `SENT` từ ví gửi và `RECEIVED_BY` tới ví nhận. Ví dụ dùng **số nguyên** biểu thị đơn vị tiền nhỏ nhất của hệ thống thử nghiệm để tránh sai số làm tròn của số thực.

Giả sử hai ví ban đầu:

| Ví | `walletId` | `balance` trước giao dịch |
| --- | --- | ---: |
| Ví gửi | `TX-A` | 1.000 |
| Ví nhận | `TX-B` | 500 |
| **Tổng** | | **1.500** |

Giao dịch muốn chuyển 200 đơn vị từ TX-A sang TX-B, đồng thời lưu lịch sử có mã `TX-TRANSFER-001`. **Bất biến** là các điều kiện luôn phải giữ đúng ở trạng thái dữ liệu đã commit.

| Mã | Bất biến / quy tắc nghiệp vụ | Cách nhận biết vi phạm |
| --- | --- | --- |
| I1 | Số dư mỗi ví không âm. | Có `balance < 0` sau commit. |
| I2 | Chuyển tiền nội bộ không tự tạo hoặc làm mất tiền. | Tổng số dư của **hai ví trong kịch bản cô lập** khác 1.500. |
| I3 | Mỗi mã `transferId` đại diện tối đa một giao dịch chuyển tiền đã lưu. | Có hai node lịch sử trùng mã. |
| I4 | Một lịch sử chuyển tiền thành công gắn với đúng một ví gửi và một ví nhận. | Thiếu hoặc thừa quan hệ `SENT` / `RECEIVED_BY`. |
| I5 | Khi thao tác thất bại, mọi số dư và cấu trúc đồ thị liên quan phải trở lại trạng thái trước khi chạy. | Một trong các số dư đổi hoặc xuất hiện node/relationship lịch sử mới. |

I2 chỉ áp dụng cho **tập ví được thử riêng**, khi không có khoản nạp/rút/phí hay thay đổi từ bên ngoài. Nếu hệ thống cho phép nạp, rút, phí, tỷ giá hoặc nhiều ví tham gia, phải mở rộng phương trình bảo toàn theo đúng các luồng tiền đó. Không dùng tổng số dư toàn database làm chứng cứ cho một giao dịch riêng khi có các ghi hợp lệ diễn ra đồng thời.

**Tiền điều kiện** của phép chuyển tiền còn gồm: số tiền dương, ví nguồn và ví đích đều tồn tại, chúng khác nhau, đủ số dư, mã giao dịch hợp lệ và chưa được dùng. Không phải mọi tiền điều kiện đều có thể biểu đạt bằng constraint Neo4j; một phần phải được kiểm tra trong luồng ứng dụng, với kiểm soát đồng thời thích hợp.

## 2. ACID nhìn từ góc độ kiểm thử

Neo4j hỗ trợ giao dịch ACID. Khi viết bài kiểm thử, cần chuyển các thuộc tính tổng quát thành những kết quả quan sát được:

| Thuộc tính | Điều cần quan sát | Điều chưa được chứng minh chỉ bằng một kiểm thử |
| --- | --- | --- |
| **Atomicity** | Sau rollback không còn bất kỳ phần ghi nào của giao dịch: số dư, node lịch sử, relationship. | An toàn đồng thời giữa nhiều giao dịch. |
| **Consistency** | Các quy tắc và constraint được kiểm tra đều đúng sau commit; giao dịch sai quy tắc bị từ chối. | Mọi bất biến nghiệp vụ nếu ứng dụng chưa định nghĩa hoặc kiểm tra chúng. |
| **Isolation** | Giao dịch khác không được nhìn thấy dữ liệu ghi chưa commit; thử nghiệm đồng thời cần kết quả đúng. | Mọi lịch thực thi đồng thời đều serializable theo mặc định. |
| **Durability** | Sau commit thành công, dữ liệu còn tồn tại khi đọc lại trên cơ sở dữ liệu phù hợp. | Khả năng khôi phục sau từng loại sự cố hạ tầng nếu chưa thử phương án phục hồi. |

Hai trường hợp cần phân biệt:

~~~text
THÀNH CÔNG                           THẤT BẠI
BEGIN                                BEGIN
  Trừ ví TX-A                         Trừ ví TX-A
  Cộng ví TX-B                         Lỗi trước khi cộng TX-B
  Tạo TxDemoTransfer                  ROLLBACK
  Tạo 2 relationship                  |
COMMIT                                 v
  |                               Dữ liệu đã commit:
  v                               A=1000, B=500,
A=800, B=700,                    không có transfer mới
có transfer và 2 quan hệ
~~~

Điểm quan trọng là **số dư được thay đổi tạm thời bên trong giao dịch chưa phải trạng thái đã commit**. Kiểm thử cần kết thúc giao dịch rồi đọc lại từ một giao dịch đọc độc lập để xác minh hiệu quả rollback.

## 3. Chuẩn bị dữ liệu thử nghiệm trên một database riêng

Những lệnh dưới đây tạo và thay đổi dữ liệu. Hãy chạy trên **database thử nghiệm có thể đặt lại dữ liệu**, không dùng trên production hoặc database dùng chung. Mỗi đoạn `CREATE CONSTRAINT` là một câu lệnh Cypher riêng.

### 3.1. Ràng buộc định danh

~~~cypher
CREATE CONSTRAINT tx_demo_wallet_id_unique IF NOT EXISTS
FOR (w:TxDemoWallet)
REQUIRE w.walletId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT tx_demo_transfer_id_unique IF NOT EXISTS
FOR (t:TxDemoTransfer)
REQUIRE t.transferId IS UNIQUE;
~~~

Hai uniqueness constraint ngăn các node cùng label trùng giá trị khóa **khi thuộc tính khóa có mặt**. Đây chưa phải quy tắc bắt buộc `walletId` hoặc `transferId` tồn tại; nếu cần vừa bắt buộc vừa duy nhất, thiết kế thêm ràng buộc phù hợp với edition và phiên bản Neo4j đang chạy. Neo4j cũng không có check constraint tổng quát trong ví dụ này để tự đảm bảo `balance >= 0`.

### 3.2. Tạo hai ví ở trạng thái ban đầu

~~~cypher
MERGE (a:TxDemoWallet {walletId: 'TX-A'})
MERGE (b:TxDemoWallet {walletId: 'TX-B'})
SET a.balance = 1000,
    b.balance = 500
RETURN a.walletId AS viGui, a.balance AS soDuGui,
       b.walletId AS viNhan, b.balance AS soDuNhan;
~~~

Ví dụ giả định hai ví thử nghiệm chưa có quan hệ lịch sử cần bảo toàn. Nếu chạy lại bài thực hành, hãy kiểm soát các `TxDemoTransfer` đã tạo ở lượt trước; việc reset số dư **không tự xóa lịch sử**. Chỉ dọn đúng dữ liệu thử nghiệm do bạn sở hữu trên database đã chọn.

### 3.3. Chụp trạng thái ban đầu

~~~cypher
MATCH (a:TxDemoWallet {walletId: 'TX-A'})
MATCH (b:TxDemoWallet {walletId: 'TX-B'})
OPTIONAL MATCH (t:TxDemoTransfer {transferId: 'TX-ROLLBACK-001'})
RETURN a.balance AS soDuA,
       b.balance AS soDuB,
       a.balance + b.balance AS tongHaiVi,
       count(t) AS soBanGhiThu;
~~~

Kết quả mong đợi trước một bài kiểm thử rollback sạch: `soDuA = 1000`, `soDuB = 500`, tổng 1.500 và `soBanGhiThu = 0`. Nếu mã `TX-ROLLBACK-001` đã có, hãy dùng fixture/mã khác hoặc làm sạch đúng dữ liệu thử nghiệm; không chấp nhận trạng thái ban đầu mơ hồ.

## 4. Định nghĩa một giao dịch chuyển tiền trên đồ thị

Đây là câu lệnh Cypher mô tả cả ba phần: cập nhật hai ví, tạo lịch sử và tạo hai relationship:

~~~cypher
MATCH (sender:TxDemoWallet {walletId: $fromId})
MATCH (recipient:TxDemoWallet {walletId: $toId})
WHERE sender <> recipient
  AND $amount > 0
  AND sender.balance >= $amount
SET sender.balance = sender.balance - $amount,
    recipient.balance = recipient.balance + $amount
CREATE (transfer:TxDemoTransfer {
  transferId: $transferId,
  amount: $amount,
  status: 'COMPLETED'
})
CREATE (sender)-[:SENT]->(transfer)
CREATE (transfer)-[:RECEIVED_BY]->(recipient)
RETURN transfer.transferId AS transferId,
       sender.balance AS soDuGui,
       recipient.balance AS soDuNhan;
~~~

Ví dụ tham số:

| Tham số | Giá trị |
| --- | --- |
| `$fromId` | `'TX-A'` |
| `$toId` | `'TX-B'` |
| `$amount` | `200` |
| `$transferId` | `'TX-ROLLBACK-001'` |

Khi chạy thành công và **commit**, trạng thái hợp lệ là TX-A = 800, TX-B = 700, có một node `TxDemoTransfer` và đúng hai relationship nối đúng ví. Nếu số tiền không hợp lệ, ví không tồn tại hoặc không đủ tiền, mẫu `MATCH ... WHERE` trả về **0 hàng**: ứng dụng phải coi đây là yêu cầu chuyển tiền **không thành công** thay vì mặc định kết quả rỗng là đã xử lý.

**Phạm vi bảo đảm của ví dụ:** một câu lệnh ghi trong một transaction thể hiện tính nguyên tử, nhưng chưa đủ để khẳng định luồng chuyển tiền an toàn trước mọi tình huống đồng thời. Kiểm tra `sender.balance >= $amount` có thể chịu ảnh hưởng của thời điểm đọc và tranh chấp giữa các giao dịch; phần kiểm thử đồng thời ở mục 10 giải thích cách phát hiện lỗi. Hệ thống tài chính thật phải có chiến lược khóa/tuần tự hóa, xác thực, idempotency và ghi sổ được đánh giá riêng.

## 5. Thử rollback tường minh với Neo4j Java Driver

Java Driver hỗ trợ **explicit transaction**: bắt đầu bằng `beginTransaction()`, gọi `tx.run()`, rồi chọn `commit()` hoặc `rollback()`. Điều này rất phù hợp để thử một thay đổi đã chạy nhưng **chủ động không commit**.

Ví dụ sau dùng `org.neo4j.driver.Driver` (API của Neo4j Java Driver 5.x). Giả định fixture đã được khởi tạo đúng như mục 3 và chưa có transfer mã `TX-ROLLBACK-001`.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Transaction;

public final class ExplicitRollbackExample {
    private static final String TRANSFER = """
        MATCH (sender:TxDemoWallet {walletId: $fromId})
        MATCH (recipient:TxDemoWallet {walletId: $toId})
        WHERE sender <> recipient
          AND $amount > 0
          AND sender.balance >= $amount
        SET sender.balance = sender.balance - $amount,
            recipient.balance = recipient.balance + $amount
        CREATE (transfer:TxDemoTransfer {
          transferId: $transferId,
          amount: $amount,
          status: 'COMPLETED'
        })
        CREATE (sender)-[:SENT]->(transfer)
        CREATE (transfer)-[:RECEIVED_BY]->(recipient)
        RETURN transfer.transferId AS transferId
        """;

    public static void verifyExplicitRollback(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            try (Transaction tx = session.beginTransaction()) {
                Record result = tx.run(TRANSFER, Map.of(
                    "fromId", "TX-A",
                    "toId", "TX-B",
                    "amount", 200L,
                    "transferId", "TX-ROLLBACK-001"
                )).single();

                if (!"TX-ROLLBACK-001"
                        .equals(result.get("transferId").asString())) {
                    throw new AssertionError("Sai kết quả giao dịch");
                }

                // Cố ý hủy ngay cả khi câu lệnh Cypher đã chạy.
                tx.rollback();
            }

            Record balances = session.run("""
                MATCH (a:TxDemoWallet {walletId: 'TX-A'})
                MATCH (b:TxDemoWallet {walletId: 'TX-B'})
                RETURN a.balance AS a, b.balance AS b
                """).single();
            long a = balances.get("a").asLong();
            long b = balances.get("b").asLong();

            long events = session.run("""
                MATCH (t:TxDemoTransfer {
                  transferId: 'TX-ROLLBACK-001'
                })
                RETURN count(t) AS n
                """).single().get("n").asLong();

            if (a != 1000L || b != 500L || events != 0L) {
                throw new AssertionError(
                    "Rollback sai: A=" + a + ", B=" + b
                        + ", events=" + events
                );
            }
        }
    }
}
~~~

Các điểm cần chú ý:

- Cả việc cập nhật số dư và tạo lịch sử nằm trong **cùng một `Transaction`**.
- `tx.rollback()` kết thúc transaction mà không công bố các ghi tạm thời.
- Phần kiểm tra được thực hiện **sau khi đã rollback**; câu `session.run()` lúc này chạy một giao dịch đọc mới trên cùng session.
- Không chỉ assert số dư: phải assert cả lịch sử. Nếu có dữ liệu quan hệ còn sót thì cũng là lỗi nguyên tử.
- Ví dụ giả định database có tên `neo4j` và trạng thái ban đầu không có thao tác khác xen vào. Trong một test suite thật, nên dùng fixture cô lập và tên database tương ứng.

**Sai lầm phổ biến:** kiểm tra số dư bằng chính `tx.run()` trước `rollback()` rồi kết luận dữ liệu đã được lưu. Transaction được quyền thấy các ghi chưa commit của chính nó, nên cách kiểm tra đó **không chứng minh dữ liệu sẽ tồn tại sau commit hoặc biến mất sau rollback**.

## 6. Tạo lỗi giữa các bước để kiểm thử rollback do exception

Trên thực tế, exception có thể phát sinh **sau khi trừ tiền nhưng trước khi cộng tiền**, hoặc sau khi tạo lịch sử nhưng trước commit. Một bài kiểm thử có giá trị phải chủ động tạo ra các tình huống đó.

### 6.1. Managed transaction tự rollback khi callback thất bại

Java Driver cung cấp `session.executeWrite(...)` để quản lý transaction ghi và có thể retry **một số lỗi transient**. Nếu callback ném ra exception ứng dụng không thuộc loại retryable, giao dịch sẽ không commit.

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class FaultInjectionExample {
    public static void rollbackAfterDebit(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            try {
                session.executeWrite(tx -> {
                    tx.run("""
                        MATCH (w:TxDemoWallet {walletId: 'TX-A'})
                        SET w.balance = w.balance - 200
                        """).consume();

                    // Giả lập lỗi sau bước trừ tiền.
                    throw new IllegalStateException("INJECTED_AFTER_DEBIT");
                });
                throw new AssertionError("Phải có exception thử nghiệm");
            } catch (IllegalStateException ex) {
                if (!"INJECTED_AFTER_DEBIT".equals(ex.getMessage())) {
                    throw ex;
                }
            }

            long actual = session.run("""
                MATCH (w:TxDemoWallet {walletId: 'TX-A'})
                RETURN w.balance AS balance
                """).single().get("balance").asLong();

            if (actual != 1000L) {
                throw new AssertionError(
                    "Số dư TX-A thay đổi sau rollback: " + actual
                );
            }
        }
    }
}
~~~

Đoạn code chỉ minh họa **điểm lỗi ngay sau một phần ghi**. Nó không phải dịch vụ chuyển tiền hoàn chỉnh. Khi chạy trong fixture sạch, số dư TX-A sau exception vẫn là 1.000. Thực tế nên chụp trạng thái trước khi chạy thay vì luôn dùng giá trị cố định nếu test có thể chạy với các dữ liệu khác.

Không đặt side effect **ngoài Neo4j** như gửi email, gọi cổng thanh toán hoặc phát thông điệp không thể hoàn tác trực tiếp trong managed callback mà không tính đến retry. Driver có thể gọi lại callback khi gặp một số lỗi transient. Rollback đồ thị không tự thu hồi email hay yêu cầu HTTP đã phát đi. Nếu cần nhất quán giữa DB và message broker, cân nhắc mẫu **transactional outbox**, idempotency và giao thức tích hợp phù hợp.

### 6.2. Các điểm bơm lỗi (*failpoints*)

| Điểm lỗi được mô phỏng | Điều đã chạy trước khi lỗi | Điều bắt buộc kiểm tra sau rollback |
| --- | --- | --- |
| F0 — trước ghi | Chỉ kiểm tra đầu vào. | Hai ví không đổi, không có transfer mới. |
| F1 — sau trừ ví nguồn | `SET sender.balance = ...` | TX-A về giá trị ban đầu; TX-B và lịch sử không đổi. |
| F2 — sau cộng ví đích | Hai thao tác số dư. | Cả hai ví về trạng thái ban đầu; tổng được bảo toàn. |
| F3 — sau tạo node lịch sử | Đã cập nhật số dư và tạo `TxDemoTransfer`. | Không còn node lịch sử mới và không mất tiền. |
| F4 — sau tạo relationship | Toàn bộ thay đổi đã tạo nhưng chưa commit. | Không còn node/relationship hoặc cập nhật số dư mới. |
| F5 — lỗi constraint | Một ghi trong cùng transaction vi phạm uniqueness. | Toàn bộ phần ghi trước lỗi bị rollback. |

Có thể triển khai các failpoint F1–F4 bằng cách tách các thao tác thành nhiều `tx.run()` trong **một explicit transaction**, rồi cố ý ném exception hoặc gọi `rollback()` tại vị trí kiểm thử. Không chạy từng bước qua các session/transaction tự commit riêng lẻ: lúc đó mỗi phần có thể đã commit, không còn là phép thử nguyên tử của một giao dịch.

## 7. Kiểm thử lỗi constraint và tính toàn vẹn của graph

Unique constraint trên `TxDemoTransfer.transferId` được tạo ở mục 3. Có thể dùng nó để kiểm tra một lỗi cơ sở dữ liệu khiến transaction thất bại.

Chuẩn bị một node lịch sử cố định trong **fixture thử nghiệm**, với một mã riêng:

~~~cypher
MERGE (t:TxDemoTransfer {transferId: 'TX-DUPLICATE-001'})
ON CREATE SET t.amount = 1, t.status = 'TEST_SEED';
~~~

Trong test, thực hiện các bước trong **một transaction**:

1. Trừ số dư TX-A như bước đầu giao dịch chuyển tiền.
2. Thực hiện `CREATE (:TxDemoTransfer {transferId: 'TX-DUPLICATE-001'})`.
3. Xác nhận thao tác bước 2 bị Neo4j từ chối vì mã đã có và uniqueness constraint đang hoạt động.
4. Rollback/đóng transaction và đọc số dư TX-A trong một giao dịch mới: phải trở lại 1.000.

Cypher cố ý gây vi phạm:

~~~cypher
CREATE (:TxDemoTransfer {
  transferId: 'TX-DUPLICATE-001',
  amount: 200,
  status: 'COMPLETED'
});
~~~

Sau exception từ database, **không tiếp tục ghi tiếp trong transaction lỗi rồi hy vọng các thao tác sẽ commit**. Xử lý lỗi ở ranh giới giao dịch; đảm bảo transaction được rollback và giải phóng trước khi kiểm tra lại.

Ngoài uniqueness, có thể kiểm tra sự toàn vẹn của các quan hệ đối với lịch sử đã commit:

~~~cypher
MATCH (t:TxDemoTransfer)
WHERE t.status = 'COMPLETED'
OPTIONAL MATCH (:TxDemoWallet)-[sent:SENT]->(t)
WITH t, count(sent) AS soQuanHeGui
OPTIONAL MATCH (t)-[received:RECEIVED_BY]->(:TxDemoWallet)
WITH t, soQuanHeGui, count(received) AS soQuanHeNhan
WHERE soQuanHeGui <> 1 OR soQuanHeNhan <> 1
RETURN t.transferId AS maChuyenTien,
       soQuanHeGui, soQuanHeNhan;
~~~

Trên **tập dữ liệu thử nghiệm do bài học tạo**, truy vấn nên trả 0 hàng sau commit hợp lệ. Đây là quy tắc ứng dụng kiểm tra bằng truy vấn, không mặc nhiên là một constraint Neo4j buộc đúng số relationship. Khi cả hai bên có thể có nhiều quan hệ trùng hoặc mô hình không giới hạn số quan hệ, cần thiết kế thao tác ghi và kiểm thử phù hợp.

Kiểm tra riêng các bản ghi không mong muốn sau rollback:

~~~cypher
MATCH (t:TxDemoTransfer {transferId: 'TX-ROLLBACK-001'})
OPTIONAL MATCH ()-[s:SENT]->(t)
OPTIONAL MATCH (t)-[r:RECEIVED_BY]->()
RETURN count(DISTINCT t) AS soTransfer,
       count(DISTINCT s) AS soSent,
       count(DISTINCT r) AS soReceivedBy;
~~~

Sau rollback, cả ba số đếm phải bằng 0. Nếu không có node `t`, hai quan hệ đi qua `t` cũng không thể còn dưới dạng quan hệ mồ côi: Neo4j không lưu relationship không có endpoint. Vì vậy, kiểm tra số đếm này cho phép quan sát rõ hơn trạng thái thử nghiệm.

## 8. Kiểm thử giao dịch commit thành công

Rollback luôn cần một **đối chứng thành công**. Một bài kiểm thử chỉ chứng minh “lỗi dẫn đến không ghi gì” có thể vô tình vượt qua vì code không từng ghi dữ liệu.

Với dữ liệu ban đầu TX-A=1000, TX-B=500, chạy câu `TRANSFER` ở mục 4 trong một transaction và **commit** với mã riêng `TX-COMMIT-001`. Sau đó đọc từ giao dịch mới:

~~~cypher
MATCH (a:TxDemoWallet {walletId: 'TX-A'})
MATCH (b:TxDemoWallet {walletId: 'TX-B'})
MATCH (t:TxDemoTransfer {transferId: 'TX-COMMIT-001'})
MATCH (a)-[:SENT]->(t)-[:RECEIVED_BY]->(b)
RETURN a.balance AS soDuA,
       b.balance AS soDuB,
       a.balance + b.balance AS tongHaiVi,
       t.amount AS soTien,
       t.status AS trangThai;
~~~

Kết quả hợp lệ là `soDuA=800`, `soDuB=700`, `tongHaiVi=1500`, `soTien=200` và `trangThai='COMPLETED'`. Cần bổ sung kiểm tra **số lượng** transfer cùng mã bằng 1 và đúng một quan hệ mỗi loại; việc `MATCH` trả ra một hàng chỉ cho biết đường đi tồn tại, chưa chứng minh tính duy nhất của mọi cạnh nếu mô hình cho phép các quan hệ trùng.

Đối với test rollback, hãy tạo **fixture mới** hoặc reset đúng ví thử nghiệm trước mỗi kịch bản. Nếu chạy commit thành công rồi dùng nguyên trạng thái để chạy test rollback mong đợi TX-A=1000, bài kiểm thử sẽ thất bại do trạng thái ban đầu đã đổi, không phải do Neo4j rollback sai.

## 9. Spring Data Neo4j: kiểm thử đúng ranh giới transaction

Trong ứng dụng Spring Data Neo4j, transaction thường được quản lý ở **tầng service** qua `@Transactional` với transaction manager dành cho Neo4j. Một lời gọi service có thể ghi nhiều node và relationship; nếu bất kỳ bước nào ném exception làm transaction rollback, toàn bộ thay đổi thuộc transaction đó phải được hủy.

Ví dụ minh họa:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TxDemoService {
    private final Neo4jClient client;

    public TxDemoService(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public void debitThenFail() {
        client.query("""
            MATCH (w:TxDemoWallet {walletId: 'TX-A'})
            SET w.balance = w.balance - 200
            """).run();

        // Exception runtime làm rollback theo quy tắc mặc định của Spring.
        throw new IllegalStateException("INJECTED_AFTER_DEBIT");
    }
}
~~~

Một integration test có thể gọi **bean service qua Spring context**, bắt exception mong đợi rồi đọc lại dữ liệu bằng một transaction độc lập. Điều quan trọng là cấu hình `Neo4jTransactionManager`/transaction manager đúng với database được dùng, và lời gọi đi qua proxy/interceptor của Spring. Gọi `@Transactional` method từ một method khác trong **cùng bean** (*self-invocation*) có thể không kích hoạt cơ chế proxy transaction theo cách thông thường.

Phân biệt hai quy tắc rollback của Spring:

- Mặc định, `@Transactional` thường đánh dấu rollback khi method ném `RuntimeException` hoặc `Error`.
- Exception checked như `IOException` có thể không gây rollback theo mặc định; nếu nghiệp vụ yêu cầu, cấu hình `@Transactional(rollbackFor = IOException.class)` hoặc chọn cách biểu diễn lỗi phù hợp.

Cũng cần chú ý: test có `@Transactional` ở **cấp phương thức test** trong Spring Test thường được framework rollback mặc định sau khi test kết thúc. Điều đó hữu ích để cô lập fixture, nhưng có thể che khuất việc code ứng dụng có thực sự commit khi chạy bên ngoài test hay không. Hãy có bài kiểm thử riêng xác nhận **commit thành công** và một bài kiểm thử thất bại đọc trạng thái bằng transaction độc lập, tránh đọc dữ liệu chưa commit trong cùng ngữ cảnh.

Nếu một thao tác nghiệp vụ còn ghi sang hệ thống khác (RDBMS, Kafka, HTTP), annotation transaction Neo4j **không tự tạo ACID phân tán** giữa các hệ thống đó. Cần thiết kế bù trừ, outbox hoặc saga tùy yêu cầu nhất quán.

## 10. Kiểm thử đồng thời, retry và trạng thái commit chưa xác định

Các bài thử F0–F5 đơn luồng rất quan trọng nhưng **chưa chứng minh** việc chuyển tiền luôn đúng khi nhiều giao dịch chạy cạnh tranh.

### 10.1. Hai giao dịch cùng trừ một ví

Giả sử TX-A có 1.000, đồng thời có hai yêu cầu chuyển **700** từ TX-A sang hai ví khác. Nếu cả hai cùng nhìn thấy số dư 1.000 trước khi có cơ chế đồng bộ ghi phù hợp, hệ thống có nguy cơ chấp nhận sai hoặc cập nhật dựa trên dữ liệu cũ.

Bài test nên dùng barrier để hai worker cùng bắt đầu ở thời điểm gần nhau, chạy nhiều vòng, sau đó kiểm tra:

1. Không có ví nào mang số dư âm.
2. Tổng tiền của các ví tham gia vẫn đúng (khi không có hoạt động ngoài phép chuyển).
3. Không có lịch sử `COMPLETED` cho một chuyển tiền mà các bút toán số dư chưa được commit.
4. Số lượng giao dịch thành công phù hợp với số dư thực tế, không dựa vào thông báo API thành công nếu DB đã rollback.

Để bảo vệ điều kiện “đủ số dư”, cần xác định và thực hiện **chiến lược khóa/tuần tự hóa thích hợp**, đọc lại giá trị sau khi giành quyền ghi nếu quy trình đòi hỏi, và kiểm thử dưới tải. **Không suy luận rằng câu `WHERE sender.balance >= $amount` trong ví dụ đơn luồng là đủ chống mọi race condition.** Neo4j có cơ chế lock khi ghi, nhưng vị trí đọc điều kiện, kế hoạch truy vấn và cạnh tranh giữa transaction vẫn phải được phân tích trên truy vấn thực tế.

Khi có nhiều node bị cập nhật, thống nhất thứ tự lấy lock hoặc dùng cách tương đương để giảm nguy cơ deadlock. Khi driver báo lỗi transient có thể retry, cần phân biệt retry **cả transaction** với retry một câu lệnh rời rạc đã để lại các side effect bên ngoài.

### 10.2. Retry và idempotency

Một yêu cầu chuyển tiền có thể được gửi lại do timeout ở client hoặc lỗi mạng. Nếu client **không nhận được phản hồi commit**, không thể tự động kết luận giao dịch đã rollback; có trường hợp commit đã thành công nhưng phản hồi không tới client.

Do đó, gắn mỗi yêu cầu với mã `transferId` ổn định và kiểm tra trạng thái đã lưu để điều hòa kết quả sau lỗi không xác định. Uniqueness constraint ngăn hai node lịch sử trùng mã, nhưng bản thân nó không đầy đủ để xây dựng API chuyển tiền idempotent: hệ thống còn phải trả lại kết quả cũ một cách có kiểm soát, không lặp bút toán, xử lý xung đột tham số của cùng mã yêu cầu và trạng thái đang xử lý.

Ví dụ kiểm thử quan trọng:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Gọi cùng một `transferId` hai lần với cùng thông tin | Không thực hiện chuyển tiền hai lần; có cách nhận diện kết quả đã xử lý. |
| Gọi cùng mã nhưng khác số tiền | Phát hiện xung đột idempotency; không tự chấp nhận ghi mới sai thông tin. |
| Lỗi trước commit đã xác nhận rollback | Không có thay đổi đã commit; có thể thực hiện lại theo chính sách. |
| Mất kết nối đúng lúc commit | Trạng thái ban đầu **chưa xác định** với client; tra cứu bằng mã yêu cầu trước khi phát lại. |
| Managed callback bị retry vì lỗi transient | Các ghi Neo4j trong transaction đã rollback phải không để lại thay đổi; side effect ngoài DB phải được kiểm soát. |

Trong Neo4j cluster, khi kiểm chứng read-after-write qua session khác, cần thiết lập nhất quán nhân quả theo cấu hình Driver/bookmark thích hợp để tránh nhầm lẫn do đọc trên các thành viên khác nhau. Đừng quy một lần đọc chưa thấy dữ liệu thành bằng chứng transaction đã rollback nếu điều kiện quan sát chưa được bảo đảm.

### 10.3. Batch transaction không có nghĩa là một transaction lớn

Một số tác vụ nhập dữ liệu dùng `CALL { ... } IN TRANSACTIONS` để chia xử lý thành các lô giao dịch. Khi một lô sau thất bại, **các lô trước có thể đã commit**. Không dùng cơ chế chia lô để triển khai thao tác nghiệp vụ yêu cầu “toàn bộ hoặc không có gì” trên tất cả phần tử mà không thiết kế cơ chế phục hồi riêng.

## 11. Ma trận kiểm thử và cách tổ chức fixture

Nên có một bộ test chạy tự động trong **database tách biệt**, với dữ liệu được đặt lại về trạng thái xác định trước từng kịch bản. Dưới đây là ma trận tối thiểu:

| ID | Trường hợp | Kết quả cần assert |
| --- | --- | --- |
| T01 | Chuyển 200 thành công và commit | A=800, B=700, tổng=1500, một transfer, đúng các quan hệ. |
| T02 | Gọi `rollback()` sau khi toàn bộ Cypher chạy | A=1000, B=500, không có lịch sử giao dịch thử. |
| T03 | Exception sau trừ tiền | Cả hai số dư và mọi lịch sử không đổi. |
| T04 | Exception sau tạo node lịch sử | Node và relationship mới không tồn tại sau rollback. |
| T05 | Vi phạm uniqueness giữa transaction | Mọi phần ghi trước lỗi được hủy; ngoại lệ đúng loại được quan sát. |
| T06 | Số tiền 0 hoặc âm | Dịch vụ từ chối; không commit thay đổi. |
| T07 | Không đủ số dư | Không có chuyển tiền/lịch sử hoàn tất; số dư không đổi. |
| T08 | Ví gửi trùng ví nhận, hoặc thiếu một endpoint | Giao dịch không hoàn tất; không ghi một phần. |
| T09 | Hai yêu cầu cạnh tranh trên cùng số dư | Bất biến và kết quả xử lý đồng thời vẫn đúng. |
| T10 | Retry cùng mã giao dịch | Không phát sinh chuyển tiền hai lần. |
| T11 | Timeout/mất phản hồi commit | Có thể hòa giải trạng thái bằng `transferId`; không giả định rollback. |
| T12 | Ứng dụng Spring ném exception checked/runtime | Kết quả rollback đúng với cấu hình `@Transactional`. |

Một khuôn tổ chức kiểm thử:

~~~text
beforeEach:
  - chuẩn bị database/fixture riêng
  - tạo 2 ví A=1000, B=500 và ràng buộc định danh
  - xác nhận chưa có transfer thuộc test hiện tại

test:
  - chụp snapshot số dư, số node, số relationship có liên quan
  - gọi đúng API giao dịch (explicit tx hoặc service)
  - tạo lỗi tại failpoint hoặc commit thành công
  - chờ transaction kết thúc và đọc bằng transaction độc lập
  - assert số dư, tổng, transfer, relationship và lỗi dự kiến

afterEach:
  - dọn đúng fixture của bài kiểm thử
  - không xóa node/relationship ngoài phạm vi đã sở hữu
~~~

**Giá trị của kiểm thử:** so sánh snapshot **trước/sau** giúp phát hiện trường hợp “không có exception nhưng số dư thay đổi sai”. Không dùng số lượng node toàn database làm oracle khi môi trường có ghi đồng thời; định danh fixture riêng bằng khóa và truy vấn đúng nhóm dữ liệu.

### 11.1. Truy vấn rà soát bất biến số dư

~~~cypher
MATCH (w:TxDemoWallet)
WHERE w.walletId IN ['TX-A', 'TX-B']
RETURN count(w) AS soVi,
       sum(w.balance) AS tongSoDu,
       min(w.balance) AS soDuThapNhat;
~~~

Trên fixture có đúng hai ví: `soVi = 2`, `tongSoDu = 1500`, `soDuThapNhat >= 0`. **Đếm số ví** trước khi chấp nhận tổng: nếu một node bị xóa, `sum()` có thể vẫn trả số có vẻ hợp lý với tập dữ liệu khác mong muốn. Nếu `balance` thiếu/null, cách tính tổng và min có thể bỏ qua giá trị; cần assert mọi ví có thuộc tính hợp lệ và kiểu số nguyên mong muốn.

### 11.2. Truy vấn rà soát transfer có đủ endpoint

~~~cypher
MATCH (t:TxDemoTransfer {transferId: $transferId})
OPTIONAL MATCH (source:TxDemoWallet)-[:SENT]->(t)
WITH t, count(source) AS senderCount
OPTIONAL MATCH (t)-[:RECEIVED_BY]->(target:TxDemoWallet)
RETURN t.transferId AS transferId,
       senderCount,
       count(target) AS recipientCount;
~~~

Khi **commit thành công**, kỳ vọng đúng một dòng với `senderCount = 1` và `recipientCount = 1`. Khi **rollback**, truy vấn `MATCH (t ... )` trả 0 dòng; đó là kỳ vọng khác nhau và phải được assert đúng. Với một mô hình cho phép nhiều relationship trùng tới cùng ví, có thể cần đếm relationship thay vì chỉ node, và đối chiếu endpoint cụ thể với yêu cầu chuyển tiền.

## 12. Những lỗi diễn giải kết quả kiểm thử thường gặp

| Quan sát | Kết luận vội vàng cần tránh | Cách kiểm chứng chính xác |
| --- | --- | --- |
| `tx.run()` trả về số dư đã thay đổi | “Đã commit thành công.” | Chỉ kết luận sau `commit()` và đọc lại theo ngữ cảnh nhất quán. |
| Callback ném exception | “Chắc chắn rollback và không có side effect.” | Đọc lại node/relationship; kiểm tra thêm side effect ngoài DB. |
| Test kết thúc với DB sạch | “Service đã tự rollback đúng.” | Kiểm tra test framework có tự rollback transaction bao ngoài hay không. |
| Không tìm thấy lịch sử mới | “Toàn bộ giao dịch đã rollback.” | Cũng phải kiểm tra số dư và quan hệ liên quan. |
| `sum(balance)` bằng giá trị cũ | “Không có lỗi dữ liệu.” | Kiểm tra từng ví, số lượng ví, thuộc tính hợp lệ, lịch sử và quan hệ. |
| Client mất kết nối khi commit | “Giao dịch đã thất bại.” | Hòa giải bằng mã yêu cầu trên database với read consistency phù hợp. |
| Thử một lần hai request đồng thời đều đúng | “Hệ thống không có race condition.” | Chạy test cạnh tranh có barrier, nhiều lịch xen kẽ và xác minh bất biến. |
| Vi phạm constraint báo lỗi | “Mọi quy tắc nghiệp vụ đã được bảo vệ.” | Phân biệt các constraint Neo4j với điều kiện nghiệp vụ trong service. |

## 13. Bài tập thực hành

**Bài 1 — Chứng minh rollback:** Tạo fixture TX-A/TX-B như mục 3. Trong một explicit transaction, trừ 200 và cộng 200, tạo transfer mã `TX-EXERCISE-01` rồi gọi `rollback()`. Chụp ảnh trạng thái trước/sau bằng các truy vấn Cypher và giải thích vì sao một kết quả đọc *bên trong* transaction chưa đủ để chứng minh rollback.

**Bài 2 — Ba điểm lỗi:** Viết một phương thức test nhận tham số `failpoint`. Dùng các giá trị `AFTER_DEBIT`, `AFTER_CREDIT`, `AFTER_TRANSFER_CREATE` để ném exception tại ba điểm khác nhau trong cùng transaction. Mỗi lần chạy phải khởi tạo fixture độc lập và kiểm tra lại ít nhất I1, I2, I4, I5.

**Bài 3 — Lỗi uniqueness:** Tạo sẵn `TxDemoTransfer {transferId:'TX-DUPLICATE-001'}` trên database thử nghiệm; bắt đầu một transaction mới, thử trừ số dư rồi tạo transfer cùng mã. Xác minh lỗi constraint và chứng minh phần trừ số dư không được commit.

**Bài 4 — Concurrency:** Hai request cùng chuyển 700 từ ví có 1.000. Hãy liệt kê tất cả kết quả được phép theo quy tắc “không âm, tổng bảo toàn, có log cho mỗi chuyển tiền đã commit”, rồi thiết kế bài kiểm thử có barrier để phát hiện cập nhật sai. Mô tả cơ chế khóa/tuần tự hóa sẽ dùng trong hệ thống thật và vì sao chỉ test tuần tự là chưa đủ.

**Bài 5 — Mất phản hồi commit:** Client gửi yêu cầu mã `TX-RETRY-09`, nhưng mất kết nối ngay lúc commit. Thiết kế bước hòa giải và quy tắc idempotency để không chuyển tiền hai lần, kể cả khi cùng mã được gửi lại với số tiền khác.

Gợi ý kiểm chứng tối thiểu sau rollback:

~~~cypher
MATCH (a:TxDemoWallet {walletId: 'TX-A'})
MATCH (b:TxDemoWallet {walletId: 'TX-B'})
OPTIONAL MATCH (t:TxDemoTransfer {transferId: $transferId})
RETURN a.balance AS aBalance,
       b.balance AS bBalance,
       a.balance + b.balance AS total,
       count(t) AS transferCount;
~~~

Giá trị đúng trên fixture ban đầu là `aBalance=1000`, `bBalance=500`, `total=1500` và `transferCount=0`. Từ đó kiểm tra thêm các quan hệ và điều kiện cụ thể của bài tập.

**Nguyên tắc cần nhớ:** rollback chỉ có ý nghĩa khi đã xác định **những bất biến nào phải được giữ** và **những ghi nào phải cùng thuộc một transaction**. Hãy kiểm thử cả luồng commit thành công, các điểm lỗi trước commit, exception của database, retry và cạnh tranh đồng thời; đọc lại dữ liệu đã commit bằng ngữ cảnh độc lập để có bằng chứng rõ ràng rằng property graph vẫn hợp lệ.
