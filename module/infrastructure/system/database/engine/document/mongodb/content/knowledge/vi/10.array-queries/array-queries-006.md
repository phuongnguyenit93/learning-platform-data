# Projection mảng bằng $elemMatch, $slice và toán tử vị trí trong MongoDB

Một tài liệu MongoDB có thể chứa mảng dài: điểm của học viên, lịch sử hoạt động, danh sách hình ảnh, bình luận hoặc các biến thể sản phẩm. Nhiều API chỉ cần **một phần tử**, **vài phần tử đầu/cuối**, hoặc **phần tử đầu tiên thỏa điều kiện**. Nếu trả về toàn bộ mảng ở mọi yêu cầu, ứng dụng sẽ phải truyền và xử lý nhiều dữ liệu không cần thiết.

**Array projection** là kỹ thuật lựa chọn phần dữ liệu của một trường mảng **trong kết quả truy vấn**. Ba công cụ chính ở bài này là:

- **`$elemMatch` trong projection**: lấy **phần tử đầu tiên** của mảng thỏa điều kiện chỉ định ngay trong projection.
- **`$slice` trong projection**: lấy một đoạn mảng theo **vị trí và số lượng**, không lọc theo giá trị của phần tử.
- **Toán tử vị trí `$` trong projection**: lấy **phần tử đầu tiên khớp điều kiện truy vấn** đối với mảng.

Cần phân biệt projection với filter: **filter quyết định tài liệu nào được trả về**, còn **projection quyết định tài liệu được trả về gồm các trường và phần tử mảng nào**. Nội dung gốc trong collection không bị thay đổi bởi một lệnh đọc sử dụng projection.

## 1. Cú pháp tổng quan

Hai đối số thường thấy trong `find()`:

~~~javascript
db.collection.find(
  { /* filter: chọn document */ },
  { /* projection: chọn các trường và phần tử mảng trả về */ }
);
~~~

Ví dụ:

~~~javascript
// Chọn các khóa học đang công bố, trả về tối đa 2 bài học đầu.
db.courses.find(
  { status: "published" },
  { title: 1, lessons: { $slice: 2 } }
);
~~~

Trong phần projection:

- `title: 1` nghĩa là lấy trường `title`.
- `lessons: { $slice: 2 }` nghĩa là trả về hai phần tử đầu của `lessons`.
- `_id` vẫn được trả về mặc định, trừ khi đặt `_id: 0`.
- Không có document nào được thêm, xóa hay sửa từ thao tác `find()`.

Bảng so sánh nhanh:

| Mục tiêu | Projection | Kết quả đối với mảng |
| --- | --- | --- |
| Trả nguyên mảng | `{ lessons: 1 }` | Toàn bộ các phần tử |
| Lấy phần tử đầu tiên đạt điều kiện | `{ grades: { $elemMatch: { score: { $gte: 90 } } } }` | Mảng chứa **một phần tử đầu tiên** khớp, nếu có |
| Lấy hai phần tử đầu | `{ lessons: { $slice: 2 } }` | Mảng tối đa hai phần tử |
| Lấy hai phần tử cuối | `{ lessons: { $slice: -2 } }` | Mảng tối đa hai phần tử |
| Lấy hai phần tử sau khi bỏ một phần tử đầu | `{ lessons: { $slice: [1, 2] } }` | Mảng từ vị trí chỉ định |
| Trả phần tử phù hợp điều kiện đã dùng ở filter | `{ "grades.$": 1 }` | Mảng chứa **một phần tử đầu tiên** khớp filter |
| Lấy **mọi** phần tử đạt điều kiện | `$filter` trong aggregation | Mảng có không, một hoặc nhiều phần tử |

**Lưu ý về tên:** MongoDB còn có toán tử `$elemMatch` dùng **trong filter**, biểu thức `$slice` dùng **trong aggregation**, toán tử `$slice` dùng **khi update với `$push`**, và toán tử vị trí `$` dùng **khi update**. Chúng có tên gần giống nhưng cú pháp và mục đích khác nhau.

## 2. Chuẩn bị bộ dữ liệu thực hành

Các ví dụ dùng **mongosh** và một collection riêng, không ảnh hưởng dữ liệu sản xuất.

~~~javascript
const lab = db.getSiblingDB("array_projection_lab");

lab.courses.drop();

lab.courses.insertMany([
  {
    _id: 101,
    title: "MongoDB căn bản",
    status: "published",
    lessons: ["BSON", "CRUD", "Query", "Indexes", "Aggregation"],
    grades: [
      { student: "An", score: 66, passed: false },
      { student: "Binh", score: 89, passed: true },
      { student: "Chi", score: 92, passed: true }
    ],
    ratings: [3, 5, 4, 5],
    details: {
      category: "database",
      topics: ["documents", "arrays", "indexes"],
      language: "vi"
    }
  },
  {
    _id: 102,
    title: "MongoDB nâng cao",
    status: "published",
    lessons: ["Aggregation", "Transactions", "Change streams", "Performance"],
    grades: [
      { student: "Dung", score: 77, passed: true },
      { student: "Hoa", score: 95, passed: true },
      { student: "Minh", score: 95, passed: true }
    ],
    ratings: [4, 5],
    details: {
      category: "database",
      topics: ["replica set", "transactions"],
      language: "vi"
    }
  },
  {
    _id: 103,
    title: "Java Fundamentals",
    status: "draft",
    lessons: ["Syntax", "OOP"],
    grades: [
      { student: "Lan", score: 45, passed: false },
      { student: "Nam", score: 58, passed: false }
    ],
    ratings: [2, 3],
    details: {
      category: "programming",
      topics: ["classes", "interfaces"],
      language: "en"
    }
  },
  {
    _id: 104,
    title: "Query Practice",
    status: "published",
    lessons: [],
    grades: [],
    ratings: [],
    details: {
      category: "database",
      topics: [],
      language: "vi"
    }
  },
  {
    _id: 105,
    title: "Mongo Express",
    status: "published",
    lessons: ["Find", "Projection"]
    // Cố ý không có grades, ratings hoặc details.
  }
]);
~~~

Để kết quả luôn dễ so sánh, có thể dùng:

~~~javascript
lab.courses.find({}, { title: 1, lessons: 1, grades: 1 })
  .sort({ _id: 1 });
~~~

Các tài liệu `101` và `102` có nhiều phần tử đạt một số điều kiện; tài liệu `103` có phần tử nhưng không đạt điều kiện điểm cao; `104` có mảng rỗng; `105` **thiếu hẳn** một số trường mảng. Bộ dữ liệu này giúp quan sát rõ kết quả trong các trường hợp biên.

## 3. Projection thông thường: lấy hoặc ẩn cả trường mảng

Trước khi dùng toán tử chuyên biệt, cần hiểu projection cơ bản:

~~~javascript
// Chỉ trả title và lessons; _id mặc định vẫn có.
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: 1 }
);
~~~

Kết quả minh họa:

~~~javascript
{
  _id: 101,
  title: "MongoDB căn bản",
  lessons: ["BSON", "CRUD", "Query", "Indexes", "Aggregation"]
}
~~~

Muốn ẩn mảng nhưng giữ các trường khác:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { grades: 0, ratings: 0 }
);
~~~

Thông thường, trong một projection bạn **không trộn** các lựa chọn inclusion (`1`) và exclusion (`0`), ngoại trừ quy tắc đặc biệt đối với `_id`. Các toán tử projection mảng có thêm quy tắc về cách kết hợp, xem mục `$slice`.

Projection **không phân trang danh sách document**. Lệnh:

~~~javascript
lab.courses.find({}, { lessons: 1 }).limit(2);
~~~

chỉ giới hạn số **document** được trả về, không giới hạn số **phần tử của từng mảng lessons**. Muốn thu gọn mảng, dùng `$slice` hoặc những toán tử phù hợp khác.

## 4. $elemMatch trong projection: phần tử đầu tiên thỏa điều kiện riêng

### 4.1. Cú pháp

~~~javascript
db.collection.find(
  { /* điều kiện chọn document */ },
  {
    arrayField: {
      $elemMatch: { /* điều kiện phần tử */ }
    }
  }
);
~~~

MongoDB duyệt các phần tử của mảng và đưa vào kết quả **phần tử đầu tiên thỏa điều kiện** của `$elemMatch`. Nếu không có phần tử nào phù hợp, **trường mảng đó không xuất hiện** trong document kết quả.

Quan trọng: điều kiện của `$elemMatch` nằm **trong projection**, nên nó quyết định phần tử nào **được hiển thị**, không mặc nhiên loại bỏ toàn bộ document có mảng không khớp.

### 4.2. Ví dụ với mảng object

Lấy tất cả khóa học đã công bố nhưng chỉ hiển thị **học viên đầu tiên đạt ít nhất 90 điểm**:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: {
      $elemMatch: { score: { $gte: 90 } }
    }
  }
).sort({ _id: 1 });
~~~

Phần kết quả liên quan:

~~~javascript
{ _id: 101, title: "MongoDB căn bản",
  grades: [{ student: "Chi", score: 92, passed: true }] }

{ _id: 102, title: "MongoDB nâng cao",
  grades: [{ student: "Hoa", score: 95, passed: true }] }

{ _id: 104, title: "Query Practice" }

{ _id: 105, title: "Mongo Express" }
~~~

Giải thích:

- Khóa học `101` có một phần tử điểm từ 90 trở lên: `Chi`.
- Khóa học `102` có **hai** phần tử điểm 95: `Hoa` và `Minh`. Projection chỉ trả phần tử xuất hiện **đầu tiên trong mảng**, tức `Hoa`.
- Khóa học `104` có mảng `grades: []` nhưng không có phần tử thỏa. Kết quả **bỏ trường grades**.
- Khóa học `105` không có `grades`, vì vậy kết quả cũng **không có trường grades**.
- Khóa học `103` là `draft` nên bị loại **bởi filter** `{ status: "published" }`; đó là lý do khác với việc trường `grades` bị lược bỏ.

Điểm dễ nhầm: một document không có phần tử khớp projection `$elemMatch` **vẫn có thể được trả về** nếu đáp ứng filter.

### 4.3. Kết hợp nhiều điều kiện trên cùng phần tử

Yêu cầu: hiển thị **học viên đầu tiên vừa đạt điểm từ 80 trở lên vừa có `passed: true`**.

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    title: 1,
    grades: {
      $elemMatch: {
        score: { $gte: 80 },
        passed: true
      }
    }
  }
);
~~~

Kết quả:

~~~javascript
{
  _id: 101,
  title: "MongoDB căn bản",
  grades: [{ student: "Binh", score: 89, passed: true }]
}
~~~

Các điều kiện `score` và `passed` áp dụng cho **cùng một object** trong mảng `grades`. Nếu không biết phần tử nào thỏa, không thể dựa vào việc một phần tử có điểm cao và phần tử khác có `passed: true` rồi kết luận rằng có một phần tử thỏa cả hai.

### 4.4. Query $elemMatch và projection $elemMatch là hai vị trí khác nhau

**Query `$elemMatch`** nằm trong filter để **chọn document**:

~~~javascript
lab.courses.find(
  {
    grades: {
      $elemMatch: {
        score: { $gte: 90 },
        passed: true
      }
    }
  },
  { title: 1 }
);
// Trả document 101 và 102; không lấy riêng phần tử mảng.
~~~

**Projection `$elemMatch`** nằm trong đối số thứ hai để **chọn phần tử mảng trả về**:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: {
      $elemMatch: { passed: true }
    }
  }
);
// Vẫn trả các document published, dù không có grade passed:true.
~~~

Có thể đặt cả hai trong một truy vấn, với mục đích **khác nhau**:

~~~javascript
lab.courses.find(
  { "grades.score": { $gte: 90 } },
  {
    title: 1,
    grades: {
      $elemMatch: { passed: true }
    }
  }
);
~~~

Truy vấn chọn khóa học `101` và `102` vì **có điểm từ 90 trở lên**, nhưng projection lại lấy **grade đầu tiên có `passed: true`**. Vì thế:

- `101` trả `Binh`, điểm **89**.
- `102` trả `Dung`, điểm **77**.

Kết quả đúng với hai điều kiện được đặt ở **hai vị trí khác nhau**, nhưng có thể trái với ý định nếu người viết tưởng rằng projection luôn trả phần tử đã khiến document khớp filter.

### 4.5. $elemMatch với mảng giá trị đơn giản

Ngoài object, mảng có thể chứa số hoặc chuỗi. Ví dụ `ratings` ở khóa học `101` là:

~~~javascript
[3, 5, 4, 5]
~~~

Lấy điểm đánh giá **đầu tiên từ 4 trở lên**:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    ratings: {
      $elemMatch: { $gte: 4 }
    }
  }
);
~~~

Kết quả:

~~~javascript
{ _id: 101, ratings: [5] }
~~~

Vì `5` là phần tử đầu tiên thỏa `$gte: 4`, phần tử `4` và phần tử `5` ở cuối **không** được trả về.

Cần tránh viết `{ ratings: { $elemMatch: { value: 4 } } }` khi mảng chỉ gồm các **số**, vì điều kiện `value` chỉ có nghĩa đối với mảng gồm **object có field value**.

## 5. $slice trong projection: cắt mảng theo vị trí

### 5.1. Hai dạng cú pháp

`$slice` không xét giá trị của từng phần tử; nó giới hạn đoạn mảng theo vị trí:

~~~javascript
// Dạng 1: lấy n phần tử đầu hoặc cuối.
db.collection.find(
  { /* filter */ },
  { arrayField: { $slice: n } }
);

// Dạng 2: bỏ qua skip phần tử, lấy tối đa limit phần tử.
db.collection.find(
  { /* filter */ },
  { arrayField: { $slice: [skip, limit] } }
);
~~~

Với dạng thứ hai, **limit phải là số nguyên dương**. `skip` có thể dương, bằng 0 hoặc âm.

| Biểu thức | Ý nghĩa đối với mảng |
| --- | --- |
| `{ $slice: 2 }` | Hai phần tử đầu |
| `{ $slice: -2 }` | Hai phần tử cuối |
| `{ $slice: [0, 2] }` | Bắt đầu từ index 0, lấy hai phần tử |
| `{ $slice: [1, 2] }` | Bỏ một phần tử đầu rồi lấy hai phần tử |
| `{ $slice: [-3, 2] }` | Bắt đầu ở vị trí thứ ba tính từ cuối, lấy hai phần tử |
| `{ $slice: [100, 2] }` | Trả mảng rỗng nếu skip vượt chiều dài mảng |

Chỉ số phần tử bắt đầu từ **0**. Mảng `["BSON", "CRUD", "Query", "Indexes", "Aggregation"]` có index 0 là `"BSON"` và index 4 là `"Aggregation"`.

### 5.2. Lấy phần tử đầu

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: 2 } }
);
~~~

Kết quả:

~~~javascript
{
  _id: 101,
  title: "MongoDB căn bản",
  lessons: ["BSON", "CRUD"]
}
~~~

Nếu mảng ít hơn hai phần tử, MongoDB trả về toàn bộ phần tử hiện có; `$slice` không tạo giá trị giả để đủ số lượng.

### 5.3. Lấy phần tử cuối

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: -2 } }
);
~~~

Kết quả:

~~~javascript
{
  _id: 101,
  title: "MongoDB căn bản",
  lessons: ["Indexes", "Aggregation"]
}
~~~

**`$slice: -2` giữ thứ tự tự nhiên của hai phần tử cuối**; nó không đảo ngược mảng.

### 5.4. Cắt từ một vị trí xác định

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: [1, 2] } }
);
~~~

Kết quả:

~~~javascript
{
  _id: 101,
  title: "MongoDB căn bản",
  lessons: ["CRUD", "Query"]
}
~~~

Ở đây `skip = 1` bỏ `"BSON"`, rồi `limit = 2` trả `"CRUD"` và `"Query"`. Đây là cách cắt **một phần mảng trong từng document**, khác với `cursor.skip()` dùng để bỏ qua **document của result set**.

### 5.5. Chỉ số âm trong mảng [skip, limit]

~~~javascript
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: [-3, 2] } }
);
~~~

Mảng có năm phần tử; vị trí `-3` tính từ cuối tương ứng index 2, nên kết quả là:

~~~javascript
{ _id: 101, lessons: ["Query", "Indexes"] }
~~~

Nếu trị tuyệt đối của skip âm lớn hơn chiều dài mảng, điểm bắt đầu được điều chỉnh về **đầu mảng**. Với skip dương vượt chiều dài mảng, kết quả là **mảng rỗng**.

### 5.6. Mảng rỗng và trường không tồn tại

~~~javascript
lab.courses.find(
  { _id: { $in: [104, 105] } },
  { title: 1, lessons: { $slice: 3 }, grades: { $slice: 2 } }
).sort({ _id: 1 });
~~~

Phần kết quả tương ứng:

~~~javascript
{ _id: 104, title: "Query Practice", lessons: [], grades: [] }
{ _id: 105, title: "Mongo Express", lessons: ["Find", "Projection"] }
~~~

Sự khác biệt:

- `104` **có** `grades: []`; `$slice` trả về **mảng rỗng**.
- `105` **không có** `grades`; projection không tự tạo trường `grades`.
- `105` có hai bài học, ít hơn giới hạn 3; cả hai được trả về.

Đây là khác biệt với **projection `$elemMatch`**: khi mảng tồn tại nhưng không có phần tử khớp, trường mảng bị **bỏ khỏi kết quả**, không nhất thiết hiện thành `[]`.

### 5.7. $slice và inclusion/exclusion projection

Một chi tiết dễ bỏ qua: **`$slice` đứng riêng được coi là exclusion projection**. Vì thế truy vấn:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: 2 } }
);
~~~

có thể **vẫn trả về các trường khác** của document, chỉ rút ngắn `lessons`. Nếu API chỉ được trả `title` và hai bài học đầu, nên khai báo rõ trường cần lấy:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    _id: 0,
    title: 1,
    lessons: { $slice: 2 }
  }
);
~~~

Khi dùng inclusion projection có trường lồng nhau, `$slice` trên một mảng lồng nhau có thể làm **các trường anh em bên trong object** không được trả về. Ví dụ:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    title: 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

Kết quả giữ `details.topics` đã cắt nhưng **không tự giữ `details.language` hoặc `details.category`**. Nếu cần các trường đó, khai báo chúng trong inclusion projection:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    title: 1,
    "details.language": 1,
    "details.category": 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

Để tránh lỗi **path collision**, không nên cùng lúc dùng `$slice` trên mảng và projection một đường dẫn con của cùng mảng trong cùng đối số projection; có thể tách thành nhiều stage `$project` khi chuyển sang aggregation.

### 5.8. $slice không thực hiện sắp xếp

Nếu `grades` là `[66, 89, 92]`, thì:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { grades: { $slice: 1 } }
);
~~~

sẽ lấy **phần tử đầu trong thứ tự mảng**, tức điểm 66, **không phải điểm cao nhất**. Lệnh `find().sort({ "grades.score": -1 })` sắp xếp các **document**, không tự sắp xếp từng phần tử trong mảng trước khi `$slice`.

Để lấy phần tử tốt nhất theo một thuộc tính, cần cách khác: lưu mảng theo thứ tự mong muốn hoặc dùng aggregation với thao tác sắp xếp mảng thích hợp (ví dụ `$sortArray` trong các phiên bản MongoDB hỗ trợ), rồi mới giới hạn số phần tử.

## 6. Toán tử vị trí $ trong projection

### 6.1. Cú pháp và ý nghĩa

Toán tử vị trí `$` trong **projection** có cú pháp:

~~~javascript
db.collection.find(
  { arrayField: { /* điều kiện */ } },
  { "arrayField.$": 1 }
);
~~~

Dấu `$` đặt **cuối đường dẫn field**, giúp lấy **phần tử đầu tiên của mảng khớp điều kiện truy vấn**.

Ví dụ với mảng điểm:

~~~javascript
lab.courses.find(
  { _id: 101, "grades.score": { $gte: 80 } },
  {
    title: 1,
    "grades.$": 1
  }
);
~~~

Kết quả:

~~~javascript
{
  _id: 101,
  title: "MongoDB căn bản",
  grades: [{ student: "Binh", score: 89, passed: true }]
}
~~~

Ở tài liệu 101, `Binh` là phần tử đầu tiên có điểm từ 80 trở lên; `Chi` cũng đạt nhưng đứng sau, nên không được trả về.

### 6.2. Điều kiện mảng nằm trong filter

Đây là khác biệt lớn với projection `$elemMatch`: toán tử `$` thường lấy phần tử thỏa **điều kiện đã viết ở filter**, còn `$elemMatch` trong projection nhận điều kiện **ngay tại projection**.

Ví dụ tìm tất cả khóa học có học viên đạt từ 90 điểm rồi trả phần tử đầu tiên khớp:

~~~javascript
lab.courses.find(
  { "grades.score": { $gte: 90 } },
  {
    title: 1,
    "grades.$": 1
  }
).sort({ _id: 1 });
~~~

Kết quả:

~~~javascript
{ _id: 101, title: "MongoDB căn bản",
  grades: [{ student: "Chi", score: 92, passed: true }] }

{ _id: 102, title: "MongoDB nâng cao",
  grades: [{ student: "Hoa", score: 95, passed: true }] }
~~~

Hai document được chọn vì điều kiện trên `grades.score`, đồng thời chỉ trả **một grade đầu tiên** khớp trong mỗi document.

### 6.3. Nhiều điều kiện phải khớp trên cùng phần tử: $elemMatch trong filter

Giả sử cần học viên vừa có `score >= 80` vừa có `passed: true`. Dùng **query `$elemMatch`** để đảm bảo hai điều kiện cùng thuộc **một phần tử**:

~~~javascript
lab.courses.find(
  {
    grades: {
      $elemMatch: {
        score: { $gte: 80 },
        passed: true
      }
    }
  },
  {
    title: 1,
    "grades.$": 1
  }
).sort({ _id: 1 });
~~~

Kết quả:

~~~javascript
{ _id: 101, title: "MongoDB căn bản",
  grades: [{ student: "Binh", score: 89, passed: true }] }

{ _id: 102, title: "MongoDB nâng cao",
  grades: [{ student: "Hoa", score: 95, passed: true }] }
~~~

Dùng điều kiện kiểu:

~~~javascript
{
  "grades.score": { $gte: 80 },
  "grades.passed": true
}
~~~

có thể khiến **hai phần tử khác nhau** lần lượt thỏa hai điều kiện, trong khi không có phần tử đơn lẻ đáp ứng cả hai. Cách đó không thay thế `$elemMatch` khi yêu cầu cùng phần tử, và còn tạo kết quả khó dự đoán nếu kết hợp với positional projection.

### 6.4. Các giới hạn quan trọng của positional $

Khi dùng projection `"grades.$": 1`, cần ghi nhớ:

1. **Chỉ một positional `$` trong projection.** Không dùng hai trường `"grades.$"` và `"ratings.$"` trong cùng projection.
2. **Nên chỉ có một trường mảng làm điều kiện chọn phần tử** trong filter; đưa nhiều mảng khác nhau vào filter có thể dẫn tới hành vi không xác định của positional projection.
3. **Nên chỉ có một điều kiện áp dụng cho mảng đang chiếu**; nếu cần ghép nhiều điều kiện trên cùng phần tử, đặt chúng trong **query `$elemMatch`**.
4. **`$` phải đứng cuối đường dẫn field**, ví dụ `"grades.$"`, không phải `"grades.$.score"`.
5. **Không kết hợp `$slice` vào chính biểu thức positional `$`** như `{ "grades.$": { $slice: 1 } }`.
6. **Không nhầm với `$` trong lệnh update.** Projection `$` chỉ thu gọn kết quả đọc, còn positional update `$` dùng để thay đổi phần tử phù hợp của mảng trong database.
7. **Dùng thận trọng với `sort()` theo field lặp trong mảng**: việc sắp xếp document không đảm bảo phần tử được chiếu có quan hệ “đầu tiên/cao nhất” theo cách người đọc kỳ vọng.

Các phiên bản MongoDB hiện đại có thể cho phép chỉ định positional projection trên một trường mảng **khác trường đã có trong query**, nhưng kết quả yêu cầu cân nhắc điều kiện mảng và kích thước các mảng. Để code rõ nghĩa, các ví dụ thực hành ở đây dùng **chính mảng `grades` có điều kiện trong filter**.

## 7. So sánh $elemMatch và positional $ bằng cùng một yêu cầu

Yêu cầu: tìm các khóa học đã công bố, hiển thị **học viên đầu tiên có `passed: true`**.

Cách 1 — Projection `$elemMatch` nhận điều kiện ngay trong projection:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: { $elemMatch: { passed: true } }
  }
);
~~~

- Trả cả các khóa học published **không có học viên passed**, nhưng có thể không chứa trường `grades` trong kết quả.
- Từ khóa học 101, lấy `Binh`.
- Từ khóa học 102, lấy `Dung`.

Cách 2 — Positional `$` dùng điều kiện trong filter:

~~~javascript
lab.courses.find(
  {
    status: "published",
    "grades.passed": true
  },
  {
    title: 1,
    "grades.$": 1
  }
);
~~~

- Chỉ trả các khóa học published **có ít nhất một học viên passed**.
- Từ khóa học 101, lấy `Binh`.
- Từ khóa học 102, lấy `Dung`.
- Khóa học 104 và 105 không được trả về vì **không thỏa filter**.

Khi cần **vừa lọc document** vừa **đặt điều kiện hiển thị độc lập**, dùng projection `$elemMatch`. Khi cần lấy phần tử **đã làm document khớp filter**, positional `$` thường mô tả đúng ý hơn, miễn tôn trọng các giới hạn về field mảng trong filter.

## 8. Khi cần nhiều phần tử: chuyển sang aggregation $filter

Cả `$elemMatch` projection và `$` positional projection đều giới hạn vào **một phần tử đầu tiên**. Nếu yêu cầu hiển thị **toàn bộ học viên có điểm >= 85**, nên dùng `$filter` trong **aggregation pipeline**:

~~~javascript
lab.courses.aggregate([
  { $match: { status: "published" } },
  {
    $project: {
      title: 1,
      highScores: {
        $filter: {
          input: { $ifNull: ["$grades", []] },
          as: "grade",
          cond: { $gte: ["$$grade.score", 85] }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả của hai khóa học có điểm từ 85:

~~~javascript
{
  _id: 101,
  title: "MongoDB căn bản",
  highScores: [
    { student: "Binh", score: 89, passed: true },
    { student: "Chi", score: 92, passed: true }
  ]
}
{
  _id: 102,
  title: "MongoDB nâng cao",
  highScores: [
    { student: "Hoa", score: 95, passed: true },
    { student: "Minh", score: 95, passed: true }
  ]
}
~~~

Khóa học 104 và 105 cũng thuộc `published`, nhưng `highScores` là `[]` do biểu thức `$ifNull` biến trường thiếu/null thành mảng rỗng trước khi lọc.

`$filter` có ba thành phần chính:

- `input`: mảng đầu vào, có thể là biểu thức.
- `as`: tên biến đại diện cho một phần tử.
- `cond`: biểu thức logic chạy với từng phần tử (ví dụ `$$grade.score`).

Kết quả `$filter` **giữ thứ tự ban đầu** của các phần tử khớp. Nếu muốn giới hạn số lượng, có thể dùng tham số `limit` của `$filter` ở phiên bản MongoDB hỗ trợ, hoặc dùng `$slice` **biểu thức aggregation** sau khi lọc.

### 8.1. $slice trong find khác $slice trong aggregation

Cùng tên nhưng hai ngữ cảnh:

~~~javascript
// Projection operator trong find():
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: 2 } }
);

// Expression operator trong aggregation:
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      firstTwoLessons: { $slice: ["$lessons", 2] }
    }
  }
]);
~~~

Khác biệt quan trọng:

| Ngữ cảnh | Cú pháp | Tác dụng |
| --- | --- | --- |
| `find()` projection | `{ lessons: { $slice: 2 } }` | Cắt mảng field `lessons` khi trả document |
| `$project` aggregation | `{ firstTwoLessons: { $slice: ["$lessons", 2] } }` | Tính một **biểu thức mảng** rồi gán vào field đầu ra |
| `$push` update modifier | `{ $push: { lessons: { $each: [...], $slice: 5 } } }` | **Thay đổi mảng được lưu** trong database theo giới hạn |

Trong aggregation có thể kết hợp linh hoạt các phép toán. Ví dụ chỉ giữ **hai học viên đầu tiên đạt điểm >= 85**:

~~~javascript
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      title: 1,
      firstTwoHighScores: {
        $slice: [
          {
            $filter: {
              input: "$grades",
              as: "g",
              cond: { $gte: ["$$g.score", 85] }
            }
          },
          2
        ]
      }
    }
  }
]);
~~~

Kết quả `firstTwoHighScores` ở khóa học 101 là `Binh` và `Chi`. Đây là **hai phần tử đầu tiên trong thứ tự mảng gốc thỏa điều kiện**, không nhất thiết là hai người có điểm cao nhất nếu mảng chưa được sắp xếp.

### 8.2. Khi muốn một phần tử theo chỉ số cụ thể

Nếu bài toán cần đúng phần tử tại **index 2**, không phải phần tử đầu tiên đạt một điều kiện, có thể dùng `$arrayElemAt` trong aggregation:

~~~javascript
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      title: 1,
      lessonAtIndex2: { $arrayElemAt: ["$lessons", 2] }
    }
  }
]);
~~~

Kết quả `lessonAtIndex2` là chuỗi `"Query"`. Cách này trả **giá trị phần tử** chứ không tự bọc trong mảng một phần tử như positional projection.

## 9. Quy tắc khi mảng nằm trong object lồng nhau

Trong dữ liệu ví dụ, `details` là một object, còn `details.topics` là mảng:

~~~javascript
{
  details: {
    category: "database",
    topics: ["documents", "arrays", "indexes"],
    language: "vi"
  }
}
~~~

Dùng `$slice` với dotted path:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    _id: 0,
    title: 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

Kết quả:

~~~javascript
{
  title: "MongoDB căn bản",
  details: {
    topics: ["documents", "arrays"]
  }
}
~~~

Để giữ cả category và language, cần yêu cầu chúng riêng:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    _id: 0,
    title: 1,
    "details.category": 1,
    "details.language": 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

Hạn chế projection path collision:

~~~javascript
// Có thể gây lỗi path collision:
// vừa chiếu mảng grades bằng $slice,
// vừa muốn chiếu trường con grades.student ở cùng projection.
lab.courses.find(
  { _id: 101 },
  {
    grades: { $slice: 2 },
    "grades.student": 1
  }
);
~~~

Nếu cần **cắt mảng rồi chỉ giữ một số field của từng object**, hãy chuyển sang aggregation với `$slice` và `$map` (hoặc nhiều `$project` liên tiếp), thay vì cố ép hai projection xung đột trên cùng path.

Ví dụ cắt hai phần tử đầu và chỉ trả tên:

~~~javascript
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      _id: 1,
      studentNames: {
        $map: {
          input: { $slice: ["$grades", 2] },
          as: "g",
          in: "$$g.student"
        }
      }
    }
  }
]);
~~~

Kết quả `studentNames` là `["An", "Binh"]`, vì đã giới hạn hai phần tử đầu của mảng `grades` trước khi ánh xạ lấy `student`.

## 10. Giới hạn và những tình huống cần chú ý

### 10.1. Truy vấn trên MongoDB view

Đối với **standard view** của MongoDB, `find()` **không hỗ trợ** các toán tử projection mảng `$elemMatch`, `$slice` và positional `$` theo quy tắc tài liệu chính thức.

Nếu đang truy vấn một view thay vì collection vật lý, cần kiểm tra khả năng dùng **aggregation pipeline** với `$project`, `$filter` hoặc `$slice` expression để tạo kết quả tương đương khi phiên bản/deployment hỗ trợ.

### 10.2. $elemMatch projection không hỗ trợ $text bên trong

Không nhúng một `$text` query vào điều kiện `$elemMatch` projection; đây không phải phép so khớp dành cho một phần tử mảng. Nếu cần tìm kiếm toàn văn rồi hiển thị phần tử, hãy tách nhiệm vụ chọn document và biến đổi mảng theo API/feature tương ứng.

### 10.3. Projection không thay đổi dữ liệu nguồn

Một lệnh `find()` với `$slice: 2` **không cắt mảng đang lưu** thành hai phần tử. Một lệnh `find()` với `$elemMatch` cũng **không xóa các phần tử không khớp**.

Nếu cần chỉnh sửa phần tử mảng trong database, đó là một bài toán update khác, dùng những toán tử như `$set`, `$push`, `$pull`, `$[]` hoặc `$[identifier]` với thiết kế kiểm soát ghi thích hợp.

### 10.4. Không mặc định projection làm truy vấn trở thành covered query

Projection có thể giảm dung lượng **kết quả trả về cho client**, nhưng máy chủ vẫn phải tìm document và xác định phần tử mảng khớp. Việc trả ít phần tử không tự bảo đảm index có thể phục vụ toàn bộ truy vấn mà không đọc document.

Đặc biệt với mảng, MongoDB có thể tạo **multikey index**; tuy nhiên việc projection trường mảng thường vẫn cần đọc nội dung document để xác định phần tử nào được trả về. Để hiểu hiệu năng thực tế, sử dụng:

~~~javascript
lab.courses.find(
  { "grades.score": { $gte: 90 } },
  { title: 1, "grades.$": 1 }
).explain("executionStats");
~~~

Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và mức I/O trên bộ dữ liệu thực tế. Ví dụ collection chỉ có năm document khó phản ánh hiệu quả index trong môi trường lớn.

### 10.5. Projection không phải cơ chế phân quyền

Một API dùng `{ title: 1, grades: { $slice: 1 } }` chỉ giảm trường được trả **ở lời gọi cụ thể**. Nếu cùng tài khoản có quyền đọc trực tiếp collection, client vẫn có thể gửi truy vấn khác để lấy toàn bộ mảng. Bảo vệ dữ liệu nhạy cảm phải dựa trên quyền truy cập, giới hạn API và cơ chế bảo mật của hệ thống, không chỉ dựa vào một projection.

### 10.6. Độ dài mảng lớn và thiết kế tài liệu

Nếu mảng như lịch sử hoạt động tăng mãi, `$slice` giúp giới hạn phần trả về nhưng **document gốc vẫn chứa toàn bộ mảng**. Giới hạn kích thước document BSON và chi phí sửa tài liệu không biến mất.

Với các lịch sử không giới hạn, cần cân nhắc tách thành collection riêng, áp dụng phân trang theo document và index phù hợp. Nếu nghiệp vụ luôn chỉ cần vài phần tử gần nhất, có thể cân nhắc thiết kế một mảng đã giới hạn độ dài từ lúc ghi, nhưng đó là quyết định mô hình dữ liệu riêng.

## 11. Các lỗi thường gặp

| Lỗi hoặc kết quả bất ngờ | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `$elemMatch` trả đúng một grade dù nhiều grade khớp | Projection `$elemMatch` chỉ trả **phần tử đầu tiên** | Dùng aggregation `$filter` khi cần tất cả |
| Document vẫn xuất hiện dù `$elemMatch` không khớp | Điều kiện đặt ở projection, không phải filter | Thêm điều kiện vào filter nếu cần loại document |
| Trường mảng bị bỏ khỏi kết quả | Không có phần tử khớp `$elemMatch` hoặc field vắng mặt | Xem điều kiện và phân biệt missing với `[]` |
| `$slice: -2` không trả mảng đảo ngược | Số âm lấy các phần tử cuối, giữ thứ tự gốc | Dùng phép biến đổi mảng phù hợp nếu cần đảo thứ tự |
| `$slice: [1, 2]` không bỏ qua một document | `$slice` cắt **phần tử trong mảng** | Dùng `cursor.skip()` cho document |
| Kết quả `$slice` còn nhiều trường hơn dự kiến | `$slice` đứng riêng là exclusion projection | Khai báo inclusion rõ: `{ title: 1, lessons: { $slice: 2 } }` |
| Positional `$` trả phần tử không đúng ý | Điều kiện filter áp dụng lên nhiều array field hoặc nhiều điều kiện không cùng phần tử | Dùng một điều kiện mảng rõ ràng, `$elemMatch` query khi cần |
| `"grades.$.score": 1` không hợp lệ | `$` phải đứng cuối field path | Dùng `"grades.$": 1` rồi xử lý object kết quả |
| Lỗi path collision | Chiếu `grades` bằng `$slice` và chiếu thêm `grades.student` cùng lúc | Dùng aggregation nhiều bước |
| Cố dùng `$slice` projection trong `$project` aggregation | Hai ngữ cảnh có cú pháp khác | Dùng `{ $slice: ["$grades", 2] }` |
| Cố cập nhật dữ liệu bằng `find()` projection | Projection chỉ ảnh hưởng nội dung đọc | Dùng update operator nếu mục tiêu là thay dữ liệu |
| Dùng projection chuyên biệt trên view | Các projection mảng này có giới hạn với `find()` trên view | Chuyển sang aggregation phù hợp |
| Muốn phần tử “điểm cao nhất” nhưng nhận phần tử đầu | `$elemMatch`, `$` và `$slice` không tự sắp xếp mảng | Sắp xếp mảng trước rồi mới chọn phần tử |

## 12. Bài tập thực hành

Các bài dưới đây dùng dữ liệu `lab.courses` ở mục 2; không cần cập nhật collection.

### Bài 1 — Lấy bài học đầu và cuối

Viết hai truy vấn cho khóa học `101`:

1. Trả `_id`, `title` và ba bài học đầu.
2. Trả `_id`, `title` và hai bài học cuối.

Gợi ý:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: 3 } }
);

lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: -2 } }
);
~~~

Kết quả `lessons` lần lượt là:

~~~javascript
["BSON", "CRUD", "Query"]
["Indexes", "Aggregation"]
~~~

### Bài 2 — Cắt theo vị trí

Từ khóa học `101`, bỏ hai bài đầu rồi lấy hai bài kế tiếp.

~~~javascript
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: [2, 2] }, _id: 1 }
);
~~~

Phần `lessons` trả về `["Query", "Indexes"]`. Vì projection gồm `$slice` và `_id: 1` nhưng không có một trường inclusion khác như `title: 1`, kết quả có thể vẫn chứa các trường khác; muốn chỉ trả `_id` và `lessons`, hãy dùng inclusion rõ ràng ở field không phải `_id` khi thích hợp, hoặc dùng aggregation `$project`.

### Bài 3 — Hiển thị học viên đầu tiên đạt điểm cao

Dùng projection `$elemMatch` tìm **grade đầu tiên có `score >= 90`** cho mọi khóa học đã `published`.

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: { $elemMatch: { score: { $gte: 90 } } }
  }
);
~~~

Xác định vì sao khóa học 104 và 105 vẫn xuất hiện nhưng không có field `grades` trong kết quả.

### Bài 4 — Lọc document và lấy phần tử cùng điều kiện

Chỉ lấy các khóa học có học viên vừa `passed: true` vừa `score >= 90`. Trả grade đầu tiên thỏa cả hai điều kiện bằng positional `$`.

~~~javascript
lab.courses.find(
  {
    grades: {
      $elemMatch: {
        passed: true,
        score: { $gte: 90 }
      }
    }
  },
  { title: 1, "grades.$": 1 }
);
~~~

Kết quả phải gồm khóa học `101` với `Chi` và `102` với `Hoa`.

### Bài 5 — $elemMatch đối với mảng số

Trên `ratings` của khóa học `101`, lấy số đầu tiên đạt `$gte: 4`.

~~~javascript
lab.courses.find(
  { _id: 101 },
  { ratings: { $elemMatch: { $gte: 4 } } }
);
~~~

Giải thích vì sao kết quả là `[5]` thay vì `[5, 4, 5]`.

### Bài 6 — Lấy tất cả phần tử thỏa điều kiện

Viết aggregation trả mọi grade có `score >= 85` của từng khóa học, giữ nguyên thứ tự mảng. Đối chiếu với `$elemMatch` projection để giải thích sự khác nhau giữa “tất cả phần tử” và “phần tử đầu tiên”.

~~~javascript
lab.courses.aggregate([
  {
    $project: {
      title: 1,
      gradesAtLeast85: {
        $filter: {
          input: { $ifNull: ["$grades", []] },
          as: "g",
          cond: { $gte: ["$$g.score", 85] }
        }
      }
    }
  }
]);
~~~

### Bài 7 — Tình huống API thực tế

Một endpoint liệt kê khóa học cần:

- Chỉ lấy document `published`.
- Trả `title`.
- Trả hai bài học đầu.
- Trả học viên đầu tiên đạt điểm từ 90 trở lên.
- Bỏ `_id` khỏi JSON phản hồi.

Viết projection kết hợp `$slice` và `$elemMatch` trên **hai trường mảng khác nhau**:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    _id: 0,
    title: 1,
    lessons: { $slice: 2 },
    grades: {
      $elemMatch: { score: { $gte: 90 } }
    }
  }
);
~~~

Hãy quan sát khóa học không có điểm >= 90: field `grades` có thể bị lược bỏ. Nếu API yêu cầu mọi phản hồi đều có `grades: []`, nên dùng aggregation để chuẩn hóa kết quả theo contract.

## 13. Những điểm cần ghi nhớ

- **`$elemMatch` projection** lấy **phần tử đầu tiên đạt điều kiện đặt ngay trong projection**. Không khớp thì trường mảng có thể bị bỏ khỏi kết quả, nhưng document vẫn được trả về nếu thỏa filter.
- **`$slice` projection** cắt **theo vị trí**, không lọc theo giá trị; số dương lấy đầu, số âm lấy cuối, mảng `[skip, limit]` cho phép chọn một đoạn.
- **Positional `$` projection** lấy **phần tử đầu tiên thỏa điều kiện mảng trong filter**, thường dùng kết hợp `$elemMatch` **query** nếu cần nhiều điều kiện cùng một phần tử.
- **`$filter` trong aggregation** phù hợp nếu cần **mọi phần tử thỏa điều kiện** hoặc xử lý array phức tạp; `$slice` expression và `$arrayElemAt` phục vụ các thao tác cắt/chọn theo vị trí trong pipeline.
- Projection chỉ định dạng **kết quả đọc**, không thay đổi dữ liệu đã lưu và không tự thay thế index, bảo mật hay thiết kế mô hình dữ liệu.

### Tài liệu tham khảo chính thức

- [Projection — MongoDB Manual](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/) — nguyên tắc inclusion/exclusion khi đọc document.
- [$elemMatch — Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/elemMatch/) — phần tử đầu tiên thỏa điều kiện projection.
- [$slice — Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/slice/) — lấy phần đầu, phần cuối và đoạn mảng.
- [$ — Positional Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/positional/) — lấy phần tử khớp filter và các giới hạn.
- [$elemMatch — Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — nhiều điều kiện trên cùng một phần tử mảng.
- [$filter — Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — giữ nhiều phần tử mảng thỏa điều kiện.
- [$slice — Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/slice/) — cắt mảng bên trong pipeline aggregation.
