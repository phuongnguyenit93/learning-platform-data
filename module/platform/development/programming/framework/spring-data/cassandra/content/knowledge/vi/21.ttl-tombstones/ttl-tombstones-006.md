# Giá trị UNSET và ý nghĩa giữ nguyên dữ liệu hiện có trong Spring Data Cassandra

## 1. Tình huống thực tế: một yêu cầu PATCH không muốn xóa những trường còn lại

Một dịch vụ Spring Boot dùng **Spring Data Cassandra** lưu hồ sơ người dùng. Người dùng chỉ muốn sửa tên hiển thị, không muốn thay đổi tiểu sử hay ảnh đại diện. API nhận:

~~~json
{
  "displayName": "An Nguyễn"
}
~~~

Nếu chương trình gán mọi trường vắng mặt thành `null` rồi phát một câu CQL cập nhật đầy đủ các cột, nó có thể **xóa những giá trị đang tồn tại**. Trong Cassandra, ghi `null` vào một cột thông thường không có nghĩa “bỏ qua”; việc xóa thường được biểu diễn bằng **tombstone**.

Với một yêu cầu cập nhật từng phần, cần phân biệt ba ý định:

1. **Không gửi trường**: giữ nguyên giá trị cột đã lưu.
2. **Gửi trường với giá trị null**: xóa giá trị cột, nếu hợp đồng API định nghĩa như vậy.
3. **Gửi một giá trị cụ thể**: thay thế giá trị cột bằng dữ liệu mới.

Ở tầng giao thức/Java driver Cassandra, ý định thứ nhất tương ứng với **UNSET** đối với một bind variable nằm trong vị trí hỗ trợ bỏ qua giá trị. Đó là trọng tâm bài học **“Giá trị UNSET và ý nghĩa giữ nguyên dữ liệu hiện có”** trong chương **TTL và tombstone**, thuộc module **SPRING_DATA_CASSANDRA**.

Bạn sẽ học cách dùng UNSET trong Java driver, hiểu sự khác biệt với `NULL` và câu CQL bỏ hẳn một cột, quản lý TTL/tombstone đúng khi PATCH, rồi kết nối với entity mapping, repository, `CassandraTemplate`, consistency và kiểm soát hiệu năng hệ dữ liệu phân tán.

**Mục tiêu sau bài học:**

- Mô tả chính xác ý nghĩa của **UNSET**, **NULL**, **giá trị cụ thể** và **trường không xuất hiện trong câu lệnh**.
- Biết khi nào UNSET **giữ nguyên giá trị và TTL hiện có** của một cột; khi nào NULL tạo xóa/tombstone.
- Dùng `PreparedStatement`/`BoundStatement` của Java driver 4.x với `unset(...)`, `setToNull(...)`, `setString(...)`.
- Thiết kế API PATCH biểu diễn **ba trạng thái** mà không nhập nhằng `Optional.empty()`.
- Nhận biết nơi **không được dùng UNSET** như partition key, clustering key hay điều kiện `WHERE` bắt buộc.
- Kiểm thử update từng phần, TTL hết hạn, đồng thời ghi, lỗi mạng và sự khác nhau giữa repository save với CQL tường minh.

## 2. Thiết kế bảng theo truy vấn trước khi nghĩ đến UNSET

Ví dụ hồ sơ người dùng được truy vấn theo `user_id`:

~~~sql
-- Keyspace app_ks được chuẩn bị trước với replication thích hợp.
CREATE TABLE app_ks.user_profiles_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    bio text,
    avatar_url text,
    city text,
    updated_at timestamp
);
~~~

| Cột | Vai trò | Ý nghĩa |
| --- | --- | --- |
| `user_id` | Partition key và toàn bộ primary key | Xác định chính xác hàng cần cập nhật |
| `display_name` | Cột thường | Có thể giữ nguyên, xóa hoặc ghi giá trị mới |
| `bio` | Cột thường | Ví dụ tiêu biểu cho dữ liệu có TTL hoặc cần xóa |
| `avatar_url` | Cột thường | Trường tùy chọn của hồ sơ |
| `city` | Cột thường | Cũng có thể xuất hiện trong PATCH |
| `updated_at` | Cột thường | Thời điểm nghiệp vụ; cần quy định có cập nhật khi no-op không |

Query đọc theo khóa:

~~~sql
SELECT user_id, display_name, bio, avatar_url, city, updated_at
FROM app_ks.user_profiles_by_id
WHERE user_id = ?;
~~~

Trong một ứng dụng Cassandra, **UNSET không thay thế quy tắc truy vấn theo partition key**. Nếu cần sửa hàng theo `user_id`, ta vẫn phải bind khóa này đầy đủ. Việc một cột không muốn sửa có thể UNSET không có nghĩa `WHERE user_id = ?` được phép để trống.

Nếu nghiệp vụ tìm theo city, cần thiết kế thêm đường đọc/index phù hợp; UNSET không tạo ra index hay cho phép lọc hiệu quả trên một cột thường.

## 3. Bốn trường hợp cần tách biệt

Giả sử hàng hiện có:

~~~text
user_id      = A
display_name = "An"
bio          = "Thích chạy bộ"
avatar_url   = "https://example.invalid/a.png"
city         = "Đà Nẵng"
~~~

Và câu CQL được chuẩn bị:

~~~sql
UPDATE app_ks.user_profiles_by_id
SET display_name = ?, bio = ?, avatar_url = ?
WHERE user_id = ?;
~~~

Với bind variable của `bio`, kết quả cần phân biệt:

| Đầu vào đối với `bio` | Ý nghĩa mong muốn | Hành vi của mutation đối với `bio` |
| --- | --- | --- |
| **UNSET** | Giữ nguyên | Không tạo cập nhật giá trị cho cột đó trong statement hỗ trợ UNSET |
| **NULL** | Xóa nội dung | Ghi xóa, thường tạo **tombstone** cho cột |
| **`"Tiểu sử mới"`** | Thay bằng giá trị mới | Ghi một phiên bản mới của cột |
| **Không có `bio` trong CQL `SET`** | Không đụng đến cột này | Câu lệnh không yêu cầu cập nhật cột đó |

Một trường hợp khác là chuỗi rỗng `""`. Nó **không tự động là NULL hoặc UNSET**: đây là **một giá trị text cụ thể** nếu schema/validation chấp nhận. API phải quyết định có cho phép tên/tiểu sử rỗng không.

### 3.1. UNSET không phải một giá trị được lưu trong bảng

UNSET **không phải dữ liệu nghiệp vụ** được persist để sau đó `SELECT bio` trả về một loại “unset”. Nó là tín hiệu ở **lần thực thi statement** rằng một bind variable không cung cấp mutation cho vị trí đó, trong những ngữ cảnh CQL/protocol hỗ trợ.

~~~mermaid
flowchart TD
    A[PATCH yêu cầu sửa hồ sơ] --> B{Trạng thái field bio?}
    B -->|Vắng mặt| C[Bind UNSET: không cập nhật bio]
    B -->|Có và null| D[Bind NULL: xóa bio / tombstone]
    B -->|Có giá trị| E[Bind text: ghi phiên bản mới]
    C --> F[Giá trị và TTL bio hiện tại giữ nguyên]
    D --> G[Bio không còn giá trị sống sau khi xóa thành công]
    E --> H[Bio mang giá trị mới với write timestamp / TTL áp dụng]
~~~

Vì vậy, `unset` không phải `delete`, không phải `null` và cũng không có nghĩa “chưa đọc dữ liệu nên không biết”. Phải biểu diễn rõ ý định update của caller.

### 3.2. Trường không có trong SQL và bind marker UNSET

Hai cách viết có thể có tác dụng **không sửa bio**:

~~~sql
-- Cách 1: không đưa bio vào SET.
UPDATE app_ks.user_profiles_by_id
SET display_name = ?
WHERE user_id = ?;

-- Cách 2: một query shape cố định có thêm bind marker cho bio.
UPDATE app_ks.user_profiles_by_id
SET display_name = ?, bio = ?
WHERE user_id = ?;
~~~

Với cách 2, ta **bind UNSET** vào vị trí `bio` khi không muốn cập nhật. Hai cách đều tránh chủ động sửa bio, nhưng khác về **cấu trúc query**:

- Cách 1 tạo các mẫu CQL riêng cho tổ hợp field được cập nhật.
- Cách 2 có thể tái sử dụng một prepared statement có cấu trúc cố định cho nhiều PATCH, miễn CQL và protocol cho phép UNSET ở những vị trí đó.

Không phải mọi vị trí dấu `?` đều được phép UNSET; phần 9 sẽ chỉ rõ giới hạn.

## 4. Vì sao NULL tạo tombstone nhưng UNSET không?

Cassandra dùng **tombstone** để ghi nhận việc một giá trị/hàng đã bị xóa. Tombstone quan trọng trong hệ thống nhân bản: nếu chỉ xóa vật lý ở một replica mà không để lại dấu xóa, một replica cũ có thể gửi lại giá trị đã bị xóa trong quá trình đồng bộ.

Với một cột thường:

~~~sql
-- Xóa giá trị ở cột bio: về ngữ nghĩa là mutation xóa.
UPDATE app_ks.user_profiles_by_id
SET bio = null
WHERE user_id = ?;

-- Cách thể hiện việc xóa cột một cách tường minh.
DELETE bio
FROM app_ks.user_profiles_by_id
WHERE user_id = ?;
~~~

Hai câu trên có thể biểu đạt việc loại bỏ giá trị cột trong tình huống thông thường; server ghi nhận thông tin xóa/tombstone theo ngữ nghĩa Cassandra.

Ngược lại:

~~~text
UPDATE ... SET bio = ? WHERE user_id = ?
               ^
               |
         Bind marker này được UNSET
~~~

thì statement **không yêu cầu mutation đối với bio**. Nếu bio đang có giá trị sống, nó vẫn giữ nguyên; nếu bio đã bị xóa trước đó, UNSET **không hoàn tác xóa**, không làm tombstone cũ biến mất. Nếu bio chưa từng có giá trị, nó vẫn chưa có giá trị.

### 4.1. Một bảng so sánh tác động

| Trạng thái trước đó của bio | UNSET | NULL | Ghi `"Mới"` |
| --- | --- | --- | --- |
| Có giá trị sống | Giữ nguyên | Xóa; tạo marker xóa | Ghi giá trị mới |
| Không có giá trị | Không chủ động tạo mới | Có thể ghi thêm thông tin xóa tùy trường hợp | Tạo giá trị mới |
| Đã có tombstone | Không xóa tombstone | Có thể tạo marker xóa mới | Ghi giá trị; kết quả còn tùy write timestamp/tombstone đang có |
| Giá trị có TTL đang chạy | **Không làm mới TTL** | Xóa giá trị | Tạo phiên bản mới; TTL do lần ghi mới quyết định |

**Quan trọng:** tombstone không phải “một hàng null” đơn giản. `SELECT bio` trả null không chứng minh hệ thống không có tombstone; dữ liệu đã xóa có thể tiếp tục tồn tại ở dạng marker phục vụ replication/compaction.

### 4.2. Tombstone nhiều ảnh hưởng đến đọc thế nào?

Khi query cần đi qua nhiều cell/hàng đã hết hạn hoặc bị xóa, Cassandra có thể phải xử lý nhiều tombstone trước khi trả một số hàng sống. Điều này có thể gây **read amplification**, tăng CPU/I/O và độ trễ, nhất là với partition lớn hoặc truy vấn rộng.

UNSET giảm **những lần xóa không cần thiết phát sinh do PATCH**, nhưng không xóa tombstone có sẵn, không sửa được partition key không phù hợp và không thay thế chính sách repair/compaction.

## 5. TTL: UNSET giữ nguyên đồng hồ hết hạn của cột

TTL (**time-to-live**) cho phép một giá trị hết hạn sau số giây được cấu hình. Với Cassandra, TTL được áp dụng theo ngữ nghĩa **cell/column** và cách câu ghi được thực thi, chứ không đơn giản là một đồng hồ TTL duy nhất cho cả object Java.

Ví dụ ghi bio với TTL 120 giây:

~~~sql
UPDATE app_ks.user_profiles_by_id
USING TTL 120
SET bio = ?
WHERE user_id = ?;
~~~

Sau khi ghi thành công, `bio` có thời gian sống 120 giây tính từ lần ghi này theo cơ chế TTL. Ta có thể quan sát:

~~~sql
SELECT bio, TTL(bio), WRITETIME(bio)
FROM app_ks.user_profiles_by_id
WHERE user_id = ?;
~~~

`TTL(bio)` thường trả số giây còn lại với cell có TTL; `WRITETIME(bio)` trả write timestamp của cell được hỗ trợ. Chúng không tương đương: **TTL tính theo giây**, còn **write timestamp có độ phân giải microsecond**. Với giá trị không có TTL, kết quả `TTL(...)` có thể là null; với cột không tồn tại/đã hết hạn, các biểu thức cũng có thể trả null theo trạng thái dữ liệu.

### 5.1. Dòng thời gian minh họa

Giả sử `bio` được ghi ở thời điểm `t = 0` với TTL 120 giây:

| Thời điểm | Thao tác | `bio` sau thao tác | TTL/expiration |
| --- | --- | --- | --- |
| `t = 0` | Ghi `"A"` với TTL 120 | `"A"` | Dự kiến hết hạn ở `t ≈ 120` |
| `t = 50` | PATCH `display_name`; bind **UNSET** cho bio | `"A"` | **Vẫn hết hạn khoảng t = 120** |
| `t = 50` | Nếu thay bằng ghi lại bio `"A"` với TTL 120 | `"A"` | TTL **được khởi động lại** cho lần ghi này, khoảng t = 170 |
| `t = 50` | Nếu thay bằng bind **NULL** cho bio | Bị xóa | Marker xóa được ghi; không còn giá trị sống |
| `t ≈ 120` | Bio ban đầu hết hạn nếu chỉ UNSET lúc t=50 | Không còn giá trị sống | Hết hạn được thể hiện bằng cơ chế tombstone/expiration |

Ba nhánh ở `t=50` là **ba kịch bản độc lập**, không diễn ra đồng thời trên cùng hàng.

**Kết luận thiết kế:** nếu mục tiêu là **giữ nguyên giá trị và thời hạn hiện tại**, hãy **không ghi lại cell**. UNSET hữu ích vì câu PATCH vẫn có thể dùng một query shape cố định nhưng không reset TTL cho field không thay đổi.

### 5.2. Ghi lại cùng giá trị cũng là một mutation

Người học đôi khi nghĩ “bio vẫn bằng `A` thì Cassandra sẽ không làm gì”. Điều này không đúng nói chung. Một `UPDATE` ghi lại cùng giá trị có thể thay đổi **write timestamp** và thông tin TTL của cell, dù chuỗi mà `SELECT` trả về nhìn không khác.

Ví dụ:

~~~sql
-- Ghi rõ giá trị, không phải UNSET.
UPDATE app_ks.user_profiles_by_id
USING TTL 300
SET bio = 'A'
WHERE user_id = ?;
~~~

Nếu mutation mới thắng theo quy tắc timestamp, nó tạo một phiên bản mới của bio và có thể đổi expiration. Không nên tự đồng nhất “giá trị bằng nhau” với “không có cập nhật”.

## 6. TTL khi câu UPDATE có nhiều cột

Giả sử chỉ muốn đổi tên và giữ nguyên bio:

~~~sql
UPDATE app_ks.user_profiles_by_id
USING TTL 600
SET display_name = ?, bio = ?
WHERE user_id = ?;
~~~

Khi bind:

- `display_name = "An mới"`: cột được ghi với TTL áp dụng theo statement.
- `bio = UNSET`: **không có mutation cho bio**, vì vậy TTL đang tồn tại của bio **không được làm mới** bởi câu lệnh này.

Ngược lại, nếu bind cả hai bằng giá trị cụ thể, **cả hai cột được ghi** và TTL có thể thay đổi theo lần ghi mới. Nếu bind bio thành NULL, đó là hành động xóa, không phải “giữ TTL như cũ”.

### 6.1. Không có USING TTL không nhất thiết giữ TTL cũ khi ghi lại giá trị

Một điểm rất dễ nhầm:

~~~sql
UPDATE app_ks.user_profiles_by_id
SET display_name = ?, bio = ?
WHERE user_id = ?;
~~~

Nếu `bio` là **UNSET**, TTL của bio cũ không bị can thiệp.

Nếu `bio` được bind giá trị cụ thể, đây là **lần ghi mới cho bio**. Việc không nêu `USING TTL` không có nghĩa tự động sao chép TTL còn lại của phiên bản trước. Với bảng không có default TTL, lần ghi mới thông thường có thể làm cột không còn TTL cũ; với bảng có `default_time_to_live`, TTL áp dụng lại theo quy tắc của schema.

Vì vậy, khi update từng phần, không thể coi một câu `UPDATE` ghi lại mọi field bằng giá trị trước đó là tương đương với việc chỉ cập nhật field được gửi.

### 6.2. Table default_time_to_live

Cassandra có thể cấu hình TTL mặc định ở mức bảng:

~~~sql
-- DDL minh họa; dùng bảng thử nghiệm riêng nếu cần lab.
ALTER TABLE app_ks.user_profiles_by_id
WITH default_time_to_live = 86400;
~~~

Đây là **thay đổi schema** và có ảnh hưởng rộng; **không áp dụng trên bảng production chỉ để thử bài học**. Khi bảng có default TTL:

- Cell được ghi mới chịu quy tắc TTL mặc định hoặc TTL được chỉ định tường minh theo cú pháp cho phép.
- Cell được **UNSET** không phải cell mới được ghi, nên việc PATCH field khác không tự “gia hạn” TTL của nó.
- `TTL 0`, default TTL và các giới hạn tương thích có quy tắc riêng tùy phiên bản. Hãy xác minh trước khi dùng chúng để biểu đạt “không bao giờ hết hạn”.
- Thay đổi default TTL ở schema **không có nghĩa gia hạn đồng loạt mọi cell hiện có** như khi ứng dụng ghi lại tất cả.

Với dữ liệu cần giữ lâu dài, hãy thiết kế TTL/retention theo use case và phiên bản Cassandra, không dùng một giá trị mặc định mơ hồ cho tất cả entity.

## 7. Giữ nguyên giá trị không đồng nghĩa ngăn hết hạn

UNSET chỉ có nghĩa **lần ghi này không thay đổi cell đó**. Nó **không đóng băng thời gian**.

~~~text
0s:  bio = "A", TTL 120
50s: PATCH display_name, bio = UNSET
90s: SELECT -> bio có thể vẫn là "A"
125s: SELECT -> bio đã hết TTL, có thể quan sát null
~~~

Không được diễn giải “giữ nguyên” thành “đảm bảo bio luôn tồn tại sau PATCH”. Nếu yêu cầu nghiệp vụ là **gia hạn TTL**, phải thực hiện **mutation chủ động** với TTL mới trên cột cần gia hạn và chấp nhận tác động của write timestamp/replication.

Tương tự, nếu client PATCH chỉ đổi avatar nhưng một writer khác xóa bio cùng lúc, UNSET **không khôi phục bio** và cũng không khóa bio chống concurrent writer. UNSET là **bỏ qua một cột trong một mutation**, không phải consistency guard.

## 8. Java driver 4.x: UNSET trên BoundStatement

Trong Java driver Cassandra 4.x, `PreparedStatement` định nghĩa các bind variables; `BoundStatement` chứa giá trị cụ thể cho **một lần thực thi**. Các phương thức như `setString(...)`, `setToNull(...)` và `unset(...)` giúp diễn đạt ba ý định.

Ví dụ CQL cố định:

~~~sql
UPDATE app_ks.user_profiles_by_id
SET display_name = ?, bio = ?, avatar_url = ?
WHERE user_id = ?;
~~~

Vị trí bind (đếm từ 0):

| Vị trí | Bind marker | Yêu cầu |
| ---: | --- | --- |
| 0 | `display_name` | VALUE, NULL hoặc UNSET tùy PATCH |
| 1 | `bio` | VALUE, NULL hoặc UNSET tùy PATCH |
| 2 | `avatar_url` | VALUE, NULL hoặc UNSET tùy PATCH |
| 3 | `user_id` trong `WHERE` | **Bắt buộc bind UUID hợp lệ** |

### 8.1. Ví dụ giữ nguyên bio và avatar

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

public final class ProfilePatchGateway {
    private final CqlSession session;
    private final PreparedStatement patch;

    public ProfilePatchGateway(CqlSession session) {
        this.session = session;
        this.patch = session.prepare(
            "UPDATE app_ks.user_profiles_by_id " +
            "SET display_name = ?, bio = ?, avatar_url = ? " +
            "WHERE user_id = ?"
        );
    }

    public void changeDisplayName(UUID userId, String newName) {
        BoundStatement statement = patch.bind()
            .setString(0, newName)
            .unset(1)
            .unset(2)
            .setUuid(3, userId);

        session.execute(statement);
    }
}
~~~

**Giải thích:**

1. Mẫu CQL được chuẩn bị **một lần** trên `CqlSession` có vòng đời dài.
2. Mỗi request tạo một `BoundStatement` mới.
3. `setString(0, newName)` ghi tên mới.
4. `unset(1)` và `unset(2)` bỏ qua bio/avatar, không yêu cầu xóa chúng.
5. `setUuid(3, userId)` đặt **partition key bắt buộc**.
6. Đây là `UPDATE` không điều kiện: nếu hàng chưa tồn tại, Cassandra có thể thực hiện upsert. Nếu nghiệp vụ chỉ cho phép sửa hàng đã có, cần `IF EXISTS`/CAS hoặc quy trình phù hợp.

**Quan trọng đối với driver 4.x:** những phương thức thay đổi option/giá trị trên `BoundStatement` thường trả về **một BoundStatement mới** theo API bất biến. Hãy **gán/chain kết quả** như ví dụ, không gọi `statement.unset(1)` rồi bỏ qua giá trị trả về.

### 8.2. NULL là một hành động khác

~~~java
BoundStatement clearBio = patch.bind()
    .unset(0)            // Giữ nguyên display_name.
    .setToNull(1)        // Xóa bio -> mutation/tombstone.
    .unset(2)            // Giữ nguyên avatar_url.
    .setUuid(3, userId);

session.execute(clearBio);
~~~

Đừng hoán đổi `setToNull(1)` và `unset(1)` chỉ vì cả hai cùng “không có chuỗi để ghi”. Đó là **hai lệnh nghiệp vụ khác nhau**.

### 8.3. Ghi giá trị rỗng không phải xóa

~~~java
BoundStatement setEmptyBio = patch.bind()
    .unset(0)
    .setString(1, "")
    .unset(2)
    .setUuid(3, userId);
~~~

Nếu validation cho phép chuỗi rỗng, mutation này có ý nghĩa **đặt bio thành chuỗi rỗng**, không phải UNSET hoặc NULL. Ứng dụng có thể chọn quy tắc “chuỗi chỉ có khoảng trắng là invalid”, nhưng phải biến đó thành **hợp đồng API rõ ràng**, không để driver quyết định thay cho nghiệp vụ.

## 9. Không được UNSET mọi bind marker

Tính năng UNSET được thiết kế cho các **vị trí hợp lệ** trong câu CQL/protocol. Những trường dùng để **định vị dữ liệu hoặc kiểm tra điều kiện** thường không thể bị bỏ trống một cách hợp lệ.

Ví dụ sau là **sai ý định**:

~~~java
BoundStatement wrong = patch.bind()
    .setString(0, "An")
    .unset(1)
    .unset(2)
    .unset(3);  // Không cung cấp user_id trong WHERE.

session.execute(wrong); // Truy vấn không có khóa định vị hợp lệ.
~~~

**Nguyên tắc:**

- Partition key/clustering key trong `WHERE` hoặc `INSERT` phải có giá trị hợp lệ theo schema.
- Bind variable trong các điều kiện `IF version = ?`, `IF state = ?` không được coi là “nếu UNSET thì tự bỏ qua điều kiện” trừ khi cú pháp và phiên bản hỗ trợ cụ thể, được kiểm chứng. **Không thiết kế logic dựa trên giả định đó.**
- UNSET không dùng để thay **tên bảng**, **tên cột**, `ORDER BY` hay cấu trúc CQL.
- Những thao tác với collections, counters, conditional updates và kiểu dữ liệu đặc biệt có hạn chế riêng; cần kiểm tra compatibility theo driver/protocol/Cassandra version.

**UNSET không phải từ khóa CQL chung để chèn tùy ý vào câu query.** Nó là trạng thái bind value ở giao thức/driver đối với vị trí được hỗ trợ; không viết `SET bio = UNSET` rồi giả định tương đương với `BoundStatement.unset(...)`.

### 9.1. Protocol và phiên bản

Hỗ trợ UNSET trong prepared statements gắn với **native protocol** tương ứng (các phiên bản protocol hiện đại, từ v4, hỗ trợ unset values). Nếu cluster/driver cũ hoặc dùng một API trừu tượng che đi bind state, hành vi có thể khác.

Khi dùng Spring Data Cassandra, cần kiểm chứng **phiên bản Spring Data + Java driver + Cassandra server** đang chạy; không suy diễn tất cả API repository đều cho caller truyền trạng thái UNSET trực tiếp.

## 10. INSERT và sự khác biệt giữa không gửi cột với gửi null

Trong Cassandra, `INSERT` có thể **upsert** hàng hiện có. Khi muốn giữ giá trị cũ của một cột mà câu insert không cần sửa, cách đơn giản nhất là **không nêu cột đó**.

~~~sql
INSERT INTO app_ks.user_profiles_by_id
    (user_id, display_name)
VALUES (?, ?);
~~~

Với hàng đã có `bio` và `avatar_url`, những cột không xuất hiện trong câu `INSERT` này thường **không bị ghi đè chỉ vì không được liệt kê**. Nó không giống việc thêm `bio = null` một cách chủ động.

Nếu dùng một câu `INSERT` chuẩn bị sẵn có nhiều cột:

~~~sql
INSERT INTO app_ks.user_profiles_by_id
    (user_id, display_name, bio, avatar_url)
VALUES (?, ?, ?, ?);
~~~

Khi bind UNSET vào các giá trị cột thông thường được hỗ trợ, ý định là **không cập nhật những cột đó**; bind NULL vào chúng lại biểu đạt xóa. Primary key `user_id` phải được cung cấp.

### 10.1. Không được nhầm insert/update với replace toàn bộ document

Cassandra không tự hiểu mỗi câu `INSERT` là “replace toàn bộ row giống thao tác PUT một document”. Các cột không được mutation động đến có thể vẫn giữ giá trị trước đó. Điều này giúp cập nhật từng phần, nhưng cũng là lý do cần định nghĩa rõ API:

- **POST create-only:** thường cần `IF NOT EXISTS` khi không muốn tạo đè một hàng có sẵn.
- **PATCH partial update:** chỉ thay các field được yêu cầu; UNSET phù hợp.
- **PUT replace:** nếu hợp đồng yêu cầu “field thiếu phải bị xóa”, phải chủ động thể hiện những xóa đó, không nhầm với UNSET.

Chọn ngữ nghĩa HTTP trước, sau đó ánh xạ sang CQL một cách có chủ đích.

## 11. JSON CQL: DEFAULT UNSET và DEFAULT NULL

Cassandra có cú pháp **`INSERT ... JSON`** cho trường hợp ghi giá trị từ JSON CQL. Ở những phiên bản hỗ trợ, phần `DEFAULT UNSET` cho phép **các cột vắng mặt trong JSON** được coi là không ghi, trong khi `DEFAULT NULL` diễn đạt việc coi cột thiếu như null theo ngữ nghĩa câu lệnh.

Ví dụ minh họa, nếu bảng đã có dữ liệu:

~~~sql
-- Chỉ cập nhật những cột được nêu trong JSON.
INSERT INTO app_ks.user_profiles_by_id JSON
'{"user_id":"11111111-1111-4111-8111-111111111111",
  "display_name":"An mới"}'
DEFAULT UNSET;
~~~

Nếu chọn:

~~~sql
-- Cẩn thận: cột vắng mặt có thể bị hiểu là null/xóa.
INSERT INTO app_ks.user_profiles_by_id JSON
'{"user_id":"11111111-1111-4111-8111-111111111111",
  "display_name":"An mới"}'
DEFAULT NULL;
~~~

thì hậu quả đối với các cột thiếu khác biệt đáng kể. **Không nhầm tùy chọn `DEFAULT UNSET` của CQL JSON với trạng thái UNSET bind variable của Java driver**: hai cơ chế có liên hệ về mục đích bỏ qua cập nhật, nhưng được biểu diễn ở hai API khác nhau.

Lưu ý:

- Phải kiểm tra **cú pháp và hành vi mặc định** của `INSERT JSON` ở phiên bản Cassandra đang triển khai.
- Một field **xuất hiện rõ ràng với giá trị JSON `null`** không giống field **vắng mặt** khi dùng `DEFAULT UNSET`.
- Ví dụ JSON này dành cho **CQL JSON literal** trong môi trường học; API web vẫn phải validate dữ liệu và tránh ghép JSON không tin cậy trực tiếp vào chuỗi CQL.
- Đối với ứng dụng Java cần kiểm soát từng cột và prepared statement, thường ưu tiên **bind markers** rõ ràng.

## 12. API PATCH cần ba trạng thái, Optional không đủ

Trong Java, `Optional<String>` có thể biểu đạt “có giá trị” và “không có giá trị”, nhưng **không biểu đạt đầy đủ ba trạng thái**:

~~~text
field không được gửi   -> KEEP (UNSET)
field được gửi = null  -> CLEAR (NULL)
field được gửi = "A"   -> SET ("A")
~~~

Nếu DTO chỉ có:

~~~java
public record ProfilePatchRequest(
    String displayName,
    String bio,
    String avatarUrl
) {}
~~~

thì trong cách mapping JSON thông thường, cả **vắng mặt** lẫn **JSON null** đều dễ trở thành Java `null`. Khi đó server không biết client muốn **giữ nguyên** hay **xóa**.

### 12.1. Mô hình PatchField với ba ý định

~~~java
import java.util.Objects;

public record PatchField<T>(Mode mode, T value) {
    public enum Mode { KEEP, CLEAR, SET }

    public PatchField {
        Objects.requireNonNull(mode, "mode");
        if (mode == Mode.SET) {
            Objects.requireNonNull(value, "SET requires value");
        } else if (value != null) {
            throw new IllegalArgumentException(
                "KEEP/CLEAR must not have a value"
            );
        }
    }

    public static <T> PatchField<T> keep() {
        return new PatchField<>(Mode.KEEP, null);
    }

    public static <T> PatchField<T> clear() {
        return new PatchField<>(Mode.CLEAR, null);
    }

    public static <T> PatchField<T> set(T value) {
        return new PatchField<>(Mode.SET, value);
    }
}
~~~

Mô hình này giữ được sự khác biệt giữa:

~~~java
PatchField<String> unchanged = PatchField.keep();
PatchField<String> deleted = PatchField.clear();
PatchField<String> written = PatchField.set("Tiểu sử mới");
~~~

Không nên ép `PatchField.keep()` thành Java `null` rồi ở tầng gateway lại diễn giải thành xóa. Cần truyền nguyên ý định cho tới lúc bind CQL.

### 12.2. Đọc trạng thái field từ JSON

Với Jackson `JsonNode`, có thể phân biệt **field vắng mặt** và **field null**:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

static PatchField<String> readTextPatch(
        JsonNode body, String fieldName) {
    if (!body.has(fieldName)) {
        return PatchField.keep();
    }

    JsonNode value = body.get(fieldName);
    if (value.isNull()) {
        return PatchField.clear();
    }
    if (!value.isTextual()) {
        throw new IllegalArgumentException(
            "Expected string or null: " + fieldName
        );
    }
    return PatchField.set(value.textValue());
}
~~~

`body.has(name)` trả true khi field **có tồn tại trong object, kể cả JSON null**; `hasNonNull(...)` không phù hợp nếu cần phân biệt null với vắng mặt. Ví dụ giả định `body` là JSON object không null, controller đã validate quyền truy cập và giới hạn kích thước nội dung.

### 12.3. Quy ước PATCH không phải thuộc tính tự động của Cassandra

Có thể định nghĩa:

| JSON request | Ý định tầng HTTP | CQL |
| --- | --- | --- |
| `{}` | Không đổi gì | Không phát update |
| `{"bio": null}` | Xóa bio | Bind NULL hoặc `DELETE bio` |
| `{"bio": ""}` | Đặt bio thành chuỗi rỗng | Bind chuỗi rỗng (nếu hợp lệ) |
| `{"bio": "Mới"}` | Đặt giá trị mới | Bind VALUE |
| `{"displayName": "An mới"}` | Chỉ đổi tên | Bind VALUE cho tên, UNSET cho bio/avatar |

Một hệ thống khác có thể chọn ngữ nghĩa HTTP riêng; quan trọng là **có tài liệu và test khẳng định** quy tắc. Không để tình cờ của JSON mapper quyết định hành vi xóa dữ liệu.

## 13. Kết hợp PatchField và BoundStatement bất biến

Ta mở rộng gateway để hỗ trợ PATCH nhiều cột với query shape ổn định:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.Objects;
import java.util.UUID;

public final class ProfilePatchServiceGateway {
    private final CqlSession session;
    private final PreparedStatement patch;

    public ProfilePatchServiceGateway(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.patch = session.prepare(
            "UPDATE app_ks.user_profiles_by_id " +
            "SET display_name = ?, bio = ?, avatar_url = ? " +
            "WHERE user_id = ?"
        );
    }

    private static BoundStatement setPatch(
            BoundStatement statement,
            int index,
            PatchField<String> field) {
        return switch (field.mode()) {
            case KEEP -> statement.unset(index);
            case CLEAR -> statement.setToNull(index);
            case SET -> statement.setString(index, field.value());
        };
    }

    public void patch(
            UUID userId,
            PatchField<String> displayName,
            PatchField<String> bio,
            PatchField<String> avatar) {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(displayName);
        Objects.requireNonNull(bio);
        Objects.requireNonNull(avatar);

        if (displayName.mode() == PatchField.Mode.KEEP
                && bio.mode() == PatchField.Mode.KEEP
                && avatar.mode() == PatchField.Mode.KEEP) {
            return; // Không cần phát mutation khi tất cả đều KEEP.
        }

        BoundStatement statement = patch.bind().setUuid(3, userId);
        statement = setPatch(statement, 0, displayName);
        statement = setPatch(statement, 1, bio);
        statement = setPatch(statement, 2, avatar);
        session.execute(statement);
    }
}
~~~

Đoạn code dùng **Java 17+** vì `record` và switch expression, cùng Java driver 4.x. Với dự án Java thấp hơn, có thể viết POJO và switch statement tương đương. Kiểu dữ liệu `PatchField<String>` được định nghĩa ở phần trước; service phải validate length, authorization và content-policy.

**Lợi ích:**

- Một `PreparedStatement` có **cấu trúc CQL ổn định**, không phải tạo chuỗi query mới cho từng request.
- Mỗi field KEEP → UNSET; CLEAR → NULL; SET → giá trị cụ thể.
- Mỗi request tạo `BoundStatement` riêng; không chia sẻ statement với giá trị bind giữa các luồng.
- Trường hợp toàn KEEP được xử lý như **no-op**, không giả định server sẽ tự tối ưu mọi câu UPDATE chỉ có UNSET.

**Giới hạn:**

- Đây là `UPDATE` không điều kiện, có thể tạo hàng nếu khóa chưa có và một số field được ghi.
- Nó **không bảo vệ lost update** đối với hai request cùng sửa một cột.
- Nó không kiểm tra JSON PATCH có quyền sửa mọi field hay không.
- Việc ghi giá trị NULL tạo tombstone; khi có hàng triệu PATCH xóa field, cần đo chi phí đọc/compaction.

## 14. Cập nhật một cột ở client khác khi ta UNSET cột đó

Giả sử:

~~~text
T0: bio = "A", avatar_url = "a.png"
T1: Request X đổi avatar_url thành "b.png", UNSET bio
T2: Request Y đổi bio thành "B", UNSET avatar_url
~~~

Với hai mutation trên **hai cell khác nhau** và không có điều kiện nghiệp vụ phức tạp, Cassandra có thể giữ cả hai thay đổi:

~~~text
bio = "B"
avatar_url = "b.png"
~~~

Đây là một lợi ích của việc **không ghi lại các cột không thay đổi**. Nếu cả hai request đều ghi snapshot đầy đủ chứa giá trị cũ của cột còn lại, một request có thể ghi đè cập nhật của request kia theo timestamp.

Tuy nhiên:

- Nếu hai request cùng **sửa bio**, UNSET không giúp giải quyết conflict trên bio.
- Nếu thay đổi avatar và bio phải hợp lệ **như một tổ hợp**, update các cell độc lập không tự bảo vệ invariant đó.
- Concurrent writes vẫn được hòa giải theo Cassandra write timestamp; **UNSET không cung cấp khóa, transaction hay kiểm tra version**.
- Nếu cần “chỉ PATCH trên phiên bản vừa đọc”, phải dùng LWT/optimistic concurrency phù hợp, ví dụ `IF version = ?`.

## 15. UNSET và optimistic locking bằng LWT: hai mục đích khác nhau

UNSET trả lời câu hỏi:

> “Tôi **không định sửa cột này** trong mutation hiện tại.”

LWT/CAS trả lời:

> “Chỉ thực hiện mutation **nếu trạng thái hiện tại vẫn khớp** điều kiện tôi mong đợi.”

Ví dụ bảng có thêm `version bigint` được quản lý nhất quán theo ứng dụng:

~~~sql
-- Ví dụ DDL bổ sung trong lab, không chạy nếu cột đã tồn tại.
ALTER TABLE app_ks.user_profiles_by_id
ADD version bigint;
~~~

Câu conditional PATCH:

~~~sql
UPDATE app_ks.user_profiles_by_id
SET display_name = ?, bio = ?, avatar_url = ?, version = ?
WHERE user_id = ?
IF version = ?;
~~~

Với cách này:

- Cột PATCH **KEEP** có thể bind UNSET ở vị trí SET tương ứng.
- Cột PATCH **CLEAR** bind NULL.
- Cột PATCH **SET** bind giá trị mới.
- `version` mới phải được cung cấp và tăng theo quy tắc ứng dụng.
- `user_id` trong `WHERE` và `expectedVersion` trong `IF` phải có giá trị hợp lệ; **không UNSET chúng**.
- Kết quả phải được đọc qua `[applied]`/`ResultSet.wasApplied()`, và việc dùng UNSET ở conditional statement cần được **kiểm chứng trên Cassandra/driver phiên bản thực tế**.

**LWT không làm mất ý nghĩa của UNSET:** một CAS thành công vẫn chỉ ghi các cell được yêu cầu; cell UNSET tiếp tục giữ nguyên giá trị và TTL hiện có.

**Đánh đổi:** Paxos cần thêm phối hợp replica và chi phí so với write thường. Chỉ áp dụng khi nghiệp vụ phải bảo vệ concurrent update, không bật LWT cho mọi PATCH theo phản xạ.

## 16. Spring Data Cassandra: repository save có nghĩa gì với null?

Spring Data Cassandra cung cấp `CassandraRepository` và `CassandraTemplate` cho thao tác entity. Ví dụ entity:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("user_profiles_by_id")
public class UserProfile {
    @PrimaryKey("user_id")
    private UUID userId;

    @Column("display_name")
    private String displayName;

    @Column("bio")
    private String bio;

    @Column("avatar_url")
    private String avatarUrl;

    protected UserProfile() {}

    public UUID getUserId() { return userId; }
    public String getDisplayName() { return displayName; }
    public String getBio() { return bio; }
    public String getAvatarUrl() { return avatarUrl; }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface UserProfileRepository
        extends CassandraRepository<UserProfile, UUID> {
}
~~~

### 16.1. Đừng suy diễn từ Java null ra CQL UNSET

Một entity Java có `bio == null` **không tự cho bạn biết** caller muốn:

- Giữ nguyên bio cũ vì request PATCH không gửi bio.
- Xóa bio cũ vì request PATCH gửi `"bio": null`.
- Biểu diễn một hàng vừa đọc không có bio.

Tùy phiên bản, mapping strategy, write options và loại thao tác của Spring Data Cassandra, các trường null có thể bị bỏ qua, được gửi null hoặc được xử lý theo cơ chế riêng. Vì vậy **không thể tuyên bố chung** “`repository.save(entity)` luôn tương đương UNSET cho null” hoặc “luôn ghi tombstone”.

**Cách làm an toàn:** đối với PATCH cần phân biệt chính xác KEEP/CLEAR/SET, sử dụng API update có **định nghĩa CQL tường minh**, bind trạng thái rõ ràng, hoặc xác minh khả năng mapping/update options của đúng phiên bản Spring Data Cassandra với integration test.

### 16.2. Load–modify–save có thể làm thay đổi field không liên quan

Một cách triển khai thường thấy:

~~~java
UserProfile entity = repository.findById(userId)
    .orElseThrow();
// Chỉ thay displayName ở entity Java.
repository.save(entity);
~~~

Nếu cơ chế save ghi lại các cột từ snapshot entity, và một writer khác đã cập nhật `bio` trong khoảng giữa read/save, mutation mới có thể **ghi lại bio cũ**. Kết quả phụ thuộc mapping/query thực tế, nhưng đây là **nguy cơ lost update** cần tránh bằng selective update hoặc CAS.

Ngoài ra, nếu bio có TTL, việc ghi lại cùng giá trị cũ có thể làm thay đổi expiration. Dùng entity save như thao tác PATCH toàn năng mà không kiểm tra CQL phát ra là thiết kế rủi ro.

### 16.3. @Transient và @Nullable không đồng nghĩa UNSET theo request

- `@Transient` của mapping dùng để **không persist một property** trong những ngữ cảnh tương ứng, không có nghĩa “field này chỉ UNSET ở request PATCH hôm nay”.
- Annotation nullability của Java/Spring chủ yếu biểu đạt hợp đồng null, không tự mã hóa ba trạng thái KEEP/CLEAR/SET.
- `Optional<T>` phù hợp cho nhiều API đọc nhưng không tự phân biệt “không xuất hiện” với “được gửi null” trong JSON PATCH.

Với update từng phần, **mô hình hóa ý định ở tầng request/service**, không buộc toàn bộ ngữ nghĩa vào trạng thái null của một entity.

## 17. Chọn giữa CqlTemplate, CassandraTemplate và CqlSession

| API | Điểm mạnh | Điều phải kiểm tra với UNSET |
| --- | --- | --- |
| `CassandraRepository` | CRUD theo khóa, mapping entity | `save(...)` xử lý null/bỏ qua field ra sao, có ghi lại cột khác không |
| `CassandraTemplate` | Entity mapping, truy vấn theo tiêu chí, update API | Mapping của update/null và write options ở phiên bản thực tế |
| `CqlTemplate`/`CqlOperations` | CQL và RowMapper tường minh | Phương thức bind có cho kiểm soát UNSET/NULL riêng hay không |
| **`CqlSession` Java driver** | Trực tiếp chuẩn bị/bind statement và setToNull/unset | Trách nhiệm query, codec, CL, validation và vòng đời session |

Với bài toán cần **đúng ba trạng thái** cho từng bind variable, `CqlSession`/`BoundStatement` thường là đường **minh bạch** để học semantics. Một ứng dụng production có thể đóng gói nó thành **custom repository fragment** và vẫn dùng repository cho những thao tác khác.

### 17.1. Spring quản lý session dài hạn

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ProfileGatewayConfig {
    @Bean
    ProfilePatchServiceGateway profilePatchGateway(
            CqlSession session) {
        return new ProfilePatchServiceGateway(session);
    }
}
~~~

Nếu Spring Boot đã tạo `CqlSession`, hãy inject và dùng lại; **không tạo một session mới cho mỗi HTTP PATCH**. Không đóng session trong `patch(...)`; vòng đời kết nối do Spring/application owner quản lý. Nếu có nhiều keyspace/session, dùng `@Qualifier` và tên bảng đầy đủ để tránh cập nhật nhầm dữ liệu.

## 18. UNSET và các kiểu collection, UDT, counter

Cassandra có list/set/map, user-defined type (UDT) và counter. Cách cập nhật không luôn giống cột text đơn giản:

1. **Collection bình thường:** ghi lại toàn bộ collection có thể thay thế nội dung đã lưu; nếu muốn giữ nguyên, không gửi mutation cho cột. Cú pháp thêm/xóa phần tử có semantics khác với replace toàn bộ.
2. **Collection element:** đối với `map[key]` hoặc các phép biến đổi riêng, không được suy rằng bind UNSET ở mọi vị trí có nghĩa “bỏ qua” hợp lệ. Phải kiểm chứng đúng cú pháp CQL.
3. **Frozen UDT/collection:** thường được coi là một giá trị nguyên khối khi ghi; UNSET cả cột sẽ giữ nguyên khối cũ, còn NULL có thể xóa khối. Muốn cập nhật một phần có thể cần đọc–ghi nguyên khối hoặc mô hình khác.
4. **Counter:** có quy tắc cập nhật riêng với phép cộng/trừ và ràng buộc CQL; không đưa ví dụ `SET counter = NULL/UNSET` rồi khẳng định giống text.
5. **Static columns:** gắn với partition theo quy tắc riêng, ảnh hưởng nhiều hàng clustering; cần hiểu scope trước khi áp dụng update từng phần.

**Nguyên tắc:** chỉ áp dụng ví dụ `setString/unset/setToNull` một cách cơ học cho những loại cột thông thường được hỗ trợ; dữ liệu phân tán có nhiều kiểu mutation, và mỗi kiểu phải có test.

## 19. Tác động hiệu năng và tombstone: tránh xóa ngoài ý muốn

Giả sử API mỗi ngày xử lý một triệu PATCH chỉ đổi `display_name`. Nếu mỗi PATCH vô tình bind `bio = null` và `avatar_url = null`:

- Hệ thống có thể phát sinh một lượng lớn marker xóa không cần thiết.
- Replica cần xử lý thêm mutation và tombstone.
- Các truy vấn đọc có thể chịu read amplification/GC/compaction pressure tùy phân bố dữ liệu, TTL và schema.
- Các giá trị còn dùng được của người dùng có thể bị xóa — đây là lỗi **tính đúng đắn**, không chỉ lỗi hiệu năng.

Nếu bind UNSET hoặc không đưa hai field đó vào mutation:

- Không tạo xóa mới cho các field không được yêu cầu.
- Giữ nguyên TTL và write timestamp hiện có của những cell đó.
- Tránh làm mất cập nhật riêng của writer khác đối với các field không liên quan.

Tuy nhiên UNSET **không làm giảm mọi loại tombstone**:

- TTL vốn có vẫn có thể hết hạn và trở thành tombstone.
- Những lệnh DELETE/NULL thực sự vẫn tạo marker xóa.
- Tombstone đã tồn tại không bị loại bỏ chỉ vì request sau dùng UNSET.
- Compaction, repair và các quy tắc giữ tombstone vẫn cần quản lý độc lập.

### 19.1. gc_grace_seconds không phải “thời gian UNSET có hiệu lực”

Thông số `gc_grace_seconds` liên quan thời gian/điều kiện an toàn để tombstone có thể được dọn trong các quy trình lưu trữ/compaction theo phiên bản và topology. Nó **không** quyết định khi nào một trường UNSET được cập nhật.

Không hạ `gc_grace_seconds` tùy tiện chỉ vì thấy tombstone nhiều: nếu replica cũ không được repair/hội tụ đúng thời hạn, có nguy cơ dữ liệu đã xóa **xuất hiện lại** sau khi marker xóa bị dọn. Cần tuân theo chính sách repair, maintenance và tính năng tombstone GC của phiên bản Cassandra thực tế.

### 19.2. Quan sát thay vì suy đoán

Các tín hiệu hữu ích:

| Quan sát | Ý nghĩa |
| --- | --- |
| Số PATCH chỉ đổi một field | Đánh giá khả năng selective update tiết kiệm mutation |
| Tỷ lệ field CLEAR/SET/KEEP | Phát hiện API gửi null ngoài dự kiến |
| `TTL(bio)` trước/sau KEEP | Xác minh không refresh TTL |
| `WRITETIME(bio)` trước/sau KEEP | Xác minh không ghi phiên bản bio mới |
| Tombstone metrics/warnings | Đánh giá chi phí xóa/TTL trên query thực |
| Kích thước partition và số row đọc | Phát hiện vấn đề query-first ngoài phạm vi UNSET |
| P95/P99 latency và timeout | Kiểm tra ảnh hưởng dưới tải và lỗi node |
| Write conflict / LWT not applied | Tách cạnh tranh nghiệp vụ khỏi PATCH KEEP |

Vì dữ liệu phân tán có độ trễ, consistency và compaction, một lệnh `SELECT` duy nhất không đủ làm bằng chứng hệ thống không có tombstone. Kết hợp test chức năng với metrics và kiểm tra schema.

## 20. Bài lab: so sánh UNSET, NULL và VALUE

### 20.1. Chuẩn bị dữ liệu

Tạo bảng `user_profiles_by_id` như phần 2 trong keyspace thử nghiệm. Thêm một hàng:

~~~sql
INSERT INTO app_ks.user_profiles_by_id
    (user_id, display_name, bio, avatar_url, city)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'An',
    'Thích chạy bộ',
    'https://example.invalid/a.png',
    'Đà Nẵng'
);
~~~

Kiểm tra:

~~~sql
SELECT display_name, bio, avatar_url, city,
       WRITETIME(bio), TTL(bio)
FROM app_ks.user_profiles_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
~~~

### 20.2. Trường hợp A: UNSET bio và avatar

Trên Java driver, dùng gateway phần 8 với:

~~~text
display_name = VALUE("An mới")
bio          = UNSET
avatar_url   = UNSET
user_id      = UUID của hàng thử nghiệm
~~~

**Kỳ vọng:** tên đổi, bio/avatar vẫn giữ giá trị cũ; `WRITETIME(bio)` không đổi do mutation này. Nếu bio có TTL đang chạy, nó tiếp tục đếm xuống và không bị reset vì KEEP.

### 20.3. Trường hợp B: NULL bio

~~~text
display_name = UNSET
bio          = NULL
avatar_url   = UNSET
user_id      = UUID của hàng thử nghiệm
~~~

**Kỳ vọng:** bio không còn giá trị sống sau mutation xóa được áp dụng; avatar và tên không bị sửa vì câu này. Trong Cassandra, xóa cell thường sinh tombstone; chỉ nhìn thấy null trên SELECT không đo trực tiếp được số tombstone.

### 20.4. Trường hợp C: VALUE rỗng hoặc mới

~~~text
display_name = UNSET
bio          = VALUE("")
avatar_url   = UNSET
user_id      = UUID của hàng thử nghiệm
~~~

**Kỳ vọng:** bio có giá trị chuỗi rỗng, khác với null. Tiếp tục đặt `bio = "Đã cập nhật"` và so sánh `WRITETIME(bio)`.

### 20.5. Trường hợp D: TTL không được làm mới khi KEEP

1. Ghi bio với TTL 120 giây trên **hàng mới riêng**.
2. Đọc `TTL(bio)`, đợi một thời gian ngắn trong môi trường test có thể kiểm soát.
3. PATCH tên với **bio UNSET**.
4. Đọc lại `TTL(bio)` và `WRITETIME(bio)`, so sánh.
5. Ghi lại bio với **TTL 120** bằng VALUE rồi quan sát TTL/WRITETIME mới.
6. Không chạy test dựa trên giấc ngủ thời gian thật quá dài; dùng khung thời gian hợp lý và tolerance để tránh flaky test.

**Không dùng chính hồ sơ production** cho thử nghiệm TTL và xóa dữ liệu.

## 21. Test Java cho PATCH ba trạng thái

### 21.1. Unit test chuyển JSON thành KEEP/CLEAR/SET

~~~java
import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

@Test
void distinguishesAbsentNullAndValue() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    var absent = mapper.readTree("{}");
    var clear = mapper.readTree("{\"bio\":null}");
    var value = mapper.readTree("{\"bio\":\"A\"}");
    var empty = mapper.readTree("{\"bio\":\"\"}");

    assertEquals(PatchField.Mode.KEEP,
        readTextPatch(absent, "bio").mode());
    assertEquals(PatchField.Mode.CLEAR,
        readTextPatch(clear, "bio").mode());
    assertEquals(PatchField.Mode.SET,
        readTextPatch(value, "bio").mode());
    assertEquals("A", readTextPatch(value, "bio").value());
    assertEquals("", readTextPatch(empty, "bio").value());
}
~~~

Đoạn test dùng Java phù hợp với `var`, JUnit 5, Jackson và hai helper đã định nghĩa. Nó kiểm tra **ngữ nghĩa DTO**, chưa chứng minh Cassandra nhận UNSET đúng cách.

### 21.2. Integration test: UNSET giữ nguyên dữ liệu

Trong cluster Cassandra thử nghiệm, chuẩn bị `CqlSession session`, schema và một hàng có `bio = 'A'`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;
import org.junit.jupiter.api.Test;

@Test
void unsetKeepsExistingBio() {
    UUID id = UUID.randomUUID();

    PreparedStatement insert = session.prepare(
        "INSERT INTO app_ks.user_profiles_by_id " +
        "(user_id, display_name, bio) VALUES (?, ?, ?)"
    );
    session.execute(insert.bind(id, "An", "A"));

    ProfilePatchGateway gateway = new ProfilePatchGateway(session);
    gateway.changeDisplayName(id, "An mới");

    PreparedStatement select = session.prepare(
        "SELECT display_name, bio " +
        "FROM app_ks.user_profiles_by_id WHERE user_id = ?"
    );
    Row row = session.execute(select.bind(id)).one();

    assertNotNull(row);
    assertEquals("An mới", row.getString("display_name"));
    assertEquals("A", row.getString("bio"));
}
~~~

Test giả định `session` được chia sẻ qua fixture và đã cấu hình keyspace/DC đúng. Dùng bind parameter cả cho câu đọc lẫn ghi; dữ liệu test phải được dọn theo chính sách của môi trường. Đây là test **trạng thái giá trị**, cần test riêng nếu muốn kiểm tra TTL/WRITETIME hoặc tombstone metrics.

### 21.3. Ma trận test cần có

| Trường hợp | Trạng thái trước | Thao tác | Kỳ vọng |
| --- | --- | --- | --- |
| KEEP trên cột có dữ liệu | `bio = A` | UNSET bio | Vẫn A |
| CLEAR trên cột có dữ liệu | `bio = A` | NULL bio | Không còn giá trị sống |
| SET giá trị mới | `bio = A` | VALUE B | B |
| SET chuỗi rỗng | `bio = A` | VALUE `""` | Chuỗi rỗng nếu hợp lệ |
| KEEP trên cột null | `bio` không có | UNSET bio | Không tạo giá trị |
| KEEP trên cột có TTL | Bio đang đếm TTL | UNSET bio | TTL tiếp tục đếm, không refresh |
| SET lại giá trị có TTL | Bio đang đếm TTL | Ghi VALUE mới với TTL | TTL theo mutation mới |
| CLEAR một cột | Avatar cũng đang có | NULL bio, UNSET avatar | Avatar không đổi |
| PATCH hoàn toàn rỗng | Có hồ sơ | Tất cả KEEP | Gateway không phát update |
| PK UNSET | Có dữ liệu bất kỳ | Bỏ `user_id` | Bị từ chối, không tạo PATCH vô đích |
| Hai PATCH cột khác nhau | Bio và avatar có sẵn | Hai writer, mỗi bên UNSET cột kia | Không chủ động ghi đè cột không sửa |
| Hai PATCH cùng bio | `bio = A` | Cùng ghi B/C | Cần chính sách conflict/LWT nếu muốn ngăn ghi đè |
| API gửi null | `bio = A` | JSON `{"bio":null}` | Mapped thành CLEAR |
| API không gửi field | `bio = A` | JSON `{}` | Mapped thành KEEP |
| Cassandra timeout | Có hoặc không có hàng | PATCH bất kỳ | Exception/trạng thái chưa chắc chắn, không giả thành KEEP |

### 21.4. Test thời gian và kết quả đọc

Khi kiểm tra TTL:

- Cassandra có độ phân giải thời gian và cách tính TTL riêng, nên không assert chính xác từng giây nếu dựa trên wall clock.
- Có thể so sánh `WRITETIME(bio)` trước/sau UNSET; với một mutation chỉ thay tên, write timestamp của bio **không nên đổi** vì nó không được ghi.
- Khi kiểm tra null sau CLEAR, không nên kết luận **tombstone đã được compaction dọn** chỉ vì query không thấy giá trị.
- Dùng consistency level phù hợp để test quan sát kết quả ghi; nếu chạy cluster đa replica và dùng CL thấp, stale read có thể ảnh hưởng kết luận.

## 22. Sai lầm thường gặp và cách sửa

| Hiểu nhầm | Điều đúng hơn |
| --- | --- |
| “Java null luôn nghĩa giữ nguyên cột.” | Null có thể biểu đạt xóa/tombstone, tùy đường mapping; phải phân biệt UNSET |
| “UNSET là một giá trị được Cassandra lưu.” | UNSET là trạng thái bind/không ghi vào mutation, không phải cell value |
| “UNSET sẽ xóa tombstone trước đó.” | UNSET không thay đổi cell, kể cả tombstone/TTL sẵn có |
| “Cứ ghi lại cùng giá trị sẽ giữ TTL cũ.” | Việc ghi lại có thể làm đổi write timestamp và expiration |
| “Nếu có USING TTL thì cả cột UNSET cũng được gia hạn.” | TTL áp dụng cho những cell được mutation ghi, không tự refresh cell UNSET |
| “Trường JSON thiếu và JSON null giống nhau.” | PATCH nên phân biệt KEEP với CLEAR |
| “Optional.empty() đủ biểu diễn mọi PATCH.” | Cần ba trạng thái để biểu diễn vắng mặt, null và giá trị |
| “Có thể UNSET partition key và Cassandra tự tìm đúng hàng.” | PK cần giá trị hợp lệ để định vị |
| “UNSET cột khác sẽ ngăn writer cạnh tranh trên cột đang sửa.” | UNSET không phải CAS/version guard |
| “Dùng repository.save() luôn bỏ qua mọi null.” | Phải kiểm tra phiên bản Spring Data/mapper/write options |
| “Gọi BoundStatement.unset() không cần nhận giá trị trả về.” | Driver 4.x dùng API statement bất biến; cần chain/gán lại |
| “Khi SELECT trả null tức không có tombstone.” | Tombstone/TTL có thể còn trong lưu trữ và ảnh hưởng đọc |
| “Giảm gc_grace_seconds sẽ xử lý tận gốc lỗi PATCH xóa nhầm.” | Phải sửa semantics PATCH; giảm grace tùy tiện có rủi ro dữ liệu sống lại |
| “DEFAULT UNSET của INSERT JSON là một option Java driver.” | Đây là cú pháp của CQL JSON, khác với bind marker UNSET |
| “CqlSession phải close sau mỗi PATCH.” | Dùng session có vòng đời dài, Spring quản lý |

## 23. Bài tập tổng hợp: triển khai PATCH hồ sơ an toàn

**Đề bài:** xây endpoint `PATCH /users/{userId}/profile` với ba trường `displayName`, `bio`, `avatarUrl`. Yêu cầu của client:

- Field **vắng mặt**: **giữ nguyên** giá trị và TTL hiện có.
- Field **có JSON null**: **xóa** giá trị.
- Field **có chuỗi hợp lệ**: **ghi mới**, kể cả chuỗi rỗng nếu contract cho phép.
- Request **không có thay đổi**: trả kết quả no-op, không phát write.
- Không được xóa hoặc đổi những field ngoài yêu cầu.

Các bước:

1. Tạo bảng `user_profiles_by_id` với partition key `user_id` theo schema của bài.
2. Ghi một profile có đầy đủ tên, bio và avatar.
3. Viết parser JSON phân biệt absent/null/text bằng `JsonNode.has(...)`.
4. Chuyển từng field thành `PatchField.KEEP`, `CLEAR` hoặc `SET`.
5. Tạo một `PreparedStatement` có đủ các bind markers cho những field cho phép update.
6. Mỗi request gọi `bind()` mới; dùng `unset`, `setToNull` hoặc `setString` theo từng ý định; luôn bind `user_id`.
7. Kiểm thử request chỉ đổi tên, bio/avatar không đổi.
8. Kiểm thử request xóa bio, avatar vẫn giữ nguyên; quan sát semantics tombstone.
9. Ghi bio với TTL 120 giây, sau đó PATCH avatar với bio UNSET; kiểm tra bio không được gia hạn TTL.
10. Kiểm thử PATCH toàn KEEP và xác minh service không thực thi mutation.
11. Thử hai PATCH đồng thời, mỗi PATCH thay một field khác nhau; so sánh với cách cập nhật snapshot đầy đủ.
12. Nếu cần ngăn lost update, thêm `version`/LWT thích hợp và kiểm tra `ResultSet.wasApplied()`.
13. Chạy integration test với đúng Spring Data Cassandra và Java driver của dự án; không dựa hoàn toàn vào unit test DTO.
14. Đo số update, tỷ lệ field bị CLEAR, tombstone warnings và độ trễ khi dữ liệu tăng.

**Tiêu chí hoàn thành:** từ một JSON request bất kỳ, người học chỉ ra chính xác cột nào **giữ nguyên**, cột nào **bị xóa**, cột nào **được ghi mới**, TTL của từng cột có thay đổi không, và request có rủi ro cạnh tranh cần CAS không.

## 24. Câu hỏi tự kiểm tra

1. UNSET trong prepared statement khác gì với bind NULL?
2. Một cột **không xuất hiện trong `SET`** và một cột có bind marker UNSET giống và khác nhau ở đâu?
3. Vì sao UPDATE bind NULL vào một cột có thể phát sinh tombstone?
4. UNSET có dọn tombstone đã có của lần xóa trước không?
5. Nếu bio có TTL 120 giây, PATCH tên với bio UNSET ở giây 50 có gia hạn bio đến giây 170 không?
6. Ghi lại `bio = "A"` với TTL mới có tương đương giữ nguyên bio không? Vì sao?
7. Nếu một câu UPDATE không chỉ định TTL nhưng ghi lại một cell có TTL cũ, có thể mặc định TTL cũ được giữ không?
8. `TTL(bio)` và `WRITETIME(bio)` khác nhau về ý nghĩa và đơn vị?
9. Vì sao `SELECT bio` trả null không chứng minh không còn tombstone?
10. Tại sao `UNSET` không phải giá trị dữ liệu của một hàng?
11. Điều gì có thể xảy ra nếu UNSET `user_id` trong `WHERE user_id = ?`?
12. Trong Java driver 4.x, vì sao phải chain hoặc gán lại giá trị trả từ `BoundStatement.unset(...)`?
13. `setString(index, "")` khác gì với `setToNull(index)` và `unset(index)`?
14. Vì sao request JSON `{}` phải khác `{"bio":null}` nếu API PATCH yêu cầu ba trạng thái?
15. Vì sao `Optional<String>` đơn thuần chưa đủ để mô tả PATCH?
16. `INSERT JSON ... DEFAULT UNSET` khác gì với `DEFAULT NULL`?
17. Vì sao `repository.save(entity)` không nên được mặc nhiên coi là selective PATCH?
18. Khi hai writer sửa **hai cột khác nhau** và UNSET cột còn lại, rủi ro ghi đè giảm như thế nào?
19. Khi hai writer cùng sửa **bio**, UNSET có bảo vệ được cả hai không? Khi nào cần LWT?
20. Vì sao một PATCH tất cả KEEP nên được xử lý như no-op ở service?
21. UNSET có đảm bảo không phát request mạng nào hay không? Vì sao?
22. Vì sao không nên tự giảm `gc_grace_seconds` để giải quyết lượng tombstone do PATCH null sai?
23. Những integration test nào cần chạy để chứng minh TTL của cột không bị reset khi UNSET?
24. Trong một hệ thống có nhiều keyspace, vì sao cần inject đúng `CqlSession` và đặt tên bảng rõ ràng?

**Ghi nhớ:** **UNSET nghĩa là không áp dụng mutation cho bind variable được hỗ trợ**, nên một cell đang có giá trị **giữ nguyên cả dữ liệu lẫn thông tin TTL/write timestamp hiện có**; UNSET không bảo vệ nó khỏi hết hạn hoặc ghi đồng thời. **NULL là hành động xóa có thể tạo tombstone**, còn **VALUE là một lần ghi mới** dù giá trị trông giống trước đó. Với Spring Data Cassandra, hãy mô hình hóa PATCH thành **KEEP/CLEAR/SET**, kiểm chứng cách framework ánh xạ null và dùng Java driver `BoundStatement.unset(...)`/`setToNull(...)` khi cần kiểm soát chính xác. Điều đó giúp tránh xóa nhầm dữ liệu, không reset TTL ngoài ý muốn và giảm tombstone không cần thiết, nhưng vẫn phải thiết kế đúng partition key, consistency, paging và cơ chế CAS cho các xung đột nghiệp vụ.
