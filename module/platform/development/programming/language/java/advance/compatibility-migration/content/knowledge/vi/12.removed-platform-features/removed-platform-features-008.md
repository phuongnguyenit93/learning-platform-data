# javah, công cụ giám sát cũ và cách thay bằng công cụ còn hỗ trợ

Khi nâng cấp một ứng dụng Java đã tồn tại nhiều năm, lỗi migration không chỉ đến từ source code hay thư viện. Build script có thể vẫn gọi lệnh javah để tạo JNI header; đội vận hành có thể dựa vào jhat, jvisualvm đi kèm một bộ JDK cũ, các cờ GC logging trước JDK 9 hoặc một script chẩn đoán chỉ chạy với công cụ của một nhà cung cấp JVM cụ thể. Đến JDK mới, những executable, option hoặc cơ chế đóng gói đó có thể đã bị loại bỏ, được tách thành sản phẩm độc lập hoặc thay đổi cách dùng.

**Mục tiêu của bài học** là nhận diện công cụ Java cũ, xác định tình trạng hỗ trợ trên JDK đích và thay bằng cơ chế còn được duy trì. Hai nhóm việc chính là thay javah trong quy trình biên dịch JNI và thay cách giám sát/chẩn đoán cũ bằng jcmd, Java Flight Recorder (JFR), JDK Mission Control (JMC), VisualVM, Eclipse Memory Analyzer (MAT), JMX cùng hệ thống observability của ứng dụng.

Điều cần bảo toàn là **khả năng tạo đúng artifact, thu thập được thông tin vận hành quan trọng và kiểm chứng kết quả trên JDK mục tiêu**. Không nên xem tất cả công cụ quen thuộc với JDK 8 là đã bị loại bỏ: một số vẫn được hỗ trợ trong JDK mới hoặc chỉ thay đổi cách đóng gói.

## 1. Phân loại công cụ trước khi migration

Một executable biến mất khỏi thư mục bin không nhất thiết có nghĩa chức năng tương ứng đã mất. Có ít nhất bốn tình huống:

| Tình huống | Đặc điểm | Cách xử lý migration |
|---|---|---|
| Công cụ bị loại bỏ | Không còn trong JDK đích | Dùng API, compiler option hoặc công cụ thay thế |
| Công cụ tách khỏi JDK | Vẫn dùng được nhưng là sản phẩm độc lập | Cài riêng, pin phiên bản và kiểm soát vòng đời |
| Công cụ đổi cú pháp hoặc output | Lệnh vẫn tồn tại, cờ/định dạng thay đổi | Cập nhật script và parser, kiểm tra runtime |
| Công cụ vẫn được hỗ trợ | Nhiều JDK mới vẫn có | Có thể tiếp tục dùng trong phạm vi được hỗ trợ |

Ví dụ tiêu biểu:

- **javah** bị loại bỏ kể từ **JDK 10**. Thay bằng tùy chọn **javac -h**, có từ JDK 8.
- **jhat** (Java Heap Analysis Tool) đã bị loại bỏ từ **JDK 9**. Có thể dùng Eclipse MAT hoặc VisualVM để phân tích heap dump.
- **jvisualvm** không còn được đóng gói sẵn trong nhiều JDK hiện đại. **VisualVM** vẫn được phát hành và cài đặt độc lập.
- **JDK Mission Control** là công cụ phân tích JFR có thể được cài riêng; việc có sẵn lệnh jmc phụ thuộc distribution và cách đóng gói.
- **jcmd, jstack, jmap, jstat, jinfo, jconsole** vẫn có thể tồn tại trong các JDK mới. Không nên xếp tất cả vào nhóm “đã bị xóa”.
- Những cờ **GC logging trước JDK 9** cần được đối chiếu với unified logging dùng cú pháp **-Xlog**; không sao chép nguyên cấu hình cũ mà không kiểm chứng.

Tập công cụ thực tế phụ thuộc phiên bản, vendor, hệ điều hành, quyền truy cập và runtime image. Một image tối giản tạo bằng jlink hoặc một container chỉ chứa runtime có thể không có công cụ chẩn đoán mà bản JDK đầy đủ cùng phiên bản cung cấp.

## 2. Tìm nơi hệ thống đang phụ thuộc vào công cụ cũ

Trước khi sửa, phải biết ai gọi công cụ và output được ai sử dụng:

| Nguồn | Cần tìm | Ví dụ |
|---|---|---|
| Build script | Task tạo JNI header hoặc gọi executable | Gradle Exec, Maven plugin, shell gọi javah |
| CI/CD | JDK/tool path và bước chẩn đoán | Jenkins, GitHub Actions, GitLab CI |
| Container/image | Công cụ nào được đóng gói | Runtime image không có jcmd |
| Runbook vận hành | Lệnh điều tra incident | jhat, jmap, jstack, jvisualvm |
| JVM option | Flag logging hoặc agent cũ | -Xloggc, -XX:+PrintGCDetails, -agentlib:hprof |
| Monitoring | Collector, parser, dashboard | Parser GC log của JDK 8 |
| Quyền truy cập | Ai attach được JVM, lưu dump ở đâu | Service account, filesystem, policy |

Một cách tìm nhanh trong repository:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'javah|jhat|jvisualvm|jmc|jstack|jmap|jinfo|jstat|jconsole|jcmd' .

rg -n --hidden -g '!**/.git/**' \
  -- '-Xloggc|-XX:\+PrintGC|-agentlib:hprof|-Xprof|-verbose:gc|-Xlog:' .
~~~

Kết quả tìm trong source chỉ là một phần của inventory. Lệnh còn có thể nằm trong script của máy chủ ứng dụng, cấu hình service manager, pipeline CI dùng chung, cron job hoặc runbook không lưu trong repository. Với mỗi điểm dùng, ghi lại mục đích, owner, đầu vào, đầu ra, môi trường và cơ chế chứng minh kết quả đúng.

Đặc biệt phân biệt JDK chạy build, JDK chạy ứng dụng và JDK chứa công cụ chẩn đoán. Phiên bản java trong terminal của developer không chứng minh runtime của service production.

## 3. javah từng được dùng để làm gì?

Java Native Interface (JNI) cho phép method Java gọi code native như C/C++. Một native method được khai báo bằng từ khóa native và không có thân method Java:

~~~java
package demo.bridge;

public final class NativeMath {
    public native int add(int left, int right);
}
~~~

Ở phía C/C++, implementation phải tuân theo JNI ABI: tên symbol, macro export, kiểu JNI và tham số môi trường. Trước đây workflow thường là:

~~~bash
javac -d build/classes src/demo/bridge/NativeMath.java
javah -jni -classpath build/classes -d build/headers demo.bridge.NativeMath
~~~

javah đọc thông tin class đã biên dịch và tạo header có khai báo symbol native tương ứng. Từ JDK 8, javac đã hỗ trợ tùy chọn -h để sinh native header khi biên dịch. javah bị loại bỏ ở JDK 10, nên build dùng javah có thể thất bại ngay tại bước tạo header khi nâng lên JDK 17 hoặc 21.

Thông báo lỗi phổ biến:

~~~text
javah: command not found
~~~

Trên Windows có thể xuất hiện thông báo không nhận diện được lệnh javah. Cách sửa là tích hợp **javac -h** vào bước compile, thay vì tiếp tục tải một executable javah cũ hoặc tự viết header bằng tay.

## 4. Thay javah bằng javac -h qua ví dụ JNI hoàn chỉnh

### 4.1. Cấu trúc demo

~~~text
jni-demo/
├── src/demo/bridge/NativeMath.java
├── native/native_math.c
└── build/
    ├── classes/
    ├── headers/
    └── native/
~~~

File src/demo/bridge/NativeMath.java:

~~~java
package demo.bridge;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    public native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println(new NativeMath().add(2, 3));
    }
}
~~~

System.loadLibrary nhận tên logic của native library. Tên file thực tế tùy OS, ví dụ libnative_math.so trên Linux, libnative_math.dylib trên macOS hoặc native_math.dll trên Windows. Ngoài tên file, native library có thể phụ thuộc các thư viện hệ điều hành khác.

### 4.2. Sinh class file và header đồng thời

Trong thư mục jni-demo:

~~~bash
mkdir -p build/classes build/headers build/native

javac \
  -h build/headers \
  -d build/classes \
  src/demo/bridge/NativeMath.java
~~~

Ý nghĩa:

- **-h build/headers:** nơi javac đặt native header được sinh.
- **-d build/classes:** nơi javac đặt class file.
- Compiler đọc khai báo native method và sinh header tương ứng, đồng bộ với bytecode Java vừa tạo.

Header thường có tên demo_bridge_NativeMath.h và chứa đoạn khai báo tương tự:

~~~c
#include <jni.h>

#ifdef __cplusplus
extern "C" {
#endif

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_add
  (JNIEnv *, jobject, jint, jint);

#ifdef __cplusplus
}
#endif
~~~

Đây là đoạn minh họa rút gọn; header thực tế còn có thể chứa include guard, comment và các chi tiết khác. **Header do javac sinh là nguồn tham chiếu chính**, vì tên symbol với method overload, package, class và kiểu tham số cần khớp chính xác.

### 4.3. Viết phần C

File native/native_math.c:

~~~c
#include "demo_bridge_NativeMath.h"

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_add(
    JNIEnv *env,
    jobject self,
    jint left,
    jint right
) {
    (void)env;
    (void)self;
    return left + right;
}
~~~

Instance native method nhận jobject làm tham số thứ hai; static native method nhận jclass ở vị trí tương ứng. JNI cung cấp các kiểu như jint, jlong, jstring và jbyteArray. Trộn kiểu C/C++ không tương thích hoặc quản lý tài nguyên JNI sai có thể gây crash, memory leak hoặc dữ liệu hỏng.

### 4.4. Build native library trên Linux

Ví dụ GCC:

~~~bash
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_math.c \
  -o build/native/libnative_math.so
~~~

Trên macOS và Windows, cần dùng native compiler, flag tạo thư viện, thư mục JNI header theo OS (darwin hoặc win32), tên file output và cơ chế linker thích hợp. Không sao chép nguyên lệnh GCC Linux cho mọi nền tảng.

Chạy trên Linux:

~~~bash
java \
  -Djava.library.path=build/native \
  -cp build/classes \
  demo.bridge.NativeMath
~~~

Kết quả:

~~~text
5
~~~

Vị trí -Djava.library.path phải nằm trước tên class main. Khi triển khai thật, kiểm tra cả native dependency graph và sự tương thích giữa JVM architecture với shared library (32/64 bit, CPU architecture, ABI).

### 4.5. Những lỗi JNI thường lộ ra sau migration

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| javah không tồn tại | JDK 10+ đã bỏ javah | Chuyển task sang javac -h |
| Header không được sinh | Source set, task hoặc path output sai | Xem output javac và directory header |
| Thiếu jni.h khi build C | Include path trỏ sai JDK | Kiểm tra JAVA_HOME/include và thư mục OS |
| UnsatisfiedLinkError: no native_math | JVM không tìm thấy shared library | Kiểm tra java.library.path, tên file và loader |
| UnsatisfiedLinkError với tên native method | Export symbol không đúng JNI descriptor hoặc native version | So sánh header với symbol được export |
| Native crash | Sai ABI, pointer, vòng đời reference hoặc thread | Thu crash log và kiểm tra code native |
| Chạy được Linux nhưng lỗi Windows | Build native theo một nền tảng duy nhất | Tạo và kiểm thử artifact cho từng nền tảng |

Khi method overloaded, JNI có quy tắc mangling symbol theo chữ ký. Không tự đoán tên hàm bằng cách nối chuỗi; dùng đúng header do compiler sinh. Việc JVM nạp được native library không tự chứng minh tất cả method JNI trong thư viện đều có implementation khớp.

## 5. Tích hợp tạo header vào Gradle và Maven

Trong project có build tool, bước tạo header phải được quản lý như một output của biên dịch Java và phải xảy ra trước bước build native code. Không nên giữ task javah độc lập chỉ để sử dụng JDK 8 song song.

### 5.1. Gradle

Với Gradle Java project, có thể đặt compiler arguments hoặc API native header output của JavaCompile theo khả năng của Gradle version đang dùng. Ví dụ ý định cấu hình bằng Groovy DSL:

~~~groovy
tasks.named("compileJava", JavaCompile) {
    options.compilerArgs += [
        "-h",
        layout.buildDirectory.dir("generated/jni-headers")
            .get().asFile.absolutePath
    ]
}
~~~

Đây là cấu hình minh họa. Với Gradle version có API native header directory riêng, nên dùng API chính thức để Gradle nhận biết output, incremental build và build cache. Cần xác minh compiler args không bị thêm trùng với cấu hình hiện có.

Build native task phải phụ thuộc vào task tạo header. Nếu compileJava bị đánh dấu UP-TO-DATE nhưng header đã bị xóa bằng một bước ngoài Gradle, build native có thể thất bại; khai báo output và dependency chính xác sẽ giúp khắc phục.

### 5.2. Maven

Với Maven Compiler Plugin, có thể truyền -h tới javac ở module có JNI declaration. Ví dụ:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <compilerArgs>
      <arg>-h</arg>
      <arg>target/generated/jni-headers</arg>
    </compilerArgs>
  </configuration>
</plugin>
~~~

Xác minh thư mục output tồn tại hoặc được plugin/compiler tạo phù hợp với phiên bản hiện tại. Nếu project đa module, cấu hình này chỉ nên áp dụng ở module có native methods. Kiểm tra các compile execution, profile và build order để native compiler luôn nhận header mới nhất.

### 5.3. Kiểm soát toolchain

Nếu build bằng JDK 21 nhưng sản phẩm vẫn hỗ trợ Java 17, cần xác định release source/API/bytecode mục tiêu, ví dụ thông qua --release 17, đồng thời kiểm tra native library ở chính runtime mục tiêu. Một header sinh bởi javac mới không tự làm native library portable trên mọi OS hoặc architecture.

Không cần commit mọi header sinh tự động vào repository nếu build có thể tái tạo chúng một cách xác định; nếu có lý do phải phát hành header như API cho đối tác native, cần gắn chúng với version thư viện và chính sách tương thích.

## 6. jhat và quy trình phân tích heap dump hiện đại

jhat là công cụ cũ dùng để duyệt dữ liệu trong Java heap dump qua giao diện web. Nó bị loại bỏ từ JDK 9. Nhu cầu vận hành vẫn tồn tại: thu heap dump, phân tích object graph, retained heap, GC roots và tìm nơi giữ reference gây memory leak.

### 6.1. Thu heap dump với JDK mới

Với HotSpot/OpenJDK và quyền attach phù hợp:

~~~bash
jcmd <pid> GC.heap_dump /secure/dumps/app-heap.hprof
~~~

Có thể cấu hình tự tạo heap dump khi OutOfMemoryError:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/secure/dumps \
  -jar app.jar
~~~

Heap dump có thể rất lớn, tiêu tốn thời gian/IO và gây pause trong quá trình tạo. File cũng có thể chứa dữ liệu nhạy cảm trong heap như token, credential hoặc thông tin cá nhân. Cần quyền truy cập hạn chế, dung lượng đủ, thời gian lưu, cách xóa và nơi chuyển file an toàn. Không đưa dump vào repository hoặc đính kèm công khai.

### 6.2. Phân tích bằng Eclipse MAT và VisualVM

**Eclipse Memory Analyzer (MAT)** phù hợp với việc phân tích retained heap, dominator tree, đường tới GC roots và nhiều tình huống memory leak trên heap dump lớn.

**VisualVM** có thể hiển thị memory, thread, profiling và mở heap dump tùy version/plugin. Với JDK hiện đại, cần cài và pin bản VisualVM độc lập phù hợp thay vì dựa vào đường dẫn jvisualvm có sẵn trong JDK 8.

Không phải công cụ nào cũng thay thế 1:1 giao diện hoặc tính năng của jhat. Điều cần xác minh là quy trình điều tra sự cố: có tạo được dump, chuyển được file, mở được trong công cụ được chọn và trả lời được câu hỏi về leak hay không.

### 6.3. Đừng nhầm định dạng HPROF với HPROF agent

File .hprof vẫn được sử dụng rộng rãi làm **định dạng heap dump**. Việc công cụ jhat bị loại bỏ không có nghĩa định dạng .hprof không còn dùng được. Ngược lại, profiler agent cũ như -agentlib:hprof là một cơ chế khác, không nên coi là công cụ được hỗ trợ trên mọi JDK mới. Với nhu cầu CPU/allocation profiling, JFR và profiler được hỗ trợ thường phù hợp hơn.

## 7. Tập trung chẩn đoán JVM qua jcmd

jcmd là công cụ đa mục đích của nhiều JVM HotSpot/OpenJDK. Thay vì ghi cứng một tập lệnh của JDK cũ, có thể hỏi chính JVM hiện tại hỗ trợ những diagnostic command nào.

~~~bash
jcmd -l
jcmd <pid> help
~~~

Các command hay dùng:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

| Nhu cầu | Cách thực hiện thường gặp | Lưu ý |
|---|---|---|
| Kiểm tra runtime | VM.version, VM.command_line | Phải chọn đúng PID |
| Xem JVM flags | VM.flags, VM.flags -all tùy JDK | Một số flag phụ thuộc vendor |
| Xem system properties | VM.system_properties | Có thể chứa secret |
| Thread dump | Thread.print | Output có thể rất lớn |
| Heap summary | GC.heap_info | Không tự chứng minh memory leak |
| Class histogram | GC.class_histogram | Có thể tiêu tốn tài nguyên hoặc pause |
| Heap dump | GC.heap_dump | File lớn và nhạy cảm |
| Flight recording | JFR.start, JFR.check, JFR.dump, JFR.stop | Cần kiểm soát thời lượng, event và quyền |

Mọi diagnostic command không nhất thiết tồn tại ở mọi release/vendor. Khi cần cú pháp cụ thể, dùng jcmd <pid> help <command> trên đúng runtime. Một số thao tác chẩn đoán kích hoạt safepoint/GC hoặc làm tăng overhead; không nên chạy tùy tiện ở production.

### 7.1. jmap, jstack, jstat, jinfo không phải tất cả đã bị loại bỏ

Các công cụ này vẫn có giá trị ở nhiều JDK:

- **jstack** thu thập thread dump; jcmd Thread.print là một lựa chọn khác trong nhiều tình huống.
- **jmap** cung cấp một số thao tác memory/heap; jcmd GC.heap_info, GC.class_histogram hoặc GC.heap_dump thay được một số nhu cầu.
- **jstat** quan sát thông số JVM/GC theo cách của nó; không có một command jcmd duy nhất thay toàn bộ khả năng lấy mẫu thời gian.
- **jinfo** cho biết một số flag và cấu hình; nhiều thông tin đó có thể xem qua jcmd.
- **jconsole** là công cụ GUI JMX có thể được cung cấp cùng JDK đầy đủ; trong image tối giản có thể không có.

Chọn công cụ theo thông tin thực sự cần thu và giới hạn của runtime. Việc chuyển sang jcmd mang lại cách gọi tập trung nhưng không phải quy tắc bắt buộc thay thế mọi executable cũ.

## 8. Java Flight Recorder và JDK Mission Control

**Java Flight Recorder (JFR)** là cơ chế ghi sự kiện JVM/ứng dụng theo thời gian. Tùy cấu hình và runtime, JFR có thể thu dữ liệu về CPU execution, allocation, garbage collection, thread, lock contention và IO. Nó giúp điều tra những hiện tượng không dễ nhìn thấy qua một heap snapshot hoặc thread dump đơn lẻ.

**JDK Mission Control (JMC)** là công cụ phân tích recording JFR. JMC thường được quản lý như sản phẩm/tooling riêng tùy vendor; không nên giả định mọi JDK image chứa sẵn jmc.

### 8.1. Ghi một recording ngắn

Ví dụ trên JDK hỗ trợ JFR:

~~~bash
jcmd <pid> JFR.start \
  name=migration-check \
  settings=profile \
  duration=60s \
  filename=/secure/recordings/migration-check.jfr

jcmd <pid> JFR.check
~~~

Có thể dùng JFR.dump để xuất recording đang chạy; xem help của diagnostic command trên runtime đích để có tham số chính xác. Mở file .jfr bằng JMC hoặc công cụ tương thích và xem timeline, sample, allocation, GC hay sự kiện liên quan.

| Triệu chứng | JFR có thể hỗ trợ phân tích |
|---|---|
| CPU tăng | Execution samples và stack trace |
| Allocation tăng | Nhóm class/method tạo object và allocation events |
| GC pause cao | Timeline GC, heap và các giai đoạn GC |
| Thread bị block | Lock contention và trạng thái thread |
| Độ trễ ngắt quãng | Sự kiện thread/IO và tương quan theo thời gian |
| Sự cố khó tái hiện | Recording ngắn quanh thời điểm sự cố |

JFR không thay thế mọi metric dài hạn hoặc distributed tracing. Recording có thể chứa tên method/class, đường dẫn, tham số hoặc dữ liệu ứng dụng tùy event; cần bảo vệ như một artifact chẩn đoán. Overhead phụ thuộc event, settings, sampling và thời lượng, vì vậy nên đo trên staging trước khi áp dụng profile recording cho production.

## 9. Giám sát dài hạn qua JMX và telemetry

Một runbook chỉ hướng dẫn mở GUI trên máy chủ là chưa đủ để có khả năng giám sát ổn định. Hệ thống cần metric, alert, log và trace được duy trì xuyên suốt JDK migration.

### 9.1. JMX

Java Management Extensions (JMX) cho phép JVM và ứng dụng công bố MBean về memory pool, GC, thread, class loading và thành phần nghiệp vụ. JConsole/VisualVM có thể sử dụng JMX, còn exporter/collector có thể lấy dữ liệu đưa vào hệ thống monitoring tập trung.

Nếu cần remote JMX, phải kiểm soát authentication, TLS hoặc lớp bảo vệ tương ứng, quyền truy cập và network exposure. Không bật endpoint JMX công khai mà vô hiệu hóa xác thực chỉ để tiện chẩn đoán.

### 9.2. Metrics, log, trace

Các tín hiệu thường cần giữ qua migration:

- Heap/non-heap memory, memory pool và pressure theo instance.
- GC pause, frequency, throughput hoặc allocation theo GC/JDK được dùng.
- Thread count, thread pool saturation, queue depth.
- Request rate, error rate, latency percentiles, timeout và retry.
- Log có cấu trúc, trace liên service và thông tin phiên bản deployment.

Micrometer, OpenTelemetry hoặc exporter phù hợp với framework có thể chuyển metric/trace tới hệ thống observability. Chúng không phải executable mặc định của JDK. Cần đối chiếu dependency/version, exporter, metric name/label và dashboard sau nâng cấp.

Một application chạy thành công nhưng mất metric hoặc alert sau migration vẫn tạo ra rủi ro vận hành nghiêm trọng.

## 10. Chuyển GC logging cũ sang unified logging

Ứng dụng chạy JDK 8 có thể dùng:

~~~text
-verbose:gc
-XX:+PrintGCDetails
-XX:+PrintGCDateStamps
-Xloggc:/var/log/app/gc.log
~~~

Từ JDK 9, HotSpot dùng unified logging với cú pháp -Xlog. Ví dụ trên JDK mới:

~~~bash
java \
  -Xlog:gc*:file=/var/log/app/gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

Đây là cấu hình cùng mục đích, không phải ánh xạ byte-for-byte của mọi flag cũ. gc* chọn tag liên quan GC; file và decorator quyết định nơi ghi và metadata. Mức chi tiết và format có thể khác phiên bản JDK/GC, nên parser hoặc dashboard dựa trên log cũ phải được kiểm tra.

Quy trình chuyển:

1. Ghi nhận option cũ, đường dẫn log, rotate/retention và parser đang dùng.
2. Kiểm tra cú pháp -Xlog của đúng JDK vendor/release mục tiêu.
3. Chạy thử, xác nhận JVM không từ chối option và file log được tạo.
4. Tạo workload GC đại diện và kiểm tra nội dung/log volume.
5. Xác nhận dashboard, alert và log collector còn hoạt động.

Một số cờ cũ có thể được ánh xạ, cảnh báo hoặc bị loại bỏ tùy version. Không dùng -XX:+IgnoreUnrecognizedVMOptions như cách giải quyết mặc định; bỏ qua flag có thể làm mất logging hoặc tuning quan trọng.

Ví dụ kết hợp GC và safepoint logging:

~~~bash
java \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

GC log phục vụ phân tích diễn tiến theo thời gian, còn jcmd GC.heap_info chỉ cho snapshot ở thời điểm gọi. Đừng coi hai nguồn là tương đương.

## 11. Kiểm tra tool availability trên JDK đích

Ở môi trường Linux/macOS:

~~~bash
command -v java
command -v javac
command -v jcmd
command -v jconsole
java -version
javac -version
~~~

Ở PowerShell:

~~~powershell
Get-Command java -All
Get-Command javac -All
Get-Command jcmd -All
Get-Command jconsole -All
java -version
javac -version
~~~

Nếu có nhiều JDK, gọi qua đường dẫn cụ thể:

~~~bash
"$JAVA_HOME/bin/jcmd" -l
"$JAVA_HOME/bin/javac" -version
~~~

Phải kiểm tra chính môi trường deployment. Việc jcmd có trên máy build không chứng minh runtime image của ứng dụng cũng có. Khi production container thiếu tooling, có thể cần debug image/diagnostic sidecar được cấp quyền phù hợp hoặc một kênh telemetry đã được thiết kế từ trước.

### 11.1. Khi jcmd không attach được

| Triệu chứng | Điều cần kiểm tra |
|---|---|
| Không thấy process | PID namespace, user, container và process đã kết thúc chưa |
| Permission denied | Quyền hệ điều hành, owner và attach policy |
| Attach bị vô hiệu hóa | Cấu hình JVM và security policy |
| Command không tồn tại | jcmd <pid> help, JVM vendor/version |
| Dump/recording không được ghi | Quyền thư mục, dung lượng, read-only filesystem |
| Output không đúng process | PID trùng qua namespace hoặc nhầm container |

Không tự mở rộng quyền của process production chỉ để chạy diagnostic command. Ghi nhận giới hạn và chọn kênh chẩn đoán được cho phép.

## 12. Kịch bản migration Java 8 sang JDK 21

Giả sử một ứng dụng Java 8 sử dụng JNI, vận hành dựa vào jhat và GC log parser cũ. Mục tiêu là JDK 21.

### Bước 1: Chốt baseline

Ghi JDK/vendor/OS/architecture, lệnh tạo JNI header, vị trí native library, output/owner của heap dump, cờ GC logging và dashboard liên quan. Tạo các test chức năng JNI đại diện và baseline metric vận hành.

### Bước 2: Chuyển build JNI

Thay task gọi javah bằng javac -h, sinh header từ source, build lại native library theo header mới và kiểm tra export symbol. Chạy test System.loadLibrary và các native method trên đúng OS/architecture/JDK đích.

### Bước 3: Thay phân tích heap

Thiết lập nơi lưu heap dump được bảo vệ, dùng jcmd GC.heap_dump hoặc HeapDumpOnOutOfMemoryError, sau đó thử mở dump bằng Eclipse MAT/VisualVM. Cập nhật runbook: người được phép tạo dump, nơi lưu, cách chuyển file và thời hạn xóa.

### Bước 4: Chuyển logging và quan sát

Chuyển cờ GC sang -Xlog; xác nhận log được thu và dashboard hoạt động. Bổ sung JFR/JMC cho điều tra chuyên sâu, đồng thời duy trì metric/alert dài hạn qua JMX hoặc telemetry ứng dụng.

### Bước 5: Kiểm thử trên JDK đích

Chạy compile, unit/integration test, JNI smoke test, workload thực tế, thread dump, heap dump và một recording JFR ngắn trong môi trường được kiểm soát. Phân biệt lỗi ứng dụng, native ABI, công cụ, class file và quyền attach.

### Bước 6: Rollout

Triển khai theo nhóm instance hoặc môi trường, theo dõi error rate, crash, native load error, GC pause, latency và telemetry ingestion. Có phương án rollback nếu chưa đủ bằng chứng ổn định.

## 13. Các sai lầm thường gặp

- **Tiếp tục gọi javah từ JDK cũ:** toolchain build bị trộn, khó kiểm soát và không giải quyết gốc vấn đề; hãy chuyển sang javac -h.
- **Viết JNI header thủ công:** dễ sai tên symbol, overload, kiểu JNI và static/instance; để compiler sinh header.
- **Chỉ kiểm tra Java compile:** native compiler, shared library, OS loader và architecture vẫn có thể lỗi.
- **Coi mọi công cụ quen thuộc là bị xóa:** nhiều JDK còn cung cấp jstat, jmap, jstack, jinfo hoặc jconsole.
- **Nhầm việc jhat bị xóa với định dạng .hprof bị loại bỏ:** heap dump vẫn có thể được phân tích bằng MAT/VisualVM.
- **Giả định VisualVM/JMC có sẵn trong JDK:** phân phối và cài đặt phụ thuộc vendor/version.
- **Giữ nguyên GC logging flag từ JDK 8:** JVM mới có thể cảnh báo/từ chối hoặc parser không hiểu output.
- **Chạy jcmd sai PID/container:** lấy dữ liệu sai JVM hoặc không thể attach.
- **Thu dump/JFR không kiểm soát:** dữ liệu nhạy cảm và overhead có thể ảnh hưởng production.
- **Chỉ dùng GUI monitoring:** thiếu alert và telemetry dài hạn.
- **Chỉ kiểm tra máy phát triển:** production image có thể thiếu tool hoặc giới hạn quyền.
- **Không thử runbook sau migration:** công cụ lỗi thời chỉ được phát hiện khi incident xảy ra.

## 14. Checklist trước khi hoàn tất

- [ ] Đã liệt kê các lệnh legacy và nơi chúng xuất hiện trong build, CI, image, runbook.
- [ ] Đã phân loại từng công cụ: bị loại bỏ, tách khỏi JDK, thay cú pháp hay vẫn hỗ trợ.
- [ ] Không còn task bắt buộc phải gọi javah.
- [ ] javac -h sinh đúng header từ source hiện tại và build tool theo dõi output.
- [ ] Native library chạy trên OS/architecture/JDK mục tiêu.
- [ ] Có quy trình tạo và phân tích heap dump thay jhat.
- [ ] VisualVM/JMC độc lập được cài/quản lý nếu cần.
- [ ] Các lệnh jcmd được thử trên đúng runtime, PID namespace và quyền.
- [ ] GC logging đã được chuyển/kiểm chứng cùng parser và dashboard.
- [ ] Metric, log và alert tiếp tục hoạt động sau nâng cấp.
- [ ] Heap dump, JFR và diagnostic output có chính sách bảo mật/lưu trữ.
- [ ] Runbook và pipeline được cập nhật với lệnh thực tế được hỗ trợ.
- [ ] Đã exercise chẩn đoán và kiểm thử trên môi trường đại diện.
- [ ] Có owner, version và support matrix cho bộ công cụ mới.

## 15. Kết luận

Migration các công cụ Java cũ phải bắt đầu từ **nhiệm vụ cần thực hiện**, rồi chọn cơ chế được hỗ trợ trên JDK đích. Với JNI, javah đã được thay bằng javac -h, cho phép tạo header trong bước biên dịch Java và đồng bộ với native declaration. Với giám sát, jhat được thay bằng quy trình heap dump và công cụ như Eclipse MAT/VisualVM; nhiều tác vụ chẩn đoán dùng jcmd, JFR và JMC, trong khi quan sát dài hạn cần JMX và telemetry ứng dụng. Việc kiểm tra đúng vendor/version, quyền runtime, native artifact, chi phí chẩn đoán và dashboard giúp Java migration giữ được khả năng vận hành và xử lý sự cố.
