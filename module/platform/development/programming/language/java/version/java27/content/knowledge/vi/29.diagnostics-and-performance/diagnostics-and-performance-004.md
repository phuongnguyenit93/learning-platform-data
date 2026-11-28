# JDK Flight Recorder và Java Mission Control

## 1. Mục tiêu: quan sát hiệu năng bằng bằng chứng, không phỏng đoán

Khi một dịch vụ Java 27 có độ trễ tăng, CPU cao, thời gian thu gom rác dài hoặc nhiều thread chờ nhau, chỉ đọc một vài dòng log thường không đủ để trả lời **đang tốn thời gian ở đâu**. JVM và ứng dụng có nhiều loại hoạt động đồng thời: phương thức Java đang thực thi, cấp phát đối tượng, GC, I/O, chờ khóa, biên dịch JIT và các tác vụ nền.

**JDK Flight Recorder (JFR)** là cơ chế ghi sự kiện chẩn đoán và profiling được tích hợp trong JVM. **Java Mission Control (JMC)** là bộ công cụ đồ họa để mở, trực quan hóa và phân tích các recording, cùng các khả năng quản lý/giám sát JVM.

Các mục tiêu của bài:

1. Hiểu JFR ghi những dữ liệu nào, những gì **không thể kết luận** chỉ từ một recording.
2. Biết tạo, kiểm tra, xuất và dừng recording bằng **jcmd**, khởi động JVM bằng cờ JFR và đọc file bằng **jfr**.
3. Dùng JMC theo một quy trình có kiểm chứng để điều tra CPU, allocation, GC, thread contention và I/O.
4. Viết **custom JFR events** bằng API **jdk.jfr** để đo một thao tác nghiệp vụ.
5. Quản lý overhead, dung lượng đĩa, retention, quyền truy cập và dữ liệu nhạy cảm của recording.
6. Phân biệt **profiling theo sự kiện/mẫu** với benchmark, metric dài hạn và tracing theo request.

Bài thuộc chương **Chẩn đoán và hiệu năng** của chương trình **Java 27 và các kiến thức liên quan**. Các ví dụ dựa trên API/chức năng chính thức còn dùng trong Java 27; không dùng tùy chọn kích hoạt JFR kiểu cũ từ thời các phiên bản thương mại trước đây.

## 2. Bản đồ công cụ: JFR, JMC, jcmd và jfr

~~~mermaid
flowchart LR
    A["Ứng dụng chạy trên JVM"] --> B["JFR: ghi events / samples"]
    C["jcmd JFR.start, JFR.dump, JFR.stop"] --> B
    D["-XX:StartFlightRecording"] --> B
    E["Application jdk.jfr API"] --> B
    B --> F["File .jfr"]
    F --> G["jfr CLI: summary / view / print"]
    F --> H["JMC: timeline, flame/stack views, analysis rules"]
    G --> I["Giả thuyết → kiểm tra → thay đổi → đo lại"]
    H --> I
~~~

| Thành phần | Vị trí | Công dụng chính |
|---|---|---|
| **JFR runtime** | Bên trong JVM hỗ trợ Flight Recorder | Thu thập các event về JVM và ứng dụng |
| **jdk.jfr** | Module JDK | Tạo custom event, điều khiển một recording |
| **jdk.jfr.consumer** | Module JDK | Đọc và xử lý sự kiện đã ghi hoặc stream sự kiện |
| **jcmd** | Công cụ dòng lệnh trong JDK | Gửi lệnh chẩn đoán tới JVM đang chạy |
| **jfr** | Công cụ dòng lệnh trong JDK | Phân tích, lọc, tổng hợp, thao tác file .jfr |
| **JMC** | Ứng dụng công cụ riêng | Xem timeline, sự kiện, stack, các quy tắc phân tích tự động |
| **Metrics/tracing** | Phụ thuộc stack giám sát của ứng dụng | Quan sát xu hướng dài hạn và giao dịch xuyên hệ thống |
| **Benchmark** | Quy trình đo có kiểm soát | So sánh độ trễ/throughput trước và sau thay đổi |

**JMC không đi kèm mặc định trong bộ cài JDK thông thường.** Hãy tải bản JMC tương thích từ nhà phân phối được tin cậy (ví dụ dự án OpenJDK JMC hoặc Oracle JMC). Không nhầm lệnh **jfr** đi kèm JDK với ứng dụng **JMC** phải cài riêng.

## 3. JFR thu thập dữ liệu gì?

JFR biểu diễn hoạt động thành **events**: một sự kiện có thể có thời điểm bắt đầu, thời lượng, thread, stack trace và các trường chuyên biệt.

Một số nhóm phổ biến:

- **Execution samples**: mẫu stack của những thread đang thực thi code.
- **Object allocation samples**: dấu vết về hoạt động cấp phát đối tượng.
- **Garbage collection**: số lần, thời lượng và một số giai đoạn GC.
- **Java monitor / locks**: các lần chờ khóa hoặc contention được ghi nhận.
- **Thread**: trạng thái/hoạt động liên quan thread theo các event được bật.
- **File/socket I/O**: thời gian chờ, số byte và thông tin liên quan đến thao tác I/O.
- **Class loading/JIT**: nạp class và hoạt động của bộ biên dịch.
- **System/JVM settings**: môi trường, cấu hình runtime và một số đặc điểm hệ thống.
- **Custom events**: thao tác nghiệp vụ như xử lý đơn, tính giá hoặc gọi dependency.

**Không phải mọi loại event đều được bật trong mọi recording.** Sự hiện diện của dữ liệu phụ thuộc cấu hình **.jfc**, ngưỡng, lấy mẫu, phiên bản runtime và workload thực sự diễn ra trong khoảng ghi.

Một loại event có thể có **số lần = 0** vì chức năng không phát sinh, vì event bị tắt, vì thời lượng nằm dưới threshold hoặc vì cấu hình/chế độ thu chưa đủ chi tiết. Không kết luận “không có sự cố” chỉ từ việc thiếu một event.

## 4. Event duration, sampling và threshold

Hai cơ chế cần phân biệt:

**Sự kiện theo thời lượng:** Một operation bắt đầu tại thời điểm A và kết thúc tại B; event có thể được ghi khi thời lượng thỏa ngưỡng. Ví dụ một số sự kiện chờ khóa hoặc I/O chậm.

**Sự kiện lấy mẫu:** JVM thu stack/đối tượng theo cơ chế sampling. Các mẫu phản ánh một phân bố được quan sát, **không phải danh sách đầy đủ mọi lời gọi phương thức hoặc mọi lần cấp phát**.

~~~text
Trục thời gian →
  |-- request A --|----- request B -----|-- C --|

Sample execution:  ^      ^      ^
Recorded duration: [          B           ]
~~~

| Chỉ số | Có thể cho biết | Không tự chứng minh |
|---|---|---|
| Số execution samples của method X | X xuất hiện nhiều trong các mẫu được ghi | X dùng chính xác n% tổng thời gian CPU của toàn hệ thống |
| Allocation sample tại dòng Y | Một đường cấp phát đáng chú ý | Mọi object tại Y đều được ghi |
| Duration của monitor enter | Đã có thời gian chờ monitor được đo | Mọi lần chờ đều được thu nếu threshold khác 0 |
| GC pause event | Thời gian dừng liên quan GC | Toàn bộ request latency do GC gây ra |
| File/socket read event | Một thao tác I/O theo cấu hình event | Đủ để giải thích mọi timeout mạng |

**JFR thường có overhead thấp**, nhưng không bằng 0: nếu bật nhiều stack traces, event rate cao hoặc threshold rất nhỏ, chi phí và kích thước recording có thể tăng đáng kể.

## 5. Xác định mục tiêu trước khi ghi

Một recording có giá trị khi gắn với câu hỏi cụ thể và điều kiện tái hiện được.

Ví dụ sự cố:

> API tìm kiếm đang có p99 latency tăng từ mức bình thường lên mức không đạt mục tiêu. CPU JVM khoảng 80%, heap ổn định, nhưng chưa biết nguyên nhân.

Nên thu ít nhất:

1. **Khoảng thời gian có triệu chứng**: thời điểm bắt đầu/kết thúc, timezone và độ dài.
2. **Phiên bản JDK và JVM options** đang chạy.
3. **Workload**: lưu lượng, loại request, số lượng kết quả, tải nền.
4. **Baseline** hoặc khoảng thời gian không có triệu chứng để so sánh.
5. **Recording configuration**: default/profile, event settings và ngưỡng.
6. **Các metrics liên quan**: CPU thực tế, container CPU quota, heap, GC, p95/p99 latency, throughput.
7. **Mức ảnh hưởng vận hành**: thời gian được phép ghi, disk quota, độ nhạy dữ liệu.

**Câu hỏi điều tra phải quyết định cấu hình recording.** Nếu muốn tìm một thao tác I/O dài, cần xác nhận event liên quan I/O đã được bật và threshold phù hợp. Nếu muốn nhận diện hot methods, cần đủ execution samples trong khoảng có tải.

## 6. Kiểm tra JDK và tiến trình cần chẩn đoán

Sử dụng JDK tương thích với JVM mục tiêu và công cụ **jcmd** đi kèm JDK.

~~~bash
java -version
jcmd -l
~~~

**jcmd -l** liệt kê những Java processes mà công cụ quan sát được trong môi trường tương ứng. Thông thường cần chạy trên cùng máy/chế độ attach phù hợp và có quyền người dùng phù hợp với JVM mục tiêu.

Ví dụ PID trong phần này là **12345**, chỉ là placeholder; phải dùng PID thực tế của tiến trình được phép chẩn đoán:

~~~bash
jcmd 12345 help
jcmd 12345 help JFR.start
jcmd 12345 help JFR.dump
~~~

Các lệnh **help** cho đúng tiến trình là cách tốt để kiểm tra tùy chọn được runtime đang chạy hỗ trợ. Không mặc định mọi JDK/vendor/container có cùng tập diagnostic commands.

Lưu ý: truy cập JVM ở production yêu cầu quyền vận hành và có thể làm lộ thông tin cấu hình. Không chạy lệnh attach vào tiến trình không được phép.

## 7. Khởi động recording trên tiến trình đang chạy bằng jcmd

Một recording ngắn để điều tra:

~~~bash
jcmd 12345 JFR.start name=investigation settings=profile duration=120s filename=investigation.jfr
~~~

Ý nghĩa:

- **name=investigation**: tên dùng để tham chiếu recording.
- **settings=profile**: cấu hình dành cho profiling, có thể thu chi tiết hơn **default**.
- **duration=120s**: tự dừng theo thời lượng yêu cầu.
- **filename=investigation.jfr**: file đích khi recording dừng.

Đường dẫn tương đối thường được diễn giải theo môi trường làm việc của **tiến trình JVM mục tiêu**, không nên giả định giống thư mục hiện tại của terminal chạy jcmd. Trong môi trường thực, dùng một đường dẫn tuyệt đối được phép ghi và có đủ dung lượng.

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.check name=investigation verbose=true
~~~

**JFR.check** cho biết recording đang hoạt động và có thể hiện các tùy chọn/event settings. Lệnh **JFR.start** có thể trả ID recording; nếu có nhiều recording đồng thời, nên dùng tên duy nhất hoặc ID tương ứng.

**profile không phải “tốt nhất trong mọi tình huống”**. Khi cần recording dài hạn, bắt đầu với default hoặc cấu hình đã được kiểm chứng về overhead.

## 8. Default và profile: chọn mức chi tiết

JDK thường cung cấp những cấu hình có tên:

| Cấu hình | Mục đích | Hướng dùng |
|---|---|---|
| **default** | Thu thập tổng quát với overhead thấp, hợp hơn cho việc ghi lâu dài | Baseline và continuous recording |
| **profile** | Tăng khả năng nhìn thấy một số dữ liệu phục vụ phân tích sâu | Điều tra có thời hạn và giám sát overhead |
| **.jfc tùy chỉnh** | Định nghĩa chính sách cho các event/settings cụ thể | Workload có câu hỏi chẩn đoán rõ |

Cấu hình được định nghĩa trong file **JFR configuration (.jfc)**, có thể được JDK cung cấp trong **JAVA_HOME/lib/jfr**.

~~~bash
jfr configure --help
~~~

Dùng **jfr configure** để tạo/điều chỉnh cấu hình theo tài liệu của JDK đang sử dụng; tránh sửa tùy tiện file mặc định của JDK trong thư mục cài đặt.

Tùy chọn ghi còn gồm **disk**, **maxage**, **maxsize**, **dumponexit**, **delay**, **duration**. Các tham số này quản lý vòng đời/retention, không thay thế cấu hình event-specific thresholds.

**Cấu hình quyết định tính kết luận.** Ví dụ nếu sampling bị tắt, mở JMC không thể “khôi phục” các execution samples chưa từng được ghi.

## 9. JFR.check, JFR.dump và JFR.stop

Ba thao tác khác nhau:

| Lệnh | Hành động | Recording còn chạy? |
|---|---|---|
| **JFR.check** | Xem trạng thái recording | Không thay đổi |
| **JFR.dump** | Xuất dữ liệu đã thu đến thời điểm được yêu cầu | **Có**, tiếp tục chạy |
| **JFR.stop** | Dừng recording; có thể ghi file đích | **Không** |

~~~bash
# Xem các recording đang hoạt động.
jcmd 12345 JFR.check

# Xuất ảnh chụp dữ liệu nhưng vẫn giữ recording chạy.
jcmd 12345 JFR.dump name=investigation filename=partial.jfr

# Dừng recording có tên investigation.
jcmd 12345 JFR.stop name=investigation
~~~

Nếu muốn dừng và chỉ định file lúc dừng:

~~~bash
jcmd 12345 JFR.stop name=investigation filename=final.jfr
~~~

Nếu recording đã có **duration**, nó có thể tự kết thúc trước khi bạn gửi lệnh stop; phải kiểm tra trạng thái thực tế.

**JFR.dump có thể xuất dữ liệu của nhiều recordings nếu không chỉ rõ tên.** Với môi trường có nhiều recording, dùng **name** hoặc ID để tránh lẫn mục tiêu và phải kiểm soát kích thước file xuất.

## 10. Ghi liên tục với maxage và maxsize

Để điều tra sự cố hiếm xảy ra, chỉ bắt đầu ghi **sau khi sự cố đã xảy ra** có thể bỏ lỡ nguyên nhân. Một giải pháp là ghi JFR liên tục với retention bị giới hạn:

~~~bash
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=1h maxsize=256m
~~~

Đây là cấu hình minh họa, **không phải tham số khuyến nghị chung**. Hãy định mức theo lưu lượng event, tốc độ phát sinh file, dung lượng disk và yêu cầu dữ liệu.

Sau khi phát hiện sự cố, xuất khoảng gần nhất:

~~~bash
jcmd 12345 JFR.dump name=rolling maxage=15m filename=incident.jfr
~~~

Khái niệm:

- **maxage**: giữ dữ liệu trong một cửa sổ thời gian.
- **maxsize**: giữ dữ liệu đến một kích thước giới hạn.
- **disk=true**: sử dụng JFR disk repository theo chính sách.
- **dump**: tạo file phục vụ phân tích; không tự dừng recording.

Một recording dạng vòng tròn không bảo đảm giữ được vô hạn lịch sử: dữ liệu cũ có thể bị xóa theo giới hạn, và các sự kiện rất dày có thể khiến thời gian lịch sử thực sự giữ được ngắn hơn dự kiến.

**Giới hạn retention của JFR không thay chính sách lưu trữ file .jfr đã dump.** File xuất ra là artifact riêng, cần phân quyền, quota, thời gian xóa và nơi lưu trữ phù hợp.

## 11. Bắt đầu recording ngay từ startup

Khi cần quan sát bootstrap hoặc một sự cố xảy ra trước khi attach được vào JVM, có thể kích hoạt JFR lúc chạy process:

~~~bash
java -XX:StartFlightRecording=name=startup,settings=default,duration=60s,filename=startup.jfr -jar app.jar
~~~

Trong tham số **-XX:StartFlightRecording**, các option được ngăn cách bởi **dấu phẩy**. Với **jcmd JFR.start**, các option được ngăn cách bởi **dấu cách**.

Một recording chỉ kéo dài 60 giây sẽ không chứa các sự kiện phát sinh sau khoảng đó. Nếu vấn đề xảy ra khi app đã ấm máy (*warm*) hoặc dưới tải thực tế, hãy thu recording ở giai đoạn phù hợp.

**Không dùng các cờ cũ như -XX:+UnlockCommercialFeatures hoặc -XX:+FlightRecorder** làm hướng dẫn mặc định cho Java 27. JFR đã là thành phần chính thức được cung cấp rộng rãi trong JDK hiện đại.

## 12. Kiểm tra file .jfr bằng công cụ dòng lệnh

Sau khi có file recording:

~~~bash
jfr summary investigation.jfr
jfr metadata investigation.jfr
jfr print --events jdk.CPULoad investigation.jfr
jfr view hot-methods investigation.jfr
jfr view gc-pauses investigation.jfr
~~~

Các lệnh:

- **summary**: thống kê loại event, số lượng và kích thước trong file.
- **metadata**: xem kiểu event và cấu trúc trường.
- **print**: in từng event; có thể lọc theo tên hoặc nhóm.
- **view**: tổng hợp sự kiện thành bảng/truy vấn đã dựng sẵn như **hot-methods** hoặc **gc-pauses**.

**Tên view có thể thay đổi theo JDK và tập event.** Dùng **jfr --help view** để liệt kê những view hiện được hỗ trợ. Nếu recording không chứa event cần thiết, một view tương ứng có thể trống hoặc không đủ dữ liệu.

Chạy **summary trước** giúp xác nhận file có nội dung đúng khoảng thời gian và loại event cần xem, trước khi phân tích chi tiết.

## 13. Lọc event và xuất dữ liệu có cấu trúc

Một recording nhiều phút có thể chứa hàng nghìn đến hàng triệu events. Hãy lọc trước khi xuất văn bản:

~~~bash
# Lọc theo tên loại event:
jfr print --events jdk.GarbageCollection investigation.jfr

# Lọc nhiều loại sự kiện:
jfr print --events jdk.CPULoad,jdk.GarbageCollection investigation.jfr

# In ở định dạng JSON để đưa vào pipeline phân tích của bạn:
jfr print --json --events jdk.CPULoad investigation.jfr

# Điều chỉnh độ sâu stack được in:
jfr print --stack-depth 20 --events jdk.ExecutionSample investigation.jfr
~~~

**jfr print --json không biến recording thành dữ liệu vô hại.** Những trường có thể chứa tên class, phương thức, đường dẫn file, thông số môi trường và giá trị ứng dụng. Chỉ xuất/đẩy lên hệ thống khác khi được phép và đã áp dụng chính sách dữ liệu.

Với file rất lớn, **không in toàn bộ recording** ra terminal hoặc hệ thống log. Dùng **jfr view** để tổng hợp, **print --events** để lọc, hoặc Consumer API để xử lý dữ liệu theo luồng.

## 14. Mở recording trong Java Mission Control

Quy trình với **JMC**:

1. Cài JMC từ nhà phân phối đáng tin cậy và bảo đảm bản này hỗ trợ recording format/JDK mục tiêu.
2. Mở JMC như một ứng dụng riêng.
3. Chọn **File → Open File...** hoặc thao tác mở tương đương trong phiên bản JMC đang sử dụng.
4. Chọn file **.jfr** đã thu và chờ công cụ nạp/sắp xếp dữ liệu.
5. Xem mục **Automated Analysis Results** (nếu có), sau đó điều hướng các trang liên quan đến **Java Application**, **Threads**, **Memory**, **I/O** và **Garbage Collections**; tên tab có thể thay đổi theo bản JMC.
6. Dùng **time range selection**, filter và stack-trace views để tập trung vào lúc triệu chứng xảy ra.

JMC có thể mở file để phân tích **offline**, không nhất thiết phải kết nối trực tiếp với server đang chạy. Phương án này phù hợp khi JVM nằm trên mạng production nhạy cảm.

**JMC không phải một phần của JDK 27 launcher.** Đừng yêu cầu người học chạy một lệnh **jmc** từ JAVA_HOME/bin mà mặc định nó sẽ tồn tại.

## 15. Automated Analysis là gợi ý, không phải kết luận cuối

JMC có những quy tắc và heuristic phân tích tự động để gợi ý dấu hiệu bất thường. Chẳng hạn nó có thể chỉ ra:

- GC pauses có thời lượng đáng chú ý.
- Một số pattern allocation hoặc contention cao.
- Method/stack xuất hiện dày trong samples.
- Lịch hoạt động thread hoặc I/O bất thường.
- Cấu hình JVM có điểm cần chú ý.

Kết quả tự động là **tín hiệu để điều tra sâu hơn**, không phải chứng cứ đủ để thay đổi cấu hình JVM ngay.

Quy trình phù hợp:

~~~text
Phát hiện p99 latency tăng
       ↓
Chọn đoạn thời gian cùng triệu chứng trong JMC
       ↓
Kiểm tra CPU / GC / allocations / I/O / locks
       ↓
Đối chiếu request logs, tracing và metrics
       ↓
Đưa ra giả thuyết cụ thể
       ↓
Thay đổi có kiểm soát và đo lại
~~~

Một cảnh báo về allocation cao không có nghĩa chắc chắn có memory leak. Một hot method trong profile cũng không tự chứng minh rằng tối ưu method ấy sẽ cải thiện p99 latency của sản phẩm.

## 16. Chọn đúng khoảng thời gian và workload

Khi so sánh hai recording, phải bảo đảm điều kiện gần tương đương:

| Điều kiện | Cần đối chiếu |
|---|---|
| Phiên bản ứng dụng | Cùng commit/build hoặc có thay đổi rõ |
| JVM/JDK | Cùng hoặc biết chính xác sự khác biệt |
| Cấu hình JFR | Tương đương về events, thresholds, sampling |
| Request mix | Tỷ lệ endpoints, payload, dữ liệu truy vấn |
| Throughput | Request/s, batch/s, scheduled workload |
| Tài nguyên | CPU cores/quota, heap, container memory, disk |
| Warm-up | JIT đã biên dịch code nóng chưa, cache đã ấm chưa |
| Thời điểm | Cửa sổ có triệu chứng và baseline |
| Dependency | Database, network, downstream latency |

Một recording khi hệ thống rảnh **không đại diện** cho tình trạng khi đạt 5.000 requests/giây. Khi CPU ở 100%, tỷ lệ method samples thường hữu ích hơn khi ghép với metric CPU/quota và throughput.

**Với benchmark**, dùng quy trình chuyên dụng như JMH cho microbenchmarks nếu phù hợp; JFR chỉ bổ sung bằng chứng về điều gì diễn ra bên trong workload, không thay thế kiểm soát sai số, warm-up và các phép đo thống kê.

## 17. Điều tra CPU hotspot bằng execution samples

Khi metrics cho thấy CPU Java cao, có thể xem **hot-methods**, execution samples và stack traces.

~~~bash
jfr view hot-methods investigation.jfr
jfr print --events jdk.ExecutionSample investigation.jfr
~~~

Cách đọc:

1. Chọn đoạn thời gian **CPU thực sự cao**.
2. Xem call tree và những methods/frames xuất hiện nhiều.
3. Phân biệt **self time** và **inclusive time** trong biểu diễn của công cụ: một phương thức wrapper có thể xuất hiện ở nhiều stacks dù không phải nơi tiêu tốn CPU chủ yếu.
4. Kiểm tra phiên bản code, cấu trúc dữ liệu và tần suất gọi.
5. Đối chiếu với thời gian thực thi end-to-end và CPU quota của container.

**Sample count là số mẫu**, không phải số lần gọi method. Một phương thức được gọi 10 triệu lần nhưng mỗi lần rất ngắn có thể xuất hiện ít; một method vòng lặp dài có thể xuất hiện nhiều.

Nếu CPU usage thấp nhưng latency cao, có thể nguyên nhân chính là **chờ I/O, monitor, downstream dependency hoặc queue**, không phải CPU hotspot. Không chỉ nhìn bảng hot methods.

## 18. Phân tích allocation pressure

JVM có thể tạo rất nhiều object ngắn hạn mà **không xảy ra memory leak**; GC có nhiệm vụ thu hồi những object không còn reachable. Vấn đề hiệu năng thường nằm ở **allocation rate**, pattern giữ lại object và chi phí GC.

Các view thường hữu ích:

~~~bash
jfr view allocation-by-class investigation.jfr
jfr view allocation-by-site investigation.jfr
~~~

Một số event liên quan như **jdk.ObjectAllocationSample** phản ánh việc cấp phát theo sampling. Không diễn giải số samples là con số chính xác tuyệt đối về mọi object đã được tạo.

Khi điều tra:

- Xác định class nào và code path nào tạo nhiều objects.
- Phân biệt **phân bổ bộ nhớ nhiều nhưng ngắn hạn** với **giữ object lâu dài**.
- Đối chiếu allocation rate với throughput: tăng cấp phát vì workload gấp đôi chưa chắc là regression.
- Xem chuỗi/hộp số, collection tạm, JSON serialization, buffering và cấu trúc dữ liệu.
- Kiểm tra kết quả sau tối ưu bằng cùng workload, tránh chỉ giảm một chỉ số nhưng tăng CPU hoặc độ trễ.

JFR giúp **định hướng** tìm nơi cấp phát; để chứng minh leak và chuỗi giữ tham chiếu, có thể cần **heap dump**, heap analysis và điều tra GC roots bằng công cụ phù hợp.

## 19. GC: phân biệt allocation, heap occupancy và pause time

GC cần được nhìn trong mối quan hệ với **heap**, **allocation rate**, **live set**, **collection behavior** và **latency**.

~~~bash
jfr view gc investigation.jfr
jfr view gc-pauses investigation.jfr
jfr print --events jdk.GarbageCollection investigation.jfr
~~~

Một số câu hỏi:

1. GC hoạt động thường xuyên hay không?
2. Phần thời gian pause có trùng khoảng p99 latency tăng không?
3. Heap sau GC có giảm về mức ổn định hay tăng dần?
4. Allocation rate có tăng cùng throughput hay tăng bất thường?
5. Có hiện tượng promotion/retained objects khiến live set tăng?
6. CPU bị chiếm bởi ứng dụng, GC threads hay hoạt động khác?

~~~text
Allocation ↑
   ↓
GC frequency có thể ↑
   ↓
Pause/CPU pressure có thể ↑
   ↓
Latency bị ảnh hưởng tùy GC và workload
~~~

**Không kết luận leak chỉ từ một lần heap usage tăng** hoặc một GC dài. JVM có thể tăng vùng heap theo chính sách và hoạt động cấp phát tự nhiên. Cần xu hướng qua nhiều chu kỳ GC, thông tin retained objects và bằng chứng từ heap nếu nghi leak.

Nếu dùng collector khác nhau, interpretation của pause/phase có thể khác; không so trực tiếp các con số mà không xét cấu hình collector, heap và workload.

## 20. Thread contention, monitor và blocked time

JFR có các loại sự kiện để phân tích thread synchronization và blocking. Ví dụ **jdk.JavaMonitorEnter** liên quan thời gian tranh chấp monitor.

~~~bash
jfr print --events jdk.JavaMonitorEnter investigation.jfr
jfr view contention-by-class investigation.jfr
jfr view contention-by-thread investigation.jfr
~~~

Khi thấy contention đáng chú ý:

- Xem monitor/class nào bị tranh chấp.
- Xem thread nào chờ, thread nào có thể đang giữ khóa.
- Xem stack traces ở thời điểm chờ.
- Kiểm tra có I/O hoặc xử lý dài **bên trong synchronized block** hay không.
- Xem lock scope và shared mutable state.

**Một contention event không đồng nghĩa deadlock.** Deadlock có thể cần thread dump hoặc phân tích quan hệ đợi của nhiều thread:

~~~bash
jcmd 12345 Thread.print
~~~

Chỉ dùng khi được phép vận hành và cần thiết; thread dumps cũng có thể chứa class/method names và dữ liệu nhạy cảm.

Với virtual threads, cách JVM xử lý blocking/pinning đã phát triển ở những bản JDK gần đây. **Không áp dụng máy móc lời khuyên cũ rằng mọi synchronized đều pin virtual thread**; cần xem JDK/version cụ thể và các sự kiện/metric thực tế.

## 21. File I/O và socket I/O

Thời gian chờ I/O có thể làm tăng latency ngay cả khi CPU thấp.

Một số view có ích:

~~~bash
jfr view file-reads-by-path investigation.jfr
jfr view socket-reads-by-host investigation.jfr
~~~

Những điều cần tìm:

- Nơi nào có các thao tác đọc/ghi chậm hoặc kéo dài.
- Số byte và tần suất của các thao tác đó.
- Stack trace của code gọi I/O.
- Tương quan với giới hạn connection pool, network latency, database timeouts và downstream metrics.
- Phần chờ do ứng dụng quản lý so với phần chờ trong OS/network.

Một **socket read kéo dài** không tự chứng minh mạng lỗi: server có thể đang chờ dữ liệu do phía bên kia chưa gửi, do query chạy chậm, timeout lớn hoặc có nhiều lớp proxy. JFR cung cấp **dấu hiệu trong JVM**, cần kết hợp thông tin phía dependency.

Khi dùng event lọc theo host/path, hãy tránh xuất đường dẫn nhạy cảm hoặc endpoint nội bộ cho người không có quyền.

## 22. Tác vụ bất đồng bộ và virtual threads

Trong ứng dụng dùng **ExecutorService**, **CompletableFuture** hoặc **virtual threads**, một request có thể trải qua nhiều thread và nhiều giai đoạn.

JFR có thể thể hiện từng thread/event riêng, nhưng không tự cung cấp đầy đủ **distributed trace** cho toàn bộ request. Muốn liên hệ nghiệp vụ:

- Có thể phát **custom events** với một operation name hoặc correlation ID **không nhạy cảm**.
- Ghi latency từng giai đoạn như parse, DB, mapping, external call.
- Đối chiếu với tracing/metrics để hiểu critical path.
- Tránh đưa toàn bộ request body, token hay thông tin định danh người dùng vào event field.

Số lượng virtual threads cao không tự là vấn đề. Cần xem tài nguyên thực sự bị giới hạn: CPU, DB connections, sockets, downstream rate limits, memory/stack usage và thời gian chờ.

**Không đánh đồng CPU samples với latency của tác vụ bất đồng bộ**: một task chủ yếu chờ network có thể xuất hiện ít trong CPU samples nhưng vẫn là nguyên nhân khiến request kết thúc chậm.

## 23. Startup, class loading và JIT compilation

Khi ứng dụng chậm ở lần chạy đầu hoặc sau redeploy, recording lúc startup có thể giúp quan sát:

- Class loading và initialization.
- Hoạt động JIT compilation.
- GC trong giai đoạn tạo nhiều object.
- Thread setup và các hoạt động nền.
- Một số thời lượng I/O liên quan khởi động.

~~~bash
java -XX:StartFlightRecording=name=startup,settings=profile,duration=90s,filename=startup.jfr -jar app.jar
~~~

Sau đó:

~~~bash
jfr summary startup.jfr
jfr view longest-class-loading startup.jfr
~~~

**Lưu ý:** Một method chạy chậm ở lần đầu có thể do khởi tạo class, JIT warm-up, tải cấu hình hay cache miss, không phải do thuật toán thuần túy. Đo benchmark cần có giai đoạn warm-up và so sánh sau khi điều kiện ổn định.

Những view về compilation và class loading có tính phụ thuộc event settings, vì vậy không phải mọi recording đều chứa dữ liệu để phân tích được.

## 24. Tạo custom JFR event cho nghiệp vụ

JDK cho phép ứng dụng định nghĩa event bằng cách **extends jdk.jfr.Event**:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Threshold;

@Name("demo.OrderProcessing")
@Label("Order Processing")
@Description("Timing of an order processing step")
@Category({"Application", "Orders"})
@Threshold("1 ms")
class OrderProcessingEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Item Count")
    int itemCount;

    @Label("Succeeded")
    boolean succeeded;
}
~~~

Ý nghĩa annotation:

| Annotation | Công dụng |
|---|---|
| **@Name** | Tên event type ổn định để lọc trong CLI/JMC |
| **@Label** | Tên hiển thị cho người phân tích |
| **@Description** | Giải thích ý nghĩa event |
| **@Category** | Phân nhóm event trong công cụ |
| **@Threshold** | Ngưỡng thời lượng mặc định để ghi event |
| **@StackTrace** | Điều khiển mặc định việc thu stack trace |
| **@Enabled** | Trạng thái bật/tắt mặc định của event |

**@Threshold("1 ms")** nghĩa là event ngắn hơn ngưỡng có thể không được ghi. Một recording có thể override setting này để phục vụ chẩn đoán cụ thể.

Event fields được hỗ trợ bởi JFR gồm các kiểu nguyên thủy, **String**, **Thread** và **Class**; field static/transient hoặc những reference types không được hỗ trợ không thành event field như mong muốn. Không đặt nguyên một object graph hoặc List vào event rồi mong JFR serialize tự động.

## 25. Event.begin, end, shouldCommit và commit

Quy trình cho một sự kiện có thời lượng:

~~~java
OrderProcessingEvent event = new OrderProcessingEvent();
event.operation = "calculate-total";
event.begin();

try {
    performOperation();
    event.succeeded = true;
} finally {
    event.end();

    if (event.shouldCommit()) {
        event.itemCount = knownItemCount;
        event.commit();
    }
}
~~~

Trong đoạn minh họa, **performOperation** và **knownItemCount** là thành phần của ứng dụng, không phải API JDK.

- **begin()**: đánh dấu bắt đầu đo thời lượng.
- **end()**: đánh dấu kết thúc.
- **isEnabled()**: cho biết có recording đang bật event tương ứng hay không.
- **shouldCommit()**: kiểm tra event có đủ điều kiện ghi theo trạng thái bật và threshold hiện tại không.
- **commit()**: ghi event khi phù hợp.

**Nên thực hiện thu thập metadata đắt đỏ sau shouldCommit() nếu có thể**: khi event bị tắt hoặc quá ngắn, điều đó tránh tạo chuỗi lớn hoặc truy vấn dữ liệu không cần thiết.

**Không ném lỗi JFR thay cho lỗi nghiệp vụ**; nếu event chỉ là chẩn đoán, cần thiết kế sao cho sự cố trong việc thu metadata không che exception chính của thao tác. Trong production, hãy tránh tạo payload event chứa dữ liệu nhạy cảm.

## 26. Custom event không phải distributed tracing

Một custom event có thể biểu thị:

~~~text
OrderProcessing[operation=calculate-total, duration=15ms]
~~~

Nó rất hữu ích khi nằm cạnh các event CPU, GC, I/O trong cùng recording. Tuy nhiên:

- Nó không tự lan truyền context qua các services.
- Nó không bảo đảm span hierarchy, sampling policy hoặc distributed trace IDs.
- Nó không phải cơ chế lưu audit nghiệp vụ có yêu cầu bền vững.
- Không bảo đảm mọi event được ghi khi recording hoặc event type bị tắt.
- Có thể thiếu event dưới điều kiện giới hạn/thay đổi cấu hình JFR.

**JFR là công cụ chẩn đoán**, không nên là hệ thống nguồn-sự-thật để xác nhận thanh toán thành công hoặc thực hiện phân tích tài chính bắt buộc.

Nếu cần liên hệ với tracing, chỉ ghi **correlation ID đã được đánh giá về privacy/cardinality**, không dùng token xác thực hay dữ liệu cá nhân.

## 27. Recording API trong ứng dụng Java

Ngoài jcmd, ứng dụng có thể điều khiển JFR qua **jdk.jfr.Recording**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

Path output = Path.of("application.jfr");

try (Recording recording = new Recording(
        Configuration.getConfiguration("default"))) {

    recording.setName("application-diagnostics");
    recording.setToDisk(true);
    recording.setMaxAge(Duration.ofMinutes(10));
    recording.setMaxSize(64L * 1024 * 1024);

    recording.start();

    // Thực hiện workload cần quan sát.

    recording.stop();
    recording.dump(output);
}
~~~

**Recording** là AutoCloseable: dùng **try-with-resources** để giải phóng tài nguyên gắn với đối tượng Recording. Nếu không dùng **setDestination**, lệnh **dump(Path)** cho phép ghi file khi cần.

Không tạo recording mới cho **mỗi request** của một dịch vụ production. Việc thu dữ liệu nên có chính sách vòng đời, quyền thao tác và quota rõ ràng; custom events là lựa chọn phù hợp hơn để đo các bước riêng lẻ trong một recording đang hoạt động.

Tùy điều kiện runtime, một số phương thức có thể ném exception khi file không ghi được hoặc JFR không sẵn sàng. Phải có chính sách xử lý để phần chẩn đoán không làm hỏng toàn bộ luồng nghiệp vụ.

## 28. Demo chạy độc lập: ghi và đọc custom events

Tệp **JfrDiagnosticsDemo.java** dưới đây tạo một recording, thực hiện workload, ghi năm custom events, xuất **demo-recording.jfr**, rồi đọc lại các events do chương trình tạo.

~~~java
import java.nio.file.Path;
import java.time.Duration;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrDiagnosticsDemo {
    @Name("demo.OrderWork")
    @Label("Order Work")
    @Category({"Application", "Orders"})
    @Threshold("0 ms")
    static class OrderWorkEvent extends Event {
        @Label("Operation")
        String operation;

        @Label("Item Count")
        int itemCount;

        @Label("Succeeded")
        boolean succeeded;
    }

    static int compute(int count) {
        int checksum = 0;

        for (int i = 0; i < count; i++) {
            checksum += i % 7;
        }

        return checksum;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("demo-recording.jfr");

        try (Recording recording =
                new Recording(Configuration.getConfiguration("default"))) {

            recording.setName("jfr-demo");
            recording.setToDisk(true);
            recording.enable(OrderWorkEvent.class)
                .withThreshold(Duration.ZERO);

            recording.start();

            for (int i = 1; i <= 5; i++) {
                OrderWorkEvent event = new OrderWorkEvent();
                event.operation = "simulate-order";
                event.itemCount = i * 100;
                event.begin();

                try {
                    int checksum = compute(800_000);
                    event.succeeded = (checksum != Integer.MIN_VALUE);

                } finally {
                    event.end();

                    if (event.shouldCommit()) {
                        event.commit();
                    }
                }
            }

            recording.stop();
            recording.dump(output);
        }

        int customCount = 0;

        try (RecordingFile recordingFile = new RecordingFile(output)) {
            while (recordingFile.hasMoreEvents()) {
                RecordedEvent event = recordingFile.readEvent();

                if (!event.getEventType().getName()
                        .equals("demo.OrderWork")) {
                    continue;
                }

                customCount++;

                System.out.println(
                    event.getString("operation")
                        + " items=" + event.getInt("itemCount")
                        + " duration=" + event.getDuration()
                );
            }
        }

        System.out.println("Custom events: " + customCount);
        System.out.println("Recording: " + output.toAbsolutePath());
    }
}
~~~

Biên dịch và chạy với JDK 27 hỗ trợ JFR:

~~~bash
javac -encoding UTF-8 JfrDiagnosticsDemo.java
java JfrDiagnosticsDemo
~~~

Kết quả dự kiến: năm dòng chứa **simulate-order**, số lượng **100, 200, 300, 400, 500**, cùng thời lượng thực tế, sau đó:

~~~text
Custom events: 5
Recording: .../demo-recording.jfr
~~~

Thời lượng của từng sự kiện phụ thuộc máy, JIT, tải và scheduling nên **không cố định**. Đường dẫn cuối cùng phụ thuộc thư mục chạy chương trình.

Bài demo dùng **Duration.ZERO** để bảo đảm các custom events không bị lọc bởi ngưỡng thời lượng trên recording của ví dụ; **đó không phải khuyến nghị mặc định cho mọi event tần suất cao ở production**.

## 29. Phân tích file demo bằng jfr

Sau khi chạy chương trình demo:

~~~bash
jfr summary demo-recording.jfr
jfr print --events demo.OrderWork demo-recording.jfr
jfr metadata --events demo.OrderWork demo-recording.jfr
~~~

Trong **summary**, tìm event type **demo.OrderWork**. Trong **print**, xem từng event với **operation**, **itemCount**, **succeeded**, **startTime** và **duration**.

Nếu dùng JMC:

1. Mở **demo-recording.jfr**.
2. Mở event browser hoặc danh sách event types.
3. Tìm nhóm **Application → Orders** hoặc tên **demo.OrderWork**.
4. Xem duration và các trường item count.
5. Tương quan thời điểm custom events với các JVM events khác có trong recording.

**Không kết luận CPU từ duration của event**: event đo *wall-clock elapsed time* giữa begin/end, có thể bao gồm thời gian thread không chạy do scheduler, lock hoặc I/O. Muốn phân biệt CPU và waiting cần thêm event/metrics phù hợp.

## 30. Đọc dữ liệu theo luồng bằng RecordingFile

Nếu chỉ cần xử lý một số event types, **RecordingFile** có API tuần tự:

~~~java
import java.nio.file.Path;
import jdk.jfr.consumer.RecordingFile;

Path path = Path.of("demo-recording.jfr");

try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        var event = file.readEvent();

        if ("demo.OrderWork".equals(event.getEventType().getName())) {
            System.out.println(event.getDuration());
        }
    }
}
~~~

**RecordingFile.readAllEvents(Path)** cũng được hỗ trợ, nhưng nó trả **List** chứa toàn bộ events; với recording lớn, nên ưu tiên duyệt tuần tự để tránh giữ nhiều đối tượng trong RAM không cần thiết.

**Chỉ mở recordings từ nguồn đáng tin cậy.** Javadoc của RecordingFile cảnh báo về việc xử lý recording files do bên khác cung cấp; đối với file không đáng tin, cần cô lập, giới hạn tài nguyên và chính sách vận hành thích hợp.

Khi xử lý file .jfr để tạo báo cáo, tránh lưu toàn bộ event payload vào database hoặc dashboard mà không kiểm tra dữ liệu nhạy cảm.

## 31. JFR Event Streaming khi cần phản ứng sớm

Java cung cấp **jdk.jfr.consumer.RecordingStream** cho tình huống cần nhận sự kiện khi ứng dụng đang chạy mà không phải đợi dump file rồi mới phân tích.

~~~java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));

    stream.onEvent("jdk.CPULoad", event -> {
        float fraction = event.getFloat("jvmUser");
        System.out.println("JVM user CPU fraction: " + fraction);
    });

    stream.startAsync();

    Thread.sleep(3_000);
}
~~~

Trong ví dụ này **stream.startAsync()** khởi động xử lý events bất đồng bộ; đóng stream khi ra khỏi try-with-resources. Sự kiện có thể không xuất hiện đủ số lần khi chạy ngắn hoặc dưới các điều kiện runtime khác nhau.

**Không ghi log từng event với tốc độ không giới hạn ở production.** Nếu event stream được dùng để tạo metric/alert, cần giới hạn queue, rate, cách xử lý callback lỗi và chính sách shutdown.

JFR event stream là kênh observability, **không phải message queue có cơ chế lưu giao dịch và retry nghiệp vụ**.

## 32. Overhead, event volume và mất dữ liệu

JFR được thiết kế cho profiling với overhead thấp trong nhiều tình huống, nhưng vẫn có các chi phí:

| Nguồn chi phí | Khi nào tăng |
|---|---|
| Thu stack traces | Tần suất event cao, stack sâu |
| Event với threshold thấp | Rất nhiều sự kiện ngắn được ghi |
| Custom event chứa String | Tạo/ghi nhiều giá trị, metadata nhạy cảm |
| Ghi disk repository | Event volume lớn, disk chậm hoặc quota hạn chế |
| Dump nhiều lần | I/O và tạo nhiều files |
| Đọc dữ liệu trong ứng dụng | RecordingFile giữ/bóc tách nhiều events |
| JMC phân tích file lớn | RAM và CPU tại máy phân tích |
| Streaming callbacks | Callback làm việc nặng hoặc không theo kịp event rate |

Để kiểm soát:

1. Bắt đầu từ **default** cho recording dài và chỉ tăng độ chi tiết khi có giả thuyết.
2. Đặt **maxage/maxsize** hợp lý nếu ghi liên tục.
3. Chỉ bật event types cần thiết và đặt **threshold/period** có ý nghĩa.
4. Không nhúng dữ liệu cá nhân/secret vào custom event fields.
5. Giám sát disk/repository, latency, CPU và recording size.
6. So sánh workload có và không có cấu hình profiling nặng khi đánh giá overhead.
7. Có chính sách khi diagnostic data bị thiếu hoặc một số events không được ghi.

**Không coi file .jfr là nhật ký đầy đủ, không mất một event nào.** Event có thể bị giới hạn bởi cấu hình, sampling, buffer/disk và trạng thái runtime.

## 33. An toàn dữ liệu và quyền truy cập recording

File **.jfr** có thể chứa:

- Tên package, class, method và stack traces.
- Tên thread, đường dẫn file, địa chỉ/hostname phụ thuộc event.
- Một số system properties và thông tin cấu hình JVM.
- Custom event fields, có thể do ứng dụng vô tình ghi dữ liệu người dùng.
- Các chuỗi hoặc metadata kỹ thuật làm lộ cấu trúc nội bộ.

Chính sách tối thiểu:

- **Chỉ người được phép** mới có quyền attach jcmd hoặc đọc .jfr.
- Lưu file tại thư mục được bảo vệ bởi quyền OS; không đặt file dưới web root.
- Hạn chế thời gian giữ, số file và tổng dung lượng.
- Mã hóa khi lưu/truyền theo chính sách tổ chức.
- Kiểm tra và **loại/che dữ liệu nhạy cảm** trước khi chia sẻ với bên ngoài.
- Tránh custom events chứa authorization headers, mật khẩu, token, toàn bộ query/request body.
- Ghi nhận ai tạo recording, phục vụ mục đích gì và khi nào được xóa.

**jfr scrub** hỗ trợ lọc bỏ một số dữ liệu/sự kiện khi thao tác recording, nhưng không bảo đảm tự động loại hết thông tin nhạy cảm trong mọi event field. Không dùng nó thay quy trình kiểm tra nội dung và phê duyệt chia sẻ dữ liệu.

## 34. Ghi GC roots và phân tích memory leak có chi phí riêng

Một số tùy chọn diagnostic cho JFR có thể thu **paths to GC roots** khi dump/stop:

~~~bash
# Chỉ dùng trong môi trường được phép và khi đang điều tra memory leak.
jcmd 12345 JFR.dump name=rolling path-to-gc-roots=true filename=leak-investigation.jfr
~~~

Tùy chọn này có thể **gây pause và tốn thêm thời gian**, vì JVM phải tìm đường tham chiếu tới những đối tượng liên quan. Không bật trong mọi recording dài hạn chỉ vì muốn “có thêm dữ liệu”.

Để điều tra leak:

1. Kiểm tra xu hướng memory sau GC qua thời gian.
2. Tìm loại đối tượng/stack cấp phát đáng chú ý.
3. Bật những tùy chọn chẩn đoán sâu hơn trong cửa sổ có kiểm soát.
4. Nếu cần, kết hợp heap dump và phân tích retained references.
5. Đối chiếu class loader/thread/cache/listener lifecycle khi nghi leak sau redeploy.

JFR giúp xác định **khi nào và nơi nào** vấn đề diễn ra; một số chuỗi tham chiếu giữ sống object vẫn cần công cụ heap analysis chuyên biệt.

## 35. Khi nào dùng JFR, khi nào dùng phương án khác?

| Nhu cầu | Công cụ ưu tiên |
|---|---|
| Điều tra CPU/GC/allocation/locks trong JVM | **JFR + JMC** hoặc **jfr CLI** |
| Truy vấn nhanh một vài event totals | **jfr summary/view** |
| Thu profile ngắn ở JVM đang chạy | **jcmd JFR.start/dump/stop** |
| Ghi liên tục để phân tích sau sự cố | **JFR rolling recording** với retention |
| Đo nghiệp vụ trong cùng JVM | **Custom JFR events** |
| Quan sát request đi qua nhiều microservices | **Distributed tracing** |
| Theo dõi SLO dài hạn và alert | **Metrics/monitoring** |
| Microbenchmark một phương thức hoặc cấu trúc dữ liệu | **JMH** theo quy trình benchmark |
| Xem object retention/GC roots chi tiết | **Heap dump + heap analyzer** khi cần |
| Điều tra stuck thread hoặc deadlock tức thời | **Thread dump/jcmd** phối hợp JFR |
| Phân tích native memory ngoài Java heap | **Native Memory Tracking** và hệ thống monitoring |

Một công cụ không thay thế tất cả. Ví dụ ứng dụng có p99 latency cao do database chậm có thể không có Java CPU hotspot nào; lúc đó tracing và DB metrics có thể quyết định hơn JFR.

## 36. Quy trình điều tra production có thể lặp lại

~~~mermaid
flowchart TD
    A["1. Xác nhận triệu chứng + phạm vi ảnh hưởng"] --> B["2. Thu baseline/metrics"]
    B --> C["3. Chọn default/profile + thời gian ghi"]
    C --> D["4. Tạo JFR recording có retention"]
    D --> E["5. Xem summary / JMC timeline"]
    E --> F{"Tín hiệu chính?"}
    F -->|"CPU"| G["Execution samples + hot methods"]
    F -->|"Memory / GC"| H["Allocation, heap trend, GC pauses"]
    F -->|"Latency / waiting"| I["Threads, monitors, I/O, dependencies"]
    G --> J["6. Giả thuyết nguyên nhân"]
    H --> J
    I --> J
    J --> K["7. Thay đổi có kiểm soát"]
    K --> L["8. So sánh recording + SLO"]
~~~

Ví dụ runbook cho dịch vụ chậm:

1. Ghi lại thời điểm p99 latency tăng và mối tương quan với traffic.
2. Kiểm tra JVM, PID, container và quyền ghi file.
3. Bắt đầu recording profile ngắn trong cửa sổ có tải (nếu được phép).
4. Kiểm tra recording xuất được và không vượt quota.
5. Chạy **jfr summary** để xác minh event types.
6. Mở JMC, chọn đúng time range có triệu chứng.
7. Điều tra CPU/allocation/GC/locks/I/O theo tín hiệu mạnh nhất.
8. Xác minh giả thuyết bằng logs, traces, metric và code cụ thể.
9. Thay đổi một yếu tố một lần nếu có thể.
10. Đo lại dưới workload tương đương, kiểm tra cả p99, throughput, CPU, memory.
11. Thu hồi file/recording cũ theo chính sách retention.

**Không cấu hình JVM dựa trên một screenshot JMC duy nhất** mà thiếu baseline và sự xác nhận từ workload.

## 37. Những sai lầm thường gặp

| Sai lầm | Tác hại | Cách tiếp cận tốt hơn |
|---|---|---|
| Chỉ bật JFR khi sự cố đã kết thúc | Mất dữ liệu nguyên nhân | Rolling recording có retention |
| Dùng profile rất chi tiết liên tục vô thời hạn | Tăng overhead/disk | Default dài hạn, profile trong khoảng có kiểm soát |
| Cho rằng JMC đi kèm mọi JDK | Không tìm thấy ứng dụng | Cài JMC riêng theo phiên bản phù hợp |
| Không xác minh PID và quyền attach | Thu sai JVM hoặc bị từ chối | jcmd -l, kiểm tra user/runtime |
| Ghi file tương đối rồi không biết nó ở đâu | Nhầm cwd tiến trình đích | Dùng absolute path được phép |
| Đọc toàn bộ event thành JSON để debug | Tràn log và dữ liệu | Lọc event/view trước |
| Xem sample count là số lần gọi | Kết luận sai hotspot | Hiểu sampling |
| Xem allocation nhiều là memory leak | Tối ưu sai mục tiêu | So live set/retained objects |
| Xem GC nhiều là nguyên nhân duy nhất của p99 | Bỏ qua DB/I/O/lock | Đối chiếu timeline và dependencies |
| Xem custom event duration như CPU time | Nhầm waiting với CPU | Dùng thêm execution samples/metrics |
| Periodic sample bị thiếu thì nghĩ không có sự kiện | Event bị tắt hoặc threshold không phù hợp | Kiểm tra .jfc / JFR.check verbose |
| Gắn request body/token vào custom event | Lộ dữ liệu bí mật | Giới hạn field và che thông tin |
| Bật paths-to-GC-roots cho mọi dump | Có thể pause đáng kể | Chỉ dùng khi điều tra leak |
| So sánh recording khác traffic/JDK/JFR settings | Kết luận performance regression sai | Chuẩn hóa điều kiện đo |
| Lạm dụng System.gc() để tạo sự kiện | Làm thay đổi workload và GC | Để collector hoạt động theo tải thực |
| Coi JFR thay tracing/audit | Thiếu causal spans và dữ liệu bền vững | Phối hợp observability chuyên biệt |
| Kết luận từ một automated rule | Heuristic có thể thiếu bối cảnh | Xem raw events, stack và baseline |

## 38. Bài tập thực hành

**Bài tập 1 — Recording ngắn.** Chạy một ứng dụng Java mẫu trên môi trường được phép, dùng **jcmd -l**, sau đó **JFR.start settings=default duration=60s**. Xác nhận recording bằng **JFR.check** và mở file bằng **jfr summary**.

**Bài tập 2 — Ghi liên tục.** Tạo recording **disk=true maxage=30m maxsize=128m**, dump một cửa sổ 10 phút để điều tra, sau đó kiểm tra recording vẫn chạy. Giải thích khác biệt giữa **JFR.dump** và **JFR.stop**.

**Bài tập 3 — Default và profile.** Chạy cùng workload hai lần: một lần với **default**, một lần với **profile**. So sánh số event types, kích thước file, CPU/latency và thời gian cần thiết để tìm một hotspot. Không kết luận khi workload khác nhau đáng kể.

**Bài tập 4 — CPU.** Tạo workload CPU-bound có phép tính lặp. Xem **hot-methods** và stack samples. Giải thích vì sao số mẫu không phải số lần gọi phương thức.

**Bài tập 5 — GC và allocation.** Tạo workload cấp phát nhiều đối tượng ngắn hạn trong môi trường thí nghiệm. So sánh **allocation-by-class**, GC pauses và heap usage sau GC. Giải thích khác biệt giữa allocation pressure và memory leak.

**Bài tập 6 — Contention.** Tạo một thao tác synchronized có thời gian giữ khóa đáng kể, chạy nhiều threads cùng gọi. Quan sát **JavaMonitorEnter** và stack trace của nơi chờ; kiểm tra cách threshold làm thay đổi số event.

**Bài tập 7 — Custom JFR event.** Chỉnh demo để ghi thêm **operation**, **itemCount**, **success** cho hai loại công việc. Đặt threshold theo nghiệp vụ, dùng **shouldCommit()** và so sánh file có/không có sự kiện rất ngắn.

**Bài tập 8 — JMC offline.** Mở file .jfr trong JMC, chọn đúng time range, xem automated analysis và một trang liên quan CPU/GC. Ghi lại giả thuyết và cách xác minh bằng metrics hoặc code.

**Bài tập 9 — Privacy.** Thiết kế chính sách retention, quyền đọc file và redaction cho recording production. Chứng minh vì sao không được tự động đăng .jfr lên ticket công khai.

**Bài tập 10 — Kế hoạch điều tra.** Một API có p99 latency tăng trong khi CPU thấp và heap ổn định. Chọn những events/view phù hợp và những dữ liệu bổ sung cần thu để phân biệt socket I/O, DB pool waiting và thread contention.

## 39. Checklist thực hành JFR/JMC trong Java 27

- [ ] Có câu hỏi hiệu năng cụ thể trước khi bật recording.
- [ ] Biết JFR được tích hợp vào JVM, còn JMC là ứng dụng phân tích cài riêng.
- [ ] Xác định chính xác JVM/PID, phiên bản JDK và quyền attach.
- [ ] Phân biệt **jcmd** điều khiển recording và **jfr** đọc file .jfr.
- [ ] Biết cách dùng **JFR.start**, **JFR.check**, **JFR.dump**, **JFR.stop**.
- [ ] Biết **dump không dừng recording**; stop mới kết thúc.
- [ ] Dùng **default** hoặc **profile** theo độ chi tiết/overhead cần thiết.
- [ ] Giới hạn **maxage**, **maxsize**, thời lượng và nơi ghi file.
- [ ] Không sử dụng cờ bật JFR thương mại cũ trong thiết kế Java 27 mới.
- [ ] Dùng **jfr summary** để xác nhận loại event đã được ghi.
- [ ] Dùng **jfr view/print** để điều tra có lọc, tránh xuất hết event.
- [ ] Trong JMC, chọn time range chứa triệu chứng, đối chiếu baseline.
- [ ] Hiểu execution/allocation samples không ghi tất cả lời gọi/cấp phát.
- [ ] Không xem GC frequency hoặc allocation rate là bằng chứng leak.
- [ ] Kết hợp CPU, GC, locks, I/O và dependency metrics khi tìm nguyên nhân.
- [ ] Tạo custom events bằng **jdk.jfr.Event** khi cần ngữ cảnh nghiệp vụ.
- [ ] Sử dụng **begin/end/shouldCommit/commit** đúng mục đích.
- [ ] Không ghi token, password, dữ liệu cá nhân hoặc request body vào JFR.
- [ ] Dùng **Recording/RecordingFile** với try-with-resources khi viết code chẩn đoán.
- [ ] Dùng **RecordingStream** khi cần theo dõi sự kiện trực tiếp, kèm giới hạn callback workload.
- [ ] Không xem .jfr là audit log hoặc distributed tracing đầy đủ.
- [ ] Chỉ thu GC roots/stack traces chi tiết hơn khi đã tính overhead.
- [ ] Bảo vệ .jfr bằng quyền truy cập, retention và quy trình chia sẻ an toàn.
- [ ] Kiểm tra hiệu quả thay đổi bằng cùng workload và metrics SLO.
- [ ] Không triển khai một “tối ưu” chỉ vì công cụ tự động gợi ý.
- [ ] Kiểm tra phiên bản JMC và event settings khi recording không hiển thị đúng.

**Kết luận:** JFR giúp thu bằng chứng về **JVM và ứng dụng đang làm gì trong một khoảng thời gian**, còn JMC giúp biến những events đó thành góc nhìn để đặt giả thuyết và điều tra. Hiệu quả của công cụ không nằm ở việc bật mọi event, mà ở cách **xác định triệu chứng, chọn cấu hình, thu đúng khoảng thời gian, đọc đúng loại dữ liệu và đo lại sau khi thay đổi**. Với Java 27, sử dụng JFR/JMC đúng cách là kết hợp profiling, metrics, tracing và quy trình bảo vệ dữ liệu vận hành.

## Tài liệu tham khảo

- [Java SE 27 — Troubleshooting Guide: Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html): JFR, JMC, jcmd và các công cụ chẩn đoán liên quan.
- [JDK 27 — jcmd command reference](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): JFR.start/check/dump/stop, thông số và quyền truy cập.
- [JDK 27 — jfr command reference](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jfr.html): summary, view, print, metadata, configure, scrub.
- [Java SE 27 — jdk.jfr.Event](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/Event.html): custom events, begin/end/commit/shouldCommit.
- [Java SE 27 — jdk.jfr.Recording](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình và điều khiển recording bằng Java.
- [Java SE 27 — jdk.jfr.Configuration](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/Configuration.html): default/profile và settings.
- [Java SE 27 — RecordingFile](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc file .jfr theo sự kiện.
- [Java SE 27 — RecordingStream](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): theo dõi event stream trong JVM.
- [OpenJDK — JDK Mission Control](https://github.com/openjdk/jmc): dự án mã nguồn mở của công cụ JMC.
- [Oracle — JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): tải công cụ, tài liệu và hướng dẫn sử dụng.
- [dev.java — Configuring JFR](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): recording options, .jfc và event settings.
- [dev.java — JFR command line tool](https://dev.java/learn/jvm/jfr/tools/): các lệnh jfr và cách lọc recordings.
