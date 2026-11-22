# Lặp dữ liệu có chủ đích để giảm trao đổi mạng

## 1. Bối cảnh: vì sao một bản ghi không phải lúc nào cũng được lưu ở một nơi?

Trong một ứng dụng học trực tuyến, màn hình **“Khóa học của tôi”** cần hiển thị tên khóa, ảnh đại diện, tên giảng viên, tiến độ và thời điểm truy cập gần nhất. Giả sử một người học đã đăng ký 20 khóa. Nếu dữ liệu được tách thành những tập riêng:

~~~text
Course         -> tên khóa, hình ảnh, mô tả
Instructor     -> tên, ảnh giảng viên
Enrollment     -> người học tham gia khóa nào
Progress       -> hoàn thành được bao nhiêu bài
~~~

thì API có thể phải đọc Enrollment, tìm 20 Course, đọc các Instructor và lấy Progress cho từng Enrollment. Nếu không có batch hoặc phép ghép phù hợp, một lần hiển thị có thể phát sinh rất nhiều request tới cơ sở dữ liệu.

Một lựa chọn khác là duy trì **bản chiếu phục vụ đúng màn hình**:

~~~json
{
  "learnerId": "L001",
  "courseId": "C101",
  "courseTitle": "NoSQL căn bản",
  "courseThumbnail": "/assets/c101.webp",
  "instructorName": "Nguyễn Minh",
  "progressPercent": 65,
  "lastAccessedAt": "2026-11-14T08:40:00Z"
}
~~~

Tên khóa và tên giảng viên trong bản chiếu này là **bản sao có chủ đích** từ những thực thể khác. Đổi lại, API có thể trả danh sách bằng một truy vấn theo learnerId mà không phải liên tục gọi các tập dữ liệu còn lại.

**Lặp dữ liệu có chủ đích (intentional data duplication hoặc denormalization)** là việc lưu một phần thông tin ở nhiều vị trí, theo một hợp đồng rõ ràng, nhằm phục vụ những đường truy vấn cụ thể. Đây là kỹ thuật quan trọng trong thiết kế NoSQL **theo truy vấn** (query-driven design).

Điểm cốt lõi của bài học:

> Chấp nhận thêm chi phí ở đường ghi và đồng bộ để giảm số lần đọc, lượt trao đổi mạng, phép ghép phân tán và thời gian chờ ở đường đọc.

Nhưng việc sao chép tùy tiện không tạo ra hệ thống tốt. Một thiết kế có chủ đích phải xác định **nguồn dữ liệu có thẩm quyền**, bản sao nào được phép trễ, quy tắc cập nhật và cách sửa sai khi các bản sao lệch nhau.

## 2. “Giảm trao đổi mạng” nghĩa là giảm những chi phí nào?

### 2.1. Round-trip giữa ứng dụng và kho dữ liệu

Một **network round-trip** là chu kỳ gửi yêu cầu rồi chờ phản hồi. Với một dịch vụ dữ liệu từ xa, mỗi lần gọi có thể tốn chi phí truyền mạng, TLS, hàng đợi, lập lịch, xử lý và chờ kết quả.

Giả sử một trang cần thông tin 20 khóa học:

~~~text
Đọc danh sách Enrollment:         1 request
Đọc 20 Course riêng lẻ:          20 request
Đọc 20 Progress riêng lẻ:        20 request
Tổng cộng:                       41 request
~~~

Nếu 41 thao tác diễn ra **tuần tự**, mỗi thao tác mất trung bình 5 ms, phần thời gian chờ có thể xấp xỉ:

\[
41 \times 5\text{ ms} = 205\text{ ms}.
\]

Đây là phép tính minh họa; thời gian thực tế thay đổi do cache, kích thước kết quả, độ trễ đuôi (tail latency), tải của node và độ đồng thời. Nếu thay bằng một truy vấn lấy bản chiếu đã chuẩn bị theo learnerId, số round-trip tại ứng dụng có thể giảm đáng kể.

### 2.2. N+1 query

**N+1 query** là hiện tượng lấy một tập N bản ghi rồi thực hiện thêm một truy vấn cho mỗi bản ghi.

~~~javascript
const enrollments = await getEnrollments(learnerId);

for (const enrollment of enrollments) {
  const course = await getCourse(enrollment.courseId);
  // Một lượt gọi riêng cho mỗi enrollment.
}
~~~

Nếu có 100 enrollment, đoạn mã có thể phát sinh 101 lần đọc. Song song hóa các lời gọi làm giảm tổng thời gian chờ trong một số trường hợp, nhưng **không tự giảm số request**; còn có thể tạo nhiều truy vấn đồng thời trên cùng dịch vụ.

Trước khi lặp dữ liệu, cũng cần cân nhắc **batch fetch** hoặc gộp ID:

~~~javascript
const courseIds = [...new Set(enrollments.map(e => e.courseId))];
const courses = await getCoursesByIds(courseIds);
~~~

Batch là một lựa chọn tốt khi dữ liệu vẫn có thể được đọc theo tập khóa phù hợp và chi phí đồng bộ bản sao không đáng đánh đổi.

### 2.3. Giao tiếp chéo partition

Trong hệ NoSQL phân tán, dữ liệu thường được phân vùng theo khóa. Nếu màn hình cần những bản ghi ở nhiều partition, ứng dụng hoặc dịch vụ dữ liệu có thể phải truy cập nhiều node và ghép kết quả.

~~~text
Partition LEARNER#L001  -> enrollment
Partition COURSE#C101   -> course metadata
Partition COURSE#C102   -> course metadata
Partition COURSE#C103   -> course metadata
Partition INSTRUCTOR#I5 -> instructor metadata
~~~

Nếu read model chứa đủ thông tin cần hiển thị theo khóa LEARNER#L001, đường đọc có thể tập trung hơn. Dù vậy, một truy vấn vào một partition **không mặc nhiên là một gói mạng hoặc một lần đọc vật lý**: paging, replication, giới hạn item và cách triển khai vẫn ảnh hưởng chi phí.

### 2.4. Giảm request không đồng nghĩa giảm tất cả chi phí

Lặp title, thumbnail, tên giảng viên vào nhiều bản ghi có thể làm:

- Tăng dung lượng lưu trữ.
- Tăng bytes truyền khi đọc một hàng.
- Tăng số cập nhật khi những trường đó thay đổi.
- Tăng số bản sao cần xóa khi có yêu cầu bảo mật.

Vì vậy, cần đo **số round-trip, bytes, số partition chạm tới, p95/p99 latency, thông lượng, chi phí lưu/ghi** trước khi kết luận giải pháp nào tốt hơn.

## 3. Chuẩn hóa và phi chuẩn hóa: đánh đổi có chủ đích

### 3.1. Mô hình chuẩn hóa

Một mô hình tách thực thể:

~~~text
Course
  courseId = C101
  title = "NoSQL căn bản"
  instructorId = I5

Instructor
  instructorId = I5
  displayName = "Nguyễn Minh"

Enrollment
  learnerId = L001
  courseId = C101
  progress = 0.65
~~~

Ưu điểm là **mỗi thông tin thường có một nguồn quản lý**. Đổi title chỉ cần cập nhật Course, không phải cập nhật mọi Enrollment. Trong hệ SQL với chỉ mục và JOIN phù hợp, kiểu dữ liệu này có thể được đọc hiệu quả; không nên mặc định JOIN luôn chậm.

Trong nhiều hệ NoSQL, phép ghép linh hoạt không được hỗ trợ như SQL hoặc có chi phí đáng kể do phân vùng. Khi ứng dụng phải tự ghép qua nhiều node/dịch vụ, số round-trip có thể trở thành nút thắt.

### 3.2. Mô hình phi chuẩn hóa

~~~text
LearnerCourseView
  learnerId = L001
  courseId = C101
  courseTitle = "NoSQL căn bản"    <- sao từ Course
  instructorName = "Nguyễn Minh"  <- sao từ Instructor
  progress = 0.65                 <- từ Enrollment/Progress
~~~

Ưu điểm: Màn hình “Khóa học của tôi” được trả từ dữ liệu đã có sẵn các trường cần thiết.

Chi phí: Khi Course.title đổi, tất cả bản chiếu chứa title có thể bị cũ cho đến khi được cập nhật. Nếu Course có hàng trăm nghìn người học, một thay đổi nhỏ có thể gây nhiều thao tác ghi.

### 3.3. Ba loại lặp dữ liệu

| Loại | Ví dụ | Mục đích |
|---|---|---|
| **Sao chép trường** | courseTitle trong EnrollmentView | Tránh phải đọc Course khi hiển thị danh sách |
| **Sao chép bản ghi theo đường truy cập** | order_by_customer và order_by_store | Đọc cùng đơn hàng qua hai khóa truy vấn khác nhau |
| **Dữ liệu tổng hợp dẫn xuất** | completedLessonCount, averageRating | Tránh quét/tính toán lại nhiều bản ghi |

Ba loại này có rủi ro cập nhật khác nhau. Tên khóa có thể được gán lại idempotent theo version; bộ đếm cộng dồn cần chống đếm trùng sự kiện; read model theo nhiều khóa cần cơ chế đồng bộ và đối soát.

## 4. Bắt đầu từ mẫu truy vấn, không bắt đầu từ việc sao chép

### 4.1. Lập ma trận truy vấn

Ví dụ cho nền tảng học tập:

| Mã | Truy vấn | Khóa đầu vào | Thứ tự/kết quả |
|---|---|---|---|
| Q1 | Khóa học của tôi | learnerId | 20 khóa gần truy cập nhất |
| Q2 | Chi tiết một khóa | courseId | Một khóa và nội dung |
| Q3 | Danh sách người đang học khóa | courseId | Phân trang theo ngày tham gia |
| Q4 | Tiến độ một người trong khóa | learnerId + courseId | Một trạng thái |
| Q5 | Báo cáo hoạt động mỗi ngày | tenantId + day | Tổng hợp |

Một mô hình tối ưu Q2 có thể không tối ưu Q1 hoặc Q3. Có thể cần:

- Course làm nguồn metadata theo courseId.
- LearnerCourseView phục vụ Q1.
- CourseLearnerView phục vụ Q3.
- Progress có thẩm quyền phục vụ Q4.
- DailySummary phục vụ Q5.

Đây là **thiết kế theo câu hỏi nghiệp vụ**. Không nên tạo thêm bảng chỉ vì “sau này có thể cần”, bởi mỗi bảng sinh thêm việc ghi, giám sát, bảo mật và khôi phục.

### 4.2. Phân loại trường theo độ mới

| Trường | Tần suất thay đổi | Cách sử dụng đề xuất |
|---|---|---|
| Tên khóa học | Thấp | Có thể lặp ở view, chấp nhận độ trễ ngắn |
| Ảnh khóa | Thấp | Có thể lặp URL, dùng cache phù hợp |
| Tên giảng viên | Thấp–trung bình | Có thể lặp nếu giảm lookup đáng kể |
| Tiến độ học | Thường xuyên | Có thể làm projection, nhưng cần trải nghiệm cập nhật gần ngay |
| Quyền truy cập đã bị thu hồi | Nhạy cảm | Xác minh ở nguồn/cơ chế phân quyền đáng tin cậy |
| Giá cuối cùng khi thanh toán | Nhạy cảm | Kiểm tra tại điểm chốt giao dịch |
| Tồn kho khả dụng | Đồng thời cao | Cần thao tác giữ/trừ có điều kiện ở nguồn |

**Bản sao được phép phục vụ hiển thị không đồng nghĩa bản sao được quyền ra quyết định nghiệp vụ.**

### 4.3. Một chủ sở hữu cho mỗi trường

Hãy định nghĩa rõ:

~~~text
Course service:
  Sở hữu Course.title và Course.thumbnail.

Instructor service:
  Sở hữu Instructor.displayName.

Progress service:
  Sở hữu Progress.completedLessons và Progress.version.

LearnerCourseView:
  Chỉ lưu bản chiếu để đọc.
  Không được sửa title hoặc progress từ API ghi độc lập.
~~~

Nếu hai hệ tự cập nhật courseTitle theo hai nguồn, sự kiện đồng bộ có thể ghi đè lẫn nhau. **Single source of truth theo trường** là nền tảng của phi chuẩn hóa an toàn.

## 5. Ví dụ xuyên suốt: màn hình “Khóa học của tôi”

### 5.1. Response mong muốn

~~~json
{
  "learnerId": "L001",
  "courses": [
    {
      "courseId": "C101",
      "title": "NoSQL căn bản",
      "instructorName": "Nguyễn Minh",
      "thumbnail": "/c101.webp",
      "progressPercent": 65,
      "lastAccessedAt": "2026-11-14T08:40:00Z"
    }
  ]
}
~~~

Nếu hệ thống chỉ có Course, Instructor, Enrollment và Progress riêng biệt, một API có thể phải tìm mỗi tập để tạo một response.

~~~mermaid
sequenceDiagram
    participant UI as Client
    participant API as Learning API
    participant E as Enrollment store
    participant C as Course store
    participant P as Progress store
    UI->>API: GET /me/courses
    API->>E: Tìm Enrollment của L001
    E-->>API: Danh sách courseId
    API->>C: Lấy metadata các Course
    C-->>API: Tên, ảnh, giảng viên
    API->>P: Lấy tiến độ của các Course
    P-->>API: Tiến độ
    API-->>UI: Ghép và trả danh sách
~~~

Nếu từng thao tác được batch tốt, sơ đồ này có thể hoạt động ổn định. Nhưng khi dữ liệu ở nhiều dịch vụ hoặc lời gọi tăng nhanh theo số khóa, có thể cần mô hình đọc riêng.

### 5.2. Read model được lặp có chọn lọc

~~~json
{
  "tenantId": "T1",
  "learnerId": "L001",
  "courseId": "C101",
  "courseTitle": "NoSQL căn bản",
  "thumbnail": "/c101.webp",
  "instructorId": "I5",
  "instructorName": "Nguyễn Minh",
  "progressPercent": 65,
  "lastAccessedAt": "2026-11-14T08:40:00Z",
  "enrollmentStatus": "ACTIVE",
  "courseVersion": 12,
  "instructorVersion": 8,
  "progressVersion": 47
}
~~~

API có thể truy vấn theo learnerId và sắp xếp theo lastAccessedAt, nếu read model có khóa/chỉ mục phù hợp.

**Lưu ý:** Việc lặp dữ liệu không tự khiến thứ tự truy vấn hiệu quả. Nếu sort key là COURSE#C101, nó không sắp theo lastAccessedAt. Cần thiết kế thêm chỉ mục hoặc cấu trúc phục vụ “gần nhất trước”.

### 5.3. Trường nào được cập nhật từ đâu?

| Field trong view | Chủ sở hữu | Khi thay đổi |
|---|---|---|
| courseTitle | Course | Event COURSE_RENAMED hoặc projection từ nguồn |
| thumbnail | Course | Event COURSE_UPDATED |
| instructorName | Instructor | Event INSTRUCTOR_PROFILE_CHANGED |
| progressPercent | Progress | Event LEARNING_PROGRESS_CHANGED |
| enrollmentStatus | Enrollment | Event ENROLLMENT_STATUS_CHANGED |

Mô hình trên thường là **read model chỉ đọc**, được duy trì bởi projection worker. Việc sửa một tên khóa phải đi qua Course service, không được sửa trực tiếp một bản sao trong LearnerCourseView.

### 5.4. Khi nào cần đọc lại nguồn?

Nếu người học bấm “Vào học”, hệ thống cần xác minh quyền truy cập hiện hành theo cơ chế có thẩm quyền. Một bản chiếu chưa kịp nhận sự kiện thu hồi quyền không được cấp quyền chỉ vì enrollmentStatus còn ACTIVE.

Tương tự, ở thương mại điện tử, việc hiển thị giá từ read model có thể là tham khảo; bước tạo đơn phải chốt giá và giữ tồn kho qua dịch vụ chịu trách nhiệm nghiệp vụ.

## 6. Mẫu nhúng dữ liệu trong document

### 6.1. Embedding giúp gom dữ liệu thường đọc cùng nhau

Một document Course có thể chứa các chương:

~~~json
{
  "_id": "C101",
  "title": "NoSQL căn bản",
  "chapters": [
    {
      "chapterId": "CH01",
      "title": "Giới thiệu",
      "lessonCount": 6
    },
    {
      "chapterId": "CH02",
      "title": "Mô hình tài liệu",
      "lessonCount": 8
    }
  ]
}
~~~

Nếu danh sách chương thường được lấy cùng Course, embedding giảm lượt lookup. Những dữ liệu được đọc/cập nhật cùng nhau và có kích thước giới hạn thường là ứng viên tốt.

### 6.2. Không nhúng tập con tăng không giới hạn

Một thiết kế thiếu cân nhắc:

~~~json
{
  "_id": "C101",
  "title": "NoSQL căn bản",
  "enrollments": [
    {"learnerId": "L001", "progressPercent": 65},
    {"learnerId": "L002", "progressPercent": 40}
  ]
}
~~~

Nếu có 500.000 người học, mảng enrollments tăng không giới hạn, khiến:

- Document có thể chạm giới hạn kích thước (ví dụ MongoDB có giới hạn BSON document).
- Nhiều người cập nhật tiến độ đồng thời vào cùng document.
- Những lần đọc metadata khóa vô tình tải nhiều enrollment không cần thiết.
- Thao tác xóa, phân trang và cập nhật từng phần ngày càng phức tạp.

Mẫu hợp lý hơn thường là **Course metadata có các tập con giới hạn**, còn Enrollment lưu riêng. Một read model lặp **một vài trường cần hiển thị** ở vị trí phục vụ danh sách, thay vì nhúng toàn bộ lịch sử người học.

### 6.3. Khi nào nên tham chiếu thay vì nhúng?

| Tình huống | Cân nhắc |
|---|---|
| Dữ liệu con luôn được đọc cùng cha, số lượng nhỏ | Nhúng có thể phù hợp |
| Dữ liệu con tăng không giới hạn | Tham chiếu và phân trang |
| Một thực thể được nhiều nơi dùng chung | Tham chiếu, chỉ lặp trường cần thiết |
| Dữ liệu đổi rất thường xuyên | Hạn chế lặp hàng loạt; cân nhắc mô hình cập nhật riêng |
| Cần cập nhật nguyên tử trong một document | Nhúng những phần có giới hạn nếu phù hợp ranh giới transaction |
| Cần truy vấn theo nhiều khóa khác nhau | Có thể thêm read model/index chuyên biệt |

Không có công thức “luôn nhúng” hoặc “luôn tham chiếu”. Cần bắt đầu từ mẫu đọc/ghi và phạm vi nguyên tử của hệ quản trị được chọn.

## 7. Ví dụ MongoDB: bản chiếu danh sách khóa học

### 7.1. Lưu dữ liệu

~~~javascript
// Nguồn Course.
db.courses.insertOne({
  _id: "C101",
  title: "NoSQL căn bản",
  instructorId: "I5",
  version: 12
});

// Bản chiếu đọc theo người học.
db.learnerCourseViews.insertOne({
  _id: "T1#L001#C101",
  tenantId: "T1",
  learnerId: "L001",
  courseId: "C101",
  courseTitle: "NoSQL căn bản",
  instructorName: "Nguyễn Minh",
  progressPercent: 65,
  lastAccessedAt: new Date("2026-11-14T08:40:00Z"),
  courseVersion: 12
});
~~~

### 7.2. Đọc đúng đường truy vấn

~~~javascript
db.learnerCourseViews
  .find(
    { tenantId: "T1", learnerId: "L001" },
    {
      courseId: 1,
      courseTitle: 1,
      instructorName: 1,
      progressPercent: 1,
      lastAccessedAt: 1
    }
  )
  .sort({ lastAccessedAt: -1, _id: 1 })
  .limit(20);
~~~

Chỉ mục hỗ trợ ví dụ:

~~~javascript
db.learnerCourseViews.createIndex({
  tenantId: 1,
  learnerId: 1,
  lastAccessedAt: -1,
  _id: 1
});
~~~

Lặp dữ liệu giúp tránh lookup sang Course/Instructor, nhưng **không thay thế việc thiết kế chỉ mục, phân trang và kiểm soát tenant**.

### 7.3. Khi khóa học đổi tên

Giả sử Course C101 đổi tên và version tăng lên 13. Projection worker có thể cập nhật các bản chiếu cũ:

~~~javascript
db.learnerCourseViews.updateMany(
  {
    tenantId: "T1",
    courseId: "C101",
    courseVersion: { $lt: 13 }
  },
  {
    $set: {
      courseTitle: "NoSQL nền tảng",
      courseVersion: 13
    }
  }
);
~~~

Đây là minh họa, chưa phải pipeline hoàn chỉnh. Trong thực tế cần xử lý:

- Bản chiếu thiếu courseVersion hoặc vừa được tạo.
- Event đến sai thứ tự.
- Nhiều thuộc tính có các nguồn version khác nhau.
- updateMany ảnh hưởng một lượng lớn document.
- Worker chết giữa chừng hoặc một phần bản sao chưa cập nhật.
- Khả năng truy vấn các document theo courseId để sửa nhanh.

**Quan trọng:** Một lệnh cập nhật nhiều document không tự tạo bảo đảm giao dịch nhiều document theo mọi cấu hình. Nếu đòi hỏi tất cả bản sao đổi tên **đồng thời ngay lập tức**, việc lặp dữ liệu không đồng bộ có thể không phù hợp với yêu cầu.

## 8. Ví dụ DynamoDB: bản ghi theo nhiều khóa truy cập

### 8.1. Cùng thông tin xuất hiện ở hai loại item

Một bảng DynamoDB có thể được thiết kế:

~~~text
PK               SK                  Các trường
----------------------------------------------------------------
COURSE#C101      META                title, instructorId, version
LEARNER#L001     COURSE#C101         title, progress, status
LEARNER#L001     COURSE#C102         title, progress, status
COURSE#C101      LEARNER#L001        learnerName, joinedAt, status
COURSE#C101      LEARNER#L002        learnerName, joinedAt, status
~~~

Hai hướng đọc:

1. Theo LEARNER#L001 để lấy danh sách khóa học của L001.
2. Theo COURSE#C101 để lấy danh sách người học của C101.

Đây là **lặp dữ liệu theo đường truy cập**. Hai item đại diện cùng một Enrollment nhưng có khóa chính khác nhau, và dữ liệu không tự đồng bộ nếu ứng dụng ghi một item rồi quên item còn lại.

### 8.2. Truy vấn theo partition key

Ví dụ AWS SDK for JavaScript v3 với Document Client:

~~~javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  QueryCommand
} from "@aws-sdk/lib-dynamodb";

const client = DynamoDBDocumentClient.from(
  new DynamoDBClient({ region: "ap-southeast-1" })
);

const result = await client.send(new QueryCommand({
  TableName: "LearningData",
  KeyConditionExpression: "PK = :pk AND begins_with(SK, :prefix)",
  ExpressionAttributeValues: {
    ":pk": "LEARNER#L001",
    ":prefix": "COURSE#"
  },
  Limit: 20
}));
~~~

Truy vấn này dùng đúng partition key và tiền tố sort key. Nhưng thứ tự item được quy định theo sort key, **không phải mặc nhiên theo lastAccessedAt**. Nếu cần “20 khóa gần học nhất”, cần một mô hình khóa hoặc chỉ mục phù hợp với trường thời gian.

### 8.3. Khi hai item cần cùng thành công

DynamoDB hỗ trợ transaction nhiều item trong những phạm vi và giới hạn API quy định. Nếu trạng thái của một Enrollment cần được ghi ở hai item một cách nguyên tử, có thể cân nhắc TransactWriteItems.

Tuy nhiên:

- Transaction có giới hạn số lượng và kích thước.
- Không tự bao trùm một Redis cache, search cluster hay dịch vụ ngoài.
- Không có nghĩa tất cả Region đều nhìn thấy cập nhật tức thì với mọi chế độ global tables.
- Một thao tác đổi tên khóa ảnh hưởng hàng trăm nghìn bản sao không phù hợp để giả định gói trong một transaction duy nhất.

Thường cần phân biệt **các bất biến nghiệp vụ phải đúng tức thời** với **bản chiếu mô tả được phép cập nhật bất đồng bộ**.

## 9. Ví dụ Cassandra/ScyllaDB: hai bảng cho hai câu hỏi

### 9.1. Truy vấn theo khách hàng và theo cửa hàng

Trong một hệ bán hàng, khách cần xem 20 đơn gần đây, cửa hàng cần xem 20 đơn mới. Một mô hình CQL minh họa:

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id text,
    order_month text,
    ordered_at timestamp,
    order_id text,
    store_id text,
    total_minor bigint,
    status text,
    PRIMARY KEY (
        (customer_id, order_month),
        ordered_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    ordered_at DESC,
    order_id ASC
);

CREATE TABLE orders_by_store_day (
    store_id text,
    order_day date,
    ordered_at timestamp,
    order_id text,
    customer_id text,
    total_minor bigint,
    status text,
    PRIMARY KEY (
        (store_id, order_day),
        ordered_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    ordered_at DESC,
    order_id ASC
);
~~~

Một đơn xuất hiện ở hai bảng với các trường cần đọc:

~~~sql
INSERT INTO orders_by_customer_month (
    customer_id, order_month, ordered_at, order_id,
    store_id, total_minor, status
) VALUES (
    'C17', '2026-11', '2026-11-14T09:00:00Z',
    'O1001', 'S5', 1590000, 'PAID'
);

INSERT INTO orders_by_store_day (
    store_id, order_day, ordered_at, order_id,
    customer_id, total_minor, status
) VALUES (
    'S5', '2026-11-14', '2026-11-14T09:00:00Z',
    'O1001', 'C17', 1590000, 'PAID'
);
~~~

Hai truy vấn:

~~~sql
SELECT order_id, total_minor, status
FROM orders_by_customer_month
WHERE customer_id = 'C17'
  AND order_month = '2026-11'
LIMIT 20;

SELECT order_id, customer_id, total_minor, status
FROM orders_by_store_day
WHERE store_id = 'S5'
  AND order_day = '2026-11-14'
LIMIT 20;
~~~

Mỗi đường đọc tận dụng partition key riêng. Cùng dữ liệu được nhân sang bảng khác để tránh truy vấn khó hoặc quét rộng trên một bảng chung.

### 9.2. Chi phí khi cập nhật trạng thái

Khi O1001 chuyển từ PAID sang SHIPPED, cả hai bảng đọc cần cập nhật trường status nếu muốn hiển thị trạng thái mới. Hai câu ghi độc lập **không mặc định là một transaction toàn vẹn qua nhiều bảng/partition**. Cần một nguồn Order có thẩm quyền, pipeline projection hoặc quy trình ghi/repair được thiết kế rõ.

### 9.3. Không tạo phân vùng vô hạn

Nếu chỉ dùng customerId làm partition, lịch sử nhiều năm có thể tạo partition quá lớn. Thêm order_month hạn chế tăng trưởng mỗi phân vùng, nhưng xem lịch sử nhiều tháng cần đọc nhiều partition.

Tương tự, cửa hàng có lưu lượng cực cao có thể gây hot partition dù đã chia theo ngày; có thể phải bucket theo giờ hoặc dùng shard phụ. Đó là đánh đổi giữa **phân phối ghi và số partition cần đọc**.

## 10. Read amplification và write amplification

### 10.1. Đổi số lần đọc lấy số lần ghi

~~~text
Không lặp:
  Mở "Khóa học của tôi":
    Lấy 20 Enrollment + tìm Course/Instructor/Progress
  Đổi Course.title:
    Sửa một bản ghi Course

Có lặp:
  Mở "Khóa học của tôi":
    Đọc LearnerCourseView trực tiếp
  Đổi Course.title:
    Sửa Course + cập nhật nhiều read model
~~~

**Read amplification** ở mức ứng dụng: số lượt truy cập hoặc lượng dữ liệu đọc vượt mức cần thiết để trả một câu hỏi.

**Write amplification** ở mức ứng dụng: một thay đổi nguồn đòi hỏi nhiều thao tác ghi vào các bản sao. Đây là khái niệm bổ sung bên cạnh write amplification nội bộ của các storage engine.

### 10.2. Mô hình định lượng đơn giản

Giả sử:

- R: số lần đọc một màn hình.
- N: số lookup bổ sung khi không có read model.
- W: số lần dữ liệu nguồn thay đổi.
- F: số bản sao trung bình cần cập nhật mỗi lần thay đổi.

Số lượt đọc bổ sung của mô hình không lặp:

\[
\text{ExtraReads} \approx R \times N.
\]

Số lượt cập nhật bản sao của mô hình có lặp:

\[
\text{ProjectionWrites} \approx W \times F.
\]

Ví dụ:

~~~text
10.000 lần mở dashboard/ngày
30 lookup bổ sung/màn hình
5 lần đổi tên khóa/ngày
2.000 bản sao bị ảnh hưởng/lần đổi tên
~~~

Ta có:

\[
\text{ExtraReads} = 10.000 \times 30 = 300.000,
\]

\[
\text{ProjectionWrites} = 5 \times 2.000 = 10.000.
\]

Không thể chỉ so số 300.000 với 10.000 để tuyên bố thiết kế nào rẻ hơn: một lần ghi hàng loạt, chi phí index, IO, message, retry và storage khác một lượt GET. Nhưng đây là cách **đặt giả thuyết để đo thực tế**.

### 10.3. Mẫu truy vấn quyết định tính hiệu quả

Lặp courseTitle hợp lý khi:

- Màn danh sách được đọc rất nhiều lần.
- Title thay đổi tương đối hiếm.
- Độ trễ cập nhật vài giây được chấp nhận.
- Có khả năng tìm và cập nhật những bản sao liên quan.

Lặp trạng thái online của một tài khoản có hàng triệu follower thường kém hợp lý nếu trạng thái đổi liên tục. Một dịch vụ presence có batch/cache theo userId có thể phù hợp hơn việc cập nhật hàng triệu bản sao mỗi phút.

## 11. Consistency: làm sao giữ các bản sao không sai?

### 11.1. Nguồn thật và bản sao được phép trễ

Giả sử Course C101 đổi tên lúc t0:

~~~text
t0  Source Course: "NoSQL nền tảng", version 13
t1  Outbox/CDC ghi nhận thay đổi
t2  Projection worker nhận event
t3  Một phần LearnerCourseView được cập nhật
t4  Tất cả bản sao đã được cập nhật
~~~

Trong khoảng t0–t4, hai người học có thể thấy hai tên khác nhau. Với tên khóa, chuyện này có thể chấp nhận nếu hệ thống đã xác định mức trễ tối đa mong muốn và có khả năng theo dõi.

Đối với quyền truy cập đã bị thu hồi hoặc số dư tiền, sử dụng bản sao trễ để quyết định có thể gây hậu quả nghiêm trọng. **Độ mới chấp nhận được là thuộc tính nghiệp vụ, không phải suy luận từ tên NoSQL.**

### 11.2. Strong read không tự đồng bộ các kho độc lập

Một hệ có thể hỗ trợ đọc nhất quán mạnh trên một item/document trong phạm vi của nó. Điều đó không có nghĩa bản chiếu ở kho khác đã nhận mọi thay đổi. Ngay cả khi projection đã cập nhật, hai yêu cầu đồng thời vẫn có thể tranh chấp ở nguồn nếu ứng dụng kiểm tra rồi mới ghi.

Các bất biến như “mỗi ghế chỉ được đặt một lần” phải được bảo vệ bằng cơ chế ghi có điều kiện hoặc giao dịch đúng phạm vi **ở nơi có thẩm quyền**, không phải bởi việc đọc một read model mới nhất.

### 11.3. Lặp dữ liệu không phải transaction phân tán miễn phí

Không thể mặc định cập nhật 100.000 EnrollmentView trong cùng một transaction với Course.title mà không có giới hạn, độ trễ hoặc rủi ro vận hành. Các cơ sở dữ liệu có khả năng transaction khác nhau về:

- Số lượng đối tượng và dung lượng.
- Phạm vi node/shard/Region.
- Isolation và xử lý xung đột.
- Chi phí dưới tải.
- Khả năng phối hợp với hệ ngoài.

Nếu việc một số bản sao cũ tạm thời là không thể chấp nhận, cần xem lại kiến trúc: có thể nên giữ trường đó ở một nguồn được đọc trực tiếp hoặc một cơ chế cập nhật đồng bộ có phạm vi đủ nhỏ.

## 12. Thiết kế pipeline cập nhật có thể phục hồi

### 12.1. Rủi ro dual write

Một cách viết tưởng đơn giản:

~~~javascript
await courseStore.updateTitle(courseId, newTitle);
await learnerCourseViews.updateTitles(courseId, newTitle);
~~~

có khoảng trống:

- Course cập nhật thành công, projection lỗi.
- Tiến trình chết trước khi gọi projection.
- Một worker khác xử lý cập nhật mới hơn và bị event cũ ghi đè.
- Client timeout rồi retry làm phát sinh event trùng.

Hai lệnh tới hai hệ dữ liệu độc lập không tự tạo một transaction chung.

### 12.2. Transactional outbox hoặc CDC

~~~mermaid
flowchart LR
    A["Course API"] --> B["Course source"]
    B --> C["Outbox / CDC"]
    C --> D["Event stream"]
    D --> E["Projection worker"]
    E --> F["LearnerCourseView"]
    F --> G["Dashboard query"]
~~~

Với **transactional outbox**, khi nguồn hỗ trợ transaction, có thể ghi Course và bản ghi event cùng lúc:

~~~text
transaction:
    UPDATE Course C101:
        title = "NoSQL nền tảng"
        version = 13

    INSERT Outbox:
        eventId = EVT-13
        entityId = C101
        entityVersion = 13
        type = COURSE_RENAMED

commit
~~~

Worker nhận event từ outbox/queue rồi cập nhật read model. **CDC** (Change Data Capture) là một đường khác để lấy thay đổi đã commit từ nguồn.

Điều hai cơ chế này không tự bảo đảm:

- Không bao giờ nhận lại event.
- Mọi event đến đúng thứ tự toàn cục.
- Bản sao cập nhật tức thì sau commit.
- Mọi thao tác projection luôn thành công.

Vì vậy cần **retry, idempotency, versioning, checkpoint và đối soát**.

### 12.3. Event được gửi lại

~~~json
{
  "eventId": "EVT-13",
  "entityId": "C101",
  "entityVersion": 13,
  "title": "NoSQL nền tảng"
}
~~~

Một hệ giao sự kiện **at least once** có thể gửi EVT-13 hai lần. Nếu projection đặt title theo version 13, thao tác có thể được thiết kế idempotent. Ngược lại, một event “tăng completedLessonCount thêm 1” mà được áp dụng hai lần sẽ làm sai số liệu.

Trong pseudo-code:

~~~text
onEvent(event):
    applyToProjectionOnlyIfNewerVersion(event)
    recordProcessingOutcome(event.eventId)
~~~

Việc kiểm tra eventId đã tồn tại rồi mới ghi không tự bảo đảm không có race. Nếu cần “một sự kiện chỉ áp dụng một lần”, điều kiện và tác dụng cập nhật phải ở phạm vi nguyên tử hoặc thiết kế cập nhật idempotent.

### 12.4. Event đến sai thứ tự

~~~text
Course v12 -> title = "NoSQL căn bản"
Course v13 -> title = "NoSQL nền tảng"
Course v14 -> title = "NoSQL nâng cao"

Thứ tự worker nhận được: v14, v12, v13
~~~

Nếu ghi vô điều kiện, bản chiếu cuối có thể quay về tên v13 dù nguồn là v14. Quy tắc đúng:

~~~text
Chỉ áp dụng candidate nếu:
  candidate.courseVersion > stored.courseVersion.
~~~

Việc so sánh và cập nhật phải được bảo vệ ở điểm ghi, vì hai worker có thể cùng đọc version cũ rồi ghi theo thứ tự ngược. Một lần GET để kiểm tra trước PUT vô điều kiện vẫn có lỗi check-then-write.

### 12.5. Nhiều nguồn có nhiều version

Một bản chiếu có thể chứa:

~~~json
{
  "courseTitle": "NoSQL nền tảng",
  "courseVersion": 13,
  "instructorName": "Nguyễn Minh",
  "instructorVersion": 8,
  "progressPercent": 65,
  "progressVersion": 47
}
~~~

Course, Instructor và Progress thay đổi độc lập; không nên dùng một version chung mà không có quy ước rõ. Event progressVersion 48 phải cập nhật nhóm trường Progress, không được mang theo title cũ và ghi đè courseTitle mới.

Có thể cập nhật từng nhóm field theo version riêng hoặc xây lại projection đầy đủ từ nguồn nhất quán theo hợp đồng.

## 13. Xóa, thu hồi và dữ liệu đến muộn

### 13.1. Dữ liệu xóa cũng cần được phát tới các bản sao

Nếu Enrollment E100 bị hủy, hệ thống cần quyết định:

- Ẩn khỏi danh sách khóa đang học.
- Giữ trong lịch sử đã hủy.
- Ngăn truy cập nội dung có trả phí.
- Xử lý các read model đang chứa status ACTIVE.

Không nên chỉ xóa nguồn rồi cho rằng bản chiếu ở các kho khác tự biến mất.

### 13.2. Nguy cơ “hồi sinh” bản ghi

~~~text
v20: Enrollment ACTIVE
v21: Enrollment CANCELLED

Worker A áp dụng v21, ẩn bản ghi.
Worker B nhận v20 đến muộn và ghi ACTIVE trở lại.
~~~

Nếu bản chiếu đã xóa cứng và không lưu thông tin phiên bản, một event cũ có thể tạo lại tài liệu ACTIVE. Cần có **tombstone/version**, trạng thái DELETED/CANCELLED hoặc cơ chế conditional delete/write theo version.

Chính sách này phải tồn tại đủ lâu so với khả năng nhận event cũ; không thể mặc định xóa vật lý rồi quên phiên bản cuối là an toàn.

### 13.3. Xóa dữ liệu cá nhân

Khi hồ sơ người học được nhân vào:

~~~text
Learner profile
Course learner list
Dashboard
Search index
Cache
Exports / reports
~~~

thì một yêu cầu xóa hoặc sửa thông tin phải bao phủ tất cả bản sao thuộc phạm vi xử lý. Phi chuẩn hóa tăng bề mặt dữ liệu nhạy cảm cần quản lý.

**Giảm thiểu dữ liệu:** Chỉ lặp learnerId, displayName và avatar nếu màn hình cần; tránh nhân email, điện thoại, thông tin thanh toán vào mọi read model.

## 14. Phân biệt read model với cache và CQRS

### 14.1. Cache không hoàn toàn giống read model

**Cache** thường lưu bản sao tạm thời của kết quả/bản ghi, có TTL hoặc eviction; khi cache miss thì tìm về nguồn.

**Read model phi chuẩn hóa** thường có schema, khóa truy cập, quy tắc projection, version và khả năng rebuild riêng. Nó có thể là dữ liệu dẫn xuất tái tạo được, nhưng không đơn thuần là một bản cache tùy ý.

| Khái niệm | Mục đích | Rủi ro cần quản lý |
|---|---|---|
| Cache-aside | Giảm lượt đọc nguồn | TTL, invalidation, cache stampede |
| Denormalized read model | Tối ưu truy vấn theo khóa cụ thể | Đồng bộ, version, repair |
| Materialized view | Duy trì kết quả dẫn xuất bằng cơ chế hệ hỗ trợ | Phạm vi query, consistency, giới hạn hệ |
| CQRS | Tách trách nhiệm mô hình ghi/đọc | Quy tắc nguồn, luồng cập nhật, vận hành |

### 14.2. CQRS không đòi hỏi hai cơ sở dữ liệu

~~~text
Command: CompleteLesson
    |
    v
Progress source
    |
    v
LearningProgressChanged
    |
    v
LearnerDashboard projection
    |
    v
Query: GET /me/dashboard
~~~

**Command Query Responsibility Segregation (CQRS)** là cách tách mô hình thao tác ghi và truy vấn đọc. Có thể dùng trong một ứng dụng/một database hoặc nhiều dịch vụ; không bắt buộc phải là event sourcing hay có hai kho vật lý.

### 14.3. Materialized view có phạm vi cụ thể

Một số hệ NoSQL hỗ trợ materialized view hay secondary index do hệ thống duy trì. Chúng có thể giảm công sức tự viết worker, nhưng phải hỏi:

- View hỗ trợ những khóa và phép lọc nào?
- Update là đồng bộ hay bất đồng bộ?
- Có thể lệch trong những tình huống lỗi nào?
- Cách backfill và sửa dữ liệu sai?
- Chi phí ghi tăng bao nhiêu?

Không được suy từ tên materialized view ra bảo đảm nhất quán mạnh trong mọi hệ.

## 15. Khi nào không nên lặp dữ liệu?

### 15.1. Field thay đổi quá thường xuyên và có fan-out lớn

Nếu trạng thái online của một tài khoản thay đổi mỗi phút và tài khoản có ba triệu người theo dõi, lặp trạng thái này vào từng hồ sơ follower sẽ gây nhiều cập nhật.

Một dịch vụ Presence đọc bằng batch/cache ngắn hạn có thể hiệu quả hơn. Dữ liệu ít biến động như displayName có thể được lặp trong phạm vi được kiểm soát.

### 15.2. Tính đúng tại thời điểm chốt giao dịch

Không sử dụng bản sao có độ trễ bất định làm căn cứ cuối cùng cho:

- Số dư hoặc hạn mức có thể chi.
- Đặt ghế cuối cùng.
- Quyền đã bị thu hồi.
- Trạng thái thanh toán để giao hàng.
- Giá cuối cùng phải xác nhận với khách.

Search/read model có thể phục vụ **khám phá hoặc hiển thị tham khảo**, nhưng bước giao dịch phải kiểm tra/ghi tại điểm có thẩm quyền bằng ràng buộc phù hợp.

### 15.3. Bản sao chứa quá nhiều dữ liệu nhạy cảm

Nếu màn hình chỉ cần tên và ảnh, việc nhân email, địa chỉ và dữ liệu thanh toán là không cần thiết. Mỗi bản sao tăng nguy cơ rò rỉ, chi phí mã hóa, audit và xóa dữ liệu.

### 15.4. Truy vấn chưa được xác nhận bằng dữ liệu sử dụng

Khi chưa biết màn hình sẽ lọc/sắp theo gì, nhiều bảng projection có thể tạo chi phí không cần thiết. Có thể bắt đầu bằng mô hình đơn giản, tối ưu batch/index, đo đạc rồi bổ sung read model theo đường truy vấn thật.

## 16. Multi-tenant và phạm vi khóa

Giả sử hai tenant đều có learnerId = L001 và courseId = C101. Một document ID chỉ bằng L001#C101 có thể gây va chạm giữa tenant.

Ví dụ khóa đầy đủ:

~~~text
LEARNER_VIEW#T1#L001#C101
LEARNER_VIEW#T2#L001#C101
~~~

Tùy công nghệ, tenantId có thể được đưa vào composite partition key hoặc document ID. Mọi query phải gắn với tenant được suy ra từ ngữ cảnh xác thực đáng tin cậy, **không chỉ từ tham số client có thể tự sửa**.

Đường đọc trực tiếp từ read model cũng cần authorization. Lặp dữ liệu không được làm xuất hiện một đường tắt vượt qua kiểm tra quyền của nguồn.

## 17. Giám sát hiệu quả và độ lệch của bản sao

### 17.1. Chỉ số đường đọc

| Chỉ số | Ý nghĩa |
|---|---|
| DB requests / API request | Số lượt gọi kho dữ liệu trên mỗi màn |
| Remote calls | Số lời gọi qua dịch vụ khác |
| Partitions touched | Số nhóm dữ liệu phải đọc |
| Payload bytes | Dung lượng truyền |
| Latency p50/p95/p99 | Độ trễ thực tế |
| Error/timeout rate | Tính ổn định |
| DB CPU/IO | Chi phí hệ dữ liệu |

Nếu số request giảm nhưng p99 vẫn cao vì một partition rất lớn hoặc payload quá nặng, cần xem lại khóa và phân trang.

### 17.2. Chỉ số đường ghi

| Chỉ số | Mục đích |
|---|---|
| Projection writes per source update | Đo write amplification |
| Event backlog / consumer lag | Phát hiện pipeline chậm |
| Oldest unprocessed event age | Phát hiện event bị kẹt |
| Retry và dead-letter queue | Phát hiện dữ liệu chưa được sửa |
| SourceVersion lag | Bản chiếu chậm bao nhiêu phiên bản |
| Drift rate | Tỷ lệ bản sao lệch nguồn |
| Projection storage size | Chi phí lưu |
| Rebuild duration | Khả năng phục hồi |

### 17.3. Định nghĩa mục tiêu độ mới

Ví dụ một hợp đồng nội bộ:

~~~text
Course.title:
  99% bản chiếu phản ánh thay đổi trong 30 giây từ khi nguồn commit.

Progress:
  Màn hình của người học phải phản ánh thay đổi gần ngay;
  khi chưa bắt kịp có thể đọc nguồn hoặc hiển thị trạng thái đồng bộ.

Access control:
  Không được dựa vào bản chiếu cũ để cấp quyền đã bị thu hồi.
~~~

Đây chỉ là **mục tiêu thiết kế minh họa**, không phải đặc tính mặc định của công nghệ. Muốn bảo đảm vận hành phải đo mốc source commit, thời điểm worker cập nhật và thời điểm API nhìn thấy kết quả.

## 18. Đối soát và xây lại read model

### 18.1. Tại sao cần rebuild?

Một projection có thể cần xây lại khi:

- Thay schema hoặc cách tính.
- Thêm trường mới cho màn hình.
- Worker trước đó có bug.
- Một số event bị mất hoặc hết thời gian lưu.
- Chuyển partition key, công nghệ lưu trữ hoặc index.
- Sửa chính sách xóa dữ liệu.

Nếu coi read model là **có thể tái tạo**, nguồn và dữ liệu lịch sử phải thật sự đủ để tái tạo nó. Một projection được tính từ sự kiện mà nguồn đã xóa hết lịch sử không thể tự được rebuild chính xác nếu không có snapshot bổ sung.

### 18.2. Chuyển phiên bản

~~~text
learnerCourseViews_v1:
  courseId, title, progress

learnerCourseViews_v2:
  courseId, title, instructorName,
  progress, lastAccessedAt
~~~

Quy trình chuyển phiên bản:

1. Tạo v2 với schema và khóa mới.
2. Ghi nhận mốc nguồn/sự kiện để nối tiếp thay đổi.
3. Backfill dữ liệu nguồn.
4. Tiếp nhận các thay đổi trong lúc backfill.
5. Bảo vệ thứ tự version và xử lý event trùng.
6. Đối chiếu bản sao thiếu, thừa, cũ và sai.
7. Chuyển query sang v2 khi đạt điều kiện.
8. Giữ phương án quay lại và dọn v1 theo chính sách.

Không nên chỉ quét dữ liệu một lần rồi bật event sau khi quét xong, vì thay đổi xảy ra trong khoảng trống có thể bị mất.

### 18.3. Cách đối soát

Một tác vụ đối soát có thể:

~~~text
for each source entity in a controlled batch:
    expected = buildProjectionFromSource(entity)
    actual = readProjection(entity.id)
    compare business fields and versions
    record missing / extra / stale / mismatched
    repair safely if permitted
~~~

Với tập dữ liệu rất lớn, có thể kết hợp lấy mẫu, đối chiếu theo mốc event và chạy chiến dịch rebuild. Điều quan trọng là **có đường sửa sai**, không chỉ cảnh báo “đã lệch” mà không thể phục hồi.

## 19. Bài tập thực hành

### Bài 1. Phát hiện N+1

Một API trả 50 bài viết. Mỗi bài cần tên tác giả, avatar và số bình luận. Hiện API lấy 50 bài rồi truy vấn thêm 3 lần cho từng bài.

Hãy:

1. Tính số lần đọc dữ liệu theo cách đơn giản nếu không có batch.
2. Đề xuất phương án batch để giảm lời gọi.
3. Đề xuất read model chứa thông tin đã lặp phù hợp.
4. Nêu những field có thể cũ vài giây và field cần đọc ở nguồn.

**Gợi ý:** Có thể có 1 + 50 × 3 = 151 lượt đọc. Nếu nhiều bài cùng tác giả, deduplication/batch giúp giảm số request mà chưa cần nhân mọi trường.

### Bài 2. Hai đường đọc đơn hàng

Một cửa hàng cần:

- Khách hàng xem 20 đơn gần nhất theo customerId.
- Cửa hàng xem đơn theo storeId.
- Tra cứu chi tiết theo orderId.
- Trạng thái chuyển PENDING → PAID → SHIPPED.

Hãy thiết kế nguồn Order và hai read model; xác định partition/sort key, trường được lặp, event thay đổi trạng thái, quy tắc version và cơ chế đối soát khi một bản sao chưa cập nhật.

**Gợi ý:** Trạng thái chính thức thuộc Order source; hai bảng đọc có thể mang bản chiếu cùng orderId và status.

### Bài 3. Trường nào nên lặp?

Màn hình khóa học cần:

~~~text
title
thumbnail
instructorName
progressPercent
paymentStatus
accessRevoked
~~~

Hãy phân loại những trường phù hợp cho projection, những trường thay đổi thường xuyên cần thiết kế riêng, và những trường không được dùng bản sao trễ để cấp quyền hoặc xác nhận thanh toán.

### Bài 4. Tính write fan-out

Tên một giảng viên được lặp vào 80.000 read model. Giảng viên đổi tên 3 lần trong tháng. Nếu cập nhật mọi bản sao, số lượt cập nhật dự kiến là:

\[
80.000 \times 3 = 240.000.
\]

Hãy nêu ít nhất năm chỉ số cần đo trước khi quyết định có nên lặp tên. Nếu màn hình được mở 2 triệu lần/tháng, liệu batch/cache có thể là lựa chọn cạnh tranh không?

### Bài 5. Event sai thứ tự

~~~text
COURSE_RENAMED v11: "NoSQL 1"
COURSE_RENAMED v12: "NoSQL cơ bản"
COURSE_RENAMED v13: "NoSQL nền tảng"

Worker nhận: v13, v11, v12
~~~

Hãy viết giả mã chỉ áp dụng version mới hơn và giải thích vì sao GET version trước rồi PUT vô điều kiện vẫn có thể xảy ra race giữa hai worker.

### Bài 6. Xóa dữ liệu cá nhân

Người dùng yêu cầu xóa tài khoản. Tên và email đã xuất hiện trong hồ sơ, bảng bạn bè, khóa học, bình luận, dashboard và search index.

Hãy nêu cách xác định bản sao, phát event xóa, đối soát xóa, bảo vệ trước event cũ phục hồi dữ liệu và bảo đảm quyền truy cập trong lúc đồng bộ chưa xong.

### Bài 7. Trạng thái online của tài khoản lớn

Một tài khoản có 3 triệu follower, trạng thái online đổi nhiều lần mỗi phút. So sánh:

- Lặp trạng thái vào mọi follower record.
- Dùng batch read tới Presence service.
- Cache ngắn hạn theo userId.

Chọn phương án theo read latency, write amplification, độ mới cần thiết và khả năng phục hồi.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Lặp toàn bộ document thay vì chỉ field cần | Tăng dung lượng và chi phí xóa | Giới hạn projection theo query |
| Để hai nơi sửa cùng một field | Hai giá trị gốc mâu thuẫn | Quy định một chủ sở hữu |
| Ghi nguồn rồi ghi view mà không có recovery | Dual write thất bại gây lệch | Outbox/CDC, retry và đối soát |
| Không version event | Event cũ ghi đè mới | Kiểm tra version tại điểm áp dụng |
| Đếm cộng dồn mọi event nhận được | Retry làm tăng hai lần | Idempotency hoặc tính lại trạng thái |
| Chỉ xóa bản sao rồi quên tombstone | Event cũ hồi sinh dữ liệu | Giữ trạng thái/version xóa phù hợp |
| Dùng projection cũ cấp quyền | Quyền đã thu hồi vẫn được dùng | Xác minh ở nguồn/cơ chế tin cậy |
| Cố nhúng tập dữ liệu tăng vô hạn | Document/partition nóng hoặc quá lớn | Tham chiếu, chia bucket, phân trang |
| Lặp không xét tenant | Rò rỉ, va chạm khóa | Khóa có phạm vi tenant và kiểm soát quyền |
| Giảm số query nhưng không đo payload | Lưu lượng có thể tăng | Đo bytes và latency |
| Không có cách rebuild | Sai dữ liệu lâu dài sau sự cố | Backfill, checkpoint, reconciliation |
| Coi materialized view là đồng bộ tức thời | Quyết định trên bản sao cũ | Hiểu phạm vi bảo đảm hệ cụ thể |

## 21. Kết luận

**Lặp dữ liệu có chủ đích để giảm trao đổi mạng** là một chiến lược quan trọng của thiết kế NoSQL theo truy vấn. Thay vì luôn lấy các thực thể phân tán rồi ghép tại thời điểm đọc, hệ thống có thể chuẩn bị một cấu trúc chứa **những trường được sử dụng cùng nhau**, đặt dưới **khóa truy cập phù hợp**.

Kỹ thuật này có thể giảm số round-trip, N+1 lookup, fan-out đọc và độ trễ của các màn hình thường xuyên truy cập. Đổi lại, nó tăng dung lượng, write amplification, độ phức tạp đồng bộ, rủi ro bản sao cũ, công việc xử lý xóa và nhu cầu giám sát.

Trước khi áp dụng, cần trả lời năm câu hỏi:

1. **Truy vấn nào đang chậm, nguyên nhân thực sự có phải trao đổi mạng không?**
2. **Field nào cần lặp và ai là nguồn có thẩm quyền của từng field?**
3. **Bản sao được phép chậm bao lâu, và hành động nào phải kiểm tra ở nguồn?**
4. **Khi event trùng, sai thứ tự, bị mất hoặc dữ liệu bị xóa, projection tự phục hồi ra sao?**
5. **Có đo, đối soát và xây lại được bản chiếu khi schema hoặc dữ liệu thay đổi không?**

Khi những câu hỏi này được xử lý, lặp dữ liệu không còn là sao chép tùy tiện. Nó trở thành **một hợp đồng rõ ràng giữa đường ghi và đường đọc**, giúp hệ thống NoSQL đáp ứng truy vấn hiệu quả mà vẫn giữ đúng ranh giới nhất quán và trách nhiệm nghiệp vụ.
