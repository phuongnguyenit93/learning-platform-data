# 16.3. Tạo custom event bằng cách kế thừa Event

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Hiểu **custom JFR event** là gì và khi nào nên tạo sự kiện riêng cho hoạt động nghiệp vụ hoặc bước xử lý của ứng dụng.
- Tạo một lớp Java kế thừa `jdk.jfr.Event`; mô tả type và field bằng `@Name`, `@Label`, `@Description`, `@Category`, `@Threshold` và `@StackTrace`.
- Ghi event theo thời điểm hoặc khoảng thời gian bằng `commit()` hoặc `begin()`/`end()`/`commit()`; sử dụng `isEnabled()` và `shouldCommit()` để hạn chế chi phí.
- Bật event trong `Recording`, lưu tệp `.jfr`, đọc lại bằng `RecordingFile`, `jfr` CLI hoặc JDK Mission Control.
- Nhận ra giới hạn về kiểu field, threshold, chi phí instrumentation, dữ liệu nhạy cảm và tính tương thích schema.

**Phiên bản:** API `jdk.jfr.Event` có từ Java 9; toàn bộ ví dụ được viết để biên dịch với **Java 17+**. Ví dụ chính đã được biên dịch bằng `javac --release 17` và chạy kiểm chứng với OpenJDK 24.

## 1. Custom event là gì? Vì sao không chỉ dùng event có sẵn?

**Java Flight Recorder (JFR)** thu các event có timestamp, duration, dữ liệu thuộc tính, thread và (nếu được bật) stack trace. JDK đã có các event như hoạt động GC, cấp phát, thread, lock hay I/O. Tuy nhiên, các event hạ tầng không tự biết bước nghiệp vụ nào đang diễn ra:

- “Bước xác thực đơn hàng mất bao lâu?”
- “Lần gọi provider thanh toán có thành công không?”
- “Một tác vụ nhập dữ liệu đang ở giai đoạn nào khi độ trễ tăng?”
- “Timeout hoặc lỗi ở luồng xử lý nào liên quan tới spike I/O?”

**Custom event** cho phép ứng dụng phát một event theo ngữ nghĩa riêng, có dữ liệu được chọn và thời điểm phù hợp. Ví dụ `demo.PaymentAttempt` chứa `requestId`, `amountCents` và `successful`, đồng thời JFR tự ghi thời điểm, thời lượng và thread.

Custom JFR event **không thay thế** structured logging, distributed tracing hoặc business metrics:

| Dữ liệu | Câu hỏi chủ yếu | Giới hạn |
|---|---|---|
| Log | Chuyện gì xảy ra ở một thời điểm, lỗi nào được in ra? | Dễ nhiều dữ liệu; phụ thuộc log level và correlation |
| Metrics | Lượng request, tỷ lệ lỗi, latency trung bình/phân vị thay đổi ra sao? | Thường tổng hợp, ít chi tiết về từng event |
| Distributed trace | Một giao dịch đi qua những service/span nào? | Cần propagation/instrumentation xuyên dịch vụ |
| Custom JFR event | Bước cụ thể bên trong JVM xảy ra khi nào, bao lâu, payload nào và stack/thread ra sao? | Chỉ chứa event đã bật, đã phát, vượt threshold; thường local đến JVM |

Khi cần phối hợp, lưu correlation ID đã được chọn an toàn trong payload JFR để đối chiếu log/trace. Tránh ghi token, mật khẩu, dữ liệu khách hàng, nội dung request nhạy cảm hoặc payload lớn.

## 2. Mô hình API: lớp Event trở thành event type

Cách tĩnh và rõ nhất là khai báo một lớp kế thừa `jdk.jfr.Event`:

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.WorkStep")
@Label("Work step")
class WorkStep extends Event {
    @Label("Step")
    String step;
}
```

Đây là **đoạn định nghĩa type**, chưa phải chương trình độc lập có `main`. Sau khi event type đã được bật trong một recording, ứng dụng có thể tạo đối tượng và gọi `commit()`. Mỗi lần `commit()` trên một instance đủ điều kiện sẽ ghi một event vào JFR; định nghĩa type không tự phát event chỉ vì lớp được nạp.

### 2.1. Những annotation thường dùng

| Annotation | Đặt tại | Vai trò |
|---|---|---|
| `@Name("demo.WorkStep")` | Lớp event | Đặt tên machine-readable ổn định để lọc và phân tích; ưu tiên tên phân cấp rõ, tránh trùng |
| `@Label("Work step")` | Lớp hoặc field | Nhãn dễ hiểu cho công cụ hiển thị |
| `@Description("...")` | Lớp hoặc field | Giải thích ý nghĩa event/field |
| `@Category({"Application", "Orders"})` | Lớp event | Nhóm event trong đường dẫn category cho UI |
| `@Threshold("10 ms")` | Lớp event | Đề xuất ngưỡng duration mặc định; các event ngắn hơn ngưỡng được lọc |
| `@StackTrace(true)` | Lớp event | Cấu hình mặc định có thu stack trace tại lúc commit hay không |
| `@Enabled(false)` | Lớp event | Tắt type theo cấu hình mặc định; recording có thể bật lại |
| `@Timespan(Timespan.MILLISECONDS)` | Field số nguyên mô tả thời lượng khác | Khai báo đơn vị để công cụ trình bày đúng |
| `@DataAmount(DataAmount.BYTES)` | Field số nguyên mô tả lượng dữ liệu | Biểu diễn đơn vị bytes thay vì số trần |

Các annotation như `@Label` và `@Category` giúp công cụ trình bày dữ liệu; tên trong `@Name` là định danh mà bộ lọc và code consumer sử dụng. Chọn tên ổn định khi có dashboard/phân tích phụ thuộc vào nó. Tên type mặc định nếu bỏ `@Name` thường được suy ra từ tên lớp, nhưng đổi package/class có thể ảnh hưởng người dùng downstream.

**Annotation cung cấp mặc định, cấu hình recording quyết định thu thực tế.** Chẳng hạn `@Threshold("10 ms")` là giá trị mặc định; code `recording.enable(...).withThreshold(...)` hoặc tệp `.jfc` có thể đặt threshold khác trong recording cụ thể.

### 2.2. Những kiểu field được JFR hỗ trợ

Theo hợp đồng `jdk.jfr.Event` trên Java 17/21:

- Primitive: `boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`.
- Reference: `String`, `Thread` và `Class`.
- **Không** dùng `List`, `Map`, array, enum hoặc đối tượng domain tùy ý làm field rồi mong JFR tự tuần tự hóa; field không hỗ trợ có thể bị **bỏ qua âm thầm**.
- Field `static` không nằm trong payload. Field `transient` cũng bị loại khỏi event data, kể cả khi kiểu của nó được hỗ trợ.

Ví dụ, nếu có `OrderStatus status` với kiểu enum, hãy chuyển **giá trị có giới hạn và an toàn** thành `String statusName`, thay vì khai báo enum trực tiếp. Nếu muốn ghi kích thước file, dùng `long bytes` và `@DataAmount(DataAmount.BYTES)`. Đừng tạo JSON khổng lồ trong một `String` chỉ để vượt giới hạn kiểu; như vậy tăng chi phí và làm dữ liệu khó phân tích.

Đối với subclass `Event`, điền field bằng gán Java trực tiếp (`event.step = "validate";`). Phương thức `Event.set(int, Object)` dành cho event được tạo **động** bằng `EventFactory`, không phải cách gán field cho lớp `extends Event` thông thường.

## 3. Vòng đời của một custom event

### 3.1. Instant event: một thời điểm

```java
WorkStep event = new WorkStep();
event.step = "completed";
event.commit();
```

Đây là **đoạn sử dụng type `WorkStep` vừa khai báo**, không phải chương trình standalone. Nếu type được bật và đạt các setting hiện hành, `commit()` ghi giá trị field và thời điểm; vì không gọi `begin()`, duration về cơ bản là không có khoảng kéo dài. Một event như vậy có thể bị loại nếu áp dụng **duration threshold dương**.

Phù hợp với một mốc trạng thái như “đã nạp config” hoặc “retry đã được lên lịch”, khi thời gian **giữa** các mốc không phải nội dung của chính event.

### 3.2. Duration event: một khoảng xử lý

```java
WorkStep event = new WorkStep();
event.step = "validate";
event.begin();
try {
    // Phần việc cần đo ở đây.
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
```

Đây là **đoạn cấu trúc minh họa**: cần thay comment bằng xử lý thực tế. `begin()` đánh dấu đầu khoảng; `end()` đánh dấu cuối; `commit()` gửi event có timestamp, duration và field. Nếu đã `begin()` nhưng chưa `end()`, `commit()` có thể tự đóng khoảng; tuy nhiên dùng `finally` và `end()` rõ ràng giúp giữ đúng thời gian ngay cả khi xử lý thất bại.

**Duration là elapsed time**, có thể bao gồm thời gian chờ I/O, khóa, scheduler, GC hoặc sleep. Nó **không phải** CPU time. Đừng lấy duration của custom event rồi kết luận method đã thực sự dùng ngần ấy CPU.

### 3.3. Kiểm tra điều kiện ghi

- `isEnabled()`: type có được bật bởi ít nhất một recording đang chạy hay không. Có thể dùng để bỏ qua việc xây dựng payload đắt tiền.
- `shouldCommit()`: event hiện có đủ điều kiện ghi theo cấu hình bật và **duration threshold** hay không. Kiểm tra **sau `end()`** với event đo duration.
- `commit()`: hoàn tất ghi event khi điều kiện recording cho phép; nó **không có nghĩa** cứ được gọi là file chắc chắn chứa event, vì type có thể bị tắt/ngưỡng chặn và recording có thể chưa hoạt động.

Khi payload tốn kém (ví dụ dựng một chuỗi mô tả chi tiết), mẫu hữu ích là chỉ tính phần đó **sau `shouldCommit()`**. Không cần micro-optimize cho mọi event hiếm; nhưng sự kiện phát hàng trăm nghìn lần mỗi giây cần xem overhead.

## 4. Ví dụ Java 17+ hoàn chỉnh: tạo custom event và đọc lại recording

Ví dụ này định nghĩa event thanh toán giả lập, có metadata, ba field được hỗ trợ và duration được đo rõ ràng. Chương trình tạo **hai event**, ghi ra `payment-attempts.jfr` rồi dùng JFR consumer API đọc đúng hai event đã tạo.

### 4.1. Mã nguồn

Tạo tệp **`CustomJfrEventDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class CustomJfrEventDemo {
    @Name("demo.PaymentAttempt")
    @Label("Payment attempt")
    @Description("Outcome and elapsed time of a payment attempt")
    @Category({"Application", "Payments"})
    @Threshold("10 ms")
    @StackTrace(true)
    public static class PaymentAttempt extends Event {
        @Label("Request ID")
        String requestId;

        @Label("Amount, cents")
        long amountCents;

        @Label("Successful")
        boolean successful;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("payment-attempts.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(PaymentAttempt.class)
                    .withThreshold(Duration.ofMillis(10))
                    .withStackTrace();
            recording.start();

            for (int i = 1; i <= 2; i++) {
                PaymentAttempt event = new PaymentAttempt();
                event.requestId = "req-" + i;
                event.amountCents = 100L * i;
                event.begin();
                try {
                    Thread.sleep(30);
                    event.successful = (i == 1);
                } finally {
                    event.end();
                    if (event.shouldCommit()) {
                        event.commit();
                    }
                }
            }

            recording.stop();
            recording.dump(file);
        }

        List<RecordedEvent> matching = RecordingFile.readAllEvents(file).stream()
                .filter(e -> e.getEventType().getName().equals("demo.PaymentAttempt"))
                .toList();

        System.out.println("Custom events: " + matching.size());
        for (RecordedEvent event : matching) {
            System.out.println(event.getString("requestId")
                    + ", cents=" + event.getLong("amountCents")
                    + ", success=" + event.getBoolean("successful"));
        }
        System.out.println("Recording: " + file.getFileName());
    }
}
```

### 4.2. Biên dịch và chạy

Ở thư mục chứa tệp, sử dụng **JDK 17 trở lên**:

```bash
javac CustomJfrEventDemo.java
java CustomJfrEventDemo
```

Chương trình có output như sau (**đã kiểm chứng bằng OpenJDK 24, biên dịch với `--release 17`**):

```text
Custom events: 2
req-1, cents=100, success=true
req-2, cents=200, success=false
Recording: payment-attempts.jfr
```

Vì chương trình dùng `Thread.sleep(30)` và ngưỡng event là 10 ms, hai event được giữ lại trong lần thử đã kiểm chứng. `Thread.sleep` chỉ bảo đảm ngủ **ít nhất** khoảng thời gian được yêu cầu trong điều kiện bình thường; duration thực tế sẽ dao động theo hệ điều hành và tải. Output của chương trình **không in** các duration biến thiên đó.

### 4.3. Đọc file bằng JDK CLI

Ngay sau khi chạy:

```bash
jfr summary payment-attempts.jfr
jfr print --events demo.PaymentAttempt payment-attempts.jfr
```

Trong `jfr print`, bạn sẽ thấy dạng:

```text
demo.PaymentAttempt {
  startTime = ...          
  duration = ... ms
  requestId = "req-1"
  amountCents = 100
  successful = true
  eventThread = "main" (...)
  stackTrace = [...]
}
```

Đây chỉ là **dạng minh họa**, không phải stdout verbatim. `startTime`, `duration`, `javaThreadId` và stack line number thay đổi theo môi trường. Sự kiện thứ hai chứa `req-2`, `amountCents = 200` và `successful = false`. Lệnh CLI có thể hiển thị thêm metadata/runtime events tùy JDK và cấu hình.

Bạn cũng có thể mở `payment-attempts.jfr` bằng **JDK Mission Control (JMC)**, vào Event Browser (tên UI tùy bản phát hành), tìm `demo.PaymentAttempt` để xem từng field, duration, thread và stack. Việc mở file offline **không cần** JVM đã tạo file còn hoạt động.

### 4.4. Giải thích từng cơ chế

1. `PaymentAttempt extends Event` xác định **một event type** với tên ổn định `demo.PaymentAttempt` và các thuộc tính `String`, `long`, `boolean`.
2. `@Category`/`@Label`/`@Description` cung cấp thông tin trình bày cho công cụ. `@Threshold` và `@StackTrace` đưa ra setting mặc định.
3. `recording.enable(PaymentAttempt.class).withThreshold(Duration.ofMillis(10)).withStackTrace()` bảo đảm type này được thu trong **recording của ví dụ** với ngưỡng và stack trace đã chọn. Nó có thể ghi đè giá trị mặc định của annotation.
4. `begin()` và `end()` đo elapsed time của tác vụ; `successful` được gán trong `try`, còn `finally` bảo đảm đóng khoảng và thử phát event cả khi tác vụ kết thúc bất thường.
5. `shouldCommit()` tránh gọi `commit()` khi event không đáp ứng setting hiện tại.
6. `stop()` rồi `dump(file)` ghi recording ra file. `try` bảo đảm đóng tài nguyên.
7. `RecordingFile.readAllEvents(file)` trả **mọi event** trong file; lọc theo `getEventType().getName()` để đếm **chỉ event custom**. Trong recording thực, còn có thể có nhiều event JDK khác.
8. `RecordedEvent.getString/getLong/getBoolean` đọc các field đúng kiểu. `RecordedEvent` còn cho phép đọc `getStartTime()`, `getDuration()`, `getThread()` và `getStackTrace()` khi dữ liệu có sẵn.

**Giới hạn của ví dụ:** `RecordingFile.readAllEvents` tải tất cả event vào bộ nhớ, phù hợp file nhỏ. Với recording lớn, dùng `RecordingFile` đọc event tuần tự hoặc công cụ phân tích streaming để tránh tiêu thụ bộ nhớ không cần thiết.

## 5. Cấu hình event: annotation và recording settings

### 5.1. Ngưỡng duration

`@Threshold("10 ms")` trên class có nghĩa thời lượng nhỏ hơn ngưỡng đó thường không được ghi theo mặc định. Recording còn có thể đặt:

```java
recording.enable(PaymentAttempt.class)
         .withThreshold(Duration.ofMillis(50))
         .withStackTrace();
```

Đây là **đoạn thay đổi cấu hình** dùng trong một `Recording` đã được tạo, không phải chương trình độc lập. Lúc này ngưỡng ghi của recording là **50 ms**, thay vì mặc định 10 ms từ annotation. Với workload mỗi attempt chỉ khoảng 30 ms, `shouldCommit()` có thể trả `false` và không có event trong file.

**Cẩn thận khi kiểm tra:** nếu nhiều recording đồng thời bật cùng type với các threshold khác nhau, hành vi `shouldCommit()` phụ thuộc những cấu hình đang hoạt động; không đơn giản là kiểm tra duy nhất một file. Đặt cùng thời gian/cấu hình và ghi lại các setting để bài đo tái lập được.

Đối với event **instant** (không gọi `begin/end`), threshold duration dương có thể khiến event không xuất hiện. Với loại event đánh dấu mốc, nên dùng threshold `0` hoặc setting phù hợp.

### 5.2. Stack trace và kích thước recording

`withStackTrace()` ghi stack tại nơi `commit()` nếu có, giúp biết call site của event. Đây không phải một full execution trace của toàn bộ phương thức giữa `begin` và `end`. Stack trace, field String dài và mật độ sự kiện cao đều làm tăng chi phí bộ nhớ/CPU của recording.

Khi event cực thường xuyên, cân nhắc:

- Chỉ phát tại những điểm có giá trị chẩn đoán (slow operation, timeout, retry, thay đổi trạng thái quan trọng).
- Chọn threshold dựa trên SLO và mục tiêu phân tích.
- Chỉ ghi field nhỏ, ổn định, đã được xử lý dữ liệu nhạy cảm.
- Bật/tắt stack trace theo nhu cầu, thử nghiệm overhead và dung lượng trên tải thực.
- Tắt event bằng cấu hình ở môi trường không cần quan sát liên tục.

### 5.3. Không nhầm enabled với recorded

Có ba điều kiện khác nhau: **event type đã được bật**, **một event instance đã thực sự commit**, và **bản ghi được lưu/bao phủ thời điểm đó**. `isEnabled() == true` không bảo đảm ngay lập tức có event trong tệp; instance có thể chưa commit, duration không qua threshold hoặc recording chưa được dump/bao phủ mốc cần tìm.

Ngược lại, khi `jfr print` không thấy type custom, trước khi nghi code bị lỗi hãy kiểm tra: tên type, setting enabled, threshold, việc gọi `commit`, recording start/stop, nơi lưu tệp và khoảng thời gian.

## 6. Đưa custom event vào mã ứng dụng thực

### 6.1. Đặt event quanh điểm có ý nghĩa

Một event nên phản ánh **một khoảng công việc rõ ràng**, ví dụ:

```text
paymentAttempt.begin()
    gọi provider
    giải mã kết quả
    quyết định retry hoặc hoàn tất
paymentAttempt.end()
paymentAttempt.commit()
```

Đây là sơ đồ tiến trình, **không phải mã Java chạy được**. Hãy quyết định phạm vi đo từ trước: event chỉ đo network round trip, hay toàn bộ attempt gồm validate, retry và xử lý kết quả? Hai cách khác nhau tạo duration khác nhau. Ghi rõ phạm vi trong `@Description` hoặc tài liệu.

Cần bảo đảm `end()` nằm trong `finally`; nếu request thất bại/throw, event vẫn phản ánh thời gian và trạng thái thất bại. Nếu log/trace đang có correlation ID, có thể thêm cùng ID an toàn dưới dạng `String` field để liên kết với JFR.

### 6.2. Khi payload tốn công tính toán

Một phương án là tạo event, đo thời gian xử lý, rồi **sau `shouldCommit()` mới tính các field đắt** như mô tả tóm tắt từ một object lớn. Ví dụ sơ đồ:

```text
tạo event -> begin -> xử lý -> end
                              |
                              v
                         shouldCommit?
                          /        \
                       false       true
                        |            |
                       bỏ qua      xây payload an toàn -> commit
```

Nếu không muốn dựng event không cần thiết, kiểm tra `isEnabled()` trước việc chuẩn bị dữ liệu/phân tích stack tốn kém. Việc bỏ qua instrumentation phải **không làm đổi hành vi nghiệp vụ**: code xử lý chính luôn chạy dù JFR bị tắt.

Không dùng event JFR như cơ chế đảm bảo gửi audit bắt buộc hoặc thanh toán: recording có thể bị tắt, lọc theo threshold, vòng đệm có giới hạn hay lỗi ghi tệp. Các nghiệp vụ cần đảm bảo giao nhận phải có hệ thống dữ liệu/audit riêng.

### 6.3. Tên và schema cho vòng đời lâu dài

Khi người khác đã viết query/dashboard dựa trên `demo.PaymentAttempt` và các tên field, đổi tên type/field có thể phá bộ phân tích. Nên chọn:

- Tên event phân cấp, ổn định, phân biệt domain và loại công việc.
- Field tên rõ đơn vị: `amountCents` tốt hơn `amount`; nếu có `latencyMs` nên gắn `@Timespan(Timespan.MILLISECONDS)`.
- Category/Label dùng cho cách hiển thị, không lạm dụng chúng làm định danh thay cho `@Name`.
- Chỉ thêm field hữu ích, tránh payload nhiều chiều/biến thiên quá lớn.
- Quy tắc riêng cho dữ liệu được phép ghi vào event, thời gian giữ recording và ai được tải file.

JFR events có thể được tiêu thụ bằng **JDK Mission Control**, `jfr print`, `RecordingFile` hoặc ứng dụng phân tích nội bộ. Không giả định một consumer tự hiểu field mới hay bắt buộc mọi consumer xử lý mọi phiên bản schema.

## 7. Những hiểu lầm phổ biến và cách sửa

| Kết luận sai | Cách hiểu đúng |
|---|---|
| “Chỉ cần tạo subclass `Event` là JFR tự phát event khi method chạy” | Phải **tạo instance, gán field và gọi `commit()`**; type phải được bật bởi recording |
| “`begin()` đã ghi một event hoàn chỉnh” | `begin()` chỉ đánh dấu điểm đầu duration; `commit()` mới phát event |
| “`end()` tự ghi event” | `end()` chỉ xác định điểm cuối; vẫn cần `commit()` |
| “`isEnabled()` true nghĩa là event chắc chắn có trong file” | Event còn phải được commit, qua threshold và nằm trong recording được lưu |
| “Array/enum/POJO là field JFR hợp lệ vì Java compile được” | Field kiểu không được hỗ trợ có thể **bị bỏ qua âm thầm** |
| “`@Label` đặt tên API để `jfr print` lọc” | `@Name`/event type name là định danh; Label dành cho hiển thị |
| “Duration event là CPU time” | Đó là **elapsed time**, bao gồm cả thời gian chờ |
| “Không thấy event nghĩa là operation không xảy ra” | Có thể type tắt, chưa commit, threshold loại, file ghi sai thời gian hoặc name filter sai |
| “Ghi mọi object/stack vào event càng chi tiết càng tốt” | Payload lớn/high frequency tăng overhead, có thể chứa dữ liệu nhạy cảm |
| “Custom JFR event có thể thay bảng audit đảm bảo” | JFR là quan sát/chẩn đoán; không có bảo đảm delivery như hệ thống nghiệp vụ/audit |

### Khi đọc kết quả, tự hỏi

1. Event đo **đúng đoạn code** cần tìm chưa?
2. Recording có chạy và bật đúng **event type name** không?
3. Duration threshold/stackTrace phù hợp với loại sự cố cần quan sát không?
4. Event fields có các kiểu hỗ trợ và giá trị đã gán trước `commit()` chưa?
5. Tệp mở trong JMC/CLI có bao phủ đúng **thời gian, JVM và workload** không?
6. Duration đo elapsed time hay CPU? Có cần đối chiếu log/metrics/traces để tìm nguyên nhân không?

## 8. Bài tập mở rộng

**Bài tập A — Instant và duration.** Tạo hai custom event types: một event “request accepted” chỉ ghi mốc, một event “request processed” đo thời gian. Với type instant, dùng threshold phù hợp (thường `0`). Chứng minh bằng `jfr print --events ...` rằng hai type mang các thuộc tính khác nhau.

**Bài tập B — Threshold.** Chạy ví dụ chính với threshold 10 ms và sau đó thay bằng 50 ms, giữ thời gian xử lý khoảng 30 ms. Giải thích vì sao số event có thể đổi; không dựa vào `sleep` để viết assertion thời gian chính xác tuyệt đối.

**Bài tập C — Field không được hỗ trợ.** Thêm `String[]` hoặc `enum` vào lớp event và so sánh danh sách field khi `jfr print`. Phân biệt “Java cho phép khai báo” với “JFR đưa field đó vào schema”.

**Bài tập D — Quan sát trong JMC.** Mở file `payment-attempts.jfr` trong JDK Mission Control; lọc `demo.PaymentAttempt` và đối chiếu `requestId`, `amountCents`, `successful`, duration và stack trace với kết quả CLI. Tìm thông tin giúp liên kết đến một request cụ thể mà không đưa thông tin nhạy cảm vào payload.

## Tài liệu tham khảo chính thức

- [Java SE 21 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): subclass, field hỗ trợ, `begin/end/commit/isEnabled/shouldCommit`.
- [Java SE 21 — `jdk.jfr` package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): định nghĩa event, metadata, các cài đặt `enabled`/`threshold`/`stackTrace` và các annotation.
- [Java SE 21 — `Recording`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình recording, start/stop/dump.
- [Java SE 21 — `RecordingFile`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc event từ tệp JFR.
- [Java SE 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): tóm tắt và lọc event từ CLI.
