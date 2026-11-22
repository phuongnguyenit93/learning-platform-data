# Phân biệt hành vi triển khai JVM với bảo đảm ngôn ngữ

Một chương trình Java có thể chạy trên nhiều JVM, hệ điều hành và kiến trúc CPU. Kết quả đúng của chương trình phải dựa trên các bảo đảm trong Java Language Specification (JLS), Java Virtual Machine Specification (JVMS) và hợp đồng của Java API. Các chi tiết như layout object, thuật toán GC, cách JIT biên dịch hay thời điểm thread được chạy thuộc về implementation và có thể thay đổi giữa runtime hoặc cấu hình.

Quy tắc thực hành là: **dựa vào đặc tả để viết logic đúng; đo runtime cụ thể để tối ưu hiệu năng**. Một hành vi quan sát được trên HotSpot không tự động trở thành bảo đảm của Java.

## 1. Bốn lớp hợp đồng cần phân biệt

| Lớp | Mô tả | Dùng để quyết định điều gì? |
|---|---|---|
| Java Language Specification (JLS) | Ngữ nghĩa của cú pháp, kiểu dữ liệu, exception, thread và memory model | Chương trình Java được phép làm gì và có thể quan sát kết quả nào |
| Java SE API specification | Hợp đồng của class và method thư viện như Thread, CountDownLatch, Runtime | Method bảo đảm điều gì cho caller |
| Java Virtual Machine Specification (JVMS) | Class-file format, bytecode, abstract runtime machine và các hành vi bắt buộc của VM | Một JVM tương thích phải thực thi bytecode như thế nào về mặt quan sát |
| JVM implementation | HotSpot, OpenJ9, GraalVM hoặc runtime cụ thể cùng flags và nền tảng | Cách thực thi, layout, GC, JIT, scheduling và đặc tính hiệu năng |

JLS và JVMS là các đặc tả liên quan nhưng không đồng nhất. JLS định nghĩa ngữ nghĩa chương trình Java; JVMS định nghĩa abstract machine có thể chạy class file. Java SE API lại có hợp đồng riêng. Implementation được tự do chọn chiến lược bên trong, miễn đáp ứng các đặc tả và hợp đồng áp dụng.

JVMS nói rõ đây là một abstract machine, không phải mô tả một implementation cụ thể. Ví dụ, memory layout của runtime data area, thuật toán garbage collection và tối ưu hóa nội bộ bytecode được để cho nhà triển khai quyết định.

## 2. Bảo đảm của ngôn ngữ là điều chương trình được quyền dựa vào

Các ví dụ sau là những bảo đảm có thể dùng trong code portable:

- Kiểu primitive có kích thước và miền giá trị được đặc tả; phép toán int tuân theo ngữ nghĩa số nguyên 32-bit của Java, kể cả khi overflow.
- Truy cập array kiểm tra giới hạn; index ngoài phạm vi gây ArrayIndexOutOfBoundsException.
- Dereference null gây NullPointerException theo ngữ nghĩa của phép truy cập.
- Quy tắc khởi tạo class, kiểm tra kiểu, dispatch method và xử lý exception được đặc tả.
- Java Memory Model xác định quan hệ đồng bộ, happens-before và các giá trị mà read được phép quan sát.
- Một lần unlock monitor happens-before lần lock tiếp theo trên cùng monitor; volatile write happens-before volatile read tiếp theo của cùng biến; Thread.start và Thread.join cũng có các quan hệ happens-before được quy định.
- Hợp đồng API như CountDownLatch bảo đảm các hành động trước countDown xảy ra trước các hành động sau khi await trả về thành công.

Đây là những điều một JVM tương thích phải bảo toàn. Code có thể dựa vào chúng mà không cần biết runtime đang chạy trên x86, ARM, Windows hay Linux.

## 3. Hành vi triển khai không phải bảo đảm của ngôn ngữ

Những quan sát sau không được dùng làm điều kiện đúng của ứng dụng:

| Quan sát | Vì sao không phải bảo đảm portable |
|---|---|
| Object luôn có header 12 hoặc 16 byte | JVMS không quy định object header hoặc layout field cụ thể |
| Reference luôn chiếm 4 hoặc 8 byte | Compressed oops là lựa chọn triển khai và cấu hình của một số JVM |
| Mọi object được viết bằng new luôn có allocation vật lý trên heap | JIT có thể loại bỏ allocation nếu không thể quan sát được |
| Một method được JIT biên dịch sau đúng N lần gọi | Ngưỡng compile, profile và tiering là chính sách implementation |
| GC chạy ngay sau System.gc() | System.gc chỉ là yêu cầu best-effort, không phải lệnh đồng bộ bắt buộc thu gom |
| Object unreachable sẽ được dọn trong một khoảng thời gian cố định | Thời điểm GC và Cleaner phụ thuộc runtime, tải và collector |
| Thread.sleep(10) làm thread chạy lại đúng sau 10 ms | Timer và scheduler chỉ bảo đảm độ trễ tối thiểu theo hợp đồng; thời điểm chạy lại phụ thuộc hệ thống |
| Thread luôn được chạy theo thứ tự tạo | Scheduler không có bảo đảm FIFO tổng quát |
| Field luôn nằm trong object theo đúng thứ tự khai báo | Layout và padding do implementation quyết định |
| Stack frame luôn nằm trên native stack | JVMS mô tả cấu trúc logic; representation vật lý do VM chọn |

Một chi tiết có thể đúng trên một build HotSpot và sai trên OpenJ9 hoặc một bản HotSpot khác. Nếu ứng dụng phụ thuộc chi tiết đó để tạo kết quả đúng, code đã gắn chặt vào implementation.

## 4. JVMS mô tả cấu trúc logic, không bắt buộc layout vật lý

JVMS mô tả các runtime data area như heap, JVM stack, method area và frame. Đây là mô hình cần để định nghĩa hành vi bytecode. Đặc tả không yêu cầu tất cả implementation phải dùng đúng một cách bố trí vật lý.

Ví dụ:

- Heap là vùng logic dùng cấp phát class instance và array; cách quản lý, mở rộng, thu hẹp và thu hồi do implementation quyết định.
- JVM stack chứa frame của thread; implementation có thể chọn cách biểu diễn và cấp phát frame khác nhau.
- Method area mô tả dữ liệu theo class như runtime constant pool, field/method data và code; vị trí vật lý và chính sách quản lý không bị cố định thành một layout duy nhất.
- Reference là giá trị dùng để truy cập object. Không có hợp đồng Java cho phép chuyển reference thành địa chỉ native để suy luận layout.

Không suy ra từ sơ đồ JVMS rằng mọi biến local chắc chắn nằm trên stack vật lý hoặc mọi object chắc chắn chiếm một vùng heap có layout cố định. Đó là cách mô hình hóa logic, không phải bản đồ RAM của mọi JVM.

## 5. JIT compiler có thể thay đổi cách thực thi nhưng phải giữ ngữ nghĩa

Một JVM có thể diễn giải bytecode, biên dịch sang native code hoặc kết hợp nhiều tầng. HotSpot thường dùng tiered compilation: code được thực thi và profile trước, sau đó các compiler tạo code tối ưu hơn khi có đủ thông tin.

Một số tối ưu hóa thường gặp:

- **Inlining:** thay lời gọi method bằng phần thân đã inline khi điều kiện phù hợp.
- **Dead-code elimination:** bỏ tính toán không ảnh hưởng kết quả quan sát được.
- **Constant folding:** tính trước biểu thức có giá trị hằng.
- **Escape analysis:** phân tích object có thoát khỏi phạm vi sử dụng hay không.
- **Scalar replacement:** thay object không escape bằng các giá trị riêng lẻ và có thể loại bỏ allocation.
- **Lock elimination:** bỏ một số thao tác khóa khi compiler chứng minh object không thể được thread khác quan sát.
- **Deoptimization:** quay về code ít tối ưu hơn khi giả định profile không còn đúng.

Các tối ưu hóa này không đổi hợp đồng của chương trình. JIT chỉ được dùng transformation mà kết quả vẫn nằm trong tập hành vi được JLS/JVMS cho phép.

### Escape analysis không đồng nghĩa với stack allocation

HotSpot có thể loại bỏ allocation của object không escape bằng scalar replacement. Điều đó không có nghĩa object đã được cấp phát trên stack. Trong trường hợp tối ưu, object có thể không tồn tại như một object vật lý nào cả; các field của nó được giữ trong register hoặc biểu diễn khác.

Vì vậy không viết code dựa trên giả định rằng object local luôn nằm trên stack hoặc object không escape chắc chắn có một stack address.

## 6. Layout object và compressed oops

Java không quy định kích thước header, thứ tự field, padding, alignment hoặc kích thước reference trong heap. Các yếu tố này thay đổi theo:

- JVM implementation và phiên bản.
- Kiến trúc 32-bit hoặc 64-bit.
- Heap size và cờ khởi chạy.
- Compressed ordinary object pointers (compressed oops).
- Cách VM căn chỉnh object và field.

Trong HotSpot, compressed oops có thể biểu diễn reference bằng offset 32-bit thay vì native pointer 64-bit trong một số cấu hình. Việc bật/tắt và cách decode phụ thuộc nền tảng và heap. Không giả định reference luôn 4 byte hoặc mọi object có cùng overhead.

Nếu cần đo object footprint trên một runtime cụ thể, có thể dùng Java Object Layout (JOL) trong môi trường benchmark hoặc diagnostic. Kết quả JOL là phép đo của JVM, phiên bản, flags và nền tảng đang chạy; nó không phải hợp đồng của Java language.

## 7. String compact storage là ví dụ của implementation detail

HotSpot từ Java 9 dùng Compact Strings để giảm bộ nhớ cho String chứa các ký tự Latin-1. Implementation lưu nội dung bằng byte array cùng thông tin coder thay vì luôn dùng char array UTF-16.

Đây là tối ưu nội bộ của JDK/HotSpot, không phải API công khai. Code ứng dụng không được giả định String có field backing array với kiểu cụ thể, không dùng reflection hoặc Unsafe để phụ thuộc layout đó, và không thay đổi cách xử lý Unicode dựa trên việc một chuỗi hiện tại được lưu bằng Latin-1.

Hợp đồng portable là String biểu diễn chuỗi ký tự theo API Java. Cách lưu byte/char ở bên trong có thể thay đổi mà không làm thay đổi hợp đồng đó.

## 8. Garbage collection: ngữ nghĩa reachability khác với thời điểm thu gom

Java bảo đảm object không còn reachable có thể được thu hồi để tái sử dụng bộ nhớ. Nhưng ngôn ngữ không quy định collector cụ thể hoặc thời điểm thu gom.

Các implementation có thể dùng collector khác nhau, ví dụ G1, ZGC, Shenandoah hoặc collector khác tùy JDK distribution. Mỗi collector có trade-off riêng về throughput, pause, CPU, heap overhead và latency.

Không nên:

- Gọi System.gc() rồi giả định object đã được thu gom.
- Dùng Thread.sleep() để chờ GC hoàn tất.
- Dựa vào việc heap hoặc process RSS phải giảm ngay sau một đợt GC.
- Giả định mọi collector đều compact hoặc di chuyển object theo cùng cách.
- Dựa vào thời điểm finalization/Cleaner để đóng file, socket hoặc transaction đúng hạn.

Nếu cần giải phóng tài nguyên đúng thời điểm, dùng close(), AutoCloseable và try-with-resources. GC là cơ chế quản lý bộ nhớ, không phải API deterministic resource management.

Khi cần chẩn đoán collector, hãy đo runtime thật bằng GC logs, JFR hoặc công cụ của JDK đang chạy. Số liệu của một collector không tự động áp dụng cho collector khác.

## 9. Scheduling và timing không phải đồng bộ hóa

JLS quy định các quan hệ đồng bộ, không quy định thread nào luôn chạy trước hoặc được cấp CPU trong bao lâu.

Thread.sleep và Thread.yield không tạo happens-before, không flush mọi write và không bảo đảm thread khác đã chạy. Sleep chỉ tạm dừng thread theo timer/scheduler; khi nào thread được chạy lại còn phụ thuộc hệ điều hành và tài nguyên CPU.

Không dùng đoạn code kiểu:

~~~java
sharedValue = 42;
Thread.sleep(10);
System.out.println(sharedValue);
~~~

để công bố dữ liệu cho thread khác. Dùng volatile, synchronized, Lock, CountDownLatch, Future hoặc primitive concurrency phù hợp.

Trong code concurrent, hãy chứng minh quan hệ happens-before thay vì dựa trên kết quả quan sát được trong một lần chạy. Một test không tái hiện race condition không chứng minh code không có data race.

## 10. Ví dụ Java: dựa vào hợp đồng, không dựa vào lịch chạy

Ví dụ sau dùng CountDownLatch để công bố dữ liệu giữa hai thread. Hợp đồng của CountDownLatch quy định các hành động trước countDown xảy ra trước các hành động sau khi await trả về thành công.

Tạo file **JvmContractDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class JvmContractDemo {
    private static int sharedValue;
    private static final CountDownLatch PUBLISHED =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread writer = new Thread(() -> {
            sharedValue = 42;
            PUBLISHED.countDown();
        });

        writer.start();
        PUBLISHED.await();

        System.out.println("value after latch: " + sharedValue);
        writer.join();

        int[] values = new int[1];
        try {
            int ignored = values[1];
            throw new AssertionError("Array bounds must be checked");
        } catch (ArrayIndexOutOfBoundsException expected) {
            System.out.println("array bounds: enforced");
        }

        System.out.println("VM implementation: "
                + System.getProperty("java.vm.name"));
        System.out.println("max heap bytes: "
                + Runtime.getRuntime().maxMemory());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 JvmContractDemo.java
java JvmContractDemo
~~~

Hai dòng đầu có kết quả cố định theo hợp đồng Java:

~~~text
value after latch: 42
array bounds: enforced
~~~

Hai dòng cuối phản ánh runtime và cấu hình đang chạy:

~~~text
VM implementation: <depends on JVM vendor and build>
max heap bytes: <depends on JVM options and environment>
~~~

CountDownLatch cung cấp quan hệ đồng bộ; code không dựa vào việc writer chạy nhanh hay chậm. Kiểm tra array bounds là hành vi ngôn ngữ/JVM được đặc tả. Tên VM và max heap chỉ là thông tin môi trường, không được hardcode thành expected value của test portable.

## 11. Kiểm thử portable và kiểm thử implementation-specific

Phân biệt mục tiêu test:

| Loại test | Có thể khẳng định |
|---|---|
| Unit test theo JLS/API | Kết quả logic, exception, visibility và contract của method |
| Concurrency test có synchronization đúng | Invariant và quan hệ happens-before cần thiết |
| Performance benchmark | Throughput/latency/allocation trên một runtime và cấu hình đã ghi rõ |
| VM diagnostic test | Flags, GC, JIT hoặc layout của một implementation cụ thể |
| Cross-JVM test | Code có tuân thủ contract trên nhiều implementation hay không |

Trong unit test portable, không assert:

- Kích thước object chính xác.
- Địa chỉ memory hoặc vị trí field.
- Thời điểm GC chạy.
- Số lần gọi trước khi JIT compile.
- Thời gian Thread.sleep hoặc scheduling chính xác.
- Thứ tự chạy thread khi không có synchronization.
- Tốc độ một method cố định trên mọi máy.

Có thể tạo test riêng cho HotSpot hoặc OpenJ9 nếu sản phẩm thật sự phụ thuộc implementation cụ thể. Khi đó ghi rõ vendor, version, architecture, flags và lý do cần kiểm tra. Không trộn assertion implementation-specific vào test suite portable.

## 12. Đo hiệu năng mà không nhầm số đo với bảo đảm

Performance là thuộc tính của workload và môi trường, không phải một con số cố định của ngôn ngữ Java.

Khi benchmark:

1. Ghi JDK vendor, version, JVM name, OS, CPU, memory và flags.
2. Dùng JMH hoặc harness phù hợp thay cho một vòng lặp nanoTime tự viết.
3. Có warm-up, measurement iteration và fork.
4. Dùng input đại diện, tránh dead-code elimination và constant folding làm sai mục tiêu đo.
5. Đo allocation/GC cùng throughput và latency.
6. Kiểm tra p95/p99 nếu ứng dụng nhạy với tail latency.
7. Chạy lại trên runtime, heap và collector sẽ triển khai thật.
8. Không biến kết quả benchmark của một máy thành giới hạn correctness của code.

Ví dụ, nếu một object allocation bị HotSpot loại bỏ trong benchmark, không có nghĩa mọi JVM đều loại bỏ nó. Ngược lại, một benchmark cho thấy allocation xảy ra cũng không chứng minh implementation khác sẽ làm tương tự.

## 13. Công cụ quan sát implementation cụ thể

Một số công cụ hữu ích để trả lời câu hỏi về runtime đang chạy:

- java -version: vendor, version và VM build.
- java -XshowSettings:vm -version: một số thông tin cấu hình VM.
- jcmd PID VM.flags: flags đang có hiệu lực trên process, nếu JDK cung cấp command đó.
- JFR: CPU samples, allocation, GC, thread park và I/O.
- GC logging: quan sát collector, pause và heap behavior.
- JOL: đo object layout trên runtime đang chạy.

Các cờ -XX và một số lệnh diagnostic phụ thuộc implementation/vendor/version. Dùng chúng để điều tra và tối ưu môi trường mục tiêu; không nhúng giả định về flag riêng của HotSpot vào logic ứng dụng portable.

## 14. Lỗi suy luận thường gặp

**Một kết quả lặp lại trên máy của tôi nên chắc chắn là Java guarantee.** Kết quả lặp lại chỉ cho biết runtime và workload đó đã thể hiện như vậy. Muốn biết guarantee, tra JLS, JVMS hoặc API specification.

**JVMS nói có heap và stack nên mọi object đều nằm đúng như sơ đồ.** JVMS mô tả abstract runtime areas; layout vật lý và representation do implementation quyết định.

**Mọi object new đều có allocation vật lý.** JIT có thể loại bỏ allocation không quan sát được bằng escape analysis và scalar replacement.

**Sleep đủ lâu là thread khác đã thấy dữ liệu.** Sleep/yield không có synchronization semantics. Dùng một cơ chế tạo happens-before.

**System.gc() đã gọi thì GC phải chạy.** Đây là yêu cầu best-effort; không dùng làm điều kiện correctness hoặc test timing.

**Object header và reference có kích thước cố định.** Không có bảo đảm portable về layout hoặc kích thước vật lý của object/reference.

**Benchmark nhanh trên HotSpot chứng minh code nhanh trên mọi JVM.** JIT, GC, layout, compiler và phần cứng có thể khác. Benchmark phải ghi rõ môi trường.

**Một test không thấy race condition nghĩa là không có data race.** Hành vi race có thể hiếm hoặc phụ thuộc timing. Phải phân tích synchronization và happens-before.

## 15. Checklist khi đọc một tuyên bố về JVM

- Xác định tuyên bố đến từ JLS, JVMS, Java SE API hay tài liệu implementation.
- Tìm điều kiện và phiên bản áp dụng.
- Phân biệt observable behavior với cách runtime thực hiện bên trong.
- Kiểm tra liệu tuyên bố có phụ thuộc vendor, collector, JIT, flags hoặc architecture không.
- Nếu là concurrency, viết ra happens-before edges thay vì suy luận từ timing.
- Nếu là performance, benchmark trên runtime mục tiêu và ghi đầy đủ cấu hình.
- Nếu là object layout, xem đó là phép đo implementation-specific.
- Không dùng một kết quả thực nghiệm để mở rộng hợp đồng của Java.
- Viết test portable theo guarantee; tách diagnostic test riêng cho implementation khi cần.

Cách suy nghĩ an toàn là giữ hai tầng tách biệt: đặc tả quyết định tính đúng đắn của chương trình; implementation quyết định cách đạt được hiệu năng. Khi đổi JDK hoặc nền tảng, code đúng theo đặc tả vẫn giữ semantics, còn số đo và tối ưu nội bộ có thể thay đổi.

## Tài liệu tham khảo

- [Java Language Specification, Chapter 17 — Threads and Locks](https://docs.oracle.com/en/java/javase/24/docs/specs/jls/jls-17.html)
- [Java Virtual Machine Specification, Chapter 2 — The Structure of the JVM](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-2.html)
- [Java Virtual Machine Specification, Section 2.7 — Representation of Objects](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-2.html#jvms-2.7)
- [CountDownLatch — Java SE API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java HotSpot VM Performance Enhancements — Java SE 24](https://docs.oracle.com/en/java/javase/24/vm/java-hotspot-virtual-machine-performance-enhancements.html)
