# Compiler statistics với jstat

## 1. Tổng quan

`jstat` là công cụ dòng lệnh của JDK dùng để đọc các performance counter từ một Java HotSpot Virtual Machine (JVM) đang chạy. Với compiler statistics, công cụ giúp quan sát hoạt động của Just-In-Time compiler (JIT): số compilation task đã thực hiện, số task thất bại, số task bị vô hiệu hóa và thời gian dành cho biên dịch.

JVM thường bắt đầu bằng cách thông dịch bytecode. Khi một method hoặc đoạn code được thực thi đủ thường xuyên, HotSpot có thể biên dịch nó thành machine code để tăng tốc các lần chạy sau. Với tiered compilation, nhiều mức biên dịch có thể được sử dụng trong quá trình ứng dụng nóng lên.

Compiler statistics hữu ích khi:

- Kiểm tra JVM có đang thực hiện JIT compilation hay không.
- Quan sát tổng số compilation task và thời gian biên dịch.
- Phát hiện compilation task thất bại hoặc bị invalidated.
- Xem method gần nhất được biên dịch.
- So sánh hoạt động compiler trong các giai đoạn warm-up và tải thực tế.

`jstat` cung cấp số liệu tổng hợp và snapshot. Nó không thay thế profiler, JFR hoặc log chi tiết của compiler; một dòng thống kê không tự giải thích vì sao method được biên dịch, vì sao compilation thất bại hoặc compilation đã cải thiện latency bao nhiêu.

## 2. Phân biệt hai chế độ compiler

Có hai output option liên quan trực tiếp đến JIT:

| Lệnh | Nội dung | Câu hỏi trả lời |
|---|---|---|
| `jstat -compiler` | Thống kê tổng hợp hoạt động compiler | JVM đã thực hiện bao nhiêu compilation task, thất bại bao nhiêu và tốn bao lâu? |
| `jstat -printcompilation` | Thông tin method được biên dịch gần nhất | Method nào vừa được compiler xử lý, bytecode size và compilation type là gì? |

`-compiler` cho biết xu hướng tổng thể của compiler. `-printcompilation` cho biết method gần nhất tại thời điểm lấy mẫu. Nó không phải danh sách đầy đủ các method đã từng được biên dịch và không lưu lại toàn bộ lịch sử compilation.

Hai lệnh dùng cùng cơ chế lấy số liệu JVM nhưng phục vụ hai góc nhìn khác nhau. Hãy chọn output option theo câu hỏi cần kiểm tra.

## 3. Cú pháp jstat và cách xác định JVM

Cú pháp tổng quát:

~~~bash
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Các thành phần:

- `-compiler` hoặc `-printcompilation` là output option cần xem.
- `-t` thêm cột timestamp thể hiện thời gian đã trôi qua kể từ lúc JVM đích khởi động.
- `-h<lines>` in lại hàng tiêu đề sau mỗi số mẫu được chỉ định.
- `vmid` là Virtual Machine Identifier của JVM cần theo dõi.
- `interval` là khoảng cách giữa các lần lấy mẫu.
- `count` là số mẫu cần lấy.

Xem trợ giúp:

~~~bash
jstat -help
~~~

Liệt kê output option mà bản JDK hiện tại hỗ trợ:

~~~bash
jstat -options
~~~

Trên JDK 24.0.2 được kiểm tra, danh sách có `-compiler` và `-printcompilation` cùng các option khác như `-class`, `-gc`, `-gcutil`, `-gccapacity` và `-gccause`.

Thông thường, `vmid` là local JVM identifier (LVMID), thường trùng với process ID của hệ điều hành nhưng không được bảo đảm luôn giống nhau. Có thể dùng:

~~~bash
jps -l
~~~

Tìm đúng class hoặc JAR của ứng dụng rồi dùng identifier tương ứng. Không sao chép PID minh họa từ tài liệu vào môi trường thật.

Ví dụ với một tiến trình local:

~~~bash
jstat -compiler 24816
jstat -printcompilation 24816
~~~

Thay `24816` bằng LVMID/PID thực tế.

## 4. Đọc kết quả jstat -compiler

Chạy:

~~~bash
jstat -compiler <pid>
~~~

Output có dạng:

~~~text
Compiled Failed Invalid   Time   FailedType FailedMethod
      31      0       0     0.01          0
~~~

Ý nghĩa từng cột:

| Cột | Ý nghĩa |
|---|---|
| `Compiled` | Tổng số compilation task đã được thực hiện |
| `Failed` | Số compilation task thất bại |
| `Invalid` | Số compilation task đã bị invalidated |
| `Time` | Tổng thời gian dành cho compilation task |
| `FailedType` | Compilation type của lần compilation thất bại gần nhất |
| `FailedMethod` | Tên class và method của lần compilation thất bại gần nhất |

### Compiled

Đây là số compilation task đã được thực hiện, không phải số method hiện đang nằm trong code cache và cũng không phải số bytecode method của ứng dụng. Giá trị thường tăng khi JVM tiếp tục chạy workload khiến JIT phải biên dịch thêm code.

### Failed

Đây là số compilation task thất bại. Nó không phải số exception mà ứng dụng ném ra. Một method Java có thể ném exception trong lúc chạy mà không có compilation task nào thất bại.

Nếu giá trị tăng, cần tìm thêm thông tin trong compiler log, JFR hoặc công cụ chẩn đoán phù hợp. Riêng counter này không cung cấp stack trace hay nguyên nhân chi tiết.

### Invalid

Đây là số compilation task bị vô hiệu hóa. Compilation bị invalidated là một trạng thái khác với compilation thất bại. JVM có thể phải loại bỏ code đã biên dịch khi các giả định tối ưu hóa không còn đúng; không nên tự động xem mọi lần invalidation là lỗi ứng dụng.

### Time

Đây là thời gian đã dành cho các compilation task. Giá trị là số liệu tổng hợp, không phải latency của request và cũng không phải thời gian biên dịch riêng của method gần nhất.

### FailedType và FailedMethod

Hai cột này mô tả lần compilation thất bại gần nhất: loại compilation và class/method liên quan. Nếu chưa có compilation failure, chúng có thể hiển thị `0` hoặc để trống tùy trường và phiên bản JVM.

Chúng không phải danh sách tất cả lỗi compiler và không giải thích nguyên nhân thất bại.

## 5. Đọc kết quả jstat -printcompilation

Chạy:

~~~bash
jstat -printcompilation <pid>
~~~

Output ví dụ từ tiến trình thực hành:

~~~text
Compiled  Size  Type Method
      31   132     1 demo/CompilerStatsDemo main
~~~

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `Compiled` | Số compilation task được thực hiện cho method được biên dịch gần nhất theo mô tả của jstat |
| `Size` | Số byte bytecode của method đó |
| `Type` | Loại compilation |
| `Method` | Tên class và method vừa được biên dịch |

Tên class dùng dấu `/` thay cho dấu `.` để phân cách package, ví dụ `demo/CompilerStatsDemo`. Cột `Type` là giá trị loại compilation mà JVM báo cáo; không nên tự gán một con số cố định cho C1/C2 nếu chưa đối chiếu tài liệu của đúng phiên bản JVM.

Lưu ý: cột `Compiled` xuất hiện ở cả `-compiler` và `-printcompilation`, nhưng cách diễn giải phụ thuộc output option. Với `-compiler`, đây là số compilation task tổng hợp. Với `-printcompilation`, đây là thông tin gắn với method được biên dịch gần nhất theo định nghĩa của tài liệu jstat.

`-printcompilation` hiển thị method mới nhất tại thời điểm lấy mẫu. Nếu nhiều method được biên dịch giữa hai lần lấy mẫu, một số method có thể không xuất hiện trong output. Dùng compiler log hoặc JFR khi cần timeline chi tiết.

## 6. Lấy nhiều mẫu theo thời gian

Nếu chỉ chạy:

~~~bash
jstat -compiler <pid>
~~~

`jstat` in một mẫu rồi kết thúc.

Lấy 5 mẫu, mỗi giây một lần:

~~~bash
jstat -compiler <pid> 1000 5
~~~

Khoảng lấy mẫu có thể ghi rõ đơn vị:

~~~bash
jstat -compiler <pid> 250ms 8
jstat -compiler <pid> 2s 5
~~~

Nếu có interval nhưng không có count, `jstat` tiếp tục lấy mẫu cho đến khi JVM kết thúc hoặc người dùng dừng lệnh.

Thêm timestamp:

~~~bash
jstat -compiler -t <pid> 1000 5
~~~

Cột `Timestamp` thể hiện số giây đã trôi qua kể từ khi JVM đích khởi động. Nó không phải thời gian hiện tại của hệ điều hành.

In lại header sau mỗi 3 mẫu:

~~~bash
jstat -compiler -t -h3 <pid> 250ms 9
~~~

Các tùy chọn lấy mẫu hữu ích khi quan sát compiler warm-up, nhưng khoảng lấy mẫu quá ngắn có thể tạo nhiều output mà không thêm thông tin hữu ích. Chọn interval đủ dài để nhìn được thay đổi và đủ ngắn để phù hợp với sự cố đang điều tra.

## 7. Ví dụ Java 17 hoàn chỉnh để tạo hoạt động JIT

Tạo file `src/demo/CompilerStatsDemo.java`:

~~~java
package demo;

/** Generates a repeatable workload for observing JIT compiler statistics. */
public final class CompilerStatsDemo {
    private static volatile long sink;

    private static long hotMethod(int value) {
        long result = value;
        for (int i = 0; i < 100; i++) {
            result = result * 31 + i;
        }
        return result;
    }

    /**
     * Runs a warm-up workload, then stays active for jstat inspection.
     *
     * @param args command-line arguments
     * @throws InterruptedException if the sleep is interrupted
     */
    public static void main(String[] args) throws InterruptedException {
        long sum = 0;
        for (int i = 0; i < 5_000_000; i++) {
            sum += hotMethod(i);
        }
        sink = sum;

        System.out.println("READY sink=" + sink);

        while (true) {
            for (int i = 0; i < 100_000; i++) {
                sink ^= hotMethod(i);
            }
            Thread.sleep(100);
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/demo/CompilerStatsDemo.java
~~~

Mở Terminal 1 và chạy:

~~~bash
java -Xms32m -Xmx128m -cp out demo.CompilerStatsDemo
~~~

Stdout chính xác trong môi trường thử nghiệm:

~~~text
READY sink=-3778119394682985248
~~~

Giữ tiến trình chạy để lấy số liệu từ Terminal 2.

Tìm PID:

~~~bash
jps -l
~~~

Lấy thống kê compiler:

~~~bash
jstat -compiler <pid>
~~~

Theo dõi 5 mẫu, mỗi giây một lần:

~~~bash
jstat -compiler -t <pid> 1000 5
~~~

Xem method được biên dịch gần nhất:

~~~bash
jstat -printcompilation <pid>
~~~

Theo dõi method mới nhất qua nhiều mẫu:

~~~bash
jstat -printcompilation <pid> 250ms 5
~~~

Trong lần thử với JDK 24.0.2, compiler đã thực hiện 31 task, không có task thất bại hoặc invalidated, tổng thời gian compilation hiển thị là `0.01`. `-printcompilation` ghi nhận method `demo/CompilerStatsDemo main` với bytecode size `132` và compilation type `1`. Số liệu có thể khác giữa các lần chạy, JDK, CPU và workload.

Khi hoàn tất, quay lại Terminal 1 và nhấn Ctrl+C để dừng chương trình.

## 8. Hiểu xu hướng compiler statistics

Không nên kết luận hiệu năng chỉ từ một mẫu. Hãy lấy nhiều mẫu và so sánh theo thời gian.

| Quan sát | Cách hiểu phù hợp |
|---|---|
| `Compiled` tăng | JVM tiếp tục thực hiện compilation task |
| `Failed` tăng | Có compilation task thất bại; cần tìm thêm chi tiết |
| `Invalid` tăng | Có compilation task bị invalidated |
| `Time` tăng | Tổng thời gian dành cho compilation task tăng |
| `FailedMethod` có tên method | Đây là method liên quan đến lần compilation failure gần nhất |
| `-printcompilation` đổi method | Một method khác trở thành method được biên dịch gần nhất |

Một số lưu ý khi phân tích:

- `Compiled` tăng trong warm-up là điều bình thường; không tự động có nghĩa compiler đang gặp vấn đề.
- `Failed=0` chỉ cho biết counter không ghi nhận compilation task thất bại tại thời điểm đó. Nó không chứng minh ứng dụng không có lỗi.
- `Invalid` khác `Failed`; không gộp hai cột thành một loại lỗi.
- `Time` là tổng thời gian compiler, không phải phần trăm CPU hay thời gian xử lý request.
- `FailedType` và `FailedMethod` chỉ mô tả lần thất bại gần nhất, không phải lịch sử đầy đủ.
- Nếu method không xuất hiện trong `-printcompilation`, có thể nó chưa được biên dịch hoặc đã bị một method khác thay thế trong lần lấy mẫu kế tiếp.

JIT compilation phụ thuộc số lần thực thi, ngưỡng biên dịch, tiered compilation, compiler mode và tải thực tế. Một ứng dụng ngắn hoặc ít gọi method có thể chưa tạo đủ hoạt động để counter tăng.

## 9. Trường hợp compiler không có số liệu

Nếu JVM được chạy ở chế độ thông dịch:

~~~bash
java -Xint -cp out demo.CompilerStatsDemo
~~~

JIT compiler bị tắt. Trong lần thử với JDK 24.0.2, `jstat -compiler` hiển thị dấu `-` ở các cột compiler thay vì số 0; `-printcompilation` cũng không có method compilation để báo cáo.

Điều này khác với compilation failure. Dấu `-` cho biết trường dữ liệu không có giá trị trong cấu hình JVM đó.

Các trường hợp khác có thể khiến counter không tăng:

- JVM mới khởi động và chưa có method đủ nóng.
- Workload không gọi lặp lại những method cần JIT.
- JVM được cấu hình để hạn chế hoặc tắt compiler.
- Tiến trình kết thúc trước khi lấy được mẫu.
- Quyền truy cập hoặc instrumentation không cho phép `jstat` đọc số liệu.

Trước khi kết luận compiler không hoạt động, kiểm tra JVM flags, thời gian chạy, workload và khả năng attach.

## 10. Giới hạn của jstat và công cụ bổ sung

Oracle đánh dấu `jstat` là **experimental and unsupported**. Các option, cách hoạt động và định dạng output có thể thay đổi hoặc bị loại bỏ trong các bản JDK tương lai.

Tài liệu Oracle cũng khuyến nghị không viết script phụ thuộc vào việc parse output dạng text của `jstat`. Nếu buộc phải tự động hóa, hãy chuẩn bị thay đổi script khi định dạng công cụ thay đổi.

`jstat -compiler` không cung cấp:

- Stack trace hoặc nguyên nhân chi tiết của compilation failure.
- Timeline đầy đủ của mọi method được biên dịch.
- Thời gian biên dịch riêng cho từng method.
- Thông tin đầy đủ về code cache hoặc native memory.
- Phân tích allocation, lock, CPU stack và latency request.

Khi cần thêm dữ liệu:

- Dùng `-XX:+PrintCompilation` để ghi log các sự kiện compilation của HotSpot trong lần chạy được cấu hình.
- Dùng Java Flight Recorder (JFR) và Java Mission Control để xem sự kiện runtime theo thời gian.
- Dùng profiler để phân tích CPU hotspot, call tree và hành vi method.
- Dùng `jcmd <pid> help` để khám phá các diagnostic command mà JVM đích hỗ trợ.

Không nên bật log hoặc profiler có overhead cao trên production mà chưa đánh giá tác động và dung lượng output.

## 11. Lỗi thường gặp

### Unknown option: compiler

Kiểm tra `jstat -options` để xem bản JDK hiện tại có hỗ trợ output option này không. Đảm bảo đang chạy `jstat` từ JDK phù hợp.

### Could not attach to process

Xác nhận LVMID/PID còn tồn tại, công cụ có quyền truy cập tiến trình và JVM đích có instrumentation mà `jstat` cần. Dùng `jps -l` để tìm lại identifier.

### Các cột compiler hiển thị dấu -

Kiểm tra JVM có đang chạy với `-Xint` hoặc cấu hình tắt compiler hay không. Dấu `-` không phải bằng chứng compilation thất bại.

### Compiled không tăng

Ứng dụng có thể chưa chạy đủ lâu, method chưa đủ nóng hoặc JIT compiler không hoạt động. Tạo workload lặp lại, kiểm tra VM flags và lấy thêm mẫu.

### Failed tăng nhưng FailedMethod trống

`FailedMethod` chỉ mô tả lần thất bại gần nhất và có thể không cung cấp đủ thông tin trong mọi trường hợp. Thu thập compiler log hoặc JFR để điều tra nguyên nhân.

### -printcompilation không hiện method mong đợi

Lệnh chỉ hiển thị method được biên dịch gần nhất tại thời điểm lấy mẫu. Method khác có thể đã được biên dịch sau đó. Lấy mẫu ngắn hơn hoặc dùng compilation log nếu cần timeline.

### Output bị thay đổi khi nâng JDK

`jstat` là công cụ experimental/unsupported. Đọc lại `jstat -help`, `jstat -options` và tài liệu đúng phiên bản JDK; không giả định tên cột hoặc định dạng luôn ổn định.

## 12. Quy trình theo dõi compiler trong thực tế

1. Xác định JVM bằng `jps -l` và xác nhận đúng PID.
2. Chạy `jstat -options` để kiểm tra option được hỗ trợ.
3. Chụp một mẫu ban đầu bằng `jstat -compiler <pid>`.
4. Theo dõi nhiều mẫu bằng `jstat -compiler -t <pid> 1000 5`.
5. Dùng `jstat -printcompilation <pid>` để xem method mới nhất.
6. So sánh `Compiled`, `Failed`, `Invalid` và `Time` giữa các mẫu.
7. Nếu `Failed` hoặc `Invalid` thay đổi bất thường, thu thập compiler log/JFR và kiểm tra VM flags.
8. Ghi nhận JDK version, PID, thời điểm, workload và lệnh đã chạy để kết quả có thể đối chiếu.
9. Dừng quá trình lấy mẫu sau khi thu thập đủ dữ liệu.

Đối với hệ thống production, bắt đầu bằng interval vừa phải và số mẫu giới hạn. Chỉ tăng tần suất lấy mẫu khi có câu hỏi cụ thể cần trả lời.

## 13. Checklist

- [ ] Xác định đúng JVM bằng `jps -l`.
- [ ] Dùng `jstat -options` để kiểm tra option có sẵn.
- [ ] Dùng `jstat -compiler` để xem thống kê tổng hợp.
- [ ] Dùng `jstat -printcompilation` để xem method được biên dịch gần nhất.
- [ ] Hiểu rõ `Compiled`, `Failed`, `Invalid`, `Time`, `FailedType` và `FailedMethod`.
- [ ] Dùng interval và count để giới hạn số mẫu.
- [ ] Dùng `-t` để xem thời gian kể từ lúc JVM khởi động.
- [ ] Dùng `-h` để lặp lại header trong output dài.
- [ ] Không nhầm compilation failure với exception của ứng dụng.
- [ ] Không nhầm `Invalid` với `Failed`.
- [ ] Kiểm tra `-Xint` hoặc compiler flags nếu các cột hiển thị `-`.
- [ ] Không parse output bằng script phụ thuộc định dạng chưa ổn định.
- [ ] Dùng JFR, compiler log hoặc profiler khi cần dữ liệu chi tiết hơn.

`jstat -compiler` cho biết hoạt động JIT ở mức tổng hợp; `jstat -printcompilation` cho biết method gần nhất được compiler xử lý. Kết hợp các mẫu theo thời gian với workload có thể lặp lại giúp hiểu giai đoạn warm-up và phát hiện thay đổi compiler, nhưng cần dùng log hoặc profiler khi phải tìm nguyên nhân sâu hơn.

## 14. Tài liệu tham khảo

- [Oracle JDK 24 — The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html): cú pháp, interval/count, timestamp, compiler counters, printcompilation và giới hạn của công cụ.
- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html): cách dùng jstat để theo dõi performance và resource consumption của HotSpot JVM.
- [Oracle JDK 17 — The jstat Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): mô tả compiler statistics và method statistics.
- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html): tùy chọn JVM dùng trong quá trình thực hành như `-Xint` và `-XX:+PrintCompilation`.
