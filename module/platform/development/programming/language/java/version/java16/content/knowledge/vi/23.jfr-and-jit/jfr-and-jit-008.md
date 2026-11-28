# Kiểm tra overhead và giới hạn suy diễn từ dữ liệu lấy mẫu

Java Flight Recorder (JFR) được thiết kế để thu thập thông tin runtime với chi phí thấp, nhưng recording vẫn có thể ảnh hưởng tới CPU, bộ nhớ, I/O và thời gian phản hồi. Mức ảnh hưởng phụ thuộc ứng dụng, cấu hình event và thời gian ghi. Đồng thời, dữ liệu lấy mẫu chỉ phản ánh một phần hoạt động; nó hữu ích để nhận diện xu hướng nhưng không phải bản ghi đầy đủ của mọi lần cấp phát hay mọi lần thực thi.

Khi dùng JFR để đánh giá hiệu năng, cần kiểm tra cả hai mặt: overhead do công cụ tạo ra và giới hạn của dữ liệu thu thập. Bài học này giải thích các yếu tố làm tăng overhead, cách so sánh recording bật/tắt trong điều kiện tương đương và những kết luận không nên rút ra chỉ từ sample count, weight hoặc stack trace.

## 1. Vì sao công cụ profiling cũng có thể ảnh hưởng tới ứng dụng?

Một công cụ profiling phải quan sát hoạt động của JVM. Để ghi dữ liệu, JVM cần tạo event, lấy timestamp, thu thập field, có thể chụp stack trace, đưa dữ liệu vào buffer và ghi buffer ra file.

Các thao tác này tiêu tốn tài nguyên. Mức overhead phụ thuộc vào:

- Số loại event được bật.
- Tần suất event xuất hiện.
- Có thu stack trace hay không và độ sâu stack trace.
- Ngưỡng thời lượng của duration event.
- Tần suất flush buffer và ghi dữ liệu ra đĩa.
- Các event cần thu thập thông tin bổ sung từ heap hoặc runtime.
- Tải CPU, số thread và đặc điểm workload của ứng dụng.

Một recording nhẹ có thể gần như không ảnh hưởng tới ứng dụng. Một recording bật nhiều event chi tiết, tần suất cao hoặc thu thập heap statistics có thể làm tăng overhead rõ rệt.

Vì vậy, kết quả đo trong lúc bật JFR cần được hiểu là kết quả của ứng dụng trong điều kiện có instrumentation. Trước khi dùng nó để kết luận về hiệu năng production, hãy xác minh mức ảnh hưởng bằng workload đại diện.

## 2. default.jfc và profile.jfc có mức chi tiết khác nhau

JDK cung cấp hai cấu hình JFR tiêu chuẩn trong thư mục **JAVA_HOME/lib/jfr**:

| Cấu hình | Mục tiêu | Đặc điểm |
| --- | --- | --- |
| **default.jfc** | Recording liên tục, giám sát dài hạn | Thu thập nhóm event nền tảng với overhead thấp |
| **profile.jfc** | Điều tra hiệu năng trong khoảng thời gian giới hạn | Thu thập nhiều event và dữ liệu chi tiết hơn, có thể ảnh hưởng hiệu năng nhiều hơn |

Tài liệu JDK hiện hành mô tả **default.jfc** phù hợp với continuous recording và thường có overhead dưới 1% trong cấu hình chuẩn. Tài liệu troubleshooting cũng mô tả một recording profiling tiêu chuẩn có overhead dưới 2% đối với phần lớn ứng dụng. Đây là số liệu tham khảo của cấu hình và workload tiêu chuẩn, không phải cam kết cho mọi ứng dụng hoặc mọi môi trường.

Một service có nhiều thread, event tần suất cao hoặc I/O rất nhạy với latency có thể có mức ảnh hưởng khác. Container có CPU quota thấp cũng có thể thể hiện overhead rõ hơn khi CPU đã gần bão hòa.

Nguyên tắc chọn cấu hình:

- Dùng **default** làm điểm bắt đầu cho recording liên tục.
- Dùng **profile** trong một phiên điều tra có mục tiêu và thời lượng phù hợp.
- Không bật mọi event chỉ vì muốn có càng nhiều dữ liệu càng tốt.
- Khi cần thêm dữ liệu, bật đúng event đang thiếu và đo lại overhead.
- Tạo bản sao cấu hình JFC riêng thay vì sửa trực tiếp file mẫu trong JDK.

Ví dụ recording liên tục với cấu hình nhẹ:

~~~bash
java -XX:StartFlightRecording=filename=default.jfr,settings=default,dumponexit=true -jar app.jar
~~~

Ví dụ profiling trong khoảng thời gian giới hạn:

~~~bash
java -XX:StartFlightRecording=filename=profile.jfr,settings=profile,duration=5m -jar app.jar
~~~

Không nên dùng kết quả của một recording **profile** để đại diện cho hiệu năng của ứng dụng khi không bật profiling mà không kiểm tra overhead.

## 3. Những thành phần recording thường làm tăng overhead

### Event có tần suất cao

Event phát sinh thường xuyên làm JVM phải tạo và ghi nhiều dữ liệu hơn. Ví dụ, event ghi nhận một hoạt động nhỏ mỗi lần lặp trong một vòng lặp nóng có thể tạo lượng dữ liệu rất lớn.

Trước khi bật event, hãy xác định câu hỏi cần trả lời. Nếu chỉ cần biết allocation hot spot, **jdk.ObjectAllocationSample** có thể hữu ích hơn việc bật nhiều event allocation chi tiết cùng lúc.

### Stack trace

Stack trace giúp truy ngược call site, nhưng thu thập stack trace cũng có chi phí. Bật stack trace cho quá nhiều event tần suất cao có thể làm tăng CPU và kích thước recording.

Chỉ bật stack trace cho các event cần xác định nguồn phát sinh. Nếu event đã cho biết thông tin cần thiết qua field, không nhất thiết phải thu thêm stack trace.

### Duration threshold

Nhiều Java Application duration event trong cấu hình tiêu chuẩn chỉ ghi các hoạt động dài hơn một ngưỡng nhất định; tài liệu troubleshooting của Oracle nêu ngưỡng thường gặp là 20 ms và có thể điều chỉnh. Ngưỡng này giúp giảm số event ngắn và giảm overhead, nhưng đồng thời làm các thao tác ngắn hơn ngưỡng không xuất hiện trong recording.

Ví dụ, nếu một lần chờ monitor chỉ kéo dài 2 ms trong khi ngưỡng đang là 20 ms, event tương ứng có thể không được ghi. Không thể kết luận rằng ứng dụng không có contention chỉ vì recording không hiển thị event chờ ngắn.

### Ghi dữ liệu ra đĩa

JFR sử dụng buffer để thu thập event và ghi dữ liệu theo từng phần. Ghi quá nhiều dữ liệu hoặc lưu file trên storage chậm có thể làm tăng I/O và dung lượng recording.

Với continuous recording, dùng cấu hình nhẹ và giới hạn dung lượng/thời gian lưu khi cần. Tránh bật event chi tiết trong thời gian dài nếu chưa có đánh giá tác động.

### Heap Statistics

Heap Statistics có thể gây overhead đáng kể. Theo tài liệu Oracle, bật tính năng này có thể kích hoạt một old/full garbage collection ở đầu và cuối quá trình thu thập, làm phát sinh pause ngoài hoạt động thông thường của ứng dụng.

Do đó:

- Không bật Heap Statistics trong phép đo latency hoặc benchmark hiệu năng thông thường.
- Chỉ dùng khi cần điều tra live set hoặc memory leak.
- Nếu bật, phải ghi rõ rằng recording có thể làm thay đổi hành vi GC.
- Không so sánh trực tiếp pause time của lần chạy có Heap Statistics với baseline không bật tính năng này mà không tính tới tác động của nó.

## 4. Allocation sample không phải bản ghi đầy đủ mọi allocation

Event **jdk.ObjectAllocationSample** lấy mẫu hoạt động cấp phát và cung cấp **objectClass**, **weight**, thread và stack trace. Nó không tạo một event cho mọi object được cấp phát.

Cần phân biệt:

- **Sample count:** số event sample được ghi.
- **Weight:** trọng số tương đối của mẫu, dùng để ước lượng allocation pressure.
- **Allocation count thực tế:** tổng số object được tạo, không thể suy ra trực tiếp bằng cách đếm sample.
- **Object size:** kích thước của một object cụ thể, không thể coi weight là kích thước chính xác của object trong event.

Khi tổng hợp weight qua đủ nhiều mẫu, theo class, thread hoặc stack trace, kết quả có thể tạo ra một ước lượng thống kê hữu ích về allocation pressure. Tuy nhiên, một recording ngắn hoặc workload ít mẫu có thể chưa đủ đại diện.

Ví dụ:

| Class | Sample count | Tổng weight |
| --- | ---: | ---: |
| **byte[]** | 30 | 420 MB |
| **String** | 75 | 260 MB |
| **OrderDto** | 18 | 110 MB |

Bảng này chỉ minh họa cách diễn giải. Không thể kết luận rằng ứng dụng tạo chính xác 30 mảng byte hoặc tổng kích thước các object byte array là đúng 420 MB. Weight là đại lượng ước lượng được đại diện bởi các sample.

Một class có sample count thấp vẫn có thể có tổng weight cao. Vì vậy, khi xếp hạng allocation hot spot, hãy xem cả count và weight; dùng weight để ước lượng áp lực cấp phát và stack trace để tìm call site.

## 5. Giới hạn của stack trace và method sampling

Stack trace cho biết đường gọi được ghi nhận tại thời điểm event. Nó giúp tìm nơi phát sinh hoạt động, nhưng không phải lúc nào cũng thể hiện toàn bộ bối cảnh nghiệp vụ.

Một số giới hạn:

- Stack trace có thể bị giới hạn độ sâu.
- Một recording có thể không bật stack trace cho event đang quan tâm.
- Một call site hiếm có thể không xuất hiện trong khoảng thời gian ngắn.
- Một frame thư viện có thể là nơi cấp phát trực tiếp, còn frame ứng dụng phía trên mới cho biết nghiệp vụ kích hoạt nó.
- Tên class nội bộ của JDK hoặc Stream implementation có thể thay đổi giữa các phiên bản.

Đối với **jdk.ExecutionSample**, JFR lấy mẫu thread đang thực thi code. Thread đang chờ I/O, sleep, park hoặc monitor thường không được tính như thread đang chạy code trong mẫu thực thi. Vì vậy, số method sample cao thường là dấu hiệu sử dụng CPU nhiều hơn, nhưng không phải phép đo CPU time chính xác cho từng thread.

Khi cần điều tra thread đang chờ, hãy xem duration event phù hợp như **jdk.JavaMonitorEnter**, **jdk.ThreadPark**, **jdk.SocketRead** hoặc **jdk.FileRead**, nếu các event đó được bật và thời lượng vượt ngưỡng cấu hình.

Không dùng method sample để kết luận một thread không hoạt động chỉ vì thread đó không xuất hiện. Thread có thể đang chờ, event có thể không được bật hoặc khoảng recording chưa bao phủ hoạt động đó.

## 6. Workload và thời gian ghi ảnh hưởng tới tính đại diện

Một recording chỉ mô tả những gì xảy ra trong khoảng thời gian được thu thập. Nếu workload không giống tình huống production, kết luận có thể không áp dụng cho production.

Các tình huống dễ làm recording thiếu đại diện:

- Ghi trong lúc ứng dụng ít request nhưng cần kết luận về giờ cao điểm.
- Recording quá ngắn nên không bao phủ batch job hoặc tác vụ định kỳ.
- Chỉ thử một loại request trong khi production có nhiều route và kích thước dữ liệu.
- Không ghi giai đoạn warm-up, khiến JIT compilation và trạng thái cache khác với lúc ứng dụng ổn định.
- Tải request giữa hai lần recording không giống nhau.
- Một sự cố hiếm không xuất hiện trong cửa sổ ghi.

Để tăng tính đại diện:

1. Chọn workload theo đúng vấn đề cần điều tra.
2. Bao phủ các loại request, kích thước input và tỷ lệ lỗi liên quan.
3. Ghi đủ lâu để quan sát các tác vụ định kỳ nếu chúng có liên quan.
4. Phân biệt warm-up với steady state.
5. Lặp lại recording nếu cần kiểm tra một xu hướng.
6. Ghi lại throughput, số request, phiên bản JDK và cấu hình JVM để hiểu điều kiện thử nghiệm.

Một sample không xuất hiện không chứng minh hoạt động đó không xảy ra. Nó có thể không được chọn, không xảy ra trong khoảng ghi hoặc bị loại bởi event settings.

## 7. Đo overhead bằng cách so sánh recording bật và tắt

Không nên áp dụng một tỷ lệ overhead cố định cho mọi ứng dụng. Cách đáng tin cậy hơn là đo trên workload đại diện.

Có thể thiết kế hai nhóm chạy:

| Nhóm | JFR | Mục đích |
| --- | --- | --- |
| Baseline | Tắt recording | Đo hành vi nền của ứng dụng |
| Recording | Bật **default** hoặc **profile** | Đo hành vi khi thu thập dữ liệu |

Giữ các điều kiện còn lại càng giống nhau càng tốt:

- Cùng phiên bản JDK và GC.
- Cùng heap size, CPU quota và cấu hình container.
- Cùng phiên bản ứng dụng và dữ liệu đầu vào.
- Cùng số request hoặc cùng tốc độ phát tải.
- Cùng warm-up và thời gian đo.
- Cùng điều kiện cache, database và dịch vụ phụ thuộc.

Các chỉ số cần so sánh:

| Chỉ số | Điều cần quan sát |
| --- | --- |
| Throughput | Số request hoàn thành mỗi giây |
| p50/p95/p99 | Độ trễ trung vị và phần đuôi |
| CPU usage | CPU của JVM và mức sử dụng CPU tổng |
| GC frequency | Số lần GC trong cùng khoảng thời gian |
| GC pause | Tổng pause và pause dài nhất |
| Allocation rate | Tốc độ cấp phát hoặc weight được chuẩn hóa |
| Recording size | Dung lượng file và tốc độ tăng dữ liệu |

Có thể dùng bảng kết quả minh họa:

| Chỉ số | Baseline | JFR default | JFR profile |
| --- | ---: | ---: | ---: |
| Throughput | 10.000 req/s | 9.980 req/s | 9.850 req/s |
| p95 | 80 ms | 81 ms | 84 ms |
| CPU | 62% | 62,5% | 65% |
| GC pause tổng | 420 ms | 422 ms | 430 ms |

Đây là số liệu giả định để minh họa, không phải benchmark JFR. Khi đo thật, cần lặp lại các lần chạy và xem độ dao động tự nhiên của hệ thống. Chênh lệch nhỏ hơn độ nhiễu giữa các lần chạy chưa đủ để kết luận JFR tạo ra overhead tương ứng.

### Trình tự đo đề xuất

1. Chạy workload baseline nhiều lần để xác định độ dao động bình thường.
2. Chạy cùng workload với **default.jfc**.
3. So sánh throughput, latency, CPU và GC.
4. Nếu cần thêm chi tiết, chạy một phiên riêng với **profile.jfc**.
5. Đo lại và ghi nhận phần overhead tăng thêm so với default.
6. Chỉ bật event chi tiết hoặc Heap Statistics khi câu hỏi điều tra yêu cầu và chấp nhận được tác động.

Không chạy baseline và recording đồng thời trên cùng một máy nếu chúng tranh chấp CPU, heap, database hoặc I/O. Hai tiến trình sẽ làm sai lệch phép so sánh.

## 8. Không nhầm overhead của JFR với biến động tự nhiên

Hiệu năng ứng dụng thay đổi ngay cả khi không bật profiling. Những yếu tố có thể gây nhiễu:

- JIT compilation và deoptimization.
- GC timing và heap occupancy.
- Cache nóng/lạnh.
- Thread scheduling và CPU contention.
- Database query plan hoặc cache phía database.
- Network latency.
- Tải nền trên máy hoặc node container.
- Thay đổi số request và kích thước payload.

Vì vậy, một lần chạy baseline và một lần chạy có JFR chưa đủ để kết luận chính xác. Hãy lặp lại và so sánh phân phối kết quả. Nếu baseline dao động 3% giữa các lần chạy, chênh lệch 0,5% ở một lần recording không phải bằng chứng chắc chắn về overhead.

Trong benchmark micro, dùng JMH để kiểm soát warm-up, fork và iteration. Nếu muốn đo overhead của JFR, có thể chạy các fork với cùng benchmark một lần không recording và một lần có recording. Không bật profiler chỉ ở một số benchmark method rồi so sánh các method có workload khác nhau.

## 9. Giới hạn khi suy diễn nguyên nhân từ sample

Một số kết luận thường gặp nhưng không được dữ liệu lấy mẫu bảo đảm:

| Kết luận vội vàng | Vì sao chưa đủ căn cứ | Cần kiểm tra thêm |
| --- | --- | --- |
| Class có nhiều sample nhất là class gây latency | Allocation có thể không nằm trên đường request chậm | Route, thread, request duration và GC pause |
| Weight là số byte chính xác đã cấp phát | Weight là trọng số mẫu | Workload, số mẫu và cách tổng hợp |
| Không có sample nghĩa là không có allocation | Sampling không ghi mọi object | Recording dài hơn, event settings và workload |
| Một stack trace là nguồn duy nhất | Nhiều call site có thể tạo cùng class | Nhóm theo stack trace, thread và thời gian |
| Thread có nhiều ExecutionSample chắc chắn dùng đúng tỷ lệ CPU tương ứng | Sampling không phải phép đo CPU time chính xác | CPU metrics và **jdk.ThreadCPULoad** |
| Allocation cao chứng minh memory leak | Allocation không cho biết object có được giữ lại hay không | Live set, heap dump và GC root |
| GC xuất hiện cùng latency spike chứng minh GC là nguyên nhân | Cả hai có thể cùng bị ảnh hưởng bởi tải | Pause overlap, CPU, lock, I/O và workload |
| Recording không có event chờ nghĩa là không có contention | Duration event có threshold và event settings | Hạ threshold có mục tiêu hoặc xem thread dump/trace |

Đặc biệt, **allocation pressure** và **object retention** là hai vấn đề khác nhau. Allocation sample giúp tìm nơi tạo object. Muốn biết object có bị giữ lại lâu, cần phân tích live object, heap dump, GC root hoặc event phù hợp như **jdk.OldObjectSample** khi được cấu hình.

## 10. Chọn mức thu thập theo câu hỏi điều tra

Không nên dùng cùng một cấu hình cho mọi tình huống. Hãy bắt đầu với câu hỏi:

| Câu hỏi | Hướng thu thập |
| --- | --- |
| Ứng dụng có dấu hiệu CPU bottleneck? | Method/Execution sampling, CPU load và stack trace |
| Class nào tạo nhiều allocation? | **jdk.ObjectAllocationSample**, weight và stack trace |
| Có thread chờ monitor lâu? | **jdk.JavaMonitorEnter** với threshold phù hợp |
| I/O hoặc network có làm request chờ? | **jdk.FileRead**, **jdk.FileWrite**, **jdk.SocketRead**, **jdk.SocketWrite** |
| Có memory leak hoặc live set tăng? | Heap analysis, Heap Statistics khi chấp nhận được overhead, Old Object Sample hoặc heap dump |
| JFR ảnh hưởng hiệu năng bao nhiêu? | So sánh baseline với recording trên workload tương đương |

Khi cần điều tra sâu, tạo một JFC riêng từ template hiện có. Bật đúng event, điều chỉnh threshold có chủ đích và giữ lại cấu hình cùng với kết quả thử nghiệm để có thể tái lập.

## 11. Checklist trước khi kết luận từ JFR

Trước khi đưa ra kết luận kỹ thuật, hãy tự kiểm tra:

- Recording dùng **default** hay **profile**?
- Những event quan trọng có được bật không?
- Stack trace có được ghi và đủ độ sâu không?
- Có duration threshold khiến event ngắn bị bỏ qua không?
- Recording có bao phủ workload và thời điểm xảy ra vấn đề không?
- Số sample đủ để xem xu hướng hay chỉ là vài event đơn lẻ?
- Weight có được diễn giải là ước lượng thay vì object size chính xác không?
- Có so sánh với baseline không bật JFR không?
- Các lần chạy có cùng JDK, heap, CPU quota và input không?
- Có đối chiếu thêm GC, response time, CPU, I/O và thread state không?
- Có nhầm allocation với object retention hoặc correlation với causation không?

Nếu một trong các điều kiện quan trọng chưa đáp ứng, hãy ghi rõ giới hạn trong kết luận và thu thập thêm dữ liệu trước khi thay đổi code hoặc cấu hình JVM.

## 12. Kết luận

JFR được thiết kế để profiling với overhead thấp, nhưng không phải công cụ miễn phí về tài nguyên. **default.jfc** phù hợp với recording liên tục; **profile.jfc** cung cấp nhiều chi tiết hơn và có thể ảnh hưởng hiệu năng rõ hơn. Event tần suất cao, stack trace, ghi đĩa và Heap Statistics là những yếu tố cần cân nhắc khi đánh giá overhead.

Dữ liệu lấy mẫu cũng có giới hạn: sample count không phải allocation count, weight là ước lượng, stack trace không luôn cho toàn bộ bối cảnh và event vắng mặt không chứng minh hoạt động không xảy ra. Hãy đo overhead bằng cách so sánh baseline và recording trên workload tương đương, lặp lại phép đo và đối chiếu JFR với GC, CPU, thread state cùng response time. Kết luận tốt cần nêu rõ bằng chứng, điều kiện đo và giới hạn suy diễn.

## Tài liệu tham khảo

- [Flight Recorder Configurations — Java SE 26](https://docs.oracle.com/en/java/javase/26/jfapi/flight-recorder-configurations.html)
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 25](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Using JDK Flight Recorder — JDK Mission Control 9](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
- [JFR Event Collection for JDK 25 — ObjectAllocationSample](https://sap.github.io/jfrevents/25.html)
- [Configuring the JDK Flight Recorder — dev.java](https://dev.java/learn/jvm/jfr/configure/)
- [JEP 328: Flight Recorder](https://openjdk.org/jeps/328)

