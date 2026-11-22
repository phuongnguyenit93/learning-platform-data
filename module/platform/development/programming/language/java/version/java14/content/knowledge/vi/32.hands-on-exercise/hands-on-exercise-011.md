# Kiểm chứng API thư viện mới bằng dữ liệu lỗi và dữ liệu biên

> **Phạm vi bài học:** Java 14 → **Thực hành tổng hợp** → **Kiểm chứng API thư viện mới bằng dữ liệu lỗi và dữ liệu biên**. Trong Java 14, **JFR Event Streaming (JEP 349)** và **Non-Volatile Mapped Byte Buffers (JEP 352)** đem đến các API có giá trị kiểm thử cao. Bài dùng **Java 17+** để chạy các ví dụ vì đó là baseline ổn định: record được giới thiệu ở Java 14 dưới dạng preview nhưng **chính thức từ Java 16**. Các API minh họa vẫn được tài liệu JDK hiện đại hỗ trợ, không dùng preview/legacy.

## 1. Điều cần chứng minh khi kiểm thử API

Việc gọi một API với dữ liệu hợp lệ và thấy chương trình không lỗi chỉ kiểm tra **happy path**. Một bộ test có chất lượng phải xác nhận cả:

- **Dữ liệu bình thường:** tạo record, đọc/ghi mapped buffer, ghi JFR event.
- **Dữ liệu lỗi:** `null`, chuỗi rỗng/whitespace, số âm, length quá lớn, quyền đọc/ghi không đủ.
- **Dữ liệu biên:** giá trị nhỏ nhất/lớn nhất còn hợp lệ, ngay bên ngoài cận, empty buffer, index cuối.
- **Trạng thái:** start stream một lần thì hợp lệ; start lần nữa bị từ chối.
- **Năng lực hệ thống:** một mode mapping có thể hoàn toàn hợp lệ về cú pháp nhưng OS/filesystem không hỗ trợ.
- **Bất đồng bộ:** sự kiện JFR có thể được flush sau một khoảng trễ, không nhất thiết tới callback ngay lập tức.
- **Cleanup:** các file/channel/recording phải được đóng và xóa có kiểm soát.

Từng test cần có **oracle**: bạn biết trước điều gì là đúng, sai hoặc **không thể sử dụng trên môi trường này**, rồi mới chạy code. Kết quả “có một exception bất kỳ” không đủ để gọi negative test là PASS.

### Những API dùng trong bài

| API | Mốc xuất hiện | Chức năng | Rủi ro cần test |
| --- | --- | --- | --- |
| `jdk.jfr.consumer.RecordingStream` | JDK 14, JEP 349 | Tiêu thụ JFR events từ JVM đang chạy | Giá trị cấu hình âm, start lặp, async |
| `jdk.nio.mapmode.ExtendedMapMode` | JDK 14, JEP 352 | `READ_WRITE_SYNC` cho non-volatile mapped file | Platform/FS-DAX không hỗ trợ |
| `FileChannel.map`, `MappedByteBuffer` | API NIO có từ trước, hiện hành | Ánh xạ file, truy cập byte vùng nhớ | Offset/length, buffer bounds, read-only |
| `record` | Preview Java 14; **final Java 16** | Mô hình dữ liệu request bất biến nông | Null, blank, cận số, normalized equality |
| `jdk.jfr.Recording`, `RecordingFile` | API JFR hiện hành | Ghi và đọc file JFR | Event payload/type, không nhầm với callback |

Đây là bài **kiểm chứng thư viện trong ứng dụng Java hiện đại**, không phải tuyên bố mọi API kể trên được tạo ra đúng năm Java 14.

## 2. Phân lớp dữ liệu thử nghiệm

Giả sử API của ứng dụng nhận `Request(String code,int size)`. Quy định:

- `code` phải khác `null` và còn ít nhất một ký tự sau `strip()`.
- `size` nằm trong đoạn đóng **[1,4096]**.
- Nếu hợp lệ, constructor lưu code sau khi đã loại whitespace ở đầu/cuối.

| Input | Lớp dữ liệu | Kết quả kỳ vọng |
| --- | --- | --- |
| `("ABC",20)` | Hợp lệ thông thường | Tạo được record |
| `(" A ",1)` | Biên dưới và normalization | `code="A", size=1` |
| `("A",4096)` | Biên trên hợp lệ | Tạo được record |
| `("A",0)` | Vừa ngoài cận dưới | `IllegalArgumentException` |
| `("A",-1)` | Số âm | `IllegalArgumentException` |
| `("A",4097)` | Vừa ngoài cận trên | `IllegalArgumentException` |
| `("A",Integer.MAX_VALUE)` | Số cực lớn | `IllegalArgumentException` theo miền nghiệp vụ |
| `(null,1)` | Null reference | `NullPointerException` |
| `("",1)` | Empty string | `IllegalArgumentException` |
| `(" \t ",1)` | Whitespace-only | `IllegalArgumentException` |

Các giá trị **cận - 1, cận, cận + 1** đặc biệt hữu ích để phát hiện lỗi off-by-one. Nhưng không nên chỉ thử các biên: thêm một số giá trị giữa miền, dữ liệu Unicode và nhiều kết hợp thuộc tính khi cần.

### Đừng dạy “số 0 luôn sai”

Với `Request`, size0 sai do quy tắc của **ứng dụng**. Nhưng `FileChannel.map(...,0)` có thể hợp lệ và tạo buffer 0 bytes; `RecordingStream.setMaxSize(0)` có nghĩa **không giới hạn kích thước lưu trữ**. Một test chỉ được phép phán đoán dựa vào **hợp đồng của phương thức đang gọi**.

## 3. Negative tests phải nhận diện đúng loại lỗi

Sai lầm thường gặp:

~~~java
try {
    new Request("A", 0);
} catch (Exception ignored) {
    System.out.println("PASS");
}
~~~

Đây là **đoạn minh họa không độc lập**. Nó có thể báo PASS khi phát sinh một exception **không liên quan**, và không báo fail nếu lệnh bất ngờ chạy thành công.

Test tốt phải:

1. Thực thi một hành động được dự đoán là sẽ bị từ chối.
2. Nếu **không có exception**, ném `AssertionError`.
3. Nếu có exception **khác loại**, cũng fail và ghi nhận actual class.
4. Chỉ chấp nhận đúng exception class (hoặc subtype được hợp đồng cho phép).
5. Không assert nguyên văn message trừ khi message chính là API contract đã công bố.

Bài dùng helper `expect(...)` để thực hiện việc này. Mọi kiểm tra invariant khác dùng `require(...)` ném `AssertionError`, **không phụ thuộc JVM flag `-ea`**. Java `assert` thường bị tắt mặc định khi không bật `java -ea`.

## 4. Hiểu đúng ranh giới trước khi viết code

### 4.1. Record: validation do constructor thực thi

Một `record Request(String code,int size)` không tự kiểm tra null/size. Phần compact canonical constructor viết:

- `Objects.requireNonNull(code)` kiểm tra null.
- `strip()` loại khoảng trắng được Java phân loại là whitespace ở hai đầu.
- `code.isEmpty()` từ chối chuỗi sau normalize rỗng.
- `size<1 || size>4096` từ chối số ngoài miền.

Bởi record giữ component fields sau normalization, `new Request(" X ",1)` và `new Request("X",1)` có equality và hash tương ứng. Đó là tác dụng của **constructor**, không phải tự động do mọi record.

### 4.2. FileChannel mapping: size hợp lệ và byte width

Theo Javadoc hiện hành của `FileChannel.map(MapMode,long,long)`:

- `position` không được âm.
- `size` không được âm và không quá `Integer.MAX_VALUE` với overload trả `MappedByteBuffer`.
- `READ_ONLY` cần channel đọc được; `READ_WRITE` cần **đọc và ghi**.
- Buffer từ `READ_ONLY` không thể ghi.
- `size=0` có thể tạo mapped buffer capacity 0.
- Behavior khi map ra ngoài nội dung file **không được quy định portable**; tránh dùng làm oracle.

Với một file **16 bytes**, `getInt(index)` đọc **4 bytes**. Index cuối hợp lệ là **12** vì cần các bytes 12,13,14,15. `getInt(13)` truy cập ra ngoài `limit=16` nên phải ném `IndexOutOfBoundsException`. Đây là test off-by-one có tính quyết định.

| Test | Kết quả |
| --- | --- |
| `putInt(0,123)`, `putInt(12,456)` và đọc lại | PASS |
| `map(...,-1,4)` | `IllegalArgumentException` |
| `map(...,0,-1)` | `IllegalArgumentException` |
| `map(...,0,(long)Integer.MAX_VALUE+1)` | `IllegalArgumentException` |
| `getInt(13)` trên buffer limit16 | `IndexOutOfBoundsException` |
| `map(READ_ONLY,16,0)` | `capacity=0` |
| `put(0,byte)` trên read-only buffer | `ReadOnlyBufferException` |
| Map `READ_WRITE` với channel chỉ `READ` | `NonWritableChannelException` |

Chú ý hai lớp quyền: **channel không cho ghi** khác với **buffer read-only**. Dù cùng bị từ chối, hai trường hợp có hai exception classes khác nhau.

### 4.3. JFR RecordingStream: settings và lifecycle

`RecordingStream` (JDK 14+) có:

- `setMaxAge(Duration)`: **Duration âm** không hợp lệ → `IllegalArgumentException`.
- `setMaxSize(long)`: số âm không hợp lệ → `IllegalArgumentException`; `0` là unlimited.
- `startAsync()`: khởi chạy bất đồng bộ; **gọi start lần hai** khi đang chạy → `IllegalStateException`.
- `onEvent(name,callback)`: nhận events qua callback khi dữ liệu được xử lý.
- `close()`/try-with-resources: đóng stream khi xong.

Không nên assert rằng callback chắc chắn đã chạy sau một `Thread.sleep(250)`: JFR events có batching/flush. Chương trình chính chỉ test **lifecycle** của stream; phần kiểm tra payload được thực hiện bằng `Recording`/`RecordingFile` riêng.

### 4.4. NVM: capability và lỗi dữ liệu không phải một

`ExtendedMapMode.READ_WRITE_SYNC` có trên API từ JDK 14 và yêu cầu môi trường hỗ trợ. Trên Linux, cơ chế SYNC map liên quan `MAP_SYNC`/`MAP_SHARED_VALIDATE`, DAX-capable backing storage, filesystem và file thực tế.

- `IllegalArgumentException` ở offset âm là **negative input test PASS**.
- `UnsupportedOperationException` khi dùng `READ_WRITE_SYNC` có thể nghĩa là **mode không được implementation hỗ trợ**.
- `IOException` có thể cho thấy filesystem/OS/device/I/O không thể đáp ứng, cần xem cause.
- SYNC map thành công tại một file chỉ cho thấy **path đó hỗ trợ**, không chứng minh mọi file hoặc crash recovery.
- Một ổ NVMe SSD thông thường không tự động có đặc tính **byte-addressable persistent memory**.

Khi `READ_WRITE_SYNC` không hỗ trợ, không được âm thầm dùng `MapMode.READ_WRITE` rồi gọi đó là “NVM-SYNC PASS”. Nếu nghiệp vụ cho phép fallback, phải báo rõ semantics khác và kiểm thử lại theo hợp đồng mới.

## 5. Chương trình Java 17+ chạy độc lập

Bộ test tích hợp record validation, NIO boundary/permission, JFR settings/lifecycle và custom event payload. Dữ liệu thử nghiệm chỉ nằm ở **file tạm** của chính chương trình.

**File: `ApiBoundaryChecks.java`**

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.channels.NonWritableChannelException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordingStream;
import jdk.nio.mapmode.ExtendedMapMode;

public class ApiBoundaryChecks {
    record Request(String code, int size) {
        Request {
            code = Objects.requireNonNull(code, "code").strip();
            if (code.isEmpty()) throw new IllegalArgumentException("blank code");
            if (size < 1 || size > 4096) throw new IllegalArgumentException("size");
        }
    }

    @Name("lab.ValidationEvent")
    static class ValidationEvent extends Event {
        int size;
    }

    @FunctionalInterface
    interface ThrowingAction { void run() throws Exception; }

    static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void expect(String name, Class<? extends Throwable> type,
                       ThrowingAction action) {
        try {
            action.run();
            throw new AssertionError(name + " did not throw " + type.getSimpleName());
        } catch (AssertionError bad) {
            throw bad;
        } catch (Throwable actual) {
            if (!type.isInstance(actual)) {
                throw new AssertionError(name + ": got " + actual.getClass().getName(),
                        actual);
            }
            System.out.println(name + "=" + actual.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        require(new Request(" X ", 1).equals(new Request("X", 1)),
                "normalization");
        require(new Request("max", 4096).size() == 4096,
                "maximum valid size");
        System.out.println("recordBoundaries=PASS");
        expect("nullCode", NullPointerException.class,
                () -> new Request(null, 1));
        expect("blankCode", IllegalArgumentException.class,
                () -> new Request(" \t ", 1));
        expect("zeroSize", IllegalArgumentException.class,
                () -> new Request("x", 0));
        expect("negativeSize", IllegalArgumentException.class,
                () -> new Request("x", -1));
        expect("aboveMax", IllegalArgumentException.class,
                () -> new Request("x", 4097));

        Path file = Files.createTempFile("api-boundary-", ".bin");
        try {
            Files.write(file, new byte[16]);
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                MappedByteBuffer mapped = channel.map(
                        FileChannel.MapMode.READ_WRITE, 0, 16);
                mapped.putInt(0, 123);
                mapped.putInt(12, 456);
                mapped.force(12, Integer.BYTES);
                require(mapped.getInt(0) == 123 && mapped.getInt(12) == 456,
                        "mapping valid endpoints");
                System.out.println("mappedEdges=PASS");
                expect("negativeMapOffset", IllegalArgumentException.class,
                        () -> channel.map(FileChannel.MapMode.READ_WRITE, -1, 4));
                expect("negativeMapLength", IllegalArgumentException.class,
                        () -> channel.map(FileChannel.MapMode.READ_WRITE, 0, -1));
                expect("tooLargeMap", IllegalArgumentException.class,
                        () -> channel.map(FileChannel.MapMode.READ_WRITE,
                                0, (long) Integer.MAX_VALUE + 1));
                expect("pastLastInt", IndexOutOfBoundsException.class,
                        () -> mapped.getInt(13));
                MappedByteBuffer empty = channel.map(
                        FileChannel.MapMode.READ_ONLY, 16, 0);
                require(empty.capacity() == 0, "zero-length mapping");
                System.out.println("emptyMapCapacity=" + empty.capacity());
            }
            try (FileChannel ro = FileChannel.open(file, StandardOpenOption.READ)) {
                MappedByteBuffer readOnly = ro.map(
                        FileChannel.MapMode.READ_ONLY, 0, 16);
                expect("modifyReadOnly", ReadOnlyBufferException.class,
                        () -> readOnly.put(0, (byte) 1));
                expect("mapWriteOnReadOnly", NonWritableChannelException.class,
                        () -> ro.map(FileChannel.MapMode.READ_WRITE, 0, 16));
            }

            // DAX/NVM probe: only result on current path, not portable PASS.
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                try {
                    MappedByteBuffer sync = channel.map(
                            ExtendedMapMode.READ_WRITE_SYNC, 0, 16);
                    sync.put(0, (byte) 5);
                    sync.force(0, 1);
                    System.out.println("nvmSyncMap=SUPPORTED");
                } catch (UnsupportedOperationException | IOException e) {
                    System.out.println("nvmSyncMap=UNAVAILABLE:" +
                            e.getClass().getSimpleName());
                }
            }
        } finally {
            try {
                Files.deleteIfExists(file);
            } catch (IOException ex) {
                file.toFile().deleteOnExit();
                System.err.println("tempFileDeferredCleanup=" +
                        ex.getClass().getSimpleName());
            }
        }

        try (RecordingStream stream = new RecordingStream()) {
            expect("negativeMaxAge", IllegalArgumentException.class,
                    () -> stream.setMaxAge(Duration.ofSeconds(-1)));
            expect("negativeMaxSize", IllegalArgumentException.class,
                    () -> stream.setMaxSize(-1));
            stream.setMaxAge(Duration.ofSeconds(5));
            stream.enable(ValidationEvent.class).withoutThreshold();
            AtomicInteger observed = new AtomicInteger();
            stream.onEvent("lab.ValidationEvent", e -> observed.incrementAndGet());
            stream.startAsync();
            expect("startTwice", IllegalStateException.class, stream::startAsync);
            ValidationEvent event = new ValidationEvent();
            event.size = 1;
            event.commit();
            Thread.sleep(250);
            System.out.println("jfrStreamLifecycle=PASS");
            // observed count not asserted: streaming is asynchronous.
        }

        Path jfr = Files.createTempFile("api-boundary-", ".jfr");
        try {
            try (Recording rec = new Recording()) {
                rec.enable(ValidationEvent.class).withoutThreshold();
                rec.start();
                ValidationEvent e = new ValidationEvent();
                e.size = 4096;
                e.commit();
                rec.stop();
                rec.dump(jfr);
            }
            long count = RecordingFile.readAllEvents(jfr).stream()
                    .filter(e -> e.getEventType().getName()
                            .equals("lab.ValidationEvent"))
                    .filter(e -> e.getInt("size") == 4096)
                    .count();
            require(count >= 1, "JFR event data must be present");
            System.out.println("jfrRecordingData=PASS");
        } finally {
            Files.deleteIfExists(jfr);
        }
        System.out.println("ALL_CHECKS_PASSED");
    }
}
~~~

### 5.1. Cách chạy

~~~bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 ApiBoundaryChecks.java
java --add-modules jdk.nio.mapmode ApiBoundaryChecks
~~~

`--add-modules jdk.nio.mapmode` cần thiết với ví dụ classpath sử dụng `ExtendedMapMode` thuộc module **JDK-specific**. Khi sử dụng custom runtime image, xác nhận các modules `jdk.jfr` và `jdk.nio.mapmode` có thực sự được đóng gói. Không cần `--enable-preview`.

### 5.2. Stdout đã kiểm tra trên Windows/JDK 24

~~~text
recordBoundaries=PASS
nullCode=NullPointerException
blankCode=IllegalArgumentException
zeroSize=IllegalArgumentException
negativeSize=IllegalArgumentException
aboveMax=IllegalArgumentException
mappedEdges=PASS
negativeMapOffset=IllegalArgumentException
negativeMapLength=IllegalArgumentException
tooLargeMap=IllegalArgumentException
pastLastInt=IndexOutOfBoundsException
emptyMapCapacity=0
modifyReadOnly=ReadOnlyBufferException
mapWriteOnReadOnly=NonWritableChannelException
nvmSyncMap=UNAVAILABLE:UnsupportedOperationException
negativeMaxAge=IllegalArgumentException
negativeMaxSize=IllegalArgumentException
startTwice=IllegalStateException
jfrStreamLifecycle=PASS
jfrRecordingData=PASS
ALL_CHECKS_PASSED
~~~

Trong lần chạy thực tế: **compile exit 0, run exit 0** và toàn bộ assertions PASS. Dòng `nvmSyncMap` **phụ thuộc thiết bị/OS/file**: trên môi trường khác có thể là `SUPPORTED`, `UNAVAILABLE:IOException` hoặc một diagnostic khác. Đừng assert nguyên văn toàn bộ stdout như một hợp đồng portable. Một số OS không cho xóa file đang mapped ngay, nên stderr có thể ghi `tempFileDeferredCleanup`; chương trình có `deleteOnExit()` để dọn sau khi process kết thúc.

## 6. Giải thích kết quả: bốn nhóm cần tách

### 6.1. Record và kiểu ngoại lệ

- `recordBoundaries=PASS`: cận dưới 1 và cận trên 4096 hợp lệ, normalization tạo record tương đương.
- `nullCode=NullPointerException`: `Objects.requireNonNull` xử lý thiếu reference.
- `blankCode=IllegalArgumentException`: chuỗi không null nhưng trở thành rỗng sau `strip`.
- `zeroSize`, `negativeSize`, `aboveMax`: đều từ điều kiện `size<1 || size>4096`.

Việc có `record` không tự làm validation; các điều kiện thật trong compact constructor quyết định hành vi. Với dữ liệu Unicode, cần hiểu `String.strip()` chỉ dùng Unicode whitespace theo định nghĩa Java, không đồng nghĩa xóa mọi ký tự vô hình.

### 6.2. Mapped file: đủ bytes và đủ quyền

- `mappedEdges=PASS`: test đọc/ghi bốn bytes đầu/cuối.
- `pastLastInt` ném `IndexOutOfBoundsException` ở index 13 dù index ấy nhỏ hơn limit16; vì `getInt` đọc đến byte 16.
- `negativeMapOffset`, `negativeMapLength` và `tooLargeMap` bị từ chối theo preconditions.
- `emptyMapCapacity=0` cho thấy zero-length khác lỗi âm.
- `modifyReadOnly` kiểm tra tính read-only của **buffer**.
- `mapWriteOnReadOnly` kiểm tra quyền ghi của **channel**.

`MappedByteBuffer.force(12,4)` flush vùng đã thay đổi theo semantics mapping, không phải transaction atomic. Không thử truncate vùng đang mapped rồi gán một exception cố định cho mọi OS vì Javadoc mô tả nhiều hành vi dependent/unspecified.

### 6.3. JFR: kết quả cấu hình khác callback delivery

`negativeMaxAge` và `negativeMaxSize` là các negative tests ổn định theo Javadoc. `startTwice` xác nhận lifecycle.

Nhưng `RecordingStream` là API streaming bất đồng bộ; **không** assert callback nhận đúng một event sau `Thread.sleep(250)`. Một JVM có thể flush event chậm hơn mà vẫn đúng. Test event payload bằng `Recording` + `RecordingFile` xác nhận một event có tên `lab.ValidationEvent` chứa field `size=4096`.

Đừng kết luận “callback streaming đã chạy” chỉ từ `jfrRecordingData=PASS`: hai bài kiểm thử **khác nhau**. Muốn test callback thực, sử dụng `CountDownLatch`, timeout, ghi lỗi trong callback và đóng stream đúng vòng đời.

### 6.4. NVM: không khả dụng không đồng nghĩa dữ liệu sai

Kết quả `nvmSyncMap=UNAVAILABLE:UnsupportedOperationException` xác nhận trên đường file của lần test **không hỗ trợ** mode `READ_WRITE_SYNC`. Code vẫn kiểm chứng đúng khả năng và không báo sai rằng NVM đã hoạt động.

Với yêu cầu nghiệp vụ **bắt buộc** SYNC mapping, trạng thái này phải làm **integration/release gate không đạt**. Với suite unit test portable, đó là capability result được ghi rõ, không phải lỗi của phép thử null/size/FileChannel.

Trên Linux muốn kiểm tra NVM thật cần tệp nằm trên **DAX-capable storage** và filesystem/file có DAX đang hoạt động. Vì ví dụ tạo file bằng `Files.createTempFile(prefix,suffix)` ở temporary directory mặc định, nó **không tự kiểm chứng một mount PMEM riêng**. Đối với test hardware, dùng `Files.createTempFile(targetDirectory,...)` đúng filesystem cần triển khai.

## 7. Kiểm thử dữ liệu lỗi và API state khi phát triển thư viện

Khi nhóm của bạn thiết kế API mới, trước tiên liệt kê **trạng thái và tiền điều kiện**:

| Phạm vi | Test dương tính | Test âm tính |
| --- | --- | --- |
| Giá trị chuỗi | Code hợp lệ sau normalization | `null`, rỗng, whitespace-only |
| Số | 1, giữa miền, 4096 | 0, âm, 4097, cực lớn |
| Buffer index | 0, index 12 cho `getInt` | Index -1, index13 ở limit16 |
| File mapping | `READ_WRITE` trên READ+WRITE channel | `READ_WRITE` trên READ-only channel |
| Buffer permission | Đọc buffer `READ_ONLY` | Ghi buffer `READ_ONLY` |
| JFR configuration | `setMaxAge(5s)`, `setMaxSize(0)` | Duration âm, size âm |
| JFR lifecycle | Start một lần, đóng đúng | Start hai lần |
| JFR event payload | Ghi event rồi đọc lại đúng fields | Field/type sai; sự kiện không có |
| SYNC NVM | Map trên file/FS thật có hỗ trợ | Unsupported implementation, permission/I/O |

**Bẫy “bắt mọi Exception”:** âm tính `IllegalArgumentException` không được coi là PASS khi mã phát sinh `IOException` khác nguồn. Test phải phân biệt input violation, resource failure và environment limitation.

**Bẫy “hardcode error message”:** Javadoc thường quy định class ngoại lệ, không quy định từng dấu câu trong message. So sánh nguyên văn message có thể làm test fail giả khi nâng JDK.

**Bẫy “chỉ in console”:** những dòng println không tự đánh dấu failure. Phải có `require`/JUnit assertion và exit code khác 0 khi bất biến sai.

**Bẫy “Java assert tự chạy”:** `assert` thường bị tắt theo mặc định. Demo dùng `require` ném `AssertionError` rõ ràng, không cần `-ea`.

## 8. Test mở rộng: property-based và dữ liệu biên

Một số tính chất hữu ích:

1. Với mọi `size` trong `[1,4096]`, `Request("A",size)` tạo thành công và accessor trả đúng size.
2. Với mọi `size<=0` hoặc `size>4096`, constructor từ chối đúng loại ngoại lệ.
3. Với các cặp code hợp lệ có khoảng trắng hai đầu, normalized records có equality và hash nhất quán.
4. Với mapped buffer limit16, `getInt(index)` hợp lệ cho index `0..12` và invalid cho index `13..16`.
5. Với `RecordingStream.setMaxSize(0)`, API chấp nhận vì đây là cú pháp unlimited.
6. Với `RecordingStream` đã start, `startAsync` lần hai phải từ chối.
7. Với event JFR được ghi và đọc lại, field payload phải đúng tên/kiểu/giá trị.
8. Với capability NVM, nếu không hỗ trợ thì không tự fallback và gọi tính năng được hỗ trợ.

### Thử overflow mà không cần cấp phát file khổng lồ

`(long) Integer.MAX_VALUE + 1` giúp test overload `FileChannel.map` trả `MappedByteBuffer`; giá trị này vi phạm size contract và bị từ chối trước khi cần cấp phát mapping lớn.

Với API tự viết, tránh overflow ở biểu thức `offset+length`: sau khi kiểm tra không âm và `length<=capacity`, có thể kiểm tra `offset>capacity-length` thay vì chỉ dùng phép cộng có khả năng tràn.

### Sinh nhiều tổ hợp có kiểm soát

Các trường hợp bổ sung gồm `Integer.MIN_VALUE`/`MAX_VALUE`, Unicode whitespace, empty file, index -1, size0, directory vs regular file, no write permission, already-closed channel và callback timeout. Không phải mọi trường hợp đều có exception portable khi có OS involvement. Lựa chọn test **từ Javadoc của đúng overload** và ghi rõ giới hạn.

Không fuzz trên data file production; dùng sandbox, temp directories, timeout, kiểm soát RAM và teardown.

## 9. Phân loại kết quả trong CI/CD

| Case | Runner | PASS nghĩa là gì? |
| --- | --- | --- |
| Record/exception/bounds | JDK 17+ | Kết quả và ngoại lệ đúng hợp đồng |
| FileChannel/ByteBuffer | JDK + filesystem ghi được | Đúng bytes/index/permissions |
| JFR lifecycle | Full JDK có `jdk.jfr` | Đúng start/settings behavior |
| JFR payload | Full JDK có JFR | File đọc lại có đúng event và field |
| SYNC capability probe | JDK có `jdk.nio.mapmode` | Báo đúng SUPPORTED/UNAVAILABLE |
| NVM business integration | Máy có FS-DAX + PMEM thật | SUPPORTED là điều kiện bắt buộc |
| Crash durability | Testbed riêng | Khôi phục dữ liệu đúng protocol |

**Không gom tất cả vào một PASS duy nhất.** Chương trình in `ALL_CHECKS_PASSED` nghĩa là tất cả **assertions của suite** đã đạt; nó **không** khẳng định đường SYNC mapping hoạt động. Nếu sản phẩm cần NVM, một **release gate riêng** phải từ chối `UNAVAILABLE`.

Nên lưu `caseName`, `expectedClass`, `actualClass`, `jdkVersion`, `OS`, `filesystem`, `moduleFlags`, `elapsedTime`, `cleanupStatus` và trạng thái `PASS/FAIL/UNAVAILABLE/SKIPPED/BLOCKED`. Với callback test, ghi thêm event settings, timeout, số event nhận được và callback errors. Retry liên tục không làm một oracle thiếu đồng bộ trở nên đúng.

### Không biến test thành rủi ro vận hành

- Dùng file tạm và `try-with-resources`, không truncate hoặc ghi đè file thật.
- Không log credentials, tokens hay thông tin nhạy cảm vào JFR recording.
- Không làm stress/power-fail tests trên production.
- Khi file mapped còn sống và không xóa ngay được, ghi nhận deferred cleanup.
- Không để JFR stream chạy vô hạn hoặc lưu recording không có giới hạn.
- Không chạy `--add-modules`/cấu hình JVM tùy tiện trên môi trường không được phép.
- Khi thay JDK, chạy lại đúng bộ negative/boundary assertions; không mặc định kết quả của hardware probe giống trước.

## 10. Lỗi phổ biến cần tránh

| Nhận định sai | Điều đúng |
| --- | --- |
| “Có API trong JDK thì máy chắc chắn hỗ trợ SYNC NVM.” | Module tồn tại không đảm bảo OS/device/filesystem hỗ trợ. |
| “Số 0 ở mọi method đều sai.” | Tùy hợp đồng; `setMaxSize(0)` hợp lệ. |
| “Có exception bất kỳ thì negative test PASS.” | Chỉ đúng loại/cause được xác định trước. |
| “Không ném exception tức là thành công.” | Còn phải assert return, side effects và state. |
| “getInt(13) nằm trong 16 bytes.” | `getInt` cần bốn bytes; cận cuối là 12. |
| “Channel READ-only giống buffer READ-only.” | Hai đối tượng và exception classes khác nhau. |
| “Map vượt EOF tự tăng file trên mọi OS.” | Javadoc không bảo đảm chung. |
| “JFR commit xong, callback nhận ngay.” | Có batching; test cần synchronization. |
| “JFR recording file đúng nghĩa callback stream đã chạy.” | Chúng là hai test khác. |
| “SYNC unavailable thì tất cả Java APIs đều hỏng.” | Có thể chỉ do không có DAX/PMEM. |
| “`MapMode.READ_WRITE` fallback tương đương SYNC.” | Persistence semantics khác nhau. |
| “Record final từ Java 14.” | Java 14 là preview, final từ Java 16. |
| “`force()` tạo atomic transaction.” | Flush khác crash consistency. |
| “Java `assert` mặc định luôn được bật.” | Phải dùng `-ea` hoặc check/JUnit. |

## 11. Checklist QA và bài tập

**Checklist:**

- [ ] Chỉ sử dụng API còn áp dụng trên các JDK hiện hành; biết chính xác mốc preview/final.
- [ ] Có hợp đồng và **test oracle** rõ cho từng input.
- [ ] Có happy path, null, blank, min/max, vừa ngoài cận, âm, zero và overflow nếu liên quan.
- [ ] Negative tests khẳng định **đúng exception class**, không che lỗi khác.
- [ ] Có test quyền FileChannel và mapped buffer.
- [ ] Không dựa vào behavior unspecified như map vượt EOF.
- [ ] Kiểm tra JFR settings/lifecycle và payload; không assert callback timing theo một sleep ngắn.
- [ ] Phân biệt **capability unavailable** với **test thất bại**.
- [ ] Nếu business cần NVM, có integration test trên FS-DAX thực.
- [ ] Các resources được đóng, file test cleanup có kiểm soát.
- [ ] CI lưu JDK/version/OS/module flags, exit code và lý do case fail.
- [ ] Không dùng data thật hoặc gây power-fail trên production.

**Bài tập:**

1. Bổ sung `new Request("",1)` và `new Request(null,1)`; giải thích khác biệt exception.
2. Bổ sung test `size=2` và `size=4095`, rồi `size=Integer.MAX_VALUE`.
3. Dùng `new Request(" A ",1)` và `new Request("A",1)` làm keys của `HashMap`; kiểm tra equality/hash.
4. Thử `mapped.getInt(12)`, `getInt(13)` và giải thích off-by-one theo 4 bytes.
5. Test `map(READ_ONLY,16,0)` và giải thích vì sao zero length hợp lệ.
6. Test `READ_WRITE` trên channel chỉ đọc; phân biệt với `put` vào read-only mapped buffer.
7. Thử `setMaxSize(0)` và `setMaxSize(-1)`, đối chiếu Javadoc.
8. Viết JFR callback test dùng `CountDownLatch` và timeout thay sleep.
9. Ghi hai custom events `size=1`, `size=4096` vào recording, đọc và xác minh payload.
10. Trên Linux có FS-DAX, đổi `Files.createTempFile` sang directory DAX đã được phê duyệt rồi thử SYNC map.
11. Phân tách suite thành portable tests và hardware-dependent tests; định nghĩa release gate không false-pass.
12. Viết report `case,input,expected,actual,JDK,OS,capability,cleanup` cho nhóm.

## 12. Tài liệu chính thức còn hiệu lực

- [OpenJDK JEP 349 – JFR Event Streaming](https://openjdk.org/jeps/349): API streaming từ JDK 14.
- [Oracle Java SE 25 – RecordingStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): `setMaxAge`, `setMaxSize`, `startAsync`.
- [Oracle Java SE 25 – RecordingFile](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): kiểm tra payload sau recording.
- [OpenJDK JEP 352 – Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): SYNC modes ở Java 14.
- [Oracle Java SE 25 – ExtendedMapMode](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): `READ_WRITE_SYNC` và unsupported behavior.
- [Oracle Java SE 25 – FileChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html): preconditions của `map`.
- [Oracle Java SE 25 – ByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): absolute indexed `getInt`.
- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395): record final ở Java 16.
- [Oracle Java SE 25 – Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): canonical constructor.
- [Oracle Java downloads](https://www.oracle.com/java/technologies/downloads/): **JDK 27** là feature release mới nhất vào tháng 11/2026, trong khi **JDK 25** là bản LTS; các API của bài được dùng từ baseline Java 17 và còn có tài liệu Java 25.

**Kết luận:** khi kiểm chứng API thư viện, **đầu vào đúng, dữ liệu lỗi, dữ liệu biên, trạng thái bất hợp lệ và giới hạn OS** đều quan trọng. Test cần một oracle đủ chặt để không false-pass, nhưng không được ép những yếu tố như NVM/OS capability và JFR callback timing thành một giá trị cố định.