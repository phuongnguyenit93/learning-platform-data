# Exception event trong Java Flight Recorder

**Exception event** là sự kiện JFR ghi nhận hoạt động ném exception hoặc Error trong JVM. Khi được bật, các event này cung cấp thời điểm, thread, loại exception, message và stack trace để tìm nơi lỗi phát sinh. Chúng giúp trả lời câu hỏi: exception nào xuất hiện, ở code path nào, trên thread nào và tần suất có tăng trong giai đoạn incident hay không?

Trong JFR, hai event quan trọng là:

- \`jdk.JavaExceptionThrow\`: event dành cho object thuộc nhánh \`java.lang.Exception\`.
- \`jdk.JavaErrorThrow\`: event dành cho object thuộc nhánh \`java.lang.Error\`.

Ngoài ra, \`jdk.ExceptionStatistics\` cung cấp thống kê định kỳ về số object thuộc nhánh \`java.lang.Throwable\` được tạo. Đây là số liệu thống kê, khác với event chi tiết cho từng lần ném exception.

Exception event đặc biệt hữu ích khi ứng dụng có nhiều lỗi được bắt và xử lý bên trong code. Log ứng dụng có thể chỉ ghi lỗi cuối cùng, còn JFR giúp tìm các stack trace lặp lại hoặc các exception xuất hiện trước khi request thất bại. Tuy nhiên, event ghi được không tự chứng minh exception đã thoát khỏi request handler hay làm request thất bại; cần đối chiếu với log, metric, trace và custom event nghiệp vụ.

## 1. Exception trong Java và quan hệ với Throwable

Mọi exception và error trong Java đều kế thừa từ \`java.lang.Throwable\`.

~~~text
                 Throwable
                 /       \
           Exception     Error
              |
       RuntimeException
~~~

Các nhánh chính:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Checked exception | Exception phải được khai báo hoặc xử lý theo quy tắc ngôn ngữ | IOException, SQLException |
| Unchecked exception | RuntimeException và các lớp con; compiler không bắt buộc khai báo | NullPointerException, IllegalArgumentException |
| Error | Vấn đề nghiêm trọng liên quan runtime hoặc môi trường thực thi | LinkageError, StackOverflowError |
| OutOfMemoryError | Error đặc biệt khi JVM không thể cấp phát thêm bộ nhớ theo yêu cầu | OutOfMemoryError |

Checked và unchecked là cách phân loại trong Java language. JFR không có một cột riêng ghi "checked" hay "unchecked"; khi cần phân loại, hãy xem \`thrownClass\` và hệ thống kế thừa của class đó.

\`RuntimeException\` vẫn nằm dưới \`Exception\`, vì vậy nó thuộc nhóm \`jdk.JavaExceptionThrow\`. \`Error\` là nhánh khác và được phản ánh bởi \`jdk.JavaErrorThrow\`.

Một exception có thể được bắt và xử lý ngay tại chỗ, được ném tiếp lên caller, hoặc cuối cùng làm request thất bại. Chỉ nhìn thấy event không đủ để biết nhánh xử lý nào đã xảy ra.

## 2. Các event JFR liên quan đến exception

### jdk.JavaExceptionThrow

Event này ghi nhận exception thuộc nhánh \`java.lang.Exception\`. Các trường thường được quan tâm:

| Field | Ý nghĩa |
|---|---|
| startTime | Thời điểm event được ghi |
| eventThread | Thread liên quan đến event |
| thrownClass | Class cụ thể của exception |
| message | Message của exception, nếu có |
| stackTrace | Stack trace tại vị trí phát sinh event, nếu được bật |

Ví dụ loại exception có thể xuất hiện:

- \`java.lang.IllegalArgumentException\`
- \`java.lang.NullPointerException\`
- \`java.io.IOException\`
- \`java.sql.SQLException\`
- \`java.util.concurrent.TimeoutException\`

Event giúp nhóm theo loại exception và stack trace để tìm code path lặp lại. Message có thể rỗng hoặc null; không nên dùng message làm khóa duy nhất để nhóm vì message có thể chứa giá trị động.

### jdk.JavaErrorThrow

Event này dành cho object thuộc nhánh \`java.lang.Error\`. Các field thường có gồm:

- \`thrownClass\`: class của Error.
- \`message\`: message nếu có.
- \`eventThread\`: thread liên quan.
- \`stackTrace\`: call path tại nơi phát sinh event, nếu được bật.

Ví dụ:

- \`NoClassDefFoundError\`
- \`NoSuchMethodError\`
- \`LinkageError\`
- \`StackOverflowError\`

Không xem \`jdk.JavaErrorThrow\` là cơ chế bảo đảm ghi lại mọi \`OutOfMemoryError\`. Một số định nghĩa event HotSpot loại trừ OutOfMemoryError khỏi event này; khi điều tra OOME, hãy kết hợp log JVM, heap dump tự động và các công cụ memory diagnostic.

### jdk.ExceptionStatistics

\`jdk.ExceptionStatistics\` là event thống kê định kỳ. Field \`throwables\` cho biết số object thuộc nhánh \`Throwable\` được tạo trong khoảng thống kê tương ứng.

Event này hữu ích để nhận biết exception object creation tăng đột biến mà không cần giữ stack trace cho từng exception. Trong cấu hình JFR phổ biến, event được phát định kỳ khoảng một giây.

Cần phân biệt:

- \`JavaExceptionThrow\` và \`JavaErrorThrow\` cung cấp chi tiết event, gồm class và stack trace khi được bật.
- \`ExceptionStatistics\` đếm object Throwable được tạo trong khoảng thống kê.
- Object Throwable được tạo không nhất thiết đã được ném; vì vậy thống kê không phải số lượng request thất bại hoặc số exception chưa được xử lý.

### Bảng so sánh

| Event | Phạm vi | Mục đích |
|---|---|---|
| jdk.JavaExceptionThrow | Exception | Tìm loại exception và stack trace |
| jdk.JavaErrorThrow | Error | Điều tra lỗi thuộc nhánh Error |
| jdk.ExceptionStatistics | Object Throwable được tạo | Theo dõi xu hướng tổng thể |

Tên event và field có thể khác giữa JDK hoặc JVM implementation. Dùng metadata của recording và tài liệu JDK đang chạy để xác nhận.

## 3. Exception event cho biết điều gì?

Một exception event thường giúp trả lời bốn câu hỏi:

1. **Loại exception nào?** Xem \`thrownClass\`.
2. **Nó xuất hiện lúc nào?** Xem \`startTime\`.
3. **Thread nào phát sinh?** Xem \`eventThread\`.
4. **Code path nào dẫn đến nó?** Xem \`stackTrace\`.

Ví dụ minh họa:

~~~text
jdk.JavaExceptionThrow {
  startTime = 14:05:12.431
  eventThread = "http-worker-3"
  thrownClass = java.lang.IllegalArgumentException
  message = "orderId is required"
  stackTrace = [
    com.acme.OrderService.validate(OrderService.java:42)
    com.acme.OrderService.submit(OrderService.java:27)
    com.acme.OrderController.create(OrderController.java:19)
  ]
}
~~~

Đây là output minh họa, không phải output cố định của một recording.

Stack trace thường là thông tin có giá trị nhất để tìm nguồn phát sinh. Nếu cùng một exception class xuất hiện từ nhiều stack trace khác nhau, cần nhóm theo cả class và call path, không chỉ theo tên class.

### Event không phải bản sao đầy đủ của Throwable

Event JFR chuẩn không lưu toàn bộ object graph của exception. Các field như class, message, thread và stack trace giúp chẩn đoán, nhưng không thay thế object inspection hoặc log đầy đủ khi cần thiết.

Cause chain, suppressed exceptions và dữ liệu tùy chỉnh có thể không được thể hiện đầy đủ trong event chuẩn. Nếu cần một mã nghiệp vụ hoặc quan hệ request cụ thể, hãy tạo custom event với field được chọn có chủ đích.

### Event không quyết định exception có được xử lý hay không

JFR có thể ghi nhận exception dù code phía trên bắt và xử lý nó. Do đó:

- Có event không đồng nghĩa request thất bại.
- Không có event không chứng minh code không ném exception; event có thể bị tắt, bị throttle hoặc nằm ngoài thời gian recording.
- Event không thay thế log về kết quả xử lý.
- Cần kết hợp custom event, log hoặc trace để biết exception có làm thao tác nghiệp vụ thất bại hay không.

## 4. Cấu hình mặc định và giới hạn tần suất

Một thay đổi đáng chú ý bắt đầu từ JDK 25: \`jdk.JavaExceptionThrow\` được bật mặc định trong cấu hình JFR chuẩn và được giới hạn ở **100 event mỗi giây**. Điều này giúp thu thập thông tin exception hữu ích mà không để một ứng dụng ném exception liên tục tạo ra recording quá lớn.

Các điểm cần nhớ:

- JDK cũ có thể tắt \`JavaExceptionThrow\` trong template mặc định.
- Từ JDK 25, cấu hình chuẩn bật event và giới hạn tốc độ ở 100/s.
- Stack trace thường được bật cho event này trong template chuẩn.
- Khi exception phát sinh vượt giới hạn, recording không còn là danh sách đầy đủ mọi lần ném.
- Không dùng số event đã ghi để tính chính xác tổng exception khi throttle đang hoạt động.

Có thể kiểm tra cấu hình đang dùng trong file recording:

~~~bash
jfr metadata exceptions.jfr
~~~

Xem active settings trong recording:

~~~bash
jfr print --events jdk.ActiveSetting exceptions.jfr
~~~

Nếu event không có trong file hoặc không có stack trace, kiểm tra template và active settings trước khi kết luận rằng ứng dụng không phát sinh exception.

### Throttle không giống threshold

Hai setting này có ý nghĩa khác nhau:

| Setting | Ý nghĩa |
|---|---|
| enabled | Bật hoặc tắt event |
| stackTrace | Ghi stack trace hay không |
| throttle | Giới hạn tốc độ event tối đa theo thời gian |
| threshold | Bỏ qua duration event ngắn hơn ngưỡng |

Exception event chủ yếu là event tại thời điểm phát sinh, nên throttle là setting quan trọng để kiểm soát event volume. Không áp dụng threshold duration như cách lọc exception count.

### Khi nào nên thay đổi throttle?

Nếu cần điều tra ngắn hạn một lỗi hiếm, giới hạn mặc định có thể đủ. Nếu cần quan sát lỗi phát sinh với tần suất cao, hãy cân nhắc:

- Recording ngắn hơn.
- Chỉ bật event cần thiết.
- Giữ stack trace nếu cần xác định call site.
- Tăng giới hạn hoặc tắt throttle chỉ trong cửa sổ thử nghiệm có kiểm soát.
- Theo dõi dung lượng recording và overhead.
- Quay lại cấu hình mặc định sau khi thu thập.

Không tắt throttle cho recording dài hạn trên production nếu chưa đánh giá số lượng exception và chi phí lưu trữ.

## 5. Bật exception event khi JVM khởi động

Có thể bắt đầu recording ngay khi chạy ứng dụng:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=2m,filename=exceptions.jfr -jar app.jar
~~~

Với JDK 25+ và template chuẩn, \`jdk.JavaExceptionThrow\` được bật mặc định. Nếu cần bảo đảm event được bật trong môi trường có template tùy chỉnh, có thể chỉ định setting trực tiếp:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=2m,filename=exceptions.jfr,jdk.JavaExceptionThrow#enabled=true,jdk.JavaExceptionThrow#stackTrace=true -jar app.jar
~~~

Để ghi cả Error event:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=2m,filename=exceptions.jfr,jdk.JavaExceptionThrow#enabled=true,jdk.JavaErrorThrow#enabled=true -jar app.jar
~~~

Tên file và thời lượng là ví dụ. Hãy chọn thư mục có quyền ghi và chính sách lưu trữ phù hợp.

## 6. Bật exception event khi JVM đang chạy bằng jcmd

Không cần restart ứng dụng chỉ để bắt đầu một recording mới nếu attach mechanism và quyền truy cập cho phép.

Tìm PID:

~~~bash
jcmd -l
~~~

Kiểm tra cú pháp JFR.start trên JVM đích:

~~~bash
jcmd 2125 help JFR.start
~~~

Bắt đầu recording:

~~~bash
jcmd 2125 JFR.start name=exception-analysis settings=default duration=2m filename=/secure/records/exceptions.jfr "jdk.JavaExceptionThrow#enabled=true" "jdk.JavaExceptionThrow#stackTrace=true" "jdk.JavaErrorThrow#enabled=true" "jdk.ExceptionStatistics#enabled=true"
~~~

Thay PID và đường dẫn bằng giá trị thực tế. Các tham số event phía sau dùng dạng \`event-name#setting=value\`; dấu ngoặc kép giúp shell giữ nguyên chuỗi setting.

Kiểm tra recording:

~~~bash
jcmd 2125 JFR.check verbose=true
~~~

Dump snapshot trong khi recording vẫn chạy:

~~~bash
jcmd 2125 JFR.dump name=exception-analysis filename=/secure/records/exceptions-snapshot.jfr
~~~

JFR.dump tạo file snapshot nhưng không kết thúc recording. Khi muốn kết thúc recording:

~~~bash
jcmd 2125 JFR.stop name=exception-analysis filename=/secure/records/exceptions-final.jfr
~~~

Dùng JFR.stop khi đã thu thập đủ dữ liệu hoặc cần giải phóng recording. Nếu recording có duration, JVM cũng có thể tự kết thúc theo thời lượng đã đặt.

### Tắt exception event khi không còn cần

Có thể dùng một recording mới với event disabled hoặc cấu hình JFC riêng. Với recording đang chạy, hãy kiểm tra khả năng cập nhật setting trên JDK đích bằng help của command tương ứng; không giả định mọi setting có thể thay đổi động theo cùng cách.

## 7. Lọc và xem exception event bằng công cụ jfr

File \`.jfr\` là file nhị phân. Bắt đầu bằng summary:

~~~bash
jfr summary exceptions.jfr
~~~

Summary cho biết thời lượng recording, số lượng event và dung lượng theo từng event type. Tìm các dòng:

- \`jdk.JavaExceptionThrow\`
- \`jdk.JavaErrorThrow\`
- \`jdk.ExceptionStatistics\`

In riêng các event:

~~~bash
jfr print --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow,jdk.ExceptionStatistics exceptions.jfr
~~~

Chỉ xem exception:

~~~bash
jfr print --events jdk.JavaExceptionThrow exceptions.jfr
~~~

Chỉ xem Error:

~~~bash
jfr print --events jdk.JavaErrorThrow exceptions.jfr
~~~

Xuất JSON để xử lý bằng công cụ khác:

~~~bash
jfr print --json --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow exceptions.jfr
~~~

Kiểm tra metadata và field:

~~~bash
jfr metadata exceptions.jfr
~~~

Metadata giúp xác nhận event name, field và kiểu dữ liệu thực tế. Điều này hữu ích khi xử lý recording được tạo từ nhiều JDK release.

### Đọc một event

Khi đọc output, tập trung vào:

1. Timestamp để xác định thời điểm phát sinh.
2. \`thrownClass\` để phân loại exception.
3. \`message\` để hiểu ngữ cảnh nếu message có giá trị.
4. \`eventThread\` để tìm thread liên quan.
5. \`stackTrace\` để xác định code path.

Message có thể chứa dữ liệu động, không ổn định hoặc nhạy cảm. Không dùng message thô làm nhãn thống kê hoặc đưa trực tiếp vào dashboard công khai.

## 8. Phân tích bằng JDK Mission Control

JDK Mission Control (JMC) mở file recording và cung cấp Event Browser để lọc, nhóm và xem chi tiết event.

Quy trình:

1. Mở file exceptions.jfr trong JMC.
2. Xác nhận khoảng thời gian recording.
3. Mở Event Browser.
4. Lọc theo \`jdk.JavaExceptionThrow\` hoặc \`jdk.JavaErrorThrow\`.
5. Nhóm theo \`thrownClass\`.
6. So sánh event theo thread và stack trace.
7. Chọn một event để xem timestamp, message và call path.
8. Đối chiếu thời điểm đó với GC, CPU, lock, I/O và request latency.
9. Kiểm tra các exception lặp lại cùng một stack trace.
10. Mở source code ở frame ứng dụng để tìm điều kiện phát sinh.

Không chỉ đếm exception theo class. Một class có thể xuất hiện trong nhiều tình huống khác nhau; cùng một class nhưng stack trace khác nhau có thể biểu thị nguyên nhân khác nhau.

### Nhóm theo class

Nhóm theo \`thrownClass\` giúp tìm loại exception phổ biến nhất. Đây là bước đầu để phát hiện:

- NullPointerException tăng sau một lần deploy.
- TimeoutException xuất hiện khi dịch vụ ngoài chậm.
- IllegalArgumentException tăng do dữ liệu đầu vào.
- SQLException tăng trong thời gian database gặp sự cố.

### Nhóm theo stack trace

Nếu nhiều event có cùng class nhưng cùng stack trace, chúng có thể xuất phát từ một code path lặp lại. Tập trung vào frame đầu tiên thuộc code ứng dụng, sau đó xem caller để hiểu luồng nghiệp vụ.

### Đối chiếu timeline

Đặt exception event cùng timeline với:

- Request latency và error rate.
- GC pause và allocation.
- Thread park, monitor contention.
- Socket read/write.
- Deployment hoặc thay đổi cấu hình.
- Log của ứng dụng và dịch vụ phụ thuộc.

Nếu exception tăng cùng lúc với timeout ở socket read, nguyên nhân gốc có thể nằm ở dịch vụ bên ngoài thay vì code ném TimeoutException.

## 9. Phân biệt exception được bắt và exception làm request thất bại

JFR exception event cho biết exception được phát sinh, nhưng không tự xác định nó đã được xử lý thành công hay chưa.

Ví dụ:

~~~java
try {
    Integer.parseInt(input);
} catch (NumberFormatException ex) {
    return Optional.empty();
}
~~~

Exception vẫn được ném và bắt trong cùng method. Nó có thể xuất hiện trong JFR dù request được xử lý bình thường theo thiết kế.

Trong khi đó:

~~~java
try {
    paymentService.charge(order);
} catch (PaymentException ex) {
    throw new CheckoutFailedException(ex);
}
~~~

Một exception ban đầu có thể được bọc lại và ném tiếp. Recording có thể cho thấy nhiều event trong cùng chuỗi xử lý. Đừng đếm mỗi event như một request thất bại.

### Cần ghép với dữ liệu nào?

| Nguồn | Câu hỏi được trả lời |
|---|---|
| JFR exception event | Exception nào, ở stack trace nào, trên thread nào |
| Application log | Handler đã xử lý hay báo lỗi ra sao |
| HTTP metric | Request có trả status lỗi không |
| Distributed trace | Exception thuộc service/span nào |
| Custom business event | Thao tác nghiệp vụ thành công hay thất bại |
| Counter/metric | Tỷ lệ lỗi theo route hoặc loại nghiệp vụ |

Một dashboard tốt nên phân biệt exception volume với request failure rate. Hai chỉ số có thể tương quan nhưng không giống nhau.

## 10. Nhận diện các mẫu lỗi thường gặp

### Exception lặp lại trong vòng lặp

Dấu hiệu:

- Cùng exception class.
- Cùng stack trace.
- Số event tăng nhanh.
- CPU hoặc allocation tăng cùng thời điểm.

Cách điều tra:

- Tìm loop hoặc retry không giới hạn.
- Kiểm tra exception có được dùng làm luồng điều khiển bình thường không.
- Kiểm tra retry delay, backoff và maximum attempts.
- Xem liệu cùng input sai có được xử lý lặp lại hay không.

### NullPointerException sau deploy

Dấu hiệu:

- NPE xuất hiện ngay sau release.
- Stack trace trỏ tới method mới hoặc code path vừa thay đổi.
- Request error rate tăng cùng thời điểm.

Cách điều tra:

- Xác định frame đầu tiên thuộc code ứng dụng.
- Kiểm tra invariant và nullability của dữ liệu đầu vào.
- Đối chiếu thay đổi code/configuration.
- Thêm validation tại ranh giới hệ thống nếu cần.

### TimeoutException tăng

Dấu hiệu:

- TimeoutException xuất hiện cùng socket read hoặc thread wait dài.
- Request latency tăng.
- Connection pool hoặc worker thread có thể bị bão hòa.

Cách điều tra:

- Đối chiếu JFR I/O event.
- Kiểm tra endpoint, timeout và retry policy.
- Xem thread có đang chờ socket, lock hoặc pool hay không.
- Đối chiếu log và metric của dịch vụ phụ thuộc.

### Exception được bắt quá nhiều

Dấu hiệu:

- Exception event nhiều nhưng HTTP error rate thấp.
- Nhiều stack trace kết thúc ở cùng catch handler.
- ExceptionStatistics tăng nhanh.

Cách điều tra:

- Xác định exception là điều kiện bình thường hay dấu hiệu lỗi.
- Thay nhánh điều khiển bằng validation/return value nếu phù hợp.
- Giảm log stack trace lặp lại.
- Đặt rate limit hoặc metric theo loại lỗi.

### LinkageError hoặc NoClassDefFoundError

Dấu hiệu:

- \`jdk.JavaErrorThrow\` ghi nhận Error thuộc nhóm linkage.
- Stack trace trỏ tới class loading hoặc method invocation.
- Lỗi xuất hiện sau deploy hoặc thay đổi dependency.

Cách điều tra:

- Kiểm tra classpath/module path.
- So sánh dependency versions.
- Kiểm tra class loader và artifact packaging.
- Đối chiếu thay đổi runtime giữa môi trường.

## 11. ExceptionStatistics và đo xu hướng

\`jdk.ExceptionStatistics\` hữu ích khi muốn quan sát số lượng object Throwable được tạo theo từng khoảng thống kê.

Ví dụ minh họa:

| Khoảng thời gian | throwables |
|---|---:|
| 10:00:00 | 12 |
| 10:00:01 | 14 |
| 10:00:02 | 180 |
| 10:00:03 | 205 |
| 10:00:04 | 22 |

Một đỉnh tăng từ 14 lên 180 object trong một giây có thể gợi ý một luồng xử lý đang tạo exception với tần suất cao.

Cần nhớ:

- Đây là số object Throwable được tạo, không nhất thiết là số exception không được xử lý.
- Một object Throwable có thể được tạo nhưng không được ném.
- Exception event chi tiết có thể bị throttle.
- Không cộng số event chi tiết và số throwables như thể chúng là hai tập độc lập.
- Hãy so sánh xu hướng với request volume, workload và error rate.

Dùng thống kê để phát hiện giai đoạn bất thường, sau đó dùng event có stack trace để tìm code path.

## 12. Hiệu năng và overhead khi thu thập exception

Ném exception thường tốn chi phí hơn một nhánh điều kiện thông thường vì JVM phải tạo object và thường thu thập stack trace. JFR bổ sung chi phí ghi event, lưu field và stack trace.

Chi phí phụ thuộc:

- Tần suất exception.
- Số event được bật.
- Throttle.
- Stack trace có được ghi hay không.
- Dung lượng recording.
- Thời gian thu thập.
- Workload và JVM implementation.

Các nguyên tắc:

1. Bắt đầu với template mặc định.
2. Ghi trong một khoảng thời gian đủ để tái hiện lỗi.
3. Dùng throttle mặc định trước.
4. Chỉ tắt throttle trong cửa sổ điều tra ngắn và có kiểm soát.
5. Theo dõi CPU, recording size và latency trong lúc thu thập.
6. Tránh ghi stack trace cho mọi custom event nếu không cần.
7. Dừng recording sau khi đã thu thập đủ.

JFR được thiết kế để profiling với overhead thấp, nhưng không có cấu hình nào bảo đảm overhead bằng không. Hãy đo trên workload đại diện trước khi áp dụng cấu hình chi tiết lâu dài.

## 13. Tạo custom event cho lỗi nghiệp vụ

Event chuẩn ghi nhận loại exception và stack trace. Khi cần biết thao tác nghiệp vụ đã thất bại hay chưa, hãy tạo custom event với field đã chuẩn hóa.

Ví dụ field hữu ích:

| Field | Ý nghĩa |
|---|---|
| operation | Tên thao tác nghiệp vụ |
| failureCode | Mã lỗi ổn định |
| exceptionType | Tên class exception |
| retryable | Có thể retry hay không |
| route | Route template, không phải URL chứa dữ liệu người dùng |

Không ghi raw request, access token, password, cookie hoặc toàn bộ exception message vào custom event.

Custom event nên ghi tại boundary nơi ứng dụng biết kết quả nghiệp vụ, ví dụ trong catch handler hoặc transaction coordinator. Nhờ đó, recording phân biệt được exception đã xảy ra với thao tác thực sự thất bại.

## 14. Ví dụ Java 17+: ghi custom JFR event khi bắt exception

Ví dụ sau cố ý phát sinh ba \`IllegalArgumentException\`, bắt chúng và ghi một custom event \`com.acme.OrderFailure\` cho mỗi lần xử lý thất bại.

Cấu trúc:

~~~text
project/
  src/
    com/acme/ExceptionEventDemo.java
  out/
~~~

Tệp src/com/acme/ExceptionEventDemo.java:

~~~java
package com.acme;

import java.nio.file.Path;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class ExceptionEventDemo {

    @Name("com.acme.OrderFailure")
    @Label("Order Failure")
    @Category({"Acme", "Orders"})
    @Description("Records an order validation failure")
    static class OrderFailure extends Event {
        @Label("Operation")
        String operation;

        @Label("Failure Code")
        String failureCode;

        @Label("Exception Type")
        String exceptionType;

        @Label("Retryable")
        boolean retryable;
    }

    private static void validateOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("order-exceptions.jfr");
        int failures = 0;

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("order-exceptions");
            recording.enable(OrderFailure.class);
            recording.start();

            for (int i = 0; i < 3; i++) {
                try {
                    validateOrder("");
                } catch (IllegalArgumentException ex) {
                    OrderFailure event = new OrderFailure();

                    if (event.isEnabled()) {
                        event.operation = "validateOrder";
                        event.failureCode = "MISSING_ORDER_ID";
                        event.exceptionType = ex.getClass().getName();
                        event.retryable = false;
                        event.commit();
                    }

                    failures++;
                }
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("CAUGHT=" + failures);
        System.out.println("RECORDING=order-exceptions.jfr");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 --add-modules jdk.jfr -d out src/com/acme/ExceptionEventDemo.java
~~~

Chạy:

~~~bash
java --add-modules jdk.jfr -cp out com.acme.ExceptionEventDemo
~~~

Stdout chính xác:

~~~text
CAUGHT=3
RECORDING=order-exceptions.jfr
~~~

File \`order-exceptions.jfr\` được tạo trong working directory.

### Phân tích custom event

Xem summary:

~~~bash
jfr summary order-exceptions.jfr
~~~

In custom event:

~~~bash
jfr print --events com.acme.OrderFailure order-exceptions.jfr
~~~

Recording chứa ba event \`com.acme.OrderFailure\`, mỗi event có operation, failureCode, exceptionType và retryable.

Ví dụ này ghi mã lỗi ổn định thay vì message gốc. Cách đó hữu ích khi message có thể chứa dữ liệu đầu vào hoặc thông tin riêng tư.

## 15. Dùng custom event duration cho thời gian xử lý lỗi

Instant event cho biết lỗi đã xảy ra. Nếu cần đo thời gian xử lý hoặc recovery sau lỗi, có thể tạo duration event:

~~~java
RecoveryEvent event = new RecoveryEvent();
event.begin();

try {
    recoverFromFailure();
    event.succeeded = true;
} catch (RuntimeException ex) {
    event.succeeded = false;
    throw ex;
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

Trong ví dụ, duration bao gồm toàn bộ khoảng recovery. Field \`succeeded\` cho biết kết quả.

Không đặt duration của event nghiệp vụ bằng thời gian tồn tại của exception object. Exception throw event và recovery event trả lời hai câu hỏi khác nhau:

- Exception event: exception nào phát sinh và ở code path nào?
- Recovery event: ứng dụng mất bao lâu để xử lý hoặc phục hồi?

## 16. Lọc event theo loại và theo stack trace

Một cách phân tích hiệu quả là lọc recording theo từng loại event:

~~~bash
jfr print --events jdk.JavaExceptionThrow exceptions.jfr
~~~

Sau đó lọc Error:

~~~bash
jfr print --events jdk.JavaErrorThrow exceptions.jfr
~~~

Nếu cần xem thống kê:

~~~bash
jfr print --events jdk.ExceptionStatistics exceptions.jfr
~~~

Trong JMC, có thể lọc theo event type và xem chi tiết từng bản ghi. Khi nhóm theo stack trace, hãy chuẩn hóa các giá trị động trong message để tránh chia một lỗi thành quá nhiều nhóm.

Nếu recording lớn, xuất JSON và xử lý theo từng event thay vì in toàn bộ ra terminal:

~~~bash
jfr print --json --events jdk.JavaExceptionThrow exceptions.jfr
~~~

Với pipeline tự động, kiểm tra metadata và JDK version. Không giả định field hoặc event setting luôn giống nhau giữa mọi bản JDK.

## 17. Kết hợp exception event với các event JVM khác

Exception thường là biểu hiện cuối của một vấn đề khác. Hãy xem các event xảy ra gần cùng thời điểm:

| Event liên quan | Điều có thể phát hiện |
|---|---|
| jdk.SocketRead / jdk.SocketWrite | Chờ network hoặc dịch vụ phụ thuộc |
| jdk.FileRead / jdk.FileWrite | I/O file chậm |
| jdk.JavaMonitorEnter | Chờ synchronized monitor |
| jdk.ThreadPark | Thread bị park hoặc chờ |
| jdk.GarbageCollection | GC trùng với thời điểm lỗi |
| jdk.ExecutionSample | Code path tiêu thụ CPU |
| jdk.ClassLoad / jdk.ClassUnload | Class loading hoặc dependency issue |

Ví dụ:

- TimeoutException cùng socket read dài có thể liên quan tới network.
- RejectedExecutionException cùng thread pool saturation có thể liên quan tới queue hoặc executor.
- SQLException cùng thời gian chờ connection dài có thể liên quan tới database pool.
- NoClassDefFoundError cùng class loading event có thể liên quan tới packaging hoặc classpath.

Đây là các giả thuyết cần xác nhận bằng timeline và dữ liệu của ứng dụng, không phải kết luận tự động từ tên exception.

## 18. Bảo vệ dữ liệu trong exception recording

Exception message và stack trace có thể tiết lộ:

- Tên bảng, câu SQL hoặc endpoint nội bộ.
- File path và cấu trúc thư mục.
- Tên class, package và dependency.
- Input của người dùng được nhúng trong message.
- ID tài khoản, order ID hoặc dữ liệu nghiệp vụ.
- Thông tin xác thực nếu ứng dụng đưa secret vào message sai cách.

Các biện pháp:

1. Chỉ thu thập event cần thiết.
2. Không ghi raw request hoặc access token vào custom event.
3. Chuẩn hóa message và mã lỗi.
4. Lưu file recording trong thư mục có quyền truy cập giới hạn.
5. Mã hóa khi lưu hoặc chuyển giao theo chính sách tổ chức.
6. Giới hạn retention.
7. Kiểm tra recording trước khi chia sẻ.
8. Scrub hoặc loại event nhạy cảm khi cần.
9. Ghi nhận người thu thập và mục đích.
10. Xóa bản sao tạm sau khi điều tra hoàn tất.

Không đưa toàn bộ exception message vào metric label. Giá trị động có thể tạo cardinality rất lớn và vô tình làm lộ dữ liệu.

## 19. Troubleshooting exception event

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy JavaExceptionThrow | Event bị tắt hoặc JDK cũ dùng template tắt mặc định | Kiểm tra JFR.check, ActiveSetting và JFR version |
| Có exception nhưng số event thấp | Throttle giới hạn event rate | Kiểm tra setting throttle và ExceptionStatistics |
| Không có stack trace | stackTrace=false hoặc recording settings không bật | Bật stackTrace cho event và thu thập lại |
| Chỉ thấy một số exception class | Recording chỉ bao phủ một khoảng thời gian hoặc event bị throttle | Kéo dài cửa sổ phù hợp, xem rate limit |
| JavaErrorThrow không thấy OOME | Event chuẩn có thể loại trừ OutOfMemoryError | Dùng log JVM và HeapDumpOnOutOfMemoryError |
| Event xuất hiện nhưng request thành công | Exception đã được catch và xử lý | Đối chiếu application log và business event |
| Exception count cao nhưng log ít | Nhiều exception được bắt nội bộ hoặc log bị rate-limit | Nhóm stack trace và kiểm tra catch handler |
| Message rỗng | Exception không có message hoặc field không được ghi | Dựa vào thrownClass và stackTrace |
| JFR file quá lớn | Exception volume cao hoặc throttle bị tắt | Giới hạn duration, bật throttle và chỉ thu thập event cần thiết |
| Không thấy ExceptionStatistics | Event bị tắt hoặc không có trong template/JDK đó | Kiểm tra jfr metadata và ActiveSetting |
| JMC không mở recording | File chưa hoàn chỉnh hoặc JMC không tương thích | Chạy jfr summary và dùng JMC phù hợp |
| Script đếm sai event | Throttle, event schema hoặc JDK thay đổi | Kiểm tra metadata, version và giới hạn dữ liệu |

## 20. Quy trình điều tra exception bằng JFR

1. Xác định triệu chứng: request lỗi, exception volume tăng hay một Error xuất hiện.
2. Xác nhận JDK version và template JFR.
3. Kiểm tra recording hiện có bằng \`jcmd PID JFR.check verbose=true\`.
4. Bật \`jdk.JavaExceptionThrow\` và \`jdk.JavaErrorThrow\` nếu cần.
5. Giữ throttle mặc định trong lần thu thập đầu.
6. Bắt đầu recording ngắn đủ để tái hiện sự cố.
7. Dump file bằng JFR.dump hoặc để recording kết thúc theo duration.
8. Chạy \`jfr summary\` để kiểm tra event count.
9. In riêng JavaExceptionThrow, JavaErrorThrow và ExceptionStatistics.
10. Nhóm theo thrownClass và stack trace.
11. Tìm frame đầu tiên thuộc code ứng dụng.
12. Đối chiếu timestamp với log, request metric, trace và event JVM khác.
13. Xác định exception được catch, propagate hay làm nghiệp vụ thất bại.
14. Nếu cần, thêm custom event ở boundary nghiệp vụ.
15. Chỉ thay đổi throttle hoặc stack settings sau khi đã đánh giá overhead.
16. Lưu kết luận cùng JDK version, recording settings và thời điểm thu thập.
17. Bảo vệ file recording và áp dụng retention sau khi hoàn tất.

## 21. Ghi nhớ

- \`jdk.JavaExceptionThrow\` ghi event liên quan tới exception thuộc nhánh \`java.lang.Exception\`.
- \`jdk.JavaErrorThrow\` dành cho object thuộc nhánh \`java.lang.Error\`.
- \`jdk.ExceptionStatistics\` thống kê object \`Throwable\` được tạo; không đồng nghĩa với số request thất bại.
- JFR event giúp xem thời điểm, thread, thrownClass, message và stack trace khi các field được bật.
- Event không tự cho biết exception đã được catch, propagate hay làm request thất bại.
- Từ JDK 25, JavaExceptionThrow được bật mặc định trong cấu hình chuẩn và throttle ở 100 event/giây.
- Khi throttle hoạt động, số event ghi được không phải tổng số exception thực tế.
- Kiểm tra \`jfr metadata\` và active settings trước khi viết parser.
- Dùng \`jfr summary\` và \`jfr print --events\` để kiểm tra recording.
- JMC Event Browser giúp lọc và nhóm event theo class, thread và stack trace.
- Ghép exception event với log, metric, trace và các event I/O, lock, GC để tìm nguyên nhân gốc.
- Dùng custom JFR event để ghi mã lỗi nghiệp vụ và kết quả xử lý.
- Không ghi raw request, token, password hoặc dữ liệu cá nhân không cần thiết vào event.
- Giữ recording ngắn và throttle hợp lý khi điều tra exception volume cao.

## Tài liệu tham khảo chính thức

- [Troubleshoot Performance Issues Using Flight Recorder — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [JDK 25 Release Notes — JFR Exception Event Defaults](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html)
- [jdk.jfr Package Summary — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Event API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [EventSettings API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jfr Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)