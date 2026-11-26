# Quan sát hành vi GC bằng unified logging, JFR và tải có lời gọi native

G1 Region Pinning là thay đổi trong cách HotSpot G1 xử lý các vùng nhớ đang được mã native truy cập qua JNI critical region. Trước đây, một số collector có thể phải trì hoãn hoặc hạn chế garbage collection khi native code giữ con trỏ tới dữ liệu trên Java heap. Từ JDK 22, G1 có thể tiếp tục thu gom các vùng khác trong khi giữ nguyên vị trí những object đang được native code sử dụng.

Đây là thay đổi implementation của G1 theo JEP 423, không phải API Java, không phải preview và cũng không cần bật một cờ riêng. Trên JDK 27, G1 là garbage collector mặc định trong mọi môi trường theo JEP 523. JDK 27 là feature release mới nhất tại ngày 25-11-2026; JDK 25 là LTS mới nhất. Bài này dùng các công cụ quan sát chuẩn hiện hành: JVM Unified Logging, Java Flight Recorder (JFR), `jfr`, JDK Mission Control và `-Xcheck:jni`.

## 1. Region Pinning giải quyết vấn đề gì?

G1 chia Java heap thành nhiều region. Khi thu gom một collection set, G1 thường di chuyển các object còn sống từ region nguồn sang region đích, cập nhật tham chiếu rồi tái sử dụng vùng nhớ cũ. Cơ chế evacuation này giúp G1 thu hồi bộ nhớ theo từng phần và hạn chế phân mảnh.

JNI có một số hàm cho phép native code truy cập trực tiếp dữ liệu của Java array hoặc String. Ví dụ:

- `GetPrimitiveArrayCritical` và `ReleasePrimitiveArrayCritical` truy cập các phần tử của primitive array.
- `GetStringCritical` và `ReleaseStringCritical` truy cập nội dung của Java String dưới dạng UTF-16.

Khi VM trả về con trỏ trực tiếp tới dữ liệu trên Java heap, object tương ứng phải giữ nguyên địa chỉ trong suốt thời gian native code đang dùng con trỏ. G1 không thể di chuyển object đó trong một lần evacuation đang diễn ra. G1 Region Pinning cho phép G1 ghim object/region liên quan và tiếp tục thu gom các vùng khác của heap.

<text color="secondary" weight="medium" size="sm">Mô hình khái niệm</text>

```text
Java heap được chia thành các region

+-----------+  +-----------+  +-----------+  +-----------+
| Region A  |  | Region B  |  | Region C  |  | Region D  |
| object    |  | object    |  | object    |  | object    |
+-----------+  +-----------+  +-----------+  +-----------+
                    ^
                    |
          JNI critical pointer
                    |
              Native code

Trong GC pause:
- Region chứa object bị pin: không di chuyển object đang được native dùng.
- Region khác: G1 vẫn có thể evacuate và thu hồi bình thường.
```

Region pinning không có nghĩa là GC không còn pause hoặc mọi object đều có thể di chuyển. G1 vẫn thực hiện các pause cần thiết; chỉ có object được native giữ con trỏ là không thể di chuyển trong khoảng thời gian đó.

## 2. Trạng thái hiện hành của JNI critical functions và G1

`GetPrimitiveArrayCritical` và `GetStringCritical` không phải API mới của Java 22. Chúng đã có trong JNI từ JDK/JRE 1.2 và vẫn được liệt kê trong JNI Specification của Java SE 27. JEP 423 bổ sung khả năng xử lý pinning cho G1 trong JDK 22.

| Thành phần | Trạng thái tại JDK 27 |
| --- | --- |
| `GetPrimitiveArrayCritical` / `ReleasePrimitiveArrayCritical` | JNI API hiện hành; có từ JDK/JRE 1.2. |
| `GetStringCritical` / `ReleaseStringCritical` | JNI API hiện hành; có từ JDK/JRE 1.2. |
| G1 Region Pinning | Implementation của HotSpot G1, được đưa vào JDK 22 qua JEP 423. |
| Unified Logging với `-Xlog` | Cơ chế logging hiện hành của JVM. |
| Java Flight Recorder | Công cụ profiling/diagnostic hiện hành trong JDK. |

G1 là collector mặc định trong mọi môi trường ở JDK 27. Không cần bật một tùy chọn pinning riêng. Có thể dùng `-XX:+UseG1GC` để chỉ rõ collector khi muốn cùng một cấu hình thử nghiệm chạy trên nhiều môi trường hoặc phiên bản JDK.

Giới hạn phạm vi: JEP 423 mô tả thay đổi cho HotSpot G1. Không suy rộng cùng hành vi nội bộ này cho mọi collector hoặc mọi JVM implementation. JNI critical functions vẫn có thể trả về bản sao dữ liệu thay vì con trỏ trực tiếp; tham số `isCopy` giúp native code biết trường hợp đó.

## 3. Các giới hạn phải tuân thủ trong critical region

Sau khi gọi `GetPrimitiveArrayCritical`, native code phải gọi `ReleasePrimitiveArrayCritical` sớm nhất có thể. Trong khoảng giữa hai lời gọi, JNI Specification yêu cầu native code:

- Không gọi các JNI function khác.
- Không thực hiện system call có thể block và chờ một Java thread khác.
- Không giữ critical region trong thời gian dài.
- Kiểm tra con trỏ trả về có phải `NULL` hay không trước khi truy cập.

Các hạn chế tương tự áp dụng cho cặp `GetStringCritical` / `ReleaseStringCritical`. Region Pinning giúp G1 tiếp tục thu gom các region không bị pin; nó không xóa bỏ các quy tắc JNI này và không bảo đảm hiệu năng nếu native code giữ con trỏ quá lâu.

Ví dụ native function chỉ đọc một primitive array. Mọi JNI call cần thiết được thực hiện trước critical region; trong critical region chỉ duyệt dữ liệu; sau đó giải phóng con trỏ:

```c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_G1PinningLoad_checksum(JNIEnv *env, jclass type, jintArray input) {
    if (input == NULL) {
        jclass exceptionClass = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (exceptionClass != NULL) {
            (*env)->ThrowNew(env, exceptionClass, "input");
        }
        return 0;
    }

    // Lấy kích thước trước khi vào critical region.
    const jsize length = (*env)->GetArrayLength(env, input);

    jboolean isCopy = JNI_FALSE;
    jint *elements = (*env)->GetPrimitiveArrayCritical(env, input, &isCopy);
    if (elements == NULL) {
        // VM có thể đã đặt một exception đang chờ, ví dụ OutOfMemoryError.
        return 0;
    }

    jlong sum = 0;
    for (jsize i = 0; i < length; i++) {
        sum += elements[i];
    }

    // Chỉ đọc dữ liệu nên JNI_ABORT là phù hợp nếu VM đã tạo bản sao.
    (*env)->ReleasePrimitiveArrayCritical(env, input, elements, JNI_ABORT);
    return sum;
}
```

`JNI_ABORT` không ghi dữ liệu từ bản sao trở lại Java array. Nếu native code có sửa phần tử và muốn ghi thay đổi về Java array, cần chọn release mode theo đúng mục đích. Không được bỏ qua bước release hoặc dùng một con trỏ sau khi đã release.

Trong ví dụ này, `isCopy` chỉ cho biết VM đã tạo bản sao hay trả dữ liệu trực tiếp; nó không thay đổi quy tắc phải release. Không gọi `GetArrayLength`, `FindClass`, logging qua JNI hay bất kỳ JNI function nào khác sau khi vào critical region và trước khi release.

Nếu native code cần xử lý lâu, chờ I/O hoặc gọi JNI function khác, hãy cân nhắc sao chép dữ liệu sang native buffer trước rồi xử lý sau khi thoát critical region. Các hàm `GetIntArrayRegion` / `SetIntArrayRegion` và các hàm region tương ứng cho kiểu primitive có thể phù hợp khi chấp nhận sao chép một phần dữ liệu.

## 4. Đọc tín hiệu pinning bằng JVM Unified Logging

Tín hiệu trực tiếp và dễ kiểm tra nhất của G1 là lý do evacuation failure trong GC log. Tài liệu G1 của Java SE 27 mô tả dòng log có dạng:

```text
[9,740s][info ][gc] GC(26) Pause Young (Normal) (G1 Evacuation Pause)
    (Evacuation Failure: Allocation/Pinned) 2159M->402M(3000M) 6,108ms
```

Hai lý do trong ngoặc có ý nghĩa khác nhau:

| Lý do | Ý nghĩa |
| --- | --- |
| `Allocation` | G1 không tìm đủ vùng đích để di chuyển object. |
| `Pinned` | G1 gặp object không thể di chuyển vì đang được giữ cố định để native code truy cập an toàn, ví dụ qua `GetPrimitiveArrayCritical`. |

Hai lý do có thể xuất hiện cùng nhau. Nếu G1 không thể evacuate toàn bộ object ra khỏi một region, region đó tạm thời không được dùng để cấp phát. G1 đưa các region evacuation failure vào nhóm ứng viên để thử evacuate ở các GC tiếp theo. Trong tình huống xấu nhất, nếu GC không thu hồi được bộ nhớ, G1 có thể phải chạy Full GC.

### Bật unified logging

Để quan sát nguyên nhân và thời gian các phase, chạy ứng dụng với:

```bash
java \
  -Xms1g -Xmx1g \
  -XX:+UseG1GC \
  -Xlog:gc=info,gc+phases=debug:file=gc.log:time,uptime,level,tags \
  -Djava.library.path=native \
  -cp out G1PinningLoad
```

`-Xlog:gc=info` ghi thông tin collection và dòng `Evacuation Failure: ...`. `-Xlog:gc+phases=debug` bổ sung thời gian của các phase trong pause. Khi cần điều tra sâu hơn, có thể dùng `-Xlog:gc*=debug`; tùy chọn này tạo nhiều log hơn và nên giới hạn thời gian thu thập.

Các tùy chọn GC logging cũ như `-XX:+PrintGCDetails`, `-XX:+PrintGC` và `-Xloggc` không nên dùng cho cấu hình mới. Unified Logging là cách quan sát GC hiện hành.

### Cách đọc kết quả

1. Tìm `Evacuation Failure: Pinned` trong `gc.log`.
2. Đối chiếu GC ID, loại collection và thời gian pause.
3. Nếu xuất hiện `Allocation/Pinned`, tách riêng hai nguyên nhân; không quy toàn bộ failure cho pinning.
4. Xem các collection tiếp theo để biết region thất bại có được evacuate và thu hồi hay không.
5. Đối chiếu với thời điểm workload gọi native critical function và lượng allocation của ứng dụng.

Không phải mỗi lần gọi `GetPrimitiveArrayCritical` đều tạo ra một dòng `Pinned`. Dòng này chỉ xuất hiện khi quá trình evacuation thực sự gặp object bị pin trong vùng cần di chuyển. Vì vậy, không thấy `Pinned` trong một lần chạy không chứng minh rằng ứng dụng không có JNI critical region.

## 5. Dùng JFR để phân tích pause và tương quan workload

JFR bổ sung góc nhìn theo dòng thời gian. Có thể dùng recording để xem GC pause, các phase, heap trước/sau collection, allocation và hoạt động của thread. JFR phù hợp để trả lời các câu hỏi như:

- Pause nào dài nhất và chúng xảy ra lúc nào?
- Heap trước và sau GC thay đổi ra sao?
- Allocation rate có tăng mạnh trong lúc workload native chạy không?
- Thread thực thi native workload có hoạt động liên tục hay bị chờ?
- Native method sample hoặc stack sample nào xuất hiện trong khoảng thời gian cần điều tra, nếu event đó được bật và nền tảng hỗ trợ?

JFR là công cụ tương quan và phân tích thời gian. Khi cần xác nhận nguyên nhân cụ thể `Pinned` của G1, hãy dùng Unified Logging làm tín hiệu trực tiếp; không giả định mọi JFR recording đều có một event riêng tương ứng với từng pinned region.

### Ghi JFR khi khởi chạy

Có thể bật recording với cấu hình `profile`:

```bash
java \
  -Xms1g -Xmx1g \
  -XX:+UseG1GC \
  -XX:StartFlightRecording=filename=g1-pinning.jfr,settings=profile,dumponexit=true \
  -Djava.library.path=native \
  -cp out G1PinningLoad
```

JFR đã được tích hợp trong JDK hiện đại; không cần thêm cờ `-XX:+FlightRecorder`. Cờ này đã deprecated và không cần thiết từ JDK 8u40.

Sau khi ứng dụng kết thúc, xem tổng quan và in các event GC:

```bash
jfr summary g1-pinning.jfr
jfr print --events jdk.GCPhasePause,jdk.GCHeapSummary g1-pinning.jfr
```

Nếu recording đã bật native method sampling và JDK/CPU hỗ trợ, có thể xem thêm:

```bash
jfr print --events jdk.NativeMethodSample g1-pinning.jfr
```

Tên event và cấu hình có thể được kiểm tra trên đúng JDK đang chạy bằng `jfr metadata`. Nếu event không có trong recording, hãy kiểm tra cấu hình recording trước khi kết luận rằng không có native activity.

Mở file `.jfr` bằng JDK Mission Control để xem biểu đồ GC pause, heap usage, allocation và thread. So sánh các khoảng thời gian trước, trong và sau workload native để xác định tương quan. Dữ liệu JFR không thay thế GC log khi cần đọc nguyên nhân `Pinned`.

## 6. Tạo tải thử nghiệm có lời gọi native

Để quan sát, có thể tạo một chương trình Java gọi JNI native method trên một primitive array trong khi thread khác liên tục cấp phát object. Tải cấp phát làm GC diễn ra thường xuyên hơn; native worker tạo các critical region ngắn lặp lại.

Ví dụ Java `G1PinningLoad.java`:

```java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

public class G1PinningLoad {
    static {
        System.loadLibrary("g1pin");
    }

    private static native long checksum(int[] input);

    private static volatile long checksumSink;
    private static volatile int allocationSink;

    public static void main(String[] args) throws InterruptedException {
        int[] input = new int[1_000_000];
        Arrays.setAll(input, index -> index);

        Thread nativeWorker = Thread.ofPlatform().start(() -> {
            long total = 0;
            while (!Thread.currentThread().isInterrupted()) {
                total += checksum(input);
            }
            checksumSink = total;
        });

        Thread allocator = Thread.ofPlatform().start(() -> {
            int value = 0;
            while (!Thread.currentThread().isInterrupted()) {
                byte[] garbage = new byte[256 * 1024];
                garbage[0] = (byte) value++;
                allocationSink = garbage[0];
            }
        });

        TimeUnit.SECONDS.sleep(30);
        nativeWorker.interrupt();
        allocator.interrupt();
        nativeWorker.join();
        allocator.join();

        System.out.println("checksum=" + checksumSink);
        System.out.println("allocationSink=" + allocationSink);
    }
}
```

Native implementation `g1pin.c` dùng hàm checksum ở phần trước. Tạo JNI header và biên dịch Java:

```bash
mkdir -p out native
javac -h native -d out G1PinningLoad.java
```

Ví dụ biên dịch thư viện trên Linux với GCC/Clang và `JAVA_HOME` trỏ tới JDK 27:

```bash
cc -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o native/libg1pin.so native/g1pin.c
```

Trên macOS và Windows, thay thư mục header JNI (`darwin` hoặc `win32`), linker option và phần mở rộng thư viện theo toolchain của hệ điều hành. Tên thư viện vẫn là `g1pin` khi gọi `System.loadLibrary("g1pin")`.

Chạy chương trình với unified logging và JFR như hai ví dụ ở trên. Nếu muốn thử `-Xcheck:jni`, hãy thực hiện một lần chạy chẩn đoán riêng:

```bash
java -Xcheck:jni \
  -XX:+UseG1GC \
  -Djava.library.path=native \
  -cp out G1PinningLoad
```

`-Xcheck:jni` bổ sung kiểm tra cách sử dụng JNI và có thể cảnh báo nếu native code gọi JNI function khác trong critical region. Tùy chọn này làm tăng overhead; không dùng kết quả hiệu năng của lần chạy chẩn đoán làm số đo benchmark.

### Thiết kế phép so sánh

Thực hiện nhiều lần chạy với cùng heap size, cùng số thread, cùng thời gian và cùng mức cấp phát:

| Lần chạy | Workload | Mục tiêu |
| --- | --- | --- |
| A | Chỉ cấp phát Java, không gọi JNI | Đường cơ sở GC. |
| B | Cấp phát Java và gọi checksum native với critical region ngắn | Quan sát G1 khi có JNI critical calls bình thường. |
| C | Tăng kích thước dữ liệu native xử lý trong mỗi lần gọi, chỉ trong môi trường lab | Tăng xác suất GC gặp object đang pin để hiểu tín hiệu `Pinned`. |

Không cố ý block, sleep, thực hiện I/O hoặc gọi JNI function khác trong critical region để tạo tải. Nếu muốn kiểm tra thời gian giữ pin dài hơn, chỉ tăng lượng phép tính CPU trong ví dụ lab, chạy trong thời gian ngắn và luôn release con trỏ. Đây không phải mẫu code để triển khai production; JNI Specification khuyến nghị không giữ critical region lâu.

Không bảo đảm lần chạy C sẽ luôn in ra `Pinned`: điều đó phụ thuộc thời điểm GC, collection set và vị trí object được pin. Mục tiêu là đối chiếu cùng lúc workload, GC log và JFR, không phải tạo ra một dòng log cố định.

## 7. Đọc kết quả và chẩn đoán

Khi phân tích, nên xem cả thời gian pause lẫn áp lực bộ nhớ:

| Quan sát | Cách diễn giải |
| --- | --- |
| Có `Evacuation Failure: Pinned` | G1 gặp object bị pin trong vùng cần evacuation. Kiểm tra native workload và thời gian giữ critical pointer. |
| Có `Evacuation Failure: Allocation` | G1 thiếu vùng đích để di chuyển object; đây là vấn đề không gian đích, không đồng nghĩa với pinning. |
| Có `Allocation/Pinned` | Cả hai nguyên nhân cùng xảy ra trong collection đó. |
| Region tạm thời unavailable cho allocation | G1 chưa thể evacuate toàn bộ object khỏi region; xem các collection kế tiếp để biết region được thu hồi ra sao. |
| Pause tăng nhưng không có `Pinned` | Điều tra phase GC, allocation rate, heap occupancy, humongous allocation và các nguyên nhân khác. Không kết luận pinning chỉ từ pause dài. |
| JFR cho thấy pause tăng cùng lúc native worker hoạt động | Đây là tương quan thời gian; cần GC log và workload control để xác định nguyên nhân. |

G1 không phải real-time collector. Việc có region pinning không bảo đảm mọi pause nằm dưới mục tiêu hoặc không có Full GC. Nếu region thất bại không được thu hồi đủ nhanh, heap pressure vẫn có thể tăng. Đọc log qua nhiều chu kỳ GC thay vì chỉ một dòng riêng lẻ.

## 8. Checklist cho ứng dụng dùng JNI

- Giữ `GetPrimitiveArrayCritical` / `GetStringCritical` trong khoảng ngắn nhất có thể.
- Không gọi JNI function khác, không block và không làm I/O trong critical region.
- Kiểm tra con trỏ trả về; luôn gọi release tương ứng khi đã nhận được con trỏ hợp lệ.
- Chọn release mode đúng với việc native code chỉ đọc hay có sửa dữ liệu.
- Dùng `-Xlog:gc=info` để xác định `Pinned` và `Allocation`; bổ sung `gc+phases=debug` khi cần phân tích phase.
- Dùng JFR để đo pause, heap và tương quan thread/native workload; xác nhận pinning cụ thể bằng GC log.
- Chạy `-Xcheck:jni` trong kiểm thử native code, không dùng lần chạy này làm benchmark hiệu năng.
- So sánh baseline và tải native với cùng cấu hình heap và thời gian chạy.
- Không coi Region Pinning là API hoặc bảo đảm chung cho mọi JVM/collector.

G1 Region Pinning giúp HotSpot G1 tiếp tục thu gom heap khi native code đang giữ con trỏ tới một số object Java. Trên JDK 27, hành vi này là một phần của G1 mặc định và không cần bật preview hay incubator API. Khi điều tra hiệu năng, unified logging cho biết evacuation failure có nguyên nhân `Pinned`; JFR giúp đặt sự kiện đó vào bối cảnh pause, heap và hoạt động của ứng dụng. Quy tắc JNI critical region vẫn cần được tuân thủ nghiêm ngặt.

## Tài liệu tham khảo

- [JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423) — thay đổi implementation của HotSpot G1 trong JDK 22.
- [JEP 523: Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523) — thay đổi mặc định của G1 trong JDK 27.
- [JDK 27 Release Notes: Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — trạng thái các thay đổi trong JDK 27.
- [Garbage-First (G1) Garbage Collector, Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html) — evacuation failure, `Pinned`, region và chu kỳ GC.
- [Garbage-First Garbage Collector Tuning, Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html) — chẩn đoán và tuning G1 bằng logging.
- [JNI Functions, Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html) — `GetPrimitiveArrayCritical`, `GetStringCritical` và các giới hạn critical region.
- [The java Command, Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — Unified Logging, JFR startup options và `-Xcheck:jni`.
- [Diagnostic Tools, Java SE 27](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html) — JFR, JDK Mission Control và công cụ chẩn đoán.
