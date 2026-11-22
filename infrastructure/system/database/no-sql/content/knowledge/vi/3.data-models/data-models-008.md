# Quan hệ giữa mô hình dữ liệu với khả năng lập chỉ mục

Khi thiết kế cơ sở dữ liệu NoSQL, chọn **mô hình dữ liệu** và chọn **chỉ mục** là hai quyết định liên quan chặt chẽ. Mô hình dữ liệu quyết định dữ liệu được biểu diễn thành bảng, tài liệu, cặp khóa–giá trị, quan hệ đồ thị hay các hàng được nhóm theo khóa phân vùng. Chỉ mục (*index*) tạo ra đường truy cập để hệ quản trị tìm đúng phần dữ liệu cần đọc mà không phải xem xét mọi bản ghi.

Tuy nhiên, có ba điều cần phân biệt ngay từ đầu:

- **Mô hình dữ liệu** không tự động quyết định toàn bộ khả năng lập chỉ mục. Hai DBMS cùng theo mô hình tài liệu có thể hỗ trợ kiểu index, cú pháp truy vấn, điều kiện và bảo đảm cập nhật rất khác nhau.
- **Có index** không đồng nghĩa **truy vấn chắc chắn dùng được index**. Điều này còn phụ thuộc điều kiện lọc, cách sắp xếp, độ chọn lọc, thứ tự trường trong index, cách phân vùng và bộ tối ưu hóa truy vấn.
- **Không có index phụ phù hợp** không nhất thiết làm dữ liệu không thể truy vấn. Hệ thống có thể quét dữ liệu, nhưng chi phí sẽ tăng nhanh khi dữ liệu lớn hoặc truy vấn phải trải rộng nhiều phân vùng.

Hiểu quan hệ giữa dữ liệu và index giúp trả lời câu hỏi thực tế hơn việc chỉ hỏi “DBMS này có hỗ trợ index không?”: **Mẫu truy vấn nào được phục vụ tốt bởi cách tổ chức dữ liệu và các đường truy cập có sẵn?**

## 1. Mô hình dữ liệu, mẫu truy cập và chỉ mục nằm ở những tầng nào?

Giả sử hệ thống bán hàng có các yêu cầu:

1. Tìm sản phẩm theo mã sản phẩm.
2. Liệt kê sản phẩm trong một danh mục, theo mức giá tăng dần.
3. Tìm sản phẩm có nội dung mô tả chứa các từ khóa.
4. Lấy 20 đơn hàng mới nhất của một khách hàng.

Tất cả đều làm việc với dữ liệu sản phẩm hoặc đơn hàng, nhưng chúng yêu cầu những **đường truy cập** khác nhau. Có thể nhìn theo bốn tầng:

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Mô hình logic** | Dữ liệu có những đối tượng, thuộc tính, liên kết và ràng buộc nào? | Sản phẩm có mã, danh mục và giá; đơn hàng thuộc khách hàng. |
| **Biểu diễn trong DBMS** | Dữ liệu được đóng gói và phân bố thành các đơn vị nào? | Bảng sản phẩm, tài liệu sản phẩm, khóa sản phẩm, partition theo khách hàng. |
| **Đường truy cập / chỉ mục** | Từ điều kiện truy vấn, làm sao định vị nhanh dữ liệu? | Chỉ mục trên mã sản phẩm, cặp danh mục–giá, chỉ mục tìm kiếm văn bản. |
| **Thực thi truy vấn** | DBMS thực sự chọn cách đọc nào? | Quét index, quét bảng/collection, đọc nhiều partition, lấy thêm bản ghi gốc. |

~~~text
      Yêu cầu của ứng dụng
       WHERE category = ?
       ORDER BY price ASC
               │
               ▼
       Mô hình và biểu diễn
     Product {id, category, price}
               │
               ▼
        Đường truy cập
      (category ASC, price ASC)
               │
               ▼
        DBMS thực thi
  Tìm nhóm category và đọc theo price
               │
               ▼
          Kết quả truy vấn
~~~

Sơ đồ thể hiện ý tưởng chung, không khẳng định mọi DBMS đều thực thi giống nhau. Mô hình và index ảnh hưởng đến kế hoạch truy vấn; DBMS vẫn có thể chọn quét toàn bộ nếu dữ liệu rất nhỏ hoặc index không có lợi.

## 2. Chỉ mục thực chất là gì?

**Chỉ mục** là cấu trúc dữ liệu hỗ trợ định vị hoặc tổ chức truy cập theo một hay nhiều giá trị, có thể trả về bản ghi hoặc thông tin dẫn đến bản ghi. Đổi lại, DBMS thường phải dành thêm dung lượng và công sức duy trì index khi dữ liệu thay đổi.

Hãy hình dung một bộ hồ sơ giấy gồm hàng triệu tờ. Nếu cần tìm hồ sơ theo mã, ta có thể lật từng tờ. Một danh mục mã hồ sơ và vị trí tương ứng giúp tìm nhanh hơn; nhưng mỗi khi thêm, đổi hoặc xóa hồ sơ, danh mục cũng phải được cập nhật.

Trong DBMS, các phương pháp truy cập phổ biến gồm:

| Cơ chế | Phù hợp với kiểu truy vấn | Lưu ý |
| --- | --- | --- |
| **B-tree / B+tree và biến thể** | So sánh bằng, khoảng giá trị, sắp xếp theo khóa | Có thể hỗ trợ điều kiện tiền tố của chỉ mục nhiều cột; phụ thuộc cách DBMS tổ chức index. |
| **Hash index / ánh xạ khóa** | Tìm chính xác theo khóa | Thường không hỗ trợ truy vấn khoảng và thứ tự như cấu trúc có sắp xếp. |
| **Inverted index** | Tìm tài liệu theo từ, token, phần tử hoặc giá trị đã được lập chỉ mục | Phù hợp full-text và các kiểu truy vấn nhiều–nhiều; khả năng phụ thuộc bộ phân tích token và DBMS. |
| **Index cho phần tử mảng / trường lồng nhau** | Tìm tài liệu chứa một giá trị trong mảng hoặc theo đường dẫn trường | Cần hiểu cách tách giá trị mảng thành mục index và giới hạn kết hợp điều kiện. |
| **Spatial index** | Truy vấn vùng, lân cận, giao nhau về hình học | Dựa trên biểu diễn không gian và cấu trúc hỗ trợ của sản phẩm. |
| **Vector index** | Tìm các vector gần nhau theo một hàm đo | Thường tối ưu *approximate nearest neighbor*, phải đánh đổi độ chính xác, tốc độ và dung lượng. |

Một số thuật ngữ hay gặp:

- **Primary key / key lookup:** định danh bản ghi. Nhiều DBMS tổ chức đường truy cập hiệu quả theo khóa chính hoặc khóa tài liệu ngay từ khi tạo dữ liệu.
- **Secondary index:** index trên thuộc tính khác với đường truy cập chính, chẳng hạn tìm sản phẩm theo danh mục.
- **Composite/compound index:** index được tạo từ nhiều thuộc tính theo một thứ tự xác định, ví dụ *(category, price)*.
- **Covering index:** đối với một truy vấn cụ thể, index chứa đủ thông tin để trả kết quả mà không phải lấy thêm bản ghi từ kho dữ liệu gốc, nếu DBMS hỗ trợ cách thực thi này.
- **Unique index/constraint:** hỗ trợ hoặc thực thi yêu cầu không có hai bản ghi trùng khóa định danh/giá trị trong phạm vi được xác định; giới hạn và cách xử lý giá trị thiếu có thể khác nhau.

Chỉ mục **không phải bản thân mô hình dữ liệu**. Một mô hình tài liệu có thể dùng B-tree cho trường đơn giản, index đa giá trị cho mảng và inverted index cho nội dung văn bản. Một hệ quan hệ cũng có thể có index toàn văn, index không gian hoặc index cho JSON.

### Index, partition và bản sao dữ liệu khác nhau thế nào?

Ba cơ chế này đều có thể làm truy vấn nhanh hơn nhưng giải quyết bài toán khác nhau:

- **Partition/shard key** quyết định bản ghi thuộc phân vùng nào. Biết đúng partition giúp tránh đọc toàn bộ cụm; bản thân partition không đồng nghĩa có secondary index cho mọi thuộc tính.
- **Index** cung cấp đường truy cập trong phạm vi hệ thống hỗ trợ, chẳng hạn từ giá trị danh mục đến vị trí sản phẩm. Index có thể cục bộ theo phân vùng hoặc được tổ chức để hỗ trợ truy vấn trên nhiều phân vùng.
- **Materialized view / bảng tra cứu phụ** chứa dữ liệu đã được sắp xếp hay tổ chức lại nhằm trả lời một mẫu truy vấn khác. Nó có thể là dữ liệu dẫn xuất và cần cơ chế đồng bộ, thay vì chỉ là một index bổ trợ trong cùng cấu trúc gốc.

Trong một số NoSQL DBMS, cách phục vụ truy vấn quan trọng được thực hiện bằng **một bảng/collection bổ sung thiết kế theo truy vấn**, vì chỉ tạo secondary index không đem lại cùng hiệu quả hoặc cùng khả năng lọc như ở RDBMS.

## 3. Mô hình quan hệ: nhiều kiểu index trên bảng và cột

Trong **mô hình quan hệ**, dữ liệu được biểu diễn thành các quan hệ thường triển khai thành bảng, với các cột và hàng. DBMS quan hệ thường cho phép tạo index trên một hoặc nhiều cột, áp dụng nhiều cơ chế tùy sản phẩm.

Ví dụ một bảng đơn hàng:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL
);

CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at DESC);

SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

**Mô hình quan hệ** cho phép thiết kế đơn hàng độc lập với khách hàng và liên kết bằng khóa. **Index** trên *(customer_id, created_at DESC)* cung cấp một đường truy cập phù hợp cho việc lấy các đơn hàng gần nhất của một khách hàng, theo thứ tự thời gian.

DBMS có thể tận dụng index để tìm vùng có cùng *customer_id* và đọc lần lượt theo *created_at*. Tuy nhiên, việc có thực sự dùng index hay không cần xem kế hoạch thực thi; dữ liệu, thống kê và các cột cần trả về đều có thể ảnh hưởng.

Trong nhiều RDBMS, người dùng có thể:

- Tạo index phục vụ nhiều truy vấn mà không phải đổi cấu trúc bảng logic.
- Dùng index trên khóa ngoại, cột lọc, cột sắp xếp hoặc biểu thức nếu DBMS hỗ trợ.
- Dùng các kiểu index khác nhau cho so sánh bằng, tìm văn bản, không gian hoặc dữ liệu bán cấu trúc.
- Kết hợp nhiều bảng qua JOIN, nhưng index chỉ giúp giảm chi phí truy cập; index không tự quyết định độ phức tạp của toàn bộ phép JOIN.

**Lưu ý:** tên SQL và ví dụ này phù hợp với cách trình bày PostgreSQL/SQL quen thuộc; hỗ trợ cú pháp, kiểu index và tối ưu hóa thay đổi giữa các DBMS. Mô hình quan hệ không bắt buộc dùng một cơ chế index cụ thể.

## 4. Mô hình khóa–giá trị: tra cứu theo key là đường truy cập trung tâm

Trong **mô hình key–value**, đơn vị cơ bản là một **khóa định danh** và **giá trị** tương ứng:

~~~text
Key                         Value
--------------------------------------------------
product:P-1001              {name: "Book A", price: 120000}
product:P-1002              {name: "Book B", price: 190000}
cart:C-42                   {items: [...]}
~~~

Lợi thế nổi bật là biết **khóa** thì có thể tìm giá trị theo đường truy cập chính của hệ thống:

~~~text
GET product:P-1001
~~~

Nhưng nếu yêu cầu đổi thành “tìm mọi sản phẩm có giá dưới 200.000” mà khóa chỉ chứa mã sản phẩm, kho key–value thuần túy **không suy ra được ngay** vị trí các sản phẩm theo giá. Cần một trong các phương án:

1. Quét các khóa và đọc từng giá trị nếu quy mô và sản phẩm cho phép; cách này thường không phù hợp khi dữ liệu lớn.
2. Tạo và duy trì cấu trúc tra cứu bổ sung, chẳng hạn tập khóa sản phẩm theo danh mục hoặc sorted set theo điểm số.
3. Sử dụng khả năng tìm kiếm/secondary index do sản phẩm hoặc mô-đun mở rộng cung cấp.
4. Chuyển workload truy vấn nhiều thuộc tính sang một mô hình/kho dữ liệu khác.

Chẳng hạn, với Redis, ứng dụng có thể dùng các cấu trúc dữ liệu như set và sorted set để xây dựng đường truy cập riêng; tính năng tìm kiếm theo trường cần được xem xét theo phiên bản và thành phần Redis đang triển khai. Không nên đánh đồng việc **Redis tra khóa nhanh** với khả năng tự truy vấn tùy ý mọi trường trong giá trị.

**Hệ quả thiết kế:** khi truy vấn tập trung theo mã định danh, mô hình key–value phù hợp tự nhiên. Khi truy vấn liên tục thay đổi theo nhiều trường, chi phí duy trì những đường truy cập phụ có thể trở thành một phần lớn của kiến trúc.

## 5. Mô hình tài liệu: trường lồng nhau và mảng ảnh hưởng cách lập index

**Mô hình tài liệu** tổ chức dữ liệu thành các document, thường có trường lồng nhau và mảng. Một document sản phẩm có thể là:

~~~json
{
  "_id": "P-1001",
  "name": "Sách học NoSQL",
  "category": "books",
  "price": 180000,
  "tags": ["database", "backend"],
  "publisher": {
    "country": "VN",
    "name": "Nha xuat ban A"
  }
}
~~~

Một document DBMS như MongoDB thường cung cấp đường truy cập theo định danh tài liệu, đồng thời hỗ trợ các kiểu index cho trường đơn, trường lồng nhau và nhiều trường kết hợp. Ví dụ:

~~~javascript
// Tìm sản phẩm theo danh mục và khoảng giá.
db.products.createIndex({ category: 1, price: 1 });

db.products.find({
  category: "books",
  price: { $gte: 100000, $lte: 200000 }
}).sort({ price: 1 });

// Lập index theo trường lồng nhau.
db.products.createIndex({ "publisher.country": 1 });

// Lập index trên các giá trị của trường mảng.
db.products.createIndex({ tags: 1 });

db.products.find({ tags: "backend" });
~~~

Về mặt mô hình:

- **Trường đơn** như *category* có thể được lập chỉ mục theo giá trị.
- **Đường dẫn trường lồng nhau** như *publisher.country* cần cơ chế hiểu cấu trúc tài liệu và đường dẫn.
- **Mảng** như *tags* thường đòi hỏi cơ chế lập chỉ mục nhiều giá trị (*multikey*), để có thể tìm tài liệu chứa một phần tử cụ thể.
- **Chỉ mục kết hợp** như *(category, price)* phục vụ một mẫu truy vấn rõ ràng tốt hơn nhiều index đơn lẻ trong một số trường hợp.

Việc lưu tất cả dữ liệu vào một document lớn không tự động làm mọi truy vấn nhanh. Nếu thường xuyên lọc theo một trường nằm sâu hoặc trong mảng, phải xem **DBMS có hỗ trợ index đúng trường đó không**, điều kiện truy vấn có dùng được index không, và index có giới hạn gì về phần tử mảng, số trường kết hợp hay kích thước document.

### Nhúng và tham chiếu cũng ảnh hưởng đường truy cập

Giả sử mỗi đơn hàng nhúng danh sách sản phẩm đã mua. Điều này thuận tiện khi ứng dụng chủ yếu đọc **một đơn hàng và toàn bộ dòng hàng của nó**. Nhưng nếu câu hỏi thường xuyên là “tìm toàn bộ đơn hàng có chứa SKU này trong sáu tháng”, ứng dụng cần đường truy cập cho các SKU nằm trong mảng hoặc một cấu trúc khác theo SKU.

Ngược lại, nếu các dòng hàng nằm ở collection riêng và được tham chiếu theo *orderId*, việc truy vấn có thể cần nhiều lần đọc hoặc phép kết hợp. **Quyết định nhúng/tham chiếu** và **thiết kế index** phải được cân nhắc cùng mẫu truy cập, thay vì xử lý độc lập.

Một index không thể loại bỏ mọi chi phí kết hợp nếu ứng dụng cần lấy nhiều tài liệu liên quan từ nhiều nơi. Tương tự, nhúng quá nhiều dữ liệu có thể làm bản ghi lớn và tăng chi phí cập nhật.

## 6. Mô hình wide-column: khóa phân vùng và thứ tự cột gom nhóm

Những hệ **wide-column** như Apache Cassandra thường định hướng thiết kế bảng theo mẫu truy vấn. Khả năng truy cập hiệu quả được quyết định mạnh bởi:

- **Partition key:** xác định nơi lưu hàng dữ liệu về mặt phân vùng.
- **Clustering columns:** định nghĩa thứ tự dữ liệu trong một partition theo quy tắc của bảng.
- **Secondary indexing hoặc cơ chế tìm kiếm bổ sung:** tùy sản phẩm và phiên bản, có phạm vi và đánh đổi riêng.

Ví dụ ứng dụng cần lấy các đơn hàng gần nhất của một khách hàng:

~~~sql
CREATE TABLE orders_by_customer (
    customer_id UUID,
    created_at TIMESTAMP,
    order_id UUID,
    status TEXT,
    total_amount DECIMAL,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Khi biết **customer_id**, DBMS có thể định vị partition tương ứng; bên trong partition, các hàng được tổ chức theo cột gom nhóm cho phép truy cập đơn hàng theo thời gian hiệu quả. Một câu truy vấn được thiết kế tương ứng:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
LIMIT 20;
~~~

Cấu trúc trên phục vụ rất tốt **một loại truy vấn đã biết trước**. Nếu sau đó ứng dụng muốn lấy *mọi đơn hàng trạng thái PAID trên toàn hệ thống*, truy vấn có thể cần đọc rất nhiều partition, hoặc phải có cơ chế index phụ/thiết kế bảng phụ tương thích với phiên bản DBMS và tải thực tế.

Một giải pháp thường được cân nhắc là duy trì bảng đọc khác có khóa phù hợp với truy vấn mới. Ví dụ:

~~~text
orders_by_customer
  partition key: customer_id
  clustering: created_at
  truy vấn chính: 20 đơn mới nhất của một khách hàng

orders_by_status_day
  partition key: (status, day)
  clustering: created_at, order_id
  truy vấn chính: đơn thuộc trạng thái X trong một ngày
~~~

Bảng thứ hai là **một cách tổ chức dữ liệu phụ theo truy vấn**, không phải thao tác “bật thêm index” đơn giản. Ứng dụng phải tính đến việc nhân bản dữ liệu, đồng bộ khi trạng thái thay đổi, thứ tự cập nhật, độ trễ và khả năng xử lý lỗi.

**Cần phân biệt:** CQL có những câu lệnh giống SQL nhưng khả năng lọc, JOIN và tổ chức truy vấn không giống RDBMS. Cassandra có các cơ chế secondary index với khả năng phát triển qua từng phiên bản, nên không nên tuyên bố “Cassandra không có secondary index”; điều quan trọng là tính tương thích và chi phí của index với truy vấn cụ thể.

### Partition key không được chọn chỉ vì có nhiều giá trị

Một partition quá lớn có thể gây tốn chi phí đọc/ghi. Một partition key mà mọi request cùng đổ vào một giá trị có thể tạo ra **hot partition**. Ngược lại, chia partition quá nhỏ hoặc phân tán sai mẫu đọc có thể khiến một truy vấn phải fan-out qua nhiều nút.

Vì vậy, thiết kế wide-column đặt câu hỏi: **để thực hiện truy vấn này, tôi đã biết khóa phân vùng chưa, dữ liệu cần đọc có nằm trong phạm vi đủ nhỏ chưa, và thứ tự clustering có giúp đọc trực tiếp không?**

## 7. Mô hình đồ thị: index đưa ta tới điểm bắt đầu, liên kết đưa ta đi tiếp

**Mô hình đồ thị** mô tả các **node**, **relationship/edge** và **property**. Một truy vấn thường có hai phần:

1. Tìm đúng **node bắt đầu** theo nhãn và thuộc tính.
2. Đi theo **các liên kết** với mẫu quan hệ được yêu cầu.

Ví dụ mạng xã hội có người dùng và quan hệ theo dõi:

~~~cypher
CREATE INDEX person_id_idx IF NOT EXISTS
FOR (p:Person) ON (p.id);

MATCH (p:Person {id: 'U-42'})-[:FOLLOWS]->(followed:Person)
RETURN followed.id, followed.name;
~~~

Trong cơ sở dữ liệu đồ thị như Neo4j, index thuộc tính có thể giúp tìm node **Person có id = U-42**. Sau đó, hệ thống thực hiện *traversal* trên các liên kết *FOLLOWS*. Hiệu quả của bước duyệt phụ thuộc vào cách graph DBMS lưu và truy cập các mối liên hệ, cùng số lượng cạnh cần duyệt.

Index trên **Person.id** không có nghĩa bước tìm tất cả người được theo dõi trở thành tìm kiếm theo một index B-tree chung. **Khả năng điều hướng theo cạnh** là một phần quan trọng của mô hình và engine đồ thị, bổ sung cho index tìm điểm khởi đầu.

Điều này cũng giải thích tại sao:

- Với truy vấn “tìm người theo email”, index thuộc tính có thể rất quan trọng.
- Với truy vấn “từ người X, duyệt bạn của bạn trong 2 bước”, tổ chức quan hệ và số cạnh đi qua có thể chi phối.
- Với truy vấn “tìm tất cả đường đi giữa A và B”, chi phí phụ thuộc giới hạn độ dài, hướng cạnh, điều kiện lọc và số nhánh có thể mở rộng; chỉ thêm property index không tự giải quyết mọi truy vấn đường đi.

Một DBMS quan hệ vẫn có thể lưu bảng cạnh và dùng JOIN hoặc truy vấn đệ quy; graph DBMS nhấn mạnh việc biểu diễn và duyệt liên kết. **Khác biệt là kết hợp giữa mô hình dữ liệu, giao diện truy vấn và cơ chế thực thi**, chứ không phải “graph có index, relational không có” hay ngược lại.

## 8. Dữ liệu chuỗi thời gian và tìm kiếm: index phải theo loại truy vấn

Chuỗi thời gian và văn bản tìm kiếm thường được gọi là *workload* hoặc *kiểu truy cập chuyên biệt*. Chúng có thể được xây trên nhiều mô hình dữ liệu, nhưng đặt ra yêu cầu lập chỉ mục rất khác nhau.

### 8.1. Chuỗi thời gian: lọc theo nguồn và khoảng thời gian

Ví dụ mỗi cảm biến phát một giá trị nhiệt độ sau mỗi 10 giây:

~~~text
device_id     measured_at                  temperature_c
SENSOR-17     2026-10-12T09:15:00Z        28.4
SENSOR-17     2026-10-12T09:15:10Z        28.6
SENSOR-17     2026-10-12T09:15:20Z        28.3
~~~

Truy vấn điển hình là **lấy điểm đo của một thiết bị trong khoảng thời gian**. Trong một RDBMS, index trên *(device_id, measured_at)* có thể phù hợp:

~~~sql
CREATE INDEX idx_readings_device_time
ON sensor_readings (device_id, measured_at DESC);

SELECT measured_at, temperature_c
FROM sensor_readings
WHERE device_id = 'SENSOR-17'
  AND measured_at >= TIMESTAMP '2026-10-12 09:00:00'
  AND measured_at <  TIMESTAMP '2026-10-12 10:00:00'
ORDER BY measured_at DESC;
~~~

Ở các hệ chuyên xử lý time-series, dữ liệu có thể được phân vùng theo thời gian, nén theo chuỗi hoặc tổ chức theo thiết bị và các khoảng thời gian; nhiều hệ còn hỗ trợ giữ dữ liệu chi tiết trong thời gian ngắn và giữ số liệu tổng hợp lâu hơn.

Index đơn lẻ không thay thế được chiến lược **partition pruning**, retention, nén và tổng hợp theo cửa sổ khi dữ liệu tăng hàng trăm triệu điểm. Đồng thời, việc thêm quá nhiều index vào bảng có tải ghi rất lớn có thể khiến chi phí ghi tăng đáng kể.

### 8.2. Văn bản: truy vấn từ khóa khác so sánh bằng

Một index trên giá trị đầy đủ của trường *description* thường không đủ để tối ưu truy vấn “tìm mọi sản phẩm có chứa những từ khóa này ở bất kỳ vị trí nào”, đặc biệt khi có yêu cầu tách từ, chuẩn hóa từ, chấm điểm mức liên quan hoặc xử lý ngôn ngữ.

**Inverted index** thường lưu ánh xạ từ token/term đến danh sách tài liệu chứa token đó:

~~~text
Term          Documents
---------------------------------
nosql         P-1001, P-1042
database      P-1001, P-1090
index         P-1042, P-1090
~~~

Truy vấn “nosql AND database” có thể dựa trên phép giao tập tài liệu của các term. Đây là ví dụ đơn giản; công cụ thực tế còn xử lý các quy tắc tách từ, dấu, từ dừng, vị trí từ, trọng số và xếp hạng.

Một document DBMS có thể hỗ trợ text index; RDBMS cũng có thể hỗ trợ full-text search; search engine chuyên dụng như OpenSearch/Elasticsearch được thiết kế nhiều cơ chế liên quan đến truy vấn văn bản. Cần phân biệt **kiểu index** với **nhãn SQL/NoSQL**.

### 8.3. Không gian và vector: index phục vụ ngữ nghĩa so sánh riêng

Truy vấn “điểm bán hàng nằm trong bán kính 2 km” cần ngữ nghĩa hình học và thường có index không gian. Truy vấn “tìm các đoạn văn có embedding gần truy vấn nhất” cần khái niệm khoảng cách hoặc mức tương đồng giữa vector và có thể sử dụng vector index.

Không nên dùng index B-tree thông thường trên từng thành phần vector rồi kỳ vọng nó tự xử lý bài toán tìm lân cận gần nhất. **Cấu trúc index phải phù hợp toán tử truy vấn**, và sản phẩm cần hỗ trợ toán tử đó.

## 9. Chỉ mục kết hợp: cùng một bộ trường, đổi thứ tự có thể đổi hiệu quả

Xét dữ liệu sản phẩm:

~~~json
{
  "id": "P-1001",
  "category": "books",
  "price": 180000,
  "brand": "Nha xuat ban A"
}
~~~

Hai yêu cầu:

- **Q1:** Liệt kê sách theo giá tăng dần.
- **Q2:** Liệt kê sản phẩm trong khoảng giá, không quan tâm danh mục.

Một index ghép *(category, price)* thường phù hợp Q1, do có thể định vị vùng *category = books* và tiếp tục đọc các giá theo thứ tự. Nhưng Q2 có thể không sử dụng hiệu quả toàn bộ index ghép này, vì giá chỉ là thành phần phía sau và dữ liệu phân nhóm theo danh mục.

Ví dụ với MongoDB:

~~~javascript
db.products.createIndex({ category: 1, price: 1 });

// Khớp tiền tố bằng category, rồi lọc/sắp xếp theo price.
db.products.find({ category: "books" })
           .sort({ price: 1 })
           .limit(20);

// Thiếu điều kiện category: cần kiểm tra kế hoạch thực thi.
db.products.find({ price: { $lt: 200000 } });
~~~

Nguyên tắc **tiền tố trái** (*leftmost prefix*) là cách nhớ hữu ích cho nhiều index B-tree ghép: các trường đầu ảnh hưởng mạnh tới khả năng tìm kiếm hiệu quả bằng các trường sau. Nhưng nguyên tắc không mô tả đầy đủ mọi DBMS, mọi kiểu index hay mọi phương pháp tối ưu; có hệ hỗ trợ các chiến lược đặc biệt.

Khi chọn thứ tự trường, nên đánh giá:

1. Điều kiện so sánh bằng nào xuất hiện thường xuyên?
2. Điều kiện khoảng nào được dùng?
3. Truy vấn cần sắp xếp theo trường nào?
4. Có yêu cầu trả về chỉ một tập nhỏ trường để tận dụng index bao phủ không?
5. Tỉ lệ bản ghi phù hợp bộ lọc là bao nhiêu và tổng số bản ghi lớn đến đâu?

**Độ chọn lọc** (*selectivity*) thể hiện khả năng điều kiện lọc thu hẹp tập dữ liệu. Điều kiện *status = ACTIVE* có thể vẫn khớp 95% bản ghi; dùng index riêng cho trường đó có thể ít lợi ích cho truy vấn đọc nhiều dữ liệu. Trong khi *customer_id = 42* có thể chỉ khớp vài chục bản ghi giữa hàng triệu đơn hàng. Tuy nhiên, index có lợi hay không phải dựa trên chi phí truy cập thực tế, không chỉ dựa trên số giá trị khác nhau của cột.

## 10. Khi nào index có tác dụng, khi nào phải đổi mô hình?

Giả sử hệ thống trước đây chỉ cho phép “xem đơn hàng theo *orderId*”, nên lưu theo khóa định danh. Sau này thêm màn hình “20 đơn hàng mới nhất của khách hàng, lọc theo trạng thái”.

Có nhiều lựa chọn:

| Hướng xử lý | Khi nào đáng cân nhắc | Đánh đổi |
| --- | --- | --- |
| **Thêm index ghép** | DBMS hỗ trợ truy vấn theo thuộc tính và index phù hợp | Tốn dung lượng, chi phí ghi, thời gian tạo index; planner vẫn cần chọn index. |
| **Đổi cách tổ chức khóa/partition** | Truy vấn này là đường truy cập quan trọng, có thể thiết kế lại dữ liệu | Có thể ảnh hưởng các mẫu đọc/ghi khác, đòi hỏi di chuyển dữ liệu. |
| **Tạo bảng/collection theo truy vấn** | Index phụ bị giới hạn, truy vấn có thể quá rộng hoặc cần thứ tự dữ liệu riêng | Phải đồng bộ dữ liệu phụ, xử lý trễ, thất bại và cập nhật trùng. |
| **Dùng search/read store chuyên dụng** | Cần truy vấn văn bản, phân tích hoặc lọc phức tạp hơn kho giao dịch | Tăng thành phần vận hành, lập chỉ mục, khả năng lệch so với nguồn. |

Tư duy thiết kế NoSQL thường nhấn mạnh **query-first modeling**: liệt kê những truy vấn quan trọng rồi chọn cấu trúc dữ liệu để trả lời chúng hiệu quả. Điều này **không có nghĩa mọi NoSQL DBMS đều bắt buộc nhân bản dữ liệu**, và cũng không có nghĩa mô hình quan hệ không cần thiết kế index theo truy vấn. Mức độ linh hoạt tùy DBMS và workload.

### Index không thể sửa mọi vấn đề mô hình hóa

Ví dụ đơn hàng là một document khổng lồ chứa lịch sử cập nhật nhiều năm. Index trên *orderId* giúp tìm document, nhưng không giảm được toàn bộ chi phí truyền, giải mã và cập nhật phần không cần thiết nếu ứng dụng luôn phải xử lý document quá lớn.

Hoặc một thiết kế partition theo ngày tạo hàng nghìn partition cho truy vấn “lấy lịch sử của một khách hàng trong ba năm”. Thêm index cục bộ có thể vẫn không tránh được việc truy cập nhiều partition. Khi **đơn vị lưu trữ và đơn vị truy vấn không phù hợp**, cần xem lại thiết kế partition, dữ liệu dẫn xuất hoặc nhu cầu thực tế.

## 11. Phân tán làm thay đổi ý nghĩa của index

Trong hệ quản trị phân tán, một truy vấn có thể phải đi tới nhiều node. Vì thế, cần hỏi index là **cục bộ** hay **toàn cục**, và index giúp định tuyến truy vấn như thế nào.

~~~text
                       Client query
                            │
                     Query coordinator
                            │
                Có biết partition key?
                      /          \
                    Có           Không
                    │              │
              Tới partition   Có thể fan-out,
              liên quan       dùng global index,
                    │         hoặc scan nhiều nơi
                    └──────────┬─────────┘
                               ▼
                          Trả kết quả
~~~

Sơ đồ không phải mô tả duy nhất của mọi hệ thống. Một số DBMS có global secondary index; một số index cục bộ theo shard; một số dùng bảng phân phối theo khóa; những hệ khác có search service riêng. Hiệu quả và bảo đảm nhất quán là quyết định theo sản phẩm/cấu hình.

Cần đặc biệt lưu ý:

- **Fan-out:** cùng một điều kiện truy vấn có thể phải gửi tới nhiều partition nếu không xác định được nơi chứa dữ liệu.
- **Hot key/hot partition:** mọi truy vấn hoặc ghi tập trung vào một khóa có thể tạo nghẽn, dù có index.
- **Cập nhật index trong môi trường phân tán:** secondary index có thể cập nhật cùng giao dịch hoặc theo cơ chế bất đồng bộ, tùy DBMS. Khi bất đồng bộ, một kết quả tìm kiếm có thể chậm hơn bản ghi nguồn.
- **Bảo đảm duy nhất:** unique constraint trong một phân vùng khác với bảo đảm duy nhất toàn cục; không nên mặc định mọi secondary index đều bảo đảm uniqueness xuyên shard.
- **Phân vùng và dung lượng:** tăng số partition hoặc nhân bản không xóa chi phí lưu index; tổng dung lượng và lưu lượng đồng bộ có thể tăng.

Ví dụ trong Amazon DynamoDB, việc tra cứu theo khóa chính và truy vấn thông qua secondary index có những tính chất riêng. Global secondary index cung cấp một khóa truy cập khác nhưng có cơ chế duy trì và bảo đảm đọc cần được xem xét; không được áp dụng nguyên xi hành vi của DynamoDB cho Cassandra, MongoDB hay các DBMS khác.

## 12. Chi phí của index: tăng tốc đọc thường làm ghi và vận hành đắt hơn

Khi thêm index, DBMS thường phải cập nhật cả dữ liệu và các cấu trúc chỉ mục liên quan. Hãy xem một ứng dụng có ba index bổ sung trên collection sản phẩm:

~~~text
Ghi sản phẩm mới
     │
     ├──> Ghi bản ghi sản phẩm
     ├──> Cập nhật index category + price
     ├──> Cập nhật index brand
     └──> Cập nhật index tags
~~~

Mức độ chi phí không nhất thiết tăng tuyến tính theo số index, nhưng **write amplification** và chi phí lưu trữ là những đánh đổi phải xem xét. Sửa trường không có trong một index có thể ít ảnh hưởng index đó; sửa trường đã lập index có thể cần thay đổi vị trí trong index.

| Tác động | Ví dụ cần quan sát |
| --- | --- |
| **Dung lượng lưu** | Tổng kích thước index, mức tăng theo dữ liệu, nhân bản. |
| **Độ trễ ghi** | Chèn/cập nhật/xóa có cần duy trì nhiều cấu trúc hơn không? |
| **Khởi tạo index** | Tạo index trên tập dữ liệu lớn có thể cần thời gian, CPU, bộ nhớ và I/O. |
| **Bộ nhớ/cache** | Index cạnh tranh bộ nhớ với dữ liệu và cấu trúc khác. |
| **Đọc và sắp xếp** | Index giúp giảm scan nhưng có thể cần đọc bản ghi gốc hoặc vẫn phải sort. |
| **Phân tán** | Cập nhật và đồng bộ index giữa node, ảnh hưởng đến độ trễ nhìn thấy dữ liệu. |
| **Bảo trì** | Theo dõi index ít dùng, tái xây dựng khi cần, thay đổi schema và đường truy cập. |

**Không lập index cho mọi trường theo phản xạ.** Index cần gắn với truy vấn thường gặp hoặc yêu cầu ràng buộc cụ thể. Mục tiêu là tối ưu **toàn bộ workload**, không phải một truy vấn riêng lẻ bằng mọi giá.

## 13. Cách thiết kế index bắt đầu từ truy vấn

Một quy trình thực hành phù hợp cho cả SQL và NoSQL:

### Bước 1 — Liệt kê mẫu truy vấn thật sự quan trọng

Ví dụ cho kho sản phẩm và đơn hàng:

| Mã | Truy vấn | Độ thường xuyên | Yêu cầu phản hồi |
| --- | --- | --- | --- |
| Q1 | Tìm sản phẩm theo ID | Cao | Thấp |
| Q2 | Lọc theo danh mục, sắp theo giá, lấy 20 kết quả | Cao | Thấp |
| Q3 | Tìm theo từ khóa trong tên/mô tả | Trung bình | Thấp đến trung bình |
| Q4 | Lấy đơn mới nhất của một khách hàng | Cao | Thấp |
| Q5 | Tính doanh thu tháng từ tất cả đơn hàng | Thấp, xử lý định kỳ | Có thể cao hơn |

Yêu cầu độ trễ phải được cụ thể hóa thành chỉ tiêu đo được (ví dụ p95), kết hợp dung lượng và tải dự kiến. Bảng trên chỉ biểu diễn mức ưu tiên tương đối.

### Bước 2 — Xác định khóa truy cập và trường lọc

Đối với từng truy vấn, ghi rõ:

- Các trường có điều kiện so sánh bằng, điều kiện khoảng, tìm kiếm từ khóa, liên kết đồ thị hoặc không gian.
- Cột/trường sắp xếp, số kết quả cần trả, phân trang và các trường được hiển thị.
- Có biết chính xác key hoặc partition key không? Truy vấn có cần dữ liệu từ nhiều đối tượng không?
- Độ chọn lọc của điều kiện và mức độ lặp lại của các giá trị.

### Bước 3 — Chọn cách tổ chức dữ liệu tương ứng

Ví dụ:

- Q1: đường truy cập theo ID thường là nền tảng trong cả bảng, document và key–value.
- Q2: index *(category, price)* trên tài liệu/bảng có thể phù hợp; nếu DBMS wide-column, có thể thiết kế bảng theo danh mục và thứ tự giá.
- Q3: cần cân nhắc full-text/inverted index; index so sánh bằng đơn thuần trên tên không thay thế phân tích văn bản.
- Q4: index *(customer_id, created_at)*, hoặc partition theo *customer_id* với thứ tự *created_at*, tùy DBMS.
- Q5: quét/tổng hợp theo batch có thể hợp lý, hoặc tạo dữ liệu dẫn xuất nếu truy vấn thường xuyên và khối lượng lớn.

### Bước 4 — Kiểm tra kế hoạch thực thi thực tế

Ví dụ trong MongoDB:

~~~javascript
db.products.find({
  category: "books",
  price: { $gte: 100000, $lte: 200000 }
}).sort({ price: 1 }).explain("executionStats");
~~~

Trong nhiều RDBMS có thể dùng **EXPLAIN** để quan sát kế hoạch. Cần xem DBMS dùng index nào, đã đọc bao nhiêu mục index/bản ghi, có quét toàn bộ hay sort thêm không, và thời gian thực thi với dữ liệu đại diện. **EXPLAIN** không đồng nghĩa với chứng minh hệ thống sẽ luôn nhanh trên mọi phân bố dữ liệu.

Trong các DBMS khác, phải dùng cơ chế đo, trace hoặc bộ công cụ truy vấn tương ứng. Với hệ phân tán, đặc biệt lưu ý số partition/node tham gia, fan-out, số bản ghi đọc thừa và độ trễ mạng.

### Bước 5 — Đánh giá tác động lên ghi, tăng trưởng và cập nhật

Nếu Q2 chiếm đa số lượng đọc, một index trên *(category, price)* có thể rất đáng giá. Nhưng nếu sản phẩm được cập nhật giá hàng chục nghìn lần mỗi giây, index này tạo thêm tải ghi cần đo. Nếu Q5 chỉ chạy một lần mỗi đêm, không nhất thiết phải tạo một index đắt đỏ phục vụ riêng truy vấn đó.

Thiết kế index tốt đi cùng phương án theo dõi sau triển khai: thay đổi kích thước dữ liệu, tần suất truy vấn, mức độ chọn lọc, phân bố khóa, độ trễ, dung lượng index và các truy vấn mới.

## 14. Các nhận định dễ gây hiểu lầm

**“NoSQL không có index.”** Sai. Nhiều DBMS NoSQL có đường truy cập theo khóa và secondary index, full-text, spatial hoặc vector index. Phạm vi cụ thể tùy sản phẩm.

**“Document DBMS tự động index mọi trường JSON.”** Không nên mặc định. Nhiều DBMS yêu cầu khai báo index cho trường truy vấn, và cơ chế tự tạo index nếu có cũng có giới hạn và chi phí.

**“Một index trên field sẽ giúp mọi truy vấn chứa field đó.”** Chưa đủ. Toán tử, thứ tự trường, điều kiện khoảng, cách sắp xếp, collation và số bản ghi phù hợp đều ảnh hưởng.

**“Có partition key là đã có index cho tất cả điều kiện lọc.”** Partition key giúp định vị phân vùng; lọc những thuộc tính khác còn phụ thuộc clustering, index phụ hoặc dữ liệu được tổ chức theo truy vấn.

**“Graph query không cần index vì đã có edge.”** Đường duyệt cạnh giúp đi từ node đã biết. Tìm node bắt đầu theo một thuộc tính có thể vẫn cần index phù hợp.

**“Index biến truy vấn toàn văn thành so sánh bằng thông thường.”** Full-text có ngữ nghĩa token hóa, phân tích ngôn ngữ và xếp hạng riêng; index cần phù hợp ngữ nghĩa đó.

**“Càng nhiều index càng tốt.”** Mỗi index cần bộ nhớ, dung lượng, duy trì và có thể làm giảm hiệu suất ghi. Index ít dùng cần được đánh giá lại.

**“Truy vấn có index thì chắc chắn ít I/O.”** Nếu điều kiện trả về phần lớn dữ liệu, hoặc cần lấy nhiều trường ngoài index, quét dữ liệu có thể có lợi hơn. DBMS có thể chọn phương án khác.

## 15. Bài tập tư duy: từ mô hình đến đường truy cập

### Bài tập 1: kho tài liệu sản phẩm

Ứng dụng lưu:

~~~json
{
  "_id": "P-001",
  "category": "phone",
  "brand": "A",
  "price": 8000000,
  "attributes": {
    "color": "black",
    "memoryGb": 256
  }
}
~~~

Yêu cầu: “Liệt kê điện thoại giá dưới 10 triệu, tăng dần theo giá”. Hãy xác định:

1. Mô hình dữ liệu đang sử dụng là gì?
2. Các trường lọc và sắp xếp là gì?
3. Index ghép nào nên được khảo sát đầu tiên?
4. Khi chuyển sang “tìm mọi sản phẩm giá dưới 10 triệu bất kể danh mục”, index ban đầu còn phù hợp như thế nào?

**Gợi ý:** Mô hình tài liệu; điều kiện *category = phone*, *price < 10000000*, sắp theo *price*; có thể xem xét index *(category, price)*. Với truy vấn không có *category*, cần xem lại đường truy cập và kế hoạch thực thi.

### Bài tập 2: đồ thị quan hệ bạn bè

Ứng dụng cần tìm những người mà tài khoản **U-42** đang theo dõi. Chọn nơi index có tác dụng trực tiếp nhất: (a) tìm node U-42, (b) làm ngắn mọi đường duyệt cạnh, (c) bảo đảm không có vòng lặp trong đồ thị.

**Gợi ý:** Index thuộc tính giúp (a), còn việc duyệt theo *FOLLOWS* phụ thuộc cách tổ chức liên kết của DBMS. Index không tự bảo đảm (b) hoặc (c).

### Bài tập 3: dữ liệu cảm biến

Có 10.000 thiết bị, mỗi thiết bị gửi 1 điểm/giây. Màn hình chỉ xem 15 phút gần nhất của **một** thiết bị, còn báo cáo cuối ngày tính nhiệt độ trung bình của toàn hệ thống. Cùng một index có chắc là cách tối ưu cho cả hai yêu cầu không?

**Gợi ý:** Truy vấn theo thiết bị và khoảng thời gian cần đường truy cập khác với tổng hợp trên toàn hệ thống. Có thể cần partition theo thời gian, index theo thiết bị, downsampling hoặc báo cáo dẫn xuất tùy khối lượng và DBMS.

### Bài tập 4: bảng wide-column

Một bảng phân vùng theo **customer_id**, sắp xếp theo **created_at**. Người dùng yêu cầu tìm toàn bộ đơn hàng có **status = FAILED** trên mọi khách hàng. Vì sao truy vấn này khó hơn truy vấn theo *customer_id*?

**Gợi ý:** Không có *customer_id* nên hệ thống có thể không xác định một partition cần đọc; cần xem khả năng secondary index, cấu trúc phụ hoặc thiết kế truy vấn phù hợp.

## 16. Kết luận thực hành

Mô hình dữ liệu và khả năng lập chỉ mục có mối quan hệ **hai chiều**: mô hình dữ liệu quyết định đơn vị và đường liên kết mà hệ thống có thể truy cập; nhu cầu truy vấn và khả năng index của DBMS lại ảnh hưởng việc chọn mô hình, cách nhúng dữ liệu, khóa phân vùng, thứ tự lưu và những bản dữ liệu dẫn xuất.

Khi đánh giá một thiết kế NoSQL, hãy hỏi theo thứ tự:

1. **Dữ liệu được mô hình hóa thế nào?** Khóa–giá trị, tài liệu, wide-column, đồ thị, quan hệ hay một tổ hợp?
2. **Ứng dụng hỏi gì?** Tìm theo ID, lọc theo trường, lấy khoảng thời gian, tìm văn bản, duyệt liên kết hay tìm hàng xóm vector?
3. **DBMS có đường truy cập nào?** Khóa chính, clustering, secondary index, inverted index, traversal, partition pruning hay một read model?
4. **Đường truy cập đó có thực sự giảm phạm vi đọc không?** Cần xem điều kiện, thứ tự, phân bố dữ liệu, số partition, giới hạn index và kế hoạch thực thi.
5. **Chi phí duy trì là bao nhiêu?** Tải ghi, dung lượng, độ trễ cập nhật, nhân bản, xử lý sự kiện và khả năng rebuild.

**Không chọn index chỉ vì có một cột hoặc trường tồn tại.** Hãy chọn mô hình dữ liệu cùng đường truy cập để phục vụ những truy vấn quan trọng của ứng dụng, sau đó đo với dữ liệu và tải thực tế.
