# Khóa bất biến, đổi khóa và chuyển dữ liệu sang partition khác trong Cassandra

## 1. Bài toán: một bản ghi cần chuyển sang nhóm khác

Trong **Spring Data Cassandra**, ứng dụng Java có thể truy cập Apache Cassandra thông qua entity mapping, repository, **CassandraTemplate** và CQL. Nhưng khi nghiệp vụ yêu cầu **đổi giá trị một phần khóa chính**, cách làm khác đáng kể so với việc sửa một cột thông thường.

Ví dụ hệ thống quản lý công việc hiển thị danh sách task theo **đội phụ trách và ngày đến hạn**. Task 42 ban đầu thuộc đội A, hạn ngày 10/03. Sau đó người dùng chuyển task sang đội B, hạn ngày 12/03. Nếu đội và ngày nằm trong **partition key**, đây là thay đổi vị trí logic của dữ liệu. Cassandra không cung cấp lệnh “đổi partition key của hàng hiện tại” như một thao tác cập nhật trực tiếp.

Các mục tiêu của bài học:

1. Phân biệt **partition key**, **clustering key** và cột dữ liệu có thể cập nhật.
2. Giải thích vì sao muốn đổi giá trị khóa phải **ghi hàng với khóa mới và loại bỏ hàng với khóa cũ**.
3. Thực hiện quy trình di chuyển với CQL và hiểu những tình huống lỗi, retry, concurrency và tính nhất quán.
4. Ánh xạ khóa tổng hợp trong Spring Data Cassandra mà không vô tình tạo thêm hàng hoặc để lại dữ liệu cũ.
5. Thiết kế đường tra cứu theo **định danh ổn định** khi bản ghi phải đổi partition nhiều lần.

Đây là kiến thức cốt lõi của chương **Khóa và phân vùng**, đồng thời liên hệ trực tiếp đến thiết kế bảng theo truy vấn, paging và hiệu năng trên hệ dữ liệu phân tán.

## 2. Khóa của Cassandra quyết định điều gì?

Xét bảng chuyên phục vụ truy vấn “liệt kê task của một đội trong một ngày”:

~~~sql
CREATE TABLE tasks_by_team_day (
    tenant_id uuid,
    team_id uuid,
    due_day date,
    task_id uuid,
    title text,
    state text,
    revision bigint,
    PRIMARY KEY ((tenant_id, team_id, due_day), task_id)
);
~~~

Trong cú pháp **`PRIMARY KEY ((tenant_id, team_id, due_day), task_id)`**:

| Thành phần | Vai trò | Hệ quả khi muốn đổi |
| --- | --- | --- |
| `tenant_id` | Phần thứ nhất của **partition key tổng hợp** | Đổi tenant là đổi partition; có thể còn liên quan ranh giới quyền truy cập |
| `team_id` | Phần thứ hai của partition key | Chuyển task sang đội khác đòi hỏi ghi hàng ở partition mới |
| `due_day` | Phần thứ ba của partition key | Đổi ngày đến hạn cũng đòi hỏi ghi hàng ở partition mới |
| `task_id` | **Clustering column**, phân biệt task trong một partition | Đổi giá trị này tạo khóa chính mới dù partition có thể giữ nguyên |
| `title`, `state`, `revision` | Cột thông thường | Có thể cập nhật tại khóa chính hiện tại |

Partition key được Cassandra dùng để tính token và xác định vị trí replica của partition theo cơ chế phân bố dữ liệu. Clustering key xác định vị trí/thứ tự hàng **bên trong partition**. Toàn bộ các thành phần của khóa chính cùng xác định duy nhất một hàng trong **bảng đó**.

Một câu cập nhật các cột thường:

~~~sql
UPDATE tasks_by_team_day
SET title = ?, state = ?, revision = ?
WHERE tenant_id = ? AND team_id = ? AND due_day = ? AND task_id = ?;
~~~

Đây là dạng CQL hợp lệ khi tham số `WHERE` cung cấp đầy đủ khóa hàng. Ngược lại, ý tưởng sau **không hợp lệ** vì `team_id` thuộc primary key:

~~~sql
-- MINH HỌA LỆNH SAI: primary-key column không được SET
UPDATE tasks_by_team_day
SET team_id = ?
WHERE tenant_id = ? AND team_id = ? AND due_day = ? AND task_id = ?;
~~~

**Quy tắc:** Cassandra không hỗ trợ `UPDATE ... SET` hoặc `DELETE` để “sửa tại chỗ” một thành phần khóa chính. Cần ghi **một hàng mới với khóa mới** và xóa **hàng cũ với khóa cũ**. Đổi clustering key cũng theo nguyên tắc này; không chỉ riêng partition key mới có tính bất biến.

> “Khóa bất biến” nói về **định danh của hàng lưu trong Cassandra**. Ở tầng nghiệp vụ, giá trị như đội phụ trách hoặc ngày đến hạn vẫn có thể thay đổi; ứng dụng phải biểu diễn thay đổi đó bằng các thao tác lưu trữ phù hợp.

## 3. Phân biệt đổi khóa với cập nhật cột và tái cân bằng cluster

Ba tình huống dễ bị nhầm là:

| Tình huống | Điều xảy ra | Có cần ghi lại hàng với khóa mới? |
| --- | --- | --- |
| Sửa `title`, `state` của task | Thay dữ liệu tại cùng primary key | **Không** |
| Chuyển `team_id` hoặc `due_day` | Primary key mới, do đó đường truy cập logic mới | **Có: insert/upsert khóa mới, delete khóa cũ** |
| Thêm/bớt node Cassandra làm token ownership thay đổi | Cassandra có thể **streaming** dữ liệu giữa các node khi thay đổi topology | **Không cần ứng dụng đổi partition key** |

**Thay đổi partition key ở tầng ứng dụng** không có nghĩa gọi lệnh chuyển một SSTable từ node A sang node B. Một thao tác ghi với khóa mới đi đến replica được xác định từ khóa mới; việc xóa khóa cũ là một mutation khác. Hai khóa thậm chí có thể nằm trên các replica khác nhau.

Điều này lý giải vì sao **Spring Data repository** không có phép “rename primary key” tương đương cập nhật trường Java: một bài toán di chuyển có thể liên quan nhiều partition, nhiều bản sao và nhiều trạng thái trung gian.

## 4. Cách di chuyển dữ liệu cơ bản bằng CQL

Giả sử một task có định danh `task_id` cố định, cần đổi từ:

- **Khóa cũ:** `(tenant_id=T, team_id=A, due_day=2026-03-10, task_id=X)`.
- **Khóa mới:** `(tenant_id=T, team_id=B, due_day=2026-03-12, task_id=X)`.

Quy trình cơ bản:

~~~mermaid
flowchart TD
    A[Đọc hàng theo khóa cũ] --> B[Chuẩn bị khóa mới và dữ liệu cần giữ]
    B --> C[INSERT hoặc upsert hàng ở khóa mới]
    C --> D{Ghi và xác minh theo yêu cầu nghiệp vụ thành công?}
    D -->|Chưa rõ hoặc thất bại| E[Đối chiếu trạng thái, retry an toàn]
    E --> C
    D -->|Có| F[DELETE hàng theo khóa cũ]
    F --> G[Đối chiếu kết quả và hoàn tất]
~~~

### Bước 1 — Đọc bản ghi cũ theo đầy đủ khóa

~~~sql
SELECT title, state, revision
FROM tasks_by_team_day
WHERE tenant_id = ? AND team_id = ? AND due_day = ? AND task_id = ?;
~~~

Đường đọc này nhắm đúng một hàng trong partition đã biết. Cần bảo toàn các giá trị nghiệp vụ cần chuyển và ghi nhận **phiên bản dữ liệu** để tránh ghi đè thay đổi mới từ luồng khác.

### Bước 2 — Ghi bản sao theo khóa mới

~~~sql
INSERT INTO tasks_by_team_day (
    tenant_id, team_id, due_day, task_id, title, state, revision
) VALUES (?, ?, ?, ?, ?, ?, ?);
~~~

Tham số ở câu `INSERT` dùng **khóa mới**; `task_id` giữ nguyên để định danh task ở tầng nghiệp vụ. Cassandra thực hiện **upsert**: ghi cùng primary key có thể cập nhật các cột được nêu thay vì tạo bản ghi thứ hai tại chính khóa đó. Tuy nhiên, việc thử lại vẫn phải xét cạnh tranh giữa các writer và giá trị timestamp/TTL.

### Bước 3 — Xóa bản ghi ở khóa cũ

~~~sql
DELETE FROM tasks_by_team_day
WHERE tenant_id = ? AND team_id = ? AND due_day = ? AND task_id = ?;
~~~

Tham số ở câu `DELETE` phải là **khóa cũ**. Nếu vô tình dùng khóa mới, có thể xóa chính dữ liệu vừa ghi và để lại hàng cũ. Sau bước này, Cassandra ghi dấu xóa (**tombstone**); dữ liệu không nhất thiết biến mất khỏi ổ đĩa ngay lập tức. Compaction và các cơ chế phân tán xử lý vòng đời tombstone sau đó.

### Bước 4 — Kiểm chứng kết quả

Tùy yêu cầu ứng dụng, xác minh hàng với khóa mới đọc được, hàng với khóa cũ không còn hiện trong đường truy cập chính, và không có cập nhật đồng thời bị bỏ mất. **Không chỉ kiểm tra kết quả HTTP của một lệnh** khi yêu cầu có tính quan trọng cao. Sử dụng mức nhất quán đọc/ghi phù hợp, chính sách xử lý timeout rõ ràng và cơ chế đối soát khi kết quả không chắc chắn.

**Giới hạn của quy trình cơ bản:** nó có ít nhất hai mutation tách biệt, có thể thất bại ở giữa. Do đó chỉ thích hợp để minh họa thao tác khóa, chưa đủ cho luồng nghiệp vụ cần điều khiển cạnh tranh hay khôi phục tự động.

## 5. Tại sao INSERT rồi DELETE không phải giao dịch di chuyển nguyên tử?

Một lần chuyển từ partition A sang partition B không mang sẵn bảo đảm “người đọc chỉ thấy đúng một hàng tại mọi thời điểm”.

| Thời điểm hoặc lỗi | Trạng thái có thể quan sát | Rủi ro |
| --- | --- | --- |
| Chưa ghi khóa mới | Chỉ còn hàng cũ | Truy vấn vào đội mới không thấy task |
| Ghi khóa mới thành công, chưa xóa cũ | **Hai hàng** cùng mô tả task ở hai partition | Danh sách theo đội/ngày có thể hiển thị trùng |
| Xóa cũ trước khi ghi mới | Có khoảng thời gian **không có hàng** ở cả hai vị trí | Mất khả năng tìm task trong lúc chuyển |
| Ghi mới timeout nhưng thực tế một số replica đã ghi | Trạng thái kết quả chưa chắc chắn | Retry/xóa sớm có thể làm dữ liệu không như mong muốn |
| Writer khác cập nhật hàng cũ khi đang chuyển | Bản sao mới có thể thiếu thay đổi vừa xảy ra | Mất cập nhật logic hoặc xuất hiện dữ liệu cũ trở lại |
| Xóa cũ thành công nhưng worker chưa ghi nhận hoàn thành | Hàng mới đã có, luồng điều phối có thể chạy lại | Cần nhận ra thao tác đã hoàn tất thay vì tạo tác dụng phụ mới |

### Logged batch có giúp di chuyển an toàn hoàn toàn không?

Cassandra hỗ trợ **batch**. Với logged batch, cơ chế batch log hỗ trợ việc các mutation trong batch cuối cùng được áp dụng khi vượt qua một số loại sự cố; tuy nhiên **batch không phải transaction nhiều partition với tính cô lập (isolation) kiểu cơ sở dữ liệu quan hệ**. Người đọc có thể quan sát trạng thái trung gian trên các partition khác nhau. Batch cũng không giải quyết việc nhiều luồng cùng thay đổi dữ liệu nghiệp vụ và không phải công cụ tăng tốc mặc định cho những ghi rải khắp cluster.

Vì vậy **đừng tuyên bố “dùng BEGIN BATCH là chuyển partition nguyên tử đối với mọi reader”**. Cần xem yêu cầu nghiệp vụ cho phép hiển thị trùng tạm thời, bỏ sót tạm thời hay đòi hỏi một định danh tra cứu ổn định và quy trình điều phối riêng.

### Lightweight transactions cũng có phạm vi giới hạn

Các điều kiện **`IF`** trong Cassandra thực thi bằng **lightweight transaction (LWT)**, hữu ích để bảo vệ cập nhật có điều kiện trong phạm vi khóa/partition tương ứng. Ví dụ, ứng dụng có thể chỉ cập nhật một bản ghi trạng thái chuyển khi `revision` vẫn bằng giá trị dự kiến. Nhưng **LWT trên một partition không biến việc INSERT sang partition mới và DELETE ở partition cũ thành một transaction có isolation xuyên partition**.

LWT có chi phí đồng thuận và độ trễ; chỉ dùng khi cần điều kiện cạnh tranh thật sự.

## 6. Thiết kế định danh ổn định và bảng chỉ vị trí

Một bài toán phổ biến: **task_id phải giữ nguyên**, dù task thay đổi đội/ngày. Nếu mọi truy vấn theo ID phải biết `team_id` và `due_day` hiện tại, client rất khó tìm task sau khi di chuyển.

Giải pháp thực tế là tách:

- **Định danh nghiệp vụ ổn định:** `(tenant_id, task_id)`.
- **Vị trí phục vụ danh sách:** `(tenant_id, team_id, due_day, task_id)` trong `tasks_by_team_day`.
- **Bảng tra cứu theo ID:** lưu vị trí mới nhất và trạng thái chuyển đổi, truy vấn trực tiếp bằng định danh ổn định.

Ví dụ bảng tra cứu:

~~~sql
CREATE TABLE task_location_by_id (
    tenant_id uuid,
    task_id uuid,
    team_id uuid,
    due_day date,
    revision bigint,
    move_state text,
    PRIMARY KEY ((tenant_id, task_id))
);
~~~

Partition key của `task_location_by_id` là **cặp tenant_id + task_id**, nên thao tác tìm vị trí theo ID có đường truy cập cụ thể và tránh dồn toàn bộ task của một tenant vào một partition duy nhất. Ví dụ:

~~~sql
SELECT team_id, due_day, revision, move_state
FROM task_location_by_id
WHERE tenant_id = ? AND task_id = ?;
~~~

Ứng dụng có thể đọc vị trí từ bảng này rồi tra bảng danh sách theo khóa đầy đủ. Hai bảng mang **hai bản biểu diễn có chủ đích** cho hai access pattern khác nhau; điều này phù hợp mô hình dữ liệu Cassandra. Chi phí đánh đổi là phải tổ chức cập nhật, đối soát và xử lý tình huống lệch trạng thái.

### 6.1. Điều phối một lần chuyển với trạng thái và revision

Một hướng thiết kế đáng cân nhắc với ứng dụng quan trọng:

1. **Đặt định danh thao tác chuyển** (ví dụ `move_id`) hoặc sử dụng revision tăng dần. Yêu cầu lặp lại cùng thao tác phải nhận diện được.
2. **Giành quyền chuyển:** sử dụng cập nhật có điều kiện trên hàng `task_location_by_id` để chuyển từ `ACTIVE` sang `MOVING` nếu revision vẫn bằng giá trị đã đọc. Với LWT, kiểm tra kết quả `[applied]` thay vì xem câu CQL chạy xong là đã đổi thành công.
3. **Ghi hàng đích** với cùng định danh ổn định và revision dự kiến. Bảo đảm retry không sinh sự kiện phụ không mong muốn.
4. **Chuyển con trỏ vị trí** sang khóa mới theo điều kiện phù hợp, chỉ sau khi ghi đích đã được xác nhận theo mức nhất quán yêu cầu.
5. **Xóa hàng nguồn**, đối soát hai vị trí, đánh dấu hoàn tất. Nếu thao tác bị ngắt, worker có thể tiếp tục từ trạng thái còn lưu.

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Đã có hàng ở vị trí cũ
    ACTIVE --> MOVING: Nhận quyền chuyển và lưu revision
    MOVING --> TARGET_READY: Đã ghi/xác minh hàng đích
    TARGET_READY --> POINTER_UPDATED: Chuyển vị trí tra cứu sang khóa mới
    POINTER_UPDATED --> CLEANUP: Xóa hàng nguồn và đối soát
    CLEANUP --> ACTIVE: Hoàn tất với revision mới
~~~

Sơ đồ mô tả **trạng thái nghiệp vụ logic**; bảng ví dụ chỉ có `move_state` và `revision`, nên nếu triển khai cần bổ sung cách lưu `move_id`, khóa nguồn/đích, giai đoạn xử lý hoặc nhật ký thao tác để khôi phục đầy đủ. Các trạng thái trong sơ đồ không tự được Cassandra sinh ra.

Một ví dụ thao tác bảo vệ giai đoạn khởi đầu bằng điều kiện:

~~~sql
UPDATE task_location_by_id
SET move_state = 'MOVING'
WHERE tenant_id = ? AND task_id = ?
IF move_state = 'ACTIVE' AND revision = ?;
~~~

Câu lệnh áp dụng trong **partition ổn định của hàng chỉ vị trí**, giúp tránh hai luồng cùng nắm quyền chuyển tại thời điểm cập nhật có điều kiện. Nhưng để bảo vệ toàn bộ vòng đời, hệ thống còn cần chiến lược lease/timeout phục hồi, kiểm soát các writer của task, và phân biệt retry của cùng một thao tác với yêu cầu mới.

### 6.2. Nhất quán giữa bảng theo ID và bảng theo danh sách

Trong khoảng chuyển đổi, danh sách của đội cũ và đội mới có thể tạm thời lệch nhau. Có vài lựa chọn thiết kế:

- **Chấp nhận nhất quán cuối cùng** cho màn hình danh sách, để luồng cleanup xử lý hàng cũ.
- **Xác thực bằng định danh ổn định** khi xử lý thao tác quan trọng: đọc trạng thái vị trí hiện tại, kiểm tra revision rồi mới thực hiện nghiệp vụ.
- **Dùng luồng sự kiện hoặc outbox có khả năng phục hồi** để cập nhật những bảng chiếu (projection) và đối soát định kỳ.
- **Đổi mô hình lưu trữ** nếu sản phẩm thực sự đòi hỏi một thao tác di chuyển nguyên tử và truy vấn tức thời trên nhiều partition; không nên hứa hẹn mức bảo đảm Cassandra không cung cấp.

Đây là bài toán **định nghĩa hành vi cho các trạng thái trung gian**, không chỉ viết thêm câu DELETE.

## 7. Liên hệ với Spring Data Cassandra: entity và repository

Một cách biểu diễn khóa tổng hợp trong Spring Data Cassandra là dùng **`@PrimaryKeyClass`** cùng các **`@PrimaryKeyColumn`**. Ví dụ minh họa về cấu trúc mapping:

~~~java
@PrimaryKeyClass
public class TaskByTeamDayKey implements java.io.Serializable {
    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "team_id", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private UUID teamId;

    @PrimaryKeyColumn(
        name = "due_day", ordinal = 2, type = PrimaryKeyType.PARTITIONED)
    private LocalDate dueDay;

    @PrimaryKeyColumn(
        name = "task_id", ordinal = 3, type = PrimaryKeyType.CLUSTERED)
    private UUID taskId;

    // Constructors, getters/setters, equals() và hashCode().
}

@Table("tasks_by_team_day")
public class TaskByTeamDay {
    @PrimaryKey
    private TaskByTeamDayKey key;

    @Column("title")
    private String title;

    @Column("state")
    private String state;

    @Column("revision")
    private Long revision;

    // Constructors, getters/setters và các phương thức nghiệp vụ.
}
~~~

Các annotation trên chỉ thể hiện **ý tưởng mapping**; cần khai báo import, constructor, phương thức và kiểm tra khả năng tương thích với phiên bản Spring Data Cassandra đang sử dụng. Nên đảm bảo `equals/hashCode` của khóa có ngữ nghĩa theo đủ thành phần định danh.

Repository:

~~~java
public interface TaskByTeamDayRepository
        extends CassandraRepository<TaskByTeamDay, TaskByTeamDayKey> {
}
~~~

Giả sử đã xác định chính xác `oldKey`, `newKey` và trạng thái dữ liệu, mã minh họa hai mutation ở mức cao:

~~~java
TaskByTeamDay source = repository.findById(oldKey)
    .orElseThrow(() -> new IllegalStateException("Task not found"));

TaskByTeamDay copy = copyWithNewKey(source, newKey);
repository.save(copy);        // INSERT/upsert tại primary key mới
repository.deleteById(oldKey); // Xóa hàng tại primary key cũ
~~~

**Đoạn mã này chỉ minh họa cơ chế**, chưa phải quy trình chuyển an toàn cho production: thiếu kiểm soát cạnh tranh, phân biệt trạng thái timeout, kiểm tra replica và cơ chế tiếp tục sau lỗi. Quan trọng hơn, **không sửa `source.getKey().setTeamId(...)` rồi kỳ vọng Cassandra tự di chuyển hàng và xóa hàng cũ**. Một lệnh save với khóa mới là một mutation đến một định danh hàng khác.

Nếu cần kiểm soát truy vấn, consistency, TTL hoặc các điều kiện CQL chuyên biệt, có thể sử dụng **CassandraTemplate** hoặc Java driver. Công cụ truy cập nào cũng phải tôn trọng bất biến của primary key và giới hạn giao dịch giữa các partition.

## 8. Những yếu tố thường bị bỏ sót khi chuyển partition

### 8.1. Race condition và lost update

Trong khi worker chuyển task, người dùng có thể đổi `state` hoặc `title` tại vị trí cũ. Nếu worker sao chép một snapshot cũ sang vị trí mới rồi xóa nguồn, thay đổi vừa xảy ra có thể bị bỏ sót. Giải pháp thường cần:

- Một điểm điều phối có revision/ownership rõ ràng cho mỗi task.
- Các writer kiểm tra trạng thái `MOVING` và biết cách chuyển hướng hoặc từ chối thao tác tạm thời.
- Quy trình idempotent có thể tiếp tục sau crash, cộng với đối soát những bản chiếu phụ.

**Timestamp ghi của Cassandra và last-write-wins không thay thế cho kiểm soát phiên bản nghiệp vụ.** Hai khóa khác nhau là hai hàng khác nhau, không tự xung đột theo cùng một primary key.

### 8.2. TTL và hạn lưu dữ liệu

Nếu dữ liệu nguồn có **TTL**, thực hiện INSERT mới mà không cân nhắc TTL có thể làm bản sao mới sống lâu hơn mục tiêu lưu trữ. TTL trong Cassandra có thể gắn với từng cột và cách ghi; phần thời gian còn lại không nhất thiết bằng TTL ban đầu. Khi cần bảo toàn vòng đời dữ liệu, xác định chính sách hết hạn theo một **thời điểm tuyệt đối** ở tầng ứng dụng rồi tính TTL phù hợp cho hàng đích, đồng thời xử lý tình huống dữ liệu hết hạn ngay trong lúc chuyển.

Có thể kiểm tra TTL hiện tại của cột thông thường trong CQL:

~~~sql
SELECT TTL(title), TTL(state)
FROM tasks_by_team_day
WHERE tenant_id = ? AND team_id = ? AND due_day = ? AND task_id = ?;
~~~

Không giả định rằng mọi cột cùng TTL, hay mọi cột đều có TTL. Việc xóa hàng cũ và dữ liệu hết hạn đều có thể sinh **tombstone**, làm tăng chi phí đọc/compaction nếu chuyển hàng với tần suất lớn.

### 8.3. Consistency, timeout và retry

Với dữ liệu ở nhiều replica, một mutation được xác nhận ở mức nhất quán nào còn ảnh hưởng khả năng đọc thấy kết quả từ một truy vấn kế tiếp. Chọn consistency level dựa trên replication factor và yêu cầu nghiệp vụ; chẳng hạn trong một datacenter với RF = 3, `LOCAL_QUORUM` thường cần phản hồi từ hai replica cho thao tác tương ứng.

Đặc biệt, **WriteTimeout không khẳng định mutation chưa được áp dụng**. Nếu retry một bước di chuyển, phải nhận diện được cùng task/khóa/phiên bản và xử lý sao cho không sinh tác dụng phụ lặp lại. Với thao tác nhiều bước, cần lưu tiến độ bền vững; đừng chỉ retry nguyên khối một cách vô điều kiện.

### 8.4. Thiết kế partition, paging và tải hệ thống

Nếu `tasks_by_team_day` dùng `(tenant_id, team_id, due_day)`, hãy đo số task trong mỗi partition và khả năng có **hot partition** ở đội lớn hoặc ngày đặc biệt. Chuyển quá nhiều task cùng lúc sẽ tạo lưu lượng đọc/ghi và tombstone; nên chia lô và điều tiết tốc độ.

Với màn hình liệt kê task theo đội/ngày, Cassandra paging dựa trên **paging state**. Khi dữ liệu đang được chuyển giữa hai partition, hai trang truy vấn ở hai thời điểm không tự tạo thành một ảnh chụp nhất quán toàn cục. Nếu giao diện cần chống hiển thị trùng, có thể deduplicate theo **`(tenant_id, task_id)`** ở tầng thích hợp và có chiến lược refresh khi vị trí thay đổi.

### 8.5. Đổi partition key có phải cách giải quyết mọi truy vấn mới?

Không. Nếu một task cần được tìm bằng nhiều hướng — theo người tạo, đội phụ trách, trạng thái, ngày đến hạn — đừng cố ép một bảng phục vụ tất cả truy vấn bằng `ALLOW FILTERING` hoặc liên tục “chuyển hàng” theo bộ lọc hiện tại. Cassandra thường dùng **các bảng được thiết kế riêng cho access pattern**, chấp nhận sao chép dữ liệu có chủ đích và tổ chức đồng bộ ở tầng ứng dụng.

## 9. Thực hành: đổi đội và ngày đến hạn

**Mục tiêu:** từ một task ở khóa cũ, tạo task tại khóa mới, kiểm chứng kết quả và nhận diện được rủi ro phân tán.

### Phần A — Quan sát hành vi khóa

1. Tạo bảng `tasks_by_team_day` trong một keyspace thử nghiệm.
2. Ghi một task với `tenant_id`, `team_id=A`, `due_day=2026-03-10` và `task_id=X`.
3. Chạy UPDATE chỉ thay `title`; xác nhận hàng vẫn được đọc bằng **khóa cũ**.
4. Thử giải thích vì sao không thể đặt `team_id` trong phần `SET` của UPDATE.
5. Viết INSERT với `team_id=B` và `due_day=2026-03-12`, giữ nguyên `task_id=X`. Truy vấn cả khóa cũ và khóa mới: lúc này có thể thấy **hai hàng**.
6. Chạy DELETE bằng **khóa cũ** rồi truy vấn cả hai vị trí để xác minh.

### Phần B — Giả lập lỗi từng bước

| Điểm dừng mô phỏng | Câu hỏi cần trả lời |
| --- | --- |
| Trước INSERT đích | Task được tìm ở đâu? |
| Sau INSERT đích, trước DELETE nguồn | Hai màn hình danh sách có thể hiện task không? |
| Sau DELETE nguồn | Nếu worker khởi động lại và chạy tiếp, làm sao biết cần tiếp tục từ bước nào? |
| INSERT đích timeout | Có được xóa nguồn ngay chỉ vì thấy timeout không? |
| Có writer cập nhật nguồn cùng lúc | Làm sao phát hiện và tránh ghi đè phiên bản mới? |

### Phần C — Thiết kế quy trình production trên giấy

Vẽ bảng `task_location_by_id` làm điểm tra cứu ổn định. Mô tả trạng thái `ACTIVE` → `MOVING` → chuyển con trỏ sang khóa mới → cleanup; chỉ rõ vị trí cần **LWT**, nơi có thể **retry an toàn**, thông tin cần lưu để khôi phục crash và chính sách khi danh sách tạm thời trùng.

**Tiêu chí đạt:** người học không chỉ chạy được INSERT/DELETE mà còn giải thích tại sao đổi khóa là thao tác tạo/xóa hàng, nhận diện trạng thái trung gian và đề xuất được cách khôi phục sau một lỗi cụ thể.

## 10. Các hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`team_id` là field Java, cứ set rồi save là Cassandra sửa partition.” | Save với khóa mới ghi sang hàng khác; hàng khóa cũ không tự bị xóa |
| “Chỉ partition key bất biến, clustering key có thể đổi trực tiếp.” | Mọi thành phần primary key đều góp phần định danh hàng, không được sửa bằng `SET` |
| “INSERT rồi DELETE luôn nguyên tử.” | Hai mutation khác partition có thể tạo trạng thái trùng/thiếu tạm thời |
| “Logged batch cho phép tất cả reader thấy dữ liệu chuyển cùng lúc.” | Batch không cung cấp isolation xuyên partition như transaction quan hệ |
| “LWT làm cho mọi bảng thay đổi cùng lúc.” | Điều kiện LWT có phạm vi, không biến nhiều partition thành một giao dịch nguyên tử toàn cục |
| “WriteTimeout nghĩa là chắc chắn chưa ghi gì.” | Mutation có thể đã đến một số replica; phải đối soát trước khi hành động tiếp |
| “Xóa hàng là giải phóng dung lượng ngay.” | DELETE tạo tombstone; việc thu hồi vật lý phụ thuộc cơ chế lưu trữ/compaction |
| “Task ID giống nhau ở hai partition là cùng một hàng Cassandra.” | Hai primary key khác nhau là hai hàng, dù đại diện cùng thực thể nghiệp vụ |
| “Chỉ cần đổi key là giải quyết được mọi truy vấn.” | Thiết kế bảng phải theo access pattern, có thể cần nhiều bảng và đường tra cứu |

## 11. Tự kiểm tra

1. Với `PRIMARY KEY ((tenant_id, team_id, due_day), task_id)`, những cột nào quyết định partition và cột nào là clustering key?
2. Vì sao thay `state` khác với thay `team_id`? Nếu đổi `task_id` mà không đổi các trường partition thì sao?
3. Vì sao hai lần ghi cùng `task_id` nhưng khác `team_id` lại có thể tạo hai hàng?
4. Trình bày thứ tự INSERT/DELETE và hai điểm có thể khiến ứng dụng mất tính nhất quán quan sát được.
5. Trong quy trình di chuyển, khi nào việc retry là an toàn? Vì sao cần idempotency và revision?
6. Vì sao logged batch và LWT không tự giải quyết yêu cầu cập nhật nguyên tử trên hai partition?
7. Bảng `task_location_by_id` giúp gì cho việc tra task bằng ID ổn định? Nó tạo thêm nghĩa vụ đồng bộ nào?
8. Nếu dữ liệu có TTL, điều gì xảy ra khi ghi lại ở partition mới với TTL mặc định?
9. Tombstone, hot partition và việc di chuyển nhiều hàng ảnh hưởng hiệu năng thế nào?
10. Repository và CassandraTemplate khác nhau về API, nhưng có thể bỏ qua quy tắc primary key của Cassandra hay không?

**Ghi nhớ:** primary key của một hàng Cassandra là định danh bất biến cho hàng đó. Đổi partition key hoặc clustering key có nghĩa là **tạo hàng dưới khóa mới rồi loại bỏ hàng cũ**, đồng thời phải thiết kế cách xử lý trạng thái trung gian, cạnh tranh và retry. Đó là phần kết nối giữa mapping trong Spring Data Cassandra và những bảo đảm thực tế của mô hình dữ liệu phân tán.
