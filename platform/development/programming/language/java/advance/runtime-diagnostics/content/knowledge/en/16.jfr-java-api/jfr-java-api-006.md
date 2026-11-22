# 16.6 Ghi mã tương quan, kết quả và độ trễ nghiệp vụ với dữ liệu giới hạn

> **Phạm vi:** Java 17+ và Java Flight Recorder (JFR) qua module `jdk.jfr`. Trọng tâm là thiết kế **custom JFR event** cho một thao tác nghiệp vụ: gắn mã tương quan có thể tra cứu, ghi nhận kết quả thành công/thất bại, đo đúng khoảng thời gian nghiệp vụ và kiểm soát **loại dữ liệu, kích thước, tần suất** phát sinh. Các ví dụ sử dụng JDK 17+; lệnh đã được kiểm tra trên OpenJDK 24.

## 1. Vì sao nên ghi business event vào JFR?

Các JFR event dựng sẵn như GC, CPU sampling, lock contention, socket I/O và file I/O giúp biết **JVM đang làm gì**. Nhưng chúng thường không trả lời trực tiếp:

- Request **đặt chỗ** hoặc **xác nhận đơn** nào đã chậm?
- Nó đã thành công, bị từ chối vì kiểm tra nghiệp vụ, bị timeout hay bị hủy?
- Khoảng chậm ở tầng nghiệp vụ bắt đầu/kết thúc ở đâu?
- Làm sao nối một thời điểm JFR với log hoặc trace của đúng thao tác mà không ghi cả request body hay thông tin cá nhân?

Một custom event cho phép ghi bối cảnh vừa đủ:

```text
Custom JFR event: demo.BusinessOperation
  startTime       : thời điểm bắt đầu đoạn được đo
  duration        : thời lượng đoạn đó (JFR tự ghi)
  correlationCode : mã tra cứu nội bộ không chứa dữ liệu cá nhân
  operation       : tên nghiệp vụ thuộc danh sách cố định
  outcome         : SUCCESS | FAILED | CANCELLED
  failureCategory : NONE | VALIDATION | DEPENDENCY | TIMEOUT | INTERRUPTED | OTHER
  itemCount       : số lượng đầu vào hợp lệ, đã giới hạn theo chính sách
```

`startTime` và `duration` do cơ chế `Event.begin()`/`Event.end()` của JFR quản lý. Các trường còn lại do ứng dụng tự định nghĩa. Thay vì “log thật nhiều để chắc chắn đủ dữ liệu”, hãy xác định **câu hỏi cần điều tra** rồi chọn vài trường ổn định, không nhạy cảm, chi phí thấp.

**Sự khác biệt với metrics và logs:**

| Tín hiệu | Mạnh nhất khi | Giới hạn cần nhớ |
| --- | --- | --- |
| **JFR business event** | Đối chiếu một giao dịch/nhóm giao dịch với thời điểm JVM bị GC, pause, lock hoặc I/O; xem duration cùng JVM timeline | Chịu event settings, threshold, buffer/retention; có thể không chứa mọi request |
| **Metrics (counter/histogram)** | Tính throughput, error rate, latency p50/p95/p99 trên toàn bộ mẫu được instrument | Thường không giữ mã riêng của từng giao dịch; các nhãn có cardinality cao dễ gây tốn tài nguyên |
| **Structured logs** | Tìm diễn biến chi tiết theo một mã, theo dõi cảnh báo và lỗi nghiệp vụ | Cần giới hạn dữ liệu cá nhân; timestamp riêng lẻ thường không cho duration đầy đủ |
| **Distributed tracing** | Theo đường request qua nhiều service, spans và critical path | Cần context propagation, sampling và chính sách thu thập; không tự thay thế thông tin JFR trong JVM |

Kết hợp JFR + metrics + logs/traces là cách có thể kiểm chứng nguyên nhân. JFR không phải hệ thống lưu audit bắt buộc, hệ thống thanh toán hay cơ chế bảo đảm ghi nhận 100% giao dịch.

## 2. Thiết kế hợp đồng event trước khi viết code

### 2.1. Event name và các trường ổn định

Tên event nên có namespace rõ ràng và ổn định, ví dụ `demo.BusinessOperation` trong lab và `com.acme.checkout.BusinessOperation` trong sản phẩm thực. Tên này được dùng khi cấu hình event, lọc `jfr print` và phân tích trong JDK Mission Control (JMC).

| Trường | Kiểu JFR phù hợp | Quy ước dữ liệu | Không được đưa vào |
| --- | --- | --- | --- |
| `correlationCode` | `String` | Mã ngẫu nhiên/opaque do hệ thống phát hành; giới hạn chiều dài, alphabet cho phép và vòng đời | Email, số điện thoại, tên khách hàng, mã phiên đăng nhập, access token, nội dung request |
| `operation` | `String` | Một giá trị thuộc allowlist cố định, ví dụ `reserve`, `checkout`, `refund` | URL nguyên bản có query string, tên class động, chuỗi tùy ý từ người dùng |
| `outcome` | `String` | `SUCCESS`, `FAILED`, `CANCELLED` hoặc schema được thống nhất | Thông điệp exception tùy ý |
| `failureCategory` | `String` | Nhóm lỗi ít giá trị, ví dụ `NONE`, `VALIDATION`, `TIMEOUT`, `DEPENDENCY`, `OTHER` | SQL, full stack trace, HTTP body, raw error messages có thể chứa bí mật |
| `itemCount` | `int` | Số lượng không âm với giới hạn và ý nghĩa rõ ràng | Giá trị giả làm số chính xác khi thực tế đã bị cắt |
| `startTime`/`duration` | Trường hệ thống của event | Thời gian do `begin`/`end` xác định | Không tự gắn timestamp lấy từ đồng hồ khác nếu không có nhu cầu đối chiếu |

Đối với custom event class, `jdk.jfr.Event` chỉ ghi các trường instance có kiểu **Java primitive, `String`, `Thread` hoặc `Class`**. Một `enum`, `Map`, `List`, array, object DTO, v.v. **không** tự động được ghi thành payload; những kiểu reference khác có thể bị bỏ qua mà không báo lỗi. Do đó nếu business layer dùng `enum Outcome`, hãy chuyển sang **tên String thuộc allowlist** trước khi ghi.

`@Name`, `@Label`, `@Category`, `@Description` giúp JFR tools nhận diện schema và trình bày trường dễ hiểu. Đổi tên/kiểu field có thể làm hỏng query hoặc dashboard đã viết trước; nên xem event schema như một **hợp đồng dữ liệu** có kiểm soát phiên bản.

### 2.2. Mã tương quan là khóa nối, không phải dữ liệu nghiệp vụ

Một mã tương quan có nhiệm vụ nối:

```text
log/service-A  -- correlationCode=c-7f3... --> JFR/service-A
   |                                            |
   +----------- trace/context ------------------+
                      |
                  service-B logs/traces
```

**Các cách tạo hợp lý:**

1. Tạo một opaque ID ngẫu nhiên phía server khi bắt đầu luồng nghiệp vụ. Nếu cần đi qua nhiều service, truyền ID theo kênh được kiểm soát và giữ nhất quán.
2. Nếu đã có trace context được chấp nhận, dùng `traceId`/`spanId` với **định dạng và giới hạn rõ ràng**; tránh đưa toàn bộ tracing baggage vào JFR.
3. Khi chỉ có business ID nhạy cảm, **không ghi trực tiếp**. Có thể phát hành một ID nội bộ ánh xạ an toàn hoặc dùng HMAC có khóa và policy phù hợp để tạo pseudonym khi thực sự cần tương quan. Hash thường của email/order ID dễ bị suy đoán từ danh sách giá trị; nó không đương nhiên bảo vệ danh tính.
4. Giới hạn mã theo độ dài (ví dụ tối đa 64 ký tự ASCII), format và nguồn tin cậy. Chỉ kiểm tra regex không đủ để bảo đảm chuỗi không chứa dữ liệu cá nhân nếu caller gửi chính email/token dưới dạng hợp lệ.

Một mã có cardinality cao có thể chấp nhận được **trong một số JFR events có retention giới hạn** vì nó dùng để tìm một giao dịch; nhưng **không** đưa từng mã vào label của time-series metrics. Số event và dữ liệu String khác nhau trên mỗi event vẫn có chi phí lưu trữ, index và phân tích.

### 2.3. Kết quả là trạng thái cuối của vùng đo

`outcome` phải mô tả **đoạn nghiệp vụ đang được đo**, không suy ra từ việc method có/không ném exception:

- `SUCCESS`: bước nghiệp vụ được xác nhận hoàn tất theo hợp đồng của bước đó.
- `FAILED`: bước thất bại (có thể vì validation, dependency hoặc lý do khác).
- `CANCELLED`: bước bị hủy/ngắt với ngữ nghĩa nghiệp vụ tương ứng.

Một phương thức trả HTTP 200 nhưng kết quả nghiệp vụ **từ chối giao dịch** vẫn có thể là `FAILED` về mặt nghiệp vụ. Ngược lại một retry đã thành công có thể là `SUCCESS` cho **attempt cuối**, nhưng luồng toàn bộ vẫn có latency khác. Hãy định nghĩa rõ event đo **một attempt** hay **toàn bộ operation**, tránh trộn hai loại.

## 3. Đo đúng “độ trễ nghiệp vụ”

### 3.1. `begin()` và `end()`

API JFR cho custom event:

```java
BusinessEvent event = new BusinessEvent();
event.begin();
try {
    // Công việc muốn đo.
} finally {
    event.end();
    if (event.shouldCommit()) {
        // Chỉ tạo payload hữu ích khi event thực sự được thu.
        event.commit();
    }
}
```

`event.begin()` bắt đầu đồng hồ JFR; `event.end()` kết thúc khoảng đo; `commit()` ghi event khi event đang enabled và đáp ứng threshold. JFR lưu `startTime`, `duration` cùng các trường bổ sung. `end()` phải được gọi sau `begin()`; nếu không gọi `end()`, `commit()` có thể đánh dấu thời điểm kết thúc, nhưng `finally` rõ ràng giúp không vô tình bỏ qua nhánh lỗi.

**Chọn ranh giới đo có ý nghĩa:** Nếu muốn “thời gian xử lý đặt chỗ”, gọi `begin()` ngay trước khi bắt đầu business operation, `end()` khi outcome của operation đã xác định. Nó sẽ **không tính** thời gian trước `begin()` như request đứng trong queue tại API gateway; cũng không tính công việc async tiếp diễn **sau** khi method đã trả về. Đặt `end()` trước hay sau ghi DB, retry, external call, transaction commit sẽ thay đổi SLI nên cần thống nhất.

Các điểm cần phân biệt:

- JFR `duration` là **thời gian elapsed** giữa begin và end; không phải CPU time của thread.
- Nếu đoạn đo chờ DB/network, lock, sleep hoặc scheduler, `duration` vẫn tăng dù thread không sử dụng CPU.
- Nếu operation chạy nhiều thread hay async, một event trên một method không tự động cộng thời gian của những task chưa `join`/`await`; hãy chọn **điểm bắt đầu/kết thúc logic của operation** rồi truyền correlation context.
- Với virtual threads, JFR vẫn ghi event theo logic begin/end, nhưng `eventThread` không đủ để suy ra request xuyên nhiều async boundaries.
- Không tự chuyển `duration` sang “số ms từ `System.currentTimeMillis()`” trong JFR payload khi JFR đã cung cấp duration; thêm trường riêng chỉ khi một metric khác có semantics khác rõ ràng.

### 3.2. `shouldCommit()` và threshold

JFR cho phép đặt `threshold`: duration **nhỏ hơn ngưỡng** sẽ không được ghi. Sau khi đã `end()`, `shouldCommit()` giúp tránh tính toán/khử dữ liệu đắt đỏ cho event không được lưu.

- Với **lab**: threshold 0, thu cả thành công và thất bại, kể cả nhanh.
- Với **chẩn đoán chậm**: ví dụ threshold 50 ms để chỉ giữ các operation mất ít nhất 50 ms.
- Với **đo tỷ lệ lỗi**: một `FAILED` rất nhanh có thể bị bỏ qua nếu cùng event bị threshold 50 ms. Không được kết luận “không có lỗi” từ JFR slow-event recording; nếu bắt buộc quan sát lỗi nhanh, thiết kế event lỗi riêng với quota/sampling phù hợp hoặc dùng metrics/logs.
- Với **phân phối latency**: nếu chỉ lưu operation chậm hơn threshold, dữ liệu là mẫu **đã bị cắt ở phía ngắn**; không thể lấy p50/p95/p99 cho **toàn bộ request** bằng cách tính trực tiếp từ những event đó. Dùng latency histogram phù hợp cho SLI; JFR để soi trường hợp cụ thể.

`Event.isEnabled()` kiểm tra có recording nào bật loại event đó; `shouldCommit()` còn xét ngưỡng duration. Đây là các công cụ giảm overhead, không phải cách đảm bảo event sẽ được lưu trên đĩa vĩnh viễn: JFR vẫn có buffer, rotation, retention và giới hạn vận hành.

## 4. Dữ liệu giới hạn nghĩa là giới hạn những gì?

Có **ba loại giới hạn phải thiết kế đồng thời**.

### 4.1. Giới hạn *loại và kích thước* dữ liệu

Một event tốt thường chỉ chứa **vài trường số và các String ngắn có cấu trúc**:

- Sử dụng **allowlist** cho `operation`, `outcome`, `failureCategory`; giá trị lạ được gộp thành `OTHER` có kiểm soát.
- Mã tương quan phải từ nguồn đáng tin cậy, có max length và không mang PII/credential. Không dùng trực tiếp session ID, JWT, cookie, URL/query, header tùy ý hay raw customer ID.
- Không ghi request/response payload, SQL text, exception message hoặc stack trace cho mọi event. Một số thông điệp lỗi chứa token, địa chỉ, đường dẫn hoặc dữ liệu riêng tư mà người viết code không dự đoán được.
- Với số lượng có thể rất lớn, xác định kiểu và giới hạn. Nếu ghi giá trị đã capped, thêm `wasCapped=true` hoặc dùng bucket để không khiến người đọc hiểu nhầm nó là số thực.
- Không thêm field `String debugData` rồi serialize object/JSON vào đó. Kích thước event và số biến thể sẽ tăng nhanh, lại khó kiểm soát nội dung nhạy cảm.

Ví dụ một quy tắc kiểm tra mã từ **hệ thống tự sinh**, tách khỏi dữ liệu khách hàng:

```java
static String safeCode(String systemCode) {
    if (systemCode == null
            || systemCode.length() > 64
            || !systemCode.matches("[A-Za-z0-9_-]{1,64}")) {
        return "INVALID";
    }
    return systemCode;
}
```

Đây là **minh họa policy đầu vào**, không phải một chương trình Java độc lập. Hàm này chỉ kiểm tra format; không thể phát hiện rằng caller đã đưa thông tin nhạy cảm vào String. Nếu bị lỗi format, nên đánh dấu `INVALID`/`MISSING` và xử lý trong log/trace theo policy, **không** nhét lại nguyên bản lỗi format vào JFR.

### 4.2. Giới hạn *tần suất* và *số event*

Giả sử hệ thống có 30.000 operation/s, trung bình event 200 byte (số minh họa, chưa tính metadata, chunk overhead và sampling). Nếu ghi mỗi operation, riêng payload lý thuyết đã khoảng 6 MB/s. Dung lượng thực còn tùy field strings, encoding, stack traces và các event JDK khác. Không dùng công thức đó như phép đo thực.

Những chiến lược thường dùng:

- Event detail chỉ cho **slow operations**, dựa trên threshold; dùng histogram/counters để giữ cái nhìn tổng thể.
- Event kết quả `FAILED` cần riêng chính sách capture nếu lỗi nhanh cũng quan trọng; không ghi dữ liệu lớn chỉ vì là lỗi.
- Chọn **bounded sampling** theo hệ thống, hoặc phát event theo request/tracing sampling policy. Thông báo rõ tỷ lệ và mục đích; mẫu JFR sau sampling không tương đương toàn bộ lưu lượng.
- Tắt stack trace cho event nghiệp vụ có mã tương quan nếu stack không trả lời câu hỏi; chỉ bật ở thời điểm điều tra bằng recording/settings riêng khi chi phí phù hợp.
- Đặt `maxage`/`maxsize`, disk headroom, quota trên storage và retention/ACL khi xuất file `.jfr`.

JFR recording settings không tự cung cấp “mỗi business ID tối đa một event” hay giới hạn bảo mật cho String fields; ứng dụng phải quyết định policy và triển khai giới hạn phù hợp tại **điểm tạo payload**.

### 4.3. Giới hạn *mức độ truy cập và thời gian giữ*

`.jfr` là artifact chẩn đoán có thể chứa chi tiết JVM/runtime, môi trường, stack/method names và custom payload. Nó không mặc nhiên được ẩn danh hoặc mã hóa. Cần:

- Hạn chế người đọc file, kiểm soát nơi lưu, chia sẻ và thời gian xóa.
- Khi trích xuất để gửi cho bên khác, kiểm tra dữ liệu và áp dụng quy trình giảm thiểu/ẩn danh nếu cần.
- Không dựa vào “không ghi email” để kết luận an toàn tuyệt đối: mã tương quan cũng có thể nối ngược ra dữ liệu khách hàng qua hệ thống nội bộ.
- Phân biệt retention của JFR recording và retention của bản export/log/report; chúng có thể khác nhau.

## 5. Lab Java 17+: ghi và đọc event nghiệp vụ hoàn chỉnh

Chương trình dưới đây chạy độc lập; nó cố tình tạo **hai operation** gồm một thành công, một thất bại đã được xử lý. Event được ghi khi operation kết thúc, dù nhánh thất bại ném exception. Không có dữ liệu cá nhân: `r-0001` và `r-0002` là mã demo cố định.

### 5.1. Tạo `BusinessJfrDemo.java`

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class BusinessJfrDemo {
    @Name("demo.BusinessOperation")
    @Label("Business operation")
    @Category({"Application", "Business"})
    @StackTrace(false)
    public static class BusinessEvent extends Event {
        @Label("Correlation code")
        public String correlationCode;
        @Label("Operation")
        public String operation;
        @Label("Outcome")
        public String outcome;
        @Label("Failure category")
        public String failureCategory;
        @Label("Item count")
        public int itemCount;
    }

    static void process(String code, boolean fail) throws InterruptedException {
        BusinessEvent event = new BusinessEvent();
        String outcome = "SUCCESS";
        String category = "NONE";
        event.begin();
        try {
            Thread.sleep(30);
            if (fail) {
                throw new IllegalArgumentException("simulated failure");
            }
        } catch (InterruptedException ex) {
            outcome = "CANCELLED";
            category = "INTERRUPTED";
            Thread.currentThread().interrupt();
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "FAILED";
            category = "VALIDATION";
            throw ex;
        } finally {
            event.end();
            if (event.shouldCommit()) {
                event.correlationCode = code;
                event.operation = "reserve";
                event.outcome = outcome;
                event.failureCategory = category;
                event.itemCount = 1;
                event.commit();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path target = Path.of("business.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(BusinessEvent.class)
                .withThreshold(Duration.ZERO)
                .withoutStackTrace();
            recording.start();
            process("r-0001", false);
            try {
                process("r-0002", true);
            } catch (IllegalArgumentException ignored) {
                // The simulated failure is expected in this lab.
            }
            recording.stop();
            recording.dump(target);
        }

        List<String> rows = new ArrayList<>();
        try (RecordingFile reader = new RecordingFile(target)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent e = reader.readEvent();
                if (!e.getEventType().getName().equals("demo.BusinessOperation")) {
                    continue;
                }
                if (e.getDuration().isNegative()) {
                    throw new IllegalStateException("Negative duration");
                }
                rows.add(e.getString("correlationCode") + "|"
                    + e.getString("operation") + "|"
                    + e.getString("outcome") + "|"
                    + e.getString("failureCategory") + "|"
                    + e.getInt("itemCount"));
            }
        }
        Collections.sort(rows);
        System.out.println("business-events=" + rows.size());
        for (String row : rows) {
            System.out.println(row);
        }
    }
}
```

Cách chương trình hoạt động:

1. `BusinessEvent` kế thừa `jdk.jfr.Event` và khai báo các field JFR hỗ trợ: bốn `String`, một `int`.
2. `@Name("demo.BusinessOperation")` là tên event để cấu hình và tìm kiếm. `@StackTrace(false)` cho biết không cần JFR stack trace mặc định với loại event này.
3. `process()` gọi `begin()` trước phần mô phỏng nghiệp vụ, bắt exception để chuyển thành **nhóm kết quả ổn định**, rồi gọi `end()` trong `finally`.
4. Sau `end()`, `shouldCommit()` xét recording/threshold. Chỉ khi cần lưu event mới điền các field; exception message `simulated failure` **không được đưa vào payload**.
5. `Recording` trong `main` chỉ dùng để tạo một bản ghi lab. `enable(...).withThreshold(Duration.ZERO).withoutStackTrace()` bật event, bỏ ngưỡng duration và tắt stack trace.
6. `RecordingFile` đọc binary `.jfr`, lọc đúng event name rồi in các trường an toàn. Chương trình kiểm tra duration không âm, nhưng không in số ms cụ thể vì phụ thuộc máy.

**Giới hạn của lab:** `code`, `operation` và `itemCount` là những giá trị kiểm soát sẵn. Trong production, phải gọi hàm giới hạn/allowlist và tuân thủ policy **trước khi** gán các field; không sao chép thẳng dữ liệu request không đáng tin vào `event`.

### 5.2. Biên dịch và chạy

Từ thư mục chứa file:

```bash
javac BusinessJfrDemo.java
java BusinessJfrDemo
```

Stdout chính xác từ mã Java trên (đã kiểm tra trên OpenJDK 24):

```text
business-events=2
r-0001|reserve|SUCCESS|NONE|1
r-0002|reserve|FAILED|VALIDATION|1
```

Chương trình tạo file `business.jfr` trong current working directory. Trong lab, các dòng được sắp bằng `Collections.sort()` trước khi in, do đó output không phụ thuộc thứ tự các event khác có thể tồn tại trong recording.

### 5.3. Kiểm tra trực tiếp bằng công cụ JFR

```bash
jfr summary business.jfr
jfr print --events demo.BusinessOperation business.jfr
jfr metadata --events demo.BusinessOperation business.jfr
```

`jfr summary` sẽ liệt kê `demo.BusinessOperation` với **2 event** trong lab đã chạy thành công. `jfr print` cung cấp những trường dạng:

```text
demo.BusinessOperation {
  startTime = ...
  duration = ...
  correlationCode = "r-0001"
  operation = "reserve"
  outcome = "SUCCESS"
  failureCategory = "NONE"
  itemCount = 1
  eventThread = "main" (...)
}
```

Dấu `...` trong block trên **chỉ là hình minh họa schema của output JFR**, không phải stdout cố định. Timestamp, duration, thread ID và thứ tự metadata có thể khác giữa lần chạy hoặc JDK. Với kết quả thật, xem file `business.jfr` bằng lệnh trên; hai trường duration và startTime do JFR tạo, không cần tự thêm vào custom class.

Một bản ghi thực nghiệm trên JDK 24 có hai event với duration khoảng vài chục ms. Điều này chỉ kiểm chứng **cách instrument**, không phải phép đo benchmark hay cam kết latency 30 ms trên mọi hệ thống.

## 6. Đưa ý tưởng vào ứng dụng thực: vị trí và vòng đời

### 6.1. Đặt event quanh đơn vị nghiệp vụ có nghĩa

Giả sử một luồng đặt chỗ gồm:

```text
HTTP request
  -> validate input
  -> query inventory
  -> reserve inventory
  -> persist reservation
  -> return response
```

Hãy xác định ranh giới mà business team gọi là “thời gian đặt chỗ”. Nếu muốn đo từ lúc vào service đến khi DB commit xong, `begin()` cần bao phủ toàn bộ các bước đó. Nếu chỉ đo dependency call, đặt tên riêng như `InventoryLookup` và `begin/end` quanh call đó. **Không dùng cùng tên event cho hai định nghĩa latency khác nhau**, vì dữ liệu không thể so sánh trung thực.

Một operation có retry có thể thiết kế:

- `BusinessOperation`: một event cho **toàn bộ** operation, outcome cuối và tổng elapsed time.
- `DependencyAttempt`: event riêng khi cần điều tra **một lần retry**, có cùng correlationCode và `attemptNumber` có giới hạn.
- Metrics đi kèm ghi tổng số operations/attempts và duration histograms.

Không phát event ở cả controller và service cùng tên rồi cộng chúng như hai giao dịch độc lập; đó là double counting.

### 6.2. Duy trì correlation khi bất đồng bộ

Trong callback/executor/virtual thread hoặc request chuyển service, **mã tương quan phải được truyền qua boundary**. `eventThread` là thread ghi event; nó không tự chứa business correlation. Cũng không nên dựa vào tên thread để tái dựng quan hệ qua thread pool.

Có thể truyền một context object nhỏ, immutable, chỉ gồm opaque code và các thuộc tính được phép qua method parameters hoặc tracing context. Với structured concurrency/async, muốn đo end-to-end latency thì `end()` chỉ chạy sau khi kết quả từ các nhánh cần thiết đã được await/hoàn tất. Nếu `end()` chạy lúc task vừa được submit, duration đo **submission latency**, không phải business completion.

Tách rõ ba thời gian khi phân tích:

1. **Queue delay** trước lúc công việc thực sự bắt đầu.
2. **Execution/elapsed duration** từ `begin()` đến `end()` của business operation.
3. **End-to-end request duration** phía client/gateway bao gồm network và những giai đoạn trước/sau vùng đo.

Nếu cần cả ba, định nghĩa events/metrics khác nhau và đặt tên rõ thay vì trộn vào một `duration`.

### 6.3. Giữ logic nghiệp vụ độc lập với lỗi ghi telemetry

Một event chẩn đoán không được biến failure nghiệp vụ thành success hoặc che exception gốc. Những phương thức ghi JFR bình thường không yêu cầu I/O đồng bộ trên hot path, nhưng code phụ tự viết để chuẩn hóa payload có thể ném exception. Vì vậy:

- Dùng `finally` để đóng khoảng đo trên success/failure/cancel.
- Giữ nhóm outcome trong các nhánh `catch` thích hợp; **không nuốt exception** chỉ để tạo event.
- Không gọi thêm network/DB từ đoạn tạo payload JFR.
- Tránh serialize object lớn hoặc gọi `toString()` trên dữ liệu không tin cậy trong `finally`.
- Ghi nhận `InterruptedException` là `CANCELLED`/`INTERRUPTED` theo semantics ứng dụng, giữ cờ interrupt nếu cần.
- Không để một lỗi trong instrumentation làm mất dấu stack/exception nghiệp vụ đang xảy ra.

Lab ở mục 5 làm rõ success/failure/interrupt với Java exception handling thông thường, không thêm side effect ngoài recording.

## 7. Bật custom event trong recording của service

### 7.1. Hai cách cấu hình

**Cách A — chương trình tự tạo recording** (chủ yếu phục vụ test/tooling):

```java
try (Recording recording = new Recording()) {
    recording.enable(BusinessJfrDemo.BusinessEvent.class)
        .withThreshold(Duration.ofMillis(20))
        .withoutStackTrace();
    recording.start();
    // Thực thi phần cần chẩn đoán.
    recording.stop();
    recording.dump(Path.of("sample.jfr"));
}
```

Block trên là **mã minh họa**, chỉ biên dịch khi đặt trong class/method có imports và xử lý exception như ví dụ hoàn chỉnh ở mục 5. Trong ứng dụng server production, **không tạo một `Recording` cho mỗi request**: recording là một cơ chế cấp JVM, có chi phí quản lý và tài nguyên; thường tạo một recording cho khoảng thời gian chẩn đoán, hoặc quản lý bằng `jcmd`/JMC.

**Cách B — recording quản trị qua JVM/JFR settings**. Tạo `.jfc` có custom event:

```bash
jfr configure --output business.jfc \
  "+demo.BusinessOperation#enabled=true" \
  "+demo.BusinessOperation#threshold=20ms" \
  "+demo.BusinessOperation#stackTrace=false"
```

Các dấu `+` trong `jfr configure` yêu cầu **thêm event setting** nếu profile cơ sở chưa chứa custom event. Tên `demo.BusinessOperation` phải khớp `@Name` trong code. Các đối số có `#` nên được quote khi gọi shell. Cấu hình `20ms` thích hợp để xem operation **chậm**; không thích hợp khi bạn cần quan sát tất cả các lần thất bại rất nhanh.

Dùng file tạo ra:

```bash
java -XX:StartFlightRecording=name=business,settings=business.jfc,disk=true,filename=business-service.jfr,dumponexit=true \
  -jar app.jar
```

`app.jar` là ứng dụng giả định có chứa custom event class và instrumentation như trên. `filename` là file JFR đầu ra; `dumponexit=true` yêu cầu dump khi JVM thoát thông thường, không bảo đảm nếu tiến trình bị kill bất ngờ. Ghi dài hạn cần đặt retention/storage và đánh giá overhead.

Với JVM đang chạy (sử dụng PID thật và quyền attach thích hợp):

```bash
jcmd -l
jcmd <PID> JFR.start name=business settings=business.jfc duration=60s filename=business-snapshot.jfr
jcmd <PID> JFR.check name=business verbose=true
```

`JFR.check verbose=true` giúp xác nhận các event settings thật của recording. Sau khi đủ thời gian, đọc `business-snapshot.jfr`; khi cần snapshot trong lúc recording còn sống:

```bash
jcmd <PID> JFR.dump name=business filename=business-now.jfr
```

Không xem `jfr configure` là lệnh khởi chạy recording: nó chỉ tạo/chỉnh file `.jfc`. Không xem `jcmd JFR.configure` là chỗ đặt ngưỡng cho một custom event: command này chủ yếu cấu hình recorder toàn cục. Tên event và threshold của recording thuộc `JFR.start settings=...` hoặc `Recording.enable(...).withThreshold(...)`.

### 7.2. Chọn ngưỡng theo câu hỏi cần trả lời

| Mục đích | Cấu hình gợi ý | Cảnh báo |
| --- | --- | --- |
| Lab xác nhận đúng event schema | `threshold=0`, stack trace off, recording ngắn | Không nhân nguyên cấu hình này lên workload lớn mà chưa đo overhead. |
| Tìm business operations chậm | `threshold=20ms`/`50ms` hoặc theo SLO thực tế | Không đủ để suy tỷ lệ thành công hay phân phối của mọi request. |
| Tìm lỗi nhanh và hiếm | Event riêng cho failure hoặc cơ chế sampling/metrics đồng bộ | Một slow-only event sẽ bỏ qua lỗi dưới ngưỡng. |
| Cần stack tại thời điểm commit | Bật stackTrace có thời hạn cho event phù hợp | Stack trace tạo thêm dữ liệu, vị trí commit không nhất thiết là nơi bắt đầu operation. |
| Theo dõi hành vi dài hạn | Metrics cho count/histograms; JFR sample/slow-case có retention | Không dùng JFR event như sổ cái giao dịch bắt buộc. |

`@StackTrace(false)` định cấu hình mặc định của loại event; recording-specific setting có thể ghi đè. `stackTrace=true` lấy stack tại **lúc commit**; nếu muốn biết call path trước đó, phải xem nó có thực sự đại diện cho câu hỏi của bạn không.

## 8. Đọc và tương quan dữ liệu đã thu

### 8.1. Dùng JFR CLI/JMC

```bash
jfr summary business-service.jfr
jfr print --events demo.BusinessOperation business-service.jfr
jfr metadata --events demo.BusinessOperation business-service.jfr
```

Quan sát:

- `startTime`: so với thời điểm log/trace theo múi giờ thống nhất.
- `duration`: khoảng thời gian đoạn business logic thực sự được instrument.
- `correlationCode`: khóa tra cứu log/tracing; đừng dựa vào thread ID làm request ID.
- `operation` + `outcome` + `failureCategory`: xác định trường hợp cần điều tra và loại lỗi.
- `itemCount`: bối cảnh tải nhỏ gọn; không đồng nghĩa độ phức tạp công việc nếu business logic có nhiều biến khác.
- `eventThread`: có ích khi đối chiếu JVM thread events, nhưng không đủ chứng minh quan hệ end-to-end khi có async.

JDK Mission Control cho phép lọc custom event theo các field và so timestamp với GC, allocation, locks hoặc I/O. Một sequence phân tích có cơ sở:

1. Tìm `correlationCode` của request chậm trong log/trace.
2. Lấy event `demo.BusinessOperation` có cùng code, cùng operation và đúng khoảng thời gian.
3. Xem duration, outcome và failureCategory.
4. So khoảng thời gian event với GC pauses, CPU load, socket/monitor events cùng JVM.
5. Đối chiếu logs/traces để xác nhận câu chuyện; ví dụ JFR có GC pause trùng khoảng request chậm **chưa đủ** chứng minh GC là nguyên nhân duy nhất.

### 8.2. Đọc trực tiếp bằng Java

Lab ở mục 5 dùng `RecordingFile` và `RecordedEvent`. Với ứng dụng phân tích offline, có thể truy xuất:

```java
if (e.getEventType().getName().equals("demo.BusinessOperation")) {
    String code = e.getString("correlationCode");
    String status = e.getString("outcome");
    Duration elapsed = e.getDuration();
    // Áp dụng bộ lọc thời gian, operation, status và quyền truy cập.
}
```

Đây là **đoạn code minh họa trong vòng lặp đã có biến `RecordedEvent e`**, không phải chương trình độc lập. Những API như `getString`, `getInt`, `getDuration` giúp đọc có kiểu; cần xử lý schema/version đúng và không giả định một field do code mới thêm sẽ luôn có trong recording cũ.

### 8.3. Kết quả tiêu biểu

Giả sử nhận được ba event **minh họa**:

| Mã | Operation | Duration | Outcome | Failure category |
| --- | --- | ---: | --- | --- |
| `a-01` | `reserve` | 15 ms | `SUCCESS` | `NONE` |
| `a-02` | `reserve` | 760 ms | `FAILED` | `DEPENDENCY` |
| `a-03` | `reserve` | 82 ms | `CANCELLED` | `INTERRUPTED` |

Nếu recording có threshold 20 ms, `a-01` **không xuất hiện** còn `a-02`/`a-03` có thể xuất hiện. Điều tra `a-02` bằng cùng mã ở trace và JVM events để tìm xem dependency timeout, pool wait, GC hay network có thực sự tham gia. Không dùng bảng đã lọc này để tính business success rate; denominator đã bị thay đổi.

## 9. Các bẫy thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Ghi `orderId`, email hoặc token vào correlation field | Có thể lộ PII/credential qua file `.jfr` | Dùng mã opaque do hệ thống cấp và policy truy cập rõ ràng. |
| Ghi `Exception.toString()`/raw error message | Có thể mang SQL, URL, path, token, dữ liệu khách hàng | Chuyển sang `failureCategory` được duyệt. |
| Truyền `Map`, `enum`, DTO vào field custom Event | JFR không tự serialize các kiểu field đó | Dùng primitive/String/Thread/Class và schema rõ. |
| Đo `begin/end` chỉ quanh `submit()` rồi gọi là “end-to-end latency” | Công việc async có thể chưa xong | Kết thúc vùng đo khi outcome logic đã xác định. |
| Chỉ ghi `SUCCESS` trong nhánh return | Các nhánh exception và cancel mất event | Dùng `try/catch/finally`; outcome đặt trước khi commit. |
| `shouldCommit()` trước khi `end()` và kết luận event nhanh sẽ bị lọc đúng | Duration lúc đó chưa phải duration cuối của operation | Kết thúc timing rồi xét threshold. |
| Thêm stack trace/exception message cho mọi request | Kích thước và rủi ro dữ liệu tăng mạnh | Tắt stack mặc định, bật có thời hạn khi cần. |
| Dùng mã tương quan làm metric label | Cardinality có thể tăng tới số requests | Metrics dùng operation/outcome allowlist; ID trong trace/JFR/log được kiểm soát. |
| Bật threshold 50 ms nhưng tuyên bố đã ghi mọi lỗi | Lỗi nhanh bị loại | Dùng failure event riêng hoặc counters/histograms phù hợp. |
| Tính p99 từ những event được thu vì “chậm” | Dữ liệu bị lọc theo duration | Dùng histogram trên toàn bộ yêu cầu đã instrument. |
| Log cùng một event hai lần ở controller và service | Phân tích có thể đếm đôi operation | Phân biệt scope và event name, hoặc chọn một ranh giới chuẩn. |
| Recording chạy liên tục không giới hạn | Có thể tăng disk/memory footprint và làm khó bảo quản | Đặt duration, maxage, maxsize, quota, sampling, ACL. |
| Dựa vào `eventThread` thay cho correlation code | Thread pool/virtual threads/async phá vỡ giả định 1 thread = 1 request | Truyền correlation context một cách tường minh. |
| Đọc một JFR file rồi khẳng định đã ghi mọi operation | JFR có settings, threshold, buffer và retention | Kiểm tra cấu hình và so sánh với metrics/logs. |

## 10. Bài thực hành mở rộng

**Bài A — Kiểm tra ngưỡng:** thay `.withThreshold(Duration.ZERO)` thành `.withThreshold(Duration.ofMillis(100))` và chạy lại. Với mỗi operation ngủ khoảng 30 ms, thông thường custom event không được ghi (có thể còn phụ thuộc scheduling và thời gian thực tế). Dùng `jfr summary` xác minh. Nếu vẫn có event, kiểm tra elapsed time và whether nó vượt threshold, không suy luận từ số ms yêu cầu `sleep()`.

**Bài B — Thêm nhánh timeout:** mô phỏng một dependency timeout, bắt exception ở business boundary và gán outcome `FAILED`, failureCategory `TIMEOUT`. Kiểm tra bằng `jfr print` rằng **không có message tùy ý** trong event, chỉ có category.

**Bài C — Async:** chuyển bước business sang một `CompletableFuture`. Chọn một trong hai định nghĩa latency: thời gian submit task hoặc thời gian có kết quả thực. Viết hai phiên bản và giải thích vì sao thời lượng khác nhau. Truyền mã tương quan vào callback bằng tham số/context cụ thể, không giả định `ThreadLocal` tự theo task.

**Bài D — Data limits:** thiết kế allowlist gồm tối đa 5 operation, 3 outcome, 6 failure category và correlation code ASCII tối đa 64 ký tự do server cấp. Gửi một chuỗi vượt giới hạn và xác minh event chỉ có sentinel `INVALID`, không chứa giá trị bị từ chối.

**Bài E — Liên hệ JVM:** bật recording với custom event và các JDK events phù hợp, tạo workload có chờ lock/I/O; đọc timeline và xác định chỗ các dữ kiện **tương quan theo thời gian**. Chỉ kết luận nguyên nhân khi có thêm stack, trace hoặc số liệu đo độc lập.

## 11. Checklist đưa vào production

- [ ] Một event name tương ứng **một phạm vi nghiệp vụ được định nghĩa rõ**; schema field/version ổn định.
- [ ] Correlation code là mã nội bộ opaque, nguồn tin cậy, định dạng/độ dài giới hạn; có chính sách xử lý khi thiếu/malformed.
- [ ] `operation`, `outcome`, `failureCategory` đều dùng allowlist; không có payload, PII, token, URL/query hoặc raw exceptions.
- [ ] `begin/end` bao đúng khoảng latency cần đo; các nhánh `SUCCESS`, `FAILED`, `CANCELLED` đều được xử lý.
- [ ] `end()` và `shouldCommit()` đặt đúng thứ tự; công việc tạo payload đặt sau kiểm tra khi có thể.
- [ ] Threshold và sampling phục vụ câu hỏi chẩn đoán; **không suy ra success rate/latency SLI** từ mẫu JFR đã lọc.
- [ ] Kiểm tra event settings thực bằng JFR tools/recording settings, và xác nhận event có thật trong file sau ghi.
- [ ] Dữ liệu được giới hạn cả field size, event rate, stack trace, retention, file access và chia sẻ.
- [ ] Với async/multi-service, context propagation không phụ thuộc thread name; traces/logs/JFR cùng dùng ID đã chuẩn hóa.
- [ ] Đo overhead, CPU, allocation, dung lượng JFR trước khi phát event trên lưu lượng lớn.
- [ ] Kiểm chứng bằng ít nhất một operation success, một failure, một cancellation/timeout và so với metrics/logs để thấy sự khác nhau về semantics.

**Ghi nhớ:** Mục tiêu không phải “nhét mọi dữ liệu nghiệp vụ vào JFR”, mà là tạo **một dấu mốc chẩn đoán gọn, có thể nối với các tín hiệu khác**. Một custom event đáng tin cần bốn yếu tố: **đúng ranh giới thời gian, outcome có nghĩa, mã tương quan an toàn và ngân sách dữ liệu rõ ràng**.

## Tài liệu tham khảo

- [Oracle JDK 21 — `jdk.jfr.Event`: field types, `begin()`, `end()`, `shouldCommit()`, `commit()`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle JDK 21 — `jdk.jfr` package và event settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle JDK 21 — `EventSettings`, threshold và stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [Oracle JDK 21 — `Recording`: enable, start, stop, dump](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle JDK 21 — `RecordingFile` (đọc offline)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Dev.java — Cấu hình JFR (`jfr configure`)](https://dev.java/learn/jvm/jfr/configure/)
- [Oracle Java 21 — Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.pdf)
