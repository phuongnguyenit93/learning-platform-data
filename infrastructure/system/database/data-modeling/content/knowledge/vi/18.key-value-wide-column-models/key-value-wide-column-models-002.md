# Thiết kế không gian khóa, khóa ghép và quy ước định danh

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **định danh nghiệp vụ**, **khóa tra cứu**, **khóa ghép**, **khóa phân vùng** và **khóa sắp xếp** trong thiết kế dữ liệu.
- Chuyển các mẫu truy cập thành một **không gian khóa (keyspace)** nhất quán, có phạm vi duy nhất rõ ràng và có thể mở rộng.
- Định nghĩa quy tắc mã hóa khóa ghép tránh nhập nhằng, chuẩn hóa đầu vào và không để dữ liệu nhạy cảm lộ qua tên khóa.
- Chọn khóa phân vùng và khóa sắp xếp phù hợp khi mô hình hóa dữ liệu kiểu **key–value** hoặc **wide-column**.
- Nhận diện khóa nóng, phân vùng quá lớn, lạm dụng tiền tố, sai phạm vi tenant, nguy cơ đổi tên và vấn đề di trú phiên bản khóa.
- Lập bảng ràng buộc và cách kiểm chứng một thiết kế khóa trước khi đưa vào vận hành.

Trong module **DATABASE_DATA_MODELING**, việc đi từ yêu cầu nghiệp vụ đến mô hình dữ liệu rõ ràng bao gồm chọn thực thể, quan hệ, khóa, chỉ mục và lược đồ vật lý. Với các hệ lưu trữ khóa–giá trị và cột rộng, **khóa không chỉ để định danh bản ghi**: cách đặt khóa có thể quyết định đường truy cập, cách phân phối tải, thứ tự quét, khả năng giữ nhất quán và mức độ dễ thay đổi lược đồ.

---

## 1. Hiểu đúng các loại khóa

Một thực thể nghiệp vụ có thể mang nhiều định danh và xuất hiện trong nhiều cấu trúc khóa. Ví dụ, đơn hàng có `orderId` ổn định, thuộc một `shopId`, do một `customerId` tạo ra và có `createdAt`.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Business identifier (định danh nghiệp vụ)** | Xác định một đối tượng theo phạm vi nghiệp vụ; có thể độc lập với cách lưu trữ | `orderId = ord_908` |
| **Storage key (khóa lưu trữ)** | Đầu vào dùng để tìm một giá trị/hàng ở kho cụ thể | `order:v1:shop_17:ord_908` |
| **Namespace (không gian tên)** | Quy ước phân nhóm key theo miền, môi trường, phiên bản hoặc đối tượng | `cart:v1:...`, `order:v1:...` |
| **Composite key (khóa ghép)** | Khóa được tạo từ nhiều thành phần có ý nghĩa | `(shopId, orderId)` |
| **Partition key (khóa phân vùng)** | Thành phần xác định vùng/phân vùng lưu dữ liệu theo cơ chế của hệ quản trị | `(shopId, customerId)` |
| **Clustering/sort key (khóa sắp xếp)** | Thành phần dùng để tổ chức hoặc truy vấn có thứ tự **trong phạm vi phân vùng**, nếu sản phẩm hỗ trợ | `(createdAt, orderId)` |
| **Lookup/index key (khóa tra cứu phụ)** | Ánh xạ từ một tiêu chí khác sang định danh chính | `email-index:v1:<digest> → userId` |

Cần tách ba câu hỏi:

1. **Đây là đối tượng nào?** Trả lời bằng định danh nghiệp vụ hoặc khóa chính logic.
2. **Ứng dụng sẽ tìm nó bằng cách nào?** Trả lời bằng khóa tra cứu hoặc chỉ mục.
3. **Hệ lưu trữ sẽ đặt và sắp xếp nó ở đâu?** Trả lời bằng khóa phân vùng, khóa sắp xếp và đặc tính sản phẩm.

Một **khóa ghép logic** không nhất thiết phải nối thành một chuỗi. Kho key–value nhận khóa byte/chuỗi có thể cần mã hóa nhiều thành phần vào một key. Trong mô hình cột rộng, nhiều hệ quản trị cho khai báo các cột riêng cho partition key và clustering key. Không nên nhầm cả hai trường hợp với một “chuỗi có dấu hai chấm”.

> **Lưu ý thuật ngữ:** “Keyspace” đôi khi là tên một đối tượng quản trị cụ thể của sản phẩm, chẳng hạn một phạm vi chứa bảng. Trong bài này, **không gian khóa** chủ yếu nói về *quy hoạch và quy ước định danh các khóa mà ứng dụng sử dụng*; khi gặp sản phẩm cụ thể, hãy kiểm tra nghĩa kỹ thuật của thuật ngữ.

## 2. Bắt đầu từ nghiệp vụ và đường truy cập

Giả sử một nền tảng bán hàng có nhiều shop. Hệ thống cần:

- Mở giỏ hàng hiện tại bằng `shopId` và `userId`.
- Tìm đơn hàng khi biết `shopId` và `orderId`.
- Hiển thị 20 đơn hàng mới nhất của một khách tại một shop.
- Lọc lịch sử đơn hàng của khách theo khoảng ngày.
- Tra cứu tài khoản theo email khi đăng nhập.
- Thống kê doanh thu của tất cả shop theo tháng.

Không thể chọn một khóa duy nhất mà tất cả yêu cầu đều được tối ưu. Hãy lập **ma trận truy cập** trước khi viết cú pháp key.

| Yêu cầu | Giá trị đầu vào đã biết | Đầu ra / tính chất truy vấn | Hàm ý thiết kế |
| --- | --- | --- | --- |
| Giỏ hiện tại | `shopId, userId` | Một giỏ | Một khóa tra cứu theo cặp ID |
| Chi tiết đơn hàng | `shopId, orderId` | Một đơn hàng | Một định danh đủ duy nhất trong shop |
| Danh sách đơn gần đây | `shopId, userId` | Nhiều đơn có thứ tự và giới hạn | Cần thứ tự trong nhóm khách |
| Lịch sử theo ngày | `shopId, userId, [from,to)` | Quét khoảng thời gian | Clustering/sort key và có thể bucket |
| Đăng nhập | Email do người dùng nhập | Tìm user ID tương ứng | Chỉ mục duy nhất theo email chuẩn hóa |
| Báo cáo doanh thu | Tháng, nhóm shop | Tổng hợp trên nhiều khách và đơn | Mô hình phân tích hoặc bảng tổng hợp riêng |

Từ ma trận này, ta có thể thiết kế:

```text
cart:v1:<shopId>:<userId>      -> cartDocument
order:v1:<shopId>:<orderId>    -> orderDocument

Đường truy cập lịch sử đơn hàng:
partition = (shopId, userId, monthBucket)
sort      = (createdAt DESC, orderId ASC)

Đường tra cứu email:
email-lookup:v1:<emailDigest>  -> userId
```

Đây là **thiết kế khái niệm**. Một cơ sở dữ liệu key–value chỉ hỗ trợ `GET` theo khóa không tự cung cấp phép quét theo `sort`; muốn đọc danh sách đơn gần đây phải dùng cấu trúc/ chỉ mục riêng hoặc hệ lưu trữ hỗ trợ sắp xếp theo khóa. Mô hình wide-column được xây để có thể đọc theo partition key và phạm vi clustering key, nhưng chính xác truy vấn nào hợp lệ phải tuân theo hệ quản trị.

## 3. Thiết kế không gian tên của khóa

Không gian tên là một **hợp đồng giữa các thành phần ghi và đọc**, dùng để tránh trùng lặp ngẫu nhiên, phân biệt miền nghiệp vụ và hỗ trợ quan sát, di trú.

Một quy ước dễ đọc cho hệ thống key–value có thể là:

```text
<entityType>:<keyFormatVersion>:<tenantId>:<logicalId>

cart:v1:shop_17:user_42
order:v1:shop_17:ord_908
profile:v1:shop_17:user_42
```

Để biến ví dụ thành hợp đồng có thể triển khai, phải quy định tường minh:

| Thành phần | Quy tắc cần xác định |
| --- | --- |
| `entityType` | Tập giá trị cho phép, ví dụ `cart`, `order`, `profile`; không trộn tên đồng nghĩa như `orders` và `order` |
| `keyFormatVersion` | Phiên bản **định dạng khóa** khi thay đổi cách mã hóa/cấu trúc; không phải mọi phiên bản nội dung đều bắt buộc tạo namespace mới |
| `tenantId` | Phạm vi chủ sở hữu; một ID nội bộ ổn định, nhất quán giữa các dịch vụ |
| `logicalId` | ID đủ duy nhất trong phạm vi đã nêu; phải định nghĩa rõ có được thay đổi hay không |
| Bộ mã hóa | UTF-8 hay bytes; cách chuẩn hóa, escape, phân biệt chữ hoa/thường và xử lý giá trị rỗng |
| Độ dài tối đa | Theo giới hạn khóa và chi phí của sản phẩm được chọn |
| Quy tắc đặt tên | Viết thường các tiền tố cố định, quy tắc dấu phân cách, không chèn PII trực tiếp |
| Quy tắc vòng đời | TTL, xóa, giữ lại, quyền sở hữu và chính sách di trú |

Không nên coi dấu `:` là một chuẩn chung: nó chỉ là quy ước biểu diễn. Kho dữ liệu có thể chấp nhận khóa nhị phân, khóa dạng tuple hoặc khai báo nhiều trường riêng.

### 3.1. Phạm vi của tính duy nhất

Hỏi “`userId` có duy nhất không?” vẫn chưa đủ. Cần nói rõ **duy nhất trong phạm vi nào**.

- Nếu `orderId` là duy nhất toàn hệ thống, `orderId` có thể đủ để tra cứu một đơn hàng; thêm `shopId` vào khóa vẫn có thể hữu ích cho phân tách dữ liệu và kiểm tra phạm vi.
- Nếu `orderId` chỉ duy nhất **trong một shop**, thì `(shopId, orderId)` mới là định danh đầy đủ.
- Nếu `cartId` duy nhất nhưng mỗi người dùng chỉ có một giỏ hiện tại trong một shop, có thể cần cả `cartId → cart` và `(shopId, userId) → cartId`. Cặp ánh xạ này tạo thêm yêu cầu nhất quán.

Bảng mô tả định danh nên ghi rõ chủ thể cấp phát, phạm vi duy nhất, khả năng đổi, khả năng tái sử dụng sau xóa và cách xử lý xung đột. Các thông tin đó hữu ích cả khi sau này chuyển sang SQL, document hoặc graph.

### 3.2. Phân biệt môi trường và ứng dụng

Ở một số hệ thống có thể gặp khóa như `prod:checkout:cart:v1:...`. Tiền tố môi trường giúp đọc log nhưng **không thay thế biện pháp cô lập môi trường** bằng database, tài khoản truy cập, cluster hoặc policy phù hợp. Không nên trông chờ vào việc các nhóm tự tránh viết sai tiền tố để bảo vệ dữ liệu production.

Namespace phục vụ cấu trúc, **không phải cơ chế phân quyền**. Người dùng tenant A không được phép đọc tenant B chỉ vì mã nguồn UI chỉ sinh khóa `shop_A`. Dịch vụ phải kiểm tra quyền theo danh tính và phạm vi truy cập tại biên API, truy vấn và cơ chế IAM/ACL khi có.

## 4. Chọn định danh nghiệp vụ: tự nhiên hay thay thế?

Một quyết định cốt lõi là thành phần `logicalId` được lấy từ đâu.

| Loại định danh | Ví dụ | Lợi ích | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Khóa tự nhiên** | Mã số thuế, SKU nội bộ theo shop | Có nghĩa với nghiệp vụ; dễ tra cứu theo mã đã biết | Có thể đổi, nhập sai, va chạm hoặc phụ thuộc phạm vi |
| **Khóa thay thế** | `user_42`, UUID | Tách định danh khỏi thuộc tính thay đổi | Cần cơ chế cấp phát và đường tra cứu từ thuộc tính nghiệp vụ |
| **Định danh có xu hướng tăng theo thời gian** | ID tạo theo thời gian, UUIDv7, ULID | Hữu ích trong một số đường sắp xếp, log và phân tích | Thứ tự thực tế phụ thuộc thuật toán, thời gian hệ thống, độ chính xác và bộ mã |
| **Định danh được chọn ngẫu nhiên** | UUIDv4 | Xác suất va chạm cực thấp với bộ sinh đúng; phân tán tốt trong nhiều thiết kế | Khó đọc; nếu làm khóa sắp xếp thì không giữ thứ tự thời gian |

Một thiết kế thường bền hơn khi dùng **ID nội bộ bất biến** để định danh và giữ các mã có thể thay đổi làm thuộc tính hoặc ánh xạ tra cứu phụ. Ví dụ, user đổi email vẫn giữ `userId` và giỏ của người đó không cần đổi khóa. Đây là nguyên tắc, không phải tuyệt đối: nếu nghiệp vụ quy định SKU ổn định trong phạm vi shop, `(shopId, sku)` vẫn có thể là khóa chính hợp lý.

**Không đồng nhất “có thứ tự theo thời gian” với “thứ tự tạo toàn cục chính xác”.** UUIDv7 và ULID có thành phần thời gian và có thể thuận tiện để sắp theo thứ tự gần đúng, nhưng tính đơn điệu giữa nhiều máy hoặc khi đồng hồ lệch còn phụ thuộc cách sinh. Truy vấn phân trang và ràng buộc nghiệp vụ vẫn cần khóa phân định cuối cùng như `orderId` khi thời điểm trùng nhau.

### 4.1. Không dùng thuộc tính có thể đổi làm khóa chính nếu không có kế hoạch đổi khóa

Giả sử khóa là:

```text
account:customer@example.com -> profile
```

Khi đổi email, ứng dụng phải tạo key mới, chuyển dữ liệu, cập nhật các tham chiếu và xóa key cũ. Nếu một bước thất bại, có thể tồn tại hai hồ sơ hoặc không còn đường tìm đúng.

Thiết kế khác:

```text
account:v1:user_42            -> profile
email-lookup:v1:<digestEmail> -> user_42
```

Trong cách này, thay đổi email không đổi khóa chính. Tuy nhiên, khóa `email-lookup` vẫn cần **đảm bảo duy nhất** và cập nhật có kiểm soát: hai yêu cầu đăng ký đồng thời không được cùng chiếm một email. Chọn giao dịch/ghi có điều kiện hoặc một nguồn dữ liệu có ràng buộc unique để bảo vệ; hai lệnh `put` tuần tự không tự bảo đảm tính duy nhất.

## 5. Mã hóa khóa ghép không nhập nhằng

Khóa ghép logic có thể là tuple `(shopId, orderId)`. Nếu kho dữ liệu nhận một chuỗi, ứng dụng cần hàm mã hóa có thể ánh xạ **mỗi tuple hợp lệ tới đúng một key khác nhau**.

### 5.1. Lỗi nối chuỗi trực tiếp

Giả sử dùng dấu `:` làm dấu phân cách:

```text
encode("a:b", "c") = "a:b:c"
encode("a", "b:c") = "a:b:c"
```

Hai tuple khác nhau tạo cùng một chuỗi. Đây là **va chạm do mã hóa**, không phải va chạm hash. Nối không có phân cách còn tệ hơn:

```text
encode("ab", "c") = "abc"
encode("a", "bc") = "abc"
```

Có ba hướng khắc phục phổ biến:

1. **Tập ký tự giới hạn + từ chối ký tự phân cách:** Ví dụ ID sinh tự động chỉ gồm `[a-z0-9_-]` và dấu `:` không xuất hiện trong thành phần. Chỉ hợp lệ nếu được kiểm tra ở mọi nơi tạo ID.
2. **Escape hoặc percent-encoding từng thành phần:** Dùng một bộ mã và quy tắc escape thống nhất, sau đó nối các thành phần đã mã hóa. Cần quy định rõ escape ký tự `%` và không giải mã trước khi tách thành phần.
3. **Length-prefix hoặc dạng nhị phân có kiểu:** Ghi độ dài byte trước mỗi thành phần để có thể giải mã không nhập nhằng; phù hợp khi khóa không bắt buộc dễ đọc.

Ví dụ về mã hóa có tiền tố độ dài trong một hệ nội bộ:

```text
logical tuple: ("a:b", "c")
encoded:       3#a:b1#c

logical tuple: ("a", "b:c")
encoded:       1#a3#b:c
```

Trong ví dụ ASCII trên, số trước `#` là **độ dài byte UTF-8**, không nhất thiết là số ký tự Unicode. Nếu chuyển sang ký tự tiếng Việt, phải tính trên byte như giao thức đã chọn. Đừng trộn phần mềm tính độ dài theo byte với phần mềm tính độ dài theo ký tự.

### 5.2. Quy tắc chuẩn hóa phải nhất quán

Tùy trường, trước khi mã hóa khóa cần quyết định:

- Có chấp nhận khoảng trắng đầu/cuối không? Nếu trim, phải trim ở cùng một biên nhập liệu và tránh làm thay đổi ID vốn cho phép khoảng trắng.
- Chữ hoa và chữ thường có phân biệt không? `SKU-a` có thể là mã khác `sku-a`; không tự viết thường mọi ID.
- Chuỗi Unicode có cần đưa về một dạng chuẩn, ví dụ NFC, không? Hai biểu diễn nhìn giống nhau có thể có byte khác nhau.
- Thời gian dùng timezone, độ chính xác và định dạng nào? Không được trộn giờ địa phương với UTC trong một trường dùng để sắp xếp.
- Giá trị null, rỗng và thiếu có phải ba trạng thái khác nhau không? Không mã hóa tùy tiện cả ba thành chuỗi rỗng.

**Email đặc biệt nhạy cảm với chuẩn hóa:** tên miền không phân biệt hoa/thường, nhưng quy tắc xử lý phần local-part phụ thuộc hệ thống và nhà cung cấp. Không tự xóa dấu chấm hoặc nội dung sau dấu `+` cho mọi địa chỉ. Hãy định nghĩa quy tắc dựa trên hợp đồng đăng nhập thực tế, sau đó áp dụng nhất quán khi tạo, tra cứu và đổi email.

### 5.3. Hợp đồng mã hóa mẫu

Có thể mô tả một hàm dựng khóa bằng giả mã độc lập sản phẩm:

```text
function cartKey(shopId, userId):
    validateOpaqueId(shopId)
    validateOpaqueId(userId)
    return join(":", ["cart", "v1", shopId, userId])

function validateOpaqueId(id):
    require id is not empty
    require matches(id, "[A-Za-z0-9_-]+")
    require byteLength(UTF8(id)) <= configuredLimit
```

Giả mã chỉ hợp lệ vì hàm kiểm tra **cấm dấu `:`** trong thành phần. Nếu tenant ID, URL, email hoặc mã bên ngoài có thể chứa dấu đó, phải dùng bộ mã khác. Đồng thời cần ghi rõ khóa phân biệt chữ hoa/thường ở cấp byte; hai ID khác nhau có thể được coi là khác dù hiển thị tương tự.

## 6. Phân biệt khóa ghép key–value với khóa trong mô hình cột rộng

Hai kho dữ liệu có thể dùng chung thực thể và mẫu truy cập nhưng tổ chức khóa rất khác.

### 6.1. Với kho key–value thuần

Ví dụ:

```text
order:v1:shop_17:ord_908 -> { ...đơn hàng... }
```

Ứng dụng cung cấp toàn bộ key để đọc giá trị. Việc key có `shop_17` **không mặc nhiên** cho phép “lấy mọi đơn hàng của shop_17” với chi phí thấp. Nếu kho phân vùng theo hash của toàn bộ key, các khóa có cùng tiền tố có thể nằm rải ở nhiều phân vùng. Quét tiền tố chỉ hiệu quả khi hệ quản trị, chỉ mục và cấu trúc lưu trữ thực sự hỗ trợ.

Để hỗ trợ danh sách đơn theo user, có thể cần một **read model** riêng như danh sách ID đã sắp xếp, hoặc sử dụng cơ sở dữ liệu cung cấp khóa sắp xếp. Khi duy trì một danh sách ở key riêng, mỗi lần tạo đơn có thể liên quan ít nhất hai ghi: đơn hàng chính và danh sách. Phải xử lý điều kiện nhất quán và phục hồi khi một bước thất bại.

### 6.2. Với mô hình wide-column

Trong một họ hệ quản trị cột rộng, bảng có thể được tổ chức theo:

```text
partition key: (shopId, userId)
clustering:    (createdAt DESC, orderId ASC)
non-key data:  total, status, currency, ...
```

Sơ đồ ý tưởng:

```text
Partition (shop_17, user_42)
  ├─ (2026-11-22T10:40:00Z, ord_908) -> status, total, ...
  ├─ (2026-11-21T15:12:00Z, ord_901) -> status, total, ...
  └─ (2026-11-20T08:05:00Z, ord_880) -> status, total, ...

Partition (shop_17, user_99)
  ├─ (2026-11-22T09:00:00Z, ord_910) -> ...
  └─ ...
```

**Partition key** chọn nhóm dữ liệu cần đọc. **Clustering key** xác định định danh/sắp xếp hàng trong nhóm đó, nếu hệ quản trị cung cấp cơ chế clustering tương ứng. Một cấu hình lưu giảm dần theo `createdAt` có thể phục vụ “20 đơn mới nhất” bằng cách đọc phần đầu phân vùng; tuy vậy việc hỗ trợ thứ tự giảm, phân trang và giới hạn cụ thể tùy sản phẩm.

Không phải mọi sản phẩm được gọi là “wide-column” đều có ngữ nghĩa primary key giống Cassandra. Ví dụ, một số hệ dùng row key byte được sắp thứ tự từ điển trong tablet, số khác dùng partition key cộng sort key. Luôn **dịch nhu cầu truy vấn sang các primitive thực tế của sản phẩm** trước khi coi đây là lược đồ triển khai.

### 6.3. Khi nào chọn thành phần làm partition key?

Hỏi đồng thời:

- Truy vấn phổ biến có cung cấp đầy đủ các thành phần này không?
- Số lượng phân vùng có đủ lớn để phân phối tải không?
- Mỗi phân vùng có thể đạt kích thước cực đại bao nhiêu trong 1 tháng, 1 năm và thời gian lưu giữ?
- Có tenant hay đối tượng đặc biệt nóng hơn nhiều so với phần còn lại không?
- Truy vấn một lần cần đọc bao nhiêu phân vùng? Có thể giới hạn và phân trang không?

Ví dụ, chọn chỉ `shopId` làm partition key cho toàn bộ đơn của shop giúp lọc theo shop, nhưng một shop lớn có thể dồn hàng triệu đơn và nhiều ghi vào một phân vùng. Chọn `(shopId, userId)` phân tán tải theo khách nhưng truy vấn toàn bộ shop phải tổng hợp nhiều phân vùng. Đó là một đánh đổi trực tiếp giữa **đường truy vấn** và **phân phối dữ liệu**.

## 7. Thiết kế khóa sắp xếp và truy vấn theo thời gian

Đối với dữ liệu có thứ tự như đơn hàng, nhật ký thiết bị hoặc sự kiện, trường thời gian thường trở thành một thành phần của khóa ghép. Có ba việc khác nhau cần xử lý:

1. **Thứ tự:** dữ liệu trong cùng nhóm có được tổ chức để lấy mới nhất hoặc khoảng ngày hiệu quả không?
2. **Tính duy nhất:** hai sự kiện có thể có cùng timestamp; cần thêm ID hoặc sequence làm khóa phân định.
3. **Quy mô:** dữ liệu của một khách hoặc thiết bị tăng mãi sẽ làm phân vùng trở nên quá lớn.

### 7.1. Dùng thời gian có định dạng nhất quán

Nếu hệ lưu trữ sắp khóa kiểu chuỗi theo thứ tự byte/từ điển, thời gian được chuẩn hóa có thể giúp thứ tự chuỗi khớp thứ tự thời gian:

```text
2026-11-20T08:05:00.000Z
2026-11-21T15:12:00.000Z
2026-11-22T10:40:00.000Z
```

Điều này chỉ đáng tin khi **định dạng, timezone, độ chính xác và phần đệm số được cố định**. Những chuỗi như `2026-2-5` và `2026-11-1` không có thứ tự từ điển trùng thứ tự ngày. Các offset múi giờ khác nhau cũng có thể khiến thứ tự chuỗi không khớp thời điểm thực.

Định dạng thời gian chỉ mang lại lợi ích truy vấn range nếu **hệ lưu trữ hỗ trợ duyệt theo thứ tự**. Với kho hash key–value chỉ cung cấp `GET(key)`, timestamp trong key không tự tạo khả năng truy vấn khoảng.

### 7.2. Thêm thành phần phân định

Nếu một khách tạo hai đơn có cùng `createdAt` tới mili giây, khóa phân cụm chỉ có thời gian có thể không phân biệt được hai hàng trong mô hình mà clustering key xác định duy nhất hàng. Một thiết kế đầy đủ hơn là:

```text
partition = (shopId, userId, monthBucket)
sort      = (createdAt DESC, orderId ASC)
```

Ở đây `orderId` giúp phân định khi timestamp trùng. Thứ tự toàn phần vẫn phải được định nghĩa rõ, nhất là khi nhiều máy có đồng hồ lệch hoặc sự kiện đến muộn. Đối với nhật ký cần thứ tự tuyệt đối theo từng thiết bị, số thứ tự do nguồn phát sinh hoặc cơ chế cấp phát tập trung theo phạm vi có thể phù hợp hơn timestamp đơn thuần.

### 7.3. Chia bucket thời gian để giới hạn phân vùng

Nếu mỗi user có lịch sử dài, thay vì partition `(shopId, userId)` cho mọi năm, có thể chia theo tháng:

```text
partition = (shopId, userId, yyyyMM)
sort      = (createdAt DESC, orderId ASC)

(shop_17, user_42, 202611) -> các đơn tháng 11/2026
(shop_17, user_42, 202610) -> các đơn tháng 10/2026
```

Lợi ích: mỗi partition có ranh giới tăng trưởng hữu hạn hơn, dễ quản lý dữ liệu cũ. Đổi lại:

- Truy vấn qua nhiều tháng phải đọc nhiều partition và **gộp kết quả đúng thứ tự**.
- Muốn lấy 20 đơn mới nhất có thể cần đọc tháng gần nhất rồi lùi tháng trước đến khi đủ.
- Chọn bucket quá nhỏ dẫn tới nhiều partition và nhiều request; bucket quá lớn dẫn tới phân vùng cồng kềnh.
- Nếu một user phát sinh lưu lượng cực lớn trong một tháng, bucket theo tháng vẫn có thể nóng; có thể cần bucket theo ngày/giờ hoặc chiến lược khác.

**Cách chọn bucket:** ước lượng số bản ghi và byte mỗi user trong từng đơn vị thời gian, lấy cả trường hợp p95/p99 và các user cực đoan. So sánh với giới hạn và hướng dẫn thực tế của sản phẩm; không chốt “bucket theo tháng” chỉ vì tiện đặt tên.

## 8. Tính phân tán: khóa đều và khóa nóng

Giả sử có 1 triệu khóa nhưng 70% request cùng đọc/ghi vào một khóa `counter:global`. Số lượng khóa lớn **không có nghĩa tải được phân tán**. Với cơ chế hash partition, một key thường thuộc về một phân vùng tại một thời điểm; tăng số node không tự chia các request đồng thời trên **chính key đó**.

Các nguồn tạo khóa nóng:

| Mẫu khóa / workload | Vấn đề | Hướng xử lý cần cân nhắc |
| --- | --- | --- |
| `counter:global` với ghi liên tục | Một key chịu toàn bộ cập nhật | Chia bộ đếm thành nhiều shard nếu nghiệp vụ chấp nhận tổng hợp; đảm bảo cộng dồn đúng |
| `events:<today>` chứa toàn bộ sự kiện | Toàn bộ producer cùng ghi một đơn vị | Phân vùng theo đối tượng, nguồn và/hoặc bucket thời gian |
| Partition `(shopId)` cho shop rất lớn | Một tenant áp đảo hệ thống | Thêm thành phần có cardinality cao phù hợp mẫu truy cập |
| `(deviceId, day)` với một thiết bị có tải rất lớn | Bucket ngày vẫn nóng | Đo tải và chia bucket nhỏ hơn hoặc shard, chấp nhận fan-out khi đọc |
| Key tăng liên tục trong kho phân vùng theo thứ tự | Ghi dồn vào dải key mới nhất | Thiết kế prefix phân tán hoặc cơ chế partition/split phù hợp sản phẩm |

**Sharding/salting** cần mô tả cả chiều ghi và chiều đọc. Ví dụ một bộ đếm được chia thành 16 shard:

```text
counter:checkout:v1:00 -> 120
counter:checkout:v1:01 -> 109
...
counter:checkout:v1:15 -> 131

total = sum(GET(counter:checkout:v1:00..15))
```

Mỗi sự kiện phải được ánh xạ vào đúng shard bằng quy tắc có kiểm soát; thao tác đọc tổng phải lấy và cộng nhiều shard, chịu chi phí và mô hình nhất quán tương ứng. Không tự thêm hậu tố ngẫu nhiên vào key của giỏ hàng vì khi mở giỏ bằng `shopId` và `userId`, ứng dụng sẽ không biết cần đọc shard nào.

Nếu hệ thống có partition key và clustering key, **thêm trường vào clustering key không nhất thiết giảm tải phân vùng**: cần thay thành phần partition thực tế thì mới có thể phân phối sang partition khác. Thiết kế phải xét thuật toán định tuyến vật lý của hệ được chọn, thay vì suy ra từ tên các trường.

## 9. Tên khóa và ràng buộc dữ liệu nhạy cảm

Key thường xuất hiện ở nơi giá trị không xuất hiện: log truy vấn, thông báo lỗi, metrics, bản sao lưu, công cụ vận hành, dashboard và request tracing. Vì vậy **không chèn bí mật, mật khẩu, access token hoặc dữ liệu định danh nhạy cảm dạng thô vào key**.

Ví dụ cần tránh:

```text
session:eyJhbGciOi...     # token truy cập nguyên văn
email:alice@example.com  # địa chỉ email trực tiếp
phone:+84...             # số điện thoại trực tiếp
```

Có thể dùng ID nội bộ hoặc, đối với một số đường tra cứu, mã dẫn xuất phù hợp từ giá trị chuẩn hóa. Khi dùng hash của dữ liệu có entropy thấp (email, số điện thoại), **hash thường không bảo đảm ẩn danh** trước tấn công đoán từ điển. Nếu cần chống dò đoán, cân nhắc HMAC với khóa bí mật được quản lý an toàn; đồng thời xác định quy trình xoay khóa và di trú chỉ mục. HMAC cũng không thay thế quy tắc phân quyền, bảo vệ log và mã hóa dữ liệu.

Bổ sung các quy tắc:

- Không cho phép đầu vào tùy ý sinh key quá dài hoặc tạo vô hạn key mà không kiểm soát hạn mức.
- Không tin phần `tenantId` lấy từ request nếu chưa kiểm tra nó thuộc phạm vi truy cập của người gọi.
- Không dùng tiền tố `admin` hoặc `private` như một hàng rào bảo mật.
- Tách **định danh ổn định** khỏi **thông tin hiển thị** như tên shop hoặc slug URL để tránh phải đổi key khi đổi thương hiệu.

## 10. Khóa tra cứu phụ và tính nhất quán

Một đối tượng có thể phải tìm qua nhiều đường, chẳng hạn user theo `userId` hoặc email. Khi tạo hai ánh xạ:

```text
user:v1:user_42                  -> { ...profile... }
email-lookup:v1:<emailDigest>   -> user_42
```

Ứng dụng cần định nghĩa tính nhất quán:

1. Có thể có hai tài khoản cùng khai báo một email không? Nếu không, cần lệnh tạo **chỉ khi khóa chưa tồn tại** với bảo đảm nguyên tử hoặc ràng buộc unique.
2. Khi email đổi, lúc nào chỉ mục mới trở thành nguồn tra cứu chính? Có được phép tồn tại trạng thái chuyển tiếp không?
3. Nếu tạo profile thành công nhưng ghi index thất bại, hệ thống xử lý thế nào? Có cơ chế retry idempotent, rollback hoặc đối soát không?
4. Khi xóa user, index email có được xóa ngay hay cần giữ một tombstone theo chính sách tái sử dụng?

Việc có “key đẹp” chỉ giải quyết định danh, chưa giải quyết **bất biến qua nhiều key**. Nếu yêu cầu đồng bộ mạnh và sản phẩm không có giao dịch phù hợp, cần chọn nguồn dữ liệu đảm bảo ràng buộc hoặc điều chỉnh luồng nghiệp vụ.

### 10.1. Một đối tượng, nhiều read model

Ví dụ đơn hàng có thể được truy cập bằng:

- `(shopId, orderId)` để đọc chi tiết.
- `(shopId, userId, createdAt, orderId)` để đọc lịch sử của khách.
- `(shopId, status, createdAt, orderId)` để xem đơn đang xử lý.

Mô hình cột rộng thường tối ưu mỗi bảng/read model cho một nhóm truy vấn được biết trước, dẫn tới dữ liệu lặp hoặc bảng chỉ mục phụ. Khi trạng thái đơn đổi, các read model phải được cập nhật theo cơ chế đã xác định. Dữ liệu lặp giúp đọc nhanh nhưng chuyển chi phí sang **ghi và đồng bộ**. Cần công bố rõ chỗ nào nhất quán tức thời, chỗ nào chấp nhận chậm và cách xử lý sự kiện trùng/đến sai thứ tự.

## 11. Versioning, đổi khóa và di trú lược đồ

Không nên thay một cách âm thầm ý nghĩa của cùng tiền tố khóa khi các phiên bản ứng dụng cùng tồn tại.

Giả sử phiên bản đầu dùng:

```text
cart:v1:<shopId>:<userId>
```

Sau đó cần hỗ trợ nhiều giỏ trên mỗi user và định danh theo `cartId`:

```text
cart:v2:<shopId>:<cartId>
active-cart-by-user:v1:<shopId>:<userId> -> <cartId>
```

Đây là thay đổi **mô hình nghiệp vụ và đường truy cập**, không chỉ là đổi dấu phân cách. Một kế hoạch chuyển đổi nên xác định:

1. **Hợp đồng mới:** Cách sinh `cartId`, điều kiện duy nhất, nguồn dữ liệu có thẩm quyền, ánh xạ `userId → cartId`.
2. **Đọc tương thích:** Trong giai đoạn chuyển tiếp có thể đọc key mới trước và fallback key cũ theo quy tắc có kiểm soát.
3. **Di trú:** Chuyển dữ liệu còn hiệu lực; bảo vệ cập nhật đồng thời và phát sinh trong lúc chuyển bằng giao dịch/cơ chế phiên bản hoặc một nguồn ghi duy nhất.
4. **Đo lường:** Quan sát số key còn ở phiên bản cũ, lỗi không tìm thấy, phiên bản ghi và sai khác giữa ánh xạ.
5. **Cắt chuyển:** Chỉ bỏ đường đọc cũ khi có bằng chứng tất cả dữ liệu cần thiết đã được chuyển hoặc hết vòng đời.
6. **Dọn dẹp:** Xóa key cũ theo chính sách lưu giữ/TTL sau khi loại bỏ dependency, tránh xóa quá sớm.

Không phải mọi sửa đổi JSON đều cần `v2` trong key. **Phiên bản key** thường đáng dùng khi cách định danh, định tuyến hoặc mã hóa thay đổi; **phiên bản schema của value** có thể quản lý riêng nếu khóa giữ nguyên.

Một thiết kế nên ghi rõ “khi đổi tên key thì sẽ làm gì”: tạo mới, đặt alias, giữ backward compatibility, hay chuyển toàn bộ tham chiếu. Đó là phần quan trọng của **khả năng tiến hóa** trong mô hình dữ liệu.

## 12. Kiểm chứng thiết kế bằng ví dụ đầy đủ

### 12.1. Đề bài

Một dịch vụ thu thập nhiệt độ của thiết bị IoT:

- Mỗi thiết bị thuộc một tenant.
- Thiết bị gửi từ một vài đến hàng nghìn số đo mỗi phút, có thể gửi lại cùng số đo khi mạng lỗi.
- API cần lấy 100 số đo mới nhất của một thiết bị, hoặc số đo của thiết bị trong khoảng `[from, to)`.
- Dữ liệu lưu tối đa 90 ngày; một số tenant có lưu lượng cao vượt trội.
- Mỗi bản ghi có `measurementId` duy nhất trong phạm vi thiết bị, thời gian sự kiện và nhiệt độ.

### 12.2. Thiết kế đề xuất

Bắt đầu bằng mẫu khóa cho kho có hỗ trợ partition và sort:

```text
partition key = (tenantId, deviceId, dayBucketUTC)
sort key      = (eventTime DESC, measurementId ASC)
value         = {temperature, receivedAt, qualityFlags, schemaVersion}
```

Một phần dữ liệu minh họa:

| Partition | Sort | Value |
| --- | --- | --- |
| `(tenant_7, dev_12, 20261122)` | `(2026-11-22T11:01:00.000Z, m_901)` | `{temperature: 24.1}` |
| `(tenant_7, dev_12, 20261122)` | `(2026-11-22T11:00:00.000Z, m_900)` | `{temperature: 24.0}` |
| `(tenant_7, dev_12, 20261121)` | `(2026-11-21T23:59:59.000Z, m_899)` | `{temperature: 23.8}` |

Thiết kế hỗ trợ một đường đọc theo thiết bị và ngày. Để tìm 100 bản ghi mới nhất, dịch vụ bắt đầu ở bucket hôm nay và tiếp tục lùi ngày đến khi đủ; nếu tenant có số đo rất thưa, cần giới hạn số bucket được đọc hoặc có chỉ mục hỗ trợ. Để đọc khoảng ngày, xác định các bucket giao với khoảng và gộp theo thời gian.

**Ràng buộc gửi lại:** chỉ thêm `measurementId` vào clustering key **không bảo đảm** cùng một `measurementId` sẽ không lặp ở các timestamp khác nhau. Nếu thiết bị có thể gửi lại một ID với thời gian thay đổi, phải định nghĩa nguồn thời gian chuẩn hoặc duy trì ràng buộc idempotency theo `(tenantId, deviceId, measurementId)`. Tính duy nhất cần gắn với đúng thành phần nghiệp vụ, không suy ra từ một cặp thời gian + ID.

**Vấn đề tải:** nếu một thiết bị gửi hàng nghìn bản ghi/phút, bucket ngày có thể quá lớn hoặc nóng. Lúc này đo số ghi/giây và byte/ngày rồi cân nhắc bucket giờ, shard bổ sung, hoặc hệ time-series chuyên dụng; mọi shard bổ sung đều làm truy vấn khoảng cần fan-out.

**Vấn đề TTL:** giữ 90 ngày theo thời điểm nhận hay thời điểm sự kiện? Nếu thiết bị gửi muộn, hai cách cho kết quả xóa khác nhau. Đặt chính sách rõ ràng và xác nhận tính năng TTL ở cấp hàng/cột/phân vùng của hệ quản trị, kể cả tác động vận hành của xóa dữ liệu.

### 12.3. Khi chỉ có key–value `GET/PUT`

Không thể lấy “100 số đo mới nhất” bằng cách chỉ biết prefix `measure:tenant_7:dev_12:...` nếu kho không hỗ trợ truy vấn tiền tố/thứ tự. Các phương án gồm:

- Chọn hệ thống có partition + sort key hoặc cơ sở dữ liệu chuỗi thời gian phù hợp.
- Duy trì chỉ mục/list của measurement ID mới nhất theo thiết bị với thao tác cập nhật nhất quán.
- Gộp số đo thành **khối dữ liệu giới hạn** theo bucket nếu phần lớn truy cập đọc cùng khối, với giới hạn kích thước và cơ chế chống ghi đè.

Thiết kế cuối cùng phải phù hợp cả yêu cầu **đọc theo thời gian**, **ghi lặp**, **giới hạn kích thước**, và **cách lưu trữ thực sự hỗ trợ**.

## 13. Các lỗi thiết kế thường gặp

| Dấu hiệu | Tại sao là vấn đề | Cách điều chỉnh |
| --- | --- | --- |
| Dùng email/slug/tên làm khóa chính | Giá trị có thể đổi, lộ thông tin hoặc không duy nhất ở phạm vi mong muốn | Dùng ID ổn định; thêm đường tra cứu phụ có kiểm soát |
| Nối khóa ghép mà không escape | Hai tuple khác nhau tạo cùng key | Cấm ký tự phân cách hoặc dùng mã hóa có khả năng giải mã duy nhất |
| Thêm `tenantId` vào chuỗi rồi xem là đã phân quyền | Đường ghi/đọc vẫn có thể truy cập sai tenant | Kiểm tra tenant từ danh tính và quyền tại API và tầng lưu trữ |
| Tin rằng key có tiền tố chung sẽ được lưu cạnh nhau | Hệ hash có thể phân tán key theo toàn chuỗi | Kiểm tra cơ chế partition và khả năng scan/range thực tế |
| Partition theo toàn shop cho lịch sử nhiều năm | Phân vùng cực lớn hoặc nóng | Tách theo khách, loại dữ liệu, bucket hoặc read model khác theo workload |
| Lấy timestamp làm khóa duy nhất | Hai sự kiện có thể trùng thời gian; thứ tự không tuyệt đối | Thêm ID/sequence và xác định ràng buộc idempotency |
| Bucket thời gian quá ngắn | Nhiều partition, tăng fan-out/chi phí đọc | Chọn độ rộng bucket theo đo lường và SLA |
| Gắn shard ngẫu nhiên vào mọi key | Khó xác định key từ ID nghiệp vụ | Chỉ shard khi có chiến lược định tuyến đọc/ghi rõ ràng |
| Đổi quy ước key ngay trong ứng dụng đang chạy | Đứt đường đọc giữa các phiên bản, sinh dữ liệu mồ côi | Quản lý phiên bản và di trú có đo lường |
| Coi mọi “composite key” đều có tác dụng như nhau | Key ghép chuỗi khác với partition + clustering | Tách khóa logic khỏi khả năng truy vấn của sản phẩm |

## 14. Checklist trước khi chốt lược đồ vật lý

Với mỗi loại key hoặc bảng, ghi được một bản mô tả ngắn bao gồm:

- **Chủ thể:** Loại thực thể/aggregate, ai sở hữu và phạm vi tenant.
- **Mẫu truy cập:** Input biết trước, thao tác `GET`/range/scan, điều kiện lọc, sort, phân trang, tần suất và SLA.
- **Định danh:** Thành phần khóa, loại ID, phạm vi duy nhất, ai cấp phát, có được sửa/tái sử dụng không.
- **Mã hóa:** Định dạng cụ thể, bộ mã byte, giới hạn độ dài, delimiter/escape hoặc tuple, chuẩn hóa và xử lý giá trị không hợp lệ.
- **Vật lý:** Partition key, sort/clustering key (nếu có), dự kiến kích thước và số lượng bản ghi mỗi partition, phân bố tải và key nóng.
- **Đúng đắn:** Ràng buộc trong một giá trị và giữa nhiều key, ghi đồng thời, idempotency, điều kiện nhất quán.
- **Bảo mật/vòng đời:** PII trong key, quyền theo tenant, TTL, lưu giữ, xóa, backup và phục hồi.
- **Tiến hóa:** Phiên bản key/value, thay đổi định danh, đọc tương thích, di trú, quan sát và kế hoạch loại bỏ dữ liệu cũ.

Cần kèm ít nhất bốn phép thử:

1. Hai bộ thành phần khóa khác nhau không được mã hóa thành cùng key, kể cả khi có delimiter, Unicode, khoảng trắng và giá trị trống.
2. Cùng một đối tượng luôn tạo **cùng key chuẩn** ở tất cả dịch vụ và ngôn ngữ lập trình.
3. Dữ liệu lớn nhất và tenant nóng nhất vẫn nằm trong giới hạn phân vùng/kích thước/chi phí đã chọn; đo ở p95/p99 thay vì chỉ lấy trung bình.
4. Khi đổi ID tra cứu phụ, dữ liệu không bị mất, không vi phạm uniqueness và không cho phép đọc chéo tenant.

## 15. Bài tập vận dụng

### Bài tập A — Giỏ hàng đa tenant

Yêu cầu: một user có đúng một giỏ hiện tại trong mỗi shop, có thể đổi email và cùng user ID xuất hiện trong nhiều shop.

Hãy chọn giữa hai key:

```text
A. cart:<email>
B. cart:v1:<shopId>:<userId>
```

**Gợi ý đáp án:** B thể hiện rõ phạm vi của giỏ và sử dụng ID ổn định. Tuy nhiên, chỉ đúng nếu `shopId` và `userId` được cấp phát/kiểm tra theo quy tắc, không chứa delimiter chưa escape và hệ thống kiểm tra phân quyền shop. Nếu cùng shop có nhiều giỏ, phải sửa giả định nghiệp vụ và bổ sung `cartId` hoặc ánh xạ giỏ hiện tại.

### Bài tập B — Đơn hàng theo khách

API cần: `GET /shops/{shopId}/customers/{userId}/orders?from=...&to=...&limit=20`, thời gian lưu giữ 5 năm, shop lớn có hàng triệu khách.

**Gợi ý mô hình:** phân vùng theo `(shopId, userId, monthBucket)`, clustering theo `(createdAt, orderId)`, có quy tắc sort theo chiều phục vụ truy vấn. Sau đó tính số partition phải đọc theo độ dài khoảng ngày; làm rõ bucket quá lớn/nhỏ và thiết kế đường truy cập `(shopId, orderId)` riêng nếu cần lấy chi tiết đơn bằng ID.

### Bài tập C — Khóa ghép chứa chuỗi không kiểm soát

Hai cặp giá trị là `("north:sales", "customer3")` và `("north", "sales:customer3")`. Chỉ ra vì sao phép nối bằng `:` gây lỗi, rồi đề xuất bộ mã không nhập nhằng.

**Gợi ý đáp án:** hai cặp đều tạo `north:sales:customer3`. Có thể dùng escape từng thành phần hoặc length-prefix; định nghĩa số byte, tập ký tự và quy tắc giải mã nhất quán. Nếu cần truy vấn prefix hoặc sort, kiểm tra định dạng mã hóa có giữ được tính chất đó trên hệ lưu trữ hay không.

### Bài tập D — Một thiết bị quá nóng

Tất cả số đo của thiết bị `dev_1` đặt trong partition `(tenant_7, dev_1)`. Sau triển khai, ghi bị nghẽn và dữ liệu tăng nhanh.

**Gợi ý đáp án:** đánh giá bucket theo ngày/giờ và nếu cần shard, nhưng chỉ quyết định sau khi đo tải p95/p99, kích thước partition và chi phí fan-out đọc. Nếu truy vấn thường đọc khoảng liên tục, cũng nên xem hệ time-series hoặc giải pháp phù hợp hơn.

## Tổng kết kiến thức

**Thiết kế khóa là thiết kế hợp đồng truy cập.** Một không gian tên rõ ràng cho biết khóa thuộc miền nào, định danh đối tượng nào và có thể tiến hóa ra sao. Khóa ghép phải có mã hóa không nhập nhằng và phạm vi duy nhất xác định. Khóa phân vùng và khóa sắp xếp phải được chọn theo workload thực tế, vì mỗi thay đổi trong thành phần khóa có thể làm thay đổi cách lưu trữ, phân phối tải và phạm vi truy vấn.

Khi đánh giá phương án, luôn kiểm tra: **Ứng dụng biết những thành phần nào của khóa? Có cần sắp xếp hoặc lọc theo khoảng không? Dữ liệu cùng phân vùng sẽ lớn và nóng tới mức nào? Các ràng buộc nhất quán và quyền truy cập được thực thi ở đâu?** Trả lời bốn câu hỏi đó giúp mô hình khóa–giá trị hoặc cột rộng phục vụ đúng nghiệp vụ và vẫn có khả năng thay đổi khi dữ liệu tăng.
