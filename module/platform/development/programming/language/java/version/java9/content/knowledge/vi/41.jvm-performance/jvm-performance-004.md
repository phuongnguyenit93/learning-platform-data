# Code cache phân đoạn theo loại mã biên dịch trong HotSpot

## 1. Code cache là gì?

Code cache là vùng bộ nhớ native của HotSpot JVM dùng để lưu các CodeBlob do VM tạo ra, trong đó có mã máy được JIT compiler sinh ra cho Java method. Một method sau khi được biên dịch có thể được biểu diễn bằng nmethod và được cài vào code cache để CPU thực thi trực tiếp.

Code cache khác với Java heap và Metaspace:

- Java heap chứa object của ứng dụng.
- Metaspace chứa metadata của class.
- Code cache chứa mã máy đã biên dịch và một số mã nội bộ của VM như runtime stubs, adapters và compiler buffers.

Code cache được quản lý như vùng nhớ riêng của VM. Dung lượng của nó không được tính bằng -Xmx. Một ứng dụng có thể còn nhiều Java heap nhưng vẫn gặp áp lực code cache nếu có quá nhiều mã được JIT biên dịch.

## 2. Vấn đề của một code cache không phân đoạn

Trước Java 9, HotSpot sử dụng một code heap chung cho nhiều loại mã. Những loại mã có vòng đời khác nhau cùng chiếm chỗ trong một vùng:

- Mã nội bộ của VM thường tồn tại trong suốt vòng đời JVM.
- Mã được biên dịch kèm dữ liệu profiling có thể ngắn hạn và được biên dịch lại ở tier cao hơn.
- Mã đã tối ưu và ổn định thường có vòng đời dài hơn.

Khi các loại mã này xen kẽ trong cùng một heap, việc thu hồi những block đã hết sử dụng có thể để lại các khoảng trống rời rạc. Tổng dung lượng trống có thể còn nhiều nhưng một số yêu cầu cấp phát vẫn khó tìm được block liên tục đủ lớn. Đây là phân mảnh bên ngoài của code cache.

Một heap chung cũng khiến VM phải quét nhiều mã không liên quan khi tìm kiếm, quản lý hoặc thu hồi code. JEP 197 giải quyết bài toán này bằng cách tách code cache thành các heap theo loại code.

## 3. Segmented Code Cache từ Java 9

JEP 197 giới thiệu Segmented Code Cache trong HotSpot từ Java 9. Thay vì đặt mọi CodeBlob vào một heap, JVM chia vùng code cache thành các segment có mục đích khác nhau.

Thiết kế ba heap cơ bản:

~~~text
Code cache
|
+-- Non-method code heap
|   +-- VM stubs, adapters, compiler buffers, interpreter code
|
+-- Profiled nmethods heap
|   +-- JIT methods có dữ liệu profiling
|
+-- Non-profiled nmethods heap
    +-- JIT methods không lưu profiling data
    +-- Native method wrappers
~~~

Các heap là những vùng riêng trong phần code cache đã được reserve. Chúng được bố trí cạnh nhau trong vùng nhớ liên tục, nhưng quản lý cấp phát và vòng đời code theo từng loại.

Phân đoạn không thay đổi bytecode, Java language semantics hay API công khai. Đây là cơ chế quản lý mã máy bên trong HotSpot; JVM implementation khác có thể có cách quản lý code cache riêng.

## 4. Ba loại code heap

| Heap | Nội dung | Đặc điểm vòng đời |
|---|---|---|
| Non-method | Runtime stubs, adapters, compiler buffers và mã nội bộ của VM | Thường tồn tại suốt vòng đời JVM |
| Profiled nmethods | Method đã biên dịch có dữ liệu profiling | Có thể ngắn hạn, được biên dịch lại khi profile tích lũy thêm |
| Non-profiled nmethods | Method đã biên dịch không giữ profiling data, gồm mã ở một số tier và native wrappers | Thường ổn định và có vòng đời dài hơn |

### Non-method code heap

Heap này chứa code không đại diện cho một Java method được JIT biên dịch. Ví dụ:

- Runtime stubs phục vụ các thao tác nội bộ của VM.
- Adapters dùng để chuyển đổi giữa các calling convention hoặc method handle signature.
- Compiler buffers và một số đoạn mã nội bộ khác.
- Bytecode interpreter code theo cách phân loại của HotSpot.

Non-method code không được thu hồi theo cách giống các nmethod thông thường. Tài liệu Oracle HotSpot mô tả loại code này tồn tại trong code cache suốt vòng đời JVM. Vì vậy, heap này cần đủ dung lượng để VM vận hành.

### Profiled nmethods heap

Heap này chứa các method đã biên dịch nhưng vẫn giữ thông tin profiling, chẳng hạn invocation counters, branch counters hoặc type profile.

Trong tiered compilation, C1 có thể tạo mã để thu thập thêm thông tin về cách method được sử dụng. Những dữ liệu đó giúp JVM quyết định liệu method có cần được biên dịch lại ở tier khác hoặc tối ưu mạnh hơn hay không.

Mã có profiling thường có vòng đời ngắn hơn: một phiên bản có thể trở nên không còn cần thiết khi method được biên dịch lại hoặc deoptimize.

### Non-profiled nmethods heap

Heap này chứa các nmethod không mang profiling data. Chúng gồm:

- Code ở tier 1 của C1, vốn không giữ profiling data đầy đủ.
- Code ở tier 4 do C2 tối ưu.
- Một số native method wrappers.

Không nên hiểu heap này chỉ chứa C2. Tier 1 của C1 cũng thuộc nhóm non-profiled theo cách phân loại của HotSpot.

Các method đã tối ưu có thể vẫn bị deoptimize nếu giả định của compiler không còn đúng. Khi phiên bản code cũ không còn được sử dụng, sweeper có thể thu hồi nó theo quy trình an toàn của VM.

## 5. Quan hệ với Tiered Compilation

Tiered compilation có thể biên dịch cùng một method nhiều lần khi JVM thu thập thêm thông tin về workload. Trong cấu hình HotSpot phổ biến, các tier có quan hệ với ba heap như sau:

| Tier | Thành phần | Vai trò | Heap |
|---:|---|---|---|
| 0 | Interpreter | Thực thi bytecode và thu thập counter ban đầu | Không phải nmethod heap |
| 1 | C1 | Biên dịch nhanh, không giữ profiling data đầy đủ | Non-profiled |
| 2 | C1 | Biên dịch có profiling | Profiled |
| 3 | C1 | Biên dịch với profiling đầy đủ hơn | Profiled |
| 4 | C2 | Biên dịch tối ưu dựa trên thông tin đã thu thập | Non-profiled |

Một luồng điển hình:

1. Method bắt đầu chạy trong interpreter ở tier 0.
2. Khi đủ nóng, C1 có thể biên dịch method ở tier 1 để giảm chi phí thực thi.
3. JVM tiếp tục thu thập thông tin và có thể tạo phiên bản profiled ở tier 2 hoặc tier 3.
4. Khi có đủ dữ liệu, C2 có thể biên dịch phiên bản tối ưu ở tier 4.
5. Phiên bản cũ có thể trở thành not entrant và được thu hồi khi không còn frame nào đang sử dụng.

Đây là cách phân loại phổ biến của HotSpot; chính sách tier và compiler có thể thay đổi theo runtime, kiến trúc, compiler được bật và các cờ JVM. Không nên xem tier là một hợp đồng của Java language.

## 6. Vì sao tách heap giúp ích?

### Giảm phân mảnh giữa các loại code

Mã ngắn hạn có profiling không còn xen kẽ trực tiếp với mã dài hạn và mã nội bộ của VM. Việc cấp phát và thu hồi trong từng heap có thể diễn ra độc lập hơn, giảm phân mảnh giữa các nhóm có vòng đời khác nhau.

### Rút ngắn thời gian quét

Một số thao tác quản lý code chỉ cần quan tâm tới một loại CodeBlob. Heap được tách giúp VM quét vùng liên quan thay vì phải xử lý toàn bộ code cache chung.

### Cải thiện locality của instruction

Các code có tính chất tương tự nằm gần nhau hơn. Điều này có thể cải thiện locality đối với instruction cache và instruction translation lookaside buffer (iTLB), tùy workload và kiến trúc CPU.

### Quản lý footprint rõ ràng hơn

Mỗi loại code có ngân sách riêng. Người vận hành có thể quan sát heap nào đang tăng nhanh và điều chỉnh dung lượng phù hợp hơn.

Phân đoạn không tự làm ứng dụng nhanh hơn trong mọi trường hợp. Nó cải thiện cách VM bố trí và quản lý mã máy; kết quả thực tế phụ thuộc số lượng method được biên dịch, vòng đời code, workload và kích thước từng heap.

## 7. Dung lượng từng heap và các cờ HotSpot hiện hành

Các cờ chính được tài liệu HotSpot hiện hành công bố:

| Cờ | Ý nghĩa |
|---|---|
| -XX:+SegmentedCodeCache | Bật code cache phân đoạn |
| -XX:-SegmentedCodeCache | Tắt phân đoạn, dùng một heap chung |
| -XX:ReservedCodeCacheSize=size | Giới hạn tổng dung lượng code cache |
| -XX:NonNMethodCodeHeapSize=size | Dung lượng heap non-method |
| -XX:ProfiledCodeHeapSize=size | Dung lượng heap profiled nmethods |
| -XX:NonProfiledCodeHeapSize=size | Dung lượng heap non-profiled nmethods |
| -XX:InitialCodeCacheSize=size | Dung lượng code cache khởi tạo ban đầu |
| -XX:+UseCodeCacheFlushing | Cho phép cơ chế flushing code cache; mặc định bật trên HotSpot hiện hành |
| -XX:StartAggressiveSweepingAt=percent | Ngưỡng phần trăm dung lượng trống để bắt đầu sweeping mạnh hơn |

Các cờ trên là tùy chọn riêng của HotSpot, không phải tùy chọn bắt buộc của mọi JVM.

Khi tiered compilation bật và ReservedCodeCacheSize đạt ít nhất 240 MB, tài liệu HotSpot hiện hành mô tả SegmentedCodeCache được bật mặc định. Giá trị mặc định thực tế vẫn phụ thuộc JDK build, kiến trúc và ergonomic decisions của VM; hãy kiểm tra runtime đang chạy thay vì giả định một con số chung.

Các heap được xác định dung lượng khi JVM khởi động và không tự thay đổi kích thước trong runtime theo mô tả của HotSpot hiện hành. Vì vậy, phân bổ quá nhiều cho heap ít sử dụng có thể để lãng phí vùng nhớ trong khi heap khác bị thiếu chỗ.

Tên cờ đúng là NonNMethodCodeHeapSize. Không nhầm với NonMethodCodeHeapSize trong một số tài liệu cũ hoặc bản mô tả không chính xác.

## 8. Ví dụ cấu hình code cache

Ví dụ cấu hình tổng code cache 384 MB:

~~~bash
java -XX:+SegmentedCodeCache -XX:ReservedCodeCacheSize=384m -XX:NonNMethodCodeHeapSize=8m -XX:ProfiledCodeHeapSize=128m -XX:NonProfiledCodeHeapSize=248m -jar application.jar
~~~

Trong ví dụ:

- Tổng ngân sách: 384 MB.
- Non-method: 8 MB.
- Profiled: 128 MB.
- Non-profiled: 248 MB.

Tổng các heap khớp với ReservedCodeCacheSize. Cấu hình này chỉ minh họa cú pháp; không nên sao chép kích thước vào production khi chưa đo workload.

Trước khi thay đổi, kiểm tra các giá trị ergonomic mà JVM đã chọn:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Tìm các flag:

~~~text
SegmentedCodeCache
ReservedCodeCacheSize
InitialCodeCacheSize
NonNMethodCodeHeapSize
ProfiledCodeHeapSize
NonProfiledCodeHeapSize
UseCodeCacheFlushing
~~~

Trên PowerShell có thể lọc trực tiếp:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "SegmentedCodeCache|ReservedCodeCacheSize|InitialCodeCacheSize|NonNMethodCodeHeapSize|ProfiledCodeHeapSize|NonProfiledCodeHeapSize|UseCodeCacheFlushing"
~~~

Không đặt heap size thấp hơn nhu cầu thật của code type tương ứng. Nếu một heap đầy trong khi heap khác còn nhiều chỗ trống, phân vùng cố định có thể khiến code cache gặp áp lực dù tổng vùng nhớ chưa sử dụng hết.

## 9. Quan sát code cache và các heap

### Xem các memory pool qua MXBeans

HotSpot công bố các code heap dưới dạng MemoryPoolMXBean. Có thể dùng ManagementFactory để quan sát tên và mức sử dụng:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryType;

public class CodeHeapNamesDemo {
    public static void main(String[] args) {
        ManagementFactory.getMemoryPoolMXBeans().stream()
                .filter(pool -> pool.getType() == MemoryType.NON_HEAP)
                .filter(pool -> pool.getName().startsWith("CodeHeap "))
                .map(pool -> pool.getName())
                .sorted()
                .forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:all CodeHeapNamesDemo.java
java -XX:+SegmentedCodeCache -XX:ReservedCodeCacheSize=240m CodeHeapNamesDemo
~~~

Output trên HotSpot có segmented code cache:

~~~text
CodeHeap 'non-nmethods'
CodeHeap 'non-profiled nmethods'
CodeHeap 'profiled nmethods'
~~~

Các tên CodeHeap là chi tiết của HotSpot, không phải tên pool được mọi JVM implementation bắt buộc phải cung cấp. Nếu cần số liệu, dùng pool.getUsage() để lấy used, committed và max; các giá trị thay đổi theo workload và thời điểm quan sát.

### Theo dõi hoạt động biên dịch

-XX:+PrintCompilation in thông tin khi method được biên dịch:

~~~bash
java -XX:+PrintCompilation -jar application.jar
~~~

Cờ này giúp thấy method nào được biên dịch và các lần biên dịch lại. Output có thể rất nhiều và phụ thuộc workload.

### Theo dõi code cache bằng Unified Logging

Dùng log tag codecache:

~~~bash
java -Xlog:codecache=Trace -jar application.jar
~~~

Trace cung cấp thông tin chi tiết về trạng thái code heap sau khi workload chạy. Khi cần điều tra tình huống code cache đầy, có thể dùng:

~~~bash
java -Xlog:codecache=Debug -jar application.jar
~~~

JDK 25 còn cung cấp phân tích trực tiếp code heap qua jcmd:

~~~bash
jcmd <pid> Compiler.CodeHeap_Analytics
~~~

Lệnh này phân tích trạng thái heap của JVM đang chạy. Cần thay <pid> bằng process ID thực tế và dùng jcmd cùng JDK tương thích với JVM mục tiêu.

## 10. Điều gì xảy ra khi code cache đầy?

Khi một code heap không còn đủ chỗ cho mã mới, HotSpot có thể tăng cường sweeping để tìm và thu hồi nmethod không còn cần thiết.

Các bước khái quát:

1. Method được biên dịch tạo thêm CodeBlob trong heap tương ứng.
2. Khi heap có áp lực, sweeper tìm code cũ, not entrant hoặc không còn được sử dụng.
3. Code không còn được tham chiếu an toàn có thể được thu hồi.
4. Nếu không có đủ dung lượng, compiler có thể bị tạm dừng hoặc tắt để tránh tiếp tục cấp phát thất bại.
5. Các method đã có mã máy vẫn có thể tiếp tục chạy; method chưa được biên dịch có thể phải chạy ở interpreter hoặc tier thấp hơn cho tới khi compilation có thể tiếp tục.

Thông báo thường gặp:

~~~text
CodeCache is full. Compiler has been disabled.
~~~

Khi gặp tình trạng này, không nên chỉ tăng ReservedCodeCacheSize ngay lập tức. Trước tiên hãy xác định heap nào đầy, số lượng nmethod, mức độ sweeping và liệu ứng dụng có tạo quá nhiều method động hoặc liên tục biên dịch lại hay không.

Segmentation giảm sự cạnh tranh giữa các nhóm code nhưng không tạo thêm dung lượng. Một heap riêng vẫn có thể đầy.

## 11. Sizing và tuning có hệ thống

Một quy trình thực tế:

1. **Đo baseline:** thu thập ReservedCodeCacheSize, từng heap, used/committed/max và hoạt động compilation.
2. **Xác định heap chịu áp lực:** non-method, profiled hay non-profiled.
3. **Xem nguyên nhân:** workload có nhiều method nóng, profiling/recompilation, proxy/generated class hoặc code lifetime bất thường hay không.
4. **Kiểm tra sweeping:** xác nhận code cũ được thu hồi; không tắt flushing chỉ để tránh thông báo.
5. **Điều chỉnh đúng heap:** chỉ tăng heap thiếu dung lượng, đồng thời kiểm tra tổng ReservedCodeCacheSize.
6. **Benchmark lại:** đo throughput, latency, startup, footprint native memory và tần suất compiler bị dừng.
7. **So sánh nhiều workload:** một cấu hình có thể phù hợp với ứng dụng dài hạn nhưng không phù hợp với chương trình ngắn hạn.

Một vài nguyên tắc:

- Không tăng tất cả các heap theo cùng một tỷ lệ khi chưa có số liệu.
- Không dành quá nhiều dung lượng cho non-method heap nếu nó luôn ít sử dụng.
- Không để profiled heap quá nhỏ nếu ứng dụng có nhiều profiling và tiered recompilation.
- Không để non-profiled heap quá nhỏ nếu nhiều method đạt tier tối ưu.
- Giữ code cache flushing ở cấu hình mặc định trừ khi có bằng chứng cụ thể cần thay đổi.
- Tính cả native memory và address-space pressure khi tăng code cache.

## 12. Code cache phân đoạn không giải quyết vấn đề gì?

Segmented Code Cache tập trung vào tổ chức vùng chứa mã máy. Nó không thay thế:

- Java heap sizing hoặc garbage collection.
- Class unloading và Metaspace management.
- Tối ưu thuật toán hoặc giảm số lần gọi method.
- Tuning compilation threshold hoặc compiler queue.
- Điều tra memory leak của object Java.
- Đo hiệu năng bằng benchmark đại diện.

Code cache có thể đầy do quá nhiều mã được biên dịch, nhưng không phải mọi hiện tượng ứng dụng chậm đều do code cache. Cần xem log và số liệu trước khi kết luận.

## 13. Lỗi thường gặp

- **Nhầm code cache với Java heap:** tăng -Xmx không làm tăng ReservedCodeCacheSize.
- **Nhầm code cache với Metaspace:** hai vùng nhớ phục vụ mục đích khác nhau.
- **Cho rằng profiled heap chỉ chứa C1:** C1 tier 1 thuộc non-profiled; tier 2 và 3 thuộc profiled.
- **Cho rằng non-profiled heap chỉ chứa C2:** nó còn chứa tier 1 và native method wrappers.
- **Cho rằng code cache chỉ chứa Java method:** non-method heap còn chứa mã nội bộ của VM.
- **Cho rằng phân đoạn làm tăng tổng dung lượng:** nó tổ chức lại dung lượng đã reserve.
- **Cho rằng các heap tự tăng giảm trong runtime:** các segment được cấu hình lúc khởi động và không tự resize theo mô tả HotSpot hiện hành.
- **Dùng tên flag cũ hoặc sai:** dùng NonNMethodCodeHeapSize, ProfiledCodeHeapSize và NonProfiledCodeHeapSize theo tài liệu hiện hành.
- **Coi kích thước mặc định là cố định cho mọi JDK:** giá trị phụ thuộc runtime và kiến trúc.
- **Chỉ tăng ReservedCodeCacheSize khi có lỗi:** hãy xác định heap cụ thể và kiểm tra sweeping trước.
- **Tắt code cache flushing để tránh compiler dừng:** có thể khiến code cũ chiếm chỗ lâu hơn.
- **Giả định mọi JVM có ba heap giống HotSpot:** segmentation là chi tiết triển khai HotSpot, không phải yêu cầu của Java SE.

## 14. Ghi nhớ

JEP 197 đưa Segmented Code Cache vào HotSpot từ Java 9 để tách mã nội bộ, mã nmethod có profiling và mã nmethod không profiling. Cách tổ chức này giảm phân mảnh giữa các code có vòng đời khác nhau, rút ngắn một số thao tác quét và cải thiện locality của instruction. Dung lượng được điều khiển bởi ReservedCodeCacheSize và các cờ heap tương ứng. Các segment được xác định lúc khởi động, vì vậy cần đo từng heap và phân bổ phù hợp. Khi code cache đầy, kiểm tra log, sweeping và heap chịu áp lực trước khi tăng dung lượng.

## 15. Tài liệu tham khảo

- [JEP 197: Segmented Code Cache](https://openjdk.org/jeps/197)
- [The java Command – Java SE 25: Segmented Code Cache options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The java Command – Java SE 25: Code Heap State Analytics](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Java HotSpot Virtual Machine Performance Enhancements – Java SE 11](https://docs.oracle.com/en/java/javase/11/vm/java-hotspot-virtual-machine-performance-enhancements.html)
- [OpenJDK HotSpot CodeCache source](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/codeCache.cpp)
