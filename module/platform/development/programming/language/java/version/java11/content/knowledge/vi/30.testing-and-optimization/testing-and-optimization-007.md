# Kiểm thử và tối ưu — JFR event, metadata và bản ghi không đầy đủ (Java 11+)

## Mục tiêu học tập

**JDK Flight Recorder (JFR)** giúp lập trình viên và nhóm vận hành điều tra hành vi JVM bằng **sự kiện (events)**. Tuy nhiên, việc một tệp `.jfr` mở thành công, có metadata, hoặc chứa một số sự kiện **không có nghĩa mọi hoạt động mong đợi đều được thu thập đầy đủ**.

Trong một cuộc điều tra hiệu năng, lỗi suy luận nguy hiểm thường là:

> “Tôi không thấy `jdk.SocketRead` hoặc custom event `demo.Detail` trong recording, vậy hoạt động đó không hề xảy ra.”

Nhận định này có thể sai vì **event type chưa được enable, threshold hoặc period đã lọc sự kiện, recording không phủ đúng khoảng thời gian, dữ liệu cũ bị loại theo maxage/maxsize, thông tin stack không được thu, quá tải/lỗi ghi dữ liệu, sai phiên bản schema, hoặc bản ghi bị hỏng/truncated**.

Bài học thuộc nhóm **Kiểm thử và tối ưu**, tập trung vào **JFR event, metadata và tính không đầy đủ của bản ghi**; sử dụng API chuẩn **Java 11** vẫn còn áp dụng trên những JDK hiện đại. Các phần chính:

1. Phân biệt bốn lớp chất lượng dữ liệu: **file có đọc được**, **metadata có đúng**, **event có hiện diện**, **coverage có đủ cho câu hỏi nghiên cứu**.
2. Hiểu các metadata `@Name`, `@Label`, `@Description`, `@Category`, `@DataAmount`, `@StackTrace` và API `EventType`/`ValueDescriptor`.
3. Phân biệt **event type có metadata** và **event instance thực sự được ghi**.
4. Biết cách dùng `Recording`, `EventSettings.withThreshold`, `withStackTrace` và `RecordingFile` để tạo và kiểm thử file.
5. Hiểu những nguyên nhân phổ biến làm recording thiếu events, thiếu fields, thiếu stack hoặc thiếu đoạn thời gian.
6. Phân biệt **file hợp lệ nhưng coverage thiếu** với **file bị cắt/hỏng không parse được**.
7. Viết và chạy chương trình `JfrCoverageDemo.java` tương thích **Java 11**, có cả file đầy đủ, file bị lọc events và header JFR bị cắt.
8. Lập test matrix và runbook khi cần dựa trên JFR để kết luận performance hoặc root cause.
9. Tối ưu chi phí thu thập JFR mà không đánh đổi dữ liệu quan trọng một cách vô thức.
10. Tách rõ **điều đã quan sát** và **điều chưa thể chứng minh**.

**Special Note:** chỉ dùng những API/cách làm vẫn có giá trị. Ví dụ Java có thể compile với `javac --release 11`; không lẫn các API xuất hiện sau Java 11 như `RecordingFile.write(Path, Predicate)` (được bổ sung ở Java 19), không dựa vào các flag thương mại JFR cũ hay giả định tất cả chức năng CLI/JMC đều giống nhau trên mọi JDK.

---

## 1. Bốn mức “đầy đủ” cần phân biệt

Một file JFR có thể **hợp lệ về mặt cấu trúc** nhưng **không đủ để trả lời câu hỏi nghiệp vụ**. Hãy đánh giá theo nhiều lớp:

| Lớp kiểm tra | Câu hỏi | Ví dụ PASS | Giới hạn |
| --- | --- | --- | --- |
| **1. File integrity / readability** | File có đúng định dạng JFR và parser đọc được không? | `new RecordingFile(file)` rồi đọc hết events thành công | Không chứng minh đủ mọi events đã xảy ra |
| **2. Metadata / schema** | Tên type, tên field, type, labels, units có như mong đợi không? | `demo.Request`, field `bytes` có `@DataAmount(BYTES)` | Schema có thể hiện diện dù không có instance được ghi |
| **3. Observed events** | Những event instances nào thực sự tồn tại trong file? | Có 1 `demo.Request` và 1 `demo.Detail` | Không chứng minh mọi event được tạo đều đến được file |
| **4. Coverage / fitness for purpose** | File đã phủ **đúng process, thời gian, settings, request và nguồn bằng chứng** chưa? | Có đủ begin/end/business IDs theo contract, trong time window cần xét | Cần đối chiếu với nguồn ngoài JFR, như metrics/traces/logs |

**File parse thành công ≠ recording đầy đủ.** Parser xác minh cấu trúc/format đủ để đọc; nó không thể biết một request đã xảy ra ngoài thời gian thu, event đã bị threshold loại hay một parent event chưa từng được commit.

**Metadata hiện diện ≠ event đã xảy ra.** `RecordingFile.readEventTypes()` cho biết những **event types được mô tả trong recording**. Để biết có bao nhiêu instances, phải **đếm các `RecordedEvent`** theo tên type và time window.

**Không có event ≠ không có hoạt động.** Khi phân tích incident, nên dùng trạng thái như **INSUFFICIENT_EVIDENCE / UNKNOWN_COVERAGE** thay vì tự biến count=0 thành một kết luận nhân quả.

## 2. Event metadata là gì và vì sao cần kiểm thử?

Một custom JFR Event có **schema** mô tả ý nghĩa của những giá trị được ghi:

```java
@Name("demo.Request")
@Label("Business request")
@Description("One completed request, no personal data")
@Category({"Learning", "Coverage"})
@StackTrace(true)
static final class Request extends Event {
    @Label("Request ID")
    String requestId;

    @Label("Payload bytes")
    @DataAmount(DataAmount.BYTES)
    long bytes;

    boolean success;
}
```

Đây là đoạn khai báo **nằm trong một outer class**. Mã hoàn chỉnh runnable nằm ở phần 8.

### Các annotation chính

| Annotation | Công dụng | Kiểm tra |
| --- | --- | --- |
| `@Name("demo.Request")` | Tên định danh type dùng khi enable/filter | `EventType.getName()` |
| `@Label("Business request")` | Nhãn dễ đọc | `EventType.getLabel()` |
| `@Description` | Mô tả ý nghĩa/điều kiện ghi | `EventType.getDescription()` |
| `@Category` | Nhóm event theo danh mục | `EventType.getCategoryNames()` |
| `@DataAmount(BYTES)` | Field `long` mang đơn vị bytes | `ValueDescriptor.getContentType()` / `getAnnotation(DataAmount.class)` |
| `@StackTrace(true)` | **Default** về việc thu stack | Có thể bị override qua `EventSettings` |

**Chú ý:** metadata là thông tin mô tả. `@DataAmount(BYTES)` **không** biến 4096 bits thành 512 bytes; code phải ghi **đúng raw value theo unit**. `@StackTrace(true)` là default; recording có thể bật/tắt stack riêng và field `getStackTrace()` vẫn có thể là `null`.

### Vì sao phải kiểm tra metadata trước khi đọc field?

Một consumer viết:

```java
long bytes = event.getLong("bytes");
```

chỉ đúng khi type đang xét có field `bytes` tương ứng kiểu `long`. Nếu bạn cố đọc field không tồn tại hoặc sai type, consumer có thể ném `IllegalArgumentException`; nếu code đơn giản bỏ lỗi đó, bản phân tích sẽ mất dữ liệu mà không được thông báo.

Cách phòng ngừa:

- Lọc theo `event.getEventType().getName()`.
- Kiểm tra schema qua `EventType.getFields()` hoặc `event.hasField("bytes")`.
- Kiểm tra `ValueDescriptor.getTypeName()`, `getContentType()` và annotation unit nếu kết quả được dùng để tính toán.
- Không hardcode **numeric event type ID** như định danh ổn định giữa các JVM/recording files.
- Version schema rõ ràng khi đổi field name, units hay meaning của events.

### Không gán ý nghĩa sai cho metadata của event đã bị lọc

Một type được JVM định nghĩa/đăng ký và có thể được mô tả trong metadata file, nhưng các event instances của nó có thể không được ghi do settings. Vì vậy **không bao giờ dùng chỉ `readEventTypes()` để khẳng định event đã xảy ra**.

Ngược lại, nếu file **không** mang một type mong đợi, cũng không thể kết luận ứng dụng không có class ấy: recording có thể chưa bật, chạy sai JVM, hoặc không có dữ liệu trong giai đoạn tương ứng.

## 3. Các nguyên nhân recording thiếu event dù file hợp lệ

### 3.1. Event chưa được enable

JFR có danh sách type rất phong phú; không nhất thiết tất cả đều bật trong mỗi profile. Recording có thể bật custom `demo.Request` nhưng không bật `demo.Detail`, hoặc không bật `jdk.SocketRead`.

```java
recording.enable(Request.class).withThreshold(Duration.ZERO);
// Nếu ứng dụng muốn thu Detail, cần enable type theo settings phù hợp.
```

Đây là đoạn minh họa, cần `Recording recording` và class `Request`.

**Hậu quả:** business request xảy ra thật, nhưng event type không được enable → không có instance trong file.

### 3.2. Event bị lọc bởi threshold

Với **duration events**, `EventSettings.withThreshold(Duration)` có thể loại những events có duration nhỏ hơn ngưỡng:

```java
recording.enable(Detail.class)
        .withThreshold(Duration.ofDays(1));
```

Nếu một `Detail` chạy 15ms, nó **không đáp ứng threshold 1 ngày**, nên không được ghi trong fixture. Đây là **file đúng định dạng** nhưng **không có event instance `Detail`**.

**Điểm quan trọng:** `detail.commit()` được gọi trong source code **không có nghĩa** event luôn tồn tại trong file. Settings là phần của contract thu thập.

Tương tự, việc dùng `@Threshold` ở event class có thể đặt default; `Recording.enable(...).withThreshold(...)` quyết định settings cụ thể của recording, có thể override default.

### 3.3. Sampling hoặc period không thu mọi occurrence

Những loại events sampled/periodic như CPU/execution samples hoặc allocation samples chỉ cung cấp **mẫu**. Một phương thức không xuất hiện trong execution samples không chứng minh nó không chạy. Không lấy số samples làm **số lần method call chính xác** hoặc total allocated bytes nếu loại event chỉ sampling.

Các events periodic phụ thuộc cấu hình `period`; khoảng time window ngắn hơn period có thể không chứa mẫu.

**Không áp dụng một “sampling rate” tự suy đoán cho mọi JFR event.** Hãy đọc metadata, event settings và JDK docs tương ứng; custom event theo `commit()`, duration event, periodic event và sampled event có semantics khác nhau.

### 3.4. Recording sai khoảng thời gian

Một flow phổ biến:

```text
12:00:00  Request A bắt đầu
12:00:01  Request A kết thúc
12:00:03  JFR recording bắt đầu
12:00:05  JFR recording dump ra incident.jfr

File hợp lệ. Request A không nằm trong khoảng được thu.
```

Không có cách nào để `RecordingFile` tái tạo event đã diễn ra **trước khi recording bắt đầu**. Khi viết báo cáo, xác định **actual start/stop times** của recording và thời gian incident. Đối với dump snapshot của recording đang chạy, không được nhầm **dump time** với **start time**.

### 3.5. Data retention giới hạn bởi `maxage`/`maxsize`

JFR có khả năng giữ dữ liệu theo tuổi và kích thước. `Recording.setMaxAge(Duration)` và `setMaxSize(long)` có thể khiến **những chunks cũ bị loại khỏi disk repository** khi vượt ngưỡng. Snapshot còn đọc được nhưng không chứa lịch sử xa hơn retention.

```java
recording.setMaxAge(Duration.ofMinutes(5));
recording.setMaxSize(64L * 1024 * 1024);
```

Đoạn minh họa dùng API Java 11. Đây là **giới hạn giữ dữ liệu**, không phải “cố gắng giữ đủ 5 phút mọi event trong mọi workload”. Với event volume cao và maxsize nhỏ, effective history có thể ngắn hơn mong đợi. Không để retention vô hạn trên production nếu storage không được quản trị.

### 3.6. Disk/memory buffers, crash và data loss

JFR thu dữ liệu qua buffers/chunks. Trong một số sự cố, phần dữ liệu còn ở memory buffers **chưa kịp được ghi ra file**; crash, power loss, IO errors hoặc repository constraints có thể khiến các khoảng thời gian không còn đầy đủ. Một số runtime/công cụ có thể phát hiện/báo mất dữ liệu, nhưng **không mặc định mọi missing event đều có marker chính xác để suy ra được**.

Nếu người dùng gửi một file sau sự cố:
- Hỏi file được tạo bằng **dump thường, dump-on-exit, crash recovery hay copy thủ công**.
- Kiểm tra JVM logging, disk write errors, thời điểm dump và repository/chunks còn lại.
- Kiểm tra file có parse được, có metadata/events trong từng interval không.
- Đối chiếu sequence/expected counts với application logs/metrics.
- Không coi một file parse được là bằng chứng tất cả buffers đều đã flush.

### 3.7. Event chưa được commit

Custom event chỉ ghi khi logic ứng dụng thực sự **commit** trong điều kiện settings phù hợp. Ví dụ code:

```java
Request event = new Request();
event.begin();
doOperation();
event.end();
// Thiếu event.commit()
```

Đây là đoạn minh họa (các class/method cần định nghĩa). **Không có `commit()`** thì không nên mong event instance tồn tại trong file. Trong failure path, nếu code thoát trước `commit`, dữ liệu cũng có thể thiếu.

Với production, nên đặt `end/commit` trong `finally` khi phù hợp, đồng thời xử lý outcome/error code và tránh logging dữ liệu nhạy cảm.

### 3.8. Sai JVM hoặc sai service instance

Một request có thể được gateway gửi tới service instance khác với JVM đang ghi JFR. Không ghép hai recordings chỉ vì thread ID hoặc timestamp giống nhau; **thread ID chỉ có ý nghĩa trong phạm vi JVM**. Luôn ghi provenance: service, instance/node, JDK version, PID nếu phù hợp, recording ID/name và time range.

## 4. Ba trạng thái file JFR không nên trộn lẫn

| Trạng thái | Ví dụ | Consumer quan sát | Kết luận đúng |
| --- | --- | --- | --- |
| **Đọc được, đủ dữ liệu yêu cầu** | Có `demo.Request` + `demo.Detail` trong fixture | Parse PASS, schema PASS, counts PASS | Đủ cho contract test này |
| **Đọc được, thiếu event instance** | `demo.Detail` bị threshold 1 ngày lọc | Parse PASS, schema Request PASS, Detail count 0 | File hợp lệ nhưng **coverage không đủ** nếu cần Detail |
| **File bị cắt/hỏng** | Chỉ còn 16 bytes đầu của file .jfr | Constructor/parser từ chối bằng `IOException` trong fixture | Không thể dùng file như recording hợp lệ; cần bản khác/chunks/backup |

**Phân biệt rõ:**
- “Metadata thiếu” là câu hỏi về **schema**, không tự động là lỗi binary file.
- “Event thiếu” là câu hỏi về **occurrences và coverage**; file vẫn có thể hoàn toàn hợp lệ.
- “File lỗi” là câu hỏi về **format/IO** và khả năng đọc. Một file bị cắt ở vùng khác có thể dẫn tới lỗi ở giai đoạn khác, hoặc chứa một số chunks vẫn đọc được tùy công cụ/version; **không được khẳng định mọi truncation đều báo giống nhau**.

### Parser không phải công cụ kiểm toán đầy đủ

`RecordingFile.readAllEvents(file)` hoặc `RecordingFile.readEvent()` đọc những events **hiện diện trong file**, không có cách biết “ứng dụng định phát 10.000 events nhưng thực ra chỉ có 9.998” nếu không có nguồn dữ liệu mong đợi từ bên ngoài hoặc sequence/correlation protocol do bạn thiết kế.

Vì vậy test tốt cần **expected event contract**, không chỉ “file có hơn 0 events”.

## 5. API Java 11 cần dùng để kiểm thử

### 5.1. Tạo recording có kiểm soát

```java
try (Recording recording = new Recording()) {
    recording.setToDisk(true);
    recording.enable(Request.class)
            .withThreshold(Duration.ZERO)
            .withStackTrace();
    recording.enable(Detail.class)
            .withThreshold(Duration.ZERO)
            .withoutStackTrace();

    recording.start();
    // Sinh events qua begin/end/commit.
    recording.stop();
    recording.dump(file);
}
```

Đây là đoạn minh họa, cần class `Request/Detail` và biến `Path file`. Chương trình đầy đủ ở phần 8 khai báo tất cả.

- `setToDisk(true)` yêu cầu recording lưu dữ liệu theo disk repository; cần quyền ghi và đủ disk.
- `enable(Class)` chọn đúng custom event type.
- `withThreshold(Duration.ZERO)` giảm nguy cơ fixture ngắn bị lọc.
- `withStackTrace/withoutStackTrace` điều khiển thu stack cho type.
- `start/stop/dump` xác lập một time window kiểm soát và xuất file.

**Không đánh đồng** `Recording.dump(file)` với dừng recording: API cho phép dump khi recording đang chạy; trong fixture, ta chủ động gọi `stop` trước `dump` để có một bản chụp ổn định.

### 5.2. Đọc metadata qua `readEventTypes()`

```java
try (RecordingFile reader = new RecordingFile(file)) {
    for (EventType type : reader.readEventTypes()) {
        if ("demo.Request".equals(type.getName())) {
            System.out.println(type.getLabel());
            for (ValueDescriptor field : type.getFields()) {
                System.out.println(field.getName());
            }
        }
    }
}
```

Đoạn minh họa cần `Path file` và imports. `readEventTypes()` chỉ cho biết những **schema mô tả trong file**. **Để biết instance count phải đọc events**.

### 5.3. Đọc từng event và đếm thực tế

```java
try (RecordingFile reader = new RecordingFile(file)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent e = reader.readEvent();
        String name = e.getEventType().getName();
        if ("demo.Request".equals(name)) {
            // Đọc dữ liệu an toàn, tăng request count.
        }
    }
}
```

Không gọi `readEvent()` sau khi `hasMoreEvents() == false`, vì API có thể ném `EOFException`. Ngoài ra có thể có `IOException` nếu file hỏng hoặc gặp lỗi IO khi đang đọc.

### 5.4. Khi nào dùng `readAllEvents()`?

`RecordingFile.readAllEvents(Path)` thuận tiện cho file test **nhỏ**. Javadoc Java 11 lưu ý phương thức này **không được thiết kế để đọc file lớn**. File nhiều gigabytes có thể làm đầy heap consumer nếu cố load toàn bộ vào List.

Với file lớn, nên dùng `hasMoreEvents/readEvent`, lọc theo type, time window và giữ counters/aggregates; nếu cần index, xây cấu trúc giới hạn memory phù hợp. **Nếu vòng lặp streaming vẫn add mọi event vào List, memory risk vẫn còn.**

### 5.5. `RecordedEvent` và null fields

Các phương thức hiện hành:
- `getEventType().getName()` — event type name.
- `getStartTime()/getEndTime()/getDuration()` — time interval.
- `getThread()` — có thể `null`.
- `getStackTrace()` — có thể `null` nếu không thu stack.
- `getString("requestId")` / `getLong("bytes")` / `getBoolean("success")` — chỉ khi schema có fields đúng type.
- `hasField("name")` — kiểm tra trước khi đọc field giữa nhiều schema versions.

**Stack null khác event missing.** Một event `demo.Request` có thể được ghi đầy đủ payload nhưng không có stack trace nếu recording tắt stack. Trong test không nên biến “stack unavailable” thành “event missing”; cần hai trạng thái chất lượng riêng.

## 6. Kiểm tra metadata và đơn vị bằng `ValueDescriptor`

Với field:

```java
@Label("Payload bytes")
@DataAmount(DataAmount.BYTES)
long bytes;
```

Metadata API có thể đọc:

```java
for (ValueDescriptor field : type.getFields()) {
    if ("bytes".equals(field.getName())) {
        DataAmount annotation = field.getAnnotation(
                DataAmount.class);
        boolean unitOkay =
                "jdk.jfr.DataAmount".equals(field.getContentType())
                && annotation != null
                && DataAmount.BYTES.equals(annotation.value());
    }
}
```

Đây là đoạn minh họa, cần `EventType type`, imports. Bài hoàn chỉnh sẽ kiểm tra các điều kiện này.

### Vì sao phải validate unit?

Một dashboard có thể format bytes theo **MiB** hoặc Mbps theo **bits**; nếu event schema đổi `bytes` thành `bits` mà vẫn giữ tên hoặc metadata cũ, số liệu sẽ bị diễn giải sai dù file parse thành công.

Tương tự:
- `@Timespan(Timespan.MILLISECONDS)` cho duration được lưu trong field riêng.
- `@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)` cho timestamp epoch milliseconds.
- `@Percentage` cho tỉ lệ dạng fraction, ví dụ 0.75 = 75%.

**Annotation không tự convert raw values.** Đây là một loại **data-quality** cần test độc lập với event count.

### Schema có thể đổi giữa JDK/app versions

Built-in JVM event types và fields có thể khác theo JDK/vendor/version. Không assume một field tồn tại từ Java 11 tới mọi bản mới. Với custom events, đổi field name/type/meaning là thay đổi contract của ứng dụng.

Khi consumer đọc nhiều file:
1. Xác định type bằng **tên**.
2. Lấy fields thực có trong file.
3. Dùng `hasField/getFields` để kiểm tra schema.
4. Mapping type/version vào cấu trúc phân tích.
5. Nếu thiếu required field, báo **SCHEMA_MISMATCH**, không âm thầm gán 0 hoặc empty string.
6. Với optional field, xử lý null/absence có chủ đích.
7. Báo JDK/vendor/app version trong kết quả phân tích.

## 7. Đặt định nghĩa “recording đủ” thành hợp đồng test

Trước khi viết parser hoặc dashboard, hãy xác định **minimum coverage contract** cho từng use case.

Ví dụ fixture:
- Trong mỗi recording hợp lệ, có đúng **một** `demo.Request` với `requestId="test-001"`.
- Request có `bytes=4096` và `success=true`.
- Schema `demo.Request` có `@Label("Business request")`.
- Field `bytes` có `@DataAmount(BYTES)`.
- Stack trace của Request được bật và có frames trong fixture.
- Với mode **full**, có đúng **một** `demo.Detail`.
- Với mode **filtered**, có đúng **0** `demo.Detail` vì recording đặt threshold một ngày.
- File header bị cắt phải bị parser từ chối trong phép thử.
- Không dùng event count của những built-in JVM events khác làm invariant; chúng có thể khác giữa JDKs.

**Chú ý:** “filtered” ở đây là **thiếu theo chủ đích** để kiểm tra cơ chế, không phải ví dụ corruption. Điều cần khẳng định từ phân tích là **Detail không được ghi trong file**. Chúng ta biết **nguyên nhân trong fixture** vì code tự đặt threshold; khi nhận file bên ngoài, không thể suy ra nguyên nhân đó nếu không có settings/logs chứng minh.

### Status nên dùng trong hệ thống phân tích

| Status | Mô tả | Hành động |
| --- | --- | --- |
| `READABLE_COMPLETE_FOR_CONTRACT` | File parse PASS, schema/expected events/interval PASS | Tiếp tục phân tích |
| `READABLE_INCOMPLETE_COVERAGE` | File parse PASS nhưng thiếu required event/time span/sequence | Cảnh báo và tìm nguồn khác |
| `SCHEMA_MISMATCH` | Required fields/types/units không đúng | Version mapping hoặc sửa producer |
| `INVALID_OR_UNREADABLE` | Parser báo IOException/unsupported format | Tìm snapshot/chunks/backup đáng tin |
| `UNKNOWN_COVERAGE` | Không có expected counts/settings/recording interval | Không khẳng định completeness |
| `PARTIAL_EVIDENCE` | Có data cho một subset, thiếu một số loại | Gắn mức tin cậy và giới hạn kết luận |

Không có một API Java 11 duy nhất `recording.isCompleteForMyBusinessQuestion()`; những statuses này là **quy ước ứng dụng** mà bạn phải tự triển khai.

## 8. Chương trình Java 11 hoàn chỉnh: hai file hợp lệ + một header hỏng

Chương trình `JfrCoverageDemo.java` dùng **JFR API chuẩn từ Java 11**. Nó:

1. Định nghĩa `demo.Request` và `demo.Detail`.
2. Tạo file **full**: bật cả hai types, threshold bằng 0.
3. Tạo file **filtered**: Request threshold 0, Detail threshold **1 ngày**, trong khi code vẫn commit Detail ngắn.
4. Mở mỗi file bằng `RecordingFile`; kiểm tra metadata của Request, unit bytes, business fields, stack và đếm instances.
5. Tạo một file thứ ba từ **16 bytes đầu** của full file, làm header JFR không đầy đủ.
6. Xác minh parser từ chối file hỏng bằng `IOException`.
7. In **10 dòng kết quả ổn định**, sau khi tất cả assertions thành công.
8. Xóa files tạm khi kết thúc; input hỏng dùng `deleteOnExit()` để tránh lỗi khóa file tạm thời trên Windows sau parse failure.

**Chỉ chạy trong môi trường test.** Code không chứa dữ liệu cá nhân, không cần database/network và không cần thư viện ngoài JDK.

### 8.1. Tệp `JfrCoverageDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import jdk.jfr.Category;
import jdk.jfr.DataAmount;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrCoverageDemo {
    @Name("demo.Request")
    @Label("Business request")
    @Description("One completed request, no personal data")
    @Category({"Learning", "Coverage"})
    @StackTrace(true)
    static final class Request extends Event {
        @Label("Request ID") String requestId;
        @Label("Payload bytes")
        @DataAmount(DataAmount.BYTES) long bytes;
        boolean success;
    }

    @Name("demo.Detail")
    @Label("Optional detail")
    static final class Detail extends Event {
        String stage;
    }

    static final class Check {
        int requests;
        int details;
        boolean schema;
        boolean stack;
    }

    private static void record(Path file, boolean includeDetails)
            throws Exception {
        try (Recording recording = new Recording()) {
            recording.setToDisk(true);
            recording.enable(Request.class)
                    .withThreshold(Duration.ZERO).withStackTrace();
            recording.enable(Detail.class)
                    .withThreshold(includeDetails
                            ? Duration.ZERO : Duration.ofDays(1))
                    .withoutStackTrace();
            recording.start();

            Request request = new Request();
            request.requestId = "test-001";
            request.bytes = 4096L;
            request.begin();

            Detail detail = new Detail();
            detail.stage = "decode";
            detail.begin();
            Thread.sleep(15);
            detail.end();
            detail.commit();

            request.success = true;
            request.end();
            request.commit();
            recording.stop();
            recording.dump(file);
        }
    }

    private static Check inspect(Path file) throws IOException {
        Check check = new Check();
        try (RecordingFile reader = new RecordingFile(file)) {
            for (EventType type : reader.readEventTypes()) {
                if (!"demo.Request".equals(type.getName())) continue;
                boolean fieldOkay = false;
                for (ValueDescriptor field : type.getFields()) {
                    if (!"bytes".equals(field.getName())) continue;
                    DataAmount amount = field.getAnnotation(DataAmount.class);
                    fieldOkay = "jdk.jfr.DataAmount".equals(
                            field.getContentType())
                            && amount != null
                            && DataAmount.BYTES.equals(amount.value());
                }
                check.schema = "Business request".equals(type.getLabel())
                        && fieldOkay;
            }
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                String name = event.getEventType().getName();
                if ("demo.Request".equals(name)) {
                    check.requests++;
                    if (!"test-001".equals(event.getString("requestId"))
                            || event.getLong("bytes") != 4096L
                            || !event.getBoolean("success")) {
                        throw new AssertionError("Wrong event payload");
                    }
                    check.stack = event.getStackTrace() != null
                            && !event.getStackTrace().getFrames().isEmpty();
                } else if ("demo.Detail".equals(name)) {
                    check.details++;
                }
            }
        }
        return check;
    }

    public static void main(String[] args) throws Exception {
        Path full = Files.createTempFile("jfr-full-", ".jfr");
        Path filtered = Files.createTempFile("jfr-filtered-", ".jfr");
        Path broken = Files.createTempFile("jfr-short-header-", ".jfr");
        broken.toFile().deleteOnExit();
        try {
            record(full, true);
            record(filtered, false);
            Check a = inspect(full);
            Check b = inspect(filtered);
            if (a.requests != 1 || a.details != 1
                    || !a.schema || !a.stack
                    || b.requests != 1 || b.details != 0
                    || !b.schema || !b.stack) {
                throw new AssertionError("Coverage test failed");
            }

            Files.write(broken, Arrays.copyOf(Files.readAllBytes(full), 16));
            boolean rejected = false;
            try (RecordingFile reader = new RecordingFile(broken)) {
                while (reader.hasMoreEvents()) reader.readEvent();
            } catch (IOException expected) {
                rejected = true;
            }
            if (!rejected) throw new AssertionError("Invalid JFR accepted");

            System.out.println("full.requests=" + a.requests);
            System.out.println("full.details=" + a.details);
            System.out.println("full.schemaValid=" + a.schema);
            System.out.println("full.stackPresent=" + a.stack);
            System.out.println("filtered.requests=" + b.requests);
            System.out.println("filtered.details=" + b.details);
            System.out.println("filtered.schemaValid=" + b.schema);
            System.out.println("filtered.fileReadable=true");
            System.out.println("truncatedHeaderRejected=" + rejected);
            System.out.println("allChecks=PASS");
        } finally {
            Files.deleteIfExists(full);
            Files.deleteIfExists(filtered);
            // Invalid-header input can remain briefly locked on Windows.
            // deleteOnExit handles it after the JVM exits.
        }
    }
}
```

### 8.2. Biên dịch và chạy

Lưu tệp chính xác tên `JfrCoverageDemo.java`, rồi chạy trong thư mục riêng:

```bash
java -version
javac --release 11 -encoding UTF-8 JfrCoverageDemo.java
java JfrCoverageDemo
```

**Output chính xác đã được kiểm thử** (sau khi biên dịch với `--release 11` trên JDK hiện đại):

```text
full.requests=1
full.details=1
full.schemaValid=true
full.stackPresent=true
filtered.requests=1
filtered.details=0
filtered.schemaValid=true
filtered.fileReadable=true
truncatedHeaderRejected=true
allChecks=PASS
```

**Đã thực thi kiểm thử thành công**. Toàn bộ assertions đều chạy trước dòng `allChecks=PASS`. Nếu metadata, count, payload, stack hoặc hành vi parse khác điều kiện fixture, chương trình ném exception thay vì trả kết quả giả.

**Phạm vi xác nhận:** `javac --release 11` chứng minh code sử dụng API/classfile target tương thích Java 11. Phiên thử đã chạy trên **một JDK hiện đại**; nếu hệ thống cam kết runtime Java 11, cần chạy riêng bằng **JDK 11 thực tế** trong CI. Không dùng thành công runtime của JDK mới làm chứng cứ đã chạy runtime JDK 11.

### 8.3. Vì sao file filtered vẫn đọc được?

Trong phương thức `record`, cả Request và Detail đều được tạo/commit. Nhưng:

```java
recording.enable(Detail.class)
        .withThreshold(Duration.ofDays(1));
```

làm **duration 15ms của Detail** không đáp ứng threshold. Vì vậy:

- `filtered.requests=1`: Request được lưu.
- `filtered.details=0`: Detail đã phát trong source nhưng bị lọc khỏi recording.
- `filtered.schemaValid=true`: metadata Request còn đúng.
- `filtered.fileReadable=true`: file vẫn hoàn toàn parse được.

**Điều KHÔNG thể làm:** chỉ nhìn `filtered.details=0` rồi kết luận “giai đoạn decode không xảy ra”. Trong fixture nó đã xảy ra và đã gọi `commit()`, nhưng bị threshold loại.

### 8.4. Vì sao metadata pass không đủ?

`full.schemaValid=true` và `filtered.schemaValid=true` kiểm tra:
- Type `demo.Request` có label `Business request`.
- Field `bytes` có content type `jdk.jfr.DataAmount`.
- Annotation xác định đơn vị `BYTES`.

Điều đó nói **schema Request chính xác**, không phải toàn bộ recording đầy đủ. File filtered vẫn mất Detail. Do vậy phải chạy **hai nhóm assertions độc lập**: schema và event coverage.

### 8.5. Vì sao stack được kiểm tra riêng?

`full.stackPresent=true` và trạng thái tương tự trong file filtered xác nhận Request có stack. Nhưng một event hợp lệ có thể có `getStackTrace()==null` khi stack không được bật hoặc dữ liệu đó không có. Trong production, **stack absent** có thể là một thiếu sót cho phân tích call path, nhưng không nhất thiết là missing event.

Không hardcode **số lượng stack frames** hoặc line numbers: chúng có thể thay đổi theo JDK, compiler optimization và call stack của runtime.

### 8.6. File hỏng mô phỏng điều gì?

Mã dùng:

```java
Files.write(broken,
        Arrays.copyOf(Files.readAllBytes(full), 16));
```

Tạo file chỉ giữ 16 byte đầu, không đủ một JFR header hoàn chỉnh. Trong fixture, `RecordingFile` từ chối bằng `IOException`, dẫn đến `truncatedHeaderRejected=true`. Đây là test **parser rejecting corrupted input**.

**Không suy rằng:** mọi truncation 16 bytes/16 KiB hoặc mọi tail corruption đều tạo **cùng loại exception**, hoặc rằng một file truncated có thể được “sửa” bằng việc thêm các bytes 0. JFR có chunks và metadata phụ thuộc cấu trúc; phục hồi cần xem tình trạng chunks còn hợp lệ và công cụ đúng version.

**Windows lưu ý:** với input JFR header hỏng, một đường parser có thể để file bị khóa ngắn hạn sau exception trong cùng process. Demo dùng `deleteOnExit()` cho file thử lỗi để tránh làm chương trình fail khi dọn tệp ngay lập tức; việc chạy trong thư mục test riêng và xóa sau process exit vẫn là thực hành tốt.

### 8.7. Vì sao không in file path, bytes hay events của JVM?

Program cố tình in những **invariants ổn định** và không assert:
- Kích thước file JFR chính xác.
- PID hoặc timestamp hiện tại.
- Thứ tự tất cả JVM background events.
- Count của `jdk.CPULoad`/GC/ThreadSleep mà fixture không kiểm soát.
- Nội dung stack frames/line numbers.
- Số bytes file bị buffer vào disk trước khi dump.

Đây là cách tốt để có test chạy lại đáng tin trên JDK 11+.

## 9. File JFR cắt/hỏng và khả năng phục hồi

Khi bạn có file `incident.jfr` không mở được, đừng ngay lập tức **sửa bytes** theo phỏng đoán. Hãy phân biệt:

1. File không tồn tại hoặc quyền đọc bị từ chối.
2. File có phần mở đầu không phải JFR/bị cắt trong header.
3. File có format/version không được parser JDK đang dùng hỗ trợ.
4. File chứa một số chunks hoàn chỉnh và một chunk cuối chưa hoàn chỉnh.
5. File đọc được nhưng **thiếu các chunks cũ** do retention hoặc snapshot chỉ lấy một khoảng.
6. JVM/process crash làm buffers/chunks chưa được flush.

**Hướng xử lý:** lấy thêm snapshot/backup nếu có, lưu bản gốc **read-only**, xem JDK/tool version, kiểm tra GC/JFR/JVM logs và repository còn các chunk files không.

### Công cụ `jfr` hỗ trợ xem file

Với file hợp lệ:

```bash
jfr summary incident.jfr
jfr metadata incident.jfr
jfr print --events demo.Request incident.jfr
```

- `summary`: các event types/occurrence counts tổng hợp được.
- `metadata`: schema/type/field annotations theo định dạng tool.
- `print`: instances thỏa event filter.

Một file không có `demo.Request` có thể vì ứng dụng không định nghĩa type đó. Đừng coi kết quả filter rỗng là parser lỗi.

### `jfr assemble` và chunk recovery

Những bản JDK có công cụ `jfr assemble` có thể **ghép các chunk JFR hoàn chỉnh** từ repository thành file phân tích được:

```bash
jfr assemble /path/to/jfr-repository recovered.jfr
```

**Điều kiện:** phải có các **chunk files tương thích và thực sự còn tồn tại**. Lệnh này không thể tạo lại event đã mất vì threshold, chưa commit, sampling hoặc bị ghi đè do retention. Các file chunk chưa hoàn chỉnh như `.part` có thể bị loại khi assemble theo hành vi tool/version.

Dùng `jfr help assemble` hoặc tài liệu CLI của JDK bạn đang sử dụng; không giả định một cú pháp hoặc khả năng cứu dữ liệu giống nhau trên mọi version. **Không ghi đè nguyên bản** trong lúc thử cứu dữ liệu.

### Bảo mật

JFR có thể chứa stack, class/method names, paths, thread names và custom event fields. Chỉ mở file từ **nguồn đáng tin**, giới hạn file size/IO/memory và tránh chia sẻ raw recordings có secrets/PII. Javadoc `RecordingFile` Java 11 khuyến cáo chỉ dùng files đáng tin. Không upload file incident chứa khách hàng lên công cụ bên thứ ba nếu chính sách không cho phép.

## 10. Phát hiện thiếu dữ liệu bằng business contract

Nếu một request đi qua ba stage A → B → C, custom events có thể ghi:

```text
demo.RequestStart(requestId=req-42)
demo.Stage(requestId=req-42, stage=A, seq=1)
demo.Stage(requestId=req-42, stage=B, seq=2)
demo.Stage(requestId=req-42, stage=C, seq=3)
demo.RequestEnd(requestId=req-42, success=true)
```

Đây là **một schema minh họa**, không phải tên events có sẵn trong JFR hay output của chương trình ở phần 8.

Nếu file chỉ có seq=1 và seq=3, có **lỗ hổng coverage** so với contract. Nhưng nguyên nhân có thể là:
- Event B không được commit vì code path/exception.
- B bị filtered theo threshold/setting.
- B được tạo ở **JVM khác**.
- Recording bị gián đoạn đúng lúc đó.
- B thực sự không chạy do branch business.
- Consumer filter không match schema/type B.
- Event nằm trong chunk đã bị retention loại.

**Nên tách hai câu hỏi:** “Có thiếu event theo **expected protocol** không?” và “Tại sao thiếu?”. Một gap sequence chứng minh thiếu so với contract **nếu protocol thực sự bảo đảm đủ các seq**, nhưng **không tự xác định root cause**.

### Provenance manifest hỗ trợ phân tích

Kèm file hoặc ghi trong hệ thống thu thập:

| Trường | Ví dụ | Vì sao |
| --- | --- | --- |
| Application/service version | `reservation-api 2.5.1` | Biết custom schema |
| JVM vendor/build | `OpenJDK ...` | Built-in JFR event schema có thể đổi |
| JVM/process identity | Instance/node/process identifier | Không ghép nhầm file |
| Recording ID/name | `Incident-2026-...` | Nhận diện snapshot |
| Start/stop/dump interval | UTC instants | Kiểm tra time coverage |
| Event settings | enabled/threshold/period/stack trace | Giải thích missing events |
| Retention | maxage/maxsize, disk mode | Biết dữ liệu cũ có thể bị loại |
| File size/hash | SHA-256 + byte length | Kiểm tra file bị sửa trong quá trình vận chuyển |
| Expected counts/IDs | Business-level counters | Đối chiếu coverage |
| Privacy classification | Data sensitivity / retention owner | Quyền và thời hạn lưu file |

**File hash chỉ kiểm tra tính toàn vẹn trong quá trình lưu/chuyển khi đã có hash đúng**. Nó không chứng minh events bị filter trước khi dump đã được ghi. Việc lưu expected business counters cũng cần tránh IDs mang dữ liệu nhạy cảm.

## 11. Kiểm tra recording time window, threshold và retention

### Thời gian

JFR event có `getStartTime()/getEndTime()` dưới dạng `Instant`. Khi phân tích:
- Lọc events đúng khoảng incident theo UTC.
- Phân biệt **event duration** với thời gian snapshot file được tạo.
- Event có thể bắt đầu trước dump và kết thúc sau một mốc filter; cần quy tắc **overlap** chứ không chỉ compare startTime.
- Khi ghép files từ nhiều JVM, clock skew có thể làm thứ tự hiển thị khác thứ tự nhân quả.
- Không dùng file order của chunks để kết luận logic nghiệp vụ chạy tuần tự.

### Retention

- `Recording.setMaxAge(Duration)`: giới hạn tuổi data ở disk repository.
- `Recording.setMaxSize(long)`: giới hạn dung lượng data lưu.
- `setToDisk(false)` có thể chỉ giữ dữ liệu bị giới hạn bởi memory buffers/rolling policies của runtime; không coi nó là khả năng giữ trọn lịch sử.
- Trong production, `maxage/maxsize` là thiết kế resource, không phải lời hứa “đầy đủ 100%”.
- Nếu incident xảy ra ngoài retained window, cần tìm những logs/metrics khác chứ không thể suy ra từ file.

### Threshold/period/stack

- Type enabled nhưng threshold lớn → nhiều duration events không ghi.
- Periodic event có tần suất lấy mẫu giới hạn → không quan sát mọi instant.
- Stack trace disabled → events vẫn có thể có payload nhưng thiếu call path.
- Thay đổi settings trong lúc recording chạy có thể tạo vùng thời gian có mức chi tiết khác nhau.
- Nhiều recordings cùng một JVM có settings riêng, cần lưu context và hiểu được các cấu hình đang có hiệu lực.
- Trong perf test, tăng detail/stack có overhead và có thể đổi chính latency muốn đo.

**Không dùng cùng một tiêu chí completeness cho tất cả types.** Với `demo.Request` mỗi request cần event, ta có thể so business counters. Với `jdk.ExecutionSample`, chỉ nên kiểm tra sample coverage/period và statistical sufficiency, không so samples với số method calls như thể 1:1.

## 12. Tối ưu recording mà không đánh mất bằng chứng quan trọng

Mục tiêu không phải “bật tất cả events, threshold 0, stack full vô hạn”; đó là cách dễ tăng CPU, disk, overhead và tăng rủi ro lộ dữ liệu.

Một chiến lược theo tầng:

### Tầng 1 — Baseline ít tốn kém

- Chọn settings phù hợp như `default`.
- Giữ những JVM health/GC/CPU events cần theo dõi.
- Thu business events tần suất hợp lý, ít field và hạn chế cardinality.
- Có retention/disk quota rõ ràng.
- Ghi metadata contract tối thiểu.

### Tầng 2 — Incident sampling / ngưỡng

- Khi có triệu chứng, bật thêm event types/threshold phục vụ câu hỏi hiện tại.
- Với lock/I/O duration, dùng threshold có ý nghĩa để tránh chi phí volume quá lớn.
- Với request tail latency, gắn ID an toàn vào **custom slow-request events**.
- Với CPU sampling, hiểu đó là **statistical evidence**.
- Với stack trace, bật cho loại event và giai đoạn thật sự cần.

### Tầng 3 — Chẩn đoán sâu có thời hạn

- Dùng `profile` hoặc cấu hình cụ thể trong thời gian ngắn.
- Theo dõi overhead của recorder (CPU/disk/memory) so với baseline.
- Giữ raw file theo policy, giới hạn quyền truy cập.
- Sau incident, trở lại cấu hình phù hợp.
- Thực hiện QA về file integrity và coverage trước khi dùng kết quả.

### Tối ưu code producer

Có thể tránh tính payload đắt tiền khi event bị tắt/không qua threshold:

```java
Request event = new Request();
event.begin();
doOperation();
event.end();

if (event.shouldCommit()) {
    event.requestId = safeId;
    event.bytes = computeObservedBytes();
    event.success = true;
    event.commit();
}
```

Đây là **đoạn minh họa**, với `doOperation/safeId/computeObservedBytes` do ứng dụng định nghĩa. Không dùng `shouldCommit()` để thay logic ghi audit bắt buộc: JFR là hệ thống chẩn đoán hiệu năng, không phải nguồn sự thật duy nhất cho compliance/audit/business transactions.

**Cẩn trọng:** threshold cao có thể tạo khoảng coverage thiếu nếu hệ thống phân tích mong đợi event cho mọi request. Khi muốn đầy đủ 100% business-level audit, dùng một hệ thống transactional/logging đáng tin với semantics phù hợp, không chỉ custom JFR events.

## 13. Lỗi thường gặp và cách xử lý

| Nhận định/lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “File parse được nên recording đầy đủ” | Parser không kiểm chứng tất cả events mong đợi | Định nghĩa coverage contract và expected counts |
| “Type có trong metadata nên event đã xảy ra” | Type descriptor khác event instance | Đếm `RecordedEvent` cùng tên |
| “Không có event thì không có hoạt động” | Có thể disabled/threshold/period/out-of-window | Kiểm tra settings và nguồn ngoài |
| “`commit()` xong chắc chắn có event” | Settings có thể lọc, recording chưa chạy | Enable/threshold/interval QA |
| “Stack null nghĩa là event missing” | Stack có thể disabled | Phân biệt payload và stack coverage |
| “`getThread()==null` nghĩa file lỗi” | JVM-wide events có thể không có thread | Null-safe parsing |
| “`hasField` không cần vì schema luôn ổn định” | JDK/app versions đổi schema | Kiểm tra metadata/version |
| “GC event type tồn tại thì GC đã pause” | Metadata không phải occurrence | Xem GC pause events thực và durations |
| “CPU sample count = method call count” | Sampling không phải full trace | Dùng thống kê, không đếm exact |
| “Không thấy event là recording hỏng” | File có thể hợp lệ nhưng filter | Phân loại readable-incomplete |
| “File hỏng header thì phục hồi bằng bytes 0” | JFR binary/chunk metadata phức tạp | Bảo toàn file gốc, tìm chunks/backup |
| “Mọi truncated file ném cùng lỗi” | Lỗi phụ thuộc nơi bị cắt/tool | Chỉ assert fixture cụ thể |
| “`jfr assemble` tạo lại events bị threshold lọc” | Chỉ ghép chunks còn tồn tại | Không hứa phục hồi dữ liệu chưa bao giờ ghi |
| “Không có JFR vì recording đã dump” | Dump không tự stop | Kiểm tra lifecycle và interval |
| “maxage=5m thì luôn có đủ 5 phút” | maxsize, churn và chunks có thể làm coverage ngắn hơn | Theo dõi thực tế retention |
| “File lớn cứ readAllEvents” | Có thể OOM consumer | Streaming bằng `hasMoreEvents/readEvent` |
| “Type ID số giống nhau ở mọi JVM” | Type IDs có thể thay đổi | Dùng event name/schema |
| “Có stack là biết toàn distributed request” | Stack là call path một thread/event | Dùng explicit trace IDs/context |
| “JFR luôn flush hết khi JVM crash” | In-memory data/chunks có thể mất | Đối chiếu repository/logs |
| “Bật tất cả stack/events càng tốt” | CPU/disk/privacy overhead | Cấu hình theo giả thuyết và ngân sách |
| “JFR thay được business audit trail” | JFR không có semantics transactional exactly-once | Dùng audit/log phù hợp |
| “Thấy correlation thì chắc nguyên nhân” | Cùng thời gian không chứng minh cause | Đối chiếu thread/stack/metrics/traces |

## 14. Quy trình điều tra một bản ghi JFR nghi không đầy đủ

**Bước 1 — Xác định đúng nguồn.** Đúng service JVM, process, node/container, JDK build, khoảng incident? Có thể bạn đang mở file của replica khác.

**Bước 2 — Xác minh định dạng.** Dùng `jfr summary` hoặc `RecordingFile`. Nếu parse lỗi, lưu original, không viết đè và tìm repository chunks/backup. Không mở file không đáng tin.

**Bước 3 — Xem metadata.** `jfr metadata`/`readEventTypes()`; có expected types, fields và units không? Chú ý JDK/vendor/app schema versions.

**Bước 4 — Đếm instances.** Lọc theo `getEventType().getName()`, time window và correlation IDs nếu có. Lập expected/observed table.

**Bước 5 — Kiểm tra settings.** Enabled, threshold, period, stack setting, recording start/stop, maxage/maxsize, disk mode, JFC profile.

**Bước 6 — Phân biệt thiếu schema và thiếu occurrence.** Cùng một type có thể có metadata nhưng 0 events; hai lỗi cần hướng sửa khác nhau.

**Bước 7 — Kiểm tra writer/producer.** Custom Event có được begin/end/commit? Exception path có bỏ commit? IsEnabled/shouldCommit? Các thread/JVM khác có phát event tương ứng?

**Bước 8 — Kiểm tra gaps.** Timestamps, sequence numbers, request IDs, chunk intervals; sự kiện có thể bị lọc, retention hoặc crash. Đánh dấu dữ liệu không đủ, không tự điền 0.

**Bước 9 — Đối chiếu hệ thống ngoài JFR.** Tracing, structured logs, counters, metrics, GC logs, incident timeline. JFR là một nguồn bằng chứng, không phải nguồn duy nhất.

**Bước 10 — Chốt kết luận có độ tin cậy.** Ghi observed facts, giả thuyết missing, những settings đã xác minh và giới hạn dữ liệu. Nếu có file không đầy đủ, nêu rõ **câu hỏi nào vẫn trả lời được** và câu hỏi nào phải để UNKNOWN.

**Bước 11 — Tối ưu có kiểm soát.** Thay threshold/period/stack chỉ khi biết loại sự kiện nào cần; đo lại overhead và coverage trong load test.

**Bước 12 — Bảo mật và retention.** File .jfr có thể chứa thông tin nội bộ và nhạy cảm; phân quyền, xóa bản test/backup theo policy, lưu version/hash/traces cần thiết cho tái hiện.

## 15. Chiến lược kiểm thử tự động và CI

Cần có nhiều cấp test, thay vì chỉ assert `Files.exists("result.jfr")`:

### A. Positive recording

- Custom event type được enable với threshold 0.
- Producer gọi `commit()`.
- File parse hoàn toàn.
- Metadata label/units đúng contract.
- Đúng event count và raw field values.
- Stack hiện diện nếu fixture yêu cầu.
- Thời gian nằm trong recording interval.

### B. Valid file nhưng filtered event

- Event type Detail được enable với threshold cực cao.
- Producer vẫn commit Detail.
- Recording được dump thành file JFR hợp lệ.
- Business Request vẫn ghi.
- Detail count bằng 0.
- Consumer báo **READABLE_INCOMPLETE_COVERAGE** nếu Detail là required theo contract.
- Không báo `INVALID_OR_UNREADABLE`.

### C. Binary corrupted input

- Tạo file truncated header trong sandbox.
- `RecordingFile` phải từ chối theo fixture.
- Code không biến IOException thành danh sách events rỗng.
- Không sửa file gốc hoặc giả mạo phần dữ liệu thiếu.
- Test cleanup phải hoạt động trên Windows/Linux khi parser mở file lỗi.

### D. Schema mismatch

- Thay tên field hoặc loại field ở phiên bản event mới (test riêng có chủ đích).
- Parser phải phát hiện required field không tồn tại.
- Không silently substitute 0/empty.
- Nếu field optional, consumer có chính sách default và metadata validation.
- Không gán sai đơn vị bytes/milliseconds/percentage.

### E. Coverage/time-window test

- Ghi event trước start, trong khoảng recording, sau stop — chỉ yêu cầu event được tạo đúng trong window.
- Nếu recording áp `maxage/maxsize`, đối chiếu được retention window thực.
- Với multiple JVMs, không join theo thread ID đơn thuần.
- Với async, truyền correlation ID qua custom stages; đừng kỳ vọng JVM built-in events tự biết request ID.

### F. Performance test

- Đo overhead bật/tắt stack, threshold, event types dưới cùng workload.
- Theo dõi CPU, RSS, file size, disk IO và dropped event signals nếu runtime cung cấp.
- Đảm bảo chính việc thu JFR không làm thay đổi P99 quá nhiều so với mục tiêu đo.
- Khi load cao, kiểm tra percentiles/coverage thay vì tin mỗi average.

### G. Cross-JDK test

- Compile target `--release 11` và chạy runtime JDK 11 nếu đó là baseline hỗ trợ.
- Chạy thêm trên JDK production đang dùng.
- Không dựa vào events/JFR tools chỉ có trên bản mới nếu mục tiêu là Java 11.
- Built-in event field schemas có thể khác, nên kiểm tra trước.
- Dữ liệu binary JFR mới có thể không đọc được bằng reader quá cũ; xác minh compatibility theo producer/consumer versions.

## 16. Bài tập thực hành

**Bài 1.** `readEventTypes()` có type `demo.Detail`. Có đủ để kết luận Detail đã được ghi ít nhất một lần? **Không**. Cần đọc instances và đếm.

**Bài 2.** File có 1 Request và 0 Detail, parser không báo lỗi. Có chắc file binary hỏng? **Không**. Có thể Detail bị threshold/disabled hoặc không commit.

**Bài 3.** Code gọi `detail.commit()` nhưng recording dùng threshold 1 ngày, event chỉ 15ms. Kết quả? **Không ghi Detail** trong fixture.

**Bài 4.** `full.schemaValid=true` có chứng minh file đủ mọi business events không? **Không**. Schema validation độc lập coverage.

**Bài 5.** `getStackTrace()==null` có nghĩa toàn event không có? **Không**. Event có thể được ghi nhưng stack không được thu.

**Bài 6.** `getLong("bytes")` trên event type không có `bytes` field có an toàn không? **Không**; kiểm tra type/hasField/metadata.

**Bài 7.** `@DataAmount(BYTES)` có tự convert giá trị bits sang bytes không? **Không**.

**Bài 8.** File bị cắt còn 16 bytes đầu, parser từ chối. Có thể sửa bằng append 0 và tin dữ liệu không mất? **Không**; tìm snapshot hoặc chunks còn hợp lệ.

**Bài 9.** Có nên gọi `RecordingFile.readAllEvents` trên file hàng GB không? **Không**; dùng streaming/aggregation.

**Bài 10.** Recording có `maxage=5m` và `maxsize` rất nhỏ. Có chắc đủ toàn bộ 5 phút events không? **Không**. Retention bị ảnh hưởng bởi size và volume.

**Bài 11.** Request đã kết thúc trước `recording.start()`. Có thể tìm Request trong file này? **Không**, trừ khi có recording khác bắt đầu sớm hơn.

**Bài 12.** File có metadata event nhưng 0 instances. Có thể coi không có hoạt động trong ứng dụng? **Không**.

**Bài 13.** `jfr assemble` phục hồi được một event chưa bao giờ được ghi do threshold không? **Không**.

**Bài 14.** `JFR.dump` có dừng recording không? **Không**. `JFR.stop` mới kết thúc.

**Bài 15.** Một custom event có requestId từ service A, built-in `jdk.ThreadSleep` có sẵn requestId đó không? **Không**. Cần thread/time và context tự truyền.

**Bài 16.** Nếu CPU sampling không ghi method X, có thể kết luận X chưa bao giờ chạy? **Không**, sampling không đếm toàn bộ.

**Bài 17.** Khi schema đổi từ `bytes` sang `payloadBits` nhưng dashboard vẫn đọc bytes, nên làm gì? **Phát hiện SCHEMA_MISMATCH**, xử lý version và unit rõ ràng.

**Bài 18.** Tại sao một recording sau crash có thể thiếu events cuối? Dữ liệu có thể còn trong buffers/chunks chưa hoàn tất.

**Bài 19.** Vì sao không nên bật full stack vô hạn cho mọi event production? CPU/disk/overhead/privacy và retention pressure.

**Bài 20.** Cần xác nhận gì trước khi khẳng định `0` GC events nghĩa JVM không GC? **Đúng JVM, recording interval, enabled events, settings, thresholds, retention và dữ liệu file**.

### Checklist trước khi tin tưởng bản ghi JFR

1. Đúng JDK build và JVM/process/node/time window?
2. File parse được và không có IO/corruption errors?
3. Type metadata/fields/units đúng contract?
4. Event instance counts và IDs được đếm từ file, không suy từ type list?
5. Enabled/threshold/period/stack settings được xác minh?
6. Recording start/stop/dump và retention window hợp lệ?
7. Có kiểm tra `getThread()/getStackTrace()` null?
8. Cần xử lý missing events như UNKNOWN thay vì no-activity?
9. Có phương án với file hỏng/header truncated?
10. Có kiểm soát readAllEvents vs streaming, memory/IO quota?
11. Có đối chiếu external counters/traces/business events?
12. Có kiểm tra writer commit/failure paths?
13. Có theo dõi dropped/lost data signals nếu runtime hỗ trợ?
14. Có xử lý nhiều JVM/cross-version và schema evolution?
15. Có thu JFR với overhead/bảo mật chấp nhận được?
16. Có giữ file gốc, manifest và provenance cho incident?
17. Đã kiểm thử trên runtime Java 11 thật nếu app cam kết Java 11?

## 17. Tài liệu tham khảo chính thức

- [Oracle Java SE 11 — jdk.jfr package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): custom events, metadata, recording settings.
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): enable/start/stop/dump, maxage/maxsize/toDisk.
- [Oracle Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): threshold, stack, period.
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): begin/end/commit/shouldCommit.
- [Oracle Java SE 11 — EventType](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html): event names/labels/categories/field metadata.
- [Oracle Java SE 11 — ValueDescriptor](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html): field types/content types/annotations.
- [Oracle Java SE 11 — DataAmount](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/DataAmount.html): BYTES/BITS content type.
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): readEventTypes, hasMoreEvents/readEvent, readAllEvents, IO/format errors and trust warning.
- [Oracle Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): start/end/duration/thread/stack/fields.
- [Oracle Java SE 11 — RecordedObject](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): hasField/getString/getLong và typed field access.
- [Oracle Java SE 25 — JFR consumer package](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html): API đọc recording vẫn hiện hành.
- [Oracle Java SE 25 — jfr command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): summary/metadata/print/assemble/disassemble, phiên bản tool hiện đại.
- [Dev.java — JFR parse/print/chunk tools](https://dev.java/learn/jvm/monitoring-troubleshooting/monitoring/jfr/): mô tả chunk files, assemble và giới hạn các fragments không hoàn chỉnh.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR trong OpenJDK từ Java 11.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): đọc event timeline, stack, CPU, GC và schema.
- [Oracle Java SE 24 — RecordingFile](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): tham khảo điểm khác biệt API mới (`write(...)` chỉ có từ Java 19, không dùng ở ví dụ Java 11).

**Kết luận:** **JFR file hợp lệ ≠ event đủ ≠ metadata đúng ≠ coverage đủ cho kết luận**. Muốn dùng JFR để kiểm thử/tối ưu hay điều tra incident, cần xác minh độc lập **cấu trúc file, schema, event instances, settings và time window**. Một event bị threshold lọc tạo ra file hoàn toàn hợp lệ nhưng thiếu bằng chứng; một file header bị cắt có thể không đọc được. Hãy xây coverage contract, kiểm tra bằng `RecordingFile/EventType/ValueDescriptor`, đối chiếu producer và dữ liệu ngoài JFR, đồng thời quản lý sampling, retention, overhead và quyền riêng tư.