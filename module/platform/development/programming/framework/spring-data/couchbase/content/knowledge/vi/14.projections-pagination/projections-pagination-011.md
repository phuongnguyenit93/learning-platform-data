# Kết quả tổng hợp và biểu diễn không phải entity

Trong **Spring Data Couchbase**, entity thường đại diện cho một document có định danh, dữ liệu body và đôi khi có metadata phiên bản CAS. Nhưng không phải mọi câu truy vấn SQL++ đều trả về document. Những truy vấn như `COUNT(1)`, `SUM(...)`, `AVG(...)`, `GROUP BY`, `DISTINCT` hoặc `SELECT RAW` có thể trả về **một con số, một object tổng hợp, một nhóm thống kê hoặc một cấu trúc JSON tùy chỉnh**. Các kết quả đó không tự trở thành entity chỉ vì được đọc từ Couchbase.

Bài học thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**, tập trung vào việc lựa chọn **hình dạng kết quả (result shape)**, ánh xạ kết quả không phải entity sang read model và phân trang đúng đơn vị nghiệp vụ. Chúng ta kết hợp SQL++, Spring Data repository, `CouchbaseTemplate`, Couchbase Java SDK và API reactive, đồng thời xét index, hiệu năng, tính nhất quán, TTL và CAS.

Ví dụ xuyên suốt là trang báo cáo **doanh thu theo kênh bán hàng**: một hàng kết quả tương ứng một kênh, không phải một đơn hàng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt entity document, projection của entity, DTO tổng hợp, scalar và JSON row tùy chỉnh.
2. Dự đoán hình dạng JSON của `SELECT`, `SELECT RAW` và `GROUP BY` trong SQL++.
3. Viết truy vấn `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `COUNT(DISTINCT ...)` và `HAVING` với ngữ nghĩa phù hợp.
4. Ánh xạ kết quả SQL++ không phải entity bằng Couchbase Java SDK sang Java record/DTO.
5. Tránh yêu cầu `@Id`, CAS, `@Version` hoặc `save(...)` cho một hàng tổng hợp không có document tương ứng.
6. Phân trang trên **các nhóm đã tổng hợp**, dùng `LIMIT/OFFSET` hoặc `pageSize + 1` và đếm đúng **số nhóm** khi cần total.
7. Nhận diện sai lệch do `MISSING`/`NULL`, field sai kiểu, `JOIN` làm nhân bản hàng và dữ liệu thay đổi giữa data query/count query.
8. Đánh giá kế hoạch `EXPLAIN`, index, reactive flow và giới hạn bộ nhớ của các phép tổng hợp.

## 2. Ba hình dạng dữ liệu trong cùng một module

Giả sử ứng dụng dùng bucket `shop`, scope `sales`, collection `orders`. Một document đơn hàng:

~~~json
{
  "tenantId": "tenant-01",
  "type": "order",
  "status": "PAID",
  "channel": "WEB",
  "totalCents": 125000,
  "createdAt": "2026-11-20T08:15:00.000Z"
}
~~~

Document key có thể là `order::1001`, được lưu trong metadata Couchbase.

Ba loại kết quả có ý nghĩa khác nhau:

| Hình dạng | Ví dụ | Có tương ứng một document duy nhất không? |
| --- | --- | --- |
| **Entity** | Một `Order` có `@Id` là `order::1001` | Có |
| **Projection của document** | `OrderCard(id, status, totalCents)` từ một đơn hàng | Thường có một document nguồn |
| **Kết quả tổng hợp** | `ChannelTotals("WEB", 350, 42800000)` | Không; là kết quả tính trên nhiều document |
| **Scalar** | Tổng số đơn hàng `350L` | Không |
| **JSON tùy biến** | `{"channel":"WEB","stats":{"count":350}}` | Không nhất thiết |

Một hàng tổng hợp là **read model** được tính ra. Để lưu lại thay đổi, ta không thể gọi `save(channelTotals)` và hy vọng Spring Data tự cập nhật 350 đơn hàng. Nếu cần lưu thống kê bền vững, phải **thiết kế document thống kê riêng**, cơ chế cập nhật, định danh và tính nhất quán của chính nó.

### Entity thường có metadata

Một entity đơn hàng có thể được định nghĩa:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("sales")
@Collection("orders")
public class Order {
    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String type;
    private String status;
    private String channel;
    private Long totalCents;
    private String createdAt;

    // Constructor, getter/setter theo dự án.
}
~~~

`@Id` ánh xạ document key; `@Version` liên quan đến CAS/optimistic locking theo cơ chế Spring Data Couchbase. Nhưng một nhóm doanh thu `WEB` không có một document key/CAS duy nhất đại diện cho mọi đơn hàng đóng góp vào nhóm đó.

## 3. `SELECT` trả về object, `SELECT RAW` có thể trả scalar

Trước khi viết Java mapper, phải biết chính xác row SQL++ mang hình dạng gì.

### Một object với alias

~~~sql
SELECT COUNT(1) AS totalOrders
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID";
~~~

Row điển hình trong kết quả:

~~~json
{
  "totalOrders": 350
}
~~~

Lúc này `rowsAsObject()` phù hợp vì mỗi row là JSON object có khóa `totalOrders`.

### Một scalar với `SELECT RAW`

~~~sql
SELECT RAW COUNT(1)
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID";
~~~

Row là **giá trị số**:

~~~json
350
~~~

Không cố dùng `rowsAsObject()` cho một scalar rồi truy cập `getLong("totalOrders")`: scalar không có object field này. Với Java SDK, chọn đường giải mã tương thích scalar, ví dụ `rowsAs(Long.class)` sau khi kiểm chứng kiểu số được trả trên phiên bản sử dụng.

### Một object gồm nhiều biểu thức

~~~sql
SELECT COUNT(1) AS totalOrders,
       SUM(o.totalCents) AS revenueCents,
       MAX(o.createdAt) AS latestOrderAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID";
~~~

Row:

~~~json
{
  "totalOrders": 350,
  "revenueCents": 42800000,
  "latestOrderAt": "2026-11-20T08:15:00.000Z"
}
~~~

Ba giá trị này mô tả **toàn bộ tập đơn hàng khớp bộ lọc**. Không phải ba thuộc tính của một document đơn hàng ngẫu nhiên.

## 4. `GROUP BY`: một row đại diện một nhóm

Trang báo cáo cần thống kê theo kênh `WEB`, `APP` và `STORE`:

~~~sql
SELECT o.channel AS channel,
       COUNT(1) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID"
GROUP BY o.channel
ORDER BY orderCount DESC, channel ASC;
~~~

Kết quả minh họa:

~~~json
[
  {
    "channel": "WEB",
    "orderCount": 350,
    "revenueCents": 42800000
  },
  {
    "channel": "APP",
    "orderCount": 245,
    "revenueCents": 25900000
  },
  {
    "channel": "STORE",
    "orderCount": 68,
    "revenueCents": 11900000
  }
]
~~~

Có 663 document được đếm nhưng chỉ có **3 row kết quả**. Khi phân trang báo cáo theo kênh, `LIMIT 2` nghĩa là **hai nhóm**, không phải hai đơn hàng.

Một query có thể trả cả các trường tổng hợp và trường khóa nhóm:

~~~sql
SELECT o.channel AS channel,
       COUNT(1) AS orderCount,
       SUM(o.totalCents) AS revenueCents,
       MIN(o.createdAt) AS firstOrderAt,
       MAX(o.createdAt) AS latestOrderAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID"
GROUP BY o.channel
ORDER BY orderCount DESC, channel ASC;
~~~

`MIN`/`MAX` trên chuỗi timestamp chỉ tương ứng thời gian sớm/muộn nếu định dạng được **chuẩn hóa cùng timezone và precision**. Không suy ra thứ tự thời gian đúng nếu document trộn nhiều định dạng chuỗi hoặc kiểu JSON.

## 5. `WHERE`, `GROUP BY`, `HAVING` và `ORDER BY` xử lý những gì?

Một câu SQL++ tổng hợp có nhiều lớp logic:

~~~sql
SELECT o.channel AS channel,
       COUNT(1) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID"
GROUP BY o.channel
HAVING COUNT(1) >= $minOrders
ORDER BY orderCount DESC, channel ASC
LIMIT $limit OFFSET $offset;
~~~

Ý nghĩa:

1. `FROM` chọn keyspace.
2. `WHERE` lọc **document nguồn** trước khi tạo nhóm.
3. `GROUP BY` chia các document còn lại thành từng nhóm theo `channel`.
4. `HAVING` lọc **nhóm tổng hợp**, ví dụ chỉ giữ nhóm có ít nhất 10 đơn hàng.
5. `SELECT` tạo row tổng hợp cho mỗi nhóm đủ điều kiện.
6. `ORDER BY` xác định thứ tự các **row nhóm**.
7. `LIMIT/OFFSET` cắt trang trên tập **nhóm sau tổng hợp**, không phải document ban đầu.

Đừng chuyển `HAVING COUNT(1) >= 10` thành một `WHERE` chỉ vì cả hai đều “lọc”: `WHERE` làm việc trước tổng hợp nên không thể kiểm tra tổng của nhóm theo cách tương đương.

### Sai thứ tự logic: giới hạn document trước khi tổng hợp

Ví dụ ý tưởng sai:

~~~sql
-- Sai ý nghĩa nghiệp vụ nếu muốn doanh thu toàn bộ kỳ báo cáo.
SELECT COUNT(1) AS orderCount,
       SUM(x.totalCents) AS revenueCents
FROM (
    SELECT o.totalCents
    FROM `shop`.`sales`.`orders` AS o
    WHERE o.status = "PAID"
    LIMIT 20
) AS x;
~~~

Query này chỉ tổng hợp **tối đa 20 đơn hàng nằm trong subquery**, không phải toàn bộ đơn hàng đã thanh toán. `LIMIT` trong subquery có thể tạo một thống kê mẫu sai lệch lớn.

Nếu mục tiêu là *top 20 nhóm*, cần `GROUP BY`/`HAVING` trước rồi `ORDER BY/LIMIT` trên **kết quả nhóm**. Không áp dụng paging của entity vào nguồn trước khi thống kê trừ khi nghiệp vụ chủ đích muốn tổng hợp chính tập con đó.

## 6. `COUNT`: các đại lượng dễ nhầm

Với cùng predicate, các dạng count có ngữ nghĩa khác nhau:

~~~sql
SELECT COUNT(1) AS allOrders,
       COUNT(o.totalCents) AS ordersWithAmount,
       COUNT(DISTINCT o.channel) AS distinctChannels
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID";
~~~

| Biểu thức | Đếm cái gì? | Lưu ý |
| --- | --- | --- |
| `COUNT(1)` | Số row đầu vào sau filter | Không phụ thuộc việc field cụ thể có mặt |
| `COUNT(o.totalCents)` | Số row có giá trị field không phải `NULL`/`MISSING` | Có thể nhỏ hơn `COUNT(1)` |
| `COUNT(DISTINCT o.channel)` | Số giá trị `channel` khác nhau được tính theo ngữ nghĩa distinct | Không đếm số document; cần chú ý null/missing |
| `COUNT(1)` sau một `GROUP BY` trong subquery | Số **row nhóm** do subquery trả | Phù hợp để đếm totalGroups |

`COUNT(DISTINCT o.channel)` không phải lúc nào cũng thay được truy vấn đếm nhóm: nếu grouping dùng `IFMISSINGORNULL`, nhiều field, `HAVING`, `JOIN` hoặc business rule khác, số nhóm thực sự có thể khác ý nghĩa của một `COUNT(DISTINCT field)` đơn giản.

### `SUM` và `AVG` xử lý dữ liệu thiếu

~~~sql
SELECT COUNT(1) AS orders,
       COUNT(o.totalCents) AS ordersWithAmount,
       SUM(o.totalCents) AS revenueCents,
       AVG(o.totalCents) AS averageCents
FROM `shop`.`sales`.`orders` AS o
WHERE o.status = "PAID";
~~~

Nếu document thiếu `totalCents` hoặc lưu `NULL`, không nên ngầm hiểu `AVG` đang chia cho mọi đơn hàng. Các hàm tổng hợp thường bỏ qua giá trị không phù hợp theo ngữ nghĩa SQL++; số lượng phần tử thực sự tham gia có thể khác số đơn hàng.

Có thể chủ đích thay missing/null bằng 0:

~~~sql
SUM(IFMISSINGORNULL(o.totalCents, 0)) AS revenueCents
~~~

Nhưng “một đơn hàng chưa có giá trị tiền thì coi là 0” là **quyết định nghiệp vụ**, không phải mẹo kỹ thuật luôn đúng. Document có `totalCents` kiểu string, âm bất hợp lệ hoặc overflow cần được kiểm tra/chuẩn hóa, không dùng fallback để che dữ liệu lỗi.

## 7. Tiền tệ và kiểu số: tổng hợp phải có ngữ nghĩa chính xác

Dữ liệu tiền thường nên lưu theo **đơn vị nhỏ nhất**, ví dụ `totalCents` kiểu số nguyên, để giảm rủi ro sai số so với floating point.

Định nghĩa DTO:

~~~java
public record ChannelTotals(
        String channel,
        long orderCount,
        long revenueCents,
        String latestOrderAt) {}
~~~

Nguyên tắc:

- `COUNT` thường trả giá trị nguyên; ở Java nên chọn kiểu `long` cho số lượng lớn.
- `SUM` trên tiền kiểu nguyên cần kiểm tra kiểu số thực tế trong JSON kết quả, phạm vi tràn và quy tắc làm tròn nếu nguồn không đồng nhất.
- Không dùng `double` để cộng tiền rồi hiển thị như thể là số chính xác.
- Nếu dùng đơn vị tiền khác nhau, `SUM(totalCents)` chỉ có ý nghĩa khi đã **nhóm/lọc theo currency** hoặc quy đổi theo tỷ giá/chính sách rõ ràng.
- Với báo cáo kế toán, yêu cầu về nguồn dữ liệu, thời điểm, idempotency và bất biến số liệu quan trọng hơn việc DTO trông đẹp.

Ví dụ JSON row có thể không chứa `latestOrderAt` nếu biểu thức tạo giá trị `MISSING`, hoặc chứa `null` trong trường hợp không có giá trị phù hợp. DTO và mapper phải quyết định liệu trường đó có bắt buộc hay được phép thiếu.

## 8. Chuẩn hóa khóa nhóm trước khi tổng hợp

Một số đơn hàng không có `channel` hoặc chứa `channel: null`. Nếu UI muốn gộp chúng thành `UNKNOWN`, sử dụng cùng biểu thức trong `SELECT` và `GROUP BY`:

~~~sql
SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel,
       COUNT(1) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID"
GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
ORDER BY orderCount DESC, channel ASC;
~~~

Đây là một **chính sách phân nhóm**: hàng không có channel được đưa vào nhóm `UNKNOWN`. Nếu hệ thống có channel thực tên `UNKNOWN`, chúng sẽ bị **gộp chung**. Nếu cần phân biệt “không nhập” và tên channel thật, hãy chọn khóa sentinel khác hoặc dùng cờ `hasChannel` trong group key.

Với chuỗi channel, chuẩn hóa chữ hoa/thường cũng cần được cân nhắc. `WEB` và `web` có thể bị xem thành hai nhóm nếu dữ liệu không chuẩn hóa.

### `GROUP BY` nhiều chiều

Thống kê theo kênh và ngày UTC:

~~~sql
SELECT o.channel AS channel,
       SUBSTR(o.createdAt, 0, 10) AS dayUtc,
       COUNT(1) AS orderCount
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID"
  AND o.createdAt IS NOT MISSING
  AND o.createdAt IS NOT NULL
GROUP BY o.channel, SUBSTR(o.createdAt, 0, 10)
ORDER BY dayUtc DESC, channel ASC;
~~~

Đoạn query dựa vào giả định `createdAt` là chuỗi ISO-8601 UTC thống nhất: mười ký tự đầu tương ứng ngày UTC. Nếu sản phẩm báo cáo ngày theo giờ Việt Nam, phải chuyển timezone trước khi nhóm; cắt chuỗi UTC rồi gắn nhãn “ngày Việt Nam” là sai nghiệp vụ.

Mỗi **cặp** (`dayUtc`, `channel`) là một row nhóm. Nếu phân trang nhóm này, sort phải có khóa phân xử đủ để xác định thứ tự giữa mọi cặp.

## 9. Không dùng entity mapping cho row tổng hợp

Một query entity thường trả document body cộng metadata cần cho `@Id`, `@Version` và converter. Một query tổng hợp không có một document tương ứng:

~~~sql
SELECT o.channel AS channel,
       COUNT(1) AS orderCount
FROM `shop`.`sales`.`orders` AS o
GROUP BY o.channel;
~~~

Row `{"channel":"WEB","orderCount":350}` **không có**:

- Document key của “document thống kê WEB” — vì row được tính từ nhiều document.
- CAS duy nhất của toàn nhóm — mỗi đơn hàng nguồn có thể có CAS riêng.
- Các field bắt buộc của entity `Order` như `status`, `tenantId`.
- Ý nghĩa mutation “save row này” để cập nhật mọi đơn hàng liên quan.

Vì vậy không nên cố ánh xạ nó sang `Order` rồi gọi `repository.save(...)`. Kết quả tổng hợp nên là **record/DTO/read model** không gắn `@Document` hay `@Id`, trừ khi bạn đang chủ đích quản lý **document thống kê vật hóa riêng**.

### Phân biệt entity projection với aggregate read model

| Nội dung | Entity projection | Aggregate read model |
| --- | --- | --- |
| Nguồn | Thường từ một document | Có thể từ hàng nghìn document |
| Query | `SELECT` ít field của entity | `COUNT/SUM/GROUP BY` và biểu thức |
| ID/CAS | Có thể cần ID/CAS của document nguồn | Thường không có ID/CAS duy nhất |
| Kiểu Java | Interface projection, DTO hoặc entity đầy đủ | DTO/record/scalar/JSON |
| Ghi ngược | Tùy thao tác và metadata; tránh lưu partial entity | Không có mutation tự nhiên cho một row aggregate |
| Phân trang | Trang của document | Trang của **nhóm/result rows** |

Projection trên repository đôi khi vẫn materialize entity rồi mới tạo DTO, tùy query path và khả năng hỗ trợ. Đừng suy rằng khai báo kiểu Java nhỏ đồng nghĩa query SQL++ tự chỉ chọn các field đó.

## 10. Cách đọc row tổng hợp bằng Couchbase Java SDK

Khi cần chắc chắn hình dạng kết quả, có thể viết SQL++ tường minh trong custom repository/service và ánh xạ row.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;

import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public record ChannelTotals(
        String channel,
        long orderCount,
        long revenueCents) {}

// Method minh họa trong class có Cluster được cấu hình.
public List<ChannelTotals> summarizeChannels(
        Cluster cluster, String tenantId) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId is required");
    }

    String statement = """
        SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel,
               COUNT(1) AS orderCount,
               SUM(IFMISSINGORNULL(o.totalCents, 0)) AS revenueCents
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.tenantId = $tenantId
          AND o.type = "order"
          AND o.status = "PAID"
        GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
        ORDER BY orderCount DESC, channel ASC
        """;

    JsonObject parameters = JsonObject.create()
            .put("tenantId", tenantId);

    QueryResult result = cluster.query(
            statement,
            queryOptions().parameters(parameters));

    return result.rowsAsObject().stream()
            .map(row -> new ChannelTotals(
                    row.getString("channel"),
                    row.getLong("orderCount"),
                    row.getLong("revenueCents")))
            .toList();
}
~~~

Đây là một ví dụ **có hợp đồng dữ liệu chặt**: nguồn `totalCents` là số nguyên đúng kiểu, không bị tràn và chính sách thiếu/null cho phép coi là 0. Với dữ liệu không bảo đảm, cần mapper kiểm tra kiểu giá trị, lỗi null, phạm vi số và dữ liệu xấu; không dùng `getLong` một cách mù quáng.

Điểm đáng chú ý:

1. `QueryResult.rowsAsObject()` phù hợp do `SELECT ... AS ...` trả object.
2. Tên khóa `channel`, `orderCount`, `revenueCents` chính là alias SQL++.
3. DTO là kết quả tính toán; không có `@Id` hoặc `@Version`.
4. Tham số tenant được bind, không ghép trực tiếp từ HTTP input.
5. Query trả tối đa một row cho mỗi channel sau khi chuẩn hóa.
6. Việc `GROUP BY` có thể xử lý nhiều document dù kết quả chỉ vài row.
7. `ORDER BY` dùng tiêu chí thống kê rồi khóa channel để có thứ tự xác định khi count bằng nhau.

Nếu cần một **con số duy nhất**, SQL++ `SELECT RAW COUNT(1)` và bộ giải mã scalar phù hợp có thể đơn giản hơn; đừng nhầm đường result scalar với `rowsAsObject()` ở ví dụ này.

## 11. Shape của kết quả còn có thể là object lồng nhau

SQL++ hỗ trợ tạo cấu trúc JSON dựa trên biểu thức:

~~~sql
SELECT o.channel AS channel,
       {
         "orders": COUNT(1),
         "revenueCents": SUM(o.totalCents)
       } AS statistics
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
GROUP BY o.channel
ORDER BY channel ASC;
~~~

Row minh họa:

~~~json
{
  "channel": "WEB",
  "statistics": {
    "orders": 350,
    "revenueCents": 42800000
  }
}
~~~

Java read model có thể là:

~~~java
public record Statistics(long orders, long revenueCents) {}

public record ChannelStatistics(
        String channel, Statistics statistics) {}
~~~

Khi dùng SDK JSON:

~~~java
JsonObject stats = row.getObject("statistics");

ChannelStatistics dto = new ChannelStatistics(
        row.getString("channel"),
        new Statistics(
                stats.getLong("orders"),
                stats.getLong("revenueCents")));
~~~

Cần phân biệt `{"statistics":null}`, thiếu `statistics`, và cấu trúc sai kiểu; đoạn mapper trên chỉ đúng khi schema result đã được kiểm chứng. Đây là lý do **alias SQL++ là một phần của hợp đồng API nội bộ**.

### `SELECT RAW` object và `SELECT` object khác nhau

~~~sql
-- Mỗi row là object {"channel":"WEB","orders":350}.
SELECT RAW {
    "channel": o.channel,
    "orders": COUNT(1)
}
FROM `shop`.`sales`.`orders` AS o
GROUP BY o.channel;
~~~

Trong khi:

~~~sql
-- Mỗi row có lớp bọc {"summary":{"channel":"WEB","orders":350}}.
SELECT {
    "channel": o.channel,
    "orders": COUNT(1)
} AS summary
FROM `shop`.`sales`.`orders` AS o
GROUP BY o.channel;
~~~

Đầu tiên trả object ở cấp row, thứ hai trả object có field `summary`. Cả hai có thể giải mã với `rowsAsObject()` nhưng đường truy cập khác nhau. Đây là **hợp đồng dữ liệu**, không phải biến thể hình thức vô hại.

## 12. `ARRAY_AGG`: tổng hợp danh sách cũng có giới hạn

SQL++ có thể gom danh sách giá trị:

~~~sql
SELECT o.channel AS channel,
       ARRAY_AGG(META(o).id) AS orderIds
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
GROUP BY o.channel;
~~~

Nếu một channel có 200.000 đơn hàng, một row có thể chứa mảng 200.000 ID — rất khác một row nhỏ chỉ có `COUNT` và `SUM`. Nguy cơ:

- Query Service giữ cấu trúc tổng hợp lớn.
- JSON response lớn dù kết quả chỉ một row nhóm.
- SDK/ứng dụng tiêu thụ nhiều bộ nhớ để decode.
- Giới hạn thời gian/tài nguyên và độ trễ tăng cao.
- Không có phân trang **bên trong mảng** chỉ nhờ `LIMIT 1` trên số nhóm.

Nếu giao diện cần danh sách đơn hàng của một channel, hãy **drill down** bằng query entity/projection riêng có `WHERE channel = ... ORDER BY ... LIMIT ...`. Dùng thống kê tổng hợp để hiển thị số liệu và điều hướng đến danh sách nguồn, không nhét toàn bộ IDs vào một row aggregate.

`DISTINCT` trong `ARRAY_AGG(DISTINCT ...)` có thể giảm trùng theo ý nghĩa dữ liệu nhưng không miễn phí bộ nhớ và không thay thế thiết kế phân trang.

## 13. Phân trang kết quả tổng hợp: đơn vị là nhóm

Giả sử có 80 channel và UI muốn 10 channel mỗi trang, sắp theo số đơn hàng giảm dần:

~~~sql
SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel,
       COUNT(1) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID"
GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
ORDER BY orderCount DESC, channel ASC
LIMIT 10 OFFSET 20;
~~~

Với dữ liệu không đổi, query trả **nhóm** thứ 21–30, không phải đơn hàng thứ 21–30.

Thứ tự `ORDER BY orderCount DESC, channel ASC` có hai phần:

- `orderCount` đưa nhóm có nhiều đơn hàng lên trước.
- `channel` phân xử khi nhiều nhóm có số đơn bằng nhau.

Nếu grouping theo nhiều chiều, khóa phân xử phải bao gồm đầy đủ tổ hợp khóa nhóm hoặc một khóa khác thực sự duy nhất ở **mức row kết quả**.

**Lưu ý quan trọng:** số đơn hàng của channel có thể đổi liên tục. Vì `orderCount` là trường sort biến động, ngay cả khi thứ tự có khóa phụ và SQL++ đúng, các nhóm vẫn có thể đổi vị trí giữa các request phân trang. Đối với báo cáo có yêu cầu kết quả cố định, cần snapshot/vật hóa theo kỳ, không chỉ ORDER BY.

## 14. `Page` của nhóm cần count nhóm, không count document

Giả sử query data trả 10 nhóm nhưng tổng số document khớp bộ lọc là 100.000. Nếu UI hiển thị “Trang 1/8” cho 80 channel, total của trang phải là **80 nhóm**, không phải 100.000 đơn hàng.

Hai truy vấn khác mục tiêu:

~~~sql
-- Đếm document nguồn: KHÔNG PHẢI số nhóm.
SELECT COUNT(1) AS totalOrders
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID";
~~~

~~~sql
-- Đếm số nhóm thực sự xuất hiện trong kết quả sau GROUP BY.
SELECT COUNT(1) AS totalGroups
FROM (
    SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel
    FROM `shop`.`sales`.`orders` AS o
    WHERE o.tenantId = $tenantId
      AND o.type = "order"
      AND o.status = "PAID"
    GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
) AS grouped;
~~~

Nếu data query có `HAVING COUNT(1) >= 10`, subquery đếm nhóm **cũng phải có HAVING đó**:

~~~sql
SELECT COUNT(1) AS totalGroups
FROM (
    SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel
    FROM `shop`.`sales`.`orders` AS o
    WHERE o.tenantId = $tenantId
      AND o.type = "order"
      AND o.status = "PAID"
    GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
    HAVING COUNT(1) >= $minOrders
) AS grouped;
~~~

Không đưa `LIMIT/OFFSET` của trang vào subquery đếm tổng, vì như vậy chỉ đếm các nhóm của trang hiện tại thay vì mọi nhóm phù hợp.

### Khi nào `COUNT(DISTINCT)` thay được query nhóm?

Nếu business requirement đúng là “số giá trị channel không null/missing khác nhau”, một câu `COUNT(DISTINCT o.channel)` có thể phù hợp. Nhưng nếu normalize missing thành `UNKNOWN`, group nhiều chiều, dùng `HAVING`, `JOIN` hay phân tách quyền, totalGroups **không nhất thiết** bằng distinct của một field thô. Hãy đếm đúng **row của query nhóm** thay vì tối ưu trước rồi làm sai nghiệp vụ.

## 15. Trả `Slice`/cửa sổ nhóm mà không đếm tổng

Nếu UI chỉ có nút “Tải thêm nhóm tiếp theo”, có thể tránh count tổng bằng cách lấy thêm một nhóm:

~~~sql
SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel,
       COUNT(1) AS orderCount,
       SUM(IFMISSINGORNULL(o.totalCents, 0)) AS revenueCents
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.type = "order"
  AND o.status = "PAID"
GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
ORDER BY orderCount DESC, channel ASC
LIMIT 11 OFFSET 20;
~~~

Với `pageSize = 10`:

1. Nếu query trả 11 nhóm, hiển thị 10 nhóm đầu và `hasNext = true`.
2. Nếu query trả tối đa 10 nhóm, hiển thị toàn bộ và `hasNext = false`.
3. Không cần chạy `COUNT` chỉ để biết `hasNext`.
4. Nhưng server vẫn có thể cần **tổng hợp tất cả document khớp** trước khi chọn top nhóm; `LIMIT 11` không làm aggregation miễn phí.

Có thể dùng `SliceImpl<ChannelTotals>` của Spring Data như một **vỏ metadata tự tạo**, hoặc định nghĩa DTO riêng. `Slice` không hứa tổng số nhóm; `Page` thì cần total tương ứng. Nếu truy vấn custom đã tự quản SQL++ `LIMIT/OFFSET`, tránh đưa thêm `Pageable` vào phương thức `@Query` khiến framework có thể ghép clause trùng.

### Cảnh báo với `PageRequest.of(page, size + 1)`

Nếu yêu cầu trang số 3 với size 10, offset phải là 30. `PageRequest.of(3, 11)` lại sinh offset 33. Vì thế look-ahead cần tăng **LIMIT lên 11 nhưng giữ OFFSET ở 30** trong SQL++ custom, không đổi cả pageSize của `PageRequest` rồi dùng lại page number.

## 16. Một DTO trang tổng hợp minh bạch

Định nghĩa hợp đồng endpoint theo thông tin người dùng thực sự cần:

~~~java
import java.util.List;

public record ChannelTotals(
        String channel,
        long orderCount,
        long revenueCents) {}

public record ChannelWindow(
        List<ChannelTotals> items,
        int page,
        int size,
        boolean hasNext) {}
~~~

Đường truy vấn Java SDK:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

// Method bên trong custom repository/service có Cluster được cấu hình.
public ChannelWindow loadChannelWindow(
        Cluster cluster,
        String tenantId,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid page/size");
    }
    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId required");
    }

    long offset = Math.multiplyExact((long) page, (long) size);
    if (offset > 10_000) {
        throw new IllegalArgumentException("Page too deep");
    }

    String sql = """
        SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel,
               COUNT(1) AS orderCount,
               SUM(IFMISSINGORNULL(o.totalCents, 0)) AS revenueCents
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.tenantId = $tenantId
          AND o.type = "order"
          AND o.status = "PAID"
        GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
        ORDER BY orderCount DESC, channel ASC
        LIMIT $limit OFFSET $offset
        """;

    JsonObject params = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", size + 1)
            .put("offset", offset);

    QueryResult queryResult = cluster.query(
            sql, queryOptions().parameters(params));

    List<ChannelTotals> fetched = queryResult.rowsAsObject()
            .stream()
            .map(row -> new ChannelTotals(
                    row.getString("channel"),
                    row.getLong("orderCount"),
                    row.getLong("revenueCents")))
            .toList();

    boolean hasNext = fetched.size() > size;
    List<ChannelTotals> visible = hasNext
            ? fetched.subList(0, size)
            : fetched;

    return new ChannelWindow(
            List.copyOf(visible), page, size, hasNext);
}
~~~

Cần nhớ:

- DTO `ChannelTotals` **không phải entity** và không có CAS.
- Query trả tối đa `size + 1` **nhóm**, không phải `size+1` document nguồn.
- `tenantId` là giá trị bind, phải lấy từ ngữ cảnh xác thực khi ứng dụng multi-tenant.
- Giá trị `size <= 100` và offset tối đa chỉ là **chính sách API minh họa**, không phải giới hạn cố định của Couchbase.
- Việc tính tiền/kiểu số cần data-quality validation như phần trước.
- Hãy đọc `EXPLAIN` và query profile: `GROUP BY` có thể cần xử lý nhiều document ngay cả khi output nhỏ.

## 17. Nếu API cần tổng nhóm chính xác

Cung cấp response khác:

~~~java
public record ChannelPage(
        List<ChannelTotals> items,
        int page,
        int size,
        long totalGroups,
        long totalPages) {}
~~~

Đường thực thi:

1. Data query với `GROUP BY`, `HAVING` (nếu có), `ORDER BY` và `LIMIT/OFFSET` lấy nội dung.
2. Count query dùng subquery `GROUP BY`/`HAVING` tương đương nhưng **không phân trang** để có `totalGroups`.
3. Tính `totalPages` bằng chia nguyên làm tròn lên:

~~~java
long totalPages = totalGroups / size
        + (totalGroups % size == 0 ? 0 : 1);
~~~

4. Dựng `ChannelPage` hoặc `PageImpl<ChannelTotals>` nếu cần giao tiếp với API Spring Data. Việc tự dựng `PageImpl` **không chạy count miễn phí**; total vẫn phải được tính ở bước trước.

**Chú ý nhất quán:** data query và count query là hai lần đọc SQL++ riêng. Nếu đơn hàng được thêm, xóa, đổi `status` hoặc `channel` giữa hai lần, `totalGroups` có thể khác tập nhóm đã tạo trang. `PageImpl`, `Mono.zip` hoặc `REQUEST_PLUS` không mặc nhiên biến chúng thành cùng một snapshot.

## 18. Vì sao `@Query`/repository không phải lúc nào cũng phù hợp?

Spring Data Couchbase mạnh trong entity mapping và repository methods. Ví dụ query entity có thể dùng Spring Expression như `#{#n1ql.selectEntity}` và `#{#n1ql.filter}` để chọn document cùng metadata cần thiết.

Một query tổng hợp:

~~~sql
SELECT o.channel AS channel,
       COUNT(1) AS orderCount
FROM `shop`.`sales`.`orders` AS o
GROUP BY o.channel;
~~~

lại không phải “query entity bị thiếu vài trường”, mà có **hình dạng result hoàn toàn khác**.

Có những lựa chọn:

| Đường thực thi | Khi nào dùng | Điều phải kiểm chứng |
| --- | --- | --- |
| Repository derived query | Tìm entity/projection từ document | Query derivation, mapping, sort và metadata |
| Repository `@Query` tùy chỉnh | Query phù hợp khả năng repository/converter | Kiểu return DTO, alias, count/pagination có được hỗ trợ đúng không |
| `CouchbaseTemplate` | Truy vấn/mapping theo API Spring Data | API tương ứng phiên bản, khả năng map result aggregate |
| Couchbase Java SDK `Cluster.query` | Kiểm soát SQL++ và result shape rõ ràng | Mapping JSON/DTO, index, consistency, error handling |
| SDK reactive / template reactive | Non-blocking trong WebFlux | Giới hạn tại server, backpressure, bộ đệm |

Đừng tự giả định repository `@Query` trả `Page<ChannelTotals>` sẽ tự suy ra một count query nhóm đúng ngữ nghĩa; count của document nguồn có thể khác count của nhóm. Với `GROUP BY`/`HAVING`/`JOIN` phức tạp, **tách custom repository** thường dễ kiểm soát hơn.

Nếu dùng `@Query` có `Pageable`, Spring Data Couchbase có thể tự nối `ORDER BY/LIMIT/OFFSET`; không viết chúng lặp trong inline query rồi lại thêm `Pageable` nếu đường module/phiên bản đó ghép clause tự động. Query custom SDK tự quản toàn bộ SQL++ sẽ minh bạch hơn cho ví dụ aggregation.

### Đừng gắn `@Document` vào DTO thống kê chỉ để converter chấp nhận

Một read model `ChannelTotals` không cần bucket/scope/collection riêng, `@Id` hay `@Version`. Khi thật sự muốn lưu số liệu vật hóa, hãy tạo **một entity thống kê khác** có ID (ví dụ theo tenant, kỳ, channel) và cơ chế cập nhật riêng; đó là một bài toán write model khác với query aggregate hiện tại.

## 19. Reactive: tổng hợp không biến thành entity

Reactive không làm thay đổi shape SQL++. Đường Java SDK có thể đọc các row object như sau:

~~~java
import com.couchbase.client.java.ReactiveCluster;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

// Ví dụ method trong custom repository với ReactiveCluster.
public Flux<ChannelTotals> streamChannelTotals(
        ReactiveCluster cluster,
        String tenantId) {

    String sql = """
        SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel,
               COUNT(1) AS orderCount,
               SUM(IFMISSINGORNULL(o.totalCents, 0)) AS revenueCents
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.tenantId = $tenantId
          AND o.type = "order"
          AND o.status = "PAID"
        GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
        ORDER BY orderCount DESC, channel ASC
        """;

    JsonObject params = JsonObject.create().put("tenantId", tenantId);

    return cluster.query(sql, queryOptions().parameters(params))
            .flatMapMany(result -> result.rowsAsObject())
            .map(row -> new ChannelTotals(
                    row.getString("channel"),
                    row.getLong("orderCount"),
                    row.getLong("revenueCents")));
}
~~~

Ví dụ này **chưa có `LIMIT`**, nên không dùng `collectList()` vô điều kiện nếu số nhóm có thể lớn. Trong API phân trang, đặt `LIMIT/OFFSET` hoặc predicate cursor **trong SQL++**, rồi mới gom tối đa `pageSize + 1` row vào `Mono<ChannelWindow>`.

`Flux.take(10)` và `Flux.limitRate(10)` không tự bảo đảm Couchbase Server chỉ tính 10 nhóm. Server có thể phải quét, join, sort hoặc aggregate nhiều document trước khi phát row. Backpressure quản lý luồng phần tử, **không phải phép tối ưu `GROUP BY` tự động**.

Nếu đồng thời chạy data query và count query:

~~~java
Mono<ChannelWindow> window = loadWindowReactive(...);
Mono<Long> totalGroups = countGroupsReactive(...);

Mono<ChannelPage> page = Mono.zip(window, totalGroups)
        .map(tuple -> buildPage(tuple.getT1(), tuple.getT2()));
~~~

Các hàm `loadWindowReactive`, `countGroupsReactive` và `buildPage` là **hàm ứng dụng minh họa**. Hai query chạy bất đồng bộ vẫn có thể nhìn các trạng thái dữ liệu khác nhau; cần thống nhất mức nhất quán với yêu cầu báo cáo.

## 20. Đọc `EXPLAIN` của query tổng hợp

Truy vấn aggregate có thể là công việc rất khác query tìm 20 entity.

~~~sql
EXPLAIN
SELECT IFMISSINGORNULL(o.channel, "UNKNOWN") AS channel,
       COUNT(1) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-01"
  AND o.type = "order"
  AND o.status = "PAID"
GROUP BY IFMISSINGORNULL(o.channel, "UNKNOWN")
ORDER BY orderCount DESC, channel ASC
LIMIT 10;
~~~

Một index ứng viên phục vụ predicate/nhóm:

~~~sql
CREATE INDEX ix_orders_tenant_status_channel
ON `shop`.`sales`.`orders` (
    tenantId,
    type,
    status,
    channel
);
~~~

Index trên **không mặc nhiên** cover `totalCents` hay biểu thức chuẩn hóa `IFMISSINGORNULL`. Optimizer có thể phải `Fetch` document body hoặc xử lý tổng hợp ngoài Index Service. Chỉ số index entries và số nhóm kết quả là hai lượng hoàn toàn khác nhau.

Khi dùng `EXPLAIN`/profiling, kiểm tra:

1. **IndexScan:** scan đúng tenant/type/status không? Độ chọn lọc cao hay thấp?
2. **Fetch:** index có chứa đủ trường và biểu thức để tính aggregate không?
3. **Group/Aggregate:** nhóm được xử lý ở Query Service hay có khả năng pushdown xuống indexer?
4. **Order:** sort theo `orderCount` có cần tính xong tất cả nhóm rồi sắp xếp không?
5. **LIMIT:** được áp dụng vào giai đoạn nào? `LIMIT 10` trên nhóm không tương đương chỉ xem 10 document.
6. **COUNT nhóm:** query đếm totalGroups có lặp lại công việc grouping đắt không?
7. **Bộ nhớ/CPU/latency:** cardinality số nhóm, mảng tổng hợp, `DISTINCT` và join ảnh hưởng ra sao?
8. **Phiên bản:** các tối ưu group aggregation/index pushdown phụ thuộc query plan và khả năng Couchbase Server cụ thể.

Couchbase có các tối ưu index group/aggregate pushdown trong những điều kiện nhất định; nhưng **không giả định chúng luôn được áp dụng**. Hãy so plan thực tế và đo p50/p95 latency, rows scanned, số `Fetch`, kết quả đúng khi dữ liệu lớn.

### Đừng thêm index cho mọi chiều báo cáo

Index trên nhiều field giúp một số query nhưng tăng chi phí lưu trữ và cập nhật index. Với nhiều báo cáo theo ngày, vùng, loại sản phẩm và channel, hãy chọn index theo workload phổ biến; báo cáo nặng có thể cần **materialized statistics** hoặc pipeline xử lý riêng thay vì truy vấn lại toàn bộ document trên mọi HTTP request.

## 21. `JOIN`, `UNNEST` và lỗi nhân bản số liệu

Giả sử mỗi đơn hàng có mảng `items`. Một query:

~~~sql
SELECT COUNT(1) AS linesCount
FROM `shop`.`sales`.`orders` AS o
UNNEST o.items AS item
WHERE o.status = "PAID";
~~~

`COUNT(1)` ở đây đếm **dòng item sau UNNEST**, không phải số đơn hàng. Một đơn có 5 item tạo 5 row trung gian.

Nếu muốn đếm đơn hàng duy nhất, có thể cần `COUNT(DISTINCT META(o).id)` với predicate và join shape phù hợp, hoặc thay đổi cách viết để **không nhân bản document trước khi đếm**. Nếu muốn đếm số lượng item, `COUNT(1)` sau UNNEST là hợp lý.

Một lỗi khác: sum doanh thu đơn hàng trên kết quả UNNEST:

~~~sql
-- Cẩn trọng: cùng totalCents của đơn có thể bị cộng lặp theo số item.
SELECT SUM(o.totalCents) AS wrongRevenue
FROM `shop`.`sales`.`orders` AS o
UNNEST o.items AS item
WHERE o.status = "PAID";
~~~

Ví dụ một đơn 100.000 đồng có 4 dòng hàng: nếu sum giá trị cấp đơn sau UNNEST, có thể cộng 4 lần. Cách sửa phụ thuộc nghiệp vụ: sum một lần ở cấp đơn, hoặc sum `item.lineTotalCents` ở cấp dòng (và kiểm soát dữ liệu), không lấy `SUM(DISTINCT o.totalCents)` làm mẹo chung vì hai đơn khác nhau có thể có tổng tiền bằng nhau.

**Luôn xác định đơn vị đo trước khi viết aggregation:** document order, order line, khách hàng duy nhất hay nhóm channel/ngày. Khi unit-of-analysis sai, query vẫn chạy và trả số “đẹp” nhưng sai nghiệp vụ.

## 22. Thời điểm tính và tính nhất quán của báo cáo

Tổng hợp thường được dùng cho dashboard, nơi người dùng có thể giả định số liệu “chính xác đến thời điểm hiện tại”. Nhưng trong Couchbase:

- Dữ liệu có thể được thêm/xóa/sửa trong lúc hai query chạy.
- Secondary index có độ trễ cập nhật tùy scan consistency.
- `REQUEST_PLUS` giúp query chờ index bắt kịp tới mốc request theo semantics của Query Service, nhưng **không tự tạo snapshot chung cho nhiều HTTP request**.
- TTL làm document biến mất khỏi query khi hết hạn.
- Một document đổi `status` hoặc `channel` có thể chuyển giữa các nhóm.
- `totalGroups`, `orderCount` và `revenueCents` có thể đổi qua thời gian.

### CAS có giải quyết được không?

Không. CAS là token phiên bản **một document**, hữu ích cho optimistic locking khi sửa document đó. Một row `ChannelTotals("WEB", ...)` cộng từ nhiều đơn hàng không có CAS thống nhất. Không dùng CAS làm ID của nhóm hay chứng minh mọi phép tổng hợp được tính trên cùng một snapshot xuyên nhiều request.

### Khi nào cần kết quả vật hóa?

Nếu một báo cáo doanh thu theo kỳ cần được chốt ở mốc T0:

1. Xác định tập order và quy tắc nghiệp vụ thuộc kỳ.
2. Tạo snapshot/aggregation job theo cơ chế nhất quán đã thiết kế.
3. Ghi kết quả vào **document báo cáo riêng** với ID xác định theo tenant/kỳ/kênh/phiên bản báo cáo.
4. Có thể dùng CAS/`@Version` cho cạnh tranh cập nhật **document báo cáo vật hóa** đó, không phải cho aggregate SQL++ tạm thời.
5. Lưu thời điểm tính, nguồn dữ liệu và trạng thái hoàn tất để người dùng biết độ mới của báo cáo.
6. Có chiến lược retry/idempotency, đối soát và dọn tài nguyên.

Một transaction ngắn có thể bảo vệ một tập mutation phù hợp, nhưng không mặc nhiên bảo đảm một báo cáo scan hàng triệu document được “chốt” bằng cách để transaction sống trong nhiều HTTP request. Phải thiết kế theo giới hạn và semantics transaction của Couchbase thực tế.

## 23. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Trả `Order` entity từ `SELECT COUNT/SUM` | Thiếu ID/CAS/field, mapping sai | Dùng DTO/record/scalar phù hợp result shape |
| Gọi `save` trên row thống kê | Không biết cập nhật document nào | Tách read model; muốn lưu thì thiết kế entity thống kê riêng |
| Dùng `rowsAsObject()` cho `SELECT RAW COUNT(1)` | Scalar không có object field | Dùng bộ giải mã scalar phù hợp |
| Query trả `AS orderCount`, mapper đọc `count` | Null/missing hoặc mapping lỗi | Khóa alias bằng contract/test |
| `COUNT(o.field)` thay `COUNT(1)` | Bỏ qua row có null/missing | Chọn biểu thức đếm đúng ý nghĩa |
| `SUM(totalCents)` trên dữ liệu sai kiểu | Kết quả sai, null hoặc lỗi tùy trường hợp | Validate/migrate schema, xử lý số và tiền rõ |
| `GROUP BY channel` nhưng count total từ document | `totalPages` lớn sai | Count **nhóm**, dùng subquery có GROUP/HAVING tương đương |
| Đếm group mà quên `HAVING` | Total không khớp danh sách nhóm | Count cùng điều kiện lọc nhóm |
| LIMIT đặt trong nguồn trước GROUP | Tổng hợp chỉ một subset | Tổng hợp trước, phân trang trên row nhóm |
| `ORDER BY orderCount` không có khóa phụ | Nhóm hòa điểm không có thứ tự toàn phần | Thêm khóa nhóm duy nhất để phân xử |
| Tổng hợp sau `UNNEST` nhưng quên row bị nhân | Đếm/sum quá lớn | Xác định unit-of-analysis, count distinct đúng chỗ |
| `ARRAY_AGG` tất cả ID một nhóm | Bộ nhớ/payload rất lớn | Query drilldown phân trang riêng |
| Dùng `Slice` rồi nghĩ COUNT được bỏ và aggregation rẻ | GROUP vẫn có thể scan nhiều document | `EXPLAIN`, index, đo latency |
| Dùng entity projection để tự động map mọi JSON aggregate | Converter có thể không hỗ trợ như mong đợi | Kiểm thử phiên bản hoặc SDK/custom repository |
| Count và data query độc lập nhưng nói cùng snapshot | Sai total khi dữ liệu động | Chấp nhận live semantics hoặc snapshot vật hóa |
| Không lọc tenant ở query aggregate | Rò rỉ số liệu tổng hợp đa tenant | Áp dụng auth/filter cho mọi truy vấn |
| `Mono.zip` được coi là giao dịch | Hai query có thể thấy trạng thái khác | Thiết kế tính nhất quán độc lập |

## 24. Checklist kiểm thử tích hợp

### Hình dạng dữ liệu

1. Query `SELECT COUNT(1) AS totalOrders` trả object có alias đúng.
2. Query `SELECT RAW COUNT(1)` trả scalar, không dùng nhầm `rowsAsObject()`.
3. `GROUP BY` trả một row cho mỗi nhóm theo khóa chuẩn hóa.
4. Nested object `AS statistics` được map đúng tầng JSON.
5. Mọi numeric field có type/range và nullability phù hợp.
6. Không có `@Id`/CAS giả tạo trong DTO aggregate.

### Ngữ nghĩa tổng hợp

7. Test 0, 1 và nhiều document khớp predicate.
8. Document thiếu field, field `null` hoặc sai kiểu không làm query im lặng sai kết quả.
9. `COUNT(1)` khác `COUNT(field)` khi field thiếu.
10. `AVG` có mẫu số đúng; `SUM`/tiền không bị làm tròn sai.
11. `GROUP BY IFMISSINGORNULL` xử lý sentinel đúng, kể cả sentinel thật.
12. `HAVING` loại đúng nhóm không đủ điều kiện.
13. `JOIN/UNNEST` không nhân bản đơn vị nghiệp vụ sai.
14. Truy vấn theo ngày có timezone và timestamp format nhất quán.

### Phân trang và bảo mật

15. Page size 2 và có 5 nhóm: trang đầu 2, trang hai 2, trang cuối 1.
16. `LIMIT size+1` trả thêm một **nhóm** để tính `hasNext`.
17. `totalGroups` đếm row sau `GROUP BY/HAVING`, không dùng totalOrders.
18. `ORDER BY` có khóa phụ duy nhất theo row nhóm.
19. Dữ liệu thêm/xóa khiến thứ tự group có thể đổi: API không hứa snapshot không có.
20. Tenant, status, type discriminator và quyền truy cập giống nhau ở mọi query, kể cả count.
21. `Pageable` kết hợp `@Query` không vô tình tạo `ORDER BY/LIMIT/OFFSET` trùng.
22. Page size/offset có giới hạn hợp lý; không gom không giới hạn kết quả.

### Hiệu năng và reactive

23. `EXPLAIN` của grouped query và grouped count được kiểm tra riêng.
24. Đo số index entries, `Fetch`, sort, latency p95 và số nhóm theo dữ liệu lớn.
25. Reactive pipeline không `block()` trên event loop.
26. `collectList()` chỉ áp dụng sau khi query có giới hạn row kết quả.
27. Hủy request/timeout và lỗi query không biến thành “báo cáo rỗng” giả.
28. Nếu dùng result materialization, kiểm thử retry/idempotency và timestamp báo cáo.

### Bảng test mẫu

Giả sử dữ liệu đứng yên:

| Channel | Số đơn PAID | Doanh thu cents |
| --- | ---: | ---: |
| WEB | 5 | 5000 |
| APP | 3 | 3600 |
| STORE | 1 | 700 |

Với `size = 2` và `ORDER BY orderCount DESC, channel ASC`:

- Trang 0 trả `WEB` và `APP`, `hasNext=true`.
- Trang 1 trả `STORE`, `hasNext=false`.
- `totalGroups = 3` và `totalOrders = 9` — **hai số khác nhau**.
- Nếu thêm một document PAID vào nhóm STORE, `totalOrders` tăng lên 10 nhưng `totalGroups` vẫn bằng 3.
- Nếu xuất hiện kênh mới `PARTNER`, `totalGroups` có thể tăng thành 4 và thứ tự nhóm thay đổi.

## 25. Bài tập thực hành

Xây dựng API báo cáo:

~~~http
GET /reports/orders/by-channel?page=0&size=20
~~~

Yêu cầu:

1. Dữ liệu nằm trong collection `orders`, có tenant, status, channel, totalCents và createdAt.
2. Viết SQL++ tính `orderCount`, `revenueCents` cho đơn `PAID` theo channel.
3. Chuẩn hóa channel thiếu/null thành nhóm rõ ràng theo chính sách nghiệp vụ.
4. Dùng `ChannelTotals` là **record DTO**, không gắn `@Document`.
5. Thực thi query bằng custom repository/SDK, map alias tường minh.
6. Sắp xếp `orderCount DESC, channel ASC` và `LIMIT size+1` để có `hasNext`.
7. Khi UI yêu cầu total, viết query count **số nhóm** tương đương `GROUP BY/HAVING`.
8. Tạo ít nhất ba nhóm, có nhóm cùng `orderCount` và một document thiếu `totalCents`.
9. Thử `SELECT RAW COUNT(1)` và so sự khác biệt result shape với `SELECT COUNT(1) AS total`.
10. Thêm một join hoặc unnest để thấy nguy cơ nhân doanh thu; sửa theo unit-of-analysis.
11. Dùng `EXPLAIN` kiểm tra index/filter, aggregation và `Fetch`.
12. Thử dữ liệu thay đổi giữa query trang và query total; mô tả giới hạn nhất quán.
13. Viết một bản reactive dùng `ReactiveCluster.query` nhưng không dựa trên `Mono<Page<...>>` tự động.
14. Mở rộng báo cáo theo ngày UTC và sau đó theo timezone kinh doanh; giải thích khác biệt.

### Câu hỏi tự kiểm tra

1. Vì sao một row `{"channel":"WEB","orderCount":350}` không phải entity `Order`?
2. `META(o).id` có thể dùng làm ID duy nhất cho một row `GROUP BY channel` không? Vì sao?
3. Hình dạng result của `SELECT RAW COUNT(1)` khác `SELECT COUNT(1) AS total` thế nào?
4. `COUNT(o.totalCents)` và `COUNT(1)` khác nhau trong trường hợp nào?
5. Vì sao `AVG(totalCents)` có thể không chia cho tổng số đơn hàng?
6. Phân biệt `WHERE` và `HAVING` khi lọc những channel có ít nhất 10 đơn.
7. Tại sao `LIMIT 10` sau GROUP BY có thể vẫn quét rất nhiều document?
8. Với 100.000 đơn thuộc 15 nhóm, total của `Page<ChannelTotals>` phải là số nào?
9. Vì sao `COUNT(DISTINCT channel)` có thể không tương đương số nhóm sau normalize và HAVING?
10. Key phân xử của sort nhóm nên là gì khi nhiều nhóm có số đơn bằng nhau?
11. Tại sao `ARRAY_AGG` có thể tốn bộ nhớ dù chỉ trả một row cho mỗi nhóm?
12. Một `SUM(order.totalCents)` sau `UNNEST items` có thể sai thế nào?
13. Tại sao `@Version`/CAS của một entity không áp dụng trực tiếp cho tổng hợp nhiều entity?
14. Khi nào cần vật hóa báo cáo thay vì truy vấn aggregate trực tiếp mỗi request?
15. Vì sao `Mono.zip(dataQuery, countQuery)` không mặc nhiên tạo snapshot?

## 26. Tài liệu chính thức và lưu ý theo phiên bản

- [Couchbase SQL++ — SELECT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/selectclause.html): `SELECT`, alias và hình dạng row kết quả.
- [Couchbase SQL++ — GROUP BY](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/groupby.html): nhóm dữ liệu, aggregation và `HAVING`.
- [Couchbase SQL++ — Aggregate Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/aggregatefun.html): `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` và các hàm tổng hợp.
- [Couchbase SQL++ — ORDER BY](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/orderby.html), [LIMIT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/limit.html) và [OFFSET](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/offset.html): thứ tự và giới hạn result rows.
- [Couchbase SQL++ — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): kiểm tra query plan.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): result shape, `QueryResult`, query parameters và SDK access.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository query, `@Query`, mapping và lưu ý về `Pageable`.
- [Spring Data — Projections](https://docs.spring.io/spring-data/couchbase/reference/repositories/projections.html): projection và các giới hạn theo module.
- [Spring Data — Query Return Types](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-return-types-reference.html): `Page`, `Slice`, `List` và publisher.

Tùy phiên bản **Couchbase Server, Java SDK và Spring Data Couchbase**, chi tiết mapping scalar/DTO, các tối ưu hóa index aggregate pushdown, hành vi repository `@Query` và reactive return types có thể khác. Vì vậy phải kiểm chứng **SQL++ thực sự chạy, shape JSON trả về và integration tests** trước khi dùng ví dụ để cam kết vận hành.

> **Ghi nhớ:** Đừng cố biến mọi kết quả SQL++ thành entity. `COUNT` có thể là một số; `GROUP BY` trả row của **nhóm**, không phải document; `SELECT RAW` có thể trả scalar hoặc object tùy biểu thức. Hãy chọn đúng DTO/read model, đếm **số nhóm** khi phân trang thống kê, và chỉ dùng CAS/`@Version` khi có một document thực sự cần kiểm soát cập nhật.
