# Chỉ mục phụ cục bộ hoặc toàn cục theo kiến trúc từng hệ

Trong cơ sở dữ liệu NoSQL, dữ liệu thường được phân tán theo **khóa phân vùng** (*partition key*), **shard** hoặc một quy tắc định tuyến tương tự. Cách tổ chức đó giúp hệ thống tìm nhanh dữ liệu khi biết đúng khóa, nhưng không có nghĩa mọi thuộc tính khác đều có một đường truy cập hiệu quả.

Giả sử hệ thống thương mại điện tử lưu đơn hàng theo khách hàng:

~~~text
Partition: CUSTOMER#C42
  ├── ORDER#O1001 → status=PAID,    createdAt=2026-11-01
  ├── ORDER#O1002 → status=SHIPPED, createdAt=2026-11-04
  └── ORDER#O1003 → status=PAID,    createdAt=2026-11-08

Partition: CUSTOMER#C93
  ├── ORDER#O1004 → status=PAID,    createdAt=2026-11-02
  └── ORDER#O1005 → status=FAILED,  createdAt=2026-11-10
~~~

Hai yêu cầu khác nhau:

1. “Lấy 20 đơn mới nhất của khách hàng C42.” Ứng dụng đã biết khóa khách hàng, nên thường có thể định tuyến đến một nhóm dữ liệu nhỏ.
2. “Lấy tất cả đơn `PAID` của cửa hàng S7 trong ngày hôm nay.” Ứng dụng **không biết khách hàng nào**. Nếu chỉ có đường truy cập theo khách hàng, truy vấn có thể phải chạm rất nhiều partition.

**Chỉ mục phụ** (*secondary index*) là một cách bổ sung đường tra cứu theo thuộc tính không phải khóa truy cập chính, chẳng hạn `status`, `shopId` hoặc `email`. Tuy nhiên, chỉ mục phụ **cục bộ** (*local*) và chỉ mục phụ **toàn cục** (*global*) có cách tổ chức, phạm vi truy vấn, chi phí và bảo đảm khác nhau.

Bài học trình bày cách hiểu hai khái niệm theo **ranh giới phân vùng thực tế**, so sánh những hệ tiêu biểu như **Amazon DynamoDB**, **Apache Cassandra**, **MongoDB triển khai sharding** và **ScyllaDB**, rồi hướng dẫn quyết định khi nào dùng chỉ mục, khi nào cần mô hình đọc chuyên dụng.

> **Lưu ý thuật ngữ:** “Local secondary index” và “Global secondary index” là tên tính năng chính thức trong một số hệ như DynamoDB; ở các hệ khác, “local/global” có thể mô tả **cách triển khai vật lý** hoặc **phạm vi tra cứu logic**, chứ không phải hai loại index có API giống hệt nhau. Luôn xác định rõ “cục bộ theo cái gì”: một partition, một shard, một node hay một vùng triển khai.

## 1. Bắt đầu từ khóa chính và đường truy cập

Giả sử tập đơn hàng có các thuộc tính:

~~~json
{
  "orderId": "O1003",
  "tenantId": "T17",
  "customerId": "C42",
  "shopId": "S7",
  "status": "PAID",
  "createdAt": "2026-11-08T10:20:00Z",
  "totalMinor": 125000,
  "currency": "VND"
}
~~~

Một mô hình lưu theo khách hàng có thể chọn:

~~~text
Primary partition key = (tenantId, customerId)
Sort/clustering key    = (createdAt DESC, orderId)
~~~

Đường đọc chính:

~~~text
tenantId + customerId
          │
          ▼
Định vị partition
          │
          ▼
Đọc các đơn theo createdAt
~~~

Đây là một **access pattern có khóa định vị rõ ràng**.

Nhưng nếu cần đọc đơn theo `shopId + status + createdAt` thì khóa hiện tại không khớp. Một hệ quản trị có thể:

- Sử dụng **secondary index** được thiết kế phù hợp.
- Tra cứu một cấu trúc dẫn xuất `orders_by_shop_status`.
- Quét và lọc nhiều partition, nếu workload nhỏ hoặc là tác vụ batch.
- Chuyển truy vấn sang hệ tìm kiếm/phân tích phù hợp nếu bộ lọc rất linh hoạt.

### Khái niệm sơ bộ

| Thành phần | Vai trò |
| --- | --- |
| **Primary key / partition key** | Xác định bản ghi hoặc phân vùng dữ liệu trong cấu trúc chính |
| **Sort key / clustering key** | Quy định tổ chức và truy cập theo thứ tự trong một phạm vi khóa |
| **Secondary index** | Cho phép tìm theo đường truy cập khác với đường chính |
| **Index entry** | Mục ánh xạ từ giá trị tra cứu đến bản ghi hoặc khóa của bản ghi |
| **Partition/shard** | Đơn vị phân phối dữ liệu; phạm vi cụ thể tùy DBMS |
| **Coordinator/query router** | Thành phần quyết định cần hỏi partition/shard nào và hợp nhất kết quả |

Chỉ mục giúp **tìm đúng tập dữ liệu**; nó không tự trả lời mọi câu hỏi về thứ tự, tính nhất quán, quyền truy cập hoặc khả năng phân trang.

## 2. Chỉ mục phụ cục bộ là gì?

Một **chỉ mục cục bộ** thường giữ các mục chỉ mục gắn với **phạm vi dữ liệu gốc** của một partition, shard hoặc node. Khi đó, tìm theo thuộc tính phụ có thể hiệu quả **nếu truy vấn đã biết phạm vi cục bộ cần tìm**.

Ví dụ khái niệm:

~~~text
Primary data, chia theo customerId

Partition A: CUSTOMER#C42
  O1001 status=PAID
  O1002 status=SHIPPED
  O1003 status=PAID

Local index của A:
  PAID    → O1001, O1003
  SHIPPED → O1002

Partition B: CUSTOMER#C93
  O1004 status=PAID
  O1005 status=FAILED

Local index của B:
  PAID   → O1004
  FAILED → O1005
~~~

Nếu hỏi:

> “Những đơn PAID của khách C42?”

ứng dụng có thể định vị partition A và dùng chỉ mục cục bộ tương ứng.

Nếu hỏi:

> “Mọi đơn PAID của tất cả khách hàng?”

ứng dụng chưa biết nên tìm A, B hay hàng triệu partition khác. Tùy khả năng DBMS, coordinator có thể **fan-out** tới nhiều nơi, hoặc truy vấn không được hỗ trợ trực tiếp nếu thiếu khóa phân vùng.

### Ưu điểm thường thấy

- Giữ cấu trúc index gần dữ liệu liên quan.
- Một truy vấn đã biết partition gốc có thể tránh tìm khắp cụm.
- Dễ duy trì tính liên hệ giữa dữ liệu nguồn và các mục index trong cùng phạm vi, tùy cơ chế DBMS.
- Phù hợp khi **đường truy cập phụ vẫn đi kèm khóa nhóm chính**.

### Giới hạn thường gặp

- Truy vấn **không biết partition key** có thể rất tốn kém.
- Chỉ mục đặt cục bộ không tự tạo một danh sách toàn hệ thống có thể duyệt theo `status` hoặc `email`.
- Hiệu quả phụ thuộc số partition cần hỏi, độ chọn lọc và phân bố dữ liệu.
- Một partition lớn hoặc nóng vẫn có thể gây giới hạn riêng.

Không được hiểu rằng “local index luôn nằm trong đúng một file” hoặc “local index không thể phục vụ truy vấn toàn cụm”. Đây là **mô tả tổ chức logic**; DBMS có thể dùng nhiều cấu trúc trên đĩa và cơ chế phân phối truy vấn phức tạp hơn.

## 3. Chỉ mục phụ toàn cục là gì?

Một **chỉ mục toàn cục** tổ chức đường tra cứu theo **giá trị thuộc tính phụ trên phạm vi rộng hơn partition gốc**. Nó có thể được phân vùng **theo khóa chỉ mục mới**, độc lập với cách phân vùng bảng/collection nguồn.

Ví dụ:

~~~text
Primary data:
  CUSTOMER#C42 → O1001, O1002, O1003
  CUSTOMER#C93 → O1004, O1005

Global access path:
  STATUS#PAID    → O1001, O1003, O1004
  STATUS#SHIPPED → O1002
  STATUS#FAILED  → O1005
~~~

Khi hỏi “các đơn PAID”, hệ có thể bắt đầu từ cấu trúc được khóa theo `STATUS#PAID`, không cần biết từng `customerId`.

### “Toàn cục” không có nghĩa một node lưu toàn bộ chỉ mục

Một global secondary index có thể **tự được phân tán** thành nhiều partition hoặc shard. Tính “toàn cục” nói đến **khả năng lập đường truy cập độc lập với partition của dữ liệu gốc**, không phải việc dồn mọi index entry vào một máy.

~~~text
Base partitions                    Global index partitions
  Customer A ─┐                    STATUS#PAID ──> base record keys
  Customer B ─┼─ index updates ──> STATUS#NEW  ──> base record keys
  Customer C ─┘                    STATUS#FAIL ──> base record keys
~~~

### Các đánh đổi thường gặp

**Lợi ích:**

- Truy vấn theo thuộc tính phụ có thể có đường định tuyến riêng, không cần quét mọi partition gốc.
- Phù hợp khi nhiều pattern quan trọng có khóa đầu vào khác nhau.
- Có thể tổ chức thứ tự/nhóm dữ liệu độc lập với bảng chính.

**Chi phí:**

- Ghi một bản ghi nguồn có thể phát sinh ghi/cập nhật/xóa index entry.
- Cần dung lượng lưu trữ và khả năng phục hồi index.
- Có thể có độ trễ đồng bộ giữa dữ liệu chính và index.
- Khóa chỉ mục có phân bố lệch có thể tạo **hot index partition**.
- Nếu chỉ mục chỉ lưu khóa tham chiếu, truy vấn còn phải đọc bản ghi nguồn để lấy field khác.
- Việc xóa, đổi giá trị trường được index và rebuild cần cơ chế chính xác.

**Không nên đánh đồng global index với truy vấn nhất quán mạnh.** Mức nhất quán phụ thuộc triển khai cụ thể, không được suy ra từ tên “global”.

## 4. Đọc hai loại index bằng cùng một access pattern

Giả sử đơn hàng có:

~~~text
Base partition key: customerId
Field cần tìm: status
~~~

| Câu hỏi | Với index cục bộ theo khách | Với global index theo status |
| --- | --- | --- |
| Đơn PAID của C42 | Có thể định vị partition C42 rồi lọc/index | Cần thêm điều kiện C42 hoặc lọc kết quả theo thiết kế |
| Đơn PAID của toàn hệ | Có thể phải hỏi nhiều partition | Có đường truy cập theo status |
| 20 đơn PAID mới nhất | Cần đường có thứ tự phù hợp trong từng nhóm và merge | Cần global index có sort key theo thời gian |
| Số đơn PAID theo từng shop | Có thể cần quét/gộp nhiều nhóm | Có thể vẫn cần index/rollup theo shop và status |
| Đơn PAID nhưng chỉ trong tenant T17 | Phải giới hạn quyền và phạm vi tenant | Nên xem tenant là một phần khóa truy cập để tránh lọc rộng |

Một chỉ mục theo `status` **chưa chắc** tối ưu truy vấn `shopId + status + createdAt`. Khóa và thứ tự của chỉ mục phải xuất phát từ **mẫu truy cập đầy đủ**, không chỉ một trường lọc.

Ví dụ khóa phụ đáng cân nhắc:

~~~text
Index partition key = (tenantId, shopId, status)
Index sort key      = (createdAt DESC, orderId)
~~~

Khi đó query:

~~~text
FindRecentOrders(
  tenantId=T17,
  shopId=S7,
  status=PAID,
  limit=50
)
~~~

có đường truy cập rõ. Nếu chỉ index theo `status` mà mọi đơn của hệ thống thường ở `PAID`, index có thể có độ chọn lọc rất thấp và bị nóng.

## 5. Cẩn thận: local/global được định nghĩa theo kiến trúc từng hệ

Những cách dùng từ “local” có thể khác nhau:

| Cách dùng từ | “Local” nằm ở đâu? | “Global” có thể có nghĩa gì? |
| --- | --- | --- |
| **DynamoDB LSI/GSI** | LSI giữ **cùng partition key** với bảng cơ sở, thay sort key | GSI có partition/sort key riêng với bảng chính |
| **Cassandra secondary index** | Mỗi node lưu chỉ mục cho phần dữ liệu nó sở hữu | Truy vấn theo thuộc tính phụ trên toàn cụm có thể cần liên hệ nhiều node |
| **MongoDB sharded cluster** | Các index được lưu trên shard cùng dữ liệu của shard | Một truy vấn logic toàn collection có thể fan-out; không mặc định có một index tập trung toàn cục |
| **ScyllaDB local/global secondary index** | Local index hỗ trợ tìm trong phạm vi base partition được biết | Global index tổ chức đường tra cứu theo indexed value độc lập hơn với base partition |
| **Search engine phân tán** | Mỗi shard có inverted index của tài liệu trên shard đó | Tìm kiếm toàn bộ index logic bằng coordinator hỏi các shard và hợp nhất kết quả |

Vì vậy, trước khi so sánh hiệu năng cần hỏi:

1. **Index được lưu ở đâu và phân vùng theo khóa gì?**
2. **Query có phải cung cấp partition key của dữ liệu nguồn không?**
3. **Coordinator cần liên hệ bao nhiêu partition/shard/node?**
4. **Index update được đồng bộ và có bảo đảm nhất quán gì?**
5. **Index có đủ field để trả kết quả hay phải đọc lại nguồn?**

Đó là những câu hỏi có ý nghĩa hơn việc chỉ hỏi “hệ này có global index hay không?”.

## 6. DynamoDB: sự phân biệt LSI và GSI rất rõ

Trong **Amazon DynamoDB**, local secondary index (**LSI**) và global secondary index (**GSI**) là **hai loại secondary index chính thức**, khác nhau ở khóa, thời điểm tạo, tính nhất quán và cách truy cập dữ liệu.

Giả sử bảng `Orders` được thiết kế để đọc đơn theo khách hàng.

### 6.1. Khóa của bảng cơ sở

~~~text
Table: Orders

Partition key: PK
Sort key:      SK

Ví dụ item:
  PK          = "TENANT#T17#CUSTOMER#C42"
  SK          = "ORDER#O1003"
  orderId     = "O1003"
  createdAt   = "2026-11-08T10:20:00Z"
  shopId      = "S7"
  status      = "PAID"
  totalMinor  = 125000
  currency    = "VND"
~~~

Với thiết kế này, bảng chính có thể tìm item bằng `PK + SK` và truy vấn các item trong một `PK`. Tuy nhiên, `SK = ORDER#...` không sắp xếp đơn theo `createdAt`.

### 6.2. LSI: cùng partition key, sort key khác

Ta muốn:

> “Lấy các đơn hàng của C42, sắp theo thời gian tạo.”

Một LSI có thể dùng:

~~~text
LSI: ByCustomerCreatedAt

Partition key: PK       (giống bảng cơ sở)
Sort key:      createdAt
~~~

Sơ đồ:

~~~text
Base table, cùng PK của C42:
  PK=TENANT#T17#CUSTOMER#C42
    SK=ORDER#O1001
    SK=ORDER#O1002
    SK=ORDER#O1003

LSI ByCustomerCreatedAt, cùng PK:
  PK=TENANT#T17#CUSTOMER#C42
    createdAt=2026-11-01... → O1001
    createdAt=2026-11-04... → O1002
    createdAt=2026-11-08... → O1003
~~~

Điểm quan trọng: **LSI không đổi partition key**. Nếu hỏi “đơn mới nhất của tất cả khách hàng”, LSI này **không cung cấp một partition key mới theo thời gian cho toàn hệ**.

Ví dụ truy vấn dạng ý tưởng với DynamoDB SDK:

~~~javascript
const params = {
  TableName: "Orders",
  IndexName: "ByCustomerCreatedAt",
  KeyConditionExpression: "PK = :pk",
  ExpressionAttributeValues: {
    ":pk": "TENANT#T17#CUSTOMER#C42"
  },
  ScanIndexForward: false,
  Limit: 20
};
~~~

Đây là **pseudocode theo kiểu DocumentClient**, không phải toàn bộ chương trình SDK chạy sẵn. Trong DynamoDB thực tế, phải dùng đúng client, kiểu marshalling tham số, tên index và logic phân trang qua `LastEvaluatedKey`.

Lợi ích: một truy vấn đã biết khách hàng có thể dùng sort key khác mà vẫn giữ phạm vi khóa khách hàng.

### 6.3. GSI: một đường định tuyến khác

Giờ ứng dụng cần:

> “Shop S7 xem 50 đơn PAID mới nhất trong tenant T17.”

Các đơn của shop nằm rải rác giữa nhiều customer `PK`. LSI không giải quyết trực tiếp việc thiếu khóa khách hàng.

Ta tạo một GSI với các thuộc tính khóa mới:

~~~text
GSI: ByShopStatusCreatedAt

GSI partition key: GSI1PK
  = "TENANT#T17#SHOP#S7#STATUS#PAID"

GSI sort key: GSI1SK
  = "2026-11-08T10:20:00Z#O1003"
~~~

Một item nguồn phải chứa những trường khóa của GSI để được lập vào index theo thiết kế này:

~~~json
{
  "PK": "TENANT#T17#CUSTOMER#C42",
  "SK": "ORDER#O1003",
  "orderId": "O1003",
  "shopId": "S7",
  "status": "PAID",
  "createdAt": "2026-11-08T10:20:00Z",
  "GSI1PK": "TENANT#T17#SHOP#S7#STATUS#PAID",
  "GSI1SK": "2026-11-08T10:20:00Z#O1003",
  "totalMinor": 125000,
  "currency": "VND"
}
~~~

Truy vấn GSI:

~~~javascript
const params = {
  TableName: "Orders",
  IndexName: "ByShopStatusCreatedAt",
  KeyConditionExpression: "GSI1PK = :pk",
  ExpressionAttributeValues: {
    ":pk": "TENANT#T17#SHOP#S7#STATUS#PAID"
  },
  ScanIndexForward: false,
  Limit: 50
};
~~~

GSI được phân vùng theo **GSI partition key**. Nó không cần cùng `PK` với bảng nguồn. Đây là nghĩa cụ thể của “global” trong DynamoDB, không phải một chỉ mục vật lý đặt trên đúng một máy.

### 6.4. Bảng đối chiếu DynamoDB LSI và GSI

| Tiêu chí | LSI | GSI |
| --- | --- | --- |
| Partition key | **Bắt buộc giống bảng cơ sở** | Có thể **khác bảng cơ sở** |
| Sort key | Khác sort key cơ sở để có thứ tự/đường truy cập bổ sung | Có thể chọn sort key riêng hoặc không có sort key |
| Tạo index | Phải khai báo khi tạo bảng | Có thể tạo khi tạo bảng hoặc bổ sung sau theo khả năng dịch vụ |
| Đọc nhất quán mạnh | Có thể yêu cầu strong consistency theo hỗ trợ của DynamoDB | **Không hỗ trợ strongly consistent reads; đọc eventually consistent** |
| Phạm vi query | Trong phạm vi partition key bảng nguồn | Theo partition key GSI, có thể gom item từ nhiều base partitions |
| Thuộc tính không được project | Có thể được lấy từ bảng cơ sở, nhưng có thêm chi phí | Không thể yêu cầu trực tiếp thuộc tính không có trong GSI thông qua truy vấn GSI |
| Dung lượng/giới hạn | Liên quan **giới hạn 10 GiB cho item collection** theo partition key khi bảng có LSI | Có cách phân phối và giới hạn theo GSI; không dùng giới hạn item collection LSI theo cùng nghĩa |
| Ghi | Bảo trì theo cơ chế gắn với bảng nguồn | Có ghi/cập nhật index và tài nguyên index liên quan |

**Chi tiết quan trọng về giới hạn LSI:** với bảng DynamoDB có LSI, một *item collection* (các item của cùng một partition key và các mục LSI tương ứng) chịu giới hạn kích thước 10 GiB theo quy định dịch vụ. Không nên chọn một partition key rất lớn, như `TENANT#all-orders`, rồi kỳ vọng LSI cho phép tăng trưởng vô hạn.

### 6.5. Tính nhất quán: GSI có thể trễ sau ghi

Giả sử một đơn chuyển từ `NEW` sang `PAID`:

~~~text
T0: Base table update status=PAID được chấp nhận
T1: GSI đang đồng bộ thay đổi
T2: Query GSI theo STATUS#PAID có thể chưa thấy đơn
T3: GSI bắt kịp thay đổi
~~~

DynamoDB GSI được cập nhật theo cơ chế **bất đồng bộ/eventual consistency**. Vì vậy, không dùng kết quả GSI vừa đọc làm bằng chứng tuyệt đối rằng một khoản thanh toán **chưa xảy ra** ngay sau khi base table vừa cập nhật.

Những tác vụ yêu cầu đọc sau ghi nhất quán mạnh cần xác định **nguồn có thẩm quyền và đường đọc phù hợp**, thay vì chỉ dựa vào GSI.

### 6.6. Projection của index khác ProjectionExpression của query

DynamoDB cho phép chọn **thuộc tính lưu trong secondary index**, với các lựa chọn như:

- `KEYS_ONLY`: chủ yếu các khóa cần thiết.
- `INCLUDE`: thêm một số thuộc tính không phải khóa được chọn.
- `ALL`: bao gồm toàn bộ thuộc tính item theo khả năng của index.

Đây là **index projection**, ảnh hưởng kích thước index, khả năng phục vụ query trực tiếp và chi phí cập nhật.

Trong khi đó, **`ProjectionExpression`** ở một lời gọi đọc là yêu cầu chọn thuộc tính **trả về cho caller**. Chúng là hai việc khác nhau:

~~~text
Index projection:
  Những thuộc tính nào được sao vào chỉ mục?

Query ProjectionExpression:
  Trong những thuộc tính truy cập được, trả cho caller các field nào?
~~~

Với **LSI**, DynamoDB có thể đọc thêm từ bảng nguồn nếu query cần thuộc tính không project vào LSI, kéo theo chi phí đọc. Với **GSI**, query trên GSI không tự fetch các thuộc tính chưa được project từ base table; ứng dụng cần đường đọc khác nếu thiếu thông tin.

Đừng đặt `ALL` cho mọi GSI chỉ vì tiện. Index có thể phình to và tăng chi phí ghi/lưu trữ; cần so với các field thực sự dùng trong access patterns.

### 6.7. GSI và tính thưa của dữ liệu

Một GSI chỉ chứa item có những thuộc tính khóa index cần thiết. Nếu một loại item không có `GSI1PK`, item đó không xuất hiện trong GSI theo đường khóa này.

Điều này cho phép **sparse GSI**, ví dụ chỉ đặt các thuộc tính khóa GSI cho đơn ở trạng thái cần tác vụ quản trị:

~~~text
Base:
  O1 status=PAID,    GSI1PK="..."
  O2 status=SHIPPED, không có GSI1PK
  O3 status=PAID,    GSI1PK="..."

GSI chỉ chứa O1 và O3 theo đường GSI1PK.
~~~

Nhưng khi một item chuyển trạng thái, ứng dụng phải **thêm, cập nhật hoặc bỏ đúng thuộc tính khóa GSI** để tránh index phản ánh sai tiêu chí nghiệp vụ. Ngoài ra, sparse index vẫn có tính eventual khi đồng bộ.

## 7. Cassandra: secondary index thường gắn với dữ liệu trên từng node

Trong **Apache Cassandra**, cách hiểu về secondary index khác với LSI/GSI của DynamoDB.

Dữ liệu Cassandra được phân phối theo token của partition key; các node sở hữu những phạm vi dữ liệu theo topology và replication. Các cơ chế secondary indexing của Cassandra, gồm **secondary index truyền thống (2i)** và **Storage-Attached Indexing (SAI)** ở phiên bản/hệ triển khai hỗ trợ, gắn với cách dữ liệu được lưu cục bộ trên node.

### 7.1. Bảng nguồn theo khách hàng

Ví dụ CQL:

~~~sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    shop_id text,
    status text,
    total_minor bigint,
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

Truy vấn đã biết partition key:

~~~sql
SELECT order_id, created_at, status, total_minor
FROM orders_by_customer
WHERE tenant_id = 'T17'
  AND customer_id = 'C42'
LIMIT 20;
~~~

Truy vấn này đi theo đường partition key và clustering, không cần chỉ mục phụ để đáp ứng access pattern cơ bản.

### 7.2. Secondary index theo status có thể trông thuận tiện

Ví dụ cú pháp của secondary index truyền thống:

~~~sql
CREATE INDEX orders_status_idx
ON orders_by_customer (status);
~~~

Sau đó có thể xuất hiện câu hỏi:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders_by_customer
WHERE status = 'PAID';
~~~

**Vấn đề kiến trúc:** `status` có thể xuất hiện trong hàng triệu partition trên nhiều node. Việc có một local index trên các node **không đồng nghĩa coordinator biết ngay một partition duy nhất chứa toàn bộ các đơn PAID**.

Nếu truy vấn không có điều kiện giúp định vị partition chính, Cassandra có thể phải **phân phối truy vấn tới nhiều node** và gom kết quả. Chi phí phụ thuộc index implementation, partition distribution, độ chọn lọc và quy mô cluster.

### Vì sao status thường là chỉ mục khó?

`status` có thể chỉ có các giá trị:

~~~text
NEW, PAID, PACKING, SHIPPED, CANCELLED, FAILED
~~~

Nếu 40% đơn ở trạng thái `PAID`, điều kiện `status='PAID'` có **độ chọn lọc thấp**: vẫn có rất nhiều item phù hợp. Một index không biến việc trả hàng triệu đơn thành thao tác rẻ.

Ngược lại, điều kiện một giá trị rất hiếm có thể chọn lọc hơn, nhưng câu hỏi **có phải fan-out toàn cluster không** vẫn quan trọng.

### 7.3. Storage-Attached Indexing (SAI)

SAI là hướng secondary indexing tích hợp sâu hơn với storage engine/SSTable so với cách 2i truyền thống. Nó hỗ trợ xây dựng cấu trúc tra cứu theo thuộc tính và có các khả năng kết hợp điều kiện nhất định, tùy phiên bản.

**Không nên hiểu SAI là “global index kiểu DynamoDB GSI”.** Chỉ mục SAI vẫn phải được đánh giá theo cơ chế distributed query của Cassandra: khả năng định vị partition, fan-out, số lượng kết quả, độ chọn lọc, tombstone, compaction và tải ghi.

Ví dụ cú pháp SAI trong những triển khai hỗ trợ:

~~~sql
CREATE CUSTOM INDEX IF NOT EXISTS orders_status_sai
ON orders_by_customer (status)
USING 'StorageAttachedIndex';
~~~

**Cú pháp và tính năng cần kiểm tra theo phiên bản Cassandra/DSE đang triển khai.** Không suy ra mọi phiên bản Apache Cassandra đều hỗ trợ đúng cú pháp hoặc cùng tập toán tử. Nếu hệ không hỗ trợ SAI, câu lệnh này không phải giải pháp thay thế tự động cho 2i.

### 7.4. Khi cần truy vấn theo shop và trạng thái

Nếu access pattern chính là:

> “Lấy 50 đơn PAID mới nhất của shop S7 trong ngày 14/11.”

một bảng đọc hướng truy vấn có thể hợp lý hơn:

~~~sql
CREATE TABLE orders_by_shop_status_day (
    tenant_id text,
    shop_id text,
    status text,
    day_bucket date,
    created_at timestamp,
    order_id text,
    customer_id text,
    total_minor bigint,
    PRIMARY KEY (
        (tenant_id, shop_id, status, day_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Truy vấn:

~~~sql
SELECT order_id, customer_id, created_at, total_minor
FROM orders_by_shop_status_day
WHERE tenant_id = 'T17'
  AND shop_id = 'S7'
  AND status = 'PAID'
  AND day_bucket = '2026-11-14'
LIMIT 50;
~~~

Đây là **read model** được phân vùng theo nhu cầu tìm đơn theo shop/trạng thái/ngày. Nó không phải secondary index tự động của Cassandra; ứng dụng hoặc pipeline phải **duy trì các dòng dữ liệu** khi đơn được tạo, sửa trạng thái hoặc xóa.

**Trade-off:**

- Đọc theo pattern nhanh hơn khi partition key phù hợp.
- Ghi tốn công hơn vì cập nhật nhiều bảng.
- Khi `status` đổi, cần xóa/sửa mục ở bảng trạng thái cũ và thêm ở bảng mới theo quy tắc.
- Nếu một shop có tải rất cao, partition theo ngày vẫn có thể nóng; cần tính kích thước, chọn bucket giờ hoặc shard bổ sung.
- Nếu đồng bộ bất đồng bộ, kết quả read model có thể trễ so với nguồn.

**Bài học Cassandra:** một secondary index không tự biến một bảng theo khách hàng thành bảng tối ưu cho mọi truy vấn theo shop, status và thời gian. Trong mô hình wide-column, **đường truy cập theo partition key** vẫn là cơ sở thiết kế.

## 8. ScyllaDB: local/global là lựa chọn của đường chỉ mục

ScyllaDB có hệ khái niệm **local secondary index** và **global secondary index** gắn với cách tổ chức secondary index bằng các cấu trúc giống bảng dẫn xuất/materialized view.

Hãy hình dung bảng gốc có:

~~~text
Base primary partition key = customer_id
Indexed attribute          = status
~~~

### Local index theo base partition

Ý tưởng:

~~~text
Local indexed access:
  (customer_id, status) → các order liên quan
~~~

Truy vấn có `customer_id` mới định vị được phạm vi cục bộ để tận dụng cấu trúc này:

~~~text
FindOrders(customerId=C42, status=PAID)
~~~

### Global index theo indexed value

Ý tưởng:

~~~text
Global indexed access:
  status → các base primary keys có status tương ứng
~~~

Truy vấn có thể bắt đầu từ indexed value mà không nhất thiết biết `customer_id`:

~~~text
FindOrders(status=PAID)
~~~

**Không suy ra global index luôn tốt hơn.** Nếu `PAID` là giá trị cực kỳ phổ biến, một đường phân phối dữ liệu theo status có thể tạo phân vùng lớn, nóng hoặc fan-out đọc bản ghi gốc. Nếu dùng local index, query có khóa khách hàng lại có thể nhỏ và dễ định tuyến hơn.

### Điểm phải xác minh trong triển khai cụ thể

- Khóa của materialized view/index được phân vùng và sao chép ra sao?
- Chỉ mục trả field có sẵn hay phải đọc lại bảng nguồn?
- Cập nhật view/index được nhìn thấy sau bao lâu?
- Có những giới hạn về kiểu dữ liệu, điều kiện truy vấn và uniqueness không?
- Chi phí tạo/rebuild index và tác động lên write path?

Cơ chế và cú pháp có thể thay đổi theo phiên bản ScyllaDB. Bảng so sánh của bài nhằm làm rõ **ý tưởng định tuyến cục bộ/toàn cục**, không thay thế tài liệu tính năng của phiên bản sản phẩm được sử dụng.

## 9. MongoDB sharding: mỗi shard có index cục bộ, query có thể toàn cluster

MongoDB là document DBMS; khi một collection được **shard**, tài liệu được phân phối dựa trên **shard key** và chiến lược phân phối của cluster.

Ví dụ shard key:

~~~javascript
// Minh họa quyết định mô hình:
// shard key: { tenantId: 1, customerId: 1 }
~~~

Giả sử có secondary index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  shopId: 1,
  status: 1,
  createdAt: -1
});
~~~

Trong sharded collection, các index thông thường được duy trì trong **phạm vi dữ liệu trên từng shard**. Query router (`mongos`) dựa vào thông tin shard key và metadata định tuyến để xác định cần gửi truy vấn tới những shard nào.

### Truy vấn có shard key phù hợp

~~~javascript
db.orders.find({
  tenantId: "T17",
  customerId: "C42"
});
~~~

Với shard key đã giả định, điều kiện theo `tenantId + customerId` có thể hỗ trợ **targeted routing** tới shard/phạm vi dữ liệu liên quan.

### Truy vấn theo secondary field nhưng không có shard key

~~~javascript
db.orders.find({
  shopId: "S7",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(50);
~~~

Truy vấn này **không cung cấp shard key giả định**. Dù mỗi shard đều có index theo `shopId + status + createdAt`, router có thể phải **scatter/gather**: gửi query tới nhiều shard, mỗi shard dùng index cục bộ rồi hợp nhất kết quả.

~~~text
                 Query shopId=S7, status=PAID
                              │
                              ▼
                            mongos
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                  Shard 1   Shard 2   Shard 3
                  index     index     index
                    │         │         │
                    └─────────┼─────────┘
                              ▼
                        Merge / limit
                              │
                              ▼
                           Response
~~~

Vì vậy **có secondary index trên mọi shard không có nghĩa đã có một global lookup duy nhất có thể định tuyến theo `shopId`**.

### Đọc hiểu hai câu “có index” và “định tuyến được”

| Câu hỏi | Index cục bộ trên shard | Shard routing |
| --- | --- | --- |
| Các record của shop S7 ở shard này có thể lọc nhanh hơn không? | Có thể, nếu index phù hợp | Không quyết định |
| Router biết chỉ cần hỏi một shard nào không? | Không do secondary index quyết định | Phụ thuộc shard key và metadata/routing |
| Query thiếu shard key có thể scatter/gather không? | Mỗi shard vẫn có thể dùng index | Có |
| Có nên thêm shopId vào shard key không? | Phải xét toàn workload | Có thể giúp một pattern nhưng ảnh hưởng các pattern khác |

Nếu hệ cần truy vấn theo cả khách hàng và shop với tải cao, không nên đổi shard key tùy tiện chỉ để tối ưu một endpoint. Cân nhắc **read model**, index phù hợp với từng shard, hoặc chiến lược phân phối mới dựa trên tổng workload.

### Uniqueness cũng gắn với sharding

Một unique index trong sharded collection có các hạn chế liên quan đến shard key. Không được cho rằng chỉ cần tạo unique secondary index bất kỳ là DBMS sẽ bảo đảm uniqueness toàn cluster theo mọi thuộc tính. Quy tắc cụ thể cần được đối chiếu với loại shard key và phiên bản MongoDB.

Đặc biệt, nếu yêu cầu **email duy nhất toàn tenant** trong dữ liệu phân tán, phải xác định ranh giới uniqueness và cách cưỡng chế nó, chứ không chỉ đặt index cục bộ rồi giả định không thể có giá trị trùng trên các shard.

## 10. Một phép so sánh rất quan trọng: global query khác global index

Một hệ thống có thể trả lời câu hỏi “tìm toàn bộ document có status=PAID” bằng cách hỏi tất cả shard. Đó là **query có phạm vi toàn cụm**, nhưng chưa chắc hệ có một **global secondary index được phân vùng theo status**.

~~~text
Phương án A — local indexes + distributed fan-out:

Query(status=PAID)
      │
      ▼
Hỏi các shard có dữ liệu nguồn
      │
      ▼
Mỗi shard dùng index status cục bộ
      │
      ▼
Gom kết quả

Phương án B — global access path:

Query(status=PAID)
      │
      ▼
Định tuyến theo status vào index riêng
      │
      ▼
Lấy danh sách base record keys hoặc projected attributes
      │
      ▼
Trả kết quả / fetch nguồn nếu cần
~~~

Hai phương án có thể trả **kết quả logic giống nhau**, nhưng khác:

- Số shard phải liên hệ.
- Cách cân bằng tải theo giá trị indexed field.
- Chi phí đọc bản ghi nguồn sau khi tra index.
- Write amplification và chi phí lưu trữ.
- Tính nhất quán giữa nguồn và chỉ mục.
- Khả năng mở rộng khi query tập trung vào một giá trị phổ biến.

Vì thế không nên dùng cụm từ “query global” để khẳng định có “global secondary index” theo cấu trúc B.

## 11. Search engine: inverted index trên từng shard cũng không phải GSI DynamoDB

Các hệ tìm kiếm phân tán như Elasticsearch hoặc OpenSearch thường lưu **inverted index** trên từng shard, sau đó coordinator gửi truy vấn tới các shard liên quan và hợp nhất kết quả.

Ví dụ tìm các sản phẩm chứa từ khóa “sổ tay”:

~~~text
Search request
      │
      ▼
Coordinator
  ├── Shard A inverted index: "sổ" → document IDs
  ├── Shard B inverted index: "sổ" → document IDs
  └── Shard C inverted index: "sổ" → document IDs
      │
      ▼
Merge / rank / return
~~~

Ứng dụng có thể trải nghiệm một **global search interface** nhưng index thực tế vẫn phân tán theo shard. Không nên so sánh trực tiếp một inverted index tìm toàn văn với GSI theo khóa chính xác của DynamoDB; chúng giải quyết **những hình dạng truy vấn** khác nhau.

Tương tự, khi cần tìm kiếm toàn văn, prefix, relevance ranking hoặc bộ lọc linh hoạt, một secondary index đơn giản theo `status` chưa chắc thay thế được công cụ search.

## 12. Chọn khóa index phụ: điều kiện bằng, thứ tự và tính phân bố

Việc chọn local hay global chỉ là bước đầu. **Key design** quyết định một index có phục vụ truy vấn thực tế hay không.

Giả sử access pattern:

~~~text
FindOpenOrders(
  tenantId=T17,
  shopId=S7,
  status in {PAID, PACKING},
  start=2026-11-14T00:00Z,
  end=2026-11-15T00:00Z,
  sort=createdAt DESC,
  limit=50
)
~~~

Một thiết kế index có thể cần:

~~~text
partition key: tenantId + shopId + status + timeBucket
sort key:      createdAt DESC + orderId
~~~

Nhưng phải xem:

1. `status IN {PAID, PACKING}` có thể yêu cầu **đọc hai partition** và merge kết quả.
2. Truy vấn qua nhiều ngày phải đọc **nhiều time buckets**.
3. Shop S7 có thể là một tenant rất nóng; một bucket ngày vẫn quá lớn.
4. Khi status thay đổi, mục index phải di chuyển từ nhóm cũ sang nhóm mới.
5. Nếu index không lưu đủ các trường response, cần đọc bản ghi nguồn.
6. Nếu nhiều người dùng cùng yêu cầu một status phổ biến, partition key đó có thể thành điểm nóng.

### Chỉ mục trên một trường có cardinality thấp

Nếu `status` chỉ có 5 giá trị, một global index partitioned **chỉ theo status** có thể dồn nhiều bản ghi vào vài nhóm. Đây thường là dấu hiệu cần thêm tenant/shop/time bucket/shard phù hợp.

Ngược lại, nếu indexed field là `paymentReference` gần như duy nhất, index theo tham chiếu có thể rất chọn lọc và hợp lý cho lookup.

### Sắp xếp có thể quyết định thiết kế index

Index theo:

~~~text
shopId + status
~~~

có thể tìm các đơn của shop/trạng thái, nhưng chưa chắc trả được **50 đơn mới nhất** mà không sắp xếp thêm.

Index theo:

~~~text
(tenantId, shopId, status) + createdAt DESC + orderId
~~~

có thể gần với query shape hơn. Với từng DBMS phải kiểm tra **khả năng index order**, cú pháp sort key, giới hạn pagination và cách xử lý nhiều partition.

**Điểm cần ghi trong access pattern:** một truy vấn gồm **điều kiện, thứ tự, giới hạn, projection, độ trễ và tính nhất quán** — không chỉ tên field trong `WHERE`.

## 13. Độ chọn lọc và fan-out quyết định nhiều hơn tên index

**Độ chọn lọc** mô tả bao nhiêu phần dữ liệu phù hợp một điều kiện.

Giả sử:

~~~text
Total orders = 100.000.000
status=PAID  = 60.000.000  (60%)
paymentId=X  = 1          (rất chọn lọc)
~~~

Chỉ mục theo `status` vẫn có thể trả hàng chục triệu kết quả. Chỉ mục theo `paymentId` có thể nhanh chóng đưa tới một bản ghi.

Tuy nhiên **tính chọn lọc cao không tự đảm bảo ít fan-out**: một local secondary index phân tán theo shard có thể vẫn phải hỏi nhiều shard để biết giá trị hiếm nằm ở đâu khi query thiếu shard key.

### Hai loại chi phí độc lập

~~~text
Routing cost:
  Cần hỏi bao nhiêu node/shard/partition?

Work per target:
  Mỗi nơi phải xem bao nhiêu index entries/document?
~~~

Một index global có thể giảm số điểm định tuyến nhưng vẫn trả lượng kết quả lớn. Một local index có thể trả rất ít kết quả ở mỗi shard nhưng phải hỏi nhiều shard.

### Mô hình ước lượng đơn giản

Gọi:

- `F`: số shard/partition phải hỏi.
- `S_i`: số mục index được xét tại shard thứ `i`.
- `R`: tổng số bản ghi thực sự trả về.

Ta có một cách nghĩ gần đúng:

\[
\text{read effort} \sim \sum_{i=1}^{F} S_i
\]

cộng thêm chi phí định tuyến, mạng, fetch dữ liệu và hợp nhất kết quả.

Đây **không phải công thức latency của một DBMS cụ thể**. Nó cho thấy vì sao cần đo **fan-out** và **keys/documents examined** riêng biệt, thay vì chỉ quan sát kích thước response.

## 14. Chi phí ghi khi có nhiều secondary indexes

Thêm secondary index có thể giảm độ trễ đọc nhưng làm ghi đắt hơn. Một cập nhật order:

~~~text
Order O1003:
  status: NEW → PAID
~~~

không chỉ thay field `status` trong bản ghi nguồn. Nếu các index có khóa liên quan đến status, DBMS hoặc hệ thống ứng dụng phải cập nhật mục chỉ mục:

~~~text
Base update:
  O1003.status = PAID

Secondary index maintenance:
  Remove entry from NEW group
  Add entry to PAID group

Other effects (if applicable):
  Update search/read model
  Emit event
  Update audit/projection
~~~

### Write amplification

Khái niệm **write amplification** ở đây chỉ việc một thay đổi nghiệp vụ dẫn đến thêm thao tác ghi vào index, replica hoặc dữ liệu dẫn xuất.

Nếu một hệ thống có quá nhiều index:

- Ghi có thể chậm và tốn tài nguyên hơn.
- Dung lượng index tăng.
- Compaction, background maintenance hoặc replication có thêm việc.
- Thay đổi schema/index có thời gian build và chi phí vận hành.
- Khi quá tải, index update có thể thành nút thắt của toàn write path.

Không có quy tắc “mỗi index cộng chính xác một lần ghi” áp dụng cho mọi hệ. Số thao tác vật lý và chi phí phụ thuộc DBMS, storage engine, loại index, cập nhật trường nào và cấu hình.

### Đánh giá trên toàn workload

Giả sử một index chỉ phục vụ báo cáo chạy mỗi tháng, trong khi `status` được cập nhật hàng chục nghìn lần/giờ. Tạo GSI hoặc một read model đồng bộ có thể làm hàng triệu lần cập nhật phải chịu chi phí để tiết kiệm thời gian cho một truy vấn hiếm.

Nếu báo cáo có thể chạy theo batch và có deadline rộng, đó có thể là đánh đổi không đáng. Nhưng nếu cần tra cứu trạng thái khẩn cấp khi sự cố thanh toán, index có thể có giá trị vận hành cao dù ít dùng.

**Quyết định phải cân bằng tần suất, độ thiết yếu, latency và chi phí duy trì**, không chỉ nhìn tốc độ của một câu truy vấn.

## 15. Tính nhất quán giữa dữ liệu gốc và index

Mọi secondary index cần phản ánh sự thay đổi của dữ liệu gốc. Có hai nhóm ý tưởng:

**Cập nhật gắn chặt với ghi nguồn**

~~~text
Write source
    │
    └── Index maintenance trong cơ chế DBMS
~~~

**Cập nhật qua pipeline bất đồng bộ**

~~~text
Write source
    │
    ▼
Commit source
    │
    ▼
Event/replication/update stream
    │
    ▼
Index catches up
~~~

Trong thực tế, một DBMS có thể dùng kết hợp cơ chế đồng bộ logic, nhật ký, cập nhật nền và replication. Không nên phân loại index chỉ dựa trên một sơ đồ đơn giản.

### Những lỗi nhất quán cần xem xét

1. **Index trễ:** bản ghi vừa tạo chưa xuất hiện khi query chỉ mục.
2. **Index cũ:** bản ghi đã đổi trạng thái nhưng query vẫn tạm thấy giá trị cũ.
3. **Bản ghi bị xóa:** index có thể cần xóa entry hoặc lọc các tham chiếu không còn hợp lệ.
4. **Event duplicate/retry:** nếu index do ứng dụng tự duy trì, ghi lại không được nhân đôi kết quả.
5. **Out-of-order changes:** sự kiện phiên bản cũ không được đè trạng thái mới.
6. **Rebuild:** khi xây lại index cần chụp dữ liệu nền và bắt kịp thay đổi xảy ra trong lúc rebuild.

### Ví dụ trạng thái thanh toán

Giả sử:

~~~text
Order service:
  Order O1003 status=PAID  (đã commit)

Global secondary index:
  Query STATUS#PAID chưa thấy O1003 vì đang lag
~~~

Ứng dụng **không được** kết luận “đơn chưa thanh toán” chỉ từ việc không tìm thấy trong index eventually consistent nếu đó là quyết định nghiệp vụ cần tính đúng ngay.

Một thiết kế có thể:

- Dùng lookup chính theo `orderId` để xác định trạng thái chính xác.
- Dùng GSI chỉ cho màn hình danh sách với độ trễ cho phép.
- Hiển thị thời điểm làm mới/lag nếu có nhu cầu.
- Giới hạn chức năng quyết định giao dịch dựa trên read model bất đồng bộ.

### Chứng minh “không có bản ghi” khó hơn “đã có kết quả”

Đối với index eventual, “không tìm thấy” có thể nghĩa là:

- Bản ghi nguồn thật sự không tồn tại.
- Bản ghi tồn tại nhưng chưa được index.
- Bản ghi thuộc partition khác do khóa tra cứu sai.
- Chỉ mục bị trễ hoặc đang rebuild.
- Item thiếu thuộc tính khóa index theo thiết kế.

Vì vậy, **negative lookup** trong hệ thống có global index asynchronous cần quy tắc riêng khi ảnh hưởng đến uniqueness, thanh toán hay phân quyền.

## 16. Chỉ mục phụ và uniqueness toàn hệ thống

**Secondary index không mặc định là unique index.**

Giả sử nghiệp vụ yêu cầu:

> Trong mỗi tenant, email đăng nhập chuẩn hóa chỉ thuộc về một tài khoản.

Nếu người dùng thuộc nhiều partition theo `userId`, một index theo `email` có thể giúp **tìm tài khoản**, nhưng chưa chắc việc **kiểm tra trước rồi tạo** tài khoản là nguyên tử:

~~~text
Client A: query email=an@example.invalid → không tìm thấy
Client B: query email=an@example.invalid → không tìm thấy

Client A: create user U1
Client B: create user U2
~~~

Cả hai có thể thành công nếu không có cơ chế uniqueness phù hợp. Với global index eventual, tình huống càng dễ bị hiểu sai.

### Các hướng bảo đảm cần khảo sát

- **Unique constraint/index** nếu DBMS hỗ trợ toàn bộ phạm vi yêu cầu.
- **Conditional put** trên một key định danh email đã chuẩn hóa, ví dụ `TENANT#T17#EMAIL#...`.
- **Transaction** phối hợp việc chiếm key email và tạo user nếu hệ quản trị hỗ trợ.
- Một service có thẩm quyền giữ **registry định danh** và xử lý tranh chấp.

Ví dụ ý tưởng trong kho key–value:

~~~text
Key:
  EMAIL#T17#an@example.invalid

Value:
  userId = U1

Operation:
  Create only if key does not exist
~~~

Nhưng nếu còn phải tạo user record ở key khác, cần giải quyết invariant **registry và user record nhất quán**, thông qua transaction hoặc một quy trình trạng thái/bù trừ phù hợp.

**Độ nhanh của lookup không phải bảo đảm uniqueness.** Đây là lỗi thiết kế phổ biến khi coi GSI theo email là ràng buộc “mỗi email một người”.

## 17. Global index theo một giá trị có thể tạo hot partition

Một nhược điểm tiềm tàng là **dồn tải theo giá trị phụ rất phổ biến**.

Ví dụ index:

~~~text
GSI partition key = status
~~~

Với các trạng thái:

~~~text
PAID       → 60% orders
SHIPPED    → 25% orders
NEW        → 10% orders
CANCELLED  → 5% orders
~~~

Phần lớn ghi/cập nhật và query tập trung vào vài giá trị. Dù toàn hệ được chia theo hàng triệu `customerId`, index phụ theo `status` có thể đưa tải về rất ít logical keys.

### Các cách giảm điểm nóng

- Kết hợp **tenant/shop** vào khóa index nếu truy vấn luôn có những điều kiện đó.
- Chia **bucket theo ngày/giờ** khi query có phạm vi thời gian.
- Dùng **write sharding** trên khóa index ở trường hợp cần thiết, rồi fan-out/merge một số shard đã biết khi đọc.
- Dùng **rollup** nếu câu hỏi chỉ cần đếm/tổng chứ không cần mọi bản ghi.
- Đưa báo cáo quét lớn vào một **analytical store** thay vì tăng nóng index giao dịch.

Ví dụ:

~~~text
Thay vì:
  STATUS#PAID

Cân nhắc:
  TENANT#T17#SHOP#S7#STATUS#PAID#DAY#2026-11-14
~~~

Nếu shop S7 vẫn có khối lượng rất lớn trong một ngày, có thể cần shard thêm theo `hash(orderId)` hoặc bucket hẹp hơn. Đổi lại, việc truy vấn nhiều shard/bucket cần gộp kết quả và quản lý phân trang.

Không nên thêm shard suffix ngẫu nhiên mà không xác định cách **đọc tất cả nhóm liên quan**; thiết kế tối ưu ghi có thể làm đường đọc phức tạp hơn.

## 18. Index lookup có phải đọc thêm dữ liệu nguồn không?

Một secondary index có thể lưu:

~~~text
Index key → base primary key
~~~

hoặc:

~~~text
Index key → base primary key + selected projected fields
~~~

Trong trường hợp thứ nhất, truy vấn index chỉ tìm được vị trí bản ghi; ứng dụng hoặc DBMS cần **fetch base record** để lấy nội dung.

Trong trường hợp thứ hai, index có thể đủ dữ liệu cho một màn hình tóm tắt.

### Ví dụ response cho danh sách đơn hàng

Danh sách cần:

~~~json
{
  "orderId": "O1003",
  "createdAt": "2026-11-08T10:20:00Z",
  "status": "PAID",
  "totalMinor": 125000,
  "currency": "VND"
}
~~~

Nếu index chỉ có `orderId` và `createdAt`, backend cần tra bảng nguồn để lấy `status`, `totalMinor`, `currency`.

Với 50 kết quả, có thể sinh thêm 50 lookup nguồn nếu không có batch/hỗ trợ trong hệ. Nếu index lưu đủ các field, số lookup giảm, nhưng index lớn hơn và phải cập nhật khi những field được sao chép đổi.

### Đánh đổi index covering

| Thiết kế | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| Chỉ khóa chính/khóa index | Index gọn, ghi ít field hơn | Có thể cần fetch dữ liệu nguồn |
| Index kèm một số field | Đủ cho các màn hình chính, giảm network/fetch | Tăng kích thước và chi phí cập nhật |
| Index sao toàn bộ item/document | Đọc một số query tiện | Lưu trữ lớn, cập nhật đắt, dễ lặp dữ liệu không cần |

Chỉ mục toàn cục và query projection là **hai quyết định khác nhau**: một cái tổ chức đường tìm, cái kia chọn lượng dữ liệu trả. Trong DynamoDB, index projection khi tạo GSI/LSI còn quyết định nội dung được lưu trong chính index.

## 19. Tenant boundary và bảo mật khi dùng secondary index

Một global index theo:

~~~text
paymentReference → orderId
~~~

có thể trả đúng bản ghi trên toàn hệ, nhưng không đảm bảo người gọi **có quyền xem bản ghi**.

Nếu ứng dụng có nhiều tenant, nên cân nhắc:

~~~text
(tenantId, paymentReference) → orderId
~~~

hoặc một cơ chế kiểm quyền phù hợp với domain. Tuy nhiên, **đưa tenantId vào khóa index không thay thế authentication/authorization**.

Ví dụ nguy hiểm:

~~~text
GET /orders/search?paymentReference=P-123

Backend:
  Query global index by paymentReference
  Return order without checking tenant ownership
~~~

Nếu index tra ra đơn của tenant khác, việc lộ kết quả là lỗi bảo mật. Cần:

- Xác thực caller.
- Xác định tenant/phạm vi truy cập từ identity đáng tin cậy.
- Kiểm tra quyền xem bản ghi và field.
- Giới hạn truy vấn và phân trang.
- Không cho caller tự nhập biểu thức index/query tùy ý dưới quyền cao.
- Audit truy cập quản trị hoặc dữ liệu nhạy cảm theo chính sách.

Một index rất nhanh chỉ làm lỗi phân quyền xảy ra nhanh hơn nếu quyền không được kiểm tra.

## 20. Chọn secondary index, read model hay scan?

Một access pattern có thể có nhiều hướng triển khai.

| Điều kiện nghiệp vụ | Hướng khảo sát | Đánh đổi cần kiểm tra |
| --- | --- | --- |
| Có base partition key và cần sắp xếp phụ trong cùng nhóm | Local index hoặc clustering/sort key phù hợp | Phạm vi item collection và độ lớn partition |
| Query thường xuyên theo khóa phụ không biết base partition | Global index hoặc bảng/read model theo khóa mới | Chi phí ghi, consistency, hot key |
| Điều kiện phụ có độ chọn lọc tốt, ít kết quả | Secondary index phù hợp với DBMS | Fan-out và data fetch |
| Query theo field rất phổ biến, trả lượng dữ liệu lớn | Bảng theo bucket/rollup hoặc analytics | Dung lượng nhóm, tổng hợp, vận hành |
| Truy vấn toàn văn, relevance ranking, tổ hợp bộ lọc linh hoạt | Search index/engine | Đồng bộ dữ liệu, quyền, lag |
| Báo cáo tháng quét hàng triệu bản ghi | Batch/analytical store | Deadline, checkpoint, không gây tải online |
| Lookup phụ hiếm nhưng cần khi sự cố | Index nhỏ/lookup table nếu hợp lý | Chi phí duy trì so với rủi ro vận hành |
| Cần uniqueness mạnh | Unique constraint hoặc conditional key/transaction | Không thay bằng eventual secondary lookup |

### Một quy trình ra quyết định

~~~text
Bắt đầu từ access pattern
         │
         ▼
Có biết primary partition key?
         │
   ┌─────┴─────┐
  Có          Không
   │            │
   ▼            ▼
Có đủ sort/      Có alternate key
filter trong     ổn định và query
partition?       thường xuyên?
   │            │
   ▼            ▼
Base/LSI/        GSI/read model/
local index      secondary index
   │            │
   └─────┬──────┘
         ▼
Đánh giá selectivity, fan-out,
hot key, consistency, write cost
         │
         ▼
Đo bằng dữ liệu/tải đại diện
         │
         ▼
Chọn thiết kế phù hợp toàn workload
~~~

Đây là sơ đồ **định hướng**, không phải thuật toán tự động chọn DBMS. Một hệ có thể dùng nhiều đường truy cập song song nếu các pattern khác nhau đủ quan trọng.

## 21. Tình huống thiết kế xuyên suốt: hai màn hình đơn hàng

Giả sử một hệ có hai chức năng:

**Màn hình A — lịch sử mua hàng**

~~~text
Input:
  tenantId, customerId, cursor

Filter:
  Tất cả đơn của một khách

Sort:
  createdAt DESC

Output:
  20 đơn/trang
~~~

**Màn hình B — đơn cần đóng gói**

~~~text
Input:
  tenantId, shopId, status=PACKING, date range

Filter:
  Một shop, một trạng thái, ngày

Sort:
  createdAt ASC

Output:
  50 đơn/trang
~~~

### 21.1. Nếu dùng DynamoDB

Có thể chọn:

~~~text
Base table Orders:
  PK = tenant#customer
  SK = createdAt#orderId

GSI ByShopStatus:
  GSI PK = tenant#shop#status#day
  GSI SK = createdAt#orderId
~~~

Khi ấy:

- Màn hình A query base table.
- Màn hình B query GSI theo shop/status/day.
- Nếu status thay đổi, GSI update có thể trễ.
- Cần pagination riêng theo từng access path và xử lý nhiều day buckets.
- GSI key nên xét hot shop và tỉ lệ cập nhật trạng thái.
- Projection cần đủ trường hiển thị hoặc có bước đọc nguồn phù hợp.

Nếu màn hình A dùng base sort key theo thời gian rồi, **không cần tạo LSI chỉ để lặp lại cùng đường sort**.

### 21.2. Nếu dùng Cassandra

Có thể tạo hai bảng đọc:

~~~text
orders_by_customer_month:
  partition = tenant + customer + month
  clustering = createdAt DESC + orderId

orders_by_shop_status_day:
  partition = tenant + shop + status + day
  clustering = createdAt ASC + orderId
~~~

Lúc đó:

- Màn hình A đọc các bucket tháng có liên quan.
- Màn hình B đọc bucket ngày theo shop/trạng thái.
- Write path phải cập nhật/đồng bộ các bảng theo chính sách.
- Nếu status đổi, mục ở bảng trạng thái cũ không được để lại sai.
- Nếu xử lý qua sự kiện, phải đo lag và hỗ trợ retry/rebuild.

Thiết kế này **không gọi hai bảng là secondary indexes tự động**; chúng là cấu trúc hướng truy vấn do ứng dụng duy trì.

### 21.3. Nếu dùng sharded MongoDB

Giả sử sharding theo tenant/customer:

- Màn hình A có thể được định tuyến chọn lọc khi có đầy đủ shard key phù hợp.
- Màn hình B thiếu customerId, nên có thể cần scatter/gather qua các shard dù mỗi shard có secondary index.
- Nếu tải B rất lớn, cần đánh giá lại shard key, mô hình đọc hoặc một pipeline riêng.
- Không nhất thiết được lợi từ một global secondary index theo cách DynamoDB GSI chỉ vì đặt `createIndex({shopId, status, createdAt})`.

### 21.4. Kết luận từ ví dụ

Cùng hai access patterns, mỗi DBMS có một đường thiết kế hợp lý khác nhau. Câu hỏi không phải “LSI hay GSI cái nào tốt hơn?” mà là:

> **Khóa truy vấn được biết là gì, dữ liệu được phân phối theo khóa nào, và một query cần truy cập bao nhiêu phạm vi dữ liệu để trả đúng kết quả?**

## 22. Thay đổi trạng thái và tác động lên index

Một đơn chuyển:

~~~text
NEW → PAID → PACKING → SHIPPED
~~~

Nếu index theo `status`, mỗi bước có thể kéo theo:

~~~text
1. Cập nhật order ở nguồn.
2. Xóa/không còn hiển thị index entry thuộc status cũ.
3. Tạo index entry thuộc status mới.
4. Đồng bộ dữ liệu dẫn xuất và cache (nếu có).
~~~

### Câu hỏi phải giải quyết

- Hai thay đổi liên tiếp đến nhanh có thể bị index xử lý sai thứ tự không?
- Nếu một update index thất bại, hệ thống có retry không?
- Người dùng xem màn hình admin có được phép thấy trạng thái cũ vài giây không?
- Xóa order ở nguồn có xóa đúng mục index không?
- Có cách so sánh số lượng/bản ghi giữa source và index không?
- Nếu rebuild, có thể tiếp tục nhận thay đổi trong lúc xây lại không?

Nếu index được DBMS duy trì nội bộ, bảo đảm phụ thuộc chính DBMS. Nếu là read model tự duy trì, nhóm ứng dụng phải thiết kế các quy tắc này rõ ràng.

### Không đồng nhất “thứ tự index” với “thứ tự sự kiện”

Một index có sort key theo `createdAt` không tự giải quyết thứ tự **cập nhật trạng thái**. Chỉ mục sắp thứ tự kết quả theo một field, còn yêu cầu “chỉ nhận phiên bản mới nhất” cần cơ chế versioning/conditional update và chính sách đồng bộ.

## 23. Thiết kế với nhiều index: khi nào chi phí không còn đáng?

Giả sử mỗi item có các đường đọc:

~~~text
orders_by_customer
orders_by_shop_status
orders_by_payment_reference
orders_by_delivery_city
orders_by_campaign
orders_by_support_phone
orders_by_refund_status
~~~

Không phải cứ có một bộ lọc là tạo một GSI/bảng phụ.

### Lý do cần giới hạn số lượng

- Mỗi index làm tăng dung lượng và công việc ghi tương ứng.
- Có giới hạn số index và các tính năng khác nhau theo DBMS.
- Một số đường query dùng field có cardinality thấp hoặc dữ liệu không ổn định.
- Những truy vấn hiếm có thể xử lý bằng công cụ admin/batch.
- Dữ liệu nhạy cảm không nên bị sao thêm sang quá nhiều kho.
- Khi thay schema, phải cập nhật nhiều index/read model.

### Một bảng quyết định ưu tiên

| Pattern | Tần suất | Ràng buộc latency | Độ chọn lọc | Gợi ý đánh giá |
| --- | --- | --- | --- | --- |
| Lịch sử đơn theo khách | Cao | Thấp | Theo khách | Primary access path |
| Đơn cần đóng gói theo shop | Cao | Thấp | Shop + status + ngày | GSI/read model riêng |
| Tìm theo payment reference | Thấp nhưng khẩn cấp | Vài giây | Rất cao | Secondary lookup có thể hợp lý |
| Tìm đơn theo từ khóa trong ghi chú hỗ trợ | Thấp | Trung bình | Full-text | Search/admin store |
| Doanh thu theo vùng trong 3 năm | Theo tháng | Batch deadline | Quét rộng | Analytics/rollup |

Đây chỉ là **ví dụ đánh giá**; quyết định cuối phải dựa trên dữ liệu phân bố, tải, độ trễ, bảo mật và bảo đảm nhất quán thực tế.

## 24. Đo và kiểm chứng một index trong môi trường thực

Không nên quyết định chỉ từ sơ đồ. Cần đo index trên dữ liệu và tải đại diện.

### Các chỉ số cần chú ý

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số shard/partition/node tham gia | Cho biết mức **fan-out** |
| Keys/index entries examined | Độ rộng của việc tra index |
| Base records/documents fetched | Có cần đọc nguồn sau khi tra index? |
| Rows returned | Kích thước kết quả thực |
| Latency p50/p95/p99 | Trải nghiệm truy vấn ở các mức tải |
| Read/write capacity hoặc I/O | Tài nguyên tiêu thụ |
| Index storage size | Chi phí lưu trữ và cache |
| Write latency khi cập nhật indexed fields | Tác động tới đường ghi |
| Index replication/update lag | Độ mới của dữ liệu phụ |
| Hot partitions và throttling | Dấu hiệu phân bố khóa không đều |
| Background build/rebuild duration | Khả năng vận hành và phục hồi |

### Phân tích theo từng DBMS

**MongoDB:** xem kế hoạch `explain`, số document/index key đã xét, việc có scatter/gather trên sharded cluster và vai trò của shard key.

**DynamoDB:** đo Query trên base/LSI/GSI, consumed capacity, throttling, latency, hot partition và quan sát độ trễ hiển thị sau cập nhật nguồn. Lưu ý GSI không có strongly consistent read.

**Cassandra/ScyllaDB:** xem tracing/metrics phù hợp, số partition, latency coordinator, số node liên quan, hiệu quả index, compaction và tải đọc/ghi.

Không tự chạy index build hoặc stress test lớn trên production nếu chưa đánh giá tác động. Nội dung này là hướng dẫn **thiết kế và kiểm chứng**, không phải lời khuyên thay cấu hình trực tiếp.

### Một phép so sánh hữu ích

Cho cùng workload:

~~~text
Q1: Find 50 latest PAID orders for one shop
Q2: Find PAID orders across all shops in one tenant
Q3: Find one order by payment reference
~~~

Hãy kiểm tra:

1. Có biết khóa định tuyến của mỗi query không?
2. Một query cần liên hệ bao nhiêu partition?
3. Cần bao nhiêu index entries được xem xét để trả 50 kết quả?
4. Có phải fetch thêm bản ghi nguồn?
5. Index có cập nhật kịp độ mới yêu cầu không?
6. Chi phí ghi tăng thế nào khi có thêm index?

Nếu trả lời được sáu câu hỏi đó, bạn đã đi xa hơn nhiều so với việc chỉ đọc tên “local” hoặc “global”.

## 25. Các lỗi thiết kế thường gặp

| Sai lầm | Vì sao sai | Cách tiếp cận đúng |
| --- | --- | --- |
| Coi local index chỉ dùng được trên một máy vật lý | Locality có thể theo partition/shard/node, tùy DBMS | Xác định rõ ranh giới local |
| Coi global index nằm trên một máy duy nhất | Global access path có thể tự phân vùng | Xem khóa phân vùng của index |
| Coi mọi secondary index là GSI như DynamoDB | Các hệ có cơ chế index khác nhau | Phân tích triển khai cụ thể |
| Tạo index trên status rồi nghĩ query theo shop/status/time chắc chắn nhanh | Thiếu khóa nhóm và sort phù hợp | Thiết kế từ query shape đầy đủ |
| Dùng Cassandra 2i/SAI rồi bỏ qua partition key | Vẫn có thể fan-out hoặc quét nhiều dữ liệu | Đo distributed query; cân nhắc bảng theo truy vấn |
| Tạo MongoDB secondary index và mặc định mongos route đúng một shard | Router dựa vào shard key/metadata | Kiểm tra targeted vs scatter/gather |
| Dùng GSI DynamoDB để xác nhận bản ghi vừa ghi đã tồn tại | GSI eventual consistency | Dùng nguồn/đường đọc có bảo đảm phù hợp |
| Dùng GSI theo email như unique constraint | GSI không tự bảo đảm uniqueness | Conditional key/transaction/unique mechanism |
| Đặt GSI partition key chỉ là một giá trị rất phổ biến | Hot partition, độ chọn lọc thấp | Kết hợp tenant/shop/bucket hoặc chiến lược khác |
| Chọn `ALL` projection cho mọi GSI | Index phình to, ghi/lưu trữ tăng | Chỉ project field cần cho access pattern |
| Nghĩ projection ít field luôn giảm read cost | Chi phí tính theo khả năng DBMS, không chỉ response | Đo consumed capacity, fetch và I/O |
| Chỉ xem độ trễ đọc mà không đo write path | Thêm index có thể làm ghi chậm | Đánh giá toàn workload |
| Quên xóa index entry khi status đổi | Danh sách bị sai, lặp/trạng thái cũ | Thiết kế đồng bộ đúng với nguồn |
| Không kiểm tra tenant scope | Có nguy cơ rò rỉ dữ liệu | Authentication, authorization và query scoping |
| Gọi scan toàn cluster là global index | Global query chưa chắc có index phân vùng độc lập | Phân biệt đường định tuyến vật lý |

## 26. Bài tập thực hành

### Bài 1 — Xác định local hay global

Hệ thống có hai bảng logic:

~~~text
Base:
  partitionKey = customerId
  sortKey      = orderId

Index A:
  partitionKey = customerId
  sortKey      = createdAt

Index B:
  partitionKey = shopId#status
  sortKey      = createdAt
~~~

Theo **nghĩa DynamoDB**, index nào phù hợp ý tưởng LSI và index nào phù hợp ý tưởng GSI? Vì sao?

**Gợi ý:** A giữ partition key của base, thay sort key; B có partition key mới. Lưu ý trong DynamoDB LSI phải được tạo cùng bảng và có quy định khác với GSI.

### Bài 2 — Cassandra và thiếu partition key

Một bảng Cassandra lưu đơn theo `(tenantId, customerId)` và clustering theo thời gian. Người quản trị muốn liệt kê mọi đơn `FAILED` trong ngày.

Hãy giải thích vì sao có index theo `status` chưa đủ bảo đảm truy vấn nhanh; đề xuất một bảng/read model phù hợp.

**Gợi ý:** query không biết `customerId`, có nguy cơ fan-out. Xem khóa `tenant + status + dayBucket`, clustering theo thời gian và chi phí duy trì khi status thay đổi.

### Bài 3 — MongoDB secondary index trên từng shard

Collection MongoDB được shard theo `(tenantId, customerId)`. Có index:

~~~javascript
db.orders.createIndex({
  shopId: 1,
  status: 1,
  createdAt: -1
});
~~~

Truy vấn:

~~~javascript
db.orders.find({
  shopId: "S7",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(50);
~~~

Vì sao vẫn có thể phải hỏi nhiều shard? Secondary index giúp ở bước nào?

**Gợi ý:** thiếu shard key để mongos định tuyến chọn lọc. Index có thể giảm lượng việc trên từng shard nhưng không tự tạo global routing key.

### Bài 4 — Đọc ngay sau khi ghi vào GSI

Một đơn vừa chuyển sang `PAID` trong DynamoDB base table. API đọc GSI `ByShopStatus` mà chưa thấy đơn. Có phải DBMS ghi thất bại không? API xác nhận thanh toán nên đọc từ đâu?

**Gợi ý:** GSI được cập nhật theo eventual consistency. Không suy ra ghi nguồn lỗi; dùng một đường đọc nguồn có thẩm quyền/bảo đảm phù hợp.

### Bài 5 — Hot key theo trạng thái

90% đơn hàng trong hệ có `status=COMPLETED`. Một GSI chỉ phân vùng theo `status`. Dự đoán vấn đề có thể gặp về phân bố tải, và đề xuất cách tách khóa có xét query thực tế.

**Gợi ý:** thêm tenant/shop/time bucket hoặc shard nếu cần, nhưng phải tính đường truy vấn và gộp các nhóm khi đọc.

### Bài 6 — Projection của GSI

Một màn hình danh sách chỉ cần `orderId`, `createdAt`, `status` và `totalMinor`. GSI mới chỉ chứa các khóa.

Nên chọn những thuộc tính nào project thêm? Nếu cần xem chi tiết đầy đủ, nên đọc qua đường nào? Những chi phí nào tăng nếu chọn `ALL` cho mọi index?

**Gợi ý:** `INCLUDE` các trường cần thiết cho danh sách theo kiến trúc phù hợp, chi tiết đọc từ base table; cân bằng kích thước index và chi phí ghi.

### Bài 7 — Uniqueness toàn tenant

Bạn tạo GSI `emailNormalized → userId`. Hai request tạo user cùng email đồng thời. Vì sao bước “Query index, nếu chưa có thì Put user” có thể không giữ được uniqueness?

**Gợi ý:** check-then-act không nguyên tử; GSI có thể eventual. Cần conditional claim key hoặc transaction/ràng buộc phù hợp.

### Bài 8 — Chọn giữa GSI và batch

Một báo cáo cuối tháng tìm toàn bộ đơn `REFUNDED` trong ba năm; nó không cần kết quả ngay, nhưng có deadline một giờ và có thể quét hàng triệu bản ghi. Bạn có tạo global index chỉ để chạy báo cáo đó không?

**Gợi ý:** chưa thể quyết định chỉ từ tần suất. Cần xét tập dữ liệu, deadline, độ chọn lọc, chi phí bảo trì index, tải online, khả năng batch/analytics và đối soát.

### Bài 9 — Chỉ số đánh giá

Hai phương án có cùng `p95 = 80ms` trên dữ liệu thử. Phương án A hỏi 12 shard và ít index entries trên mỗi shard; phương án B hỏi 1 index partition nhưng key đó rất nóng.

Nên đo thêm gì trước khi chọn một phương án?

**Gợi ý:** p99 dưới peak, fan-out, throughput, hot partition/throttling, write cost, kích thước index, lag, phân bố request theo key.

### Bài 10 — Phân loại phát biểu

Chỉ ra phát biểu đúng hoặc sai và giải thích:

1. “DynamoDB LSI có thể thay partition key của bảng nguồn.”
2. “DynamoDB GSI cho phép strong consistent read nếu bật tùy chọn.”
3. “Global secondary index chắc chắn được lưu ở một node trung tâm.”
4. “Một truy vấn trên sharded MongoDB có thể scatter/gather dù mỗi shard có index phù hợp.”
5. “Secondary index có thể tăng chi phí ghi.”
6. “Có index theo email nghĩa là hệ thống đã bảo đảm email duy nhất.”

**Gợi ý:** lần lượt sai, sai, sai, đúng, đúng, sai.

## 27. Checklist khi thiết kế đường truy cập phụ

Có thể dùng mẫu sau trong tài liệu thiết kế:

~~~yaml
accessPattern:
  id: ORD-R-BY-SHOP-STATUS
  actor: "Shop operations dashboard"
  goal: "List newest PAID orders for one shop"
  inputs:
    - tenantId
    - shopId
    - status
    - timeRange
    - pageCursor
  sort: "createdAt DESC, orderId DESC"
  outputFields:
    - orderId
    - status
    - createdAt
    - totalMinor
  pageSize: 50
  consistency: "Define tolerated index lag"
  latencyTarget: "TBD"
  peakRps: "TBD"

dataLayout:
  sourcePartitionKey: "tenantId + customerId"
  proposedIndexScope: "Global alternate access path"
  indexPartitionKey: "tenantId + shopId + status + dayBucket"
  indexSortKey: "createdAt + orderId"
  indexProjection: "Minimal fields used by list"

risks:
  - "Hot shop/status/day keys"
  - "Source/index update lag"
  - "Status changes require index maintenance"
  - "Pagination across time buckets"
  - "Tenant authorization"
  - "Write amplification"

verification:
  - "Inspect query routing and fan-out"
  - "Measure keys examined and base fetches"
  - "Measure p95/p99 under peak load"
  - "Measure index storage and write cost"
  - "Check read-after-write expectations"
  - "Exercise migration/rebuild strategy"
~~~

Đây là **mẫu đặc tả minh họa**, không phải cấu hình tự động tạo index cho một DBMS. Các trường chưa biết như `TBD` phải được khảo sát; thiết kế index nên được quyết định từ workload thật, không chỉ từ tên field.

## 28. Tổng kết

Để phân biệt **chỉ mục phụ cục bộ** và **chỉ mục phụ toàn cục** trong NoSQL, hãy nhớ:

1. **Chỉ mục phụ bổ sung đường tra cứu theo thuộc tính khác khóa chính.** Nó không tự động giúp mọi truy vấn có filter, sort và phân trang đều hiệu quả.
2. **Locality phải được định nghĩa theo DBMS.** DynamoDB LSI giữ cùng partition key với bảng nguồn; index truyền thống trên các node Cassandra và index trên shard MongoDB có cơ chế tổ chức khác.
3. **Global index là đường truy cập rộng hơn hoặc độc lập hơn với partition nguồn**, không có nghĩa tất cả index entries nằm trên một máy. DynamoDB GSI là ví dụ rõ ràng về một index có partition key riêng.
4. **Global query không đồng nghĩa global index.** Trong sharded MongoDB hoặc search engine, một query toàn cluster có thể được thực thi bằng index cục bộ và scatter/gather.
5. **Index phải phù hợp query shape.** Tenant, shop, status, khoảng thời gian, thứ tự và pagination đều ảnh hưởng lựa chọn khóa index. Index theo một field cardinality thấp có nguy cơ hot và trả quá nhiều kết quả.
6. **Đọc nhanh có chi phí ở phía ghi và đồng bộ.** Secondary index tốn dung lượng, write amplification và có thể tạo lag; GSI DynamoDB chỉ hỗ trợ eventually consistent reads.
7. **Index không tự bảo đảm tính đúng đắn nghiệp vụ.** Uniqueness, authorization, trạng thái thanh toán và dữ liệu cần nhất quán mạnh phải được bảo vệ bằng cơ chế thích hợp.
8. **Đánh giá bằng fan-out và kế hoạch thực thi.** Cần biết query chạm bao nhiêu shard/partition, xem bao nhiêu index entries, fetch thêm bao nhiêu base records và tác động lên write path.

**Nguyên tắc thực hành:** trước khi chọn local hoặc global secondary index, hãy xác định **khóa đầu vào của truy vấn**, **cách dữ liệu nguồn được phân vùng**, **cách chỉ mục được định tuyến/cập nhật** và **bảo đảm kết quả cần đạt**. Cùng một từ “secondary index”, mỗi kiến trúc NoSQL có thể đưa ra một đánh đổi rất khác.
