# Dùng CompileCommand=help trên JVM đích để xác minh cấu hình JIT

HotSpot cung cấp **-XX:CompileCommand=help** để liệt kê cú pháp, các lệnh compiler và những tùy chọn JIT có thể áp dụng theo từng phương thức. Đây là điểm bắt đầu hữu ích khi kiểm tra một cấu hình CompileCommand, đặc biệt từ JDK 16 khi tên tùy chọn và kiểu giá trị được xác minh chặt chẽ hơn.

Tuy nhiên, cần phân biệt hai việc: tra cứu những gì một bản JVM hỗ trợ và kiểm tra cấu hình đã được nạp vào một tiến trình đang chạy. **CompileCommand=help** chạy lúc khởi động một JVM mới; nó không attach vào tiến trình đích. Để kiểm tra tiến trình thật, cần kết hợp **jcmd VM.command_line**, file CompileCommand nếu có, thông báo khởi động và dữ liệu compilation. Bài học này hướng dẫn quy trình đó để tránh nhầm lẫn giữa cú pháp hợp lệ, cấu hình đã nạp và hành vi JIT thực tế.

## 1. CompileCommand=help xác minh điều gì?

CompileCommand là cơ chế riêng của HotSpot JVM để áp dụng chỉ thị compiler cho các phương thức khớp với method pattern. Các lệnh thường dùng gồm:

| Lệnh | Mục đích |
| --- | --- |
| **exclude** | Loại phương thức khớp pattern khỏi JIT compilation |
| **compileonly** | Chỉ cho phép biên dịch các phương thức được chỉ định |
| **inline** | Yêu cầu thử inline phương thức |
| **dontinline** | Ngăn inline phương thức |
| **print** | In mã assembly sau khi phương thức được biên dịch, nếu môi trường có disassembler phù hợp |
| **log** | Giới hạn compilation logging theo phương thức |
| **break** | Dừng tại đầu quá trình biên dịch phương thức khi debug JVM |
| **option** | Cú pháp tương thích cũ để gán compiler option cho method pattern |
| **help** | In hướng dẫn CompileCommand và danh sách tùy chọn |
| **quiet** | Tắt thông báo echo các CompileCommand đã đọc |

Từ JDK 16, các tùy chọn compiler theo từng phương thức được đưa thành command thông thường với cú pháp:

~~~text
-XX:CompileCommand=<option-name>,<method-pattern>,<value>
~~~

JVM xác minh tên option, tự suy ra kiểu dữ liệu và báo lỗi khi tên không tồn tại hoặc giá trị không phù hợp. Cú pháp cũ với command **option** vẫn được hỗ trợ để tương thích; tên, kiểu và giá trị của cú pháp cũ cũng được kiểm tra tính nhất quán.

**CompileCommand=help** giúp trả lời:

- JVM này hỗ trợ những command nào?
- Tùy chọn compiler nào có thể được dùng theo phương thức?
- Cách viết method pattern và giá trị như thế nào?
- Cần dùng kiểu giá trị nào cho một option?

Lệnh này không trả lời trực tiếp:

- Tiến trình production đã được khởi chạy với CompileCommand nào?
- File command bên ngoài đã được đọc với nội dung gì?
- Một method pattern có thực sự khớp phương thức được tải hay không?
- Một phương thức đã được JIT biên dịch hoặc inline hay chưa?

Để trả lời các câu hỏi sau, cần kiểm tra tiến trình đang chạy và log compilation.

## 2. Chạy help bằng đúng JDK của ứng dụng

Dùng lệnh:

~~~bash
java -XX:CompileCommand=help -version
~~~

Lệnh gọi Java launcher để tạo một JVM mới bằng executable **java** đang nằm trên PATH. JVM in trợ giúp CompileCommand; tùy runtime, output phiên bản cũng có thể xuất hiện do tham số **-version**.

Để chắc chắn đang tra cứu đúng runtime, kiểm tra trước:

~~~bash
java -version
where java
~~~

Trên Linux hoặc macOS:

~~~bash
java -version
which java
~~~

Nếu ứng dụng chạy bằng một JDK cụ thể, nên gọi trực tiếp executable của JDK đó thay vì dựa vào PATH.

PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" -XX:CompileCommand=help -version
~~~

Linux hoặc macOS:

~~~bash
"$JAVA_HOME/bin/java" -XX:CompileCommand=help -version
~~~

So sánh phiên bản vừa hiển thị với phiên bản của JVM đích. Cùng tên lệnh không bảo đảm mọi bản build hoặc nhà phân phối HotSpot có cùng danh sách option. Một compiler option có thể được thêm, đổi hoặc loại bỏ giữa các phiên bản.

## 3. Đọc output của CompileCommand=help

Output trợ giúp có thể khá dài. Hãy tìm các nhóm thông tin sau:

1. Cú pháp tổng quát của CompileCommand.
2. Các command như **exclude**, **inline**, **dontinline**, **compileonly** và **print**.
3. Cú pháp option theo phương thức.
4. Các option và kiểu giá trị mà JVM hiện tại nhận diện.
5. Các ghi chú về method pattern, wildcard và method signature.

Tên option trong danh sách là tên cần dùng chính xác. Không nên tự đoán tên dựa trên tên flag JVM khác; compiler option gắn với CompileCommand có thể khác với VM flag toàn cục.

Ví dụ, một option boolean được viết theo cú pháp mới:

~~~bash
java -XX:CompileCommand=BlockLayoutByFrequency,java/lang/StringBuffer.append,true -version
~~~

Trong đó:

- **BlockLayoutByFrequency** là tên compiler option.
- **java/lang/StringBuffer.append** là method pattern.
- **true** là giá trị boolean.

Ví dụ này minh họa cú pháp được giới thiệu trong JDK 16 Release Notes. Option thực tế có thể không còn hiện diện trong một JDK khác; hãy kiểm tra danh sách help trên chính runtime sẽ sử dụng.

### Kiểm tra một tên option cụ thể

Khi cần xác minh cấu hình dự định, hãy so sánh tên và kiểu giá trị với output trợ giúp. Nếu option không được liệt kê, không nên giả định JVM vẫn hỗ trợ nó.

Với một cấu hình thử nghiệm, có thể khởi chạy một JVM ngắn bằng đúng runtime và truyền option cần kiểm tra:

~~~bash
java -XX:CompileCommand=<option-name>,com/example/OrderService.calculate,<value> -version
~~~

Thay placeholder bằng option và giá trị thật lấy từ help. Nếu tên option không tồn tại hoặc giá trị sai kiểu, JVM sẽ báo lỗi tương ứng.

Lệnh thử này xác minh parser của JVM mới. Nó chưa chứng minh method pattern khớp với class thực tế, cũng chưa chứng minh method đã được biên dịch trong workload.

## 4. Không nhầm CompileCommand=help với jcmd help

Hai lệnh đều có chữ **help**, nhưng phục vụ hai cơ chế khác nhau:

| Lệnh | Đối tượng được hỏi | Nội dung trả về |
| --- | --- | --- |
| **java -XX:CompileCommand=help -version** | JVM mới được khởi chạy bằng executable hiện tại | Cú pháp CompileCommand và danh sách command/option JIT |
| **jcmd <pid> help** | JVM đang chạy có PID được chỉ định | Danh sách diagnostic command mà tiến trình hỗ trợ |
| **jcmd <pid> help Compiler.codelist** | JVM đang chạy có PID được chỉ định | Cú pháp và mô tả diagnostic command Compiler.codelist |

Không có lệnh **jcmd <pid> CompileCommand=help**. CompileCommand là tùy chọn khởi động HotSpot, không phải diagnostic command có thể gọi trực tiếp bằng jcmd.

Điều này rất quan trọng khi kiểm tra production: chạy help bằng một JVM mới không thể chứng minh cấu hình của một tiến trình đã khởi chạy từ trước.

## 5. Xác định đúng JVM đích bằng jcmd

Trước tiên, liệt kê các JVM mà công cụ có thể nhìn thấy:

~~~bash
jcmd -l
~~~

Kết quả minh họa:

~~~text
18420 com.example.OrderApplication
20116 org.apache.catalina.startup.Bootstrap
~~~

Chọn PID của ứng dụng cần kiểm tra. Sau đó xác nhận phiên bản:

~~~bash
jcmd 18420 VM.version
~~~

Xem command line đã dùng để khởi chạy tiến trình:

~~~bash
jcmd 18420 VM.command_line
~~~

**VM.command_line** in command line được dùng để khởi động chính JVM đó. Hãy tìm các phần liên quan:

- **-XX:CompileCommand=...**
- **-XX:CompileCommandFile=...**
- **-XX:CompileCommand=quiet**
- Các tùy chọn JVM khác có thể ảnh hưởng đến JIT.

Có thể kiểm tra các VM flag hiện tại:

~~~bash
jcmd 18420 VM.flags -all
~~~

Lưu ý rằng **VM.flags** chủ yếu liệt kê VM flag và giá trị hiện tại. CompileCommand là nhóm chỉ thị theo phương thức; không nên mong đợi mọi mục CompileCommand xuất hiện như một VM flag trong kết quả này.

## 6. Kiểm tra CompileCommandFile và .hotspot_compiler

CompileCommand có thể được truyền trực tiếp trên command line hoặc đọc từ file.

Tùy chọn:

~~~text
-XX:CompileCommandFile=<path>
~~~

cho phép chỉ định file chứa các command cho JIT. Nếu không chỉ định file riêng, HotSpot có thể đọc file **.hotspot_compiler** theo cơ chế mặc định.

Theo thứ tự xử lý được mô tả trong tài liệu Java:

1. JVM đọc các CompileCommand truyền trên command line.
2. Sau đó JIT compiler đọc command từ file **.hotspot_compiler** hoặc file được chỉ định bởi **CompileCommandFile**.

Vì vậy, khi **VM.command_line** có **CompileCommandFile**, hãy mở đúng file đó và kiểm tra từng dòng. Nếu không có tùy chọn file, hãy kiểm tra thư mục làm việc của tiến trình để xác định có file **.hotspot_compiler** hay không.

Ví dụ file command:

~~~text
exclude com/example/OrderService calculate
dontinline com/example/OrderMapper map
print com/example/PriceEngine compute
~~~

Mỗi dòng biểu diễn một command cùng class và method pattern. Cần kiểm tra cả file thực tế mà tiến trình đã đọc, không chỉ file cùng tên nằm trong thư mục dự án hiện tại.

### Chú ý các nguồn tùy chọn được tiêm vào lúc khởi động

Trong một số môi trường, JVM nhận thêm tùy chọn thông qua biến môi trường hoặc script khởi chạy, chẳng hạn **JDK_JAVA_OPTIONS** và **JAVA_TOOL_OPTIONS**. Hãy kiểm tra môi trường của service hoặc container nơi JVM được khởi chạy nếu command line chưa giải thích được cấu hình quan sát được.

Không nên chỉ kiểm tra terminal hiện tại: biến môi trường của shell người dùng có thể khác với môi trường của Windows Service, systemd service, container hoặc tiến trình do process manager khởi chạy.

## 7. Hiểu thông báo echo CompileCommand khi JVM khởi động

HotSpot thường in ra các CompileCommand đã đọc. Ví dụ một dòng có thể có dạng:

~~~text
CompilerOracle: exclude com/example/OrderService.calculate
~~~

Thông báo này là bằng chứng JVM đã đọc command và method pattern. Tuy nhiên, nó không chứng minh rằng phương thức đã được tải, đã được gọi đủ nhiều lần hoặc đã có một compilation xảy ra.

Nếu cấu hình có:

~~~bash
-XX:CompileCommand=quiet
~~~

HotSpot sẽ không in các command đã đọc. Do đó, không thấy dòng echo không đồng nghĩa không có CompileCommand. Hãy kiểm tra **VM.command_line**, file command và môi trường khởi chạy.

Tiền tố thông báo có thể thay đổi theo phiên bản JVM. Hãy xem nội dung command và method pattern thay vì phụ thuộc hoàn toàn vào tên tiền tố.

## 8. Kiểm tra hành vi compilation thực tế

Sau khi xác minh cấu hình khởi động, cần kiểm tra JVM thực sự làm gì với phương thức.

### Xem danh sách phương thức đã biên dịch

Dùng diagnostic command:

~~~bash
jcmd 18420 Compiler.codelist
~~~

**Compiler.codelist** liệt kê các phương thức đã biên dịch còn tồn tại trong code cache tại thời điểm truy vấn. Nó hữu ích để kiểm tra một phương thức có xuất hiện trong danh sách compilation hay không.

Có thể xem hàng đợi compilation:

~~~bash
jcmd 18420 Compiler.queue
~~~

Hàng đợi chỉ phản ánh các phương thức đang chờ được biên dịch; nó không phải danh sách toàn bộ CompileCommand đã nạp.

Các diagnostic command có thể khác giữa phiên bản JVM. Trước khi dùng, kiểm tra trên chính tiến trình:

~~~bash
jcmd 18420 help
jcmd 18420 help Compiler.codelist
jcmd 18420 help Compiler.queue
~~~

### Ghi compilation log khi cần kiểm tra chi tiết

Đối với một lần chạy điều tra có kiểm soát, có thể bật:

~~~bash
java -XX:+PrintCompilation -jar app.jar
~~~

**PrintCompilation** in thông tin khi phương thức được biên dịch. Nó giúp đối chiếu tên method và thời điểm compilation với workload.

Nếu cần file log chi tiết hơn:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=hotspot.xml -jar app.jar
~~~

Log compilation có thể dùng để phân tích các quyết định và sự kiện liên quan tới JIT. Đây là thiết lập cần chuẩn bị lúc khởi động JVM; không thể mặc nhiên bật mọi tùy chọn chẩn đoán cho một tiến trình đã chạy.

Hãy dùng log trong môi trường thử nghiệm hoặc một phiên profiling có giới hạn, vì lượng dữ liệu và overhead phụ thuộc workload.

## 9. Phân biệt Compiler Directives với CompileCommand

HotSpot còn có cơ chế **Compiler Control** sử dụng file directives JSON. Đây là cơ chế khác với CompileCommand.

Có thể xem directives đang hoạt động trên JVM bằng:

~~~bash
jcmd 18420 Compiler.directives_print
~~~

Kết quả hiển thị directive stack. Nó không phải bản liệt kê đầy đủ các CompileCommand đã đọc từ command line hoặc **.hotspot_compiler**.

| Cơ chế | Cách cấu hình | Cách kiểm tra |
| --- | --- | --- |
| **CompileCommand** | **-XX:CompileCommand** hoặc **CompileCommandFile** | **VM.command_line**, file command, startup echo và compilation log |
| **Compiler Directives** | **-XX:CompilerDirectivesFile** hoặc diagnostic command | **Compiler.directives_print** |

Không dùng **Compiler.directives_print** thay cho **CompileCommand=help** hoặc **VM.command_line**. Hai cơ chế có thể cùng ảnh hưởng đến JIT nhưng có cách quản lý và kiểm tra khác nhau.

## 10. Quy trình kiểm tra cấu hình JIT trên JVM đích

Có thể áp dụng quy trình sau khi cần xác minh một cấu hình CompileCommand:

1. Xác định đường dẫn JDK mà service thực sự sử dụng.
2. Chạy **java -version** và **java -XX:CompileCommand=help -version** bằng đúng executable đó.
3. Đối chiếu tên command, option và kiểu giá trị với output help.
4. Dùng **jcmd -l** hoặc PID từ hệ thống quản lý tiến trình để xác định JVM đích.
5. Chạy **jcmd <pid> VM.version** để xác nhận phiên bản tiến trình.
6. Chạy **jcmd <pid> VM.command_line** để xem tùy chọn khởi động.
7. Kiểm tra **CompileCommandFile**, file **.hotspot_compiler** và các biến môi trường của service nếu có.
8. Đọc thông báo echo CompileCommand nếu có; lưu ý **quiet** có thể tắt các thông báo này.
9. Dùng **Compiler.codelist**, **Compiler.queue**, **PrintCompilation** hoặc **LogCompilation** để kiểm tra hành vi compilation phù hợp với câu hỏi.
10. Nếu tiến trình dùng Compiler Directives, kiểm tra riêng bằng **Compiler.directives_print**.
11. Ghi lại JDK, PID, command line, file cấu hình và thời điểm kiểm tra để kết quả có thể tái lập.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Help không liệt kê option mong muốn | Đang gọi nhầm JDK hoặc option không có trong bản build đó | Dùng đúng executable của service và kiểm tra lại phiên bản |
| **jcmd -l** không thấy tiến trình | Khác user, host hoặc PID namespace; JVM chạy trong container riêng | Chạy jcmd trên cùng host/container và bằng user phù hợp |
| **VM.command_line** không có CompileCommand | Cấu hình đến từ file hoặc biến môi trường; hoặc command không được truyền ở startup | Kiểm tra CompileCommandFile, .hotspot_compiler và môi trường service |
| Không thấy echo command | **quiet** đã được bật hoặc output được chuyển hướng | Kiểm tra command line, file cấu hình và log startup |
| Method không xuất hiện trong Compiler.codelist | Chưa được gọi đủ nóng, pattern không khớp, bị loại khỏi compilation hoặc code đã bị unload | Kiểm tra workload, pattern, compilation log và thời điểm truy vấn |
| Directives print không có rule mong muốn | Cấu hình dùng CompileCommand thay vì Compiler Directives, hoặc file directives chưa được nạp | Kiểm tra đúng cơ chế và file tương ứng |
| Cấu hình hợp lệ nhưng hiệu năng không đổi | Method không được gọi, option không tác động như giả thuyết hoặc lợi ích không đáng kể | Đo lại với workload đại diện và kiểm tra compilation log |

## 12. Lưu ý khi kiểm tra trong production

- **jcmd** cần chạy trên cùng máy với JVM đích và thường cần cùng effective user/group đã khởi chạy JVM.
- Trong container, PID nhìn từ host có thể khác PID bên trong container; chạy công cụ trong đúng PID namespace khi cần.
- **Compiler.codelist** có impact mức Medium theo tài liệu JDK 16; tránh truy vấn liên tục trên ứng dụng nhạy latency.
- **PrintCompilation** và **LogCompilation** cần được bật trước khi JVM khởi chạy; nên thử ở staging trước.
- Output help chỉ cho biết khả năng của runtime, không xác minh cấu hình đang hoạt động trong process khác.
- CompileCommand là cơ chế HotSpot-specific; JVM khác có thể không hỗ trợ.
- Tên option và khả năng compiler thay đổi theo phiên bản; không sao chép cấu hình JIT giữa các JDK mà không kiểm tra.

## 13. Kết luận

**-XX:CompileCommand=help** là cách tra cứu các command và compiler option mà một bản HotSpot hỗ trợ. Từ JDK 16, cơ chế kiểm tra tên option và suy luận kiểu giá trị giúp phát hiện cấu hình sai rõ ràng hơn.

Để xác minh JVM đích, hãy dùng **jcmd VM.version** và **VM.command_line**, kiểm tra file **CompileCommandFile** hoặc **.hotspot_compiler**, sau đó đối chiếu thông báo khởi động và compilation log. **Compiler.codelist** giúp xem phương thức đã biên dịch; **Compiler.directives_print** chỉ dành cho Compiler Directives. Phân biệt đúng các nguồn dữ liệu này giúp xác nhận cả cấu hình lẫn hành vi JIT mà không nhầm output trợ giúp của JVM mới với trạng thái của tiến trình production.

## Tài liệu tham khảo

- [Consolidated JDK 16 Release Notes — Improved CompileCommand Flag](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [The java Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [The jcmd Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jcmd.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Diagnostic Tools — Java SE 27](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [Commands for Working with Directive Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/vm/commands-work-directive-files.html)
- [Notes on Debugging HotSpot's JIT Compilation](https://jornvernee.github.io/hotspot/jit/2023/08/18/debugging-jit.html)

