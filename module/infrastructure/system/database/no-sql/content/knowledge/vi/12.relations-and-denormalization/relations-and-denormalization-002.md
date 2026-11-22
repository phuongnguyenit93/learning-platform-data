# Chọn nhúng, tham chiếu hoặc lưu cạnh quan hệ theo mô hình

Trong NoSQL, dữ liệu có quan hệ với nhau không nhất thiết được tổ chức thành những bảng và khóa ngoại giống cơ sở dữ liệu quan hệ. Một quan hệ có thể được biểu diễn bằng **object nhúng trong document**, **ID tham chiếu đến thực thể khác**, **document liên kết chứa hai ID**, **cạnh (edge) trong cơ sở dữ liệu đồ thị**, hoặc các **danh sách kề (adjacency lists)** được vật chất hóa để đọc nhanh trong key–value/wide-column store.

Các phương án này có thể cho ra giao diện giống hệt nhau nhưng khác biệt lớn về hiệu năng, tính nhất quán, cách cập nhật, quy mô tăng trưởng và quy tắc xóa. Chẳng hạn, “học viên A đang học khóa C” có thể là một ID trong mảng của A, một document đăng ký riêng, hoặc một cạnh **ENROLLED_IN**. Cách nào phù hợp phụ thuộc vào việc ứng dụng cần truy vấn **theo học viên**, **theo khóa học**, **duyệt nhiều bước quan hệ**, hay **thay đổi trạng thái của chính mối quan hệ**.

Mục tiêu của bài là chọn biểu diễn quan hệ dựa trên **hình dạng dữ liệu**, **access patterns**, **bất biến nghiệp vụ** và **khả năng của từng hệ NoSQL**. Ví dụ chính dùng MongoDB cho mô hình tài liệu, Neo4j/Cypher để minh họa đồ thị và các mô hình key–value/wide-column để làm rõ khi quan hệ phải được lưu theo đường truy cập. Cú pháp và bảo đảm của mỗi sản phẩm không tự áp dụng cho sản phẩm khác.

## 1. Phân biệt “thực thể”, “giá trị con” và “mối quan hệ”

Giả sử có một nền tảng học trực tuyến:

- Một **khóa học** có cấu hình hiển thị và danh sách mục tiêu học tập.
- Một **giảng viên** có hồ sơ riêng và có thể dạy nhiều khóa học.
- Một **học viên** có thể đăng ký nhiều khóa học, và mỗi khóa có thể có nhiều học viên.
- Mỗi **đăng ký** có ngày đăng ký, trạng thái và tiến độ.
- Một học viên có thể **theo dõi** học viên khác; sản phẩm có thể gợi ý người quen thông qua các bước kết nối.

Những khái niệm trên không cùng một loại:

| Dữ liệu | Danh tính độc lập? | Vòng đời/cập nhật | Gợi ý biểu diễn |
|---|---|---|---|
| Cấu hình hiển thị của một khóa | Thường không cần tách thành thực thể | Thường được đọc và sửa cùng khóa | Nhúng trong khóa học |
| Giảng viên | Có ID và hồ sơ riêng | Được nhiều khóa học sử dụng; cập nhật độc lập | Tham chiếu instructorId |
| Đăng ký học viên–khóa học | Có thể là thực thể nghiệp vụ riêng | Có status, tiến độ, lịch sử | Document liên kết hoặc cạnh có thuộc tính |
| Quan hệ theo dõi giữa hai người | Quan hệ chính là dữ liệu cần duyệt | Thêm/bỏ quan hệ; có thể duyệt nhiều bước | Cạnh đồ thị hoặc adjacency model |
| Tên khóa học tại thời điểm cấp chứng chỉ | Giá trị lịch sử, không phải trạng thái hiện tại | Không tự đổi khi tên khóa học đổi | Snapshot nhúng trong chứng chỉ |

**Nhúng** phù hợp khi phần dữ liệu con thuộc cùng một đơn vị nghiệp vụ và không cần vòng đời riêng. **Tham chiếu** phù hợp khi đối tượng được dùng chung hoặc có danh tính độc lập. **Cạnh quan hệ** đặc biệt hữu ích khi quan hệ có thuộc tính riêng, số lượng liên kết lớn hoặc ứng dụng cần duyệt đồ thị.

Không nên biến tất cả object lồng nhau trong JSON thành thực thể độc lập; cũng không nên nhúng mọi thực thể liên quan chỉ để giảm một truy vấn.

## 2. Ba phương án cơ bản

### 2.1. Nhúng (embedding)

Nhúng đặt dữ liệu con vào trong document/value của thực thể cha:

~~~javascript
{
  _id: "course-nosql",
  tenantId: "school-a",
  title: "NoSQL căn bản",
  settings: {
    visibility: "PUBLIC",
    language: "vi",
    allowComments: true
  },
  learningObjectives: [
    "Hiểu mô hình dữ liệu",
    "Thiết kế truy vấn theo nhu cầu"
  ]
}
~~~

**settings** và **learningObjectives** ở đây được xem như những giá trị thuộc khóa học. Khi mở trang chi tiết, ứng dụng đọc được chúng trong một document. Nếu người quản trị thay đổi **allowComments**, có thể cập nhật field của cùng document.

Nhúng thường đem lại:

- Một đường đọc đơn giản để lấy aggregate đầy đủ.
- Ít phép ghép/truy vấn bổ sung.
- Cơ hội cập nhật nhiều trường trong một đơn vị có ranh giới nguyên tử phù hợp, ví dụ một MongoDB document.
- Dữ liệu con có vòng đời gắn với document cha.

Nhưng nhúng có thể gây khó khăn nếu mảng tăng không giới hạn, đối tượng con cần truy vấn độc lập, nhiều writer tranh chấp cùng document, hoặc dữ liệu con được chia sẻ rộng giữa nhiều thực thể.

### 2.2. Tham chiếu (referencing)

Thay vì sao chép toàn bộ hồ sơ giảng viên trong mỗi khóa học, khóa học lưu ID:

~~~javascript
// courses
{
  _id: "course-nosql",
  tenantId: "school-a",
  title: "NoSQL căn bản",
  instructorId: "instructor-07"
}

// instructors
{
  _id: "instructor-07",
  tenantId: "school-a",
  displayName: "Giảng viên An",
  bio: "Giảng dạy hệ thống dữ liệu"
}
~~~

Hồ sơ giảng viên được quản lý tại **instructors**. Khi đổi tên hiển thị, ứng dụng cập nhật một hồ sơ thay vì sửa tất cả khóa học do người này dạy.

Đổi lại, trang chi tiết khóa học cần một đường lấy hồ sơ giảng viên: truy vấn thứ hai, truy vấn gom theo **$in**, phép **$lookup** hoặc cache theo hợp đồng độ mới. **Tham chiếu bằng ID không tự tạo ràng buộc khóa ngoại** trong MongoDB: ứng dụng phải kiểm tra ID, quyền, tenant và xử lý khi giảng viên bị xóa.

### 2.3. Lưu chính mối quan hệ thành dữ liệu (edge / association)

Với quan hệ nhiều-nhiều giữa học viên và khóa học:

~~~javascript
// enrollments
{
  _id: "enrollment-101",
  tenantId: "school-a",
  studentId: "student-01",
  courseId: "course-nosql",
  enrolledAt: ISODate("2026-11-14T09:00:00Z"),
  status: "ACTIVE",
  progressPercent: 35
}
~~~

Document này không chỉ nói rằng hai đối tượng có liên hệ; nó chứa **thuộc tính của quan hệ**. Ngày đăng ký, trạng thái và tiến độ thuộc về **lần tham gia khóa học**, không thuộc chung hồ sơ học viên hay định nghĩa khóa học.

Trong graph database, cùng ý nghĩa có thể biểu diễn bằng một cạnh:

~~~text
(:Student {id: "student-01"})
       |
       | [:ENROLLED_IN {
       |      enrolledAt: ...,
       |      status: "ACTIVE",
       |      progressPercent: 35
       |  }]
       v
(:Course {id: "course-nosql"})
~~~

**Document liên kết** và **graph edge** cùng có thể mô hình hóa mối quan hệ, nhưng không có cùng API/traversal/performance mặc định. Một collection MongoDB chứa **studentId, courseId** không tự biến thành đồ thị với khả năng duyệt nhiều bước tối ưu như một graph engine.

## 3. Quyết định dựa trên đường đọc và đường ghi

Trước khi chọn mô hình, liệt kê các câu hỏi sản phẩm thực sự cần trả lời:

| Access pattern | Đầu vào | Kết quả | Tác động lên cách lưu |
|---|---|---|---|
| Chi tiết một khóa học | courseId | Tiêu đề, cấu hình, mục tiêu | Nhúng các giá trị con nhỏ, ổn định |
| Hiển thị tên giảng viên hiện tại | courseId | Hồ sơ instructor | Reference tới instructor |
| Danh sách khóa của học viên | tenantId, studentId | Các khóa đã đăng ký, status, ngày đăng ký | Index theo studentId trên quan hệ |
| Danh sách học viên của một khóa | tenantId, courseId | Các enrollment hiện hành | Index ngược theo courseId |
| Thêm một đăng ký | studentId, courseId | Không trùng, lưu enrolledAt | Unique key/index hoặc điều kiện ghi |
| Hoàn thành khóa học | studentId, courseId | Cập nhật progress/status của quan hệ | Edge/association có thuộc tính |
| Gợi ý bạn của bạn | userId, tối đa 2–3 bước | Các user reachable qua follow/friend | Traversal graph hoặc read model được chuẩn bị |
| Cấp chứng chỉ | enrollmentId | Tên khóa tại thời điểm cấp | Snapshot lịch sử, không tự cập nhật theo catalog |

Một **mẫu đọc thường xuyên** là lý do để co-locate dữ liệu hoặc tạo đường truy cập thích hợp. Một **bất biến ghi** là lý do để chọn phạm vi cập nhật nguyên tử/điều kiện. Khi hai yêu cầu xung đột, có thể phải tách nguồn chính và thêm read model, thay vì cố thỏa mọi thao tác bằng một document.

## 4. Cardinality và tăng trưởng của quan hệ

**Cardinality** trả lời: mỗi đối tượng có thể liên kết tới bao nhiêu đối tượng khác?

~~~mermaid
flowchart LR
    A["Học viên"] -->|"nhiều-nhiều"| B["Khóa học"]
    C["Khóa học"] -->|"một-một hoặc một-nhiều theo nghiệp vụ"| D["Cấu hình"]
    E["Giảng viên"] -->|"một-nhiều"| F["Khóa học do giảng viên dạy"]
~~~

Ba trường hợp cần phân biệt:

**Một–một (1:1):** cấu hình nhỏ và chỉ có nghĩa khi khóa học tồn tại thường phù hợp với embedding. Tuy nhiên, nếu hai phần có phân quyền, vòng đời hoặc tốc độ cập nhật khác nhau, tách document cũng có thể hợp lý.

**Một–nhiều (1:N):** có thể nhúng nếu N **nhỏ và được giới hạn**. Nếu N tăng lâu dài như bình luận, tin nhắn hoặc log sự kiện, dùng collection riêng và index/phân trang thường an toàn hơn.

**Nhiều–nhiều (N:M):** ví dụ học viên–khóa học. Có thể lưu một mảng ID ở mỗi phía nếu quan hệ rất nhỏ, ít thay đổi và chỉ đọc một chiều; nhưng khi cả hai phía lớn, cần thuộc tính quan hệ và truy vấn hai chiều, một **association collection / edge** thường có lợi.

Ví dụ nếu có **100.000 học viên**, mỗi người trung bình tham gia **8 khóa**, số quan hệ khoảng:

\[
100\,000 \times 8 = 800\,000\ \text{enrollments}
\]

Nếu một khóa nổi tiếng có **50.000 học viên**, nhúng cả 50.000 enrollment vào document khóa học sẽ làm document tăng liên tục và nhiều thao tác ghi dồn vào một điểm. Với MongoDB, còn có giới hạn kích thước BSON document **16 MiB**, nhưng thiết kế có thể không phù hợp từ trước khi chạm giới hạn đó.

Một association collection cho phép mỗi quan hệ là một document, phân trang độc lập theo cả hai chiều. Trong graph database, số cạnh nối với một node (**degree**) có thể lớn; phải thiết kế traversal tránh fan-out không giới hạn, không suy rằng đồ thị tự xử lý tốt mọi node có hàng triệu cạnh trong mọi truy vấn.

## 5. Ví dụ MongoDB: nhúng dữ liệu con, tham chiếu thực thể, tách quan hệ

### 5.1. Các collection chính

~~~javascript
db.students.insertMany([
  {
    _id: "student-01",
    tenantId: "school-a",
    displayName: "Bình"
  },
  {
    _id: "student-02",
    tenantId: "school-a",
    displayName: "Chi"
  }
]);

db.instructors.insertOne({
  _id: "instructor-07",
  tenantId: "school-a",
  displayName: "Giảng viên An",
  bio: "Giảng dạy hệ thống dữ liệu"
});

db.courses.insertMany([
  {
    _id: "course-nosql",
    tenantId: "school-a",
    title: "NoSQL căn bản",
    instructorId: "instructor-07",
    settings: { visibility: "PUBLIC", allowComments: true },
    learningObjectives: [
      "Hiểu mô hình dữ liệu",
      "Thiết kế truy vấn theo nhu cầu"
    ]
  },
  {
    _id: "course-java",
    tenantId: "school-a",
    title: "Java căn bản",
    instructorId: "instructor-07",
    settings: { visibility: "PUBLIC", allowComments: true },
    learningObjectives: ["Nắm cú pháp", "Viết chương trình cơ bản"]
  }
]);
~~~

Cùng một giảng viên có thể được hai khóa tham chiếu. Các trường **settings** và **learningObjectives** được nhúng vì giả định chúng nhỏ, có giới hạn và được đọc chủ yếu cùng khóa. Nếu sản phẩm sau này cho phép hàng triệu lesson/asset trong mỗi khóa, không nên tự động nhúng toàn bộ lesson/asset vào cùng document.

### 5.2. Collection liên kết có thuộc tính quan hệ

~~~javascript
db.enrollments.insertMany([
  {
    _id: "enrollment-101",
    tenantId: "school-a",
    studentId: "student-01",
    courseId: "course-nosql",
    enrolledAt: ISODate("2026-11-14T09:00:00Z"),
    status: "ACTIVE",
    progressPercent: 35
  },
  {
    _id: "enrollment-102",
    tenantId: "school-a",
    studentId: "student-01",
    courseId: "course-java",
    enrolledAt: ISODate("2026-11-12T08:00:00Z"),
    status: "ACTIVE",
    progressPercent: 60
  },
  {
    _id: "enrollment-103",
    tenantId: "school-a",
    studentId: "student-02",
    courseId: "course-nosql",
    enrolledAt: ISODate("2026-11-13T10:00:00Z"),
    status: "PAUSED",
    progressPercent: 10
  }
]);
~~~

Dữ liệu mẫu thể hiện quan hệ:

~~~text
student-01 -- enrollment-101 (ACTIVE, 35%) --> course-nosql
student-01 -- enrollment-102 (ACTIVE, 60%) --> course-java
student-02 -- enrollment-103 (PAUSED, 10%) --> course-nosql
~~~

Chỉ **student-01** đang có enrollment **ACTIVE** ở khóa NoSQL; **student-02** có quan hệ nhưng hiện tạm dừng. Định nghĩa “đang học” vì vậy không thể chỉ kiểm tra **courseId** có xuất hiện trong mảng ID hay không.

## 6. Chọn index cho quan hệ theo cả hai chiều

Với giả định một cặp học viên–khóa học chỉ có **một bản ghi enrollment** (trạng thái có thể thay đổi), tạo unique index:

~~~javascript
db.enrollments.createIndex(
  { tenantId: 1, studentId: 1, courseId: 1 },
  { unique: true, name: "uniq_tenant_student_course" }
);
~~~

Index bảo vệ tính duy nhất của bộ khóa, ngay cả khi hai request đăng ký cùng lúc. Nếu ứng dụng muốn lưu **nhiều lần đăng ký lịch sử** cho một cặp, ràng buộc này không còn phù hợp; cần định nghĩa **attemptId** hoặc cấu trúc history riêng rồi chọn quy tắc “tối đa một đăng ký ACTIVE” có cơ chế thực thi phù hợp.

Đường đọc từ học viên sang khóa học:

~~~javascript
db.enrollments.createIndex(
  {
    tenantId: 1,
    studentId: 1,
    status: 1,
    enrolledAt: -1,
    _id: -1
  },
  { name: "by_student_status_time" }
);
~~~

Đường đọc ngược từ khóa học sang học viên:

~~~javascript
db.enrollments.createIndex(
  {
    tenantId: 1,
    courseId: 1,
    status: 1,
    enrolledAt: -1,
    _id: -1
  },
  { name: "by_course_status_time" }
);
~~~

Hai index phản ánh **hai câu hỏi khác nhau**. Index bắt đầu bằng **studentId** không tự tối ưu được truy vấn chỉ có **courseId**. Đổi lại, mỗi index bổ sung cần không gian lưu và chi phí cập nhật; chỉ giữ những index phù hợp với workload thực tế.

### Đọc danh sách khóa của một học viên

~~~javascript
db.enrollments.find(
  {
    tenantId: "school-a",
    studentId: "student-01",
    status: "ACTIVE"
  },
  { _id: 1, courseId: 1, enrolledAt: 1, progressPercent: 1 }
)
.sort({ enrolledAt: -1, _id: -1 })
.limit(20);
~~~

Theo dữ liệu mẫu, kết quả lần lượt là **course-nosql** (35%) rồi **course-java** (60%).

### Đọc học viên đang học trong một khóa

~~~javascript
db.enrollments.find(
  {
    tenantId: "school-a",
    courseId: "course-nosql",
    status: "ACTIVE"
  },
  { _id: 1, studentId: 1, enrolledAt: 1 }
)
.sort({ enrolledAt: -1, _id: -1 })
.limit(20);
~~~

Kết quả chỉ có **student-01** vì enrollment của **student-02** đang **PAUSED**.

Khi tập quan hệ lớn, **phân trang trên collection liên kết** có lợi hơn tải mảng nhiều nghìn ID về client rồi cắt trang. Dùng cặp **(enrolledAt, _id)** làm khóa sắp xếp ổn định và thiết kế cursor theo hướng sắp xếp; tránh dựa vào offset sâu khi dữ liệu lớn và liên tục thay đổi.

## 7. Lấy chi tiết đối tượng được tham chiếu: $lookup hoặc đọc hai pha

Đường đọc enrollment chỉ trả **courseId**, nhưng giao diện cần **title hiện tại** của khóa học. Có hai cách:

**Đọc hai pha:** lấy trang enrollments; thu tập courseId; truy vấn courses bằng **_id: { $in: [...] }** trong phạm vi tenant; ghép lại theo thứ tự enrollment ở ứng dụng. Điều này tránh một truy vấn khóa học cho mỗi dòng (**N+1 queries**).

**Aggregation $lookup:** ghép khóa học ngay trong query, sau khi giới hạn tập liên kết:

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
  { $limit: 20 },
  {
    $lookup: {
      from: "courses",
      let: {
        courseRef: "$courseId",
        tenantRef: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$courseRef"] },
                { $eq: ["$tenantId", "$$tenantRef"] }
              ]
            }
          }
        },
        { $project: { _id: 1, title: 1, instructorId: 1 } }
      ],
      as: "course"
    }
  },
  { $unwind: "$course" },
  {
    $project: {
      _id: 0,
      courseId: 1,
      courseTitle: "$course.title",
      enrolledAt: 1,
      progressPercent: 1
    }
  }
]);
~~~

Kết quả mong đợi:

| courseId | courseTitle | progressPercent |
|---|---|---:|
| course-nosql | NoSQL căn bản | 35 |
| course-java | Java căn bản | 60 |

**$lookup không tạo khóa ngoại.** Nếu enrollment trỏ tới một khóa đã bị xóa, **course** sẽ là mảng rỗng. **$unwind** trong ví dụ loại phần tử đó khỏi kết quả; khi cần phát hiện dữ liệu mồ côi, phải giữ lại bản liên kết chưa match, chẳng hạn với **preserveNullAndEmptyArrays: true**, và có cơ chế đối soát.

Cần lọc và phân quyền theo tenant ở cả đầu quan hệ và bản ghi đích. Một chuỗi **courseId** có vẻ hợp lệ chưa chứng minh người dùng được phép truy cập khóa đó.

## 8. Khi mối quan hệ có vòng đời riêng

Một mối quan hệ không nhất thiết tồn tại vĩnh viễn ở trạng thái “có hoặc không”. Enrollment có thể đi qua nhiều trạng thái:

~~~mermaid
flowchart LR
    A["ACTIVE"] -->|"tạm dừng"| B["PAUSED"]
    B -->|"tiếp tục"| A
    A -->|"hoàn thành"| C["COMPLETED"]
    A -->|"hủy"| D["CANCELLED"]
    B -->|"hủy"| D
~~~

Lưu **status** trên association document giúp thay đổi trạng thái mà không phải sửa nguyên document student hay course. Ví dụ MongoDB:

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

Điều kiện **status: "ACTIVE"** buộc transition chỉ xảy ra từ trạng thái được cho phép. Ứng dụng cần kiểm tra **matchedCount/modifiedCount**, xử lý retry và xác định có cho phép tiếp tục từ PAUSED hay không.

Nếu học viên có thể đăng ký lại nhiều lần và cần lưu lịch sử từng lượt, mối quan hệ thực tế là **một chuỗi enrollment attempts**, không chỉ một cặp ID. Khi đó cần mô hình hóa **attemptId**, mốc thời gian và ràng buộc “một lượt hiện hành” riêng.

**Quan hệ có thuộc tính riêng** là tín hiệu mạnh cho việc lưu một record/cạnh riêng, nhưng không phải luật tuyệt đối. Một quan hệ một–nhiều rất nhỏ với thuộc tính đơn giản vẫn có thể được nhúng nếu nó gắn chặt vào vòng đời của chủ thể cha.

## 9. Lưu cạnh trong graph database: khi traversal là yêu cầu chính

Một graph database biểu diễn trực tiếp **node** và **relationship/edge**. Ví dụ với Neo4j/Cypher:

~~~cypher
MERGE (s:Student {tenantId: 'school-a', id: 'student-01'})
ON CREATE SET s.displayName = 'Bình'

MERGE (c:Course {tenantId: 'school-a', id: 'course-nosql'})
ON CREATE SET c.title = 'NoSQL căn bản'

MERGE (s)-[r:ENROLLED_IN]->(c)
ON CREATE SET
  r.enrolledAt = datetime('2026-11-14T09:00:00Z'),
  r.status = 'ACTIVE',
  r.progressPercent = 35;
~~~

**ENROLLED_IN** là kiểu quan hệ và **status/progressPercent** là thuộc tính của cạnh. Cypher tập trung vào mẫu hình quan hệ:

~~~cypher
MATCH (s:Student {tenantId: 'school-a', id: 'student-01'})
      -[r:ENROLLED_IN {status: 'ACTIVE'}]->
      (c:Course {tenantId: 'school-a'})
RETURN c.id AS courseId,
       c.title AS courseTitle,
       r.progressPercent AS progress
ORDER BY r.enrolledAt DESC
LIMIT 20;
~~~

Điểm mạnh của mô hình đồ thị thể hiện rõ khi người dùng cần duyệt từ node qua nhiều cạnh, chẳng hạn “bạn của những người tôi theo dõi”, “khóa học được nhiều người cùng nhóm quan tâm”, “đường kết nối ngắn nhất” hoặc “những thực thể chịu ảnh hưởng qua 3 tầng quan hệ”.

~~~text
(student-01)
     |
     | FOLLOWS
     v
(student-02)
     |
     | FOLLOWS
     v
(student-03)
~~~

Với một truy vấn tìm người dùng reachable qua tối đa hai bước:

~~~cypher
MATCH (me:Student {tenantId: 'school-a', id: 'student-01'})
      -[:FOLLOWS*1..2]->
      (candidate:Student {tenantId: 'school-a'})
WHERE candidate <> me
RETURN DISTINCT candidate.id AS studentId
LIMIT 50;
~~~

Đây là ví dụ traversal, không phải yêu cầu rằng mọi ứng dụng có quan hệ N:M đều phải dùng graph database. Nếu chỉ cần **“liệt kê khóa của một học viên”** và **“liệt kê học viên của một khóa”**, association collection có index thường đã đáp ứng tốt.

### Graph edge không miễn trừ ràng buộc nghiệp vụ

- **MERGE** mô tả việc khớp hoặc tạo mẫu quan hệ; không nên suy từ đó rằng mọi tình huống cạnh tranh ghi đã được chặn trùng nếu chưa thiết kế constraints/locking phù hợp.
- Quan hệ có thể mang thuộc tính, nhưng **một cạnh có status** không tự bảo đảm cạnh đó luôn hợp lệ theo state machine.
- Một node rất nhiều cạnh và phép duyệt sâu có thể tạo fan-out lớn; vẫn phải giới hạn độ sâu, điều kiện lọc và lượng kết quả.
- Quan hệ liên tenant cần kiểm soát dữ liệu ở **cả hai node**, không chỉ trên node bắt đầu.
- Khi xóa node/cạnh, cần có quy tắc xử lý lịch sử và những bản sao dẫn xuất ở ngoài graph.

**Chọn graph vì cần duyệt liên kết như một hoạt động chính**, không chỉ vì trên sơ đồ có nhiều mũi tên.

## 10. Khi nào một array ID là đủ?

Không phải mọi mối quan hệ đều cần một collection riêng. Ví dụ một khóa có **tối đa 5 moderator**, ít thay đổi và chỉ cần đọc moderator IDs khi mở trang quản lý:

~~~javascript
{
  _id: "course-nosql",
  tenantId: "school-a",
  moderatorIds: ["user-11", "user-12"]
}
~~~

MongoDB hỗ trợ thao tác mảng theo set:

~~~javascript
db.courses.updateOne(
  { _id: "course-nosql", tenantId: "school-a" },
  { $addToSet: { moderatorIds: "user-13" } }
);
~~~

**$addToSet** không thêm cùng một ID lần nữa nếu phần tử đã có trong array. Nhưng nó **không** tự kiểm tra user-13 có tồn tại, có cùng tenant, có đủ quyền làm moderator hay tổng số moderator chưa vượt mức 5. Muốn giới hạn số lượng dưới ghi đồng thời, cần cơ chế điều kiện cập nhật hoặc mô hình khác phù hợp.

Mảng ID thuận lợi khi:

- Cardinality **nhỏ và có giới hạn thực tế**.
- Quan hệ không có nhiều thuộc tính riêng.
- Đọc chủ yếu từ một phía.
- Không cần phân trang từng liên kết.
- Vòng đời quan hệ gắn chặt với document sở hữu.

Ngược lại, nếu một course có hàng trăm nghìn học viên, một **studentIds[]** trong document course sẽ tăng liên tục, khó phân trang, và dồn ghi vào cùng document. Một collection liên kết sẽ hợp lý hơn.

## 11. Tránh lưu hai chiều thành hai nguồn sự thật độc lập

Một ý tưởng khác là lưu mảng ID ở **cả hai bên**:

~~~javascript
// student-01
{ courseIds: ["course-nosql"] }

// course-nosql
{ studentIds: ["student-01"] }
~~~

Ứng dụng muốn đăng ký học viên phải ghi hai document. Nếu ghi **student.courseIds** thành công nhưng cập nhật **course.studentIds** thất bại, hai truy vấn trả kết quả khác nhau.

~~~mermaid
flowchart TD
    A["Đăng ký student-01 vào course-nosql"] --> B["Ghi student.courseIds"]
    B --> C{"Ghi course.studentIds thành công?"}
    C -->|Có| D["Hai chiều khớp nhau"]
    C -->|Không| E["Dữ liệu lệch hai chiều"]
    E --> F["Retry/đối soát hoặc thiết kế lại nguồn quan hệ"]
~~~

Có thể dùng transaction nhiều document trong môi trường MongoDB hỗ trợ, nhưng ở quy mô lớn việc cập nhật hai array không giới hạn vẫn bất lợi. Thông thường nên chọn **một nguồn chính cho mối quan hệ**, ví dụ **enrollments**, rồi:

- Query trực tiếp theo chiều studentId bằng index.
- Query trực tiếp theo chiều courseId bằng index.
- Hoặc tạo read model nếu thực sự cần dữ liệu đã sắp/đếm sẵn cho hiệu năng, và chấp nhận quy tắc đồng bộ được định nghĩa.

**Dữ liệu lặp không nhất thiết sai**. Vấn đề là không rõ **bản nào là nguồn chính**, thời điểm bản sao được làm mới và cách xử lý lỗi một phần.

## 12. Đối chiếu key–value: adjacency set và tính nhất quán nhiều key

Trong Redis, một quan hệ nhiều-nhiều đơn giản có thể được lưu thành Set:

~~~redis
SADD student:student-01:courses course-nosql course-java
SADD course:course-nosql:students student-01 student-02

SMEMBERS student:student-01:courses
SISMEMBER course:course-nosql:students student-01
~~~

Ưu điểm: truy vấn thành viên một tập hoặc lấy danh sách ID theo key thuận tiện. Nhưng hệ thống hiện có **hai tập khác nhau** đại diện cho một quan hệ. Nếu cả hai là nguồn chính, yêu cầu consistency sẽ trở nên phức tạp. Khi update một chiều mà chiều kia lỗi, dữ liệu lệch.

Trong Redis đơn máy, có thể có các cơ chế transaction/script cho một số thao tác nhiều key. Khi dùng Redis Cluster, các thao tác liên quan nhiều key còn phụ thuộc vào việc các key có thuộc cùng hash slot và các giới hạn lệnh hay không. Không được mặc định hai lệnh **SADD** tách rời là một giao dịch xuyên toàn cluster.

Với quan hệ có **enrolledAt**, **status**, **progressPercent**, Set chỉ lưu ID không còn đủ. Có thể:

1. Lưu một **Hash/JSON** cho mỗi quan hệ, các Set chỉ đóng vai trò index dẫn xuất.
2. Dùng document database/graph làm nguồn chính rồi đồng bộ Redis Set như cache/index.
3. Chọn mô hình key–value khác có hỗ trợ điều kiện ghi phù hợp.

**Một Set mang danh sách ID là adjacency list**, không đồng nghĩa một edge có thuộc tính và vòng đời riêng.

## 13. Đối chiếu wide-column: mỗi bảng phục vụ một chiều truy vấn

Trong Cassandra, dữ liệu thường được tổ chức theo **partition key** và **clustering columns** để phục vụ đường đọc đã biết.

Nếu thường truy vấn “khóa đang học theo student”, có thể tạo bảng:

~~~sql
-- Giả sử keyspace training đã được cấu hình cho môi trường sử dụng.
CREATE TABLE training.enrollments_by_student (
  tenant_id text,
  student_id text,
  course_id text,
  enrolled_at timestamp,
  status text,
  progress_percent int,
  PRIMARY KEY ((tenant_id, student_id), course_id)
);
~~~

Query:

~~~sql
SELECT course_id, enrolled_at, status, progress_percent
FROM training.enrollments_by_student
WHERE tenant_id = 'school-a'
  AND student_id = 'student-01';
~~~

Nếu cần “mọi học viên đang ACTIVE của một khóa”, bảng theo student không còn định vị được partition từ courseId. Một bảng khác có thể phục vụ chiều ngược:

~~~sql
CREATE TABLE training.enrollments_by_course (
  tenant_id text,
  course_id text,
  student_id text,
  enrolled_at timestamp,
  status text,
  progress_percent int,
  PRIMARY KEY ((tenant_id, course_id), student_id)
);
~~~

Nhưng hai bảng **enrollments_by_student** và **enrollments_by_course** là hai hình chiếu của cùng quan hệ. Phải có quy tắc nguồn chính, ghi/đồng bộ, retry, idempotency và đối soát, đặc biệt khi trạng thái enrollment đổi.

Ở hai bảng minh họa, clustering theo **course_id** hoặc **student_id**, không phải theo **enrolled_at**. Vì vậy chúng **không tự tối ưu** truy vấn “20 đăng ký mới nhất” theo ngày; muốn order thời gian phải thiết kế thêm clustering columns hoặc bảng theo truy vấn tương ứng. Đây là đặc điểm quan trọng của tư duy wide-column: **hình dạng primary key quyết định đường đọc**, không phải chỉ tên bảng.

Partition chứa rất nhiều quan hệ cũng có thể trở nên lớn/hot. Nếu một course có hàng triệu student, cần đánh giá bucket/shard, số partition phải truy vấn và cơ chế phân trang. **Đặt dữ liệu trong cùng partition không tự bảo đảm các hàng có transaction semantics giống một document MongoDB.**

## 14. Đối chiếu DynamoDB: một item, nhiều item và adjacency patterns

DynamoDB có thể lưu một item đại diện cho enrollment:

~~~text
PK                 = STUDENT#student-01
SK                 = COURSE#course-nosql
tenantId           = school-a
status             = ACTIVE
progressPercent    = 35
enrolledAt         = 2026-11-14T09:00:00Z
~~~

Mô hình này phù hợp để **Query** các khóa học của một học viên theo partition key. Nhưng muốn truy vấn ngược “học viên của một khóa”, hệ thống cần thiết kế **secondary index** hoặc item/bảng dẫn xuất phục vụ chiều ngược. Việc có cùng thuộc tính courseId trong value không tự cho phép Query theo courseId hiệu quả.

Ở DynamoDB, có các cơ chế **conditional write** và **transaction** cho item trong phạm vi được hỗ trợ; khi vật chất hóa hai chiều bằng nhiều item, cần quyết định cập nhật đồng bộ hay bất đồng bộ, giới hạn transaction và cách xử lý retry. Việc sao chép một quan hệ thành nhiều item **không làm các item tự cập nhật cùng nhau**.

Một thiết kế tốt phải nêu rõ:

- Item nào là **nguồn quan hệ**.
- Trường nào tham gia **partition key/sort key**.
- GSI/LSI hoặc read model nào cần cho chiều ngược.
- Bất biến nào phải bảo vệ bằng điều kiện ghi.
- Độ trễ cập nhật giữa nguồn và các index/bản sao được chấp nhận.

Các quyết định này khác với Neo4j traversal, dù cả hai đều biểu diễn các thực thể và mối quan hệ.

## 15. Tham chiếu, snapshot và cache là ba loại “lặp dữ liệu” khác nhau

Khi một document lưu thông tin về thực thể khác, hãy xác định **ngữ nghĩa của bản sao**.

### Tham chiếu tới thông tin hiện tại

Một enrollment lưu **courseId** và giao diện đọc **courses.title** tại thời điểm xem. Nếu tên khóa đổi, tên mới được hiển thị.

### Snapshot tại thời điểm giao dịch

Một chứng chỉ cần ghi **courseTitleAtIssue**:

~~~javascript
{
  _id: "certificate-91",
  tenantId: "school-a",
  studentId: "student-01",
  courseId: "course-nosql",
  courseTitleAtIssue: "NoSQL căn bản",
  issuedAt: ISODate("2026-11-14T13:00:00Z")
}
~~~

Nếu tên khóa sau đó đổi thành **NoSQL thực hành**, chứng chỉ đã cấp vẫn cần giữ tên cũ theo quy tắc nghiệp vụ lịch sử. Bản sao này **không phải cache cần làm mới**.

### Cache/read model cho đường đọc

Một enrollment có thể chứa **courseTitleCache** để giảm số phép join ở màn hình thường truy cập:

~~~javascript
{
  _id: "enrollment-101",
  courseId: "course-nosql",
  courseTitleCache: "NoSQL căn bản",
  courseTitleVersion: 3
}
~~~

Nếu đây là **cache tên hiện tại**, phải chốt độ trễ đồng bộ, version, invalidation, xử lý cập nhật trùng/lệch thứ tự và nguồn gốc để dựng lại. Không thể vừa tuyên bố “luôn hiện tên mới ngay lập tức” vừa chấp nhận cache bất đồng bộ mà không có cơ chế đáp ứng yêu cầu đó.

| Cách lưu | Khi nguồn đổi | Ý nghĩa |
|---|---|---|
| Reference | Lần đọc tiếp theo truy nguồn chính theo hợp đồng nhất quán | Muốn dữ liệu hiện tại |
| Snapshot lịch sử | **Không tự đổi** | Giữ sự thật tại thời điểm phát sinh |
| Cache/read model | Cập nhật theo quy tắc đồng bộ đã đặt | Tối ưu hiệu năng đọc |

Ba lựa chọn đều có thể dùng ID và một số trường trùng nhau, nhưng **cách quản lý hoàn toàn khác**.

## 16. Đọc và ghi cùng nhau chưa đủ: cần biết quyền sở hữu dữ liệu

Giả sử trang course luôn hiển thị giảng viên. Điều đó không đồng nghĩa phải nhúng toàn bộ instructor vào mọi course, bởi hồ sơ giảng viên:

- Có danh tính độc lập.
- Được nhiều khóa dùng chung.
- Có quy tắc phân quyền, cập nhật và có thể xóa khác khóa học.
- Có thể còn được tìm kiếm theo tên/chuyên môn.

Nếu nhúng toàn bộ instructor ở 500 khóa, một lần đổi tên/hồ sơ đòi cập nhật 500 bản sao. Nếu thiếu một bản, các trang sẽ không nhất quán. Reference giải quyết nguồn sở hữu; cache hoặc read model có thể tối ưu đường đọc nếu sau này đo được nhu cầu.

Một ví dụ đối lập: **địa chỉ giao hàng tại lúc chốt đơn** nên được snapshot trong order, dù customer có một địa chỉ mặc định dùng chung. Đổi địa chỉ mặc định sau khi mua không được âm thầm đổi địa điểm giao của đơn cũ.

**Ai sở hữu dữ liệu và dữ liệu mô tả “hiện tại” hay “lịch sử”** là câu hỏi quan trọng ngang với số lần truy vấn.

## 17. Bất biến nghiệp vụ quyết định ranh giới bảo vệ quan hệ

Một quan hệ có thể có những bất biến:

1. Không tồn tại hai enrollment hiện hành cho cùng **(tenantId, studentId, courseId)** theo quy định.
2. Chỉ học viên và khóa học thuộc cùng tenant mới được liên kết.
3. Không đăng ký khóa đang **CLOSED**.
4. **progressPercent** trong khoảng **0–100**.
5. Chỉ cho phép chuyển trạng thái theo state machine.

Các điều kiện cần những cơ chế khác nhau:

| Điều kiện | Cơ chế ứng viên |
|---|---|
| Không trùng bộ khóa | Unique index/constraint hoặc conditional create |
| Giá trị status/progress hợp lệ | Validation khi ghi và quy tắc trạng thái |
| Hai đầu cùng tenant | Kiểm tra đáng tin cậy và phối hợp với thao tác tạo/xóa thực thể |
| Không liên kết tới course đang đóng | Conditional workflow/transaction hay trạng thái lifecycle bảo vệ race |
| Không áp dụng lại cùng yêu cầu | Idempotency key/record và xử lý retry |

Ví dụ MongoDB:

~~~javascript
db.enrollments.updateOne(
  {
    tenantId: "school-a",
    studentId: "student-01",
    courseId: "course-nosql"
  },
  {
    $setOnInsert: {
      enrolledAt: ISODate("2026-11-14T09:00:00Z"),
      status: "ACTIVE",
      progressPercent: 0
    }
  },
  { upsert: true }
);
~~~

**$setOnInsert** không tự sửa enrollment đã tồn tại. Unique index trên bộ khóa vẫn là lớp bảo vệ quan trọng khi có hai request đồng thời. Nhưng lệnh này **giả định** các điều kiện về quyền, tenant và course status đã được kiểm soát bằng quy trình phù hợp. Một kiểm tra “course đang OPEN” trước lệnh upsert có thể bị race với tác vụ đóng khóa; nếu bất biến cứng yêu cầu không cho ghi trong trường hợp đó, cần phối hợp các thao tác bằng cơ chế nhất quán phù hợp.

**Không nên chỉ dựa vào mô hình graph/document để suy ra toàn vẹn quan hệ.** Việc có cạnh hoặc có ID chỉ thể hiện cách lưu, không tự quyết định ai được liên kết với ai.

## 18. Xóa thực thể và xử lý quan hệ mồ côi

Nếu một course bị xóa nhưng enrollment vẫn giữ **courseId**, quan hệ có thể bị **mồ côi (orphan)**. Việc xóa một node/record có liên kết phải theo chính sách:

| Chính sách | Ý nghĩa | Ví dụ phù hợp |
|---|---|---|
| **Restrict** | Không cho xóa khi còn quan hệ bắt buộc | Không xóa khóa còn học viên đang học |
| **Cascade** | Xóa/hủy quan hệ phụ thuộc | Xóa cache tham gia tạm không còn giá trị |
| **Soft delete / archive** | Đánh dấu thực thể đóng, giữ quan hệ cần cho lịch sử | Khóa đã kết thúc nhưng còn chứng chỉ |
| **Detach** | Bỏ cạnh/liên kết, giữ thực thể ở hai đầu | Bỏ tag khỏi bài viết |
| **Snapshot** | Giữ bản mô tả lịch sử độc lập | Chứng chỉ cần tên khóa tại ngày cấp |

Đối với khóa học có nhiều học viên, **xóa cascade tức thì tất cả enrollment** có thể phá hỏng tiến độ và chứng chỉ. Trước khi xóa cần trả lời: dữ liệu nào còn nghĩa vụ giữ, dữ liệu nào được xóa theo yêu cầu, và đường đọc lịch sử sẽ thay đổi thế nào?

Một quy trình xóa an toàn có thể là:

~~~mermaid
flowchart TD
    A["Yêu cầu xóa course"] --> B["Kiểm tra quyền và chính sách"]
    B --> C["Đánh dấu DELETING / chặn quan hệ mới"]
    C --> D["Dọn hoặc chuyển trạng thái edges/enrollments"]
    D --> E["Dọn read model, cache, search index"]
    E --> F["Đối soát số quan hệ và bản sao"]
    F --> G["Hoàn tất theo chính sách retention"]
~~~

Với quan hệ hàng triệu bản ghi, việc xử lý có thể cần batch và checkpoint, không nhất thiết một transaction khổng lồ. Nếu có yêu cầu xóa dữ liệu cá nhân, phải xem cả dữ liệu dẫn xuất, archive và backup theo phạm vi chính sách; chỉ xóa một document/node không chứng minh mọi bản sao đã được xử lý.

Graph database có cơ chế xóa node và quan hệ riêng, ví dụ Neo4j hỗ trợ **DETACH DELETE** để xóa node cùng các quan hệ gắn vào nó. Nhưng có thể thực thi lệnh **không** có nghĩa nó phù hợp với chính sách nghiệp vụ; hãy xác định dữ liệu lịch sử và trách nhiệm xóa trước khi dùng.

## 19. Phân quyền và tenant isolation xuyên qua quan hệ

Trong hệ đa tenant, các quan hệ thường cần giới hạn ở phạm vi tổ chức:

~~~text
Student:
  tenantId = school-a
  id = student-01

Course:
  tenantId = school-b
  id = course-secret

Enrollment:
  studentId = student-01
  courseId = course-secret
~~~

Nếu ứng dụng chỉ kiểm tra hai ID tồn tại, nó có thể vô tình liên kết dữ liệu giữa hai tenant. Một unique index trên **(tenantId, studentId, courseId)** bảo vệ tính duy nhất bộ khóa, **không chứng minh hai đầu đều thuộc tenant đó**.

Cần:

- Lấy danh tính và tenant của người thao tác từ ngữ cảnh xác thực đáng tin cậy.
- Kiểm tra thực thể đích có cùng tenant hoặc có chính sách chia sẻ liên tenant được phép.
- Khi đọc bằng join/traversal, áp dụng ràng buộc quyền ở **cả điểm bắt đầu và các node/bản ghi được đi tới**.
- Không cho phép truyền tùy ý ID của tenant khác để sửa hoặc tạo quan hệ.
- Cân nhắc tính nhạy cảm của metadata trên edge (ai theo dõi ai, ai tham gia nhóm nào).

Một cạnh có thể **tự tiết lộ thông tin nhạy cảm** dù node ở hai đầu đều công khai. Vì vậy, kiểm soát quyền truy cập không chỉ áp dụng cho thuộc tính node/document mà còn với **sự tồn tại của quan hệ**.

## 20. Hiệu năng: ít join chưa chắc rẻ hơn, graph chưa chắc luôn nhanh

Các lựa chọn nên được đánh giá qua **công việc hệ thống cần làm**:

| Chỉ số | Liên hệ với mô hình |
|---|---|
| Số truy vấn / request | N+1 khi đọc reference từng bản ghi; join/batch read có thể giảm |
| Bytes truyền về | Nhúng object lớn có thể làm response phình to |
| Kích thước document/partition | Mảng liên kết tăng vô hạn làm đọc/ghi khó |
| Số index entries | Tạo index cho hai chiều tăng dung lượng và chi phí ghi |
| Fan-out của graph traversal | Node có nhiều cạnh tạo số đường duyệt lớn |
| Tranh chấp ghi | Nhiều update dồn vào một document/key/node/edge |
| Độ trễ đồng bộ | Read model có thể chậm hơn nguồn chính |
| Chi phí xóa/đối soát | Quan hệ phân tán trong nhiều kho phức tạp hơn khi cleanup |
| p95/p99 latency | Đo trên tải thực, không chỉ dữ liệu mẫu |

### Tình huống A: trang chi tiết khóa học

Nếu settings nhỏ, nhúng giúp một lần đọc. Nhưng nếu nhúng hàng chục nghìn lesson vào cùng course, mỗi trang detail chỉ cần 5 trường lại có thể làm tăng chi phí đọc và kích thước dữ liệu dù dùng projection.

### Tình huống B: danh sách học viên một khóa

Một course có 100.000 enrollment, UI chỉ muốn 20 học viên/trang. Collection liên kết có index theo **courseId** và cursor sẽ hợp lý hơn một mảng **studentIds[]** khổng lồ trong document course.

### Tình huống C: gợi ý bạn qua ba bước

Một graph database có thể biểu diễn traversal tự nhiên. Nhưng nếu mỗi user có 10.000 follow edges, duyệt ba bước không giới hạn có thể mở rộng đến lượng ứng viên rất lớn. Cần điều kiện loại bỏ, giới hạn độ sâu, tránh node hub hoặc xây read model đề xuất trước khi trả UI.

### Tình huống D: một trường được nhiều nơi sao chép

Cache tên khóa trong 100.000 enrollment có thể giảm join khi đọc, nhưng việc đổi tên khóa thành công rồi đồng bộ 100.000 bản sao tốn công và dễ lỗi một phần. Cần đánh giá tần suất đổi tên, số lần đọc, độ mới cần thiết và chi phí cập nhật.

Đừng kết luận mô hình nào tốt hơn chỉ bằng số lần query. **Chi phí ghi, đồng bộ và vòng đời dữ liệu** cũng là một phần của tổng chi phí sở hữu.

## 21. Nhận diện ba loại “cạnh” trong thiết kế NoSQL

Từ **edge** đôi khi được dùng cho nhiều kỹ thuật liên quan nhưng không đồng nhất:

1. **Graph edge native:** mối quan hệ trong graph database, có hướng/loại/thuộc tính và được truy cập qua traversal API. Ví dụ Neo4j **(Student)-[:ENROLLED_IN]->(Course)**.
2. **Association document/item:** một record chứa **studentId, courseId, status, enrolledAt**, được truy vấn bằng index/primary key. Ví dụ MongoDB **enrollments** hoặc DynamoDB item.
3. **Adjacency list:** tại một ID lưu tập ID láng giềng, ví dụ Redis Set **student:X:courses**, Cassandra bảng theo **student_id**.

| Tiêu chí | Graph edge | Association document | Adjacency list |
|---|---|---|---|
| Có thuộc tính của quan hệ | Thường hỗ trợ | Có | Có thể cần record phụ |
| Đọc trực tiếp hai chiều | Tùy mô hình truy vấn và index | Cần index hai chiều | Có thể cần hai danh sách/bảng |
| Duyệt nhiều hop | Khả năng trọng tâm của graph engine | Thường phải tự join/lặp ở app hoặc pipeline | Thường nhiều vòng đọc ở ứng dụng |
| Ràng buộc duy nhất quan hệ | Cần constraint/thiết kế riêng | Unique index/conditional write | Cần quy tắc bảo vệ các key |
| Xử lý dữ liệu lặp | Ít phải lưu bản danh sách kề thủ công trong API graph | Có thể join/read model | Dễ lưu hai chiều, cần đồng bộ |
| Chi phí traversal hub | Vẫn phải quản lý fan-out | Join/filter có thể tốn | Nhiều ID/đường đọc |

Lựa chọn không phụ thuộc tên gọi. Cần quan sát **truy vấn cụ thể nào được hỗ trợ tốt, bất biến nào được database bảo vệ, và giá phải trả khi quan hệ tăng**.

## 22. Quy trình chọn mô hình theo từng bước

~~~mermaid
flowchart TD
    A["Xác định dữ liệu có quan hệ"] --> B{"Đối tượng con có danh tính/vòng đời độc lập?"}
    B -->|"Không"| C{"Nhỏ, có giới hạn, thường đọc/ghi cùng cha?"}
    C -->|"Có"| D["Ưu tiên cân nhắc nhúng"]
    C -->|"Không"| E["Tách thành record/collection riêng"]
    B -->|"Có"| F["Tham chiếu tới nguồn chính"]
    F --> G{"Quan hệ nhiều-nhiều hoặc có thuộc tính riêng?"}
    G -->|"Có"| H["Association record hoặc graph edge"]
    G -->|"Không"| I["ID reference hoặc mảng ID có giới hạn"]
    H --> J{"Truy vấn chính là duyệt nhiều hop?"}
    J -->|"Có"| K["Đánh giá graph model/engine"]
    J -->|"Không"| L["Đánh giá association + indexes/read models"]
    D --> M["Xem lại tăng trưởng, ghi đồng thời, xóa"]
    E --> M
    I --> M
    K --> M
    L --> M
    M --> N["Đo latency, fan-out, tính nhất quán"]
~~~

Quy trình trên cần được bổ sung những câu hỏi về nghiệp vụ:

**Bước 1 — Liệt kê access patterns.** Đọc từ A sang B hay từ B sang A? Lấy một ID, phân trang danh sách, lọc theo trạng thái hay duyệt nhiều bước?

**Bước 2 — Xác định source of truth.** Hồ sơ giảng viên do đâu quản lý? Trạng thái enrollment nằm ở đâu? Bản sao nào chỉ để cache?

**Bước 3 — Xác định cardinality.** Một node có tối đa bao nhiêu cạnh? Số liên kết có tăng vô hạn theo thời gian không? Có node hub không?

**Bước 4 — Xác định thuộc tính và vòng đời quan hệ.** Mối quan hệ có ngày bắt đầu, role, tiến độ, trọng số hay nhiều lần thay đổi trạng thái không?

**Bước 5 — Xác định bất biến và đồng thời.** Có cấm trùng cặp, cấm liên tenant, cấm quan hệ đến thực thể đã đóng? Database có cơ chế bảo vệ đúng phạm vi không?

**Bước 6 — Quyết định storage model.** Nhúng, reference, association, graph edge hoặc adjacency list; có thể phối hợp nhiều kỹ thuật.

**Bước 7 — Thiết kế đường đọc/ghi thực tế.** Khóa, index, traversal depth, pagination, CAS/transaction và retry.

**Bước 8 — Thiết kế cập nhật và xóa.** Snapshot hay cache? Khi đối tượng bị xóa thì restrict, cascade, soft delete hay detach?

**Bước 9 — Đo với dữ liệu đại diện.** Số quan hệ p95/p99, fan-out, độ trễ truy vấn, contention, thời gian đồng bộ read model và chi phí vận hành.

## 23. Các sai lầm thường gặp

| Nhầm lẫn | Hệ quả | Hướng đúng |
|---|---|---|
| “Một trang đọc cùng nhau thì nhúng tất cả” | Sao chép thực thể chia sẻ, mảng tăng vô hạn | Xét danh tính, vòng đời và giới hạn |
| “Có ID tham chiếu là tự có khóa ngoại” | Orphan reference và liên kết sai tenant | Kiểm tra khi ghi/xóa, đối soát |
| “Quan hệ nhiều-nhiều chỉ cần mảng ở hai bên” | Hai bản nguồn sự thật lệch khi ghi lỗi | Chọn association/source chính và index hai chiều |
| “Graph luôn tốt hơn document cho N:M” | Tăng chi phí hệ thống dù chỉ truy vấn một hop đơn giản | Chọn graph khi traversal thực sự quan trọng |
| “Lưu edge mà không cần thuộc tính quan hệ” | Mất ngày đăng ký, trạng thái, tiến độ | Xác định dữ liệu thuộc edge hay node |
| “MERGE/upsert thay thế mọi ràng buộc” | Concurrent updates, kiểm tra quyền và trạng thái vẫn có lỗ hổng | Unique/conditional write/transaction và auth |
| “Array ID nhỏ hôm nay sẽ nhỏ mãi” | Document/key trở thành hotspot khi scale | Ước lượng p95/p99 và tăng trưởng |
| “Lưu cả hai chiều luôn cải thiện hiệu năng” | Chi phí ghi, đồng bộ và sửa sai tăng | Chỉ tạo read model khi có lợi ích đo được |
| “Snapshot phải cập nhật khi source đổi” | Chứng chỉ/hóa đơn mất lịch sử | Phân biệt lịch sử với cache |
| “Xóa node là xong” | Quan hệ, cache, archive còn dữ liệu | Quy trình xóa theo phạm vi và chính sách |
| “LIMIT 20 thì traversal rẻ” | Có thể đã duyệt tập ứng viên rất lớn | Giới hạn fan-out/độ sâu và đo công việc thực |
| “Một index giải quyết mọi chiều truy vấn” | Truy vấn ngược có thể quét lớn | Thiết kế index/partition theo từng access pattern |

## 24. Bài tập thực hành

### Bài tập 1 — Chọn nhúng hay tham chiếu

Một hệ bán hàng có **product**, **productDescription**, **manufacturer** và **reviews**. Mô tả ngắn được đọc cùng sản phẩm, manufacturer có nhiều sản phẩm và được sửa hồ sơ riêng, reviews có thể tăng lên hàng triệu. Hãy phân loại dữ liệu nào phù hợp embedding, dữ liệu nào reference/collection riêng. Nêu ranh giới tăng trưởng và đường phân trang.

### Bài tập 2 — Quan hệ nhiều-nhiều có thuộc tính

Một người dùng tham gia nhiều nhóm, một nhóm có nhiều người. Quan hệ chứa **joinedAt**, **role**, **status**. Đề xuất collection **memberships**, unique index, hai index đọc theo user/group và quy tắc khi một thành viên rời nhóm rồi tham gia lại.

### Bài tập 3 — Đọc ngược

MongoDB đang lưu **courseIds[]** trong student, nhưng trang quản trị mới cần 50 học viên ACTIVE mới nhất của một khóa. Hãy giải thích giới hạn của mô hình cũ, đề xuất association collection và index/sort/cursor phù hợp.

### Bài tập 4 — Graph traversal

Một sản phẩm mạng xã hội thường xuyên hỏi “người bạn của bạn trong tối đa ba bước”, nhưng không thường cần list toàn bộ profile theo ID. So sánh lưu cạnh native trong graph database với lưu Set adjacency trong Redis. Cần đo những gì ở các user có hàng chục nghìn mối quan hệ?

### Bài tập 5 — Tên hiện tại và snapshot lịch sử

Giảng viên đổi tên hiển thị, khóa học đổi tiêu đề, nhưng chứng chỉ đã cấp phải giữ tiêu đề lúc cấp. Hãy xác định nguồn chính, tham chiếu và snapshot. Nếu cache tên hiện tại trong enrollment, cần quy tắc đồng bộ nào?

### Bài tập 6 — Quan hệ mồ côi

Khóa học có 50.000 học viên, hệ thống muốn xóa khóa. Hãy so sánh **restrict**, **cascade**, **soft delete** và **snapshot**. Nêu cách chặn enrollment mới trong lúc dọn và cách phát hiện dữ liệu còn trỏ vào course không tồn tại.

### Bài tập 7 — Thêm liên kết khi đồng thời

Hai request cùng đăng ký một học viên vào một khóa. Vì sao **findOne rồi insertOne** không đủ? Viết unique index MongoDB phù hợp và mô tả cách xử lý duplicate key. Nêu lý do còn phải kiểm tra tenant và trạng thái khóa.

### Bài tập 8 — Hai chiều trong key–value

Một hệ dùng Redis Set **student:X:courses** và **course:Y:students**. Đăng ký thành công ở Set thứ nhất nhưng ghi Set thứ hai thất bại. Đề xuất source of truth, retry/idempotency và job đối soát. Nếu dùng Redis Cluster, bạn cần kiểm tra điều kiện gì trước khi muốn thao tác nguyên tử nhiều key?

### Bài tập 9 — Wide-column

Thiết kế Cassandra access table cho “danh sách khóa của một học viên” và “danh sách học viên của một khóa” với yêu cầu phân trang theo thời điểm đăng ký. Chọn partition/clustering columns cho mỗi chiều, giải thích rủi ro partition quá rộng và dữ liệu lặp giữa hai bảng.

### Bài tập 10 — Ra quyết định có số liệu

Một đội đề xuất chuyển toàn bộ quan hệ N:M sang graph database. Hãy lập danh sách thông tin phải đo: số hop thường truy vấn, phân bố degree, p95/p99 fan-out, số lần cập nhật quan hệ, constraint, chi phí vận hành, độ trễ đọc và yêu cầu xóa. Từ đó chỉ ra trường hợp nào association collection vẫn là phương án đủ tốt.

## 25. Kết luận và cách vận dụng

Để chọn **nhúng, tham chiếu hoặc lưu cạnh quan hệ**, không bắt đầu bằng câu hỏi “database nào hiện đại nhất?” mà bắt đầu từ **dữ liệu thuộc ai, được đọc/ghi ra sao và quan hệ có ý nghĩa nghiệp vụ gì**:

- **Nhúng** phần dữ liệu nhỏ, có giới hạn, cùng vòng đời và thường đọc/ghi cùng thực thể cha.
- **Tham chiếu** thực thể có danh tính độc lập, được nhiều nơi sử dụng và có nguồn cập nhật chính rõ ràng.
- **Lưu association/edge** khi quan hệ nhiều-nhiều, có trạng thái/thuộc tính riêng, cần truy vấn hai chiều hoặc duyệt liên kết.
- **Cân nhắc graph native** nếu traversal nhiều bước là chức năng trung tâm, thay vì mặc định chọn graph cho mọi N:M.
- **Phi chuẩn hóa có kiểm soát** khi access pattern quan trọng cần read model, đồng thời nêu rõ source of truth, độ mới, retry và đối soát.

Mỗi phương án cần được thử bằng cùng một chuỗi suy luận: **yêu cầu nghiệp vụ → cardinality và vòng đời → đường đọc/ghi → ranh giới nhất quán → index/khóa/traversal → cập nhật và xóa → số liệu kiểm chứng**. Nhờ vậy, mối quan hệ trong mô hình NoSQL được biểu diễn đúng với thao tác thực tế, không chỉ đúng về mặt sơ đồ.
