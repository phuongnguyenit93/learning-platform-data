# Phân biệt lấy mẫu cấp phát với ghi nhận mọi lần cấp phát

Khi cần tìm nguồn tạo object nhiều trong Java, Java Flight Recorder (JFR) cung cấp hai cách quan sát chính: lấy mẫu cấp phát và ghi các event chi tiết gắn với một số đường cấp phát cụ thể. Hai cách này khác nhau về mức độ chi tiết, chi phí thu thập và cách diễn giải dữ liệu.

JDK 16 bổ sung **jdk.ObjectAllocationSample** để profiling allocation với overhead thấp. JFR vẫn có các event **jdk.ObjectAllocationInNewTLAB** và **jdk.ObjectAllocationOutsideTLAB** để quan sát những trường hợp cấp phát liên quan đến Thread Local Allocation Buffer (TLAB). Tuy nhiên, tên của hai event TLAB dễ gây hiểu nhầm: chúng không tạo ra một bản ghi cho mọi object được cấp phát trong heap. Bài học này làm rõ sự khác biệt để chọn cách thu thập phù hợp trong Java hiện đại.

## 1. Vì sao cần quan sát allocation?

Mỗi lần ứng dụng tạo object, JVM phải cấp phát vùng nhớ trên heap. Các object tạm thời thường được thu hồi nhanh, nhưng nếu ứng dụng tạo chúng với tốc độ cao, garbage collector phải làm việc nhiều hơn. Điều này có thể làm tăng tần suất GC, tiêu thụ CPU và ảnh hưởng latency.

Một số nguồn allocation thường gặp:

- Tạo DTO hoặc object trung gian khi xử lý từng request.
- Chuyển đổi dữ liệu qua nhiều lớp hoặc nhiều định dạng.
- Tạo chuỗi tạm trong vòng lặp.
- Boxing primitive thành wrapper khi không cần thiết.
- Sao chép collection hoặc tạo buffer mới cho mỗi lần đọc/ghi.
- Tạo iterator, lambda capture hoặc object callback lặp lại trong một đường xử lý nóng.

Muốn tối ưu đúng chỗ, cần xác định class nào được cấp phát nhiều, thread nào tạo chúng và stack trace dẫn tới call site nào. JFR có thể thu thập dữ liệu này với nhiều mức độ chi tiết khác nhau.

## 2. TLB và đường cấp phát object trong HotSpot

HotSpot thường sử dụng **Thread Local Allocation Buffer (TLAB)** để cấp phát object nhỏ nhanh chóng. Mỗi Java thread có một vùng cấp phát riêng. Khi còn chỗ trong TLAB, JVM có thể cấp phát object bằng cách di chuyển con trỏ trong vùng nhớ đó.

Khi TLAB hiện tại hết chỗ hoặc không còn phù hợp với object cần cấp phát, JVM có thể cấp phát một TLAB mới. Object quá lớn hoặc không phù hợp với TLAB có thể được cấp phát bên ngoài TLAB.

Có thể hình dung đơn giản:

~~~text
Java thread
   |
   +-- TLAB còn chỗ ------> cấp phát object trong TLAB hiện tại
   |
   +-- TLAB cần refill ---> cấp phát TLAB mới, rồi cấp phát object
   |
   +-- object không phù hợp TLAB ---> cấp phát ngoài TLAB
~~~

Phần lớn object nhỏ được cấp phát nhanh trong TLAB hiện có. Vì vậy, nếu chỉ ghi event khi TLAB được cấp phát mới hoặc khi object nằm ngoài TLAB, recording sẽ không có event tương ứng với mọi object trong heap.

Đây là cơ sở để hiểu đúng ba event allocation của JFR.

## 3. ObjectAllocationSample: lấy mẫu allocation

JDK 16 bổ sung event **jdk.ObjectAllocationSample** cho JFR. Event này được thiết kế để profiling allocation với overhead thấp, phù hợp với việc theo dõi thường xuyên hoặc tìm xu hướng cấp phát trong một workload.

Event có các trường chính:

| Trường | Ý nghĩa |
| --- | --- |
| **objectClass** | Class của object được chọn làm mẫu |
| **weight** | Trọng số tương đối của mẫu, tính bằng byte |
| **thread** | Thread thực hiện cấp phát |
| **stackTrace** | Call stack tại vị trí mẫu được ghi nhận |

### Hiểu đúng weight

**weight** không phải kích thước chính xác của object được lấy mẫu. Đây là trọng số đại diện cho lượng allocation tương ứng với mẫu. Khi tổng hợp weight của nhiều event theo class, thread hoặc stack trace, kết quả tạo ra một ước lượng thống kê về allocation pressure.

Ví dụ minh họa:

| Class | Tổng weight trong recording |
| --- | ---: |
| **byte[]** | 720 MB |
| **String** | 480 MB |
| **OrderDto** | 160 MB |

Bảng này gợi ý rằng **byte[]** là nhóm allocation đáng điều tra. Nó không có nghĩa recording đã ghi chính xác từng object byte array với tổng kích thước đúng bằng 720 MB. Hãy dùng weight để xếp hạng và tìm call site, sau đó đối chiếu với GC, latency và workload thực tế.

### Sampling không ghi mọi object

JFR giới hạn tần suất event sample để kiểm soát overhead. Một recording có thể chứa rất ít event so với số object ứng dụng thực sự tạo ra. Các mẫu được tổng hợp theo weight để phản ánh allocation pressure, không dùng số event đơn thuần làm tổng số object.

Tài liệu JDK 16 ghi nhận event này được bật trong cả hai cấu hình **default** và **profile**, với giới hạn tối đa tại thời điểm phát hành lần lượt là 150 và 300 event mỗi giây. Cấu hình JDK hiện hành có thể thay đổi theo phiên bản và nhà phân phối; hãy kiểm tra file JFC đang dùng trước khi dựa vào một con số cụ thể.

## 4. Hai event TLAB ghi nhận trường hợp cấp phát cụ thể

JFR còn có hai event allocation chi tiết hơn. Chúng vẫn có trong JDK hiện đại, nhưng có overhead cao hơn nên không được bật mặc định trong các cấu hình tiêu chuẩn của JDK 16.

### jdk.ObjectAllocationInNewTLAB

Event này được phát khi một allocation dẫn tới việc cấp phát hoặc refill TLAB. Nó ghi lại:

- **objectClass:** class của object làm phát sinh lần refill.
- **allocationSize:** kích thước của object đó.
- **tlabSize:** kích thước TLAB mới được cấp phát.
- **thread** và **stackTrace:** thread và call stack tại vị trí cấp phát.

Điểm quan trọng: event mô tả object khiến JVM phải refill TLAB. Nó không ghi từng object nhỏ được cấp phát sau đó trong TLAB mới. Những object được cấp phát nhanh trong TLAB đang có không tạo ra một event **ObjectAllocationInNewTLAB** riêng cho từng object.

### jdk.ObjectAllocationOutsideTLAB

Event này được phát khi object được cấp phát bên ngoài TLAB. Nó ghi lại:

- **objectClass:** class của object.
- **allocationSize:** kích thước của object.
- **thread** và **stackTrace:** thread và call stack tại vị trí cấp phát.

Với đường cấp phát ngoài TLAB, event có thể được ghi cho từng object thuộc trường hợp này. Tuy nhiên, nó không bao gồm những object được cấp phát bình thường trong TLAB hiện có.

### So sánh ba event

| Đặc điểm | ObjectAllocationSample | ObjectAllocationInNewTLAB | ObjectAllocationOutsideTLAB |
| --- | --- | --- | --- |
| Cách thu thập | Lấy mẫu | Event khi TLAB được cấp phát/refill | Event cho allocation ngoài TLAB |
| Phạm vi | Mẫu đại diện cho allocation pressure | Object làm phát sinh TLAB mới | Object được cấp phát ngoài TLAB |
| Kích thước | **weight** là trọng số mẫu | **allocationSize** và **tlabSize** | **allocationSize** |
| Stack trace | Có thể thu thập | Có thể thu thập | Có thể thu thập |
| Overhead | Thấp hơn | Cao hơn | Cao hơn |
| Phù hợp | Profiling thường xuyên, tìm hot spot | Điều tra chi tiết refill TLAB | Điều tra object cấp phát ngoài TLAB |

Vì vậy, không nên gọi hai event TLAB là chế độ ghi nhận mọi lần cấp phát trên heap. Kết hợp chúng cũng không tạo thành một trace đầy đủ cho tất cả object: các allocation thông thường bên trong TLAB hiện tại vẫn không có event riêng.

## 5. JDK 16 thay đổi cách bật event allocation như thế nào?

Theo JDK 16 Release Notes:

- **jdk.ObjectAllocationSample** được giới thiệu và bật trong **default** cùng **profile**.
- **jdk.ObjectAllocationInNewTLAB** và **jdk.ObjectAllocationOutsideTLAB** có overhead cao hơn.
- Hai event TLAB được tắt trong cả hai cấu hình tiêu chuẩn để giảm overhead.

Đây là lý do nên bắt đầu profiling bằng **ObjectAllocationSample**. Khi sampling chỉ ra một nhóm allocation đáng nghi nhưng chưa đủ chi tiết để điều tra, có thể bật thêm event TLAB trong một recording ngắn và có mục tiêu.

Các file **default.jfc** và **profile.jfc** là cấu hình mẫu đi kèm JDK. **default.jfc** hướng tới recording liên tục với overhead thấp; **profile.jfc** thu thập nhiều dữ liệu hơn và có thể ảnh hưởng hiệu năng lớn hơn. Kiểm tra cấu hình của đúng JDK đang chạy vì các mức event và thiết lập có thể khác theo phiên bản.

## 6. Khi nào nên chọn sampling, khi nào bật event TLAB?

| Tình huống | Cách thu thập nên bắt đầu |
| --- | --- |
| Muốn biết class và call site nào tạo nhiều object trong workload thực | **ObjectAllocationSample** |
| Cần profiling thường xuyên trong môi trường production | **default.jfc** với sampling mặc định |
| Điều tra ngắn một allocation hot spot đã xác định | **profile.jfc**, sau đó cân nhắc bật event TLAB |
| Nghi ngờ object lớn được cấp phát ngoài TLAB | Bật **ObjectAllocationOutsideTLAB** trong recording ngắn |
| Muốn xem những allocation làm refill TLAB | Bật **ObjectAllocationInNewTLAB** trong recording ngắn |
| Muốn đếm chính xác mọi object trên heap | Các event JFR trên không cung cấp trace đầy đủ; cần instrumentation chuyên biệt và đánh giá overhead |

Không bật event TLAB chỉ vì muốn có nhiều event hơn. Recording có nhiều event không tự động đồng nghĩa với dữ liệu hữu ích hơn. Hãy xác định câu hỏi cần trả lời trước, sau đó chọn event vừa đủ.

## 7. Tạo cấu hình JFR để bật event TLAB

Trên JDK hiện đại, có thể dùng **jfr configure** để tạo file cấu hình riêng dựa trên **profile.jfc**. Ví dụ bật hai event TLAB:

~~~bash
jfr configure --input "/path/to/jdk/lib/jfr/profile.jfc" --output allocation-detail.jfc jdk.ObjectAllocationInNewTLAB#enabled=true jdk.ObjectAllocationOutsideTLAB#enabled=true
~~~

Thay **/path/to/jdk** bằng đường dẫn JDK đang dùng. Lệnh tạo file **allocation-detail.jfc**, giữ cấu hình profile làm nền và bật hai event được chọn. Không chỉnh sửa trực tiếp file cấu hình mặc định trong thư mục JDK; hãy tạo một file riêng để dễ kiểm soát thay đổi.

Khởi chạy ứng dụng với cấu hình mới:

~~~bash
java -XX:StartFlightRecording=filename=allocation-detail.jfr,settings=allocation-detail.jfc,duration=60s -jar app.jar
~~~

Ví dụ này ghi recording trong 60 giây. Chọn khoảng thời gian đủ bao phủ workload cần điều tra và tránh giữ cấu hình chi tiết lâu hơn cần thiết.

Nếu ứng dụng đã chạy, có thể dùng **jcmd** để bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=AllocationDetail settings=allocation-detail.jfc duration=60s filename=allocation-detail.jfr
~~~

Thay **<pid>** bằng process ID của JVM cần kiểm tra. Lệnh cần chạy trên cùng máy và bằng tài khoản có quyền attach phù hợp với tiến trình JVM.

## 8. Đọc và so sánh dữ liệu trong recording

Bắt đầu bằng tổng quan recording:

~~~bash
jfr summary allocation-detail.jfr
~~~

In các event allocation TLAB:

~~~bash
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB --stack-depth 20 allocation-detail.jfr
~~~

Khi đọc kết quả, chú ý:

- **ObjectAllocationInNewTLAB:** xem class và stack trace của object làm phát sinh refill; phân biệt **allocationSize** với **tlabSize**.
- **ObjectAllocationOutsideTLAB:** xem class, kích thước và call site của object được cấp phát ngoài TLAB.
- **ObjectAllocationSample:** xem tổng weight theo class, thread và stack trace để tìm nhóm allocation có áp lực lớn.
- **Thread:** xác định allocation đến từ request handler, worker, scheduler hay tác vụ nền.
- **Stack trace:** truy ngược tới phương thức tạo object, rồi kiểm tra code có thể tránh tạo object tạm hoặc sao chép dữ liệu lặp lại hay không.

Có thể mở file **.jfr** bằng JDK Mission Control (JMC) để lọc event, nhóm theo class và xem stack trace trực quan. Khi so sánh hai recording, dùng cùng workload, cấu hình, thời lượng và điều kiện chạy để kết quả có ý nghĩa.

## 9. Ví dụ cách diễn giải dữ liệu

Giả sử recording sample cho thấy **byte[]** có weight lớn, tập trung trong stack trace của hàm đọc file. Đây là dấu hiệu nên kiểm tra cách cấp phát buffer.

Sau đó, bật event TLAB trong một recording ngắn và nhận thấy nhiều event **ObjectAllocationOutsideTLAB** đến từ một hàm xử lý ảnh. Có thể hàm này đang tạo các mảng lớn vượt khả năng cấp phát TLAB thông thường. Hãy kiểm tra kích thước buffer, số lần tạo và khả năng tái sử dụng bộ đệm theo vòng đời phù hợp.

Nếu event **ObjectAllocationInNewTLAB** xuất hiện thường xuyên, hãy xem object nào làm phát sinh refill và stack trace tương ứng. Không cộng **tlabSize** vào tổng object allocation: đây là kích thước vùng cấp phát mới, không phải kích thước object.

Sau khi thay đổi code, ghi lại JFR với cùng workload và so sánh:

1. Tổng weight của **ObjectAllocationSample** theo class và call site.
2. Số lượng cùng kích thước allocation trong các event TLAB đã bật.
3. Tốc độ GC và thời gian dành cho GC.
4. Throughput và latency của ứng dụng.

Đừng kết luận một thay đổi tốt chỉ vì số event giảm. Hãy xem cả allocation pressure, GC và hiệu năng đầu cuối.

## 10. Giới hạn và lưu ý khi cần độ chính xác cao

- **Sampling là ước lượng:** không dùng số event sample để đếm số object hoặc xem weight là kích thước chính xác của object.
- **InNewTLAB không ghi mọi object trong TLAB:** nó phản ánh allocation làm phát sinh TLAB mới.
- **OutsideTLAB chỉ phản ánh allocation ngoài TLAB:** object được cấp phát trong TLAB hiện có không xuất hiện trong event này.
- **Event chi tiết có overhead cao hơn:** chỉ bật trong thời gian và phạm vi cần thiết; đo ảnh hưởng trên workload đại diện.
- **JFR không phải bộ đếm mọi allocation:** nếu yêu cầu trace từng object, cần instrumentation ở cấp bytecode hoặc giải pháp profiling chuyên biệt. Cần kiểm tra khả năng bao phủ và đo overhead trước khi dùng trong môi trường production.
- **Allocation không đồng nghĩa memory leak:** muốn tìm object bị giữ lại lâu dài, cần xem thêm live set, GC root, heap dump hoặc event **jdk.OldObjectSample**.
- **Cấu hình phụ thuộc phiên bản:** kiểm tra file JFC và metadata của đúng JDK thay vì giả định mọi bản phân phối có cùng thiết lập.

## 11. Kết luận

**jdk.ObjectAllocationSample** phù hợp để tìm xu hướng và allocation hot spot với overhead thấp. Hai event **jdk.ObjectAllocationInNewTLAB** và **jdk.ObjectAllocationOutsideTLAB** cung cấp thông tin chi tiết hơn cho các trường hợp refill TLAB và allocation ngoài TLAB, nhưng chúng không ghi lại mọi object được cấp phát trên heap.

Trong Java hiện đại, hãy bắt đầu bằng sampling, dùng event TLAB trong recording ngắn khi cần thêm bằng chứng, rồi phân tích class, weight, kích thước và stack trace. Chọn mức thu thập theo câu hỏi cần trả lời, kiểm tra overhead và xác nhận kết quả bằng workload tương đương sau khi tối ưu.

## Tài liệu tham khảo

- [Consolidated JDK 16 Release Notes — New jdk.ObjectAllocationSample Event](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 16](https://docs.oracle.com/en/java/javase/16/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Flight Recorder Configurations — Java SE 27](https://docs.oracle.com/en/java/javase/27/jfapi/flight-recorder-configurations.html)
- [Diagnostic Tools — Java SE 27](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [The jfr Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [JFR Event Metadata — OpenJDK](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml)
- [HotSpot Allocation Implementation — OpenJDK](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/memAllocator.cpp)

