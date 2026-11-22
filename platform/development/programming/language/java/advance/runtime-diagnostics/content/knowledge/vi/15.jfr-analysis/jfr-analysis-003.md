# 15.3. Dùng `jfr print` với bộ lọc event, category, stack depth và đầu ra JSON hoặc XML

## Mục tiêu bài học

**Java Flight Recorder (JFR)** ghi các sự kiện JVM và ứng dụng thành file binary `.jfr`. Công cụ dòng lệnh **`jfr print`** trong JDK đọc file đã lưu, in các event ở dạng dễ đọc hoặc chuyển thành JSON/XML để xử lý tự động. Khả năng chọn **event type**, **category**, và số **stack frames** hiển thị giúp tập trung vào tín hiệu cần điều tra thay vì đọc toàn bộ recording.

Sau bài này, bạn sẽ biết cách:

1. Kiểm tra recording bằng `jfr summary` và `jfr metadata` để tìm tên event/category thật.
2. Lọc bằng `--events`, `--categories`, danh sách tên và glob.
3. Hiểu **quy tắc OR/union** khi dùng đồng thời filter theo tên và category.
4. Dùng `--stack-depth` nhưng không nhầm thao tác hiển thị với thao tác thu thập stack trace.
5. Xuất `--json` hoặc `--xml` để dùng trong pipeline, kiểm tra encoding và dữ liệu rỗng.
6. Tạo một recording nhỏ bằng Java 17+ và tự thực hành trên các event có thể dự đoán.

Các lệnh dưới đây áp dụng cho **JDK 17+**; chi tiết event type, category và trường output phụ thuộc JDK, recording settings và workload. Cú pháp `print` tập trung vào khả năng có trong JDK 17.

## 1. Từ Java recording đến lệnh `jfr print`

```text
Java process / JVM
     |
     | JFR recording: event settings, sampling, thresholds, stack traces
     v
recording.jfr  (binary file)
     |
     +-- jfr summary    -> danh sách event type, count, kích thước
     +-- jfr metadata   -> định nghĩa type, category và fields
     +-- jfr print      -> từng instance event theo bộ lọc
             |
             +-- mặc định: human-readable text
             +-- --json: máy đọc được
             +-- --xml:  máy đọc được
```

Một **event type** (ví dụ `jdk.GarbageCollection`) là kiểu sự kiện; một **event instance** là một lần xảy ra được ghi, có timestamp và các field. **Category** là metadata phân loại các type, có thể bao gồm nhiều type khác nhau. Stack trace là một field tùy event/settings; không phải mọi event đều có stack.

`jfr print` chỉ **đọc** dữ liệu đã ghi. Nó không mở recording, không thay đổi file `.jfr`, không chạy lại những thao tác ứng dụng và không tái tạo event đã bị threshold/sampling loại bỏ. Nếu cần lấy recording mới từ JVM đang chạy, dùng `jcmd ... JFR.start` hoặc cơ chế ghi JFR tương đương.

## 2. Cú pháp `jfr print` chuẩn JDK 17

```text
jfr print [--xml|--json]
          [--categories <filters>]
          [--events <filters>]
          [--stack-depth <depth>]
          <file>
```

| Tùy chọn | Tác dụng | Điều cần nhớ |
| --- | --- | --- |
| `<file>` | Đường dẫn file recording `.jfr` | File phải tồn tại và là dữ liệu JFR hợp lệ. |
| `--events <filters>` | Chọn các event theo **tên type** | Tên đơn giản/đầy đủ, các tên cách dấu phẩy, hoặc quoted glob. |
| `--categories <filters>` | Chọn event theo **tên category** | Category khác tên type; xem `jfr metadata`. |
| `--stack-depth <depth>` | Giới hạn số frame stack trace được **in** | Mặc định là **5**; không khôi phục frame chưa ghi. |
| `--json` | In JSON | Một lựa chọn thay cho human-readable và XML. |
| `--xml` | In XML | Không kết hợp cùng `--json` trong một lệnh. |
| Không có `--json`/`--xml` | In dạng văn bản dễ đọc | Tốt cho kiểm tra trực tiếp tại terminal. |

Tra cứu trực tiếp từ JDK đang dùng:

```bash
jfr --help print
```

**Quan trọng:** `jfr print` chỉ lọc **những gì đã có trong file**. Nó không lọc theo giá trị tùy ý của field như `duration > 100 ms`. Để lọc theo field, xuất JSON/XML rồi xử lý thêm hoặc dùng API phân tích JFR.

## 3. Chuẩn bị file và xác định filter đáng dùng

Nếu đã có `recording.jfr`, kiểm tra bằng:

```bash
jfr summary recording.jfr
jfr metadata recording.jfr
```

- **`summary`** thống kê số lượng instance theo event type, kích thước dữ liệu. Nếu type không có instance, `jfr print --events ...` không có gì tương ứng để in.
- **`metadata`** hiển thị tên type, category và cấu trúc field của event trong recording. Nó giúp tránh gõ sai tên, nhầm chữ hoa/thường hoặc đoán category.
- **Có metadata không đảm bảo có instance**. Đối chiếu `summary` hoặc `print` để biết recording đã ghi sự kiện thuộc type đó chưa.

Để tạo một recording chẩn đoán từ tiến trình Java đang chạy, với PID minh họa `12345`:

```bash
jcmd 12345 JFR.start name=diag settings=profile duration=30s filename=diag.jfr
```

Lệnh yêu cầu ghi 30 giây. File `diag.jfr` chỉ dùng cho `jfr print` **sau khi recording kết thúc và file thực sự tồn tại**. `settings=profile` không bảo đảm tất cả event đều được ghi: phụ thuộc cấu hình, tải, threshold và thời điểm. Đường dẫn recording thuộc môi trường của JVM đích; khi chạy trong container cần xác định path và quyền đọc tương ứng. PID cũng chỉ là ví dụ.

## 4. Lọc theo tên event với `--events`

### 4.1. Chọn một event type

```bash
jfr print --events "jdk.GarbageCollection" diag.jfr
```

Lệnh trên chỉ in những instance có tên type khớp `jdk.GarbageCollection`. Đây là **tên event**, không phải tên class Java mà stack trace đang gọi, cũng không phải một giá trị field.

Một ví dụ khác:

```bash
jfr print --events "jdk.CPULoad" diag.jfr
```

Nếu recording không có instance của `jdk.CPULoad`, output có thể rỗng. Không được kết luận CPU luôn bằng 0 chỉ từ lệnh lọc trống; hãy kiểm tra lại `summary`, settings và cửa sổ thời gian.

### 4.2. Nhiều event trong một filter

```bash
jfr print --events "jdk.GarbageCollection,jdk.CPULoad" diag.jfr
```

Dấu phẩy ngăn cách các tên type. Nghĩa là lấy instance **thuộc một trong các type được liệt kê**. Viết tên event đủ điều kiện `jdk.XXX` giúp minh bạch và tránh nhập nhằng với những event tùy biến có tên ngắn tương tự.

### 4.3. Wildcard/glob

```bash
jfr print --events "jdk.GC*" diag.jfr
jfr print --events "jdk.*" --stack-depth 10 diag.jfr
```

Mẫu `jdk.GC*` chọn những tên type khớp glob bắt đầu bằng `jdk.GC` nếu file có các type ấy; `jdk.*` thường rộng hơn nhiều. **Glob không đồng nghĩa Java regular expression**. Dùng dấu quote để tránh shell (Bash, zsh, PowerShell) diễn giải `*` trước khi truyền vào `jfr`.

Các bộ lọc danh sách tên/glob được áp dụng trên **symbolic event type names** (metadata `@Name`), không phải chuỗi văn bản tự do có trong stack trace hoặc field.

## 5. Lọc theo category với `--categories`

Ví dụ chuẩn của JDK:

```bash
jfr print --categories "GC" diag.jfr
```

Lệnh tìm các event có category phù hợp `GC`, và **có thể** in nhiều event type. Danh sách category thực tế nằm trong `jfr metadata diag.jfr`.

Có thể dùng danh sách tên đơn giản, tên qualified hoặc quoted glob:

```bash
jfr print --categories "GC,JVM,Java*" diag.jfr
```

Category có thể là phân cấp hoặc metadata tùy event type; nếu muốn kết quả chính xác, hãy dựa trên category name thực tế của recording. Không mặc định tất cả event “liên quan GC” đều mang một category tên `GC` hoặc có cấu trúc field giống nhau.

### 5.1. Hai bộ lọc kết hợp bằng OR, không phải AND

Ví dụ Oracle JDK 17:

```bash
jfr print --categories "GC" --events "jdk.CPULoad" diag.jfr
```

Kết quả là:

```text
S = {event thuộc category GC}
    ∪ {event có type jdk.CPULoad}
```

Đây là **hợp (union)**. Không phải chỉ những event đồng thời thuộc category GC **và** có type `jdk.CPULoad`. Nếu muốn phép AND theo nhiều tiêu chí, chọn một bộ lọc hẹp hoặc xử lý tập kết quả xuất ra bằng công cụ khác. Không dùng hai option trên với kỳ vọng chúng thu hẹp giao của nhau.

Tương tự, `--events "A,B"` là type A **hoặc** type B; `--categories "C,D"` là category C **hoặc** D.

## 6. Giới hạn số frame với `--stack-depth`

Khi một event có stack trace, `jfr print` mặc định **hiển thị tối đa 5 frame**. Tăng ngưỡng trình bày:

```bash
jfr print --events "jdk.ExecutionSample" --stack-depth 20 diag.jfr
```

Khi đọc:

1. **Recording stage:** event type phải được bật; nếu muốn stack trace cần cấu hình thu thập stack (chẳng hạn `stackTrace=true`) và JVM phải thực sự ghi frame. Còn có thể có giới hạn stack depth/sampling ở thời điểm ghi.
2. **Printing stage:** `--stack-depth 20` chỉ tăng số frame tối đa được in từ **những frame file đã chứa**. Nó không mở rộng chiều sâu đã capture, không chạy lại ứng dụng và không gắn stack mới cho event.
3. **Không có frame:** có thể event không hỗ trợ/cấu hình không ghi stack, hoặc không có stack phù hợp; thử `--stack-depth 100` cũng không tạo dữ liệu mới.
4. **Giá trị lớn:** output có thể dài hơn nhưng chưa chắc hữu ích hơn. Chọn số đủ phục vụ giả thuyết điều tra.

Một event không nhất thiết có đầy đủ call tree của request. Nó phản ánh vị trí/tình huống ghi event. Nếu mục tiêu là phân tích hot methods, sampling frequency, lock hoặc allocation, phải chọn event type và settings phù hợp ngay từ lúc recording.

## 7. Chọn human-readable, JSON hoặc XML

### 7.1. Dạng văn bản mặc định

```bash
jfr print --events "jdk.CPULoad" diag.jfr
```

Dạng này thuận tiện xem nhanh các field, timestamp và stack. Một số giá trị được format theo annotation của JFR: ví dụ tỷ lệ có thể hiện thành %. Không tự áp dụng các đơn vị của output văn bản cho mọi field trong JSON/XML mà chưa kiểm tra.

### 7.2. JSON

```bash
jfr print --json --events "jdk.CPULoad" diag.jfr
```

Trên Bash/sh và Windows Command Prompt, lưu output:

```bash
jfr print --json --events "jdk.CPULoad" diag.jfr > cpu-events.json
```

JSON dễ đưa vào parser hoặc pipeline, gồm event types, dữ liệu field, có thể có object/nested stack/thread/timestamp. **Không giả định mọi field đều tồn tại, hay schema không đổi qua mọi phiên bản JDK**. Hãy đọc output thực tế trước khi viết code truy cập field lồng nhau.

Kiểm tra file JSON có đúng cú pháp (nếu máy có Python):

```bash
python -m json.tool cpu-events.json
```

Trên **Windows PowerShell 5.1**, toán tử `>` có thể xuất theo encoding khác với UTF-8 mà nhiều JSON parser mong muốn. Có thể dùng cách chỉ rõ encoding:

```powershell
jfr print --json --events "jdk.CPULoad" diag.jfr | Out-File -FilePath cpu-events.json -Encoding utf8
```

Tùy PowerShell phiên bản, encoding/BOM có thể khác; xác minh bằng parser sau khi lưu. Khi xuất JFR chứa thông tin nội bộ, kiểm soát dữ liệu nhạy cảm trong file JSON trước khi chia sẻ.

### 7.3. XML

```bash
jfr print --xml --events "jdk.GarbageCollection" diag.jfr
jfr print --xml --events "jdk.GarbageCollection" diag.jfr > gc-events.xml
```

XML phù hợp với công cụ cần tree, element/attribute và XML parser. Không dùng cách tách chuỗi thủ công để “parse XML”. Tên node/field cụ thể nên lấy từ output JDK thật.

### 7.4. Không bật `--json` và `--xml` cùng lúc

Cú pháp `[--xml|--json]` nghĩa là chọn **một định dạng** mỗi lần gọi. Muốn hai file, chạy hai lệnh độc lập trên cùng `.jfr`. Hai định dạng **chỉ thay cách xuất**, không làm recording chi tiết hơn, không kích hoạt thêm event và không tăng stack depth đã thu thập.

Với recording lớn, in toàn bộ event dạng JSON/XML có thể tạo rất nhiều dữ liệu. Nên áp dụng `--events`/`--categories` trước, sau đó mới lưu file; kiểm tra dung lượng, encoding, timestamp và field format.

## 8. Bài thực hành độc lập: tự tạo recording bằng Java 17+

Ví dụ này tạo **hai custom event**: một type `demo.Operation` có category `Demo` và một type `demo.Checkpoint` có category `Diagnostics`. Như vậy có thể kiểm tra event filter, category filter và quy tắc OR mà không phụ thuộc ứng dụng thật có GC/CPU event nào.

Tạo file **`JfrPrintDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class JfrPrintDemo {
    @Name("demo.Operation")
    @Label("Operation")
    @Category({"Demo"})
    public static class Operation extends Event {
        @Label("Action")
        public String action;
    }

    @Name("demo.Checkpoint")
    @Label("Checkpoint")
    @Category({"Diagnostics"})
    public static class Checkpoint extends Event {
        @Label("Sequence")
        public int sequence;
    }

    private static void writeEvents() {
        Operation operation = new Operation();
        operation.action = "checkout";
        operation.begin();
        operation.end();
        operation.commit();

        Checkpoint checkpoint = new Checkpoint();
        checkpoint.sequence = 7;
        checkpoint.commit();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(Operation.class)
                     .withThreshold(Duration.ZERO)
                     .withStackTrace();
            recording.enable(Checkpoint.class)
                     .withThreshold(Duration.ZERO)
                     .withStackTrace();

            recording.start();
            writeEvents();
            recording.stop();
            recording.dump(Path.of("demo.jfr"));
        }
        System.out.println("Created demo.jfr");
    }
}
```

Giải thích:

- `@Name` gắn **tên type** cho bộ lọc `--events`; `@Category` khai báo **category** cho `--categories`.
- `@Label` chỉ là nhãn hiển thị, không thay tên type.
- `withThreshold(Duration.ZERO)` đặt threshold 0, để event rất ngắn vẫn có thể được ghi.
- `withStackTrace()` yêu cầu lưu stack trace trong recording. Do đó việc chỉnh `--stack-depth` về sau mới có dữ liệu để hiển thị.
- `Recording.start()`, `stop()` và `dump()` tạo file trong thư mục hiện hành. Chương trình không gọi GC, không tạo dữ liệu dung lượng lớn.

Biên dịch/chạy:

```bash
javac --release 17 JfrPrintDemo.java
java JfrPrintDemo
```

Khi chạy thành công, stdout mà chính mã Java phát ra là:

```text
Created demo.jfr
```

JVM có thể in thông báo khác trong môi trường đặc biệt. Nội dung timestamp, thread, stack trong JFR **không cố định**, nên không bịa lại một output duy nhất cho các lệnh `jfr print`.

### 8.1. Kiểm tra

```bash
jfr summary demo.jfr
jfr metadata demo.jfr
```

Trong điều kiện recording chạy thành công, hai custom event đã được `commit()` một lần mỗi type. File có thể chứa thêm metadata hoặc các event hệ thống; điều quan trọng là biết hai type dùng trong thí nghiệm.

### 8.2. Filter theo một event

```bash
jfr print --events "demo.Operation" demo.jfr
```

Kết quả bao gồm một `demo.Operation` với field `action = checkout` (khi file đã ghi event). Các timestamp, duration và stack frames có giá trị phụ thuộc lần chạy.

### 8.3. Filter theo category

```bash
jfr print --categories "Diagnostics" demo.jfr
```

Trong hai custom event, chỉ `demo.Checkpoint` thuộc `Diagnostics`, với field `sequence = 7`.

### 8.4. Kết hợp bộ lọc, trực tiếp kiểm tra OR

```bash
jfr print --events "demo.Operation" --categories "Diagnostics" demo.jfr
```

Kết quả gồm **cả `demo.Operation` lẫn `demo.Checkpoint`**. Nếu nhầm hai filter là phép AND thì sẽ mong kết quả rỗng; file demo cho phép nhìn thấy rõ hành vi union của JDK.

### 8.5. Stack và JSON/XML

```bash
jfr print --events "demo.Operation" --stack-depth 12 demo.jfr
jfr print --json --events "demo.Operation" demo.jfr
jfr print --xml --categories "Diagnostics" demo.jfr
```

Dùng bản `--stack-depth 12` để xem nhiều frame hơn so với mặc định khi có đủ frame được ghi. Dùng JSON/XML để phân tích máy đọc, và chỉ giả định các field sau khi kiểm tra file thực.

## 9. Tình huống phân tích trong thực tế

Khi điều tra ứng dụng bị latency spike:

1. **Xác định recording đúng thời điểm:** ghi lại JDK vendor/version, PID, thời gian start/stop, clock/timezone và điều kiện tải.
2. **Đọc `summary`:** có event type nào và count ra sao? Nếu không có, kiểm tra event settings/sampling/threshold trước khi kết luận nguyên nhân vắng mặt.
3. **Đọc `metadata`:** tìm type name/category name chính xác. Nếu đang nghi GC, thử `--events "jdk.GarbageCollection"` hoặc category `GC` có trong file.
4. **Lọc đủ hẹp:** xuất những event liên quan trước, tránh in toàn bộ recording. Nếu vừa dùng `--events` vừa dùng `--categories`, nhớ kết quả là union.
5. **Xem stack trace:** nếu chỉ có vài frame hoặc không có, quay lại cấu hình thu thập, đừng cố sửa bằng `--stack-depth`.
6. **Xuất JSON/XML để tự động hóa:** chuẩn hóa timestamps, xác nhận đơn vị/field và encoding, rồi ghép với application logs, request traces hoặc OS metrics.
7. **Đặt kết luận theo bằng chứng:** một event GC không chứng minh request chậm do GC; phải ghép timestamp, duration, workload và nhiều tín hiệu khác.

| Tín hiệu | Kiểm tra tiếp | Không được kết luận vội |
| --- | --- | --- |
| `jfr print` rỗng dù nghi GC nhiều | `summary`, `metadata`, recording window/settings | “JVM không chạy GC”. |
| `--categories GC` trả nhiều event type | Phạm vi category trong metadata | “Tất cả là một lần GC”. |
| `--events A --categories B` trả A và B | Quy tắc OR trong tài liệu JDK | “Filter bị lỗi”. |
| `--stack-depth 64` chỉ thấy 3 frame | Stack đã ghi, event settings | “Lệnh sẽ tự bổ sung 61 frame”. |
| JSON không parse được sau redirect | Encoding/BOM, file hỏng hay output khác | “JFR format không hỗ trợ JSON”. |
| Không thấy `jdk.ExecutionSample` | Config profile/default, event enabled, workload | “Ứng dụng không dùng CPU”. |

## 10. Những lỗi phổ biến

- **Nhầm `jfr print` với `jcmd JFR.start`:** lệnh đầu đọc `.jfr`, lệnh sau yêu cầu JVM bắt đầu recording.
- **Gõ sai tên event/category:** phải kiểm tra `summary` và `metadata`; tên event phân biệt với tên Java method xuất hiện trong stack.
- **Cho rằng `--events` cộng `--categories` là AND:** tài liệu JDK 17 xác nhận **OR/union**.
- **Dùng regex cho `--events`:** cú pháp hỗ trợ tên, danh sách cách dấu phẩy, glob; không mặc định Java regex.
- **Không quote wildcard:** shell có thể tự xử lý dấu `*` trước `jfr`.
- **Tăng `--stack-depth` rồi mong có stack mới:** print không thay quá trình capture event.
- **Cho rằng mọi event có stack trace:** không đúng; tùy loại event/settings.
- **Dùng cả `--json` và `--xml` một lần:** hai định dạng loại trừ nhau.
- **Coi giá trị trong định dạng người đọc là raw field value:** JFR có annotation hiển thị đơn vị/percentage; dùng parser và hiểu field đúng loại.
- **Tạo output JSON/XML khổng lồ:** phải lọc trước, tránh ghi nội dung không cần vào log hoặc repository.
- **Không kiểm tra encoding của file sau redirect:** dễ gây parser error, đặc biệt trên shell/PowerShell cũ.
- **Không xác nhận event có thực trong recording:** không nên gán output trống cho một kết luận hiệu năng.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Muốn in riêng `jdk.CPULoad` trong `diag.jfr`?  
**Đáp án:** `jfr print --events "jdk.CPULoad" diag.jfr`.

**Câu 2.** Dùng `--categories GC --events jdk.CPULoad` nghĩa là gì?  
**Đáp án:** Chọn event thuộc category GC **hoặc** có type `jdk.CPULoad`, không yêu cầu cả hai.

**Câu 3.** Vì sao `--stack-depth 50` vẫn chỉ in 4 frame?  
**Đáp án:** Vì file có thể chỉ ghi 4 frame có sẵn cho event. `print` không thể thêm frame đã mất.

**Câu 4.** Muốn dùng máy đọc kết quả dưới dạng JSON và XML đồng thời?  
**Đáp án:** Chạy hai lần `jfr print` trên cùng file, lần dùng `--json` và lần dùng `--xml`.

**Câu 5.** Muốn chỉ lấy event có `duration` lớn hơn 100 ms, `--events` có làm được không?  
**Đáp án:** Không; `--events` lọc theo tên type. Cần xử lý field từ JSON/XML hoặc API consumer JFR.

**Câu 6.** Với `demo.jfr` ở bài thực hành, bộ lọc `--events "demo.Operation" --categories "Diagnostics"` chọn type nào?  
**Đáp án:** Cả `demo.Operation` lẫn `demo.Checkpoint`, thể hiện union.

## Tài liệu tham khảo

- [Oracle JDK 17 — Lệnh `jfr`: `print`, `summary`, `metadata`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Oracle JDK 17 — `jcmd`: `JFR.start`, `JFR.dump`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Java SE 17 — API `Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Java SE 17 — API `EventSettings`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [Java SE 17 — API `Category`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Category.html)
- [dev.java — The JFR command-line tool](https://dev.java/learn/jvm/jfr/tools/)
