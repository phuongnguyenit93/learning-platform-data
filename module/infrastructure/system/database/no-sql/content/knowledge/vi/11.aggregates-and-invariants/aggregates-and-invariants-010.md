# Phát hiện, đối soát và sửa dữ liệu vi phạm quy tắc trong NoSQL

## 1. Vì sao dữ liệu ghi thành công vẫn có thể sai?

Một cơ sở dữ liệu NoSQL có thể xác nhận thao tác ghi thành công trong khi **quy tắc nghiệp vụ** vẫn bị vi phạm. Ví dụ, một document đơn hàng chứa đầy đủ các trường nhưng tổng tiền không khớp các dòng hàng; hai request đồng thời làm tồn kho âm; một sự kiện thanh toán được xử lý hai lần; một search index đang hiển thị tài liệu đã bị thu hồi quyền.

Xét document minh họa:

```json
{
  "_id": "ORD-1001",
  "customerId": "CUS-007",
  "status": "PAID",
  "items": [
    { "sku": "P10", "quantity": 2, "unitPriceVnd": 150000 },
    { "sku": "P20", "quantity": 1, "unitPriceVnd": 220000 }
  ],
  "totalVnd": 490000,
  "version": 4
}
```

Nếu không có giảm giá, thuế hoặc phí, tổng hai dòng hàng là **520.000 VND**, khác `totalVnd = 490000`. Document có thể hợp lệ về kiểu dữ liệu nhưng sai về **bất biến nghiệp vụ**. Tuy nhiên, nếu `totalVnd` đã bao gồm giảm giá hợp lệ 30.000 VND, phép so sánh đơn giản lại đưa ra cảnh báo giả. Vì vậy, trước khi tìm lỗi phải xác định chính xác **định nghĩa dữ liệu đúng**.

Bài học này tập trung vào ba việc liên kết chặt chẽ:

1. **Phát hiện (detect):** nhận ra record, quan hệ hoặc bản dẫn xuất có dấu hiệu vi phạm quy tắc.
2. **Đối soát (reconcile):** xác minh bằng nguồn có thẩm quyền, đúng phiên bản, đúng thời điểm và đúng chính sách.
3. **Sửa dữ liệu (repair):** phục hồi trạng thái đúng mà không ghi đè thay đổi mới, không xử lý trùng, không tạo vi phạm khác.

Quy trình tổng quát:

```text
Định nghĩa invariant và nguồn dữ liệu có thẩm quyền
                       |
                       v
         Online check / CDC / Batch scan
                       |
                       v
             Finding + bằng chứng
                       |
                       v
             Xác minh và phân loại
                 /           \
                v             v
      Sửa tự động an toàn   Cách ly / xử lý thủ công
                \             /
                 v           v
             Kiểm chứng kết quả
                       |
                       v
             Audit + khắc phục gốc
```

Các ví dụ sử dụng MongoDB, cache và read model để giải thích. Khái niệm áp dụng cả với key–value, document, wide-column, graph và các hệ NoSQL chuyên biệt, nhưng khả năng transaction, index, snapshot và nhất quán khác nhau theo hệ quản trị.

## 2. Bất biến là gì? Phải đúng ở phạm vi nào?

**Invariant (bất biến)** là một điều kiện mà trạng thái hệ thống cần thỏa mãn tại một ranh giới hoặc thời điểm xác định:

\[
I(S)=\text{true}
\]

Trong đó \(S\) là trạng thái liên quan, còn \(I\) là quy tắc. Ví dụ:

- Mỗi dòng đơn có số lượng mua dương.
- Mỗi mã SKU là duy nhất **trong một tenant**.
- Tổng tiền bằng tổng các dòng hàng cộng phí, thuế và trừ giảm giá theo chính sách áp dụng.
- Một đơn chỉ được chuyển trạng thái qua những bước hợp lệ.
- Không bán quá số lượng tồn kho được cấp phát.
- Một mã giao dịch thanh toán không được tạo tác động tài chính hai lần.
- Một projection chỉ được coi là đồng bộ sau khi bắt kịp phiên bản nguồn.

### Phạm vi kiểm soát

| Phạm vi | Ví dụ | Cơ chế thường dùng |
|---|---|---|
| Một trường | `quantity > 0` | Input validation, schema validation |
| Một document/aggregate | Tổng tiền đơn hàng, chuyển trạng thái đơn | Tính toán tại service, cập nhật nguyên tử có điều kiện |
| Nhiều document | SKU duy nhất, tham chiếu khách hàng | Unique index, kiểm tra vòng đời, transaction nếu cần |
| Nhiều collection/service | Đơn hàng khớp phân bổ tồn kho | Giao dịch có phạm vi thích hợp hoặc workflow điều phối |
| Event stream | Một sự kiện không bị cộng hai lần | Idempotency key, deduplication, thứ tự sự kiện |
| Read model/cache | Projection theo kịp dữ liệu nguồn | Version, CDC/outbox, reconciliation |
| Bảo mật | Không trả dữ liệu bị thu hồi quyền | Authorization ở đường đọc có thẩm quyền |

**Điều quan trọng:** NoSQL thường tối ưu theo nhóm dữ liệu được đọc/ghi cùng nhau. Khi bất biến nằm trong một document hoặc một key, thao tác nguyên tử ở phạm vi đó có thể đủ. Khi bất biến vượt qua nhiều document, shard hoặc service, cần thiết kế một giao thức nhất quán ở phạm vi rộng hơn; không nên suy ra rằng những thao tác riêng lẻ thành công sẽ tự tạo kết quả đúng toàn cục.

### Bất biến mạnh và nhất quán cuối cùng

Giả sử nguồn sản phẩm vừa được cập nhật lên `version=8` lúc 10:00:00, search index đang ở `version=7` lúc 10:00:02. Nếu dịch vụ quy định index được phép chậm tối đa 10 giây, đây có thể chỉ là **trạng thái đang hội tụ**, chưa phải lỗi.

Nhưng nếu 10:30 vẫn ở v7, hệ thống cần phát hiện và sửa. Ngược lại, với giá chốt đơn, số dư hoặc quyền truy cập vừa bị thu hồi, nhiều nghiệp vụ **không thể** chấp nhận 10 giây sai lệch tại thời điểm quyết định. Các thao tác đó phải tham chiếu nguồn/cơ chế có thẩm quyền, không phụ thuộc vào projection có thể trễ.

Trước khi triển khai detector, cần trả lời rõ:

- Quy tắc áp dụng cho đơn vị dữ liệu nào?
- Ai sở hữu giá trị đúng? Bản nào chỉ là dữ liệu dẫn xuất?
- Quy tắc phải đúng ngay tại commit hay chỉ sau một khoảng hội tụ?
- Sự khác biệt nào được phép do trạng thái lịch sử?
- Có đủ bằng chứng để sửa tự động không, hay cần phê duyệt?

## 3. Các lớp vi phạm dữ liệu thường gặp

| Loại | Dấu hiệu | Nguyên nhân thường thấy | Rủi ro |
|---|---|---|---|
| Sai kiểu/cấu trúc | Thiếu `customerId`, giá lưu dưới dạng chuỗi | Legacy import, thiếu validation | Lỗi xử lý và lọc |
| Sai quan hệ giữa các trường | `totalVnd` không khớp giá dòng hàng | Logic tính tiền lệch, cập nhật một phần | Sai giao dịch và báo cáo |
| Trùng định danh logic | Hai document có cùng `tenantId + sku` | Race, thiếu unique constraint | Truy xuất mơ hồ |
| Mồ côi tham chiếu | `order.customerId` không còn customer | Xóa không kiểm soát | Mất quan hệ |
| Chuyển trạng thái sai | `PAID` quay lại `PENDING` | Ghi đè event cũ | Quy trình lệch |
| Xử lý event trùng | Một giao dịch cộng doanh thu hai lần | Retry, at-least-once delivery | Sai số liệu |
| Projection chậm/hỏng | Source v8, index v7 quá lâu | Consumer kẹt, bỏ sót event | Đọc dữ liệu cũ |
| Xóa không lan truyền | Search trả tài liệu đã xóa/thu hồi | Cache/index còn bản cũ | Rủi ro bảo mật |
| Invariant xuyên dữ liệu | Tồn kho âm sau hai đơn cạnh tranh | Check-then-write không nguyên tử | Bán vượt hàng |

Một phát hiện có thể có nhiều lời giải thích. **Detector nên báo nghi vấn có bằng chứng; không nên tự đoán nguyên nhân rồi ghi đè dữ liệu.**

## 4. Ví dụ nguồn dữ liệu và bản phục vụ đọc

Giả sử một hệ bán hàng có:

- `orders` trong MongoDB: nguồn có thẩm quyền về trạng thái, dòng hàng và tổng tiền.
- `customers` trong MongoDB: hồ sơ khách hàng hiện hành.
- `order_search`: read model phục vụ tìm kiếm nhanh, lưu `sourceVersion`.
- Một luồng event để lan truyền thay đổi đơn hàng tới read model và báo cáo.

Document nguồn:

```javascript
{
  _id: "ORD-1001",
  customerId: "CUS-007",
  status: "PAID",
  items: [
    { sku: "P10", quantity: 2, unitPriceVnd: 150000 },
    { sku: "P20", quantity: 1, unitPriceVnd: 220000 }
  ],
  totalVnd: 490000,
  version: 4,
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
```

Read model:

```javascript
{
  _id: "ORD-1001",
  customerId: "CUS-007",
  status: "PENDING",
  totalVnd: 490000,
  sourceVersion: 3,
  projectedAt: ISODate("2026-11-14T07:58:00Z")
}
```

Có hai nghi vấn **độc lập**: tổng tiền của nguồn có thể sai và trạng thái của projection đã lạc hậu. Đối soát mỗi nghi vấn phải dùng quy tắc khác nhau. Nếu projection sai nhưng source đúng, có thể tái tạo projection. Nếu source tự mâu thuẫn, không được mặc nhiên lấy projection để “sửa” source.

## 5. Phòng ngừa từ lúc ghi

### 5.1. Input validation và business validation

Một lệnh tạo đơn nên được kiểm tra tại service:

```text
createOrder(command):
    require customerId is valid and authorized
    require items is nonempty
    for each line in items:
        require line.quantity > 0
        require line.unitPriceVnd >= 0
        require line.sku is valid for this order

    price = authoritativePricingPolicy(...)
    calculatedTotal = price.calculate(items, discounts, taxes, fees)
    require calculatedTotal fits supported numeric range

    write validated order
```

Nếu cần chính xác tiền tệ, thống nhất kiểu số nguyên trong đơn vị nhỏ nhất hoặc decimal có kiểm soát độ chính xác. Đừng để client tự gửi `totalVnd` rồi ghi thẳng vào nguồn.

### 5.2. Schema validation trong MongoDB

```javascript
db.createCollection("orders_demo", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["customerId", "status", "items", "totalVnd", "version"],
      properties: {
        customerId: { bsonType: "string" },
        status: { enum: ["PENDING", "PAID", "CANCELLED"] },
        items: { bsonType: "array", minItems: 1 },
        totalVnd: { bsonType: ["int", "long"] },
        version: { bsonType: ["int", "long"] }
      }
    }
  },
  validationAction: "error"
});
```

Validator bảo vệ các trường và kiểu cơ bản; nó **chưa tự chứng minh** tính đúng của tổng tiền, quyền sở hữu, vòng đời trạng thái hay tham chiếu khách hàng. Cần phối hợp với quy tắc nghiệp vụ.

### 5.3. Unique index cho định danh logic

```javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);
```

Đây là cách ngăn trùng `(tenantId, sku)` khi phạm vi và quy tắc dữ liệu phù hợp. Trước khi tạo index trên dữ liệu legacy phải xử lý bản trùng; cần xác định hành vi của trường thiếu/null, kiểu và collation nếu chúng ảnh hưởng tính duy nhất.

### 5.4. Cập nhật có điều kiện

```javascript
db.orders.updateOne(
  { _id: "ORD-1002", status: "PENDING", version: 3 },
  {
    $set: { status: "PAID", paidAt: new Date() },
    $inc: { version: 1 }
  }
);
```

Trong MongoDB, bộ lọc và phép cập nhật trên **một document** được thực hiện nguyên tử. Nếu `matchedCount = 0`, có thể đơn đã chuyển trạng thái, version thay đổi hoặc không tồn tại; không được coi là thành công vô điều kiện.

Những cách phòng ngừa này làm giảm dữ liệu sai mới phát sinh nhưng **không chữa được** record cũ, projection lệch, event bị bỏ sót hoặc sai khác giữa nhiều service.

## 6. Ba con đường phát hiện: trực tuyến, theo event và quét định kỳ

### Kiểm tra trực tuyến (online)

Trước hoặc trong thao tác ghi, hệ thống kiểm tra invariant có thể bảo vệ tại thời điểm commit. Ví dụ thao tác trừ kho có điều kiện “chỉ trừ nếu availableQuantity >= số yêu cầu”, thay vì đọc số lượng rồi kiểm tra ở ứng dụng trước khi ghi không điều kiện.

### Kiểm tra theo sự kiện (change-driven)

Sau mỗi thay đổi đã commit, một CDC consumer hoặc outbox consumer kiểm tra các trường liên quan. Cách này rút ngắn thời gian phát hiện và giới hạn số bản ghi phải kiểm tra.

### Quét/đối soát định kỳ (batch)

Một job quét theo tenant, khoảng thời gian hoặc dải ID tìm lỗi đã tồn tại từ trước, event bị mất hoặc hành vi mà online validation chưa bao phủ.

```text
API + online guard --> NoSQL source
                           |        |
                           v        v
                         CDC      Batch scan
                           \       /
                            v     v
                       Rule detectors
                            |
                            v
                    Finding repository
                            |
                            v
                      Triage/Repair
```

Ba cách bổ sung chứ không thay thế nhau. Một consumer có thể bỏ sót event do lỗi cấu hình; một batch job có thể chậm hàng giờ; một phép kiểm tra trực tuyến không nhất thiết biết mọi lỗi phát sinh do dữ liệu hệ khác.

## 7. Truy vấn phát hiện dữ liệu nghi vấn trong MongoDB

Các lệnh dưới đây **chỉ đọc dữ liệu**, phù hợp để minh họa detector. Trên production cần xem tải, chỉ mục và cách quét batch trước khi chạy trên tập lớn.

### 7.1. Trường bắt buộc bị thiếu

```javascript
db.orders.find({
  $or: [
    { customerId: { $exists: false } },
    { status: { $exists: false } },
    { items: { $exists: false } },
    { totalVnd: { $exists: false } }
  ]
});
```

`$exists: false` tìm trường không tồn tại; trường có giá trị `null` là một tình huống khác, cần quy tắc riêng. Không được coi sự tồn tại của trường là bằng chứng giá trị hợp lệ.

### 7.2. Dòng hàng có số lượng hoặc giá không hợp lệ

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      $or: [
        { quantity: { $lte: 0 } },
        { unitPriceVnd: { $lt: 0 } }
      ]
    }
  }
});
```

Ví dụ giả định nghiệp vụ đơn hàng bán mới không cho phép số lượng bằng 0 hoặc giá âm. Detector riêng cần phát hiện kiểu sai, trường thiếu và các trường hợp hoàn tiền được biểu diễn theo mô hình khác. Không áp cứng quy tắc này lên mọi record tài chính.

### 7.3. Tổng tiền không khớp tổng dòng

Giả định `items` là mảng hợp lệ, `quantity`/`unitPriceVnd` là số, và tổng tiền **không có phí, giảm giá hoặc thuế**:

```javascript
db.orders.aggregate([
  {
    $match: {
      items: { $type: "array" },
      totalVnd: { $type: "number" }
    }
  },
  {
    $set: {
      calculatedTotalVnd: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPriceVnd"
              ]
            }
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$totalVnd", "$calculatedTotalVnd"] }
    }
  },
  {
    $project: {
      _id: 1,
      version: 1,
      totalVnd: 1,
      calculatedTotalVnd: 1
    }
  }
]);
```

Trên dữ liệu mẫu, phép tính ra 520.000 VND trong khi trường đã lưu là 490.000 VND. Pipeline trên chỉ tạo **báo cáo nghi vấn**. Nếu có các item sai kiểu hoặc thiếu field, phép toán có thể lỗi; nên tách kiểm tra schema trước. Với đơn thực tế, dùng công thức và phiên bản chính sách tính tiền đúng thời điểm giao dịch; không tự sửa giá trị chỉ dựa vào pipeline giản lược.

### 7.4. Phát hiện khóa nghiệp vụ trùng

```javascript
db.products.aggregate([
  {
    $match: {
      tenantId: { $exists: true },
      sku: { $exists: true }
    }
  },
  {
    $group: {
      _id: { tenantId: "$tenantId", sku: "$sku" },
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
```

Truy vấn giúp nhận diện các nhóm trùng trong dữ liệu cũ trước khi tạo unique index. Ở tập lớn, `$push` toàn bộ ID của một nhóm có thể tốn bộ nhớ; có thể quét theo tenant hoặc tạo báo cáo số lượng trước rồi điều tra từng nhóm. **Không xóa ngẫu nhiên một record** vì các bản trùng có thể đang được tham chiếu từ nhiều nơi.

### 7.5. Tìm tham chiếu mồ côi

```javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "matchedCustomers"
    }
  },
  { $match: { matchedCustomers: { $size: 0 } } },
  { $project: { _id: 1, customerId: 1, status: 1, version: 1 } }
]);
```

Nếu không còn customer trùng ID, đây là **ứng viên orphan reference**. Nhưng có thể hồ sơ khách đã được xóa theo chính sách bảo vệ dữ liệu mà đơn vẫn phải giữ ID lịch sử. Phải xác minh ý nghĩa trước khi sửa. `$lookup` toàn tập trên production có thể đắt; nên áp dụng phạm vi, index hoặc phương án đối chiếu batch phù hợp.

### 7.6. Phát hiện chuyển trạng thái trái phép cần lịch sử

Một document hiện đang `PENDING` không cho biết nó từng được thanh toán hay chưa. Cần event log hoặc nhật ký chuyển trạng thái đủ tin cậy:

```text
10:00  CREATED            -> PENDING
10:05  PAYMENT_CONFIRMED  -> PAID
10:06  UPDATE_STATUS      -> PENDING  // cần điều tra
```

Đây là **bất biến theo thời gian**. Không thể suy ra lịch sử từ trạng thái cuối cùng nếu không có bằng chứng. Khi thiếu log, cần báo giới hạn xác minh chứ không tạo sự kiện giả để “hoàn chỉnh” dữ liệu.

## 8. Đối soát nguồn có thẩm quyền và read model

Nếu `orders` là nguồn còn `order_search` là projection, dữ liệu tìm kiếm cần phản ánh những trường nguồn theo chính sách, nhưng có thể chậm trong một cửa sổ cho phép.

Một truy vấn đối chiếu minh họa:

```javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "order_search",
      localField: "_id",
      foreignField: "_id",
      as: "searchMatches"
    }
  },
  {
    $set: {
      searchDoc: { $arrayElemAt: ["$searchMatches", 0] }
    }
  },
  {
    $project: {
      _id: 1,
      sourceVersion: "$version",
      searchVersion: "$searchDoc.sourceVersion",
      sourceStatus: "$status",
      searchStatus: "$searchDoc.status",
      updatedAt: 1
    }
  }
]);
```

Các trạng thái đáng phân biệt:

| Quan sát | Có thể có ý nghĩa gì? |
|---|---|
| Không có projection | Chưa index, event lỗi, hoặc record cố ý không hiển thị |
| Search version thấp hơn source | Đang hội tụ hoặc consumer bị kẹt |
| Hai version bằng nhau nhưng trường khác | Mapper sai, event thiếu dữ liệu, ghi không nguyên khối |
| Search version cao hơn source | Có thể đọc nguồn replica trễ, restore lệch mốc, ID/version không nhất quán |

**Không nên suy ra projection là “đúng hơn” chỉ vì version cao hơn trong một lần so sánh.** Detector đang đọc hai nguồn tại các thời điểm khác nhau, có thể không phải snapshot nhất quán.

### Đối soát nội dung bằng checksum

Chỉ so version có thể bỏ sót một projection ghi đúng version nhưng sai dữ liệu. Có thể chuẩn hóa các trường quan trọng rồi tính checksum:

```text
canonical = normalize(
    orderId, customerId, status, totalVnd, version
)
digest = hash(canonical)
```

Cần chuẩn hóa cùng quy tắc: thứ tự trường, kiểu số và đơn vị tiền, thời gian/múi giờ, phân biệt null và thiếu, thứ tự mảng khi có ý nghĩa, và phiên bản transform. Nếu projection cố tình bỏ bớt hoặc đổi cấu trúc trường, checksum phải áp dụng trên **cùng ý nghĩa**, không so hai object nguyên vẹn khác schema.

### Đối soát số liệu tổng hợp

Một dashboard doanh thu theo ngày cần dùng cùng cách chọn:

- Múi giờ và khoảng thời gian.
- Trạng thái đơn nào được tính.
- Chính sách hoàn tiền và hủy đơn.
- Thuế, phí, chiết khấu và tiền tệ.
- Watermark đối với event đến muộn.

Dashboard tính đến 10:00 và nguồn được quét đến 10:05 khác nhau chưa chắc là lỗi. So sánh phải có cùng **điểm cắt** hoặc quy tắc hiệu chỉnh độ trễ.

## 9. Tránh cảnh báo giả do hệ đang cập nhật

Giả sử detector đọc nguồn lúc 10:00:00 ở version 7. Writer commit version 8 lúc 10:00:01. Projector áp dụng v8 lúc 10:00:02. Detector đọc projection lúc 10:00:03 và thấy v8. Hai kết quả khác version nhưng là hai **quan sát khác thời điểm**, không phải bằng chứng source sai.

Các biện pháp:

1. Dùng version, event sequence, checkpoint hoặc watermark để xác định mốc so sánh.
2. Đưa nghi vấn “projection chậm” vào trạng thái `IN_FLIGHT` trước khi vượt ngưỡng.
3. Sau grace period, đọc lại nguồn và projection để xác nhận.
4. Dùng snapshot/điểm cắt nhất quán nếu datastore và yêu cầu hỗ trợ.
5. Không sửa ngay chỉ vì một phép đọc hai nơi khác giá trị.

Ví dụ quy tắc minh họa:

```text
if source.version > projection.version:
    if source.updatedAt is within allowedLag:
        classification = IN_FLIGHT
    else:
        classification = LAG_VIOLATION
```

Timestamp giữa các máy có thể lệch; với hệ phân tán phức tạp, cần kết hợp thời gian với watermark và cách nguồn phát event. Ngược lại, nếu rủi ro là lộ dữ liệu do quyền đã bị thu hồi, **không thể** cho phép đường trả nội dung vi phạm quyền trong lúc chờ projection hội tụ.

## 10. Quét dữ liệu lớn theo batch và checkpoint

Job đối soát không nên nạp toàn bộ collection vào RAM hoặc phân trang sâu bằng `skip`. Một chiến lược là quét theo tenant và dải ID:

```text
checkpoint = loadCheckpoint(jobId, tenantId)
batchSize = 500

loop:
    docs = readSource(
        tenantId = tenantId,
        idGreaterThan = checkpoint.lastId,
        orderByIdAscending = true,
        limit = batchSize
    )

    if docs is empty:
        stop

    for doc in docs:
        evaluateRules(doc)
        upsertFindingIfNeeded(doc)

    persistCheckpoint(docs.last.id)
```

Ví dụ truy vấn MongoDB tương đương cho một dải ID:

```javascript
db.orders
  .find({ _id: { $gt: lastId } })
  .sort({ _id: 1 })
  .limit(500);
```

Nếu có tenant, đưa `tenantId` vào điều kiện và chọn chỉ mục thích hợp. Cần biết kiểu ID, thứ tự so sánh và cách phục hồi checkpoint. Một lỗ hổng quan trọng: document đã quét xong vẫn có thể bị cập nhật sau đó và job không quay lại trong lượt hiện tại. Vì vậy cần **quét định kỳ kết hợp CDC hoặc quét chồng lấn**, không xem checkpoint ID đơn thuần là đảm bảo phát hiện mọi thay đổi.

Trên cluster, việc quét phải hạn chế tải, phân vùng công việc, retry có backoff, tránh gây ảnh hưởng đến request giao dịch. Có thể ưu tiên các dải mới thay đổi và lịch sử vi phạm, nhưng vẫn cần một cơ chế độc lập kiểm tra dữ liệu ít thay đổi.

## 11. Lưu finding và phân loại mức độ

Detector nên ghi một **finding** có bằng chứng, thay vì chỉ in log:

```json
{
  "findingId": "order-total:ORD-1001:v4",
  "ruleId": "ORDER_TOTAL_MATCHES_ITEMS",
  "entityType": "Order",
  "entityId": "ORD-1001",
  "observedVersion": 4,
  "severity": "HIGH",
  "detectedAt": "2026-11-14T08:10:00Z",
  "evidence": {
    "storedTotalVnd": 490000,
    "calculatedTotalVnd": 520000
  },
  "state": "OPEN"
}
```

`findingId` nên ổn định để job retry không tạo hàng nghìn record trùng. Các trường cần thiết: rule/version, ID thực thể, phiên bản dữ liệu đã quan sát, mức độ, thời điểm, bằng chứng tối thiểu, trạng thái điều tra, người chịu trách nhiệm và kết quả sửa.

Một workflow:

```text
OPEN -> INVESTIGATING -> REPAIRING -> VERIFYING -> RESOLVED
          |
          +--> FALSE_POSITIVE
          |
          +--> QUARANTINED -> MANUAL_REVIEW
```

| Mức | Tình huống | Hướng ưu tiên |
|---|---|---|
| Critical | Vi phạm quyền, thanh toán trùng có hậu quả tài chính | Chặn rủi ro ngay tại nguồn/đường đọc, cảnh báo |
| High | Đơn đã thanh toán có số tiền bất thường | Cách ly và đối chiếu chứng từ |
| Medium | Projection lâu không cập nhật | Replay/reindex có version guard |
| Low | Cache tên cũ trong thời gian cho phép | Theo dõi hoặc invalidation theo SLA |

Không nên xếp hạng chỉ theo số record: một lần lộ quyền truy cập có thể nghiêm trọng hơn nhiều bản cache trễ vài giây.

## 12. Chọn cách sửa theo nguồn có thẩm quyền

### Trường hợp A — Projection sai, nguồn đúng

Nếu `order_search` có version 3 còn `orders` hiện version 4, có thể:

1. Đọc lại document nguồn.
2. Biến đổi thành schema projection.
3. Upsert projection có điều kiện chỉ khi incoming version mới hơn.
4. Kiểm tra lại version và các trường quan trọng.
5. Đóng finding sau khi đã xác minh.

Đây là tình huống thường có thể **tự động replay hoặc rebuild** nếu đủ thông tin và mapper đáng tin cậy.

### Trường hợp B — Document nguồn tự mâu thuẫn

Với `totalVnd` không khớp `items`, có thể item bị sửa sai, tổng tiền đã trừ giảm giá hoặc dữ liệu lịch sử có quy tắc khác. Nếu đơn đã chốt tài chính, **không tự động ghi lại total** khi chưa xác nhận. Có thể cần đối soát payment event, invoice và chính sách giá tại thời điểm mua; trong nhiều hệ kế toán, sửa chữa đúng là tạo bản điều chỉnh/bút toán bù trừ chứ không thay dữ liệu lịch sử.

### Trường hợp C — Tham chiếu mồ côi

Trước khi tạo khách hàng mới hoặc xóa đơn, phải xem khách đã bị xóa theo chính sách hay thiếu do đồng bộ. Có thể giữ ID lịch sử, snapshot ẩn danh, khôi phục từ nguồn có thẩm quyền hoặc đưa vào xử lý thủ công. **Tự tạo một customer giả để nối đủ quan hệ có thể làm sai quyền sở hữu.**

### Trường hợp D — Khóa nghiệp vụ trùng

Xác minh vì sao trùng: lỗi nhập liệu, ID không duy nhất theo đúng phạm vi, hay race. Trước khi hợp nhất hoặc xóa record, kiểm tra mọi tham chiếu và lịch sử. Sau khi làm sạch, tạo ràng buộc để lỗi không tái phát.

### Trường hợp E — Bộ đếm và tổng hợp lệch

Nếu có event log đầy đủ và định danh sự kiện ổn định, có thể tính lại tổng từ log, deduplicate theo event ID rồi thay projection tại checkpoint đúng. Nếu log mất dữ liệu hoặc không xác định được giao dịch trùng, không tuyên bố chắc chắn rằng tổng tính lại là đúng tuyệt đối.

## 13. Sửa có điều kiện: không ghi đè thay đổi mới

Job phát hiện lỗi khi document ở version 4. Trước khi sửa, một request hợp lệ có thể cập nhật lên version 5. Nếu job ghi vô điều kiện từ trạng thái cũ, nó sẽ **làm mất cập nhật hợp lệ**.

Ví dụ sửa một trường đơn giản **sau khi đã xác minh là được phép**, chỉ khi đơn còn ở version mong đợi:

```javascript
const result = db.orders.updateOne(
  {
    _id: "ORD-1002",
    version: 4,
    status: "PENDING"
  },
  {
    $set: {
      customerNote: "Đã xác minh địa chỉ giao hàng"
    },
    $inc: { version: 1 }
  }
);

printjson(result);
```

Nếu `matchedCount = 0`, không được bỏ điều kiện version để ép ghi. Phải đọc lại record mới nhất và kiểm tra invariant một lần nữa. Phép **compare-and-set** cần diễn ra trong chính thao tác nguyên tử hoặc transaction tương đương, không chỉ bằng một lần đọc trước khi sửa.

Ví dụ trên không sửa tổng tiền của đơn đã thanh toán. Những sửa đổi tài chính phải theo workflow riêng và quy tắc nghiệp vụ được phê duyệt.

### Sửa nhiều document

Một `updateOne` trên MongoDB không tạo giao dịch xuyên hai document. Nếu cần cập nhật đơn và tồn kho cùng nhau, phải chọn transaction trên topology được hỗ trợ hoặc workflow có xử lý bù trừ phù hợp; cũng phải xử lý lỗi commit, retry và idempotency. Ghi thành công vào MongoDB rồi ghi tiếp Redis/search index **không** trở thành transaction ACID xuyên ba hệ.

## 14. Chặn sự kiện cũ ghi đè read model mới

Giả sử projection đang ở version 9, nhưng job backfill từ snapshot cũ gửi lại version 8. Nếu ghi đè vô điều kiện, read model sẽ lùi.

Với **full-state projection**, hành vi mong muốn:

```text
apply(event):
    current = projection.get(event.entityId)

    if current exists and current.sourceVersion >= event.version:
        return NO_OP

    projection.conditionalUpsert(
        entityId = event.entityId,
        data = transform(event.fullState),
        sourceVersion = event.version,
        onlyIfStoredVersionIsLower = true
    )
```

Đây là **pseudocode**; không phải lệnh chung của mọi NoSQL store. Đặc biệt, đọc version rồi ghi ở hai request độc lập **không đủ an toàn với nhiều worker đồng thời**; điều kiện kiểm tra và ghi phải có tính nguyên tử hoặc được điều phối bởi một writer theo thực thể.

Nếu event chỉ là **delta** (chẳng hạn “tăng 1”), bỏ qua event đến muộn hoặc thiếu giữa hai version có thể làm tổng sai. Khi đó phải xử lý thứ tự, phát hiện gap, replay đầy đủ/deduplicate hoặc xây lại từ log nguồn. Không áp dụng cùng logic cho full-state và delta.

### Tombstone khi xóa

Nếu version 10 đã xóa sản phẩm, còn event cập nhật v9 đến muộn, một projector ngây thơ có thể tạo lại sản phẩm đã xóa. **Tombstone** lưu ID và version xóa giúp từ chối event cũ. Phải xác định thời gian giữ tombstone, khả năng tái sử dụng ID và chính sách xóa dữ liệu ở các bản lưu/cache.

## 15. Repair idempotent, audit và quarantine

Một repair job có thể bị crash sau khi ghi sửa nhưng trước khi đánh dấu hoàn tất. Vì thế, chạy lại cùng repair không được tạo tác động sai thêm.

Quy trình:

```text
1. Claim finding bằng lease / worker ID
2. Đọc lại nguồn và xác nhận version hiện hành
3. Xác minh invariant và quyền được phép sửa
4. Ghi có điều kiện + idempotency key
5. Đọc lại kiểm chứng
6. Lưu repair audit và đóng finding
7. Nếu không thành công: retry có backoff hoặc escalate
```

**Lease không tự thay thế fencing/version guard.** Worker cũ có thể tiếp tục sau khi lease hết hạn và worker mới đã nhận việc. Một repair an toàn phải ngăn worker cũ ghi vào trạng thái mới.

Ví dụ audit record:

```json
{
  "repairId": "repair:ORD-1001:TOTAL:v4",
  "findingId": "order-total:ORD-1001:v4",
  "entityId": "ORD-1001",
  "observedVersion": 4,
  "action": "ESCALATED_FOR_FINANCIAL_REVIEW",
  "actor": "reconciliation-worker",
  "outcome": "REQUIRES_MANUAL_APPROVAL"
}
```

Không ghi toàn bộ dữ liệu cá nhân hoặc bí mật vào metric/log rộng quyền. Audit nên lưu ID, field thay đổi, version, sự kiện, người thực hiện và bằng chứng tối thiểu có phân quyền.

### Khi nào cách ly dữ liệu?

**Quarantine** phù hợp khi tự sửa có thể gây hậu quả:

- Đơn có tổng tiền bất thường: dừng hoàn tiền/xuất chứng từ tự động cho đơn cần điều tra.
- Giao dịch thanh toán trùng: chặn tác động tài chính thêm lần nữa.
- Bản ACL mâu thuẫn: chặn đường trả nội dung không đủ tin cậy.
- Hai record trùng SKU có nhiều tham chiếu: tránh tự xóa gây mồ côi.

Quarantine cần lý do, người chịu trách nhiệm, thời hạn xử lý và cách mở lại. Không nên âm thầm làm mất record khỏi mọi giao diện khiến hệ ngoài retry vô hạn.

### Dry run và kill switch

Trước khi bật auto-repair trên production:

- Chạy **dry-run** để thấy số record dự kiến sẽ sửa.
- Giới hạn theo tenant, loại rule, phiên bản hoặc danh sách ID.
- Có ngưỡng nếu finding tăng đột biến để dừng sửa.
- Throttle để không gây quá tải trên cluster.
- Có phương án rollback/bù trừ và audit cho hành động không đảo được.
- Chỉ tự sửa nguồn khi quy tắc được xác nhận đủ chắc chắn.

Rebuild một projection từ nguồn đúng có rủi ro khác hẳn sửa dữ liệu tài chính hoặc quyền sở hữu tại nguồn.

## 16. Khắc phục nguyên nhân gốc để lỗi không tái diễn

| Nguyên nhân | Biện pháp phòng ngừa |
|---|---|
| API chấp nhận giá trị sai | Validation tại API/database |
| Hai worker ghi cùng một aggregate | Conditional update, optimistic concurrency hoặc transaction |
| Cập nhật nhiều đơn vị dữ liệu không nguyên tử | Điều chỉnh ranh giới aggregate, transaction/workflow phù hợp |
| Thiếu unique index | Làm sạch dữ liệu rồi thêm constraint |
| Consumer xử lý trùng | Event ID, deduplication và ghi idempotent |
| Event đến sai thứ tự | Version guard, ordering per entity, gap handling |
| Dual-write nguồn và search | Outbox hoặc CDC có retry và giám sát |
| Cache nạp lại bản cũ sau invalidation | Versioned cache, CAS/fallback theo yêu cầu |
| Đổi schema projection bị thiếu record | Backfill + CDC + checkpoint và đối soát |
| Detector dùng công thức nghiệp vụ lỗi thời | Version rule và chính sách lịch sử |

Sau mỗi lỗi nghiêm trọng, bổ sung **kiểm thử tái hiện**: ghi cạnh tranh gây tồn kho âm, event v8/v9 đảo thứ tự, consumer crash và retry, record xóa bị hồi sinh, hay phép tính tiền qua nhiều phiên bản chính sách.

## 17. Monitoring chất lượng dữ liệu và việc sửa

Đo cả **số lỗi, độ tuổi, tần suất và kết quả sửa**:

| Chỉ số | Ý nghĩa |
|---|---|
| `invariant_violations_total` theo rule | Số lần phát hiện vi phạm |
| `open_findings_count` theo severity | Số nghi vấn chưa đóng |
| `oldest_finding_age_seconds` | Finding tồn tại lâu nhất |
| `reconciliation_scan_lag_seconds` | Độ trễ job so với lịch |
| `source_projection_version_gap` | Chênh lệch version |
| `auto_repair_success_rate` | Tỷ lệ sửa tự động được xác nhận |
| `repair_conflict_total` | Số sửa bị từ chối do version đã đổi |
| `quarantined_records_count` | Bản ghi cần xử lý thủ công |
| `false_positive_rate` | Tỷ lệ finding không phải lỗi thật |
| `reopened_findings_total` | Vi phạm tái xuất hiện sau khi đóng |

Không đưa từng `orderId` hay `customerId` làm label metric vì cardinality lớn và rủi ro lộ dữ liệu; chi tiết được lưu trong finding/audit store.

SLO minh họa cho projection: **99% thay đổi xuất hiện trong 10 giây và mọi chênh lệch kéo dài hơn 60 giây phải được cảnh báo**. Đây không phải chuẩn chung của NoSQL; mức thực tế tùy dữ liệu và rủi ro. Với quyền truy cập hay giao dịch tài chính, dùng một cơ chế chặn và kiểm tra mạnh hơn tại đường quyết định.

## 18. Quy trình đối soát hoàn chỉnh cho hệ đơn hàng

Hệ thống có `orders` làm nguồn, `order_search` làm projection, event stream có version theo đơn. Quy trình:

**Bước 1 — Định nghĩa rule.** Mỗi dòng hàng hợp lệ; tổng tiền theo pricing policy đúng phiên bản; trạng thái chuyển hợp lệ; projection bắt kịp nguồn trong ngưỡng.

**Bước 2 — Phòng ngừa.** API kiểm tra dữ liệu, sử dụng một thao tác ghi nguyên tử trong aggregate khi có thể; ràng buộc ID duy nhất và version.

**Bước 3 — Phát hiện.** Online guard khi ghi, consumer kiểm tra sau event, job scan theo tenant/ID định kỳ để tìm lỗi bị bỏ sót.

**Bước 4 — Lưu finding.** Kèm rule ID, entity ID, version, bằng chứng, mức độ và thời gian; không tạo trùng khi scan lại.

**Bước 5 — Xác minh.** Đọc lại nguồn, xét chính sách lịch sử, grace period và event log. Đừng coi chênh lệch tạm thời là lỗi thực.

**Bước 6 — Quyết định sửa.** Projection trễ có thể reindex từ nguồn. Đơn đã thanh toán sai tiền phải chuyển xem xét chứng từ và bút toán điều chỉnh; không tự ghi đè.

**Bước 7 — Ghi an toàn.** CAS/transaction, idempotency, version guard; nếu version nguồn đổi từ lúc phát hiện, quay lại xác minh.

**Bước 8 — Kiểm chứng.** Đọc lại nguồn và projection theo hợp đồng nhất quán; chỉ đóng finding khi đạt điều kiện và lưu audit.

**Bước 9 — Ngăn tái phát.** Sửa mã nguồn, validation, mapper hoặc quy trình event; bổ sung test tải cạnh tranh và giám sát.

## 19. Bài tập ứng dụng

### Bài 1 — Phân loại invariant

Cho năm quy tắc: SKU duy nhất trong tenant; item quantity dương; tổng tiền đúng; search index đồng bộ trong 15 giây; không trả tài liệu đã thu hồi quyền. Hãy phân loại theo phạm vi và chỉ ra quy tắc nào có thể eventual, quy tắc nào phải được bảo vệ mạnh tại đường ghi/đọc.

### Bài 2 — Tìm sai tổng tiền

| Đơn | Dòng hàng | totalVnd |
|---|---|---:|
| O1 | 2 × 100.000, 1 × 50.000 | 250.000 |
| O2 | 1 × 100.000, 3 × 50.000 | 200.000 |
| O3 | 1 × 70.000 | 70.000 |

Giả định không có phí và giảm giá, đơn nào sai? Nếu O2 đã thanh toán, có nên tự động sửa ngay `totalVnd` không? Cần xem những bằng chứng nào?

### Bài 3 — Độ trễ hợp lệ hay lỗi?

Source lên v12 lúc 10:00:00; projection v11 lúc 10:00:05, ngưỡng trễ cho phép 10 giây. Đến 10:03:00 vẫn v11. Thiết kế trạng thái finding từ `IN_FLIGHT` đến `LAG_VIOLATION` và quy tắc xác minh lại.

### Bài 4 — Repair bị xung đột

Job phát hiện lỗi ở version 4; khi sửa, document đã lên v5. Hãy viết bộ lọc `updateOne` có `version: 4` và giải thích cách xử lý `matchedCount = 0`.

### Bài 5 — Event đảo thứ tự

Projection đang v9, worker nhận event full-state v8, worker khác sắp áp v10. Hãy mô tả cơ chế atomic conditional upsert. Nếu event chỉ là “tăng counter”, cách xử lý có khác không?

### Bài 6 — Bộ đếm sai do retry

Dashboard ghi 1.002 lần thanh toán nhưng log nguồn chứa 1.000 giao dịch duy nhất. Hãy đề xuất đối soát theo event ID, watermark và chính sách hoàn tiền; làm sao replay mà không cộng trùng?

### Bài 7 — Xóa và thu hồi quyền

Một tài liệu nội bộ bị thu hồi quyền xem của nhóm `support` nhưng search index cập nhật trễ. Hãy giải thích cơ chế chặn tại nguồn có thẩm quyền, tombstone/ACL đồng bộ và cách kiểm chứng mọi đường đọc nội dung.

## 20. Kết luận

Trong NoSQL, **phát hiện, đối soát và sửa dữ liệu vi phạm quy tắc** đòi hỏi hiểu cả mô hình dữ liệu lẫn thời điểm, phiên bản và nguồn có thẩm quyền. Không có một câu truy vấn quét hay một job auto-repair nào thay thế được quy định rõ **bất biến áp dụng ở đâu và thế nào mới là đúng**.

Một hệ thống đáng tin cậy cần phòng ngừa bằng validation và ghi nguyên tử, phát hiện qua nhiều đường độc lập, xác minh để loại chênh lệch tạm thời, sửa có điều kiện và idempotent, kiểm chứng với bằng chứng, đồng thời theo dõi và giải quyết nguyên nhân gốc.

**Phát hiện khác biệt chưa có nghĩa biết bản nào sai; biết bản sai chưa có nghĩa đủ điều kiện tự sửa; và sửa thành công một lần chưa có nghĩa hệ thống sẽ không tạo lại lỗi.** Quy trình đầy đủ từ rule đến audit và phòng tái phát mới giúp dữ liệu NoSQL giữ tính đúng đắn khi mở rộng.
