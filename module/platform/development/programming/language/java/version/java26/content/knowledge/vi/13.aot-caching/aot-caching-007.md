# Tạo bộ đệm bằng -XX:AOTCacheOutput

**Ahead-of-Time Cache (AOT cache)** là tính năng của HotSpot JVM giúp giảm thời gian khởi động và làm nóng ứng dụng bằng cách lưu lại một số dữ liệu runtime đã được chuẩn bị trước. Từ JDK 25, có thể tạo cache cho ứng dụng bằng một lệnh `-XX:AOTCacheOutput=<file>`; JVM thực hiện training rồi tự chạy bước assembly để tạo file `.aot`. Khi triển khai, dùng `-XX:AOTCache=<file>` để nạp cache.

AOT cache được giới thiệu trong JDK 24 qua JEP 483. JDK 25 bổ sung cách tạo cache một bước qua JEP 514. JDK 26 tiếp tục cải tiến bằng JEP 516: dữ liệu object trong cache có thể được nạp với mọi garbage collector, bao gồm ZGC. Các cơ chế này vẫn được duy trì trong JDK 27. Đây là tính năng runtime của HotSpot, không phải preview hay incubator API.

## 1. AOT cache lưu gì và giúp ích ở đâu?

AOT cache là một file chứa các artifact mà JVM có thể chuẩn bị trước khi chạy ứng dụng. Trong JDK 26/27, cache lưu các Java class và heap object đã được ghi nhận trong quá trình training. Nhờ đó, lần chạy sau có thể giảm công việc đọc, phân tích, nạp và liên kết class, đồng thời khởi tạo sẵn một số object cần thiết.

Hai mục tiêu chính:

- **Startup:** rút ngắn thời gian từ lúc JVM bắt đầu đến khi ứng dụng sẵn sàng xử lý công việc đầu tiên.
- **Warmup:** giảm một phần công việc ban đầu trước khi ứng dụng đạt trạng thái hoạt động ổn định.

AOT cache không biến ứng dụng thành native executable và không thay thế JIT compiler. JVM vẫn thực thi bytecode và tiếp tục JIT compile các method theo hoạt động thực tế. Cache giúp chuyển một số công việc chuẩn bị từ lúc khởi động sang giai đoạn tạo cache trước đó.

JDK 25 còn có **JEP 515 — Ahead-of-Time Method Profiling**, một cải tiến liên quan giúp profile thực thi method từ lần chạy trước sẵn sàng sớm hơn để JIT warm up nhanh hơn. Đây là một tối ưu AOT bổ sung; không nên hiểu file `.aot` là native executable chứa toàn bộ mã máy của ứng dụng.

Không nhầm AOT cache với:

| Cơ chế | Vai trò |
| --- | --- |
| AOT cache | Lưu class và heap object đã chuẩn bị trước để cải thiện startup/warmup của HotSpot |
| CDS (Class Data Sharing) | Chia sẻ dữ liệu class đã được xử lý giữa các JVM process; AOT cache là bước phát triển tiếp theo với nhiều artifact hơn |
| JIT compilation | Biên dịch bytecode thành native code trong lúc ứng dụng chạy, dựa trên profile thực tế |
| GraalVM Native Image | Biên dịch ứng dụng thành executable native riêng; đây là mô hình triển khai khác với AOT cache của HotSpot |

## 2. Quy trình ba giai đoạn

Việc tạo và sử dụng cache có ba giai đoạn logic:

1. **Training:** chạy ứng dụng với workload đại diện. JVM quan sát class được nạp, object được khởi tạo và hoạt động của ứng dụng; dữ liệu được ghi vào AOT configuration.
2. **Assembly:** JVM dùng dữ liệu training để tạo file AOT cache `.aot`.
3. **Production:** khởi chạy ứng dụng với `-XX:AOTCache` để nạp cache và tận dụng các artifact đã chuẩn bị.

```text
                    Training
       chạy ứng dụng với workload đại diện
                       |
                       v
              AOT Configuration
                       |
                       v
                    Assembly
              tạo file application.aot
                       |
                       v
                   Production
        java -XX:AOTCache=application.aot ...
                       |
                       v
             Startup / warmup nhanh hơn
```

Từ JDK 25, `-XX:AOTCacheOutput` gộp hai giai đoạn Training và Assembly vào một lệnh. Bạn không cần tự đặt tên hoặc quản lý file cấu hình trung gian trong trường hợp thông thường.

## 3. Tạo cache bằng một lệnh `-XX:AOTCacheOutput`

Giả sử ứng dụng được đóng gói trong `app.jar`, có main class `com.example.App`. Chạy training trên đúng JDK và môi trường mục tiêu:

```bash
java -XX:AOTCacheOutput=app.aot -cp app.jar com.example.App
```

Hoặc nếu JAR có `Main-Class` trong manifest:

```bash
java -XX:AOTCacheOutput=app.aot -jar app.jar
```

`-XX:AOTCacheOutput=app.aot` yêu cầu JVM tạo cache tại `app.aot`. Với cấu hình mặc định `-XX:AOTMode=auto`, JVM tự chuyển sang chế độ `record` để thực hiện training. Khi training kết thúc, JVM khởi chạy một JVM process thứ hai để thực hiện Assembly và ghi cache.

Lệnh trên có nghĩa:

- Ứng dụng thực sự được chạy trong giai đoạn training.
- Workload của lần chạy này quyết định class và object nào được đưa vào cache.
- Khi ứng dụng kết thúc hoặc recording được dừng, JVM thực hiện Assembly.
- File `app.aot` là kết quả cần chuyển sang môi trường production tương ứng.

`-XX:AOTCacheOutput` và `-XX:AOTCache` không được dùng đồng thời trong cùng một lệnh. Một tùy chọn tạo cache; tùy chọn còn lại nạp cache đã tạo.

Các tùy chọn `-XX` thuộc HotSpot JVM, không phải API Java SE portable cho mọi implementation JVM. Khi dùng bản phân phối JVM khác HotSpot, hãy kiểm tra tài liệu của nhà cung cấp trước khi đưa cờ này vào launch script.

## 4. Training phải mô phỏng workload production

Training không chỉ là khởi chạy ứng dụng rồi kết thúc ngay. Hãy cho ứng dụng đi qua những đường khởi tạo và chức năng quan trọng mà production thường sử dụng:

- Khởi tạo cấu hình, dependency injection container và các service dùng chung.
- Nạp các class được sử dụng trong luồng request phổ biến.
- Tạo các object dùng chung và dữ liệu khởi tạo có thể tái sử dụng.
- Chạy smoke test cho các luồng nghiệp vụ quan trọng.
- Nếu cần, dùng dữ liệu giả lập hoặc mock dependency bên ngoài để kích hoạt đúng đường code mà không phụ thuộc hệ thống production.

Tránh chạy toàn bộ test suite nặng hoặc tải các class không dùng trong production chỉ để training. Việc đó có thể làm cache phình to và làm giảm hiệu quả. Training quá nông cũng không tốt: nếu một luồng khởi tạo quan trọng không được chạy, cache sẽ không có đủ artifact để hỗ trợ luồng đó.

Với service chạy liên tục, lệnh `-XX:AOTCacheOutput` sẽ tiếp tục recording trong khi process còn hoạt động. Có thể kết thúc recording bằng `HotSpotAOTCacheMXBean.endRecording()`; phương thức trả về sau khi artifact đã được ghi xong. MXBean này có từ JDK 26 trong module `jdk.management`. Nên điều khiển từ công cụ quản trị bên ngoài khi có thể, để tránh thêm logic chỉ dành cho training vào chính ứng dụng.

Ví dụ truy cập MXBean từ code nếu ứng dụng cần chủ động kết thúc recording:

```java
import java.lang.management.ManagementFactory;
import jdk.management.HotSpotAOTCacheMXBean;

HotSpotAOTCacheMXBean aotCache =
        ManagementFactory.getPlatformMXBean(HotSpotAOTCacheMXBean.class);

if (aotCache != null) {
    boolean ended = aotCache.endRecording();
    System.out.println("AOT recording ended: " + ended);
}
```

`endRecording()` không khởi động recording; recording phải được bật từ đầu bằng tùy chọn JVM như `-XX:AOTCacheOutput`. Phương thức trả `true` nếu recording đang hoạt động và được kết thúc thành công, ngược lại trả `false`.

## 5. Dùng cache trong production

Sau khi tạo được `app.aot`, khởi chạy ứng dụng với `-XX:AOTCache`:

```bash
java -XX:AOTCache=app.aot -cp app.jar com.example.App
```

Với executable JAR:

```bash
java -XX:AOTCache=app.aot -jar app.jar
```

Khi không chỉ định `-XX:AOTMode`, chế độ mặc định là `auto`. Nếu cache có thể được nạp, JVM sử dụng cache; nếu cache không tồn tại, không truy cập được hoặc không tương thích, JVM tiếp tục chạy ứng dụng mà không dùng cache. Đây là lựa chọn phù hợp cho production vì cache là tối ưu hóa hiệu năng, không nên trở thành điều kiện bắt buộc để ứng dụng khởi động.

Có thể bật unified logging để quan sát việc nạp cache:

```bash
java -XX:AOTCache=app.aot -Xlog:aot -cp app.jar com.example.App
```

Nếu cần kiểm tra kỹ classpath và artifact được sử dụng:

```bash
java -XX:AOTCache=app.aot -Xlog:aot,class+path=info -cp app.jar com.example.App
```

Log giúp xác định cache có được chấp nhận hay không và hỗ trợ tìm nguyên nhân khi JVM bỏ qua cache.

## 6. Khác biệt `AOTMode` giữa JDK 26 và JDK 27

`-XX:AOTCacheOutput` tự hoạt động với chế độ mặc định `auto`; không cần đặt `AOTMode` tường minh cho quy trình thông thường. Nếu cần điều khiển chi tiết, hãy chú ý khác biệt sau:

| Mode | JDK 26 | JDK 27 | Vai trò |
| --- | --- | --- | --- |
| `auto` | Có, mặc định | Có, mặc định | Tự chọn record/production tùy cache option; production có thể chạy tiếp nếu cache không nạp được |
| `off` | Có | Có | Không dùng AOT cache |
| `record` | Có | Có | Chạy ứng dụng để ghi dữ liệu training |
| `create` | Có | Có | Chỉ Assembly từ AOT configuration; không chạy ứng dụng |
| `on` | Có | Có nhưng là alias của `required` và bị khuyến cáo không dùng | Nạp cache theo chế độ fail-fast |
| `required` | Chưa có | Có | Yêu cầu cache phải nạp thành công; lỗi thì JVM dừng ngay |

Trong JDK 27, dùng `required` thay cho `on` khi cần kiểm tra fail-fast. Không dùng `required` cho production thông thường nếu bạn muốn ứng dụng vẫn khởi động khi cache bị thiếu hoặc không tương thích. Với production, ưu tiên `auto`.

## 7. Khi nào nên tách Training và Assembly thành hai lệnh?

Lệnh `-XX:AOTCacheOutput` rất tiện, nhưng thực hiện cả training và assembly trong cùng quy trình. JVM khởi chạy thêm một process để Assembly; process này dùng Java heap riêng với kích thước bằng heap của training JVM. Vì vậy, bộ nhớ heap cần thiết ở thời điểm Assembly có thể xấp xỉ gấp đôi `-Xmx` đã đặt, chưa tính metaspace, code cache và native memory.

Ví dụ nếu training JVM dùng `-Xmx2g`, môi trường cần khoảng 4 GB chỉ cho hai Java heap ở giai đoạn Assembly. Trong container nhỏ, cách một bước có thể bị thiếu bộ nhớ.

Khi giới hạn tài nguyên, có thể tách ba giai đoạn thủ công:

```bash
# 1. Training: ghi dữ liệu quan sát vào app.aotconfig
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -cp app.jar com.example.App

# 2. Assembly: tạo app.aot từ cấu hình đã ghi
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar com.example.App

# 3. Production: sử dụng cache
java -XX:AOTCache=app.aot -cp app.jar com.example.App
```

Ở bước Assembly, ứng dụng không được thực thi; JVM đọc `app.aotconfig` và ghi artifact vào `app.aot`. File cấu hình trung gian có thể xóa sau khi cache được tạo và kiểm tra thành công.

Tách bước giúp chạy training trên môi trường giống production nhưng ít tài nguyên, rồi chạy Assembly trên máy có nhiều RAM/CPU hơn. Máy Assembly vẫn phải cùng JDK release, hệ điều hành và kiến trúc CPU tương thích với nơi sẽ nạp cache.

## 8. Điều kiện tương thích và vòng đời cache

AOT cache gắn với ứng dụng cụ thể. Tài liệu JDK xác định cache theo:

- Ứng dụng được biểu diễn bởi `-classpath`, `-jar` hoặc `--module-path`.
- JDK release dùng để tạo cache.
- Hệ điều hành và kiến trúc CPU.

Nếu một trong các yếu tố này thay đổi, cần tạo lại cache. Trong quy trình build/deploy, hãy xem `.aot` là artifact của đúng phiên bản ứng dụng và nền tảng, không phải file dùng chung cho mọi bản phát hành.

Để training và production nhất quán:

1. Dùng cùng JDK release và cùng OS/CPU architecture.
2. Dùng cùng phiên bản ứng dụng và dependency; nếu thay JAR hoặc thư viện, tạo lại cache.
3. Giữ nguyên timestamp của JAR giữa training và production khi đóng gói/deploy.
4. Đảm bảo classpath production tương thích với classpath training; production phải bao gồm các JAR đã dùng khi training.
5. Với classpath, ưu tiên danh sách JAR rõ ràng; tránh thư mục classpath, wildcard hoặc nested JAR trong quy trình cache.
6. Dùng workload training phản ánh luồng khởi tạo và chức năng production.
7. Tránh các JVMTI agent hoặc tùy chọn JVM làm biến đổi class theo cách không tương thích với cache.

Với ứng dụng Spring Boot đóng gói dạng executable/fat JAR có nested JAR, hãy theo hướng dẫn đóng gói của framework. Spring Boot khuyến nghị extract ứng dụng ra cấu trúc thư mục triển khai trước khi training AOT cache, rồi dùng cùng cấu trúc extracted đó khi production.

## 9. JDK 26: AOT cache dùng được với mọi GC

Trước JDK 26, cơ chế lưu và nạp heap object của AOT cache phụ thuộc cách bố trí object trong heap, khiến một số tối ưu không tương thích với ZGC.

**JEP 516 — Ahead-of-Time Object Caching with Any GC** thay đổi cách nạp object từ định dạng trung gian không phụ thuộc garbage collector. JVM cấp phát và liên kết object theo layout phù hợp với collector đang chạy, thay vì ánh xạ trực tiếp một định dạng heap cố định vào bộ nhớ.

Kết quả là từ JDK 26, AOT cache có thể dùng với mọi garbage collector được HotSpot hỗ trợ, bao gồm ZGC. Không cần tạo một loại cache khác hoặc bật một cờ riêng cho ZGC.

JEP 516 không thay đổi quy trình `-XX:AOTCacheOutput` và `-XX:AOTCache`; nó mở rộng khả năng nạp object của cache sang các GC khác. JDK 27 tiếp tục giữ khả năng này.

## 10. Kiểm tra cache có thực sự được sử dụng

Sau khi tạo cache, xác nhận file tồn tại và có kích thước hợp lý. Sau đó chạy production với logging:

```bash
java -XX:AOTCache=app.aot -Xlog:aot,class+path=info -cp app.jar com.example.App
```

Nếu cần kiểm tra nghiêm ngặt khi phát triển hoặc trong pipeline, dùng fail-fast:

```bash
# JDK 26
java -XX:AOTCache=app.aot -XX:AOTMode=on -Xlog:aot -cp app.jar com.example.App

# JDK 27
java -XX:AOTCache=app.aot -XX:AOTMode=required -Xlog:aot -cp app.jar com.example.App
```

Chế độ fail-fast làm JVM dừng nếu cache không thể nạp. Đây là cách phát hiện cấu hình không tương thích trong CI hoặc kiểm tra phát hành; production thông thường nên giữ `auto` để tránh cache lỗi làm ứng dụng ngừng khởi động.

Sau khi nạp cache thành công, vẫn cần benchmark startup và warmup trên workload thực tế. Việc có file `.aot` không chứng minh rằng mọi class/object production đều nằm trong cache hoặc startup sẽ cải thiện một tỷ lệ cố định.

## 11. Các nguyên nhân cache không được dùng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| JVM chạy nhưng không dùng cache | Chế độ `auto` bỏ qua cache không tồn tại hoặc không tương thích | Bật `-Xlog:aot` để xem lý do; kiểm tra đường dẫn và quyền đọc file |
| Cache được tạo nhưng không nạp được sau khi deploy | Khác JDK release, OS/CPU architecture hoặc application classpath | Tạo lại cache trong pipeline đúng JDK và nền tảng triển khai |
| Cache không cải thiện startup | Training chưa đi qua các đường khởi tạo quan trọng | Mở rộng workload training bằng smoke test đại diện |
| Cache không tương thích sau khi cập nhật thư viện | JAR/dependency hoặc timestamp thay đổi | Tạo lại cache sau mỗi build/release của ứng dụng |
| One-step creation bị OOM | JVM Assembly thứ hai cần heap riêng tương đương training JVM | Giảm heap training hợp lý hoặc tách Training/Assembly thành hai lệnh |
| Một số class không được cache | Training không nạp class hoặc classpath không tương thích | Kiểm tra class loading với `-Xlog:class+load`/JFR và làm lại training |
| Fail-fast mode làm ứng dụng không khởi động | Cache không thể nạp hoặc JVM options không tương thích | Dùng `auto` cho production; chỉ giữ fail-fast trong kiểm tra |

## 12. Đo lợi ích thay vì chỉ dựa vào cache file

So sánh cùng ứng dụng ở hai cấu hình:

- Baseline: chạy không có `-XX:AOTCache`.
- AOT: chạy với `-XX:AOTCache=app.aot`.

Giữ các điều kiện giống nhau: JDK, heap, GC, CPU, container limit, cấu hình JVM và dữ liệu đầu vào. Đo nhiều lần sau khi môi trường đã ổn định và thu thập:

- Thời gian từ lúc process bắt đầu đến khi ứng dụng sẵn sàng nhận request.
- Thời gian đến request/operation đầu tiên hoàn tất.
- Warmup time đến khi throughput và latency đạt mức ổn định.
- RSS, native memory và heap occupancy.
- Tỷ lệ cache được nạp thành công trong các lần deploy.

AOT cache nhắm vào startup và warmup. Nếu workload chủ yếu bị giới hạn bởi database, network hoặc xử lý nghiệp vụ sau khi đã nóng, lợi ích ở throughput dài hạn có thể nhỏ. Cũng không nên so một lần cold start với một lần warm start mà không kiểm soát OS page cache và các điều kiện chạy khác.

## Ghi nhớ

- AOT cache được giới thiệu ở JDK 24; JDK 25/JEP 514 thêm cách tạo cache một bước bằng `-XX:AOTCacheOutput`.
- `-XX:AOTCacheOutput=app.aot` thực hiện Training và tự chạy Assembly khi recording kết thúc.
- Dùng `-XX:AOTCache=app.aot` ở lần chạy production; mặc định `auto` cho phép JVM tiếp tục không dùng cache nếu cache không tương thích.
- One-step creation chạy thêm JVM Assembly với heap riêng; dự trù bộ nhớ xấp xỉ hai lần `-Xmx` trong giai đoạn đó.
- Cache gắn với ứng dụng/classpath, JDK release, OS và CPU architecture; tạo lại sau khi build hoặc nâng JDK.
- Training cần workload đại diện và classpath tương thích với production.
- JDK 26/JEP 516 cho phép nạp heap object từ AOT cache với mọi GC, bao gồm ZGC.
- Dùng `-Xlog:aot` để chẩn đoán và benchmark để xác minh lợi ích thực tế.
- JDK 27 dùng `required` cho chế độ fail-fast; `on` chỉ là alias cũ. Production thông thường nên dùng `auto`.

## Tài liệu tham khảo

- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483) — thiết kế AOT cache và quy trình training/assembly/production.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514) — tạo AOT cache bằng một lệnh `-XX:AOTCacheOutput`.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515) — cải thiện warmup bằng dữ liệu profile method từ lần chạy trước.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516) — hỗ trợ cache object với mọi garbage collector từ JDK 26.
- [The `java` Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — `-XX:AOTCacheOutput`, `-XX:AOTCache`, `AOTMode`, logging và điều kiện tương thích.
- [The `java` Command, Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — mode `required`, alias `on` và hành vi auto hiện hành.
- [HotSpotAOTCacheMXBean, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/jdk/management/HotSpotAOTCacheMXBean.html) — kết thúc recording bằng `endRecording()`.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) — xác nhận JEP 516 và khả năng AOT object cache với ZGC.
- [Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations, Inside.java](https://inside.java/2026/01/09/run-aot-cache/) — ví dụ một bước, điều kiện training, chi phí bộ nhớ và cách kiểm tra cache.
- [Spring Boot AOT Cache](https://docs.spring.io/spring-boot/reference/packaging/aot-cache.html) — hướng dẫn dùng AOT cache với executable JAR đã extract.
