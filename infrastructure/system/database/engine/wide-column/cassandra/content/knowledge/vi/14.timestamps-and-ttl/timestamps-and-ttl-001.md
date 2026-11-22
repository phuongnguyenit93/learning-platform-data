# Mutation timestamp và quy tắc last-write-wins trong Apache Cassandra

## 1. Bối cảnh: nhiều replica có thể nhận các phiên bản khác nhau

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Một partition được lưu trên nhiều replica theo cấu hình replication; các bản ghi đến những replica đó có thể không cùng thứ tự, đặc biệt khi có độ trễ mạng, retry hoặc nhiều ứng dụng ghi đồng thời. Cassandra cần một quy tắc nhất quán để chọn giá trị khi các phiên bản xung đột.

Quy tắc mặc định cho dữ liệu thông thường là **last-write-wins (LWW)**: với cùng một ô dữ liệu (*cell*), phiên bản có **mutation timestamp lớn hơn** được ưu tiên. Chữ “last” ở đây chỉ **timestamp của lần ghi**, không nhất thiết là thao tác đến replica cuối cùng hoặc thao tác người dùng thực hiện sau cùng theo đồng hồ thực tế.

Ví dụ, cùng một khách hàng có cột `display_name` được ghi ở hai nơi:

| Lệnh ghi | Thời điểm replica nhận | Mutation timestamp (micro giây) | Giá trị |
|---|---|---:|---|
| A | Đến sau | `1760000000001000` | `An` |
| B | Đến trước | `1760000000002000` | `Bình` |

Sau khi các phiên bản được đối chiếu, **`Bình` thắng** vì timestamp của B lớn hơn, dù A đến sau. Đây là điểm cốt lõi để hiểu xung đột ghi trong Cassandra.

## 2. Mutation timestamp là gì?

**Mutation** là thay đổi dữ liệu, như `INSERT`, `UPDATE` hoặc `DELETE`. Mỗi cell dữ liệu thông thường được gắn một **write timestamp** kiểu số nguyên 64-bit, biểu diễn số **micro giây kể từ Unix epoch (1970-01-01 00:00:00 UTC)**. Cassandra dùng số này khi hòa giải các phiên bản dữ liệu giữa replica.

- **Không phải cột ứng dụng:** `created_at timestamp` hay `updated_at timestamp` do ta tự thiết kế chỉ là dữ liệu của bảng; Cassandra không tự lấy các cột đó làm thứ tự LWW.
- **Không phải thời điểm nhận trên đĩa:** ghi đến node sau vẫn có thể thua nếu mutation timestamp thấp hơn.
- **Có thể do nhiều nơi cung cấp:** CQL chỉ định qua `USING TIMESTAMP`, driver gắn query timestamp hoặc coordinator tạo timestamp mặc định nếu request không cung cấp. Chính sách thực tế phụ thuộc cấu hình driver và đường đi của lệnh ghi.
- **Có độ phân giải micro giây:** khác với kiểu dữ liệu CQL `timestamp`, thường biểu diễn thời gian ở độ phân giải mili giây. Nhầm mili giây với micro giây có thể gây ra thứ tự ghi bất ngờ.
- **Được áp dụng ở mức cell:** một câu `UPDATE` có thể ghi nhiều cell cùng một timestamp, nhưng các cột trong một hàng vẫn có thể giữ timestamp khác nhau từ những lần cập nhật khác nhau.

Khi muốn xem timestamp thực sự gắn với một cột thông thường, dùng hàm CQL `writetime()`:

```sql
SELECT customer_id, display_name, writetime(display_name)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

`writetime(display_name)` trả về timestamp của cell đang tồn tại (đơn vị micro giây). Không dùng hàm này cho cột khóa chính hoặc counter; cell bị xóa hay chưa có dữ liệu thường được biểu diễn bằng `null` trong kết quả truy vấn.

## 3. Quy tắc LWW hoạt động như thế nào?

Giả sử hai mutation cùng thay đổi **một cell** của cùng partition/row:

1. Cassandra so sánh mutation timestamp của các phiên bản.
2. **Timestamp lớn hơn thắng** và trở thành giá trị được nhìn thấy khi các replica đã đối chiếu.
3. Nếu hai phiên bản có **timestamp bằng nhau**, Cassandra sử dụng quy tắc phân xử xác định khác; trong trường hợp ghi so với tombstone ở cùng timestamp, **tombstone được ưu tiên**. Với hai giá trị sống khác nhau, không được giả định lệnh đến sau sẽ thắng. Ứng dụng nên tránh cố tình tạo các bản ghi xung đột cùng timestamp.

Điểm quan trọng là **đơn vị giải quyết xung đột là cell**, không phải toàn bộ hàng. Nếu request X đổi `display_name` ở timestamp `T2` và request Y đổi `email` ở `T3`, cả hai thay đổi có thể cùng xuất hiện trong hàng vì chúng tác động lên hai cell khác nhau.

```text
                 Partition: customer_id = ...
                         |
              +----------+----------+
              |                     |
    display_name (T2)           email (T3)
        "Bình"              "binh@example.com"

    Mỗi cell giữ phiên bản thắng theo timestamp riêng.
```

Khi một thao tác ghi nhiều cột, các cột được gắn timestamp tương ứng với mutation đó; tuy nhiên LWW **không** biến toàn bộ row thành một đối tượng được thay thế nguyên khối. Với các kiểu collection, Cassandra còn có chi tiết về cell/phần tử và kiểu `frozen`, nên không suy rộng ví dụ cell đơn giản cho mọi cấu trúc dữ liệu.

## 4. Thực hành CQL: quan sát ghi cũ, ghi mới và xóa

Các lệnh sau chạy trong một **keyspace thử nghiệm** đã được tạo và chọn bằng `USE <keyspace>;`. Dùng `customer_id` chưa từng ghi trước đó để không bị ảnh hưởng bởi timestamp tồn tại từ lần chạy khác.

### Bước 1 — Tạo bảng và ghi dữ liệu ban đầu

```sql
CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id uuid PRIMARY KEY,
    display_name text,
    email text
);

INSERT INTO customer_profiles (customer_id, display_name, email)
VALUES (
    11111111-1111-1111-1111-111111111111,
    'An',
    'an@example.com'
)
USING TIMESTAMP 1760000000000000;

SELECT display_name, writetime(display_name),
       email, writetime(email)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

Hai cell `display_name` và `email` đều mang timestamp `1760000000000000`.

### Bước 2 — Thử ghi với timestamp **cũ hơn**

```sql
UPDATE customer_profiles
USING TIMESTAMP 1759999999999000
SET display_name = 'Bình'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

SELECT display_name, writetime(display_name)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

Kết quả vẫn là **`An`**, timestamp vẫn là `1760000000000000`: phiên bản `'Bình'` có timestamp nhỏ hơn nên không thể thay thế cell đang thắng, dù câu `UPDATE` vừa được thực thi thành công.

### Bước 3 — Ghi với timestamp **mới hơn**

```sql
UPDATE customer_profiles
USING TIMESTAMP 1760000000002000
SET display_name = 'Bình'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

SELECT display_name, writetime(display_name),
       email, writetime(email)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

Lúc này `display_name = 'Bình'` có timestamp `1760000000002000`, trong khi `email = 'an@example.com'` vẫn mang timestamp cũ. Đó là minh họa trực tiếp cho LWW ở mức cell.

### Bước 4 — Xóa tạo tombstone

```sql
DELETE display_name FROM customer_profiles
USING TIMESTAMP 1760000000003000
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

-- Ghi muộn về thời gian thực, nhưng timestamp lại cũ hơn tombstone.
UPDATE customer_profiles
USING TIMESTAMP 1760000000002500
SET display_name = 'Chi'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

SELECT display_name, email
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

`display_name` vẫn là `null`; cột `email` vẫn có dữ liệu. `DELETE` không chỉ xóa một chuỗi khỏi bản ghi mà tạo **tombstone** để đánh dấu dữ liệu đã xóa. Tombstone với timestamp `1760000000003000` che các phiên bản cũ hơn (và phiên bản sống có timestamp bằng nó), ngăn các replica mang dữ liệu cũ làm sống lại giá trị khi đồng bộ.

Một lần ghi có timestamp **cao hơn tombstone** mới có thể tạo giá trị nhìn thấy trở lại:

```sql
UPDATE customer_profiles
USING TIMESTAMP 1760000000004000
SET display_name = 'Chi'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

> **Lưu ý về thí nghiệm:** Những timestamp trên được cố ý cố định để minh họa thứ tự xung đột. Không dùng lại các con số đó như timestamp thủ công cho dữ liệu thật. Nếu đã chạy thử nhiều lần trên cùng khóa chính, nên dùng khóa mới để tránh trạng thái tombstone hoặc timestamp từ lần trước ảnh hưởng đến kết quả.

## 5. LWW tương tác với replication và consistency level

Với replication factor `RF = 3`, một partition có ba replica. Nếu ghi tại `CL = ONE`, coordinator có thể xác nhận sau khi số replica đáp ứng mức nhất quán đó; các replica khác có thể chưa thấy phiên bản mới ngay lúc ấy. Khi đọc, Cassandra đối chiếu dữ liệu thu được từ các replica tham gia truy vấn và dùng timestamp để giải quyết phiên bản khác nhau. Các cơ chế sửa chữa và đồng bộ replica giúp đưa dữ liệu về trạng thái thống nhất theo thời gian.

```text
       Ứng dụng A                          Ứng dụng B
       ghi name=An                        ghi name=Bình
       ts=100                             ts=200
             \                           /
              \                         /
               v                       v
                  Cassandra cluster
               /          |          \
           Replica 1   Replica 2    Replica 3
           thấy ts=100 thấy ts=200   tạm thời cũ
               \          |          /
                +---- hòa giải ------+
                       ts=200 thắng
```

**Consistency level** và **LWW** trả lời hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi được trả lời | Điều không bảo đảm |
|---|---|---|
| `ONE`, `QUORUM`, `ALL` khi ghi/đọc | Cần bao nhiêu replica tham gia hoặc phản hồi để thao tác đáp ứng mức nhất quán yêu cầu? | Không tự biến timestamp thấp thành bản ghi thắng. |
| Last-write-wins | Khi nhiều phiên bản cùng một cell xung đột, phiên bản nào thắng? | Không bảo đảm bản ghi thắng là thao tác người dùng gửi cuối theo thời gian thực. |
| Lightweight transaction (`IF ...`, Paxos) | Có thể kiểm tra điều kiện và cập nhật có điều phối cho trường hợp cần thứ tự/điều kiện mạnh hơn không? | Không miễn phí: có thêm độ trễ và chi phí điều phối. |

Ví dụ, tăng mức ghi lên `ALL` không cứu được một cập nhật mới có timestamp thấp hơn tombstone cũ. Ngay cả cặp đọc/ghi `QUORUM` có giao nhau cũng không thay đổi nguyên tắc chọn phiên bản theo timestamp. Khi nghiệp vụ đòi **compare-and-set**, chống ghi đè có điều kiện hoặc trạng thái phải tiến theo thứ tự rõ ràng, nên cân nhắc **lightweight transaction (LWT)** và thiết kế khóa phù hợp thay vì chỉ dựa vào LWW.

## 6. Timestamp lệch đồng hồ và các lỗi khó phát hiện

LWW phụ thuộc trực tiếp vào timestamp do client hoặc coordinator đưa vào mutation. Vì vậy sai lệch đồng hồ giữa các máy có thể ảnh hưởng đến dữ liệu lâu hơn thời gian mạng chậm.

**Tình huống future timestamp:** máy A có đồng hồ chạy nhanh và ghi `'Đã duyệt'` với timestamp tương lai `T+10 phút`. Máy B hoạt động đúng giờ và cập nhật `'Đã hủy'` một phút sau theo thời gian thật, nhưng timestamp của B vẫn nhỏ hơn của A. LWW tiếp tục chọn `'Đã duyệt'`. Việc tăng `CL` không sửa được thứ tự này.

Các nguyên tắc vận hành:

1. Đồng bộ đồng hồ các host/coordinator bằng dịch vụ đồng bộ thời gian, đồng thời giám sát **clock skew**.
2. Chỉ tự cung cấp `USING TIMESTAMP` khi có yêu cầu rõ ràng về thứ tự từ nguồn sự kiện và bảo đảm đơn vị **micro giây**. Nếu nhiều dịch vụ dùng timestamp tự sinh, phải thống nhất nguồn, đơn vị và cách xử lý xung đột.
3. Trong ứng dụng Java, xem cấu hình **timestamp generator** của Cassandra driver. Một số driver tạo timestamp phía client, có thể hỗ trợ tăng đơn điệu trên một tiến trình; điều đó không mặc nhiên giải quyết đồng hồ lệch giữa nhiều máy.
4. Với retry cùng một sự kiện, nên dùng lại timestamp ổn định của mutation khi nghiệp vụ cần tính idempotent. Tạo timestamp mới trên mỗi retry có thể vô tình làm sự kiện cũ thắng sự kiện mới hơn.
5. Tránh gán timestamp cực lớn hoặc ở tương lai. Nó có thể khiến các lần ghi bình thường về sau liên tục bị che khuất.

### Minh họa từ Java

Giả sử ứng dụng đã có `CqlSession` kết nối đến cluster bằng DataStax/Apache Cassandra Java Driver, ta có thể truyền timestamp nguồn qua prepared statement:

```java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class CustomerProfileRepository {
    private final CqlSession session;
    private final PreparedStatement updateName;

    public CustomerProfileRepository(CqlSession session) {
        this.session = session;
        this.updateName = session.prepare(
            "UPDATE customer_profiles " +
            "USING TIMESTAMP ? " +
            "SET display_name = ? WHERE customer_id = ?"
        );
    }

    public void updateName(UUID customerId, String name, long eventTimeMicros) {
        session.execute(updateName.bind(eventTimeMicros, name, customerId));
    }
}
```

`eventTimeMicros` phải là **`long` biểu diễn micro giây**, được tính và kiểm soát theo chính sách nghiệp vụ. Đừng đưa trực tiếp `System.currentTimeMillis()` vào tham số này: giá trị trả về có đơn vị **mili giây** và sẽ sai lệch khoảng 1.000 lần so với timestamp micro giây hiện tại. Nếu không có lý do kiểm soát timestamp thủ công, có thể để driver/coordinator áp dụng chính sách timestamp đã cấu hình.

## 7. Phân biệt mutation timestamp, TTL và các loại thời gian khác

Trong chương **Timestamp và TTL**, cần phân biệt ba khái niệm:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Mutation timestamp** | Quyết định phiên bản cell nào thắng khi có xung đột | `USING TIMESTAMP 1760000000002000`, `writetime(display_name)` |
| **TTL (time to live)** | Xác định dữ liệu sống bao lâu trước khi hết hạn và được xử lý như dữ liệu đã xóa | `USING TTL 3600` cho cell hết hạn sau khoảng một giờ |
| **Cột CQL kiểu `timestamp`** | Lưu mốc thời gian của nghiệp vụ để truy vấn | `created_at timestamp`, `event_time timestamp` |

Ví dụ có thể viết `INSERT ... USING TIMESTAMP <microseconds> AND TTL 3600`: timestamp phục vụ phân xử phiên bản, còn TTL phục vụ vòng đời dữ liệu. Một giá trị đã hết TTL sẽ được xử lý như dữ liệu hết hạn/tombstone trong Cassandra. Không nên hiểu TTL là “timestamp mới hơn” hay cho rằng có TTL thì một mutation luôn thắng các mutation khác.

**Ngoại lệ quan trọng:** cột kiểu `counter` dùng cơ chế cập nhật riêng và không áp dụng kiểu ghi LWW thông thường; không gắn `USING TIMESTAMP` thủ công cho cập nhật counter. Các thao tác LWT (`IF NOT EXISTS`, `IF ...`) cũng có quy tắc điều phối riêng, cần xem xét độc lập khi cần tính đúng đắn theo điều kiện.

## 8. Cách chẩn đoán một cập nhật “thành công nhưng không thấy giá trị mới”

Khi `UPDATE` trả thành công mà `SELECT` vẫn thấy giá trị cũ, hãy kiểm tra theo trình tự sau:

| Bước | Kiểm tra | Lý do |
|---|---|---|
| 1 | Xác nhận đúng keyspace, partition key, clustering key và cột được cập nhật | Hai mutation chỉ xung đột khi cùng vị trí dữ liệu. |
| 2 | `SELECT value, writetime(value)` ở cột còn tồn tại | Xem phiên bản hiện thắng và mutation timestamp của nó. |
| 3 | Kiểm tra `USING TIMESTAMP`, timestamp generator của driver và log sự kiện | Tìm timestamp sai đơn vị, cũ hơn hoặc ở tương lai. |
| 4 | Kiểm tra các lệnh `DELETE` và TTL có thể đã áp dụng | Tombstone có thể che các bản ghi cũ; `writetime()` không tự hiển thị timestamp của tombstone đã xóa. |
| 5 | Đối chiếu RF, consistency level, replica không sẵn sàng và tình trạng repair | Phân biệt xung đột phiên bản với việc replica chưa đồng bộ. |

Tombstone còn liên quan đến **compaction**, thời gian giữ tombstone (`gc_grace_seconds` trong những cấu hình áp dụng) và **repair**. Xóa tombstone quá sớm khi replica vẫn giữ dữ liệu cũ có thể dẫn đến hiện tượng dữ liệu bị xóa xuất hiện trở lại (*zombie data*). Vì vậy thiết kế thời gian sửa chữa replica và chính sách dọn tombstone là một phần của vận hành Cassandra, không chỉ là tối ưu dung lượng.

## 9. Tự kiểm tra kiến thức

**Bài 1.** Với cùng một cell, replica X có `'A'` ở timestamp `500`, replica Y có `'B'` ở timestamp `700`. X nhận mutation sau Y. Phiên bản nào thắng? **Đáp án:** `'B'`, vì `700 > 500`.

**Bài 2.** Cột `name` được ghi ở timestamp `900`; cột `email` được cập nhật ở timestamp `1000`. Lệnh cũ ghi lại `name` ở timestamp `800` có làm mất `email` không? **Đáp án:** Không. `name` giữ phiên bản timestamp `900`; `email` giữ phiên bản timestamp `1000`, vì chúng là hai cell riêng.

**Bài 3.** Một tombstone xóa `name` có timestamp `1200`, sau đó client retry ghi `name` với timestamp `1100`. Có thể làm sống lại tên không? **Đáp án:** Không; tombstone vẫn thắng. Cần mutation mới hợp lệ với timestamp cao hơn, và cần xem xét nghiệp vụ có thực sự cho phép khôi phục giá trị đã xóa hay không.

**Bài 4.** Dịch vụ A luôn cung cấp micro giây, dịch vụ B lại truyền mili giây vào `USING TIMESTAMP`. Hệ quả là gì? **Đáp án:** Timestamp của B nhỏ hơn khoảng 1.000 lần so với hiện tại, nên ghi của B thường thua các phiên bản được ghi với timestamp đúng. Cần chuẩn hóa đơn vị hoặc bỏ gán thủ công.

**Ghi nhớ:** Cassandra hòa giải phiên bản theo **mutation timestamp của từng cell**; timestamp cao hơn thắng, tombstone che các phiên bản cũ, và thứ tự đó có thể khác thứ tự thao tác thực tế. Thiết kế bảng theo truy vấn, quản lý clock skew, lựa chọn consistency level và cân nhắc LWT khi cần điều kiện cập nhật là các quyết định liên quan nhưng có vai trò khác nhau.
