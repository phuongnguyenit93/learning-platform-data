# Single-table design và mô hình quan hệ dữ liệu

> **Chương:** DynamoDB  
> **Module:** CLOUD_PROVIDERS_AWS — tìm hiểu AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Trong cơ sở dữ liệu quan hệ, ta thường bắt đầu từ **entities, foreign keys và chuẩn hóa dữ liệu**, sau đó viết SQL JOIN để lấy thông tin. Với **Amazon DynamoDB**, một cơ sở dữ liệu NoSQL dạng key-value/document được AWS quản lý, thiết kế hiệu quả lại bắt đầu từ **những truy vấn và thao tác ứng dụng cần thực hiện**. Single-table design (STD) là một cách tổ chức **nhiều loại entity và quan hệ trong một bảng**, sử dụng **partition key (PK)**, **sort key (SK)**, item collections và secondary indexes để phục vụ các access patterns quan trọng với ít thao tác đọc.

Bài học sử dụng ví dụ **nền tảng học trực tuyến nhiều trường (multi-tenant)**. Học viên đăng ký nhiều khóa học; mỗi khóa học có nhiều học viên và nhiều bài học. Ứng dụng Java cần đọc nhanh hồ sơ, nội dung khóa học, danh sách đăng ký hai chiều và danh mục đã xuất bản, đồng thời bảo vệ ranh giới tenant.

Kết thúc bài, người học có thể:

1. Giải thích **single-table design là mẫu thiết kế**, không phải quy tắc “mọi ứng dụng bắt buộc chỉ có một bảng”.
2. Liệt kê, đo khối lượng và xếp ưu tiên **access patterns trước khi chọn keys**.
3. Xây dựng khóa tổng hợp `PK`/`SK`, namespace entity types và **item collection**.
4. Mô hình hóa **one-to-one, one-to-many và many-to-many** không cần JOIN lúc truy vấn nóng.
5. Sử dụng **GSI, LSI, sparse index, overloaded index** và đánh đổi với duplication.
6. Hiểu Query so với Scan, `KeyConditionExpression`, pagination, tính nhất quán, giới hạn kích thước.
7. Áp dụng **conditional writes, optimistic locking, transactions và idempotency** để duy trì ràng buộc nghiệp vụ.
8. Dự phòng hot partition, skew, capacity, cost, backup/PITR và data migration.
9. Trình bày mô hình bằng bảng, Mermaid, JSON, AWS CLI và ví dụ Java AWS SDK v2.
10. Phân biệt điều kiện để chọn **single-table, multi-table hoặc mô hình kết hợp**.

## 1. Tư duy access-pattern-first

### 1.1. DynamoDB không phải RDBMS chỉ thay cú pháp

Trong RDBMS, bạn có thể lưu:

~~~sql
CREATE TABLE student (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200)
);
CREATE TABLE course (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(300)
);
CREATE TABLE enrollment (
    student_id VARCHAR(64),
    course_id VARCHAR(64),
    enrolled_at TIMESTAMP,
    PRIMARY KEY (student_id, course_id)
);
~~~

Và sau đó truy vấn quan hệ bằng `JOIN`. DynamoDB không cung cấp **SQL JOIN** theo kiểu RDBMS trong API truy vấn DynamoDB. Dù có **PartiQL** hỗ trợ một tập cú pháp SQL để tương tác với bảng, nó không biến DynamoDB thành một máy chủ relational joins/foreign keys.

Vì vậy, với các đường đọc thường xuyên, ta thiết kế items để truy vấn theo **PK equality + SK range/prefix**, hoặc một **GSI** có khóa được tạo cho access pattern đó.

### 1.2. Single-table design là gì?

Thay vì bảng riêng cho `Students`, `Courses`, `Lessons` và `Enrollments`, ta có thể dùng một bảng `LearningCore` chứa các items khác loại:

~~~text
Table: LearningCore
Primary key: PK (String), SK (String)

PK                              SK                       Entity
TENANT#t1#USER#u1               PROFILE                  USER
TENANT#t1#COURSE#c1             META                     COURSE
TENANT#t1#COURSE#c1             LESSON#0001#l1           LESSON
TENANT#t1#COURSE#c1             LESSON#0002#l2           LESSON
TENANT#t1#COURSE#c1             ENROLLMENT#u1            ENROLLMENT
TENANT#t1#COURSE#c1             ENROLLMENT#u2            ENROLLMENT
~~~

**Không phải mọi item phải có cùng attributes.** Một `COURSE` item có `title` và `category`, một `ENROLLMENT` có `status`, `studentId` và `enrolledAt`. Chỉ các key/index attributes phải tuân thủ schema type của bảng/index.

### 1.3. Khi nào kiểu này hữu ích?

| Đặc điểm workload | Single-table đáng cân nhắc? | Lý do |
|---|---|---|
| Truy vấn lấy course và lessons liên tục | Có | Có thể đồng vị trí items theo một PK |
| Truy vấn quan hệ từ course → students và ngược lại | Có, dùng base + GSI | Định tuyến quan hệ theo access patterns |
| Workloads gồm nhiều entities độc lập, ít đọc cùng nhau | Có thể không | Multi-table đơn giản hơn |
| Các entities có yêu cầu backup, key KMS, TTL hoặc table class riêng | Thường nên cân nhắc multi-table | Ranh giới vận hành từng bảng rõ hơn |
| Schema biến động liên tục, truy vấn ad-hoc/analytics phức tạp | Thường cân nhắc RDBMS/warehouse | STD buộc dự đoán access patterns |
| Dữ liệu multi-tenant cần tenant-specific table encryption | Có thể chọn table-per-tenant | Một bảng chung không đáp ứng mọi isolation policy |

**AWS không yêu cầu tất cả ứng dụng dùng single-table design.** Tài liệu mới còn trình bày multi-table và aggregate design như những phương án có giá trị tùy correlation giữa access patterns và yêu cầu vận hành.

### 1.4. Quy trình đề xuất

~~~mermaid
flowchart TD
    A[Business requirements] --> B[Liệt kê entities và relationships]
    B --> C[Liệt kê access patterns / QPS / latency]
    C --> D[Định nghĩa PK, SK và item collections]
    D --> E[Kiểm tra mọi pattern qua GetItem/Query]
    E --> F{Có access pattern mới không?}
    F -->|Có| G[Thêm GSI / sparse GSI / duplication có kiểm soát]
    G --> H[Đánh giá write costs và consistency]
    F -->|Không| H
    H --> I[Test tải, hot keys, pagination, security]
    I --> J[Chốt data contract + migration/runbook]
~~~

**Không nên:** vẽ ERD xong chuyển toàn bộ tables thành items, rồi dựa vào `Scan + FilterExpression` để tái tạo joins. Mẫu đó thường tốn read capacity và khó đạt latency tốt khi dữ liệu lớn.

## 2. Các access patterns trước khi tạo bảng

### 2.1. Bài toán giáo dục multi-tenant

Entities:

- **Tenant/trường:** có nhiều học viên và khóa học.
- **Student/user:** có hồ sơ; có thể đăng ký nhiều khóa học.
- **Course:** có metadata, nhiều lessons và danh sách enrollments.
- **Lesson:** thuộc một course, có vị trí thứ tự.
- **Enrollment:** quan hệ **many-to-many** giữa users và courses, có `status`/`enrolledAt`.
- **Published catalog:** listing các courses đã publish theo category.

### 2.2. Ma trận truy vấn

| Mã | Ai gọi? | Cần lấy gì? | Tần suất minh họa | Cách truy xuất mục tiêu |
|---|---|---|---|---|
| AP1 | Profile API | Hồ sơ user theo ID | 500 QPS | `GetItem` base PK/SK |
| AP2 | Course API | Metadata một course | 1.000 QPS | `GetItem` base PK/SK |
| AP3 | Course page | Các lessons của course theo thứ tự | 300 QPS | `Query` base PK + `begins_with(SK)` |
| AP4 | Teacher portal | Các students enrolled trong một course | 200 QPS | `Query` base PK + enrollment prefix |
| AP5 | Student dashboard | Các courses user đã đăng ký | 700 QPS | `Query` GSI1 theo user |
| AP6 | Enrollment service | User đã đăng ký course này chưa? | 300 QPS | `GetItem` direct edge |
| AP7 | Public catalog | Courses published theo category, mới nhất trước | 400 QPS | `Query` sparse GSI2 |
| AP8 | Admin | Cập nhật status của một enrollment | 100 WPS | `UpdateItem` conditional/transaction |
| AP9 | Reporting | Tổng hợp enrollment theo tháng | theo batch | S3 export/analytics, không Scan nóng trên API |

Các con số chỉ để **diễn tập ước lượng**; cần thu telemetry thực. Mỗi access pattern phải được mô tả thêm bởi **p95/p99 latency, items per query, kích thước items, consistency requirement, tỷ lệ đọc/ghi và tính nhạy cảm dữ liệu**.

### 2.3. Đừng thiết kế chỉ cho câu hỏi hôm nay

Bảng thiết kế nên có:

~~~text
AccessPattern:
  id: AP5
  operation: List courses enrolled by user
  input: tenantId, userId, pageSize, nextToken
  frequency: 700 requests/second at peak
  expectedResponse: up to 30 enrollments/page
  consistency: eventual acceptable for dashboard
  requiredAttributes: courseId, status, enrolledAt, courseTitleSnapshot
  authz: caller may query only own tenant/user unless staff
  storagePath: GSI1PK + GSI1SK
~~~

Sau này nếu sản phẩm cần “tìm user theo email chưa biết ID”, phải đánh giá thêm index hoặc dịch vụ search; không tự chuyển thành full-table scan mỗi request.

## 3. PK/SK và item collections

### 3.1. Partition key và sort key

DynamoDB table có thể dùng:

- **Simple primary key:** chỉ partition key, một item cho mỗi PK.
- **Composite primary key:** partition key + sort key, cho phép nhiều items cùng PK nhưng SK khác.

Trong ví dụ:

~~~text
PK = "TENANT#" + tenantId + "#COURSE#" + courseId
SK = "LESSON#" + zeroPaddedOrder + "#" + lessonId
~~~

Một item được nhận diện duy nhất bởi **(PK, SK)**; ghi lại cùng cặp keys có thể **thay item hiện có**, trừ khi dùng condition expression.

### 3.2. Item collection là gì?

Một **item collection** là tập items có **cùng giá trị partition key** của base table.

~~~text
PK = TENANT#t1#COURSE#c1
 ├── SK=META
 ├── SK=LESSON#0001#l1
 ├── SK=LESSON#0002#l2
 ├── SK=ENROLLMENT#u1
 └── SK=ENROLLMENT#u2
~~~

Đây là **logical co-location** giúp `Query PK=...` lấy nhóm items liên quan. Không khẳng định mọi item cùng PK luôn bị khóa vào **một physical partition**: DynamoDB có adaptive capacity và split-for-heat tùy điều kiện, đặc biệt khi **không có LSI**. Điều cần thiết là thiết kế phân phối đủ đều để tránh hot keys.

### 3.3. Quy ước khóa cho multi-tenant

Đề xuất:

~~~text
PK = TENANT#<tenantId>#<ENTITY>#<entityId>
SK = <ITEM_TYPE>[#<orderedSuffix>]

Ví dụ:
PK = TENANT#t1#USER#u1
SK = PROFILE

PK = TENANT#t1#COURSE#c1
SK = META
~~~

Tất cả access keys (kể cả GSI partition keys nếu áp IAM per-tenant) bắt đầu bằng tenant prefix ổn định. **Giá trị keys là contract ứng dụng**, không có ý nghĩa đặc biệt với DynamoDB; `#` chỉ là delimiter tự chọn.

Không ghép input chưa được kiểm tra tùy ý vào keys. Validate tenant/user/course identifiers, chuẩn hóa encoding/case và tránh dấu phân cách do user kiểm soát gây key collisions.

### 3.4. Composite sort keys và prefix queries

Một số ví dụ:

~~~text
SK = META
SK = LESSON#0001#l1
SK = LESSON#0002#l2
SK = ENROLLMENT#u1
SK = ENROLLMENT#u2
SK = STATS
~~~

Với một course PK, bạn có thể:

- `GetItem PK=courseKey SK=META` để lấy metadata;
- `Query PK=courseKey AND begins_with(SK, "LESSON#")` để lấy lessons;
- `Query PK=courseKey AND begins_with(SK, "ENROLLMENT#")` để lấy enrollments;
- `Query PK=courseKey` để lấy tất cả các loại item trong collection (cần kiểm tra kích thước và pagination).

**Chỉ cần SK prefix là được nếu tenant/course PK đã biết.** DynamoDB không có khả năng Query theo SK mà không có PK equality trong cùng index.

### 3.5. Sort order không giống thứ tự nhập

Nếu sort key là **String**, DynamoDB sắp theo thứ tự bytes UTF-8, không theo quy tắc số học cho chuỗi số:

~~~text
LESSON#1
LESSON#10
LESSON#2
~~~

Để thứ tự đúng, dùng **zero-padded sequence**:

~~~text
LESSON#0001
LESSON#0002
LESSON#0010
~~~

Với timestamps, dùng ISO-8601 UTC cố định định dạng như `2026-11-20T03:00:00Z` để lexical order trùng thứ tự thời gian theo cùng độ chính xác/timezone. Đừng trộn `+07:00` với `Z` trong một sort range nếu muốn so trực tiếp.

### 3.6. Tránh item lớn/đơn khổng lồ

DynamoDB giới hạn **400 KiB cho mỗi item** (bao gồm tên attributes và values theo quy tắc tính size của AWS). Không nhét một list 100.000 lessons/enrollments vào **một** item.

Phân biệt:

- **Nested document trong một item:** tốt cho dữ liệu nhỏ, thay cùng nhau, có bounded cardinality.
- **Nhiều items cùng PK:** tốt cho one-to-many lớn, cần pagination/update độc lập.
- **S3 private object + metadata pointer trong DynamoDB:** tốt cho video, PDF hoặc blob lớn.

## 4. Thiết kế dữ liệu mẫu có thể truy vấn

### 4.1. Bảng LearningCore

Lược đồ key logic:

~~~text
Table name: LearningCore
PK: String
SK: String

Optional projected index-key attributes:
GSI1PK: String
GSI1SK: String
GSI2PK: String
GSI2SK: String
~~~

Không phải mọi item cần có `GSI1PK` hoặc `GSI2PK`. Chỉ items có đầy đủ index-key attributes cần thiết mới được đưa vào GSI tương ứng. Cần đảm bảo values đúng kiểu được định nghĩa trong index key schema.

### 4.2. Item mẫu

| Entity | PK | SK | Dữ liệu khác | Index keys |
|---|---|---|---|---|
| USER | `TENANT#t1#USER#u1` | `PROFILE` | name, emailHash, createdAt | không |
| COURSE | `TENANT#t1#COURSE#c1` | `META` | title, category, visibility, publishedAt | `GSI2PK=TENANT#t1#CATEGORY#java`, `GSI2SK=PUBLISHED#2026-11-20T03:00:00Z#COURSE#c1` nếu published |
| LESSON | `TENANT#t1#COURSE#c1` | `LESSON#0001#l1` | title, videoS3Key, duration | không |
| ENROLLMENT | `TENANT#t1#COURSE#c1` | `ENROLLMENT#u1` | userId, status, enrolledAt, titleSnapshot | `GSI1PK=TENANT#t1#USER#u1`, `GSI1SK=ENROLLMENT#c1` |
| ENROLLMENT | `TENANT#t1#COURSE#c1` | `ENROLLMENT#u2` | userId, status, enrolledAt, titleSnapshot | `GSI1PK=TENANT#t1#USER#u2`, `GSI1SK=ENROLLMENT#c1` |

Tất cả được lưu ở **một bảng**, nhưng rõ entity type và key namespace. `titleSnapshot` là **denormalized field**: nếu tên khóa học đổi, enrollment snapshot có thể cũ; phải định nghĩa consistency contract trước khi sử dụng.

### 4.3. JSON biểu diễn user item

Đây là JSON ứng dụng ở dạng logic, **không phải** định dạng `AttributeValue` của AWS CLI:

~~~json
{
  "PK": "TENANT#t1#USER#u1",
  "SK": "PROFILE",
  "entityType": "USER",
  "userId": "u1",
  "displayName": "Hoc vien 1",
  "createdAt": "2026-11-20T03:00:00Z"
}
~~~

### 4.4. JSON biểu diễn course item và sparse catalog

~~~json
{
  "PK": "TENANT#t1#COURSE#c1",
  "SK": "META",
  "entityType": "COURSE",
  "courseId": "c1",
  "title": "Java tren AWS",
  "category": "java",
  "visibility": "PUBLISHED",
  "publishedAt": "2026-11-20T03:00:00Z",
  "GSI2PK": "TENANT#t1#CATEGORY#java",
  "GSI2SK": "PUBLISHED#2026-11-20T03:00:00Z#COURSE#c1"
}
~~~

Nếu course ở `DRAFT`, **không gắn GSI2PK/GSI2SK** để nó không xuất hiện trong catalog GSI. Khi chuyển PUBLISHED → DRAFT, phải **REMOVE** cả index-key attributes theo data contract. Không chỉ sửa `visibility` rồi giả định index tự ẩn course.

### 4.5. JSON biểu diễn enrollment (edge)

~~~json
{
  "PK": "TENANT#t1#COURSE#c1",
  "SK": "ENROLLMENT#u1",
  "entityType": "ENROLLMENT",
  "userId": "u1",
  "courseId": "c1",
  "status": "ACTIVE",
  "enrolledAt": "2026-11-20T03:05:00Z",
  "GSI1PK": "TENANT#t1#USER#u1",
  "GSI1SK": "ENROLLMENT#c1"
}
~~~

Mỗi enrollment là **một item đại diện quan hệ** (edge). Từ course → students dùng **base table**; từ user → courses dùng **GSI1**. Không cần tạo hai enrollment items đối xứng nếu GSI1 đủ đáp ứng latency/consistency. Nhưng GSI1 eventual consistency có thể gây chậm cập nhật dashboard ngay sau đăng ký; cân nhắc cách hiển thị/đọc bổ sung trên writer path.

### 4.6. Một sơ đồ item collection

~~~mermaid
flowchart TD
    T[(LearningCore)] --> U["PK TENANT#t1#USER#u1"]
    T --> C["PK TENANT#t1#COURSE#c1"]
    U --> P["SK PROFILE"]
    C --> M["SK META"]
    C --> L1["SK LESSON#0001#l1"]
    C --> L2["SK LESSON#0002#l2"]
    C --> E1["SK ENROLLMENT#u1"]
    C --> E2["SK ENROLLMENT#u2"]
    E1 -. "GSI1PK=TENANT#t1#USER#u1" .-> U
    M -. "GSI2PK=TENANT#t1#CATEGORY#java" .-> CAT[Catalog GSI2]
~~~

## 5. Các dạng quan hệ dữ liệu

### 5.1. One-to-one

Ví dụ mỗi user có một profile:

~~~text
PK=TENANT#t1#USER#u1  SK=PROFILE
~~~

Nếu dữ liệu auth và thông tin hiển thị luôn được đọc chung và nhỏ, có thể embed vào cùng một item. Nếu secrets/audit/PII có quyền đọc khác, cần cân nhắc lưu ở table/item/tài nguyên riêng với IAM/DB authz phù hợp.

### 5.2. One-to-many: course → lessons

~~~text
PK=TENANT#t1#COURSE#c1
  SK=META
  SK=LESSON#0001#l1
  SK=LESSON#0002#l2
  SK=LESSON#0003#l3
~~~

Một `Query` có `begins_with(SK, "LESSON#")` trả lessons theo thứ tự SK. Các lessons có thể update riêng, tăng/giảm số lượng mà không vượt giới hạn 400 KiB của một single embedded list item.

**Trade-off:** nếu course có hàng triệu lessons/events hoặc một course viral nhận quá nhiều traffic ghi lên cùng PK, cần chia thành các item collections theo bucket/course section; phải chấp nhận nhiều queries/fan-out để lấy toàn bộ.

### 5.3. Many-to-many: student ↔ course

~~~mermaid
flowchart LR
    U1[User u1] -->|enrolled| C1[Course c1]
    U1 -->|enrolled| C2[Course c2]
    U2[User u2] -->|enrolled| C1
    U2 -->|enrolled| C3[Course c3]
~~~

**Mô hình cạnh/edge item**:

~~~text
Base table:
  PK=TENANT#t1#COURSE#c1
  SK=ENROLLMENT#u1

GSI1:
  GSI1PK=TENANT#t1#USER#u1
  GSI1SK=ENROLLMENT#c1
~~~

Hệ quả:

- Liệt kê students của course: base `Query`.
- Liệt kê courses của user: GSI1 `Query`.
- Kiểm tra user đã enrolled chưa: base `GetItem` theo PK/SK.
- Cập nhật enrollment status: một `UpdateItem` trên base item; GSI tự duy trì các index keys và projected fields.
- Nếu GSI1 chỉ project `KEYS_ONLY` thì dashboard phải đọc tiếp base items; nếu project cần thiết, sẽ có thêm storage/write costs.

**Không phải RDBMS foreign key:** DynamoDB không tự bảo đảm course/user tồn tại khi tạo edge; cần condition checks, transactions hoặc application constraints.

### 5.4. Adjacency list: khi quan hệ phức tạp hơn

Một **adjacency list** biểu diễn nodes và edges dưới các partition keys của node. Với graph nhiều loại cạnh:

~~~text
PK=NODE#course-c1  SK=META
PK=NODE#course-c1  SK=EDGE#STUDENT#u1
PK=NODE#user-u1    SK=META
PK=NODE#user-u1    SK=EDGE#COURSE#c1
~~~

Cách **dual-edge** có ưu điểm query hai chiều trên base table nhưng tạo **hai copies của một quan hệ**, cần transactional write/delete để giữ đồng bộ. Mô hình ví dụ chính dùng **một edge + GSI** vì dễ quản lý hơn với access pattern đã biết.

Khi nào nên dual-edge? Khi **cả hai chiều** đều cần strong consistency trên base table hoặc quyền/latency không phù hợp với GSI eventual. Khi nào nên single-edge + GSI? Khi có thể chấp nhận eventual consistency ở chiều ngược, giảm duplicate base items và số writes.

### 5.5. Không biến một GSI thành DB JOIN engine

Nếu API cần user profile + 100 course metadata, có thể:

- GSI1 query các enrollment edges với projected `courseId`, `titleSnapshot`;
- Hoặc lấy courseIds rồi `BatchGetItem` course META (cần pagination/unprocessed keys);
- Hoặc thay response contract chỉ trả course summary và tải chi tiết khi cần.

Đừng query N enrollment rồi gọi N lần `GetItem` tuần tự nếu ứng dụng có thể gom và giới hạn requests hợp lý. Đó là vấn đề tương tự **N+1** trong ORM, nhưng xảy ra ở phía application/DynamoDB APIs.

## 6. GSI và LSI: truy vấn chiều thứ hai

### 6.1. GSI là gì?

**Global Secondary Index (GSI)** có partition/sort keys **khác** base table. DynamoDB tự cập nhật index từ thay đổi trên table theo cơ chế **eventual consistency**.

Trong ví dụ:

~~~text
Base key: PK, SK

GSI1:
  Partition key: GSI1PK
  Sort key:      GSI1SK

GSI2:
  Partition key: GSI2PK
  Sort key:      GSI2SK
~~~

GSI1 dùng tra enrollments theo user. GSI2 dùng liệt kê courses published theo category. **Không được đọc strongly consistent từ GSI**, kể cả base table query có thể yêu cầu `ConsistentRead=true`.

### 6.2. LSI khác GSI ra sao?

| Khía cạnh | GSI | LSI |
|---|---|---|
| Partition key | Có thể khác base PK | **Giống base PK** |
| Sort key | Có thể khác base SK | Khác base SK |
| Tạo thêm sau khi table tồn tại | Có thể theo giới hạn AWS | **Không**; chỉ lúc tạo table |
| Consistency | **Eventual only** | Eventual hoặc strong |
| Item collection size | Không áp 10 GB constraint của LSI | Có **10 GB limit** cho collection của base table cùng LSI |
| Capacity | GSI có index-specific consumption/throttling | Tiêu thụ capacity của base table theo semantics |
| Backfill | GSI tạo trên table hiện có cần backfill | Không có kiểu thêm LSI sau |

**Giới hạn 10 GB** cần diễn giải chính xác: chỉ áp khi bảng có ít nhất một **LSI**, tính tổng base table items và projected index entries cho **một PK value**. Một single-table design **không có LSI** không chịu cùng giới hạn item collection cố định đó; vẫn chịu giới hạn size/throughput/quota khác.

### 6.3. Sparse GSI

GSI chỉ chứa item nếu index key attributes cần thiết có mặt đúng kiểu. Điều này cho phép **sparse indexing**:

~~~text
COURSE c1 DRAFT:
  no GSI2PK, no GSI2SK  -> not indexed

COURSE c2 PUBLISHED:
  GSI2PK=TENANT#t1#CATEGORY#java
  GSI2SK=PUBLISHED#2026-11-20T03:00:00Z#COURSE#c2
  -> indexed
~~~

Một `Query` GSI2 theo category chỉ xem courses có key và phù hợp category. Ưu điểm: không cần FilterExpression qua toàn bộ courses/drafts. Nhược điểm: phải cập nhật keys **khi status/category thay đổi**, quản trị consistency/propagation.

### 6.4. Index overloading

**Overloading** là dùng cùng một GSI cho nhiều loại entity và access patterns bằng key namespace khác nhau:

~~~text
GSI1PK=TENANT#t1#USER#u1
GSI1SK=ENROLLMENT#c1

GSI1PK=TENANT#t1#INSTRUCTOR#u2
GSI1SK=COURSE#c1

GSI1PK=TENANT#t1#COUPON#abc
GSI1SK=REDEMPTION#u3
~~~

Điều kiện: keys có phân vùng namespace rõ, không trộn item types trong một Query, projection và capacity cost đã tính. Đừng overload index chỉ để dùng hết ít GSI nhất — làm mã khó hiểu, tăng coupling và khó phân quyền.

### 6.5. Projection và write amplification

GSI projection thường chọn:

- `KEYS_ONLY`: ít storage/write hơn; cần đọc base item nếu thiếu fields.
- `INCLUDE`: chỉ thêm vài attributes cần cho truy vấn.
- `ALL`: copy toàn bộ attributes vào index entry; thuận tiện nhưng có thể đắt và tăng write amplification.

Với AP5 dashboard, có thể project `courseId`, `status`, `enrolledAt`, `titleSnapshot`. Với AP7 catalog, project `title`, `category`, `publishedAt`. Chọn dựa vào **response contract**, không chọn `ALL` theo phản xạ.

### 6.6. GSI hot partitions cũng có thể gây throttling

Một GSI2 key kiểu `TENANT#t1#CATEGORY#java` có thể quá nóng nếu toàn hệ thống truy vấn/ghi danh mục Java. Dù base PKs đã phân bố tốt, **GSI partition key** có thể thành hotspot riêng.

Với workload lớn, cân nhắc key sharding:

~~~text
GSI2PK=TENANT#t1#CATEGORY#java#SHARD#00
GSI2PK=TENANT#t1#CATEGORY#java#SHARD#01
...
GSI2PK=TENANT#t1#CATEGORY#java#SHARD#0f
~~~

Nhược điểm: catalog API phải **Query nhiều shards rồi merge-sort/paginate**, phức tạp hơn và tăng requests. Chỉ shard sau khi đã đo traffic/skew và cân nhắc cache.


## 7. GetItem, Query, Scan và phân trang

### 7.1. Ánh xạ mọi access pattern sang API

| Access pattern | API | Khóa truy vấn | Index |
|---|---|---|---|
| AP1 — hồ sơ user | `GetItem` | `PK=TENANT#t1#USER#u1, SK=PROFILE` | Base |
| AP2 — metadata course | `GetItem` | `PK=TENANT#t1#COURSE#c1, SK=META` | Base |
| AP3 — lessons theo course | `Query` | `PK=:course AND begins_with(SK,"LESSON#")` | Base |
| AP4 — enrollments theo course | `Query` | `PK=:course AND begins_with(SK,"ENROLLMENT#")` | Base |
| AP5 — enrollments theo user | `Query` | `GSI1PK=:user AND begins_with(GSI1SK,"ENROLLMENT#")` | GSI1 |
| AP6 — kiểm tra user enrolled? | `GetItem` | `PK=:course, SK=ENROLLMENT#userId` | Base |
| AP7 — published catalog | `Query` | `GSI2PK=:category`, sort key phù hợp | GSI2 |

**Nếu truy vấn chỉ biết email nhưng schema không có email lookup**, DynamoDB không tự tìm bằng JOIN hay một Query theo attribute thường. Phải bổ sung access pattern/index hoặc thay hợp đồng API để có user ID.

### 7.2. GetItem với composite key

Kiểm tra `u1` đã đăng ký course `c1`:

~~~text
PK = TENANT#t1#COURSE#c1
SK = ENROLLMENT#u1
~~~

`GetItem` là direct key access. Khi cần đọc kết quả ghi vừa hoàn thành trên base table trong cùng Region, có thể yêu cầu `ConsistentRead=true`. Không áp `ConsistentRead` cho GSI.

### 7.3. Query cần partition key equality

~~~text
KeyConditionExpression:
    PK = :pk AND begins_with(SK, :prefix)

:pk     = "TENANT#t1#COURSE#c1"
:prefix = "LESSON#"
~~~

DynamoDB hỗ trợ equality trên PK, cộng điều kiện SK như `begins_with`, `BETWEEN` hoặc khoảng so sánh. `ScanIndexForward=false` cho thứ tự SK giảm dần.

**Không thể Query chỉ với `begins_with(SK,"LESSON#")` mà bỏ PK equality** trong cùng index. Nếu cần tất cả lessons trên mọi course, cần index/access pattern mới hoặc batch analytics.

### 7.4. FilterExpression không tiết kiệm dung lượng đã đọc

Giả sử course có 20.000 enrollments nhưng chỉ 300 active:

~~~text
KeyCondition:
    PK = :course AND begins_with(SK, "ENROLLMENT#")

FilterExpression:
    #status = :active
~~~

`FilterExpression` được áp **sau khi DynamoDB đọc items thỏa key condition**. Nó không làm giảm read capacity của dữ liệu đã đọc. `ProjectionExpression` giảm attributes trả qua network nhưng không tự làm DynamoDB tính capacity theo kích thước response nhỏ hơn.

Nếu cần truy vấn active enrollments ở tải cao, thiết kế status vào **SK hoặc sparse GSI key**, ví dụ:

~~~text
GSI3PK=TENANT#t1#COURSE#c1#STATUS#ACTIVE
GSI3SK=ENROLLED#2026-11-20T03:05:00Z#USER#u1
~~~

Mỗi GSI thêm chi phí write/storage và có thể tạo hotspot, nên cần đo trước khi thêm.

### 7.5. Giới hạn 1 MB mỗi lần gọi Query

`Query` đọc tối đa khoảng **1 MB dữ liệu** mỗi API request trước khi áp filter/projection, hoặc dừng sớm theo `Limit`. Khi response có `LastEvaluatedKey`, client dùng nó làm `ExclusiveStartKey` của lần tiếp theo.

~~~mermaid
flowchart TD
    R[Query PK + SK] --> P[Đọc tối đa 1 MB hoặc Limit]
    P --> F[Apply FilterExpression nếu có]
    F --> O[Return Items + LastEvaluatedKey]
    O --> D{LastEvaluatedKey rỗng?}
    D -->|Không| N[Query tiếp dùng ExclusiveStartKey]
    N --> P
    D -->|Có| E[Kết thúc]
~~~

**Một page Items rỗng không nhất thiết là kết thúc**: các items được đọc có thể đã bị filter loại nhưng LastEvaluatedKey còn. Ngược lại LastEvaluatedKey xuất hiện chưa bảo đảm page tiếp theo có result hợp lệ; chỉ dừng khi hết token.

### 7.6. Limit và CLI pagination

- `Limit=20` giới hạn số items **được đánh giá**, không đảm bảo trả đủ 20 nếu FilterExpression loại bớt.
- AWS CLI có pagination riêng: `--max-items` ở cấp CLI khác `--limit` ở API.
- Để minh họa một page ở API, có thể dùng `--no-paginate --limit 20` và kiểm tra `LastEvaluatedKey`.
- Backend nên cung cấp **opaque page token** sau khi đã xác thực tenant, không để client sửa raw DynamoDB key tùy ý.
- Query trên nhiều pages không tự tạo **một snapshot transaction** xuyên toàn bộ pages, dù từng page có thể dùng strong consistency.

### 7.7. Khi nào Scan phù hợp?

`Scan` có thể dùng trong **small sandbox**, migration có giới hạn throughput, offline maintenance hoặc export/analytics phù hợp. Không dùng Scan nóng mỗi API request để tìm theo field không phải key. Một Query với FilterExpression có thể cũng rất đắt nếu partition đó có nhiều items; hãy theo dõi `ScannedCount` vs `Count`.

## 8. Consistency, điều kiện ghi và transactions

### 8.1. Consistency khác nhau theo nguồn

| Đường đọc | Eventual | Strong |
|---|---|---|
| GetItem base | Có | Có |
| Query base | Có | Có |
| Query LSI | Có | Có |
| Query GSI | Có | **Không** |
| DynamoDB Streams | Theo stream semantics | Không phải strong read query |

Ngay sau Put enrollment, base GetItem strong có thể thấy item đã commit, còn GSI1 query theo user chưa thấy vì index được cập nhật **bất đồng bộ**. Giao diện cần biết điều này: một GSI chưa có record không chứng minh enrollment chưa được tạo.

### 8.2. Conditional Put ngăn ghi trùng

Dùng primary key duy nhất:

~~~text
PK=TENANT#t1#COURSE#c1
SK=ENROLLMENT#u1
~~~

`PutItem` mặc định có thể overwrite item cùng key. Chặn bằng condition:

~~~text
attribute_not_exists(PK) AND attribute_not_exists(SK)
~~~

Khi item đã tồn tại, DynamoDB trả `ConditionalCheckFailedException`. Ứng dụng phân biệt **duplicate registration** với **lỗi hạ tầng**; không retry vô hạn lỗi điều kiện.

### 8.3. Optimistic locking

Một enrollment item có `version=4`. Client update với:

~~~text
ConditionExpression: #version = :expected
UpdateExpression: SET #status = :newStatus, #version = :next
~~~

Nếu another writer đã cập nhật thành version 5, condition fail và ngăn **lost update**. Với transaction concurrency cao, cần backoff/jitter, cách trình bày conflict rõ cho người dùng.

### 8.4. Transaction cho nhiều items

Đăng ký một học viên có thể cần:

1. Xác nhận USER PROFILE tồn tại.
2. Xác nhận COURSE META còn mở.
3. Put ENROLLMENT mới với condition chưa tồn tại.
4. Update COURSE STATS enrollment count.

~~~mermaid
flowchart TD
    C[Enroll command] --> TX[TransactWriteItems]
    TX --> U[ConditionCheck user exists]
    TX --> M[ConditionCheck course open]
    TX --> E[Put new enrollment if not exists]
    TX --> S[Update course stats]
    U --> ALL{All succeed?}
    M --> ALL
    E --> ALL
    S --> ALL
    ALL -->|Yes| COMMIT[Atomic commit]
    ALL -->|No| STOP[No partial commit]
~~~

`TransactWriteItems` hỗ trợ tối đa **100 write actions**, tổng **4 MB**, trên tối đa 100 distinct items thuộc cùng account và Region. Các actions gồm `Put`, `Update`, `Delete` và `ConditionCheck`; **không được tác động hai lần cùng một item trong cùng transaction**.

**Quan trọng:** cần tạo `STATS` item khi tạo course. Một counter nóng có thể gây transaction conflicts khi course rất phổ biến; có thể cần sharded counters/đếm bất đồng bộ thay vì tăng một item duy nhất mỗi enrollment.

### 8.5. Transaction không có nghĩa end-to-end exactly-once

- Trong cùng Region, DynamoDB transaction có nguyên tắc **all-or-nothing** cho items được chỉ định.
- Network timeout sau commit có thể khiến client **không biết** transaction thành công; dùng idempotency key/đối soát state.
- `ClientRequestToken` làm identical transactional requests idempotent trong cửa sổ thời gian do AWS định nghĩa.
- Gửi email/nhắn tin sau commit không thuộc DynamoDB transaction; dùng outbox/Streams/event workflow.
- Transaction thường tiêu thụ nhiều capacity hơn các operations thường, cần benchmark.

### 8.6. Dual-edge cần atomicity

Nếu bạn biểu diễn một quan hệ thành hai items:

~~~text
PK=COURSE#c1 SK=STUDENT#u1
PK=STUDENT#u1 SK=COURSE#c1
~~~

thì xóa hoặc tạo quan hệ cần update **cả hai**, nếu không có thể có một edge mồ côi. Dùng transaction hoặc chọn **một edge + GSI** khi consistency requirements cho phép.

### 8.7. TTL là xóa bất đồng bộ

DynamoDB TTL dùng một attribute **Unix epoch timestamp giây**. Expired items được dọn **bất đồng bộ**, không đúng từng giây:

- Không dùng TTL làm cơ chế duy nhất để khóa quyền vào đúng thời điểm;
- Backend kiểm tra `expiresAt` khi đọc/ghi cần giới hạn thời gian chặt;
- TTL phù hợp dọn session/invite/temporary data;
- TTL deletes có thể đi vào Streams theo semantics AWS;
- Khi item thật sự xóa, GSI entries được dọn theo cơ chế dịch vụ.

### 8.8. Global Tables: đừng khẳng định mọi cross-Region read đều eventual

DynamoDB Global Tables có các chế độ như **multi-Region eventual consistency (MREC)** và **multi-Region strong consistency (MRSC)** trên Region sets/tính năng đủ điều kiện. Tuy nhiên **GSI vẫn eventual consistency**, và một DynamoDB transaction **không trở thành global atomic transaction ở mọi Region**. Chọn chế độ dựa vào RPO/RTO/latency, quotas/availability và khả năng giải quyết conflicting writes.

## 9. Hot partitions và write sharding

### 9.1. Hot PK tạo ra bottleneck

Nếu mọi registration của một khóa học viral đều ghi:

~~~text
PK=TENANT#t1#COURSE#viral
SK=ENROLLMENT#userId
~~~

thì lưu lượng ghi tập trung vào logical item collection. DynamoDB có adaptive capacity và có thể split hot collections khi điều kiện cho phép, nhưng **không xóa mọi giới hạn vật lý/quota/hot key**.

AWS mô tả thiết kế mỗi physical partition ở mức tối đa khoảng **1.000 write capacity units/s** và **3.000 read capacity units/s**. Không hiểu đây là một giới hạn cứng áp dụng giống nhau cho mọi logical partition key: adaptive capacity, item isolation/splitting, capacity mode và traffic pattern đều ảnh hưởng.

### 9.2. Quan sát hotspot

Dấu hiệu:

- `ThrottledRequests`/`WriteKeyRangeThroughputThrottleEvents` tăng;
- Một số tenant/course IDs có latency lớn hơn hẳn;
- GSI2 có key `CATEGORY#java` nhận nhiều writes/reads hơn keys khác;
- Provisioned table còn capacity nhưng một key range vẫn bị throttle;
- Một số items/counters bị tranh chấp transaction cao.

Theo dõi CloudWatch metrics, `ConsumedReadCapacityUnits`/`ConsumedWriteCapacityUnits` và Contributor Insights khi có policy cho phép; **không đưa PII vào partition keys/diagnostic dashboards**.

### 9.3. Shard enrollments theo course khi cần

Một cách sau khi đo đủ tải:

~~~text
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#00
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#01
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#02
...
SK=ENROLLMENT#u1

shard = hash(userId) mod shardCount
~~~

Kiểm tra một enrollment có cả courseId/userId → tính shard và `GetItem`. Nhưng liệt kê toàn bộ enrollments theo course sẽ phải **Query nhiều shards rồi merge/paginate**. Đây là đánh đổi chủ động; không shard mọi entity chỉ vì “DynamoDB cần phân vùng”.

Khi thay số shards, cần giữ shard version/route metadata, vì những items cũ vẫn nằm ở shards cũ. Thêm GSI/replica hoặc cache có thể là phương án đơn giản hơn.

### 9.4. LSI 10 GB và hot item collections

Khi một table có ít nhất một **LSI**, item collection theo một PK bị giới hạn **10 GB**, tính cả base items và projected LSI entries. Bảng **không có LSI** không chịu cùng ràng buộc item collection 10 GB đó; vẫn có item-size/throughput/quota khác.

Tránh dùng LSI cho item collections **unbounded** (ví dụ một course có hàng chục triệu enrollments), trừ khi đã chứng minh growth ceiling. Dùng GSI, sharding hoặc archival nếu thích hợp.

### 9.5. Hot GSI cũng làm writes chậm

Một index `GSI3PK=TENANT#t1#STATUS#PENDING` nhận mọi event của tenant lớn có thể thành hotspot. GSI write throttling có thể ảnh hưởng các base-table writes. Kiểm tra cardinality, skew, projection, replicated writes, traffic burst và khả năng dùng cache/alternate keys trước khi thêm GSI.


## 10. Multi-tenant isolation, IAM và PII

### 10.1. Tên partition key có namespace tenant

Trong ví dụ:

~~~text
Base PK  = TENANT#t1#COURSE#c1
GSI1PK   = TENANT#t1#USER#u1
GSI2PK   = TENANT#t1#CATEGORY#java
~~~

Thiết kế này giúp API dễ kiểm soát `tenantId` đầu vào và giới hạn truy vấn ở mức tenant. Nhưng **tiền tố không tự ngăn cross-tenant data access** nếu backend tin giá trị tenant do caller tự gửi.

Một luồng đúng:

~~~text
HTTP request /tenants/t1/courses/c1/students
  -> Verify identity/access token
  -> Resolve tenant membership từ nguồn tin cậy
  -> Kiểm tra caller có quyền quản trị course c1
  -> Xây PK tenant t1 từ server-side context
  -> Query DynamoDB với key hợp lệ
  -> Chỉ trả fields được phép qua DTO
~~~

**Không ghép tenant key trực tiếp từ query parameter chưa xác minh**.

### 10.2. DynamoDB IAM condition dynamodb:LeadingKeys

DynamoDB có IAM condition key `dynamodb:LeadingKeys` để giới hạn **partition key values** mà một principal được phép truy cập. Cần dùng modifier `ForAllValues` theo hướng dẫn AWS.

Ví dụ **khái niệm** khi IAM principal tag `TenantId` được IAM/identity provider tin cậy cấp:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TenantScopedGetAndQuery",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:Query"],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/LearningCore",
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/LearningCore/index/*"
      ],
      "Condition": {
        "ForAllValues:StringLike": {
          "dynamodb:LeadingKeys": "TENANT#${aws:PrincipalTag/TenantId}#*"
        }
      }
    }
  ]
}
~~~

Phải **kiểm thử policy bằng principal thật** và negative tests: tenant t1 không được Query tenant t2 trên base **hoặc GSI**, dù app client biết IDs. Điều kiện này không thay authorization cấp user/resource.

Chú ý: `LeadingKeys` áp vào leading partition key; **mọi GSI partition key** được role truy vấn cũng phải tuân thủ tenant prefix. Nếu GSI dùng shared key `STATUS#PENDING` không chứa tenant, chính sách ví dụ trên có thể chặn pattern đó — đừng mở wildcard IAM tùy tiện, hãy thiết kế index/security lại.

### 10.3. IAM identity khác application authorization

AWS IAM xác định role có được gọi `dynamodb:Query`/`PutItem` trên table/index hay không. Backend vẫn phải kiểm tra người dùng được đọc enrollment của course nào, có thuộc trường và được giao quyền instructor không.

Cũng cần bảo vệ **table exports, PITR backups, Streams subscribers, CloudWatch metrics/logs**. Một consumer Streams được quyền đọc events nhiều entity types có thể thấy dữ liệu mà các API thông thường đã được lọc.

### 10.4. Keys và attributes có thể chứa PII

Không đưa mật khẩu, token, email/phone thô hoặc thông tin thanh toán vào `PK`/`SK`. Keys thường xuất hiện trong query logs, traces, CLI outputs, backups và một số công cụ giám sát.

Dùng opaque IDs và phân loại PII; chỉ project attributes cần thiết vào GSI. Nếu cần lookup theo email, cân nhắc **normalized email hash/HMAC** làm index key với key management/lookup contract phù hợp; hashing đơn giản không tự bảo vệ trước dictionary attacks trên dữ liệu có entropy thấp.

### 10.5. Encryption, KMS và ranh giới table

DynamoDB hỗ trợ encryption at rest; các lựa chọn AWS-owned/AWS-managed/customer-managed keys cần đánh giá theo compliance. Single-table lưu nhiều entities cùng resource table và có chung nhiều chính sách vận hành. Nếu một tenant bắt buộc dùng KMS key hoặc retention độc lập, **table-per-tenant/account-per-tenant** có thể là lựa chọn phù hợp hơn.

## 11. Cost model của single-table design

### 11.1. Capacity theo item size

Các quy tắc nền tảng về DynamoDB capacity:

- Write capacity được tính theo **đơn vị mỗi 1 KiB item** (làm tròn lên), và giao dịch/GSI có thêm consumption.
- Strongly consistent reads được tính theo **đơn vị mỗi 4 KiB item** (làm tròn lên).
- Eventually consistent reads thường tiêu thụ **một nửa read capacity units** so với strong reads cho cùng dữ liệu.
- Transactional read/write có thể tốn nhiều capacity hơn thao tác thường.
- GSI reads được tính theo **index entry size**, index writes và lưu trữ gây overhead.
- On-demand/provisioned, adaptive capacity, burst và table class ảnh hưởng hiệu quả chi phí.

Đừng chỉ đếm số thuộc tính trả về: `ProjectionExpression` và `FilterExpression` **không** tự làm nhỏ dữ liệu DynamoDB đọc để tính read units trên base Query.

### 11.2. GSI projection là trade-off chi phí

Giả sử course META có item 40 KiB, nhưng catalog chỉ cần `title`/`category`/`publishedAt`. GSI2 `ProjectionType=ALL` lưu và update nhiều hơn `INCLUDE` các fields này. Chọn projection dựa vào **API response contract**.

| Lựa chọn | Ưu điểm | Nhược điểm |
|---|---|---|
| `KEYS_ONLY` | Index entry nhỏ | Có thể cần thêm base-table gets |
| `INCLUDE` | Cân bằng query và lưu trữ | Phải chọn fields trước |
| `ALL` | Query trả đầy đủ fields đã lưu | Tốn GSI storage/write; PII có thể bị index hóa quá mức |

**Đọc dữ liệu từ GSI không tự fetch các attributes chưa được project từ base table** như cách LSI có thể hoạt động. Khi API cần field không có trong GSI projection, ứng dụng phải truy vấn base items riêng (hoặc thay projection).

### 11.3. Một edge + GSI hay hai base edges?

| Mô hình | Read course→users | Read user→courses | Writes | Consistency |
|---|---|---|---|---|
| Một edge + GSI1 | Base Query | GSI1 Query | Base Put + GSI maintenance | GSI eventual |
| Hai base edge items | Base Query | Base Query | Hai Puts, thường cần transaction | Có thể strong ở cả hai hướng |
| Embed list courseIds vào USER PROFILE | Khó đọc users của course | Một GetItem | Update list lớn | Giới hạn 400 KiB và contention |
| RDBMS join table | SQL JOIN/index | SQL JOIN/index | Relational INSERT | SQL transactions/FK |

Nếu dashboard chấp nhận index propagation ngắn, **một edge + GSI1** thường là giải pháp hợp lý; nếu dữ liệu quan hệ hai chiều phải lập tức strong consistent và access pattern cho phép, dual-edge có thể phù hợp dù đắt hơn. Chọn theo yêu cầu, không có mẫu đúng tuyệt đối.

### 11.4. Chi phí không giảm chỉ vì dùng một bảng

Một table với 7 GSIs, GSI projections rộng, transactions cho mọi change và shared streams có thể đắt hơn hai hoặc ba tables được tối ưu. Tính tổng:

- Base table read/write request units;
- GSI storage + read/write throughput;
- Backfill khi tạo index;
- Transactions, conditional errors và retries;
- Global Tables replication theo Region/mode;
- Export/PITR/backups, Streams, Lambda consumers;
- CloudWatch/Contributor Insights, KMS và network;
- On-demand vs provisioned capacity configuration.

Dùng AWS Pricing Calculator và billing tags theo workload/tenant khi có chiến lược cost allocation. Không gắn số tiền USD cố định trong bài vì giá thay đổi theo Region và thời điểm.

## 12. Streams, TTL, backups và schema migration

### 12.1. Streams của bảng nhiều loại entity

Một table `LearningCore` có thể phát DynamoDB Streams records cho nhiều entity types:

~~~mermaid
flowchart TD
    TABLE[(LearningCore Stream)] --> ROUTER[Lambda / consumer]
    ROUTER -->|entityType USER| P[Profile sync]
    ROUTER -->|entityType COURSE| S[Search index]
    ROUTER -->|entityType ENROLLMENT| A[Analytics]
    ROUTER -->|entityType LESSON| C[Cache invalidation]
~~~

Stream event consumers cần:

- Kiểm tra `entityType`/key prefix và validate schema version;
- Xử lý **at-least-once**/duplicates/poison-pill records phù hợp;
- Không giả định mọi consumer chỉ nhận changes của một loại entity;
- Có IAM/PII controls và destination failure handling;
- Phân biệt stream retention với backup/long-term audit.

Với multi-table, có thể quản lý Streams riêng từng table nếu các team cần cô lập vận hành.

### 12.2. TTL không thay business-time constraints

Nếu có `expiresAt` (Unix epoch giây):

~~~json
{
  "PK": "TENANT#t1#INVITE#inv1",
  "SK": "META",
  "entityType": "INVITATION",
  "expiresAt": 1795143600
}
~~~

DynamoDB TTL có thể xóa item **sau** lúc timestamp đã hết hạn, không đúng chính xác thời điểm đó. Backend phải kiểm tra `expiresAt` với giờ hiện tại khi xác minh invitation/token. TTL giúp dọn storage; không phải quyền truy cập thời gian thực.

### 12.3. PITR và restore

Backups/PITR trong single-table hoạt động ở **table scope**. Nếu vô tình xóa enrollment một course, bạn có thể:

1. Restore backup sang **table mới** ở môi trường kiểm soát;
2. Xác định item keys cần khôi phục;
3. Đối chiếu với dữ liệu production mới nhất;
4. Reapply các items một cách idempotent/conditional;
5. Ghi audit và dọn temporary table theo policy.

**Không restore đè production table** mà chưa đánh giá mất thay đổi của entities khác. Đừng coi có Streams hay GSI là đã có giải pháp khôi phục độc lập.

### 12.4. Migration từ RDBMS/multi-table

~~~mermaid
flowchart TD
    OLD[Legacy tables] --> AP[Finalize access patterns]
    AP --> NEW[Create new DynamoDB table + GSIs]
    NEW --> BACKFILL[Backfill with validation]
    BACKFILL --> DUAL[CDC / dual-write idempotent]
    DUAL --> VERIFY[Reconcile counts and invariants]
    VERIFY --> CANARY[Canary switch reads]
    CANARY --> CUT[Switch writes and monitor]
    CUT --> CLEAN[Retire legacy path after rollback window]
~~~

Các rủi ro:

- Duplicate edges/missing user or course;
- Sai tenant namespace và key collisions;
- Sort key mất thứ tự khi không zero-pad;
- GSI propagation/backfill chưa hoàn tất;
- Index write pressure khi bulk migration;
- Query pagination/FilterExpression bất ngờ;
- Old/new services cùng ghi nhưng schema contract khác;
- Streams consumers nhận cả records backfill và records business.

### 12.5. Schema evolution

DynamoDB không hỗ trợ update **PK/SK** của item tại chỗ như ordinary non-key attributes. Đổi khóa từ:

~~~text
PK=TENANT#t1#COURSE#c1
SK=ENROLLMENT#u1
~~~

sang:

~~~text
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#03
SK=ENROLLMENT#u1
~~~

đòi tạo **item mới** và xóa item cũ; muốn atomic trong cùng Region/table và không vượt giới hạn cần transactions. Với migration lớn, cần dual-read/dual-write hoặc versioned routing trong cửa sổ chuyển đổi.

Có thể thêm attribute `schemaVersion` để versioned payload. Cố gắng giữ ổn định PK/SK contract vì chúng quyết định toàn bộ access patterns và IAM tenant policy.

### 12.6. Khi nào nên chọn multi-table hoặc hybrid?

Chọn **multi-table/hybrid** khi:

- Entities độc lập, gần như không truy vấn chung;
- Quyền IAM/KMS/backup/PITR/TTL/Streams khác biệt mạnh;
- Trách nhiệm vận hành theo team tách biệt;
- Có cơ sở dữ liệu giao dịch cần phức tạp JOIN/reporting;
- Tenant isolation bắt buộc table/account-level;
- STD dẫn đến quá nhiều GSI overloading và code khó bảo trì;
- Không có lợi ích locality rõ ràng so với chi phí thay đổi/đào tạo.

**Single-table design là công cụ tối ưu hóa theo access patterns**, không phải mục tiêu “càng ít bảng càng tốt”.


## 13. Thực hành 1 — Quan sát schema và index bằng AWS CLI (chỉ đọc)

> **Phạm vi lab bắt buộc: chỉ đọc cấu hình** trong account/Region sandbox được cấp. Bạn cần AWS CLI v2, IAM credentials hợp lệ và các quyền như `dynamodb:ListTables`, `dynamodb:DescribeTable`, `dynamodb:DescribeTimeToLive`, `dynamodb:DescribeContinuousBackups` và CloudWatch read permissions tùy bài. Không tạo bảng, không quét dữ liệu người dùng và không đọc dữ liệu production.

### 13.1. Xác minh account, profile và Region

Bash/AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

Nếu CloudShell đã có credentials được quản lý bởi phiên đăng nhập và không có profile `aws-lab-dev`, bỏ profile variable/argument liên quan. Kiểm tra account/ARN trước khi thao tác.

### 13.2. Liệt kê tên bảng

~~~bash
aws dynamodb list-tables \
  --region "$REGION" \
  --query 'TableNames' \
  --output table
~~~

Kết quả rỗng có thể do sai account/Region hoặc chưa có table; đừng tạo table production chỉ để học. `ListTables` có pagination, AWS CLI có paginator theo phiên bản. Mọi resource names trong bài là placeholder.

### 13.3. Xem table primary key và GSIs

~~~bash
TABLE=LearningCoreSandbox

aws dynamodb describe-table \
  --table-name "$TABLE" \
  --region "$REGION" \
  --query 'Table.{Name:TableName,Status:TableStatus,BillingMode:BillingModeSummary.BillingMode,KeySchema:KeySchema,AttributeDefinitions:AttributeDefinitions,GSIs:GlobalSecondaryIndexes[].{Name:IndexName,Status:IndexStatus,Keys:KeySchema,Projection:Projection},LSIs:LocalSecondaryIndexes[].{Name:IndexName,Keys:KeySchema,Projection:Projection},StreamSpecification:StreamSpecification}' \
  --output json
~~~

Cần đối chiếu:

| Thuộc tính | Câu hỏi |
|---|---|
| `KeySchema` | Có base PK (HASH), SK (RANGE) đúng String không? |
| `AttributeDefinitions` | Những key/index attributes định nghĩa kiểu gì? |
| `GlobalSecondaryIndexes` | GSI1/GSI2 có tồn tại, `IndexStatus=ACTIVE` chưa? |
| `Projection` | `KEYS_ONLY`/`INCLUDE`/`ALL`, có đúng fields API cần? |
| `LocalSecondaryIndexes` | Có LSI khiến item collection chịu giới hạn 10 GB không? |
| `BillingMode` | On-demand hay provisioned? |
| `StreamSpecification` | Stream có được bật/loại image phù hợp? |

**Lưu ý:** `AttributeDefinitions` trong `DescribeTable` không phải “toàn bộ schema fields” của table. DynamoDB yêu cầu định nghĩa **key attributes** của table/index; các non-key attributes thay đổi theo từng item mà không cần khai báo trước.

### 13.4. Kiểm tra TTL

~~~bash
aws dynamodb describe-time-to-live \
  --table-name "$TABLE" \
  --region "$REGION" \
  --output json
~~~

Nếu có `TimeToLiveStatus=ENABLED`, kiểm tra attribute name và format epoch **giây** ở ứng dụng. Không hiểu TTL enabled nghĩa mọi expired item đã bị xóa chính xác lúc hết hạn.

### 13.5. Kiểm tra PITR

~~~bash
aws dynamodb describe-continuous-backups \
  --table-name "$TABLE" \
  --region "$REGION" \
  --query 'ContinuousBackupsDescription.{BackupsStatus:ContinuousBackupsStatus,PITR:PointInTimeRecoveryDescription}' \
  --output json
~~~

Lệnh chỉ xem config; không restore/sửa bảng. Với single-table, cần biết PITR bảo vệ **toàn table**, không riêng từng loại entity.

### 13.6. Kiểm tra CloudWatch metrics cho table

Ví dụ đọc mức tiêu thụ read capacity trong 30 phút qua GNU date trên AWS CloudShell:

~~~bash
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedReadCapacityUnits \
  --dimensions "Name=TableName,Value=$TABLE" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Sum \
  --region "$REGION" \
  --output json
~~~

Đơn vị và statistic của metric phải đọc theo định nghĩa CloudWatch; `Sum` trong một bucket thời gian không phải QPS. Nếu dùng Windows PowerShell, thay `date -d` bằng cách tạo UTC ISO timestamps bằng `Get-Date`.

### 13.7. Bảng ghi nhận

| Điều kiểm tra | Kết quả lab | Đánh giá |
|---|---|---|
| Base PK/SK | ... | Có hỗ trợ GetItem/Query patterns? |
| GSI1 keys/projection | ... | Hỗ trợ user→enrollments? |
| GSI2 keys/projection | ... | Hỗ trợ published catalog? |
| LSI count | ... | Có 10 GB item collection constraint không? |
| Billing mode | ... | Phù hợp tải và ngân sách? |
| TTL | ... | Không dựa vào xóa chính xác? |
| PITR | ... | Có khôi phục khi mất dữ liệu? |
| Streams | ... | Consumers đọc nhiều entity types? |
| Capacity metrics | ... | Có cần load test/hot-key investigation? |

## 14. Thực hành 2 — Query theo access patterns (sandbox read-only)

> Phần này có thể **đọc dữ liệu item**. Chỉ chạy trên `LearningCoreSandbox` của chính bạn với dữ liệu **giả**, không tự chạy `GetItem`/`Query` trên dữ liệu cá nhân thật. Những typed JSON values dưới đây là định dạng **AWS DynamoDB AttributeValue**, khác JSON logic ở mục 4.

### 14.1. GetItem — một course

~~~bash
aws dynamodb get-item \
  --table-name "$TABLE" \
  --key '{"PK":{"S":"TENANT#t1#COURSE#c1"},"SK":{"S":"META"}}' \
  --projection-expression 'PK,SK,#title,#visibility' \
  --expression-attribute-names '{"#title":"title","#visibility":"visibility"}' \
  --consistent-read \
  --region "$REGION" \
  --output json
~~~

Nếu table chưa có test item, response không có `Item`. Đó **không phải lỗi API**; chỉ là chưa tìm thấy khóa. `--consistent-read` được phép trên base table; không dùng cho GSI.

### 14.2. Query — lessons cùng course theo thứ tự

~~~bash
aws dynamodb query \
  --table-name "$TABLE" \
  --key-condition-expression 'PK = :pk AND begins_with(SK, :prefix)' \
  --expression-attribute-values '{":pk":{"S":"TENANT#t1#COURSE#c1"},":prefix":{"S":"LESSON#"}}' \
  --projection-expression 'PK,SK,#title' \
  --expression-attribute-names '{"#title":"title"}' \
  --no-paginate \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --region "$REGION" \
  --output json
~~~

Phân tích `Count`, `ScannedCount`, `LastEvaluatedKey` và `ConsumedCapacity`. `--limit 20` ở cấp API là số **items evaluated**, không bảo đảm trả 20. Nếu có LastEvaluatedKey, cần dùng giá trị đó cho `--exclusive-start-key` ở request tiếp theo.

### 14.3. Query GSI1 — enrollments theo user

~~~bash
aws dynamodb query \
  --table-name "$TABLE" \
  --index-name GSI1 \
  --key-condition-expression 'GSI1PK = :user AND begins_with(GSI1SK, :kind)' \
  --expression-attribute-values '{":user":{"S":"TENANT#t1#USER#u1"},":kind":{"S":"ENROLLMENT#"}}' \
  --no-paginate \
  --limit 20 \
  --return-consumed-capacity INDEXES \
  --region "$REGION" \
  --output json
~~~

**Không thêm `--consistent-read` vào GSI Query**. Nếu enrollment vừa tạo chưa hiển thị, phải kiểm tra GSI eventual propagation; không tự ghi trùng edge. `GSI1` cần được định nghĩa và active, projected fields đủ dùng.

### 14.4. Query GSI2 — catalog theo category

~~~bash
aws dynamodb query \
  --table-name "$TABLE" \
  --index-name GSI2 \
  --key-condition-expression 'GSI2PK = :category AND begins_with(GSI2SK, :published)' \
  --expression-attribute-values '{":category":{"S":"TENANT#t1#CATEGORY#java"},":published":{"S":"PUBLISHED#"}}' \
  --scan-index-forward false \
  --no-paginate \
  --limit 20 \
  --region "$REGION" \
  --output json
~~~

Vì sort key bắt đầu với `PUBLISHED#<timestamp>` dạng ISO-8601 UTC thống nhất, `--scan-index-forward false` lấy các courses mới hơn trước trong nhóm category. Nếu có nhiều categories hoặc status, cần thiết kế đúng key contract, không dựa vào FilterExpression.

### 14.5. Không Scan vì thiếu index

Không chạy kiểu:

~~~bash
# ANTI-PATTERN cho API hot path; không chạy trên production
aws dynamodb scan \
  --table-name "$TABLE" \
  --filter-expression 'email = :email' \
  --expression-attribute-values '{":email":{"S":"someone@example.test"}}'
~~~

Scan đọc qua các items rồi mới filter, gây chi phí/latency lớn; còn có rủi ro quét thông tin người dùng ngoài phạm vi nếu IAM quá rộng. Nếu cần email lookup thường xuyên, thêm index hoặc dịch vụ nhận dạng phù hợp, kết hợp data protection.

## 15. Thực hành 3 — Ghi bằng điều kiện/transaction (tùy chọn, có tác động)

> **Không bắt buộc, có tác động thật.** Chỉ thử trên bảng riêng có tên `LearningCoreSandbox`, tenant IDs giả, có approval, budget và cleanup plan. Không chạy với thông tin học viên thật. Worker hiện tại **không thực thi bất kỳ lệnh AWS nào**; các lệnh dưới đây chỉ là ví dụ dạy học.

### 15.1. Tạo một enrollment với PutItem conditional

~~~bash
# CHỈ CHẠY trên table sandbox do bạn sở hữu.
aws dynamodb put-item \
  --table-name LearningCoreSandbox \
  --item '{"PK":{"S":"TENANT#t1#COURSE#c1"},"SK":{"S":"ENROLLMENT#u1"},"entityType":{"S":"ENROLLMENT"},"userId":{"S":"u1"},"courseId":{"S":"c1"},"status":{"S":"ACTIVE"},"GSI1PK":{"S":"TENANT#t1#USER#u1"},"GSI1SK":{"S":"ENROLLMENT#c1"}}' \
  --condition-expression 'attribute_not_exists(PK) AND attribute_not_exists(SK)' \
  --return-consumed-capacity TOTAL \
  --region ap-southeast-1
~~~

`PutItem` tạo item khi chưa có, hoặc thất bại với `ConditionalCheckFailedException` nếu khóa tồn tại. **Không** tự diễn giải mọi ConditionalCheckFailedException thành server error cần retry.

Ví dụ này **chưa kiểm tra USER PROFILE hoặc COURSE META tồn tại**, nên chỉ dùng để minh họa conditional Put. Hệ thống thật cần validation/transaction cho invariants.

### 15.2. Mẫu TransactWriteItems

Ví dụ JSON shape để review trước khi chạy, với ba actions **khác items**: xác minh user, course đang mở, rồi tạo edge.

~~~json
{
  "TransactItems": [
    {
      "ConditionCheck": {
        "TableName": "LearningCoreSandbox",
        "Key": {
          "PK": {"S": "TENANT#t1#USER#u1"},
          "SK": {"S": "PROFILE"}
        },
        "ConditionExpression": "attribute_exists(PK)"
      }
    },
    {
      "ConditionCheck": {
        "TableName": "LearningCoreSandbox",
        "Key": {
          "PK": {"S": "TENANT#t1#COURSE#c1"},
          "SK": {"S": "META"}
        },
        "ConditionExpression": "#visibility = :published",
        "ExpressionAttributeNames": {"#visibility": "visibility"},
        "ExpressionAttributeValues": {":published": {"S": "PUBLISHED"}}
      }
    },
    {
      "Put": {
        "TableName": "LearningCoreSandbox",
        "Item": {
          "PK": {"S": "TENANT#t1#COURSE#c1"},
          "SK": {"S": "ENROLLMENT#u1"},
          "entityType": {"S": "ENROLLMENT"},
          "userId": {"S": "u1"},
          "courseId": {"S": "c1"},
          "status": {"S": "ACTIVE"},
          "GSI1PK": {"S": "TENANT#t1#USER#u1"},
          "GSI1SK": {"S": "ENROLLMENT#c1"}
        },
        "ConditionExpression": "attribute_not_exists(PK)"
      }
    }
  ]
}
~~~

Đối với AWS CLI, `--transact-items` cần **mảng các actions**, không phải toàn bộ object `{"TransactItems": ...}`. Khi lưu nội dung làm file `enroll-actions.json`, dùng phần **mảng** bên trong ở định dạng AWS CLI:

~~~bash
# CÓ TÁC ĐỘNG; minh họa, không chạy trong worker.
aws dynamodb transact-write-items \
  --transact-items file://enroll-actions.json \
  --client-request-token training-operation-id \
  --region ap-southeast-1
~~~

Trên production, cần operation ID ổn định, IAM phù hợp, kiểm soát transaction conflicts, tracking và **không** dùng những credentials/IDs giả trong ví dụ.

### 15.3. Thử fail-safe duplicate

Thực hiện Put cùng cặp PK/SK hai lần trên sandbox:

- Lần đầu: item được tạo.
- Lần sau: `ConditionalCheckFailedException` khi item tồn tại.
- Đọc lại base item để phân biệt duplicate hợp lệ với enrollment status khác.
- Không xóa item giả ngay nếu đang thực hiện bài kiểm thử tiếp theo; dọn theo quy trình.

**Trường hợp quan trọng:** nếu có hai requests song song của cùng user/course, condition check ở DynamoDB giúp ngăn overwrite/duplicate edge; không đủ để bảo đảm side effect email/payment không bị gọi trước khi transaction commit.

### 15.4. Dọn tài nguyên sandbox

Không đưa lệnh `delete-table` vào quy trình lab bắt buộc, vì lệnh này **xóa cả table** và dữ liệu. Với stack/table thử riêng, kiểm tra ownership, tags, item count/retention và snapshot policy trước khi dọn. Không xóa production table hoặc backup để “hoàn thành bài”.


## 16. Ví dụ Java AWS SDK for Java v2

### 16.1. Vì sao dùng low-level DynamoDbClient trong bài?

Với single-table, cùng một `Query` có thể trả nhiều **entity types khác nhau**. AWS SDK v2 **DynamoDbEnhancedClient** có typed mappings tiện lợi khi schema ổn định theo một entity, nhưng với polymorphic items cần converter/repository design cẩn thận. Bài này minh họa **low-level DynamoDbClient** để thấy rõ PK/SK, index và pagination.

Yêu cầu:

- Java 17+ hoặc phiên bản Java được dự án hỗ trợ;
- Dependency AWS SDK v2 DynamoDB;
- IAM role/session credentials, không hard-code access key;
- Region đúng với table;
- Table sandbox và test data giả.

### 16.2. Query lessons của một course

~~~java
import java.util.Map;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

public final class CourseLessonReader {

    private final DynamoDbClient dynamoDb;

    public CourseLessonReader(DynamoDbClient dynamoDb) {
        this.dynamoDb = dynamoDb;
    }

    public QueryResponse loadFirstPage(
            String verifiedTenantId,
            String courseId) {

        // tenantId phải lấy từ authentication/authorization context
        // đáng tin, không dùng trực tiếp request query parameter.
        String pk = "TENANT#" + verifiedTenantId + "#COURSE#" + courseId;

        QueryRequest request = QueryRequest.builder()
            .tableName("LearningCoreSandbox")
            .keyConditionExpression(
                "PK = :pk AND begins_with(SK, :prefix)")
            .expressionAttributeValues(Map.of(
                ":pk", AttributeValue.builder().s(pk).build(),
                ":prefix",
                AttributeValue.builder().s("LESSON#").build()
            ))
            .limit(20)
            .consistentRead(true)  // Chỉ base table hoặc LSI.
            .build();

        return dynamoDb.query(request);
    }

    public static void main(String[] args) {
        try (DynamoDbClient client = DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            CourseLessonReader reader = new CourseLessonReader(client);
            QueryResponse page = reader.loadFirstPage("t1", "c1");
            System.out.println("items=" + page.count());
            System.out.println(
                "morePages=" + !page.lastEvaluatedKey().isEmpty());
        }
    }
}
~~~

**Bảo mật:** `verifiedTenantId` phải đến từ trusted auth context. Method phải validate `courseId` và kiểm tra membership/quyền business phù hợp trước khi truy vấn nếu course là private.

### 16.3. Pagination đúng cách

Mã minh họa đọc nhiều pages với một giới hạn để không quét cả một item collection rất lớn:

~~~java
QueryRequest request = QueryRequest.builder()
    .tableName("LearningCoreSandbox")
    .keyConditionExpression(
        "PK = :pk AND begins_with(SK, :prefix)")
    .expressionAttributeValues(Map.of(
        ":pk", AttributeValue.builder()
            .s("TENANT#t1#COURSE#c1").build(),
        ":prefix", AttributeValue.builder()
            .s("ENROLLMENT#").build()
    ))
    .limit(25)
    .build();

Map<String, AttributeValue> cursor = Map.of();
int maxPages = 3;

for (int pageIndex = 0; pageIndex < maxPages; pageIndex++) {
    QueryRequest pageRequest = request.toBuilder()
        .exclusiveStartKey(cursor)
        .build();

    QueryResponse response = dynamoDb.query(pageRequest);
    // Xử lý các response.items() trong quyền truy cập và dung lượng cho phép.
    System.out.println("pageCount=" + response.count());

    cursor = response.lastEvaluatedKey();
    if (cursor == null || cursor.isEmpty()) {
        break;
    }
}
~~~

Đây là đoạn **trích bên trong một method** đã có biến `DynamoDbClient dynamoDb` và imports phù hợp, không phải Java source file độc lập. Trong API production, hãy **trả nextToken** cho client thay vì đọc ba pages mọi request. Token cần chứa query shape/index/tenant scope được bảo vệ (ví dụ signed/encrypted opaque token) để người dùng không sửa key.

### 16.4. Query GSI1 của user

~~~java
QueryRequest request = QueryRequest.builder()
    .tableName("LearningCoreSandbox")
    .indexName("GSI1")
    .keyConditionExpression(
        "GSI1PK = :pk AND begins_with(GSI1SK, :prefix)")
    .expressionAttributeValues(Map.of(
        ":pk", AttributeValue.builder()
            .s("TENANT#t1#USER#u1").build(),
        ":prefix", AttributeValue.builder()
            .s("ENROLLMENT#").build()
    ))
    .limit(20)
    .build();

QueryResponse response = dynamoDb.query(request);
~~~

**Không bật `consistentRead(true)` cho GSI1**. Nếu enrollment vừa được ghi không xuất hiện, ứng dụng có thể hiển thị kết quả từ lệnh ghi hoặc làm một base GetItem theo courseId/userId. Không retry GSI Query không giới hạn để “ép” strong consistency.

### 16.5. Repository/DTO layer nên che key layout

Đừng để mọi controller tự nối strings:

~~~text
"PK = TENANT#" + userSuppliedTenant + "#COURSE#" + userSuppliedCourse
~~~

Đề xuất các lớp:

~~~text
EnrollmentRepository
  - getEnrollment(VerifiedTenantId, CourseId, UserId)
  - listEnrollmentsByCourse(...)
  - listEnrollmentsByUser(...)
  - createEnrollmentConditionally(...)

CourseRepository
  - getMetadata(...)
  - listLessons(...)
  - listPublishedByCategory(...)
~~~

Lợi ích là chỉ một chỗ hiểu `PK/SK/GSI` và phiên bản key schema, dễ thêm validation/authorization, metrics và migration. Không trả raw DynamoDB `AttributeValue` objects từ REST API.

### 16.6. Java retry và lỗi không được nuốt

- Với `ProvisionedThroughputExceededException` hoặc throttling errors, dùng retry/backoff/jitter theo AWS SDK v2 và SLO; không retry vô hạn.
- Với `ConditionalCheckFailedException`, thường là business conflict/duplicate, không phải lỗi transient để retry vô hạn.
- Với `TransactionCanceledException`, cần xem cancellation reasons/conditions để biết lỗi nào permanent.
- Với timeout sau write, cần idempotency/reconciliation để tránh side effects lặp.
- Không log `PK/SK` nếu chúng chứa PII; không log toàn bộ item JSON trong production.
- Khi có batched writes, kiểm tra `UnprocessedItems` và retry hợp lý, không coi `BatchWriteItem` là atomic transaction.

## 17. Tình huống thiết kế: nền tảng khóa học nhiều trường

### 17.1. Yêu cầu

Ứng dụng Java/Spring Boot phục vụ:

- 50.000 học viên và 5.000 courses phân bố nhiều trường;
- Học viên được đăng ký nhiều courses, course có nhiều học viên;
- API cần lấy course metadata và lessons dưới 100 ms p95 trong điều kiện mục tiêu;
- Dashboard học viên liệt kê courses đã đăng ký;
- Category catalog chỉ chứa published courses;
- Một course viral có thể có 20.000 đăng ký/phút;
- Học viên không được đọc enrollment của tenant khác;
- Mọi enrollment phải không bị tạo trùng bởi retry;
- Có analytics lịch sử và yêu cầu PITR/backup;
- Ngân sách phải tính cả GSIs, transactions và Streams.

Đây là **số liệu minh họa để lập kế hoạch**, không phải SLA AWS hay kết quả benchmark thực tế.

### 17.2. Thiết kế lõi

~~~mermaid
flowchart TD
    APP[Spring Boot API] --> REPO[DynamoDB repositories]
    REPO --> BASE[(LearningCore Base Table)]
    REPO --> G1[GSI1 - enrollments by user]
    REPO --> G2[GSI2 - published by category]
    BASE --> IC[Course item collection]
    IC --> META[SK META]
    IC --> LESSON[SK LESSON#order#id]
    IC --> EDGE[SK ENROLLMENT#user]
    EDGE -. "GSI1 user-centric keys" .-> G1
    META -. "GSI2 sparse catalog keys" .-> G2
    BASE --> STREAM[DynamoDB Streams]
    STREAM --> S3[Analytics pipeline / S3]
~~~

### 17.3. Access-pattern acceptance tests

| Test | Cách kiểm tra | Kết quả đúng |
|---|---|---|
| AP1 | GetItem PROFILE | Trả đúng user của tenant |
| AP2 | GetItem COURSE META | Trả đúng course |
| AP3 | Query LESSON prefix | Sắp theo `0001,0002,...` |
| AP4 | Query ENROLLMENT prefix | Có phân trang, không Scan |
| AP5 | GSI1 Query theo user | Đúng enrollment relationships, chấp nhận propagation |
| AP6 | GetItem enrollment edge | Phát hiện duplicate nhanh |
| AP7 | GSI2 Query category | Chỉ published courses, sort theo timestamp |
| Duplicate registration | Hai Put conditional song song | Chỉ một tạo edge thành công |
| Cross-tenant | User t1 yêu cầu t2 | 403/AccessDenied và không lộ dữ liệu |
| Viral course | Load 20.000 đăng ký/phút | Không bottleneck quá SLO; shard nếu cần |
| GSI lag | Ghi rồi Query ngay | UX/logic không coi stale GSI là failed write |
| PITR restore | Restore sang table test | Khôi phục items mà không overwrite production |

### 17.4. Nên shard course viral như thế nào?

Với 20.000 registrations/phút (khoảng 333 writes/giây trên edge items ở cùng course), DynamoDB adaptive capacity có thể xử lý tùy item size/capacity, nên **chưa tự khẳng định chắc chắn sẽ bị throttle**. Nhưng thêm counters giao dịch trên một `STATS` item có thể gây contention và limits. Cần load-test thực tế:

1. Đo p99 latency và throttling.
2. Theo dõi base và GSI write capacity, hot keys.
3. Nếu counters là hotspot, chuyển sang sharded counters hoặc asynchronous aggregate.
4. Nếu edge PK vẫn hot, thêm deterministic shards.
5. Điều chỉnh AP4 list enrollments thành fan-out reads/pagination theo shard, đo lại cost.
6. Không thay `shardCount` tùy tiện làm mất khả năng GetItem các enrollment cũ.

### 17.5. Kế hoạch khôi phục

- PITR bật theo yêu cầu và kiểm tra restore.
- Streams consumers idempotent, failure sink/alarms rõ.
- Có cách đối soát enrollment edges và trạng thái course/user.
- Không xóa item expired bằng TTL rồi cho đó là business authorization.
- Runbook khi GSI stale/throttling: kiểm tra index status/capacity, tránh duplicate writes.
- Khi cần analytics tổng hợp, dùng S3/Glue/Athena hoặc data platform phù hợp, không Scan toàn table trong request người dùng.

## 18. Chẩn đoán sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| `ValidationException: Query condition missed key schema element` | Query thiếu PK equality | Xem KeyConditionExpression và đúng index keys |
| `begins_with(SK)` không chạy | Chỉ có SK condition, không có PK | Thêm PK equality |
| Query trả empty sau Put | Query GSI eventual / sai key prefix | Đọc base GetItem, kiểm tra GSI propagation |
| Sort lesson `1,10,2` | SK string không zero-pad | Dùng `0001,0002,0010` |
| `ResourceNotFoundException` trên GSI | Index chưa tạo/ACTIVE, sai Region/table | DescribeTable và IndexStatus |
| `ConditionalCheckFailedException` khi enrollment | Đã tồn tại edge hoặc condition không khớp | GetItem strong, phân biệt duplicate |
| Duplicate edge items | Không dùng conditional Put hoặc dual-edge không atomic | Unique PK/SK + transactions |
| Lệch quan hệ hai chiều | Dual-edge update thiếu atomicity | Transaction/reconciliation; cân nhắc GSI |
| Dashboard không thấy enrollment vừa tạo | GSI eventual consistency | Đọc base hoặc UX optimistic |
| Items rỗng nhưng pagination còn | FilterExpression loại hết page | Theo LastEvaluatedKey |
| `Read capacity` cao dù response ít | Filter sau Query, Projection không giảm size đọc | Thiết kế index/key, so Count/ScannedCount |
| API phải dùng Scan để tìm email | Thiếu access pattern/index | Thiết kế lookup index hoặc identity service |
| `ItemCollectionSizeLimitExceededException` | Có LSI, item collection >10 GB | Shard/archive, tránh LSI unbounded |
| `ValidationException: Item size too large` | Vượt 400 KiB/item | Tách items/S3 reference |
| GSI update bị throttle | Hot GSI PK hoặc capacity thấp | GSI metrics, sharding/capacity |
| Một course viral làm latency tăng | Hot PK/counter item | Traffic distribution, sharded counter |
| Cross-tenant data leak | Backend tin tenantId do client chọn | Verified tenant context, IAM LeadingKeys |
| TTL expired item vẫn tồn tại | TTL xóa bất đồng bộ | Check expiresAt trong business logic |
| GSI lacks projected attribute | ProjectionType/INCLUDE thiếu field | Fetch base / change projection |
| Transaction canceled | Condition failed/conflict/capacity/size | Cancellation reasons, limit 100 actions/4 MB |
| Update bị mất vì concurrent writers | Không có condition/version check | Optimistic locking |
| Dữ liệu orphan sau delete user/course | Không có foreign-key cascade | Delete workflow, Streams/reconciliation |
| Costs tăng dù chỉ một table | Nhiều GSIs/ALL projections/transactions | Capacity and storage breakdown |
| PITR restore ảnh hưởng nhiều entities | Shared table backup boundary | Restore sang temp và selective reconcile |
| Streams consumer nhận nhiều loại records | Single-table shared stream | Filter/route theo entityType |
| Global table có data khác Region | Mode/lag/conflict handling | MREC/MRSC config và data contract |

### 18.1. Runbook theo thứ tự

~~~text
1. Xác định account, Region, table, GSI, tenant và API action.
2. Xem access pattern: key-based GetItem/Query hay đang Scan?
3. Đọc Table KeySchema/GSI keys, IndexStatus, projection.
4. Kiểm tra PK/SK prefix, type, zero-padding, tenant namespace.
5. So Count, ScannedCount, ConsumedCapacity và LastEvaluatedKey.
6. Phân loại stale GSI, conditional conflict, throttling hay permission.
7. Xem hot PK/GSI key, CloudWatch/Contributor Insights và capacity.
8. Kiểm tra idempotency/transaction/TTL và business invariants.
9. Thử sửa ở sandbox, load test và đo p95/p99, write amplification.
10. Rollout có migration/rollback; quan sát lỗi/chi phí và ghi audit.
~~~


## 19. Câu hỏi tự kiểm tra và bài tập

### 19.1. Câu hỏi lý thuyết

1. Single-table design khác mô hình “mỗi entity một bảng” ở cơ sở truy vấn như thế nào?
2. Vì sao cần biết access patterns trước khi quyết định PK/SK?
3. Một table DynamoDB có composite key `PK, SK` khác gì simple PK?
4. Item collection là gì? Nó có nhất thiết là một physical partition cố định không?
5. `GetItem` và `Query` khác nhau khi truy vấn enrollment?
6. Có thể Query theo sort key mà không có partition key equality không?
7. Vì sao `FilterExpression` không giảm read capacity tiêu thụ của các items đã được đọc?
8. `ProjectionExpression` có làm giảm kích thước item DynamoDB dùng tính read capacity không?
9. Vì sao số lượng items trả về sau filter có thể bằng 0 nhưng vẫn có `LastEvaluatedKey`?
10. Tại sao đặt `LESSON#1, LESSON#2, LESSON#10` gây sai thứ tự nếu SK là String?
11. Trong ví dụ, AP4 course → students dùng index nào?
12. AP5 user → courses dùng index nào? Consistency ra sao?
13. Vì sao một enrollment edge + GSI1 có thể đơn giản hơn hai edge base items?
14. Khi nào dual-edge có thể phù hợp hơn edge + GSI?
15. GSI và LSI khác nhau ở partition key/consistency?
16. Giới hạn 10 GB item collection áp dụng với điều kiện nào?
17. Vì sao sparse GSI2 tốt cho published catalog?
18. Điều gì cần xảy ra với `GSI2PK/GSI2SK` khi course chuyển PUBLISHED → DRAFT?
19. `KEYS_ONLY`, `INCLUDE` và `ALL` khác nhau ở chi phí/projection?
20. Tại sao one-course viral traffic có thể tạo hot PK?
21. Sharding enrollment theo userId giúp writes nhưng tác động AP4 ra sao?
22. `TransactWriteItems` tối đa bao nhiêu actions và tổng dữ liệu?
23. Điều kiện nào ngăn PutItem overwrite enrollment có sẵn?
24. Vì sao transactions không tự bảo đảm email không được gửi hai lần?
25. TTL có xóa item chính xác vào giây hết hạn không?
26. Vì sao IAM `dynamodb:LeadingKeys` không thay backend authorization?
27. Một index có GSI PK không chứa tenant prefix ảnh hưởng IAM per-tenant như thế nào?
28. Tại sao Streams consumer phải hiểu nhiều entity types trong single-table?
29. Vì sao restore toàn single-table production để khôi phục một enrollment có thể nguy hiểm?
30. Khi nào multi-table hoặc hybrid design có lợi hơn?

### 19.2. Đáp án gợi ý ngắn

1. Tổ chức nhiều entity types theo truy vấn, keys và item collections, không theo một bảng/loại entity.
2. Keys quyết định Query được gì hiệu quả; tránh Scan/Filter nóng.
3. Composite cho nhiều items cùng PK với SK khác; uniqueness theo cả hai.
4. Tập items cùng logical PK; physical partitioning có thể thay đổi qua adaptive capacity/splitting.
5. GetItem dùng exact PK+SK; Query dùng PK equality và SK condition/range.
6. Không, Query cần partition key equality trên table/index được chọn.
7. Filter được áp sau bước đọc.
8. Không; chủ yếu giảm network response.
9. Filter loại hết những items của page trước khi trả, nhưng còn pages.
10. String SK sắp lexical, nên cần zero-padding.
11. Base table Query theo course PK và ENROLLMENT prefix.
12. GSI1, eventual consistency.
13. Chỉ một source-of-truth edge, GSI tự update; không hai base copies.
14. Khi hai chiều cần strongly consistent reads hoặc index constraints khác.
15. GSI PK có thể khác và chỉ eventual; LSI cùng PK, có thể strong.
16. Chỉ tables có ít nhất một LSI, tính item collection theo một PK cả projected LSI entries.
17. Chỉ indexed published items, không phải Query rồi filter drafts.
18. Loại bỏ index keys để không còn xuất hiện trong GSI2.
19. Keys only/selected/all projected attributes, khác storage/write/read follow-ups.
20. Ghi nhiều vào cùng logical PK/counter item/physical partition range.
21. AP4 phải query nhiều shards rồi merge/paginate.
22. 100 actions và 4 MB tổng.
23. `attribute_not_exists(PK)` (hoặc cùng với SK) trên target item.
24. Email bên ngoài DynamoDB transaction; network timeout/retry có thể duplicate.
25. Không, TTL xóa bất đồng bộ.
26. IAM giới hạn leading key, không kiểm tra quyền user đối với course/resource.
27. Có thể phá policy tenant-scoped; cần thiết kế lại index/policy.
28. Cả user/course/lesson/enrollment changes chia sẻ một stream.
29. Có thể ghi đè thay đổi hợp lệ của các entity khác; nên restore sang table riêng và chọn lọc.
30. Khi dữ liệu/teams/backup/KMS/TTL/workloads độc lập hoặc ít access correlation.

### 19.3. Bài tập thiết kế A — one-to-many

Hãy thêm **reviews** cho từng course, với yêu cầu:

- Liệt kê 20 reviews mới nhất của course;
- GetItem một review theo `reviewId`;
- Chỉ chủ review hoặc instructor được sửa nội dung;
- Có TTL cho temporary moderation drafts.

Gợi ý:

~~~text
PK=TENANT#t1#COURSE#c1
SK=REVIEW#2026-11-20T03:20:00Z#r1
~~~

Phân tích vấn đề: với SK chứa timestamp, **GetItem theo reviewId đơn lẻ** không xác định SK nếu không biết timestamp. Bạn cần **lookup mapping**, stable SK khác, một GSI hoặc thay API để truyền timestamp. Cũng cần cân nhắc chỉnh review timestamp có thay key hay không.

### 19.4. Bài tập thiết kế B — many-to-many

Một giáo viên phụ trách nhiều khóa học, mỗi khóa học có nhiều giáo viên. Hãy thiết kế:

- Query tất cả teachers của một course;
- Query tất cả courses của một teacher;
- Gỡ assignment phải có hiệu lực khi gọi API ngay sau đó;
- Có thể đọc danh sách teacher names mà không phát sinh 100 GetItem tuần tự.

Hãy so sánh:

1. Single-edge + GSI (nhẹ writes, đọc GSI eventual).
2. Dual-edge transaction (mạnh hơn khi cần strong cả hai hướng).
3. Table riêng `CourseAssignments` (tách lifecycle/permissions).

Không mặc định GSI đủ cho quyền bị thu hồi tức thì; authorization backend có thể cần base-table strong check.

### 19.5. Bài tập thiết kế C — đo hiệu năng

Với 1.000 course IDs có phân bố Zipf (một số course rất nóng), hãy đề xuất:

- Traffic generator có key skew giống production;
- Metrics về read/write consumed units, throttles, p95/p99 và GSI lag;
- So sánh một PK/course với 8 enrollment shards/course;
- Chi phí read fan-out của AP4 sau khi sharding;
- Kiểm thử duplicate enrollment và transaction conflicts;
- Cách nhận biết dữ liệu trả về bằng GSI bị trễ.

**Không kết luận một phương án tối ưu chỉ dựa trên số bảng/index**, mà dùng hiệu năng, độ phức tạp và chi phí đo thực tế.

## 20. Checklist triển khai production

### Access patterns và keys

- [ ] Đã liệt kê entities, relationships, access patterns, QPS, read/write ratio, latency và consistency needs.
- [ ] Mọi critical read có `GetItem` hoặc `Query` theo table/index keys; không phụ thuộc Scan nóng.
- [ ] PK có cardinality đủ và tenant prefixes được chuẩn hóa.
- [ ] SK prefixes/versioning/zero-padding/timestamp formatting được mô tả trong data contract.
- [ ] Mỗi item có `entityType` và schema version khi cần.
- [ ] One-to-many dùng item collection, không nhồi unbounded list vào một item.
- [ ] Many-to-many dùng edge/GSI/dual-edge có lựa chọn consistency và atomicity rõ ràng.
- [ ] Khi có sharding, routing version và merge-pagination đã được thiết kế.

### Index và capacity

- [ ] GSI partition key diversity được đo, không tạo hot GSI PK vô tình.
- [ ] Sparse index keys được thêm/xóa đúng khi status thay đổi.
- [ ] Projection chỉ gồm attributes ứng dụng cần, không lộ PII không cần.
- [ ] Không yêu cầu `ConsistentRead=true` cho GSI.
- [ ] LSI chỉ được tạo khi có nhu cầu strong read alternative sort và item collection 10 GB không gây rủi ro.
- [ ] Đã kiểm tra item size 400 KiB và Query 1 MB page, có LastEvaluatedKey pagination.
- [ ] Đã load-test traffic burst/hot keys/adaptive capacity và thiết lập alarms.
- [ ] Billing mode, on-demand/provisioned, Global Table mode và GSI costs được tính.

### Correctness và security

- [ ] Conditional writes bảo vệ duplicate, optimistic locking cho concurrent updates.
- [ ] Transaction dùng đúng các distinct items, không vượt 100 actions/4 MB.
- [ ] Có idempotency business operation ID cho network retries và external side effects.
- [ ] TTL không được dùng thay business authorization/expiry checks.
- [ ] IAM least privilege có kiểm tra `LeadingKeys`/GSI tenant indexes khi phù hợp.
- [ ] Backend xác minh tenant membership và quyền tới resource, không tin client-supplied tenantId.
- [ ] Không lưu credentials/PII trong keys/logs/overshared GSI projections.
- [ ] PITR/backup/encryption/KMS và restore drills được thiết kế.

### Vận hành và chi phí

- [ ] Streams consumers xử lý nhiều entity types, idempotency và failures riêng.
- [ ] Có retry/backoff và cảnh báo throttling/ConditionalCheck/TransactionCanceled theo loại lỗi.
- [ ] Có câu trả lời cho missing/stale GSI results ngay sau write.
- [ ] Có migration plan cho key schema/GSI changes và rollback window.
- [ ] Có kế hoạch archival/large object storage S3 khi items tăng lớn.
- [ ] Cost allocation đo base/GSI/storage/transactions/PITR/Streams/logs.
- [ ] Sandbox không dùng dữ liệu thật, có ownership và cleanup policy.
- [ ] Rà soát multi-table/hybrid khi isolation/operations không phù hợp một bảng.

**Kết quả mong đợi:** người học có thể thiết kế một bảng DynamoDB phục vụ nhiều entities/relationships bằng access patterns rõ ràng; chọn PK/SK/GSI/LSI theo nhu cầu, hiểu tính nhất quán và pagination, bảo vệ ràng buộc bằng điều kiện/transactions và vận hành có giám sát, khôi phục, bảo mật, kiểm soát chi phí.

## Tài liệu AWS chính thức

- [Data modeling for DynamoDB tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling.html)
- [Data modeling foundations: single-table vs multiple tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-foundations.html)
- [First steps for modeling relational data](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-modeling-nosql.html)
- [DynamoDB data modeling building blocks](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-blocks.html)
- [Data modeling schema packages and access patterns](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-schemas.html)
- [Adjacency list pattern for many-to-many relationships](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-adjacency-graphs.html)
- [Best practices for partition key design](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html)
- [Key condition expressions and Query API](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html)
- [Query filter expression and capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html)
- [Pagination with Query](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html)
- [Global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html)
- [Local secondary indexes and 10 GB item collection limit](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LSI.html)
- [General secondary index design](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-indexes-general.html)
- [Read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html)
- [DynamoDB transactions and limits](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
- [Condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html)
- [Optimistic locking with version numbers](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBMapper.OptimisticLocking.html)
- [DynamoDB adaptive capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/burst-adaptive-capacity.html)
- [DynamoDB fine-grained IAM access via LeadingKeys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html)
- [DynamoDB time to live (TTL)](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html)
- [DynamoDB Streams and Lambda](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)
- [DynamoDB point-in-time recovery](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/PointInTimeRecovery.html)
- [Global tables consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html#HowItWorks.ReadConsistency.GlobalTables)
- [AWS SDK for Java 2.x DynamoDB code examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_dynamodb_code_examples.html)
- [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý áp dụng:** Tên bảng, AWS account/Region, tenant/user/course IDs, số QPS, API responses và snippets trong bài là **ví dụ đào tạo**. AWS có thể cập nhật tính năng, quotas, consistency modes, pricing và API details. Trước khi triển khai production, hãy xác minh tài liệu AWS hiện hành, chạy benchmark và security negative tests trên sandbox, bảo vệ dữ liệu nhạy cảm, có rollback plan và quy trình phê duyệt thay đổi.
