# 4.3. Khám phá lệnh bằng help và đọc cú pháp, tùy chọn, mức Impact của từng lệnh

`jcmd` là công cụ gửi **diagnostic commands** tới một JVM đang chạy. Trước khi yêu cầu thread dump, heap histogram, heap dump hoặc ghi JFR, người vận hành cần biết **JVM đích có hỗ trợ lệnh không, cú pháp chính xác là gì, tham số nào bắt buộc, lệnh tác động đến ứng dụng ra sao**. Câu trả lời đáng tin cậy nhất xuất phát từ chính **`help` của JVM đích**, rồi được đối chiếu với tài liệu của đúng JDK/vendor/version.

Bài học thuộc mục **4. Công cụ jcmd**, tập trung vào quy trình khám phá và **đọc** help, thay vì mặc định mọi lệnh `jcmd` đều vô hại hoặc đưa ngay các lệnh có thể làm JVM tạm dừng/chỉnh trạng thái vào production.

**Sau bài học, bạn có thể:**
- Phân biệt `jcmd -h`, `jcmd -l`, `jcmd <PID> help`, `jcmd <PID> help <COMMAND>` và `jcmd <PID> help -all`.
- Đọc chính xác các trường **Description, Impact, Permission, Syntax, Options, Arguments, kiểu dữ liệu và default value** trong output help.
- Diễn giải **Impact: Low / Medium / High** theo đúng ý nghĩa của mức tác động; phân biệt impact với **quyền truy cập** và **tác dụng thay đổi trạng thái**.
- Chọn lệnh phù hợp với mục tiêu đo, yêu cầu vận hành và tài nguyên có sẵn; giải quyết lỗi cú pháp hoặc thiếu command mà không thử tùy tiện trên hệ thống thật.

## 1. Hiểu đúng ba tầng của jcmd

Không có một lệnh `help` chung thay thế tất cả. Cần tách:

| Tầng | Ví dụ | Mục đích |
| --- | --- | --- |
| **Tiện ích jcmd ở phía người gọi** | `jcmd -h` hoặc `jcmd --help` nếu bản công cụ hỗ trợ | Xem cách sử dụng command-line launcher, cách chọn target và các switch của chương trình `jcmd` |
| **Danh sách JVM nhìn thấy** | `jcmd -l` | Tìm những Java process có thể liệt kê trong môi trường hiện tại |
| **Diagnostic command được JVM đích công bố** | `jcmd 12345 help` | Hỏi **JVM có PID 12345** những command nó hỗ trợ |
| **Chi tiết một diagnostic command** | `jcmd 12345 help Thread.print` | Đọc mô tả, impact, permission, syntax, options và arguments của `Thread.print` ở đúng JVM đó |
| **Chi tiết toàn bộ command** | `jcmd 12345 help -all` | In help đầy đủ cho các command đã được công bố; output thường dài |

Ở các ví dụ, **12345 chỉ là PID minh họa**, phải thay bằng PID thực tế và đúng namespace. `jcmd -h` là trợ giúp của **chương trình công cụ**; `jcmd 12345 help` là lệnh diagnostic `help` được gửi vào **JVM đang chạy**. Khác biệt này rất quan trọng: công cụ phía người gọi có thể đến từ một JDK khác với JVM đích, còn danh sách command phụ thuộc phiên bản và trạng thái JVM đích.

Một thứ tự khám phá hợp lý:

~~~bash
jcmd -h
jcmd -l
jcmd 12345 help
jcmd 12345 help Thread.print
~~~

Nếu cần xem toàn bộ mô tả thay vì một command:

~~~bash
jcmd 12345 help -all
~~~

**Không cần thực thi `Thread.print`, `GC.heap_dump` hoặc một lệnh GC chỉ để đọc help của nó.** Giai đoạn khám phá trước tiên là giai đoạn tra cứu.

## 2. Xác định đúng JVM đích trước khi hỏi help

`jcmd` cần kết nối tới JVM còn sống, thường trên cùng máy và dưới **effective user/group** tương ứng với process; quyền attach, runtime image và chính sách hệ điều hành/container đều có thể ảnh hưởng.

Quy trình định danh tối thiểu:

1. Xác định **service, container/pod, host, PID, thời điểm quan sát, Java vendor/version**.
2. Thử `jcmd -l` trong môi trường thích hợp, đối chiếu tên main class/JAR với service mong muốn.
3. Nếu không thấy process nằm trong Docker/PID namespace khác, tìm PID bằng công cụ process/container **ở đúng namespace**. Việc `jcmd -l` không liệt kê được **không tự chứng minh** process đã chết.
4. Gọi `jcmd <PID> help` và bảo đảm PID còn đại diện cho đúng JVM, tránh PID bị tái sử dụng sau restart.
5. Nếu attach thất bại, kiểm tra user/group, quyền truy cập, cơ chế attach có bị tắt, JDK có `jcmd` hay không, cấu hình filesystem/namespace và trạng thái JVM.

Hai hình thức lựa chọn mục tiêu sau cần hiểu trước khi sử dụng:
- `jcmd 0 <COMMAND>` có thể gửi command tới **mọi JVM** mà tiện ích thấy.
- `jcmd <MAIN_CLASS> <COMMAND>` có thể khớp **nhiều process** có cùng main class.

Vì vậy, khi học hay chẩn đoán một JVM cụ thể, **ưu tiên PID xác minh trực tiếp**, tránh broadcast ngoài ý muốn. Hỏi help theo PID cũng giúp lấy đúng cú pháp của phiên bản đích.

Nếu chương trình đã thoát hoặc bị JVM fatal crash, `jcmd` không thể attach vào tiến trình cũ; khi đó dùng log, `hs_err`, core dump, exit reason và thông tin deployment để phân tích, không thử PID mới mà chưa xác minh.

## 3. Đọc một trang help từ trên xuống

Ví dụ:

~~~bash
jcmd 12345 help Thread.print
~~~

Trên một bản HotSpot/OpenJDK, thông tin có cấu trúc tương tự sau (các câu chữ/format cụ thể có thể khác theo bản build):

~~~text
Thread.print
Prints all threads with stacktraces.

Impact: Medium: Depends on the number of threads.
Permission: java.lang.management.ManagementPermission(monitor)

Syntax : Thread.print [options]

Options:
    -l : [optional] Prints java.util.concurrent locks (BOOLEAN, false)
~~~

Đây là **ví dụ giản lược để học cách đọc**, không phải stdout cố định trên mọi JDK. Hãy chia nó thành từng câu hỏi:

| Trường trong help | Ý nghĩa | Cần ghi nhớ |
| --- | --- | --- |
| **Tên command** | Tên diagnostic command, ví dụ `Thread.print` | Thường phân biệt hoa/thường và có dấu chấm trong tên |
| **Description** | Mục đích lệnh | Cho biết công việc lệnh *thực hiện*, không hứa rằng mọi lần chạy có cùng hiệu năng |
| **Impact** | Phân loại mức tác động dự kiến lên JVM đích | Có thể kèm điều kiện phụ thuộc số thread, heap size hoặc nội dung |
| **Permission** | Quyền runtime/Java được mô tả cho command | Không thay thế quyền OS/container để attach |
| **Syntax** | Dạng lời gọi sau `jcmd <PID>` | Ký hiệu trong ngoặc vuông là **cú pháp mô tả**, không gõ nguyên dấu `[` và `]` |
| **Options** | Tham số theo tên, ví dụ `-l`, `-all`, `name=...` | Xem kiểu, default, optional và yêu cầu về cách viết |
| **Arguments** | Đối số theo vị trí, ví dụ `filename` | Kiểm tra có bắt buộc không và thứ tự theo help |

Dòng `Syntax : Thread.print [options]` nghĩa là chạy:

~~~bash
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
~~~

chứ **không** gõ:

~~~text
jcmd 12345 Thread.print [options]
~~~

Ở lệnh `Thread.print`, `-l` là boolean option để in thêm thông tin về `java.util.concurrent` locks; **`-l` ở đây khác `jcmd -l`** (liệt kê process), dù cùng cách viết. Ngữ cảnh quyết định ý nghĩa.

### Options, arguments, optional/default và kiểu dữ liệu

Khi đọc một parameter, cần thu đủ bốn thuộc tính:

1. **Tên**: ví dụ `-l`, `-all`, `name`, `duration` hoặc positional `filename`.
2. **Kiểu dữ liệu**: `BOOLEAN`, `STRING`, `INT/INTEGER`, duration có hậu tố đơn vị theo mô tả...
3. **Optional hay required**: `[optional]` hoặc `(Optional)` chỉ tham số có thể bỏ; `no default value` trên một argument bắt buộc nghĩa là phải truyền giá trị.
4. **Default**: giá trị khi không truyền option; nó **không phải** giá trị bạn đã chủ động cấu hình.

Một số command yêu cầu option theo dạng **`key` hoặc `key=value`**, và help ghi rõ quy tắc. Ví dụ boolean có thể viết `-all` hoặc dạng tương đương nếu command hỗ trợ; string/duration thường cần `name=myrecording`, `duration=60s`. Không giả định mọi command hiểu cùng tên `-all` hoặc cùng hậu tố `m`, `s`, `k`; mỗi command có grammar riêng.

**Argument có khoảng trắng:** đường dẫn hoặc giá trị chứa space phải được shell quote thích hợp trước khi đến `jcmd`. Cách quote trên Bash, PowerShell và cmd.exe có thể khác nhau. Cú pháp được giúp đỡ bởi `jcmd ... help <COMMAND>` chỉ nói **cách command nhận tham số**, còn shell xử lý ký tự quote/escape trước khi chương trình nhận chúng. Khi không chắc, dùng đường dẫn không chứa khoảng trắng trong môi trường thử nghiệm và kiểm tra trực tiếp ở đúng shell đang dùng.

**Vị trí của option và argument:** đọc `Syntax` cùng phần `Options/Arguments`. Với `GC.heap_dump`, `filename` là positional argument, khác các flag lựa chọn. Đừng biến mọi tham số thành `name=value` chỉ vì một command khác dùng dạng đó.

## 4. Impact: Low, Medium, High thực sự nói gì?

`Impact` trong help của HotSpot là **đánh giá định tính về mức tác động dự kiến** khi thực thi diagnostic command lên JVM đích, chứ không phải chứng nhận không phát sinh pause, không gây tốn đĩa, không làm đổi trạng thái hay có quyền chạy an toàn ở production.

| Mức | Cách hiểu vận hành | Ví dụ trong tài liệu JDK 17 |
| --- | --- | --- |
| **Low** | Thường ít tác động tương đối; vẫn có chi phí và có thể làm thay đổi trạng thái nếu command là loại điều khiển | `VM.version`, `VM.flags`, `VM.command_line`, `VM.info`; `JFR.start` cũng ghi Low dù **bắt đầu recording** |
| **Medium** | Có thể có công việc đáng kể; thời gian phụ thuộc workload và quy mô dữ liệu | `Thread.print` (phụ thuộc số thread), `GC.heap_info`, `VM.native_memory` |
| **High** | Có khả năng tốn tài nguyên/pause đáng kể; đánh giá trước khi dùng trên hệ thống tải thật | `GC.class_histogram`, `GC.heap_dump`; phụ thuộc heap size/content |

**Hai điều cần nhớ:**

- `Low` **không đồng nghĩa với “read-only”**: `VM.set_flag` được ghi Impact: Low nhưng **thay đổi một VM flag**; `JFR.start` Impact: Low nhưng **khởi động recording**, có overhead/tiêu thụ dung lượng; `ManagementAgent.start` có thể bật management agent. Cần đọc **Description** và hậu quả, không nhìn mỗi nhãn Impact.
- `Medium/High` **không phải số milliseconds cố định**. `Thread.print` phụ thuộc số thread; `GC.heap_dump` phụ thuộc heap size/content, dung lượng đĩa, hệ thống I/O và có thể yêu cầu full GC. Một command có thể ảnh hưởng đáng kể trên workload lớn nhưng ít hơn trên máy thử nghiệm nhỏ.

**Bốn câu hỏi phải hỏi trước khi execute một command:**
1. **Thao tác gì?** In thông tin, bắt đầu thu thập, yêu cầu GC, ghi file hay sửa runtime flag?
2. **Impact nào?** Có điều kiện “depends on heap size/number of threads” không?
3. **Tốn gì?** CPU, pause, RAM, đĩa, I/O, kích thước output, dữ liệu nhạy cảm?
4. **Có phù hợp mục tiêu hiện tại không?** Có cách ít tác động hơn, hoặc cần báo trước vận hành trong cửa sổ cho phép?

Nếu chưa trả lời được, chỉ đọc `help` để lấy thông tin, **không thử command thực thi trên production** để xem nó làm gì.

## 5. Ví dụ đọc help theo mục tiêu

### 5.1. Kiểm tra JVM flags: lệnh thường có Impact Low

~~~bash
jcmd 12345 help VM.flags
~~~

Đọc trong help: command dùng để in giá trị VM flags; Impact: **Low**; cú pháp `VM.flags [options]`; một boolean option `-all` có default false cho phép in **tất cả flags được JVM hỗ trợ**. Khi cần thực thi lệnh đọc sau khi đã định danh đúng PID:

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
~~~

Bản `-all` có thể in **rất nhiều dòng**, do đó cần cân nhắc nơi lưu và khả năng che secrets. `-all` trong `VM.flags` không đồng nghĩa `-all` của `GC.heap_dump` hoặc `help`.

### 5.2. Thread dump: Impact Medium theo số lượng thread

~~~bash
jcmd 12345 help Thread.print
~~~

Help nêu `Syntax : Thread.print [options]`, một lựa chọn `-l` mặc định false, Impact **Medium** vì chi phí liên quan số lượng thread. Nếu cần chạy để điều tra lock ownership, đọc kỹ số thread và môi trường đang vận hành:

~~~bash
jcmd 12345 Thread.print -l
~~~

Output có thể rất dài, đặc biệt với nhiều worker. `Thread.print` là **snapshot**, một thread ở `WAITING` không tự chứng minh deadlock. Nếu cần phân tích stall, thường phải so sánh nhiều snapshot cùng timestamp và tiến độ xử lý.

### 5.3. Heap histogram: Impact High

~~~bash
jcmd 12345 help GC.class_histogram
~~~

Tài liệu JDK 17 mô tả Impact **High**, phụ thuộc heap size/content. Command cho thống kê heap theo lớp đối tượng; option `-all` trong help của command này chỉ định có xem cả các đối tượng chưa tới mức không thể truy cập hay không. Không đọc nhãn `-all` rồi tưởng nó chỉ “in nhiều cột” như ở `VM.flags`. Nếu mục tiêu chỉ là xác nhận kích thước heap chung, có thể xem help của `GC.heap_info` trước khi cân nhắc histogram.

### 5.4. Heap dump: Impact High, có positional filename

~~~bash
jcmd 12345 help GC.heap_dump
~~~

Các phần quan trọng trong tài liệu JDK 17:

- **Description:** tạo file heap dump dạng HPROF.
- **Impact:** High, phụ thuộc kích thước/nội dung heap.
- **Syntax:** `GC.heap_dump [options] [arguments]`.
- **Options:** `-all` là boolean optional, default false; bật để dump cả đối tượng unreachable theo mô tả.
- **Arguments:** `filename` kiểu STRING **bắt buộc**, không có default.
- **Hành vi:** trong JDK 17, lệnh thường **yêu cầu full GC trước khi dump**, trừ trường hợp dùng `-all` theo điều kiện được tài liệu nêu.

Cú pháp mẫu để **hiểu vị trí argument**, không phải khuyến nghị chạy ngay:

~~~text
jcmd 12345 GC.heap_dump /var/tmp/heap-12345.hprof
jcmd 12345 GC.heap_dump -all /var/tmp/heap-12345-all.hprof
~~~

Dump có thể lớn, gây pause, lấp đầy đĩa và chứa dữ liệu nhạy cảm trong object graph. Trước khi chạy thật, phải kiểm tra nơi ghi được bởi process, dung lượng, mục đích chẩn đoán và điều kiện vận hành. **Filename không có default** nghĩa là không được bỏ đối số file để chờ command tự chọn đường dẫn.

### 5.5. JFR.start: Impact Low nhưng có tác dụng

~~~bash
jcmd 12345 help JFR.start
~~~

Help trình bày options như `name`, `duration`, `settings`, `filename`, `delay`, `disk`. Ví dụ **cú pháp minh họa** khi có quyết định thu JFR trên tiến trình phù hợp:

~~~text
jcmd 12345 JFR.start name=diagnose settings=profile duration=60s filename=/var/tmp/diagnose.jfr
~~~

`JFR.start` trong tài liệu JDK 17 có Impact Low, nhưng nó **bắt đầu ghi recording** và có thể ghi ra file/tiêu thụ tài nguyên. `settings=profile` thu sự kiện chi tiết hơn `default`; không coi overhead là bằng không. Với một tác vụ chỉ muốn biết có recording nào đang chạy, khám phá `help JFR.check` rồi dùng command quan sát phù hợp thay vì tự động start.

### 5.6. VM.set_flag: ví dụ phản chứng về Impact Low

~~~bash
jcmd 12345 help VM.set_flag
~~~

Tài liệu JDK 17 ghi **Impact: Low**, nhưng Description nói rõ **đặt giá trị flag của JVM** và Permission liên quan quyền `control`. Đây là **lệnh thay đổi trạng thái**, hoàn toàn khác `VM.flags` chỉ đọc. Nếu mục tiêu của bạn là kiểm chứng cấu hình hiện tại thì dùng `VM.flags`, không chạy `VM.set_flag`. Đây là ví dụ quan trọng cho thấy **Impact và “read-only/write” là hai trục phân loại riêng**.

### 5.7. GC.run: Medium nhưng không phải lệnh đọc

~~~bash
jcmd 12345 help GC.run
~~~

`GC.run` được tài liệu mô tả là gọi `System.gc()`; Impact Medium phụ thuộc heap size/content. Có nghĩa đây là **yêu cầu hành động GC**, không phải đo snapshot. Không dùng lệnh này chỉ để “xem JVM có GC không”. Cần phân biệt với `GC.heap_info` (lấy thông tin heap) và `GC.class_histogram` (tạo thống kê có Impact cao).

## 6. Ba cặp tên giống nhau dễ gây nhầm

### 6.1. `help -all` với `VM.flags -all` với `GC.heap_dump -all`

| Câu lệnh | Ý nghĩa của `-all` |
| --- | --- |
| `jcmd 12345 help -all` | Hiển thị **trợ giúp** cho tất cả diagnostic commands JVM công bố |
| `jcmd 12345 VM.flags -all` | In tất cả VM flags được hỗ trợ cùng giá trị theo khả năng JVM |
| `jcmd 12345 GC.heap_dump -all /path/file.hprof` | Yêu cầu dump bao gồm cả đối tượng unreachable; tác động và nội dung khác cách dump mặc định |

Không có quy tắc “`-all` luôn làm cùng một việc”; phải đọc `help <COMMAND>`.

### 6.2. `jcmd -l` với `Thread.print -l`

- `jcmd -l`: **tùy chọn của công cụ jcmd** để liệt kê JVM.
- `jcmd 12345 Thread.print -l`: **tùy chọn của diagnostic command** để hiện thêm lock thông tin về `java.util.concurrent`.

Hai option thuộc hai bộ phân tích khác nhau. Việc có ký hiệu giống nhau không đảm bảo nghĩa giống nhau.

### 6.3. `-Dkey=value` khi khởi động JVM với `name=value` của diagnostic command

- `java -Dapp.mode=prod MyApp`: thiết lập Java system property **khi startup**.
- `jcmd 12345 JFR.start name=diagnose ...`: truyền **named option của diagnostic command** tới JVM đã chạy.

Không dùng `-D` cho mọi option của `jcmd`, và đừng tưởng command options tự động xuất hiện trong `VM.system_properties`.

## 7. Thực hành trên chương trình Java 17+ tự tạo

Mục tiêu: có một JVM thật, còn sống, đủ để bạn thử **chỉ các lệnh help**. Không cần cố ý tạo memory leak, deadlock hay kích hoạt heap dump.

Tạo file **JcmdHelpTarget.java** với nội dung đầy đủ:

~~~java
public final class JcmdHelpTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("JcmdHelpTarget ready");
        Thread.sleep(180_000L);
    }
}
~~~

Biên dịch và chạy tại **Terminal 1** bằng JDK 17 trở lên:

~~~bash
javac JcmdHelpTarget.java
java JcmdHelpTarget
~~~

**Stdout chính xác ngay sau khi bắt đầu:**

~~~text
JcmdHelpTarget ready
~~~

Chương trình giữ main thread ngủ khoảng 180 giây, không in thêm dòng nào khi kết thúc bình thường. Con số là **thời gian sống của ứng dụng ví dụ**, không phải độ dài tác vụ `jcmd`. Nếu quá khoảng này, JVM thoát và cần chạy lại để tiếp tục thí nghiệm. Có thể dừng bằng Ctrl+C sau khi hoàn thành.

Trong **Terminal 2** của cùng máy và đúng người dùng:

~~~bash
jcmd -l
~~~

Tìm dòng chứa `JcmdHelpTarget`, ghi lại **PID thực tế**. Giả sử PID là 12345, khám phá lần lượt:

~~~bash
jcmd 12345 help
jcmd 12345 help VM.version
jcmd 12345 help Thread.print
jcmd 12345 help GC.heap_dump
jcmd 12345 help JFR.start
jcmd 12345 help VM.set_flag
jcmd 12345 help -all
~~~

Danh sách ở trên **chỉ gọi `help`**, không thực thi dump hay thay đổi flag. Không có một stdout cố định cho `jcmd` vì PID, vendor, JDK build, danh mục command và cách trình bày help phụ thuộc JVM đích. Kết quả bắt buộc của chương trình `JcmdHelpTarget` là dòng `JcmdHelpTarget ready` đã nêu.

Ghi ra bảng quan sát cho **từng** command:

| Command | Description | Impact | Permission | Syntax | Tham số đặc biệt | Thao tác đọc hay có side effect |
| --- | --- | --- | --- | --- | --- | --- |
| `VM.version` | Đọc bản JVM | Low | Theo help | Không có positional args điển hình | Không | Đọc |
| `Thread.print` | In thread stacks | Medium | Theo help | `Thread.print [options]` | `-l` | Đọc snapshot, tốn công lấy mẫu |
| `GC.heap_dump` | Ghi heap HPROF | High | Theo help | `GC.heap_dump [options] [arguments]` | `filename` bắt buộc, `-all` | Ghi file/đòi hỏi tài nguyên; có thể full GC |
| `JFR.start` | Bắt đầu Flight Recording | Low | Theo help | Nhiều named options | `duration`, `filename`, `settings` | Thay đổi trạng thái recording |
| `VM.set_flag` | Thay giá trị flag | Low | Quyền `control` theo help | Positional flag name/value | Chỉ áp dụng flag đủ điều kiện | Thay đổi cấu hình VM |

Bảng này đưa ra **dự kiến theo JDK 17**; khi thực hành phải ưu tiên thông tin thực tế do JVM in. Nếu một command không được liệt kê, không tự suy rằng đó là lỗi của `jcmd`: có thể do bản JVM, vendor, môi trường hoặc command bị ẩn/không hỗ trợ.

### Bài tập nhỏ

1. Trong cùng JVM, so sánh `help VM.flags` và `help GC.heap_dump`; xác định command nào chỉ in thông tin, command nào tạo file và điều gì khiến Impact khác nhau.
2. Tìm `-all` của ba command `help`, `VM.flags` và `GC.heap_dump`; giải thích vì sao không thể hoán đổi chúng.
3. Tìm một command có **Low Impact nhưng thay đổi trạng thái** và trình bày hai bằng chứng từ help (Description và Permission/Options).
4. Xem `help Thread.print` và trả lời option `-l` là optional hay required, default là gì, và vì sao số lượng thread ảnh hưởng chi phí.
5. Khi JVM ví dụ hết thời gian sống, thử lại `jcmd 12345 help` có thể thất bại hoặc PID bị tái sử dụng; nêu cách xác minh process trước lần thử tiếp theo.

## 8. Ra quyết định theo mục đích và mức tác động

Trước khi gửi command thực thi, viết ra yêu cầu quan sát cụ thể. Một nhánh thực hành phù hợp:

~~~text
Xác định triệu chứng cần điều tra
       |
       v
Định danh đúng JVM/PID + Java vendor/version
       |
       v
jcmd <PID> help
       |
       v
jcmd <PID> help <COMMAND>
       |
       v
Đọc Description + Syntax + Options/Arguments
       |
       v
Đọc Impact + Permission + các side effects
       |
       +-- Chỉ cần dữ liệu cấu hình nhỏ --> cân nhắc lệnh đọc Low
       |
       +-- Cần thread/heap statistics --> cân nhắc Medium/High theo tải
       |
       +-- Cần dump/record/change flag --> xác định tài nguyên, cửa sổ vận hành
       |
       v
Thực thi có mục đích; ghi timestamp, PID, output và tác động quan sát
~~~

**Impact là một tín hiệu trong quyết định**, không phải chính sách “Low thì auto-run, High thì cấm”. Một lệnh Low có thể thay đổi VM; một lệnh High có thể là lựa chọn cần thiết khi đang xử lý sự cố nhưng cần chuẩn bị. Hãy xem **mục đích thực tế và hậu quả** trước, rồi mới chọn công cụ.

### Tình huống A: Cần xác minh tham số heap

Nên bắt đầu từ `help VM.flags` và `help VM.command_line`; sau đó dùng các lệnh đọc tương ứng để so sánh flag hiệu lực với startup args. Không tạo heap dump chỉ để biết `-Xmx` đang là bao nhiêu.

### Tình huống B: Nghi deadlock

Xem `help Thread.print` và Impact Medium, số thread và cách lưu output. Thu những snapshot có timestamp khi cần, tìm lock owner/wait chain. `Thread.print` không tự chứng minh nguyên nhân trong một lần lấy mẫu.

### Tình huống C: Nghi memory leak

`GC.heap_dump` có thể hữu ích để phân tích retention nhưng thuộc High Impact và tạo file lớn; trước tiên cân nhắc `GC.heap_info`, metrics, GC logs/JFR và tiêu chí cần heap dump. Không xem `-all` là cách làm dump “an toàn hơn” cho mọi trường hợp; nó thay đổi tập đối tượng và liên quan hành vi GC của command.

### Tình huống D: Chỉ muốn biết chương trình có JFR nào đang chạy

`help JFR.check` cho phép xem cú pháp lệnh quan sát; không khởi động recording mới bằng `JFR.start` nếu mục tiêu chỉ là kiểm tra trạng thái. Nhãn Low của `JFR.start` không làm nó trở thành lệnh đọc.

### Tình huống E: Cần biết VM có hỗ trợ một command mới

Lệnh có thể xuất hiện ở JDK mới nhưng không có trong JVM đang chạy; `jcmd <PID> help` là thước đo trực tiếp. Không ép dùng syntax của bài blog viết cho JDK khác, và không tự nâng version ở production chỉ vì command trong tài liệu không tìm thấy.

## 9. Khi help hoặc attach không hoạt động

| Triệu chứng | Điều cần xác minh | Xử lý hợp lý |
| --- | --- | --- |
| `jcmd -l` không thấy JVM | Khác container/PID namespace, JVM đã thoát, thiếu quyền liệt kê | Tìm process đúng môi trường, xác minh PID và start time |
| `Could not attach` / permission denied | Effective UID/GID, chính sách OS, attach bị disable, runtime bị treo | Chạy từ đúng người dùng/môi trường hoặc dùng cơ chế quan sát đã chuẩn bị |
| `Unknown diagnostic command` | JVM version/vendor không có command, tên sai hoa/thường | Dùng `jcmd <PID> help` và xem đúng tên từ danh sách |
| Help có command nhưng chạy sai | Thiếu positional argument, sai tên option, sai type/đơn vị hoặc shell quoting | Đọc lại `Syntax`, `Options`, `Arguments`; kiểm tra dấu `=` và khoảng trắng |
| `-all` cho kết quả khác dự kiến | Trùng tên option ở command khác | Đọc help của **chính command đang gọi** |
| Không thấy trường Impact/Permission như ví dụ | Vendor/JDK hoặc output format khác | Dùng help thực tế và tài liệu JDK/vendor; không bịa giá trị |
| Output quá dài hoặc chứa secrets | Lệnh in nhiều flags/properties/stacks/path | Chọn đúng phạm vi, lưu ở chỗ giới hạn truy cập, lọc trước khi chia sẻ |
| Lệnh read-only vẫn ảnh hưởng hiệu năng | Chi phí thu thập, số thread/heap hoặc tần suất gọi cao | Điều chỉnh tần suất và lựa chọn command; đối chiếu latency/CPU/GC khi thu |

Lệnh `help` trả lỗi **không phải lý do để thử lần lượt tất cả command**. Phân biệt lỗi attach, command không tồn tại và lỗi cú pháp; mỗi nhóm có cách giải quyết khác nhau.

## 10. Những hiểu nhầm phổ biến

- **“`jcmd -h` đã chứa toàn bộ các command của JVM hiện tại.”** Sai: đây là trợ giúp của tiện ích; phải gửi `help` tới PID cụ thể để biết bộ command ở target.
- **“Command có trong tài liệu Java 21 nên Java 17 phải có.”** Sai: version/vendor và bản build quyết định danh sách.
- **“`-all` luôn có một ý nghĩa.”** Sai: tham số được parse trong ngữ cảnh từng command.
- **“Dấu `[options]` phải gõ nguyên văn.”** Sai: ngoặc vuông trong help biểu thị thành phần tùy chọn.
- **“`(STRING, no default value)` nghĩa là có thể để trống.”** Sai với **positional argument bắt buộc** như filename của `GC.heap_dump`.
- **“Impact: Low chắc chắn không làm thay đổi ứng dụng.”** Sai: `VM.set_flag`, `JFR.start` có thể thay đổi trạng thái/hoạt động dù nhãn Low.
- **“Impact: High là lệnh luôn chạy chậm một số giây cố định.”** Sai: phụ thuộc heap/content, I/O và workload.
- **“Permission: monitor đủ để attach mọi process.”** Sai: còn quyền OS, user/group, container và cấu hình JVM.
- **“Thread.print Medium nghĩa là có deadlock.”** Sai: Impact là chi phí lệnh, không phải kết luận về thread state.
- **“Đã mở được help thì mọi command đều nên chạy ngay.”** Sai: help là bước xem thông tin; execute là thao tác khác và có thể ghi file, trigger GC, start recording hoặc đổi flag.
- **“Một lần help đủ cho mọi JVM cùng tên ứng dụng.”** Sai: PID/JDK/vendor hoặc capabilities khác nhau; chẩn đoán cần bám target thực.
- **“Cứ thay JVM command bằng tên gần giống nếu bị Unknown.”** Sai: chỉ dùng command được JVM công bố và cú pháp chính xác.

## 11. Checklist thực hành

Trước khi quyết định thực thi một diagnostic command, có thể ghi vào ticket:

1. **Target**: service, PID, host/container, Java vendor/version, thời điểm và người thực hiện.
2. **Discovery**: `jcmd <PID> help` đã xác nhận command tồn tại.
3. **Syntax**: từ `jcmd <PID> help <COMMAND>`, chép đúng tên, positional arguments bắt buộc, options, type, default và đơn vị.
4. **Impact**: Low/Medium/High theo output của target; ghi thêm điều kiện phụ thuộc heap size, thread count hay workload.
5. **Side effect**: chỉ đọc, in snapshot, ghi file, chạy GC, bắt đầu recording hay thay đổi flag; đánh giá dung lượng và thời gian tác động.
6. **Permissions**: quyền runtime được help nêu và quyền attach/OS/container thực tế.
7. **Evidence**: lưu output đã che bí mật, timestamp, PID/start time; ghi cả việc command thất bại và thông báo lỗi nếu có.
8. **Conclusion**: phân biệt dữ liệu lấy được từ command với giả thuyết nguyên nhân sự cố; kiểm chứng bằng metrics, timeline và những công cụ phù hợp khác.

**Ghi nhớ:** ba thao tác khác nhau là **tìm JVM** bằng `jcmd -l`, **khám phá command** bằng `jcmd <PID> help [<COMMAND>]`, và **thực thi command** bằng `jcmd <PID> <COMMAND> ...`. Khi đọc help, luôn xem **Description + Syntax + Options/Arguments + Impact + Permission** như một bộ thống nhất. **Low Impact không đảm bảo read-only**, còn High Impact không phải lệnh sai; lựa chọn phụ thuộc mục tiêu và điều kiện vận hành của đúng JVM.

### Tài liệu tham khảo

- Oracle JDK 17, **The jcmd Command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle JDK 17, **Diagnostic Tools** (ví dụ cấu trúc help): https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html

Tài liệu mô tả các command của JDK tương ứng; **help trả về từ JVM đích** vẫn là nguồn để xác nhận các command thực sự có sẵn, cú pháp và Impact trong môi trường cần chẩn đoán.