# Đo hiệu quả trên JDK triển khai với tải thực tế trước khi điều chỉnh cấu hình G1

G1 Region Pinning được đưa vào JDK 22 qua JEP 423. Thay đổi này cho phép G1 tiếp tục thu gom heap trong khi một thread đang ở JNI critical region và giữ tham chiếu đến đối tượng Java. G1 giữ các đối tượng cần thiết ở vị trí hiện tại, đồng thời thu gom những vùng heap khác.

Tính năng này vẫn có trong G1 trên JDK hiện đại, bao gồm JDK 25 LTS và JDK 27. Đây là hành vi tự động của collector, không phải API Java và không có cờ riêng để bật hoặc tắt region pinning. Vì vậy, cách đánh giá phù hợp là đo ứng dụng trên đúng JDK và môi trường triển khai, quan sát GC cùng độ trễ thực tế, sau đó mới quyết định có cần thay đổi cấu hình G1 hay không.

## 1. JEP 423 thay đổi điều gì?

G1 chia Java heap thành nhiều **region**. Khi thu gom, G1 thường di chuyển các đối tượng còn sống ra khỏi những region được chọn để thu hồi, rồi dùng lại vùng nhớ đó.

Một số thư viện native dùng JNI để lấy con trỏ tới dữ liệu của mảng hoặc chuỗi Java. Ví dụ, cặp hàm **GetPrimitiveArrayCritical(...)** và **ReleasePrimitiveArrayCritical(...)** tạo một JNI critical region. Nếu JVM trả về con trỏ trực tiếp tới dữ liệu trên heap, đối tượng phải được giữ ở vị trí hợp lệ cho tới khi native code release con trỏ; JVM cũng có thể trả về một bản sao thay vì pin đối tượng gốc.

Trước region pinning, một số đường đi của G1 phải trì hoãn hoặc không thể thực hiện thu gom khi critical region đang hoạt động. JEP 423 thay đổi cách G1 xử lý tình huống này:

1. Thread native vẫn giữ được tham chiếu tới đối tượng Java trong critical region.
2. G1 có thể tiếp tục chạy garbage collection thay vì phải chờ toàn bộ critical region kết thúc.
3. Region chứa đối tượng đang được native code sử dụng được giữ nguyên vị trí để con trỏ vẫn hợp lệ.
4. G1 có thể thu gom các region khác trong heap.
5. Khi vùng bị pin không còn bị giữ, G1 có thể đưa region đã gặp evacuation failure trở lại danh sách ứng viên để thu gom ở các chu kỳ sau.

Region pinning giúp giảm sự cản trở giữa JNI critical region và hoạt động GC. Nó không biến G1 thành real-time collector và cũng không bảo đảm mọi pause đều ngắn hơn.

### Phạm vi tác động

| Tình huống | Ý nghĩa của region pinning |
|---|---|
| Ứng dụng có JNI critical region dùng **GetPrimitiveArrayCritical** hoặc hàm tương tự và giữ con trỏ tới dữ liệu heap gốc | G1 có thể tiếp tục thu gom các region khác trong khi đối tượng được native code sử dụng vẫn ở đúng vị trí |
| Ứng dụng không dùng JNI critical region | Không có đường thực thi này để tạo ra lợi ích trực tiếp từ JEP 423 |
| Ứng dụng chỉ dùng Java heap và các thao tác Java thông thường | Hành vi pinning không phải lý do để tự thay đổi cấu hình G1 |
| Ứng dụng dùng FFM để thao tác native memory | Không nên mặc định FFM đang pin Java heap; cần xác định đường gọi native thực tế của thư viện |

JEP 423 là thay đổi bên trong G1. Ứng dụng không cần sửa mã Java hoặc thêm tùy chọn JVM để sử dụng tính năng này khi đang chạy bằng G1.

## 2. Region pinning không thay đổi hợp đồng JNI critical region

Region pinning không loại bỏ các giới hạn của JNI. Theo JNI specification, sau khi gọi **GetPrimitiveArrayCritical(...)**, native code cần gọi hàm release tương ứng trong thời gian ngắn. Trong critical region, native code không được gọi các JNI function khác hoặc system call có thể khiến thread hiện tại block để chờ một Java thread khác.

Ví dụ các hàm cần đi theo cặp:

~~~c
jboolean isCopy = JNI_FALSE;

jint *values = (*env)->GetPrimitiveArrayCritical(
    env, array, &isCopy
);

if (values == NULL) {
    return; // JVM có thể đã ném OutOfMemoryError
}

/* Chỉ xử lý dữ liệu ngắn gọn, không gọi JNI khác,
   không chờ I/O hoặc thread Java khác. */

(*env)->ReleasePrimitiveArrayCritical(
    env, array, values, 0
);
~~~

Đoạn mã chỉ minh họa vòng đời lấy và trả con trỏ. Nếu truyền **isCopy**, JNI cho biết JVM trả về bản sao hay vùng dữ liệu gốc; không được mặc định con trỏ luôn trỏ trực tiếp vào mảng trên heap. Mã native thực tế phải xử lý lỗi, kích thước mảng và chế độ release phù hợp.

Các nguyên tắc khi rà soát thư viện JNI:

- Release con trỏ ngay sau khi hoàn thành phần xử lý cần truy cập trực tiếp dữ liệu.
- Không giữ con trỏ qua thao tác I/O, chờ lock, chờ thread hoặc công việc có thời gian không xác định.
- Không gọi JNI function khác trong critical region.
- Kiểm tra giá trị con trỏ trả về; JVM có thể không cấp được vùng truy cập.
- Không lưu con trỏ sau khi gọi hàm release tương ứng.

G1 có thể thu gom các region khác trong lúc đối tượng được pin vẫn còn được sử dụng. Điều đó không cho phép native code giữ con trỏ lâu hơn hoặc bỏ qua quy tắc JNI.

Tham khảo: [JNI Specification — GetPrimitiveArrayCritical và ReleasePrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html).

## 3. Xác định collector thực sự trên JDK triển khai

Không nên dựa vào cấu hình máy phát triển để suy ra collector trong production. Cần xác định JDK, bản phân phối, tài nguyên CPU/RAM, container limit và collector thực sự được JVM chọn.

Tính đến ngày 25/11/2026, JDK 27 đã GA ngày 15/09/2026:

- **JDK 27** là feature release mới nhất. Theo JEP 523, G1 là collector mặc định trong mọi môi trường, kể cả môi trường tài nguyên hạn chế.
- **JDK 25** là LTS mới nhất. Việc chọn collector mặc định có thể phụ thuộc môi trường; trong một số môi trường hạn chế, JVM có thể chọn Serial GC.
- Nếu cần bảo đảm phép đo đang chạy bằng G1 trên nhiều môi trường hoặc nhiều phiên bản JDK, có thể chỉ định rõ **-XX:+UseG1GC**.

Ví dụ kiểm tra phiên bản runtime:

~~~shell
java -version
~~~

Để xem các cờ JVM đang có hiệu lực của một tiến trình:

~~~shell
jcmd <pid> VM.flags -all
~~~

Có thể kiểm tra giá trị **UseG1GC** trong danh sách cờ. Log khởi tạo GC cũng cho biết collector mà JVM sử dụng. Trên JDK 27, G1 được chọn mặc định; chỉ thêm **-XX:+UseG1GC** khi cần làm rõ cấu hình trong phép so sánh hoặc bảo đảm cùng collector giữa các môi trường.

Không mặc định rằng hai tiến trình cùng chạy một phiên bản Java sẽ có cấu hình giống nhau. Container CPU quota, giới hạn bộ nhớ, tham số JVM và launcher của nền tảng triển khai đều có thể làm thay đổi lựa chọn runtime.

## 4. Thiết lập phép đo bằng tải thực tế

Trước khi thay đổi G1, hãy xác định ứng dụng đang cần cải thiện điều gì. Ví dụ:

- Độ trễ p99 của request vượt SLO.
- Throughput giảm khi tải tăng.
- CPU dành cho GC chiếm tỷ lệ lớn.
- Các GC pause kéo dài hoặc xảy ra quá thường xuyên.
- Heap tăng cao, thường xuyên xuất hiện Full GC hoặc áp lực bộ nhớ trong container.

Sau đó chạy phép đo với workload đại diện cho production.

### Giữ các điều kiện so sánh nhất quán

Ghi lại các yếu tố sau cho mỗi lần chạy:

| Yếu tố | Cần giữ hoặc ghi nhận |
|---|---|
| JDK | Vendor, phiên bản đầy đủ, build và bản cập nhật |
| Ứng dụng | Commit/build, cấu hình, thư viện JNI và native library |
| Máy chạy | CPU, RAM, kiến trúc, hệ điều hành |
| Container | CPU quota, memory limit, request/limit và cách đặt heap |
| JVM | **-Xms**, **-Xmx**, collector và các cờ GC |
| Workload | Dữ liệu đầu vào, phân bố request, kích thước payload |
| Tải | Số client, concurrency, tốc độ request và thời gian chạy |
| Trạng thái ứng dụng | Warm-up, cache, connection pool và dữ liệu đã nạp |

Không so sánh một lần chạy trên máy phát triển với một lần chạy trên production rồi kết luận thay đổi đến từ G1. Khác biệt về CPU quota, bộ nhớ, dữ liệu hoặc mức tải có thể làm sai kết quả.

### Chạy đủ lâu để thấy chu kỳ GC

Một lần benchmark ngắn có thể chỉ ghi nhận young collections mà chưa đi qua concurrent marking và mixed collections. Với ứng dụng có heap lớn, cần chạy đủ lâu để quan sát các giai đoạn GC xảy ra trong điều kiện tải bình thường và tải cao.

Quy trình nên có:

1. Warm-up ứng dụng để JIT compiler, cache và connection pool đạt trạng thái ổn định.
2. Chạy workload đại diện, bao gồm phân bố request và mức đồng thời thực tế.
3. Thu thập dữ liệu qua nhiều chu kỳ GC và giai đoạn tải cao.
4. Lặp lại phép đo nhiều lần để giảm ảnh hưởng của nhiễu môi trường.
5. So sánh các lần chạy trên cùng điều kiện triển khai.

Nếu cần đánh giá một thay đổi cấu hình, chỉ thay đổi một nhóm tham số trong mỗi vòng thử nghiệm. Điều này giúp nhận ra tham số nào tạo ra thay đổi quan sát được.

## 5. Chỉ số cần theo dõi

Không nên chỉ nhìn vào số lần GC hoặc thời gian của một pause đơn lẻ. Hãy ghép số liệu JVM với metric của ứng dụng.

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Ứng dụng | Throughput, request/second | Khả năng xử lý công việc |
| Ứng dụng | p50, p95, p99, p99.9 latency | Phân bố độ trễ, đặc biệt là tail latency |
| Ứng dụng | Error rate và timeout | Ảnh hưởng tới người dùng |
| Tài nguyên | CPU process, CPU throttling | Phân biệt chi phí GC với thiếu CPU |
| Bộ nhớ | Heap used, post-GC occupancy, RSS | Phân biệt heap pressure với native/container memory pressure |
| GC | Số lần collection, loại collection, pause duration | Tần suất và thời gian ứng dụng bị dừng |
| GC | Tổng thời gian pause trong khoảng đo | Mức thời gian ứng dụng thực sự bị dừng do GC |
| GC | Allocation rate và promotion | Áp lực tạo đối tượng và đưa đối tượng lên old generation |
| GC | Full GC, evacuation failure, humongous regions | Dấu hiệu về thiếu vùng đích, heap pressure hoặc phân mảnh |

G1 thực hiện một phần công việc đồng thời với application thread. Vì vậy, **tổng thời gian GC** và **tổng thời gian application bị pause** là hai đại lượng khác nhau. Khi đánh giá tác động tới latency, cần xem thời gian pause và đối chiếu timestamp với request chậm.

Đối với region pinning, chú ý log có lý do **Pinned**. Tuy nhiên, chỉ nhìn thấy một dòng Pinned không đủ để kết luận pinning là nguyên nhân chính làm giảm throughput hoặc tăng p99. Cần xem tần suất, thời lượng, mức heap pressure và metric ứng dụng trong cùng khoảng thời gian.

## 6. Thu thập GC log trên JDK hiện hành

Unified Logging là cách hiện hành để ghi lại hoạt động GC.

### Log ở mức thông tin

Có thể bắt đầu với:

~~~shell
java -XX:+UseG1GC -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Trên JDK 27, **-XX:+UseG1GC** là tùy chọn tường minh; G1 đã là collector mặc định trong mọi môi trường. Trên JDK 25, tùy chọn này hữu ích khi cần bảo đảm tiến trình benchmark thực sự dùng G1.

GC log giúp xác định:

- Loại collection: young, concurrent start, mixed hoặc full.
- Heap occupancy trước và sau collection.
- Pause duration.
- Evacuation failure và lý do.
- Các thay đổi heap, region và thông tin liên quan đến humongous objects.

### Tăng mức chi tiết khi cần chẩn đoán

Khi log thông tin chưa giải thích được pause hoặc phase tốn thời gian, có thể thu thập log chi tiết hơn:

~~~shell
java -XX:+UseG1GC -Xlog:gc*=debug:file=gc-debug.log:time,uptime,level,tags -jar app.jar
~~~

Mức debug tạo nhiều log hơn và có thể tăng chi phí ghi I/O. Chỉ bật trong khoảng thời gian cần điều tra, đồng thời kiểm tra overhead của logging trong môi trường tương tự production.

Một số nhóm log hữu ích:

| Nhóm log | Mục đích |
|---|---|
| **gc** | Loại GC, pause, heap occupancy và evacuation failure |
| **gc+cpu** | So sánh thời gian user, system và real trong pause |
| **gc+heap** | Theo dõi heap và số region, bao gồm humongous regions |
| **gc+phases** | Xem thời gian từng phase của collection |
| **gc+ergo+cset** | Xem cách G1 chọn collection set và dự đoán thời gian |

Oracle khuyến nghị bắt đầu bằng **-Xlog:gc*=debug** khi chẩn đoán G1, sau đó thu hẹp log theo vấn đề đang quan sát. Tham khảo [Garbage-First Garbage Collector Tuning — JDK 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html).

## 7. Dùng JDK Flight Recorder để xem tác động của GC

GC log mô tả quyết định và các phase của collector. JDK Flight Recorder (JFR) giúp xem GC pause trong bối cảnh hoạt động của ứng dụng, CPU và bộ nhớ.

Có thể bắt đầu một recording khi chạy ứng dụng:

~~~shell
java -XX:+UseG1GC -XX:StartFlightRecording=filename=gc-profile.jfr,settings=profile,duration=30m -jar app.jar
~~~

Thời lượng 30 phút chỉ là ví dụ; chọn khoảng thời gian đủ dài để quan sát workload và chu kỳ GC của ứng dụng. Khi thu thập trên production, đánh giá overhead và chính sách lưu trữ recording của môi trường.

Dùng công cụ **jfr** để xem tổng quan recording:

~~~shell
jfr summary gc-profile.jfr
~~~

In các sự kiện GC pause:

~~~shell
jfr print --events jdk.GCPhasePause gc-profile.jfr
~~~

Trong JDK Mission Control, có thể xem GC pause, tổng thời gian pause, heap usage, CPU và các sự kiện liên quan theo timeline. Đối chiếu thời điểm pause với request latency để xác định liệu các request chậm có trùng với stop-the-world pause hay không.

Khi điều tra GC, tránh bật thu thập heap statistics chỉ để có thêm dữ liệu nếu chưa cần thiết. Việc yêu cầu heap statistics có thể kích hoạt thêm old collection và làm thay đổi hành vi đang đo. Xem [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html).

## 8. Đọc đúng evacuation failure liên quan đến pinning

Trên JDK 27, G1 có thể ghi nhận evacuation failure cùng một hoặc cả hai lý do **Allocation** và **Pinned**.

Ví dụ:

~~~text
GC(26) Pause Young (Normal) (G1 Evacuation Pause)
(Evacuation Failure: Allocation/Pinned)
2159M->402M(3000M) 6.108ms
~~~

Hai lý do này không đồng nghĩa:

| Lý do | Ý nghĩa | Hướng điều tra |
|---|---|---|
| **Pinned** | G1 gặp đối tượng không thể di chuyển vì đang được giữ để native code sử dụng, ví dụ qua **GetPrimitiveArrayCritical()** hoặc JNI tương tự | Kiểm tra đường gọi JNI, thời gian giữ critical region và số lần xảy ra |
| **Allocation** | G1 không tìm đủ vùng đích để di chuyển đối tượng trong collection set | Kiểm tra heap pressure, allocation rate, concurrent marking và dung lượng heap |

Nếu G1 không thể di chuyển tất cả đối tượng ra khỏi một region, region đó tạm thời không dùng để cấp phát. G1 đưa region đã gặp evacuation failure thành ứng viên cho các collection tiếp theo. Region pinning cho phép G1 tiếp tục thu gom những vùng khác trong cùng lúc.

Khi đọc log, hãy trả lời các câu hỏi:

1. Có xuất hiện **Pinned** hay chỉ **Allocation**?
2. Tần suất xảy ra có tăng khi tải JNI tăng không?
3. Những lần đó có trùng với p99 latency hoặc throughput giảm không?
4. Heap còn đủ vùng trống hay đang chịu áp lực allocation?
5. Các region bị ảnh hưởng có được thu gom ở những collection tiếp theo không?

**Pinned** là tín hiệu để điều tra, không phải chỉ thị rằng cần tăng heap hoặc chỉnh region size ngay lập tức. Nếu nguyên nhân là **Allocation**, thay đổi liên quan JNI critical region có thể không giải quyết được vấn đề.

Tham khảo [Evacuation Failure — JDK 27 G1 GC](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html).

## 9. Điều chỉnh G1 sau khi đã có bằng chứng

Khuyến nghị chung của Oracle là bắt đầu với cấu hình mặc định của G1. Chỉ thay đổi tham số khi log và metric cho thấy vấn đề cụ thể.

| Bằng chứng quan sát được | Hướng điều tra hoặc thử nghiệm |
|---|---|
| Pause vượt mục tiêu latency nhưng throughput còn dư | Thử điều chỉnh pause-time goal bằng **-XX:MaxGCPauseMillis** |
| GC chiếm nhiều thời gian, heap có đủ headroom và ứng dụng ưu tiên throughput | Thử nới pause-time goal hoặc đánh giá heap size lớn hơn |
| Young collection có phase Object Copy dài, nhiều object sống sót | Điều tra kích thước young generation và tỷ lệ object sống sót trước khi thay đổi giới hạn |
| Mixed collection mất nhiều thời gian ở old regions | Xem **gc+ergo+cset=debug**; sau đó mới cân nhắc các tham số như **G1MixedGCCountTarget** |
| Full GC xuất hiện sau evacuation failure Allocation | Điều tra allocation rate, thời điểm concurrent marking, heap capacity và humongous objects |
| Humongous regions chiếm tỷ lệ cao và có dấu hiệu fragmentation | Kiểm tra kích thước object và region trước khi cân nhắc **-XX:G1HeapRegionSize** |
| Log cho thấy real pause lớn hơn nhiều tổng user/system time | Điều tra CPU throttling, hệ điều hành, memory allocation hoặc I/O của môi trường |

### Pause-time goal không phải cam kết latency

Ví dụ:

~~~shell
java -XX:+UseG1GC -XX:MaxGCPauseMillis=150 -jar app.jar
~~~

**-XX:MaxGCPauseMillis** là mục tiêu để G1 điều chỉnh lượng công việc trong pause. Đây không phải giới hạn cứng và không bảo đảm mọi pause đều nhỏ hơn 150 ms.

Mục tiêu pause thấp hơn có thể khiến G1 thu gom thường xuyên hơn hoặc giảm lượng công việc thực hiện trong mỗi pause, từ đó ảnh hưởng throughput. Hãy đánh giá cả latency lẫn throughput sau thay đổi.

### Tránh khóa cứng young generation khi chưa có lý do

Không nên tùy tiện đặt **-Xmn**, **-XX:NewRatio** hoặc giới hạn young generation thành một kích thước cố định. G1 dùng kích thước young generation để điều chỉnh pause-time; khóa cứng kích thước này có thể làm mất khả năng điều khiển pause tự động.

Khi chuyển từ collector khác sang G1, Oracle khuyến nghị bắt đầu bằng cách bỏ các cờ GC cũ, sau đó chỉ đặt heap size và pause-time goal nếu phép đo cho thấy cần thiết.

## 10. Phân biệt hiệu quả của JEP 423 với thay đổi JDK khác

JEP 423 có trong JDK 22 và tiếp tục được dùng khi ứng dụng chạy G1 trên các JDK hiện đại. Tuy nhiên, khi so sánh JDK 22 với JDK 25 hoặc JDK 27, không thể quy toàn bộ thay đổi hiệu năng cho region pinning.

Các phiên bản JDK sau đó còn có những thay đổi khác trong compiler, runtime, G1 và lựa chọn collector. Ví dụ, JDK 27 đưa G1 thành collector mặc định trong mọi môi trường qua JEP 523. Một phép đo giữa hai phiên bản JDK vì thế phản ánh tổng hợp các thay đổi của runtime, không cô lập riêng JEP 423.

Nếu cần đánh giá tác động của việc nâng cấp JDK:

- Giữ cùng ứng dụng, native library, workload và cấu hình heap.
- Ghi lại chính xác collector được chọn ở mỗi phiên bản.
- Đo cùng các chỉ số ứng dụng và GC.
- Ghi nhận các thay đổi runtime khác giữa hai phiên bản.
- Chỉ kết luận về tác động tổng thể của lần nâng cấp, trừ khi có thí nghiệm riêng đủ khả năng cô lập một thay đổi.

JEP 423 không có cờ bật/tắt để tạo một phép A/B trực tiếp trên cùng một JDK. Không nên tự tạo một cờ JVM giả định để vô hiệu hóa region pinning. Muốn xác định tính năng có liên quan đến vấn đề hay không, hãy kiểm tra ứng dụng có dùng JNI critical region, theo dõi dấu hiệu **Pinned** và đối chiếu với metric trong workload thật.

## 11. Quy trình thực hành trước khi thay đổi cấu hình G1

1. **Xác định mục tiêu.** Chọn SLO cần cải thiện: p99 latency, throughput, CPU, heap footprint hoặc tỷ lệ Full GC.
2. **Xác nhận runtime.** Ghi lại vendor, build JDK, collector thực tế, CPU quota, memory limit và toàn bộ cờ JVM.
3. **Kiểm tra JNI.** Xác định thư viện nào dùng **GetPrimitiveArrayCritical()**, **GetStringCritical()** hoặc API tương tự; bảo đảm critical region được release đúng cách.
4. **Đo baseline.** Chạy workload production-like với cấu hình hiện tại, thu GC log, JFR và metric ứng dụng.
5. **Phân tích nguyên nhân.** Phân biệt pause dài, GC thường xuyên, Allocation failure, Pinned failure, Full GC và CPU throttling.
6. **Thử một thay đổi.** Chọn tham số phù hợp với nguyên nhân đã xác định; giữ các điều kiện khác ổn định.
7. **Đo lại và so sánh.** Lặp lại workload, so sánh phân bố latency, throughput, CPU, heap và tổng pause.
8. **Xác nhận trên deployment thật.** Triển khai canary hoặc một nhóm instance nhỏ, theo dõi qua tải cao và rollback nếu metric xấu đi.

Nếu không có bằng chứng rằng G1 đang gây ra vấn đề, giữ cấu hình mặc định thường là lựa chọn tốt. Nếu có dấu hiệu pinning, ưu tiên kiểm tra JNI critical region và thời gian giữ con trỏ trước khi thay đổi heap hoặc các tham số GC không liên quan.

## Tài liệu tham khảo chính thức

- [JEP 423 — Region Pinning for G1](https://openjdk.org/jeps/423): mục tiêu và thiết kế region pinning trong JDK 22.
- [JDK 22 Release Notes — Region Pinning for G1](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html): mô tả G1 tiếp tục thu gom trong khi JNI critical region giữ tham chiếu đến Java object.
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523): thay đổi lựa chọn collector mặc định trong JDK 27.
- [JDK 27 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html): region, collection cycle, evacuation failure và trạng thái collector.
- [JDK 27 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html): khuyến nghị cấu hình mặc định, GC logging và chẩn đoán latency/throughput.
- [JNI Specification — GetPrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html): giới hạn, giá trị isCopy và vòng đời của JNI critical region.
- [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html): dùng JFR để phân tích GC pause và hoạt động ứng dụng.

