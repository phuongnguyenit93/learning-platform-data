# 14.2 Phân biệt bản ghi liên tục với bản ghi có thời lượng cố định

## Mục tiêu học tập

Java Flight Recorder (JFR) ghi các sự kiện của JVM và ứng dụng, như GC, class loading, CPU sampling, thread activity, allocation samples hoặc I/O (tùy cấu hình sự kiện). Khi điều tra vấn đề runtime, quyết định **ghi liên tục** hay **ghi trong khoảng thời gian cố định** ảnh hưởng trực tiếp đến việc có giữ được các phút trước sự cố, tốn bao nhiêu tài nguyên và lúc nào nhận được tệp .jfr để phân tích.

Sau bài này, bạn có thể:

1. Giải thích vòng đời của **continuous recording** và **fixed-duration recording**, đặc biệt mối quan hệ giữa thời gian chạy, dữ liệu còn được giữ và thời điểm xuất tệp.
2. Phân biệt chính xác các tham số JFR: duration, delay, settings, disk, maxage, maxsize, filename, dumponexit; biết giới hạn và tương tác của chúng.
3. Dùng jcmd để bắt đầu, kiểm tra, dump và dừng bản ghi một cách có kiểm soát; hiểu vì sao **dump không đồng nghĩa stop**.
4. Chọn chế độ theo nhu cầu: truy nguyên sự cố hiếm xuất hiện, theo dõi dài hạn, khảo sát hotspot, kiểm tra regression hoặc thu bằng chứng ngắn quanh một thí nghiệm.
5. Tránh các lỗi như chỉ đặt filename rồi tưởng đã có file liên tục, để repository tăng không giới hạn, dùng profile lâu dài mà không đánh giá chi phí, hoặc chờ một bản ghi cố định đã kết thúc để thu sự cố xảy ra sau đó.

Phạm vi: HotSpot/OpenJDK Java 17+; cú pháp thao tác minh họa theo jcmd/JFR của JDK 21. Cấu hình và event hỗ trợ có thể khác giữa JDK/vendor. Trong mọi trường hợp, hãy xác minh bằng lệnh help trên chính JVM đích.

## 1. Hai khái niệm khác nhau: vòng đời bản ghi và thời gian giữ dữ liệu

**JFR recording** là một phiên thu sự kiện có tên/ID, cấu hình event và trạng thái vòng đời. **Tệp .jfr** là dữ liệu được xuất để lưu giữ và mở trong Java Mission Control (JMC), công cụ jfr hoặc hệ thống phân tích tương thích. Trong lúc ghi với disk=true, JFR có thể dùng **disk repository** tạm để chứa các chunk; repository không phải một tệp bằng chứng được bảo đảm lưu mãi.

Một bản ghi có ba mốc cần tách:

- **Bắt đầu thu:** khi recording chuyển sang chạy, có thể sau delay.
- **Kết thúc thu:** do thời hạn duration, thao tác stop, hoặc tiến trình/JVM kết thúc.
- **Xuất dữ liệu:** một thao tác JFR.dump trong lúc vẫn chạy, JFR.stop kèm filename, tự ghi khi hết duration có filename, hoặc hành vi dump-on-exit nếu đủ điều kiện.

Ở bản ghi liên tục, thời gian thu có thể kéo dài nhiều giờ/ngày, nhưng dữ liệu lưu lại thường chỉ là **cửa sổ gần nhất** do maxage hoặc maxsize giới hạn. Ở bản ghi có thời lượng cố định, JFR dừng thu sau duration, nhưng tệp đầu ra chỉ được tạo/ghi thành công nếu chọn cơ chế lưu phù hợp và có quyền/không gian ghi.

**Đừng nhầm thời gian recording hoạt động với khoảng dữ liệu nằm trong file dump.** Một phiên chạy 24 giờ nhưng chỉ giữ tối đa 30 phút có thể cung cấp khoảng cuối cùng trước thời điểm dump; nó không chứa toàn bộ 24 giờ.

## 2. So sánh trực tiếp

| Tiêu chí | Bản ghi liên tục (continuous) | Bản ghi có thời lượng cố định (fixed-duration) |
| --- | --- | --- |
| Cách khởi động | Không đặt duration hoặc duration=0s (trên jcmd JDK 21) | Đặt duration dương, ví dụ duration=2m |
| Khi nào ngừng | Chạy tới khi stop, JVM kết thúc hoặc có can thiệp | Tự dừng khi đủ duration; cũng có thể stop sớm |
| Mục tiêu chính | Giữ lịch sử gần nhất để điều tra sự cố khó tái hiện | Thu chi tiết trong cửa sổ biết trước |
| Dữ liệu còn giữ | Thường giới hạn bằng maxage/maxsize, loại bỏ chunk cũ | Thường giữ khoảng thời gian từ start đến stop; giới hạn retention nếu đặt có thể khiến mất phần đầu |
| Tạo tệp phân tích | JFR.dump khi có sự kiện hoặc JFR.stop với filename | filename ở lúc JFR.start để tự ghi khi kết thúc; có thể dump sớm |
| Lựa chọn settings thường hợp lý | default.jfc hoặc cấu hình nhẹ đã đo overhead | profile.jfc hoặc cấu hình chuyên sâu cần thiết |
| Chi phí vận hành | Tích lũy theo thời gian, cần retention/giám sát disk | Tập trung trong cửa sổ ngắn, cần đo CPU/volume/pause overhead |
| Điểm mạnh | Có thể giữ **dữ liệu trước khi sự cố được phát hiện** | Dễ gắn với load test, thao tác, giả thuyết, thời gian thử |
| Điểm yếu | Nếu không dump trước khi dữ liệu cũ bị đẩy ra, không thể phục hồi phần đã mất | Sự cố ngoài cửa sổ thu có thể không có bằng chứng |

**default và profile không định nghĩa continuous/fixed.** Chúng là bộ cấu hình các sự kiện và chi phí ghi. Có thể chạy fixed-duration với settings=default và continuous với settings=profile, nhưng lựa chọn đó phải có lý do và số đo overhead riêng.

## 3. Cơ chế bản ghi liên tục: “hộp đen” giữ cửa sổ gần nhất

### 3.1. Vòng đời và rolling retention

Khi JFR.start không đặt duration, mặc định duration=0s nghĩa là chạy vô thời hạn cho tới khi bị dừng/VM kết thúc. Với disk=true, các sự kiện được tổng hợp thành chunk và ghi vào repository. maxage và maxsize là giới hạn **lượng dữ liệu được giữ** trong repository cho recording đó, không phải bộ đếm để tự dừng recording.

- **maxage=1h**: chỉ giữ dữ liệu gần đây theo giới hạn tuổi; khi vượt ngưỡng, các chunk cũ có thể bị loại bỏ. Đây không phải cam kết có đúng một giờ dữ liệu nếu recording mới chạy vài phút hoặc bị ràng buộc thêm bởi maxsize.
- **maxsize=256m**: giới hạn dữ liệu ghi được giữ, theo dung lượng. Nếu tốc độ sinh sự kiện cao, 256 MiB có thể chỉ bao phủ ít phút; nếu thấp, có thể bao phủ lâu hơn.
- **Đặt cả maxage và maxsize**: tập dữ liệu còn lại bị giới hạn bởi cả hai. Cửa sổ thực tế có thể ngắn hơn maxage và lượng giữ lại được quản lý theo các chunk, không nhất thiết cắt đúng ranh giới giây/byte.
- **Không đặt cả hai** với disk=true: repository dữ liệu của recording có thể tăng về tổng dung lượng theo thời gian, cần chính sách vận hành thay vì mặc định tin rằng nó tự xoay vòng.
- **disk=false**: lưu trong các bộ đệm nhớ; tham số maxage/maxsize dùng cho dữ liệu disk không áp dụng cho chế độ này trên jcmd JDK 21. Không dùng cách này để kỳ vọng có lịch sử dài trước sự cố.

Ví dụ theo timeline, tất cả số là minh họa:

| Mốc | Continuous đang chạy, maxage=30m, maxsize đủ lớn | Dữ liệu có khả năng còn giữ |
| --- | --- | --- |
| 09:00 | Start | Gần như chưa có |
| 09:10 | Vẫn recording | 09:00–09:10 |
| 10:00 | Vẫn recording | Khoảng 09:30–10:00 |
| 10:07 | Ứng dụng có spike; dump ngay | Khoảng 09:37–10:07, gồm trước và trong spike |
| 10:45 | Không dump lần nữa | Những dữ liệu rất cũ có thể đã bị loại; snapshot lúc 10:07 nếu đã xuất là bằng chứng độc lập |

Nếu maxsize chặt hơn, cửa sổ tại 10:07 có thể ngắn hơn 30 phút. Nếu ứng dụng bị kill và chưa có dump, repository chưa chắc còn tồn tại/hợp lệ sau restart. Mốc giờ trên chỉ minh họa cơ chế, không phải dự đoán timestamp chính xác của mọi chunk JFR.

### 3.2. Continuous không đồng nghĩa “file .jfr đang mở và tự đầy mãi”

Ví dụ JFR.start có filename nhưng không có duration:

~~~bash
jcmd "$PID" JFR.start name=watch settings=default disk=true \
  maxage=30m maxsize=256m filename=/var/tmp/jfr/watch-final.jfr
~~~

Bản ghi **vẫn chạy**. filename ở start định nghĩa nơi ghi bản ghi khi recording dừng; dữ liệu liên tục có thể đang nằm trong repository tạm. Để lấy snapshot ngay mà không tắt “hộp đen”, dùng JFR.dump với một đường dẫn đầu ra khác. Đừng đợi đến stop nếu muốn giữ bằng chứng tại một sự cố đã xảy ra.

### 3.3. Khi nào chọn continuous?

Phù hợp khi:

- Sự cố latency, CPU, GC hoặc contention xuất hiện ngẫu nhiên và thường được phát hiện **sau** khi đã xảy ra.
- Cần ít nhất vài phút lịch sử trước/sau alert để xác định cơ chế.
- Dịch vụ chạy dài, muốn có baseline telemetry và khả năng dump theo incident.
- Có giám sát retention, dung lượng disk, quyền ghi, quy trình xuất/thu hồi dữ liệu và ngân sách overhead rõ ràng.

**Chi phí cần đánh giá:** event selection, event stack traces, sampling rate, size của chunk, CPU/I/O, repository space và tác động lên chính workload. Settings=default thường là khởi điểm nhẹ cho ghi liên tục. Đừng tự tuyên bố “JFR overhead bằng 0”; chỉ đo overhead thực tế với tải đại diện.

## 4. Cơ chế fixed-duration: ghi có điểm bắt đầu và kết thúc

Khi chỉ định duration=2m, recording được lên lịch kết thúc sau khoảng 2 phút kể từ khi bắt đầu thu. Nếu có delay, JVM chờ delay rồi mới ghi; delay không phải dữ liệu “trước thời điểm start”. Khi thời lượng đạt, recording kết thúc; nếu có filename phù hợp, dữ liệu được viết ra tệp đích theo cơ chế của lệnh.

Ví dụ:

~~~bash
jcmd "$PID" JFR.start name=cpu_probe settings=profile \
  disk=true duration=2m filename=/var/tmp/jfr/cpu-probe-2m.jfr
~~~

Giải thích:

1. Lệnh bắt đầu phiên cpu_probe với các event trong profile.jfc.
2. Phiên thu kéo dài khoảng 2 phút, trừ khi bị stop sớm/JVM dừng.
3. filename là đích xuất tệp .jfr khi phiên kết thúc; ngay sau JFR.start tệp có thể **chưa có hoặc chưa hoàn chỉnh**.
4. Sau khi kết thúc thành công, dùng jfr summary/jfr print hoặc JMC để kiểm tra có dữ liệu trong khoảng mục tiêu.

Fixed-duration phù hợp để:

- Lấy mẫu ngắn khi latency tăng ổn định và biết thời gian tái hiện.
- Đo request mix cụ thể sau warm-up trong load test.
- Điều tra CPU methods, allocation hotspots, locks/I/O trong đoạn benchmark có kiểm soát.
- So sánh hai phiên baseline và candidate cùng độ dài, cùng event settings và tải tương đương.

**Lưu ý:** duration chỉ quy định vòng đời, không đảm bảo mọi event đều được bật, mọi stack đều được ghi, hay không có dropped events. Một recording “2 phút” vẫn có thể chỉ phản ánh tải 1 phút nếu tác nhân cần khảo sát xuất hiện muộn.

### 4.1. Fixed-duration cũng có thể mất dữ liệu đầu cửa sổ

Nếu đặt duration=30m nhưng maxage=5m hoặc maxsize quá nhỏ, dữ liệu cũ có thể bị loại trong lúc recording còn chạy. Vì vậy câu “fixed duration thì chắc chắn giữ đủ toàn bộ khoảng” chỉ đúng nếu cấu hình giữ dữ liệu, dung lượng và quá trình xuất đủ đáp ứng.

Muốn thu trọn khoảng, cân đối retention hoặc không đặt cap nhỏ hơn nhu cầu, và bảo đảm disk/container có đủ chỗ. Với profile nhiều event, khối lượng có thể tăng đáng kể. Đừng đặt giá trị “vô hạn” trên production chỉ vì mong file đầy đủ: cần có ngân sách và cơ chế chống đầy disk.

## 5. Tham số quan trọng và những nhầm lẫn cần tránh

| Tùy chọn | Ý nghĩa đúng trên jcmd JDK 21 | Sai lầm phổ biến |
| --- | --- | --- |
| duration=2m | Tự ngừng recording sau khoảng 2 phút | Nhầm là chỉ giữ 2 phút cuối nhưng vẫn chạy mãi |
| duration=0s hoặc bỏ duration | Recording không tự hết hạn theo thời gian | Hiểu 0s là dừng ngay |
| delay=15s | Chờ 15 giây trước khi bắt đầu thu | Nghĩ delay lấy được lịch sử 15 giây trước |
| settings=default | Dùng cấu hình .jfc nhẹ, thiên về liên tục | Tưởng default là một loại recording riêng |
| settings=profile | Bật tập sự kiện chuyên sâu hơn, có thể tốn hơn | Chạy suốt nhiều ngày mà không đo overhead |
| disk=true | Ghi dữ liệu ra disk repository trong quá trình recording | Nghĩ disk=true đã tạo ngay tệp bằng chứng cuối cùng |
| maxage=30m | Tối đa thời gian dữ liệu được giữ trên disk cho recording | Nhầm là tự stop sau 30 phút |
| maxsize=256m | Giới hạn dung lượng dữ liệu trên disk được giữ | Nhầm là giới hạn kích thước heap/JVM hoặc đảm bảo đúng 30 phút dữ liệu |
| filename=/path/file.jfr ở JFR.start | Đích ghi khi recording dừng | Nghĩ tệp đã đầy đủ ngay khi start |
| dumponexit=true | Cố ghi bản ghi khi JVM shutdown theo cơ chế được hỗ trợ | Tin rằng SIGKILL/OOMKilled chắc chắn tạo file |
| JFR.dump name=... filename=... | Xuất snapshot, recording đang chạy **tiếp tục chạy** | Tưởng dump cũng tắt recording |
| JFR.stop name=... filename=... | Dừng và ghi tệp đích | Stop không kèm filename rồi mặc định tin đã giữ dữ liệu |

maxage và maxsize trên JFR.start hợp lệ khi disk=true. maxsize phải không nhỏ hơn kích thước chunk tối đa mà JFR.configure quy định. Một đơn vị như m trong duration là **phút**, còn m trong maxsize là **MiB/MB theo quy tắc parser của JVM**; luôn đọc ngữ cảnh của option.

### 5.1. Bộ nhớ JFR, repository và tệp artifact là ba thành phần khác nhau

- **Bộ đệm trong JVM** lưu sự kiện trước khi flush; không phải toàn bộ lịch sử của continuous.
- **Disk repository** gồm dữ liệu tạm/recording chunks mà JVM dùng trong lúc ghi; location cấu hình bằng JFR.configure repositorypath (tùy version) và cần filesystem ổn định, dung lượng đủ.
- **Tệp được xuất (.jfr)** được tạo bằng dump/stop/hoàn tất duration; đó mới là artifact cần bảo toàn và đưa vào kho sự cố.

Đừng dựa vào việc copy thủ công các chunk đang mở trong repository như một phương thức backup chuẩn. JFR có thể xóa chunk cũ theo retention hoặc dọn repository khi JVM exit. Kế hoạch điều tra cần thao tác xuất có kiểm chứng.

## 6. Thực hành A: recording liên tục và dump sau cảnh báo

Đây là chuỗi lệnh minh họa Linux shell, Java 17+/JDK 21; lệnh tương tác với JVM nên chỉ chạy khi đúng service, PID và quyền. Trên production cần xác nhận lệnh attach được cho phép, nơi lưu log không chứa dữ liệu công khai và đủ không gian.

### 6.1. Chuẩn bị đúng PID và nơi lưu evidence

~~~bash
java -version
jcmd -l
PID=12345               # Thay PID thật; không dùng 12345 trên hệ thống thực
mkdir -p /var/tmp/jfr    # Thư mục phải ghi được bởi process Java đích
jcmd "$PID" help JFR.start
jcmd "$PID" help JFR.dump
~~~

Chạy jcmd từ cùng máy/container phù hợp với JVM và có effective user/group đáp ứng yêu cầu attach. Tên file chỉ có ý nghĩa với filesystem theo ngữ cảnh của process đích; kiểm tra mount/volume/permissions. Không nhầm PID trong namespace host với PID nhìn từ container.

### 6.2. Bắt đầu continuous một lần

~~~bash
jcmd "$PID" JFR.start name=service_watch \
  settings=default disk=true maxage=1h maxsize=256m
jcmd "$PID" JFR.check name=service_watch
~~~

Lệnh start không có duration nên recording tiếp tục. Theo dõi JFR.check để xác minh đúng tên/ID và trạng thái. Khi chạy liên tục, lưu timestamp start, Java version, cấu hình event, maxage/maxsize và mức disk thực tế. Không start thêm nhiều recording cùng tên mỗi lần alert; kiểm tra phiên hiện hữu trước.

### 6.3. Khi alert phát sinh, dump cửa sổ gần nhất

~~~bash
jcmd "$PID" JFR.dump name=service_watch \
  filename=/var/tmp/jfr/watch-incident.jfr maxage=15m
jcmd "$PID" JFR.check name=service_watch
jfr summary /var/tmp/jfr/watch-incident.jfr
~~~

JFR.dump tạo snapshot dữ liệu còn tồn tại, với tùy chọn giới hạn đoạn xuất (ở đây tối đa 15 phút gần nhất). Bản ghi service_watch **vẫn hoạt động** sau dump; một alert sau đó có thể yêu cầu snapshot thứ hai. Nếu cần phân tích khoảng trước/sau spike, hãy dump đủ gần thời điểm có sự kiện; đừng chờ đến khi rolling retention xóa dữ liệu cũ.

Trong cùng incident, giữ file riêng theo timestamp và instance để tránh ghi trùng tên. Đặt tên watch-incident.jfr ở đây chỉ là minh họa; thực tế nên có time/PID/instance trong tên và hồ sơ vận hành.

### 6.4. Khi thực sự muốn chấm dứt continuous

~~~bash
jcmd "$PID" JFR.stop name=service_watch \
  filename=/var/tmp/jfr/watch-final.jfr
~~~

Stop là thao tác thay đổi trạng thái: sau đó service_watch không còn thu sự kiện mới. Nếu stop mà không có filename, có nguy cơ dữ liệu chưa dump bị bỏ đi theo hành vi của lệnh; khi cần artifact hãy chỉ rõ filename và xác nhận file hoàn tất. Không dừng continuous chỉ để xem một snapshot nếu vẫn muốn giữ khả năng quan sát cho sự cố tiếp theo.

**Phân biệt ba kết quả:**

- JFR.check: kiểm tra phiên đang hoạt động (không xuất file).
- JFR.dump: xuất bản sao dữ liệu đang giữ; phiên vẫn hoạt động.
- JFR.stop: kết thúc phiên, có thể xuất file nếu chỉ rõ filename.

## 7. Thực hành B: fixed-duration cho thí nghiệm đã hẹn

Ví dụ muốn đo 2 phút sau khi service đã warm-up, trên cùng PID giả định và thư mục đã tạo:

~~~bash
jcmd "$PID" JFR.start name=load_test_2m \
  settings=profile disk=true duration=2m \
  filename=/var/tmp/jfr/load-test-2m.jfr
jcmd "$PID" JFR.check name=load_test_2m
~~~

Sau khi duration kết thúc và quá trình xuất hoàn tất:

~~~bash
jfr summary /var/tmp/jfr/load-test-2m.jfr
jfr print --events jdk.GarbageCollection /var/tmp/jfr/load-test-2m.jfr
~~~

Lệnh jfr print là ví dụ lọc một loại event, chỉ in những event thực sự có trong file. Không có event phù hợp không chứng minh hệ thống không có GC; cần kiểm tra cấu hình event và khoảng ghi. Thời gian chờ ở ví dụ là điều kiện quan sát, **không** dùng lệnh blocking tùy ý trong production.

Nếu tải chỉ bắt đầu sau 1 phút và recording kết thúc sau 2 phút, file chỉ chứa một phút thực nghiệm hữu ích. Cần thiết kế đồng bộ với warm-up, ổn định workload, điểm bắt đầu/stop và mốc log ứng dụng. Có thể dùng delay=15s để hẹn khởi động nhưng phải tính delay vào lịch thử.

### 7.1. Có thể dump fixed-duration trước khi hết hạn

~~~bash
jcmd "$PID" JFR.dump name=load_test_2m \
  filename=/var/tmp/jfr/load-test-interim.jfr
~~~

Nếu đang chạy, lệnh này tạo snapshot trung gian và recording vẫn tiếp tục đến duration hoặc stop. Nếu sự cố nghiêm trọng xảy ra trước khi thời lượng kết thúc, snapshot sớm giúp giữ evidence; các event sau thời điểm dump không thể tự xuất hiện trong file snapshot cũ.

### 7.2. Khi nào cần chủ động stop sớm?

Có thể dùng:

~~~bash
jcmd "$PID" JFR.stop name=load_test_2m \
  filename=/var/tmp/jfr/load-test-early-stop.jfr
~~~

Chỉ khi recording **còn đang chạy** và muốn dừng sớm; nếu đã tự dừng theo duration, JFR.stop có thể báo không có recording active. Đừng thực thi cả thao tác stop sớm lẫn chờ file tự kết thúc như thể hai hành động bắt buộc của một quy trình.

## 8. Thực hành C: cấu hình JFR ngay từ khi khởi động JVM

Không phải lúc nào bạn cũng attach được sau khi có incident. Startup option cho phép thu dữ liệu từ khi ứng dụng khởi động, hữu ích cho slow startup hoặc các incident xảy ra ngay khi traffic bắt đầu.

### 8.1. Continuous từ startup

~~~bash
java -XX:StartFlightRecording=name=startup_watch,settings=default,disk=true,maxage=1h,maxsize=256m \
  -jar app.jar
~~~

Đây là cấu hình startup có recording không giới hạn duration, giữ rolling window. app.jar chỉ là tên ví dụ; cần đường dẫn thực và lệnh service hiện hành. Hãy dự phòng repository space và cơ chế JFR.dump để xuất bằng chứng.

### 8.2. Fixed-duration từ startup

~~~bash
java -XX:StartFlightRecording=name=startup_probe,settings=profile,duration=2m,filename=/var/tmp/jfr/startup-probe.jfr \
  -jar app.jar
~~~

Bản ghi kết thúc sau khoảng hai phút thu, rồi ghi file nếu JVM còn hoạt động và có quyền/dung lượng ghi. Đây là cách thu warm-up/startup có thời hạn; nếu lỗi xảy ra ở phút thứ 8 thì recording này không thể chứa dữ liệu lúc đó.

### 8.3. Vai trò của dumponexit

Có thể đặt dumponexit=true để JVM thử ghi recording khi shutdown; tuy nhiên **shutdown sạch khác với kill đột ngột**. SIGKILL, OOMKilled, mất máy, lỗi filesystem hoặc crash có thể ngăn JVM hoàn tất xuất file. Với sự cố cần bằng chứng chắc chắn hơn, continuous + dump định kỳ/theo alert được kiểm chứng là chiến lược tốt hơn việc chỉ tin vào dumponexit.

## 9. Thực hành D: Java 17+ API minh họa hai chế độ

Ngoài jcmd, Java có API trong module jdk.jfr để quản lý Recording. Chương trình dưới đây độc lập, minh họa sự khác nhau giữa **lấy snapshot mà vẫn recording** và **tự ngừng sau duration**. Ví dụ tạo tệp trong thư mục làm việc hiện tại; chạy ở môi trường có JDK đầy đủ và quyền ghi file.

Tạo tệp **JfrModesDemo.java**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;

public class JfrModesDemo {
    public static void main(String[] args) throws Exception {
        try (Recording continuous =
                     new Recording(Configuration.getConfiguration("default"))) {
            continuous.setName("continuous-demo");
            continuous.setToDisk(true);
            continuous.setMaxAge(Duration.ofMinutes(10));
            continuous.setMaxSize(128L * 1024 * 1024);
            continuous.start();

            Thread.sleep(1200);
            continuous.dump(Path.of("continuous-snapshot.jfr"));
            System.out.println("Continuous snapshot saved");
        }

        try (Recording fixed =
                     new Recording(Configuration.getConfiguration("profile"))) {
            fixed.setName("fixed-demo");
            fixed.setToDisk(true);
            fixed.setDuration(Duration.ofSeconds(3));
            fixed.setDestination(Path.of("fixed-result.jfr"));
            fixed.start();

            while (fixed.getState() == RecordingState.RUNNING) {
                Thread.sleep(100);
            }
            System.out.println("Fixed recording finished");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --add-modules jdk.jfr JfrModesDemo.java
java --add-modules jdk.jfr JfrModesDemo
jfr summary continuous-snapshot.jfr
jfr summary fixed-result.jfr
~~~

Phần stdout do mã System.out.println tạo ra khi cả hai phiên và ghi file thành công:

~~~text
Continuous snapshot saved
Fixed recording finished
~~~

Hai lệnh jfr summary tiếp theo in thêm **báo cáo thay đổi theo môi trường**, nên không mô phỏng stdout của chúng. Hai tệp .jfr là artifact có thật được tạo bởi chương trình.

Giải thích hành vi:

- Continuous bắt đầu mà không đặt duration; sau khoảng 1,2 giây, dump xuất snapshot. Đóng Recording bằng try-with-resources kết thúc ví dụ; ở dịch vụ thật, thường giữ phiên continuous chạy dài hơn nhiều.
- Fixed dùng setDuration(3 giây) và setDestination. Nó tự kết thúc theo thời gian; vòng lặp chờ tới khi RecordingState không còn RUNNING. Vì có destination, kết quả được ghi/đóng theo cơ chế của API.
- Số giây rất ngắn chỉ giúp thử API, **không phải khoảng thu hữu ích để kết luận performance**. Trong sản phẩm cần cân nhắc event configuration, overhead, permissions, chu kỳ ghi/đọc và lifecycle thay vì copy nguyên thời lượng minh họa.

**Không lẫn hai API:** setDuration là đặt giới hạn phiên thu; setMaxAge và setMaxSize là giới hạn dữ liệu giữ. dump(Path) xuất bản sao mà không ngầm thay duration. Phương thức close trên recording thử nghiệm dọn tài nguyên, không tương đương “đã chắc chắn lưu file cuối” nếu chưa dump/setDestination thành công.

## 10. Phân biệt dữ liệu được ghi với dữ liệu đủ để kết luận

Chế độ thu chỉ trả lời **khi nào** và **giữ bao lâu**. Chất lượng evidence còn phụ thuộc các yếu tố:

### 10.1. Event settings

- **default.jfc**: tập sự kiện thiên về quan sát thường xuyên, chi phí thấp tương đối; phù hợp làm baseline continuous.
- **profile.jfc**: thu nhiều loại dữ liệu chuyên sâu hơn, thường thích hợp cửa sổ ngắn; kiểm tra CPU/size overhead thực tế.
- **Custom .jfc**: chọn event, threshold, stack traces, sampling period theo giả thuyết; lập hồ sơ cấu hình và version để so sánh các phiên.

Nếu cần allocation profiling, contention hoặc một loại I/O event cụ thể mà cấu hình chưa bật, việc kéo dài duration không tự làm xuất hiện loại event bị tắt. Trước và sau thí nghiệm, kiểm tra JFR.check verbose nếu được hỗ trợ và báo cáo jfr summary để biết file chứa những event nào.

### 10.2. Sampling và tính đại diện

JFR có thể ghi cả event chính xác lẫn event được lấy mẫu. “Không tìm thấy CPU sample của method X” chưa đủ kết luận X không chạy. Hãy kiểm tra khoảng ghi, tải, số lượng sample, threshold, event settings và stack truncation. Tránh diễn giải 20 giây startup như steady-state hiệu suất của service nhiều giờ.

### 10.3. Đồng bộ timeline

Khi điều tra p99, GC, CPU spike:

- Đồng bộ timestamp giữa JFR, application logs, APM, system metrics; dùng cùng timezone/UTC khi so sánh.
- Ghi thời điểm khởi động và kết thúc recording, phiên bản build, JDK, PID/pod, cấu hình JFR, CPU/memory limits.
- Gắn marker từ load test/incident vào timeline; muốn phân tích nguyên nhân nên giữ cả các phút **trước** spike.
- Tránh so bản baseline 20 phút yên tĩnh với profile 2 phút lúc peak load rồi kết luận chỉ vì event count tăng.

### 10.4. Retention không bảo đảm lấy được toàn bộ sự cố

Continuous với maxage=30m có thể mất phần đầu nếu incident kéo dài 2 giờ và dump muộn. Fixed-duration 2m không bắt được sự cố hiếm xảy ra ở phút thứ 20. Khi kịch bản yêu cầu cả dữ liệu trước và sau sự cố, có thể phối hợp một continuous nhẹ và một fixed/profile khi nhận alert, nhưng phải kiểm soát tổng overhead; nhiều recording chia sẻ hạ tầng JFR chứ không hoàn toàn độc lập về chi phí.

## 11. Chọn chế độ theo tình huống thực tế

| Câu hỏi điều tra | Lựa chọn khởi đầu | Lý do và cách thu đúng |
| --- | --- | --- |
| “Hôm qua p99 tăng ngẫu nhiên nhưng không tái hiện được.” | Continuous nhẹ, đủ retention; dump ngay khi alert | Cần lịch sử trước khi con người phát hiện |
| “Chạy load test 5 phút để so CPU hotspot trước/sau sửa code.” | Fixed-duration, profile có kiểm soát | Có cửa sổ và tải xác định; so event settings tương đồng |
| “Sự cố xuất hiện sau vài giờ uptime.” | Continuous từ startup, rolling window đủ dài | Fixed 2 phút lúc khởi động thường bỏ lỡ |
| “Muốn đo startup chậm trong 90 giây đầu.” | Fixed từ startup | Cửa sổ trùng lifecycle startup, dễ phân tích |
| “Muốn điều tra GC pauses lúc spike chưa biết trước.” | Continuous + GC logs/APM + dump khi spike | Snapshot giữ vài phút trước/sau alert |
| “Chỉ cần tăng chi tiết sampling trong 3 phút hiện tại.” | Fixed/profile song song với continuous nhẹ nếu ngân sách cho phép | Không cần tăng overhead của bản continuous cả ngày |
| “Service có thể bị OOMKilled bất ngờ.” | Continuous với dump chủ động/định kỳ được kiểm chứng | dumponexit không bảo đảm tồn tại sau SIGKILL |
| “Cần ghi mọi sự kiện suốt một tuần và giữ đầy đủ.” | Thiết kế ngân sách/archival riêng; phân đoạn kỳ ghi/export | Một continuous rolling đơn lẻ không bảo đảm giữ trọn tuần |

### Tình huống minh họa 1: dump quá muộn

Cấu hình continuous maxage=15m, maxsize đủ lớn, alert phát hiện lúc 10:00 nhưng người trực đến 10:40 mới dump. Lúc này phần dữ liệu liên quan 09:50–10:00 có thể đã bị loại. Không phải JFR “mất ngẫu nhiên”; retention đang hoạt động đúng chính sách. Cần điều chỉnh cửa sổ lưu theo thời gian phát hiện và điều tra thực tế, hoặc tự động dump nhanh khi alert và bảo vệ artifact.

### Tình huống minh họa 2: fixed-duration có dữ liệu nhưng thiếu hiện tượng

Thử nghiệm bắt đầu JFR.fixed ở 14:00 cho duration=2m; load test chạy từ 14:01:50 đến 14:05. File chỉ có khoảng 10 giây tải thực trong kỳ recording. CPU hotspot không xuất hiện vì phần lớn tải diễn ra sau khi recording kết thúc. Sửa quy trình đồng bộ: warm-up xong mới start fixed, phát marker hoặc delay phù hợp, rồi chạy tải trong cửa sổ.

### Tình huống minh họa 3: profile kéo dài và làm thay đổi hành vi ứng dụng

Team bật settings=profile liên tục trong giờ peak trên service nhạy tail latency, không kiểm tra CPU/disk usage. Các event và stack traces có thể tăng overhead hoặc kích thước repository, khiến phép đo khác baseline. Thiết kế lại: continuous default nhẹ, fixed profile ngắn và so overhead bằng A/B có kiểm soát. **Cấu hình recording có thể là một biến trong thí nghiệm**.

## 12. Vận hành an toàn: nơi lưu, dung lượng, bảo mật và xác minh

### 12.1. Dung lượng và retention

Trước khi bật ghi dài hạn:

1. Ước lượng tốc độ sinh JFR event theo peak workload, không chỉ traffic trung bình.
2. Chọn maxage và maxsize sao cho khớp thời gian cần truy nguyên và disk budget.
3. Kiểm tra repositorypath, quyền ghi, size của chunk và dung lượng còn lại; maxsize phải hợp lệ với kích thước chunk tối đa.
4. Có ngưỡng cảnh báo disk/IO, chính sách dọn các artifact .jfr đã dump và nơi lưu ngoài container khi cần.
5. Xác nhận bằng một vòng chạy/dump/read: file có thể mở, có timestamp/event mong đợi, retention hoạt động như thiết kế.

**File .jfr cuối cùng và repository cùng tiêu thụ bộ nhớ lưu trữ** trong những thời điểm nhất định; đừng tính riêng maxsize rồi mặc định disk không thể vượt budget đó. Nhiều recording, metadata, file dump đã xuất và các log khác đều góp phần vào disk usage.

### 12.2. Đường dẫn và permissions

Đường dẫn filename từ jcmd có thể được JVM đích diễn giải trên filesystem của nó. Nếu đang attach từ host vào container hoặc dùng container có mount khác, đường dẫn tồn tại ở shell vận hành chưa chắc tồn tại/ghi được với JVM. Tệp output có thể bị giữ trong filesystem ephemeral sau khi pod restart, vì vậy có thể cần volume/collector riêng. Tránh tên file trùng và xác minh kích thước/timestamp sau khi xuất.

### 12.3. Bảo vệ dữ liệu trong recording

JFR có thể chứa class names, thread names, stack traces, file paths, endpoint patterns, metadata môi trường, event payload từ code tùy chỉnh và thông tin vận hành nhạy cảm. Hạn chế quyền đọc/chia sẻ, có retention cho artifact và tránh upload lên hệ thống công khai. Không dùng jfr print để phát tán hàng nghìn sự kiện ra console không được kiểm soát.

### 12.4. Kiểm tra nhanh file đã dùng được

~~~bash
jfr summary /var/tmp/jfr/watch-incident.jfr
jfr metadata /var/tmp/jfr/watch-incident.jfr
~~~

jfr summary giúp đọc khoảng thời gian và số lượng event đã ghi; jfr metadata mô tả các loại sự kiện trong metadata file. Kiểm tra **event thực tế** trong summary/print, không suy luận rằng metadata event type có nghĩa event đó đã xuất hiện. Nếu không thấy đúng khoảng hoặc event, xem lại thời gian, settings, rotation/retention, đường dẫn và quyền ghi.

## 13. Troubleshooting những lỗi thường gặp

| Triệu chứng | Điều cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| Không tìm thấy PID trong jcmd -l | Process/container namespace, quyền attach, JDK/JRE image | Chọn đúng PID cùng môi trường, đúng user và JDK tools |
| JFR.start báo trùng tên hoặc recording không đúng | JFR.check toàn bộ recording | Dùng tên duy nhất hoặc thao tác đúng recording đã chạy |
| JFR.dump báo không có recording | Recording đã kết thúc, PID đổi, JFR không khởi động | Xác minh trạng thái hiện tại; không giả định recording cũ sau restart |
| Start thành công nhưng không thấy file ngay | filename tại JFR.start gắn với stop; session chưa kết thúc | Dùng JFR.dump để lấy snapshot hoặc đợi duration kết thúc |
| maxage=1h nhưng chỉ thấy vài phút | maxsize nhỏ, vừa mới start, tốc độ event cao, một số chunk bị loại | Đọc khoảng thực từ file, kiểm tra retention và event rate |
| Repository đầy disk | maxage/maxsize thiếu hoặc quá lớn, nhiều recording/dump | Điều chỉnh chính sách retention có số liệu và dọn artifact theo quy trình |
| File .jfr không mở được | File chưa ghi xong, đường dẫn sai, bị cắt/truncated, thiếu quyền | Xác minh hoàn tất dump, file size và jfr summary |
| Không có CPU/GC event kỳ vọng | Settings không bật loại event, sampling/threshold, thu sai khoảng | Kiểm tra .jfc, jfr summary/print và timeline tải |
| Đã stop nhưng không thấy file | JFR.stop không có filename, sai path/permissions | Khi cần lưu, chỉ định filename và xác minh output |
| Không có dump sau OOMKilled | SIGKILL không cho JVM chạy shutdown hook | Thu evidence chủ động trước sự cố; điều tra OS/container events |
| Fixed-duration mất phần đầu dù đủ duration | maxage/maxsize hạn chế dữ liệu giữ | Tăng retention có cơ sở hoặc giảm duration phù hợp ngân sách |
| JFR làm CPU/I/O tăng | profile events quá dày, stack traces, recording song song | Dùng default nhẹ, giới hạn thời lượng của profiling và đo overhead |

## 14. Checklist trước khi chọn và chạy

- [ ] Tôi biết câu hỏi cần trả lời: “đã xảy ra bất ngờ” hay “sắp thử nghiệm có kiểm soát”.
- [ ] Tôi cần lịch sử **trước alert**, hay chỉ cần dữ liệu trong một cửa sổ đã hẹn?
- [ ] Tôi xác định thời gian recording chạy, thời gian dữ liệu được giữ và thời điểm xuất file là ba vấn đề riêng.
- [ ] Tôi chọn settings=default/profile/custom theo event cần xem, có đo/giới hạn overhead.
- [ ] Nếu continuous: đặt disk/retention phù hợp, biết khi nào JFR.dump và cơ chế tự động lấy evidence.
- [ ] Nếu fixed: đặt duration phù hợp warm-up/load và filename có quyền ghi; không để retention cắt mất cửa sổ cần phân tích.
- [ ] Tôi biết JFR.dump **không dừng**, còn JFR.stop **dừng** recording.
- [ ] Tôi có kế hoạch tránh mất dữ liệu do OOMKilled, pod restart, disk full, sai container path.
- [ ] Tôi đã xác minh JDK/vendor/PID, recording name và event settings trên process thực tế.
- [ ] Tôi có phép kiểm tra output bằng jfr summary hoặc JMC, và tệp chứa đúng khoảng thời gian cần nghiên cứu.
- [ ] Tôi có naming, quyền truy cập, retention và chính sách xử lý dữ liệu nhạy cảm cho artifact .jfr.

## 15. Kết luận

**Continuous recording** dành cho câu hỏi “trước khi sự cố được phát hiện đã xảy ra điều gì?”: phiên thu có thể chạy vô thời hạn, giữ rolling window, và thường **dump khi cần nhưng tiếp tục thu**.

**Fixed-duration recording** dành cho câu hỏi “trong khoảng thực nghiệm xác định này JVM làm gì?”: phiên được đặt duration dương, tự kết thúc và có thể ghi tệp khi hết hạn.

Không có chế độ nào mặc định đầy đủ hơn chế độ còn lại. Lựa chọn tốt là chế độ cung cấp **đúng dữ liệu, đúng khoảng thời gian, đủ event, với overhead và giới hạn lưu trữ chấp nhận được**, cùng một quy trình xác minh file .jfr thực sự có thể phân tích.

### Tài liệu tham khảo

- Oracle JDK 21, jcmd (JFR.start, JFR.check, JFR.dump, JFR.stop): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21, jdk.jfr.Recording API: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Java Flight Recorder API Programmer’s Guide, Flight Recorder Configurations: https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html
- Java 21 JFR command-line tool: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
