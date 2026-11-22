# Tham chiếu dữ liệu chia sẻ và xử lý quan hệ nhiều-nhiều

Trong cơ sở dữ liệu NoSQL dạng **tài liệu (document database)**, một document có thể chứa các object và array lồng nhau. Điều này làm cho **nhúng dữ liệu (embedding)** rất thuận tiện khi một nhóm thông tin được đọc và cập nhật như một đơn vị. Tuy nhiên, nhiều đối tượng nghiệp vụ được **chia sẻ** giữa các document, hoặc có quan hệ **nhiều-nhiều (many-to-many)**: một học viên tham gia nhiều khóa học và một khóa học có nhiều học viên; một sản phẩm thuộc nhiều danh mục và một danh mục chứa nhiều sản phẩm.

Nhúng toàn bộ đối tượng vào mọi nơi nó xuất hiện có thể khiến cùng một thông tin phải sửa ở hàng nghìn bản sao. Ngược lại, lưu mỗi thứ thành collection riêng rồi ghép dữ liệu mọi lúc cũng có thể khiến đường đọc chậm và phức tạp. Thiết kế tốt cần trả lời rõ: **đâu là dữ liệu có danh tính độc lập, đâu là bản chụp lịch sử, quan hệ có thuộc tính riêng hay không, đọc theo chiều nào và dữ liệu lớn lên đến đâu**.

Bài này sử dụng **MongoDB** làm ví dụ cụ thể, với cú pháp **mongosh**. Nguyên tắc xác định aggregate, tham chiếu, xử lý quan hệ và chi phí truy vấn cũng hữu ích với document database khác, nhưng index, transaction, phép nối và giới hạn vật lý phụ thuộc sản phẩm.

## 1. Ba khái niệm cần phân biệt

**Nhúng (embed)** là đặt dữ liệu con trong cùng một document. Khi đọc document cha, ứng dụng có sẵn dữ liệu con:

~~~javascript
{
  _id: "order-101",
  items: [
    { sku: "pen", titleAtPurchase: "Bút xanh", quantity: 2, unitPrice: 10000 },
    { sku: "book", titleAtPurchase: "Sổ tay", quantity: 1, unitPrice: 35000 }
  ]
}
~~~

**Tham chiếu (reference)** là lưu định danh của một đối tượng khác. Document chứa reference không tự mang toàn bộ nội dung của đối tượng được trỏ đến:

~~~javascript
{
  _id: "lesson-201",
  courseId: "course-nosql",
  title: "Thiết kế dữ liệu"
}
~~~

**Document liên kết (association/edge document)** là một document đại diện cho chính **mối quan hệ** giữa hai đối tượng:

~~~javascript
{
  _id: "enrollment-501",
  studentId: "student-01",
  courseId: "course-nosql",
  enrolledAt: ISODate("2026-11-01T09:00:00Z"),
  status: "ACTIVE"
}
~~~

Trường hợp cuối rất hữu ích khi quan hệ có thuộc tính như ngày bắt đầu, trạng thái, vai trò, điểm số hay lịch sử tương tác. Thay vì chỉ trả lời “học viên thuộc khóa học nào?”, ta còn trả lời “học viên tham gia khi nào, hiện còn theo học không?”.

| Cách biểu diễn | Nguồn dữ liệu có danh tính riêng? | Có cần thêm truy vấn để lấy đầy đủ dữ liệu? | Trường hợp phù hợp |
|---|---|---|---|
| Nhúng object | Thường không cần danh tính độc lập cho object con | Thường không | Dòng hàng chốt trong đơn, địa chỉ giao hàng tại thời điểm đặt |
| Lưu ID tham chiếu | Có | Có nếu cần chi tiết đối tượng được tham chiếu | Người tạo bài viết, danh mục, nhà xuất bản |
| Collection liên kết | Hai đầu quan hệ độc lập; quan hệ cũng có thể có danh tính | Có khi cần hiển thị cả hai đầu | Học viên–khóa học, thành viên–nhóm, người dùng–vai trò |

Một tham chiếu trong MongoDB thường chỉ là trường ID do ứng dụng đặt quy ước. MongoDB **không tự tạo khóa ngoại hay bảo đảm đối tượng được tham chiếu luôn tồn tại**, nên cần thiết kế cả đường ghi, cập nhật và xóa.

## 2. Từ yêu cầu nghiệp vụ đến quyết định mô hình

Giả sử có nền tảng học trực tuyến với các yêu cầu:

1. Mỗi **học viên** có thể đăng ký nhiều **khóa học**.
2. Mỗi **khóa học** có thể có rất nhiều học viên; số lượng tiếp tục tăng theo thời gian.
3. Trang **Khóa học của tôi** hiển thị các khóa mà học viên đang theo học, sắp xếp theo thời điểm đăng ký.
4. Trang quản trị khóa học liệt kê học viên đang tham gia, có phân trang.
5. Một cặp **học viên–khóa học** chỉ có một quan hệ đăng ký hiện hành; cần biết ngày đăng ký và trạng thái.
6. Khi đổi tên khóa học, danh sách của học viên hiển thị tên mới; tiến độ hoặc điểm số của học viên vẫn thuộc riêng từng lần đăng ký theo quy tắc nghiệp vụ.

Điều kiện quan trọng nhất: **học viên và khóa học là hai thực thể độc lập**. Cả hai đều cần được đọc, sửa và quản lý vòng đời riêng. Tên khóa học là thông tin dùng chung giữa nhiều học viên.

~~~mermaid
flowchart LR
    S1["Học viên S1"] -->|"đăng ký"| C1["Khóa học C1"]
    S1 -->|"đăng ký"| C2["Khóa học C2"]
    S2["Học viên S2"] -->|"đăng ký"| C1
    S3["Học viên S3"] -->|"đăng ký"| C1
~~~

Nếu lưu toàn bộ khóa học bên trong từng document học viên, mỗi lần đổi tên khóa C1 phải sửa mọi học viên có C1. Nếu lưu toàn bộ học viên bên trong mỗi document khóa học, document C1 có thể tăng liên tục và gây khó phân trang, cập nhật. Đây là tín hiệu nên cân nhắc **reference** và **collection liên kết**.

## 3. Xác định access patterns trước khi chọn cách nhúng

Một mô hình nhiều-nhiều phải phục vụ **hai chiều truy vấn**, đồng thời xét các đường ghi liên quan:

| Thao tác | Đầu vào | Kết quả cần có | Đặc điểm |
|---|---|---|---|
| Xem khóa học của tôi | tenantId, studentId, cursor | Khóa đã đăng ký, sắp xếp theo enrolledAt | Đọc thường xuyên, cần tên khóa mới |
| Xem học viên của khóa | tenantId, courseId, cursor | Danh sách học viên và trạng thái | Fan-out có thể rất lớn |
| Đăng ký khóa | tenantId, studentId, courseId | Tạo một quan hệ nếu hợp lệ và chưa tồn tại | Chống đăng ký trùng khi concurrent |
| Ngừng học / đăng ký lại | Cặp studentId–courseId | Thay đổi status, lưu lịch sử theo hợp đồng | Cần rõ quy tắc trạng thái |
| Đổi tên khóa học | courseId, title | Tên mới được hiển thị mọi nơi đọc dữ liệu sống | Tránh sửa bản sao ở mỗi học viên |
| Xóa học viên / khóa học | ID cần xóa | Xử lý quan hệ còn tồn tại và dữ liệu liên quan | Cần chính sách xóa và kiểm soát race |
| Thống kê số học viên | tenantId, courseId | Số đăng ký hợp lệ | Có thể đếm trực tiếp hoặc dùng read model |

Trong ví dụ, **tenantId** biểu diễn phạm vi tổ chức. Mọi truy vấn từ người dùng cần được ràng buộc với tenant và quyền của tài khoản hiện tại. Các ID được minh họa dưới dạng chuỗi để dễ theo dõi; ứng dụng có thể dùng ObjectId, UUID hoặc ID khác nếu quy ước nhất quán.

## 4. Ba phương án lưu quan hệ nhiều-nhiều

### Phương án A — Nhúng mảng khóa học trong học viên

~~~javascript
{
  _id: "student-01",
  tenantId: "school-a",
  fullName: "An",
  courseIds: ["course-java", "course-nosql"]
}
~~~

Ưu điểm: biết danh sách ID khóa học của một học viên chỉ bằng một lần đọc document. Nếu mỗi học viên chỉ có **rất ít** khóa và hầu như chỉ đọc theo chiều học viên, đây có thể là phương án đơn giản.

Hạn chế: vẫn phải lấy document khóa học để biết tên hiện tại; muốn tìm tất cả học viên của một khóa cần index/đường truy vấn theo mảng, và mảng tiếp tục tăng theo thời gian. Nếu mối quan hệ có **enrolledAt**, **status**, **score**, dữ liệu nhúng sẽ phức tạp hơn. Việc cập nhật concurrent và quy tắc không trùng cần được thiết kế riêng. Dùng mảng chứa ID không tự đảm bảo thực thể tham chiếu còn tồn tại.

### Phương án B — Nhúng mảng học viên trong khóa học

~~~javascript
{
  _id: "course-nosql",
  tenantId: "school-a",
  title: "NoSQL căn bản",
  studentIds: ["student-01", "student-02", "student-03"]
}
~~~

Phương án này giúp xem ID học viên của khóa qua một document. Nhưng một khóa rất nổi tiếng có thể có hàng trăm nghìn người đăng ký. Mảng không giới hạn gây tăng kích thước document, làm cập nhật tập trung tại một khóa nóng, khó chia trang và có thể chạm giới hạn kích thước document của MongoDB.

Lưu **mảng ở cả hai phía** còn tạo vấn đề nhất quán: ghi thành công vào học viên nhưng thất bại ở khóa học sẽ sinh ra hai góc nhìn trái ngược. Hai mảng cũng làm tăng lượng ghi và công việc xóa/đồng bộ.

### Phương án C — Collection liên kết riêng

~~~text
students               enrollments                courses
---------              --------------------       ------------
student-01   <------   studentId                 course-java
student-02   <------   studentId                 course-nosql
                       courseId   ---------------->
                       enrolledAt
                       status
                       progress
~~~

Mỗi đăng ký là một document, ví dụ:

~~~javascript
{
  _id: "enrollment-001",
  tenantId: "school-a",
  studentId: "student-01",
  courseId: "course-nosql",
  enrolledAt: ISODate("2026-11-12T10:00:00Z"),
  status: "ACTIVE",
  progressPercent: 25
}
~~~

Ưu điểm: quan hệ có thể tăng thành nhiều document; dễ truy vấn theo cả **studentId** và **courseId** bằng index riêng; thuộc tính của quan hệ có nơi lưu rõ ràng; không cần sửa mảng dài ở mỗi thực thể.

Đổi lại, đường đọc tên khóa hoặc thông tin học viên cần phép ghép hoặc truy vấn bổ sung; các ghi liên quan nhiều collection có thể cần transaction hoặc mô hình nhất quán đã được xác định.

| Tiêu chí | Mảng ở học viên | Mảng ở khóa học | Collection enrollments |
|---|---|---|---|
| Đọc ID khóa của một học viên | Thuận tiện | Cần tìm ngược | Lọc theo studentId |
| Đọc ID học viên của một khóa | Cần tìm ngược | Thuận tiện | Lọc theo courseId |
| Quan hệ tăng rất lớn | Mảng có thể tăng quá lớn | Mảng có thể tăng quá lớn | Mỗi quan hệ là document riêng |
| Thuộc tính trên quan hệ | Có thể nhúng object con | Có thể nhúng object con | Lưu trực tiếp trong edge document |
| Phân trang theo cả hai chiều | Khó hơn khi mảng lớn | Khó hơn khi mảng lớn | Thiết kế index cho từng chiều |
| Không trùng cặp | Cần logic bổ sung | Cần logic bổ sung | Có thể dùng unique compound index |
| Cập nhật tên khóa đang dùng chung | Vẫn tra course | Khóa chứa tên chính | Truy vấn/join tới course |

Với yêu cầu ví dụ, **collection enrollments là ứng viên chính** vì quan hệ lớn dần, có trạng thái và cần truy vấn hai chiều.

## 5. Mô hình dữ liệu minh họa với MongoDB

Ta sử dụng ba collection:

~~~text
students
  _id, tenantId, fullName, status

courses
  _id, tenantId, title, status

enrollments
  _id, tenantId, studentId, courseId,
  enrolledAt, status, progressPercent
~~~

**students** và **courses** sở hữu dữ liệu độc lập. **enrollments** sở hữu thuộc tính của quan hệ. Trong ví dụ, mỗi cặp học viên–khóa học chỉ có **một document đăng ký hiện hành**; khi ngừng học và đăng ký lại, ứng dụng cập nhật trạng thái theo chính sách. Nếu bài toán cần lưu nhiều **lần đăng ký** của cùng cặp, phải thay đổi định nghĩa danh tính quan hệ và thiết kế unique index, không giữ nguyên ràng buộc một cặp chỉ có một record.

### Dữ liệu thử nghiệm

Các câu lệnh **mongosh** sau dùng dữ liệu giả lập, phù hợp chạy trong một database thử nghiệm:

~~~javascript
db.students.insertMany([
  { _id: "student-01", tenantId: "school-a", fullName: "An", status: "ACTIVE" },
  { _id: "student-02", tenantId: "school-a", fullName: "Bình", status: "ACTIVE" },
  { _id: "student-03", tenantId: "school-a", fullName: "Chi", status: "ACTIVE" }
]);

db.courses.insertMany([
  {
    _id: "course-java", tenantId: "school-a",
    title: "Java căn bản", status: "PUBLISHED"
  },
  {
    _id: "course-nosql", tenantId: "school-a",
    title: "NoSQL căn bản", status: "PUBLISHED"
  },
  {
    _id: "course-web", tenantId: "school-a",
    title: "Web cơ bản", status: "PUBLISHED"
  }
]);

db.enrollments.insertMany([
  {
    _id: "enrollment-001", tenantId: "school-a",
    studentId: "student-01", courseId: "course-nosql",
    enrolledAt: ISODate("2026-11-12T10:00:00Z"),
    status: "ACTIVE", progressPercent: 25
  },
  {
    _id: "enrollment-002", tenantId: "school-a",
    studentId: "student-01", courseId: "course-java",
    enrolledAt: ISODate("2026-11-10T08:00:00Z"),
    status: "ACTIVE", progressPercent: 50
  },
  {
    _id: "enrollment-003", tenantId: "school-a",
    studentId: "student-02", courseId: "course-nosql",
    enrolledAt: ISODate("2026-11-11T12:00:00Z"),
    status: "ACTIVE", progressPercent: 10
  },
  {
    _id: "enrollment-004", tenantId: "school-a",
    studentId: "student-03", courseId: "course-nosql",
    enrolledAt: ISODate("2026-11-09T07:00:00Z"),
    status: "PAUSED", progressPercent: 30
  }
]);
~~~

Trong dữ liệu mẫu:

- An đang học **NoSQL căn bản** và **Java căn bản**.
- Bình đang học **NoSQL căn bản**.
- Chi có quan hệ với khóa NoSQL nhưng trạng thái **PAUSED**, vì vậy không được tính là học viên **ACTIVE** khi nghiệp vụ yêu cầu chỉ liệt kê người đang học.
- **NoSQL căn bản** là tài liệu khóa học được chia sẻ; tên khóa chỉ có nguồn chính tại collection **courses**.

## 6. Index cho hai chiều truy vấn và chống trùng quan hệ

### Ràng buộc duy nhất một cặp học viên–khóa học

~~~javascript
db.enrollments.createIndex(
  { tenantId: 1, studentId: 1, courseId: 1 },
  { unique: true, name: "uniq_tenant_student_course" }
);
~~~

Index duy nhất này bảo đảm **không thể tồn tại hai document có cùng bộ (tenantId, studentId, courseId)** trong phạm vi ràng buộc của MongoDB, với điều kiện dữ liệu hiện có hợp lệ và môi trường index đáp ứng cấu hình triển khai. Nếu dữ liệu cũ đã có cặp trùng, việc tạo index unique sẽ thất bại; cần xử lý dữ liệu trước.

Unique index giúp chống một dạng race:

~~~text
Request A: kiểm tra chưa có đăng ký
Request B: kiểm tra chưa có đăng ký
Request A: insert enrollment
Request B: insert enrollment
~~~

Nếu không có ràng buộc ở database, cả hai request có thể cùng ghi thành công. Với unique index, chỉ một thao tác được phép tạo cặp đó; thao tác còn lại nhận lỗi khóa trùng hoặc cần được xử lý theo logic nghiệp vụ. Không nên dựa duy nhất vào **find trước rồi insert** để chống trùng.

### Index cho trang “Khóa học của tôi”

~~~javascript
db.enrollments.createIndex(
  {
    tenantId: 1,
    studentId: 1,
    status: 1,
    enrolledAt: -1,
    _id: -1
  },
  { name: "by_student_status_enrolled" }
);
~~~

Query chính lọc **tenantId**, **studentId**, **status** bằng điều kiện bằng nhau, rồi sort **enrolledAt DESC, _id DESC**. Index hỗ trợ đường truy cập này và pagination theo cặp khóa sắp xếp.

### Index cho trang học viên của khóa

~~~javascript
db.enrollments.createIndex(
  {
    tenantId: 1,
    courseId: 1,
    status: 1,
    enrolledAt: -1,
    _id: -1
  },
  { name: "by_course_status_enrolled" }
);
~~~

Đây là đường đọc **ngược chiều**: từ một khóa học đến các quan hệ đăng ký. Index đầu tiên bắt đầu bằng **studentId**, nên không mặc nhiên hiệu quả cho truy vấn chỉ biết **courseId**.

Không nên tạo index cho mọi tổ hợp trường một cách máy móc. Mỗi index tốn bộ nhớ/lưu trữ và chi phí cập nhật khi ghi. Cần kiểm tra kế hoạch bằng **explain("executionStats")** và số liệu tải thực tế, đặc biệt khi tập dữ liệu tăng lớn hoặc có khóa học nhận lượng đăng ký vượt trội.

## 7. Đọc quan hệ từ học viên đến khóa học

Trước hết, nếu giao diện chỉ cần ID và tiến độ đăng ký:

~~~javascript
db.enrollments
  .find(
    {
      tenantId: "school-a",
      studentId: "student-01",
      status: "ACTIVE"
    },
    {
      _id: 1,
      courseId: 1,
      enrolledAt: 1,
      progressPercent: 1
    }
  )
  .sort({ enrolledAt: -1, _id: -1 })
  .limit(10);
~~~

Kết quả có thứ tự:

| Vị trí | courseId | enrolledAt (UTC) | progressPercent |
|---:|---|---|---:|
| 1 | course-nosql | 2026-11-12 10:00 | 25 |
| 2 | course-java | 2026-11-10 08:00 | 50 |

Nhưng giao diện còn muốn hiển thị **title hiện tại của khóa học**. Có hai cách phổ biến:

**Cách 1 — Query hai pha.** Lấy các enrollment trước, thu thập **courseId** của trang hiện tại, lấy các khóa tương ứng bằng điều kiện **_id: { $in: [...] }**, sau đó ghép theo ID trong ứng dụng và khôi phục thứ tự từ danh sách enrollment. Cách này thường có thể kiểm soát lượng dữ liệu vì chỉ join các bản ghi của trang.

**Cách 2 — MongoDB aggregation với $lookup.** Ghép trực tiếp thông tin khóa học sau khi lọc, sắp xếp và giới hạn enrollment:

~~~javascript
db.enrollments.aggregate([
  {
    $match: {
      tenantId: "school-a",
      studentId: "student-01",
      status: "ACTIVE"
    }
  },
  { $sort: { enrolledAt: -1, _id: -1 } },
  { $limit: 10 },
  {
    $lookup: {
      from: "courses",
      let: { targetCourseId: "$courseId", targetTenant: "$tenantId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$targetCourseId"] },
                { $eq: ["$tenantId", "$$targetTenant"] }
              ]
            }
          }
        },
        { $project: { _id: 1, title: 1, status: 1 } }
      ],
      as: "course"
    }
  },
  { $unwind: "$course" },
  {
    $project: {
      _id: 1,
      enrolledAt: 1,
      progressPercent: 1,
      courseId: 1,
      courseTitle: "$course.title",
      courseStatus: "$course.status"
    }
  }
]);
~~~

Kết quả kỳ vọng của dữ liệu mẫu:

| courseId | courseTitle | progressPercent |
|---|---|---:|
| course-nosql | NoSQL căn bản | 25 |
| course-java | Java căn bản | 50 |

**Vì sao $limit đứng trước $lookup?** Ta muốn xác định trước 10 quan hệ cần hiển thị; sau đó chỉ join khóa học của trang đó. Nếu join hàng triệu enrollment rồi mới giới hạn, cơ sở dữ liệu có thể phải xử lý lượng công việc không cần thiết.

**Vì sao thêm điều kiện tenant trong $lookup?** ID được lưu trong enrollment phải được xem là tham chiếu theo đúng phạm vi dữ liệu. Kiểm tra cùng tenant là một lớp bảo vệ mô hình khi ứng dụng đa tenant, không thay thế toàn bộ xác thực và phân quyền ở API.

**Vì sao $unwind có ý nghĩa?** Nếu tham chiếu đến khóa học không còn tồn tại, **$lookup** trả về mảng rỗng; **$unwind** như ví dụ sẽ bỏ enrollment đó khỏi kết quả. Đây là một lựa chọn hiển thị có hệ quả. Nếu cần phát hiện **orphan reference**, nên giữ lại enrollment với **preserveNullAndEmptyArrays: true** và đưa ra cảnh báo, thay vì âm thầm giấu lỗi dữ liệu.

Trong ứng dụng thật, nên đo số document được quét, lượng dữ liệu và độ trễ của các phép ghép. **$lookup** không biến mọi quan hệ nhiều-nhiều thành phép nối miễn phí; kích thước tập dữ liệu, thứ tự stage, index và phân bố truy vấn vẫn quyết định chi phí.

## 8. Đọc theo chiều ngược: từ khóa học đến học viên

Trang quản trị cần “danh sách học viên đang tham gia khóa NoSQL”. Trước tiên lấy quan hệ:

~~~javascript
db.enrollments
  .find({
    tenantId: "school-a",
    courseId: "course-nosql",
    status: "ACTIVE"
  })
  .sort({ enrolledAt: -1, _id: -1 })
  .limit(10);
~~~

Theo dữ liệu mẫu, kết quả có **student-01** và **student-02**; **student-03** không xuất hiện vì trạng thái **PAUSED**.

Để thêm tên học viên:

~~~javascript
db.enrollments.aggregate([
  {
    $match: {
      tenantId: "school-a",
      courseId: "course-nosql",
      status: "ACTIVE"
    }
  },
  { $sort: { enrolledAt: -1, _id: -1 } },
  { $limit: 10 },
  {
    $lookup: {
      from: "students",
      let: { targetId: "$studentId", targetTenant: "$tenantId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$targetId"] },
                { $eq: ["$tenantId", "$$targetTenant"] }
              ]
            }
          }
        },
        { $project: { _id: 1, fullName: 1 } }
      ],
      as: "student"
    }
  },
  { $unwind: "$student" },
  {
    $project: {
      _id: 1,
      studentId: 1,
      studentName: "$student.fullName",
      enrolledAt: 1,
      status: 1
    }
  }
]);
~~~

Kết quả:

| studentId | studentName | enrolledAt (UTC) |
|---|---|---|
| student-01 | An | 2026-11-12 10:00 |
| student-02 | Bình | 2026-11-11 12:00 |

Khi quan hệ tăng lớn, không nên đọc toàn bộ học viên cùng lúc rồi phân trang ở client. Dùng **limit** và cursor theo cặp **(enrolledAt, _id)** để số bản ghi của từng trang được giới hạn từ cơ sở dữ liệu. Với sort giảm dần, trang sau lấy document có **enrolledAt nhỏ hơn** thời điểm cuối trang trước, hoặc bằng thời điểm đó nhưng có **_id nhỏ hơn**.

## 9. Tham chiếu tới dữ liệu dùng chung: một nguồn chính, nhiều nơi tiêu thụ

Việc nhiều học viên cùng tham chiếu **course-nosql** minh họa loại **dữ liệu chia sẻ có danh tính độc lập**. Tên, mô tả và trạng thái của khóa học thuộc collection **courses**. Khi quản trị đổi tên:

~~~javascript
db.courses.updateOne(
  { _id: "course-nosql", tenantId: "school-a" },
  { $set: { title: "NoSQL thực hành" } }
);
~~~

Lần đọc tiếp theo bằng cách join vào **courses** sẽ lấy tên mới, thay vì phải cập nhật từng enrollment. Cần lưu ý nếu có cache hoặc read model chứa tên khóa, các bản sao đó vẫn cần quy tắc đồng bộ/invalidating theo yêu cầu độ mới.

### Khi nào nên sao chép một vài trường?

Đôi khi màn hình “Khóa học của tôi” được đọc rất thường xuyên và phép join trở thành chi phí đáng kể. Khi đó có thể bổ sung snapshot nhỏ:

~~~javascript
{
  _id: "enrollment-001",
  tenantId: "school-a",
  studentId: "student-01",
  courseId: "course-nosql",
  enrolledAt: ISODate("2026-11-12T10:00:00Z"),
  status: "ACTIVE",
  courseTitleCache: "NoSQL thực hành"
}
~~~

Nhưng **courseTitleCache** là dữ liệu dẫn xuất, cần một hợp đồng rõ:

- **Nguồn chính** là **courses.title**.
- Độ trễ chấp nhận được khi đổi tên là bao lâu?
- Event cập nhật tên được gửi, retry và xử lý trùng thế nào?
- Khi consumer bỏ sót event, hệ thống đối soát hoặc dựng lại cache ra sao?
- Khi xóa khóa, trường dẫn xuất và các quan hệ còn tồn tại được xử lý thế nào?

Nếu nghiệp vụ yêu cầu **luôn hiển thị tên hiện tại ngay sau khi đổi**, một cache bất đồng bộ chưa chắc phù hợp. Nếu nghiệp vụ chấp nhận trễ ngắn, sao chép có kiểm soát có thể giảm chi phí đọc. **Phi chuẩn hóa phải có quy tắc đồng bộ**, không chỉ là thêm trường để truy vấn nhanh.

### Phân biệt bản sao dẫn xuất với snapshot lịch sử

Đơn hàng đã thanh toán thường cần giữ nguyên **tên và giá sản phẩm tại thời điểm mua**:

~~~javascript
{
  _id: "order-101",
  items: [{
    productId: "product-42",
    nameAtPurchase: "Bút xanh",
    unitPriceAtPurchase: 10000,
    quantity: 2
  }]
}
~~~

Tại đây **nameAtPurchase** và **unitPriceAtPurchase** là dữ liệu lịch sử có chủ đích. Nếu sản phẩm đổi tên hoặc giá, hóa đơn cũ **không nên tự cập nhật** theo catalog. Ngược lại, tên khóa học trong danh sách học viên được yêu cầu hiển thị mới nhất. Cả hai đều có thể chứa “dữ liệu lặp”, nhưng **mục đích và quy tắc cập nhật trái ngược**.

Một quyết định quan trọng khi nhúng dữ liệu là: **thông tin này mô tả thực thể ở hiện tại hay trạng thái tại thời điểm giao dịch?**

## 10. Ghi quan hệ: kiểm tra tồn tại, quyền và tính duy nhất

Một đăng ký khóa học thành công thường cần nhiều điều kiện:

1. Học viên tồn tại, thuộc tenant và có trạng thái được phép đăng ký.
2. Khóa học tồn tại, thuộc tenant, đang mở đăng ký.
3. Người thao tác có quyền đăng ký cho học viên đó.
4. Chưa có quan hệ hiện hành trái với quy tắc đăng ký.
5. Không tạo ra hai quan hệ trùng khi có retry hoặc hai request đồng thời.

Ví dụ thao tác tạo quan hệ theo cặp, với unique index đã thiết lập:

~~~javascript
db.enrollments.updateOne(
  {
    tenantId: "school-a",
    studentId: "student-01",
    courseId: "course-web"
  },
  {
    $setOnInsert: {
      enrolledAt: ISODate("2026-11-14T10:00:00Z"),
      status: "ACTIVE",
      progressPercent: 0
    }
  },
  { upsert: true }
);
~~~

**$setOnInsert** chỉ ghi các trường đó khi có insert; nếu cặp quan hệ đã tồn tại, lệnh không tự thay đổi trạng thái. Đoạn minh họa **giả định ứng dụng đã xác thực và kiểm tra học viên/khóa học trước đó**. Kiểm tra trước rồi upsert vẫn có thể gặp race với thao tác xóa hoặc thay trạng thái của đối tượng khác.

Với hai request cạnh tranh, unique index vẫn cần được giữ để bảo vệ tính duy nhất. Khi gặp lỗi duplicate key, ứng dụng phải phân biệt “đăng ký đã tồn tại” với các lỗi khác và quyết định trả trạng thái idempotent hay thông báo xung đột dựa trên nghiệp vụ.

### Ranh giới nguyên tử và transaction

MongoDB bảo đảm thao tác ghi đối với **một document** có tính nguyên tử ở phạm vi document đó. Nhưng kiểm tra document học viên, kiểm tra document khóa học và chèn enrollment liên quan **nhiều document/collection**. Đây không mặc nhiên là một thao tác nguyên tử thống nhất.

Nếu yêu cầu bắt buộc toàn bộ chuỗi kiểm tra và ghi tuân thủ một trạng thái nhất quán, có thể cân nhắc **transaction nhiều document**, với điều kiện triển khai MongoDB hỗ trợ và ứng dụng đã xác định retry/conflict. Dùng transaction không tự sửa một quy tắc nghiệp vụ mơ hồ. Ví dụ, nếu khóa đang bị đóng đăng ký bởi một thao tác khác, cần quy định rõ điều kiện nào ngăn đăng ký và thao tác cập nhật khóa có phối hợp với thao tác ghi enrollment như thế nào.

Một thiết kế thực tế thường kết hợp:

- **Unique index** cho bất biến không trùng cặp.
- **Conditional update** để chuyển trạng thái chỉ khi đang ở trạng thái cho phép.
- **Transaction** khi nhất quán nhiều document thật sự là yêu cầu, đồng thời xử lý xung đột, retry và thất bại.
- **Idempotency key** hoặc định danh thao tác cho nghiệp vụ có thể bị gọi lại qua mạng, nhất là khi có hệ ngoài như thanh toán.
- **Đối soát** để phát hiện tham chiếu lỗi hoặc cập nhật bất đồng bộ bị bỏ sót.

Không nên dùng transaction cho mọi lần đọc chỉ vì quan hệ nhiều-nhiều. Phạm vi giao dịch và chi phí cần xuất phát từ bất biến nghiệp vụ.

## 11. Trạng thái của mối quan hệ và lịch sử

Một enrollment có thể chuyển giữa các trạng thái:

~~~mermaid
flowchart LR
    A["ACTIVE"] -->|"tạm ngừng"| B["PAUSED"]
    B -->|"học lại"| A
    A -->|"hoàn tất"| C["COMPLETED"]
    A -->|"hủy"| D["CANCELLED"]
    B -->|"hủy"| D
~~~

Sơ đồ chỉ là một **quy tắc nghiệp vụ minh họa**. Không phải mọi hệ thống đều cho phép từ COMPLETED trở lại ACTIVE, hay cho phép CANCELLED đăng ký lại trên cùng một document. Cần chốt quy tắc từ nghiệp vụ trước khi đặt enum và index.

Một cập nhật có điều kiện:

~~~javascript
db.enrollments.updateOne(
  {
    tenantId: "school-a",
    studentId: "student-01",
    courseId: "course-nosql",
    status: "ACTIVE"
  },
  {
    $set: {
      status: "PAUSED",
      pausedAt: ISODate("2026-11-14T12:00:00Z")
    }
  }
);
~~~

Điều kiện **status: "ACTIVE"** có nghĩa chỉ bản ghi đang ACTIVE mới chuyển sang PAUSED bằng lệnh này. Ứng dụng nên kiểm tra **matchedCount/modifiedCount** để biết thao tác có thực sự tác động đúng đối tượng và trạng thái hay không.

Nếu phải lưu **từng lần đăng ký** như một phiên riêng, unique index **(tenantId, studentId, courseId)** không còn phù hợp với dữ liệu lịch sử. Một thiết kế mới có thể sử dụng **attemptId** riêng hoặc collection history, kèm ràng buộc “không có hơn một đăng ký ACTIVE cho một cặp” bằng cơ chế phù hợp. Không nên tự xóa lịch sử hoặc tạo thêm enrollment trùng mà chưa định nghĩa bản ghi nào là hiện hành.

## 12. Xóa thực thể được tham chiếu: tránh quan hệ mồ côi

Giả sử khóa học **course-nosql** bị xóa khỏi **courses**, nhưng các enrollment vẫn lưu **courseId: "course-nosql"**. Đây là **orphan reference**: tham chiếu còn tồn tại nhưng đối tượng đích không còn.

Trong document database, thường phải chọn chính sách rõ ràng:

| Chính sách | Cách hiểu | Ví dụ |
|---|---|---|
| **Restrict** | Không cho xóa khi vẫn có quan hệ cần giữ | Không xóa khóa còn học viên đang học |
| **Cascade** | Xóa hoặc hủy các quan hệ phụ thuộc | Xóa dữ liệu phiên tạm gắn với một tài khoản đã hủy |
| **Soft delete / archive** | Giữ đối tượng ở trạng thái đã dừng, ẩn khỏi truy cập bình thường | Khóa học ngừng mở nhưng lịch sử học tập vẫn cần |
| **Detach** | Bỏ tham chiếu, giữ dữ liệu độc lập còn hợp lệ | Gỡ một tag khỏi danh sách sản phẩm |
| **Snapshot** | Giữ bản mô tả lịch sử độc lập với thực thể sống | Ghi tên khóa tại thời điểm cấp chứng chỉ |

Không có chính sách mặc định đúng cho mọi quan hệ. Chẳng hạn, học viên đã hoàn thành khóa có thể cần chứng chỉ và dữ liệu tiến độ lâu dài; xóa tất cả enrollment khi bỏ khóa khỏi catalog có thể phá vỡ lịch sử nghiệp vụ.

Nếu quyết định cascade, quy trình thường cần:

1. Đặt trạng thái khóa **DELETING** hoặc chặn đăng ký mới.
2. Xác định toàn bộ enrollment liên quan và phạm vi xử lý.
3. Xóa/hủy theo batch hoặc transaction thích hợp với khối lượng và tính nhất quán.
4. Dọn cache, chỉ mục tìm kiếm, read model và dữ liệu dẫn xuất tương ứng.
5. Chỉ xác nhận xóa hoàn tất khi các bước bắt buộc được ghi nhận, kể cả lỗi retry.

Với nhiều triệu enrollment, một transaction bao trùm tất cả bản ghi thường không phải cách xử lý phù hợp. Quy trình batch idempotent, trạng thái tiến trình và cơ chế chặn ghi mới có thể cần thiết. Nếu bài toán yêu cầu xóa dữ liệu cá nhân, còn phải xác định phạm vi backup/archive và các bản sao khác theo chính sách áp dụng.

**Tham chiếu không tạo bảo vệ toàn vẹn tự động.** Nếu một client ghi trực tiếp enrollment với **studentId** không tồn tại, MongoDB không mặc nhiên từ chối như một ràng buộc khóa ngoại quan hệ. Kiểm tra và đối soát tham chiếu là trách nhiệm của thiết kế ứng dụng.

## 13. Đa tenant và tính đúng đắn của ID

Trong ứng dụng đa tenant, cùng một mã ngắn như **course-java** có thể được đặt trong hai tổ chức. Có hai cách tổ chức ID:

- **_id duy nhất toàn cục**: mọi khóa học có ID riêng; **tenantId** vẫn là trường bắt buộc để áp dụng quyền và phân vùng truy cập.
- **ID chỉ duy nhất trong tenant**: cần khóa định danh có phạm vi tenant, ví dụ ID ghép, và các unique index tương ứng. Không được dùng **_id** trùng trong cùng collection MongoDB nếu _id vẫn là khóa chính mặc định.

Dù cách nào, không thể chỉ tin **courseId** từ request. Cần giới hạn truy vấn bằng tenant và danh tính được xác thực, đồng thời không cho phép gán enrollment của học viên tenant A vào khóa tenant B.

Một unique index trên **tenantId, studentId, courseId** mô tả tính duy nhất của quan hệ trong tenant, nhưng **không tự chứng minh** hai ID ở hai đầu thuộc cùng tenant. Kiểm tra đó vẫn thuộc đường ghi và cơ chế dữ liệu nhất quán.

Khi sharding MongoDB, cách chọn shard key ảnh hưởng phân bố tải, vị trí dữ liệu và khả năng áp đặt unique index trên các trường khác. Các quy tắc unique index đối với sharded collection phụ thuộc cấu hình shard key; phải kiểm tra thiết kế thực tế trước khi dựa vào index làm bảo đảm duy nhất toàn hệ.

## 14. Quan sát hiệu năng: quan hệ có thể làm tăng fan-out

Giả sử hệ thống có **100.000 học viên**, mỗi học viên trung bình **8 khóa học**, và một khóa có thể có **50.000 học viên**. Khi dùng collection enrollments, số document quan hệ có thể vào khoảng:

\[
100\,000 \times 8 = 800\,000\ \text{enrollments}
\]

Đây chỉ là ước tính minh họa khi mỗi quan hệ được lưu một document. Tập quan hệ lớn vẫn có thể quản lý được với phân vùng và index hợp lý, nhưng một số truy vấn dễ trở thành vấn đề:

- Đọc toàn bộ học viên của một khóa mà **không phân trang** sẽ tạo payload lớn.
- Thực hiện từng truy vấn riêng để lấy tên khóa cho từng enrollment có thể tạo **N+1 queries**.
- Một khóa nổi tiếng có thể làm lưu lượng đọc/ghi tập trung vào cùng một tập index key hoặc shard.
- Duy trì **studentCount** bằng cách tăng một counter tập trung có thể gây contention và sai lệch nếu retry mà không có quy tắc idempotent.
- Join nhiều collection trong một truy vấn tổng hợp có thể tốn bộ nhớ, CPU và I/O.

Với MongoDB, đo kế hoạch thực thi của đường đọc enrollment:

~~~javascript
db.enrollments
  .find({
    tenantId: "school-a",
    courseId: "course-nosql",
    status: "ACTIVE"
  })
  .sort({ enrolledAt: -1, _id: -1 })
  .limit(10)
  .explain("executionStats");
~~~

Các tín hiệu hữu ích:

| Tín hiệu | Câu hỏi |
|---|---|
| **winningPlan**, **IXSCAN**, **COLLSCAN**, **SORT** | Query đang sử dụng index hay quét collection? Có bước sort riêng tốn tài nguyên không? |
| **totalKeysExamined** | Cần duyệt bao nhiêu khóa index cho trang kết quả? |
| **totalDocsExamined** | Cần đọc bao nhiêu document thực tế? |
| **nReturned** | Có trả đúng số hàng và điều kiện lọc không? |
| **Latency p95/p99 tại API** | Người dùng gặp độ trễ như thế nào dưới tải thực? |
| **Số lệnh DB trên một request** | Có xảy ra N+1 do đọc từng tham chiếu riêng không? |
| **Phân bố kích thước/tải theo khóa** | Có một course hoặc tenant trở thành điểm nóng không? |

Một kết quả explain của dữ liệu thử nghiệm nhỏ không đủ để kết luận hệ thống đạt độ trễ sản xuất. Nên thử với cardinality, phân bố khóa, concurrent updates, số lượng trường và tỷ lệ trạng thái gần với workload thật.

## 15. Khi nào nên tạo read model từ quan hệ?

Đôi khi trang tổng quan cần “số học viên đang ACTIVE của mỗi khóa” với tần suất cao. Có thể đếm trực tiếp:

~~~javascript
db.enrollments.countDocuments({
  tenantId: "school-a",
  courseId: "course-nosql",
  status: "ACTIVE"
});
~~~

Với dữ liệu mẫu, kết quả là **2**. Ở quy mô lớn và tải nhiều, ứng dụng có thể muốn lưu một trường đếm như **activeEnrollmentCount** trong **courses** hoặc một collection thống kê riêng.

Đây là **read model** hoặc dữ liệu phi chuẩn hóa. Nó giúp đọc nhanh, nhưng phải quản lý:

- Chỉ tăng khi một enrollment thực sự chuyển từ không ACTIVE sang ACTIVE.
- Chỉ giảm khi thật sự rời ACTIVE.
- Retry cùng sự kiện không được cộng/trừ hai lần.
- Khi xử lý sự kiện theo thứ tự khác dự kiến, số đếm không được sai mãi.
- Có quy trình đối soát định kỳ với **enrollments** làm nguồn chính.
- Nếu người dùng yêu cầu dữ liệu nhất quán tức thì, cập nhật bất đồng bộ có thể chưa đáp ứng.

Không nên thêm counter vào course mà bỏ qua quy tắc cập nhật của từng trạng thái. Trong tình huống có hàng nghìn đăng ký đồng thời, counter tập trung còn có thể là hot document; một read model phân mảnh hoặc gom theo batch có thể phù hợp hơn nếu chấp nhận độ trễ.

## 16. Các sai lầm dễ gặp khi xử lý dữ liệu chia sẻ

| Sai lầm | Hệ quả | Hướng suy nghĩ đúng |
|---|---|---|
| Nhúng toàn bộ course trong mỗi student | Đổi tên course phải cập nhật rất nhiều bản sao | Lưu nguồn chính ở courses, student/enrollment tham chiếu ID |
| Nhúng toàn bộ student vào một course | Document tăng không giới hạn, khó phân trang | Collection liên kết cho quan hệ có cardinality lớn |
| Ghi mảng ID ở cả hai đầu mà không có quy tắc đồng bộ | Một phía thấy đăng ký, phía kia không thấy | Chọn nguồn chính cho quan hệ và cơ chế dẫn xuất rõ ràng |
| Chỉ kiểm tra tồn tại trước khi insert | Hai request đồng thời có thể tạo bản ghi trùng | Unique index, ghi có điều kiện và xử lý race |
| Tạo reference rồi tưởng có khóa ngoại | Dễ có ID trỏ đến document không tồn tại | Kiểm tra ghi, chính sách xóa và đối soát orphan |
| Dùng $lookup trước khi giới hạn tập kết quả | Join quá nhiều bản ghi | Lọc, sort, limit theo access pattern trước khi join nếu ngữ nghĩa cho phép |
| Xóa course mà không xử lý enrollments | Quan hệ mồ côi, giao diện thiếu dữ liệu | Chọn restrict, soft delete, cascade hoặc snapshot theo nghiệp vụ |
| Dùng tên course làm thông tin lịch sử bất biến trong mọi màn hình | Dễ lẫn dữ liệu hiện tại với snapshot | Xác định lúc nào cần “giá trị hiện tại” và lúc nào cần “tại thời điểm xảy ra” |
| Chỉ tạo index theo studentId | Truy vấn ngược theo courseId có thể quét lớn | Thiết kế index riêng cho cả hai chiều quan trọng |
| Cache dữ liệu chia sẻ nhưng không có độ mới được định nghĩa | Tên/thông tin cập nhật hiển thị không nhất quán | Đặt hợp đồng đồng bộ, invalidation và quan sát độ trễ |

## 17. Quy trình quyết định có thể áp dụng lại

~~~mermaid
flowchart TD
    A["Dữ liệu được dùng ở nhiều document?"] --> B{"Có danh tính độc lập?"}
    B -->|"Không; thuộc một aggregate"| C["Ưu tiên cân nhắc nhúng"]
    B -->|"Có"| D["Tách thực thể chính và lưu reference"]
    D --> E{"Quan hệ có nhiều phần tử hoặc thuộc tính?"}
    E -->|"Ít, giới hạn và đọc một chiều"| F["Có thể dùng mảng ID"]
    E -->|"Nhiều, tăng lâu dài hoặc đọc hai chiều"| G["Collection liên kết"]
    F --> H["Xác định index và đường cập nhật"]
    G --> H
    H --> I["Định nghĩa unique, quyền, transaction và xóa"]
    I --> J["Đo truy vấn, join, fan-out và độ nhất quán"]
    J -->|"Không đáp ứng"| K["Đánh giá read model/phi chuẩn hóa có kiểm soát"]
~~~

Áp dụng luồng này đòi hỏi hiểu chính xác ý nghĩa của quan hệ. Với một trường **authorId** trong bài viết, tác giả là thực thể chia sẻ và reference thường hợp lý. Với một danh sách **orderItems** trong hóa đơn, các dòng hàng mô tả giao dịch và được đọc cùng đơn, nên embedding thường hợp lý. Với **students–courses**, các quan hệ phát triển độc lập, cần trạng thái và đọc theo cả hai chiều, nên collection liên kết là ứng viên rõ ràng.

Trước khi kết luận một mô hình, hãy trả lời:

1. **Phần nào là source of truth?** Nếu tên khóa đổi, nguồn dữ liệu nào quyết định tên hiển thị?
2. **Quan hệ có thuộc tính riêng không?** Nếu có, chúng đặt ở đâu?
3. **Tập quan hệ có giới hạn không?** Nếu không, tránh phụ thuộc mảng tăng vô hạn.
4. **Truy vấn hai chiều nào quan trọng?** Có index và pagination tương ứng chưa?
5. **Đăng ký trùng và ghi đồng thời được ngăn thế nào?**
6. **Khi một đầu bị xóa, xử lý đầu kia theo chính sách nào?**
7. **Nếu dùng dữ liệu dẫn xuất, chấp nhận độ trễ và đối soát ra sao?**
8. **Kết quả nào chứng minh thiết kế đúng?** Tập ID, thứ tự, tên hiện tại, trạng thái, tính duy nhất và độ trễ truy vấn.

## 18. Bài tập áp dụng

**Bài tập 1 — Dữ liệu chia sẻ.** Một thư viện có sách và tác giả. Một tác giả có thể viết nhiều sách; một sách có thể có nhiều tác giả, có thứ tự hiển thị và vai trò (tác giả chính, đồng tác giả). Hãy đề xuất document chính, collection liên kết, index và truy vấn danh sách tác giả của sách theo thứ tự đã quy định.

**Bài tập 2 — Tăng trưởng quan hệ.** Một sản phẩm nằm trong nhiều danh mục, còn một danh mục có thể chứa hàng triệu sản phẩm. So sánh mảng **productIds** nhúng trong category, mảng **categoryIds** trong product và collection **product_categories** theo hai đường đọc: “các danh mục của một sản phẩm” và “20 sản phẩm đầu trong một danh mục”.

**Bài tập 3 — Tính duy nhất.** Hai request gửi đăng ký cùng một khóa học trong cùng một thời điểm. Giải thích vì sao **findOne trước rồi insertOne** chưa đủ; chỉ ra unique index và cách ứng dụng xử lý lỗi duplicate key để tránh tạo hai enrollment.

**Bài tập 4 — Xóa dữ liệu.** Quản trị muốn xóa khóa học đang có 50.000 enrollment, trong đó có chứng chỉ đã cấp. Hãy nêu các câu hỏi nghiệp vụ phải chốt trước khi quyết định restrict, soft delete hoặc cascade, và cách phát hiện orphan references.

**Bài tập 5 — Tên mới và bản chụp cũ.** Khóa học đổi tên từ “NoSQL căn bản” thành “NoSQL thực hành”. Trang “Khóa học của tôi” phải dùng tên mới, còn chứng chỉ đã cấp phải ghi tên tại ngày cấp. Hãy chỉ ra trường nào là reference, trường nào là snapshot và quy tắc cập nhật tương ứng.

**Bài tập 6 — Truy vấn thực tế.** Dùng dữ liệu MongoDB trong bài để viết truy vấn trả về:

- Tất cả khóa học **ACTIVE** của An theo thứ tự đăng ký mới nhất.
- Danh sách học viên **ACTIVE** của khóa NoSQL.
- Số học viên **ACTIVE** của khóa NoSQL.
- Một bản ghi bị coi là orphan nếu **courseId** không tồn tại trong courses cùng tenant.

Với mỗi truy vấn, hãy giải thích **lọc theo khóa nào, index nào phù hợp, dữ liệu tham chiếu được lấy bằng cách nào và kết quả dự kiến là gì**.

Trong mô hình tài liệu, **tham chiếu không phải một lựa chọn “đối lập” tuyệt đối với nhúng**. Hai kỹ thuật thường phối hợp: nhúng dữ liệu nhỏ thuộc cùng aggregate, tham chiếu đến thực thể được chia sẻ và dùng document liên kết khi quan hệ nhiều-nhiều có vòng đời hoặc thuộc tính riêng. Quyết định cuối cùng phải được kiểm chứng bằng truy vấn thật, tính nhất quán khi ghi và hành vi khi dữ liệu thay đổi hoặc bị xóa.
