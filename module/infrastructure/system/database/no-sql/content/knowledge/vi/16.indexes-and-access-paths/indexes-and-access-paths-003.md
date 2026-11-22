# Chỉ mục đơn, ghép và quy tắc thứ tự các thành phần

Trong cơ sở dữ liệu NoSQL, một truy vấn trả về 20 đơn hàng có thể phải đọc **20, 2.000 hoặc 2 triệu bản ghi** tùy dữ liệu được lưu và lập chỉ mục ra sao. Vì vậy, lựa chọn **chỉ mục đơn (single-field index)**, **chỉ mục ghép (compound/composite index)** và **thứ tự các thành phần khóa** ảnh hưởng trực tiếp đến độ trễ, lượng I/O, dung lượng và chi phí ghi.

Giả sử API cần:

~~~text
Cho tenant T1 và trạng thái PAID:
    lấy 20 đơn mới nhất;
    sort theo createdAt giảm dần;
    dùng cursor để phân trang.
~~~

Chỉ mục theo riêng **status** có thể tìm nhiều đơn PAID rồi vẫn phải lọc tenant và sắp xếp. Chỉ mục ghép theo **(tenantId, status, createdAt DESC, orderId DESC)** có thể cung cấp đường đọc sát yêu cầu hơn: khoanh phạm vi tenant/status rồi duyệt theo thứ tự cần trả.

Tuy vậy, quy tắc chỉ mục **không giống nhau ở tất cả NoSQL**. Compound B-tree index của MongoDB khác partition key và sort key của DynamoDB; clustering key của Cassandra khác secondary index, còn Redis sorted set và inverted index của search engine cũng có tính chất riêng. Bài học trước hết giải thích quy tắc trên mô hình index có thứ tự, sau đó đối chiếu từng công nghệ để tránh áp dụng nhầm.

## 1. Index là đường truy cập, không phải bản thân truy vấn

Giả sử có một triệu document:

~~~json
{
  "orderId": "O-9001",
  "tenantId": "T1",
  "customerId": "C42",
  "storeId": "S12",
  "status": "PAID",
  "createdAt": "2026-11-14T10:30:00Z",
  "totalMinor": 250000
}
~~~

Muốn tìm đơn của C42, hệ có thể phải kiểm tra rất nhiều document nếu không có đường truy cập phù hợp. Một secondary index giúp định vị các document có field customerId:

~~~text
Document source:
    O-9001 -> customerId C42
    O-9002 -> customerId C77
    O-9003 -> customerId C42

Single-field index customerId:
    C42 -> O-9001, O-9003
    C77 -> O-9002
~~~

Index có thể chứa khóa và thông tin định vị document. Query đọc entry trong index, rồi có thể cần truy xuất document nguồn để lấy các field chưa nằm trong index.

| Khái niệm | Vai trò |
| --- | --- |
| **Primary key** | Xác định bản ghi hoặc định tuyến tới phạm vi lưu trữ. |
| **Secondary index** | Cung cấp đường truy cập phụ theo một hoặc nhiều thuộc tính. |
| **Single-field index** | Index trên một field. |
| **Compound index** | Index nhiều field, có thứ tự khai báo xác định. |
| **Partition/shard key** | Phân phối dữ liệu giữa partition hoặc node. |
| **Clustering/sort key** | Tổ chức thứ tự trong phạm vi partition hoặc item collection. |
| **Covering index** | Có thể trả những field cần thiết mà không đọc document nguồn, khi điều kiện engine cho phép. |
| **Index selectivity** | Mức độ điều kiện giúp giảm số ứng viên phải kiểm tra. |
| **Index intersection** | Kết hợp nhiều index để tìm tập kết quả, nếu optimizer hỗ trợ. |

Có index không đồng nghĩa optimizer chắc chắn dùng index: nếu phần lớn document khớp, scan có thể là kế hoạch hợp lý. Quyết định phải dựa trên **query plan và số bản ghi/entry thực sự được đọc**.

## 2. Chỉ mục đơn: khi nào đủ?

Trong MongoDB:

~~~javascript
db.orders.createIndex({ customerId: 1 });

db.orders.find({
  customerId: "C42"
});
~~~

Index trên customerId có thể giúp lấy những order thuộc khách này, nhưng chưa tự phục vụ một query phức tạp:

~~~javascript
db.orders.find({
  tenantId: "T1",
  customerId: "C42",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Nếu C42 có 30 đơn, lọc và sort tiếp sau index customerId có thể không đáng kể. Nếu khách có 200.000 đơn, cùng cách đọc có thể quá tốn kém.

**Chỉ mục đơn** thường phù hợp khi:

- Một trường là điều kiện chính, có độ chọn lọc tốt.
- Query không thường xuyên sort trên tập ứng viên lớn.
- Đường đọc theo field này được dùng ở nhiều vị trí.
- Index ghép tăng chi phí ghi nhưng chưa mang lại lợi ích được đo.
- Dữ liệu tăng trưởng vẫn nằm trong SLO.

Một index theo **status** có thể kém chọn lọc nếu 80% order là PAID. Không thêm index cho mọi field xuất hiện trong filter chỉ theo cảm tính.

## 3. Chỉ mục ghép là một khóa có thứ tự

Ví dụ:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  orderId: -1
});
~~~

Khóa khái niệm được sắp theo từng thành phần:

~~~text
(tenantId, status, createdAt DESC, orderId DESC)

T1, PAID, 2026-11-14 10:30, O-9001
T1, PAID, 2026-11-14 10:20, O-9002
T1, PAID, 2026-11-14 10:10, O-9003
T1, PENDING, ...
T2, PAID, ...
~~~

Khi tenantId và status được cố định bằng equality, index có thể cho một phạm vi mà createdAt đã có thứ tự mong muốn. Query có thể duyệt các entry và dừng sớm sau khi tìm đủ kết quả phù hợp.

Hai index sau **không tương đương**:

~~~javascript
// A: nhóm tenant/status trước, rồi tới thời gian.
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});

// B: thời gian đứng trước, status và tenant phía sau.
db.orders.createIndex({
  createdAt: -1,
  status: 1,
  tenantId: 1
});
~~~

Với query **tenantId + status + sort theo createdAt**, A có thể định vị hiệu quả hơn. Với query **20 đơn mới nhất toàn hệ**, B có thể hợp lý hơn. Không có một thứ tự tối ưu cho mọi access pattern.

## 4. Quy tắc tiền tố trái (leftmost prefix)

Với ordered compound index:

~~~text
(A, B, C, D)
~~~

Các tiền tố thuận lợi:

~~~text
(A)
(A, B)
(A, B, C)
(A, B, C, D)
~~~

Lý do: khi có A, engine có thể định vị vùng entry chứa A; khi thêm B, vùng đó hẹp hơn. Nếu chỉ có C, entry mang C nằm rải trong nhiều nhóm A/B nên thường không có một vùng liên tục để seek trực tiếp.

Ví dụ:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

| Filter | Khả năng khai thác khóa theo tiền tố |
| --- | --- |
| tenantId = T1 | Có tiền tố tenantId. |
| tenantId = T1 và status = PAID | Có tiền tố tenantId + status. |
| tenantId = T1, status = PAID và createdAt trong khoảng | Có thể thu hẹp cả ba trường. |
| Chỉ status = PAID | Thiếu field đầu tenantId. |
| Chỉ createdAt gần đây | Thiếu hai field đầu. |
| tenantId = T1 và createdAt gần đây, không có status | Có thể thu hẹp tenantId, nhưng createdAt không là một vùng liên tục đơn giản qua mọi status. |

**Chú ý:** điều này không có nghĩa optimizer tuyệt đối không bao giờ sử dụng index nếu thiếu trường đầu. Một số engine có thể quét index rộng, áp filter hoặc dùng tối ưu khác. Nguyên tắc đúng là **không khai thác được lợi thế seek theo tiền tố như truy vấn có đầy đủ các thành phần trước**.

Nếu một API quan trọng thường xuyên lọc status mà không biết tenantId, có thể cần index khác, read model khác hoặc xem lại vì sao API không có tenantId.

## 5. Equality, Sort, Range: quy tắc ESR

Khi thiết kế ordered compound index cho MongoDB, một hướng dẫn hữu ích là:

1. **E – Equality:** field có điều kiện so sánh bằng.
2. **S – Sort:** field được dùng cho thứ tự kết quả.
3. **R – Range:** field có điều kiện khoảng như >=, <=, >, <.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID",
  totalMinor: { $gte: 100000 }
})
.sort({
  createdAt: -1,
  orderId: -1
})
.limit(20);
~~~

Hai candidate index:

~~~javascript
// ESR: equality -> sort -> range.
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  orderId: -1,
  totalMinor: 1
});

// ERS: equality -> range -> sort.
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  totalMinor: 1,
  createdAt: -1,
  orderId: -1
});
~~~

### Khi ESR thuận lợi

Nếu điều kiện tổng tiền không quá chọn lọc và query cần các order mới nhất trước, sắp xếp theo createdAt ngay trong index có thể tránh sort một tập lớn.

Tuy vậy, totalMinor đứng phía sau sort có thể buộc engine xem nhiều entry để tìm đủ 20 order vượt ngưỡng.

### Khi ERS có thể tốt hơn

Nếu totalMinor >= 100000 chỉ khớp 0,01% order, đặt range sớm có thể giảm mạnh số ứng viên. Đổi lại, vì các entry được sắp theo totalMinor trước createdAt, query có thể cần sort sau khi lọc.

**ESR là heuristic, không phải định luật**. Cần so số index entry được đọc, số document fetch, chi phí sort, memory, latency và selectivity thật. Khi range rất chọn lọc, **ERS** có thể tốt hơn.

## 6. Hai field equality có bắt buộc thứ tự nào?

Cho query:

~~~javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID"
})
.sort({ createdAt: -1 });
~~~

Hai index:

~~~text
(tenantId, status, createdAt DESC)
(status, tenantId, createdAt DESC)
~~~

đều có thể cung cấp một phạm vi hẹp nếu **cả tenantId và status có điều kiện bằng**.

Nhưng chúng có mức tái sử dụng khác:

- Index bắt đầu bằng tenantId thuận lợi với query chỉ biết tenantId.
- Index bắt đầu bằng status thuận lợi nếu query khác chỉ biết status, dù status có thể rất ít chọn lọc.
- Nếu mọi query của hệ đa tenant bắt buộc có tenantId, đặt tenantId trước thường đáng cân nhắc.
- Nếu query có thêm IN, range và sort, kế hoạch có thể khác hẳn so với chỉ equality.

Không thể quyết định chỉ bằng “field nào cardinality cao hơn”. Phải xem **nhóm truy vấn cần các tiền tố nào**.

## 7. Range đứng trước sort có thể phá thứ tự toàn cục

Index:

~~~text
(tenantId ASC, totalMinor ASC, createdAt DESC)
~~~

Dữ liệu trong T1 được nhóm theo tiền trước, rồi mới theo thời gian trong từng mức tiền:

~~~text
T1, 100000, 11:00
T1, 100000, 10:00
T1, 150000, 14:00
T1, 150000, 09:00
T1, 200000, 13:00
T1, 200000, 12:00
~~~

Khi query:

~~~javascript
db.orders.find({
  tenantId: "T1",
  totalMinor: { $gte: 100000, $lte: 200000 }
})
.sort({ createdAt: -1 });
~~~

nó muốn thứ tự toàn cục **14:00, 13:00, 12:00, 11:00, 10:00, 09:00**, nhưng index đang ưu tiên nhóm theo totalMinor. Engine có thể cần sort riêng hoặc chọn index khác.

**Range thường làm suy giảm khả năng dùng các field phía sau để cung cấp sort toàn cục**, trừ những trường hợp và tối ưu cụ thể. Không suy luận “field có trong index” thành “không cần sort”.

## 8. Thứ tự ASC/DESC trong compound index

Trong MongoDB, index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1,
  orderId: -1
});
~~~

có thể hỗ trợ sort theo:

~~~javascript
db.orders.find({ tenantId: "T1" })
  .sort({ createdAt: -1, orderId: -1 });
~~~

và có thể duyệt ngược để phục vụ thứ tự đảo chiều tương ứng. Nhưng query có hướng trộn:

~~~javascript
db.orders.find({ tenantId: "T1" })
  .sort({ createdAt: -1, orderId: 1 });
~~~

không tự tương đương pattern trên. Cần xem index có hướng hỗn hợp phù hợp:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1,
  orderId: 1
});
~~~

Một ordered index có thể **duyệt xuôi hoặc duyệt ngược**; nó không tự đổi chiều độc lập của từng thành phần theo ý muốn. Những field equality đứng trước sort cũng cần được cố định đúng cách.

### Cần tie-breaker để phân trang ổn định

Hai order có thể cùng thời điểm:

~~~text
2026-11-14T10:30:00.000Z -> O-101
2026-11-14T10:30:00.000Z -> O-102
~~~

Sort chỉ theo createdAt không xác định hoàn toàn thứ tự giữa hai order. Thêm **orderId** hoặc **_id** làm tie-breaker ổn định và duy nhất trong phạm vi kết quả:

~~~javascript
db.orders.find({ tenantId: "T1" })
  .sort({ createdAt: -1, orderId: -1 });
~~~

Thứ tự được định nghĩa trong API phải đồng bộ với index và cursor.

## 9. Sort theo hậu tố khi bỏ qua field giữa

Index:

~~~text
(tenantId, status, createdAt DESC)
~~~

Query:

~~~javascript
db.orders.find({ tenantId: "T1" })
  .sort({ createdAt: -1 });
~~~

Không thể mặc định index trả toàn bộ đơn T1 theo createdAt mới nhất vì nó được chia thành nhóm theo status:

~~~text
T1, CANCELLED, ...
T1, PAID, ...
T1, PENDING, ...
~~~

Để phục vụ timeline của **mọi status**, một candidate index khác là:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1
});
~~~

Quy tắc khái niệm: muốn sort theo tập field không đứng ngay đầu index, **các field đứng trước phần sort thường cần được cố định bằng equality** để phần còn lại có thứ tự liên tục.

## 10. Cardinality và selectivity khác nhau

**Cardinality** là số lượng giá trị khác nhau; **selectivity** là tỷ lệ dữ liệu được điều kiện giữ lại.

Ví dụ giả định 10 triệu order:

| Predicate | Số document khớp | Nhận xét |
| --- | ---: | --- |
| orderId = O-101 | 1 | Rất chọn lọc |
| customerId = C42 | 50 | Chọn lọc cao |
| tenantId = T1 | 300.000 | Tùy tenant |
| status = PAID | 8.000.000 | Chọn lọc thấp |
| createdAt trong một giờ | 15.000 | Phụ thuộc tốc độ ghi |
| tenantId=T1, status=PAID, createdAt gần nhất | Có thể vài trăm | Phụ thuộc phân bố kết hợp |

Đây chỉ là bộ số minh họa. Một trạng thái chỉ có ba giá trị nhưng có thể rất lệch. Trong tenant T1, PAID có thể chiếm 95%; trong T2 chỉ 10%. Planner và chiến lược index phải được đo trên dữ liệu có **skew/hot tenants**, không chỉ phân bố đều.

## 11. Covering index và chi phí FETCH document

Nếu query chỉ cần bốn field, một index có các field đó đôi khi giúp engine không phải đọc document nguồn.

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  orderId: -1,
  totalMinor: 1
});

db.orders.find(
  {
    tenantId: "T1",
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1,
    orderId: 1,
    totalMinor: 1
  }
)
.sort({ createdAt: -1, orderId: -1 })
.limit(20);
~~~

Nếu filter, sort và projection đều được index đáp ứng theo điều kiện MongoDB, query có thể là **covered query**; cần xem explain để biết có cần FETCH hay không. Đối với executionStats, một dấu hiệu là **totalDocsExamined = 0** trong trường hợp index-only phù hợp.

Nhưng không nên nhét toàn bộ payload vào index chỉ để tránh FETCH:

~~~text
shippingAddress
paymentDetails
items
largeDescription
notes
~~~

Index lớn hơn tốn disk, cache và write maintenance. Multikey, null, collation, _id và các điều kiện khác có thể ảnh hưởng khả năng cover. Đừng đánh giá chỉ bằng tên các field xuất hiện trong index.

## 12. Index intersection có thay compound index không?

Hai index đơn:

~~~javascript
db.orders.createIndex({ tenantId: 1 });
db.orders.createIndex({ status: 1 });
~~~

có thể giúp một số query:

~~~javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID"
});
~~~

Một optimizer có thể chọn một index rồi lọc field còn lại, hoặc đôi khi kết hợp các index nếu tính năng hỗ trợ và chi phí phù hợp.

Nhưng intersection **không tự tương đương**:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Compound index duy trì tổ hợp key và thứ tự trên cùng cấu trúc. Intersection có thể cần đọc/hợp nhất hai tập ứng viên và không tự cung cấp sort theo createdAt. Ngoài ra, planner có thể không chọn intersection dù tồn tại hai index.

**Kết luận:** không thay compound index quan trọng bằng hai index đơn chỉ dựa vào suy đoán; phải xem plan và đo.

## 13. Một index có thể phục vụ bao nhiêu query?

Giả sử hệ có:

~~~text
Q1: tenantId + status, sort createdAt DESC.
Q2: tenantId + customerId, sort createdAt DESC.
Q3: tenantId, sort createdAt DESC.
Q4: tenantId + orderId, lookup một đơn.
Q5: tenantId + totalMinor range, sort createdAt DESC.
~~~

Một số candidate:

~~~javascript
// Q1
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  orderId: -1
});

// Q2
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  orderId: -1
});

// Q3
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1,
  orderId: -1
});

// Q4
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);
~~~

Đây là **danh sách để xem xét**, không phải chỉ dẫn tạo mọi index. Nếu Q3 rất hiếm, chi phí SORT của nó có thể chấp nhận được; nếu Q3 là dashboard quan trọng, index riêng đáng giá hơn. Trước khi thêm index, phải biết **tần suất, cardinality, độ trễ đích và write cost**.

| Query | Equality | Range | Sort | Candidate |
| --- | --- | --- | --- | --- |
| Q1 | tenantId, status | Không | createdAt, orderId | tenantId/status/createdAt/orderId |
| Q2 | tenantId, customerId | Không | createdAt, orderId | tenantId/customerId/createdAt/orderId |
| Q3 | tenantId | Không | createdAt, orderId | tenantId/createdAt/orderId |
| Q4 | tenantId, orderId | Không | Không | unique tenantId/orderId |
| Q5 | tenantId | totalMinor | createdAt | So ESR với ERS |

## 14. Partial, sparse và unique index

Một **partial index** MongoDB chỉ chứa những document thỏa điều kiện khai báo:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    createdAt: -1,
    orderId: -1
  },
  {
    partialFilterExpression: {
      status: "PENDING"
    }
  }
);
~~~

Nếu PENDING là một phần nhỏ trong collection, index này có thể giảm dung lượng và phục vụ query hàng đợi. Nhưng nó không thể tự phục vụ query cần **đủ mọi trạng thái** vì index không chứa tất cả document.

**Sparse index** có ngữ nghĩa theo sự tồn tại field, khác partial index. **Unique index** bảo vệ tính duy nhất trong phạm vi key hoặc tập được index. Những thuộc tính index này không thể thay thế tùy ý cho nhau.

Ví dụ uniqueness username theo tenant:

~~~javascript
db.users.createIndex(
  {
    tenantId: 1,
    usernameNormalized: 1
  },
  {
    unique: true
  }
);
~~~

Cần định nghĩa **usernameNormalized** theo quy tắc Unicode/case-fold chính xác. Với unique index, phải kiểm tra missing/null, sparse/partial và dữ liệu lịch sử trước khi tạo; không mặc định các record thiếu field luôn được cho phép cùng tồn tại.

Khi đã có index bắt đầu bằng tenantId, một index đơn trên tenantId có thể đôi lúc bị dư thừa. Tuy nhiên, chỉ nên bỏ sau khi xem usage/plan và xác minh chúng không khác nhau về **unique, partial, sparse, collation** hoặc mục tiêu vận hành.

## 15. Array và multikey index

MongoDB có thể tạo **multikey index** khi field index là array:

~~~json
{
  "productId": "P-100",
  "tenantId": "T1",
  "tags": ["steel", "vacuum", "bottle"]
}
~~~

~~~javascript
db.products.createIndex({
  tenantId: 1,
  tags: 1
});
~~~

Multikey index có thể hỗ trợ truy vấn phần tử tags, nhưng nhiều giá trị có thể tạo nhiều index entry. Khi index nhiều field mảng, MongoDB có **ràng buộc compound multikey cụ thể**; không thể giả định mọi kết hợp hai array đều hợp lệ.

Một tình huống logic:

~~~json
{
  "variants": [
    { "color": "red", "size": "S" },
    { "color": "blue", "size": "L" }
  ]
}
~~~

Nếu yêu cầu tìm một variant vừa **red** vừa **size L**, không được để điều kiện red khớp phần tử đầu và L khớp phần tử sau. Dùng **$elemMatch** để diễn đạt ràng buộc cùng phần tử:

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "red",
      size: "L"
    }
  }
});
~~~

Compound multikey có thể ảnh hưởng sort, covering và index size; nên xem explain của chính query thật.

## 16. Collation, Unicode và kiểu dữ liệu ảnh hưởng thứ tự

Một index sắp xếp string theo quy tắc so sánh của database và collation. Ví dụ:

~~~text
"An"
"an"
"Án"
"Anh"
~~~

Thứ tự và equality có thể khác theo locale, case sensitivity và accent sensitivity. Nếu query dùng collation không tương thích với index, hiệu quả filter/sort có thể thay đổi.

Những điều cần thống nhất:

- Field là string hay number? **"100"** và **100** không có cùng thứ tự/kiểu.
- Date lưu ở dạng Date hay chuỗi? String timestamp có nhiều timezone/precision khác nhau có thể sort sai.
- Có normalize Unicode trước khi lưu username/key không?
- Null, missing và mixed types có được phép không?
- Truy vấn và index có cùng collation không?
- Khi đổi schema hoặc collation, có cần rebuild index không?

Đừng dùng một index trên chuỗi ngày tháng không được chuẩn hóa rồi giả định thứ tự thời gian luôn đúng.

## 17. Index và keyset pagination

API lấy 20 đơn mới nhất theo tenant/status:

~~~javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID"
})
.sort({
  createdAt: -1,
  orderId: -1
})
.limit(20);
~~~

Index có thể là:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  orderId: -1
});
~~~

Cursor chứa **lastCreatedAt** và **lastOrderId** của record cuối trang. Trang kế có thể dùng điều kiện:

~~~javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID",
  $or: [
    {
      createdAt: {
        $lt: new Date("2026-11-14T10:30:00Z")
      }
    },
    {
      createdAt: new Date("2026-11-14T10:30:00Z"),
      orderId: { $lt: "O-9001" }
    }
  ]
})
.sort({
  createdAt: -1,
  orderId: -1
})
.limit(20);
~~~

Đây là minh họa keyset pagination; điều kiện OR và index phải được đo bằng explain. Nếu orderId là kiểu khác string, so sánh phải theo kiểu thực.

Với **OFFSET/SKIP** rất sâu, engine có thể phải đi qua nhiều index entry chỉ để bỏ chúng; ngoài ra insert/delete giữa các trang có thể làm vị trí lệch. Keyset giảm vấn đề đó nhưng **không tự tạo snapshot nhất quán** cho toàn bộ chuỗi request. Cursor cần được ký/kiểm tra để không thay đổi tenant và điều kiện sort trái phép.

## 18. Multi-tenancy và giới hạn của index

Trong hệ nhiều tenant, phần lớn query nên có tenantId từ thông tin đã xác thực:

~~~text
tenantId + orderId
tenantId + customerId + createdAt
tenantId + status + createdAt
tenantId + categoryId + price
~~~

Một compound index bắt đầu bằng tenantId có thể là lựa chọn tốt vì nhiều query dùng cùng tiền tố. Nhưng **đặt tenantId vào index không tự cung cấp authorization**; backend phải xác minh caller có quyền trên tenant đó.

Cũng cần chú ý:

- Một tenant lớn có thể chiếm phần lớn index entries/traffic.
- Query quản trị toàn hệ có thể không biết tenantId và cần đường khác.
- Uniqueness có thể theo tenant hoặc toàn hệ, phải nêu rõ.
- Shard key không nhất thiết chính là compound index key.
- Index tốt bên trong shard không loại bỏ network fan-out nếu query phải tới nhiều shard.

Đừng nhầm **đường truy cập logic** với **phân phối vật lý**.

## 19. DynamoDB: PK/SK không phải compound B-tree index MongoDB

DynamoDB sử dụng **partition key PK** và tùy chọn **sort key SK**. Nó không cho tự khai báo tùy ý compound B-tree index nhiều field như MongoDB.

Ví dụ:

~~~text
PK = TENANT#T1#CUSTOMER#C42
SK = ORDER#2026-11-14T10:30:00Z#O-9001

status = PAID
totalMinor = 250000
~~~

Query:

~~~text
KeyConditionExpression:
    PK = TENANT#T1#CUSTOMER#C42
    AND begins_with(SK, ORDER#)

ScanIndexForward = false
Limit = 20
~~~

Các nguyên tắc:

1. Query cần equality trên **partition key** của bảng hoặc index được truy cập.
2. Có thể thêm điều kiện trên sort key theo toán tử được hỗ trợ: equality, prefix, range...
3. Thứ tự trong cùng partition theo SK; **ScanIndexForward** quyết định chiều duyệt.
4. **FilterExpression** lọc sau khi đọc theo key condition, không làm phần filter ngoài khóa trở thành index seek.
5. LIMIT không đồng nghĩa chắc chắn có đủ số dòng sau filter; cần xử lý **LastEvaluatedKey**.
6. Query nhiều partition không tự có sort toàn cục.

### Ghép nhiều thành phần vào SK

~~~text
SK = STATUS#PAID#DATE#2026-11-14T10:30:00Z#ORDER#O-9001
~~~

Thứ tự thành phần trong chuỗi SK quyết định khả năng query prefix:

- **STATUS trước DATE** thuận lợi khi biết status rồi lấy theo thời gian.
- **DATE trước STATUS** thuận lợi cho phạm vi theo thời gian nhưng không tự tìm liên tục mọi item của một status.
- Format ngày, timezone, chiều sort và tie-breaker phải nhất quán với **lexicographical order** của key.

Đây là tương đồng về **tư duy tiền tố**, không phải cùng cơ chế với MongoDB compound index.

## 20. DynamoDB: GSI, LSI, projection và consistency

Nếu PK gốc phục vụ lookup theo orderId:

~~~text
PK = TENANT#T1#ORDER#O-9001
SK = META

GSI1PK = TENANT#T1#CUSTOMER#C42
GSI1SK = ORDER#2026-11-14T10:30:00Z#O-9001
~~~

Một **GSI** theo GSI1PK/GSI1SK cung cấp đường query lịch sử khách. Nhưng GSI có chi phí dung lượng/write và cập nhật **bất đồng bộ**. Query trên GSI sử dụng **eventually consistent reads**, không có strong consistent read trên GSI.

| Cấu trúc | Vai trò | Đánh đổi |
| --- | --- | --- |
| Primary PK/SK | Exact lookup và Query theo khóa chính | Không query tùy ý field ngoài khóa |
| GSI | Truy cập theo khóa thay thế | Write/storage overhead; cập nhật async |
| LSI | Đường sort khác trong phạm vi partition key của bảng | Giới hạn/vòng đời khác GSI |
| Projection | Những field sẵn có ở index | Tăng index size hoặc cần đường đọc khác |
| FilterExpression | Lọc thêm sau truy cập theo key | Không giảm toàn bộ read cost như key condition |
| Scan | Duyệt không có key condition | Thường không phù hợp API tần suất cao |

Không tự tạo GSI partition key **STATUS#PAID** cho mọi tenant nếu nó làm dồn tải vào một khóa nóng. Cần phân tích tenant/store/bucket thời gian.

DynamoDB dùng **một SK** với chiều quét xuôi/ngược; không thể khai báo hướng ASC/DESC độc lập cho nhiều thành phần logic trong SK như compound MongoDB. Nếu yêu cầu sort hỗn hợp, phải thiết kế encoding hoặc read model phù hợp.

## 21. Cassandra/ScyllaDB: partition và clustering key

Trong CQL:

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id text,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_minor bigint,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Query:

~~~sql
SELECT created_at, order_id, status, total_minor
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
~~~

Ý nghĩa:

- **(tenant_id, customer_id, month_bucket)** là composite partition key: định vị partition.
- **created_at** là clustering column đầu: sắp theo thời gian trong partition.
- **order_id** là clustering column tiếp: thứ tự ổn định khi trùng timestamp.
- **CLUSTERING ORDER BY** quy định chiều thứ tự theo clustering columns.
- Đọc lịch sử vượt một tháng có thể cần nhiều partition và merge/pagination ở tầng ứng dụng.

### Quy tắc prefix trong clustering

Một điều kiện range trên **created_at** trong một partition đã định vị có thể là đường truy cập hợp lý:

~~~sql
SELECT created_at, order_id, status
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at >= ?
LIMIT 50;
~~~

Nếu query muốn lọc chỉ **status=PAID** cho toàn hệ, bảng theo customer/month này không tự hỗ trợ vì thiếu đường định vị. Cần **bảng theo access pattern**, secondary index phù hợp hoặc search/read model.

CQL có quy tắc riêng cho equality, IN, range và ORDER BY theo phiên bản. **Cassandra/ScyllaDB secondary index hoặc SAI không thể coi hệt MongoDB compound B-tree.** Một số tính năng index/optimizer khác nhau giữa sản phẩm và phiên bản, cần xem tài liệu cụ thể.

## 22. Redis: key pattern và sorted set

Redis không có compound collection B-tree index tự động cho mọi hash field. Đường truy cập thường được thiết kế bằng **key name** hoặc cấu trúc phụ:

~~~text
order:T1:O-9001             -> Hash/String chi tiết.
orders-by-customer:T1:C42  -> Sorted set order IDs.
orders-by-status:T1:PAID   -> Sorted set hoặc Set.
~~~

Ví dụ:

~~~redis
ZADD orders-by-customer:T1:C42 1763000000 O-9001
ZREVRANGE orders-by-customer:T1:C42 0 19
~~~

Score chỉ minh họa; không khẳng định giá trị đó trùng timestamp cụ thể. Khi score trùng nhau, Redis áp dụng quy tắc thứ tự member; nếu cần sort đa chiều ổn định, phải thiết kế member/score hoặc phương pháp phân trang tương ứng.

Các vấn đề:

- Sorted set phải được cập nhật khi item nguồn thêm/xóa/đổi trường.
- Một key tổng toàn hệ có thể thành hot key rất lớn.
- TTL và read model phụ không tự đồng bộ với source.
- Dùng **KEYS order:\*** làm query thường xuyên dễ gây vấn đề tải.
- Set/ZSET intersection không tự tương đương compound B-tree index về sort và chi phí.

**Tư duy chung là thiết kế cấu trúc cho access pattern**, không áp luật ESR trực tiếp lên mọi Redis key.

## 23. Search engine: inverted index khác ordered compound index

Trong Elasticsearch/OpenSearch, những field như category, status và brand có thể được tra cứu bằng **inverted index**. Các filter được kết hợp qua các tập document, không nhất thiết cần index theo khóa ghép **(category, brand, price)** giống MongoDB.

~~~text
category=drinkware -> document IDs
brand=alpha        -> document IDs
price 100..250     -> document IDs trong range
~~~

Tuy nhiên, sort theo price, date hoặc relevance có chi phí riêng. Cần xem mapping, doc values, index sorting, phân bố shard và các kiểu pagination như search_after theo khả năng sản phẩm. Với full-text, cách analyzer/tokenization còn khác equality trên keyword.

Index tìm kiếm thường là **bản chiếu cập nhật có độ trễ** từ nguồn. Không nên dùng một kết quả search đã lọc để quyết định uniqueness, tồn kho hay quyền giao dịch khi nó không cung cấp consistency cần thiết.

## 24. Các kiểu index không thay thế được nhau

| Kiểu index/cấu trúc | Thường phù hợp | Không mặc định phù hợp |
| --- | --- | --- |
| Ordered B-tree | Equality, range, sort theo key | Mọi tổ hợp sort/filter |
| Hashed | Equality/định tuyến theo hash | Range sort theo giá trị gốc |
| Inverted/text | Token, keyword, full-text | Leftmost-prefix B-tree |
| Geospatial | Khoảng cách/vùng địa lý | Sort tùy ý các trường khác |
| Multikey | Array membership | Mọi sort/cover như scalar |
| Partial | Query nằm trong tập document có điều kiện | Query cần cả tập ngoài filter |
| Unique | Ràng buộc duy nhất theo key | Bất biến xuyên nhiều record |
| TTL/expiration | Quản lý vòng đời | Là chỉ mục sort đa chiều tổng quát |
| Sorted set | Thứ tự theo score/member | Query ad hoc theo nhiều thuộc tính |

Trước khi chọn index, xác định **engine thật đang tổ chức key ra sao**, không suy từ tên gọi chung.

## 25. Explain: bằng chứng thay vì suy đoán

Với MongoDB:

~~~javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID",
  createdAt: {
    $gte: new Date("2026-11-01T00:00:00Z")
  }
})
.sort({
  createdAt: -1,
  orderId: -1
})
.limit(20)
.explain("executionStats");
~~~

Cần quan sát:

| Metric/operator | Câu hỏi |
| --- | --- |
| **IXSCAN/indexName** | Index nào được chọn? |
| **indexBounds** | Điều kiện có khoanh vùng key hiệu quả? |
| **COLLSCAN** | Có quét toàn collection không? |
| **FETCH** | Có đọc document nguồn? |
| **SORT** | Có sort ngoài index? Bao nhiêu dữ liệu? |
| **nReturned** | Trả mấy record? |
| **totalKeysExamined** | Đã xét bao nhiêu index entry? |
| **totalDocsExamined** | Đã đọc bao nhiêu document nguồn? |
| **executionTimeMillis** | Độ trễ của lần đo với môi trường hiện tại? |

Ví dụ minh họa:

~~~text
Query A:
    nReturned = 20
    totalKeysExamined = 45
    totalDocsExamined = 20

Query B:
    nReturned = 20
    totalKeysExamined = 850000
    totalDocsExamined = 180000
~~~

Cùng trả 20 dòng nhưng chi phí truy cập có thể chênh rất lớn. Đừng chỉ nhìn một lần executionTimeMillis trên cache nóng; hãy đo plan và p95/p99 trên workload đủ lớn, có ghi đồng thời.

## 26. Nhiều index làm tăng write amplification

Khi insert hoặc update một document, engine phải duy trì những index có liên quan. Index nhiều field, multikey index hoặc nhiều cấu trúc phụ có thể tăng:

- Disk, RAM/page cache và metadata.
- CPU cho insert/update/delete.
- Số entry cần thêm/xóa khi status hoặc category thay đổi.
- Replication và hoạt động nền/compaction tùy engine.
- Thời gian build/rebuild index.
- Chi phí backup, vận hành và migration.

Ví dụ giả định:

~~~text
10 triệu order
Một index entry logic ~80 byte

Một index:
    10.000.000 * 80 byte ~= 763 MiB payload logic

Năm index tương tự:
    ~= 3,73 GiB payload logic
~~~

Đây **không phải dung lượng vật lý thực tế**, vì còn compression, index structure, multikey fan-out, replication và overhead khác.

Một index ít được truy vấn có thể vẫn tốn tài nguyên ghi. Nhưng **không xóa index chỉ vì usage thấp**: nó có thể phục vụ một job hiếm nhưng thiết yếu hoặc unique constraint.

## 27. Index key khác shard key

Trong cluster phân tán:

~~~text
Client query
    |
    v
Query router
   / | \
Shard1 Shard2 Shard3
   \ | /
 Merge / sort / limit
~~~

Một compound index có thể hỗ trợ tìm/sort rất tốt **bên trong shard**, nhưng nếu query không có shard key phù hợp, nó vẫn có thể phải đến nhiều shard. Chi phí network và merge có thể chi phối.

Phân biệt:

- **Index key:** sắp xếp/định vị entry để phục vụ query.
- **Shard/partition key:** quyết định dữ liệu phân tán vật lý.
- **Query predicate:** có đủ thông tin định tuyến hẹp không?
- **Global order:** lấy top-N giữa nhiều shard cần cách merge phù hợp.

Với DynamoDB/Cassandra, partition key là một phần trực tiếp của đường truy cập. Với MongoDB sharded cluster, shard key và secondary compound index có thể là hai thiết kế khác nhau. Một query tối ưu local vẫn có thể chậm nếu scatter-gather.

## 28. Benchmark so sánh index theo workload

Giả sử dữ liệu thử có 10 triệu order, một số tenant rất lớn và status PAID chiếm nhiều. Bộ test nên có:

| Test | Query | Điều cần xác minh |
| --- | --- | --- |
| A | Lookup tenant + orderId | Exact lookup và uniqueness |
| B | tenant + status + sort time | ESR và prefix |
| C | tenant + sort time, thiếu status | Có index timeline phù hợp? |
| D | tenant + total range + sort time | ESR so với ERS |
| E | customer history, cursor nhiều trang | Thứ tự và độ trễ |
| F | status hiếm và phổ biến | Khác biệt selectivity |
| G | Insert/update hỗn hợp | Write amplification |
| H | Tenant cực lớn | Hot key/shard và p99 |
| I | Index build khi có traffic | Chi phí vận hành |
| J | Drop/rebuild có rollback | Tính liên tục dịch vụ |

Metric cần có:

~~~text
query_latency_p50/p95/p99
offered_rps
successful_rps
timeout_ratio
keys_examined
docs_examined
rows_returned
sort_stage_memory
index_size_bytes
index_cache_hit_ratio
write_latency
shard_fanout
hot_partition_utilization
index_build_duration
~~~

Các số đo phải gắn với **dataset, query shape, topology, version và load**. Một index “nhanh hơn trong demo” chưa đủ để chốt sản phẩm.

## 29. Ma trận nghiệm thu minh họa

| Mã | Tiêu chí | Bằng chứng |
| --- | --- | --- |
| AC-01 | Lookup trả đúng record và tenant | Test với auth + query |
| AC-02 | Thứ tự createdAt/orderId ổn định | Test dữ liệu trùng timestamp |
| AC-03 | Query quan trọng p95 trong SLO | Load test end-to-end |
| AC-04 | Keys examined nằm trong ngân sách | Explain trên nhiều nhóm tenant |
| AC-05 | Query yêu cầu index sort không có SORT lớn ngoài dự kiến | Explain/operator metric |
| AC-06 | Read/write latency đạt dưới workload hỗn hợp | Test đồng thời |
| AC-07 | Index size và build cost trong ngân sách | Storage/build benchmark |
| AC-08 | Hot tenant không gây mất ổn định toàn hệ | Stress key-skew |
| AC-09 | Unique constraint hoạt động khi ghi đồng thời | Concurrent insert |
| AC-10 | Index rollout/rebuild không gây mất dữ liệu | Migration + rollback drill |

Các ngưỡng cụ thể phải được dự án phê duyệt. Không coi bảng này là benchmark thực tế.

## 30. Quy trình lựa chọn index

~~~mermaid
flowchart TD
    A[Liệt kê query và tần suất] --> B[Phân loại equality, range, sort, limit]
    B --> C[Chọn database và access path]
    C --> D{Ordered compound index?}
    D -->|Có| E[Prefix, ESR/ERS, hướng sort]
    D -->|Không| F[PK/SK, index phụ hoặc read model]
    E --> G[Đo selectivity, skew, multikey, collation]
    F --> G
    G --> H[Explain/tracing trên dữ liệu đại diện]
    H --> I[Benchmark đọc và ghi hỗn hợp]
    I --> J{Đạt correctness, latency và chi phí?}
    J -->|Không| K[Điều chỉnh index hoặc data model]
    K --> H
    J -->|Có| L[Rollout, monitor và ghi hợp đồng]
~~~

Trình tự thực hành:

1. **Viết query đầy đủ:** input, filter, range, sort, projection, limit và cursor.
2. **Nhóm các access pattern:** query nào có thể dùng chung index?
3. **Xác định sản phẩm:** MongoDB ordered index, DynamoDB PK/SK/GSI, CQL partition/clustering, Redis hay search.
4. **Chọn thứ tự:** equality prefix, sort và range theo ứng viên ESR/ERS.
5. **Kiểm tra case đặc biệt:** null/missing, unique, partial, multikey, collation, hot tenant.
6. **Đọc plan:** index bounds, scan, sort, fetch, shard fan-out.
7. **Đo load:** p95/p99, throughput, tài nguyên, write amplification.
8. **Rollout:** build index theo khả năng sản phẩm, theo dõi và giữ đường rollback.
9. **Theo dõi lâu dài:** khi dataset và query shape thay đổi, tối ưu cũ có thể không còn hợp lý.

## 31. Bài tập: thiết kế index cho catalog sản phẩm

Cho document:

~~~json
{
  "productId": "P-100",
  "tenantId": "T1",
  "categoryId": "drinkware",
  "brandId": "B12",
  "status": "ACTIVE",
  "priceMinor": 125000,
  "ratingAverage": 4.6,
  "createdAt": "2026-11-14T10:30:00Z",
  "tags": ["steel", "vacuum"]
}
~~~

Các query:

~~~text
Q1: lookup sản phẩm theo tenantId + productId.
Q2: tenant + category, sort price ASC.
Q3: tenant + status ACTIVE, sort createdAt DESC.
Q4: tenant + category + price range, sort rating DESC.
Q5: tenant + tags chứa steel.
Q6: tenant + brand, sort createdAt DESC.
~~~

### Nhiệm vụ A — Đề xuất candidate index cho Q2

~~~javascript
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  priceMinor: 1,
  productId: 1
});
~~~

Giải thích vì sao equality tenant/category đứng trước, price dùng sort và productId làm tie-breaker. Xác định query nào dùng được index này khi thiếu category.

### Nhiệm vụ B — So ESR và ERS cho Q4

~~~javascript
// A: sort rating trước range price.
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  ratingAverage: -1,
  productId: 1,
  priceMinor: 1
});

// B: range price trước sort rating.
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  priceMinor: 1,
  ratingAverage: -1,
  productId: 1
});
~~~

Nếu khoảng giá rộng, A có thể thuận lợi hơn để trả kết quả theo rating. Nếu khoảng giá rất hẹp, B có thể giảm ứng viên rồi sort. Kiểm chứng bằng explain và benchmark.

### Nhiệm vụ C — Chọn đường cho Q3/Q5

~~~javascript
db.products.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  productId: -1
});

db.products.createIndex({
  tenantId: 1,
  tags: 1
});
~~~

Thảo luận multikey, chi phí cập nhật tags, khả năng sort và cách tránh thêm nhiều index dư thừa.

### Nhiệm vụ D — Đo

Với tenant lớn và nhỏ, ghi lại:

- nReturned / totalKeysExamined / totalDocsExamined;
- Có SORT/FETCH không;
- p95/p99 của mỗi query;
- Index storage, throughput ghi và cost cập nhật field;
- Kết quả khi có 20 sản phẩm trùng price hoặc createdAt;
- Khả năng phân trang không lặp/bỏ sót theo hợp đồng.

## 32. Những sai lầm thường gặp

**“Query có ba field thì tạo index theo thứ tự chúng xuất hiện trong request.”** Thứ tự JSON filter không phải quy tắc chọn compound index. Phải xét equality, sort, range và workload.

**“Field chọn lọc nhất luôn phải đứng đầu.”** Không tuyệt đối; tiền tố query, sort và tái sử dụng index cũng quan trọng.

**“Index (A,B,C) tốt như nhau cho B,C.”** Không có leading prefix để seek phạm vi theo B,C hiệu quả.

**“Có index đơn cho mọi field thì tương đương compound index.”** Intersection không tự cho thứ tự sort và có chi phí riêng.

**“Range đứng trước sort vẫn đảm bảo kết quả đã sắp xếp.”** Không mặc định khi range trải nhiều giá trị.

**“Đặt DESC nghĩa là không thể đọc ASC.”** Duyệt ngược có thể đảo hướng tương ứng; sort trộn nhiều field cần pattern phù hợp.

**“LIMIT 20 nghĩa là engine chỉ đọc 20 entry.”** Nếu filter/sort không phù hợp, có thể đọc rất nhiều rồi mới trả 20.

**“Tên field có trong index là covered query.”** Còn phụ thuộc projection, multikey, _id và engine.

**“Unique index bảo vệ mọi bất biến.”** Nó bảo vệ uniqueness theo khóa, không tự bảo vệ tồn kho hay transaction nhiều bản ghi.

**“Mọi NoSQL có compound B-tree như MongoDB.”** DynamoDB, Cassandra, Redis và search index có cơ chế khác nhau.

**“Index càng nhiều càng tốt.”** Mỗi index có chi phí storage, write và vận hành.

**“Query nhanh trong dataset nhỏ là đã tối ưu.”** Phải đo key skew, tải ghi song song và p99 ở dữ liệu đại diện.

## Kết luận

**Chỉ mục đơn** phù hợp khi query truy cập theo một field có chọn lọc và không cần sort phức tạp. **Chỉ mục ghép** tổ chức nhiều field theo thứ tự xác định, giúp phục vụ những query **lọc, sắp xếp, giới hạn và phân trang**. Trên ordered compound index, **quy tắc tiền tố trái** chỉ ra những điều kiện có thể khoanh vùng key thuận lợi; **Equality–Sort–Range (ESR)** gợi ý cách đặt field, nhưng luôn cần so sánh với ERS khi range rất chọn lọc.

Trong NoSQL, điều quan trọng nhất là **không áp một quy tắc chỉ mục cho mọi công nghệ**: MongoDB có compound index có thứ tự; DynamoDB dùng PK/SK/GSI; Cassandra/ScyllaDB dùng partition và clustering key; Redis dựa trên key/structure phụ; search engine dựa trên inverted index và thuật toán khác.

Quy trình đáng tin cậy là **liệt kê query trước, chọn đường truy cập theo equality/range/sort, kiểm tra explain, đo dữ liệu lớn và tải hỗn hợp, rồi mới chốt thứ tự các thành phần**. Một chỉ mục tốt không chỉ làm query nhanh hơn; nó phải làm đúng dữ liệu và thứ tự đã cam kết trong giới hạn chi phí đọc/ghi/vận hành được chấp thuận.
