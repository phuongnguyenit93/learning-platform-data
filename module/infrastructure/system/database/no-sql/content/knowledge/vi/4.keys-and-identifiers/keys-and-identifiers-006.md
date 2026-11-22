# Thiết kế tiền tố, vùng tên và mã tenant trong khóa NoSQL

## 1. Vì sao phải thiết kế cấu trúc khóa?

Trong cơ sở dữ liệu NoSQL, khóa thường là điểm bắt đầu của thao tác đọc, ghi và định vị dữ liệu. Ở hệ thống nhỏ, khóa có thể chỉ là một mã như `123`. Nhưng khi ứng dụng có nhiều loại tài nguyên, nhiều môi trường, nhiều dịch vụ và nhiều khách hàng cùng sử dụng, một mã ngắn không đủ để biểu thị **dữ liệu thuộc về đâu và có ý nghĩa gì**.

Giả sử hai cửa hàng khác nhau đều phát sinh đơn hàng `ord_123`. Nếu dữ liệu dùng chung một kho và tên khóa chỉ là:

```text
order:ord_123
```

thì hai đơn có thể va chạm hoặc bị ghi đè. Một quy ước có ngữ cảnh rõ hơn:

```text
prod:commerce:tnt_7J2:order:ord_123
prod:commerce:tnt_9Q4:order:ord_123
```

Hai khóa khác nhau bởi mã tenant, dù cùng loại tài nguyên và cùng ID cục bộ.

Ví dụ trên minh họa **khóa logic dạng chuỗi**. Không phải mọi hệ NoSQL dùng một chuỗi khóa: Redis làm việc trực tiếp với key string; DynamoDB thường dùng partition key và sort key; Cassandra khai báo partition key bằng cột; MongoDB có `_id` và các chỉ mục. Nguyên tắc tổ chức định danh có thể dùng chung, nhưng cơ chế lưu trữ và truy vấn cần được thiết kế cho từng hệ.

## 2. Tiền tố, vùng tên và mã tenant: ba vai trò khác nhau

| Thành phần | Ý nghĩa | Ví dụ | Giải quyết vấn đề |
|---|---|---|---|
| **Prefix** (tiền tố) | Đoạn đầu của khóa theo quy ước đặt tên | `prod:commerce:` | Dễ nhận diện và phân nhóm khóa |
| **Namespace** (vùng tên) | Phạm vi logic mà tên và ID được phân biệt với phạm vi khác | `commerce:tnt_7J2` | Ngăn xung đột giữa ứng dụng, miền nghiệp vụ hoặc tenant |
| **Tenant ID** | Định danh ổn định của khách hàng/tổ chức trong ứng dụng đa tenant | `tnt_7J2` | Xác định phạm vi sở hữu và truy vấn dữ liệu |
| **Resource type** | Nhãn loại dữ liệu | `order`, `cart`, `invoice` | Phân biệt các thực thể có cùng mã |
| **Resource ID** | ID bản ghi cụ thể | `ord_123` | Xác định đối tượng cần đọc hoặc ghi |

**Prefix** là cách mã hóa một phần namespace vào chuỗi khóa. **Namespace** rộng hơn prefix: có thể được thực hiện bằng database riêng, collection riêng, một cột `tenantId` hay một partition key ghép. **Tenant** không đồng nghĩa **user**: một tenant có thể chứa nhiều người dùng; một người dùng có thể được cấp quyền đối với nhiều tenant.

Ví dụ cấu trúc nhiều tenant:

```text
Nền tảng quản lý bán hàng
  |
  +-- Tenant tnt_7J2
  |     +-- Order ord_123
  |     +-- User usr_456
  |
  +-- Tenant tnt_9Q4
        +-- Order ord_123
        +-- User usr_890
```

Ở đây `ord_123` không bắt buộc duy nhất toàn hệ thống; nó có thể duy nhất **bên trong từng tenant**, miễn định danh đầy đủ luôn chứa đúng phạm vi tenant.

## 3. Đề xuất một quy ước đặt tên khóa

Một mẫu phổ biến khi hệ thống dùng key dạng chuỗi:

```text
<environment>:<application>:<tenant-id>:<resource-type>:<resource-id>
```

Ví dụ:

```text
prod:commerce:tnt_7J2:order:ord_123
prod:commerce:tnt_7J2:order:ord_124
prod:commerce:tnt_7J2:cart:usr_456
prod:commerce:tnt_9Q4:order:ord_123
```

Ý nghĩa từng đoạn:

1. `environment`: `dev`, `staging`, `prod` để nhận diện môi trường, nhất là khi có hạ tầng dùng chung.
2. `application`: `commerce`, `identity`, `billing` để phân biệt chủ sở hữu nghiệp vụ.
3. `tenant-id`: ID tổ chức/khách hàng, ví dụ `tnt_7J2`.
4. `resource-type`: `order`, `invoice`, `profile`, giúp tránh các ID trùng giữa loại dữ liệu.
5. `resource-id`: định danh ổn định của bản ghi cần thao tác.

Thứ tự này là **quy ước**, không phải công thức tối ưu chung. Có hệ thống đặt tenant trước application; với những hệ có composite PK/SK, thứ tự trường còn quyết định đường truy cập và phân vùng. Mục tiêu là một quy tắc **nhất quán, không nhập nhằng và bám theo mẫu truy vấn chính**.

### Vùng tên theo dịch vụ và môi trường

Nếu hai dịch vụ cùng dùng một Redis:

```text
prod:commerce:tnt_7J2:cart:usr_456
prod:identity:tnt_7J2:session:sess_789
```

thì nhãn ứng dụng giúp giảm va chạm. Tuy nhiên, thêm `prod` không có nghĩa đã cô lập production với staging về quyền truy cập hoặc độ an toàn vận hành. Môi trường quan trọng vẫn nên được tách ở tầng hạ tầng, credential và chính sách tương ứng.

### Đặt thêm tiểu vùng tên khi cần

Nếu một tài nguyên gồm các phần có vòng đời khác nhau:

```text
prod:commerce:tnt_7J2:order:ord_123:status
prod:commerce:tnt_7J2:order:ord_123:timeline
```

Nhưng không nên chia mọi trường thành khóa riêng chỉ vì có thể đặt tiền tố. Khi một document cần đọc hoặc cập nhật như một đơn vị, mô hình lưu chung thường đơn giản hơn. Tên khóa và cấu trúc value là hai quyết định liên quan nhưng không đồng nhất.

## 4. Dấu phân cách và quy tắc chuẩn hóa

Dấu `:` phổ biến vì dễ đọc; Redis không tự hiểu từng đoạn sau dấu hai chấm như cột riêng. Ứng dụng phải thống nhất quy tắc tạo và diễn giải khóa.

Nên xác định từ đầu:

- Tên cố định viết chữ thường, ví dụ `order` thay vì khi dùng `Order`, khi dùng `orders`.
- ID dùng một tập ký tự cho phép rõ ràng; ví dụ `A–Z`, `a–z`, `0–9`, `_`, `-`.
- Mỗi đoạn có giới hạn độ dài.
- Những dữ liệu có chứa `:` phải được mã hóa theo cách đảo ngược được và không gây nhập nhằng, hoặc đổi sang ID nội bộ.
- Không tự ý biến ID có phân biệt chữ hoa/thường thành chữ thường.
- Mọi dịch vụ dùng chung một quy ước về phiên bản, tên loại tài nguyên và thứ tự đoạn.

Ví dụ nếu ghép trực tiếp đầu vào:

```text
tenantId = "north:west"
orderId  = "ord:123"

tenant:north:west:order:ord:123
```

Chuỗi sinh ra không thể được phân đoạn an toàn bằng thao tác `split(":")` thông thường. Cách thích hợp là **cấp ID nội bộ ổn định** hoặc **mã hóa segment** trước khi ghép. Việc thay dấu `:` bằng ký tự khác một cách tùy tiện cũng có thể gây va chạm nếu ký tự thay thế đã tồn tại trong dữ liệu gốc.

Không nên đưa trực tiếp email, tên công ty, số điện thoại hoặc giấy tờ cá nhân vào khóa: chúng có thể thay đổi, làm khóa dài và làm rò rỉ dữ liệu qua log, metric hoặc công cụ quan sát.

## 5. Thiết kế mã tenant

Trong ứng dụng multi-tenant, tenant thường đại diện cho một công ty, tổ chức hoặc cửa hàng. Tenant có thể đổi tên hiển thị, thay tên miền và gói dịch vụ, nhưng dữ liệu phải tiếp tục liên kết với đúng tổ chức.

```text
Tenant ID:     tnt_7J2
Tên hiển thị:  Cửa hàng Hoa Mai
Tên miền:      hoamai.example
```

Nếu tên hiển thị đổi thành "Hoa Mai Store", `tnt_7J2` nên giữ nguyên. Vì vậy mã tenant cần:

- **Bất biến** trong vòng đời tenant, kể cả khi đổi tên hoặc domain.
- **Duy nhất** trong phạm vi cấp phát và đối chiếu.
- **Có dạng chuẩn** để tránh một tenant có nhiều cách viết.
- **Không lộ thông tin nhạy cảm** qua chính giá trị mã.
- **Ngắn gọn hợp lý** vì xuất hiện lặp lại trong hàng triệu khóa/chỉ mục.
- **Được sinh bằng cơ chế chống va chạm**, chẳng hạn ID opaque hoặc UUID khi phù hợp.

Tenant ID là **định danh**, không phải **quyền truy cập**. Biết chuỗi `tnt_7J2` không đồng nghĩa được phép đọc dữ liệu thuộc tenant đó.

### Phân biệt tenant, user và resource ID

Ví dụ:

```text
prod:commerce:tnt_7J2:user:usr_456
prod:commerce:tnt_7J2:cart:usr_456
prod:commerce:tnt_7J2:order:ord_123
```

`tnt_7J2` là tenant; `usr_456` là một người dùng; `ord_123` là đơn hàng. Nếu user được cấp quyền với nhiều tenant thì một số dữ liệu user có thể ở namespace toàn cục, còn dữ liệu gắn với một tổ chức cần scope tenant. Cần mô hình hóa quan hệ thành viên và quyền riêng, không mặc định user luôn thuộc một tenant duy nhất.

## 6. Redis: tiền tố giúp tổ chức key string

Trong Redis, có thể lưu đơn dưới một key kiểu hash:

```redis
HSET prod:commerce:tnt_7J2:order:ord_123 status PAID total 550000
HSET prod:commerce:tnt_9Q4:order:ord_123 status PENDING total 120000

HGETALL prod:commerce:tnt_7J2:order:ord_123
```

Hai tenant cùng có `ord_123` nhưng hai key hoàn toàn khác nhau. Redis hiểu chúng là **chuỗi khóa khác nhau**, không tự áp dụng permission dựa trên chuỗi `tnt_7J2`.

### Prefix giúp quan sát, không thay chỉ mục

Muốn kiểm kê khóa theo namespace:

```redis
SCAN 0 MATCH prod:commerce:tnt_7J2:order:* COUNT 100
```

`SCAN` trả về một cursor tiếp theo cùng một lô khóa. Để duyệt đầy đủ, gọi lại với cursor cho đến khi cursor `0`. `COUNT` là gợi ý chứ không phải số phần tử bảo đảm. Trong lúc dữ liệu thay đổi, một vòng quét không tạo ảnh chụp nhất quán và có thể thấy giá trị lặp.

**Không dùng `KEYS` làm đường đọc API trên Redis lớn**: việc quét đồng bộ tất cả khóa có thể gây nghẽn. Nếu nghiệp vụ cần "20 đơn gần nhất của tenant", hãy thiết kế thêm đường truy cập có thứ tự, ví dụ sorted set chứa các order ID với điểm số thời gian, sau đó lấy thông tin đơn từ hash. Chỉ có prefix trong tên khóa chưa tạo ra chức năng phân trang hay sắp xếp hiệu quả.

### TTL và khóa cache

Ví dụ cache sản phẩm theo tenant:

```redis
SET prod:commerce:tnt_7J2:cache:product:prd_88 "{\"name\":\"Sách A\"}" EX 300
```

TTL giúp khóa cache hết hạn sau một khoảng thời gian; nó không thay thế cơ chế làm mới hoặc xóa cache khi dữ liệu thay đổi và yêu cầu nhất quán cao.

Nếu kết quả dashboard thay đổi theo tenant, user hoặc ngôn ngữ, key cache cần phân biệt những chiều thực sự làm thay đổi kết quả:

```text
prod:commerce:tnt_7J2:cache:user:usr_456:locale:vi:dashboard
prod:commerce:tnt_7J2:cache:user:usr_456:locale:en:dashboard
```

Nếu bỏ `tenantId` hoặc `locale` khi kết quả phụ thuộc các giá trị đó, ứng dụng có thể trả nhầm cache dù truy vấn database gốc đã đúng.

### Redis Cluster và hash tag

Trong Redis Cluster, dấu `:` **không khiến mọi khóa chung tiền tố được đặt cùng slot**. Redis có cơ chế hash tag sử dụng phần giữa `{...}` để tính slot:

```text
prod:commerce:{tnt_7J2:order:ord_123}:meta
prod:commerce:{tnt_7J2:order:ord_123}:items
```

Hai khóa có cùng hash tag nằm cùng slot, có thể hữu ích cho thao tác multi-key yêu cầu cùng slot. Nhưng nếu gắn cùng tag chỉ gồm tenant ID cho tất cả dữ liệu của một tenant lớn, tải của tenant có thể dồn vào một slot nóng. **Nhóm logic theo tenant** và **gom slot vật lý** là hai lựa chọn khác nhau.

## 7. DynamoDB: mô hình khóa PK/SK theo access pattern

Trong DynamoDB, partition key (PK) và sort key (SK) có vai trò trong đường truy vấn. Xét một bảng dùng chung `CommerceData`:

| PK | SK | Dữ liệu |
|---|---|---|
| `TENANT#tnt_7J2#CUSTOMER#cus_42` | `PROFILE` | Thông tin khách |
| `TENANT#tnt_7J2#CUSTOMER#cus_42` | `ORDER#2026-11-11T08:30:00Z#ord_123` | Đơn đầu |
| `TENANT#tnt_7J2#CUSTOMER#cus_42` | `ORDER#2026-11-12T10:15:00Z#ord_124` | Đơn tiếp |
| `TENANT#tnt_9Q4#CUSTOMER#cus_42` | `PROFILE` | Khách khác tenant |

Truy vấn "lấy đơn của khách `cus_42` thuộc tenant `tnt_7J2`" có thể dùng một PK và điều kiện tiền tố SK:

```javascript
import { QueryCommand } from "@aws-sdk/lib-dynamodb";

// Giả định documentClient đã được khởi tạo và tenantId đã được
// kiểm tra quyền truy cập từ server.
const tenantId = "tnt_7J2";
const customerId = "cus_42";

const result = await documentClient.send(new QueryCommand({
  TableName: "CommerceData",
  KeyConditionExpression: "#pk = :pk AND begins_with(#sk, :prefix)",
  ExpressionAttributeNames: { "#pk": "PK", "#sk": "SK" },
  ExpressionAttributeValues: {
    ":pk": "TENANT#" + tenantId + "#CUSTOMER#" + customerId,
    ":prefix": "ORDER#"
  },
  ScanIndexForward: false,
  Limit: 20
}));
```

Sort key bắt đầu bằng `ORDER#` giúp chỉ tìm các item đơn hàng trong nhóm khách đã chọn. Dùng timestamp theo một định dạng có thứ tự từ điển tương ứng với thời gian nếu muốn sắp xếp theo ngày. `Limit` giới hạn số item được đánh giá trong lượt Query; cần xử lý `LastEvaluatedKey` nếu còn trang tiếp theo.

Mô hình này được xây để **liệt kê đơn theo khách**. Nếu API chỉ biết `tenantId + orderId` mà không biết khách hàng, nó có thể cần một item lookup riêng hoặc GSI với các khóa phản ánh đường truy cập đó. Một PK/SK không tự đáp ứng tất cả câu hỏi.

### Không đặt tất cả dữ liệu của tenant lớn dưới cùng PK

```text
PK = TENANT#tnt_BIG
SK = ORDER#...
```

Cách này thuận tiện để đọc theo tenant nhưng có thể tạo tập trung tải hoặc item collection quá lớn. Có thể đưa thêm chiều khách hàng, ngày/tháng hoặc shard khi nhu cầu truy vấn cho phép. Mỗi lựa chọn thay đổi cách phân trang và tìm dữ liệu qua nhiều nhóm, nên phải dựa vào access pattern và lưu lượng thực tế.

## 8. Cassandra: tenant trong composite partition key

Apache Cassandra dùng partition key để xác định dữ liệu thuộc partition nào, và clustering columns để tổ chức thứ tự trong partition.

Ví dụ bảng liệt kê đơn theo khách:

```sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    total decimal,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Cặp `(tenant_id, customer_id)` là **partition key ghép**; `created_at` và `order_id` là clustering columns. Có thể truy vấn:

```sql
SELECT order_id, created_at, status, total
FROM orders_by_customer
WHERE tenant_id = 'tnt_7J2'
  AND customer_id = 'cus_42'
LIMIT 20;
```

Trong thiết kế này, truy vấn chỉ theo `tenant_id` sẽ không tự động là truy vấn partition key đầy đủ; Cassandra không tự biến mọi bộ lọc thành đường đọc hiệu quả. Nếu cần liệt kê đơn toàn tenant theo tháng, thường phải thiết kế bảng/đường truy cập phù hợp khác.

Ví dụ cũng cho thấy mã tenant có thể là **cột khóa riêng**, không cần ghép với dấu `:`. Điều quan trọng là tổ hợp tenant + customer được dùng nhất quán trong thao tác ghi và đọc.

## 9. MongoDB: tenant là trường và thành phần chỉ mục

Với MongoDB, có thể giữ `tenantId` là một trường riêng và dùng `_id` có tính duy nhất:

```javascript
db.orders.insertMany([
  {
    _id: "tnt_7J2:ord_123",
    tenantId: "tnt_7J2",
    orderId: "ord_123",
    customerId: "cus_42",
    status: "PAID",
    createdAt: ISODate("2026-11-11T08:30:00Z")
  },
  {
    _id: "tnt_9Q4:ord_123",
    tenantId: "tnt_9Q4",
    orderId: "ord_123",
    customerId: "cus_42",
    status: "PENDING",
    createdAt: ISODate("2026-11-12T10:15:00Z")
  }
]);
```

Hai document có cùng `orderId` nhưng khác `_id` do mã tenant. Để truy vấn theo những trường quan trọng:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);

db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1
});

// Chi tiết đơn, giới hạn trong tenant:
db.orders.findOne({ tenantId: "tnt_7J2", orderId: "ord_123" });

// Danh sách đơn của khách theo tenant:
db.orders.find({
  tenantId: "tnt_7J2",
  customerId: "cus_42"
}).sort({ createdAt: -1 }).limit(20);
```

Chỉ mục unique ghép đảm bảo không có hai document trùng cùng cặp `(tenantId, orderId)` trong collection khi các giá trị hợp lệ. Khi dùng sharding, cần xét thêm ràng buộc shard key và unique index theo cấu hình MongoDB thực tế.

**Không nên suy ra rằng đặt tenant trong một chuỗi `_id` sẽ khiến mọi truy vấn theo tenant đều nhanh.** Muốn lấy danh sách, lọc theo khách hoặc sắp xếp theo thời gian thì cần chỉ mục phù hợp với điều kiện truy vấn. Tên khóa, chỉ mục và shard key là ba quyết định liên quan nhưng không thay thế cho nhau.

## 10. Thứ tự thành phần khóa phụ thuộc mẫu truy cập

| Yêu cầu nghiệp vụ | Khóa/chỉ mục gợi ý | Đánh đổi cần cân nhắc |
|---|---|---|
| Tra một đơn theo tenant và order ID | `tenant + orderId` | Chưa hỗ trợ liệt kê theo khách |
| Liệt kê đơn của khách trong tenant | `tenant + customerId`, thứ tự ngày | Truy vấn order ID trực tiếp cần đường đọc khác |
| Lấy sự kiện trong một tháng | `tenant + yyyyMM + eventId` | Đọc nhiều tháng phải phối hợp nhiều bucket |
| Đọc giỏ hàng hiện tại | `tenant + userId + cart` | Cần tính vòng đời giỏ và TTL nếu cache |
| Đọc cấu hình của tenant | `tenant + configName` | Cần quy tắc invalidation khi đổi cấu hình |
| Tìm khách theo email trong tenant | Chỉ mục email theo tenant hoặc mapping riêng | Email có thể đổi; cần bảo vệ dữ liệu cá nhân |

Ví dụ thiết kế `tenant + yyyyMM` có ích khi truy vấn chủ yếu theo tháng, nhưng làm khó truy vấn vượt nhiều tháng. Thiết kế `tenant + customerId` phân tán theo khách hơn, nhưng nếu tenant chỉ có một khách rất lớn thì vẫn có nguy cơ tải tập trung.

Trước khi chốt cấu trúc, hãy liệt kê câu hỏi hệ thống cần trả lời: **Có biết tenant và ID trực tiếp không? Có cần danh sách theo thời gian không? Số lượng bản ghi trong mỗi tenant tăng thế nào?** Một quy ước đẹp về tên không thay được phân tích đường truy vấn.

## 11. Khóa quá dài, điểm nóng và phân vùng

Định danh tenant có hai mặt: nó giúp phân tách logic nhưng cũng có thể ảnh hưởng phân bố vật lý nếu được dùng như toàn bộ partition key.

### Hot partition

Nếu một tenant có khối lượng vượt trội, việc đặt tất cả đơn của tenant dưới một PK:

```text
PK = TENANT#tnt_BIG
SK = ORDER#...
```

có thể trở thành điểm nóng. Tùy công nghệ và yêu cầu đọc, có thể thêm `customerId`, bucket thời gian hoặc shard có kiểm soát. Tuy nhiên:

- Bucket thời gian làm truy vấn theo một kỳ thuận tiện, nhưng đọc toàn lịch sử phải tập hợp nhiều bucket.
- Sharding tăng khả năng phân phối ghi, nhưng truy vấn cần biết shard hoặc truy vấn nhiều nơi.
- Đặt khách hàng vào partition key phù hợp đọc theo khách, không tự giải quyết việc tổng hợp toàn tenant.

### Độ dài khóa

Một prefix dài lặp lại ở hàng triệu bản ghi tăng dung lượng lưu trữ, băng thông và có thể làm chỉ mục lớn hơn. Dùng ID ổn định, gọn và tên domain hợp lý; không tối giản đến mức mất khả năng phân biệt hoặc khó vận hành.

### Noisy neighbor

Hai tenant có thể cùng hạ tầng nhưng khối lượng khác rất xa. Prefix bảo đảm phân biệt danh tính logic, **không bảo đảm chia tài nguyên công bằng**. Cần quan sát tải theo tenant, độ phân bố partition, cache hit rate, giới hạn sử dụng và phương án cô lập tenant lớn khi nghiệp vụ cần.

## 12. Bảo mật: namespace không thay thế phân quyền

Điểm then chốt: **đặt tenant ID trong khóa không đồng nghĩa khóa được bảo vệ khỏi tenant khác**.

Ví dụ minh họa thiết kế không an toàn:

```java
// Sai nếu chưa xác minh header có thuộc quyền của user.
String key = "prod:commerce:"
        + request.getHeader("X-Tenant-Id")
        + ":order:"
        + orderId;
```

Người dùng có thể sửa header hoặc tham số URL. Nếu server cứ dùng giá trị đó để đọc, ứng dụng có thể tạo lỗ hổng truy cập chéo tenant.

Luồng thiết kế đúng:

```text
Request
   |
   v
Xác thực danh tính người gọi
   |
   v
Xác định tenant hoạt động, kiểm tra membership và quyền
   |
   v
Truyền tenant context đã xác minh vào service
   |
   v
Xây khóa / điều kiện truy vấn có tenant
   |
   v
Kiểm tra quyền trên tài nguyên rồi thao tác dữ liệu
```

Nếu người dùng tham gia nhiều tenant, server có thể cho phép chọn tenant nhưng phải kiểm tra quyền mỗi lần, thay vì tin rằng ID do client đưa vào là đáng tin cậy.

Ngoài kiểm tra ở API, nên áp dụng lớp bảo vệ phù hợp tại repository, database credential, IAM/ACL hoặc phân tách cơ sở dữ liệu khi yêu cầu cô lập cao. Tại các đường cache, queue, job nền và export, tenant context cũng phải được giữ chính xác; một luồng bỏ điều kiện tenant có thể làm lộ dữ liệu dù các luồng khác hoạt động đúng.

Đặc biệt, nếu cache có dữ liệu thay đổi theo tenant hoặc quyền của user, cần bảo đảm cache key đủ chiều phân biệt hoặc sử dụng cơ chế cô lập tương đương.

## 13. Tạo khóa tập trung bằng Java

Để tránh mỗi controller tự ghép key theo một cách, có thể đặt logic vào một **key factory**. Ví dụ đơn giản:

```java
import java.util.Objects;
import java.util.regex.Pattern;

public final class KeyFactory {
    private static final Pattern SAFE_SEGMENT =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private final String environment;
    private final String application;

    public KeyFactory(String environment, String application) {
        this.environment = checked(environment);
        this.application = checked(application);
    }

    public String orderKey(String tenantId, String orderId) {
        return String.join(
                ":",
                environment,
                application,
                checked(tenantId),
                "order",
                checked(orderId)
        );
    }

    public String cartKey(String tenantId, String userId) {
        return String.join(
                ":",
                environment,
                application,
                checked(tenantId),
                "cart",
                checked(userId)
        );
    }

    private static String checked(String segment) {
        Objects.requireNonNull(segment, "key segment must not be null");
        if (!SAFE_SEGMENT.matcher(segment).matches()) {
            throw new IllegalArgumentException("Invalid key segment");
        }
        return segment;
    }
}
```

Sử dụng:

```java
KeyFactory keys = new KeyFactory("prod", "commerce");

String orderKey = keys.orderKey("tnt_7J2", "ord_123");
// prod:commerce:tnt_7J2:order:ord_123

String cartKey = keys.cartKey("tnt_7J2", "usr_456");
// prod:commerce:tnt_7J2:cart:usr_456
```

Lớp này chỉ **kiểm tra cú pháp** và dựng chuỗi. Nó không xác thực rằng caller có quyền với `tnt_7J2`. Ứng dụng phải truyền tenant ID lấy từ ngữ cảnh bảo mật đã xác minh. Ví dụ giả định ID tuân theo allowlist; nếu hệ thống có các định dạng ID khác, cần thiết kế bộ mã hóa segment tương ứng.

Tập trung hóa hàm tạo key giúp tên khóa nhất quán, hạn chế lỗi quên tenant, đơn giản hóa instrumentation và chuẩn bị tốt hơn cho các lần đổi quy ước.

## 14. Chuyển đổi định dạng khóa khi hệ thống phát triển

Giả sử ứng dụng ban đầu chỉ có một khách hàng:

```text
order:ord_123
```

Khi chuyển sang multi-tenant, muốn dùng:

```text
prod:commerce:tnt_7J2:order:ord_123
```

Thay hàm tạo khóa không tự di chuyển dữ liệu đã ghi. Một kế hoạch migration cần:

1. **Kiểm kê** nơi đọc/ghi/xóa key, cả consumer sự kiện và job chạy nền.
2. **Xác định quyền sở hữu dữ liệu cũ** bằng nguồn đáng tin cậy. Không tự đoán tenant từ mã tài nguyên nếu trước đó mã không đủ để phân biệt.
3. **Backfill** hoặc thiết kế giai đoạn ghi cả khóa cũ/mới với cơ chế tránh mất cập nhật.
4. **Chuyển luồng đọc** sang khóa mới; nếu dùng fallback cũ phải bảo đảm fallback không đọc nhầm dữ liệu tenant khác.
5. **Đối soát** số lượng, nội dung, phiên bản và quá trình invalidation.
6. **Ngừng đọc/ghi khóa cũ** rồi xóa dữ liệu cũ có kiểm soát.

Có thể đưa phiên bản vào cấu trúc:

```text
v1:prod:commerce:tnt_7J2:order:ord_123
v2:prod:commerce:tnt_7J2:order:ord_123
```

Version prefix giúp phân biệt định dạng, không tự thực hiện migration. Với cache TTL ngắn, có thể cho khóa cũ tự hết hạn nếu nghiệp vụ chấp nhận. Với dữ liệu nguồn, phải bảo đảm chuyển đổi đúng và không mất dữ liệu.

## 15. Vận hành theo tenant

### Theo dõi hệ thống

Namespace hỗ trợ phân tích khóa theo ứng dụng hoặc loại tài nguyên. Nhưng không nên đưa mọi `tenantId`, `userId`, `orderId` vào nhãn metric dạng cardinality không giới hạn: số chuỗi nhãn lớn có thể làm hệ quan sát quá tải. Thay vào đó, ưu tiên metric tổng hợp theo loại thao tác và cơ chế drill-down có kiểm soát khi cần phân tích một tenant cụ thể.

Nếu log có tên khóa đầy đủ, cần chú ý thông tin cá nhân hoặc định danh bị lộ qua log, debug tool và hệ thống bên thứ ba. Hạn chế ghi nguyên khóa khi không cần; bảo vệ quyền xem log và thời gian lưu log.

### Xóa và xuất dữ liệu tenant

Việc có mã tenant trong khóa giúp truy tìm phạm vi nhưng không có nghĩa chỉ cần quét một prefix là xóa hoặc xuất được toàn bộ dữ liệu tenant. Dữ liệu có thể nằm ở nhiều collection, bảng chỉ mục, cache, event, object storage và bản sao lưu. Quản trị dữ liệu theo tenant cần danh mục các nơi lưu dữ liệu và cơ chế retention, export, deletion rõ ràng.

### Chuyển tenant sang hạ tầng riêng

Khi một tenant phát triển lớn hoặc có yêu cầu cô lập đặc biệt, ID ổn định cùng cách truy vấn theo tenant hỗ trợ kiểm kê và di chuyển. Tuy vậy, tính khả thi phụ thuộc mô hình lưu trữ, định danh quan hệ và cơ chế bảo toàn nhất quán trong lúc chuyển, chứ không chỉ tên prefix.

## 16. Bài tập tình huống

Một ứng dụng quản lý lịch hẹn phục vụ nhiều phòng khám; mỗi phòng khám là một tenant. Một user có thể làm việc tại nhiều phòng khám. Các yêu cầu:

1. Lấy lịch hẹn theo tenant và appointment ID.
2. Liệt kê lịch hẹn của một bác sĩ trong một ngày.
3. Cache dashboard theo tenant, user và ngôn ngữ.
4. Cho phép phòng khám đổi tên mà không làm mất liên kết tới lịch hẹn cũ.

Một quy ước khóa logic tham khảo:

```text
prod:clinic:tnt_A1:appointment:apt_1001
prod:clinic:tnt_A1:doctor:doc_17:day:2026-11-14:appointments
prod:clinic:tnt_A1:cache:user:usr_09:locale:vi:dashboard
prod:clinic:tnt_A1:cache:user:usr_09:locale:en:dashboard
```

Khóa thứ hai chỉ mô tả đường truy cập danh sách. Để truy vấn hiệu quả, cần quyết định cấu trúc vật lý tương ứng: sorted set, secondary index hoặc PK/SK tùy database và nhu cầu cập nhật.

Hãy tự trả lời:

- Nếu hai tenant đều có lịch hẹn `apt_1001`, các khóa có va chạm không?
- Vì sao cache tiếng Việt và tiếng Anh cần hai khóa khi nội dung hiển thị khác nhau?
- Nếu user tự đổi tenant ID trong request, backend phải xác minh điều gì?
- Nếu một bác sĩ có nhiều năm lịch hẹn, chia nhóm theo ngày giúp và gây hạn chế gì?
- Khi phòng khám đổi tên, vì sao mã `tnt_A1` không nên thay đổi?

Giải thích: tenant ID làm phạm vi định danh khác nhau; locale là chiều ảnh hưởng kết quả; quyền tenant phải xác minh trên server; nhóm theo ngày tối ưu truy vấn một ngày nhưng cần gom nhiều nhóm khi truy vấn dài hơn; tên hiển thị không phải định danh kỹ thuật bất biến.

## 17. Ghi nhớ

**Prefix** giúp nhận diện nhóm khóa, **namespace** xác lập phạm vi đặt tên và **tenant ID** chỉ ra dữ liệu thuộc khách hàng/tổ chức nào. Một khóa bền vững cần tránh va chạm, ổn định khi thông tin hiển thị thay đổi, dễ tạo nhất quán và phục vụ mẫu truy vấn chủ đạo.

Với Redis, cấu trúc này thường xuất hiện trong key string; với DynamoDB và Cassandra, những thành phần tương tự có thể tham gia vào khóa phân vùng và thứ tự truy vấn; với MongoDB, tenant thường là trường được lọc và đánh chỉ mục. Bất kể hệ nào, đưa tenant vào khóa **không thay thế kiểm tra quyền**, cũng không tự đảm bảo phân bố tải đều.

Khi chuẩn bị một loại khóa mới, hãy hỏi: **Dữ liệu thuộc môi trường, ứng dụng và tenant nào? ID có bất biến không? Truy vấn thường bắt đầu từ trường nào? Cấu trúc có tạo điểm nóng hoặc khiến các thao tác theo tenant trở nên khó khăn không?** Trả lời được các câu hỏi đó là nền tảng để thiết kế khóa NoSQL nhất quán và có thể mở rộng.
