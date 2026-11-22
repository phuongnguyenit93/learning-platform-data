# NoSQL là gì và vì sao xuất hiện nhiều mô hình dữ liệu khác nhau?

## 1. Từ một ứng dụng quen thuộc đến câu hỏi về cách lưu dữ liệu

Giả sử một nền tảng thương mại điện tử có các chức năng sau:

- Quản lý tài khoản, đơn hàng, thanh toán và tồn kho.
- Hiển thị danh mục sản phẩm: điện thoại có thông số RAM, bộ nhớ; quần áo có kích cỡ, chất liệu; sách có tác giả, nhà xuất bản.
- Lưu giỏ hàng tạm thời để người dùng quay lại vẫn tiếp tục mua sắm.
- Ghi nhận hàng triệu lượt xem, lượt nhấp và thao tác tìm kiếm để phân tích hành vi.
- Gợi ý sản phẩm theo mối liên hệ giữa khách hàng, mặt hàng, sở thích và lịch sử tương tác.

Ta **có thể** bắt đầu với một hệ quản trị cơ sở dữ liệu quan hệ (RDBMS) như PostgreSQL hoặc MySQL. Một hệ như vậy vẫn đáp ứng rất nhiều ứng dụng lớn khi được thiết kế, lập chỉ mục và vận hành đúng cách. Tuy nhiên, mỗi loại chức năng trên đặt ra một kiểu truy cập dữ liệu khác nhau:

| Chức năng | Câu hỏi thường xuyên nhất | Điều hệ thống cần ưu tiên |
|---|---|---|
| Đặt hàng và thanh toán | Đơn hàng này đã thanh toán chưa? Có trừ tồn kho đúng không? | Giao dịch, ràng buộc và tính nhất quán |
| Danh mục sản phẩm | Lấy toàn bộ thông tin của một sản phẩm để hiển thị | Dữ liệu đa dạng, đọc theo một thực thể |
| Giỏ hàng | Giỏ của người dùng U gồm những sản phẩm nào? | Đọc/ghi nhanh theo khóa, có thể hết hạn |
| Nhật ký tương tác | Sự kiện của U trong ngày D là gì? | Ghi liên tục với khối lượng lớn, truy vấn theo thời gian |
| Phát hiện gian lận | Những tài khoản nào dùng chung thiết bị và phương thức thanh toán? | Duyệt các quan hệ nhiều bước |
| Tìm kiếm | Sản phẩm nào chứa cụm từ gần đúng với yêu cầu? | Tìm kiếm văn bản, xếp hạng kết quả |

Không phải một hệ quản trị duy nhất luôn tối ưu cho tất cả các kiểu truy cập đó. **Tư duy NoSQL** bắt đầu bằng việc nhìn vào dữ liệu, câu truy vấn, quy mô, yêu cầu nhất quán và ràng buộc vận hành; từ đó chọn mô hình lưu trữ phù hợp với từng bài toán.

## 2. NoSQL là gì?

**NoSQL** là tên gọi chung cho một nhóm hệ quản trị dữ liệu không lấy **mô hình bảng quan hệ và phép nối bảng (JOIN)** làm cách tổ chức, truy cập dữ liệu chủ đạo. Các hệ NoSQL thường cung cấp những mô hình như **key–value**, **document**, **wide-column** và **graph**. Một số hệ chuyên dụng cho chuỗi thời gian hoặc tìm kiếm cũng thường được thảo luận trong hệ sinh thái này.

Tên gọi NoSQL xuất phát từ cách nói “Not Only SQL” (không chỉ SQL): SQL và cơ sở dữ liệu quan hệ vẫn hữu ích, trong khi những dạng dữ liệu và kiểu truy vấn khác có thể phù hợp hơn với cách lưu trữ khác. Đây là một **nhóm phương pháp và công nghệ**, không phải một chuẩn kỹ thuật duy nhất. Hai cơ sở dữ liệu cùng được gọi là NoSQL có thể khác nhau rất nhiều về cấu trúc dữ liệu, ngôn ngữ truy vấn, giao dịch và khả năng phân tán.

Cần phân biệt ba khái niệm thường bị gộp làm một:

- **Mô hình dữ liệu**: cách biểu diễn và liên kết thông tin, chẳng hạn bảng có khóa ngoại, tài liệu JSON, cặp khóa–giá trị hay đồ thị đỉnh–cạnh.
- **Mô hình truy vấn**: cách ứng dụng đọc/ghi, chẳng hạn tra cứu bằng khóa, lọc thuộc tính, quét theo thời gian hay duyệt quan hệ.
- **Cơ chế triển khai**: cách hệ thống lưu trên đĩa, lập chỉ mục, sao chép, chia dữ liệu giữa nhiều máy và phục hồi khi có lỗi.

Một công nghệ có thể hỗ trợ nhiều cách truy vấn hoặc nhiều mô hình dữ liệu. Ví dụ, một cơ sở dữ liệu quan hệ hiện đại có thể lưu JSON, lập chỉ mục JSON và phân vùng dữ liệu; ngược lại, một số hệ NoSQL hỗ trợ giao dịch và cú pháp truy vấn giống SQL. Vì vậy, ranh giới giữa hai nhóm **không tuyệt đối**.

### 2.1. So với mô hình quan hệ

Trong mô hình quan hệ, dữ liệu thường được chia thành những bảng đại diện cho các thực thể và mối quan hệ:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    total_amount DECIMAL(12, 2) NOT NULL
);

SELECT c.name, o.id, o.total_amount
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE c.id = 42;
~~~

Kiểu thiết kế này rất phù hợp khi cần ràng buộc dữ liệu rõ ràng, xử lý giao dịch nhiều bước và kết hợp thông tin từ nhiều bảng. Chuẩn hóa dữ liệu (normalization) giúp giảm sự lặp lại không cần thiết: tên khách hàng được quản lý tại một nơi thay vì sao chép vào mọi bản ghi.

Với nhiều hệ NoSQL, dữ liệu có thể được nhóm theo **đơn vị mà ứng dụng thường đọc hoặc ghi cùng nhau**. Chẳng hạn, một tài liệu sản phẩm chứa luôn tập thuộc tính và các biến thể cần hiển thị:

~~~json
{
  "_id": "P100",
  "name": "Áo khoác",
  "category": "fashion",
  "attributes": {
    "material": "cotton",
    "style": "unisex"
  },
  "variants": [
    { "sku": "P100-M-BLACK", "size": "M", "color": "black" },
    { "sku": "P100-L-BLACK", "size": "L", "color": "black" }
  ]
}
~~~

Ứng dụng có thể lấy phần lớn thông tin để hiển thị sản phẩm chỉ với một lần đọc tài liệu. Đổi lại, nếu dữ liệu được sao chép vào nhiều tài liệu, việc cập nhật đồng bộ có thể khó hơn. Sự khác biệt nằm ở **cách tối ưu cho truy cập dữ liệu và các ràng buộc cần bảo đảm**, không phải ở việc mô hình nào luôn nhanh hơn.

## 3. Những bài toán thúc đẩy sự phát triển của NoSQL

### 3.1. Lượng dữ liệu và lưu lượng truy cập tăng mạnh

Khi số người dùng, sự kiện và yêu cầu tăng lên, hệ thống phải xử lý đồng thời nhiều thao tác. Có hai hướng mở rộng phổ biến:

- **Mở rộng theo chiều dọc (scale up)**: dùng máy mạnh hơn, nhiều CPU/RAM/ổ đĩa hơn.
- **Mở rộng theo chiều ngang (scale out)**: chia công việc và dữ liệu giữa nhiều máy.

Một số hệ NoSQL, đặc biệt là key–value và wide-column phân tán, được thiết kế với cơ chế phân mảnh dữ liệu (**sharding/partitioning**) và nhân bản (**replication**) ngay từ đầu. Điều này thuận lợi cho những tải công việc có thể phân chia theo khóa. Chẳng hạn, sự kiện của người dùng có thể phân theo cặp `(user_id, ngày)` và phân bố trên nhiều nút.

Tuy nhiên, **NoSQL không đồng nghĩa với tự động mở rộng vô hạn**. Khóa phân vùng kém có thể tạo ra một “điểm nóng” (hot partition) nếu quá nhiều lượt ghi cùng dồn vào một nút. Hệ quản trị quan hệ cũng có thể scale out thông qua phân vùng, replica hoặc giải pháp phân tán. Lựa chọn cần dựa trên đặc điểm tải thực tế.

### 3.2. Dữ liệu không đồng nhất và thay đổi liên tục

Giả sử một website bán nhiều loại sản phẩm. Trường `screen_size` có nghĩa với TV, `shoe_size` có nghĩa với giày, nhưng cả hai đều không phù hợp với sách. Nếu thiết kế một bảng có hàng trăm cột dùng chung, rất nhiều ô sẽ rỗng; nếu tách thành nhiều bảng phụ, truy vấn hiển thị sản phẩm có thể trở nên phức tạp.

**Document database** cho phép mỗi tài liệu biểu diễn một thực thể với cấu trúc lồng nhau và những thuộc tính riêng. Điều này đặc biệt hữu ích với:

- Danh mục hàng hóa có thuộc tính theo từng nhóm.
- Hồ sơ người dùng có cấu hình tùy chọn.
- Nội dung do người dùng tạo với nhiều loại metadata.
- API thường trao đổi dữ liệu theo dạng JSON.

“Lược đồ linh hoạt” (**flexible schema**) không có nghĩa là “không cần lược đồ”. Ứng dụng vẫn cần quy ước tên trường, kiểu dữ liệu, trường bắt buộc, phiên bản cấu trúc, quy tắc kiểm tra và kế hoạch chuyển đổi dữ liệu khi thay đổi.

### 3.3. Độ trễ thấp cho thao tác rất đơn giản

Giỏ hàng, phiên đăng nhập, mã xác thực tạm thời, bộ đếm hoặc cấu hình tính năng thường có chung đặc điểm: ứng dụng đã biết một **khóa định danh** và chỉ cần lấy hoặc cập nhật giá trị tương ứng.

Thay vì thiết kế truy vấn nhiều bảng cho từng thao tác, mô hình **key–value** tổ chức theo dạng:

~~~text
session:token_abc  -> { userId: 42, expiresAt: ... }
cart:user_42       -> { items: [...], updatedAt: ... }
feature:checkout   -> enabled
~~~

Việc tra cứu theo khóa có thể rất nhanh và nhiều hệ hỗ trợ thời hạn sống (**TTL — time to live**) để tự loại bỏ dữ liệu tạm. Nhưng khi cần “tìm tất cả giỏ hàng có sản phẩm X” hoặc “liệt kê phiên theo nhiều thuộc tính”, key–value thuần túy thường không phù hợp nếu không có chỉ mục hoặc cấu trúc bổ sung.

### 3.4. Dòng dữ liệu sự kiện được ghi liên tục

Ứng dụng theo dõi lượt nhấp, thiết bị IoT, log hoặc hành vi người dùng thường ghi vô số sự kiện mới. Những câu hỏi điển hình là:

- Lấy 100 sự kiện gần đây của người dùng U.
- Đọc dữ liệu của thiết bị D trong khoảng thời gian T.
- Tổng hợp số lần xảy ra sự kiện theo phút, giờ hoặc ngày.

Đây là loại tải **ghi nhiều, đọc theo khóa và khoảng thời gian**, có thể được phục vụ tốt bởi một mô hình wide-column hoặc cơ sở dữ liệu chuỗi thời gian. Khả năng phân vùng theo thời gian, giữ dữ liệu theo kỳ hạn, nén và tổng hợp nhiều mẫu liên tiếp trở nên quan trọng hơn khả năng JOIN tùy ý.

### 3.5. Quan hệ giữa các đối tượng là trung tâm của bài toán

Một hệ thống chống gian lận muốn tìm các tài khoản dùng chung địa chỉ giao hàng, thiết bị, số điện thoại hoặc phương thức thanh toán. Nếu phải đi qua nhiều lớp quan hệ, câu truy vấn có thể trở thành một chuỗi JOIN tự nối phức tạp.

**Graph database** đặt thực thể và mối quan hệ ở vị trí trung tâm: tài khoản là đỉnh, thiết bị là đỉnh, “sử dụng thiết bị” là cạnh. Truy vấn có thể yêu cầu “đi từ tài khoản A qua thiết bị đến những tài khoản khác”, hoặc tìm một đường đi giữa hai đối tượng. Mô hình này phù hợp khi **đường đi và sự liên kết** là dữ liệu cần khai thác, thay vì chỉ tìm một bản ghi riêng lẻ.

### 3.6. Hệ thống hoạt động trên nhiều máy, nhiều vùng địa lý

Với dịch vụ phân tán, lỗi mạng và lỗi máy là điều phải dự kiến. Nhà thiết kế cần trả lời:

- Dữ liệu có được sao chép đến nhiều nút hay vùng không?
- Nếu một nút chưa nhận bản cập nhật mới nhất, có cho phép đọc giá trị cũ trong thời gian ngắn không?
- Khi mất kết nối giữa các nhóm nút, hệ thống sẽ tiếp tục phục vụ thao tác nào?
- Thời điểm nào một cập nhật được xem là thành công?

Nhiều hệ NoSQL cung cấp các lựa chọn về nhân bản, nhất quán và độ sẵn sàng để phù hợp những bài toán phân tán lớn. Tuy nhiên, **không có một chính sách nhất quán chung cho mọi cơ sở dữ liệu NoSQL**; thậm chí chính sách có thể thay đổi theo thao tác, bảng hoặc cấu hình.

## 4. Các mô hình dữ liệu phổ biến và cách chúng giải quyết bài toán

### 4.1. Key–value: khi ứng dụng đã biết khóa

**Đơn vị lưu trữ:** một khóa ánh xạ đến một giá trị. Giá trị có thể là chuỗi, JSON hoặc cấu trúc dữ liệu như danh sách, tập hợp, hash, tùy sản phẩm.

~~~text
GET cart:user_42
    -> { "items": [{ "sku": "P100-M-BLACK", "quantity": 2 }] }

SET cart:user_42
    -> { "items": [{ "sku": "P100-M-BLACK", "quantity": 3 }] }
~~~

Những lựa chọn như Redis thường được dùng cho cache, phiên, giỏ hàng, bộ đếm và dữ liệu cần phản hồi nhanh. Khả năng lưu bền, cấu trúc giá trị, cơ chế hết hạn và chính sách eviction phụ thuộc cấu hình, nên không thể mặc định mọi dữ liệu đặt vào key–value đều an toàn như dữ liệu giao dịch được lưu bền.

**Phù hợp:** đọc/ghi dựa trên khóa, số lượng thao tác rất lớn, cấu trúc truy cập đơn giản.

**Kém phù hợp:** truy vấn tùy ý theo nhiều điều kiện, JOIN và các quan hệ nhiều bước.

**Câu hỏi thiết kế:** Khóa có đủ ổn định không? Giá trị có bị quá lớn không? Dữ liệu có cần được giữ vĩnh viễn hay có thể hết hạn?

### 4.2. Document: khi một thực thể có dữ liệu lồng nhau và đa dạng

**Đơn vị lưu trữ:** tài liệu, thường biểu diễn tương tự JSON; các tài liệu được tổ chức trong collection hoặc cấu trúc tương đương. MongoDB là một ví dụ tiêu biểu.

~~~json
{
  "_id": "P200",
  "name": "Laptop",
  "brand": "ExampleBrand",
  "specifications": {
    "cpu": "8 cores",
    "ramGB": 16,
    "storageGB": 512
  },
  "tags": ["office", "portable"]
}
~~~

Một tài liệu có thể chứa các nhóm trường lồng nhau, mảng và thông tin mà giao diện thường cần lấy cùng lúc. Cơ sở dữ liệu document thường hỗ trợ chỉ mục và truy vấn theo thuộc tính bên trong tài liệu, không chỉ tìm theo ID.

**Phù hợp:** catalog, nội dung CMS, cấu hình, hồ sơ người dùng, dữ liệu theo aggregate (một nhóm thông tin thường được xử lý như một khối).

**Đánh đổi:** nhúng quá nhiều dữ liệu có thể làm tài liệu lớn; sao chép thông tin chung sang nhiều tài liệu làm tăng công việc cập nhật; các quan hệ phức tạp có thể đòi hỏi truy vấn nhiều lần hoặc cơ chế liên kết.

**Nguyên tắc nhúng hay tham chiếu:** nhúng khi dữ liệu liên quan nhỏ, có vòng đời gắn chặt và thường được đọc cùng nhau; tham chiếu khi dữ liệu có kích thước lớn, dùng chung cho nhiều thực thể hoặc thay đổi độc lập. Đây là nguyên tắc khởi đầu, cần điều chỉnh theo truy vấn và khả năng của hệ cụ thể.

### 4.3. Wide-column: khi truy vấn dựa trên khóa phân vùng

**Đơn vị lưu trữ:** dữ liệu được tổ chức quanh khóa phân vùng và các cột sắp xếp, thích hợp cho những tập bản ghi lớn có mẫu truy vấn được xác định trước. Apache Cassandra là ví dụ nổi bật.

Một bảng sự kiện theo người dùng và ngày có thể được mô hình hóa như sau (cú pháp mang tính minh họa theo Cassandra Query Language):

~~~sql
CREATE TABLE user_events (
    user_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    action text,
    PRIMARY KEY ((user_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Trong ví dụ này, cặp `(user_id, event_day)` xác định phân vùng; `event_time` và `event_id` là khóa sắp xếp bên trong phân vùng. Câu hỏi “sự kiện gần đây của người dùng U trong ngày D” phù hợp với cấu trúc đó.

Ngược lại, yêu cầu “tìm mọi sự kiện có `action = 'purchase'` trên toàn bộ người dùng” không phải truy vấn được hỗ trợ hiệu quả chỉ nhờ thiết kế trên. Ta có thể cần **bảng theo mẫu truy vấn khác**, chỉ mục thích hợp hoặc một hệ chuyên phân tích.

**Phù hợp:** ghi phân tán quy mô lớn, nhật ký hoạt động, telemetry, dữ liệu truy xuất theo partition key và thứ tự thời gian.

**Đánh đổi:** phải thiết kế bảng theo câu truy vấn; chọn partition key sai có thể gây mất cân bằng tải; JOIN và truy vấn linh hoạt thường không phải thế mạnh.

**Lưu ý thuật ngữ:** wide-column/column-family như Cassandra **khác** với cơ sở dữ liệu phân tích lưu trữ theo cột (columnar analytics) vốn tối ưu quét/tổng hợp các cột trên khối dữ liệu lớn.

### 4.4. Graph: khi ý nghĩa nằm ở các cạnh nối

**Đơn vị lưu trữ:** đỉnh (node/vertex) đại diện cho thực thể; cạnh (edge/relationship) biểu diễn quan hệ, có thể mang thuộc tính.

~~~text
(Account A) --USES_DEVICE--> (Device D)
(Account B) --USES_DEVICE--> (Device D)
(Account B) --USES_CARD----> (Card C)
~~~

Một truy vấn mô tả các tài khoản dùng chung thiết bị với A có thể viết theo cú pháp Cypher minh họa:

~~~cypher
MATCH (a:Account {id: 'A'})-[:USES_DEVICE]->(d:Device)
      <-[:USES_DEVICE]-(other:Account)
RETURN DISTINCT other.id;
~~~

Những hệ như Neo4j phù hợp với tìm đường đi, mạng xã hội, gợi ý theo quan hệ, tri thức liên kết và phát hiện mẫu gian lận.

**Phù hợp:** truy vấn nhiều bước qua những mối liên hệ thay đổi liên tục hoặc khó biểu diễn bằng một số JOIN cố định.

**Đánh đổi:** không nhất thiết là lựa chọn kinh tế nhất cho tra cứu khóa đơn giản, log khối lượng lớn hoặc tổng hợp dạng bảng. Cơ sở dữ liệu quan hệ vẫn có thể xử lý nhiều bài toán quan hệ rất tốt, nhất là khi kiểu nối đã biết và được tối ưu.

### 4.5. Các hệ chuyên dụng: time-series và search

Không phải mọi sản phẩm chuyên dụng đều nằm hoàn toàn trong một nhóm NoSQL, nhưng chúng minh họa rõ **bài toán dẫn đến mô hình lưu trữ riêng**:

| Nhu cầu | Mô hình/phương pháp thường gặp | Cách truy cập chính |
|---|---|---|
| Đo nhiệt độ mỗi giây, CPU, độ trễ, dữ liệu sensor | Time-series database như InfluxDB; một số hệ SQL cũng chuyên time-series | Lọc theo nhãn thiết bị và thời gian, tổng hợp theo khoảng, retention |
| Tìm sản phẩm gần đúng, gõ sai chính tả, lọc và xếp hạng tài liệu | Search engine như Elasticsearch/OpenSearch | Inverted index, phân tích từ, relevance score |
| Báo cáo phân tích trên dữ liệu lớn | Data warehouse, OLAP hoặc columnar engine | Quét/tổng hợp nhiều bản ghi, số chiều đo lớn |

Ở đây, câu hỏi chủ đạo không chỉ là “SQL hay NoSQL?” mà là **hệ thống phải thực hiện thao tác nào với hiệu năng và đặc tính gì?** Một hệ time-series có thể dùng SQL; một search engine thường nhận dữ liệu đồng bộ từ nguồn giao dịch thay vì thay thế toàn bộ nguồn đó.

## 5. Vì sao không có một mô hình tối ưu cho tất cả?

### 5.1. Đọc theo đối tượng và đọc theo mối quan hệ có chi phí khác nhau

Khi một trang sản phẩm luôn cần tên, thuộc tính và các biến thể, gom chúng trong một tài liệu có thể giảm số lần truy vấn. Khi nhiều đơn hàng cùng tham chiếu một khách hàng, giữ thông tin khách hàng tập trung trong bảng quan hệ có thể giảm cập nhật lặp lại. Khi cần đi qua 5 lớp quan hệ, graph có thể diễn đạt truy vấn tự nhiên hơn.

**Cách nhóm dữ liệu làm rẻ một số truy vấn và làm đắt những truy vấn khác.** Vì vậy, chọn mô hình dữ liệu nghĩa là chọn xem ứng dụng sẽ tối ưu đường truy cập nào.

### 5.2. Chuẩn hóa và phi chuẩn hóa đều có mục đích

- **Chuẩn hóa (normalization):** chia dữ liệu để giảm trùng lặp, làm rõ ràng buộc, tránh sai lệch khi cập nhật. Rất phù hợp cho nhiều hệ thống giao dịch quan hệ.
- **Phi chuẩn hóa (denormalization):** lưu dữ liệu dư hoặc gom trước các phần thường được đọc cùng nhau. Có thể tăng tốc đọc và đơn giản hóa đường truy vấn, nhưng phải quản lý việc đồng bộ khi dữ liệu thay đổi.

Ví dụ, lưu `product_name_snapshot` và `unit_price_at_purchase` trong chi tiết đơn hàng là một lựa chọn có chủ đích: đơn hàng cần giữ thông tin **tại thời điểm mua**, cho dù sản phẩm đổi tên hoặc đổi giá sau đó. Ngược lại, lưu 10 bản sao của “tồn kho hiện tại” mà không có cơ chế đồng bộ rõ ràng dễ dẫn đến bán vượt số lượng.

### 5.3. Tính nhất quán, độ sẵn sàng và lỗi mạng

Trong hệ thống phân tán, các bản sao có thể chưa cập nhật đồng thời. Có một số khái niệm cần tách bạch:

| Khái niệm | Ý nghĩa thực tế |
|---|---|
| **Strong consistency / linearizability** | Sau khi một thao tác ghi hoàn tất, những lượt đọc sau đó trong phạm vi bảo đảm sẽ thấy giá trị mới nhất |
| **Eventual consistency** | Nếu ngừng cập nhật và hệ thống tiếp tục hoạt động bình thường, các bản sao sẽ dần hội tụ về cùng trạng thái |
| **Availability** | Hệ thống còn trả lời yêu cầu theo cam kết của mô hình đang xét |
| **Partition tolerance** | Hệ thống được thiết kế để xử lý tình huống mất liên lạc giữa các nhóm nút |

**Định lý CAP** nói rằng khi xảy ra phân hoạch mạng, một hệ thống phân tán không thể đồng thời bảo đảm cả **tính nhất quán tuyến tính** (C theo CAP) và **tính sẵn sàng** (A theo định nghĩa CAP) cho mọi yêu cầu. CAP không có nghĩa “bất kỳ lúc nào cũng phải chọn hai trong ba”, cũng không chứng minh mọi NoSQL đều ưu tiên A.

Trong điều kiện mạng bình thường, ta còn phải cân bằng **độ trễ** với **mức nhất quán**. Một hệ có thể cho phép lựa chọn mức nhất quán ở thao tác đọc/ghi hoặc hỗ trợ giao dịch mạnh trong một phạm vi nhất định. Cần đọc tài liệu của chính sản phẩm và cấu hình cụ thể.

**ACID** và **CAP** cũng là hai cách nhìn khác nhau. ACID nói về các thuộc tính giao dịch (Atomicity, Consistency theo ràng buộc nghiệp vụ, Isolation, Durability), trong khi chữ C của CAP nói về cách quan sát dữ liệu trên hệ phân tán. Không nên kết luận rằng “SQL = ACID, NoSQL = không ACID”. Nhiều hệ NoSQL có giao dịch, và mức bảo đảm phụ thuộc cơ chế, phạm vi và cấu hình.

### 5.4. Đơn giản hóa một truy vấn có thể khiến việc cập nhật khó hơn

Giả sử danh mục sản phẩm lưu cả tên nhà cung cấp trong từng tài liệu sản phẩm. Trang chi tiết đọc nhanh vì không cần JOIN. Nhưng khi nhà cung cấp đổi tên, hệ thống phải cập nhật nhiều tài liệu hoặc chấp nhận trạng thái tạm thời khác nhau.

Đây là sự đánh đổi thường gặp giữa:

- **Read path**: số bước và chi phí để trả lời câu hỏi.
- **Write path**: số nơi và thứ tự phải cập nhật khi dữ liệu đổi.
- **Consistency requirement**: bao lâu các bản sao hoặc dữ liệu sao chép phải đồng nhất.

Một thiết kế tốt trả lời rõ cả ba thay vì chỉ đo thời gian đọc của một ví dụ đơn lẻ.

## 6. Đặt bài toán trước, chọn database sau

### Bước 1: Liệt kê các câu truy vấn thực tế

Không bắt đầu bằng “muốn dùng MongoDB/Redis/Cassandra”. Hãy viết ra:

1. Người dùng hoặc dịch vụ thường yêu cầu dữ liệu gì?
2. Tra cứu theo ID, lọc nhiều thuộc tính, duyệt quan hệ hay truy vấn theo khoảng thời gian?
3. Tần suất đọc và ghi là bao nhiêu? Truy vấn nào nằm trên đường phản hồi trực tiếp tới người dùng?
4. Có cần tìm kiếm văn bản, tổng hợp thống kê, xếp hạng hay xử lý hàng loạt không?

Ví dụ: “Hiển thị 20 sự kiện cuối của thiết bị T trong vòng một ngày” có ảnh hưởng trực tiếp tới thiết kế khóa phân vùng và thứ tự sắp xếp.

### Bước 2: Làm rõ ràng buộc dữ liệu

Một số yêu cầu nghiêm ngặt:

- Không được trừ tiền hai lần cho cùng giao dịch.
- Không cho phép số lượng tồn kho âm nếu nghiệp vụ cấm bán vượt tồn.
- Một đơn hàng chỉ chuyển trạng thái theo luồng hợp lệ.

Các yêu cầu đó cần cơ chế giao dịch, thao tác nguyên tử, kiểm tra điều kiện hoặc phối hợp phù hợp, bất kể nhãn công nghệ. Trong khi đó, số lượt xem sản phẩm cập nhật chậm vài giây thường có thể chấp nhận được.

### Bước 3: Tính quy mô và phân bố tải

Cần ước lượng số bản ghi, kích thước dữ liệu, tốc độ tăng trưởng, tỉ lệ đọc/ghi, số lượng người dùng đồng thời, mục tiêu độ trễ (chẳng hạn p95/p99), thời gian lưu giữ và chi phí vận hành. Đặc biệt phải tìm **khóa nóng** hoặc trường hợp một khách hàng/thiết bị sinh ra tải lớn bất thường.

### Bước 4: Chọn mô hình theo cách dữ liệu được sử dụng

| Nếu trọng tâm là… | Nên xem xét… | Phải kiểm tra thêm… |
|---|---|---|
| Giao dịch nhiều thực thể, ràng buộc rõ ràng, truy vấn JOIN linh hoạt | Relational | Chỉ mục, transaction isolation, phân vùng, tải đỉnh |
| Tra cứu nhanh bằng khóa, dữ liệu tạm/TTL | Key–value | Persistence, eviction, kích thước giá trị, hotspot |
| Thực thể nhiều thuộc tính lồng nhau, dữ liệu thường đọc cùng nhau | Document | Index, cập nhật nhiều tài liệu, kích thước tài liệu |
| Ghi sự kiện phân tán, đọc theo partition key và thứ tự | Wide-column | Thiết kế partition/clustering key, cân bằng phân vùng |
| Duyệt quan hệ nhiều bước, phân tích kết nối | Graph | Kiểu traversal, quy mô đồ thị, tải ghi |
| Tính toán theo thời gian, retention và aggregation | Time-series | Độ phân giải, downsampling, nhãn có cardinality cao |
| Tìm kiếm từ ngữ, xếp hạng, lọc văn bản | Search engine | Độ trễ đồng bộ chỉ mục, tính mới của kết quả |

Bảng này là định hướng lựa chọn, **không phải luật bắt buộc**. Có nhiều công nghệ hỗ trợ chồng lấp chức năng.

### Bước 5: Đánh giá chi phí duy trì tính đúng đắn

Có cần cập nhật dữ liệu ở nhiều nơi không? Có chấp nhận đọc dữ liệu cũ không? Có cơ chế phát hiện và xử lý sự kiện lặp, lỗi một phần, retry, hoặc xung đột giữa các bản sao không?

Chỉ nên đưa dữ liệu sang nhiều hệ khác nhau khi lợi ích lớn hơn chi phí phát triển, giám sát, bảo mật, sao lưu, khôi phục và đồng bộ. Một RDBMS được lập chỉ mục và phân vùng tốt có thể là lựa chọn đơn giản, đáng tin cậy nhất cho một hệ thống ở giai đoạn đầu.

## 7. Ví dụ kiến trúc: mỗi loại dữ liệu phục vụ một mục đích

Xét một ứng dụng bán hàng có tăng trưởng lớn. Một kiến trúc khả thi có thể là:

~~~text
                       Ứng dụng bán hàng
                              |
      +-----------------------+-----------------------+
      |                       |                       |
  Orders/Payments         Product catalog        Session/Cart
      |                       |                       |
  Relational DB           Document DB            Key–value
      |
      +---- phát sự kiện nghiệp vụ ----> Event stream
                                             |
                               +-------------+-------------+
                               |                           |
                        Activity/Telemetry            Search index
                      Wide-column/Time-series         Search engine
~~~

Đây là ví dụ về **polyglot persistence**: dùng hơn một kiểu lưu trữ vì các phần của hệ thống có nhu cầu khác nhau. Tùy mức độ phức tạp, hệ thống có thể thêm graph database cho chức năng gợi ý hoặc chống gian lận.

Phân công trách nhiệm cần rõ:

- **Đơn hàng/thanh toán**: nguồn sự thật chính cho giao dịch. Dữ liệu cần nhất quán theo nghiệp vụ.
- **Catalog**: mô tả sản phẩm đa dạng, hiển thị theo thực thể. Tồn kho có thể nằm trong thành phần bảo đảm cập nhật nguyên tử riêng.
- **Giỏ hàng**: thao tác nhanh theo người dùng; thiết kế thời hạn lưu giữ và khôi phục dựa trên yêu cầu.
- **Nhật ký tương tác**: lượng ghi lớn, chủ yếu truy vấn theo người dùng hoặc theo thời gian.
- **Chỉ mục tìm kiếm**: được xây dựng từ dữ liệu nguồn, có thể cập nhật chậm hơn nguồn chính.

Ví dụ khách hàng đổi tên sản phẩm: hệ catalog cập nhật dữ liệu gốc, sau đó phát sự kiện để làm mới chỉ mục tìm kiếm. Trong một khoảng ngắn, trang chi tiết có thể hiển thị tên mới nhưng kết quả tìm kiếm vẫn mang tên cũ. Nếu nghiệp vụ chấp nhận điều này, đồng bộ bất đồng bộ là hợp lý. Nếu dữ liệu ảnh hưởng đến thanh toán hoặc ràng buộc pháp lý, cần bảo đảm chặt hơn.

Kiến trúc nhiều database không phải mục tiêu tự thân. Mỗi hệ bổ sung kéo theo kết nối, giám sát, sao lưu, kiểm soát truy cập, khôi phục sự cố và quy trình xử lý khi cập nhật một phần. Ở quy mô nhỏ, một cơ sở dữ liệu quan hệ có cột JSON, cache và chỉ mục thích hợp có thể đáp ứng đầy đủ nhu cầu.

## 8. Những hiểu lầm phổ biến về NoSQL

**“NoSQL không có schema.”** Sai. Schema có thể được thực thi ở lớp ứng dụng, bằng validator của database, bằng quy ước collection hoặc bằng cấu trúc khóa. Không quản lý schema sẽ làm dữ liệu khó kiểm soát và khó nâng cấp.

**“NoSQL luôn nhanh hơn SQL.”** Sai. Hiệu năng phụ thuộc truy vấn, chỉ mục, cách phân vùng, kích thước dữ liệu, phần cứng và cấu hình. Một truy vấn JOIN có chỉ mục tốt có thể nhanh hơn cách gom dữ liệu kém hợp lý; một hệ key–value cũng có thể chậm vì khóa nóng.

**“Dùng NoSQL thì phải chấp nhận dữ liệu không nhất quán.”** Sai. Các hệ NoSQL có những mức bảo đảm khác nhau, và nhiều hệ hỗ trợ thao tác nguyên tử hoặc giao dịch. Hãy nêu chính xác yêu cầu nhất quán của từng thao tác.

**“Cần dữ liệu lớn thì phải chuyển sang NoSQL.”** Sai. Dung lượng lớn không tự quyết định mô hình. Các hệ quan hệ phân tán, data warehouse và giải pháp chuyên dụng có thể xử lý tập dữ liệu rất lớn.

**“Document database là nơi chứa JSON tùy ý.”** Chưa đủ. Giá trị của nó nằm ở cách truy cập tài liệu, cập nhật, lập chỉ mục và tổ chức aggregate; tính linh hoạt phải được quản lý có chủ đích.

**“Đưa mọi thứ vào cùng một tài liệu sẽ tránh được JOIN.”** Nguy hiểm. Tài liệu có thể phình to, gây ghi dư thừa, xung đột cập nhật hoặc khó xử lý các quan hệ nhiều–nhiều.

**“NoSQL thay thế hoàn toàn cơ sở dữ liệu quan hệ.”** Sai. RDBMS vẫn là lựa chọn mạnh cho nhiều ứng dụng giao dịch và báo cáo. Mục tiêu là chọn thiết kế phù hợp với yêu cầu, không chạy theo nhãn công nghệ.

## 9. Tình huống tự vận dụng

### Tình huống A: quản lý lịch sử đo cảm biến

Một nhà máy nhận dữ liệu từ 100.000 cảm biến. Mỗi cảm biến gửi nhiệt độ mỗi 10 giây. Người vận hành thường xem biểu đồ nhiệt độ của một thiết bị trong 24 giờ gần nhất, trung bình theo phút và cảnh báo khi vượt ngưỡng.

**Gợi ý tư duy:** Đây là luồng dữ liệu gắn thời gian, có nhiều lượt ghi liên tục và thường đọc theo `device_id` cùng khoảng thời gian. Hãy xem xét time-series database hoặc mô hình wide-column, rồi xác định retention, cách phân vùng và phương án tổng hợp. Các quy tắc cảnh báo thời gian thực có thể cần một thành phần xử lý sự kiện riêng.

### Tình huống B: hệ thống đặt vé

Khách đặt vé cuối cùng của một chuyến xe. Hai người nhấn mua gần như đồng thời, nhưng hệ thống không được bán cùng một ghế hai lần.

**Gợi ý tư duy:** Trọng tâm là khả năng bảo vệ điều kiện đặt chỗ dưới truy cập đồng thời, không phải “dữ liệu có linh hoạt không”. Cần giao dịch hoặc cơ chế cập nhật có điều kiện với tính nguyên tử phù hợp. Relational DB thường là lựa chọn tự nhiên; dùng NoSQL vẫn phải chứng minh được cơ chế bảo đảm đó.

### Tình huống C: phát hiện tài khoản gian lận

Hệ thống cần tìm những tài khoản liên kết gián tiếp qua thiết bị, thẻ thanh toán và địa chỉ IP, trong giới hạn ba bước quan hệ, để phục vụ phân tích rủi ro.

**Gợi ý tư duy:** Hãy xem xét graph database vì câu truy vấn chính là duyệt quan hệ. Trước khi chọn, cần biết số lượng đỉnh/cạnh, hướng truy vấn, tần suất cập nhật và cách giải thích kết quả. Một hệ quan hệ được thiết kế tốt vẫn có thể giải quyết nếu quan hệ và truy vấn đủ đơn giản.

## 10. Kết luận

NoSQL là **tập hợp những lựa chọn mô hình dữ liệu và hệ quản trị** phát triển để phục vụ các dạng truy cập mà mô hình bảng quan hệ không phải lúc nào cũng thuận tiện nhất: tra cứu theo khóa, tài liệu linh hoạt, sự kiện phân tán, chuỗi thời gian, tìm kiếm và mạng quan hệ nhiều bước.

Thay vì hỏi “SQL hay NoSQL tốt hơn?”, hãy hỏi: **Ứng dụng đọc và ghi dữ liệu ra sao? Những ràng buộc nào tuyệt đối không được vi phạm? Cần mở rộng theo chiều nào? Đổi lấy tốc độ hoặc độ linh hoạt thì hệ thống phải trả chi phí gì?** Trả lời được những câu hỏi đó là nền tảng để chọn mô hình dữ liệu đúng và xây dựng hệ thống đáng tin cậy.
