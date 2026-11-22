# Điều kiện truy vấn thuận lợi và hạn chế của từng mô hình dữ liệu NoSQL

## 1. Bắt đầu từ câu truy vấn thay vì tên công nghệ

Giả sử một hệ thống thương mại điện tử cần thực hiện những thao tác sau:

1. Đọc giỏ hàng của người dùng có mã `u42`.
2. Hiển thị toàn bộ thông tin của sản phẩm `p100`, bao gồm các biến thể màu sắc và kích cỡ.
3. Liệt kê 50 sự kiện gần nhất của thiết bị `d7`.
4. Tìm những tài khoản có quan hệ gián tiếp với một tài khoản nghi vấn qua thiết bị và thẻ thanh toán.
5. Tìm sản phẩm có tên gần giống câu người dùng vừa gõ.
6. Tổng hợp nhiệt độ trung bình của cảm biến theo từng khoảng 5 phút.

Mọi thao tác đều là “truy vấn dữ liệu”, nhưng cách tìm câu trả lời khác nhau. Có truy vấn biết chính xác khóa; có truy vấn lọc theo thuộc tính; có truy vấn đi theo trình tự thời gian; có truy vấn duyệt nhiều tầng quan hệ; lại có truy vấn cần phân tích từ ngữ.

Đó là lý do **mô hình dữ liệu không chỉ quyết định dữ liệu được biểu diễn ra sao mà còn quyết định kiểu truy vấn nào được xử lý thuận lợi**. Khi dữ liệu được lưu theo một cấu trúc nhất định, một số thao tác có thể xác định nhanh phần dữ liệu cần đọc; những thao tác khác buộc phải quét rộng, gọi nhiều lần, kết hợp kết quả ở ứng dụng hoặc duy trì một cấu trúc phụ.

Trong NoSQL, các mô hình thường gặp gồm:

- **Key–value:** tra cứu một giá trị từ một khóa.
- **Document:** truy vấn các tài liệu có cấu trúc lồng nhau, thường gần với JSON.
- **Wide-column/column-family:** truy vấn theo khóa phân vùng và thứ tự các cột/bản ghi bên trong phân vùng.
- **Graph:** truy vấn những đối tượng và các cạnh quan hệ nối chúng.
- **Time-series:** truy vấn chuỗi đo đạc/sự kiện theo thời gian.
- **Search-oriented:** tra cứu và xếp hạng văn bản bằng chỉ mục tìm kiếm.

Time-series và search-oriented là các **mô hình hoặc hệ chuyên dụng theo loại truy vấn**, không nhất thiết luôn là một nhóm NoSQL tách biệt: có sản phẩm time-series hỗ trợ SQL, và có hệ thống tích hợp chức năng tìm kiếm vào document database. Những tên gọi này chỉ giúp hình dung đường truy cập dữ liệu chủ đạo.

Bài học này tập trung vào **điều kiện để truy vấn chạy thuận lợi, truy vấn nào dễ trở nên tốn kém, và cách nhận biết giới hạn của từng mô hình**.

## 2. Truy vấn “thuận lợi” nghĩa là gì?

Một truy vấn thuận lợi khi mô hình lưu trữ và chỉ mục cho phép hệ thống **định vị một lượng dữ liệu nhỏ, thực hiện ít bước và trả kết quả đúng theo yêu cầu**.

Không nên hiểu “thuận lợi” là “luôn nhanh” hoặc “luôn rẻ”. Trên thực tế còn có kích thước dữ liệu, cấu hình máy, mạng, số người dùng đồng thời, mức nhất quán và khối lượng cập nhật.

### 2.1. Sáu câu hỏi để phân tích một truy vấn

Trước khi chọn mô hình, hãy đặt các câu hỏi:

| Câu hỏi | Điều cần quan sát | Ví dụ |
|---|---|---|
| Biết khóa định danh không? | Có thể xác định trực tiếp một bản ghi hoặc phân vùng? | `cart:user:42` |
| Lọc bằng gì? | Trường cố định, thuộc tính linh hoạt, khoảng giá trị, từ khóa? | `category = "laptop"`, `price < 20_000_000` |
| Cần sắp xếp/phân trang không? | Có thể lấy 20 bản ghi đầu mà không quét toàn bộ? | Sự kiện mới nhất trước |
| Cần kết hợp thực thể không? | Một thực thể, nhiều thực thể, nhiều bước quan hệ? | Tài khoản → thiết bị → tài khoản |
| Khối lượng thực tế ra sao? | Một bản ghi nhỏ, hàng triệu sự kiện, dữ liệu phân tán? | 10 triệu log/ngày |
| Cần bảo đảm gì khi đọc/ghi? | Có chấp nhận bản sao cập nhật chậm? Có cần giao dịch? | Đơn hàng phải cập nhật đúng |

**Điều kiện lọc** là phần quan trọng. “Lấy sản phẩm theo ID” khác hẳn “tìm mọi sản phẩm được sửa tuần trước, có giá dưới X và thuộc thương hiệu Y”, dù cùng trả về sản phẩm.

### 2.2. Độ chọn lọc, chỉ mục và phạm vi quét

Giả sử collection có 10 triệu sản phẩm:

- Truy vấn theo ID duy nhất có thể hướng thẳng đến một tài liệu.
- Truy vấn theo danh mục `"electronics"` có thể trả hàng trăm nghìn tài liệu.
- Truy vấn theo màu `"black"` có thể phải đọc một lượng dữ liệu lớn nếu không có chỉ mục phù hợp.
- Truy vấn tìm sản phẩm “giống” từ khóa nhập tự do cần cách tổ chức chỉ mục khác với so khớp chính xác.

**Selectivity (độ chọn lọc)** thể hiện điều kiện lọc thu hẹp tập dữ liệu nhiều đến đâu. Chỉ mục có ích khi giúp giảm phần cần duyệt; nhưng nếu truy vấn trả về phần lớn dữ liệu, chi phí đọc nhiều bản ghi vẫn tồn tại. Chỉ mục còn có giá của nó: thêm dung lượng, tăng công cập nhật khi ghi và cần được duy trì.

### 2.3. Một truy vấn có thể biến thành nhiều thao tác

Trong ứng dụng đặt phòng, API “hiển thị phòng và tiện nghi” có thể:

- Đọc một tài liệu chứa phòng, ảnh và tiện nghi;
- Đọc phòng rồi gọi thêm bảng/collection tiện nghi;
- Duyệt nhiều mối quan hệ để tìm các phòng tương đồng;
- Đồng thời truy vấn giá hoặc lịch trống ở một nguồn khác.

Độ trễ API phụ thuộc **tổng đường đi của dữ liệu**, không chỉ số mili giây của một lệnh DB. Một mô hình giúp giảm số lượt truy cập cho truy vấn phổ biến có thể đổi lại việc cập nhật phức tạp hơn.

## 3. Key–value: mạnh nhất khi biết khóa

### 3.1. Cách tổ chức dữ liệu

Mô hình key–value ánh xạ một khóa duy nhất đến một giá trị. Giá trị có thể là chuỗi, cấu trúc danh sách, hash, JSON hoặc đối tượng nhị phân tùy sản phẩm.

```text
cart:user:42      -> {"items":[{"sku":"A1","qty":2}]}
session:token:abc  -> {"userId":42,"expiresAt":"..."}
config:feature:x   -> "enabled"
```

Một số hệ key–value như Redis còn cung cấp kiểu cấu trúc dữ liệu riêng, thao tác nguyên tử trên những kiểu đó, TTL và các lệnh chuyên dụng. Không nên mặc định một hệ key–value bất kỳ đều có đầy đủ các khả năng này.

### 3.2. Khi nào truy vấn thuận lợi?

**Điều kiện chủ chốt: ứng dụng biết khóa chính xác hoặc có thể suy ra khóa từ dữ liệu đầu vào.**

Ví dụ với giao diện lệnh minh họa:

```text
GET cart:user:42
SET cart:user:42 {"items":[{"sku":"A1","qty":3}]}
DEL cart:user:42
```

Những kiểu thao tác phù hợp:

- Đọc hoặc ghi một đối tượng theo ID.
- Lưu phiên đăng nhập theo session ID.
- Lưu giỏ hàng theo user ID.
- Lưu kết quả tính sẵn cho một truy vấn có tham số đã biết.
- Bộ đếm, hàng đợi hoặc tập hợp nếu sản phẩm có cấu trúc và lệnh thích hợp.

Nếu truy vấn luôn có khóa, hệ thống có thể định tuyến trực tiếp đến shard/nút chịu trách nhiệm, tránh việc phải xét mọi bản ghi. Mức độ nhanh còn phụ thuộc giao thức, kích thước giá trị và tải tại khóa đó.

### 3.3. Hạn chế: truy vấn ngược theo giá trị hoặc nhiều thuộc tính

Bây giờ đặt câu hỏi: “Tìm **tất cả** giỏ hàng chứa sản phẩm `A1`”.

Nếu key–value chỉ có khóa `cart:user:{id}` và giá trị là một chuỗi JSON, hệ thống có thể không có cách tìm trực tiếp những khóa thỏa điều kiện. Cách đơn giản nhưng kém hiệu quả là đọc lần lượt rất nhiều giỏ hàng để kiểm tra.

Tương tự, những yêu cầu sau không tự nhiên với key–value thuần túy:

- Liệt kê tất cả người dùng đăng nhập trong một khoảng thời gian;
- Lọc các giỏ hàng theo cả tổng tiền và số loại mặt hàng;
- Kết hợp dữ liệu giỏ hàng với hồ sơ người dùng và giá sản phẩm;
- Tìm kiếm toàn văn bên trong giá trị tùy ý.

Có thể xây **chỉ mục phụ do ứng dụng duy trì**, dùng cấu trúc set/sorted set nếu hệ hỗ trợ, hoặc đưa truy vấn sang database khác. Đổi lại, mỗi cập nhật phải duy trì nhất quán nhiều cấu trúc.

### 3.4. Những yếu tố cần thận trọng

| Yếu tố | Vì sao ảnh hưởng truy vấn? |
|---|---|
| Hot key | Một khóa có lượng truy cập quá cao có thể gây tắc nghẽn ở một nút |
| Giá trị lớn | Đọc một key vẫn tốn băng thông và giải mã nếu giá trị hàng MB |
| TTL và eviction | Dữ liệu có thể hết hạn hoặc bị loại khỏi cache theo chính sách |
| Phân mảnh khóa | Các khóa có quan hệ nghiệp vụ có thể nằm trên nhiều nút khác nhau |
| Thao tác nguyên tử | Bảo đảm có thể chỉ áp dụng trong phạm vi một khóa hoặc theo tính năng của sản phẩm |

**Quy tắc nhận diện:** nếu câu hỏi mở đầu bằng “Cho tôi giá trị của khóa này”, key–value là ứng viên đáng xem xét. Nếu câu hỏi mở đầu bằng “Tìm tất cả đối tượng có những đặc điểm này”, cần xem khả năng index/query của sản phẩm hoặc một mô hình khác.

## 4. Document: thuận lợi khi truy vấn tập trung vào một đối tượng có thuộc tính lồng nhau

### 4.1. Cấu trúc tài liệu

Document database lưu các thực thể dưới dạng tài liệu, thường có thuộc tính lồng nhau và mảng. Mỗi tài liệu có thể có các trường khác nhau.

```json
{
  "_id": "p100",
  "name": "Laptop M",
  "category": "laptop",
  "brand": "Example",
  "price": 18000000,
  "specifications": {
    "ramGB": 16,
    "storageGB": 512
  },
  "variants": [
    {"sku": "p100-gray", "color": "gray", "stock": 5},
    {"sku": "p100-black", "color": "black", "stock": 8}
  ],
  "tags": ["office", "portable"]
}
```

Nếu giao diện sản phẩm thường cần tên, giá, cấu hình và biến thể trong cùng một lần đọc, việc đặt chúng trong một tài liệu có thể giúp truy vấn đơn giản.

### 4.2. Khi nào truy vấn thuận lợi?

Các điều kiện thường hỗ trợ tốt:

- Đọc một tài liệu theo ID hoặc một khóa được đánh chỉ mục.
- Lọc theo thuộc tính tài liệu, kể cả thuộc tính lồng nhau, với chỉ mục thích hợp.
- Hiển thị một nhóm dữ liệu thường được đọc cùng nhau.
- Truy xuất một mảng nhỏ, có giới hạn và gắn vòng đời với thực thể chính.
- Thay đổi cấu trúc thuộc tính theo loại đối tượng mà không cần một bảng có rất nhiều cột rỗng.

Ví dụ cú pháp theo MongoDB, giả sử collection đã có dữ liệu và các chỉ mục cần thiết:

```javascript
// Lấy một sản phẩm theo ID
db.products.findOne({ _id: "p100" });

// Lọc và sắp xếp các sản phẩm trong một thương hiệu
db.products.find(
  { category: "laptop", brand: "Example" },
  { name: 1, price: 1 }
).sort({ price: 1 }).limit(20);

// Chỉ mục phù hợp với bộ lọc bằng nhau và thứ tự sắp xếp trên
db.products.createIndex({ category: 1, brand: 1, price: 1 });
```

Trong truy vấn thứ hai, bộ lọc bằng nhau theo `category` và `brand` kết hợp thứ tự sắp xếp theo `price` có thể tận dụng chỉ mục ghép phù hợp. Tuy nhiên, việc dùng chỉ mục nào vẫn do bộ tối ưu và hình dạng truy vấn quyết định; cần quan sát kế hoạch thực thi trên dữ liệu thật.

Với tài liệu đa dạng:

```javascript
db.products.find({
  category: "laptop",
  "specifications.ramGB": { $gte: 16 }
});
```

Truy vấn trường lồng nhau là điều tự nhiên với mô hình document; điều đó **không đảm bảo** mọi truy vấn trường lồng nhau đều nhanh mà không cần index.

### 4.3. Điểm mạnh của việc nhúng dữ liệu

Giả sử một sản phẩm có 4 biến thể và trang chi tiết luôn hiển thị cả 4. Nhúng mảng `variants` có thể tránh nhiều lần gọi tới collection khác. Các thông tin đó được đọc cùng nhau, có số lượng nhỏ và cùng vòng đời cập nhật.

Nhưng nếu thay `variants` bằng một mảng chứa **hàng triệu lượt xem**, tài liệu có thể lớn và cập nhật liên tục. Khi đó, việc nhúng là lựa chọn tệ: các sự kiện có vòng đời và quy mô khác với sản phẩm.

Nguyên tắc thực dụng:

- **Nhúng (embed)** khi dữ liệu phụ nhỏ, thường được đọc cùng nhau và có vòng đời gần với dữ liệu chính.
- **Tham chiếu (reference)** khi dữ liệu có số lượng lớn, tăng không giới hạn, chia sẻ cho nhiều đối tượng hoặc cập nhật độc lập.
- **Tạo read model riêng** khi cần một cách truy cập khác hoàn toàn, với kế hoạch đồng bộ rõ ràng.

### 4.4. Hạn chế: liên kết nhiều thực thể và dữ liệu sao chép

Ví dụ hệ thống quản lý đơn hàng:

```text
Customer <---- Order ----> Product
                      \--> Shipment
                      \--> Payment
```

Nếu mỗi đơn hàng sao chép tên, email và địa chỉ hiện tại của khách hàng, một thay đổi hồ sơ có thể đòi hỏi cập nhật nhiều tài liệu. Nhưng cũng có trường hợp **cố ý chụp ảnh dữ liệu tại thời điểm đặt hàng**: đơn hàng cần giữ giá mua và địa chỉ giao hàng lúc chốt, không phụ thuộc thông tin sau này.

Những truy vấn sau có thể phức tạp tùy sản phẩm và cách thiết kế:

- JOIN tùy ý qua nhiều tập tài liệu lớn;
- Cập nhật nguyên tử nhiều tài liệu có quan hệ với nhau;
- Tổng hợp nhiều chiều trên phần lớn collection;
- Duyệt quan hệ nhiều bước khi liên kết thay đổi thường xuyên;
- Sắp xếp/lọc trên nhiều trường với chỉ mục không phù hợp;
- Truy vấn các mảng lồng nhau quá lớn hoặc tài liệu phình to.

Một số document database có pipeline aggregation, lookup và giao dịch nhiều tài liệu. Vì vậy, hạn chế nêu trên là **chi phí và độ phù hợp**, không phải khẳng định mọi thao tác đó đều không thể thực hiện.

**Quy tắc nhận diện:** document thuận lợi khi câu trả lời thường xoay quanh **một thực thể hoặc aggregate**, có nhiều thuộc tính lồng nhau và có thể xây chỉ mục cho các bộ lọc quan trọng. Nếu phải ghép nhiều thực thể độc lập trong hầu hết truy vấn, hãy cân nhắc mô hình quan hệ hoặc cấu trúc riêng cho nhu cầu đọc đó.

## 5. Wide-column / column-family: mạnh khi biết partition key và trật tự truy xuất

### 5.1. Cách tổ chức theo truy vấn

Một hệ wide-column phân tán như Apache Cassandra thường tổ chức truy xuất dựa trên:

- **Partition key:** xác định nhóm dữ liệu được phân phối đến các nút.
- **Clustering columns:** xác định thứ tự sắp xếp các bản ghi bên trong partition.
- **Các cột dữ liệu:** giá trị lưu kèm từng hàng.

Ví dụ lưu sự kiện theo người dùng và ngày, dùng CQL minh họa:

```sql
CREATE TABLE user_events_by_day (
    user_id text,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    details text,
    PRIMARY KEY ((user_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Khóa phân vùng là cặp `(user_id, event_day)`. Trong mỗi partition, hệ thống có thể truy xuất các bản ghi theo thứ tự clustering, bắt đầu từ sự kiện gần đây nhất theo `occurred_at`.

### 5.2. Khi nào truy vấn thuận lợi?

Truy vấn điển hình:

```sql
SELECT occurred_at, event_id, event_type
FROM user_events_by_day
WHERE user_id = 'u42'
  AND event_day = '2026-11-14'
LIMIT 50;
```

Ứng dụng biết đúng partition và chỉ lấy một đoạn đầu của danh sách sắp xếp. Đây là tình huống rất hợp với thiết kế bảng trên.

Các mẫu truy vấn thường thuận lợi:

- Tìm theo partition key đầy đủ.
- Đọc các bản ghi theo thứ tự clustering đã thiết kế.
- Lấy “N sự kiện mới nhất” cho một đối tượng trong một khoảng đã chia partition hợp lý.
- Ghi nhiều bản ghi độc lập trên nhiều partition mà không cần JOIN.
- Truy vấn có mẫu truy cập tương đối cố định và đã biết trước.

### 5.3. Hạn chế: câu hỏi không khớp partition key

Giả sử bộ phận phân tích hỏi:

> “Tìm toàn bộ sự kiện `purchase` trong ngày hôm nay, bất kể người dùng là ai.”

Bảng `user_events_by_day` được chia theo `user_id` cùng ngày. Không biết `user_id`, truy vấn không xác định được một partition cụ thể. Một truy vấn quét nhiều partition sẽ khác hoàn toàn với truy vấn chọn đúng một partition.

Trong Cassandra, không nên coi `ALLOW FILTERING` là cách sửa phổ quát: nó có thể buộc phải đọc nhiều dữ liệu và hiệu năng tăng theo kích thước tập dữ liệu. Chức năng thứ cấp như secondary indexes, materialized views hoặc search indexes thay đổi theo phiên bản, cấu hình và sản phẩm; cần đánh giá riêng.

Một cách phổ biến là **thiết kế thêm bảng theo câu hỏi cần trả lời**:

```sql
CREATE TABLE purchases_by_day (
    event_day date,
    bucket int,
    occurred_at timestamp,
    event_id uuid,
    user_id text,
    PRIMARY KEY ((event_day, bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Để truy vấn toàn bộ sự kiện mua hàng của ngày, ứng dụng đọc nhiều `bucket` rồi gộp kết quả. Việc chia bucket giúp tránh dồn mọi giao dịch của một ngày vào một partition quá lớn, nhưng cũng khiến truy vấn đọc cần fan-out qua nhiều partition. Hệ thống phải đảm bảo bảng phụ này chỉ nhận các sự kiện mua hàng và được cập nhật đồng bộ với nguồn phát sự kiện phù hợp.

**Một truy vấn mới có thể yêu cầu một bảng mới hoặc một mô hình truy cập mới**. Đây là đánh đổi quan trọng của wide-column theo cách thiết kế query-first.

### 5.4. Partition quá lớn hoặc quá nóng

Partition key không phù hợp gây hai vấn đề:

1. **Partition quá lớn:** người dùng có hàng tỷ sự kiện trong một partition có thể làm đọc, compaction, repair và quản lý dữ liệu trở nên tốn kém.
2. **Hot partition:** nhiều lượt ghi/đọc cùng tập trung vào một partition, khiến một số nút quá tải còn những nút khác nhàn rỗi.

Phân vùng theo ngày/giờ hoặc chia bucket có thể giúp giới hạn kích thước và phân phối tải, nhưng đồng thời tăng số partition phải truy vấn. Chọn khóa cần kết hợp **phân bố lưu lượng** và **đường truy vấn chính**.

### 5.5. Những hạn chế cần nhận biết

| Kiểu truy vấn | Đánh giá với bảng wide-column thiết kế ở trên |
|---|---|
| Sự kiện mới nhất của `u42` trong ngày | Thuận lợi |
| Sự kiện của `u42` trong 30 ngày | Có thể đọc nhiều partition ngày và gộp |
| Tìm toàn bộ sự kiện có `event_type = "purchase"` | Không được tối ưu bởi khóa hiện tại |
| Sắp xếp toàn bộ sự kiện của mọi người dùng theo thời gian | Không thuận lợi nếu không có read model khác |
| JOIN sự kiện với profile người dùng | Không phải điểm mạnh của mô hình |
| Truy vấn phân tích nhiều chiều ad hoc | Thường cần hệ phân tích/chỉ mục chuyên dụng |

**Phân biệt thuật ngữ:** wide-column/column-family như Cassandra không đồng nghĩa với **columnar analytics** như những công cụ OLAP lưu dữ liệu theo cột để quét và tổng hợp khối lượng lớn. Tên nghe gần nhau nhưng tối ưu truy vấn khác nhau.

**Quy tắc nhận diện:** wide-column phù hợp khi hệ thống ghi/đọc quy mô lớn, câu truy vấn có thể mô tả bằng **partition key + thứ tự clustering**, và chấp nhận thiết kế bảng theo nhu cầu truy vấn đã biết.

## 6. Graph: thuận lợi khi truy vấn là đi theo các mối quan hệ

### 6.1. Dữ liệu nằm ở đỉnh và cạnh

Graph database biểu diễn đối tượng thành **node/vertex**, liên kết thành **edge/relationship**, có thể gắn thuộc tính trên cả hai.

```text
(User u1) --USES--> (Device d5) <--USES-- (User u2)
(User u2) --PAID_WITH--> (Card c7) <--PAID_WITH-- (User u3)
```

Đối với hệ chống gian lận, những kết nối có thể quan trọng hơn nội dung một tài liệu riêng lẻ. Truy vấn thường bắt đầu từ một tài khoản rồi đi qua các cạnh để tìm đối tượng liên quan.

### 6.2. Khi nào truy vấn thuận lợi?

Các câu hỏi tiêu biểu:

- Những tài khoản nào dùng chung thiết bị với tài khoản A?
- Có đường đi nào từ người dùng A đến người dùng B trong tối đa 4 bước?
- Những sản phẩm nào được người dùng có cùng sở thích quan tâm?
- Những thành phần nào của hệ thống phụ thuộc gián tiếp vào một dịch vụ gặp sự cố?
- Những nhóm node nào tạo thành cộng đồng liên kết dày đặc?

Ví dụ theo cú pháp Cypher minh họa của Neo4j:

```cypher
MATCH (a:Account {id: 'A'})-[:USES_DEVICE]->(d:Device)
      <-[:USES_DEVICE]-(other:Account)
RETURN DISTINCT other.id;
```

Truy vấn thể hiện trực tiếp hai quan hệ liên tiếp. Nếu hệ có chỉ mục để tìm `Account.id` và có cấu trúc lưu các cạnh/đỉnh kề hiệu quả, việc duyệt có thể phù hợp với đồ thị có nhiều cấp liên kết.

### 6.3. Hạn chế: lan rộng quá mức và node bậc cao

Graph không đồng nghĩa với mọi truy vấn quan hệ đều rẻ.

- **Supernode:** một node kết nối với hàng triệu node khác (chẳng hạn một địa chỉ IP phổ biến). Duyệt qua node này có thể sinh lượng kết quả rất lớn.
- **Truy vấn độ sâu lớn:** duyệt thêm một bước có thể nhân mạnh số đường đi phải xét.
- **Không có điểm bắt đầu chọn lọc:** tìm “mọi mẫu quan hệ” trên toàn đồ thị có thể phải xét lượng lớn node/cạnh.
- **Truy vấn tổng hợp bảng:** tính tổng doanh thu theo tháng của mọi đơn hàng có thể phù hợp hơn với SQL/OLAP.
- **Cập nhật ở quy mô lớn:** mô hình graph cần kế hoạch phân vùng, chỉ mục và kiểm soát tranh chấp khi ghi.

Ví dụ, yêu cầu “tìm đường đi dài không giới hạn giữa mọi cặp tài khoản” là một bài toán khác hẳn “từ tài khoản A tìm những tài khoản chung thiết bị trong 2 bước”. Cả hai dùng graph nhưng độ khó và chi phí hoàn toàn khác nhau.

### 6.4. Graph không phải lựa chọn mặc định cho mọi quan hệ

Nếu chỉ cần tra cứu các đơn hàng của một khách hàng:

```sql
SELECT *
FROM orders
WHERE customer_id = 42;
```

Một chỉ mục `orders(customer_id)` trong database quan hệ có thể giải quyết rất tốt. Không nhất thiết dựng graph database chỉ vì tồn tại quan hệ “khách hàng có đơn hàng”.

**Quy tắc nhận diện:** graph đáng xem xét khi **duyệt các quan hệ nhiều bước, quan hệ thay đổi thường xuyên hoặc cấu trúc kết nối là kết quả chính của truy vấn**. Nếu phần lớn câu hỏi là tìm bản ghi đơn lẻ, aggregate hoặc tổng hợp theo cột, mô hình khác có thể đơn giản hơn.

## 7. Time-series: thuận lợi khi luôn truy vấn theo đối tượng và thời gian

### 7.1. Điểm chung của dữ liệu chuỗi thời gian

Một bản ghi đo có thể gồm:

```json
{
  "device_id": "sensor-7",
  "timestamp": "2026-11-14T08:00:00Z",
  "temperature": 24.6,
  "humidity": 71.2,
  "site": "warehouse-2"
}
```

Dữ liệu thường được **ghi nối tiếp theo thời gian** và truy vấn bằng:

- Thiết bị/nguồn phát nào?
- Trong khoảng thời gian nào?
- Cần giá trị từng điểm hay trung bình/tổng/max/min theo khoảng?
- Dữ liệu cũ phải giữ bao lâu?
- Có cần lấy mẫu xuống (downsampling) cho biểu đồ dài hạn không?

Time-series database hoặc một hệ có khả năng xử lý chuỗi thời gian được xây dựng quanh các mẫu truy vấn này.

### 7.2. Khi nào truy vấn thuận lợi?

- “Biểu đồ nhiệt độ của cảm biến S trong 24 giờ gần nhất.”
- “Trung bình CPU 5 phút một lần trong 7 ngày.”
- “Đếm số lỗi theo phút trong giờ cao điểm.”
- “Xóa hoặc lưu trữ dữ liệu đo quá 90 ngày.”
- “Truy vấn dữ liệu gần nhất của mỗi thiết bị.”

Một truy vấn khái niệm:

```text
SELECT average(temperature) GROUP BY 5-minute window
FROM measurements
WHERE device_id = 'sensor-7'
  AND timestamp BETWEEN start_time AND end_time
ORDER BY time ASC
```

Đây là **giả mã mô tả truy vấn**, không phải cú pháp có thể chạy nguyên xi ở mọi time-series database. Mỗi hệ cung cấp ngôn ngữ và hàm gom nhóm theo thời gian riêng.

Để xử lý thuận lợi, hệ thống thường dựa trên việc tổ chức dữ liệu theo **thời gian và nhãn/khóa series**, có thể kết hợp nén, lưu trữ theo vùng thời gian, retention và cấu trúc tổng hợp.

### 7.3. Hạn chế: số lượng chuỗi quá lớn, truy vấn ngoài thời gian

Trong một số hệ time-series, tập nhãn xác định từng series. Nếu dùng những nhãn có số lượng giá trị độc nhất cực lớn, như `request_id` thay đổi ở mọi bản ghi, **cardinality** của series có thể tăng đột biến, gây áp lực lên chỉ mục và bộ nhớ.

Các giới hạn khác:

- Cần JOIN phức tạp với hồ sơ khách hàng hoặc các giao dịch có quan hệ chặt.
- Truy vấn mọi cặp sự kiện có quan hệ ngữ nghĩa mà không có cấu trúc quan hệ sẵn.
- Tìm kiếm toàn văn nội dung log tự do nếu công cụ không có chỉ mục văn bản.
- Cập nhật hoặc xóa từng sự kiện đã lưu với tần suất lớn ở hệ tối ưu cho append.
- Truy vấn lịch sử kéo dài nhiều năm ở độ phân giải giây mà không có chính sách retention/downsampling.

**Quy tắc nhận diện:** time-series thuận lợi khi câu truy vấn gần như luôn chứa **khoảng thời gian** và thường thêm **nguồn phát hoặc nhóm nhãn**, kèm các phép tổng hợp theo cửa sổ thời gian.

## 8. Search-oriented: thuận lợi khi truy vấn là ngôn ngữ và độ liên quan

### 8.1. Tìm từ khác với so khớp trường

Khi người dùng tìm `"dien thoai chup dem tot"`, hệ thống có thể cần phân tích từ, không dấu, chính tả, từ đồng nghĩa, xếp hạng tài liệu và lọc theo danh mục. Truy vấn kiểu này khác với `WHERE sku = 'A100'`.

Search engine như Elasticsearch hoặc OpenSearch thường dựa vào **inverted index**: ánh xạ từ/term đã phân tích đến những tài liệu chứa nó, kết hợp thông tin giúp tính điểm liên quan.

```text
"laptop"  -> [doc1, doc4, doc8, ...]
"mỏng"    -> [doc1, doc5, ...]
"văn phòng" -> [doc2, doc4, ...]
```

Ví dụ cấu trúc truy vấn JSON theo Elasticsearch:

```json
{
  "query": {
    "bool": {
      "must": [
        {"match": {"title": "laptop mỏng văn phòng"}}
      ],
      "filter": [
        {"term": {"category.keyword": "laptop"}}
      ]
    }
  },
  "size": 20
}
```

Ví dụ giả định trường `category.keyword` đã được khai báo trong mapping. `match` sử dụng cơ chế phân tích văn bản và tính điểm liên quan, còn `term` lọc theo giá trị chính xác của trường phù hợp.

### 8.2. Khi nào truy vấn thuận lợi?

- Tìm từ khóa trong tiêu đề, mô tả hoặc nhiều trường văn bản.
- Hỗ trợ gõ gần đúng, autocomplete hoặc từ đồng nghĩa khi được cấu hình.
- Xếp hạng kết quả theo độ liên quan.
- Kết hợp tìm kiếm từ khóa với các điều kiện lọc.
- Tổng hợp theo facet cho trải nghiệm tìm kiếm, nếu engine hỗ trợ.

### 8.3. Hạn chế: dữ liệu mới nhất và giao dịch

Nhiều hệ search xây dựng chỉ mục riêng từ nguồn dữ liệu. Một thay đổi trong database giao dịch có thể **chưa hiển thị ngay** trong kết quả tìm kiếm nếu hệ đồng bộ bất đồng bộ hoặc cơ chế làm mới chỉ mục có độ trễ.

Các hạn chế hay gặp:

- Giao dịch cập nhật nhất quán nhiều thực thể không phải thế mạnh chính.
- Dùng điểm liên quan để xếp hạng không thay thế truy vấn bảo đảm tính đúng tuyệt đối.
- Độ trễ cập nhật chỉ mục, mapping và phân tích từ cần được quản lý.
- Tìm kiếm bằng từ khóa không phải lựa chọn rẻ nhất cho đọc bản ghi theo ID đơn giản.
- Truy vấn join/ad hoc phân tích quan hệ nhiều bước thường không phù hợp.
- Truy vấn vector/ngữ nghĩa có thể có cấu trúc chỉ mục và đánh đổi độ chính xác–hiệu năng riêng, cần đánh giá theo sản phẩm.

**Quy tắc nhận diện:** nếu người dùng muốn “tìm nội dung gần đúng hoặc liên quan nhất”, hãy nghĩ đến search-oriented. Nếu muốn “xác nhận tồn kho để chốt đơn”, hãy đọc từ nguồn có ràng buộc giao dịch phù hợp thay vì xem chỉ mục tìm kiếm như nguồn sự thật duy nhất.

## 9. Mô hình quan hệ như một điểm đối chiếu cần thiết

Dù trọng tâm là NoSQL, các hạn chế chỉ có ý nghĩa khi đối chiếu với cách giải quyết thay thế. Cơ sở dữ liệu quan hệ tổ chức dữ liệu theo bảng, khóa chính, khóa ngoại, chỉ mục, phép JOIN và giao dịch.

Nó đặc biệt phù hợp khi:

- Phải duy trì ràng buộc dữ liệu chặt chẽ trên nhiều thực thể.
- Truy vấn kết hợp nhiều bảng theo các quan hệ rõ ràng.
- Cần nhiều cách lọc và tổng hợp mà không thể biết trước hết mọi mẫu truy vấn.
- Giao dịch cần cập nhật đồng bộ nhiều bảng.
- Nhu cầu dữ liệu còn có thể đáp ứng hiệu quả với chỉ mục, phân vùng, cache và mở rộng theo khả năng của hệ.

Ví dụ:

```sql
SELECT c.id, c.name, COUNT(o.id) AS order_count
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE o.created_at >= TIMESTAMP '2026-11-01 00:00:00'
GROUP BY c.id, c.name
ORDER BY order_count DESC
LIMIT 20;
```

Truy vấn kết hợp nhiều thực thể và tổng hợp như thế được diễn đạt tự nhiên bằng SQL. Một số document database hoặc hệ khác cũng có thể xử lý, nhưng cách thực thi, chi phí và khả năng bảo đảm ràng buộc khác nhau.

**NoSQL không có nghĩa là “không có SQL”, “không có transaction”, “không có schema” hoặc “luôn phân tán”.** Nhiều hệ hỗ trợ giao dịch, chỉ mục phụ hay cú pháp truy vấn giống SQL. Cần đánh giá **sản phẩm cụ thể, phiên bản, cấu hình và workload**, thay vì dựa vào nhãn công nghệ.

## 10. So sánh nhanh: loại truy vấn nào hợp từng mô hình?

Bảng dưới dùng “Thuận lợi” theo nghĩa **phù hợp với lối tổ chức dữ liệu chủ đạo**, giả định đã thiết kế khóa/chỉ mục đúng và kích thước dữ liệu hợp lý.

| Mẫu truy vấn | Key–value | Document | Wide-column | Graph | Time-series | Search |
|---|---|---|---|---|---|---|
| Lấy một đối tượng theo khóa chính xác | Rất thuận lợi | Rất thuận lợi | Thuận lợi khi đủ partition key | Có thể, thường không cần graph | Có thể tùy mô hình | Có thể, thường không cần search |
| Lọc theo nhiều thuộc tính của một thực thể | Hạn chế nếu thiếu index phụ | Thuận lợi nếu index phù hợp | Hạn chế nếu không khớp khóa/bảng đã thiết kế | Có thể nhưng không phải trọng tâm | Hợp với nhãn và thời gian | Thuận lợi với index phù hợp |
| Lấy N sự kiện gần nhất theo một ID | Cần cấu trúc bổ sung | Có thể với index | Rất thuận lợi khi có partition + clustering | Có thể | Rất thuận lợi | Có thể nhưng không chuyên cho dữ liệu nguồn |
| Duyệt liên kết nhiều bước | Cần tự duy trì chỉ mục/liên kết | Có thể tốn nhiều truy vấn | Thường không thuận lợi | Rất thuận lợi | Không phải trọng tâm | Không phải trọng tâm |
| Tìm từ khóa gần đúng, xếp hạng | Không phải trọng tâm | Tùy chức năng tìm kiếm | Không phải trọng tâm | Không phải trọng tâm | Không phải trọng tâm | Rất thuận lợi |
| Tổng hợp theo cửa sổ thời gian | Cần tính ngoài | Có thể nếu có index/aggregation | Có thể qua bảng tổng hợp hoặc xử lý ngoài | Không phải trọng tâm | Rất thuận lợi | Có thể qua aggregation |
| JOIN linh hoạt nhiều thực thể | Không thuận lợi | Có thể nhưng cần cân nhắc | Không thuận lợi | Thuận lợi với quan hệ, song khác JOIN bảng | Tùy sản phẩm | Không thuận lợi |
| Truy vấn ad hoc nhiều chiều quy mô lớn | Không phải trọng tâm | Tùy engine và index | Thường cần hệ phân tích | Không phải trọng tâm | Hạn chế ngoài thời gian | Tùy engine; không thay OLAP tổng quát |

Bảng không thay thế benchmark. Một document database có text index có thể đáp ứng tìm kiếm cơ bản rất tốt; một hệ quan hệ với JSON và full-text search có thể đáp ứng nhiều yêu cầu vốn thường gắn với NoSQL. Khi cần phân tích dạng quét nhiều cột trên hàng tỷ bản ghi, hệ **columnar OLAP/data warehouse** có thể phù hợp hơn cả sáu loại nêu trên.

## 11. Cùng một dữ liệu, thay câu hỏi là thay đường truy vấn

Lấy một tập dữ liệu bán hàng có các thực thể:

```text
User ---- Order ---- OrderItem ---- Product
 |                         |
 +---- ActivityEvent       +---- Review
            |
         Timestamp
```

### 11.1. Câu hỏi A: “Giỏ hàng của user 42 có gì?”

Biết trước `user_id = 42`, chỉ cần đọc hoặc thay một cấu trúc nhỏ. Key–value là lựa chọn tự nhiên.

Một key:

```text
cart:u42 -> {"items":[{"productId":"p100","quantity":2}]}
```

Nếu giỏ hàng cần kiểm tra giá và tồn kho tại thời điểm thanh toán, hệ thống vẫn phải truy vấn nguồn dữ liệu đáng tin cậy phù hợp. Giá trong cache chỉ nên xem là thông tin hiển thị nếu nghiệp vụ cho phép.

### 11.2. Câu hỏi B: “Hiển thị chi tiết sản phẩm p100”

Giao diện cần tên, mô tả, thuộc tính và một số biến thể. Document có thể gom dữ liệu cần đọc cùng nhau; chỉ mục theo `_id` giúp tìm nhanh. Dữ liệu tăng không giới hạn như toàn bộ bình luận hoặc lịch sử lượt xem nên được cân nhắc đặt riêng.

### 11.3. Câu hỏi C: “50 sự kiện gần nhất của user 42 trong ngày”

Dạng truy vấn theo khóa định danh và thứ tự thời gian; wide-column hoặc time-series phù hợp nếu volume và kiến trúc yêu cầu. Có thể đặt một bảng `events_by_user_day` với partition `(user_id, day)` và clustering theo timestamp giảm dần.

### 11.4. Câu hỏi D: “Những tài khoản nào liên quan tới user 42 qua thiết bị thanh toán?”

Truy vấn quan hệ theo đường đi, có thể phải duyệt nhiều bước và khử trùng lặp. Graph thuận lợi nếu đây là nhu cầu thường xuyên và đồ thị đủ phức tạp.

### 11.5. Câu hỏi E: “Tìm sản phẩm giống cụm từ người dùng nhập”

Truy vấn xử lý từ và xếp hạng, search index giúp truy xuất danh sách ứng viên. Nhưng mức tồn kho, giá chốt và khả năng đặt hàng vẫn nên đối chiếu ở dữ liệu nguồn theo yêu cầu nghiệp vụ.

### 11.6. Câu hỏi F: “Doanh thu theo vùng, tháng và phân khúc”

Đây là phép tổng hợp phân tích trên một tập dữ liệu lớn, kết hợp nhiều chiều. Có thể dùng SQL, data warehouse, columnar OLAP hoặc một hệ thống phân tích chuyên dụng. Không nên mặc định key–value hay wide-column kiểu Cassandra là câu trả lời chỉ vì dữ liệu lớn.

**Bài học:** cùng một ứng dụng có thể cần nhiều **cách nhìn (read model)** lên cùng dữ liệu. Không nên biến việc dùng nhiều database thành mục tiêu; chỉ bổ sung khi lợi ích xử lý truy vấn xứng đáng với chi phí đồng bộ và vận hành.

## 12. Thiết kế theo truy vấn: từ yêu cầu đến khóa và chỉ mục

### 12.1. Ghi truy vấn bằng lời trước khi viết schema

Ví dụ yêu cầu:

> “Lấy 20 đơn gần nhất của một khách hàng, chỉ lấy đơn đã hoàn tất, ở một khoảng thời gian.”

Hãy làm rõ:

- Luôn biết `customer_id`?
- Luôn lọc `status = "COMPLETED"` hay trạng thái thay đổi?
- Cần sắp theo `created_at` giảm dần?
- Khách hàng lớn có thể có bao nhiêu đơn?
- Cần phân trang sâu đến mức nào?
- Cập nhật trạng thái của một đơn có thường xuyên không?
- Nếu một bản ghi đơn thay đổi, các view phụ cần đồng bộ trong bao lâu?

Câu trả lời quyết định có nên dùng chỉ mục ghép trên document/relational, bảng riêng theo status trong wide-column hay một mô hình khác.

### 12.2. Chọn cấu trúc theo điều kiện lọc và sắp xếp

Với document database, một truy vấn:

```javascript
db.orders.find({
  customerId: "u42",
  status: "COMPLETED"
}).sort({ createdAt: -1 }).limit(20);
```

Có thể được hỗ trợ bởi chỉ mục ghép:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

Các trường lọc bằng nhau thường đặt trước trường sắp xếp trong chỉ mục theo mẫu truy vấn này. Trên thực tế cần quan sát plan và các truy vấn khác: index phù hợp một truy vấn không chắc tối ưu cho mọi truy vấn.

Với wide-column, một thiết kế có thể dùng **một bảng theo customer/status và ngày hoặc bucket**, sắp theo thời điểm, rồi lấy một số bản ghi đầu. Tuy nhiên, thay đổi `status` có thể kéo theo xóa/thêm hàng ở bảng theo trạng thái; đây là chi phí cập nhật phải tính từ đầu.

### 12.3. Tránh truy vấn không có giới hạn

Bất kể dùng mô hình gì, yêu cầu “trả mọi bản ghi” thường tạo phản hồi lớn, tiêu tốn RAM và băng thông. Nên xác định:

- Giới hạn số kết quả hợp lý;
- Cách phân trang theo cursor/seek khi cần đọc sâu;
- Thứ tự ổn định và khóa phân giải khi hai bản ghi có cùng timestamp;
- Dữ liệu nào có thể chỉ trả về dưới dạng tổng hợp;
- Truy vấn nào phải chạy nền hoặc chuyển sang đường phân tích.

Ví dụ, khi đọc sự kiện theo thời gian, sử dụng cặp `(timestamp, event_id)` để phân trang theo cursor giúp hạn chế vấn đề trùng/mất kết quả do nhiều sự kiện có cùng timestamp. Cách thực hiện cụ thể phụ thuộc database và điều kiện consistency.

### 12.4. Tính chi phí ghi cho mỗi chỉ mục hoặc read model

Nếu một sự kiện được ghi vào nguồn chính và ba bảng tổng hợp/phục vụ truy vấn, ta có bốn nơi cần quản lý cập nhật. Một lỗi xảy ra giữa các bước có thể khiến dữ liệu chưa đồng nhất.

Phải xác định:

- Dữ liệu nào là **source of truth**?
- Những read model nào được cập nhật đồng bộ?
- Cái nào được cập nhật bất đồng bộ từ event?
- Có idempotency để xử lý sự kiện lặp?
- Khi lỗi đồng bộ, làm sao retry, phát hiện sai lệch và xây dựng lại chỉ mục?
- Người dùng chấp nhận kết quả chậm cập nhật bao lâu?

Thiết kế chỉ tốt khi **cả truy vấn đọc lẫn đường cập nhật** đáp ứng nhu cầu.

## 13. Các giới hạn chung thường bị bỏ qua

### 13.1. Phân tán dữ liệu và truy vấn qua nhiều nút

Một hệ có nhiều shard không tự động nhanh hơn cho mọi truy vấn.

- Truy vấn xác định đúng shard thường ít tốn kém.
- Truy vấn thiếu shard/partition key có thể phải hỏi nhiều nút.
- Sắp xếp toàn cục trên dữ liệu phân tán có thể đòi hỏi gộp nhiều kết quả.
- Một shard nóng có thể kéo dài độ trễ toàn bộ request dù phần lớn node còn dư tài nguyên.

Vì vậy, khi xem xét truy vấn NoSQL, hãy tự hỏi: **Câu truy vấn có thể định vị một hoặc vài partition cụ thể không?**

### 13.2. Chỉ mục không phải miễn phí

Tạo index giúp lọc nhanh hơn nhưng chiếm dung lượng và làm tăng công cập nhật. Chỉ mục nhiều trường cần hợp với thứ tự lọc/sắp; index cho một truy vấn không đồng nghĩa tối ưu cho truy vấn khác.

Ví dụ một sản phẩm có 20 chỉ mục để hỗ trợ các cách lọc ít dùng: tốc độ ghi có thể giảm và chi phí lưu tăng. Cần ưu tiên chỉ mục cho truy vấn phổ biến hoặc đòi hỏi SLO nghiêm ngặt, dựa trên dữ liệu quan sát.

### 13.3. Nhất quán và giao dịch ảnh hưởng khả năng trả lời đúng

Truy vấn đọc replica có thể nhanh hơn hoặc gần người dùng hơn nhưng đôi khi trả bản sao chưa cập nhật, tùy sản phẩm và mức nhất quán. Truy vấn sau khi ghi cần bảo đảm **read-your-writes** phải xem cơ chế đọc/ghi thực tế.

Những cập nhật giao dịch như “đặt ghế cuối cùng” cần nguyên tử hóa kiểm tra và ghi. Không thể chỉ chọn mô hình dữ liệu vì truy vấn đọc nhanh mà bỏ qua tính đúng đắn. Có NoSQL hỗ trợ transaction và cập nhật có điều kiện, nhưng phạm vi bảo đảm khác nhau.

### 13.4. Giới hạn của một bản ghi/tài liệu/phân vùng

Một số hệ giới hạn kích thước tài liệu hoặc khuyến nghị giới hạn partition. Mảng hoặc bản ghi phình to sẽ làm truy vấn khó phân trang, cập nhật tốn kém hoặc gây hot spot.

Cấu trúc lồng nhau chỉ hiệu quả khi phần dữ liệu được nhúng có **kích thước và vòng đời hợp lý**.

### 13.5. Hiệu năng phụ thuộc dữ liệu thật

Cùng câu truy vấn nhưng khác hẳn khi:

- 10.000 bản ghi so với 1 tỷ bản ghi;
- Khóa phân phối đều so với chỉ 1% khóa nhận phần lớn lưu lượng;
- Trả 200 byte so với 2 MB;
- Dữ liệu nằm trong RAM so với phải đọc đĩa;
- Chỉ có một máy so với cụm đa vùng địa lý;
- Không có cập nhật đồng thời so với hàng nghìn ghi/giây.

Do đó, không thể khẳng định “mô hình X nhanh hơn Y” chỉ bằng một phép đo đơn lẻ.

## 14. Khung lựa chọn mô hình theo câu truy vấn thực tế

Có thể đi theo trình tự sau:

**Bước 1 — Chọn 5–10 truy vấn quan trọng nhất.** Nêu rõ đầu vào, kết quả, bộ lọc, sắp xếp và quy mô.

**Bước 2 — Xác định đường đọc chính.** Biết khóa, lọc thuộc tính, đọc theo thứ tự thời gian, duyệt quan hệ, tìm từ khóa hay tổng hợp nhiều chiều?

**Bước 3 — Xác định ràng buộc dữ liệu.** Có cần cập nhật nhiều thực thể cùng lúc, tính duy nhất, read-your-writes, độ bền ghi hoặc đồng bộ chỉ mục tức thời?

**Bước 4 — Phác thảo khóa, chỉ mục và đơn vị lưu trữ.** Vẽ ra câu truy vấn sẽ đến một bản ghi, một phân vùng, vài phân vùng hay gần như toàn bộ dữ liệu.

**Bước 5 — Tính chi phí cập nhật.** Dữ liệu nào bị sao chép? Khi một trường đổi, cần cập nhật những đâu?

**Bước 6 — Đánh giá phân phối tải.** Có khóa nóng, partition quá lớn, fan-out, số truy vấn đồng thời hoặc đột biến dữ liệu không?

**Bước 7 — Thử nghiệm có điều kiện đo rõ ràng.** Kiểm tra p50/p95/p99, thông lượng thành công, sai lệch dữ liệu, mức dùng CPU/I/O và chi phí vận hành ở quy mô gần thực tế.

### 14.1. Ma trận gợi ý nhanh

| Điều kiện nổi bật của yêu cầu | Mô hình đáng xem xét | Câu hỏi xác nhận trước khi quyết định |
|---|---|---|
| Luôn biết khóa của đối tượng cần đọc/ghi | Key–value | Có cần lọc ngược theo giá trị, scan hoặc giữ dữ liệu bền vững? |
| Thường đọc nhiều trường lồng nhau của cùng một đối tượng | Document | Mảng có tăng không giới hạn? Có nhiều quan hệ cần cập nhật cùng lúc? |
| Lượng ghi lớn, truy vấn cố định bằng khóa phân vùng và thứ tự | Wide-column | Partition key có phân bố đều? Có truy vấn ad hoc ngoài khóa? |
| Câu trả lời chủ yếu là đường đi, độ gần hoặc mẫu liên kết | Graph | Độ sâu duyệt và supernode có giới hạn được không? |
| Dữ liệu đo theo thời gian, cần window aggregation và retention | Time-series | Nhãn có cardinality quá lớn? Có phải join nghiệp vụ phức tạp không? |
| Tìm từ ngữ gần đúng, có phân tích văn bản và xếp hạng | Search-oriented | Chỉ mục cập nhật chậm bao lâu? Nguồn dữ liệu gốc ở đâu? |
| Giao dịch nhiều thực thể, JOIN linh hoạt và ràng buộc chặt | Relational | Có thể tối ưu bằng index, JSON và partition trước khi thêm hệ khác? |
| Tổng hợp nhiều chiều trên lượng dữ liệu rất lớn | Columnar OLAP / warehouse | Dữ liệu cập nhật tức thời hay có thể đồng bộ theo lô/stream? |

Không cần chọn đúng một hệ cho toàn bộ ứng dụng. Nhưng cũng không nên tách quá sớm: **mỗi database mới tạo thêm chi phí đồng bộ, vận hành, sao lưu, bảo mật, giám sát và xử lý sự cố**.

## 15. Tình huống thực hành

### Tình huống 1 — Danh mục hàng hóa với thuộc tính thay đổi

Một nền tảng có 20 loại sản phẩm. Mỗi loại dùng tập thuộc tính khác nhau; trang chi tiết luôn hiển thị tên, mô tả, giá, 5–10 biến thể. Người dùng cần lọc theo danh mục và một vài trường phổ biến.

**Phân tích:** document là ứng viên hợp lý vì cấu trúc thuộc tính linh hoạt và phần lớn dữ liệu được đọc cùng nhau. Cần lập chỉ mục theo các bộ lọc phổ biến, giới hạn số biến thể nhúng và tách dữ liệu phát sinh liên tục như lượt xem/bình luận khối lượng lớn.

**Câu hỏi mở rộng:** Nếu hệ thống đột ngột phải báo cáo tổng doanh thu từng nhà cung cấp theo quý, dữ liệu catalog một mình đã đủ chưa? Cần kết hợp nguồn đơn hàng hay một hệ phân tích?

### Tình huống 2 — Dữ liệu hoạt động có hàng chục triệu sự kiện mỗi ngày

Ứng dụng ghi log truy cập và thường hỏi: “Người dùng U đã làm gì trong ngày D, mới nhất trước?”. Thi thoảng cần thống kê số lượt click của mọi người dùng theo quốc gia.

**Phân tích:** wide-column với khóa `(user_id, day)` và clustering theo timestamp phù hợp truy vấn đầu nếu partition không quá lớn. Truy vấn thống kê toàn hệ cần thiết kế đường tổng hợp riêng hoặc đưa dữ liệu sang hệ phân tích. Không nên kỳ vọng một bảng theo người dùng trả lời tốt mọi phân tích.

### Tình huống 3 — Phát hiện gian lận theo thiết bị chung

Một dịch vụ tài chính muốn phát hiện cụm tài khoản dùng chung thiết bị, IP và phương thức thanh toán. Truy vấn thường cần đi 2–4 bước quan hệ, có thể giải thích đường nối cho chuyên viên.

**Phân tích:** graph phù hợp với truy vấn duyệt cạnh và đường đi. Cần giới hạn độ sâu, xử lý các node bậc cao và thiết kế chỉ mục điểm bắt đầu. Hệ thống giao dịch nguồn vẫn cần giữ ràng buộc tài khoản và thanh toán.

### Tình huống 4 — Hệ thống quan trắc nhiều cảm biến

Mỗi cảm biến phát 1 sự kiện/giây. Người quản trị xem biểu đồ 24 giờ, trung bình theo phút và cảnh báo vượt ngưỡng. Dữ liệu thô chỉ cần giữ 30 ngày, dữ liệu tổng hợp giữ 2 năm.

**Phân tích:** time-series thuận lợi vì toàn bộ truy vấn dựa vào device/time và window aggregation. Cần retention, downsampling, chiến lược xử lý ghi dồn và tránh dùng request ID duy nhất làm nhãn định danh series nếu engine tính cardinality từ các nhãn đó.

### Tình huống 5 — Trang tìm kiếm phòng cho thuê

Người dùng nhập “căn hộ gần trung tâm có ban công”, muốn kết quả liên quan, sau đó lọc khu vực, giá, số phòng, ngày trống.

**Phân tích:** tìm kiếm ngôn ngữ và lọc có thể dùng search index; giá, trạng thái đặt phòng và lịch trống cần được kiểm chứng bằng hệ nguồn theo ràng buộc nghiệp vụ. Nếu chỉ mục được đồng bộ bất đồng bộ, một phòng vừa được đặt có thể còn hiển thị tạm thời, nên bước xác nhận phải kiểm tra dữ liệu đủ mới.

## 16. Câu hỏi ôn tập và hướng trả lời

**1. Vì sao key–value rất phù hợp với `GET cart:user:42` nhưng yếu với truy vấn “tất cả giỏ hàng chứa SKU A1”?**

Vì thao tác đầu biết chính xác khóa cần đọc; thao tác sau lọc theo giá trị nằm trong nhiều key. Nếu không có cấu trúc chỉ mục bổ sung, hệ thống có thể phải duyệt nhiều giá trị.

**2. Một document có 2 triệu phần tử mảng vì sao có thể là thiết kế kém dù UI cần đọc thông tin của thực thể?**

Vì mảng tăng không giới hạn làm tài liệu lớn, cập nhật phức tạp và đọc/thay đổi tốn tài nguyên. Dữ liệu tăng độc lập nên được tách ra theo mô hình truy vấn khác.

**3. Vì sao bảng wide-column với partition key `(user_id, day)` không tự động hỗ trợ truy vấn mọi sự kiện trong một ngày?**

Vì chưa biết `user_id` nên không định vị được một partition. Muốn truy vấn theo ngày trên toàn người dùng có thể cần bảng/bucket theo ngày hoặc hệ phân tích riêng.

**4. Khi nào graph có lợi hơn việc truy vấn khóa ngoại?**

Khi câu hỏi chính cần đi theo các quan hệ có độ sâu và cấu trúc thay đổi, như tìm nhiều tài khoản liên kết gián tiếp. Truy vấn một bảng theo khóa ngoại với chỉ mục tốt vẫn rất phù hợp với relational.

**5. Một hệ time-series có nhiều dữ liệu và có vẻ truy vấn chậm. Có nên thêm nhiều node ngay không?**

Chưa đủ thông tin. Cần xem điều kiện thời gian, nhãn series, cardinality, phân vùng, mức độ tổng hợp, data retention, chỉ mục và tài nguyên bị bão hòa. Thêm node không giải quyết được mọi truy vấn hoặc thiết kế nhãn kém.

**6. Có nên coi kết quả search index là xác nhận tồn kho cuối cùng?**

Không nên mặc định như vậy. Search index có thể cập nhật chậm so với nguồn giao dịch, nên cần kiểm tra tồn kho và điều kiện đặt hàng ở nguồn có cơ chế đảm bảo đúng nghiệp vụ.

**7. Vì sao một truy vấn có chỉ mục vẫn có thể chậm?**

Chỉ mục có thể kém chọn lọc, phải đọc nhiều bản ghi lớn, trả lượng dữ liệu lớn, sắp xếp/tổng hợp ngoài index, gặp hot partition hoặc bị giới hạn mạng/I/O. Cần xem kế hoạch thực thi và số bản ghi/byte thực tế.

## 17. Kết luận

Mỗi mô hình dữ liệu NoSQL tạo ra một **đường truy cập thuận lợi**:

- Key–value tối ưu cho câu hỏi có sẵn khóa.
- Document thuận lợi khi đọc và lọc một thực thể có thuộc tính lồng nhau.
- Wide-column thuận lợi khi truy vấn khớp partition key và thứ tự clustering đã thiết kế.
- Graph thuận lợi khi câu hỏi là duyệt các mối quan hệ.
- Time-series thuận lợi khi truy vấn dựa vào thời gian và nguồn phát.
- Search-oriented thuận lợi khi cần tìm kiếm văn bản, xếp hạng và truy vấn gần đúng.

Hạn chế của mỗi mô hình thường xuất hiện khi truy vấn **đi ngược lại cách dữ liệu được tổ chức**, buộc hệ thống quét rộng, ghép nhiều kết quả hoặc duy trì thêm chỉ mục/read model. Vì vậy, trước khi chọn database, hãy mô tả câu truy vấn thật, dữ liệu trả về, độ lớn, tần suất, yêu cầu đúng đắn và độ trễ mục tiêu. Sau đó mới chọn khóa, chỉ mục, cách nhóm dữ liệu và công nghệ phù hợp.
