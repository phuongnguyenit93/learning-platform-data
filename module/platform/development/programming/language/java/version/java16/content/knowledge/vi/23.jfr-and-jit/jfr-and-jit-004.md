# Dump, kết thúc và kiểm tra nội dung bản ghi bằng công cụ JFR

Sau khi JFR đã ghi dữ liệu, cần đưa recording ra file, xác định khoảng thời gian cần phân tích và kiểm tra file trước khi mở bằng công cụ phân tích. Hai lệnh **JFR.dump** và **JFR.stop** có mục đích khác nhau: dump tạo một bản ghi từ dữ liệu hiện có nhưng giữ recording tiếp tục chạy; stop kết thúc recording và cần chỉ định file đầu ra nếu muốn giữ dữ liệu.

Sau khi có file **.jfr**, có thể dùng **jfr summary**, **jfr metadata**, **jfr print** hoặc JDK Mission Control (JMC) để kiểm tra event và phân tích hoạt động của JVM. Bài học này tập trung vào vòng đời dump, lưu file và xác minh nội dung, dựa trên các công cụ vẫn được hỗ trợ trong Java hiện đại.

## 1. Phân biệt dump và stop

Một recording đang chạy có thể được xử lý theo hai cách:

- **JFR.dump:** sao chép dữ liệu đã thu thập tới file tại thời điểm gọi lệnh. Recording vẫn tiếp tục chạy.
- **JFR.stop:** kết thúc recording. Nếu cần giữ dữ liệu, phải chỉ định **filename** để JVM ghi nội dung ra file.

Ví dụ, ứng dụng đang ghi recording tên **ApiIncident**:

~~~bash
jcmd 12345 JFR.dump name=ApiIncident filename=recordings/api-incident-snapshot.jfr
~~~

Sau lệnh này, file snapshot chứa dữ liệu được chọn tại thời điểm dump; recording **ApiIncident** vẫn hoạt động. Có thể tiếp tục quan sát ứng dụng rồi dump thêm một snapshot khác.

Khi đã thu thập đủ dữ liệu:

~~~bash
jcmd 12345 JFR.stop name=ApiIncident filename=recordings/api-incident-final.jfr
~~~

Lệnh này dừng recording và ghi phần dữ liệu còn lại vào file cuối cùng. Hai file snapshot và final có thể chứa các khoảng thời gian chồng lấn, vì vậy cần xem timestamp bên trong khi tổng hợp kết quả.

| Lệnh | Mục đích | Recording sau lệnh |
| --- | --- | --- |
| **JFR.dump** | Lưu một bản ghi từ dữ liệu hiện có | Tiếp tục chạy |
| **JFR.stop** | Kết thúc recording và lưu dữ liệu nếu có filename | Đã dừng |
| **JFR.check** | Xem trạng thái recording | Tiếp tục chạy |

Đây là khác biệt quan trọng khi điều tra sự cố đang diễn ra: dump để lấy bằng chứng ngay mà không ngắt recording; stop khi không cần thu thập thêm.

## 2. Dump toàn bộ hoặc chỉ một khoảng thời gian

Mặc định, **JFR.dump** ghi dữ liệu của recording được chọn vào file. Có thể chỉ định **begin** và **end** để giới hạn khoảng thời gian.

Ví dụ, dump dữ liệu từ 15 phút trước tới hiện tại:

~~~bash
jcmd 12345 JFR.dump name=ApiIncident begin=-15m filename=recordings/api-incident-last-15m.jfr
~~~

Có thể chọn một khoảng cụ thể bằng timestamp:

~~~bash
jcmd 12345 JFR.dump name=ApiIncident begin=2026-11-27T09:00:00 end=2026-11-27T09:10:00 filename=recordings/api-incident-window.jfr
~~~

Các giá trị **begin** và **end** được phân tích theo định dạng mà **LocalTime.parse()**, **LocalDateTime.parse()** hoặc **Instant.parse()** chấp nhận. Có thể dùng thời gian tương đối như **-30s**, **-15m** hoặc **-12h**. Timestamp phải tương ứng với thời gian của event trong recording.

Một số tùy chọn hữu ích:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| **name** | Chọn recording cần dump; nếu bỏ qua, dữ liệu từ tất cả recording đang chạy có thể được dump |
| **filename** | File nhận dữ liệu; nếu bỏ qua, JFR tạo tên file dựa trên PID và ngày hiện tại |
| **begin** | Thời điểm bắt đầu của khoảng dữ liệu cần dump |
| **end** | Thời điểm kết thúc của khoảng dữ liệu cần dump |
| **maxage** | Giới hạn độ dài thời gian dữ liệu được ghi ra file |
| **maxsize** | Giới hạn kích thước dữ liệu được ghi ra file |
| **path-to-gc-root** | Thu thập đường dẫn tới GC root tại thời điểm dump |

Để tránh dump nhầm recording hoặc khó tìm file, nên chỉ định rõ cả **name** và **filename** trong các lệnh vận hành.

### Lưu ý về path-to-gc-root

**path-to-gc-root=true** yêu cầu JFR thu thập đường dẫn tham chiếu từ object tới GC root. Thông tin này hữu ích khi điều tra object bị giữ lại và nghi ngờ memory leak. Tuy nhiên, việc thu thập có thể làm ứng dụng tạm dừng trong một khoảng ngắn và tốn thời gian hơn.

Chỉ bật tùy chọn này khi có giả thuyết cụ thể về memory leak. Với điều tra CPU, latency hoặc allocation thông thường, không cần thu thập đường dẫn GC root.

## 3. Dừng recording và tránh mất dữ liệu

Lệnh **JFR.stop** có tùy chọn **filename**:

~~~bash
jcmd 12345 JFR.stop name=ApiIncident filename=recordings/api-incident-final.jfr
~~~

Nếu không truyền **filename**, dữ liệu recording bị loại bỏ thay vì được ghi thành file. Đây là lỗi vận hành dễ gặp khi chỉ muốn dừng recording sau khi kiểm tra bằng **JFR.check**.

Ví dụ sau dừng recording nhưng không giữ dữ liệu:

~~~bash
jcmd 12345 JFR.stop name=ApiIncident
~~~

Chỉ dùng cách này khi chủ động muốn bỏ recording. Nếu cần phân tích, luôn chỉ định file đầu ra.

Một số quy tắc để lưu an toàn:

1. Đặt đường dẫn file rõ ràng và bảo đảm thư mục đích đã tồn tại.
2. Dùng tên recording nhất quán giữa **JFR.start**, **JFR.dump**, **JFR.check** và **JFR.stop**.
3. Nếu dump snapshot, dùng tên file khác với file cuối để tránh ghi đè bằng chứng trước đó.
4. Kiểm tra dung lượng đĩa trước khi ghi recording lớn.
5. Xác minh file sau khi dump hoặc stop bằng công cụ **jfr**.

Nếu recording được khởi động với **duration**, JVM tự kết thúc recording khi hết thời lượng và lưu theo **filename** đã cấu hình lúc bắt đầu. Nếu dùng recording chạy liên tục, có thể dump snapshot trong lúc điều tra và stop có chủ đích khi kết thúc.

## 4. Kiểm tra trạng thái và xác nhận file đã được tạo

Trước khi dump hoặc stop, kiểm tra recording đang chạy:

~~~bash
jcmd 12345 JFR.check
~~~

Có thể lọc theo tên:

~~~bash
jcmd 12345 JFR.check name=ApiIncident
~~~

Nếu cần xem các event settings của recording:

~~~bash
jcmd 12345 JFR.check name=ApiIncident verbose=true
~~~

Sau khi chạy **JFR.dump** hoặc **JFR.stop**, kiểm tra file có tồn tại và dung lượng lớn hơn 0. Ví dụ trên Linux:

~~~bash
ls -lh recordings/api-incident-final.jfr
~~~

Trên PowerShell:

~~~powershell
Get-Item .\recordings\api-incident-final.jfr | Select-Object Name, Length, LastWriteTime
~~~

Việc file tồn tại và không rỗng mới chỉ là kiểm tra sơ bộ. Một file JFR cần được đọc thành công và có event phù hợp với mục tiêu điều tra. Dùng công cụ **jfr** để kiểm tra nội dung ở các bước tiếp theo.

## 5. Xem tổng quan bằng jfr summary

File **.jfr** được lưu ở định dạng nhị phân. Lệnh **jfr summary** cung cấp thống kê tổng quan:

~~~bash
jfr summary recordings/api-incident-final.jfr
~~~

Kết quả thường cho biết:

- Phiên bản JFR và thời gian recording.
- Thời điểm bắt đầu, thời lượng và kích thước file.
- Số lượng event theo từng loại.
- Các event nào có dữ liệu trong recording.

Đây là bước đầu tiên nên chạy sau khi tạo file. Nếu số event bằng không hoặc thời lượng không khớp với khoảng điều tra, hãy kiểm tra lại recording settings, thời điểm bắt đầu, khoảng **begin/end** và tên file.

Không phải event nào cũng xuất hiện trong mọi recording. Nếu một event không có trong summary, có thể event chưa được bật trong cấu hình, không phát sinh trong khoảng thời gian ghi hoặc không có dữ liệu phù hợp.

## 6. Kiểm tra event và field bằng jfr metadata

**jfr metadata** hiển thị metadata về các event trong file: tên event, category và cấu trúc field.

~~~bash
jfr metadata recordings/api-incident-final.jfr
~~~

Trong JDK 16, lệnh **jfr metadata** nhận file recording và in metadata của các event trong file. Một số JDK mới hơn bổ sung tùy chọn lọc metadata theo event hoặc category; hãy xem **jfr help metadata** của đúng JDK nếu muốn dùng các bộ lọc đó.

Metadata giúp trả lời các câu hỏi:

- Event có tên chính xác là gì?
- Event thuộc category nào?
- Event có những field nào?
- Tên field và kiểu dữ liệu được ghi ra sao?

Cần phân biệt metadata với dữ liệu event thực tế. **jfr metadata** mô tả cấu trúc event; muốn xem giá trị đã được ghi, dùng **jfr print**.

Nếu file được tạo bằng JDK khác với JDK đang dùng để phân tích, hãy truyền file recording cho **jfr metadata** để xem metadata gắn với chính recording đó. Điều này hữu ích khi event tùy chỉnh hoặc schema thay đổi giữa các phiên bản.

## 7. Lọc nội dung bằng jfr print

**jfr print** hiển thị event trong recording dưới dạng văn bản dễ đọc:

~~~bash
jfr print recordings/api-incident-final.jfr
~~~

Một recording production có thể chứa rất nhiều event. Không nên in toàn bộ file ngay từ đầu; hãy lọc theo event hoặc category cần điều tra.

### Lọc theo tên event

Ví dụ chỉ xem event garbage collection và allocation:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.ObjectAllocationSample recordings/api-incident-final.jfr
~~~

Một số event thường được quan tâm:

| Event | Dữ liệu cần xem |
| --- | --- |
| **jdk.GarbageCollection** | Các lần GC và thời lượng |
| **jdk.ObjectAllocationSample** | Mẫu cấp phát object và stack trace |
| **jdk.ExecutionSample** | Mẫu stack của thread đang thực thi |
| **jdk.JavaMonitorEnter** | Thread chờ lấy monitor |
| **jdk.ThreadPark** | Thread bị park hoặc chờ đồng bộ |
| **jdk.SocketRead**, **jdk.SocketWrite** | Hoạt động đọc và ghi socket |

Tên event và mức độ có dữ liệu phụ thuộc cấu hình JFC. Có thể xem tên event có trong recording bằng **jfr summary** hoặc **jfr metadata**.

### Lọc theo category

Có thể lọc event theo category:

~~~bash
jfr print --categories GC recordings/api-incident-final.jfr
~~~

Category giúp xem một nhóm event có cùng mục đích, ví dụ GC, Compiler, Java Application hoặc Thread.

Nếu truyền đồng thời **--categories** và **--events**, kết quả là hợp của hai bộ lọc: event khớp category hoặc khớp tên event sẽ được in. Đây không phải phép giao giữa hai điều kiện.

### Tăng độ sâu stack trace

Mặc định, **jfr print** hiển thị tối đa năm frame của stack trace. Khi cần truy ngược sâu hơn tới caller, có thể tăng **--stack-depth**:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 20 recordings/api-incident-final.jfr
~~~

Tăng độ sâu làm output dài hơn. Hãy chọn mức vừa đủ để xác định call site và đường gọi liên quan.

### Xuất JSON hoặc XML

Nếu muốn xử lý bằng script hoặc công cụ khác, có thể xuất dữ liệu dạng JSON:

~~~bash
jfr print --json --events jdk.GarbageCollection recordings/api-incident-final.jfr
~~~

Hoặc XML:

~~~bash
jfr print --xml --events jdk.GarbageCollection recordings/api-incident-final.jfr
~~~

Dữ liệu dạng JSON/XML hữu ích cho tích hợp tự động, nhưng thường không thuận tiện bằng chế độ văn bản hoặc JMC khi đọc thủ công. Chỉ xuất event cần thiết để tránh output quá lớn.

## 8. Phân tích recording bằng JDK Mission Control

JDK Mission Control (JMC) là công cụ phân tích recording bằng giao diện đồ họa. JMC được phân phối riêng, không phải thành phần luôn có sẵn trong cài đặt JDK tiêu chuẩn.

Mở file **.jfr** trong JMC bằng cách chọn **File > Open File** hoặc mở file từ trình quản lý file. Khi recording được tải, JMC cung cấp trang phân tích tự động và các nhóm dữ liệu theo chủ đề.

Một số khu vực thường dùng:

| Khu vực | Nội dung phân tích |
| --- | --- |
| **Automated Analysis** | Các quy tắc và dấu hiệu hiệu năng cần chú ý |
| **Overview** | Thông tin chung, thời gian và hoạt động chính |
| **Code** | CPU samples, hot methods và stack trace |
| **Memory** | Heap, GC, allocation và object |
| **Threads** | CPU theo thread, thread state, contention và latency |
| **Locks** | Monitor contention và thời gian chờ khóa |
| **I/O** | File, socket và hoạt động I/O |
| **Events** | Danh sách event, bộ lọc và chi tiết từng event |

Có thể chọn một khoảng thời gian trên timeline để tập trung phân tích giai đoạn xảy ra sự cố. Ví dụ, nếu latency tăng từ 10:05 tới 10:07, hãy khoanh vùng khoảng đó rồi đối chiếu CPU, GC, thread contention và I/O.

JMC hỗ trợ xem stack trace và drill down từ bảng tổng hợp xuống từng event. Đây là cách hiệu quả để kết nối dấu hiệu hiệu năng với phương thức hoặc thread cụ thể.

## 9. Quy trình xác minh và phân tích một file JFR

Sau khi dump hoặc stop recording, có thể thực hiện quy trình sau:

**Bước 1 — Xác nhận file**

~~~bash
jfr summary recordings/api-incident-final.jfr
~~~

Kiểm tra file đọc được, có thời lượng và số event phù hợp.

**Bước 2 — Xem event metadata**

~~~bash
jfr metadata recordings/api-incident-final.jfr
~~~

Xác định tên event, category và field cần đọc.

**Bước 3 — Lọc event liên quan**

~~~bash
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample,jdk.JavaMonitorEnter recordings/api-incident-final.jfr
~~~

Chỉ lấy nhóm event liên quan tới giả thuyết điều tra.

**Bước 4 — Mở trong JMC**

Mở file và dùng Automated Analysis cùng các khu vực Code, Memory, Threads, Locks hoặc I/O để xác định dấu hiệu nổi bật.

**Bước 5 — Đối chiếu với workload**

So sánh timestamp trong recording với thời điểm request hoặc tác vụ có vấn đề. Kiểm tra thread, stack trace, GC pause, allocation và I/O ở cùng khoảng thời gian.

**Bước 6 — Ghi lại kết luận và giới hạn**

Ghi rõ event nào hỗ trợ kết luận, khoảng thời gian quan sát, cấu hình JFR và những dữ liệu không được thu thập. Không kết luận rằng ứng dụng không có vấn đề chỉ vì một event không xuất hiện trong recording.

## 10. Xử lý recording bị thiếu hoặc khó đọc

Một số tình huống thường gặp:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có file sau khi stop | **JFR.stop** không có **filename** | Chạy stop với file đầu ra; kiểm tra thư mục đích |
| File tồn tại nhưng không có event cần tìm | Event chưa bật hoặc không phát sinh | Kiểm tra JFC settings, summary và metadata |
| File chỉ chứa một phần khoảng thời gian | **begin/end**, **maxage** hoặc **maxsize** giới hạn dữ liệu | Kiểm tra tham số dump và recording repository |
| Output quá dài | In toàn bộ event hoặc stack trace quá sâu | Lọc bằng **--events**, **--categories** và giới hạn **--stack-depth** |
| Không hiểu field của event | Chưa xem metadata | Dùng **jfr metadata** trên chính file |
| JMC không mở được file | File chưa hoàn chỉnh, hỏng hoặc JMC không tương thích | Kiểm tra bằng **jfr summary**, dùng JMC/JDK tương thích và xác minh file |
| File quá lớn để chuyển đi | Recording dài hoặc nhiều event | Chỉ dump khoảng thời gian cần thiết; cân nhắc tách chunk khi phù hợp |

JFR lưu dữ liệu theo các chunk. Nếu JVM kết thúc bất thường và còn repository chunk có thể phục hồi, công cụ **jfr assemble** có thể ghép các chunk hoàn chỉnh thành recording:

~~~bash
jfr assemble /path/to/jfr-repository recordings/recovered.jfr
~~~

Chỉ dùng khi có repository chunk phù hợp và cần phục hồi recording. Không phải mọi file hỏng đều có thể khôi phục. Lệnh **jfr disassemble** có thể tách recording thành các chunk khi cần thao tác hoặc chuyển file theo từng phần, nhưng không phải bước cần thiết trong quy trình phân tích thông thường.

## 11. Bảo vệ dữ liệu trong recording

JFR recording có thể chứa tên thread, tên class, stack trace, đường dẫn file, tham số runtime và dữ liệu từ custom event do ứng dụng tự ghi. Vì vậy:

- Lưu file trong thư mục có quyền truy cập phù hợp.
- Không đưa recording production lên nơi công khai khi chưa kiểm tra nội dung.
- Chỉ chia sẻ event và khoảng thời gian cần thiết.
- Khi cần trao đổi file, dùng kênh truyền được tổ chức cho phép và giới hạn người nhận.

Nếu cần tạo bản chia sẻ đã lọc, hãy thực hiện trên một bản sao và kiểm tra lại file đầu ra. Đừng thay đổi hoặc loại bỏ dữ liệu gốc trước khi xác nhận bản phân tích đã hoàn tất.

## 12. Kết luận

**JFR.dump** tạo snapshot mà không dừng recording; **JFR.stop** kết thúc recording và cần có **filename** nếu muốn giữ dữ liệu. Có thể giới hạn khoảng dump bằng **begin/end**, thời lượng bằng **maxage** hoặc dung lượng bằng **maxsize**. Với dữ liệu nghi ngờ memory leak, **path-to-gc-root** có thể cung cấp thêm thông tin nhưng có thể gây pause ngắn.

Sau khi tạo file, hãy kiểm tra theo thứ tự **jfr summary**, **jfr metadata**, **jfr print**, rồi mở bằng JDK Mission Control khi cần phân tích trực quan. Xác minh timestamp, event count, stack trace và khoảng workload trước khi kết luận. Quy trình này giúp recording trở thành bằng chứng có thể kiểm tra và sử dụng để tìm nguyên nhân sự cố trong Java hiện đại.

## Tài liệu tham khảo

- [The jcmd Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jcmd.html)
- [The jfr Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jfr.html)
- [The jfr Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [Diagnostic Tools — Java SE 27](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [JDK Mission Control User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html)
- [Using JDK Flight Recorder — JDK Mission Control 9](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)

