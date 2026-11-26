# Giới hạn kích thước và chi phí cập nhật collection

> **Chương:** Kiểu dữ liệu  
> **Công nghệ:** Apache Cassandra, CQL, Spring Data Cassandra và Java driver.  
> **Trọng tâm:** chọn `list`, `set`, `map` đúng mục đích; kiểm soát kích thước và tốc độ cập nhật; nhận diện chi phí tombstone, compaction; biết khi nào cần mô hình hóa từng phần tử thành hàng riêng.

## 1. Bài toán: trạng thái thiết bị và dòng sự kiện

Giả sử hệ thống IoT có hai yêu cầu:

- Hiển thị trạng thái một thiết bị, gồm 5–20 nhãn (ví dụ `outdoor`, `critical`), một nhóm thuộc tính nhỏ như `firmware`, `zone`, `owner` và thời điểm hoạt động cuối.
- Lưu hàng chục nghìn sự kiện mỗi ngày, cho phép xem 50 sự kiện mới nhất theo thiết bị/ngày và phân trang những sự kiện cũ hơn.

Hai yêu cầu đều chứa “nhiều giá trị”, nhưng chỉ yêu cầu đầu phù hợp với collection trong một row. Nhu cầu thứ hai tăng liên tục theo thời gian và cần khóa phân vùng, thứ tự cùng paging riêng.

Một bảng trạng thái minh họa:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS telemetry.device_snapshot (
    device_id        uuid PRIMARY KEY,
    tags             set<text>,
    labels           map<text, text>,
    recent_event_ids list<uuid>,
    last_seen        timestamp
);
~~~

`SimpleStrategy` với RF=1 chỉ dùng cho môi trường học tập một node. Sản xuất nhiều node thường dùng `NetworkTopologyStrategy` với replication factor dựa trên topology thực tế.

Ở bảng này, `device_id` là partition key, giúp đọc trạng thái một thiết bị hiệu quả. Các collection cần được **giới hạn số phần tử, kích thước value và tần suất thay đổi**. Nếu cứ nối sự kiện vào `recent_event_ids` mà không có giới hạn, collection trở thành kho lịch sử không kiểm soát.

**Ý chính:** collection rất hữu ích cho một **nhóm dữ liệu nhỏ có giới hạn** gắn với row chủ, nhưng không thay thế bảng Cassandra được thiết kế theo access pattern.

## 2. Học xong bài này bạn làm được gì?

Bạn sẽ có thể giải thích:

1. Khi nào nên chọn `set<T>`, `map<K,V>`, `list<T>` hoặc `frozen<...>`.
2. Vì sao giới hạn kích thước lý thuyết không phải ngưỡng an toàn cho dữ liệu production.
3. Partial update khác gì với việc ghi lại cả collection.
4. Vì sao xóa phần tử, TTL và ghi đè collection có thể tạo tombstone gây chậm đọc.
5. Vì sao `list` thường không phù hợp để lưu event log hoặc làm queue.
6. Spring Data Cassandra ánh xạ Java collections ra sao và khi nào nên dùng `CqlSession` cho mutation cụ thể.
7. Cách thiết kế bảng thay thế có partition key, clustering columns và paging.
8. Những chỉ số cần đo trước khi chọn collection cho sản phẩm thật.

Những kết luận cần dựa trên **workload, dữ liệu và phiên bản Cassandra/driver thật**, không dựa vào việc một câu CQL có chạy thành công trên vài bản ghi mẫu hay không.

## 3. Ba loại collection và đặc điểm lưu trữ

| Kiểu CQL | Tính chất | Ví dụ phù hợp | Tín hiệu nên tránh |
| --- | --- | --- | --- |
| `set<text>` | Giá trị không trùng nhau; không có thứ tự nghiệp vụ | Tag của thiết bị | Nhiều trăm nghìn ID, cần thời điểm tạo từng tag |
| `map<text,text>` | Tra entry bằng key trong một collection | 10–30 thuộc tính hiển thị | Key tăng theo timestamp hoặc cần query các thiết bị theo value |
| `list<uuid>` | Có thứ tự, cho phép trùng phần tử | Danh sách rất ngắn, ít writer | Log sự kiện dài, queue, nhiều writer cùng append |
| `frozen<map<...>>` | Cả collection là một giá trị khi ghi | Cấu hình nhỏ được thay nguyên khối | Cập nhật một key mỗi giây trong map lớn |

Collection **non-frozen** thường được lưu dưới dạng multi-cell, cho phép Cassandra cập nhật/xóa entry riêng lẻ với những thao tác CQL được hỗ trợ. Lợi ích này không đồng nghĩa cập nhật miễn phí: nhiều lần thay đổi cùng collection vẫn tạo mutation, SSTable, tombstone và chi phí hòa giải khi đọc.

Collection **frozen** được xử lý như một giá trị nguyên khối: việc sửa một phần tử thường đòi hỏi thay toàn bộ giá trị. Frozen hữu ích cho một cấu trúc nhỏ, bất biến hoặc được lưu theo version; không tự động tốt hơn cho collection lớn.

### Không nhầm tính duy nhất với tính đúng nghiệp vụ

`set` không chứa phần tử trùng, nhưng điều đó **không** cung cấp giao dịch exactly-once cho cả pipeline. `map` có một entry cho mỗi key, nhưng hai writer cùng sửa một key vẫn có thể ghi đè nhau. `list` cho phép trùng, nên retry append sau timeout có thể tạo cùng ID hai lần.

## 4. Giới hạn kích thước: có nhiều ngưỡng phải xét

Không nên chốt “collection nhỏ” chỉ bằng số lượng phần tử. Một map có 10 entry mà mỗi value là JSON 2 MB có thể nặng hơn map có 2.000 cặp giá trị vài byte. Cũng không nên dùng giới hạn lý thuyết của cell/protocol làm dung lượng mục tiêu: ngưỡng an toàn vận hành thường thấp hơn nhiều và phụ thuộc workload.

Các đại lượng cần thống kê:

- **Số phần tử:** trung bình, P95, P99 và lớn nhất trên từng thiết bị/tenant.
- **Độ lớn:** byte của key/value, kích thước row sau serialization, tổng byte/partition.
- **Tốc độ thay đổi:** số cập nhật/giây, tỷ lệ thêm, thay, xóa; lượng đỉnh.
- **Độ bền lưu:** TTL, retention và compaction strategy.
- **Đường đọc:** luôn lấy toàn collection hay chỉ cần một entry/field?
- **Mẫu đồng thời:** bao nhiêu writer cùng sửa row, cùng key?
- **Replication/consistency:** chi phí cập nhật và đọc qua nhiều replica.
- **Nhu cầu truy vấn:** có cần lọc, sắp xếp hoặc phân trang theo từng entry?

Một ví dụ **ngân sách nghiệp vụ**, không phải hard limit của Cassandra:

| Field | Ngưỡng giả định | Giải thích |
| --- | --- | --- |
| `tags` | Tối đa 20 phần tử, mỗi tag ≤ 64 ký tự | Danh mục nhãn nhỏ |
| `labels` | Tối đa 32 key; mỗi value ≤ 256 ký tự | Metadata hiện tại, không chứa lịch sử |
| `recent_event_ids` | Tối đa 10 ID và cập nhật hiếm | Dùng làm shortcut, không làm nguồn event |
| Event history | Hàng chục nghìn/ngày | Phải lưu thành các row theo bucket thời gian |

Nếu số ký tự được giới hạn, vẫn cần chú ý **độ dài byte UTF-8**: ký tự tiếng Việt và emoji có thể chiếm nhiều byte. Ngưỡng maxCount hoặc maxValue phải được thực thi ở mọi luồng nhập liệu, không chỉ ở REST controller.

### Ước lượng sơ bộ

Một thiết bị có 1.000 metadata entry. Mỗi key 20 byte và mỗi value 200 byte:

~~~text
Raw key/value bytes = 1.000 × (20 + 200)
                    = 220.000 byte ≈ 214,8 KiB
~~~

Con số này chưa gồm cell metadata, tombstone, SSTable, replication, compaction, serialization/network framing và overhead trong JVM. Để đánh giá an toàn, phải đo khi đọc và khi có update/delete trên dữ liệu đại diện.

## 5. Tạo dữ liệu mẫu

~~~sql
INSERT INTO telemetry.device_snapshot (
    device_id, tags, labels, recent_event_ids, last_seen
) VALUES (
    11111111-1111-4111-8111-111111111111,
    {'outdoor', 'active'},
    {'firmware': '1.2.3', 'zone': 'north'},
    [
      22222222-2222-4222-8222-222222222222,
      33333333-3333-4333-8333-333333333333
    ],
    '2026-11-25T08:00:00Z'
);
~~~

Đọc trạng thái theo đúng partition key:

~~~sql
SELECT tags, labels, recent_event_ids, last_seen
FROM telemetry.device_snapshot
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Với query này, Cassandra xác định được partition. Nhưng muốn “tìm mọi thiết bị có tag `outdoor`” là một access pattern khác. Việc có cột `tags` không khiến Cassandra tự tra cứu hiệu quả toàn cluster. Khi thực sự cần, phải cân nhắc bảng đọc theo tag hoặc index phù hợp với phiên bản/nền tảng đang dùng và được kiểm thử bằng dữ liệu thật.

## 6. Partial update trên set

Thêm một nhãn:

~~~sql
UPDATE telemetry.device_snapshot
SET tags = tags + {'maintenance'}
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Xóa một nhãn:

~~~sql
UPDATE telemetry.device_snapshot
SET tags = tags - {'active'}
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

**Lợi ích:** thao tác nhắm tới phần tử tương ứng, tránh việc ứng dụng tải toàn bộ set rồi thay nguyên collection mỗi lần. Tuy nhiên:

- Xóa phần tử tạo thông tin xóa (tombstone) phải được hợp nhất trong quá trình đọc/compaction.
- Thêm/xóa cùng tag liên tục vẫn tạo mutation; một set cuối cùng chỉ có vài phần tử có thể từng trải qua rất nhiều thay đổi.
- Set không bảo đảm thứ tự hiển thị, thời điểm thêm hoặc “tag được gắn trước/sau”. Nếu cần thông tin thời gian cho từng tag, nên mô hình hóa riêng.
- Retry với cùng tag có kết quả logic không trùng ở set, nhưng vẫn phải phân tích timestamp, TTL, cạnh tranh và các tác động ngoài Cassandra.
- Quy tắc max 20 tag không tự được database bảo đảm khi nhiều writer cùng kiểm tra số phần tử rồi thêm.

Set phù hợp với nhóm tag nhỏ, không phải tập hàng triệu event ID.

## 7. Partial update trên map và lỗi mất cập nhật

Ghi một entry:

~~~sql
UPDATE telemetry.device_snapshot
SET labels['firmware'] = '1.2.4'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Thêm/cập nhật một số entry:

~~~sql
UPDATE telemetry.device_snapshot
SET labels = labels + {
    'firmware': '1.2.5',
    'owner': 'operations'
}
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Xóa một entry:

~~~sql
DELETE labels['zone']
FROM telemetry.device_snapshot
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Với non-frozen map, partial update hữu ích khi các writer sửa những key khác nhau. So sánh:

~~~text
Ban đầu labels = {firmware: 1.2.3}

Writer A đọc toàn bộ map, thêm owner=ops
Writer B đọc toàn bộ map, thêm zone=south

A save toàn map: {firmware:1.2.3, owner:ops}
B save toàn map: {firmware:1.2.3, zone:south}
~~~

Nếu B ghi đè toàn map sau A, entry `owner` có thể mất. Mỗi writer dùng CQL cập nhật **đúng key của mình** thường tránh được việc thay thế những entry không liên quan. Tuy vậy hai writer **cùng sửa `firmware`** vẫn có xung đột; partial update không tự biến cập nhật thành transaction hoặc compare-and-swap.

Một map với key được đặt theo timestamp (ví dụ `reading_2026_11_25_08_00`) sẽ liên tục tăng cardinality. Đó là dấu hiệu dữ liệu nên chuyển sang bảng time series với clustering key thay vì tiếp tục nới giới hạn map.

## 8. List: dữ liệu có thứ tự nhưng append không an toàn với retry

Nối cuối list:

~~~sql
UPDATE telemetry.device_snapshot
SET recent_event_ids = recent_event_ids + [
    44444444-4444-4444-8444-444444444444
]
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Thêm đầu:

~~~sql
UPDATE telemetry.device_snapshot
SET recent_event_ids = [
    55555555-5555-4555-8555-555555555555
] + recent_event_ids
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Xóa phần tử theo giá trị:

~~~sql
UPDATE telemetry.device_snapshot
SET recent_event_ids = recent_event_ids - [
    22222222-2222-4222-8222-222222222222
]
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Các thao tác sửa theo **index** và xóa list theo giá trị có thể cần đọc trạng thái hiện hữu để tìm phần tử, phát sinh chi phí read-before-write tùy loại thao tác và phiên bản. Append/prepend cũng không cung cấp mô hình queue với ack, offset hoặc thứ tự nghiệp vụ giữa nhiều writer.

Một lỗi điển hình:

~~~text
1. Client append event E.
2. Server đã xử lý nhưng client không nhận phản hồi trước timeout.
3. Client retry cùng câu append.
4. List chứa [..., E, E].
~~~

`list` cho phép phần tử trùng. Không được đánh dấu append list là retry idempotent chỉ vì event ID không đổi. Ngoài ra, append liên tục không tự xóa entry cũ: một danh sách “10 sự kiện gần nhất” có thể tăng thành hàng triệu entry nếu không có quy trình giới hạn.

**Không dùng Cassandra list làm nguồn dữ liệu cho event log không giới hạn hoặc message queue.** Cần một bảng phân vùng theo thời gian hoặc hệ hàng đợi có semantics phù hợp.

## 9. Frozen và non-frozen: chọn theo kiểu cập nhật

Ví dụ bảng chứa collection thường:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.device_ui_settings (
    device_id uuid PRIMARY KEY,
    tags      set<text>,
    labels    map<text, text>
);
~~~

Ví dụ lưu một cấu hình theo version, thay nguyên khối:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.device_config_versions (
    device_id uuid,
    version   int,
    labels    frozen<map<text, text>>,
    PRIMARY KEY ((device_id), version)
);
~~~

| Khía cạnh | Non-frozen | Frozen |
| --- | --- | --- |
| Đơn vị lưu/update | Phần tử/cell của collection có thể cập nhật riêng | Cả collection là một giá trị |
| Partial update | Hỗ trợ thao tác phù hợp theo kiểu | Thường cần ghi lại nguyên giá trị |
| Nhiều key thay riêng | Có thể thuận lợi nếu collection nhỏ | Write amplification khi thay toàn khối |
| Cấu hình bất biến theo version | Có thể dùng nhưng phức tạp hơn yêu cầu | Một lựa chọn hợp lý cho giá trị nhỏ |
| Dữ liệu khổng lồ | Vẫn không nên | Cũng không nên |

Thứ tự, kiểu phần tử, nested collection/UDT và yêu cầu `frozen` cần xác minh theo **phiên bản Cassandra**. Không giả định có thể đổi một cột non-frozen thành frozen bằng một `ALTER TABLE` đơn giản mà không cần chuyển dữ liệu. Trong nhiều thiết kế cần tạo cột/bảng mới rồi migrate.

Đừng nhầm Java `Map<String,String>` với cấu hình frozen hay non-frozen thực tế. Hãy kiểm tra schema CQL và annotation/converter cụ thể.

## 10. Chi phí thay cả collection

Hai câu lệnh đều thay đổi firmware nhưng có ý nghĩa vận hành khác nhau.

**Chỉ thay key:**

~~~sql
UPDATE telemetry.device_snapshot
SET labels['firmware'] = '1.2.6'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

**Thay cả map:**

~~~sql
UPDATE telemetry.device_snapshot
SET labels = {
    'firmware': '1.2.6',
    'zone': 'north',
    'owner': 'operations'
}
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Thay cả collection có thể tạo collection-level tombstone/deletion marker cho trạng thái cũ cùng các cell mới; khi có nhiều lần thay, chi phí đọc và compaction có thể tăng. Quan trọng hơn, hai writer gửi lại hai snapshot map khác nhau có thể ghi đè phần thay đổi của nhau.

Với cấu hình rất nhỏ, hiếm khi thay và chỉ một writer, full replace có thể là lựa chọn chấp nhận được. Với map nhiều key hoặc nhiều writer, hãy ưu tiên mutation nhắm vào entry tương ứng, hoặc chuyển sang bảng quan hệ key–value theo partition key cụ thể. **Không áp dụng một quy tắc cho mọi workload; phải đo.**

## 11. Tombstone, TTL và compaction

Cassandra sử dụng mô hình lưu trữ ghi tuần tự với memtable và SSTable. Xóa dữ liệu không nhất thiết xóa ngay khỏi đĩa: Cassandra ghi dấu xóa (tombstone) để phân giải trạng thái giữa các replica và dọn trong compaction khi thỏa điều kiện.

Collection có thể sinh tombstone khi:

- Xóa entry trong map/set/list.
- Ghi đè hoặc xóa toàn bộ collection.
- TTL trên cell/mutation hết hạn.
- Thao tác cập nhật lại những phần tử đã có hoặc thay thế dữ liệu qua nhiều lần ghi.

Ví dụ cập nhật tag tạm thời với TTL:

~~~sql
UPDATE telemetry.device_snapshot
USING TTL 3600
SET tags = tags + {'temporary'}
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Với non-frozen collection, TTL gắn với các cell/mutation được cập nhật theo ngữ nghĩa của CQL và phiên bản Cassandra. Đừng suy diễn mọi tag khác đều hết hạn trong một giờ chỉ từ câu lệnh này. Hãy kiểm thử trường hợp cụ thể, kể cả cách ghi đè TTL hoặc xóa entry.

**Vì sao map hiện chỉ có 5 key mà vẫn đọc chậm?** Có thể nó đã trải qua hàng chục nghìn lần thêm/xóa trước đó. Quá trình đọc có thể phải kiểm tra những tombstone/phiên bản dữ liệu còn trong các SSTable trước khi hợp nhất kết quả. Theo dõi số tombstone được đọc, p95/p99 latency, số SSTable/partition và compaction backlog.

Không đặt `gc_grace_seconds` cực thấp chỉ để “xóa tombstone sớm” mà chưa đánh giá repair, node downtime và khả năng dữ liệu cũ xuất hiện lại. Đó là quyết định vận hành của cluster.

## 12. Mapping Java collection trong Spring Data Cassandra

Một entity có thể ánh xạ các collection CQL sang Java:

**`DeviceSnapshot.java`**

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_snapshot")
public class DeviceSnapshot {
    @PrimaryKey("device_id")
    private UUID deviceId;

    @Column("tags")
    private Set<String> tags;

    @Column("labels")
    private Map<String, String> labels;

    @Column("recent_event_ids")
    private List<UUID> recentEventIds;

    @Column("last_seen")
    private Instant lastSeen;

    public DeviceSnapshot() { }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID v) { deviceId = v; }

    public Set<String> getTags() { return tags; }
    public void setTags(Set<String> v) { tags = v; }

    public Map<String, String> getLabels() { return labels; }
    public void setLabels(Map<String, String> v) { labels = v; }

    public List<UUID> getRecentEventIds() { return recentEventIds; }
    public void setRecentEventIds(List<UUID> v) { recentEventIds = v; }

    public Instant getLastSeen() { return lastSeen; }
    public void setLastSeen(Instant v) { lastSeen = v; }
}
~~~

Repository:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceSnapshotRepository
        extends CassandraRepository<DeviceSnapshot, UUID> {
}
~~~

Tương ứng thường là:

| Java | CQL |
| --- | --- |
| `Set<String>` | `set<text>` |
| `Map<String,String>` | `map<text,text>` |
| `List<UUID>` | `list<uuid>` |
| `Instant` | `timestamp` |
| `UUID` primary key | `uuid` partition key |

Mapping có thể bị thay đổi bởi converter tùy chỉnh, naming strategy hoặc annotation khác; kiểm tra schema thật thay vì chỉ suy từ kiểu Java. Lưu ý `@Table("device_snapshot")` tìm bảng trong keyspace mà session cấu hình. Spring Boot có thể cấu hình `spring.cassandra.keyspace-name: telemetry` nếu migration đã tạo keyspace/table.

### Cẩn thận với read–modify–save

~~~java
DeviceSnapshot snapshot = repository.findById(deviceId).orElseThrow();
snapshot.getLabels().put("firmware", "1.2.4");
repository.save(snapshot);
~~~

Đây là logic đọc entity, sửa rồi lưu. Đừng giả định `repository.save` sẽ tự tối ưu thành partial update một entry. Nó có thể cập nhật nhiều cột/collection tùy mapping và lệnh mà Spring Data sinh ra, gây nguy cơ ghi đè thay đổi từ writer khác. Với thao tác thay một key, hãy dùng CQL nhắm đúng phần tử hoặc API template/update của phiên bản đã kiểm chứng.

## 13. Cập nhật một entry bằng Java driver

Spring Boot starter cho Spring Data Cassandra cung cấp Java driver qua dependency graph. Nếu cần mutation CQL cụ thể, có thể tạo một service dùng `CqlSession`:

~~~java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import org.springframework.stereotype.Service;

@Service
public class DeviceLabelService {
    private final CqlSession session;
    private final PreparedStatement changeFirmware;

    public DeviceLabelService(CqlSession session) {
        this.session = session;
        this.changeFirmware = session.prepare(
            "UPDATE telemetry.device_snapshot "
          + "SET labels[?] = ? WHERE device_id = ?");
    }

    public void setFirmware(UUID deviceId, String version) {
        if (deviceId == null || version == null || version.isBlank()
                || version.length() > 128) {
            throw new IllegalArgumentException("Dữ liệu firmware không hợp lệ");
        }
        session.execute(changeFirmware.bind("firmware", version, deviceId));
    }
}
~~~

Câu này cập nhật riêng `labels['firmware']`, không cần tải toàn bộ map về sửa trước. Prepared statement tránh nối trực tiếp input vào CQL; đồng thời giữ kiểu dữ liệu bind rõ ràng.

Thêm một tag vào set bằng prepared statement:

~~~java
import java.util.Set;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class DeviceTagWriter {
    private final CqlSession session;
    private final PreparedStatement addTag;

    public DeviceTagWriter(CqlSession session) {
        this.session = session;
        this.addTag = session.prepare(
            "UPDATE telemetry.device_snapshot "
          + "SET tags = tags + ? WHERE device_id = ?");
    }

    public void add(UUID deviceId, String tag) {
        if (deviceId == null || tag == null || tag.isBlank()
                || tag.length() > 64) {
            throw new IllegalArgumentException("Dữ liệu tag không hợp lệ");
        }
        BoundStatement statement = addTag.bind()
            .setSet(0, Set.of(tag), String.class)
            .setUuid(1, deviceId);
        session.execute(statement);
    }
}
~~~

**Quan trọng:** giới hạn số tag bằng một phép kiểm tra “đọc size rồi thêm” không bảo đảm invariant dưới cập nhật đồng thời. Nếu yêu cầu maxCount là ràng buộc cứng, cần thêm chiến lược đồng bộ hoặc thiết kế dữ liệu phù hợp. Với nhiều tenant, kiểm tra quyền sở hữu `deviceId` trước khi ghi.

Có thể đọc một row qua `CassandraTemplate`:

~~~java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

public class DeviceSnapshotLookup {
    private final CassandraTemplate template;

    public DeviceSnapshotLookup(CassandraTemplate template) {
        this.template = template;
    }

    public Optional<DeviceSnapshot> find(UUID deviceId) {
        Query q = Query.query(
            Criteria.where("device_id").is(deviceId));
        return Optional.ofNullable(
            template.selectOne(q, DeviceSnapshot.class));
    }
}
~~~

Repository, `CassandraTemplate` và `CqlSession` cùng tuân theo mô hình phân vùng; thay API không làm một query thiếu partition key trở nên nhanh.

## 14. Chuyển lịch sử sự kiện khỏi list sang bảng riêng

Thay vì một list tăng vô hạn:

~~~text
device_snapshot:
  device_id = D
  recent_event_ids = [E1, E2, ... E2000000]
~~~

Hãy thiết kế bảng theo truy vấn “sự kiện của một thiết bị trong một ngày UTC, mới nhất trước”:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Đọc timeline:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Lợi ích:

- `(device_id, event_day)` định tuyến dữ liệu và giới hạn kích thước partition theo bucket.
- `event_time DESC` hỗ trợ “mới nhất trước” **trong một partition**; `event_id` phân biệt sự kiện trùng timestamp.
- Có thể phân trang theo row bằng paging state của driver, hoặc Spring Data Cassandra `Slice` với `CassandraPageRequest`.
- Nếu retry cùng bộ khóa `(deviceId, day, eventTime, eventId)` ổn định, ghi lại thường cập nhật cùng row. Cần chuẩn hóa `Instant` đến độ phân giải millisecond của Cassandra.
- Retention có thể quản lý theo TTL và chính sách compaction phù hợp, có kiểm soát tombstone.
- Đọc nhiều ngày là nhiều bucket: ứng dụng phải ghép kết quả, không dựa vào `ORDER BY` toàn cục giữa các partition.

Cassandra paging state phân trang theo **row kết quả CQL**, không phân trang các entry trong một collection khổng lồ. Tăng page size không khắc phục việc chọn sai mô hình dữ liệu.

Một thiết bị rất nhiều event/ngày vẫn có thể có partition quá lớn; khi đó đo dữ liệu thật và xem xét bucket theo giờ hoặc chiến lược sharding phù hợp.

## 15. Map metadata nhiều key cũng có thể cần bảng riêng

Nếu metadata không còn là tập thuộc tính nhỏ mà gồm hàng nghìn key động được cập nhật độc lập, có thể chọn:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.device_attributes (
    device_id   uuid,
    attr_key    text,
    attr_value  text,
    updated_at  timestamp,
    PRIMARY KEY ((device_id), attr_key)
);
~~~

Tra một thuộc tính:

~~~sql
SELECT attr_value, updated_at
FROM telemetry.device_attributes
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND attr_key = 'firmware';
~~~

Cấu trúc này hỗ trợ truy vấn thuộc tính **của một thiết bị** bằng clustering key. Nó không giải quyết truy vấn “tất cả thiết bị có firmware X”: câu hỏi đó cần access pattern và bảng/index mới.

Nếu một thiết bị có số lượng thuộc tính cực lớn, partition chỉ theo `device_id` cũng có thể trở thành quá lớn. Việc tách collection thành bảng là bước đầu; vẫn phải đánh giá cardinality, bucket và kích thước partition.

## 16. Consistency, đồng thời và chi phí retry

Giả sử Cassandra sử dụng RF=3 trong local datacenter và service ghi ở `LOCAL_QUORUM`. Hai replica xác nhận mutation có thể đáp ứng quorum, nhưng:

- Quorum không tạo transaction bao trùm hai lần gọi repository hoặc nhiều partition.
- Hai writer cập nhật **cùng map key** có thể cạnh tranh theo quy tắc phân giải timestamp/mutation.
- Client timeout không bảo đảm mutation thất bại. Ghi có thể đã được áp dụng nhưng phản hồi không đến kịp.
- Retry `list append` có nguy cơ tạo phần tử trùng.
- Partial update không tự có invariant “tối đa 20 tag” trong môi trường nhiều writer.
- LWT/conditional update có semantics và chi phí riêng, chỉ dùng khi thực sự cần ràng buộc điều kiện; phải kiểm tra phiên bản/đường ghi phù hợp.

Ví dụ rủi ro:

~~~text
Client append E → timeout → retry append E
Kết quả có thể là [E, E].

Client ghi event theo khóa ổn định (D, day, time, E) → timeout → retry
Kết quả thường vẫn là một row mang cùng khóa.
~~~

Cần thiết kế idempotency tại nơi phát sinh event, không chỉ trông chờ kiểu collection.

## 17. Kiểm soát kích thước ở tầng API và các job

Một hợp đồng rõ ràng có thể được ghi thành quy tắc:

~~~text
device_snapshot.tags
  maxCount = 20
  maxTagBytes = 128
  allowed = nhãn đã qua chuẩn hóa

device_snapshot.labels
  maxCount = 32
  maxKeyBytes = 128
  maxValueBytes = 512

device_snapshot.recent_event_ids
  maxCount = 10
  purpose = shortcut giao diện, không là nguồn event

event history
  table = events_by_device_day
  retention = chính sách nghiệp vụ riêng
~~~

Mọi đường ghi phải tuân thủ: API, batch import, worker, admin tool, replay pipeline. Nếu API từ chối thêm tag thứ 21 nhưng job nội bộ có thể thêm hàng nghìn tag, hợp đồng không có hiệu lực.

Ngoài cardinality, cần xét **tốc độ cập nhật**. Một set luôn giữ 10 phần tử nhưng bị thêm/xóa 1.000 lần mỗi phút có thể gây nhiều tombstone và I/O. Một map 20 key bị sửa mỗi tháng có thể không có vấn đề.

Đặt ngưỡng theo **chi phí cuối** (latency, disk, compaction, replication) chứ không chỉ dung lượng hiện tại của collection.

## 18. Benchmark: đo điều gì trước khi chốt thiết kế?

Tạo dữ liệu thử trên cluster/version tương đương môi trường vận hành:

- Phân phối cardinality: 1, 10, 100, 1.000 entry; bao gồm phần tử có value lớn.
- Thử tải đọc: truy vấn toàn collection và truy vấn chỉ lấy cột scalar.
- Thử tải ghi: thêm/sửa/xóa một entry, thay toàn collection, nhiều writer đồng thời.
- Thử list append có retry và kiểm tra khả năng trùng.
- Thử TTL và chu kỳ add/delete để quan sát tombstone.
- Đo khi compaction hoạt động, với replication và consistency thật.

| Nhóm đo | Metrics | Mục đích |
| --- | --- | --- |
| Read | p50/p95/p99, timeout, bytes returned | Đọc collection có tăng tail latency không? |
| Write | p95/p99, timeout, pending/dropped mutations | Mutation có gây hotspot khi nhiều writer? |
| Storage | byte/row, byte/partition, SSTable count | Có vượt giới hạn kích thước thực tế? |
| Tombstone | Tombstones scanned, số lần delete/TTL expire | Có read amplification do dữ liệu xóa? |
| Cluster | CPU, disk I/O, compaction backlog, GC | Chi phí có dồn sang vận hành nền? |
| Ứng dụng | Response payload, retry rate, duplicate events | Có rủi ro nghiệp vụ dù CQL thành công? |

Thử A/B hai đường: cập nhật một map key so với read–modify–save toàn map. Đối chiếu không chỉ latency mà cả lost update khi hai writer cùng chạy. Nếu collection tăng không giới hạn, thêm phương án bảng riêng vào benchmark.

Không báo một “ngưỡng collection an toàn tuyệt đối” nếu chưa có đo đạc; dữ liệu thật, topology, Cassandra version và access pattern quyết định.

## 19. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `list<uuid>` lưu toàn bộ event | Collection tăng không giới hạn, append có thể trùng khi retry | Bảng timeline theo device/day |
| `map` key là timestamp | Cardinality tăng liên tục | Bảng time series với clustering time |
| Ghi lại cả map khi chỉ sửa một key | Write amplification, lost update | Partial map mutation |
| Xóa và thêm set liên tục | Tombstone và compaction backlog | Hạn chế churn hoặc đổi mô hình |
| `frozen<map>` lớn, thay một key thường xuyên | Phải thay nguyên collection | Non-frozen collection nhỏ hoặc bảng key-value |
| Map hiện nhỏ nhưng vẫn đọc chậm | Lịch sử xóa/ghi đè tạo tombstone | Đo tombstone scanned và compaction |
| Tìm tất cả thiết bị có một tag bằng quét snapshot | Query không theo partition key | Bảng đọc theo tag hoặc index có kiểm chứng |
| Tin rằng page size 50 chia 50 entry trong map | Driver paging theo row | Đưa entry thành rows |
| Chỉ giới hạn collection ở controller | Worker/import vẫn ghi không giới hạn | Thực thi contract ở mọi đường ghi |
| Timeout cao dùng để cứu row quá lớn | Không xử lý nguyên nhân | Giảm collection, thiết kế lại query/schema |

## 20. Bài tập vận dụng

### Bài A — Chọn cấu trúc

Một thiết bị có 12 tag, 15 thuộc tính và 30.000 event/ngày. Chọn cấu trúc tương ứng và giải thích.

**Gợi ý:** set cho tag nhỏ; map cho metadata nhỏ; bảng event theo bucket UTC. Không lưu event vào list dài.

### Bài B — Ước lượng dung lượng

Một map có 2.000 entry, key trung bình 24 byte và value 120 byte. Dữ liệu key/value thô là bao nhiêu và còn thiếu khoản overhead nào?

**Gợi ý:** `2.000 × (24 + 120) = 288.000 byte` (khoảng 281,25 KiB), chưa tính cell metadata, replication, compaction, tombstone, serialization/network và dữ liệu cũ trong SSTable.

### Bài C — Retry và list

Một client append event E rồi bị timeout và gửi lại cùng E. Vì sao list có thể có hai E? Viết giải pháp dùng bảng event với primary key ổn định.

**Gợi ý:** list cho phép trùng; thao tác append không idempotent. Bảng `((device_id, event_day), event_time, event_id)` sử dụng cùng khóa khi replay để hạn chế tạo row trùng.

### Bài D — Frozen hay non-frozen?

Một cấu hình 8 entry thay mỗi tháng và một map 10.000 entry thay 100 key/phút. Chọn chiến lược cho từng trường hợp.

**Gợi ý:** frozen có thể hợp lý cho value object nhỏ thay nguyên khối; map lớn thay key liên tục nên tránh frozen, cân nhắc bảng riêng.

### Bài E — Tombstone

Một set hiện có 5 nhãn nhưng từng trải qua 100.000 lần add/delete. Giải thích tại sao đọc vẫn có thể chậm và nêu metrics cần thu.

**Gợi ý:** Tombstone/phiên bản cũ có thể còn trong SSTable trước khi compaction cho phép loại bỏ; theo dõi tombstone scan, SSTables/partition, compaction backlog, p99 latency.

### Bài F — Query theo tag

Product muốn “100 thiết bị có tag `maintenance` tại chi nhánh S”. Vì sao chỉ có `tags set<text>` trong bảng `device_snapshot` chưa đủ?

**Gợi ý:** Truy vấn theo site/tag là access pattern khác truy vấn theo device ID. Có thể cần bảng đọc theo `(tenant_id, site_id, tag)` và clustering `device_id`; đánh giá kích thước partition, đồng bộ khi thêm/xóa tag và quyền truy cập.

### Bài G — Concurrency

Hai writer đều đọc map tại thời điểm T rồi sửa hai key khác nhau. Hãy viết CQL partial update và phân tích khi nào vẫn cần LWT/điều kiện.

**Gợi ý:** `SET labels['firmware'] = ...` và `SET labels['zone'] = ...` giúp tránh thay cả map, nhưng nếu cả hai sửa cùng key hoặc có invariant chéo, phải có cơ chế giải quyết xung đột riêng.

**Tiêu chí đạt:** phân biệt đúng tính chất của list/set/map và frozen; xác định được giới hạn cardinality/byte; giải thích được partial update, tombstone, TTL, retry; ánh xạ Java collections đúng; chuyển một danh sách sự kiện lớn thành bảng có partition key, clustering và paging phù hợp.

## 21. Checklist trước khi dùng collection

- [ ] Số lượng phần tử **có giới hạn nghiệp vụ** và được kiểm tra ở mọi đường ghi?
- [ ] Kích thước key/value đã được tính theo **byte** và có kiểm thử với phần tử lớn?
- [ ] Dữ liệu có tăng theo thời gian không? Có cần bảng theo bucket/partition?
- [ ] Có cần tìm/lọc/sort/paging **từng phần tử** thay vì đọc cả collection?
- [ ] Loại list/set/map và frozen/non-frozen phù hợp với cách mutation?
- [ ] Cập nhật một entry có vô tình biến thành save lại toàn collection?
- [ ] Retry, timeout và cập nhật đồng thời đã có quy tắc idempotency?
- [ ] TTL, tombstone, compaction và repair được đưa vào kế hoạch vận hành?
- [ ] Có số đo p95/p99, partition size, tombstone scanned từ workload thực tế?
- [ ] Có hướng di chuyển sang bảng riêng khi cardinality hoặc access pattern thay đổi?

## Tài liệu tham khảo

- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): kiểu collection, `frozen`, `UPDATE`, `DELETE` và TTL.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): partition key và thiết kế bảng theo truy vấn.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): ánh xạ collection và Java types.
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): truy vấn/mutation với Spring Data.
- [Spring Data Cassandra — Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): repository theo khóa và query.
- [Java driver 4 — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/): prepared statement, bind values và retry/timeout.
