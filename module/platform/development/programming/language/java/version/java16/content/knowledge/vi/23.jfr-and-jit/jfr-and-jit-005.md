# Đọc allocation sample theo stack trace để tìm điểm tạo đối tượng

Java Flight Recorder (JFR) có event **jdk.ObjectAllocationSample** để lấy mẫu hoạt động cấp phát object. Mỗi mẫu cho biết class của object được ghi nhận, trọng số cấp phát (**weight**), thread và stack trace tại vị trí lấy mẫu. Khi nhóm và tổng hợp weight theo class hoặc stack trace, có thể tìm ra những đường code đang tạo nhiều áp lực cấp phát bộ nhớ.

Đọc allocation sample không chỉ là tìm class có nhiều mẫu. Cần kết hợp ba góc nhìn: **objectClass** cho biết loại object, **weight** giúp ước lượng lượng cấp phát được đại diện, còn **stackTrace** chỉ ra đường gọi dẫn tới điểm tạo object. Bài học này trình bày quy trình từ recording tới call site, cách diễn giải dữ liệu và cách xác nhận hiệu quả sau khi tối ưu.

## 1. Allocation sample cung cấp thông tin gì?

Event **jdk.ObjectAllocationSample** được bổ sung trong JDK 16 và vẫn được hỗ trợ trong các JDK hiện đại. Những field quan trọng gồm:

| Field | Ý nghĩa khi phân tích |
| --- | --- |
| **objectClass** | Class của object được chọn làm mẫu, ví dụ **byte[]**, **String** hoặc **OrderDto** |
| **weight** | Trọng số mẫu tính bằng byte, dùng để ước lượng allocation pressure |
| **eventThread** | Thread thực hiện hoạt động cấp phát được lấy mẫu |
| **stackTrace** | Call stack tại điểm ghi nhận mẫu, giúp truy ngược đường code tạo object |
| **startTime** | Thời điểm mẫu được ghi nhận trong recording |

Điểm quan trọng nhất là **weight không phải kích thước chính xác của riêng object được chọn làm mẫu**. Đây là trọng số tương đối đại diện cho lượng cấp phát được lấy mẫu. JFR dùng sampling để giảm overhead thay vì phát event cho mọi object; khi tổng hợp weight của nhiều mẫu theo class, thread hoặc stack trace, kết quả tạo ra ước lượng thống kê về allocation pressure.

Vì vậy, cần phân biệt hai chỉ số:

- **Số mẫu (sample count):** số event đã được ghi nhận cho một nhóm.
- **Tổng weight:** lượng cấp phát ước lượng được đại diện bởi các mẫu trong nhóm đó.

Một nhóm có nhiều event chưa chắc có tổng weight lớn nhất. Ngược lại, một số mẫu có weight cao có thể đại diện cho lượng cấp phát đáng kể. Khi xếp hạng hot spot, hãy xem cả hai, nhưng ưu tiên tổng weight và tỷ trọng theo mục tiêu giảm allocation.

## 2. Hiểu mối quan hệ giữa class, thread và stack trace

Một allocation sample nên được đọc như một dấu vết gồm ba câu hỏi:

1. **Object nào được cấp phát?** Xem **objectClass**.
2. **Luồng nào thực hiện?** Xem **eventThread**.
3. **Đường code nào dẫn tới allocation?** Xem **stackTrace**.

Ví dụ minh họa một event được in ra:

~~~text
jdk.ObjectAllocationSample {
  startTime = 09:42:18.125
  objectClass = byte[] (classLoader = bootstrap)
  weight = 768.0 kB
  eventThread = "http-nio-8080-exec-7" (javaThreadId = 47)
  stackTrace = [
    java.util.Arrays.copyOf(...)
    java.lang.String.getBytes(...)
    com.example.InvoiceFormatter.format(...)
    com.example.InvoiceService.createReceipt(...)
    com.example.InvoiceController.handle(...)
  ]
}
~~~

Đây là dữ liệu minh họa để giải thích cách đọc:

- **byte[]** là class của object được chọn làm mẫu.
- **768.0 kB** là weight của mẫu, không phải kết luận rằng một mảng byte duy nhất có kích thước 768 KB.
- **http-nio-8080-exec-7** là thread đang xử lý request.
- Stack trace dẫn từ thao tác cấp phát trong thư viện tới các phương thức ứng dụng như **InvoiceFormatter.format()** và **InvoiceService.createReceipt()**.

Khi đọc stack trace, hãy tìm frame thuộc code ứng dụng gần điểm cấp phát, sau đó đi ngược các caller để hiểu vì sao đường code đó được gọi thường xuyên. Các frame thư viện như **Arrays.copyOf()** hoặc phương thức xử lý chuỗi có thể là nơi cấp phát trực tiếp; frame ứng dụng phía trên thường cho biết nghiệp vụ nào kích hoạt allocation.

Không kết luận chỉ dựa vào tên class. Ví dụ, **byte[]** có thể được tạo bởi xử lý ảnh, đọc file, mã hóa, nén, chuyển đổi chuỗi hoặc thư viện mạng. Stack trace và thread giúp phân biệt các nguyên nhân này.

## 3. Ghi recording có đủ dữ liệu allocation

Trước khi phân tích, hãy bảo đảm recording bật event allocation sample và stack trace. Cấu hình JFR **profile** thường phù hợp cho một phiên profiling ngắn:

~~~bash
java -XX:StartFlightRecording=filename=allocation-profile.jfr,settings=profile,duration=3m -jar app.jar
~~~

Chạy workload đại diện trong thời gian recording. Nếu ứng dụng đang hoạt động, có thể bắt đầu recording bằng **jcmd**:

~~~bash
jcmd <pid> JFR.start name=AllocationProfile settings=profile duration=3m filename=allocation-profile.jfr
~~~

Cấu hình **profile** thu thập nhiều dữ liệu hơn **default**, nên thường phù hợp với phiên điều tra có giới hạn thời gian. Với recording dài hạn, cân nhắc **default** và đánh giá overhead trong môi trường triển khai.

Sau khi recording kết thúc, kiểm tra tổng quan:

~~~bash
jfr summary allocation-profile.jfr
~~~

Xác nhận recording có thời lượng phù hợp và có event **jdk.ObjectAllocationSample**. Nếu event không xuất hiện, kiểm tra cấu hình JFC và workload: event có thể chưa được bật, recording quá ngắn hoặc khoảng ghi không có allocation phù hợp.

## 4. In allocation sample và stack trace bằng jfr

Dùng **jfr print** để xem event:

~~~bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 20 allocation-profile.jfr
~~~

Các tham số:

- **--events jdk.ObjectAllocationSample** chỉ in event allocation sample.
- **--stack-depth 20** yêu cầu hiển thị tối đa 20 frame stack trace để có thêm ngữ cảnh caller.

Nếu output dài, có thể chuyển kết quả vào file văn bản để tìm kiếm hoặc lọc theo class và tên package. Không nên đọc recording bằng cách in toàn bộ event khi ứng dụng có nhiều hoạt động; lọc đúng event trước sẽ dễ tập trung hơn.

Ví dụ một số mẫu cùng class nhưng khác stack trace:

~~~text
objectClass = byte[]
weight = 2.4 MB
eventThread = "http-nio-8080-exec-7"
stackTrace = [
  java.util.Arrays.copyOf(...)
  com.example.InvoiceFormatter.format(...)
  com.example.InvoiceService.createReceipt(...)
]

objectClass = byte[]
weight = 1.1 MB
eventThread = "file-worker-2"
stackTrace = [
  java.nio.ByteBuffer.allocate(...)
  com.example.FileImporter.readChunk(...)
]
~~~

Hai mẫu đều liên quan tới **byte[]**, nhưng đường cấp phát khác nhau. Mẫu thứ nhất xuất phát từ xử lý hóa đơn; mẫu thứ hai đến từ đọc file. Nếu chỉ xem tổng allocation theo class, hai nguồn này sẽ bị gộp lại và khó xác định phương án tối ưu phù hợp.

## 5. Nhóm mẫu theo class để tìm loại object nổi bật

Bắt đầu bằng việc xem class nào có tổng weight cao. Một bảng tổng hợp minh họa:

| Class | Sample count | Tổng weight | Tỷ trọng |
| --- | ---: | ---: | ---: |
| **byte[]** | 420 | 1.8 GB | 45% |
| **String** | 510 | 1.1 GB | 28% |
| **HashMap$Node** | 180 | 620 MB | 15% |
| **OrderDto** | 95 | 480 MB | 12% |

Số liệu trên chỉ minh họa cách xếp hạng, không phải kết quả benchmark hoặc recording thực tế.

Cách diễn giải:

- **byte[]** có tổng weight lớn nhất: kiểm tra thao tác sao chép buffer, chuyển đổi dữ liệu, đọc file, mã hóa hoặc nén.
- **String** có sample count cao: xem xử lý chuỗi, parse, format, ghép chuỗi hoặc tạo chuỗi trung gian.
- **HashMap$Node** có weight đáng chú ý: xem code tạo map mới, mở rộng map hoặc nạp nhiều entry.
- **OrderDto** xuất hiện nhiều: xác định DTO có thực sự cần tạo ở từng bước hay có thể giảm bước chuyển đổi dữ liệu.

Không tối ưu một class chỉ vì nó đứng đầu bảng. Allocation có thể là chi phí cần thiết để biểu diễn kết quả nghiệp vụ. Hãy xem class đó được tạo ở đâu, có thể tránh tạo lặp lại không và nó có ảnh hưởng tới GC hoặc latency hay không.

## 6. Nhóm theo stack trace để tìm call site

Sau khi xác định class nổi bật, chuyển sang nhóm mẫu theo stack trace. Mục tiêu là tìm phương thức hoặc đường gọi chịu trách nhiệm cho phần lớn weight.

Một ví dụ tổng hợp theo call site:

| Stack trace / phương thức ứng dụng | Class nổi bật | Tổng weight | Nhận định ban đầu |
| --- | --- | ---: | --- |
| **InvoiceFormatter.format()** | **byte[]**, **String** | 920 MB | Có thể tạo nhiều dữ liệu chuỗi hoặc buffer trung gian |
| **FileImporter.readChunk()** | **byte[]** | 610 MB | Kiểm tra kích thước và vòng đời buffer |
| **OrderMapper.toDto()** | **OrderDto**, **HashMap$Node** | 430 MB | Kiểm tra chuyển đổi và tạo collection lặp lại |

Tổng weight theo stack trace giúp xác định call site nào đáng điều tra trước. Một phương thức có thể xuất hiện trong nhiều stack trace khác nhau; khi đó, hãy xem tổng hợp theo method hoặc theo nhánh stack phù hợp với câu hỏi.

### Đọc stack trace theo hướng từ allocation tới caller

Khi mở một stack trace:

1. Xác định frame gần thao tác cấp phát trực tiếp, thường là phương thức thư viện hoặc constructor.
2. Tìm frame đầu tiên thuộc package của ứng dụng.
3. Đọc các caller phía trên để hiểu đường xử lý nghiệp vụ.
4. So sánh các stack trace cùng class để phát hiện nhiều nguồn cấp phát khác nhau.
5. Ưu tiên call site có tổng weight cao và xuất hiện trong workload quan trọng.

Nếu stack trace chỉ hiển thị frame thư viện, tăng **--stack-depth** hoặc mở recording bằng JMC để xem thêm caller. Nếu recording không thu stack trace, cần tạo recording mới với cấu hình có stack trace; không thể khôi phục call stack đã không được ghi.

## 7. Dùng JDK Mission Control để xem allocation profile

JDK Mission Control (JMC) cung cấp giao diện để nhóm allocation và xem stack trace dễ dàng hơn so với đọc output văn bản.

Quy trình cơ bản:

1. Mở file **allocation-profile.jfr** trong JMC.
2. Mở trang **Method Profiling** hoặc khu vực phân tích allocation tương ứng với phiên bản JMC.
3. Xem danh sách top allocation theo class, package hoặc method.
4. Chọn class hoặc method nổi bật để xem stack trace.
5. Dùng bảng và biểu đồ để so sánh tỷ trọng allocation giữa các đường code.
6. Đối chiếu với thread và khoảng thời gian trên timeline.

Trong JMC, phân biệt số lượng sample với lượng cấp phát được ước lượng. Trang **Method Profiling** hiển thị top allocations theo package và class, sau đó cho phép kiểm tra stack trace để tìm code liên quan. Nếu cần đối chiếu chính xác tổng **weight** của event, hãy xem chi tiết event hoặc dùng **jfr print**; cách trình bày và tên cột có thể khác theo phiên bản JMC. Không diễn giải số sample thành số byte.

Khi nhiều stack trace cùng đi qua một phương thức, hãy xem tổng weight được gộp theo method. Phương thức xuất hiện ở nhiều đường gọi có thể là điểm tối ưu có ảnh hưởng rộng.

## 8. Ví dụ thực tế: tìm allocation do ghép chuỗi lặp lại

Giả sử một endpoint tạo nội dung hóa đơn từ danh sách dòng hàng:

~~~java
public String formatReceipt(List<OrderLine> lines) {
    String receipt = "";

    for (OrderLine line : lines) {
        receipt += line.name()
            + ": "
            + line.quantity()
            + "\n";
    }

    return receipt;
}
~~~

Nếu danh sách có nhiều dòng, mỗi lần ghép chuỗi trong vòng lặp có thể tạo chuỗi và mảng dữ liệu mới. Các phần nội dung trước đó được sao chép vào kết quả mới. Trong JFR, có thể thấy **String** hoặc **byte[]** với weight đáng kể và stack trace đi qua **formatReceipt()**.

Sau khi xác nhận call site, thử dùng **StringBuilder**:

~~~java
public String formatReceipt(List<OrderLine> lines) {
    StringBuilder receipt = new StringBuilder();

    for (OrderLine line : lines) {
        receipt.append(line.name())
            .append(": ")
            .append(line.quantity())
            .append('\n');
    }

    return receipt.toString();
}
~~~

Cách viết này xây dựng nội dung trong một builder và chỉ tạo chuỗi kết quả cuối cùng. Nó thường giảm việc tạo các chuỗi trung gian trong vòng lặp. Tuy nhiên, hãy đo lại bằng cùng workload để xác nhận mức cải thiện và bảo đảm định dạng đầu ra không đổi.

Một số nguồn allocation khác và hướng kiểm tra:

| Dấu hiệu trong sample | Vị trí cần xem | Hướng điều tra |
| --- | --- | --- |
| **byte[]** và stack có copy/encode | Xử lý file, network, charset | Kiểm tra sao chép buffer và chuyển đổi lặp |
| **String** và stack có format/concat | Formatter, serializer, mapper | Kiểm tra ghép chuỗi và tạo chuỗi trung gian |
| **HashMap$Node** | Khởi tạo hoặc nạp map | Kiểm tra map mới được tạo trong vòng lặp, capacity và số entry |
| **ArrayList**, **Object[]** | Tạo hoặc mở rộng collection | Kiểm tra kích thước dự kiến và các bản sao collection |
| Wrapper như **Integer** hoặc **Long** | Boxing trong generic hoặc API object | Kiểm tra boxing không cần thiết trong đường code nóng |

Các dấu hiệu chỉ gợi ý nơi cần xem code. Chúng không tự chứng minh rằng một API hoặc class là nguyên nhân gốc.

## 9. Phân biệt allocation hot spot với memory leak

Allocation sample chỉ ra nơi object được tạo. Nó không cho biết object có tiếp tục được giữ lại sau khi không còn cần thiết hay không.

| Câu hỏi | Dữ liệu nên xem |
| --- | --- |
| Object được tạo ở đâu? | **jdk.ObjectAllocationSample**, stack trace |
| Class hoặc call site nào tạo nhiều allocation? | Tổng weight theo class, method và stack trace |
| Object nào sống lâu bất thường? | **jdk.OldObjectSample**, dữ liệu live object hoặc heap dump |
| Object còn được giữ bởi ai? | Đường dẫn tới GC root và phân tích heap |
| Allocation có gây áp lực GC không? | Allocation rate, GC events, pause time và heap usage |

Một phương thức có allocation weight cao chưa chắc gây memory leak. Nó có thể tạo nhiều object ngắn hạn và các object đó được thu hồi bình thường. Ngược lại, memory leak có thể đến từ một số ít object bị giữ tham chiếu lâu dài.

Nếu nghi ngờ leak, hãy chuyển sang phân tích object sống lâu, **OldObjectSample**, GC root hoặc heap dump. Không dùng riêng allocation stack trace để kết luận object bị rò rỉ.

## 10. Xác nhận tối ưu bằng recording trước và sau

Sau khi thay đổi code, ghi một recording mới với điều kiện tương đương:

- Cùng cấu hình JFR, nhất là event và stack trace.
- Cùng thời lượng và workload đại diện.
- Cùng số request hoặc cùng lượng dữ liệu đầu vào nếu có thể.
- Cùng môi trường JDK, CPU, heap và cấu hình ứng dụng.
- So sánh tổng weight theo class, stack trace và method.

Để so sánh công bằng khi lượng request khác nhau, có thể chuẩn hóa tổng weight theo số request đã xử lý. Ví dụ:

\[
\text{Estimated bytes/request} =
\frac{\text{Total sample weight}}{\text{Completed requests}}
\]

Đây là chỉ số ước lượng từ sampling, không phải phép đo byte chính xác cho từng request. Chỉ so sánh khi cách ghi và workload đủ tương đồng.

Ngoài allocation, hãy theo dõi thêm:

- GC frequency và thời gian pause.
- Heap usage và allocation rate.
- Throughput.
- p95/p99 latency.
- CPU usage.

Một thay đổi có thể giảm allocation nhưng làm tăng CPU hoặc latency. Chỉ kết luận tối ưu thành công khi số liệu runtime và yêu cầu nghiệp vụ đều phù hợp.

## 11. Quy trình thực hành từ sample tới điểm tạo object

Có thể áp dụng quy trình sau cho một hot spot:

1. Ghi JFR với **settings=profile** trong một khoảng thời gian ngắn có workload đại diện.
2. Kiểm tra **jfr summary** và xác nhận có **jdk.ObjectAllocationSample**.
3. In event bằng **jfr print --events jdk.ObjectAllocationSample --stack-depth 20**.
4. Nhóm tổng weight theo **objectClass** để tìm loại object nổi bật.
5. Nhóm theo **stackTrace** hoặc method để tìm đường code tạo object.
6. Dùng **eventThread** và timestamp để xác định workload hoặc tác vụ nền.
7. Mở code tại frame ứng dụng gần điểm cấp phát và tìm thao tác tạo object lặp lại.
8. Đưa ra thay đổi nhỏ có giả thuyết rõ ràng; không thêm cache hoặc object pool chỉ dựa trên một bảng xếp hạng.
9. Ghi lại JFR với workload tương đương và so sánh weight, GC, throughput và latency.
10. Nếu nghi ngờ object bị giữ lại lâu, chuyển sang công cụ phân tích live object hoặc heap dump.

## 12. Kết luận

Đọc **jdk.ObjectAllocationSample** theo stack trace giúp chuyển từ nhận định chung như “ứng dụng tạo nhiều object” sang một phương thức và đường gọi cụ thể cần điều tra. **objectClass** cho biết loại object, **weight** ước lượng lượng allocation được đại diện, **eventThread** xác định luồng và **stackTrace** chỉ ra call site.

Hãy nhóm weight theo class và stack trace, tìm frame ứng dụng gần điểm cấp phát, rồi kiểm tra code dưới workload thực tế. Sau tối ưu, ghi lại JFR với điều kiện tương đương và so sánh allocation cùng GC, throughput và latency. Nhớ rằng allocation sample chỉ mô tả nơi tạo object; muốn tìm object bị giữ lại và memory leak, cần dữ liệu về object sống lâu và đường dẫn tới GC root.

## Tài liệu tham khảo

- [JDK 16 Release Notes — New jdk.ObjectAllocationSample Event](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [JFR Event Metadata — ObjectAllocationSample, OpenJDK](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml)
- [JDK Mission Control 9 — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
- [JDK Mission Control 9 User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html)
- [Java SE 27 — Diagnostic Tools and Flight Recorder](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [Java SE 27 — JFR Configuration](https://docs.oracle.com/en/java/javase/27/jfapi/flight-recorder-configurations.html)

