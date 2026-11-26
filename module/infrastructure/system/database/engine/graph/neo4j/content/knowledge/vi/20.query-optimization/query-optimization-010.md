# Nhận diện giới hạn do mô hình dữ liệu thay vì chỉ sửa câu truy vấn

Một truy vấn Cypher chậm không phải lúc nào cũng do viết sai `MATCH`, thiếu `WITH` hoặc quên tạo index. Có những trường hợp Neo4j đã chọn điểm bắt đầu hợp lý, đã sử dụng index và không quét toàn bộ node, nhưng vẫn phải mở rộng hàng trăm nghìn relationship để trả về mười kết quả. Khi đó, **chi phí lớn xuất phát từ cấu trúc và phân bố dữ liệu trên đồ thị**, nên chỉ đổi cú pháp có thể không giải quyết được vấn đề.

Bài học thuộc chương **Tối ưu truy vấn** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng Neo4j để mô hình hóa dữ liệu liên kết theo **property graph**, truy vấn quan hệ và đường đi bằng Cypher, thiết kế index/constraint, tích hợp Java Driver và Spring Data Neo4j. Chủ đề tập trung vào việc phân biệt **giới hạn của câu truy vấn** với **giới hạn của mô hình dữ liệu**, sau đó quyết định khi nào nên điều chỉnh label, relationship, thuộc tính, cách lưu lịch sử hoặc dữ liệu tính sẵn.

Sau bài này, bạn có thể:

- Đọc `EXPLAIN`/`PROFILE` để tìm toán tử sinh nhiều hàng trung gian, `DB Hits` và độ trễ.
- Nhận diện node có bậc quá lớn, traversal nở theo nhiều tầng, cạnh trùng, dữ liệu quá phân mảnh và điều kiện lọc khó áp dụng sớm.
- Đo phân bố bậc (*degree distribution*) thay vì chỉ nhìn số lượng node và relationship trung bình.
- So sánh việc sửa truy vấn với thay đổi mô hình, bao gồm cả chi phí ghi dữ liệu, đồng bộ, lưu trữ và độ mới của dữ liệu.
- Thiết kế phép thử trước/sau để chứng minh giải pháp thật sự cải thiện hiệu năng mà vẫn đúng kết quả nghiệp vụ.

## 1. Phân biệt hai loại nút thắt

Hãy bắt đầu từ câu hỏi: **Neo4j đang làm công việc thừa vì truy vấn chưa tốt, hay vì dữ liệu được tổ chức khiến công việc đó là bắt buộc?**

| Dấu hiệu | Nghiêng về vấn đề truy vấn/index | Nghiêng về vấn đề mô hình |
| --- | --- | --- |
| Điểm bắt đầu | Bắt đầu bằng quét label dù có thuộc tính lọc chọn lọc. | Đã tìm chính xác một node nhưng nó nối với quá nhiều node khác. |
| Số hàng trung gian | Có tích Descartes vô tình vì hai pattern độc lập. | Đường đi nghiệp vụ hợp lệ vốn tạo quá nhiều kết hợp. |
| Bộ lọc | `WHERE`/`LIMIT` đặt sai chỗ, giữ nhiều hàng không cần thiết. | Điều kiện chọn lọc chỉ tồn tại ở cuối một đường đi dài. |
| Dữ liệu | Có index phù hợp nhưng truy vấn không tận dụng được. | Có một “supernode”, dữ liệu lệch mạnh theo tenant/sản phẩm/thời gian. |
| Kết quả sau viết lại | Thay pattern, đẩy bộ lọc sớm giúp giảm chi phí rõ rệt. | Nhiều biến thể Cypher vẫn phải đi qua gần như cùng số relationship. |
| Giải pháp lâu dài | Sửa câu lệnh, thêm index/constraint phù hợp, bỏ hàng trùng. | Thay cách biểu diễn quan hệ, lưu tập kết quả đã tổng hợp hoặc điều chỉnh vòng đời dữ liệu. |

Đây là dấu hiệu định hướng, **không phải kết luận tự động**. Một truy vấn có thể đồng thời gặp cả hai loại vấn đề. Hãy đo kế hoạch thực thi và phân bố dữ liệu trước khi quyết định.

### 1.1. Một mô hình, hai mức chi phí

Giả sử có đồ thị hành vi:

~~~text
(:User {tenantId, userId})
      |
      | [:VIEWED]
      v
(:Product {sku, name})
      ^
      | [:VIEWED]
      |
(:User {tenantId, userId})
~~~

Ứng dụng muốn gợi ý người dùng khác từng xem cùng sản phẩm. Một người xem 20 sản phẩm; nếu mỗi sản phẩm phổ biến được 10.000 người khác xem, phép đi `User → Product → User` có thể tạo xấp xỉ **20 × 10.000 = 200.000 lượt ghép ứng viên** trước khi loại hàng trùng và chọn top 10. Con số chỉ là ví dụ minh họa; chi phí thực tế còn phụ thuộc quan hệ trùng, phân bố sản phẩm và kế hoạch thực thi.

Thêm index `User(tenantId, userId)` giúp Neo4j tìm người dùng ban đầu nhanh. Nó **không làm số relationship ở 20 sản phẩm phổ biến tự giảm đi**. `LIMIT 10` sau khi đã tính điểm cho mọi ứng viên cũng không thể tự loại bỏ việc duyệt tập ứng viên cần thiết để xác định top 10.

Đây là giới hạn có thể xuất phát từ mô hình và thuật toán đề xuất, không đơn thuần từ cú pháp Cypher.

## 2. Xác định công việc thật sự bằng EXPLAIN và PROFILE

`EXPLAIN` cho biết kế hoạch dự kiến mà không thực thi câu truy vấn; `PROFILE` thực thi thật và ghi nhận thống kê trong kế hoạch. Thử trên môi trường đại diện với tham số và lượng dữ liệu tương tự thực tế:

~~~cypher
EXPLAIN
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other <> u AND other.tenantId = $tenantId
RETURN other.userId AS candidateId, count(DISTINCT p) AS sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

Đo tiếp bằng:

~~~cypher
PROFILE
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other <> u AND other.tenantId = $tenantId
RETURN other.userId AS candidateId, count(DISTINCT p) AS sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

Các tham số `$tenantId` và `$userId` phải được cung cấp bởi công cụ thử hoặc ứng dụng. Không có bản ghi bắt đầu thì truy vấn trả rỗng; đó không phải bằng chứng truy vấn nhanh trên trường hợp đông dữ liệu.

Khi đọc kế hoạch, chú ý những điểm sau:

| Thông số/toán tử thường gặp | Điều cần hỏi |
| --- | --- |
| `NodeIndexSeek`, `NodeByLabelScan` và các toán tử tương ứng | Neo4j bắt đầu từ bao nhiêu node? Có lọc đúng tenant và khóa định danh không? |
| `Expand(All)` / `Expand(Into)` hoặc toán tử mở rộng đường đi | Mỗi hàng đầu vào mở rộng thành bao nhiêu hàng? Có node nào sinh lượng quan hệ cực lớn không? |
| `Filter` | Có quá nhiều hàng bị loại **sau** một phép mở rộng đắt tiền không? |
| `Distinct`, `Aggregation`, `EagerAggregation` | Hệ thống phải gom bao nhiêu hàng trước khi có thể trả kết quả? |
| `Sort`, `Top` | Có phải xếp hạng tập ứng viên rất lớn để lấy vài hàng đầu? |
| `Rows` và `DB Hits` | Số lượng hàng và truy cập cơ sở dữ liệu tăng mạnh ở đoạn nào? |
| Bộ nhớ, page cache và thời gian nếu kế hoạch hiển thị | Nút thắt là mở rộng quan hệ, đọc dữ liệu hay cấp phát/tổng hợp? |

Tên toán tử và các thống kê được hiển thị có thể khác theo phiên bản, runtime và cách chạy Neo4j. `DB Hits` là tín hiệu thao tác truy cập dữ liệu ở mức kế hoạch, **không phải đơn vị đo thời gian tuyệt đối**. Nên đọc cùng `Rows`, thời gian, bộ nhớ và kết quả.

**Dấu hiệu mô hình đáng nghi:** từ một node `User` tìm được bằng index (1 hàng), bước đến `Product` sinh 20 hàng nhưng bước quay về `User` tạo hàng trăm nghìn hàng. Sau đó `Aggregation` nén kết quả xuống vài nghìn người và `Top` chỉ còn 10 người. Đổi cú pháp cuối truy vấn không làm biến mất chi phí mở rộng ban đầu.

## 3. Kiểm tra phân bố bậc: đừng chỉ dựa vào trung bình

**Bậc của node** là số quan hệ gắn với nó theo một hướng/type được xét. Một mô hình có trung bình 50 lượt xem mỗi sản phẩm vẫn có thể chứa một sản phẩm nổi tiếng với hàng triệu lượt xem. Những node có bậc bất thường lớn thường được gọi là *supernode* hoặc *dense hub* trong bối cảnh hiệu năng.

Để khảo sát trên mô hình mẫu:

~~~cypher
MATCH (p:Product)
OPTIONAL MATCH (p)<-[v:VIEWED]-(:User)
WITH p, count(v) AS viewDegree
RETURN count(*) AS productCount,
       min(viewDegree) AS minViews,
       percentileCont(viewDegree, 0.50) AS p50Views,
       percentileCont(viewDegree, 0.95) AS p95Views,
       percentileCont(viewDegree, 0.99) AS p99Views,
       max(viewDegree) AS maxViews;
~~~

Một truy vấn riêng giúp xác định node nào gây bùng nổ:

~~~cypher
MATCH (p:Product)
OPTIONAL MATCH (p)<-[v:VIEWED]-(:User)
WITH p, count(v) AS viewDegree
RETURN p.sku AS sku, viewDegree
ORDER BY viewDegree DESC, sku ASC
LIMIT 20;
~~~

Những phép thống kê này **vẫn phải đọc nhiều relationship** và có thể đắt trên dữ liệu lớn. Hãy chạy trên môi trường phân tích, bản sao dữ liệu hoặc thời gian phù hợp; với hệ thống nhiều tenant, cần đo phân bố theo tenant và phân khúc thay vì chỉ gộp toàn cục. Một vài thuộc tính hoặc hướng quan hệ có thể có phân bố hoàn toàn khác nhau.

Ví dụ một tập giả định:

| Thước đo số lượt `VIEWED` trên mỗi Product | Giá trị |
| --- | ---: |
| Trung vị (p50) | 8 |
| p95 | 170 |
| p99 | 4.000 |
| Lớn nhất | 2.100.000 |

Trung vị nhỏ không giúp ích nhiều nếu truy vấn thường xuyên đi qua sản phẩm có 2,1 triệu quan hệ. Kỹ thuật giới hạn truy vấn theo “số nhánh trung bình” sẽ dự đoán sai hiệu năng ở các trường hợp xấu nhất.

### 3.1. Chi phí đi qua nhiều tầng

Với đồ thị có bậc phân nhánh trung bình khoảng `d`, mở rộng đến `k` bước **có thể** tạo lượng đường đi tăng rất nhanh theo `d^k` trong những cấu trúc ít hội tụ. Đây là hình dung về tăng trưởng, không phải công thức dự đoán tuyệt đối cho Neo4j: đồ thị có chu trình, các quan hệ hội tụ, hướng/type ràng buộc và quy tắc duy nhất của đường đi làm số lượng thay đổi.

Ví dụ:

~~~cypher
MATCH (start:User {tenantId: $tenantId, userId: $userId})
MATCH p = (start)-[:FOLLOWS*1..4]->(candidate:User)
WHERE candidate.tenantId = $tenantId
RETURN candidate.userId AS userId, length(p) AS hops
ORDER BY hops ASC, userId ASC
LIMIT 20;
~~~

Mẫu truy vấn trên **liệt kê đường đi phù hợp**, một người đích có thể xuất hiện trên nhiều đường. `LIMIT 20` ở kết quả cuối không bảo đảm engine chỉ phải xét 20 đường đi để tìm 20 hàng đầu theo thứ tự mong muốn. Nếu nghiệp vụ chỉ cần người đích duy nhất hoặc đường đi ngắn nhất, phải thay đổi **định nghĩa kết quả** và chọn phép truy vấn phù hợp trước khi tối ưu.

## 4. Những dấu hiệu mô hình đang áp đặt giới hạn

### 4.1. Điểm nối quá đông: supernode

Các node như `:GlobalCatalog`, `:Everyone`, `:PopularTopic` hoặc một sản phẩm có lượt tương tác cực lớn khiến nhiều truy vấn phải qua cùng một “cổng” có bậc rất lớn. Neo4j có những tối ưu nội bộ cho dense node, nhưng không thể loại bỏ số phép mở rộng thực sự cần thiết để tìm kết quả.

Giải pháp cần xét theo ngữ nghĩa:

- Nếu mục tiêu là tìm một sản phẩm theo `sku`, đi thẳng đến `(:Product {sku})` với index thay vì đi từ `GlobalCatalog` qua mọi sản phẩm.
- Nếu tìm người dùng tương tự, tránh mở rộng qua **mọi** sản phẩm phổ biến khi thuật toán cho phép bỏ qua những sản phẩm mang rất ít tín hiệu cá nhân hóa.
- Nếu cần top-K đề xuất lặp lại nhiều lần, cân nhắc tiền tính các mối quan hệ điểm tương đồng với chính sách làm mới rõ ràng.

Không chia một supernode thành nhiều node ngẫu nhiên mà làm thay đổi ý nghĩa miền dữ liệu, mất khả năng truy vấn hoặc tạo quan hệ trùng.

### 4.2. Đưa mọi thuộc tính thành node và relationship

Mô hình dưới đây có thể quá phân mảnh nếu `status` chỉ là một giá trị đơn giản của đơn hàng:

~~~text
(:Order)-[:HAS_STATUS]->(:Status {code:'PAID'})
~~~

Nếu có hàng triệu `Order` cùng nối đến một node trạng thái `PAID`, truy vấn lọc đơn hàng có thể phải duyệt một nhóm cực lớn hoặc đi đường vòng không cần thiết. Khi không có nhu cầu gắn siêu dữ liệu hoặc liên kết nghiệp vụ độc lập cho trạng thái, lưu `status` thành thuộc tính có thể hợp lý hơn:

~~~text
(:Order {orderId, status:'PAID', createdAt, tenantId})
~~~

Với mô hình thứ hai, có thể xét range index phục vụ tìm kiếm theo tenant, trạng thái và thời gian:

~~~cypher
CREATE RANGE INDEX order_scope_status_created IF NOT EXISTS
FOR (o:Order)
ON (o.tenantId, o.status, o.createdAt);
~~~

Chỉ mục này không tự bảo đảm mọi truy vấn sẽ dùng được thứ tự sắp xếp từ index. Cần kiểm tra `EXPLAIN`/`PROFILE` với mẫu lọc và thứ tự thực tế. Trong miền nghiệp vụ mà `Status` là thực thể có vòng đời, quyền hạn, bản dịch, lịch sử chuyển trạng thái hoặc quan hệ khác, node riêng vẫn có giá trị; không nên tự động biến mọi node nhỏ thành property.

### 4.3. Lưu sự kiện lặp dưới dạng nhiều relationship giống nhau

Giả sử mỗi lần người dùng xem sản phẩm đều tạo một quan hệ mới:

~~~text
(:User)-[:VIEWED {at}]->(:Product)
(:User)-[:VIEWED {at}]->(:Product)
(:User)-[:VIEWED {at}]->(:Product)
~~~

Đối với câu hỏi “người dùng đã từng xem sản phẩm nào?”, ba quan hệ này biểu diễn một cặp user–product lặp lại, làm tăng số hàng phải mở rộng rồi `DISTINCT`. Nhưng đối với câu hỏi “người dùng xem bao nhiêu lần trong mỗi ngày?”, ba sự kiện riêng là thông tin quan trọng.

Có thể lựa chọn hai biểu diễn phục vụ hai kiểu truy vấn:

~~~text
(:User)-[:HAS_VIEWED {count, lastSeenAt}]->(:Product)

(:ViewEvent {eventId, at})
    -[:BY_USER]->(:User)
    -[:OF_PRODUCT]->(:Product)
~~~

Quan hệ `HAS_VIEWED` có thể được thiết kế để mỗi cặp user–product chỉ có một cạnh tổng hợp; các node `ViewEvent` giữ lịch sử chi tiết khi cần audit/analytics. **Hai biểu diễn cần quy tắc đồng bộ hoặc tái tính**, vì nếu một hệ thống ghi sự kiện thành công nhưng không cập nhật quan hệ tổng hợp thì dữ liệu đề xuất có thể cũ.

Neo4j không mặc nhiên có constraint “tối đa một relationship với cùng hai endpoint” chỉ vì ta dùng một relationship type. Cần thiết kế luồng ghi, ràng buộc định danh phù hợp và kiểm thử đồng thời để bảo vệ cấu trúc tổng hợp.

### 4.4. Thuộc tính lọc chỉ nằm ở cuối đường đi

Một truy vấn muốn tìm sản phẩm được quan tâm **trong tenant hiện tại** nhưng chỉ có `tenantId` trên node `User` có thể phải mở rộng các tương tác toàn cục trước khi lọc tenant:

~~~cypher
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other.tenantId = $tenantId AND other <> u
RETURN other.userId AS candidateId, count(DISTINCT p) AS sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

Nếu một sản phẩm liên kết với hàng triệu user thuộc các tenant khác nhau, phép mở rộng về `other` có thể tạo rất nhiều hàng bị loại. Việc gắn tenant lên một điểm bắt đầu có tính chọn lọc hơn, dùng phân vùng đồ thị theo miền hoặc tạo cấu trúc liên kết phù hợp tenant có thể hữu ích, **nhưng mọi phương án phải kiểm soát chặt quyền truy cập và nhất quán dữ liệu**.

Không tự suy luận rằng thêm `WHERE other.tenantId = $tenantId` sẽ làm Neo4j không duyệt các cạnh của tenant khác. Phân tích kế hoạch để biết bộ lọc được áp dụng ở giai đoạn nào, rồi thử thay đổi điểm neo hoặc cấu trúc dữ liệu nếu vẫn có fan-out lớn.

### 4.5. Lịch sử không giới hạn làm truy vấn hiện tại ngày càng đắt

Ví dụ mỗi thay đổi giá được lưu thành một node:

~~~text
(:Product)-[:HAD_PRICE]->(:PriceEvent {amount, effectiveAt})
~~~

Lịch sử giá cần cho kiểm toán và báo cáo, nhưng màn hình sản phẩm chỉ cần **giá hiện hành**. Khi số `PriceEvent` tăng qua nhiều năm, mỗi request đi hết lịch sử để lấy bản mới nhất sẽ tốn công ngày càng nhiều. Có thể giữ lịch sử và thêm một giá hiện hành được cập nhật có kiểm soát:

~~~text
(:Product {currentPrice, currentPriceUpdatedAt})
(:Product)-[:HAD_PRICE]->(:PriceEvent {amount, effectiveAt})
~~~

Giá hiện hành là một **bản sao suy ra từ lịch sử**: cần định nghĩa cách xử lý cập nhật đồng thời, chỉnh sửa hồi tố, mất đồng bộ và sửa chữa sai lệch. Nếu cần truy vấn giá theo thời điểm lịch sử, vẫn phải dùng sự kiện/phiên bản hợp lệ tại thời điểm đó. Việc materialize dữ liệu giúp giảm chi phí đọc nhưng làm tăng trách nhiệm ghi và đối soát.

## 5. Trường hợp điển hình: “đã có index nhưng vẫn rất chậm”

Xét truy vấn đề xuất người dùng tương tự theo các sản phẩm đã xem. Trước tiên, tạo index phù hợp để tìm người dùng gốc theo định danh trong tenant:

~~~cypher
CREATE RANGE INDEX user_tenant_id_lookup IF NOT EXISTS
FOR (u:User)
ON (u.tenantId, u.userId);
~~~

Câu truy vấn:

~~~cypher
PROFILE
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other <> u AND other.tenantId = $tenantId
WITH other, count(DISTINCT p) AS sharedProducts
RETURN other.userId AS candidateId, sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

Giả sử `PROFILE` cho thấy: Neo4j tìm đúng một node `u` bằng index; sang `Product` chỉ có 20 hàng; quay về `other` tạo 200.000 hàng; sau loại trùng và tổng hợp còn vài nghìn ứng viên. Nếu đây là kết quả trên dữ liệu đại diện, **điểm chi phí chính là hai bước đi qua quan hệ**.

Một số cách sửa thuần câu truy vấn vẫn đáng thử:

- Chỉ lấy các `VIEWED` còn giá trị trong khung thời gian nghiệp vụ, nếu quan hệ có thuộc tính thời gian và điều kiện đó thực sự thuộc yêu cầu.
- Lọc theo nhãn/type/thuộc tính đặc hiệu nếu có nguồn dữ liệu cho phép chọn lọc hơn.
- Bỏ những pattern lặp hoặc phép mở rộng không góp vào kết quả.
- Chọn chiến lược tính `DISTINCT`/tổng hợp có số hàng trung gian hợp lý; so sánh kế hoạch khi dùng `WITH`.

Nhưng nếu định nghĩa “người dùng chung sản phẩm” yêu cầu duyệt **mọi tương tác**, engine có thể vẫn phải đi qua một tập quan hệ rất lớn. Khi đó cần thảo luận thuật toán đề xuất hoặc cách lưu dữ liệu.

### 5.1. Phương án mô hình: lưu danh sách tương đồng đã tính

Nếu yêu cầu sản phẩm cho phép đề xuất không cần tính lại từ mọi lượt xem trong từng request, có thể tạo các cạnh tổng hợp:

~~~text
(:User)-[:SIMILAR_USER {
  score,
  calculatedAt,
  modelVersion
}]->(:User)
~~~

Một batch job tính trước số người tương đồng phù hợp cho mỗi user, chẳng hạn chỉ lưu tối đa 50 ứng viên trên mỗi người. Đường đọc trở thành:

~~~cypher
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[r:SIMILAR_USER]->(other:User)
WHERE other.tenantId = $tenantId
  AND r.calculatedAt >= $minCalculatedAt
RETURN other.userId AS candidateId,
       r.score AS similarityScore,
       r.calculatedAt AS calculatedAt
ORDER BY similarityScore DESC, candidateId ASC
LIMIT 10;
~~~

Độ lớn đầu vào lúc đọc có thể được khống chế bằng **số cạnh tương đồng lưu tối đa** trên mỗi `User`, nếu quy trình ghi thật sự duy trì giới hạn đó. Thứ tự `ORDER BY` vẫn cần để chọn top 10 nhưng chỉ xếp hạng một tập nhỏ hơn nhiều. Đổi lại:

| Lợi ích | Chi phí/giới hạn |
| --- | --- |
| Mỗi request đọc ít quan hệ hơn. | Phải xây dựng và chạy tiến trình tính điểm ban đầu. |
| Có thể đặt mức trần ứng viên trên mỗi user. | Kết quả có thể thiếu ứng viên mới hoặc bị cắt ở ngưỡng top-K. |
| Dễ cache kết quả giữa các request. | Cần xử lý cập nhật, hết hạn, xóa user và quyền truy cập. |
| Tách tải phân tích khỏi truy vấn trực tuyến. | Tốn thêm dung lượng lưu cạnh và công vận hành. |

Đây là **thay đổi ý nghĩa vận hành**: điểm được tính ở một thời điểm, có phiên bản thuật toán và độ trễ cập nhật. Nếu nghiệp vụ đòi độ chính xác tức thời trên mọi tương tác, không được thay câu truy vấn thời gian thực bằng cache mà không thống nhất yêu cầu.

## 6. Các phương án thay đổi mô hình và khi nào nên dùng

| Tình huống | Phương án cân nhắc | Đánh đổi bắt buộc |
| --- | --- | --- |
| Một node nối hàng triệu node chỉ để truy cập phần tử theo khóa. | Tìm phần tử bằng label + property index, hạn chế đi qua hub. | Phải bảo đảm khóa và phạm vi tenant đúng. |
| Một quan hệ chứa các lần tương tác lặp nhưng câu hỏi chỉ cần “đã từng”. | Duy trì cạnh tổng hợp duy nhất về mặt nghiệp vụ; giữ event nếu cần lịch sử. | Phải đồng bộ summary với event; quản lý cạnh tranh ghi. |
| Đường đi nhiều tầng rất đắt và truy vấn lặp lại. | Tiền tính liên kết rút gọn hoặc tập ứng viên top-K. | Dữ liệu có thể cũ, thêm khối lượng ghi và cập nhật. |
| Mỗi thuộc tính ít thay đổi được mô hình thành node riêng. | Dùng property trên node nguồn khi đúng ý nghĩa miền. | Có thể mất khả năng gắn quan hệ độc lập cho thực thể đó. |
| Đọc trạng thái hiện tại phải duyệt toàn bộ lịch sử. | Lưu trạng thái hiện tại đồng thời giữ lịch sử. | Cần bảo vệ nhất quán và hỗ trợ cập nhật hồi tố. |
| Một loại node trộn nhiều loại nghiệp vụ và bộ lọc khó chọn lọc. | Đánh giá thêm label/type rõ nghĩa, chỉ mục và điểm bắt đầu mới. | Chi phí quản lý schema, nhập dữ liệu và đảm bảo tính nhất quán label. |
| Query đa tenant thường xuyên mở rộng ngoài phạm vi cần thiết. | Đưa khóa tenant vào đường truy cập phù hợp, thiết kế phạm vi quan hệ/đọc. | Cần kiểm soát bảo mật, di chuyển tenant và quan hệ liên tenant hợp lệ. |

**Nguyên tắc:** thay đổi mô hình không nhất thiết là tạo thêm node. Đôi khi phương án tốt nhất là **bớt một quan hệ**, **thêm một thuộc tính**, hoặc **giữ một tập con đã tổng hợp**. Hãy lựa chọn theo những câu hỏi mà ứng dụng thực sự cần trả lời.

## 7. Mô hình dữ liệu có thể thay đổi kết quả, không chỉ tốc độ

Tối ưu bằng cách thay cấu trúc luôn cần kiểm tra *tính tương đương nghiệp vụ*.

### 7.1. Tổng hợp một cạnh có làm mất sự kiện?

Nếu biến mười quan hệ `VIEWED {at}` thành một quan hệ `HAS_VIEWED {count: 10}` thì câu hỏi “đã từng xem” vẫn có thể trả lời được, nhưng câu hỏi “xem lúc 9 giờ sáng hay 10 giờ tối” không thể dựng lại chính xác chỉ từ `count`. Nếu giữ event riêng, phải xác định nguồn dữ liệu chuẩn và cách tái tạo summary khi sai lệch.

### 7.2. Tạo shortcut có giữ đúng quyền truy cập?

Cạnh `SIMILAR_USER` đã tính từ dữ liệu của nhiều tenant có thể vô tình lộ liên kết giữa các nhóm người dùng. Dù truy vấn có `WHERE other.tenantId = $tenantId`, cần đánh giá cách batch job tạo cạnh, cách đọc quyền trên cả hai endpoint và cách xóa/thay đổi quyền. Một shortcut chỉ đúng khi **quan hệ mới phản ánh cùng ranh giới bảo mật** với dữ liệu gốc.

### 7.3. Đưa giá hiện tại lên Product có còn đúng lịch sử?

Một đơn hàng nên lưu giá **tại thời điểm đặt mua** chứ không phụ thuộc vào `Product.currentPrice` thay đổi sau này. Vì vậy, đôi khi cần `(:OrderLine {unitPriceAtPurchase})` tách khỏi `Product.currentPrice`. Đây không phải dư thừa vô ích: hai giá đại diện hai sự thật khác nhau.

### 7.4. Bỏ tầng trung gian có làm mất thuộc tính của quan hệ?

Mô hình:

~~~text
(:Order)-[:HAS_LINE]->(:OrderLine {
  quantity, unitPriceAtPurchase
})-[:OF_PRODUCT]->(:Product)
~~~

Lưu `OrderLine` như node giúp giữ số lượng và giá từng dòng hàng, kể cả khi một sản phẩm xuất hiện trong nhiều đơn. Rút gọn thành `(:Order)-[:CONTAINS]->(:Product)` mà không lưu các thuộc tính tương ứng sẽ làm mất thông tin nghiệp vụ. Nếu chọn quan hệ `CONTAINS {quantity, unitPriceAtPurchase}` thay cho node, cần xem dòng hàng có định danh, lịch sử, khuyến mại, hoàn trả hoặc quan hệ khác cần gắn riêng không.

Do đó, tối ưu mô hình phải đi cùng **mô hình hóa đúng sự thật**, không chỉ giảm số hop.

## 8. Khi nào tối ưu query vẫn là bước đúng?

Không nên viện lý do “mô hình kém” để bỏ qua một truy vấn có thể sửa dễ dàng. Một số thay đổi câu truy vấn có thể giảm công việc rất lớn mà không sửa schema:

### 8.1. Bắt đầu từ node chọn lọc

Nếu đã biết user, tìm theo khóa của user rồi duyệt quan hệ, thay vì quét mọi `VIEWED` trước khi lọc user:

~~~cypher
MATCH (u:User {tenantId: $tenantId, userId: $userId})-[:VIEWED]->(p:Product)
RETURN p.sku AS sku
ORDER BY sku ASC;
~~~

Chỉ mục trên `User(tenantId, userId)` có thể hỗ trợ tìm node nguồn. Kiểm tra kế hoạch thực tế: nếu số sản phẩm người dùng xem cũng rất lớn, khối lượng quan hệ cần duyệt có thể vẫn đáng kể.

### 8.2. Tránh nhân hàng không chủ đích

Ví dụ hai pattern độc lập có thể tạo tích Descartes:

~~~cypher
MATCH (u:User {userId: $userId}),
      (p:Product)
RETURN u.userId AS userId, p.sku AS sku
LIMIT 10;
~~~

Nếu cần sản phẩm **người đó đã xem**, thêm pattern quan hệ và điều kiện tenant tương ứng sẽ thay đổi cả tính đúng đắn lẫn hiệu năng. Không dùng `LIMIT 10` như cách che giấu một `MATCH` thiếu liên kết.

### 8.3. Áp dụng giới hạn đúng giai đoạn

~~~cypher
MATCH (p:Product)<-[v:VIEWED]-(:User)
WITH p, count(v) AS viewCount
ORDER BY viewCount DESC, p.sku ASC
LIMIT 10
RETURN p.sku AS sku, viewCount
ORDER BY viewCount DESC, sku ASC;
~~~

Đây là **10 sản phẩm được xem nhiều nhất trên toàn bộ dữ liệu**. Neo4j vẫn cần tính đủ số lượt xem theo sản phẩm để xếp hạng chính xác; `LIMIT 10` cuối phép tổng hợp không xóa chi phí đếm toàn bộ quan hệ. Nếu nghiệp vụ chỉ hỏi “top sản phẩm của tenant X trong 24 giờ”, đổi điều kiện truy vấn có thể làm giảm đầu vào **khi mô hình lưu đủ tenant và thời gian ở vị trí lọc hữu ích**.

### 8.4. Dùng các kiểu index cho đúng vấn đề

Index có thể giúp chọn node theo thuộc tính, tra cứu phạm vi hoặc hỗ trợ truy vấn văn bản; constraint giúp bảo vệ khóa nghiệp vụ. Không có index nào biến một phép liệt kê tất cả đường đi hợp lệ thành tác vụ hằng số. Tạo index tràn lan còn làm tăng chi phí ghi và dung lượng lưu trữ.

Nếu một câu truy vấn đã lấy đúng một node bằng index rồi tốn chủ yếu ở mở rộng quan hệ, hãy chuyển trọng tâm từ “thêm index nào?” sang “vì sao phải mở rộng những quan hệ này?”.

## 9. Phương pháp ra quyết định dựa trên bằng chứng

Đề xuất quy trình sáu bước cho một truy vấn Neo4j chậm:

1. **Chốt kết quả nghiệp vụ:** cần trả thực thể nào, theo thời gian/tenant nào, có cần dữ liệu mới tức thời không? Phân biệt yêu cầu chính xác tuyệt đối với top-K gợi ý chấp nhận tính gần đúng.
2. **Lấy mẫu dữ liệu đại diện:** tổng số node/relationship, độ lệch theo tenant, top bậc cao, tỷ lệ null/trùng, độ dài lịch sử. Dữ liệu ít ở dev có thể che giấu supernode xuất hiện ở production.
3. **Đo truy vấn hiện tại:** lưu `PROFILE`, tham số, số hàng, DB Hits, thời gian p50/p95/p99 từ ứng dụng, cùng phiên bản Neo4j và cấu hình cần thiết để so sánh.
4. **Sửa nguyên nhân ở mức truy vấn trước:** bỏ Cartesian product vô ý, bắt đầu từ điểm lọc chọn lọc, sử dụng index đúng, hạn chế projection dư thừa. Đo lại cùng bộ dữ liệu.
5. **Nếu chi phí bắt buộc vẫn cao, thử mô hình mới:** dựng nguyên mẫu trên dữ liệu sao chép hoặc fixture, tạo cạnh tổng hợp/shortcut, tách lịch sử, chọn cách giảm fan-out; ghi rõ tác động lên semantics và độ mới dữ liệu.
6. **Chạy kiểm thử kết quả và vận hành:** so sánh kết quả trên tập tình huống chuẩn, tải đọc/ghi, dung lượng, tần suất cập nhật, an toàn tenant, khả năng backfill và rollback migration.

### 9.1. Bảng đo trước/sau

Trước khi thay schema, chuẩn bị bảng theo **số liệu đo thực tế**, tránh tự coi các giá trị minh họa là kết quả chuẩn:

| Chỉ số | Trước thay đổi | Sau sửa Cypher/index | Sau đổi mô hình |
| --- | --- | --- | --- |
| Thời gian p50/p95 đọc (ms) | *đo* | *đo* | *đo* |
| `Rows` ở bước mở rộng lớn nhất | *đo* | *đo* | *đo* |
| `DB Hits` | *đo* | *đo* | *đo* |
| Kết quả đúng trên tập kiểm thử | *đo* | *đo* | *đo* |
| Độ trễ cập nhật dữ liệu đề xuất | *đo* | *đo* | *đo* |
| Tốc độ ghi và độ lớn dữ liệu | *đo* | *đo* | *đo* |
| Tỷ lệ lỗi / vi phạm bảo mật tenant | *đo* | *đo* | *đo* |

Các con số nên được lấy từ cùng khối lượng dữ liệu, bộ tham số, điều kiện cache và cấu hình máy có thể so sánh. Thử cả người dùng bình thường lẫn người dùng có nhiều tương tác, sản phẩm rất phổ biến, tenant lớn và dữ liệu mới phát sinh. Chỉ tối ưu theo truy vấn “dễ” có thể làm p50 đẹp nhưng p99 vẫn kém.

### 9.2. Chi phí migration là một phần của giải pháp

Nếu chuyển từ các quan hệ `VIEWED` dạng sự kiện sang `HAS_VIEWED` dạng tổng hợp, cần trả lời rõ:

- Dữ liệu cũ được backfill như thế nào và phát hiện/cập nhật event phát sinh trong lúc backfill ra sao?
- Tránh tạo trùng relationship tổng hợp khi có nhiều worker ghi đồng thời bằng cơ chế nào?
- Giữ cả hai biểu diễn trong bao lâu và kiểm tra tính nhất quán bằng phép đối soát nào?
- Đọc ứng dụng chuyển sang biểu diễn mới theo cách nào, rollback khi phát hiện sai có làm mất lịch sử không?
- Index, constraint, tài nguyên lưu trữ và đường cập nhật Java Driver/Spring Data Neo4j thay đổi ra sao?

Một tối ưu chỉ tăng tốc câu truy vấn nhưng làm dữ liệu sai hoặc khó duy trì thì chưa phải tối ưu thành công.

## 10. Bài tập tình huống

### Bài tập 1 — Chẩn đoán từ PROFILE

Một truy vấn tìm 10 người dùng tương đồng có kế hoạch như sau (số liệu **giả định**):

| Giai đoạn | Hàng đầu ra |
| --- | ---: |
| Tìm user bằng index | 1 |
| Mở rộng user → product | 24 |
| Mở rộng product → other users | 320.000 |
| Lọc tenant và bỏ user ban đầu | 110.000 |
| `Aggregation` theo ứng viên | 5.000 |
| Top 10 | 10 |

Hãy trả lời: bước nào gây tăng hàng lớn nhất? Vì sao thêm index trên `User.userId` có thể không giải quyết được? Những câu hỏi nào về phân bố degree, tenant và lịch sử `VIEWED` cần được kiểm chứng trước khi sửa mô hình?

### Bài tập 2 — Giữ đúng nghiệp vụ

Một nhóm muốn thay mọi relationship `VIEWED {at}` thành một cạnh `HAS_VIEWED {count}`. Liệt kê ít nhất ba truy vấn **giữ nguyên kết quả** hoặc có thể suy ra từ dữ liệu tổng hợp và ba truy vấn **không thể trả lời chính xác** nếu xóa hoàn toàn lịch sử event. Đề xuất cách giữ event và summary mà không có mâu thuẫn quá lâu.

### Bài tập 3 — Thiết kế cho top 10 theo tenant

Hệ thống có một node chủ đề phổ biến nối đến hàng triệu sản phẩm của nhiều tenant. Người dùng cần top 10 sản phẩm gần đây của **một tenant**. Hãy đề xuất hai phương án truy cập khác nhau, phác thảo Cypher, rồi trình bày cách kiểm tra `PROFILE` và quyền truy cập tenant. Đừng giả định thêm `LIMIT 10` ở cuối sẽ tự giảm số quan hệ phải duyệt.

### Bài tập 4 — Cân nhắc shortcut

Đối với quan hệ `SIMILAR_USER` được tính mỗi đêm, sản phẩm yêu cầu gợi ý phải phản ánh hành vi mới trong tối đa năm phút. Phương án batch mỗi đêm có đáp ứng không? Nêu ít nhất hai cách thay đổi kiến trúc (ví dụ tính cập nhật gia tăng hoặc kết hợp kết quả đã tính với tín hiệu mới), rồi phân tích chi phí và bài kiểm thử cần có.

### Bài tập 5 — Quyết định giữa OrderLine node và relationship

Một đơn có thể có nhiều dòng hàng, mỗi dòng chứa số lượng, giá tại thời điểm mua và thông tin hoàn trả. Nhóm muốn bỏ `OrderLine` node để giảm một hop. Hãy xác định thông tin nào vẫn có thể lưu trên relationship, thông tin nào cần định danh/quan hệ độc lập và bộ kiểm thử tính đúng đắn cần chạy khi migration.

## 11. Câu hỏi tự kiểm tra trước khi sửa mô hình

Khi một truy vấn chậm lặp lại, hãy kiểm tra theo thứ tự:

1. Neo4j đã bắt đầu từ node đủ chọn lọc và dùng index hợp lý chưa?
2. Toán tử nào sinh ra nhiều `Rows` hoặc `DB Hits` nhất? Số đó tăng như thế nào theo tenant, thời gian và degree?
3. Có phải truy vấn chỉ cần một kết quả nhỏ nhưng vẫn phải đọc một lượng quan hệ lớn theo đúng cấu trúc dữ liệu hiện tại không?
4. Chi phí có đến từ một số ít supernode, lịch sử không giới hạn hoặc dữ liệu bị nhân bản dưới dạng relationship không?
5. Có thể thay đổi thuật toán hoặc lưu dữ liệu tổng hợp mà **giữ đúng bất biến nghiệp vụ, quyền truy cập và yêu cầu độ mới** không?
6. Giải pháp mới được đo và kiểm thử như thế nào, kể cả chi phí ghi, migration và các truy vấn khác dùng chung mô hình?

**Điểm mấu chốt:** câu truy vấn quyết định **cách** Neo4j đi qua đồ thị; mô hình dữ liệu quyết định **những con đường và lượng quan hệ nào tồn tại để phải đi qua**. Khi `PROFILE` cho thấy phần lớn công việc là mở rộng những quan hệ hợp lệ nhưng quá đông, việc chỉ chỉnh `MATCH`/`WITH`/`LIMIT` thường có giới hạn. Hãy chứng minh nút thắt bằng dữ liệu, sau đó chọn thay đổi mô hình phù hợp với câu hỏi nghiệp vụ và kiểm tra cả hiệu năng lẫn tính đúng đắn.
