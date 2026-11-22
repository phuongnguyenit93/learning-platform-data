# Sai lệch đồng hồ và cập nhật mang thời điểm quá xa trong tương lai

## 1. Bài toán trong Apache Cassandra

**Apache Cassandra** là cơ sở dữ liệu **wide-column phân tán**. Dữ liệu trong một partition được nhân bản lên nhiều replica theo **replication factor (RF)**; các request từ nhiều ứng dụng có thể đến khác node và khác thời điểm. Khi hai mutation cùng thay đổi một cell, Cassandra thường chọn phiên bản có **mutation timestamp lớn hơn** theo quy tắc **last-write-wins (LWW)**.

Vấn đề xuất hiện khi đồng hồ của máy tạo timestamp bị sai lệch: **một lần ghi có timestamp nằm quá xa trong tương lai có thể che khuất hàng loạt lần ghi hợp lệ về sau**. Cassandra không tự hiểu rằng người dùng vừa nhấn “Lưu” sau sự kiện trước đó. Nó chỉ so sánh giá trị timestamp trên mutation.

Ví dụ trong hệ thống hồ sơ khách hàng:

- Dịch vụ A có đồng hồ nhanh hơn thực tế **30 phút** và ghi `display_name = 'An'`.
- Một phút sau theo thời gian thực, dịch vụ B có đồng hồ đúng ghi `display_name = 'Bình'`.
- Nếu timestamp của A lớn hơn timestamp của B, Cassandra vẫn hiển thị **`'An'`**, kể cả khi yêu cầu B được replica xác nhận thành công.

Đây là lỗi **thứ tự phiên bản dữ liệu**, không đơn thuần là lỗi hiển thị đồng hồ hay lỗi query. Với những nghiệp vụ nhạy cảm như trạng thái xử lý đơn hàng, một cập nhật tương lai có thể khiến trạng thái nhìn thấy bị “kẹt” cho đến khi có mutation mang timestamp đủ lớn, hoặc được xử lý theo một quy trình khôi phục có kiểm soát.

## 2. Mutation timestamp và đồng hồ: điều Cassandra thực sự so sánh

**Mutation timestamp** là metadata của cell, biểu diễn thời gian dưới dạng số nguyên 64-bit có đơn vị **micro giây (µs) kể từ Unix epoch**. Nó có thể được cung cấp bởi:

1. **CQL `USING TIMESTAMP`** khi câu ghi chỉ định timestamp rõ ràng.
2. **Ứng dụng** qua API statement của driver, ví dụ `setQueryTimestamp(long)` trong Java Driver 4.x.
3. **Timestamp generator của driver** nếu driver được cấu hình tạo timestamp phía client.
4. **Coordinator** của Cassandra khi request không mang timestamp phía client.

Nguồn timestamp thực tế phụ thuộc CQL, client/driver và cấu hình đang sử dụng. Nếu timestamp đã được gán ở đường xử lý request thì nó đi cùng mutation tới replica; **không phải mỗi replica tự gán một đồng hồ riêng cho cùng mutation**.

Đừng nhầm mutation timestamp với:

| Khái niệm | Đơn vị thường dùng | Ý nghĩa |
|---|---|---|
| Mutation timestamp / `writetime(column)` | **Micro giây** | Phân xử phiên bản cell theo LWW |
| Cột CQL có kiểu `timestamp` | **Mili giây** | Lưu mốc thời gian nghiệp vụ, ví dụ `created_at` |
| CQL `USING TTL` / `ttl(column)` | **Giây** | Thời gian sống hoặc thời gian sống còn lại của cell |
| Thời điểm request đến coordinator | Tùy hệ thống log | Thông tin quan sát; không nhất thiết là mutation timestamp |

**Độ phân giải micro giây không bảo đảm đồng hồ chính xác tới micro giây.** Timestamp generator có thể tăng giá trị để tránh trùng trong cùng tiến trình, nhưng đồng hồ thật của máy vẫn có thể nhanh hoặc chậm so với thế giới bên ngoài.

## 3. Clock skew là gì và phát sinh ở đâu?

**Clock skew** là độ chênh giữa đồng hồ của các máy tại cùng một thời điểm thực. **Clock drift** thường nói đến việc đồng hồ chạy nhanh/chậm khiến độ lệch tích lũy dần. Cassandra đặc biệt nhạy cảm với sai lệch đồng hồ vì LWW so sánh các giá trị timestamp đến từ nhiều nguồn.

Ví dụ sơ đồ:

```text
    Thời gian thật                      10:00:00
           |
           +-- Client A (nhanh 30 phút) 10:30:00  -> ghi ts ~ 10:30
           |
           +-- Client B (đúng giờ)      10:00:00  -> ghi ts ~ 10:00
           |
           +-- Coordinator C (chậm 2s)  09:59:58  -> ghi ts ~ 09:59:58

    Cùng một cell: timestamp 10:30 thắng,
    bất kể request từ B hay C được gửi sau.
```

Những nguồn sai lệch phổ biến:

- **Đồng hồ host/VM/container:** máy ảo bị tạm dừng hoặc đồng bộ lại giờ, nguồn đồng hồ hypervisor không ổn định, cấu hình dịch vụ đồng bộ thời gian sai.
- **Client tạo timestamp:** các pod/JVM dùng đồng hồ của các host khác nhau; một host bị nhanh khiến mọi ghi phát ra từ nó có thể mang timestamp tương lai.
- **Coordinator tạo timestamp:** nếu driver không gửi timestamp, request đi qua các coordinator khác nhau có thể nhận giá trị không theo thứ tự thực do đồng hồ node khác nhau.
- **Ứng dụng tự gán timestamp:** nhập epoch mili giây thành micro giây, nhân đơn vị sai, dùng thời gian sự kiện tương lai hoặc đồng hồ ngoại vi không tin cậy.
- **Retry và phát lại sự kiện:** một lần retry được cấp timestamp mới có thể làm sự kiện cũ thắng sự kiện mới hơn; ngược lại, phát lại cùng timestamp cũ có thể không thay đổi dữ liệu.

**Múi giờ không phải clock skew.** `2027-01-01T08:00:00+07:00` và `2027-01-01T01:00:00Z` là **cùng một thời điểm**. Khác cách hiển thị không có nghĩa đồng hồ sai. Cần chuẩn hóa theo **UTC/epoch** khi so sánh và ghi log, không chỉ nhìn giờ địa phương.

## 4. Timeline: một future timestamp làm che ghi hợp lệ

Giả sử lúc các máy bắt đầu xử lý một bản ghi, timestamp thực xấp xỉ `T0 = 2000000000000000 µs`. Máy A có đồng hồ nhanh hơn **30 phút**; máy B đúng giờ và ghi sau A **1 phút**.

| Mutation cùng cell | Timestamp (µs) | Chênh so với `T0` | Giá trị |
|---|---:|---:|---|
| Ghi ban đầu | `2000000000000000` | `0` | `queued` |
| Máy A bị nhanh 30 phút | `2000001800000000` | `+1.800.000.000 µs` = `+30 phút` | `approved` |
| Máy B ghi 1 phút sau thời gian thực | `2000000060000000` | `+60.000.000 µs` = `+1 phút` | `cancelled` |

```text
Thời gian thực:
  T0                      T0 + 1 phút
  |-----------------------------|
  A ghi approved                B ghi cancelled
  timestamp = T0 + 30 phút      timestamp = T0 + 1 phút
       |                              |
       +-------- timestamp lớn ------+
                        |
             approved vẫn thắng

Phải có phiên bản hợp lệ với timestamp > T0 + 30 phút
thì cell mới có thể hiển thị giá trị khác.
```

**Điểm cần hiểu:** Cập nhật của B có thể được coordinator và replica chấp nhận ở mức consistency được yêu cầu, nhưng **không trở thành phiên bản thắng** của cell. “Ghi thành công” chỉ phản ánh việc yêu cầu hoàn thành theo giao thức/mức nhất quán, **không bảo đảm giá trị ghi sẽ hiển thị nếu có timestamp xung đột lớn hơn**.

Khoảng thời gian bị che không phải một “khóa” vật lý tồn tại chính xác 30 phút. Nếu các timestamp tiếp theo vẫn thấp hơn `T_future`, chúng thua. Ngay cả sau 30 phút, một mutation mới chỉ thắng khi **timestamp của mutation đó thực sự lớn hơn** giá trị đang thắng, với quy tắc xử lý trường hợp timestamp bằng nhau của Cassandra.

## 5. Thực hành CQL: tái hiện lỗi trên partition thử nghiệm

Chỉ chạy ví dụ trong **keyspace thử nghiệm** được tạo/chọn sẵn. Dùng UUID chưa từng ghi; các timestamp cố định dưới đây nhằm tái hiện lỗi, **không dùng cho dữ liệu sản xuất**.

### 5.1. Tạo bảng và giá trị ban đầu

```sql
CREATE TABLE IF NOT EXISTS profile_state_demo (
    profile_id uuid PRIMARY KEY,
    status text,
    note text,
    ttl_probe text
);

INSERT INTO profile_state_demo (profile_id, status, note)
VALUES (
    44444444-4444-4444-4444-444444444444,
    'queued',
    'created'
)
USING TIMESTAMP 2000000000000000;

SELECT status, writetime(status), note, writetime(note)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

Kết quả mong đợi: `status = 'queued'`; cả hai cell `status` và `note` có write timestamp `2000000000000000`.

### 5.2. Giả lập đồng hồ phía client chạy nhanh

```sql
UPDATE profile_state_demo
USING TIMESTAMP 2000001800000000
SET status = 'approved'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT status, writetime(status)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

Cell `status` giờ có `approved` cùng timestamp `2000001800000000`: **30 phút vượt quá `T0`** trong kịch bản.

### 5.3. Ghi sau theo thời gian thực nhưng timestamp thấp hơn

```sql
UPDATE profile_state_demo
USING TIMESTAMP 2000000060000000
SET status = 'cancelled'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT status, writetime(status), note, writetime(note)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

Kết quả vẫn là `status = 'approved'`, timestamp `2000001800000000`; trong khi `note = 'created'` giữ timestamp cũ. Điều này minh họa **LWW ở mức cell**, không ghi đè nguyên cả hàng.

### 5.4. Kiểm tra một mutation có timestamp lớn hơn

```sql
-- Chỉ minh họa kết quả LWW trong môi trường thử nghiệm.
UPDATE profile_state_demo
USING TIMESTAMP 2000001800000001
SET status = 'cancelled'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT status, writetime(status)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

Giờ `cancelled` thắng vì timestamp **cao hơn đúng 1 µs**. **Không áp dụng máy móc mẹo “cứ tăng timestamp để sửa” trên production**: ghi đè bằng timestamp tương lai còn lớn hơn có thể làm những cập nhật bình thường tiếp tục thua lâu hơn.

### 5.5. Tombstone cũng có thể ở tương lai

```sql
-- Trên một UUID thử nghiệm khác để tránh xung đột với các bước trước.
INSERT INTO profile_state_demo (profile_id, status)
VALUES (
    55555555-5555-5555-5555-555555555555,
    'open'
)
USING TIMESTAMP 2000000000000000;

DELETE status FROM profile_state_demo
USING TIMESTAMP 2000001800000000
WHERE profile_id = 55555555-5555-5555-5555-555555555555;

UPDATE profile_state_demo
USING TIMESTAMP 2000000060000000
SET status = 'reopened'
WHERE profile_id = 55555555-5555-5555-5555-555555555555;

SELECT status
FROM profile_state_demo
WHERE profile_id = 55555555-5555-5555-5555-555555555555;
```

`status` vẫn không có giá trị hiển thị, vì **tombstone** có timestamp lớn hơn bản ghi `reopened`. Khi timestamp bằng nhau, tombstone được ưu tiên trước giá trị sống. `writetime(status)` không phải công cụ xem trực tiếp timestamp của tombstone đã xóa.

## 6. Tăng consistency level có sửa được đồng hồ lệch không?

**Không.** Trong Cassandra, ba cơ chế giải quyết ba khía cạnh khác nhau:

| Cơ chế | Câu hỏi nó giải quyết | Điều nó không giải quyết |
|---|---|---|
| `RF` (replication factor) | Có bao nhiêu replica lưu partition? | Không định nghĩa timestamp nào đúng theo nghiệp vụ |
| Consistency level như `ONE`, `QUORUM`, `ALL` | Cần số lượng replica/ack phù hợp để hoàn tất request? | Không sửa timestamp lớn bất thường, không bảo đảm “request đến sau thắng” |
| Last-write-wins | Cell nào thắng khi nhiều phiên bản xung đột? | Không biết đồng hồ gốc có đúng, không biết thứ tự người dùng bấm nút |
| Repair | Replica được đối chiếu và đồng bộ ra sao? | Không tự đoán giá trị “đúng về nghiệp vụ” nếu timestamp đã sai |

Giả sử `RF = 3` và cả ba replica đã ghi `approved@T_future`. Dù request `cancelled@T_normal` sau đó được gửi với `CL = ALL`, timestamp thấp hơn vẫn thua. **Repair có thể làm các replica cùng thống nhất về phiên bản có timestamp lớn nhất**, nhưng không biến bản ghi đúng về mặt nghiệp vụ thành bản ghi thắng.

Với `CL = ONE`, còn có thể gặp trạng thái replica chưa đồng bộ. Khi chẩn đoán phải phân biệt **đọc dữ liệu cũ vì replica** với **bản mới bị LWW che vì timestamp**. Một lần đọc ở mức phù hợp, kết hợp `writetime()` và lịch sử mutation, giúp làm rõ nguyên nhân; nhưng chỉ tăng CL không phải biện pháp khắc phục gốc.

## 7. Driver, coordinator và lựa chọn nguồn timestamp

Trong ứng dụng Java kết nối Cassandra bằng **Java Driver 4.x**, một request có thể được gán timestamp từ driver trước khi gửi đi. Ví dụ, `AtomicTimestampGenerator` duy trì timestamp tăng đơn điệu trong phạm vi generator ngay cả khi nhiều request phát rất nhanh. Tuy nhiên:

- **Tăng đơn điệu trong một tiến trình** không bảo đảm thứ tự trên **nhiều JVM/pod/máy**.
- Một máy client có đồng hồ nhanh 30 phút có thể tiếp tục cấp timestamp nhanh 30 phút cho nhiều mutation.
- Nếu để **coordinator** gán timestamp phía server, vấn đề clock skew chuyển sang đồng hồ của các node Cassandra có thể nhận vai trò coordinator.
- Khi có `USING TIMESTAMP` hoặc statement timestamp do ứng dụng đặt, cấu hình clock đồng bộ của driver có thể **không giúp gì** nếu chính ứng dụng đang cung cấp một giá trị tương lai.

Ví dụ Java Driver 4.x ghi theo chính sách timestamp mặc định:

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ProfileStateRepository {
    private final CqlSession session;
    private final PreparedStatement updateStatus;

    public ProfileStateRepository(CqlSession session) {
        this.session = session;
        this.updateStatus = session.prepare(
            "UPDATE profile_state_demo " +
            "SET status = ? WHERE profile_id = ?"
        );
    }

    public void updateStatus(UUID id, String status) {
        // Không gán USING TIMESTAMP hay setQueryTimestamp().
        // Driver/coordinator chọn timestamp theo cấu hình hoạt động.
        session.execute(updateStatus.bind(status, id));
    }
}
```

Khi **cố tình** đồng bộ thứ tự với nguồn sự kiện đã đáng tin cậy, ứng dụng có thể chọn timestamp thủ công:

```java
import java.time.Instant;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public void updateWithEventTime(UUID id, String status, Instant eventTime) {
    long micros = Math.addExact(
        Math.multiplyExact(eventTime.getEpochSecond(), 1_000_000L),
        eventTime.getNano() / 1_000L
    );

    BoundStatement statement = updateStatus.bind(status, id)
        .setQueryTimestamp(micros);

    session.execute(statement);
}
```

Đoạn thứ hai chỉ nên dùng nếu **thứ tự theo event time** chính là chính sách nghiệp vụ mong muốn và event time đủ tin cậy. Không dùng trực tiếp `System.currentTimeMillis()` cho `setQueryTimestamp()` vì API cần **micro giây**, còn hàm trên trả **mili giây**. `Instant` có độ phân giải nano giây; phép chuyển trong ví dụ lấy epoch microseconds và bỏ phần nhỏ hơn 1 µs.

## 8. Tác động với TTL, tombstone, compaction và repair

Sai lệch đồng hồ gây lỗi khó hơn khi dữ liệu có **TTL** hoặc bị xóa:

- **Mutation timestamp** quyết định bản ghi sống/tombstone nào thắng khi đối chiếu phiên bản.
- **TTL**, khai báo trong CQL bằng **giây** (ví dụ `USING TTL 3600`), điều khiển thời hạn sống của dữ liệu theo cơ chế thời gian hết hạn riêng. **Không suy ra** một timestamp ghi nhanh 30 phút sẽ tự động kéo dài TTL thêm đúng 30 phút; đây là hai yếu tố khác nhau.
- **Tombstone** có write timestamp cao trong tương lai có thể che dữ liệu sống được ghi sau bằng timestamp bình thường.
- **Compaction** và chính sách thu gom tombstone cần phối hợp với **repair** và tình trạng replica. Thu gom tombstone khi còn replica mang phiên bản cũ có thể dẫn tới hiện tượng dữ liệu đã xóa xuất hiện trở lại (*zombie data*).

Ví dụ về TTL, ở bảng thử nghiệm:

```sql
UPDATE profile_state_demo
USING TTL 3600
SET ttl_probe = 'temporary'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT ttl_probe, writetime(ttl_probe), ttl(ttl_probe)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

`writetime(ttl_probe)` biểu diễn **micro giây** của mutation; `ttl(ttl_probe)` biểu diễn **số giây còn lại**. Cột `ttl_probe` chưa được ghi trong các bước trước, nên lần cập nhật này không phải cạnh tranh với một giá trị có timestamp lớn. Đây là cell khác `status`: timestamp tương lai của `status` **không tự động thay đổi TTL trên `ttl_probe`**.

Trong vận hành thật, không tùy tiện giảm `gc_grace_seconds`, bỏ repair hoặc xóa file SSTable chỉ để “loại bỏ” một future timestamp. Những thao tác đó có thể thay đổi khả năng chống zombie và tính an toàn của dữ liệu; cần kế hoạch phục hồi riêng khi xác định đúng nguyên nhân.

## 9. Cách nhận biết lỗi trên hệ thống đang hoạt động

Dấu hiệu thường gặp: ứng dụng ghi `UPDATE` thành công, nhưng `SELECT` vẫn trả trạng thái cũ. Đặc biệt đáng ngờ nếu `writetime()` lớn hơn đáng kể so với **epoch microseconds** tương ứng với giờ UTC hiện tại.

### 9.1. Đọc dữ liệu và timestamp của cell

```sql
SELECT profile_id, status, writetime(status)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

So sánh số trả về với timestamp UTC từ **nguồn thời gian đáng tin cậy**. Ví dụ:

```text
Giờ UTC thực:        T0
writetime(status):   T0 + 30 phút
Độ lệch quan sát:    +1.800.000.000 µs
```

Lưu ý `writetime()` chỉ cho biết timestamp của **cell đang hiển thị**. Nó không chỉ ra **ai** đã tạo timestamp. Với cell đã bị xóa hoặc TTL đã hết, cần công cụ/chẩn đoán tombstone phù hợp thay vì kỳ vọng `writetime()` luôn hiện số.

### 9.2. Lần ngược nguồn gán timestamp

| Câu hỏi | Dữ liệu cần đối chiếu |
|---|---|
| Query có `USING TIMESTAMP` không? | CQL cuối cùng gửi đi, phần code dựng prepared/batch statement |
| Mã Java có `setQueryTimestamp()` không? | Tham số, đơn vị, nơi chuyển từ `Instant` hoặc event time |
| Driver có tạo timestamp phía client? | Cấu hình timestamp generator và phiên bản driver |
| Có để coordinator tạo timestamp? | Cấu hình request, coordinator được chọn, trạng thái đồng hồ Cassandra node |
| Có request từ nhiều region/host? | Tên service, host/pod, clock offset, thời gian retry |
| Có xóa/TTL không? | Lịch sử `DELETE`, TTL, thời điểm tombstone và chính sách repair |
| Có sự kiện cũ được replay? | Event ID, thứ tự nguồn, retry ID, deduplication |

Chú ý sự khác nhau giữa **micro giây và mili giây**: epoch milliseconds thường có khoảng 13 chữ số ở thời đại hiện nay, còn epoch microseconds khoảng 16 chữ số. Đây chỉ là dấu hiệu nhanh, **không phải phép kiểm tra độ đúng tuyệt đối**. Dữ liệu nhập nhầm đơn vị có thể trông giống timestamp rất xa trong quá khứ; dữ liệu đã nhân sai hoặc nguồn thời gian tương lai có thể trông như timestamp ở rất xa phía trước.

### 9.3. Đồng hồ các node và ứng dụng

Trên máy Linux, người vận hành thường kiểm tra đồng bộ thời gian qua `timedatectl`, `chronyc tracking` hoặc công cụ tương đương theo hạ tầng; đồng thời so sánh với nguồn UTC/NTP chuẩn. Cần đo ở **cả máy Cassandra** và **máy chạy service/driver**, bởi một bên có thể tạo timestamp mà bên còn lại chỉ nhận.

Nên quan sát các tín hiệu:

- Clock offset/độ lệch thời gian giữa host và nguồn chuẩn, xu hướng drift, các lần đồng hồ bị nhảy về trước/sau.
- Cảnh báo clock drift/timestamp generator của driver, nếu driver và cấu hình cung cấp.
- Sự gia tăng của trường hợp `writetime(cell) > nowMicros + ngưỡng` cho các bản ghi sống được chọn mẫu an toàn.
- Ghi timeout/retry bất thường, nhiều tác nhân cùng ghi một partition hoặc cùng một cell.
- Tình trạng replica, consistency level, repair lag và các đợt compaction liên quan.

**Mốc ngưỡng** phải do hệ thống quyết định theo SLA và kiểu ghi. Ví dụ nguồn sự kiện lịch sử có thể chủ động dùng timestamp quá khứ; log backfill hợp lệ không nên bị coi là clock skew chỉ vì khác giờ xử lý.

## 10. Phòng ngừa: đồng bộ thời gian và giới hạn nguồn ghi

Một chiến lược tốt là **giảm khả năng timestamp sai xuất hiện ngay từ nguồn**:

1. **Đồng bộ giờ mọi host.** Sử dụng NTP/chrony hoặc dịch vụ thời gian tương đương; kiểm tra trạng thái đồng bộ sau reboot, suspend/resume và thay đổi hạ tầng.
2. **Giám sát offset cùng cảnh báo drift.** Cần đo cả cluster Cassandra lẫn client tạo timestamp. Không chỉ nhìn đồng hồ của một node bất kỳ.
3. **Chuẩn hóa timestamp tại API.** Tên biến/field phải thể hiện đơn vị: `epochMicros`, `epochMillis` hoặc dùng chuỗi ISO-8601 có offset rõ ràng.
4. **Hạn chế gán timestamp thủ công.** Với ghi thông thường, ưu tiên chính sách generator được hiểu rõ; dùng event timestamp khi sự kiện nguồn có định nghĩa thứ tự hợp lệ.
5. **Kiểm tra timestamp đầu vào nếu hợp đồng nghiệp vụ cho phép.** Ví dụ với mutation “đang diễn ra ngay bây giờ”, từ chối hoặc cách ly request có `eventTime > trustedNow + allowedSkew`. Không tự từ chối mọi timestamp quá khứ vì có thể đang import/replay hợp lệ.
6. **Xử lý retry có định danh sự kiện.** Giữ nguyên timestamp đối với cùng mutation khi yêu cầu idempotent theo thời điểm nguồn; đừng để retry cũ tự nhận timestamp lớn hơn một cập nhật mới nếu nghiệp vụ không mong muốn.
7. **Tránh nhiều writer cạnh tranh cùng cell.** Nếu cần thứ tự cập nhật chắc chắn, dùng một owner điều phối, sequence/version được kiểm tra hoặc **lightweight transaction (LWT)** thay vì chỉ trông đợi LWW.

Ví dụ Java chỉ minh họa **kiểm tra biên future timestamp** cho sự kiện thời gian thực:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class EventTimeGuard {
    private final Clock clock;
    private final Duration allowedFutureSkew;

    public EventTimeGuard(Clock clock, Duration allowedFutureSkew) {
        this.clock = clock;
        this.allowedFutureSkew = allowedFutureSkew;
    }

    public void validateRealtimeEvent(Instant eventTime) {
        Instant now = clock.instant();
        if (eventTime.isAfter(now.plus(allowedFutureSkew))) {
            throw new IllegalArgumentException(
                "Event time is unreasonably far in the future"
            );
        }
    }
}
```

Guard này chỉ có ý nghĩa nếu `clock` được đồng bộ với nguồn tin cậy; **một máy có đồng hồ sai không thể tự chứng minh đồng hồ của chính mình đang đúng**. `allowedFutureSkew` phải là giá trị được cấu hình từ SLA, không sao chép một hằng số tùy ý cho mọi hệ thống. Lệnh nhập lại dữ liệu lịch sử cần chính sách khác so với cập nhật trạng thái thời gian thực.

## 11. Khắc phục sự cố khi đã có future timestamp

Khi phát hiện dữ liệu bị ảnh hưởng, việc ưu tiên là **ngăn lỗi lặp lại**, **xác định phạm vi** rồi mới thay đổi dữ liệu. Một quy trình ứng cứu thực tế:

### Bước 1 — Ổn định nguồn timestamp

Kiểm tra và đồng bộ giờ trên client/coordinator; tạm ngừng hoặc cách ly thành phần đang phát timestamp sai. Xác nhận cấu hình `USING TIMESTAMP` / `setQueryTimestamp()` / generator đã được sửa, kể cả đường retry và batch.

### Bước 2 — Xác định phạm vi tác động

Đối chiếu keyspace, partition key, clustering key và cell bị ảnh hưởng; thu thập `writetime()` của các cell còn sống, log request, event ID và thời điểm do nguồn tin cậy ghi lại. Kiểm tra có tombstone/TTL liên quan hay không. **Không tự suy ra tất cả dữ liệu trong một hàng đều bị ảnh hưởng**, vì LWW áp dụng theo cell.

### Bước 3 — Chọn phương án khôi phục dựa trên nghiệp vụ

| Phương án | Khi cân nhắc | Giới hạn |
|---|---|---|
| Chờ những mutation bình thường có timestamp vượt qua giá trị sai | Khoảng lệch nhỏ, trạng thái tạm thời, chấp nhận được với SLA | Không phù hợp nếu lệch nhiều tháng/năm hoặc cần sửa tức thời |
| Dùng nguồn dữ liệu sự kiện đáng tin cậy để tái tạo trạng thái | Có event log/version chuẩn, xác định chính xác giá trị hợp lệ | Cần thiết kế ghi lại và xác minh cách xử lý timestamp/tombstone |
| Chạy thao tác sửa có chủ đích ở phạm vi partition/cell xác định | Có kế hoạch vận hành, đã sao lưu/đối chiếu, hiểu timestamp đang thắng | Có thể tạo timestamp còn lớn hơn và kéo dài vấn đề nếu triển khai sai |
| Chuyển sang mô hình cập nhật có điều kiện hoặc điều phối một writer | Nhiều writer có xung đột trạng thái lặp lại | Thay đổi thiết kế/chi phí, không tự động sửa dữ liệu cũ |

**Cần đặc biệt thận trọng với việc ghi lại bằng một timestamp lớn hơn future timestamp sai.** Trong thí nghiệm, điều này chứng minh luật LWW; trong production, nó có thể tiếp tục “đầu độc” các bản ghi về sau. Phải đánh giá các request kế tiếp, đặc điểm tombstone, backup và kế hoạch phục hồi an toàn trước khi can thiệp. Không trực tiếp xóa SSTable, chỉnh timestamp vật lý hoặc giảm grace period chỉ để xóa dấu vết của sự cố.

### Bước 4 — Kiểm tra trạng thái sau sửa

Đọc lại đúng partition/cell ở mức consistency phù hợp; xác minh giá trị và `writetime()` khi cell tồn tại. Theo dõi retry của ứng dụng, đồng hồ của các nguồn ghi và tiến trình repair. Cần kiểm tra cả **những thao tác ghi tiếp theo** để chắc rằng một timestamp còn bất thường không tiếp tục chi phối dữ liệu.

## 12. Liên hệ thiết kế bảng theo truy vấn và nghiệp vụ có thứ tự

Cassandra thiết kế bảng theo **truy vấn**. Thời điểm sự kiện dùng để truy vấn không đồng nhất với mutation timestamp dùng để LWW.

Ví dụ hệ thống nhận trạng thái theo từng phiên xử lý, cần lưu **lịch sử**:

```sql
CREATE TABLE IF NOT EXISTS status_events_by_order (
    order_id uuid,
    event_time timeuuid,
    status text,
    source_id text,
    PRIMARY KEY ((order_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

SELECT event_time, status, source_id
FROM status_events_by_order
WHERE order_id = 66666666-6666-6666-6666-666666666666
LIMIT 20;
```

Mô hình này lưu các event thành **những hàng khác nhau**, giảm ghi đè trực tiếp lên một cell trạng thái. Tuy nhiên, `timeuuid` cũng thường được tạo theo đồng hồ, nên sai lệch đồng hồ vẫn có thể làm thứ tự sự kiện chưa phản ánh đúng thứ tự nghiệp vụ. Nếu thực sự cần thứ tự nghiêm ngặt, sử dụng **sequence/version từ nguồn điều phối đáng tin cậy**, lưu định danh sự kiện và quy tắc xử lý trùng, hoặc LWT cho các trạng thái có điều kiện.

Không thể viết `ORDER BY writetime(status)` để giải quyết bài toán thứ tự sự kiện: Cassandra sắp xếp trong partition theo **clustering key** phù hợp với thiết kế bảng, không theo metadata mutation timestamp của cell.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Ghi cuối cùng luôn thắng.” | Bản có **mutation timestamp lớn hơn** thường thắng; thời điểm request đến có thể khác |
| “Client clock chạy nhanh chỉ làm lệch log.” | Nếu client/driver tạo timestamp, dữ liệu có thể bị **ghi đè sai thứ tự** |
| “Tăng `CL` lên `ALL` sẽ sửa future timestamp.” | CL không thay cơ chế LWW, chỉ ràng buộc số replica tham gia/xác nhận |
| “`writetime()` cho biết thời gian người dùng sửa dữ liệu.” | Nó cho biết **timestamp metadata thắng**, có thể do client đặt thủ công |
| “Timestamp micro giây chắc chắn là thời gian thực chính xác.” | Độ phân giải không tương đương độ chính xác hay đồng hồ đồng bộ |
| “NTP tự sửa những cell đã có timestamp tương lai.” | Đồng bộ đồng hồ giúp **ghi sau này**; metadata đã ghi không tự được viết lại |
| “Cứ xóa rồi tạo lại là hết lỗi.” | Một **tombstone timestamp thấp hơn** cũng có thể thua phiên bản tương lai |
| “TTL bằng số giây sẽ tự chữa mọi giá trị ghi sai.” | TTL có cơ chế thời hạn riêng; không là công cụ phục hồi thứ tự ghi |
| “Dữ liệu đang hiển thị đúng sau repair nghĩa là nguyên nhân hết.” | Repair đồng bộ replica; nguồn timestamp sai vẫn có thể tái diễn |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Dịch vụ A ghi `status = 'PAID'` với timestamp `T+30 phút` do đồng hồ nhanh. Một phút sau, dịch vụ B ghi `status = 'REFUNDED'` với timestamp `T+1 phút`. Giá trị nào thắng?

**Đáp án:** `PAID`, vì timestamp của A lớn hơn. Ghi thành công từ B không có nghĩa nó thắng LWW.

**Câu 2.** Nếu đổi cả đọc và ghi sang `QUORUM` hoặc `ALL`, có bảo đảm `REFUNDED` thắng không?

**Đáp án:** Không. Consistency level không sửa thứ tự timestamp; cần xử lý nguồn thời gian và quy tắc cập nhật trạng thái.

**Câu 3.** `writetime(status)` lớn hơn giờ UTC hiện tại 2 giờ. Có thể kết luận chắc chắn coordinator bị lệch 2 giờ không?

**Đáp án:** Chưa. Timestamp có thể do `USING TIMESTAMP`, Java statement, driver generator hoặc coordinator cấp. Phải kiểm tra nguồn gán và log.

**Câu 4.** Một máy có đồng hồ nhanh được chỉnh lại đúng giờ. Những cell đã mang timestamp tương lai có tự giảm write timestamp không?

**Đáp án:** Không. Đồng bộ giờ thay đổi **nguồn timestamp của các ghi tiếp theo**, không tự sửa metadata đã lưu.

**Câu 5.** Nếu lệnh `DELETE` mang timestamp nhỏ hơn phiên bản còn sống trong tương lai, bản ghi có bị xóa khỏi kết quả đọc không?

**Đáp án:** Không bảo đảm; tombstone cũ hơn không thắng phiên bản sống có timestamp cao hơn. Cần xem timestamp thực tế của các mutation liên quan.

**Câu 6.** Trong bảng lịch sử sự kiện, nếu muốn sắp xếp theo thứ tự nghiệp vụ, có nên dựa vào `writetime(status)` không?

**Đáp án:** Không. Thiết kế **clustering key** theo tiêu chí truy vấn, đồng thời xác định nguồn thời gian hoặc sequence đáng tin cậy.

**Câu 7.** Tại sao sửa một bản ghi bằng cách gán timestamp cực lớn hơn hiện tại có thể gây hệ quả lâu dài?

**Đáp án:** Nó khiến các ghi bình thường về sau có timestamp thấp hơn tiếp tục thua, kéo dài tình trạng bị che khuất và gây khó khăn cho repair/khôi phục nghiệp vụ.

---

**Ghi nhớ:** Trong Cassandra, **sai lệch đồng hồ ở nơi tạo mutation timestamp có thể trở thành sai lệch dữ liệu thực tế** vì cơ chế LWW so sánh timestamp, không so sánh thời gian người dùng thao tác. Cần đồng bộ và giám sát đồng hồ trên cả client lẫn Cassandra node, kiểm soát timestamp được gán thủ công, chẩn đoán bằng `writetime()` kết hợp lịch sử request, và chọn cơ chế điều phối/thứ tự nghiệp vụ phù hợp khi nhiều writer cùng cập nhật một cell. 
