# Khóa ghép, thứ tự thành phần và khả năng truy vấn theo tiền tố

## 1. Vấn đề: cùng một bộ trường, đổi thứ tự khóa có thể đổi khả năng truy vấn

Trong hệ thống NoSQL, khóa không chỉ là cách đặt tên cho một bản ghi. Ở nhiều cơ sở dữ liệu, khóa còn quyết định **dữ liệu được đặt ở đâu**, **bản ghi được sắp xếp như thế nào** và **truy vấn nào có thể dùng chỉ mục thay vì quét dữ liệu**.

Giả sử ứng dụng đa khách hàng (multi-tenant) lưu đơn hàng với các thuộc tính:

| Trường | Ý nghĩa | Giá trị minh họa |
| --- | --- | --- |
| tenantId | Đơn vị sở hữu dữ liệu | T01 |
| customerId | Khách hàng | C088 |
| createdAt | Thời điểm tạo đơn | 2026-11-14T08:30:00Z |
| orderId | Mã đơn duy nhất | O947 |
| status | Trạng thái | PAID |

Một số nhu cầu truy vấn là:

1. Lấy tất cả đơn của khách C088 thuộc tenant T01.
2. Lấy đơn của khách đó trong một khoảng thời gian, mới nhất trước.
3. Lấy một đơn khi đã biết mã O947.
4. Lấy tất cả đơn có trạng thái PAID của tenant T01, không phụ thuộc khách hàng.

Nếu khóa ghép có thứ tự **(tenantId, customerId, createdAt, orderId)**, hai truy vấn đầu có thể rất thuận lợi với một chỉ mục có thứ tự và hỗ trợ tiền tố. Nhưng truy vấn theo **status** không tự nhiên được khóa này hỗ trợ. Đổi thành **(tenantId, status, customerId, createdAt)** thì truy vấn theo trạng thái có thể tốt hơn, còn truy vấn lịch sử của một khách với tất cả trạng thái có thể trở nên khó hơn.

Vì vậy, khi thiết kế khóa ghép, phải đi từ **mẫu truy cập dữ liệu (access pattern)** và khả năng cụ thể của hệ quản trị. Cùng tên “NoSQL” nhưng DynamoDB, Cassandra, MongoDB, Redis hay một kho key–value có thứ tự sử dụng khái niệm khóa khác nhau.

## 2. Ba khái niệm cần phân biệt

### 2.1. Khóa định danh bản ghi

**Khóa định danh** cho biết bản ghi nào là duy nhất. Ví dụ:

~~~text
orderId = O947

hoặc một định danh ghép:
(tenantId, orderId) = (T01, O947)
~~~

Nếu mã đơn chỉ duy nhất bên trong một tenant, cặp **(tenantId, orderId)** là một định danh đầy đủ; chỉ dùng **orderId** có thể gây trùng giữa các tenant. Việc cặp trường tạo thành định danh **không tự động** bảo đảm hệ quản trị có thể tìm nhanh bằng riêng **tenantId**: điều đó phụ thuộc cấu trúc chỉ mục và cách lưu trữ.

### 2.2. Khóa phân vùng và khóa sắp xếp

Một số NoSQL phân tán tổ chức dữ liệu theo:

- **Partition key**: xác định vùng/nhóm lưu trữ logic hoặc giá trị băm dùng để phân phối dữ liệu.
- **Sort key / clustering column**: xác định thứ tự các bản ghi trong phạm vi partition, theo quy tắc riêng của hệ quản trị.
- **Secondary index**: cung cấp đường truy cập bổ sung khi truy vấn chính không phù hợp với khóa lưu trữ.

Ví dụ mô hình logic:

~~~text
Partition = TENANT#T01#CUSTOMER#C088

    ORDER#2026-11-15T09:10:00Z#O948
    ORDER#2026-11-14T08:30:00Z#O947
    ORDER#2026-11-12T11:00:00Z#O946
~~~

Ở hệ có sort key được sắp theo thứ tự, các đơn của cùng khách nằm trong cùng phạm vi khóa phân vùng và có thể truy cập theo khoảng thời gian. Thứ tự thực tế tăng hay giảm, khả năng quét ngược và giới hạn mỗi partition phụ thuộc hệ quản trị.

### 2.3. Khóa ghép và chỉ mục ghép không phải một

**Khóa ghép (composite key)** là khóa tạo bởi nhiều thành phần. Tùy sản phẩm, đó có thể là:

- Một **partition key** gồm nhiều trường, ví dụ cặp **(tenantId, customerId)** trong Cassandra.
- Một **primary key** gồm partition key và sort key, như cặp **(PK, SK)** trong bảng DynamoDB.
- Một **compound index** trên nhiều trường của document, ví dụ **{tenantId: 1, customerId: 1, createdAt: -1}** trong MongoDB.
- Một chuỗi khóa do ứng dụng tự ghép, chẳng hạn **TENANT#T01#CUSTOMER#C088#ORDER#O947** trong key–value store.

Bốn trường hợp trên **không cung cấp cùng một bộ phép truy vấn**. Đặc biệt, khi ứng dụng ghép nhiều trường thành **một chuỗi** rồi đem đi băm để chọn partition, hệ thống không nhất thiết hiểu các thành phần bên trong hay hỗ trợ truy vấn từng tiền tố.

## 3. Tiền tố trái nhất là gì?

Giả sử một cấu trúc chỉ mục có thứ tự được định nghĩa bởi bộ trường:

~~~text
K = (A, B, C, D)
~~~

Các **tiền tố trái nhất (leftmost prefixes)** của K là:

~~~text
(A)
(A, B)
(A, B, C)
(A, B, C, D)
~~~

Các bộ **(B)**, **(A, C)** hoặc **(B, C)** không phải tiền tố trái nhất vì bỏ qua một thành phần đứng trước.

Với một **chỉ mục ghép có thứ tự theo từ điển** và cơ chế truy vấn hỗ trợ, dữ liệu có cùng A nằm trong một vùng chỉ mục; trong vùng A, dữ liệu có cùng B thường nằm gần nhau; sau đó mới xét C và D. Bởi vậy, điều kiện bằng nhau trên các trường đầu có thể thu hẹp phạm vi đọc hiệu quả.

Ví dụ dùng thứ tự **(tenantId, customerId, createdAt)**:

| Điều kiện truy vấn | Quan hệ với tiền tố | Nhận định ban đầu |
| --- | --- | --- |
| tenantId = T01 | Khớp A | Có khả năng tìm theo tiền tố đầu |
| tenantId = T01, customerId = C088 | Khớp (A, B) | Có khả năng thu hẹp theo hai trường đầu |
| tenantId = T01, customerId = C088, createdAt trong khoảng | Bằng nhau trên (A, B), khoảng trên C | Thường thuận lợi cho range scan |
| customerId = C088 | Thiếu A | Không tận dụng được tiền tố trái nhất theo cách thông thường |
| tenantId = T01, createdAt trong khoảng | Bỏ qua B | Không có một đoạn liên tục nhỏ bảo đảm cho điều kiện thời gian |
| status = PAID | Trường không có trong khóa | Cần đường truy cập khác hoặc lọc |

**Đây là quy tắc tư duy cho chỉ mục nhiều trường có thứ tự, không phải bảo đảm phổ quát cho mọi loại NoSQL.** Hệ quản trị có thể có bộ tối ưu, chỉ mục phụ hoặc kỹ thuật quét riêng; phải kiểm tra kế hoạch thực thi và giới hạn của từng sản phẩm.

### 3.1. Vì sao điều kiện bằng nhau thường đứng trước điều kiện khoảng?

Một chỉ mục **(tenantId, customerId, createdAt)** được sắp theo tenant trước, rồi customer, rồi thời gian. Khi biết chính xác **tenantId** và **customerId**, hệ có thể tìm một đoạn chỉ mục liên tiếp và đi qua các giá trị **createdAt** trong khoảng.

Nếu chỉ biết **tenantId** và **createdAt**, các sự kiện ở cùng khoảng thời gian của nhiều khách lại nằm rải trong các nhóm customer. Hệ thống có thể phải đọc nhiều đoạn, quét rộng hoặc dùng chỉ mục khác.

Một nguyên tắc thiết kế hữu ích là **equality trước, range sau**, nhưng vị trí trường phục vụ **ORDER BY**, độ chọn lọc, khả năng bao phủ và bộ tối ưu có thể làm lựa chọn tối ưu thay đổi. Không nên áp dụng quy tắc như công thức tuyệt đối.

### 3.2. Thứ tự khóa tác động cả việc sắp xếp kết quả

Với chỉ mục **(tenantId, customerId, createdAt DESC)**, yêu cầu “lấy 20 đơn mới nhất của một khách trong một tenant” có thể được phục vụ gần với thứ tự đã lưu. Nhưng yêu cầu “20 đơn mới nhất của toàn tenant, bất kể khách hàng” không còn tương thích trực tiếp, vì mỗi customer tạo một nhóm riêng.

Điều kiện lọc **và** thứ tự kết quả phải được thiết kế cùng nhau. Một truy vấn tìm được bản ghi nhờ chỉ mục vẫn có thể phải sắp xếp hoặc tổng hợp thêm.

## 4. Trường hợp cụ thể: DynamoDB với partition key và sort key

Trong DynamoDB, primary key của bảng có thể chỉ gồm partition key hoặc gồm **partition key + sort key**. Với dạng thứ hai, một item được định danh bằng **cặp giá trị đầy đủ**: nhiều item được phép có cùng partition key nhưng phải khác sort key trong partition đó.

Ví dụ thiết kế bảng đơn hàng theo lịch sử khách:

~~~text
PK = TENANT#T01#CUSTOMER#C088
SK = ORDER#2026-11-14T08:30:00Z#O947

Attributes:
orderId = O947
status  = PAID
amount  = 125000
~~~

Truy vấn trực tiếp phù hợp:

- **PK bằng giá trị cụ thể** để lấy các item cùng một khách.
- **PK bằng giá trị cụ thể + điều kiện SK** để lấy một đoạn thời gian hoặc một tiền tố loại đối tượng.
- **PK + SK đầy đủ** để đọc trực tiếp item có đúng cặp khóa.

Mã lệnh minh họa DynamoDB Query (các tên trường, thời gian và tham số là ví dụ):

~~~json
{
  "TableName": "Orders",
  "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
  "ExpressionAttributeValues": {
    ":pk": { "S": "TENANT#T01#CUSTOMER#C088" },
    ":prefix": { "S": "ORDER#2026-11" }
  }
}
~~~

Điều kiện này trả các đơn trong tháng 11/2026 nếu mọi SK sử dụng quy ước **ORDER#YYYY-MM-DD...** nhất quán. Việc lọc tiền tố SK ở đây là năng lực của **Query trên sort key**, không phải truy vấn tùy ý một đoạn của PK.

Để truy vấn bằng khoảng trên SK, có thể dùng điều kiện kiểu:

~~~text
PK = TENANT#T01#CUSTOMER#C088
AND
SK BETWEEN ORDER#2026-11-01 AND ORDER#2026-11-30T23:59:59Z
~~~

Trong hệ thống thực, nên ưu tiên ranh giới thời gian rõ ràng, chẳng hạn khoảng **[đầu tháng, đầu tháng kế tiếp)** ở tầng ứng dụng, đồng thời xây biểu thức SK theo phép so sánh mà DynamoDB hỗ trợ. Cần bảo đảm dạng mã hóa thời gian giữ được thứ tự và bao phủ đủ độ chính xác của dấu thời gian.

**Giới hạn cần ghi nhớ:**

1. Query bảng cần điều kiện bằng nhau với **toàn bộ giá trị PK**. Không thể chỉ cung cấp chuỗi tiền tố **TENANT#T01** rồi kỳ vọng DynamoDB Query tự lấy tất cả partition key bắt đầu bằng tiền tố đó.
2. **begins_with** có thể dùng với sort key phù hợp, không biến thành phép tìm trên mọi thuộc tính hay mọi partition key.
3. **FilterExpression** áp dụng sau khi đọc các item thỏa điều kiện khóa; nó không tự biến thuộc tính **status** thành lối truy cập chính hiệu quả.
4. Nếu cần truy vấn theo trạng thái trên toàn tenant, cân nhắc **GSI** với khóa phù hợp, hoặc bản chiếu dữ liệu khác. GSI có chi phí lưu trữ/ghi và đặc tính nhất quán đọc riêng; đọc GSI không hỗ trợ strongly consistent read.
5. Partition key có lưu lượng quá lớn vẫn có thể tạo điểm nóng. Thêm trường tháng, bucket hoặc phân bố khóa chỉ có ý nghĩa khi đã xác định cách query và tổng hợp nhiều bucket.

Một thiết kế thường dùng là thêm item tra cứu riêng:

~~~text
PK = TENANT#T01#ORDER#O947
SK = META
~~~

Nếu chọn mô hình này, ứng dụng phải xác định item nào là nguồn sự thật, cách giữ các item nhất quán và có cần transactional write hay không. Đây là **bản chiếu truy vấn khác**, không phải phép tìm miễn phí từ khóa cũ.

## 5. Trường hợp cụ thể: Cassandra với partition key ghép và clustering columns

Cassandra phân biệt rõ **partition key** và **clustering columns** trong khóa chính. Một ví dụ bảng đơn hàng:

~~~sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    total decimal,
    PRIMARY KEY (
        (tenant_id, customer_id),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Cách đọc khai báo:

- **(tenant_id, customer_id)** là **partition key ghép**: cả hai cùng xác định một partition logic.
- **created_at**, rồi **order_id** là **clustering columns**: xác định thứ tự và tính duy nhất của hàng bên trong partition.
- **status** và **total** là các thuộc tính không nằm trong primary key.

Một truy vấn phù hợp với mô hình:

~~~sql
SELECT order_id, created_at, status, total
FROM orders_by_customer
WHERE tenant_id = 'T01'
  AND customer_id = 'C088'
  AND created_at >= '2026-11-01T00:00:00Z'
  AND created_at <  '2026-12-01T00:00:00Z'
LIMIT 20;
~~~

Ở đây, điều kiện bằng nhau trên **đầy đủ partition key** đưa truy vấn tới partition thích hợp; khoảng thời gian trên clustering column đầu có thể thu hẹp các hàng cần duyệt. Thứ tự **DESC** đã được khai báo cho **created_at**.

Không nên hiểu khóa ghép Cassandra thành quy tắc “có thể truy vấn mọi tiền tố như B-tree”:

- Không phải cứ có **tenant_id** là có thể truy vấn hiệu quả mọi hàng mà không biết **customer_id**; đây là hai thành phần của cùng một partition key ghép.
- Các hạn chế đối với clustering columns mang tính tuần tự: muốn lọc sâu theo **order_id** thường phải thỏa ràng buộc trên các clustering column đứng trước, tùy dạng truy vấn.
- CQL không cung cấp JOIN nghiệp vụ như SQL quan hệ; thường phải tạo các bảng **theo truy vấn**, ví dụ bảng **orders_by_status** hoặc **orders_by_id**, nếu có nhu cầu truy cập khác.
- **ALLOW FILTERING** không phải cách thay thế lâu dài cho mô hình khóa phù hợp; nó có thể dẫn đến đọc dữ liệu rộng và hiệu năng khó dự đoán.

Nếu số đơn của một khách tăng vô hạn trong một partition, cần cân nhắc chia bucket theo tháng/quý hoặc một quy tắc có thể truy vấn được. Khi thêm bucket vào partition key, mọi truy vấn phải biết bucket hoặc chủ động thực hiện nhiều truy vấn rồi tổng hợp.

## 6. Trường hợp cụ thể: MongoDB với compound index

MongoDB cho phép tạo compound index trên nhiều trường của document. Ví dụ:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  orderId: 1
});
~~~

Thứ tự các trường trong chỉ mục có ý nghĩa. Một truy vấn phù hợp:

~~~javascript
db.orders.find({
  tenantId: "T01",
  customerId: "C088",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(20);
~~~

Vì hai trường đầu được lọc bằng nhau và thời gian đứng ngay sau, chỉ mục có thể phục vụ bộ lọc và thứ tự phù hợp. MongoDB có thể tối ưu những truy vấn phức tạp hơn, nhưng hiệu quả thực tế cần quan sát bằng **explain()** với dữ liệu và phân bố thật.

Phân biệt các truy vấn:

| Truy vấn | Khả năng tận dụng compound index đã nêu |
| --- | --- |
| tenantId | Có tiền tố đầu |
| tenantId + customerId | Có tiền tố hai trường đầu |
| tenantId + customerId + khoảng createdAt | Có tiền tố bằng nhau rồi trường khoảng |
| customerId mà không có tenantId | Thiếu trường đầu, thường không phải đường truy cập hiệu quả của chỉ mục này |
| tenantId + khoảng createdAt, không có customerId | Bỏ qua trường giữa; chỉ mục có thể hỗ trợ phần tenant nhưng không bảo đảm quét hẹp theo thời gian |
| tenantId + status | Chưa có status trong chỉ mục; cần cân nhắc index riêng nếu truy vấn phổ biến |

**Điểm khác với DynamoDB:** compound index của MongoDB là cấu trúc chỉ mục trên các trường độc lập; trong khi chuỗi **PK = TENANT#T01#CUSTOMER#C088** của DynamoDB là **một giá trị thuộc tính**. Quy tắc tiền tố các trường của compound index không thể áp trực tiếp cho tiền tố ký tự của DynamoDB partition key.

**Điểm khác với Cassandra:** compound index là đường truy cập phụ; không mặc định quyết định partition logic của toàn bộ collection giống cách Cassandra dùng partition key. Một MongoDB collection có thể còn có shard key riêng khi được sharding; cần xét thêm các quy tắc định tuyến shard nếu dùng cluster phân tán.

## 7. Trường hợp key–value: ghép chuỗi khóa không tự tạo chỉ mục tiền tố

Trong Redis hoặc kho key–value tương tự, ứng dụng có thể đặt tên khóa:

~~~text
tenant:T01:customer:C088:order:O947
tenant:T01:customer:C088:order:O948
tenant:T01:customer:C099:order:O949
~~~

Cách đặt tên này giúp nhìn cấu trúc và tránh xung đột tên. Nhưng thao tác đọc chuẩn theo khóa vẫn cần **toàn bộ tên khóa**.

Ví dụ, trong Redis, **SCAN với MATCH** có thể lặp qua các khóa khớp mẫu:

~~~text
SCAN 0 MATCH tenant:T01:customer:C088:order:* COUNT 100
~~~

Điều này không tương đương một phép truy vấn index prefix được tối ưu theo tenant/customer. Redis SCAN là thao tác lặp có thể cần nhiều lần gọi, chi phí duyệt phụ thuộc tập khóa; COUNT chỉ là gợi ý, và trong lúc dữ liệu thay đổi kết quả lặp có thể bị trùng hoặc bỏ sót trong những tình huống nhất định. Nó không phù hợp để thay truy vấn nghiệp vụ trực tuyến quy mô lớn.

Nếu cần “lấy 20 đơn mới nhất của khách”, có thể tổ chức thêm một **sorted set theo khách** với score là thời gian hoặc lưu mục lục chuyên biệt; ứng dụng phải cập nhật và làm sạch chỉ mục đó theo quy tắc đã thiết kế.

Một số kho key–value có thứ tự từ điển (ordered KV store) thực sự hỗ trợ quét theo khoảng khóa. Khi đó mã hóa khóa thành một chuỗi byte duy trì thứ tự có thể tạo ra prefix range hiệu quả. Cần đọc rõ hợp đồng của sản phẩm: **khả năng duyệt prefix đến từ cấu trúc lưu trữ/chỉ mục**, không chỉ từ việc các key có chung ký tự đầu.

## 8. Mã hóa thành phần thành khóa: làm sao để đúng và có thứ tự?

Khi phải tự tạo khóa chuỗi/byte, mã hóa phải giải quyết cả **tính duy nhất** lẫn **thứ tự**. Một khóa “dễ đọc” chưa chắc an toàn cho truy vấn.

### 8.1. Tránh va chạm do nối chuỗi mơ hồ

Nếu nối trực tiếp:

~~~text
(tenant="AB", customer="C")  -> "ABC"
(tenant="A",  customer="BC") -> "ABC"
~~~

Hai bộ giá trị khác nhau tạo cùng một khóa.

Thêm dấu phân cách nhưng không escape cũng có thể va chạm:

~~~text
("A|B", "C") -> "A|B|C"
("A", "B|C") -> "A|B|C"
~~~

Các cách xử lý gồm:

- Mã hóa chiều dài của từng thành phần: **3:ABC2:DE**.
- Escape dấu phân cách theo quy tắc có thể giải mã ngược.
- Sử dụng bộ mã hóa tuple chính thức của hệ quản trị, nếu có.
- Dùng các cột/thuộc tính khóa riêng biệt khi hệ hỗ trợ.

Mục tiêu là **mỗi bộ giá trị hợp lệ ánh xạ tới đúng một dạng byte khóa** và có thể phân tách trở lại mà không mơ hồ. Chọn quy tắc mã hóa một lần, ghi rõ phiên bản, và dùng đồng nhất cho ghi lẫn đọc.

### 8.2. Thứ tự từ điển của chuỗi khác thứ tự số

Nếu lưu số nguyên dạng chuỗi biến độ dài:

~~~text
"1"
"10"
"100"
"2"
"20"
~~~

Đây là thứ tự từ điển thông thường, không phải thứ tự số học. Với số nguyên không âm và giới hạn miền đã biết, dùng dạng cố định chiều rộng:

~~~text
000001
000002
000010
000020
000100
~~~

Giải pháp này chỉ phù hợp khi chiều rộng bao phủ mọi giá trị. Với số âm, số thực, số rất lớn hoặc binary key, cần encoding có khả năng duy trì thứ tự đúng theo định nghĩa so sánh của kho lưu trữ, không chỉ thêm số 0 tùy tiện.

### 8.3. Dấu thời gian muốn sắp xếp đúng phải chuẩn hóa

Nếu dùng dạng ISO 8601, hãy thống nhất UTC, độ chính xác và độ rộng trường:

~~~text
2026-11-03T09:05:07.000Z
2026-11-14T08:30:00.000Z
2026-12-01T00:00:00.000Z
~~~

Với cùng chuẩn này, thứ tự từ điển tương ứng thứ tự thời gian. Không nên trộn dấu thời gian có offset khác nhau, số chữ số phần giây khác nhau, hoặc định dạng ngày không chuẩn hóa rồi kỳ vọng sắp xếp chuỗi luôn đúng thời gian thực.

Khi nhiều đơn có cùng thời điểm, thêm một thành phần định danh ổn định phía sau thời gian:

~~~text
SK = ORDER#2026-11-14T08:30:00.000Z#O947
~~~

Như vậy, khóa không va chạm do hai đơn cùng timestamp và thứ tự vẫn xác định được. Nếu cần sắp xếp **mới nhất trước**, có thể dùng chiều sắp xếp của clustering/index hoặc khả năng quét ngược; không tự động đảo giá trị thời gian nếu chưa chắc encoding đảo vẫn đúng.

### 8.4. Thống nhất cách chuẩn hóa và version

Các quy tắc cần chốt ngay:

| Vấn đề | Quy tắc cần xác định |
| --- | --- |
| Chữ hoa/chữ thường | tenantId, customerId có phân biệt hoa thường không? |
| Unicode | Có chuẩn hóa Unicode trước khi mã hóa không? |
| Giá trị null | Null được cấm hay mã hóa bằng token riêng? |
| Dấu phân cách | Dấu phân cách được escape bằng cách nào? |
| Timestamp | UTC, độ chính xác cố định, cách xử lý trùng timestamp |
| Kiểu số | Miền số và kiểu encoding bảo toàn thứ tự |
| Phiên bản | Chẳng hạn tiền tố **v1#** để hỗ trợ thay đổi quy ước |
| Độ dài | Giới hạn byte khóa và chi phí lưu index của hệ đang dùng |

Đổi thứ tự thành phần sau khi đã có dữ liệu thường đồng nghĩa **đổi cách truy cập** và phải tính chuyện backfill, dual-read/dual-write trong giai đoạn chuyển đổi, hoặc chỉ mục mới.

## 9. Truy vấn tiền tố trên khóa có thứ tự thực chất hoạt động thế nào?

Giả sử ordered KV store lưu các khóa theo thứ tự byte và cho phép quét khoảng:

~~~text
T01|C088|2026-11-13|O946
T01|C088|2026-11-14|O947
T01|C088|2026-11-15|O948
T01|C099|2026-11-14|O949
T02|C088|2026-11-14|O950
~~~

Với bộ mã hóa bảo toàn thứ tự và tách thành phần rõ ràng, một truy vấn bắt đầu từ tiền tố **T01|C088|** có thể đọc một **dải liên tiếp**:

~~~text
start: "T01|C088|"
stop:  first key strictly beyond prefix "T01|C088|"
~~~

Trong ví dụ ký tự ASCII đơn giản, một prefix range có thể biểu diễn bằng điểm bắt đầu **T01|C088|** và một cận trên được tính bằng **prefix successor**. Cách tính cận trên chính xác phụ thuộc thứ tự byte, encoding và API của kho dữ liệu; không thể mặc định ghép một ký tự bất kỳ để tạo cận trên.

Để lọc tháng 11, có thể dùng một dải thời gian có ranh giới rõ:

~~~text
lower = "T01|C088|2026-11-01"
upper = "T01|C088|2026-12-01"
range = [lower, upper)
~~~

Hình dung các phần khóa:

~~~mermaid
flowchart TD
    A["Tenant"] --> B["Customer trong tenant"]
    B --> C["Thời gian trong customer"]
    C --> D["Order ID tại cùng thời điểm"]
    A -. "lọc tenant" .-> E["Dải rộng"]
    B -. "lọc tenant + customer" .-> F["Dải hẹp hơn"]
    C -. "thêm khoảng thời gian" .-> G["Dải thời gian"]
~~~

Sơ đồ thể hiện **thứ tự sắp xếp logic**. Nó chỉ dẫn tới range scan hiệu quả nếu kho lưu trữ thật sự có cấu trúc khóa có thứ tự và điều kiện truy vấn được hỗ trợ. Trong một hash store, các khóa có cùng tiền tố có thể nằm ở những vị trí hoàn toàn khác nhau.

## 10. Thiết kế khóa theo tập truy vấn thay vì theo cấu trúc đối tượng

Quay lại đơn hàng đa tenant. Lập bảng truy vấn trước khi chốt khóa:

| Truy vấn | Điều kiện và thứ tự | Đường truy cập đề xuất |
| --- | --- | --- |
| Q1. Xem lịch sử đơn của một khách | tenant + customer, mới nhất trước | Khóa theo tenant/customer; thời gian làm sort/clustering |
| Q2. Xem một đơn theo mã | tenant + orderId | Khóa tra cứu trực tiếp hoặc secondary index |
| Q3. Xem các đơn PAID của tenant | tenant + status, mới nhất trước | Secondary index hoặc bản chiếu theo tenant/status/time |
| Q4. Báo cáo doanh thu theo tháng | tenant + thời gian, SUM nhiều đơn | Mô hình đọc theo thời gian, bảng tổng hợp hoặc hệ phân tích |

Không cần ép một khóa phục vụ tối ưu cả bốn truy vấn nếu cách truy cập đối nghịch nhau. Một thiết kế thực tế có thể chọn:

~~~text
Base access:
  tenantId, customerId -> createdAt DESC, orderId

Lookup by order:
  tenantId, orderId -> order record

Read by status:
  tenantId, status -> createdAt DESC, orderId
~~~

Tùy sản phẩm, đây có thể là primary key cùng secondary indexes, bảng vật lý theo truy vấn, hoặc projection qua sự kiện. Nếu có dữ liệu sao chép, hãy xác định nguồn sự thật và cách sửa sai lệch.

### 10.1. Chi phí của đường truy cập bổ sung

Một chỉ mục phụ hoặc bản chiếu mới có thể đem lại tốc độ đọc, nhưng kéo theo:

- Dung lượng và chi phí ghi mỗi khi đơn được tạo hoặc cập nhật.
- Cập nhật nhiều nơi khi **status** thay đổi.
- Khả năng đọc chưa thấy dữ liệu mới ngay nếu bản chiếu được cập nhật bất đồng bộ.
- Backfill khi thêm index vào dữ liệu đã có.
- Giám sát độ trễ, thao tác chạy lại và phát hiện bản chiếu lỗi.

Cần cân nhắc tần suất mỗi truy vấn, độ trễ yêu cầu, dung lượng, tỷ lệ đọc/ghi và chi phí vận hành trước khi tạo thêm index.

### 10.2. Tránh partition quá lớn hoặc quá nóng

Khóa **tenantId** đơn độc có thể tạo partition rất lớn khi một tenant có hàng triệu đơn hoặc lưu lượng ghi vượt trội. Khóa **(tenantId, customerId)** phân nhỏ hơn, nhưng một khách đặc biệt hoạt động mạnh vẫn có thể là điểm nóng.

Một hướng là thêm **bucket thời gian** hoặc **bucket phân phối tải**:

~~~text
PK = TENANT#T01#CUSTOMER#C088#MONTH#2026-11
SK = ORDER#2026-11-14T08:30:00Z#O947
~~~

Ưu điểm là giới hạn dữ liệu theo một khoảng rõ ràng. Đổi lại, muốn xem lịch sử 12 tháng phải truy vấn nhiều partition; cần ghép kết quả, xử lý phân trang và bảo đảm sắp xếp toàn cục. Nếu thêm bucket ngẫu nhiên, truy vấn theo customer có thể phải fan-out qua nhiều bucket.

**Thẻ phân vùng càng đa dạng không có nghĩa truy vấn càng nhanh:** cần cân bằng giữa phân phối tải và số partition phải chạm tới cho một thao tác đọc.

## 11. Các lỗi phổ biến

### Lỗi 1: Lấy một tên khóa có tiền tố rồi tưởng truy vấn được cả nhóm

Ví dụ **tenant:T01:customer:C088:order:O947** là một key nguyên vẹn trong Redis. Đặt tên có cấu trúc hữu ích, nhưng lệnh GET theo **tenant:T01** không thể trả toàn bộ đơn hàng có cùng tiền tố. Cần chỉ mục/mô hình dữ liệu khác.

### Lỗi 2: Gộp tất cả thành phần vào partition key có băm

Nếu dùng **hash(tenantId, customerId, createdAt, orderId)**, các đơn của cùng khách có thể bị phân phối không theo thời gian. Đây là lợi ích cho tính phân tán, nhưng làm mất tính liên tiếp cần cho truy vấn lịch sử nếu không có sort key/index bổ trợ.

### Lỗi 3: Đặt thành phần có độ biến thiên cao lên đầu chỉ vì “selective”

Trường **orderId** rất chọn lọc, nhưng đặt đầu chỉ mục phục vụ lịch sử đơn theo khách có thể cản trở truy vấn **tenant + customer**. Độ chọn lọc quan trọng, song phải xét cả dạng điều kiện, thứ tự sắp xếp và khả năng sử dụng tiền tố.

### Lỗi 4: Đặt range trước các trường vẫn cần lọc bằng nhau

Với một chỉ mục đã sắp **(tenantId, createdAt, customerId)**, truy vấn “mọi đơn của C088 trong tháng 11” có thể phải duyệt nhiều khách trong khoảng thời gian rồi kiểm tra customerId. Nếu truy vấn theo một khách phổ biến hơn, thứ tự **(tenantId, customerId, createdAt)** có thể thuận tiện hơn.

### Lỗi 5: Nhầm tính duy nhất của khóa với tính nhất quán của nghiệp vụ

Khóa **(tenantId, orderId)** giúp ngăn định danh trùng tại phạm vi được bảo đảm, nhưng không tự bảo đảm “không bán quá tồn kho”, “không thanh toán hai lần” hay “trạng thái đơn và tồn kho luôn cập nhật cùng lúc”. Các bất biến đó cần giao dịch, điều kiện ghi, idempotency hoặc quy trình nhất quán được thiết kế riêng.

### Lỗi 6: Quên thứ tự và định dạng dữ liệu ở mức byte

Một khóa ngày tháng dùng định dạng **DD/MM/YYYY**, timestamp trộn timezone hoặc số thứ tự không padding có thể khiến sắp xếp từ điển khác ý định. Mọi nơi tạo khóa phải tuân cùng encoding.

### Lỗi 7: Tin rằng mọi truy vấn thỏa tiền tố đều có chi phí nhỏ

Ngay cả khi truy vấn hợp lệ, tiền tố **tenantId** có thể bao gồm hàng triệu bản ghi. Dùng **limit**, **pagination**, khoảng thời gian phù hợp và chỉ mục đủ hẹp. Nên đo số bản ghi đọc và độ trễ p95/p99, không chỉ kiểm tra truy vấn chạy được.

## 12. Quy trình chọn khóa ghép cho một mô hình mới

**Bước 1 — Liệt kê truy vấn phải hỗ trợ.** Viết từng truy vấn với điều kiện bằng nhau, điều kiện khoảng, thứ tự, giới hạn kết quả và tần suất thực tế.

**Bước 2 — Xác định khóa định danh.** Các trường nào bảo đảm không trùng? Có multi-tenant không? Tính duy nhất áp dụng trong phạm vi nào?

**Bước 3 — Chọn mô hình truy cập chính.** Với DynamoDB, phân định PK và SK; với Cassandra, xác định partition key và clustering columns; với MongoDB, xác định thứ tự trường trong compound index; với ordered KV, xác định encoding và range.

**Bước 4 — Kiểm tra tiền tố theo đúng cơ chế.** Đánh dấu điều kiện nào trùng tiền tố trái nhất, điều kiện nào cần đủ partition key, điều kiện nào là range trên sort/clustering field, điều kiện nào bắt buộc qua index khác.

**Bước 5 — Xem điểm nóng và kích thước partition.** Thử với tenant/khách hàng đông nhất, không chỉ giá trị trung bình. Đánh giá bucket nếu cần và tính tác động tới truy vấn liên thời gian.

**Bước 6 — Chốt encoding và vòng đời thay đổi.** Chuẩn hóa timestamp, số, Unicode, phân cách, phiên bản và cách di chuyển dữ liệu khi đổi khóa.

**Bước 7 — Đo với dữ liệu đại diện.** Kiểm tra kế hoạch truy vấn, số bản ghi đọc, write amplification, độ trễ và chi phí index. Một mô hình đúng trên giấy vẫn có thể không đạt yêu cầu khi skew dữ liệu cao.

## 13. Bài tập thực hành

### Bài 1: Chỉ mục nhiều trường

Một document database có compound index **(tenantId, departmentId, createdAt DESC, employeeId)**. Hãy xác định truy vấn nào thuận lợi theo tiền tố:

1. Lấy mọi hồ sơ của tenant T01.
2. Lấy hồ sơ của phòng D02 thuộc tenant T01, mới nhất trước.
3. Tìm mọi hồ sơ của nhân viên E03 mà không biết tenant.
4. Lấy hồ sơ trong khoảng ngày của tenant T01, nhưng không biết department.

**Gợi ý đáp án:** (1) dùng tiền tố đầu; (2) dùng hai thành phần đầu rồi thứ tự createdAt; (3) thiếu các thành phần đầu; (4) có tenant nhưng bỏ qua department nên không có dải hẹp đơn giản theo ngày. Đây là định hướng cho compound index theo thứ tự; vẫn phải xem kế hoạch thực thi.

### Bài 2: Chọn khóa cho truy vấn thời gian

Ứng dụng giám sát có truy vấn chủ đạo: “Lấy 100 sự kiện mới nhất của thiết bị X trong một tenant”. Có các phương án:

~~~text
A. (eventId, tenantId, deviceId, timestamp)
B. (tenantId, deviceId, timestamp DESC, eventId)
C. (tenantId, timestamp DESC, deviceId, eventId)
~~~

Nếu dùng một chỉ mục ghép có thứ tự, **B** thường phù hợp nhất cho truy vấn đã mô tả: biết tenant và thiết bị trước, sau đó đọc thời gian mới nhất. **A** phù hợp hơn với tìm theo eventId; **C** có thể hợp cho luồng sự kiện toàn tenant nhưng kém thuận lợi khi cần chỉ một thiết bị.

### Bài 3: Chuyển sang hệ key–value

Bạn lưu khóa **order:T01:C088:2026-11-14:O947** trong một hệ chỉ hỗ trợ đọc chính xác theo khóa. Yêu cầu mới: “Lấy tất cả đơn của C088 trong tháng 11”.

**Đáp án định hướng:** Không thể suy ra có truy vấn tiền tố hiệu quả chỉ vì tên khóa dùng dấu hai chấm. Hãy thiết kế danh sách chỉ mục theo tenant/customer/tháng, sorted set theo thời gian, secondary index, hoặc chuyển workload sang kho có khả năng range scan phù hợp. Cần thiết kế cả cơ chế cập nhật chỉ mục khi đơn bị sửa/xóa.

### Bài 4: Đổi thứ tự thành phần

Hệ thống đang có chỉ mục **(tenantId, customerId, createdAt)**. Một màn hình mới yêu cầu “20 đơn mới nhất của toàn tenant, bất kể khách nào”. Hãy giải thích vì sao chỉ mục cũ có thể chưa đủ và đề xuất phương án.

**Đáp án định hướng:** Các đơn đang được nhóm theo customer trước khi xét thời gian; đọc đầu mỗi nhóm rồi ghép và sắp xếp không giống quét một đoạn liên tục toàn tenant. Có thể cần chỉ mục/bản chiếu **(tenantId, createdAt DESC, orderId)**, tùy khả năng của hệ quản trị, với chi phí ghi và đồng bộ bổ sung.

## 14. Tổng kết

Điều cốt lõi khi làm việc với **khóa ghép** là phân biệt ba câu hỏi: **khóa nào định danh bản ghi**, **thành phần nào quyết định partition**, và **thứ tự nào cho phép tìm theo tiền tố hoặc khoảng**. Trong một chỉ mục ghép có thứ tự, các trường đầu thường quyết định phạm vi tìm; bỏ qua một trường ở giữa có thể làm mất lợi thế của dải khóa liên tiếp.

Tuy nhiên, **quy tắc tiền tố chỉ đúng trong phạm vi cấu trúc dữ liệu và API của từng hệ**. DynamoDB đòi hỏi đủ giá trị partition key khi Query và có thể dùng điều kiện tiền tố trên sort key; Cassandra yêu cầu tuân mô hình partition/clustering; MongoDB dùng tiền tố trường của compound index; còn một chuỗi khóa Redis tự ghép không trở thành chỉ mục tiền tố. Hãy thiết kế từ truy vấn thực, mã hóa khóa không mơ hồ, kiểm tra điểm nóng và đo hiệu năng trên dữ liệu đại diện.
