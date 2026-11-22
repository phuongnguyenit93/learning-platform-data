# Đo riêng khởi động, liên kết, làm nóng JIT và thực thi ổn định khi Java gọi mã native

## 1. Mục tiêu: tách đúng các chi phí của một lần tương tác native

Trong ứng dụng Java dùng **JNI (Java Native Interface)** hoặc **Foreign Function & Memory API (FFM)**, câu “gọi native mất bao lâu?” chưa xác định được đang đo điều gì. Một lần chạy mới có thể gồm JVM khởi động, tải class, nạp thư viện động, chuẩn bị symbol/đường gọi, thông dịch hoặc biên dịch JIT phần Java, rồi mới đến hàng triệu lần gọi đã ổn định. Gộp các giai đoạn đó thành một số trung bình có thể dẫn đến quyết định tối ưu sai.

Bài này tập trung vào **hiệu năng tương tác Java ↔ native**: biết đặt ranh giới đo riêng từng giai đoạn, đọc số liệu đúng ngữ cảnh và thiết kế kiểm thử có thể tái lập. Ví dụ chính dùng **Java 17+ và JNI/C**; phần so sánh với FFM được nêu riêng vì FFM trở thành API chuẩn từ JDK 22. Đối với JDK 24+, cần cấp quyền native access thích hợp khi chạy ví dụ.

Sau bài học, bạn có thể trả lời:

1. Ứng dụng chậm vì **khởi động JVM**, **load thư viện**, **lần gọi native đầu**, **JIT chưa nóng**, hay **chi phí gọi lặp ổn định**?
2. Đo “liên kết” như thế nào mà không nhầm lẫn nó với chi phí thực thi?
3. Khi nào dùng đồng hồ thời gian của hệ điều hành, `System.nanoTime()`, JFR, compiler log hoặc **JMH**?
4. Khi giảm số lần qua biên Java/native, cải thiện thực tế là bao nhiêu và có đáng đánh đổi không?

## 2. Bản đồ bốn giai đoạn cần phân biệt

| Giai đoạn | Điểm bắt đầu/kết thúc cần quan sát | Cách đo phù hợp | Điều **không** thể kết luận chỉ từ số đó |
| --- | --- | --- | --- |
| **A. Khởi động** (cold launch) | Hệ điều hành bắt đầu tiến trình `java` → JVM sẵn sàng/ứng dụng phát tín hiệu ready hoặc kết thúc một tác vụ cố định | Đồng hồ **bên ngoài tiến trình**, chạy nhiều JVM mới; startup timestamp của ứng dụng nếu có | `nanoTime()` trong `main` không bao phủ toàn bộ startup JVM; số wall time chứa nhiều hoạt động khác |
| **B. Nạp và liên kết native** | Gọi `System.load/ loadLibrary` → trả về; **riêng** lần đầu gọi phương thức `native` → trả về | Hai đồng hồ riêng bằng `nanoTime()`; log/JFR để xác nhận sự kiện | Thời gian “first call” **không phải** chi phí liên kết thuần; còn có chạy hàm, adapter, class/JIT/OS |
| **C. Làm nóng JIT** (warm-up) | Lặp workload đại diện trước khi công bố số steady state | Nhiều batch, ghi `ns/op` theo thứ tự; xem `-XX:+PrintCompilation`/JFR | Một batch nhanh không đủ chứng minh đã ổn định; JIT có thể biên dịch tiếp hoặc deoptimize |
| **D. Thực thi ổn định** (steady state) | Sau warm-up đã chọn, đo nhiều batch/từng fork với cùng workload | JMH cho microbenchmark; median, phân tán và khoảng tin cậy; throughput/latency thật khi cần | Số của phép cộng native rất nhỏ **không** đại diện cho copy mảng, callbacks hay tác vụ native lớn |

Hình dung tiến trình thông thường:

~~~text
OS tạo process
    ↓
JVM/bootstrap + class loading + initialization
    ↓
System.load / loadLibrary (+ OS dynamic loader, JNI_OnLoad nếu có)
    ↓
Lần đầu gọi native method (có thể bind symbol lazily)
    ↓
Nhiều lời gọi lúc JIT/interpreter và CPU caches còn thay đổi
    ↓
Nhiều lời gọi ở trạng thái đã làm nóng, lấy số liệu ổn định
~~~

Đây là **sơ đồ logic**, không phải cam kết mọi JVM/thư viện tuân theo một thứ tự tuyệt đối. Ví dụ, một static initializer có thể load thư viện ngay khi class được dùng; thư viện có thể đăng ký native methods sớm bằng `RegisterNatives`; JIT được khởi chạy và biên dịch bất đồng bộ trong nhiều đoạn thời gian.

### Vì sao “liên kết” cần được giải nghĩa?

- **OS loader:** khi `System.load(...)` thành công, hệ điều hành/JVM đã xử lý việc nạp library, relocation cần thiết và có thể chạy hàm khởi tạo. Nếu có `JNI_OnLoad`, JVM gọi nó trong quá trình load.
- **JNI native-method binding:** với liên kết theo tên JNI thông thường, JVM gắn lời gọi khai báo `native` vào hàm C tương ứng khi phương thức đó được gọi lần đầu. Các thư viện dùng `RegisterNatives` có thể thực hiện việc đăng ký chủ động, làm thay đổi ranh giới trên.
- **JIT compilation:** trình biên dịch HotSpot tối ưu **mã Java** và đường gọi/adapter khi đủ nóng. Nó không “JIT biên dịch lại” hàm C đã được biên dịch bằng `cc/gcc/clang/MSVC`.

Vì vậy, `T_first_call` là **phép đo đại diện cho đường đi lần đầu (first-use latency)**, bao gồm binding **nếu** binding diễn ra ở lần đó; không thể lấy nó trừ `T_steady_call` để tuyên bố phần chênh là “thời gian liên kết JNI chính xác”. Trừ hai phép đo khác điều kiện còn dễ cộng thêm biến động scheduler, cache và JIT.

## 3. Lập kế hoạch phép đo trước khi viết benchmark

Ghi rõ workload thực tế và ranh giới nghiệp vụ: tiến trình CLI chạy một lần, server sống lâu, batch xử lý hàng triệu phần tử, hay request đầu tiên sử dụng thư viện native. Với server, phân biệt **time to process ready** và **first native request latency**; nếu lazy load đến request đầu, startup nhìn nhanh hơn nhưng request đầu bị cộng thêm chi phí.

Chọn metric thích hợp:

- **Startup:** thời gian wall-clock của toàn tiến trình và/hoặc từ lúc process bắt đầu đến tín hiệu ready; báo median/p95 qua các lần chạy tiến trình **mới**. Chú thích “cold JVM” khác “cold OS page cache” vì khởi chạy JVM mới không xóa page cache.
- **Load:** elapsed time bao quanh riêng lệnh nạp thư viện, báo mili giây; cố gắng chuẩn bị chuỗi đường dẫn/đọc cấu hình bên ngoài khoảng đo nếu chỉ muốn thời gian loader.
- **First call:** elapsed time của **một lời gọi đầu** sau load, báo micro giây hoặc nano giây, nhưng trình bày như proxy và chạy nhiều fork riêng biệt.
- **Warm-up:** ghi thời gian từng batch theo thứ tự (ví dụ mỗi batch 100.000 calls), không gộp vào mẫu steady; ghi số vòng, khối lượng và cờ JVM.
- **Steady state:** thời gian hoặc throughput sau warm-up, thường `ns/op`/`ops/s`. Nếu cần latency dịch vụ thật, lấy p50/p95/p99 ở tầng request và tải tương đương production; microbenchmark chỉ trả lời phạm vi hẹp.

**Nguyên tắc đồng hồ:** lấy hiệu `end - start` từ `System.nanoTime()` bên trong một JVM cho các đoạn ngắn. Không dùng `System.currentTimeMillis()` để chia thời gian nanosecond, cũng không lấy `nanoTime()` của hai tiến trình khác nhau để trừ. Gọi đồng hồ hai lần quanh **một** native call quá nhỏ sẽ bị overhead đo lấn át; do đó phần steady phải đo một **batch** gồm rất nhiều lời gọi và chia cho số lời gọi, còn phần first-call chấp nhận nhiễu của phép đo một lần.

Để thí nghiệm công bằng, cố định JDK vendor/version, OS, kiến trúc CPU, tham số JVM, compiler flags của thư viện native, dữ liệu đầu vào, thread count, mức tải và điều kiện máy. Không so số ở hai máy hoặc hai JDK khác nhau rồi kết luận nguyên nhân là JNI khi có nhiều biến chưa kiểm soát.

## 4. Bài thực hành JNI đầy đủ: một native method, bốn chế độ

Ví dụ dùng hàm native rất nhỏ `next(x) = x + 1` nhằm làm rõ overhead của biên Java/native. Đây là **bài học về phép đo**, không phải ứng dụng tính toán cần tăng tốc bằng C. Mã Java hợp lệ từ **JDK 17 trở lên**, thư viện C biên dịch riêng cho từng hệ điều hành.

### 4.1. Tạo `JniPhases.java`

~~~java
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Locale;

public final class JniPhases {
    private static final int CALLS = 100_000;
    private static final int WARM_BATCHES = 12;
    private static final int STEADY_BATCHES = 10;
    private static volatile long observed;

    public static native long next(long value);

    private static long runBatch() {
        long sum = 0;
        for (int i = 0; i < CALLS; i++) {
            sum += next(i);
        }
        observed = sum; // Giữ kết quả nhìn thấy được bên ngoài vòng lặp.
        return sum;
    }

    private static double median(double[] source) {
        double[] copy = source.clone();
        Arrays.sort(copy);
        int mid = copy.length / 2;
        return (copy.length % 2 == 0)
                ? (copy[mid - 1] + copy[mid]) / 2.0
                : copy[mid];
    }

    public static void main(String[] args) {
        String mode = args.length == 0 ? "all" : args[0];

        if ("baseline".equals(mode)) {
            System.out.println("baseline_ready");
            return;
        }
        if (!"load".equals(mode) &&
                !"first".equals(mode) &&
                !"all".equals(mode)) {
            throw new IllegalArgumentException(
                    "Use: baseline | load | first | all");
        }

        String lib = Path.of(System.mapLibraryName("jniphases"))
                .toAbsolutePath().toString();

        long start = System.nanoTime();
        System.load(lib);
        long loadNs = System.nanoTime() - start;

        if ("load".equals(mode)) {
            System.out.printf(Locale.ROOT,
                    "load_ms=%.3f%n", loadNs / 1_000_000.0);
            return;
        }

        start = System.nanoTime();
        long firstResult = next(3);
        long firstNs = System.nanoTime() - start;

        if (firstResult != 4L) {
            throw new AssertionError("Unexpected JNI result");
        }
        System.out.println("jni_result=" + firstResult);
        System.out.printf(Locale.ROOT,
                "load_ms=%.3f%n", loadNs / 1_000_000.0);
        System.out.printf(Locale.ROOT,
                "first_call_us=%.3f%n", firstNs / 1_000.0);

        if ("first".equals(mode)) {
            return;
        }

        double[] warm = new double[WARM_BATCHES];
        for (int i = 0; i < WARM_BATCHES; i++) {
            start = System.nanoTime();
            runBatch();
            warm[i] = (System.nanoTime() - start) / (double) CALLS;
        }

        double[] steady = new double[STEADY_BATCHES];
        long checksum = 0;
        for (int i = 0; i < STEADY_BATCHES; i++) {
            start = System.nanoTime();
            checksum = runBatch();
            steady[i] = (System.nanoTime() - start) / (double) CALLS;
        }

        if (checksum != 5_000_050_000L ||
                observed != 5_000_050_000L) {
            throw new AssertionError("Incorrect checksum");
        }

        System.out.println("batch_checksum=" + checksum);
        System.out.printf(Locale.ROOT,
                "warmup_ns_per_call_first=%.2f last=%.2f%n",
                warm[0], warm[warm.length - 1]);
        System.out.printf(Locale.ROOT,
                "steady_ns_per_call_median=%.2f%n", median(steady));
    }
}
~~~

Điểm thiết kế của chương trình:

- Chế độ `baseline` không load JNI và kết thúc nhanh, dùng để quan sát thành phần startup cơ bản. Nó **không** cô lập tuyệt đối chi phí JVM vì vẫn có class loading, `println`, class initialization và shutdown.
- Chế độ `load` gọi `System.load` đúng một lần trong JVM mới rồi báo `load_ms`. Đường dẫn được chuẩn bị **trước** đồng hồ; biến số vẫn gồm overhead gọi `System.load` và loader hệ điều hành.
- Chế độ `first` thêm phép đo một lời gọi JNI đầu tiên sau load; sau đó **dừng**, không trộn vào các lần đo steady.
- Chế độ `all` tiếp tục thực thi 12 batch làm nóng và 10 batch đo. Mỗi batch có 100.000 lời gọi; `observed` là biến `volatile` giữ checksum để giảm nguy cơ benchmark bị tối ưu bỏ.
- Không in ra console **bên trong** vòng lặp. Các con số thời gian được giữ lại, rồi mới in ở cuối giai đoạn, tránh để chi phí I/O lấn át hàm native.
- `System.nanoTime()` đo thời gian trong một JVM; output `ns_per_call` là **chi phí trung bình cả vòng lặp + JNI + hàm C** chia cho số lần gọi, không phải “chi phí crossing thuần”.

### 4.2. Tạo `jni_phases.c`

~~~c
#include "JniPhases.h"

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT jlong JNICALL Java_JniPhases_next(
        JNIEnv *env, jclass declaringClass, jlong value) {
    (void)env;
    (void)declaringClass;
    return value + 1;
}
~~~

`javac -h` sẽ tạo header `JniPhases.h` với chữ ký JNI đúng cho `next(long)`. Tên hàm C `Java_JniPhases_next` khớp class Java ở **default package** và tên phương thức. Nếu thêm package/đổi tên, cần tạo lại header và sửa C theo tên được sinh; không copy symbol cũ. Hàm `JNI_OnLoad` trả phiên bản JNI hỗ trợ; nó chạy trong quá trình nạp library, vì vậy chi phí của nó thuộc **load phase**, không được gán nhầm cho first-call binding.

### 4.3. Biên dịch

Yêu cầu JDK 17+ (có `javac` và header `jni.h`), trình biên dịch C, và biến môi trường `JAVA_HOME` trỏ tới **cùng JDK** được dùng biên dịch/chạy. Đặt hai file trong một thư mục làm việc; các lệnh dưới chạy ngay trong thư mục đó.

**Linux** (GCC hoặc Clang; ví dụ dùng `cc`):

~~~bash
javac -h . JniPhases.java
cc -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjniphases.so jni_phases.c
~~~

**macOS**:

~~~bash
javac -h . JniPhases.java
cc -O2 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -o libjniphases.dylib jni_phases.c
~~~

**Windows**, chạy trong x64 Native Tools Command Prompt for Visual Studio (đã có `cl` và `JAVA_HOME`):

~~~bat
javac -h . JniPhases.java
cl /LD /O2 /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jni_phases.c /Fe:jniphases.dll
~~~

Java chọn tên library bằng `System.mapLibraryName("jniphases")`: `libjniphases.so`, `libjniphases.dylib` hoặc `jniphases.dll` tùy OS. Nó được load bằng **đường dẫn tuyệt đối** tới thư mục làm việc, nên không cần thêm `-Djava.library.path`. Nếu chạy từ thư mục khác, phải đặt lại đường dẫn/thư mục cho khớp. Kiến trúc binary phải trùng kiến trúc JVM (x64/ARM64).

### 4.4. Chạy theo từng pha và đối chiếu output

Với **JDK 17–23**:

~~~bash
java -cp . JniPhases baseline
java -cp . JniPhases load
java -cp . JniPhases first
java -cp . JniPhases all
~~~

Với **JDK 24+**, JNI load/binding nằm trong cơ chế native access restrictions. Khi benchmark, cấp quyền cho code trên class path để tránh cảnh báo hoặc lỗi cấp quyền làm nhiễu kết quả:

~~~bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases baseline
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases load
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases first
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases all
~~~

Các dòng output **chính xác, không phụ thuộc máy** của chương trình là:

~~~text
baseline_ready
~~~

cho riêng chế độ `baseline`; với `first` và `all`, luôn có:

~~~text
jni_result=4
~~~

Với `all`, còn có:

~~~text
batch_checksum=5000050000
~~~

Các số sau `load_ms=`, `first_call_us=`, `warmup_ns_per_call_first=... last=...` và `steady_ns_per_call_median=` **thay đổi theo máy và từng lần chạy**, nên không có stdout số cố định hợp lệ để sao chép. Lý do checksum cố định: trong mỗi batch, hàm C trả `1, 2, ..., 100000`, tổng là `100000 × 100001 / 2 = 5000050000`.

Nếu báo `UnsatisfiedLinkError`, kiểm tra tên file native, thư mục chạy, architecture, các thư viện phụ thuộc và chữ ký hàm được sinh. Nếu báo `IllegalCallerException` trên JDK 24+, kiểm tra cờ native access và module/class path; đây là vấn đề quyền, không phải kết luận về hiệu năng.

## 5. Đo startup thật từ **ngoài** JVM

Nếu chỉ bắt đầu `System.nanoTime()` trong `main`, một phần lớn thời gian JVM bootstrap, chuẩn bị VM, đọc class và khởi tạo ban đầu đã trôi qua. Dùng đồng hồ của tiến trình gọi JVM để đo **wall-clock inclusive**.

Ví dụ trên **Linux có GNU time**:

~~~bash
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases baseline
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases load
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases first
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases all
~~~

Trên JDK 24+, thêm hai cờ native access vào **từng lệnh** như mục 4.4. `/usr/bin/time` đo từ khi tạo process cho đến lúc process kết thúc, bao gồm thời gian shutdown và I/O; đó là số **end-to-end của chế độ** đang chạy, không phải riêng “JVM bootstrap time”. Nếu cần chỉ “đến sẵn sàng nhận request”, dùng mốc ready ở ứng dụng hoặc hệ thống quan sát startup có thể tái lập.

Ví dụ trên **Windows PowerShell**:

~~~powershell
Measure-Command { java -cp . JniPhases baseline }
Measure-Command { java -cp . JniPhases load }
~~~

Lệnh PowerShell còn chịu overhead của thao tác đo/shell, nên phù hợp quan sát sơ bộ. Cùng một kiểu đo và launcher cho mọi mẫu; chạy lặp lại **nhiều process mới**, ghi median/p95 và thứ tự chạy. Cân nhắc đổi thứ tự để giảm ảnh hưởng page cache nóng, và ghi trạng thái máy/CPU governor, không coi lần JVM mới thứ hai là cold disk run. Trên macOS, cú pháp `time` khác GNU `/usr/bin/time -f`; dùng `time java ...` hoặc công cụ time của hệ điều hành.

**Không trừ máy móc** “wall all – wall baseline” để suy ra chính xác thời gian native; hai run độc lập có nhiễu, và `all` còn thêm cả warm-up, đo steady, output và nhiều bước khác. Các đồng hồ `load_ns` và `first_call_ns` cung cấp dấu mốc nội bộ bổ sung, không khiến phép trừ trở thành kết quả chuyên biệt.

## 6. Đọc đúng số liệu load, first call, warm-up và steady

### 6.1. Load native library

Chạy `load` trên nhiều JVM mới, giữ nguyên file `.so/.dylib/.dll`. Khoảng `System.load` có thể bao gồm OS dynamic loader, relocation, initializer native, `JNI_OnLoad` và logic quản lý native library của JVM. Nếu lần đầu load chậm khác thường, thử đối chiếu JVM tiến trình mới và trạng thái cache của hệ điều hành. Không gọi `System.load` liên tục trong một JVM rồi coi đó là 20 lần “cold load”: thư viện có thể đã được quản lý như loaded và việc gọi lại không tái hiện nạp ban đầu.

Để xác nhận thư viện nào thực sự được nạp, dùng **JFR events** `jdk.NativeLibraryLoad` / `jdk.NativeLibraryUnload` khi được bật. Các event xác nhận load/unload; chúng không trực tiếp cho biết riêng thời gian resolve từng native method. Việc ghi JFR có overhead, nên thực hiện phiên chẩn đoán riêng với phiên lấy số benchmark cuối.

### 6.2. First JNI call/binding

Chế độ `first` gọi `next(3)` đúng một lần sau khi `System.load` đã hoàn tất. Với cơ chế JNI thông thường, JVM tìm symbol khi lần đầu gọi phương thức `native`; thời gian `first_call_us` bao gồm cả phần gọi C trả `4`. Nó còn có thể chứa hoạt động thiết lập JNI adapter hoặc CPU/cache. Khi JDK 24+ chưa cấp quyền, thông báo native access có thể được in vào stderr hoặc thao tác bị chặn tùy chế độ; **cấp quyền cố định trước khi đo**, không dùng cảnh báo làm mốc đo độ trễ.

Nếu thư viện sử dụng `RegisterNatives` trong `JNI_OnLoad`, bước đăng ký có thể đã xảy ra trong **load phase**. Nếu OS loader trì hoãn resolve một số symbol/relocation, một phần công việc cũng có thể xảy ra sau `System.load`. Do đó số first-call là “cold first use” theo triển khai cụ thể, không phải định nghĩa phổ quát của thời gian native linker.

### 6.3. Warm-up JIT

12 batch đầu trong `all` được chạy **trước** 10 batch tính median steady. Đầu tiên, HotSpot có thể thông dịch mã Java; sau đủ hotness có thể biên dịch Java caller/loop và tạo/tối ưu đường gọi. Nhiều yếu tố khác như cache CPU và branch predictors cũng thay đổi trong giai đoạn đầu. Thời gian warm-up từng batch **không nhất thiết giảm đều** vì biên dịch bất đồng bộ, OS scheduling, GC hoặc deoptimization.

Tham khảo output của HotSpot compiler (chạy **riêng phiên chẩn đoán**, không sử dụng con số thời gian của run có thêm logging làm benchmark cuối):

~~~bash
java -XX:+PrintCompilation -cp . JniPhases all
~~~

Trên JDK 24+, thêm `--enable-native-access=ALL-UNNAMED --illegal-native-access=deny`. Flag `-XX:+PrintCompilation` cho biết phương thức nào được JIT compile; nếu không thấy một dòng cho `next` thì điều đó **không** nghĩa là native call không chạy, bởi hàm C không phải bytecode được JIT. Có thể dùng `java -Xint ...` làm phép thử chẩn đoán khi tắt JIT, nhưng `-Xint` thay đổi chế độ thực thi, nên không được so như kết quả steady của chế độ JIT mặc định.

Một chương trình server không nhất thiết có một thời điểm “warm-up hoàn thành” duy nhất; các nhánh ít dùng hoặc class mới xuất hiện sau đó vẫn có thể làm nóng muộn. Ghi rõ đã warm code path nào, số lượng invocation và dấu hiệu compilation ổn định; nếu có biến động, tăng warm-up/điều tra thay vì tùy chọn bỏ outlier theo cảm tính.

### 6.4. Steady state

Mã đo batch của bài trả `ns_per_call_median`, tính bằng median của 10 số `elapsed_ns / 100000`. Đây là cách quan sát dễ hiểu, nhưng **không phải** một microbenchmark có độ tin cậy tương đương JMH: nó đo ít fork, warm-up cố định chưa chắc đủ, timer/safepoint tác động, và không đưa confidence interval.

Đối với kết luận hiệu năng JNI/FFM dùng để chọn thiết kế, hãy dùng **OpenJDK Java Microbenchmark Harness (JMH)**. Chuẩn bị thư viện native **ngoài đoạn đo** (ví dụ trong `@Setup(Level.Trial)`), chạy fork JVM mới độc lập (ví dụ `@Fork(3)`), các vòng làm nóng `@Warmup(...)` và đo `@Measurement(...)`, trả kết quả từ `@Benchmark` hoặc đưa vào `Blackhole` để không mất tác dụng quan sát. Với native access trên JDK 24+, đảm bảo cờ JVM đi tới **các process fork** của JMH, không chỉ process điều phối.

Một cấu hình minh họa cho đoạn benchmark steady là:

~~~java
// Trích đoạn cấu hình JMH, KHÔNG phải chương trình Java độc lập;
// cần dự án JMH và dependency/annotation processor của JMH.
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
~~~

JMH **steady benchmark** không thay thế benchmark **cold startup/first-call**: default warm-up làm biến mất phần chi phí ban đầu mà ta đang muốn định lượng. Nếu mục tiêu là startup/first-use, thiết kế thí nghiệm khởi tạo một **process/fork mới cho mỗi mẫu**, hoặc dùng chế độ đo một lần thích hợp và diễn giải kết quả là thời gian startup/first-use inclusive. Không vô tình dùng kết quả steady để tuyên bố first call nhanh.

## 7. So sánh JNI, FFM và chi phí crossing

Bài ví dụ sử dụng JNI để dễ thấy ranh giới. Với **FFM (JDK 22+)**, cần tách các giai đoạn tương đương nhưng không nhất thiết trùng cách đặt tên:

| Mốc JNI | Hoạt động gần tương ứng trong FFM | Điểm cần đo |
| --- | --- | --- |
| `System.load(...)` | Nạp thư viện qua `SymbolLookup.libraryLookup(...)` hoặc cơ chế nạp thư viện liên quan | Load thư viện, vòng đời arena/lookup và hệ điều hành |
| Bind phương thức `native` lần đầu | Tìm symbol bằng `SymbolLookup.find(...)`; tạo downcall handle qua `Linker.downcallHandle(...)` | Phân biệt **lookup**, **tạo method handle** và **lời gọi đầu** |
| JNI Java→C call | `MethodHandle.invokeExact(...)` của downcall đã tạo | Đo gọi lặp; chi phí marshalling, layout, memory scope và ABI |
| Truyền chuỗi/mảng qua JNI | Truyền `MemorySegment` hoặc buffer native | Đo copy/allocate/pin, scope và quản lý bộ nhớ, không chỉ “call overhead” |

**Không tạo `downcallHandle` lại ở mỗi lần benchmark steady** trừ khi mục tiêu là chi phí tạo handle; giữ `Linker`/lookup/handle được thiết lập trước khi bấm đồng hồ để đo riêng các lời gọi. Nếu công việc thật luôn phải cấp phát arena/copy dữ liệu ở mỗi request, phải làm **thêm** một benchmark end-to-end bao gồm chi phí ấy. Khi so JNI và FFM, bảo đảm gọi **cùng hàm C**, cùng dữ liệu, điều kiện lỗi, ABI/layout và vòng đời buffer trước khi nói bên nào nhanh hơn. Chi phí chuyển qua biên có thể nhỏ hơn rất nhiều so với thuật toán native hoặc copy dữ liệu thực.

Một mô hình định tính hữu ích:

`T_workload ≈ N_calls × T_boundary + T_native_work + T_marshal_or_copy + T_other`

Nó chỉ là **mô hình hướng phân tích**. Các thành phần tương tác qua cache, JIT và contention nên không bảo đảm cộng tuyến tính. Với API thực hiện thao tác cực nhỏ (như `next(long)`), overhead per call có thể nổi bật; dùng một API native xử lý cả batch đôi khi giảm `N_calls`. Với thao tác native dài (ví dụ xử lý ảnh), cải thiện vài nanosecond crossing khó quan trọng bằng native algorithm, bộ nhớ và I/O. Bất kỳ thay đổi “gộp batch” nào cũng cần đo lại end-to-end để kiểm tra chi phí copy/chuyển dữ liệu phát sinh.

## 8. Thiết kế báo cáo có thể so sánh được

Một báo cáo thí nghiệm nên chia thành các bảng **khác mục tiêu**:

| Mẫu báo cáo | Đơn vị | Số lần chạy hợp lý | Ghi chú bắt buộc |
| --- | --- | --- | --- |
| Fresh JVM `baseline`, `load`, `first` | ms wall/process | Nhiều JVM mới, nêu N thực tế | Cùng Java/OS/launcher, thứ tự chạy, cold/warm page cache |
| `System.load` trong một JVM mới | ms/load | Nhiều JVM mới | Library, JNI_OnLoad, binary dependencies, source JDK |
| Lần đầu `next(3)` sau load | µs/first call | Nhiều JVM mới | Đây là first-use proxy, không phải pure binding |
| Warm-up batches | ns/call theo từng batch | Nhiều batch/fork | Trật tự batch, compilation log khi điều tra |
| JMH steady calls | ns/op + sai số hoặc ops/s | Nhiều fork, warm-up, measurement | Có/không tính allocation/copy; cờ JVM của fork |
| E2E request latency | p50/p95/p99, throughput | Tải gần production | Nhận diện lazy native load, burst, GC, contention |

Khi đưa ra một kết luận, viết theo dạng: “Trên JDK X, OS Y, thư viện native biên dịch bằng Z, workload W, median của N fork ...; sự khác biệt nằm ở giai đoạn ...”. Tránh ghi “JNI nhanh hơn FFM 2×” chỉ từ một phép cộng giả lập hoặc một lần chạy có đầy log.

Ví dụ diễn giải **giả định, không phải kết quả đo thật**: Nếu CLI chạy đúng một tác vụ rồi thoát, startup 200 ms, load 15 ms, còn phần xử lý steady 1 ms, thì giảm steady từ 1 ms xuống 0,5 ms ít tác động tới tổng thời gian. Nếu server sống nhiều giờ và gọi qua biên hàng trăm triệu lần, tối ưu số lần crossing hoặc kích thước dữ liệu mỗi call có thể đáng giá hơn. Chính **khối lượng sử dụng** quyết định giai đoạn nào cần tối ưu.

### Sự kiện quan sát hỗ trợ, không thay thế benchmark

- **JFR:** `jdk.NativeLibraryLoad`/`jdk.NativeLibraryUnload` (khi được bật) để kiểm tra load/unload, các event compilation/GC/safepoint để giải thích biến động nếu được cấu hình thu thập.
- **HotSpot `-XX:+PrintCompilation`:** quan sát thời điểm Java code được compile; dùng bên ngoài phiên đo cuối để giảm log overhead.
- **JVM class loading:** `-Xlog:class+load=info` giúp tìm nhánh tải class muộn; log rất nhiều nên chỉ bật khi điều tra.
- **Profiler hệ điều hành:** CPU sampling, native stack traces, loader trace (nếu được hỗ trợ) để phân biệt chậm ở Java, JNI stub, libc/OS loader hoặc hàm C; công cụ đo cũng có overhead.
- **JMH:** tách forks, warm-up, measurement và báo độ dao động cho benchmark ngắn; với request latency thực, vẫn cần load test/profile ứng dụng.

## 9. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao làm kết quả sai | Cách sửa |
| --- | --- | --- |
| Lấy thời gian của một lệnh `java Main` làm “JNI call latency” | Bao gồm JVM startup, I/O, loader, JIT, shutdown | Tách fresh-process benchmark và in-process phase timer |
| Đo từ đầu `main` rồi gọi đó là “JVM startup” | JVM đã khởi tạo trước khi `main` chạy | Dùng đồng hồ ngoài process và/hoặc mốc ready rõ ràng |
| Kết luận “first call – steady = binding time” | First call chứa nhiều chi phí khác, hai mẫu khác điều kiện | Gọi first-call là proxy, tìm bằng chứng loader/symbol nếu cần |
| Gộp warm-up và steady rồi lấy một trung bình | JIT/tiering và cache thay đổi theo thời gian | Lưu từng batch, xác định cửa sổ steady, dùng JMH |
| Gọi hàm vài nanosecond và bấm `nanoTime()` từng call | Overhead đồng hồ, scheduling lớn so với payload | Đo batch dài, chia số operations; tốt hơn dùng JMH |
| Bỏ kết quả tính toán | Compiler có thể loại phép tính hoặc hoist các phần không quan sát được | Dùng result/volatile sink hoặc JMH `Blackhole` |
| Đo `System.load` nhiều lần trong một JVM rồi gọi cold load | Library đã được nạp, dynamic loader/cache thay đổi | Một lần initial load trên mỗi JVM/fork mới |
| So JNI/FFM khi một bên copy mảng, bên kia dùng native segment | Workload/semantics khác nhau | Cùng dữ liệu, ABI, hàm C; báo riêng marshalling |
| Bật `PrintCompilation`, profiling nặng ngay lúc đo steady | I/O và instrumentation làm lệch timing | Một run chẩn đoán, một run benchmark tinh gọn |
| Quên native access trên JDK 24+ | Warning hoặc `IllegalCallerException` làm sai/không chạy benchmark | Cấu hình `--enable-native-access` đúng module ở **mọi fork** |
| Không cố định CPU, compiler flags, JDK và nhiệt độ máy | DVFS, máy nền, GC làm kết quả không tái lập | Ghi môi trường, lặp nhiều mẫu, dùng so sánh phân phối |

## 10. Checklist đánh giá trước khi tối ưu

- [ ] Có định nghĩa rõ “ready”, “native library loaded”, “first-use” và “steady” cho ứng dụng đang xét.
- [ ] Đã đo startup từ ngoài JVM bằng nhiều tiến trình mới; phân biệt JVM cold với OS page-cache cold.
- [ ] Đã đặt đồng hồ riêng quanh `System.load` và lần đầu gọi `native`; không gọi first-call proxy là thời gian binding chính xác.
- [ ] Đã kiểm tra code path native được thực thi thật và xử lý đúng quyền `--enable-native-access` trên JDK 24+.
- [ ] Đã ghi warm-up batches, xem tác động JIT/tiering và tách hoàn toàn chúng khỏi các mẫu steady.
- [ ] Đã benchmark steady bằng JMH hoặc quy trình tương đương có nhiều fork, warm-up, measurement, có kết quả observable.
- [ ] Đã bao phủ copy/allocate/marshalling thực tế, số lần crossing, GC, safepoint và end-to-end latency nếu mục tiêu là production.
- [ ] Đã ghi phiên bản JDK/OS/CPU/compiler/native binary, flags JVM và mức tải; đã so phân phối qua nhiều lần thay vì một con số.
- [ ] Đã diễn giải kết quả theo thời gian sống và tần suất dùng JNI/FFM của hệ thống, rồi đo lại sau tối ưu.

## Tài liệu tham khảo

- OpenJDK JEP 472 — native loading/linking restrictions từ JDK 24: https://openjdk.org/jeps/472
- Oracle JNI Specification — Design Overview, *Resolving Native Method Names*: https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html
- Oracle JDK Migration Guide — native access, `jnativescan` và JFR library events: https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html
- Oracle JDK Java launcher — HotSpot `-XX:+PrintCompilation`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- Oracle FFM `Linker` API (JDK 25) và downcall handles: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html
- OpenJDK Java Microbenchmark Harness (JMH): https://github.com/openjdk/jmh

**Thông điệp cốt lõi:** Muốn tối ưu tương tác Java/native, trước tiên phải định lượng **khởi động**, **nạp/liên kết**, **JIT warm-up** và **steady state** bằng các phép đo có ranh giới, đơn vị và điều kiện chạy riêng. Chỉ số ở một giai đoạn không thể đại diện cho cả vòng đời ứng dụng.