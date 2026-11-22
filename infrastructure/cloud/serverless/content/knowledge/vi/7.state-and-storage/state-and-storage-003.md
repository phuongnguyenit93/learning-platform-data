# Mô hình truy cập dữ liệu và thiết kế khóa cho NoSQL

Trong ứng dụng serverless, Java function thường khởi động khi có HTTP request, message hoặc event, thực hiện một phần nghiệp vụ rồi kết thúc. Database phải lưu trạng thái giữa các lần invocation và phục vụ nhiều function chạy đồng thời. Với NoSQL phân tán, hiệu năng và chi phí phụ thuộc lớn vào cách ứng dụng truy cập dữ liệu và cách dữ liệu được phân vùng. Một schema có vẻ gọn nhưng không hỗ trợ truy vấn chính có thể khiến mỗi request phải quét nhiều bản ghi, tạo nhiều lần gọi mạng hoặc dồn tải vào một partition.

Thiết kế NoSQL vì vậy bắt đầu từ câu hỏi: **ứng dụng cần đọc và ghi dữ liệu theo những cách nào?** Sau khi liệt kê các access pattern, ta mới chọn cấu trúc item/document, partition key, sort key, index và chiến lược phân phối tải. Đây là cách tiếp cận phù hợp với nhiều kho key-value và wide-column phân tán. Document database và graph database có những đặc điểm truy vấn riêng, nhưng vẫn cần xác định workload, index, giới hạn truy vấn và cách mở rộng trước khi thiết kế.

## 1. NoSQL không phải một kiểu database duy nhất

NoSQL là nhóm các hệ quản trị dữ liệu có mô hình và trade-off khác nhau. Không nên áp dụng một công thức khóa cho tất cả.

| Nhóm dữ liệu | Cấu trúc thường gặp | Truy vấn mạnh | Điều cần chú ý |
|---|---|---|---|
| Key-value | Một khóa xác định một giá trị/item | Đọc/ghi theo khóa | Khả năng truy vấn phụ thuộc key và index được hỗ trợ |
| Wide-column | Partition key, clustering/sort columns và các cột | Đọc một partition hoặc một dải khóa có thứ tự | Phải thiết kế partition, clustering và kích thước partition |
| Document | JSON/BSON hoặc document tương tự | Tìm theo field, nested field và index | Index, kích thước document và query plan ảnh hưởng hiệu năng |
| Graph | Node, edge và thuộc tính | Traversal theo quan hệ | Mô hình quan hệ và độ sâu traversal quyết định chi phí |

Các khái niệm partition key, sort key và item collection đặc biệt quan trọng với kho key-value/wide-column phân tán. Với document store, khóa chính thường định danh document còn secondary index phục vụ truy vấn theo field. Với graph store, thiết kế cần ưu tiên quan hệ và traversal. Bài này tập trung vào access pattern và thiết kế khóa của kho NoSQL phân tán dạng key-value/wide-column, đồng thời chỉ ra phần có thể áp dụng rộng hơn.

## 2. Bắt đầu từ access pattern

Access pattern mô tả một thao tác dữ liệu mà ứng dụng cần thực hiện, bao gồm điều kiện tìm kiếm, thứ tự, giới hạn kết quả và cách cập nhật. Không chỉ ghi “đọc đơn hàng”; hãy ghi cụ thể “đọc một đơn hàng theo tenant và order ID”, “liệt kê đơn hàng mới nhất của khách hàng” hoặc “tìm các đơn đang chờ thanh toán trong một vùng”.

Ví dụ ứng dụng đặt hàng có thể có các access pattern sau:

| Mã | Thao tác | Điều kiện | Kết quả mong muốn |
|---|---|---|---|
| AP1 | Lấy đơn hàng | `tenantId + orderId` | Một đơn hàng |
| AP2 | Liệt kê đơn của khách hàng | `tenantId + customerId`, sắp xếp mới nhất trước | Một trang đơn hàng |
| AP3 | Lấy các đơn đang chờ thanh toán | `tenantId + status`, sắp xếp theo thời điểm tạo | Một trang công việc |
| AP4 | Lấy chi tiết đơn | `tenantId + orderId` | Đơn hàng và các dòng hàng |
| AP5 | Cập nhật trạng thái đơn | `tenantId + orderId`, kiểm tra version hiện tại | Một lần cập nhật có điều kiện |
| AP6 | Tra cứu event đã xử lý | `consumerName + eventId` | Một dấu inbox hoặc không có |

Với mỗi pattern, cần xác định tần suất đọc/ghi, số item trung bình và tối đa, kích thước dữ liệu, độ trễ mục tiêu, yêu cầu nhất quán và khả năng tăng trưởng. Một pattern được gọi rất nhiều lần có thể ảnh hưởng đến thiết kế partition nhiều hơn một pattern chỉ chạy trong tác vụ quản trị hiếm gặp.

Một bảng thiết kế hữu ích có thể thêm các cột `QPS đọc`, `QPS ghi`, `p95 mục tiêu`, `kích thước trang`, `consistency` và `SLA`. Ước lượng này không cần chính xác ngay từ đầu; nó giúp phát hiện sớm các pattern có nguy cơ tạo hotspot hoặc chi phí index cao.

## 3. Quy tắc thiết kế dữ liệu theo truy vấn

Trong cơ sở dữ liệu quan hệ, mô hình thường bắt đầu từ entity và quan hệ rồi dùng join để tạo kết quả. Trong nhiều kho NoSQL phân tán, join giữa các entity không phải thao tác rẻ hoặc thậm chí không được hỗ trợ. Ứng dụng thường đọc một item collection đã được sắp xếp theo khóa, hoặc dùng index được tạo trước cho một pattern.

Điều này dẫn đến một số nguyên tắc:

1. Liệt kê các truy vấn cần hỗ trợ trước khi quyết định cấu trúc lưu trữ.
2. Mỗi truy vấn quan trọng phải có đường truy cập bằng khóa hoặc index phù hợp.
3. Đưa dữ liệu thường được đọc cùng nhau vào cùng item collection hoặc cùng document nếu kích thước và vòng đời phù hợp.
4. Chấp nhận denormalization có chủ đích khi nó giảm số lần đọc hoặc tránh join nóng.
5. Xác định cách cập nhật bản sao dữ liệu và mức eventual consistency mà nghiệp vụ chấp nhận.
6. Kiểm tra giới hạn partition, item/document size, transaction, index và throughput của dịch vụ cụ thể.

Denormalization không có nghĩa là sao chép mọi field vào mọi nơi. Mỗi bản sao cần có mục đích truy vấn rõ, chủ sở hữu dữ liệu và chiến lược cập nhật. Nếu cùng một thông tin được sao chép vào nhiều projection, cần chấp nhận độ trễ cập nhật và có cơ chế rebuild khi consumer bỏ lỡ event.

## 4. Partition key và sort key

Trong kho key-value/wide-column phân tán, partition key xác định nhóm dữ liệu được lưu hoặc định tuyến cùng một partition logic. Sort key (còn gọi là clustering key hoặc range key tùy hệ quản trị) sắp xếp item bên trong nhóm đó. Một primary key có thể chỉ gồm partition key hoặc là tổ hợp partition key và sort key.

Ví dụ với dữ liệu đơn hàng:

```text
Partition key (PK)        Sort key (SK)                 Item type
TENANT#t-42#ORDER#o-1001  META                         Order metadata
TENANT#t-42#ORDER#o-1001  LINE#0001                    Order line 1
TENANT#t-42#ORDER#o-1001  LINE#0002                    Order line 2
TENANT#t-42#ORDER#o-1001  PAYMENT#p-88                 Payment reference
TENANT#t-42#ORDER#o-1002  META                         Order metadata
TENANT#t-42#CUSTOMER#c-7  ORDER#2026-11-17T10:30#o-1001 Customer order index
```

Các item có cùng partition key tạo thành một item collection. Với `TENANT#t-42#ORDER#o-1001`, ứng dụng có thể lấy metadata, các dòng hàng và tham chiếu thanh toán bằng một truy vấn theo partition key, có thể giới hạn sort key bằng prefix hoặc range tùy database.

Sort key nên mã hóa thứ tự hoặc loại item theo cách có thể truy vấn. Một pattern thường dùng là `TYPE#timestamp#uniqueId`; timestamp ở định dạng có thứ tự từ điển tương ứng thứ tự thời gian, chẳng hạn ISO-8601 UTC với độ chính xác thống nhất. Thêm unique ID để hai item cùng thời điểm không đè lên nhau.

### Ví dụ đọc theo khóa

```text
GetItem:
  PK = TENANT#t-42#ORDER#o-1001
  SK = META

Query:
  PK = TENANT#t-42#ORDER#o-1001
  SK begins_with LINE#

Query:
  PK = TENANT#t-42#CUSTOMER#c-7
  SK between ORDER#2026-11-01 and ORDER#2026-12-01
  ScanIndexForward = false
```

Các cú pháp trên minh họa mô hình truy vấn, không phải cú pháp chung của mọi nhà cung cấp. Một database có thể dùng `partition key`, `clustering column`, `range key` hoặc document index với tên gọi khác.

## 5. Chọn partition key để phân phối tải

Partition key ảnh hưởng đến nơi dữ liệu được phân phối và cách tải đọc/ghi được chia giữa các partition. Một khóa tốt thường có cardinality đủ cao và phân bố hoạt động tương đối đều. Khóa có ít giá trị hoặc một giá trị nhận phần lớn request dễ tạo hot partition.

Ví dụ các lựa chọn:

| Partition key | Ưu điểm | Rủi ro |
|---|---|---|
| `status` | Dễ truy vấn tất cả đơn theo trạng thái | Giá trị ít; `PENDING` có thể trở thành hotspot |
| `tenantId` | Dễ cô lập dữ liệu theo tenant | Tenant lớn có thể chiếm phần lớn tải trong một partition logic |
| `orderId` | Cardinality cao, phân phối tốt | Không trực tiếp liệt kê tất cả đơn của một khách hàng |
| `customerId` | Truy vấn đơn theo khách hàng thuận tiện | Khách hàng rất lớn hoặc có hoạt động cao có thể tạo partition nóng |
| `tenantId#shard` | Chia tải của tenant lớn | Truy vấn phải biết hoặc fan-out qua nhiều shard |

Không chỉ nhìn số lượng khóa khác nhau. Hãy xem phân bố request theo khóa. Một khóa có hàng triệu giá trị vẫn có thể nóng nếu 30% traffic dồn vào một khách hàng hoặc một tenant. Dữ liệu lịch sử cũng cần được xem xét: partition key đều ở thời điểm hiện tại có thể trở nên lệch khi một tenant tăng trưởng.

### Hot partition và write sharding

Hot partition xuất hiện khi một partition nhận lượng request hoặc dung lượng vượt mức mà dịch vụ có thể phục vụ ổn định. Dấu hiệu thường là throttling, latency tăng, retry tăng và phân bố capacity lệch.

Nếu một tenant hoặc một aggregate có lưu lượng ghi rất cao, có thể thêm shard suffix:

```text
PK = TENANT#t-42#SHARD#00
PK = TENANT#t-42#SHARD#01
...
PK = TENANT#t-42#SHARD#15
```

Ứng dụng chọn shard bằng hash của một ID ổn định hoặc phân phối round-robin. Cách này tăng số partition có thể nhận ghi, nhưng truy vấn toàn tenant phải đọc nhiều shard rồi hợp nhất kết quả. Phân trang toàn cục cũng phức tạp hơn vì cần giữ continuation state cho từng shard. Chỉ dùng write sharding khi số liệu cho thấy hotspot và có thể chấp nhận chi phí fan-out đọc.

Một lựa chọn khác là thêm thời gian vào khóa cho dữ liệu append-only, ví dụ `TENANT#t-42#DAY#2026-11-17`. Cách này giới hạn kích thước một nhóm theo ngày nhưng truy vấn qua nhiều ngày cần đọc nhiều partition. Chọn độ phân đoạn thời gian theo tốc độ ghi, thời gian lưu và phạm vi truy vấn.

## 6. Thiết kế sort key và composite key

Sort key thường hỗ trợ lấy một loại item, một dải thời gian hoặc một tập con có thứ tự. Composite key ghép nhiều thành phần thành một chuỗi có quy ước delimiter và encoding.

Ví dụ:

```text
PK = TENANT#t-42#CUSTOMER#c-7
SK = ORDER#2026-11-17T10:30:00.000Z#o-1001
```

Truy vấn theo customer có thể đọc các order mới nhất trước. Khi cần lọc theo loại item, prefix giúp phân biệt `ORDER#`, `ADDRESS#` hoặc `PREFERENCE#`.

Quy tắc xây composite key:

- Dùng prefix rõ nghĩa để tránh va chạm giữa các loại entity.
- Chuẩn hóa chữ hoa/thường, Unicode, delimiter và timezone.
- Encode hoặc escape giá trị đầu vào nếu chúng có thể chứa delimiter.
- Đưa trường dùng để sắp xếp vào vị trí phù hợp; dùng định dạng fixed-width hoặc ISO-8601 UTC nếu cần thứ tự từ điển.
- Thêm unique tie-breaker khi hai record có thể có cùng timestamp.
- Không đưa dữ liệu bí mật hoặc thông tin cá nhân trực tiếp vào key.
- Giữ quy tắc key ổn định; thay đổi cách tạo key thường đồng nghĩa di chuyển dữ liệu hoặc hỗ trợ hai phiên bản key trong thời gian chuyển đổi.

Không ghép quá nhiều field vào key chỉ để tránh tạo index. Key phải hỗ trợ các pattern có thật và giữ được khả năng phân phối tải. Nếu một query cần tìm theo một thuộc tính không nằm trong primary key, cân nhắc secondary index hoặc projection riêng thay vì tạo một key quá phức tạp.

## 7. Item collection và mô hình một bảng

Một số kho NoSQL cho phép lưu nhiều loại item trong cùng bảng với partition key và sort key. Mô hình này thường được gọi là single-table design. Mỗi loại item có thể có thuộc tính khác nhau nhưng chia sẻ cấu trúc khóa.

Ví dụ:

| PK | SK | Thuộc tính chính | Access pattern |
|---|---|---|---|
| `TENANT#t-42#ORDER#o-1001` | `META` | status, total, createdAt | Lấy đơn theo ID |
| `TENANT#t-42#ORDER#o-1001` | `LINE#0001` | productId, quantity, price | Lấy dòng hàng của đơn |
| `TENANT#t-42#ORDER#o-1001` | `PAYMENT#p-88` | paymentStatus, providerRef | Lấy payment của đơn |
| `TENANT#t-42#CUSTOMER#c-7` | `ORDER#2026-11-17T10:30#o-1001` | orderId, total, status | Liệt kê đơn của khách hàng |
| `TENANT#t-42#STATUS#PENDING` | `2026-11-17T10:30#o-1001` | orderId, customerId | Liệt kê đơn pending qua index hoặc projection |

Single-table design có thể giảm số lần đọc và giúp lấy các item liên quan trong một query. Đổi lại, cấu trúc khóa và access pattern cần được thiết kế kỹ; tên thuộc tính có thể khác nhau giữa item type, index cần được quản lý cẩn thận và truy vấn ad hoc thường khó hơn.

Nhiều bảng hoặc collection cũng là lựa chọn hợp lý khi các entity có vòng đời, quyền sở hữu, throughput hoặc access pattern rất khác nhau. Không có quy tắc rằng mọi ứng dụng NoSQL phải dùng một bảng duy nhất. Hãy so sánh độ phức tạp vận hành và chi phí truy vấn của từng phương án.

## 8. Secondary index: mở rộng đường truy cập

Khi primary key không phục vụ một access pattern quan trọng, database có thể hỗ trợ secondary index. Index tạo một đường truy cập bổ sung dựa trên thuộc tính khác.

Các dạng thường gặp:

- **Global secondary index (GSI):** có partition/sort key riêng, cho phép truy vấn theo một cách phân vùng khác với bảng gốc. Dữ liệu index có thể được cập nhật bất đồng bộ và đọc có thể eventual consistent tùy dịch vụ.
- **Local secondary index (LSI):** dùng cùng partition key với bảng gốc nhưng có sort key khác, nếu database hỗ trợ. Thường có giới hạn cấu trúc và phải được xác định khi tạo bảng.
- **Secondary index của document store:** index một hoặc nhiều field, có thể gồm compound, sparse, partial hoặc multikey index tùy sản phẩm.

Ví dụ để tìm đơn hàng theo trạng thái và thời gian:

```text
Base table:
  PK = TENANT#t-42#ORDER#o-1001
  SK = META

GSI1:
  GSI1PK = TENANT#t-42#STATUS#PENDING
  GSI1SK = 2026-11-17T10:30:00.000Z#o-1001
```

Khi trạng thái thay đổi từ `PENDING` sang `PAID`, ứng dụng cập nhật thuộc tính index để item rời khỏi nhóm pending và xuất hiện trong nhóm paid. Nếu index được cập nhật bất đồng bộ, một khoảng thời gian ngắn có thể thấy kết quả cũ hoặc chưa thấy kết quả mới. API cần quyết định có thể chấp nhận eventual consistency hay cần đọc lại từ nguồn chính.

Mỗi index có chi phí lưu trữ và ghi. Khi một item được thêm, cập nhật hoặc xóa, các index liên quan cũng cần được cập nhật. Thêm index cho mọi field làm tăng write amplification, dung lượng và độ phức tạp. Chỉ tạo index để hỗ trợ access pattern có giá trị; đo số lần query và độ trễ trước khi giữ index lâu dài.

### Sparse index

Một số database chỉ đưa item vào index khi item có thuộc tính khóa index. Đây là sparse index. Ví dụ, chỉ các đơn hàng có `nextActionAt` mới được đưa vào index xử lý công việc đến hạn. Các đơn đã hoàn tất không cần xuất hiện trong index đó. Sparse index có thể giảm dung lượng và chi phí quét so với index mọi item, nếu dịch vụ hỗ trợ semantics này.

## 9. Denormalization và read model

NoSQL thường dùng denormalization để phục vụ truy vấn mà không cần join. Ví dụ, item đơn hàng có thể lưu `customerName` tại thời điểm đặt hàng để hiển thị lịch sử đơn mà không phải đọc thêm customer profile. Read model cho dashboard có thể tổng hợp số đơn theo ngày và trạng thái.

Khi dữ liệu gốc thay đổi, bản sao cần được cập nhật. Có thể cập nhật đồng bộ trong cùng transaction nếu database hỗ trợ, hoặc phát event để consumer cập nhật projection bất đồng bộ. Phương án bất đồng bộ tạo eventual consistency: read model có thể chậm hơn nguồn chính.

Trước khi denormalize, hãy trả lời:

1. Bản sao phục vụ truy vấn nào và ai sở hữu nó?
2. Khi dữ liệu nguồn đổi, bản sao được cập nhật bằng transaction, outbox hay event consumer?
3. Nếu event bị giao trùng hoặc đến sai thứ tự, projection xử lý thế nào?
4. Có thể rebuild bản sao từ nguồn chính hoặc event history không?
5. API có thể hiển thị dữ liệu trễ trong bao lâu?

Đối với dữ liệu có tính lịch sử, lưu snapshot giá trị tại thời điểm nghiệp vụ có thể đúng hơn việc luôn đồng bộ theo profile hiện tại. Ví dụ, hóa đơn thường cần giữ tên và địa chỉ tại thời điểm phát hành để đảm bảo tính nhất quán lịch sử.

## 10. Phân trang và truy vấn theo dải

Với tập dữ liệu lớn, tránh tải toàn bộ kết quả vào một function invocation. Dùng giới hạn trang và continuation token/cursor. Nhiều NoSQL database trả về khóa tiếp tục như `LastEvaluatedKey`, continuation token hoặc cursor; request kế tiếp gửi lại token để tiếp tục từ vị trí đã đọc.

Ví dụ API:

```http
GET /customers/c-7/orders?limit=25&cursor=eyJwayI6Li4ufQ
```

```json
{
  "items": [
    { "orderId": "o-1001", "status": "PAID" },
    { "orderId": "o-1000", "status": "PENDING" }
  ],
  "nextCursor": "eyJwayI6Li4ufQ"
}
```

Cursor nên được encode và ký hoặc bảo vệ ở server nếu nó chứa key nội bộ. Không để client sửa partition key, tenant ID hoặc điều kiện truy vấn tùy ý thông qua cursor. Giới hạn page size để tránh một request kéo quá nhiều dữ liệu và tiêu tốn memory/time của function.

Offset pagination (`page=100`) thường kém phù hợp với partitioned NoSQL vì database có thể phải bỏ qua nhiều item trước khi trả trang. Cursor/keyset pagination thường ổn định và tiết kiệm hơn. Nếu dữ liệu thay đổi trong lúc người dùng chuyển trang, kết quả có thể không phải snapshot nhất quán; nếu nghiệp vụ cần snapshot, phải dùng khả năng snapshot hoặc version/cutoff phù hợp.

Với query fan-out qua nhiều shard, mỗi shard có continuation token riêng. API có thể lưu chúng trong cursor tổng hợp và hợp nhất kết quả theo thứ tự. Thiết kế này tăng độ phức tạp và chi phí; nên tránh fan-out nếu có thể phục vụ pattern bằng một partition hoặc một index được phân phối tốt.

## 11. Nhất quán, cập nhật có điều kiện và concurrency

Function serverless có thể chạy đồng thời trên nhiều instance. Hai invocation có thể cùng đọc một giá trị rồi ghi đè kết quả của nhau. Không nên dựa vào thứ tự gọi function hoặc một biến trong bộ nhớ để bảo vệ dữ liệu.

Các cơ chế phổ biến:

- **Conditional write:** chỉ cập nhật khi điều kiện còn đúng, ví dụ `status = PENDING` hoặc item chưa tồn tại.
- **Optimistic locking:** lưu `version`; cập nhật với điều kiện version hiện tại bằng giá trị đã đọc, rồi tăng version.
- **Atomic counter:** dùng thao tác tăng/giảm nguyên tử khi database hỗ trợ, thay vì read-modify-write ở ứng dụng.
- **Transaction:** nhóm các thay đổi cần commit hoặc rollback cùng nhau trong giới hạn số item, partition và thời gian của database.
- **Idempotency key:** bảo vệ thao tác tạo tài nguyên khỏi request retry hoặc message redelivery.

Ví dụ optimistic locking:

```text
Read order:
  orderId = o-1001
  status = PENDING
  version = 7

Conditional update:
  SET status = PAID, version = 8
  IF version = 7 AND status = PENDING
```

Nếu invocation khác đã cập nhật version thành 8, điều kiện thất bại. Ứng dụng phải đọc lại và quyết định thử lại, trả conflict hoặc áp dụng quy tắc nghiệp vụ khác. Không retry vô hạn một conflict do nghiệp vụ.

Không phải mọi NoSQL database đều hỗ trợ transaction giống nhau. Có dịch vụ chỉ hỗ trợ atomicity trong một item, có dịch vụ hỗ trợ transaction nhiều item trong giới hạn nhất định. Hãy thiết kế ranh giới transaction theo khả năng thực tế, không giả định có ACID xuyên nhiều partition hoặc nhiều dịch vụ.

## 12. Ví dụ Java: tạo key bằng một nơi duy nhất

Tách logic xây khóa khỏi handler giúp tránh việc các function tạo key không nhất quán. Ví dụ dưới đây minh họa một convention cho bảng đơn hàng; repository adapter sẽ ánh xạ nó sang SDK cụ thể.

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class OrderKeys {
    private static final DateTimeFormatter SORT_TIME =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
                    .withZone(ZoneOffset.UTC);

    private OrderKeys() {}

    public static String orderPk(String tenantId, String orderId) {
        return "TENANT#" + safe(tenantId) + "#ORDER#" + safe(orderId);
    }

    public static String metadataSk() {
        return "META";
    }

    public static String lineSk(int lineNumber) {
        return "LINE#%04d".formatted(lineNumber);
    }

    public static String customerOrderPk(String tenantId, String customerId) {
        return "TENANT#" + safe(tenantId) + "#CUSTOMER#" + safe(customerId);
    }

    public static String customerOrderSk(Instant createdAt, String orderId) {
        return "ORDER#" + SORT_TIME.format(createdAt) + "#" + safe(orderId);
    }

    private static String safe(String value) {
        if (value == null || value.isBlank()
                || value.contains("#") || value.contains("\n")) {
            throw new IllegalArgumentException("Invalid key component");
        }
        return value;
    }
}
```

Trong code production, có thể dùng một hàm encode thay vì từ chối delimiter, tùy định dạng ID. Cần bảo đảm mọi writer và reader dùng cùng một quy tắc. Định dạng timestamp ở ví dụ có độ chính xác mili giây; nếu nhiều record cùng timestamp, order ID làm tie-breaker. Không thay formatter sau khi dữ liệu đã tồn tại mà không có kế hoạch migration.

## 13. Ví dụ Java: repository bám theo access pattern

Tầng domain không nên biết tên index hoặc cấu trúc key của một nhà cung cấp. Repository có thể diễn tả thao tác theo ngôn ngữ nghiệp vụ, còn adapter chuyển nó thành `GetItem`, `Query`, index query hoặc lệnh tương ứng.

```java
import java.util.List;
import java.util.Optional;

public record OrderSummary(
        String orderId,
        String status,
        long total) {}

public record Page<T>(List<T> items, String nextCursor) {}

public interface OrderRepository {
    Optional<Order> findById(String tenantId, String orderId);

    Page<OrderSummary> findRecentByCustomer(
            String tenantId,
            String customerId,
            int pageSize,
            String cursor);

    boolean changeStatus(
            String tenantId,
            String orderId,
            long expectedVersion,
            String newStatus);
}
```

`findRecentByCustomer` tương ứng access pattern AP2 và có thể dùng partition key của customer cùng sort key theo thời gian. `changeStatus` tương ứng AP5 và nên được triển khai bằng conditional update. `cursor` được adapter giải mã và kiểm tra; domain không cần phụ thuộc vào định dạng continuation token của database.

Không tạo một method tổng quát như `findByAnyField(Map<String, Object> filters)` nếu database không thể thực hiện hiệu quả mọi tổ hợp điều kiện. API linh hoạt kiểu đó dễ dẫn đến scan, query tốn kém và khó kiểm soát quyền truy cập. Hãy cung cấp method rõ ràng cho các access pattern được hỗ trợ.

## 14. Tác động của serverless lên thiết kế NoSQL

FaaS có thể tăng số invocation rất nhanh. Điều này tạo các yêu cầu đặc biệt cho database:

- **Connection và client:** tái sử dụng SDK client an toàn ở phạm vi instance để tránh khởi tạo kết nối cho mỗi request; không lưu trạng thái nghiệp vụ thay đổi trong biến static.
- **Concurrency:** giới hạn số invocation đồng thời theo throughput và connection limit của database. Nếu function scale đến hàng nghìn instance, một pool nhỏ trên mỗi instance vẫn có thể tạo tổng số kết nối lớn.
- **Retry:** lỗi throttling có thể kích hoạt retry đồng loạt. Dùng backoff/jitter, giới hạn concurrency và queue để điều tiết tải.
- **Timeout:** đặt timeout function, SDK và database hợp lý; không để client chờ lâu hơn giới hạn invocation mà không có cơ chế hủy hoặc tiếp tục workflow.
- **Cold start:** tạo client và tải cấu hình ở mức tối thiểu cần thiết; đo thời gian khởi tạo và độ trễ truy vấn trong môi trường gần production.
- **Chi phí:** theo dõi read/write capacity hoặc request units, storage, index, backup, network, retry và chi phí function. Một access pattern phải quét nhiều item có thể làm chi phí tăng theo dữ liệu.

Với workload bursty, queue giúp làm phẳng tốc độ ghi. Đặt maximum concurrency cho event source mapping hoặc cơ chế tương đương để database không bị quá tải. Khi queue backlog tăng, theo dõi tuổi message cũ nhất và throughput hoàn tất để quyết định có tăng worker hay điều tra bottleneck.

## 15. Multi-tenant và bảo mật khóa

Trong hệ thống nhiều tenant, tenant ID thường là một thành phần của partition key hoặc điều kiện truy vấn để dữ liệu được phân vùng theo tenant. Tuy nhiên, chỉ đưa tenant ID vào key không tự động bảo đảm cô lập dữ liệu. Mọi request phải lấy tenant từ danh tính đã xác thực hoặc context đáng tin cậy, không tin tenant ID tùy ý trong request body.

Các quy tắc cần áp dụng:

1. Repository luôn nhận tenant context và xây key có tenant prefix hoặc áp dụng filter/partition condition tương ứng.
2. Không cho client truyền trực tiếp PK/SK tùy ý vào API công khai.
3. Kiểm tra quyền trên từng resource, kể cả khi biết order ID.
4. Đặt giới hạn và theo dõi tenant có lưu lượng cao; có thể cần shard cho tenant lớn.
5. Không nhúng email, số điện thoại, access token hoặc dữ liệu bí mật vào key.
6. Mã hóa dữ liệu, quản lý quyền truy cập theo function/service và giới hạn quyền đọc backup/export.

Nếu dùng tenant ID làm partition key duy nhất, tenant lớn có thể tạo hot partition. Nếu thêm shard, phải có quy tắc ánh xạ tenant và khả năng query qua shard. Bảo mật và phân phối tải cần được xem xét cùng nhau.

## 16. TTL, vòng đời dữ liệu và lưu trữ dài hạn

Time to live (TTL) cho phép database tự động hết hạn item sau một thời điểm, nếu dịch vụ hỗ trợ. TTL hữu ích cho session, idempotency record, cache metadata, temporary workflow state hoặc dữ liệu tạm. Việc xóa có thể diễn ra bất đồng bộ sau thời điểm TTL; không nên dùng TTL như một bộ hẹn giờ chính xác để kích hoạt nghiệp vụ đúng một thời điểm.

Trước khi đặt TTL, cần xác định:

- Dữ liệu có thể xóa sau bao lâu và có yêu cầu kiểm toán hay không?
- Consumer còn có thể retry hoặc replay trong khoảng thời gian nào?
- Idempotency record cần tồn tại lâu hơn cửa sổ retry nào?
- Bản sao trong index, backup, stream hoặc archive có retention riêng không?
- Có cần xuất dữ liệu sang object storage/data lake trước khi hết hạn không?

Đối với lịch sử đơn hàng, hóa đơn hoặc dữ liệu kiểm toán, không đặt TTL chỉ để giảm storage khi chưa có chính sách retention và nghĩa vụ lưu trữ rõ ràng.

## 17. Thay đổi key và migration

Key schema là một phần của hợp đồng dữ liệu. Khi thay đổi partition key, sort key hoặc index, dữ liệu cũ không tự động chuyển sang cấu trúc mới. Migration có thể cần đọc và ghi lại item, tạo index mới, backfill, kiểm tra số lượng và chuyển traffic theo giai đoạn.

Một quy trình chuyển đổi an toàn thường gồm:

1. Thiết kế key version mới, ghi rõ access pattern nào được cải thiện và chi phí phát sinh.
2. Tạo index/table mới và kiểm tra bằng dữ liệu thử hoặc shadow traffic.
3. Backfill dữ liệu cũ theo batch có giới hạn để không làm quá tải database.
4. Trong giai đoạn chuyển tiếp, dual-write hoặc dùng outbox/CDC để giữ dữ liệu mới đồng bộ; tránh dual-write không có cơ chế phát hiện lệch.
5. So sánh kết quả đọc giữa key cũ và key mới; đo latency, throttling và số record thiếu.
6. Chuyển reader sang key mới, giữ đường rollback trong khoảng thời gian đã xác định.
7. Dừng ghi và xóa cấu trúc cũ sau khi xác nhận không còn consumer phụ thuộc.

Nếu key được tạo từ code ở nhiều function, cần phát hành thư viện hoặc module dùng chung và kiểm tra tương thích trước khi đổi convention. Không để từng service tự thay đổi delimiter, timezone hoặc casing.

## 18. Quan sát và tối ưu access pattern

Theo dõi hiệu năng theo từng access pattern thay vì chỉ theo tổng database. Một số chỉ số hữu ích:

- Số lần `Get`/`Query`/`Scan` hoặc loại operation tương ứng.
- Read/write units hoặc request units theo table, index và tenant.
- p50/p95/p99 latency theo repository method và access pattern.
- Số item đọc so với số item trả về; tỷ lệ scan/filter.
- Throttling, retry, conditional check failure và transaction conflict.
- Kích thước item/document, kích thước partition và phân bố tải theo partition key.
- Chi phí index, storage, backup, TTL cleanup và network.

Nếu query đọc hàng nghìn item rồi lọc còn vài item, có thể thiếu index hoặc key chưa phù hợp. Nếu một partition nhận tải cao bất thường, xem lại cardinality và skew. Nếu nhiều request cần đọc nhiều item riêng lẻ, cân nhắc batch get hoặc thiết kế item collection để lấy dữ liệu cùng lúc. Chỉ thay đổi schema sau khi đo được pattern và hiểu tác động đến writer, reader, index, cache và event consumer.

Không log toàn bộ document để chẩn đoán. Ghi access pattern name, thời gian, số item đọc/trả, index sử dụng, kết quả và ID tương quan đã được làm sạch. Tránh đưa partition key chứa thông tin cá nhân vào metric label có cardinality cao.

## 19. Khi nào NoSQL phù hợp và khi nào cần cân nhắc mô hình khác?

NoSQL phân tán phù hợp khi access pattern có thể xác định trước, cần throughput lớn, dữ liệu có cấu trúc linh hoạt hoặc cần scale theo partition. Nó đặc biệt hữu ích cho key lookup, item collection, event projection, session và workload serverless có tải biến động.

Cơ sở dữ liệu quan hệ có thể phù hợp hơn khi ứng dụng cần nhiều join linh hoạt, transaction nhiều bảng phức tạp, ràng buộc quan hệ mạnh hoặc truy vấn ad hoc thường xuyên. Graph database phù hợp khi traversal quan hệ là trọng tâm. Search engine phù hợp với tìm kiếm toàn văn và ranking. Có thể kết hợp nhiều loại store, mỗi loại phục vụ một access pattern, nhưng cần xác định nguồn dữ liệu chuẩn và cách đồng bộ giữa chúng.

Không chọn NoSQL chỉ vì hệ thống dùng serverless. Quyết định cần cân bằng latency, throughput, consistency, mô hình truy vấn, chi phí, khả năng vận hành và kỹ năng đội ngũ.

## 20. Checklist thiết kế

- [ ] Đã liệt kê access pattern cụ thể, tần suất, độ trễ và kích thước dữ liệu.
- [ ] Mỗi pattern quan trọng có đường truy cập bằng primary key hoặc index phù hợp.
- [ ] Partition key có cardinality và phân bố tải đủ tốt; đã xem xét tenant/aggregate lớn.
- [ ] Sort key hỗ trợ prefix/range/order cần thiết và có tie-breaker duy nhất.
- [ ] Composite key có quy ước delimiter, encoding, casing và timezone ổn định.
- [ ] Không có query quan trọng phải scan toàn bảng nếu không có lý do và ngân sách rõ ràng.
- [ ] Index chỉ phục vụ access pattern có giá trị và đã tính write/storage amplification.
- [ ] Denormalized copy có chủ sở hữu, cách cập nhật và kế hoạch rebuild.
- [ ] Pagination dùng cursor/continuation token và giới hạn page size.
- [ ] Conditional write/version/idempotency bảo vệ cập nhật đồng thời.
- [ ] Transaction nằm trong giới hạn thực tế của database.
- [ ] Multi-tenant access luôn ràng buộc tenant từ danh tính đáng tin cậy.
- [ ] TTL phù hợp với retry, replay, kiểm toán và retention.
- [ ] Có kế hoạch migration khi thay đổi key hoặc index.
- [ ] Đã đo throttling, latency, item read/write, hot partition và chi phí theo access pattern.
- [ ] Function concurrency, retry và queue được cấu hình theo năng lực database.

Thiết kế NoSQL tốt là thiết kế làm cho các truy vấn quan trọng đi theo đường khóa/index dự kiến, phân phối tải hợp lý và giữ được tính đúng đắn khi nhiều function chạy đồng thời. Bắt đầu từ access pattern, chọn partition và sort key theo cả truy vấn lẫn phân bố tải, sau đó kiểm chứng bằng metric thực tế. Với ứng dụng serverless, cách tiếp cận này giúp giảm scan và số lần gọi dữ liệu, kiểm soát concurrency, đồng thời giữ trạng thái nghiệp vụ bền vững qua các lần function invocation.
