# NULL, giá trị chưa được lưu và UNSET từ driver trong Apache Cassandra

Trong Apache Cassandra, ba tình huống **“chưa từng lưu giá trị”**, **“chủ động xóa giá trị bằng NULL”** và **“bỏ qua trường bằng UNSET”** có thể cho kết quả `SELECT` trông giống nhau, nhưng **không có cùng tác động lên dữ liệu và hiệu năng**. Nếu một ứng dụng Java nhận yêu cầu PATCH và đưa mọi trường không được cung cấp thành `null`, nó có thể vô tình xóa dữ liệu cũ, tạo nhiều **tombstone** và khiến truy vấn chậm hoặc khó xử lý khi replica chưa đồng bộ.

Bài này thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trong Cassandra phân tán, khóa phân vùng quyết định vị trí dữ liệu, truy vấn được thiết kế theo bảng và mức nhất quán đọc/ghi quyết định yêu cầu xác nhận giữa các replica. Vì vậy, hiểu đúng `NULL` và `UNSET` cần đi cùng **CQL INSERT/UPDATE/DELETE, Java Driver 4.x, thiết kế primary key, xử lý retry, TTL, tombstone, compaction và repair**.

## 1. Bốn trạng thái cần phân biệt

Trong một request cập nhật, trước khi bind vào CQL, ứng dụng thường gặp bốn trường hợp:

| Tình huống | Ý định nghiệp vụ | Hành vi thích hợp |
|---|---|---|
| Trường **không được gửi** trong request | Không thay đổi giá trị hiện tại | Không đưa vào phép ghi hoặc bind **UNSET** |
| Trường **có mặt và bằng `null`** | Chủ động xóa giá trị hiện tại, nếu API định nghĩa như vậy | Ghi **CQL NULL** hoặc `DELETE` cột |
| Trường **có mặt với giá trị cụ thể** | Cập nhật/ghi đè giá trị | Bind giá trị tương ứng |
| Trường **có mặt với giá trị rỗng nhưng hợp lệ** | Ghi chính giá trị rỗng/0/false | Bind `""`, `0`, `false` tùy kiểu và hợp đồng |

Điểm cốt lõi:

- **CQL `NULL` trong một mutation:** thông thường có ý nghĩa **xóa cột**; Cassandra ghi một **tombstone** để các replica nhận biết việc xóa.
- **UNSET trong prepared statement:** biến bind được đánh dấu **không tham gia mutation**. Dữ liệu cũ ở cột đó không bị thay đổi và **không phát sinh tombstone cho chính giá trị bị bỏ qua**.
- **Cột chưa từng được lưu:** không có giá trị sống để trả về; một `SELECT` thường hiển thị `null` cho cột đó.
- **Cột đã bị xóa:** đọc cũng có thể trả `null`; bên dưới có thể vẫn còn tombstone cho đến khi đủ điều kiện dọn dẹp.

**Chỉ nhìn giá trị `null` trong kết quả `SELECT` không thể kết luận cột chưa bao giờ tồn tại, vừa bị xóa, hay giá trị đã hết TTL.** Đây là khác biệt căn bản giữa *ngữ nghĩa truy vấn* và *lịch sử lưu trữ vật lý*.

## 2. Cassandra không lưu NULL như một giá trị bình thường

### 2.1. Một bảng CQL có cột được khai báo nhưng không phải row nào cũng có giá trị

Trong CQL, schema định nghĩa các cột có thể xuất hiện trong bảng. Khác với một số trực giác từ SQL quan hệ, các cột **không thuộc primary key** thường không bắt buộc phải được ghi trong mọi row.

Ví dụ:

~~~cql
CREATE TABLE customer_profiles_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    bio text,
    loyalty_points int,
    marketing_opt_in boolean,
    updated_at timestamp
);
~~~

Ở đây:

- `customer_id` là **partition key**: cần có giá trị hợp lệ để xác định row.
- `display_name`, `bio`, `loyalty_points`, `marketing_opt_in`, `updated_at` là **cột thường**: có thể chưa được lưu.
- Schema **không tự tạo giá trị mặc định** `0` cho `loyalty_points` hay `false` cho `marketing_opt_in`.
- `NULL` **không phải** một giá trị khóa phân vùng hợp lệ; các thành phần `PRIMARY KEY` cần được cung cấp và không được null.

Một số hệ cơ sở dữ liệu quan hệ có `NOT NULL` trên cột thường và có phép kiểm tra null theo ba giá trị logic SQL. Đừng mang nguyên giả định đó sang Cassandra: **CQL tập trung vào ghi/đọc theo primary key; dữ liệu thiếu và việc xóa được xử lý thông qua cấu trúc lưu trữ phân tán.**

### 2.2. Vì sao xóa tạo tombstone?

Trong Cassandra, dữ liệu được sao chép trên nhiều **replica**. Khi ứng dụng xóa một cột, nếu hệ thống chỉ xóa byte ở một replica mà không giữ dấu vết, bản sao khác đang giữ giá trị cũ có thể đồng bộ lại và khiến dữ liệu **xuất hiện trở lại**.

Cassandra dùng **tombstone** như một dấu xóa có metadata thời gian. Dấu xóa được truyền và hòa giải trong các lần đọc, ghi, repair và compaction theo quy tắc hệ thống; nó cho replica biết rằng một giá trị cũ đã bị xóa.

~~~text
Trước khi xóa:
Replica A: bio = "Thích cà phê"
Replica B: bio = "Thích cà phê"

Sau khi ghi DELETE/NULL (minh họa đơn giản):
Replica A: tombstone cho bio
Replica B: có thể còn giá trị cũ nếu chưa nhận mutation

Khi đồng bộ/đọc theo cơ chế Cassandra:
tombstone đủ mới che giá trị cũ
~~~

**Tombstone không phải lỗi dữ liệu.** Nó là cơ chế cần thiết cho xóa phân tán. Vấn đề xuất hiện khi ứng dụng tạo **rất nhiều tombstone không cần thiết**, ví dụ gửi hàng loạt giá trị NULL cho những cột chỉ đơn giản là không được cung cấp.

Tombstone không nhất thiết bị xóa ngay. Việc dọn dẹp phụ thuộc vào nhiều điều kiện an toàn, `gc_grace_seconds`, trạng thái replica và compaction. Không được hứa rằng một lần compaction hoặc một mốc TTL sẽ lập tức xóa hết dấu xóa.

## 3. Thực hành CQL: INSERT thiếu cột, NULL và DELETE

Để thấy rõ tác động, dùng cùng bảng `customer_profiles_by_id` với một khóa cố định.

### Bước 1 — Ghi một số cột, bỏ các cột còn lại

~~~cql
INSERT INTO customer_profiles_by_id (
    customer_id, display_name, loyalty_points, marketing_opt_in
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'Nguyễn Hà', 0, false
);

SELECT customer_id, display_name, bio,
       loyalty_points, marketing_opt_in
FROM customer_profiles_by_id
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Kết quả có thể được công cụ hiển thị gần như:

~~~text
display_name | bio  | loyalty_points | marketing_opt_in
-------------+------+----------------+-----------------
Nguyễn Hà    | null | 0              | false
~~~

Ở đây `bio` **chưa được ghi**, không có nghĩa ứng dụng đã gửi một lệnh xóa `bio`. Ngược lại, `0` và `false` là **giá trị thật**, không phải null. CQL không tự suy ra `false` từ “chưa có marketing consent” hoặc `0` từ “chưa tính điểm”.

### Bước 2 — INSERT thêm một cột trên cùng primary key

~~~cql
INSERT INTO customer_profiles_by_id (customer_id, bio)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Thích cà phê và sách'
);
~~~

Một `INSERT` trong Cassandra mặc định là **upsert**: nếu row có cùng primary key đã tồn tại, các cột được nêu trong lệnh sẽ được ghi/cập nhật. Các cột **không được nêu** trong `INSERT ... VALUES` vẫn giữ nguyên giá trị trước đó. Trong ví dụ này, `display_name`, `loyalty_points`, `marketing_opt_in` không bị xóa.

Điều này khác với `INSERT JSON` mặc định (xem phần 7), nơi các trường **vắng mặt** có thể bị xử lý thành NULL nếu không yêu cầu `DEFAULT UNSET`.

### Bước 3 — Ghi NULL để xóa một cột

~~~cql
UPDATE customer_profiles_by_id
SET bio = null
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Lệnh này biểu thị **xóa `bio`**. Một tombstone có thể được lưu, và các lần đọc thông thường sau đó sẽ cho thấy `bio` không còn giá trị đang sống. Những cột khác của cùng row không bị xóa chỉ vì `bio` bằng NULL.

Lệnh tương đương về mục đích xóa cột:

~~~cql
DELETE bio
FROM customer_profiles_by_id
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

**Chú ý:** `DELETE bio` khác `DELETE FROM customer_profiles_by_id WHERE ...`. Lệnh đầu chỉ xóa cột đã nêu, lệnh sau xóa **row** theo primary key được chỉ định. Hãy chọn phạm vi xóa theo đúng yêu cầu nghiệp vụ.

### Bước 4 — UPDATE chỉ cột được cung cấp

~~~cql
UPDATE customer_profiles_by_id
SET display_name = 'Nguyễn Thị Hà'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Lệnh chỉ ghi `display_name`. Nó **không** đồng thời xóa `bio`, ghi `loyalty_points = 0` hay thay `marketing_opt_in`.

Trong Cassandra, `UPDATE` cũng có tính chất **upsert** nếu không dùng điều kiện thích hợp: nó có thể tạo dữ liệu cho một primary key chưa tồn tại. Vì thế, “UPDATE” không phải cam kết rằng row đã tồn tại từ trước; muốn có điều kiện tồn tại, cần xem xét `IF EXISTS` và chi phí LWT theo yêu cầu.

## 4. Phân biệt NULL, UNSET và giá trị thật: bảng quyết định

Giả sử `bio` của một khách hàng đang là `"Thích cà phê"`:

| Thao tác ghi | `bio` sau khi mutation được áp dụng | Tombstone cho bio từ thao tác đó? | Có làm thay đổi cột khác? |
|---|---|---|---|
| `INSERT` chỉ nêu `customer_id`, `display_name` | Giữ `"Thích cà phê"` | Không | Chỉ cột được nêu (và metadata row theo lệnh) |
| `UPDATE SET bio = 'Thích trà'` | `"Thích trà"` | Không phải phép xóa | Không |
| `UPDATE SET bio = null` | Không còn giá trị sống | **Có** | Không |
| `DELETE bio FROM ...` | Không còn giá trị sống | **Có** | Không |
| Prepared `UPDATE SET bio = ?` với biến **UNSET** | Giữ `"Thích cà phê"` | **Không** | Không đối với biến đó |
| Prepared `UPDATE SET bio = ?` với biến **CQL NULL** | Không còn giá trị sống | **Có** | Không đối với cột khác |
| Prepared `UPDATE SET bio = ?` với `""` | Chuỗi rỗng, nếu hợp đồng cho phép | Không phải phép xóa | Không |

Hãy tách hai câu hỏi:

1. **Client muốn mutation nào?** (giữ nguyên, ghi đè, xóa).
2. **SELECT hiện đọc được gì?** (giá trị sống, null, hoặc không có row).

Đôi khi kết quả `SELECT bio = null` giống nhau sau “chưa từng lưu” và “đã xóa”. Nhưng nếu muốn chống một replica giữ giá trị cũ hồi sinh dữ liệu, tombstone chính là metadata cần thiết. Không được cố loại bỏ tất cả tombstone bằng cách đổi thao tác xóa thật thành UNSET.

## 5. UNSET trong Java Driver 4.x

### 5.1. Khái niệm: UNSET là trạng thái của **bind variable**

Với Apache Cassandra Java Driver 4.x, một **prepared statement** chứa vị trí `?` hoặc named bind markers. Từ native protocol **v4** (Cassandra 2.2 trở lên), một bind variable có thể để ở trạng thái **UNSET**: Cassandra bỏ qua giá trị đó trong mutation, thay vì hiểu là NULL.

Trong Java Driver 4.x, các thao tác thường dùng là:

| API | Ý nghĩa |
|---|---|
| `builder.setString(i, value)` | Bind một giá trị `text` |
| `builder.setBoolean(i, value)` | Bind `true`/`false` |
| `builder.setToNull(i)` | Bind **CQL NULL**, yêu cầu xóa giá trị cột nếu dùng trong mutation phù hợp |
| `builder.unset(i)` | Đánh dấu biến **UNSET**; server bỏ qua cột tương ứng |
| `statement.isSet(i)` | Kiểm tra biến đã được bind hay chưa; một biến set-to-null vẫn là **đã được set** |
| `statement.isNull(i)` | Kiểm tra giá trị bind là **NULL**; không đồng nghĩa với UNSET |
| `row.isNull("column")` | Kiểm tra một cột **trong kết quả SELECT** có null hay không |

`UNSET` **không phải một giá trị lưu trong cell** và **không phải literal NULL**. Một câu lệnh CQL thông thường không có kiểu cột `unset`. Trạng thái UNSET có ý nghĩa tại thời điểm **xây dựng và gửi mutation**, không phải một “dấu giữ nguyên” tồn tại trong bảng.

**Quan trọng:** các thành phần của `PRIMARY KEY` là bắt buộc cho thao tác tìm/ghi theo khóa; **không** được bind NULL hoặc UNSET cho khóa rồi mong Cassandra tự chọn row. Nếu một PATCH không cung cấp ID/partition key, phải từ chối hoặc tìm lại khóa bằng một đường truy cập được thiết kế riêng.

### 5.2. Ví dụ Java: giữ nguyên cột bằng UNSET

Giả sử ứng dụng muốn sửa `display_name` nhưng giữ nguyên `bio` và `marketing_opt_in`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

// session là CqlSession đã kết nối và chọn keyspace phù hợp.
UUID customerId =
    UUID.fromString("11111111-1111-4111-8111-111111111111");

PreparedStatement patch = session.prepare(
    "UPDATE customer_profiles_by_id "
  + "SET display_name = ?, bio = ?, marketing_opt_in = ? "
  + "WHERE customer_id = ?");

BoundStatement bound = patch.boundStatementBuilder()
    .setString(0, "Nguyễn Thị Hà") // Ghi giá trị mới.
    .unset(1)                     // Không thay đổi bio.
    .unset(2)                     // Không thay đổi marketing_opt_in.
    .setUuid(3, customerId)       // Bắt buộc có primary key.
    .build();

session.execute(bound);
~~~

Giá trị `bio` hiện tại vẫn được giữ, bất kể nó đang là một chuỗi hay chưa từng được ghi. **Không tạo tombstone cho các cột được UNSET** trong phép ghi này.

Trong driver 4.x, `BoundStatement` là **immutable**: các phương thức kiểu `bound.unset(1)` trả về instance mới, không sửa `bound` cũ. Với `BoundStatementBuilder` ở ví dụ, có thể gọi setter trong quá trình build; sau `build()`, bản thân statement an toàn để chia sẻ theo quy tắc driver.

~~~java
BoundStatement original = patch.bind(
    "Tên cũ", "Bio cũ", true, customerId
);

BoundStatement modified = original.unset(1);

// original vẫn giữ biến bio đã bind.
// modified có biến bio là UNSET.
session.execute(modified);
~~~

**Đừng bỏ qua giá trị trả về của `unset()` trên immutable BoundStatement**. Ví dụ sau là lỗi:

~~~java
BoundStatement wrong = patch.bind(
    "Tên mới", "Dữ liệu không muốn ghi", false, customerId
);
wrong.unset(1);      // Trả về đối tượng mới nhưng bị bỏ qua.
session.execute(wrong); // Vẫn có thể ghi giá trị bio đã bind.
~~~

### 5.3. Ví dụ Java: chủ động xóa cột bằng NULL

Nếu người dùng yêu cầu xóa tiểu sử, hãy **bind NULL có chủ đích**:

~~~java
BoundStatement clearBio = patch.boundStatementBuilder()
    .unset(0)                // Giữ display_name.
    .setToNull(1)            // Chủ động xóa bio.
    .unset(2)                // Giữ marketing_opt_in.
    .setUuid(3, customerId)
    .build();

session.execute(clearBio);
~~~

Đây là một mutation xóa `bio`, không phải “không có gì để ghi”. Sau đó `bio` có thể đọc là `null`; việc xóa được biểu diễn bởi tombstone trong đường lưu trữ Cassandra.

Một số typed setters như `setString(index, null)` cũng có thể bind NULL theo codec, nhưng với code nghiệp vụ ba trạng thái, **`setToNull` diễn đạt ý định xóa rõ ràng hơn**. Với kiểu primitive như `boolean` hoặc `int`, dùng `setToNull` thay vì tìm cách truyền `null` vào `setBoolean`/`setInt`.

### 5.4. Kiểm tra trạng thái bind

~~~java
BoundStatement check = patch.boundStatementBuilder()
    .setString(0, "Tên mới")
    .unset(1)
    .setToNull(2)
    .setUuid(3, customerId)
    .build();

System.out.println(check.isSet(0)); // true: display_name có giá trị
System.out.println(check.isSet(1)); // false: bio UNSET
System.out.println(check.isSet(2)); // true: marketing_opt_in được set NULL
System.out.println(check.isNull(2)); // true: biến thứ 2 là NULL
~~~

`isSet` và `isNull` trả lời **hai câu khác nhau**. Không được dùng `isNull` thay thế hoàn toàn `isSet` khi quyết định một trường có được gửi hay không.

## 6. PATCH API: phân biệt absent, explicit null và value

Giả sử API nhận JSON để cập nhật khách hàng.

### 6.1. Ba request và ba ý nghĩa khác nhau

~~~json
{"displayName": "Nguyễn Hà"}
~~~

Chỉ thay `display_name`. Các trường không có mặt (`bio`, `marketingOptIn`) phải **giữ nguyên** nếu đó là hợp đồng PATCH của API.

~~~json
{"bio": null}
~~~

Yêu cầu **xóa tiểu sử** nếu hợp đồng quy định JSON null = clear.

~~~json
{"bio": "", "marketingOptIn": false, "loyaltyPoints": 0}
~~~

Yêu cầu ghi **chuỗi rỗng, false và 0**. Không được tự biến ba giá trị này thành null hoặc UNSET bằng các kiểm tra như `if (value)`, `if (points > 0)`, `if (!text.isBlank())` khi chúng là giá trị hợp lệ.

Với một số thư viện parse JSON sang POJO, trường **vắng mặt** và trường **explicit null** đều trở thành một thuộc tính Java bằng `null`. Khi cần mô hình ba trạng thái, nên dùng:

- Một kiểu `PatchField<T>` có các trạng thái `KEEP`, `CLEAR`, `SET`.
- Hoặc một cấu trúc JSON có kiểm tra **sự có mặt của key** (ví dụ `containsKey`) trước khi đọc giá trị.
- Hoặc một DTO hỗ trợ explicit presence, do contract/API framework quản lý.

**Chỉ dùng `Optional<T>` như một property trong DTO không tự giải quyết mọi trường hợp**, nếu deserializer đã đánh đồng trường vắng với trường explicit null.

### 6.2. Mẫu Java kết hợp enum và builder

Ví dụ sau nhấn mạnh logic ba trạng thái của `bio`. Các trường khác áp dụng tương tự.

~~~java
import com.datastax.oss.driver.api.core.cql.BoundStatementBuilder;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

enum PatchAction { KEEP, CLEAR, SET }

// patch là PreparedStatement:
// UPDATE customer_profiles_by_id
// SET display_name=?, bio=?, marketing_opt_in=?
// WHERE customer_id=?

PatchAction bioAction = PatchAction.CLEAR;  // Ví dụ từ API request.
String newBio = null;                       // Chỉ được đọc khi SET.

BoundStatementBuilder builder = patch.boundStatementBuilder()
    .unset(0)
    .unset(1)
    .unset(2)
    .setUuid(3, customerId);

switch (bioAction) {
    case KEEP:
        builder.unset(1);
        break;
    case CLEAR:
        builder.setToNull(1);
        break;
    case SET:
        if (newBio == null) {
            throw new IllegalArgumentException("SET yêu cầu một giá trị");
        }
        builder.setString(1, newBio);
        break;
}

session.execute(builder.build());
~~~

Ví dụ này dùng `CLEAR` để sinh tombstone vì người dùng **thực sự muốn xóa**. Nếu PATCH gửi cả `displayName`, `marketingOptIn` và `bio`, cần áp dụng **một quyết định riêng cho từng trường**; không biến tất cả thành NULL chỉ vì một trường được xóa.

### 6.3. Khi nào dùng câu lệnh UPDATE chỉ nêu các cột thay đổi?

Với request chỉ cập nhật vài cột, bạn có thể tạo câu lệnh CQL riêng **chỉ chứa các cột cần sửa**:

~~~cql
UPDATE customer_profiles_by_id
SET marketing_opt_in = false
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Cách này rõ ràng, ít biến và tránh bind null ngoài ý muốn. Nhưng nếu API có nhiều tổ hợp trường tùy chọn, số lượng prepared statement khác nhau có thể tăng; một prepared statement dùng **UNSET** hợp lý giúp tái sử dụng câu truy vấn.

Cần cân đối số lượng statement, hiệu năng chuẩn bị/caching, tính dễ hiểu và yêu cầu concurrency. Không dùng nối chuỗi CQL chứa input người dùng để tạo SQL/CQL động; nếu sinh câu lệnh theo tập cột đã kiểm soát, vẫn **bind giá trị** qua prepared statement.

## 7. Ngoại lệ quan trọng: INSERT JSON DEFAULT NULL và DEFAULT UNSET

Đối với `INSERT ... VALUES`, cột không được nêu thường **không bị thay đổi**. Nhưng đối với **`INSERT JSON`**, Cassandra có ngữ nghĩa mặc định khác.

Theo tài liệu CQL, khi dùng `INSERT JSON`:

- **`DEFAULT NULL`** (mặc định) khiến các cột **bị thiếu trong JSON** được xử lý như NULL, nên có thể xóa giá trị cũ và tạo tombstone.
- **`DEFAULT UNSET`** khiến các cột **bị thiếu trong JSON** được bỏ qua, nhờ đó giữ nguyên giá trị cũ và không sinh tombstone vì omission đó.
- **Giá trị explicit JSON `null`** vẫn là yêu cầu ghi NULL, **ngay cả khi dùng `DEFAULT UNSET`**; tùy chọn đó chỉ áp dụng cho **trường bị thiếu**, không áp dụng để biến explicit null thành UNSET.

Ví dụ, giả sử row đã có `bio = 'Thích cà phê'`:

~~~cql
-- CẢNH BÁO: bio và các cột thường khác không xuất hiện trong JSON
-- có thể được xử lý như NULL, xóa giá trị trước đó.
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","display_name":"Tên mới"}'
DEFAULT NULL;
~~~

Khi thật sự muốn **giữ những cột không xuất hiện trong JSON**, phải chỉ rõ:

~~~cql
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","display_name":"Tên mới"}'
DEFAULT UNSET;
~~~

Nếu JSON có `"bio": null` thì ý nghĩa là **xóa bio**:

~~~cql
-- DEFAULT UNSET chỉ bảo vệ cột bị thiếu;
-- bio có mặt với explicit null nên vẫn là mutation xóa.
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","bio":null}'
DEFAULT UNSET;
~~~

**Quy tắc review:** luôn xem xét riêng **`INSERT ... VALUES`**, **`INSERT JSON DEFAULT NULL`** và **`INSERT JSON DEFAULT UNSET`**. Không suy diễn semantics “thiếu là giữ nguyên” từ một dạng CQL sang mọi dạng CQL.

Ngoài ra, `DEFAULT UNSET` ở đây là **tùy chọn của INSERT JSON**; nó không phải một giá trị mặc định cho mọi cột trong `CREATE TABLE`.

## 8. SELECT: không nhầm row không tồn tại với cột thiếu giá trị

### 8.1. Kiểm tra bằng Row và isNull

Trong Java Driver 4.x, trước khi đọc một cột, hãy tách hai câu hỏi:

1. **Có trả về row không?** `result.one() == null` nghĩa là truy vấn không trả về hàng.
2. **Nếu có row, cột đó có giá trị sống không?** `row.isNull("column")` giúp kiểm tra.

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement select = session.prepare(
    "SELECT display_name, bio, loyalty_points, marketing_opt_in "
  + "FROM customer_profiles_by_id WHERE customer_id = ?");

Row row = session.execute(select.bind(customerId)).one();

if (row == null) {
    // Không tìm được row đang sống cho khóa này.
} else {
    String bio = row.getString("bio"); // Có thể null.

    Integer points = row.isNull("loyalty_points")
        ? null : row.getInt("loyalty_points");

    Boolean marketing = row.isNull("marketing_opt_in")
        ? null : row.getBoolean("marketing_opt_in");

    // points == 0, marketing == false KHÔNG đồng nghĩa null.
}
~~~

Đặc biệt với cột primitive `int`/`boolean`, **không được đọc bằng getter primitive rồi dựa vào 0/false để xác định “chưa có giá trị”**. Hãy kiểm tra `row.isNull` trước, rồi dùng wrapper `Integer`/`Boolean` nếu nghiệp vụ cần phân biệt ba trạng thái.

Một cột `text` có thể chứa `""` (chuỗi rỗng) — nó khác `null`. Một cột số có thể chứa `0` — nó khác `null`. Một cột boolean có thể chứa `false` — nó khác `null`. Đối với **collection**, cần kiểm tra đặc tính riêng của từng kiểu/phiên bản thay vì mặc nhiên áp dụng cách phân biệt `empty`/null như với `text`.

### 8.2. SELECT null không cho biết lịch sử tombstone

Nếu `row.getString("bio") == null`, có thể có nhiều lý do:

- `bio` chưa từng được ghi.
- `bio` đã bị xóa bằng `DELETE bio` hoặc `UPDATE SET bio = null`.
- `bio` từng có giá trị nhưng **TTL đã hết hạn**.
- Dữ liệu hoặc các replica đang ở trạng thái cần đồng bộ theo quy tắc nhất quán.

Không xây quy trình nghiệp vụ kiểu “nếu `bio` null thì chắc chắn chưa từng có tiểu sử”. Nếu cần sự thật lịch sử “đã từng có và bị xóa bởi ai, khi nào”, phải thiết kế **audit event** riêng, với khóa, người thực hiện, thời điểm và chính sách lưu giữ phù hợp.

Ngay cả khi chỉ có primary key và chưa có cột thường nào được ghi, cách Cassandra biểu diễn **row liveness** vẫn khác với một giá trị cột NULL. Đừng dùng `row == null` và `row.isNull("bio")` như hai trạng thái có thể hoán đổi.

## 9. Truy vấn theo trạng thái thiếu dữ liệu: phải thiết kế bảng

Một yêu cầu phổ biến là:

> “Tìm tất cả hồ sơ chưa có `bio` hoặc chưa xác nhận consent trong một tenant.”

Không nên mặc định rằng Cassandra có thể quét toàn cluster hiệu quả bằng:

~~~cql
-- Không dùng như mẫu truy vấn Cassandra tổng quát:
-- SELECT * FROM customer_profiles_by_id WHERE bio = null;
-- SELECT * FROM customer_profiles_by_id WHERE bio IS NULL;
~~~

Một truy vấn theo **cột thường** chưa có đường truy cập phù hợp không trở nên rẻ chỉ vì đang tìm `null`. Những cú pháp `IS NULL`/`IS NOT NULL` có thể xuất hiện trong các ngữ cảnh CQL riêng như khai báo điều kiện cho **materialized view**; không có nghĩa một bảng bất kỳ hỗ trợ hiệu quả `WHERE bio IS NULL` như SQL.

Nếu yêu cầu là “liệt kê hồ sơ cần bổ sung theo tenant và ngày”, hãy mô hình hóa **trạng thái cần xử lý** thành dữ liệu đọc được theo khóa:

~~~cql
CREATE TABLE profile_review_queue_by_tenant_day (
    tenant_id uuid,
    review_day date,
    created_at timestamp,
    customer_id uuid,
    reason text,
    PRIMARY KEY ((tenant_id, review_day), created_at, customer_id)
) WITH CLUSTERING ORDER BY (created_at ASC, customer_id ASC);
~~~

Truy vấn:

~~~cql
SELECT created_at, customer_id, reason
FROM profile_review_queue_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND review_day = '2026-11-21'
LIMIT 100;
~~~

Cách thiết kế này có các lưu ý:

- **`reason`** có thể là `MISSING_BIO` hoặc `PENDING_CONSENT` theo danh mục nghiệp vụ rõ ràng, không phải suy từ null.
- Bảng hàng đợi được cập nhật khi trạng thái hồ sơ thay đổi; cần cơ chế retry, đối soát và xóa/đánh dấu công việc đã xử lý.
- `review_day` là **partition bucket**. Nếu một tenant có lượng công việc lớn, cần bucket nhỏ hơn hoặc shard.
- Cassandra không tự đồng bộ các bảng phục vụ nhiều truy vấn thành một transaction ACID đa partition. Nếu hệ thống cần tính đúng tức thời, phải thiết kế luồng ghi và consistency phù hợp.

**Chọn kiểu NULL/UNSET là quyết định ghi cột; chọn partition key là quyết định đọc dữ liệu.** Không thể thay thế thiết kế truy vấn bằng việc cho mọi cột nhận null.

## 10. NULL/UNSET với TTL, counter, collections và primary key

### 10.1. TTL có thể làm giá trị biến mất mà không có PATCH

Cassandra có thể tự hết hạn dữ liệu theo **TTL** (đơn vị giây). Một cột đã được ghi bình thường có thể đọc thành null sau khi TTL kết thúc vì giá trị không còn sống; tombstone từ hết hạn cần được xử lý theo cơ chế lưu trữ.

~~~cql
UPDATE customer_profiles_by_id
USING TTL 3600
SET bio = 'Thông tin tạm thời'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Khi TTL hết, `bio` có thể không còn giá trị. Nhưng **UNSET không bắt đầu TTL mới** cho cột bị bỏ qua, vì không ghi giá trị mới. Nếu viết lại một cột bằng giá trị mới với TTL, cần xem xét ý nghĩa reset TTL của lần ghi đó; không nên giả định một bản cập nhật không liên quan tự kéo dài tuổi thọ của mọi cột.

Một số ứng dụng dùng `TTL(column)` để kiểm tra số giây TTL còn lại của cột thường. Tuy nhiên, `TTL(column)` không phải lịch sử đầy đủ; cột không có giá trị, cột không dùng TTL và các tình huống khác cần được diễn giải đúng theo schema/phiên bản. **Không dùng TTL để phân biệt chắc chắn “chưa từng có” và “đã bị xóa”.**

### 10.2. Primary key không được NULL/UNSET

~~~cql
-- KHÔNG HỢP LỆ: null không xác định được partition key.
-- INSERT INTO customer_profiles_by_id (customer_id, display_name)
-- VALUES (null, 'Không xác định');
~~~

Nếu dữ liệu đầu vào chưa có ID, ứng dụng phải cấp/đòi ID trước khi ghi hoặc dùng cấu trúc staging với primary key hợp lệ. Nếu muốn phân biệt “không có customer_id”, điều đó thuộc **trạng thái input trước khi ghi**, không phải một partition key null được lưu trong Cassandra.

Trong câu lệnh với biến bind `? WHERE customer_id = ?`, không unset biến khóa để biến một UPDATE thành “cập nhật tất cả khách hàng”. Cassandra không hỗ trợ cách hiểu đó.

### 10.3. Collections, UDT và các kiểu có quy tắc riêng

Đối với `list`, `set`, `map`, `tuple` hoặc user-defined type, **NULL ở cấp cột** là một câu chuyện khác với **NULL ở phần tử** hoặc **field bên trong cấu trúc**. Một số cấu trúc không chấp nhận phần tử null; một số thao tác cập nhật có thể tạo tombstone ở cấp phần tử/collection. Không áp dụng máy móc quy tắc “set null = xóa cả cột” cho mọi mutation ở mức phần tử.

Ví dụ với một `frozen<udt>`, cập nhật toàn bộ giá trị khác với một UDT không frozen được thao tác trường riêng. Cần xem quy tắc CQL của kiểu và thao tác thật sự trước khi tối ưu hóa tombstone.

### 10.4. Counter không giống cột số thường

Cassandra có kiểu `counter` và cập nhật bằng phép cộng/trừ riêng; không xem `counter` như một `bigint` nullable có thể dùng `SET count = null` hay `UNSET` để “khởi tạo lại” tùy ý. Khi cần reset hoặc chỉnh sửa bộ đếm, phải dùng quy trình thiết kế theo semantics counter và xử lý retry không idempotent.

## 11. Tombstone và hệ phân tán: khi NULL là cần thiết, khi UNSET là tối ưu

### 11.1. Tại sao tombstone nhiều gây chậm?

Trong một số mô hình workload, mỗi lần ứng dụng gửi một `UPDATE` chứa nhiều cột NULL không cần thiết, Cassandra phải ghi nhận các dấu xóa. Theo thời gian, dữ liệu có thể tích lũy tombstone trong SSTable; truy vấn cần xét tombstone để bỏ qua dữ liệu cũ, làm tăng CPU, I/O và áp lực compaction.

Ví dụ một pipeline ingest nhận 10 triệu record/ngày, mỗi record có 20 trường tùy chọn. Nếu cứ bind NULL cho tất cả trường thiếu, số dấu xóa có thể cao hơn rất nhiều so với nhu cầu nghiệp vụ, kể cả khi nhiều cột trước đó chưa từng có giá trị.

**Giải pháp:** nếu trường không được gửi nghĩa là **không thay đổi**, dùng **UNSET** hoặc không đưa cột vào mutation. Nếu nghiệp vụ yêu cầu **xóa**, vẫn phải dùng NULL/DELETE để tránh giá trị cũ tồn tại.

### 11.2. gc_grace_seconds, compaction và repair

Tombstone chỉ được dọn khi Cassandra xác định an toàn theo quy tắc hệ thống. **`gc_grace_seconds`** giúp duy trì dấu xóa đủ lâu trong các tình huống replica có thể vắng mặt; **repair** giúp đồng bộ replica để tránh dữ liệu cũ hồi sinh; **compaction** xử lý SSTable và dọn dẹp dấu xóa khi đủ điều kiện.

Không tùy ý đặt `gc_grace_seconds = 0` để “chữa” truy vấn chậm do quá nhiều NULL. Việc dọn tombstone quá sớm khi replica chưa nhận xóa có thể tạo nguy cơ **zombie data** (dữ liệu tưởng đã xóa xuất hiện lại). Chính sách repair, cấu hình compaction, TTL và lịch vận hành phải được đánh giá cùng workload.

**UNSET giảm số tombstone không cần thiết, nhưng không thay thế cho xóa dữ liệu thực sự hoặc repair.**

### 11.3. Write timestamp, retry và xung đột

Cassandra có metadata write timestamp cho cell dùng trong quy tắc giải quyết xung đột. Một mutation xóa với NULL/DELETE tạo tombstone có metadata để che các giá trị cũ theo quy tắc timestamp và loại mutation; các phiên bản ghi về sau hoặc ghi có timestamp khác có thể ảnh hưởng kết quả đọc.

Ở hệ phân tán, timeout không chứng minh lệnh chưa được áp dụng. Nếu client retry:

- Giữ **cùng primary key** và cùng **ý định PATCH** cho một yêu cầu nghiệp vụ.
- Với thao tác xóa thật, retry xóa là một yêu cầu nghiệp vụ hợp lệ, nhưng cần cân nhắc **write timestamp** và các ghi đồng thời (ví dụ người dùng vừa cập nhật lại bio).
- Đừng đánh tráo `NULL` thành `UNSET` trong lần retry: đó là **thay đổi ý nghĩa mutation**.
- Nếu phải chống cập nhật cạnh tranh, đánh dấu phiên bản, cân nhắc **LWT/IF** với khóa phù hợp, hoặc áp dụng cơ chế điều phối ở ứng dụng; `LOCAL_QUORUM` không tự bảo đảm “PATCH cuối theo thời gian thực luôn thắng” khi có nhiều writer.

Trong Cassandra, `WRITETIME(column)` cho biết metadata ghi của một **cột thường đang có giá trị phù hợp**; nó không phải lịch sử toàn bộ request PATCH và không thay thế audit log. Nó cũng không làm một giá trị `null` trong `SELECT` trở thành bằng chứng “chưa từng được lưu”.

## 12. Mapper và những lỗi chuyển đổi ở tầng Java

Nếu sử dụng **DataStax/Apache Java Driver Mapper 4.x**, chú ý cấu hình **NullSavingStrategy** (tên có thể xuất hiện trong cấu hình mapper):

| Chiến lược | Hành vi đối với property Java `null` | Hệ quả |
|---|---|---|
| **`DO_NOT_SET`** | Không bind property đó, tương đương biến bị bỏ qua | Giữ giá trị cũ, tránh tombstone không cần thiết |
| **`SET_TO_NULL`** | Bind CQL NULL cho property đó | Có thể xóa giá trị cũ và tạo tombstone |

Một entity Java với `bio == null` có thể mang ý nghĩa **“không biết bio vì không tải trường này”** hoặc **“muốn xóa bio”**. Mapper không thể tự đoán ý định nghiệp vụ. Hãy dùng DTO/PATCH model có phân biệt trạng thái, không dựa duy nhất vào object model được serialize.

Các lỗi khác:

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Xem missing JSON field là `null` cần ghi | Xóa nhiều cột ngoài ý muốn | Kiểm tra field presence và dùng UNSET |
| Xem explicit JSON null là UNSET | Người dùng muốn xóa nhưng cột vẫn còn | Bind `setToNull` hoặc `DELETE` |
| Lấy `row.getBoolean` rồi coi `false` là thiếu | Mất ý nghĩa `false` thật | `row.isNull` trước khi đọc |
| Xem `loyalty_points=0` là NULL | Sai tính toán và báo cáo | Giữ số 0 là giá trị hợp lệ |
| Bỏ qua kết quả `bound.unset()` của driver 4 | Statement gốc không đổi, có thể ghi nhầm | Gán lại kết quả hoặc dùng builder |
| Dùng `INSERT JSON` mặc định cho partial update | Trường thiếu có thể bị xóa | `DEFAULT UNSET` hoặc prepared statement |
| Bind `null` cho khóa | Không có partition key hợp lệ | Validate toàn bộ primary key |
| Xem `null` từ SELECT là “chưa từng ghi” | Sai lịch sử nghiệp vụ | Thiết kế audit/metadata riêng |
| Gửi NULL cho mọi trường tùy chọn trên mỗi request | Bùng nổ tombstone, đọc chậm | UNSET trường không được cập nhật |
| Đổi DELETE thành UNSET để “tránh tombstone” | Không còn thực sự xóa dữ liệu | Dùng DELETE/NULL cho yêu cầu xóa |
| Giảm `gc_grace_seconds` thiếu đánh giá | Nguy cơ dữ liệu cũ xuất hiện lại | Repair và compaction theo quy trình an toàn |

## 13. Bài tập tình huống

### Bài 1 — Một PATCH, ba giá trị khác nhau

Row hiện có:

~~~text
customer_id = 11111111-1111-4111-8111-111111111111
display_name = "Hà"
bio = "Thích cà phê"
marketing_opt_in = true
~~~

API nhận:

~~~json
{"displayName": "Nguyễn Hà", "bio": null}
~~~

**Câu hỏi:** sau PATCH, ba cột `display_name`, `bio`, `marketing_opt_in` phải có trạng thái gì?

**Đáp án:** `display_name = "Nguyễn Hà"`, `bio` bị xóa (`NULL`/tombstone), `marketing_opt_in` vẫn `true` (UNSET/không ghi). Không được tự chuyển marketing consent thành `false`.

### Bài 2 — False và null

Một cột `marketing_opt_in boolean` được truy vấn. Kết quả ứng dụng trả `false` cho cả row chưa có giá trị lẫn row đã chọn không đồng ý.

**Câu hỏi:** vấn đề ở đâu?

**Đáp án:** ứng dụng đã làm mất sự khác biệt giữa **“chưa có quyết định”** và **“đã từ chối”**. Cần kiểm tra `row.isNull("marketing_opt_in")` trước khi gọi `getBoolean`, rồi biểu diễn bằng `Boolean` hoặc trạng thái nghiệp vụ rõ ràng.

### Bài 3 — INSERT JSON gây mất dữ liệu

Row có `bio = "Thích cà phê"`. Worker dùng:

~~~cql
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","display_name":"Hà mới"}';
~~~

**Câu hỏi:** `bio` có được giữ nguyên chắc chắn không?

**Đáp án:** không. `INSERT JSON` mặc định xử lý các cột thiếu như NULL và có thể xóa giá trị cũ. Dùng **`DEFAULT UNSET`** nếu mục tiêu là partial upsert; explicit JSON null vẫn có nghĩa xóa.

### Bài 4 — Hai lệnh sau có tương đương?

~~~java
builder.unset(1);     // A
builder.setToNull(1); // B
~~~

**Đáp án:** không. A bỏ qua biến số 1 và giữ nguyên giá trị cột tương ứng; B bind NULL và có thể tạo tombstone để xóa giá trị cột đó.

### Bài 5 — Query báo cáo thiếu bio

Yêu cầu: “Hằng ngày lấy 100 hồ sơ thiếu bio mới nhất của một tenant.” Bảng chỉ có `PRIMARY KEY(customer_id)`, `tenant_id`, `bio` là cột thường.

**Câu hỏi:** có nên quét tất cả profile bằng `WHERE bio IS NULL` không?

**Đáp án:** không nên xem đó là đường truy vấn mặc định. Thiết kế một bảng/hàng đợi theo `tenant_id + day`, clustering theo thời điểm và customer ID, hoặc một cơ chế indexing phù hợp được kiểm chứng; cập nhật trạng thái thiếu bio khi dữ liệu thay đổi.

## 14. Checklist khi review NULL, thiếu giá trị và UNSET

- [ ] API đã phân biệt **trường không được gửi**, **explicit null**, **giá trị cụ thể** và **giá trị rỗng hợp lệ**?
- [ ] Với PATCH, trường bị thiếu được **UNSET/không ghi**, không vô tình thành CQL NULL?
- [ ] Khi thật sự cần xóa, có dùng **NULL/DELETE** thay vì UNSET để đảm bảo replica biết về lần xóa?
- [ ] Mọi thành phần `PRIMARY KEY` đã có giá trị và không bị bind NULL/UNSET?
- [ ] Đã phân biệt `INSERT ... VALUES` với `INSERT JSON DEFAULT NULL` và `DEFAULT UNSET`?
- [ ] Java Driver 4.x đã dùng đúng `unset`, `setToNull`, `isSet` và xử lý tính bất biến của BoundStatement?
- [ ] Khi đọc, đã phân biệt **không có Row** với **có Row nhưng cột null**?
- [ ] Các giá trị `false`, `0`, `""` được giữ đúng ngữ nghĩa, không bị xem là thiếu?
- [ ] Với TTL, đã hiểu hết hạn cột có thể khiến SELECT trả null nhưng không chứng minh cột chưa từng tồn tại?
- [ ] Nếu cần audit việc xóa, đã có log/sự kiện riêng thay vì suy từ null?
- [ ] Truy vấn theo trạng thái thiếu dữ liệu đã có **partition key/đường truy cập** phù hợp, không phụ thuộc quét toàn cluster?
- [ ] Đã đo tombstone, kích thước partition, độ trễ p95/p99 và kế hoạch compaction/repair/gc_grace_seconds?
- [ ] Retry/đồng thời trên cùng primary key có giữ ý định xóa/giữ/ghi và có cơ chế chống ghi đè sai?
- [ ] Nếu dùng Mapper, đã kiểm tra `NullSavingStrategy.DO_NOT_SET` vs `SET_TO_NULL`?

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Manipulation (INSERT/UPDATE/DELETE)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra — JSON Support và DEFAULT UNSET](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/json.html).
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/tombstones.html).
- [Apache Cassandra Java Driver 4.x — Prepared statements và UNSET](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).
- [Apache Cassandra Java Driver 4.x — Mapper null saving strategy](https://apache.github.io/cassandra-java-driver/4.18.0/mapper/daos/null_saving/).
- [Apache Cassandra Java Driver 4.x — SettableByIndex.setToNull](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/data/SettableByIndex.html).

**Ghi nhớ:** **NULL xóa; UNSET bỏ qua; chưa từng lưu không phải là một giá trị đang sống**. Cả cột chưa được lưu lẫn cột đã bị xóa đều có thể đọc thành `null`, nhưng việc xóa phải để lại metadata phù hợp cho replica. Trong Java Driver, hãy thiết kế PATCH với ba trạng thái **KEEP / CLEAR / SET**, bind đúng `unset` hoặc `setToNull`, và dùng primary key/đường truy cập rõ ràng. Đó là cách giữ được ngữ nghĩa nghiệp vụ và tránh tombstone không cần thiết trong Cassandra phân tán.

