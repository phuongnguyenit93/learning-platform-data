# Sự kiện jdk.ObjectAllocationSample được bổ sung trong Java 16

JDK 16 bổ sung sự kiện **jdk.ObjectAllocationSample** cho Java Flight Recorder (JFR), giúp theo dõi hoạt động cấp phát object với overhead thấp. Sự kiện này ghi lại mẫu object được cấp phát, lớp của object, stack trace và trọng số mẫu (**weight**). Khi tổng hợp trọng số của nhiều mẫu theo class, thread hoặc stack trace, lập trình viên có thể ước lượng khu vực nào đang tạo ra nhiều áp lực cấp phát bộ nhớ.

Sự kiện này vẫn hữu ích trong Java hiện đại. Nó được bật trong các cấu hình JFR tiêu chuẩn, bao gồm **default** và **profile**. Bài học tập trung vào cách ghi recording, đọc dữ liệu và dùng kết quả để tìm nguồn cấp phát object nhiều trong ứng dụng.

## 1. Vì sao JDK 16 bổ sung ObjectAllocationSample?

Ứng dụng Java liên tục tạo object trong quá trình xử lý request, chuyển đổi dữ liệu, xây dựng chuỗi, tạo collection và thực thi các tác vụ nghiệp vụ. Nhiều object tồn tại rất ngắn rồi được garbage collector thu hồi. Mỗi lần cấp phát có thể rẻ, nhưng nếu tốc độ cấp phát quá cao, ứng dụng có thể tạo thêm áp lực cho garbage collector, tăng số lần thu gom vùng trẻ và ảnh hưởng độ trễ.

Trước JDK 16, JFR có các event như **jdk.ObjectAllocationInNewTLAB** và **jdk.ObjectAllocationOutsideTLAB** để mô tả một số hoạt động cấp phát liên quan đến Thread Local Allocation Buffer (TLAB). Các event này cung cấp chi tiết allocation nhưng có overhead cao hơn.

JDK 16 bổ sung **jdk.ObjectAllocationSample** để hỗ trợ profiling cấp phát theo mẫu với overhead thấp hơn. Theo JDK 16 Release Notes:

- Event được bật trong cấu hình **default** và **profile**.
- Tại thời điểm giới thiệu, giới hạn tối đa là 150 event mỗi giây trong **default** và 300 event mỗi giây trong **profile**.
- Các event TLAB cũ có overhead cao hơn và được tắt trong cả hai cấu hình tiêu chuẩn để giảm overhead.

Các cấu hình JFR hiện hành vẫn duy trì cách tiếp cận này: **default.jfc** dùng cho recording liên tục với mức chi tiết thấp và **profile.jfc** thu thập nhiều dữ liệu hơn trong khoảng thời gian ngắn. Vì vậy, khi cần điều tra allocation, hãy bắt đầu với event lấy mẫu này và chọn cấu hình phù hợp với mục tiêu recording.

## 2. ObjectAllocationSample ghi lại thông tin gì?

**jdk.ObjectAllocationSample** thuộc nhóm **Java Application**. Event có các thông tin quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| **objectClass** | Class của object được chọn làm mẫu |
| **weight** | Trọng số của mẫu, biểu diễn bằng byte |
| **thread** | Thread thực hiện hoạt động cấp phát |
| **stackTrace** | Call stack tại vị trí cấp phát được ghi nhận |

Trường **weight** là điểm cần hiểu đúng. Nó không đơn giản là kích thước chính xác của object được chọn mẫu và cũng không phải số byte của riêng một lần gọi **new**. Đây là trọng số tương đối của mẫu. Khi cộng trọng số của nhiều mẫu theo một class, thread hoặc stack trace, kết quả tạo ra một ước lượng có ý nghĩa thống kê về áp lực cấp phát.

Ví dụ minh họa:

| Mẫu | Class | Weight |
| --- | --- | ---: |
| 1 | **byte[]** | 320 KB |
| 2 | **String** | 480 KB |
| 3 | **byte[]** | 400 KB |
| 4 | **OrderDto** | 160 KB |

Khi tổng hợp, **byte[]** có tổng weight 720 KB, còn **String** có 480 KB. Điều này gợi ý rằng cấp phát mảng byte đang chiếm tỷ trọng đáng chú ý trong khoảng recording được quan sát. Các con số trên chỉ là ví dụ để minh họa cách đọc; không phải số liệu từ một recording thực tế.

Không diễn giải một event có weight 320 KB thành một object **byte[]** duy nhất có kích thước 320 KB. Một mẫu có thể đại diện cho lượng cấp phát lớn hơn object được chọn làm mẫu. Hãy xem weight theo nhóm mẫu và thời gian quan sát.

## 3. Phân biệt allocation sampling với ghi nhận mọi object

**ObjectAllocationSample** là event lấy mẫu. Nó không ghi một event cho mỗi object được cấp phát. JFR giới hạn tần suất event để giữ overhead thấp; do đó, recording có thể chứa ít event hơn rất nhiều so với số object ứng dụng thực sự tạo ra.

Có thể phân biệt:

| Đặc điểm | ObjectAllocationSample | Event allocation chi tiết kiểu TLAB |
| --- | --- | --- |
| Mục đích | Ước lượng áp lực cấp phát bằng sampling | Ghi chi tiết một số hoạt động cấp phát |
| Số event | Một phần mẫu, có giới hạn tần suất | Có thể phát sinh nhiều event hơn |
| Thông tin chính | Class, weight, thread, stack trace | Class, kích thước cấp phát và thông tin TLAB tùy event |
| Overhead | Thấp hơn, phù hợp profiling thường xuyên | Cao hơn, cần cân nhắc khi bật |
| Cách sử dụng | Tìm class và call site có áp lực cấp phát cao | Điều tra chi tiết khi có lý do cụ thể |

Sampling không cho biết chính xác tổng số object đã được tạo. Nó giúp xác định xu hướng và vị trí đáng điều tra. Các mẫu ít hoặc recording quá ngắn có thể chưa đại diện cho workload; hãy ghi trong khoảng thời gian đủ dài và chạy workload gần với thực tế.

Cũng cần phân biệt **allocation pressure** với **memory leak**:

- Allocation pressure cao có nghĩa ứng dụng tạo object với tốc độ hoặc khối lượng lớn.
- Memory leak là tình trạng object không còn cần thiết vẫn được giữ tham chiếu, khiến bộ nhớ không được giải phóng như mong muốn.

Một ứng dụng có thể tạo nhiều object tạm thời nhưng không bị leak. Ngược lại, một số ít object bị giữ lại lâu dài cũng có thể gây leak. **ObjectAllocationSample** chủ yếu giúp tìm nơi tạo object; khi nghi ngờ leak, cần xem thêm dữ liệu về object tồn tại lâu, GC root hoặc heap dump.

## 4. Ghi JFR recording để theo dõi allocation

JFR được tích hợp trong JVM. Có thể bắt đầu recording khi khởi chạy ứng dụng hoặc kết nối vào một JVM đang chạy.

### Ghi recording khi khởi động ứng dụng

Dùng tùy chọn **-XX:StartFlightRecording**:

~~~bash
java -XX:StartFlightRecording=filename=allocation.jfr,settings=profile,duration=2m -jar app.jar
~~~

Trong ví dụ:

- **filename=allocation.jfr** đặt tên file recording.
- **settings=profile** dùng cấu hình thu thập nhiều dữ liệu hơn để profiling.
- **duration=2m** giới hạn recording trong hai phút.

Khi recording kết thúc, JFR ghi dữ liệu ra file **allocation.jfr**. Cấu hình **profile** phù hợp cho một phiên điều tra ngắn; nó có thể có overhead cao hơn cấu hình **default**.

Nếu cần ghi liên tục trong môi trường production, hãy cân nhắc **settings=default**. Cấu hình này được thiết kế cho recording liên tục với overhead thấp. Không nên mặc định dùng cấu hình profile trong thời gian dài nếu chưa đánh giá tác động tới ứng dụng.

### Ghi recording trên JVM đang chạy

Có thể dùng **jcmd** để bắt đầu recording mà không cần khởi động lại ứng dụng:

~~~bash
jcmd <pid> JFR.start name=AllocationProfile settings=profile duration=2m filename=allocation.jfr
~~~

Thay **<pid>** bằng process ID của JVM cần kiểm tra. Có thể xem recording đang chạy:

~~~bash
jcmd <pid> JFR.check
~~~

Nếu cần kiểm soát recording bằng các lệnh riêng, JFR cung cấp **JFR.start**, **JFR.check**, **JFR.dump** và **JFR.stop**. Hãy xem trợ giúp của đúng JDK đang chạy bằng **jcmd <pid> help JFR.start** hoặc **jcmd <pid> help JFR.dump**, vì tùy chọn và cú pháp chi tiết có thể khác theo phiên bản.

Việc điều khiển recording bằng **jcmd** cần quyền truy cập phù hợp tới tiến trình JVM. Trong môi trường container hoặc production, cũng cần bảo đảm công cụ chẩn đoán có thể nhìn thấy đúng process và có quyền attach.

## 5. Đọc recording bằng công cụ jfr

Sau khi có file **allocation.jfr**, dùng lệnh **jfr** đi kèm JDK để xem thông tin.

### Xem tổng quan recording

~~~bash
jfr summary allocation.jfr
~~~

Lệnh này hiển thị số lượng event, thời gian recording và thống kê tổng quan. Trước khi phân tích sâu, hãy kiểm tra file có dữ liệu và thời lượng recording có đủ để đại diện cho workload hay không.

### Chỉ in ObjectAllocationSample

~~~bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 20 allocation.jfr
~~~

Trong đó:

- **--events jdk.ObjectAllocationSample** lọc đúng event cần xem.
- **--stack-depth 20** yêu cầu hiển thị tối đa 20 frame của stack trace.

Kết quả giúp xem class được chọn mẫu, weight, thread và vị trí trong call stack. Stack trace mặc định của lệnh **jfr print** có thể bị giới hạn độ sâu; tăng độ sâu khi cần tìm caller phía trên, nhưng cũng làm output dài hơn.

### Kiểm tra metadata của event

~~~bash
jfr metadata --events jdk.ObjectAllocationSample allocation.jfr
~~~

Lệnh này cho biết event có những field nào trong recording. Đây là cách hữu ích khi phân tích file được tạo từ JDK khác hoặc khi metadata event thay đổi giữa các phiên bản.

### Phân tích bằng JDK Mission Control

JDK Mission Control (JMC) mở file **.jfr** và trình bày dữ liệu qua các bảng, biểu đồ và nhóm phân tích. Khi điều tra allocation, hãy mở các khu vực liên quan tới Memory hoặc allocation sites, sau đó xem:

- Class nào có tổng weight lớn.
- Stack trace nào lặp lại nhiều và có trọng số cao.
- Thread nào tạo ra nhiều allocation.
- Allocation tăng ở thời điểm nào trong recording.
- Các call site có tương quan với hoạt động GC hoặc độ trễ ứng dụng hay không.

JMC giúp lọc và nhóm dữ liệu thuận tiện hơn so với đọc toàn bộ event dạng văn bản. Hãy dùng phiên bản JMC hỗ trợ event **jdk.ObjectAllocationSample** và tương thích với JDK recording đang phân tích.

## 6. Quy trình tìm nguồn cấp phát object nhiều

Có thể thực hiện theo trình tự sau:

1. **Tạo workload đại diện:** chọn luồng xử lý, endpoint hoặc tác vụ đang có dấu hiệu tạo nhiều object.
2. **Ghi recording:** bắt đầu JFR với **profile** trong khoảng thời gian ngắn, đủ bao phủ workload.
3. **Xác nhận dữ liệu:** chạy **jfr summary** để kiểm tra recording và lọc event bằng **jfr print**.
4. **Xếp hạng class:** tổng hợp weight theo **objectClass** để xác định nhóm object có áp lực cấp phát lớn.
5. **Tìm call site:** xem stack trace của các mẫu có weight cao và lặp lại để xác định phương thức tạo object.
6. **Đối chiếu thread và thời gian:** xác định allocation đến từ worker, request handler, scheduler hay tác vụ nền.
7. **Kiểm tra code:** xem có chuyển đổi dữ liệu lặp lại, tạo chuỗi tạm, boxing không cần thiết, sao chép collection hoặc cấp phát buffer trong vòng lặp hay không.
8. **Thay đổi có mục tiêu:** chỉ tối ưu vị trí có bằng chứng từ recording; tránh thêm object pool hoặc cache khi chưa có lý do.
9. **Ghi recording lại:** chạy cùng workload và so sánh weight theo class/call site, tốc độ GC và độ trễ trước, sau thay đổi.

Ví dụ, recording cho thấy **byte[]** có weight cao và stack trace thường đi qua một hàm đọc file. Hãy kiểm tra hàm đó có đang tạo buffer mới cho từng lần đọc hay chuyển đổi dữ liệu nhiều lần không. Nếu **String** xuất hiện với weight cao trong stack trace của một formatter, hãy kiểm tra việc ghép chuỗi hoặc chuẩn hóa chuỗi có bị lặp trong vòng lặp không.

Đừng tối ưu chỉ vì một class xuất hiện nhiều mẫu. Một class có thể được cấp phát nhiều nhưng vẫn cần thiết và không phải nút thắt. Hãy đối chiếu với throughput, latency, GC và mục tiêu nghiệp vụ.

## 7. Điều chỉnh cấu hình allocation sampling

JFR cung cấp hai cấu hình có sẵn:

| Cấu hình | Mục tiêu | AllocationSample trong cấu hình JDK hiện hành |
| --- | --- | --- |
| **default.jfc** | Recording liên tục, overhead thấp | Bật, giới hạn khoảng 150 event/giây |
| **profile.jfc** | Profiling ngắn, nhiều dữ liệu hơn | Bật, giới hạn khoảng 300 event/giây |

Các mức 150 và 300 event/giây là giới hạn tần suất trong cấu hình tiêu chuẩn, không phải số object được tạo ra mỗi giây và cũng không phải tần suất cố định mà ứng dụng bắt buộc phải đạt.

Nếu cần tùy chỉnh event, JDK hiện đại cung cấp lệnh **jfr configure** để tạo file cấu hình mới. Ví dụ:

~~~bash
jfr configure --input profile.jfc --output allocation.jfc jdk.ObjectAllocationSample#enabled=true jdk.ObjectAllocationSample#stackTrace=true
~~~

Sau đó dùng file **allocation.jfc** khi khởi động recording:

~~~bash
java -XX:StartFlightRecording=filename=allocation.jfr,settings=allocation.jfc,duration=2m -jar app.jar
~~~

Nên tạo cấu hình riêng từ template có sẵn thay vì chỉnh sửa trực tiếp **default.jfc** hoặc **profile.jfc** trong thư mục JDK. Khi thay đổi throttle hoặc bật thêm event allocation chi tiết, cần đo overhead trên workload đại diện và chỉ tăng mức thu thập khi thông tin bổ sung thực sự cần thiết.

## 8. Những giới hạn cần nhớ khi đọc kết quả

- **Weight là trọng số thống kê:** không phải kích thước chính xác của object được lấy mẫu hoặc số byte chính xác của từng lần cấp phát.
- **Event không ghi mọi allocation:** không dùng số event để đếm tổng số object.
- **Recording ngắn có thể thiếu đại diện:** các call site hiếm hoặc workload không xuất hiện trong khoảng ghi sẽ không được thể hiện đầy đủ.
- **Stack trace cần được bật:** nếu không thu thập stack trace, khả năng truy ngược call site sẽ bị hạn chế.
- **Sampling có overhead:** JFR được thiết kế để overhead thấp, nhưng không có nghĩa là bằng không. Cấu hình profile và việc bật thêm event có thể tăng chi phí.
- **Allocation không đồng nghĩa leak:** event này cho biết nguồn tạo object; cần công cụ và dữ liệu khác để xác định object có bị giữ lại quá lâu hay không.
- **So sánh phải cùng điều kiện:** dùng workload, thời lượng, cấu hình JFR và môi trường tương đương khi đánh giá trước và sau tối ưu.

Kết quả JFR là dữ liệu quan sát runtime. Hãy kết hợp nó với số liệu GC, heap usage, latency và throughput để hiểu tác động thực tế thay vì chỉ nhìn một event riêng lẻ.

## 9. Kết luận

**jdk.ObjectAllocationSample** được bổ sung trong Java 16 để hỗ trợ allocation profiling với overhead thấp. Event ghi lại class của object được lấy mẫu, trọng số **weight**, thread và stack trace. Tổng hợp weight theo class hoặc call site giúp xác định khu vực tạo nhiều object và gây áp lực cấp phát.

Trong Java hiện đại, hãy dùng **default.jfc** cho recording liên tục và **profile.jfc** cho phiên profiling ngắn. Dùng **jcmd** hoặc **-XX:StartFlightRecording** để ghi dữ liệu, sau đó phân tích bằng **jfr** hoặc JDK Mission Control. Đọc weight như một ước lượng thống kê, tìm call site có ảnh hưởng lớn và đo lại dưới workload tương đương sau khi tối ưu.

## Tài liệu tham khảo

- [JDK 16 Release Notes — New jdk.ObjectAllocationSample Event Enabled by Default](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [JDK 27 Diagnostic Tools — Flight Recorder](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [JDK 27 Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/27/jfapi/flight-recorder-configurations.html)
- [The jfr Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [OpenJDK JFR Event Metadata — ObjectAllocationSample](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml)

