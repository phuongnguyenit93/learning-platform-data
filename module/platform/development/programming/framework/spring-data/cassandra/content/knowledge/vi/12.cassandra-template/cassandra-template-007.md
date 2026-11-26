# Ghi giá trị null, bỏ qua giá trị và cập nhật một phần

> **Chương:** CassandraTemplate  
> **Bối cảnh:** Spring Data Cassandra truy cập Apache Cassandra theo mô hình dữ liệu phân tán, thông qua entity mapping, repository, `CassandraTemplate` và Java driver/CQL.  
> **Trọng tâm:** hiểu ba ý nghĩa hoàn toàn khác nhau của **ghi null**, **không cập nhật cột** và **cập nhật một phần**; tránh vô tình xóa dữ liệu hoặc tạo tombstone khi triển khai API PATCH.

## 1. Tình huống: thay đổi một thuộc tính thiết bị mà không làm mất thuộc tính khác

Một hệ thống IoT có bảng trạng thái thiết bị. Mỗi thiết bị có tên hiển thị, mức pin, firmware, thời điểm cập nhật; hệ thống cũng lưu lịch sử sự kiện ở một bảng khác theo thiết bị và ngày UTC.

Ví dụ trạng thái hiện tại:

~~~text
device_id       = 11111111-1111-4111-8111-111111111111
display_name    = "Cảm biến kho A"
battery_percent = 72
firmware        = "1.2.3"
updated_at      = 2026-11-25T08:00:00Z
~~~

Người vận hành gọi API PATCH để thay đổi **chỉ phần trăm pin** thành `68`. Nếu ứng dụng đọc một entity chỉ có `batteryPercent=68` còn `displayName=null` rồi thực hiện một phép ghi không đúng, nó có thể xóa tên hiện có thay vì giữ nguyên.

Một yêu cầu khác cho phép người vận hành **xóa tên hiển thị**, khi đó gửi `"displayName": null` là hành động có chủ đích. Trường hợp client **không gửi `displayName`** lại có ý nghĩa “không đụng đến cột này”.

Đây chính là ba trạng thái quan trọng:

| Trường trong yêu cầu PATCH | Ý định nghiệp vụ | Hành động trên Cassandra |
| --- | --- | --- |
| Không có `displayName` | Giữ nguyên tên | **Không ghi** vào cột `display_name` |
| Có `displayName: null` | Xóa giá trị tên | Ghi `NULL`/`DELETE` cho cột, tạo thông tin xóa |
| Có `displayName: "Kho B"` | Đổi sang giá trị mới | Ghi một giá trị mới cho cột |

**Không nên đồng nhất null với “không có gì để cập nhật”.** Đây là khác biệt cốt lõi giữa `CassandraTemplate`, câu CQL được sinh ra và mutation thực tế trên Cassandra.

## 2. Chuẩn bị bảng và entity để học xuyên suốt

Ví dụ dùng keyspace `telemetry`. Trong môi trường demo một node:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS telemetry.device_state_by_id (
    device_id       uuid PRIMARY KEY,
    display_name    text,
    battery_percent int,
    firmware        text,
    updated_at      timestamp
);
~~~

`SimpleStrategy` và RF=1 chỉ phù hợp học tập. Sản xuất nhiều node/datacenter cần replication strategy và consistency được đánh giá theo topology thực.

Khóa chính của bảng là `device_id` nên một lần sửa trạng thái chỉ cần biết thiết bị; Cassandra có thể định tuyến đến partition tương ứng. Truy vấn trạng thái:

~~~sql
SELECT device_id, display_name, battery_percent, firmware, updated_at
FROM telemetry.device_state_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Nạp dữ liệu mẫu:

~~~sql
INSERT INTO telemetry.device_state_by_id
(device_id, display_name, battery_percent, firmware, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Cảm biến kho A',
    72,
    '1.2.3',
    '2026-11-25T08:00:00Z'
);
~~~

Mapping Java:

**`DeviceState.java`**

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_state_by_id")
public class DeviceState {

    @PrimaryKey("device_id")
    private UUID deviceId;

    @Column("display_name")
    private String displayName;

    @Column("battery_percent")
    private Integer batteryPercent;

    @Column("firmware")
    private String firmware;

    @Column("updated_at")
    private Instant updatedAt;

    public DeviceState() { }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public Integer getBatteryPercent() { return batteryPercent; }
    public void setBatteryPercent(Integer value) { batteryPercent = value; }

    public String getFirmware() { return firmware; }
    public void setFirmware(String value) { firmware = value; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }
}
~~~

Dùng `Integer` thay vì `int` cho một giá trị có thể thiếu/null. Kiểu Java nullable **không tự quy định** Cassandra sẽ bỏ qua cột hay ghi tombstone: điều đó phụ thuộc câu lệnh được gửi và cách binding/mapping.

Trong Spring Boot với `spring-boot-starter-data-cassandra`, cấu hình kết nối demo:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
~~~

Tên datacenter phải khớp cluster; `datacenter1` chỉ là ví dụ. Tạo schema bằng migration trước khi chạy ứng dụng, không coi entity là bằng chứng bảng đã tồn tại.

## 3. Ba trạng thái ở tầng CQL: VALUE, NULL và UNSET

Cassandra sử dụng khái niệm **cell mutation**. Đối với một cột thông thường:

1. **Ghi giá trị thật:** một mutation ghi/cập nhật cell.
2. **Ghi null hoặc DELETE:** ghi ý nghĩa xóa giá trị, thường sinh **tombstone** để hệ thống phân tán hòa giải giữa replica.
3. **Không gửi cột hoặc bind marker là UNSET:** không yêu cầu thay đổi cell tương ứng trong statement đó.

Ví dụ:

~~~sql
-- Ghi giá trị: thay phần trăm pin; tên và firmware không bị đề cập.
UPDATE telemetry.device_state_by_id
SET battery_percent = 68,
    updated_at = '2026-11-25T08:05:00Z'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

~~~sql
-- Xóa tên hiện tại: ghi tombstone cho cột display_name.
UPDATE telemetry.device_state_by_id
SET display_name = null
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Cách diễn đạt xóa cột tường minh hơn:

~~~sql
DELETE display_name
FROM telemetry.device_state_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Trong hai ví dụ xóa, cột `display_name` không còn giá trị đang hiển thị. Nhưng điều đó **không** đồng nghĩa Cassandra đã xóa vật lý dữ liệu cũ ngay lập tức. Tombstone và compaction quyết định quá trình loại bỏ dữ liệu đã bị xóa.

**UNSET không phải một literal CQL giống `NULL`.** Nó là trạng thái của **bind variable** khi dùng prepared/bound statement qua driver. Bạn không viết `SET display_name = UNSET` như một từ khóa CQL thông thường. Khi muốn giữ nguyên cột, đơn giản nhất là **không đưa cột đó vào mệnh đề `SET`** hoặc dùng marker `UNSET` nếu câu CQL chuẩn bị sẵn có marker ấy.

## 4. UNSET khác gì với NULL trong prepared statement?

Giả sử truy vấn chuẩn bị có hai cột cần xử lý:

~~~sql
UPDATE telemetry.device_state_by_id
SET display_name = ?, updated_at = ?
WHERE device_id = ?;
~~~

Với bind marker thứ nhất:

| Giá trị bind của `display_name` | Hành vi mong muốn |
| --- | --- |
| Chuỗi `"Kho B"` | Cập nhật tên thành `Kho B` |
| `NULL` bằng API `setToNull(...)` | Xóa tên hiện có, tạo mutation/tombstone |
| `UNSET` bằng API `unset(...)` | Không tác động tới tên; các cột khác vẫn được cập nhật |

Trong Java driver 4.x có `BoundStatementBuilder`. Đoạn mã sau biểu diễn ba trạng thái:

~~~java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatementBuilder;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class DeviceNameWriter {
    private final CqlSession session;
    private final PreparedStatement statement;

    public DeviceNameWriter(CqlSession session) {
        this.session = session;
        this.statement = session.prepare(
            "UPDATE telemetry.device_state_by_id "
          + "SET display_name = ?, updated_at = ? "
          + "WHERE device_id = ?");
    }

    public void updateName(
            UUID deviceId, NameChange change, Instant now) {
        BoundStatementBuilder builder = statement.boundStatementBuilder()
            .setInstant(1, now)
            .setUuid(2, deviceId);

        switch (change.kind()) {
            case KEEP -> builder.unset(0);
            case CLEAR -> builder.setToNull(0);
            case SET -> builder.setString(0, change.value());
        }

        session.execute(builder.build());
    }

    public enum Kind { KEEP, CLEAR, SET }

    public record NameChange(Kind kind, String value) { }
}
~~~

Các index `0`, `1`, `2` khớp thứ tự marker trong prepared statement. `KEEP` được minh họa cùng thao tác cập nhật `updated_at`; nếu request **không thay bất cứ field nào**, service nên từ chối hoặc trả no-op thay vì ghi `updated_at` vô nghĩa.

**Các ràng buộc phải có:** không chấp nhận `SET` với value null; không nhận `deviceId` null; kiểm tra độ dài tên, quyền truy cập và chính sách timestamp. Nên đặt constructor/validator cho `NameChange` để giữ invariant thay vì tin caller tạo object đúng.

Dùng `unset(0)` chỉ áp dụng cho marker trong statement thích hợp; **không thể bỏ qua partition key bắt buộc**. Nếu `device_id` là UNSET/NULL thì Cassandra không có khóa định tuyến hợp lệ. Không suy diễn từ việc driver cho phép unset một cột dữ liệu rằng mọi khóa chính cũng có thể unset.

## 5. CassandraTemplate: cập nhật một phần không cần dựng entity đầy đủ

Spring Data Cassandra cung cấp `CassandraTemplate` và các abstraction `Query`, `Criteria`, `Update`. Đối với thao tác đổi **một cột** nhưng giữ nguyên những cột khác, dùng cập nhật dựa trên query/update thay vì tạo entity với hàng loạt field null.

Ví dụ service cập nhật phần trăm pin:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.data.cassandra.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class DeviceBatteryService {
    private final CassandraTemplate template;

    public DeviceBatteryService(CassandraTemplate template) {
        this.template = template;
    }

    public void changeBattery(UUID deviceId, Integer percent) {
        if (deviceId == null || percent == null
                || percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                "deviceId hoặc batteryPercent không hợp lệ");
        }

        Query query = Query.query(
            Criteria.where("device_id").is(deviceId));

        Update update = Update
            .update("battery_percent", percent)
            .set("updated_at", Instant.now());

        template.update(query, update, DeviceState.class);
    }
}
~~~

Về ý nghĩa, câu lệnh sinh ra chỉ cần cập nhật `battery_percent` và `updated_at` trong partition có `device_id` tương ứng. `display_name` và `firmware` **không nằm trong yêu cầu ghi**, nên chúng được giữ nguyên.

`CassandraTemplate` có trách nhiệm chuyển các `Criteria` và `Update` thành truy vấn tương ứng với entity mapping; nó không biến một truy vấn thiếu partition key thành truy vấn hiệu quả. Với bảng một partition key như `device_state_by_id`, cập nhật bằng `device_id` là lựa chọn định tuyến đúng.

### Lựa chọn giữa các API

| API | Mục tiêu chính | Chú ý khi cập nhật một phần |
| --- | --- | --- |
| `CassandraTemplate.update(Query, Update, Class)` | Chỉ rõ các cột cần đổi, tái sử dụng mapping | Phù hợp để tránh vô tình ghi các field không được gửi |
| `CassandraTemplate.update(entity)` | Ghi lại entity đã ánh xạ | Không giả định nó tự suy luận trường nào được gửi trong PATCH |
| `CassandraRepository.save(entity)` | Lưu entity theo ID | Không thay thế hợp đồng PATCH ba trạng thái |
| `CqlSession` với prepared statement | Kiểm soát `setToNull`, `unset`, TTL, consistency và CQL cụ thể | Phải tự chịu trách nhiệm bind, mapping và giới hạn truy vấn |

**Quan trọng:** cách framework xử lý giá trị null khi chuyển **toàn bộ entity** thành statement có thể chịu tác động của phiên bản Spring Data Cassandra, write options và mapping. Không nên gắn cho `save(entity)` một quy tắc “null luôn được bỏ qua” hoặc “null luôn tạo tombstone” mà không kiểm tra câu CQL thực tế. Với PATCH, nên định nghĩa rõ mutation qua `Update` hoặc prepared statement có chủ đích.

## 6. Vì sao entity có field null không đủ để biểu diễn PATCH?

Giả sử client chỉ gửi:

~~~json
{
  "batteryPercent": 68
}
~~~

Nếu deserializer tạo object:

~~~java
DeviceState input = new DeviceState();
input.setBatteryPercent(68);
~~~

thì `input.getDisplayName() == null`. Nhưng Java object **không cho biết** client đã bỏ qua field hay cố tình gửi `"displayName": null`. Hai request khác nhau có thể dẫn đến cùng một entity:

~~~json
{"batteryPercent": 68}
~~~

~~~json
{"batteryPercent": 68, "displayName": null}
~~~

Vì vậy, một DTO thông thường chỉ có `String displayName` chưa đủ để giữ thông tin **field có được gửi hay không** nếu cả hai tình huống có ngữ nghĩa khác nhau.

### Thiết kế DTO ba trạng thái

Có thể mô tả một field bằng:

~~~java
public enum PatchKind {
    ABSENT,  // không có field trong request
    CLEAR,   // field được gửi với null
    SET      // field có giá trị mới
}

public record FieldPatch<T>(PatchKind kind, T value) {
    public static <T> FieldPatch<T> absent() {
        return new FieldPatch<>(PatchKind.ABSENT, null);
    }

    public static <T> FieldPatch<T> clear() {
        return new FieldPatch<>(PatchKind.CLEAR, null);
    }

    public static <T> FieldPatch<T> set(T value) {
        if (value == null) throw new IllegalArgumentException("value null");
        return new FieldPatch<>(PatchKind.SET, value);
    }
}
~~~

Một yêu cầu cập nhật có thể chứa:

~~~java
public record DeviceStatePatch(
    FieldPatch<String> displayName,
    FieldPatch<Integer> batteryPercent,
    FieldPatch<String> firmware
) { }
~~~

Trong ứng dụng thật, controller/deserializer phải giữ được trạng thái có/không của property. Có thể parse JSON bằng Jackson `JsonNode` rồi kiểm tra `has(...)`:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

FieldPatch<String> displayNamePatch(JsonNode body) {
    if (!body.has("displayName")) {
        return FieldPatch.absent();
    }

    JsonNode node = body.get("displayName");
    if (node.isNull()) {
        return FieldPatch.clear();
    }

    if (!node.isTextual()) {
        throw new IllegalArgumentException(
            "displayName phải là chuỗi hoặc null");
    }

    return FieldPatch.set(node.asText());
}
~~~

`JsonNode.has("displayName")` cho phép phân biệt property không tồn tại với property có `null` (khi giá trị `null` được biểu diễn bằng NullNode). Đối với các field khác, vẫn phải kiểm tra kiểu, range và dữ liệu cho phép; không nên biến mọi node thành chuỗi một cách âm thầm.

**Quy ước PATCH là quyết định API.** Nếu sản phẩm không cho phép xóa `batteryPercent`, yêu cầu `"batteryPercent": null` phải bị từ chối, không được tự xóa field hoặc đổi thành số 0.

## 7. Xử lý PATCH ở tầng service mà không ghi các trường vắng mặt

Với một số field được phép clear, service cần tạo danh sách mutation từ DTO đã validate. Ví dụ logic ở mức ý tưởng:

~~~text
Input:
  displayName = ABSENT
  batteryPercent = SET(68)
  firmware = ABSENT

Mutation:
  UPDATE battery_percent = 68
  UPDATE updated_at = currentTime

Không cập nhật:
  display_name
  firmware
~~~

Khi field có `CLEAR`, tạo mutation riêng có chủ đích:

~~~text
Input:
  displayName = CLEAR
  batteryPercent = ABSENT
  firmware = ABSENT

Mutation:
  DELETE display_name
  hoặc UPDATE display_name = null
~~~

Cách tổ chức đơn giản cho một field tùy chọn:

~~~java
public void applyDisplayName(
        UUID deviceId, FieldPatch<String> patch) {

    switch (patch.kind()) {
        case ABSENT -> {
            return;
        }
        case CLEAR -> clearDisplayName(deviceId);
        case SET -> rename(deviceId, patch.value());
    }
}
~~~

Các hàm `clearDisplayName` và `rename` phải thực sự dùng CQL/`Update` chỉ tác động cột tương ứng; không gọi `repository.save` một entity thiếu các field khác rồi mặc nhiên coi đó là patch.

Nếu cập nhật nhiều field trong **cùng row**, có thể xây một statement có các column set tương ứng thay vì gửi nhiều update độc lập. Điều này giúp giảm round trip và làm rõ một mutation, nhưng không tự đem lại transaction ACID xuyên nhiều partition.

### Cảnh báo về timestamp cập nhật

Nếu request chỉ có `ABSENT` cho mọi field, đừng vô tình nâng `updated_at`; như vậy API đã tạo một thay đổi khi người dùng không yêu cầu gì. Hãy chọn một chính sách: trả 400/no-op theo contract, hoặc chỉ cập nhật `updated_at` khi thực sự có thay đổi được chấp nhận.

## 8. Ghi null sinh tombstone: điều đó có ý nghĩa gì?

Cassandra được thiết kế để lưu trữ phân tán trên nhiều replica. Xóa dữ liệu không đơn giản là xóa byte ngay khỏi một ổ đĩa: replica có thể tạm thời chưa nhận được mutation xóa. Cassandra dùng **tombstone** để biểu diễn dữ liệu đã bị xóa và hỗ trợ hòa giải trạng thái.

Khi chạy:

~~~sql
UPDATE telemetry.device_state_by_id
SET display_name = null
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

hoặc:

~~~sql
DELETE display_name
FROM telemetry.device_state_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

thông tin xóa phải được duy trì theo quy tắc lưu trữ, replica repair, TTL và compaction. Ghi null liên tục trên nhiều field/row có thể tạo tombstone không cần thiết, tăng chi phí đọc và xử lý nền.

**Nhưng không phải mọi tombstone đều là lỗi.** Khi nghiệp vụ thật sự cần xóa giá trị, tombstone là ngữ nghĩa bình thường của Cassandra. Vấn đề là tạo rất nhiều tombstone do hiểu nhầm null là “bỏ qua field”.

### Minh họa hai luồng

~~~text
Luồng đúng:
  PATCH {batteryPercent:68}
    → UPDATE battery_percent=68
    → display_name, firmware không đổi

Luồng sai:
  PATCH {batteryPercent:68}
    → dựng entity: name=null, battery=68, firmware=null
    → phát mutation xóa name và firmware
    → mất dữ liệu + tombstone không cần thiết
~~~

Khi giám sát, theo dõi latency đọc/ghi, số tombstone được scan, compaction backlog và kích thước partition. Không giải quyết tình trạng nhiều tombstone bằng cách giảm bừa `gc_grace_seconds`: việc giữ/xóa tombstone liên quan đến repair và khả năng dữ liệu cũ xuất hiện lại nếu các replica không đồng bộ.

## 9. NULL trong kết quả đọc không nói lên lịch sử dữ liệu

Giả sử query:

~~~sql
SELECT display_name
FROM telemetry.device_state_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Ứng dụng nhận `null`. Có thể do:

- Cột chưa từng được ghi trên row đó.
- Giá trị đã được xóa bằng `DELETE`/`SET ... = null`.
- TTL của cột đã hết hạn.
- Đọc từ replica hoặc ở consistency chưa nhìn thấy mutation mới nhất, tùy hoàn cảnh.

Chỉ từ giá trị `null` được đọc ra, **không thể biết chắc** đó là “chưa từng có” hay “đã từng có rồi xóa”. Nếu sản phẩm cần phân biệt các trạng thái này, phải mô hình hóa thông tin nghiệp vụ riêng, chẳng hạn trạng thái `neverSet`/`clearedAt`/lịch sử audit ở bảng chuyên dụng.

Đừng dùng `NULL` như một trạng thái nghiệp vụ phức tạp nếu ứng dụng cần truy vấn theo trạng thái ấy. Cassandra không phải cơ sở dữ liệu quan hệ với những điều kiện `IS NULL` tổng quát được lập index mặc định cho mọi cột.

## 10. Omitted column và UNSET không phải hai thao tác hoàn toàn đồng nhất ở mọi trường hợp

Về mục tiêu **giữ nguyên một regular column**, hai cách sau thường tương đương:

1. Sinh CQL chỉ chứa các cột thực sự cần sửa.
2. Dùng một prepared statement có đủ marker, bind `UNSET` vào cột không cần sửa.

Tuy nhiên:

- Omit column làm câu CQL ngắn và rõ hơn; nếu có nhiều tổ hợp field, số dạng prepared statement có thể tăng.
- `UNSET` giúp tái sử dụng một prepared statement có danh sách cột ổn định, nhưng cần kiểm tra semantics của statement cụ thể.
- Partition key và clustering key bắt buộc **không được thiếu** khi statement cần xác định row.
- Các thao tác như điều kiện `IF`, collection mutation, batch hoặc statement đặc biệt có giới hạn riêng đối với UNSET theo phiên bản driver/server.
- Nếu đồng thời cập nhật `updated_at`, dù mọi field nghiệp vụ đều UNSET, thao tác vẫn là một write vào `updated_at`.

Một quy tắc đơn giản: dùng `CassandraTemplate` `Update` cho tập thay đổi nhỏ, rõ ràng; dùng driver `UNSET` khi thực sự cần giữ một prepared statement mà vẫn biểu diễn ba trạng thái. Bất kể lựa chọn nào, kiểm thử **giá trị cột cũ có còn nguyên** mới là bằng chứng chính.

## 11. UPSERT: cập nhật một phần có thể tạo row mới

Trong Cassandra, `UPDATE` thông thường có semantics gần với **upsert**: không nhất thiết row đã tồn tại như SQL `UPDATE WHERE` trong RDBMS.

Ví dụ:

~~~sql
UPDATE telemetry.device_state_by_id
SET battery_percent = 68
WHERE device_id = 99999999-9999-4999-8999-999999999999;
~~~

Nếu row của thiết bị trên chưa tồn tại, Cassandra vẫn có thể tạo dữ liệu ở khóa đó với `battery_percent` được ghi; `display_name`, `firmware` và `updated_at` có thể vắng mặt. Do đó, `CassandraTemplate.update(query, update, ...)` **không nên được hiểu là “chỉ sửa nếu row đã tồn tại”** trừ khi bạn thực thi thêm điều kiện với cơ chế hỗ trợ rõ ràng.

Nếu nghiệp vụ yêu cầu “chỉ sửa thiết bị đã tồn tại”, xem xét:

- Thực thi ràng buộc ở **luồng tạo thiết bị** và quản lý lifecycle, tránh gửi patch tới thiết bị chưa đăng ký.
- Sử dụng thao tác điều kiện `IF EXISTS` khi cần bảo đảm ở Cassandra, hiểu rõ chi phí LWT.
- Tránh dùng `existsById` rồi `update` như bảo đảm atomic: hai thao tác đó có race.

Ví dụ CQL điều kiện:

~~~sql
UPDATE telemetry.device_state_by_id
SET battery_percent = 68
WHERE device_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
~~~

Phải đọc kết quả `[applied]` để biết điều kiện có được áp dụng; LWT sử dụng cơ chế đồng thuận, thường đắt hơn write thông thường và không phải lựa chọn mặc định cho mọi luồng cảm biến.

## 12. TTL và write timestamp khi cập nhật một phần

Cassandra hỗ trợ TTL cho giá trị được ghi. Ví dụ:

~~~sql
UPDATE telemetry.device_state_by_id
USING TTL 3600
SET display_name = 'Tên tạm thời'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Cần hiểu rằng TTL áp dụng theo ngữ nghĩa **những cell được ghi** trong mutation; không được mặc định mọi cột khác trong row tự hết hạn sau một giờ. Nếu một cột đã có TTL nhưng được ghi lại với mutation khác, thời điểm hết hạn của giá trị mới có thể thay đổi theo chính sách TTL/default TTL hiện hành.

Vì vậy, khi thực hiện PATCH:

- `ABSENT` → không sửa cell, tránh làm mới TTL của nó.
- `SET` → ghi giá trị mới; xác định TTL nếu giá trị cần hết hạn.
- `CLEAR` → tạo mutation xóa; không có ý nghĩa “đặt TTL 0 để bỏ qua”.
- Nếu có `updated_at`, hãy hiểu nó là thời gian ứng dụng ghi/nhận sự kiện, không mặc nhiên tương đương **Cassandra writetime**.

Cassandra sử dụng timestamp của mutation trong quá trình giải quyết xung đột giữa các replica. `updated_at` là cột nghiệp vụ, có thể khác writetime. Nếu nhiều writer đồng thời sửa cùng cột, “request đến API sau cùng” không nhất thiết là quy tắc xác định thắng/thua trên mọi replica; cần hiểu xử lý timestamp và consistency, hoặc dùng cơ chế đồng bộ phù hợp.

## 13. Bảo toàn collection: null không phải collection rỗng

Nếu row có collection như `tags set<text>` hoặc `labels map<text,text>`, PATCH cần phân biệt:

- **Omit `tags`**: không sửa tập tag.
- **Clear `tags`**: yêu cầu xóa giá trị collection hoặc xóa các entry tùy contract.
- **Set `tags`**: thay toàn tập tag.
- **Add/remove một tag**: dùng partial collection mutation, không phải thay cả collection.

Ví dụ:

~~~sql
-- Cập nhật một entry map, giữ các entry khác.
UPDATE telemetry.device_state_by_id
SET firmware = '1.2.4'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Bảng mẫu ở đây dùng `firmware text`, chưa chứa map. Nếu ứng dụng bổ sung `labels map<text,text>` bằng migration, mutation đúng trên map có thể là:

~~~sql
UPDATE telemetry.device_state_by_id
SET labels['firmware'] = '1.2.4'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Điều kiện tiên quyết: cột `labels` phải tồn tại và được khai báo là **non-frozen map**. Với `frozen<map<...>>`, không được giả định partial update entry vẫn hoạt động như non-frozen. Ghi đè hoặc xóa collection có thể tạo nhiều tombstone; khi collection lớn hoặc cập nhật liên tục, nên đánh giá bảng riêng theo truy vấn.

**Lưu ý:** collection rỗng và null không phải hai trạng thái có semantics nghiệp vụ giống nhau trên mọi phiên bản CQL/driver hoặc cách mapping. Nếu API cần phân biệt, hãy kiểm thử round-trip trên phiên bản cụ thể và mô hình hóa một trường trạng thái riêng nếu cần.

## 14. Kết hợp CassandraTemplate và repository có chủ đích

Một ứng dụng có thể dùng repository cho CRUD thông thường và `CassandraTemplate` cho các cập nhật chính xác hơn.

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceStateRepository
        extends CassandraRepository<DeviceState, UUID> {
}
~~~

Ví dụ đọc:

~~~java
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class DeviceStateReader {
    private final DeviceStateRepository repository;

    public DeviceStateReader(DeviceStateRepository repository) {
        this.repository = repository;
    }

    public Optional<DeviceState> find(UUID id) {
        return repository.findById(id);
    }
}
~~~

Ví dụ cập nhật có chủ đích qua template đã ở mục 5. Nên đặt các thao tác patch vào một service chuyên trách thay vì để controller lẫn lộn:

~~~text
Controller
    ↓ parse PATCH, giữ ABSENT/CLEAR/SET
Service
    ↓ validate quyền, key, kiểu và invariant
CassandraTemplate Query+Update / CqlSession prepared statement
    ↓ đúng các cột cần đổi
Apache Cassandra partition theo device_id
~~~

Khi cần điều kiện/ràng buộc phức tạp hơn hoặc cần set/unset rõ từng marker, `CqlSession` có thể là mức kiểm soát phù hợp. Việc dùng `CqlSession` không làm mất giá trị của Spring Data repository; hai đường nên cùng tuân theo một contract nghiệp vụ và chính sách consistency.

## 15. Thiết kế theo truy vấn và khóa phân vùng vẫn là điều kiện tiên quyết

Ví dụ `device_state_by_id` có khóa đơn `device_id`, nên các UPDATE trong bài chỉ cần cột đó. Nhưng bảng event time series có thể dùng khóa:

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

Muốn cập nhật một row sự kiện ở bảng này phải định vị bằng **đủ full primary key** phù hợp: `device_id`, `event_day`, `event_time` và `event_id`. Chỉ có `event_id` hoặc chỉ có `device_id` không phải khóa đầy đủ của một row.

Ví dụ UPDATE một row sự kiện:

~~~sql
UPDATE telemetry.events_by_device_day
SET payload = '{"celsius":25.6}'
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
  AND event_time = '2026-11-25T09:30:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Không dùng `ALLOW FILTERING` hay tăng request timeout để “sửa” câu UPDATE thiếu khóa. Nếu một yêu cầu nghiệp vụ mới cần cập nhật hàng loạt theo `event_type`, phải đánh giá access pattern, bảng projection hoặc pipeline phù hợp, không xem `CassandraTemplate` là cơ chế quét/cập nhật mọi row tự do.

## 16. Đồng thời: partial update tốt hơn full replace nhưng chưa phải transaction

Xét hai yêu cầu cùng lúc:

~~~text
A: PATCH {displayName:"Kho B"}
B: PATCH {batteryPercent:68}
~~~

Nếu mỗi request chỉ cập nhật cột mình cần:

~~~sql
UPDATE telemetry.device_state_by_id
SET display_name = 'Kho B'
WHERE device_id = 11111111-1111-4111-8111-111111111111;

UPDATE telemetry.device_state_by_id
SET battery_percent = 68
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

thì hai cột độc lập thường tránh được vấn đề lost update do client đọc một snapshot cũ rồi ghi lại mọi cột.

Tuy nhiên:

- Nếu A và B cùng sửa `display_name`, vẫn có xung đột theo write timestamp.
- Nếu một thay đổi có **invariant nhiều cột** (ví dụ `min <= max`), hai partial update độc lập có thể làm trạng thái trung gian không hợp lệ.
- Nếu hai row/bảng khác nhau cần cập nhật đồng bộ, `CassandraTemplate` không tự tạo transaction ACID đa partition.
- Nếu client timeout rồi retry, cần xét mutation idempotent, TTL, timestamp và side effect bên ngoài.
- Nếu dùng nhiều mức consistency khác nhau, read có thể thấy trạng thái chưa cập nhật khi một replica chậm.

Với bất biến cần điều kiện, cân nhắc LWT `IF ...` theo CQL phù hợp và đo chi phí; không nên mặc định chuyển mọi PATCH thành LWT.

## 17. Read consistency, write consistency và PATCH

Cassandra là hệ phân tán. Trong keyspace RF=3 của một datacenter, `LOCAL_QUORUM` cần đa số replica (2/3). `LOCAL_ONE` chỉ cần một replica ở datacenter địa phương.

Một patch có thể ghi `LOCAL_QUORUM`, còn query đọc ở `LOCAL_ONE`. Trong một số tình huống, read từ replica chưa cập nhật có thể trả trạng thái cũ. Vì vậy, nếu API cần bảo đảm “ngay sau PATCH phải đọc thấy giá trị mới”, hãy đánh giá **cả** read/write consistency, luồng xác nhận và khả năng có nhiều writer, không chỉ cấu hình write.

Consistency level không biến việc kiểm tra `existsById` rồi cập nhật thành nguyên tử; cũng không làm một projection bất đồng bộ xuất hiện trước khi pipeline ghi projection ấy.

Một lựa chọn thực hành tốt là định nghĩa rõ:

| Operation | Hợp đồng cần chốt | Ví dụ câu hỏi |
| --- | --- | --- |
| `PATCH /device/{id}` | Cần xác nhận bao nhiêu replica? | Có chấp nhận trường hợp read ngay sau đó hơi cũ không? |
| `GET /device/{id}` | Read consistency và thời gian đáp ứng | Có cần read-your-writes không? |
| Sync job | Retry/backoff, idempotency | Nếu client timeout, mutation có thể đã thành công không? |
| Audit log | Nguyên nhân và thời điểm thay đổi | Có cần lưu sự kiện `CLEAR` riêng để phân biệt với chưa từng đặt? |

## 18. Kiểm thử: chứng minh KEEP, CLEAR và SET không bị lẫn

Nên dùng Cassandra thật trong môi trường cô lập hoặc Testcontainers với schema tạo bằng migration. Mock template không chứng minh được semantics CQL, tombstone và UNSET.

### Ma trận kiểm thử

| Trạng thái trước | PATCH | Trạng thái mong đợi sau |
| --- | --- | --- |
| `display_name = Kho A` | Không có `displayName` | Vẫn `Kho A` |
| `display_name = Kho A` | `"displayName": null` | Không còn tên |
| `display_name = Kho A` | `"displayName": "Kho B"` | Thành `Kho B` |
| `battery_percent = 72` | `"batteryPercent": 68` | Pin thành 68, các field khác giữ nguyên |
| `battery_percent = 72` | `"batteryPercent": null` nhưng không cho clear | Request bị từ chối |
| Row không tồn tại | UPDATE thường theo key | Kiểm tra semantics upsert đã chốt |
| Row không tồn tại | UPDATE `IF EXISTS` | `[applied]` là false |
| Nhiều writer cập nhật hai cột khác nhau | Hai partial update | Không làm mất field không liên quan |
| Có TTL trên một cột | PATCH field khác | Không vô tình làm mới TTL của cột không cập nhật |

### Ví dụ thử với CQL

Sau khi nạp dữ liệu mẫu:

~~~sql
-- Chỉ cập nhật pin.
UPDATE telemetry.device_state_by_id
SET battery_percent = 68
WHERE device_id = 11111111-1111-4111-8111-111111111111;

-- Tên hiển thị phải giữ nguyên nếu không có mutation cho tên.
SELECT display_name, battery_percent
FROM telemetry.device_state_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Sau đó thử xóa:

~~~sql
DELETE display_name FROM telemetry.device_state_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;

SELECT display_name
FROM telemetry.device_state_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Khi dùng prepared statements, thêm test cho `unset(0)` và `setToNull(0)` với cùng dữ liệu ban đầu. Cần kiểm tra cả giá trị các cột khác sau ghi, không chỉ kiểm tra statement không ném exception.

### Không biến kiểm thử thành sửa dữ liệu production

Dùng keyspace test riêng, UUID ngẫu nhiên hoặc bộ dữ liệu cô lập. Nếu dùng Testcontainers, khởi động đúng phiên bản Cassandra tương thích, áp DDL trước khi test, cấu hình local datacenter và kết nối phù hợp. Test ghi/xóa trên keyspace production có thể làm mất dữ liệu thật.

## 19. Quan sát và xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| PATCH pin làm mất tên thiết bị | Mapped entity với field null bị ghi/xóa ngoài ý muốn | Dùng `Query + Update` chỉ chứa pin và updated_at |
| Gửi `displayName:null` nhưng tên không bị xóa | Mọi null bị coi là ABSENT/UNSET | Lưu trạng thái property present và gọi clear có chủ đích |
| Client không gửi tên nhưng tên vẫn bị xóa | DTO không phân biệt vắng mặt và null | Dùng tri-state PATCH hoặc JSON presence-aware parsing |
| Thêm `UNSET` nhưng query lỗi | Marker đặt sai vị trí hoặc dùng cho khóa bắt buộc | Chỉ unset regular column hợp lệ; bind đủ khóa |
| UPDATE thông báo thành công nhưng tạo row thiếu field | Cassandra UPDATE có thể upsert | Kiểm tra quy tắc create/update, dùng `IF EXISTS` nếu cần |
| LWT chậm hơn ghi thông thường | Chi phí đồng thuận | Chỉ dùng cho bất biến nghiệp vụ cần bảo đảm |
| Nhiều tombstone sau PATCH | Vô tình ghi null hoặc ghi lại/xóa nhiều cột | Đo CQL/mutation thực, giảm clear không cần thiết |
| Patch đã thành công nhưng GET thấy cũ | Read consistency hoặc replica chưa cập nhật | Xem RF, read/write consistency, tải và topology |
| TTL của field thay đổi ngoài dự tính | Đã ghi lại cell có TTL hoặc dùng write options khác | Kiểm tra TTL/writetime và chỉ ghi cột cần sửa |
| `@Transient` khiến field không được lưu | Field bị loại khỏi entity mapping | Đánh giá annotation và schema; không dùng nó để điều khiển PATCH theo request |
| Query cập nhật sai partition | Không bind đủ primary key khi dùng bảng composite key | Thiết kế query theo schema thật, không dùng filtering để chữa |

Khi debug, log **tên field được cập nhật và loại thao tác (KEEP/CLEAR/SET)** thay vì log nội dung nhạy cảm. Có thể ghi nhận request correlation ID, query timeout, p95/p99 latency, tỷ lệ retry, số tombstone scan và compaction backlog. Không log password, token hoặc toàn bộ dữ liệu cảm biến không cần thiết.

## 20. Quy trình triển khai PATCH an toàn

Một quy trình từ yêu cầu đến production:

1. **Chốt API contract:** field nào optional, field nào cho clear, field nào chỉ cho SET; quy định ABSENT/CLEAR/SET và HTTP response.
2. **Xác minh schema:** mọi câu UPDATE có đủ partition key; cột và type khớp mapping Java.
3. **Thiết kế DTO ba trạng thái:** giữ thông tin property có xuất hiện trong JSON; validate type, range, quyền và số lượng field.
4. **Chọn API ghi:** `CassandraTemplate.update(Query, Update, ...)` cho field-set cụ thể; dùng `CqlSession` nếu cần `setToNull`/`unset`/LWT chi tiết.
5. **Kiểm soát lifecycle:** tránh upsert trái ý định; cân nhắc `IF EXISTS` khi contract đòi hỏi.
6. **Phân tích consistency và concurrency:** xác định khi nào cần read-your-writes, cùng-key conflict và retry idempotent.
7. **Kiểm thử tích hợp:** KEEP giữ nguyên, CLEAR xóa, SET cập nhật; thử TTL, row chưa tồn tại và nhiều writer.
8. **Đo hiệu năng:** số round trip, write latency, tombstone, compaction, timeout, tải cao nhất của thiết bị.
9. **Triển khai theo đợt:** canary, quan sát, xác minh dữ liệu hiện hữu không bị xóa ngoài ý muốn; chuẩn bị rollback ứng dụng.

**Lưu ý:** rollback code không tự khôi phục giá trị đã bị xóa và bị compaction xử lý. Nếu đã ghi null sai vào production, việc khôi phục có thể cần dữ liệu audit, snapshot/backup hoặc nguồn dữ liệu khác. Do đó cần test PATCH semantics **trước** khi mở traffic.

## 21. Bài tập vận dụng

### Bài A — Ba trạng thái của field

Dữ liệu ban đầu: `display_name="Cảm biến kho A"`, `battery_percent=72`. Với ba JSON sau, hãy xác định các mutation:

~~~json
{"batteryPercent": 68}
~~~

~~~json
{"displayName": null}
~~~

~~~json
{"displayName": "Cảm biến kho B"}
~~~

**Gợi ý:** request thứ nhất chỉ set pin; request thứ hai clear tên; request thứ ba set tên. Không gửi field không phải clear field.

### Bài B — UNSET và NULL trên prepared statement

Một prepared statement có `SET display_name = ?, updated_at = ? WHERE device_id = ?`. Hãy viết hai lần bind marker thứ nhất bằng `unset(0)` và `setToNull(0)`. Giải thích vì sao trường hợp đầu giữ nguyên tên còn trường hợp sau tạo mutation xóa; vì sao marker `device_id` không thể unset.

### Bài C — Chọn CassandraTemplate hay repository

Service chỉ cần cập nhật `battery_percent` và `updated_at` của một thiết bị. Viết query `Criteria.where("device_id")` kết hợp `Update.update(...)`. Tại sao không dựng entity với các trường khác null rồi gọi `save` khi API PATCH phải giữ nguyên cột khác?

### Bài D — Race và read-modify-save

Hai request đồng thời sửa tên và pin, cả hai đều đọc entity cũ rồi lưu cả entity. Mô tả một kịch bản mất cập nhật và đề xuất partial update theo cột để giảm xung đột. Vì sao vẫn cần xử lý riêng nếu cả hai sửa cùng một cột?

### Bài E — TTL và tombstone

Một cột có TTL một giờ, request PATCH chỉ sửa cột khác. Hãy giải thích vì sao không nên ghi lại toàn bộ entity; những phép đo nào chứng minh số tombstone và latency thay đổi do các mutation không cần thiết?

### Bài F — Kiểm tra tồn tại

Product yêu cầu PATCH chỉ được thực hiện khi thiết bị đã đăng ký. Vì sao `existsById` rồi `update` chưa đủ để tạo bảo đảm nguyên tử? Hãy dùng `IF EXISTS` trong CQL và giải thích chi phí LWT cùng cách đọc `[applied]`.

### Bài G — Schema theo truy vấn

Một bảng sự kiện có `PRIMARY KEY ((device_id, event_day), event_time, event_id)`. API chỉ có `eventId` và muốn xóa `payload` của một event. Có thể dùng `CassandraTemplate.update` trực tiếp theo eventId không? Thiết kế một bảng tra cứu vị trí event hoặc thay đổi API để có đủ khóa; đánh giá chi phí đồng bộ bảng lookup.

**Tiêu chí đạt:** người học phân biệt rõ NULL/tombstone, UNSET/giữ nguyên và update giá trị; viết được partial update đúng partition key; thiết kế PATCH ba trạng thái; biết rủi ro upsert, TTL, consistency và concurrency; kiểm chứng bằng Cassandra thật thay vì chỉ nhìn object Java.

## 22. Checklist khi review một cập nhật một phần

- [ ] API phân biệt được field **không có**, field có **null** và field có **giá trị**?
- [ ] Những field không được gửi **không** xuất hiện trong mutation?
- [ ] NULL/CLEAR chỉ được dùng ở field sản phẩm cho phép xóa?
- [ ] Dùng `CassandraTemplate Update` hoặc statement binding có chủ đích thay vì full entity save ngoài ý muốn?
- [ ] Query chứa đủ partition key; với row có clustering key, đã xác định đủ khóa chưa?
- [ ] Đã quyết định UPDATE cho phép upsert hay bắt buộc `IF EXISTS`?
- [ ] Đã kiểm tra TTL và tránh ghi lại cell không thay đổi?
- [ ] Retry có an toàn, consistency và race condition đã được phân tích?
- [ ] Có integration test xác minh KEEP, CLEAR, SET và các field không liên quan?
- [ ] Tombstone, latency, compaction được giám sát; có kế hoạch khôi phục nếu clear sai?

## Tài liệu tham khảo

- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): thao tác `Query`, `Criteria`, `Update` và entity mapping.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): ánh xạ field, annotation và kiểu dữ liệu.
- [Spring Data Cassandra — Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): `save` và truy cập theo key.
- [Java Driver 4 — Bound statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/): bind values, `setToNull` và `unset`.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): `UPDATE`, `DELETE`, `NULL`, `TTL`, `IF EXISTS` và primary key.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): mô hình theo truy vấn, partition key và giới hạn update.
