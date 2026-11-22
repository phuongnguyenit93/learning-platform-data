# Chi phí thay đổi quan hệ hoặc chuyển dữ liệu giữa các nhóm

## 1. Vì sao một thay đổi quan hệ có thể rất tốn kém?

Trong cơ sở dữ liệu NoSQL, dữ liệu thường được tổ chức theo **những truy vấn ứng dụng cần thực hiện nhiều nhất**. Muốn đọc các tác vụ của một dự án thật nhanh, ta có thể đặt mã dự án vào partition key, nhúng các tác vụ vào document dự án, hoặc lưu một bảng đọc chuyên dụng theo dự án. Những lựa chọn này giúp đọc thuận tiện, nhưng tạo ra đánh đổi khi quan hệ thay đổi.

Giả sử một nền tảng quản lý công việc có:

~~~text
Project A
  ├── Task 17: "Viết bài học NoSQL"
  ├── Task 18: "Rà soát bài học"
  └── Task 19: "Xuất bản"

Project B
  ├── Task 31: "Thiết kế API"
  └── Task 32: "Viết kiểm thử"
~~~

Người quản lý muốn chuyển **Task 17** từ Project A sang Project B, giữ nguyên ID, người phụ trách, nội dung và lịch sử. Về nghiệp vụ, đó chỉ là một thay đổi:

~~~text
Trước: Task 17 thuộc Project A
Sau:   Task 17 thuộc Project B
~~~

Nhưng về lưu trữ, hệ thống có thể phải:

1. Sửa trạng thái ở bản ghi nguồn.
2. Loại Task 17 khỏi danh sách Project A.
3. Thêm Task 17 vào danh sách Project B.
4. Thay đổi index hoặc chuyển bản ghi sang partition mới.
5. Cập nhật bộ đếm và bản chiếu dữ liệu đang dùng cho API.
6. Làm mất hiệu lực cache của cả hai dự án.
7. Phát sự kiện, ghi audit và xử lý retry.
8. Bảo vệ tính nhất quán khi một bước thất bại giữa chừng.

Vì vậy, **chi phí thay đổi quan hệ** không chỉ là số byte được sửa trong một thuộc tính. Nó bao gồm cả chi phí **đọc, ghi, định tuyến, lưu trữ, nhất quán, vận hành và phục hồi**.

Bài học giải thích tại sao những kiểu biểu diễn quan hệ khác nhau dẫn đến chi phí di chuyển khác nhau, cách tính toán đánh đổi và cách tổ chức một thao tác chuyển nhóm an toàn.

## 2. Thuật ngữ và phạm vi

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Relationship mutation** | Tạo, xóa hoặc thay đổi một quan hệ giữa các thực thể |
| **Reparenting** | Chuyển một đối tượng con từ cha/nhóm cũ sang cha/nhóm mới |
| **Rekeying** | Chuyển dữ liệu sang một khóa định danh/định vị khác |
| **Repartitioning** | Dữ liệu chuyển sang phân vùng khác do partition key thay đổi |
| **Denormalization** | Lưu bản sao có chủ đích để tối ưu một số thao tác đọc |
| **Read model / projection** | Bản chiếu được tổ chức theo một mẫu truy vấn xác định |
| **Source of truth** | Nguồn dữ liệu có thẩm quyền khi các bản sao không đồng ý |
| **Write amplification** | Một thay đổi nghiệp vụ sinh ra nhiều thao tác ghi hoặc I/O |
| **Idempotency** | Thực hiện lại cùng một yêu cầu không gây hiệu ứng nghiệp vụ lặp sai |
| **Consistency window** | Khoảng thời gian các bản sao có thể chưa phản ánh cùng trạng thái |

Chúng ta dùng ví dụ từ **MongoDB, Cassandra, DynamoDB và Neo4j** để đối chiếu. Không nên áp đặt bảo đảm transaction, cập nhật khóa hoặc chi phí ghi của sản phẩm này cho sản phẩm khác.

### 2.1. Thay đổi quan hệ không nhất thiết là thay đổi thực thể

Ví dụ quan hệ `User FOLLOWS User` bị xóa nhưng cả hai User vẫn tồn tại. Một học viên rời Group A nhưng lịch sử học tập không được xóa. Một Task chuyển Project mà `taskId` vẫn giữ nguyên.

Điều này gợi ra một nguyên tắc thiết kế quan trọng: **định danh thực thể và định danh/địa chỉ của quan hệ cần được phân biệt**. Nếu ID của Task luôn chứa Project A, một lần chuyển Project có thể khiến mọi đường dẫn hoặc tham chiếu phụ thuộc ID cũ cần cập nhật.

## 3. Cùng một quan hệ 1:N có thể được lưu theo nhiều cách

### 3.1. Cách A — Task lưu mã Project như thuộc tính

~~~json
{
  "_id": "task-17",
  "title": "Viết bài học NoSQL",
  "projectId": "project-A",
  "status": "IN_PROGRESS",
  "version": 4
}
~~~

Nếu `_id` là khóa bất biến và `projectId` chỉ là một trường bình thường, chuyển sang B ở mức mô hình dữ liệu là sửa `projectId`. Nếu có index trên trường này, DBMS phải bảo trì index tương ứng. Nếu `projectId` nằm trong shard key, tính chất cập nhật và di chuyển vật lý còn phụ thuộc DBMS, phiên bản và cấu hình.

### 3.2. Cách B — Nhúng Task vào document Project

~~~json
{
  "_id": "project-A",
  "name": "Dự án A",
  "tasks": [
    { "taskId": "task-17", "title": "Viết bài học NoSQL" },
    { "taskId": "task-18", "title": "Rà soát bài học" }
  ]
}
~~~

Muốn chuyển Task 17, phải **loại khỏi mảng của A và thêm vào mảng của B**. Đây là cập nhật ít nhất hai document nếu Project A và B lưu riêng. Một thao tác ghi nguyên tử trên document A không tự làm việc sửa document B trở thành nguyên tử.

Khi một Project có hàng trăm nghìn Task, mảng nhúng còn có nguy cơ quá lớn, cạnh tranh ghi và khó phân trang. Với đối tượng con chuyển nhóm thường xuyên, nhúng toàn bộ con trong cha có thể kém phù hợp.

### 3.3. Cách C — Khóa của Task chứa mã nhóm

~~~text
PK = PROJECT#A
SK = TASK#17
~~~

Đổi sang B:

~~~text
PK = PROJECT#B
SK = TASK#17
~~~

Với hệ không cho sửa primary key trực tiếp, thao tác này thường là **put bản ghi dưới khóa mới rồi delete bản ghi dưới khóa cũ**. Dữ liệu có thể cần định tuyến tới partition/shard khác.

### 3.4. Cách D — Quan hệ là một bản ghi độc lập

~~~json
{
  "_id": "relation-task17-projectA",
  "taskId": "task-17",
  "projectId": "project-A",
  "relationshipType": "IN_PROJECT",
  "since": "2026-11-14T08:00:00Z"
}
~~~

Nếu quan hệ có ID và metadata độc lập, có thể sửa hoặc thay bản ghi liên kết, giữ nguyên Task và Project. Nhưng ứng dụng phải bảo đảm không có hai quan hệ hiện hành nếu nghiệp vụ quy định mỗi Task thuộc tối đa một Project.

### 3.5. Cách E — Quan hệ là cạnh đồ thị

~~~text
(Task 17)-[:IN_PROJECT]->(Project A)
~~~

Chuyển nhóm nghĩa là xóa cạnh cũ, tạo cạnh mới. Node Task không cần đổi ID hoặc sao chép nội dung. Transaction của graph DBMS có thể giúp thay hai cạnh cùng nhau trong phạm vi hỗ trợ, nhưng hệ vẫn cần ràng buộc nghiệp vụ, cache invalidation và audit.

### 3.6. Ma trận so sánh

| Biểu diễn | Công việc khi chuyển A → B | Nguy cơ nổi bật |
|---|---|---|
| Task có `projectId` | Một update nguồn, cộng index liên quan | Tranh chấp phiên bản, shard key, cache |
| Project có `tasks[]` | Xóa phần tử A, thêm phần tử B | Hai document và mảng lớn |
| Khóa chính có Project | Tạo bản ghi khóa B, xóa khóa A | Rekey và trạng thái trung gian |
| Collection quan hệ | Đổi/thay liên kết | Ràng buộc duy nhất, dữ liệu mồ côi |
| Read model theo Project | Xóa projection A, thêm projection B | Dữ liệu trễ, event sai thứ tự |
| Graph edge | Xóa cạnh A, tạo cạnh B | Nhiều cạnh hợp lệ, audit và quyền |

**Cardinality nghiệp vụ không đủ để quyết định mô hình lưu trữ.** Một quan hệ 1:N vẫn có thể được lưu bằng tham chiếu, mảng nhúng, khóa partition hoặc edge.

## 4. Phân loại các thao tác thay đổi quan hệ

### 4.1. Tạo liên kết

Ví dụ Student đăng ký Course. Khi dữ liệu Enrollment được lưu riêng, có thể cần tạo một bản ghi; khi cả Student và Course cùng giữ mảng ID, có thể phải cập nhật hai phía.

### 4.2. Xóa liên kết

Ví dụ User A hủy theo dõi B. Hành động xóa quan hệ `FOLLOWS` không đồng nghĩa xóa User A/B. Nếu cần lịch sử follow/unfollow, có thể giữ sự kiện hoặc trạng thái quan hệ thay vì xóa mọi dấu vết.

### 4.3. Đổi đích của liên kết

Ví dụ chuyển Task A → B hoặc chuyển quản lý từ nhóm X sang nhóm Y. Nghiệp vụ cần xác định Task thuộc đúng một cha hay có thể thuộc nhiều cha đồng thời.

### 4.4. Thay đổi một thuộc tính dùng làm khóa phân nhóm

Đơn hàng đổi `PENDING → PAID`. Nếu trạng thái chỉ là regular field, đây có thể là update thông thường. Nếu trạng thái được đưa vào partition key hoặc bảng đọc riêng, đổi trạng thái là di chuyển dữ liệu giữa hai nhóm.

### 4.5. Di chuyển hàng loạt

Ví dụ nhập Project A vào Project B và chuyển 500.000 Task. Thay vì một transaction đơn giản, hệ có thể cần batch, checkpoint, backfill, bắt các thay đổi mới, đối soát và cutover.

Không nên coi mọi thao tác trên là một hàm `setParentId(newId)`; độ phức tạp phụ thuộc cách dữ liệu được lưu và các bất biến nghiệp vụ.

## 5. Những loại chi phí cần đo

### 5.1. Chi phí ghi

Một Task nguồn và ba bản chiếu có thể được tổ chức:

~~~text
Task source
  ├── tasks_by_project
  ├── tasks_by_assignee
  └── tasks_by_status
~~~

Chuyển Task từ A sang B có thể yêu cầu:

1. Update Task nguồn.
2. Delete entry ở `tasks_by_project(A)`.
3. Put entry ở `tasks_by_project(B)`.
4. Update `tasks_by_assignee` nếu bản chiếu này sao chép `projectId`.
5. Update `tasks_by_status` nếu bản chiếu này cũng chứa `projectId`.
6. Sửa các bộ đếm A và B.
7. Invalidate cache và ghi event/audit.

Những bước nào thực sự cần làm phụ thuộc **trường nào được lặp trong từng read model**. Chi phí write amplification tầng ứng dụng khác với I/O nội bộ do index, replication và compaction.

### 5.2. Chi phí đọc

Nếu chỉ lưu Task theo `taskId`, truy vấn “Task thuộc Project A” cần index hoặc bộ lọc phù hợp. Một bảng đọc theo `projectId` giúp đọc nhóm nhanh hơn, nhưng phải cập nhật khi Project đổi.

Đây là đánh đổi:

~~~text
Ít bản sao
  -> ghi/move đơn giản hơn
  -> một số truy vấn có thể phải đọc/index/ghép nhiều hơn

Bản chiếu theo truy vấn
  -> đọc nhóm thuận tiện
  -> move phải cập nhật nhiều nơi, có chi phí đồng bộ
~~~

### 5.3. Chi phí lưu trữ

Copy-before-delete có thể tạm giữ một Task ở cả nhóm A và B. Migration còn có thể giữ song song dữ liệu cũ/mới, index, event log, bản sao cho rollback và backup. Nếu dịch chuyển hàng trăm triệu bản ghi, dung lượng tạm thời là ràng buộc thực sự.

### 5.4. Chi phí nhất quán

Khi nguồn đã cho Task thuộc B nhưng bản chiếu chưa đổi:

~~~text
Task source          -> project-B
tasks_by_project(A)  -> vẫn có Task 17
tasks_by_project(B)  -> chưa có Task 17
~~~

Đây là trạng thái **stale**. Nếu ứng dụng cho phép eventual consistency, phải nói rõ stale được phép trong phạm vi nào và bao lâu, khi nào cần đọc nguồn, cách quan sát độ trễ và cách sửa khi bản chiếu không bắt kịp.

### 5.5. Chi phí vận hành

Bao gồm retry, điều tra dữ liệu lệch, rebuild index/read model, migration, kiểm tra quyền khi chuyển nhóm, monitoring, xử lý quá tải và quy trình rollback. Độ phức tạp không nên được ghi bằng một điểm mơ hồ mà thiếu mô tả bước lỗi cụ thể.

---

## 6. Quan hệ một-một: chuyển quyền sở hữu

Giả sử một User có tối đa một Preferences hoặc Profile riêng:

~~~text
User A -> Profile P
User B -> chưa có Profile
~~~

Khi chuyển Profile P sang User B:

- B đã có Profile chưa?
- Profile có vòng đời độc lập với User A không?
- Bảo đảm “mỗi User tối đa một Profile” được thực thi ở đâu?
- ID của Profile có đang dựa trên `userId` không?
- Quyền truy cập trước và sau chuyển thay đổi thế nào?

Nếu Profile dùng `_id = user-A`, chuyển chủ có thể cần **rekey**; không thể chỉ cập nhật một field thông thường và giữ primary key trùng với chủ mới. Nếu Profile có ID riêng và `ownerUserId` là trường có unique index, có thể update trường chủ, nhưng phải xử lý uniqueness và xung đột khi hai request cùng chuyển.

**Unique constraint bảo đảm tối đa một bản ghi theo khóa được ràng buộc, không tự bảo đảm User được tham chiếu tồn tại hoặc Profile được xóa cùng User.**

## 7. Quan hệ một-nhiều: chi phí chuyển con

Với Course → Lesson hoặc Project → Task, cần phân biệt:

- Con nhỏ và **không bao giờ** đổi cha: nhúng thường thuận tiện.
- Con dài, có vòng đời riêng hoặc đổi cha thường xuyên: tham chiếu bằng ID thường linh hoạt hơn.
- Con rất nhiều và chủ yếu đọc theo cha: có thể dùng partition theo cha nhưng phải tính chi phí rekey.
- Con cần truy vấn theo nhiều chiều: dùng index/bảng đọc phụ với cơ chế đồng bộ.

Ví dụ một bài học được chuyển từ Course A sang B. Nếu Course nhúng toàn bộ nội dung bài, hệ có thể phải sửa hai document lớn. Nếu Lesson là document riêng chứa `courseId`, thường chỉ cần update một nguồn và index. Nếu khóa của Lesson chứa Course, phải chuyển khóa hoặc tạo bản sao mới.

### 7.1. Chuyển nhóm và thứ tự trong nhóm

Chuyển Task sang Project B thường phải xác định vị trí `position` mới. Nếu `position` là clustering key hoặc thành phần primary key, việc đổi vị trí cũng có thể thành rekey.

Nếu dự án sắp Task theo:

~~~text
Task 31: position = 1
Task 32: position = 2
Task 17: position = 3
~~~

việc kéo Task 17 lên đầu có thể làm nhiều Task phải đổi `position`. Một cách khác là cấp vị trí có khoảng cách (100, 200, 300), nhưng sau nhiều lần chèn sẽ cần rebalance, xử lý tranh chấp và duy trì thứ tự.

Như vậy, ngay cả **đổi thứ tự trong cùng nhóm** cũng có thể tạo chi phí cập nhật nhiều bản ghi.

## 8. Quan hệ nhiều-nhiều: cập nhật liên kết hai phía

Giả sử User tham gia Group qua Membership:

~~~json
{
  "_id": "membership-9001",
  "userId": "user-101",
  "groupId": "group-A",
  "role": "MEMBER",
  "status": "ACTIVE",
  "joinedAt": "2026-11-14T08:00:00Z"
}
~~~

Quan hệ N:M có thể được lưu bằng:

- Hai mảng ID ở User và Group.
- Collection Membership làm nguồn liên kết.
- Hai bảng đọc theo hai hướng `groups_by_user` và `users_by_group`.
- Cạnh graph `MEMBER_OF`.

Nếu User chuyển Group:

- Hai mảng ID phải được đồng bộ nếu cả hai phía giữ danh sách.
- Membership có thể cần đổi `groupId` hoặc tạo quan hệ mới, tùy chính sách lịch sử.
- Bảng `users_by_group` phải xóa ở A và thêm ở B.
- `groups_by_user` có thể cần đổi entry tương ứng.
- Lịch sử chuyển nhóm cần giữ lại nếu nghiệp vụ yêu cầu.

Nếu Membership có metadata và vòng đời riêng, một **association document** thường thuận tiện hơn coi quan hệ như hai mảng ID đối xứng. Nhưng collection riêng cần index hai chiều và kiểm soát tham chiếu mồ côi.

### 8.1. Tối đa một nhóm hiện hành khác với lịch sử nhiều nhóm

Nghiệp vụ có thể quy định một User chỉ thuộc **một Group hiện hành**, nhưng trước đây đã thuộc nhiều Group khác.

Một cấu trúc dễ hiểu:

~~~text
User.currentGroupId     -> nhóm hiện hành
GroupMoveEvent          -> lịch sử A -> B -> C
users_by_group          -> bản chiếu danh sách hiện hành
~~~

Nếu lưu mọi Membership lịch sử như những bản ghi với trạng thái, cần ràng buộc riêng cho “tối đa một ACTIVE” thay vì unique index trên tất cả các cặp Group/User một cách máy móc.

---

## 9. MongoDB: thay đổi trường quan hệ trên một document

Xét Task nguồn:

~~~json
{
  "_id": "task-17",
  "title": "Viết bài học NoSQL",
  "projectId": "project-A",
  "status": "IN_PROGRESS",
  "version": 4
}
~~~

### 9.1. Index cho danh sách theo Project

~~~javascript
db.tasks.createIndex({
  projectId: 1,
  updatedAt: -1,
  _id: -1
});
~~~

Query:

~~~javascript
db.tasks.find(
  { projectId: "project-A" },
  { title: 1, status: 1, projectId: 1, updatedAt: 1 }
).sort({ updatedAt: -1, _id: -1 }).limit(30);
~~~

Chuyển Project khiến index theo `projectId` phải được cập nhật. Chi phí này là một phần write path mà application không nhất thiết nhìn thấy dưới dạng nhiều lệnh.

### 9.2. Update có điều kiện

~~~javascript
const result = db.tasks.updateOne(
  {
    _id: "task-17",
    projectId: "project-A",
    version: 4
  },
  {
    $set: {
      projectId: "project-B",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount === 0) {
  // Có thể Task đã đổi nhóm, phiên bản đã thay đổi,
  // hoặc retry của lần chuyển đã hoàn tất.
  // Cần đọc lại trạng thái hoặc tra requestId.
}
~~~

Điều kiện `projectId` và `version` giúp phát hiện một thay đổi cạnh tranh. Nhưng nếu lần đầu thành công rồi response thất lạc, retry bằng version cũ cũng cho `matchedCount = 0`. **Không được hiểu mọi kết quả không khớp là lần đầu thất bại.**

### 9.3. Một update logic có thể thành việc di chuyển vật lý

Nếu collection được shard theo `projectId`, việc thay đổi shard key có điều kiện và phạm vi hỗ trợ riêng theo phiên bản/cấu hình MongoDB. Không nên mặc định lệnh update đơn giản có thể áp dụng nguyên xi trên mọi cluster hoặc không làm tăng chi phí chuyển shard.

Giữ `taskId` làm ID nghiệp vụ ổn định giúp tránh phá các tham chiếu, nhưng vẫn phải xem cách DBMS lưu trữ và định tuyến document.

### 9.4. Khi Task được nhúng trong Project

Giả sử:

~~~json
{
  "_id": "project-A",
  "tasks": [
    { "taskId": "task-17", "title": "Viết bài học NoSQL" },
    { "taskId": "task-18", "title": "Rà soát bài học" }
  ]
}
~~~

Đổi cha đòi xóa phần tử ở A và thêm ở B. Nếu hai update diễn ra độc lập, lỗi ở giữa có thể tạo trạng thái Task có mặt ở **cả hai Project** hoặc tạm thời **không ở Project nào**.

Nếu hai document nằm trong một phạm vi transaction MongoDB được hỗ trợ và yêu cầu chuyển phải nguyên tử, có thể dùng multi-document transaction. Transaction có chi phí và giới hạn; không nên biến toàn bộ việc chuyển hàng triệu Task thành một transaction kéo dài.

### 9.5. Ví dụ transaction nguồn và bản chiếu

Giả sử có `tasks` là nguồn và `task_project_feed` là bản chiếu. Một cách minh họa dùng Node.js MongoDB driver:

~~~javascript
const session = client.startSession();

try {
  await session.withTransaction(async () => {
    const db = client.db("learning");
    const tasks = db.collection("tasks");
    const feed = db.collection("task_project_feed");

    const update = await tasks.updateOne(
      {
        _id: "task-17",
        projectId: "project-A",
        version: 4
      },
      {
        $set: { projectId: "project-B", updatedAt: new Date() },
        $inc: { version: 1 }
      },
      { session }
    );

    if (update.matchedCount !== 1) {
      throw new Error("TASK_STATE_CHANGED");
    }

    await feed.deleteOne(
      { _id: "project-A#task-17" },
      { session }
    );

    await feed.updateOne(
      { _id: "project-B#task-17" },
      {
        $set: {
          projectId: "project-B",
          taskId: "task-17",
          title: "Viết bài học NoSQL"
        }
      },
      { upsert: true, session }
    );
  });
} finally {
  await session.endSession();
}
~~~

**Giới hạn của ví dụ:**

- Chỉ là mô hình cho một move nhỏ; môi trường thực phải hỗ trợ transaction với cấu hình phù hợp.
- Driver có thể retry transaction/callback theo điều kiện lỗi. Không thực hiện side effect bên ngoài không thể rollback, như gửi email, ngay trong callback.
- Ví dụ chưa triển khai idempotency key, authorization, retry khi kết quả commit chưa rõ và kiểm tra mọi thuộc tính của projection.
- Transaction trong MongoDB không tự bao phủ message broker, cache hoặc dịch vụ khác.
- Nếu nguồn và projection ở hai hệ độc lập, cần giao thức khác thay cho transaction nội bộ.

**Một transaction phù hợp chỉ giúp những ghi trong phạm vi giao dịch có thể cùng commit hoặc rollback; nó không làm mọi hệ thống ngoài transaction lập tức đồng bộ.**

---

## 10. Cassandra: đổi partition key thường là copy-and-delete

Trong wide-column Cassandra, partition key quyết định partition logic. Ví dụ bảng đọc:

~~~sql
CREATE TABLE tasks_by_project (
    project_id text,
    task_id text,
    title text,
    status text,
    updated_at timestamp,
    PRIMARY KEY ((project_id), task_id)
);
~~~

Bản ghi cũ có khóa:

~~~text
(project_id = project-A, task_id = task-17)
~~~

Muốn chuyển B, cần một bản ghi với khóa mới:

~~~text
(project_id = project-B, task_id = task-17)
~~~

### 10.1. Không thể UPDATE primary key như cột thường

CQL primary key không được sửa như regular column. Về logic, cần:

~~~sql
INSERT INTO tasks_by_project (
    project_id, task_id, title, status, updated_at
) VALUES (
    'project-B', 'task-17',
    'Viết bài học NoSQL', 'IN_PROGRESS',
    '2026-11-14T08:20:00Z'
);
~~~

~~~sql
DELETE FROM tasks_by_project
WHERE project_id = 'project-A'
  AND task_id = 'task-17';
~~~

Thao tác INSERT ghi vào partition mới, DELETE loại bản ghi thuộc partition cũ. Nếu hai partition được phân phối tới các replica khác nhau, đây còn là hoạt động qua các nhóm lưu trữ khác nhau.

### 10.2. Hai thứ tự thực hiện đều có cửa sổ trung gian

**Insert B trước, delete A sau:**

~~~text
Trong khoảng giữa:
  Project A vẫn có Task 17
  Project B đã có Task 17
~~~

**Delete A trước, insert B sau:**

~~~text
Trong khoảng giữa:
  Project A không có Task 17
  Project B chưa có Task 17
~~~

Không có thứ tự nào tự bảo đảm người đọc luôn thấy đúng một nhóm khi hai lệnh độc lập và có độ trễ/khả năng lỗi.

### 10.3. BATCH không phải SQL transaction tổng quát

Có thể viết:

~~~sql
BEGIN BATCH
  INSERT INTO tasks_by_project (
      project_id, task_id, title, status, updated_at
  ) VALUES (
      'project-B', 'task-17',
      'Viết bài học NoSQL', 'IN_PROGRESS',
      '2026-11-14T08:20:00Z'
  );
  DELETE FROM tasks_by_project
  WHERE project_id = 'project-A'
    AND task_id = 'task-17';
APPLY BATCH;
~~~

Nhưng Cassandra `BATCH` có các đặc điểm về atomicity/durability và giới hạn riêng, **không tương đương transaction SQL có mức cô lập mạnh trên mọi thao tác nhiều partition**. Batch đa partition còn có overhead điều phối, không phải kỹ thuật tăng throughput bằng cách gom tùy ý nhiều ghi.

Không nên tự kết luận mọi reader sẽ quan sát việc đổi nhóm như một thao tác nguyên tử giữa hai partition. Cần thiết kế theo consistency level và các bảo đảm thực tế của Cassandra đang dùng.

### 10.4. Tách nguồn Task theo ID và bảng đọc theo Project

Một mô hình:

~~~sql
CREATE TABLE task_by_id (
    task_id text PRIMARY KEY,
    project_id text,
    title text,
    status text,
    version bigint,
    updated_at timestamp
);
~~~

~~~sql
CREATE TABLE tasks_by_project (
    project_id text,
    task_id text,
    title text,
    status text,
    updated_at timestamp,
    PRIMARY KEY ((project_id), task_id)
);
~~~

Trong đó `task_by_id` có thể là nguồn có thẩm quyền theo hợp đồng ứng dụng; `tasks_by_project` là projection phục vụ API. Khi move, sửa nguồn rồi điều chỉnh projection. Nếu projection chưa bắt kịp, có nguồn để đối soát.

Đánh đổi là dữ liệu được nhân bản và cần cơ chế retry/đồng bộ, không mặc nhiên có transaction qua hai bảng.

### 10.5. Tombstone và dữ liệu dịch chuyển thường xuyên

Trong Cassandra, `DELETE` tạo tombstone theo cơ chế lưu trữ của hệ; việc xóa vật lý diễn ra sau khi các điều kiện liên quan đến compaction/repair được đáp ứng. Move nhiều lần giữa các nhóm có thể tạo nhiều tombstone, gây chi phí lưu trữ và đọc nếu truy vấn đi qua nhiều dữ liệu đã bị xóa.

Với những quan hệ thay đổi rất thường xuyên, cần đo tombstone, compaction, repair và p95/p99 thay vì chỉ đo một lệnh INSERT.

---

## 11. DynamoDB: khóa chính không phải thuộc tính có thể sửa tùy ý

Giả sử item có:

~~~text
PK = PROJECT#A
SK = TASK#17
~~~

Sau khi Task chuyển B, khóa cần là:

~~~text
PK = PROJECT#B
SK = TASK#17
~~~

DynamoDB không dùng `UpdateItem` để đổi primary key của item thành một khóa khác. Ở mức mô hình, cần tạo item dưới khóa mới và xóa item khóa cũ.

### 11.1. Dùng transaction khi nằm trong phạm vi hỗ trợ

Có thể cân nhắc `TransactWriteItems` gồm:

- `Put` item ở B với condition ngăn ghi đè sai.
- `Delete` item ở A với condition xác nhận trạng thái phiên bản mong đợi.

DynamoDB transaction có giới hạn về số item, dữ liệu và phạm vi hỗ trợ. Cần kiểm tra tài liệu dịch vụ cho tài khoản, region và workload hiện tại. Chuyển hàng triệu item không phải một transaction đơn lẻ.

### 11.2. Giữ khóa nguồn theo Task ID

Một thiết kế khác:

~~~json
{
  "PK": "TASK#17",
  "SK": "META",
  "taskId": "task-17",
  "projectId": "project-A",
  "title": "Viết bài học NoSQL",
  "version": 4
}
~~~

Nếu sử dụng GSI theo `projectId` để truy vấn danh sách nhóm, việc đổi `projectId` trên item nguồn không đòi đổi `PK` hoặc `SK` của nguồn. Nhưng GSI cần được duy trì và có **đặc tính nhất quán đọc riêng**; không nên giả định đọc danh sách qua GSI ngay sau update luôn nhìn thấy Task ở B.

### 11.3. Đánh đổi DynamoDB

| Thiết kế | Move | Đọc theo Project | Đánh đổi |
|---|---|---|---|
| Item chính theo Project | Put B + delete A | Query theo PK thuận lợi | Rekey, transaction/điều kiện |
| Item chính theo Task + GSI Project | Update thuộc tính | Query GSI | Chi phí index và eventual consistency |
| Item nguồn + item index thủ công | Update nguồn + thay index A/B | Query index thủ công | Đồng bộ, retry và đối soát |

Mẫu nào hợp lý phụ thuộc tần suất move, yêu cầu read-your-writes, ngân sách ghi và khả năng phục vụ truy vấn theo Project.

---

## 12. Neo4j: thay đổi cạnh, giữ nguyên node

Trong property graph:

~~~text
(Task 17)-[:IN_PROJECT]->(Project A)
~~~

Chuyển nhóm là thay cạnh cũ bằng cạnh mới, trong khi node Task vẫn giữ định danh.

### 12.1. Tạo dữ liệu thử

~~~cypher
CREATE CONSTRAINT task_id_unique IF NOT EXISTS
FOR (t:Task)
REQUIRE t.taskId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project)
REQUIRE p.projectId IS UNIQUE;
~~~

~~~cypher
MERGE (a:Project {projectId: 'project-A'})
SET a.name = 'Dự án A';

MERGE (b:Project {projectId: 'project-B'})
SET b.name = 'Dự án B';

MERGE (t:Task {taskId: 'task-17'})
SET t.title = 'Viết bài học NoSQL';

MATCH (t:Task {taskId: 'task-17'})
MATCH (a:Project {projectId: 'project-A'})
MERGE (t)-[:IN_PROJECT]->(a);
~~~

### 12.2. Di chuyển trong một câu lệnh

~~~cypher
MATCH (t:Task {taskId: 'task-17'})
      -[oldRel:IN_PROJECT]->
      (old:Project {projectId: 'project-A'})
MATCH (target:Project {projectId: 'project-B'})
DELETE oldRel
CREATE (t)-[:IN_PROJECT]->(target);
~~~

Trong Neo4j, các ghi trong một transaction được commit/rollback theo hợp đồng DBMS. Tuy vậy, truy vấn này chỉ tìm cạnh cũ A → Task đúng theo mô hình, **không tự bảo đảm toàn graph không có một cạnh IN_PROJECT khác** nếu dữ liệu trước đó đã sai hoặc các writer cạnh tranh.

Nếu nghiệp vụ quy định một Task thuộc đúng một Project, cần cơ chế kiểm soát tranh chấp và ràng buộc phù hợp ở transaction/tầng ứng dụng.

### 12.3. Lưu lịch sử quan hệ

Nếu phải biết Task từng thuộc Project nào, xóa cạnh cũ có thể làm mất lịch sử. Có thể dùng:

~~~text
(Task)-[:CURRENT_PROJECT]->(Project B)
(Task)-[:WAS_IN {from: t0, to: t1}]->(Project A)
~~~

hoặc lưu `TaskMoveEvent` độc lập. **Graph edge giúp biểu diễn move dễ hiểu hơn, nhưng không miễn phí audit, quyền truy cập, cache và sự đồng bộ với hệ ngoài.**

---

## 13. Ba mức nhất quán khi chuyển nhóm

### 13.1. Nguồn có thẩm quyền đã đổi

Task nguồn:

~~~json
{
  "_id": "task-17",
  "projectId": "project-B",
  "version": 5
}
~~~

Một thao tác đọc nguồn với mức consistency phù hợp có thể xác nhận trạng thái mới. Nhưng API đọc danh sách nhóm qua GSI hoặc read model bất đồng bộ có thể vẫn thấy dữ liệu cũ.

### 13.2. Bản chiếu được cập nhật bất đồng bộ

Nguồn phát event:

~~~json
{
  "eventId": "move-9001",
  "taskId": "task-17",
  "fromProjectId": "project-A",
  "toProjectId": "project-B",
  "taskVersion": 5,
  "occurredAt": "2026-11-14T08:20:00Z"
}
~~~

Worker xử lý:

~~~text
Bỏ Task 17 khỏi A
Thêm Task 17 vào B
Ghi nhận version 5 đã áp dụng
~~~

Trong khoảng chờ, các API đọc projection cần có chính sách rõ về stale data.

### 13.3. Read-your-writes

Người dùng vừa chuyển Task sang B có thể yêu cầu **nhìn thấy ngay kết quả chuyển**. Một số lựa chọn:

- API trả Task đã cập nhật từ nguồn; client cập nhật UI cục bộ.
- Client tạm đọc nguồn theo Task ID, thay vì tin read model chưa đồng bộ.
- Ghi nguồn và projection trong cùng transaction nếu DBMS hỗ trợ phạm vi cần thiết.
- Chờ projection đạt version mong đợi, có timeout và fallback.

Không nên chỉ viết “eventual consistency” nếu sản phẩm có yêu cầu đọc ngay sau ghi. Cần mô tả **màn hình nào cho phép trễ, trễ bao lâu và xử lý thế nào khi quá ngưỡng**.

---

## 14. Retry và xung đột đồng thời

### 14.1. Retry sau khi response bị mất

Client gửi yêu cầu:

~~~json
{
  "requestId": "move-9001",
  "taskId": "task-17",
  "expectedFromProjectId": "project-A",
  "toProjectId": "project-B",
  "expectedVersion": 4
}
~~~

Server đã commit thay đổi, nhưng response bị mất. Client retry; update có điều kiện cũ không còn khớp.

Nếu chỉ thấy `matchedCount = 0` và trả lỗi, client sẽ tưởng thao tác chưa thực hiện. Cần có **requestId/idempotency key** được quản lý cạnh tranh an toàn:

1. Nếu request đã có kết quả, trả lại kết quả đã lưu.
2. Nếu chưa, kiểm tra quyền và version.
3. Thực hiện nguồn đúng một lần trong phạm vi bảo đảm.
4. Lưu kết quả request/event theo giao thức phù hợp.
5. Consumer phải xử lý event được gửi lại mà không làm sai trạng thái.

**Có requestId trong JSON không tự tạo idempotency** nếu hệ không lưu và kiểm tra nó.

### 14.2. Hai yêu cầu chuyển cạnh tranh

~~~text
R1: A -> B với expectedVersion = 4
R2: A -> C với expectedVersion = 4
~~~

Nếu cả hai cùng đọc version 4, chỉ một được thành công theo compare-and-set phù hợp. Request còn lại phải nhận conflict, đọc lại trạng thái và quyết định thao tác mới.

Nếu không có kiểm soát này, một cập nhật có thể âm thầm ghi đè kết quả của cập nhật khác.

### 14.3. Event đến sai thứ tự

~~~text
Version 5: A -> B
Version 6: B -> C
~~~

Worker có thể nhận version 6 trước version 5 do queue/retry. Nếu xử lý theo **thứ tự nhận**, event cũ có thể đưa projection trở lại B.

Cần dùng version/sequence được tạo từ nguồn có thẩm quyền. Một hướng xử lý:

- Projection ghi version đã áp dụng.
- Event cũ hơn hoặc trùng version không được ghi đè state mới hơn.
- Nếu logic cần áp dụng mọi bước, khi phát hiện thiếu version trung gian phải xử lý gap theo giao thức rõ ràng.
- Timestamp từ đồng hồ vật lý không tự bảo đảm thứ tự event xuyên nhiều node.

### 14.4. Bộ đếm dễ sai khi event lặp

Nếu event Move được xử lý bằng:

~~~text
A.taskCount -= 1
B.taskCount += 1
~~~

và event được gửi hai lần, count sẽ sai. Ghi đè một projection theo version và cộng trừ counter là **hai loại thao tác có tính idempotency khác nhau**.

Cần dùng deduplication, conditional update, transaction phù hợp hoặc cơ chế tính lại count từ nguồn. Không nên chỉ dựa vào “queue hiếm khi gửi lặp”.

---

## 15. Giao thức chuyển nhóm không có transaction chung

Khi nguồn Task và read model nằm trong những hệ khác nhau, thường không có transaction nguyên tử bao trùm cả hai.

### 15.1. Transactional outbox

Một luồng mẫu:

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Source as Task source
    participant Outbox as Outbox/stream
    participant Worker as Projection worker
    participant View as Project read model

    Client->>Source: Move(Task17, A, B, requestId)
    Source->>Source: Kiểm tra quyền và version
    Source->>Outbox: Ghi TaskMoved(v5) cùng giao dịch nguồn nếu hỗ trợ
    Source-->>Client: Source committed
    Outbox-->>Worker: Phát event, có thể gửi lại
    Worker->>View: Bỏ khỏi A, thêm vào B theo version
    Worker-->>Outbox: Xác nhận xử lý theo giao thức
~~~

**Transactional outbox** nghĩa là thay đổi nguồn và bản ghi event được ghi atomically trong cùng phạm vi transaction phù hợp, rồi event được truyền bất đồng bộ. Không nên viết ra broker trực tiếp rồi mặc định broker và DBMS cùng commit.

Consumer cần xử lý **at-least-once delivery** và có thể rebuild projection từ nguồn hoặc log khi sai lệch.

### 15.2. Theo dõi trạng thái yêu cầu

~~~text
REQUESTED
   ↓
SOURCE_COMMITTED
   ↓
PROJECTION_UPDATING
   ↓
PROJECTION_CONVERGED
~~~

Nếu worker thất bại giữa chừng, có thể retry projection mà không cần chuyển nguồn lần nữa. Đây là mô hình hữu ích khi thao tác move quan trọng hoặc tốn nhiều thời gian.

Không nhất thiết phải tạo trạng thái chi tiết cho mọi thay đổi nhỏ; nhưng với move qua nhiều hệ thống, trạng thái và correlation ID giúp truy vết lỗi.

### 15.3. Thứ tự xử lý projection có đánh đổi

**Thêm vào B rồi xóa A** tạo cửa sổ Task có ở cả hai nhóm.

**Xóa A rồi thêm B** tạo cửa sổ Task không có ở nhóm nào.

Một transaction đa item nếu được hỗ trợ có thể cung cấp bảo đảm mạnh hơn trong phạm vi của nó; nếu cập nhật bất đồng bộ, cần chấp nhận cửa sổ stale hoặc dùng cơ chế kiểm tra nguồn.

Không có thứ tự hai thao tác độc lập nào tự bảo đảm mọi người đọc nhìn thấy đúng một nhóm tại mọi thời điểm.

---

## 16. Di chuyển hàng loạt: backfill, checkpoint và cutover

Giả sử cần hợp nhất Project A vào B, chuyển **500.000 Task**. Đây không còn là một move đơn lẻ.

### 16.1. Những khó khăn riêng

- Không thể gói quá nhiều item trong một transaction thông thường.
- Task tiếp tục được tạo/sửa/xóa trong lúc di chuyển.
- Có thể bị throttle, timeout hoặc worker restart.
- Data cũ và mới có thể tồn tại song song.
- Cần tránh bỏ sót những thay đổi sau khi batch đi qua một vị trí.
- Dung lượng và index tạm thời có thể tăng mạnh.
- Cần biết chính xác lúc nào đường đọc mới an toàn để sử dụng.

### 16.2. Quy trình tham khảo

~~~mermaid
flowchart TD
    A["Thiết kế schema và khóa đích"] --> B["Tạo đường đọc/index đích"]
    B --> C["Bắt đầu theo dõi thay đổi phát sinh"]
    C --> D["Backfill theo batch có checkpoint"]
    D --> E["Catch-up thay đổi sau snapshot"]
    E --> F["Đối soát ID, version và bất biến"]
    F --> G["Cutover đường đọc có kiểm soát"]
    G --> H["Theo dõi, rollback nếu cần"]
    H --> I["Dọn dữ liệu cũ khi an toàn"]
~~~

Các pha:

1. Xác định nguồn có thẩm quyền, khóa mới và quy tắc idempotency.
2. Chuẩn bị bảng/index mới và capacity cho bản sao tạm.
3. Thu thập thay đổi phát sinh qua log, outbox hoặc cơ chế phù hợp.
4. Backfill theo batch có retry và checkpoint bền vững.
5. Bắt kịp các event sau thời điểm snapshot.
6. Đối soát cả ID, số lượng, version và dữ liệu liên quan.
7. Chuyển traffic đọc sang mô hình mới, có điều kiện rollback.
8. Theo dõi tỷ lệ lỗi, p95/p99, missing/duplicate records.
9. Dọn bảng cũ khi đã qua giai đoạn rollback và đáp ứng retention.

### 16.3. Checkpoint phải có ý nghĩa đúng

Ví dụ:

~~~json
{
  "migrationId": "projectA-to-B-20261114",
  "phase": "BACKFILL",
  "lastTaskId": "task-30481",
  "processedCount": 30481,
  "failedCount": 3,
  "snapshotWatermark": "version-8172"
}
~~~

Giá trị `lastTaskId` chỉ dùng làm cursor an toàn nếu cách duyệt có **thứ tự ổn định** và không bỏ sót Task được thêm/xóa trong lúc migration. Với dữ liệu biến động, cần snapshot semantics hoặc nguồn thay đổi đủ tin cậy.

Checkpoint cần trả lời:

- Batch nào đã hoàn thành bền vững?
- Chạy lại batch có tạo bản ghi trùng không?
- Những ghi phát sinh sau snapshot được lấy từ đâu?
- Worker khác khởi động lại có tạo cùng kết quả không?

### 16.4. Ước lượng tốc độ

Chuyển 500.000 Task trong 2 giờ cần trung bình:

\[
500000 / (2 \times 3600) \approx 69{,}4\ \text{Task/giây}.
\]

Nếu mỗi Task tạo tối thiểu ba thao tác ghi logic, tương ứng khoảng 208 ghi logic/giây chưa tính replication, index và retry. Đây chỉ là phép tính dung lượng sơ bộ. Tăng tốc migration có thể ảnh hưởng latency của API production; cần rate limit, backpressure và ngân sách tài nguyên.

---

## 17. Khóa nhóm bất biến hay khóa thực thể bất biến?

Giả sử:

~~~text
Task ID:       task-17
Current group: project-A
~~~

Hai cách chọn khóa:

**Theo nhóm:**

~~~text
PK = project-A
SK = task-17
~~~

**Theo thực thể:**

~~~text
PK = task-17
projectId = project-A (thuộc tính/index)
~~~

### 17.1. Khi khóa theo nhóm hợp lý

Dữ liệu hiếm khi đổi nhóm và truy vấn hầu như luôn trong một nhóm. Ví dụ phép đo của thiết bị được ghi theo `(deviceId, eventDay)` và không cần đổi thiết bị sau khi ghi. Partition key chứa nhóm là lựa chọn tự nhiên.

### 17.2. Khi khóa theo nhóm có thể gây chi phí lớn

Task thường xuyên đổi Project, Product đổi category, Order đổi status hoặc User được chuyển team. Nếu nhóm là thành phần primary key, mỗi thay đổi có thể là rekey/copy-delete.

Khi đó có thể cân nhắc giữ ID nguồn bất biến và thêm index/read model theo group. Đổi lại, chi phí đọc và đồng bộ index có thể tăng. Không có lựa chọn tối ưu tuyệt đối.

### 17.3. Cần tránh biến ID logic thành “địa chỉ vật lý”

Nếu API công khai ID `project-A/task-17` nhưng Task có thể chuyển sang B, mọi đường dẫn, cache key và tham chiếu từ hệ khác có thể bị ảnh hưởng. Giữ `task-17` làm ID logic độc lập và dùng trường/quan hệ riêng biểu diễn Project thường giúp ổn định tham chiếu hơn.

---

## 18. Dữ liệu lặp: snapshot lịch sử và projection hiện tại

Đừng sửa mọi bản sao chỉ vì quan hệ hiện tại đã thay đổi.

### 18.1. Snapshot lịch sử

~~~json
{
  "taskId": "task-17",
  "projectNameAtCompletion": "Project A",
  "completedAt": "2026-11-13T10:00:00Z"
}
~~~

Nếu đây là snapshot tại lúc hoàn thành, sau khi Task chuyển B vẫn phải giữ giá trị Project A. Đây là **bản sao lịch sử bất biến**, không phải projection bị stale.

### 18.2. Projection hiện tại

~~~json
{
  "taskId": "task-17",
  "currentProjectName": "Project B",
  "sourceVersion": 5
}
~~~

Nếu là bản chiếu hiện tại, phải có cơ chế đồng bộ từ nguồn, đánh dấu version và giới hạn độ trễ.

### 18.3. Audit event

~~~json
{
  "eventId": "move-9001",
  "taskId": "task-17",
  "fromProjectId": "project-A",
  "toProjectId": "project-B",
  "actorId": "user-3",
  "sourceVersion": 5
}
~~~

Audit ghi **sự kiện thay đổi**, không nên bị ghi đè như trạng thái hiện tại. Bảo mật và retention của audit có thể khác dữ liệu nghiệp vụ.

---

## 19. Cache, counter và search index cũng phải được tính

Giả sử ứng dụng cache:

~~~text
project:project-A:tasks:page1
project:project-B:tasks:page1
task:task-17
~~~

Chuyển Task có thể ảnh hưởng cả ba khóa. Nếu danh sách sort theo `updatedAt DESC`, Task còn có thể đổi vị trí giữa các trang; chỉ làm mới một cache entry không nhất thiết đủ.

Nếu Project có `taskCount`, move logic cần giảm A và tăng B. Nếu worker xử lý event hai lần, count có thể sai, nên phải có cách dedupe, conditional update hoặc đối soát từ nguồn.

Search index cũng có thể chứa `projectId`. Dữ liệu nguồn đã sang B nhưng search index còn cho kết quả theo A có thể gây sai UX và nghiêm trọng hơn nếu phân quyền dựa trên group. Cần xác định API nào được dùng index stale và API nào phải kiểm tra nguồn trước khi trả dữ liệu.

---

## 20. Chuyển group và an toàn đa tenant

Một Task chuyển Project **trong cùng tenant** khác với việc dữ liệu chuyển **giữa hai tenant**.

Trong hệ đa tenant, thay đổi tenant có thể ảnh hưởng:

- Khóa phân vùng chứa tenant ID.
- Quyền đọc/ghi và chính sách phân quyền.
- Khóa mã hóa riêng theo tenant.
- Retention, data residency và nghĩa vụ pháp lý.
- Search index, cache và bản xuất dữ liệu.
- Các tham chiếu từ Invoice, Payment, Project hoặc User.
- Audit và phê duyệt thực hiện việc chuyển.

**Không nên coi thay đổi `tenantId` là update bình thường** nếu tenant là ranh giới bảo mật. Một projection còn dữ liệu ở tenant cũ có thể trở thành lỗ hổng lộ dữ liệu, không chỉ là lỗi màn hình.

Một quy trình cần kiểm tra quyền trên nhóm nguồn và nhóm đích, trạng thái tài nguyên, chính sách lưu giữ, phạm vi dữ liệu và cách thu hồi truy cập cũ. Khóa có chứa tenant không thay thế kiểm tra authorization.

---

## 21. Mô hình định lượng chi phí move

Định nghĩa:

- \(N_m\): số thao tác chuyển nhóm trong một ngày.
- \(W_s\): số ghi nguồn trên một move.
- \(W_p\): số put/delete/update projection trên một move.
- \(W_o\): số side effect khác như audit, outbox hoặc counter.
- \(B\): số byte cần sao chép/di chuyển logic cho một move.

Ước tính:

\[
W_{\text{logic/day}} = N_m(W_s+W_p+W_o)
\]

\[
B_{\text{logic/day}} = N_m B
\]

Đây là **ước tính tầng ứng dụng**, không phải số I/O vật lý hoặc hóa đơn cloud. Chỉ mục, replication, compaction và retry có thể làm công việc thực tế nhiều hơn.

### 21.1. Ví dụ

Giả sử:

~~~text
10.000 Task được chuyển mỗi ngày.
Mỗi Task có payload copy khoảng 4 KB.
Một move bao gồm:
  1 update nguồn
  1 delete projection A
  1 put projection B
  1 event/outbox
~~~

Khi đó:

~~~text
10.000 × 4 = 40.000 thao tác logic/ngày
10.000 × 4 KB = khoảng 40 MB dữ liệu copy logic/ngày
~~~

Chưa tính replica, index, compaction, cache và retry. Nếu Task được chuyển nhiều lần liên tiếp, số event, tombstone và thao tác cập nhật sẽ tăng mà dữ liệu nguồn có thể gần như không thay đổi dung lượng.

### 21.2. Chi phí trạng thái trung gian

Ngoài latency và byte, nên đo:

| Metric | Ý nghĩa |
|---|---|
| `moveLatencyP95/P99` | Độ trễ người dùng của API move |
| `projectionLagP95/P99` | Trễ từ nguồn commit đến projection bắt kịp |
| `staleEntries` | Số Task còn ở nhóm cũ |
| `missingEntries` | Số Task chưa xuất hiện ở nhóm mới |
| `duplicateEntries` | Số Task xuất hiện đồng thời ở hai nhóm |
| `moveConflictRate` | Tỷ lệ xung đột phiên bản |
| `moveRetryRate` | Tỷ lệ yêu cầu/event cần xử lý lại |
| `reconciliationFixes` | Số bản ghi được đối soát và sửa |
| `bytesMoved` | Lượng dữ liệu logic/physical được chuyển |
| `hotPartitionLoad` | Mức tải nhóm/partition lớn nhất |

Khi hệ có eventual consistency, phải đặt **ngưỡng chấp nhận rõ ràng** cho lag và mức sai lệch, không chỉ đo p95 của query đọc.

---

## 22. Tình huống thực hành: chuyển thành viên giữa hai nhóm

Một nền tảng học trực tuyến có:

~~~text
Group A: 100.000 thành viên
Group B: 20.000 thành viên
User 101 đang thuộc Group A
~~~

Yêu cầu nghiệp vụ:

1. Mỗi User chỉ có **một Group hiện hành**.
2. Lịch sử chuyển nhóm phải được giữ.
3. API danh sách thành viên trả tối đa 50 người mỗi trang.
4. Một số Group có thể lên tới hàng triệu thành viên.
5. Khi move thành công, quyền truy cập tài liệu thuộc Group A phải bị thu hồi theo chính sách ngay tại nguồn có thẩm quyền.
6. Danh sách thành viên cho phép cập nhật chậm một khoảng nhỏ có kiểm soát.
7. Client có thể retry do timeout.

### 22.1. Mô hình dữ liệu gợi ý

Nguồn:

~~~json
{
  "_id": "user-101",
  "currentGroupId": "group-A",
  "version": 7
}
~~~

Event:

~~~json
{
  "_id": "group-move-5001",
  "userId": "user-101",
  "fromGroupId": "group-A",
  "toGroupId": "group-B",
  "sourceVersion": 8,
  "actorId": "admin-3"
}
~~~

Projection trước move:

~~~json
{
  "_id": "group-A#user-101",
  "groupId": "group-A",
  "userId": "user-101",
  "sourceVersion": 7
}
~~~

Projection sau move:

~~~json
{
  "_id": "group-B#user-101",
  "groupId": "group-B",
  "userId": "user-101",
  "sourceVersion": 8
}
~~~

### 22.2. Câu hỏi

1. Nếu `currentGroupId` là thuộc tính thường có index, move có thể là một update nguồn không? Index phải thay đổi gì?
2. Nếu Group có mảng `members[]` chứa hàng triệu ID, nguy cơ kích thước và contention là gì?
3. Với read model khóa `(groupId, userId)`, move cần những thao tác nào?
4. API kiểm tra quyền nên dựa vào nguồn authoritative hay bản chiếu có thể stale?
5. Làm sao xử lý hai request `A → B` và `A → C` có cùng expected version?
6. Nếu retry `group-move-5001` sau khi server đã commit, làm sao trả kết quả đúng?
7. Nếu event version 9 đến trước version 8, projection cần làm gì?
8. Nếu Group A có 10 triệu thành viên, một partition chứa toàn bộ có phù hợp không?
9. Những metric nào phát hiện danh sách Group A/B lệch nguồn?
10. Viết một ADR ngắn so sánh nhúng mảng, tham chiếu và read model theo Group.

### 22.3. Hướng giải quyết

- Giữ `userId` bất biến, `currentGroupId` là trạng thái hiện hành có kiểm soát version.
- Không nhúng danh sách thành viên không giới hạn trong document Group.
- Dùng association/index/bảng đọc theo Group để phân trang; cân nhắc bucketing khi group quá lớn.
- Dùng nguồn authoritative hoặc cơ chế có bảo đảm tương ứng để kiểm tra quyền ngay sau move.
- Event mang `requestId` và `sourceVersion`; consumer xử lý idempotent và không để version cũ ghi đè version mới.
- Lịch sử Move lưu ở một nguồn audit riêng, không ghi đè.
- Đối soát định kỳ ID, version, count và nhóm hiện hành; theo dõi projection lag và tỷ lệ bản ghi sai.

### 22.4. Ma trận cho bài thực hành

| Tiêu chí | Nhúng members trong Group | User có `currentGroupId` | User nguồn + projection theo Group |
|---|---|---|---|
| Đọc danh sách thành viên | Thuận tiện khi nhỏ | Cần index theo group | Query nhóm tối ưu |
| Nhóm hàng triệu thành viên | Không thuận lợi | Có thể dùng index phù hợp | Có thể chia bucket/read model |
| Chuyển A → B | Sửa hai Group document | Update một User và index | Update nguồn + đổi projection |
| Kiểm tra quyền sau move | Cần xác định nguồn đáng tin | Có thể dựa trên nguồn User | Nguồn User đúng; projection có thể trễ |
| Lịch sử chuyển | Cần event riêng | Cần event riêng | Cần event riêng |
| Vận hành | Mảng lớn/contended | Index và query tuning | Lag, retry, đối soát, backfill |

---

## 23. Ghi lại đánh đổi bằng Architecture Decision Record

Một quyết định cần mô tả **tần suất chuyển nhóm**, **mẫu đọc**, **chi phí ghi** và **bảo đảm nhất quán**. Ví dụ:

~~~markdown
# ADR: Chuyển Task giữa Project

## Bối cảnh
- Query: danh sách Task theo Project, 30 bản ghi/trang.
- Move: Task có thể đổi Project thường xuyên.
- Bất biến: taskId không đổi; chỉ một Project hiện hành.
- Yêu cầu: read-your-writes trên Task nguồn.
- Projection danh sách được phép trễ có giới hạn.

## Phương án
A. Nhúng Task trong Project.tasks[].
B. Task nguồn theo taskId, projectId là thuộc tính có index.
C. Task nguồn theo taskId + tasks_by_project bất đồng bộ.

## Đánh đổi
- Đọc: số query, partition, p95/p99.
- Ghi: số bản ghi/index phải cập nhật trên mỗi move.
- Lưu trữ: bản sao, index, tombstone, backup.
- Nhất quán: nguồn thật, mức stale, read-your-writes.
- Độ phức tạp: retry, migration, backfill, reconciliation.

## Quyết định
Chọn ... vì ... (số đo).
Chấp nhận ... (bất lợi).
Không chọn các phương án còn lại vì ...

## Bảo đảm
- Kiểm tra quyền trên nguồn và đích.
- Conditional update với expectedVersion.
- Idempotency key cho request Move.
- Version/event ordering cho projection.
- Metric, alert và quy trình đối soát.

## Xem xét lại khi
- Tần suất move tăng vượt dự báo.
- Một Project trở thành hot partition.
- p95/p99 hoặc lag vượt ngân sách.
- Yêu cầu nhất quán/retention thay đổi.
~~~

Bản ghi kỹ thuật không nên chỉ nói “phương án B dễ hơn”. Hãy nêu **vì sao dễ**, các tác vụ vẫn cần làm và điều kiện mà quyết định có thể không còn hợp lý.

## 24. Các ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Đổi Project chỉ là đổi một field.” | Có thể phải thay index, projection, cache, counter hoặc partition key. |
| “Dữ liệu được nhúng thì chuyển con cũng nguyên tử.” | Chuyển giữa hai document cần transaction/giao thức phù hợp. |
| “Khóa theo nhóm luôn tốt.” | Đọc nhóm thuận tiện nhưng rekey đắt khi nhóm thay đổi thường xuyên. |
| “Chỉ cần copy B rồi delete A là xong.” | Cần xử lý lỗi giữa hai bước, retry, version và quan sát stale. |
| “CQL BATCH là SQL transaction toàn cục.” | Bảo đảm và chi phí khác nhau; cần hiểu phạm vi của Cassandra. |
| “Đổi thuộc tính đã được đánh index không tốn chi phí phụ.” | DBMS phải bảo trì index, có thể thêm write amplification. |
| “Event đến sau luôn mới hơn.” | Event có thể đến sai thứ tự; dùng version/sequence có thẩm quyền. |
| “Có requestId thì tự động idempotent.” | Phải lưu/kiểm tra requestId một cách cạnh tranh an toàn. |
| “Bộ đếm cộng trừ sau event luôn đúng.” | Event lặp có thể làm count sai nếu thiếu deduplication. |
| “Snapshot lịch sử phải cập nhật theo nhóm hiện tại.” | Snapshot có thể phải bất biến; không đồng nhất với projection. |
| “Migration chỉ cần backfill một lần.” | Cần bắt ghi mới, checkpoint, đối soát và cutover. |
| “Dữ liệu qua tenant chỉ cần sửa tenantId.” | Tenant là ranh giới bảo mật, retention và quyền cần được kiểm tra. |

## 25. Kết luận

Trong NoSQL, một quan hệ có thể được lưu thành **thuộc tính tham chiếu, mảng nhúng, khóa phân vùng, association document, bản chiếu theo truy vấn hoặc cạnh graph**. Cách biểu diễn quyết định chi phí thay đổi quan hệ và chuyển dữ liệu giữa các nhóm.

Nếu dữ liệu hiếm khi đổi nhóm và chủ yếu đọc theo nhóm, khóa theo nhóm có thể rất hiệu quả. Nếu dữ liệu thường xuyên đổi chủ sở hữu, trạng thái hoặc nhóm, nên cân nhắc **định danh nguồn ổn định** với thuộc tính/quan hệ có thể cập nhật và index hoặc read model phục vụ các truy vấn cần thiết.

Một thao tác move đáng tin cậy phải giải quyết **trạng thái nguồn, danh sách nhóm cũ/mới, retry, cập nhật đồng thời, bản sao bị trễ, audit và phân quyền**. Move hàng loạt còn cần backfill, checkpoint, catch-up, đối soát và kế hoạch cutover/rollback.

**Thiết kế NoSQL theo truy vấn không chỉ hỏi “đọc nhóm nào nhanh nhất?”, mà còn phải hỏi “khi dữ liệu đổi nhóm, hệ sẽ cập nhật, giữ đúng và phục hồi như thế nào?”**
