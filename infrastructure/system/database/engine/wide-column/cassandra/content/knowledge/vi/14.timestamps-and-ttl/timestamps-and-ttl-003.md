# Timestamp do driver, client hoặc coordinator cung cấp trong Apache Cassandra

## 1. Vì sao cần biết ai gán mutation timestamp?

Trong **Apache Cassandra**, một cơ sở dữ liệu phân tán theo mô hình **wide-column**, cùng một partition có thể được ghi đến nhiều replica. Khi các replica nắm giữ những phiên bản khác nhau của cùng một cell, Cassandra dùng **mutation timestamp** (còn gọi là *write timestamp*) để hòa giải theo nguyên tắc **last-write-wins**: bản có timestamp lớn hơn thường thắng.

Vì vậy, người phát ra lệnh `UPDATE` sau theo thời gian thực **không chắc** ghi đè được một giá trị có timestamp lớn hơn. Muốn xử lý đúng xung đột, cần biết timestamp được gán ở đâu: trực tiếp trong câu CQL, qua mã ứng dụng/driver hay ở **coordinator** của cluster.

Ví dụ hai dịch vụ đều cập nhật `display_name` cho một khách hàng:

| Yêu cầu | Thời điểm người dùng thao tác | Write timestamp được gán (µs) | Giá trị |
|---|---|---:|---|
| Dịch vụ A | Trước | `1767225600123500` | `'An'` |
| Dịch vụ B | Sau | `1767225600123400` | `'Bình'` |

Nếu cùng ghi một cell và không có tombstone mới hơn, **`'An'` thắng** vì timestamp của A lớn hơn, dù thao tác của B xảy ra sau. Nguyên nhân có thể là B cố dùng timestamp cũ hoặc đồng hồ các máy lệch nhau. Consistency level cao hơn không sửa được thứ tự timestamp sai này.

> **Thuật ngữ:** `client` là chương trình gọi Cassandra; `driver` là thư viện phía client, ví dụ Apache/DataStax Java Driver; `coordinator` là node Cassandra tiếp nhận và điều phối một request đến các replica phù hợp. Driver cũng chạy ở phía client, nhưng tự sinh timestamp và ứng dụng tự gán timestamp là **hai chính sách khác nhau**.

## 2. Bốn nguồn timestamp và thứ tự ưu tiên

Với lệnh ghi CQL thông thường, có bốn khả năng gán mutation timestamp, theo **thứ tự ưu tiên từ cao xuống thấp**:

1. **Trong chính câu CQL:** `USING TIMESTAMP <epoch_microseconds>`.
2. **Ứng dụng đặt trên statement thông qua API của driver:** ví dụ `setQueryTimestamp(long)` trong Java Driver 4.x.
3. **Timestamp generator do driver cấu hình:** tự tạo giá trị cho request khi statement không có timestamp riêng.
4. **Coordinator tạo timestamp phía server:** khi request không mang timestamp do phía client cung cấp.

```text
                 Ứng dụng Java / client CQL
                            |
                            v
                 CQL có USING TIMESTAMP?
                    /             \
                  Có              Không
                   |                |
         Lấy timestamp từ CQL      v
                              Statement có
                            query timestamp?
                              /          \
                            Có          Không
                             |             |
                         Lấy từ API         v
                                    Driver timestamp
                                       generator
                                      /       \
                                  Có giá trị  Không gán
                                     |           |
                            Lấy từ generator     v
                                           Coordinator
                                         tự sinh timestamp
                                                |
                                                v
                                Ghi các mutation tới replica
```

Quy tắc này phù hợp với Java Driver 4.x và cơ chế **default timestamp** trong Cassandra native protocol: timestamp ghi trực tiếp trong CQL được ưu tiên hơn timestamp mặc định truyền kèm request.

| Nguồn | Ai quyết định? | Trường hợp sử dụng | Lưu ý |
|---|---|---|---|
| `USING TIMESTAMP` | Người viết câu CQL hoặc ứng dụng tạo CQL | Import dữ liệu, phát lại sự kiện, bài toán có timestamp nguồn rõ ràng | Đơn vị **micro giây**; cao nhất trong thứ tự ưu tiên |
| `setQueryTimestamp()` | Mã ứng dụng thông qua driver | Một số request cần timestamp nghiệp vụ riêng | Không cần sửa chuỗi CQL; giá trị là epoch **micro giây** |
| Driver timestamp generator | Cấu hình và thuật toán trong thư viện client | Luồng ghi bình thường cần chính sách nhất quán của mỗi client/session | Có thể tăng đơn điệu trong phạm vi driver, không bảo đảm toàn cluster |
| Coordinator | Node Cassandra xử lý request | Khi client không cung cấp timestamp | Phụ thuộc đồng hồ node coordinator; khác node có thể lệch thời gian |

**Điều cần tránh:** Một request không được gán một timestamp độc lập tại **từng replica** khi đang thực hiện một mutation bình thường. Timestamp được xác định trên đường xử lý request rồi đi cùng dữ liệu tới replica. Ngược lại, **hai request khác nhau** có thể do hai client hoặc hai coordinator khác nhau gán timestamp, dẫn đến xung đột.

## 3. CQL `USING TIMESTAMP`: điều khiển trực tiếp từ lệnh ghi

Tạo bảng thử nghiệm trong một **keyspace** riêng đã được chọn bằng `USE <keyspace>;`:

```sql
CREATE TABLE IF NOT EXISTS customer_profile_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    contact_email text
);
```

Viết một giá trị với timestamp xác định:

```sql
INSERT INTO customer_profile_by_id (customer_id, display_name, contact_email)
VALUES (
    33333333-3333-3333-3333-333333333333,
    'An',
    'an@example.com'
)
USING TIMESTAMP 1767225600123456;

SELECT display_name, writetime(display_name),
       contact_email, writetime(contact_email)
FROM customer_profile_by_id
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

Hai cell thông thường vừa được ghi mang timestamp `1767225600123456`. Hàm `writetime()` cho biết **write timestamp đang thắng** của cell, không phải thời gian truy vấn được thực hiện. Hàm này không dùng cho primary key hoặc counter.

Thử ghi lại `display_name` với timestamp **nhỏ hơn**:

```sql
UPDATE customer_profile_by_id
USING TIMESTAMP 1767225600123000
SET display_name = 'Bình'
WHERE customer_id = 33333333-3333-3333-3333-333333333333;

SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

Kết quả vẫn là `'An'` và `1767225600123456`. Lệnh vừa chạy không giành được phiên bản thắng vì timestamp cũ hơn. Đổi sang timestamp mới hơn:

```sql
UPDATE customer_profile_by_id
USING TIMESTAMP 1767225600124000
SET display_name = 'Bình'
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

Lúc này `display_name = 'Bình'` với timestamp `1767225600124000`; `contact_email` vẫn mang timestamp ban đầu. LWW áp dụng theo **cell**, không mặc định thay thế toàn bộ hàng.

CQL cũng hỗ trợ timestamp thủ công cho thao tác xóa thông thường:

```sql
DELETE display_name FROM customer_profile_by_id
USING TIMESTAMP 1767225600125000
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

Thao tác xóa tạo **tombstone** mang timestamp tương ứng. Một giá trị sống ghi sau nhưng có timestamp nhỏ hơn tombstone sẽ không xuất hiện trở lại. Khi thử các ví dụ, dùng khóa mới nếu đã chạy trước đó để tránh tombstone/timestamp còn sót.

**Cảnh báo về đơn vị:** `USING TIMESTAMP` cần số **micro giây kể từ Unix epoch**. Trong Java, `System.currentTimeMillis()` trả về **mili giây**, không được chuyển nguyên xi vào CQL. Hai loại timestamp này khác nhau khoảng một nghìn lần về giá trị số.

## 4. Client đặt timestamp trên statement qua Java Driver

Ứng dụng Java thường dùng `CqlSession` và prepared statement. Nếu nghiệp vụ có timestamp đã xác thực từ sự kiện, Java Driver 4.x cho phép đặt nó bằng `Statement.setQueryTimestamp(long)`, đưa timestamp vào **metadata của request** thay vì ghép `USING TIMESTAMP` vào chuỗi CQL.

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ProfileWriter {
    private final CqlSession session;
    private final PreparedStatement updateName;

    public ProfileWriter(CqlSession session) {
        this.session = session;
        this.updateName = session.prepare(
            "UPDATE customer_profile_by_id " +
            "SET display_name = ? WHERE customer_id = ?"
        );
    }

    public void rename(UUID id, String name, long epochMicros) {
        BoundStatement statement = updateName.bind(name, id)
            .setQueryTimestamp(epochMicros);
        session.execute(statement);
    }
}
```

Lệnh sử dụng có thể là:

```java
UUID customerId = UUID.fromString(
    "33333333-3333-3333-3333-333333333333"
);
writer.rename(customerId, "Chi", 1767225600126000L);
```

**Ý nghĩa:** driver gửi timestamp `1767225600126000` qua thuộc tính của native protocol. Vì câu CQL bên trong prepared statement không có `USING TIMESTAMP`, timestamp cấp statement là giá trị được áp dụng. Đây là cách hữu ích khi nhiều lần thực thi cùng một prepared statement nhưng mỗi sự kiện có timestamp riêng.

Trong Java Driver 4.x, các statement built-in là đối tượng bất biến theo mô hình trả **statement mới** khi gọi hàm `setQueryTimestamp()`. Cần dùng giá trị trả về như ví dụ, không chỉ gọi phương thức rồi thực thi biến statement cũ.

### Khi cả hai cách xuất hiện trên cùng request

Giả sử câu CQL chứa `USING TIMESTAMP 1767225600124000` nhưng mã Java gọi `setQueryTimestamp(1767225600126000L)`. Với cơ chế xử lý timestamp CQL/native protocol, **timestamp ghi trong `USING TIMESTAMP` được ưu tiên**, nên mutation mang timestamp `1767225600124000`.

Vì dễ gây hiểu lầm khi debug, hãy chọn **một vị trí chủ đạo** để đặt timestamp thủ công cho mỗi loại thao tác. Nếu một kết quả khác kỳ vọng, kiểm tra cả nội dung CQL và timestamp của statement.

## 5. Driver tự tạo timestamp: chính sách mặc định và tính tăng đơn điệu

Khi không có `USING TIMESTAMP` và mã ứng dụng không gọi `setQueryTimestamp()`, **timestamp generator** của driver có thể gán timestamp trước khi request được gửi đến Cassandra.

Ở **DataStax/Apache Cassandra Java Driver 4.x** theo cấu hình mặc định được mô tả trong tài liệu Java Driver 4.16, `AtomicTimestampGenerator` là lựa chọn mặc định, với các tính chất:

- Sinh timestamp phía **client** cho request; không cần node coordinator lấy giờ nếu giá trị được gửi kèm.
- Duy trì **timestamp tăng đơn điệu trong phạm vi các luồng dùng cùng generator/session**. Ngay cả hai lần phát rất gần nhau cũng có thể được tăng thêm một micro giây để tránh trùng.
- Tăng đơn điệu **không đồng nghĩa** đồng hồ vật lý chính xác tới micro giây. Trên nhiều hệ thống, nguồn đồng hồ thực có thể chỉ cho mức mili giây; phần micro giây là giá trị được bộ sinh tăng bổ sung.
- Nếu hệ thống sinh timestamp quá nhanh hoặc đồng hồ bị lùi, generator có thể phải tạo timestamp đi trước thời gian thực. Driver có cơ chế log cảnh báo **clock skew/drift** khi cấu hình ngưỡng tương ứng.

Ví dụ cấu hình HOCON minh họa:

```hocon
datastax-java-driver {
  advanced.timestamp-generator {
    class = AtomicTimestampGenerator
  }
}
```

Có hai lựa chọn đáng chú ý:

| Generator | Hành vi | Khi nào cân nhắc |
|---|---|---|
| `AtomicTimestampGenerator` | Duy trì giá trị tăng đơn điệu trên các luồng cùng generator | Ghi thông thường trong một JVM/session; mặc định thường dùng của Java Driver 4.x |
| `ThreadLocalTimestampGenerator` | Tăng đơn điệu **trong từng thread**, không bảo đảm giữa các thread | Trường hợp các luồng ghi độc lập và không cạnh tranh timestamp |
| `ServerSideTimestampGenerator` | Không gán timestamp phía client, để server quyết định | Khi muốn coordinator là nguồn timestamp cho request |
| Custom generator | Dùng chính sách do ứng dụng triển khai | Khi có nguồn thời gian/thứ tự riêng đã được quản lý |

Lưu ý **phạm vi**: một generator tăng đơn điệu trên một JVM không tạo ra thứ tự toàn cục giữa nhiều pod, nhiều JVM, nhiều vùng địa lý hoặc nhiều driver khác nhau. Khi các hệ thống cùng ghi một cell, timestamp từ các nguồn khác nhau vẫn có thể xung đột.

## 6. Coordinator gán timestamp khi client không gửi

Nếu client không đặt timestamp trong CQL, statement không có timestamp riêng **và driver không sinh timestamp**, request đến Cassandra cần timestamp mặc định. Khi đó **coordinator** sẽ gán timestamp cho mutation phía server.

Trong Java Driver 4.x, có thể yêu cầu chính sách này bằng generator tương ứng:

```hocon
datastax-java-driver {
  advanced.timestamp-generator {
    class = ServerSideTimestampGenerator
  }
}
```

Đường đi minh họa với replication factor `RF = 3`:

```text
Client A                          Cluster Cassandra
  |
  | UPDATE (không có timestamp client)
  +------------------------------> Coordinator X
                                    |
                                    | Gán timestamp tX
                             +------+-------+
                             |      |       |
                             v      v       v
                          Replica 1  2      3
                           ghi tX   ghi tX ghi tX
```

Node coordinator chọn timestamp cho request; các replica nhận mutation theo cơ chế của Cassandra. **Không phải ba replica tự lấy ba giá trị thời gian độc lập cho cùng mutation**. Tuy nhiên, request tiếp theo có thể được điều phối bởi **coordinator Y** với đồng hồ khác coordinator X, nên vẫn có nguy cơ timestamp không tăng theo thứ tự sự kiện thực.

Ví dụ:

- Request 1 đến coordinator X có đồng hồ nhanh 20 giây và gán `t1`.
- Request 2 đến coordinator Y sau 1 giây theo thời gian thực nhưng đồng hồ Y chính xác hơn, nên gán `t2 < t1`.
- Với cùng một cell, request 2 có thể không thay đổi giá trị nhìn thấy vì LWW giữ bản ghi với timestamp lớn hơn từ request 1.

Đồng bộ thời gian trên các node là bắt buộc về mặt vận hành. Dù timestamp được sinh từ phía client hay server, **NTP/chrony**, giám sát clock skew và chính sách timestamp nhất quán giúp giảm các lỗi khó tái hiện.

## 7. Ví dụ đối chiếu ba đường gán timestamp trong cùng một bảng

Với bảng `customer_profile_by_id` ở phần 3, ta có thể thử ba lệnh **trên ba UUID khác nhau** để quan sát timestamp được tạo bởi các nguồn khác nhau. Dùng khóa riêng sẽ không trộn lẫn xung đột timestamp giữa các bài thử.

**Trường hợp A — CQL quyết định:**

```sql
INSERT INTO customer_profile_by_id (customer_id, display_name)
VALUES (aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, 'CQL value')
USING TIMESTAMP 1767225600123456;

SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa;
```

`writetime(display_name)` trả về `1767225600123456` khi không có giá trị cạnh tranh trên cùng khóa.

**Trường hợp B — Java statement quyết định:**

```java
UUID id = UUID.fromString("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
BoundStatement statement = session.prepare(
        "INSERT INTO customer_profile_by_id " +
        "(customer_id, display_name) VALUES (?, ?)"
    )
    .bind(id, "Java statement value")
    .setQueryTimestamp(1767225600124567L);
session.execute(statement);
```

Kiểm tra:

```sql
SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb;
```

`writetime(display_name)` trả về `1767225600124567`.

**Trường hợp C — mặc định từ driver hoặc coordinator:**

```sql
INSERT INTO customer_profile_by_id (customer_id, display_name)
VALUES (cccccccc-cccc-cccc-cccc-cccccccccccc, 'Default value');

SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = cccccccc-cccc-cccc-cccc-cccccccccccc;
```

Timestamp đọc được gần thời điểm request được gửi/xử lý nếu đồng hồ hoạt động bình thường. **Chỉ nhìn `writetime()` không xác định được nó do driver hay coordinator tạo**; phải biết tool/driver gửi truy vấn và cấu hình timestamp generator. Ví dụ, `cqlsh` và ứng dụng Java có thể có chính sách timestamp khác nhau theo phiên bản/cấu hình.

## 8. Thiết kế ứng dụng: chọn nguồn timestamp theo tình huống

Không có nguồn timestamp duy nhất tốt nhất cho mọi nghiệp vụ. Hãy bắt đầu từ câu hỏi: **ý nghĩa của “ghi mới hơn” là gì**?

| Nhu cầu | Cách thường phù hợp | Lý do |
|---|---|---|
| Ghi CQL thông thường từ một Java service | Driver timestamp generator mặc định, đồng bộ đồng hồ | Có hành vi rõ ràng, tránh tự xử lý timestamp cho mọi lệnh |
| Import sự kiện lịch sử theo thứ tự nguồn đáng tin cậy | `USING TIMESTAMP` hoặc `setQueryTimestamp()` với timestamp được chuẩn hóa | Có thể giữ thứ tự ưu tiên theo thời điểm/số phiên bản từ nguồn nếu chính sách nghiệp vụ yêu cầu |
| Muốn server sở hữu việc gán timestamp | `ServerSideTimestampGenerator` hoặc client không cung cấp timestamp | Coordinator chịu trách nhiệm gán thời gian ghi |
| Nhiều dịch vụ tranh chấp một trạng thái quan trọng | Xem xét LWT (`IF ...`), event version, hoặc điều phối ghi | LWW dựa timestamp không bảo đảm đúng thứ tự nghiệp vụ toàn cục |
| Thường xuyên retry thao tác cập nhật | Thiết kế idempotency key và chính sách giữ timestamp cho cùng mutation | Tránh retry của sự kiện cũ vô tình mang timestamp mới và ghi đè dữ liệu khác |

Đừng dùng `USING TIMESTAMP` làm công cụ thay thế cho thiết kế bảng theo truy vấn hoặc điều kiện cập nhật. Nếu cần lấy sự kiện gần nhất theo thời gian nghiệp vụ, tạo **clustering key** phù hợp (ví dụ `event_time` hoặc epoch microseconds). Cassandra không hỗ trợ sắp xếp dữ liệu theo `writetime()` như một khóa truy vấn tổng quát.

### Ví dụ retry gây ghi đè ngoài ý muốn

1. Sự kiện `E1: status = QUEUED` được phát trước nhưng request bị timeout; ứng dụng chưa biết replica nào đã ghi.
2. Sự kiện `E2: status = COMPLETED` được xử lý thành công và mang timestamp `T2`.
3. Retry `E1` được phát lại với timestamp mới `T3 > T2`.
4. Cassandra có thể chọn `QUEUED`, làm trạng thái quay về quá khứ.

Nếu nghiệp vụ cần phát lại sự kiện theo thứ tự nguồn, có thể giữ timestamp/vị trí thứ tự cố định cho từng mutation (và quản lý va chạm timestamp giữa các nguồn). Nếu cần **compare-and-set** trên trạng thái, dùng chiến lược có điều kiện thay vì chỉ tin LWW.

## 9. Các giới hạn và tình huống đặc biệt

### 9.1. Lightweight transaction (LWT)

LWT như `INSERT ... IF NOT EXISTS` hoặc `UPDATE ... IF ...` được điều phối bằng cơ chế giao dịch có điều kiện. Cassandra **không cho phép `USING TIMESTAMP` do người dùng tùy chọn đối với conditional update**; câu lệnh như dưới đây bị từ chối:

```sql
-- Ví dụ cố tình không hợp lệ:
UPDATE customer_profile_by_id
USING TIMESTAMP 1767225600123456
SET display_name = 'Lan'
WHERE customer_id = 33333333-3333-3333-3333-333333333333
IF display_name = 'An';
```

Với Java Driver 4.x, timestamp phía client ở mức protocol/generator đối với LWT sẽ bị bỏ qua và server xử lý timestamp theo cơ chế của LWT. Khi cần cập nhật có điều kiện, hãy hiểu rõ trạng thái `[applied]` trong kết quả LWT và chi phí điều phối thay vì cố ép thứ tự bằng timestamp thủ công.

### 9.2. Counter

Counter có cơ chế cập nhật đặc thù; không áp dụng quy tắc ghi/đọc theo cell timestamp như cột thông thường. **Không dùng `USING TIMESTAMP` cho counter update**. Hãy chọn mô hình đếm phù hợp khi cần idempotency hay replay.

### 9.3. Batch và timestamp

Java Driver cho phép đặt query timestamp ở mức **`BatchStatement`**, khi đó timestamp áp dụng cho các child statement theo cơ chế của driver/protocol. Timestamp đặt bằng `setQueryTimestamp()` trên **từng child statement nằm trong batch** có thể bị **bỏ qua**; nếu cần timestamp riêng cho từng mutation trong batch, phải thiết kế lệnh và `USING TIMESTAMP` tương ứng đúng với quy tắc CQL. Không xem batch như một cách tự động bảo đảm thứ tự theo đồng hồ hay giao dịch phân tán tổng quát.

### 9.4. TTL, tombstone, compaction và repair

Mutation timestamp (µs) quyết định phiên bản cell nào thắng; **TTL** được khai báo bằng **giây** và quy định vòng đời dữ liệu. Cột CQL kiểu `timestamp` lại lưu thời gian nghiệp vụ ở mức **mili giây**. Ba đơn vị này không thể dùng thay thế nhau.

Khi `DELETE` hoặc TTL tạo dữ liệu bị xóa/hết hạn, tombstone giúp ngăn replica còn dữ liệu cũ làm sống lại phiên bản đã xóa. Các quy trình **repair** và **compaction** cần được vận hành với chính sách lưu tombstone phù hợp. Nếu có bản ghi mang timestamp rất xa trong tương lai, những mutation thông thường về sau có thể tiếp tục thua tombstone hoặc giá trị cũ.

## 10. Chẩn đoán lỗi từ nguồn timestamp

Khi người dùng báo “UPDATE thành công nhưng đọc vẫn ra giá trị cũ”, kiểm tra từng lớp:

| Bước | Câu hỏi | Cách xác minh |
|---|---|---|
| 1 | Có ghi đúng partition, row và cell không? | Đối chiếu keyspace, bảng, partition key và clustering key |
| 2 | Write timestamp hiện thắng là bao nhiêu? | `SELECT value, writetime(value) ... WHERE ...` trên cột thường đang tồn tại |
| 3 | Query có `USING TIMESTAMP` không? | Xem CQL thực tế, kể cả query chuẩn bị từ trước |
| 4 | Ứng dụng có đặt `setQueryTimestamp()` không? | Xem chỗ build statement và tham số epoch microseconds |
| 5 | Driver có timestamp generator gì? | Xem cấu hình `advanced.timestamp-generator` theo driver/session/profile |
| 6 | Server có phải là nguồn timestamp không? | Xác nhận driver không gửi default timestamp, rồi kiểm tra đồng hồ coordinator |
| 7 | Có lệch đồng hồ, retry hoặc tombstone không? | Kiểm tra clock-skew logs, event ID, policy retry, lịch sử DELETE/TTL |
| 8 | Có replica chưa đồng bộ? | Xem replication factor, consistency level, trạng thái replica và repair |

Hai lưu ý quan trọng:

- `writetime()` **không chỉ ra trực tiếp ai tạo timestamp**; nó chỉ phản ánh giá trị của cell đang tồn tại. Muốn truy nguồn cần kết hợp mã client, cấu hình driver và log.
- Đừng chẩn đoán bằng cách tăng `CL` rồi giả định đã sửa thứ tự ghi. `ONE`, `QUORUM` hay `ALL` điều chỉnh phạm vi replica cần xác nhận, **không thay luật ưu tiên timestamp**.

Một quy ước log có ích là ghi `eventId`, `partitionKey`, `mutationTimestampMicros` (nếu ứng dụng tự đặt), `timestampSource` (`cql`/`statement`/`driver`/`coordinator` nếu biết được), cấu hình driver và kết quả request. Không log dữ liệu cá nhân nhạy cảm không cần thiết.

## 11. Tự kiểm tra

**Câu 1.** Ứng dụng vừa đặt `setQueryTimestamp(5000)`, vừa gửi câu CQL có `USING TIMESTAMP 4000`. Với write bình thường, timestamp nào được ưu tiên?

**Đáp án:** `4000` từ CQL `USING TIMESTAMP`, vì ưu tiên cao hơn query timestamp ở mức statement.

**Câu 2.** Một Java Driver dùng `AtomicTimestampGenerator` sinh timestamp tăng đơn điệu trong cùng session. Có bảo đảm hai Java service ở hai máy phát sinh timestamp theo thứ tự tuyệt đối không?

**Đáp án:** Không. Mỗi máy/session có bộ sinh và đồng hồ riêng; tính tăng đơn điệu nội bộ không áp dụng trên toàn hệ thống.

**Câu 3.** Client không gắn `USING TIMESTAMP`, không đặt timestamp statement, nhưng vẫn đọc được `writetime(display_name)`. Ai đã tạo timestamp?

**Đáp án:** Có thể là **driver timestamp generator**, hoặc **coordinator** nếu generator không gán. Chỉ `writetime()` không đủ để xác định.

**Câu 4.** Server coordinator gán timestamp cho request với RF = 3. Ba replica có tự tạo ba timestamp khác nhau cho cùng mutation không?

**Đáp án:** Không. Timestamp đã được xác định cho mutation trên đường điều phối; replica tiếp nhận mutation tương ứng.

**Câu 5.** Vì sao lệnh `UPDATE ... USING TIMESTAMP ... IF condition` không phù hợp?

**Đáp án:** Đây là LWT; Cassandra không cho phép chỉ định timestamp CQL thủ công cho conditional update. Cần dùng cơ chế timestamp và điều phối của LWT.

**Câu 6.** Nếu client truyền `System.currentTimeMillis()` trực tiếp vào `USING TIMESTAMP`, lỗi chính là gì?

**Đáp án:** Giá trị ở đơn vị **mili giây**, trong khi mutation timestamp dùng **micro giây**. Cần chuyển đúng đơn vị hoặc để driver/coordinator gán.

## 12. Tài liệu tham khảo

- [Apache Cassandra Native Protocol — default timestamp và cách CQL ghi đè timestamp từ protocol](https://cassandra.apache.org/doc/latest/cassandra/reference/native-protocol.html)
- [DataStax Java Driver 4.16 — Query timestamps](https://docs.datastax.com/en/developer/java-driver/4.16/manual/core/query_timestamps/)
- [Java Driver 4.x — `Statement.setQueryTimestamp(long)`](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/Statement.html)

**Ghi nhớ:** Trong Cassandra, **`USING TIMESTAMP` > `setQueryTimestamp()` > driver timestamp generator > coordinator fallback** là thứ tự ưu tiên nguồn mutation timestamp cho ghi CQL thông thường. Dù nguồn nào gán, timestamp tính bằng **micro giây** và tham gia **last-write-wins** của từng cell. Chọn nguồn theo ngữ nghĩa nghiệp vụ, kiểm soát lệch đồng hồ giữa client và server, và dùng LWT khi cần cập nhật có điều kiện.
