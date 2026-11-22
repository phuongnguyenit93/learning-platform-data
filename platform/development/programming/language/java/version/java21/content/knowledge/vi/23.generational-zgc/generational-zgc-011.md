# Kiểm tra tùy chọn GC theo phiên bản khi nâng từ JDK 21 lên JDK mới

Khi nâng ứng dụng từ JDK 21 lên JDK mới hơn, cần rà soát các JVM option của ZGC theo đúng phiên bản đích. Điểm thay đổi quan trọng nhất là `-XX:+ZGenerational`: ở JDK 21 và 22, tùy chọn này dùng để bật Generational ZGC; ở JDK 23, Generational ZGC trở thành mặc định và chế độ không generational bị deprecated; từ JDK 24, chế độ không generational cùng tùy chọn `ZGenerational` đã bị loại bỏ.

Vì vậy, cấu hình từng dùng trên JDK 21 như `-XX:+UseZGC -XX:+ZGenerational` không nên được sao chép nguyên trạng sang JDK 24 trở lên. Trên các phiên bản mới, chỉ cần `-XX:+UseZGC` để chọn ZGC; collector này chạy ở chế độ generational. Các tùy chọn heap và chẩn đoán khác vẫn cần được kiểm tra theo tài liệu của runtime đích.

## 1. Vì sao tùy chọn ZGenerational thay đổi?

Generational ZGC chia heap thành hai thế hệ logic:

- **Young generation:** nơi object mới được cấp phát và được thu gom thường xuyên hơn vì nhiều object thường kết thúc vòng đời sớm.
- **Old generation:** nơi object sống lâu được giữ lại và thu gom theo chu kỳ phù hợp.

Cách tổ chức này tận dụng weak generational hypothesis: phần lớn object mới tạo sẽ sớm không còn được tham chiếu. Nhờ tập trung thu gom vùng young thường xuyên, Generational ZGC có thể giảm công việc GC trên toàn bộ heap trong nhiều workload.

JDK 21 đưa Generational ZGC vào ZGC như một chế độ có thể bật riêng, để ứng dụng có thời gian kiểm thử trước khi trở thành mặc định. Sau đó, dự án OpenJDK chuyển dần sang chỉ duy trì chế độ generational. Sự chuyển đổi này tạo ra thay đổi trực tiếp trong JVM option và cần được xử lý khi nâng JDK.

## 2. Bảng thay đổi theo phiên bản JDK

| Phiên bản | Chế độ mặc định khi bật `-XX:+UseZGC` | Trạng thái `ZGenerational` | Cấu hình cần nhớ |
|---|---|---|---|
| JDK 21 | Non-generational | Có; mặc định tắt | Thêm `-XX:+ZGenerational` để bật Generational ZGC |
| JDK 22 | Non-generational | Có; mặc định tắt | Tương tự JDK 21, thêm `-XX:+ZGenerational` để bật generational |
| JDK 23 | Generational | Còn tồn tại; non-generational bị deprecated for removal | Không cần thêm `+ZGenerational`; `-XX:-ZGenerational` chỉ còn là lựa chọn chuyển tiếp để kiểm thử tương thích |
| JDK 24 | Generational | Đã bị loại bỏ cùng non-generational mode | Dùng `-XX:+UseZGC`; không truyền `ZGenerational` ở cả dạng `+` lẫn `-` |
| JDK 25 và JDK 26 | Generational | Không còn | Dùng `-XX:+UseZGC`; kiểm tra các option còn lại theo tài liệu phiên bản đích |

Lưu ý: “Generational mặc định” ở JDK 23 trở lên chỉ nói về chế độ của ZGC khi ứng dụng đã chọn ZGC. Nó không có nghĩa ZGC tự trở thành garbage collector mặc định của mọi JVM. Nếu không truyền `-XX:+UseZGC`, JVM vẫn chọn collector mặc định theo môi trường và cấu hình của nó.

## 3. Cấu hình JDK 21 và cấu hình sau khi nâng cấp

### JDK 21: bật Generational ZGC tường minh

Trên JDK 21, chỉ bật ZGC chưa đủ để chọn chế độ generational. Cần có cả hai option:

```bash
java \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  -Xms2g \
  -Xmx8g \
  -Xlog:gc* \
  -jar app.jar
```

Nếu bỏ `-XX:+ZGenerational`, JDK 21 dùng chế độ non-generational khi ZGC được bật. Vì vậy, khi ứng dụng đang chạy Generational ZGC trên JDK 21, hãy ghi nhận điều đó trước khi so sánh hiệu năng với JDK mới.

### JDK 23: không cần bật lại chế độ generational

JDK 23 đã chọn Generational ZGC làm mặc định. Cấu hình có thể rút gọn:

```bash
java \
  -XX:+UseZGC \
  -Xms2g \
  -Xmx8g \
  -Xlog:gc* \
  -jar app.jar
```

`-XX:+ZGenerational` vẫn được nhận diện trong JDK 23 nhưng là dư thừa vì giá trị mặc định đã là bật. Ngược lại, `-XX:-ZGenerational` có thể chọn lại chế độ non-generational trong giai đoạn chuyển tiếp, nhưng chế độ đó đã deprecated for removal. Không nên giữ tùy chọn tắt này trong cấu hình production mới.

### JDK 24 trở lên: xóa ZGenerational khỏi command line

Từ JDK 24, non-generational ZGC bị loại bỏ và option `ZGenerational` không còn tồn tại. Cấu hình dùng cho JDK 24, 25 hoặc 26 nên có dạng:

```bash
java \
  -XX:+UseZGC \
  -Xms2g \
  -Xmx8g \
  -Xlog:gc* \
  -jar app.jar
```

Nếu vẫn truyền `-XX:+ZGenerational` hoặc `-XX:-ZGenerational`, JVM mới có thể dừng ngay khi khởi động với lỗi `Unrecognized VM option`. Hãy xóa option này khỏi script và cấu hình triển khai, không cố giữ nó bằng cách bỏ qua option không được nhận diện.

## 4. Cách xử lý khi một ứng dụng cần chạy trên nhiều JDK

Nếu cùng một ứng dụng còn hỗ trợ JDK 21 và đồng thời triển khai trên JDK 24 trở lên, không nên dùng một danh sách JVM option cố định có `-XX:+ZGenerational` cho mọi runtime.

Có thể quản lý cấu hình theo major version:

```text
JDK 21 / 22:
    -XX:+UseZGC -XX:+ZGenerational

JDK 23:
    -XX:+UseZGC

JDK 24+:
    -XX:+UseZGC
```

Một cách khác là duy trì file cấu hình JVM riêng cho từng image/runtime. Nếu dùng script để chọn option theo phiên bản, hãy đọc phiên bản từ chính executable Java sẽ chạy ứng dụng, không dựa vào một `java` khác trong `PATH`.

Không dùng `-XX:+IgnoreUnrecognizedVMOptions` để che lỗi option đã bị xóa. Cách này có thể làm JVM khởi động nhưng che giấu cấu hình không còn được áp dụng; khi đó ứng dụng không chạy với đúng chế độ GC mà nhóm vận hành nghĩ rằng đã cấu hình.

## 5. Rà soát option trong môi trường triển khai

Option JVM không chỉ nằm trong câu lệnh `java -jar`. Khi nâng JDK, cần tìm tất cả nơi có thể bổ sung JVM argument:

- Dockerfile, container image, entrypoint và startup script.
- Kubernetes Deployment/StatefulSet, Helm values, ConfigMap và manifest triển khai.
- Systemd service, Windows service wrapper và script khởi động ứng dụng.
- Biến môi trường `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và các cấu hình runtime do nền tảng cung cấp.
- Cấu hình CI/CD, test runner, Maven/Gradle daemon hoặc công cụ đóng gói ứng dụng.

Đặc biệt tìm cả hai dạng `-XX:+ZGenerational` và `-XX:-ZGenerational`. Dạng bật thường xuất hiện trong cấu hình JDK 21; dạng tắt có thể còn sót lại từ thử nghiệm so sánh non-generational trên JDK 23.

### Xác nhận đúng runtime đang dùng

Chạy các lệnh bằng đúng Java executable được cấu hình cho service:

```bash
java -version
java -XX:+UseZGC -XX:+PrintFlagsFinal -version
```

Trên Linux/macOS, có thể lọc các cờ liên quan:

```bash
java -XX:+UseZGC -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'UseZGC|ZGenerational'
```

Trên Windows PowerShell:

```powershell
java -XX:+UseZGC -XX:+PrintFlagsFinal -version 2>&1 | Select-String 'UseZGC|ZGenerational'
```

Kết quả giúp kiểm tra flag nào còn tồn tại và giá trị hiện tại của flag. Với JDK 24 trở lên, không còn dòng `ZGenerational` vì option đã bị loại bỏ. `PrintFlagsFinal` không thay thế việc kiểm tra command line thực tế của service; hãy xác nhận cả executable, biến môi trường và startup arguments của process.

Với process đang chạy, có thể kiểm tra bằng `jcmd` từ cùng JDK:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

`VM.command_line` cho biết command line dùng để khởi chạy JVM; `VM.flags` hiển thị các VM flag đang có hiệu lực. Thay `<pid>` bằng process ID thực tế.

## 6. Những option ZGC vẫn cần xem xét sau khi bỏ ZGenerational

Việc loại bỏ `ZGenerational` không có nghĩa mọi option ZGC đều bị xóa. Các cấu hình heap, trả bộ nhớ và ghi log vẫn được tài liệu JDK mới hỗ trợ. Hãy chọn theo mục tiêu ứng dụng và kiểm tra trên đúng bản JDK đang triển khai.

| Option | Mục đích | Cách dùng/thận trọng |
|---|---|---|
| `-XX:+UseZGC` | Chọn ZGC | Vẫn là option bật ZGC trên JDK mới |
| `-Xmx<size>` | Đặt giới hạn heap tối đa | Đảm bảo heap chứa live set và có đủ headroom cho allocation trong khi GC chạy |
| `-Xms<size>` | Đặt heap ban đầu/tối thiểu | Khi đặt bằng `-Xmx`, ZGC không uncommit heap xuống thấp hơn mức này |
| `-XX:SoftMaxHeapSize=<size>` | Đặt soft limit cho heap | ZGC cố gắng ở dưới mức này nhưng vẫn có thể vượt lên đến `-Xmx` để tránh allocation stall |
| `-XX:-ZUncommit` | Tắt việc trả heap không dùng về hệ điều hành | Giảm hoạt động commit/uncommit nhưng giữ lại nhiều bộ nhớ hơn |
| `-XX:ZUncommitDelay=<seconds>` | Đặt thời gian bộ nhớ phải không dùng trước khi uncommit | Giá trị mặc định được tài liệu ZGC hiện hành nêu là 300 giây |
| `-XX:+AlwaysPreTouch` | Chạm trước các trang heap khi khởi động | Có thể giúp độ trễ ổn định hơn nhưng làm startup chậm và commit bộ nhớ sớm |
| `-Xlog:gc*` | Ghi log GC theo Unified Logging | Dùng để so sánh chu kỳ GC, pause và hoạt động heap sau khi nâng JDK |

ZGC được thiết kế để tự điều chỉnh; JVM tự thay đổi kích thước generation, số GC thread và ngưỡng tenuring theo workload. Thường nên bắt đầu bằng việc cấp đủ `-Xmx`, quan sát dữ liệu rồi mới thêm tuning. Không sao chép hàng loạt các cờ nội bộ từ cấu hình cũ mà không có số liệu chứng minh.

Nếu mục tiêu là giảm footprint, để ZGC trả bộ nhớ không dùng về hệ điều hành có thể phù hợp. Nếu mục tiêu là latency rất thấp và môi trường đủ RAM, có thể thử `-Xms` bằng `-Xmx` cùng `-XX:+AlwaysPreTouch`. Đây là lựa chọn đánh đổi giữa footprint, startup và latency; cần đo trong môi trường thực tế.

## 7. Ghi log và đo lại sau khi nâng JDK

Không kết luận migration thành công chỉ vì JVM khởi động được. Hãy chạy cùng workload đại diện và thu thập GC log:

```bash
java \
  -XX:+UseZGC \
  -Xms2g \
  -Xmx8g \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar app.jar
```

Nếu cần phân tích sâu hơn, có thể thu JDK Flight Recorder:

```bash
java \
  -XX:+UseZGC \
  -XX:StartFlightRecording=filename=zgc-migration.jfr,settings=profile \
  -jar app.jar
```

Khi so sánh JDK 21 với JDK mới, giữ workload, dữ liệu, concurrency và giới hạn CPU/RAM tương đương. Theo dõi ít nhất:

- Throughput và thời gian đáp ứng p95/p99 của ứng dụng.
- GC pause và thời gian các chu kỳ thu gom.
- Heap occupancy, live set và tốc độ allocation.
- CPU dùng cho GC so với CPU dành cho ứng dụng.
- Dấu hiệu allocation stall, áp lực bộ nhớ và footprint của process.

Generational ZGC thường có lợi với workload tạo nhiều object ngắn hạn, nhưng không bảo đảm mọi ứng dụng đều nhanh hơn ở mọi chỉ số. Một số workload có đặc điểm khác có thể không được cải thiện hoặc có thể giảm hiệu năng. Hãy dựa trên phép đo thay vì chỉ dựa vào tên chế độ GC.

## 8. Các lỗi thường gặp khi nâng cấp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JDK 24+ báo `Unrecognized VM option 'ZGenerational'` | Startup script còn `+ZGenerational` hoặc `-ZGenerational` | Xóa option này; giữ `-XX:+UseZGC` nếu muốn chọn ZGC |
| JDK 21 chạy ZGC nhưng không chạy generational | Thiếu `-XX:+ZGenerational` | Thêm option khi mục tiêu là Generational ZGC trên JDK 21/22 |
| JDK 23 vẫn có `-XX:-ZGenerational` | Cấu hình cũ đang ép chế độ non-generational | Bỏ cờ tắt; chế độ này đã deprecated for removal |
| Tưởng JDK 24+ tự chọn ZGC mà không cần cấu hình | Nhầm default mode của ZGC với default collector của JVM | Thêm `-XX:+UseZGC` nếu ứng dụng cần ZGC |
| Service chạy được nhưng log không phản ánh cấu hình dự kiến | Kiểm tra nhầm Java executable hoặc bỏ sót biến môi trường/startup wrapper | Kiểm tra `java -version`, `jcmd VM.command_line` và `jcmd VM.flags` trên đúng process |
| Latency thay đổi sau migration | Khác biệt allocation, heap sizing, uncommit, CPU hoặc workload | Thu GC log/JFR và so sánh trong môi trường tương đương |

## 9. Checklist trước khi triển khai

1. Xác nhận major version và vendor của JDK đích.
2. Tìm mọi JVM argument ở script, container, service, CI và biến môi trường.
3. Xác định cấu hình cũ có `-XX:+ZGenerational` hay `-XX:-ZGenerational`.
4. Nếu đích là JDK 21/22, giữ `+ZGenerational` khi muốn bật chế độ generational.
5. Nếu đích là JDK 23, bỏ cờ tắt; generational đã là mặc định.
6. Nếu đích là JDK 24 trở lên, xóa cả dạng bật và tắt `ZGenerational` vì flag đã bị loại bỏ.
7. Giữ `-XX:+UseZGC` nếu chủ đích là dùng ZGC; rà soát `-Xms`, `-Xmx`, `SoftMaxHeapSize` và uncommit theo giới hạn tài nguyên.
8. Khởi chạy thử bằng đúng executable JDK đích và xác nhận `VM.command_line`/`VM.flags`.
9. Chạy workload đại diện, thu `-Xlog:gc*` hoặc JFR và so sánh latency, throughput, CPU cùng heap.
10. Chỉ triển khai khi startup option, hành vi GC và SLO ứng dụng đều đã được xác nhận.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html)
- [Oracle Java SE 22 — Available Collectors](https://docs.oracle.com/en/java/javase/22/gctuning/available-collectors.html)
- [Oracle — Significant Changes in JDK 23](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-23.html)
- [Oracle — Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
- [Oracle Java SE 26 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/z-garbage-collector.html)
- [Oracle Java SE 26 — The java Command and GC Options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439)
- [OpenJDK JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
- [OpenJDK JEP 490 — ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490)
