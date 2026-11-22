# Khi nào chuyển pipeline phức tạp sang template hoặc fragment?

> **Chương:** Aggregation repository  
> **Module:** `SPRING_DATA_MONGODB`

Trong Spring Data MongoDB, `@Aggregation` cho phép đặt một pipeline MongoDB ngay trên phương thức repository. Với truy vấn báo cáo cố định, đây thường là lựa chọn gọn, dễ gọi và dễ nhận biết hợp đồng dữ liệu. Nhưng một pipeline có thể phát triển từ ba stage thành nhiều nhánh lọc tùy chọn, `$lookup` giữa các collection, `$facet` vừa trả danh sách vừa đếm tổng nhóm, phân trang, phép tính tùy nghiệp vụ và những yêu cầu khác nhau theo endpoint. Khi đó, tiếp tục nhét mọi trường hợp vào một annotation dài có thể khiến code khó đọc, khó tái sử dụng và khó kiểm thử.

Có hai hướng mở rộng quan trọng: chuyển logic aggregation sang **`MongoTemplate` với `Aggregation` DSL**, hoặc đóng gói logic đó vào một **custom repository fragment** để ứng dụng vẫn gọi qua một repository domain nhất quán. **Template và fragment không phải hai lựa chọn loại trừ nhau**: fragment thường dùng `MongoTemplate` bên trong.

Bài thuộc module `SPRING_DATA_MONGODB`, nơi thực hành kết nối và ánh xạ document, thao tác bằng `MongoTemplate` hoặc repository, truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Trọng tâm ở đây là **tiêu chí quyết định nơi đặt pipeline**, cách chuyển một ví dụ thực tế và các giới hạn mà developer cần kiểm tra trước khi đưa vào sản xuất.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác biệt giữa `@Aggregation`, `MongoTemplate.aggregate(...)` và custom repository fragment.
2. Nhận diện những dấu hiệu **chưa cần chuyển** và những dấu hiệu pipeline đã đủ phức tạp để chuyển.
3. Viết một pipeline báo cáo tĩnh bằng repository `@Aggregation`, sau đó chuyển thành pipeline động bằng `Aggregation.newAggregation(...)`.
4. Đóng gói pipeline động trong fragment theo quy ước Spring Data, tránh để controller biết chi tiết aggregation.
5. Phân biệt kết quả aggregation DTO với entity nguồn, đặc biệt khi `$group` làm đổi ý nghĩa `_id`.
6. Thiết kế filter tenant và quyền truy cập, optional filters, giới hạn kết quả, phân trang và kiểm thử BSON thật.
7. Đánh giá query plan, index, `$facet`, `$lookup`, khả năng streaming/reactive và chi phí của việc tổ chức code.

## 2. Ba cấp độ tổ chức aggregation

```text
Controller / Application Service
               |
               v
      OrderRepository (domain API)
               |
       +-------+-------------------+
       |                           |
   @Aggregation           OrderReportOperations
   pipeline tĩnh          (repository fragment)
       |                           |
       v                           v
  Spring Data                  MongoTemplate
  repository query             Aggregation DSL
       |                           |
       +-------------+-------------+
                     |
                     v
               MongoDB server
                     |
                     v
             Aggregation result DTO
```

Có thể gọi trực tiếp `MongoTemplate` từ một service chuyên biệt khi pipeline thuộc logic báo cáo vượt ngoài trách nhiệm của repository domain. Tuy nhiên, nếu team muốn các truy vấn của `Order` được tìm qua một **interface repository duy nhất**, custom fragment giúp che cấu trúc pipeline và giữ code gọi đơn giản.

### 2.1. Bảng so sánh

| Tiêu chí | Repository `@Aggregation` | `MongoTemplate` / Aggregation DSL | Repository fragment |
| --- | --- | --- | --- |
| Pipeline cố định, ngắn | Rất phù hợp | Dùng được, đôi khi dài hơn cần thiết | Có thể quá nhiều boilerplate |
| Stage tùy chọn từ request | Khó mở rộng, dễ nổ số lượng phương thức | **Phù hợp**: ghép `AggregationOperation` động | **Phù hợp**, thường dùng template bên trong |
| `$lookup` / `$facet` phức tạp | Viết được JSON dài, khó bảo trì hơn | Có builder và khả năng mở rộng stage | Giấu chi tiết phức tạp sau API domain |
| Tái sử dụng đoạn filter/pipeline | Hạn chế trong chuỗi annotation | Dễ tách helper/operations | Dễ chia sẻ trong lớp implementation |
| Kiểm thử từng stage | Có thể chạy integration test, khó lắp ghép từng đoạn | Dễ tạo pipeline tiền tố và kiểm tra | Test qua repository + test logic implementation |
| Mapping field/DTO | Cần kiểm tra input/output mapping | Hỗ trợ typed aggregation và mapping | Dựa vào template/DSL được chọn |
| API đối với caller | Phương thức repository | Phương thức của service/template trực tiếp | Phương thức repository domain |
| Số lớp/mã phụ trợ | Ít | Trung bình | Nhiều hơn (interface, impl, wiring) |
| Hiệu năng khi BSON pipeline giống nhau | Về bản chất do MongoDB xử lý | **Không mặc định nhanh hơn** | **Không mặc định nhanh hơn** |

**Kết luận quan trọng:** chuyển sang template **không phải một cách tối ưu hiệu năng tự động**. Nó chủ yếu giải quyết khả năng tổ chức pipeline động, kiểm thử, bảo trì và kiểm soát option/query mapping. Hiệu năng vẫn phụ thuộc BSON được gửi, index, phân bố dữ liệu và hạ tầng MongoDB.

## 3. Khi nào giữ @Aggregation?

Giữ annotation là lựa chọn hợp lý nếu:

- Số stage ít và **cấu trúc pipeline cố định**.
- Các tham số chỉ thay **giá trị** của filter hoặc ngưỡng, không quyết định xuất hiện/mất đi của stage.
- Output DTO ổn định và có thể mô tả ngắn gọn.
- Không cần lắp ghép nhiều nhánh `$match`, `$lookup`, `$facet`, projection hoặc pagination tùy yêu cầu.
- Code review có thể đọc toàn bộ pipeline mà không phải lần theo nhiều biến thể chuỗi JSON.

Ví dụ về hợp đồng đơn giản: “Trong một tenant, đếm số đơn và tổng giá trị theo **một trạng thái**”. Đây là truy vấn có giá trị tham số, nhưng **không thay đổi cấu trúc pipeline**.

### 3.1. Dấu hiệu không nên chuyển quá sớm

Nếu chỉ cần thêm một điều kiện cố định hoặc thay giá trị từ `"PAID"` sang tham số `?1`, việc viết thêm ba lớp fragment có thể làm bài toán khó hiểu hơn. Độ dài annotation **không phải** tiêu chí duy nhất; một pipeline dài nhưng ổn định, được kiểm thử tốt vẫn có thể chấp nhận.

Không nên tạo một DSL chung cho mọi aggregation chỉ vì dự án có hai truy vấn đơn giản. Tính tổng quát quá mức có thể làm mất khả năng đọc ngữ nghĩa MongoDB ngay tại chỗ.

## 4. Khi nào chuyển sang MongoTemplate?

Những tín hiệu thường rõ ràng:

1. **Stage động:** request có thể thêm/bỏ `$match`, `$lookup`, `$group`, `$project`, `$sort` hoặc `$limit`.
2. **Nhiều bộ lọc tùy chọn:** khoảng thời gian, trạng thái, kênh, ngưỡng giá trị, loại người dùng, nhóm quyền.
3. **Pipeline phân nhánh:** `$facet` trả nhiều thống kê từ cùng một tập đầu vào, hoặc các pipeline con của `$lookup` có điều kiện.
4. **Đổi hình dạng output:** nhóm theo kênh hoặc trạng thái tùy lựa chọn, thêm các số liệu tổng hợp chỉ khi được yêu cầu.
5. **Cần cấu hình thực thi:** option aggregation, collation, allowDiskUse, kiểm soát read concern/session hoặc đường đọc reactive phù hợp.
6. **Cần kiểm thử theo stage:** tách các `AggregationOperation`, đối chiếu pipeline MongoDB được sinh ra và kết quả trung gian.
7. **Cần tái sử dụng logic:** filter tenant, soft-delete policy, thời gian, trạng thái và công thức được dùng bởi nhiều báo cáo.

Đó là tín hiệu về **khả năng thay đổi cấu trúc và độ khó bảo trì**, không phải một ngưỡng cứng như “trên 5 stage thì bắt buộc chuyển”. Một pipeline chỉ ba stage nhưng một stage chứa `$cond` lồng nhiều tầng cũng có thể nên chuyển.

### 4.1. Không chuyển chỉ để nối JSON tùy tiện

Chuyển `@Aggregation` sang code Java nhưng tiếp tục ghép tên field và operator từ chuỗi người dùng không làm pipeline an toàn hơn. Với filter động, ưu tiên `Criteria` và các builders có thể kiểm soát kiểu/nội dung; tên field, sort key và nhóm phép tính cần **allowlist**.

## 5. Khi nào cần custom repository fragment?

Fragment là bước **đóng gói API**, không phải một loại MongoDB query mới. Cân nhắc fragment khi:

- Caller muốn sử dụng `orderRepository.revenueByStatus(...)` thay vì biết `MongoTemplate` và collection name.
- Cần một **hợp đồng báo cáo domain** ổn định, trong khi implementation có thể thay đổi từ annotation sang template hoặc pipeline khác.
- Có nhiều method aggregation liên quan một aggregate root/repository và cần dùng chung validation, mapping, rule về tenant.
- Muốn tách trách nhiệm của derived-query methods khỏi logic xây pipeline động.
- Cần thay đổi/kiểm thử riêng implementation mà không làm controller/service trộn BSON với logic nghiệp vụ.

Nếu báo cáo là **cross-domain** (kết hợp order, payment, shipment, inventory...), có thể một `ReportingService`/query adapter chuyên biệt rõ ràng hơn là nhét mọi báo cáo vào `OrderRepository`. Không ép fragment vào nơi sai ranh giới chỉ vì muốn “tất cả là repository”.

### 5.1. Một câu hỏi quyết định nhanh

```text
Pipeline có cấu trúc cố định, ít nhánh?
    |
    +-- Có --> @Aggregation nếu rõ ràng và dễ test.
    |
    +-- Không --> MongoTemplate + Aggregation DSL.
                    |
                    +-- Caller nên thấy domain repository API?
                           |
                           +-- Có --> custom repository fragment
                           |
                           +-- Không --> dedicated query/reporting service
```

**Fragment và template phối hợp:** implementation của fragment thường chính là chỗ sử dụng `MongoTemplate`, xây `AggregationOperation` và ánh xạ kết quả. Chọn fragment không làm biến mất nhu cầu hiểu MongoDB aggregation.

## 6. Tình huống xuyên suốt: báo cáo đơn hàng

Hệ thống có collection `orders`. Mỗi document là **một đơn hàng** (không phải một dòng hàng), gồm tenant, trạng thái, kênh bán, thời điểm tạo, số tiền nguyên và cờ archive:

```javascript
{
  _id: "A-101",
  tenantId: "TENANT-A",
  status: "PAID",
  channel: "web",
  amountMinor: NumberLong(100000),
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  archived: false
}
```

Chọn dữ liệu đơn giản để thấy **điểm chuyển đổi kiến trúc** rõ ràng thay vì mất tập trung vào công thức tài chính.

### 6.1. Dữ liệu mẫu (chỉ trên database kiểm thử)

```javascript
use shop

db.orders.insertMany([
  { _id: "A-101", tenantId: "TENANT-A", status: "PAID",
    channel: "web", amountMinor: NumberLong(100000),
    createdAt: ISODate("2026-11-10T09:00:00Z"), archived: false },
  { _id: "A-102", tenantId: "TENANT-A", status: "PAID",
    channel: "app", amountMinor: NumberLong(80000),
    createdAt: ISODate("2026-11-10T10:00:00Z"), archived: false },
  { _id: "A-103", tenantId: "TENANT-A", status: "PAID",
    channel: "web", amountMinor: NumberLong(20000),
    createdAt: ISODate("2026-11-11T09:00:00Z"), archived: false },
  { _id: "A-104", tenantId: "TENANT-A", status: "NEW",
    channel: "web", amountMinor: NumberLong(50000),
    createdAt: ISODate("2026-11-11T10:00:00Z"), archived: false },
  { _id: "A-105", tenantId: "TENANT-A", status: "PAID",
    channel: "app", amountMinor: NumberLong(35000),
    createdAt: ISODate("2026-11-12T10:00:00Z"), archived: true },
  { _id: "A-106", tenantId: "TENANT-A", status: "NEW",
    channel: "app", amountMinor: NumberLong(40000),
    createdAt: ISODate("2026-11-12T11:00:00Z"), archived: false },
  { _id: "A-107", tenantId: "TENANT-A", status: "CANCELLED",
    channel: "web", amountMinor: NumberLong(60000),
    createdAt: ISODate("2026-11-13T09:00:00Z"), archived: false },
  { _id: "A-108", tenantId: "TENANT-A", status: "PAID",
    channel: "web", amountMinor: NumberLong(30000),
    createdAt: ISODate("2026-11-14T09:00:00Z"), archived: false },
  { _id: "B-201", tenantId: "TENANT-B", status: "PAID",
    channel: "web", amountMinor: NumberLong(999999),
    createdAt: ISODate("2026-11-13T09:00:00Z"), archived: false }
])
```

Khi **chỉ lấy TENANT-A, archived=false và status thuộc {PAID, NEW}**:

| Nhóm | ID được tính | Số đơn | Tổng `amountMinor` |
| --- | --- | ---: | ---: |
| PAID | A-101, A-102, A-103, A-108 | 4 | 230.000 |
| NEW | A-104, A-106 | 2 | 90.000 |

A-105 bị loại vì `archived=true`, A-107 không thuộc tập trạng thái được chọn, B-201 bị loại vì thuộc tenant B. Những điều kiện này phải được giữ **trong mọi biến thể** pipeline.

### 6.2. Bộ yêu cầu ban đầu và khi mở rộng

**Phiên bản 1:** “Với tenant và trạng thái đã biết, trả tổng đơn và tổng tiền”. Pipeline `$match` → `$group` → `$project` cố định.

**Phiên bản 2:** Báo cáo có thể lọc theo thời gian `[from, to)`, tập trạng thái, kênh, giá trị tối thiểu; sắp xếp nhóm theo doanh thu và giới hạn số nhóm. Các stage vẫn đơn giản, nhưng **điều kiện được lắp từ input**.

**Phiên bản 3:** Muốn đồng thời lấy dữ liệu trang và tổng số nhóm bằng `$facet`, hoặc nối payment bằng `$lookup`; nhu cầu tái sử dụng, debug và option pipeline rõ ràng hơn. Đây thường là lúc tách aggregation sang template và cân nhắc fragment.

## 7. Entity nguồn và DTO đầu ra

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String status,
    String channel,
    long amountMinor,
    Instant createdAt,
    boolean archived
) {}
```

File `StatusRevenue.java`:

```java
package com.example.shop.orders;

public record StatusRevenue(
    String status,
    long orderCount,
    long revenueMinor
) {}
```

`@Id` ánh xạ property `id` sang BSON `_id`. Ví dụ dùng ID dạng `"A-101"` là BSON String không có dạng ObjectId. Khi dùng ID dạng 24 ký tự hex hoặc có `@MongoId`/`@Field`, kiểm tra mapping và kiểu BSON thực tế.

Sau `$group`, `_id` mang **giá trị status của nhóm**, không còn là `OrderDocument.id`. Vì thế cần output DTO riêng `StatusRevenue`. Không nên nhận kết quả aggregate đã group vào `OrderDocument` rồi gọi `repository.save(...)`, vì schema không còn đầy đủ và `_id` đã đổi ý nghĩa.

## 8. Bước đầu: @Aggregation với pipeline tĩnh

Đây là cách bắt đầu đúng khi chỉ muốn tổng hợp theo một trạng thái. File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        """
        {
          '$match': {
            'tenantId': ?0,
            'status': ?1,
            'archived': false
          }
        }
        """,
        """
        {
          '$group': {
            '_id': '$status',
            'orderCount': { '$sum': 1 },
            'revenueMinor': { '$sum': '$amountMinor' }
          }
        }
        """,
        """
        {
          '$project': {
            '_id': 0,
            'status': '$_id',
            'orderCount': 1,
            'revenueMinor': 1
          }
        }
        """
    })
    List<StatusRevenue> summarizeStatus(
        String permittedTenantId,
        String status);
}
```

Repository annotation dùng `org.springframework.data.mongodb.repository.Aggregation`, **khác** lớp `org.springframework.data.mongodb.core.aggregation.Aggregation` dùng để tạo pipeline bằng DSL.

### 8.1. Các tham số được bind thế nào?

`?0` và `?1` là **placeholder tham số theo vị trí** trong query annotation của Spring Data. Khi phương thức được gọi với `("TENANT-A","PAID")`, Spring Data bind hai giá trị thành filter, không phải ghép tùy tiện đoạn JSON từ user.

Kỳ vọng:

```java
List<StatusRevenue> result =
    repository.summarizeStatus("TENANT-A", "PAID");

// Một hàng:
// StatusRevenue("PAID", 4L, 230000L)
```

Tầng service phải xác minh `permittedTenantId` từ danh tính/ủy quyền; không cho client tự chọn bất kỳ tenant rồi tin rằng tên biến “permitted” đã bảo vệ dữ liệu.

### 8.2. Đặt $project sau $group

Sau `$group`, output có:

```javascript
{
  _id: "PAID",
  orderCount: 4,
  revenueMinor: NumberLong(230000)
}
```

`$project` đổi `_id` thành `status` và loại `_id`, tạo schema phù hợp `StatusRevenue`:

```javascript
{
  status: "PAID",
  orderCount: 4,
  revenueMinor: NumberLong(230000)
}
```

Đừng dùng tên field `status` từ entity nguồn sau group mà quên rằng chỉ những field được `$group`/projection tạo ra mới tồn tại.

### 8.3. Khi nào annotation bắt đầu mất ưu thế?

Giả sử business yêu cầu:

- Chỉ thêm `channel = web` khi user chọn kênh.
- Bỏ bộ lọc status nếu tất cả trạng thái được phép được chọn, hoặc cho phép tập trạng thái bất kỳ từ allowlist.
- Thêm `createdAt >= from AND createdAt < to`.
- Thêm `amountMinor >= minimumAmountMinor` khi có ngưỡng.
- Có thể nhóm theo `status` hoặc `channel`.
- Có thể trả một phần nhóm và tổng số nhóm bằng `$facet`.

Viết một annotation cho mỗi tổ hợp sẽ tạo rất nhiều phương thức và lặp lại pipeline. Một annotation có thể bind tham số, nhưng **bind giá trị khác với thêm/bỏ stage hoặc thay đổi hình dạng pipeline**. Ở đây nên xem xét `MongoTemplate`.

## 9. Thiết kế hợp đồng filter trước khi tạo pipeline động

Khi chuyển sang template, đừng truyền hàng chục tham số riêng rẽ thiếu quy tắc. Đặt chúng trong một type mô tả ý định báo cáo và validate trước khi gửi xuống MongoDB.

File `OrderReportFilter.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public record OrderReportFilter(
    Instant fromInclusive,
    Instant toExclusive,
    Set<String> statuses,
    String channel,
    Long minimumAmountMinor,
    int maxGroups
) {
    private static final Set<String> SUPPORTED_STATUSES =
        Set.of("NEW", "PAID", "CANCELLED");

    public OrderReportFilter {
        Objects.requireNonNull(fromInclusive, "fromInclusive");
        Objects.requireNonNull(toExclusive, "toExclusive");
        Objects.requireNonNull(statuses, "statuses");

        statuses = Set.copyOf(statuses);

        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException(
                "fromInclusive phải trước toExclusive");
        }
        if (!SUPPORTED_STATUSES.containsAll(statuses)) {
            throw new IllegalArgumentException(
                "Có trạng thái không được hỗ trợ");
        }
        if (minimumAmountMinor != null
                && minimumAmountMinor < 0) {
            throw new IllegalArgumentException(
                "minimumAmountMinor không được âm");
        }
        if (maxGroups < 1 || maxGroups > 100) {
            throw new IllegalArgumentException(
                "maxGroups phải trong khoảng 1..100");
        }
        if (channel != null && channel.isBlank()) {
            throw new IllegalArgumentException(
                "channel không được rỗng");
        }
    }
}
```

Thiết kế này dùng:

- `[fromInclusive, toExclusive)`: từ thời điểm bắt đầu **bao gồm**, đến thời điểm kết thúc **không bao gồm**. Không tự cộng 23:59:59.999 vào ngày cuối, vì độ chính xác thời gian và múi giờ có thể khác.
- `statuses`: tập trạng thái do API cho phép. **Tập rỗng được định nghĩa là không lấy gì**, tránh vô tình bỏ filter rồi đọc mọi trạng thái.
- `channel`: `null` nghĩa là không lọc theo kênh; giá trị không null phải là tên kênh được chấp nhận theo hợp đồng sản phẩm.
- `minimumAmountMinor`: tùy chọn; dùng số nguyên đơn vị tiền nhỏ nhất.
- `maxGroups`: giới hạn **số nhóm sau aggregation**, không phải số order đầu vào.

Nếu kênh đến từ input người dùng, ứng dụng nên dùng enum/allowlist được thống nhất thay vì chấp nhận string tùy ý. Dù `Criteria.is(...)` bind giá trị an toàn hơn ghép JSON, nó không thay thế validation nghiệp vụ hoặc phân quyền.

## 10. Bước chuyển: MongoTemplate và Aggregation DSL

Một cách triển khai đơn giản là tạo `List<AggregationOperation>` và chỉ thêm các stage cần thiết. Các filter tùy chọn có thể gom vào `Criteria` trước khi tạo `Aggregation.match`.

File `OrderReportQueryService.java`:

```java
package com.example.shop.orders;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class OrderReportQueryService {

    private final MongoTemplate template;

    public OrderReportQueryService(MongoTemplate template) {
        this.template = template;
    }

    public List<StatusRevenue> revenueByStatus(
            String permittedTenantId,
            OrderReportFilter filter) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant không hợp lệ");
        }
        if (filter == null) {
            throw new IllegalArgumentException(
                "Filter không hợp lệ");
        }

        // Fail-closed: không bỏ bộ lọc nếu tập trạng thái rỗng.
        if (filter.statuses().isEmpty()) {
            return List.of();
        }

        Criteria criteria = Criteria
            .where("tenantId").is(permittedTenantId)
            .and("archived").is(false)
            .and("createdAt")
                .gte(filter.fromInclusive())
                .lt(filter.toExclusive())
            .and("status").in(filter.statuses());

        if (filter.channel() != null) {
            criteria.and("channel").is(filter.channel());
        }
        if (filter.minimumAmountMinor() != null) {
            criteria.and("amountMinor")
                .gte(filter.minimumAmountMinor());
        }

        List<AggregationOperation> stages = new ArrayList<>();
        stages.add(Aggregation.match(criteria));
        stages.add(
            Aggregation.group("status")
                .count().as("orderCount")
                .sum("amountMinor").as("revenueMinor"));
        stages.add(
            Aggregation.project("orderCount", "revenueMinor")
                .and("_id").as("status")
                .andExclude("_id"));
        stages.add(
            Aggregation.sort(Sort.by(
                Sort.Order.desc("revenueMinor"),
                Sort.Order.asc("status"))));
        stages.add(Aggregation.limit(filter.maxGroups()));

        TypedAggregation<OrderDocument> aggregation =
            Aggregation.newAggregation(
                OrderDocument.class,
                stages.toArray(new AggregationOperation[0]));

        return template.aggregate(
            aggregation, StatusRevenue.class).getMappedResults();
    }
}
```

Ví dụ sử dụng API Spring Data MongoDB DSL phổ biến, Java 17+ và Spring Data repository/data mapping đã được cấu hình. Trong dự án thật, cần đối chiếu overload/mapping của phiên bản Spring Data đang dùng và xác nhận bằng test tích hợp.

### 10.1. Vì sao đây là “pipeline động” dù nhóm/sort cố định?

Danh sách stage hiện gồm năm bước cố định, nhưng **`Criteria` được cấu thành động** từ các filter. Điều này đã có giá trị vì bỏ các tổ hợp annotation lặp lại. Nếu báo cáo tiếp tục thêm optional `$lookup`, `$facet` hoặc nhánh projection theo lựa chọn người dùng, ta có thể bổ sung `stages.add(...)` có điều kiện mà không phải nhân bản cả pipeline.

Ví dụ thêm một stage tùy chọn:

```java
// Chỉ là minh họa khi reporting contract cần thêm giai đoạn.
if (includeHighValueOnly) {
    stages.add(
        Aggregation.match(
            Criteria.where("revenueMinor").gte(100000L)));
}
```

**Phải đặt đúng vị trí**: đoạn này có ý nghĩa khi chạy **sau `$group`**, nơi `revenueMinor` đã được tạo. Nếu đặt trước `$group`, field đó chưa tồn tại trên order nguồn và filter sẽ sai. Khi thêm code điều kiện, luôn ghi rõ stage áp lên **schema trung gian nào**.

### 10.2. TypedAggregation và field mapping

`Aggregation.newAggregation(OrderDocument.class, ...)` giúp Spring Data biết loại input để ánh xạ field path khi dựng pipeline. Đây là điều hữu ích nếu entity dùng `@Field` để đổi tên lưu BSON.

Tuy nhiên:

- Cần phân biệt field **nguồn** (như `amountMinor`) với field **kết quả stage** (như `revenueMinor`).
- Sau `$group`, schema không còn giống entity nguồn; việc tham chiếu tên field cần dựa vào output stage thực tế.
- Nếu trộn `AggregationOperation` raw BSON/Jackson/`Document.parse(...)` với typed DSL, raw stage có thể không tự áp mapping property giống DSL. Phải kiểm tra pipeline thực gửi xuống MongoDB.

### 10.3. Khi template trực tiếp là đủ

Một `OrderReportQueryService` như trên đã là giải pháp hợp lý nếu:

- Báo cáo thuộc application/query layer, không cần xuất hiện trong domain repository.
- Đội phát triển có ranh giới query service rõ.
- Các endpoint báo cáo phức tạp cần phối hợp nhiều repository hoặc collection.

Không nhất thiết tạo fragment chỉ để “được phép dùng MongoTemplate”. Fragment là lựa chọn **giữ ranh giới API repository** khi điều đó có ích cho tổ chức dự án.

## 11. Ví dụ chạy trên tập dữ liệu

Gọi báo cáo hai trạng thái trong tháng 11/2026:

```java
OrderReportFilter filter = new OrderReportFilter(
    java.time.Instant.parse("2026-11-01T00:00:00Z"),
    java.time.Instant.parse("2026-12-01T00:00:00Z"),
    java.util.Set.of("PAID", "NEW"),
    null,
    null,
    10);

List<StatusRevenue> report =
    orderReportQueryService.revenueByStatus(
        "TENANT-A", filter);
```

Kết quả theo `revenueMinor` giảm dần:

```text
StatusRevenue("PAID", 4, 230000)
StatusRevenue("NEW",  2,  90000)
```

Nếu thêm `channel = "web"`:

```text
StatusRevenue("PAID", 3, 150000) // A-101, A-103, A-108
StatusRevenue("NEW",  1,  50000) // A-104
```

A-102 là PAID nhưng kênh app nên không được tính trong biến thể web. A-105 bị archive, A-107 CANCELLED không thuộc tập, B-201 sai tenant.

## 12. Bước đóng gói: repository fragment

Giả sử team có quy ước tất cả truy vấn của `Order` được truy cập qua `OrderRepository`. Ta muốn caller viết:

```java
List<StatusRevenue> rows =
    orderRepository.revenueByStatus(permittedTenantId, filter);
```

Nhưng code xây pipeline vẫn có đủ sự linh hoạt của `MongoTemplate`. **Fragment** là nơi đặt logic đó.

### 12.1. Định nghĩa fragment interface

File `OrderReportOperations.java`:

```java
package com.example.shop.orders;

import java.util.List;

public interface OrderReportOperations {

    List<StatusRevenue> revenueByStatus(
        String permittedTenantId,
        OrderReportFilter filter);
}
```

Interface này không chứa `Aggregation`, `Criteria`, `Document` hoặc loại trả về phụ thuộc driver. Caller chỉ biết domain inputs và output DTO.

### 12.2. Implementation với MongoTemplate

File `OrderReportOperationsImpl.java`:

```java
package com.example.shop.orders;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;

public class OrderReportOperationsImpl
        implements OrderReportOperations {

    private final MongoTemplate template;

    public OrderReportOperationsImpl(MongoTemplate template) {
        this.template = template;
    }

    @Override
    public List<StatusRevenue> revenueByStatus(
            String permittedTenantId,
            OrderReportFilter filter) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant không hợp lệ");
        }
        if (filter == null) {
            throw new IllegalArgumentException(
                "Filter không hợp lệ");
        }
        if (filter.statuses().isEmpty()) {
            return List.of();
        }

        Criteria scoped = Criteria
            .where("tenantId").is(permittedTenantId)
            .and("archived").is(false)
            .and("status").in(filter.statuses())
            .and("createdAt")
                .gte(filter.fromInclusive())
                .lt(filter.toExclusive());

        if (filter.channel() != null) {
            scoped.and("channel").is(filter.channel());
        }
        if (filter.minimumAmountMinor() != null) {
            scoped.and("amountMinor")
                .gte(filter.minimumAmountMinor());
        }

        List<AggregationOperation> stages = new ArrayList<>();
        stages.add(Aggregation.match(scoped));
        stages.add(
            Aggregation.group("status")
                .count().as("orderCount")
                .sum("amountMinor").as("revenueMinor"));
        stages.add(
            Aggregation.project("orderCount", "revenueMinor")
                .and("_id").as("status")
                .andExclude("_id"));
        stages.add(
            Aggregation.sort(Sort.by(
                Sort.Order.desc("revenueMinor"),
                Sort.Order.asc("status"))));
        stages.add(Aggregation.limit(filter.maxGroups()));

        TypedAggregation<OrderDocument> pipeline =
            Aggregation.newAggregation(
                OrderDocument.class,
                stages.toArray(new AggregationOperation[0]));

        return template.aggregate(
            pipeline, StatusRevenue.class).getMappedResults();
    }
}
```

Đoạn implementation cố ý lặp **cùng ý tưởng** như `OrderReportQueryService` ở mục 10 để minh họa **hai lựa chọn vị trí đặt pipeline**. **Trong một ứng dụng thật, không duy trì hai bản copy đồng thời.** Hãy chuyển logic từ service sang fragment, hoặc trích thành một builder chung và để service/fragment cùng sử dụng **một implementation duy nhất**.

### 12.3. Ghép fragment vào repository

Sau khi quyết định dùng fragment, `OrderRepository` mở rộng interface mới:

```java
package com.example.shop.orders;

import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderReportOperations {

    // Giữ method annotation đơn giản để test đối chiếu
    // trong giai đoạn refactor.
    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': ?1, 'archived': false } }",
        "{ '$group': { '_id': '$status', 'orderCount': { '$sum': 1 }, 'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'status': '$_id', 'orderCount': 1, 'revenueMinor': 1 } }"
    })
    List<StatusRevenue> summarizeStatus(
        String permittedTenantId, String status);
}
```

Spring Data repository composition tìm implementation fragment theo quy ước tên `<FragmentInterface>Impl`; ở đây là `OrderReportOperationsImpl`. Cần đặt class trong package được repository scanning phát hiện hoặc đăng ký bean rõ ràng theo cấu hình. Nếu nhiều fragment hoặc thay postfix `Impl`, phải kiểm tra quy tắc discovery thực tế.

Đừng tạo một class tên `OrderRepositoryImpl` để kế thừa ngầm mọi method repository rồi bỏ qua cơ chế fragment hiện đại nếu không có lý do và hiểu đúng quy tắc Spring Data đang dùng.

### 12.4. Trách nhiệm của từng lớp

| Lớp | Trách nhiệm |
| --- | --- |
| Controller | Nhận request, chuẩn hóa input HTTP, không ghép BSON |
| Application service | Xác thực user, suy ra tenant được phép, áp policy sản phẩm |
| `OrderRepository` | Công bố API truy vấn của domain Order |
| `OrderReportOperations` | Hợp đồng nghiệp vụ cho truy vấn báo cáo tùy chọn |
| `OrderReportOperationsImpl` | Xây, thực thi pipeline và trả DTO |
| `MongoTemplate` | Mapping, kết nối, điều phối MongoDB aggregation |
| MongoDB server | Thực thi pipeline, xử lý index, sort/group/join |

**Quyền truy cập không tự sinh từ fragment.** Nếu người dùng có thể gọi report với một tenant khác, ứng dụng vẫn có rò rỉ dữ liệu. `permittedTenantId` phải được suy ra từ hoặc kiểm tra với authorization trước khi truyền vào repository.

### 12.5. Nhiều fragment trong một repository

Ví dụ ngoài bài:

```java
public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderReportOperations,
                OrderCustomWriteOperations {
}
```

Ở đây `OrderCustomWriteOperations` tượng trưng cho một fragment khác do dự án định nghĩa, không phải một API dựng sẵn. Có thể tách các năng lực **read/report** và **custom write** theo ranh giới rõ; tránh để một implementation khổng lồ nhận mọi nhiệm vụ chỉ vì cùng collection.

## 13. $facet: lúc pipeline không còn chỉ là ba stage

Yêu cầu mới: trả **một trang nhóm doanh thu** và **tổng số nhóm** để dựng pagination. Nếu gọi hai aggregation riêng, hai lần đọc có thể không phản ánh cùng trạng thái dữ liệu khi concurrent writes xảy ra; `$facet` cho phép chạy nhiều pipeline con trên cùng luồng đầu vào trong một aggregation.

### 13.1. Pipeline MongoDB minh họa

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] },
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
    }
  },
  {
    $project: {
      _id: 0,
      status: "$_id",
      orderCount: 1,
      revenueMinor: 1
    }
  },
  {
    $facet: {
      rows: [
        { $sort: { revenueMinor: -1, status: 1 } },
        { $skip: 0 },
        { $limit: 1 }
      ],
      totalGroups: [
        { $count: "value" }
      ]
    }
  }
])
```

Kết quả khái niệm:

```javascript
[
  {
    rows: [
      { status: "PAID", orderCount: 4,
        revenueMinor: NumberLong(230000) }
    ],
    totalGroups: [ { value: 2 } ]
  }
]
```

**Hai số đếm khác nhau**:

- `orderCount` trong `rows` đếm **đơn hàng thuộc nhóm status**.
- `totalGroups.value` đếm **số nhóm status sau `$group`**, ở đây là 2.

Nếu đặt `$facet` **trước `$group`**, nhánh `totalGroups: [{$count:"value"}]` sẽ đếm số **document order đầu vào**, ở đây là 6, không phải số nhóm. Đặt stage đúng chỗ quan trọng hơn việc chỉ biết tên `$facet`.

### 13.2. Tại sao $facet là tín hiệu chuyển sang template?

Một `@Aggregation` dài với `$facet` vẫn có thể chạy. Nhưng khi `rows` tùy sort, skip/limit, có một số nhánh thống kê bật/tắt theo filter, hay cần thay đổi group key, annotation sẽ khó đọc và dễ mắc lỗi mapping output.

Với template, có thể:

- Xây các stage **chung** (`$match`, `$group`, `$project`).
- Bổ sung `Aggregation.facet(...)` hoặc stage raw **do ứng dụng định nghĩa** theo API phiên bản Spring Data.
- Ánh xạ kết quả sang DTO có `rows` và `totalGroups`, thay vì cố coi nó là entity Order.
- Kiểm thử từng nhánh, đặc biệt tình huống **không có dữ liệu**.

Khi dùng pipeline có `$facet`, đầu ra thường có một document chứa các **array kết quả**. Vì vậy DTO output thay đổi và phải được thiết kế lại:

```java
public record FacetedOrderReport(
    java.util.List<StatusRevenue> rows,
    java.util.List<TotalGroups> totalGroups
) {
    public record TotalGroups(long value) {}
}
```

Không mặc định `Page<StatusRevenue>` từ repository tự có tổng nhóm chính xác cho aggregation phức tạp. Nếu Spring Data hỗ trợ bổ sung sort/limit bằng `Pageable` cho một query method, điều đó **không đồng nghĩa** framework tự tính đúng `totalGroups` cho mọi pipeline. Cần tự định nghĩa thống kê tổng hoặc thiết kế `Slice`/scroll khi không cần tổng.

### 13.3. Khi nào không cần facet?

Nếu API chỉ cần 10 nhóm doanh thu cao nhất, không cần `totalGroups` và không cần nhiều bảng phụ, pipeline `$group → $sort → $limit` là đủ. `$facet` làm output và kiểm thử phức tạp hơn; chỉ sử dụng khi **giải quyết đúng một yêu cầu có thật**.

Ngoài ra, `$facet` có giới hạn bộ nhớ/kích thước đầu ra của MongoDB; đừng đưa toàn bộ order và một tập kết quả không giới hạn vào các mảng facet rồi hy vọng `allowDiskUse` xử lý mọi giới hạn. Giảm đầu vào sớm, giới hạn rows và đo trên dữ liệu đại diện.

## 14. $lookup: khi phải phối hợp nhiều collection

Ví dụ Order có thể cần số khoản thanh toán thành công từ collection `payments`. Khi một pipeline báo cáo dùng join, team nên cân nhắc:

1. Dữ liệu có phù hợp để embed/denormalize theo yêu cầu đọc không?
2. Có thể tính trên một collection bằng materialized field đã được duy trì không?
3. Nếu dùng `$lookup`, khóa join và tenant có index phù hợp không?
4. Output là nhiều payment trên một order hay chỉ số tổng? Có cần `$unwind` không?
5. Ai sở hữu logic này: repository Order hay reporting/query service xuyên domain?

### 14.1. Ví dụ $lookup có khóa tenant

```javascript
db.orders.aggregate([
  { $match: {
      tenantId: "TENANT-A",
      archived: false
  }},
  {
    $lookup: {
      from: "payments",
      let: {
        orderId: "$_id",
        tenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$orderId", "$$orderId"] },
                { $eq: ["$tenantId", "$$tenant"] }
              ]
            }
          }
        },
        { $match: { state: "CAPTURED" } },
        { $project: { _id: 0, amountMinor: 1 } }
      ],
      as: "capturedPayments"
    }
  }
])
```

Stage `$lookup` tạo `capturedPayments` là **array** trên từng Order; nó không tự làm số document Order tăng. Nếu thêm `$unwind: "$capturedPayments"`, một Order có nhiều payment có thể được nhân thành nhiều document đầu ra. Nếu sau đó `$group` tổng tiền order mà không kiểm soát nhân bản, báo cáo có thể **đếm trùng**.

Trong hệ thống multi-tenant, filter chỉ theo `orderId` mà không ràng buộc tenant của payment có thể tạo lộ dữ liệu nếu ID không duy nhất ở phạm vi toàn hệ thống hoặc dữ liệu bị lỗi. Ví dụ minh họa thêm **cả orderId và tenantId** vào join; service vẫn phải xác minh tenant của caller.

### 14.2. Khi template/fragment thực sự giúp ích

Với các `$lookup` có pipeline con tùy trạng thái payment và thời gian, việc đặt các biểu thức `let`/`$expr` dài trong annotation dễ gây khó debug. Với template có thể dùng builders phù hợp hoặc `AggregationOperation` tùy chỉnh cho stage MongoDB mà phiên bản DSL chưa hỗ trợ.

Nhưng “dùng custom stage” không có nghĩa chấp nhận JSON tùy ý từ request. Luôn kiểm soát field path, operator, biến và tên collection tại application layer.

### 14.3. Ranh giới domain

Nếu report vừa đọc Order vừa join Payment vừa group theo Shipment, một `BillingReportQueryService` chuyên dụng có thể rõ ràng hơn `OrderRepository`. Fragment nên được sử dụng khi **hợp đồng vẫn thật sự thuộc repository Order**.

## 15. Sort, Pageable, giới hạn và kết quả tổng hợp

Một khác biệt quan trọng giữa truy vấn repository đơn giản và aggregation là ý nghĩa của **sort/limit/skip** phụ thuộc vào **vị trí stage**.

### 15.1. Sort trước hay sau group?

Trong ví dụ:

```javascript
[
  { $match: { tenantId: "TENANT-A", archived: false } },
  { $group: {
      _id: "$status",
      revenueMinor: { $sum: "$amountMinor" }
  }},
  { $sort: { revenueMinor: -1, _id: 1 } },
  { $limit: 2 }
]
```

`$sort` và `$limit` áp dụng cho **document nhóm**, nên có nghĩa “hai nhóm doanh thu lớn nhất”.

Nếu đẩy `$limit: 2` **trước `$group`**, pipeline chỉ cộng **hai order đầu luồng**, không phải mọi order của tenant. Không nên di chuyển stage giới hạn chỉ vì muốn query nhanh; nó có thể làm sai số liệu.

### 15.2. Pageable không tự giải mọi bài toán aggregation

Spring Data MongoDB có hỗ trợ các tham số đặc biệt như `Sort` và `Pageable` trên một số phương thức repository aggregation. Tuy nhiên cần kiểm tra:

- Sort được gắn vào **giai đoạn nào**, và sort key có còn tồn tại sau `$group`/`$project` không?
- Giới hạn/trang áp lên **document gốc**, **nhóm**, hay **array bên trong `$facet`**?
- Output có phải `List`, `Slice` hoặc kiểu khác được framework hỗ trợ ở phiên bản đang chạy?
- Tổng số nhóm được tính từ đâu? **Không mặc định** một đối tượng `Page` có count chính xác chỉ vì method nhận `Pageable`.

Với pipeline động và output có `$facet`, nên chủ động tạo stage `$sort/$skip/$limit` tại đúng vị trí, cùng một hợp đồng DTO rõ ràng cho tổng số nhóm hoặc cờ “còn trang tiếp theo”.

### 15.3. Pagination phải có sort quyết định

Ví dụ dùng `revenueMinor` giảm dần và `status` tăng dần để tránh thứ tự khó đoán khi hai nhóm có cùng tổng:

```javascript
{ $sort: { revenueMinor: -1, status: 1 } }
```

Nếu group theo một khóa không duy nhất hoặc có nhiều tổ hợp field, hãy thêm khóa phụ ổn định và phù hợp. Với dữ liệu đang thay đổi, `skip/limit` qua nhiều request vẫn có thể gặp trùng/bỏ sót nhóm khi thứ tự tổng tiền thay đổi; nếu cần báo cáo nhất quán tuyệt đối theo một snapshot, phải thiết kế thời điểm đọc, caching/materialization hoặc read concern/transaction phù hợp.

### 15.4. Không nhận sort key từ user mà không kiểm tra

Sai về ranh giới API:

```java
// PHẢN VÍ DỤ: sortProperty lấy trực tiếp từ request.
Sort.by(sortProperty);
```

Giải pháp tốt hơn là ánh xạ tham số đã được allowlist:

```java
String sortField = switch (sortBy) {
    case "revenue" -> "revenueMinor";
    case "count"   -> "orderCount";
    case "status"  -> "status";
    default -> throw new IllegalArgumentException(
        "sortBy không được hỗ trợ");
};
```

Đoạn này thuộc lớp xây query có `sortBy` kiểu `String` đã validate; chưa tự tạo stage sort. Nếu API cho người dùng chọn sort theo field **không có trong kết quả sau projection**, query có thể lỗi hoặc cho thứ tự không mong muốn.

## 16. Mapping: schema nguồn và schema kết quả là hai hợp đồng khác nhau

Các câu truy vấn repository đơn giản thường trả `OrderDocument`. Nhưng với aggregation, output có thể là:

- Document chỉ còn `status`, `orderCount`, `revenueMinor` sau group/project.
- Document có `rows[]` và `totalGroups[]` sau facet.
- Document có `capturedPayments[]` sau lookup.
- Document có `_id` là object tổng hợp nhiều field, không phải ID order gốc.

Vì vậy **không dùng entity nguồn làm DTO report** nếu pipeline đã thay đổi hình dạng dữ liệu.

### 16.1. _id trong $group không phải khóa chính gốc

```javascript
{
  $group: {
    _id: {
      status: "$status",
      channel: "$channel"
    },
    totalMinor: { $sum: "$amountMinor" }
  }
}
```

Document kết quả có `_id` là **object**:

```javascript
{
  _id: { status: "PAID", channel: "web" },
  totalMinor: NumberLong(150000)
}
```

Một DTO có field `String id` không thể tự giả định giá trị này là ID của order. Hoặc tạo DTO phản ánh khóa nhóm lồng nhau, hoặc `$project` đổi nó thành các field đầu ra:

```javascript
{
  $project: {
    _id: 0,
    status: "$_id.status",
    channel: "$_id.channel",
    totalMinor: 1
  }
}
```

Đây cũng là tín hiệu nên chuyển sang template: khi kiểu kết quả thay đổi theo lựa chọn group dimension, cần quản lý read model/mapper chặt chẽ thay vì hy vọng Spring Data tự đoán đúng mọi projection.

### 16.2. Cẩn trọng với số tiền và kiểu BSON

`$sum` có thể trả kiểu số khác nhau tùy dữ liệu đầu vào và quá trình nâng kiểu số. Khi `amountMinor` là BSON Int64 hợp lệ, Java `long` có thể phù hợp trong ví dụ. Nhưng với số tiền Decimal128, dữ liệu lẫn Double hoặc tổng có thể vượt giới hạn Long, cần DTO và converter theo chuẩn tài chính của hệ thống.

Không dùng một `double` để đại diện tiền đòi hỏi độ chính xác tuyệt đối. Nếu collection lưu số bằng String từ hệ thống cũ, `$sum` không tự đảm bảo diễn giải số như nghiệp vụ mong muốn; cần kiểm tra/migration hoặc biểu thức chuyển kiểu với chính sách lỗi minh bạch.

### 16.3. Kết quả rỗng có nhiều dạng

- `$group` theo `status` sau `$match` không có document phù hợp: thường **không có nhóm nào**.
- `$group` với `_id: null` trong một pipeline không có input: không được mặc định sẽ trả một hàng có tổng 0.
- `$facet` có thể trả một document chứa `rows: []` và `totalGroups: []`; nhánh `$count` khi không có input có thể trả array rỗng.

DTO cần thiết kế cho trường hợp không có dữ liệu; không gọi `get(0)` trên `totalGroups` mà không kiểm tra list rỗng.

## 17. Transaction, option thực thi và đường đọc reactive

Một lý do khác để dùng template là cần kiểm soát **cách thực thi** ngoài nội dung stage. Nhưng chọn template không tự cấp transaction hoặc quyền đọc mạnh hơn.

### 17.1. AggregationOptions

Khi pipeline nhiều nhóm/sort lớn, ứng dụng có thể cần cấu hình `AggregationOptions` theo phiên bản Spring Data, ví dụ chính sách `allowDiskUse`, collation hoặc cursor batch size:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

AggregationOptions options = AggregationOptions.builder()
    .allowDiskUse(true)
    .build();

Aggregation pipelineWithOptions =
    aggregation.withOptions(options);
```

Trong đoạn này, `aggregation` là biến `Aggregation` đã tạo trước. Cần xác nhận API và option được hỗ trợ bởi phiên bản Spring Data/MongoDB của dự án. `allowDiskUse(true)` **không có nghĩa mọi stage, mọi mảng trong facet được phép vượt các giới hạn**; vẫn phải hạn chế dữ liệu đầu vào/output và đo memory.

### 17.2. Transaction không tự khắc phục pipeline sai

Aggregation đọc nhiều collection với `$lookup` không tự động có cùng các bảo đảm như một transaction nhiều document ở mọi deployment/read concern. Nếu báo cáo cần snapshot nhất quán, hãy xác định rõ:

- MongoDB deployment và session/transaction manager có hỗ trợ không?
- Read concern nào được sử dụng, và dữ liệu của nhiều collection phải nhất quán tới mức nào?
- Kết quả sẽ được cache/materialize ở một thời điểm hay đọc live?
- Có tính cả dữ liệu đang thay đổi trong lúc báo cáo không?

Việc chuyển từ annotation sang template **không tự giải quyết** các quyết định này.

### 17.3. ReactiveMongoTemplate

Khi ứng dụng dùng reactive, `ReactiveMongoTemplate` thực thi aggregation và trả `Flux` theo kết quả:

```java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<StatusRevenue> revenueReactive(
        ReactiveMongoTemplate template,
        Aggregation pipeline) {
    return template.aggregate(
        pipeline, "orders", StatusRevenue.class);
}
```

Đây là method minh họa đặt trong class phù hợp, với pipeline đã chứa filter tenant. Trong reactive, publisher chỉ chạy khi được subscribe; cần quản lý hủy, timeout, backpressure và tránh gọi blocking `MongoTemplate` trên event loop.

Nếu domain API muốn reactive repository fragment, có thể định nghĩa fragment trả `Flux<StatusRevenue>` và dùng `ReactiveMongoTemplate` trong implementation. **Không** viết fragment reactive rồi gọi `block()` bên trong để chuyển sang MongoTemplate đồng bộ; điều đó phá vỡ đặc tính không chặn luồng.

### 17.4. Khi output rất lớn

`MongoTemplate.aggregate(...).getMappedResults()` gom kết quả vào `List`. Với báo cáo trả hàng trăm nghìn dòng, cân nhắc `aggregateStream(...)`, reactive `Flux`, limit hoặc cách phân trang phù hợp. Nhưng streaming kết quả không làm `$group`/`$sort` trên server bớt tính toán nếu pipeline vẫn phải xử lý toàn bộ dữ liệu.

## 18. Kiểm thử tích hợp: chứng minh hai cách tạo cùng kết quả

Khi refactor từ `@Aggregation` sang template/fragment, cần xác minh **ngữ nghĩa truy vấn không đổi**. Unit test chỉ mock repository trả đúng hai hàng chưa đủ: nó không xác nhận `$match` có tenant, mapping `_id` sau group, phép tính tổng số hoặc cách Spring Data bind tham số.

Tốt nhất dùng **MongoDB instance test cô lập**, seed dữ liệu BSON thật bằng driver rồi gọi cả annotation và fragment. Sau đó thêm test cho các điều kiện mà annotation cũ không hỗ trợ.

### 18.1. JUnit 5 + @DataMongoTest

File `OrderRepositoryAggregationIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Set;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderRepositoryAggregationIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    private static Document order(
            String id, String tenantId, String status,
            String channel, long amountMinor,
            String createdAt, boolean archived) {
        return new Document("_id", id)
            .append("tenantId", tenantId)
            .append("status", status)
            .append("channel", channel)
            .append("amountMinor", amountMinor)
            .append("createdAt", Date.from(Instant.parse(createdAt)))
            .append("archived", archived);
    }

    private static OrderReportFilter filter(
            Set<String> statuses, String channel,
            Long minimumAmountMinor) {
        return new OrderReportFilter(
            Instant.parse("2026-11-01T00:00:00Z"),
            Instant.parse("2026-12-01T00:00:00Z"),
            statuses, channel, minimumAmountMinor, 10);
    }

    @BeforeEach
    void seed() {
        // Chỉ thực hiện trên database MongoDB TEST cô lập.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("A-101", "TENANT-A", "PAID", "web",
                100000L, "2026-11-10T09:00:00Z", false),
            order("A-102", "TENANT-A", "PAID", "app",
                80000L, "2026-11-10T10:00:00Z", false),
            order("A-103", "TENANT-A", "PAID", "web",
                20000L, "2026-11-11T09:00:00Z", false),
            order("A-104", "TENANT-A", "NEW", "web",
                50000L, "2026-11-11T10:00:00Z", false),
            order("A-105", "TENANT-A", "PAID", "app",
                35000L, "2026-11-12T10:00:00Z", true),
            order("A-106", "TENANT-A", "NEW", "app",
                40000L, "2026-11-12T11:00:00Z", false),
            order("A-107", "TENANT-A", "CANCELLED", "web",
                60000L, "2026-11-13T09:00:00Z", false),
            order("A-108", "TENANT-A", "PAID", "web",
                30000L, "2026-11-14T09:00:00Z", false),
            order("B-201", "TENANT-B", "PAID", "web",
                999999L, "2026-11-13T09:00:00Z", false)
        ));
    }

    @Test
    void fixedAnnotationAggregationMatchesExpectedPaidGroup() {
        List<StatusRevenue> rows = repository.summarizeStatus(
            "TENANT-A", "PAID");

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 4L, 230000L));
    }

    @Test
    void fragmentProducesSameResultForPaidAndNew() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), null, null));

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 4L, 230000L),
            new StatusRevenue("NEW", 2L, 90000L));
    }

    @Test
    void dynamicChannelFilterDoesNotMixTenants() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), "web", null));

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 3L, 150000L),
            new StatusRevenue("NEW", 1L, 50000L));
    }

    @Test
    void amountThresholdAppliesBeforeGrouping() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), null, 40000L));

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 2L, 180000L),
            new StatusRevenue("NEW", 2L, 90000L));
    }

    @Test
    void upperTimeBoundaryIsExclusive() {
        OrderReportFilter oneDay = new OrderReportFilter(
            Instant.parse("2026-11-11T00:00:00Z"),
            Instant.parse("2026-11-12T00:00:00Z"),
            Set.of("PAID", "NEW"), null, null, 10);

        List<StatusRevenue> rows =
            repository.revenueByStatus("TENANT-A", oneDay);

        assertThat(rows).containsExactly(
            new StatusRevenue("NEW", 1L, 50000L),
            new StatusRevenue("PAID", 1L, 20000L));
    }

    @Test
    void emptyStatusesMustNotExpandQueryToAllStatuses() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A", filter(Set.of(), null, null));
        assertThat(rows).isEmpty();
    }

    @Test
    void invalidStatusIsRejected() {
        assertThatThrownBy(
            () -> filter(Set.of("UNKNOWN"), null, null))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void reportDoesNotModifyStoredOrder() {
        repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), null, null));

        Document stored = template.getCollection("orders")
            .find(new Document("_id", "A-101"))
            .first();

        assertThat(stored).isNotNull();
        assertThat(stored.getString("status")).isEqualTo("PAID");
        assertThat(stored.getLong("amountMinor"))
            .isEqualTo(100000L);
        assertThat(stored.containsKey("revenueMinor")).isFalse();
        assertThat(stored.containsKey("orderCount")).isFalse();
    }
}
```

**Cảnh báo quan trọng:** `collection.deleteMany(new Document())` xóa **toàn bộ collection `orders` của database đang kết nối**. Phải sử dụng MongoDB **test cô lập**, chẳng hạn Testcontainers với cấu hình test connection riêng. Tuyệt đối không chạy code test này trên production hoặc database dùng chung.

Ví dụ dùng package `@DataMongoTest` phổ biến của Spring Boot 3.x; package/test slice có thể thay đổi khi nâng major version. Cần kiểm tra dependency/test configuration đang chạy và khả năng **repository scanning tìm `OrderReportOperationsImpl`**. `@DataMongoTest` có thể không load các service `@Service` thông thường; test này gọi fragment qua repository để xác minh wiring, không cần load `OrderReportQueryService` ở mục 10.

### 18.2. Mỗi test bắt được lỗi gì?

| Test | Lỗi có thể phát hiện |
| --- | --- |
| `fixedAnnotationAggregation...` | Annotation bind sai status/tenant hoặc group/project mapping sai |
| `fragmentProducesSameResult...` | Fragment lắp sai hoặc tổng của hai trạng thái không đúng |
| `dynamicChannelFilter...` | Bỏ filter channel hoặc rò rỉ tenant B |
| `amountThreshold...` | Đặt ngưỡng tiền lên `revenueMinor` sau group thay vì `amountMinor` trước group |
| `upperTimeBoundaryIsExclusive` | Dùng `lte(to)` thay cho `lt(to)` hoặc tính sai ngày UTC |
| `emptyStatuses...` | Tập trạng thái rỗng vô tình mở rộng thành tất cả trạng thái |
| `invalidStatus...` | API cho phép status ngoài allowlist |
| `reportDoesNotModifyStoredOrder` | Nhầm output aggregation với entity nguồn hoặc lệnh ghi |

### 18.3. Debug bằng các tiền tố pipeline

Nếu tổng khác kỳ vọng, đừng thay cả pipeline ngay. Chạy lần lượt:

```javascript
// 1. Kiểm tra số ORDER sau $match:
db.orders.aggregate([
  { $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] }
  }},
  { $count: "matchedOrders" }
])
// [{ matchedOrders: 6 }]

// 2. Thêm $group, chưa sort/limit:
db.orders.aggregate([
  { $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] }
  }},
  { $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
  }}
])
// PAID: 4/230000; NEW: 2/90000 (thứ tự chưa bảo đảm).
```

Với template, có thể lấy các `AggregationOperation` đã xây và thực thi pipeline tiền tố. Nếu `$match` đúng 6 document mà tổng sai, hãy kiểm tra kiểu BSON/giá trị của `amountMinor` và logic `$group`. Nếu tiền tố đã sai 5 document, kiểm tra quyền tenant, `archived` hoặc filter thời gian trước khi chỉnh accumulator.

### 18.4. Ma trận kiểm thử cần mở rộng

| Tình huống | Kỳ vọng |
| --- | --- |
| Tenant không có order | Không có nhóm giả |
| Order tenant khác cùng status | Không góp vào kết quả |
| `archived=true` | Không được tính vào doanh thu active |
| `archived` thiếu trong legacy | Không tự coi là false; cần policy migration/compatibility |
| `amountMinor` null/String hoặc quá lớn | Có validation và xử lý số rõ, không âm thầm cộng sai |
| `channel` null/không tồn tại | Không tự hiểu thành mọi kênh khi request yêu cầu một kênh cụ thể |
| Tập trạng thái rỗng | Trả rỗng, fail-closed |
| Thời gian nằm đúng toExclusive | Bị loại vì upper bound exclusive |
| Tổng hai nhóm bằng nhau | Có khóa sort phụ xác định |
| `$facet` không có nhóm | `rows: []`, `totalGroups` có thể là array rỗng |
| `$lookup` nhiều payment cùng order | Không đếm trùng đơn khi unwind/group |
| Fragment không được phát hiện | Test wiring thất bại; sửa package, postfix hoặc bean registration |
| Dữ liệu đổi khi đang phân trang | Có consistency strategy phù hợp |

## 19. Hiệu năng: chuyển code không thay kế hoạch MongoDB

Đối với cùng BSON pipeline và cùng options, MongoDB không biết nó bắt nguồn từ repository annotation, `MongoTemplate` hay fragment. Chênh lệch đáng kể thường đến từ **pipeline sinh ra khác nhau**, cách mapping, tài nguyên Java, hoặc cấu hình execution.

### 19.1. Index ứng viên

Với filter thường xuyên theo tenant, archive, status và khoảng thời gian:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    archived: 1,
    status: 1,
    createdAt: 1
  },
  { name: "idx_tenant_archive_status_date" }
)
```

Khi kênh luôn được lọc, có thể kiểm tra thêm một ứng viên:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    archived: 1,
    channel: 1,
    status: 1,
    createdAt: 1
  },
  { name: "idx_tenant_archive_channel_status_date" }
)
```

Đây là **index ứng viên**, không phải yêu cầu tạo cả hai trong mọi dự án. Thứ tự các field, tính chọn lọc, số lượng tenant, tần suất có channel, kích thước index và chi phí ghi đều ảnh hưởng lựa chọn. Nếu `createdAt` là range, các key đứng sau nó có thể không được tận dụng cho một số mẫu truy vấn như kỳ vọng. Đo với workload thật.

Nếu `$lookup` đọc payment theo tenant/order/state, cân nhắc index trên collection `payments` như `{tenantId:1, orderId:1, state:1}`, rồi kiểm tra `explain`. Khả năng tối ưu join qua `$expr` và index phụ thuộc phiên bản MongoDB, dạng biểu thức và phân bố dữ liệu.

### 19.2. Explain bản pipeline thật

```javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] },
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
    }
  },
  { $sort: { revenueMinor: -1, _id: 1 } }
])
```

Quan sát:

- `totalDocsExamined` và `totalKeysExamined` khi kế hoạch cung cấp những chỉ số đó.
- Số document `$match` trả và số nhóm sau `$group`.
- Có collection scan, index scan hoặc các stage sort dùng bộ nhớ lớn không.
- Thời gian execution, tài nguyên và số document đầu ra.
- `$facet`/`$lookup` có kéo theo lượng dữ liệu lớn hoặc làm nhân bản document không.

`$sort` **theo tổng `revenueMinor` sau `$group`** không thể mặc định tận dụng thứ tự index trên `amountMinor` của document gốc. Index giúp chọn dữ liệu vào pipeline, nhưng stage group/sort tổng hợp vẫn có chi phí riêng.

### 19.3. Đừng tự đặt @Aggregation là chậm

Nếu annotation tạo BSON đúng và ổn định, chuyển nguyên văn sang DSL không phải tối ưu. Hãy đặt câu hỏi:

1. Đường đọc có bao nhiêu document?
2. Stage nào là bottleneck?
3. Có thể đẩy `$match` sớm theo field gốc không?
4. Có tạo mảng `$push` quá lớn hoặc kết quả `$facet` quá rộng không?
5. Có thể lưu trước giá trị tổng hợp khi đọc nhiều hơn ghi mà nghiệp vụ cho phép không?
6. Có cần projection giảm dữ liệu phải đọc/trả về không?

Nếu câu trả lời yêu cầu đổi cấu trúc pipeline để tối ưu, **template giúp thử nghiệm và tái sử dụng**; lợi ích đến từ **thiết kế BSON mới**, không từ tên API Java.

## 20. Refactor an toàn từ @Aggregation sang fragment

Một lộ trình tránh thay đổi ngữ nghĩa ngoài ý muốn:

1. **Đóng băng hợp đồng đầu ra**: ghi lại DTO, thứ tự, kiểu số, cách xử lý rỗng và điều kiện tenant.
2. **Viết integration test cho annotation cũ** trên dữ liệu BSON có tenant khác, archive và các biên thời gian.
3. **Chép pipeline sang template** bằng `AggregationOperation` có thứ tự tương đương; xác minh BSON và kết quả.
4. **Tách filter động** thành type có validation, quy tắc fail-closed và allowlist sort/status/channel.
5. **Đưa vào repository fragment** nếu API cần thuộc domain Order; không nhân đôi implementation.
6. **Chuyển caller** sang method mới, giữ method annotation cũ trong thời gian đối chiếu nếu cần.
7. **Chạy test so sánh** kết quả hai đường trên cùng dữ liệu, bao gồm count/tổng/thứ tự.
8. **Đo explain/performance** trên tập đại diện, rà index và option execution.
9. **Xóa pipeline annotation cũ** sau khi mọi caller đã chuyển, tránh hai định nghĩa báo cáo khác nhau tồn tại âm thầm.
10. **Theo dõi sau rollout**: tỷ lệ lỗi aggregation, query latency, docs examined, heap, và sai lệch báo cáo so với đối soát.

### 20.1. Không trích helper chỉ để che syntax

Một helper như `buildAggregation(filter)` có giá trị khi nó gom **logic tái sử dụng thật**, không phải khi nó rải một pipeline năm dòng qua mười lớp. Nên đặt helper theo ý nghĩa nghiệp vụ: `activeOrdersOfTenant`, `sumAmountByStatus`, `revenueGroupSort`... nhưng tránh tạo một framework query tổng quát quá mức chỉ để phục vụ một endpoint.

### 20.2. Khi nào nên để repository annotation và fragment cùng tồn tại?

Có thể giữ các method `@Aggregation` đơn giản trong repository và dùng fragment cho truy vấn phức tạp **nếu chúng phục vụ hai hợp đồng khác nhau**. Không cần chuyển tất cả annotation sang template trong một đợt. Mục tiêu là nơi đặt code **phù hợp với độ biến thiên và trách nhiệm**, không thống nhất máy móc mọi method theo một kỹ thuật.

## 21. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Annotation dài hàng trăm dòng, mỗi endpoint copy một bản | Pipeline có nhiều stage/filter tùy chọn nhưng vẫn bị đặt trong `@Aggregation` | Chuyển sang template, tách các operation có ý nghĩa rồi cân nhắc fragment |
| Chuyển sang template nhưng số liệu không đổi và vẫn chậm | Không đổi BSON/index, chỉ đổi API Java | Dùng `explain`, tối ưu stage và schema thay vì kỳ vọng template nhanh tự động |
| Fragment không được ghép vào repository | Sai tên hậu tố `Impl`, package scanning hoặc cấu hình bean | Kiểm tra fragment interface/implementation và integration test khởi tạo context |
| `$group` trả `_id` như status, DTO lại mong ID order | Nhầm group key với `@Id` entity nguồn | Dùng DTO kết quả và projection rõ |
| Báo cáo có cả order tenant khác | `$match` thiếu tenant hoặc optional OR thoát khỏi ràng buộc | Đặt tenant bắt buộc ở group AND ngoài và test anti-leak |
| Tập statuses rỗng làm hiện tất cả trạng thái | Service bỏ filter khi input rỗng | Fail-closed hoặc quy định tường minh giá trị ALL có quyền |
| Tổng tiền khác giữa annotation và fragment | Trật stage, khác filter date/archive, mapping sai tên field | Test so sánh cùng BSON và tiền tố pipeline |
| `$limit` trước group làm doanh thu thấp | Giới hạn document gốc thay vì nhóm | Đặt limit sau `$group`/`$sort` theo mục đích |
| Trang báo cáo có rows đúng nhưng totalCount sai | Đếm order thay vì nhóm hoặc page count không được tính | `$facet` sau group với nhánh `$count` đúng vị trí |
| Có `Pageable` nhưng không có tổng nhóm chính xác | Lầm tưởng framework tự xây count cho mọi aggregation | Định nghĩa rõ `Slice`/facet/count pipeline |
| Raw stage bỏ qua tên field `@Field` | Lẫn tên property Java và tên BSON | Dùng typed DSL nơi phù hợp; kiểm tra pipeline gửi server |
| `$lookup` làm số order tăng | Unwind mảng payment rồi group thiếu điều kiện distinct | Thiết kế cardinality theo order và key tenant |
| Sort key do client gửi làm query không hợp lệ | Không allowlist sort field hoặc field bị loại trước stage sort | Mapping sort key rõ và kiểm tra schema trung gian |
| Report có doanh thu NaN/sai kiểu | Giá BSON String/Double/null, dữ liệu legacy | Validation, chuyển kiểu có policy, kiểu tiền đúng |
| Phương thức fragment reactive gọi `block()` | Trộn blocking với reactive | Dùng `ReactiveMongoTemplate` và trả `Flux`/`Mono` |
| Test mock xanh nhưng pipeline lỗi ở server | Chỉ mock `MongoTemplate`, không test mapping và operator thật | Testcontainers/MongoDB thật, assert cả kết quả và wiring |
| Đưa `$facet` đầu pipeline khiến đọc quá rộng | Chưa lọc data trước khi phân nhánh | `$match` sớm và kiểm tra giới hạn/hiệu năng |
| `allowDiskUse` được bật nhưng facet vẫn lỗi | Có giới hạn riêng với facet/output | Giảm nhóm, giảm kết quả, thiết kế pipeline khác |

## 22. Checklist chọn công cụ

Trước khi chọn nơi đặt pipeline, tự trả lời:

1. **Pipeline có cố định không?** Nếu chỉ bind giá trị cho stage cố định, `@Aggregation` có thể là đủ.
2. **Điều kiện có tùy chọn hoặc thay đổi cấu trúc không?** Nếu có, `MongoTemplate`/`Aggregation` DSL thường dễ bảo trì hơn.
3. **Output schema có ổn định không?** Nếu không, có thể cần nhiều DTO hoặc một contract linh hoạt được kiểm soát.
4. **Có nhiều nhánh `$facet` hoặc `$lookup` không?** Cân nhắc DSL/raw operations tin cậy và test riêng từng nhánh.
5. **Caller nên biết template hay chỉ repository domain?** Nếu cần một repository API thống nhất, chọn fragment.
6. **Báo cáo thuộc một domain hay xuyên nhiều domain?** Với báo cáo tổng hợp rộng, query service chuyên biệt có thể rõ hơn fragment của một entity.
7. **Có những ràng buộc bắt buộc nào?** Tenant, soft-delete, quyền, thời gian, trạng thái hợp lệ phải được giữ trong mọi nhánh.
8. **Pagination đang áp lên đơn gốc, nhóm hay array facet?** Đặt `$sort/$skip/$limit` đúng chỗ, xác định tổng nhóm.
9. **Có cần option thực thi?** Xác định read concern, disk use, collation, stream/reactive và hạ tầng hỗ trợ.
10. **Có test hồi quy trên BSON thật chưa?** So sánh annotation cũ và fragment mới bằng số liệu/tập đích/thứ tự.
11. **Đã đo kế hoạch thực thi chưa?** Xác nhận index và số document quét trước khi tuyên bố refactor cải thiện hiệu năng.
12. **Có đang duy trì hai bản pipeline giống nhau không?** Trích logic chung hoặc xóa đường cũ sau chuyển đổi.

### 22.1. Ma trận quyết định nhanh

| Hoàn cảnh | Lựa chọn thường hợp lý |
| --- | --- |
| Ba stage cố định, chỉ tenant và status là tham số | `@Aggregation` |
| Filter động theo channel/amount/time và sort tùy chọn | `MongoTemplate` + `Aggregation` |
| Pipeline động nhưng caller chỉ nên thấy `orderRepository.report(...)` | `MongoTemplate` **bên trong repository fragment** |
| Báo cáo join ba domain và xuất nhiều cấu trúc khác nhau | Dedicated reporting/query service |
| Chỉ tìm order có item thỏa điều kiện, không cần biến đổi array | Derived query/`@Query`/`Criteria.elemMatch` có thể đơn giản hơn aggregation |
| Cần hiệu năng tốt hơn nhưng pipeline cố định hiện đang chậm | Phân tích `explain`/index/schema trước, **không đổi API chỉ vì tốc độ** |

## 23. Bài tập vận dụng

Một nền tảng bán hàng có collection `sales`:

```javascript
{
  _id: "SALE-001",
  tenantId: "TENANT-X",
  state: "PAID",
  channel: "web",
  currency: "VND",
  grossMinor: NumberLong(250000),
  occurredAt: ISODate("2026-11-10T09:00:00Z"),
  deleted: false
}
```

Giai đoạn đầu, team có repository method `@Aggregation` cố định: group theo `state` và tính `saleCount`, `grossTotal` trong một tenant.

Sau đó, sản phẩm yêu cầu thêm:

- Khoảng thời gian tùy chọn với `fromInclusive` và `toExclusive`.
- Có thể lọc `channel` hoặc `currency`; chỉ cộng dữ liệu cùng tiền tệ, không cộng VND với USD vào một tổng không có quy đổi.
- Có thể nhóm theo `state` hoặc `channel`.
- Phân trang **nhóm kết quả** cùng một trường tổng số nhóm.
- Không được đưa `deleted=true` hoặc tenant khác vào kết quả.
- Một số báo cáo cần join collection `refunds`.

**Yêu cầu thực hiện:**

1. Viết phiên bản `@Aggregation` đơn giản chỉ có filter tenant, `deleted=false`, group và project.
2. Nêu ít nhất ba dấu hiệu khiến việc tiếp tục viết biến thể annotation riêng cho từng tổ hợp không còn hợp lý.
3. Định nghĩa `SalesReportFilter` với validation về thời gian, tập status, currency và giới hạn kích thước trang.
4. Xây một `List<AggregationOperation>` động với filter tenant/deleted bắt buộc, filter tùy chọn, group key lấy từ allowlist và sort theo trường được phép.
5. Viết fragment `SalesReportOperations` và `SalesReportOperationsImpl`, ghép vào `SalesRepository`.
6. Thêm `$facet` **sau group** để tạo `rows[]` và `totalGroups[]`. Chỉ rõ vì sao đếm trước group trả một số khác.
7. Nếu join refunds theo `saleId`, thêm ràng buộc tenant ở `$lookup`; đề xuất cách tránh đếm trùng sale khi có nhiều refunds.
8. Định nghĩa DTO của output sau group và DTO bọc facet. Không dùng `SalesDocument` làm entity output báo cáo.
9. Seed ít nhất một sale tenant khác, một sale deleted, một sale ngoại tệ và một sale ngoài kỳ; kiểm thử không sai tổng.
10. So sánh `explain` trước/sau khi tạo index phù hợp, đối chiếu số document examined và chi phí group/sort.
11. Thử dùng repository `@Aggregation` với `Pageable` rồi đánh giá xem nó có cung cấp **tổng số nhóm** chính xác cho hợp đồng API này không.
12. Lập kế hoạch refactor theo hai giai đoạn, bảo đảm có test so sánh annotation cũ với fragment mới trước khi bỏ đường cũ.

**Định hướng:** sử dụng cùng một filter tenant/deleted ở cấp `$match` đầu pipeline; tuyệt đối không ghép nguyên JSON người dùng truyền vào. Group key là giá trị từ allowlist, không phải field name tùy ý. Các loại tiền tệ phải được tách nhóm hoặc có bước quy đổi theo tỷ giá và thời điểm được nghiệp vụ xác nhận. `$facet` chỉ cần thiết nếu API yêu cầu nhiều nhánh kết quả; không bắt buộc cho mọi báo cáo.

## 24. Tài liệu tham khảo

- Spring Data MongoDB — [Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): query/aggregation trên repository và tham số.
- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): xây pipeline bằng Aggregation DSL, mapping và expression.
- Spring Data MongoDB — [Aggregation API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/Aggregation.html): builder `match`, `group`, `project`, `sort`, `limit`.
- Spring Data Commons — [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): repository fragments, interface và implementation discovery.
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): ngữ nghĩa stage và dòng document.
- MongoDB Manual — [`$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/): các nhánh con và cấu trúc kết quả.
- MongoDB Manual — [`$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): join và pipeline con.
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): thứ tự stage và optimizer.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): đọc query plan và số liệu thực thi.

## Ghi nhớ

**Giữ `@Aggregation` khi pipeline cố định, nhỏ gọn và dễ hiểu. Chuyển sang `MongoTemplate` khi cấu trúc hoặc điều kiện pipeline trở nên động, nhiều nhánh và cần kiểm soát DSL, DTO, option hoặc debug từng stage. Dùng repository fragment khi muốn bọc pipeline đó sau một API repository thuộc domain rõ ràng.** Template và fragment có thể kết hợp: fragment chứa template, không phải một cách truy vấn khác ở server. Chuyển đổi an toàn đòi hỏi giữ điều kiện tenant/quyền, xác định schema đầu ra sau `$group`/`$facet`, kiểm thử trên BSON thực, đối chiếu số liệu với đường cũ và đo `explain`. **Không chuyển API Java với kỳ vọng MongoDB tự chạy nhanh hơn khi BSON pipeline không đổi.**
