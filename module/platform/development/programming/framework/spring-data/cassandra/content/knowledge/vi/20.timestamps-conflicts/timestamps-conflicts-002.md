# Phân biệt cột kiểu timestamp với timestamp của thao tác ghi

Trong **Apache Cassandra**, từ *timestamp* được dùng cho **hai khái niệm khác nhau**. Thứ nhất là **kiểu dữ liệu CQL `timestamp`**, dùng để lưu một thời điểm như `occurred_at` hoặc `updated_at`, và thường được Spring Data Cassandra ánh xạ với `java.time.Instant`. Thứ hai là **write timestamp** (*timestamp của mutation*) mà Cassandra gắn vào dữ liệu được ghi để hòa giải các phiên bản giữa các replica. Cùng tên gọi nhưng hai giá trị có **đơn vị, nguồn gốc và ý nghĩa hoàn toàn khác nhau**.

Bài học thuộc chương **Timestamp và xung đột** của module **SPRING_DATA_CASSANDRA**. Chúng ta sẽ phân biệt hai loại timestamp, thử `USING TIMESTAMP` và `WRITETIME()`, lý giải **last-write-wins**, thao tác ghi đến muộn, clock skew, tombstone, TTL, retry, LWT và cách kiểm chứng bằng `CqlSession`, Spring Data repository và `CassandraTemplate`. Trọng tâm vẫn là thiết kế dữ liệu theo truy vấn, primary key, tính nhất quán và kiểm soát hiệu năng trong hệ phân tán.

Sau bài học, bạn có thể giải thích tại sao một cập nhật có `updated_at` mới hơn vẫn có thể **thua** một cập nhật khác, và tại sao `WRITETIME(updated_at)` không phải là cùng giá trị với cột `updated_at`.

## 1. Hai khái niệm mang tên timestamp

| Thuộc tính | Cột có kiểu CQL `timestamp` | Write timestamp của mutation |
|---|---|---|
| Bản chất | **Giá trị dữ liệu** trong một cột | **Metadata dùng để hòa giải phiên bản** của cell/tombstone |
| Ví dụ | `occurred_at = '2026-11-25T09:00:00.123Z'` | `1795597200123000` |
| Đơn vị cơ bản | Mili giây kể từ Unix epoch | Micro giây kể từ Unix epoch |
| Java thường dùng | `Instant` / `java.util.Date` tùy mapping | `long` micro giây khi đặt trực tiếp |
| Xem bằng CQL | `SELECT occurred_at` | `SELECT WRITETIME(status)` |
| Điều khiển | Gán cột bằng `INSERT`/`UPDATE` | Chọn timestamp của mutation qua `USING TIMESTAMP`, driver hoặc mặc định |
| Ảnh hưởng last-write-wins | **Không tự quyết định** giá trị nào thắng | **Có**, khi các mutation cạnh tranh trên cùng cell |
| Ảnh hưởng `ORDER BY` | Có thể nếu cột là **clustering column** | Không phải cột để `ORDER BY` tùy ý |
| Có thể thay đổi riêng? | Có, nếu là cột thường | Có thể ghi lại với timestamp khác khi mutation được thực thi |

<u>Điều quan trọng nhất:</u> Cột `updated_at` không phải một “cột điều khiển xung đột” tự động. Nếu application viết `updated_at = Instant.now()`, nó chỉ thay **giá trị nghiệp vụ**. Cassandra vẫn sử dụng **write timestamp** của các cell để quyết định phiên bản nào được ưu tiên.

### 1.1. Ví dụ cùng một thời điểm nhưng hai cách biểu diễn

Đặt thời điểm:

~~~text
2026-11-25T09:00:00.123Z
~~~

Hai phép tính:

~~~text
CQL timestamp value:
  1,795,597,200,123 mili giây từ epoch

Write timestamp tương ứng nếu ta chủ động chọn cùng instant:
  1,795,597,200,123,000 micro giây từ epoch

1 mili giây = 1.000 micro giây
~~~

Con số trên chỉ là **ví dụ cùng mốc thời gian**, không có quy tắc rằng Cassandra tự lấy giá trị `occurred_at` để làm write timestamp. Hai giá trị có thể khác nhau hoàn toàn: sự kiện xảy ra hôm qua nhưng vừa được hệ thống ghi vào hôm nay.

## 2. Một bảng minh họa rõ hai loại thời gian

Giả sử ứng dụng quản lý trạng thái đơn hàng theo tenant và ID. Truy vấn chủ yếu là đọc hoặc sửa **một hàng đã biết toàn bộ khóa**:

~~~sql
CREATE TABLE order_state_by_id (
    tenant_id uuid,
    order_id uuid,
    occurred_at timestamp,
    updated_at timestamp,
    status text,
    note text,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Ở đây `(tenant_id, order_id)` là **composite partition key**, đồng thời là primary key đầy đủ. Các cột `occurred_at`, `updated_at`, `status`, `note` và `revision` đều là cột thường.

| Cột | Ý nghĩa nghiệp vụ | Có phải write timestamp? |
|---|---|---|
| `occurred_at` | Thời điểm sự kiện trong domain diễn ra | Không |
| `updated_at` | Thời điểm do ứng dụng xác định cho lần cập nhật | Không |
| `status` | Trạng thái đơn `NEW`, `PAID`, `SHIPPED` | Không |
| `revision` | Số phiên bản **nghiệp vụ** do ứng dụng quản lý | Không |
| Metadata của `status` | Write timestamp của cell `status` | **Có**, xem qua `WRITETIME(status)` |

Truy vấn point read:

~~~sql
SELECT tenant_id, order_id, occurred_at,
       updated_at, status, note, revision
FROM order_state_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

**Tại sao không dùng một bảng duy nhất cho mọi lịch sử đơn?** Bảng theo ID rất tốt cho point read nhưng không tự hỗ trợ “20 thay đổi trạng thái mới nhất của một khách”. Nếu cần lịch sử, phải thiết kế bảng sự kiện theo **partition key và clustering key** phù hợp (phần 12), không biến `WRITETIME` thành phương tiện tìm kiếm lịch sử.

## 3. Cột CQL timestamp: dữ liệu về thời điểm xảy ra

CQL `timestamp` biểu diễn một **instant trên trục thời gian** với độ chính xác **mili giây**. Nó không lưu tên múi giờ `Asia/Ho_Chi_Minh`, UTC offset ban đầu, tên vùng `ZoneId` hay độ chính xác nano giây từ `Instant`.

~~~sql
INSERT INTO order_state_by_id (
    tenant_id, order_id, occurred_at,
    updated_at, status, revision
) VALUES (
    87529939-5371-48e2-a1c4-268e8461260b,
    e15bcb3e-0b28-4d24-b005-b4d999d9c43e,
    '2026-11-24T08:00:00+00:00',
    '2026-11-25T09:00:00.123+00:00',
    'NEW',
    1
);
~~~

`occurred_at` mô tả khi sự kiện diễn ra; `updated_at` mô tả khi nghiệp vụ cho rằng trạng thái được thay đổi. **Cả hai chỉ là giá trị cột**. Nếu command này được ghi lại vào một thời điểm khác, write timestamp do driver/server cấp có thể khác mà nội dung hai cột vẫn giống hệt.

### 3.1. Spring Data Cassandra ánh xạ thành Instant

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;

@Column("occurred_at")
private Instant occurredAt;

@Column("updated_at")
private Instant updatedAt;
~~~

Với Java Driver 4, `Row.getInstant("occurred_at")` đọc được CQL `timestamp`. Khi giá trị Java có nano giây vượt quá mili giây, cần **định nghĩa chính sách chuẩn hóa hoặc từ chối ở biên**:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

static Instant requireMillis(Instant input) {
    if (input == null ||
            !input.equals(input.truncatedTo(ChronoUnit.MILLIS))) {
        throw new IllegalArgumentException(
                "Instant must have millisecond precision");
    }
    return input;
}
~~~

Ví dụ `2026-11-25T09:00:00.123456789Z` không round-trip nguyên vẹn nếu chỉ lưu trong một cột `timestamp`. Cũng không nên chuyển từ `LocalDateTime` sang `Instant` bằng múi giờ mặc định của máy chủ mà không công bố rõ zone, vì kết quả sẽ khác theo môi trường.

### 3.2. Cột timestamp có tự sắp theo write time không?

**Không.** Nếu `updated_at` là cột thường như trong `order_state_by_id`, câu CQL:

~~~sql
-- Không phải ORDER BY hợp lệ theo primary key của bảng này:
SELECT * FROM order_state_by_id ORDER BY updated_at DESC;
~~~

không trở thành hợp lệ chỉ vì kiểu cột là `timestamp`. Cassandra hỗ trợ thứ tự trong partition dựa trên **clustering columns** với quy tắc CQL tương ứng. Một cột kiểu `timestamp` có thể là clustering key nếu thiết kế bảng như vậy, nhưng **kiểu dữ liệu không tự quyết định vị trí khóa**.

## 4. Write timestamp: metadata để hòa giải phiên bản

Khi Cassandra lưu dữ liệu, mỗi mutation có **write timestamp** (giá trị micro giây từ epoch). Với các cột thông thường, các cell/tombstone mang timestamp để Cassandra so sánh các phiên bản của **cùng vị trí dữ liệu** trên replica và trong SSTable.

Trong một mutation gán nhiều cột, các cell được cập nhật có thể mang **cùng write timestamp**. Nhưng sau đó một lệnh `UPDATE` chỉ sửa `status` sẽ thay write timestamp của cell `status` mà **không nhất thiết đổi write timestamp của `occurred_at`, `updated_at` hoặc `note`**.

### 4.1. Xem bằng WRITETIME()

~~~sql
SELECT occurred_at, updated_at, status,
       WRITETIME(occurred_at) AS occurred_write_us,
       WRITETIME(updated_at)  AS updated_write_us,
       WRITETIME(status)      AS status_write_us
FROM order_state_by_id
WHERE tenant_id = 87529939-5371-48e2-a1c4-268e8461260b
  AND order_id = e15bcb3e-0b28-4d24-b005-b4d999d9c43e;
~~~

`WRITETIME(status)` trả về **`bigint` micro giây** của cell tương ứng, không trả một giá trị kiểu `timestamp`. Tên alias `status_write_us` được dùng để nhấn mạnh đơn vị.

`WRITETIME(updated_at)` cũng **khác** với `updated_at`:

~~~text
updated_at             = 2026-11-25T09:00:00.123Z
WRITETIME(updated_at)  = 1795597200123000 (nếu writer chủ động dùng
                                                   đúng microsecond đó)
~~~

Trong thực tế hai mốc **không cần trùng nhau**. Một backfill có thể đặt giá trị `updated_at` cách đây một tháng trong khi write timestamp thuộc ngày hiện tại. Một retry có thể đặt lại cùng giá trị `updated_at` nhưng dùng write timestamp mới nếu ứng dụng không kiểm soát nó.

**Giới hạn:** `WRITETIME` thường được dùng cho cell của cột dữ liệu thông thường. Không giả định có thể truy vấn `WRITETIME` tùy ý trên **primary key, counter hoặc từng phần tử của mọi kiểu collection**. Hãy kiểm tra khả năng CQL theo phiên bản; trong bài ta chỉ áp dụng cho cột scalar thường như `status`.

### 4.2. Dùng TTL() để phân biệt thời hạn, không phải thời điểm

~~~sql
SELECT status,
       WRITETIME(status) AS status_write_us,
       TTL(status)       AS status_ttl_s
FROM order_state_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

`TTL(status)` cho biết **số giây TTL còn lại** của dữ liệu còn tồn tại và có TTL theo ngữ nghĩa CQL; nó **không phải** thời gian cập nhật, và có thể là `null` khi không có TTL. Dữ liệu xóa/hết hạn và tombstones có cách xử lý khác; không dùng `TTL` như đồng hồ đánh thứ tự mutation.

## 5. Đặt write timestamp rõ ràng bằng USING TIMESTAMP

Cassandra cho phép client truyền timestamp của mutation trong CQL:

~~~sql
INSERT INTO order_state_by_id (
    tenant_id, order_id, occurred_at, updated_at,
    status, revision
) VALUES (
    87529939-5371-48e2-a1c4-268e8461260b,
    e15bcb3e-0b28-4d24-b005-b4d999d9c43e,
    '2026-11-24T08:00:00+00:00',
    '2026-11-25T09:00:00.123+00:00',
    'NEW',
    1
) USING TIMESTAMP 1795597200123000;
~~~

Lệnh này thể hiện **hai loại timestamp trong cùng statement**:

- `updated_at = '2026-11-25T09:00:00.123+00:00'`: **nội dung cột**, được lưu với độ chính xác mili giây.
- `USING TIMESTAMP 1795597200123000`: **write timestamp**, được dùng làm metadata micro giây cho mutation.

Với `UPDATE`, vị trí `USING TIMESTAMP` đứng trước `SET`:

~~~sql
UPDATE order_state_by_id
USING TIMESTAMP 1795597200123100
SET status = 'PAID'
WHERE tenant_id = 87529939-5371-48e2-a1c4-268e8461260b
  AND order_id = e15bcb3e-0b28-4d24-b005-b4d999d9c43e;
~~~

Với `DELETE`, vị trí nằm sau tên bảng:

~~~sql
DELETE status
FROM order_state_by_id
USING TIMESTAMP 1795597200123200
WHERE tenant_id = 87529939-5371-48e2-a1c4-268e8461260b
  AND order_id = e15bcb3e-0b28-4d24-b005-b4d999d9c43e;
~~~

**Cảnh báo:** các lệnh trên là các bước minh họa thứ tự; nếu chạy theo đúng thứ tự, lệnh cuối **xóa `status`**. Chỉ chạy trong keyspace test và không sao chép thao tác `DELETE` lên dữ liệu production.

### 5.1. Đơn vị là micro giây, không phải mili giây

Một lỗi nguy hiểm là lấy `Instant.toEpochMilli()` rồi truyền trực tiếp vào `USING TIMESTAMP`:

~~~java
// Sai về đơn vị nếu đặt trực tiếp làm write timestamp:
long milliseconds = Instant.parse(
        "2026-11-25T09:00:00.123Z").toEpochMilli();

// Đúng cho instant có độ chính xác đúng mili giây:
long microseconds = Math.multiplyExact(milliseconds, 1_000L);
~~~

Nếu truyền `1795597200123` (mili giây) thay vì `1795597200123000` (micro giây), Cassandra coi đó là timestamp **rất cũ**, dẫn đến cập nhật mới có thể bị phiên bản đã ghi trước đó áp đảo.

Với một `Instant` có độ chính xác micro giây, cách tính tổng quát:

~~~java
import java.time.Instant;

static long toEpochMicroseconds(Instant value) {
    return Math.addExact(
            Math.multiplyExact(value.getEpochSecond(), 1_000_000L),
            value.getNano() / 1_000L);
}
~~~

Cassandra write timestamp đo bằng micro giây. Nếu `Instant` có nano giây dư không chia hết cho 1.000 thì đoạn code này **bỏ phần nhỏ hơn micro giây**; khi nghiệp vụ yêu cầu không mất thông tin, phải kiểm tra `value.getNano() % 1_000 == 0` trước khi chuyển.

### 5.2. Không tự đặt timestamp tương lai tùy tiện

Một write timestamp quá xa trong tương lai có thể khiến các bản ghi với timestamp “bình thường” sau đó **không thể thắng** ở cùng cell cho đến khi ứng dụng sử dụng timestamp lớn hơn. Đó không phải cơ chế khóa nghiệp vụ, mà là lỗi khó phục hồi do đồng hồ hoặc việc nhập timestamp thủ công.

Hãy dùng explicit timestamp chỉ khi có lý do: ví dụ migration/replay có contract rõ ràng về thứ tự, cần giữ timestamp ổn định giữa retry hoặc điều phối một luồng mutation. Nếu không cần, ưu tiên chính sách timestamp của driver đã được quản lý và quan sát tốt.

## 6. Last-write-wins: giá trị nào thực sự thắng?

Cassandra thường hòa giải các phiên bản của một cell theo **write timestamp**: phiên bản có timestamp **lớn hơn** thường được ưu tiên. Đây là cơ chế thường gọi là **last-write-wins (LWW)**, nhưng từ “last” phải hiểu theo **timestamp metadata**, **không phải** “lệnh đến máy chủ sau cùng” và cũng không phải `updated_at` trong payload.

### 6.1. Hai writer: lệnh đến sau chưa chắc thắng

Giả sử một hàng có `status = 'NEW'`, hai writer phát cập nhật:

| Writer | Thứ tự mạng | Write timestamp (µs) | `status` | Kỳ vọng khi hòa giải |
|---|---:|---:|---|---|
| A | Đến trước | `1795597200123200` | `PAID` | **Thắng** |
| B | Đến sau | `1795597200123100` | `NEW` | Thua vì timestamp nhỏ hơn |

~~~sql
-- A được thực thi trước, write timestamp lớn hơn.
UPDATE order_state_by_id
USING TIMESTAMP 1795597200123200
SET status = 'PAID'
WHERE tenant_id = ? AND order_id = ?;

-- B đến muộn trên mạng nhưng write timestamp nhỏ hơn.
UPDATE order_state_by_id
USING TIMESTAMP 1795597200123100
SET status = 'NEW'
WHERE tenant_id = ? AND order_id = ?;
~~~

Sau khi mutation được hòa giải và replica phản hồi theo consistency phù hợp, giá trị `status` thắng là **`PAID`**. Không thể kết luận “cập nhật đến cuối cùng sẽ thắng”.

### 6.2. Nếu hai write timestamp bằng nhau?

Khi hai mutation cạnh tranh có **cùng write timestamp**, Cassandra dùng các quy tắc tie-break xác định để các replica hội tụ; tombstone có ý nghĩa ưu tiên so với giá trị live ở trường hợp timestamp bằng nhau. Với hai giá trị live có timestamp bằng nhau, việc so sánh nội dung có thể ảnh hưởng kết quả theo quy tắc hòa giải của Cassandra.

**Không thiết kế nghiệp vụ dựa trên thứ tự tie-break của hai payload live.** Việc dùng `long` micro giây **không bảo đảm** hai writer độc lập sẽ luôn tạo timestamp khác nhau: clock skew hoặc sinh timestamp không đúng quy tắc có thể dẫn đến hòa giải ngoài dự kiến.

### 6.3. Last-write-wins diễn ra theo cell, không phải toàn bộ object Java

Giả sử trạng thái ban đầu:

~~~text
status          = NEW       (writetime = 100)
updated_at      = 09:00Z    (writetime = 100)
note            = waiting   (writetime = 100)
~~~

Hai writer:

~~~text
Writer A: SET status = PAID, updated_at = 09:05Z
          using writetime = 300

Writer B: SET note = manual-review
          using writetime = 200
~~~

Sau hòa giải:

~~~text
status          = PAID           (writetime = 300)
updated_at      = 09:05Z         (writetime = 300)
note            = manual-review  (writetime = 200)
~~~

**Không có một “timestamp của cả entity” duy nhất** bảo đảm các cột luôn thuộc cùng phiên bản object Java. Cần kiểm soát thao tác ghi theo field, batch/transaction phù hợp, idempotency và điều kiện nghiệp vụ nếu muốn giữ một bất biến liên quan nhiều cột hoặc nhiều bảng.

## 7. Updated_at mới hơn vẫn có thể thua

Giả sử ứng dụng gửi hai cập nhật:

~~~text
Command X:
    updated_at (CQL value) = 2026-11-25T09:10:00Z
    status                = PAID
    write timestamp       = 1795597200123400

Command Y:
    updated_at (CQL value) = 2026-11-25T09:20:00Z
    status                = NEW
    write timestamp       = 1795597200123300
~~~

Y mang **giá trị `updated_at` mới hơn**, nhưng write timestamp **nhỏ hơn** X. Nếu cả hai command ghi `status` và `updated_at` vào **cùng các cell**, sau hòa giải các giá trị của **X** sẽ thắng: trạng thái `PAID` với `updated_at=09:10Z`.

Kết luận:

- Cassandra **không đọc `updated_at` rồi so sánh hai giá trị đó** trước khi ghi.
- `WRITETIME(updated_at)` phản ánh timestamp metadata của cell, không phải một dạng alias của `updated_at`.
- Dùng `updated_at` để kiểm soát tiến trình trạng thái cần **logic điều kiện riêng**, ví dụ LWT/version, thay vì chỉ thêm một field thời gian.

Một trường hợp còn nguy hiểm hơn là **chỉ sửa một cột**: command mới cập nhật `status` nhưng bỏ `updated_at`; lúc đó người đọc có thể thấy trạng thái mới đi với thời gian nghiệp vụ cũ. Đừng dựa vào một entity object để suy ra mọi field được cập nhật đồng bộ.

## 8. Write timestamp mặc định lấy từ đâu?

Khi câu CQL **không khai báo `USING TIMESTAMP`**, một timestamp được chọn theo cơ chế cấu hình và môi trường thực thi. Với **Java Driver 4**, cơ chế **timestamp generator** ở phía client có thể cung cấp microsecond timestamp mặc định cho request; nếu client không cung cấp timestamp, Cassandra có thể sử dụng timestamp do coordinator sinh.

Vì vậy, cần phân biệt:

| Tầng | Hành vi cần kiểm tra |
|---|---|
| Spring Data repository/`CassandraTemplate` | API entity CRUD; không tự lấy `updatedAt` làm write timestamp |
| Java Driver timestamp generator | Chính sách sinh timestamp mặc định; có thể dùng đồng hồ client |
| `USING TIMESTAMP` hoặc statement query timestamp | Timestamp của mutation được chỉ định rõ |
| Cassandra coordinator | Có thể cấp timestamp khi client không gửi |
| Application auditing | Có thể điền `@CreatedDate`, `@LastModifiedDate` vào cột dữ liệu; **không đồng nghĩa** điều khiển write timestamp |

Các phiên bản driver/Spring Data và cấu hình session có thể thay đổi nguồn timestamp hiệu lực. **Không suy đoán chắc chắn** rằng “Cassandra luôn lấy đồng hồ server” hoặc “luôn dùng đồng hồ client”. Hãy xem driver config và kiểm chứng `WRITETIME()` trên môi trường test.

### 8.1. Clock skew có thể tạo xung đột khó hiểu

~~~text
Node A / app A: đồng hồ chạy nhanh 20 giây
Node B / app B: đồng hồ đúng

App A gửi mutation có timestamp tương lai.
App B gửi mutation thật sự sau đó, nhưng timestamp nhỏ hơn.

=> Mutation của B có thể không thắng ở cùng cell.
~~~

Giảm rủi ro bằng đồng bộ đồng hồ (NTP), theo dõi drift, không cho client tùy ý truyền write timestamp từ nguồn không tin cậy, dùng generator phù hợp và đặt ràng buộc nghiệp vụ bằng LWT hoặc cơ chế điều phối riêng khi cần.

## 9. Điều khiển write timestamp qua Java Driver

Nếu cần explicit write timestamp, có thể dùng **prepared/bound statement** của Java Driver 4. Ví dụ:

~~~java
package example.orders;

import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class StatusWriter {
    private final CqlSession session;
    private final PreparedStatement update;

    public StatusWriter(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
                "UPDATE order_state_by_id SET status = ? " +
                "WHERE tenant_id = ? AND order_id = ?");
    }

    public void writeWithTimestamp(
            UUID tenantId, UUID orderId, String status,
            long writeTimestampMicros) {

        BoundStatement bound = update.bind(status, tenantId, orderId)
                .setQueryTimestamp(writeTimestampMicros);

        session.execute(bound);
    }
}
~~~

`setQueryTimestamp(long)` đặt **timestamp metadata** của request theo đơn vị micro giây. Nó **không** sửa cột CQL `updated_at`. Java Driver 4 dùng statement bất biến với các setter kiểu này: **giữ lại object trả về** từ `.setQueryTimestamp(...)`, không bỏ qua kết quả.

Cũng có thể viết CQL rõ ràng:

~~~java
PreparedStatement update = session.prepare(
        "UPDATE order_state_by_id USING TIMESTAMP ? " +
        "SET status = ? WHERE tenant_id = ? AND order_id = ?");

session.execute(update.bind(
        writeTimestampMicros, status, tenantId, orderId));
~~~

**Chọn một cách điều khiển timestamp cho statement**; không cần đặt cả `USING TIMESTAMP` và query timestamp trên cùng request. Dùng `USING TIMESTAMP ?` giúp biểu đạt rõ ý định ngay trong CQL; dùng `setQueryTimestamp` giúp đặt trên object statement.

`CqlSession` phải được quản lý vòng đời và dùng chung từ Spring container. `PreparedStatement` có thể được tái sử dụng thay vì prepare lại cho mọi request. Không nối các giá trị nhạy cảm vào chuỗi CQL; dùng bind markers `?`.

### 9.1. Qua CqlTemplate

`CqlTemplate`/`CqlOperations` có thể thực thi CQL với bind parameters:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlOperations;

public void changeStatus(
        CqlOperations cql, UUID tenantId, UUID orderId,
        String status, long writeTimestampMicros) {

    cql.execute(
            "UPDATE order_state_by_id USING TIMESTAMP ? " +
            "SET status = ? WHERE tenant_id = ? AND order_id = ?",
            writeTimestampMicros, status, tenantId, orderId);
}
~~~

Đây là một phương thức dành cho DAO/service; cách kiểm tra kết quả thành công, retry và quyền tenant được quyết định bởi nghiệp vụ. `CqlTemplate` sử dụng CQL trực tiếp; nó không đòi hỏi entity `@Table` để xác định lệnh trên.

### 9.2. Qua CassandraTemplate và repository

`CassandraTemplate`/`CassandraOperations` và `CassandraRepository` có thể đọc/ghi entity, nhưng **không nên mặc định** `repository.save(entity)` sẽ lấy `entity.getUpdatedAt()` làm write timestamp. Nếu cần bảo đảm write timestamp cụ thể, dùng API statement hoặc tùy chọn ghi được hỗ trợ bởi phiên bản Spring Data đang chạy, rồi **kiểm tra `WRITETIME()` trên dữ liệu thực**.

Điều quan trọng là tách:

~~~text
Entity.updatedAt (Instant, CQL timestamp)
                  ≠
Write timestamp của cell (long microseconds)
~~~

Tương tự, Spring Data auditing `@LastModifiedDate` có thể thiết lập **giá trị cột ngày sửa đổi** dựa trên callback/auditor, nhưng không tạo một cơ chế compare-and-set và không tự quy định write timestamp của Cassandra.

## 10. Entity Spring Data minh họa hai loại timestamp

Lớp khóa ghép:

~~~java
package example.orders;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class OrderStateKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    public OrderStateKey() {}
    public OrderStateKey(UUID tenantId, UUID orderId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID value) { orderId = value; }

    @Override
    public boolean equals(Object value) {
        if (this == value) return true;
        if (!(value instanceof OrderStateKey)) return false;
        OrderStateKey that = (OrderStateKey) value;
        return Objects.equals(tenantId, that.tenantId)
                && Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId);
    }
}
~~~

Entity:

~~~java
package example.orders;

import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_state_by_id")
public class OrderState {

    @PrimaryKey
    private OrderStateKey id;

    @Column("occurred_at")
    private Instant occurredAt;

    @Column("updated_at")
    private Instant updatedAt;

    @Column("status")
    private String status;

    @Column("note")
    private String note;

    @Column("revision")
    private Long revision;

    public OrderState() {}

    public OrderStateKey getId() { return id; }
    public void setId(OrderStateKey value) { id = value; }
    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant value) { occurredAt = value; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
    public String getNote() { return note; }
    public void setNote(String value) { note = value; }
    public Long getRevision() { return revision; }
    public void setRevision(Long value) { revision = value; }
}
~~~

Repository:

~~~java
package example.orders;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderStateRepository
        extends CassandraRepository<OrderState, OrderStateKey> {
}
~~~

Đọc theo đầy đủ key:

~~~java
OrderStateKey id = new OrderStateKey(tenantId, orderId);
Optional<OrderState> order = repository.findById(id);
~~~

Những ví dụ cần được đặt vào class/file riêng, có imports phù hợp và schema test tồn tại trước. **Không có field Java nào ở entity trên tương ứng trực tiếp với write timestamp metadata**; muốn đọc metadata hãy dùng `WRITETIME` qua CQL hoặc một projection/truy vấn phù hợp.

## 11. Query WRITETIME bằng Java Driver mà không nhầm với Instant

Để quan sát metadata của **cùng một cell**:

~~~java
import java.time.Instant;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public record OrderStateTiming(
        Instant businessUpdatedAt,
        Long statusWriteMicros,
        String status) {
}

public OrderStateTiming readTiming(
        CqlSession session, UUID tenantId, UUID orderId) {

    PreparedStatement ps = session.prepare(
            "SELECT updated_at, status, " +
            "WRITETIME(status) AS status_write_us " +
            "FROM order_state_by_id " +
            "WHERE tenant_id = ? AND order_id = ?");

    Row row = session.execute(ps.bind(tenantId, orderId)).one();
    if (row == null) {
        return null;
    }

    Long writeTime = row.isNull("status_write_us")
            ? null
            : row.getLong("status_write_us");

    return new OrderStateTiming(
            row.getInstant("updated_at"),
            writeTime,
            row.getString("status"));
}
~~~

Đây là **các khai báo cần tách vào file/class Java phù hợp**. `Long` được dùng cho `statusWriteMicros` vì metadata có thể vắng mặt (ví dụ cell chưa được ghi). Không ép `long` micro giây thành `Instant` bằng cách gọi `Instant.ofEpochMilli(statusWriteMicros)` vì sai đơn vị.

Nếu muốn chuyển write timestamp sang `Instant` để hiển thị hoặc debug:

~~~java
import java.time.Instant;

static Instant fromEpochMicros(long micros) {
    long seconds = Math.floorDiv(micros, 1_000_000L);
    long microPart = Math.floorMod(micros, 1_000_000L);
    return Instant.ofEpochSecond(seconds, microPart * 1_000L);
}
~~~

Ở API public, không nên lộ write timestamp như một `updatedAt` nghiệp vụ mà không giải thích rõ. Có thể chỉ trả giá trị `updatedAt` do ứng dụng xác định, còn `statusWriteMicros` để quan sát/debug nội bộ.

## 12. Timestamps trong khóa sắp xếp sự kiện

Một mô hình khác là lưu **một hàng trên mỗi sự kiện**, ví dụ lịch sử trạng thái theo đơn/ngày:

~~~sql
CREATE TABLE order_events_by_day (
    tenant_id uuid,
    order_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, order_id, event_day),
        occurred_at, event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Truy vấn:

~~~sql
SELECT occurred_at, event_id, event_type, payload
FROM order_events_by_day
WHERE tenant_id = ?
  AND order_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Ở đây `occurred_at` là **clustering column kiểu timestamp**. Nó điều khiển **thứ tự hàng trong partition**, **không phải write timestamp metadata**. Sự kiện được nhận đến muộn nhưng có `occurred_at` cũ vẫn nằm theo khóa thời gian sự kiện, nếu cùng hàng/khóa được ghi và không bị metadata khác che khuất.

Phân biệt:

| Khi người dùng hỏi… | Giá trị nên dùng |
|---|---|
| “Sự kiện diễn ra lúc nào?” | `occurred_at` (CQL timestamp) |
| “Lịch sử theo thứ tự thời gian xảy ra?” | Clustering `occurred_at` (cộng `event_id` phá hòa) |
| “Cell `event_type` được ghi với timestamp nào?” | `WRITETIME(event_type)` |
| “Trạng thái hiện tại đã qua mấy bước?” | Version/sequence nghiệp vụ, không suy từ `WRITETIME` |
| “Mọi event mới nhất trên toàn bộ tenant?” | Cần access pattern/bảng phù hợp, không chỉ `ORDER BY` |

**Không đặt `WRITETIME(occurred_at)` lên clustering key rồi xem nó là sort key.** Primary key có cách lưu trữ riêng và `WRITETIME` không phải công cụ truy vấn metadata của khóa. Nếu cần ordering theo thời gian ghi nhận hệ thống, hãy mô hình hóa một **cột/khóa nghiệp vụ riêng**, với policy tạo giá trị và xử lý clock skew.

## 13. Xóa, tombstone và timestamp

Khi `DELETE` hoặc khi TTL hết hạn, Cassandra dùng **tombstone** để biểu thị dữ liệu đã bị xóa/hết hiệu lực trong hệ phân tán. Tombstone cũng gắn với timestamp để ngăn một bản ghi cũ từ replica khác xuất hiện trở lại trong quá trình hòa giải.

Ví dụ:

~~~sql
-- Ghi trạng thái tại timestamp 1000.
UPDATE order_state_by_id USING TIMESTAMP 1000
SET status = 'NEW'
WHERE tenant_id = ? AND order_id = ?;

-- Xóa trạng thái tại timestamp 3000.
DELETE status FROM order_state_by_id USING TIMESTAMP 3000
WHERE tenant_id = ? AND order_id = ?;

-- Một ghi đến muộn với timestamp 2000 sẽ không làm status sống lại.
UPDATE order_state_by_id USING TIMESTAMP 2000
SET status = 'PAID'
WHERE tenant_id = ? AND order_id = ?;
~~~

Trong ví dụ, các timestamp `1000/2000/3000` là số **micro giây từ Unix epoch** chỉ nhằm minh họa thứ tự. **Không dùng những giá trị này trong ứng dụng thật** vì chúng thuộc thời điểm rất xa trong quá khứ; nên chạy test với timestamp epoch hiện hành hoặc giá trị test riêng được kiểm soát.

Điểm cần nhớ:

- Delete không xóa ngay toàn bộ byte vật lý trên mọi SSTable/replica.
- Tombstone có timestamp lớn hơn có thể chặn dữ liệu với write timestamp nhỏ hơn.
- Với **cùng timestamp**, delete/tombstone được ưu tiên hơn live cell theo quy tắc hòa giải Cassandra.
- Tombstone được dọn theo quy tắc compaction/`gc_grace_seconds` và sự an toàn của replica; sai cấu hình hoặc replica bỏ lỡ delete có thể gây **zombie data**.
- Xóa liên tục, TTL dày đặc và cập nhật không đúng mô hình có thể làm tăng tombstone scan và p99 latency.

**Quan trọng:** việc một cell không còn hiển thị không có nghĩa không còn dấu vết tombstone hoặc mọi replica đã đồng bộ tức thời.

### 13.1. TTL không phải là write timestamp

~~~sql
UPDATE order_state_by_id
USING TTL 3600
SET note = 'temporary'
WHERE tenant_id = ? AND order_id = ?;
~~~

TTL là **thời gian sống của dữ liệu**, thường tính bằng giây. `WRITETIME(note)` là metadata về timestamp của mutation; `TTL(note)` là thời gian sống còn lại nếu cell có TTL. Hai metadata phục vụ **hai câu hỏi khác nhau**.

Một ghi `note` không TTL sau đó có thể thay chính sách hết hạn của cell; các cột khác trong cùng hàng có thể có TTL riêng. Không mặc định xóa một cột là xóa cả entity, và không dùng TTL như một cơ chế compare-and-set.

## 14. Khi LWW không đủ: LWT và version nghiệp vụ

LWW là quy tắc hòa giải bản ghi, **không tự kiểm tra điều kiện nghiệp vụ** như “một đơn đã SHIPPED không được quay lại NEW”. Đặt timestamp tăng dần theo đồng hồ không giải quyết triệt để các trường hợp hai writer độc lập, request chậm, replay hoặc clock skew.

Nếu thao tác cần điều kiện “chỉ chuyển `NEW → PAID`”, có thể dùng **lightweight transaction (LWT)**:

~~~sql
UPDATE order_state_by_id
SET status = 'PAID', revision = 2
WHERE tenant_id = ? AND order_id = ?
IF status = 'NEW';
~~~

Khi thực thi qua driver, đọc `[applied]`:

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement ps = session.prepare(
        "UPDATE order_state_by_id " +
        "SET status = ?, revision = ? " +
        "WHERE tenant_id = ? AND order_id = ? " +
        "IF status = ?");

Row outcome = session.execute(
        ps.bind("PAID", 2L, tenantId, orderId, "NEW")).one();

if (outcome == null) {
    throw new IllegalStateException("Missing LWT result");
}
boolean applied = outcome.getBoolean("[applied]");
if (!applied) {
    // Trạng thái hiện tại không còn phù hợp; xử lý conflict của domain.
}
~~~

LWT đòi hỏi cơ chế consensus bổ sung, có chi phí cao hơn ghi thông thường. **Không trộn `USING TIMESTAMP` hoặc client-provided write timestamp với lệnh điều kiện LWT**: Cassandra không cho phép đặt timestamp tùy ý theo cách đó trên conditional statements. Nếu cần bảo toàn thời gian nghiệp vụ, lưu nó dưới dạng **cột `timestamp` riêng**, không coi nó là write timestamp của LWT.

### 14.1. Số revision không tự động là compare-and-set

Chỉ ghi:

~~~sql
UPDATE order_state_by_id
SET revision = 3
WHERE tenant_id = ? AND order_id = ?;
~~~

**không** khiến Cassandra từ chối writer đang giữ revision cũ. Để đặt ràng buộc phiên bản, cần dùng điều kiện tương ứng, ví dụ:

~~~sql
UPDATE order_state_by_id
SET status = 'SHIPPED', revision = 3
WHERE tenant_id = ? AND order_id = ?
IF revision = 2;
~~~

Hãy kiểm tra `[applied]` và xử lý conflict có chủ đích. Đừng hiểu `LOCAL_QUORUM` như một phiên bản của LWT: **consistency level** quyết định số replica xác nhận, còn **điều kiện IF/LWT** kiểm tra tiền điều kiện của mutation. Cả hai phải được cấu hình phù hợp với replication và SLA.

## 15. Retry, timestamp và idempotency

Sau timeout, client có thể không biết lệnh ghi đã được áp dụng hay chưa. Cần phân biệt:

| Cách retry | Rủi ro/ý nghĩa |
|---|---|
| Lặp lại cùng `SET status='PAID'` trên cùng khóa | Thường có thể thiết kế idempotent, nếu không phá invariant nghiệp vụ |
| Lặp lại bằng write timestamp **mới hơn** | Có thể ghi đè mutation khác diễn ra giữa hai lần thử |
| Lặp lại bằng **cùng write timestamp đã được chọn** | Giúp duy trì thứ tự hòa giải cho cùng command; cần tránh tie với payload khác |
| Lặp lại `UPDATE counter = counter + 1` | Không idempotent: có thể tăng nhiều lần |
| Append vào `list` | Có thể thêm trùng khi request được thực thi lại |
| Retry LWT sau timeout | Có thể nhận `[applied]=false` vì lần đầu đã thành công |
| Sinh `order_id` hoặc clustering timestamp mới mỗi lượt retry | Có thể tạo hàng nghiệp vụ trùng dưới khóa mới |

**Một cách tiếp cận có kiểm soát:** command được gắn `commandId`, primary key và payload ổn định; nếu cần timestamp explicit, chọn một lần rồi tái sử dụng sau retry. Đồng thời giới hạn số lượt retry, có backoff, không retry tự động các thao tác không idempotent và dùng LWT khi invariant cần compare-and-set.

Timestamp tự chọn **không thay thế idempotency key**; cùng timestamp trên hai payload khác nhau vẫn có thể dẫn tới tie-break không đúng ý định nghiệp vụ.

### 15.1. Không lấy timestamp phía client không tin cậy làm write timestamp

Giả sử mobile client gửi `updatedAt=2099-01-01` rồi backend dùng giá trị đó làm `USING TIMESTAMP`. Một sai lệch đồng hồ, bug hoặc payload độc hại có thể khiến cell trở thành “không thể cập nhật” bởi những write timestamp hiện tại. Cần:

- Xác thực nguồn và phạm vi giá trị thời gian.
- Tách `clientOccurredAt` (dữ liệu được báo cáo) khỏi write timestamp hệ thống.
- Đặt giới hạn cho clock skew và thời gian tương lai.
- Với thứ tự nghiệp vụ, dùng version/sequence hoặc LWT có kiểm soát.

## 16. Kiểm thử tích hợp: chứng minh hai loại timestamp khác nhau

Một bài test tốt không chỉ so sánh entity đã đọc với entity đã ghi. Nó cần **kiểm tra giá trị CQL** và **write timestamp metadata** độc lập. Sử dụng Cassandra instance dành riêng cho test, keyspace/table đã tạo, replication/consistency được kiểm soát và không chạy các câu `USING TIMESTAMP` trên production.

### 16.1. CQL kiểm thử có thể dự đoán

Trong một hàng test hoàn toàn mới, chọn write timestamp cố định ở thời điểm hiện hành:

~~~sql
-- Bước 1: ghi hai cột với timestamp 1795597200123000.
INSERT INTO order_state_by_id (
    tenant_id, order_id, occurred_at, status
) VALUES (
    87529939-5371-48e2-a1c4-268e8461260b,
    e15bcb3e-0b28-4d24-b005-b4d999d9c43e,
    '2026-11-24T08:00:00+00:00',
    'NEW'
) USING TIMESTAMP 1795597200123000;

-- Bước 2: cập nhật status với timestamp lớn hơn.
UPDATE order_state_by_id
USING TIMESTAMP 1795597200123200
SET status = 'PAID'
WHERE tenant_id = 87529939-5371-48e2-a1c4-268e8461260b
  AND order_id = e15bcb3e-0b28-4d24-b005-b4d999d9c43e;

-- Bước 3: cố ghi status cũ hơn, timestamp thấp hơn.
UPDATE order_state_by_id
USING TIMESTAMP 1795597200123100
SET status = 'NEW'
WHERE tenant_id = 87529939-5371-48e2-a1c4-268e8461260b
  AND order_id = e15bcb3e-0b28-4d24-b005-b4d999d9c43e;

-- Bước 4: xem cả value và metadata.
SELECT occurred_at, status,
       WRITETIME(occurred_at) AS occurred_write_us,
       WRITETIME(status) AS status_write_us
FROM order_state_by_id
WHERE tenant_id = 87529939-5371-48e2-a1c4-268e8461260b
  AND order_id = e15bcb3e-0b28-4d24-b005-b4d999d9c43e;
~~~

Kết quả kỳ vọng khi mutation đã hội tụ trên fixture test:

~~~text
occurred_at        = 2026-11-24T08:00:00Z    (giá trị nghiệp vụ)
status             = PAID                    (write timestamp thắng)
occurred_write_us  = 1795597200123000       (chỉ ghi ở bước 1)
status_write_us    = 1795597200123200       (ghi thành công ở bước 2)
~~~

Cả hai cột ban đầu được ghi trong cùng lệnh `INSERT`, nhưng **khác `WRITETIME` sau khi chỉ sửa `status`**. Điều này xác nhận write timestamp không phải metadata chung của toàn hàng.

### 16.2. Ví dụ JUnit + Java Driver

~~~java
package example.orders;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class WriteTimestampIntegrationTest {
    @Autowired CqlSession session;

    @Test
    void businessTimestampAndWriteTimestampAreIndependent() {
        UUID tenantId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        long baseUs = 1795597200123000L;
        Instant occurred = Instant.parse("2026-11-24T08:00:00Z");

        PreparedStatement insert = session.prepare(
                "INSERT INTO order_state_by_id " +
                "(tenant_id, order_id, occurred_at, status) " +
                "VALUES (?, ?, ?, ?) USING TIMESTAMP ?");

        session.execute(insert.bind(
                tenantId, orderId, occurred, "NEW", baseUs));

        PreparedStatement update = session.prepare(
                "UPDATE order_state_by_id USING TIMESTAMP ? " +
                "SET status = ? WHERE tenant_id = ? AND order_id = ?");

        session.execute(update.bind(
                baseUs + 200L, "PAID", tenantId, orderId));

        // Lệnh đến sau nhưng write timestamp nhỏ hơn phải thua.
        session.execute(update.bind(
                baseUs + 100L, "NEW", tenantId, orderId));

        PreparedStatement select = session.prepare(
                "SELECT occurred_at, status, " +
                "WRITETIME(occurred_at) AS occurred_us, " +
                "WRITETIME(status) AS status_us " +
                "FROM order_state_by_id " +
                "WHERE tenant_id = ? AND order_id = ?");

        Row row = session.execute(
                select.bind(tenantId, orderId)).one();

        assertNotNull(row);
        assertEquals(occurred, row.getInstant("occurred_at"));
        assertEquals("PAID", row.getString("status"));
        assertEquals(baseUs, row.getLong("occurred_us"));
        assertEquals(baseUs + 200L, row.getLong("status_us"));
    }
}
~~~

Trong integration test, cần đảm bảo keyspace `order_state_by_id` đã có và cấu hình consistency phù hợp. Với cluster nhiều replica, hãy chọn phương án ghi/đọc đảm bảo mức phản hồi mong muốn và tránh kết luận sai do replica chưa hội tụ tức thời. Ở phạm vi soạn bài STEP 4, **đây là code minh họa chưa được thực thi**; kiểm thử Gradle/CI và review chuyên môn sẽ thực hiện ở bước QA riêng.

### 16.3. Test nên bổ sung

| Tình huống | Kỳ vọng cần xác minh |
|---|---|
| CQL value `updated_at` mới, write timestamp cũ | Giá trị mới **không tự thắng** chỉ vì ngày trong payload mới |
| Cùng cell, write timestamp A lớn hơn B | A thắng sau hòa giải |
| Chỉ sửa `status` | `WRITETIME(occurred_at)` không đổi |
| Cùng write timestamp, hai payload live khác nhau | Không dựa vào thứ tự nhận như rule nghiệp vụ |
| Delete/tombstone timestamp lớn hơn | Ghi với timestamp cũ không làm cell hồi sinh |
| TTL của `note` | Phân biệt TTL seconds còn lại với `WRITETIME` micro giây |
| Retry với timestamp cố định | Cùng command không vô tình vượt qua mutation khác bằng timestamp mới |
| LWT `IF revision = n` | Kiểm tra `[applied]` và conflict |
| Driver timestamp generator/clock skew | Không suy ra timestamp nguồn theo clock mà chưa kiểm tra cấu hình |
| Đọc qua Spring Data entity | `Instant` round-trip ở mili giây; không nhầm với write timestamp |

## 17. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Gọi `updated_at` là write timestamp | Hiểu sai cơ chế LWW | Tách business field khỏi `WRITETIME` metadata |
| Truyền `Instant.toEpochMilli()` vào `USING TIMESTAMP` | Timestamp nhỏ hơn thực tế 1.000 lần | Chuyển đúng micro giây, kiểm tra overflow/precision |
| Ghi `updated_at` mới hơn rồi nghĩ sẽ thắng | Writer có metadata cũ vẫn có thể thua | Dùng LWT/version cho thứ tự nghiệp vụ |
| Tưởng `WRITETIME(status)` là timestamp của cả hàng | Các cột có metadata khác nhau | Kiểm tra từng cell có ý nghĩa |
| Lấy `WRITETIME` của primary key như cột thường | Query không theo khả năng CQL | Dùng cột thường/thiết kế read model phù hợp |
| Tự sinh write timestamp ở mobile client | Clock skew hoặc timestamp tương lai gây che dữ liệu | Dùng chính sách timestamp hệ thống tin cậy |
| Retry với timestamp mới và payload cũ | Có thể ghi đè cập nhật đã xảy ra | Giữ command ID/timestamp và đánh giá idempotency |
| Trộn client-supplied timestamp vào LWT | Không được hỗ trợ cho conditional mutation | Lưu business time trong cột, dùng `IF` |
| Dùng `LOCAL_QUORUM` rồi nghĩ không cần LWT | Vẫn có race nghiệp vụ | Dùng điều kiện rõ khi invariant đòi hỏi |
| Hiểu tombstone là xóa vật lý tức thời | Bỏ qua compaction, grace period và zombie risk | Giám sát TTL/delete, repair và lifecycle |
| Dùng cột `timestamp` thường cho `ORDER BY` | CQL không hỗ trợ nếu không là clustering | Thiết kế partition/clustering theo truy vấn |
| Lấy `WRITETIME` làm event log | Không có lịch sử đầy đủ mutation | Lưu event thành nhiều hàng có khóa ổn định |

## 18. Bài tập thực hành

Hệ thống logistics lưu trạng thái hiện tại của kiện hàng:

~~~sql
CREATE TABLE package_state_by_id (
    tenant_id uuid,
    package_id uuid,
    scanned_at timestamp,
    last_seen_at timestamp,
    state text,
    version bigint,
    PRIMARY KEY ((tenant_id, package_id))
);
~~~

Một thiết bị quét offline gửi sự kiện **đến muộn**. Hai mutation:

~~~text
Mutation A:
  scanned_at value   = 2026-11-25T09:00:00Z
  state              = AT_HUB
  write timestamp    = 1795597300000000

Mutation B:
  scanned_at value   = 2026-11-25T09:10:00Z
  state              = IN_TRANSIT
  write timestamp    = 1795597200000000
~~~

Giả sử cả hai cùng ghi các cột `scanned_at` và `state` vào đúng một primary key.

**Bài tập A — dự đoán hòa giải:** Sau khi cả hai được nhận và dữ liệu hội tụ, `state` và `scanned_at` có giá trị nào? `scanned_at` nào có giá trị ngày giờ lớn hơn, và write timestamp nào mới là giá trị lớn hơn?

**Bài tập B — sửa thiết kế:** Ứng dụng muốn bảo đảm state chỉ tiến `CREATED → AT_HUB → IN_TRANSIT → DELIVERED`. Viết CQL `UPDATE ... IF state = ?` hoặc `IF version = ?` và giải thích cách xử lý `[applied]=false`. Vì sao so sánh `last_seen_at` trên Java rồi `UPDATE` vô điều kiện không loại bỏ race?

**Bài tập C — kiểm chứng qua CQL:** Ghi hai mutation có `USING TIMESTAMP`, sau đó `SELECT scanned_at, state, WRITETIME(scanned_at), WRITETIME(state)` để đối chiếu. Chạy trên **test cluster** với key UUID riêng, không đụng production.

**Bài tập D — lịch sử quét:** Thiết kế `scans_by_package_day` có partition key `(tenant_id, package_id, scan_day)` và clustering `(scanned_at DESC, scan_id ASC)`. Giải thích vì sao clustering theo `scanned_at` là sắp theo thời gian sự kiện, không phải theo `WRITETIME`. Viết truy vấn 50 scan gần nhất và nêu cách tiếp tục bằng paging state.

### Câu hỏi tự kiểm tra

1. CQL `timestamp` và write timestamp khác nhau ở **đơn vị** nào?
2. `updated_at = '2026-11-25T09:00:00Z'` có tự trở thành write timestamp của cell không?
3. `WRITETIME(updated_at)` có bằng giá trị `updated_at` không?
4. Writer đến mạng sau nhưng có write timestamp nhỏ hơn có luôn thắng không?
5. `USING TIMESTAMP` cho phép một số mili giây từ `toEpochMilli()` được truyền trực tiếp không?
6. Khi hai writer sửa **hai cột khác nhau**, các cột có phải cùng metadata timestamp không?
7. Vì sao clock của client chạy nhanh có thể khiến update về sau không thắng?
8. Tombstone có write timestamp lớn hơn chặn một ghi đến muộn như thế nào?
9. `LOCAL_QUORUM` có tự biến câu `UPDATE` thành compare-and-set không?
10. Nếu cần thứ tự lịch sử sự kiện và paging, nên dựa vào `WRITETIME` hay clustering key của bảng sự kiện?

**Đáp án gợi ý:** (1) mili giây vs micro giây; (2) không; (3) không, đây là giá trị so với metadata; (4) không, LWW theo metadata; (5) không, phải đổi đơn vị; (6) không, metadata theo cell; (7) timestamp tương lai có thể áp đảo mutation mới; (8) mutation cũ không làm cell sống lại khi tombstone còn có hiệu lực; (9) không, cần LWT/IF; (10) clustering key được thiết kế theo nhu cầu.

## 19. Checklist trước khi triển khai

- [ ] Đã phân biệt rõ **CQL timestamp (milliseconds)** và **write timestamp (microseconds)**.
- [ ] `occurred_at`, `updated_at`, `scanned_at` được hiểu là **dữ liệu nghiệp vụ**, không phải metadata hòa giải.
- [ ] Đã xác định nguồn và độ tin cậy của write timestamp mặc định: driver generator hay coordinator.
- [ ] Nếu dùng `USING TIMESTAMP`/`setQueryTimestamp`, có kiểm tra đơn vị, precision, overflow và khoảng thời gian.
- [ ] Không cho client không đáng tin cậy điều khiển write timestamp tùy ý.
- [ ] Đã kiểm thử `WRITETIME` trên các **cột thường** và không đọc nhầm primary key.
- [ ] Hiểu LWW là theo cell/tombstone; không coi entity là một snapshot nguyên tử tự động.
- [ ] Không thiết kế nghiệp vụ dựa trên tie-break của hai giá trị live có cùng timestamp.
- [ ] Nếu trạng thái phải tiến có điều kiện, dùng `IF`/LWT hoặc cơ chế version đã được kiểm chứng.
- [ ] Phân biệt consistency level, serial consistency của LWT và business validation.
- [ ] Retry giữ primary key/command ID và xem xét giữ timestamp ổn định khi cần idempotency.
- [ ] Có kế hoạch xử lý tombstones, TTL, compaction, repair và nguy cơ zombie data.
- [ ] Không dùng `WRITETIME` thay cho lịch sử sự kiện hoặc sắp xếp toàn bảng.
- [ ] Bảng lịch sử có partition/clustering key phù hợp và giới hạn partition/page size.
- [ ] Integration test xác nhận cả **giá trị cột** lẫn **write timestamp metadata**.
- [ ] Theo dõi p95/p99 latency, retry, clock skew, hot partition, tombstones và xung đột LWT.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — Architecture: Dynamo](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — CQL Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html).
- [Apache Cassandra Java Driver 4 — Query Timestamps](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/query_timestamps/).
