# Cú pháp CompileCommand có kiểm tra tên và kiểu tùy chọn từ Java 16

**CompileCommand** là cơ chế riêng của HotSpot JVM để áp dụng một số chỉ thị của JIT compiler cho những phương thức khớp với method pattern. Từ JDK 16, cú pháp truyền tùy chọn compiler được cải tiến: tên tùy chọn được kiểm tra, kiểu giá trị được JVM tự suy ra và lỗi được báo rõ hơn khi tên hoặc giá trị không hợp lệ.

Thay đổi này giúp tránh tình trạng gõ sai tên tùy chọn nhưng không nhận ra lệnh đã bị bỏ qua. Cú pháp mới vẫn được hỗ trợ trong các JDK hiện đại; cú pháp cũ cũng được giữ để tương thích và nay được kiểm tra tính nhất quán. Bài học này giải thích cách viết lệnh, chọn method pattern, đọc lỗi và dùng CompileCommand có kiểm soát khi phân tích hành vi JIT.

## 1. CompileCommand dùng để làm gì?

JIT compiler biên dịch những phương thức được thực thi đủ thường xuyên thành mã máy để tăng tốc ứng dụng. **CompileCommand** cho phép người vận hành yêu cầu HotSpot áp dụng một số hành vi compiler cho các phương thức được chỉ định.

Ví dụ, có thể yêu cầu JVM không biên dịch một phương thức:

~~~bash
java -XX:CompileCommand=exclude,java/lang/String.indexOf -jar app.jar
~~~

Lệnh này yêu cầu HotSpot loại phương thức **java.lang.String.indexOf()** khỏi quá trình biên dịch JIT. Đây là ví dụ cú pháp để hiểu cơ chế, không phải khuyến nghị loại một phương thức thư viện chuẩn khỏi JIT trong ứng dụng thực tế.

Một số CompileCommand phổ biến:

| Command | Ý nghĩa |
| --- | --- |
| **exclude** | Không biên dịch phương thức khớp pattern |
| **compileonly** | Chỉ biên dịch các phương thức khớp pattern; các phương thức khác bị loại khỏi compilation |
| **inline** | Yêu cầu thử inline phương thức |
| **dontinline** | Ngăn inline phương thức |
| **print** | In mã assembly sau khi phương thức được biên dịch, nếu môi trường hỗ trợ |
| **log** | Giới hạn compilation logging theo phương thức |
| **break** | Đặt breakpoint phục vụ debug JVM/compiler |
| **help** | In hướng dẫn và danh sách tùy chọn |
| **quiet** | Tắt thông báo echo CompileCommand |

Các lệnh này tác động tới cách HotSpot biên dịch phương thức. Chúng không thay đổi logic Java và không phải API của ngôn ngữ Java. CompileCommand cũng là cơ chế đặc thù của HotSpot; không nên giả định JVM khác sẽ hỗ trợ cùng cú pháp hoặc hành vi.

## 2. Vấn đề của cú pháp tùy chọn trước JDK 16

Trước JDK 16, các tùy chọn compiler theo từng phương thức thường được truyền thông qua command con **option** với dạng:

~~~text
-XX:CompileCommand=option,<method pattern>,<option name>,<value type>,<value>
~~~

Ví dụ minh họa bật tùy chọn boolean **BlockLayoutByFrequency** cho phương thức **append()** của **StringBuffer**:

~~~bash
java -XX:CompileCommand=option,java/lang/StringBuffer.append,BlockLayoutByFrequency,bool,true -version
~~~

Cú pháp cũ cần người dùng cung cấp cả tên tùy chọn và kiểu giá trị. Trước thay đổi ở JDK 16, các tên tùy chọn trong nhóm này không được xác minh đầy đủ. Nếu viết sai tên, lệnh có thể bị bỏ qua mà người dùng khó nhận ra nguyên nhân.

Ví dụ gõ sai tên:

~~~bash
java -XX:CompileCommand=option,java/lang/StringBuffer.append,BlockLayoutByFrequence,bool,true -version
~~~

Ở đây **BlockLayoutByFrequence** bị sai chính tả. Vấn đề không nằm ở method pattern hoặc kiểu boolean mà ở tên tùy chọn compiler. JDK 16 cải thiện cơ chế kiểm tra để phát hiện loại lỗi này.

## 3. Cú pháp mới từ JDK 16

Từ JDK 16, một tùy chọn compiler có thể được viết trực tiếp như một CompileCommand thông thường:

~~~text
-XX:CompileCommand=<option name>,<method pattern>,<value>
~~~

Tên tùy chọn được đặt ở vị trí đầu tiên sau dấu bằng. JVM tra cứu tên này, xác định kiểu giá trị tương ứng và kiểm tra giá trị được truyền vào.

Ví dụ tương đương với lệnh cũ ở trên:

~~~bash
java -XX:CompileCommand=BlockLayoutByFrequency,java/lang/StringBuffer.append,true -version
~~~

Có thể đọc lệnh theo ba phần:

1. **BlockLayoutByFrequency** là tên tùy chọn compiler.
2. **java/lang/StringBuffer.append** là method pattern áp dụng tùy chọn.
3. **true** là giá trị; JVM biết tùy chọn này có kiểu boolean.

Điểm thay đổi quan trọng là người dùng không cần tự viết phần **bool** trong cú pháp mới. JVM suy ra kiểu từ định nghĩa tùy chọn và kiểm tra giá trị theo kiểu đó.

### So sánh hai dạng

| Nội dung | Cú pháp cũ | Cú pháp mới từ JDK 16 |
| --- | --- | --- |
| Tên option | Có | Có |
| Method pattern | Có | Có |
| Khai báo value type | Người dùng phải ghi | JVM tự suy ra |
| Kiểm tra tên option | Đã được bổ sung | Có |
| Kiểm tra value type và value | Đã được bổ sung cho cú pháp cũ | Có |
| Khuyến nghị cho cấu hình mới | Chỉ dùng khi cần tương thích cấu hình cũ | Ưu tiên |

Cú pháp cũ vẫn được hỗ trợ để giữ tương thích. JDK 16 bổ sung kiểm tra tính nhất quán giữa tên option, kiểu được khai báo và giá trị; vì vậy không cần hiểu rằng mọi cấu hình cũ đều bị loại bỏ.

## 4. JVM kiểm tra tên và kiểu giá trị như thế nào?

Có hai nhóm lỗi quan trọng mà thay đổi này giúp phát hiện.

### Tên tùy chọn không tồn tại

Ví dụ:

~~~bash
java -XX:CompileCommand=BlockLayoutByFrequence,java/lang/StringBuffer.append,true -version
~~~

Nếu tên tùy chọn không tồn tại trong JVM đang chạy, HotSpot đưa ra thông báo lỗi cho biết command hoặc option không được nhận diện. Người dùng có thể sửa tên dựa trên danh sách option mà JVM cung cấp.

### Giá trị không khớp kiểu

Giả sử **BlockLayoutByFrequency** là tùy chọn boolean. Truyền một chuỗi không phải giá trị boolean:

~~~bash
java -XX:CompileCommand=BlockLayoutByFrequency,java/lang/StringBuffer.append,enabled -version
~~~

JVM có thể phát hiện giá trị không phù hợp với kiểu được định nghĩa cho tùy chọn và đưa ra thông báo lỗi. Điều này giúp phân biệt lỗi tên option với lỗi kiểu hoặc định dạng giá trị.

### Tên command không phân biệt hoa thường

Theo ghi chú phát hành JDK 16, tên command được xử lý không phân biệt chữ hoa và chữ thường. Tuy nhiên, nên giữ cách viết đúng theo tên option được JVM liệt kê để cấu hình dễ đọc và dễ bảo trì.

Ví dụ, không nên dựa vào việc viết hoa tùy tiện để thay thế bước tra cứu tên option. Hãy lấy tên từ **CompileCommand=help** của đúng runtime đang dùng.

## 5. Liệt kê tùy chọn hợp lệ bằng CompileCommand=help

Không cần đoán tên option hoặc kiểu dữ liệu. JDK 16 bổ sung cách liệt kê các tùy chọn có sẵn:

~~~bash
java -XX:CompileCommand=help -version
~~~

Thông tin trợ giúp cho biết các command và option mà JVM hiện tại nhận diện. Khi cần kiểm tra một tùy chọn, hãy xem:

- Tên chính xác của option.
- Option có tồn tại trong bản JVM đang chạy hay không.
- Kiểu giá trị mà option yêu cầu.
- Option có phụ thuộc compiler cụ thể hay không.
- Cú pháp command được runtime hỗ trợ.

Danh sách có thể khác giữa các phiên bản JDK, bản build và cấu hình HotSpot. Một option có trong một bản JDK không nhất thiết tồn tại hoặc có cùng tác dụng trong bản khác. Vì vậy, **CompileCommand=help** trên runtime triển khai là nguồn kiểm tra thực tế cần ưu tiên.

## 6. Method pattern xác định phương thức nào được áp dụng

CompileCommand cần một method pattern để xác định phạm vi tác động. Cách viết thường gặp là tên class đầy đủ cùng tên phương thức.

Dạng slash-separated:

~~~bash
-XX:CompileCommand=exclude,java/lang/String.indexOf
~~~

Dạng **Class::method** cũng được hỗ trợ:

~~~bash
-XX:CompileCommand=exclude,java.lang.String::indexOf
~~~

Nếu không ghi method signature, command có thể áp dụng cho tất cả overload có cùng tên trong class khớp pattern. Khi cần giới hạn một overload cụ thể, có thể ghi method descriptor theo định dạng trong class file.

Ví dụ chỉ nhắm tới overload nhận một String và trả về int:

~~~bash
java "-XX:CompileCommand=exclude,java/lang/String.indexOf,(Ljava/lang/String;)I" -version
~~~

Trong shell, cần đặt toàn bộ argument trong dấu nháy kép vì descriptor chứa dấu chấm phẩy. Nếu không quote, shell có thể hiểu dấu chấm phẩy là ký tự kết thúc lệnh.

Có thể dùng wildcard **\*** trong class pattern và method pattern:

~~~bash
-XX:CompileCommand=dontinline,*.parse
~~~

Ví dụ này nhắm tới các phương thức có tên **parse** trong những class khớp pattern. Wildcard làm phạm vi ảnh hưởng rộng hơn; hãy kiểm tra pattern cẩn thận trước khi áp dụng cho ứng dụng thật.

Các dấu phẩy và dấu chấm cũng có thể được dùng như dấu phân cách thay thế cho khoảng trắng trong cú pháp CompileCommand. Dù vậy, cách dùng dấu phẩy như các ví dụ trên thường dễ đọc và dễ sao chép hơn.

## 7. Một số ví dụ CompileCommand thường gặp

### Theo dõi compilation của một phương thức

~~~bash
java -XX:CompileCommand=print,com/example/OrderService.calculate -jar app.jar
~~~

Command **print** yêu cầu in mã assembly sau khi phương thức được biên dịch. Khả năng hiển thị phụ thuộc nền tảng, compiler và thư viện disassembler tương ứng. Đây là thao tác chẩn đoán chuyên sâu, không phải cách kiểm tra thông thường cho mọi ứng dụng.

### Ngăn inline một phương thức

~~~bash
java -XX:CompileCommand=dontinline,com/example/OrderService.calculate -jar app.jar
~~~

Lệnh này ngăn JIT inline phương thức khớp pattern. Nó có thể hữu ích trong một thử nghiệm có giả thuyết cụ thể về inlining, nhưng cũng có thể làm giảm hiệu năng do tăng chi phí lời gọi hoặc làm thay đổi quyết định tối ưu hóa liên quan.

### Giới hạn compilation vào một nhóm phương thức

~~~bash
java -XX:CompileCommand=compileonly,com/example/OrderService.calculate -jar app.jar
~~~

**compileonly** có phạm vi tác động lớn: các phương thức khác có thể bị loại khỏi compilation. Không dùng command này như một thiết lập production chung. Nó phù hợp hơn với thử nghiệm compiler hoặc chẩn đoán có kiểm soát.

Các ví dụ trên minh họa cú pháp và tác dụng của command. Khi sử dụng thật, cần kiểm tra lệnh có khớp đúng method hay không và đo hành vi sau khi áp dụng.

## 8. Kiểm tra command có được JVM nhận hay không

HotSpot thường in thông tin CompileCommand ra đầu ra khi xử lý command. Ví dụ với command **exclude**, có thể thấy dòng theo dạng:

~~~text
CompilerOracle: exclude java/lang/String.indexOf
~~~

Thông báo này giúp xác nhận JVM đã đọc command và method pattern. Tuy nhiên, nó không chứng minh rằng phương thức đã được biên dịch hoặc một thay đổi hiệu năng cụ thể đã xảy ra. Để kiểm tra hành vi JIT, cần dùng thêm log compilation, JFR hoặc công cụ chẩn đoán thích hợp.

Có thể dùng **quiet** để tắt việc in các command đã đọc:

~~~bash
java -XX:CompileCommand=quiet -XX:CompileCommand=exclude,java/lang/String.indexOf -version
~~~

Đặt **quiet** trước các command cần ẩn để dễ kiểm soát đầu ra. Trong giai đoạn kiểm tra cấu hình, nên giữ thông báo mặc định để nhìn thấy JVM đã nhận những gì.

## 9. CompileCommand và Compiler Directives

CompileCommand là cách truyền chỉ thị ngắn gọn qua command line hoặc file lệnh. Với cấu hình compiler phức tạp hơn, HotSpot còn có **Compiler Control** và file compiler directives.

Compiler directives cho phép mô tả nhiều thuộc tính áp dụng theo method pattern trong file JSON. Chúng phù hợp khi cần lưu một bộ chính sách compiler có cấu trúc và quản lý như cấu hình riêng. CompileCommand vẫn hữu ích cho lệnh đơn giản, thử nghiệm nhanh và tương thích với quy trình chẩn đoán hiện có.

Không nên chuyển mọi CompileCommand thành directives nếu không có nhu cầu. Hãy chọn cơ chế phù hợp với số lượng phương thức, độ phức tạp của cấu hình và cách nhóm vận hành quản lý JVM.

## 10. Những điều CompileCommand không bảo đảm

Việc kiểm tra tên và kiểu option giúp phát hiện lỗi cú pháp, nhưng không đảm bảo command sẽ làm ứng dụng nhanh hơn.

Cần phân biệt:

- **Tên option hợp lệ** không có nghĩa option phù hợp với mọi compiler hoặc mọi kiến trúc.
- **Method pattern hợp lệ** không bảo đảm class và method đó thực sự được tải hoặc được biên dịch trong workload.
- **Command được nhận** không có nghĩa JIT bắt buộc tạo mã máy theo một kết quả tối ưu hóa cụ thể.
- **Inline hoặc exclude** có thể làm thay đổi các quyết định tối ưu hóa khác, dẫn tới kết quả ngược với kỳ vọng.
- **CompileCommand là HotSpot-specific**, không phải chuẩn Java SE áp dụng cho mọi JVM.

Nếu mục tiêu là cải thiện hiệu năng, hãy bắt đầu bằng JFR hoặc profiler để xác định hot method, tạo benchmark đại diện và chỉ thử CompileCommand khi có giả thuyết rõ ràng. So sánh trước và sau trong cùng điều kiện, đồng thời theo dõi throughput, latency, CPU và GC.

## 11. Quy trình sử dụng CompileCommand an toàn

1. Xác định phương thức hoặc compiler option cần kiểm tra từ dữ liệu profiling.
2. Chạy **-XX:CompileCommand=help** trên đúng JDK để xác nhận tên và kiểu option.
3. Viết method pattern đủ hẹp, thêm descriptor nếu cần phân biệt overload.
4. Dùng cú pháp mới **option name, method pattern, value** cho cấu hình mới.
5. Chạy ứng dụng trong môi trường thử nghiệm và kiểm tra thông báo parser.
6. Xác minh phương thức có được khớp và compilation behavior có thay đổi như dự kiến.
7. Đo lại bằng workload tương đương; không kết luận dựa trên một lần chạy.
8. Ghi lại phiên bản JDK, command, workload và kết quả để có thể tái lập.
9. Chỉ giữ cấu hình nếu lợi ích đo được ổn định và không gây suy giảm ở các đường xử lý khác.

## 12. Kết luận

JDK 16 cải tiến CompileCommand bằng cách đưa các tùy chọn compiler thành command có tên rõ ràng, kiểm tra tên option và tự suy ra kiểu giá trị. Khi tên không tồn tại hoặc giá trị không khớp kiểu, JVM có thể đưa ra thông báo hữu ích thay vì âm thầm bỏ qua cấu hình sai.

Cú pháp mới có dạng **-XX:CompileCommand=<option name>,<method pattern>,<value>**. Cú pháp cũ với command **option** vẫn được hỗ trợ và cũng được kiểm tra tính nhất quán. Hãy dùng **-XX:CompileCommand=help** để tra cứu option của đúng runtime, viết method pattern có phạm vi rõ ràng và chỉ áp dụng chỉ thị JIT sau khi đã có dữ liệu profiling cùng phép đo xác nhận.

## Tài liệu tham khảo

- [Consolidated JDK 16 Release Notes — Improved CompileCommand Flag](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [The java Command — Java SE 16, Advanced JIT Compiler Options](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [The java Command — Java SE 26, CompileCommand](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java Virtual Machine Guide — Compiler Control and CompileCommand](https://docs.oracle.com/en/java/javase/16/vm/java-virtual-machine-guide.pdf)

