# Đường truy cập chính và vai trò của khóa lưu trữ

Một truy vấn NoSQL không chỉ được quyết định bởi **điều kiện lọc**. Hiệu quả của nó phụ thuộc rất lớn vào việc dữ liệu được **định vị bằng khóa nào**, được **đặt cùng phạm vi lưu trữ với những bản ghi nào** và có **thứ tự ra sao** trong phạm vi đó.

Giả sử ứng dụng cần hiển thị **20 đơn hàng gần nhất của một khách hàng**. Nếu dữ liệu được tổ chức theo khóa khách hàng và thứ tự thời gian, hệ thống có thể đi đến đúng nhóm đơn và lấy một dải ngắn. Nếu dữ liệu chỉ được định vị theo mã đơn hàng, câu hỏi “của khách X, mới nhất trước” có thể buộc hệ thống tìm qua rất nhiều đơn, dùng chỉ mục phụ hoặc duy trì thêm một bản dữ liệu phục vụ riêng truy vấn này.

Vì thế, khi thiết kế NoSQL, phải xác định **đường truy cập chính (primary access path)** trước khi nghĩ đến những chỉ mục bổ sung. Đường truy cập chính là cách ứng dụng **đi thẳng đến một bản ghi, một nhóm bản ghi hoặc một dải bản ghi** thông qua khóa và tổ chức dữ liệu mà hệ thống hỗ trợ hiệu quả nhất.

Bài học tập trung vào vai trò của **khóa lưu trữ**, phân biệt nó với **khóa định danh nghiệp vụ**, **partition key**, **sort/clustering key**, **chỉ mục chính** và **chỉ mục phụ**. Ví dụ triển khai dùng DynamoDB, Cassandra, MongoDB, Redis và Bigtable để đối chiếu. Mỗi hệ có ngữ nghĩa riêng: không nên hiểu mọi từ “primary key” hay “index” là cùng một cơ chế vật lý.

## 1. Từ câu hỏi nghiệp vụ đến đường đọc dữ liệu

Xét dịch vụ bán hàng có các truy vấn:

1. **GET /orders/{orderId}**: lấy chi tiết một đơn theo mã đơn.
2. **GET /customers/{customerId}/orders?limit=20**: lấy 20 đơn mới nhất của một khách.
3. **GET /orders?status=PAID&from=...&to=...**: lấy các đơn đã thanh toán trong khoảng thời gian.
4. **GET /orders?sku=BOOK-01**: tìm đơn có chứa một sản phẩm.
5. **PATCH /orders/{orderId}**: đổi trạng thái một đơn nếu nó đang ở trạng thái cho phép.

Các yêu cầu đều đọc hoặc ghi trên thực thể **order**, nhưng **không cùng một đường truy cập**.

| Truy vấn | Khóa/điều kiện đã biết | Cần trả về | Đường truy cập ứng viên |
|---|---|---|---|
| Chi tiết đơn | orderId | Một bản ghi | Tra cứu theo định danh duy nhất |
| Đơn gần nhất của khách | customerId | Dải có thứ tự thời gian | Nhóm theo khách và sắp theo thời gian |
| Đơn PAID theo thời gian | status, time range, tenant | Dải qua nhiều khách | Chỉ mục/bảng theo trạng thái và thời gian |
| Đơn chứa SKU | sku, tenant | Nhiều đơn | Chỉ mục multikey/read model theo SKU |
| Chuyển trạng thái | orderId, trạng thái mong đợi | Cập nhật đúng một đơn | Tra theo khóa định danh và ghi có điều kiện |

Không có lý do để mặc định một khóa duy nhất sẽ phục vụ tối ưu cả năm truy vấn. Ta cần **chọn một hoặc vài đường truy cập quan trọng**, rồi đánh giá chi phí hỗ trợ các đường còn lại bằng chỉ mục phụ, bản sao dẫn xuất hoặc một kho phân tích.

### Hình dung công việc tìm dữ liệu

~~~mermaid
flowchart TD
    A["Request có điều kiện truy vấn"] --> B{"Biết khóa truy cập chính?"}
    B -->|Có| C["Định vị key/partition/range"]
    C --> D["Đọc phần dữ liệu phù hợp"]
    B -->|Không| E{"Có index phụ đúng điều kiện?"}
    E -->|Có| F["Tìm key qua index phụ"]
    F --> D
    E -->|Không| G["Scan rộng hoặc dùng read model khác"]
    D --> H["Lọc bổ sung, sắp xếp/phân trang nếu cần"]
    G --> H
    H --> I["Kết quả cho ứng dụng"]
~~~

Sơ đồ là cách suy luận, không đại diện chính xác cho mọi query planner. Ví dụ MongoDB có nhiều loại index và optimizer lựa chọn kế hoạch; Redis GET làm việc trực tiếp theo key; DynamoDB Query định vị theo partition key; Cassandra cần điều kiện phù hợp primary key để truy cập partition hiệu quả.

## 2. “Khóa” trong NoSQL có thể mang nhiều nghĩa

Những thuật ngữ dễ bị trộn lẫn:

| Thuật ngữ | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Business key / logical ID** | Nghiệp vụ nhận diện thực thể bằng gì? | orderId = web-1001 |
| **Primary key** | Engine coi tổ hợp thuộc tính nào là định danh duy nhất của item/row? | (tenantId, orderId) |
| **Storage key / row key** | Engine dùng khóa nào để định vị và tổ chức đơn vị lưu trữ? | Redis key, Bigtable row key |
| **Partition key** | Khóa nào xác định phạm vi phân vùng/định tuyến? | tenantId + deviceId + day |
| **Sort key / clustering key** | Trong một partition/nhóm, bản ghi được xác định hoặc sắp như thế nào? | createdAt + orderId |
| **Shard key** | Khóa nào quyết định phân bố document giữa các shard? | MongoDB shard key |
| **Primary index** | Chỉ mục gắn với truy cập chính/định danh theo ngữ nghĩa engine | MongoDB _id index, Couchbase key-based access |
| **Secondary index** | Truy cập thêm bằng thuộc tính khác khóa chính | GSI DynamoDB, index MongoDB |

Không nên dùng các khái niệm này thay thế cho nhau:

- **_id** của MongoDB là định danh document và được index, nhưng **không tự là shard key** của mọi sharded collection.
- **Partition key** DynamoDB được dùng để tính toán phân bố item; nếu table có **sort key**, chính **partition key + sort key** tạo định danh đầy đủ của item.
- Trong Cassandra, **PRIMARY KEY ((partition_key), clustering_key)** chỉ ra cả **định tuyến partition** lẫn **định danh/sắp xếp row**.
- Trong Redis, một **key** xác định một value có kiểu dữ liệu riêng; thao tác GET/HGETALL theo key không giống Query nhiều hàng theo clustering key.
- Trong Bigtable, **row key** là chuỗi byte ảnh hưởng mạnh đến truy cập theo khoảng khóa và phân bố tải.

**Tên trường không đủ để khẳng định khả năng truy vấn.** Đặt tên một thuộc tính là **customerId** không có nghĩa database tự biết nơi chứa tất cả đơn của khách và trả chúng theo thời gian.

## 3. Ba hình thức truy cập phổ biến

### 3.1. Point lookup: một key → một bản ghi/value

~~~text
Input: orderId = "order-1001"

Storage:
  order:order-1001 -> {customerId, items, status, totalMinor}
~~~

Ứng dụng biết **đủ khóa**, engine có thể định vị bản ghi trực tiếp qua cấu trúc tra cứu phù hợp. Đây là dạng truy cập rất thuận tiện trong key–value database và các API **GetItem**, **GET** hoặc **find by primary key**.

### 3.2. Range/query within partition: một nhóm → một dải có thứ tự

~~~text
Khóa nhóm: customer-07
Thứ tự:    createdAt DESC, orderId DESC

customer-07:
  2026-11-14 10:00  order-1004
  2026-11-14 09:00  order-1001
  2026-11-12 13:30  order-0930
~~~

Nếu engine hỗ trợ sort/clustering key, truy vấn có thể lấy **20 hàng đầu** trong nhóm theo thứ tự lưu hoặc index, thay vì đọc toàn bộ lịch sử rồi sort ở ứng dụng.

### 3.3. Scan/filter: tìm trong nhiều nhóm chưa biết khóa

~~~text
Input: status = "PAID"
Nhưng data được nhóm theo customerId.

Không có status access path:
  đọc nhiều khách/partition -> kiểm tra status -> chọn kết quả
~~~

Điều kiện filter có thể giảm **kết quả trả về** nhưng không nhất thiết giảm lượng dữ liệu phải **đọc từ storage**. Một query trả 20 dòng vẫn có thể tốn nhiều I/O nếu phải xét hàng triệu dòng trước khi tìm đủ 20 dòng phù hợp.

**Đường truy cập hiệu quả là đường giúp tránh đọc phần dữ liệu không liên quan ngay từ đầu**, chứ không chỉ trả về một response nhỏ.

## 4. Một khóa lưu trữ tốt cần phục vụ thao tác nào?

Trước khi chọn khóa, hãy ghi access pattern thành một hợp đồng:

~~~yaml
# Ví dụ hợp đồng truy vấn, không phải cấu hình database
name: latestOrdersByCustomer
tenantId: shop-a
customerId: customer-07
filters:
  createdAt:
    fromInclusive: "2026-11-01T00:00:00Z"
    toExclusive: "2026-12-01T00:00:00Z"
sort:
  - createdAt: DESC
  - orderId: DESC
limit: 20
cursor: "lastSeenCreatedAt+lastSeenOrderId"
consistency: "theo hợp đồng của hệ và nghiệp vụ"
~~~

Các câu hỏi cần làm rõ:

1. Request **luôn biết** tenantId và customerId hay đôi khi chỉ biết orderId?
2. Cần **một item**, **cả partition**, hay **một dải thời gian**?
3. Mức tải là vài request/phút hay hàng nghìn request/giây?
4. Kết quả cần **sort** theo thời gian hay theo giá/điểm?
5. Có cần **cursor pagination** ổn định khi dữ liệu mới liên tục được chèn?
6. Một customer có tối đa bao nhiêu order? Có thể tăng nhiều năm không?
7. Những thuộc tính nào cần **cập nhật độc lập**?
8. Có yêu cầu **đọc ngược** như tất cả đơn theo trạng thái hoặc SKU không?

Khóa lưu trữ được chọn từ **thao tác thực tế**, không chỉ từ sơ đồ thực thể **Customer 1:N Order**.

## 5. Redis: đường truy cập chính là key cụ thể

Redis minh họa rõ nhất point lookup theo key:

~~~redis
SET order:shop-a:order-1001 "{\"status\":\"PENDING\",\"totalMinor\":240000}"
GET order:shop-a:order-1001
EXISTS order:shop-a:order-1001
DEL order:shop-a:order-1001
~~~

Trong ví dụ:

- **order:shop-a:order-1001** là key ứng dụng tự đặt theo quy ước.
- **GET** định vị đúng value của key đó.
- Redis không tự hiểu **shop-a** là tenant hay **order-1001** là orderId; ý nghĩa nằm trong hợp đồng đặt tên key.
- Các dấu **:** tạo namespace dễ đọc, **không tạo cây thư mục hoặc index theo prefix** mặc định.

Khi ứng dụng chỉ biết customerId và muốn **20 order mới nhất**, không thể chỉ dùng **GET customer-07** để tự tìm toàn bộ order có chứa trường customerId. Cần thiết kế thêm đường truy cập, ví dụ Sorted Set chứa ID theo score thời gian:

~~~redis
ZADD customer:shop-a:customer-07:orders 1794646800 "order-1001"
ZADD customer:shop-a:customer-07:orders 1794647100 "order-1004"
ZREVRANGE customer:shop-a:customer-07:orders 0 19
~~~

**Score** chỉ minh họa mốc thời gian Unix seconds; cần bảo đảm score thực sự khớp **createdAt** của dữ liệu. Nếu nhiều order cùng score, thứ tự giữa chúng được quyết định bởi ngữ nghĩa Sorted Set, **không** mặc nhiên theo orderId nghiệp vụ hay thời gian nano giây. Nếu cần tie-breaker ổn định, hãy thiết kế thêm thứ tự/ID và quy tắc phân trang phù hợp.

Đường đọc:

~~~text
customer:shop-a:customer-07:orders
           |
           v
  [order-1004, order-1001, ...]
           |
           v
  GET/MGET các order keys tương ứng
~~~

Đường ghi mới phải cập nhật **order value** và **Sorted Set chỉ mục**. Nếu một bước thành công và bước kia thất bại, các đường đọc có thể lệch. Redis transaction/script, cách đồng bộ bất đồng bộ hoặc đối soát phải được chọn theo yêu cầu; đặc biệt Redis Cluster có giới hạn khi thao tác nhiều key ở những hash slot khác nhau.

**Vai trò của key ở Redis:** xác định **điểm truy cập trực tiếp**. Để có nhiều đường truy cập, ứng dụng có thể phải quản lý **các key/index dẫn xuất** bổ sung.

## 6. MongoDB: _id lookup mạnh, nhưng truy vấn khác cần index phù hợp

MongoDB lưu document trong collection và mặc định có index duy nhất trên **_id**. Ví dụ:

~~~javascript
db.orders.insertOne({
  _id: "order-1001",
  tenantId: "shop-a",
  customerId: "customer-07",
  status: "PENDING",
  totalMinor: NumberLong("240000"),
  createdAt: ISODate("2026-11-14T09:00:00Z")
});
~~~

Tra theo _id:

~~~javascript
db.orders.findOne({ _id: "order-1001" });
~~~

Đây là **đường truy cập theo định danh** được hỗ trợ bởi _id index. Nhưng để lấy đơn của một khách:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  customerId: "customer-07"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Chỉ có _id index **chưa đủ** để khẳng định truy vấn này sẽ hiệu quả. Có thể tạo một compound index phục vụ lọc và sort:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "by_customer_recent" }
);
~~~

Index này là một **đường truy cập bổ sung**: filter theo tenantId/customerId, rồi duyệt keys được sắp theo createdAt/_id. Nó không thay đổi _id là định danh document.

### Vì sao thứ tự field trong compound index quan trọng?

Với truy vấn trên, thứ tự ứng viên:

~~~text
tenantId = ?
customerId = ?
createdAt DESC
_id DESC
~~~

Hai field đầu là **điều kiện equality**, sau đó là **thứ tự** cần duyệt. Nếu chỉ mục là **(createdAt, customerId)**, engine có thể phải duyệt rất nhiều order mới của những khách khác rồi mới lọc customerId. Một compound index được đặt đúng theo **filter và sort thực tế** thường giảm việc đọc không cần thiết.

Tuy nhiên, không có quy tắc máy móc “field cardinality cao nhất luôn phải đứng đầu” hoặc “mọi filter đều phải được index”. Cần xét điều kiện equality/range, sort, tính chọn lọc, chi phí ghi và query plan.

### Kiểm tra đường thực sự được dùng

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  customerId: "customer-07"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Cần xem **winningPlan**, **nReturned**, **totalKeysExamined**, **totalDocsExamined**, các bước **IXSCAN/COLLSCAN/SORT** và thời gian thực thi. Nếu truy vấn trả 20 document nhưng phải duyệt hàng triệu document, việc chỉ nhìn số dòng kết quả sẽ che giấu vấn đề.

Một index có thể không được chọn nếu optimizer ước lượng một kế hoạch khác phù hợp hơn; và **index không biến mọi truy vấn thành index-only/covered query**, đặc biệt khi cần đọc field không có trong index.

## 7. MongoDB: khóa định danh và shard key là hai quyết định khác nhau

Với MongoDB sharded collection, **shard key** ảnh hưởng việc phân bố document và định tuyến truy vấn giữa các shard. Nó không tự đồng nghĩa với trường **_id**.

Ví dụ:

~~~text
Document _id:
  order-1001

Shard key ứng viên:
  tenantId + customerId
~~~

Nếu một truy vấn chứa shard key phù hợp, router có thể nhắm tới tập shard liên quan thay vì phải gửi yêu cầu rộng. Nếu truy vấn chỉ có **_id** nhưng shard key là thuộc tính khác và không có cách định tuyến tương ứng, tìm theo _id có thể không được target tới một shard duy nhất.

Ngược lại, nếu chỉ chọn shard key theo **tenantId**, một tenant cực lớn có thể gây mất cân bằng hoặc tạo tải tập trung tùy cách phân vùng/chunks và workload.

Khi thiết kế sharding:

- Phân biệt **index phục vụ filter/sort** và **shard key phục vụ phân bố/định tuyến**.
- Đo mức phân bố của các giá trị khóa, không chỉ đếm số giá trị duy nhất.
- Xem đường truy vấn **có mang shard key** hay không.
- Xem hot writes, monotonic keys, chunks và độ cân bằng giữa shard.
- Kiểm tra giới hạn cụ thể của phiên bản MongoDB về unique index, shard key, update và routing.

**Không nên nói “có index trên customerId là truy vấn đã được shard routing tối ưu”.** Index và shard routing giải quyết hai vấn đề liên quan nhưng khác nhau.

## 8. DynamoDB: partition key và sort key tạo đường Query tự nhiên

Trong DynamoDB, một table có thể dùng:

~~~text
PK (partition key)
SK (sort key)
~~~

Mỗi item được định danh bằng **(PK, SK)**. Các item có cùng PK tạo một **item collection logic** theo sort key; hệ thống quản lý phân bố vật lý bên dưới theo cơ chế riêng.

Giả sử thiết kế đường đọc **“20 order gần nhất của một khách”**:

~~~text
PK = "TENANT#shop-a#CUSTOMER#customer-07"
SK = "ORDER#2026-11-14T09:00:00.000Z#order-1001"
~~~

Những item cùng customer có thể là:

~~~text
PK                                       SK
TENANT#shop-a#CUSTOMER#customer-07      ORDER#2026-11-14T10:00:00.000Z#order-1004
TENANT#shop-a#CUSTOMER#customer-07      ORDER#2026-11-14T09:00:00.000Z#order-1001
TENANT#shop-a#CUSTOMER#customer-07      ORDER#2026-11-12T13:30:00.000Z#order-0930
~~~

Một Query có thể:

- Chọn đúng **PK**.
- Giới hạn SK theo **begins_with** hoặc một khoảng phù hợp.
- Duyệt theo chiều tăng/giảm của SK bằng **ScanIndexForward**.
- Dùng **Limit** và **LastEvaluatedKey** để phân trang.

Ví dụ dạng tham số API, không phải mã SDK hoàn chỉnh:

~~~json
{
  "TableName": "OrdersByCustomer",
  "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
  "ExpressionAttributeValues": {
    ":pk": {"S": "TENANT#shop-a#CUSTOMER#customer-07"},
    ":prefix": {"S": "ORDER#"}
  },
  "ScanIndexForward": false,
  "Limit": 20
}
~~~

Nếu SK là chuỗi thời gian **UTC ISO 8601 có định dạng, độ dài và độ chính xác nhất quán**, thứ tự từ điển của phần thời gian có thể khớp thứ tự thời gian. Nếu lẫn timestamp có offset khác, không zero-pad hoặc độ chính xác không nhất quán, việc sort theo chuỗi có thể không đúng ý định. Thêm **orderId** ở cuối giúp phân biệt hai order có cùng timestamp.

### Vì sao Query khác FilterExpression?

Trong DynamoDB:

~~~text
KeyConditionExpression
  -> xác định partition key và điều kiện sort key

FilterExpression
  -> lọc các item đã được đọc bởi Query/Scan
~~~

Ví dụ Query theo PK customer rồi thêm filter **status = PAID** vẫn có thể phải đọc nhiều item PENDING/CANCELLED. **FilterExpression không biến status thành partition/sort key**, và không giảm lượng dữ liệu đã được đọc trước bước filter theo cách một đường khóa phù hợp có thể làm.

Đặc biệt, **Limit** là giới hạn số item được đánh giá ở một lần Query trước bước FilterExpression; nó không bảo đảm trả đủ 20 item cuối cùng sau filter. Một page có thể trả ít hơn 20 item hoặc rỗng dù còn page sau. Ứng dụng phải xử lý **LastEvaluatedKey** khi cần thu đủ số kết quả.

### Lấy chi tiết order theo orderId thì sao?

Với PK theo customer và SK chứa thời gian, nếu API **chỉ có orderId**, chưa biết customerId và timestamp, nó không có đủ khóa để **GetItem** trực tiếp theo thiết kế trên.

Các lựa chọn:

1. API hoặc token có cả **customerId + createdAt + orderId**, cho phép xác định PK/SK.
2. Duy trì một **lookup item** theo orderId để tra ra PK/SK.
3. Dùng một **GSI** nếu orderId là thuộc tính được index phù hợp.
4. Chọn một table thiết kế khác nếu **get by orderId** là đường truy cập quan trọng nhất.

Mỗi lựa chọn có chi phí thêm và quy tắc nhất quán. **Tối ưu đường truy cập theo khách không tự động tối ưu truy cập theo mã đơn độc lập.**

## 9. DynamoDB: cách sắp sort key quyết định query theo range

Giả sử SK là:

~~~text
ORDER#2026-11-14T09:00:00.000Z#order-1001
ORDER#2026-11-14T10:00:00.000Z#order-1004
~~~

Câu hỏi **“orders từ ngày 10 đến trước ngày 15”** cần các mốc có cùng quy tắc mã hóa. Có thể dùng khoảng trên SK:

~~~text
SK >= "ORDER#2026-11-10T00:00:00.000Z"
SK <  "ORDER#2026-11-15T00:00:00.000Z"
~~~

Đây là biểu diễn logic của khoảng **[start, end)**. DynamoDB **KeyConditionExpression** hỗ trợ những dạng điều kiện như so sánh range trên sort key hoặc **BETWEEN**; khi hiện thực hóa, cần dùng cú pháp đúng và tránh điều kiện không được hỗ trợ. Với **BETWEEN**, hai đầu đều được bao gồm, nên phải đặc biệt chú ý ranh giới kết thúc.

Nếu key sử dụng **ORDER#<ISO timestamp>#<ID>**, truy vấn dùng **prefix ORDER#** rồi lấy các item mới nhất rất thuận tiện. Nhưng nếu cần lọc **status = PAID**, status không nằm ở đoạn key đó. Có thể cân nhắc:

~~~text
GSI1PK = TENANT#shop-a#STATUS#PAID
GSI1SK = 2026-11-14T09:00:00.000Z#order-1001
~~~

GSI tạo **đường truy cập khác** theo trạng thái. Đổi lại là index storage, write amplification và cơ chế đồng bộ index. DynamoDB GSI có đặc điểm đọc nhất quán sau cùng theo ngữ nghĩa sản phẩm; không nên dùng GSI eventual làm nguồn duy nhất để bảo vệ một bất biến ghi cứng.

## 10. Cassandra: partition key định tuyến, clustering key tổ chức dải

Trong Cassandra, primary key của bảng có thể có cấu trúc:

~~~sql
PRIMARY KEY ((tenant_id, device_id, bucket_day), event_time, event_id)
~~~

Phần trong **hai lớp ngoặc** là **composite partition key**. Các cột sau là **clustering columns**.

Xét hệ thống đo sự kiện của thiết bị:

~~~sql
CREATE TABLE events_by_device_day (
    tenant_id text,
    device_id text,
    bucket_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

Một partition logic được xác định bởi **tenant + device + day**. Trong partition, các row được định danh thêm bởi **event_time + event_id**, với thứ tự clustering hướng về sự kiện mới nhất.

~~~text
Partition ("shop-a", "sensor-01", 2026-11-14)
    |
    +-- 10:05:00, event-id-4
    +-- 10:04:30, event-id-3
    +-- 10:03:00, event-id-2
    +-- 10:01:00, event-id-1
~~~

Truy vấn tự nhiên:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM events_by_device_day
WHERE tenant_id = 'shop-a'
  AND device_id = 'sensor-01'
  AND bucket_day = '2026-11-14'
LIMIT 100;
~~~

Với đủ partition key, truy vấn định vị đúng partition; vì clustering mới nhất trước, nó có thể đọc các row đầu phù hợp thay vì quét toàn bộ thiết bị nhiều năm.

Truy vấn theo dải:

~~~sql
SELECT event_time, event_id, event_type
FROM events_by_device_day
WHERE tenant_id = 'shop-a'
  AND device_id = 'sensor-01'
  AND bucket_day = '2026-11-14'
  AND event_time >= '2026-11-14T09:00:00Z'
  AND event_time < '2026-11-14T10:00:00Z';
~~~

Trong CQL, điều kiện trên clustering key có giới hạn về thứ tự và các dạng quan hệ được phép. Ví dụ trên chỉ range trên **clustering column đầu tiên**, sau khi xác định đầy đủ partition key; không đồng nghĩa mọi tổ hợp filter trên cột bất kỳ đều được chấp nhận hiệu quả.

### Những truy vấn không được khóa chính này phục vụ tự nhiên

~~~text
Lấy mọi event_type = "ERROR" của tất cả device trong tenant.

Khóa table hiện có:
  partition = tenant + device + day

Input lại chỉ biết:
  tenant + event_type + time range
~~~

Không có **deviceId**, hệ thống không định vị được một partition đơn lẻ. Một giải pháp ứng viên là **bảng truy cập riêng** theo:

~~~text
events_by_tenant_type_day:
  partition = tenant + event_type + day (+ bucket phụ nếu cần)
  clustering = event_time + eventId
~~~

Nhưng đây là một bản sao dữ liệu phục vụ truy vấn khác. Cần xác định nguồn chính, cách ghi hai bảng, idempotency, độ mới và đối soát nếu việc cập nhật không cùng một transaction đủ mạnh.

**Vai trò của primary key Cassandra:** không chỉ chống trùng; nó định nghĩa **partition nào chứa row** và **row nào nằm cạnh nhau theo clustering order**.

## 11. Chọn bucket để tránh partition quá lớn

Giả sử thiết bị ghi **10 sự kiện/giây**:

\[
10 \times 60 \times 60 \times 24 = 864\,000
\]

Nếu một partition chứa dữ liệu của thiết bị theo **ngày**, nó có thể nhận **864.000 sự kiện/ngày** trước khi xét lỗi ghi/trùng và chính sách retention.

Nếu partition theo **giờ**:

\[
10 \times 60 \times 60 = 36\,000
\]

mỗi partition chứa khoảng **36.000 sự kiện/giờ**.

| Cách phân bucket | Lợi thế | Đánh đổi |
|---|---|---|
| Theo thiết bị, không bucket | Query lịch sử theo một khóa đơn giản | Partition tăng không giới hạn |
| Theo thiết bị + ngày | Giảm kích thước partition; thường hợp cho dữ liệu theo ngày | Đọc 30 ngày cần nhiều partition |
| Theo thiết bị + giờ | Partition nhỏ hơn và giảm độ nóng của một partition theo thời gian | Đọc nhiều ngày cần nhiều bucket hơn |
| Theo thiết bị + giờ + shard | Phân tán tải của một thiết bị rất nóng | Query phải tìm/gộp trên nhiều shard |

Bucket quá lớn gây rủi ro **wide partition**, áp lực compaction, read amplification và hotspot. Bucket quá nhỏ làm tăng **fan-out** cho truy vấn dài hạn. Không nên chọn “ngày” hay “giờ” theo thói quen; hãy ước lượng **rows/partition**, **bytes/partition**, **writes/second/partition**, **số partition mỗi query** và giới hạn/khuyến nghị thực tế của phiên bản engine đang vận hành.

Đối với dữ liệu chuỗi thời gian, TTL và tombstones cũng ảnh hưởng cách đọc/compaction. Một partition có ít row hiện hữu chưa chắc rẻ nếu chứa nhiều dữ liệu đã xóa và tombstones cần duyệt.

## 12. Bigtable và HBase: row key ảnh hưởng thứ tự và phân bố

Trong các wide-column store có cách sắp hàng theo **row key** như Bigtable/HBase, ứng dụng thường chọn một khóa byte có thứ tự từ điển:

~~~text
tenant#device#timestamp#eventId
~~~

Ví dụ:

~~~text
shop-a#sensor-01#20261114T090000Z#e1
shop-a#sensor-01#20261114T090500Z#e2
shop-a#sensor-01#20261114T091000Z#e3
~~~

Nếu các row keys có tiền tố chung **shop-a#sensor-01#**, chúng có thể nằm gần nhau theo thứ tự key, thuận tiện scan một dải liên tiếp.

Nhưng nếu toàn hệ thống sử dụng **timestamp tăng dần** ở đầu key:

~~~text
20261114T090000Z#shop-a#sensor-01
20261114T090001Z#shop-a#sensor-02
20261114T090002Z#shop-b#sensor-03
~~~

thì dữ liệu mới có thể tập trung vào phần cuối không gian khóa, tạo **hotspot** tại vùng tiếp nhận ghi, tùy cách phân chia tablet/region và workload. Một row key được tối ưu cho **scan thời gian toàn hệ** có thể không tối ưu cho **một thiết bị theo thời gian**.

Các kỹ thuật như **hash prefix/salting, đảo timestamp, bucket theo thời gian hoặc pre-splitting** có thể giảm hotspot, nhưng làm query phức tạp hơn:

- Có salt prefix thì truy vấn một dải có thể phải scan nhiều prefix.
- Có reverse timestamp thì đọc mới nhất thuận tiện, nhưng cần mã hóa và boundary range đúng.
- Có bucket thì đọc nhiều ngày phải ghép nhiều dải.

Không có một công thức key áp dụng cho mọi workload. **Thứ tự byte của row key là một phần của hành vi truy vấn**, nên phải được thiết kế và kiểm tra với dữ liệu đại diện.

## 13. Khóa composite: thiết kế từ các thành phần có ý nghĩa

Một khóa composite thường mã hóa nhiều chiều:

~~~text
TENANT#shop-a#CUSTOMER#customer-07
ORDER#2026-11-14T09:00:00.000Z#order-1001
~~~

Lợi ích là đưa những điều kiện thường dùng vào đường truy cập chính. Nhưng phải thiết kế quy tắc rõ:

1. **Thành phần và thứ tự** cố định.
2. **Định dạng timestamp** đồng nhất, có timezone.
3. **Dấu phân cách và escaping/encoding** tránh hai tuple khác nhau tạo cùng chuỗi.
4. **Trường không được đổi** nếu nằm trong primary key; nếu giá trị đổi, có thể phải xóa item/row cũ rồi chèn mới.
5. **Khóa có thể tăng kích thước**, tác động lưu trữ/index và network.
6. **Tenant scope** phải có nếu uniqueness/phân quyền được xác định theo tenant.
7. **Version của key format** cần được cân nhắc nếu lâu dài phải đổi cấu trúc.

### Va chạm do ghép chuỗi không có escaping

Giả sử ghép bằng dấu **:**:

~~~text
tenantId = "a:b", customerId = "c"  -> "a:b:c"
tenantId = "a",   customerId = "b:c" -> "a:b:c"
~~~

Hai tuple khác nhau cho cùng chuỗi. Cần mã hóa từng phần, dùng định dạng chiều dài–giá trị, hoặc tận dụng composite key native thay vì tự ghép tùy tiện khi engine hỗ trợ.

### Có nên đưa status vào khóa?

Đường đọc **“đơn PAID mới nhất”** có thể gợi ý:

~~~text
PK = TENANT#shop-a#STATUS#PAID
SK = 2026-11-14T09:00Z#order-1001
~~~

Nhưng trạng thái **PENDING → PAID → REFUNDED** thay đổi theo vòng đời. Nếu status là thành phần khóa chính của một bản ghi nguồn, việc đổi status có thể đòi xóa/ghi lại item dưới khóa khác. Vì vậy, nhiều hệ chọn giữ order theo **orderId** ở nguồn chính và dùng **secondary index/read model** theo status để phục vụ truy vấn.

**Field thường thay đổi không phải lúc nào cũng là lựa chọn tốt cho khóa lưu trữ nguồn chính**, dù nó là điều kiện lọc rất phổ biến.

## 14. Cardinality, độ lệch tải và khóa nóng

**Cardinality** là số giá trị khóa/nhóm khác nhau. Nhưng số lượng giá trị lớn chưa đủ: **phân bố lượng ghi/đọc trên mỗi giá trị** cũng rất quan trọng.

Ví dụ:

~~~text
10.000 khách hàng:
  9.999 khách: mỗi người 2 đơn/ngày
  1 khách doanh nghiệp: 200.000 đơn/ngày
~~~

Partition theo customerId có cardinality cao, nhưng khách doanh nghiệp có thể tạo một **hot partition** vì nhận phần lớn ghi. Một khóa **tenantId** duy nhất còn dễ nóng hơn nếu một tenant cực lớn dồn toàn bộ traffic vào một nhóm.

| Tín hiệu | Nguy cơ | Gợi ý xử lý |
|---|---|---|
| Partition key có ít giá trị | Mất cân bằng dữ liệu và tải | Thêm chiều định danh/bucket |
| Một giá trị khóa nhận nhiều ghi | Hot key/partition | Shard/bucket, phân tải có kiểm soát |
| Timestamp tăng dần ở đầu key range | Hot vùng cuối dải trong một số engine | Reverse/salt/bucket theo cơ chế engine |
| Một partition tích lũy quá nhiều row | Wide partition | Chia theo ngày/giờ hoặc thêm bucket |
| Một query phải lấy quá nhiều partition | Fan-out cao | Thay đường đọc, rollup hoặc read model |
| Khóa phân tán ngẫu nhiên | Ghi có thể trải đều | Mất tính gần nhau để scan theo range |

**Hashing** có thể giúp phân tán ghi nhưng không tự giữ **tính liên tục của dải thời gian**. Nếu chia một khách thành 16 shard bằng hash orderId, truy vấn 20 đơn mới nhất có thể phải đọc ứng viên từ cả 16 shard rồi merge/sort. Cần định lượng lợi ích cân bằng tải so với chi phí query fan-out.

Khi đánh giá hotspot, đo **request/second theo partition key**, phân bố p95/p99 của số bản ghi/partition và mức skew (ví dụ top 1% khóa chịu bao nhiêu phần trăm traffic), không chỉ tổng số key.

## 15. Vì sao một khóa có thể tốt cho ghi nhưng không tốt cho đọc?

Ví dụ một bảng sự kiện có thể chọn:

**Khóa theo eventId ngẫu nhiên:**

~~~text
eventId -> payload
~~~

Lợi ích: tra cứu một event theo ID thuận tiện, ghi có thể được phân tán tùy engine. Hạn chế: đọc **100 event mới nhất của sensor-01** không biết eventId của chúng.

**Khóa theo sensorId + timestamp:**

~~~text
sensorId + time bucket -> events sorted by timestamp
~~~

Lợi ích: đọc theo thiết bị và thời gian rất thuận tiện. Hạn chế: một sensor cực nóng có thể tập trung tải; lookup theo eventId không biết sensorId/time.

**Kết hợp hai đường lưu:**

~~~text
events_by_id
  eventId -> complete event

events_by_sensor_day
  sensorId + day + timestamp -> eventId/summary
~~~

Cách kết hợp tăng dung lượng và công việc đồng bộ nhưng phục vụ hai truy vấn quan trọng. Có thể giữ payload đầy đủ ở một nguồn và chỉ lưu **eventId + summary** ở read model, thay vì nhân bản tất cả dữ liệu.

Điểm cốt lõi: **khóa lưu trữ tối ưu một tập truy vấn xác định, không tối ưu mọi truy vấn có thể xuất hiện trong tương lai**.

## 16. Chỉ mục chính và chỉ mục phụ giải quyết những việc khác nhau

Trong cách nói chung:

**Đường chính:** định vị dữ liệu theo khóa cơ sở do engine/table thiết kế.

**Chỉ mục phụ:** duy trì cấu trúc để tìm dữ liệu qua một thuộc tính/khóa khác.

| Cơ chế | Ví dụ | Đánh đổi |
|---|---|---|
| MongoDB _id index | Tìm một document theo _id | Chỉ hỗ trợ tốt điều kiện phù hợp khóa _id |
| MongoDB compound secondary index | Tìm order theo customer + createdAt | Thêm index storage/ghi, planner phải chọn đúng |
| DynamoDB table PK/SK | Query orders của customer | Chỉ truy cập hiệu quả khi biết PK |
| DynamoDB GSI | Query orders theo status/time | Thêm copy index, throughput/độ trễ và consistency riêng |
| Cassandra primary key | Định vị partition và range theo clustering | Query theo chiều khác có thể cần bảng khác/index thích hợp |
| Redis secondary structure do ứng dụng duy trì | Sorted Set customer orders | Phải đồng bộ với các value keys |
| Bigtable row-key range | Scan các row có prefix/time range | Row-key design quyết định clustering/hotspot |

**Tạo chỉ mục phụ không miễn phí.** Một lần ghi thay đổi indexed field có thể làm engine sửa nhiều cấu trúc; nhiều index tăng chi phí lưu trữ và cập nhật. Ở các mô hình denormalized, một thay đổi nguồn còn phải cập nhật nhiều **read models**.

Ngược lại, không có index phụ phù hợp có thể làm một truy vấn ít gặp phải scan rất lớn. Do đó cần phân loại:

- Truy vấn **trực tuyến, độ trễ chặt** → ưu tiên đường truy cập trực tiếp.
- Truy vấn **báo cáo định kỳ** → có thể chuyển sang analytics hoặc batch.
- Truy vấn **hiếm và đơn giản** → đôi khi index sẵn đã đủ, không cần tạo một read model mới.
- Truy vấn **mới phát sinh** → đo chi phí trước khi thay đổi mô hình nguồn.

## 17. Một secondary index không thay thế primary access path

Với MongoDB, thêm:

~~~javascript
db.orders.createIndex({ status: 1, createdAt: -1 });
~~~

giúp engine có một lựa chọn khi truy vấn theo status/time. Nhưng khi API chỉ có customerId, index này không trở thành index phù hợp nhất chỉ vì nó chứa createdAt.

Với DynamoDB, một GSI có PK theo status cho phép Query theo status. Nhưng **GetItem** trên table vẫn yêu cầu **primary key của table**; GSI được Query qua API và có cơ chế nhất quán/throughput riêng.

Với Cassandra, một secondary index hoặc Storage-Attached Index (SAI) trong những phiên bản/hệ hỗ trợ có thể hỗ trợ một số điều kiện truy vấn, nhưng không được giả định nó biến mọi truy vấn xuyên nhiều partition thành một đường đọc có hiệu năng ngang với primary-key lookup. Cần benchmark theo cardinality, selectivity, partition count và dữ liệu thực tế.

**Chọn đường chính trước, thêm đường phụ theo truy vấn có bằng chứng**, thay vì tạo index trên mọi field rồi kỳ vọng engine tự tối ưu tất cả.

## 18. Thiết kế đường đọc ngược và bản sao theo truy vấn

Xét một quan hệ N:M giữa học viên và khóa học:

~~~text
student-01 -> course-nosql
student-01 -> course-java
student-02 -> course-nosql
~~~

Hai truy vấn:

- **Liệt kê khóa đang học của student-01**.
- **Liệt kê học viên đang ACTIVE của course-nosql**.

Nếu dữ liệu lưu theo khóa **studentId**, đường thứ nhất thuận tiện, đường thứ hai không.

Trong Cassandra có thể tổ chức:

~~~sql
CREATE TABLE enrollments_by_student (
  tenant_id text,
  student_id text,
  course_id text,
  status text,
  enrolled_at timestamp,
  PRIMARY KEY ((tenant_id, student_id), course_id)
);

CREATE TABLE enrollments_by_course (
  tenant_id text,
  course_id text,
  student_id text,
  status text,
  enrolled_at timestamp,
  PRIMARY KEY ((tenant_id, course_id), student_id)
);
~~~

Hai bảng trên phục vụ lookup **theo student** và **theo course**. Tuy nhiên, vì clustering key là **course_id/student_id**, chúng **không tự phục vụ phân trang theo enrolled_at DESC**. Nếu nghiệp vụ yêu cầu đăng ký mới nhất, phải thay đổi clustering design hoặc thêm read model với sort key phù hợp.

Hai bảng cũng là **hai bản dữ liệu liên quan**. Khi một enrollment đổi status, phải đồng bộ cả hai theo hợp đồng; lỗi giữa chừng có thể làm hai màn hình trả dữ liệu khác nhau.

### Khi nào không cần nhân bản?

Nếu dùng MongoDB, một collection **enrollments** có index theo student và một index theo course có thể phục vụ cả hai chiều mà không cần lưu hai document quan hệ cho cùng một cặp. Việc chọn **bảng theo truy vấn** hay **index phụ** phụ thuộc sản phẩm và workload, không phải quy tắc chung cho mọi NoSQL.

## 19. Truy vấn giới hạn 20 dòng không có nghĩa chỉ đọc 20 dòng

Ví dụ:

~~~text
Storage key: customerId
Filter bổ sung: status = PAID
Limit: 20
~~~

Một customer có 100.000 order, chỉ 100 order PAID, và phần lớn nằm rất sâu trong lịch sử. Hệ thống có thể phải đọc rất nhiều order PENDING trước khi có 20 PAID để trả về.

| Tình huống | Hành vi có thể xảy ra |
|---|---|
| Partition/key phù hợp với cả customer + status | Có thể duyệt trực tiếp tập PAID |
| Partition chỉ theo customer, filter status sau khi đọc | Có thể đọc nhiều item bị loại |
| Có index theo customer + status + time | Có thể tránh đọc phần lớn item khác status |
| Scan toàn table theo status | Đọc rộng, dù response chỉ có 20 dòng |

Trong DynamoDB, hãy phân biệt **Limit**, **Count**, **ScannedCount** và **LastEvaluatedKey**; FilterExpression có thể khiến một page đã đọc nhiều item nhưng trả về ít item. Trong MongoDB, quan sát **keysExamined/docsExamined/nReturned**; trong Cassandra, theo dõi số partition, row/tombstone được đọc, timeout và số page.

Một chỉ số mô tả mức đọc thừa:

\[
\text{Read Amplification Ratio}
= \frac{\text{số item/row được xét hoặc đọc}}{\text{số item trả về}}
\]

Đây là tỷ lệ mang tính phân tích, không phải một metric chuẩn đồng nhất giữa mọi engine. Nó cũng không thay thế số byte I/O hay độ trễ thực tế; nhưng giúp phát hiện một query trả ít mà phải duyệt quá nhiều.

## 20. Sort và pagination phải dựa trên thứ tự ổn định

Một API lịch sử đơn thường có:

~~~text
Sort: createdAt DESC
Limit: 20
~~~

Nếu hai order cùng **createdAt**, thứ tự của chúng có thể không ổn định nếu không có khóa phụ. Nên có **orderId** hoặc một ID duy nhất làm tie-breaker:

~~~text
createdAt DESC, orderId DESC
~~~

Trong MongoDB:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  customerId: "customer-07"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Một cursor cho trang tiếp theo có thể dựa trên **(lastCreatedAt, lastId)**:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  customerId: "customer-07",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-14T09:00:00Z") } },
    {
      createdAt: ISODate("2026-11-14T09:00:00Z"),
      _id: { $lt: "order-1001" }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Ví dụ giả định **_id là String** được sắp cùng quy ước với index; không chuyển tùy tiện giữa String và ObjectId hoặc so sánh ID bằng kiểu khác. Nếu ứng dụng cho phép thay đổi createdAt, cursor có thể không còn ổn định theo ý nghĩa snapshot; cần quy tắc thời gian bất biến hoặc snapshot/watermark phù hợp.

Với DynamoDB, phân trang thường dùng **LastEvaluatedKey** làm **ExclusiveStartKey** ở request tiếp theo. Nó là cơ chế của Query/Scan, không phải offset số trang và không nên tự thay bằng “bỏ qua N item” khi dữ liệu lớn. Trên nhiều partition/shard, ứng dụng có thể phải giữ cursor riêng từng nguồn rồi merge.

**Keyset/cursor pagination** thường phù hợp hơn offset sâu cho tập dữ liệu lớn liên tục thay đổi, nhưng cần định nghĩa điều gì xảy ra khi có bản ghi mới hoặc bị xóa giữa hai lần đọc.

## 21. Ranh giới nhất quán không tự xuất hiện vì dữ liệu cùng khóa

Đặt các item chung một partition key thuận tiện truy vấn nhóm, **không có nghĩa nhiều item tự được cập nhật nguyên tử như một document**.

Ví dụ:

~~~text
Customer partition:
  ORDER#1001 -> status PAID
  ORDER#1002 -> status PENDING
  SUMMARY    -> totalPaid = 1
~~~

Nếu muốn đổi order-1002 thành PAID **và** tăng totalPaid, hai item phải được cập nhật cùng ý định nghiệp vụ. Trong DynamoDB có thể cần transaction/conditional writes theo giới hạn hỗ trợ, hoặc chấp nhận summary là read model được cập nhật sau và đối soát. Một PK chung không tự bảo vệ tổng.

Trong Cassandra, các bảo đảm ghi trên partition, batch và lightweight transaction có ngữ nghĩa riêng; **cùng partition** không đồng nghĩa hệ tự kiểm tra mọi bất biến nghiệp vụ giữa các hàng.

Trong MongoDB, thao tác ghi trên **một document** có tính nguyên tử ở phạm vi document, nhưng nếu dữ liệu liên quan nằm trên nhiều document thì cần xem transaction hoặc workflow khác. Không được nhầm **đường truy cập chung** với **ranh giới transaction**.

## 22. Khóa định danh nên ổn định và phản ánh ownership

Một order đã chốt thường có **orderId ổn định**, còn **status** thay đổi nhiều lần.

~~~text
Order identity:
  tenantId + orderId

Mutable fields:
  status, shippingAddress, paymentStatus, updatedAt
~~~

Nếu status nằm trong primary key, mỗi lần chuyển trạng thái có thể phải di chuyển dữ liệu sang key khác hoặc viết bản sao mới. Nếu dùng status trong **read model**, việc đồng bộ có thể được thiết kế riêng.

Tương tự, **customer email** hiếm khi là khóa lưu duy nhất tốt cho customer nếu email có thể thay đổi hoặc có quy tắc chuẩn hóa phức tạp. Một **customerId ổn định** thường thích hợp làm định danh, còn email có thể được bảo vệ bằng unique index theo phạm vi tenant.

Khóa còn phải hỗ trợ phân quyền:

- TenantId trong logical/partition key giúp biểu diễn phạm vi truy cập và tránh trộn lẫn dữ liệu, nhưng **không thay thế authorization**.
- API không được tin tenantId do client tự khai; phải lấy/đối chiếu từ ngữ cảnh xác thực.
- Truy vấn chỉ theo orderId mà thiếu điều kiện owner/tenant có thể gây lộ dữ liệu nếu ứng dụng không kiểm tra quyền.
- Unique index và storage key bảo vệ tính định danh, **không tự xác nhận người dùng được phép xem hoặc sửa item đó**.

## 23. Chỉ mục và bản đọc dẫn xuất cần được cập nhật đúng khi ghi

Giả sử nguồn chính:

~~~text
orders_by_id:
  order-1001 -> {customerId, status, createdAt}
~~~

Và read model:

~~~text
orders_by_customer:
  customer-07 + createdAt -> order-1001

orders_by_status:
  shop-a + PAID + createdAt -> order-1001
~~~

Khi status đổi **PENDING → PAID**, đường chính cập nhật status. Read model theo status cần:

1. Loại bỏ bản **PENDING** nếu có.
2. Tạo hoặc cập nhật bản **PAID**.
3. Không áp dụng lại sự kiện cũ sau sự kiện mới.
4. Không tạo bản sao trùng khi consumer retry.
5. Đối soát những bản bị bỏ sót do worker dừng giữa chừng.

~~~mermaid
flowchart TD
    A["Ghi order nguồn chính"] --> B["Ghi change event/outbox"]
    B --> C["Consumer cập nhật index/read models"]
    C --> D["Đường đọc theo customer"]
    C --> E["Đường đọc theo status"]
    C --> F["Đường đọc theo SKU"]
    C --> G["Giám sát lag, duplicate và mismatch"]
    G --> H["Replay/backfill/đối soát khi cần"]
~~~

Nếu secondary index được engine quản lý nội bộ, database chịu trách nhiệm cập nhật index theo bảo đảm của sản phẩm. Nếu là **bảng truy cập do ứng dụng duy trì**, phải thiết kế write path và cơ chế sửa lỗi rõ ràng.

Một read model bất đồng bộ **không nên được dùng làm nguồn duy nhất để quyết định một bất biến ghi cứng**, ví dụ “chỉ bán nếu stock còn” hoặc “một ghế chỉ được xác nhận một lần”. Những quyết định đó cần cơ chế điều kiện ghi tại nguồn có thẩm quyền.

## 24. Không gian lưu trữ, write amplification và read amplification

Ví dụ một order xuất hiện ở:

~~~text
1 bản nguồn theo orderId
1 bản chỉ mục theo customerId
1 bản theo status + time
1 bản theo product SKU (mỗi item có thể nhiều bản)
~~~

Một lần đổi trạng thái có thể khiến nhiều bản đọc/chỉ mục phải cập nhật. Đây là **write amplification ở cấp mô hình**. Trong khi đó, thiếu access path phù hợp có thể khiến truy vấn phải scan rộng — **read amplification**.

Hai loại chi phí cần được đặt cạnh nhau:

| Câu hỏi | Nếu nghiêng về một đường đọc mới | Nếu nghiêng về dùng index/nguồn hiện có |
|---|---|---|
| Truy vấn chạy nhiều lần mỗi giây? | Có thể đáng đầu tư read model | Nếu hiếm, chưa chắc đáng |
| Truy vấn phải scan rất rộng? | Một đường key mới có thể giảm chi phí | Index hiện tại có thể đã đủ |
| Dữ liệu nguồn đổi thường xuyên? | Bản sao tăng chi phí đồng bộ | Tham chiếu/lookup có thể đơn giản hơn |
| Cần nhất quán tức thời? | Dùng đường đọc có bảo đảm phù hợp | Tránh read model eventual cho quyết định cứng |
| Số chiều truy vấn rất nhiều? | Không thể tạo vô hạn bảng cho mọi chiều | Cân nhắc search/analytics chuyên dụng |
| Tập dữ liệu tăng nhanh? | Partition bucketing có thể cần thiết | Thiết kế lại nếu một partition tăng vô hạn |

Không nên cho rằng “chỉ có một query là nhanh nhất” nếu một query đó phải đọc hàng triệu item, hoặc “thêm index luôn làm nhanh” nếu index không khớp query và làm tăng chi phí ghi quá nhiều.

## 25. Ước tính nhanh đường truy cập trước khi triển khai

Giả sử:

~~~text
1.000.000 khách
Trung bình 50 order/khách/năm
Giữ dữ liệu nóng 2 năm
Trung bình 1.000 byte payload/order
~~~

Số order:

\[
1\,000\,000 \times 50 \times 2 = 100\,000\,000
\]

Payload thô ước tính:

\[
100\,000\,000 \times 1\,000
= 100\,000\,000\,000\ \text{byte}
\approx 100\ \text{GB}
\]

Con số này **chưa tính** index, metadata, replication, compression, backup, log hoặc bản sao theo access pattern.

Nếu mỗi khách có trung bình 100 order trong 2 năm, partition/customer trung bình không lớn. Nhưng chỉ số trung bình che giấu khách hàng lớn. Cần đo **p50/p95/p99/max orders per customer**, không chỉ lấy 100 rồi áp dụng cho mọi khách.

Giả sử một customer doanh nghiệp ghi 100.000 order/ngày, mỗi order 1 KB:

\[
100\,000 \times 1\,000
= 100\,000\,000\ \text{byte/ngày}
\approx 100\ \text{MB/ngày}
\]

Một partition tích lũy lâu dài theo customer có thể trở nên quá lớn hoặc nóng trong một số engine; bucket theo ngày/tháng hay shard có thể cần, nhưng làm query toàn lịch sử phải kết nối nhiều vùng.

**Mô hình khóa phải được chọn theo phân bố dữ liệu và tốc độ tải thực tế, không chỉ số trung bình trên slide kiến trúc.**

## 26. Quan sát đường truy cập sau khi hệ thống chạy

Một quyết định khóa tốt trên giấy cần được xác nhận bằng số liệu.

| Metric/quan sát | Ý nghĩa |
|---|---|
| **p50/p95/p99 latency** theo access pattern | Thời gian phản hồi thực tế của query |
| **Bytes read vs bytes returned** | Phát hiện I/O thừa do scan hoặc fetch payload lớn |
| **Rows/items examined vs returned** | Phát hiện filter sau khi đọc rộng |
| **Partition fan-out** | Một request chạm bao nhiêu partition/shard |
| **Partition size p95/p99/max** | Phát hiện wide partition |
| **Hot key/partition rate** | Một số khóa chiếm nhiều tài nguyên |
| **Index hit/query plan** | Query có dùng index như dự tính không |
| **Pagination depth** | Người dùng có đọc quá sâu không, cursor có ổn định không |
| **Write amplification** | Một ghi nguồn gây bao nhiêu update index/read model |
| **Read model lag** | Độ trễ bản sao so với nguồn |
| **Throttling/conflict/retry** | Phân vùng nóng hoặc cập nhật cạnh tranh |
| **Storage/index growth** | Đường truy cập bổ sung tốn bao nhiêu chi phí |

Theo sản phẩm:

- **MongoDB:** **explain("executionStats")**, keys/docs examined, winningPlan, các stage sort/fetch/scan, số shard được target trong triển khai sharded.
- **DynamoDB:** đọc các số liệu **ConsumedCapacity**, **Count**, **ScannedCount**, **LastEvaluatedKey**, throttling/hot key và metrics từ CloudWatch hoặc hệ quan sát tương ứng.
- **Cassandra:** trace/metrics/query latency, số partition/row/tombstone cần đọc, read/write timeouts, mức phân bố token/partition và compaction.
- **Redis:** latency, command count, memory, key size, slowlog, hot key, eviction/cache hit và độ lệch hash slot khi dùng cluster.
- **Bigtable/HBase:** phân bố load theo tablet/region, kích thước row key ranges, hotspot và scan latency.

Không phải mọi hệ đều cung cấp cùng một chỉ số hay tên gọi. Quan trọng là kết nối metric với **đường truy cập cụ thể đang được đo**, thay vì chỉ nhìn CPU trung bình toàn cluster.

## 27. Các phản ví dụ thường gặp

### Phản ví dụ 1: “Có LIMIT 20 nên query chắc chắn rẻ”

Sai vì hệ có thể scan hàng triệu item rồi mới tìm được 20 item thỏa filter. Phải kiểm tra số item/row được duyệt trước khi trả về.

### Phản ví dụ 2: “customerId là primary key nên toàn bộ lịch sử để chung một partition”

Chưa chắc phù hợp. Một khách có thể có hàng triệu bản ghi; cần ước lượng kích thước và thời hạn lưu, có thể dùng time bucket hoặc read model riêng.

### Phản ví dụ 3: “Đặt timestamp ở đầu key sẽ query thời gian rất nhanh”

Trong một số ordered key stores, timestamp tăng dần ở đầu key có thể tạo vùng ghi nóng. Ngoài ra, query theo từng device có thể phải lẫn rất nhiều device.

### Phản ví dụ 4: “Thêm FilterExpression là có index theo status”

Sai trong DynamoDB. FilterExpression thường áp dụng sau khi item đã được đọc bởi Query/Scan; nó không thay thế KeyConditionExpression hoặc GSI.

### Phản ví dụ 5: “Cùng partition key thì cập nhật nhiều item là nguyên tử”

Không có kết luận chung như vậy. Cần biết transaction/conditional write của từng engine và phạm vi bảo đảm.

### Phản ví dụ 6: “Hash shard key giúp mọi truy vấn nhanh hơn”

Hashing có thể giúp phân bố tải nhưng phá tính liên tục của range; query theo thời gian có thể phải fan-out và merge nhiều shard.

### Phản ví dụ 7: “Có index trên _id thì sharded query theo _id luôn tới một shard”

Nếu shard key khác _id và truy vấn không có đủ thông tin định tuyến, cần kiểm tra chính xác cơ chế target shard của phiên bản/cấu hình.

### Phản ví dụ 8: “Tạo index cho mọi field thì không cần thiết kế schema”

Nhiều index tăng ghi/dung lượng, trong khi filter/sort/range không khớp index vẫn có thể đọc rất rộng. Một số engine không hỗ trợ truy vấn tùy ý ngay cả khi có những index hạn chế.

### Phản ví dụ 9: “Một bản ghi nguồn chỉ cần một khóa duy nhất”

Đúng về định danh có thể chỉ cần một khóa, nhưng ứng dụng còn có nhiều access patterns. Cần quyết định secondary indexes/read models theo lợi ích đo được.

### Phản ví dụ 10: “Tên field là partitionId thì tự quyết định nơi lưu”

Không đúng. Chỉ cấu hình schema/index/partitioning thực tế của database mới quyết định đường định tuyến; tên trường trong document không tự tạo phân vùng.

## 28. Quy trình thiết kế đường truy cập chính

~~~mermaid
flowchart TD
    A["Liệt kê query & write patterns"] --> B["Chọn truy vấn ưu tiên, SLO và phạm vi"]
    B --> C["Biết đủ key nào từ request?"]
    C --> D["Chọn identity / partition / sort key"]
    D --> E["Ước lượng cardinality, size, skew, tốc độ tăng"]
    E --> F{"Có hot hoặc wide partition?"}
    F -->|Có| G["Bucket/shard/đổi key có kiểm soát"]
    F -->|Không| H["Thiết kế query theo key/range"]
    G --> H
    H --> I["Xác định query không được key chính hỗ trợ"]
    I --> J["Index phụ / read model / analytics khi cần"]
    J --> K["Kiểm tra consistency, cập nhật và xóa"]
    K --> L["Đo plan, scanned/returned, latency và cost"]
    L --> M{"Đạt yêu cầu?"}
    M -->|Chưa| D
    M -->|Đạt| N["Giám sát khi dữ liệu và truy vấn thay đổi"]
~~~

Các bước có thể áp dụng cho phần lớn bài toán NoSQL:

1. **Viết truy vấn cụ thể:** khóa đầu vào, filter, sort, limit, range, payload và tần suất.
2. **Chọn đường truy cập được ưu tiên:** point lookup, range theo một chủ thể hay aggregate theo thời gian.
3. **Định nghĩa identity ổn định:** business key, tenant scope và uniqueness.
4. **Chọn partition/shard key theo khả năng định vị và phân bố tải**, không chỉ theo tên thực thể.
5. **Chọn sort/clustering key** nếu engine hỗ trợ, dựa trên thứ tự query và tie-breaker.
6. **Ước lượng partition size và hotspot:** p95/p99/max, dữ liệu tăng và thời gian lưu.
7. **Xác định query không được khóa chính phục vụ** và chọn index/read model/analytics có chủ đích.
8. **Thiết kế quyền, concurrency, transaction và vòng đời**: khóa truy cập không tự bảo vệ bất biến.
9. **Thiết kế cursor/pagination và xử lý dữ liệu thay đổi khi đọc**.
10. **Benchmark/quan sát** số item phải đọc, fan-out, độ trễ và write amplification.

## 29. Bài tập thực hành

### Bài tập 1 — Từ yêu cầu sang khóa

API cần lấy **20 order mới nhất của customerId** và **một order theo orderId**. Hãy đề xuất primary access path cho mỗi truy vấn, giải thích vì sao một khóa **PK=customerId, SK=createdAt#orderId** không tự cho phép GetItem theo orderId khi không biết customerId.

### Bài tập 2 — Composite key

Thiết kế khóa theo **tenantId + customerId + createdAt + orderId**. Trình bày quy tắc format timestamp, quy tắc escape separator và cách bảo đảm hai order cùng timestamp vẫn có định danh duy nhất.

### Bài tập 3 — DynamoDB Query vs filter

Một customer có 10.000 order nhưng chỉ 50 order PAID. API Query theo PK customer, dùng **FilterExpression status=PAID** và **Limit=20**. Vì sao trang đầu có thể trả ít hơn 20 PAID? Đề xuất GSI/read model và cách xử lý LastEvaluatedKey.

### Bài tập 4 — Cassandra range query

Thiết kế bảng sự kiện theo **tenant + device + day**, clustering **time DESC + eventId**. Viết CQL lấy 100 event mới nhất trong một ngày. Giải thích điều gì xảy ra nếu cần đọc 30 ngày hoặc cần tìm mọi event ERROR của cả tenant.

### Bài tập 5 — Ước lượng partition

Một sensor ghi **25 event/giây**, giữ raw 90 ngày. So sánh rows/partition nếu bucket theo ngày và theo giờ. Hãy nêu khi nào mỗi lựa chọn có thể tạo partition quá rộng hoặc query fan-out lớn.

### Bài tập 6 — Redis đường truy cập thứ hai

Lưu order theo key **order:{id}**. Cần đọc 20 order mới nhất của customer. Hãy đề xuất Sorted Set theo customer, cách cập nhật khi order được tạo/xóa và chính sách xử lý nếu order value tồn tại nhưng sorted set thiếu ID.

### Bài tập 7 — MongoDB compound index

Một collection có index **(_id)** nhưng query thường lọc **tenantId + customerId**, sort **createdAt DESC**. Thiết kế compound index thích hợp và mô tả cách dùng **explain("executionStats")** để so với COLLSCAN. Vì sao một index chỉ theo status không giúp nhiều cho truy vấn này?

### Bài tập 8 — Truy vấn ngược nhiều-nhiều

Tạo **enrollments_by_student** và **enrollments_by_course** trong Cassandra. Nếu trang quản trị cần **50 enrollment mới nhất theo enrolledAt**, cần sửa thiết kế clustering như thế nào? Đánh đổi khi một course có một triệu học viên là gì?

### Bài tập 9 — Khóa nóng

Một khách doanh nghiệp tạo 200.000 order/ngày, còn hàng nghìn khách khác chỉ có vài order. Nếu partition theo customerId, nguy cơ nào xuất hiện? Phác thảo phương án bucket/shard và cách merge kết quả 20 đơn mới nhất.

### Bài tập 10 — Thay trạng thái

Đội phát triển muốn dùng **status** làm thành phần chính của khóa nguồn vì màn hình báo cáo thường filter PAID. Hãy phân tích chi phí khi order **PENDING → PAID → REFUNDED**, và đề xuất nguồn theo orderId + index/read model theo status.

### Bài tập 11 — Point lookup và phân quyền

API chỉ nhận **orderId**, database có thể tìm bản ghi rất nhanh bằng primary index. Vì sao vẫn cần xác thực tenant/owner? Hãy nêu cách tổ chức logical key hoặc điều kiện đọc để tránh người dùng A xem order của người B.

### Bài tập 12 — Keyset pagination

Có nhiều order cùng **createdAt** và khách tải lịch sử theo trang 20 dòng. Hãy thiết kế thứ tự **createdAt DESC, orderId DESC**, biểu diễn cursor và điều kiện trang tiếp theo. Giải thích vấn đề khi order mới được thêm giữa hai trang.

### Bài tập 13 — Đồng bộ secondary read model

Nguồn order đổi status thành PAID; ứng dụng có thêm bảng **orders_by_status**. Hãy mô tả cách tạo event, chống xử lý trùng và sai thứ tự, dọn bản ở trạng thái cũ, checkpoint và job đối soát. Tại sao đọc bản này có thể không thích hợp để bảo vệ bất biến thanh toán?

### Bài tập 14 — Hệ thống lai

Một ứng dụng dùng MongoDB làm nguồn order, Redis cache theo orderId và Elasticsearch hoặc một search engine cho truy vấn văn bản. Hãy phân tích đường truy cập chính của từng hệ, trường hợp nào nên lấy từ nguồn và cách xử lý cache/search index trễ khi order bị xóa hoặc thay quyền.

### Bài tập 15 — Đánh giá bằng số liệu

Một đề xuất mới tạo thêm GSI/read model để tối ưu truy vấn hiếm. Hãy lập bảng các thông số cần đo: query volume, p95 latency, scanned/returned, index size, write amplification, consistency, partition skew, chi phí đồng bộ và mức độ quan trọng của SLO. Từ đó giải thích khi nào nên giữ mô hình nguồn và khi nào cần tạo đường truy cập mới.

---

**Kết luận:** Trong NoSQL, **khóa lưu trữ không chỉ định danh dữ liệu; nó còn quyết định cách định vị, tổ chức và đọc dữ liệu hiệu quả nhất**. Một key phù hợp giúp thực hiện point lookup hoặc range query mà không quét rộng. Partition key ảnh hưởng đến phân bố và giới hạn phạm vi đọc; sort/clustering key ảnh hưởng đến thứ tự và phân trang. Những truy vấn dùng chiều dữ liệu khác có thể cần index phụ, read model hoặc bảng được thiết kế theo access pattern. Để chọn đúng, hãy đi theo chuỗi **yêu cầu truy vấn → khóa đã biết → key/partition/sort → kích thước và độ nóng → index phụ → tính nhất quán và chi phí cập nhật → số liệu kiểm chứng**. Chọn khóa tốt là chọn một **đường truy cập có chủ đích**, không phải mong rằng mọi điều kiện lọc đều được database tối ưu như nhau.
