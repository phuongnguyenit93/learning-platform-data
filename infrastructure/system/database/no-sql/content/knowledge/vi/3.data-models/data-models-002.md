# Khóa–giá trị: truy cập qua định danh và thao tác trên giá trị

## 1. Mô hình khóa–giá trị là gì?

Trong nhóm mô hình dữ liệu NoSQL, **key–value (khóa–giá trị)** tổ chức thông tin thành các cặp gồm một **khóa (key)** và một **giá trị (value)**. Ứng dụng biết khóa nào thì có thể yêu cầu hệ lưu trữ lấy, ghi, thay thế hoặc xóa giá trị gắn với khóa đó.

Có thể hình dung một không gian khóa–giá trị như một ánh xạ:

\[
\text{Store}: \text{Key} \longrightarrow \text{Value}
\]

Ví dụ:

| Khóa | Giá trị | Ý nghĩa |
|---|---|---|
| `user:42:profile` | `{"displayName":"An","language":"vi"}` | Hồ sơ người dùng 42 |
| `cart:42` | `{"items":[{"sku":"BK-01","quantity":2}]}` | Giỏ hàng của người dùng 42 |
| `feature:checkout-v2` | `true` | Cờ bật/tắt một tính năng |
| `session:7f3c...` | Dữ liệu phiên đăng nhập | Tra cứu trạng thái bằng mã phiên |
| `rate:api:tenant-17:minute-202611141530` | `18` | Bộ đếm request theo một cửa sổ thời gian |

Mỗi khóa đại diện cho một định danh được ứng dụng quy ước. Trong không gian khóa và phạm vi được sản phẩm định nghĩa, một khóa xác định một mục dữ liệu để thao tác. Tùy hệ thống, giá trị có thể là chuỗi, số, dữ liệu nhị phân, JSON đã tuần tự hóa, hay một cấu trúc do database hỗ trợ trực tiếp.

**Ý tưởng trung tâm:** muốn lấy thông tin, ứng dụng thường **biết hoặc tạo được khóa**. Mô hình này rất phù hợp với các thao tác “lấy theo ID”, “ghi trạng thái theo ID” và “tăng bộ đếm theo ID”.

### 1.1. Khác gì với tìm kiếm theo thuộc tính?

Giả sử cần lấy hồ sơ người dùng có ID `42`:

~~~text
GET user:42:profile
~~~

Ứng dụng xây được khóa từ ID nên có đường truy cập trực tiếp.

Nhưng nếu yêu cầu là “tìm mọi người dùng sống ở Hà Nội”, ứng dụng chỉ biết **thuộc tính**, không biết danh sách khóa của những người thỏa điều kiện. Một kho key–value thuần túy chưa chắc có khả năng truy vấn theo trường `city` nằm trong value. Có thể cần chỉ mục bổ sung, cấu trúc dữ liệu khác, công cụ tìm kiếm hoặc sản phẩm hỗ trợ query nâng cao.

Phân biệt hai câu hỏi:

- **Truy cập bằng định danh:** “Giá trị của khóa `user:42:profile` là gì?”
- **Truy vấn theo nội dung:** “Những value nào có thuộc tính `city = 'Hanoi'`?”

Hai yêu cầu dẫn đến các phương án thiết kế khác nhau. Một giá trị chứa JSON **không tự động biến** kho key–value thuần túy thành hệ truy vấn document.

### 1.2. Không đồng nhất mọi sản phẩm key–value

Một số sản phẩm chỉ coi value là một khối dữ liệu mà phía ứng dụng tự diễn giải. Sản phẩm khác có các kiểu dữ liệu và lệnh thao tác trên danh sách, tập hợp, hash, bộ đếm hoặc cấu trúc phức tạp. Cũng có sản phẩm cung cấp chỉ mục phụ, giao dịch, biểu thức điều kiện hoặc cách truy vấn theo khóa ghép.

Vì thế, có hai tầng cần giữ riêng:

1. **Mô hình khái niệm:** định danh ánh xạ đến một giá trị.
2. **Bảo đảm và API cụ thể:** sản phẩm hỗ trợ kiểu value nào, thao tác nào nguyên tử, đọc/ghi nhất quán đến đâu, kích thước và TTL bị giới hạn ra sao.

Bài này dùng các phép `GET`, `PUT`, `DELETE` như **ký hiệu khái niệm**; chúng không phải cú pháp chung bắt buộc của mọi database NoSQL.

## 2. Ba thành phần cần hiểu rõ: khóa, giá trị và phép thao tác

### 2.1. Khóa là “địa chỉ logic” của dữ liệu

Khóa dùng để xác định mục dữ liệu. Trong code, một khóa thường được xây từ thông tin nghiệp vụ:

~~~text
profileKey(userId) = "user:" + userId + ":profile"
cartKey(userId)    = "cart:" + userId
orderKey(orderId)  = "order:" + orderId
~~~

Nếu mã người dùng là `42` thì `cartKey(42)` tạo ra `cart:42`. Để đọc giỏ hàng, ứng dụng không cần thực hiện một phép tìm kiếm trên trường `userId` bên trong toàn bộ value.

Điểm cần phân biệt: khóa vừa là **cách đặt tên dữ liệu ở tầng ứng dụng**, vừa có thể là **đầu vào cho cách phân vùng vật lý** của database. Tuy nhiên, một chuỗi giống nhau về hình thức không có nghĩa hệ thống nào cũng phân vùng hoặc sắp xếp khóa theo cách giống nhau.

### 2.2. Giá trị là nội dung được gắn với khóa

Ví dụ value của khóa `cart:42` có thể là:

~~~json
{
  "schemaVersion": 1,
  "ownerId": "42",
  "items": [
    { "sku": "BK-01", "quantity": 2 },
    { "sku": "PEN-09", "quantity": 1 }
  ],
  "updatedAt": "2026-11-14T08:00:00Z"
}
~~~

Ứng dụng phải quyết định value nên chứa gì: một trường nhỏ, toàn bộ đối tượng, một danh sách, một snapshot, hay tham chiếu đến dữ liệu ở nơi khác. Value lớn có thể thuận tiện cho đọc nhưng khiến mỗi lần cập nhật phải truyền và ghi nhiều dữ liệu; value nhỏ có thể dễ cập nhật nhưng cần nhiều khóa và nhiều lần đọc.

Một value chứa các trường có tên chưa đảm bảo database có thể lọc, sắp xếp hay cập nhật riêng từng trường. Cần xem mô hình truy cập của **sản phẩm cụ thể**.

### 2.3. Các phép thao tác thường gặp

| Phép thao tác mang tính khái niệm | Đầu vào → kết quả mong muốn | Điều cần lưu ý |
|---|---|---|
| `GET(key)` | Khóa → giá trị hiện có hoặc trạng thái không tìm thấy | Phải định nghĩa cách xử lý key thiếu, timeout, quyền truy cập |
| `PUT(key, value)` | Khóa, value → lưu mới hoặc thay thế | Có thể mặc định ghi đè; cần xem sản phẩm |
| `DELETE(key)` | Khóa → xóa mục dữ liệu | Xóa logic, xóa vật lý và replication có thể khác nhau |
| `EXISTS(key)` | Khóa → có hay không | Không thay thế được kiểm tra điều kiện nguyên tử trước thao tác tiếp theo |
| `PUT_IF_ABSENT(key, value)` | Chỉ ghi nếu khóa chưa tồn tại | Tùy sản phẩm; thường dùng cho tạo duy nhất hoặc idempotency |
| `COMPARE_AND_SET(key, expected, new)` | Chỉ ghi khi điều kiện hiện tại đúng | Không phải API phổ quát; có thể triển khai bằng version/conditional write |
| `INCREMENT(key, delta)` | Thay đổi giá trị số | Chỉ có nếu được hỗ trợ; phạm vi nguyên tử phải tra tài liệu |
| `EXPIRE(key, ttl)` | Gán thời gian hết hạn | Ngữ nghĩa thời hạn, độ chính xác và cách xóa tùy hệ |
| `BATCH(keys, operations)` | Nhiều thao tác trong một yêu cầu | Batch không mặc nhiên là transaction nguyên tử nhiều khóa |

**“Thường gặp” không có nghĩa “được hỗ trợ ở mọi hệ key–value”.** Bắt buộc tra tài liệu nếu nghiệp vụ dựa vào thao tác có điều kiện, giao dịch, độ bền sau khi ghi hay TTL.

## 3. Vòng đời một cặp khóa–giá trị

Giả sử hệ thống quản lý giỏ hàng theo ID người dùng.

~~~mermaid
flowchart TD
    A["Tạo key từ userId"] --> B["GET cart:42"]
    B --> C{"Key có tồn tại?"}
    C -->|Không| D["Tạo giỏ hàng rỗng ở ứng dụng"]
    C -->|Có| E["Đọc và giải mã value"]
    D --> F["Thêm hoặc sửa sản phẩm"]
    E --> F
    F --> G["Ghi value mới theo key"]
    G --> H["Kiểm tra kết quả ghi"]
    H --> I["Lần đọc tiếp theo dùng cùng key"]
~~~

Các bước chính:

1. **Xác định khóa.** Ứng dụng quyết định `cart:42` là nơi chứa giỏ hàng của người dùng `42`.
2. **Đọc.** Store nhận khóa và trả về giá trị hoặc trạng thái không tồn tại.
3. **Diễn giải.** Nếu value là JSON, ứng dụng giải mã và kiểm tra phiên bản cấu trúc.
4. **Thao tác.** Thêm sản phẩm, đổi số lượng hoặc xóa sản phẩm trong giỏ.
5. **Ghi.** Lưu value mới; khi có ghi đồng thời phải dùng cơ chế chống mất cập nhật phù hợp.
6. **Xóa hoặc hết hạn.** Giỏ có thể bị xóa khi người dùng thanh toán hoặc hết hạn theo chính sách sản phẩm.

Đồ thị mô tả logic, chưa nói store hỗ trợ lệnh gì và thao tác ghi có nguyên tử hay không. Phần xử lý đồng thời sẽ được làm rõ ở mục 6.

## 4. Thiết kế khóa theo mẫu truy cập

### 4.1. Xác định trước cách truy cập

Trước khi đặt tên khóa, hãy liệt kê câu hỏi hệ thống cần trả lời:

| Nhu cầu | Dữ kiện đầu vào đã biết | Khóa gợi ý |
|---|---|---|
| Lấy hồ sơ theo ID | `userId` | `user:{userId}:profile` |
| Lấy giỏ hàng theo người dùng | `userId` | `cart:{userId}` |
| Lấy đơn theo mã đơn | `orderId` | `order:{orderId}` |
| Đọc cờ tính năng theo tên | `featureName` | `feature:{featureName}` |
| Đếm request trong phút theo tenant | `tenantId` và cửa sổ thời gian | `rate:{tenantId}:{yyyyMMddHHmm}` |

Hầu hết ví dụ trên là **point lookup**: biết khóa và cần lấy đúng một mục. Đây là kiểu truy cập tự nhiên của key–value.

Ngược lại, nếu yêu cầu “liệt kê mọi đơn của một khách hàng từ mới đến cũ”, một khóa `order:{orderId}` không trả lời trực tiếp. Có thể phải bổ sung danh sách ID theo khách hàng, dữ liệu tổng hợp, chỉ mục, hoặc chọn sản phẩm cho phép truy vấn theo một khóa phân vùng và tiêu chí sắp xếp.

### 4.2. Quy ước đặt khóa

Tên khóa nên giúp ứng dụng xác định loại dữ liệu và tránh đụng tên:

~~~text
{domain}:{entityId}:{purpose}
{environment}:{tenantId}:{domain}:{entityId}
~~~

Ví dụ:

~~~text
prod:tenant17:user:42:profile
prod:tenant17:user:42:preferences
prod:tenant17:cart:42
~~~

Lưu ý thực tế:

- **Nhất quán:** thống nhất chữ hoa/chữ thường, dấu phân cách, định dạng ID và cách escape ký tự phân tách nếu ID tự do.
- **Độc nhất trong phạm vi cần thiết:** nếu ứng dụng đa tenant, đừng để hai tenant cùng ghi vào `cart:42` khi yêu cầu tách biệt.
- **Ổn định:** thay đổi định dạng khóa cần có kế hoạch migration hoặc đọc cả dạng cũ và mới.
- **Không lộ bí mật:** không dùng mật khẩu, token dễ đoán hay dữ liệu cá nhân nhạy cảm làm key được ghi vào log. Dùng định danh phù hợp và phân quyền đúng.
- **Độ dài hợp lý:** khóa dài làm tăng dung lượng lưu, băng thông và đôi khi ảnh hưởng hiệu năng hoặc chi phí.
- **Không suy ra được phép quét theo prefix:** tên khóa bắt đầu bằng `user:` không đảm bảo sản phẩm có API liệt kê prefix hiệu quả.

**Lưu ý về phân vùng:** nhiều hệ phân tán quyết định vị trí lưu bằng hàm hash hoặc partition key. Một khóa được truy cập quá thường xuyên có thể tạo *hot key/hot partition*. Chia khóa để phân tán tải phải dựa vào access pattern thực tế: việc thêm hậu tố ngẫu nhiên có thể khiến một lần đọc cần truy vấn nhiều khóa.

### 4.3. Khi một thực thể có nhiều lối truy cập

Giả sử có:

~~~text
user:42:profile -> {"email":"a@example.test","displayName":"An"}
~~~

Ứng dụng muốn tìm người dùng bằng email. Nếu store chỉ hỗ trợ truy cập theo key, có thể xây thêm ánh xạ:

~~~text
email-to-user:<normalized-email-key> -> "42"
~~~

Luồng đọc là “email → userId → profile”. Tuy nhiên, khi đổi email phải cập nhật **hai khóa**. Nếu cập nhật không có giao dịch phù hợp, xảy ra lỗi giữa hai lần ghi có thể để lại mapping cũ hoặc sai. Cũng cần xử lý cạnh tranh khi hai yêu cầu cùng đăng ký một email.

Đây là đánh đổi của **secondary lookup được quản lý ở ứng dụng**. Một số sản phẩm có secondary index hoặc tính năng truy vấn riêng; không thể áp đặt chung một cách xây chỉ mục cho tất cả hệ key–value.

## 5. Thao tác trên value: toàn bộ khối hay một phần cấu trúc?

### 5.1. Thay thế toàn bộ value

Ở một interface key–value tối giản, cập nhật nghĩa là đọc value, sửa tại ứng dụng rồi ghi value mới:

~~~text
old = GET("user:42:profile")
profile = decode(old)
profile.language = "en"
PUT("user:42:profile", encode(profile))
~~~

Đây là **mã giả**, không phải cú pháp của sản phẩm cụ thể. Nếu value chứa nhiều thuộc tính, thay đổi một trường vẫn có thể phải ghi lại toàn bộ value. Vì vậy kích thước value và số lần cập nhật có ảnh hưởng trực tiếp đến hiệu năng.

### 5.2. Cập nhật ngay trong store

Một số database key–value cho phép thao tác trực tiếp trên kiểu value được quản lý bởi server, ví dụ:

- tăng bộ đếm số nguyên;
- thêm phần tử vào set;
- thêm phần tử vào list;
- sửa một trường trong cấu trúc hash/map;
- đặt thời gian hết hạn hoặc áp dụng điều kiện chỉ ghi khi key chưa tồn tại.

Lúc đó application không nhất thiết phải tải, sửa rồi ghi lại cả khối dữ liệu. Nhưng **phạm vi nguyên tử, kiểu dữ liệu hợp lệ và hành vi khi lỗi** là đặc tả sản phẩm.

Ví dụ minh họa cú pháp **Redis**, không phải cú pháp NoSQL chung:

~~~redis
SET feature:checkout-v2 "enabled"
GET feature:checkout-v2

SET session:7f3c "user=42" EX 1800
GET session:7f3c
TTL session:7f3c

INCR metric:login:20261114
DEL feature:checkout-v2
~~~

Ở ví dụ này:

- `SET` ghi giá trị chuỗi theo key.
- `GET` đọc giá trị chuỗi.
- `EX 1800` đặt thời gian hết hạn theo giây ở lệnh `SET`.
- `TTL` đọc thời gian sống còn lại theo ngữ nghĩa Redis.
- `INCR` tăng giá trị số mà Redis quản lý.
- `DEL` xóa key.

Redis còn có các kiểu dữ liệu và lệnh khác, nhưng không vì vậy mà mọi key–value store đều phải hỗ trợ chúng. Lựa chọn persistence, replication, eviction và tính bền vững của các thao tác này phải xác minh theo cấu hình.

### 5.3. Giá trị có cấu trúc vẫn cần một hợp đồng dữ liệu

Giả sử value mã hóa JSON cho giỏ hàng. Nhóm phát triển cần quy ước:

- Trường nào bắt buộc, trường nào có thể thiếu?
- Số tiền dùng đơn vị nào? Tránh mất chính xác do dùng số thực không phù hợp.
- `schemaVersion` nào đang được ghi và phiên bản cũ được đọc ra sao?
- Nếu cả người dùng và một background job cùng sửa giỏ thì xung đột được xử lý thế nào?
- Value có vượt kích thước tối đa hoặc giới hạn request của sản phẩm không?
- Những thông tin nào không nên để nguyên trong value, hoặc cần bảo vệ bằng quyền truy cập/mã hóa?

**“Schema linh hoạt” không đồng nghĩa với “không có schema”.** Hợp đồng dữ liệu của ứng dụng vẫn tồn tại dù database không kiểm tra mọi trường.

## 6. Ghi đồng thời và nguy cơ mất cập nhật

### 6.1. Vì sao đọc–sửa–ghi có thể sai?

Giả sử value ban đầu là:

~~~json
{ "version": 3, "quantity": 1 }
~~~

Hai request A và B đồng thời tăng `quantity`:

| Thời điểm | Request A | Request B |
|---|---|---|
| T1 | Đọc `quantity = 1` | |
| T2 | | Đọc `quantity = 1` |
| T3 | Ghi `quantity = 2` | |
| T4 | | Ghi `quantity = 2` |
| Kết quả | | Cả hai đều tăng 1, nhưng kết quả là 2 thay vì 3 |

Mỗi lệnh ghi có thể thành công riêng lẻ mà **toàn bộ chuỗi đọc–sửa–ghi vẫn không nguyên tử**. Không được ngộ nhận “key–value có thao tác trên một key” đồng nghĩa “mọi phép cập nhật trên key đó tự động an toàn khi cạnh tranh”.

### 6.2. Cách xử lý tùy tính năng sản phẩm

**Cách A — Phép tăng nguyên tử:** nếu store hỗ trợ `INCREMENT(key, 1)` với bảo đảm phù hợp, mỗi request tăng trực tiếp trên server. Đây là lựa chọn tự nhiên cho bộ đếm nhưng chưa chắc giải được cập nhật đối tượng phức tạp.

**Cách B — Conditional write / compare-and-set (CAS):** ghi value mới chỉ khi phiên bản hoặc điều kiện quan sát trước đó còn đúng.

~~~text
function incrementWithVersion(key):
    repeat:
        current = GET(key)                  // value và version
        next = copy(current)
        next.quantity = current.quantity + 1
        next.version = current.version + 1

        success = COMPARE_AND_SET(
            key,
            expectedVersion = current.version,
            newValue = next
        )

        if success:
            return next
        // Có ghi khác chen vào: đọc lại rồi thử tiếp
~~~

Đây là **mã giả diễn tả ý tưởng**. Tên lệnh, cách version được lưu, mức cô lập, chi phí retry và lỗi có thể khác nhau theo hệ thống. Việc đọc version và kiểm tra trước khi ghi phải được triển khai bằng cơ chế **nguyên tử do store cung cấp**, không phải hai câu lệnh “kiểm tra rồi ghi” tách rời ở phía client.

**Cách C — Giao dịch hoặc script phía server:** một số sản phẩm cung cấp transaction hay khả năng thực thi nhiều thao tác trong một đơn vị nguyên tử. Phải đọc tài liệu để xác định phạm vi áp dụng: một key, nhiều key, một partition hay nhiều partition.

**Cách D — Thiết kế lại cấu trúc dữ liệu:** thay vì mỗi thao tác sửa toàn bộ một value lớn, có thể tách những thực thể cập nhật độc lập thành key khác nhau hoặc đưa cập nhật qua một bộ xử lý tuần tự. Giải pháp này đánh đổi độ đơn giản của việc đọc gộp lấy kiểm soát đồng thời.

### 6.3. Đừng nhầm atomicity với idempotency

- **Atomicity:** thao tác có xảy ra trọn vẹn theo phạm vi đã định nghĩa hay không.
- **Idempotency:** thực hiện lại cùng một yêu cầu có tạo tác dụng nghiệp vụ ngoài mong muốn hay không.
- **Consistency:** trạng thái nào các lượt đọc được phép quan sát và các bất biến phải được giữ thế nào.
- **Durability:** dữ liệu đã xác nhận thành công có được giữ lại trước các dạng sự cố nào.

Ví dụ, `INCREMENT` có thể nguyên tử nhưng request bị timeout sau khi server đã tăng. Nếu client gửi lại và tăng lần nữa thì bộ đếm có thể tăng hai lần. Cần thiết kế **request ID/idempotency key** và cơ chế ghi có điều kiện hoặc transaction phù hợp nếu thao tác nghiệp vụ chỉ được tính một lần.

## 7. Key không tồn tại, timeout và kết quả không chắc chắn

Các trường hợp dưới đây phải được phân biệt:

| Hiện tượng | Có thể có nghĩa | Cách ứng dụng xử lý |
|---|---|---|
| Không tìm thấy key | Key chưa từng ghi, đã bị xóa, đã hết hạn hoặc không nhìn thấy theo ngữ nghĩa đọc của sản phẩm | Quy định rõ fallback, tạo mới hay trả lỗi |
| Key tồn tại, value rỗng | Dữ liệu hợp lệ nhưng rỗng, hoặc hợp đồng dữ liệu có vấn đề | Phân biệt với “không có key” |
| Lỗi kết nối trước khi gửi | Thao tác chưa chắc đã đi đến store | Retry có backoff nếu phù hợp |
| Timeout sau khi gửi write | Server có thể đã ghi hoặc chưa ghi; client chưa biết kết quả | Kiểm tra idempotency/đọc lại theo bảo đảm của sản phẩm |
| Ghi bị từ chối vì điều kiện | Có request khác thay đổi value hoặc key đã tồn tại | Trả conflict hoặc đọc lại, tính toán lại |
| Key hết hạn trong lúc xử lý | Giá trị vừa đọc có thể không còn tồn tại ở lần thao tác sau | Thiết kế để chịu được thay đổi theo thời gian |

Một hàm `GET(key)` trong code không nên lẫn lộn kết quả `NOT_FOUND` với lỗi mạng, lỗi phân quyền hoặc lỗi giải mã value. Trường hợp nào ứng dụng có thể retry cũng phụ thuộc việc thao tác có an toàn khi lặp lại không.

## 8. TTL: giá trị có vòng đời

**Time to live (TTL)** thể hiện thời gian một mục dữ liệu còn được xem là hợp lệ theo cơ chế của sản phẩm. TTL hữu ích cho:

- phiên đăng nhập hoặc session có thời hạn;
- cache dữ liệu có thể tạo lại;
- mã xác thực dùng một lần (kèm điều kiện sử dụng một lần đúng cách);
- bộ đếm theo cửa sổ thời gian;
- token hoặc trạng thái tạm của một quy trình.

Ví dụ khái niệm:

~~~text
PUT("session:7f3c", sessionData, ttl = 30 minutes)
~~~

Cần xác minh **TTL bắt đầu từ thời điểm nào**, một lần ghi mới có làm mới TTL không, đọc có tự gia hạn không, dữ liệu hết hạn có bị xóa vật lý ngay không, và TTL có giữ nguyên sau restore hoặc failover không. Không mặc định database nào cũng có cơ chế giống Redis.

TTL **không tự thay thế** kiểm tra quyền truy cập, thu hồi session, chính sách xóa dữ liệu theo pháp lý hay đảm bảo xóa tuyệt đối khỏi backup. Với dữ liệu quan trọng, ứng dụng phải tính đến trường hợp key biến mất sớm hoặc còn được quan sát theo cách sản phẩm định nghĩa.

### 8.1. Cache và dữ liệu nguồn là hai vai trò khác nhau

Một ứng dụng có thể dùng kho key–value làm cache trước database chính:

~~~mermaid
flowchart TD
    A["Đọc hồ sơ user 42"] --> B["GET cache:user:42"]
    B --> C{"Có dữ liệu hợp lệ?"}
    C -->|Có| D["Trả dữ liệu cache"]
    C -->|Không| E["Đọc hệ thống nguồn"]
    E --> F["Ghi cache với TTL phù hợp"]
    F --> G["Trả kết quả"]
~~~

Đây là mô hình **cache-aside**. Nó giảm lần đọc hệ thống nguồn khi cache hit, nhưng mở ra nhiều câu hỏi: cache được cập nhật hay vô hiệu hóa lúc ghi thế nào, có thể trả dữ liệu cũ trong bao lâu, khi cache mất toàn bộ key thì hệ thống nguồn chịu tải ra sao, và làm thế nào chống hàng nghìn request cùng tái tạo một key nóng?

Không nên tự động coi một kho key–value là cache. Nhiều hệ key–value được dùng làm **kho dữ liệu chính** với chiến lược lưu bền riêng, trong khi cache là một **vai trò kiến trúc** có thể do nhiều công nghệ đảm nhiệm.

## 9. Mở rộng: một phép tra key có thể đi qua nhiều thành phần

Trong triển khai phân tán, một request đọc theo key thường bao gồm thêm các bước ngoài ý tưởng ánh xạ logic:

~~~text
Ứng dụng
   |
   | GET(key)
   v
Client / router
   |
   | chọn phân vùng hoặc nút theo cơ chế của sản phẩm
   v
Node phục vụ khóa
   |
   | đọc dữ liệu / xác minh bản sao nếu cần
   v
Kết quả hoặc lỗi
~~~

**Partitioning** chia tập khóa thành nhiều phần để nhiều nút cùng xử lý lưu lượng và dung lượng. **Replication** tạo bản sao phục vụ khả năng chịu lỗi, phục hồi hoặc đọc ở vị trí khác. Cơ chế áp dụng rất khác nhau: hàm hash, range partition, primary/replica, quorum, leaderless, cụm trong một vùng hay nhiều vùng.

Một thao tác “theo khóa” không mặc nhiên đạt độ trễ hằng số từ góc nhìn người dùng. Độ trễ còn chịu ảnh hưởng mạng, disk, tải, kích thước value, retry, định tuyến, khóa nóng, replication và failover.

### 9.1. Hot key và phân bố tải

Một khóa như `feature:global-settings` có thể được mọi request đọc liên tục. Nếu tất cả lần đọc dồn về cùng điểm phục vụ, nút hoặc phân vùng có thể quá tải dù tổng số lượng khóa rất lớn.

Biện pháp có thể gồm cache phía ứng dụng, bản sao đọc, thay đổi cách phân phối, gom/batch request hoặc phân tách dữ liệu; khả năng thực thi phụ thuộc hệ thống. Đối với bộ đếm tập trung cập nhật dày đặc, một số thiết kế dùng nhiều “shard counter” rồi cộng kết quả, nhưng phải chấp nhận chi phí đọc tổng và giải quyết tính đúng đắn.

### 9.2. Nhất quán và độ bền phải được định nghĩa

Đọc từ một replica sau ghi có thấy ngay value mới hay không? Khi một node báo ghi thành công rồi mất điện, dữ liệu có phục hồi được hay không? Khi mất kết nối giữa vùng, request được chấp nhận hay từ chối?

Đây là câu hỏi về **bảo đảm của sản phẩm, cấu hình và topology**, không có đáp án chung cho tất cả key–value database. Đừng đồng nhất “có replication” với “không bao giờ mất dữ liệu”, hoặc “có sharding” với “mọi truy vấn tự mở rộng”.

### 9.3. Không dùng quét toàn bộ khóa làm lối truy cập mặc định

Giả sử màn hình cần hiển thị “20 đơn hàng mới nhất của một khách hàng”, nhưng chỉ lưu `order:{orderId}`. Một giải pháp ngây thơ là duyệt mọi khóa `order:*`, đọc value từng đơn, lọc `customerId` rồi sắp xếp. Cách đó có thể tốn kém, chậm, khó phân trang và không được sản phẩm hỗ trợ hiệu quả.

Hướng thiết kế tốt hơn là **xác định access pattern trước**, sau đó chọn key/index/mô hình dữ liệu có đường truy cập phù hợp. Nếu cần truy vấn nhiều chiều, có thể một database hoặc mô hình khác phù hợp hơn so với key–value tối giản.

## 10. Ví dụ thiết kế: session, bộ đếm và giỏ hàng

### 10.1. Session theo mã ngẫu nhiên

**Yêu cầu:** client gửi một mã phiên khó đoán; server cần tìm nhanh thông tin phiên, áp dụng hết hạn và thu hồi được phiên.

~~~text
Key:   session:<opaque-random-session-id>
Value: { userId, issuedAt, sessionVersion, ... }
~~~

Luồng: xác thực request → đọc theo khóa phiên → kiểm tra trạng thái/hiệu lực → xử lý → khi logout thì xóa hoặc vô hiệu hóa.

Những quyết định cần có: giá trị không được chứa bí mật dư thừa, key có đủ entropy, quyền truy cập store, TTL và cơ chế thu hồi, xử lý trường hợp store không sẵn sàng. Đừng chỉ dựa vào TTL để đạt đầy đủ yêu cầu bảo mật.

### 10.2. Bộ đếm request theo cửa sổ

**Yêu cầu:** giới hạn request của từng tenant theo phút.

~~~text
Key:   request-count:tenant17:202611141530
Value: 18
~~~

Nếu database hỗ trợ phép tăng nguyên tử và TTL phù hợp, mỗi request có thể tăng một giá trị gắn với cửa sổ hiện tại. Tuy nhiên, để ra quyết định “cho phép hay từ chối” phải xét tính nguyên tử giữa phép tăng, ngưỡng giới hạn và cách tạo key mới. Nếu key bị reset hoặc mất khi failover, chính sách giới hạn sẽ thay đổi.

Đây là **minh họa một cách mô hình hóa fixed window**, không phải đầy đủ thuật toán rate limiting cho mọi yêu cầu. Sliding window, token bucket và các chiến lược khác có đặc tính sai số, tải và lưu trữ khác nhau.

### 10.3. Giỏ hàng của một người dùng

**Yêu cầu:** lấy toàn bộ giỏ chỉ bằng `userId`, sửa số lượng sản phẩm, có thể giữ trạng thái trong một khoảng thời gian.

~~~text
Key:   cart:42
Value: JSON của toàn bộ giỏ hàng
~~~

**Ưu điểm:** tra cứu đơn giản, một lần đọc có thể lấy toàn bộ giỏ.

**Đánh đổi:** một thay đổi nhỏ có thể phải ghi lại cả value; hai request đồng thời có thể ghi đè lẫn nhau; value lớn vượt giới hạn hoặc tăng chi phí; truy vấn “tìm giỏ chứa SKU X” không phải đường truy cập tự nhiên.

Khi workload thay đổi, có thể tách các item hoặc dùng một cấu trúc được sản phẩm hỗ trợ. Mỗi lựa chọn phải cân bằng số lần đọc, khả năng cập nhật độc lập, tính nhất quán và chi phí lưu trữ.

## 11. Khi nào mô hình key–value phù hợp?

| Nhu cầu | Đánh giá ban đầu | Câu hỏi cần kiểm chứng |
|---|---|---|
| Đọc cấu hình theo tên đã biết | Rất tự nhiên | Cách invalidation và đồng bộ phiên bản? |
| Lưu session theo token | Phù hợp về access pattern | TTL, persistence, failover, security? |
| Đếm lượt theo ID | Phù hợp nếu có phép tăng phù hợp | Atomicity, retry, idempotency, hot key? |
| Đọc một hồ sơ theo ID | Phù hợp | Value lớn bao nhiêu, cập nhật thường xuyên không? |
| Lấy giỏ hàng theo user ID | Có thể phù hợp | Xử lý cập nhật đồng thời và kích thước value ra sao? |
| Tìm người theo hàng chục thuộc tính | Không phải thế mạnh của key–value thuần | Sản phẩm có query/index hay cần hệ tìm kiếm? |
| Thống kê toàn bộ dữ liệu theo nhiều chiều | Cần đánh giá kỹ | Có hệ analytics/aggregation riêng không? |
| Cập nhật nhiều đối tượng với bất biến giao dịch | Phụ thuộc mạnh vào sản phẩm | Phạm vi transaction/isolation và hành vi conflict? |
| Duyệt quan hệ nhiều bước trong mạng xã hội | Không tự nhiên với key lookup đơn giản | Có nên dùng graph hay mô hình riêng không? |

Bảng chỉ định hướng theo kiểu truy cập. Việc một giải pháp cụ thể có đáp ứng mục tiêu tải, độ trễ, chi phí và đúng đắn hay không cần đọc tài liệu và đo trên hệ đang dùng.

### 11.1. So với những mô hình NoSQL khác

- **Document:** nội dung có cấu trúc là đối tượng dữ liệu quan trọng, và một số sản phẩm hỗ trợ truy vấn/index theo trường bên trong tài liệu. Truy cập theo ID vẫn phổ biến; điều khác biệt thường nằm ở khả năng hiểu và truy vấn value.
- **Wide-column/partitioned-row:** mô hình hóa theo partition key, clustering/order và access pattern; có thể lấy một nhóm hàng theo khóa phân vùng. Không được coi các quy tắc khóa của mọi sản phẩm là giống nhau.
- **Graph:** biểu diễn đỉnh, cạnh và quan hệ, hỗ trợ các thao tác duyệt kết nối; khác với việc chỉ lấy một value theo key.

Đây là các **nhóm mô hình học tập**. Sản phẩm có thể hỗ trợ nhiều mô hình hoặc cung cấp khả năng vượt ra ngoài phân loại thuần túy.

## 12. Bài tập tự áp dụng

### Bài tập 1 — Xây khóa từ yêu cầu

Ứng dụng có ba thao tác: (A) lấy hồ sơ theo user ID; (B) lấy danh sách 10 bài đăng mới nhất theo tác giả; (C) đếm số lần mở một bài đăng theo post ID.

**Câu hỏi:** thao tác nào ánh xạ trực tiếp tới một khóa? Thao tác nào có thể cần thêm mô hình truy cập?

**Gợi ý:** A dùng `user:{id}:profile`; C dùng `post:{id}:views` nếu sản phẩm có phép tăng an toàn. B cần một thứ tự theo tác giả và thời gian; chỉ lưu `post:{postId}` chưa đủ để phục vụ B hiệu quả.

### Bài tập 2 — Tìm lỗi trong chuỗi cập nhật

Hai request cùng chạy:

~~~text
count = GET("likes:post-1")
PUT("likes:post-1", count + 1)
~~~

**Câu hỏi:** vì sao tổng like có thể sai? Có những hướng khắc phục nào?

**Gợi ý:** cả hai có thể đọc cùng số cũ và ghi ra cùng số mới. Dùng atomic increment, conditional write/CAS hoặc cơ chế tuần tự/giao dịch phù hợp; xét thêm retry khi timeout.

### Bài tập 3 — Thiết kế expiry

Một key giỏ hàng được tạo với TTL 24 giờ. Mỗi lần người dùng thêm sản phẩm, ứng dụng muốn thời hạn lại bắt đầu từ thời điểm sửa.

**Câu hỏi:** khi `PUT` được gọi, có chắc TTL tự được gia hạn không?

**Gợi ý:** không thể suy ra từ mô hình key–value. Phải kiểm tra việc ghi đè giữ nguyên, xóa hay làm mới TTL trong **sản phẩm và lệnh cụ thể**, sau đó chọn API phù hợp.

### Bài tập 4 — Chuyển sản phẩm

Giả sử hệ thống đang dùng Redis để lưu session và muốn chuyển sang một key–value store khác.

**Câu hỏi:** có thể giữ nguyên phần nào của thiết kế và cần kiểm tra lại điều gì?

**Gợi ý:** có thể giữ access pattern “lookup theo session ID”, quy ước định danh, mô hình session và yêu cầu TTL. Cần xem lại ngôn ngữ lệnh, cách đặt TTL, phạm vi atomicity, bảo đảm đọc/ghi, persistence, replication, hạn mức, mã hóa và hành vi failover. API `GET`/`SET` của Redis không phải giao diện chung của mọi sản phẩm.

## 13. Ghi nhớ khi thiết kế với khóa–giá trị

Mô hình key–value đơn giản ở chỗ **khóa đóng vai trò địa chỉ logic, còn value là nội dung gắn với địa chỉ ấy**. Sự đơn giản này làm nó hiệu quả về mặt thiết kế cho những đường truy cập biết trước định danh: session, cấu hình, trạng thái theo ID, bộ đếm, giỏ hàng và nhiều loại dữ liệu tạm thời.

Nhưng chất lượng hệ thống phụ thuộc những quyết định vượt ra ngoài phép `GET(key)`: đặt khóa để phân bố tải tốt; chọn giá trị đủ nhỏ, có cấu trúc rõ ràng; quản lý TTL; kiểm soát ghi đồng thời; phân biệt mất key với lỗi; và xác định tính nhất quán, độ bền, giới hạn theo database cụ thể.

Khi phân tích một yêu cầu, hãy tự hỏi theo thứ tự: **Ứng dụng biết khóa gì? Cần thao tác nào trên giá trị? Có ghi đồng thời không? Key tồn tại trong bao lâu? Cần đọc theo tiêu chí khác không? Sản phẩm đang dùng bảo đảm điều gì?** Trả lời rõ những câu hỏi này mới quyết định được mô hình khóa–giá trị có phù hợp hay cần kết hợp với cấu trúc lưu trữ khác.

