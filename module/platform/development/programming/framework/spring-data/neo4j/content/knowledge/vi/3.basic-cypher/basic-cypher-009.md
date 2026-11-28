# ORDER BY, SKIP, LIMIT và thứ tự kết quả ổn định

Một truy vấn Neo4j có thể tìm đúng các node và relationship nhưng vẫn trả về kết quả theo thứ tự khác nhau giữa những lần chạy. Nếu ứng dụng hiển thị danh sách sản phẩm, khách hàng hoặc đơn hàng theo trang, sự khác biệt này có thể khiến một bản ghi xuất hiện ở hai trang hoặc bị bỏ sót. Trong Cypher, `ORDER BY`, `SKIP` và `LIMIT` phối hợp để sắp xếp và phân trang kết quả.

Spring Data Neo4j (SDN) cho phép đặt các mệnh đề này trong truy vấn repository bằng `@Query`, sau đó truyền số dòng cần bỏ qua và số dòng cần lấy qua tham số. Để phân trang đáng tin cậy, cần xác định rõ đơn vị dữ liệu đang phân trang, xây dựng thứ tự có tiêu chí phân xử khi các giá trị bằng nhau, và hiểu ảnh hưởng của dữ liệu thay đổi giữa các lần gọi.

Sau bài học, bạn có thể:

- Sắp xếp kết quả theo một hoặc nhiều tiêu chí bằng `ORDER BY`.
- Giải thích vì sao kết quả cần một khóa phụ duy nhất để có thứ tự xác định.
- Dùng `SKIP` và `LIMIT` đúng thứ tự để lấy một phần kết quả.
- Phân trang đúng đơn vị node hoặc nhóm sau `DISTINCT` và phép tổng hợp.
- Chọn phân trang theo vị trí hoặc theo khóa khi tích hợp Cypher vào repository.

## 1. Thứ tự kết quả trong Cypher

`MATCH` xác định các dòng phù hợp với mẫu đồ thị, còn `RETURN` chọn dữ liệu cần trả về. Nếu không có `ORDER BY`, ứng dụng không được dựa vào thứ tự các dòng trả về. Neo4j không cam kết kết quả luôn theo thứ tự tạo node, thứ tự ID nội bộ hay thứ tự của lần chạy trước.

Ví dụ, truy vấn sau tìm các sản phẩm:

~~~cypher
MATCH (p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
~~~

Truy vấn không quy định sản phẩm nào phải xuất hiện trước. Muốn hiển thị giá từ cao xuống thấp, hãy thêm `ORDER BY`:

~~~cypher
MATCH (p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
ORDER BY price DESC
~~~

`ASC` sắp xếp tăng dần và là chiều mặc định; `DESC` sắp xếp giảm dần. Có thể viết `ORDER BY price` thay cho `ORDER BY price ASC`. Hãy dùng alias đã khai báo trong `RETURN` hoặc biểu thức thuộc phạm vi của mệnh đề để diễn đạt tiêu chí sắp xếp rõ ràng.

Một số kiểu sắp xếp thường gặp:

~~~cypher
// Tên tăng dần
ORDER BY name ASC

// Giá giảm dần
ORDER BY price DESC

// Ngày tạo mới nhất trước, sau đó tên tăng dần
ORDER BY createdAt DESC, name ASC
~~~

Khi có nhiều tiêu chí, Cypher ưu tiên tiêu chí đứng trước. Chỉ khi hai dòng có cùng giá trị ở tiêu chí trước, tiêu chí tiếp theo mới được dùng để phân định. Vì vậy, `ORDER BY price DESC, name ASC` trước tiên xếp giá từ cao xuống thấp; các sản phẩm cùng giá được xếp theo tên.

## 2. Tạo thứ tự xác định bằng khóa phân xử

Một danh sách có thể đã được sắp xếp nhưng vẫn chưa có thứ tự xác định nếu nhiều dòng có cùng giá trị ở tất cả tiêu chí. Ví dụ:

~~~cypher
MATCH (p:Product)
RETURN p.name AS name,
       p.price AS price
ORDER BY price DESC
LIMIT 10
~~~

Nếu nhiều sản phẩm có cùng giá, truy vấn không xác định sản phẩm nào đứng trước trong nhóm đồng giá. Khi lấy trang đầu, một sản phẩm có thể được chọn ở lần chạy này nhưng nằm ngoài giới hạn ở lần chạy khác.

Hãy thêm một tiêu chí phân xử có giá trị duy nhất trong tập kết quả, chẳng hạn mã SKU:

~~~cypher
MATCH (p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
ORDER BY price DESC, sku ASC
LIMIT 10
~~~

Trong ví dụ, `price` quyết định thứ tự chính; `sku` quyết định thứ tự giữa các sản phẩm cùng giá. Nếu `sku` là duy nhất và không rỗng theo quy tắc dữ liệu của ứng dụng, mỗi sản phẩm có một vị trí xác định trong thứ tự đó. Có thể bảo vệ tính duy nhất của mã bằng constraint:

~~~cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE
~~~

Uniqueness constraint ngăn các giá trị SKU khác null bị trùng; ứng dụng vẫn cần bảo đảm SKU bắt buộc phải có giá trị để khóa phân xử luôn hoàn chỉnh.

Một thứ tự xác định cần đáp ứng hai điều:

1. Tiêu chí sắp xếp phản ánh đúng yêu cầu nghiệp vụ, ví dụ giá giảm dần hoặc thời điểm tạo mới nhất trước.
2. Tổ hợp các tiêu chí phân biệt được mọi dòng trong tập kết quả. Thường thêm khóa duy nhất của node làm tiêu chí cuối cùng.

Khóa phân xử phải duy nhất ở đúng cấp độ dòng đang trả về. Nếu truy vấn trả về một dòng cho mỗi sản phẩm, SKU duy nhất có thể đủ. Nếu truy vấn trả về một dòng cho mỗi lần mua, SKU không đủ vì một sản phẩm có thể xuất hiện trong nhiều lần mua; cần thêm định danh đơn hàng hoặc định danh sự kiện.

### Xử lý giá trị trùng và null

Với nhiều tiêu chí, hãy ghi rõ chiều sắp xếp cho từng tiêu chí để người đọc hiểu quy tắc:

~~~cypher
MATCH (p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
ORDER BY price DESC, name ASC, sku ASC
~~~

Neo4j xếp giá trị `null` sau các giá trị khác khi sắp xếp tăng dần và trước các giá trị khác khi sắp xếp giảm dần. Nếu trường dùng làm khóa phân trang có thể là `null`, cần xác định rõ cách xử lý trước khi dùng nó trong cursor hoặc khóa phân xử. Với mã định danh, nên bảo đảm giá trị tồn tại và duy nhất.

## 3. Phân trang bằng SKIP và LIMIT

`SKIP` bỏ qua một số dòng đầu tiên trong thứ tự đã xác định; `LIMIT` giới hạn số dòng được trả về. Khi kết hợp, hãy đặt `ORDER BY` trước, sau đó `SKIP`, rồi `LIMIT`:

~~~cypher
MATCH (p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
ORDER BY price DESC, sku ASC
SKIP 20
LIMIT 10
~~~

Truy vấn trên sắp xếp toàn bộ danh sách theo giá giảm dần và SKU tăng dần, bỏ qua 20 dòng đầu rồi lấy tối đa 10 dòng tiếp theo. Đây là trang thứ ba nếu mỗi trang có 10 dòng và trang được đánh số từ 1.

Với số dòng mỗi trang là `pageSize` và chỉ số trang bắt đầu từ 0 là `page`, số dòng cần bỏ qua được tính như sau:

~~~text
skip = page * pageSize
~~~

Ví dụ với `pageSize = 10`:

| Chỉ số trang (`page`) | `SKIP` | `LIMIT` |
|---:|---:|---:|
| 0 | 0 | 10 |
| 1 | 10 | 10 |
| 2 | 20 | 10 |
| 3 | 30 | 10 |

Trong ứng dụng, không nên ghép số trang trực tiếp vào chuỗi Cypher. Hãy truyền chúng qua tham số:

~~~cypher
MATCH (p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
ORDER BY price DESC, sku ASC
SKIP $skip
LIMIT $limit
~~~

`$skip` và `$limit` là tham số số nguyên được truyền khi thực thi truy vấn. Ứng dụng cần kiểm tra `skip` không âm, `limit` lớn hơn 0 và giới hạn kích thước trang tối đa theo chính sách của hệ thống. Việc giới hạn kích thước trang giúp tránh một yêu cầu vô tình tải quá nhiều dữ liệu.

Không dùng `LIMIT` một mình để giả định rằng Neo4j sẽ trả về cùng một nhóm bản ghi trong mọi lần chạy. Nếu không có `ORDER BY`, tập dòng được lấy có thể thay đổi.

## 4. Phân trang đúng đơn vị dữ liệu

Một dòng trong kết quả Cypher không phải lúc nào cũng tương ứng với một node. Khi một node kết nối với nhiều node khác, `MATCH` có thể tạo nhiều dòng cho cùng node nguồn. Vì thế, trước khi đặt `SKIP` và `LIMIT`, cần xác định ứng dụng muốn phân trang theo node, relationship hay nhóm kết quả.

Ví dụ, mỗi khách hàng có thể mua nhiều sản phẩm:

~~~cypher
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN c.customerCode AS customerCode,
       p.sku AS sku
ORDER BY customerCode ASC, sku ASC
SKIP $skip
LIMIT $limit
~~~

Truy vấn này phân trang các cặp khách hàng–sản phẩm. Một khách hàng có nhiều sản phẩm có thể chiếm nhiều dòng và xuất hiện trên nhiều trang. Nếu giao diện cần phân trang khách hàng, phải lấy danh sách khách hàng trước rồi mới mở rộng quan hệ:

~~~cypher
MATCH (c:Customer)
WITH c
ORDER BY c.customerCode ASC
SKIP $skip
LIMIT $limit
OPTIONAL MATCH (c)-[:PURCHASED]->(p:Product)
RETURN c.customerCode AS customerCode,
       c.name AS customerName,
       collect(p.sku) AS productSkus
ORDER BY customerCode ASC
~~~

Ở đây, `SKIP` và `LIMIT` áp dụng cho các node `Customer` trước khi truy vấn sản phẩm liên quan. `OPTIONAL MATCH` vẫn giữ khách hàng chưa mua sản phẩm nào; `collect` gom các SKU thành danh sách. Mệnh đề `ORDER BY` cuối cùng xác định thứ tự các dòng trả về sau bước mở rộng và tổng hợp.

Nếu muốn mỗi sản phẩm chỉ xuất hiện một lần dù có nhiều đường liên kết dẫn đến nó, hãy cân nhắc `DISTINCT` trước khi phân trang:

~~~cypher
MATCH (:Customer)-[:PURCHASED]->(p:Product)
WITH DISTINCT p
ORDER BY p.sku ASC
SKIP $skip
LIMIT $limit
RETURN p.sku AS sku,
       p.name AS name
ORDER BY sku ASC
~~~

`DISTINCT` loại bỏ các dòng trùng theo biến được chọn. Thứ tự ở `WITH` xác định nhóm sản phẩm được chọn cho trang; `ORDER BY` cuối cùng xác định thứ tự hiển thị. Việc đặt giới hạn trước hay sau `DISTINCT` làm thay đổi ý nghĩa kết quả, nên hãy sắp xếp các bước theo đúng đơn vị cần phân trang.

## 5. Sắp xếp và giới hạn sau phép tổng hợp

Khi truy vấn dùng hàm tổng hợp như `count`, `sum` hoặc `collect`, hãy hoàn thành việc nhóm dữ liệu trước khi sắp xếp và giới hạn các nhóm. Ví dụ, tìm 5 sản phẩm được nhiều khách hàng mua nhất:

~~~cypher
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
WITH p, count(DISTINCT c) AS customerCount
RETURN p.sku AS sku,
       p.name AS name,
       customerCount
ORDER BY customerCount DESC, sku ASC
LIMIT 5
~~~

`WITH` tạo một dòng cho mỗi sản phẩm và tính số khách hàng khác nhau đã mua sản phẩm đó. `ORDER BY` xếp số khách hàng giảm dần; SKU tăng dần phân xử các sản phẩm có cùng số khách hàng. `LIMIT 5` vì vậy chọn 5 nhóm sản phẩm đứng đầu, không phải 5 dòng mua hàng ban đầu.

`ORDER BY` cũng có thể điều khiển thứ tự các dòng được đưa vào phép tổng hợp `collect`:

~~~cypher
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
WITH c, p
ORDER BY c.customerCode ASC, p.name ASC, p.sku ASC
RETURN c.customerCode AS customerCode,
       collect(p.name) AS productNames
ORDER BY customerCode ASC
~~~

Trong trường hợp này, thứ tự được thiết lập ở `WITH` trước khi `collect` tạo danh sách sản phẩm cho từng khách hàng. Nếu ứng dụng yêu cầu thứ tự của các phần tử trong danh sách, hãy sắp xếp các dòng đầu vào cho phép tổng hợp thay vì trông chờ thứ tự phát sinh từ `MATCH`.

## 6. Phân trang theo vị trí và phân trang theo khóa

### Offset pagination với SKIP

`SKIP` và `LIMIT` phù hợp với giao diện có số trang rõ ràng, ví dụ trang 1, 2, 3. Công thức phổ biến là:

~~~text
skip = page * pageSize
limit = pageSize
~~~

Ưu điểm là cách tính trang đơn giản và người dùng có thể chuyển đến một trang bất kỳ. Tuy nhiên, khi `SKIP` lớn, cơ sở dữ liệu vẫn phải xử lý và bỏ qua nhiều dòng trước khi trả về trang cần lấy. Các trang sâu vì vậy có thể tốn kém hơn.

Offset pagination còn chịu ảnh hưởng khi dữ liệu thay đổi giữa hai lần gọi. Giả sử trang đầu đã được lấy, sau đó một sản phẩm mới được chèn vào đầu danh sách. Khi ứng dụng lấy trang tiếp theo bằng `SKIP 10`, ranh giới trang đã dịch chuyển; một sản phẩm có thể lặp lại hoặc bị bỏ qua. `ORDER BY` ổn định giải quyết sự mơ hồ khi sắp xếp, nhưng không đóng băng tập dữ liệu giữa các request.

### Keyset pagination với khóa tiếp tục

Với danh sách lớn hoặc thường xuyên thay đổi, có thể dùng keyset pagination: thay vì đếm số dòng cần bỏ qua, request tiếp theo gửi giá trị của dòng cuối cùng ở trang trước làm cursor. Ví dụ, sắp xếp sản phẩm theo SKU tăng dần:

~~~cypher
MATCH (p:Product)
WHERE p.sku > $afterSku
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
ORDER BY sku ASC
LIMIT $limit
~~~

Với trang đầu tiên, chạy truy vấn mà bỏ mệnh đề `WHERE`. Từ trang tiếp theo, thêm điều kiện `WHERE p.sku > $afterSku` và truyền SKU cuối cùng của trang trước vào `afterSku`. Vì SKU là duy nhất và thứ tự tăng dần, truy vấn tiếp tục từ vị trí sau bản ghi đó mà không cần bỏ qua toàn bộ các dòng trước.

Nếu thứ tự gồm nhiều tiêu chí, cursor phải chứa đủ các giá trị phân xử. Ví dụ sắp xếp theo tên tăng dần, sau đó SKU tăng dần:

~~~cypher
MATCH (p:Product)
WHERE p.name > $afterName
   OR (p.name = $afterName AND p.sku > $afterSku)
RETURN p.sku AS sku,
       p.name AS name,
       p.price AS price
ORDER BY name ASC, sku ASC
LIMIT $limit
~~~

Điều kiện `WHERE` mô tả thứ tự từ điển của cặp `(name, sku)`: lấy những dòng có tên lớn hơn tên cursor, hoặc có cùng tên nhưng SKU lớn hơn SKU cursor. Các trường cursor cần có giá trị, cùng quy tắc so sánh và cùng chiều sắp xếp ở mọi request. Nên ưu tiên khóa không rỗng và ít thay đổi; nếu giá trị sắp xếp thay đổi giữa các lần lấy trang, bản ghi vẫn có thể di chuyển qua vị trí cursor.

Keyset pagination giảm công việc bỏ qua các dòng ở trang sâu và thường ổn định hơn khi có bản ghi mới được thêm trước cursor. Tuy nhiên, nó không tạo ra một ảnh chụp dữ liệu bất biến: việc xóa bản ghi, thay đổi khóa sắp xếp hoặc thay đổi quan hệ vẫn có thể ảnh hưởng kết quả các trang sau. Nếu nghiệp vụ cần một tập kết quả nhất quán xuyên suốt nhiều lần gọi, cần thiết kế thêm cơ chế snapshot hoặc mốc dữ liệu phù hợp.

## 7. Tích hợp truy vấn phân trang trong Spring Data Neo4j

Một repository có thể dùng `@Query` để khai báo Cypher và nhận các tham số phân trang. Ví dụ dưới đây trả về projection chỉ chứa thông tin cần cho màn hình danh sách. Trong dự án Java, đặt `ProductSummary` và `ProductRepository` ở hai file riêng vì mỗi file chỉ có một kiểu top-level được khai báo `public`:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.math.BigDecimal;
import java.util.List;

public interface ProductSummary {
    String getSku();
    String getName();
    BigDecimal getPrice();
}

public interface ProductRepository
        extends Neo4jRepository<Product, Long> {

    @Query("""
        MATCH (p:Product)
        RETURN p.sku AS sku,
               p.name AS name,
               p.price AS price
        ORDER BY price DESC, sku ASC
        SKIP $skip
        LIMIT $limit
        """)
    List<ProductSummary> findProductPage(
        @Param("skip") long skip,
        @Param("limit") long limit
    );
}
~~~

Các alias `sku`, `name` và `price` khớp với getter trong projection. `skip` và `limit` được truyền như tham số truy vấn; không nối chuỗi để tạo câu Cypher. Ví dụ dùng `Long` làm ID của entity `Product`, còn `sku` là khóa nghiệp vụ dùng làm tiêu chí sắp xếp ổn định.

Ở tầng service, tính offset và xác thực đầu vào trước khi gọi repository:

~~~java
public List<ProductSummary> getProductPage(int page, int pageSize) {
    if (page < 0) {
        throw new IllegalArgumentException("page must be non-negative");
    }
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize must be between 1 and 100");
    }

    long skip = Math.multiplyExact((long) page, pageSize);
    return productRepository.findProductPage(skip, pageSize);
}
~~~

`Math.multiplyExact` giúp phát hiện tràn số khi tính offset. Giới hạn `pageSize` là ví dụ chính sách của ứng dụng; hệ thống thực tế cần chọn ngưỡng phù hợp với dung lượng dữ liệu và trải nghiệm giao diện.

Với truy vấn tùy chỉnh, hãy kiểm tra khả năng hỗ trợ phân trang của kiểu repository và phiên bản Spring Data Neo4j đang dùng trước khi giả định rằng chỉ cần thêm `Pageable` là truy vấn sẽ tự động được sửa. Cách truyền `skip` và `limit` tường minh như ví dụ giúp thể hiện trực tiếp hành vi Cypher. Nếu API cần tổng số bản ghi, phải thiết kế truy vấn đếm phù hợp; không nên suy ra tổng số dòng chỉ từ kích thước trang hiện tại.

## 8. Hiệu năng và những lỗi thường gặp

`ORDER BY` có thể cần sắp xếp một tập kết quả lớn. Khi truy vấn chậm, dùng `EXPLAIN` để xem kế hoạch thực thi và `PROFILE` để quan sát số dòng, phép toán và lượng công việc thực tế. Một số nguyên tắc giúp truy vấn dễ tối ưu:

- Giới hạn tập dữ liệu sớm bằng label, điều kiện `WHERE` và các index phù hợp trước khi sắp xếp.
- Chỉ trả về các property cần dùng; tránh tải toàn bộ entity graph nếu màn hình chỉ cần vài trường.
- Dùng khóa sắp xếp có ý nghĩa và ổn định; thêm khóa duy nhất ở cuối để phân xử.
- Phân trang sau `DISTINCT` hoặc phép tổng hợp nếu đơn vị hiển thị là node hoặc nhóm, không phải từng dòng kết nối.
- Với trang sâu hoặc dữ liệu thay đổi thường xuyên, cân nhắc cursor thay cho `SKIP` lớn.
- Không giả định index sẽ luôn loại bỏ bước sắp xếp; hãy kiểm tra kế hoạch thực thi của truy vấn thực tế.

Các lỗi cần tránh:

**Dùng LIMIT mà không ORDER BY.** Kích thước trang có giới hạn nhưng nhóm bản ghi được chọn không có thứ tự được bảo đảm.

**Sắp xếp theo tiêu chí không duy nhất.** `ORDER BY price DESC` chưa xác định thứ tự giữa các sản phẩm cùng giá. Hãy thêm SKU hoặc khóa phân biệt phù hợp.

**Đặt LIMIT trước DISTINCT hoặc tổng hợp sai mục tiêu.** Giới hạn dòng quan hệ trước khi gom nhóm có thể làm mất node hoặc nhóm mà người dùng muốn xem.

**Phân trang dòng quan hệ trong khi giao diện cần phân trang node.** Một khách hàng có nhiều sản phẩm có thể chiếm nhiều dòng; hãy chọn trang khách hàng trước rồi mới mở rộng quan hệ.

**Nghĩ rằng ORDER BY giữ nguyên tập dữ liệu giữa nhiều request.** Thứ tự xác định không ngăn bản ghi mới, bản ghi bị xóa hoặc thuộc tính sắp xếp bị cập nhật làm dịch chuyển ranh giới trang.

**Dùng cursor thiếu tiêu chí phân xử.** Nếu cursor chỉ lưu tên nhưng nhiều sản phẩm có cùng tên, trang tiếp theo có thể bỏ sót những sản phẩm còn lại trong nhóm tên đó. Cursor phải chứa toàn bộ tổ hợp khóa tạo nên thứ tự.

## 9. Tự kiểm tra

1. Vì sao truy vấn có `LIMIT 10` nhưng không có `ORDER BY` không phù hợp để xây dựng danh sách phân trang?
2. Nếu hai sản phẩm có cùng giá, cần thêm tiêu chí nào để thứ tự giữa chúng được xác định?
3. Với `page = 4` và `pageSize = 20`, giá trị `SKIP` là bao nhiêu?
4. Truy vấn `MATCH (c:Customer)-[:PURCHASED]->(p:Product)` đang phân trang khách hàng hay các cặp khách hàng–sản phẩm?
5. Khi nào keyset pagination phù hợp hơn offset pagination? Cursor cần lưu những giá trị nào nếu thứ tự gồm hai tiêu chí?

**Bài tập thực hành:** Xây dựng API liệt kê sản phẩm theo giá giảm dần. Mỗi trang có 15 sản phẩm; các sản phẩm cùng giá phải được sắp theo SKU tăng dần. Viết Cypher dùng `ORDER BY`, `SKIP` và `LIMIT`; tạo repository method nhận hai tham số phân trang; sau đó mô tả cách chuyển truy vấn sang keyset pagination khi số trang lớn. Kiểm tra thêm trường hợp nhiều sản phẩm đồng giá và trường hợp có sản phẩm mới được thêm vào giữa hai lần gọi trang.

Khi thiết kế danh sách cho ứng dụng Spring Data Neo4j, hãy xác định đơn vị dữ liệu trước, tạo thứ tự có khóa phân xử duy nhất, rồi mới áp dụng giới hạn. Cách sắp xếp và phân trang cần phản ánh đúng dữ liệu mà giao diện muốn hiển thị và cách dữ liệu có thể thay đổi trong quá trình người dùng duyệt.
