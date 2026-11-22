# Timestamp, Duration và well-known types

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **Timestamp** biểu diễn một thời điểm tuyệt đối với **Duration** biểu diễn một khoảng thời gian.
- Khai báo và import hai well-known type này trong schema proto3.
- Chuyển đổi chính xác giữa Protobuf và Java **Instant**, **java.time.Duration**.
- Hiểu giới hạn, độ chính xác và quy tắc chuẩn hóa seconds/nanos.
- Nhận biết cách ProtoJSON biểu diễn Timestamp và Duration.
- Chọn well-known type phù hợp và tránh dùng chúng sai ngữ nghĩa trong hợp đồng Spring gRPC.

## 1. Well-known types là gì?

Protocol Buffers cung cấp một tập message chuẩn có sẵn, gọi là **well-known types (WKT)**. Chúng mô tả những khái niệm thường gặp như thời điểm, khoảng thời gian, dữ liệu động, trường cần cập nhật hoặc một giá trị bất kỳ. Các kiểu này có schema chuẩn, lớp Java tương ứng và quy tắc ProtoJSON được định nghĩa rõ.

Hai kiểu thời gian thường dùng nhất:

- **google.protobuf.Timestamp**: một thời điểm cụ thể trên dòng thời gian, tính từ Unix epoch.
- **google.protobuf.Duration**: một khoảng thời gian có thể dương, âm hoặc bằng không.

Trong dịch vụ **SPRING_GRPC**, dùng chúng để trao đổi thời điểm tạo đơn, thời hạn hiệu lực, thời gian xử lý hoặc khoảng chờ cấu hình. Dùng kiểu chuẩn giúp các client Java và client ngôn ngữ khác thống nhất cách biểu diễn.

Một số WKT khác:

| Kiểu | Mục đích |
| --- | --- |
| **google.protobuf.Empty** | Message không có field, thường dùng khi RPC không cần request/response data. |
| **google.protobuf.FieldMask** | Chỉ ra các field cần đọc hoặc cập nhật. |
| **google.protobuf.Any** | Chứa một message Protobuf có type URL. |
| **google.protobuf.Struct**, **Value**, **ListValue** | Biểu diễn dữ liệu có cấu trúc động gần với JSON. |
| **google.protobuf.StringValue**, **BoolValue** và các wrapper khác | Bao một scalar; thường gặp trong schema cũ trước khi proto3 optional phổ biến. |

WKT không phải một kiểu duy nhất có cùng cách serialize. Mỗi loại có schema và quy tắc JSON riêng. Bài này tập trung vào Timestamp và Duration.

## 2. Import Timestamp và Duration trong .proto

Các định nghĩa chuẩn được cung cấp trong thư viện Protobuf. Import đúng file rồi dùng tên đầy đủ:

~~~proto
syntax = "proto3";

package learning.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message OrderEvent {
  string order_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
  google.protobuf.Duration processing_time = 3;
}
~~~

Không tự định nghĩa message riêng có tên Timestamp hoặc Duration để thay thế WKT. Dùng kiểu chuẩn giúp công cụ sinh mã, runtime và ProtoJSON hiểu đúng ngữ nghĩa.

Trong Java, hai lớp tương ứng là:

- **com.google.protobuf.Timestamp**
- **com.google.protobuf.Duration**

Các tiện ích chuyển đổi và định dạng nằm trong artifact **protobuf-java-util**, ví dụ **com.google.protobuf.util.Timestamps**, **Durations** và **JsonFormat**. Phiên bản thư viện này cần tương thích với phiên bản Protobuf runtime được dự án sử dụng.

## 3. Timestamp biểu diễn một thời điểm tuyệt đối

Timestamp biểu diễn số giây và phần nano giây tính từ **Unix epoch: 1970-01-01T00:00:00Z**. Nó không lưu múi giờ địa phương, tên vùng như **Asia/Ho_Chi_Minh**, hoặc cách người dùng nhìn đồng hồ.

Message có hai field:

| Field | Ý nghĩa |
| --- | --- |
| **seconds** | Số giây tính từ Unix epoch. |
| **nanos** | Phần nano giây bổ sung, từ 0 đến 999.999.999. |

Timestamp có độ chính xác tới **nano giây**. Ví dụ, **1970-01-01T00:00:01.250Z** tương ứng **seconds = 1**, **nanos = 250000000**.

Giá trị âm cũng được chuẩn hóa với nanos không âm. Ví dụ thời điểm nửa giây trước epoch:

~~~text
seconds = -1
nanos   = 500000000
~~~

Hai thành phần kết hợp thành **-0,5 giây**. Không biểu diễn trường hợp này bằng **seconds = 0**, **nanos = -500000000**; quy tắc Timestamp yêu cầu nanos nằm trong khoảng không âm.

### Phạm vi hợp lệ

Timestamp hỗ trợ khoảng từ **0001-01-01T00:00:00Z** đến **9999-12-31T23:59:59.999999999Z**:

- **seconds**: từ **-62.135.596.800** đến **253.402.300.799**.
- **nanos**: từ **0** đến **999.999.999**.

Không phải mọi giá trị long đều là một Timestamp hợp lệ. Khi dữ liệu có thể đến từ client ngoài, cần kiểm tra phạm vi thay vì chỉ tin rằng builder đã được tạo thành công.

## 4. Duration biểu diễn một khoảng thời gian

Duration mô tả lượng thời gian giữa hai thời điểm hoặc một khoảng chờ/thời hạn được cấu hình. Nó không gắn với ngày bắt đầu cụ thể.

Duration cũng có hai field:

| Field | Ý nghĩa |
| --- | --- |
| **seconds** | Phần giây có dấu. |
| **nanos** | Phần nano giây có dấu, cùng dấu với seconds hoặc một trong hai bằng 0. |

Ví dụ:

| Khoảng thời gian | seconds | nanos |
| --- | ---: | ---: |
| **2,5 giây** | 2 | 500.000.000 |
| **2 giây** | 2 | 0 |
| **-1,5 giây** | -1 | -500.000.000 |
| **-0,5 giây** | 0 | -500.000.000 |
| **0 giây** | 0 | 0 |

Quy tắc cùng dấu giúp biểu diễn Duration theo dạng chuẩn hóa. Không đặt **seconds = 1** và **nanos = -500000000**; đó không phải biểu diễn chuẩn hợp lệ của 0,5 giây.

Duration hỗ trợ phạm vi xấp xỉ **±10.000 năm**:

- **seconds**: từ **-315.576.000.000** đến **315.576.000.000**.
- **nanos**: từ **-999.999.999** đến **999.999.999**.
- **seconds** và **nanos** phải cùng dấu, trừ trường hợp một thành phần bằng 0.

Duration không phải lịch ngày/tháng. Một tháng có thể có 28, 29, 30 hoặc 31 ngày; vì vậy không quy đổi một tháng thành một Duration cố định nếu nghiệp vụ thực sự nói về tháng lịch.

## 5. Khai báo và đọc các field thời gian

Timestamp và Duration là **message field**, nên có explicit presence trong proto3 mà không cần nhãn optional:

~~~proto
import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message Job {
  string job_id = 1;
  google.protobuf.Timestamp started_at = 2;
  google.protobuf.Timestamp finished_at = 3;
  google.protobuf.Duration timeout = 4;
}
~~~

Java sinh các phương thức như:

- **hasStartedAt()** và **getStartedAt()**.
- **hasFinishedAt()** và **getFinishedAt()**.
- **hasTimeout()** và **getTimeout()**.

Khi field chưa được đặt, getter trả default instance. Default Timestamp là epoch (**seconds = 0**, **nanos = 0**); default Duration là khoảng 0 giây. Do đó, không dùng giá trị getter để suy ra field có được gửi hay không:

~~~java
Job job = Job.newBuilder().setJobId("job-42").build();

System.out.println(job.hasStartedAt()); // false
System.out.println(job.getStartedAt().getSeconds()); // 0
System.out.println(job.hasTimeout()); // false
System.out.println(job.getTimeout().getSeconds()); // 0
~~~

Nếu ứng dụng cần phân biệt “chưa cung cấp thời điểm” với “thời điểm epoch”, hãy kiểm tra **hasStartedAt()**. Nếu cần phân biệt “không cấu hình timeout” với “timeout bằng 0”, kiểm tra **hasTimeout()**.

## 6. Chuyển đổi Timestamp với java.time.Instant

**java.time.Instant** cũng biểu diễn một thời điểm tuyệt đối theo Unix epoch. Đây là kiểu Java phù hợp để chuyển đổi với **google.protobuf.Timestamp**.

### Từ Instant sang Timestamp

~~~java
import com.google.protobuf.Timestamp;
import com.google.protobuf.util.Timestamps;
import java.time.Instant;

Instant instant = Instant.parse("2026-11-19T08:30:15.123456789Z");

Timestamp timestamp = Timestamp.newBuilder()
    .setSeconds(instant.getEpochSecond())
    .setNanos(instant.getNano())
    .build();

if (!Timestamps.isValid(timestamp)) {
    throw new IllegalArgumentException("Timestamp outside Protobuf range");
}
~~~

**Instant.getNano()** trả phần nano trong giây, không phải tổng số nano từ epoch. Dùng **getEpochSecond()** và **getNano()** giữ được độ chính xác tới nano giây.

### Từ Timestamp sang Instant

~~~java
Instant restored = Instant.ofEpochSecond(
    timestamp.getSeconds(),
    timestamp.getNanos());
~~~

Có thể dùng tiện ích **Timestamps.fromMillis(...)** và **Timestamps.toMillis(...)** khi hệ thống chỉ cần độ chính xác mili giây:

~~~java
Timestamp fromMillis = Timestamps.fromMillis(
    System.currentTimeMillis());

long epochMillis = Timestamps.toMillis(fromMillis);
~~~

Các hàm millisecond làm mất phần độ chính xác nhỏ hơn một mili giây. Nếu dữ liệu cần giữ nano giây, dùng chuyển đổi seconds/nanos trực tiếp.

### Timestamp không phải LocalDateTime

**LocalDateTime** không chứa múi giờ hoặc offset, nên không thể tự xác định một thời điểm tuyệt đối. Nếu đầu vào là thời gian địa phương, cần biết múi giờ hoặc offset rồi chuyển thành Instant:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.of(2026, 11, 19, 15, 30);
Instant instant = local.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
~~~

Timestamp chỉ lưu kết quả thời điểm tuyệt đối. Nếu nghiệp vụ cần “15:30 giờ địa phương mỗi ngày” hoặc một lịch theo vùng, hãy lưu thêm timezone ID và quy tắc lịch; một Timestamp đơn lẻ không thể giữ ý nghĩa đó.

## 7. Chuyển đổi Duration với java.time.Duration

Java **java.time.Duration** biểu diễn khoảng thời gian với giây và nano. Có thể dùng **Durations** để chuyển đổi các giá trị phổ biến:

~~~java
import com.google.protobuf.util.Durations;

com.google.protobuf.Duration timeout = Durations.fromMillis(1500);
long timeoutMillis = Durations.toMillis(timeout);
~~~

**fromMillis()** phù hợp khi đầu vào chỉ có độ chính xác mili giây. Nếu cần giữ nano giây, phải chú ý khác biệt cách chuẩn hóa số âm giữa Java và Protobuf.

### Chuẩn hóa Duration âm

Java **java.time.Duration** lưu giây theo hướng làm tròn xuống và phần nano không âm. Ví dụ **java.time.Duration.ofMillis(-500)** có:

~~~java
java.time.Duration javaDuration =
    java.time.Duration.ofMillis(-500);

System.out.println(javaDuration.getSeconds()); // -1
System.out.println(javaDuration.getNano());    // 500000000
~~~

Protobuf Duration yêu cầu seconds và nanos cùng dấu. Vì vậy, không sao chép trực tiếp hai giá trị trên vào message Protobuf. Chuyển đổi chính xác:

~~~java
import com.google.protobuf.util.Durations;

static com.google.protobuf.Duration toProtoDuration(
        java.time.Duration value) {

    long seconds = value.getSeconds();
    int nanos = value.getNano();

    // Java biểu diễn -0.5s là (-1s, +500ms);
    // Protobuf biểu diễn là (0s, -500ms).
    if (seconds < 0 && nanos > 0) {
        seconds += 1;
        nanos -= 1_000_000_000;
    }

    com.google.protobuf.Duration result =
        com.google.protobuf.Duration.newBuilder()
            .setSeconds(seconds)
            .setNanos(nanos)
            .build();

    if (!Durations.isValid(result)) {
        throw new IllegalArgumentException(
            "Duration outside Protobuf range");
    }
    return result;
}
~~~

Chiều ngược lại có thể dùng **java.time.Duration.ofSeconds(seconds, nanos)**:

~~~java
static java.time.Duration toJavaDuration(
        com.google.protobuf.Duration value) {
    if (!com.google.protobuf.util.Durations.isValid(value)) {
        throw new IllegalArgumentException("Invalid Protobuf Duration");
    }
    return java.time.Duration.ofSeconds(
        value.getSeconds(), value.getNanos());
}
~~~

**Duration.ofSeconds(long, long)** tự chuẩn hóa phần nano khi cần. Việc kiểm tra **Durations.isValid()** trước khi chuyển giúp từ chối message ngoài phạm vi hoặc sai dấu.

## 8. ProtoJSON biểu diễn Timestamp và Duration

ProtoJSON dùng biểu diễn đặc biệt cho hai WKT này:

- **Timestamp** được biểu diễn thành chuỗi RFC 3339.
- **Duration** được biểu diễn thành chuỗi có hậu tố **s**.

Ví dụ message:

~~~proto
message Job {
  google.protobuf.Timestamp started_at = 1;
  google.protobuf.Duration timeout = 2;
}
~~~

JSON tương ứng:

~~~json
{
  "startedAt": "2026-11-19T08:30:15.123456789Z",
  "timeout": "1.5s"
}
~~~

Timestamp JSON có thể nhận offset hợp lệ, nhưng khi xuất chuẩn ProtoJSON sẽ dùng UTC với hậu tố **Z**. Phần giây lẻ có thể dùng 3, 6 hoặc 9 chữ số thập phân tùy độ chính xác cần biểu diễn.

Duration JSON dùng chuỗi như:

- **"3s"** cho 3 giây.
- **"1.5s"** cho 1,5 giây.
- **"-0.5s"** cho nửa giây âm.
- **"0s"** cho khoảng bằng không.

Không dùng JSON number như **1500** để thay cho Duration trong ProtoJSON. Đơn vị và hậu tố **s** là một phần của định dạng.

Java có thể in và parse bằng **JsonFormat**:

~~~java
import com.google.protobuf.util.JsonFormat;

String json = JsonFormat.printer().print(job);

Job.Builder builder = Job.newBuilder();
JsonFormat.parser().merge(json, builder);
Job parsed = builder.build();

System.out.println(parsed.hasStartedAt());
System.out.println(parsed.getTimeout().getSeconds());
~~~

Nếu dùng Jackson hoặc serializer JSON tổng quát khác, không mặc định rằng kết quả tuân theo ProtoJSON. Dùng **JsonFormat** khi trao đổi JSON theo hợp đồng Protobuf.

## 9. WKT khác và cách chọn đúng kiểu

Timestamp và Duration không thay thế mọi kiểu ngày giờ hoặc mọi cấu trúc động. Một số lựa chọn:

| Nhu cầu | Kiểu phù hợp | Ghi chú |
| --- | --- | --- |
| Một thời điểm tuyệt đối | **Timestamp** | UTC instant, không lưu timezone ID. |
| Khoảng thời gian hoặc timeout cấu hình | **Duration** | Số giây/nano, không phải tháng lịch. |
| Một ngày lịch, không có giờ | Message ngày chuyên biệt, ví dụ **google.type.Date** nếu hệ sinh thái cung cấp | Không ép ngày sinh thành Timestamp lúc nửa đêm nếu không có ý nghĩa thời điểm. |
| Một lịch địa phương có múi giờ | Message chứa local date/time và timezone ID | Cần giữ quy tắc múi giờ để tính thời điểm. |
| Thời gian gọi RPC phải kết thúc trước hạn | **io.grpc.Deadline** ở API gRPC | Duration có thể cấu hình khoảng chờ, nhưng không thay thế deadline gắn với call. |
| Đo thời gian chạy trong cùng tiến trình | **System.nanoTime()** | Dùng đồng hồ monotonic để đo elapsed time; không dùng wall-clock Timestamp. |
| Cập nhật một phần message | **FieldMask** | Liệt kê các đường dẫn field cần cập nhật. |
| Payload message có kiểu chưa biết lúc biên dịch | **Any** | Kèm type URL và bytes của message được đóng gói. |
| Request/response không có dữ liệu | **Empty** | Message chuẩn không có field. |

Đặc biệt, **Duration không phải deadline**. Trong client gRPC, **io.grpc.Deadline** gắn thời điểm hết hạn vào một RPC cụ thể. Một field Duration trong request có thể là cấu hình timeout nghiệp vụ, nhưng server vẫn phải quyết định cách áp dụng và giới hạn nó.

## 10. Ví dụ hợp đồng và xử lý thời gian trong Spring gRPC

Một event có thời điểm phát sinh và khoảng thời gian xử lý:

~~~proto
syntax = "proto3";

package learning.audit.v1;

option java_package = "com.example.audit.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message RecordEventRequest {
  string event_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
  google.protobuf.Duration processing_time = 3;
}
~~~

Trong Java, ứng dụng có thể kiểm tra presence và validity trước khi lưu:

~~~java
import com.example.audit.v1.RecordEventRequest;
import com.google.protobuf.util.Timestamps;
import com.google.protobuf.util.Durations;

void validate(RecordEventRequest request) {
    if (request.getEventId().isBlank()) {
        throw new IllegalArgumentException("event_id is required");
    }

    if (!request.hasOccurredAt()) {
        throw new IllegalArgumentException("occurred_at is required");
    }
    if (!Timestamps.isValid(request.getOccurredAt())) {
        throw new IllegalArgumentException("occurred_at is invalid");
    }

    if (request.hasProcessingTime()
            && !Durations.isValid(request.getProcessingTime())) {
        throw new IllegalArgumentException("processing_time is invalid");
    }
}
~~~

**occurred_at** là message field nên có **hasOccurredAt()** dù không khai báo optional. Ví dụ quy định thời điểm phát sinh là bắt buộc ở tầng nghiệp vụ; Protobuf schema tự nó không bắt buộc field này phải có mặt.

Không tin Timestamp từ client chỉ vì nó hợp lệ về phạm vi. Nếu timestamp ảnh hưởng thứ tự nghiệp vụ, chống phát lại hoặc quyền truy cập, server còn cần kiểm tra độ lệch cho phép, nguồn thời gian và quy tắc nghiệp vụ. Timestamp hợp lệ về cấu trúc không chứng minh đồng hồ client chính xác.

## 11. Kiểm thử chuyển đổi và biên thời gian

Các trường hợp nên kiểm thử:

1. Timestamp có nano giây, round-trip qua Java và binary không mất độ chính xác.
2. Timestamp trước Unix epoch để xác nhận cách chuẩn hóa seconds/nanos.
3. Duration âm có phần lẻ, đặc biệt **-0.5s**.
4. Timestamp/Duration ngoài phạm vi hoặc sai quy tắc dấu bị từ chối.
5. ProtoJSON dùng RFC 3339 cho Timestamp và hậu tố **s** cho Duration.
6. Field message vắng mặt khác với field được đặt bằng default instance.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.protobuf.Timestamp;
import com.google.protobuf.util.Timestamps;
import com.google.protobuf.util.Durations;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class TimeTypesTest {
    @Test
    void preservesNanosecondsInTimestamp() throws Exception {
        Instant instant =
            Instant.parse("2026-11-19T08:30:15.123456789Z");

        Timestamp source = Timestamp.newBuilder()
            .setSeconds(instant.getEpochSecond())
            .setNanos(instant.getNano())
            .build();

        Timestamp parsed = Timestamp.parseFrom(source.toByteArray());
        assertTrue(Timestamps.isValid(parsed));
        assertEquals(instant.getEpochSecond(), parsed.getSeconds());
        assertEquals(123456789, parsed.getNanos());
    }

    @Test
    void validatesNegativeDurationNormalization() {
        java.time.Duration javaValue =
            java.time.Duration.ofMillis(-500);

        com.google.protobuf.Duration protoValue =
            toProtoDuration(javaValue);

        assertEquals(0, protoValue.getSeconds());
        assertEquals(-500000000, protoValue.getNanos());
        assertTrue(Durations.isValid(protoValue));
        assertEquals(javaValue, toJavaDuration(protoValue));
    }
}
~~~

Hai hàm **toProtoDuration()** và **toJavaDuration()** trong test là các hàm chuyển đổi được trình bày ở mục 7. Trong dự án thực tế, đặt chúng ở một lớp mapper dùng chung và kiểm thử thêm các biên ±10.000 năm.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng Timestamp cho khoảng thời gian | Không biết thời điểm bắt đầu/kết thúc nào tạo ra giá trị | Dùng **Duration**. |
| Dùng Duration cho tháng lịch | Một tháng không có số giây cố định | Dùng kiểu ngày/lịch và timezone phù hợp. |
| Coi Timestamp là giờ địa phương | Diễn giải sai khi client ở múi giờ khác | Chuyển local time sang Instant với timezone rõ ràng. |
| Chỉ chuyển qua milliseconds | Mất độ chính xác micro/nano giây | Chuyển seconds và nanos trực tiếp khi cần độ chính xác cao. |
| Sao chép seconds/nanos âm từ Java Duration | Tạo Duration Protobuf sai quy tắc dấu | Chuẩn hóa trước và kiểm tra **Durations.isValid()**. |
| Bỏ qua **hasXxx()** | Nhầm field vắng mặt với epoch hoặc duration 0 | Kiểm tra presence của message field. |
| Xem Timestamp hợp lệ là thời gian đáng tin cậy | Client có thể gửi thời điểm sai lệch | Kiểm tra chính sách thời gian ở server. |
| Dùng Duration thay cho gRPC Deadline | Không giới hạn trực tiếp vòng đời RPC | Đặt deadline trên client call bằng API gRPC. |

## 13. Bài tập thực hành

Một dịch vụ xử lý tác vụ cần lưu thời điểm nhận yêu cầu, thời điểm hoàn tất và thời gian xử lý:

~~~proto
import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message TaskTiming {
  string task_id = 1;
  google.protobuf.Timestamp received_at = 2;
  google.protobuf.Timestamp completed_at = 3;
  google.protobuf.Duration processing_time = 4;
}
~~~

Hãy:

1. Giải thích vì sao **received_at** và **completed_at** là Timestamp, còn **processing_time** là Duration.
2. Tạo hai Timestamp từ **java.time.Instant** với độ chính xác nano giây.
3. Chuyển **java.time.Duration.ofMillis(-500)** sang Protobuf Duration và chứng minh seconds/nanos cùng dấu.
4. Xuất message thành ProtoJSON, xác định định dạng RFC 3339 và hậu tố **s**.
5. Kiểm tra trường hợp **completed_at** chưa được đặt và trường hợp được đặt bằng Timestamp epoch.
6. Giải thích vì sao đo thời gian chạy trong một tiến trình nên dùng đồng hồ monotonic, còn thời điểm sự kiện cần Timestamp.
7. Nêu cách áp dụng gRPC Deadline nếu client chỉ cho phép RPC chạy tối đa một khoảng thời gian cấu hình.

**Tiêu chí hoàn thành:** chọn đúng ngữ nghĩa thời gian, chuyển đổi Java không mất độ chính xác ngoài ý muốn, chuẩn hóa Duration âm, kiểm tra presence/validity và phân biệt WKT với API deadline của gRPC.

## 14. Ghi nhớ

- **Timestamp** là một thời điểm tuyệt đối tính từ Unix epoch; **Duration** là khoảng thời gian có dấu.
- Cả hai dùng seconds và nanos, nhưng có quy tắc chuẩn hóa và miền giá trị khác nhau.
- Timestamp tương ứng tốt với **java.time.Instant**; Duration tương ứng với **java.time.Duration** nhưng cần chú ý chuẩn hóa giá trị âm.
- ProtoJSON biểu diễn Timestamp bằng chuỗi RFC 3339 và Duration bằng chuỗi kết thúc với **s**.
- Timestamp/Duration là message field nên có presence; dùng **hasXxx()** để phân biệt field vắng mặt với giá trị mặc định.
- **Duration không thay thế io.grpc.Deadline**; dùng đúng API theo mục đích đo thời gian hoặc giới hạn RPC.
- Dùng WKT chuẩn thay vì tự định nghĩa message thời gian riêng nếu ngữ nghĩa phù hợp.

Sử dụng Timestamp, Duration và các well-known types đúng cách giúp hợp đồng Protocol Buffers thống nhất giữa Java và các client khác, đồng thời tránh lỗi múi giờ, độ chính xác và diễn giải thời gian trong dịch vụ Spring gRPC.
