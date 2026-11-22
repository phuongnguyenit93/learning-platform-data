# Phân tích CPU hot method bằng JFR

**CPU hot method** là phương thức xuất hiện thường xuyên trong các mẫu stack trace của những thread đang thực thi code. Khi CPU của JVM tăng cao, việc tìm đúng hot method giúp xác định phần code tiêu thụ nhiều thời gian xử lý nhất và ưu tiên tối ưu đúng nơi.

Java Flight Recorder (JFR) thu thập các mẫu thực thi, trạng thái CPU, hoạt động thread, sự kiện JIT và nhiều dữ liệu runtime khác. JDK Mission Control (JMC) trực quan hóa recording bằng các bảng Hot Methods, Call Tree, Hot Threads và CPU. Từ JDK 24, công cụ dòng lệnh jfr còn có view tên hot-methods để xem kết quả trực tiếp trong terminal.

Bài này hướng dẫn cách tạo recording, tìm hot method, đọc stack trace, phân biệt CPU-bound với I/O hoặc lock waiting, thực hành bằng một chương trình Java 17+ và xác minh hiệu quả sau tối ưu.

## 1. Hot method là gì?

Một phương thức được xem là hot khi nó chiếm tỷ trọng lớn trong các mẫu thực thi CPU được thu thập trong recording.

Ví dụ, một request có thể đi qua chuỗi gọi:

~~~text
RequestHandler.handle()
  -> OrderService.calculate()
     -> PricingEngine.applyRules()
        -> DiscountRule.evaluate()
~~~

Nếu JFR thường xuyên lấy mẫu thread khi nó đang chạy bên trong PricingEngine.applyRules(), phương thức này có thể xuất hiện nổi bật trong Hot Methods.

Hot method có thể là:

- Phương thức tính toán có vòng lặp lớn.
- Thuật toán tìm kiếm, sắp xếp, mã hóa hoặc nén dữ liệu.
- Phương thức xử lý chuỗi, regex hoặc JSON.
- Hàm chuyển đổi dữ liệu được gọi quá nhiều lần.
- Phương thức trong thư viện hoặc framework.
- Native method được gọi qua JNI hoặc thư viện hệ thống.

Một phương thức được gọi nhiều lần chưa chắc là hot method. Phương thức có số lần gọi thấp nhưng mỗi lần tính toán rất lâu vẫn có thể chiếm phần lớn CPU.

### Hot method không đồng nghĩa với method có nhiều invocation

Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Invocation count | Số lần phương thức được gọi |
| Execution samples | Số mẫu stack có ghi nhận phương thức đang thực thi |
| CPU hot method | Phương thức chiếm tỷ trọng lớn trong các mẫu CPU |
| Wall-clock latency | Thời gian thực tế người dùng phải chờ |
| CPU utilization | Mức sử dụng CPU của process hoặc hệ thống |

JFR sampling ước lượng nơi CPU dành nhiều thời gian. Nó không đếm chính xác mọi lần gọi phương thức và không đo trực tiếp thời gian chờ của người dùng.

## 2. JFR thu thập dữ liệu CPU như thế nào?

JFR là framework ghi sự kiện và profiling được tích hợp trong JDK. JVM có thể ghi các event theo thời gian, lưu vào file .jfr và cho phép phân tích sau khi recording kết thúc.

Đối với CPU hot method, các event quan trọng gồm:

| Event | Vai trò |
|---|---|
| jdk.CPULoad | Theo dõi CPU load của JVM và toàn hệ thống |
| jdk.ThreadCPULoad | Hỗ trợ xác định thread tiêu thụ CPU qua method sampling |
| jdk.ExecutionSample | Lưu mẫu stack trace của thread đang thực thi Java code |
| jdk.NativeMethodSample | Lưu mẫu thực thi trong native method |
| jdk.Compilation | Ghi hoạt động biên dịch JIT |
| jdk.CompilerPhase | Ghi các phase của quá trình JIT compilation |

### jdk.CPULoad

Dùng để trả lời câu hỏi JVM có thực sự đang sử dụng nhiều CPU hay không.

Event này cho phép so sánh CPU load của JVM với CPU load toàn hệ thống:

- JVM cao và hệ thống cao: JVM có thể là một nguồn tiêu thụ CPU đáng kể.
- JVM thấp nhưng hệ thống cao: process khác có thể đang sử dụng CPU.
- JVM thấp và hệ thống thấp nhưng request chậm: có thể vấn đề nằm ở I/O, lock, network hoặc dependency.

### jdk.ThreadCPULoad

Giúp tìm thread nào đang có hoạt động CPU nổi bật. Sau khi tìm được thread, chuyển sang stack samples và Hot Threads để xem thread đó đang thực thi đường gọi nào.

Thông tin này dựa trên method sampling nên không phải phép đo CPU chính xác tuyệt đối cho từng thread. Khi số mẫu ít, thứ hạng thread có thể thiếu ổn định.

### jdk.ExecutionSample

Đây là event quan trọng nhất khi tìm hot Java method.

JVM định kỳ lấy mẫu stack của thread đang thực thi code. Mỗi mẫu cho biết thread đang ở đâu trong call stack tại thời điểm lấy mẫu.

Các thread đang chờ I/O, ngủ hoặc chờ lock thường không được lấy mẫu như thread đang chạy code. Vì vậy, nhiều execution samples ở một phương thức là dấu hiệu phương thức hoặc đường gọi chứa nó đang tiêu thụ đáng kể thời gian thực thi.

### jdk.NativeMethodSample

Nếu ứng dụng tiêu thụ CPU trong native code, hãy xem cả native method samples. Một phương thức Java có thể chỉ là điểm gọi vào thư viện native; tối ưu phần Java bên ngoài có thể không giải quyết được CPU bottleneck bên trong native library.

## 3. JFR và JDK Mission Control

Hai thành phần này có vai trò khác nhau:

- **JFR:** thu thập runtime events và method samples từ JVM.
- **JMC:** mở recording, hiển thị biểu đồ, bảng thống kê và call tree để phân tích.

JFR được tích hợp trong JDK hiện đại. JMC là ứng dụng riêng và không nằm trong cài đặt JDK thông thường; cần cài đặt JMC nếu muốn dùng giao diện phân tích đồ họa.

JMC có các khu vực hữu ích:

| Khu vực | Dùng để làm gì? |
|---|---|
| Code → Hot Methods | Xếp hạng phương thức theo tỷ lệ execution samples |
| Code → Call Tree | Xem các đường gọi dẫn đến phương thức hot |
| Threads → Hot Threads | Xem thread có nhiều hoạt động CPU |
| Threads → Overview | Quan sát hoạt động thread và CPU |
| JVM Internals → Compiler | Xem hoạt động biên dịch JIT |
| JVM Internals → Garbage Collections | Kiểm tra CPU và thời gian dành cho GC |
| I/O | Xác định thời gian chờ file và socket |
| Locks / Contention | Tìm thread bị chặn do đồng bộ hóa |

JMC cho phép chọn một phương thức trong Hot Methods để xem stack trace liên quan. Call Tree giúp lần theo đường gọi, bắt đầu từ thread entry như Thread.run() rồi đi đến những nhánh có nhiều mẫu nhất.

## 4. Tạo JFR recording cho CPU profiling

Để tìm hot method, nên ghi trong lúc ứng dụng đang xử lý workload đại diện. Một recording quá ngắn hoặc được tạo lúc ứng dụng idle có thể không phản ánh bottleneck thực tế.

### Kiểm tra công cụ

~~~bash
java --version
jcmd -l
jfr --help
~~~

Dùng jcmd để tìm JVM đang chạy. Xác định đúng PID, host và user trước khi bắt đầu recording.

### Ghi recording vào một JVM đang chạy

Cú pháp:

~~~bash
jcmd <pid> JFR.start name=cpu-hot settings=profile duration=30s filename=cpu-hot.jfr
~~~

Giải thích:

- **pid:** PID của JVM mục tiêu.
- **name=cpu-hot:** tên recording.
- **settings=profile:** dùng profile settings để thu thập nhiều dữ liệu profiling hơn.
- **duration=30s:** ghi trong 30 giây.
- **filename=cpu-hot.jfr:** file output.

Đường dẫn tương đối được giải quyết theo working directory của JVM mục tiêu. Trong môi trường production, nên dùng đường dẫn tuyệt đối đến thư mục có quyền ghi và được bảo vệ.

Ví dụ trên Windows:

~~~powershell
jcmd 12345 JFR.start name=cpu-hot settings=profile duration=30s filename=C:\diagnostics\cpu-hot.jfr
~~~

Ví dụ trên Linux:

~~~bash
jcmd 12345 JFR.start name=cpu-hot settings=profile duration=30s filename=/var/tmp/cpu-hot.jfr
~~~

Thay PID và đường dẫn bằng giá trị của môi trường thực tế.

### Kiểm tra recording

~~~bash
jcmd <pid> JFR.check
~~~

Lệnh cho biết recording đang hoạt động trên JVM. Recording có duration sẽ tự kết thúc và ghi file khi hết thời gian.

### Chọn profile phù hợp

JFR có hai template thường dùng:

| Template | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| default.jfc | Thu thập dữ liệu cơ bản với overhead thấp | Recording liên tục, giám sát dài hạn |
| profile.jfc | Thu thập nhiều dữ liệu method profiling hơn, overhead cao hơn | Điều tra bottleneck trong một khoảng thời gian ngắn |

Profile recording phù hợp hơn khi cần tìm CPU hot method vì method sampling được thực hiện tích cực hơn. Tuy nhiên, overhead thay đổi theo ứng dụng và cấu hình; hãy đo tác động trên workload thực tế.

Không bật mọi event ở mức chi tiết cao trong thời gian dài nếu chưa đánh giá overhead.

## 5. Phân tích recording bằng công cụ jfr

Sau khi file recording được tạo, dùng jfr CLI để kiểm tra.

### Xem thông tin tổng quan

~~~bash
jfr summary cpu-hot.jfr
~~~

Summary hiển thị thông tin recording, khoảng thời gian, số lượng event theo loại và các metadata quan trọng.

Trước khi đọc hot method, xác nhận file có đủ thời gian ghi và có event liên quan đến method sampling.

### Xem Hot Methods trực tiếp trong terminal

Trên JDK 24, jfr hỗ trợ view:

~~~bash
jfr view hot-methods cpu-hot.jfr
~~~

Có thể tăng chiều rộng bảng:

~~~bash
jfr view --width 160 hot-methods cpu-hot.jfr
~~~

View hot-methods tổng hợp dữ liệu mẫu để giúp nhận diện phương thức nổi bật trong recording.

### Xem thread CPU load

~~~bash
jfr view thread-cpu-load cpu-hot.jfr
~~~

### Xem CPU load samples

~~~bash
jfr view cpu-load-samples cpu-hot.jfr
~~~

Các view này giúp đối chiếu phương thức hot với thread và tình trạng CPU trong cùng recording.

### In event thô

Nếu cần xem stack sample cụ thể:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.NativeMethodSample cpu-hot.jfr
~~~

Để xem thêm thông tin CPU và thread:

~~~bash
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad cpu-hot.jfr
~~~

Event thô thường có nhiều dữ liệu. Dùng filter event để thu hẹp nội dung và tránh đọc toàn bộ recording khi không cần thiết.

## 6. Tìm hot method trong JDK Mission Control

Mở file cpu-hot.jfr bằng JMC.

Quy trình:

1. Mở JDK Mission Control.
2. Chọn Open File và mở recording.
3. Chờ JMC hoàn tất phân tích.
4. Mở khu vực Code.
5. Chọn Hot Methods.
6. Sắp xếp theo tỷ lệ execution time hoặc số mẫu.
7. Chọn một phương thức nổi bật để xem stack trace.
8. Mở Call Tree để tìm caller và đường gọi liên quan.
9. Chuyển sang Threads để xem thread nào tạo ra nhiều mẫu.
10. Đối chiếu với CPU, GC, I/O và lock events.

### Đọc bảng Hot Methods

Bảng Hot Methods giúp xếp hạng các phương thức theo tỷ trọng thời gian thực thi được ước lượng từ mẫu.

Khi xem bảng:

- Tìm phương thức có tỷ lệ mẫu lớn.
- Kiểm tra số mẫu đủ lớn hay không.
- Xem phương thức thuộc package ứng dụng, thư viện hay JDK.
- Chọn phương thức để xem stack trace.
- Kiểm tra phương thức được gọi từ những caller nào.
- Đánh giá phương thức có nằm trên đường xử lý nghiệp vụ quan trọng hay không.

Một phương thức thư viện có thể đứng đầu vì nhiều caller cùng sử dụng nó. Khi đó, cần kiểm tra caller và dữ liệu đầu vào trước khi sửa code thư viện hoặc tối ưu phần gọi.

### Dùng Call Tree

Call Tree cho biết các đường gọi dẫn đến hot method.

Ví dụ:

~~~text
Thread.run()
  ApplicationWorker.run()
    OrderService.process()
      PricingEngine.calculate()
        DiscountEngine.evaluate()
          RuleMatcher.match()
~~~

Nếu RuleMatcher.match() xuất hiện nhiều trong mẫu, hãy kiểm tra:

- Có vòng lặp hoặc regex phức tạp không?
- Có lặp lại cùng phép tính không?
- Có thể tính trước hoặc cache kết quả không?
- Có thể giảm số lần gọi không?
- Có cấu trúc dữ liệu phù hợp hơn không?

Call Tree giúp xác định phương thức hot nằm trong ngữ cảnh nào, từ đó tránh tối ưu sai tầng.

## 7. Ví dụ: phân biệt CPU-bound và thread waiting

Một hệ thống có request latency cao chưa chắc do CPU hot method.

Có ba tình huống thường gặp:

### Tình huống A: CPU-bound

Thread liên tục chạy code và tạo nhiều execution samples. CPU của JVM cao.

Cách xử lý:

- Mở Hot Methods.
- Xem Call Tree.
- Tìm vòng lặp, thuật toán hoặc phép tính chiếm nhiều mẫu.
- Kiểm tra số thread CPU cao.
- Tối ưu code và đo lại.

### Tình huống B: I/O-bound

Thread dành nhiều thời gian chờ socket hoặc file. CPU có thể thấp dù request latency cao.

Kiểm tra:

- jdk.SocketRead
- jdk.SocketWrite
- jdk.FileRead
- jdk.FileWrite

Tìm endpoint hoặc dependency gây chậm, thời gian chờ và lượng dữ liệu truyền.

### Tình huống C: Lock contention

Nhiều thread chờ cùng monitor hoặc bị park. CPU không nhất thiết cao.

Kiểm tra:

- jdk.JavaMonitorEnter
- jdk.JavaMonitorWait
- jdk.ThreadPark
- jdk.ThreadSleep

Xem lock nào bị tranh chấp và stack trace của thread chờ.

Một số Java Application duration events mặc định chỉ ghi khi thời gian vượt 20 ms. Vì vậy, không thấy event không chứng minh rằng ứng dụng không có các lần chờ ngắn. Có thể điều chỉnh threshold để thu thập thêm dữ liệu, nhưng recording sẽ có nhiều event hơn và có thể tăng overhead.

## 8. Ví dụ: JIT compilation cũng có thể tiêu thụ CPU

Khi ứng dụng mới khởi động hoặc vừa trải qua warm-up, CPU có thể tăng do JIT compiler biên dịch các method nóng.

Các event liên quan:

- jdk.Compilation
- jdk.CompilationFailure
- jdk.CompilerPhase

Trong JMC, mở phần Compilations để xem các method được biên dịch và hoạt động compiler.

Không nên nhầm CPU dùng cho JIT compilation với CPU dùng để xử lý request nghiệp vụ.

Nếu recording chỉ lấy trong giai đoạn startup, Hot Methods có thể phản ánh workload warm-up thay vì workload ổn định.

Để có kết quả phù hợp:

1. Khởi động ứng dụng.
2. Chạy workload warm-up.
3. Chờ hệ thống đạt trạng thái ổn định.
4. Bắt đầu recording.
5. Ghi trong giai đoạn workload đại diện.
6. So sánh thêm recording ở các giai đoạn khác nếu cần.

## 9. Lab Java 17+: tạo một CPU hot method

Chương trình sau tạo một vòng lặp tính toán liên tục để có thể quan sát bằng JFR. Method hotLoop() thực hiện nhiều phép toán số nguyên và giữ kết quả trong biến volatile để JVM không loại bỏ toàn bộ công việc.

Tạo file **CpuHotMethodsDemo.java**:

~~~java
public final class CpuHotMethodsDemo {
    private static volatile long sink;

    public static void main(String[] args) {
        long seconds = args.length == 0
                ? 90L
                : Long.parseLong(args[0]);

        if (seconds <= 0) {
            throw new IllegalArgumentException(
                    "seconds must be positive");
        }

        long deadline = System.nanoTime()
                + seconds * 1_000_000_000L;

        long state = 0x1234ABCD5678EF90L;

        System.out.println("READY");

        while (System.nanoTime() < deadline) {
            state = hotLoop(state, 500_000);
        }

        sink = state;
        System.out.println("DONE");
    }

    private static long hotLoop(long state, int rounds) {
        for (int i = 0; i < rounds; i++) {
            state ^= state << 13;
            state ^= state >>> 7;
            state ^= state << 17;
            state += 0x9E3779B97F4A7C15L ^ i;
        }

        return state;
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 CpuHotMethodsDemo.java
~~~

Chạy chương trình trong terminal thứ nhất:

~~~bash
java CpuHotMethodsDemo 90
~~~

Stdout:

~~~text
READY
DONE
~~~

Dòng READY xuất hiện trước khi vòng lặp bắt đầu chạy. Dòng DONE xuất hiện sau khi chương trình đã chạy đủ thời gian được chỉ định.

### Bắt đầu recording từ terminal thứ hai

Tìm JVM:

~~~bash
jps -l
~~~

Tìm PID của CpuHotMethodsDemo, sau đó:

~~~bash
jcmd <pid> JFR.start name=cpu-lab settings=profile duration=30s filename=cpu-lab.jfr
~~~

Sau khoảng 30 giây, file recording được tạo. Kiểm tra:

~~~bash
jfr summary cpu-lab.jfr
~~~

Xem hot methods:

~~~bash
jfr view hot-methods cpu-lab.jfr
~~~

Trong recording, hotLoop() là phương thức tính toán chính và có thể xuất hiện nổi bật trong stack samples. JIT có thể inline method hoặc thay đổi cách hiển thị stack frame, vì vậy tên và thứ hạng cụ thể phụ thuộc runtime.

Khi chương trình hoàn tất, terminal thứ nhất in:

~~~text
DONE
~~~

Đây là lab CPU-bound một thread. Nó giúp quan sát quy trình profiling; kết quả không đại diện cho workload của một ứng dụng production thực tế.

## 10. Cách đọc kết quả hot method đúng

Một phương thức có tỷ lệ sample cao cần được xem xét trong ngữ cảnh.

### Kiểm tra số mẫu

Nếu recording chỉ có rất ít samples, thứ hạng hot method có thể thay đổi mạnh giữa các lần ghi.

Nên:

- Ghi đủ lâu để có số mẫu đại diện.
- Lặp lại recording khi kết quả bất thường.
- Dùng workload gần với production.
- Tránh kết luận từ một stack sample đơn lẻ.

### Kiểm tra caller và callee

Phương thức xuất hiện nhiều trong stack không nhất thiết là nơi cần sửa.

Ví dụ:

~~~text
OrderService.handle()
  JsonParser.parse()
    StringDecoder.decode()
      Character.isWhitespace()
~~~

Nếu Character.isWhitespace() có nhiều mẫu, nguyên nhân có thể là parser đang xử lý payload lớn hoặc được gọi quá nhiều lần. Tối ưu ở caller hoặc giảm số lần parse có thể hiệu quả hơn thay đổi method cấp thấp.

### Kiểm tra thread

Một phương thức có thể hot vì một worker thread bị quá tải, hoặc vì nhiều worker cùng gọi nó.

Dùng Hot Threads và thread filters để phân biệt:

- Một thread duy nhất sử dụng CPU cao.
- Nhiều thread cùng thực hiện một method.
- Một thread xử lý background job gây CPU spike.
- Thread pool có workload không cân bằng.

### Kiểm tra JIT inlining

JIT có thể inline method nhỏ vào caller. Stack trace có thể biểu diễn logical inline frame tùy thông tin recording và runtime.

Do đó, khi không thấy một method nhỏ trong bảng, không thể kết luận nó không được thực thi. Xem call tree, compiler events và các frame lân cận.

## 11. Tối ưu hot method theo nguyên nhân

Sau khi xác định được method, cần hiểu công việc mà nó thực hiện trước khi sửa.

| Dấu hiệu | Hướng tối ưu cần xem xét |
|---|---|
| Vòng lặp lặp lại cùng phép tính | Loại bỏ tính toán trùng lặp, giảm số vòng lặp |
| Nhiều object tạm | Giảm allocation, tái sử dụng dữ liệu khi phù hợp |
| Regex hoặc parsing tốn CPU | Tối ưu pattern, parse một lần, giới hạn input |
| Tìm kiếm tuyến tính trên dữ liệu lớn | Chọn cấu trúc dữ liệu phù hợp như HashMap hoặc Set |
| Chuyển đổi chuỗi liên tục | Giảm copy và tạo chuỗi trung gian |
| Serialization/deserialization tốn CPU | Giảm payload, tối ưu schema và codec |
| Method thư viện chiếm nhiều mẫu | Kiểm tra caller, cấu hình và phiên bản thư viện |
| CPU tăng do JIT | Đánh giá warm-up, compilation và workload ổn định |
| Native method hot | Kiểm tra native library, JNI và dữ liệu truyền qua biên Java/native |

Không áp dụng cache hoặc tăng concurrency theo phản xạ. Cache có thể tăng memory pressure; concurrency cao hơn có thể tăng contention và context switching.

### Tối ưu theo dữ liệu đo

Quy trình tốt:

1. Ghi baseline trước khi thay đổi.
2. Xác định hot method và call path.
3. Đưa ra giả thuyết cụ thể.
4. Thay đổi một yếu tố chính.
5. Chạy lại cùng workload.
6. Ghi JFR lần nữa.
7. So sánh CPU, throughput, latency và GC.
8. Giữ thay đổi chỉ khi kết quả cải thiện và không tạo regression.

Đừng chỉ so sánh tỷ lệ sample. Nếu throughput tăng, một method có thể chiếm tỷ trọng sample lớn hơn dù thời gian xử lý mỗi request đã giảm. Luôn xem cả CPU thực tế và kết quả nghiệp vụ.

## 12. Phân biệt self work và work của các method được gọi

Một call stack chứa nhiều method lồng nhau. Một sample ở method sâu có thể đồng thời cho thấy các caller bên trên.

Khi phân tích:

- **Self work:** phần công việc thực hiện bên trong chính method.
- **Inclusive work:** tổng công việc của method và các method được nó gọi.
- **Caller:** method gọi method đang xem.
- **Callee:** method được method đang xem gọi.

Ví dụ:

~~~text
Controller.handle()
  Service.process()
    Repository.load()
      JsonParser.parse()
~~~

Nếu Service.process() xuất hiện nhiều trong call tree, điều đó có thể do thời gian tiêu tốn trong Repository.load() hoặc JsonParser.parse(), chứ không phải bản thân Service.process().

Hãy mở rộng nhánh con và kiểm tra phương thức sâu hơn trước khi quyết định nơi tối ưu.

## 13. Giới hạn của CPU method sampling

JFR sampling là phương pháp thống kê, không phải phép đo chính xác thời gian của từng lần gọi.

Những giới hạn cần nhớ:

- Method ngắn có thể không trúng mẫu.
- Recording quá ngắn có thể thiếu số mẫu.
- Workload không đại diện làm sai thứ hạng.
- Thread đang chờ I/O hoặc lock không được lấy mẫu như thread chạy code.
- Native code cần xem native method samples.
- JIT inlining có thể thay đổi cách hiển thị frame.
- Hot method trong thư viện có thể chỉ là biểu hiện của workload từ caller.
- Sampling không cung cấp chính xác invocation count.
- Tỷ lệ mẫu không trực tiếp bằng phần trăm wall-clock latency của request.

Không dùng Hot Methods làm bằng chứng duy nhất để kết luận nguyên nhân sự cố. Hãy đối chiếu với CPU load, thread state, GC, I/O, lock contention và application metrics.

## 14. Kiểm soát overhead và bảo vệ recording

JFR được thiết kế để thu thập dữ liệu với overhead thấp, nhưng overhead thay đổi theo workload, event settings và thời lượng ghi.

Một recording profile có thể thu thập nhiều method samples hơn recording continuous dùng default settings. Hãy cân nhắc:

- Ghi trong thời gian đủ để có mẫu đại diện.
- Tránh bật event không liên quan.
- Đo overhead trong môi trường kiểm thử nếu có.
- Theo dõi CPU, memory, disk và latency khi recording.
- Giới hạn thời gian và dung lượng recording.
- Dùng default settings cho continuous monitoring khi phù hợp.

File .jfr có thể chứa class names, package, thread names, system properties, file paths, endpoint và thông tin runtime nội bộ. Hãy bảo vệ file như dữ liệu vận hành nhạy cảm:

- Lưu tại thư mục có quyền truy cập tối thiểu.
- Không commit file vào Git.
- Không chia sẻ recording qua kênh công khai.
- Redact thông tin trước khi đưa vào báo cáo.
- Áp dụng retention policy và xóa file khi hết nhu cầu.

## 15. Lỗi thường gặp

### Hot Methods không có dữ liệu

Kiểm tra recording có event execution sampling hay không. Nếu dùng default continuous settings, số method samples có thể ít hơn profile recording.

Dùng profile recording ngắn để thu thập thêm dữ liệu khi cần.

### CPU cao nhưng Hot Methods không có method ứng dụng nổi bật

Kiểm tra:

- CPU của JVM so với CPU toàn hệ thống.
- NativeMethodSample.
- JIT compiler events.
- Garbage collection.
- Các process khác trên host.
- Workload và thời gian ghi recording.

### Hot method thay đổi giữa các recording

Có thể do workload, warm-up, thread scheduling hoặc số mẫu khác nhau. Ghi lại trong cùng điều kiện và đủ lâu trước khi so sánh.

### Method đứng đầu là thư viện JDK

Kiểm tra caller trong Call Tree. Method JDK có thể nhận nhiều mẫu vì ứng dụng gọi nó quá nhiều lần hoặc truyền dữ liệu có kích thước lớn.

### Request chậm nhưng CPU thấp

Kiểm tra SocketRead, SocketWrite, FileRead, FileWrite, JavaMonitorWait, ThreadPark và GC pauses. Có thể bottleneck nằm ở network, disk, lock hoặc dependency bên ngoài.

### CPU tăng ngay sau khi khởi động

Kiểm tra JIT compilation và warm-up. Recording quá sớm có thể phản ánh chi phí startup thay vì workload ổn định.

### Recording quá lớn

Giảm duration, chọn settings phù hợp, giới hạn maxsize/maxage hoặc chỉ bật các event cần thiết. Không xóa file cũ nếu chưa xác minh đã được lưu trữ an toàn.

## 16. Quy trình phân tích CPU hot method hoàn chỉnh

1. Xác định service, JVM PID, JDK version và workload cần điều tra.
2. Kiểm tra CPU load của JVM và toàn hệ thống.
3. Warm-up ứng dụng nếu cần.
4. Bắt đầu JFR recording bằng profile settings trong khoảng thời gian đại diện.
5. Kiểm tra summary và số lượng ExecutionSample.
6. Mở Hot Methods để tìm phương thức có tỷ lệ sample lớn.
7. Mở Call Tree để hiểu caller, callee và đường gọi.
8. Xem Hot Threads để xác định thread tiêu thụ CPU.
9. Kiểm tra native samples, JIT, GC, I/O và lock events.
10. Đọc source code và xác định nguyên nhân có thể tối ưu.
11. Đề xuất thay đổi nhỏ, đo baseline và thực hiện thử nghiệm.
12. Ghi recording sau thay đổi với workload và cấu hình tương đương.
13. So sánh CPU, throughput, latency, GC và sample distribution.
14. Lưu kết quả cùng JDK version, JVM flags, recording settings và thời gian thử nghiệm.

## 17. Checklist CPU hot method

- Xác định đúng JVM và PID.
- Ghi CPU load của JVM và toàn hệ thống.
- Chọn profile recording khi cần method sampling chi tiết.
- Ghi trong workload đại diện và đủ lâu.
- Kiểm tra số lượng ExecutionSample.
- Xem Hot Methods và Call Tree.
- Phân biệt self work với inclusive work.
- Lọc theo thread để tìm CPU hotspot.
- Kiểm tra NativeMethodSample khi có native code.
- Kiểm tra JIT compilation và warm-up.
- Kiểm tra I/O, lock, park và GC nếu CPU không phải nguyên nhân.
- Không coi sample percentage là thời gian chính xác của mỗi invocation.
- Tối ưu theo giả thuyết có thể kiểm chứng.
- Đo lại bằng cùng workload và cấu hình.
- Bảo vệ file JFR và xóa theo retention policy.

## 18. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| CPU hot method | Phương thức xuất hiện nhiều trong các mẫu thực thi CPU |
| JFR | Java Flight Recorder, framework ghi runtime events và profiling |
| JMC | JDK Mission Control, công cụ phân tích recording |
| ExecutionSample | Mẫu stack trace của thread đang thực thi Java code |
| NativeMethodSample | Mẫu thực thi trong native method |
| CPULoad | Thống kê CPU load của JVM và hệ thống |
| ThreadCPULoad | Dữ liệu hỗ trợ xác định thread sử dụng CPU |
| Hot Methods | Bảng xếp hạng phương thức theo execution samples |
| Call Tree | Cây đường gọi phương thức |
| Hot Threads | Nhóm thread có hoạt động CPU nổi bật |
| Sampling | Lấy mẫu trạng thái thay vì ghi mọi lần thực thi |
| JIT | Just-In-Time compiler |
| Compilation event | Sự kiện biên dịch method của JIT |
| Self work | Công việc thực hiện bên trong chính method |
| Inclusive work | Công việc của method và các method được gọi |
| CPU-bound | Công việc bị giới hạn bởi năng lực xử lý CPU |
| I/O-bound | Công việc bị giới hạn bởi thời gian chờ I/O |
| Lock contention | Tranh chấp khi nhiều thread cần cùng một lock |
| Warm-up | Giai đoạn JVM nạp class, profiling và biên dịch JIT |

Phân tích CPU hot method bằng JFR giúp chuyển từ nhận định chung rằng ứng dụng dùng nhiều CPU sang việc xác định method và call path cần kiểm tra. Hãy kết hợp Hot Methods, Call Tree, Hot Threads và các event CPU/I/O/lock, sau đó tối ưu và đo lại trên workload tương đương.

## Tài liệu tham khảo

- Oracle JDK 24 — [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- Oracle — [Java Mission Control and Flight Recorder Demo](https://www.oracle.com/webfolder/technetwork/tutorials/obe/java/mc-jfr/index.html)
- Oracle — [JDK Mission Control](https://docs.oracle.com/en/java/java-components/jdk-mission-control/index.html)