# Theo dõi sự kiện JFR nạp và dỡ thư viện bản địa (Native Library Load/Unload)

## 1. Mục tiêu và bối cảnh

Một ứng dụng Java có thể nạp mã máy từ thư viện hệ điều hành qua **JNI** (`System.load`/`System.loadLibrary`), **Foreign Function & Memory API** (FFM, ví dụ `SymbolLookup.libraryLookup`), JVMTI agent hoặc những đường thực thi native khác. Trong hệ thống nhiều module, plugin hay class loader, việc nạp/dỡ thư viện sai thời điểm có thể gây `UnsatisfiedLinkError`, khó xác định phụ thuộc hệ điều hành, tăng số lượng thư viện đang lưu trú, hoặc làm ứng dụng lỗi khi tài nguyên native đã bị giải phóng.

**Java Flight Recorder (JFR)** ghi sự kiện với dấu thời gian, thời lượng và metadata để phân tích sau. Đối với native library, cần phân biệt **sự kiện mô tả thư viện đang có mặt** với **sự kiện mô tả một thao tác load/unload xảy ra**. Đây là điểm quan trọng nhất khi đọc file `.jfr`.

Sau bài này, bạn có thể:

- Chọn đúng sự kiện theo phiên bản JDK và phân biệt snapshot với lịch sử thao tác.
- Bật recording trước thời điểm phát sinh load/unload, thu file `.jfr` rồi lọc các sự kiện cần thiết.
- Đọc `name`, `success`, `errorMessage`, timestamp, duration và stack trace khi có.
- Dùng một ví dụ Java + C để kích hoạt load/unload, rồi kiểm chứng bằng JFR.
- Điều tra những tình huống “thư viện không nạp được”, “không thấy unload” và “có snapshot nhưng thiếu load event” mà không đưa ra kết luận quá mức từ dữ liệu thiếu.

## 2. Các sự kiện và phiên bản JDK

| Event type | Khả dụng | Dùng để trả lời |
| --- | --- | --- |
| `jdk.NativeLibrary` | Có trên các bản HotSpot JDK trước JDK 22, bao gồm JDK 17/21, và tiếp tục trên bản mới | *Tại thời điểm JFR lấy snapshot, tiến trình JVM có những native module nào?* |
| `jdk.NativeLibraryLoad` | Được bổ sung từ **JDK 22** trong OpenJDK/HotSpot | *Trong khoảng ghi, JVM đã thực hiện thao tác nạp thư viện nào và thành công hay thất bại?* |
| `jdk.NativeLibraryUnload` | Được bổ sung từ **JDK 22** trong OpenJDK/HotSpot | *Trong khoảng ghi, JVM đã thực hiện thao tác dỡ thư viện nào và kết quả ra sao?* |

Tên đầy đủ (kèm tiền tố `jdk.`) nên được dùng khi cấu hình hoặc lọc sự kiện. Cùng một phiên bản Java SE nhưng JVM/vendor khác có thể khác về hỗ trợ event; **kiểm tra event metadata của chính runtime đang chạy** trước khi triển khai quy trình giám sát.

### Snapshot `jdk.NativeLibrary`

Đây là **periodic event**: HotSpot liệt kê các native module đang được nạp và phát bản ghi tương ứng, thường theo chu kỳ chunk JFR (cấu hình phổ biến là `everyChunk`). Các trường quan trọng:

- `name`: tên hoặc đường dẫn module native, tùy hệ điều hành/cơ chế nạp.
- `baseAddress`: địa chỉ bắt đầu ánh xạ module.
- `topAddress`: địa chỉ kết thúc ánh xạ, **có thể không xác định/không khả dụng**.

Một snapshot **không phải** bằng chứng rằng thư viện vừa được nạp đúng lúc timestamp của bản ghi. Việc xuất hiện lặp lại trong nhiều chunk cũng **không có nghĩa** thư viện đã được nạp lại nhiều lần.

### Sự kiện thao tác `jdk.NativeLibraryLoad` và `jdk.NativeLibraryUnload`

Các sự kiện này thuộc nhóm runtime, ghi thông tin khi VM thực hiện load hoặc unload. Những trường cần quan tâm:

| Trường | Diễn giải |
| --- | --- |
| `name` | Tên/đường dẫn được ghi nhận cho thư viện trong thao tác; có thể không được chuẩn hóa giống nhau trên mọi nền tảng |
| `success` | `true` nếu thao tác được VM ghi nhận là thành công; `false` nếu thất bại |
| `errorMessage` | Mô tả lỗi nếu có; thường không có nội dung ở thao tác thành công |
| `startTime` | Thời điểm bắt đầu sự kiện được đo bởi JFR |
| `duration` | Thời lượng của thao tác được instrument; không mặc định bằng tổng thời gian khởi tạo toàn bộ tầng ứng dụng |
| `eventThread` | Luồng được gắn với sự kiện nếu runtime có thể cung cấp |
| `stackTrace` | Stack trace khi thu thập được và tùy chọn này được bật |

Trong các JDK mới hơn, sự kiện load còn có thể có những trường bổ sung về xử lý môi trường floating-point. **Không hard-code mọi trường tùy chọn** khi viết công cụ phân tích nhiều phiên bản; dùng `jfr metadata` hoặc `RecordedEvent.hasField(...)` trước khi đọc.

**Phân biệt “thao tác unload thành công” và “module đã biến mất khỏi memory map”:** JVM có thể gọi cơ chế unload, nhưng hệ điều hành, reference count, dependency hoặc native runtime khác vẫn ảnh hưởng việc file thực sự được unmap. Cần đối chiếu với snapshot/OS khi muốn kết luận về trạng thái cư trú trong bộ nhớ.

## 3. JFR quan sát những gì và không quan sát những gì?

Dòng sự kiện điển hình:

```text
Ứng dụng Java / JNI / FFM
        |
        | yêu cầu load/unload
        v
Cơ chế nạp native của JVM
        |
        +--> NativeLibraryLoad / NativeLibraryUnload (JDK 22+)
        |        name, success, errorMessage, thời gian...
        v
Bộ nạp thư viện của hệ điều hành
        |
        v
Module native trong không gian địa chỉ tiến trình
        |
        +--> NativeLibrary (snapshot các module đang nạp)
```

Không nên suy diễn rằng JFR này là một bộ theo dõi **mọi** thao tác `dlopen`/`dlclose` hay `LoadLibrary` từ **mọi** mã trong hệ điều hành. Đây là sự kiện JVM được instrument; thao tác do một thư viện C bất kỳ tự thực hiện có thể không đi qua vị trí ghi event ấy. JFR cũng không tự báo **ai đang giữ mọi native handle** hoặc chứng minh thư viện đã giải phóng toàn bộ heap native.

Một timeline giả định:

| 10:00:00 | 10:00:05 | 10:00:20 | 10:00:40 |
| --- | --- | --- | --- |
| JVM đã nạp `libcore.so` | Bắt đầu JFR | `libaddon.so` được nạp | `libaddon.so` được dỡ |
| Không có load event trong recording mới cho `libcore.so` | Snapshot có thể liệt kê `libcore.so` | `NativeLibraryLoad(name=libaddon.so, success=true)` | `NativeLibraryUnload(name=libaddon.so, success=true)` |

Nếu chỉ ghi từ 10:00:05, **thiếu load event của `libcore.so` là bình thường**, không có nghĩa JFR hỏng. Snapshot giúp nhận diện các thư viện đã có trước khi bắt đầu ghi.

## 4. Kiểm tra runtime có hỗ trợ sự kiện

Dùng cùng JDK/JVM như tiến trình cần điều tra:

```bash
java -version

# Kiểm tra metadata mà lệnh jfr của JDK hiện tại biết.
jfr metadata --events jdk.NativeLibrary

# Chỉ kỳ vọng hai event này nếu runtime hỗ trợ (HotSpot JDK 22+).
jfr metadata --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload
```

Có thể xem event type bằng Java API, chẳng hạn biểu thức sau (đoạn Java minh họa, nằm trong phương thức phù hợp):

```java
jdk.jfr.FlightRecorder.getFlightRecorder()
        .getEventTypes()
        .stream()
        .map(jdk.jfr.EventType::getName)
        .filter(name -> name.startsWith("jdk.NativeLibrary"))
        .sorted()
        .forEach(System.out::println);
```

Danh sách phụ thuộc **JVM đang chạy**, nên output của đoạn này không được giả định giống nhau giữa JDK 17 và JDK 22+. Nếu JDK 17/21 không có hai event thao tác thì không thể “bật lên” chỉ bằng sửa `.jfc`; hãy dùng `jdk.NativeLibrary` snapshot hoặc nâng cấp JVM ở môi trường thích hợp.

Để hiểu trường nào thực sự tồn tại trong một file đã ghi, chạy:

```bash
jfr metadata --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload app.jfr
```

## 5. Ghi và xem sự kiện trong ứng dụng đang chạy

Đây là workflow cho **HotSpot JDK 22+**. Thay `<PID>` bằng PID thật, đảm bảo công cụ `jcmd` có thể attach vào JVM và thư mục đích có quyền ghi.

### 5.1. Bắt đầu trước khi tái hiện vấn đề

```bash
# Tìm tiến trình JVM.
jcmd -l

# Bắt đầu recording. profile/default trên HotSpot 22+ thường
# đã bật NativeLibrary, NativeLibraryLoad và NativeLibraryUnload.
jcmd <PID> JFR.start name=nativewatch settings=profile

# Xác nhận recording tồn tại và xem cấu hình thực tế.
jcmd <PID> JFR.check name=nativewatch verbose=true
```

Sau khi xác nhận recording **RUNNING** và các event mong muốn **enabled**, thực hiện thao tác ứng dụng gây nạp/dỡ thư viện (ví dụ khởi tạo plugin hoặc gọi một API có bước load native). Nếu dùng cấu hình `.jfc` tự tạo hoặc JVM vendor khác, phải xác minh event và ngưỡng `threshold`; nên đặt ngưỡng `0 ms` cho thao tác ngắn nếu cần bắt đầy đủ.

### 5.2. Dump, stop và lọc

```bash
# Có thể lấy một bản chụp file trong lúc recording vẫn chạy.
jcmd <PID> JFR.dump name=nativewatch filename=/tmp/nativewatch-sample.jfr

# Kết thúc và ghi recording hoàn chỉnh.
jcmd <PID> JFR.stop name=nativewatch filename=/tmp/nativewatch-final.jfr

# Kiểm tra file có những loại event nào và số lượng bao nhiêu.
jfr summary /tmp/nativewatch-final.jfr

# Sự kiện thao tác load/unload (JDK 22+).
jfr print --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload \
    --stack-depth 20 /tmp/nativewatch-final.jfr

# Danh sách thư viện ở các lần snapshot.
jfr print --events jdk.NativeLibrary /tmp/nativewatch-final.jfr
```

Lệnh dùng đường dẫn Linux làm ví dụ; trên Windows/macOS hãy chọn đường dẫn hợp lệ. `JFR.dump` không dừng recording; `JFR.stop` dừng recording đã chỉ định. Với recording ngắn, nên dừng và dump sau khi thao tác cần đo đã hoàn tất, và xét thời điểm flush/chunk khi phân tích.

Bộ lọc `--events` nhận các tên cách nhau bằng dấu phẩy. `jfr print --json` cũng có thể dùng để đưa dữ liệu vào script phân tích, nhưng cấu trúc JSON nên đọc theo schema thực tế của JDK đang dùng.

### 5.3. Bắt từ khởi động JVM

Nếu sự cố xảy ra trước khi bạn kịp attach, bật recording ngay lúc JVM khởi chạy:

```bash
java -XX:StartFlightRecording=filename=startup-native.jfr,settings=profile,dumponexit=true \
     -cp app.jar com.example.Main
```

Đây là **mẫu lệnh** cho ứng dụng có class `com.example.Main` trong `app.jar`; thay bằng entrypoint thật. Với file JAR thực thi có manifest phù hợp, dùng `-jar app.jar` thay cho `-cp ... com.example.Main`.

Ngay cả recording khởi động cũng có thể thiếu thao tác rất sớm ở giai đoạn VM bootstrap; việc thiếu stack trace hoặc thiếu event không đủ để kết luận chắc chắn không có tải native. Khi cần khảo sát toàn bộ giai đoạn khởi động/OS loader, phối hợp thêm công cụ phù hợp của hệ điều hành.

## 6. Thực hành: tự tạo load và unload để thu JFR

Ví dụ **chạy độc lập trên Linux, HotSpot JDK 22+ và compiler C**. Sử dụng FFM API đã được chuẩn hóa trong JDK 22 để kiểm soát vòng đời: `SymbolLookup.libraryLookup(path, arena)` nạp thư viện khi lookup được tạo, và arena đóng sẽ yêu cầu dỡ thư viện gắn với nó. Cách này làm tình huống unload dễ tái hiện hơn so với chờ garbage collector thu gom một class loader chứa JNI library.

### 6.1. Tệp `jfrprobe.c`

```c
/* Không cần Java native method hay JNI header trong ví dụ FFM này. */
int native_answer(void) {
    return 42;
}
```

### 6.2. Tệp `NativeLibraryEventsDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.SymbolLookup;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public final class NativeLibraryEventsDemo {
    public static void main(String[] args) throws Exception {
        Path library = Path.of("libjfrprobe.so")
                .toAbsolutePath()
                .normalize();
        Path output = Path.of("native-events.jfr");

        try (Recording recording = new Recording()) {
            recording.enable("jdk.NativeLibraryLoad")
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.enable("jdk.NativeLibraryUnload")
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.enable("jdk.NativeLibrary");
            recording.start();

            try (Arena arena = Arena.ofConfined()) {
                // Thao tác nạp native library xảy ra tại đây.
                SymbolLookup symbols =
                        SymbolLookup.libraryLookup(library, arena);

                // Đảm bảo thư viện thực sự có symbol được xuất.
                if (symbols.find("native_answer").isEmpty()) {
                    throw new IllegalStateException(
                            "Missing native_answer symbol");
                }
            } // Đóng arena: yêu cầu unload thư viện gắn với lookup.

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Recording saved: native-events.jfr");
    }
}
```

### 6.3. Biên dịch và chạy

```bash
# Linux, GCC/Clang hoặc cc tương thích; thư viện phải có kiến trúc
# CPU tương ứng với JVM (ví dụ đều là x86_64).
cc -std=c11 -fPIC -shared -o libjfrprobe.so jfrprobe.c

# Dùng JDK 22 trở lên cho cả javac lẫn java.
javac NativeLibraryEventsDemo.java
java --enable-native-access=ALL-UNNAMED NativeLibraryEventsDemo

jfr print --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload \
    native-events.jfr
```

**Stdout của chương trình Java khi chạy thành công:**

```text
Recording saved: native-events.jfr
```

Phần output từ `jfr print` **không có chuỗi cố định**: timestamp, đường dẫn, thread, stack và duration thay đổi theo JVM, môi trường và lịch ghi. Với bản HotSpot có đủ event, hãy tìm bản ghi có `name` chứa `libjfrprobe.so` và kiểm tra `success=true` của thao tác load; khi arena đóng, kiểm tra unload event tương ứng. Nếu hệ điều hành giữ thư viện vì dependency/reference khác, phân biệt unload request/event với việc thực sự unmap khỏi tiến trình.

**Vì sao đây là ví dụ hợp lệ từ Java 22, không phải Java 17?** Hai event thao tác và FFM ổn định được dùng ở đây dành cho JDK 22+. Trên JDK 21, FFM còn ở trạng thái preview và phải dùng cấu hình tương ứng; JDK 17 không có API FFM ổn định theo kiểu import trên. Đối với JDK 17/21, dùng quy trình snapshot `jdk.NativeLibrary` trong các phần trước.

**Lưu ý phiên bản mới:** từ JDK 24, thao tác `System.load`/`System.loadLibrary` và một số JNI/FFM operation áp dụng quy định native access; `--enable-native-access=ALL-UNNAMED` cho mã classpath tránh cảnh báo hoặc chế độ từ chối khi thao tác bị xem là restricted. Trong ứng dụng modular, nên cấp quyền đúng module thay vì toàn classpath.

## 7. Phân tích bằng Java API thay vì chỉ đọc text

Với file `native-events.jfr` vừa tạo, ta có thể dùng `jdk.jfr.consumer.RecordingFile` để duyệt event và phân loại theo tên. Ví dụ sau là một **chương trình độc lập**; hãy dùng runtime có khả năng đọc định dạng file JFR đã ghi, lý tưởng là cùng bản JDK.

### Tệp `PrintNativeLibraryEvents.java`

```java
import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class PrintNativeLibraryEvents {
    public static void main(String[] args) throws Exception {
        Path input = Path.of(args.length == 0
                ? "native-events.jfr" : args[0]);

        try (RecordingFile recording = new RecordingFile(input)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();

                if (!type.equals("jdk.NativeLibraryLoad")
                        && !type.equals("jdk.NativeLibraryUnload")
                        && !type.equals("jdk.NativeLibrary")) {
                    continue;
                }

                String name = event.getString("name");
                System.out.println(type + " | " + name);

                // Snapshot không có success/errorMessage.
                if (!type.equals("jdk.NativeLibrary")) {
                    boolean success = event.getBoolean("success");
                    System.out.println("  success=" + success);

                    if (!success && event.hasField("errorMessage")) {
                        System.out.println("  error="
                                + event.getString("errorMessage"));
                    }
                }
            }
        }
    }
}
```

Chạy:

```bash
javac PrintNativeLibraryEvents.java
java PrintNativeLibraryEvents native-events.jfr
```

Stdout của trình đọc phụ thuộc các event thực tế, nên **không thể khẳng định trước số dòng hoặc thứ tự path**. Đây là chương trình Java 17+ về cú pháp và API consumer; file JFR được tạo trên JDK mới hơn có thể đòi runtime đọc phù hợp.

Khi mở rộng sang chương trình phân tích thật, nên lấy thêm `event.getStartTime()`, `event.getDuration()`, thread nếu có, và stack trace nếu khác `null`. Với các trường tùy chọn, kiểm tra metadata/`hasField`. Đừng giả định mọi event đều có stack trace; chẳng hạn sự kiện ở giai đoạn VM bootstrap hoặc thread state đặc biệt có thể không mang stack đầy đủ.

## 8. Điều tra các tình huống thực tế

### Trường hợp A — `UnsatisfiedLinkError` khi gọi `System.loadLibrary`

**Hiện tượng:** Java báo không nạp được `foo` hoặc thiếu một thư viện phụ thuộc.

1. Bắt JFR **trước** lời gọi thất bại; lọc `jdk.NativeLibraryLoad` theo `foo` hoặc đường dẫn liên quan.
2. Kiểm tra `success=false` và `errorMessage` (nếu có), đồng thời đọc exception của Java.
3. So sánh kiến trúc thư viện (32/64 bit, CPU architecture), vị trí file, quyền truy cập, ABI/JNI version và các dependency transitive.
4. Với Linux, có thể dùng `ldd`/`readelf` trên file đáng tin cậy để kiểm tra linkage; trên macOS dùng `otool -L`, trên Windows dùng công cụ kiểm tra PE/DLL dependencies phù hợp.
5. Khắc phục đúng tên/path/dependency rồi **tạo recording mới** và kiểm tra `success=true`.

Một `errorMessage` cho biết lỗi ở đường nạp mà VM quan sát; nó **không** nhất thiết phân biệt mọi lỗi logic xảy ra trong `JNI_OnLoad` hoặc sau khi load thư viện thành công.

### Trường hợp B — Không thấy unload event

Không có unload event có thể do:

- JFR bắt đầu quá muộn, đã dừng quá sớm hoặc `jdk.NativeLibraryUnload` chưa được bật.
- Thư viện vẫn có người sở hữu: class loader của JNI vẫn reachable, arena của FFM chưa đóng, hoặc code khác còn giữ native handle.
- JVM không thực hiện thao tác unload qua đường code mà JFR đang theo dõi.
- Trạng thái native của hệ điều hành vẫn giữ module do phụ thuộc/reference count.
- JVM/vendor/version không hỗ trợ event tương ứng.

Ví dụ, `System.loadLibrary("foo")` thường gắn native library với class loader của class gọi. Nó **không** có API Java để gọi `System.unloadLibrary` tương ứng. Khi class loader đủ điều kiện được thu gom thì JVM có thể dỡ thư viện theo vòng đời liên quan, nhưng GC và thời điểm unload **không được đảm bảo theo một deadline do ứng dụng tự chọn**. Gọi `System.gc()` không phải phép kiểm thử unload xác định.

### Trường hợp C — Thấy thư viện trong snapshot nhưng không có load event

Nếu `jdk.NativeLibrary` liệt kê `libfoo.so` mà `jdk.NativeLibraryLoad` không ghi nó, các khả năng gồm:

- Thư viện đã nạp trước khi recording khởi chạy.
- Event load bị disable, filter hoặc thao tác không đi qua hook được ghi.
- Runtime chỉ hỗ trợ snapshot, chẳng hạn HotSpot JDK 17/21.
- File không chứa toàn bộ thời gian quan sát (recording bị cắt bởi thiết lập retention/dump).

**Không kết luận** rằng có leak chỉ từ sự khác biệt này. Snapshot mô tả *tồn tại*; load event mô tả *sự thay đổi* trong khoảng được ghi.

### Trường hợp D — Có nhiều load/unload cùng tên

Lập timeline theo `startTime` và `name`, sau đó xem `success`, `duration`, thread và stack trace. Kiểm tra việc tạo/hủy class loader/plugin hoặc arena FFM theo request có làm thư viện nạp đi nạp lại không. Nhưng chỉ dựa trên tên file là chưa đủ để khẳng định mọi event đại diện cho một ánh xạ bộ nhớ khác nhau; caching, alias path, reference counting và implementation của OS loader đều ảnh hưởng.

Nếu thời lượng load tăng, đo thêm thao tác khởi tạo và dependency; `duration` của native load event chỉ là khoảng mà hook JFR đo được, **không tự chứng minh toàn bộ thời gian khởi tạo module Java hoặc JNI là nguyên nhân chậm**.

## 9. Checklist thực hành khi thu JFR native library

1. **Phiên bản:** xác nhận JDK/JVM vendor; `jfr metadata` có đủ `NativeLibraryLoad`, `NativeLibraryUnload` hay chỉ `NativeLibrary`.
2. **Phạm vi thời gian:** bắt recording trước bước gây sự cố; với lỗi startup dùng `-XX:StartFlightRecording` khi phù hợp.
3. **Cấu hình:** kiểm tra `enabled`, `threshold` và `stackTrace` bằng `JFR.check verbose=true` hoặc metadata/config.
4. **Thu file:** giữ bản recording đã stop/dump đúng thời điểm, ghi lại PID, JVM version và bước tái hiện để đối chiếu.
5. **Phân tích:** phân tách snapshot và thao tác; xem `name` + `success` + `errorMessage` + thời gian, sau đó thread/stack nếu có.
6. **Xác minh:** dùng thông tin Java exception, vòng đời class loader/arena, OS loader/dependency để kiểm tra giả thuyết thay vì kết luận từ một event.
7. **Bảo vệ dữ liệu chẩn đoán:** file `.jfr` có thể chứa đường dẫn thư viện, tên thread, stack trace và thông tin runtime nội bộ; giới hạn chia sẻ theo phạm vi cần thiết.

**Kết luận kỹ thuật:** từ JDK 22, `jdk.NativeLibraryLoad`/`jdk.NativeLibraryUnload` cho biết các thao tác nạp/dỡ native mà JVM ghi nhận, còn `jdk.NativeLibrary` cung cấp ảnh chụp những thư viện đang hiện diện. Kết hợp cả hai loại event, ghi đúng thời điểm và đối chiếu vòng đời JNI/FFM giúp chẩn đoán có cơ sở hơn so với chỉ nhìn `UnsatisfiedLinkError` hoặc một danh sách file `.so`/`.dll`.

## Tài liệu tham khảo

- Oracle JDK 22, [`jfr` command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jfr.html) và [`jcmd` command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jcmd.html).
- Oracle JDK 22, [`SymbolLookup.libraryLookup` và vòng đời `Arena`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- OpenJDK, [cấu hình JFR mặc định (default.jfc)](https://github.com/openjdk/jdk/blob/master/src/jdk.jfr/share/conf/jfr/default.jfc) để kiểm tra mặc định từng bản nguồn.
- Oracle JDK 24, [hướng dẫn chuyển đổi liên quan native access](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html).
