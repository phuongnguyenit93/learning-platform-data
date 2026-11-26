# Estimated Rows, Rows, DB Hits và giới hạn diễn giải số liệu trong kế hoạch thực thi Neo4j

## 1. Tại sao cần đọc các chỉ số của execution plan?

Neo4j sử dụng **property graph** gồm node, relationship và thuộc tính; Cypher mô tả *cần tìm dữ liệu gì*, còn **query planner** quyết định *đi qua graph bằng cách nào*. Cùng một truy vấn có thể được thực thi bằng cách quét label, tra cứu index, duyệt relationship theo hướng xác định hoặc kết hợp nhiều operator.

Ví dụ ứng dụng bán hàng muốn tìm những sản phẩm đã mua của một khách hàng:

```cypher
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku, p.price;
```

Truy vấn đúng kết quả vẫn có thể chậm nếu planner bắt đầu từ quá nhiều node, mở rộng relationship quá rộng hoặc phải sắp xếp số lượng dòng lớn. Kế hoạch thực thi cung cấp các dấu hiệu để trả lời:

- **`Estimated Rows`**: Neo4j *ước lượng* mỗi operator sẽ sinh bao nhiêu dòng khi lập kế hoạch?
- **`Rows`**: Operator *thực sự* sinh bao nhiêu dòng trong lần chạy vừa đo?
- **`DB Hits`**: Operator thực hiện bao nhiêu đơn vị thao tác truy cập cơ sở dữ liệu?

Ba số này có liên quan nhưng **không thay thế được nhau**. Đặc biệt, chúng không phải thước đo trực tiếp của thời gian phản hồi người dùng, số node trong database hay số lượt đọc đĩa.

Mục tiêu của bài thuộc chương **Kế hoạch thực thi** là biết cách đọc ba chỉ số trong `EXPLAIN`/`PROFILE`, xác định vị trí tăng dòng hoặc phát sinh truy cập lớn, và tránh kết luận sai khi tối ưu Cypher, index, constraint, truy vấn quan hệ, Java Driver hoặc Spring Data Neo4j.

## 2. `EXPLAIN` và `PROFILE`: xem kế hoạch trước hay đo sau?

Neo4j tạo execution plan từ truy vấn Cypher và các thông tin có sẵn, như label/type, index, constraint và thống kê phân bố dữ liệu.

| Lệnh | Có chạy truy vấn? | Nhìn thấy gì? | Khi nào dùng? |
| --- | --- | --- | --- |
| `EXPLAIN` | **Không** thực thi truy vấn | Cấu trúc operator, `Estimated Rows`, hướng truy cập dữ liệu | Xem nhanh chiến lược planner trước khi chạy truy vấn nặng |
| `PROFILE` | **Có** thực thi truy vấn | Cấu trúc plan và số đo như `Rows`, `DB Hits`, đôi khi thời gian, bộ nhớ, page cache | Đo truy vấn đọc an toàn trên bộ dữ liệu đại diện |

```cypher
EXPLAIN
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku, p.price;
```

```cypher
PROFILE
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku, p.price;
```

**Cảnh báo về `PROFILE`:** đây là truy vấn **thực thi thật**, không phải mô phỏng. Nếu đưa `PROFILE` trước `CREATE`, `MERGE`, `DELETE` hoặc `SET`, Neo4j vẫn thực hiện các thao tác ghi. Để xem trước câu lệnh ghi mà không sửa graph, dùng `EXPLAIN`. Bản thân việc profiling cũng có overhead nên chỉ đo khi có mục tiêu cụ thể.

## 3. Kế hoạch thực thi có cấu trúc như thế nào?

Một execution plan thường gồm:

1. **Header:** thông tin phiên bản Cypher, planner, runtime và đôi khi kích thước batch.
2. **Cây operator:** từng bước tìm node/relationship, lọc, kết hợp, tổng hợp, sắp xếp và trả kết quả.
3. **Footer:** tổng truy cập database, các chỉ số tổng khác nếu runtime cung cấp.

Một số operator thường gặp:

| Operator | Vai trò thường gặp | Cần chú ý |
| --- | --- | --- |
| `NodeByLabelScan` | Quét node theo label | Có thể hợp lý trên label ít node, tốn kém nếu quét hàng triệu node không cần thiết |
| `NodeIndexSeek` | Tìm node bằng index | Kiểm tra predicate, tính chọn lọc, `Rows` và `DB Hits` thực tế |
| `Expand(All)` | Đi theo các relationship từ node đầu vào | Một node có nhiều quan hệ có thể sinh rất nhiều dòng |
| `Expand(Into)` | Kiểm tra/kết nối các node đã được ràng buộc | Có thể phát sinh nhiều thao tác kiểm tra quan hệ |
| `Filter` | Loại dòng không thỏa điều kiện | Nếu rất nhiều dòng bị loại, hãy xem có thể chọn lọc sớm hơn không |
| `CartesianProduct` | Ghép từng dòng của hai tập đầu vào độc lập | Rất dễ làm số dòng nhân lên theo tích hai tập |
| `EagerAggregation` | Gom nhóm hoặc đếm | Đầu ra có thể chỉ vài dòng dù đã đọc hàng triệu dòng |
| `Sort` hoặc `Top` | Sắp xếp hoặc chọn các phần tử đầu | Cần xem bộ nhớ, lượng dòng và khả năng tận dụng thứ tự từ index |
| `ProduceResults` | Trả dòng kết quả cho client | Số dòng tại đây có thể khác xa số dòng được xử lý ở các operator phía dưới |

**Plan là một cây**, không phải nhật ký từng câu lệnh tuần tự của một thread. Thường đọc luồng dữ liệu từ các operator truy cập ở phía dưới lên operator trả kết quả ở phía trên, đồng thời quan sát các nhánh `Apply`, `Join` hoặc `CartesianProduct`. Neo4j có thể sử dụng pipelined/parallel runtime và ghép nhiều operator thành một pipeline.

### Mẫu bảng minh họa

Bảng dưới đây **hoàn toàn giả định để tập đọc chỉ số**, không phải kết quả đo từ một phiên bản Neo4j cụ thể:

| Operator | Estimated Rows | Rows | DB Hits |
| --- | ---: | ---: | ---: |
| `ProduceResults` | 10 | 6 | 0 |
| `Filter` | 10 | 6 | 0 |
| `Expand(All)` | 15 | 400 | 1.200 |
| `NodeIndexSeek` | 1 | 1 | 3 |

Từ bảng minh họa có thể nhận xét: planner dự kiến `Expand(All)` sinh 15 dòng nhưng thực tế là 400, rồi `Filter` chỉ giữ 6 dòng; chi phí mở rộng quan hệ đã xảy ra trước khi loại bỏ phần lớn kết quả. **Không** lấy các số trong bảng làm giá trị chuẩn cho một loại operator; một plan thực tế sẽ phụ thuộc data, phiên bản và runtime.

## 4. `Estimated Rows`: dự đoán số dòng của planner

### 4.1. Khái niệm và nguồn gốc

`Estimated Rows` là **số dòng ước lượng mà một operator sẽ xuất ra**. Planner dùng nó để đánh giá nhiều chiến lược và chọn plan có chi phí dự kiến hợp lý.

Ước lượng thường dựa trên:

- Số node theo label, số relationship theo type và mô hình phân bố liên kết.
- Thống kê index, ví dụ độ chọn lọc của một thuộc tính.
- Mô hình xác suất/selectivity cho điều kiện `WHERE`.
- Giả định khi kết hợp nhiều nhánh pattern, đặc biệt nếu các thuộc tính hoặc cấu trúc graph có tương quan mạnh.

**Estimated Rows không phải số đo tại thời điểm chạy.** Nó không được tự động sửa thành `Rows` chỉ vì Neo4j đã thấy các dòng thực tế trong một lần `PROFILE`.

### 4.2. Vì sao ước lượng có thể sai?

Giả sử một graph mạng xã hội có 99% người dùng chỉ theo dõi vài tài khoản, nhưng 1% tài khoản phổ biến có hàng triệu follower. Nếu planner dựa trên phân bố trung bình, nó có thể dự đoán sai số dòng khi truy vấn rơi vào tài khoản đặc biệt nổi tiếng.

Các nguyên nhân phổ biến:

- **Phân bố lệch (skew):** node có bậc quan hệ cao hơn phần lớn các node khác.
- **Tương quan dữ liệu:** `city = 'HCM'` và `country = 'VN'` không độc lập; mô hình ước lượng có thể không biểu diễn chính xác tương quan này.
- **Thống kê chưa phản ánh biến động gần đây:** sau đợt import, xóa hoặc đổi nhãn lớn.
- **Tham số khác nhau:** cùng một truy vấn nhưng `customerId` chỉ đến người ít đơn hàng hoặc khách có hàng triệu đơn hàng.
- **Pattern phức tạp:** nhiều chiều mở rộng, `OPTIONAL MATCH`, đường đi biến độ dài, phép join, aggregation.
- **Kế hoạch được cache:** truy vấn có thể dùng lại plan đã tạo trước thay vì lập lại ngay với thống kê mới.

Một ước lượng thấp hơn thực tế có thể làm planner chọn cách duyệt hoặc join không phù hợp. Nhưng **sai lệch chưa chứng minh truy vấn chậm**; cần đối chiếu `DB Hits`, thời gian và tài nguyên.

### 4.3. Đo sai lệch `Estimated Rows` so với `Rows`

Với cùng một operator, có thể đặt:

\[
\text{Hệ số sai lệch} =
\frac{\max(\text{Estimated Rows},\ \text{Rows})}
{\max(1,\min(\text{Estimated Rows},\ \text{Rows}))}
\]

Đây **chỉ là chỉ số hỗ trợ chẩn đoán** do người phân tích tự tính, không phải metric chính thức do Neo4j báo cáo. Nếu ước lượng là 20 nhưng thực tế 2.000 dòng, sai lệch tương ứng **100 lần**. Nên ưu tiên xem **vị trí operator đầu tiên có sai lệch lớn**, thay vì chỉ so ở `ProduceResults`.

Nếu `Estimated Rows = 0` hoặc `Rows = 0`, tỉ số có thể mất ý nghĩa, đặc biệt với các operator có ước lượng rất nhỏ. Cần xét trực tiếp số tuyệt đối và ý nghĩa của nhánh dữ liệu; không coi một phép chia là bằng chứng hiệu năng.

## 5. `Rows`: dòng chảy qua operator, không phải số node

`Rows` chỉ xuất hiện khi `PROFILE` và ghi nhận **số dòng mà operator đã tạo ra trong lần thực thi đó**. Một dòng có thể chứa:

- Một biến node: `{c}`.
- Một cặp node: `{c, p}`.
- Một relationship hoặc đường đi: `{c, r, p}`.
- Một giá trị tổng hợp: `{customerId, purchaseCount}`.

Ví dụ Cypher **không cần truy cập graph** vẫn có thể tạo nhiều dòng:

```cypher
PROFILE
UNWIND [1, 2, 3] AS number
UNWIND ['A', 'B'] AS letter
RETURN number, letter;
```

`UNWIND` thứ nhất tạo 3 dòng; mỗi dòng được `UNWIND` thứ hai mở rộng thành 2 dòng, nên kết quả cuối có **6 dòng**. `Rows` tăng ở bước tạo dòng, dù không có 6 node hay 6 lần đọc đĩa.

Ngược lại:

```cypher
PROFILE
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN count(*) AS purchaseCount;
```

Kết quả cuối chỉ có **một dòng chứa tổng số pattern phù hợp**; các operator đọc và duyệt graph bên dưới vẫn có thể xử lý rất nhiều dòng. Vì vậy, **`Rows = 1` ở `ProduceResults` không đồng nghĩa truy vấn chỉ xử lý một bản ghi**.

### Các tình huống làm `Rows` tăng hoặc giảm

| Mẫu truy vấn/operator | Tác động có thể quan sát | Lưu ý |
| --- | --- | --- |
| `Expand(All)` trên node có nhiều relationship | Một dòng đầu vào có thể nở thành hàng trăm/hàng triệu dòng | Đo fan-out của relationship, loại và hướng |
| `MATCH (a), (b)` không liên kết hai tập | Số dòng có thể là tích `|A| × |B|` | Rất dễ tạo Cartesian product ngoài ý muốn |
| `WHERE` / `Filter` | Giảm số dòng đi tiếp | Lọc muộn vẫn phải trả chi phí cho các bước trước |
| `DISTINCT` | Có thể giảm dòng trùng | Có chi phí deduplicate, có thể cần bộ nhớ |
| `RETURN count(*)` | Một dòng tổng hợp nếu không nhóm | Không phản ánh số dòng đã quét |
| `WITH key, count(*)` | Một dòng cho mỗi nhóm `key` | Đo riêng số nhóm và số đầu vào |
| `LIMIT n` | Giới hạn đầu ra và có thể dừng upstream sớm | Không bảo đảm tiết kiệm tương ứng nếu phía trước phải sort/aggregate |
| `OPTIONAL MATCH` | Có thể giữ một dòng với giá trị `null` khi không khớp | Không đồng nghĩa mọi nhánh đều có 0 dòng |

## 6. `DB Hits`: thao tác tầng lưu trữ, không phải đọc đĩa

### 6.1. Một database hit là gì?

`DB Hits` là **đơn vị trừu tượng** dùng để đếm công việc yêu cầu từ storage engine, chẳng hạn:

- Tìm node hoặc relationship qua ID/index/scan.
- Kiểm tra label, relationship type hoặc bậc node.
- Đọc thuộc tính node/relationship.
- Duyệt relationship, tìm đường đi.
- Tạo, xóa hoặc cập nhật thành phần graph, kiểm tra một số thông tin schema.

`DB Hits` được ghi nhận trong `PROFILE` và thường giúp tìm ra nơi truy vấn làm nhiều việc với storage engine.

### 6.2. Phân biệt ba khái niệm dễ nhầm

| Chỉ số | Đo điều gì? | Không có nghĩa là |
| --- | --- | --- |
| `Rows` | Số dòng mỗi operator thực tế xuất ra | Số node khác nhau hoặc số thao tác lưu trữ |
| `DB Hits` | Số thao tác truy cập storage engine theo mô hình đếm của Neo4j | Số lần đọc vật lý từ SSD/HDD |
| `Page Cache Hits/Misses` | Số lần tìm page trong cache thành công/thất bại, nếu runtime/edition cung cấp | Đồng nhất với `DB Hits` hoặc thời gian phản hồi end-to-end |

Ví dụ, đọc một thuộc tính đã ở trong page cache vẫn có thể phát sinh **DB Hits**, nhưng không cần đọc block từ ổ đĩa. Một `IndexSeek` trả một dòng vẫn có thể tạo nhiều DB Hits. Ngược lại, một `UNWIND` sinh hàng nghìn dòng in-memory có thể có rất ít thao tác lưu trữ.

### 6.3. Có nên luôn tối thiểu hóa DB Hits?

**Không.** Ít DB Hits hơn thường là dấu hiệu tích cực khi so sánh *cùng yêu cầu* trên *cùng bộ dữ liệu* với runtime tương đương. Tuy nhiên:

- Query có thể tốn CPU cho sort, hash join, regex hoặc xử lý biểu thức dù DB Hits thấp.
- Một `EagerAggregation` có thể dùng nhiều bộ nhớ, nhưng không thêm nhiều truy cập storage.
- Page cache lạnh làm truy cập đắt hơn so với cache nóng dù DB Hits gần như không đổi.
- Pipelined runtime hoặc các bản Neo4j khác nhau có thể ghi nhận DB Hits hơi khác nhau.
- Một truy vấn giảm DB Hits nhưng tăng thời gian vì phải sắp xếp hoặc materialize nhiều dòng vẫn có thể là tối ưu hóa không hiệu quả.

Tổng `DB Hits` ở footer là tổng hợp số đo của các operator **khi có thể đo đầy đủ**. Nếu có operator không hỗ trợ đo, có thể thấy dạng **`n + ?`**, tức `n` là cận dưới, không phải tổng chính xác. Đừng cộng lại toàn bộ cột operator rồi khẳng định đó là số lượng I/O vật lý.

## 7. Thực hành trên graph khách hàng – sản phẩm

### 7.1. Tạo dữ liệu nhỏ, có thể chạy lại

Các ví dụ sau dùng riêng một database thử nghiệm hoặc label chuyên dụng nếu môi trường đang có dữ liệu thực. Bắt đầu bằng các constraint để `MERGE` theo khóa:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer) REQUIRE c.id IS UNIQUE;
```

```cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;
```

Tạo ba khách hàng:

```cypher
UNWIND [
  {id: 'C001', name: 'An'},
  {id: 'C002', name: 'Bình'},
  {id: 'C003', name: 'Chi'}
] AS row
MERGE (c:Customer {id: row.id})
SET c.name = row.name;
```

Tạo ba sản phẩm:

```cypher
UNWIND [
  {sku: 'P001', name: 'Sách Cypher', price: 120},
  {sku: 'P002', name: 'Bút', price: 30},
  {sku: 'P003', name: 'Bàn phím', price: 250}
] AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.price = row.price;
```

Tạo các liên kết mua hàng:

```cypher
UNWIND [
  {customerId: 'C001', sku: 'P001'},
  {customerId: 'C001', sku: 'P002'},
  {customerId: 'C002', sku: 'P002'},
  {customerId: 'C003', sku: 'P001'},
  {customerId: 'C003', sku: 'P003'}
] AS row
MATCH (c:Customer {id: row.customerId})
MATCH (p:Product {sku: row.sku})
MERGE (c)-[:PURCHASED]->(p);
```

Nếu dữ liệu thử hoàn toàn sạch, graph có 3 `Customer`, 3 `Product` và 5 quan hệ `PURCHASED`. Không nên diễn giải các con số này như tổng toàn database khi đã có dữ liệu trước đó mang cùng label.

### 7.2. Dùng `EXPLAIN` để xem cách tiếp cận

```cypher
EXPLAIN
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku AS sku, p.price AS price
ORDER BY price DESC;
```

Câu hỏi khi đọc plan:

1. Neo4j bắt đầu từ `Customer` hay `Product`? Điều này thể hiện ở các leaf operator.
2. Nó dùng `NodeIndexSeek` theo `Customer.id` hoặc `Product.sku`, hay quét label?
3. Phần mở rộng `PURCHASED` nằm ở đâu?
4. `Estimated Rows` biến đổi ra sao giữa operator tìm node, mở rộng và lọc?
5. Có `Sort`, `Top` hoặc operator khác trước khi trả kết quả không?

Vì dữ liệu chỉ có vài node, planner có thể thấy quét label rẻ hơn dùng index; điều đó **không tự chứng minh index tạo sai**.

### 7.3. Dùng `PROFILE` để đối chiếu

```cypher
PROFILE
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku AS sku, p.price AS price
ORDER BY price DESC;
```

Với các bản ghi mẫu không bị sửa, kết quả truy vấn là sản phẩm `P001` có `price = 120`: khách `C001` mua hai sản phẩm `P001` và `P002`, nhưng `P002` không đạt ngưỡng 100.

Hãy tìm operator làm việc với các quan hệ `PURCHASED`. Nó có thể xuất ra hai dòng rồi nhánh lọc chỉ còn một dòng. **Tên và thứ tự operator thực tế có thể khác** theo phiên bản Cypher, runtime, thống kê và plan được chọn; không áp một ảnh plan minh họa lên mọi môi trường.

### 7.4. Ví dụ Cartesian product làm tăng dòng

```cypher
PROFILE
MATCH (c:Customer), (p:Product)
RETURN c.id AS customerId, p.sku AS sku;
```

Nếu tập thử gồm đúng 3 customer và 3 product, truy vấn trả **9 cặp**. Đây là tích Descartes, không có ý nghĩa “khách đã mua sản phẩm”. Muốn tìm giao dịch mua hàng, phải nối bằng relationship:

```cypher
PROFILE
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN c.id AS customerId, p.sku AS sku;
```

Truy vấn thứ hai trả 5 kết quả tương ứng 5 quan hệ mẫu. Khi sửa truy vấn, **bảo toàn ngữ nghĩa** quan trọng hơn giảm số liệu: hai câu lệnh ở trên trả hai tập kết quả khác nhau, nên không được dùng chúng làm benchmark thay thế trực tiếp cho nhau.

### 7.5. Aggregation che số dòng trung gian

```cypher
PROFILE
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN c.id AS customerId, count(p) AS purchasedCount
ORDER BY customerId;
```

Nếu graph đúng dữ liệu mẫu, kết quả có ba dòng: `C001 → 2`, `C002 → 1`, `C003 → 2`. Những con số này là số relationship đã khớp; một operator gần đầu ra có ba dòng **không phủ nhận** việc traversal trước đó sinh năm dòng.

## 8. Cách đọc sai lệch giữa `Estimated Rows` và `Rows`

Một workflow thực tế nên chú ý **nơi sai lệch đầu tiên xuất hiện** rồi lần theo tác động ở phía trên:

### Trường hợp A: Index seek ước lượng đúng, traversal phình to

Ví dụ giả định:

| Bước | Estimated Rows | Rows | Diễn giải |
| --- | ---: | ---: | --- |
| Tìm `Customer.id` | 1 | 1 | Chọn node đầu vào đúng |
| Đi theo `PURCHASED` | 10 | 50.000 | Khách này có nhiều quan hệ hơn mức ước lượng |
| Lọc theo `price` | 2 | 300 | Phần lớn dòng đã được tạo ra rồi mới bị loại |

Đây có thể là vấn đề fan-out, dữ liệu lệch hoặc điều kiện chọn lọc chưa được khai thác tốt. Không kết luận “tạo thêm index sẽ giải quyết” trước khi kiểm tra khả năng bắt đầu từ đầu còn lại, hướng traversal và độ chọn lọc.

### Trường hợp B: `Rows` cao từ trước operator `Filter`

Nếu nhiều dòng được tạo rồi mới `Filter` bỏ đi, nên xem `WHERE` có đang sử dụng đúng thuộc tính, có index phù hợp hay không. **Không mặc định rằng chuyển vị trí dòng `WHERE` trong văn bản Cypher sẽ đổi plan**: Cypher là ngôn ngữ khai báo, planner có quyền đẩy predicate và sắp xếp lại cách truy cập.

### Trường hợp C: Sai lệch ước lượng lớn nhưng `DB Hits` nhỏ

Chỉ số estimate sai có thể **không gây tác động thực tế đáng kể** nếu số dòng tuyệt đối nhỏ, toàn bộ thao tác nằm trong bộ nhớ hoặc planner vẫn chọn chiến lược phù hợp. Đánh giá bằng thời gian và độ ổn định; không tối ưu chỉ để làm các cột estimated/actual gần nhau.

### Trường hợp D: `Estimated Rows` gần đúng nhưng `DB Hits` cao

Planner dự đoán đúng số dòng không bảo đảm đường truy cập rẻ. Một pattern khớp ít dòng nhưng phải kiểm tra nhiều quan hệ hoặc đọc nhiều property có thể tạo nhiều DB Hits. Cần xem operator truy cập, predicate và trạng thái index.

## 9. Các giới hạn khi diễn giải số liệu plan

### 9.1. Không so sánh số giữa các runtime như thể cùng một phép đo chuẩn hóa

Neo4j có các runtime, trong đó **pipelined** và **parallel** có cơ chế thực thi khác nhau. Một số operator được **fuse** thành pipeline; khi đó một số thống kê (đặc biệt thời gian) chỉ gắn với pipeline, thay vì từng operator.

- `Rows` và `DB Hits` vẫn hữu ích, nhưng cách đếm chi tiết và mức độ hiển thị có thể khác theo runtime/phiên bản.
- `Time (ms)` của các operator fuse có thể đại diện cho **cả pipeline**; không cộng lặp mọi ô thời gian giống nhau.
- Trong parallel runtime, thời gian làm việc được báo có thể cộng dồn giữa worker, không phải wall-clock tổng của request.
- Một số ô trống hoặc ký hiệu `?` là **không có số đo**, không đồng nghĩa giá trị bằng 0.

Khi benchmark, ghi rõ phiên bản Neo4j, phiên bản Cypher, runtime, thông số query, dữ liệu và tình trạng tải hệ thống.

### 9.2. Page cache và độ trễ truy cập ổ đĩa

Neo4j duy trì **page cache** để tránh đọc lại các page trên đĩa. Hai lần thực thi cùng query có thể có DB Hits tương tự nhưng thời gian rất khác nhau nếu:

- Lần đầu page cache **lạnh**, nhiều lần phải nạp page từ storage.
- Lần sau cache **nóng**, nhiều dữ liệu đã ở RAM.
- Hệ thống đang xử lý tác vụ ghi hoặc query khác gây tranh chấp tài nguyên.

`Page Cache Hits/Misses` (khi có, ví dụ trên Enterprise Edition) giúp kiểm tra thêm. **DB Hits lớn không có nghĩa cùng số lượng I/O đĩa**; và page-cache misses cũng không tự giải thích toàn bộ độ trễ mạng, driver, ứng dụng.

### 9.3. Bộ nhớ và xử lý eager

`Sort`, `EagerAggregation`, join hoặc `Eager` có thể giữ nhiều dòng trong bộ nhớ. Một truy vấn với DB Hits thấp vẫn có thể chậm hoặc gây áp lực heap khi phải sắp xếp hàng triệu kết quả.

`Memory (Bytes)` của từng operator (nếu có) phản ánh **mức đỉnh cho operator**, không phải tổng bộ nhớ của tất cả operator. Tổng memory ở footer biểu diễn đỉnh toàn query, **không đơn giản bằng tổng các đỉnh operator**: các đỉnh có thể xảy ra ở thời điểm khác nhau.

`Eager` có thể được thêm để bảo toàn tính đúng khi đọc và ghi chồng lấn; không nên cố bỏ nó bằng cách viết lại truy vấn nếu điều đó làm thay đổi ngữ nghĩa hoặc phá vỡ tính đúng.

### 9.4. `LIMIT` và việc không đọc hết dữ liệu

```cypher
PROFILE
MATCH (p:Product)
RETURN p.sku
LIMIT 5;
```

Với những operator **lazy**, `LIMIT` có thể khiến upstream dừng sớm. Nhưng với:

```cypher
PROFILE
MATCH (p:Product)
RETURN p.sku, p.price
ORDER BY p.price DESC
LIMIT 5;
```

Neo4j có thể phải xem xét nhiều sản phẩm trước khi biết top 5, trừ khi dùng được thứ tự/index hoặc tối ưu thích hợp. Vì vậy không lấy `Rows = 5` ở đầu ra để kết luận chỉ có 5 node được đọc.

### 9.5. Kết quả truy vấn và dữ liệu truyền về client

Plan phản ánh công việc xử lý phía database engine. Thời gian một HTTP request hoặc service Java còn gồm mạng, kết nối driver, ánh xạ DTO, serialization, pagination, tải của hệ thống và thời gian người dùng nhận đủ kết quả.

Nếu một truy vấn có 100.000 kết quả, phần truyền dữ liệu/serialize có thể tốn nhiều thời gian dù plan không có DB Hits bất thường. Cần đo thêm latency phía ứng dụng, không chỉ ảnh `PROFILE` trong Neo4j Browser.

## 10. Tối ưu dựa trên bằng chứng, không chỉ một con số

### 10.1. Cố định đầu vào để so sánh

Để đánh giá một thay đổi Cypher/index:

1. Giữ nguyên **ngữ nghĩa và tập kết quả**. So sánh số dòng, khóa thực thể và tính trùng trước/sau.
2. Chạy với dữ liệu và tham số đại diện, bao gồm cả trường hợp **high-degree node** và trường hợp thông thường.
3. Ghi `EXPLAIN` và `PROFILE`: tìm index/scan, `Estimated Rows`, `Rows`, `DB Hits`, memory/time khi có.
4. Đo nhiều lần sau warm-up, theo dõi trạng thái page cache và tải hệ thống; không so sánh một lần cache lạnh với một lần cache nóng.
5. Chỉ triển khai thay đổi khi latency, tài nguyên và tính đúng được cải thiện theo mục tiêu.

**Không profile truy vấn ghi trực tiếp trên production để thử nghiệm.** Tạo bản sao dữ liệu hoặc một kịch bản test được kiểm soát; nếu cần đo luồng ghi thật, phải hiểu tác động commit và khả năng retry.

### 10.2. Kiểm tra index/constraint và dùng predicate phù hợp

Ví dụ constraint cho khóa khách hàng:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer) REQUIRE c.id IS UNIQUE;
```

Constraint giữ dữ liệu nhất quán và tạo index thích hợp cho truy cập qua `id`. Với truy vấn lọc sản phẩm theo giá như trong ví dụ, có thể cân nhắc range index:

```cypher
CREATE RANGE INDEX idx_product_price IF NOT EXISTS
FOR (p:Product) ON (p.price);
```

Sau khi schema đã được tạo, kiểm tra `SHOW INDEXES` và tình trạng `ONLINE` trước khi đánh giá plan. Index không nhất thiết được sử dụng khi label nhỏ hoặc predicate kém chọn lọc. **Index không tự thay thế điều kiện kết nối graph**.

### 10.3. Thiết kế truy vấn để tránh mở rộng không cần thiết

Nếu mục tiêu là đếm số lần mua của **một khách**, thay vì duyệt toàn bộ graph rồi lọc ở tầng ứng dụng:

```cypher
MATCH (c:Customer {id: $customerId})-[:PURCHASED]->(p:Product)
RETURN count(*) AS purchases;
```

Truy vấn có predicate trên khóa khách trước khi đi theo relationship. Planner có cơ hội dùng index và thu hẹp vùng graph phải khám phá. Tuy nhiên, Cypher planner được quyền chọn lại thứ tự thực thi; hãy xem operator thực tế để biết đường truy cập.

Để tránh nhân số dòng bởi hai nhánh một-nhiều không phụ thuộc, có thể tổng hợp riêng từng nhánh trong subquery. Ví dụ đếm số sản phẩm đã mua và số cửa hàng đã ghé của một khách hàng:

```cypher
MATCH (c:Customer {id: $customerId})
CALL (c) {
  MATCH (c)-[:PURCHASED]->(p:Product)
  RETURN count(p) AS productCount
}
CALL (c) {
  MATCH (c)-[:VISITED]->(s:Store)
  RETURN count(s) AS storeCount
}
RETURN c.id, productCount, storeCount;
```

Ví dụ trên sử dụng **variable scope clause** `CALL (c)` (Cypher 5.23+). Nếu viết `MATCH` cho cả hai nhánh và tổng hợp trong cùng một luồng mà không xét multiplicity, số dòng có thể nhân lên, khiến `count` sai và `DB Hits` tăng. Hãy xác định semantics của `count(*)`, `count(DISTINCT ...)` và cách xử lý khách không có quan hệ trước khi viết lại.

### 10.4. Giới hạn việc can thiệp planner

Các gợi ý như `USING INDEX` hoặc `USING JOIN` chỉ nên xem xét sau khi đã đo rõ planner chọn đường truy cập không phù hợp và kiểm chứng giải pháp trên dữ liệu đại diện. Một hint hữu ích ở dữ liệu hôm nay có thể thành bất lợi khi phân bố và kích thước graph thay đổi.

Nếu nghi số liệu thống kê không còn phù hợp, kiểm tra cơ chế **index sampling** và **query replanning** của phiên bản Neo4j đang dùng. `db.resampleIndex('indexName')` phục vụ cập nhật thống kê planner, **không phải sửa dữ liệu sai hoặc đồng bộ lại mọi entry trong index**. Xóa query cache hoặc ép replan là thao tác vận hành cần lý do rõ ràng, không phải bước đầu tiên khi thấy `Estimated Rows` lệch.

## 11. Đọc số liệu từ Java Driver và ứng dụng Spring

### 11.1. Java Driver: lấy profile sau khi consume

Neo4j Java Driver cung cấp execution plan qua `ResultSummary`. Trên **Java Driver 6.2+**, API `queryProfile()` trả về `Optional<QueryProfile>`; `QueryProfile` có các trường như `rows()` và `dbHits()` theo `OptionalLong`. Ví dụ:

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.QueryProfile;
import org.neo4j.driver.summary.ResultSummary;

String query = """
    PROFILE
    MATCH (c:Customer {id: $customerId})-[:PURCHASED]->(p:Product)
    RETURN p.sku AS sku
    """;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    ResultSummary summary = session.run(
        query, java.util.Map.of("customerId", "C001")
    ).consume();

    summary.queryProfile().ifPresent(root -> {
        System.out.println("Root operator: " + root.operatorType());
        System.out.println("Rows: " + root.rows().orElse(-1));
        System.out.println("DB Hits: " + root.dbHits().orElse(-1));
    });
}
```

Trong ví dụ, `driver` đã được tạo và quản lý vòng đời ở tầng ứng dụng. `consume()` đảm bảo đã nhận toàn bộ kết quả/trình tổng kết trước khi đọc plan. Root operator chỉ đại diện **một node của cây plan**; để phân tích đầy đủ cần duyệt `children()`, xem `operatorType()` và các chỉ số từng operator. Dấu `-1` là giá trị minh họa khi số liệu không hiện diện, **không phải số đo Neo4j**.

Java Driver cũ có `ResultSummary.profile()` và `ProfiledPlan.records()`/`dbHits()`; các API này được đánh dấu deprecated trong những bản driver mới. Không sao chép ví dụ của version 6.2+ vào driver 5.x mà không kiểm tra API đang dùng.

### 11.2. Spring Data Neo4j

Ứng dụng Spring Data Neo4j có thể dùng `@Query` hoặc `Neo4jClient` cho Cypher. Việc kiểm chứng plan thường được thực hiện với **cùng câu Cypher và tham số** trong Neo4j Browser/cypher-shell hoặc thông qua Neo4j Java Driver có kiểm soát. Chú ý:

- Bật `PROFILE` trên câu truy vấn ghi có thể **thay đổi graph thực sự**, kể cả bên trong service `@Transactional`.
- Chuỗi Cypher, kiểu tham số và điều kiện do Spring đưa vào cần được đối chiếu với câu truy vấn đo; plan có thể khác khi tham số và dữ liệu khác.
- Driver/API có thể thêm chi phí ánh xạ entity, lazy loading hoặc các query riêng. Nếu đo ở tầng service, không suy rằng một plan duy nhất đại diện toàn bộ thao tác ứng dụng.
- Đo `Rows`, `DB Hits` để tìm chi phí phía Neo4j, đồng thời theo dõi latency và thông lượng phía ứng dụng.

## 12. Những ngộ nhận dễ gây tối ưu sai

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`Estimated Rows = 100` nghĩa là DB đã đọc 100 node.” | Đây là **ước lượng dòng đầu ra của operator**, không phải số node hoặc số lần đọc. |
| “`Rows = 1` nên query không có vấn đề.” | Aggregation hoặc `LIMIT` có thể trả một dòng sau khi xử lý khối lượng dữ liệu lớn. |
| “`DB Hits = 1.000` nghĩa là đọc ổ đĩa 1.000 lần.” | DB Hits đếm thao tác storage engine, phải phân biệt với page-cache misses/I/O vật lý. |
| “Query A có DB Hits thấp hơn nên chắc chắn nhanh hơn B.” | Cần so cùng semantics, dữ liệu, cache, runtime và đo latency/CPU/memory. |
| “`EXPLAIN` cho biết truy vấn đã chạy tốn bao nhiêu DB Hits.” | `EXPLAIN` **không chạy**; dùng `PROFILE` mới có số đo. |
| “`PROFILE DELETE` chỉ xem trước.” | `PROFILE` thực thi lệnh ghi thật; dùng `EXPLAIN` để kiểm tra trước. |
| “Chuyển `WHERE` lên trước `MATCH` chắc chắn giảm DB Hits.” | Planner Cypher tự chọn chiến lược; phải xem plan và bảo toàn ngữ nghĩa. |
| “Operator có `DB Hits = 0` không tốn thời gian.” | Sort, aggregation, CPU, bộ nhớ và network có thể vẫn tốn tài nguyên. |
| “`Memory (Bytes)` có thể cộng trên toàn bộ operator.” | Mỗi operator thường báo peak riêng; tổng peak query không phải phép cộng đơn giản. |
| “Nhiều ô `Time (ms)` cùng số nghĩa là nhiều operator tốn từng ấy thời gian.” | Operator được fuse trong cùng pipeline có thể chia sẻ số đo thời gian. |
| “Planner ước lượng sai nên index bị hỏng.” | Sai ước lượng có thể do skew, selectivity, thống kê hoặc plan cache; xem index status và dữ liệu thực. |
| “Planner luôn dùng index nếu đã tạo.” | Planner chọn theo chi phí ước tính; scan có thể rẻ hơn trên dữ liệu nhỏ hoặc điều kiện ít chọn lọc. |

## 13. Checklist phân tích một truy vấn chậm

1. **Xác nhận tính đúng:** truy vấn trả tập kết quả nào, có trùng do nhiều path/relationship không?
2. **Chạy `EXPLAIN`:** xác định leaf operator, index/scan, `Estimated Rows`, hướng traversal và khả năng Cartesian product.
3. **Chạy `PROFILE` an toàn:** chỉ với truy vấn đọc hoặc trên dữ liệu test được phép ghi. Ghi `Rows`, `DB Hits` từng nhánh.
4. **Tìm điểm phình dòng đầu tiên:** so `Estimated Rows` với `Rows` khi đi qua `Expand`, join, `OPTIONAL MATCH`, filter và aggregation.
5. **Tìm vùng tiêu thụ storage:** so `DB Hits` các operator; đối chiếu page cache, memory, time khi khả dụng.
6. **Xem bối cảnh:** runtime, Neo4j version, plan cache, tham số, dữ liệu lệch, transaction/cluster và tải concurrent.
7. **Chọn thay đổi nhỏ có căn cứ:** index/constraint, predicate chọn lọc, pattern traversal, subquery tách các nhánh hoặc sửa Cartesian product ngoài ý muốn.
8. **Đo lại và đối chiếu kết quả:** cùng semantics, cùng input; đánh giá thời gian, tài nguyên và tính ổn định trước khi triển khai.

## 14. Bài tập tự luyện

1. Với graph mẫu, chạy `PROFILE MATCH (c:Customer)-[:PURCHASED]->(p:Product) RETURN count(*)`. Giải thích vì sao `Rows` tại `ProduceResults` có thể là 1 nhưng phía dưới xử lý 5 quan hệ.
2. So sánh `PROFILE MATCH (c:Customer), (p:Product) RETURN c, p` và truy vấn có `[:PURCHASED]`. Giải thích vì sao số dòng 9 và 5 phản ánh hai **ngữ nghĩa khác nhau**.
3. Thử `EXPLAIN` trước và sau khi tạo constraint trên `Customer.id`. Với graph nhỏ, planner có thể vẫn scan không? Giải thích bằng chi phí.
4. Giả sử operator `Expand(All)` có `Estimated Rows = 50`, `Rows = 5.000`, `DB Hits = 12.000`. Bạn sẽ xem những operator và thông tin nào trước khi đề xuất index hoặc viết lại truy vấn?
5. Hai lần `PROFILE` cùng query có DB Hits gần bằng nhau nhưng thời gian khác nhiều; nêu tối thiểu ba lý do không liên quan đến lỗi query plan.
6. Viết truy vấn tìm mỗi khách hàng và hai số đếm: số quan hệ `PURCHASED` và `VISITED`. Dùng subquery tách nhánh để không nhân kết quả hai tập, sau đó so sánh plan với cách viết gộp.

## 15. Ghi nhớ

- **`Estimated Rows`** là dự đoán đầu ra của từng operator khi **lập plan**; có thể sai do dữ liệu lệch, thống kê và giả định selectivity.
- **`Rows`** là số dòng thực sự sinh ra ở từng operator trong **`PROFILE`**; không phải số node duy nhất và không nhất thiết bằng số dòng cuối.
- **`DB Hits`** là chỉ báo công việc với storage engine, **khác đọc đĩa** và không độc lập quyết định latency.
- **`EXPLAIN` không chạy query**; **`PROFILE` chạy thật**, bao gồm tác động ghi dữ liệu nếu có.
- Hãy đọc **cả cây operator**, quan tâm fan-out ở `Expand`, nhánh `CartesianProduct`, filter muộn, aggregation/sort, page cache, bộ nhớ và runtime.
- Chỉ tối ưu khi đã xác nhận **tập kết quả đúng**, so sánh công bằng và đo lại trên dữ liệu đại diện.

### Tài liệu tham khảo chính thức

- [Neo4j Cypher Manual — Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual — Operators](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/)
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher Manual — Query caches](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/caching/)
- [Neo4j Operations Manual — Statistics and execution plans](https://neo4j.com/docs/operations-manual/current/performance/statistics-execution-plans/)
- [Neo4j Java Driver API — `ResultSummary`](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/ResultSummary.html)
- [Neo4j Java Driver API — `QueryProfile`](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/QueryProfile.html)
