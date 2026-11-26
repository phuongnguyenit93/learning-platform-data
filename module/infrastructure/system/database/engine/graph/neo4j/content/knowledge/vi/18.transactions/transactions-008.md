# Chia lô ghi dữ liệu theo dung lượng và thời gian giao dịch trong Neo4j

## Mục tiêu

Neo4j lưu dữ liệu dưới dạng **property graph**, gồm node, relationship và property. Khi nhập hàng trăm nghìn sản phẩm, đồng bộ hàng triệu quan hệ hoặc cập nhật một mạng đồ thị lớn, việc đưa tất cả thao tác vào **một giao dịch dài** có thể tăng áp lực bộ nhớ, thời gian giữ khóa và chi phí xử lý khi phải rollback. Ngược lại, tạo **một giao dịch cho từng dòng** thường tốn nhiều lần trao đổi với máy chủ.

Trong chương **Giao dịch** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, bài này tập trung vào việc chia tác vụ ghi thành các **lô (batch)** có giới hạn rõ ràng, bao gồm tình huống dùng Cypher, Neo4j Java Driver và ứng dụng Spring Data Neo4j. Sau bài học, bạn có thể:

- Phân biệt kích thước lô tính theo **số dòng**, **dung lượng ước lượng** và **ngân sách thời gian**.
- Hiểu ranh giới commit, rollback và tác động của việc **một số lô đã commit** khi lô sau gặp lỗi.
- Viết câu lệnh `CALL { ... } IN TRANSACTIONS` để chia lô phía Neo4j và chọn cách chia lô phía Java khi cần kiểm soát chi tiết.
- Chọn kích thước lô bằng đo lường, thiết kế ghi **có thể chạy lại**, kiểm soát timeout và lỗi cạnh tranh.

> **Phạm vi:** Các ví dụ sử dụng Neo4j Cypher 5 và Neo4j Java Driver 5.x. Cú pháp `CALL (row) { ... }` dùng *variable scope clause* có từ Neo4j 5.23; ví dụ thay thế cho phiên bản cũ nằm ở mục 4. Khi ứng dụng chạy Cypher 25 hoặc phiên bản khác, cần kiểm tra tài liệu đúng phiên bản.

## 1. Tại sao cần chia lô?

Hãy hình dung hệ thống thương mại lưu:

```text
(:Customer {id})
    └──[:PLACED]──> (:Order {id, placedAt})
                           └──[:CONTAINS]──> (:Product {sku, name, price})
```

Một lần nhập có thể gồm 500.000 sản phẩm, sau đó là nhiều triệu quan hệ `CONTAINS`. Mỗi phép `MERGE` hoặc `SET` có thể cần tra cứu index, đọc/ghi record và ghi vào transaction log. Các thao tác trong **một giao dịch** phải cùng thành công hoặc cùng rollback; nếu giao dịch quá lớn, mọi công việc trong giao dịch ấy có thể phải thực hiện lại khi có lỗi.

Có ba chiến lược thường gặp:

| Chiến lược | Đặc điểm | Hệ quả |
| --- | --- | --- |
| Một giao dịch cho toàn bộ 500.000 dòng | Có thể giữ tính nguyên tử cho toàn bộ lần nhập | Rủi ro tài nguyên/khóa/rollback và thời gian kéo dài |
| Một giao dịch cho từng dòng | Mỗi lần hỏng ảnh hưởng một dòng | Chi phí khởi tạo/commit và lượt gọi qua mạng có thể rất lớn |
| Nhiều giao dịch, mỗi giao dịch vài trăm đến vài nghìn dòng | Cân bằng chi phí cố định với tài nguyên mỗi giao dịch | Phải chấp nhận và quản lý việc commit từng phần |

Sơ đồ luồng ứng dụng:

```text
Nguồn dữ liệu
    ↓ kiểm tra + chuẩn hóa
Hàng đợi/đệm bản ghi
    ↓ đủ số dòng, đủ dung lượng hoặc hết thời gian đệm
Một batch được gửi tới một transaction
    ↓ commit thành công
Ghi nhận tiến độ → nhận batch tiếp theo
    └── nếu lỗi: retry an toàn / lưu lỗi / tiếp tục từ checkpoint
```

**Điểm quyết định:** nếu một batch gồm 500 dòng, **đơn vị commit là 500 dòng đó**. Hoàn tất batch thứ nhất không khiến các batch sau tự động nằm chung một giao dịch. Một lỗi ở batch thứ 8 không tự rollback 7 batch đã commit trước đó.

## 2. Ba giới hạn cần xem xét cùng nhau

### 2.1. Số dòng mỗi batch

Giới hạn đơn giản nhất là `maxRows`. Với `N` dòng đầu vào và `B` dòng/batch:

```text
Số batch = ceil(N / B)
```

Ví dụ `N = 4.800` và `B = 500` tạo **10 batch**: 9 batch có 500 dòng và một batch có 300 dòng. Số dòng giúp dự đoán số lượt commit, nhưng **không phản ánh kích thước thực tế của mỗi bản ghi**. Một node chỉ có `sku` khác xa node có hàng chục property và chuỗi dài.

### 2.2. Dung lượng mỗi batch

Thêm ngưỡng `maxEstimatedBytes` để tránh một lô chứa quá nhiều dữ liệu lớn. Ví dụ minh họa:

| Trường hợp | Số dòng | Kích thước đầu vào ước lượng mỗi dòng | Tổng dung lượng đầu vào |
| --- | ---: | ---: | ---: |
| A: mã + giá | 500 | 1 KiB | Khoảng 500 KiB |
| B: nhiều trường văn bản | 500 | 100 KiB | Khoảng 49 MiB |
| C: nhiều trường văn bản | 2.000 | 100 KiB | Khoảng 195 MiB |

Đây chỉ là **ước lượng dữ liệu truyền vào**, không phải dung lượng transaction thực tế trong Neo4j. Chi phí còn bao gồm entity được chạm tới, index, transaction state, bản ghi log và bộ nhớ của các toán tử truy vấn. Không có một hệ số quy đổi chính xác từ kích thước JSON/CSV sang bộ nhớ transaction.

Có thể áp dụng quy tắc trước khi thêm dòng:

```text
Nếu batch không rỗng và (batchBytes + rowBytes > maxEstimatedBytes):
    gửi và commit batch hiện tại
    bắt đầu batch mới
thêm dòng vào batch
```

Nếu một dòng riêng lẻ lớn hơn giới hạn, cần **tách dữ liệu hợp lệ ở mức nghiệp vụ** hoặc báo lỗi riêng; đừng âm thầm vượt ngưỡng và tưởng rằng hệ thống vẫn an toàn.

### 2.3. Thời gian đệm và thời gian thực thi giao dịch

Có **hai đồng hồ khác nhau**:

1. **Thời gian chờ trong đệm (buffer age):** ứng dụng đã nhận một vài dòng nhưng chưa đủ `maxRows`/`maxEstimatedBytes`. Sau một ngưỡng, ứng dụng gửi lô để giảm độ trễ.
2. **Thời gian transaction:** từ khi bắt đầu xử lý/ghi đến khi hoàn tất commit hoặc rollback. Đây là một phép đo hiệu năng và liên quan đến transaction timeout.

Ví dụ, ứng dụng chọn `maxRows = 500`, `maxEstimatedBytes = 1 MiB`, `maxBufferAge = 2 giây`. Nếu dòng đến chậm, có thể gửi 20 dòng sau 2 giây; nếu mỗi dòng lớn, có thể gửi 30 dòng vì đã gần 1 MiB; nếu dữ liệu nhỏ và đến nhanh, có thể gửi 500 dòng.

**Không nhầm thời gian đệm với transaction timeout.** Timeout có thể hủy một giao dịch chạy quá lâu; nó **không tự động commit phần đã xử lý**. Nếu muốn tự điều chỉnh kích thước batch theo thời gian thực thi, phải đo các giao dịch đã hoàn tất rồi thay đổi **batch tiếp theo**.

## 3. Chuẩn bị bài thực hành

Chỉ chạy ví dụ trong cơ sở dữ liệu thực hành. Ta dùng nhãn `:Product` để tập trung vào việc chia lô, không tạo quá nhiều loại node/relationship cùng lúc.

Tạo ràng buộc khóa nghiệp vụ (chạy riêng **trước** tác vụ nhập):

```cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;
```

Ràng buộc trên giúp tìm theo `sku` qua index thích hợp và ngăn hai node `Product` có cùng `sku`. Đầu vào phải có `sku` hợp lệ; `MERGE` với giá trị khóa `null` sẽ thất bại.

Trước khi nhập, kiểm tra dữ liệu thực tế về khóa trùng, giá trị thiếu, kiểu số và kích thước của các trường. Nếu muốn chạy lại ví dụ và không tạo node trùng, sử dụng `MERGE` trên đúng khóa `sku`.

## 4. Chia batch ngay trong Cypher: CALL ... IN TRANSACTIONS

Neo4j hỗ trợ subquery thực thi theo từng giao dịch với mệnh đề `IN TRANSACTIONS`. Ví dụ tạo hoặc cập nhật 2.500 sản phẩm, mỗi giao dịch nhận 500 dòng:

```cypher
UNWIND range(1, 2500) AS n
CALL (n) {
  MERGE (p:Product {sku: 'SKU-' + toString(n)})
  SET p.name = 'Sản phẩm ' + toString(n),
      p.price = toFloat(n % 1000)
} IN TRANSACTIONS OF 500 ROWS;
```

Các bước diễn ra:

1. `range(1, 2500)` tạo danh sách 2.500 số; `UNWIND` tạo 2.500 dòng.
2. `CALL (n)` đưa giá trị `n` ở từng dòng vào subquery.
3. `IN TRANSACTIONS OF 500 ROWS` tạo **5 giao dịch con**, mỗi giao dịch xử lý tối đa 500 dòng.
4. `MERGE` tìm hoặc tạo node theo `sku`; `SET` cập nhật thuộc tính.

Kiểm chứng số lượng trong cơ sở dữ liệu chỉ có các node do ví dụ tạo:

```cypher
MATCH (p:Product)
WHERE p.sku STARTS WITH 'SKU-'
RETURN count(p) AS productsImported;
```

Với dữ liệu mẫu sạch, kết quả là `2500`. Nếu trước đó đã có những `Product` cùng tiền tố, kết quả đếm là số node thỏa điều kiện trong cơ sở dữ liệu tại thời điểm kiểm tra, không phải số dòng mà lệnh vừa ghi.

### 4.1. Khác biệt phiên bản cú pháp

`CALL (n) { ... }` là cách khai báo biến đầu vào rõ ràng trong **Neo4j 5.23 trở lên**. Ở một số phiên bản Cypher 5 cũ hơn, có thể dùng:

```cypher
UNWIND range(1, 2500) AS n
CALL {
  WITH n
  MERGE (p:Product {sku: 'SKU-' + toString(n)})
  SET p.name = 'Sản phẩm ' + toString(n),
      p.price = toFloat(n % 1000)
} IN TRANSACTIONS OF 500 ROWS;
```

Cú pháp nhập biến bằng `WITH` trong subquery là lối viết cũ và có thể phát sinh cảnh báo deprecated trên Neo4j mới; hãy ưu tiên cú pháp phù hợp phiên bản đang chạy.

### 4.2. Giới hạn quan trọng: implicit transaction

`CALL { ... } IN TRANSACTIONS` cần được thực thi trong một **implicit transaction**. Nếu gửi toàn bộ câu lệnh này vào một **explicit/managed transaction** (ví dụ bên trong callback `session.executeWrite(...)` của Java Driver), Neo4j sẽ từ chối vì cơ chế này tự quản lý các giao dịch con.

- Trong **Neo4j Browser**, một số phiên bản cần tiền tố `:auto` trước truy vấn để chạy ở chế độ auto-commit.
- Trong **Java Driver**, có thể dùng `session.run(cypher, parameters)` để gửi truy vấn implicit transaction; cần tiêu thụ kết quả để bảo đảm quá trình hoàn thành.
- Nếu ứng dụng đã tự tạo một transaction cho từng batch, hãy dùng `UNWIND $rows ... MERGE/SET` bên trong transaction đó, **không** thêm `IN TRANSACTIONS`.

Mỗi batch được commit độc lập. Nếu một batch thất bại sau khi các batch trước đã commit, chỉ các giao dịch chưa commit hoặc giao dịch lỗi bị rollback. Không nên thiết kế logic phụ thuộc vào giả định cả lần nhập là một giao dịch nguyên tử.

### 4.3. Chia lô khi nạp CSV

Giả sử file CSV có header `sku,name,price`, đã được đặt tại vị trí mà cấu hình Neo4j cho phép truy cập bằng đường dẫn `file:///products.csv`:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS csv
WITH csv, toFloat(csv.price) AS parsedPrice
WHERE csv.sku IS NOT NULL
  AND trim(csv.sku) <> ''
  AND parsedPrice IS NOT NULL
CALL (csv, parsedPrice) {
  MERGE (p:Product {sku: csv.sku})
  SET p.name = csv.name,
      p.price = parsedPrice
} IN TRANSACTIONS OF 500 ROWS;
```

Truy vấn này chỉ đưa các dòng đã vượt qua bộ lọc vào subquery, vì vậy **500 ROWS là 500 dòng sau khi lọc**, không nhất thiết là 500 dòng vật lý liên tục của file. Dòng không hợp lệ đang bị bỏ qua; trong hệ thống thật nên đưa chúng vào báo cáo lỗi riêng để tránh mất dữ liệu một cách im lặng.

`LOAD CSV` là phương án thuận tiện cho nguồn CSV được Neo4j truy cập. Việc file nằm ở thư mục import, URL được cho phép, quyền truy cập và thiết lập bảo mật tùy môi trường máy chủ. Một đường dẫn `file:///` không có nghĩa là Neo4j đọc file trên máy của ứng dụng Java từ xa.

### 4.4. Chọn kích thước batch trong Cypher

`IN TRANSACTIONS OF 500 ROWS` kiểm soát theo **số dòng**. Nó không tự đo số byte và không có nghĩa “commit cứ mỗi 2 giây”. Nếu dữ liệu khác nhau nhiều về dung lượng hoặc cần chính sách thời gian chi tiết, thường dễ kiểm soát hơn bằng **batch do ứng dụng tạo**.

## 5. Chia lô ở Java Driver: số dòng + dung lượng + thời gian

Trong ứng dụng Java hoặc Spring Data Neo4j, cách rõ ràng là tạo danh sách đầu vào cho từng batch, rồi **mỗi batch gọi một managed transaction**. Java Driver có `Session.executeWrite(...)`, callback có thể được chạy lại khi xảy ra lỗi thuộc loại có thể retry. Vì vậy, câu lệnh ghi nên có khả năng chạy lại an toàn.

Ví dụ Java 17 trở lên, Neo4j Java Driver 5.x; giả sử `Driver` đã được khởi tạo và quản lý vòng đời ở tầng ứng dụng:

```java
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

public final class ProductBatchWriter {
    public record ProductInput(String sku, String name, double price) {}

    private static final int MAX_ROWS = 500;
    private static final long MAX_BYTES = 1L * 1024 * 1024;
    private static final long MAX_BUFFER_AGE_NANOS =
        Duration.ofSeconds(2).toNanos();

    private static final String UPSERT = """
        UNWIND $rows AS row
        MERGE (p:Product {sku: row.sku})
        SET p.name = row.name,
            p.price = row.price
        """;

    public static void importAll(
        Driver driver, Iterable<ProductInput> source
    ) {
        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            List<Map<String, Object>> batch = new ArrayList<>();
            long bufferedBytes = 0;
            long firstRowAt = 0;

            for (ProductInput item : source) {
                if (item.sku() == null || item.sku().isBlank()
                    || item.name() == null
                    || !Double.isFinite(item.price())) {
                    throw new IllegalArgumentException("Invalid product");
                }

                // Kích thước ước lượng, không phải số byte Bolt thực tế.
                long rowBytes =
                    item.sku().getBytes(StandardCharsets.UTF_8).length
                    + item.name().getBytes(StandardCharsets.UTF_8).length
                    + Double.BYTES + 64L;
                if (rowBytes > MAX_BYTES) {
                    throw new IllegalArgumentException("Oversized row");
                }

                long now = System.nanoTime();
                if (!batch.isEmpty() &&
                    (bufferedBytes + rowBytes > MAX_BYTES
                     || now - firstRowAt >= MAX_BUFFER_AGE_NANOS)) {
                    writeBatch(session, batch);
                    batch.clear();
                    bufferedBytes = 0;
                }

                if (batch.isEmpty()) {
                    firstRowAt = System.nanoTime();
                }
                batch.add(Map.of(
                    "sku", item.sku(),
                    "name", item.name(),
                    "price", item.price()
                ));
                bufferedBytes += rowBytes;

                if (batch.size() >= MAX_ROWS
                    || bufferedBytes >= MAX_BYTES) {
                    writeBatch(session, batch);
                    batch.clear();
                    bufferedBytes = 0;
                }
            }

            if (!batch.isEmpty()) {
                writeBatch(session, batch); // Batch cuối chưa đầy.
            }
        }
    }

    private static void writeBatch(
        Session session, List<Map<String, Object>> buffered
    ) {
        // Sao chép trước callback: dữ liệu mỗi lần retry phải cố định.
        List<Map<String, Object>> rows = List.copyOf(buffered);
        TransactionConfig config = TransactionConfig.builder()
            .withTimeout(Duration.ofSeconds(15))
            .build();

        session.executeWrite(tx -> {
            tx.run(UPSERT, Map.of("rows", rows)).consume();
            return null;
        }, config);
    }
}
```

Đặc điểm của ví dụ:

- `MAX_ROWS` giới hạn số bản ghi; `MAX_BYTES` giới hạn **ước lượng dung lượng đầu vào**; `MAX_BUFFER_AGE_NANOS` giới hạn thời gian đệm **khi có bản ghi tiếp theo được nhận**.
- `executeWrite` tạo một giao dịch quản lý bởi driver cho **mỗi batch**; `consume()` buộc thực thi truy vấn trước khi callback kết thúc.
- `withTimeout(15 giây)` đặt timeout cho **thời gian transaction**, không phải lệnh yêu cầu Neo4j commit sau 15 giây. Nếu timeout xảy ra, lô đó phải được xem là chưa xác nhận thành công.
- `List.copyOf(buffered)` giữ danh sách tham số cố định cho các lần driver retry callback. `Map.of(...)` cũng tạo map không sửa được.
- Nếu nguồn tạm ngừng cung cấp dòng, vòng lặp không có sự kiện mới để đánh giá `MAX_BUFFER_AGE_NANOS`. Muốn **flush đúng giờ kể cả khi không có dòng mới**, cần hàng đợi và scheduler/consumer có cơ chế đánh thức theo thời gian.
- Ước lượng byte trong code tính chuỗi UTF-8, số và một khoản overhead giả định; nó **không thay thế** phép đo memory/latency thực tế trong Neo4j.

Đây là mã ví dụ xử lý đồng bộ. Hệ thống sản xuất cần thêm log batch, xử lý checkpoint, giám sát và cơ chế báo lỗi nhập dữ liệu. Đặt phương pháp `writeBatch` trong lớp dịch vụ nghiệp vụ tương ứng khi tích hợp với Spring Data Neo4j; đừng đặt vòng lặp nhiều batch bên trong một phương thức được bọc bằng **một** `@Transactional` chung nếu mục tiêu là commit từng batch độc lập.

## 6. Thời gian giao dịch: đo và điều chỉnh lô

Nếu batch 500 dòng thường xử lý trong 200 ms nhưng có lúc cần 20 giây, một kích thước cố định có thể không phù hợp. Thay vì đoán một con số “tốt nhất” cho mọi hệ thống, thực hiện chạy thử trên dữ liệu đại diện.

### 6.1. Những chỉ số nên thu thập

| Chỉ số | Cách dùng |
| --- | --- |
| `rows/batch` và `estimatedBytes/batch` | Biết cấu hình và sự khác biệt giữa các bản ghi |
| `transactionDurationMs`, p50/p95/p99 | Phát hiện batch chậm không đều hoặc vượt mục tiêu |
| `rowsCommitted/s` | Đo throughput có ý nghĩa nghiệp vụ |
| Số batch lỗi, retry và timeout | Nhận biết kích thước quá lớn, xung đột hoặc sự cố |
| Bộ nhớ, GC, CPU, disk I/O, transaction log | Tìm nút thắt tài nguyên |
| Số lần chờ khóa, deadlock, số transaction đồng thời | Xác định tranh chấp khi ghi song song |

Trong một lần thử, thay đổi **một biến tại một thời điểm**. Chẳng hạn, giữ cùng dữ liệu, index và mức đồng thời; đo `B = 100, 500, 1.000, 2.000` dòng. So sánh throughput và p95 thời gian mỗi batch. Nếu batch lớn không tăng throughput nhưng làm tăng timeout hoặc sử dụng bộ nhớ, hãy giảm ngưỡng.

### 6.2. Ngân sách thời gian cho một batch

Giả sử mục tiêu vận hành mong muốn mỗi transaction hoàn thành trong **khoảng 1 giây**, và timeout cấu hình là 15 giây. Có thể điều chỉnh lô **sau khi quan sát một số giao dịch đã commit**:

```text
Nếu p95 thời gian giao dịch > mục tiêu:
    giảm maxRows hoặc maxEstimatedBytes cho các batch sắp tới
Nếu p95 thấp, không có retry/timeout và tài nguyên còn dư:
    thử tăng từ từ kích thước batch, luôn có trần
Nếu xuất hiện lỗi/timeout:
    không coi batch là đã commit; xác minh hoặc retry an toàn
```

Đây là **chính sách điều chỉnh ở ứng dụng**, không phải tính năng tự động của `IN TRANSACTIONS`. Trong thực tế, transaction time còn phụ thuộc index, số relationship phải mở rộng, lượng dữ liệu ghi và cạnh tranh khóa. Timeout là **hàng rào chặn giao dịch bất thường**, không phải công cụ đảm bảo thời gian commit đúng đến mili giây.

## 7. Nhất quán, retry và khả năng phục hồi

### 7.1. Batch độc lập không tạo một “siêu giao dịch”

Giả sử có bốn batch, mỗi batch 500 dòng:

| Batch | Kết quả | Trạng thái |
| --- | --- | --- |
| 1 | Commit thành công | 500 dòng đã được ghi |
| 2 | Commit thành công | Thêm 500 dòng đã được ghi |
| 3 | Lỗi kiểu dữ liệu, rollback | Không nhận batch 3 là đã ghi |
| 4 | Chưa chạy | Chưa ghi |

Đến đây **1.000 dòng đầu đã commit**. Nếu nghiệp vụ đòi hỏi tất cả 2.000 dòng phải cùng thành công hoặc cùng thất bại, phải xem lại thiết kế: không thể chỉ thêm `IN TRANSACTIONS` mà vẫn có tính nguyên tử trên toàn bộ lần nhập.

### 7.2. Idempotency: chạy lại một batch mà không nhân đôi dữ liệu

Nên dùng khóa nghiệp vụ bền vững:

```cypher
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.price = row.price;
```

Khi cùng `sku` được gửi lại, `MERGE` có thể tìm node cũ và `SET` cập nhật giá trị. Ràng buộc duy nhất trên `:Product(sku)` bảo vệ tránh nhiều node trùng khóa khi có ghi đồng thời.

Ngược lại:

```cypher
UNWIND $rows AS row
CREATE (p:Product {sku: row.sku, name: row.name});
```

`CREATE` luôn cố tạo node mới; với unique constraint sẽ gặp lỗi khi trùng `sku`, còn không có constraint thì dễ sinh bản ghi trùng khi retry. Tương tự, `CREATE (a)-[:BOUGHT]->(b)` có thể tạo nhiều relationship trùng nghĩa; hãy thiết kế khóa/quan hệ tương ứng và dùng `MERGE` khi thực sự muốn tái sử dụng mẫu.

**Không coi mọi cập nhật là idempotent.** Chẳng hạn `SET p.stock = p.stock + row.delta` có thể cộng kho **hai lần** nếu retry lại cùng sự kiện. Với phép cộng/trừ có ý nghĩa kinh doanh, cần mã giao dịch/sự kiện duy nhất và cơ chế chống xử lý trùng thích hợp.

### 7.3. Checkpoint và batch lỗi

Một quy trình nhập có thể lưu:

```text
jobId
sourceVersion
lastCommittedCursor (hoặc mã sự kiện cuối đã xác nhận)
totalRowsCommitted
lastError
```

Chỉ cập nhật checkpoint sau khi **batch đã được xác nhận commit thành công**. Khi phát lại, dùng khóa nghiệp vụ và thao tác idempotent để an toàn cả trong trường hợp commit đã thành công nhưng ứng dụng mất kết nối trước khi nhận phản hồi. Nếu checkpoint nằm ngoài Neo4j, cập nhật checkpoint và commit không tự trở thành một giao dịch phân tán; thiết kế chạy lại phải chịu được khoảng trống đó.

Nếu nguồn thay đổi theo thời gian, con trỏ phải gắn với một phiên bản dữ liệu hoặc thứ tự ổn định. Không nên dùng “đã đọc 500 dòng” như bằng chứng chắc chắn rằng 500 dòng ấy đã được commit.

### 7.4. Retry và lỗi cạnh tranh

`executeWrite` có thể tự retry **lỗi tạm thời** theo chính sách driver. Callback có thể chạy nhiều lần, vì thế không nên gửi email, trừ tiền qua dịch vụ ngoài hoặc tăng bộ đếm ngoài Neo4j bên trong callback. Chỉ đặt các thao tác ghi database phù hợp và có thể chạy lại trong callback; side effect khác cần cơ chế phối hợp riêng.

Khi có nhiều writer, thử nghiệm trước với **mức đồng thời thấp**. Cập nhật cùng node/relationship có thể gây chờ khóa, deadlock hoặc tăng thời gian giao dịch. Gói nhiều dòng trong một batch thường giúp giảm số commit nhưng cũng có thể tăng thời gian giữ khóa. Việc tăng số luồng không luôn cải thiện throughput.

## 8. Tác động tới Java Driver, Spring Data Neo4j và vận hành

### 8.1. Java Driver

- Dùng **một query với `UNWIND $rows` trên mỗi batch** thường giảm số lần gọi qua mạng so với gọi query riêng cho từng dòng.
- Tạo `Session` theo phạm vi công việc hợp lý và đóng khi hoàn tất; các session không dùng chung giữa những luồng không được thiết kế để chia sẻ nó.
- Dùng `executeWrite` cho transaction do ứng dụng quản lý; dùng `session.run` nếu thực sự cần truy vấn phía server với `IN TRANSACTIONS`.
- Truyền tham số thay vì nối chuỗi Cypher; kiểm tra `sku`, giá trị số và những property có thể bằng `null` trước khi ghi.

### 8.2. Spring Data Neo4j

Một phương thức `@Transactional` thường bao bọc các lệnh ghi bên trong nó vào **một transaction**, dù trong Java có vòng lặp 500 dòng. Muốn commit theo từng lô, ranh giới transaction phải nằm ở **từng lô**, ví dụ gọi qua service/`TransactionTemplate` với mỗi batch là một transaction độc lập phù hợp cấu hình transaction manager.

Chú ý cơ chế **self-invocation** của proxy trong Spring: gọi một phương thức `@Transactional` khác **ngay trong cùng đối tượng** có thể không đi qua proxy, làm ranh giới giao dịch không như dự kiến. Đồng thời cần cân nhắc lỗi ghi giữa các batch và cách resume. Đừng mặc định phân trang repository hoặc `saveAll(...)` tự tạo đúng số batch theo byte/thời gian mà nghiệp vụ mong muốn.

### 8.3. Neo4j vận hành

- Tạo index/constraint cho các khóa dùng trong `MERGE` **trước khi** nhập khối lượng lớn; kiểm tra `EXPLAIN` và `PROFILE` trên dữ liệu thử nghiệm để thấy kế hoạch truy vấn và số dòng trung gian.
- Theo dõi bộ nhớ transaction, áp lực GC, I/O, transaction log và thời gian chờ khóa. Đừng dùng kích thước file CSV để dự đoán duy nhất mức bộ nhớ.
- Khi cần nhập rất lớn, hãy đánh giá `LOAD CSV` và `CALL { ... } IN TRANSACTIONS`; một số hệ thống cũng có APOC nếu plugin này đã được cài đặt và cho phép, nhưng bài thực hành không yêu cầu APOC.
- Khi một batch fail, lưu đủ mã lỗi và định danh batch để xử lý; không tự tăng `maxRows` vô hạn hoặc retry mọi lỗi nhập liệu không hợp lệ.
- Thực hiện benchmark trên cấu hình gần thực tế về node, relationship, index, mức đồng thời và phần cứng; lô tốt cho 10.000 sản phẩm đơn giản chưa chắc tốt cho 10.000 node liên kết nhiều cạnh.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Transaction quá lâu hoặc timeout | Lô quá lớn, chờ khóa, truy vấn thiếu index | Giảm lô, kiểm tra kế hoạch và contention |
| Có dữ liệu được ghi dù tác vụ báo lỗi | Các batch trước đã commit | Thiết kế checkpoint, idempotency và cảnh báo partial success |
| Chạy lại tạo quan hệ trùng | Dùng `CREATE` hoặc thiếu khóa nghiệp vụ | Dùng `MERGE` phù hợp và unique constraint |
| Batch 500 dòng vẫn gây thiếu bộ nhớ | Mỗi dòng rất lớn hoặc duyệt nhiều entity | Thêm giới hạn byte và kiểm tra transaction memory |
| Có thời gian đệm 2 giây mà một phần dữ liệu phải chờ lâu hơn | Chỉ kiểm tra đồng hồ khi có dòng mới | Dùng scheduler/timer ở hàng đợi nếu cần flush theo thời gian thực |
| Lỗi khi dùng `IN TRANSACTIONS` bên trong `executeWrite` | Nested explicit/implicit transaction không được hỗ trợ | Chọn đúng cơ chế chia batch ở server hoặc client |
| Retry bị cộng tồn kho lần thứ hai | Cập nhật dạng `x = x + delta` không idempotent | Khóa sự kiện, chống xử lý trùng và thiết kế phép ghi |
| Tăng kích thước lô nhưng throughput không tăng | CPU/I/O/index/lock đã là nút thắt | Đo p95, GC, lock và giới hạn đồng thời |

## 10. Bài tập tổng hợp

**Bối cảnh:** Một dịch vụ nhận 12.300 sản phẩm, mỗi sản phẩm khoảng 2 KiB ở đầu vào, cần nhập vào Neo4j với mục tiêu lô không quá 1 MiB. Dữ liệu thỉnh thoảng đến chậm, người dùng muốn thấy tiến độ liên tục và có thể chạy lại sau sự cố.

1. Nếu chỉ áp dụng `maxRows = 500`, có bao nhiêu batch?
2. Nếu mỗi dòng là 2 KiB, 500 dòng ước lượng bao nhiêu KiB? Việc đó có chứng minh transaction sẽ dùng ít hơn 1 MiB bộ nhớ không?
3. Nếu lô 1–7 commit, lô 8 fail, có thể rollback lô 1–7 bằng câu lệnh ngoài cùng không?
4. Hãy chọn cách ghi khi nguồn là file CSV phía server; sau đó chọn cách ghi khi dữ liệu đi qua service Java cần kiểm soát byte và thời gian đệm.
5. Vì sao cần `MERGE` với `sku` duy nhất và checkpoint theo lô?

**Gợi ý đáp án:**

1. `ceil(12300 / 500) = 25` batch (24 batch 500 dòng, một batch 300 dòng).
2. `500 × 2 KiB = 1.000 KiB`, thấp hơn 1 MiB theo dung lượng **ước lượng đầu vào**; transaction Neo4j còn nhiều loại chi phí khác nên không thể kết luận về memory.
3. **Không**. Batch 1–7 đã commit độc lập; cần cơ chế bù trừ nghiệp vụ nếu muốn đảo trạng thái đã ghi.
4. CSV phía server: cân nhắc `LOAD CSV ... CALL { ... } IN TRANSACTIONS OF 500 ROWS`. Service Java: tạo batch với ngưỡng `rows/bytes/bufferAge` và dùng một transaction `executeWrite` cho mỗi batch.
5. `MERGE` trên khóa ổn định giúp chạy lại không nhân đôi node; checkpoint giúp biết tiến độ đã được xác nhận, kết hợp idempotency để xử lý kết quả commit chưa chắc chắn do mất kết nối.

## 11. Checklist trước khi đưa vào vận hành

- [ ] Khóa nghiệp vụ và unique constraint đã được xác định; đầu vào không có khóa `null`.
- [ ] Mỗi batch có giới hạn số dòng và, nếu cần, dung lượng đầu vào ước lượng.
- [ ] Đã phân biệt **thời gian đệm**, **thời gian transaction** và **transaction timeout**.
- [ ] Đã chọn một trong hai cơ chế: `IN TRANSACTIONS` phía Neo4j hoặc quản lý transaction theo lô ở ứng dụng.
- [ ] Đã ghi nhận số batch thành công, batch lỗi, retry, p95 thời gian và throughput.
- [ ] Có khả năng chạy lại sau partial commit, không nhân đôi node/relationship hay áp dụng delta nhiều lần.
- [ ] Kiểm thử dữ liệu lỗi, giá trị thiếu, dòng quá lớn, batch cuối, mất kết nối và ghi đồng thời.
- [ ] Kích thước batch đã được đo với index, dữ liệu và mức đồng thời đại diện cho production.

## Kết luận

Chia lô ghi dữ liệu trong Neo4j là một quyết định về **ranh giới transaction**. `CALL { ... } IN TRANSACTIONS` phù hợp khi chia lô theo số dòng trong Cypher; batching ở Java Driver hoặc Spring Data Neo4j cho phép thêm ngưỡng byte, thời gian đệm, timeout, checkpoint và chính sách retry. Giới hạn theo **số dòng, dung lượng và thời gian** giúp kiểm soát tài nguyên và độ trễ, nhưng không tự bảo đảm toàn bộ lần nhập là một giao dịch nguyên tử. Để khôi phục sau lỗi, cần khóa nghiệp vụ, phép ghi có thể chạy lại và giám sát trên dữ liệu thực tế.

### Tài liệu tham khảo

- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
