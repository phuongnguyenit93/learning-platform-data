# Cấu hình Generational ZGC trên đúng JDK 21

Java 21 giới thiệu **Generational ZGC**: phiên bản Z Garbage Collector chia heap thành young generation và old generation để thu gom các đối tượng mới thường xuyên hơn, còn các đối tượng sống lâu được xử lý theo chu kỳ phù hợp. Trên đúng JDK 21, cần bật cả hai tùy chọn `-XX:+UseZGC` và `-XX:+ZGenerational` để chọn chế độ này.

Điểm cần chú ý khi cấu hình theo phiên bản: JDK 21 và 22 yêu cầu bật `ZGenerational` tường minh; từ JDK 23, Generational ZGC trở thành mặc định và chế độ non-generational bị deprecated; từ JDK 24, tùy chọn `ZGenerational` đã bị loại bỏ vì ZGC chỉ còn chế độ generational. Vì vậy, không sao chép nguyên một dòng JVM arguments giữa các phiên bản JDK mà không kiểm tra phiên bản runtime.

## 1. Generational ZGC giải quyết vấn đề gì?

ZGC là garbage collector hướng đến độ trễ thấp, thực hiện phần lớn công việc thu gom đồng thời với ứng dụng. Generational ZGC bổ sung cách phân chia đối tượng theo tuổi:

- **Young generation:** chứa phần lớn đối tượng mới cấp phát. Nhiều đối tượng trong nhóm này thường không còn được sử dụng sau thời gian ngắn, nên có thể thu gom thường xuyên hơn.
- **Old generation:** chứa các đối tượng sống lâu hơn, được giữ lại qua nhiều chu kỳ young collection. Nhóm này không cần được thu gom thường xuyên như young generation.

Thiết kế này tận dụng *weak generational hypothesis*: phần lớn đối tượng được tạo ra có vòng đời ngắn, trong khi một phần nhỏ sống lâu. Thay vì thường xuyên phải xử lý toàn bộ tập đối tượng sống, GC có thể tập trung nhiều hơn vào vùng có khả năng chứa rác cao.

Generational ZGC hướng tới:

- Giảm nguy cơ allocation stall khi ứng dụng cấp phát nhanh.
- Giảm lượng heap headroom cần thiết trong một số workload.
- Giảm CPU overhead dành cho garbage collection trong các workload phù hợp.
- Duy trì mục tiêu pause time thấp của ZGC.

Đây là mục tiêu thiết kế, không phải cam kết rằng mọi ứng dụng sẽ nhanh hơn. Kết quả phụ thuộc allocation rate, live set, tỷ lệ đối tượng sống lâu, CPU, heap và workload thực tế.

## 2. Hai tùy chọn bắt buộc trên JDK 21

Để bật Generational ZGC trong JDK 21, dùng:

```shell
java -XX:+UseZGC -XX:+ZGenerational -version
```

Ý nghĩa:

| Tùy chọn | Vai trò |
|---|---|
| `-XX:+UseZGC` | Chọn Z Garbage Collector |
| `-XX:+ZGenerational` | Bật chế độ generational của ZGC trên JDK 21 |

Chỉ dùng `-XX:+UseZGC` trên JDK 21 sẽ không chọn chế độ generational. Đây là điểm dễ cấu hình sai nhất khi chuyển từ hướng dẫn của JDK mới hơn sang JDK 21.

Generational ZGC là tính năng chính thức trong JDK 21. Không cần `--enable-preview` và cũng không cần `-XX:+UnlockExperimentalVMOptions` để bật hai tùy chọn trên.

## 3. Cấu hình tối thiểu khi khởi chạy ứng dụng

Ví dụ chạy một ứng dụng JAR với JDK 21:

```shell
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar
```

Nếu cần chỉ định heap, có thể thêm `-Xms` và `-Xmx`:

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xms2g -Xmx4g -jar app.jar
```

Trong ví dụ:

- `-Xms2g` đặt kích thước heap ban đầu/tối thiểu là 2 GB.
- `-Xmx4g` đặt giới hạn tối đa của Java heap là 4 GB.
- Hai tùy chọn ZGC chọn Generational ZGC của JDK 21.

Các giá trị 2 GB và 4 GB chỉ minh họa cú pháp, không phải cấu hình khuyến nghị chung. Hãy xác định heap theo live set, tốc độ cấp phát, headroom cho quá trình GC chạy đồng thời và giới hạn bộ nhớ của môi trường triển khai.

## 4. Đặt heap size và SoftMaxHeapSize

Với ZGC, `-Xmx` là một trong những tham số quan trọng nhất. Vì GC làm việc đồng thời với ứng dụng, heap cần đủ chỗ cho:

- Các đối tượng đang còn sống (live set).
- Các đối tượng mới tiếp tục được cấp phát trong khi GC đang chạy.
- Biến động allocation rate và các đợt tải tăng đột ngột.

Nếu heap quá sát live set, ứng dụng có thể thiếu khoảng trống để tiếp tục cấp phát trong khi GC xử lý. Điều đó làm tăng nguy cơ allocation stall hoặc phải chờ GC.

`-XX:SoftMaxHeapSize` đặt một mục tiêu mềm thấp hơn hoặc bằng `-Xmx`. ZGC cố gắng giữ heap không vượt quá soft limit, nhưng vẫn có thể dùng thêm bộ nhớ cho đến `-Xmx` nếu cần để tránh ứng dụng bị đình trệ.

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xms2g -Xmx4g -XX:SoftMaxHeapSize=3g -jar app.jar
```

Ở ví dụ này, ZGC cố gắng vận hành quanh soft limit 3 GB nhưng vẫn được phép tăng đến 4 GB. `SoftMaxHeapSize` không phải hard cap và không thay thế `-Xmx`.

Khi chạy trong container, không đặt `-Xmx` bằng toàn bộ memory limit của container. JVM còn cần bộ nhớ ngoài Java heap như metaspace, code cache, thread stacks, direct buffers, thư viện native và cấu trúc nội bộ của GC. Hãy để lại headroom cho các phần này và xác nhận bằng RSS/container memory metrics.

## 5. Chọn chính sách commit và uncommit bộ nhớ

ZGC có thể trả lại các vùng heap không còn cần thiết cho hệ điều hành. Trên JDK 21, các tùy chọn liên quan gồm:

| Tùy chọn | Tác dụng |
|---|---|
| `-XX:+ZUncommit` | Cho phép uncommit vùng heap không còn sử dụng; đây là hành vi mặc định |
| `-XX:-ZUncommit` | Tắt việc uncommit vùng heap không sử dụng |
| `-XX:ZUncommitDelay=<seconds>` | Đặt thời gian một vùng heap phải không được sử dụng trước khi đủ điều kiện uncommit; mặc định là 300 giây |

Uncommit có thể giảm footprint bộ nhớ khi ứng dụng ít tải hoặc có thời gian nhàn rỗi. Tuy nhiên, việc commit lại bộ nhớ khi tải tăng có thể ảnh hưởng latency.

Ví dụ giữ heap đã commit, không trả vùng heap không dùng về hệ điều hành:

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xms4g -Xmx4g -XX:+AlwaysPreTouch -jar app.jar
```

Khi `-Xms` bằng `-Xmx`, ZGC không thể uncommit heap xuống thấp hơn mức tối thiểu này, nên uncommit bị vô hiệu hóa theo hệ quả của cấu hình. `-XX:+AlwaysPreTouch` yêu cầu JVM chạm vào các trang heap trước khi đưa bộ nhớ cho ứng dụng; điều này có thể giảm một số độ trễ do page fault lúc chạy nhưng làm thời gian khởi động và commit bộ nhớ ban đầu tăng lên.

Chỉ dùng heap cố định và `AlwaysPreTouch` khi mục tiêu latency và ngân sách bộ nhớ cho phép. Với môi trường cần co giãn footprint, hãy giữ chính sách uncommit mặc định và đo tác động của nó.

## 6. Không tự đặt kích thước young/old generation theo kiểu collector khác

Generational ZGC tự điều chỉnh kích thước generation, số GC threads và các ngưỡng liên quan dựa trên workload. Cách bắt đầu phù hợp là:

1. Bật Generational ZGC bằng đúng hai cờ của JDK 21.
2. Chọn `-Xmx` đủ cho live set và allocation headroom.
3. Thu thập GC log và số liệu ứng dụng dưới tải đại diện.
4. Chỉ thay đổi thêm heap hoặc các tùy chọn ZGC khi số liệu chỉ ra một vấn đề cụ thể.

Không bê nguyên các tham số tuning generation của G1 như `G1NewSizePercent`, `G1MaxNewSizePercent` hoặc các cấu hình young/old của collector khác sang ZGC. Generational ZGC có cơ chế quản lý generation riêng và được thiết kế để tự thích nghi.

## 7. Bật GC logging để xác nhận và theo dõi

Java 21 dùng Unified Logging. Để ghi log GC cơ bản:

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc -jar app.jar
```

Để thu thập log chi tiết hơn vào file:

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

Có thể thêm rotation để tránh file log tăng không giới hạn:

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
```

Khi đọc log, hãy quan sát:

- Loại chu kỳ thu gom, bao gồm các chu kỳ young và major.
- Thời lượng các pha pause và thời gian chu kỳ GC chạy đồng thời.
- Heap occupancy trước/sau collection.
- Tần suất collection và dấu hiệu allocation stall.
- Thời điểm GC tăng hoạt động so với thời điểm latency ứng dụng tăng.

GC log là một nguồn dữ liệu để điều tra, không tự cho biết toàn bộ nguyên nhân chậm. Cần đối chiếu với allocation rate, CPU, request latency, throughput và bộ nhớ thực tế của tiến trình.

## 8. Xác minh runtime thực sự đang dùng JDK 21 và Generational ZGC

Trước khi kiểm tra cờ GC, xác định chính xác runtime mà service sử dụng:

```shell
java -version
```

Trong môi trường có nhiều JDK, lệnh `java` trên terminal có thể khác JDK được cấu hình trong service, container, IDE hoặc script khởi chạy. Hãy kiểm tra command line thực tế của tiến trình production.

Có thể yêu cầu JVM in các flag cuối cùng:

```shell
java -XX:+UseZGC -XX:+ZGenerational -XX:+PrintFlagsFinal -version
```

Trong output, kiểm tra các giá trị `UseZGC` và `ZGenerational` đều là `true`. Đây là cách xác nhận flag đã được nhận và giá trị cuối cùng của chúng. Kết hợp với GC log lúc chạy ứng dụng để xác nhận collector được chọn và quan sát hoạt động thực tế.

Nếu JVM báo `Unrecognized VM option 'ZGenerational'`, thường là runtime không phải JDK 21/22 hỗ trợ cờ này, hoặc đang dùng một bản phân phối/runtime không có tùy chọn tương ứng. Kiểm tra `java -version` của chính tiến trình và tài liệu nhà cung cấp JDK.

## 9. Khác biệt cấu hình giữa JDK 21 và JDK mới hơn

Generational ZGC đã thay đổi cách được bật qua các bản phát hành:

| JDK | Cách chọn Generational ZGC | Ghi chú |
|---|---|---|
| JDK 21 và JDK 22 | `-XX:+UseZGC -XX:+ZGenerational` | Phải bật generational mode tường minh |
| JDK 23 | `-XX:+UseZGC` | Generational mode trở thành mặc định; chế độ non-generational bị deprecated |
| JDK 24 trở lên | `-XX:+UseZGC` | ZGC chỉ còn generational mode; tùy chọn `ZGenerational` đã bị loại bỏ |

Vì vậy:

- Nếu ứng dụng thực sự chạy trên JDK 21, giữ cả `-XX:+UseZGC` và `-XX:+ZGenerational`.
- Nếu nâng runtime lên JDK 23 hoặc mới hơn, cập nhật JVM arguments theo phiên bản mới; không tiếp tục thêm cờ đã deprecated hoặc removed.
- Không đặt cùng lúc nhiều cờ GC xung đột như `-XX:+UseG1GC` và `-XX:+UseZGC`; chỉ chọn một collector cho tiến trình.

Đây là khác biệt phiên bản cần giữ trong tài liệu vận hành. Cấu hình JDK 21 vẫn đúng cho JDK 21; việc JDK mới hơn thay đổi mặc định không làm cho cờ `ZGenerational` có thể dùng vô thời hạn.

## 10. Khi nào nên chọn Generational ZGC?

Generational ZGC đáng để thử nghiệm khi ứng dụng có yêu cầu latency thấp, heap lớn hoặc allocation rate cao và có thể hưởng lợi từ việc thu gom đối tượng ngắn hạn thường xuyên hơn.

Trước khi chọn, hãy xem xét:

- **Latency objective:** p95/p99 hoặc SLA có nhạy với GC pause hay không.
- **Heap và live set:** heap có đủ chỗ cho live set và headroom không.
- **Allocation profile:** ứng dụng tạo nhiều đối tượng ngắn hạn hay giữ nhiều đối tượng lâu dài.
- **CPU budget:** concurrent GC sử dụng CPU trong khi ứng dụng đang chạy.
- **Throughput:** giảm pause có thể đi kèm chi phí CPU hoặc throughput khác với collector khác.
- **Memory limit:** heap và native memory có nằm trong giới hạn máy/container không.

Không phải mọi ứng dụng đều cần ZGC. Nếu G1 đáp ứng latency và throughput mục tiêu với chi phí thấp hơn, thay collector không đem lại lợi ích thực tế. Hãy benchmark trên workload đại diện thay vì chọn chỉ dựa trên tên collector.

## 11. Đo hiệu năng trước và sau khi bật

Để đánh giá cấu hình, so sánh cùng một ứng dụng và workload với collector hiện tại và Generational ZGC:

1. Dùng cùng JDK 21 update release, phần cứng, container limit và cấu hình ứng dụng.
2. Warm up ứng dụng trước khi lấy số liệu.
3. Dùng cùng dữ liệu và cùng mức tải, gồm cả steady load và burst nếu production có burst.
4. Đo throughput, p50/p95/p99 latency, error rate và timeout.
5. Thu GC log, CPU utilization, heap occupancy, allocation rate, RSS và thời gian GC.
6. Lặp lại nhiều lần và so sánh trong điều kiện tương đương.

Không chỉ nhìn vào pause time. Một cấu hình có pause ngắn nhưng dùng quá nhiều CPU hoặc tăng RSS vượt giới hạn container vẫn có thể là lựa chọn không phù hợp.

## 12. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chạy JDK 21 nhưng không dùng generational mode | Chỉ truyền `-XX:+UseZGC` | Bổ sung `-XX:+ZGenerational` |
| JVM báo không nhận `ZGenerational` | Runtime không phải JDK 21/22 hoặc phiên bản mới đã loại bỏ cờ | Kiểm tra runtime thực tế và dùng cấu hình đúng phiên bản |
| JVM báo không nhận `UseZGC` | Runtime hoặc bản phân phối không hỗ trợ ZGC trên nền tảng đó | Kiểm tra JDK vendor, version và platform support |
| Ứng dụng vẫn gặp allocation stall | Heap thiếu headroom, allocation rate tăng hoặc GC không theo kịp | Kiểm tra `-Xmx`, live set, allocation rate và GC log |
| Container bị OOM dù Java heap chưa chạm `-Xmx` | Native memory, direct buffer, metaspace hoặc thread stack làm tổng RSS vượt limit | Giảm heap hợp lý và theo dõi native/container memory |
| Latency tăng khi tải thấp | Commit/uncommit hoặc các hoạt động nền có thể ảnh hưởng | Kiểm tra GC log; đánh giá `-Xms`, `-Xmx`, `ZUncommit` và `AlwaysPreTouch` theo số liệu |
| CPU tăng sau khi chuyển sang ZGC | Concurrent GC và workload cạnh tranh CPU | Đo allocation profile, headroom và CPU; benchmark với collector khác |
| Log quá lớn | Bật `-Xlog:gc*` nhưng không cấu hình rotation | Đặt `filecount` và `filesize` phù hợp |

Không tăng heap hoặc tắt uncommit một cách tự động khi thấy latency cao. Trước tiên cần xác định latency đến từ GC pause, concurrent GC CPU, allocation stall, I/O hay phần xử lý ứng dụng.

## 13. Checklist triển khai trên JDK 21

- Xác nhận service đang chạy bằng JDK 21.
- Bật đúng hai cờ `-XX:+UseZGC -XX:+ZGenerational`.
- Không thêm `--enable-preview` hoặc `-XX:+UnlockExperimentalVMOptions` cho tính năng này.
- Chọn `-Xmx` dựa trên live set, allocation rate và headroom.
- Chỉ đặt `SoftMaxHeapSize` khi có mục tiêu soft limit rõ ràng.
- Quyết định có cần heap cố định, uncommit hoặc `AlwaysPreTouch` dựa trên latency và memory budget.
- Bật `-Xlog:gc` hoặc `-Xlog:gc*` trong giai đoạn quan sát; cấu hình rotation khi ghi file.
- Xác minh flag bằng `-XX:+PrintFlagsFinal` và xem GC log của tiến trình thực tế.
- Theo dõi throughput, p95/p99 latency, CPU, heap, RSS, allocation rate và GC activity.
- Benchmark với workload production-like trước khi áp dụng rộng rãi.
- Khi nâng lên JDK 23+, bỏ cờ `ZGenerational` theo thay đổi phiên bản.

Generational ZGC trên Java 21 được bật bằng `-XX:+UseZGC -XX:+ZGenerational`. Sau khi chọn đúng collector, phần quan trọng nhất là cấp đủ heap headroom, quan sát GC log và đo hiệu năng dưới tải thực tế. Khi vận hành trên JDK mới hơn, phải cập nhật JVM arguments theo thay đổi mặc định và vòng đời của tùy chọn `ZGenerational`.

## Tài liệu tham khảo

- [Oracle JDK 21 Release Notes — Generational ZGC](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [Oracle Java 21 — Z Garbage Collector Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html)
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
- [JEP 490 — ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490)
