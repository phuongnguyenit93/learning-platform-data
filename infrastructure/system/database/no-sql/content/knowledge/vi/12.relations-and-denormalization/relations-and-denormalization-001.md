# Biểu diễn quan hệ một-một, một-nhiều và nhiều-nhiều

## 1. Quan hệ vẫn tồn tại trong cơ sở dữ liệu NoSQL

**NoSQL không có nghĩa là không có quan hệ giữa dữ liệu.** Hệ thống quản lý người dùng, đơn hàng, sản phẩm, khóa học hoặc mạng xã hội đều phải biểu diễn sự liên hệ giữa những thực thể nghiệp vụ. Điều thay đổi là **cách lưu, truy xuất và duy trì quan hệ** có thể khác cơ sở dữ liệu quan hệ truyền thống.

Ví dụ nền tảng học trực tuyến có:

- Một người dùng sở hữu một bộ tùy chọn cá nhân.
- Một khóa học bao gồm nhiều bài học.
- Nhiều học viên có thể tham gia nhiều khóa học, và mỗi khóa học có nhiều học viên.

Ba tình huống tương ứng với:

| Kiểu quan hệ | Cách gọi | Ví dụ |
|---|---|---|
| **Một-một (1:1)** | One-to-one | Một tài khoản ↔ một hồ sơ cấu hình cá nhân |
| **Một-nhiều (1:N)** | One-to-many | Một khóa học → nhiều bài học |
| **Nhiều-nhiều (N:M)** | Many-to-many | Nhiều học viên ↔ nhiều khóa học |

Trong SQL, người học thường nghĩ đến khóa ngoại, unique constraint và bảng trung gian. Trong NoSQL, một quan hệ có thể được biểu diễn bằng **document lồng nhau, danh sách định danh tham chiếu, khóa ghép, collection trung gian, bảng đọc chuyên dụng hoặc cạnh đồ thị**.

Không phải kiểu quan hệ nào cũng nên dùng một hình thức lưu trữ cố định. Cùng một quan hệ 1:N có thể là mảng nhúng khi con nhỏ và có cùng vòng đời, nhưng cần collection riêng khi con tăng không giới hạn hoặc được cập nhật độc lập.

Mục tiêu của bài là biết **chọn đúng biểu diễn cho từng quan hệ dựa trên số lượng, vòng đời, mẫu truy cập và bảo đảm nhất quán**, đồng thời triển khai được bằng các mô hình NoSQL thông dụng.

## 2. Trước tiên, xác định đúng ý nghĩa của 1, N và M

### 2.1. Số lượng và tính bắt buộc

Một quan hệ không chỉ có “một” hay “nhiều”; còn có **số lượng tối thiểu** và **số lượng tối đa**.

Ví dụ:

- Mỗi người dùng có **0 hoặc 1** hồ sơ bổ sung: `User 1 → 0..1 Profile`.
- Mỗi đơn hàng có **ít nhất 1** dòng hàng: `Order 1 → 1..N OrderItem`.
- Mỗi học viên có thể tham gia **0..N** khóa học; mỗi khóa có thể có **0..M** học viên.

Hai quy tắc “tối đa một” và “bắt buộc phải có một” là khác nhau. Một **unique index** có thể giới hạn không có hai hồ sơ cùng `userId`; nó không tự bảo đảm mọi `User` đều có `Profile`.

### 2.2. Quan hệ có hướng nghiệp vụ

Quan hệ 1:N thường được mô tả từ cha tới con:

~~~text
Course --has--> Lesson
~~~

Nhưng ứng dụng cũng có thể truy vấn ngược:

~~~text
Lesson --belongs to--> Course
~~~

Định nghĩa “một khóa học có nhiều bài học” không nói rằng dữ liệu phải được lưu thành mảng trong Course. Nó chỉ mô tả **cardinality của nghiệp vụ**.

Với graph, hướng cạnh phải được quy ước rõ. Với document hoặc wide-column, hướng truy cập liên quan đến **khóa nào được chọn để tra cứu hiệu quả**.

### 2.3. Quan hệ có thể mang thuộc tính riêng

Ví dụ học viên đăng ký khóa học:

~~~text
Student --enrolls in--> Course
~~~

Bản thân mối quan hệ có thể có:

- Ngày đăng ký.
- Trạng thái `ACTIVE`, `COMPLETED`, `CANCELLED`.
- Vai trò `STUDENT` hoặc `TEACHING_ASSISTANT`.
- Phương thức thanh toán và mã chứng nhận.
- Tiến độ, điểm tổng kết hoặc trạng thái học lại.

Khi quan hệ có **thuộc tính, định danh và vòng đời riêng**, một **document/edge entity trung gian** thường phù hợp hơn việc chỉ nhét hai danh sách ID đối xứng vào hai phía.

## 3. Những cách biểu diễn quan hệ thường gặp trong NoSQL

| Cách biểu diễn | Hình thức dữ liệu | Phù hợp nhất khi | Điểm cần cân nhắc |
|---|---|---|---|
| **Nhúng (embedding)** | Đối tượng con hoặc mảng con nằm trong document cha | Con nhỏ, có giới hạn, cùng vòng đời và thường đọc cùng cha | Kích thước document, contention và cập nhật độc lập |
| **Tham chiếu (referencing)** | Lưu ID của thực thể liên quan | Thực thể có vòng đời riêng, dùng chung hoặc cần truy vấn độc lập | Thêm lần đọc, index, xử lý tham chiếu mồ côi |
| **Danh sách ID (adjacency list)** | `followingIds[]`, `memberIds[]` | Tập liên kết nhỏ, thường đọc từ một phía | Mảng lớn, cập nhật cạnh, truy vấn ngược |
| **Collection liên kết (association/edge collection)** | Một document cho mỗi cặp liên quan | N:M lớn, quan hệ có thuộc tính/trạng thái | Thêm collection, index hai chiều và sự nhất quán |
| **Bảng đọc theo mẫu truy cập** | `lessons_by_course`, `courses_by_student` | Wide-column/key-value cần truy vấn nhanh theo khóa đã biết | Dữ liệu lặp và đồng bộ nhiều bảng |
| **Cạnh property graph** | `(Student)-[:ENROLLED_IN]->(Course)` | Duyệt nhiều bước và truy vấn mạng quan hệ | Hướng cạnh, tính chọn lọc, bậc node lớn và giới hạn traversal |

**Đọc và ghi đều quan trọng.** Một biểu diễn tối ưu truy vấn “tìm tất cả bài học của khóa này” có thể không tối ưu “tìm khóa học của bài học này” hoặc “tìm khóa học chứa các bài do tác giả X tạo”.

## 4. Nguyên tắc chọn biểu diễn trước khi đi vào từng loại

Nên trả lời sáu câu hỏi:

1. **Vòng đời:** Xóa cha có phải xóa con? Con có cần tồn tại độc lập không?
2. **Kích thước:** Một phía có tối đa bao nhiêu đối tượng liên quan, và sau ba năm sẽ là bao nhiêu?
3. **Mẫu đọc:** Thường đọc một phía kèm phía kia, hay truy vấn mỗi phía độc lập?
4. **Mẫu ghi:** Cập nhật hai phía có cần nguyên tử không? Có bao nhiêu tác nhân ghi đồng thời?
5. **Nhất quán:** Nếu một phía thay đổi trước, phía còn lại được phép chậm bao lâu?
6. **Định danh và phân quyền:** Quan hệ có ID, trạng thái, thời hạn hay chính sách quyền truy cập riêng không?

Sơ đồ định hướng:

~~~mermaid
flowchart TD
  A["Xác định cardinality và truy vấn"] --> B{"Đối tượng liên quan có cùng vòng đời, nhỏ và có giới hạn?"}
  B -->|"Có"| C["Cân nhắc embedding"]
  B -->|"Không"| D{"Quan hệ có nhiều cạnh hoặc metadata/vòng đời riêng?"}
  D -->|"Có"| E["Cân nhắc edge/association collection hoặc graph edge"]
  D -->|"Không"| F["Cân nhắc tham chiếu ID"]
  C --> G["Đánh giá cập nhật đồng thời và giới hạn document"]
  E --> H["Thiết kế index theo cả hai chiều truy vấn"]
  F --> H
  G --> I["Đo chi phí đọc, ghi, lưu trữ và tính nhất quán"]
  H --> I
~~~

Sơ đồ chỉ giúp suy nghĩ. Có những trường hợp dữ liệu con cùng vòng đời nhưng quá lớn, hoặc một quan hệ có metadata đơn giản vẫn phù hợp là property trên cạnh graph. Không nên quyết định chỉ bằng một điều kiện.

---

## 5. Quan hệ một-một (1:1)

### 5.1. Ví dụ nghiệp vụ

Một tài khoản có tối đa một bộ tùy chọn:

~~~text
User (userId = u1)
  └── Preferences (language, theme, digest)
~~~

Quan hệ có thể là **1:1 bắt buộc** nếu tạo User và Preferences cùng lúc; hoặc **1:0..1** nếu người dùng chưa thiết lập tùy chọn.

Có ba lựa chọn phổ biến: **nhúng**, **tách document dùng cùng khóa**, hoặc **tham chiếu bằng một ID riêng**.

### 5.2. Cách A — Nhúng vào document chính

~~~json
{
  "_id": "user-101",
  "displayName": "Lan",
  "email": "lan@example.test",
  "preferences": {
    "language": "vi",
    "theme": "dark",
    "weeklyDigest": true
  }
}
~~~

Ưu điểm:

- Đọc hồ sơ và tùy chọn thường chỉ cần một document.
- Cập nhật vài thuộc tính liên quan trong một document có thể tận dụng bảo đảm ghi nguyên tử cấp document nếu DBMS hỗ trợ.
- Không cần tham chiếu thứ hai để truy vấn tùy chọn.
- Xóa User đồng thời loại bỏ dữ liệu nhúng trong cùng tài liệu.

Ví dụ MongoDB:

~~~javascript
db.users.updateOne(
  { _id: "user-101" },
  {
    $set: {
      "preferences.theme": "light",
      "preferences.weeklyDigest": false
    }
  }
);
~~~

Đây là ví dụ thích hợp nếu Preferences có kích thước nhỏ, thuộc riêng User, thường được tải cùng hồ sơ.

**Không nên nhúng chỉ vì cardinality là 1:1.** Nếu phần dữ liệu có quyền truy cập, vòng đời, tần suất ghi hoặc dung lượng rất khác User, tách document có thể hợp lý hơn.

### 5.3. Cách B — Hai document dùng cùng định danh

Ví dụ:

~~~json
{
  "_id": "user-101",
  "displayName": "Lan",
  "email": "lan@example.test"
}
~~~

~~~json
{
  "_id": "user-101",
  "language": "vi",
  "theme": "dark",
  "weeklyDigest": true
}
~~~

Document đầu thuộc collection `users`; document sau thuộc `user_preferences`. Hai collection khác nhau nên có thể cùng dùng `_id = "user-101"` mà không xung đột.

Cách này biểu diễn ý tưởng: “Một User được định danh bằng khóa X và Preferences của User đó cũng có khóa X”.

Ví dụ truy vấn:

~~~javascript
db.users.findOne({ _id: "user-101" });
db.user_preferences.findOne({ _id: "user-101" });
~~~

Ưu điểm:

- Dữ liệu cấu hình có thể được truy cập và cập nhật độc lập.
- Có thể áp chính sách truy cập hoặc retention khác nhau tùy hệ.
- Dễ tránh tải Preferences khi chỉ cần thông tin hồ sơ ngắn.

Đánh đổi:

- Đọc cả hai có thể cần nhiều thao tác hoặc phép ghép được DBMS hỗ trợ.
- Xóa User không nhất thiết xóa Preferences tự động.
- Tạo hai document không mặc nhiên nguyên tử; có thể xuất hiện User nhưng chưa có Preferences nếu không có transaction/quy trình phù hợp.

**Cùng ID không tự tạo khóa ngoại** trong MongoDB hoặc nhiều document DBMS khác. Phải kiểm soát sự tồn tại, dọn dữ liệu mồ côi và thứ tự tạo/xóa.

### 5.4. Cách C — Document 1:1 với ID riêng và unique constraint

Có thể muốn Preferences có định danh và version độc lập:

~~~json
{
  "_id": "pref-9001",
  "userId": "user-101",
  "language": "vi",
  "theme": "dark",
  "version": 3
}
~~~

Để không tạo hai Preferences cho cùng một User, trên MongoDB có thể tạo:

~~~javascript
db.user_preferences.createIndex(
  { userId: 1 },
  { unique: true }
);
~~~

Nếu mọi Preferences **đều có `userId` bắt buộc**, unique index trên trường này giúp bảo đảm mỗi giá trị `userId` xuất hiện tối đa một lần trong collection. Nếu `userId` là tùy chọn hoặc có `null`, cần xem chính sách index và validation; trong MongoDB một unique single-field index không tự cho phép vô hạn document thiếu trường hoặc có giá trị null giống nhau. Có thể cân nhắc **partial unique index** khi yêu cầu nghiệp vụ có phần tử không liên kết.

Một unique constraint trên `userId` chỉ bảo đảm **tối đa một Preferences theo ID User**; nó không tự bảo đảm rằng User được tham chiếu tồn tại hoặc luôn có Preferences.

### 5.5. Khi nào nên tách dữ liệu 1:1?

Ví dụ tài khoản có một tập **thông tin xác thực nhạy cảm** hoặc hồ sơ được cập nhật bởi một hệ khác. Dù logic là 1:1, không nên mặc định nhúng cùng document thường xuyên được đọc cho giao diện. Tách giúp hạn chế phạm vi dữ liệu trả về và cách áp dụng quyền.

Với dữ liệu nhạy cảm, **tách collection không thay thế kiểm tra quyền và mã hóa**. Chỉ nên minh họa bằng metadata không nhạy cảm; không đưa mật khẩu thật, khóa bí mật hoặc token vào mẫu dữ liệu.

### 5.6. So sánh ba cách lưu 1:1

| Tiêu chí | Nhúng trong User | Tách cùng `_id` | Tách với `userId` unique |
|---|---|---|---|
| Đọc cả hai | Rất thuận tiện | Có thể thêm lần đọc | Có thể thêm lần đọc |
| Đọc Preferences độc lập | Phải đọc trường trong User | Truy vấn bằng cùng ID | Truy vấn bằng userId/index |
| Vòng đời | Thường gắn chặt User | Có thể độc lập | Có thể độc lập |
| Tính nguyên tử một lần cập nhật | Trong phạm vi document | Qua hai document cần cơ chế tương ứng | Tương tự |
| Giới hạn 1:1 | Tự nhiên trong cấu trúc nhúng | Mỗi `_id` duy nhất trong collection | Cần unique index trên `userId` |
| Dữ liệu có quyền/retention khác | Có thể bất tiện | Linh hoạt hơn | Linh hoạt hơn |

## 6. Quan hệ một-nhiều (1:N): nhúng hay tham chiếu?

### 6.1. Ví dụ khóa học và bài học

Một khóa học có nhiều bài:

~~~text
Course "nosql-basic"
  ├── Lesson "intro"
  ├── Lesson "document"
  ├── Lesson "wide-column"
  └── Lesson "graph"
~~~

Một Lesson thuộc một Course theo quy tắc của ví dụ, nhưng Course có thể có rất nhiều Lesson. Câu hỏi quan trọng:

- Mỗi khóa học có tối đa bao nhiêu bài?
- Các bài dài bao nhiêu?
- Chúng được sửa riêng hay luôn phát hành cùng khóa học?
- API có thường lấy toàn bộ nội dung bài cùng metadata khóa học không?
- Có cần truy vấn Lesson độc lập bằng ID không?

### 6.2. Cách A — Nhúng danh sách con

Với một khóa học ngắn và mỗi bài chỉ có metadata nhỏ:

~~~json
{
  "_id": "course-nosql",
  "title": "Nhập môn NoSQL",
  "chapters": [
    {
      "chapterId": "ch-1",
      "title": "Tổng quan",
      "position": 1
    },
    {
      "chapterId": "ch-2",
      "title": "Mô hình dữ liệu",
      "position": 2
    }
  ]
}
~~~

Ưu điểm:

- Một lần đọc Course trả về luôn mục lục.
- Thứ tự nội dung nằm trong cùng một document.
- Nếu danh sách nhỏ và thay đổi cùng Course, cập nhật có thể đơn giản.

Nhược điểm:

- Mảng lớn dần khiến document tăng dung lượng.
- Nhiều người cùng cập nhật mục lục có thể tạo tranh chấp.
- Tìm một chương hoặc chỉnh sửa độc lập có thể khó hơn so với document con.
- Hạn chế về kích thước document tùy DBMS.

**Nhúng mảng không đồng nghĩa phải nhúng toàn bộ nội dung Lesson.** Có thể nhúng mục lục có giới hạn nhưng lưu các Lesson dài ở collection riêng.

### 6.3. Cách B — Mỗi con là document có tham chiếu cha

Tài liệu Course:

~~~json
{
  "_id": "course-nosql",
  "title": "Nhập môn NoSQL"
}
~~~

Các Lesson:

~~~json
{
  "_id": "lesson-1",
  "courseId": "course-nosql",
  "title": "Tổng quan",
  "position": 1,
  "content": "..."
}
~~~

~~~json
{
  "_id": "lesson-2",
  "courseId": "course-nosql",
  "title": "Mô hình dữ liệu",
  "position": 2,
  "content": "..."
}
~~~

Cách này phù hợp nếu Lesson:

- Có nội dung dài hoặc kích thước biến thiên.
- Được sửa và xuất bản độc lập.
- Có version hoặc audit riêng.
- Cần truy vấn, phân trang hoặc lập chỉ mục riêng.
- Có số lượng lớn khiến embedding kém phù hợp.

Khi cần danh sách Lesson, ứng dụng lọc theo `courseId` và sắp theo `position`.

Ví dụ MongoDB:

~~~javascript
db.lessons.find(
  { courseId: "course-nosql" },
  { _id: 1, title: 1, position: 1 }
).sort({ position: 1, _id: 1 }).limit(50);
~~~

Tạo index phù hợp:

~~~javascript
db.lessons.createIndex({
  courseId: 1,
  position: 1,
  _id: 1
});
~~~

`courseId` là khóa lọc bằng, `position` và `_id` phục vụ thứ tự ổn định. Khi hai Lesson có cùng `position`, `_id` tạo tie-breaker. Nếu nghiệp vụ **không cho hai Lesson cùng vị trí trong một Course**, cần ràng buộc riêng thay vì chỉ dựa vào tie-breaker:

~~~javascript
db.lessons.createIndex(
  { courseId: 1, position: 1 },
  { unique: true }
);
~~~

Chỉ tạo unique index này nếu nghiệp vụ thật sự yêu cầu mỗi vị trí xuất hiện tối đa một lần. Khi đổi thứ tự nhiều Lesson, phải thiết kế cách hoán vị vị trí để không vi phạm uniqueness trong trạng thái trung gian.

### 6.4. Cách C — Document cha chứa danh sách ID con

~~~json
{
  "_id": "course-nosql",
  "title": "Nhập môn NoSQL",
  "lessonIds": ["lesson-1", "lesson-2"]
}
~~~

Ưu điểm: đọc Course có danh sách ID theo thứ tự để truy vấn các Lesson tương ứng. Nhưng khi số Lesson tăng:

- Mảng ID có thể trở nên lớn.
- Mỗi lần thêm/xóa Lesson phải cập nhật Course và Lesson hoặc đảm bảo quy tắc sở hữu.
- Có thể phát sinh ID trỏ đến Lesson đã xóa.
- Truy vấn ngược “Lesson này thuộc Course nào?” cần index/thuộc tính tương ứng.

Với quan hệ 1:N không giới hạn, **đặt khóa cha trên từng document con** thường dễ mở rộng hơn giữ toàn bộ ID con trong cha. Nếu cần mục lục để đọc nhanh, có thể lưu **bản chiếu nhỏ** trong cha kèm chính sách đồng bộ rõ ràng.

### 6.5. Đơn hàng và dòng hàng: trường hợp nhúng có lợi

Không phải mọi quan hệ 1:N đều nên tách. Với đơn hàng bán lẻ có số item được giới hạn:

~~~json
{
  "_id": "order-1001",
  "customerId": "customer-42",
  "status": "CONFIRMED",
  "items": [
    {
      "lineId": "1",
      "productId": "product-8",
      "productNameAtPurchase": "Chuột không dây",
      "unitPriceVnd": 450000,
      "quantity": 2
    },
    {
      "lineId": "2",
      "productId": "product-21",
      "productNameAtPurchase": "Bàn di chuột",
      "unitPriceVnd": 150000,
      "quantity": 1
    }
  ],
  "totalVnd": 1050000
}
~~~

Dòng hàng thường được tạo cùng đơn, thuộc về đơn và được đọc cùng đơn. Nhúng giúp:

- Giảm số request khi hiển thị chi tiết.
- Lưu snapshot tên/giá tại thời điểm mua.
- Có thể ghi/cập nhật nhóm trường trong một document theo bảo đảm của DBMS.

Nhưng danh mục `Product` vẫn có vòng đời độc lập; `productId` chỉ tham chiếu đến sản phẩm hiện tại. Không nên cập nhật `unitPriceVnd` của đơn cũ khi catalog đổi giá.

**Snapshot lịch sử** là bản sao có chủ đích khác với **bản sao dữ liệu hiện tại cần đồng bộ**.

### 6.6. Mảng một-nhiều không giới hạn

Trường hợp một bài viết có thể nhận hàng triệu bình luận:

~~~text
Post -> Comment 1
     -> Comment 2
     -> ...
     -> Comment 1.000.000
~~~

Nhúng tất cả vào `comments[]` có thể gây:

- Document rất lớn hoặc vượt giới hạn.
- Mỗi bình luận mới đều cập nhật cùng document cha.
- Khó phân trang và tìm theo tác giả.
- Khó áp TTL, quyền hoặc trạng thái kiểm duyệt riêng.
- Tăng contention và chi phí vận hành.

Thay vì vậy, lưu Comment riêng với `postId` và index phục vụ phân trang:

~~~json
{
  "_id": "comment-9001",
  "postId": "post-101",
  "authorId": "user-5",
  "content": "Bài viết hữu ích!",
  "createdAt": "2026-11-14T08:15:27Z"
}
~~~

~~~javascript
db.comments.createIndex({
  postId: 1,
  createdAt: -1,
  _id: -1
});
~~~

Nếu cần preview, có thể nhúng **3–5 bình luận mới nhất** vào Post như bản chiếu giới hạn, trong khi nguồn đầy đủ là collection Comment. Khi đó phải ghi rõ cách duy trì preview và mức độ trễ chấp nhận được.

MongoDB có giới hạn **16 MiB cho một BSON document**; hệ NoSQL khác có giới hạn riêng. Giới hạn cứng không phải mức nên nhắm tới: document lớn có thể gây tốn băng thông, chỉ mục hoặc tranh chấp từ trước khi chạm trần.

## 7. Quan hệ một-nhiều trong wide-column: partition và clustering

Trong hệ wide-column như Cassandra, quan hệ 1:N thường được biểu diễn bằng **một partition key cho cha** và **clustering key cho con**, nếu số lượng và kích thước trong partition được kiểm soát.

Ví dụ lưu các Lesson của một Course:

~~~sql
CREATE TABLE lessons_by_course (
    course_id text,
    lesson_position int,
    lesson_id text,
    title text,
    published_at timestamp,
    PRIMARY KEY ((course_id), lesson_position, lesson_id)
) WITH CLUSTERING ORDER BY (
    lesson_position ASC,
    lesson_id ASC
);
~~~

Truy vấn:

~~~sql
SELECT lesson_id, title, lesson_position
FROM lessons_by_course
WHERE course_id = 'course-nosql'
LIMIT 50;
~~~

Trong bảng trên:

- `course_id` là partition key; một Course tương ứng một partition logic.
- `lesson_position` và `lesson_id` là clustering columns, hỗ trợ thứ tự trong partition.
- Truy vấn danh sách Lesson của một Course thuận tiện.

Tuy nhiên:

- Nếu Course có số hàng rất lớn hoặc dữ liệu Lesson quá nặng, partition có thể tăng quá mức.
- Nếu một Course cực phổ biến và nhiều tác nhân cập nhật cùng lúc, nó có thể trở thành điểm nóng.
- Nếu cần truy vấn Lesson theo `lesson_id` mà không biết `course_id`, bảng này không tự là đường truy vấn theo ID tối ưu.

Có thể tạo bảng đọc riêng:

~~~sql
CREATE TABLE lesson_by_id (
    lesson_id text PRIMARY KEY,
    course_id text,
    lesson_position int,
    title text,
    published_at timestamp
);
~~~

Đây là ví dụ **dữ liệu lặp theo mẫu truy vấn**. Khi tiêu đề thay đổi, ứng dụng có thể phải cập nhật cả hai bảng; không nên mặc định ghi hai bảng độc lập được đồng bộ nguyên tử. Cần mô tả source of truth, idempotency, retry và đối soát.

### 7.1. Giới hạn tăng trưởng partition

Nếu mỗi Course có vài chục Lesson, partition theo `course_id` thường dễ hiểu. Nhưng với một luồng sự kiện 1:N có hàng triệu sự kiện, nên cân nhắc **time bucket**:

~~~text
Partition key = (deviceId, eventDay)
Clustering    = (occurredAt, eventId)
~~~

Time bucket chia dữ liệu thành các partition có vòng đời theo kỳ. Nếu một kỳ hiện tại vẫn quá nóng, có thể cần hash bucket; đổi lại truy vấn phải đọc nhiều partition rồi ghép. Cardinality nghiệp vụ 1:N không thay đổi, nhưng cách lưu vật lý được thiết kế để phân tán tải.

---

## 8. Quan hệ nhiều-nhiều (N:M): tại sao cần thiết kế cẩn thận?

Một học viên có thể đăng ký nhiều khóa học, một khóa học có thể có nhiều học viên:

~~~mermaid
flowchart LR
  A["Student An"] --> C1["Course NoSQL"]
  A --> C2["Course Java"]
  B["Student Bình"] --> C1
  B --> C3["Course DevOps"]
  D["Student Chi"] --> C1
  D --> C2
~~~

Những cách biểu diễn có thể lựa chọn:

1. Mảng ID khóa học trong từng Student.
2. Mảng ID học viên trong từng Course.
3. Hai phía đều giữ mảng ID.
4. Một collection **Enrollment** làm thực thể quan hệ.
5. Một cặp bảng read model theo từng hướng truy vấn.
6. Cạnh `ENROLLED_IN` trong property graph.

Chọn cách nào phụ thuộc **khối lượng quan hệ**, cách truy vấn hai chiều và các thuộc tính trên quan hệ.

### 8.1. Cách A — Mảng ID trên một phía

Student:

~~~json
{
  "_id": "student-101",
  "displayName": "An",
  "courseIds": [
    "course-nosql",
    "course-java"
  ]
}
~~~

Ưu điểm:

- Đọc những khóa mà một Student tham gia từ một document.
- Dễ triển khai nếu mỗi Student chỉ có ít liên kết.
- Có thể thêm/xóa ID bằng toán tử cập nhật mảng.

Ví dụ MongoDB:

~~~javascript
db.students.updateOne(
  { _id: "student-101" },
  { $addToSet: { courseIds: "course-devops" } }
);
~~~

`$addToSet` tránh thêm giá trị trùng vào mảng theo phép so sánh phần tử của MongoDB, nhưng nó **không kiểm tra Course có tồn tại**, và không tự lưu metadata như ngày đăng ký, trạng thái hay tiến độ.

Nhược điểm quan trọng: tìm **mọi Student của một Course** cần một đường truy vấn khác:

~~~javascript
db.students.find(
  { courseIds: "course-nosql" },
  { _id: 1, displayName: 1 }
);
~~~

Có thể tạo index trên mảng `courseIds`, nhưng mảng lớn và số liên kết nhiều có thể làm index tăng, cập nhật document lớn và phân trang các thành viên khó hơn.

### 8.2. Cách B — Hai phía đều có mảng ID

Student:

~~~json
{
  "_id": "student-101",
  "courseIds": ["course-nosql"]
}
~~~

Course:

~~~json
{
  "_id": "course-nosql",
  "studentIds": ["student-101", "student-202"]
}
~~~

Mỗi chiều có danh sách truy cập nhanh, nhưng một thao tác đăng ký phải cập nhật **cả Student và Course**. Nếu một cập nhật thành công, cập nhật còn lại thất bại, hai danh sách có thể mâu thuẫn:

~~~text
Student.courseIds có course-nosql
Course.studentIds không có student-101
~~~

Vì vậy cách lưu hai phía cần quyết định:

- Có dùng transaction nhiều document hay không?
- Nếu dùng đồng bộ bất đồng bộ, bên nào là source of truth?
- Retry có tạo trùng hoặc ghi đè không?
- Dữ liệu lệch được phát hiện và sửa như thế nào?
- Mảng phía Course có thể có hàng trăm nghìn thành viên không?

**Không nên nhân đôi hai mảng ID như hai nguồn sự thật độc lập** chỉ để tránh một truy vấn, nhất là khi cardinality lớn.

### 8.3. Cách C — Collection Enrollment trung gian

Một cách phổ biến và linh hoạt hơn là tạo một document cho mỗi quan hệ Student–Course:

~~~json
{
  "_id": "enroll-student101-nosql",
  "studentId": "student-101",
  "courseId": "course-nosql",
  "enrolledAt": "2026-11-14T08:15:27Z",
  "status": "ACTIVE",
  "role": "STUDENT",
  "progressPercent": 35
}
~~~

Trong ví dụ, Enrollment là **thực thể quan hệ**. Nó chứa thuộc tính của hành động đăng ký, có vòng đời và truy vấn riêng.

Đây là cách biểu diễn N:M bằng việc chuyển nó thành hai quan hệ 1:N:

~~~text
Student 1 ---- N Enrollment N ---- 1 Course
~~~

Mỗi Enrollment thuộc một Student và một Course, nhưng một Student/Course có thể liên hệ với nhiều Enrollment.

### 8.4. Chặn đăng ký trùng

Nếu nghiệp vụ quy định một Student chỉ có **tối đa một Enrollment hiện hành/duy nhất cho mỗi Course** và không cần nhiều lần đăng ký lịch sử, có thể tạo unique index:

~~~javascript
db.enrollments.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true }
);
~~~

Lệnh ghi idempotent:

~~~javascript
db.enrollments.updateOne(
  {
    studentId: "student-101",
    courseId: "course-nosql"
  },
  {
    $setOnInsert: {
      status: "ACTIVE",
      role: "STUDENT",
      progressPercent: 0,
      enrolledAt: new Date()
    }
  },
  { upsert: true }
);
~~~

`$setOnInsert` đặt giá trị khi insert mới, không ghi đè Enrollment đã có. Với unique index trên cặp khóa, hai request cạnh tranh có thể gặp **duplicate-key error** trong trường hợp race; ứng dụng cần xử lý trường hợp đó bằng đọc lại hoặc retry có kiểm soát.

Nếu nghiệp vụ cho phép học lại nhiều lần và lưu lịch sử nhiều kỳ, unique index trên cặp `(studentId, courseId)` sẽ không còn đúng. Khi đó cần một quan hệ có `attemptId` hoặc `enrollmentId`, cùng quy tắc **một đăng ký ACTIVE hay nhiều đăng ký song song** được mô hình hóa rõ.

**Unique index bảo đảm không có hai cặp trùng trong collection, không thay thế kiểm tra Student và Course có tồn tại.**

### 8.5. Index cho truy vấn hai chiều

Truy vấn **những Course của một Student**, mới đăng ký trước:

~~~javascript
db.enrollments.find(
  { studentId: "student-101", status: "ACTIVE" },
  { courseId: 1, enrolledAt: 1, role: 1 }
).sort({ enrolledAt: -1, _id: -1 }).limit(20);
~~~

Index phù hợp:

~~~javascript
db.enrollments.createIndex({
  studentId: 1,
  status: 1,
  enrolledAt: -1,
  _id: -1
});
~~~

Truy vấn **những Student của một Course**:

~~~javascript
db.enrollments.find(
  { courseId: "course-nosql", status: "ACTIVE" },
  { studentId: 1, enrolledAt: 1, role: 1 }
).sort({ enrolledAt: -1, _id: -1 }).limit(50);
~~~

Index theo chiều còn lại:

~~~javascript
db.enrollments.createIndex({
  courseId: 1,
  status: 1,
  enrolledAt: -1,
  _id: -1
});
~~~

Cần đặt điều kiện lọc và thứ tự theo **query thực tế**. Index có chi phí lưu trữ và ghi; không nên tạo hàng loạt chỉ mục cho mọi tổ hợp không có nhu cầu.

### 8.6. Lấy dữ liệu đích sau khi đọc Enrollment

Kết quả truy vấn Enrollment chỉ có `courseId`, không nhất thiết có tiêu đề khóa học. Ứng dụng có thể:

1. Đọc Enrollment theo Student và phân trang.
2. Lấy các Course theo tập `courseId`.
3. Trả kết quả theo thứ tự Enrollment, xử lý Course bị xóa/ẩn.

Hoặc dùng aggregation của MongoDB như `$lookup` khi phù hợp:

~~~javascript
db.enrollments.aggregate([
  {
    $match: {
      studentId: "student-101",
      status: "ACTIVE"
    }
  },
  { $sort: { enrolledAt: -1, _id: -1 } },
  { $limit: 20 },
  {
    $lookup: {
      from: "courses",
      localField: "courseId",
      foreignField: "_id",
      as: "course"
    }
  },
  { $unwind: "$course" },
  {
    $project: {
      _id: 0,
      courseId: 1,
      enrolledAt: 1,
      "course.title": 1
    }
  }
]);
~~~

Ví dụ này giả định `courses._id` có cùng kiểu và giá trị với `enrollments.courseId`. `$unwind` như trên **loại Enrollment không có Course khớp**; nếu cần giữ quan hệ mồ côi để điều tra, hãy dùng quy tắc khác. Đồng thời nếu Course đã bị xóa/ẩn, kết quả phải tuân thủ quyền truy cập và chính sách nghiệp vụ.

**Aggregation có `$lookup` không biến MongoDB thành hệ khóa ngoại ràng buộc tự động.** Khả năng ghép, hiệu năng, giới hạn và phân phối phụ thuộc index/phiên bản/cấu hình.

### 8.7. Khi quan hệ cần nhiều lần đăng ký lịch sử

Giả sử một Student học lại Course hai lần:

~~~json
{
  "_id": "enrollment-001",
  "studentId": "student-101",
  "courseId": "course-nosql",
  "attemptNo": 1,
  "status": "COMPLETED",
  "enrolledAt": "2026-01-10T08:00:00Z",
  "completedAt": "2026-03-01T08:00:00Z"
}
~~~

~~~json
{
  "_id": "enrollment-002",
  "studentId": "student-101",
  "courseId": "course-nosql",
  "attemptNo": 2,
  "status": "ACTIVE",
  "enrolledAt": "2026-11-14T08:00:00Z"
}
~~~

Khi đó mỗi lần đăng ký là **một thực thể riêng**. Có thể cần unique index trên `(studentId, courseId, attemptNo)`, còn quy tắc “tối đa một ACTIVE” phải được thực thi bằng ràng buộc hoặc luồng nghiệp vụ phù hợp.

Bản chất quan hệ Student–Course vẫn là N:M, nhưng có thêm nhiều **sự kiện/phiên bản của quan hệ** theo thời gian. Không nên coi tất cả Enrollment là một cạnh đơn giản nếu hệ phải giữ lịch sử đầy đủ.

---

## 9. Quan hệ nhiều-nhiều trong mô hình cột rộng

Trong Cassandra, việc truy vấn theo cả hai chiều thường dẫn tới **hai bảng đọc**:

- `courses_by_student`: tìm khóa học của một học viên.
- `students_by_course`: tìm học viên của một khóa học.

Ví dụ:

~~~sql
CREATE TABLE courses_by_student (
    student_id text,
    course_id text,
    status text,
    enrolled_at timestamp,
    PRIMARY KEY ((student_id), course_id)
);
~~~

~~~sql
CREATE TABLE students_by_course (
    course_id text,
    student_id text,
    status text,
    enrolled_at timestamp,
    PRIMARY KEY ((course_id), student_id)
);
~~~

Query theo học viên:

~~~sql
SELECT course_id, status, enrolled_at
FROM courses_by_student
WHERE student_id = 'student-101';
~~~

Query theo khóa học:

~~~sql
SELECT student_id, status, enrolled_at
FROM students_by_course
WHERE course_id = 'course-nosql';
~~~

Hai bảng chứa thông tin Enrollment lặp ở hai hướng. Lợi ích là mỗi truy vấn có thể định vị đúng partition key. Chi phí là khi đăng ký/hủy/đổi trạng thái, ứng dụng phải **duy trì hai bảng nhất quán theo hợp đồng phù hợp**.

Cassandra không cung cấp **foreign key constraint** tương tự SQL RDBMS cho kiểu quan hệ này. Một số cơ chế batch trong Cassandra không nên bị hiểu là transaction SQL với khả năng cô lập mọi đọc và ghi trên nhiều partition. Nếu cần tính đúng đắn nghiệp vụ chặt, phải thiết kế source of truth, consistency, conditional updates/LWT theo khả năng cụ thể, idempotency và quy trình đối soát.

### 9.1. Cẩn thận với một Course quá đông thành viên

Nếu một Course có hàng triệu học viên, partition theo `course_id` có thể quá lớn hoặc nóng. Có thể dùng bucket:

~~~text
Partition key = (courseId, bucket)
Clustering    = studentId
bucket = stableHash(studentId) mod N
~~~

Cách này phân tán liên kết của Course qua N partition, nhưng truy vấn “tất cả học viên của Course” phải đọc các bucket liên quan rồi merge và phân trang. Lượng bucket phải dựa trên tải và giới hạn thực tế.

Nếu truy vấn chính là “danh sách học viên đăng ký mới nhất”, bảng với clustering theo `studentId` không hỗ trợ trực tiếp thứ tự thời gian đăng ký; có thể cần bảng khác với `enrolledAt` và một tie-breaker ổn định. Đây là ví dụ tại sao **cardinality N:M không đủ để xác định primary key**.

### 9.2. Tạo nhiều bảng theo truy vấn là sự đánh đổi

| Lợi ích | Chi phí |
|---|---|
| Đọc theo từng hướng bằng partition key rõ ràng | Dữ liệu quan hệ được nhân bản |
| Có thể chọn clustering order đúng API | Mỗi lần đổi quan hệ cập nhật nhiều bảng |
| Có thể phân tán tải theo khóa phù hợp | Migration khi đổi key/bucket phức tạp |
| Có thể giới hạn dữ liệu của một lần đọc | Cần đối soát bản sao và xử lý lỗi ghi |

**Đừng coi hai bảng đọc là hai nguồn dữ liệu độc lập ngang hàng.** Quy định một nguồn nghiệp vụ đáng tin, hoặc một giao thức cập nhật có bảo đảm rõ ràng.

## 10. Quan hệ trong mô hình đồ thị: cạnh là thành phần hạng nhất

Property graph lưu quan hệ như một đối tượng có **kiểu, hướng và thuộc tính**:

~~~cypher
(:Student {studentId: 'student-101'})
  -[:ENROLLED_IN {status: 'ACTIVE'}]->
(:Course {courseId: 'course-nosql'})
~~~

Trong Neo4j, đây là hình thức quen thuộc để biểu diễn N:M. Một Student có thể có nhiều cạnh `ENROLLED_IN` đến các Course; một Course có thể nhận nhiều cạnh từ các Student.

### 10.1. Tạo dữ liệu với Cypher

~~~cypher
CREATE CONSTRAINT student_id_unique IF NOT EXISTS
FOR (s:Student)
REQUIRE s.studentId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT course_id_unique IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseId IS UNIQUE;
~~~

~~~cypher
MERGE (s1:Student {studentId: 'student-101'})
SET s1.name = 'An';

MERGE (s2:Student {studentId: 'student-202'})
SET s2.name = 'Bình';

MERGE (c1:Course {courseId: 'course-nosql'})
SET c1.title = 'Nhập môn NoSQL';

MERGE (c2:Course {courseId: 'course-java'})
SET c2.title = 'Java cơ bản';
~~~

Tạo các cạnh:

~~~cypher
MATCH (an:Student {studentId: 'student-101'})
MATCH (binh:Student {studentId: 'student-202'})
MATCH (nosql:Course {courseId: 'course-nosql'})
MATCH (java:Course {courseId: 'course-java'})
MERGE (an)-[e1:ENROLLED_IN]->(nosql)
  ON CREATE SET e1.enrolledAt = datetime(),
                e1.status = 'ACTIVE'
MERGE (an)-[e2:ENROLLED_IN]->(java)
  ON CREATE SET e2.enrolledAt = datetime(),
                e2.status = 'ACTIVE'
MERGE (binh)-[e3:ENROLLED_IN]->(nosql)
  ON CREATE SET e3.enrolledAt = datetime(),
                e3.status = 'ACTIVE';
~~~

`MERGE` trên mẫu cạnh giữa hai node cố định giúp tìm hoặc tạo một cạnh phù hợp với kiểu và hướng chỉ định. Trong hệ có nhiều writer đồng thời, muốn **bảo đảm không trùng cạnh theo nghiệp vụ** cần xem transaction, định danh quan hệ và các ràng buộc được hệ graph hỗ trợ. Nếu cho phép một người đăng ký cùng Course nhiều lần, không nên dùng đúng mẫu `MERGE` này để lưu các lượt lịch sử riêng biệt.

### 10.2. Truy vấn những Course một Student tham gia

~~~cypher
MATCH (s:Student {studentId: 'student-101'})
      -[e:ENROLLED_IN]->(c:Course)
WHERE e.status = 'ACTIVE'
RETURN c.courseId AS courseId,
       c.title AS title,
       e.enrolledAt AS enrolledAt
ORDER BY enrolledAt DESC, courseId;
~~~

### 10.3. Truy vấn những Student của một Course

~~~cypher
MATCH (s:Student)
      -[e:ENROLLED_IN]->
      (c:Course {courseId: 'course-nosql'})
WHERE e.status = 'ACTIVE'
RETURN s.studentId AS studentId,
       s.name AS name
ORDER BY studentId;
~~~

Không cần một “bảng trung gian” theo hình thức collection riêng, vì **relationship** đã là một thành phần của property graph. Tuy nhiên, nếu Enrollment cần định danh riêng, lưu lịch sử nhiều lần đăng ký hoặc liên kết tới các thực thể khác như Payment/Certificate, **mô hình Enrollment như node** có thể phù hợp hơn:

~~~text
(Student)-[:HAS_ENROLLMENT]->(Enrollment)
(Enrollment)-[:FOR_COURSE]->(Course)
~~~

Số bước truy vấn nhiều hơn, đổi lại Enrollment có vòng đời và các quan hệ riêng.

### 10.4. Đồ thị không xóa được mọi giới hạn quy mô

Một Course có hàng triệu cạnh vẫn là node bậc lớn. Duyệt toàn bộ thành viên, tìm nhiều bước, sắp xếp và phân trang có thể tốn tài nguyên. Graph database hữu ích khi cần các truy vấn liên kết, nhưng **không mặc nhiên nhanh hơn mọi mô hình document hoặc wide-column**. Cần xác định truy vấn, bậc node và độ sâu traversal thực tế.

---

## 11. Biểu diễn N:M bằng key-value

Một kho key-value đơn giản thường không có join trực tiếp. Quan hệ N:M có thể biểu diễn bằng những khóa truy xuất đã biết:

~~~text
student:student-101:courses
  -> [course-nosql, course-java]

course:course-nosql:students
  -> [student-101, student-202]
~~~

Đây là **hai adjacency lists**. Nếu quan hệ lớn, danh sách có thể không vừa một value hoặc gây chi phí cập nhật lớn. Có thể lưu mỗi liên kết bằng một key riêng:

~~~text
enrollment:student-101:course-nosql -> {
  status: "ACTIVE",
  enrolledAt: "2026-11-14T08:15:27Z"
}
~~~

Nhưng nếu chỉ biết `courseId`, muốn tìm mọi Student thì kho key-value thuần có thể không hỗ trợ quét tiền tố/các khóa theo mẫu hiệu quả. Khi đó thường cần secondary index, thêm khóa ngược hoặc một hệ lưu trữ khác.

Ví dụ hai hướng:

~~~text
studentCourses:student-101:course-nosql -> enrollmentId
courseStudents:course-nosql:student-101 -> enrollmentId
~~~

Đọc mỗi hướng đơn giản nếu DBMS hỗ trợ tìm theo prefix/collection phù hợp; cập nhật/xóa phải đồng bộ hai khóa và dữ liệu Enrollment. Các bảo đảm atomicity phụ thuộc sản phẩm key-value và cách triển khai.

Không nên xem cú pháp key trên là API chung cho mọi kho key-value; đây là **quy ước mô hình logic**.

## 12. Quan hệ và lặp dữ liệu: denormalization có chủ đích

Một quan hệ có thể biểu diễn bằng ID, nhưng để tăng tốc đọc, nhiều hệ NoSQL **lặp một phần thuộc tính** từ thực thể đích.

Ví dụ Enrollment chứa thêm:

~~~json
{
  "_id": "enroll-student101-nosql",
  "studentId": "student-101",
  "courseId": "course-nosql",
  "courseTitleSnapshot": "Nhập môn NoSQL",
  "status": "ACTIVE",
  "enrolledAt": "2026-11-14T08:15:27Z"
}
~~~

Cần phân biệt hai ngữ nghĩa:

1. **Snapshot:** tiêu đề được chốt tại thời điểm đăng ký. Nếu Course đổi tên, Enrollment giữ tiêu đề cũ để bảo toàn lịch sử.
2. **Current projection:** tiêu đề được nhân bản để hiển thị nhanh **và được kỳ vọng luôn gần với tên hiện tại**. Khi Course đổi tên, hệ phải cập nhật read model tương ứng.

Hai trường hợp cùng có dữ liệu lặp, nhưng chi phí đồng bộ khác nhau. Không được dùng một tên mơ hồ rồi cập nhật snapshot theo nguồn sống.

### 12.1. Nguồn sự thật (source of truth)

Một cấu trúc rõ ràng có thể quy định:

~~~text
Course document:
  nguồn sự thật về tiêu đề hiện tại

Enrollment document:
  nguồn sự thật về trạng thái đăng ký

Enrollment.courseTitleSnapshot:
  bản lịch sử, không tự đồng bộ

Enrollment.courseTitleCurrent:
  nếu có, là bản chiếu có thể trễ
~~~

Không phải hệ nào cũng cần cả hai loại trường. Đặt tên nhất quán giúp đội ngũ tránh cập nhật nhầm dữ liệu lịch sử.

### 12.2. Thứ tự cập nhật, retry và chống trùng

Khi một Student đăng ký Course, luồng nghiệp vụ có thể:

~~~text
Client gửi yêu cầu có idempotency key
   ↓
Kiểm tra Student, Course và quyền đăng ký
   ↓
Tạo/cập nhật Enrollment nguồn
   ↓
Phát sự kiện EnrollmentCreated hoặc cập nhật read model
   ↓
Danh sách theo Student/Course có dữ liệu mới
~~~

Đây là luồng logic, chưa phải transaction tự động giữa mọi bước. Cần quyết định:

- Một yêu cầu retry có dùng lại cùng idempotency key và Enrollment ID không?
- Nếu Enrollment đã tồn tại, sẽ trả về kết quả cũ hay tạo lượt học mới?
- Nếu nguồn ghi thành công nhưng cập nhật bản chiếu thất bại, worker có retry được không?
- Khi event đến sai thứ tự, version nào được áp dụng?
- Khi xóa Enrollment, làm sao loại dữ liệu ở mọi index và read model?

**Thêm bản sao để tăng tốc đọc làm tăng trách nhiệm duy trì đúng trạng thái quan hệ**.

## 13. Giao dịch, tính duy nhất và tính toàn vẹn tham chiếu

### 13.1. Atomicity của một document khác atomicity của quan hệ

Trong MongoDB, một thao tác cập nhật trên **một document** có tính nguyên tử theo hợp đồng DBMS. Nhưng tạo một `Student` và một `Enrollment` trong hai collection riêng **không tự nguyên tử** chỉ vì chúng có ID tham chiếu.

Khi nghiệp vụ đòi một nhóm ghi cùng thành công hoặc cùng thất bại, phải xét transaction nhiều document, conditional updates hoặc quy trình có cơ chế khôi phục.

Với những hệ phân tán khác, phạm vi transaction và consistency có thể chỉ ở một item, một partition, hoặc rộng hơn tùy DBMS. Không nên lấy bảo đảm của sản phẩm này áp vào sản phẩm khác.

### 13.2. Tính duy nhất của quan hệ

Các quy tắc cần được khai báo:

- Một User có tối đa một Preferences.
- Một Student có tối đa một Enrollment hiện hành cho cùng Course.
- Một Lesson thuộc đúng một Course trong cùng phiên bản chương trình.
- Một quan hệ Follow giữa hai User có hướng và không được trùng theo đúng quy tắc.

Những quy tắc này có thể cần:

- Unique index/constraint.
- Khóa được xây xác định từ hai ID, ví dụ `studentId#courseId`.
- Ghi có điều kiện (*conditional write*, CAS).
- Transaction hoặc lock khi cập nhật nhiều bản ghi.
- Cơ chế idempotency khi retry.

**Kiểm tra “chưa tồn tại” bằng đọc rồi mới ghi** có thể bị race khi hai yêu cầu cùng thực hiện. Nếu unique constraint hoặc conditional write phù hợp có sẵn, hãy tận dụng chúng thay vì chỉ dựa vào kiểm tra ở application.

### 13.3. Tính toàn vẹn tham chiếu

Một Enrollment có `courseId = "course-nosql"` vẫn có thể tồn tại sau khi Course bị xóa nếu DBMS không tự thực thi foreign key/cascade.

Các chính sách có thể chọn:

- **Restrict:** không cho xóa Course nếu còn Enrollment cần giữ.
- **Cascade:** xóa các Enrollment liên quan khi Course bị xóa, trong phạm vi transaction/quy trình tương ứng.
- **Soft delete:** đánh dấu Course không hoạt động, giữ Enrollment để kiểm toán.
- **Archive/tombstone:** giữ định danh Course và metadata tối thiểu để không làm lịch sử trở thành mồ côi không giải thích được.
- **Asynchronous cleanup:** xử lý dọn liên kết theo sự kiện và có monitoring.

Không có chính sách xóa “đúng cho mọi dữ liệu”. Với lịch sử học tập cần lưu thành tích nhiều năm, xóa cứng Course rồi xóa tất cả Enrollment có thể làm mất dữ liệu nghiệp vụ quan trọng.

### 13.4. Xóa quan hệ khác xóa thực thể

“Hủy theo dõi” thường chỉ xóa cạnh `FOLLOWS`, không xóa User.

“Hủy đăng ký Course” có thể đổi `Enrollment.status = CANCELLED` thay vì xóa bản ghi để giữ lịch sử thanh toán.

“Xóa tài khoản” có thể kích hoạt chính sách riêng cho dữ liệu cá nhân trong Enrollment, Progress, Payment và audit.

Đừng dùng cascade delete rộng chỉ vì quan hệ trong sơ đồ là 1:N.

## 14. Truy vấn ngược là lý do phổ biến khiến thiết kế phải thay đổi

Với quan hệ 1:N, chọn lưu `courseId` trong Lesson thường làm truy vấn **Lesson theo Course** dễ dàng. Nhưng nếu cần “Course của Lesson”, ứng dụng chỉ cần đọc Lesson theo `lessonId` để lấy `courseId` nếu có index phù hợp.

Với N:M, hai phía đều “nhiều”, nên cần thiết kế **hai hướng truy vấn** rõ ràng:

~~~text
studentId -> những courseId đã đăng ký
courseId  -> những studentId đã đăng ký
~~~

Nếu hệ chủ yếu đọc theo Student, chỉ mục theo `studentId` có thể là đường chính. Nếu màn hình giảng viên thường đọc danh sách Student theo Course, cần chỉ mục/bảng theo `courseId`. Còn nếu cần lọc theo `status` và sắp theo `enrolledAt`, chỉ mục phải bao gồm những trường phù hợp.

### 14.1. Kết quả lớn cần phân trang

Một Course có một triệu học viên không thể trả toàn bộ Enrollment trong một response. Hãy định nghĩa:

~~~text
GET /courses/course-nosql/students?status=ACTIVE&limit=50
Sort: enrolledAt DESC, enrollmentId DESC
Cursor: (lastEnrolledAt, lastEnrollmentId)
~~~

Dùng tie-breaker duy nhất để có thứ tự ổn định. Một cột thời gian có thể có nhiều bản ghi bằng nhau; sort chỉ theo timestamp có thể làm phân trang bị lặp hoặc bỏ sót.

### 14.2. Thứ tự không phải một thuộc tính tự nhiên của quan hệ

Mạng Follow có thể không cần sắp theo thời gian. Danh sách bài học trong Course thường cần `position ASC`. Enrollment thường cần `enrolledAt DESC`. Chọn khóa sắp xếp theo **ngữ nghĩa API**, không tự động lấy ID hoặc thứ tự vật lý của DBMS.

**`LIMIT 50` chỉ giới hạn số kết quả, không bảo đảm DBMS chỉ đọc 50 bản ghi** nếu thiếu index hoặc phải quét/merge nhiều partition.

## 15. Trường hợp không nên nhúng hoặc không nên dùng mảng ID

| Mô hình định thử | Rủi ro | Hướng cân nhắc |
|---|---|---|
| User nhúng toàn bộ đơn hàng | Số đơn tăng không giới hạn, quyền và retention riêng | Đơn hàng riêng theo customerId; index lịch sử |
| Post nhúng hàng triệu Comment | Document quá lớn, ghi vào một điểm, khó phân trang | Comment riêng; preview giới hạn |
| Course nhúng toàn bộ Enrollment | Course phổ biến thành document nóng/rất lớn | Enrollment trung gian; phân vùng theo truy vấn |
| Student và Course cùng lưu mảng ID đầy đủ | Hai nguồn dữ liệu có thể lệch, khó retry | Association collection làm nguồn chính |
| Một Course có một million Student làm một partition Cassandra | Partition quá lớn/hot | Bucketing hoặc read model chia tải |
| Graph node có hàng triệu cạnh rồi duyệt không giới hạn | Traversal và aggregation rất đắt | Lọc sớm, giới hạn traversal, projection/index thích hợp |
| Chỉ tham chiếu Product hiện tại trong Order | Tên/giá lịch sử bị thay đổi theo catalog | Nhúng snapshot lúc mua |
| Nhúng dữ liệu có TTL 30 ngày trong cha lưu 10 năm | Khó xóa riêng và thực thi retention | Tách dữ liệu hoặc cơ chế xóa trường phù hợp |

Bảng minh họa tính **đánh đổi**. Có những hệ đọc tập nhỏ có thể dùng mảng ID rất tốt; vấn đề xuất hiện khi cardinality và mẫu truy cập không còn phù hợp.

## 16. So sánh chi phí đọc, ghi, lưu trữ và độ phức tạp

| Lựa chọn | Chi phí đọc | Chi phí ghi | Lưu trữ | Độ phức tạp |
|---|---|---|---|---|
| Nhúng 1:1 | Ít lần đọc cho cả hai | Một document khi cập nhật chung | Ít metadata liên kết | Dễ nếu cùng vòng đời; khó khi quyền/TTL khác |
| Tham chiếu 1:1 | Có thể phải đọc hai document | Cập nhật độc lập hơn | Hai document và index | Dọn orphan, bảo đảm tạo/xóa |
| Nhúng 1:N bounded | Đọc cha kèm con nhanh | Cùng cha có thể thành điểm ghi tập trung | Document lớn hơn | Giới hạn mảng, cập nhật đồng thời |
| Con riêng có parent ID | Đọc có thể cần thêm request | Con ghi độc lập | Index và metadata riêng | Cascade, consistency, projection |
| N:M bằng hai mảng ID | Đọc nhanh theo từng phía | Hai phía phải cập nhật | Hai bản sao liên kết | Xử lý lệch dữ liệu, mảng lớn |
| N:M bằng association collection | Lọc, phân trang tốt nếu có index | Một Enrollment nguồn; index theo hai chiều | Một document/cạnh và index | Truy vấn ghép, ràng buộc unique |
| N:M bằng read models | Rất nhanh cho query đã thiết kế | Write amplification | Lặp dữ liệu theo hướng đọc | Đồng bộ, retry, reconciliation |
| N:M bằng graph edges | Traversal tự nhiên | Quản lý cạnh và node | Thuộc tính node/cạnh, index | Bậc node lớn, traversal, quy tắc cạnh |

Không có con số hiệu năng cố định từ bảng trên. Khi cân nhắc production, cần đo workload đại diện: phân bố cardinality, tốc độ tạo/xóa liên kết, số request/read, p95/p99, index size và hậu quả của eventual consistency.

---

## 17. Quy trình thiết kế một quan hệ NoSQL từ yêu cầu

### Bước 1 — Viết ràng buộc cardinality

Ví dụ:

~~~text
Một Student có 0..N Enrollment.
Một Course có 0..N Enrollment.
Mỗi Enrollment thuộc đúng một Student và một Course.
Một Student chỉ được có một Enrollment ACTIVE
cho mỗi Course (quy tắc nghiệp vụ).
~~~

Nếu cho phép nhiều attempt, quy định identity của từng attempt và quy tắc riêng cho `ACTIVE`.

### Bước 2 — Liệt kê query và thao tác ghi

| ID | Thao tác | Điều kiện và thứ tự | Tần suất dự kiến |
|---|---|---|---|
| Q1 | Những Course của Student | studentId, status, enrolledAt DESC | Rất thường xuyên |
| Q2 | Những Student của Course | courseId, status, enrolledAt DESC | Thường xuyên |
| Q3 | Lấy một Enrollment | studentId + courseId hoặc enrollmentId | Thường xuyên |
| W1 | Đăng ký Course | idempotency, unique relationship | Thường xuyên |
| W2 | Cập nhật tiến độ | enrollmentId, version | Rất thường xuyên |
| W3 | Hủy/hoàn thành | enrollmentId, trạng thái hiện tại | Trung bình |
| W4 | Xóa/ẩn Course | Chính sách giữ lịch sử và quyền | Hiếm |

### Bước 3 — Chọn bản ghi nguồn

Nếu Enrollment có metadata riêng, chọn **document Enrollment** làm nguồn có thể đơn giản hơn cố bảo đảm hai mảng ID trong Student và Course luôn khớp.

Dữ liệu Student/Course gốc vẫn giữ riêng. Một số thuộc tính có thể snapshot hoặc đọc qua ID.

### Bước 4 — Thiết kế đường đọc/index

Cho Q1 cần index theo `(studentId, status, enrolledAt DESC, enrollmentId DESC)`.

Cho Q2 cần index theo `(courseId, status, enrolledAt DESC, enrollmentId DESC)`.

Cho Q3 cần định danh/unique constraint phù hợp và trùng với quy tắc khi học lại. Tránh dùng một ID được tạo mới ở mỗi lần retry nếu muốn cùng yêu cầu chỉ tạo một Enrollment.

### Bước 5 — Thiết kế tính nhất quán

Làm rõ:

- Nguồn nào xác định Enrollment có hiệu lực?
- Nếu cập nhật index/bảng đọc thất bại thì sẽ retry thế nào?
- Có cho phép read model chậm cập nhật không, và tối đa theo hợp đồng là bao lâu?
- Nếu Course biến mất, Enrollment được giữ, ẩn hay xóa?
- Khi nhiều request đồng thời, ràng buộc “tối đa một ACTIVE” được thực thi tại đâu?

### Bước 6 — Kiểm tra giới hạn và đo

- Mỗi Course có bao nhiêu học viên ở p50/p95/p99?
- Course lớn nhất có tạo hotspot không?
- Truy vấn có chỉ đọc một partition/index range hay fan-out nhiều nơi?
- Độ trễ khi tải cao và khi dữ liệu tăng gấp 10 lần?
- Mỗi thao tác ghi phải cập nhật bao nhiêu index/read model?
- Phân trang ở timestamp bằng nhau có ổn định không?

### Bước 7 — Ghi lại quyết định

Ghi một ADR hoặc bảng ngắn nêu:

- Phương án được chọn và phương án bị loại.
- Mẫu truy vấn trọng tâm.
- Bảo đảm tính đúng đắn và nhất quán.
- Đánh đổi đọc/ghi/lưu trữ/phức tạp.
- Điều kiện xem xét lại như partition nóng, mảng vượt ngưỡng hoặc read model lag.

## 18. Tình huống thực hành: mạng xã hội học tập

Một mạng học tập có ba loại quan hệ:

1. Mỗi User có tối đa một bộ Preferences.
2. Một Post có thể có hàng triệu Comment.
3. Một User có thể theo dõi nhiều User, và mỗi User có thể được rất nhiều người khác theo dõi.

Yêu cầu API:

~~~text
GET /users/{id}/preferences
GET /posts/{id}/comments?limit=30
GET /users/{id}/following?limit=50
GET /users/{id}/followers?limit=50
POST /users/{id}/follow/{targetId}
DELETE /users/{id}/follow/{targetId}
~~~

### 18.1. Hãy xác định kiểu quan hệ

| Quan hệ | Cardinality |
|---|---|
| User – Preferences | 1:0..1 hoặc 1:1 tùy nghiệp vụ |
| Post – Comment | 1:N |
| User – User qua FOLLOWS | N:M có hướng |

Với Follow, `A FOLLOWS B` không đồng nghĩa `B FOLLOWS A`. Đây là điểm khác biệt với quan hệ bạn bè hai chiều.

### 18.2. Phương án gợi ý

**Preferences:** nhúng nếu nhỏ và luôn thuộc hồ sơ, hoặc tách nếu quyền/nhịp ghi khác.

**Comment:** collection riêng:

~~~json
{
  "_id": "comment-1001",
  "postId": "post-55",
  "authorId": "user-101",
  "content": "Nội dung hữu ích",
  "createdAt": "2026-11-14T08:15:27Z"
}
~~~

**Follow:** collection quan hệ:

~~~json
{
  "_id": "user-101#user-202",
  "followerId": "user-101",
  "followeeId": "user-202",
  "followedAt": "2026-11-14T08:20:00Z",
  "status": "ACTIVE"
}
~~~

Một thiết kế có thể dùng unique index:

~~~javascript
db.follows.createIndex(
  { followerId: 1, followeeId: 1 },
  { unique: true }
);
~~~

Index đọc **following**:

~~~javascript
db.follows.createIndex({
  followerId: 1,
  status: 1,
  followedAt: -1,
  _id: -1
});
~~~

Index đọc **followers**:

~~~javascript
db.follows.createIndex({
  followeeId: 1,
  status: 1,
  followedAt: -1,
  _id: -1
});
~~~

Quy tắc nghiệp vụ:

- Không cho người dùng theo dõi chính mình nếu sản phẩm cấm.
- Không tạo hai cạnh ACTIVE cùng hướng cho một cặp.
- Kiểm tra quyền riêng tư, trạng thái chặn và tài khoản bị vô hiệu hóa.
- Hủy theo dõi có thể xóa document Follow hoặc đổi status theo yêu cầu lịch sử.
- Một lượt retry của cùng hành động Follow không tạo cạnh trùng.

### 18.3. Bài tập so sánh

Hãy trả lời:

1. Vì sao không nên nhúng tất cả Comment vào Post?
2. Vì sao chỉ lưu `followingIds[]` trong User có thể khó đáp ứng API `followers` khi lượng người dùng lớn?
3. Hai index trên Follow phục vụ **hai chiều truy vấn** khác nhau như thế nào?
4. Cần làm gì nếu Follow phải lưu nhiều lần theo dõi–hủy–theo dõi để phục vụ thống kê lịch sử?
5. Nếu một người nổi tiếng có 10 triệu follower, truy vấn `followers` và xử lý follower count cần thiết kế thêm gì?
6. Nếu graph database được sử dụng, cạnh `FOLLOWS` biểu diễn hướng nào và loại truy vấn hai bước có thể viết ra sao?

### 18.4. Hướng phân tích

- Post–Comment là 1:N tăng không giới hạn: tách Comment, phân trang và index theo `postId`.
- User–User Follow là N:M có hướng: association collection hoặc graph edge phù hợp hơn hai mảng ID đầy đủ không giới hạn.
- Cần hai đường đọc khi hỗ trợ both following/followers với SLO thấp.
- Nếu giữ lịch sử nhiều lần Follow, tách **current relationship** khỏi **follow events** hoặc dùng thực thể sự kiện có ID riêng; đừng áp unique index sai lên toàn bộ lịch sử.
- Follower count có thể cần bộ đếm tổng hợp/read model và chính sách đối soát, không nên cứ đọc toàn bộ cạnh để đếm ở mỗi request.
- Người nổi tiếng là trường hợp **high-degree node/hot key**, cần đo tải, phân vùng và hành vi khi có nhiều cập nhật đồng thời.

---

## 19. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu chính xác |
|---|---|
| “NoSQL không hỗ trợ quan hệ.” | Quan hệ vẫn được biểu diễn bằng embedding, reference, association, key hoặc graph edge. |
| “Quan hệ 1:1 luôn phải nhúng.” | Có thể cần tách do quyền, vòng đời, kích thước và nhịp cập nhật khác nhau. |
| “Quan hệ 1:N phải là một mảng con.” | Với tập con lớn hoặc vô hạn, lưu con riêng có parent ID thường phù hợp hơn. |
| “Quan hệ N:M chỉ cần hai mảng ID.” | Hai mảng có thể lệch; quan hệ có metadata và quy mô lớn nên cân nhắc association collection. |
| “Có cùng ID là hệ tự tạo foreign key.” | Nhiều NoSQL không tự kiểm tra sự tồn tại hay cascade giữa document. |
| “Unique index bảo đảm hai phía quan hệ đều tồn tại.” | Unique chỉ ngăn trùng khóa trong phạm vi ràng buộc, không thay thế toàn vẹn tham chiếu. |
| “`$addToSet` là transaction của Student và Course.” | Nó chỉ cập nhật một mảng trong một document, không cập nhật đồng thời Course. |
| “Dữ liệu lặp luôn là sai.” | Snapshot lịch sử và read model có thể là lựa chọn có chủ đích, nhưng phải hiểu chi phí đồng bộ. |
| “Graph edge không bao giờ bị trùng.” | Ràng buộc nghiệp vụ và ghi đồng thời vẫn cần được xử lý đúng. |
| “Có nhiều row cùng partition thì Cassandra tự chia đều ra mọi node.” | Partition key mới quyết định nhóm dữ liệu; clustering key chỉ sắp trong partition. |
| “LIMIT giúp query liệt kê mọi quan hệ lớn trở nên rẻ.” | Nếu thiếu index hoặc cần scan/fan-out nhiều phần, DBMS có thể phải xử lý rất nhiều dữ liệu trước khi trả ít hàng. |
| “Xóa cha luôn phải xóa toàn bộ con.” | Cần chính sách restrict/cascade/soft-delete/archive theo yêu cầu lịch sử, retention và pháp lý. |

## 20. Kết luận

Biểu diễn quan hệ trong NoSQL cần tách hai quyết định:

1. **Quan hệ nghiệp vụ là gì?** Một-một, một-nhiều hay nhiều-nhiều; có hướng không; cardinality tối thiểu/tối đa; có metadata, trạng thái và vòng đời riêng không?
2. **Dữ liệu nên lưu như thế nào để phục vụ truy vấn?** Nhúng, tham chiếu, collection liên kết, bảng đọc theo từng chiều hay cạnh graph; index, phân trang, transaction và đồng bộ ra sao?

Các nguyên tắc thực hành:

- Với **1:1**, nhúng khi đối tượng nhỏ và cùng vòng đời; tách khi cần quyền, cập nhật hoặc lưu giữ độc lập; dùng unique constraint khi cần giới hạn “tối đa một”.
- Với **1:N**, nhúng con nhỏ có giới hạn, nhưng với danh sách tăng không giới hạn hãy cân nhắc document con có parent ID, index và phân trang.
- Với **N:M**, ưu tiên mô hình quan hệ trung gian hoặc graph edge khi liên kết lớn, được truy vấn hai chiều hoặc có thuộc tính riêng; tránh tạo hai nguồn sự thật không đồng bộ.
- **Cardinality không quyết định toàn bộ schema**: mẫu lọc, thứ tự, giới hạn kết quả, bậc node/partition và độ tươi dữ liệu mới quyết định chi phí truy vấn.
- Mỗi bản sao/denormalization phải có **ngữ nghĩa rõ ràng**: snapshot bất biến hay projection hiện tại; source of truth là gì; xử lý retry, xóa và backfill ra sao.

Một thiết kế NoSQL tốt không cố loại bỏ quan hệ. Nó làm cho **quan hệ được biểu diễn rõ, truy xuất hiệu quả, đủ ràng buộc tính đúng đắn và có thể vận hành khi dữ liệu tăng trưởng**.
