# Vì sao nâng cấp JDK có thể ảnh hưởng ứng dụng đang hoạt động

Nâng cấp JDK có thể làm thay đổi cách một ứng dụng được biên dịch, khởi động và thực thi, ngay cả khi mã nguồn của ứng dụng không thay đổi. JDK không chỉ là công cụ dùng để chạy lệnh `javac`; nó còn cung cấp máy ảo Java (JVM), thư viện chuẩn, các công cụ đi kèm và nhiều cấu hình mặc định ảnh hưởng trực tiếp đến môi trường chạy.

Vì vậy, một ứng dụng từng hoạt động ổn định trên JDK cũ chưa chắc sẽ hoạt động giống hệt khi chuyển sang JDK mới. Ứng dụng có thể không khởi động được, thiếu lớp hoặc thư viện, gặp lỗi bảo mật, xử lý dữ liệu khác trước, hoặc thay đổi hiệu năng. Muốn nâng cấp an toàn, cần hiểu những phần nào của nền tảng Java có thể thay đổi và kiểm tra chúng theo từng lớp.

## 1. JDK là một phần của môi trường thực thi ứng dụng

Một ứng dụng Java thường được phát triển từ mã nguồn, biên dịch thành bytecode rồi chạy trên JVM. Khi triển khai, file JAR hoặc WAR thường không chứa sẵn JVM; máy chủ, container hoặc môi trường vận hành cung cấp JDK/JRE phù hợp để chạy ứng dụng.

```text
Mã nguồn Java
     |
     v
Trình biên dịch javac
     |
     v
Bytecode (.class) + thư viện ứng dụng
     |
     v
JVM + thư viện chuẩn của JDK
     |
     v
Hệ điều hành / container / phần cứng
```

JDK (Java Development Kit) là bộ công cụ phát triển. Trong đó có trình biên dịch, JVM và các thư viện chuẩn cần thiết để phát triển, kiểm tra và chạy chương trình. Tùy cách đóng gói và phiên bản Java, môi trường triển khai có thể được gọi là JRE hoặc dùng trực tiếp một bản phân phối JDK. Dù tên gọi là gì, ứng dụng vẫn phụ thuộc vào JVM và các thư viện có mặt trong môi trường thực thi.

Điều này tạo ra hai thời điểm cần phân biệt:

- **Thời điểm build:** mã nguồn được biên dịch bằng một JDK. Phiên bản compiler, API mà compiler nhìn thấy và cấu hình build quyết định bytecode được tạo ra.
- **Thời điểm runtime:** bytecode được nạp và thực thi bằng JVM cùng thư viện của JDK đang cài trên máy chạy ứng dụng. Phiên bản runtime quyết định nhiều hành vi thực tế.

Hai thời điểm này có thể dùng JDK khác nhau. Chẳng hạn, nhóm phát triển biên dịch ứng dụng trên JDK mới nhưng máy chủ vẫn chạy JDK cũ; hoặc ứng dụng được build từ lâu nhưng nay được triển khai lại trên runtime mới. Cả hai trường hợp đều có thể phát sinh vấn đề tương thích.

## 2. Tương thích không chỉ có nghĩa là biên dịch thành công

Khi đánh giá một lần nâng cấp JDK, cần xem xét nhiều loại tương thích. Một ứng dụng vượt qua một loại kiểm tra chưa chắc đã vượt qua các loại còn lại.

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ khi không tương thích |
|---|---|---|
| Tương thích mã nguồn (source compatibility) | Mã nguồn hiện tại có biên dịch được bằng compiler mới không? | Một API không còn được cung cấp khiến compiler báo không tìm thấy package hoặc class. |
| Tương thích nhị phân (binary compatibility) | Các file `.class` hoặc JAR đã biên dịch có được JVM nạp và liên kết thành công không? | JVM cũ không đọc được bytecode có phiên bản class file mới; hoặc thiếu class/method mà ứng dụng cần. |
| Tương thích hành vi (behavioral compatibility) | Khi chạy, chương trình có giữ nguyên kết quả và quy tắc xử lý mong đợi không? | Cách mã hóa văn bản, lựa chọn thuật toán bảo mật hoặc dữ liệu múi giờ thay đổi. |
| Tương thích vận hành (operational compatibility) | Ứng dụng có khởi động, giám sát, mở kết nối và đáp ứng tải như trước không? | JVM từ chối một tùy chọn khởi động cũ, mức dùng bộ nhớ hoặc độ trễ thay đổi. |

Ví dụ, mã nguồn có thể biên dịch thành công vì các thư viện cần thiết đã được thêm vào classpath. Tuy nhiên, khi chạy trên máy chủ, một thư viện khác phiên bản có thể được nạp trước, dẫn đến `NoSuchMethodError`. Tương tự, ứng dụng có thể khởi động bình thường nhưng chỉ lỗi khi xử lý một loại chứng chỉ TLS, đọc một file có ký tự ngoài ASCII hoặc tải một class thông qua reflection.

Do đó, câu hỏi đúng không chỉ là “Ứng dụng có compile được trên JDK mới không?”, mà còn là “Ứng dụng có thể khởi động, thực hiện đầy đủ luồng nghiệp vụ và vận hành ổn định trong môi trường mới không?”.

## 3. Những thay đổi trong JDK có thể tác động đến ứng dụng

### 3.1. Thư viện chuẩn và API có thể thay đổi

JDK cung cấp nhiều package mà ứng dụng có thể sử dụng trực tiếp. Qua các phiên bản, API có thể được bổ sung, đánh dấu deprecated, thay đổi hoặc loại bỏ. Một số module từng được đóng gói cùng JDK cũng có thể được tách ra khỏi bộ JDK tiêu chuẩn.

Một ví dụ đáng chú ý là nhóm module Java EE và CORBA đã được loại khỏi JDK từ Java 11. Ứng dụng cũ từng dựa vào các API như JAXB mà không khai báo dependency riêng có thể gặp lỗi biên dịch như `package javax.xml.bind does not exist`, hoặc lỗi runtime như `ClassNotFoundException` khi chuyển môi trường.

Nguyên nhân là trước đây ứng dụng vô tình dựa vào thư viện được cung cấp sẵn bởi JDK. Khi thư viện đó không còn nằm trong JDK, dependency cần được khai báo rõ ràng trong hệ thống build và đóng gói cùng ứng dụng.

Một thay đổi khác là phiên bản class file. Compiler mới có thể tạo bytecode cho phiên bản Java mới hơn. JVM cũ không hiểu định dạng class file đó và có thể báo `UnsupportedClassVersionError`.

```text
Compiler mới
     |
     v
Bytecode phiên bản mới
     |
     v
JVM cũ không hỗ trợ phiên bản class file
     |
     v
UnsupportedClassVersionError
```

Thông thường, bytecode được tạo cho phiên bản Java cũ có thể chạy trên JVM mới hơn, miễn là các API và dependency mà chương trình sử dụng vẫn tồn tại và tương thích. Chiều ngược lại không được bảo đảm: JVM cũ không thể chạy bytecode yêu cầu định dạng class file mới.

### 3.2. Cơ chế module và truy cập reflection có thể chặt chẽ hơn

Một số thư viện và framework cũ sử dụng reflection để truy cập trường, phương thức hoặc constructor không công khai. Một số trường hợp còn truy cập vào các class nội bộ của JDK, chẳng hạn các package có tên bắt đầu bằng `sun.` hoặc `com.sun.`.

Những API nội bộ này không phải hợp đồng công khai ổn định. Khi nền tảng Java tăng cường cơ chế module và đóng gói nội bộ, việc truy cập sâu vào các class đó có thể bị cảnh báo hoặc bị chặn. Ứng dụng có thể gặp `IllegalAccessException`, `InaccessibleObjectException` hoặc lỗi liên quan khi một thư viện cố mở quyền truy cập bằng reflection.

Ví dụ, một framework cũ có thể cố truy cập trường private bên trong một class của JDK. Trên môi trường cũ, thao tác đó có thể thành công do cách đóng gói còn cho phép. Trên môi trường mới, cùng đoạn mã có thể bị từ chối vì module sở hữu class không mở package đó cho module gọi.

Hướng xử lý nên theo thứ tự:

1. Xác định thư viện hoặc đoạn mã nào đang truy cập nội bộ.
2. Nâng cấp thư viện lên phiên bản hỗ trợ JDK mục tiêu.
3. Nếu là mã do ứng dụng sở hữu, thay API nội bộ bằng API công khai được hỗ trợ.
4. Chỉ dùng tùy chọn mở module như `--add-opens` khi đã hiểu rõ phạm vi và xem đó là biện pháp chuyển tiếp có kiểm soát.

Thêm `--add-opens` có thể giúp ứng dụng cũ tiếp tục chạy trong một số tình huống, nhưng nó không biến API nội bộ thành API được bảo đảm ổn định. Nếu phụ thuộc này còn tồn tại, lần nâng cấp JDK tiếp theo vẫn có thể gặp vấn đề.

### 3.3. JVM, garbage collector và trình biên dịch JIT có thể thay đổi hành vi vận hành

JVM chịu trách nhiệm nạp class, quản lý bộ nhớ, thu gom rác (garbage collection), biên dịch mã nóng bằng JIT và thực thi bytecode. Những thành phần này được cải tiến qua các phiên bản JDK.

Các thay đổi có thể đem lại hiệu năng tốt hơn, nhưng cũng có thể làm khác đi:

- Thời điểm và thời lượng các lần garbage collection.
- Mức sử dụng heap, native memory, metaspace hoặc số lượng thread.
- Thời gian khởi động và thời gian làm nóng JIT.
- Độ trễ ở mức trung bình hoặc ở các phân vị cao như p95, p99.
- Cách JVM phản ứng khi bộ nhớ gần cạn hoặc khi ứng dụng chịu tải lớn.

Ví dụ, một ứng dụng có thể chạy ổn định với cấu hình heap và garbage collector được tinh chỉnh cho JDK cũ. Sau khi nâng cấp, thuật toán GC mặc định hoặc cách triển khai đã thay đổi; cùng cấu hình cũ có thể tạo ra nhịp thu gom rác khác và làm độ trễ tăng trong giờ cao điểm.

Điều đó không có nghĩa JDK mới luôn chậm hơn. Hiệu năng phụ thuộc vào ứng dụng, dữ liệu, tải, phần cứng và cấu hình. Vì vậy, không nên chỉ dựa vào kết quả benchmark nhỏ hoặc thời gian khởi động để kết luận. Cần đo trên tải đại diện và quan sát cả thông lượng, độ trễ, bộ nhớ lẫn hoạt động GC.

### 3.4. Tùy chọn JVM và cách ghi log có thể không còn giống trước

Ứng dụng thường được khởi động cùng các tùy chọn như `-Xms`, `-Xmx`, cấu hình garbage collector, system properties hoặc các cờ bật/tắt tính năng. Qua các phiên bản, một số tùy chọn có thể bị deprecated, thay thế hoặc loại bỏ.

Nếu script triển khai vẫn truyền một cờ không còn được JVM hỗ trợ, ứng dụng có thể dừng ngay khi khởi động với thông báo kiểu `Unrecognized VM option`. Một số tùy chọn trước đây có tác dụng nhưng nay có ý nghĩa khác hoặc không còn là cách cấu hình được khuyến nghị.

Cơ chế logging của JVM cũng thay đổi theo thời gian. Chẳng hạn, các phiên bản Java mới đã đưa vào hệ thống unified logging với cú pháp `-Xlog`. Script thu thập log dựa trên cờ GC logging cũ cần được kiểm tra và điều chỉnh khi chuyển phiên bản.

Vì vậy, việc nâng JDK cần rà soát cả lệnh khởi động thực tế, file cấu hình container, biến môi trường và script quản lý tiến trình, không chỉ kiểm tra file JAR.

### 3.5. Cấu hình bảo mật và kết nối mạng có thể nghiêm ngặt hơn

JDK cung cấp các thành phần bảo mật như JSSE, JCA, danh sách thuật toán mật mã, kho chứng chỉ tin cậy và các provider. Những thành phần này được cập nhật để loại bỏ thuật toán yếu, sửa lỗ hổng và tuân theo yêu cầu bảo mật mới.

Một kết nối từng thành công có thể thất bại sau khi nâng JDK nếu máy chủ đối tác chỉ hỗ trợ giao thức hoặc cipher suite đã bị vô hiệu hóa, chứng chỉ không còn được chấp nhận, chuỗi chứng chỉ thiếu CA tin cậy, hoặc cấu hình bảo mật mới từ chối một thuật toán cũ.

Ví dụ, ứng dụng kết nối đến một dịch vụ nội bộ cũ chỉ hỗ trợ cấu hình TLS yếu. Runtime mới từ chối thương lượng kết nối; lỗi xuất hiện dưới dạng `SSLHandshakeException`. Nhìn từ mã nghiệp vụ, lệnh gọi HTTP không thay đổi, nhưng chính sách bảo mật của runtime đã thay đổi.

Khi điều tra, cần kiểm tra cả hai phía của kết nối: phiên bản JDK, truststore, chứng chỉ, giao thức và cipher suite được máy khách hỗ trợ, cùng cấu hình TLS của dịch vụ đích. Không nên giải quyết bằng cách bật lại một thuật toán yếu trong production mà chưa đánh giá rủi ro và có phương án thay thế.

### 3.6. Charset, locale và dữ liệu múi giờ có thể ảnh hưởng kết quả xử lý

Ứng dụng có thể phụ thuộc vào các giá trị mặc định của môi trường như charset, locale hoặc timezone. Khi những giá trị mặc định hay dữ liệu đi kèm JDK thay đổi, cùng một đoạn mã có thể tạo ra kết quả khác.

Một ví dụ cụ thể là charset mặc định. Từ Java 18, UTF-8 trở thành charset mặc định theo JEP 400 trong các môi trường tiêu chuẩn, trong khi các phiên bản trước thường lấy charset mặc định từ môi trường. Ứng dụng cũ dựa vào charset mặc định để đọc hoặc ghi file có thể cho ra dữ liệu khác khi chuyển JDK, đặc biệt nếu file được tạo bằng một encoding khác UTF-8.

Mã nguồn dễ gây phụ thuộc vào mặc định:

```java
// Phụ thuộc vào charset mặc định của môi trường
String content = new String(bytes);
```

Nếu định dạng file được quy định là UTF-8, nên nêu rõ encoding:

```java
import java.nio.charset.StandardCharsets;

String content = new String(bytes, StandardCharsets.UTF_8);
```

Tương tự, nếu nghiệp vụ cần xử lý thời gian theo một múi giờ cụ thể, hãy dùng `ZoneId` rõ ràng thay vì dựa vào timezone mặc định của máy chạy. Dữ liệu timezone và locale cũng được cập nhật theo thay đổi của thế giới; điều đó có thể ảnh hưởng cách phân tích ngày giờ, định dạng số, tiền tệ hoặc tên tháng.

### 3.7. Dependency, framework, agent và thư viện native có thể chưa hỗ trợ JDK mới

Ứng dụng hiếm khi chỉ dùng thư viện chuẩn. Framework, ORM, thư viện JSON, thư viện bytecode, công cụ kiểm thử, Java agent và thư viện native đều có thể phụ thuộc vào chi tiết của JDK.

Một số thư viện tạo hoặc biến đổi bytecode nên cần được cập nhật để hiểu phiên bản class file mới. Một số framework dùng reflection hoặc truy cập các API nội bộ. Java agent có thể can thiệp vào quá trình nạp class. Thư viện JNI/JNA còn phụ thuộc vào ABI, kiến trúc CPU và thư viện hệ điều hành.

Vì thế, ứng dụng có thể biên dịch được nhưng vẫn lỗi khi khởi động do framework chưa hỗ trợ runtime mới, hoặc chỉ lỗi ở một luồng cụ thể do agent không xử lý được class file mới. Các dependency gián tiếp cũng cần được xem xét; không phải mọi thư viện đều xuất hiện trực tiếp trong file build của ứng dụng.

Trước khi nâng cấp, cần đối chiếu phiên bản được hỗ trợ của framework và thư viện quan trọng với JDK mục tiêu. Nếu một dependency đã ngừng bảo trì hoặc chỉ hỗ trợ JDK cũ, cần xác định phương án nâng cấp hoặc thay thế trước khi triển khai.

### 3.8. Hệ điều hành, container và kiến trúc phần cứng cũng là một phần của tương thích

JDK chạy trên một môi trường cụ thể. Bản phân phối JDK, hệ điều hành, kiến trúc CPU, thư viện native, image container và thiết lập tài nguyên đều có thể ảnh hưởng kết quả.

Một lần nâng JDK thường đi kèm việc đổi base image container hoặc nâng hệ điều hành. Nếu ứng dụng sử dụng thư viện native, thay đổi libc, kiến trúc CPU hoặc phiên bản thư viện hệ thống có thể làm thư viện không nạp được. Giới hạn CPU và memory của container cũng có thể khiến JVM nhận diện tài nguyên khác với máy ảo hoặc máy chủ trước đó.

Khi so sánh hai môi trường, cần ghi nhận đầy đủ cả phiên bản JDK lẫn vendor/distribution, hệ điều hành, kiến trúc, image container và giới hạn tài nguyên. Chỉ ghi “Java 21” là chưa đủ để mô tả toàn bộ môi trường chạy.

## 4. Một số tình huống minh họa

### Tình huống A: Ứng dụng mất một API từng có sẵn trong JDK

Một ứng dụng cũ dùng JAXB để chuyển đổi XML nhưng không khai báo dependency JAXB riêng vì môi trường JDK trước đây cung cấp sẵn các module liên quan. Khi chuyển sang JDK 11 trở lên, build có thể báo không tìm thấy package hoặc runtime báo thiếu class.

Điểm cần hiểu: mã nguồn không nhất thiết sai. Ứng dụng đang dựa vào một thành phần được cung cấp gián tiếp bởi JDK cũ. Cách xử lý là khai báo dependency tương ứng, chọn phiên bản tương thích và đóng gói nó cùng ứng dụng.

### Tình huống B: Framework cũ không còn truy cập được class nội bộ

Ứng dụng khởi động bằng JDK cũ. Một framework dùng reflection để mở một trường private bên trong class thuộc JDK. Sau khi nâng cấp, ứng dụng gặp `InaccessibleObjectException` khi framework thực hiện thao tác đó.

Điểm cần hiểu: quy tắc đóng gói module đã chặt chẽ hơn. Cần tìm ra framework gây truy cập, kiểm tra phiên bản hỗ trợ JDK mục tiêu và nâng cấp. Tùy chọn `--add-opens` chỉ nên dùng khi có lý do rõ ràng và kế hoạch loại bỏ phụ thuộc.

### Tình huống C: Nội dung file thay đổi sau khi nâng cấp

Ứng dụng đọc file CSV bằng `new String(bytes)` rồi phân tích dữ liệu. File được tạo bởi một hệ thống dùng encoding khác UTF-8. Khi môi trường chạy đổi charset mặc định, các ký tự có dấu có thể bị sai hoặc dữ liệu không còn được phân tích như mong đợi.

Điểm cần hiểu: chương trình đã dựa vào một mặc định không được ghi rõ trong hợp đồng dữ liệu. Cần quy định encoding của file và chỉ định charset tường minh trong mã nguồn.

### Tình huống D: Ứng dụng không khởi động vì cờ JVM cũ

Pipeline triển khai vẫn truyền một tùy chọn GC từng dùng trên JDK cũ. JDK mới không còn nhận tùy chọn đó và JVM dừng trước khi nạp class ứng dụng.

Điểm cần hiểu: cấu hình vận hành là một phần của ứng dụng. Cần kiểm tra lệnh chạy và thay cờ cũ bằng cấu hình được hỗ trợ trên JDK mục tiêu, sau đó kiểm tra lại hành vi GC và logging.

## 5. Vì sao ứng dụng đang chạy ổn định vẫn có thể bị ảnh hưởng?

Một ứng dụng đang hoạt động thường đã được kiểm chứng trong một tổ hợp cụ thể: phiên bản JDK, dependency, cấu hình JVM, hệ điều hành, chứng chỉ, dữ liệu và tải thực tế. Khi một thành phần trong tổ hợp đó thay đổi, các giả định mà ứng dụng dựa vào có thể không còn đúng.

Một số nguyên nhân thường gặp:

1. **Runtime thay đổi trong khi bytecode giữ nguyên.** File JAR cũ được chạy trên JVM mới, nên hành vi của thư viện chuẩn, bảo mật, GC hoặc JIT có thể khác.
2. **Ứng dụng được build lại bằng compiler mới.** Bytecode, API được sử dụng hoặc dependency được phân giải có thể khác bản build trước.
3. **Môi trường triển khai thay đổi cùng lúc.** Image container, hệ điều hành, biến môi trường, timezone, truststore hoặc giới hạn tài nguyên được cập nhật.
4. **Lỗi chỉ xuất hiện ở một nhánh ít được dùng.** Một thao tác reflection, kết nối TLS đến đối tác hiếm gặp hoặc file có encoding đặc biệt có thể không xuất hiện trong kiểm tra khởi động.
5. **Khác biệt hiệu năng chỉ lộ ra khi có tải.** Một ứng dụng chạy tốt trong kiểm thử nhỏ vẫn có thể gặp độ trễ, GC pause hoặc áp lực bộ nhớ khi lượng request tăng.

Với hệ thống chạy liên tục, ảnh hưởng thường xuất hiện khi tiến trình được khởi động lại bằng runtime mới, khi một instance mới được đưa vào cụm, hoặc khi triển khai rolling update làm các instance tạm thời chạy trên nhiều phiên bản JDK khác nhau. Nếu hành vi giữa các instance khác nhau, cùng một request có thể thành công ở instance này nhưng thất bại ở instance khác.

## 6. Cách đánh giá ảnh hưởng trước khi nâng cấp

Không nên bắt đầu bằng việc thay JDK trên production rồi chờ xem có lỗi hay không. Hãy xác định môi trường hiện tại, chọn JDK mục tiêu và kiểm tra từng lớp phụ thuộc.

### Bước 1: Ghi nhận môi trường đang chạy

Thu thập ít nhất các thông tin sau:

- Phiên bản, vendor và bản phân phối JDK/JVM đang dùng ở build và runtime.
- Lệnh khởi động thực tế, JVM arguments, system properties và biến môi trường.
- Hệ điều hành, kiến trúc CPU, image container và giới hạn CPU/memory.
- Phiên bản framework, dependency trực tiếp và dependency bắc cầu.
- Các thư viện native, Java agent, công cụ giám sát và công cụ profiling.
- Các kết nối ngoài hệ thống, truststore, chứng chỉ và giao thức bảo mật.
- Các định dạng file, encoding, locale và timezone mà nghiệp vụ sử dụng.

Nên lấy thông tin từ môi trường thực tế đang chạy, vì cấu hình trong máy phát triển có thể khác cấu hình của production.

### Bước 2: Xác định phạm vi thay đổi của JDK mục tiêu

Đọc ghi chú phát hành và hướng dẫn migration của các phiên bản nằm giữa JDK hiện tại và JDK mục tiêu. Tập trung vào:

- API hoặc module bị loại bỏ, thay thế hay thay đổi.
- Thay đổi về module system, reflection và truy cập API nội bộ.
- Thay đổi về JVM flags, garbage collector, logging và quản lý bộ nhớ.
- Thay đổi về TLS, thuật toán mật mã, chứng chỉ và provider.
- Thay đổi về charset mặc định, locale, timezone và thư viện chuẩn.
- Yêu cầu JDK tối thiểu của framework, plugin, agent và dependency.

Nếu nâng qua nhiều phiên bản lớn, cần xem các thay đổi tích lũy ở từng phiên bản trung gian, không chỉ ghi chú của phiên bản đích.

### Bước 3: Kiểm tra dependency và API nội bộ

Rà soát dependency trực tiếp lẫn bắc cầu, sau đó nâng những thư viện chưa hỗ trợ JDK mục tiêu. Các công cụ như `jdeps` có thể giúp phát hiện dependency và tham chiếu đến API nội bộ của JDK; `jdeprscan` có thể hỗ trợ tìm việc sử dụng API đã deprecated. Kết quả công cụ là đầu vào để điều tra, không thay thế kiểm thử runtime: reflection động, class được nạp theo cấu hình và tương tác với hệ thống bên ngoài có thể không được phát hiện đầy đủ qua phân tích tĩnh.

Nếu dự án build bằng JDK mới nhưng cần duy trì khả năng chạy trên một phiên bản Java thấp hơn, có thể dùng tùy chọn `--release` để giới hạn mức ngôn ngữ, bytecode và API chuẩn theo phiên bản đích mà compiler hỗ trợ:

```bash
javac --release 17 -d out src/com/example/App.java
```

Ví dụ trên yêu cầu compiler tạo đầu ra tương thích với Java 17. Nó không bảo đảm toàn bộ dependency bên ngoài, cấu hình runtime hoặc hành vi ứng dụng tương thích; các phần đó vẫn cần được kiểm tra riêng.

### Bước 4: Kiểm thử trên đúng JDK và môi trường mục tiêu

Tạo môi trường kiểm thử gần với production nhất có thể, bao gồm cùng loại image, cấu hình JVM, dependency và giới hạn tài nguyên. Chạy ít nhất các nhóm kiểm tra sau:

| Nhóm kiểm tra | Nội dung cần xác nhận |
|---|---|
| Build | Mã nguồn biên dịch được; dependency được phân giải và đóng gói đúng. |
| Khởi động | JVM chấp nhận mọi cờ; ứng dụng nạp class, cấu hình và bean thành công. |
| Tích hợp | Database, message broker, HTTP client, TLS và các dịch vụ bên ngoài kết nối được. |
| Nghiệp vụ | Các luồng chính và các trường hợp biên cho kết quả đúng. |
| Dữ liệu | File, encoding, ngày giờ, locale và serialization được xử lý đúng. |
| Bảo mật | Chứng chỉ, TLS, thuật toán và xác thực hoạt động theo chính sách mới. |
| Hiệu năng | Thông lượng, độ trễ, bộ nhớ, thread và GC đáp ứng mục tiêu. |
| Vận hành | Log, metric, tracing, health check, shutdown và restart hoạt động bình thường. |

Không chỉ kiểm tra đường đi thành công. Cần thử các trường hợp lỗi, timeout, tải cao, dữ liệu lớn và các kết nối ít được sử dụng nhưng quan trọng.

### Bước 5: Triển khai có kiểm soát và quan sát

Sau khi kiểm thử đạt yêu cầu, triển khai thử trên staging hoặc một nhóm instance nhỏ. Theo dõi log khởi động, exception, lỗi kết nối, tỷ lệ request thất bại, độ trễ p95/p99, mức dùng heap/native memory và hoạt động GC.

Nếu dùng rolling deployment, cần biết trong khoảng thời gian chuyển đổi có những phiên bản JDK nào đang cùng phục vụ request. Kiểm tra tính tương thích của giao thức và dữ liệu giữa các instance trong giai đoạn này.

Chuẩn bị trước image hoặc artifact của phiên bản cũ, cấu hình tương ứng và quy trình rollback. Nếu xuất hiện lỗi vượt ngưỡng, có thể quay lại môi trường đã biết là ổn định trong khi tiếp tục điều tra. Chỉ kết thúc migration khi toàn bộ instance đã chạy đúng phiên bản mục tiêu và các chỉ số vận hành giữ ổn định trong khoảng quan sát phù hợp.

## 7. Phân biệt nâng cấp bản vá và nâng cấp phiên bản lớn

Không phải mọi lần nâng JDK đều có mức độ thay đổi như nhau.

- **Nâng bản vá (patch update):** thường tập trung vào sửa lỗi và bảo mật trong cùng nhánh phát hành. Dù phạm vi thay đổi thường hẹp hơn, bản vá vẫn có thể cập nhật danh sách thuật toán bị vô hiệu hóa, chứng chỉ tin cậy hoặc sửa hành vi có liên quan đến ứng dụng.
- **Nâng phiên bản lớn (major release):** có thể bổ sung API, thay đổi JVM, cập nhật mặc định, loại bỏ API/module cũ và thay đổi yêu cầu của công cụ hoặc dependency. Cần đánh giá rộng hơn và kiểm thử migration đầy đủ.
- **Đổi vendor hoặc bản phân phối:** ngay cả khi cùng ghi một số phiên bản Java, các bản phân phối có thể khác về cách đóng gói, thành phần đi kèm, bản vá và hỗ trợ nền tảng. Cần kiểm tra đúng bản phân phối sẽ dùng trong production.

Vì vậy, “chỉ nâng một bản vá” không đồng nghĩa với không có rủi ro. Mức kiểm tra có thể được điều chỉnh theo phạm vi thay đổi, nhưng vẫn phải xác nhận các chức năng và yêu cầu bảo mật quan trọng.

## 8. Những nhận định dễ dẫn đến migration thiếu an toàn

| Nhận định | Vì sao chưa đủ | Cách đánh giá phù hợp |
|---|---|---|
| “Mã nguồn compile được nên ứng dụng tương thích.” | Compile không kiểm tra đầy đủ runtime, reflection, TLS, dữ liệu và hiệu năng. | Kiểm tra build, startup, integration, nghiệp vụ và vận hành. |
| “JDK mới luôn chạy được mọi ứng dụng cũ.” | API/module có thể bị loại bỏ; truy cập nội bộ có thể bị chặn; mặc định có thể thay đổi. | Đối chiếu migration guide, dependency và kiểm thử trên JDK mục tiêu. |
| “Không sửa mã nguồn thì hành vi sẽ giữ nguyên.” | Runtime, thư viện chuẩn, bảo mật, dữ liệu và môi trường đã thay đổi. | So sánh kết quả và chỉ số của cùng ứng dụng trên hai môi trường. |
| “Ứng dụng khởi động thành công là đủ.” | Lỗi có thể chỉ xuất hiện ở một nhánh nghiệp vụ, kết nối hoặc tải cụ thể. | Kiểm thử các luồng đại diện, trường hợp biên và tải thực tế. |
| “Cùng số phiên bản Java thì mọi bản JDK đều giống nhau.” | Vendor, bản phân phối, hệ điều hành và thành phần đóng gói có thể khác. | Ghi nhận và kiểm thử đúng bản JDK sẽ triển khai. |

## 9. Kết luận

Nâng cấp JDK là thay đổi nền tảng thực thi của ứng dụng. Ảnh hưởng có thể đến từ compiler, bytecode, JVM, thư viện chuẩn, module system, bảo mật, các giá trị mặc định, dependency hoặc môi trường hệ điều hành. Vì các lớp này liên kết với nhau, ứng dụng không cần thay đổi mã nguồn vẫn có thể gặp lỗi hoặc thay đổi hành vi sau khi nâng cấp.

Một migration an toàn bắt đầu bằng việc ghi nhận chính xác môi trường hiện tại, xác định thay đổi từ JDK mục tiêu, kiểm tra dependency và cấu hình, sau đó chạy kiểm thử trên môi trường gần production. Cuối cùng, triển khai theo từng bước, quan sát các chỉ số vận hành và giữ sẵn phương án rollback. Cách tiếp cận này giúp biến việc nâng JDK từ một thay đổi có nhiều giả định thành một thay đổi có phạm vi, bằng chứng và khả năng kiểm soát rõ ràng.
