# $replaceRoot, $unionWith và thay đổi hình dạng kết quả

## 1. Bài toán: thống nhất dữ liệu có nhiều hình dạng

Trong chương **Aggregation nâng cao** của **Spring Data MongoDB**, một pipeline không chỉ lọc hoặc cộng tổng: nó còn có thể **thay đổi toàn bộ hình dạng document** và **ghép các luồng kết quả đến từ nhiều collection**.

Giả sử nền tảng thương mại lưu hai loại sự kiện:

- Collection `order_events` ghi đơn hàng vừa được thanh toán. Chi tiết đơn nằm trong object `payload`.
- Collection `refund_events` ghi tiền hoàn cho đơn. Chi tiết hoàn tiền nằm trong object `details` và có tên field khác.

Màn hình lịch sử tài chính muốn hiển thị **một dòng sự kiện thống nhất** dù nguồn là đơn hàng hay hoàn tiền:

~~~json
{
  "eventId": "r-101",
  "source": "REFUND",
  "tenantId": "tenant-a",
  "orderId": "ord-101",
  "netAmountVnd": -40000,
  "occurredAt": { "$date": "2026-11-20T09:10:00Z" }
}
~~~

Sự kiện đơn hàng có `netAmountVnd` dương; sự kiện hoàn tiền có giá trị âm. Để tạo ra cùng output schema, MongoDB cần **chuẩn hóa từng nguồn**, rồi mới kết hợp và sắp xếp.

Hai stage trọng tâm:

1. **`$replaceRoot`**: thay toàn bộ document hiện tại bằng một document mới — có thể lấy từ một object lồng hoặc tạo bằng expression.
2. **`$unionWith`**: bổ sung kết quả từ một collection/pipeline khác vào luồng hiện tại. Nó hoạt động theo tinh thần *UNION ALL*, **không tự loại bản ghi trùng**.

Chúng thường đi cùng `$match`, `$set`, `$project`, `$sort`, `$group` và `$limit`. Spring Data MongoDB cho phép xây pipeline bằng `Aggregation`, `MongoTemplate.aggregate`, các builder theo phiên bản và `AggregationOperation` khi cần stage BSON tùy chỉnh.

### Mục tiêu học tập

1. Giải thích được vì sao `$replaceRoot` khác `$project` và khi nào document nguồn mất trường.
2. Viết `$replaceRoot` trên object nhúng, dùng `$mergeObjects` để bảo vệ metadata và xử lý document không hợp lệ.
3. Kết hợp hai collection bằng `$unionWith` mà không nhầm với `$lookup` hoặc phép nối khử trùng.
4. Chuẩn hóa tên, kiểu và ngữ nghĩa của các field đầu ra trước khi ánh xạ vào DTO.
5. Tạo pipeline từ Spring Data MongoDB bằng `AggregationOperation` và đọc `AggregationResults<DTO>`/`Document`.
6. Nhận biết giới hạn phiên bản, tenant security, collation, chi phí đọc, quy tắc sort/pagination và khả năng chạy trong transaction.
7. Viết integration test kiểm tra BSON thực tế, dữ liệu trùng, nhánh lọc và tổng hợp sau union.

> Ví dụ sử dụng Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x trên MongoDB có hỗ trợ `$unionWith` (được giới thiệu từ MongoDB 4.4). Cần xác minh phiên bản server, Spring Data, driver và các hạn chế topology trước khi áp dụng. Bài dùng **raw BSON stage** trong `AggregationOperation` ở những chỗ builder có thể khác giữa các phiên bản.

## 2. So sánh nhanh: replaceRoot, project, unwind, unionWith, lookup

| Stage | Thay đổi gì? | Có đổi số dòng không? | Khi nào dùng? |
|---|---|---|---|
| `$project` | Chọn/tính/đổi tên các field của document | Thông thường không | Định nghĩa output schema |
| `$set` / `$addFields` | Thêm hoặc ghi đè một số field | Không | Tính `netAmountVnd` hay tạo metadata |
| `$replaceRoot` | **Thay toàn bộ document root** | Một input hợp lệ thành một output | Đưa document con lên root hoặc dựng root mới |
| `$replaceWith` | Cách diễn đạt tương đương `$replaceRoot` cho một expression | Một input hợp lệ thành một output | Thay root bằng expression theo cú pháp ngắn |
| `$unwind` | Tách mỗi phần tử array thành dòng riêng | Có thể tăng/giảm | Xử lý từng item trong mảng |
| `$lookup` | Ghép thông tin liên quan từ collection khác vào document hiện tại | Thường thêm array; tùy pipeline sau | Join theo khóa/quan hệ |
| `$unionWith` | **Nối thêm các document kết quả** từ nguồn khác | Thường tăng số dòng | Kết hợp các tập dữ liệu có schema đã chuẩn hóa |
| `$group` | Tạo document theo nhóm | Thường giảm số dòng | Tổng hợp, đối soát, khử trùng có chủ đích |

Hãy xác định trước yêu cầu:

- Muốn “mỗi đơn hàng đi kèm các khoản hoàn tiền” → thường cân nhắc `$lookup`.
- Muốn “sự kiện đơn hàng **và** sự kiện hoàn tiền cùng xuất hiện trong một timeline” → `$unionWith`.
- Muốn “nâng `payload` lên thành document kết quả” → `$replaceRoot`.
- Chỉ muốn đổi tên một vài field mà vẫn giữ metadata gốc → `$project` hoặc `$set` có thể đơn giản hơn.

Không dùng `$unionWith` như một cách cập nhật hai collection; đây là **aggregation đọc và biến đổi kết quả**, không ghi dữ liệu nguồn nếu không có cơ chế ghi được thiết kế riêng.

## 3. Hai collection có schema khác nhau

### 3.1. Đơn hàng

Document gốc trong `order_events`:

~~~json
{
  "_id": "o-101",
  "tenantId": "tenant-a",
  "occurredAt": { "$date": "2026-11-20T09:00:00Z" },
  "payload": {
    "orderId": "ord-101",
    "amount_vnd": 150000,
    "regionCode": "HCM"
  }
}
~~~

### 3.2. Hoàn tiền

Document gốc trong `refund_events`:

~~~json
{
  "_id": "r-101",
  "tenantId": "tenant-a",
  "occurredAt": { "$date": "2026-11-20T09:10:00Z" },
  "details": {
    "orderRef": "ord-101",
    "refund_vnd": 40000,
    "reason": "RETURN"
  }
}
~~~

Điểm khác nhau:

| Ý nghĩa | order_events | refund_events | Output thống nhất |
|---|---|---|---|
Khóa sự kiện | `_id` | `_id` | `eventId` |
Nguồn | Ngầm hiểu là ORDER | Ngầm hiểu là REFUND | `source` |
Tenant | `tenantId` | `tenantId` | `tenantId` |
Mã đơn | `payload.orderId` | `details.orderRef` | `orderId` |
Tiền | `payload.amount_vnd` dương | `details.refund_vnd` dương | `netAmountVnd`: ORDER dương, REFUND âm |
Thời gian | `occurredAt` | `occurredAt` | `occurredAt` |

Để hình dung thêm một đợt dữ liệu:

| eventId | source | tenant | orderId | số tiền nguồn | netAmountVnd |
|---|---|---|---|---:|---:|
| `o-101` | ORDER | tenant-a | ord-101 | 150.000 | +150.000 |
| `o-102` | ORDER | tenant-a | ord-102 | 60.000 | +60.000 |
| `r-101` | REFUND | tenant-a | ord-101 | 40.000 | −40.000 |
| `o-201` | ORDER | tenant-b | ord-201 | 900.000 | +900.000 |
| `r-201` | REFUND | tenant-b | ord-201 | 200.000 | −200.000 |

Timeline của `tenant-a` phải trả **ba dòng** với tổng tiền ròng **170.000 VND**; hai dòng tenant-b không được tham gia.

## 4. Entity nguồn và quy tắc đặt tên BSON

Các record sau minh họa cách Spring Data MongoDB ánh xạ document; mỗi top-level `public record` đặt trong một file Java riêng, cùng package `com.example.events`.

**OrderPayload.java**

~~~java
package com.example.events;

import org.springframework.data.mongodb.core.mapping.Field;

public record OrderPayload(
        String orderId,
        @Field("amount_vnd") long amountVnd,
        String regionCode) {
}
~~~

**OrderEvent.java**

~~~java
package com.example.events;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "order_events")
public record OrderEvent(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        Instant occurredAt,
        OrderPayload payload) {
}
~~~

**RefundDetails.java**

~~~java
package com.example.events;

import org.springframework.data.mongodb.core.mapping.Field;

public record RefundDetails(
        String orderRef,
        @Field("refund_vnd") long refundVnd,
        String reason) {
}
~~~

**RefundEvent.java**

~~~java
package com.example.events;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "refund_events")
public record RefundEvent(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        Instant occurredAt,
        RefundDetails details) {
}
~~~

Trong Java có property `amountVnd`/`refundVnd`, nhưng trong BSON là `amount_vnd`/`refund_vnd`. **Raw MongoDB aggregation expression** cần tham chiếu đúng tên BSON, chẳng hạn `"$payload.amount_vnd"`, không phải cứ dùng tên property Java là Spring Data tự dịch mọi string trong một `Document` tùy chỉnh.

`@MongoId(FieldType.STRING)` bảo toàn `_id` kiểu BSON String; đây là lựa chọn của ví dụ, không phải quy tắc bắt buộc cho mọi ứng dụng.

## 5. $replaceRoot: đưa document lồng lên root

Giả sử chỉ muốn xem dữ liệu trong `payload` mà không cần metadata bao ngoài:

~~~javascript
db.order_events.aggregate([
  { $match: { _id: "o-101" } },
  { $replaceRoot: { newRoot: "$payload" } }
]);
~~~

Kết quả:

~~~json
{
  "orderId": "ord-101",
  "amount_vnd": 150000,
  "regionCode": "HCM"
}
~~~

**Toàn bộ root cũ đã bị thay**. Document output không còn `_id`, `tenantId` hoặc `occurredAt` vì các trường này không nằm trong `payload`.

Khi thực hiện `$replaceRoot`:

1. Giá trị của `newRoot` **phải là một document/object**.
2. Nếu `payload` bị thiếu, bằng `null` hoặc là scalar không phải object, pipeline có thể **báo lỗi**.
3. Các field không thuộc root mới sẽ biến mất, kể cả `_id` nếu không được bảo toàn.
4. Đây là biến đổi **kết quả aggregation**, không thay BSON document gốc trong collection.
5. Nếu root mới là một array, không được hiểu nó như một document thay thế hợp lệ; cần chuyển đổi/`$unwind` theo nhu cầu.

Vì vậy không nên dùng `$replaceRoot: { newRoot: "$payload" }` một cách mù quáng trên collection cũ chưa kiểm soát schema.

### 5.1. Bảo vệ khỏi payload thiếu hoặc sai kiểu

Khi cần bỏ các document không có payload object:

~~~javascript
db.order_events.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      payload: { $type: "object" }
    }
  },
  { $replaceRoot: { newRoot: "$payload" } }
]);
~~~

Nếu nghiệp vụ muốn **giữ** document có payload null/missing, có thể xây `newRoot` bằng `$ifNull` hoặc `$mergeObjects` với object mặc định. Tuy nhiên, **`$ifNull` không sửa được scalar sai kiểu** như chuỗi hoặc số; cần kiểm tra schema hoặc dùng điều kiện kiểu dữ liệu.

### 5.2. $replaceWith là cách viết tương đương

MongoDB cũng hỗ trợ stage `$replaceWith`:

~~~javascript
db.order_events.aggregate([
  { $match: { _id: "o-101" } },
  { $replaceWith: "$payload" }
]);
~~~

Nó có cùng ý tưởng thay root như `$replaceRoot`, nhưng cú pháp là expression trực tiếp. `$replaceWith` được bổ sung ở các phiên bản MongoDB mới hơn `$replaceRoot`; khi phải hỗ trợ server cũ, cần xác minh phiên bản trước khi chọn stage.

## 6. $replaceRoot kết hợp $mergeObjects để giữ metadata

Timeline cần giữ `eventId`, `source`, `tenantId` và `occurredAt`, đồng thời đưa nội dung `payload` ra root. `$mergeObjects` giúp tạo document kết hợp:

~~~javascript
db.order_events.aggregate([
  { $match: { tenantId: "tenant-a", payload: { $type: "object" } } },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$payload",
          {
            eventId: "$_id",
            source: { $literal: "ORDER" },
            tenantId: "$tenantId",
            occurredAt: "$occurredAt"
          }
        ]
      }
    }
  }
]);
~~~

Kết quả trung gian:

~~~json
{
  "orderId": "ord-101",
  "amount_vnd": 150000,
  "regionCode": "HCM",
  "eventId": "o-101",
  "source": "ORDER",
  "tenantId": "tenant-a",
  "occurredAt": { "$date": "2026-11-20T09:00:00Z" }
}
~~~

### 6.1. Thứ tự merge ảnh hưởng bảo mật

`$mergeObjects` lấy field trùng tên từ **operand xuất hiện sau**. Ở ví dụ, `"$payload"` đứng trước, còn metadata đáng tin cậy đứng sau:

~~~javascript
{ $mergeObjects: ["$payload", { tenantId: "$tenantId", source: "ORDER" }] }
~~~

Nếu payload do client kiểm soát chứa `tenantId: "tenant-b"` hoặc `source: "REFUND"`, metadata bên ngoài sẽ **ghi đè** các field đó. Đảo thứ tự có thể cho phép payload ghi đè tên field quan trọng.

Tuy nhiên, merge xong vẫn có thể còn nhiều field payload không được phép lộ. Một `$project` **whitelist** sau đó giúp chốt output schema.

### 6.2. $mergeObjects không thay schema validation

Trong expression:

- Operand bằng `null` có thể được bỏ qua theo semantics của `$mergeObjects`.
- Operand là một scalar không phải document có thể gây lỗi.
- Field trong payload có kiểu sai vẫn có thể được mang lên root.

Vì vậy, đặt `$match`/schema validation đúng trước replaceRoot; không cho rằng merge “chữa lành” dữ liệu cũ. Nếu có nhiều schema version, hãy xây migration hoặc nhánh xử lý tường minh.

## 7. Chuẩn hóa output bằng $set và $project sau replaceRoot

Sau `$replaceRoot` ở mục 6, output còn `amount_vnd` và `regionCode`. Timeline chỉ cần `netAmountVnd`; có thể thêm hai stage:

~~~javascript
{
  $set: {
    netAmountVnd: "$amount_vnd"
  }
},
{
  $project: {
    _id: 0,
    eventId: 1,
    source: 1,
    tenantId: 1,
    orderId: 1,
    netAmountVnd: 1,
    occurredAt: 1
  }
}
~~~

Đây là **hai stage** đặt tiếp sau stage `$replaceRoot`, không phải một command độc lập. `$set` tạo field mới từ field đã có trên root; `$project` loại `amount_vnd` và những field khác không nằm trong output contract.

Kết quả:

~~~json
{
  "eventId": "o-101",
  "source": "ORDER",
  "tenantId": "tenant-a",
  "orderId": "ord-101",
  "netAmountVnd": 150000,
  "occurredAt": { "$date": "2026-11-20T09:00:00Z" }
}
~~~

Một lưu ý khi nối stage: expression `"$amount_vnd"` **chỉ hợp lệ sau khi payload đã được nâng lên root**. Trước `$replaceRoot`, đường dẫn đúng là `"$payload.amount_vnd"`. Khi pipeline thay đổi hình dạng, các path cũ không tự còn đúng.

## 8. $unionWith: nối thêm kết quả từ collection khác

`$unionWith` có thể dùng dạng:

~~~javascript
{
  $unionWith: {
    coll: "refund_events",
    pipeline: [
      // Các stage chỉ áp dụng cho refund_events.
    ]
  }
}
~~~

Nó bổ sung kết quả của `refund_events` vào luồng đang chạy trên `order_events`. **Không có điều kiện join theo `orderId`** và cũng **không tự bỏ duplicate**; đây là hợp nhất các dòng kết quả, không phải ghép cột của cùng một dòng.

### 8.1. Ba đặc điểm phải nhớ

1. **Hai nhánh có thể có schema khác nhau.** MongoDB không tự kiểm tra và chuẩn hóa field giữa hai nhánh cho ứng dụng.
2. **Kết quả có thể chứa trùng lặp.** Nếu hai nhánh sinh cùng một event hoặc cùng collection được union, chúng vẫn có thể xuất hiện hai lần.
3. **Thứ tự kết quả không được bảo đảm chỉ bởi thứ tự nhánh.** Muốn timeline có thứ tự, đặt `$sort` rõ ràng **sau `$unionWith`**.

Mặc dù output có thể hiển thị các dòng nhánh đầu trước nhánh sau trong một số lần chạy, đừng viết UI/test phụ thuộc vào thứ tự tự nhiên đó.

### 8.2. Khác biệt với $lookup

Giả sử đơn `ord-101` có hai lần hoàn tiền:

- `$lookup`: có thể trả **một document đơn hàng** với mảng `refunds` gồm hai phần tử.
- `$unionWith`: trả **một dòng ORDER và hai dòng REFUND** theo output schema thống nhất.

Vì thế, dùng `$unionWith` khi muốn một danh sách sự kiện đa nguồn; dùng `$lookup` khi muốn bổ sung quan hệ của một document nguồn với tập document khác. Nếu mục tiêu là báo cáo tổng tiền, có thể union các dòng đã chuẩn hóa rồi `$group`.

## 9. Pipeline đầy đủ: ORDER và REFUND cùng output schema

Đây là pipeline MongoDB shell mô tả **hai nhánh**. Nhánh ORDER chuẩn hóa `payload.amount_vnd` thành số tiền dương; nhánh REFUND chuẩn hóa `details.refund_vnd` thành số tiền âm:

~~~javascript
db.order_events.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      payload: { $type: "object" },
      "payload.amount_vnd": { $type: "number" }
    }
  },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$payload",
          {
            eventId: "$_id",
            source: { $literal: "ORDER" },
            tenantId: "$tenantId",
            occurredAt: "$occurredAt"
          }
        ]
      }
    }
  },
  { $set: { netAmountVnd: "$amount_vnd" } },
  {
    $project: {
      _id: 0, eventId: 1, source: 1, tenantId: 1,
      orderId: 1, netAmountVnd: 1, occurredAt: 1
    }
  },
  {
    $unionWith: {
      coll: "refund_events",
      pipeline: [
        {
          $match: {
            tenantId: "tenant-a",
            details: { $type: "object" },
            "details.refund_vnd": { $type: "number" }
          }
        },
        {
          $replaceRoot: {
            newRoot: {
              $mergeObjects: [
                "$details",
                {
                  eventId: "$_id",
                  source: { $literal: "REFUND" },
                  tenantId: "$tenantId",
                  occurredAt: "$occurredAt"
                }
              ]
            }
          }
        },
        {
          $set: {
            orderId: "$orderRef",
            netAmountVnd: { $multiply: ["$refund_vnd", -1] }
          }
        },
        {
          $project: {
            _id: 0, eventId: 1, source: 1, tenantId: 1,
            orderId: 1, netAmountVnd: 1, occurredAt: 1
          }
        }
      ]
    }
  },
  { $sort: { occurredAt: -1, source: 1, eventId: 1 } },
  { $limit: 100 }
]);
~~~

### 9.1. Vì sao lọc tenant ở cả hai nhánh?

`$match` đầu pipeline chỉ lọc collection **order_events**. Nó **không tự áp dụng** cho nhánh `refund_events` bên trong `$unionWith`. Nếu quên `$match` của nhánh refund, kết quả timeline có thể lộ dữ liệu hoàn tiền của **tenant khác**.

Đây là một lỗi phân quyền nghiêm trọng. Luôn đưa tenant/authorization filter đáng tin cậy vào **từng nhánh nguồn**. Đừng chờ đến khi union xong mới lọc theo tenant nếu trước đó pipeline đã tổng hợp/biến đổi làm mất metadata bảo mật.

### 9.2. Vì sao cùng alias và cùng kiểu?

Nhánh ORDER dùng:

~~~javascript
{ netAmountVnd: "$amount_vnd" }
~~~

Nhánh REFUND dùng:

~~~javascript
{ netAmountVnd: { $multiply: ["$refund_vnd", -1] } }
~~~

Nếu một nhánh trả `amountVnd`, còn nhánh kia trả `netAmountVnd`, MongoDB vẫn union được, nhưng DTO với field `netAmountVnd` có thể nhận thiếu dữ liệu của một nhánh. Tương tự, nếu nhánh refund trả số âm dưới dạng String trong khi nhánh order trả Long, phép `$sum` sau union không còn đúng như mong muốn.

**Chuẩn hóa cả tên field, BSON type, đơn vị tiền, quy ước dấu và ý nghĩa nghiệp vụ** trước khi dùng kết quả đa nguồn.

### 9.3. $limit phải nằm sau sort của toàn tập

`$sort` cuối pipeline xếp mọi dòng từ cả hai collection rồi `$limit` cắt 100 dòng mới nhất. Nếu đặt `$limit: 100` **trước `$unionWith`**, giới hạn chỉ áp dụng vào nhánh đầu, không bảo đảm chỉ trả 100 dòng của toàn bộ kết quả.

Nếu đặt `$sort` riêng trong từng nhánh mà không sort lại sau union, **thứ tự cuối cùng vẫn không được bảo đảm**.

## 10. Java DTO của kết quả đã chuẩn hóa

Sau pipeline, cả ORDER và REFUND đều có cấu trúc giống nhau. Tạo một Java record để biểu diễn:

**UnifiedEventDto.java**

~~~java
package com.example.events;

import java.time.Instant;

public record UnifiedEventDto(
        String eventId,
        String source,
        String tenantId,
        String orderId,
        long netAmountVnd,
        Instant occurredAt) {
}
~~~

Với dữ liệu mục 3, kỳ vọng ba dòng của tenant-a theo thứ tự giảm dần thời gian:

| eventId | source | orderId | netAmountVnd | occurredAt |
|---|---|---|---:|---|
| `r-101` | REFUND | ord-101 | −40.000 | 09:10 |
| `o-102` | ORDER | ord-102 | +60.000 | 09:05 |
| `o-101` | ORDER | ord-101 | +150.000 | 09:00 |

Không nên đưa thẳng `OrderEvent` hay `RefundEvent` làm output type: các model đó có field lồng và tên field khác. DTO phản ánh **schema sau hai nhánh đã chuẩn hóa**.

Nếu dữ liệu lịch sử thiếu `occurredAt` hoặc `orderId`, cần validate hoặc xử lý fallback tường minh. Primitive `long netAmountVnd` không thể biểu diễn null như `Long`; tốt nhất kiểm tra tính hợp lệ của input và output thay vì im lặng cho giá trị mặc định.

## 11. Spring Data MongoDB: dựng stage bằng AggregationOperation

Spring Data có nhiều builder aggregation, nhưng chữ ký các builder `replaceRoot`/`unionWith` có thể khác giữa các phiên bản. Để trình bày một ví dụ **có thể đọc và đối chiếu trực tiếp với BSON**, ta dùng `AggregationOperation`:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

AggregationOperation stage = context ->
        new Document("$replaceRoot",
                new Document("newRoot", "$payload"));
~~~

`AggregationOperation` biểu diễn **một stage**. Phương thức `toDocument(context)` trả BSON stage tương ứng. Khi tạo raw `Document`, ta đang dùng tên BSON vật lý và field references dưới dạng chuỗi bắt đầu bằng `$`.

Đây là lựa chọn chủ động cho pipeline ghép hai collection có schema khác nhau:

- Không nhầm metadata Java của nguồn ORDER với metadata Java của nguồn REFUND.
- Không phụ thuộc tên một builder nâng cao cụ thể trong mọi nhánh phiên bản.
- Dễ so sánh từng stage với lệnh MongoDB shell.

Đổi lại, **raw BSON không type-safe** và nhiều string field path không được tự kiểm tra tại compile time. Production cần integration test, review quyền truy cập và xác minh command BSON thực tế.

### 11.1. Không ghép JSON từ input người dùng

Không xây lệnh như:

~~~java
// KHÔNG làm thế này với input từ client:
String json = "{ $match: { tenantId: '" + userInput + "' } }";
~~~

Thay vào đó, gán giá trị vào `Document` như một value:

~~~java
Document match = new Document("$match",
        new Document("tenantId", authenticatedTenantId));
~~~

`authenticatedTenantId` phải được lấy từ ngữ cảnh xác thực/ủy quyền đáng tin, không phải bất kỳ tenant nào client tự chọn. Khi dùng `Document`, hãy whitelist tên field và toán tử thay vì nhận toàn bộ BSON query từ client.

## 12. Service Spring Data đầy đủ cho timeline và báo cáo ròng

Code dưới đây dùng `MongoTemplate.aggregate` với **collection name** và các raw `AggregationOperation`. Điều này có chủ đích: ORDER và REFUND có metadata `@Field` khác nhau, nên mỗi nhánh dùng **tên BSON đã chuẩn hóa rõ**.

**UnifiedEventReportService.java**

~~~java
package com.example.events;

import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.stereotype.Service;

@Service
public class UnifiedEventReportService {
    private final MongoTemplate mongo;

    public UnifiedEventReportService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    private static AggregationOperation stage(Document bson) {
        return context -> bson;
    }

    private static void validateTenant(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId không hợp lệ");
        }
    }

    private List<AggregationOperation> unifiedStages(String tenantId) {
        validateTenant(tenantId);

        Document orderMatch = new Document("$match",
                new Document("tenantId", tenantId)
                        .append("payload", new Document("$type", "object"))
                        .append("payload.amount_vnd",
                                new Document("$type", "number")));

        Document orderMetadata = new Document("eventId", "$_id")
                .append("source", new Document("$literal", "ORDER"))
                .append("tenantId", "$tenantId")
                .append("occurredAt", "$occurredAt");

        Document orderRoot = new Document("$replaceRoot",
                new Document("newRoot",
                        new Document("$mergeObjects", List.of(
                                "$payload", orderMetadata))));

        Document orderSet = new Document("$set",
                new Document("netAmountVnd", "$amount_vnd"));

        Document commonProjection = new Document("_id", 0)
                .append("eventId", 1)
                .append("source", 1)
                .append("tenantId", 1)
                .append("orderId", 1)
                .append("netAmountVnd", 1)
                .append("occurredAt", 1);

        Document refundMatch = new Document("$match",
                new Document("tenantId", tenantId)
                        .append("details", new Document("$type", "object"))
                        .append("details.refund_vnd",
                                new Document("$type", "number")));

        Document refundMetadata = new Document("eventId", "$_id")
                .append("source", new Document("$literal", "REFUND"))
                .append("tenantId", "$tenantId")
                .append("occurredAt", "$occurredAt");

        Document refundRoot = new Document("$replaceRoot",
                new Document("newRoot",
                        new Document("$mergeObjects", List.of(
                                "$details", refundMetadata))));

        Document refundSet = new Document("$set",
                new Document("orderId", "$orderRef")
                        .append("netAmountVnd",
                                new Document("$multiply",
                                        List.of("$refund_vnd", -1))));

        List<Document> refundStages = List.of(
                refundMatch,
                refundRoot,
                refundSet,
                new Document("$project", commonProjection));

        Document union = new Document("$unionWith",
                new Document("coll", "refund_events")
                        .append("pipeline", refundStages));

        return List.of(
                stage(orderMatch),
                stage(orderRoot),
                stage(orderSet),
                stage(new Document("$project", commonProjection)),
                stage(union));
    }

    private Aggregation timelinePipeline(String tenantId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải nằm trong 1..100");
        }
        List<AggregationOperation> stages =
                new ArrayList<>(unifiedStages(tenantId));
        stages.add(stage(new Document("$sort",
                new Document("occurredAt", -1)
                        .append("source", 1)
                        .append("eventId", 1))));
        stages.add(stage(new Document("$limit", limit)));
        return Aggregation.newAggregation(stages);
    }

    public List<UnifiedEventDto> timeline(
            String tenantId, int limit) {
        AggregationResults<UnifiedEventDto> results =
                mongo.aggregate(
                        timelinePipeline(tenantId, limit),
                        "order_events",
                        UnifiedEventDto.class);
        return results.getMappedResults();
    }

    public List<Document> timelineDocuments(
            String tenantId, int limit) {
        return mongo.aggregate(
                timelinePipeline(tenantId, limit),
                "order_events",
                Document.class).getMappedResults();
    }

    public List<OrderBalanceDto> balanceByOrder(String tenantId) {
        List<AggregationOperation> stages =
                new ArrayList<>(unifiedStages(tenantId));

        stages.add(stage(new Document("$group",
                new Document("_id", "$orderId")
                        .append("eventCount", new Document("$sum", 1))
                        .append("netVnd",
                                new Document("$sum", "$netAmountVnd")))));
        stages.add(stage(new Document("$project",
                new Document("_id", 0)
                        .append("orderId", "$_id")
                        .append("eventCount", 1)
                        .append("netVnd", 1))));
        stages.add(stage(new Document("$sort",
                new Document("orderId", 1))));

        return mongo.aggregate(
                Aggregation.newAggregation(stages),
                "order_events",
                OrderBalanceDto.class).getMappedResults();
    }
}
~~~

**OrderBalanceDto.java**

~~~java
package com.example.events;

public record OrderBalanceDto(
        String orderId,
        long eventCount,
        long netVnd) {
}
~~~

### 12.1. Vì sao các stage dùng Document thay vì tên property Java?

Trong `OrderPayload`, tên Java `amountVnd` được ánh xạ thành `amount_vnd`. Trong `RefundDetails`, tên Java `refundVnd` được ánh xạ thành `refund_vnd`. Pipeline raw cố ý dùng:

~~~java
"payload.amount_vnd"
"details.refund_vnd"
"$amount_vnd"
"$refund_vnd"
~~~

**Không viết `"$amountVnd"`** rồi mặc định một custom stage `Document` sẽ tự được map sang field BSON. Một TypedAggregation theo `OrderEvent.class` cũng không thể tự suy metadata cho toàn bộ collection refund của `$unionWith` nếu nhánh đó được diễn đạt bằng raw BSON.

Các phiên bản Spring Data có những builder như `ReplaceRootOperation` và `UnionWithOperation`; có thể dùng chúng nếu API thực tế hỗ trợ đầy đủ pipeline, mapping context và semantics mà dự án cần. Với pipeline có nhiều schema nguồn, **đọc kết quả BSON thực tế là bước xác minh bắt buộc**.

### 12.2. Tại sao tách hai method timeline và balanceByOrder?

Timeline cần **giữ mọi event**, sort theo thời gian rồi limit. Báo cáo theo đơn cần **nhóm toàn bộ event của tenant** rồi tính net.

Nếu tái sử dụng một pipeline timeline đã `$limit: 100` để cộng tổng, báo cáo sẽ sai với tenant có hơn 100 sự kiện. Bởi vậy `balanceByOrder` chỉ dùng các stage chuẩn hóa và union; nó **không áp dụng limit timeline trước khi group**.

### 12.3. Document không phải output entity

`timelineDocuments(...)` trả `List<Document>` với các field **đã chuẩn hóa**. Nó không trả raw document từ hai collection. Nếu muốn đọc source documents, dùng truy vấn nguồn riêng. Nếu muốn BSON phản hồi ở cấp lệnh aggregation, `AggregationResults.getRawResults()` có ý nghĩa khác với mỗi `Document` trong `getMappedResults()`.

## 13. Kiểm tra kết quả: DTO, Document và số liệu

Với dữ liệu mẫu:

~~~java
List<UnifiedEventDto> events =
        reportService.timeline("tenant-a", 100);

for (UnifiedEventDto e : events) {
    System.out.println(e.source() + " " + e.orderId()
            + " " + e.netAmountVnd());
}
~~~

`reportService` là bean `UnifiedEventReportService`. Kết quả mong đợi:

~~~text
REFUND ord-101 -40000
ORDER ord-102 60000
ORDER ord-101 150000
~~~

Đọc bằng Document:

~~~java
List<Document> documents =
        reportService.timelineDocuments("tenant-a", 100);

for (Document row : documents) {
    String eventId = row.getString("eventId");
    String source = row.getString("source");
    Object netAmount = row.get("netAmountVnd");

    if (!(netAmount instanceof Number amount)) {
        throw new IllegalStateException(
                "netAmountVnd phải là BSON number");
    }
    System.out.println(eventId + " " + source
            + " " + amount.longValue());
}
~~~

**Kiểu BSON số có thể khác nhau**: Int32, Int64, Double, Decimal128. `Number.longValue()` trong ví dụ chỉ thích hợp khi dữ liệu đã được validation là số nguyên và nằm trong miền `long`. Với tiền có phần lẻ hoặc Decimal128, chuyển đổi sang `BigDecimal` theo quy tắc tài chính; không đi qua `double` tùy tiện.

Với `balanceByOrder("tenant-a")`:

| orderId | eventCount | netVnd |
|---|---:|---:|
| `ord-101` | 2 | 110.000 |
| `ord-102` | 1 | 60.000 |

**Tổng ròng = 170.000 VND.** Các giá trị này chỉ đúng theo định nghĩa “sự kiện ORDER ghi tiền dương, REFUND ghi tiền âm”. Một hệ thống kế toán thật cần thêm quy tắc về giao dịch đảo, phí, thuế, tiền tệ, partial refund, chargeback và event bị phát lại.

## 14. $unionWith không khử trùng: phải định nghĩa khóa và semantics

`$unionWith` mang ngữ nghĩa tương tự **UNION ALL**, không phải **UNION DISTINCT**. Nếu cùng một sự kiện xuất hiện trong cả hai nhánh, hoặc một nhánh được đưa vào hai lần, kết quả có thể chứa hai dòng giống nhau.

Ví dụ:

~~~javascript
db.order_events.aggregate([
  { $project: { _id: 0, eventId: "$_id" } },
  {
    $unionWith: {
      coll: "order_events",
      pipeline: [
        { $project: { _id: 0, eventId: "$_id" } }
      ]
    }
  }
]);
~~~

Mỗi `eventId` của collection `order_events` có thể xuất hiện **hai lần**. MongoDB không tự kiểm tra hai dòng trùng nhau.

### 14.1. Tạo khóa định danh đa nguồn

Không thể mặc định `eventId` là duy nhất **giữa các collection**. Một document có `_id: "101"` ở ORDER và một document khác có cùng `_id` ở REFUND vẫn là hai sự kiện độc lập.

Trong timeline thống nhất, khóa logic có thể là:

~~~text
source + ":" + eventId
~~~

Hoặc dùng tuple `(source, eventId)`. Nếu dữ liệu nhiều tenant và ID chỉ unique trong tenant, thêm `tenantId` vào khóa. Khi xây cursor, checkpoint, response ID hoặc deduplication key, phải dùng **đúng namespace**.

### 14.2. Khử trùng có chủ đích bằng $group

Với output đã chuẩn hóa, nếu yêu cầu loại các **bản sao của cùng một event**, có thể dùng:

~~~javascript
{
  $group: {
    _id: { source: "$source", eventId: "$eventId" },
    event: { $first: "$$ROOT" }
  }
},
{
  $replaceRoot: { newRoot: "$event" }
}
~~~

Nhưng `$first` lựa chọn một document dựa trên thứ tự đầu vào. Nếu các dòng trùng key lại **khác nội dung**, cần có chính sách chọn bản đúng (revision, timestamp, source authority) và một `$sort` phù hợp trước nhóm. Nếu không, kết quả được giữ có thể không xác định. Sau group cũng cần sort lại nếu caller yêu cầu thứ tự.

Đặc biệt, **không tự khử trùng các lần hoàn tiền khác nhau có cùng `orderId`**. Hai lần refund hợp lệ của cùng đơn phải là hai sự kiện; gom theo orderId chỉ phù hợp khi **tính tổng**, không phải deduplicate event.

## 15. Group sau union: biến tập sự kiện thành báo cáo

Khi hai nguồn đã có chung field `netAmountVnd`, báo cáo theo đơn trở nên đơn giản:

~~~javascript
// Thêm sau stage $unionWith của pipeline chuẩn hóa.
{
  $group: {
    _id: "$orderId",
    eventCount: { $sum: 1 },
    netVnd: { $sum: "$netAmountVnd" }
  }
},
{
  $project: {
    _id: 0,
    orderId: "$_id",
    eventCount: 1,
    netVnd: 1
  }
}
~~~

Khi `$group` thực thi, schema output **lại thay đổi**:

~~~text
Trước $group:
  eventId, source, tenantId, orderId, netAmountVnd, occurredAt

Sau $group:
  _id (orderId), eventCount, netVnd

Sau $project:
  orderId, eventCount, netVnd
~~~

Đây là lý do `OrderBalanceDto` phải **khác `UnifiedEventDto`**. Không lưu hay ánh xạ một dòng báo cáo ròng thành entity gốc chỉ vì pipeline bắt đầu từ collection đơn hàng.

Nếu cần tổng theo vùng, vùng của hoàn tiền cũng phải được xác định rõ theo nghiệp vụ: refund có thể phải lấy vùng của đơn gốc từ nguồn chuẩn, chứ không tự có cùng `regionCode`. `$unionWith` không tự join theo khóa; nếu thiếu dữ liệu cần thiết, phải thiết kế source schema hoặc bước join riêng trước/sau union.

## 16. $sort, $skip, $limit và tính ổn định giữa các request

Timeline có thể dùng:

~~~javascript
{ $sort: { occurredAt: -1, source: 1, eventId: 1 } },
{ $skip: 20 },
{ $limit: 20 }
~~~

`occurredAt DESC` đưa sự kiện mới lên trước; `source ASC, eventId ASC` giúp phá hòa nếu timestamp trùng. Tuy nhiên:

- Sort ổn định khi tập dữ liệu không đổi **không tạo snapshot** qua nhiều lần gọi.
- Insert mới vào đầu timeline có thể làm offset tiếp theo trả lại một event đã thấy.
- Xóa hoặc đổi timestamp có thể làm bỏ sót event.
- `skip` sâu vẫn có thể tốn tài nguyên sau khi server đã đọc và chuẩn hóa nhiều dòng từ hai nguồn.

Nếu cần scrolling dài, cân nhắc **keyset cursor** dựa trên tuple sort (`occurredAt`, `source`, `eventId`). Nhưng điều kiện “sau cursor” phải được áp dụng **cho cả hai nhánh** theo cùng quy tắc thứ tự; không chỉ áp dụng ở nhánh ORDER rồi union REFUND không giới hạn.

### 16.1. Thứ tự stage ảnh hưởng kết quả

| Vị trí stage | Hệ quả |
|---|---|
`$match tenant` trong cả hai nhánh | Không trộn dữ liệu tenant |
`$project` sớm trong từng nhánh | Giảm field/payload trung gian, giữ output nhất quán |
`$unionWith` sau chuẩn hóa | Hai tập có thể xử lý thống nhất |
`$sort` sau union | Sort toàn bộ timeline |
`$limit` sau sort | Lấy N sự kiện đúng theo thứ tự toàn tập |
`$group` sau union | Tổng hợp trên cả hai nguồn |
`$limit` trước group tổng doanh thu | Có nguy cơ báo cáo thiếu dữ liệu |

Không tự động cho rằng hai `$sort` ở các nhánh được bảo toàn qua union. Và không áp dụng limit trong code Java sau khi lấy toàn bộ dữ liệu nếu có thể giảm lượng kết quả ngay tại server.

## 17. Hiệu năng, index, collation và các giới hạn triển khai

### 17.1. $match từng nguồn để giảm việc đọc

Index ứng viên khi thường xuyên lọc tenant và đọc timeline theo thời gian:

~~~javascript
db.order_events.createIndex(
  { tenantId: 1, occurredAt: -1, _id: 1 },
  { name: "idx_order_tenant_time_id" }
);

db.refund_events.createIndex(
  { tenantId: 1, occurredAt: -1, _id: 1 },
  { name: "idx_refund_tenant_time_id" }
);
~~~

Hai collection có **index riêng**. Không thể tạo một index B-tree duy nhất bao phủ hai collection. Kể cả khi mỗi nhánh dùng index tốt cho `$match`, `$sort` cuối trên kết quả union có thể cần xử lý trên tập kết quả trung gian. Điều đó không tự được giải quyết bởi việc có index ở từng nguồn.

Khi filter có thêm trạng thái, thời gian hoặc loại sự kiện, cần xây index theo workload; đừng mặc định index trên `tenantId + occurredAt` tối ưu mọi truy vấn `$unionWith`.

### 17.2. Xem explain và profiler

Chạy pipeline tương đương với:

~~~javascript
db.order_events.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-a" } },
  {
    $unionWith: {
      coll: "refund_events",
      pipeline: [
        { $match: { tenantId: "tenant-a" } }
      ]
    }
  }
]);
~~~

Đây là pipeline **rút gọn để xem kế hoạch**, không phải pipeline chuẩn hóa đầy đủ của mục 9. Với pipeline thật, cần đối chiếu `keysExamined`, `docsExamined`, stage sort/group và thời gian. Các công cụ quan sát có thể hiển thị execution stats của nhánh union khác nhau theo phiên bản server; không dựa vào một trường thống kê duy nhất nếu không thấy đủ hai nhánh.

Đo cả:

- Số document mỗi nhánh đọc trước khi filter và số dòng kết quả sau chuẩn hóa.
- CPU và memory cho `$replaceRoot`/`$mergeObjects`/`$sort`/`$group`.
- Network payload, latency p95/p99, tốc độ tăng dữ liệu của hai collection.
- Tác động của index mới lên tốc độ insert các event.
- BSON type conversion khi output được map thành Java DTO hoặc Document.

### 17.3. Collation và so sánh String

Nếu hai collection được tạo với **default collation khác nhau**, hoặc sort/so sánh chuỗi yêu cầu quy tắc ngôn ngữ riêng, cần kiểm tra yêu cầu collation của `$unionWith` và chỉ định collation aggregation phù hợp ở cấp lệnh khi phiên bản API hỗ trợ.

Một tên field String có thể được so sánh khác theo case/locale; điều này ảnh hưởng sort, group và dedup. Không giả định mọi collection có cùng collation hoặc ID String theo quy tắc case-insensitive. Với khóa sự kiện, thường cần cách so sánh xác định và thống nhất.

### 17.4. Giới hạn và tính năng không tương thích

- `$unionWith` yêu cầu MongoDB từ **4.4** và có các hạn chế về pipeline con, môi trường chạy và topology.
- Không coi `$unionWith` là stage hợp lệ trong mọi transaction; MongoDB có hạn chế sử dụng `$unionWith` trong transaction. Hãy xác minh theo phiên bản server nếu code đang chạy trong `@Transactional` hoặc session transaction.
- Pipeline con của `$unionWith` không được tùy tiện sử dụng các stage ghi như `$out` hoặc `$merge`.
- Một số tổ hợp liên quan view, collation, sharding hoặc stage tìm kiếm có quy tắc riêng, phải kiểm tra tài liệu đúng version.
- Khi output group/sort rất lớn, MongoDB có giới hạn bộ nhớ/stage; tùy phiên bản có thể cần `allowDiskUse` hoặc thiết kế pre-aggregation.

Đừng dùng một ví dụ hoạt động trên MongoDB standalone mới để mặc định mọi topology/phiên bản production hỗ trợ cùng khả năng.

## 18. Bảo mật và độ tin cậy của dữ liệu đa nguồn

Khi kết hợp collection, một lỗi nhỏ ở một nhánh có thể gây tác động rộng:

### 18.1. Tenant và authorization

- Lọc `tenantId` trong ORDER và REFUND từ **auth context đáng tin cậy**.
- Không lấy tenant chỉ từ query parameter rồi tin hoàn toàn.
- Không chỉ lọc tenant **sau** `$group`: dữ liệu đã bị tổng hợp lẫn từ trước.
- Nếu quyền truy cập khác nhau theo từng loại event, áp dụng điều kiện tương ứng trong từng nhánh.
- Không công khai mọi field từ `payload`/`details`; sử dụng `$project` whitelist.

### 18.2. Tính hợp lệ của tiền và event

- `amount_vnd`/`refund_vnd` phải có kiểu số đúng, không âm nếu là số tiền nguồn.
- Không trộn VND và ngoại tệ vào một `netAmountVnd` mà không có quy đổi/nhóm theo currency.
- Một refund có thể là một phần của đơn; đừng “dedup theo orderId” làm mất refund hợp lệ.
- Nếu event có trạng thái `CANCELLED`/`REVERSED`, cần định nghĩa có tham gia timeline và báo cáo ròng không.
- Retry khi ghi event có thể tạo bản sao; unique event ID/idempotency ở **đường ghi** thường cần thiết hơn khử trùng sau union.
- Khi dữ liệu giữa hai collection thay đổi trong lúc query, không tự suy luận aggregation luôn cho snapshot nghiệp vụ qua mọi topology/read concern.

### 18.3. Logging và thông tin nhạy cảm

Pipeline BSON có thể chứa tenant ID, order ID và số tiền. Với MongoDB Java Driver `CommandListener` hoặc profiler, chỉ bật logging theo chính sách được phép, ẩn thông tin nhạy cảm và giới hạn thời gian lưu.

DTO output là lớp kiểm soát field giúp tránh rò cấu trúc nội bộ, nhưng **không thay thế** authorization và filter ở database.

## 19. Kiểm thử tích hợp trên MongoDB thật

Mock `MongoTemplate` chỉ chứng minh service gọi API. Nó **không xác minh** MongoDB hiểu `$replaceRoot`, `$unionWith`, `$mergeObjects` hay tên BSON raw đúng. Nên kiểm thử trên MongoDB thật có phiên bản hỗ trợ `$unionWith`, ví dụ Testcontainers. Spring Boot `@DataMongoTest` nạp hạ tầng Spring Data MongoDB nhưng **không tự khởi động server**.

### 19.1. Test seed cả hai collection

**UnifiedEventReportServiceTest.java**

~~~java
package com.example.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(UnifiedEventReportService.class)
class UnifiedEventReportServiceTest {

    @Autowired MongoTemplate mongo;
    @Autowired UnifiedEventReportService reports;

    private Date at(String instant) {
        return Date.from(Instant.parse(instant));
    }

    @BeforeEach
    void seed() {
        // Chỉ xóa dữ liệu trong DB test được cô lập.
        mongo.getCollection("order_events").deleteMany(new Document());
        mongo.getCollection("refund_events").deleteMany(new Document());

        mongo.getCollection("order_events").insertMany(List.of(
                new Document("_id", "o-101")
                        .append("tenantId", "tenant-a")
                        .append("occurredAt", at("2026-11-20T09:00:00Z"))
                        .append("payload",
                                new Document("orderId", "ord-101")
                                        .append("amount_vnd", 150000L)
                                        .append("regionCode", "HCM")),
                new Document("_id", "o-102")
                        .append("tenantId", "tenant-a")
                        .append("occurredAt", at("2026-11-20T09:05:00Z"))
                        .append("payload",
                                new Document("orderId", "ord-102")
                                        .append("amount_vnd", 60000L)
                                        .append("regionCode", "HN")),
                new Document("_id", "o-201")
                        .append("tenantId", "tenant-b")
                        .append("occurredAt", at("2026-11-20T09:30:00Z"))
                        .append("payload",
                                new Document("orderId", "ord-201")
                                        .append("amount_vnd", 900000L))));

        mongo.getCollection("refund_events").insertMany(List.of(
                new Document("_id", "r-101")
                        .append("tenantId", "tenant-a")
                        .append("occurredAt", at("2026-11-20T09:10:00Z"))
                        .append("details",
                                new Document("orderRef", "ord-101")
                                        .append("refund_vnd", 40000L)
                                        .append("reason", "RETURN")),
                new Document("_id", "r-201")
                        .append("tenantId", "tenant-b")
                        .append("occurredAt", at("2026-11-20T09:15:00Z"))
                        .append("details",
                                new Document("orderRef", "ord-201")
                                        .append("refund_vnd", 200000L))));
    }

    @Test
    void timelineUnifiesShapeAndFiltersBothTenants() {
        List<UnifiedEventDto> rows = reports.timeline("tenant-a", 100);

        assertThat(rows).hasSize(3);
        assertThat(rows).extracting(UnifiedEventDto::eventId)
                .containsExactly("r-101", "o-102", "o-101");
        assertThat(rows).extracting(UnifiedEventDto::source)
                .containsExactly("REFUND", "ORDER", "ORDER");
        assertThat(rows).extracting(UnifiedEventDto::tenantId)
                .containsOnly("tenant-a");
        assertThat(rows).extracting(UnifiedEventDto::netAmountVnd)
                .containsExactly(-40000L, 60000L, 150000L);
    }

    @Test
    void outputDocumentHasWhitelistedShape() {
        List<Document> rows = reports.timelineDocuments("tenant-a", 100);
        Document refund = rows.get(0);

        assertThat(refund.getString("source")).isEqualTo("REFUND");
        assertThat(refund.getString("orderId")).isEqualTo("ord-101");
        assertThat(refund.containsKey("_id")).isFalse();
        assertThat(refund.containsKey("details")).isFalse();
        assertThat(refund.containsKey("payload")).isFalse();
        assertThat(refund.containsKey("reason")).isFalse();

        Object amount = refund.get("netAmountVnd");
        assertThat(amount).isInstanceOf(Number.class);
        assertThat(((Number) amount).longValue()).isEqualTo(-40000L);
    }

    @Test
    void groupAfterUnionUsesAllEventsNotTimelineLimit() {
        List<OrderBalanceDto> balances =
                reports.balanceByOrder("tenant-a");

        assertThat(balances).containsExactly(
                new OrderBalanceDto("ord-101", 2L, 110000L),
                new OrderBalanceDto("ord-102", 1L, 60000L));
    }

    @Test
    void otherTenantDoesNotLeakIntoResult() {
        List<UnifiedEventDto> tenantB = reports.timeline("tenant-b", 100);
        assertThat(tenantB).extracting(UnifiedEventDto::eventId)
                .containsExactly("o-201", "r-201");
        assertThat(tenantB).extracting(UnifiedEventDto::tenantId)
                .containsOnly("tenant-b");
    }
}
~~~

**Lưu ý:** test `tenantB` ở trên dùng thứ tự `occurredAt DESC`. Vì `o-201` lúc 09:30 và `r-201` lúc 09:15, kết quả là `o-201, r-201`. Test làm rõ sort được thực hiện **sau khi union**, không dựa vào thứ tự nhánh.

### 19.2. Kiểm thử trường hợp dữ liệu lỗi

Những test nên bổ sung:

| Case | Mục tiêu |
|---|---|
`payload = null` hoặc thiếu | Stage filter loại dữ liệu không có object trước replaceRoot |
`payload` là String | Không thực hiện replaceRoot trên scalar sai kiểu |
`payload.amount_vnd` thiếu hoặc là String | Không được map thành số tiền hợp lệ |
`details.refund_vnd` null/sai kiểu | Định nghĩa policy thay vì âm thầm cộng sai |
Order và refund có cùng eventId | Không coi hai nguồn là một event khi key namespace khác |
Hai lần refund khác ID cùng orderId | Không bị deduplicate khi báo cáo ròng |
Payload cố tình có `tenantId`/`source` giả | Metadata cuối `$mergeObjects` ghi đè, `$project` whitelist |
Tenant có 0 event ORDER nhưng có REFUND | Nhánh refund vẫn có thể xuất hiện sau union |
Timestamp trùng | Sort có tie-breaker source/eventId |
Nhiều hơn timeline limit | Tổng `balanceByOrder` vẫn dùng đủ event |
Server không hỗ trợ `$unionWith` | Test phát hiện lỗi phiên bản, không bỏ qua âm thầm |
Số tiền quá miền Int64 hoặc Decimal128 | Mapping và quy tắc chính xác số |

### 19.3. Kiểm tra BSON command và execution

Nếu cần xác minh raw pipeline do Java gửi, dùng `CommandListener` của MongoDB Driver với `CommandStartedEvent` trong integration test. Kiểm tra:

- Stage đầu có `$match` tenant cho ORDER.
- Nhánh `$unionWith.pipeline` có `$match` tenant riêng cho REFUND.
- `$replaceRoot` dùng đúng `$mergeObjects` và đặt metadata cuối.
- `$project` của hai nhánh trả cùng field names.
- `$sort`/`$limit` nằm sau union.

Khi xem `explain("executionStats")`, so sánh index/độ trễ theo dữ liệu đại diện. Không nhầm việc test trả đúng vài document với chứng minh hiệu năng production.

## 20. Những lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
Cho rằng `$replaceRoot` chỉ thêm field con | Root cũ bị thay và metadata biến mất | Dùng `$mergeObjects` hoặc `$project` có chủ đích |
`newRoot` tham chiếu null/scalar | Aggregation có thể lỗi | Kiểm tra object type hoặc expression fallback hợp lệ |
Đặt metadata trước payload trong `$mergeObjects` | Payload có thể ghi đè tenant/source | Đặt metadata đáng tin cậy sau, rồi whitelist output |
Vẫn dùng `"$payload.amount_vnd"` sau replaceRoot | Field path không còn đúng | Dùng `"$amount_vnd"` sau khi nâng payload |
Nhầm `$unionWith` với `$lookup` | Sai shape: dòng nối thay vì array join | Chọn theo nhu cầu timeline hay quan hệ |
Cho rằng union tự khử duplicate | Tổng doanh thu có thể tính hai lần | Định nghĩa event ID và dedup khi nghiệp vụ yêu cầu |
Hai nhánh xuất tên tiền khác nhau | DTO thiếu field, group sai | Chuẩn hóa `netAmountVnd` ở cả hai |
Quên đổi dấu REFUND | Tổng ròng bị tăng thay vì giảm | Quy định sign convention và test |
Không lọc tenant ở nhánh union | Rò dữ liệu tenant khác | `$match` đáng tin cậy trong mỗi nhánh |
Đặt `$limit` trước union hoặc group tổng | Timeline/báo cáo sai phạm vi | Limit sau sort của toàn tập; không limit trước group doanh thu |
Tin thứ tự union là thứ tự kết quả | UI/test không ổn định | Sort cuối và tie-breaker |
Raw expression dùng tên property Java thay BSON | Field missing/null ngoài ý muốn | Kiểm tra `@Field` và command BSON |
Map output union vào entity gốc | Thiếu/nhầm field | Tạo DTO theo output schema |
Khử trùng theo `orderId` | Mất nhiều lần refund hợp lệ | Dedup theo event key có namespace |
Cho rằng `$unionWith` dùng được mọi transaction | Runtime không hỗ trợ | Kiểm tra version và hạn chế transaction/topology |
Chỉ test ORDER, không seed REFUND | Không phát hiện lỗi ở union branch | Integration test hai collection |
Không đo index/độ trễ từng nguồn | Pipeline chậm khi dữ liệu tăng | Explain, metrics, index từng collection |

## 21. Bài tập vận dụng

**Bài 1 — Thay root.** Tạo một `order_events` với `payload` object. Chạy `$replaceRoot: { newRoot: "$payload" }`, liệt kê field biến mất. Thử thiếu payload và giải thích vì sao cần kiểm tra kiểu.

**Bài 2 — Merge metadata.** Dùng `$mergeObjects` giữ `eventId`, `tenantId`, `source`. Cố tình thêm `tenantId: "tenant-b"` trong payload, xác minh metadata đáng tin cậy thắng nếu đứng cuối. Thêm `$project` whitelist.

**Bài 3 — Union hai schema.** Tạo 2 order và 1 refund. Chuẩn hóa từng nhánh về `eventId/source/orderId/netAmountVnd/occurredAt` rồi dùng `$unionWith`. Kiểm tra refund mang dấu âm.

**Bài 4 — Tenant isolation.** Thêm event ở tenant-b. Bỏ `$match` trong pipeline con của `$unionWith`, quan sát lỗi rò dữ liệu trong môi trường test, sau đó thêm lại filter và viết regression test.

**Bài 5 — UNION ALL và dedup.** Union collection ORDER với chính nó và xác minh mỗi event xuất hiện hai lần. Dùng `$group` theo (`source`, `eventId`) để loại duplicate và giải thích vai trò của `$first` cùng sort.

**Bài 6 — Báo cáo ròng.** Sau union, `$group` theo `orderId` để tính `netVnd` và `eventCount`. Kiểm tra ord-101 có net 110000, ord-102 có 60000; tuyệt đối không limit timeline trước group.

**Bài 7 — Spring Data.** Triển khai `AggregationOperation` raw BSON và `MongoTemplate.aggregate`; so sánh `AggregationResults<UnifiedEventDto>` với `AggregationResults<Document>`. Kiểm tra field output đã được whitelist.

**Bài 8 — Mapping @Field.** Đổi tên Java `amountVnd`, giữ BSON field `amount_vnd` bằng `@Field`. Viết test chứng minh raw aggregation dùng đúng tên BSON, không phải tên property Java.

**Bài 9 — Paging.** Tạo 1000 event ở mỗi nguồn; so sánh sort/limit sau union với limit trước union. Thử paging bằng offset khi có insert xen giữa, sau đó thiết kế keyset cursor theo (`occurredAt`, `source`, `eventId`).

**Bài 10 — Hiệu năng.** Tạo index tenant/time trên từng collection, chạy explain và benchmark pipeline trên dữ liệu lớn. Ghi docsExamined, keysExamined, CPU, memory và p95, xác định bottleneck ở filter, replaceRoot, union hay sort.

**Bài 11 — Tính đúng đắn dữ liệu.** Thử refund nhiều lần trên một đơn, amount null, sự kiện phát lại và nhiều loại tiền tệ. Định nghĩa rõ khi nào báo cáo phải thất bại hoặc loại/quarantine một event thay vì âm thầm trả tổng sai.

## 22. Ghi nhớ

**`$replaceRoot`** thay **toàn bộ document hiện tại** bằng một document mới; kết hợp `$mergeObjects` và `$project` giúp nâng object lồng lên root mà vẫn giữ metadata được tin cậy và chốt output schema. Cần kiểm tra kiểu object của `newRoot`, bảo vệ field bị trùng và sửa field paths theo schema sau mỗi stage.

**`$unionWith`** nối kết quả từ một collection/pipeline khác theo tinh thần **UNION ALL**: **không join theo khóa, không tự khử trùng, không bảo đảm thứ tự và không tự đồng nhất schema**. Mỗi nhánh phải được lọc tenant/authorization và chuẩn hóa tên field, kiểu dữ liệu, đơn vị, dấu tiền trước khi union. Muốn timeline đúng thì sort/limit ở sau union; muốn tổng hợp đúng thì group trên **toàn bộ các dòng** phù hợp.

Trong **Spring Data MongoDB**, có thể dùng `Aggregation`/`MongoTemplate.aggregate` với builder theo phiên bản hoặc `AggregationOperation` chứa BSON stage để triển khai và kiểm tra pipeline. Khi dùng raw `Document`, các tên field phải là **BSON vật lý**, không nên trông đợi Spring Data tự dịch mọi expression. Đặt DTO theo **output cuối cùng**, kiểm tra kết quả bằng MongoDB thật và theo dõi index, phiên bản, collation, giới hạn transaction, retry/idempotency ở đường ghi và bảo mật đa tenant trước khi đưa vào production.
