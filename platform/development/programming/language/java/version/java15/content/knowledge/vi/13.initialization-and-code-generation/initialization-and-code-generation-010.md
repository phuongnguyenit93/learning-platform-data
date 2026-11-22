# Đo chi phí định nghĩa, liên kết và gọi mã sau warm-up (Java 15+)

## Mục tiêu

Khi sinh **hidden class** tại runtime bằng **MethodHandles.Lookup.defineHiddenClass(...)**, ứng dụng phải trả nhiều loại chi phí khác nhau: chuẩn bị bytecode, **định nghĩa và liên kết lớp**, khởi tạo, tìm phương thức hoặc tạo handle, thực hiện lần gọi đầu, sau đó mới đến **chi phí gọi mã đã được làm nóng (warm-up)**. Bài này hướng dẫn **tách đúng giai đoạn, đo đúng đại lượng và diễn giải số liệu** mà không đánh đồng một lần gọi lạnh với tốc độ ổn định sau khi JIT tối ưu.

Kết thúc bài, cần biết:

- Vẽ đúng ranh giới giữa **define + link**, **initialize**, **find MethodHandle**, **first invocation** và **steady-state invocation**.
- Giải thích vì sao **không thể tách riêng chính xác chi phí linking chỉ bằng một lệnh System.nanoTime quanh defineHiddenClass**.
- Viết một chương trình Java 17+ tạo hidden class, chia các pha đo, làm nóng và kiểm tra kết quả.
- Nhận ra ảnh hưởng của **JIT, class loading, resolution, GC, phân bổ bộ nhớ, tối ưu hóa mã, bộ xử lý và phương pháp lấy mẫu**.
- Thiết kế benchmark đáng tin cậy hơn bằng **JMH** khi cần so sánh hiệu năng để ra quyết định.

Hidden class xuất hiện từ **Java 15** (JEP 371) và API này còn được sử dụng trong các bản Java hiện hành. Những công cụ dùng ở đây — **System.nanoTime()**, **MethodHandles.Lookup**, **MethodHandle.invokeExact()**, **Class.isHidden()**, **Lookup.ensureInitialized()** và **JMH** — không phụ thuộc các API legacy.

## 1. Hiểu đúng vòng đời trước khi đo

Xét một framework có bytecode của một lớp mẫu và muốn tạo hidden class rồi gọi một phương thức static:

~~~java
MethodHandles.Lookup hiddenLookup =
        ownerLookup.defineHiddenClass(classBytes, false);
Class<?> generated = hiddenLookup.lookupClass();

hiddenLookup.ensureInitialized(generated);

MethodHandle handler = hiddenLookup.findStatic(
        generated, "compute",
        MethodType.methodType(long.class, long.class));

long answer = (long) handler.invokeExact(3L);
~~~

Đây là **đoạn mã minh họa trong một phương thức**: ownerLookup phải có quyền định nghĩa hidden class, classBytes phải là class-file bytes hợp lệ và cùng package, các ngoại lệ/lỗi phải được xử lý. Chương trình đầy đủ ở mục 6.

Các pha trong ví dụ không tương đương nhau:

| Giai đoạn | Hoạt động đại diện | Chi phí có thể bao gồm |
| --- | --- | --- |
| Chuẩn bị đầu vào | Đọc/sinh **byte[] classBytes** | Đọc file, parse template, sinh bytecode, cấp phát byte[] |
| **Định nghĩa + liên kết** | **defineHiddenClass(bytes, false)** | Định nghĩa lớp mới, metadata, xác minh, chuẩn bị, phần liên kết mà JVM thực hiện |
| **Khởi tạo** | **ensureInitialized(generated)** | Khởi tạo class, thực thi **<clinit>** và hệ quả liên quan |
| **Tìm đường gọi** | **findStatic(...)** | Kiểm tra quyền, tìm member, tạo MethodHandle và một số công việc resolution |
| **Lần gọi đầu** | **invokeExact(...)** lần đầu | Đường gọi lạnh, khởi tạo hoặc resolution còn hoãn nếu chưa làm ở bước trước, thiết lập đường liên kết/call site |
| **Gọi sau warm-up** | Nhiều lần **invokeExact(...)** | Mã đã được thực thi đủ để JVM có cơ hội biên dịch JIT, inline và tối ưu |

**Ranh giới quan trọng:** theo tài liệu **defineHiddenClass**, lớp vừa tạo được JVM **linked** trước khi phương thức trả về. Đặt **initialize=false** chỉ tránh yêu cầu **khởi tạo ngay**, không biến defineHiddenClass thành một thao tác “chỉ lưu bytecode mà chưa liên kết”.

### Linked không có nghĩa tất cả tham chiếu đã được resolve

Theo *Java Virtual Machine Specification (JVMS)*, **linking** gồm **verification**, **preparation** và **resolution**. Tuy nhiên, JVM được phép chọn thời điểm giải quyết nhiều tham chiếu ký hiệu (symbolic references), miễn đáp ứng quy tắc của JVM; một số việc resolution có thể **được hoãn tới lúc dùng**.

Vì vậy:

- Thời gian **defineHiddenClass(...)** là **chi phí định nghĩa kèm phần linking thực hiện lúc đó**.
- Không thể kết luận rằng mọi lần resolve phương thức, lớp hoặc trường đã hoàn thành ngay sau define.
- Nếu một lời gọi đầu tiên chậm hơn lời gọi tiếp theo, **không được mặc nhiên quy toàn bộ chênh lệch cho JIT**: nó có thể liên quan resolution, thiết lập đường gọi, compiler và nhiều yếu tố khác.
- Muốn quan sát nội bộ chi tiết hơn cần dùng **JFR, logging/profiling hoặc công cụ JVM chuyên dụng**, thay vì trừ tùy tiện hai con số nanoTime.

## 2. Phân biệt định nghĩa, khởi tạo và gọi mã

### 2.1. Define + link khác với tạo instance

**defineHiddenClass(...)** trả về một **Lookup trên hidden class vừa định nghĩa**. Nó **không bắt buộc tạo đối tượng bằng constructor**. Nếu mã sau đó tạo instance, chi phí **new/constructor** là pha khác, cần đo riêng.

Với **ClassOption.NESTMATE**, **ClassOption.STRONG**, kích thước class file, bảng hằng và số phương thức khác nhau, chi phí có thể khác. Muốn so sánh công bằng, phải ghi lại **đúng cấu hình** và **đúng bytecode**.

Mỗi lần gọi **defineHiddenClass** thành công sẽ định nghĩa một **lớp runtime mới**, ngay cả khi dùng lại cùng byte[]. Do đó, benchmark định nghĩa lớp đo **khả năng tạo lớp mới**, không phải tra cứu một lớp đã có trong cache.

### 2.2. Khởi tạo là một pha riêng khi initialize=false

Lời gọi:

~~~java
MethodHandles.Lookup hidden = owner.defineHiddenClass(bytes, false);
hidden.ensureInitialized(hidden.lookupClass());
~~~

cho phép đo **pha định nghĩa + liên kết** và **pha khởi tạo** ở hai khoảng thời gian riêng biệt. **ensureInitialized** bảo đảm lớp đã được khởi tạo khi lời gọi thành công; nếu lớp đã khởi tạo thì thao tác không chạy lại **<clinit>**.

Nếu thay thành **defineHiddenClass(bytes, true)**, thời gian đo phương thức này có thể bao gồm **cả khởi tạo lớp**. Không lấy thời gian của trường hợp true để báo là “chỉ định nghĩa”, rồi lại cộng thêm một lần chi phí khởi tạo như thể các pha độc lập.

**Chi phí <clinit> có thể rất khác nhau:** nếu mã khởi tạo tạo cache, đọc cấu hình hoặc thực hiện công việc nặng, chính logic ấy có thể chiếm thời gian chủ yếu. Vì vậy một thí nghiệm đo class trống chưa đại diện cho lớp sinh động thực tế của ứng dụng.

### 2.3. Tìm MethodHandle không phải chi phí mỗi lần gọi

~~~java
MethodHandle mh = hidden.findStatic(
        hidden.lookupClass(),
        "compute",
        MethodType.methodType(long.class, long.class));
~~~

Chi phí tra cứu member, kiểm tra truy cập và tạo **MethodHandle** xảy ra ở lúc tìm handle. Trong đường chạy thường xuyên, hãy **tạo và tái sử dụng handle**, không gọi findStatic mỗi lần rồi khẳng định phần overhead đó là chi phí invokeExact.

Nếu dùng **reflection**, **interface dispatch**, **lambda** hoặc **MethodHandle** với một cấu hình khác, cần đo chúng trên **đường gọi thực tế của ứng dụng**. Đây là các chiến lược sử dụng khác nhau, không nhất thiết có kết quả ngang nhau.

### 2.4. Lần gọi đầu và lời gọi đã warm-up

Lời gọi đầu thường đi qua một số đường chưa nóng, có thể phải giải quyết tham chiếu hay thiết lập bộ máy gọi mã. Các lời gọi sau có thể giúp JVM **thu thập thông tin thực thi** và **JIT compile**. Sau khi warm-up đủ lâu, một đường gọi có thể được inline, làm cho con số ns/call phản ánh **mã máy tối ưu**, không đơn thuần là “mỗi lần gọi tốn bao nhiêu chu kỳ”.

Cũng không có định nghĩa toàn cục rằng **10.000** hay **200.000** lần gọi là luôn warm-up đủ. Số lần cần thiết phụ thuộc phương thức, nhánh thực thi, trình biên dịch JIT, phiên bản JVM, tùy chọn chạy và tải hệ thống.

## 3. Xác định rõ đại lượng cần đo

Trước khi viết benchmark, trả lời ba câu hỏi:

1. **Ứng dụng sinh bao nhiêu lớp mới?** Một lớp mỗi yêu cầu, mỗi biểu thức, mỗi tenant hay mỗi lần khởi động? Nếu sinh thường xuyên, **define + link**, khởi tạo, metadata và GC class có thể là chi phí quan trọng.
2. **Mỗi lớp được gọi bao nhiêu lần?** Nếu một lớp chỉ chạy một lần, startup/first-call có thể lớn hơn nhiều so với công việc hữu ích. Nếu một lớp được gọi hàng triệu lần, **throughput và latency sau warm-up** quan trọng hơn.
3. **Cần tối ưu thời gian hay bộ nhớ?** Sinh nhiều hidden class có thể làm tăng metadata/metaspace và chi phí GC, ngay cả khi steady-state invocation khá nhanh.

Các chỉ số nên tách thành:

| Nhóm đo | Chỉ số đề xuất | Tránh kết luận sai |
| --- | --- | --- |
| Sinh lớp | **ns/class** hoặc **classes/s**, đo nhiều lớp mới | Không đo lại trên cùng Class rồi gọi đó là định nghĩa lớp |
| Khởi tạo | **ns/initialization** trên lớp mới có initialize=false | Không đo ensureInitialized lần thứ hai trên cùng lớp |
| Tìm handle | **ns/lookup** sau khi biết lớp | Không trộn findStatic vào mỗi invoke nếu hệ thống cache handle |
| Cold invocation | **Thời gian lần đầu** trên lớp mới | Không đánh đồng với steady state |
| Warm invocation | **ns/op**, **ops/s** | Không suy ra từ một lần gọi đơn lẻ |
| Tác động hệ thống | **Metaspace/heap, allocation, GC, class unload, p95/p99** | Không chỉ nhìn một số trung bình thấp |

**Không có giá trị ns/op phổ quát** cho hidden class hoặc MethodHandle. Con số phụ thuộc JVM, CPU, mã sinh, cách gọi và khối lượng công việc. Benchmark phải đo **chính workload cần tối ưu**.

## 4. Trình tự đo tách pha

Một quy trình thực hành hợp lý cho đo thăm dò:

1. **Tạo bytes trước khi bắt đầu đồng hồ đo định nghĩa.** Đọc file class hoặc sinh bytecode trong pha riêng; nếu gộp sẽ không biết chi phí nằm ở bước nào.
2. **Làm nóng đường đo:** gọi thử API tạo lớp, khởi tạo và gọi code trên các lớp thử, không tính kết quả vào số đo chính. Với so sánh giữa các cách làm, giữ quy trình warm-up tương đương.
3. **Định nghĩa một hidden class mới** bằng **defineHiddenClass(bytes, false)**; đo thời gian quanh lời gọi. Ghi nhãn **define + link**, không nhãn linking thuần túy.
4. **Khởi tạo chính lớp vừa định nghĩa** bằng **ensureInitialized**; đo riêng nếu ứng dụng thực tế thực hiện bước này.
5. **Tìm MethodHandle** bằng lookup trả về từ defineHiddenClass; đo riêng thao tác tìm.
6. **Đo first invocation** của handle này. Kết quả là một mẫu cold call, dễ nhiễu.
7. **Warm-up chính handle** bằng nhiều lần gọi với dữ liệu thay đổi, giữ kết quả có tác dụng quan sát được để compiler không xóa phép tính.
8. **Đo một loạt lời gọi** và chia thời gian tổng cho số phép gọi. Nếu thao tác quá ngắn, cần số lượng đủ lớn để chi phí đọc đồng hồ không chi phối.
9. **Lặp nhiều vòng và nhiều JVM fork**, lấy phân bố mẫu; thử nhiều bộ dữ liệu, class sizes và điều kiện tải để phản ánh môi trường triển khai.

Trong mã học tập ở mục 6, các bước này được thực hiện để **minh họa ranh giới**, không tạo ra một microbenchmark đủ độ tin cậy cho production.

## 5. Vì sao nanoTime cần thận trọng?

**System.nanoTime()** thích hợp đo **khoảng thời gian tương đối** trong cùng JVM. Nó **không phải** đồng hồ thời gian thực để gắn mốc lịch, và một độ chênh nanosecond **không bảo đảm độ chính xác ở cấp một nano giây**.

Các nguồn nhiễu thường gặp:

- **JIT warm-up:** JVM có thể thông dịch, biên dịch tầng thấp rồi tối ưu mạnh hơn; diễn biến làm thời gian các vòng đo thay đổi.
- **Dead-code elimination và constant folding:** nếu kết quả không được sử dụng, trình biên dịch có thể giảm hoặc xóa phép tính; dùng checksum/Blackhole phù hợp.
- **Inlining:** sau warm-up, MethodHandle hoặc phương thức đích có thể được tối ưu vào đường gọi; lúc ấy “chi phí gọi độc lập” có thể không còn là khái niệm chính xác.
- **GC và class unloading:** định nghĩa nhiều lớp mới tạo áp lực metadata; lần GC xen giữa mẫu có thể tạo outlier.
- **CPU scheduling, frequency scaling, tải nền:** khi CPU thay đổi xung hoặc thread bị ngắt, một phép đo ngắn có thể méo mạnh.
- **Phân bổ và I/O:** nếu mở file, tạo byte[] hoặc in console bên trong thời gian đo, kết quả sẽ bao gồm những thao tác đó.
- **Chênh lệch phiên bản/flags JVM:** Java 17, 21, 25 và các bản cập nhật JVM có thể tối ưu khác nhau. Không so sánh số đo từ hai máy mà không ghi rõ môi trường.

Nếu phương thức có nhiều nhánh hoặc dữ liệu phụ thuộc đầu vào, dùng mẫu đầu vào đại diện. Warm-up với một giá trị nhưng đo toàn giá trị khác có thể khiến compiler phải biên dịch lại hoặc đổi đường tối ưu.

## 6. Ví dụ Java 17+ hoàn chỉnh

Chương trình sau có một lớp mẫu **Template** với phương thức static **compute(long)**. Nó đọc class file đã biên dịch, tạo hidden class từ bytes, tách thời gian **define+link**, **initialize**, **find MethodHandle**, **first invokeExact**, sau đó warm-up chính MethodHandle và đo **một triệu lần gọi**.

Mọi lần tìm class file diễn ra **trước** khoảng đo định nghĩa. Một biến **volatile** giữ kết quả checksum để hạn chế việc phép tính bị coi là không có tác dụng. Tuy nhiên, compiler vẫn có thể **inline và tối ưu** đường chạy; đây là minh họa thời gian một đoạn công việc, **không phải phép đo overhead thuần của invokeExact**.

Lưu toàn bộ mã dưới đây thành **HiddenClassTimingDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassTimingDemo {
    public static class Template {
        private static long factor = 7;

        public static long compute(long x) {
            return x * 31 + factor;
        }
    }

    private static volatile long resultSink;

    private static byte[] readBytes() throws IOException {
        try (InputStream in = HiddenClassTimingDemo.class
                .getResourceAsStream("HiddenClassTimingDemo$Template.class")) {
            if (in == null) {
                throw new IOException("Không tìm thấy Template.class");
            }
            return in.readAllBytes();
        }
    }

    private static MethodHandle findCompute(MethodHandles.Lookup lookup)
            throws ReflectiveOperationException {
        return lookup.findStatic(lookup.lookupClass(),
                "compute", MethodType.methodType(long.class, long.class));
    }

    private static long invokeMany(MethodHandle mh, int count) throws Throwable {
        long sum = 0;
        for (int i = 0; i < count; i++) {
            sum += (long) mh.invokeExact((long) i);
        }
        return sum;
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = readBytes();
        MethodHandles.Lookup owner = MethodHandles.lookup();

        // Làm nóng các đường định nghĩa, khởi tạo và gọi, không tính vào số đo.
        for (int i = 0; i < 100; i++) {
            MethodHandles.Lookup warm = owner.defineHiddenClass(bytes, false);
            warm.ensureInitialized(warm.lookupClass());
            MethodHandle warmHandle = findCompute(warm);
            resultSink ^= (long) warmHandle.invokeExact((long) i);
        }

        long start = System.nanoTime();
        MethodHandles.Lookup hidden = owner.defineHiddenClass(bytes, false);
        long defineAndLinkNs = System.nanoTime() - start;

        start = System.nanoTime();
        hidden.ensureInitialized(hidden.lookupClass());
        long initNs = System.nanoTime() - start;

        start = System.nanoTime();
        MethodHandle mh = findCompute(hidden);
        long findNs = System.nanoTime() - start;

        start = System.nanoTime();
        long first = (long) mh.invokeExact(3L);
        long firstCallNs = System.nanoTime() - start;

        resultSink ^= invokeMany(mh, 200_000); // Làm nóng đường gọi này.
        start = System.nanoTime();
        long checksum = invokeMany(mh, 1_000_000);
        long steadyNs = System.nanoTime() - start;
        resultSink ^= checksum;

        System.out.println("isHidden: " + hidden.lookupClass().isHidden());
        System.out.println("First value: " + first);
        System.out.println("Checksum: " + checksum);
        System.out.println("Các giai đoạn đo đều có kết quả nano giây >= 0: "
                + (defineAndLinkNs >= 0 && initNs >= 0 && findNs >= 0
                && firstCallNs >= 0 && steadyNs >= 0));
        System.out.printf("Define + link (ns): %d%n", defineAndLinkNs);
        System.out.printf("Initialize (ns): %d%n", initNs);
        System.out.printf("Find MethodHandle (ns): %d%n", findNs);
        System.out.printf("First call (ns): %d%n", firstCallNs);
        System.out.printf("After warm-up, %d calls (ns): %d%n",
                1_000_000, steadyNs);
        System.out.printf("Average measured ns/call: %.3f%n",
                steadyNs / 1_000_000.0);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**, trong thư mục chứa **HiddenClassTimingDemo.java**:

~~~bash
javac --release 17 -encoding UTF-8 HiddenClassTimingDemo.java
java HiddenClassTimingDemo
~~~

**Một lần chạy thực tế trên JDK 24** sau khi biên dịch --release 17 cho stdout:

~~~text
isHidden: true
First value: 100
Checksum: 15499991500000
Các giai đoạn đo đều có kết quả nano giây >= 0: true
Define + link (ns): 27300
Initialize (ns): 1700
Find MethodHandle (ns): 10300
First call (ns): 1000
After warm-up, 1000000 calls (ns): 1930600
Average measured ns/call: 1.931
~~~

**Lưu ý bắt buộc khi đọc output:** Bốn dòng đầu là kết quả kiểm tra logic trong lần chạy này; **các số thời gian nano giây và ns/call ở những dòng sau thay đổi theo máy, JVM, lần chạy và môi trường**. Những con số trên **chỉ là minh họa có thật từ một lần chạy**, tuyệt đối không phải số chuẩn cho hidden class hoặc cam kết chạy lại sẽ nhận cùng kết quả.

### Phân tích kết quả

- **isHidden: true:** API đã định nghĩa một hidden class, không gọi lại lớp Template thông thường.
- **First value: 100:** phương thức compute(3) trả **3 × 31 + 7 = 100**.
- **Checksum: 15499991500000:** tổng của các kết quả **compute(i)** với i từ 0 tới 999.999; kết quả giúp xác nhận phép tính thực sự được sử dụng.
- **Define + link:** đồng hồ bao quanh một lời gọi defineHiddenClass trên **bytes có sẵn**, chưa yêu cầu khởi tạo.
- **Initialize:** thời gian quanh **ensureInitialized** của lớp vừa tạo. Nó không đo đọc bytes hay mọi chi phí linking đã xảy ra.
- **Find MethodHandle:** đo hoạt động tìm method static theo kiểu **(long)long** trên lớp ẩn.
- **First call:** đo riêng lần invokeExact đầu của handle, khi đường gọi chưa được warm-up theo chính handle đó.
- **After warm-up:** đo 1.000.000 lần invokeExact sau 200.000 lần gọi warm-up trên **cùng handle**. Kết quả đo bao gồm overhead vòng lặp, tính toán bên trong compute và bất kỳ tối ưu hóa JIT nào.
- **Average measured ns/call:** chỉ là **steadyNs / số lần lặp** trong demo này. **Không được diễn giải đó là “overhead cố hữu của MethodHandle.invokeExact()”** hoặc số thời gian hoàn toàn tách biệt với code được gọi.

Tệp **HiddenClassTimingDemo$Template.class** do javac sinh ra từ nested class có tên. getResourceAsStream tìm resource ấy trong cùng package với lớp chủ; cả hai cùng package nên điều kiện của defineHiddenClass được đáp ứng. Không có tính năng preview hoặc thư viện bên ngoài.

## 7. Biến bản demo thành benchmark đáng tin cậy

Mã thăm dò dùng nanoTime là công cụ **học cách phân pha**. Nếu cần so sánh thiết kế, sử dụng **OpenJDK JMH (Java Microbenchmark Harness)**, vì JMH hỗ trợ warm-up, measurement iterations, fork, kết quả thống kê và cơ chế hạn chế nhiều sai lệch thường gặp.

### Thiết kế hai nhóm benchmark riêng

**Nhóm A — chi phí tạo lớp mới:**

- Chuẩn bị **byte[]**, **Lookup** và thông tin cấu hình trong setup, không đọc file từ disk bên trong một phép đo.
- Mỗi phép đo gọi **defineHiddenClass(bytes, false)** để sinh **Class mới**.
- Giữ lại kết quả theo cách benchmark không bị tối ưu bỏ, đồng thời quản lý số lớp sinh ra và tài nguyên trong mỗi phép thử.
- Đo **throughput/latency** của việc định nghĩa mới theo đúng chính sách NESTMATE/STRONG/khởi tạo mà ứng dụng dùng.
- Theo dõi **GC, class unloading, metaspace và OOME**; các lớp sinh ra không phải dữ liệu miễn phí.
- Nếu ứng dụng sinh mã bytecode tại runtime, đo **bước sinh bytes** ở một benchmark riêng hoặc đo end-to-end có gắn nhãn rõ ràng.

**Nhóm B — chi phí gọi lớp đã tạo:**

- Định nghĩa lớp, khởi tạo và tìm **MethodHandle** trong bước setup, không làm lại mỗi operation.
- Benchmark chỉ **gọi phương thức** trên một handle đã lưu, với dữ liệu đầu vào đủ đa dạng và kết quả được tiêu thụ bằng **JMH Blackhole** hoặc giá trị trả về.
- Thử **direct call**, **interface dispatch**, **MethodHandle** hay cách gọi thực tế khác nếu đó là các phương án kiến trúc cần so sánh.
- Dùng **JMH warm-up iterations**, **measurement iterations** và **nhiều JVM forks**; không chỉ một lần chạy trong IDE.
- Tách riêng benchmark đường gọi **cold** nếu nhu cầu thực tế là “mỗi generated class chỉ được gọi một lần”.

**Không đặt defineHiddenClass trong cùng một @Benchmark với invocation** rồi lấy thời gian trung bình tổng để kết luận chi phí mỗi lời gọi warm. Nếu nghiệp vụ thực sự vừa sinh vừa gọi đúng một lần, đo end-to-end cũng cần thiết, nhưng phải **đặt tên và diễn giải là end-to-end**.

### Chọn chế độ đo JMH

- **AverageTime**: trung bình thời gian trên operation, thích hợp so sánh một đơn vị công việc.
- **Throughput**: số operation trên một đơn vị thời gian.
- **SampleTime**: phân bố mẫu thời gian, hữu ích khi quan tâm tới độ trễ.
- **SingleShotTime**: có thể dùng để khảo sát một operation lớn hoặc một tình huống lạnh, nhưng cần setup/fork hợp lý để tránh ngộ nhận về steady state.

Đối với thao tác **định nghĩa lớp**, benchmark cần cân nhắc số lượng class mới được tạo và việc chúng còn được giữ hay có thể unload. Đối với thao tác **gọi mã nóng**, JIT có thể tối ưu mạnh; nên dùng workload đủ thực tế để kết quả có giá trị áp dụng.

JMH không tự thay thế thiết kế thí nghiệm tốt. Đặt **@State** đúng phạm vi, **@Setup** đúng giai đoạn, giữ dữ liệu đầu vào hợp lệ, và tránh đo cùng một bộ dữ liệu đến mức compiler đơn giản hóa công việc ngoài dự kiến. Tham khảo mẫu chính thức của dự án OpenJDK JMH thay vì tự tạo “nanosecond benchmark” bằng một vòng lặp ngắn.

## 8. Quan sát JVM ngoài đồng hồ đo

Khi có chênh lệch đáng kể, đừng lập tức sửa code để “tối ưu”; cần biết chi phí phát sinh ở đâu:

- **Java Flight Recorder (JFR)**: thu sự kiện về thực thi JVM, GC, compilation/class loading nếu môi trường và cấu hình ghi cho phép. Dùng JFR để đối chiếu những bất thường thay vì chỉ nhìn số ns tổng.
- **JVM unified logging**: quan sát class load/unload và các hoạt động JVM khi bật log phù hợp, ví dụ **-Xlog:class+load=info,class+unload=info** trên HotSpot. Bật logging có overhead; đo có log và đo thông thường là hai điều kiện khác nhau.
- **GC/metaspace metrics**: số lớp sinh ra, heap, metaspace, số lần GC và class unloading. Đây là dữ liệu bắt buộc khi hệ thống tạo nhiều hidden class.
- **Profiler hoặc công cụ cấp JVM**: dùng khi cần xem JIT compilation, CPU hotspots hoặc allocation; không thể trích một con số “linking thuần túy” đáng tin chỉ bằng cách trừ defineNs khỏi firstCallNs.

Một chương trình có thể có **ns/call rất thấp** nhưng vẫn kém hiệu quả tổng thể nếu phải tạo nhiều class mới, dùng nhiều bộ nhớ metadata hoặc làm GC liên tục. Chỉ so sánh khi **cùng định nghĩa workload**, cùng phiên bản/runtime và cùng yêu cầu về tính đúng đắn.

## 9. Nguyên tắc ra quyết định kiến trúc

Giả sử framework có hai phương án:

- **Phương án 1:** sinh hidden class mới cho mỗi biểu thức và gọi một lần.
- **Phương án 2:** cache generated class/MethodHandle theo một khóa nghiệp vụ, sau đó tái sử dụng khi có cùng biểu thức.

Nếu mỗi class chỉ được gọi ít lần, chi phí định nghĩa và khởi tạo có thể chiếm tỷ trọng cao; cache có thể giảm startup cost. Nhưng cache giữ mạnh Class/MethodHandle/instance **cũng có thể kéo dài vòng đời hidden class** và tăng chi phí bộ nhớ. Cần đo **hit rate, latency, p95/p99, kích thước cache, class unloading và tổng tải** trước khi chọn.

Nếu mỗi class chạy rất nhiều lần, steady-state invocation và hiệu quả tối ưu JIT có thể quan trọng hơn chi phí định nghĩa ban đầu. Tuy nhiên, tối ưu chỉ có ý nghĩa khi **mã sinh thực hiện cùng công việc** và kết quả đúng trong mọi trường hợp biên.

**Không có kết luận sẵn** rằng hidden class luôn nhanh hơn lớp thông thường, anonymous class, lambda hoặc reflection. Hidden class là cơ chế **định nghĩa lớp runtime**, không phải cam kết hiệu năng tự động.

## 10. Lỗi thường gặp

1. **Gọi defineHiddenClass(..., false) là “chưa liên kết”.** Sai. Lớp đã được linked; false chỉ không yêu cầu khởi tạo ngay.
2. **Gọi thời gian defineHiddenClass là chi phí linking đơn lẻ.** Sai. Khoảng này bao gồm định nghĩa và linking diễn ra trong lời gọi.
3. **Đo initialize=true rồi cộng thêm chi phí <clinit>** như thể chưa chạy. Có thể đếm trùng khởi tạo.
4. **Đo một lần invokeExact rồi gọi đó là ns/op sau warm-up.** Sai. First call có các chi phí lạnh và nhiều nguồn nhiễu.
5. **Để readAllBytes() hoặc sinh bytecode trong đoạn đo define mà không gắn nhãn.** Số đo khi ấy gồm cả chuẩn bị dữ liệu.
6. **Gọi findStatic ở từng vòng rồi báo chi phí chỉ của invokeExact.** Đo như vậy có chi phí tìm handle và kiểm tra quyền lặp lại.
7. **Tái sử dụng cùng Class object để benchmark “định nghĩa nhiều lớp”.** Không có định nghĩa lớp mới khi chỉ tái dùng Class đã có.
8. **Cho rằng warm-up 200.000 lần luôn đủ.** Con số ví dụ không là ngưỡng JVM bảo đảm; phải kiểm tra sự ổn định với workflow thực tế.
9. **Không tiêu thụ kết quả phép tính.** JIT có thể đơn giản hóa hoặc xóa công việc, khiến kết quả không đại diện.
10. **Thấy 1–2 ns/call rồi khẳng định đó là overhead máy ảo cố định.** Code có thể được inline/tối ưu; kết quả gồm workload/vòng lặp và có sai lệch đo.
11. **Không đo GC/metaspace khi sinh hàng triệu lớp.** Hidden class có chi phí metadata, không chỉ CPU.
12. **So sánh hai kết quả đo khác JVM, CPU, warm-up hoặc workload.** Các kết luận khi đó không đáng tin.
13. **Giữ STRONG hoặc cache vô hạn mà không theo dõi vòng đời.** Tạo hidden class có thể unload độc lập theo mặc định, nhưng strong references và STRONG có thể khiến lớp tồn tại lâu hơn.
14. **Bắt mọi lỗi liên kết rồi tiếp tục benchmark như không có chuyện gì.** Nếu bytes không hợp lệ hoặc lỗi truy cập, benchmark không còn đo cùng công việc.
15. **In ra console trong vòng lặp đo.** Thời gian I/O chi phối kết quả và làm sai lệch latency invocation.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Khi defineHiddenClass(bytes, false) trả về, hidden class đã được linked chưa?  
**Đáp án:** Đã linked theo hợp đồng API. Nó chưa được yêu cầu khởi tạo, và một số resolution khác có thể xảy ra khi dùng sau đó.

**Câu 2.** Muốn đo chi phí khởi tạo riêng sau defineHiddenClass(bytes, false), dùng API nào?  
**Đáp án:** **Lookup.ensureInitialized(Class<?>)** trên hidden class vừa được tạo, với Lookup có quyền thích hợp.

**Câu 3.** Thời gian một triệu lần invokeExact sau warm-up có biểu diễn “overhead thuần của MethodHandle” không?  
**Đáp án:** Không. Nó bao gồm code đích, vòng lặp và tác động tối ưu JIT; có thể đã được inline.

**Câu 4.** Một framework sinh 10.000 hidden class nhưng mỗi lớp chỉ chạy một lần nên tập trung đo gì?  
**Đáp án:** **define+link, initialization, first-call, allocation, GC/metaspace và latency end-to-end**; steady-state ns/call riêng không đủ phản ánh tải.

**Câu 5.** Công cụ nào được OpenJDK cung cấp để thiết kế microbenchmark có warm-up, fork và thống kê?  
**Đáp án:** **JMH (Java Microbenchmark Harness)**.

## 12. Ghi nhớ

**Tách các pha trước khi tối ưu.** defineHiddenClass là **định nghĩa + liên kết**; **initialize=false** cho phép đo khởi tạo riêng. Tìm MethodHandle, lần gọi đầu và gọi sau warm-up cũng phải được đo hoặc mô tả riêng. **System.nanoTime giúp quan sát cơ bản**, nhưng không đủ chứng minh kết luận hiệu năng vi mô. Với quyết định kỹ thuật, dùng **JMH**, đo nhiều lần và nhiều fork, kiểm tra số liệu **GC/metaspace**, ghi rõ cấu hình và tải thực tế.

## Tham khảo chính thức

- Oracle, **MethodHandles.Lookup.defineHiddenClass / ensureInitialized**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle, **JVMS §5.4 Linking, §5.5 Initialization**, Java SE 25: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html
- OpenJDK, **JEP 371 – Hidden Classes**: https://openjdk.org/jeps/371
- OpenJDK, **Java Microbenchmark Harness (JMH)**: https://github.com/openjdk/jmh
