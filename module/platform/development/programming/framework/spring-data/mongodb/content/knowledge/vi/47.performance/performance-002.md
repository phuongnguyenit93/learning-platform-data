# Explain và executionStats để kiểm tra kế hoạch truy vấn

Khi một câu truy vấn MongoDB chạy chậm trong ứng dụng **Spring Data MongoDB**, đo thời gian gọi `MongoTemplate` hoặc repository mới chỉ cho biết triệu chứng. Muốn biết truy vấn đang quét toàn bộ collection, dùng index nào, có phải sắp xếp trong bộ nhớ hay đọc bao nhiêu document để trả về vài kết quả, ta cần xem **kế hoạch truy vấn** (*query execution plan*) bằng `explain()`.

`explain` giúp phân tích truy vấn `find`, các pipeline `aggregate` và những thao tác khác được MongoDB hỗ trợ. Trong đó, chế độ **`executionStats`** bổ sung số liệu thực thi để kiểm tra xem kế hoạch đã chọn có thực sự hiệu quả với điều kiện lọc, dữ liệu và index hiện có hay không. Đây là một kỹ năng quan trọng khi thiết kế truy vấn, index và chẩn đoán hiệu năng trong module Spring Data MongoDB.

## 1. Trình tối ưu truy vấn quyết định những gì?

Khi nhận một truy vấn, MongoDB cần lựa chọn cách tìm và xử lý dữ liệu. Nó có thể:

- Duyệt toàn bộ collection (`COLLSCAN`) rồi lọc từng document.
- Duyệt một index (`IXSCAN`), có thể lấy document gốc bằng `FETCH`.
- Kết hợp các bước lọc, giới hạn (`LIMIT`), bỏ qua (`SKIP`), chiếu trường (`PROJECTION`) và sắp xếp (`SORT`).
- Xử lý các nhánh truy vấn hoặc pipeline, ví dụ `$or`, `$lookup`, `$group` hay truy vấn trên sharded cluster.

Tập hợp các bước được chọn gọi là **winning plan**. Có index trong collection **không đồng nghĩa** với việc mọi truy vấn sẽ dùng index đó; lựa chọn còn phụ thuộc vào điều kiện lọc, thứ tự sort, độ chọn lọc, kiểu dữ liệu, collation, thống kê và các lựa chọn thực thi của phiên bản MongoDB.

Ví dụ collection `orders` có các document:

~~~javascript
{
  _id: ObjectId("6650ef9c2d5b40641f000001"),
  tenantId: "T01",
  status: "PAID",
  createdAt: ISODate("2026-09-20T10:30:00Z"),
  totalMinor: 250000,
  customerId: "C104"
}
~~~

Ứng dụng cần lấy **20 đơn hàng đã thanh toán mới nhất** của tenant `T01`, tạo từ đầu tháng 9/2026. Nếu collection có hàng triệu đơn, chỉ thêm `limit(20)` không bảo đảm truy vấn sẽ nhanh: MongoDB có thể vẫn phải xem rất nhiều document hoặc sort rất nhiều kết quả trước khi lấy 20 bản ghi.

## 2. Ba chế độ `explain` nên phân biệt

MongoDB cung cấp ba mức thông tin thường dùng:

| Verbosity | Thông tin chính | Khi nào dùng |
| --- | --- | --- |
| `queryPlanner` | Kế hoạch được chọn, các kế hoạch ứng viên và thông tin index liên quan; thường không thực thi truy vấn đầy đủ để lấy số liệu thực tế | Xem MongoDB dự kiến thực hiện bằng cách nào |
| `executionStats` | Bao gồm `queryPlanner` và các số liệu thực thi của kế hoạch thắng, như `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis` | Đo lượng công việc thực tế mà kế hoạch đã dùng |
| `allPlansExecution` | Thêm thông tin về quá trình đánh giá thử các kế hoạch ứng viên, trong phạm vi MongoDB thu thập | Tìm hiểu vì sao một plan được chọn thay cho plan khác |

Trong `mongosh`, có thể xem trực tiếp truy vấn:

~~~javascript
const filter = {
  tenantId: "T01",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-09-01T00:00:00Z") }
};

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("queryPlanner");

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("allPlansExecution");
~~~

`explain` không trả về danh sách đơn hàng như `find()` thông thường; nó trả về tài liệu giải thích kế hoạch. Với `executionStats`, MongoDB thực thi công việc cần thiết để thu thập thống kê, vì thế nên kiểm soát tác động khi chạy trên tập dữ liệu lớn hoặc trên môi trường production.

> **Lưu ý về đo lường:** `explain` không sử dụng plan cache hiện có theo cách của một truy vấn thông thường và không thêm lựa chọn plan vào cache. Thời gian trong `explain` không phải thời gian phản hồi đầu-cuối của ứng dụng: nó không đo đầy đủ mạng, ánh xạ object Spring Data, serialization hay thời gian downstream xử lý dữ liệu. Dùng `explain` để hiểu kế hoạch và lượng công việc; dùng đo latency thực tế để xác nhận hiệu năng ứng dụng.

## 3. Những trường quan trọng nhất trong kết quả

Kết quả `explain` có nhiều trường và có thể khác nhau giữa các phiên bản MongoDB, classic execution engine, slot-based execution engine (SBE), cấu trúc aggregation và sharded cluster. Đừng viết chương trình kiểm tra hiệu năng chỉ dựa vào một đường dẫn JSON cố định của `winningPlan`.

| Trường / thành phần | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| `queryPlanner.winningPlan` | Kế hoạch MongoDB chọn | Xem chuỗi stage, indexName, hướng duyệt, điều kiện biên `indexBounds` |
| `queryPlanner.rejectedPlans` | Các kế hoạch ứng viên không được chọn, nếu có | Hỗ trợ tìm hiểu cạnh tranh giữa index; không khẳng định mọi phương án đã được thử |
| `executionStats.nReturned` | Số document kết quả kế hoạch thực thi trả về | Mẫu số hữu ích khi so sánh lượng quét, nhưng cần xét `limit` và độ chọn lọc |
| `executionStats.totalKeysExamined` | Số index entry/key được kiểm tra | Cao bất thường có thể báo vùng quét index quá rộng |
| `executionStats.totalDocsExamined` | Số lần kiểm tra document | Nếu rất cao so với kết quả, có thể đang lọc sau khi đọc nhiều document |
| `executionStats.executionTimeMillis` | Thời gian thực thi ước lượng theo bộ đo của MongoDB | Để tham khảo trong điều kiện thử nghiệm tương đương, không đại diện cho latency API |
| `executionStats.executionStages` | Số liệu ở từng stage | Tìm bước gây nhiều reads, scan hoặc sort |
| `indexName`, `indexBounds` | Index được sử dụng và phạm vi quét index | Kiểm tra điều kiện lọc có giới hạn được phạm vi quét như mong muốn không |

`totalDocsExamined` đếm các lượt kiểm tra document, **không nhất thiết bằng số document duy nhất**. `totalKeysExamined` cũng không phải số kết quả được trả. Hai chỉ số này cần được đọc cùng `nReturned`, điều kiện lọc và giới hạn kết quả.

Một kết quả **minh họa đã rút gọn** sau khi có index phù hợp có thể trông như sau:

~~~json
{
  "queryPlanner": {
    "winningPlan": {
      "stage": "LIMIT",
      "inputStage": {
        "stage": "FETCH",
        "inputStage": {
          "stage": "IXSCAN",
          "indexName": "idx_orders_tenant_status_created",
          "direction": "forward"
        }
      }
    }
  },
  "executionStats": {
    "nReturned": 20,
    "executionTimeMillis": 4,
    "totalKeysExamined": 24,
    "totalDocsExamined": 20
  }
}
~~~

Các giá trị `4`, `24`, `20` là **số liệu giả định để học cách đọc plan**, không phải benchmark hay đầu ra cam kết của một phiên bản MongoDB. Ở một server dùng SBE, `winningPlan` có thể nằm dưới `queryPlanner.winningPlan.queryPlan` và kèm `slotBasedPlan`; những trường hợp có shard/aggregation có thể có cấu trúc lồng khác.

Ở ví dụ này, MongoDB dùng `IXSCAN` trên index phù hợp, chỉ đọc khoảng vài chục khóa, lấy 20 document và trả về 20 kết quả. Sự xuất hiện của `FETCH` là bình thường khi truy vấn cần các trường không có đủ trong index. Không phải mọi truy vấn tốt đều có `totalDocsExamined = 0`.

## 4. Đọc các stage thường gặp

| Stage / dấu hiệu | Ý nghĩa | Câu hỏi khi điều tra |
| --- | --- | --- |
| `COLLSCAN` | Quét document trong collection | Có thể dùng index phù hợp với filter không, hay quét toàn collection thực sự rẻ hơn? |
| `IXSCAN` | Duyệt các entry trong index | `indexBounds` có hẹp không? `keysExamined` có lớn hơn nhiều so với `nReturned`? |
| `FETCH` | Lấy document thật để kiểm tra/đọc thêm dữ liệu | Có nhiều document bị lọc lại sau khi FETCH? Có cần covered query không? |
| `SORT` | Có bước sắp xếp ngoài thứ tự index đang duyệt | Có thể chọn compound index hỗ trợ sort không? Kích thước tập phải sort là bao nhiêu? |
| `LIMIT` / `SKIP` | Giới hạn kết quả hoặc bỏ qua một số kết quả | Phân trang sâu bằng `skip` có khiến MongoDB phải duyệt quá nhiều key không? |
| `PROJECTION_COVERED` hoặc dấu hiệu equivalent | Dữ liệu trả về đủ từ index theo engine đang dùng | Có thể loại bỏ `FETCH` và giữ `totalDocsExamined = 0` không? |
| `OR` / các stage hợp nhất nhánh | Kết hợp kết quả nhiều nhánh | Mỗi nhánh có index thích hợp chưa? |
| `SHARD_MERGE` và các stage liên quan shard | Tổng hợp kết quả từ các shard | Truy vấn có nhắm đúng shard hay phải fan-out? |

Stage `SORT` **không luôn là lỗi**: sort trên tập nhỏ có thể rẻ hơn việc duy trì thêm một index lớn. `COLLSCAN` cũng có thể hợp lý với collection nhỏ hoặc truy vấn trả phần lớn collection. Điều cần đánh giá là **lượng công việc và độ trễ so với nhu cầu thực tế**, không phải cố loại bỏ mọi tên stage bị cho là xấu.

### `indexBounds` và compound index

Với index `{ tenantId: 1, status: 1, createdAt: -1 }`, truy vấn ví dụ có hai điều kiện bằng (`tenantId`, `status`) và một khoảng thời gian (`createdAt`). MongoDB có thể giới hạn vùng index theo tenant, trạng thái và khoảng ngày, đồng thời đọc theo thứ tự `createdAt` giảm dần mà không cần sort riêng.

Nếu index chỉ là `{ tenantId: 1 }`, MongoDB vẫn có thể phải đọc rất nhiều đơn của tenant, lọc `status` và `createdAt`, rồi sort phần còn lại. `IXSCAN` xuất hiện **chưa đủ** để kết luận index tốt; hãy xem phạm vi quét và các số đếm thực tế.

## 5. Thử nghiệm trước và sau khi bổ sung index

Chạy truy vấn thực tế dưới hai điều kiện giống nhau: cùng dữ liệu, filter, sort, limit, projection, collation và môi trường. Bắt đầu bằng cách xem index đang tồn tại:

~~~javascript
db.orders.getIndexes();
~~~

Sau đó chạy truy vấn và lưu lại các số liệu `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, winning plan. Nếu chưa có index phù hợp, cân nhắc tạo compound index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_orders_tenant_status_created" }
);
~~~

Chạy lại `explain("executionStats")` với chính xác truy vấn trước đó. So sánh ví dụ **giả lập**:

| Chỉ số | Trước (thiếu index phù hợp) | Sau (compound index) |
| --- | ---: | ---: |
| Plan chính | `COLLSCAN` + `SORT` | `IXSCAN` + `FETCH` |
| `nReturned` | 20 | 20 |
| `totalKeysExamined` | 0 | 24 |
| `totalDocsExamined` | 120.000 | 20 |
| `executionTimeMillis` | 165 ms | 4 ms |

Ở tình huống minh họa này, index giúp thu hẹp số document phải đọc và cung cấp thứ tự sort. Nhưng **đừng lấy các con số giả lập làm mục tiêu bắt buộc**. Với truy vấn thực tế, tập dữ liệu, phân bố giá trị, cache và tải hệ thống sẽ quyết định mức cải thiện. Một compound index có thể giúp query đọc nhanh hơn nhưng cũng tăng dung lượng lưu trữ, chi phí ghi và thời gian xây dựng index.

### Chọn thứ tự field của index

Với nhiều truy vấn kết hợp equality, sort và range, quy tắc tham khảo là **Equality → Sort → Range (ESR)**. Ví dụ trên phù hợp với điều kiện bằng trên `tenantId`, `status` và sort/range theo `createdAt`.

Tuy nhiên ESR không phải công thức tuyệt đối. Điều kiện range rất chọn lọc, query khác dùng cùng collection, hướng sort, index partial, multikey, collation và giới hạn ghi có thể khiến thứ tự khác tốt hơn. Luôn xác nhận lại bằng kế hoạch và dữ liệu đại diện. Nếu dùng index partial, filter truy vấn phải thỏa điều kiện cần thiết để optimizer có thể sử dụng index đó; index sparse và multikey cũng có các giới hạn riêng.

## 6. Covered query và chi phí đọc document

Nếu câu truy vấn chỉ lọc, sort và trả về các trường đã có trong index, MongoDB có thể trả kết quả mà không đọc document gốc. Đây là **covered query**. Với index `{ tenantId: 1, status: 1, createdAt: -1 }`, thử:

~~~javascript
db.orders.find(
  { tenantId: "T01", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1 })
 .limit(20)
 .explain("executionStats");
~~~

Nếu các điều kiện hỗ trợ covered query và plan thực sự dùng index này, `totalDocsExamined` có thể bằng `0`. Việc khai báo `{ _id: 0 }` là quan trọng khi `_id` không có trong index, vì projection mặc định của `find` có thể bao gồm `_id`.

Không nên cố ép mọi truy vấn thành covered query: bổ sung quá nhiều field vào index làm index phình to và tăng chi phí ghi. Chỉ tối ưu khi số liệu cho thấy việc lấy document gốc là nút thắt và query shape ổn định.

## 7. Dùng `explain` từ ứng dụng Spring Data MongoDB

Trong hệ thống thực tế, truy vấn thường bắt đầu bằng `Criteria`, `Query`, `MongoTemplate`, repository, query derivation hoặc aggregation API. Để tái hiện kế hoạch chính xác, phải kiểm tra **BSON được gửi tới MongoDB**, kể cả field mapping (`@Field`), kiểu BSON, projection, sort, limit, skip, collation và hint (nếu có).

Ví dụ code ứng dụng dùng `MongoTemplate`:

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderReadService {
    private final MongoTemplate template;

    public OrderReadService(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> newestPaidOrders(String tenantId, Instant since) {
        Query query = new Query()
            .addCriteria(Criteria.where("tenantId").is(tenantId)
                .and("status").is("PAID")
                .and("createdAt").gte(Date.from(since)))
            .with(Sort.by(Sort.Direction.DESC, "createdAt"))
            .limit(20);

        return template.find(query, Order.class, "orders");
    }
}
~~~

Ở đây `Order` là entity `@Document` của ứng dụng; các field Java phải map tới field MongoDB tương ứng. Đoạn code giả định `tenantId`, `status`, `createdAt` có cùng tên ở Java và BSON, `createdAt` được lưu dưới kiểu BSON Date.

Để xem `executionStats` bằng cùng kết nối ứng dụng, có thể dùng **MongoDB Java Driver** thông qua callback `MongoTemplate.execute`:

~~~java
import java.time.Instant;
import java.util.Date;
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class OrderExplainService {
    private final MongoTemplate template;

    public OrderExplainService(MongoTemplate template) {
        this.template = template;
    }

    public Document explainNewestPaidOrders(String tenantId, Instant since) {
        return template.execute("orders", collection ->
            collection.find(Filters.and(
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("status", "PAID"),
                    Filters.gte("createdAt", Date.from(since))
                ))
                .sort(Sorts.descending("createdAt"))
                .limit(20)
                .explain(ExplainVerbosity.EXECUTION_STATS)
        );
    }
}
~~~

`MongoTemplate.execute` mở truy cập collection qua driver; ví dụ này xây dựng filter BSON **thủ công**, nên không tự áp dụng ánh xạ `@Field` từ entity như `MongoTemplate.find`. Nếu ứng dụng dùng `@Field("created_at")`, converter riêng, `@Query`, soft-delete filter hoặc collation, phải chuyển các chi tiết đó vào truy vấn explain tương ứng. Giải thích một query khác query production sẽ dẫn đến kết luận sai dù kết quả nhìn hợp lý.

Chỉ gọi chẩn đoán dạng này từ công cụ nội bộ, môi trường kiểm thử hoặc tuyến quản trị được kiểm soát. Tránh để một API công khai tùy ý chạy `executionStats` theo điều kiện đầu vào không giới hạn, vì phân tích có thể gây tốn tài nguyên tương đương truy vấn nặng.

### Phân tích truy vấn do repository sinh ra

Khi dùng method derivation như `findTop20ByTenantIdAndStatusAndCreatedAtAfterOrderByCreatedAtDesc`, cần đối chiếu câu lệnh thực được driver gửi, thay vì suy đoán từ tên method. Bật log phù hợp trong môi trường kiểm thử hoặc dùng cơ chế quan sát command của driver, đọc filter, projection, sort, limit, collation và read preference; sau đó đưa **cùng query shape** vào `mongosh` hoặc callback driver. Không ghi log giá trị nhạy cảm của query ở môi trường production.

## 8. Xem `explain` với aggregation pipeline

Với Spring Data MongoDB, `Aggregation` và `MongoTemplate.aggregate` có thể tạo pipeline nhiều stage. `explain` giúp đánh giá `$match` đã được đẩy sớm chưa, `$sort` có dùng index được không và `$group`/`$lookup` tốn tài nguyên ở đâu.

Ví dụ trong `mongosh`:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "T01", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 },
  { $project: { _id: 0, customerId: 1, totalMinor: 1, createdAt: 1 } }
]);
~~~

MongoDB có thể tối ưu hoặc sắp xếp lại các stage theo quy tắc của optimizer, vì vậy kế hoạch thực thi **không nhất thiết sao chép nguyên thứ tự pipeline bạn viết**. Khi `$match` và `$sort` được đẩy xuống phần truy vấn sử dụng index, kết quả explain có thể hiển thị ở các vùng `queryPlanner`, `$cursor`, execution stats hoặc khu vực riêng của shard/SBE tùy phiên bản.

Với aggregation, đặc biệt lưu ý số document đi qua từng stage, các thao tác `$group` và `$lookup`, lượng bộ nhớ sử dụng, spill ra đĩa (khi có số liệu tương ứng) và giới hạn kết quả. `executionStats` của một `find` đơn giản không thể đại diện cho toàn bộ pipeline nếu logic chính nằm ở các stage aggregation phía sau.

## 9. Các tình huống khiến kế hoạch khác kỳ vọng

### Có index nhưng MongoDB vẫn chọn `COLLSCAN`

Điều này có thể hợp lý khi collection nhỏ, query trả phần lớn dữ liệu hoặc index không hỗ trợ tốt filter/sort. Hãy kiểm tra `getIndexes()`, điều kiện thực, `indexBounds`, collation, kiểu dữ liệu và độ chọn lọc. Thử nghiệm với `hint()` **chỉ để đối chiếu trên môi trường phù hợp**, rồi so sánh thống kê; không đưa `hint` vào production như một phản xạ khi thấy planner không chọn index.

### `IXSCAN` xuất hiện nhưng `totalKeysExamined` vẫn rất lớn

Một index có thể chỉ giới hạn theo field đầu tiên rồi quét phần lớn key của tenant, hoặc field range và sort không phù hợp với thứ tự index. Cần xem `indexBounds` và các điều kiện được áp dụng sau `FETCH`, xem lại thứ tự field của compound index và tập query phải phục vụ.

### `SORT` xuất hiện dù đã tạo index

Index có thể không hỗ trợ sort trong query shape cụ thể, ví dụ có điều kiện range không tương thích phía trước field cần sort, sort khác thứ tự index, collation khác hoặc multikey làm hạn chế thứ tự có thể sử dụng. Kiểm tra `SORT` đang xử lý bao nhiêu kết quả và chi phí thực, rồi mới quyết định thêm index.

### `nReturned` ít, lượng quét lớn

Truy vấn hiếm dữ liệu có thể phải quét nhiều key mới tìm ra vài document phù hợp. Phân trang sâu bằng `skip(100000)` cũng có thể đòi duyệt nhiều kết quả rồi bỏ qua. Nếu giao diện phân trang theo thứ tự cố định, cân nhắc **keyset pagination** (ví dụ theo `createdAt` kèm `_id` làm khóa phá hòa) và compound index phù hợp.

### Thay đổi kiểu dữ liệu hoặc mapping làm index kém hiệu quả

Ví dụ `createdAt` có document lưu BSON Date, document khác lại lưu chuỗi; query dùng `Date` không có cùng ngữ nghĩa với chuỗi. Tương tự, Java `@Field("tenant_id")` sẽ tạo query vật lý khác chuỗi `"tenantId"` dùng trong callback driver. Kiểm tra dữ liệu thực và mapping trước khi kết luận index hoạt động sai.

### Plan tốt trên máy dev nhưng chậm ở production

Dev có thể có ít dữ liệu, phân bố `status` khác, cache ấm, ít kết nối hoặc không có shard. Trên production, index build, replication lag, lưu lượng ghi, shard targeting và cạnh tranh tài nguyên có thể chi phối latency. Cần đo trên dữ liệu đại diện và kết hợp số liệu từ ứng dụng, MongoDB profiler/slow query log và hệ thống giám sát được cấu hình phù hợp.

## 10. Quy trình chẩn đoán và xác minh sau tối ưu

Một quy trình hiệu quả có thể thực hiện tuần tự như sau:

1. **Chọn đúng truy vấn chậm:** lấy query shape thực tế từ ứng dụng Spring Data MongoDB, xác định endpoint, tỷ lệ gọi, p50/p95/p99, timeout và khối lượng dữ liệu.
2. **Tái hiện điều kiện:** giữ nguyên filter, sort, projection, limit, skip, collation, data type, read preference và môi trường dữ liệu đủ đại diện.
3. **Đọc `queryPlanner`:** xác định winning plan, indexName, các stage và `indexBounds`; kiểm tra truy vấn có đúng cấu trúc dự kiến hay không.
4. **Đọc `executionStats`:** ghi `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis` và các stage thực thi. Tìm nút thắt cụ thể như quét rộng, `FETCH` lọc lại nhiều hoặc sort nặng.
5. **Thử một thay đổi có giả thuyết:** bổ sung/chỉnh index, điều chỉnh projection, đưa `$match` sớm hơn, thay cách phân trang hoặc sửa schema/mapping.
6. **Chạy lại và so sánh:** dùng điều kiện tương đương, thử nhiều lần khi thích hợp, chú ý cache và biến động tải; không dựa vào một lần đo.
7. **Đo tại lớp ứng dụng:** xác nhận latency p95/p99, CPU, I/O, số kết nối, hiệu quả cache và ảnh hưởng của index mới lên insert/update/delete.
8. **Triển khai và theo dõi:** xây dựng index theo kế hoạch vận hành, quan sát query chậm, tải ghi, kích thước index và hiệu năng sau phát hành; sẵn sàng điều chỉnh nếu kết quả không như dự kiến.

### Mẫu bảng ghi nhận kết quả tối ưu

| Mục | Trước tối ưu | Sau tối ưu | Ghi chú |
| --- | --- | --- | --- |
| Query shape và tham số | Ghi lại | Giữ tương đương | Cùng filter/sort/limit/collation |
| Winning plan | `COLLSCAN`, `SORT`... | `IXSCAN`, `FETCH`... | Ghi index và stage thực tế |
| `nReturned` | ... | ... | Đảm bảo tương đồng về kết quả |
| `totalKeysExamined` | ... | ... | So sánh vùng quét index |
| `totalDocsExamined` | ... | ... | So sánh lượng document được đọc |
| `executionTimeMillis` | ... | ... | Thời gian theo explain, chỉ tham khảo |
| p95 của thao tác Spring Data | ... | ... | Quan sát bằng đo lường ứng dụng |
| Ảnh hưởng ghi/index size | ... | ... | Không đánh đổi quá lớn để tối ưu một query |

## 11. Kết luận thực hành

`queryPlanner` cho biết **MongoDB định thực hiện truy vấn bằng kế hoạch nào**; `executionStats` bổ sung **kế hoạch đó đã kiểm tra bao nhiêu key, bao nhiêu document và trả bao nhiêu kết quả**. Một `IXSCAN` không tự động là tốt, một `COLLSCAN` không tự động là xấu, và vài mili giây ghi trong `explain` không thay thế được latency thực tế của ứng dụng.

Với Spring Data MongoDB, hãy bắt đầu từ đúng filter/sort/projection mà `MongoTemplate` hoặc repository gửi xuống MongoDB, xem kế hoạch, xác định chi phí đang nằm ở đâu, rồi thử index hoặc thay đổi truy vấn theo một giả thuyết rõ ràng. **Đọc `explain` cùng `executionStats`, sau đó kiểm chứng bằng số liệu ứng dụng** là cách ra quyết định tối ưu có cơ sở và tránh tạo index dư thừa.
