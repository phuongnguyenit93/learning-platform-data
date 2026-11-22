# Bài toán phù hợp, giới hạn và đánh đổi khi chọn MongoDB

MongoDB là hệ quản trị cơ sở dữ liệu hướng tài liệu (*document database*). Thay vì tổ chức dữ liệu chủ yếu thành các bảng và hàng liên kết bằng khóa ngoại, MongoDB lưu các tài liệu BSON trong *collection*. BSON có cấu trúc gần với JSON nhưng bổ sung kiểu dữ liệu như `ObjectId`, `Date` và `Decimal128`. Một tài liệu có thể chứa object và mảng lồng nhau, nên nhiều thông tin được đọc hoặc cập nhật cùng nhau có thể nằm trong một đơn vị lưu trữ.

Điểm quan trọng khi lựa chọn MongoDB không phải là “dữ liệu có phải JSON không?”, mà là **ứng dụng đọc, ghi, thay đổi và đảm bảo tính đúng đắn cho dữ liệu đó như thế nào**. MongoDB phù hợp với một số kiểu truy cập và mô hình dữ liệu; ở những bài toán khác, chi phí duy trì quan hệ, giao dịch, chỉ mục và vận hành có thể lớn hơn lợi ích của document model.

## 1. Đặt bài toán trước khi chọn công nghệ

Giả sử xây dựng hệ thống quản lý sản phẩm cho một sàn thương mại điện tử. Mỗi loại sản phẩm có tập thuộc tính khác nhau:

- Laptop: CPU, RAM, dung lượng lưu trữ, kích thước màn hình.
- Áo: chất liệu, màu, kích cỡ, hướng dẫn bảo quản.
- Sách: tác giả, nhà xuất bản, số trang.

Một tài liệu sản phẩm có thể biểu diễn như sau:

```javascript
// Ví dụ chạy trong mongosh
db.products.insertOne({
  _id: "P1001",
  sellerId: "S42",
  category: "laptop",
  name: "Laptop 14 inch",
  status: "ACTIVE",
  attributes: {
    cpu: "Core i7",
    ramGb: 16,
    storage: { type: "SSD", capacityGb: 512 }
  },
  tags: ["office", "lightweight"],
  createdAt: ISODate("2026-01-15T09:00:00Z")
});
```

Một tài liệu áo có thể sử dụng `attributes.size` và `attributes.fabric` thay cho `attributes.cpu`. Cả hai vẫn thuộc cùng collection `products`, với các trường chung dành cho tìm kiếm, lọc và quản trị. Đây là tình huống **MongoDB thường thuận lợi**: các bản ghi cùng một nhóm nghiệp vụ có phần lõi chung nhưng cấu trúc chi tiết thay đổi theo loại.

Tuy nhiên, cần hỏi thêm: ứng dụng sẽ tìm kiếm theo các thuộc tính nào? Có bao nhiêu kiểu sản phẩm? Thuộc tính nào bắt buộc? Tần suất lọc và sắp xếp theo `attributes` lớn đến đâu? Chỉ việc lưu được nhiều cấu trúc không đảm bảo truy vấn sẽ nhanh hoặc dữ liệu sẽ đúng.

### Từ yêu cầu nghiệp vụ đến lựa chọn lưu trữ

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Một màn hình hoặc API thường cần đọc những dữ liệu nào cùng nhau? | Quyết định phần nào nên đặt chung trong một document. |
| Một thao tác nghiệp vụ cần cập nhật bao nhiêu thực thể? | Quyết định có thể tận dụng tính nguyên tử của một document hay phải dùng transaction nhiều document. |
| Quan hệ giữa các thực thể là 1–1, 1–ít hay 1–rất nhiều? | Quyết định nên *embed* hay *reference*, và liệu mảng có tăng vô hạn không. |
| Dữ liệu thay đổi cấu trúc thường xuyên đến mức nào? | Đánh giá lợi ích của mô hình linh hoạt so với chi phí kiểm soát schema. |
| Cần truy vấn, tổng hợp, sắp xếp hoặc tìm kiếm theo trường nào? | Quyết định chỉ mục, cách phân vùng, cách giữ dữ liệu và chi phí truy vấn. |
| Có yêu cầu chặt chẽ về toàn vẹn, giao dịch, kiểm toán không? | Đánh giá độ phức tạp khi triển khai ràng buộc và giao dịch. |
| Quy mô dữ liệu, tốc độ ghi và mục tiêu độ trễ là bao nhiêu? | Chỉ ra khi nào replication, sharding hoặc hệ thống chuyên dụng thực sự cần thiết. |

## 2. Những bài toán MongoDB thường phù hợp

### 2.1. Catalog có thuộc tính đa dạng, cấu trúc phát triển theo sản phẩm

Danh mục hàng hóa, tài sản số, biểu mẫu động và metadata của tài nguyên thường có các trường khác nhau theo loại. Document model giúp lưu các nhóm trường tùy biến một cách tự nhiên, đồng thời giữ những thuộc tính dùng chung như mã, chủ sở hữu và trạng thái.

Lợi ích rõ nhất khi: ứng dụng thường lấy một đối tượng hoàn chỉnh; mỗi đối tượng có các nhóm thuộc tính lồng nhau; đội phát triển cần thêm trường mà không phải xây dựng nhiều bảng phụ cho từng biến thể.

Đánh đổi: phải quy định kiểu dữ liệu, trường bắt buộc và phiên bản cấu trúc. Nếu cho phép mọi document tùy ý, cùng một khái niệm có thể xuất hiện dưới các tên và kiểu khác nhau (`price` dạng string ở tài liệu cũ, dạng number ở tài liệu mới), khiến truy vấn và báo cáo trở nên khó tin cậy. MongoDB có cơ chế xác thực schema cho collection; ứng dụng vẫn cần logic migration và kiểm thử tương thích.

### 2.2. Hồ sơ, cấu hình và nội dung có cấu trúc lồng nhau

Ví dụ một cấu hình người dùng gồm ngôn ngữ, giao diện, cài đặt thông báo và danh sách tùy chọn có kích thước giới hạn. API thường đọc hoặc sửa các phần của cấu hình theo `userId`, và toàn bộ dữ liệu thuộc cùng một đối tượng nghiệp vụ.

```javascript
{
  _id: "U501",
  locale: "vi-VN",
  preferences: {
    theme: "dark",
    notifications: { email: true, push: false }
  }
}
```

Cấu hình này có thể được đọc bằng một truy vấn và cập nhật nguyên tử trong một document. Không cần phân tách mọi object lồng nhau thành bảng hoặc collection riêng nếu chúng có vòng đời gắn với hồ sơ.

### 2.3. Nội dung CMS, tài liệu nghiệp vụ và metadata

Trang nội dung, bài viết, mẫu biểu hoặc hồ sơ xử lý có thể chứa các block như tiêu đề, đoạn văn, ảnh, tùy chọn hiển thị và lịch sử phiên bản rút gọn. MongoDB hữu ích khi API quản lý trọn một tài liệu, các block thay đổi theo loại và cần lấy nội dung theo định danh hoặc trạng thái.

Nhưng nếu một “tài liệu” chứa các phần được nhiều người sửa đồng thời, có lịch sử chỉnh sửa vô hạn hoặc cần tìm kiếm toàn văn nâng cao, kiến trúc thường phải bổ sung cơ chế versioning, kiểm soát xung đột, lưu lịch sử riêng hoặc một công cụ tìm kiếm phù hợp. **Lưu được nội dung trong document không đồng nghĩa với có sẵn mọi khả năng quản lý nội dung.**

### 2.4. Dữ liệu sự kiện và time series với mô hình truy vấn rõ ràng

Sự kiện ứng dụng, dữ liệu thiết bị và phép đo theo thời gian có thể có payload thay đổi. MongoDB hỗ trợ cách tổ chức và truy vấn dữ liệu theo thời gian, kể cả collection chuyên biệt cho time series. Phù hợp khi cần tra cứu theo thiết bị/người dùng và khoảng thời gian, kèm một số phép tổng hợp vận hành.

Đổi lại, dữ liệu có tốc độ ghi rất cao, thời gian lưu rất dài, nhu cầu phân tích cột quy mô lớn hoặc tìm kiếm log toàn văn có thể phù hợp hơn với hệ thống time-series, log/search hay analytical warehouse chuyên dụng. Cần đánh giá tốc độ nạp, chiến lược retention, tổng chi phí lưu trữ và câu truy vấn thực tế, thay vì coi một hệ quản trị là công cụ tối ưu cho mọi loại dữ liệu.

### 2.5. Dịch vụ sở hữu một aggregate nghiệp vụ rõ ràng

Một dịch vụ quản lý đơn hàng có thể lưu đơn và các dòng sản phẩm cùng một document, vì việc đọc trạng thái đơn thường cần cả danh sách dòng hàng. Một thao tác cập nhật trạng thái và metadata của chính đơn hàng có thể thực hiện nguyên tử.

Mô hình này có lợi khi ranh giới dữ liệu được thiết kế theo *aggregate* nghiệp vụ: nhóm thông tin thường đi cùng nhau, có kích thước hữu hạn và chia sẻ vòng đời. Nó kém phù hợp hơn khi phần lớn nghiệp vụ là cập nhật đồng thời nhiều aggregate độc lập với nhiều ràng buộc chéo.

## 3. Document model đem lại gì, và phải trả giá gì?

| Đặc tính | Lợi ích trong bài toán phù hợp | Giới hạn hoặc đánh đổi |
| --- | --- | --- |
| Schema linh hoạt | Thêm các trường tùy chọn, hỗ trợ nhiều biến thể đối tượng. | Dễ sinh dữ liệu không nhất quán nếu thiếu validation, migration và quy ước đặt tên. |
| Object/mảng lồng nhau | Lấy dữ liệu liên quan trong một lần đọc; biểu diễn aggregate tự nhiên. | Document có thể phình to; cập nhật mảng lớn và truy vấn phần tử phức tạp hơn. |
| Tính nguyên tử ở cấp document | Cập nhật nhiều trường của cùng đối tượng như một thao tác nguyên tử. | Bất biến xuyên nhiều document vẫn cần thiết kế giao dịch và xử lý lỗi. |
| Chỉ mục phong phú | Hỗ trợ nhiều kiểu truy vấn bằng index phù hợp. | Index tăng dung lượng, bộ nhớ và chi phí ghi; không thể index mọi tổ hợp tùy ý. |
| Replication và sharding | Hỗ trợ tính sẵn sàng và phân phối dữ liệu khi có nhu cầu. | Tăng độ phức tạp vận hành, độ trễ mạng và yêu cầu thiết kế shard key. |
| Denormalization | Giảm các thao tác ghép nhiều thực thể khi đọc. | Dữ liệu trùng lặp cần quy tắc cập nhật và chấp nhận trạng thái lệch tạm thời hoặc transaction. |

MongoDB không tự biến mọi truy vấn thành một lần đọc. Document được mô hình hóa sai có thể tạo nhiều truy vấn nhỏ, `$lookup` tốn kém, index lớn hoặc những thao tác ghi đụng độ trên cùng document. Hiệu năng đến từ **sự phù hợp giữa cách tổ chức dữ liệu và mẫu truy cập**, không chỉ từ tên cơ sở dữ liệu.

## 4. Quyết định embed hay reference

Đây là một trong những quyết định ảnh hưởng lớn nhất đến khả năng vận hành của MongoDB.

### Embed: đặt dữ liệu con trong document cha

```javascript
{
  _id: "ORDER-1007",
  customerId: "C103",
  status: "CREATED",
  orderedAt: ISODate("2026-02-01T10:30:00Z"),
  items: [
    { productId: "P1", nameSnapshot: "Bàn phím", quantity: 2, unitPriceMinor: 195000 },
    { productId: "P2", nameSnapshot: "Chuột", quantity: 1, unitPriceMinor: 250000 }
  ],
  totalMinor: 640000
}
```

Thông tin `nameSnapshot` và `unitPriceMinor` là ảnh chụp của giá/tên tại thời điểm mua; thay đổi catalog sau này không được làm thay đổi lịch sử đơn hàng. Các dòng hàng có số lượng tương đối giới hạn và thường được lấy cùng với đơn, nên *embed* là lựa chọn có cơ sở. Trong ví dụ, `Minor` chỉ đơn vị tiền nhỏ nhất theo quy ước của hệ thống; ứng dụng thực tế cần định nghĩa rõ tiền tệ và cách làm tròn.

**Nên cân nhắc embed khi** dữ liệu con thuộc về cha, ít được truy cập độc lập, thường đọc/ghi cùng nhau, có giới hạn kích thước và không bị chia sẻ làm nguồn sự thật cho nhiều đối tượng khác.

### Reference: giữ định danh để truy cập đối tượng độc lập

```javascript
// Collection customers
{ _id: "C103", fullName: "Nguyen A", loyaltyTier: "SILVER" }

// Collection orders
{ _id: "ORDER-1007", customerId: "C103", status: "CREATED" }
```

Khách hàng tồn tại độc lập và có thể có số đơn không giới hạn. Gắn mọi đơn vào một mảng trong document khách hàng sẽ tạo một mảng tăng mãi, dễ gây truy vấn và cập nhật tốn kém, đồng thời chạm giới hạn kích thước document. **MongoDB giới hạn kích thước một BSON document ở 16 MiB**; việc lưu dữ liệu phát triển không giới hạn trong một tài liệu thường là dấu hiệu cần tách cấu trúc.

**Nên cân nhắc reference khi** một thực thể có vòng đời riêng, được dùng ở nhiều nơi, cần truy vấn độc lập, quan hệ 1–rất nhiều hoặc nhiều–nhiều, hoặc kích thước tập con không thể dự báo. Có thể dùng `$lookup` để kết hợp collection, nhưng cần đo chi phí thực tế của truy vấn, index và dữ liệu trao đổi.

### Một quy tắc thực dụng

1. Bắt đầu từ **một thao tác đọc/ghi thực tế** (ví dụ mở chi tiết đơn hàng), không bắt đầu từ sơ đồ bảng.
2. Xác định những thuộc tính cần nằm chung để đáp ứng một bất biến hoặc một lần đọc.
3. Tách dữ liệu có vòng đời độc lập, có kích thước tăng không giới hạn hoặc cần được nhiều aggregate dùng như nguồn sự thật.
4. Chỉ sao chép trường thực sự phục vụ truy vấn; phải có chính sách cập nhật hoặc chấp nhận snapshot bất biến.
5. Thử với dữ liệu và tần suất tăng trưởng dự kiến trước khi chốt thiết kế.

Không có quy tắc “luôn embed” hay “luôn reference”. Một hệ thống thực tế thường kết hợp cả hai cách trong cùng mô hình.

## 5. Tính đúng đắn dữ liệu và giao dịch

### 5.1. Atomicity không đồng nghĩa với mọi nghiệp vụ đều nguyên tử

MongoDB thực hiện thao tác ghi trên **một document** một cách nguyên tử, kể cả khi thao tác thay đổi nhiều trường hoặc phần tử mảng trong document đó. Ví dụ, cập nhật trạng thái và thời điểm xác nhận của cùng một đơn hàng có thể là một lệnh:

```javascript
db.orders.updateOne(
  { _id: "ORDER-1007", status: "CREATED" },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);
```

Điều kiện `status: "CREATED"` giúp thao tác chỉ chuyển trạng thái khi đơn còn ở trạng thái mong đợi. Ứng dụng phải kiểm tra `matchedCount`/`modifiedCount` để biết thay đổi có được áp dụng hay không. Đây là một cách giảm lỗi cập nhật cạnh tranh mà không nhất thiết phải đọc rồi ghi tách rời.

Ngược lại, nghiệp vụ “tạo đơn, trừ tồn kho, ghi thanh toán” liên quan nhiều document hoặc collection. Nếu mọi thay đổi phải cùng thành công hoặc cùng hủy, cần transaction nhiều document hoặc thiết kế nghiệp vụ khác phù hợp với đặc tính hệ thống phân tán.

MongoDB **có hỗ trợ transaction nhiều document** trong các cấu hình được hỗ trợ; nhận định “MongoDB không có transaction” là sai. Nhưng transaction cần tài nguyên, làm tăng phạm vi khóa/xung đột và có thể phát sinh retry khi có lỗi tạm thời. Không nên mặc định áp transaction cho mọi thao tác chỉ để che đi mô hình dữ liệu chưa phù hợp.

### 5.2. Tính nhất quán phụ thuộc thiết lập và đường đọc/ghi

Với replica set, các lựa chọn như `writeConcern`, `readConcern` và `readPreference` ảnh hưởng đến xác nhận ghi, độ mới của dữ liệu được đọc, khả năng chịu lỗi và độ trễ. Chẳng hạn, `writeConcern: "majority"` yêu cầu ghi được xác nhận theo điều kiện đa số thành viên có quyền bỏ phiếu thích hợp; nó không tự động biến mọi lượt đọc từ secondary thành đọc dữ liệu mới nhất.

Các yêu cầu như “người dùng phải thấy ngay thao tác vừa lưu”, “không được đọc dữ liệu chưa được xác nhận theo chính sách” và “không được ghi trùng thanh toán” cần được mô tả riêng. Sau đó mới chọn session, read/write concern, idempotency key, unique index hoặc transaction. Không nên kết luận chung rằng MongoDB “luôn eventual consistency” hay “luôn strong consistency” mà bỏ qua đường thao tác thực tế.

### 5.3. Ràng buộc và schema vẫn phải được thiết kế

Một số ràng buộc có thể triển khai qua **unique index**, collection validator và thao tác cập nhật có điều kiện. Tuy nhiên, ràng buộc xuyên nhiều collection và các quan hệ nghiệp vụ phức tạp thường cần logic ứng dụng hoặc transaction. MongoDB không cung cấp mô hình khóa ngoại kiểu quan hệ để tự động kiểm tra mọi tham chiếu giữa document.

Ví dụ, để tránh trùng mã sản phẩm trong phạm vi một người bán:

```javascript
db.products.createIndex(
  { sellerId: 1, sku: 1 },
  { unique: true }
);
```

Trong sharded collection, khả năng áp dụng unique index còn phụ thuộc cấu hình và shard key; phải xác nhận giới hạn của phiên bản và cách phân mảnh trước khi coi đó là ràng buộc toàn cục. Ngoài ra, cần xác định cách xử lý trường thiếu hoặc giá trị `null` theo quy tắc nghiệp vụ.

## 6. Truy vấn và chỉ mục: thiết kế theo nhu cầu sử dụng

Giả sử màn hình quản lý hiển thị 20 sản phẩm đang bán của một seller, mới nhất trước:

```javascript
db.products.find(
  { sellerId: "S42", status: "ACTIVE" },
  { name: 1, category: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(20);

db.products.createIndex({
  sellerId: 1,
  status: 1,
  createdAt: -1
});
```

Compound index trên phù hợp với một đường truy vấn cụ thể: lọc theo `sellerId`, `status` rồi sắp xếp `createdAt`. Nhưng nó không bảo đảm hiệu quả cho các API khác, chẳng hạn tìm mọi laptop có `attributes.ramGb >= 16`, tìm kiếm văn bản hay tổng hợp doanh thu theo ngày.

Những đánh đổi cần nhận diện:

- **Index phục vụ đọc nhưng làm ghi đắt hơn**: insert, update và delete có thể phải cập nhật nhiều cấu trúc chỉ mục; index còn chiếm đĩa và bộ nhớ.
- **Truy vấn trên trường động**: nếu người dùng có thể lọc theo hàng trăm thuộc tính tùy chọn, việc xây index riêng cho mọi trường thường không khả thi. Cần thống kê bộ lọc thực tế, xem xét index phù hợp hoặc hệ tìm kiếm chuyên dụng.
- **Mảng và multikey index**: truy vấn phần tử mảng được hỗ trợ, nhưng mô hình mảng lớn hoặc tổ hợp điều kiện phức tạp có thể khiến index tăng đáng kể; cần kiểm tra giới hạn index với schema cụ thể.
- **Aggregation**: pipeline cho phép lọc, nhóm, biến đổi và kết hợp dữ liệu, nhưng phép nhóm/sắp xếp trên lượng dữ liệu lớn vẫn tốn CPU, RAM hoặc I/O; đôi khi cần pre-aggregation hoặc hệ analytics riêng.
- **Phân trang**: `skip` với offset rất lớn thường ngày càng tốn kém; với luồng dữ liệu tăng liên tục, phân trang theo khóa có thứ tự ổn định thường đáng cân nhắc hơn.

Không nên chỉ căn cứ vào thời gian chạy của truy vấn trên vài trăm bản ghi thử nghiệm. Hãy dùng `explain()` để xem query plan và số tài liệu/khóa được quét, đo p95/p99 latency dưới tải gần thực tế và kiểm tra kích thước working set so với tài nguyên máy.

## 7. Replication, sharding và vận hành phân tán

MongoDB hỗ trợ **replica set** để có các bản sao dữ liệu và khả năng bầu primary khi xảy ra sự cố. Đây là cơ sở quan trọng cho tính sẵn sàng và một số khả năng của hệ thống. Nhưng replication không thay thế backup: xóa nhầm hoặc ghi sai có thể được sao chép sang các replica.

**Sharding** phân phối dữ liệu giữa nhiều shard để đáp ứng quy mô lớn hơn. Sharding không phải nút bấm “tự động nhanh hơn”: shard key quyết định phân bố dữ liệu và mức độ một truy vấn được định tuyến đến shard cụ thể hay phải quét rộng. Một key có phân bố lệch có thể tạo shard quá tải; một key không tương ứng với filter phổ biến có thể khiến truy vấn phải gửi đến nhiều shard.

Khi đánh giá sharding, cần trả lời được:

1. Tốc độ tăng dữ liệu và lưu lượng ghi có thực sự vượt khả năng của một node/replica set được cấu hình hợp lý không?
2. Truy vấn quan trọng có mang điều kiện theo shard key không, hay sẽ phải fan-out đến nhiều shard?
3. Có nguy cơ dồn ghi vào một giá trị shard key hoặc một khoảng khóa liên tiếp không?
4. Các yêu cầu unique index, transaction, aggregation và di chuyển dữ liệu chịu tác động gì khi chia shard?
5. Đội vận hành có giám sát, backup/restore, capacity planning và quy trình khắc phục sự cố phân tán chưa?

Mở rộng ngang giúp giải quyết một số giới hạn về dung lượng và lưu lượng, nhưng đổi lại là độ phức tạp cấu hình, cân bằng dữ liệu, mạng, monitoring và chi phí. Đối với phần lớn dự án còn nhỏ, thiết kế schema và index đúng, đặt ngưỡng tải và lập kế hoạch tăng trưởng thường có giá trị hơn việc sharding từ đầu.

## 8. Khi nào MongoDB có thể là lựa chọn kém phù hợp?

### 8.1. Bài toán có quan hệ chặt và truy vấn kết hợp phức tạp

Hệ thống kế toán, sổ cái, báo cáo nghiệp vụ nhiều chiều hoặc dữ liệu liên kết qua nhiều thực thể thường cần ràng buộc toàn vẹn, join và giao dịch phức tạp. Cơ sở dữ liệu quan hệ như PostgreSQL thường đem lại mô hình SQL, khóa ngoại, constraint và công cụ phân tích quan hệ tự nhiên hơn.

MongoDB có `$lookup` và transaction; vì vậy cần nói chính xác rằng **các thao tác đó có thể thực hiện**, nhưng khi chúng là trung tâm của gần mọi yêu cầu, lợi ích của document model có thể bị giảm đáng kể.

### 8.2. Nghiệp vụ nhiều bước phải nhất quán xuyên nhiều aggregate

Ví dụ: một hệ thống chuyển tiền đòi hỏi số dư, bút toán, hạn mức và nhật ký được cập nhật theo các quy tắc nhất quán rất chặt. Có thể xây dựng trên MongoDB với transaction và thiết kế phù hợp, nhưng một RDBMS thường là ứng viên đầu tiên để đánh giá khi mô hình dữ liệu phụ thuộc nhiều vào quan hệ và constraint xuyên bảng.

Trường hợp này không nên quyết định chỉ dựa vào benchmark ghi/đọc thô. Phải thử cả yêu cầu khôi phục sau lỗi, retry, chống xử lý trùng và khả năng kiểm toán.

### 8.3. Tìm kiếm văn bản hoặc phân tích dữ liệu là workload chính

Tìm kiếm toàn văn với ranking phức tạp, phân tích log dung lượng lớn, dashboard hàng tỷ sự kiện hoặc warehouse nhiều phép join có thể phù hợp hơn với search engine hoặc hệ OLAP. MongoDB có các khả năng search và aggregation nhất định, nhưng nên so sánh theo loại truy vấn, tính năng triển khai, độ trễ, retention và chi phí thực tế.

### 8.4. Dữ liệu là graph với nhiều cấp quan hệ cần duyệt liên tục

Nếu nghiệp vụ chủ yếu là tìm đường đi, liên kết nhiều tầng hoặc phân tích mạng quan hệ, graph database có thể diễn đạt và tối ưu các truy vấn đó thuận tiện hơn. MongoDB có các phép kết hợp và duyệt quan hệ nhất định, song hiệu quả phụ thuộc đồ thị và số bước truy vấn.

### 8.5. Chỉ cần cache hoặc key–value đơn giản với thời gian sống rất ngắn

Session tạm, bộ đếm có mục tiêu độ trễ rất thấp hoặc dữ liệu cache có thể hợp lý hơn với Redis hay một kho key–value chuyên dụng. MongoDB có thể lưu các đối tượng đó, nhưng không nên chọn chỉ vì cả hai đều đọc theo key.

## 9. Ba tình huống thiết kế: chọn gì và vì sao?

### Tình huống A — Sàn bán hàng với catalog đa dạng

**Nhu cầu:** nhiều danh mục, thuộc tính sản phẩm không đồng nhất; màn hình sản phẩm chủ yếu tải một đối tượng; tìm kiếm theo người bán, danh mục, trạng thái và một tập bộ lọc phổ biến.

**Đánh giá:** MongoDB là một ứng viên tốt cho catalog. Có thể đặt trường chung ở mức gốc, thuộc tính chuyên biệt trong object, dùng validator và index cho truy vấn phổ biến. Nếu cần full-text search với ranking phức tạp, đánh giá thêm dịch vụ tìm kiếm. Không nên mặc định dùng chính cấu trúc catalog để lưu lịch sử thanh toán hoặc tính sổ cái.

### Tình huống B — Đơn hàng, tồn kho và thanh toán

**Nhu cầu:** cập nhật đơn, trừ tồn kho, ghi nhận thanh toán và đảm bảo không bán vượt số lượng tồn.

**Đánh giá:** có thể embed các dòng hàng và snapshot giá trong đơn MongoDB; nhưng tồn kho là thực thể được nhiều đơn cùng cập nhật. Cần kiểm soát cạnh tranh bằng ghi có điều kiện, transaction hoặc workflow đặt chỗ/chốt đơn có bù trừ. Nếu toàn hệ thống đặt trọng tâm vào nhiều invariant xuyên bảng và báo cáo SQL, nên đánh giá RDBMS trước hoặc kiến trúc dùng nhiều kho dữ liệu theo ranh giới dịch vụ.

### Tình huống C — Dữ liệu đo từ cảm biến

**Nhu cầu:** nhận phép đo theo thiết bị, đọc dữ liệu trong 24 giờ gần nhất, xóa dữ liệu cũ sau thời hạn lưu, thỉnh thoảng tổng hợp theo phút.

**Đánh giá:** MongoDB time-series có thể phù hợp nếu tốc độ ghi, giữ liệu và truy vấn nằm trong khả năng của triển khai. Cần thiết kế metadata thiết bị, timestamp, retention và đo throughput/độ trễ. Khi nhu cầu chuyển sang tổng hợp xuyên nhiều năm và hàng nghìn chiều, nên đối chiếu với hệ time-series hoặc phân tích chuyên dụng. Chỉ mục TTL có thể hỗ trợ loại bỏ dữ liệu hết hạn trong những cấu hình phù hợp, nhưng việc xóa diễn ra bất đồng bộ, không phải cam kết xóa đúng từng giây.

## 10. Bảng so sánh theo trọng tâm nghiệp vụ

| Trọng tâm | MongoDB thường nổi bật khi | Giải pháp khác nên được đánh giá |
| --- | --- | --- |
| Dữ liệu nghiệp vụ dạng object | Aggregate rõ ràng, cấu trúc lồng nhau và truy cập theo object. | RDBMS nếu quan hệ và constraint xuyên nhiều thực thể là trung tâm. |
| Schema thay đổi | Có nhiều biến thể nhưng vẫn kiểm soát schema/version tốt. | RDBMS với JSON/JSONB cũng có thể đủ nếu hệ thống đã dựa mạnh vào SQL. |
| Giao dịch | Phần lớn ghi nằm trong một document, giao dịch chéo chỉ xuất hiện có chủ đích. | RDBMS khi nghiệp vụ liên tục cần transaction và khóa ngoại xuyên bảng. |
| Tìm kiếm | Tra cứu theo key, điều kiện/index và aggregation xác định. | Search engine khi relevance ranking và phân tích văn bản là trọng tâm. |
| Báo cáo | Tổng hợp vận hành vừa sức, có thể tiền tổng hợp. | Columnar OLAP/warehouse cho truy vấn phân tích lớn, nhiều phép join. |
| Quan hệ nhiều tầng | Quan hệ có giới hạn, đường truy cập cụ thể. | Graph DB khi duyệt cạnh/đường đi là tính năng cốt lõi. |
| Cache ngắn hạn | Có yêu cầu lưu trữ bền vững cùng logic document. | Key–value/in-memory store khi mục tiêu chính là cache và độ trễ tối thiểu. |

Bảng trên là gợi ý đặt vấn đề, không phải bảng xếp hạng hiệu năng. Một ứng dụng có thể kết hợp nhiều công cụ: ví dụ PostgreSQL cho giao dịch, MongoDB cho catalog tài liệu, search engine cho tìm kiếm và warehouse cho báo cáo. Đổi lại, kiến trúc đa kho dữ liệu cần đồng bộ sự kiện, xử lý dữ liệu đến muộn và theo dõi tính nhất quán giữa các hệ thống.

## 11. Những đánh đổi về vận hành và chi phí dễ bị bỏ quên

**Chất lượng dữ liệu.** Schema linh hoạt giúp triển khai nhanh nhưng yêu cầu kỷ luật dữ liệu: quy ước tên trường, kiểu trường, version, validation và chiến lược migration. Mỗi document “khác một chút” sẽ trở thành nợ kỹ thuật nếu ứng dụng không xác định tiêu chuẩn chung.

**Dung lượng và write amplification.** Embed hoặc sao chép trường giảm số lần đọc nhưng có thể tăng kích thước bản ghi. Nhiều index giúp truy vấn đa dạng hơn nhưng khiến mỗi lần ghi phải bảo trì thêm index. Cần đo cả dung lượng dữ liệu, chỉ mục, backup và lưu lượng đọc/ghi khi ước tính chi phí.

**Hiệu năng dưới tải.** Khối lượng 100.000 document với API đơn giản khác hẳn khối lượng tương tự có những mảng lớn, `$lookup` nhiều tầng và sắp xếp không có index. Cần thử bằng tỷ lệ đọc/ghi, phân phối kích thước document, cardinality và mức đồng thời sát thực tế.

**Khả năng khôi phục.** Replica set hỗ trợ tính sẵn sàng nhưng không thay cho backup, phục hồi theo thời điểm hoặc diễn tập restore. Kế hoạch vận hành cần xác định RPO/RTO, kiểm thử restore định kỳ và cách xử lý xóa/ghi nhầm.

**Bảo mật và tuân thủ.** Phải thiết lập xác thực, phân quyền tối thiểu, bảo mật kết nối, quản lý secrets, kiểm soát truy cập mạng và chính sách lưu/xóa dữ liệu. Dữ liệu cá nhân nhúng trong nhiều document hoặc snapshot có thể khó xóa đồng bộ hơn nếu thiếu thiết kế vòng đời dữ liệu.

**Phụ thuộc nền tảng.** Cần xem xét phiên bản, hình thức triển khai tự quản trị hay dịch vụ quản lý, các khả năng phụ thuộc nhà cung cấp, chi phí chuyển dữ liệu và nhu cầu đội ngũ về kỹ năng vận hành. Chi phí tổng thể không chỉ là tiền lưu trữ mỗi GB.

## 12. Quy trình đánh giá MongoDB cho một dự án thực tế

Thay vì chọn theo trào lưu, hãy thực hiện một đánh giá nhỏ dựa trên nghiệp vụ:

1. **Liệt kê 5–10 thao tác quan trọng nhất:** API đọc/ghi, filter, sort, aggregation, mức đồng thời và cam kết thời gian đáp ứng.
2. **Xác định invariant:** điều gì tuyệt đối không được sai, chẳng hạn không trừ tồn kho âm, không lập trùng giao dịch, không mất sự kiện đã xác nhận.
3. **Vẽ ranh giới aggregate:** dữ liệu nào thuộc cùng một đơn vị nhất quán và cùng vòng đời; dữ liệu nào phát triển độc lập.
4. **Phác thảo document và các reference:** nêu rõ trường trùng lặp, mảng có giới hạn, cách cập nhật và chiến lược migration.
5. **Thiết kế index dựa trên truy vấn:** ưu tiên filter/sort dùng thường xuyên, kiểm tra số index và tác động lên ghi.
6. **Dựng prototype có dữ liệu đại diện:** bao gồm dữ liệu lớn, phân phối lệch, trường thiếu, đồng thời và các thao tác lỗi/retry.
7. **Đo cả hiệu năng và tính đúng đắn:** p95/p99, throughput, tài nguyên, query plan, xung đột ghi, failover và kiểm tra dữ liệu sau retry.
8. **So sánh chi phí vận hành:** backup/restore, replication, sharding khi tăng trưởng, giám sát, quản trị schema và năng lực đội ngũ.
9. **Chọn theo bằng chứng:** ghi lại lý do MongoDB đáp ứng tốt hơn hoặc kém hơn các phương án khác đối với chính workload đã đo.

### Một mẫu quyết định ngắn

```text
Workload: catalog sản phẩm đa dạng thuộc tính
Truy cập chính: đọc theo productId; lọc theo sellerId/status/category
Đơn vị nhất quán: một sản phẩm và các thuộc tính của nó
Quan hệ tăng vô hạn: đánh giá, sự kiện và lịch sử thay đổi -> collection riêng
Index dự kiến: (sellerId, status, createdAt), các bộ lọc được dùng nhiều
Invariant: SKU duy nhất trong phạm vi seller, giá không âm, schema hợp lệ
Rủi ro: thuộc tính động khó lập index; dữ liệu trùng lặp; truy vấn tìm kiếm
Kiểm chứng: query plan, p95, tốc độ ghi, kích thước index, lỗi cập nhật
Quyết định: thử MongoDB cho catalog, so sánh với PostgreSQL JSONB
```

Mẫu này giúp làm rõ quyết định kiến trúc trước khi hệ thống chứa hàng triệu document. Không cần chứng minh MongoDB “nhanh hơn SQL” một cách chung chung; chỉ cần chứng minh hệ thống đáp ứng **truy vấn thực, invariant thực và giới hạn vận hành thực** của dự án.

## 13. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu chính xác hơn |
| --- | --- |
| “NoSQL nghĩa là không có schema.” | Schema vẫn tồn tại trong dữ liệu và ứng dụng; MongoDB hỗ trợ validation, nhưng đội ngũ phải thiết kế và quản trị nó. |
| “MongoDB không có join.” | Có `$lookup`; câu hỏi là tần suất và chi phí join có phù hợp với mô hình tài liệu hay không. |
| “MongoDB không có transaction.” | Có transaction nhiều document trong cấu hình được hỗ trợ; cần cân nhắc chi phí và xung đột. |
| “Dùng document thì luôn chỉ cần một query.” | Reference, aggregation và mảng lớn vẫn có thể yêu cầu nhiều truy vấn hoặc quét nhiều dữ liệu. |
| “MongoDB luôn nhanh hơn cơ sở dữ liệu quan hệ.” | Hiệu năng phụ thuộc truy vấn, index, mô hình dữ liệu, tải, phần cứng và cách triển khai. |
| “Có sharding là tự động mở rộng tốt.” | Hiệu quả sharding phụ thuộc shard key, phân bố tải và khả năng target truy vấn. |
| “Có replica là đã an toàn khỏi mất dữ liệu.” | Replication không thay thế backup/restore và không tự sửa lỗi dữ liệu do ứng dụng gây ra. |
| “Schema linh hoạt nên không cần migration.” | Khi contract API hoặc kiểu dữ liệu thay đổi, vẫn cần chiến lược tương thích và nâng cấp dữ liệu. |

Khi phải lựa chọn MongoDB, hãy đặt câu hỏi cuối cùng: **document có thực sự là ranh giới tự nhiên cho phần lớn thao tác của ứng dụng hay không?** Nếu câu trả lời là có, schema biến đổi có kiểm soát, truy vấn rõ ràng và đội ngũ sẵn sàng quản lý tính nhất quán, chỉ mục cùng vận hành, MongoDB là lựa chọn đáng thử. Nếu câu trả lời là không, đặc biệt khi nghiệp vụ xoay quanh quan hệ chặt, giao dịch nhiều thực thể và báo cáo SQL, một cơ sở dữ liệu quan hệ hoặc hệ thống chuyên dụng khác có thể đưa đến thiết kế đơn giản và dễ tin cậy hơn.
