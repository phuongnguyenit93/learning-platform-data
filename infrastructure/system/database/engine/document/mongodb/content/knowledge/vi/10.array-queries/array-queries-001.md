# So khớp toàn bộ mảng và so khớp từng phần tử trong MongoDB

## 1. Vì sao truy vấn mảng dễ gây nhầm lẫn?

Một document MongoDB có thể chứa trường kiểu mảng (*array*) với các phần tử đơn giản như string, number hoặc các document lồng nhau. Mảng rất hữu ích để biểu diễn danh sách nhãn của sản phẩm, điểm số qua nhiều lần kiểm tra, các dòng hàng của một đơn đặt hàng hoặc các thuộc tính bổ sung của một thực thể.

Tuy nhiên, câu truy vấn “tìm document có mảng phù hợp” có ít nhất ba ý nghĩa khác nhau:

1. **Toàn bộ mảng bằng một danh sách cho trước:** đúng số phần tử, đúng giá trị và đúng thứ tự.
2. **Mảng có chứa một hoặc nhiều giá trị nhất định:** có thể có phần tử bổ sung, thứ tự không quan trọng.
3. **Có một phần tử riêng lẻ thỏa đồng thời nhiều điều kiện:** điều kiện phải áp dụng lên **cùng một phần tử**, không được ghép kết quả từ hai phần tử khác nhau.

MongoDB cung cấp các cách viết khác nhau để diễn đạt từng ý nghĩa. Chọn sai toán tử không chỉ làm truy vấn chậm, mà còn có thể trả về dữ liệu **không đúng về mặt nghiệp vụ**.

Ví dụ, một sản phẩm có:

~~~javascript
{
  _id: "P100",
  tags: ["sale", "laptop"],
  scores: [72, 91],
  variants: [
    { color: "black", stock: 0 },
    { color: "white", stock: 8 }
  ]
}
~~~

Các yêu cầu sau là khác nhau:

- “Nhãn **chính xác** là `["sale", "laptop"]`.”
- “Có nhãn `"sale"`.”
- “Có **cả** nhãn `"sale"` và `"laptop"`, không cần quan tâm thứ tự.”
- “Có ít nhất một điểm nằm trong khoảng 80–90.”
- “Có biến thể **màu đen và còn hàng**.”

Với yêu cầu cuối, document ví dụ **không đáp ứng**: biến thể đen hết hàng, còn biến thể trắng mới có hàng. Một truy vấn chỉ kiểm tra “có color=black” và “có stock>0” ở hai phần tử khác nhau sẽ cho kết quả sai. Đây là lý do cần hiểu rõ `$elemMatch`.

### Bảng định hướng nhanh

| Ý định truy vấn | Cú pháp tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Mảng đúng `["red", "blue"]`, theo thứ tự | `{ tags: ["red", "blue"] }` | So khớp mảng nguyên vẹn trong trường hợp mảng phẳng. |
| Có phần tử `"red"` | `{ tags: "red" }` | Phần tử mảng bằng giá trị cho trước; cũng có thể khớp trường scalar. |
| Có phần tử thuộc một trong nhiều giá trị | `{ tags: { $in: ["red", "blue"] } }` | Logic **OR** giữa các giá trị. |
| Mảng chứa cả hai giá trị | `{ tags: { $all: ["red", "blue"] } }` | Logic **AND** về sự hiện diện của các giá trị. |
| Mảng có chính xác hai phần tử | `{ tags: { $size: 2 } }` | Kiểm tra số phần tử, không kiểm tra nội dung. |
| Một phần tử thỏa đồng thời nhiều điều kiện | `{ scores: { $elemMatch: { $gte: 80, $lt: 90 } } }` | Các điều kiện áp dụng trên cùng một phần tử. |
| Một object trong mảng có `sku=A` và `qty>=2` | `{ items: { $elemMatch: { sku: "A", qty: { $gte: 2 } } } }` | Các trường phải thuộc cùng một object con. |

Các ví dụ dưới đây sử dụng `mongosh`, tên collection riêng và bộ dữ liệu cố định để phân biệt những trường hợp rất giống nhau về cú pháp.

---

## 2. Chuẩn bị dữ liệu mẫu

Giả sử collection `arrayQueryLesson` **đang trống** trước khi thực hiện ví dụ. Mỗi document mô tả một mặt hàng với nhãn, điểm đánh giá thử nghiệm và các dòng tồn kho:

~~~javascript
db.arrayQueryLesson.insertMany([
  {
    _id: 1,
    name: "A",
    tags: ["red", "blue"],
    scores: [65, 85, 94],
    items: [
      { sku: "A", qty: 1 },
      { sku: "B", qty: 3 }
    ]
  },
  {
    _id: 2,
    name: "B",
    tags: ["blue", "red"],
    scores: [75, 92],
    items: [
      { sku: "A", qty: 3 }
    ]
  },
  {
    _id: 3,
    name: "C",
    tags: ["red", "blue", "green"],
    scores: [82],
    items: [
      { sku: "B", qty: 1 }
    ]
  },
  {
    _id: 4,
    name: "D",
    tags: ["red"],
    scores: [88, 90],
    items: []
  },
  {
    _id: 5,
    name: "E",
    tags: [],
    scores: [],
    items: []
  },
  {
    _id: 6,
    name: "F",
    // Không có trường tags.
    scores: [70],
    items: [
      { sku: "A", qty: 1 },
      { sku: "B", qty: 2 }
    ]
  },
  {
    _id: 7,
    name: "G",
    // Cố ý dùng scalar để minh họa ảnh hưởng của schema không đồng nhất.
    tags: "red",
    scores: 88,
    items: { sku: "A", qty: 2 }
  },
  {
    _id: 8,
    name: "H",
    tags: ["red", "red"],
    scores: [50],
    items: []
  }
]);
~~~

Tóm tắt các trường quan trọng:

| `_id` | `tags` | `scores` | `items` |
| --- | --- | --- | --- |
| 1 | `["red", "blue"]` | `[65, 85, 94]` | A:1, B:3 |
| 2 | `["blue", "red"]` | `[75, 92]` | A:3 |
| 3 | `["red", "blue", "green"]` | `[82]` | B:1 |
| 4 | `["red"]` | `[88, 90]` | Rỗng |
| 5 | `[]` | `[]` | Rỗng |
| 6 | Không tồn tại | `[70]` | A:1, B:2 |
| 7 | Scalar `"red"` | Scalar `88` | Một object A:2 |
| 8 | `["red", "red"]` | `[50]` | Rỗng |

Document số 7 cố ý **khác schema**; mục đích là làm rõ rằng một số toán tử có thể khớp cả scalar, trong khi các toán tử thực sự yêu cầu mảng thì không. Trong ứng dụng thật, nên dùng schema validation để tránh sự không đồng nhất này nếu field được định nghĩa luôn là mảng.

Để hiển thị kết quả theo thứ tự ID, có thể thêm `.sort({ _id: 1 })` vào câu lệnh `find()`. Nếu không có `sort()`, **không dựa vào thứ tự trả về** như một hợp đồng của truy vấn.

---

## 3. So khớp toàn bộ mảng: bằng đúng danh sách cho trước

### 3.1. Array equality

Khi truyền một array làm giá trị so sánh:

~~~javascript
db.arrayQueryLesson.find(
  { tags: ["red", "blue"] },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Trong bộ dữ liệu mảng phẳng ở trên, kết quả là **`_id: 1`**.

- `_id: 1` có đúng hai phần tử `"red"`, `"blue"` theo thứ tự này.
- `_id: 2` có hai phần tử giống nhau nhưng **ngược thứ tự**, nên không khớp.
- `_id: 3` có thêm `"green"`, nên không khớp.
- `_id: 8` có hai phần tử đều là `"red"`, nên không khớp.

**Kích thước, giá trị và thứ tự** đều quan trọng đối với phép so khớp một mảng nguyên vẹn. Đây là lựa chọn khi nghiệp vụ cần chính xác một danh sách có thứ tự, chẳng hạn một chuỗi bước xử lý được xác định rõ.

Cách viết tường minh với `$eq`:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $eq: ["red", "blue"] }
});
~~~

Trong các ví dụ mảng một chiều, hai cách viết trên diễn đạt cùng ý định. Lưu ý với **mảng lồng mảng**, ngữ nghĩa equality của MongoDB có thể còn khớp một phần tử mảng con bằng array được truy vấn; phần 10 trình bày cách tránh nhầm lẫn trong trường hợp đó. Vì vậy, không nên coi phép array equality là một công cụ xác minh mọi cấu trúc BSON đệ quy một cách tuyệt đối.

### 3.2. Có cùng các giá trị nhưng ngược thứ tự vẫn khác

~~~javascript
db.arrayQueryLesson.find({ tags: ["blue", "red"] });
~~~

Kết quả trên dữ liệu mẫu là **`_id: 2`**, không phải `_id: 1`. MongoDB không tự sắp xếp phần tử trước khi so sánh array equality.

Nếu nghiệp vụ coi tag là **tập hợp không có thứ tự**, phép so sánh chính xác cả thứ tự có thể không phù hợp. Khi đó cân nhắc `$all` hoặc thiết lập quy tắc chuẩn hóa thứ tự trước khi lưu.

### 3.3. Mảng con không tự bằng mảng lớn

~~~javascript
db.arrayQueryLesson.find({
  tags: ["red"]
});
~~~

Kết quả là **`_id: 4`**, vì field của document này đúng là mảng một phần tử `["red"]`. Điều kiện không có nghĩa “mảng chứa giá trị red”. Để hỏi về **phần tử**, phải viết theo cách khác ở mục tiếp theo.

Trong các hệ thống lưu tag, đây là một nhầm lẫn thường gặp:

~~~javascript
// Không đúng với ý định "có nhãn red":
db.products.find({ tags: ["red"] });

// Đúng với ý định "có nhãn red":
db.products.find({ tags: "red" });
~~~

### 3.4. Mảng các document: equality còn phụ thuộc cấu trúc object

Với mảng các embedded document, equality yêu cầu phần tử document có nội dung phù hợp; phép so sánh bằng một embedded document có thể nhạy với **thứ tự các field trong document**, đồng thời với thứ tự các phần tử mảng.

~~~javascript
db.arrayQueryLesson.find({
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 3 }
  ]
});
~~~

Trong tập mẫu, câu này tìm `_id: 1`. Nhưng nếu chỉ cần “có một dòng SKU A với số lượng ít nhất 1”, so sánh toàn bộ mảng là quá chặt và dễ hỏng khi document thêm field mới như `unit` hoặc `warehouse`.

Thông thường, với mảng object, nên hỏi theo **thuộc tính của phần tử**, dùng dotted path hoặc `$elemMatch`, thay vì ràng buộc cấu trúc cả mảng.

---

## 4. So khớp một phần tử bằng giá trị scalar

Truy vấn đơn giản nhất để tìm các document mà `tags` **có chứa** giá trị `"red"` là:

~~~javascript
db.arrayQueryLesson.find(
  { tags: "red" },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Kết quả theo dataset: **`_id: 1, 2, 3, 4, 7, 8`**.

Vì sao?

- Với các document 1, 2, 3, 4 và 8, `tags` là array chứa ít nhất một phần tử `"red"`.
- Với document 7, `tags` là **scalar** bằng `"red"`, nên phép equality vẫn khớp.
- Document 5 có mảng rỗng, document 6 thiếu field, nên không khớp.

Đây là khác biệt quan trọng: **`{ tags: "red" }` không khẳng định field phải có kiểu array.** Nó có thể khớp giá trị scalar hoặc phần tử của một mảng.

Nếu schema quy định `tags` luôn là array và được đảm bảo bởi validator, sự linh hoạt này không gây vấn đề. Nếu dữ liệu cũ lẫn cả scalar và array, truy vấn có thể trả thêm những document ngoài ý định.

### 4.1. Dùng `$elemMatch` để buộc có phần tử trong mảng

~~~javascript
db.arrayQueryLesson.find({
  tags: { $elemMatch: { $eq: "red" } }
});
~~~

Điều kiện này yêu cầu `tags` là mảng có **ít nhất một phần tử** bằng `"red"`; document số 7 với scalar `"red"` không khớp. Kết quả là **`_id: 1, 2, 3, 4, 8`**.

Với một điều kiện membership đơn giản, `$elemMatch` có thể dài dòng hơn cần thiết. Nhưng nó hữu ích nếu cần buộc ngữ nghĩa array và đặc biệt hữu ích khi nhiều điều kiện phải áp dụng lên cùng phần tử.

### 4.2. Phần tử ở vị trí xác định

Nếu câu hỏi là “phần tử đầu tiên phải bằng red”, dùng vị trí mảng:

~~~javascript
db.arrayQueryLesson.find({
  "tags.0": "red"
});
~~~

Kết quả là **`_id: 1, 3, 4, 8`**. Document 2 có red ở vị trí thứ hai nên bị loại. Chỉ số mảng bắt đầu từ **0**.

Trong MongoDB, path `"tags.0"` truy cập phần tử đầu tiên của trường `tags`. Điều kiện này không tương đương với kiểm tra membership và cũng không so khớp toàn bộ mảng.

**Khi nào cần vị trí?** Khi thứ tự phần tử mang ý nghĩa nghiệp vụ rõ ràng: bước đầu của quy trình, mục ưu tiên, thứ tự người nhận hoặc slot cố định. Với tag không có thứ tự nghiệp vụ, truy vấn theo chỉ số thường là dấu hiệu mô hình hoặc API đang gắn thêm ý nghĩa không cần thiết.

---

## 5. `$in`: mảng có ít nhất một giá trị trong tập lựa chọn

Giả sử cần tìm tài liệu có nhãn `"green"` **hoặc** `"blue"`:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $in: ["green", "blue"] }
});
~~~

Kết quả là **`_id: 1, 2, 3`**.

Ở đây `$in` diễn đạt logic **OR**:

~~~text
tags chứa "green"
        OR
tags chứa "blue"
~~~

Vì document số 1 chứa blue, nó được chọn dù không chứa green. Document số 3 chứa cả green và blue cũng được chọn.

Có thể viết điều kiện OR dài hơn:

~~~javascript
db.arrayQueryLesson.find({
  $or: [
    { tags: "green" },
    { tags: "blue" }
  ]
});
~~~

Với các giá trị equality đơn giản, `$in` thường dễ đọc hơn. Nhưng khi những nhánh OR chứa điều kiện phức tạp, `$or` có thể phù hợp hơn.

### 5.1. `$in` không yêu cầu tất cả giá trị phải xuất hiện

~~~javascript
db.arrayQueryLesson.find({
  tags: { $in: ["red", "blue"] }
});
~~~

Điều kiện trên tìm **ít nhất một** trong hai màu, nên cả document chỉ có `["red"]` vẫn được chọn. Nó không giải quyết yêu cầu “có đồng thời red và blue”.

Để diễn đạt AND về membership, dùng `$all`.

---

## 6. `$all`: có đủ các giá trị, không quan tâm thứ tự

~~~javascript
db.arrayQueryLesson.find({
  tags: { $all: ["red", "blue"] }
});
~~~

Kết quả: **`_id: 1, 2, 3`**.

- Document 1 có red và blue đúng thứ tự được liệt kê.
- Document 2 có cả hai dù thứ tự đảo ngược.
- Document 3 có đủ red và blue, đồng thời có thêm green.
- Document 4 chỉ có red nên không đủ.
- Document 7 là scalar `"red"` và không phải mảng chứa đủ hai phần tử.

Sự khác nhau giữa các toán tử:

~~~text
tags = ["blue", "red", "green"]

So khớp ["red", "blue"]       -> KHÔNG (khác cả thứ tự, kích thước)
$in  ["red", "blue"]           -> CÓ (ít nhất một giá trị)
$all ["red", "blue"]           -> CÓ (có đủ cả hai giá trị)
$size 2                       -> KHÔNG (mảng có 3 phần tử)
~~~

### 6.1. `$all` không kiểm tra số lần lặp của một giá trị

~~~javascript
db.arrayQueryLesson.find({
  tags: { $all: ["red", "red"] }
});
~~~

Dùng cùng giá trị hai lần trong `$all` **không buộc mảng phải có hai phần tử red**. Một mảng `["red"]` cũng đáp ứng điều kiện về sự hiện diện của red. Nếu nghiệp vụ đòi hỏi **hai lần xuất hiện** của cùng một giá trị, cần thiết kế phép đếm theo mảng hoặc schema phù hợp.

Điều này cũng có nghĩa `$all` nên được hiểu là “có đủ các giá trị được yêu cầu”, **không phải phép so sánh hai đa tập có đếm trùng lặp**.

### 6.2. Kết hợp `$all` với `$size`

Giả sử cần đúng **hai phần tử**, có cả red và blue, nhưng không quan trọng thứ tự:

~~~javascript
db.arrayQueryLesson.find({
  tags: {
    $all: ["red", "blue"],
    $size: 2
  }
});
~~~

Trong bộ dữ liệu phẳng này, kết quả là **`_id: 1, 2`**. Điều kiện `$all` yêu cầu hai giá trị khác nhau; `$size: 2` loại document 3 có thêm green.

Tuy nhiên, nếu nhu cầu thật sự là một danh sách có thứ tự xác định, hãy dùng array equality. Đừng ghép nhiều toán tử không cần thiết để mô phỏng một phép so sánh đã có cú pháp rõ ràng.

---

## 7. `$size`: số lượng phần tử, không phải điều kiện giá trị

Truy vấn mọi document có đúng hai nhãn:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $size: 2 }
});
~~~

Kết quả: **`_id: 1, 2, 8`**.

Document số 8 có hai nhãn giống nhau `["red", "red"]` nên vẫn hợp lệ với `$size: 2`. Toán tử này **không quan tâm giá trị hay tính duy nhất**.

Truy vấn mảng rỗng:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $size: 0 }
});
~~~

Kết quả: **`_id: 5`**. Document số 6 thiếu `tags` và document số 7 có `tags` là scalar, nên không phải mảng rỗng.

### 7.1. `$size` không phải toán tử so sánh khoảng

Không viết:

~~~javascript
// Không phải cú pháp $size hợp lệ để diễn đạt "ít nhất 2 phần tử":
db.arrayQueryLesson.find({
  tags: { $size: { $gte: 2 } }
});
~~~

`$size` trong query nhận **số nguyên chính xác**, không nhận biểu thức `$gte` theo cách này.

Nếu schema bảo đảm trường luôn là array, có thể dùng biểu thức aggregation để tính kích thước và so sánh:

~~~javascript
db.arrayQueryLesson.find({
  $expr: {
    $gte: [
      {
        $size: {
          $cond: [
            { $isArray: "$tags" },
            "$tags",
            []
          ]
        }
      },
      2
    ]
  }
});
~~~

Trong ví dụ, `$isArray` và `$cond` bảo vệ các document thiếu trường hoặc chứa scalar. Nếu bỏ bảo vệ và gọi `$size` trên một giá trị không phải array, truy vấn có thể gặp lỗi.

Với ứng dụng thường xuyên lọc theo kích thước mảng, có thể cân nhắc lưu trường `tagCount` được cập nhật đồng bộ. Nhưng khi đó cần xử lý mọi đường thêm/xóa phần tử, retry và migration để bộ đếm không lệch dữ liệu thực.

### 7.2. Hiệu năng của `$size`

Một index multikey thông thường **không trực tiếp tối ưu phần điều kiện `$size`**. MongoDB có thể sử dụng các điều kiện khác trong cùng truy vấn để thu hẹp tập document, rồi kiểm tra độ dài mảng. Nếu phần lớn request chỉ tìm “mảng có ít nhất N phần tử”, hãy đo query plan và cân nhắc materialized count hoặc cấu trúc lưu trữ khác khi thực sự cần.

---

## 8. Nhiều điều kiện trên mảng số: cùng phần tử hay khác phần tử?

Đây là ví dụ quan trọng nhất để hiểu `$elemMatch`.

Yêu cầu: **“Có ít nhất một điểm vừa lớn hơn 80 vừa nhỏ hơn 90.”**

### 8.1. Cách viết có thể khớp hai phần tử khác nhau

~~~javascript
db.arrayQueryLesson.find({
  scores: {
    $gt: 80,
    $lt: 90
  }
});
~~~

Đối với trường array, MongoDB có thể đánh giá `$gt: 80` ở **một phần tử** và `$lt: 90` ở **phần tử khác**. Vì vậy, truy vấn này có thể khớp document số 2:

~~~javascript
{ _id: 2, scores: [75, 92] }
~~~

Trong đó:

- `92 > 80` là đúng.
- `75 < 90` là đúng.
- **Không có điểm nào** đồng thời lớn hơn 80 và nhỏ hơn 90.

Document số 2 **không đáp ứng ý định nghiệp vụ**, dù biểu thức truy vấn thiếu `$elemMatch` có thể tìm thấy nó.

Truy vấn trên còn có thể khớp document số 7, nơi `scores` là scalar `88`, vì bản thân giá trị 88 thỏa hai phép so sánh.

### 8.2. Cách viết đúng khi yêu cầu cùng một phần tử

~~~javascript
db.arrayQueryLesson.find({
  scores: {
    $elemMatch: {
      $gt: 80,
      $lt: 90
    }
  }
});
~~~

Kết quả trên dữ liệu mẫu: **`_id: 1, 3, 4`**.

| `_id` | `scores` | Có điểm trong khoảng (80,90)? | Với `$elemMatch` |
| --- | --- | --- | --- |
| 1 | `[65, 85, 94]` | 85 | Khớp |
| 2 | `[75, 92]` | Không có | Không khớp |
| 3 | `[82]` | 82 | Khớp |
| 4 | `[88, 90]` | 88 | Khớp |
| 5 | `[]` | Không | Không khớp |
| 6 | `[70]` | Không | Không khớp |
| 7 | Scalar `88` | Không phải array | Không khớp |
| 8 | `[50]` | Không | Không khớp |

`$elemMatch` yêu cầu có **ít nhất một phần tử trong array** thỏa đồng thời mọi điều kiện bên trong. Phần tử ấy có thể nằm ở bất kỳ vị trí nào.

### 8.3. Các biên của khoảng

Các toán tử so sánh:

| Toán tử | Ý nghĩa |
| --- | --- |
| `$gt: 80` | Lớn hơn 80, **không bao gồm** 80. |
| `$gte: 80` | Lớn hơn hoặc bằng 80. |
| `$lt: 90` | Nhỏ hơn 90, **không bao gồm** 90. |
| `$lte: 90` | Nhỏ hơn hoặc bằng 90. |

Nếu yêu cầu “từ 80 đến 90, bao gồm hai đầu”, phải viết:

~~~javascript
db.arrayQueryLesson.find({
  scores: {
    $elemMatch: {
      $gte: 80,
      $lte: 90
    }
  }
});
~~~

Đừng để lỗi biểu diễn khoảng bị che bởi việc truy vấn mảng có hay không có `$elemMatch`.

---

## 9. Mảng embedded document: dotted path và `$elemMatch`

Mỗi phần tử của `items` trong ví dụ là một object có `sku` và `qty`. Một yêu cầu thường gặp là:

> “Tìm các document có **cùng một dòng hàng** mang `sku = "A"` và `qty >= 2`.”

### 9.1. Cách viết dotted path có thể ghép các phần tử khác nhau

~~~javascript
db.arrayQueryLesson.find({
  "items.sku": "A",
  "items.qty": { $gte: 2 }
});
~~~

Truy vấn này có thể khớp **`_id: 1, 2, 6, 7`**.

Xét document số 1:

~~~javascript
{
  _id: 1,
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 3 }
  ]
}
~~~

- Điều kiện `"items.sku": "A"` đúng với **phần tử thứ nhất**.
- Điều kiện `"items.qty": { $gte: 2 }` đúng với **phần tử thứ hai**.
- Không có dòng hàng SKU A với qty ít nhất 2.

Tương tự, document số 6 có A:1 và B:2; nó vẫn có thể khớp hai điều kiện dotted path nhưng không đạt yêu cầu trên cùng một dòng.

Document 7 còn cho thấy dotted path có thể đi vào **một object scalar**, không chỉ phần tử array.

### 9.2. Gói điều kiện bằng `$elemMatch`

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
});
~~~

Kết quả đúng cho yêu cầu này: **`_id: 2`**.

- Document 2 có phần tử `{ sku: "A", qty: 3 }`.
- Document 1 và 6 có SKU A nhưng số lượng của chính dòng A đều chỉ là 1.
- Document 7 chứa `items` dưới dạng object scalar chứ không phải array, nên `$elemMatch` không khớp.

Đây là ngữ nghĩa chính xác:

~~~text
Tồn tại một phần tử x trong items sao cho:
    x.sku == "A"
        AND
    x.qty >= 2
~~~

`$elemMatch` không bắt buộc tất cả phần tử đều phù hợp; chỉ cần **một phần tử** thỏa cả hai điều kiện.

### 9.3. Một điều kiện thì dotted path thường đủ

Nếu chỉ cần “có dòng hàng SKU A”:

~~~javascript
db.arrayQueryLesson.find({
  "items.sku": "A"
});
~~~

Đây là truy vấn ngắn gọn và phù hợp khi không cần đảm bảo nhiều điều kiện trên cùng phần tử, với điều kiện schema được hiểu đúng. Nếu muốn chỉ khớp khi `items` là array, có thể dùng:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $elemMatch: { sku: "A" }
  }
});
~~~

Với bộ dữ liệu, câu thứ hai loại document 7 vì `items` không phải mảng. MongoDB không tự sửa schema không đồng nhất; ứng dụng nên xác định kiểu field ngay từ lúc thiết kế.

### 9.4. Truy vấn với object có nhiều field

Giả sử dòng hàng có cấu trúc:

~~~javascript
{
  sku: "A",
  qty: 2,
  warehouse: { city: "HCM", zone: "A1" },
  status: "READY"
}
~~~

Có thể kết hợp các field bên trong cùng phần tử:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 },
      status: "READY",
      "warehouse.city": "HCM"
    }
  }
});
~~~

Dotted path `"warehouse.city"` lúc này được hiểu tương đối với **object con đang được kiểm tra** trong `$elemMatch`. Tất cả điều kiện đều phải đúng với cùng dòng hàng.

---

## 10. Khi cần hai phần tử khác nhau cùng tồn tại

`$elemMatch` yêu cầu **một phần tử thỏa nhiều điều kiện**. Nhưng có những yêu cầu khác:

> “Một đơn hàng phải có ít nhất một dòng SKU A, và ít nhất một dòng SKU B với số lượng từ 2 trở lên.”

Hai điều kiện được phép thuộc **hai phần tử khác nhau**. Có thể viết bằng `$and` chứa hai `$elemMatch`:

~~~javascript
db.arrayQueryLesson.find({
  $and: [
    {
      items: {
        $elemMatch: { sku: "A" }
      }
    },
    {
      items: {
        $elemMatch: {
          sku: "B",
          qty: { $gte: 2 }
        }
      }
    }
  ]
});
~~~

Kết quả: **`_id: 1, 6`**.

- Document 1 có A:1 và B:3.
- Document 6 có A:1 và B:2.
- Document 2 chỉ có A:3, không có B.
- Document 7 chứa một object scalar, không phải mảng.

Trong trường hợp thích hợp, `$all` cũng chấp nhận nhiều biểu thức `$elemMatch`:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $all: [
      { $elemMatch: { sku: "A" } },
      { $elemMatch: { sku: "B", qty: { $gte: 2 } } }
    ]
  }
});
~~~

Hai cách viết biểu đạt sự tồn tại của hai nhóm điều kiện. Phần tử đáp ứng điều kiện thứ nhất và phần tử đáp ứng điều kiện thứ hai có thể là những phần tử khác nhau. Nếu một phần tử đồng thời đáp ứng cả hai nhóm điều kiện, MongoDB cũng không bắt buộc phải chọn hai phần tử phân biệt; khi nghiệp vụ yêu cầu **hai đối tượng khác nhau theo ID**, cần ràng buộc thêm theo định danh hoặc mô hình dữ liệu phù hợp.

### 10.1. Không trộn lẫn hai yêu cầu

So sánh:

~~~javascript
// Một dòng phải vừa là A vừa có qty >= 2:
{
  items: {
    $elemMatch: { sku: "A", qty: { $gte: 2 } }
  }
}

// Có một dòng A và một dòng B qty >= 2:
{
  $and: [
    { items: { $elemMatch: { sku: "A" } } },
    { items: { $elemMatch: { sku: "B", qty: { $gte: 2 } } } }
  ]
}
~~~

Ý định nghiệp vụ quyết định cấu trúc truy vấn. Việc mọi điều kiện đều xuất hiện trong một biểu thức JSON không có nghĩa chúng đều áp dụng lên cùng một phần tử.

---

## 11. Mảng lồng mảng và đường dẫn truy cập

Đôi khi một field chứa **mảng của các mảng**, chẳng hạn các dòng điểm theo từng lớp học hoặc các nhóm tọa độ. Khi đó cần phân biệt:

- **Mảng bên ngoài:** danh sách nhóm.
- **Mảng bên trong:** phần tử cũng có kiểu array.
- **Phần tử scalar:** giá trị số/chuỗi nằm trong mảng trong cùng.

Ví dụ:

~~~javascript
db.matrixExamples.insertMany([
  {
    _id: "M1",
    matrix: [
      [1, 2],
      [3, 4]
    ]
  },
  {
    _id: "M2",
    matrix: [
      [1, 3],
      [2, 4]
    ]
  }
]);
~~~

Nếu cần kiểm tra hàng đầu tiên bằng `[1, 2]`, có thể sử dụng chỉ số phần tử:

~~~javascript
db.matrixExamples.find({
  "matrix.0": [1, 2]
});
~~~

Câu này tìm document có **mảng con tại vị trí 0** phù hợp với giá trị mảng cho trước, theo ngữ nghĩa equality.

Nếu cần kiểm tra **toàn bộ cấu trúc hai chiều**, so sánh mảng ở mức gốc có thể hữu ích:

~~~javascript
db.matrixExamples.find({
  matrix: [
    [1, 2],
    [3, 4]
  ]
});
~~~

Tuy vậy, MongoDB có quy tắc array equality có thể khớp cả **phần tử mảng con** bằng giá trị array được truy vấn. Khi thiết kế schema cho mảng lồng sâu hoặc cần xác minh cấu trúc tuyệt đối, hãy đặt điều kiện tại đúng path, hoặc dùng biểu thức aggregation kiểm tra rõ cả kiểu, độ dài và cấu trúc. Không suy luận từ ví dụ mảng phẳng sang mọi kiểu mảng lồng nhau.

### 11.1. Mảng document bên trong document

Ví dụ một đơn hàng có nhiều gói giao, mỗi gói có các dòng sản phẩm:

~~~javascript
{
  _id: "ORDER-1",
  shipments: [
    {
      carrier: "FAST",
      packages: [
        { sku: "A", qty: 1 },
        { sku: "B", qty: 2 }
      ]
    },
    {
      carrier: "SLOW",
      packages: [
        { sku: "A", qty: 3 }
      ]
    }
  ]
}
~~~

Yêu cầu “có một shipment của hãng FAST **chứa trong chính shipment đó** package SKU A” cần bảo toàn ranh giới từng shipment:

~~~javascript
db.orders.find({
  shipments: {
    $elemMatch: {
      carrier: "FAST",
      packages: {
        $elemMatch: {
          sku: "A"
        }
      }
    }
  }
});
~~~

Nếu tách `"shipments.carrier": "FAST"` và `"shipments.packages.sku": "A"` thành hai điều kiện độc lập, chúng có thể được đáp ứng bởi **hai shipment khác nhau**, gây kết quả sai cho ràng buộc cùng shipment.

---

## 12. Mảng rỗng, field không tồn tại, `null` và giá trị scalar

Một trong những nguồn lỗi khó phát hiện là ứng dụng gộp các trạng thái khác nhau:

~~~javascript
{ _id: 1, tags: [] }
{ _id: 2, tags: null }
{ _id: 3 }                  // thiếu tags
{ _id: 4, tags: "red" }      // scalar
{ _id: 5, tags: ["red"] }    // array
~~~

Các biểu diễn này **không đồng nghĩa**.

### 12.1. Mảng rỗng

Để tìm field có mảng rỗng:

~~~javascript
db.collection.find({
  tags: { $size: 0 }
});
~~~

Trong dữ liệu mẫu, kết quả là `_id: 5`. Không dùng điều kiện `{ tags: null }` với ý định “mảng không có phần tử”: MongoDB có quy tắc riêng khi so khớp `null` và field thiếu.

### 12.2. Field tồn tại

~~~javascript
db.arrayQueryLesson.find({
  tags: { $exists: true }
});
~~~

Trả về document có field `tags`, kể cả mảng rỗng hoặc scalar. Trên bộ dữ liệu mẫu, nó gồm **`_id: 1, 2, 3, 4, 5, 7, 8`**, không gồm document 6.

`$exists` chỉ nói field có mặt; nó **không khẳng định field là array, có phần tử hay có giá trị non-null**.

### 12.3. Phủ định membership

~~~javascript
db.arrayQueryLesson.find({
  tags: { $ne: "red" }
});
~~~

Với dữ liệu mẫu, câu này tìm **`_id: 5, 6`**. Nó khớp những document mà `tags` **không chứa** phần tử red, và cũng bao gồm document **thiếu field tags**.

Tương tự:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $nin: ["red", "blue"] }
});
~~~

`$nin` thường khớp document không có giá trị nào thuộc danh sách, **bao gồm field thiếu**. Đây có thể không phải ý định của một bộ lọc “sản phẩm có tag khác red/blue”. Nếu cần field thực sự tồn tại, hãy kết hợp điều kiện về presence hoặc kiểu field phù hợp.

### 12.4. Chỉ lấy document mà field là mảng

Khi schema không ổn định, cần phân biệt array và scalar:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $type: "array" }
});
~~~

Trong bộ dữ liệu, điều kiện này tìm document **`_id: 1, 2, 3, 4, 5, 8`**. Document số 7 có `tags` là string nên không được chọn. Trong các ứng dụng có thể kiểm soát đầu vào, dùng schema validator để bảo đảm kiểu dữ liệu sẽ đơn giản hóa mọi truy vấn phía sau.

### 12.5. Phủ định trên mảng document cần diễn đạt cẩn thận

Yêu cầu “không có dòng hàng nào có `sku=A` và `qty>=2`” có thể dùng `$not` bao lấy `$elemMatch`:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $not: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 2 }
      }
    }
  }
});
~~~

Điều kiện tìm những document **không tồn tại một phần tử mảng** thỏa cặp ràng buộc. Nó có thể khớp cả document thiếu `items` hoặc chứa giá trị không phải array. Nếu nghiệp vụ yêu cầu `items` phải là một mảng hợp lệ, cần thêm ràng buộc schema hoặc điều kiện kiểu field phù hợp.

---

## 13. So khớp embedded document chính xác hay chỉ một phần trường?

Xét:

~~~javascript
{
  _id: "ORDER-2",
  items: [
    {
      sku: "A",
      qty: 2,
      unitPriceMinor: 120000
    }
  ]
}
~~~

Nếu tìm phần tử object bằng equality trực tiếp:

~~~javascript
db.orders.find({
  items: {
    sku: "A",
    qty: 2
  }
});
~~~

Điều kiện object equality yêu cầu phần tử có **embedded document tương ứng chính xác**, nên object chứa thêm `unitPriceMinor` có thể không khớp. Trật tự field trong embedded document cũng có thể quan trọng khi so sánh chính xác.

Nếu chỉ quan tâm SKU và số lượng, nên viết:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: 2
    }
  }
});
~~~

Với `$elemMatch`, phần tử có thể có thêm `unitPriceMinor`, `discount` hay `warehouse` mà vẫn phù hợp. Truy vấn này bám sát **điều kiện nghiệp vụ**, ít phụ thuộc sự mở rộng schema hơn.

Cách viết dotted path:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": 2
});
~~~

vẫn có nguy cơ ghép hai phần tử khác nhau nếu đơn có nhiều item. Chỉ khi ý định là “có SKU A ở đâu đó và có một dòng qty 2 ở đâu đó”, hai dotted path độc lập mới diễn đạt đúng.

### 13.1. Phần tử có nhiều kiểu dữ liệu

MongoDB cho phép mảng chứa các kiểu BSON khác nhau nếu schema không cấm:

~~~javascript
{
  _id: "MIXED-1",
  values: [10, "10", null, { number: 10 }]
}
~~~

Điều kiện `{ values: 10 }` và `{ values: "10" }` không phải hai cách biểu diễn tương đương. Với truy vấn khoảng, kiểu BSON và *type bracketing* ảnh hưởng kết quả; không nên mong MongoDB tự ép mọi string số thành number.

Nếu domain yêu cầu mảng toàn số, hãy validate đầu vào và định nghĩa schema nhất quán. Một mảng vừa string vừa number dễ gây sai trong lọc, sắp xếp và aggregation.

---

## 14. Chỉ mục đa khóa (*multikey index*) cho truy vấn mảng

Khi tạo index trên một field chứa array, MongoDB sử dụng **multikey index**, lập các index key từ phần tử mảng theo quy tắc của index. Điều này giúp các truy vấn membership không nhất thiết phải quét toàn collection.

Ví dụ:

~~~javascript
db.arrayQueryLesson.createIndex({ tags: 1 });

db.arrayQueryLesson.find({
  tags: "red"
}).explain("executionStats");
~~~

Một query planner có thể chọn index để tìm các document chứa red. Tuy nhiên, chỉ mục không tự làm mọi truy vấn mảng có hiệu năng tối ưu: số lượng phần tử, tính chọn lọc, số document phải fetch và điều kiện sắp xếp đều ảnh hưởng.

### 14.1. Compound multikey index cho mảng document

~~~javascript
db.arrayQueryLesson.createIndex({
  "items.sku": 1,
  "items.qty": 1
});
~~~

Đây là một index ghép trên **hai trường con của cùng mảng items** trong schema mẫu. Nó có thể hỗ trợ điều kiện theo SKU và số lượng:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
}).explain("executionStats");
~~~

`$elemMatch` không chỉ thể hiện ràng buộc nghiệp vụ, mà trong những điều kiện thích hợp còn giúp MongoDB **kết hợp giới hạn index** dành cho các predicate phải thuộc cùng một phần tử mảng. Với các điều kiện dotted path độc lập, query planner có thể không được phép giao các index bounds theo cách đó vì điều kiện có thể khớp ở những phần tử khác nhau.

Không nên suy luận rằng tạo index này thì query chắc chắn không phải đọc document: các ràng buộc multikey, projection và query plan thực tế sẽ quyết định có cần FETCH hay không.

### 14.2. Những điểm cần theo dõi

| Chỉ số/khía cạnh | Câu hỏi cần trả lời |
| --- | --- |
| `nReturned` | Số document thực sự trả về? |
| `totalKeysExamined` | Đã duyệt bao nhiêu entry index? |
| `totalDocsExamined` | Đã đọc/kiểm tra bao nhiêu document? |
| `IXSCAN` / `COLLSCAN` | Có sử dụng index hay phải quét collection? |
| Kích thước index | Mỗi document có nhiều phần tử mảng, index phình ra bao nhiêu? |
| Tốc độ insert/update | Chi phí duy trì multikey index ảnh hưởng ghi thế nào? |
| p95/p99 latency | Truy vấn nhanh với dữ liệu thực hay chỉ nhanh trên mẫu nhỏ? |

Index đa khóa có những hạn chế như **compound multikey index không được chứa nhiều array field độc lập theo cách tạo ra parallel arrays trong một document**. Điều kiện cụ thể phụ thuộc cấu trúc field và dữ liệu. Thiết kế index nên dựa trên schema và query plan thực tế, không “thêm mọi trường của mảng vào index” một cách máy móc.

### 14.3. `$size`, `$all` và `$elemMatch` có cùng tác dụng với index không?

Không. Chúng có ngữ nghĩa và khả năng tận dụng index khác nhau:

- Membership như `{tags:"red"}` thường là ứng viên tốt cho index trên `tags`.
- `$all` yêu cầu nhiều giá trị cùng xuất hiện; hiệu quả tùy cách query planner kết hợp các điều kiện/index.
- `$size` không trực tiếp được tối ưu bằng index cho chính điều kiện số phần tử.
- `$elemMatch` rất quan trọng khi muốn nhóm nhiều điều kiện trên **cùng** phần tử và có thể hỗ trợ compounding/intersection bounds trong tình huống phù hợp.

Trước khi quyết định thêm index, dùng `explain("executionStats")` trên tập dữ liệu đại diện. Với collection chỉ có tám document mẫu, planner có thể chọn `COLLSCAN` mà vẫn hợp lý; không xem đó là kết luận hiệu năng cho hệ thống lớn.

---

## 15. Áp dụng từ Java MongoDB Sync Driver

Khi dùng Java, có thể dùng `Filters` để biểu đạt ngữ nghĩa giống `mongosh`. Ví dụ với MongoDB Java Sync Driver:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public class ArrayQueries {

    public static void examples(MongoCollection<Document> collection) {
        // Mảng đúng ["red", "blue"] theo thứ tự.
        Bson exactArray = Filters.eq(
            "tags", List.of("red", "blue")
        );

        // Mảng có phần tử "red" (cũng có thể khớp scalar).
        Bson containsRed = Filters.eq("tags", "red");

        // Có ít nhất một trong hai giá trị.
        Bson containsEither = Filters.in(
            "tags", "red", "blue"
        );

        // Có cả hai giá trị, không quan tâm thứ tự.
        Bson containsBoth = Filters.all(
            "tags", "red", "blue"
        );

        // Có một dòng items với sku=A và qty>=2.
        Bson sameItem = Filters.elemMatch(
            "items",
            Filters.and(
                Filters.eq("sku", "A"),
                Filters.gte("qty", 2)
            )
        );

        // Mỗi filter biểu diễn một yêu cầu khác nhau.
        System.out.println(collection.countDocuments(exactArray));
        System.out.println(collection.countDocuments(containsRed));
        System.out.println(collection.countDocuments(containsEither));
        System.out.println(collection.countDocuments(containsBoth));
        System.out.println(collection.countDocuments(sameItem));
    }
}
~~~

Với schema thực, nên dùng POJO/codec phù hợp và kiểm tra tính nhất quán kiểu dữ liệu. Đặc biệt, `Filters.eq("tags", List.of(...))` và `Filters.eq("tags", "red")` là **hai câu hỏi khác nhau**, dù cùng gọi phương thức `eq`.

Nếu cần điều kiện so sánh cho **cùng một phần tử trong mảng scalar**, có thể diễn đạt tường minh:

~~~java
Bson oneScoreBetween80And90 = new Document(
    "scores",
    new Document(
        "$elemMatch",
        new Document("$gt", 80).append("$lt", 90)
    )
);
~~~

Không viết hai điều kiện `gte`/`lt` tách rời rồi giả định rằng MongoDB tự ép chúng lên cùng phần tử.

### 15.1. Khi dùng Spring Data MongoDB

Với `MongoTemplate`, có thể dùng `Criteria.elemMatch(...)`:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("items").elemMatch(
        Criteria.where("sku").is("A")
            .and("qty").gte(2)
    )
);
~~~

Logic vẫn tương đương với query BSON:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
}
~~~

Khi gặp lỗi kết quả sai, nên kiểm tra **BSON query thực tế** sinh ra bởi abstraction đang dùng, không chỉ nhìn tên phương thức Java.

---

## 16. Bốn tình huống nghiệp vụ và cách chọn toán tử

### 16.1. Bộ lọc nhãn sản phẩm

Yêu cầu: khách hàng chọn hai nhãn `"sale"` và `"outdoor"`.

- Chế độ “có **ít nhất một** nhãn đã chọn”: dùng `$in`.
- Chế độ “phải có **tất cả** nhãn đã chọn”: dùng `$all`.
- Chế độ “danh sách nhãn **đúng bằng** hai nhãn theo thứ tự lưu”: dùng array equality nếu thứ tự là một phần của yêu cầu.
- Chế độ “chỉ hai nhãn đó, không có nhãn khác, không cần thứ tự”: cân nhắc `$all` kết hợp `$size` khi nhãn là hai giá trị khác nhau.

Không nên chọn toán tử trước khi UI/API xác định “bất kỳ” hay “tất cả”.

### 16.2. Điểm kiểm tra của học viên

Một học viên có `scores: [70, 95]`. Yêu cầu “có ít nhất một lần kiểm tra trong khoảng 80–90” **không được** diễn đạt bằng:

~~~javascript
{ scores: { $gte: 80, $lte: 90 } }
~~~

Vì hai phép so sánh có thể dựa trên các phần tử khác nhau. Dùng:

~~~javascript
{
  scores: {
    $elemMatch: {
      $gte: 80,
      $lte: 90
    }
  }
}
~~~

Nếu yêu cầu thực sự là “có **một điểm >= 80** và có **một điểm <= 90**, có thể từ hai lần kiểm tra”, cú pháp không dùng `$elemMatch` có thể đúng. Ngữ nghĩa phải xuất phát từ nghiệp vụ.

### 16.3. Đơn hàng có biến thể sản phẩm

Một đơn có:

~~~javascript
{
  orderId: "O-1",
  lines: [
    { color: "black", available: false },
    { color: "white", available: true }
  ]
}
~~~

Yêu cầu “có biến thể màu đen còn hàng”:

~~~javascript
{
  lines: {
    $elemMatch: {
      color: "black",
      available: true
    }
  }
}
~~~

Document trên **không khớp**. Viết `"lines.color":"black"` và `"lines.available":true` độc lập sẽ sai vì ghép hai biến thể khác nhau.

### 16.4. Tìm sự kiện theo một cặp thuộc tính

Giả sử `events` chứa:

~~~javascript
[
  { type: "LOGIN", success: false, at: ISODate("2026-11-14T08:00:00Z") },
  { type: "PAYMENT", success: true, at: ISODate("2026-11-14T08:05:00Z") }
]
~~~

Yêu cầu “có một sự kiện LOGIN thành công” cần:

~~~javascript
{
  events: {
    $elemMatch: {
      type: "LOGIN",
      success: true
    }
  }
}
~~~

Nếu chỉ viết `"events.type":"LOGIN"` và `"events.success":true`, hai điều kiện có thể đến từ hai event khác nhau, tạo cảnh báo bảo mật sai.

---

## 17. Bài tập tự kiểm tra với dữ liệu mẫu

### Bài 1: So khớp nguyên mảng

Dự đoán ID trả về:

~~~javascript
db.arrayQueryLesson.find({
  tags: ["blue", "red"]
});
~~~

**Đáp án:** `_id: 2`. Mảng số 1 có cùng giá trị nhưng đảo thứ tự.

### Bài 2: Phần tử và mảng nguyên vẹn

Hai truy vấn:

~~~javascript
// A
db.arrayQueryLesson.find({ tags: "red" });

// B
db.arrayQueryLesson.find({ tags: ["red"] });
~~~

**Đáp án:** A khớp ID 1, 2, 3, 4, 7, 8; B khớp ID 4 trong dataset mảng phẳng. A là phép membership/scalar equality, B yêu cầu mảng cụ thể.

### Bài 3: AND hay OR?

~~~javascript
// A
db.arrayQueryLesson.find({
  tags: { $in: ["red", "green"] }
});

// B
db.arrayQueryLesson.find({
  tags: { $all: ["red", "green"] }
});
~~~

**Đáp án:** A khớp ID 1, 2, 3, 4, 7, 8 vì có red hoặc green; B chỉ khớp ID 3 vì có cả hai.

### Bài 4: Đếm phần tử

~~~javascript
db.arrayQueryLesson.find({
  tags: { $size: 2 }
});
~~~

**Đáp án:** ID 1, 2, 8. Hai phần tử có thể trùng giá trị.

### Bài 5: Khoảng số

~~~javascript
// A
db.arrayQueryLesson.find({
  scores: { $gt: 80, $lt: 90 }
});

// B
db.arrayQueryLesson.find({
  scores: {
    $elemMatch: { $gt: 80, $lt: 90 }
  }
});
~~~

**Đáp án:** A có thể khớp ID 1, 2, 3, 4, 7; B chỉ khớp ID 1, 3, 4. ID 2 không có điểm thỏa đồng thời cả hai giới hạn; ID 7 chứa scalar.

### Bài 6: Mảng các document

~~~javascript
// A
db.arrayQueryLesson.find({
  "items.sku": "A",
  "items.qty": { $gte: 2 }
});

// B
db.arrayQueryLesson.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
});
~~~

**Đáp án:** A có thể khớp ID 1, 2, 6, 7; B chỉ khớp ID 2. Đây là khác biệt giữa “hai điều kiện có mặt đâu đó” và “một phần tử thỏa cả hai”.

### Bài 7: Mảng rỗng và field thiếu

~~~javascript
// A
db.arrayQueryLesson.find({
  tags: { $size: 0 }
});

// B
db.arrayQueryLesson.find({
  tags: { $ne: "red" }
});
~~~

**Đáp án:** A khớp ID 5; B khớp ID 5 và 6. Với B, field thiếu cũng được bao gồm.

### Bài 8: Chọn cấu trúc theo yêu cầu mới

Giả sử có collection `orders` với `items` chứa `sku`, `warehouseId` và `qty`. Hãy viết:

1. Tìm đơn có **bất kỳ** item nào thuộc warehouse `W1` hoặc `W2`.
2. Tìm đơn có **một item** là `sku = "P1"` và `qty >= 5`.
3. Tìm đơn có **một item P1** và **một item P2**, không yêu cầu cùng một phần tử.
4. Tìm đơn có **đúng ba item**.

**Gợi ý:** (1) dùng dotted path + `$in`; (2) dùng một `$elemMatch`; (3) dùng hai `$elemMatch` kết hợp `$and`; (4) dùng `$size: 3`.

---

## 18. Những lỗi tư duy thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`{ tags: ["a", "b"] }` nghĩa là chứa a và b.” | Với mảng phẳng, đây là array equality: kích thước và thứ tự phải khớp. |
| “`{ tags: "a" }` chỉ khớp field kiểu array.” | Nó cũng có thể khớp field scalar bằng `"a"`. |
| “`$in` đòi tất cả giá trị.” | `$in` là OR; `$all` mới dùng cho yêu cầu có đủ giá trị. |
| “`$all` đảm bảo đúng thứ tự.” | Nó không bắt buộc thứ tự và cho phép phần tử bổ sung. |
| “`$all: ["a", "a"]` yêu cầu hai lần a.” | Không; nó không đếm số lần lặp của cùng giá trị. |
| “`$size` kiểm tra nội dung mảng.” | Nó chỉ kiểm tra số phần tử. |
| “`$size` dùng được với `$gte`.” | Trong query operator, `$size` nhận độ dài chính xác. |
| “Hai predicate trên array luôn áp dụng một phần tử.” | Chúng có thể được đáp ứng bởi các phần tử khác nhau. |
| “Dotted path đủ để ràng buộc `sku` và `qty` ở cùng item.” | Cần `$elemMatch` khi điều kiện phải cùng một phần tử. |
| “`$elemMatch` yêu cầu mọi phần tử đều thỏa.” | Chỉ cần **ít nhất một** phần tử thỏa tất cả predicate. |
| “Một object scalar có thể được xem là array một phần tử.” | `$elemMatch` yêu cầu field kiểu array; scalar không khớp. |
| “Mảng rỗng, `null` và field thiếu là như nhau.” | Chúng có ngữ nghĩa và hành vi truy vấn khác nhau. |
| “`$ne`/`$nin` tự loại field thiếu.” | Chúng có thể khớp document không có field đó. |
| “Có multikey index là mọi truy vấn mảng đều nhanh.” | Phải kiểm tra index bounds, kích thước index, fetch và query plan. |

## 19. Cách tiếp cận khi viết truy vấn mảng trong dự án

1. **Viết câu hỏi bằng ngôn ngữ nghiệp vụ.** Đó là “bằng chính xác”, “chứa bất kỳ”, “chứa tất cả”, “có ít nhất một phần tử thỏa nhiều điều kiện”, hay “có hai phần tử thỏa hai điều kiện riêng”?
2. **Xác nhận schema.** Field luôn là array hay có thể là scalar, `null`, thiếu trường? Array chứa scalar hay embedded documents? Có array lồng array không?
3. **Chọn toán tử tối thiểu diễn đạt đúng ý định.** Dùng array equality, scalar equality, `$in`, `$all`, `$size`, `$elemMatch` hoặc dotted path đúng trường hợp.
4. **Thử các trường hợp đối nghịch.** Đảo thứ tự phần tử, thêm phần tử thừa, đưa các điều kiện vào hai phần tử khác nhau, dùng mảng rỗng, thiếu field và sai kiểu dữ liệu.
5. **Xem xét chỉ mục theo đường truy cập.** Với array nhiều phần tử, đo cardinality, multikey index, các chỉ số `keysExamined` và `docsExamined`.
6. **Theo dõi biến đổi schema.** Khi một field từ scalar chuyển thành array hoặc object con bổ sung field mới, các truy vấn equality có thể đổi hành vi. Dùng migration/validation để giữ dữ liệu nhất quán.
7. **Kiểm tra kết quả với dữ liệu đại diện.** Đo cả **đúng/sai nghiệp vụ** lẫn độ trễ; truy vấn nhanh nhưng ghép dữ liệu từ các phần tử khác nhau vẫn là truy vấn sai.

## 20. Tài liệu chính thức nên đọc thêm

- [MongoDB — Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/): so khớp array, phần tử và các điều kiện trên mảng.
- [MongoDB — Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/): dotted path, `$elemMatch` với object trong mảng.
- [MongoDB — `$elemMatch`](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/): ngữ nghĩa một phần tử phải thỏa tất cả điều kiện.
- [MongoDB — `$all`](https://www.mongodb.com/docs/manual/reference/operator/query/all/): yêu cầu có đủ giá trị.
- [MongoDB — `$size`](https://www.mongodb.com/docs/manual/reference/operator/query/size/): kiểm tra độ dài array và giới hạn liên quan tới index.
- [MongoDB — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): index trên array và cách dùng `$elemMatch` với compound bounds.
- [MongoDB — Java Sync Driver, Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): dựng bộ lọc BSON trong Java.

Ý nghĩa cốt lõi của bài học là **định lượng đúng phạm vi điều kiện**:

- **Toàn bộ mảng**: so sánh danh sách với danh sách, thường quan tâm kích thước và thứ tự.
- **Tồn tại phần tử**: so sánh với giá trị scalar, dùng `$in` hoặc những toán tử membership tương ứng.
- **Cùng một phần tử**: nhóm mọi ràng buộc cần đi cùng nhau trong một `$elemMatch`.
- **Nhiều phần tử với nhiều vai trò**: viết rõ các điều kiện tồn tại độc lập, không vô tình ép hoặc tách chúng.

Khi phân biệt được bốn cách hiểu đó, việc lựa chọn `$eq`, `$in`, `$all`, `$size`, dotted path và `$elemMatch` sẽ trở thành quyết định có cơ sở, thay vì thử cú pháp cho đến khi truy vấn tình cờ trả ra dữ liệu.
