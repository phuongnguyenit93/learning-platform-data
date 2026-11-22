# Cập nhật bằng aggregation pipeline với AggregationUpdate

## 1. Vì sao cần một cách cập nhật khác Update thông thường?

Trong chương **Ghi và cập nhật** của **Spring Data MongoDB**, ta đã có thể dùng `MongoTemplate` kết hợp `Query` và `Update` để sửa document mà không cần tải toàn bộ entity. Ví dụ `Update.set("status", "ACTIVE")` gán trạng thái mới, còn `Update.inc("quantity", 1)` tăng số lượng bằng một phép cập nhật trên MongoDB.

Nhưng đôi khi giá trị cần ghi **phụ thuộc vào chính các field đang nằm trên server**. Một hóa đơn có `quantity`, `unitPriceVnd`, `shippingFeeVnd` và `discountVnd`; ứng dụng muốn tính lại:

\[
\text{totalVnd} = \text{quantity} \times \text{unitPriceVnd}
                 + \text{shippingFeeVnd} - \text{discountVnd}
\]

Nếu làm theo cách “đọc hóa đơn → tính trong Java → ghi lại” thì giữa lần đọc và lần ghi, một request khác có thể thay số lượng hoặc phí vận chuyển. Kết quả cuối cùng có nguy cơ bị tính từ trạng thái cũ.

**Aggregation pipeline update** cho phép MongoDB tính biểu thức dựa trên field của từng document ngay khi thực hiện lệnh cập nhật. Spring Data MongoDB cung cấp `AggregationUpdate` để xây dựng kiểu cập nhật này:

~~~java
AggregationUpdate update = Aggregation.newUpdate()
        .set("totalVnd")
        .toValue(/* biểu thức aggregation */);
~~~

Đây là ví dụ khung cú pháp; những đoạn đầy đủ phía dưới dùng biểu thức thực tế. Một phép cập nhật trên **một document** vẫn có tính nguyên tử ở cấp document. Nếu điều kiện ghi phù hợp, pipeline có thể tính và lưu kết quả trên trạng thái document được MongoDB xử lý tại thời điểm cập nhật, không phải trên một bản sao vừa được đọc về Java.

### Kết quả cần đạt sau bài học

1. Phân biệt `Update` với `AggregationUpdate`, và phân biệt **aggregation update** với `MongoTemplate.aggregate(...)`.
2. Dùng `Aggregation.newUpdate()` và `MongoTemplate.updateFirst/updateMulti` để tính field từ những giá trị đang lưu.
3. Hiểu ý nghĩa của `$set`, `$unset`, `$add`, `$multiply`, `$ifNull`, `$cond` và `$map` trong update pipeline.
4. Tránh bẫy dấu `$`, tên field BSON, thứ tự stage và sự khác biệt giữa toán tử update với aggregation expression.
5. Kết hợp filter, tenant, kiểm tra version và xử lý kết quả để giữ bất biến nghiệp vụ khi có concurrent writes.
6. Kiểm thử nguyên vẹn BSON, trạng thái trước/sau, field thiếu và hiệu năng trên MongoDB thật.

> Ngữ cảnh ví dụ: Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB từ **4.2 trở lên** (khả năng update bằng aggregation pipeline được MongoDB giới thiệu từ phiên bản 4.2). Chi tiết API và các toán tử expression khả dụng cần được kiểm tra theo phiên bản Spring Data/driver/server của dự án.

## 2. Ba cơ chế dễ bị nhầm lẫn

| Cơ chế | Ví dụ | Dữ liệu được đưa cho MongoDB | Mục đích |
|---|---|---|---|
**Update thông thường** | `new Update().set("status", "ACTIVE").inc("quantity", 1)` | Document chứa các **update operators** như `$set`, `$inc` | Cập nhật field hoặc thao tác atomic đã có toán tử trực tiếp |
**AggregationUpdate** | `Aggregation.newUpdate().set("totalVnd").toValue(expression)` | **Mảng các aggregation pipeline stages** trong lệnh update | Tính và biến đổi field từ trạng thái document trên server |
**Aggregation truy vấn** | `mongo.aggregate(pipeline, Source.class, Report.class)` | Pipeline thực thi như một **truy vấn/tổng hợp** | Lọc, nhóm, tính và trả kết quả; không mặc nhiên ghi dữ liệu nguồn |

Ví dụ BSON của update thông thường:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  { $inc: { quantity: 1 } }
);
~~~

Ví dụ **aggregation pipeline update**:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    {
      $set: {
        totalVnd: {
          $subtract: [
            {
              $add: [
                { $multiply: ["$quantity", "$unitPriceVnd"] },
                "$shippingFeeVnd"
              ]
            },
            "$discountVnd"
          ]
        }
      }
    }
  ]
);
~~~

Hãy nhìn **tham số thứ hai** của `updateOne`: update thông thường dùng một *document chứa update operator*, còn pipeline update dùng **một array chứa các stage**. Trong pipeline, `$set` là **aggregation stage** và giá trị bên phải được tính như **aggregation expression**. Nó không hoàn toàn giống ngữ nghĩa của toán tử `$set` trong update document thông thường.

## 3. Những stage MongoDB cho phép trong update pipeline

MongoDB không chấp nhận mọi aggregation stage trong update pipeline. Các stage phù hợp bao gồm:

| Stage | Tác dụng khi cập nhật document |
|---|---|
| `$set` hoặc `$addFields` | Tạo hoặc thay field từ một expression |
| `$project` | Xác định lại các field còn được giữ trong document |
| `$unset` | Loại field khỏi document |
| `$replaceRoot` hoặc `$replaceWith` | Tạo lại document root từ expression |

Các stage dành cho đọc/tổng hợp như `$match`, `$sort`, `$group`, `$lookup`, `$unwind`, `$out` hay `$merge` **không được sử dụng tùy ý như stage của update pipeline**. Muốn chọn document nào được cập nhật, đặt điều kiện ở **`Query`/filter** của `updateFirst` hoặc `updateMulti`, không thêm một `$match` vào danh sách update stages.

Ví dụ:

~~~javascript
// Đúng: chọn document bằng filter của lệnh update,
// sau đó pipeline chỉ gồm các stage được phép.
db.invoices.updateMany(
  { tenantId: "tenant-a", status: "DRAFT" },
  [
    { $set: { reviewed: true } },
    { $unset: "oldStatusText" }
  ]
);
~~~

Ở đây `$unset` xóa field cũ, còn filter `status = DRAFT` nằm ngoài pipeline. Nếu phép biến đổi cần join nhiều collection để quyết định dữ liệu, hãy xem lại mô hình nghiệp vụ: có thể cần bước đọc/aggregation riêng, transaction hoặc một read model chuyên dụng, thay vì kỳ vọng `AggregationUpdate` cho phép toàn bộ pipeline báo cáo.

### Thứ tự stage có ý nghĩa

Các stage pipeline được đánh giá theo **thứ tự**. Stage sau nhìn thấy kết quả của stage trước. Trong một stage `$set` chứa nhiều biểu thức, **không dựa vào thứ tự liệt kê field** để giả định biểu thức bên phải của một field sẽ nhìn thấy giá trị của field khác vừa được gán trong cùng stage.

Ví dụ nếu cần ghi `subtotal` rồi mới tính `total` từ `subtotal` mới, có thể dùng **hai stage tách biệt**:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    { $set: { subtotalVnd: { $multiply: ["$quantity", "$unitPriceVnd"] } } },
    { $set: { totalVnd: { $add: ["$subtotalVnd", "$shippingFeeVnd"] } } }
  ]
);
~~~

Không tự động suy luận số stage Spring Data sẽ tạo từ một chuỗi builder nếu chưa kiểm tra BSON; khi sự phụ thuộc giữa các phép tính quan trọng, hãy xác minh pipeline kết quả hoặc dùng biểu thức trực tiếp không phụ thuộc vào field vừa ghi.

## 4. Mô hình hóa hóa đơn bằng Spring Data MongoDB

Ví dụ sử dụng một hóa đơn đơn giản, số tiền biểu diễn bằng **số nguyên VND** để tập trung vào cơ chế pipeline. Với tiền tệ có phần thập phân, có thể thiết kế `BigDecimal`/BSON Decimal128 cùng quy tắc làm tròn riêng; không dùng `double` bừa bãi để tính tiền.

**Invoice.java**

~~~java
package com.example.billing;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "invoices")
public record Invoice(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String status,
        int quantity,
        long unitPriceVnd,
        long shippingFeeVnd,
        long discountVnd,
        long totalVnd) {
}
~~~

`@MongoId(FieldType.STRING)` giữ `_id` là BSON String ngay cả với chuỗi có dạng 24 ký tự hex. Record là ví dụ phù hợp cho đọc và ghi trạng thái đầy đủ, nhưng **không nên thực hiện read-modify-save từ một bản sao cũ** nếu nghiệp vụ cho phép ghi đồng thời mà không có kiểm soát version.

Một document ban đầu:

~~~json
{
  "_id": "inv-101",
  "tenantId": "tenant-a",
  "status": "DRAFT",
  "quantity": 3,
  "unitPriceVnd": 100000,
  "shippingFeeVnd": 10000,
  "discountVnd": 50000,
  "totalVnd": 0
}
~~~

Theo công thức trên, tổng đúng phải là:

\[
3 \times 100000 + 10000 - 50000 = 260000\text{ VND}.
\]

Field `totalVnd` hiện đang bằng 0 và cần được cập nhật từ dữ liệu trên server. Ở môi trường thật, cần bảo đảm `quantity`, `unitPriceVnd`, `shippingFeeVnd`, `discountVnd` là các giá trị hợp lệ, không vượt giới hạn số học và tương thích schema cũ.

## 5. Ví dụ đầu tiên: tính tổng từ các field hiện có

Trong Spring Data MongoDB, `AggregationExpression` mô tả một biểu thức phía MongoDB. Có thể xây biểu thức bằng các lớp toán tử Spring Data như `ArithmeticOperators`; ở đây dùng một implementation tường minh với `Document` để dễ so sánh **BSON chính xác**.

**InvoiceRecalculationService.java**

~~~java
package com.example.billing;

import com.mongodb.client.result.UpdateResult;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationExpression;
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class InvoiceRecalculationService {
    private final MongoTemplate mongo;

    public InvoiceRecalculationService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public UpdateResult recalculate(String tenantId, String invoiceId) {
        Query query = Query.query(
                Criteria.where("id").is(invoiceId)
                        .and("tenantId").is(tenantId)
                        .and("status").is("DRAFT"));

        AggregationExpression total = context ->
                new Document("$subtract", List.of(
                        new Document("$add", List.of(
                                new Document("$multiply", List.of(
                                        "$quantity", "$unitPriceVnd")),
                                "$shippingFeeVnd")),
                        "$discountVnd"));

        AggregationUpdate update = Aggregation.newUpdate()
                .set("totalVnd").toValue(total);

        return mongo.updateFirst(query, update, Invoice.class);
    }
}
~~~

Điểm quan trọng:

1. `Query` chứa ID, tenant và trạng thái; MongoDB chỉ cập nhật document phù hợp. `id` sẽ được mapping sang `_id` nhờ `Invoice.class`.
2. `AggregationExpression` là biểu thức **được MongoDB tính**, không phải phép tính chạy trên một đối tượng Java đã tải về.
3. `Aggregation.newUpdate().set("totalVnd").toValue(total)` yêu cầu ghi kết quả biểu thức vào `totalVnd`.
4. `mongo.updateFirst(...)` thực hiện update trên document đầu tiên khớp; vì filter có `_id` duy nhất, tối đa một document được cập nhật.
5. `UpdateResult` cho phép kiểm tra có document khớp hay không, có đổi dữ liệu hay không. Không cần tải `Invoice` chỉ để tính lại tổng.

Khi gọi với `tenant-a` và `inv-101`, giá trị `totalVnd` được cập nhật thành `260000` (giả sử dữ liệu không đổi và không có lỗi). Với một document thỏa điều kiện, phép tính và ghi field được thực hiện trong một thao tác update trên server.

### 5.1. Toán tử aggregation phải dùng field reference đúng

Trong biểu thức phía trên:

~~~javascript
{ $multiply: ["$quantity", "$unitPriceVnd"] }
~~~

`"$quantity"` là **field reference**, còn `"quantity"` không có ký tự `$` là một chuỗi literal trong expression. Nếu quên `$`, MongoDB không tự hiểu đó là property Java.

Tương tự `List.of("$quantity", "$unitPriceVnd")` bên trong `Document` chỉ là **cú pháp Java tạo BSON expression**, không có phép toán nào xảy ra khi Java gọi `List.of`.

### 5.2. Kiểm tra kết quả cập nhật

~~~java
UpdateResult result =
        invoiceRecalculationService.recalculate("tenant-a", "inv-101");

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

Giả sử code này nằm trong một service/test có bean `invoiceRecalculationService`. Diễn giải:

- `matched == 1`: có document thỏa filter tại lúc update.
- `matched == 0`: có thể sai ID/tenant, document đã đổi trạng thái hoặc bị xóa; không kết luận nguyên nhân chỉ từ con số này.
- `modified == 0` với `matched == 1` có thể nghĩa kết quả phép tính bằng giá trị đang lưu; **không** đồng nghĩa lệnh update thất bại.

Nếu workflow cần phân biệt “không tìm thấy” và “đã chuyển trạng thái”, có thể đọc lại **sau** thao tác để giải thích, nhưng phép đọc đó không thay thế điều kiện bảo vệ ngay trong lệnh ghi.

## 6. So sánh trực tiếp với Update.set và Update.inc

Một thay đổi cố định:

~~~java
import org.springframework.data.mongodb.core.query.Update;

Update classic = new Update()
        .set("status", "APPROVED")
        .inc("quantity", 1);
~~~

Ở đây `"APPROVED"` là giá trị cụ thể đã được Java cung cấp; `$inc` là update operator của MongoDB.

Khi sử dụng pipeline, để tăng số lượng từ giá trị đang lưu cần **aggregation expression**:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    {
      $set: {
        quantity: { $add: ["$quantity", 1] }
      }
    }
  ]
);
~~~

`$inc` **không phải aggregation pipeline stage**. Nếu chỉ cần tăng trường số, `Update.inc(...)` thường ngắn gọn hơn và diễn đạt mục đích rõ ràng. `AggregationUpdate` trở nên hữu ích khi cần công thức, xử lý missing/null, nhiều bước biến đổi hoặc sử dụng các biểu thức như `$cond` và `$map`.

| Yêu cầu | Update thường | AggregationUpdate |
|---|---|---|
`status = "APPROVED"` | `Update.set(...)` | `$set` stage với literal |
`quantity = quantity + 1` | `Update.inc(...)` | `$set` + `$add` expression |
`total = quantity * price + fee - discount` | Không có một toán tử Update trực tiếp ngắn gọn | Dùng `$multiply`/`$add`/`$subtract` |
Nếu field thiếu, dùng 0 rồi cộng | `inc` xử lý một số tình huống nhưng không đồng nghĩa null handling tùy ý | `$ifNull` + `$add` theo policy |
Phân loại trạng thái dựa trên nhiều field | Cần code/phương thức thích hợp khác | `$cond` hoặc `$switch` |
Biến đổi từng phần tử array | Có array operators, array filters | `$map`/`$filter`, kết hợp expression |

Đừng chuyển mọi cập nhật nhỏ sang pipeline “vì mạnh hơn”. Tính đơn giản của lệnh, tính rõ ràng của business invariant và hiệu năng thực tế là tiêu chí lựa chọn.

## 7. Xử lý missing/null và giá trị mặc định trong biểu thức

Khi document cũ thiếu `discountVnd` hoặc lưu `discountVnd: null`, phép `$subtract` trên giá trị null có thể cho kết quả null thay vì số tiền đúng. Có thể biểu diễn chính sách “discount không có nghĩa là 0” bằng `$ifNull`:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101", status: "DRAFT" },
  [
    {
      $set: {
        totalVnd: {
          $subtract: [
            {
              $add: [
                { $multiply: ["$quantity", "$unitPriceVnd"] },
                { $ifNull: ["$shippingFeeVnd", 0] }
              ]
            },
            { $ifNull: ["$discountVnd", 0] }
          ]
        }
      }
    }
  ]
);
~~~

Trong Spring Data, phần Java có thể dùng expression tường minh:

~~~java
AggregationExpression safeTotal = context ->
        new Document("$subtract", List.of(
                new Document("$add", List.of(
                        new Document("$multiply", List.of(
                                "$quantity", "$unitPriceVnd")),
                        new Document("$ifNull", List.of(
                                "$shippingFeeVnd", 0)))),
                new Document("$ifNull", List.of(
                        "$discountVnd", 0))));

AggregationUpdate recalculateSafely = Aggregation.newUpdate()
        .set("totalVnd").toValue(safeTotal);
~~~

Đoạn trên chỉ áp dụng default cho **phí vận chuyển và giảm giá**; nó vẫn yêu cầu `quantity` và `unitPriceVnd` có kiểu số hợp lệ. Nếu dữ liệu cũ có chuỗi thay vì số, cần migration hoặc toán tử chuyển kiểu với xử lý lỗi được thiết kế. Không mặc định “null ở mọi field đều bằng 0” vì có thể làm che giấu dữ liệu lỗi.

### Giới hạn số học

Ví dụ dùng `long`, nhưng giá trị đầu vào lớn có thể vượt miền số nguyên 64 bit hoặc làm các toán tử MongoDB tăng kiểu dữ liệu theo quy tắc số học riêng. Với nghiệp vụ tiền tệ thực, cần kiểm soát precision, miền giá trị, Decimal128 và nguyên tắc làm tròn; không chỉ thay kiểu Java rồi cho rằng expression trên server luôn giữ nguyên semantics.

### Chuỗi bắt đầu bằng dấu $

Trong aggregation expression, chuỗi `"$status"` được hiểu là **tham chiếu field**. Muốn gán literal mang nội dung `"$VIP"`, phải biểu diễn rõ literal:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [ { $set: { displayTag: { $literal: "$VIP" } } } ]
);
~~~

Tương tự khi tạo biểu thức raw trong Java:

~~~java
AggregationExpression dollarText =
        context -> new Document("$literal", "$VIP");

AggregationUpdate update = Aggregation.newUpdate()
        .set("displayTag").toValue(dollarText);
~~~

Không nối raw expression từ dữ liệu người dùng và mặc nhiên coi đó là literal. Hãy phân biệt input text, field path và toán tử BSON để tránh lỗi logic và truy vấn không mong đợi.

## 8. Cập nhật theo điều kiện với $cond

Giả sử nghiệp vụ cần gán một nhãn phân loại từ **số lượng hiện tại**:

- Nếu `quantity >= 10`, nhãn là `BULK`.
- Nếu không, nhãn là `RETAIL`.

MongoDB hỗ trợ `$cond`:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    {
      $set: {
        orderClass: {
          $cond: {
            if: { $gte: ["$quantity", 10] },
            then: "BULK",
            else: "RETAIL"
          }
        }
      }
    }
  ]
);
~~~

Một expression Java tương đương:

~~~java
AggregationExpression orderClass = context ->
        new Document("$cond", new Document(
                "if", new Document("$gte", List.of("$quantity", 10)))
                .append("then", "BULK")
                .append("else", "RETAIL"));

AggregationUpdate update = Aggregation.newUpdate()
        .set("orderClass").toValue(orderClass);
~~~

Với nhiều nhánh, MongoDB có `$switch`; Spring Data cũng có builder biểu thức điều kiện. Đối với logic quá phức tạp, cần xem xét đặt quy tắc nghiệp vụ ở lớp domain hoặc một write model có kiểm soát: sức mạnh expression không có nghĩa mọi chính sách kinh doanh đều nên bị nhúng vào một pipeline khó kiểm thử.

### Điều kiện cập nhật khác điều kiện tính toán

Ví dụ `$cond` **không ngăn việc cập nhật** một hóa đơn đã `PAID`; nó chỉ chọn giá trị của `orderClass`. Muốn **chỉ cập nhật DRAFT**, thêm `Criteria.where("status").is("DRAFT")` vào **filter**:

~~~java
Query draftOnly = Query.query(
        Criteria.where("id").is("inv-101")
                .and("tenantId").is("tenant-a")
                .and("status").is("DRAFT"));

mongo.updateFirst(draftOnly, update, Invoice.class);
~~~

Đây là điểm quan trọng trong xử lý trạng thái: **filter bảo vệ document được phép sửa**, expression quyết định **giá trị sửa**.

## 9. Biến đổi array bằng $map trong update pipeline

Một trường hợp nổi bật của aggregation update là biến đổi **mọi phần tử** của một array nhúng mà không kéo toàn bộ array về Java.

Giả sử document `purchase_orders` chứa:

~~~json
{
  "_id": "ord-7",
  "status": "DRAFT",
  "lines": [
    { "sku": "A", "quantity": 2, "unitPriceVnd": 50000 },
    { "sku": "B", "quantity": 3, "unitPriceVnd": 20000 }
  ]
}
~~~

Ta muốn thêm `lineTotalVnd` cho từng dòng hàng bằng công thức `quantity * unitPriceVnd`. Pipeline:

~~~javascript
db.purchase_orders.updateOne(
  { _id: "ord-7", status: "DRAFT" },
  [
    {
      $set: {
        lines: {
          $map: {
            input: { $ifNull: ["$lines", []] },
            as: "line",
            in: {
              $mergeObjects: [
                "$$line",
                {
                  lineTotalVnd: {
                    $multiply: ["$$line.quantity", "$$line.unitPriceVnd"]
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
);
~~~

Trong `$map`:

- `input` xác định mảng nguồn.
- `as: "line"` đặt tên biến cục bộ cho mỗi phần tử.
- `"$$line"` là **biến phần tử**, khác với `"$lines"` là tham chiếu field document gốc.
- `$mergeObjects` giữ các field khác của mỗi dòng và ghi thêm `lineTotalVnd`.
- `$multiply` tính toán trên giá trị của chính dòng đang xét.

Spring Data có thể nhận expression để cập nhật array bằng `AggregationUpdate`:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationExpression;
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;

AggregationExpression recalculateLines = context ->
        new Document("$map", new Document(
                "input", new Document("$ifNull", List.of("$lines", List.of())))
                .append("as", "line")
                .append("in", new Document("$mergeObjects", List.of(
                        "$$line",
                        new Document("lineTotalVnd",
                                new Document("$multiply", List.of(
                                        "$$line.quantity",
                                        "$$line.unitPriceVnd")))))));

AggregationUpdate update = Aggregation.newUpdate()
        .set("lines").toValue(recalculateLines);
~~~

Đây là **expression dạng raw BSON**; nếu model Java dùng `@Field("unit_price_vnd")` cho property `unitPriceVnd` bên trong dòng, hãy dùng **field name thực tế** ở biểu thức raw, ví dụ `"$$line.unit_price_vnd"`. Không giả định mọi đường expression tự mapping tên property như `Criteria.where(...)`.

### Cẩn trọng khi thay cả array

`$map` tạo một array mới cho field `lines`. Tất cả các phần tử được tính toán theo biểu thức và field `lines` được ghi lại. Nếu chỉ muốn sửa **một dòng có SKU cụ thể**, một lệnh update với positional operator hoặc `arrayFilters` có thể đơn giản, ít công việc và phù hợp hơn.

Không dùng `$map` để xử lý một array tăng vô hạn: MongoDB giới hạn kích thước BSON document ở **16 MiB**, và biểu thức trên array lớn có thể tốn nhiều CPU/bộ nhớ. Cần đo workload và xem xét tách dòng hàng thành collection riêng nếu vòng đời/khối lượng dữ liệu đòi hỏi.

## 10. Thứ tự stage, $unset và chuyển đổi schema

Pipeline update hữu ích trong **migration schema tại chỗ**. Ví dụ các document cũ có `legacyAmount` và cần lưu `amountVnd` theo chuẩn mới, sau đó bỏ field cũ:

~~~javascript
db.invoices.updateMany(
  {
    status: "DRAFT",
    legacyAmount: { $type: "number" }
  },
  [
    { $set: { amountVnd: "$legacyAmount" } },
    { $unset: "legacyAmount" }
  ]
);
~~~

Stage `$set` copy giá trị từ field cũ, stage `$unset` xóa field cũ. Thứ tự này quan trọng: nếu xóa `legacyAmount` trước, stage sau không còn dữ liệu để copy. Filter giới hạn phạm vi migration đến những document phù hợp.

**Những điểm cần chuẩn bị trước khi migrate thật:**

1. Kiểm kê schema hiện tại, bao gồm field thiếu/null, kiểu BSON số và dữ liệu lỗi.
2. Thiết kế rollback hoặc khả năng đọc tương thích trong giai đoạn triển khai nhiều phiên bản ứng dụng.
3. Chạy theo lô có checkpoint và đo tốc độ ghi/chi phí cập nhật index.
4. Dùng truy vấn chọn phạm vi rõ ràng; tránh cập nhật toàn collection ngoài ý muốn.
5. Nếu migration liên quan field định danh, phải lưu ý `_id` là bất biến; không xem thay `_id` như sửa một field bình thường.
6. Kiểm tra kết quả thực tế bằng raw BSON và thống kê số document đã chuyển.

Không phải migration nào cũng an toàn nếu chỉ gói trong một lệnh `updateMany`; khi chuyển đổi hàng triệu document, một lỗi giữa quá trình có thể để lại tập dữ liệu **một phần đã đổi**. Cần idempotency và khả năng chạy lại.

## 11. Ghi đồng thời, tính nguyên tử và optimistic locking

### 11.1. Vì sao pipeline giúp giảm read-modify-write race?

Giả sử hai request đồng thời muốn **tăng một counter** dựa trên giá trị đang lưu.

~~~text
Lỗi dễ gặp:
  A đọc counter = 5
  B đọc counter = 5
  A lưu counter = 6
  B lưu counter = 6
Kết quả: mất một lần tăng.
~~~

Thay vì đọc rồi lưu bản sao cũ, dùng một update operator:

~~~javascript
db.counters.updateOne(
  { _id: "monthly-billing" },
  { $inc: { processed: 1 } }
);
~~~

Hoặc aggregation pipeline expression tương đương về ý tưởng:

~~~javascript
db.counters.updateOne(
  { _id: "monthly-billing" },
  [
    {
      $set: {
        processed: {
          $add: [
            { $ifNull: ["$processed", 0] },
            1
          ]
        }
      }
    }
  ]
);
~~~

Hai update trên **cùng một document** được MongoDB thực thi nguyên tử ở cấp document, thay vì ứng dụng tự ghi số 6 sau một lần đọc cũ. Với phép tăng đơn giản, `$inc` thường là lựa chọn trực tiếp hơn; với công thức phức tạp phụ thuộc nhiều field, pipeline có ý nghĩa.

### 11.2. Atomic trên một document không đồng nghĩa transaction toàn collection

`mongo.updateMulti(query, aggregationUpdate, Invoice.class)` có thể yêu cầu MongoDB cập nhật **nhiều document**, và biểu thức được đánh giá cho từng document. Nhưng **cả tập document không được bảo đảm nguyên tử như một transaction duy nhất** chỉ vì dùng pipeline.

Nếu một thao tác nghiệp vụ cần sửa hóa đơn, trừ tồn kho và ghi ledger **đồng thời** ở nhiều collection, cần xem xét MongoDB transaction với session/topology được hỗ trợ, hoặc một quy trình reservation/outbox/idempotency phù hợp. Pipeline update không tự thay thế transaction.

### 11.3. Khi dùng @Version, filter vẫn cần kiểm tra kỳ vọng

`@Version` của Spring Data MongoDB hỗ trợ optimistic locking trên các đường ghi phù hợp, đặc biệt khi save entity đã đọc. Với thao tác `MongoTemplate.updateFirst(...)` được xây dựng thủ công, **không mặc định cho rằng query đã kiểm tra version kỳ vọng**.

Ví dụ một nghiệp vụ chỉ cho phép xác nhận hóa đơn khi đang `DRAFT` và `version` vẫn bằng giá trị client đã đọc. Filter phải chỉ rõ điều kiện đó; nếu pipeline tự cập nhật version, cả hai đường ghi phải thống nhất chính sách.

~~~java
Query expected = Query.query(
        Criteria.where("id").is(invoiceId)
                .and("tenantId").is(tenantId)
                .and("status").is("DRAFT")
                .and("version").is(expectedVersion));

AggregationExpression nextVersion = context ->
        new Document("$add", List.of("$version", 1));

AggregationUpdate update = Aggregation.newUpdate()
        .set("version").toValue(nextVersion);

UpdateResult result = mongo.updateFirst(
        expected, update, VersionedInvoice.class);
~~~

Đoạn trên là **mẫu thao tác có điều kiện**, giả sử dự án đã định nghĩa `VersionedInvoice` (entity khác `Invoice` ở mục 4) với `id`, `tenantId`, `status`, `version` được ánh xạ đúng và lựa chọn cơ chế tăng version tường minh. Đây không phải class đã đầy đủ để copy chạy độc lập. Khi dùng `@Version` trong một entity thật, phải kiểm tra cách Spring Data xử lý tự tăng version cùng các thao tác update để **không vô tình tăng hai lần** hoặc bỏ qua đường ghi không tuân thủ contract.

Nếu `getMatchedCount() == 0`, lệnh không cập nhật document do thiếu ID, sai tenant, trạng thái đã đổi hoặc version cũ. Tầng nghiệp vụ có thể trả lỗi xung đột hoặc đọc lại, rồi **đánh giá lại quyết định trước khi retry**. Không retry mù mọi cập nhật có side effect như cộng điểm, chuyển tiền hoặc xác nhận giao dịch.

### 11.4. Write concern và lỗi không xác định

Một lần timeout sau khi gửi lệnh không chứng minh MongoDB chưa ghi. Với cập nhật **không idempotent** như tăng counter hoặc thêm một entry, retry không có khóa sự kiện/idempotency token có thể làm áp dụng hai lần. Cần phân biệt retryable write của driver với **idempotency nghiệp vụ**, và chọn write concern, error handling, event ID/checkpoint phù hợp.

## 12. Mapping field, BSON type và vấn đề expression raw

Spring Data MongoDB cho phép dùng property Java trong `Criteria` và `Update` khi có entity type, ví dụ:

~~~java
@Field("unit_price_vnd")
private long unitPriceVnd;
~~~

Khi đó, `Criteria.where("unitPriceVnd").gte(10000)` có thể được mapping sang `unit_price_vnd`. Nhưng biểu thức `AggregationExpression` được tạo bằng `new Document("$multiply", List.of("$quantity", "$unitPriceVnd"))` là một cấu trúc BSON tường minh: **không dựa vào việc framework sẽ duyệt và đổi mọi chuỗi bắt đầu bằng `$` trong raw Document**.

Hai hướng an toàn:

1. Với biểu thức raw, dùng **đúng tên field BSON lưu trữ**, ví dụ `"$unit_price_vnd"`, và kiểm tra command thật.
2. Dùng các lớp builder biểu thức của Spring Data để khai thác cơ chế mapping context khi được hỗ trợ, rồi vẫn test representation trong phiên bản sử dụng.

Đối với expression trên document lồng nhau hoặc mảng, càng cần cẩn thận với tên property được đổi bằng `@Field` và với biến `$$line`. Raw expression không phải là nơi nên ghép tùy ý string field path từ input của client.

### Kiểu BSON và giá trị null

| Dữ liệu thực tế | Nguy cơ khi tính toán | Chính sách thường cần |
|---|---|---|
`quantity` là BSON int/long hợp lệ | Có thể nhân quá miền số cho phép | Giới hạn số lượng, kiểm tra overflow hoặc dùng kiểu phù hợp |
`discountVnd` missing/null | `$subtract` có thể ra null | `$ifNull` nếu nghiệp vụ cho phép mặc định 0 |
`unitPriceVnd` là String trong dữ liệu cũ | Toán tử số học không có kiểu mong đợi | Migration hoặc conversion có kiểm soát |
`amount` là Double | Sai số nhị phân khi tính tiền | Thiết kế Decimal128/BigDecimal và round policy |
`lines` không phải array | `$map` có thể gây lỗi | Schema validation, `$isArray` hoặc xử lý dữ liệu sai trước |
`currency` khác nhau giữa các dòng | Phép cộng tiền không còn đúng nghiệp vụ | Chỉ cộng cùng đơn vị hoặc dùng quy đổi có chính sách rõ ràng |

MongoDB Schema Validation có thể giúp hạn chế một số sai lệch dữ liệu được ghi, nhưng không thay thế validation ở tầng ứng dụng và migration cho dữ liệu đã tồn tại.

## 13. Hiệu năng: có ít round trip hơn nhưng không mặc định rẻ hơn

Aggregation pipeline update có thể loại bỏ bước **đọc document về Java để tính rồi ghi lại**, nhờ đó giảm round trip và nguy cơ ghi từ snapshot cũ. Tuy nhiên nó vẫn phải đọc các giá trị cần thiết trên server, tính expression và ghi lại kết quả.

Những yếu tố ảnh hưởng:

- **Filter và index:** `{ _id: ... }` có unique index mặc định; `{ tenantId, status }` cần index dựa trên workload, nhất là khi update nhiều document.
- **Độ phức tạp expression:** `$add` đơn giản khác với `$map` qua hàng nghìn phần tử hoặc xử lý chuỗi phức tạp.
- **Kích thước document:** ghi lại array lớn hoặc nhiều field có thể tăng CPU, memory, I/O và oplog.
- **Index trên field được đổi:** cập nhật các field có index có thể phát sinh thêm công việc duy trì index.
- **Tần suất tranh chấp:** nhiều worker cùng cập nhật một document nóng có thể tạo bottleneck dù từng lệnh nguyên tử.
- **Chính sách nhất quán:** transaction, write concern, retry và replication lag có thể ảnh hưởng thời gian phản hồi.

### Query và index

Với trường hợp tính lại hóa đơn theo ID và tenant:

~~~javascript
db.invoices.find({
  _id: "inv-101",
  tenantId: "tenant-a",
  status: "DRAFT"
}).explain("executionStats");
~~~

`explain` trên lệnh tìm tương đương giúp quan sát **đường chọn document**. Nó không tự đo toàn bộ chi phí tính toán và ghi của update pipeline; hãy bổ sung command monitoring, profiler và metrics dưới tải thích hợp. Đặc biệt, không đánh giá hiệu năng production chỉ dựa trên một document test nhỏ.

### Chọn chiến lược cập nhật

| Tình huống | Hướng ưu tiên |
|---|---|
Tăng counter một đơn vị | `Update.inc` |
Gán một giá trị cố định | `Update.set` |
Đọc toàn bộ aggregate, áp dụng nghiệp vụ và kiểm soát version | `save` với optimistic locking phù hợp |
Tính field từ nhiều field đang lưu | `AggregationUpdate` |
Biến đổi tất cả phần tử array theo expression | `AggregationUpdate` + `$map`, nếu khối lượng chấp nhận được |
Sửa đúng một phần tử array theo ID/điều kiện | Update positional/arrayFilters nếu phù hợp |
Cập nhật nhiều collection có bất biến liên quan | Transaction hoặc quy trình nhất quán được thiết kế |

## 14. Kiểm thử AggregationUpdate với MongoDB thật

Unit test chỉ tạo `AggregationUpdate` và mock `MongoTemplate` chưa chứng minh MongoDB thực thi expression đúng, nhất là khi có BSON type và field path. Nên có integration test trên một MongoDB thật (ví dụ Testcontainers) với schema cô lập. Trong Spring Boot 3.x, `@DataMongoTest` nạp hạ tầng MongoDB cho test nhưng **không tự khởi động server**.

### 14.1. Kiểm thử công thức tổng tiền

~~~java
package com.example.billing;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationExpression;
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class InvoiceAggregationUpdateTest {
    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void setUp() {
        // Chỉ xóa trên database test riêng.
        mongo.remove(new Query(), Invoice.class);
        mongo.insert(new Invoice(
                "inv-101", "tenant-a", "DRAFT",
                3, 100000L, 10000L, 50000L, 0L));
    }

    @Test
    void calculatesTotalFromCurrentServerFields() {
        AggregationExpression total = context ->
                new Document("$subtract", List.of(
                        new Document("$add", List.of(
                                new Document("$multiply", List.of(
                                        "$quantity", "$unitPriceVnd")),
                                "$shippingFeeVnd")),
                        "$discountVnd"));
        AggregationUpdate update = Aggregation.newUpdate()
                .set("totalVnd").toValue(total);

        Query draftInvoice = Query.query(
                Criteria.where("id").is("inv-101")
                        .and("tenantId").is("tenant-a")
                        .and("status").is("DRAFT"));

        var result = mongo.updateFirst(
                draftInvoice, update, Invoice.class);

        assertThat(result.getMatchedCount()).isEqualTo(1);
        Invoice after = mongo.findById("inv-101", Invoice.class);
        assertThat(after).isNotNull();
        assertThat(after.totalVnd()).isEqualTo(260000L);

        Document bson = mongo.getCollection("invoices")
                .find(new Document("_id", "inv-101"))
                .first();
        assertThat(bson).isNotNull();
        assertThat(bson.get("totalVnd")).isInstanceOf(Number.class);
        assertThat(((Number) bson.get("totalVnd")).longValue())
                .isEqualTo(260000L);
    }

    @Test
    void doesNotTouchOtherTenantOrWrongStatus() {
        AggregationExpression constant = context ->
                new Document("$literal", 999L);
        AggregationUpdate update = Aggregation.newUpdate()
                .set("totalVnd").toValue(constant);

        Query wrongTenant = Query.query(
                Criteria.where("id").is("inv-101")
                        .and("tenantId").is("tenant-b"));

        assertThat(mongo.updateFirst(
                wrongTenant, update, Invoice.class).getMatchedCount())
                .isZero();
        assertThat(mongo.findById(
                "inv-101", Invoice.class).totalVnd())
                .isZero();
    }
}
~~~

Test chứng minh công thức tính đúng từ field hiện có và điều kiện tenant được áp dụng. Test **không** tự chứng minh hiệu năng hoặc mọi tình huống concurrent update; cần thêm kiểm thử song song, field null/missing và các giới hạn input.

### 14.2. Các ca biên nên thử

| Kịch bản | Kết quả mong đợi |
|---|---|
`discountVnd = 0` | Tổng = tiền hàng + phí |
`discountVnd` null/missing | Pipeline có `$ifNull` áp dụng đúng chính sách 0, hoặc lỗi được phân loại rõ |
`quantity = 0` | Kết quả theo quy tắc phí/discount; không âm nếu nghiệp vụ cấm |
`status = PAID` | Filter DRAFT không cập nhật |
`tenantId` không khớp | `matchedCount = 0` |
Hai luồng đồng thời áp dụng phép tăng counter | Không mất lần tăng nếu dùng atomic server-side expression phù hợp |
Lặp lại phép tính tổng với đầu vào không đổi | Kết quả ổn định, không cộng thêm ngoài ý muốn |
Retry pipeline tăng counter sau timeout | Có cơ chế idempotency hoặc phân loại kết quả trước đó |
`unitPriceVnd` là String hoặc null | Kiểm thử validation/migration hoặc lỗi được xử lý |
Mảng `lines` rỗng/null | `$map` có chính sách fallback đúng |
Field dùng `@Field` khác tên property Java | Expression raw tham chiếu BSON field đúng |

### 14.3. Quan sát command và BSON stage

MongoDB Java Driver hỗ trợ `CommandListener` nhận `CommandStartedEvent`. Trong môi trường test, có thể đăng ký listener khi tạo `MongoClient` để thấy lệnh `update` cùng trường `updates`; mỗi phần tử có filter `q` và update `u`. Đối với aggregation pipeline update, `u` là **mảng pipeline**, không phải update document `{ "$set": ... }` thông thường.

Ví dụ cấu trúc dự kiến:

~~~json
{
  "update": "invoices",
  "updates": [
    {
      "q": {
        "_id": "inv-101",
        "tenantId": "tenant-a",
        "status": "DRAFT"
      },
      "u": [
        {
          "$set": {
            "totalVnd": {
              "$subtract": [
                {
                  "$add": [
                    { "$multiply": ["$quantity", "$unitPriceVnd"] },
                    "$shippingFeeVnd"
                  ]
                },
                "$discountVnd"
              ]
            }
          }
        }
      ],
      "multi": false
    }
  ]
}
~~~

Đây là bản minh họa lược bớt một số field của command; không phải cam kết byte-for-byte. Khi kiểm tra raw BSON, chú ý sự khác nhau giữa String/Int32/Int64/Decimal128 và tên field được mapping. Chỉ capture command trong môi trường được phép, tránh lộ thông tin hóa đơn, địa chỉ hoặc dữ liệu khách hàng vào log production.

## 15. Những lỗi thường gặp khi dùng AggregationUpdate

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
Nhầm `AggregationUpdate` với `aggregate()` để truy vấn | Kỳ vọng trả báo cáo thay vì ghi dữ liệu | Phân biệt update pipeline và aggregation truy vấn |
Đưa `$match` vào danh sách update stages | Server từ chối stage không được phép | Đặt điều kiện trong `Query` |
Viết `$inc` như một pipeline stage | Sai ngữ nghĩa update pipeline | Dùng `$add` trong expression hoặc Update.inc |
Quên `$` trước tên field trong raw expression | Tính trên chuỗi literal, không phải giá trị field | Dùng `"$quantity"`, kiểm tra BSON thực |
Không dùng `$literal` với chuỗi bắt đầu bằng `$` | Chuỗi bị hiểu thành tham chiếu field | Dùng `$literal` đúng vị trí |
Giả định các gán trong một stage có thứ tự tuần tự | Expression đọc giá trị không như dự kiến | Tách stage có phụ thuộc hoặc viết expression đầy đủ |
Raw expression dùng tên Java khi BSON có `@Field` | Tính trên field không tồn tại, kết quả null/lỗi | Dùng tên BSON vật lý hoặc builder mapping-aware |
Không xử lý null/missing trong phép tính | Kết quả null hoặc sai nghiệp vụ | `$ifNull`/validation/migration |
Gọi `updateMulti` rồi nghĩ cả collection được commit nguyên tử | Trạng thái nhiều document có thể chỉ cập nhật một phần khi lỗi | Transaction hoặc quy trình có thể chạy lại |
Tin một lệnh pipeline tự kiểm tra `@Version` | Ghi đè khi query thiếu version kỳ vọng | Điều kiện compare-and-set và chính sách version rõ ràng |
Trả entity partial rồi `save` thay cho pipeline | Mất các field chưa đọc | Cập nhật đúng field trên server |
Dùng `$map` để sửa một phần tử array đơn giản | Xử lý thừa cả array | Cân nhắc positional operator/arrayFilters |
Retry mọi update không idempotent sau timeout | Có thể cộng/trừ hai lần | Event ID, idempotency key hoặc logic điều kiện phù hợp |
Không kiểm tra `matchedCount` | Bỏ qua lỗi sai trạng thái hoặc sai tenant | Phân loại no-match và xử lý theo API contract |
Không test trên MongoDB thật | Không phát hiện lỗi stage/BSON/mapping | Integration test với collection cô lập |

## 16. Bài tập thực hành

**Bài 1 — Viết lại phép tính.** Tạo collection `invoices` theo mục 4. So sánh cách đọc entity rồi tính Java với `AggregationUpdate` tính `totalVnd` trực tiếp. Kiểm tra giá trị 260000 và số round trip, nêu rủi ro khi có request khác cập nhật số lượng giữa hai thao tác.

**Bài 2 — Phân biệt $set và $inc.** Viết `Update.inc("quantity", 1)` và pipeline `$set: { quantity: { $add: ["$quantity", 1] } }`. Giải thích vì sao `$inc` không dùng như stage pipeline và khi nào cách thứ nhất đơn giản hơn.

**Bài 3 — Xử lý missing/null.** Tạo ba hóa đơn có `discountVnd` là 0, null và không có field. So sánh biểu thức dùng `$subtract` trực tiếp với biểu thức có `$ifNull`. Giải thích chính sách nghiệp vụ khi dữ liệu giảm giá không hợp lệ.

**Bài 4 — Stage ordering.** Viết pipeline tính `subtotalVnd` ở stage thứ nhất rồi tính `totalVnd` ở stage thứ hai. Thử đảo thứ tự để quan sát kết quả trên document chưa có `subtotalVnd`. Giải thích vì sao thứ tự stage khác thứ tự property trong một stage.

**Bài 5 — Cập nhật nhãn bằng $cond.** Ghi `orderClass = BULK` khi `quantity >= 10`, ngược lại `RETAIL`. Chỉ cho phép cập nhật hóa đơn DRAFT thuộc tenant hiện tại; kiểm thử trạng thái PAID không bị sửa.

**Bài 6 — Biến đổi mảng.** Tạo đơn hàng với hai dòng hàng. Dùng `$map`/`$mergeObjects` thêm `lineTotalVnd` cho từng dòng. Sau đó thay tên field Java bằng `@Field("unit_price_vnd")` và xác minh expression raw cần tham chiếu đúng BSON field.

**Bài 7 — Đồng thời và idempotency.** Cho hai worker cập nhật cùng một counter. So sánh read-modify-save không version với phép tăng trên server. Mô phỏng retry sau timeout và thiết kế cách ngăn một event bị áp dụng hai lần.

**Bài 8 — Migration.** Tạo dữ liệu cũ có `legacyAmount`; dùng update pipeline tạo `amountVnd` rồi bỏ `legacyAmount`. Thiết kế filter theo type, chạy lại an toàn, báo cáo số bản ghi đã chuyển và phương án triển khai rolling upgrade.

**Bài 9 — Hiệu năng.** Với nhiều hóa đơn, so sánh update từng ID với `updateMulti` trên một tập có filter/index. Đo `matchedCount`, `modifiedCount`, p95 latency, tải server và tình trạng dữ liệu khi một phần xử lý lỗi. Không coi nhiều document được ghi nguyên tử chỉ vì pipeline chạy trên server.

## 17. Ghi nhớ

**`AggregationUpdate`** là cách Spring Data MongoDB xây dựng **aggregation pipeline update** để tính hoặc biến đổi giá trị dựa trên **trạng thái document ở MongoDB**, thay vì bắt buộc đọc toàn bộ document về Java rồi lưu lại. Phối hợp `Aggregation.newUpdate()`, `set(...).toValue(...)` và `MongoTemplate.updateFirst/updateMulti` giúp thực hiện các phép tính, điều kiện và biến đổi mảng bằng aggregation expressions.

Cần phân biệt **update operators** (`$inc`, `$set` kiểu update thường) với **aggregation pipeline stages/expressions** (`$set` stage, `$add`, `$multiply`, `$ifNull`, `$cond`, `$map`). Filter chọn document nằm trong `Query`; biểu thức bên trong pipeline tạo giá trị; thứ tự stage có thể ảnh hưởng kết quả. Raw BSON expression phải dùng đúng tên field lưu trữ và xử lý rõ field reference/literal.

Một update trên **một document** có tính nguyên tử ở cấp document, nhưng không tự tạo transaction cho **nhiều document**, không tự giải quyết optimistic locking nếu thiếu điều kiện version kỳ vọng, và không bảo đảm an toàn khi retry các phép ghi không idempotent. Luôn kiểm tra `matchedCount`, kiểu BSON, schema cũ, index và command thực tế; viết integration test cho dữ liệu biên và tình huống đồng thời trước khi đưa pipeline update vào production.
