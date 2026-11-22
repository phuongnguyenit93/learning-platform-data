# Đối chiếu `nReturned`, `totalKeysExamined` và `totalDocsExamined` trong kế hoạch thực thi MongoDB

## 1. Đọc `explain()` không chỉ để xem MongoDB có dùng index hay không

Một truy vấn có thể dùng index mà vẫn chậm. Ngược lại, một truy vấn quét collection đôi khi hợp lý nếu collection rất nhỏ hoặc cần trả phần lớn dữ liệu. Vì vậy, khi đánh giá **kế hoạch thực thi (execution plan)** của MongoDB, không nên dừng ở kết luận “có `IXSCAN` thì tốt, có `COLLSCAN` thì xấu”.

Ba chỉ số rất hữu ích trong `explain("executionStats")` là:

- **`nReturned`:** số document kết quả được trả về ở phạm vi thống kê đang xem.
- **`totalKeysExamined`:** tổng số **khóa index** mà quá trình thực thi xem xét.
- **`totalDocsExamined`:** tổng số **document** phải xem xét trong quá trình thực thi.

Chúng giúp trả lời ba câu hỏi khác nhau:

1. Truy vấn thực sự trả lại **bao nhiêu kết quả**?
2. MongoDB phải xem xét **bao nhiêu khóa index** để đi đến kết quả đó?
3. MongoDB phải đọc/xem xét **bao nhiêu document** để xác định kết quả?

Ví dụ trực giác:

```text
Ứng dụng yêu cầu: "Lấy 20 đơn đã thanh toán mới nhất"

Kịch bản A:
    nReturned          = 20
    totalKeysExamined  = 20
    totalDocsExamined  = 20

Kịch bản B:
    nReturned          = 20
    totalKeysExamined  = 40.000
    totalDocsExamined  = 40.000

Kịch bản C:
    nReturned          = 20
    totalKeysExamined  = 0
    totalDocsExamined  = 100.000
```

Nếu cùng một truy vấn, cùng tập dữ liệu và cùng ngữ nghĩa kết quả, A rõ ràng cần xem xét ít khóa/tài liệu hơn. B có thể là một index kém phù hợp hoặc một bước lọc bổ sung đắt tiền; C gợi ý collection scan. Tuy nhiên, **ba bộ số trên chỉ là ví dụ minh họa**, không phải kết quả thực đo, và không cho phép khẳng định ngay mức độ trễ nếu thiếu thông tin về cache, sort, kích thước dữ liệu, giới hạn kết quả và tải hệ thống.

Mục tiêu bài học là biết **đọc, đối chiếu, giải thích và đặt giả thuyết cải thiện**, thay vì áp dụng máy móc một ngưỡng “tỷ lệ tốt/xấu” cho mọi query.

## 2. Chuẩn bị môi trường và bộ dữ liệu thử nghiệm

Các lệnh dùng cú pháp **mongosh**. Nên thực hiện trong một database thử nghiệm, không chạy các lệnh tạo index hoặc ghi dữ liệu mẫu trực tiếp trên collection production. Ví dụ sử dụng collection riêng `explainOrdersDemo`; lần đầu chạy cần collection chưa có các `_id` tương ứng.

```javascript
const docs = [];

for (let i = 0; i < 2000; i++) {
  const group = Math.floor(i / 5);

  docs.push({
    _id: i,
    tenantId: "T" + (i % 5),
    status: group % 4 === 0 ? "PAID" : "PENDING",
    createdAt: new Date(Date.UTC(2026, 9, 1, 0, i)),
    amount: i % 400,
    tags: i % 3 === 0 ? ["vip", "promotion"] : ["regular"]
  });
}

db.explainOrdersDemo.insertMany(docs);
```

Ý nghĩa bộ dữ liệu:

- Có 2.000 document, mỗi document có `_id` khác nhau.
- Có năm tenant `T0` đến `T4`.
- Có cả trạng thái `PAID` và `PENDING`.
- `createdAt` tăng theo phút để tạo thứ tự thời gian rõ ràng.
- `tags` là mảng để có thể quan sát thêm multikey index.

Các giá trị số ở phần minh họa kết quả `explain` phía dưới có thể **khác số thực tế khi chạy**, vì planner phụ thuộc phiên bản MongoDB, dữ liệu, index hiện có, execution engine và điều kiện môi trường.

Truy vấn chính của bài:

```javascript
db.explainOrdersDemo
  .find({
    tenantId: "T2",
    status: "PAID"
  })
  .sort({ createdAt: -1 })
  .limit(10);
```

Yêu cầu nghiệp vụ: **lấy 10 đơn đã thanh toán gần nhất của tenant T2**. Đây là một ví dụ tốt để xem sự tương tác giữa điều kiện lọc, thứ tự index và `limit`.

## 3. Gọi `explain("executionStats")`

### 3.1. Cú pháp thường dùng

```javascript
db.explainOrdersDemo
  .find({
    tenantId: "T2",
    status: "PAID"
  })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

Trong kết quả có thể có các phần quan trọng:

```javascript
{
  queryPlanner: {
    // Thông tin truy vấn đã được chuẩn hóa và kế hoạch được chọn.
    winningPlan: { /* các stage hoặc biểu diễn tương đương */ }
  },
  executionStats: {
    nReturned: 10,
    executionTimeMillis: 1,
    totalKeysExamined: 10,
    totalDocsExamined: 10,
    executionStages: { /* thống kê ở các stage */ }
  }
}
```

**Đây là hình dạng ví dụ** để nhận diện trường; những con số minh họa không phải kết quả bảo đảm từ bộ dữ liệu ở phần 2. Tùy phiên bản, biểu diễn `winningPlan` có thể gồm `queryPlan`, `slotBasedPlan` hoặc cấu trúc stage khác. Đọc **ngữ nghĩa các chỉ số** thay vì phụ thuộc vào một cây JSON duy nhất.

### 3.2. Ba chế độ của `explain`

| Chế độ | Mục đích | Điều cần biết |
|---|---|---|
| `"queryPlanner"` | Xem các kế hoạch và kế hoạch thắng được planner chọn | Chủ yếu là thông tin lập kế hoạch, không phải bộ thống kê thực thi đầy đủ |
| `"executionStats"` | Thực thi để lấy thống kê về kế hoạch được chọn | Cung cấp `nReturned`, `totalKeysExamined`, `totalDocsExamined` và nhiều thống kê khác |
| `"allPlansExecution"` | Xem thêm thống kê của những candidate plan được đánh giá trong giai đoạn chọn kế hoạch, khi được cung cấp | Không nên cộng số của các candidate plan với số của winning plan |

```javascript
db.explainOrdersDemo.explain("queryPlanner")
  .find({ tenantId: "T2" });

db.explainOrdersDemo.explain("executionStats")
  .find({ tenantId: "T2" });

db.explainOrdersDemo.explain("allPlansExecution")
  .find({ tenantId: "T2" });
```

`explain` dùng để hiểu một kế hoạch trong bối cảnh nhất định. Nó không hoàn toàn đồng nhất với việc đo thời gian thực của ứng dụng:

- `explain` có thể không tái hiện việc sử dụng plan cache giống một query thông thường.
- Không đo toàn bộ thời gian chờ connection pool hoặc mọi lượt truyền dữ liệu tới client.
- Một truy vấn thực tế có thể phải xử lý nhiều batch cursor, trong khi cách quan sát explain có phạm vi thống kê riêng.
- Cache nóng/lạnh, tải CPU/I/O và concurrent writes có thể làm thời gian thay đổi.

Khi chẩn đoán production, kết hợp `explain` với profiler, log, metrics của MongoDB và độ trễ đo từ ứng dụng.

## 4. `nReturned`: số kết quả, không phải số document đã đọc

### 4.1. Ý nghĩa

Ở phần thống kê thực thi tổng thể của một câu `find`, `nReturned` thường diễn đạt **số document truy vấn trả về** trong lần thực thi được phân tích.

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).limit(10).explain("executionStats");
```

Trong ví dụ này, `nReturned` không lớn hơn 10 vì câu query có `limit(10)`. Nhưng không thể suy ra MongoDB chỉ phải xem xét 10 khóa hoặc 10 document để tìm được chúng.

### 4.2. Lưu ý với `limit`

Giả sử filter rất ít chọn lọc. MongoDB có thể phải đọc hàng trăm document mới tìm đủ 10 document khớp:

```text
nReturned         = 10
totalDocsExamined = 500
```

Tỷ lệ 500/10 gợi ý nhiều document đã được xem xét trước khi trả 10 kết quả. Tuy nhiên, nếu có `sort` không được index hỗ trợ, máy chủ có thể cần duyệt rất nhiều document khớp để xác định **10 giá trị lớn nhất/nhỏ nhất** trước khi trả batch đầu.

Ngược lại, với index khớp bộ lọc và thứ tự, máy chủ có thể lấy 10 document phù hợp từ một vùng khóa gần nhau rồi dừng sớm.

### 4.3. Lưu ý với `skip`

```javascript
db.explainOrdersDemo.find({ tenantId: "T2" })
  .sort({ createdAt: -1 })
  .skip(100)
  .limit(10)
  .explain("executionStats");
```

Ở đây `nReturned` tối đa là 10, nhưng để tới trang được yêu cầu, server có thể phải duyệt qua các kết quả bị `skip` bỏ qua. Đừng dùng `nReturned = 10` để kết luận chi phí đọc chỉ bằng 10.

### 4.4. Lưu ý với aggregation

```javascript
db.explainOrdersDemo.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
```

Nếu pipeline nhóm ra năm tenant, số document **đầu ra** chỉ là năm, dù các stage trước có thể đã xem xét hàng trăm document nguồn. Với pipeline `$unwind`, một document nguồn còn có thể tạo **nhiều document trung gian**.

Vì vậy, khi phân tích aggregation phải phân biệt:

- `nReturned` tại **đầu ra cuối** hoặc tại một stage.
- Số document được đưa qua **các stage trung gian**.
- `totalDocsExamined` / `totalKeysExamined` của **truy cập storage**.

Không dùng tỷ lệ `totalDocsExamined / nReturned` của một pipeline `$group` để kết luận ngay index kém: việc **nhiều document nguồn tạo ít nhóm đầu ra** có thể chính là yêu cầu nghiệp vụ.

## 5. `totalKeysExamined`: số khóa index đã được xem xét

### 5.1. Index scan tìm từ khóa đến document

Giả sử đã tạo:

```javascript
db.explainOrdersDemo.createIndex({ tenantId: 1 });
```

Khi lọc `tenantId: "T2"`, MongoDB có thể dùng index để tìm các entry khóa tương ứng. `totalKeysExamined` đếm **số khóa index được xem xét trong quá trình thực thi**, không phải số index tồn tại và cũng không phải số khóa được tạo ra khi xây dựng index.

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2"
}).explain("executionStats");
```

Một document thường có một khóa trong index scalar này, nên ở các truy vấn đơn giản số khóa được xem xét có thể gần số document ứng viên. Nhưng không được xem đây là công thức luôn đúng, vì:

- Compound index có giới hạn khóa theo nhiều trường.
- Multikey index có thể có **nhiều khóa cho cùng một document**.
- Một query có thể duyệt vùng khóa rồi kiểm tra điều kiện bổ sung.
- Một số kế hoạch dùng nhiều index hoặc các stage index khác nhau.
- Các bước thực thi, phạm vi bounds và nhu cầu loại trùng có thể làm số khóa khác số document.

### 5.2. `totalKeysExamined = 0` không tự nghĩa là truy vấn nhanh

Nếu planner chọn `COLLSCAN`, query không phải duyệt khóa index:

```text
totalKeysExamined = 0
totalDocsExamined = 100.000
nReturned         = 10
```

Con số 0 ở `totalKeysExamined` **không có nghĩa “không làm việc”**. Nó có thể cho biết MongoDB đang quét document trực tiếp.

Trong trường hợp collection có 20 document và query cần trả cả 20, `COLLSCAN` có thể hợp lý. Với collection có 100 triệu document và chỉ cần 10 kết quả, cần xem lại bộ lọc và index.

### 5.3. `totalKeysExamined` cao không mặc nhiên là lỗi

Ví dụ một truy vấn thực hiện phân tích tất cả các giá trị khóa trong một khoảng rộng hoặc cần đếm số phần tử khớp. Khi đó việc quét hàng chục nghìn khóa có thể là chi phí tự nhiên của yêu cầu.

Một query **covered** có thể:

```text
nReturned         = 5.000
totalKeysExamined = 5.000
totalDocsExamined = 0
```

Tuy phải quét nhiều khóa, nó có thể không cần đọc document gốc. Cần xem **mục tiêu truy vấn, số lượng kết quả và công việc ở các stage** trước khi đánh giá.

## 6. `totalDocsExamined`: document được xem xét, không phải toàn bộ collection

### 6.1. Ý nghĩa

`totalDocsExamined` ghi nhận số lần engine phải xem xét document khi thực hiện truy vấn. Với kế hoạch có `FETCH`, số này thường phản ánh việc lấy document để kiểm tra điều kiện hoặc tạo kết quả. Với `COLLSCAN`, nó phản ánh số document được quét.

Điểm dễ nhầm:

> **`totalDocsExamined` không bắt buộc bằng số document khác nhau đã được đọc.** Trong những kế hoạch phức tạp, một document có thể bị xem xét nhiều lần; thống kê phản ánh số lần xem xét theo cách engine thực thi.

Ví dụ:

```text
nReturned         = 30
totalKeysExamined = 2.000
totalDocsExamined = 1.500
```

Một cách diễn giải hợp lý là server tìm các ứng viên bằng index rồi vẫn phải lấy/xét nhiều document để tìm 30 kết quả cuối. Nhưng từ ba con số này **chưa thể xác định** chính xác điều kiện nào gây loại bỏ, vì còn cần xem các stage và index bounds.

### 6.2. `totalDocsExamined = 0` có thể là tín hiệu rất tốt

Nếu query được đáp ứng hoàn toàn bằng index, execution engine có thể trả kết quả mà không phải lấy document gốc. Đây là trường hợp **covered query**.

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});

db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1 })
.limit(10)
.explain("executionStats");
```

Các trường được lọc, sắp xếp và trả về đều nằm trong index; projection cũng **loại `_id`**, vì `_id` không nằm trong compound index trên. Khi planner sử dụng index theo cách đáp ứng đủ yêu cầu, `totalDocsExamined` có thể bằng 0.

Không phải mọi query có `IXSCAN` đều là covered query. Nếu projection cần thêm `amount`, server có thể phải `FETCH` document dù index đã giúp tìm đúng vị trí:

```javascript
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 0, createdAt: 1, amount: 1 }
).sort({ createdAt: -1 }).limit(10);
```

Ở đây `amount` không nằm trong index mẫu, nên việc lấy document gốc là nhu cầu bình thường.

### 6.3. `totalDocsExamined` bằng `nReturned` cũng không bảo đảm tối ưu toàn bộ

```text
nReturned         = 10
totalKeysExamined = 30.000
totalDocsExamined = 10
```

Truy vấn có thể đã quét rất nhiều **khóa index** nhưng chỉ phải lấy 10 document. Tỷ lệ document examined/returned rất đẹp, nhưng số khóa cao cho thấy vẫn có chi phí tìm kiếm đáng kể. Đây là lý do **phải đọc cả ba chỉ số cùng nhau**.

## 7. Đối chiếu ba số bằng một bảng tình huống

Những giá trị sau là **số liệu giả định** cho các truy vấn mẫu, không phải kết quả đo từ bộ dữ liệu 2.000 document. Sử dụng chúng để luyện cách diễn giải:

| Kịch bản | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | Cách đọc ban đầu |
|---|---:|---:|---:|---|
| A. Index phù hợp, trả document | 20 | 20 | 20 | Ít khóa và ít document phải xem xét |
| B. Index được dùng nhưng lọc lại nhiều | 20 | 25.000 | 25.000 | Xem lại thứ tự khóa, bộ lọc và stage `FETCH` |
| C. Collection scan | 20 | 0 | 100.000 | Không dùng khóa index, quét nhiều document |
| D. Covered query | 20 | 20 | 0 | Có thể đáp ứng hoàn toàn từ index |
| E. Quét nhiều khóa, fetch ít | 20 | 25.000 | 20 | Chi phí index scan có thể vẫn cao |
| F. `skip` sâu | 20 | 10.020 | 10.020 | Trả 20 nhưng có thể phải duyệt nhiều kết quả bị bỏ |
| G. Tìm trong multikey | 40 | 700 | 90 | Nhiều khóa có thể cùng tham chiếu document; cần kiểm tra plan |
| H. Trả phần lớn collection nhỏ | 200 | 0 | 200 | `COLLSCAN` có thể là lựa chọn hợp lý |

**Không dùng chỉ một hàng trong bảng để kết luận query “nhanh” hay “chậm”.** Để so sánh có ý nghĩa, cần biết các truy vấn đang thực hiện **cùng chức năng**, kết quả có tương đương không, dữ liệu có cùng phân bố và điều kiện giới hạn/sort có giống nhau không.

### 7.1. Cặp tỷ lệ dễ dùng để đặt câu hỏi

Đối với truy vấn `find` thông thường, có thể tính:

\[
\text{Keys per returned doc}=
\frac{\text{totalKeysExamined}}{\text{nReturned}}
\]

\[
\text{Docs per returned doc}=
\frac{\text{totalDocsExamined}}{\text{nReturned}}
\]

Ví dụ kịch bản B:

```text
Keys per returned doc = 25.000 / 20 = 1.250
Docs per returned doc = 25.000 / 20 = 1.250
```

Nói cách khác, trung bình phải xem xét **1.250 khóa và 1.250 document cho mỗi document được trả về**. Đây là một tín hiệu để điều tra tính chọn lọc của index.

**Không tính tỷ lệ khi `nReturned = 0` theo cách chia trực tiếp.** Một query không trả kết quả vẫn có thể quét nhiều khóa/tài liệu; khi đó hãy báo số xem xét tuyệt đối, xem index bounds, và thử hiểu vì sao không có kết quả.

### 7.2. Tỷ lệ chỉ có ý nghĩa khi biết ngữ nghĩa truy vấn

- `limit(10)` làm mẫu số nhỏ, kể cả khi lệnh cố tình duyệt nhiều ứng viên để sắp xếp.
- `skip(100000)` khiến số khóa/tài liệu xem xét cao dù query trả 10 document.
- `$group` có thể biến hàng triệu document thành vài nhóm; tỷ lệ input/output cao là điều tự nhiên.
- `$unwind` có thể làm số document đầu ra lớn hơn số document nguồn.
- Multikey index có nhiều khóa trên cùng một document, khiến `keys/docs` không phản ánh số document gốc duy nhất.
- Query trả hàng nghìn document để export có thể có các tỷ lệ gần 1 nhưng tổng công việc vẫn lớn.

Vì vậy, tỷ lệ là **công cụ đặt giả thuyết**, không phải một tiêu chuẩn chất lượng phổ quát.

## 8. Truy vấn không có index: nhận diện `COLLSCAN`

Giả sử chưa có index thích hợp cho điều kiện:

```javascript
db.explainOrdersDemo.find({
  amount: { $gt: 390 }
}).explain("executionStats");
```

Nếu query planner dùng collection scan, ta có thể thấy:

```text
winningPlan
  COLLSCAN

totalKeysExamined = 0
totalDocsExamined = số document phải quét
nReturned         = số document amount > 390
```

**Không phải lúc nào `totalDocsExamined` cũng bằng toàn bộ số document của collection**. Có thể có `limit` khiến query dừng sớm, hoặc cách thực thi khác làm phạm vi quét thay đổi.

Một index ứng viên:

```javascript
db.explainOrdersDemo.createIndex({ amount: 1 });
```

Sau đó thực hiện lại `explain("executionStats")` để xem planner có chọn index không. Vì bộ dữ liệu chỉ có 2.000 document và điều kiện phân bố theo cách nhân tạo, planner **có thể vẫn chọn `COLLSCAN`** nếu thấy phù hợp.

Không nên ép `hint` vào production chỉ để làm biến mất `COLLSCAN` khỏi explain. Phải đo **tổng công việc** và độ trễ trên workload thực.

## 9. Có `IXSCAN` nhưng vẫn phải đọc nhiều document: xem `FETCH`

### 9.1. Điều kiện không nằm đủ trong index

Giả sử chỉ có index trên `status`:

```javascript
db.explainOrdersDemo.createIndex({ status: 1 });
```

Nhưng query cần lọc cả `tenantId`:

```javascript
db.explainOrdersDemo.find({
  status: "PAID",
  tenantId: "T2"
}).explain("executionStats");
```

Index `{ status: 1 }` có thể giúp tìm những document `PAID`, nhưng nó không lưu `tenantId`. Khi đó server có thể:

1. `IXSCAN` tìm các khóa `status = "PAID"`.
2. `FETCH` lấy document tương ứng.
3. Kiểm tra `tenantId = "T2"` trên document đã lấy.
4. Chỉ trả những document thỏa cả hai điều kiện.

Số khóa và document xem xét có thể lớn hơn `nReturned` đáng kể.

### 9.2. Compound index giúp thu hẹp từ hai phía

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1
});
```

Với cùng query, compound index có khả năng tạo index bounds cho cả hai điều kiện bằng nhau. Truy vấn có thể duyệt ít khóa và ít document hơn.

Nếu muốn vừa lọc theo tenant/trạng thái vừa lấy đơn mới nhất:

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Index mới có thể hỗ trợ cả `sort({ createdAt: -1 })` sau hai điều kiện bằng nhau. Điều này đặc biệt có ích khi query có `limit` nhỏ vì server có thể lấy các document đầu theo thứ tự index mà không cần sắp xếp toàn bộ tập ứng viên.

### 9.3. Đừng đoán chỉ từ một chỉ số

Sau khi thêm index ghép, có thể xảy ra:

```text
Trước:
nReturned         = 10
totalKeysExamined = 500
totalDocsExamined = 500

Sau:
nReturned         = 10
totalKeysExamined = 10
totalDocsExamined = 10
```

Đây là kết quả **giả định** minh họa sự cải thiện về số lần xem xét. Muốn kết luận index thật sự có lợi, còn phải xét chi phí ghi index, kích thước index, những query khác và độ trễ thực tế.

## 10. Ít document được đọc nhưng nhiều khóa: multikey và bounds rộng

MongoDB dùng **multikey index** khi trường được index chứa mảng. Một document có thể đóng góp nhiều khóa index:

```javascript
{
  _id: 1,
  tags: ["mongodb", "index", "backend"]
}
```

```javascript
db.explainOrdersDemo.createIndex({ tags: 1 });

db.explainOrdersDemo.find({
  tags: { $in: ["vip", "promotion"] }
}).explain("executionStats");
```

Trong bộ dữ liệu thử nghiệm, một số document mang **cả hai tag** `"vip"` và `"promotion"`. Query có thể xét nhiều khóa dẫn tới cùng một document rồi khử trùng document kết quả.

Vì vậy, có thể gặp:

```text
totalKeysExamined  > totalDocsExamined
totalDocsExamined >= nReturned  (trong nhiều find có FETCH)
```

Đây là **một dạng tình huống có thể xảy ra**, không phải bất đẳng thức bất biến:

- Covered query có thể có `totalDocsExamined = 0`.
- `COLLSCAN` có `totalKeysExamined = 0`.
- Các stage phức tạp có những cách tính và số lượng trung gian khác nhau.

Khi thấy `keysExamined` cao, cần xem `isMultiKey`, `multiKeyPaths`, index bounds và các stage loại trùng (`dupsTested`, `dupsDropped` nếu được báo cáo). Không thể chỉ từ số khóa cao suy ra index có lỗi.

### 10.1. Bounds kém chặt

Nếu index chỉ giới hạn một điều kiện rộng rồi phải lọc lại bằng trường khác, số khóa cũng có thể cao dù không có mảng:

```javascript
// Index chỉ trên createdAt, query cần điều kiện tenant và status.
db.explainOrdersDemo.createIndex({ createdAt: -1 });

db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(10)
  .explain("executionStats");
```

Server có thể duyệt nhiều document theo thời gian để tìm đủ 10 đơn phù hợp với tenant/trạng thái, tùy kế hoạch được chọn. Index có hỗ trợ thứ tự sort nhưng **không nhất thiết hỗ trợ tốt bộ lọc**. Compound index phù hợp có thể cân bằng cả hai yêu cầu.

## 11. Covered query: `docsExamined = 0` không phải dữ liệu bằng 0

Một covered query minh họa:

```javascript
db.explainOrdersDemo.find(
  {
    tenantId: "T2",
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .limit(10)
 .explain("executionStats");
```

Với compound index `{ tenantId: 1, status: 1, createdAt: -1 }`, MongoDB có thể trả các giá trị cần thiết từ index:

```text
nReturned         = 10
totalKeysExamined = 10
totalDocsExamined = 0
```

Đây là một **kết quả lý tưởng giả định**. Số document được trả vẫn là 10: `totalDocsExamined = 0` chỉ nói rằng engine không cần đọc **document gốc** cho truy vấn cụ thể, không phải nó không tìm thấy dữ liệu.

### 11.1. Vì sao projection quan trọng?

```javascript
// Có thể được cover (nếu index phù hợp).
{ _id: 0, tenantId: 1, status: 1, createdAt: 1 }

// Thường cần đọc thêm document vì amount không có trong index.
{ _id: 0, tenantId: 1, status: 1, createdAt: 1, amount: 1 }
```

Nếu không loại `_id` khỏi projection, MongoDB thường mặc định trả `_id`; trong ví dụ compound index không chứa `_id` như một trường khóa, điều này có thể ngăn covered query.

Không nên tạo index rất rộng chỉ để mọi phép chiếu đều được cover: index lớn làm tăng chi phí ghi, lưu trữ và cache.

### 11.2. Đọc plan để xác nhận

Một kế hoạch index-only có thể không có `FETCH` và cho `totalDocsExamined = 0`. Nhưng biểu diễn stage phụ thuộc phiên bản; với engine mới, kế hoạch có thể trình bày khác. Tốt nhất xem **cùng lúc**:

- Index nào được chọn?
- Các trường cần tìm, sort và trả về có trong index không?
- `totalDocsExamined` có bằng 0 không?
- Có stage hoặc hoạt động nào phải lấy lại document gốc không?

## 12. `nReturned` thấp do `limit` hoặc do điều kiện chọn lọc?

Hai truy vấn đều có thể trả 10 document nhưng ý nghĩa rất khác:

```javascript
// Trả tối đa 10 trong rất nhiều document PAID.
db.explainOrdersDemo.find({
  status: "PAID"
}).limit(10);

// Tìm một giá trị _id cụ thể; có thể trả 0 hoặc 1.
db.explainOrdersDemo.find({
  _id: 123
});
```

### 12.1. Query có `limit` nhỏ

Với `limit(10)`, nReturned = 10 không cho biết trong collection có bao nhiêu document thỏa điều kiện. Nếu query muốn trang đầu trong một danh sách có 100.000 kết quả, index hỗ trợ sort và limit có thể rất quan trọng.

### 12.2. Query có điều kiện cực chọn lọc

Với `{ _id: 123 }`, unique index `_id` thường cho phép truy cập rất ít khóa/document. Ở đây nReturned = 1 phản ánh điều kiện tìm kiếm rất chọn lọc, không phải do giới hạn 1.

### 12.3. Query không trả kết quả

```javascript
db.explainOrdersDemo.find({
  tenantId: "NOT-EXISTING"
}).explain("executionStats");
```

Kết quả có thể là:

```text
nReturned = 0
```

Tuy nhiên:

- Có index phù hợp, máy chủ có thể xác định không có khóa trong khoảng rất nhanh.
- Không có index, máy chủ có thể quét toàn bộ collection vẫn trả 0.

Vì vậy, **nReturned = 0 không đồng nghĩa công việc = 0**. Trong trường hợp này hãy xem trực tiếp `totalKeysExamined`, `totalDocsExamined` và plan; không chia cho nReturned để tạo tỷ lệ.

## 13. Đọc thống kê ở các stage thay vì chỉ nhìn tổng

`executionStats` thường chứa một cây thống kê ở `executionStages` hoặc biểu diễn tương đương. Các stage thường gặp bao gồm:

| Stage hoặc thành phần | Chức năng chính | Gợi ý khi đọc |
|---|---|---|
| `COLLSCAN` | Quét các document trong collection | Có thể làm `totalDocsExamined` cao dù không có index key |
| `IXSCAN` | Quét khóa index | Liên quan `keysExamined` và index bounds |
| `FETCH` | Lấy document sau khi xác định khóa ứng viên | Có thể chứa filter bổ sung và làm tăng document examined |
| `SORT` | Sắp xếp khi không thể chỉ dựa vào thứ tự có sẵn | Xem có blocking sort, giới hạn bộ nhớ hoặc cách tối ưu limit |
| `LIMIT` | Giới hạn số document được chuyển tiếp | Giải thích vì sao `nReturned` thấp |
| `SKIP` | Bỏ qua các kết quả đầu theo thứ tự | Có thể gây nhiều công việc trước khi trả trang |
| `COUNT_SCAN` hoặc stage đếm | Đếm kết quả theo kế hoạch thích hợp | Số đầu ra không nhất thiết phản ánh số khóa cần xem |
| `OR` / các stage nhiều nhánh | Hợp các đường quét từ nhiều điều kiện | Có thể phát sinh trùng hoặc cần gộp kết quả |

**Không được cộng mọi trường `nReturned` trong các stage** để tìm tổng document trả về. Mỗi stage nhận và phát dữ liệu theo phạm vi của chính nó:

```text
 IXSCAN
  keysExamined = 10.000
      |
      v
 FETCH (filter bổ sung)
  nReturned = 150
      |
      v
 SORT
      |
      v
 LIMIT
  nReturned = 20
```

Sơ đồ là **minh họa luồng logic**. Trong plan thực, thứ tự stage, việc đẩy `LIMIT` vào `SORT` và tên stage có thể khác. `nReturned` của `IXSCAN`, `FETCH` và `LIMIT` là số kết quả **ở từng bước**, không phải ba nhóm document độc lập.

### 13.1. Đọc filter ở `FETCH`

Nếu `FETCH` có filter trên `tenantId` trong khi index chỉ chứa `status`, đó là dấu hiệu server phải lấy document để kiểm tra `tenantId`. Compound index chứa cả hai trường có thể giúp giảm khối lượng fetch.

### 13.2. Đọc `indexBounds`

Một compound index được dùng không có nghĩa **mọi trường trong index đều được ràng buộc chặt**. Hãy xem `indexBounds` và điều kiện còn nằm ở filter. Một khoảng toàn miền hoặc rộng có thể khiến số khóa phải xem xét lớn hơn nhiều so với kết quả cuối.

### 13.3. Đọc `rejectedPlans` đúng phạm vi

`queryPlanner.rejectedPlans` mô tả những plan không được chọn; không có nghĩa MongoDB đã thực thi chúng đến hết. Nếu dùng `allPlansExecution`, số liệu trial của các plan khác cũng có phạm vi riêng. Đừng cộng `keysExamined` của candidate plan vào `executionStats.totalKeysExamined` rồi đánh giá query.

## 14. Sort: vì sao chỉ nhìn ba số là chưa đủ?

Giả sử query:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

Truy vấn có hai phần:

1. Tìm document thỏa điều kiện.
2. Chọn **10 document có `createdAt` mới nhất**.

Nếu index chỉ hỗ trợ điều kiện bằng nhau nhưng không hỗ trợ sort, MongoDB có thể phải xem xét **toàn bộ tập ứng viên** để xác định 10 document mới nhất. Kết quả vẫn là:

```text
nReturned = 10
```

nhưng `totalKeysExamined` và `totalDocsExamined` có thể lớn hơn 10.

Compound index:

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

có thể giúp đọc đúng thứ tự trong vùng tenant/trạng thái và dừng sớm nhờ `limit`.

**Tuy nhiên, hai plan có cùng ba chỉ số vẫn có thể có thời gian khác nhau** nếu một plan cần sort, tính toán hoặc xử lý bộ nhớ nhiều hơn. Khi đánh giá truy vấn có `sort`, xem thêm stage `SORT`, khả năng dùng index để sort và `executionTimeMillis` trong bối cảnh đo.

## 15. Phân trang sâu: nReturned nhỏ nhưng phải duyệt nhiều

Ví dụ:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2"
})
.sort({ createdAt: -1, _id: -1 })
.skip(300)
.limit(20)
.explain("executionStats");
```

Nếu index hỗ trợ filter và thứ tự, server có thể vẫn phải **đi qua** số lượng lớn kết quả trước khi lấy 20 document ở trang sâu. Điều đó có thể tạo:

```text
nReturned         = 20
totalKeysExamined ≈ 320
totalDocsExamined có thể lớn, nhỏ hơn 320 hoặc bằng 0
```

Đây chỉ là minh họa định tính; con số thực tế phụ thuộc projection, plan và thứ tự stage. Điểm đáng nhớ là `skip` có thể khiến chi phí tăng theo độ sâu của trang.

Nếu ứng dụng cần cuộn liên tục qua lượng dữ liệu lớn, cân nhắc **keyset pagination**:

```javascript
// Trang đầu.
db.explainOrdersDemo.find({
  tenantId: "T2"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Lưu `lastCreatedAt` và `lastId` của document cuối trang. Trang sau dùng điều kiện trên khóa sắp xếp:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

`lastCreatedAt` và `lastId` ở đây là biến do ứng dụng lấy từ trang trước; không chạy đoạn trang sau khi chưa khởi tạo hai biến đó.

Keyset pagination giúp tránh việc phải bỏ qua một offset rất lớn, nhưng chỉ hoạt động đúng khi thứ tự, token, điều kiện lọc và trường sort được thiết kế nhất quán. Phương pháp này không tự tạo snapshot cố định khi dữ liệu đang được ghi đồng thời.

## 16. Đối chiếu index trước và sau một thay đổi

Khi muốn thử một compound index, cách thực hiện có kỷ luật là giữ **nguyên query và cùng tập dữ liệu**, chỉ thay một biến mỗi lần.

### 16.1. Lưu truy vấn cần phân tích

```javascript
const filter = { tenantId: "T2", status: "PAID" };
const sort = { createdAt: -1 };
const limit = 10;

db.explainOrdersDemo.find(filter)
  .sort(sort)
  .limit(limit)
  .explain("executionStats");
```

### 16.2. So sánh các hướng index

Ví dụ các index ứng viên:

```javascript
// Chỉ tenant:
db.explainOrdersDemo.createIndex({ tenantId: 1 });

// Tenant + status:
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1
});

// Tenant + status + sort:
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Trong thực hành, các index có thể cùng tồn tại. Planner có thể chọn một index khác với index vừa tạo. Nếu cần so sánh **riêng một index** trong môi trường thử nghiệm, có thể dùng `hint()` để yêu cầu một kế hoạch thích hợp:

```javascript
db.explainOrdersDemo.find(filter)
  .sort(sort)
  .limit(limit)
  .hint({ tenantId: 1, status: 1, createdAt: -1 })
  .explain("executionStats");
```

**Không biến `hint()` thành khuyến nghị áp dụng đại trà trong production**. Hint ép một đường sử dụng index; khi dữ liệu, version, phân bố khóa hoặc workload thay đổi, index được ép có thể không còn tốt. Dùng hint chủ yếu để thử nghiệm có kiểm soát và xác thực tác động trước khi cân nhắc sử dụng lâu dài.

### 16.3. Bảng ghi nhận kết quả thực tế

Sau mỗi lần chạy `explain`, ghi lại:

| Kế hoạch/index | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | `executionTimeMillis` | Có `SORT`? |
|---|---:|---:|---:|---:|---|
| Collection scan hoặc baseline | Điền từ explain | Điền từ explain | Điền từ explain | Điền từ explain | Có/không |
| Index `tenantId` | Điền từ explain | Điền từ explain | Điền từ explain | Điền từ explain | Có/không |
| Index `tenantId, status` | Điền từ explain | Điền từ explain | Điền từ explain | Điền từ explain | Có/không |
| Index `tenantId, status, createdAt` | Điền từ explain | Điền từ explain | Điền từ explain | Điền từ explain | Có/không |

Đừng chỉ chọn hàng có `executionTimeMillis` thấp nhất sau một lần chạy, vì số mili-giây có thể biến thiên do cache, background load và kích thước dữ liệu nhỏ. Hãy đọc **kết hợp** số khóa, số document, stage, độ trễ thực tế và chi phí duy trì index.

## 17. Các trường hợp không thể kết luận chỉ bằng ba chỉ số

### 17.1. Kết quả phải được nhóm hoặc tổng hợp

```javascript
db.explainOrdersDemo.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      totalAmount: { $sum: "$amount" }
    }
  }
]);
```

Một kết quả gồm năm nhóm có thể yêu cầu xem nhiều document nguồn. `nReturned` đầu ra thấp là bình thường. Hãy quan sát chi phí đầu vào và các stage `$match`, `$group`, thay vì áp dụng cùng tỷ lệ cho query trang danh sách.

### 17.2. Truy vấn cần trả rất nhiều document

Một export 100.000 document có thể có:

```text
nReturned         = 100.000
totalKeysExamined = 100.000
totalDocsExamined = 100.000
```

Tỷ lệ keys/returned và docs/returned gần 1 trông rất tốt, nhưng việc truyền 100.000 document qua mạng, giải mã BSON và xử lý trong ứng dụng vẫn có thể tốn đáng kể thời gian. Trong tình huống này, xem thêm projection, batch size, throughput và khả năng xử lý streaming.

### 17.3. Các document kích thước khác nhau

Hai truy vấn cùng đọc 1.000 document nhưng một tập có document vài trăm byte, tập kia có document rất lớn. Ba chỉ số không phản ánh trực tiếp **số byte dữ liệu phải đọc hoặc trả về**. Cache hit, I/O đĩa và kích thước document có thể ảnh hưởng mạnh đến thời gian.

### 17.4. Truy vấn dùng nhiều index hoặc có nhánh `$or`

```javascript
db.explainOrdersDemo.find({
  $or: [
    { tenantId: "T1", status: "PAID" },
    { tenantId: "T2", status: "PAID" }
  ]
}).explain("executionStats");
```

Một kế hoạch có thể dùng nhiều nhánh index rồi hợp kết quả; số khóa được xem xét có thể là tổng của các nhánh. Một document cũng có thể khớp nhiều nhánh và cần xử lý trùng lặp. Phải xem cấu trúc các stage thay vì diễn giải ba chỉ số như một đường index đơn giản.

### 17.5. Query trên sharded cluster

Trong sharded cluster, `mongos` có thể gửi truy vấn đến một hoặc nhiều shard. Phản hồi explain có thể có thống kê theo shard và phần gộp kết quả. Khi đó:

- `nReturned` của từng shard không nhất thiết bằng số document cuối ở client.
- Các shard có thể xem xét số khóa/document rất khác nhau do phân bố dữ liệu.
- Sort/limit và các bước merge có thể ảnh hưởng số kết quả ở các cấp.
- Một shard “nóng” hoặc chậm có thể quyết định độ trễ dù tổng counters không quá lớn.

Đọc cả **thống kê từng shard** và kế hoạch gộp ở router. Không cộng nhầm những số đã được tổng hợp với những số trong từng shard nếu chúng thể hiện cùng công việc ở các cấp khác nhau.

## 18. Các chỉ số bổ sung nên xem cùng ba số chính

| Chỉ số/thông tin | Câu hỏi bổ sung |
|---|---|
| `winningPlan` | Planner đã chọn chiến lược gì? |
| `indexName` / `keyPattern` | Query thực sự dùng index nào? |
| `indexBounds` | Những vùng khóa nào được quét? Rộng hay hẹp? |
| `executionStages` | Chi phí xuất hiện ở stage nào? |
| `executionTimeMillis` | Thời gian mà explain ghi nhận là bao nhiêu trong lần phân tích? |
| `SORT` và các thống kê liên quan | Có sắp xếp tốn tài nguyên không? |
| `isMultiKey` / `multiKeyPaths` | Index có liên quan đến mảng không? |
| `dupsTested` / `dupsDropped` khi có | Có nhiều khóa/nhánh cùng dẫn tới một document không? |
| `rejectedPlans` | Các phương án nào đã được planner xem xét rồi không chọn? |
| Profiler và application metrics | Người dùng thực sự chờ ở bước nào? |

**Cần phân biệt metric server-side và client-side.** `executionTimeMillis` của explain không bao gồm mọi thời gian ứng dụng chờ chọn server, đợi connection pool, tải nhiều batch, giải mã dữ liệu và xử lý JSON sau khi nhận.

## 19. Quy trình chẩn đoán một truy vấn chậm

Khi gặp query trả vài dòng nhưng chậm, có thể dùng quy trình sau.

### Bước 1 — Cố định câu hỏi nghiệp vụ

Xác định rõ bộ lọc, projection, sort, limit/skip và nhu cầu consistency:

```javascript
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 1, createdAt: 1, amount: 1 }
).sort({ createdAt: -1 }).limit(10);
```

Đừng so sánh truy vấn trả toàn document với truy vấn chỉ trả hai trường mà coi chúng tương đương về chi phí.

### Bước 2 — Thu thập explain

```javascript
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 1, createdAt: 1, amount: 1 }
).sort({ createdAt: -1 }).limit(10)
 .explain("executionStats");
```

Ghi ba chỉ số cùng `winningPlan`, index được chọn, sort và thời gian.

### Bước 3 — Đọc ba chỉ số theo thứ tự

**Trước tiên xem `nReturned`:** query có trả đúng số kỳ vọng? Có `limit`, `skip` hoặc aggregation làm thay đổi đầu ra?

**Tiếp theo xem `totalDocsExamined`:** server có phải đọc nhiều document để lấy ít kết quả không? Có `FETCH`, `COLLSCAN` hoặc filter bổ sung?

**Sau đó xem `totalKeysExamined`:** query có quét nhiều khóa index không? Index bounds rộng? Có multikey, `$in`, `$or` hoặc xử lý trùng?

Đọc theo thứ tự này giúp tránh giải thích sai một số lớn mà chưa biết nó phục vụ mục tiêu gì.

### Bước 4 — Khoanh vùng nguyên nhân

| Quan sát | Các nguyên nhân có thể kiểm tra tiếp |
|---|---|
| `keys = 0`, `docs` rất lớn | Collection scan; index không có/không hữu ích, hoặc query cần nhiều document |
| `keys` lớn, `docs` lớn, `nReturned` nhỏ | Index lọc kém, filter nằm ở FETCH, sort/skip hoặc range quá rộng |
| `keys` lớn, `docs` thấp | Quét nhiều index keys, multikey/khử trùng, bounds rộng, index-only một phần |
| `docs = 0`, `keys` gần `nReturned` | Khả năng covered query hiệu quả |
| `nReturned = 0` nhưng `docs` lớn | Không khớp kết quả nhưng đã quét nhiều tài liệu |
| `keys/docs` ít nhưng query vẫn chậm | Sort, CPU expression, kích thước document, I/O, network, ứng dụng |
| Cùng query nhưng chỉ chậm trên một shard | Phân bố dữ liệu, index, cache hoặc tải shard không đồng đều |

### Bước 5 — Đề xuất ít thay đổi có mục tiêu

Những hướng thường có ích:

- Tạo/chỉnh compound index theo bộ lọc và thứ tự sort.
- Rà soát thứ tự trường index (điều kiện bằng nhau, điều kiện khoảng, sort).
- Giảm field projection không cần thiết.
- Tránh `skip` quá sâu khi phù hợp với keyset pagination.
- Kiểm tra điều kiện type, array và `$elemMatch` có đúng nghĩa nghiệp vụ không.
- Sửa mô hình dữ liệu nếu phải tính toán hoặc kết hợp dữ liệu quá tốn kém cho mỗi request.
- Giảm số document phải trả nếu API thật sự không cần chúng.

### Bước 6 — Đo lại cùng workload

Sử dụng cùng query, tập dữ liệu, projection và sort. Ghi lại ba chỉ số trước/sau cùng latency và chi phí ghi/index. Một thay đổi có thể giúp query A nhưng làm tăng chi phí insert/update hoặc làm index lớn, ảnh hưởng query B.

### Bước 7 — Không bỏ qua môi trường production

Index được chọn trong bộ dữ liệu 2.000 document có thể khác với collection 100 triệu document. Kết quả đo cần được xác thực trên workload đại diện, cùng điều kiện caching và dữ liệu có phân bố gần thực tế. Chỉ những con số **thật từ môi trường đo** mới có thể dùng để cam kết cải thiện hiệu năng.

## 20. Những nhầm lẫn hay gặp

| Nhầm lẫn | Diễn giải đúng |
|---|---|
| `IXSCAN` luôn nhanh | Index có thể quét rất nhiều khóa; cần xem bounds và số lượng trả về |
| `COLLSCAN` luôn xấu | Với tập nhỏ hoặc query trả phần lớn dữ liệu, collection scan có thể hợp lý |
| `nReturned` là số document đã xét | Nó phản ánh đầu ra ở phạm vi thống kê đang xem |
| `totalKeysExamined` là số index được sử dụng | Nó là số **khóa index được xem xét**, không phải số cấu trúc index |
| `totalDocsExamined` là tổng document của collection | Nó là số lần document được xem xét trong quá trình thực thi |
| `totalKeysExamined = 0` nghĩa không tốn chi phí | Collection scan có thể có `keys = 0` và `docs` rất lớn |
| `totalDocsExamined = 0` nghĩa không trả kết quả | Covered query có thể trả kết quả từ index mà không đọc document gốc |
| `totalDocsExamined = nReturned` nghĩa chắc chắn tối ưu | Có thể vẫn quét rất nhiều khóa hoặc có sort/cost khác |
| Keys lớn hơn docs nghĩa index bị lỗi | Multikey và các kế hoạch phức tạp có thể xem nhiều khóa cho một document |
| Nên chia `docs / nReturned` cho mọi aggregation | Group/unwind/count làm thay đổi ý nghĩa số document đầu ra |
| `nReturned = 0` nghĩa query gần như miễn phí | Query không khớp vẫn có thể quét rất nhiều dữ liệu |
| `limit(10)` bảo đảm chỉ xét 10 document | Sort, skip và filter kém chọn lọc có thể khiến server xét nhiều hơn |
| `explain` có đủ mọi thời gian hệ thống | Không bao gồm đầy đủ thời gian driver, network và xử lý của ứng dụng |
| Tạo compound index chắc chắn được planner chọn | Planner còn đánh giá dữ liệu, thống kê, điều kiện query và các index khác |
| Mọi lần explain đều cho cùng số/timing | Kế hoạch và thời gian có thể thay đổi theo điều kiện và phiên bản |

## 21. Bài tập thực hành

### Bài 1 — Đọc bảng thống kê

Ba kế hoạch của **cùng một truy vấn** có số liệu giả định:

| Kế hoạch | `nReturned` | `totalKeysExamined` | `totalDocsExamined` |
|---|---:|---:|---:|
| A | 15 | 15 | 15 |
| B | 15 | 4.000 | 4.000 |
| C | 15 | 0 | 50.000 |

Hãy trả lời:

1. Kế hoạch nào xem xét ít khóa và ít document nhất?
2. Kế hoạch nào nhiều khả năng dùng `COLLSCAN`?
3. Kế hoạch nào có thể dùng index nhưng vẫn phải lọc lại nhiều?
4. Vì sao chưa thể chỉ từ bảng này chứng minh latency của A là nhỏ nhất?

### Bài 2 — Tự chạy `explain("executionStats")`

Dùng collection `explainOrdersDemo` ở phần 2:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(10)
  .explain("executionStats");
```

Ghi `nReturned`, `totalKeysExamined`, `totalDocsExamined` và stage của winning plan. Sau đó tạo index `{ tenantId: 1, status: 1, createdAt: -1 }` và chạy lại. Giải thích kết quả dựa trên **chỉ số bạn thực sự đọc được**, không dựa vào số minh họa trong bài.

### Bài 3 — Vì sao projection làm thay đổi `docsExamined`?

Với index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

So sánh:

```javascript
// A
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
).explain("executionStats");

// B
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1, amount: 1 }
).explain("executionStats");
```

Hãy xác định truy vấn nào **có khả năng covered**, vì sao thêm `amount` có thể dẫn đến `FETCH`, và tại sao một index rộng hơn chưa chắc tốt hơn về tổng chi phí hệ thống.

### Bài 4 — Xem tác động của sort và limit

So sánh hai query:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).limit(10).explain("executionStats");

db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

Tại sao thêm sort có thể khiến truy vấn xem xét nhiều hơn dù `nReturned` vẫn là 10? Compound index có thể giúp ở bước nào?

### Bài 5 — `nReturned = 0`

Chạy một query không thể khớp:

```javascript
db.explainOrdersDemo.find({
  tenantId: "NOT-EXISTING"
}).explain("executionStats");
```

Hãy so sánh kế hoạch khi **có** và **không có** index hỗ trợ `tenantId` trên một môi trường thử nghiệm phù hợp. Tại sao không thể tính tỷ lệ docs/returned khi không có kết quả? Những chỉ số nào cho biết query phải làm nhiều hay ít việc?

### Bài 6 — Multikey và số khóa

Tạo index:

```javascript
db.explainOrdersDemo.createIndex({ tags: 1 });
```

Chạy:

```javascript
db.explainOrdersDemo.find({
  tags: { $in: ["vip", "promotion"] }
}).explain("executionStats");
```

Giải thích vì sao một document có hai tag đều khớp mà `find()` chỉ trả document đó một lần. Khi số khóa được xem xét lớn hơn số document được đọc, nên tìm thông tin gì trong plan?

### Bài 7 — So sánh phân trang offset và keyset

Truy vấn:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2"
}).sort({ createdAt: -1, _id: -1 })
  .skip(300)
  .limit(20)
  .explain("executionStats");
```

Hãy thiết kế truy vấn keyset cho trang tiếp theo dựa trên `createdAt` và `_id` của document cuối trang trước. Giải thích vì sao ở trang sâu, `nReturned` có thể vẫn là 20 nhưng `totalKeysExamined` lớn.

### Bài 8 — Kết quả aggregation không giống kết quả find

Cho pipeline:

```javascript
db.explainOrdersDemo.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
```

Hãy mô tả vì sao số document đầu ra của pipeline có thể nhỏ hơn rất nhiều so với `totalDocsExamined`. Đâu là thời điểm nên xem thống kê stage `$group` thay vì dùng một tỷ lệ đơn giản?

### Bài 9 — Phân biệt truy vấn index-only và collection scan

Hai bộ số giả định:

```text
X: nReturned=100, totalKeysExamined=100, totalDocsExamined=0
Y: nReturned=100, totalKeysExamined=0, totalDocsExamined=100
```

Hãy đề xuất một kế hoạch hợp lý cho X và Y. Có thể khẳng định X luôn nhanh hơn Y không? Những dữ kiện bổ sung nào cần biết để đánh giá?

### Bài 10 — Viết báo cáo chẩn đoán ngắn

Một API lấy 20 đơn gần nhất:

```text
nReturned         = 20
totalKeysExamined = 90.000
totalDocsExamined = 1.000
```

Hãy viết báo cáo gồm:

1. Hai chỉ số nào có độ chênh lớn so với số kết quả?
2. Ít document fetched hơn keys examined gợi ý những nguyên nhân nào?
3. Cần xem thêm các stage, index bounds, multikey hoặc sort nào?
4. Một index ghép có thể giúp thế nào nếu query lọc theo `tenantId`, `status` rồi sort theo `createdAt`?
5. Cần đo lại những gì trước khi đề xuất áp dụng index cho production?

## 22. Tổng kết

**`nReturned` cho biết đầu ra, `totalKeysExamined` cho biết số khóa index phải xem xét, `totalDocsExamined` cho biết số lần document được xem xét.** Ba chỉ số mô tả những lớp công việc khác nhau của kế hoạch thực thi và chỉ có ý nghĩa khi đặt cạnh nhau.

**Số gần nhau không tự động là tối ưu; số chênh lệch không tự động là lỗi.** Một covered query có thể có `docsExamined = 0`, collection scan có `keysExamined = 0`, multikey index có nhiều khóa cho một document, còn `limit` hoặc `$group` có thể làm `nReturned` rất nhỏ so với đầu vào.

**Muốn tối ưu chính xác, phải hiểu query trước khi nhìn con số.** Xác định filter, projection, sort, limit/skip, dữ liệu mảng, index bounds và những stage làm việc nhiều nhất; sau đó mới đưa ra giả thuyết về index hoặc mô hình truy vấn.

**`explain("executionStats")` là điểm khởi đầu cho điều tra, không phải bài kiểm tra hiệu năng cuối cùng.** Hãy đối chiếu với độ trễ thực tế, lượng dữ liệu đọc/truyền, tải hệ thống và chi phí duy trì index trước khi quyết định thay đổi. Khi đọc đúng ba chỉ số trong ngữ cảnh, bạn có thể giải thích **MongoDB đã phải làm bao nhiêu việc để tạo ra kết quả** thay vì chỉ nhận xét cảm tính rằng “query có index”.
