# `jdk.jfr` cùng `jdk.jfr.consumer` trong ứng dụng mô-đun Java

## 1. Hai package, một mô-đun Java

**Java Flight Recorder (JFR)** là cơ chế ghi nhận sự kiện về hoạt động JVM và ứng dụng. Thay vì chỉ in log theo từng dòng, JFR lưu các sự kiện có kiểu và metadata: tên sự kiện, thời gian, thời lượng, thread, trường dữ liệu và thông tin liên quan nếu được bật. Có thể dùng nó để nghiên cứu hiệu năng, độ trễ, lỗi vận hành và hành vi runtime.

Java cung cấp hai package quan trọng:

| Package | Vai trò | API thường gặp |
| --- | --- | --- |
| `jdk.jfr` | **Tạo sự kiện và điều khiển quá trình ghi** | `Event`, `Recording`, `FlightRecorder`, `EventType`, `Name`, `Label`, `Configuration` |
| `jdk.jfr.consumer` | **Đọc/phân tích sự kiện đã ghi hoặc nhận luồng sự kiện** | `RecordingFile`, `RecordedEvent`, `RecordingStream`, `EventStream` |

**Cốt lõi của bài:** `jdk.jfr` và `jdk.jfr.consumer` là **hai package thuộc cùng một JPMS module tên `jdk.jfr`**. Trong một ứng dụng Java có `module-info.java`, chỉ cần khai báo:

```java
module com.example.jfrapp {
    requires jdk.jfr;
}
```

Không viết `requires jdk.jfr.consumer;`: đây **không phải tên mô-đun**. `requires` khai báo phụ thuộc **module**, không phải từng package.

**Tính hiện hành:** JFR và module `jdk.jfr` đã là API của JDK từ Java 9; các API consumer tiếp tục được duy trì trong Java 17, 21 và các JDK mới. Bài này dùng **Java 17+**, không dựa vào API preview, thư viện JFR thương mại cũ hoặc cờ thử nghiệm không còn cần thiết.

## 2. Mối quan hệ giữa JPMS và JFR

**JPMS (Java Platform Module System)** quản lý module, quyền đọc module và package được xuất ra ngoài.

Một ứng dụng mô-đun cần phân biệt ba yếu tố:

1. **Module `jdk.jfr`:** cung cấp API tạo/điều khiển sự kiện và consumer.
2. **Module ứng dụng**, ví dụ `com.example.jfrapp`: khai báo `requires jdk.jfr;` để trình biên dịch và runtime biết phụ thuộc.
3. **Package trong source của ứng dụng**, ví dụ `com.example.jfrapp`: chứa lớp thực thi và lớp sự kiện tùy biến.

JPMS gọi cơ chế này là **readability**: module ứng dụng đọc được module `jdk.jfr` khi có `requires jdk.jfr;`. Module `jdk.jfr` công khai cả hai package API `jdk.jfr` và `jdk.jfr.consumer`, nên mã ứng dụng có thể `import` các lớp ở cả hai.

Ví dụ các câu import đều hợp lệ khi có `requires jdk.jfr;`:

```java
import jdk.jfr.Event;
import jdk.jfr.Recording;
import jdk.jfr.FlightRecorder;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordedEvent;
```

**Không cần `requires java.base;`** vì mọi module Java tự đọc `java.base`. Cũng **không cần `exports com.example.jfrapp;`** nếu module này chỉ là ứng dụng tự chạy và không có module khác cần biên dịch gọi công khai các lớp của nó.

Ngược lại, nếu bạn xây dựng **thư viện** có API công khai trong package riêng để module khác dùng, hãy cân nhắc `exports` chính package công khai ấy. Nếu một thư viện tích hợp reflection như framework serialization cần truy cập sâu vào một package, việc dùng `opens` có thể liên quan đến **framework đó**; bản thân việc tạo sự kiện JFR và đọc dữ liệu qua API công khai trong ví dụ dưới đây **không yêu cầu `opens`**.

### Xem mô-đun do JDK cung cấp

```bash
java --describe-module jdk.jfr
```

Một JDK phù hợp sẽ liệt kê module `jdk.jfr` và các package được xuất, trong đó có `jdk.jfr` và `jdk.jfr.consumer`. Danh sách còn có thể có package nội bộ hoặc export có điều kiện; **không phụ thuộc vào package nội bộ `jdk.jfr.internal`** trong mã ứng dụng.

Nếu dùng **custom runtime image** tạo bởi `jlink`, phải đảm bảo ảnh runtime có module `jdk.jfr`. Khai báo `requires jdk.jfr;` của ứng dụng là một cách để công cụ phân giải module biết phụ thuộc khi đưa ứng dụng vào ảnh.

## 3. Phía ghi: `jdk.jfr.Event` và `Recording`

Một sự kiện JFR tùy biến thường được định nghĩa bằng cách **kế thừa `jdk.jfr.Event`**:

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.OrderProcessed")
@Label("Order processed")
class OrderProcessed extends Event {
    @Label("Order ID")
    String orderId;

    @Label("Amount")
    long amount;
}
```

Đây là **đoạn mã minh họa** cho một lớp sự kiện, chưa phải chương trình chạy độc lập. Ý nghĩa:

- `@Name("demo.OrderProcessed")` đặt tên sự kiện ổn định để lọc ở phía consumer. Nên chọn tên có namespace rõ ràng, tránh trùng với loại sự kiện khác.
- `@Label` cung cấp nhãn hiển thị dễ hiểu cho công cụ phân tích.
- Hai trường `orderId` và `amount` là **payload** sẽ xuất hiện trong recording nếu event được ghi.
- Kiểu trường `String` và `long` được JFR hỗ trợ. Không giả định mọi kiểu Java đều thành field JFR: các mảng, collection hoặc object tùy ý không tự được ghi thành cấu trúc tùy biến.

Tạo event và gọi `commit()`:

```java
OrderProcessed event = new OrderProcessed();
event.orderId = "A-100";
event.amount = 250L;
event.commit();
```

`commit()` gửi sự kiện tới hệ thống JFR **khi event được bật và thỏa cài đặt ghi**. Nó không mặc nhiên tạo một tệp `.jfr` riêng, và không đảm bảo sự kiện được giữ lại khi không có recording đang chạy hoặc event đã bị tắt/bị lọc.

### Vòng đời `Recording`

`Recording` trong package `jdk.jfr` điều khiển một session ghi:

1. Tạo `Recording`.
2. Cấu hình loại event, ngưỡng thời gian, kích thước hoặc thời hạn lưu dữ liệu khi cần.
3. Gọi `start()`.
4. Chạy mã tạo event.
5. Gọi `stop()`.
6. Gọi `dump(Path)` để ghi tệp `.jfr`, sau đó `close()` để giải phóng tài nguyên.

`Recording` triển khai `AutoCloseable` nên nên được đặt trong **try-with-resources**. Có thể tạo từ `Configuration.getConfiguration("default")` hoặc `"profile"` để dùng cấu hình phổ biến của JDK; với ví dụ đơn giản, có thể bắt đầu từ `new Recording()` và **bật rõ loại event tùy biến**.

**Thời gian sự kiện:** `Event.begin()` và `Event.end()` đo khoảng thời gian thao tác, nếu cần; gọi `commit()` cũng có thể kết thúc event đã `begin()` nhưng chưa `end()`. `shouldCommit()` giúp tránh tính toán payload tốn kém khi cấu hình hiện tại sẽ không ghi event. Không phải sự kiện nào cũng cần đo thời lượng.

## 4. Phía đọc: `jdk.jfr.consumer`

Khi có tệp recording, mã phân tích **không cần tạo event mới**. Nó có thể dùng:

- `RecordingFile`: đọc tuần tự từng sự kiện từ một tệp `.jfr`.
- `RecordedEvent`: biểu diễn một sự kiện đã được ghi, cung cấp metadata và API lấy trường theo tên.
- `RecordedEvent.getEventType().getName()`: lấy tên loại sự kiện để lọc, ví dụ `demo.OrderProcessed`.
- `RecordedEvent.getString("orderId")` và `getLong("amount")`: đọc payload theo **tên trường và kiểu phù hợp**.
- `RecordingFile.readAllEvents(path)`: tiện cho tệp nhỏ khi muốn có `List<RecordedEvent>`, nhưng có thể tiêu tốn nhiều bộ nhớ với tệp lớn.

Cách đọc tuần tự, tiết kiệm bộ nhớ hơn:

```java
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("demo.OrderProcessed".equals(event.getEventType().getName())) {
            System.out.println(event.getString("orderId"));
        }
    }
}
```

Đây là **đoạn mã minh họa**, giả định `path` là `java.nio.file.Path` trỏ tới recording hợp lệ. Trong thực tế tệp có thể chứa **nhiều loại sự kiện JVM và ứng dụng**. Hãy lọc chính xác loại quan tâm, không giả định sự kiện đầu tiên luôn là event của mình.

JFR recording là dữ liệu có cấu trúc, **không phải log text** để tách chuỗi bằng regex. Dùng những phương thức của `RecordedEvent` và các đối tượng consumer liên quan. Một số trường có thể bị thiếu hoặc khác kiểu giữa event types; nếu xử lý tệp ngoại lai, hãy kiểm tra schema/metadata thay vì gọi `getString` vô điều kiện.

## 5. Ví dụ ứng dụng JPMS hoàn chỉnh trên Java 17+

Ví dụ sau sử dụng **cả package `jdk.jfr` và `jdk.jfr.consumer` trong cùng một module có tên**. Ứng dụng tạo một sự kiện, ghi recording ra tệp tạm, đọc lại event và xóa tệp tạm.

### 5.1. Cấu trúc thư mục

```text
src/
└── com.example.jfrapp/
    ├── module-info.java
    └── com/
        └── example/
            └── jfrapp/
                └── Main.java
```

Đây là cấu trúc **module source path**: thư mục ngay dưới `src` mang đúng tên module `com.example.jfrapp`. Package được ánh xạ thành đường dẫn `com/example/jfrapp`.

### 5.2. Tệp `src/com.example.jfrapp/module-info.java`

```java
module com.example.jfrapp {
    requires jdk.jfr;
}
```

Chỉ một `requires jdk.jfr;` để dùng cả hai package. Không khai báo `requires jdk.jfr.consumer`.

### 5.3. Tệp `src/com.example.jfrapp/com/example/jfrapp/Main.java`

```java
package com.example.jfrapp;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

@Name("demo.OrderProcessed")
@Label("Order processed")
class OrderProcessed extends Event {
    @Label("Order ID")
    String orderId;
    @Label("Amount")
    long amount;
}

public class Main {
    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("JFR unavailable");
            return;
        }

        Path output = Files.createTempFile("demo-recording-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(OrderProcessed.class)
                         .withThreshold(Duration.ZERO)
                         .withoutStackTrace();
                recording.start();

                OrderProcessed event = new OrderProcessed();
                event.orderId = "A-100";
                event.amount = 250L;
                event.commit();

                recording.stop();
                recording.dump(output);
            }

            int matching = 0;
            try (RecordingFile file = new RecordingFile(output)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent event = file.readEvent();
                    if (!"demo.OrderProcessed".equals(
                            event.getEventType().getName())) {
                        continue;
                    }
                    System.out.println(
                            "event=" + event.getEventType().getName());
                    System.out.println(
                            "orderId=" + event.getString("orderId"));
                    System.out.println(
                            "amount=" + event.getLong("amount"));
                    matching++;
                }
            }
            System.out.println("matchingEvents=" + matching);
        } finally {
            Files.deleteIfExists(output);
        }
    }
}
```

**Cách chương trình hoạt động:**

1. `FlightRecorder.isAvailable()` kiểm tra JVM có hỗ trợ JFR. Nếu không, chương trình thông báo và kết thúc; ví dụ không cố tự khởi tạo recording trên runtime không hỗ trợ.
2. `Files.createTempFile(...)` tạo đường dẫn tệp tạm với đuôi `.jfr`; `finally` bảo đảm xóa khi thao tác hoàn tất hoặc gặp lỗi.
3. `recording.enable(OrderProcessed.class)` bật loại event riêng, `withThreshold(Duration.ZERO)` cho phép event dù thời lượng rất ngắn, `withoutStackTrace()` bỏ stack trace để giữ ví dụ nhẹ.
4. `recording.start()` bắt đầu ghi, sau đó event có dữ liệu cố định được `commit()` một lần.
5. `recording.stop()` kết thúc thu thập; `recording.dump(output)` lưu nội dung recording vào tệp.
6. `RecordingFile` đọc tệp tuần tự, **lọc theo tên sự kiện** và dùng `getString`, `getLong` để lấy dữ liệu.
7. `try-with-resources` đóng `Recording` và `RecordingFile`; ứng dụng không để file JFR tạm lại sau khi chạy.

**Vì sao dùng `@Name`?** Consumer thường phân tích file ở một tiến trình khác, không tham chiếu trực tiếp tới lớp Java `OrderProcessed` đã tạo event. Tên loại sự kiện là điểm nhận diện ổn định ở định dạng recording.

### 5.4. Biên dịch và chạy

Đặt terminal tại **thư mục cha của `src`** và dùng JDK 17 hoặc mới hơn:

```bash
javac --release 17 -d out --module-source-path src -m com.example.jfrapp
java --module-path out --module com.example.jfrapp/com.example.jfrapp.Main
```

Giải thích tham số:

- `--release 17`: biên dịch theo mức API/ngôn ngữ Java 17.
- `-d out`: ghi class file ra `out`.
- `--module-source-path src`: tìm module trong `src/<tên-module>/...`.
- `-m com.example.jfrapp`: chọn module cần biên dịch.
- `--module-path out`: cho launcher tìm module đã biên dịch.
- `--module com.example.jfrapp/com.example.jfrapp.Main`: chạy `Main` của module đã chọn.

**Đầu ra đã kiểm chứng trên OpenJDK với JFR khả dụng:**

```text
event=demo.OrderProcessed
orderId=A-100
amount=250
matchingEvents=1
```

Nếu JVM không hỗ trợ JFR hoặc runtime image thiếu thành phần cần thiết, chương trình có thể không chạy được như ví dụ hoặc sẽ in `JFR unavailable` khi bước kiểm tra có thể thực hiện. Tệp tạm có tên ngẫu nhiên nhưng không được in, nên khi môi trường hoạt động bình thường **bốn dòng trên là đầu ra ổn định**.

**Đã kiểm chứng:** mã được biên dịch với `javac --release 17`, chạy bằng `java --module-path ... --module ...` và trả đúng bốn dòng trên. Không cần thêm `--add-exports`, `--add-opens` hay classpath cho các package JFR công khai.

## 6. Dùng consumer theo thời gian thực thay vì đọc tệp

`jdk.jfr.consumer` không chỉ có `RecordingFile`. Trong Java hiện đại, package còn cung cấp các API *streaming*:

- `RecordingStream`: nhận sự kiện từ **JVM hiện tại**.
- `EventStream`: interface cho luồng sự kiện JFR, với khả năng gắn callback và quản lý vòng đời.
- `RecordedEvent` vẫn là đối tượng biểu diễn event nhận được.

Một ví dụ minh họa về việc đăng ký callback:

```java
import jdk.jfr.consumer.RecordingStream;

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.GarbageCollection");
    stream.onEvent("jdk.GarbageCollection", event ->
            System.out.println(event.getEventType().getName()));
    stream.start(); // Chặn thread gọi cho tới khi stream kết thúc.
}
```

Đoạn trên là **mã minh họa**, phải đặt trong lớp và ngữ cảnh phù hợp. `start()` chạy đồng bộ và **có thể chặn lâu dài** cho đến khi stream đóng. Với ứng dụng phục vụ request, thường dùng `startAsync()`, thêm quản lý thread, thời gian sống và `close()` phù hợp; không đặt việc start chặn vào luồng xử lý request.

Ngoài ra, sự kiện JVM phụ thuộc hoạt động thực tế và cấu hình ghi nên **không thể hứa rằng mỗi lần chạy sẽ nhận đúng một sự kiện GarbageCollection**. Không dùng lượng event GC làm điều kiện kiểm thử có đầu ra cố định.

**Chọn API nào?**

| Nhu cầu | API thường phù hợp |
| --- | --- |
| Ghi event ứng dụng, tạo recording, cấu hình recording | `jdk.jfr.Event`, `jdk.jfr.Recording` |
| Phân tích tệp `.jfr` đã tạo (offline) | `jdk.jfr.consumer.RecordingFile` |
| Đọc nhanh toàn bộ sự kiện từ **tệp nhỏ** | `RecordingFile.readAllEvents(path)` |
| Nhận event từ JVM hiện tại trong lúc chạy | `jdk.jfr.consumer.RecordingStream` |
| Kết hợp logic giám sát liên tục | `EventStream` hoặc `RecordingStream` với callback/lifecycle rõ ràng |

Dù chọn offline hay streaming, hãy quản lý đóng tài nguyên, giới hạn lưu trữ và **tính nhạy cảm của dữ liệu event**.

## 7. Cấu hình, chi phí và vận hành

### Chỉ bật dữ liệu cần thiết

Recording có thể thu nhiều sự kiện JVM. Một số sự kiện tạo nhiều dữ liệu hoặc cần thu thập tốn kém; với event tùy biến, cần chọn payload thật sự hữu ích. Tránh đưa vào JFR **mật khẩu, token, dữ liệu định danh không cần thiết hoặc nội dung request nhạy cảm**.

Có thể điều chỉnh ngưỡng thời gian bằng `withThreshold(Duration...)`, tần suất và stack trace theo cấu hình event. Trong ví dụ phần 5, ta chủ ý dùng ngưỡng `Duration.ZERO` để event ngắn vẫn được ghi; không nhất thiết cấu hình như vậy cho mọi hệ thống sản xuất.

### Giới hạn dung lượng recording

`Recording` có các API như `setMaxAge(Duration)` và `setMaxSize(long)` để giới hạn lượng dữ liệu ghi. Khi giữ recording trong thời gian dài, cần cấu hình chính sách giữ dữ liệu; nếu không, recording lưu trên đĩa có thể tiêu tốn đáng kể tài nguyên.

Đừng mở `Recording` mới cho **mỗi request HTTP** chỉ để ghi một event nhỏ. Thường nên dùng một recording phục vụ bài toán giám sát, để các event trong ứng dụng cùng ghi vào đó. Có thể dùng công cụ `jcmd` hoặc công cụ quan sát phù hợp để điều khiển JFR mà không nhất thiết nhúng toàn bộ vòng đời recording vào từng nghiệp vụ.

### Xử lý file JFR an toàn

`RecordingFile` có thể ném `IOException` khi file không tồn tại, bị hỏng hoặc không phải JFR file hợp lệ. **Chỉ dùng file JFR từ nguồn đáng tin**, kiểm tra quyền đọc/ghi và tránh tải toàn bộ file rất lớn vào bộ nhớ.

Nếu ứng dụng ghi file để các công cụ ngoài tiến trình phân tích, đừng xóa file ngay như trong **demo**. Demo dùng file tạm và xóa để tránh rác; ứng dụng thực tế nên lưu tới vị trí có quyền truy cập phù hợp và chính sách retention.

### Runtime image mô-đun

Trong một runtime image tối giản, **không nên mặc định giả định mọi module JDK đều còn đó**. Khi xây dựng ứng dụng JPMS, cần có `jdk.jfr` trong graph được phân giải. Nếu một môi trường Java thiếu module, launcher có thể báo `Module jdk.jfr not found, required by com.example.jfrapp` trước khi chạy `main`; khi ấy kiểm tra `FlightRecorder.isAvailable()` trong chương trình **không có cơ hội thực thi**.

Vì thế, hãy kiểm tra cả:

1. **Phân giải module trước khi chạy**: runtime có module `jdk.jfr` hay không?
2. **Khả năng JFR trong JVM khi đã chạy**: `FlightRecorder.isAvailable()` có trả `true` hay không?

Hai điều kiện này không đồng nhất.

## 8. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Viết `requires jdk.jfr.consumer;` | Nhầm package thành module | Chỉ dùng `requires jdk.jfr;` |
| Import được `jdk.jfr.Event` nhưng không có `RecordingFile` | Bỏ sót import hoặc nhầm đường dẫn lớp | Import `jdk.jfr.consumer.RecordingFile`, không thêm module khác |
| Module application không đọc được `jdk.jfr` | Thiếu `requires jdk.jfr;` trong `module-info.java` | Thêm đúng directive và biên dịch lại |
| `Module jdk.jfr not found` khi chạy | Runtime image không có module JFR | Dùng runtime/JDK có module hoặc sửa cấu hình custom image |
| Event tùy biến không có trong file | Chưa bật event, chưa start, bị threshold lọc hoặc chưa commit | `enable(...).withThreshold(Duration.ZERO)`, start trước commit, stop/dump đúng thứ tự |
| Giả định `commit()` tạo ngay một tệp `.jfr` | Commit event không đồng nghĩa dump recording | Dùng `Recording.dump(Path)` hoặc cấu hình destination |
| Consumer đọc dòng đầu là event của mình | File chứa nhiều loại event | Lọc bằng `getEventType().getName()` |
| Gọi `getString("amount")` cho trường `long` | Sai kiểu dữ liệu | Dùng `getLong("amount")` theo schema |
| Dùng `RecordingFile.readAllEvents` với file lớn | Có thể chiếm nhiều bộ nhớ | Đọc tuần tự với `hasMoreEvents()/readEvent()` |
| Không đóng `Recording`/`RecordingFile` | Giữ tài nguyên không cần thiết | Dùng try-with-resources |
| Gọi `RecordingStream.start()` trong request thread | Lệnh đồng bộ có thể chặn lâu dài | Dùng `startAsync()` và quản lý vòng đời phù hợp |
| Đưa thông tin bí mật vào event payload | Recording có thể được chia sẻ/thu thập tập trung | Giảm dữ liệu nhạy cảm, kiểm soát quyền và lưu trữ |
| Dùng API nội bộ `jdk.jfr.internal.*` | Không phải API công khai ổn định | Dùng package `jdk.jfr` và `jdk.jfr.consumer` được export |

## 9. Câu hỏi thực hành có đáp án

**Câu 1.** Trong ứng dụng có `module-info.java`, muốn dùng `Recording` và `RecordingFile` thì khai báo bao nhiêu `requires`?  
**Đáp án:** Một, `requires jdk.jfr;`. Hai lớp nằm trong hai package của cùng module `jdk.jfr`.

**Câu 2.** `jdk.jfr.consumer` là tên một module riêng?  
**Đáp án:** Không. Nó là **package** trong module `jdk.jfr`.

**Câu 3.** Vì sao demo cần `recording.enable(OrderProcessed.class)` trước khi `start()`?  
**Đáp án:** Để event tùy biến được ghi rõ ràng theo cấu hình, tránh phụ thuộc vào cấu hình mặc định; `withThreshold(Duration.ZERO)` loại bỏ ngưỡng thời lượng cho demo.

**Câu 4.** `commit()` có đảm bảo tạo file ngay không?  
**Đáp án:** Không. Nó ghi sự kiện vào hệ thống JFR khi được bật; cần quản lý recording và `dump(Path)` hoặc destination để tạo file.

**Câu 5.** Khi file `.jfr` chứa event JVM khác, làm sao lấy event `demo.OrderProcessed`?  
**Đáp án:** Lặp qua `RecordedEvent` và lọc `event.getEventType().getName().equals("demo.OrderProcessed")`.

**Câu 6.** Vì sao `RecordedEvent.getString("orderId")` phù hợp nhưng `getString("amount")` không?  
**Đáp án:** Kiểu `orderId` là `String` còn `amount` là `long`; dùng accessor đúng kiểu, ví dụ `getLong("amount")`.

**Câu 7.** Dùng `RecordingFile.readAllEvents` cho file JFR nhiều gigabyte có thích hợp không?  
**Đáp án:** Không. Nó tải toàn bộ danh sách event; đọc tuần tự bằng `RecordingFile` hoặc giải pháp streaming để hạn chế bộ nhớ.

**Câu 8.** Trong runtime JPMS tự tạo, `FlightRecorder.isAvailable()` có thay được kiểm tra module `jdk.jfr` tồn tại không?  
**Đáp án:** Không. Nếu module không được tìm thấy khi phân giải module, ứng dụng không khởi động được để gọi phương thức đó.

**Câu 9.** Nếu muốn quan sát event khi JVM còn chạy, dùng API consumer nào?  
**Đáp án:** `RecordingStream` và callback `onEvent(...)`, kết hợp start/close có vòng đời rõ ràng.

## 10. Ghi nhớ và tài liệu chính thức

**Dấu hiệu của ứng dụng mô-đun dùng JFR đúng cách** là có `requires jdk.jfr;` trong `module-info.java`, dùng `jdk.jfr` để **tạo/ghi event**, dùng `jdk.jfr.consumer` để **đọc event**, đồng thời kiểm soát tài nguyên và dữ liệu nhạy cảm.

- `jdk.jfr` và `jdk.jfr.consumer` **không phải hai module**.
- `Event.commit()`, `Recording.start()/stop()/dump()` và `RecordingFile.readEvent()` đảm nhiệm **các giai đoạn khác nhau**.
- Ví dụ đơn giản nên có event tùy biến với tên ổn định, ngưỡng rõ ràng và vòng đời resource được đóng.
- Khi triển khai JPMS hay runtime image tối giản, cần **có module `jdk.jfr`** ở runtime.
- Nên xử lý file recording như dữ liệu quan sát có thể nhạy cảm, không như text log vô hại.

Tài liệu chính thức (API hiện vẫn áp dụng cho Java 17+):

- [Oracle Java SE 21 — Module `jdk.jfr`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html): mô tả module chứa cả hai package.
- [Oracle Java SE 21 — Package `jdk.jfr`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): sự kiện, metadata, recording và cấu hình.
- [Oracle Java SE 21 — Package `jdk.jfr.consumer`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html): các API đọc dữ liệu JFR.
- [Oracle Java SE 21 — `Recording`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`, `start`, `stop`, `dump` và giới hạn lưu trữ.
- [Oracle Java SE 21 — `RecordingFile`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc tuần tự hoặc đọc toàn bộ sự kiện.
- [Oracle Java SE 21 — `Event`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): sự kiện tự định nghĩa và `commit`.
- [Oracle Java SE 21 — `RecordingStream`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): consumer streaming trong JVM hiện tại.
