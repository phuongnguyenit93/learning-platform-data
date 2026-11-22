# Breakpoint trong Debugging JVM

## 1. Breakpoint là gì?

**Breakpoint (điểm dừng)** là một yêu cầu gửi tới debugger để tạm dừng chương trình khi một vị trí hoặc sự kiện cụ thể xảy ra. Khi JVM dừng tại breakpoint, người phát triển có thể xem stack trace, thread hiện tại, giá trị biến, trạng thái object và từng bước thực thi để tìm nguyên nhân lỗi.

Breakpoint giúp trả lời những câu hỏi như:

- Biến bắt đầu mang giá trị sai ở dòng nào?
- Nhánh điều kiện nào đã được thực thi?
- Method nhận tham số gì tại thời điểm được gọi?
- Trường dữ liệu bị thay đổi ở đâu?
- Exception xuất hiện tại vị trí nào và đi qua những lời gọi nào?
- Thread nào đang chạy đoạn code gây lỗi?

Breakpoint là một công cụ điều tra có chủ đích. Đặt điểm dừng gần nơi dữ liệu bắt đầu sai giúp thu hẹp phạm vi tìm kiếm; đặt quá nhiều điểm dừng có thể làm phiên debug khó theo dõi và kéo dài thời gian điều tra.

## 2. Breakpoint hoạt động trong kiến trúc JPDA như thế nào?

Java Platform Debugger Architecture (JPDA) cung cấp các lớp giao tiếp để debugger điều khiển một JVM đang chạy:

| Thành phần | Vai trò |
|---|---|
| JVM TI (Java Virtual Machine Tool Interface) | Giao diện native mà VM cung cấp để đặt breakpoint, lấy stack frame và nhận sự kiện |
| JDWP (Java Debug Wire Protocol) | Giao thức truyền yêu cầu và sự kiện giữa JVM cần debug và debugger |
| JDI (Java Debug Interface) | API Java cấp cao mà IDE và debugger dùng để đặt breakpoint, đọc biến và điều khiển thực thi |
| jdb | Debugger dòng lệnh của JDK, xây dựng trên JDI |

Khi người dùng đặt breakpoint trong IDE:

1. IDE tạo yêu cầu breakpoint qua JDI.
2. JDI gửi yêu cầu qua JDWP tới debug agent trong JVM.
3. Debug agent chuyển yêu cầu tới VM qua JVM TI.
4. Khi luồng thực thi chạm vị trí đó, VM phát breakpoint event.
5. Event được gửi ngược về debugger để IDE hiển thị stack, source line và biến.

Vì vậy, breakpoint trong IDE và breakpoint trong jdb cùng dựa trên cơ chế debug của JVM. Khác biệt chủ yếu nằm ở giao diện và các tiện ích mà công cụ cung cấp.

Tài liệu: [Oracle Java SE 24 — Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html) và [JPDA Structure Overview](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/architecture.html).

## 3. Chuẩn bị bytecode có thông tin debug

Để debugger ánh xạ bytecode về dòng source và hiển thị biến cục bộ, file class cần có metadata debug phù hợp.

Dùng javac với tùy chọn `-g`:

```bash
javac -g -d out src/BreakpointDemo.java
```

`-g` yêu cầu compiler tạo đầy đủ thông tin debug, gồm:

- Source file information.
- LineNumberTable để ánh xạ bytecode tới dòng source.
- LocalVariableTable để debugger hiển thị tên và giá trị biến cục bộ.

Có thể chọn riêng từng nhóm:

```bash
javac -g:lines,vars,source -d out src/BreakpointDemo.java
```

Nếu biên dịch bằng `-g:none`, debugger có thể thiếu thông tin dòng hoặc tên biến. Khi đó, breakpoint theo dòng, lệnh `locals` hoặc việc xem source có thể không hoạt động như mong đợi.

Dùng `javap -c -l` để kiểm tra bytecode và metadata:

```bash
javap -c -l -classpath out BreakpointDemo
```

Trong output, tìm `LineNumberTable` và `LocalVariableTable`. Nếu thiếu bảng tương ứng, hãy kiểm tra lại cách build và bảo đảm debugger đang nạp đúng file class vừa biên dịch.

Tài liệu: [Oracle Java SE 24 — The javac Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html).

## 4. Các loại breakpoint thường dùng

### 4.1. Line breakpoint

Dừng tại một dòng source có bytecode tương ứng. Đây là loại phổ biến nhất khi biết vị trí cần kiểm tra.

Ví dụ trong jdb:

```text
stop at com.example.OrderService:42
```

Debugger dừng tại instruction đầu tiên gắn với dòng 42. Nếu dòng đó không tạo bytecode thực thi, breakpoint có thể không được đặt hoặc sẽ chuyển tới vị trí bytecode gần nhất phù hợp.

### 4.2. Method breakpoint

Dừng khi một method bắt đầu chạy. Hữu ích khi cần kiểm tra mọi lần gọi vào một API hoặc một method xử lý nghiệp vụ.

```text
stop in com.example.OrderService.calculateTotal
```

Nếu method bị overload, cần chỉ rõ kiểu tham số:

```text
stop in com.example.OrderService.calculateTotal(int,java.lang.String)
```

Có thể đặt breakpoint ở constructor hoặc static initializer khi cần theo dõi quá trình tạo object hay khởi tạo class.

### 4.3. Exception breakpoint

Dừng khi một exception được ném ra. Cách này đặc biệt hữu ích khi exception bị catch ở tầng sâu và stack trace cuối cùng không cho biết vị trí ban đầu.

Trong jdb:

```text
catch all java.lang.IllegalArgumentException
```

JDB cũng hỗ trợ chọn `caught`, `uncaught` hoặc `all`. Ví dụ, `catch uncaught java.lang.IllegalArgumentException` chỉ dừng với exception không được xử lý trong call stack hiện tại.

Gỡ cấu hình exception breakpoint:

```text
ignore all java.lang.IllegalArgumentException
```

### 4.4. Field watchpoint

Watchpoint theo dõi việc truy cập hoặc thay đổi một field. Nó hữu ích khi một biến trạng thái bị thay đổi ở nhiều nơi và chưa biết method nào gây ra giá trị sai.

JDB hỗ trợ:

```text
watch access com.example.Cache.threshold
watch all com.example.Cache.threshold
unwatch all com.example.Cache.threshold
```

`watch access` dừng khi field được đọc; `watch all` theo dõi cả truy cập và sửa đổi theo khả năng của VM. Watchpoint có thể tạo nhiều sự kiện nếu field được đọc hoặc ghi thường xuyên, vì vậy nên chọn đúng field và phạm vi cần điều tra.

### 4.5. Conditional breakpoint và hit count

IDE thường cho phép đặt điều kiện Java expression, hit count hoặc log message khi breakpoint được kích hoạt. Ví dụ, chỉ dừng khi `orderId == 5001` hoặc khi `attempt >= 3`.

Cú pháp `stop` cơ bản của jdb tập trung vào vị trí dòng/method và thread; nó không cung cấp cùng bộ giao diện điều kiện và hit-count như các IDE phổ biến. Nếu cần điều kiện phức tạp, dùng conditional breakpoint trong IDE hoặc viết debugger client dựa trên JDI.

## 5. Khởi chạy ứng dụng dưới jdb

Cách đơn giản nhất là thay lệnh `java` bằng `jdb`.

Biên dịch ứng dụng:

```bash
javac -g -d out src/BreakpointDemo.java
```

Khởi chạy debugger:

```bash
jdb -classpath out BreakpointDemo
```

JDB mở prompt và chờ lệnh. Đặt breakpoint trước khi chạy:

```text
stop at BreakpointDemo:6
run
```

JDB có thể báo breakpoint đang được defer tới khi class được load. Đây là hành vi bình thường khi class chưa được nạp. Khi chương trình chạy tới vị trí đó, debugger sẽ dừng.

Một số lựa chọn hữu ích:

- `jdb -sourcepath src -classpath out BreakpointDemo`: chỉ rõ nơi tìm source và class.
- `jdb -launch -classpath out BreakpointDemo`: khởi chạy debuggee ngay khi debugger mở.
- `jdb -listconnectors`: xem các connector có sẵn.
- `help` tại prompt: xem cú pháp lệnh jdb theo phiên bản đang dùng.

Tài liệu: [Oracle Java SE 24 — The jdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html).

## 6. Ví dụ thực hành: dừng tại breakpoint và xem biến

Ví dụ dưới đây tính tổng tiền sau khi áp dụng mức giảm giá cố định. Breakpoint ở dòng tính discount cho phép kiểm tra dữ liệu trước khi phép tính hoàn tất.

Tạo file `BreakpointDemo.java`:

```java
public class BreakpointDemo {
    private static int discountThreshold = 100;

    static int calculateTotal(int price, int quantity) {
        int subtotal = price * quantity;
        int discount = subtotal >= discountThreshold ? 10 : 0;
        int total = subtotal - discount;
        return total;
    }

    public static void main(String[] args) {
        int unitPrice = 25;
        int quantity = 5;
        int total = calculateTotal(unitPrice, quantity);
        System.out.println("Total: " + total);
    }
}
```

Biên dịch và mở jdb:

```bash
javac -g BreakpointDemo.java
jdb BreakpointDemo
```

Tại prompt jdb, nhập từng lệnh:

```text
stop at BreakpointDemo:6
run
locals
print subtotal
print BreakpointDemo.discountThreshold
next
print discount
cont
```

Ý nghĩa:

1. `stop at BreakpointDemo:6` đặt line breakpoint trước phép tính discount.
2. `run` bắt đầu chương trình.
3. `locals` hiển thị tham số và biến cục bộ trong frame hiện tại.
4. `print subtotal` đọc giá trị subtotal.
5. `print BreakpointDemo.discountThreshold` đọc static field.
6. `next` thực thi dòng hiện tại rồi dừng ở dòng tiếp theo trong cùng method.
7. `print discount` kiểm tra giá trị discount vừa được tính.
8. `cont` tiếp tục cho tới khi chương trình kết thúc hoặc gặp breakpoint khác.

Tại breakpoint, các giá trị mong đợi:

```text
price = 25
quantity = 5
subtotal = 125
BreakpointDemo.discountThreshold = 100
discount = 10
```

Stdout cuối cùng của chương trình:

```text
Total: 115
```

Đây là ví dụ đã được biên dịch bằng `javac -g` và chạy dưới jdb trên OpenJDK Zulu 24.0.2. JDB thực tế dừng tại dòng 6, hiển thị đúng tham số và subtotal, rồi tiếp tục tới kết quả `Total: 115`.

## 7. Các lệnh jdb để quản lý breakpoint và điều khiển chương trình

| Lệnh | Tác dụng |
|---|---|
| `stop at Class:line` | Đặt breakpoint theo dòng |
| `stop in Class.method` | Đặt breakpoint theo method |
| `stop` | Liệt kê breakpoint hiện tại |
| `clear Class:line` | Xóa breakpoint theo dòng |
| `clear Class.method` | Xóa breakpoint theo method |
| `catch all ExceptionClass` | Dừng khi exception được ném |
| `ignore all ExceptionClass` | Gỡ exception breakpoint |
| `watch access Class.field` | Theo dõi việc đọc field |
| `watch all Class.field` | Theo dõi truy cập và thay đổi field |
| `unwatch all Class.field` | Gỡ field watchpoint |
| `cont` | Tiếp tục thực thi |
| `exit` hoặc `quit` | Thoát debugger |

Ví dụ đặt và gỡ breakpoint:

```text
stop in BreakpointDemo.calculateTotal
stop
clear BreakpointDemo:6
clear BreakpointDemo.calculateTotal
```

Khi method có nhiều phiên bản overload, hãy chỉ rõ kiểu tham số để tránh đặt breakpoint nhầm method.

## 8. Step qua code và kiểm tra stack frame

Khi debugger đã dừng, có thể điều khiển chương trình theo từng bước:

| Lệnh | Tác dụng |
|---|---|
| `step` | Thực thi dòng hiện tại và đi vào method được gọi |
| `next` | Thực thi dòng hiện tại nhưng đi qua lời gọi method |
| `step up` | Chạy tới khi method hiện tại trả về caller |
| `cont` | Tiếp tục tới breakpoint hoặc khi chương trình kết thúc |
| `where` | Hiển thị stack trace của thread hiện tại |
| `where all` | Hiển thị stack của các thread |
| `up` / `down` | Di chuyển giữa các stack frame |
| `locals` | Hiển thị biến cục bộ trong frame |
| `print expression` | Đánh giá và in giá trị expression |
| `dump expression` | In thông tin object |
| `threads` | Liệt kê thread |
| `thread <id>` | Chọn thread làm thread hiện tại |
| `list` | Hiển thị source quanh vị trí hiện tại |

Ví dụ:

```text
where
up
locals
print this
down
next
cont
```

Khi kiểm tra biến, hãy chú ý frame đang được chọn. Cùng một tên biến có thể tồn tại ở nhiều method hoặc nhiều lần gọi đệ quy. `up` và `down` thay đổi frame hiện tại, do đó kết quả `locals` và `print` cũng thay đổi theo.

## 9. Đặt breakpoint khi ứng dụng đã chạy

Có thể attach debugger vào JVM đã khởi chạy nếu JVM được bật debug agent.

Ví dụ khởi chạy ứng dụng với JDWP socket trên loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out BreakpointDemo
```

Attach từ terminal khác:

```bash
jdb -attach 127.0.0.1:5005
```

Các tham số quan trọng:

- `transport=dt_socket`: dùng TCP socket transport.
- `server=y`: JVM đích lắng nghe kết nối debugger.
- `address=127.0.0.1:5005`: chỉ lắng nghe trên loopback tại port 5005.
- `suspend=n`: ứng dụng được phép chạy trước khi debugger attach.

Nếu cần debugger kết nối trước khi `main()` bắt đầu, dùng `suspend=y`. Đây cũng là giá trị mặc định của JDWP agent nếu không chỉ định. Với `suspend=n`, breakpoint ở đầu chương trình có thể bị bỏ lỡ nếu ứng dụng chạy qua vị trí đó trước khi debugger attach.

Trên Windows, có thể dùng shared memory transport `dt_shmem` khi cả JVM và debugger chạy trên cùng máy. Kiểm tra connector có sẵn bằng `jdb -listconnectors`.

Để attach qua ProcessAttach connector vào một JVM local đã bật debug agent:

```bash
jdb -connect com.sun.jdi.ProcessAttach:pid=<PID>
```

PID là process ID của JVM đích. Connector này yêu cầu JVM hỗ trợ attach và được khởi chạy với `server=y`.

## 10. Remote debugging an toàn qua SSH tunnel

JDWP có thể truyền các yêu cầu điều khiển JVM. Theo đặc tả Oracle, JDWP cho phép đọc và sửa cả private field, cũng như gọi private method; vì vậy, ai truy cập được debug port có thể kiểm soát sâu tiến trình.

Không mở JDWP port ra Internet hoặc mạng không tin cậy. Cấu hình JVM chỉ lắng nghe trên loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

Từ máy chạy debugger, tạo SSH tunnel:

```bash
ssh -L 5005:127.0.0.1:5005 user@server
```

Sau đó kết nối JDB qua tunnel:

```bash
jdb -attach 127.0.0.1:5005
```

Cách này giữ debug port trên loopback của server và dùng SSH để chuyển tiếp kết nối. Nếu buộc phải cho phép kết nối trực tiếp qua mạng, giới hạn nguồn IP bằng firewall và tùy chọn `allow` của JDWP, đồng thời chỉ mở trong thời gian và phạm vi cần thiết.

Tài liệu: [Oracle Java SE 24 — Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html) và [JDWP Protocol](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html).

## 11. Breakpoint trong IDE

Các IDE như IntelliJ IDEA, Eclipse và Visual Studio Code cung cấp giao diện trực quan trên nền tảng Java debugger/JDI.

Thông thường, bạn có thể:

- Nhấp vào lề trái của dòng source để bật/tắt line breakpoint.
- Đặt method breakpoint hoặc exception breakpoint.
- Tạo field watchpoint nếu debugger và VM hỗ trợ.
- Đặt condition expression để chỉ dừng khi điều kiện đúng.
- Đặt hit count để dừng sau một số lần gọi nhất định.
- Dùng logpoint để ghi thông tin mà không dừng thread.
- Chọn suspend all threads hoặc chỉ suspend event thread.
- Xem Variables, Watches, Call Stack, Threads và Evaluate Expression.

Conditional breakpoint rất hữu ích khi lỗi chỉ xảy ra với một dữ liệu cụ thể. Ví dụ, đặt điều kiện `orderId == 5001` thay vì dừng ở hàng nghìn request.

Khi dùng expression có gọi method, cần lưu ý debugger có thể thực thi method đó trong debuggee. Method có side effect hoặc chờ lock có thể làm thay đổi trạng thái ứng dụng trong lúc điều tra.

## 12. Breakpoint trong ứng dụng đa luồng

Breakpoint có thể làm thay đổi timing của chương trình đa luồng. Khi dừng một thread, các thread khác có thể tiếp tục hoặc cùng bị dừng tùy suspend policy.

Trong JDB, mặc định khi breakpoint hit, debugger suspend tất cả thread. Có thể chỉ dừng thread phát sinh sự kiện bằng tùy chọn `thread` trong lệnh `stop`, theo cú pháp trợ giúp của jdb:

```text
stop thread <thread-id> at BreakpointDemo:6
```

Một số lưu ý:

- Dừng tất cả thread có thể làm request khác bị chờ và khiến triệu chứng timing biến mất.
- Dừng thread đang giữ monitor có thể khiến thread khác chờ lock.
- Breakpoint trong critical section có thể làm thay đổi thứ tự acquire/release lock.
- Lỗi race condition có thể không tái hiện khi debugger làm chậm chương trình.
- Khi điều tra concurrency, kết hợp breakpoint với log có correlation ID, thread dump và Java Flight Recorder.

Breakpoint giúp xem trạng thái tại một thời điểm, nhưng không thay thế việc thu thập chuỗi sự kiện theo thời gian.

## 13. Breakpoint và virtual thread

Virtual thread có thể được tạo với số lượng lớn và vòng đời ngắn. Nếu debugger theo dõi mọi virtual thread liên tục, lượng event và metadata có thể làm debugger bị quá tải.

Trong JDK 24, JDB mặc định không theo dõi mọi virtual thread ngay khi chúng được tạo. Nó theo dõi virtual thread khi có event liên quan, chẳng hạn breakpoint event.

Có thể yêu cầu JDB theo dõi tất cả thread, bao gồm virtual thread:

```bash
jdb -trackallthreads -classpath out BreakpointDemo
```

Tùy chọn này cũng bật cơ chế include virtual threads khi JDB khởi chạy ứng dụng. Khi attach vào JVM đã chạy, một số virtual thread được tạo trước thời điểm attach có thể không được debug agent liệt kê.

Chỉ bật theo dõi toàn bộ virtual thread khi cần phân tích luồng cụ thể và đã cân nhắc số lượng thread. Với hệ thống dùng virtual thread quy mô lớn, hãy chọn breakpoint hẹp và kết hợp JFR để quan sát sự kiện theo thời gian.

Tài liệu: [Oracle Java SE 24 — Working With Virtual Threads in jdb](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html).

## 14. Lỗi thường gặp khi breakpoint không hoạt động

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Breakpoint không hit | Code không đi qua dòng đó hoặc dòng không có bytecode | Xác nhận flow thực tế và chọn dòng có executable statement |
| JDB báo deferred breakpoint | Class chưa được load | Đây là hành vi bình thường; tiếp tục chạy để class được load |
| Breakpoint dừng ở dòng khác | Source và bytecode không cùng build hoặc line mapping khác | Clean/rebuild đúng source rồi xác nhận classpath |
| Không xem được local variable | Thiếu LocalVariableTable | Biên dịch lại với `javac -g` hoặc `-g:vars` |
| Không tìm thấy source | Source path không đúng | Dùng `-sourcepath` hoặc lệnh `use` trong jdb |
| Method breakpoint không hit | Sai tên class, method hoặc overload | Kiểm tra package và chỉ rõ kiểu tham số |
| Exception breakpoint dừng quá nhiều | Theo dõi cả exception được catch | Chọn `uncaught` hoặc loại exception cụ thể |
| Field watchpoint không được hỗ trợ | VM không cung cấp capability access/modification watchpoint | Kiểm tra thông báo debugger và khả năng của VM |
| JDB không attach được | Sai host/port, JDWP agent chưa bật hoặc firewall chặn | Kiểm tra command line JVM, connector và port |
| Debugger không thấy tất cả virtual thread | Cơ chế theo dõi virtual thread mặc định có giới hạn | Dùng `-trackallthreads` khi phù hợp |
| Chương trình treo khi dừng breakpoint | Thread khác chờ lock do thread bị suspend đang giữ | Xem stack của các thread và cân nhắc suspend policy |

## 15. Quy trình sử dụng breakpoint hiệu quả

Khi điều tra một lỗi cụ thể, có thể thực hiện theo thứ tự:

1. Tái hiện lỗi và ghi lại input, request ID, thời điểm và môi trường.
2. Xác định method hoặc nhánh code có liên quan.
3. Kiểm tra source và class có cùng build, có debug metadata.
4. Đặt một breakpoint gần điểm dữ liệu bắt đầu sai.
5. Khi dừng, xem stack frame, tham số và biến cục bộ.
6. Dùng `step` hoặc `next` để theo dõi phép tính và nhánh điều kiện.
7. Nếu chưa biết ai sửa field, đặt watchpoint.
8. Nếu lỗi bắt đầu từ exception, đặt exception breakpoint để bắt vị trí throw.
9. Xóa breakpoint tạm sau khi đã xác định nguyên nhân.
10. Sửa code, chạy test hồi quy và kiểm tra lại với input gây lỗi.

Nên đặt breakpoint gần điều kiện lỗi đầu tiên, thay vì đặt rải rác trên toàn bộ ứng dụng. Mỗi lần dừng hãy ghi lại giá trị quan trọng và giả thuyết đang kiểm tra để tránh thay đổi nhiều biến cùng lúc.

## 16. Tổng kết

Breakpoint là cơ chế debugger dùng để tạm dừng JVM tại vị trí hoặc sự kiện đã chọn, giúp quan sát dữ liệu và điều khiển chương trình theo từng bước.

Những điểm cần nhớ:

- Biên dịch với `javac -g` để có line number và local variable metadata.
- Dùng `stop at` cho line breakpoint và `stop in` cho method breakpoint trong jdb.
- Dùng `catch` để dừng khi exception được ném và `watch` để theo dõi field.
- Dùng `locals`, `print`, `dump`, `where`, `step`, `next` và `cont` để kiểm tra trạng thái.
- JDB có thể khởi chạy JVM mới hoặc attach vào JVM đã bật JDWP.
- JPDA kết hợp JVM TI, JDWP và JDI để chuyển yêu cầu debugger thành sự kiện trong VM.
- Với virtual thread, hiểu giới hạn theo dõi mặc định và dùng `-trackallthreads` khi thực sự cần.
- Breakpoint có thể làm thay đổi timing và suspend thread; dùng có chủ đích, đặc biệt trong hệ thống đa luồng.
- JDWP có quyền điều khiển sâu JVM; giữ debug port trên loopback hoặc qua SSH tunnel.

**Tài liệu tham khảo chính thức:**

- [Oracle Java SE 24 — The jdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html)
- [Oracle Java SE 24 — Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html)
- [Oracle Java SE 24 — JPDA Structure Overview](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/architecture.html)
- [Oracle Java SE 24 — Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [Oracle Java SE 24 — JDWP Protocol](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html)
- [Oracle Java SE 24 — The javac Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
