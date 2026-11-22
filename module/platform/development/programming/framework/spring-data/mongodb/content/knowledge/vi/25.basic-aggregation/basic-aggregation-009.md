# Ánh xạ kết quả vào DTO và đọc kết quả Document thô

## 1. Khi aggregation không còn trả về hình dạng document ban đầu

Trong chương **Aggregation cơ bản** của **Spring Data MongoDB**, một pipeline thường bắt đầu bằng `$match`, tiếp tục bằng `$group`, `$project` và `$sort`. Điểm khác truy vấn `find` thông thường là **hình dạng document sau pipeline có thể không giống entity nguồn**.

Ví dụ collection `sales_orders` chứa các đơn hàng:

~~~json
{
  "_id": "o-101",
  "tenantId": "tenant-a",
  "status": "PAID",
  "region_code": "HCM",
  "amount_vnd": 120000,
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Báo cáo doanh thu theo vùng lại cần mỗi vùng một dòng:

~~~json
{
  "regionCode": "HCM",
  "orderCount": 2,
  "revenueVnd": 200000
}
~~~

Không còn một đối tượng “đơn hàng” nào tương ứng với dòng kết quả đó. `regionCode` là khóa nhóm, `orderCount` là số đơn và `revenueVnd` là số tiền tổng hợp. Vì thế:

- **DTO/Java record** là kiểu nhận kết quả phù hợp khi cấu trúc báo cáo **đã được định nghĩa rõ ràng**.
- **`org.bson.Document`** phù hợp để khảo sát kết quả linh hoạt, debug BSON, làm việc với pipeline có cấu trúc thay đổi hoặc kiểm tra trường chưa đưa vào DTO.
- **`AggregationResults<T>`** chứa các kết quả đã được ánh xạ, đồng thời cho phép truy cập thông tin trả về thô ở cấp lệnh aggregation.

Nếu ánh xạ một dòng báo cáo vào `SalesOrder` chỉ vì pipeline đọc từ `sales_orders`, các field không còn trong kết quả có thể thành `null`/giá trị mặc định hoặc gây lỗi materialization. **Kiểu đầu ra phải phản ánh *output schema của pipeline*, không chỉ collection đầu vào.**

### Mục tiêu bài học

1. Tách bạch entity nguồn, BSON sau từng stage và DTO đích.
2. Dùng `MongoTemplate.aggregate(...)` và `AggregationResults<T>` để nhận record/class DTO.
3. Hiểu `getMappedResults()`, `getUniqueMappedResult()` và `getRawResults()`.
4. Đọc kết quả theo từng document bằng `AggregationResults<Document>` mà không nhầm với **raw command reply**.
5. Xử lý `_id` của `$group`, `$project`, alias, `@Field` và kiểu dữ liệu BSON.
6. Kiểm thử bằng MongoDB thật để chứng minh cả kết quả DTO lẫn cấu trúc Document và hiệu năng.

> Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB tương thích. Một số overload, kiểu mapping và chi tiết metadata có thể thay đổi giữa phiên bản. Khi ứng dụng đang sử dụng phiên bản khác, cần kiểm tra API và integration test thay vì suy từ tên lớp.

## 2. Ba lớp dữ liệu: source entity, output document và DTO

| Lớp dữ liệu | Định nghĩa | Hình dạng mẫu |
|---|---|---|
**Source entity** | Document đang lưu; mapping bởi `@Document`/`@Field` | `SalesOrder`: `id`, `tenantId`, `status`, `regionCode`, `amountVnd` |
**BSON kết quả của pipeline** | Document MongoDB trả sau `$group`/`$project` | `{ regionCode, orderCount, revenueVnd }` |
**DTO đích** | Object Java tạo từ kết quả pipeline | `RegionRevenueDto` record hoặc `RegionRevenueClassDto` |

Luồng dữ liệu khái niệm:

~~~mermaid
flowchart TD
    A["Collection sales_orders"] --> B["Entity metadata: @Document, @Field"]
    B --> C["$match: lọc tenant và PAID"]
    C --> D["$group: _id và các accumulator"]
    D --> E["$project: đặt alias output"]
    E --> F["$sort: xếp hạng"]
    F --> G["BSON document kết quả"]
    G --> H["MappingConverter"]
    H --> I["RegionRevenueDto"]
    G --> J["org.bson.Document"]
    F --> K["AggregationResults: dữ liệu và raw reply"]
~~~

**Lưu ý:** `$group` có thể thay thế cấu trúc một-nhiều document đầu vào thành một document cho mỗi nhóm. `$project` có thể đặt tên lại, tính biểu thức và loại trường. Vì vậy kết quả cuối không còn cần mang toàn bộ field của entity nguồn.

Phân biệt hai câu hỏi:

- “**MongoDB đã tạo ra những field nào?**” → xem output BSON hoặc `Document`.
- “**Ứng dụng muốn dùng kiểu Java nào để biểu diễn các field đó?**” → thiết kế DTO và kiểm thử conversion.

## 3. Entity nguồn và dữ liệu dùng chung

Ta dùng collection `sales_orders`; mỗi document đại diện cho một đơn hàng đã hoặc chưa thanh toán. Trong ví dụ, số tiền là **số nguyên VND**; một hệ thống tiền tệ đa đơn vị hoặc có phần lẻ phải thiết kế Decimal128/BigDecimal và quy tắc làm tròn phù hợp.

**SalesOrder.java**

~~~java
package com.example.sales;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "sales_orders")
public record SalesOrder(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String status,
        @Field("region_code") String regionCode,
        @Field("amount_vnd") long amountVnd,
        Instant createdAt) {
}
~~~

Metadata trên entity:

- Property Java `id` tương ứng BSON `_id`; `@MongoId(FieldType.STRING)` giữ ID lưu kiểu BSON String.
- Property Java `regionCode` tương ứng BSON `region_code`.
- Property Java `amountVnd` tương ứng BSON `amount_vnd`.
- `tenantId` và `status` có cùng tên trong Java và BSON.
- `createdAt` dùng `Instant`; conversion và độ chính xác thời gian phải tuân theo cấu hình Spring Data và BSON Date.

Ta có năm document mẫu:

| ID | tenantId | status | region_code | amount_vnd |
|---|---|---|---|---:|
| `o-101` | `tenant-a` | `PAID` | `HCM` | 120.000 |
| `o-102` | `tenant-a` | `PAID` | `HCM` | 80.000 |
| `o-103` | `tenant-a` | `PAID` | `HN` | 50.000 |
| `o-104` | `tenant-a` | `CANCELLED` | `HN` | 999.000 |
| `o-105` | `tenant-b` | `PAID` | `HCM` | 700.000 |

Báo cáo “doanh thu đơn PAID của tenant-a” phải có **hai dòng**, không lấy đơn CANCELLED và không lộ đơn của tenant-b:

| regionCode | orderCount | revenueVnd |
|---|---:|---:|
| `HCM` | 2 | 200.000 |
| `HN` | 1 | 50.000 |

Kết quả này sẽ là chuẩn để so sánh DTO và Document ở các phần sau.

## 4. Định nghĩa DTO đích bằng Java record

Khi API đã biết ba field của một báo cáo, record diễn đạt hợp đồng gọn:

**RegionRevenueDto.java**

~~~java
package com.example.sales;

public record RegionRevenueDto(
        String regionCode,
        long orderCount,
        long revenueVnd) {
}
~~~

Spring Data dùng metadata của record để materialize đối tượng bằng canonical constructor khi đường mapping/phiên bản hỗ trợ. Accessor là `regionCode()`, `orderCount()` và `revenueVnd()`, **không phải** `getRegionCode()`.

Ví dụ:

~~~java
RegionRevenueDto row =
        new RegionRevenueDto("HCM", 2L, 200000L);

String code = row.regionCode();
long count = row.orderCount();
long sum = row.revenueVnd();
~~~

Ưu điểm:

- Có tên field rõ ràng, tránh code phía service phải gọi `Document.get(...)` ở mọi nơi.
- Bất biến nông, không có setter vô tình thay đổi kết quả.
- Tự có `equals`/`hashCode` theo giá trị, tiện cho kiểm thử.
- Dễ tạo DTO phản hồi API mà không lộ metadata document nguồn.

**Hạn chế:** record không tự bảo đảm schema ở MongoDB hợp lệ. Nếu pipeline thiếu `regionCode`, document output có giá trị không khớp kiểu, hoặc `revenueVnd` là null nhưng DTO khai báo primitive `long`, mapping có thể lỗi hoặc mang giá trị không mong muốn tùy cấu hình. **Phải kiểm tra output BSON, không chỉ nhìn kiểu DTO.**

### 4.1. DTO class có constructor cũng dùng được

Record không phải lựa chọn duy nhất. Một class DTO tường minh:

**RegionRevenueClassDto.java**

~~~java
package com.example.sales;

import org.springframework.data.annotation.PersistenceCreator;

public final class RegionRevenueClassDto {
    private final String regionCode;
    private final long orderCount;
    private final long revenueVnd;

    @PersistenceCreator
    public RegionRevenueClassDto(
            String regionCode, long orderCount, long revenueVnd) {
        this.regionCode = regionCode;
        this.orderCount = orderCount;
        this.revenueVnd = revenueVnd;
    }

    public String getRegionCode() { return regionCode; }
    public long getOrderCount() { return orderCount; }
    public long getRevenueVnd() { return revenueVnd; }
}
~~~

Class DTO cần constructor mapping phù hợp. `@PersistenceCreator` hữu ích khi class có nhiều constructor để Spring Data biết phải chọn constructor nào; nếu chỉ có một constructor, annotation thường không bắt buộc. Với class Java thường, việc giữ tên tham số bằng compiler option `-parameters` giúp constructor binding dựa vào tên property.

Không thêm `@Document(collection = "sales_orders")` cho một DTO tổng hợp chỉ vì kết quả xuất phát từ collection đó. DTO là **hình dạng đầu ra**, không phải aggregate root để gọi `save`.

## 5. Xây pipeline $match → $group → $project → $sort

Trước khi viết Java, ta xác định MongoDB pipeline mong muốn:

~~~javascript
db.sales_orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$region_code",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$amount_vnd" }
    }
  },
  {
    $project: {
      _id: 0,
      regionCode: "$_id",
      orderCount: 1,
      revenueVnd: 1
    }
  },
  {
    $sort: { revenueVnd: -1, regionCode: 1 }
  }
]);
~~~

### 5.1. Từng stage thay đổi dữ liệu ra sao?

| Stage | Hình dạng và ý nghĩa |
|---|---|
`$match` | Giữ đơn `tenant-a` và `PAID`; document vẫn có `_id`, `region_code`, `amount_vnd`, ... |
`$group` | Tạo một document theo từng khóa vùng: `{ "_id": "HCM", "orderCount": 2, "revenueVnd": 200000 }` |
`$project` | Đổi `_id` nhóm thành `regionCode` và loại `_id` khỏi output |
`$sort` | Sắp xếp vùng theo doanh thu giảm dần, sau đó theo mã vùng |

**Điểm dễ quên:** `$group` xuất khóa nhóm ở trường `_id`, **không tự xuất field `regionCode`**. Để record có component `regionCode`, cần `$project` hoặc alias tương ứng ở output.

Các stage nhìn kết quả stage trước, vì vậy `$sort` ở cuối phải sort theo field **đang tồn tại ở output**. Nếu `$project` loại `revenueVnd` rồi vẫn sort theo nó, câu lệnh không còn thể hiện ý định ban đầu.

### 5.2. $match trước $group: đúng và thường hiệu quả hơn

Đưa điều kiện tenant/status vào `$match` trước nhóm giúp server giảm số document đi qua `$group`, và có thể tận dụng index. Nếu filter tenant chỉ được thêm sau `$group`, metadata tenant đã có thể mất, tổng hợp sai phạm vi và có nguy cơ rò dữ liệu chéo tenant.

Đừng dùng một điều kiện tenant trong Java **sau khi đã nhận báo cáo nhóm tổng hợp của nhiều tenant**. Khi đó số tiền đã trộn ngay tại server; lọc response không thể khôi phục tính đúng đắn hay bảo mật.

## 6. MongoTemplate.aggregate trả DTO

Đây là phiên bản Java đầy đủ của pipeline mục 5. Ta sử dụng dạng `aggregate(aggregation, SalesOrder.class, RegionRevenueDto.class)` để Spring Data biết **entity nguồn** và **kiểu đích**.

**RegionSalesReportService.java**

~~~java
package com.example.sales;

import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Service
public class RegionSalesReportService {
    private final MongoTemplate mongo;

    public RegionSalesReportService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    private Aggregation revenuePipeline(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId không hợp lệ");
        }

        return newAggregation(
                match(Criteria.where("tenantId").is(tenantId)
                        .and("status").is("PAID")),
                group("regionCode")
                        .count().as("orderCount")
                        .sum("amountVnd").as("revenueVnd"),
                project("orderCount", "revenueVnd")
                        .and("_id").as("regionCode")
                        .andExclude("_id"),
                sort(Sort.by(
                        Sort.Order.desc("revenueVnd"),
                        Sort.Order.asc("regionCode"))));
    }

    public AggregationResults<RegionRevenueDto> typed(
            String tenantId) {
        return mongo.aggregate(
                revenuePipeline(tenantId),
                SalesOrder.class,
                RegionRevenueDto.class);
    }

    public AggregationResults<Document> documents(
            String tenantId) {
        return mongo.aggregate(
                revenuePipeline(tenantId),
                SalesOrder.class,
                Document.class);
    }

    public List<RegionRevenueClassDto> classDtos(
            String tenantId) {
        return mongo.aggregate(
                revenuePipeline(tenantId),
                SalesOrder.class,
                RegionRevenueClassDto.class)
                .getMappedResults();
    }
}
~~~

Điểm đáng chú ý:

1. `revenuePipeline` tạo **aggregation pipeline**, chưa tự gửi query đến MongoDB.
2. `group("regionCode")` và `sum("amountVnd")` sử dụng **property Java** của entity nguồn; khi thực thi typed aggregation, Spring Data dùng metadata mapping để tham chiếu BSON `region_code` và `amount_vnd`.
3. `project(...).and("_id").as("regionCode")` tạo tên field đầu ra khớp DTO.
4. `andExclude("_id")` không trả khóa nhóm dưới tên `_id` nữa; DTO chỉ cần `regionCode`.
5. `sort(...)` áp dụng trên **output field** của stage projection.
6. Kết quả có thể được materialize thành Java record, class DTO hoặc `Document` **từ cùng một logic pipeline**.

**Lưu ý về overload:** Nếu dùng overload `aggregate(aggregation, "sales_orders", RegionRevenueDto.class)` chỉ có **tên collection** thay vì source entity type, cơ chế ánh xạ đường dẫn property Java sang `@Field` của `SalesOrder` có thể không có đủ metadata. Khi pipeline viết theo property Java, ưu tiên overload có `SalesOrder.class` và kiểm tra BSON sinh ra.

### 6.1. Đọc danh sách DTO

~~~java
AggregationResults<RegionRevenueDto> results =
        reportService.typed("tenant-a");

List<RegionRevenueDto> rows =
        results.getMappedResults();

for (RegionRevenueDto row : rows) {
    System.out.println(
            row.regionCode() + ": " +
            row.orderCount() + " đơn, " +
            row.revenueVnd() + " VND");
}
~~~

`reportService` là bean kiểu `RegionSalesReportService`. Với dữ liệu mục 3, output mong muốn:

~~~text
HCM: 2 đơn, 200000 VND
HN: 1 đơn, 50000 VND
~~~

`getMappedResults()` trả danh sách các đối tượng **đã được Spring Data ánh xạ**. Khi pipeline không có dòng nào, danh sách thường rỗng; không nên mặc định là một DTO chứa toàn giá trị 0. Với aggregation có `$group`, một tập nguồn rỗng thường không sinh dòng nhóm, nên cần định nghĩa semantics nếu API muốn một dòng zero-total.

## 7. AggregationResults<T>: getMappedResults và getUniqueMappedResult

`AggregationResults<T>` là wrapper quan trọng của `MongoTemplate.aggregate(...)`. Hai phương thức thường dùng:

| Phương thức | Kết quả | Phù hợp |
|---|---|---|
`getMappedResults()` | `List<T>` gồm tất cả các document đã chuyển thành `T` | Báo cáo theo vùng, danh sách nhóm, ranking |
`getUniqueMappedResult()` | Một `T` hoặc `null` khi không có kết quả; nhiều kết quả không đáp ứng hợp đồng unique | Báo cáo tổng hợp toàn tenant cần tối đa một dòng |
`getRawResults()` | `org.bson.Document` chứa phản hồi thô ở cấp lệnh aggregation | Chẩn đoán metadata/lệnh, không phải danh sách DTO |

**Không nên gọi `getUniqueMappedResult()`** trên pipeline báo cáo theo vùng nếu có thể có hai hoặc nhiều vùng. Contract của phương thức yêu cầu kết quả duy nhất và có thể ném lỗi khi nhiều document được trả về.

### 7.1. Một pipeline chỉ trả một dòng tổng hợp

Nếu cần báo cáo tổng số đơn và doanh thu của cả tenant, **không nhóm theo vùng**:

**TotalRevenueDto.java**

~~~java
package com.example.sales;

public record TotalRevenueDto(
        long orderCount,
        long revenueVnd) {
}
~~~

Phương thức bổ sung trong service:

~~~java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

public TotalRevenueDto totalForTenant(String tenantId) {
    Aggregation pipeline = newAggregation(
            match(Criteria.where("tenantId").is(tenantId)
                    .and("status").is("PAID")),
            group()
                    .count().as("orderCount")
                    .sum("amountVnd").as("revenueVnd"),
            project("orderCount", "revenueVnd")
                    .andExclude("_id"));

    AggregationResults<TotalRevenueDto> results =
            mongo.aggregate(pipeline, SalesOrder.class, TotalRevenueDto.class);

    return results.getUniqueMappedResult();
}
~~~

Đây là đoạn method **bổ sung vào `RegionSalesReportService`** có field `mongo`; không phải tệp class Java độc lập. `group()` không có field nhóm tạo một nhóm toàn bộ tập đầu vào; `$project` chỉ giữ hai giá trị tổng hợp.

Nếu không có đơn nào khớp, `$group` có thể trả **không dòng nào**, nên `getUniqueMappedResult()` có thể là `null`. Tầng service cần chính sách rõ: trả `null`, `Optional.empty()` hoặc DTO zero-total do ứng dụng tạo. Đừng để API thay đổi ngầm giữa `null` và object 0 mà không có hợp đồng.

### 7.2. Số lượng dòng không đồng nghĩa số lượng document nguồn

Một báo cáo theo vùng trả **hai DTO** không có nghĩa chỉ có hai đơn hàng thỏa `$match`. Trên dữ liệu mẫu, có **ba đơn PAID** của tenant-a nhưng chỉ hai **nhóm**. Khi đánh giá số lượng:

- `rows.size() == 2` là số **document đầu ra của pipeline**.
- Tổng `orderCount` trong hai dòng bằng 3 là số đơn đã được nhóm.
- Số document nguồn phải được suy từ accumulator phù hợp hoặc truy vấn count riêng, không từ số dòng DTO.

## 8. Document thô ở cấp dòng kết quả

Nếu chưa quyết định DTO, hoặc cần kiểm tra trực tiếp các field do aggregation tạo ra, ta có thể trả `AggregationResults<org.bson.Document>`:

~~~java
AggregationResults<Document> rawRowsResult =
        reportService.documents("tenant-a");

List<Document> rows = rawRowsResult.getMappedResults();

for (Document row : rows) {
    String region = row.getString("regionCode");
    Object count = row.get("orderCount");
    Object revenue = row.get("revenueVnd");

    System.out.println(region + " / " + count + " / " + revenue);
}
~~~

Trong ví dụ, `reportService.documents(...)` đã gọi `aggregate(..., SalesOrder.class, Document.class)`. Vì **kiểu đích là `Document.class`**, mỗi phần tử của `getMappedResults()` là một document **sau pipeline**, ví dụ:

~~~json
{
  "regionCode": "HCM",
  "orderCount": 2,
  "revenueVnd": 200000
}
~~~

Điểm này khác `SalesOrder` ban đầu: không có `tenantId`, `status`, `amount_vnd`; chúng đã bị lược bỏ hoặc tổng hợp.

### 8.1. Đọc số bằng Number, đừng đoán Int32 hay Int64

Kết quả `$sum: 1` hoặc `$sum: "$amount_vnd"` có thể mang kiểu BSON số khác nhau tùy dữ liệu đầu vào, phạm vi giá trị và phép tính. Không nên mặc định:

~~~java
long count = row.getLong("orderCount"); // Có thể lỗi nếu BSON là Int32.
~~~

Cách linh hoạt hơn khi nghiệp vụ kỳ vọng số nguyên:

~~~java
Object countValue = row.get("orderCount");
if (!(countValue instanceof Number countNumber)) {
    throw new IllegalStateException("orderCount không phải số");
}

long count = countNumber.longValue();
~~~

Tuy nhiên `Number.longValue()` có thể làm mất phần lẻ hoặc tràn phạm vi nếu dữ liệu không thuộc miền số nguyên 64-bit. Trong code production phải **kiểm tra kiểu và miền giá trị** trước khi chuyển đổi; ví dụ với Decimal128 cần chuyển sang `BigDecimal` thay vì `longValue()` mù quáng.

### 8.2. Document là cấu trúc động

`Document` cho phép:

~~~java
String region = row.getString("regionCode");
boolean hasRevenue = row.containsKey("revenueVnd");
Object rawRevenue = row.get("revenueVnd");
String diagnosticJson = row.toJson();
~~~

`toJson()` tiện để debug cấu trúc, nhưng có thể dùng biểu diễn Extended JSON cho một số BSON types. Nó **không thay thế JSON contract của API**, và không nên log nguyên document nếu chứa email, token, dữ liệu tài chính hay thông tin tenant nhạy cảm.

Khi pipeline thay đổi tên field, `row.get("revenueVnd")` sẽ trả `null` nếu field không tồn tại. Trên DTO primitive, sai lệch đó có thể bị phát hiện ở giai đoạn materialization theo đường mapping; với `Document`, nguy cơ **âm thầm chấp nhận thiếu field** cao hơn nếu không validate.

## 9. getRawResults không phải getMappedResults<Document>

Hai khái niệm thường bị gọi chung là “raw” nhưng không đồng nhất:

~~~java
AggregationResults<RegionRevenueDto> typed =
        reportService.typed("tenant-a");

// 1) Những dòng kết quả đã được ánh xạ thành DTO.
List<RegionRevenueDto> dtoRows = typed.getMappedResults();

// 2) Phản hồi BSON thô của lệnh aggregation ở cấp server/driver.
Document commandReply = typed.getRawResults();
~~~

`getRawResults()` trả một `Document` đại diện cho **phản hồi thô** mà Spring Data giữ lại, có thể chứa metadata như `ok` và cấu trúc cursor hoặc các field tùy phiên bản/protocol. Nó **không phải** một `Document` duy nhất của báo cáo vùng, và cũng không nên được xem là một API ổn định để duyệt toàn bộ batch kết quả bằng các key tự đoán.

Để đọc **từng dòng BSON output**, dùng:

~~~java
List<Document> dataRows =
        reportService.documents("tenant-a")
                .getMappedResults();
~~~

Để đọc **mỗi dòng dưới dạng DTO**:

~~~java
List<RegionRevenueDto> mappedRows =
        reportService.typed("tenant-a")
                .getMappedResults();
~~~

Để quan sát **lệnh MongoDB được gửi xuống server**, `getRawResults()` chưa chắc đáp ứng mục tiêu. Khi đó hãy dùng MongoDB Java Driver `CommandListener` trong môi trường test, hoặc công cụ profiler/explain được cho phép, để kiểm tra pipeline BSON thực sự.

### 9.1. Tại sao không tách cursor.firstBatch bằng tay?

Nếu code ứng dụng phụ thuộc `commandReply.get("cursor", ...).get("firstBatch")`, nó sẽ tự gắn chặt vào hình dạng protocol/cursor và cách Spring Data nhận kết quả. Những thay đổi ở driver, batch size hoặc response có thể gây lỗi dù `getMappedResults()` vẫn hoạt động bình thường.

Sử dụng API mức cao của `AggregationResults<T>` cho dữ liệu nghiệp vụ. Chỉ dùng raw command reply cho **chẩn đoán** đã được thiết kế để chịu thay đổi giữa các phiên bản.

## 10. $group._id, alias và constructor mapping

Đây là nguồn gây lỗi phổ biến nhất khi ánh xạ aggregation vào DTO.

### 10.1. Thiếu $project: chỉ có _id, không có regionCode

Pipeline:

~~~javascript
db.sales_orders.aggregate([
  { $match: { tenantId: "tenant-a", status: "PAID" } },
  {
    $group: {
      _id: "$region_code",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$amount_vnd" }
    }
  }
]);
~~~

Trả document:

~~~json
{
  "_id": "HCM",
  "orderCount": 2,
  "revenueVnd": 200000
}
~~~

Nhưng `RegionRevenueDto` chờ:

~~~java
public record RegionRevenueDto(
        String regionCode, long orderCount, long revenueVnd) {}
~~~

Trường `regionCode` chưa tồn tại trong BSON output. Tùy converter/constructor, component này có thể nhận `null` hoặc mapping có thể thất bại nếu có invariant. **Không suy rằng field nhóm `_id` tự động sẽ được bind vào component có tên `regionCode`.**

### 10.2. Cách sửa: alias rõ ràng sau khi group

~~~javascript
{
  $project: {
    _id: 0,
    regionCode: "$_id",
    orderCount: 1,
    revenueVnd: 1
  }
}
~~~

Tên field của **output document** bây giờ trùng với tên component của record. Khi cần field có tên khác vì hợp đồng API, hãy alias ở pipeline hoặc dùng DTO field/annotation mapping phù hợp và kiểm thử.

### 10.3. Alias là một phần của hợp đồng giữa pipeline và DTO

Một lỗi đặt tên như:

~~~javascript
{ $project: { region: "$_id", orderCount: 1, revenueVnd: 1 } }
~~~

không thể tự được giải quyết chỉ bằng việc Java record có `regionCode`. Giữa `region` và `regionCode` không có quan hệ mặc định. Với kết quả động hoặc dữ liệu nhiều loại report, cân nhắc một bước chuyển đổi tường minh; đừng đặt logic “đoán alias” rải rác trong controller.

## 11. Mapping @Field: input property khác output alias

Trong `SalesOrder`:

~~~java
@Field("region_code") String regionCode,
@Field("amount_vnd") long amountVnd,
~~~

Giả sử viết aggregation typed:

~~~java
Aggregation aggregation = newAggregation(
        group("regionCode")
                .sum("amountVnd").as("revenueVnd"));
~~~

Khi sử dụng `SalesOrder.class` làm **input type**, Spring Data MongoDB có thể ánh xạ tham chiếu property nguồn thành:

~~~javascript
{
  $group: {
    _id: "$region_code",
    revenueVnd: { $sum: "$amount_vnd" }
  }
}
~~~

Nhưng sau `$project`, field `regionCode` là **field output mới do pipeline tạo**, không còn là tham chiếu trực tiếp tới property nguồn ở mọi stage. Cần hiểu pipeline là một **chuỗi schema biến đổi**:

~~~text
Input:
    region_code, amount_vnd, tenantId, status

Sau $group:
    _id, revenueVnd, orderCount

Sau $project:
    regionCode, revenueVnd, orderCount
~~~

Do đó:

- `@Field` trên entity nguồn hướng dẫn các field **đang lưu trong MongoDB**.
- `as("regionCode")` xác định tên field **trong kết quả pipeline**.
- DTO/record đích phải tương thích tên/type **sau pipeline**.
- Nếu dùng raw stage `Document`, cần thận trọng vì các chuỗi path trong BSON raw có thể không trải qua cùng cơ chế mapping metadata như builder typed.

### 11.1. Input collection name thay cho input class

Ví dụ thiếu metadata nguồn:

~~~java
// Khi pipeline dùng tên property Java nhưng chỉ truyền collection name,
// cần xác minh mapper có đủ ngữ cảnh hay không.
mongo.aggregate(
        aggregation, "sales_orders", RegionRevenueDto.class);
~~~

Trong bài, ta ưu tiên:

~~~java
mongo.aggregate(
        aggregation, SalesOrder.class, RegionRevenueDto.class);
~~~

Lý do: overload với source entity type cho Spring Data biết chính xác mapping `regionCode -> region_code` và `amountVnd -> amount_vnd`. Nếu dự án bắt buộc dùng collection name, có thể tạo `TypedAggregation<SalesOrder>` hoặc viết pipeline theo **tên BSON vật lý** và kiểm thử.

Không trộn ngẫu nhiên `regionCode` và `region_code` qua các stage: làm vậy có thể khiến filter đúng nhưng group thành một nhóm null, hoặc projection bị thiếu trường.

## 12. BSON numeric types, null/missing và Decimal128

### 12.1. Tại sao kết quả sum/count cần kiểm thử kiểu?

MongoDB có các dạng BSON số như Int32, Int64, Double và Decimal128. Khi tính `$sum`:

- Một số nhỏ có thể được biểu diễn thành Int32 hoặc Int64 tùy toán tử và dữ liệu.
- Một phép toán có nguồn là Double/Decimal128 có thể tạo ra kiểu số tương ứng.
- Overflow, null, số quá lớn hoặc dữ liệu sai kiểu cần được xử lý theo semantics của MongoDB và hợp đồng nghiệp vụ.

Với DTO:

~~~java
public record RegionRevenueDto(
        String regionCode, long orderCount, long revenueVnd) {}
~~~

Spring Data converter có thể chuyển một BSON number phù hợp sang Java `long`. Nhưng nó không thể đảm bảo mọi dữ liệu đều thuộc miền `long`. Test giá trị lớn và kiểu dữ liệu thật thay vì chỉ với tổng vài nghìn đồng.

### 12.2. Document yêu cầu kiểm tra kiểu rõ ràng

~~~java
Document row = dataRows.get(0);

Object revenue = row.get("revenueVnd");
if (revenue instanceof Number number) {
    long value = number.longValue();
    // Chỉ hợp lệ khi nghiệp vụ đã bảo đảm số nguyên và không overflow.
} else {
    throw new IllegalStateException("revenueVnd không phải số");
}
~~~

Nếu báo cáo dùng Decimal128, có thể nhận `org.bson.types.Decimal128` và chuyển thành `BigDecimal`:

~~~java
import java.math.BigDecimal;
import org.bson.types.Decimal128;

Object value = row.get("revenueVnd");
if (value instanceof Decimal128 decimal) {
    BigDecimal exact = decimal.bigDecimalValue();
}
~~~

Không mặc định convert qua `double` rồi chuyển thành `BigDecimal` cho giá trị tài chính: số thực nhị phân có thể gây sai số.

### 12.3. Group key null và document thiếu field

Nếu một số đơn hàng có `region_code: null` hoặc không có trường `region_code`, `$group` theo region có thể tạo nhóm `_id: null`. Sau `$project`, DTO có `regionCode == null`. Ứng dụng phải quyết định:

- Từ chối/migrate document thiếu region.
- Cho phép nhóm `UNKNOWN` với chính sách rõ ràng.
- Lọc bỏ document thiếu region trước `$group` nếu báo cáo định nghĩa như vậy.

Không tự đổi `null` thành `"HCM"` hoặc cộng chung vào vùng khác chỉ vì DTO không chấp nhận null. Đặc biệt với báo cáo tài chính, việc loại một nhóm có thể làm tổng báo cáo không còn khớp tổng nguồn.

### 12.4. Giá trị thiếu hoặc sai kiểu trong $sum

Nếu `amount_vnd` thiếu hoặc không phải số, hành vi của accumulator `$sum` có quy tắc riêng và có thể khiến báo cáo bỏ qua đóng góp hoặc sinh kết quả không mong muốn. Khi dữ liệu cũ chưa chuẩn hóa, hãy định nghĩa rõ:

1. Những đơn nào được phép tham gia báo cáo?
2. Field tiền có bắt buộc không và kiểu BSON nào được chấp nhận?
3. Lỗi dữ liệu được **loại khỏi báo cáo, ghi nhận riêng hay làm báo cáo thất bại**?
4. Có cần đối soát tổng doanh thu với nguồn khác hay không?

Một DTO đẹp không sửa được một pipeline đã chọn/tổng hợp dữ liệu sai.

## 13. Document lồng nhau, array output và khi nào chưa nên map DTO

Aggregation không chỉ sinh document phẳng. `$push` có thể sinh array, `$facet` có thể sinh nhiều nhóm kết quả, `$lookup` có thể sinh mảng document liên kết. Khi output shape thay đổi thường xuyên, `Document` hữu ích để khảo sát:

~~~json
{
  "regionCode": "HCM",
  "orderCount": 2,
  "sampleOrders": [
    { "id": "o-101", "amountVnd": 120000 },
    { "id": "o-102", "amountVnd": 80000 }
  ]
}
~~~

Một đoạn code đọc array có kiểm tra:

~~~java
Document report = dataRows.get(0);
List<Document> orders =
        report.getList("sampleOrders", Document.class);

if (orders != null) {
    for (Document order : orders) {
        String id = order.getString("id");
        Object amount = order.get("amountVnd");
        // Validate type nếu tiếp tục xử lý số tiền.
    }
}
~~~

**Đây là ví dụ một shape mở rộng**, không phải output của pipeline vùng đang dùng (pipeline đó chưa có `sampleOrders`). Để thử đoạn này phải bổ sung các stage tương ứng; đừng copy nguyên vào test hiện tại rồi kỳ vọng field tồn tại.

Khi shape đã ổn định, nên tạo DTO lồng:

~~~java
package com.example.sales;

import java.util.List;

public record OrderSnippetDto(
        String id, long amountVnd) {}

public record RegionDetailsDto(
        String regionCode,
        long orderCount,
        List<OrderSnippetDto> sampleOrders) {}
~~~

Hai record này cần đặt trong **hai file Java riêng** nếu đều là top-level `public`, hoặc đổi một record thành không public khi chung file. Đây là minh họa hợp đồng DTO, không phải pipeline tự động sinh từ `RegionSalesReportService`.

Đừng trả một mảng không giới hạn các đơn hàng từ `$push` chỉ để làm báo cáo tổng hợp. Với vùng có hàng triệu đơn, array có thể quá lớn, tốn bộ nhớ và chạm giới hạn BSON document **16 MiB**. Nên giới hạn dữ liệu, tách endpoint chi tiết hoặc dùng pagination theo nhu cầu.

## 14. Chọn DTO hay Document trong thực tế

| Tiêu chí | DTO/record | `org.bson.Document` |
|---|---|---|
Output schema cố định | Phù hợp | Sử dụng được nhưng phải tự kiểm tra key/type |
Tích hợp business service/API | Rõ ràng, type-safe hơn | Dễ làm lộ cấu trúc DB nếu trả thẳng |
Debug pipeline mới | Cần sửa/rebuild DTO khi đổi shape | Linh hoạt, dễ quan sát mọi field |
Phát hiện field bị thiếu/đổi alias | Có thể lỗi mapping hoặc giá trị null tùy kiểu | `get()` trả null, dễ bỏ qua nếu không validate |
Kiểu số BSON thay đổi | Converter có thể hỗ trợ chuyển đổi | Chủ động đọc Int32/Int64/Decimal128 |
Kết quả lồng nhau | DTO nested nếu schema ổn định | Dễ duyệt document/array khi khảo sát |
Khả năng refactor | Tên field trong code rõ ràng | Dùng string key, cần test nhiều hơn |
Hiệu năng | Có chi phí materialization | Cũng có chi phí BSON/Document materialization |
Truyền qua public API | Nên thiết kế response DTO | Không nên công khai thẳng Document thô |

**Quy tắc gợi ý:** dùng `Document` để quan sát và thăm dò, sau đó **chốt hợp đồng DTO** cho đường đọc ổn định. Nhưng đừng biến “DTO luôn nhanh hơn” hoặc “Document luôn ít conversion hơn” thành khẳng định hiệu năng không có số đo; chi phí chính thường còn nằm ở query plan, lượng dữ liệu và network.

### 14.1. Giữ MongoDB khỏi contract HTTP

Không trả raw `Document` trực tiếp ra HTTP chỉ vì dễ serialize. Một Document có thể chứa `_id`, trường nội bộ, metadata aggregation hoặc BSON types cần chuyển đổi chính xác. Tầng API nên:

- Chọn field được phép công khai.
- Trả tên field ổn định theo API contract.
- Chuyển số tiền/thời gian theo chuẩn thống nhất.
- Kiểm tra tenant/role trước khi aggregate.
- Giới hạn số dòng và thời gian truy vấn.

DTO không tự bảo đảm bảo mật: **filter tenant phải được thực hiện tại MongoDB**, không phải chỉ map DTO sau khi đã tổng hợp toàn bộ collection.

## 15. Hiệu năng, index và lượng kết quả

Aggregation với DTO hay Document đều thực hiện **cùng pipeline trên server** nếu các stage tương đương. Chuyển output Java từ `Document.class` thành `RegionRevenueDto.class` không tự làm `$group` rẻ hơn.

### 15.1. Index cho $match đầu pipeline

Ví dụ một index ứng viên:

~~~javascript
db.sales_orders.createIndex(
  { tenantId: 1, status: 1, region_code: 1 },
  { name: "idx_tenant_status_region" }
);
~~~

Nó có thể giúp lọc theo tenant/status và hỗ trợ đường đọc tùy query, nhưng cần kiểm tra explain thực tế. Nếu `amount_vnd` cũng thường tham gia báo cáo, có thể cân nhắc covered index phù hợp khi workload chứng minh lợi ích; index rộng làm tăng chi phí ghi/dung lượng và không phải cứ thêm tất cả field là tối ưu.

### 15.2. Xem kế hoạch pipeline

Trong MongoDB shell:

~~~javascript
db.sales_orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-a", status: "PAID" } },
  {
    $group: {
      _id: "$region_code",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$amount_vnd" }
    }
  },
  {
    $project: {
      _id: 0, regionCode: "$_id",
      orderCount: 1, revenueVnd: 1
    }
  }
]);
~~~

Đo số document/keys examined, thời gian và sự hiện diện của các stage cần nhiều bộ nhớ. `$group` có thể gây tốn bộ nhớ khi có nhiều khóa nhóm; tùy phiên bản/giới hạn server và cấu hình, có thể cần cho phép dùng disk hoặc thiết kế pre-aggregation/materialized view phù hợp.

### 15.3. getMappedResults materialize danh sách

`getMappedResults()` trả `List<T>`, có nghĩa ứng dụng nhận và giữ các object kết quả trong bộ nhớ. Khi output là vài vùng, chi phí nhỏ. Nhưng với pipeline tạo hàng triệu document, không nên chuyển sang List vô giới hạn chỉ vì API thuận tiện.

Trong các phiên bản hỗ trợ, `MongoTemplate.aggregateStream(...)` có thể cung cấp `Stream<T>` để xử lý tuần tự và đóng tài nguyên đúng cách, ví dụ:

~~~java
try (java.util.stream.Stream<RegionRevenueDto> stream =
        mongo.aggregateStream(
                aggregation, SalesOrder.class, RegionRevenueDto.class)) {
    stream.forEach(row -> {
        // Xử lý từng dòng, tránh giữ toàn bộ kết quả.
    });
}
~~~

Ở đây `aggregation` là pipeline đã được khai báo trong scope phù hợp. Stream/cursor cần được **đóng** và không nên kéo dài qua nhiều request HTTP. Đổi sang streaming không sửa một pipeline kém hiệu năng trên server.

### 15.4. Limit và sort sau group

`$sort` + `$limit` có thể hữu ích cho “top 10 vùng theo doanh thu”. Nhưng cần xác định rõ:

- `$limit` **trước group** nghĩa là chỉ nhóm một phần đơn hàng, có thể làm tổng doanh thu sai.
- `$limit` **sau group/sort** cắt bớt các dòng báo cáo nhưng vẫn phải tổng hợp dữ liệu nguồn cần thiết.
- Nếu thêm sort theo doanh thu, một tie-breaker như `regionCode` giúp kết quả ổn định khi hai vùng có tổng bằng nhau.

Không tự áp dụng pagination offset vào một pipeline tổng hợp có kết quả biến động mà kỳ vọng snapshot qua nhiều request; cần xác định semantics nhất quán riêng.

## 16. Kiểm thử DTO và Document trên MongoDB thật

Mock `MongoTemplate` có thể kiểm tra service đã gọi `aggregate` nhưng không chứng minh stage mapping, BSON aliases hoặc kiểu numeric thực tế. Nên dùng integration test với MongoDB thật, ví dụ Testcontainers. Trong Spring Boot 3.x, `@DataMongoTest` cấu hình test slice MongoDB nhưng **không tự khởi động server**.

### 16.1. Test seed và ánh xạ record/class DTO

**RegionSalesAggregationTest.java**

~~~java
package com.example.sales;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(RegionSalesReportService.class)
class RegionSalesAggregationTest {
    @Autowired
    MongoTemplate mongo;

    @Autowired
    RegionSalesReportService reports;

    private SalesOrder order(
            String id, String tenant, String status,
            String region, long amount, int hour) {
        return new SalesOrder(
                id, tenant, status, region, amount,
                Instant.parse("2026-11-20T00:00:00Z")
                        .plusSeconds(3600L * hour));
    }

    @BeforeEach
    void seed() {
        // Chỉ thực hiện trên MongoDB test được cô lập.
        mongo.remove(new Query(), SalesOrder.class);
        mongo.insert(List.of(
                order("o-101", "tenant-a", "PAID", "HCM", 120000L, 8),
                order("o-102", "tenant-a", "PAID", "HCM", 80000L, 9),
                order("o-103", "tenant-a", "PAID", "HN", 50000L, 10),
                order("o-104", "tenant-a", "CANCELLED", "HN", 999000L, 11),
                order("o-105", "tenant-b", "PAID", "HCM", 700000L, 12)
        ), SalesOrder.class);
    }

    @Test
    void groupsSourceOrdersIntoTwoDtoRows() {
        List<RegionRevenueDto> rows =
                reports.typed("tenant-a").getMappedResults();

        assertThat(rows).containsExactly(
                new RegionRevenueDto("HCM", 2L, 200000L),
                new RegionRevenueDto("HN", 1L, 50000L));
    }

    @Test
    void classDtoUsesConstructorMapping() {
        List<RegionRevenueClassDto> rows =
                reports.classDtos("tenant-a");

        assertThat(rows).hasSize(2);
        assertThat(rows.get(0).getRegionCode()).isEqualTo("HCM");
        assertThat(rows.get(0).getOrderCount()).isEqualTo(2L);
        assertThat(rows.get(0).getRevenueVnd()).isEqualTo(200000L);
    }

    @Test
    void documentRowsHaveProjectedShapeAndNumericValues() {
        List<Document> rows =
                reports.documents("tenant-a").getMappedResults();

        assertThat(rows).hasSize(2);
        Document hcm = rows.get(0);

        assertThat(hcm.getString("regionCode")).isEqualTo("HCM");
        assertThat(hcm.containsKey("_id")).isFalse();
        assertThat(hcm.containsKey("amount_vnd")).isFalse();

        Object count = hcm.get("orderCount");
        Object revenue = hcm.get("revenueVnd");
        assertThat(count).isInstanceOf(Number.class);
        assertThat(revenue).isInstanceOf(Number.class);
        assertThat(((Number) count).longValue()).isEqualTo(2L);
        assertThat(((Number) revenue).longValue()).isEqualTo(200000L);
    }

    @Test
    void sourceFieldMappingAndTenantFilterRemainCorrect() {
        Document rawOrder = mongo.getCollection("sales_orders")
                .find(new Document("_id", "o-101")).first();

        assertThat(rawOrder).isNotNull();
        assertThat(rawOrder.getString("region_code")).isEqualTo("HCM");
        assertThat(rawOrder.containsKey("regionCode")).isFalse();
        assertThat(rawOrder.get("amount_vnd")).isInstanceOf(Number.class);

        assertThat(reports.typed("tenant-b").getMappedResults())
                .containsExactly(
                        new RegionRevenueDto("HCM", 1L, 700000L));
    }
}
~~~

Các test được tổ chức theo ba hợp đồng:

1. **Kết quả nghiệp vụ:** chỉ tenant-a và PAID được tính, doanh thu đúng.
2. **Kết quả kiểu Java:** record/class DTO có đúng các field và giá trị.
3. **BSON thực:** source dùng `region_code`/`amount_vnd`; output được alias thành `regionCode`/`revenueVnd` và không còn `_id`.

Đây là ví dụ dựa trên MongoDB thực đang được cung cấp cho test. `@DataMongoTest` không tự đảm bảo server đã khởi động. Không dùng `remove(new Query(), ...)` hoặc `dropCollection` trên database chung với các test chạy đồng thời; cần cô lập database/collection hoặc seed theo namespace riêng.

### 16.2. Những test bổ sung nên có

| Tình huống | Kỳ vọng cần xác minh |
|---|---|
Không có đơn nào khớp tenant/status | `getMappedResults()` rỗng; unique total có thể null |
Một vùng duy nhất | `getUniqueMappedResult()` phù hợp khi pipeline thực sự chỉ trả một document |
Hai vùng | Không dùng unique result như một cách chọn “vùng đầu tiên” |
Field `region_code` thiếu/null | Có nhóm null hoặc policy xử lý như đã định nghĩa |
Field `amount_vnd` lưu kiểu BSON khác | Converter/Document đọc đúng hoặc báo lỗi rõ |
Pipeline quên `$project` alias | DTO không còn shape đúng; test phải phát hiện |
`$match` quên tenant | Test có dữ liệu tenant-b phải phát hiện trộn doanh thu |
Doanh thu hai vùng bằng nhau | Sort tie-breaker ổn định |
Đơn CANCELLED có doanh thu rất lớn | Không được cộng vào PAID report |
Aggregation dùng source collection name thay type | Phải đối chiếu mapping metadata, không suy đoán |
Output lớn | Giới hạn memory hoặc dùng stream có đóng cursor |

### 16.3. Chẩn đoán BSON pipeline

Muốn biết lệnh MongoDB thực sự chạy ra sao, có thể dùng MongoDB Java Driver `CommandListener` và `CommandStartedEvent` trong test. Lệnh aggregation thường có mảng `pipeline`; kiểm tra `$match`, `$group`, `$project`, `$sort` theo **tên field BSON thực tế**.

Để kiểm tra query plan, dùng `explain("executionStats")` trên pipeline tương đương ở MongoDB shell. `AggregationResults.getRawResults()` dùng cho phản hồi server sau aggregation; nó không tự thay thế việc capture command hoặc explain.

Khi log pipeline, phải che thông tin nhạy cảm (tenant, account, số tiền hoặc filter chứa dữ liệu cá nhân) và không bật full command logging trong production nếu chưa có chính sách phù hợp.

## 17. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
Map `$group` result vào entity đơn hàng gốc | Field thiếu/null, logic hiểu sai một dòng nhóm | Thiết kế DTO theo output schema |
Cho rằng `$group` giữ tên property nhóm | Output thực có `_id` | `$project`/alias tường minh |
Quên loại `_id` khi DTO không cần | Có thể lộ metadata hoặc không khớp contract | `andExclude("_id")` khi phù hợp |
Nhầm `getRawResults()` với danh sách raw rows | Code đọc sai cấu trúc cursor/metadata | Dùng `AggregationResults<Document>.getMappedResults()` |
Lấy `Document.getLong()` cho một BSON Int32 | Lỗi cast/kiểu | Kiểm tra `Number` và miền giá trị |
Ép Decimal128 qua double để tính tiền | Sai số | Giữ `BigDecimal`/Decimal128 theo chính sách |
Đổi tên DTO mà quên alias pipeline | Field null hoặc lỗi materialization | Test mapping và output shape |
Trộn Java property và BSON physical field tùy tiện | Group sai, sum null/0 hoặc filter rỗng | Typed source mapping và kiểm tra BSON |
Nhầm số DTO với số đơn đã được nhóm | Báo cáo số document sai | Dùng `orderCount` accumulator |
Không lọc tenant trước group | Trộn doanh thu giữa tenants | `$match` tenant từ auth context trước tổng hợp |
`$limit` trước `$group` trong báo cáo tổng | Tổng doanh thu bị tính thiếu | Group toàn bộ tập phù hợp, limit sau khi có nhóm |
Chỉ test với một vùng | Không phát hiện unique-result misuse | Test không, một và nhiều dòng |
Giữ mọi raw document vô hạn trong List | Tốn memory | Limit/stream và pagination phù hợp |
Cho rằng đổi DTO sang Document làm query nhanh hơn | Chẩn đoán sai bottleneck | Đo explain, network, conversion và index |
Serialize raw `Document` thẳng vào API công khai | Rò cấu trúc MongoDB/BSON type | Dùng response DTO có contract |
Kiểm thử bằng mock mà không có MongoDB thực | Không phát hiện @Field/alias/type errors | Integration test MongoDB cô lập |

## 18. Bài tập thực hành

**Bài 1 — DTO tổng hợp.** Tạo `SalesOrder`, `RegionRevenueDto` và pipeline `$match → $group → $project → $sort`. Seed 5 đơn như mục 3; kiểm tra HCM có 2 đơn/200000 VND và HN có 1 đơn/50000 VND.

**Bài 2 — Raw Document.** Chạy chính pipeline của bài 1 nhưng cho `Document.class` làm output. In các key sau `$project`, đọc `orderCount/revenueVnd` dưới dạng `Number` rồi đổi sang `long` có validation.

**Bài 3 — Hai nghĩa của raw.** So sánh `results.getRawResults()` với `aggregate(..., Document.class).getMappedResults()`. Viết giải thích vì sao một bên là **reply ở cấp lệnh**, còn bên kia là **từng document kết quả**.

**Bài 4 — Thiếu alias.** Bỏ `$project`. Quan sát `_id` trong Document, sau đó chạy DTO có component `regionCode`. Sửa pipeline để output khớp hợp đồng record và thêm regression test.

**Bài 5 — Total unique.** Dùng `group()` tổng hợp tất cả đơn PAID một tenant thành `TotalRevenueDto`. So sánh `getUniqueMappedResult()` với `getMappedResults()` khi không có đầu vào, một dòng và nhiều vùng.

**Bài 6 — @Field và source type.** Giữ `@Field("region_code")` và `@Field("amount_vnd")`. Thử typed input `SalesOrder.class` và overload nhận collection name; đối chiếu BSON filter/group thực tế để nhận biết khi nào thiếu mapping metadata.

**Bài 7 — Null/missing.** Tạo một đơn không có `region_code` và một đơn `amount_vnd` null trong database test (dùng raw BSON nếu cần). Định nghĩa chính sách xử lý và kiểm tra nhóm null/tổng số để tránh báo cáo âm thầm sai.

**Bài 8 — Số học tài chính.** Thử dữ liệu doanh thu ở các kiểu Int32, Int64, Double và Decimal128 theo schema test. Thiết kế DTO và cách đọc `Document` giữ chính xác số tiền; nêu rủi ro khi dùng `double`.

**Bài 9 — Aggregation lồng.** Bổ sung `sampleOrders` bằng `$push` cho từng vùng, sau đó dùng `Document.getList` để kiểm tra shape. Khi schema ổn định, thiết kế nested record DTO và giới hạn số item để không làm mảng phát triển vô hạn.

**Bài 10 — Hiệu năng.** Seed dữ liệu đủ lớn, so sánh filter có index với không có index, thực hiện cùng pipeline output DTO và Document. Đo `explain("executionStats")`, số document scanned, thời gian, memory ứng dụng và chi phí conversion; chỉ kết luận sau khi có số liệu thực tế.

## 19. Ghi nhớ

Trong **Spring Data MongoDB**, `MongoTemplate.aggregate(...)` có thể trả `AggregationResults<DTO>` khi output pipeline đã có schema rõ, hoặc `AggregationResults<Document>` khi cần xem trực tiếp từng document kết quả. **`getMappedResults()`** trả các dòng đã được materialize; **`getUniqueMappedResult()`** chỉ phù hợp khi pipeline tạo tối đa một dòng; **`getRawResults()`** là phản hồi BSON ở cấp lệnh, **không phải** danh sách raw rows của báo cáo.

Khi chuyển từ `$group` sang DTO, phải xử lý đúng trường `_id` và **alias bằng `$project`** để output có những tên field DTO cần. Dùng input entity type để Spring Data ánh xạ property Java qua `@Field`, nhưng luôn kiểm tra tên BSON sau từng stage, kiểu số, null/missing và các giới hạn của converter.

Hãy chọn **DTO cho hợp đồng ứng dụng ổn định, Document để quan sát/khảo sát schema**, và dùng integration test với MongoDB thực để xác minh cả hai. Phân tách đúng **entity nguồn — BSON output — DTO đích** là nền tảng để kết quả aggregation chính xác, dễ bảo trì và không lộ dữ liệu ngoài phạm vi được phép.
