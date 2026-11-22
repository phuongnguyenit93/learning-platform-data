# Chỉ mục trên trường, mảng hoặc đường dẫn và chi phí cập nhật trong cơ sở dữ liệu tài liệu

Một hệ quản trị cơ sở dữ liệu tài liệu (document database) cho phép lưu các đối tượng có cấu trúc linh hoạt: trường đơn, đối tượng lồng nhau, mảng giá trị và mảng tài liệu con. Tính linh hoạt đó giúp một tài liệu biểu diễn trọn vẹn thực thể nghiệp vụ, nhưng cũng đặt ra câu hỏi quan trọng: **làm sao tìm đúng tài liệu mà không phải quét toàn bộ tập dữ liệu, và phải trả giá bao nhiêu khi thêm hoặc thay đổi chỉ mục?**

Trong nhiều hệ document, **chỉ mục (index)** là cấu trúc bổ trợ giúp định vị tài liệu từ một hoặc nhiều giá trị trường. Trên MongoDB, chỉ mục thường được tổ chức bằng cấu trúc cây B-tree; tùy tính năng, còn có các loại chỉ mục chuyên dụng. Một chỉ mục có thể áp dụng cho trường đơn như `customerId`, đường dẫn lồng nhau như `shipping.city`, hoặc giá trị bên trong mảng như `items.sku`. Chỉ mục giúp giảm công đọc đối với truy vấn thích hợp, song làm tăng dung lượng lưu trữ, bộ nhớ hoạt động và công việc khi ghi.

Bài học dùng **MongoDB và cú pháp mongosh** làm ví dụ cụ thể. Các ý tưởng về đường dẫn, cấu trúc lồng nhau, cập nhật và chi phí chỉ mục có thể áp dụng rộng hơn, nhưng không mặc định mọi cơ sở dữ liệu tài liệu có cùng khả năng lập chỉ mục hay bộ tối ưu truy vấn giống MongoDB. Những số liệu minh họa trong bài là giả định để học cách suy luận, không phải kết quả benchmark thực tế.

## 1. Đặt câu hỏi về truy vấn trước khi tạo chỉ mục

Hãy giả định hệ thống bán hàng có collection `orders`. Mỗi đơn chứa dữ liệu nhận diện khách hàng, thời gian tạo, trạng thái, địa chỉ giao hàng và một danh sách sản phẩm tại thời điểm mua.

~~~javascript
// Một tài liệu minh họa trong collection orders.
{
  _id: "o1001",
  customerId: "c42",
  status: "PAID",
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  totalAmount: 580000,
  shipping: {
    city: "Da Nang",
    district: "Hai Chau",
    addressType: "HOME"
  },
  tags: ["fragile", "priority"],
  items: [
    { sku: "SKU-A", quantity: 1, unitPrice: 400000 },
    { sku: "SKU-B", quantity: 2, unitPrice: 90000 }
  ],
  payment: {
    method: "CARD",
    providerRef: "tx-8801"
  }
}
~~~

Ứng dụng đặt ra các truy vấn:

| Mã | Nhu cầu nghiệp vụ | Điều kiện / sắp xếp | Tần suất giả định |
|---|---|---|---|
| Q1 | Danh sách 20 đơn gần nhất của một khách | `customerId`, `createdAt DESC` | Cao |
| Q2 | Danh sách đơn đã thanh toán, mới nhất trước | `status`, `createdAt DESC` | Trung bình |
| Q3 | Lọc đơn giao đến một thành phố | `shipping.city`, có thể kèm `status` | Trung bình |
| Q4 | Lọc đơn có nhãn hàng dễ vỡ | `tags` chứa `fragile` | Thấp |
| Q5 | Tìm đơn chứa một sản phẩm cụ thể | `items.sku` | Trung bình |
| Q6 | Tìm đơn có cùng một dòng hàng thỏa cả SKU và số lượng | `items.sku` và `items.quantity` trong **cùng phần tử mảng** | Thấp |
| Q7 | Tra cứu đối soát từ mã thanh toán | `payment.providerRef` | Thấp nhưng yêu cầu đúng đắn cao |

Không thể chọn một chỉ mục duy nhất chỉ vì nó bao phủ nhiều tên trường. Một index chỉ có giá trị khi **thứ tự khóa, cách lọc, cách sắp xếp, mức chọn lọc và dữ liệu thực tế** phù hợp với truy vấn cần phục vụ. Vì thế, đầu ra đầu tiên nên là ma trận query pattern như trên, gồm cả tần suất và độ trễ mục tiêu.

Các câu hỏi cần ghi lại cho từng query:

- Điều kiện nào **luôn** có trong `WHERE`, điều kiện nào chỉ xuất hiện đôi khi?
- Có `sort`, `limit`, phân trang hoặc tìm khoảng thời gian không?
- Truy vấn trả một tài liệu, 20 tài liệu hay hàng chục nghìn tài liệu?
- Trường lọc nằm ở cấp cao nhất, bên trong object hay trong mảng?
- Giá trị trường có tính chọn lọc cao không, hay phần lớn tài liệu cùng chung một giá trị?
- Trường ấy được cập nhật bao nhiêu lần, mỗi lần cập nhật có ảnh hưởng đến bao nhiêu phần tử mảng?

## 2. Chỉ mục giúp đọc nhanh bằng cách nào?

Không có index phù hợp, hệ quản trị có thể phải duyệt rất nhiều tài liệu để tìm bản ghi thỏa điều kiện, thường thể hiện bằng bước `COLLSCAN` trong kế hoạch truy vấn MongoDB. Một index lưu giá trị khóa đã tổ chức cùng tham chiếu đến tài liệu tương ứng, giúp hệ quản trị tìm khu vực khóa liên quan và đọc một tập nhỏ hơn.

~~~mermaid
flowchart TD
    A["Truy vấn: customerId = c42"] --> B{"Có index hữu ích?"}
    B -->|Có| C["Tra cứu khóa trong index"]
    C --> D["Định vị các tài liệu phù hợp"]
    D --> E["Áp dụng điều kiện còn lại và trả kết quả"]
    B -->|Không| F["Quét nhiều tài liệu trong collection"]
    F --> E
~~~

Một trường hợp đơn giản:

~~~javascript
// Không có index trên customerId, truy vấn có thể quét nhiều tài liệu.
db.orders.find({ customerId: "c42" });

// Tạo index theo customerId để hỗ trợ truy vấn lọc bằng trường này.
db.orders.createIndex(
  { customerId: 1 },
  { name: "ix_orders_customer" }
);
~~~

Số `1` thể hiện thứ tự tăng dần của khóa trong chỉ mục; `-1` là giảm dần. Chỉ mục không tự bảo đảm truy vấn nhanh: nếu điều kiện khớp gần như toàn bộ collection, phải trả nhiều tài liệu, hoặc phải đọc thêm dữ liệu lớn, lợi ích có thể nhỏ hơn mong đợi. Bộ tối ưu truy vấn cũng có thể chọn collection scan khi nó ước tính phù hợp hơn.

**Index không phải bản sao đầy đủ của collection**. Nó là một cấu trúc dữ liệu bổ sung cần duy trì mỗi khi các giá trị mà index theo dõi thay đổi.

## 3. Chỉ mục trên trường đơn (single-field index)

Chỉ mục trường đơn là bước bắt đầu dễ hiểu nhất. Nó phù hợp khi ứng dụng thường xuyên lọc bằng một trường và tập kết quả đủ chọn lọc.

~~~javascript
db.orders.createIndex(
  { customerId: 1 },
  { name: "ix_customer" }
);

// Có thể dùng index customerId.
db.orders.find({ customerId: "c42" });

// Một trường index khác cho mã đối soát.
db.orders.createIndex(
  { "payment.providerRef": 1 },
  { name: "ix_payment_provider_ref" }
);
~~~

Trường có **cardinality cao** (nhiều giá trị phân biệt) thường tạo điều kiện cho truy vấn equality chọn lọc hơn trường chỉ có vài giá trị như `status` với `CREATED`, `PAID`, `CANCELLED`. Tuy nhiên, chỉ nhìn số giá trị phân biệt là chưa đủ: phân bố dữ liệu lệch, tỷ lệ query và các điều kiện đi kèm cũng tác động đến việc index có hữu ích hay không.

Một câu hỏi hay gặp: có nên tạo chỉ mục `{status: 1}`? Nếu 90% đơn có trạng thái `PAID`, truy vấn `{status: "PAID"}` trả gần hết collection, nên index này có thể ít giúp ích. Nhưng truy vấn `{status: "PAYMENT_FAILED"}` chỉ khớp 0,1% bản ghi thì cùng một trường có thể hữu ích hơn. Hãy đo từng kiểu giá trị và tính đến thao tác sort/limit.

Với `_id`, MongoDB tự tạo chỉ mục duy nhất mặc định cho collection thông thường. Tạo thêm chỉ mục sao chép y hệt mà không phục vụ mục đích mới thường chỉ tăng chi phí lưu trữ và cập nhật.

## 4. Chỉ mục ghép và thứ tự trường (compound index)

Khi truy vấn vừa lọc vừa sắp xếp, chỉ mục ghép thường có giá trị hơn nhiều chỉ mục trường đơn rời rạc. Với Q1, ứng dụng biết `customerId`, cần 20 đơn mới nhất và có thể dùng `_id` làm khóa phụ để bảo đảm thứ tự xác định nếu hai đơn cùng timestamp.

~~~javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "ix_customer_recent" }
);

db.orders.find({ customerId: "c42" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Thứ tự khóa được chọn có chủ ý:

1. `customerId` là equality filter, giúp tìm phạm vi đơn hàng của một khách.
2. `createdAt DESC` phù hợp việc trả đơn mới nhất trước.
3. `_id DESC` giúp quyết định thứ tự trong nhóm có cùng thời điểm và phục vụ cách phân trang ổn định hơn.

Đặt `createdAt` đứng đầu một index khác sẽ làm thay đổi phạm vi truy xuất: hệ thống có thể phải xem nhiều đơn của nhiều khách trước khi lọc đúng khách. Không thể suy ra rằng hai chỉ mục chứa cùng tập trường nhưng đảo thứ tự sẽ có chi phí tương đương.

### 4.1. Nguyên tắc tiền tố (prefix)

Index `{customerId: 1, createdAt: -1, _id: -1}` có thể hữu ích cho truy vấn theo `customerId` hoặc theo `customerId` kèm `createdAt`. Ngược lại, một truy vấn **chỉ** theo `createdAt` và không biết `customerId` thường không thể khai thác cùng đường sắp xếp toàn cục hiệu quả như index có `createdAt` đứng đầu.

| Truy vấn | Độ phù hợp với index `(customerId, createdAt DESC, _id DESC)` |
|---|---|
| `customerId = c42` | Có thể khai thác tiền tố |
| `customerId = c42`, lấy đơn mới nhất | Phù hợp với lọc và sort |
| `customerId = c42`, `createdAt >= t` | Có thể dùng phần khóa thời gian trong phạm vi khách |
| Chỉ lấy 20 đơn mới nhất của tất cả khách | Không có thứ tự thời gian toàn cục theo khóa này |
| Chỉ lọc `status = PAID` | Không phục vụ trực tiếp đường lọc chính |

Một mẹo xây index ghép là phân nhóm **Equality → Sort → Range (ESR)**, nhưng đây là hướng dẫn lựa chọn thứ tự ban đầu, không phải luật luôn đúng. Với range rất chọn lọc, mục tiêu sort hoặc cardinality cụ thể, thứ tự khác có thể tốt hơn; hãy xác nhận bằng explain và benchmark.

### 4.2. Hướng sắp xếp

Với compound index, hướng của các trường sort quan trọng. Một index có thể hỗ trợ đi xuôi hoặc ngược thứ tự khóa phù hợp; tuy nhiên, yêu cầu sắp xếp hỗn hợp ở nhiều trường phải tương thích với thứ tự index. Index `{a: 1, b: -1}` không tương đương cho mọi truy vấn với `{a: 1, b: 1}`.

Chỉ mục có thể giúp tránh một bước sort riêng trong kế hoạch truy vấn, nhưng còn phụ thuộc equality predicates, filter, collation và cách trình tối ưu chọn plan.

## 5. Chỉ mục trên đường dẫn lồng nhau (dotted path index)

Một tài liệu có thể có object lồng nhau, ví dụ:

~~~javascript
{
  _id: "o1002",
  shipping: {
    city: "Ha Noi",
    district: "Ba Dinh",
    recipient: {
      name: "Lan",
      verified: true
    }
  }
}
~~~

MongoDB cho phép tham chiếu trường sâu bằng **dotted path**:

~~~javascript
// Index trên một trường cụ thể trong object lồng nhau.
db.orders.createIndex(
  { "shipping.city": 1 },
  { name: "ix_shipping_city" }
);

db.orders.find({
  "shipping.city": "Ha Noi"
});
~~~

Dấu chấm chỉ rõ một đường dẫn đi vào object. Nó không mang nghĩa “tự động index mọi trường con”. Index `shipping.city` không tự trở thành index chuyên dụng cho `shipping.district` hay `shipping.recipient.verified`. Khi query cần thành phố và trạng thái, có thể thử index ghép:

~~~javascript
db.orders.createIndex(
  { "shipping.city": 1, status: 1, createdAt: -1 },
  { name: "ix_city_status_recent" }
);

db.orders.find({
  "shipping.city": "Ha Noi",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(30);
~~~

Với dữ liệu lồng nhau, cần hiểu cách query xử lý trường bị thiếu, giá trị `null` và kiểu dữ liệu khác nhau. Ví dụ, tài liệu không có `shipping.city` không tương đương tài liệu có `shipping.city: ""`. Cách chọn index cùng partial predicate, sparse option và logic query phải được kiểm tra theo kiểu dữ liệu thực, vì trường có thể không tồn tại ở một số phiên bản schema.

### 5.1. Đánh chỉ mục cả object hay một trường con?

Có khác biệt quan trọng giữa:

~~~javascript
db.orders.createIndex({ shipping: 1 });
db.orders.createIndex({ "shipping.city": 1 });
~~~

Index trên chính object `shipping` hữu ích cho những điều kiện phù hợp với **toàn bộ giá trị object**, kể cả ngữ nghĩa thứ tự trường khi so sánh object; nó không thay thế đường truy cập chuyên dụng cho thành phố. Index trên `shipping.city` nhắm trực tiếp vào truy vấn về thành phố. Do đó, “cứ index object cha là mọi trường con tự nhanh” là giả định sai.

## 6. Mảng scalar và chỉ mục multikey

Document thường chứa mảng:

~~~javascript
{
  _id: "o1001",
  tags: ["fragile", "priority", "gift"]
}
~~~

Khi tạo index trên một trường chứa mảng, MongoDB sử dụng **multikey index**. Ý tưởng: một document có thể đóng góp nhiều khóa index, tương ứng với các giá trị phần tử của mảng (chi tiết như loại bỏ khóa trùng lặp và cách tạo khóa phụ thuộc cấu trúc/index).

~~~javascript
db.orders.createIndex(
  { tags: 1 },
  { name: "ix_tags" }
);

db.orders.find({ tags: "fragile" });
~~~

Sơ đồ khái niệm:

~~~text
Document o1001
  tags = ["fragile", "priority", "gift"]
          |          |          |
          v          v          v
       fragile     priority     gift
          \          |          /
             tham chiếu -> o1001
~~~

Đây là **một document có thể xuất hiện thông qua nhiều giá trị khóa index**, không phải ba document mới. Nếu mảng có một triệu phần tử, hệ lưu trữ có nguy cơ phải quản lý số lượng khóa index rất lớn. Chi phí không chỉ ở một lần đọc, mà còn ở tạo index, thêm/xóa phần tử mảng, kích thước index và tác vụ bảo trì.

Mảng rất dài thường là dấu hiệu cần xem lại **ranh giới aggregate**: liệu một document có nên giữ toàn bộ lịch sử hay nên chia lịch sử thành các document riêng, collection khác hoặc các bucket có giới hạn?

### 6.1. Truy vấn một hay nhiều giá trị

~~~javascript
// Tài liệu có phần tử "gift" trong tags.
db.orders.find({ tags: "gift" });

// Có ít nhất một trong các nhãn được liệt kê.
db.orders.find({
  tags: { $in: ["gift", "priority"] }
});

// Phải có cả hai nhãn (theo ngữ nghĩa điều kiện $all).
db.orders.find({
  tags: { $all: ["gift", "priority"] }
});
~~~

Các truy vấn này không có cùng độ chọn lọc hay đường thực thi trong mọi bộ dữ liệu. Index có thể hỗ trợ tìm khóa ứng viên, nhưng truy vấn như `$all` có thể vẫn cần kiểm tra thêm điều kiện trên document. Đừng đánh giá hiệu năng chỉ dựa trên việc “có index tags”.

### 6.2. Multikey và tính duy nhất

Nếu tạo **unique multikey index**, ràng buộc unique được đánh giá **giữa các document** theo cách MongoDB xây khóa index. Nó không phải validator bảo đảm mọi phần tử trong mảng của **cùng một document** khác nhau. Ví dụ, một document chứa phần tử lặp trong mảng không được mặc định sẽ bị từ chối chỉ vì có unique multikey index. Muốn cấm lặp trong một mảng, cần thiết kế quy tắc dữ liệu/validation phù hợp.

## 7. Mảng tài liệu con và đường dẫn vào phần tử

Trong `orders`, mỗi đơn chứa mảng `items` gồm các object:

~~~javascript
{
  _id: "o1003",
  items: [
    { sku: "SKU-A", quantity: 1, unitPrice: 400000 },
    { sku: "SKU-B", quantity: 3, unitPrice: 90000 }
  ]
}
~~~

Ứng dụng có thể tìm mọi đơn chứa SKU cụ thể bằng dotted path qua mảng:

~~~javascript
db.orders.createIndex(
  { "items.sku": 1 },
  { name: "ix_items_sku" }
);

db.orders.find({
  "items.sku": "SKU-A"
});
~~~

Index trên `items.sku` là multikey khi `items` là mảng các object. Những giá trị SKU trong các phần tử khác nhau có thể tạo các khóa index liên quan tới cùng document.

Nếu một đơn có 3 dòng hàng, chi phí duy trì index khác với một đơn có 5.000 dòng hàng. Mỗi lần thêm, bỏ hoặc thay SKU của dòng hàng đều có khả năng thay đổi tập khóa index của document đó. Tuy nhiên, **không nên khẳng định chi phí cập nhật luôn bằng đúng số phần tử của mảng**: thuật toán cập nhật tùy engine, cấu trúc mảng và phần thay đổi; điều đúng cần theo dõi là index có thêm nhiều entry và việc chỉnh mảng có thể khiến write amplification tăng đáng kể.

### 7.1. Hai điều kiện có thể khớp ở hai phần tử khác nhau

Đây là điểm dễ sai về mặt **tính đúng đắn của query**. Xét document:

~~~javascript
{
  _id: "o1004",
  items: [
    { sku: "SKU-A", quantity: 1 },
    { sku: "SKU-B", quantity: 5 }
  ]
}
~~~

Truy vấn:

~~~javascript
db.orders.find({
  "items.sku": "SKU-A",
  "items.quantity": { $gte: 3 }
});
~~~

có thể khớp vì **một phần tử** chứa `SKU-A`, còn **phần tử khác** có `quantity >= 3`. Nó không bảo đảm có một dòng hàng SKU-A số lượng ít nhất 3.

Muốn hai điều kiện áp dụng cho **cùng một phần tử** của `items`, dùng `$elemMatch`:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 3 }
    }
  }
});
~~~

Với document `o1004` ở trên, query có `$elemMatch` không khớp. Đây không phải mẹo tối ưu thuần hiệu năng; nó là quy tắc diễn đạt chính xác yêu cầu nghiệp vụ.

### 7.2. Index ghép trong cùng mảng phần tử

Có thể xem xét index ghép trên hai đường dẫn của cùng mảng object:

~~~javascript
db.orders.createIndex(
  { "items.sku": 1, "items.quantity": 1 },
  { name: "ix_item_sku_quantity" }
);
~~~

Cần phân biệt hai tầng:

- **Ngữ nghĩa query:** `$elemMatch` ràng buộc cùng phần tử mảng.
- **Đường truy cập index:** bộ tối ưu có thể tận dụng ràng buộc đó để thu hẹp khoảng khóa index phù hợp, tùy biểu thức, thứ tự trường và kế hoạch được chọn.

Không phải cứ có index ghép là MongoDB mặc định hiểu hai điều kiện dotted path phải cùng một phần tử; nếu query không dùng `$elemMatch` đúng chỗ thì kết quả logic vẫn có thể rộng hơn mong muốn.

### 7.3. Hạn chế của compound multikey với nhiều mảng

Không thể tùy ý tạo một compound index gồm nhiều trường mảng độc lập trong cùng một document. Ví dụ một tài liệu có `tags` là mảng và `couponCodes` cũng là mảng; compound index trên cả hai có thể vi phạm hạn chế **parallel arrays** của MongoDB, vì sẽ phải biểu diễn rất nhiều tổ hợp khóa không phù hợp.

~~~javascript
// Dạng sau có thể không được phép với document có cả hai trường là mảng:
db.orders.createIndex({
  tags: 1,
  couponCodes: 1
});
~~~

Cần đọc giới hạn theo phiên bản và phân biệt **các đường dẫn chung một mảng object** với **hai mảng độc lập**. Nếu một index chỉ có thể tạo khi dữ liệu hiện tại chưa xuất hiện parallel arrays, cũng cần lưu ý khả năng các lần ghi về sau bị từ chối nếu đưa document vi phạm ràng buộc đó vào collection.

## 8. Multikey index không bảo toàn thứ tự phần tử mảng

Giả sử `items` giữ thứ tự mà khách hàng chọn sản phẩm. Việc index `items.sku` nhằm tìm theo SKU, **không biến index thành công cụ trả lại phần tử theo thứ tự ban đầu trong array**. Tương tự, `sort` trên trường mảng chịu quy tắc riêng về cách xác định giá trị sort và multikey index, không tương đương sort theo vị trí phần tử mảng.

Nếu nghiệp vụ cần “5 sự kiện mới nhất của một user” và số sự kiện tăng liên tục, mô hình nhúng một mảng sự kiện khổng lồ rồi index một trường con có thể không thích hợp. Một collection riêng với mỗi sự kiện là document, index ghép theo `userId` và `createdAt` có thể dễ mở rộng hơn.

Ví dụ mô hình thay thế:

~~~javascript
{
  _id: "event-10001",
  userId: "u42",
  occurredAt: ISODate("2026-11-14T08:20:00Z"),
  type: "LOGIN",
  payload: { deviceType: "mobile" }
}
~~~

~~~javascript
db.userEvents.createIndex(
  { userId: 1, occurredAt: -1, _id: -1 },
  { name: "ix_user_events_recent" }
);

db.userEvents.find({ userId: "u42" })
  .sort({ occurredAt: -1, _id: -1 })
  .limit(5);
~~~

Đánh đổi là tốn thêm document và có thể cần nhiều lần đọc hoặc cơ chế liên kết để lấy dữ liệu parent. Quyết định phụ thuộc việc đọc cùng nhau, số phần tử tối đa, yêu cầu nguyên tử và pattern tăng trưởng.

## 9. Đường dẫn động: wildcard index khi schema thay đổi

Một số hệ thống lưu thuộc tính mở rộng do người dùng định nghĩa:

~~~javascript
{
  _id: "p1001",
  category: "electronics",
  attributes: {
    color: "black",
    warrantyMonths: 24,
    screenSize: 13.3
  }
}

{
  _id: "p1002",
  category: "clothing",
  attributes: {
    color: "blue",
    material: "cotton",
    size: "M"
  }
}
~~~

Nếu liên tục phát sinh trường mới bên dưới `attributes`, việc dự đoán từng tên trường để tạo index riêng có thể khó. MongoDB hỗ trợ **wildcard index** để lập chỉ mục nhiều đường dẫn dưới một nhánh:

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "ix_product_attributes_wildcard" }
);
~~~

Ví dụ truy vấn:

~~~javascript
db.products.find({
  "attributes.material": "cotton"
});
~~~

Wildcard index hữu ích khi tập đường dẫn truy vấn biến động và không biết trước hết các trường. Nhưng nó có chi phí cập nhật/lưu trữ khi tài liệu có nhiều thuộc tính, không hỗ trợ mọi cách sort, lọc và kết hợp như một index ghép thiết kế riêng. Với một truy vấn quan trọng có mẫu ổn định, index chuyên biệt thường đáng được so sánh.

Hãy nhớ: **wildcard không giải quyết nhu cầu tìm kiếm mọi loại dữ liệu theo mọi cách**. Tìm toàn văn, tìm vector tương tự, tìm địa lý và các truy vấn phân tích lớn có loại chỉ mục/công nghệ riêng; không thể thay thế bằng dotted path index thông thường.

## 10. Partial và sparse index: chỉ ghi các mục cần quan tâm

Khi chỉ một phần tài liệu cần được truy vấn theo đường nhất định, việc đưa mọi document vào index có thể lãng phí. Có thể dùng **partial index** để giới hạn tập document đủ điều kiện tạo entry.

Ví dụ chỉ thường tìm các đơn `PAID` theo thành phố và thời gian:

~~~javascript
db.orders.createIndex(
  { "shipping.city": 1, createdAt: -1 },
  {
    name: "ix_paid_city_recent",
    partialFilterExpression: { status: "PAID" }
  }
);

db.orders.find({
  status: "PAID",
  "shipping.city": "Da Nang"
}).sort({ createdAt: -1 }).limit(20);
~~~

Index chỉ chứa tài liệu thỏa filter `status: "PAID"` theo ngữ nghĩa của partial filter. Bộ tối ưu thường chỉ có thể dùng partial index khi query bảo đảm phạm vi kết quả nằm trong tập đã được index; nếu query **không** giới hạn `status` như vậy, dùng index có thể bỏ sót tài liệu nên không được xem là đường truy cập đủ kết quả.

**Cần tính chi phí thay đổi trạng thái:** một document từ `CREATED` sang `PAID` sẽ bắt đầu thuộc partial index; từ `PAID` sang trạng thái khác có thể rời index. Dù trường `status` không xuất hiện trong key pattern, nó vẫn quyết định membership và có thể phát sinh cập nhật index.

**Sparse index** là một cơ chế khác, chủ yếu bỏ các document không có trường được index theo quy tắc sản phẩm. Không nên coi sparse và partial hoàn toàn đồng nghĩa, đặc biệt với `null`, trường thiếu và các điều kiện trên nhiều trường. Khi yêu cầu phức tạp, hãy thiết kế điều kiện partial tường minh và kiểm thử truy vấn liên quan.

### 10.1. Unique và điều kiện thiếu dữ liệu

Một index `unique` có thể dùng để bảo vệ tính duy nhất của mã tham chiếu trong phạm vi được thiết kế. Tuy nhiên, với đường dẫn tùy chọn, **trường thiếu hoặc `null` cần được xử lý có chủ đích**, vì ràng buộc unique trên index đơn thông thường có những ngữ nghĩa riêng đối với các giá trị đó.

Ví dụ minh họa yêu cầu chỉ các đơn đã có chuỗi mã thanh toán hợp lệ mới tham gia ràng buộc:

~~~javascript
db.orders.createIndex(
  { "payment.providerRef": 1 },
  {
    name: "ux_payment_provider_ref",
    unique: true,
    partialFilterExpression: {
      "payment.providerRef": { $type: "string" }
    }
  }
);
~~~

Index này chỉ diễn đạt tính duy nhất theo giá trị `providerRef` trong tập document khớp điều kiện. Nếu hệ có nhiều nhà cung cấp mà mã tham chiếu có thể trùng giữa các nhà cung cấp, phải xác định lại **phạm vi duy nhất** (chẳng hạn provider + ref). Chỉ mục unique cũng không tự giải quyết mọi vấn đề idempotency, giao dịch đa document hoặc race trong các hệ thống ngoài database.

## 11. Chi phí của chỉ mục đối với INSERT, UPDATE và DELETE

Mỗi index là một cấu trúc cần được duy trì. Tăng số index có thể làm giảm số document phải duyệt khi đọc, nhưng tăng lượng công việc trên đường ghi.

~~~mermaid
flowchart TD
    A["Ứng dụng ghi hoặc cập nhật document"] --> B["Kiểm tra ràng buộc và xác định thay đổi"]
    B --> C["Cập nhật bản ghi dữ liệu"]
    B --> D["Cập nhật các index bị ảnh hưởng"]
    D --> E["Thêm / xóa / đổi các index entry"]
    E --> F["Tăng I/O, CPU, bộ nhớ và lưu trữ"]
    C --> G["Hoàn tất thao tác theo bảo đảm ghi"]
    F --> G
~~~

Bảng tác động:

| Thao tác | Có thể phát sinh với index | Điểm cần quan sát |
|---|---|---|
| `INSERT` một document | Tạo entry ở các index liên quan; multikey có thể có nhiều entry trên mỗi document | Thời gian ghi, dung lượng index, tính chọn lọc |
| Cập nhật **trường được index** | Xóa/thay entry cũ, thêm entry mới; với partial index có thể đổi membership | Write latency, contention, compaction/log |
| Cập nhật **trường không được index** | Thông thường không cần đổi các index không liên quan, dù vẫn có chi phí sửa document | Document rewrite/relocation, write latency |
| Thêm phần tử vào mảng được index | Có thể thêm khóa multikey và thay đổi cấu trúc dữ liệu | Số phần tử, số khóa index, kích thước document |
| Xóa phần tử mảng | Có thể gỡ các index entry không còn tương ứng | Chi phí xóa/cập nhật, lịch sử dữ liệu |
| `DELETE` document | Loại bỏ entry của document ở các index | Số index, số giá trị multikey |
| Tạo index mới trên dữ liệu đã có | Phải xây index bằng cách xử lý collection hiện hữu | Thời gian build, CPU, RAM, I/O, ảnh hưởng tải |

Không nên diễn giải rằng **mọi UPDATE đều sửa mọi index**. Nếu thay `shipping.recipient.name` còn index chỉ nằm ở `customerId`, MongoDB có thể không phải sửa index `customerId`. Nhưng cập nhật document vẫn có chi phí riêng và các index có điều kiện membership, chẳng hạn partial index, cần được xét kỹ.

### 11.1. Write amplification

**Write amplification** là hiện tượng một thay đổi nhỏ ở cấp nghiệp vụ dẫn đến nhiều công việc đọc/ghi, tạo log hoặc cấu trúc lưu trữ hơn lượng dữ liệu thay đổi ban đầu. Chỉ mục là một trong các nguồn gây ra hiện tượng này.

Giả sử một collection có 1,5 triệu document và tám index. Khi tạo một đơn mới có 100 dòng hàng trong `items`, các index đơn thường cần entry phù hợp cho document mới; index multikey trên `items.sku` có thể phải đại diện rất nhiều SKU. Nếu mỗi đơn chỉ có 2–3 dòng hàng, profile khác hẳn. Số entry thực tế phụ thuộc các giá trị trùng, dữ liệu và kiểu index; phải đo thay vì lấy một công thức đơn giản “số index × số phần tử” làm kết quả chắc chắn.

Câu hỏi nên đặt ra là: lợi ích p95/p99 của một truy vấn đọc có xứng với **dung lượng index tăng, thời gian ghi tăng và chi phí bảo trì lâu dài** hay không?

### 11.2. Trường được cập nhật thường xuyên

Nếu `status` thay đổi nhiều lần trong vòng đời đơn, đặt `status` vào nhiều index sẽ có giá. Ngược lại `createdAt` thường được ghi một lần rồi bất biến, nên index theo `createdAt` thường không phải cập nhật do chính trường ấy sau khi tạo đơn. Đây là khác biệt nghiệp vụ cần dùng khi đánh giá chi phí.

Đường dẫn sâu cũng có thể bị cập nhật: sửa `shipping.city` ảnh hưởng index `shipping.city`; sửa `shipping.recipient.name` không nhất thiết ảnh hưởng index trên thành phố. Với array, việc thêm phần tử hoặc thay giá trị đã được index tác động đến số lượng khóa multikey và có thể đắt hơn một cập nhật scalar.

## 12. Chỉ mục và kích thước tài liệu

Một document lớn không tự sinh index lớn nếu chỉ index một trường scalar nhỏ, nhưng **index vào mảng dài, object có nhiều đường dẫn hoặc nhiều trường ghép** có thể làm số khóa index tăng đáng kể. Cần phân biệt:

1. **Kích thước document:** chi phí lưu và đọc nội dung gốc; cập nhật có thể khiến document lớn lên.
2. **Kích thước index:** tổng khóa và cấu trúc bổ trợ; phụ thuộc khóa index, số tài liệu, giá trị mảng, cardinality và loại index.
3. **Số index trên collection:** cùng một thao tác ghi có thể phải duy trì nhiều cấu trúc.
4. **Tính nóng của truy vấn và dữ liệu:** index hữu ích khi phần lớn cấu trúc cần thiết có thể được cache; khi index tăng quá lớn so với memory, đọc index có thể tốn I/O hơn.
5. **Chi phí trả kết quả:** index tìm đúng document nhưng kết quả vẫn có thể là document lớn, tốn network và decode.

Ví dụ, một query chỉ muốn `orderId`, `status` và `createdAt` nhưng API lại trả toàn bộ `items` có 3.000 phần tử; dù có index đúng, response vẫn có thể chậm. Cần sử dụng **projection** phù hợp:

~~~javascript
db.orders.find(
  { customerId: "c42" },
  { _id: 1, status: 1, createdAt: 1, totalAmount: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Projection giúp giảm lượng field trả về. Trong một số trường hợp, nếu index chứa đủ các trường truy vấn cần, MongoDB có thể thực hiện **covered query** mà không phải đọc document gốc. Tuy nhiên, cần xét index thực tế, `_id`, collation và giới hạn multikey; không thể mặc định projection có nghĩa truy vấn được cover.

## 13. Đọc execution plan để biết index có thực sự được dùng không

Trên MongoDB, có thể quan sát đường thực thi bằng `explain`. Ví dụ:

~~~javascript
db.orders.find({
  customerId: "c42"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

Những trường đáng chú ý trong kết quả (cấu trúc có thể thay đổi giữa các phiên bản và engine):

| Chỉ số hoặc stage | Câu hỏi cần trả lời |
|---|---|
| `IXSCAN` | Có thực sự quét index không, index nào được sử dụng? |
| `COLLSCAN` | Có đang quét nhiều document của collection không? |
| `FETCH` | Có cần lấy document gốc sau khi dùng index không? |
| `SORT` | Có cần bước sắp xếp bổ sung, hay thứ tự index đã đủ? |
| `nReturned` | Bao nhiêu kết quả được trả? |
| `totalKeysExamined` | Bao nhiêu khóa index được xem trong lần chạy? |
| `totalDocsExamined` | Bao nhiêu document được xem trong lần chạy? |
| `executionTimeMillis` | Thời gian engine ghi nhận trong ngữ cảnh phép giải thích truy vấn |

Một truy vấn trả 20 tài liệu nhưng duyệt 2 triệu index keys có thể chưa tối ưu, mặc dù stage là `IXSCAN`. Mục tiêu không phải chỉ nhìn thấy `IXSCAN`, mà là **giảm công đọc phải thực hiện để trả kết quả đúng trong workload thực**.

Tương tự, một query có `totalDocsExamined = 0` có thể là trường hợp cover, nhưng cần xem đủ kế hoạch và ngữ nghĩa để kết luận. `executionTimeMillis` của một lần `explain` không thay thế p95/p99 dưới tải đồng thời qua driver và mạng.

### 13.1. Các lệnh quan sát index

~~~javascript
// Liệt kê các index hiện có.
db.orders.getIndexes();

// Thống kê mức sử dụng index qua aggregation.
db.orders.aggregate([{ $indexStats: {} }]);

// Xem thống kê collection và kích thước index tổng thể.
db.orders.stats();

// Xem query plan với một điều kiện theo mảng.
db.orders.find({
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 2 }
    }
  }
}).explain("executionStats");
~~~

Các số liệu thống kê phản ánh phạm vi quan sát và thời gian của từng cơ chế. Chẳng hạn bộ đếm dùng index chỉ phản ánh khoảng thời gian kể từ khi thống kê được khởi tạo/reset theo quy tắc của hệ thống; một index ít được dùng trong giai đoạn ban ngày chưa chắc vô ích nếu phục vụ job quan trọng cuối tháng. Các công cụ quan sát cũng có chi phí và cần dùng phù hợp trong môi trường thật.

## 14. Vì sao nhiều index không đồng nghĩa với nhiều hiệu năng?

Thêm index trên mọi trường có thể làm tăng chi phí mà không cải thiện các truy vấn quan trọng. Một collection với 20 index vẫn có thể quét lớn nếu tất cả index đều thiếu thứ tự/tiền tố phù hợp cho query cụ thể.

Có những trường hợp hệ quản trị kết hợp nhiều index trong một query (*index intersection*), nhưng không nên mặc định nó luôn chọn cách này hoặc luôn hiệu quả bằng compound index được thiết kế đúng. Với query quan trọng, so sánh **một compound index theo access pattern** với **nhiều single-field index** bằng execution plan và dữ liệu thực.

Ví dụ Q1 và Q2 cần hai đường truy cập:

~~~javascript
// Q1: lịch sử theo khách.
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "ix_customer_recent" }
);

// Q2: đơn theo trạng thái.
db.orders.createIndex(
  { status: 1, createdAt: -1, _id: -1 },
  { name: "ix_status_recent" }
);
~~~

Hai index có chung các trường thời gian, nhưng phục vụ hai truy vấn với equality prefix khác nhau. Nếu Q2 cực hiếm hoặc dữ liệu đã có hàng loạt tài liệu trùng trạng thái, cần kiểm tra chi phí có xứng không. Không tự động tạo index thứ hai chỉ vì một code path có gọi `find({status:...})`.

Một **index thừa** có thể là index bị bao phủ bởi index ghép khác đối với workload cụ thể, nhưng quyết định loại bỏ cần kiểm tra mọi query, sort, collation, ràng buộc unique/partial/TTL và tình huống vận hành; không xóa index chỉ dựa vào tên tương tự.

## 15. Định nghĩa giả thuyết để đo lợi ích và chi phí cập nhật

Thiết kế index tốt phải được kiểm chứng bằng phép đo **cả đọc và ghi**. Ví dụ dùng 2 triệu đơn, 95% có 1–8 `items`, phần còn lại 20–200 `items`, một ít đơn có tới 1.000 phần tử. Các con số này **chỉ là bộ dữ liệu giả định** để tạo workload có phân bố lệch.

Ba phương án:

- **A — Baseline:** chỉ có index `_id` mặc định.
- **B — Read-focused:** có compound index cho Q1 và dotted path index `items.sku` cho Q5.
- **C — Read-heavy:** thêm index `status + createdAt`, `shipping.city + status` và compound multikey `items.sku + items.quantity`.

Các giả thuyết có thể bác bỏ:

> H1: Ở workload 500 truy vấn Q1 mỗi giây, index `(customerId, createdAt DESC, _id DESC)` sẽ giúp p95 đọc lịch sử thấp hơn baseline A, vì giảm quét dữ liệu và sắp xếp bên ngoài index.

> H2: Thêm nhiều index ở C sẽ tăng chi phí INSERT và cập nhật `status` so với B trong cùng cấu hình, dù Q2/Q3 có thể nhanh hơn.

> H3: Khi số phần tử `items` tăng từ 5 lên 500, chi phí cập nhật phần tử được index và kích thước index tăng đủ đáng kể để cần cân nhắc tách một phần dữ liệu.

Một kịch bản benchmark nên xác định rõ tỷ lệ query, tỷ lệ ghi, thời gian chạy, warm-up và điều kiện dữ liệu:

~~~yaml
experiment: order-index-tradeoff
dataset:
  orders: 2000000
  itemCountDistribution: "95%: 1-8; 4.9%: 20-200; 0.1%: up-to-1000"
  statuses: ["CREATED", "PAID", "SHIPPED", "CANCELLED"]
workload:
  readRequestsPerSecondTarget: 500
  writeRequestsPerSecondTarget: 100
  queryMix:
    Q1_customer_recent: 0.50
    Q2_status_recent: 0.20
    Q3_city_status: 0.10
    Q5_item_sku: 0.10
    Q6_same_item_condition: 0.10
  mutations:
    - create_order
    - update_status
    - append_item
    - modify_item_quantity
compare: ["A_baseline", "B_targeted_indexes", "C_more_indexes"]
measure:
  - query_p50_p95_p99
  - write_p50_p95_p99
  - operation_errors
  - achieved_throughput
  - keys_examined_and_docs_examined
  - index_size_and_build_time
  - cpu_memory_disk_io
~~~

Đây là cấu hình mô tả thí nghiệm, **không phải tệp chạy trực tiếp bởi một framework benchmark cụ thể**. Khi triển khai, cần chuẩn bị tool tạo tải, seed dữ liệu và telemetry phù hợp. Không lấy các con số giả định trên làm kết quả thực tế.

### 15.1. Quy trình đối chiếu

1. Xác định phần cứng, version MongoDB, topology/replica, cấu hình cache, driver và dữ liệu gốc.
2. Nạp tập dữ liệu có số phần tử mảng và phân bố khách hàng thực tế hoặc mô phỏng hợp lý; xác định rõ hot customers và trường thiếu.
3. Chạy baseline sau warm-up; ghi p50/p95/p99, error rate, CPU, RAM, I/O và throughput thực đạt.
4. Tạo từng nhóm index, theo dõi **thời gian xây index** và tác động đối với hệ thống trong lúc build.
5. Chạy lại cùng workload; lặp nhiều lần để phân biệt chênh lệch ổn định với dao động ngẫu nhiên.
6. Ghi thêm số liệu của `INSERT`, cập nhật trường index, cập nhật trường không index và cập nhật mảng dài.
7. Kiểm tra query plan và so sánh chi phí index trên disk/memory; rút ra kết luận trong phạm vi phép thử.

Không kết luận chỉ từ một truy vấn đơn lẻ trên 100 bản ghi. Nếu tốc độ tạo tải thấp hơn mục tiêu do load generator bị nghẽn, phải báo cả **offered load** và **achieved throughput**; không mặc định hệ thống đã chịu được tải định trước.

### 15.2. Bảng báo cáo minh họa

| Chỉ số giả định | A | B | C | Ý nghĩa cần xem |
|---|---:|---:|---:|---|
| Q1 p95 | 520 ms | 65 ms | 70 ms | B/C có lợi cho Q1 |
| Q5 p95 | 390 ms | 55 ms | 52 ms | Index `items.sku` có lợi cho Q5 |
| Q2 p95 | 420 ms | 415 ms | 75 ms | C cải thiện Q2 |
| INSERT p95 | 12 ms | 18 ms | 31 ms | Thêm index có thể tăng chi phí tạo document |
| Update `status` p95 | 9 ms | 10 ms | 22 ms | Nhiều index trên status tăng chi phí ghi |
| Dung lượng index bổ sung | 0 GiB | 1.8 GiB | 4.1 GiB | C tiêu tốn nhiều không gian hơn |

**Toàn bộ số trong bảng chỉ là kết quả giả định để tập diễn giải**, không phải kết quả đo MongoDB hoặc mức tốc độ cam kết. Kết luận nếu đo thật phải kèm điều kiện tải, số lần lặp, độ biến thiên, số lỗi và các metric bổ trợ; có thể C hợp lý nếu Q2 là luồng nghiệp vụ chính, nhưng không xứng đáng nếu Q2 rất hiếm.

## 16. Cập nhật mảng và đồng thời: xem xét tính đúng đắn

Chỉ mục giúp tìm tài liệu; nó không tự bảo đảm thao tác sửa một phần tử mảng đúng đích. Ví dụ muốn tăng số lượng của SKU-A trong đơn `o1001`:

~~~javascript
db.orders.updateOne(
  {
    _id: "o1001",
    items: { $elemMatch: { sku: "SKU-A" } }
  },
  {
    $inc: { "items.$.quantity": 1 }
  }
);
~~~

Đây là ví dụ positional `$` nhắm tới phần tử đầu tiên phù hợp của mảng trong ngữ cảnh query thích hợp. Nếu trong nghiệp vụ một đơn không được có hai dòng cùng SKU, **bất biến đó cần được quy định và kiểm tra riêng**; index trên `items.sku` không tự cấm SKU lặp trong một document.

Khi cần cập nhật nhiều phần tử có điều kiện, MongoDB hỗ trợ cơ chế array filters trong các phiên bản phù hợp:

~~~javascript
db.orders.updateOne(
  { _id: "o1001" },
  { $set: { "items.$[line].unitPrice": 95000 } },
  {
    arrayFilters: [{ "line.sku": "SKU-B" }]
  }
);
~~~

Thao tác cập nhật **trong một document** có tính nguyên tử ở phạm vi document theo bảo đảm của MongoDB, nhưng cập nhật cùng lúc `orders` và một collection `inventory` là vấn đề phạm vi nhiều document, có thể cần transaction hoặc thiết kế nghiệp vụ bù trừ tùy yêu cầu. Các trường được index trong `items` có thể yêu cầu cập nhật index; đừng đánh giá hiệu năng write chỉ bằng kết quả `matchedCount`.

### 16.1. Thay thế cả document có thể làm tăng chi phí

Một pattern đọc JSON vào ứng dụng, sửa một trường rồi `replaceOne` toàn bộ document có thể khiến thao tác và truyền dữ liệu lớn hơn nhiều so với `$set`, `$inc` hoặc `$push` phù hợp. Với thay đổi cạnh tranh, còn có nguy cơ ghi đè thay đổi của client khác nếu thiếu predicate phiên bản/điều kiện. Chỉ mục có thể giúp tìm document nhưng không giải quyết lost update.

Ví dụ optimistic concurrency theo phiên bản:

~~~javascript
db.orders.updateOne(
  { _id: "o1001", version: 7 },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 }
  }
);
~~~

Nếu không khớp bản ghi, ứng dụng phải xử lý trường hợp document không tồn tại hoặc version đã đổi, không mặc định retry vô hạn. Có cần index riêng trên `version` không? Khi query đã biết `_id` duy nhất, một index bổ sung trên `version` thường không cần thiết cho ví dụ này; hãy hiểu điều kiện truy vấn trước khi thêm index.

## 17. Những lưu ý khi vận hành index

Tạo index trên collection nhỏ trong môi trường học thường nhanh. Với production có hàng chục triệu tài liệu, **xây, thay hoặc xóa index là thay đổi vận hành cần lên kế hoạch**. Việc build index có thể tiêu thụ CPU, RAM, I/O và ảnh hưởng ứng dụng; khả năng chạy song song với ghi và các giới hạn tùy phiên bản MongoDB, topology và cấu hình.

Các việc nên ghi trong một phiếu thay đổi:

| Hạng mục | Nội dung cần nêu |
|---|---|
| Query cần tối ưu | Mã query, người sử dụng, tần suất và SLO |
| Index đề xuất | Key pattern, order, tên, unique/partial/collation nếu có |
| Dữ liệu đầu vào | Số document, tỷ lệ trường thiếu, độ dài mảng, phân bố giá trị |
| Lợi ích kỳ vọng | Giảm keys/docs examined, tránh sort, hạ p95/p99 |
| Chi phí | Dung lượng, thời gian build, tăng write latency và backup/recovery |
| Triển khai | Cửa sổ thay đổi, giám sát, điều kiện dừng |
| Khôi phục | Khi nào drop/hide index, tác động đến query, trình tự khôi phục |
| Kiểm chứng | Kết quả explain và số liệu tải trước/sau |

Một số phiên bản MongoDB hỗ trợ **hidden indexes** để thử ảnh hưởng tới việc chọn query plan trước khi xóa, nhưng cần kiểm tra chính xác tính năng của phiên bản. Xóa index không phải bước mặc định sau khi thấy bộ đếm sử dụng thấp; index có thể hỗ trợ job định kỳ hoặc ràng buộc quan trọng.

Giới hạn số index, kích thước key, kiểu kết hợp multikey, đặc điểm index trên array và hỗ trợ query có thể khác theo phiên bản. Không chép một con số giới hạn từ tài liệu sản phẩm khác hoặc phiên bản khác.

### 17.1. Khi collection được phân mảnh (sharding)

Trong cụm sharded, index ở collection và **shard key** là hai thiết kế liên quan nhưng khác vai trò. Một query có index tốt vẫn có thể phải gửi đến nhiều shard nếu không có điều kiện định tuyến phù hợp. Chi phí tổng cộng lúc đó gồm mạng và điều phối giữa shard. Unique index cũng có ràng buộc theo shard key và topology tùy phiên bản. Vì vậy, với một collection đã sharded, cần đánh giá song song **định tuyến query**, **phân bố ghi** và **index cục bộ**, không chỉ đọc một execution plan trên môi trường một node.

## 18. Lỗi thường gặp khi lập chỉ mục trường, mảng và đường dẫn

| Nhầm lẫn | Vì sao sai | Cách xử lý |
|---|---|---|
| “Document linh hoạt nên index tự phát hiện mọi trường” | Index vẫn phải được định nghĩa hoặc dùng tính năng cụ thể | Liệt kê query pattern và tạo index có mục tiêu |
| “Index trên object cha đủ cho mọi trường con” | Đường dẫn `shipping.city` khác giá trị object `shipping` | Tạo dotted path index cho truy vấn cần |
| “Index mảng giống index scalar: một document một entry” | Multikey có thể có nhiều khóa từ một document | Đo số phần tử và chi phí index theo phân bố dữ liệu |
| “Hai điều kiện trên `items.sku` và `items.quantity` luôn cùng phần tử” | Có thể khớp ở hai object khác nhau trong mảng | Dùng `$elemMatch` khi cần ràng buộc cùng phần tử |
| “Có compound index thì MongoDB tự liên kết điều kiện cùng phần tử mảng” | Query semantics không đổi vì có index | Viết điều kiện đúng, rồi xem bounds/plan |
| “Thêm index cho mọi trường sẽ luôn nhanh hơn” | Tăng chi phí ghi và lưu trữ; nhiều index không đúng tiền tố | Chọn theo tải và đo trước/sau |
| “Query dùng IXSCAN tức là đã tối ưu” | Có thể quét rất nhiều khóa hoặc FETCH rất nhiều document | Xem `keysExamined`, `docsExamined`, `nReturned`, latency |
| “Projection chắc chắn là covered query” | Có thể cần FETCH, nhất là với multikey và field ngoài index | Đọc execution plan |
| “Không query một index tuần này thì xóa được” | Có job định kỳ/ràng buộc ít dùng nhưng quan trọng | Xem toàn vòng vận hành và ý nghĩa index |
| “Chỉ đo SELECT, không cần đo UPDATE” | Index ảnh hưởng INSERT, DELETE, update indexed fields và array | Benchmark cả đường đọc và ghi |
| “Một mảng cứ tăng mãi mà có index là ổn” | Document, multikey và thao tác mảng có giới hạn, chi phí tăng | Đặt giới hạn hoặc tách thực thể liên quan |
| “Cột thiếu và `null` có cùng ý nghĩa với mọi index” | Missing/null/partial/sparse có ngữ nghĩa riêng | Kiểm tra schema, predicate và trường hợp thiếu |

## 19. Bài thực hành: từ yêu cầu đến index có bằng chứng

**Đề bài:** bạn xây dịch vụ quản lý đơn hàng MongoDB. Bộ dữ liệu có khách hàng thường và một nhóm khách hàng mua hàng rất nhiều; có đơn chỉ chứa một sản phẩm, có đơn chứa hàng trăm sản phẩm; `shipping` có thể thiếu ở đơn hàng số.

### Phần A — Thiết kế index

1. Viết truy vấn lấy 20 đơn mới nhất của một khách hàng, dùng `createdAt` và `_id` để có thứ tự ổn định. Đề xuất compound index và giải thích vì sao `customerId` đứng đầu.
2. Viết truy vấn đơn đã thanh toán theo thành phố, sắp theo thời gian. Đề xuất index trên dotted path cùng các trường khác, rồi giải thích trường hợp có thể không cần index riêng.
3. Tạo một index trên `tags`. Nêu lý do đây là multikey index khi dữ liệu là mảng.
4. Tạo index `items.sku` và truy vấn tìm đơn chứa SKU-A.
5. Tạo một document có hai dòng hàng: SKU-A số lượng 1, SKU-B số lượng 5. So sánh query hai dotted paths thông thường với query dùng `$elemMatch` để tìm SKU-A số lượng ít nhất 3.
6. Đề xuất cách xử lý khi mỗi đơn có 10.000 dòng hàng, tránh chỉ trông chờ vào index mảng.

### Phần B — Đo và giải thích

Thực hiện theo môi trường MongoDB thử nghiệm đang sử dụng:

~~~javascript
// 1. Xem index hiện có.
db.orders.getIndexes();

// 2. Chạy explain cho đường đọc theo khách.
db.orders.find({ customerId: "c42" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

// 3. Xem thống kê sử dụng index.
db.orders.aggregate([{ $indexStats: {} }]);

// 4. Quan sát thống kê tập dữ liệu.
db.orders.stats();
~~~

Sau đó trả lời:

- Khi chưa có index phù hợp, query plan cho thấy engine đọc bao nhiêu document?
- Sau khi thêm index, `totalKeysExamined` và `totalDocsExamined` thay đổi ra sao? Có stage `SORT` hay không?
- Có khác biệt về p95/p99 khi đo nhiều request đồng thời qua application/driver không?
- Khi thêm 500 dòng vào `items` của một số đơn, index size và update latency biến đổi thế nào?
- Một index ghép thêm có cải thiện query quan trọng đủ để bù thời gian build, RAM, disk và write latency không?

### Phần C — Tình huống thiết kế

Giả sử bảng đơn hàng có ba API:

~~~text
GET /customers/{id}/orders?limit=20
GET /orders?city=DaNang&status=PAID&limit=20
GET /orders?sku=SKU-A&minQuantity=3
~~~

Hãy viết ra ba query MongoDB tương ứng. Với API thứ ba, cần bảo đảm SKU và số lượng thuộc **cùng dòng hàng**, không được dùng hai điều kiện array path độc lập nếu điều đó làm kết quả sai.

Thiết kế một index cho mỗi API nếu có lý do đo đạc, rồi mô tả cách bạn kiểm tra index nào được dùng, chi phí cập nhật khi đơn thay đổi và khi nào phải quay lại mô hình dữ liệu.

## 20. Cách suy luận khi chọn index cho mô hình tài liệu

Trình tự làm việc hữu ích nhất là:

1. **Đọc nghiệp vụ và query pattern.** Xác định equality, range, sort, limit và điều kiện về cùng phần tử mảng.
2. **Xác định cấu trúc tài liệu.** Trường scalar, nested object, mảng scalar, mảng object hay đường dẫn động có tính chất index khác nhau.
3. **Chọn khóa index có mục tiêu.** Dùng single-field, compound, dotted path, multikey hoặc partial/wildcard khi có lý do cụ thể.
4. **Đo đường đọc.** Dùng execution plan, số document/key được duyệt và p95/p99 dưới tải thực.
5. **Đo đường ghi.** Xem INSERT, UPDATE, DELETE, thao tác mảng, dung lượng index và ảnh hưởng build/maintenance.
6. **Điều chỉnh mô hình nếu cần.** Nếu mảng tăng không giới hạn hoặc phải lập quá nhiều index để phục vụ các truy vấn đối nghịch, cân nhắc chia thực thể, tạo projection đọc riêng hoặc chuyển một phần workload sang công cụ phù hợp.

Một index tốt không chỉ làm truy vấn chạy nhanh trên vài document ví dụ. Nó phải **phục vụ đúng ngữ nghĩa truy vấn, có chi phí cập nhật chấp nhận được và giữ được hiệu quả khi tài liệu, mảng và lưu lượng cùng tăng**.
