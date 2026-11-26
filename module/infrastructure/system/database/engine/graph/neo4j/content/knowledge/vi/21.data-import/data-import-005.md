# Phân lô nhập bằng giao dịch và theo dõi tiến độ

Trong Neo4j, dữ liệu được mô hình hóa dưới dạng **property graph** gồm node, relationship, label, relationship type và property. Khi nhập hàng trăm nghìn hoặc hàng triệu bản ghi từ CSV, API hay hệ thống khác, một giao dịch chứa toàn bộ dữ liệu có thể chiếm nhiều bộ nhớ, giữ khóa lâu và khó khôi phục khi xảy ra lỗi. **Chia dữ liệu thành các lô (batch)**, xử lý từng lô trong giao dịch riêng và ghi nhận tiến độ giúp việc nhập dữ liệu có thể kiểm soát, đo lường và chạy lại an toàn hơn.

Bài thuộc chương **Nhập dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`, tập trung vào cách dùng **`LOAD CSV` kết hợp `CALL { ... } IN TRANSACTIONS`** và cách chủ động chia lô từ **Java Driver**. Nội dung cũng giải thích thiết kế khóa định danh, constraint, xử lý dữ liệu lỗi, tiến độ đã **commit**, khôi phục sau gián đoạn và lựa chọn kích thước lô. Ví dụ Cypher hướng đến Neo4j 5; cú pháp import biến vào subquery `CALL (row)` cần Neo4j **5.23 trở lên**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao nhập dữ liệu theo lô giảm phạm vi rollback và giúp kiểm soát tài nguyên giao dịch.
2. Dùng `LOAD CSV` và `CALL { ... } IN TRANSACTIONS OF n ROWS` để nhập node hoặc relationship.
3. Chọn kích thước lô ban đầu, điều chỉnh theo số liệu thực tế và hiểu đánh đổi giữa lô quá nhỏ và quá lớn.
4. Phân biệt số **hàng nguồn đã đọc**, số **hàng được chấp nhận**, số **giao dịch/lô đã commit** và số **node/relationship được tạo mới**.
5. Thiết kế cơ chế checkpoint để có thể tiếp tục import an toàn sau lỗi bằng Java Driver.
6. Quan sát hoạt động import và kiểm tra tính đúng đắn bằng Cypher.

## 2. Vì sao cần phân lô theo giao dịch?

Một giao dịch trong Neo4j là một đơn vị nguyên tử: **hoặc toàn bộ thay đổi trong giao dịch đó được commit, hoặc toàn bộ bị rollback**. Với nhập dữ liệu lớn, cách chia lô thay đổi phạm vi của đơn vị nguyên tử:

~~~text
Nguồn dữ liệu (10.000 dòng)
         |
         v
  [Lô 1: 1..1000] ------> TX 1: COMMIT
  [Lô 2: 1001..2000] ---> TX 2: COMMIT
  [Lô 3: 2001..3000] ---> TX 3: ROLLBACK (nếu lỗi)
  [Lô 4..10] -----------> Chưa chạy (nếu job dừng)
~~~

Nếu lỗi xảy ra tại lô thứ ba, hai lô đã commit **vẫn tồn tại**; Neo4j không rollback toàn bộ job nhập. Vì vậy, **toàn bộ công việc import không còn là một giao dịch nguyên tử**. Đó là đánh đổi có chủ đích để hạn chế thời gian giữ tài nguyên và dễ thử lại phần chưa hoàn thành.

| Phương án | Lợi ích | Rủi ro/giới hạn |
|---|---|---|
| Một giao dịch cho toàn bộ dữ liệu | Tất cả hoặc không có gì | Có thể tốn bộ nhớ/khóa lớn; lỗi cuối job làm mất công sức toàn bộ |
| Nhiều giao dịch nhỏ | Giới hạn tác động khi lỗi, có thể theo dõi commit | Tốn overhead tạo/commit nhiều transaction; cần chiến lược tiếp tục |
| Nhiều giao dịch lớn | Ít overhead commit hơn | Mỗi lỗi rollback nhiều hàng, tăng bộ nhớ và thời gian giữ khóa |

Không có kích thước lô tối ưu cho mọi bộ dữ liệu. Nó phụ thuộc kích thước mỗi hàng, số relationship tạo ra, độ phức tạp của `MERGE`, chỉ mục, tốc độ lưu trữ, bộ nhớ và mức độ ghi đồng thời.

## 3. Chuẩn bị nguồn dữ liệu và khóa định danh

Giả sử cần nhập khách hàng và đơn hàng. Hai tệp CSV mẫu:

**`customers.csv`**

~~~csv
customerId,name,region
C001,An,Ha Noi
C002,Binh,Ho Chi Minh
C003,Chi,Da Nang
~~~

**`orders.csv`**

~~~csv
orderId,customerId,totalAmount
O001,C001,150000
O002,C001,90000
O003,C003,350000
~~~

Đồ thị mong đợi:

~~~text
(C001:Customer {name:'An'})  --[:PLACED]--> (O001:Order {totalAmount:150000})
                             \-[:PLACED]--> (O002:Order {totalAmount:90000})
(C002:Customer {name:'Binh'})
(C003:Customer {name:'Chi'}) --[:PLACED]--> (O003:Order {totalAmount:350000})
~~~

Để `MERGE` tìm đúng node khi chạy lại và tránh tạo nhiều node cùng khóa, tạo constraint **trước** khi import trên database thực hành:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

**Vì sao cần constraint?** `MERGE (c:Customer {customerId: ...})` tìm mẫu đã có hoặc tạo mới. Uniqueness constraint bảo vệ quy tắc duy nhất theo `customerId` và hỗ trợ tra cứu bằng index tương ứng. Không có constraint, các bản ghi trùng hoặc hai luồng ghi cạnh tranh có thể gây dữ liệu không mong muốn; `MERGE` không thay thế toàn bộ kiểm soát tính duy nhất, đặc biệt khi đã có dữ liệu trùng trước đó.

### Tệp CSV được Neo4j đọc ở đâu?

Ví dụ dùng `file:///customers.csv` hoặc `file:///orders.csv`. Đây là đường dẫn nhìn từ **máy chủ Neo4j**, thông thường nằm trong thư mục import được cấu hình, **không mặc nhiên là thư mục trên máy chạy Neo4j Browser hoặc Java client**. Trong Docker, tệp phải được mount đúng vào môi trường container. Các dịch vụ cloud có thể yêu cầu nguồn HTTPS hoặc cơ chế tải dữ liệu khác thay vì truy cập file cục bộ.

`LOAD CSV WITH HEADERS` dùng dòng đầu làm tên thuộc tính của biến `row`; các trường CSV đọc ra ban đầu là **chuỗi hoặc null**. Cần tự chuyển đổi các giá trị số và ngày giờ thay vì trông đợi Neo4j suy đoán kiểu.

## 4. Nhập node theo lô bằng `LOAD CSV` và `CALL ... IN TRANSACTIONS`

Với Neo4j **5.23+**, câu lệnh dưới đây lấy từng dòng từ CSV, chỉ giữ khách hàng có khóa hợp lệ rồi xử lý các dòng qua nhiều transaction:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row,
     trim(coalesce(row.customerId, '')) AS customerId
WHERE customerId <> ''
CALL (row, customerId) {
    MERGE (c:Customer {customerId: customerId})
    SET c.name = row.name,
        c.region = row.region
} IN TRANSACTIONS OF 1000 ROWS;
~~~

`CALL (row, customerId)` đưa biến từ truy vấn ngoài vào subquery. `IN TRANSACTIONS OF 1000 ROWS` chia các hàng **đi tới lời gọi subquery** thành các nhóm tối đa 1.000 hàng và xử lý từng nhóm trong một giao dịch riêng. Nếu chỉ có 3 hàng mẫu, job hoàn thành trong một transaction; khi nguồn chứa 10.000 hàng hợp lệ, thông thường có 10 nhóm 1.000 hàng.

**Quan trọng:** `CALL { ... } IN TRANSACTIONS` phải chạy trong **implicit transaction (auto-commit)**. Không đặt câu lệnh này trong `BEGIN ... COMMIT`, explicit transaction hoặc callback `session.executeWrite(...)` của Java Driver. Trong Neo4j Browser, có thể cần chạy bằng tiền tố `:auto` (ví dụ `:auto LOAD CSV ...`); trong Java Driver, dùng truy vấn auto-commit với `session.run(...)`. Nếu công cụ đang tự bao mọi truy vấn trong explicit transaction, phải điều chỉnh cơ chế thực thi.

Với Neo4j 5 trước 5.23 (khi phiên bản hỗ trợ `CALL { ... } IN TRANSACTIONS` nhưng chưa hỗ trợ scope clause `CALL (row)`), dùng cách nhập biến cũ:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row,
     trim(coalesce(row.customerId, '')) AS customerId
WHERE customerId <> ''
CALL {
    WITH row, customerId
    MERGE (c:Customer {customerId: customerId})
    SET c.name = row.name,
        c.region = row.region
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Phân biệt hai vấn đề:** `1000 ROWS` quyết định ranh giới commit; `MERGE` quyết định cách mỗi node được tìm/tạo để hỗ trợ chạy lại. Thay `MERGE` bằng `CREATE` có thể nhanh hơn trong một số trường hợp, nhưng chạy lại có thể tạo node trùng và xung đột constraint. Chỉ dùng `CREATE` khi dữ liệu và chiến lược nhập bảo đảm phù hợp.

### Kết quả sau khi nhập tệp mẫu

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IN ['C001', 'C002', 'C003']
RETURN c.customerId AS customerId,
       c.name AS name,
       c.region AS region
ORDER BY customerId;
~~~

Trên database thử nghiệm trống trước khi nhập, kết quả là ba khách hàng `C001`, `C002`, `C003`. Nếu nguồn CSV có dòng trùng khóa, số dòng được xử lý có thể **lớn hơn** số node tồn tại sau nhập, vì `MERGE` có thể cập nhật node hiện hữu.

## 5. Nhập relationship: chia quy trình thành các giai đoạn rõ ràng

Khi dữ liệu biểu diễn quan hệ, nên xác định node đầu/cuối trước. Ví dụ, chỉ nhập đơn hàng khi khách hàng tham chiếu đã tồn tại. Trước tiên xem có khóa khách hàng không hợp lệ trong CSV:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
WITH row,
     trim(coalesce(row.customerId, '')) AS customerId
WHERE customerId <> ''
OPTIONAL MATCH (c:Customer {customerId: customerId})
WITH row, c
WHERE c IS NULL
RETURN row.orderId AS orderId,
       row.customerId AS missingCustomerId
LIMIT 20;
~~~

Truy vấn chỉ phát hiện **một phần** lỗi tham chiếu (những dòng có `customerId` khác rỗng nhưng không có node tương ứng). Cần kiểm tra riêng khóa rỗng, trùng mã và giá trị tiền không hợp lệ.

Khi dữ liệu đã được xác thực, import đơn hàng và relationship:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
WITH row,
     trim(coalesce(row.orderId, '')) AS orderId,
     trim(coalesce(row.customerId, '')) AS customerId,
     toIntegerOrNull(row.totalAmount) AS totalAmount
WHERE orderId <> ''
  AND customerId <> ''
  AND totalAmount IS NOT NULL
  AND totalAmount >= 0
CALL (orderId, customerId, totalAmount) {
    MATCH (c:Customer {customerId: customerId})
    MERGE (o:Order {orderId: orderId})
    SET o.totalAmount = totalAmount
    MERGE (c)-[:PLACED]->(o)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Trật tự import:** import khách hàng trước, rồi import đơn và liên kết. `MATCH (c:Customer ...)` trong subquery sẽ không tìm thấy gì nếu một dòng tham chiếu đến khách hàng chưa có: dòng đó sẽ **không tạo Order và relationship**, và không mặc nhiên phát sinh lỗi. Vì vậy cần **đếm và báo cáo dòng nguồn không hợp lệ trước và sau khi nhập**, thay vì coi câu lệnh hoàn thành là bằng chứng mọi dòng đã được ghi.

Với dữ liệu mẫu hợp lệ, truy vấn kiểm tra:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.orderId IN ['O001', 'O002', 'O003']
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.totalAmount AS totalAmount
ORDER BY orderId;
~~~

Phải có ba cặp liên kết đúng, với tổng tiền `150000 + 90000 + 350000 = 590000`. Nếu cùng một mã đơn hàng xuất hiện với các khách hàng khác nhau trong file, phải xác định quy tắc xử lý xung đột nghiệp vụ trước khi nhập; `MERGE (c)-[:PLACED]->(o)` không tự bảo đảm mỗi Order chỉ có một người sở hữu.

## 6. Theo dõi tiến độ: phân biệt bốn số liệu

Thông báo “đã nhập 10.000 bản ghi” dễ gây nhầm lẫn. Một pipeline dùng `WHERE`, `MERGE` và nhiều transaction cần phân biệt:

| Chỉ số | Ý nghĩa | Có bằng số node mới tạo không? |
|---|---|---|
| **Source rows** | Số dòng có trong nguồn sau header, kể cả dòng sai | Không |
| **Accepted rows** | Số dòng qua kiểm tra hợp lệ và được đưa vào bước nhập | Không |
| **Committed input rows** | Số hàng nguồn thuộc các lô đã commit thành công | Không |
| **Created/updated entities** | Số node/relationship thực sự tạo hoặc cập nhật | Không nhất thiết bằng ba số trên |

Ví dụ, một tệp có 10.000 dòng, 100 dòng không hợp lệ, 200 dòng trùng khóa. Có thể có 9.900 dòng được chấp nhận nhưng **ít hơn 9.900 node mới** nếu `MERGE` khớp node đã tồn tại. Nếu một transaction bị rollback, không thể cộng các dòng của transaction đó vào số **đã commit**.

### 6.1. Quan sát job đang chạy bằng `SHOW TRANSACTIONS`

Trên Neo4j 5, với quyền xem transaction phù hợp, bạn có thể kiểm tra transaction hiện đang hoạt động:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, currentQuery, status, elapsedTime
WHERE currentQuery CONTAINS 'LOAD CSV'
RETURN transactionId, status, elapsedTime, currentQuery;
~~~

Lệnh này giúp nhận biết truy vấn còn chạy, thời gian của transaction và trạng thái được Neo4j công bố. **Nó không phải đồng hồ phần trăm hoàn thành chính xác**: transaction đã commit có thể không còn xuất hiện trong danh sách, còn số dòng CSV được commit qua tất cả lô không được suy ra chỉ bằng thời gian chạy. Cũng không nên suy đoán `elapsedTime` hiển thị là thời gian hoàn thành của toàn bộ job.

### 6.2. Đếm dữ liệu đích để đối chiếu

Sau import, kiểm tra dữ liệu thực tồn tại:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS totalCustomerNodes;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS totalOrderNodes,
       coalesce(sum(o.totalAmount), 0) AS totalOrderAmount;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

Các phép đếm đích có ý nghĩa khi database thực hành chỉ chứa đúng tập cần nhập, hoặc dữ liệu được gắn một `runId`/nhãn/tập khóa riêng để phân biệt với dữ liệu cũ. Trong cơ sở dữ liệu sản xuất, đếm toàn bộ label chưa chắc phản ánh tiến độ của một **lượt import cụ thể**.

### 6.3. Ước lượng tiến độ của `LOAD CSV`

Nếu biết **tổng số dòng hợp lệ** trong một snapshot CSV và ghi nhận được **số dòng đã commit thực sự**, có thể tính:

~~~text
progress_percent = committed_valid_rows / total_valid_rows * 100
~~~

Số dòng trong một tệp nguồn có thể được đếm trước lúc import hoặc tính ở pipeline chuẩn bị dữ liệu. Tuy nhiên, `CALL { ... } IN TRANSACTIONS` **không tự tạo checkpoint nghiệp vụ bền vững cho từng lô**. Nếu cần hiển thị chính xác tiến độ, khả năng tiếp tục theo `batchNo` và nhật ký lỗi, hãy quản lý lô tại tầng ứng dụng như phần tiếp theo.

## 7. Chủ động chia lô và checkpoint bằng Java Driver

Khi ứng dụng Java cần cập nhật tiến độ chính xác, có thể chia tệp thành các lô, gắn `runId` và `batchNo`, sau đó dùng **một managed write transaction cho từng lô**. Trong **cùng transaction**, ghi cả dữ liệu nghiệp vụ và dấu mốc `:ImportBatch`. Nếu transaction rollback, **cả dữ liệu lẫn checkpoint của lô đó đều rollback**.

Thiết kế một node checkpoint:

~~~text
(:ImportBatch {
  batchKey: 'customers-20261125:0',
  runId: 'customers-20261125',
  batchNo: 0,
  state: 'DONE',
  rowsSubmitted: 1000,
  finishedAt: datetime(...)
})
~~~

`batchKey` là khóa duy nhất ổn định, thường ghép `runId` và `batchNo`. Bản ghi `DONE` chỉ được tạo **sau khi các câu lệnh của lô đã chạy thành công và trong cùng transaction với chúng**. Chuẩn bị constraint để tránh các node checkpoint trùng khóa:

~~~cypher
CREATE CONSTRAINT import_batch_key_unique IF NOT EXISTS
FOR (b:ImportBatch)
REQUIRE b.batchKey IS UNIQUE;
~~~

Ví dụ Java Driver 5.x cho một lô khách hàng. Đầu vào `rows` là danh sách map đã được ứng dụng **kiểm tra khóa và chuẩn hóa kiểu dữ liệu**; mã gọi bên ngoài có trách nhiệm đọc CSV theo luồng, nhóm từng tối đa 1.000 dòng hợp lệ và gọi phương thức này cho từng nhóm:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

public final class CustomerBatchImporter {
    private CustomerBatchImporter() {}

    public static void writeBatch(
            Session session,
            String runId,
            long batchNo,
            List<Map<String, Object>> rows) {

        final String batchKey = runId + ":" + batchNo;

        // Một giao dịch cho dữ liệu và checkpoint của cùng lô.
        session.executeWrite(tx -> {
            boolean done = tx.run("""
                    MATCH (b:ImportBatch {batchKey: $batchKey})
                    WHERE b.state = 'DONE'
                    RETURN b.batchKey AS batchKey
                    """, Values.parameters("batchKey", batchKey))
                    .hasNext();

            if (done) {
                return null; // Lô này đã commit ở lần chạy trước.
            }

            tx.run("""
                    UNWIND $rows AS row
                    MERGE (c:Customer {customerId: row.customerId})
                    SET c.name = row.name,
                        c.region = row.region
                    """, Values.parameters("rows", rows)).consume();

            tx.run("""
                    MERGE (b:ImportBatch {batchKey: $batchKey})
                    SET b.runId = $runId,
                        b.batchNo = $batchNo,
                        b.state = 'DONE',
                        b.rowsSubmitted = $rowsSubmitted,
                        b.finishedAt = datetime()
                    """, Values.parameters(
                        "batchKey", batchKey,
                        "runId", runId,
                        "batchNo", batchNo,
                        "rowsSubmitted", rows.size())).consume();

            return null;
        });
    }
}
~~~

**Ý nghĩa quan trọng của mã:**

1. `session.executeWrite(...)` tạo một managed transaction, có cơ chế retry khi gặp một số lỗi tạm thời theo cấu hình driver. Toàn bộ công việc trong callback phải an toàn khi **chạy lại**, không gửi email, ghi file bên ngoài hoặc cộng bộ đếm ngoài DB ngay trong callback.
2. `UNWIND $rows` biến một danh sách tham số thành nhiều hàng trong **một** transaction. Đây là kiểu nhập theo lô do **Java Driver** quản lý, khác với `CALL ... IN TRANSACTIONS` do **Cypher engine** chia transaction.
3. `MERGE` theo `customerId` và uniqueness constraint giúp chạy lại không sinh node trùng khi cùng dữ liệu và cùng khóa. Nếu dòng nguồn trùng khóa nhưng thông tin khác nhau, vẫn phải xác định quy tắc cập nhật.
4. Marker `ImportBatch` được ghi **cùng transaction**. Nếu lô thất bại trước commit, không xuất hiện marker `DONE` mới; nếu ứng dụng mất kết nối ngay sau commit và không biết kết quả, lần chạy lại có thể nhận ra marker đã tồn tại.
5. `rowsSubmitted` chỉ đếm **dòng ứng dụng chuyển vào lô**. Nó không phải số node mới tạo. Ví dụ này giả định tầng ứng dụng đã kiểm tra dữ liệu trước khi gọi; nếu muốn đếm số row được chấp nhận trong Cypher hoặc số node thực tạo, cần thêm cơ chế đo riêng.

Mã minh họa thiết kế cho **một bộ chạy tuần tự**. Không chạy hai worker đồng thời cho cùng `runId`/`batchNo` khi chưa có cơ chế điều phối và khóa phù hợp; đọc marker rồi ghi trong transaction không tự tạo “khóa phân tán” bảo đảm chỉ một worker xử lý. Ngoài ra, một marker `DONE` chỉ đáng tin khi **snapshot nguồn, quy tắc làm sạch và mapping tương ứng với `runId` không đổi**.

### Cách gọi từ pipeline đọc nguồn

Phần đọc CSV có thể dùng thư viện xử lý CSV trong Java (để xử lý đúng dấu phẩy, dấu nháy, encoding). Luồng xử lý ở mức khái niệm:

~~~text
runId cố định + snapshot nguồn cố định
              |
    đọc CSV và chuẩn hóa từng dòng
              |
         gom tối đa 1.000 dòng
              |
    writeBatch(session, runId, batchNo, rows)
              |
    transaction commit thành công?
       /                         \
     có                         không
      |                           |
ghi/đọc checkpoint DONE      ghi lỗi ngoài transaction/
đến batchNo kế tiếp          dừng hoặc retry theo chính sách
~~~

Không cần đọc toàn bộ CSV vào bộ nhớ. Chỉ cần giữ một lô hiện tại và thông tin nguồn bất biến; đó là lợi thế của cách đọc theo luồng. Khi job chạy lại, dùng cùng `runId` và cách chia lô để nhận diện các `batchKey` đã hoàn thành.

## 8. Truy vấn tiến độ từ các checkpoint đã commit

Với các lô do Java quản lý, truy vấn sau trả số lô đã commit và tổng số hàng đầu vào mà các lô đó đã nhận:

~~~cypher
MATCH (b:ImportBatch {runId: $runId})
WHERE b.state = 'DONE'
RETURN count(b) AS committedBatches,
       coalesce(sum(b.rowsSubmitted), 0) AS committedInputRows,
       max(b.finishedAt) AS latestCommittedAt;
~~~

Giả sử snapshot nguồn có **10.000 dòng hợp lệ** và được chia thành đúng 10 lô, mỗi lô 1.000 dòng. Nếu query trả `committedBatches = 7` và `committedInputRows = 7000`, tiến độ **commit theo hàng đầu vào** là `7000 / 10000 = 70%`. Đây là dữ liệu minh họa về trạng thái sau 7 lô, không phải số đo hệ thống thực.

Trong một bảng điều khiển, có thể trình bày:

| Trường | Ví dụ | Cần hiểu đúng |
|---|---:|---|
| Total accepted rows | 10.000 | Lấy từ snapshot đã kiểm tra |
| Committed input rows | 7.000 | Tổng `rowsSubmitted` của marker `DONE` |
| Committed batches | 7/10 | Số lô đã commit trên tổng số lô xác định |
| Progress | 70% | Tiến độ commit theo hàng nguồn |
| Created customers | *Đo riêng* | Không suy ra từ 7.000 nếu `MERGE` cập nhật node cũ |
| Failed batch | *Theo báo cáo ứng dụng* | Transaction rollback sẽ không tự sinh marker `DONE` |

Nếu lô cuối có ít hơn 1.000 dòng, không dùng công thức `committedBatches / totalBatches` để suy ra chính xác số dòng đã hoàn thành; hãy cộng `rowsSubmitted` của các lô thực tế.

### Phân biệt tiến độ và trạng thái nguồn

Checkpoint `DONE` không chứng minh bản ghi nguồn chưa bị thay đổi sau lần import. Một chiến lược vững chắc thường gắn run với **tên/phiên bản snapshot**, **checksum tệp**, **tổng số dòng hợp lệ** và **phiên bản quy tắc chuyển đổi**. Nếu nguồn khác, hãy tạo `runId` mới hoặc có kế hoạch cập nhật rõ ràng, thay vì dùng lại các marker của dữ liệu cũ.

## 9. Xử lý lỗi, rollback và tiếp tục import

| Tình huống | Điều có thể xảy ra | Cách xử lý |
|---|---|---|
| CSV thiếu khóa `customerId` | `MERGE` không thể định danh node đúng | Kiểm tra và cách ly dòng lỗi trước khi đưa vào lô |
| Giá trị tiền không phải số | `toIntegerOrNull` trả `null`, dòng có thể bị lọc | Đếm và lưu báo cáo dòng bị loại, không coi là nhập thành công |
| Một lô bị lỗi constraint | Transaction của lô rollback | Sửa dữ liệu/logic, chạy lại lô; các lô đã commit được giữ |
| Mất mạng sau khi server commit | Ứng dụng có thể không rõ lô đã hoàn tất | Tra checkpoint trong DB, rồi quyết định bỏ qua/chạy lại |
| Job dừng ở lô thứ k | Các lô trước đã commit | Đọc marker `DONE`, tiếp tục từ lô còn thiếu với cùng snapshot |
| Dòng trùng khóa với dữ liệu đã có | `MERGE` có thể khớp và cập nhật node cũ | Chọn chính sách cập nhật, bảo vệ dữ liệu bằng constraint |
| Nhiều luồng chạy cùng batch | Có thể tranh chấp khóa/ghi trùng | Chỉ có một chủ sở hữu batch hoặc áp dụng phối hợp có khóa |

**Với `CALL { ... } IN TRANSACTIONS`**, nếu job gặp lỗi giữa chừng, các lô trước đã commit có thể vẫn tồn tại. Tùy phiên bản Neo4j, cú pháp xử lý lỗi và báo trạng thái transaction có thể khác nhau. Không mặc nhiên giả định toàn bộ nguồn được rollback, hoặc những lô sau lỗi đã được xử lý. Hãy kiểm chứng dữ liệu đích và chạy lại với phép ghi có tính idempotent, hoặc dùng checkpoint tầng ứng dụng như phần 7 khi cần phục hồi đến từng lô chính xác.

**Idempotent** ở đây nghĩa là chạy lại cùng lô với cùng dữ liệu không làm tăng số node/relationship ngoài ý muốn. Dùng `MERGE` theo khóa ổn định và `MERGE` relationship phù hợp là một phần của giải pháp, nhưng chưa đủ nếu các phép cập nhật dùng `SET x = x + 1`, `CREATE` thiếu bảo vệ, dữ liệu nguồn đổi, hoặc một khóa nghiệp vụ ánh xạ nhiều node.

## 10. Chọn kích thước lô và tối ưu hiệu năng

Các giá trị như **100**, **500**, **1.000**, **5.000** hàng/lô là các cấu hình **để thử nghiệm**, không phải ngưỡng tối ưu được Neo4j bảo đảm. Bắt đầu từ mức vừa phải (ví dụ 1.000 hàng/lô), sau đó đo:

- **Số lô và số transaction commit:** quá nhiều lô rất nhỏ tạo overhead.
- **Thời gian mỗi lô và tốc độ hàng/giây:** đo trên dữ liệu đại diện, bỏ qua kết luận từ một lô đầu tiên.
- **Bộ nhớ/transaction và thời gian giữ khóa:** lô lớn hoặc tạo nhiều relationship có thể tiêu tốn nhiều tài nguyên.
- **Tỉ lệ rollback/retry:** lô lớn khiến mỗi lần lỗi phải làm lại nhiều hàng.
- **Tác động lên workload khác:** chỉ chạy song song khi đã kiểm tra lock contention, tài nguyên và mức tải ghi.

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng điều chỉnh |
|---|---|---|
| Nhiều lô, overhead commit lớn | Batch quá nhỏ | Thử tăng lô có kiểm soát |
| Memory hoặc thời gian transaction tăng mạnh | Batch quá lớn, mỗi hàng tạo nhiều node/edge | Giảm batch, đơn giản hóa thao tác từng hàng |
| `MERGE` chậm trên nhiều dữ liệu | Thiếu index/constraint trên khóa tìm | Tạo constraint/index phù hợp trước import |
| Lỗi một lần phải chạy lại nhiều dữ liệu | Batch lớn hoặc nguồn chưa được kiểm tra | Giảm lô, validate sớm |
| Các lô tranh chấp cùng node | Nhiều writer cập nhật khóa chung | Giảm độ song song, chia nguồn theo khóa |

Một batch 1.000 dòng khách hàng đơn giản và 1.000 dòng tạo nhiều quan hệ qua các pattern match phức tạp có chi phí rất khác nhau. Không nên tối ưu chỉ dựa trên `ROWS` mà bỏ qua lượng công việc trong mỗi hàng.

### Index/constraint trước hay sau khi nhập?

Với lệnh `MERGE` theo mã định danh, **uniqueness constraint** hoặc index thích hợp giúp tìm nhanh node đã có và bảo đảm nhất quán định danh. Nếu chỉ dùng `CREATE` cho một lần nạp dữ liệu mới, một số chiến lược có thể xây index sau khi import để giảm overhead ghi. Đây là quyết định về **khả năng đúng và chi phí tổng thể**, không phải mẹo “luôn bỏ index cho nhanh”.

Đối với nạp rất lớn vào database mới, cũng cần đánh giá công cụ **`neo4j-admin database import`** theo quy trình offline được phiên bản hỗ trợ. Công cụ này phục vụ kịch bản khác với online import vào database đang hoạt động, và không sử dụng cùng cơ chế checkpoint Cypher ở ví dụ này.

## 11. Kiểm thử tính đúng đắn sau khi import

Với database thực hành chỉ có ba khách hàng và ba đơn hàng mẫu, kiểm tra số lượng:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customers;  // 3 nếu chỉ có dữ liệu mẫu
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orders,
       coalesce(sum(o.totalAmount), 0) AS totalAmount;
// orders = 3, totalAmount = 590000 nếu chỉ có dữ liệu mẫu
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
// 3 nếu chỉ có dữ liệu mẫu
~~~

Kiểm tra thiếu liên kết:

~~~cypher
MATCH (o:Order)
WHERE NOT EXISTS {
    MATCH (:Customer)-[:PLACED]->(o)
}
RETURN o.orderId AS orderWithoutCustomer
LIMIT 20;
~~~

Với dữ liệu mẫu hợp lệ, kết quả phải rỗng. Với dữ liệu thật, cần so thêm các bản ghi lỗi đã cách ly, tổng tiền/định danh từ nguồn, số dòng trùng khóa và những node được cập nhật. Nếu import được thiết kế để chỉ thêm mới một phần dữ liệu, không dùng tổng số node toàn database làm tiêu chí duy nhất.

### Thử lại để kiểm tra tính idempotent

Trên database thực hành:

1. Lấy số khách hàng, đơn hàng và relationship hiện có.
2. Chạy lại cùng dữ liệu bằng các lệnh `MERGE` trong mục 4–5.
3. Đếm lại: số node và quan hệ **không tăng** nếu các khóa và quan hệ không thay đổi.
4. Thay đổi thử một `name` trong nguồn (trên bản sao) để xem chính sách `SET` cập nhật thế nào; không gọi đó là cùng snapshot nữa.

## 12. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách đúng |
|---|---|---|
| Chạy `CALL ... IN TRANSACTIONS` bên trong explicit transaction | Có thể bị từ chối vì yêu cầu implicit transaction | Dùng auto-commit; nếu muốn tự điều khiển transaction, dùng `UNWIND $rows` và Java Driver |
| Đọc `file:///...` từ máy client | Không tìm thấy tệp trên máy chủ Neo4j | Đặt/mount tệp vào nguồn server được phép, hoặc dùng URL hỗ trợ |
| Không tạo khóa duy nhất rồi dùng `MERGE` trên dữ liệu lớn | Chậm và dễ khó kiểm soát dữ liệu trùng | Thiết kế khóa, constraint/index phù hợp |
| Dùng `CREATE` rồi chạy lại job sau lỗi | Sinh node/relationship trùng | Dùng thao tác idempotent hoặc chỉ tiếp tục các batch chưa commit |
| Lấy số dòng CSV làm số node mới | Sai vì lọc dòng và `MERGE` có thể cập nhật | Theo dõi riêng source, accepted, committed và created |
| Đếm toàn bộ label làm tiến độ của một run | Trộn dữ liệu cũ với dữ liệu vừa nhập | Gắn run/snapshot/batch hoặc đối chiếu tập khóa |
| Ghi checkpoint ngoài transaction của dữ liệu | Có thể marker `DONE` nhưng dữ liệu chưa commit, hoặc ngược lại | Ghi checkpoint và dữ liệu trong cùng transaction |
| Dùng lại checkpoint với CSV đã bị sửa | Bỏ qua sai lô hoặc nhập không nhất quán | Gắn run với snapshot/checksum/version |
| Chọn batch cực lớn ngay từ đầu | Tăng rủi ro memory và rollback dài | Thử mức vừa phải, đo rồi điều chỉnh |
| Không kiểm tra quan hệ tham chiếu bị thiếu | Bỏ sót Order hoặc tạo mô hình sai | Validate khóa nguồn và đếm đối chiếu sau import |

## 13. Bài luyện tập

### Bài 1 — Tính số transaction

Một CSV có **12.350 dòng**; sau khi kiểm tra có **350 dòng không hợp lệ**. Truy vấn chỉ đưa dòng hợp lệ vào `CALL ... IN TRANSACTIONS OF 1000 ROWS`. Hỏi sẽ cần bao nhiêu transaction cho các lô dữ liệu?

<details>
<summary>Đáp án gợi ý</summary>

Có `12.350 - 350 = 12.000` dòng hợp lệ. Với 1.000 dòng mỗi lô, có **12 transaction** (nếu không có ảnh hưởng khác tới dòng đầu vào). Đây là số lô thực thi theo hàng nhập, không phải số node mới được tạo.

</details>

### Bài 2 — Phân tích lỗi giữa import

Nguồn có 4.500 dòng hợp lệ, batch size 1.000. Hai lô đầu thành công; lô thứ ba thất bại và job dừng. Nếu không có cơ chế tiếp tục tự động, có thể nói “toàn bộ job đã rollback” không? Cần làm gì trước khi chạy lại?

<details>
<summary>Đáp án gợi ý</summary>

Không. Hai lô đã commit vẫn tồn tại; lô thứ ba rollback và các lô còn lại chưa được xử lý. Cần kiểm tra số dữ liệu đã ghi/checkpoint, sửa nguyên nhân lỗi, xác nhận dữ liệu nguồn chưa đổi, rồi chạy lại bằng `MERGE` an toàn hoặc chỉ tiếp tục các lô chưa commit.

</details>

### Bài 3 — Thiết kế checkpoint

Bạn viết import từ Java Driver với các lô 500 dòng và muốn bảng tiến độ hiển thị được **số hàng nguồn đã commit**. Hãy xác định các trường tối thiểu cần có trong `:ImportBatch` và giải thích tại sao checkpoint phải được ghi trong cùng transaction với node/relationship của lô.

<details>
<summary>Đáp án gợi ý</summary>

Mỗi lô nên có `batchKey` duy nhất, `runId`, `batchNo`, `state` và `rowsSubmitted`; nên lưu thời điểm commit quan sát được, phiên bản/snapshot nguồn ở cấp run. Nếu dữ liệu rollback mà marker `DONE` đã được ghi riêng, pipeline có thể bỏ qua lô chưa nhập; nếu dữ liệu commit mà marker không có, ứng dụng có thể chạy lại. Ghi chúng cùng transaction giúp một đơn vị commit nhất quán và việc chạy lại dễ kiểm chứng hơn.

</details>

### Bài 4 — Chọn chiến lược

Hệ thống nhận cập nhật khách hàng hằng đêm vào database đang chạy, mỗi bản ghi có khóa duy nhất. Bạn chọn `neo4j-admin database import` hay chia lô từ Cypher/Java Driver? Vì sao? Nếu phải nhập 50 triệu node ban đầu vào database mới chưa phục vụ truy vấn, lựa chọn có thay đổi không?

<details>
<summary>Đáp án gợi ý</summary>

Cập nhật hằng đêm vào database đang chạy phù hợp với cơ chế online import theo lô cùng `MERGE` và constraint. Với một lần nạp ban đầu rất lớn vào database mới, nên đánh giá công cụ offline `neo4j-admin database import` theo phiên bản và yêu cầu vận hành. Không có một lựa chọn tối ưu tuyệt đối; cần đánh giá downtime, nguồn dữ liệu, quy tắc cập nhật và kiểm chứng dữ liệu.

</details>

## 14. Ghi nhớ

- **Batch là ranh giới giao dịch:** lỗi ở một lô không tự rollback những lô đã commit trước đó.
- **`CALL { ... } IN TRANSACTIONS OF n ROWS`** tiện để xử lý `LOAD CSV` theo lô trên server, nhưng phải dùng implicit transaction.
- **Java Driver `executeWrite` + `UNWIND $rows`** phù hợp khi ứng dụng muốn tự điều phối từng batch và ghi checkpoint cùng transaction.
- **Tiến độ có nghĩa khi dựa trên commit thực tế** và phân biệt dòng nguồn, dòng hợp lệ, dòng đã commit, node/relationship tạo mới.
- **`MERGE`, khóa ổn định và uniqueness constraint** hỗ trợ chạy lại an toàn; cần kiểm soát thêm dữ liệu trùng, tham chiếu thiếu và phiên bản snapshot.
- **Điều chỉnh batch size bằng phép đo** về thời gian, bộ nhớ, khóa, số lượt retry và tác động lên hệ thống, không chọn một con số cố định cho mọi workload.
