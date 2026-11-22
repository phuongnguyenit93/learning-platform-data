# Phân biệt khóa truy cập, khóa phân vùng và khóa sắp xếp

## 1. Vì sao ba loại khóa dễ bị nhầm lẫn?

Khi thiết kế dữ liệu NoSQL, từ **khóa** (*key*) xuất hiện trong nhiều ngữ cảnh: “lấy đơn hàng bằng khóa”, “chọn partition key để chia tải”, “dùng sort key để liệt kê đơn hàng theo thời gian”. Ba cách nói này có liên quan nhưng giải quyết **ba câu hỏi khác nhau**:

1. **Khóa truy cập (access key):** Ứng dụng biết thông tin nào để tìm đúng dữ liệu cần đọc hoặc ghi?
2. **Khóa phân vùng (partition key):** Hệ thống dùng thông tin nào để xác định nhóm dữ liệu và đường định tuyến đến nơi phục vụ nhóm đó?
3. **Khóa sắp xếp (sort key):** Khi nhiều bản ghi thuộc cùng một nhóm, dựa vào thông tin nào để xác định thứ tự hoặc truy cập theo khoảng?

Hiểu đúng vai trò của từng khóa giúp chọn mô hình dữ liệu phù hợp với cách ứng dụng đọc/ghi, tránh quét dữ liệu không cần thiết và nhìn thấy nguy cơ một nhóm dữ liệu trở nên quá lớn hoặc quá nóng.

> **Phạm vi bài học:** Đây là mô hình tư duy chung cho NoSQL. Những tên như *partition key*, *sort key*, *clustering column*, *shard key*, *primary key* có nghĩa và bảo đảm cụ thể theo từng sản phẩm. Không được coi chúng là những tên thay thế hoàn toàn tương đương.

### Sau bài học, bạn sẽ làm được gì?

- Phân biệt **định danh dùng ở tầng ứng dụng** với **khóa dùng để phân phối dữ liệu**.
- Hiểu rằng sort key chỉ tạo thứ tự trong **phạm vi mà mô hình/sản phẩm định nghĩa**, không mặc định có một thứ tự toàn cục.
- Thiết kế cặp khóa phục vụ truy vấn “một khách hàng có các đơn hàng mới nhất nào?”.
- Nhận biết khi nào cần khóa ghép, chỉ mục phụ, bảng tra cứu bổ sung hoặc thay đổi mẫu truy cập.
- Đọc tài liệu DynamoDB, Cassandra, MongoDB và Redis mà không suy diễn API của hệ này sang hệ khác.

## 2. Định nghĩa ba vai trò qua một ví dụ

Giả sử dịch vụ bán hàng có các đơn:

| orderId | customerId | createdAt (UTC) | status | total |
|---|---|---|---|---:|
| O-101 | C-42 | 2026-11-14 09:00 | PAID | 180.000 |
| O-102 | C-42 | 2026-11-14 10:15 | PENDING | 220.000 |
| O-103 | C-42 | 2026-11-14 11:30 | PAID | 90.000 |
| O-104 | C-77 | 2026-11-14 10:45 | PAID | 310.000 |

Ứng dụng cần hai chức năng:

- **Q1:** lấy đơn theo mã đơn hàng `orderId`.
- **Q2:** lấy 20 đơn mới nhất của khách hàng `customerId`.

Đối với Q1, `orderId = O-103` có thể là **khóa truy cập** tự nhiên: ứng dụng biết mã đơn và muốn một kết quả duy nhất.

Đối với Q2, `customerId = C-42` là đầu vào để chọn **nhóm đơn hàng của khách hàng đó**. Nếu thiết kế một cấu trúc lưu theo khách hàng, `customerId` có thể đóng vai trò **khóa phân vùng logic**; `createdAt` kết hợp `orderId` có thể đóng vai trò **khóa sắp xếp** để lấy các đơn mới nhất, đồng thời tránh trùng khi hai đơn được tạo cùng thời điểm.

Ví dụ mô hình hóa:

~~~text
Partition key: customerId = "C-42"

    Sort key                          Value
    -------------------------------------------------------
    "2026-11-14T09:00:00Z#O-101"      {status: PAID, ...}
    "2026-11-14T10:15:00Z#O-102"      {status: PENDING, ...}
    "2026-11-14T11:30:00Z#O-103"      {status: PAID, ...}

Partition key: customerId = "C-77"

    Sort key                          Value
    -------------------------------------------------------
    "2026-11-14T10:45:00Z#O-104"      {status: PAID, ...}
~~~

Đây là sơ đồ **nhóm khóa ở mức logic**, chưa nói mỗi nhóm nằm trên một ổ đĩa hoặc một máy riêng. Trong nhiều hệ thống, rất nhiều giá trị partition key cùng chia sẻ một phân vùng vật lý; một nhóm lớn cũng có thể được hệ thống tổ chức hoặc phân chia nội bộ theo cơ chế riêng.

## 3. Khóa truy cập: thứ mà ứng dụng dùng để tìm dữ liệu

**Khóa truy cập** là cách gọi ở tầng thiết kế ứng dụng cho thông tin đã biết tại thời điểm thao tác. Nó có thể là một định danh đơn, một khóa ghép, hoặc tập điều kiện mà hệ thống có đường tra cứu hiệu quả.

Ví dụ:

~~~text
getOrderById(orderId = "O-103")
getCartByUserId(userId = "U-12")
getSessionByToken(sessionId = "s_a9...")
listOrdersByCustomer(customerId = "C-42")
getOrderByCustomerAndTime(customerId = "C-42", createdAt = ...)
~~~

Những tham số đầu vào này là dữ kiện của nghiệp vụ. Chúng không tự xác định database sẽ dùng bao nhiêu partition, cột khóa nào hay chỉ mục nào.

### 3.1. Định danh duy nhất và khóa dùng để truy vấn không luôn giống nhau

Một đơn hàng có thể được định danh duy nhất bằng `orderId`, nhưng màn hình lịch sử mua sắm lại truy cập theo `customerId` và `createdAt`. Nếu mô hình lưu chỉ tối ưu tìm theo `orderId`, chức năng lịch sử đơn hàng có thể không có đường đọc hiệu quả.

Cần phân biệt:

- **Định danh nghiệp vụ:** ví dụ mã đơn `O-103`, có thể phải duy nhất trên toàn hệ thống.
- **Khóa tra cứu thực tế:** ví dụ cặp `customerId` và `createdAt#orderId` phục vụ lịch sử đơn.
- **Định danh bản ghi trong một cấu trúc lưu trữ:** có thể là `orderId` hoặc một khóa ghép tùy mô hình.

Do đó, “đơn hàng có ID duy nhất” **không chứng minh** rằng truy vấn theo ID sẽ hiệu quả với mọi cấu trúc lưu, cũng không chứng minh rằng `orderId` bắt buộc là partition key.

### 3.2. Một khóa truy cập có thể gồm nhiều trường

Nếu ứng dụng biết `tenantId` và `customerId` thì có thể thiết kế một định danh ghép ở tầng ứng dụng:

~~~text
tenantId = "T-7"
customerId = "C-42"

accessKey = ("T-7", "C-42")
serializedKey = "TENANT#T-7#CUSTOMER#C-42"
~~~

Việc ghép chuỗi là **quy ước mã hóa khóa**, không có nghĩa database tự hiểu hai trường thành hai thành phần partition key. Có sản phẩm nhận nhiều trường khóa riêng; có sản phẩm nhận một chuỗi duy nhất; có sản phẩm sử dụng cấu trúc key khác hẳn.

### 3.3. Đừng nhầm truy cập theo khóa với lọc sau khi đọc

Ví dụ: ứng dụng cần “20 đơn hàng gần nhất đã thanh toán của C-42”.

- Nếu index/key cho phép lọc theo `customerId` và thứ tự thời gian, database có thể đọc một vùng dữ liệu tương đối hẹp rồi áp dụng điều kiện `status`.
- Nếu chỉ có index theo `orderId`, ứng dụng có thể phải quét nhiều đơn để tìm.
- Nếu `status` là bộ lọc **thực hiện sau khi đọc**, nó không nhất thiết giảm số bản ghi hay số bytes database phải đọc.

“API hỗ trợ filter” là một thuộc tính của sản phẩm. **“Filter được dùng để định tuyến và giảm chi phí đọc”** là câu hỏi riêng phải xác minh bằng tài liệu và kế hoạch truy vấn.

## 4. Khóa phân vùng: dùng để nhóm và định tuyến

Trong các cơ sở dữ liệu phân tán, dữ liệu phải được đặt ở những vị trí phục vụ cụ thể. Khóa phân vùng là thông tin mà mô hình lưu trữ hoặc hệ thống sử dụng để **xác định phân vùng logic/định tuyến**.

Một cách hình dung khái quát:

~~~mermaid
flowchart TD
    Q["Ứng dụng gửi request chứa khóa"] --> R["Xác định partition key"]
    R --> P["Cơ chế định tuyến: hash/token/range..."]
    P --> A["Nhóm hoặc phân vùng phục vụ A"]
    P --> B["Nhóm hoặc phân vùng phục vụ B"]
    P --> C["Nhóm hoặc phân vùng phục vụ C"]
    A --> X["Đọc/ghi và trả kết quả"]
    B --> X
    C --> X
~~~

Sơ đồ chỉ minh họa ý tưởng: chi tiết định tuyến, replication, nhiều replica, failover và vị trí vật lý phụ thuộc sản phẩm.

### 4.1. Khóa phân vùng không đồng nghĩa “một phân vùng vật lý”

Giả sử chọn `customerId` làm partition key. Điều này không có nghĩa mỗi khách hàng có một máy hoặc một file riêng. Hệ thống có thể ánh xạ nhiều giá trị partition key vào cùng một phân vùng vật lý. Địa chỉ vật lý có thể thay đổi khi thêm/bớt node hoặc cân bằng lại tải.

Phải tách ba khái niệm:

| Thành phần | Ý nghĩa |
|---|---|
| **Giá trị partition key** | Giá trị logic của bản ghi/nhóm, ví dụ `C-42` |
| **Partition logic** | Tập dữ liệu được xác định theo mô hình và quy tắc truy vấn |
| **Partition vật lý / shard / node** | Đơn vị triển khai và phân bổ tài nguyên do hệ thống quản lý |

Một số sản phẩm dùng từ *partition* theo những nghĩa đặc thù, vì vậy hãy đọc định nghĩa của sản phẩm đó.

### 4.2. Khóa phân vùng có ảnh hưởng đến khả năng phân phối tải

Nếu phần lớn request dồn vào một giá trị khóa, ví dụ `customerId = "super-customer"`, nhóm dữ liệu đó có thể trở thành **hot partition / hot key**. Cụm có nhiều node không tự giải quyết được vấn đề nếu mẫu truy cập tập trung vào cùng một điểm.

Tương tự, một partition key có quá ít giá trị khác nhau, ví dụ `status ∈ {PENDING, PAID, CANCELLED}`, có thể làm một số nhóm nhận khối lượng dữ liệu rất lớn. Dù vậy không thể kết luận từ số giá trị khác nhau (*cardinality*) mà bỏ qua phân bố lưu lượng, kích thước bản ghi, cơ chế chia vật lý và khả năng tự cân bằng của sản phẩm.

Hướng đánh giá:

1. Có bao nhiêu giá trị partition key khác nhau trong dữ liệu thật?
2. Mỗi giá trị nhận bao nhiêu lần đọc/ghi, kích thước và tốc độ tăng dữ liệu bao nhiêu?
3. Khóa nào là điểm nóng? Tải có lệch mạnh theo thời gian hoặc tenant không?
4. Hệ thống phân vùng vật lý, nhân bản, chia lại và giới hạn thông lượng thế nào?
5. Khi thay đổi khóa để chia tải, các truy vấn cần gom kết quả từ nhiều nhóm sẽ tốn thêm bao nhiêu công sức?

### 4.3. Khóa phân vùng đơn và ghép

Đôi khi cần dùng cả `tenantId` và `customerId` làm khóa phân vùng logic:

~~~text
Partition key = (tenantId, customerId)
~~~

Hoặc ứng dụng tự mã hóa thành một thuộc tính:

~~~text
Partition key = "TENANT#T-7#CUSTOMER#C-42"
~~~

Hai cách này **chỉ tương đương ở ý tưởng nhóm dữ liệu**; cú pháp, thứ tự so sánh, cách hash và điều kiện truy vấn có thể khác nhau. Không được giả định có thể tìm theo `customerId` mà bỏ qua `tenantId` chỉ vì cả hai cùng nằm trong khóa ghép.

## 5. Khóa sắp xếp: dùng để đặt thứ tự trong nhóm

**Sort key** thường được dùng để mô tả thành phần khóa phân biệt và sắp xếp các item **trong cùng một giá trị partition key**. Các tên tương ứng ở một số sản phẩm là *clustering key/column* hoặc *range key*.

Với lịch sử đơn hàng của khách:

~~~text
PK = CUSTOMER#C-42

SK = ORDER#2026-11-14T09:00:00Z#O-101
SK = ORDER#2026-11-14T10:15:00Z#O-102
SK = ORDER#2026-11-14T11:30:00Z#O-103
~~~

Nếu sản phẩm hỗ trợ thứ tự và phép truy vấn theo khoảng trên sort key, ứng dụng có thể:

- lấy item có đủ cả partition key và sort key;
- lấy các item thuộc `C-42` trong một khoảng thời gian;
- đọc theo thứ tự tăng hoặc giảm của sort key;
- lấy một số item đầu của thứ tự, rồi phân trang.

**Sort key không mặc nhiên sắp xếp toàn bộ database.** Hai nhóm khách hàng `C-42` và `C-77` được định tuyến theo partition key riêng. Nếu muốn “20 đơn mới nhất của tất cả khách hàng”, không thể suy ra rằng chỉ cần dùng sort key và một câu lệnh là có thứ tự toàn cục hiệu quả.

### 5.1. Thứ tự dữ liệu phụ thuộc kiểu và cách mã hóa

Một chuỗi và một con số không phải lúc nào cũng được sắp như nhau:

~~~text
Thứ tự chuỗi theo ký tự (minh họa):
"1", "10", "2"

Thứ tự số:
1, 2, 10
~~~

Nếu ghép số vào chuỗi sort key mà muốn thứ tự số, có thể phải dùng dạng độ rộng cố định:

~~~text
SEQ#000001
SEQ#000002
SEQ#000010
~~~

Với thời gian, có thể dùng dạng UTC ISO 8601 **chuẩn hóa cùng độ chính xác và cùng múi giờ** nếu sản phẩm sắp chuỗi theo cách tương thích:

~~~text
2026-11-14T09:00:00.000Z
2026-11-14T10:15:00.000Z
2026-11-14T11:30:00.000Z
~~~

Nếu timestamp có độ chính xác hoặc định dạng khác nhau, so sánh chuỗi có thể không phản ánh đúng thời gian thực. Trên một số hệ, sort key có kiểu timestamp hoặc số nguyên thay vì chuỗi nên cách sắp xếp khác.

### 5.2. Sort key nên đủ phân biệt để tránh ghi đè

Nếu dùng duy nhất `createdAt` làm sort key trong cặp `(customerId, createdAt)`, hai đơn phát sinh cùng thời điểm có thể trùng toàn bộ khóa. Một giải pháp là thêm mã đơn làm phần phân biệt:

~~~text
PK = CUSTOMER#C-42
SK = 2026-11-14T10:15:00.000Z#ORDER#O-102
~~~

Nhưng phép ghép này cần quy ước escape, độ dài, định dạng và tính duy nhất. Ở sản phẩm hỗ trợ nhiều clustering columns, có thể để timestamp và order ID thành các cột riêng. Kết luận quan trọng là **tính duy nhất của toàn bộ khóa** phải được xác định cho đúng cấu trúc lưu trữ.

### 5.3. Sort key có thể mã hóa loại đối tượng

Một số thiết kế dùng tiền tố để gom các loại dữ liệu trong cùng partition:

~~~text
PK = USER#42

SK = PROFILE#MAIN
SK = ADDRESS#HOME
SK = ORDER#2026-11-14T10:15:00Z#O-102
SK = ORDER#2026-11-14T11:30:00Z#O-103
~~~

Nếu hệ thống hỗ trợ truy vấn theo tiền tố của sort key, có thể lấy riêng nhóm đơn `ORDER#...`. Đây là **một mẫu thiết kế của hệ có sort key dạng chuỗi và API truy vấn thích hợp**; không phải mọi kho key–value đều hỗ trợ `begins_with`, truy vấn prefix hoặc thứ tự giống nhau.

## 6. Quan hệ giữa ba loại khóa

### 6.1. Bảng phân biệt trọng tâm

| Góc nhìn | Khóa truy cập | Khóa phân vùng | Khóa sắp xếp |
|---|---|---|---|
| Câu hỏi trả lời | “Ứng dụng biết gì để lấy dữ liệu?” | “Nhóm nào cần định tuyến đến?” | “Bản ghi nào, theo thứ tự nào trong nhóm?” |
| Tầng thiết kế | API và access pattern của ứng dụng | Mô hình lưu trữ và phân phối dữ liệu | Mô hình item/hàng, thứ tự và range query |
| Dạng phổ biến | Một ID, nhiều ID hoặc tổ hợp điều kiện | Một hoặc nhiều thuộc tính, đôi khi được mã hóa ghép | Thời gian, số thứ tự, ID phụ hoặc khóa ghép |
| Phạm vi | Theo thao tác nghiệp vụ | Theo nhóm/partition mà sản phẩm định nghĩa | Thường trong cùng một giá trị partition key |
| Ảnh hưởng chính | Có truy cập trực tiếp được không? | Cân bằng tải, nhóm dữ liệu và chi phí fan-out | Range, thứ tự và độ phân biệt trong nhóm |
| Có bắt buộc tồn tại? | Mọi ứng dụng đều có cách tìm dữ liệu, nhưng không nhất thiết gọi là một cột key | Tùy sản phẩm/mô hình; trong phân tán có cơ chế định tuyến | Không; có hệ chỉ dùng key đơn |

### 6.2. Một trường có thể giữ nhiều vai trò

Ví dụ một bảng có duy nhất `orderId` làm partition key, không có sort key. Ở đây `orderId` vừa là định danh nghiệp vụ, vừa là khóa truy cập cho Q1, vừa là partition key theo mô hình đó.

Ở một cấu trúc khác:

~~~text
PK = CUSTOMER#C-42
SK = ORDER#2026-11-14T11:30:00Z#O-103
~~~

Cặp `(PK, SK)` có thể đóng vai trò khóa chính của item, trong khi `customerId` là thành phần phân vùng, `createdAt#orderId` là thành phần sắp xếp, và `orderId` vẫn là ID nghiệp vụ của đơn.

Cùng một thuật ngữ “primary key” có thể chỉ **một trường duy nhất** hoặc **tổ hợp partition key và sort/clustering key** tùy sản phẩm. Vì vậy cần đọc lược đồ và tài liệu, thay vì suy từ tên gọi.

### 6.3. Quan hệ được thể hiện như thế nào?

~~~mermaid
flowchart TD
    A["Nhu cầu nghiệp vụ / API"] --> B["Thông tin truy cập đã biết"]
    B --> C{"Có đường đọc hiệu quả?"}
    C -->|Có| D["Chọn cấu trúc khóa và index"]
    C -->|Chưa| E["Thiết kế thêm access pattern / index"]
    E --> D
    D --> F["Partition key: định tuyến và nhóm"]
    D --> G["Sort/clustering key nếu có: thứ tự trong nhóm"]
    F --> H["Đọc/ghi theo bảo đảm của sản phẩm"]
    G --> H
~~~

Không thể chọn được partition key và sort key tốt nếu chưa biết ứng dụng sẽ đọc gì, ghi gì và dữ liệu phân bố thế nào.

## 7. Ví dụ thiết kế hoàn chỉnh với lịch sử đơn hàng

Giả sử hệ thống đa tenant phải hỗ trợ:

| Truy vấn | Dữ kiện có sẵn | Kết quả |
|---|---|---|
| Q1: Chi tiết đơn hàng | `tenantId`, `orderId` | Một đơn |
| Q2: Lịch sử mua hàng | `tenantId`, `customerId` | 20 đơn mới nhất và phân trang |
| Q3: Đơn trong khoảng thời gian | `tenantId`, `customerId`, từ ngày/đến ngày | Danh sách theo thời gian |
| Q4: Danh sách đơn chờ xử lý của tenant | `tenantId`, `status` | Nhiều đơn cần xử lý |

### 7.1. Đường truy cập Q2/Q3 theo khách hàng

Một mô hình khái niệm:

~~~text
PK = TENANT#<tenantId>#CUSTOMER#<customerId>
SK = ORDER#<utc-created-at>#<orderId>

Ví dụ:
PK = TENANT#T-7#CUSTOMER#C-42
SK = ORDER#2026-11-14T11:30:00.000Z#O-103
~~~

Khóa phân vùng chứa tenant và khách hàng để nhóm lịch sử đúng phạm vi. Sort key chứa thời gian và ID nhằm có thứ tự và phân biệt các đơn.

Truy vấn giả lập:

~~~text
QUERY(
  partitionKey = "TENANT#T-7#CUSTOMER#C-42",
  sortKeyPrefix = "ORDER#",
  sortDescending = true,
  limit = 20,
  cursor = optionalCursor
)
~~~

Đây là **mã giả mô tả ý định**. Không phải database nào cũng hỗ trợ prefix, giảm dần, cursor hoặc giới hạn theo cách như vậy. Với sort key mã hóa nhiều thành phần, cách đảo thứ tự phải phù hợp quy tắc sắp xếp thật của sản phẩm.

### 7.2. Q1 có thể không dùng được cấu trúc Q2

Khi API chỉ biết `orderId = O-103` mà không biết `customerId`, có thể **không tạo được PK của bảng Q2**. Vì thế không đủ thông tin cho truy cập trực tiếp bằng cặp khóa.

Các lựa chọn phổ biến:

- Có cấu trúc chính hoặc bảng tra cứu theo `(tenantId, orderId)`.
- Có chỉ mục phụ cho truy vấn theo `orderId` nếu hệ thống hỗ trợ và đáp ứng bảo đảm cần thiết.
- Thay đổi contract API để truyền thêm `customerId` nếu điều đó thật sự phù hợp nghiệp vụ và bảo mật.
- Duy trì hai phép chiếu dữ liệu cho hai access pattern; xác định rõ cơ chế đồng bộ.

Không nên “giải quyết” bằng cách quét mọi khách hàng để tìm một ID đơn. Điều này phá vỡ mục tiêu truy cập theo khóa.

### 7.3. Q4 là một access pattern khác

Để lấy mọi đơn có `status = PENDING` trong tenant, partition key theo khách hàng không cung cấp đường truy cập trực tiếp. Có thể tạo chỉ mục theo trạng thái hoặc một queue/luồng xử lý riêng.

Nếu dùng `status` làm partition key duy nhất, tập giá trị ít và luồng ghi tập trung có thể gây hotspot. Một cách nghiên cứu là chia theo tenant, thời gian, bucket hoặc thuộc tính phân phối phù hợp. Nhưng mỗi lần chia sẽ ảnh hưởng đến việc fan-out query và tổng hợp kết quả. Không có công thức “chọn partition key X luôn đúng” cho mọi tải.

### 7.4. Đọc nhanh không xóa chi phí duy trì dữ liệu

Nếu lưu hai cấu trúc:

~~~text
ordersById:
  (tenantId, orderId) -> order

ordersByCustomer:
  (tenantId, customerId, createdAt, orderId) -> order summary
~~~

thì thay đổi `status` cần cập nhật dữ liệu ở những vị trí phù hợp. Phải xác định một nguồn sự thật, cơ chế cập nhật, xử lý retry, lỗi giữa chừng, xóa và tính nhất quán của dữ liệu nhân bản.

Các chỉ mục do database quản lý có thể giải quyết một phần bài toán, nhưng phạm vi giao dịch và thời điểm index phản ánh cập nhật vẫn phải kiểm tra theo sản phẩm.

## 8. Nhìn sang các sản phẩm NoSQL cụ thể

Các khái niệm ở trên là khung tư duy. Tên và cú pháp khi triển khai **khác nhau theo database**.

### 8.1. Amazon DynamoDB: partition key và sort key trong primary key

Một bảng DynamoDB có thể dùng **simple primary key** chỉ gồm partition key hoặc **composite primary key** gồm partition key và sort key.

Ví dụ bảng `OrdersByCustomer`:

~~~text
Partition key (PK): TENANT#T-7#CUSTOMER#C-42
Sort key (SK):      ORDER#2026-11-14T11:30:00.000Z#O-103
Attributes:         orderId, status, total, ...
~~~

Trong bảng có khóa ghép, cặp `(PK, SK)` xác định item duy nhất. Truy vấn `Query` điển hình yêu cầu điều kiện bằng nhau trên partition key; có thể thêm điều kiện trên sort key để thu hẹp phạm vi và điều khiển chiều kết quả theo khả năng API. Khi biết cả PK và SK, có thể dùng thao tác truy cập item theo khóa đầy đủ. Khi chỉ biết `orderId` nằm trong thuộc tính thông thường, không thể mặc định truy cập trực tiếp bằng `GetItem`.

Một **global secondary index (GSI)** có thể có partition/sort key riêng để tạo một access pattern khác, nhưng hành vi cập nhật index, consistency và chi phí phải xét theo tài liệu hiện hành. `FilterExpression` không đồng nghĩa điều kiện truy cập bằng key; trong DynamoDB, filter được áp dụng sau bước đọc dữ liệu của `Query` hoặc `Scan`, nên không thể mặc định dùng filter để tránh chi phí đọc ban đầu.

Ví dụ hình thức gửi yêu cầu mang tính minh họa:

~~~json
{
  "TableName": "OrdersByCustomer",
  "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
  "ExpressionAttributeValues": {
    ":pk": {"S": "TENANT#T-7#CUSTOMER#C-42"},
    ":prefix": {"S": "ORDER#"}
  },
  "ScanIndexForward": false,
  "Limit": 20
}
~~~

Đây là phong cách payload DynamoDB cấp API thấp cho mục tiêu minh họa; code thực tế cần xem SDK, schema và xử lý phân trang. `Limit` trong tình huống có filter không nhất thiết bằng số item cuối cùng trả về; cần tiếp tục theo cơ chế pagination của dịch vụ.

### 8.2. Apache Cassandra: partition key và clustering columns

Trong Cassandra/CQL, một bảng có **primary key** gồm partition key và tùy chọn các clustering columns. Clustering columns xác định thứ tự hàng **bên trong partition** theo cấu hình của bảng.

Ví dụ:

~~~sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id uuid,
    status text,
    total bigint,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Ý nghĩa của lược đồ:

- `(tenant_id, customer_id)` trong dấu ngoặc kép ở phần primary key là **composite partition key** theo cú pháp CQL; cả hai thành phần cùng xác định partition.
- `created_at` và `order_id` là **clustering columns**, được dùng để phân biệt và sắp thứ tự hàng trong partition theo quy tắc đã khai báo.
- Giá trị của toàn bộ primary key xác định hàng duy nhất trong bảng.

Ví dụ truy vấn theo khách hàng:

~~~sql
SELECT order_id, created_at, status, total
FROM orders_by_customer
WHERE tenant_id = 'T-7'
  AND customer_id = 'C-42'
LIMIT 20;
~~~

Bảng được cấu hình sắp xếp `created_at DESC` trong partition. Nếu ứng dụng cần cách sắp hoặc lọc khác, phải đọc quy tắc truy vấn của Cassandra; không mặc định có thể `ORDER BY` tùy ý trên mọi cột, trên nhiều partition hoặc dùng bất kỳ điều kiện filter nào mà không tốn chi phí lớn.

Một bảng thiết kế cho Q2 có thể không tối ưu Q1. Cassandra thường được mô hình hóa theo các truy vấn cần hỗ trợ; việc tạo thêm bảng/đường truy cập có chi phí đồng bộ và cần giải quyết yêu cầu consistency.

### 8.3. MongoDB: `_id`, shard key và chỉ mục sắp xếp là khái niệm khác nhau

Trong MongoDB, một document có trường `_id` được dùng làm định danh duy nhất trong collection. Nhưng khi triển khai sharded cluster, **shard key** là cấu hình riêng dùng để phân phối và định tuyến dữ liệu. Shard key có thể khác `_id`; các bảo đảm về tính duy nhất trong sharded collection phải kiểm tra theo quy tắc index/shard key của phiên bản đang dùng.

Sắp xếp truy vấn thường thể hiện qua `sort` và được tối ưu bằng index thích hợp, ví dụ:

~~~javascript
db.orders.createIndex({ tenantId: 1, customerId: 1, createdAt: -1 });

db.orders
  .find({ tenantId: "T-7", customerId: "C-42" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

Trong ví dụ này:

- `tenantId` + `customerId` là các điều kiện truy vấn của ứng dụng.
- Index hỗ trợ đường lọc và thứ tự khi planner lựa chọn phù hợp.
- Nó **không tự chứng minh** rằng các trường này là shard key.
- `createdAt` ở index không phải một “sort key” có cùng API/ngữ nghĩa như sort key trong composite primary key DynamoDB.

Muốn đánh giá hiệu năng phải xem execution plan, dữ liệu và topology thực tế. Khi truy vấn không xác định được shard phù hợp, thao tác có thể phải liên hệ nhiều shard, tùy kiểu truy vấn và cơ chế định tuyến.

### 8.4. Redis: khóa trong keyspace và phân phối slot

Với Redis, ứng dụng thường truy cập trực tiếp bằng key như:

~~~redis
SET order:O-103 "{\"status\":\"PAID\"}"
GET order:O-103
~~~

Trong một Redis Cluster, cơ chế hash slot quyết định nơi key được định tuyến; **không có một trường sort key bắt buộc bên trong mỗi item như mô hình composite primary key DynamoDB**. Tiền tố `order:` chỉ là quy ước đặt tên ở tầng ứng dụng, không tự tạo thứ tự hay đường truy vấn theo thời gian.

Redis có kiểu dữ liệu và lệnh phục vụ mục tiêu khác, chẳng hạn **sorted set** dùng điểm số để duy trì thứ tự; muốn dùng nó làm danh sách đơn hàng theo thời gian phải thiết kế và duy trì cấu trúc đó. Những đặc điểm như hash tags, multi-key commands, TTL, persistence và cluster restrictions cần tra tài liệu Redis và cách triển khai đang dùng.

### 8.5. Bảng đối chiếu để tránh suy diễn

| Sản phẩm / mô hình | Khóa truy cập thường thấy | Thành phần phân phối/nhóm | Thành phần liên quan đến thứ tự | Giới hạn cần nhớ |
|---|---|---|---|---|
| DynamoDB | Khóa item, `Query` theo key hoặc index | Partition key của table/index | Sort key nếu cấu trúc có | Sort key tùy chọn; truy vấn theo PK và điều kiện SK |
| Cassandra | Primary key hoặc mẫu `WHERE` theo thiết kế bảng | Partition key một/nhiều cột | Clustering columns | Sắp thứ tự trong partition, hạn chế query tùy ý |
| MongoDB | `_id` và các điều kiện có index | Shard key khi sharding | Sort + index tương ứng | `_id`, shard key và index không đồng nghĩa |
| Redis | Tên key trong keyspace | Cluster slot từ key theo cơ chế Redis Cluster | Cấu trúc do ứng dụng chọn, ví dụ sorted set | Không có sort key bắt buộc cho mọi key |

Không có phép ánh xạ “sort key DynamoDB = cột indexed MongoDB = clustering key Cassandra = Redis key suffix” đúng cho mọi tình huống. Chúng cùng giúp **lý luận về truy cập và thứ tự**, nhưng có contract khác nhau.

## 9. Những lỗi thiết kế khóa thường gặp

### 9.1. Dùng khóa truy cập thuận tiện làm partition key mà không đo phân bố

Một nhóm chọn `status` làm partition key vì API thường lọc theo trạng thái. Nhưng `status` chỉ có vài giá trị; trạng thái `PENDING` nhận phần lớn lần ghi, trở thành điểm nóng. Phải xem phân bố request thực tế, số item trong mỗi nhóm và khả năng xử lý của sản phẩm.

Một lựa chọn khác như `tenantId#day#bucket` có thể phân phối tải tốt hơn nhưng đổi lại query “mọi đơn PENDING” phải gom nhiều bucket. Khóa tốt phải phục vụ **cả truy cập lẫn phân phối tải**, không chỉ một trong hai.

### 9.2. Dùng timestamp làm khóa sắp xếp mà quên tính duy nhất

Hai đơn có thể tạo ra cùng mili-giây. Nếu `(PK, SK)` phải duy nhất mà `SK = createdAt`, lần ghi sau có thể xung đột hoặc thay thế bản ghi trước theo ngữ nghĩa sản phẩm. Cân nhắc thêm ID phân biệt hoặc một cơ chế tạo số thứ tự duy nhất phù hợp.

### 9.3. Giả định chuỗi có dấu hai chấm tạo thứ tự truy vấn

Tên khóa:

~~~text
order:C-42:2026-11-14T09:00:00Z
order:C-42:2026-11-14T10:15:00Z
~~~

trông có vẻ được sắp xếp, nhưng không chứng minh rằng database có thể query theo prefix, range và trả kết quả có thứ tự. Cần phân biệt **quy ước đặt tên** với **cơ chế index/sort thật**.

### 9.4. Đặt thứ tự trong partition nhưng lại cần danh sách toàn cục

Nếu khóa chia theo khách hàng, lấy đơn mới nhất của **một khách hàng** có thể thuận tiện. Nhưng lấy “100 đơn mới nhất toàn hệ thống” thường cần thêm một access pattern, index/bảng tổng hợp hoặc hệ phân tích. Sort key trong từng nhóm không tạo một thứ tự toàn cục miễn phí.

### 9.5. Lấy nhiều item rồi filter và tưởng đã tối ưu

Ví dụ chỉ có PK là `customerId` và sort key là thời gian. Ứng dụng muốn 20 đơn `PAID` mới nhất, nhưng lọc sau khi đọc. Nếu khách hàng có rất ít đơn `PAID`, nó có thể phải đọc nhiều item hơn dự kiến mới đủ 20 kết quả. Với sản phẩm có filter server-side, cần biết filter được thực thi trước hay sau bước đọc/index và chi phí được tính như thế nào.

### 9.6. Dùng khóa ghép nhưng query thiếu thành phần bắt buộc

Nếu mô hình nhóm bằng `(tenantId, customerId)` mà API chỉ có `customerId`, không thể mặc định truy vấn trực tiếp được nhóm đó. Giải pháp có thể là yêu cầu API truyền tenant từ ngữ cảnh xác thực, dùng một đường tra cứu khác hoặc thiết kế lại partition key. Không tự bỏ tenant ra khỏi khóa nếu điều đó ảnh hưởng tách dữ liệu giữa khách hàng tổ chức.

### 9.7. Nhầm khóa phân vùng với cơ chế bảo đảm tính duy nhất

Partition key dùng để nhóm và định tuyến, nhưng **không phải mọi mô hình đều yêu cầu partition key một mình phải duy nhất**. Trong mô hình có sort key, nhiều item chia sẻ PK và khác SK; toàn bộ cặp khóa mới xác định item duy nhất. Ở một số index phụ, tính duy nhất lại có quy tắc khác.

### 9.8. Quên rằng đổi khóa là một cuộc di chuyển dữ liệu

Thay `customerId` bằng `customerId#month` có thể cần ghi lại dữ liệu, tạo index mới, điều chỉnh API và xử lý đọc theo cả lược đồ cũ/mới trong giai đoạn chuyển đổi. Vì cấu trúc khóa nằm trên đường truy cập cơ bản, đổi key thường phức tạp hơn đổi một trường value. Cần có kế hoạch dữ liệu lịch sử, backfill, dual-read/dual-write nếu cần, kiểm tra hoàn tất và cách loại bỏ đường cũ.

## 10. Chọn partition key cần cân nhắc tải và phạm vi truy vấn

Một khóa phân vùng có thể đáp ứng tốt chức năng nhưng vận hành kém nếu lưu lượng tăng. Hãy so sánh các lựa chọn sau cho đơn hàng:

| Lựa chọn partition key | Truy vấn thuận lợi | Rủi ro/đánh đổi |
|---|---|---|
| `orderId` | Đọc đơn theo ID | Lịch sử theo khách hàng cần đường tra cứu khác |
| `customerId` | Lịch sử của một khách hàng | Khách rất lớn hoặc hoạt động nhiều có thể tạo nhóm nóng |
| `tenantId#customerId` | Phân tách tenant, lịch sử khách hàng | API phải xác định tenant; khách rất lớn vẫn có thể nóng |
| `tenantId#customerId#yyyyMM` | Thu hẹp độ lớn nhóm theo tháng | Lịch sử nhiều tháng cần ghép kết quả/phân trang qua nhóm |
| `status` | Nhóm theo trạng thái | Ít giá trị, dễ lệch tải và nhóm quá lớn |
| `tenantId#bucketId` | Có thể chia tải theo bucket | Truy vấn theo khách hàng hoặc trạng thái có thể cần fan-out |

Những đánh giá này chỉ là **giả thuyết thiết kế ban đầu**. Kết quả phụ thuộc loại database, cơ chế index, mô hình consistency, phân bố tenant, thời gian lưu dữ liệu, thông lượng và chi phí thực tế.

### 10.1. Bucketing chỉ giải được một phần bài toán

Chia dữ liệu của một khách theo tháng:

~~~text
PK = CUSTOMER#C-42#MONTH#2026-11
PK = CUSTOMER#C-42#MONTH#2026-10
~~~

giúp tránh một nhóm tăng mãi theo thời gian, nhưng truy vấn cần “toàn bộ lịch sử” phải đọc nhiều bucket rồi hợp nhất. Nếu cùng khách phát sinh lượng ghi rất cao trong một tháng, bucket tháng vẫn có thể nóng. Chia thêm theo ngày hoặc nhánh ngẫu nhiên làm truy vấn fan-out phức tạp hơn.

Vì vậy nên dùng **số liệu và truy vấn thực tế** để quyết định độ rộng bucket, cách xác định cursor và cách kết hợp thứ tự; đừng chọn một công thức bucketing chỉ vì mẫu code trên mạng.

### 10.2. Sort key không cứu được partition key không phù hợp

Nếu một nhóm PK chứa tất cả đơn `PENDING` trên toàn hệ thống, sort key theo `createdAt` giúp có thứ tự trong nhóm nhưng không loại bỏ vấn đề ghi tập trung. Ngược lại, chọn partition key quá phân tán có thể khiến truy vấn thời gian phải đọc rất nhiều nhóm. Hai thành phần giải quyết mục tiêu khác nhau và cần được đánh giá cùng nhau.

## 11. Tính đúng đắn: một khóa nhanh chưa chắc đủ

Khóa tối ưu đường đọc không tự bảo đảm các bất biến nghiệp vụ.

### 11.1. Ghi đồng thời

Hai request cùng cập nhật `order.status` có thể đua nhau. Việc cùng dùng một partition key chưa chứng minh quá trình “đọc trạng thái → kiểm tra → ghi trạng thái mới” là nguyên tử. Cần xem conditional write, transaction, version/compare-and-set và isolation theo sản phẩm.

Ví dụ yêu cầu nghiệp vụ:

~~~text
Chỉ chuyển PENDING -> PAID nếu đơn hiện vẫn PENDING.
Nếu request bị gửi lại, không được thu tiền lần thứ hai.
~~~

Ở đây cần bảo đảm cập nhật có điều kiện và idempotency. Không thể giải chỉ bằng cách chọn SK là timestamp.

### 11.2. Đồng bộ nhiều lối truy cập

Nếu Q1 đọc theo `orderId` còn Q2 theo `customerId`, cùng một đơn có thể xuất hiện ở nhiều cấu trúc. Khi đổi trạng thái, phải xác định lối nào là nguồn sự thật, index nào được quản lý tự động, các bản sao được cập nhật đồng bộ hay bất đồng bộ và lỗi giữa chừng được khôi phục thế nào.

Có hệ cung cấp GSI với consistency khác bảng gốc; có hệ khuyến khích bảng được tổ chức theo query; có hệ cho phép secondary index với giới hạn riêng. Không được giả định mọi cấu trúc đọc đều phản ánh write ngay lập tức.

### 11.3. Xóa và thay đổi định danh

Khi đổi `customerId` của một đơn hoặc xóa tài khoản, những bản ghi/ánh xạ theo khóa cũ có thể phải được di chuyển hoặc xóa. Với hệ có key bất biến theo mô hình thiết kế, đổi “khóa” thường tương đương thao tác tạo bản ghi mới và xử lý bản cũ. Cần bảo đảm không làm mất dữ liệu, không để kết quả tra cứu trỏ tới bản ghi không còn hợp lệ.

## 12. Quy trình chọn khóa cho một access pattern

Có thể đi theo chuỗi quyết định sau:

~~~mermaid
flowchart TD
    A["Mô tả truy vấn và thao tác ghi"] --> B["Liệt kê trường đã biết ở đầu vào"]
    B --> C["Xác định item / nhóm cần trả về"]
    C --> D{"Đọc một item hay danh sách?"}
    D -->|Một item| E["Xét khóa truy cập duy nhất"]
    D -->|Danh sách| F["Xét partition key và điều kiện thứ tự/range"]
    E --> G["Kiểm tra phân bố khóa và truy vấn khác"]
    F --> G
    G --> H["Đối chiếu khả năng sản phẩm"]
    H --> I["Đánh giá hot key, consistency, uniqueness"]
    I --> J["Thiết kế thêm index / cấu trúc nếu cần"]
    J --> K["Đo trên tải và dữ liệu đại diện"]
~~~

Diễn giải từng bước:

1. **Ghi câu hỏi nghiệp vụ bằng ngôn ngữ độc lập sản phẩm.** Ví dụ “mỗi khách hàng xem 20 đơn gần nhất, có thể phân trang”; đồng thời ghi dữ liệu được biết khi gọi API.
2. **Ghi dạng kết quả.** Một item hay nhiều item? Có yêu cầu lọc, thứ tự, khoảng thời gian, số lượng và phân trang không?
3. **Chọn nhóm dữ liệu có ý nghĩa truy vấn.** Với lịch sử đơn, một khách hàng có thể là nhóm tự nhiên; với chi tiết đơn, ID đơn có thể là định danh tự nhiên.
4. **Chọn trường sắp xếp nếu mô hình hỗ trợ.** Đặt time/order/rank theo loại dữ liệu, đảm bảo phân biệt bản ghi và định dạng chính xác.
5. **Đánh giá phân phối.** Kiểm tra cardinality, độ lệch lưu lượng, quy mô nhóm, hot key và tốc độ tăng dữ liệu.
6. **Xác minh sản phẩm.** Partition key có bắt buộc equality không? Sort key có range/prefix không? Có scan bắt buộc không? Phạm vi index và consistency là gì?
7. **Xác định access pattern còn thiếu.** Nếu một cấu trúc không hỗ trợ mọi truy vấn, thiết kế index, bảng phụ hoặc kiến trúc đọc riêng và cách duy trì nó.
8. **Kiểm chứng điều kiện thực tế.** Dùng dữ liệu đại diện để xem số item đọc, độ trễ p95/p99, tốc độ ghi, chi phí, retry, failover và những bất biến quan trọng.

### 12.1. Mẫu ghi quyết định thiết kế

~~~yaml
useCase: "Liệt kê 20 đơn gần nhất của khách hàng"
knownAtRequest:
  - tenantId
  - customerId
result:
  sort: "createdAt DESC"
  pageSize: 20
candidateDesign:
  accessKey: "(tenantId, customerId)"
  partitionKey: "TENANT#<tenantId>#CUSTOMER#<customerId>"
  sortKey: "ORDER#<createdAt-UTC>#<orderId>"
assumptionsToVerify:
  - "Query hỗ trợ điều kiện theo partition key"
  - "Có thứ tự phù hợp theo sort key trong partition"
  - "Hỗ trợ pagination và giới hạn kích thước/độ dài khóa"
  - "Độ lệch tải giữa các customer không gây hotspot không chấp nhận được"
  - "Lối truy cập theo orderId có cách giải quyết riêng"
productContext:
  name: "<tên sản phẩm>"
  version: "<phiên bản/loại dịch vụ>"
  topology: "<cluster/region/config>"
evidence:
  docs: "<tài liệu đúng phiên bản>"
  observedMetrics: "<kết quả thử nghiệm trên workload đại diện>"
~~~

Mẫu giúp phân biệt **lựa chọn thiết kế** với **bảo đảm sản phẩm đã được xác minh**. Phần `assumptionsToVerify` không được coi là đặc tính chắc chắn chỉ vì đã ghi vào YAML.

## 13. Bài tập vận dụng

### Bài tập A — Nhận diện ba vai trò

Một bảng giả định có:

~~~text
PK = TENANT#T-7#CUSTOMER#C-42
SK = ORDER#2026-11-14T11:30:00Z#O-103
orderId = O-103
~~~

Trả lời:

1. API có `tenantId` và `customerId`, muốn lịch sử đơn: đâu là thông tin truy cập?
2. Trường nào quyết định nhóm dữ liệu?
3. Thành phần nào phục vụ thứ tự trong nhóm?
4. API chỉ có `orderId` thì có đủ khóa để truy cập trực tiếp cấu trúc trên không?

**Gợi ý đáp án:** (1) cặp tenant và customer; (2) PK đã mã hóa tenant/customer; (3) SK chứa thời gian và mã đơn; (4) chưa đủ, vì không biết PK. Có thể cần một bảng/ánh xạ/index khác.

### Bài tập B — Tìm lỗi về thứ tự

Một nhóm tạo sort key kiểu chuỗi:

~~~text
ORDER#9
ORDER#10
ORDER#11
~~~

Nhóm mong nhận `9, 10, 11` theo số tăng dần. Hãy giải thích vì sao thứ tự từ điển có thể khác và đề xuất cách giải.

**Gợi ý đáp án:** nếu so sánh ký tự, `ORDER#10` có thể đứng trước `ORDER#9`. Dùng kiểu số nếu sản phẩm hỗ trợ hoặc mã hóa với độ rộng cố định, ví dụ `ORDER#000009`, `ORDER#000010`, `ORDER#000011`. Kiểm tra giới hạn số và quy tắc sort thực tế.

### Bài tập C — Chọn giữa hai partition key

Yêu cầu: liệt kê đơn theo từng khách hàng trong tenant. Chọn một trong hai:

~~~text
A: PK = status
B: PK = tenantId#customerId
~~~

**Gợi ý:** B gắn với access pattern lịch sử khách hàng hơn. A có thể gom quá nhiều dữ liệu vào vài trạng thái. Dù vậy B vẫn cần kiểm tra khách hàng lớn, phân bố tải, sort key và những truy vấn khác. Không thể kết luận hiệu năng chỉ từ tên khóa.

### Bài tập D — Vì sao một sort key chưa đủ?

Đã có bảng theo `(customerId, createdAt#orderId)`. Sản phẩm muốn dashboard “100 đơn mới nhất toàn bộ hệ thống”. Có thể chỉ dùng sort key hiện tại để bảo đảm truy vấn toàn cục nhanh không?

**Gợi ý:** Không mặc định. Sort thường chỉ có phạm vi theo partition. Cần một lối truy cập khác: index phù hợp, dòng dữ liệu phục vụ dashboard, công cụ phân tích hoặc một mô hình read projection. Phải xét cách cập nhật và độ trễ dữ liệu.

### Bài tập E — Đối chiếu thuật ngữ

Phân loại các câu sau:

1. “`_id` của document MongoDB luôn là shard key.”
2. “Composite primary key DynamoDB có partition key và sort key.”
3. “Cassandra có thể dùng nhiều cột làm composite partition key.”
4. “Tên Redis key chứa timestamp nên có sẵn thứ tự query theo timestamp.”
5. “Access key là khái niệm dùng khi phân tích cách ứng dụng truy cập dữ liệu.”

**Gợi ý đáp án:** (1) sai; (2) đúng cho cấu trúc composite (sort key không bắt buộc ở simple primary key); (3) đúng theo cú pháp partition key ghép; (4) sai; (5) đúng về vai trò trong phương pháp thiết kế.

## 14. Tổng hợp tư duy để mang sang các mô hình NoSQL

Khi nói “khóa” trong một thiết kế, hãy làm rõ nó đang trả lời câu nào:

- **Khóa truy cập:** “Để tìm dữ liệu này, client đang có những định danh và điều kiện gì?”
- **Khóa phân vùng:** “Đơn vị nhóm/định tuyến nào sẽ nhận thao tác này; khối lượng dữ liệu và tải có phân bố phù hợp không?”
- **Khóa sắp xếp:** “Trong nhóm đã chọn, làm sao phân biệt item, lấy theo khoảng và trả thứ tự mong muốn?”

Hãy nhớ rằng một trường có thể đảm nhiệm nhiều vai trò và một hệ thống có thể không có sort key theo nghĩa của DynamoDB/Cassandra. Mọi kết luận về cú pháp query, thứ tự, cơ chế hash, ranh giới uniqueness, phạm vi atomicity hoặc bảo đảm nhất quán đều cần kiểm tra trên **sản phẩm, phiên bản và cấu hình thực tế**.

Quy trình đúng bắt đầu từ **access pattern và bất biến nghiệp vụ**, sau đó mới đến lựa chọn partition key, sort/clustering key, index và cách phân phối tải. Khi các truy vấn không thể cùng phục vụ tốt bởi một cấu trúc, hãy chủ động thiết kế thêm đường truy cập và quản lý chi phí đồng bộ thay vì kỳ vọng một khóa có thể giải quyết mọi bài toán.

